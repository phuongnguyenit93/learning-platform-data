# Đọc, ghi văn bản bằng `Files.readString` và `Files.writeString` trong Java 17

Từ Java 11, lớp `java.nio.file.Files` cung cấp hai phương thức tiện lợi để làm việc với tệp văn bản: `readString` đọc toàn bộ nội dung tệp thành một `String`, còn `writeString` ghi văn bản vào tệp. Cả hai đều có sẵn và dùng ổn định trong Java 17.

Hai phương thức giúp mã xử lý tệp ngắn gọn hơn so với việc tự tạo `BufferedReader` hoặc `BufferedWriter`. Khi sử dụng, bạn vẫn cần quyết định rõ **đường dẫn**, **charset**, **cách mở tệp** (ghi đè hay nối thêm), và **cách xử lý lỗi I/O**.

> **Phạm vi:** Bài tập trung vào `Files.readString(Path)` và `Files.writeString(Path, CharSequence)` cùng các overload có `Charset` và `OpenOption`. API được bổ sung từ Java 11, không phải preview feature.

## 1. Hai phương thức làm gì?

Các import chính:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
~~~

Đọc tệp:

~~~java
Path path = Path.of("data", "message.txt");
String content = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(content);
~~~

Ghi tệp:

~~~java
Path path = Path.of("data", "message.txt");
Files.writeString(path, "Xin chào Java 17", StandardCharsets.UTF_8);
~~~

`readString` trả về nội dung văn bản dưới dạng một `String`. `writeString` nhận một `CharSequence` (ví dụ `String`) và ghi các ký tự đó vào tệp.

Các phương thức này thuộc `java.nio.file.Files`, làm việc với `Path` thuộc NIO.2. Chúng tự mở và đóng tài nguyên bên trong; bạn không cần tự quản lý stream cho mỗi lần gọi.

### 1.1. Overload không truyền charset

Java cung cấp cách gọi ngắn:

~~~java
String content = Files.readString(path);
Files.writeString(path, content);
~~~

**Hai overload không chỉ định charset đều sử dụng UTF-8.** Đây là quy định của chính API, không phụ thuộc charset mặc định của hệ điều hành hay `Charset.defaultCharset()`.

Nếu định dạng tệp là UTF-8, bạn có thể dùng overload ngắn. Trong mã xử lý dữ liệu cần thể hiện rõ hợp đồng mã hóa, ghi `StandardCharsets.UTF_8` tường minh thường giúp người đọc hiểu ngay cách diễn giải byte.

### 1.2. Các overload quan trọng

| Phương thức | Ý nghĩa |
|---|---|
| `Files.readString(path)` | Đọc toàn bộ tệp, dùng UTF-8 |
| `Files.readString(path, charset)` | Đọc toàn bộ tệp bằng charset được chỉ định |
| `Files.writeString(path, text)` | Ghi văn bản bằng UTF-8 với tùy chọn mở mặc định |
| `Files.writeString(path, text, charset)` | Ghi văn bản bằng charset được chỉ định |
| `Files.writeString(path, text, options...)` | Ghi bằng UTF-8 và tùy chỉnh cách mở tệp |
| `Files.writeString(path, text, charset, options...)` | Ghi bằng charset và tùy chỉnh cách mở tệp |

`readString` và `writeString` có thể ném `IOException` khi xảy ra lỗi đọc, ghi hoặc mã hóa/giải mã.

## 2. Tạo đường dẫn tệp bằng Path

`Files` nhận đối tượng `Path`, không nhận trực tiếp một chuỗi tên tệp. Có thể tạo `Path` bằng `Path.of(...)`:

~~~java
Path relative = Path.of("data", "notes.txt");
Path inHome = Path.of(System.getProperty("user.home"), "notes.txt");
~~~

Dùng nhiều thành phần đường dẫn riêng biệt giúp Java ghép dấu phân cách phù hợp với hệ điều hành. Tránh tự nối chuỗi kiểu `"data/" + fileName` nếu muốn mã dễ chuyển giữa Windows, Linux và macOS.

### 2.1. Thư mục cha phải tồn tại

`writeString` có thể tạo tệp đích nếu được mở với tùy chọn mặc định, nhưng **không tự tạo toàn bộ thư mục cha còn thiếu**.

Ví dụ, nếu thư mục `data` chưa tồn tại, việc ghi vào `data/notes.txt` có thể thất bại với `NoSuchFileException`.

Tạo thư mục trước:

~~~java
Path path = Path.of("data", "notes.txt");
Files.createDirectories(path.getParent());
Files.writeString(path, "Nội dung ghi vào tệp", StandardCharsets.UTF_8);
~~~

`createDirectories` tạo cả các thư mục cha cần thiết; nếu thư mục đã tồn tại thì không gây lỗi chỉ vì nó đã có sẵn.

Nếu đường dẫn chỉ là tên tệp đơn giản như `Path.of("notes.txt")`, `getParent()` có thể trả về `null`. Khi viết helper dùng cho cả đường dẫn có và không có thư mục cha, hãy kiểm tra trước:

~~~java
Path path = Path.of("notes.txt");
Path parent = path.getParent();

if (parent != null) {
    Files.createDirectories(parent);
}
~~~

### 2.2. Đường dẫn tương đối được tính từ thư mục làm việc

Đường dẫn tương đối như `Path.of("data", "notes.txt")` được phân giải theo thư mục làm việc hiện tại của tiến trình Java. Thư mục này có thể khác thư mục chứa file `.java` hoặc file `.class`.

Khi debug, có thể in:

~~~java
System.out.println(Path.of("data", "notes.txt").toAbsolutePath());
System.out.println(System.getProperty("user.dir"));
~~~

Điều này giúp xác định chính xác ứng dụng đang tìm hoặc tạo tệp ở đâu.

## 3. Đọc toàn bộ tệp bằng readString

Ví dụ đầy đủ:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadTextDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data", "message.txt");
        String content = Files.readString(path, StandardCharsets.UTF_8);

        System.out.println("Nội dung tệp:");
        System.out.println(content);
    }
}
~~~

Nếu tệp chứa:

~~~text
Xin chào
Java 17
Đọc văn bản bằng Files
~~~

thì `content` chứa toàn bộ các dòng đó trong một chuỗi.

### 3.1. readString giữ các ký tự xuống dòng

`readString` đọc văn bản thành chuỗi; nó không tự tách dòng thành `List<String>` và cũng không tự xóa ký tự xuống dòng.

Ví dụ, nếu nội dung tệp có ký tự xuống dòng giữa hai dòng, `content` sẽ giữ ký tự tương ứng. Tệp dùng LF (`\n`) và tệp dùng CRLF (`\r\n`) có thể tạo chuỗi khác nhau ở phần kết thúc dòng.

Nếu cần xử lý theo dòng, bạn có thể dùng `String.lines()` sau khi đọc hoặc chuyển sang API đọc streaming. `String.lines()` trả về stream các dòng, không giữ terminator của từng dòng:

~~~java
String content = Files.readString(path, StandardCharsets.UTF_8);

content.lines()
        .filter(line -> !line.isBlank())
        .forEach(System.out::println);
~~~

### 3.2. Tệp rỗng

Nếu tệp tồn tại nhưng không có byte nội dung, `readString` trả về chuỗi rỗng:

~~~java
String content = Files.readString(path);

if (content.isEmpty()) {
    System.out.println("Tệp chưa có nội dung");
}
~~~

Đừng nhầm chuỗi rỗng với `null`: phương thức không trả về null để biểu thị tệp rỗng.

### 3.3. Đọc tệp không tồn tại hoặc không đọc được

Nếu tệp không tồn tại, đường dẫn không trỏ đến một tệp đọc được hoặc có lỗi I/O, phương thức ném ngoại lệ. `NoSuchFileException` là một kiểu `IOException` thường gặp khi đường dẫn không tồn tại.

Có thể xử lý bằng `try/catch`:

~~~java
try {
    String content = Files.readString(path, StandardCharsets.UTF_8);
    System.out.println(content);
} catch (IOException e) {
    System.err.println("Không thể đọc tệp: " + e.getMessage());
}
~~~

Hoặc khai báo `throws IOException` ở phương thức gọi nếu tầng trên có trách nhiệm xử lý lỗi.

## 4. Ghi văn bản bằng writeString

Ví dụ:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class WriteTextDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data", "message.txt");
        Files.createDirectories(path.getParent());

        String content = "Xin chào Java 17" + System.lineSeparator()
                + "Ghi văn bản bằng Files.writeString";

        Files.writeString(path, content, StandardCharsets.UTF_8);

        System.out.println("Đã ghi tệp: " + path.toAbsolutePath());
    }
}
~~~

`System.lineSeparator()` trả về chuỗi phân cách dòng phù hợp với nền tảng. Nếu định dạng tệp quy định bắt buộc LF, bạn có thể ghi `\n` tường minh thay vì dùng line separator của hệ điều hành.

### 4.1. Mặc định writeString tạo tệp hoặc ghi đè nội dung cũ

Khi không truyền `OpenOption`, `writeString` hoạt động với các tùy chọn mặc định tương đương:

- `CREATE`: tạo tệp nếu chưa tồn tại.
- `TRUNCATE_EXISTING`: xóa nội dung cũ của tệp đã tồn tại trước khi ghi.
- `WRITE`: mở tệp để ghi.

Ví dụ:

~~~java
Files.writeString(path, "Nội dung mới", StandardCharsets.UTF_8);
~~~

Nếu tệp đã chứa "Nội dung rất dài từ lần trước", nội dung cũ bị truncate; kết quả là tệp chỉ chứa "Nội dung mới".

Vì vậy, đừng gọi `writeString(path, text)` với giả định rằng nó tự nối nội dung. **Mặc định là ghi thay thế nội dung cũ.**

### 4.2. Chỉ định rõ tùy chọn ghi

Bạn có thể viết rõ các tùy chọn:

~~~java
import static java.nio.file.StandardOpenOption.CREATE;
import static java.nio.file.StandardOpenOption.TRUNCATE_EXISTING;
import static java.nio.file.StandardOpenOption.WRITE;

Files.writeString(
        path,
        content,
        StandardCharsets.UTF_8,
        CREATE,
        TRUNCATE_EXISTING,
        WRITE
);
~~~

Cách này tương đương hành vi mặc định, nhưng làm ý định ghi đè rõ ràng hơn. `StandardOpenOption` thuộc `java.nio.file`.

### 4.3. Nối thêm nội dung bằng APPEND

Nếu muốn thêm văn bản vào cuối tệp mà giữ nội dung cũ, dùng `APPEND`:

~~~java
import java.nio.file.StandardOpenOption;

Files.writeString(
        path,
        "Dòng được thêm sau" + System.lineSeparator(),
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND
);
~~~

- `CREATE` cho phép tạo tệp nếu chưa có.
- `WRITE` mở quyền ghi.
- `APPEND` đặt vị trí ghi ở cuối tệp.

Không thêm `TRUNCATE_EXISTING` khi mục tiêu là nối thêm dữ liệu.

### 4.4. Ghi tệp mới mà không ghi đè tệp đã tồn tại

Nếu muốn tạo tệp mới và coi việc tệp đã tồn tại là lỗi, dùng `CREATE_NEW`:

~~~java
Files.writeString(
        path,
        "Nội dung ban đầu",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE
);
~~~

Nếu tệp đã tồn tại, thao tác thất bại thay vì ghi đè. Đây là lựa chọn phù hợp khi việc thay thế tệp cũ có thể làm mất dữ liệu ngoài ý muốn.

## 5. Mã hóa ký tự và Charset

Tệp lưu byte; `String` trong Java biểu diễn chuỗi ký tự. Khi đọc, Java cần **giải mã byte thành ký tự**; khi ghi, Java cần **mã hóa ký tự thành byte**. Charset quy định phép chuyển đổi đó.

### 5.1. UTF-8 là lựa chọn mặc định của readString/writeString

Có thể đọc và ghi UTF-8 bằng overload không có charset:

~~~java
String text = Files.readString(path);
Files.writeString(path, text);
~~~

Hoặc thể hiện tường minh:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, text, StandardCharsets.UTF_8);
~~~

Với văn bản tiếng Việt và dữ liệu đa ngôn ngữ, UTF-8 thường là lựa chọn phù hợp. Một ký tự Unicode có thể được mã hóa thành một hoặc nhiều byte UTF-8; không nên giả định một ký tự luôn tương ứng một byte.

### 5.2. Đọc tệp dùng charset khác

Nếu một tệp cũ được tạo bằng charset đã biết, truyền đúng charset đó:

~~~java
String content = Files.readString(
        path,
        StandardCharsets.ISO_8859_1
);
~~~

Ví dụ với charset không có hằng trong `StandardCharsets`:

~~~java
import java.nio.charset.Charset;

Charset windows1252 = Charset.forName("windows-1252");
String content = Files.readString(path, windows1252);
~~~

Chỉ chọn charset sau khi biết định dạng nguồn. Không thử ngẫu nhiên nhiều charset rồi chọn kết quả "trông có vẻ đúng", vì nhiều chuỗi byte có thể giải mã thành ký tự hợp lệ nhưng sai nội dung.

### 5.3. Ghi tệp bằng charset cụ thể

~~~java
Files.writeString(
        path,
        "Văn bản cần ghi",
        StandardCharsets.UTF_8
);
~~~

Nếu hệ thống tích hợp yêu cầu một charset khác, hãy chỉ định chính xác:

~~~java
Files.writeString(
        path,
        "Legacy text",
        StandardCharsets.ISO_8859_1
);
~~~

Nếu ký tự trong chuỗi không thể biểu diễn bằng charset được chọn, thao tác có thể thất bại với `IOException`. Không nên chọn charset hẹp như US-ASCII cho nội dung có thể chứa tiếng Việt.

### 5.4. Không nhầm charset của readString với charset mặc định hệ thống

| Cách gọi | Charset |
|---|---|
| `Files.readString(path)` | UTF-8 |
| `Files.writeString(path, text)` | UTF-8 |
| `Files.readString(path, charset)` | Charset được truyền |
| `Files.writeString(path, text, charset)` | Charset được truyền |

Đừng suy luận overload không tham số charset sẽ dùng charset mặc định của máy. Đây là hành vi khác với một số API chuyển byte thành chuỗi như `new String(bytes)` nếu không chỉ định charset.

## 6. Xử lý lỗi khi đọc và ghi

Các phương thức làm việc với tệp có thể gặp lỗi do đường dẫn, quyền truy cập, tệp bị xóa, lỗi thiết bị hoặc dữ liệu không giải mã được.

### 6.1. IOException là checked exception

Cả `readString` và `writeString` khai báo ném `IOException`. Có hai cách xử lý thông dụng:

**Cách 1: khai báo throws**

~~~java
static String load(Path path) throws IOException {
    return Files.readString(path, StandardCharsets.UTF_8);
}
~~~

Cách này phù hợp khi tầng gọi có thể quyết định thông báo lỗi, retry hoặc trả kết quả cho người dùng.

**Cách 2: bắt ngoại lệ tại nơi xử lý**

~~~java
try {
    Files.writeString(path, "Hello", StandardCharsets.UTF_8);
} catch (IOException e) {
    System.err.println("Ghi tệp thất bại: " + e.getMessage());
}
~~~

Không nên bắt `IOException` rồi bỏ qua hoàn toàn nếu việc ghi/đọc thất bại có ảnh hưởng đến tính đúng đắn của chương trình.

### 6.2. Một số ngoại lệ thường gặp

| Ngoại lệ | Tình huống có thể gặp | Hướng xử lý |
|---|---|---|
| `NoSuchFileException` | Tệp không tồn tại khi đọc, hoặc thư mục cha chưa tồn tại khi ghi | Kiểm tra đường dẫn, tạo thư mục cha nếu cần |
| `AccessDeniedException` | Tiến trình không có quyền đọc/ghi | Kiểm tra quyền và tài khoản chạy ứng dụng |
| `MalformedInputException` | Byte không hợp lệ với charset giải mã đã chọn | Xác định đúng charset hoặc xử lý dữ liệu lỗi |
| `FileAlreadyExistsException` | Dùng `CREATE_NEW` nhưng tệp đã tồn tại | Chọn tên khác hoặc xử lý trường hợp trùng |
| `InvalidPathException` | Chuỗi đầu vào không thể tạo thành đường dẫn hợp lệ | Kiểm tra đầu vào trước khi gọi `Path.of` |

`MalformedInputException` là ngoại lệ thuộc nhánh lỗi mã hóa ký tự và cũng là một loại `IOException`. Không nên khắc phục bằng cách đổi charset tùy tiện; hãy xác định encoding thực tế của tệp.

### 6.3. Phân biệt lỗi I/O với lỗi đường dẫn

`Path.of(...)` có thể ném `InvalidPathException` ngay lúc tạo đường dẫn. `Files.readString(...)` hoặc `writeString(...)` có thể ném `IOException` khi thực hiện thao tác trên hệ thống tệp.

Nếu đường dẫn do người dùng cung cấp, hãy xác thực nó theo thư mục gốc ứng dụng được phép truy cập. Không nên ghép trực tiếp một đường dẫn tùy ý từ request vào vị trí lưu trữ mà không kiểm soát phạm vi.

## 7. Đọc và ghi văn bản có nhiều dòng

### 7.1. Ghi nhiều dòng

Có thể tạo chuỗi nhiều dòng bằng text block hoặc nối các dòng:

~~~java
String content = """
        id,name,status
        1,An,ACTIVE
        2,Bình,INACTIVE
        """;

Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

Text block giữ ký tự xuống dòng theo quy tắc của ngôn ngữ. `writeString` ghi chuỗi được truyền; nó không tự thêm dòng mới sau nội dung.

Nếu tạo nội dung động:

~~~java
String content = String.join(
        System.lineSeparator(),
        "id,name,status",
        "1,An,ACTIVE",
        "2,Bình,INACTIVE"
) + System.lineSeparator();

Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

Dòng cuối có ký tự xuống dòng vì ta chủ động nối `System.lineSeparator()`.

### 7.2. Đọc nội dung và xử lý từng dòng

Nếu tệp nhỏ, có thể đọc toàn bộ rồi dùng `lines()`:

~~~java
String content = Files.readString(path, StandardCharsets.UTF_8);

content.lines()
        .map(String::strip)
        .filter(line -> !line.isEmpty())
        .forEach(System.out::println);
~~~

Cách này đơn giản, nhưng toàn bộ tệp vẫn được nạp vào bộ nhớ trước khi xử lý.

### 7.3. Đừng nhầm readString với readAllLines

Hai phương thức trả về kiểu dữ liệu khác nhau:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
~~~

- `readString` trả về một chuỗi duy nhất, giữ ký tự xuống dòng trong chuỗi.
- `readAllLines` trả về danh sách các dòng, không giữ terminator dòng ở cuối từng phần tử.

Nếu cần thao tác văn bản như một khối, `readString` thuận tiện hơn. Nếu cần duyệt các dòng của tệp nhỏ, `readAllLines` có thể phù hợp.

## 8. Khi nào không nên dùng readString/writeString?

`readString` đọc toàn bộ nội dung thành một `String`. Do đó, kích thước tệp và lượng bộ nhớ khả dụng là yếu tố quan trọng.

Nên dùng khi:

- Tệp cấu hình nhỏ hoặc vừa.
- Tệp JSON, XML, CSV nhỏ cần đưa vào parser dạng chuỗi.
- Nội dung template hoặc tài liệu văn bản có kích thước kiểm soát được.
- Bài toán thực sự cần toàn bộ nội dung cùng lúc.

Cân nhắc streaming khi:

- Tệp log rất lớn.
- Tệp dữ liệu có hàng triệu dòng.
- Ứng dụng cần xử lý từng dòng mà không giữ toàn bộ nội dung trong RAM.
- Tệp được sinh hoặc xử lý liên tục.

### 8.1. Đọc streaming với BufferedReader

~~~java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;

    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
~~~

`BufferedReader` cho phép xử lý từng dòng. Khối `try-with-resources` bảo đảm reader được đóng ngay cả khi quá trình xử lý ném ngoại lệ.

### 8.2. Ghi streaming với BufferedWriter

~~~java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedWriter writer =
             Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("id,name");
    writer.newLine();
    writer.write("1,An");
    writer.newLine();
}
~~~

`BufferedWriter` phù hợp khi nội dung được tạo từng phần. Bạn không cần ghép tất cả vào một chuỗi lớn trước khi ghi.

### 8.3. Files.lines và việc đóng Stream

`Files.lines(path)` tạo một `Stream<String>` để đọc các dòng theo kiểu lazy. Stream này giữ tài nguyên tệp mở, vì vậy phải đóng nó, thường bằng `try-with-resources`:

~~~java
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> line.contains("ERROR"))
            .forEach(System.out::println);
}
~~~

Đừng trả stream ra khỏi phương thức sau khi đã đóng hoặc bỏ quên việc đóng stream. Với xử lý dòng tuần tự đơn giản, `BufferedReader` thường dễ kiểm soát hơn.

## 9. Ghi đè, nối thêm và an toàn dữ liệu

Lựa chọn `OpenOption` ảnh hưởng trực tiếp đến nội dung tệp.

| Nhu cầu | Tùy chọn thường dùng |
|---|---|
| Tạo mới hoặc ghi đè toàn bộ | `CREATE, TRUNCATE_EXISTING, WRITE` |
| Nối thêm vào cuối | `CREATE, WRITE, APPEND` |
| Chỉ tạo nếu chưa tồn tại | `CREATE_NEW, WRITE` |

### 9.1. Ghi đè có thể làm mất dữ liệu cũ

Nếu nội dung cũ cần giữ lại, không dùng overload mặc định một cách vô tình. Hãy chọn append hoặc một chiến lược lưu phiên bản phù hợp.

~~~java
Files.writeString(path, "Nội dung thay thế", StandardCharsets.UTF_8);
~~~

Đây là thao tác thay thế nội dung, không phải cập nhật một đoạn trong tệp.

### 9.2. writeString không cam kết thao tác thay thế là atomic

`writeString` không cung cấp cam kết rằng một lần ghi toàn bộ tệp luôn xuất hiện như một thao tác atomic đối với mọi tiến trình khác. Nếu ứng dụng cần tránh để người đọc thấy tệp đích ở trạng thái ghi dở, có thể thiết kế quy trình ghi ra tệp tạm trong cùng filesystem rồi di chuyển bằng `Files.move` với `ATOMIC_MOVE` khi filesystem hỗ trợ. Cần xử lý trường hợp atomic move không được hỗ trợ và xác định chính sách thay thế tệp đích riêng.

Đây là yêu cầu nâng cao; với tệp cấu hình nhỏ không chia sẻ đồng thời, `writeString` thường đủ đơn giản.

## 10. Ví dụ hoàn chỉnh: đọc và cập nhật tệp văn bản

Tạo file **`TextFileWorkflow.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class TextFileWorkflow {

    public static void main(String[] args) throws IOException {
        Path path = Path.of("data", "notes.txt");

        // Tạo thư mục cha nếu cần.
        Files.createDirectories(path.getParent());

        // Ghi mới hoặc thay thế toàn bộ nội dung.
        String initialContent = """
                Java 17
                Files.readString
                Files.writeString
                """;

        Files.writeString(
                path,
                initialContent,
                StandardCharsets.UTF_8
        );

        // Đọc toàn bộ nội dung.
        String loaded = Files.readString(path, StandardCharsets.UTF_8);

        System.out.println("Nội dung hiện tại:");
        System.out.print(loaded);

        // Nối thêm một dòng.
        Files.writeString(
                path,
                "Đã đọc và ghi thành công" + System.lineSeparator(),
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND
        );

        // Đọc lại để thấy nội dung sau khi append.
        String updated = Files.readString(path, StandardCharsets.UTF_8);

        System.out.println("Nội dung sau cập nhật:");
        System.out.print(updated);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 TextFileWorkflow.java
java TextFileWorkflow
~~~

Kết quả minh họa:

~~~text
Nội dung hiện tại:
Java 17
Files.readString
Files.writeString
Nội dung sau cập nhật:
Java 17
Files.readString
Files.writeString
Đã đọc và ghi thành công
~~~

Lần ghi đầu dùng tùy chọn mặc định nên tạo mới hoặc thay thế nội dung. Lần ghi sau truyền `APPEND` nên nội dung mới được nối vào cuối tệp. Cả hai lần đều dùng UTF-8.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `NoSuchFileException` khi ghi | Thư mục cha chưa tồn tại | Gọi `Files.createDirectories(path.getParent())` khi parent khác null |
| Nội dung cũ biến mất sau writeString | Overload mặc định truncate tệp hiện có | Dùng `APPEND` nếu muốn nối |
| Tiếng Việt bị lỗi ký tự | Dùng sai charset so với tệp | Xác định encoding thật và truyền `Charset` phù hợp |
| Tệp không có dòng mới sau khi ghi | `writeString` không tự thêm newline | Thêm `System.lineSeparator()` hoặc `\n` theo định dạng |
| Tệp lớn làm ứng dụng tốn nhiều RAM | `readString` nạp toàn bộ nội dung vào một chuỗi | Dùng `BufferedReader` hoặc `Files.lines` và đóng tài nguyên |
| `MalformedInputException` | Byte không hợp lệ theo charset đang dùng | Xác minh encoding, không đổi charset ngẫu nhiên |
| Gọi `getParent()` rồi truyền null vào createDirectories | Đường dẫn chỉ có tên tệp, không có parent tường minh | Kiểm tra parent khác null trước |
| Gọi `readString` nhưng tệp không tồn tại | Không có dữ liệu để đọc | Kiểm tra tồn tại hoặc xử lý `NoSuchFileException` |
| Dùng `CREATE_NEW` cho tệp đã có | Tùy chọn yêu cầu tệp chưa tồn tại | Chọn tên khác hoặc xử lý trường hợp đã tồn tại |

## 12. Bài tập thực hành

### Bài 1: Ghi và đọc lại một tệp UTF-8

Tạo chương trình ghi nội dung tiếng Việt "Xin chào Java 17" vào `hello.txt`, sau đó đọc lại và in ra màn hình.

**Đáp án gợi ý:**

~~~java
Path path = Path.of("hello.txt");

Files.writeString(path, "Xin chào Java 17", StandardCharsets.UTF_8);

String content = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(content);
~~~

### Bài 2: Vì sao dữ liệu cũ bị mất?

Cho:

~~~java
Files.writeString(path, "Dòng thứ nhất", StandardCharsets.UTF_8);
Files.writeString(path, "Dòng thứ hai", StandardCharsets.UTF_8);
~~~

Sau hai lệnh, nội dung tệp là gì?

**Đáp án:** Chỉ còn "Dòng thứ hai" vì lần ghi thứ hai dùng tùy chọn mặc định `TRUNCATE_EXISTING`. Muốn giữ cả hai dòng, hãy dùng `APPEND` ở lần ghi thứ hai.

### Bài 3: Nối thêm nội dung

Viết lệnh nối thêm "Dòng mới" vào cuối tệp, tạo tệp nếu chưa tồn tại.

**Đáp án:**

~~~java
Files.writeString(
        path,
        "Dòng mới" + System.lineSeparator(),
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND
);
~~~

### Bài 4: Xử lý thư mục chưa tồn tại

Tại sao lệnh ghi vào `data/logs/app.txt` có thể thất bại nếu `data/logs` chưa có?

**Đáp án:** `writeString` có thể tạo tệp đích nhưng không tạo các thư mục cha. Hãy gọi:

~~~java
Path path = Path.of("data", "logs", "app.txt");
Files.createDirectories(path.getParent());
~~~

### Bài 5: Chọn charset

Một tệp được xác định là UTF-8. Nên dùng overload nào?

**Đáp án:** Có thể dùng `Files.readString(path)` vì overload mặc định dùng UTF-8, hoặc viết tường minh `Files.readString(path, StandardCharsets.UTF_8)` để thể hiện hợp đồng encoding.

### Bài 6: Khi nào cần BufferedReader?

Một tệp log có dung lượng vài GB, chương trình chỉ cần đếm số dòng chứa "ERROR". Có nên gọi `readString` không?

**Đáp án:** Không phù hợp vì `readString` nạp toàn bộ nội dung vào một chuỗi. Dùng `Files.newBufferedReader` để duyệt từng dòng và tăng bộ đếm, đóng reader bằng try-with-resources.

## 13. Ghi nhớ

Khi làm việc với tệp văn bản trong Java 17:

1. Dùng `Path.of(...)` để tạo đường dẫn.
2. Dùng `Files.readString(path)` để đọc toàn bộ nội dung thành một chuỗi.
3. Dùng `Files.writeString(path, text)` để ghi UTF-8; mặc định là tạo mới hoặc truncate nội dung cũ.
4. Truyền `StandardCharsets.UTF_8` hoặc charset cụ thể khi cần thể hiện rõ encoding.
5. Dùng `StandardOpenOption.APPEND` cùng `CREATE` và `WRITE` khi muốn nối thêm.
6. Tạo thư mục cha trước khi ghi nếu cần.
7. Xử lý `IOException` và các lỗi đường dẫn phù hợp.
8. Chuyển sang API streaming khi tệp lớn hoặc cần xử lý từng dòng.

`readString` và `writeString` là lựa chọn gọn cho văn bản có kích thước kiểm soát được. Việc chọn đúng charset và tùy chọn mở tệp mới là yếu tố quyết định dữ liệu có được đọc/ghi đúng như mong đợi hay không.

## 14. Tài liệu tham khảo

- [Oracle Java SE 17 — Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): đặc tả `readString`, `writeString`, tùy chọn mở và các API đọc/ghi streaming.
- [Oracle Java SE 17 — Path API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): tạo và thao tác đường dẫn.
- [Oracle Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset được Java đảm bảo có sẵn.
- [Oracle Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE`, `TRUNCATE_EXISTING`, `WRITE`, `APPEND` và `CREATE_NEW`.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): bối cảnh charset mặc định của Java; lưu ý overload `readString`/`writeString` không truyền charset đã quy định UTF-8 từ Java 11.

