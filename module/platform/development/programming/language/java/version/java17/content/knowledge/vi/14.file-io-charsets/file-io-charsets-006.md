# Đọc dòng bằng Files.lines và duyệt cây thư mục bằng Files.walk trong Java 17

Khi làm việc với tệp trong Java, có hai nhu cầu xuất hiện thường xuyên: **đọc nội dung theo từng dòng** và **tìm các tệp nằm trong một thư mục cùng các thư mục con**. Từ Java 8, lớp **java.nio.file.Files** cung cấp **Files.lines()** và **Files.walk()** để thực hiện hai việc đó bằng Stream API. Cả hai API vẫn được hỗ trợ và sử dụng bình thường trong Java 17.

**Files.lines()** trả về một **Stream<String>** để xử lý từng dòng của tệp. **Files.walk()** trả về một **Stream<Path>** để duyệt các đường dẫn trong cây thư mục. Vì cả hai đều trả về stream có thể giữ tài nguyên I/O mở, **đóng stream đúng cách bằng try-with-resources** là phần quan trọng của cách sử dụng.

Bài học này trình bày cách đọc tệp lớn mà không nạp toàn bộ nội dung vào bộ nhớ, chọn charset, xử lý lỗi I/O, duyệt thư mục theo độ sâu, lọc tệp, xử lý symbolic link và áp dụng các API vào chương trình thực tế.

## 1. Hai API giải quyết hai bài toán nào?

| API | Đầu vào | Kết quả | Mục đích |
| --- | --- | --- | --- |
| **Files.lines(path)** | Đường dẫn tới một tệp | **Stream<String>** | Đọc từng dòng văn bản. |
| **Files.walk(path)** | Đường dẫn bắt đầu của cây thư mục hoặc một tệp | **Stream<Path>** | Duyệt đường dẫn bắt đầu và các mục nằm bên dưới. |

Ví dụ, nếu có cây thư mục:

~~~text
project/
├── README.md
├── config/
│   └── app.properties
└── logs/
    ├── app.log
    └── archive/
        └── old.log
~~~

**Files.lines(Path.of("project/logs/app.log"))** đọc các dòng trong một tệp log cụ thể. **Files.walk(Path.of("project"))** duyệt project, các thư mục con và các tệp được tìm thấy trong cây đó.

Hai API trả về stream nên có thể kết hợp với các thao tác như filter, map, flatMap, forEach, count hoặc collect. Việc đọc/duyệt được thực hiện theo kiểu lazy: các phần tử thường được lấy khi stream được tiêu thụ, thay vì bắt buộc tải toàn bộ kết quả ngay lúc tạo stream.

## 2. Đọc từng dòng bằng Files.lines()

### 2.1. Cú pháp cơ bản

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("data", "messages.txt");

try (Stream<String> lines = Files.lines(path)) {
    lines.forEach(System.out::println);
} catch (IOException e) {
    System.err.println("Không thể mở tệp: " + e.getMessage());
}
~~~

Giải thích:

- Path.of(...) tạo đường dẫn tới tệp.
- Files.lines(path) mở tệp và trả về Stream<String>.
- Mỗi phần tử của stream là nội dung của một dòng, không chứa ký tự kết thúc dòng.
- forEach là thao tác terminal, tiêu thụ các dòng để in ra.
- try-with-resources gọi close() trên stream khi kết thúc, kể cả khi phần thân gặp lỗi.

**Không bỏ try-with-resources chỉ vì đã gọi forEach.** Kết thúc một thao tác terminal không tự động thay thế trách nhiệm đóng stream. Stream giữ tài nguyên của tệp cho tới khi được đóng.

### 2.2. Files.lines() là lazy

Đoạn mã:

~~~java
Stream<String> lines = Files.lines(path);
~~~

không có nghĩa mọi dòng đã được đọc và lưu vào một danh sách. Stream cung cấp các dòng khi có thao tác tiêu thụ, chẳng hạn:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long count = lines.count();
    System.out.println("Số dòng: " + count);
}
~~~

Điều này hữu ích với tệp lớn vì chương trình không cần giữ toàn bộ danh sách dòng trong heap. Tuy nhiên, lazy không có nghĩa là không dùng bộ nhớ: thư viện vẫn cần buffer cho việc đọc, và các thao tác downstream có thể tự tích lũy dữ liệu. Ví dụ collect(Collectors.toList()) vẫn tạo một danh sách chứa toàn bộ dòng.

### 2.3. Đọc có điều kiện

Stream cho phép lọc và biến đổi dữ liệu ngay trong quá trình đọc:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    lines.filter(line -> !line.isBlank())
            .map(String::strip)
            .forEach(System.out::println);
}
~~~

Trong ví dụ:

- filter loại bỏ dòng rỗng hoặc chỉ có khoảng trắng.
- map(String::strip) bỏ khoảng trắng đầu và cuối của từng dòng.
- forEach xử lý các dòng còn lại.

Lưu ý strip() làm thay đổi chuỗi được xử lý. Nếu khoảng trắng đầu/cuối có ý nghĩa, ví dụ trong tệp dữ liệu fixed-width, không nên loại bỏ nó.

## 3. Charset và cách diễn giải văn bản

### 3.1. Chọn charset tường minh

Files.lines(Path) dùng UTF-8. Khi biết charset của tệp, có thể truyền rõ ràng:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
}
~~~

Các charset thường gặp:

| Charset | Khi nào gặp |
| --- | --- |
| StandardCharsets.UTF_8 | Văn bản UTF-8, lựa chọn phổ biến cho tệp mới và trao đổi dữ liệu hiện đại. |
| StandardCharsets.UTF_16 | Dữ liệu được mã hóa theo UTF-16. |
| StandardCharsets.ISO_8859_1 | Một số định dạng cũ hoặc giao thức quy định Latin-1. |
| Charset.forName("...") | Khi phải hỗ trợ một charset cụ thể theo hợp đồng của dữ liệu. |

Ví dụ với charset được cấu hình:

~~~java
Charset charset = Charset.forName("windows-1252");
try (Stream<String> lines = Files.lines(path, charset)) {
    lines.forEach(System.out::println);
}
~~~

Chỉ chọn charset khi biết dữ liệu thực sự được mã hóa theo charset đó. Đọc một tệp UTF-8 bằng Windows-1252 có thể không báo lỗi nhưng tạo ra ký tự sai (mojibake). Ngược lại, charset không phù hợp cũng có thể khiến decoder báo lỗi với một số dữ liệu.

### 3.2. Đừng phụ thuộc vào charset mặc định của máy

Khi xử lý dữ liệu có tiếng Việt hoặc được trao đổi giữa các hệ thống, hãy thống nhất encoding và nêu rõ trong code:

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    // Xử lý dữ liệu UTF-8.
}
~~~

Điều này giúp hành vi đọc tệp rõ ràng giữa máy developer, CI và production. Đặc biệt với dữ liệu cũ, hãy kiểm tra nguồn tạo tệp thay vì đoán charset từ nội dung nhìn thấy.

### 3.3. BOM ở đầu tệp

Một số tệp UTF-8 có byte order mark (BOM) ở đầu. UTF-8 không cần BOM để xác định byte order; nếu tệp chứa BOM, việc giải mã thông thường có thể đưa ký tự U+FEFF vào đầu dòng đầu tiên. Nếu định dạng tệp của bạn quy định bỏ BOM, hãy xử lý nó tường minh, chẳng hạn chỉ loại bỏ ký tự này ở đầu dòng đầu tiên:

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.map(line -> line.startsWith("\uFEFF")
                    ? line.substring(1)
                    : line)
            .forEach(System.out::println);
}
~~~

Không nên xóa U+FEFF ở mọi vị trí một cách tùy tiện nếu ký tự đó có thể là dữ liệu thực.

## 4. Dòng trống, dấu kết thúc dòng và tệp rỗng

Files.lines() trả về nội dung dòng, không bao gồm ký tự kết thúc dòng. Các kiểu line terminator phổ biến LF, CR và CRLF đều được xử lý như ranh giới giữa các dòng.

Ví dụ tệp có nội dung:

~~~text
alpha
beta
gamma
~~~

Stream chứa ba phần tử:

~~~text
alpha
beta
gamma
~~~

Không có ký tự xuống dòng ở cuối mỗi phần tử. Nếu cần tạo lại nội dung nhiều dòng, bạn phải chọn cách nối dòng rõ ràng.

### 4.1. Tệp rỗng và dòng rỗng

- Tệp rỗng tạo stream không có phần tử; count() trả 0.
- Tệp có một dòng chứa văn bản rỗng do chỉ có một line terminator có thể tạo một phần tử chuỗi rỗng.
- Dòng trống ở giữa tệp được trả về dưới dạng chuỗi rỗng; isBlank() cũng trả true với dòng chỉ có khoảng trắng.
- Tệp kết thúc bằng line terminator không tạo thêm một dòng giả ở sau terminator cuối.
- Dòng cuối không có line terminator vẫn được trả về bình thường.

Có thể kiểm tra bằng một ví dụ tự tạo tệp:

~~~java
import java.nio.charset.StandardCharsets;

Path path = Path.of("sample-lines.txt");
Files.writeString(path, "first\n\nthird", StandardCharsets.UTF_8);

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(line -> System.out.println("[" + line + "]"));
}
~~~

Kết quả:

~~~text
[first]
[]
[third]
~~~

Nếu cần biết dòng nào là dòng đầu/cuối hoặc số thứ tự dòng, có thể dùng một bộ đếm cho thao tác tuần tự, hoặc tạo một phép đánh số riêng. Không nên giả định Stream<String> tự cung cấp số dòng.

## 5. Xử lý lỗi khi đọc stream

Files.lines() có thể gặp lỗi ở hai thời điểm:

1. **Khi mở tệp:** phương thức có thể ném IOException (ví dụ tệp không tồn tại hoặc không thể mở).
2. **Trong lúc tiêu thụ stream:** lỗi đọc phát sinh sau đó được bọc trong UncheckedIOException và ném từ thao tác stream đang khiến việc đọc xảy ra.

Ví dụ xử lý cả hai:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("data", "events.log");

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> line.contains("ERROR"))
            .forEach(System.out::println);
} catch (UncheckedIOException e) {
    System.err.println("Lỗi khi đang đọc: " + e.getCause());
} catch (IOException e) {
    System.err.println("Lỗi khi mở/đóng tệp: " + e.getMessage());
}
~~~

UncheckedIOException là runtime exception, có getCause() để truy cập IOException gốc. try-with-resources vẫn đóng stream khi có exception. Trong code production, hãy quyết định rõ có tiếp tục xử lý, báo lỗi, retry hay hủy tác vụ; không nên nuốt lỗi I/O rồi xem dữ liệu đọc được là hoàn chỉnh.

### 5.1. Vì sao không dùng forEach ngoài try-with-resources?

Đoạn mã dưới đây có thể đọc được, nhưng không thể hiện việc đóng stream:

~~~java
Files.lines(path).forEach(System.out::println);
~~~

Nên viết:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    lines.forEach(System.out::println);
}
~~~

Stream có thể giữ file descriptor và các tài nguyên hệ thống khác. Nếu không đóng, chương trình đọc nhiều tệp trong thời gian dài có thể giữ quá nhiều file handle.

### 5.2. Tránh giữ stream qua nhiều tầng gọi

Không nên trả Stream<String> từ một phương thức đã mở tệp mà không làm rõ ai chịu trách nhiệm đóng stream. Nếu buộc phải trả stream, hợp đồng API phải nói rõ caller cần đóng. Một lựa chọn đơn giản hơn là xử lý trong phạm vi phương thức:

~~~java
static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
~~~

Phương thức này trả kết quả đã tính và tự quản lý vòng đời stream.

## 6. Ví dụ đọc tệp log lớn theo dòng

Không cần nạp toàn bộ log vào List<String> nếu chỉ muốn đếm hoặc lọc:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class LogReader {
    public static void main(String[] args) throws IOException {
        Path logFile = Path.of("logs", "application.log");

        try (Stream<String> lines =
                Files.lines(logFile, StandardCharsets.UTF_8)) {
            long errorCount = lines
                    .filter(line -> line.contains("ERROR"))
                    .count();
            System.out.println("Tổng dòng ERROR: " + errorCount);
        } catch (UncheckedIOException e) {
            throw new IOException("Không đọc hết được log", e.getCause());
        }
    }
}
~~~

count() tiêu thụ stream một lần. Sau terminal operation, không dùng lại stream đã tiêu thụ. Nếu cần xử lý mỗi dòng ngay khi đọc, dùng forEach; nếu cần kết quả tổng hợp, chọn collector hoặc phép reduction phù hợp.

## 7. Duyệt cây thư mục bằng Files.walk()

### 7.1. Cú pháp cơ bản

Files.walk(start) trả về một Stream<Path> gồm đường dẫn bắt đầu và các mục trong cây thư mục bên dưới:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path root = Path.of("project");

try (Stream<Path> paths = Files.walk(root)) {
    paths.forEach(System.out::println);
} catch (IOException e) {
    System.err.println("Không thể duyệt thư mục: " + e.getMessage());
}
~~~

Điểm cần nhớ:

- Đường dẫn root cũng là một phần tử của stream.
- Nếu root là thư mục, các mục bên dưới được duyệt theo chiều sâu (depth-first).
- Nếu root là một tệp, stream có thể chỉ chứa chính đường dẫn đó.
- Mặc định, Files.walk **không đi theo symbolic link**.
- Stream phải được đóng bằng try-with-resources.

Thứ tự giữa các mục cùng cấp không được bảo đảm theo một thứ tự tên cụ thể. Nếu kết quả cần ổn định, hãy sort:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.map(Path::toString)
            .sorted()
            .forEach(System.out::println);
}
~~~

Việc sort cần giữ dữ liệu hoặc thực hiện sắp xếp trước khi in; với cây rất lớn, điều này có thể tăng đáng kể bộ nhớ sử dụng.

### 7.2. Chỉ lấy tệp thường

Thông thường, ta không muốn in thư mục, chỉ muốn lấy file:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

Files.isRegularFile(path) kiểm tra đường dẫn có trỏ tới tệp thường hay không. Mặc định phép kiểm tra này theo symbolic link; nếu đường dẫn là symlink tới một tệp thường, nó có thể trả true.

Nếu muốn chỉ nhận mục là tệp thường **mà bản thân đường dẫn không phải symlink**, dùng LinkOption.NOFOLLOW_LINKS:

~~~java
import java.nio.file.LinkOption;

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(path ->
                    Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
            .forEach(System.out::println);
}
~~~

### 7.3. Lọc theo phần mở rộng

Ví dụ tìm các tệp .java:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .filter(path -> path.getFileName().toString().endsWith(".java"))
            .forEach(System.out::println);
}
~~~

Phép endsWith(".java") phân biệt chữ hoa/thường. Nếu hệ thống cần hỗ trợ cả .JAVA, hãy chuẩn hóa phần tên theo locale phù hợp hoặc so sánh không phân biệt hoa/thường:

~~~java
.filter(path -> path.getFileName().toString()
        .toLowerCase(Locale.ROOT).endsWith(".java"))
~~~

Không nên gọi toLowerCase() theo locale mặc định cho tên định danh kỹ thuật nếu cần kết quả nhất quán giữa máy.

### 7.4. Tìm tệp theo tên

~~~java
String expectedName = "application.properties";

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .filter(path -> path.getFileName() != null)
            .filter(path -> path.getFileName().toString()
                    .equals(expectedName))
            .forEach(System.out::println);
}
~~~

getFileName() có thể trả về null trong một số đường dẫn gốc đặc biệt, vì vậy kiểm tra null trước khi chuyển thành chuỗi giúp ví dụ tổng quát hơn.

## 8. Giới hạn độ sâu với Files.walk(start, maxDepth, ...)

Overload nhận maxDepth cho phép giới hạn mức đi sâu:

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.forEach(System.out::println);
}
~~~

Độ sâu được tính từ start:

~~~text
root/                    depth 0
├── README.md            depth 1
├── config/              depth 1
│   └── app.properties   depth 2
└── logs/                depth 1
    └── app.log          depth 2
~~~

Với maxDepth = 2, các mục tới độ sâu 2 được đưa vào stream; các thư mục ở mức đó không được duyệt sâu hơn nữa.

| maxDepth | Phạm vi |
| --- | --- |
| 0 | Chỉ đường dẫn bắt đầu. |
| 1 | Đường dẫn bắt đầu và các mục trực tiếp bên dưới. |
| 2 | Thêm một cấp con nữa. |
| Integer.MAX_VALUE | Giới hạn thực tế lớn nhất được API cho phép; overload walk(start) dùng mức sâu tối đa này. |

maxDepth không phải số lượng tệp. Nó giới hạn **số cấp thư mục** được duyệt. Nếu chỉ muốn một số lượng kết quả tối đa, có thể dùng limit(n) nhưng cần nhớ rằng traversal có thể dừng trước khi đã duyệt hết cây:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .limit(20)
            .forEach(System.out::println);
}
~~~

## 9. Symbolic link và FileVisitOption.FOLLOW_LINKS

Mặc định, Files.walk không đi theo symbolic link. Một symlink tới thư mục sẽ xuất hiện như một mục đường dẫn, nhưng cây thư mục ở đích liên kết không được duyệt thông qua liên kết đó.

Nếu thực sự cần đi theo symlink, truyền FileVisitOption.FOLLOW_LINKS:

~~~java
import java.nio.file.FileVisitOption;

try (Stream<Path> paths = Files.walk(
        root,
        Integer.MAX_VALUE,
        FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
}
~~~

### 9.1. Rủi ro vòng lặp liên kết

Symlink có thể tạo vòng lặp:

~~~text
root/
└── child/
    └── back-to-root -> ../..
~~~

Nếu đi theo liên kết, traversal có thể gặp lại thư mục đã đi qua. Java phát hiện chu trình liên kết trong quá trình theo dõi và có thể báo FileSystemLoopException. Với Files.walk, lỗi I/O phát sinh trong lúc duyệt stream được bọc trong UncheckedIOException.

Chỉ bật FOLLOW_LINKS khi có yêu cầu rõ ràng. Nếu không cần theo symlink, giữ mặc định giúp tránh duyệt nhầm ra ngoài cây thư mục dự kiến hoặc gặp vòng lặp.

### 9.2. Kiểm tra symlink tường minh

Nếu muốn loại mọi symlink khỏi kết quả:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(path -> !Files.isSymbolicLink(path))
            .filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

Files.isSymbolicLink(path) kiểm tra chính mục đường dẫn. Nếu ứng dụng cần phân biệt symlink, junction hoặc reparse point theo đặc thù hệ điều hành, hãy kiểm tra hành vi của filesystem provider đang sử dụng.

## 10. Lỗi I/O khi duyệt cây thư mục

Tương tự Files.lines, Files.walk có thể ném IOException khi mở traversal và bọc lỗi I/O phát sinh trong quá trình tiêu thụ stream bằng UncheckedIOException.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path root = Path.of("data");

try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
            .forEach(System.out::println);
} catch (UncheckedIOException e) {
    System.err.println("Lỗi trong khi duyệt cây: " + e.getCause());
} catch (IOException e) {
    System.err.println("Không thể bắt đầu/đóng traversal: " + e.getMessage());
}
~~~

Một số nguyên nhân:

- thư mục không tồn tại;
- tài khoản chạy chương trình không có quyền truy cập;
- một mục bị xóa hoặc đổi tên trong khi đang duyệt;
- lỗi filesystem hoặc thiết bị lưu trữ;
- vòng lặp symbolic link khi bật FOLLOW_LINKS.

Files.isRegularFile() và một số hàm kiểm tra thuộc tính trả false nếu không thể xác định chắc chắn loại tệp; chúng không thay thế việc xử lý lỗi của traversal. Nếu ứng dụng cần báo cáo chính xác từng lỗi truy cập và tiếp tục duyệt phần còn lại, Files.walkFileTree() với FileVisitor có thể phù hợp hơn.

### 10.1. Cây thư mục có thể thay đổi trong lúc duyệt

Files.walk không tạo snapshot bất biến của filesystem. Nếu tệp hoặc thư mục được thêm, xóa hay đổi tên khi stream đang chạy, việc thay đổi có được quan sát hay không phụ thuộc vào filesystem provider và thời điểm duyệt.

Nếu cần kết quả nhất quán theo một trạng thái cụ thể, hãy phối hợp khóa/quy trình snapshot ở tầng ứng dụng hoặc làm việc trên một bản sao ổn định. Đừng giả định stream là ảnh chụp nguyên tử của cả cây.

## 11. Kết hợp Files.walk() với Files.lines()

Một tình huống phổ biến là tìm tất cả log trong một thư mục, sau đó đọc từng tệp và đếm số dòng chứa từ khóa.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class SearchLogs {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("logs");
        String keyword = "ERROR";

        try (Stream<Path> files = Files.walk(root)) {
            files.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString()
                            .endsWith(".log"))
                    .forEach(path -> {
                        try (Stream<String> lines =
                                Files.lines(path, StandardCharsets.UTF_8)) {
                            long count = lines
                                    .filter(line -> line.contains(keyword))
                                    .count();
                            System.out.println(path + ": " + count);
                        } catch (IOException | UncheckedIOException e) {
                            System.err.println("Không đọc được "
                                    + path + ": " + e.getMessage());
                        }
                    });
        } catch (UncheckedIOException e) {
            throw new IOException("Lỗi khi duyệt thư mục log",
                    e.getCause());
        }
    }
}
~~~

Có hai stream độc lập nên có hai phạm vi đóng tài nguyên:

1. files giữ tài nguyên traversal của Files.walk.
2. Mỗi lines giữ tệp log đang đọc và được đóng sau khi đếm xong.

Không được đóng stream traversal trước khi xử lý xong các đường dẫn. Cũng không nên thu thập tất cả đường dẫn và tất cả nội dung file vào bộ nhớ nếu chỉ cần xử lý từng tệp một.

## 12. Dùng Files.walk để thống kê cây thư mục

Ví dụ đếm số tệp thường theo phần mở rộng:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Stream;

public class ExtensionReport {
    public static void main(String[] args) throws IOException {
        Path root = Path.of("project");
        Map<String, Long> counts = new TreeMap<>();

        try (Stream<Path> paths = Files.walk(root)) {
            paths.filter(Files::isRegularFile)
                    .forEach(path -> {
                        Path name = path.getFileName();
                        String fileName = name == null
                                ? ""
                                : name.toString();
                        int dot = fileName.lastIndexOf('.');
                        String extension = dot >= 0
                                ? fileName.substring(dot).toLowerCase(Locale.ROOT)
                                : "(no extension)";
                        counts.merge(extension, 1L, Long::sum);
                    });
        }

        counts.forEach((extension, count) ->
                System.out.println(extension + ": " + count));
    }
}
~~~

Ví dụ dùng TreeMap để báo cáo theo thứ tự khóa. Chuẩn hóa extension với Locale.ROOT giúp kết quả không phụ thuộc locale mặc định của máy.

## 13. Khi nào dùng Files.walkFileTree() thay vì Files.walk()?

Files.walk() phù hợp khi muốn xử lý cây thư mục bằng các phép biến đổi stream. Nhưng nếu cần kiểm soát sâu quá trình duyệt, API Files.walkFileTree() với FileVisitor có thể thích hợp hơn:

| Nhu cầu | API nên cân nhắc |
| --- | --- |
| Lấy danh sách đường dẫn rồi lọc/map/count | Files.walk() |
| Đọc một tệp theo từng dòng | Files.lines() |
| Bỏ qua hẳn một thư mục con (prune) | Files.walkFileTree() và SKIP_SUBTREE |
| Xử lý riêng trước/sau khi vào thư mục | FileVisitor.preVisitDirectory / postVisitDirectory |
| Xử lý lỗi cho từng tệp/thư mục và quyết định tiếp tục | FileVisitor.visitFileFailed |
| Sao chép, xóa hoặc thao tác sâu theo sự kiện traversal | Files.walkFileTree() thường phù hợp hơn |

Một điểm quan trọng: dùng Files.walk(root).filter(...) chỉ lọc **những phần tử được đưa vào stream**. Nó không ngăn Files.walk đi vào thư mục con đã bị lọc. Nếu muốn loại bỏ cả một subtree để tiết kiệm traversal, dùng walkFileTree và trả FileVisitResult.SKIP_SUBTREE tại thư mục cần bỏ qua.

## 14. Các lưu ý về hiệu năng và tài nguyên

### 14.1. Đóng stream ngay khi xong

Files.lines và Files.walk đều phải được đóng. Luôn đặt chúng trong try-with-resources, kể cả khi pipeline có filter, map, count hay forEach.

### 14.2. Không thu thập toàn bộ dữ liệu nếu không cần

Với tệp rất lớn:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    lines.filter(line -> line.contains("WARN"))
            .count();
}
~~~

thường dùng ít bộ nhớ hơn:

~~~java
List<String> allLines = Files.readAllLines(path);
long count = allLines.stream()
        .filter(line -> line.contains("WARN"))
        .count();
~~~

readAllLines tiện cho tệp nhỏ và khi cần truy cập lặp lại toàn bộ nội dung; nó đọc toàn bộ các dòng thành một danh sách, nên không phù hợp với tệp lớn nếu bộ nhớ bị giới hạn.

### 14.3. Cẩn thận với parallel()

Stream từ Files.lines hoặc Files.walk có thể được chuyển sang parallel stream, nhưng không nên thêm parallel() chỉ vì xử lý nhiều dữ liệu. Đọc filesystem thường chịu ảnh hưởng I/O, filesystem provider, buffer và thứ tự xử lý. Parallel downstream cũng có thể làm thứ tự in/log không ổn định hoặc tạo contention ở accumulator dùng chung.

Hãy đo bằng workload thực tế. Nếu chuyển sang xử lý song song, đảm bảo mỗi tác vụ không đóng hoặc tiêu thụ cùng một stream lồng nhau sai vòng đời; mỗi tệp phải có phạm vi mở/đóng riêng.

### 14.4. Không dựa vào thứ tự duyệt mặc định

Files.walk duyệt theo chiều sâu nhưng không hứa thứ tự tên tệp giữa các mục cùng cấp. Nếu thuật toán cần thứ tự xác định, sort kết quả hoặc sắp xếp theo khóa nghiệp vụ. Với cây rất lớn, sắp xếp toàn bộ kết quả có thể tốn bộ nhớ.

### 14.5. Đường dẫn tương đối và thư mục làm việc

Path.of("data") tạo đường dẫn tương đối theo thư mục làm việc hiện tại của tiến trình, không nhất thiết là thư mục chứa file .java. Khi chạy từ IDE, Gradle, service hoặc container, working directory có thể khác nhau.

Có thể in đường dẫn tuyệt đối để chẩn đoán:

~~~java
Path root = Path.of("data");
System.out.println(root.toAbsolutePath().normalize());
~~~

normalize() loại bỏ các thành phần dấu chấm và dấu chấm đôi theo cú pháp đường dẫn; nó không xác minh sự tồn tại hoặc truy cập filesystem. toRealPath() mới truy cập filesystem và có thể ném IOException.

## 15. Chương trình hoàn chỉnh: tìm kiếm từ khóa trong cây log

Tạo tệp LogTreeSearch.java:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class LogTreeSearch {
    public static void main(String[] args) throws IOException {
        Path root = Path.of(args.length > 0 ? args[0] : "logs");
        String keyword = args.length > 1 ? args[1] : "ERROR";
        long totalMatches = 0;

        try (Stream<Path> paths = Files.walk(root, 10)) {
            var iterator = paths.iterator();
            while (iterator.hasNext()) {
                Path path = iterator.next();
                if (!Files.isRegularFile(path)
                        || !path.getFileName().toString().endsWith(".log")) {
                    continue;
                }

                try (Stream<String> lines =
                        Files.lines(path, StandardCharsets.UTF_8)) {
                    long matches = lines
                            .filter(line -> line.contains(keyword))
                            .count();
                    totalMatches += matches;
                    System.out.println(path + ": " + matches);
                } catch (IOException | UncheckedIOException e) {
                    System.err.println("Bỏ qua tệp " + path
                            + " vì lỗi đọc: " + e.getMessage());
                }
            }
        } catch (UncheckedIOException e) {
            throw new IOException("Lỗi khi duyệt cây thư mục",
                    e.getCause());
        }

        System.out.println("Tổng số dòng khớp: " + totalMatches);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LogTreeSearch.java
java LogTreeSearch ./logs ERROR
~~~

Chương trình:

1. Duyệt cây logs tối đa 10 cấp tính từ thư mục gốc.
2. Chỉ chọn tệp thường có tên kết thúc bằng .log.
3. Đọc từng tệp theo UTF-8 bằng Files.lines.
4. Đếm số dòng có chứa từ khóa.
5. Đóng stream đọc tệp sau mỗi lần scan và đóng stream duyệt cây khi hoàn tất.

Ví dụ dùng iterator để xử lý từng đường dẫn theo thứ tự tuần tự và cộng tổng bằng biến cục bộ. Cách này cũng làm rõ rằng chỉ một tệp log được mở trong mỗi lượt. Với ứng dụng lớn hơn, có thể tách hàm xử lý từng tệp để dễ kiểm thử.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Tệp bị khóa hoặc chương trình mở quá nhiều file | Stream từ Files.lines không được đóng. | Dùng try-with-resources cho mọi stream đọc tệp. |
| Tên tiếng Việt hiển thị sai | Charset dùng để giải mã không khớp encoding của tệp. | Xác định encoding và truyền StandardCharsets.UTF_8 hoặc charset phù hợp. |
| Không thấy dòng cuối | Có thể đang giả định file phải kết thúc bằng line terminator hoặc xử lý stream chưa được tiêu thụ. | Dòng cuối không cần line terminator; kiểm tra terminal operation và dữ liệu nguồn. |
| Files.lines ném NoSuchFileException | Đường dẫn không tồn tại hoặc working directory khác dự kiến. | In toAbsolutePath(), kiểm tra đường dẫn và quyền truy cập. |
| Lỗi đọc xuất hiện trong forEach thay vì ở dòng gọi Files.lines | Lỗi I/O xảy ra khi stream được tiêu thụ, được bọc trong UncheckedIOException. | Bắt UncheckedIOException quanh pipeline. |
| Files.walk trả cả thư mục và tệp | Stream bao gồm đường dẫn gốc và các mục con. | Lọc bằng Files.isRegularFile. |
| Symlink không được duyệt vào thư mục đích | Files.walk mặc định không theo symbolic link. | Chỉ truyền FOLLOW_LINKS nếu thực sự cần. |
| Duyệt cây lặp hoặc lỗi FileSystemLoopException | Theo symlink tạo vòng lặp. | Giữ mặc định không follow hoặc xử lý lỗi chu trình. |
| maxDepth = 1 không lấy file trong thư mục con | Độ sâu bắt đầu từ root là 0; mục trực tiếp là 1. | Tăng maxDepth theo số cấp cần duyệt. |
| filter bỏ thư mục nhưng vẫn thấy nội dung sâu bên dưới | filter chỉ lọc kết quả, không prune traversal. | Dùng walkFileTree nếu cần SKIP_SUBTREE. |
| Kết quả duyệt không theo thứ tự tên | Filesystem provider không đảm bảo thứ tự anh em. | Sort khi cần thứ tự xác định. |
| readAllLines tốn nhiều bộ nhớ | Toàn bộ dòng được nạp vào danh sách. | Dùng Files.lines để xử lý tuần tự theo stream. |

## 17. Bài tập tự luyện

### Bài 1 — Đếm dòng không rỗng

Viết phương thức nhận Path và trả về số dòng không rỗng bằng Files.lines. Đảm bảo stream luôn được đóng và phương thức xử lý được IOException.

Gợi ý:

~~~java
static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
~~~

### Bài 2 — Tìm tất cả tệp .java

Viết chương trình nhận một thư mục gốc, dùng Files.walk để liệt kê các tệp .java. Chỉ nhận tệp thường và không đi theo symbolic link.

### Bài 3 — Giới hạn độ sâu

Với cây:

~~~text
root/
├── a.txt
├── one/
│   ├── b.txt
│   └── two/
│       └── c.txt
└── d/
    └── e.txt
~~~

Hãy xác định những đường dẫn được đưa vào stream khi dùng Files.walk(root, 1), Files.walk(root, 2) và Files.walk(root, 3). Nhớ rằng root có độ sâu 0.

### Bài 4 — Tìm từ khóa trong tất cả log

Kết hợp Files.walk và Files.lines để tìm các dòng chứa WARN trong mọi tệp .log. In tên tệp cùng số dòng khớp. Đảm bảo đóng cả stream traversal và stream đọc từng tệp.

### Bài 5 — Khi nào cần walkFileTree?

Giả sử thư mục archive/ có hàng triệu tệp và bạn muốn bỏ qua toàn bộ subtree này. Giải thích vì sao Files.walk(root).filter(...) không ngăn traversal đi vào archive/, và nêu cách dùng FileVisitor với SKIP_SUBTREE.

### Bài 6 — Kiểm tra encoding

Tạo một tệp UTF-8 chứa tiếng Việt, đọc bằng Files.lines(path, StandardCharsets.UTF_8), rồi thử đọc bằng một charset khác. Quan sát kết quả và giải thích vì sao việc xác định encoding phải dựa vào hợp đồng dữ liệu chứ không dựa vào việc một chuỗi “trông có vẻ đọc được”.

## 18. Ghi nhớ khi dùng Files.lines và Files.walk

- Files.lines(path) đọc từng dòng thành Stream<String>; overload nhận charset cho phép chọn encoding tường minh.
- Files.lines xử lý lazy; dùng count, forEach, collect hoặc terminal operation khác để tiêu thụ stream.
- Dòng trả về không chứa line terminator; tệp rỗng cho stream rỗng và dòng cuối không cần ký tự xuống dòng.
- Luôn đóng stream của Files.lines bằng try-with-resources; lỗi lúc mở là IOException, lỗi trong lúc đọc có thể được bọc trong UncheckedIOException.
- Files.walk(root) trả cả root và các đường dẫn bên dưới, duyệt theo chiều sâu; thứ tự giữa các mục cùng cấp không được bảo đảm.
- maxDepth tính root ở mức 0; filter lọc phần tử nhưng không ngăn traversal đi sâu vào thư mục bị lọc.
- Files.walk mặc định không theo symbolic link; chỉ dùng FOLLOW_LINKS khi có chủ đích và xử lý vòng lặp.
- Files.walk cũng trả stream giữ tài nguyên, nên phải đóng bằng try-with-resources.
- Dùng Files.walkFileTree khi cần prune subtree hoặc xử lý chi tiết từng sự kiện/lỗi traversal.
- Dùng Files.lines để xử lý tuần tự mà không nạp toàn bộ tệp; chỉ dùng readAllLines khi tệp đủ nhỏ và cần giữ tất cả dòng trong bộ nhớ.

### Tài liệu tham khảo

- [Java SE 17 API — Files.lines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)) — đọc dòng và charset mặc định UTF-8.
- [Java SE 17 API — Files.walk](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walk(java.nio.file.Path,java.nio.file.FileVisitOption...)) — duyệt cây thư mục bằng stream.
- [Java SE 17 API — Files.walkFileTree](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.util.Set,int,java.nio.file.FileVisitor)) — duyệt bằng FileVisitor và điều khiển subtree.
- [Java SE 17 API — FileVisitOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html) — tùy chọn theo symbolic link.
- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html) — lazy operations và quản lý stream có tài nguyên.
