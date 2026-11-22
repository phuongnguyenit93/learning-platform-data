# FileReader, FileWriter và lựa chọn charset trong Java

## 1. Vì sao đọc/ghi tệp văn bản cần quan tâm đến charset?

Tệp trên đĩa lưu **byte**, nhưng chương trình Java thường làm việc với **ký tự** (`char`, `String`). Giữa hai thế giới này luôn có bước chuyển đổi:

```text
Đọc tệp:
Tệp (byte) ──giải mã bằng Charset──> Reader ──ký tự──> Chương trình

Ghi tệp:
Chương trình ──ký tự──> Writer ──mã hóa bằng Charset──> Tệp (byte)
```

Trong nhóm **luồng ký tự** (`java.io`), `FileReader` đọc ký tự từ tệp và `FileWriter` ghi ký tự ra tệp. Chúng giúp sử dụng API `Reader`/`Writer` thay vì tự ghép từng byte. Tuy nhiên, **chỉ gọi `new FileReader("data.txt")` hoặc `new FileWriter("data.txt")` không nói rõ tệp đang dùng bộ mã ký tự nào**. Chọn sai charset có thể tạo văn bản lỗi dấu như `CafÃ©` hoặc gây mất thông tin khi ghi.

Mục tiêu của bài: biết `FileReader`/`FileWriter` làm gì, dùng đúng API Java 17+, chọn charset rõ ràng và xử lý các tình huống thực tế như ghi đè, nối thêm, xuống dòng, lỗi mã hóa và tài nguyên tệp.

### Các khái niệm nền

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Character / ký tự | Đơn vị văn bản ở tầng ứng dụng; API `Reader`/`Writer` trao đổi các đơn vị `char` UTF-16 của Java |
| Byte | Đơn vị 8 bit được lưu trên tệp; khác với `char` |
| Charset | Quy tắc ánh xạ giữa ký tự và byte (ví dụ UTF-8, UTF-16, ISO-8859-1) |
| Encoding | Chiều mã hóa ký tự thành byte khi ghi |
| Decoding | Chiều giải mã byte thành ký tự khi đọc |
| Default charset | Charset mặc định của Java runtime, có thể khác nhau theo phiên bản/cấu hình |
| Mojibake | Chữ bị biến dạng do đọc byte với charset khác charset đã dùng khi ghi |

Charset là **quy ước của dữ liệu**; tên file `.txt`, `.csv`, `.json` tự nó không xác định charset.

## 2. `FileReader`: đọc tệp thành ký tự

`FileReader` kế thừa `InputStreamReader` → `Reader`. Nó mở tệp, đọc byte từ nguồn và **giải mã** chúng thành các đơn vị `char` Java. Một số cách khởi tạo trên Java 17:

```java
Reader reader1 = new FileReader("notes.txt"); // Charset mặc định của JVM.
Reader reader2 = new FileReader("notes.txt", StandardCharsets.UTF_8);
Reader reader3 = new FileReader(Path.of("notes.txt").toFile(),
                                StandardCharsets.UTF_8);
```

Đây là **đoạn minh họa**, cần import `java.io.FileReader`, `java.io.Reader`, `java.nio.charset.StandardCharsets` và `java.nio.file.Path`; hãy đóng các reader sau khi dùng. Các constructor nhận `Charset` được thêm từ **Java 11**. Dùng constructor có charset để ghi rõ hợp đồng của tệp.

Một số phương thức kế thừa từ `Reader`:

| Phương thức | Ý nghĩa |
| --- | --- |
| `int read()` | Đọc một đơn vị `char` dạng `int`, hoặc `-1` khi hết luồng |
| `int read(char[] buffer)` | Đọc một số đơn vị ký tự vào mảng, trả số đã đọc hoặc `-1` |
| `int read(char[] buffer, int off, int len)` | Đọc vào đoạn `buffer[off .. off+len)` |
| `long skip(long n)` | Bỏ qua tối đa `n` đơn vị ký tự, có thể bỏ qua ít hơn |
| `void close()` | Đóng reader và tài nguyên liên quan |

Lưu ý:

- Kết quả `read()` phải lưu vào `int` để phân biệt dữ liệu với **EOF = -1**.
- `read(char[])` không cam kết điền đầy mảng mỗi lần. Chỉ xử lý `buffer[0..count)` khi `count > 0`.
- Một `char` là **một code unit UTF-16**, không nhất thiết là một Unicode code point. Ví dụ emoji nằm ngoài BMP thường gồm **hai `char`** (surrogate pair). Do đó số đơn vị `char` đọc không nhất thiết bằng số “ký tự người dùng nhìn thấy”.
- `FileReader` đọc **văn bản**; nếu phải giữ nguyên byte của ảnh, ZIP hoặc file nhị phân thì dùng `InputStream`.

### Đọc đến EOF bằng mảng ký tự

```java
// Giả định biến Reader reader đã được mở trong try-with-resources.
char[] buffer = new char[4096];
int count;
while ((count = reader.read(buffer)) != -1) {
    // Chỉ xử lý các phần tử 0 đến count - 1.
}
```

Đây là **mẫu mã trong ngữ cảnh**, chưa phải một chương trình chạy độc lập. Điều kiện dừng luôn dựa trên giá trị trả về của `read`, không dựa vào kích thước tệp bằng byte.

## 3. `FileWriter`: ghi ký tự thành byte

`FileWriter` kế thừa `OutputStreamWriter` → `Writer`. Nó nhận `String`/`char`, **mã hóa theo charset** rồi ghi byte vào tệp.

```java
Writer writer1 = new FileWriter("notes.txt"); // Charset mặc định.
Writer writer2 = new FileWriter("notes.txt", StandardCharsets.UTF_8);
Writer writer3 = new FileWriter("notes.txt", StandardCharsets.UTF_8, true);
```

Đây là **đoạn minh họa**, cần import `java.io.FileWriter`, `java.io.Writer`, `java.nio.charset.StandardCharsets` và quản lý đóng luồng. Tham số boolean `true` ở constructor thứ ba là **append**: nối thêm vào cuối tệp. Các constructor kết hợp `Charset` với `append` có từ Java 11.

Các phương thức quan trọng:

| Phương thức | Hành vi |
| --- | --- |
| `write(int c)` | Ghi một đơn vị `char` (16 bit thấp của `int`), rồi mã hóa thành byte theo charset |
| `write(char[] data)` | Ghi toàn bộ mảng ký tự |
| `write(char[] data, int off, int len)` | Ghi đoạn mảng ký tự |
| `write(String text)` | Ghi chuỗi ký tự |
| `write(String text, int off, int len)` | Ghi một đoạn chuỗi |
| `append(CharSequence csq)` | Thêm ký tự vào luồng |
| `flush()` | Đẩy dữ liệu đệm của writer xuống tầng bên dưới; writer vẫn dùng được |
| `close()` | Kết thúc writer, xử lý dữ liệu đệm còn lại và giải phóng tài nguyên |

Mặc định `new FileWriter(path, UTF_8)` **tạo tệp nếu chưa tồn tại**, và **xóa nội dung cũ để ghi mới** khi tệp đã tồn tại. Điều này quan trọng với file cấu hình, log và dữ liệu người dùng. `new FileWriter(path, UTF_8, true)` dùng để nối thêm; nó **không tự thêm ký tự xuống dòng** giữa nội dung cũ và mới.

Cũng như luồng byte, `flush()` không phải bảo đảm dữ liệu đã bền vững trên đĩa (`fsync`). Với tài nguyên do mình mở, ưu tiên `try-with-resources` để `close()` tự chạy khi kết thúc khối, kể cả nếu có ngoại lệ.

## 4. Charset nào cần chọn và vì sao UTF-8 thường là mặc định tốt?

**UTF-8** mã hóa ASCII thông dụng bằng một byte, đồng thời biểu diễn được toàn bộ Unicode bằng chuỗi byte có độ dài thay đổi. Nó phù hợp cho văn bản đa ngôn ngữ, bao gồm tiếng Việt, và có tính liên thông tốt với công cụ, API, HTML, JSON.

Một số charset thường gặp:

| Charset | Đặc điểm | Khi nào nên dùng |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Unicode, 1–4 byte cho mỗi code point | Lựa chọn ưu tiên cho file text mới và trao đổi dữ liệu hiện đại |
| `StandardCharsets.UTF_16` | Unicode, byte-order mark có thể được dùng để biểu thị thứ tự byte | Khi định dạng/tệp quy định UTF-16 |
| `StandardCharsets.UTF_16LE` / `UTF_16BE` | Dạng UTF-16 có thứ tự byte xác định | Khi hệ thống đối tác yêu cầu chính xác LE/BE |
| `StandardCharsets.ISO_8859_1` | Một byte/đơn vị ký tự trong tập Latin-1, không biểu diễn đầy đủ tiếng Việt | Chỉ khi dữ liệu thực sự là Latin-1 |
| `StandardCharsets.US_ASCII` | Chỉ các ký tự ASCII | Dữ liệu có giao kèo ASCII |
| Charset cũ như `windows-1252` | Mã hóa legacy giới hạn ký tự | Khi phải tương thích với tệp/hệ thống cũ theo đặc tả |

**Đừng chọn charset theo chữ có vẻ đọc được**. UTF-8 cũng có thể chứa hoàn toàn ASCII; nhìn dòng `Hello` không chứng minh định dạng là UTF-8. Hãy xác nhận qua tài liệu định dạng, cấu hình xuất dữ liệu, BOM nếu có, hoặc quy ước rõ ràng giữa bên ghi và bên đọc.

### Vì sao không dựa vào `Charset.defaultCharset()`?

Các phiên bản Java có khác biệt quan trọng:

- **Java 17 trở về trước:** default charset của JVM thường phụ thuộc hệ điều hành, locale hoặc cấu hình runtime. Hai máy có thể mặc định khác nhau.
- **Java 18 trở lên:** theo **JEP 400**, mặc định trong phần lớn API Java SE là **UTF-8**; có chế độ tương thích `-Dfile.encoding=COMPAT`. Một số kênh console/thiết bị còn có quy tắc encoding riêng.
- `Files.newBufferedReader(path)` và `Files.newBufferedWriter(path)` được đặc tả dùng UTF-8 khi không truyền charset, kể cả trên Java 17; vì vậy đừng đồng nhất mặc định của hai API này với `new FileReader(path)` không tham số charset.

Nếu file do ứng dụng kiểm soát, hãy chọn **`StandardCharsets.UTF_8` tường minh** ở cả đầu đọc và đầu ghi. Nếu định dạng bên ngoài bắt buộc charset khác, **phải tuân thủ charset đó** thay vì tự chuyển sang UTF-8 mà không thống nhất.

## 5. Ví dụ chạy được: vòng ghi và đọc UTF-8

Chương trình sau tạo file `hello-utf8.txt`, ghi tiếng Việt bằng `FileWriter` với UTF-8, đọc lại bằng `FileReader` cùng charset và so sánh nội dung. Nó dùng vòng `read(char[])` để thể hiện hợp đồng đọc từng phần.

**Lưu thành `FileTextRoundTrip.java` (mã nguồn UTF-8):**

```java
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileTextRoundTrip {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("hello-utf8.txt");
        String original = "Tiếng Việt: Hà Nội, Đà Nẵng và Cần Thơ.";

        try (Writer writer =
                     new FileWriter(path.toFile(), StandardCharsets.UTF_8)) {
            writer.write(original);
        }

        StringBuilder restored = new StringBuilder();
        try (Reader reader =
                     new FileReader(path.toFile(), StandardCharsets.UTF_8)) {
            char[] buffer = new char[8];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                restored.append(buffer, 0, count);
            }
        }

        System.out.println("Equal text: " + original.contentEquals(restored));
        System.out.println("File exists: " + Files.exists(path));
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac -encoding UTF-8 FileTextRoundTrip.java
java FileTextRoundTrip
```

**Stdout chính xác khi đọc/ghi thành công:**

```text
Equal text: true
File exists: true
```

Hai `try-with-resources` tạo ranh giới rõ: writer phải được đóng hoàn toàn **trước khi** reader mở để đọc tệp. Việc tạo `FileReader` sau khi `FileWriter` kết thúc cũng tránh phải đoán thời điểm dữ liệu đệm đã xuống tệp.

`StringBuilder.append(char[], offset, length)` dùng đúng `count`; nếu không, ở lượt đọc cuối sẽ lẫn ký tự cũ trong mảng đệm. Định dạng file là UTF-8 vì **cả hai constructor dùng cùng `StandardCharsets.UTF_8`**. In ra boolean ASCII giúp kết quả kiểm thử không phụ thuộc font hoặc charset của terminal.

## 6. Minh họa hỏng dấu khi chọn sai charset

Giả sử một tệp chứa từ `Café` được lưu UTF-8. Chữ `é` có byte UTF-8 là `C3 A9`. Nếu cùng hai byte này bị diễn giải dưới Latin-1 thì cho ra hai ký tự `Ã` và `©`, tạo chuỗi `CafÃ©`. Đây là **mojibake**, không phải do kiểu `String` tự làm hỏng Unicode.

**Tệp `CharsetMismatch.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class CharsetMismatch {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("cafe-utf8.txt");
        String expected = "Café";

        Files.writeString(path, expected, StandardCharsets.UTF_8);

        String correct = Files.readString(path, StandardCharsets.UTF_8);
        String wrong = Files.readString(path, StandardCharsets.ISO_8859_1);

        System.out.println("UTF-8 matches: " + expected.equals(correct));
        System.out.println("Latin-1 matches: " + expected.equals(wrong));
        System.out.println("File hex: "
                + HexFormat.of().formatHex(Files.readAllBytes(path)));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CharsetMismatch.java
java CharsetMismatch
```

**Stdout chính xác:**

```text
UTF-8 matches: true
Latin-1 matches: false
File hex: 436166c3a9
```

`HexFormat` có từ Java 17. Các byte `43 61 66` là `Caf` ở ASCII; `C3 A9` là ký tự `é` ở UTF-8. Kết quả boolean chứng minh rằng **byte không thay đổi nhưng chuỗi sau giải mã có thể khác nhau**. Nếu một tệp vốn là Latin-1 mà ta đọc nhầm thành UTF-8, decoder có thể gặp chuỗi byte không hợp lệ và xử lý theo quy tắc lỗi của API.

Đổi cách giải mã **không phải phép sửa chữa thần kỳ**: nếu dữ liệu đã bị giải mã sai, chỉnh sửa, rồi ghi đè lại, thông tin gốc có thể đã mất. Cần biết tệp gốc được tạo bằng encoding gì.

## 7. Ghi đè, append và ranh giới dòng

Hai cách mở writer có ý nghĩa khác nhau:

```java
// Ghi mới: nội dung cũ của file sẽ bị xóa.
new FileWriter("events.txt", StandardCharsets.UTF_8);

// Nối thêm byte được tạo từ ký tự ghi:
new FileWriter("events.txt", StandardCharsets.UTF_8, true);
```

Đây là **đoạn minh họa**; khi dùng thật hãy mở trong `try-with-resources` và đóng writer. Cũng cần nhớ rằng append chỉ di chuyển điểm ghi tới cuối tệp; không tự thêm dấu cách hoặc ký tự xuống dòng.

**Tệp `AppendText.java`:**

```java
import java.io.BufferedReader;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class AppendText {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("events.txt");

        // Chạy nhiều lần vẫn bắt đầu bằng nội dung xác định.
        try (FileWriter writer =
                     new FileWriter(path.toFile(), StandardCharsets.UTF_8)) {
            writer.write("first");
            writer.write(System.lineSeparator());
        }

        try (FileWriter writer =
                     new FileWriter(path.toFile(), StandardCharsets.UTF_8, true)) {
            writer.write("second");
            writer.write(System.lineSeparator());
        }

        try (BufferedReader reader =
                     new BufferedReader(
                             new FileReader(path.toFile(), StandardCharsets.UTF_8))) {
            System.out.println("Line 1: " + reader.readLine());
            System.out.println("Line 2: " + reader.readLine());
            System.out.println("EOF: " + (reader.readLine() == null));
        }
    }
}
```

Chạy:

```bash
javac AppendText.java
java AppendText
```

**Stdout chính xác:**

```text
Line 1: first
Line 2: second
EOF: true
```

`BufferedReader.readLine()` đọc đến ký tự kết thúc dòng hoặc EOF và **loại bỏ ký tự kết thúc dòng khỏi chuỗi trả về**. Khi không còn dữ liệu, nó trả `null`; `null` khác với một dòng rỗng (`""`). `System.lineSeparator()` tạo xuống dòng theo nền tảng, thường `"\n"` trên Linux/macOS hoặc `"\r\n"` trên Windows. Nếu định dạng file yêu cầu LF cố định (ví dụ một giao thức hay file được chuẩn hóa), hãy ghi chính xác `"\n"` theo quy ước đó thay vì lệ thuộc hệ điều hành.

Tệp cũ có thể **không có dòng kết thúc**; nối `second` lúc này sẽ dính vào chữ cuối cùng của dòng trước. Bài toán ghi log cần thận trọng hơn: nhiều tiến trình nối cùng file, khóa tệp, đồng bộ và rollover không được bảo đảm chỉ bằng `append=true`.

## 8. FileReader/FileWriter và BufferedReader/BufferedWriter

`FileReader` và `FileWriter` mở tệp và chuyển đổi charset. Chúng đã có cơ chế đệm nhất định khi chuyển đổi giữa byte và ký tự, nhưng không cung cấp mọi tiện ích đọc/ghi theo dòng của các lớp buffered wrapper.

```java
// Đoạn minh họa; imports java.io.* và StandardCharsets.
try (BufferedReader reader = new BufferedReader(
        new FileReader("input.txt", StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng, không giữ toàn bộ file trong RAM.
    }
}
```

`BufferedReader` có `readLine()`; `BufferedWriter` có `newLine()`. Wrapper hỗ trợ các thao tác kích thước nhỏ hiệu quả hơn tùy workload. Khi dùng `try-with-resources`, chỉ khai báo và đóng wrapper ngoài nếu wrapper sở hữu luồng trong; đóng wrapper sẽ đóng reader/writer bên dưới.

Có thể tạo writer theo dòng:

```java
// Đoạn minh họa; imports java.io.* và StandardCharsets.
try (BufferedWriter writer = new BufferedWriter(
        new FileWriter("output.txt", StandardCharsets.UTF_8))) {
    writer.write("Dòng thứ nhất");
    writer.newLine();
    writer.write("Dòng thứ hai");
}
```

`newLine()` dùng dấu kết thúc dòng theo nền tảng. Nếu file có quy định newline LF/CRLF riêng, hãy ghi đúng ký tự đó.

### Dùng API Files hiện đại khi thuận tiện

Java 17 còn có API `java.nio.file.Files` trả về `BufferedReader`/`BufferedWriter`:

```java
Path path = Path.of("notes.txt");

// UTF-8 được ghi rõ, giữ hợp đồng nội dung rõ ràng:
try (BufferedWriter writer =
         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Xin chào!");
}

try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
```

Đoạn này yêu cầu import `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets`, `java.io.BufferedReader`, `java.io.BufferedWriter` và xử lý `IOException`. Nếu chạy thành công, stdout là `Xin chào!` trên terminal hỗ trợ Unicode. Cả `Files.newBufferedReader(path)` lẫn `Files.newBufferedWriter(path)` mặc định dùng UTF-8, song truyền tường minh vẫn giúp người đọc code nhận ra quy ước.

Với tệp text nhỏ, `Files.readString(path, StandardCharsets.UTF_8)` và `Files.writeString(path, text, StandardCharsets.UTF_8)` ngắn gọn. Tuy nhiên, đọc cả tệp thành một chuỗi cần bộ nhớ tỷ lệ kích thước tệp; dùng `Reader`/`BufferedReader` để xử lý tuần tự dữ liệu lớn. `Files.writeString` mặc định tạo hoặc truncate tệp; muốn append thì dùng `StandardOpenOption.APPEND` cùng các tùy chọn tạo file phù hợp.

### Bảng chọn cách tiếp cận

| Nhu cầu | API hợp lý |
| --- | --- |
| Hiểu cơ chế reader/writer gắn tệp | `new FileReader(file, charset)`, `new FileWriter(file, charset)` |
| Đọc file text theo từng dòng | `Files.newBufferedReader(path, charset)` hoặc `BufferedReader(FileReader)` |
| Ghi file text từng dòng | `Files.newBufferedWriter(path, charset)` hoặc `BufferedWriter(FileWriter)` |
| Tệp nhỏ, đọc/ghi nguyên chuỗi | `Files.readString` / `Files.writeString` |
| Chỉ sao chép tệp nguyên trạng, không cần hiểu nội dung | API byte như `Files.copy` / `InputStream` |
| Chuyển mã giữa các định dạng text | Reader giải mã theo charset nguồn rồi Writer mã hóa theo charset đích |

## 9. Chuyển mã charset và xử lý tệp legacy

Giả sử đã xác minh tệp cũ thực sự lưu Latin-1, muốn chuyển sang UTF-8. Hướng đi đúng là:

```text
legacy.txt (Latin-1 bytes)
    └─ FileReader(..., ISO_8859_1)
            └─ các char Unicode trong Java
                    └─ FileWriter(..., UTF_8)
                            └─ utf8.txt (UTF-8 bytes)
```

**Tệp `ConvertLatin1ToUtf8.java`:**

```java
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class ConvertLatin1ToUtf8 {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java ConvertLatin1ToUtf8 <latin1-source> <utf8-target>");
            return;
        }

        Path source = Path.of(args[0]);
        Path target = Path.of(args[1]);

        if (source.toAbsolutePath().normalize()
                    .equals(target.toAbsolutePath().normalize())
                || (java.nio.file.Files.exists(target)
                    && java.nio.file.Files.isSameFile(source, target))) {
            throw new IllegalArgumentException("Use distinct files");
        }

        try (Reader reader =
                     new FileReader(source.toFile(), StandardCharsets.ISO_8859_1);
             Writer writer =
                     new FileWriter(target.toFile(), StandardCharsets.UTF_8)) {
            char[] buffer = new char[4096];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                writer.write(buffer, 0, count);
            }
        }

        System.out.println("Conversion complete");
    }
}
```

Chạy sau khi có tệp nguồn Latin-1:

```bash
javac ConvertLatin1ToUtf8.java
java ConvertLatin1ToUtf8 legacy.txt utf8.txt
```

**Stdout khi hoàn tất thành công:**

```text
Conversion complete
```

Bài toán này khác **sao chép nhị phân**: file đầu ra có thể chứa byte khác và kích thước khác dù nội dung ký tự tương đương. Không thể suy ra charset nguồn chắc chắn từ tên file; ví dụ đang giả định charset nguồn đã được xác minh. Không dùng hai đường dẫn cùng tệp vì mở writer có thể xóa nguồn. Kiểm tra đường dẫn trước khi mở chỉ giảm rủi ro trong tình huống thông thường, không phải cơ chế chống thay đổi đồng thời nguyên tử.

**Hạn chế của ISO-8859-1:** nó không bao phủ tất cả chữ tiếng Việt. Nếu dữ liệu gốc đến từ encoding kiểu `windows-1258` hay một charset khác, phải chọn đúng charset thực tế, ví dụ `Charset.forName("windows-1258")` **nếu charset đó được runtime hỗ trợ**. Không thay bừa bằng Latin-1 khi thấy file lỗi dấu.

## 10. Encoding lỗi, ký tự không biểu diễn được và BOM

### 10.1 Charset không phải lúc nào cũng nhận được mọi dữ liệu

Với charset hạn chế như US-ASCII hoặc Latin-1, một số ký tự Unicode **không thể mã hóa trực tiếp**. Ngược lại, byte stream có thể chứa chuỗi byte **không hợp lệ** đối với UTF-8.

Phản ứng khi gặp dữ liệu không hợp lệ/phần ký tự không biểu diễn được phụ thuộc API và cách cấu hình decoder/encoder. Một số đường tạo reader/writer thuận tiện có thể dùng **replacement** (ký tự thay thế khi giải mã hoặc byte thay thế khi mã hóa), khiến chương trình tiếp tục chạy nhưng mất thông tin. Vì vậy “không có exception” **không chứng minh dữ liệu được giữ nguyên**.

Nếu bắt buộc phát hiện dữ liệu không hợp lệ, có thể cấu hình **`CharsetDecoder`** và chọn hành động `CodingErrorAction.REPORT`:

```java
// Minh họa đọc UTF-8 nghiêm ngặt từ tệp đã có.
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(
        Files.newInputStream(Path.of("input.txt")), decoder)) {
    char[] buf = new char[4096];
    while (reader.read(buf) != -1) {
        // Xử lý nội dung đã giải mã.
    }
}
```

Đây là **đoạn minh họa**; cần `java.nio.charset.CharsetDecoder`, `CodingErrorAction`, `StandardCharsets`, `java.io.InputStreamReader`, `java.io.Reader`, `java.nio.file.Files`, `Path`. Khi gặp byte UTF-8 malformed, decoder ở chế độ `REPORT` có thể ném `MalformedInputException` (một `IOException`). Cần quyết định rõ chính sách ứng dụng: báo lỗi, thay ký tự hoặc bỏ qua, không âm thầm sửa nội dung quan trọng.

Tương tự có thể cấu hình `CharsetEncoder` với `REPORT` khi cần phát hiện ký tự không mã hóa được.

### 10.2 Byte Order Mark (BOM)

BOM là một mẫu byte ở đầu một số tệp Unicode để nhận biết encoding/thứ tự byte. Với UTF-8, BOM thường là `EF BB BF` và **không bắt buộc**. `FileWriter` với UTF-8 **không tự chèn BOM**; nếu dữ liệu nguồn có BOM, cần hiểu cách công cụ/decoder cụ thể xử lý, tránh xuất hiện ký tự `U+FEFF` không mong muốn ở đầu nội dung.

Với UTF-16, thứ tự byte là quan trọng. Dùng `UTF_16`, `UTF_16LE`, `UTF_16BE` theo **đúng định dạng được quy định**; đừng phỏng đoán dựa vào hệ điều hành.

### 10.3 Ký tự Unicode và việc cắt buffer

Vì `Reader` trả đơn vị `char` UTF-16, một code point ngoài BMP có thể chia thành **hai code unit**. Vòng đọc/gửi `char[]` không vì thế có nghĩa là mỗi lần đọc trả nguyên một “ký tự hiển thị”. Nếu ứng dụng cần xử lý Unicode code point độc lập, có thể dùng `String.codePoints()` sau khi tập hợp một đoạn chuỗi hợp lệ và chú ý cặp surrogate bị chia qua ranh giới buffer.

Khi **sao chép ký tự trung thực** từ Reader sang Writer có cùng quy ước, việc ghi từng mảng theo thứ tự vẫn phù hợp; quan trọng là không loại bỏ hoặc sửa cặp surrogate giữa các lần đọc.

## 11. Đọc theo dòng và định dạng xuống dòng

Khi cần các dòng logic, `BufferedReader.readLine()` tiện hơn tự tìm `'\n'`. Nó nhận biết LF, CR hoặc CRLF và trả nội dung **không chứa dấu kết thúc dòng**. Tệp có dòng rỗng sẽ cho `""` còn EOF là `null`.

Nếu đọc bằng `readLine()` rồi viết lại với `writer.newLine()`, file đầu ra có thể đổi dấu xuống dòng từ LF sang CRLF hoặc ngược lại tùy môi trường. Nếu mục tiêu là **giữ nguyên nội dung tệp đến từng byte**, không giải mã rồi ghi lại theo dòng mà nên sao chép byte.

Trong các định dạng có yêu cầu xuống dòng cố định, ví dụ trao đổi dữ liệu giữa Linux và Windows, thống nhất `"\n"` hay `"\r\n"` theo đặc tả. Nếu file text được tạo bởi nhiều thành phần khác nhau, hãy xác định cả **charset** và **newline convention**.

## 12. Vòng đời tài nguyên và các lỗi cần xử lý

Dùng `try-with-resources` để đóng `FileReader`/`FileWriter` ngay cả khi phát sinh ngoại lệ:

```java
try (FileReader reader =
         new FileReader("input.txt", StandardCharsets.UTF_8)) {
    // Xử lý dữ liệu.
}
```

Đây là **đoạn minh họa** có các import tương ứng. Nếu `read()`/ `write()` xảy ra lỗi, thường nhận `IOException` hoặc ngoại lệ con; thao tác mở reader có thể thất bại nếu file không tồn tại/không có quyền đọc, writer có thể thất bại nếu không thể tạo/ghi file. Kết quả ghi dở có thể để lại **file đầu ra chỉ chứa một phần dữ liệu**; đóng tài nguyên không biến cả thao tác thành giao dịch nguyên tử.

Một số nguyên tắc:

1. **Rõ người sở hữu luồng**: nếu phương thức nhận một Reader do bên gọi sở hữu, cần quy định bên nào chịu trách nhiệm đóng. Không tùy tiện đóng luồng được dùng chung.
2. **Tránh ghi đè ngoài ý muốn**: với file quan trọng, kiểm tra tình huống tồn tại tệp, dùng lựa chọn tạo file phù hợp hoặc một quy trình ghi tạm rồi thay thế khi thành công.
3. **Đọc từng phần khi file lớn**: `Files.readString`/ `readAllLines` tích lũy dữ liệu trong RAM, trong khi `BufferedReader.readLine` xử lý từng dòng.
4. **Phân biệt lỗi kỹ thuật và lỗi dữ liệu**: file mở được nhưng sai charset không nhất thiết phát sinh `IOException` ngay.
5. **Đừng trông cậy `flush()` để bảo đảm tính bền vững**: ứng dụng cần bảo đảm ghi xuống thiết bị phải dùng cơ chế đồng bộ file riêng.
6. **Nếu mở nhiều resource trong cùng try**: Java đóng theo thứ tự **ngược** thứ tự khai báo và giữ các lỗi đóng bổ sung trong `suppressed exceptions`.

## 13. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `new FileReader("a.txt")` trên Java 17 mà quên default charset | Có thể đọc khác nhau giữa các máy | `new FileReader("a.txt", UTF_8)` hoặc đúng charset của dữ liệu |
| Ghi UTF-8 nhưng đọc Latin-1/charset mặc định khác | Sai dấu, mojibake | Thống nhất charset hai phía |
| Ghi tiếng Việt với US-ASCII | Ký tự không biểu diễn được có thể bị thay | Chọn UTF-8 hoặc encoding hỗ trợ dữ liệu |
| Dùng `byte[]` rồi ép thẳng sang `char` để đọc văn bản | Bỏ qua quy tắc mã hóa đa byte | Dùng `Reader`/`CharsetDecoder` |
| Ghi `new FileWriter(path, UTF_8)` lên tệp đang có dữ liệu | Tệp cũ bị truncate | Chủ động chọn ghi mới, append hoặc fail-if-exists |
| `append=true` nhưng không chèn newline | Nội dung bị dính dòng | Thêm newline theo định dạng |
| Cho rằng mỗi `read(char[])` lấp đầy buffer | Mất dữ liệu hoặc lấy ký tự cũ | Dựa đúng `count` |
| So `char` trực tiếp với EOF rồi bỏ qua kiểu trả về | Dễ nhầm `int -1` với dữ liệu ký tự | Giữ kết quả `read()` ở `int` |
| Quên `close()` writer | Có thể giữ tài nguyên, chưa đẩy hết dữ liệu đệm | `try-with-resources` |
| Đọc toàn bộ file rất lớn vào `String` | Tốn nhiều bộ nhớ | Streaming theo khối hoặc dòng |
| Dùng `readLine()` rồi `newLine()` khi cần giữ byte gốc | Newline/encoding có thể thay đổi | Sao chép byte nguyên trạng |
| Giả định mọi file UTF-8 đều có BOM | Có thể bỏ sai byte đầu hoặc để lại U+FEFF | Theo đặc tả file/đầu vào thực tế |

## 14. Quy tắc chọn API trong thực tế

- **Chỉ muốn lưu/đọc văn bản mới theo UTF-8 và thao tác đơn giản:** `Files.writeString`/`Files.readString` cho file nhỏ; `Files.newBufferedReader`/`newBufferedWriter` cho dữ liệu dài.
- **Đang dùng `FileReader`/`FileWriter`:** truyền `StandardCharsets.UTF_8` hoặc charset được đặc tả thay vì dùng mặc định không rõ.
- **Muốn thao tác theo dòng:** dùng `BufferedReader`/`BufferedWriter`.
- **Muốn sửa hay chuyển charset của tài liệu legacy:** biết chính xác charset nguồn, giải mã đúng rồi mã hóa theo charset đích; test với các ký tự khó như chữ có dấu và emoji.
- **Muốn giữ byte 100%:** ưu tiên API byte, không tự giải mã rồi mã hóa lại.
- **Cần xử lý dữ liệu có thể sai encoding:** xác định chính sách lỗi và cân nhắc decoder/encoder với `CodingErrorAction.REPORT`.

Không có một charset “đúng cho mọi tệp”: **UTF-8 là lựa chọn tốt cho tệp mới**, nhưng với file hiện hữu thì charset đúng là charset mà nguồn dữ liệu thực sự sử dụng.

## 15. Bài tập tự kiểm tra

1. Chạy `FileTextRoundTrip` hai lần và xác nhận `hello-utf8.txt` bị ghi lại từ đầu. Đổi `original` thành chuỗi có emoji và dấu tiếng Việt, kiểm tra `Equal text: true`.
2. Chạy `CharsetMismatch`, lý giải từng nhóm byte trong `436166c3a9` và vì sao đọc Latin-1 không bằng bản gốc.
3. Trong `AppendText`, bỏ `System.lineSeparator()` ở lần ghi đầu. Dự đoán `readLine()` sẽ trả gì và kiểm chứng.
4. Viết hàm đọc file UTF-8 theo dòng, đếm số dòng rỗng. Phân biệt dòng `""` với `null` ở EOF.
5. Xây dựng tệp UTF-8 sai (ví dụ byte `0xC3` đứng một mình cuối file), thử decoder mặc định và decoder `REPORT`, ghi lại sự khác nhau về kết quả hoặc exception.
6. Tự trả lời: vì sao Java 17 không nên phụ thuộc vào `new FileReader(path)` khi dữ liệu đa ngôn ngữ? Khi nào cần `ISO_8859_1`? Khi sao chép file ảnh có nên dùng `FileReader`/`FileWriter` không?
7. Cho tệp `legacy.txt` được xác nhận là Latin-1, thử chương trình chuyển mã và kiểm tra byte đầu/đuôi của tệp đích; giải thích vì sao tệp kết quả UTF-8 có thể lớn hơn.

## Tài liệu tham khảo

- Java SE 17 API: [`FileReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileReader.html), [`FileWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileWriter.html).
- Java SE 17 API: [`Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [`StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- OpenJDK: [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400).

**Ghi nhớ:** `FileReader` đọc byte từ tệp rồi giải mã thành ký tự; `FileWriter` mã hóa ký tự thành byte rồi ghi. Chọn **đúng charset của dữ liệu**, ưu tiên **UTF-8 rõ ràng** với file mới, quản lý resource bằng `try-with-resources`, và kiểm tra cẩn thận chế độ **ghi đè/append**.
