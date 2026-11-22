# BufferedReader.readLine(): đọc từng dòng và dấu kết thúc dòng bị loại bỏ

`BufferedReader.readLine()` trong Java giúp đọc văn bản từng dòng mà không cần tự dò ký tự xuống dòng. Mỗi lần gọi trả về **nội dung của một dòng, đã bỏ dấu kết thúc dòng**, hoặc `null` nếu hết dữ liệu và không còn ký tự nào để tạo một dòng mới.

Điều này rất tiện khi phân tích từng dòng trong tệp cấu hình, log hoặc dữ liệu văn bản. Tuy nhiên, có một hệ quả quan trọng: **không thể biết dòng vừa đọc kết thúc bằng `\n`, `\r`, `\r\n` hay đơn giản kết thúc tại EOF chỉ từ `String` mà `readLine()` trả về**. Khi cần giữ nguyên dấu kết thúc dòng, phải chọn cách đọc khác.

## 1. BufferedReader là gì?

`java.io.BufferedReader` là một `Reader` có bộ đệm ký tự. Nó thường bọc quanh một `Reader` khác để đọc nhiều ký tự hiệu quả hơn, chẳng hạn `FileReader` hoặc `InputStreamReader`. Ngoài thao tác `read()` đọc ký tự, phương thức `readLine()` gom các ký tự thành một dòng.

Ví dụ một vòng lặp đọc:

~~~java
String line;
while ((line = reader.readLine()) != null) {
    // Xử lý đúng nội dung dòng, không có ký tự kết thúc dòng.
    System.out.println(line);
}
~~~

Đây là **mảnh mã minh họa**: biến `reader` phải là một `BufferedReader` đã mở, và chương trình phải xử lý `IOException`. Phép gán trong điều kiện là có chủ đích: mỗi vòng gọi `readLine()` **một lần** rồi so sánh giá trị trả về với `null`.

Luồng dữ liệu có hai lớp cần phân biệt:

~~~text
Tệp hoặc luồng byte --[giải mã bằng Charset]--> Reader chứa ký tự
                                            |
                                            v
                                        BufferedReader
                                            |
                                            v
                                    readLine(): String hoặc null
~~~

`BufferedReader` xử lý **ký tự đã được giải mã**, không trực tiếp quyết định encoding của file. Nếu nguồn là byte, chọn charset chính xác khi xây dựng `InputStreamReader`, hoặc dùng `Files.newBufferedReader(path, StandardCharsets.UTF_8)`. Điều này quan trọng với chữ tiếng Việt và dữ liệu trao đổi giữa nhiều máy.

## 2. Những dấu kết thúc dòng mà readLine() nhận diện

Theo hợp đồng của `BufferedReader.readLine()`, một dòng được coi là kết thúc tại:

| Ký hiệu trong chuỗi Java | Tên | Các ký tự kết thúc dòng |
|---|---|---|
| `"\n"` | LF (line feed) | `U+000A` |
| `"\r"` | CR (carriage return) | `U+000D` |
| `"\r\n"` | CRLF | Hai ký tự `U+000D U+000A` đi liền nhau |

Cả ba trường hợp đều được nhận diện khi đọc. Với CRLF, `\r\n` được tính là **một** dấu kết thúc dòng, không tạo thêm dòng rỗng chỉ vì có hai ký tự.

Ví dụ:

~~~text
Dữ liệu đầu vào dưới dạng escape: "Java\r\nSpring\nSQL\rEOF"
Kết quả gọi readLine() lần lượt:
1. "Java"
2. "Spring"
3. "SQL"
4. "EOF"
5. null
~~~

Dòng `"EOF"` được trả về dù không có dấu xuống dòng phía sau: **EOF cũng có thể kết thúc dòng cuối cùng có nội dung**. Chỉ lần gọi tiếp theo, khi không còn ký tự nào, mới trả về `null`.

Đừng nhầm ba dấu kết thúc dòng này với mọi ký tự Unicode hiển thị như xuống dòng. Ví dụ `U+2028` (LINE SEPARATOR) **không phải** dấu ngắt dòng được `readLine()` mô tả trong hợp đồng. `readLine()` cũng không yêu cầu dấu xuống dòng phải trùng `System.lineSeparator()` của hệ điều hành hiện tại. Một ứng dụng chạy trên Windows vẫn đọc đúng dữ liệu có LF và ngược lại.

## 3. Chính xác điều gì bị loại bỏ?

Giả sử nguồn chứa:

~~~text
"A\r\nB\nC\rD"
~~~

`BufferedReader.readLine()` trả theo thứ tự:

~~~text
"A"
"B"
"C"
"D"
null
~~~

Mỗi `String` trả về **không chứa** `\r` hoặc `\n` được dùng để kết thúc dòng. Phương thức không thêm dấu cách hoặc ký tự phân cách thay thế.

Không có thông tin nào đi kèm giá trị trả về cho biết dòng đó dùng LF, CR, CRLF hay kết thúc do EOF. Vì thế các nguồn khác nhau có thể tạo **cùng một danh sách các dòng**. Chẳng hạn cả `"A\nB"` và `"A\r\nB"` đều tạo danh sách `["A", "B"]`.

Lưu ý rằng `readLine()` loại bỏ **dấu kết thúc dòng**, chứ không gọi `trim()` hoặc `strip()`:

- Khoảng trắng đầu dòng và cuối dòng (dấu cách, tab) vẫn nằm trong `String`.
- Một dòng chứa ba dấu cách trả về chuỗi dài 3, **không phải** chuỗi rỗng.
- Một dòng trống thật sự trả về `""`, nghĩa là `String` có độ dài 0, **không phải** `null`.
- Những ký tự `\r`/`\n` đóng vai trò dấu ngắt dòng không còn nằm trong kết quả.

Nếu ứng dụng cần phân biệt dòng trắng do khoảng trắng với dòng hoàn toàn trống, hãy kiểm tra trực tiếp `line.isEmpty()` so với `line.isBlank()`. Hai điều kiện mang ý nghĩa khác nhau.

## 4. Ví dụ hoàn chỉnh: CRLF, CR, LF và dòng trống

Tạo file **`ReadLineDemo.java`** với mã sau (Java 17+):

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ReadLineDemo {
    public static void main(String[] args) throws IOException {
        String content = "An\r\n\r\nBinh\nCuong\rDung\n";

        try (BufferedReader reader = new BufferedReader(
                new StringReader(content))) {
            String line;
            int index = 0;
            while ((line = reader.readLine()) != null) {
                index++;
                System.out.printf("%d: <%s> (len=%d)%n",
                        index, line, line.length());
            }
            System.out.println("count=" + index);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ReadLineDemo.java
java ReadLineDemo
~~~

Stdout chính xác:

~~~text
1: <An> (len=2)
2: <> (len=0)
3: <Binh> (len=4)
4: <Cuong> (len=5)
5: <Dung> (len=4)
count=5
~~~

Giải thích thứ tự:

1. `"An\r\n"` tạo dòng `"An"`; cả CR và LF của cặp CRLF bị bỏ.
2. `"\r\n"` ngay sau đó tạo một dòng **rỗng**; đó là dòng thứ hai `""`, có độ dài 0.
3. `"Binh\n"` tạo `"Binh"`, `"Cuong\r"` tạo `"Cuong"`.
4. `"Dung\n"` tạo `"Dung"`. Dù dữ liệu có LF cuối cùng, `readLine()` **không sinh thêm một dòng rỗng** chỉ vì chuỗi kết thúc bằng đúng một dấu kết thúc dòng.
5. Lần gọi sau cùng gặp EOF, trả `null`; vòng lặp dừng.

Ví dụ sử dụng `StringReader` để kết quả không phụ thuộc hệ điều hành hoặc encoding của file thực tế. Quy tắc loại dấu kết thúc dòng là quy tắc của `BufferedReader` và vẫn áp dụng khi nguồn là tệp.

## 5. Phân biệt dòng rỗng, hết file và newline ở cuối

Đây là phần thường gây lỗi nhất. Xem các mẫu dữ liệu sau:

| Nội dung nguồn (cú pháp escape) | Những giá trị `readLine()` trước EOF | Số dòng |
|---|---|---:|
| `""` | Không có `String` nào; trả `null` ngay | 0 |
| `"\n"` | `""` rồi `null` | 1 |
| `"\r\n"` | `""` rồi `null` | 1 |
| `"A"` | `"A"` rồi `null` | 1 |
| `"A\n"` | `"A"` rồi `null` | 1 |
| `"A\r\n"` | `"A"` rồi `null` | 1 |
| `"A\n\n"` | `"A"`, `""` rồi `null` | 2 |
| `"\nA"` | `""`, `"A"` rồi `null` | 2 |
| `"A\n\nB"` | `"A"`, `""`, `"B"` rồi `null` | 3 |

Hai khác biệt cần nhớ:

**Dòng trống**: một dấu kết thúc dòng xuất hiện khi chưa có ký tự nội dung kể từ dấu kết thúc dòng trước đó. Vì vậy đọc `"\n"` cho dòng rỗng `""`. Vòng lặp phải tiếp tục khi giá trị là `""`.

**EOF**: khi `readLine()` không còn bất kỳ ký tự nào để tạo một dòng mới, nó trả `null`. Dòng cuối có nội dung được trả về ngay cả khi chưa có dấu kết thúc dòng. Khi dấu kết thúc dòng đã là ký tự cuối, EOF sau đó **không phát sinh thêm dòng mới**.

Vì thế `"A"` và `"A\n"` cho cùng chuỗi trả về `"A"` rồi `null`. Nếu cần biết file gốc có newline cuối hay không, `readLine()` **không đủ thông tin**.

### Kiểm chứng bằng chương trình Java

Tạo **`ReadLineEdgeCases.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;

public class ReadLineEdgeCases {
    public static void main(String[] args) throws IOException {
        inspect("empty", "");
        inspect("LF", "\n");
        inspect("A", "A");
        inspect("A+LF", "A\n");
        inspect("A+LF+LF", "A\n\n");
        inspect("A+CRLF", "A\r\n");
    }

    private static void inspect(String label, String source)
            throws IOException {
        List<String> lines = new ArrayList<>();

        try (BufferedReader reader = new BufferedReader(
                new StringReader(source))) {
            String line;
            while ((line = reader.readLine()) != null) {
                lines.add(line);
            }
        }

        String first = lines.isEmpty()
                ? "<none>" : "\"" + lines.get(0) + "\"";
        System.out.printf("%s -> count=%d, first=%s%n",
                label, lines.size(), first);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReadLineEdgeCases.java
java ReadLineEdgeCases
~~~

Stdout:

~~~text
empty -> count=0, first=<none>
LF -> count=1, first=""
A -> count=1, first="A"
A+LF -> count=1, first="A"
A+LF+LF -> count=2, first="A"
A+CRLF -> count=1, first="A"
~~~

Chương trình cho thấy sự khác biệt giữa **`null` khi EOF**, **`""` khi có một dòng trống**, và việc **một dấu xuống dòng ở cuối không tự cộng thêm một dòng rỗng**.

## 6. Đọc file thực tế: luôn kiểm soát charset

Khi nguồn là tệp, có thể dùng `Files.newBufferedReader`. Mặc định `Files.newBufferedReader(path)` dùng UTF-8; để rõ hợp đồng dữ liệu, nên truyền `StandardCharsets.UTF_8` tường minh, nhất là khi xử lý file chứa tiếng Việt.

Ví dụ độc lập **`ReadTextFileLines.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadTextFileLines {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("read-lines-", ".txt");

        try {
            Files.writeString(path, "red\r\n\r\nblue\n",
                    StandardCharsets.UTF_8);

            try (BufferedReader reader = Files.newBufferedReader(
                    path, StandardCharsets.UTF_8)) {
                String line;
                int lineNumber = 0;
                while ((line = reader.readLine()) != null) {
                    System.out.printf("%d: [%s]%n",
                            ++lineNumber, line);
                }
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReadTextFileLines.java
java ReadTextFileLines
~~~

Stdout:

~~~text
1: [red]
2: []
3: [blue]
~~~

Tệp tạm chỉ phục vụ minh họa; đoạn mã dùng `finally` để xóa sau khi đóng `BufferedReader`. Với một đường dẫn do người dùng cung cấp, hãy xử lý quyền truy cập và `IOException`; đừng dùng mã xóa file tạm để xóa một tệp thật.

Có thể mở bằng constructor truyền charset khác:

~~~java
// Mảnh mã minh họa: path là một Path đã được xác định.
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Sử dụng line.
    }
}
~~~

Đây là cách thuận tiện khi nguồn là file UTF-8. Nếu file được mã hóa bằng charset khác, phải biết và truyền đúng charset đó; `BufferedReader` **không tự phát hiện encoding**. Một số byte sai encoding có thể gây lỗi giải mã hoặc ký tự thay thế tùy reader/decoder và quy tắc của API.

### BufferedReader và dấu BOM

Nếu file UTF-8 có tiền tố BOM (`EF BB BF`), các API đọc ký tự UTF-8 thường có thể để lại ký tự `U+FEFF` ở đầu nội dung thay vì tự loại bỏ nó. `readLine()` **chỉ loại dấu kết thúc dòng** theo hợp đồng, nên đừng kỳ vọng nó loại BOM, khoảng trắng hoặc metadata khác. Nếu hệ thống hỗ trợ file có BOM, hãy quyết định xử lý BOM tại đầu văn bản theo định dạng dữ liệu.

## 7. Khi ghi lại: dấu kết thúc dòng có thể bị thay đổi

Vì đã mất ký tự phân cách gốc, code đọc bằng `readLine()` rồi ghi bằng một separator tự chọn sẽ **chuẩn hóa dấu kết thúc dòng**, không tái tạo byte gốc.

Ví dụ:

~~~java
// Mảnh mã minh họa: reader và writer đã được mở và cần đóng đúng cách.
String line;
while ((line = reader.readLine()) != null) {
    writer.write(line);
    writer.newLine();
}
~~~

`BufferedWriter.newLine()` ghi **line separator của nền tảng hiện tại** theo quy tắc của `System.lineSeparator()`. Nếu file gốc dùng CRLF, chương trình chạy trên một môi trường dùng LF có thể đổi CRLF thành LF. Hơn nữa, ví dụ này luôn ghi một dấu kết thúc dòng sau mỗi dòng, kể cả khi dòng cuối của nguồn ban đầu không có dấu kết thúc dòng.

Với `writer.write('\n')`, chương trình cố định LF nhưng cũng vẫn thay đổi đầu vào nếu nguyên bản dùng CRLF/CR. Với `System.lineSeparator()` hoặc `PrintWriter.println()`, ý nghĩa cũng là tạo một separator mới, không phải khôi phục separator đã bị xóa.

### Ví dụ nhận biết việc chuẩn hóa

Tạo tệp **`NormalizeLinesDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class NormalizeLinesDemo {
    public static void main(String[] args) throws IOException {
        String source = "one\r\ntwo\rthree\n";
        StringBuilder normalized = new StringBuilder();

        try (BufferedReader reader = new BufferedReader(
                new StringReader(source))) {
            boolean first = true;
            String line;
            while ((line = reader.readLine()) != null) {
                if (!first) {
                    normalized.append('\n');
                }
                normalized.append(line);
                first = false;
            }
        }

        System.out.println("source chars=" + source.length());
        System.out.println("normalized chars=" + normalized.length());
        System.out.println("normalized="
                + normalized.toString().replace("\n", "|"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NormalizeLinesDemo.java
java NormalizeLinesDemo
~~~

Stdout:

~~~text
source chars=15
normalized chars=13
normalized=one|two|three
~~~

Nội dung nguồn có CRLF, CR và một LF ở cuối; kết quả chỉ nối các dòng bằng LF và không có newline cuối. `boolean first` được dùng thay vì `normalized.length() > 0` vì **dòng đầu có thể rỗng**: một dòng rỗng vẫn phải được tính là một dòng đã đọc. Ngay cả khi code chèn LF trước mỗi dòng sau dòng đầu, việc khôi phục byte nguồn chính xác vẫn là điều không thể từ các chuỗi `readLine()` đơn thuần.

Nếu mục đích chỉ là **phân tích nội dung từng dòng**, bỏ dấu ngắt thường là điều mong muốn. Nếu mục đích là **sao chép file nguyên vẹn**, đừng dùng đọc dòng rồi ghi lại; sao chép byte bằng `Files.copy` hoặc `InputStream`/`OutputStream`. Nếu cần chỉnh sửa mà bảo toàn chính xác CR, LF, CRLF và trạng thái newline cuối, phải đọc theo ký tự/byte và lưu separator cùng từng dòng (hoặc giữ toàn bộ nội dung trong bộ nhớ khi kích thước cho phép).

## 8. readLine(), lines() và các API khác

| Cách đọc | Kết quả | Mức độ giữ separator |
|---|---|---|
| `BufferedReader.readLine()` | Một `String` mỗi lần; `null` khi EOF | Bỏ CR, LF, CRLF |
| `BufferedReader.lines()` | `Stream<String>` của các dòng | Vẫn bỏ dấu kết thúc dòng |
| `Files.lines(path, charset)` | `Stream<String>` từ file | Bỏ dấu kết thúc dòng |
| `Files.readAllLines(path, charset)` | `List<String>` của toàn bộ dòng | Bỏ dấu kết thúc dòng |
| `Files.readString(path, charset)` | Toàn bộ văn bản dưới dạng `String` | Giữ các ký tự `\r` và `\n` có trong nội dung |
| Đọc bằng `Reader.read()` hoặc `read(char[])` | Các ký tự thô được reader giải mã | Có thể quan sát và lưu lại CR/LF |

`BufferedReader.lines()` có thể thuận tiện cho xử lý kiểu Stream, nhưng kết quả vẫn là các dòng **không mang terminator**. Khi đọc `lines()` mà có lỗi I/O trong quá trình tiêu thụ stream, ngoại lệ được biểu diễn dưới dạng `UncheckedIOException`. Không trộn thao tác đọc trực tiếp trên `BufferedReader` với việc tiêu thụ stream `lines()` đang hoạt động.

Ví dụ khi muốn duyệt từng dòng bằng Stream:

~~~java
// Mảnh mã minh họa: reader cần đang mở trong phạm vi try-with-resources.
reader.lines()
      .filter(line -> !line.isBlank())
      .forEach(System.out::println);
~~~

Giải pháp này chủ động bỏ dòng trống và dòng chỉ có whitespace vì điều kiện `!line.isBlank()`; đó là quyết định của ứng dụng, **không phải hành vi mặc định của `readLine()`**.

Lưu ý quản lý tài nguyên: với một stream lấy từ `reader.lines()`, đóng stream không thay thế cho việc quản lý đóng `reader` theo hợp đồng của `BufferedReader`; hãy sử dụng `try-with-resources` cho `BufferedReader`. Với `Files.lines(...)`, stream trả về chứa tài nguyên file và chính stream cần đóng.

## 9. Hiệu năng, độ dài dòng và các trường hợp cần cẩn thận

- **Có thể chặn để chờ**: trên một nguồn ký tự đang mở như socket, `readLine()` có thể chờ đến khi gặp dấu kết thúc dòng, EOF hoặc lỗi; không nên giả định mỗi lần gọi lập tức có một dòng.
- **Dòng rất dài**: `BufferedReader` có bộ đệm nhưng `readLine()` vẫn phải tạo `String` cho toàn bộ dòng. Dữ liệu không đáng tin cậy có thể có dòng dài bất thường gây tiêu thụ bộ nhớ lớn. Nếu cần giới hạn kích thước mỗi bản ghi, nên có logic đọc ký tự theo giới hạn trước khi gom toàn bộ dòng.
- **Không phải parser CSV tổng quát**: CSV có thể chứa dấu xuống dòng bên trong trường được đặt trong dấu nháy. `readLine()` chỉ phân tách dòng vật lý, không tự phân tách bản ghi logic của CSV.
- **Không loại whitespace**: `readLine()` không gọi `trim()`/`strip()`, không bỏ comment, không tách token; ứng dụng phải chủ động chọn bước xử lý sau đó.
- **Không dùng `reader.ready()` làm điều kiện hết file**: `ready()` cho biết liệu thao tác đọc tiếp theo có thể không bị block, không phải dấu EOF. Cách lặp đúng vẫn là kiểm tra `readLine() != null`.
- **Ngoại lệ I/O**: phương thức có thể ném `IOException`; dùng `try-with-resources`, phản ánh rõ lỗi đọc và tránh giả định rằng `null` đại diện cho lỗi.

Đối với file nhỏ và mục tiêu giữ nguyên các ký tự ngắt dòng, `Files.readString(path, UTF_8)` dễ hiểu hơn. Với file lớn và mục tiêu xử lý theo dòng, `BufferedReader.readLine()` giúp không cần tải toàn bộ file, miễn là từng dòng vẫn có kích thước hợp lý.

## 10. Các lỗi thường gặp và cách sửa

| Sai sót | Vì sao sai | Cách làm đúng |
|---|---|---|
| `while ((line = reader.readLine()) != "")` | So sánh tham chiếu `String` và không kiểm tra EOF; có thể gặp `null` | Dùng `while ((line = reader.readLine()) != null)` |
| `if (line.isEmpty()) break;` | Dòng rỗng `""` là dữ liệu hợp lệ, không phải EOF | Dừng khi `line == null` |
| Nghĩ file kết thúc bằng `\n` thì có thêm dòng rỗng | Một terminator cuối không tạo thêm một dòng mới ở EOF | Xem các ví dụ `"A\n"` và `"A\n\n"` |
| Ghép `readLine()` bằng `System.lineSeparator()` để tái tạo file y nguyên | Separator gốc đã bị loại, không còn biết LF/CRLF/CR hoặc newline cuối | Đọc/giữ separator thô nếu cần bảo toàn |
| Giả định `readLine()` tự hiểu UTF-8 | `BufferedReader` đọc ký tự đã giải mã bởi Reader bên dưới | Chọn charset ở `InputStreamReader` hoặc `Files.newBufferedReader` |
| Dùng `trim()` khi cần giữ whitespace | `trim()` xóa nội dung có ý nghĩa, khác với việc bỏ terminator | Dùng nguyên `line`, chỉ strip nếu nghiệp vụ yêu cầu |
| Dùng `reader.ready()` để xác định EOF | `ready()` không phải phép kiểm tra hết dữ liệu | Đọc đến khi trả `null` |
| Dùng `readLine()` cho tài liệu phải bảo toàn byte hoặc newline | Thao tác đọc dòng làm mất thông tin phân cách | Đọc ký tự/byte thô hoặc `Files.readString` với file vừa bộ nhớ |

## 11. Ghi nhớ

1. `BufferedReader.readLine()` nhận diện **LF (`\n`), CR (`\r`) và CRLF (`\r\n`)** và **loại bỏ dấu kết thúc dòng** khỏi `String` trả về.
2. **`null` nghĩa là EOF** khi không còn dòng nào; **`""` là một dòng rỗng hợp lệ**. Phải dừng trên `null`, không dừng trên `""`.
3. Dòng cuối **không có terminator** vẫn được trả về; dấu newline đơn lẻ ở cuối file **không tạo thêm một dòng trống**.
4. Từ `readLine()` **không thể khôi phục chính xác** loại separator hoặc biết có newline ở cuối nguồn. Đọc rồi ghi lại thường thay đổi dấu xuống dòng.
5. Chọn **charset chính xác**, đóng `BufferedReader` bằng `try-with-resources` và xử lý `IOException`.
6. Dùng đọc theo dòng cho xử lý nội dung; dùng cách đọc bảo toàn ký tự/byte nếu yêu cầu giữ nguyên định dạng.

### Tài liệu tham khảo chính thức

- [Java SE — BufferedReader.readLine()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#readLine())
- [Java SE — BufferedReader.lines()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#lines())
- [Java SE — Files.newBufferedReader()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset))
