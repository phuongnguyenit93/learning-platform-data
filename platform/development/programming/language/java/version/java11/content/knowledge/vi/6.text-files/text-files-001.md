# Path.of với chuỗi đường dẫn hoặc URI (Java 11+)

## 1. Bài toán: từ thông tin vị trí đến đối tượng Path

Khi làm việc với **tệp văn bản** trong Java, ta thường bắt đầu từ một chuỗi như tên tệp `notes.txt`, các thành phần thư mục như `data` và `reports`, hoặc một **URI** nhận được từ API khác. Để đọc/ghi tệp bằng `java.nio.file.Files`, bước đầu tiên là có một đối tượng `Path` mô tả vị trí tệp.

Từ **Java 11**, interface `java.nio.file.Path` cung cấp hai phương thức tĩnh thường dùng:

```java
Path.of(String first, String... more)
Path.of(URI uri)
```

Cả hai trả về một `Path`, nhưng chúng xử lý **hai loại đầu vào khác nhau**:

- `Path.of("data", "notes.txt")`: nhận một hoặc nhiều **chuỗi thành phần đường dẫn** theo cú pháp của filesystem mặc định trên máy.
- `Path.of(uri)`: nhận một đối tượng `java.net.URI`. Java chọn **filesystem provider** tương ứng với scheme của URI (ví dụ `file`), rồi yêu cầu provider diễn giải URI đó.

Đối tượng `Path` **không phải chính tệp hay nội dung tệp**. Việc tạo `Path` không tự tạo tệp, không đọc nội dung, không đảm bảo vị trí đang tồn tại và cũng không chứng minh ứng dụng có quyền truy cập. Các thao tác thực tế như `Files.readString`, `Files.writeString`, `Files.exists`, `Files.createDirectories` mới tương tác với filesystem.

Mục tiêu bài: chọn đúng overload `Path.of`, hiểu URI/đường dẫn tương đối hoặc tuyệt đối, viết được thao tác đọc/ghi tệp UTF-8 và tránh các lỗi không tương thích giữa máy hoặc filesystem.

## 2. Dùng `Path.of(String first, String... more)`

### 2.1. Một chuỗi đường dẫn

```java
import java.nio.file.Path;

Path one = Path.of("notes.txt");       // Tệp tương đối
Path two = Path.of("data/notes.txt");  // Một chuỗi chứa dấu phân cách
```

Hai dòng này là **mảnh mã minh họa**, cần đặt trong phương thức/lớp khi biên dịch độc lập. Cách diễn giải cú pháp phụ thuộc filesystem mặc định: trên các hệ điều hành khác nhau, tên ổ đĩa, root, dấu phân cách hoặc ký tự không hợp lệ có thể khác nhau.

`Path.of("notes.txt")` là **đường dẫn tương đối**. Khi ứng dụng thực sự mở tệp, vị trí được hiểu dựa trên **working directory** của tiến trình và các quy tắc của filesystem; nó không mặc nhiên trỏ tới thư mục chứa tệp `.java`, `.class` hoặc JAR.

### 2.2. Ghép các thành phần tên

```java
Path report = Path.of("data", "reports", "2026.txt");
System.out.println(report.getFileName()); // 2026.txt
```

Các phần tử `first, more...` được nối theo quy tắc của **filesystem provider mặc định**, thường bằng dấu phân cách thư mục của hệ điều hành. Việc truyền riêng từng thành phần là cách rõ ràng khi các tên thư mục/tệp được xây dựng độc lập. Không cần tự ghép bằng `"\\"` hay `"/"` trong mã ứng dụng thông thường.

`Path.of("data", "reports", "2026.txt")` không tạo thư mục `data` hoặc `reports`. Nó chỉ tạo đối tượng mô tả đường dẫn. Nếu cần ghi vào đó, hãy tạo thư mục cha trước bằng `Files.createDirectories` rồi dùng `Files.writeString`.

### 2.3. Các thao tác Path thường dùng

```java
Path relative = Path.of("docs", "notes.txt");

relative.isAbsolute();                 // false với ví dụ tương đối này
relative.getFileName();                // notes.txt
relative.getParent();                  // docs
relative.toAbsolutePath();             // Gắn với thư mục làm việc mặc định
relative.toAbsolutePath().normalize(); // Đường dẫn tuyệt đối, chuẩn hóa cú pháp
```

- `getFileName()` và `getParent()` cho thành phần tên cuối và đường dẫn cha (có trường hợp trả `null` tùy dạng `Path`).
- `toAbsolutePath()` tạo dạng tuyệt đối dựa trên filesystem/working directory; **không kiểm tra tệp tồn tại**.
- `normalize()` loại bỏ các đoạn dư thừa về mặt **cú pháp**, như `.` và cặp tên thư mục/`..` khi có thể. Nó **không truy cập đĩa**, không xác minh symlink và không đảm bảo hai đường dẫn sau chuẩn hóa tham chiếu cùng tệp thật.
- `toRealPath()` là thao tác khác: liên quan filesystem thật, kiểm tra đường dẫn tồn tại và xử lý liên kết theo tùy chọn; có thể ném `IOException`.

Ví dụ `Path.of("docs", ".", "drafts", "..", "notes.txt").normalize()` thường tạo `Path` tương đương về cú pháp với `Path.of("docs", "notes.txt")`. Nếu có symbolic link, loại bỏ `..` theo cú pháp có thể khác ý nghĩa khi truy cập thực tế; đừng dùng `normalize()` thay cho kiểm tra quyền truy cập hoặc bảo mật.

## 3. Dùng `Path.of(URI uri)`

### 3.1. URI là gì và khác chuỗi đường dẫn ra sao?

`java.net.URI` mô tả một *resource identifier* có thể có **scheme**, ví dụ:

```text
file:///var/app/notes.txt
https://example.org/notes.txt
jar:file:///app/archive.zip!/docs/notes.txt
```

Ba dòng trên là các **ví dụ định dạng URI**, không phải các đường dẫn file đều dùng được bởi mọi hệ điều hành/provider. Scheme `file` thường tương ứng filesystem mặc định; `https` trỏ tới tài nguyên web và không có nghĩa là một tệp trong filesystem; `jar` có thể liên quan provider của filesystem trong ZIP/JAR.

`Path.of(URI uri)` chọn filesystem provider dựa trên **scheme**. Với provider mặc định, URI phải có scheme `file` và một path tuyệt đối, không có query hoặc fragment. Một vài phần khác như authority/UNC path có quy tắc phụ thuộc nền tảng.

**Không thể dùng một HTTP URI với `Path.of(uri)` để tự động tải dữ liệu qua mạng.** Nếu bài toán là đọc nội dung từ HTTP(S), phải dùng API dành cho HTTP; `Path.of` dành cho filesystem, bao gồm những provider có hỗ trợ.

### 3.2. Cách an toàn để tạo URI file từ một Path đã biết

```java
Path file = Path.of("docs", "notes.txt").toAbsolutePath();
URI uri = file.toUri();
Path restored = Path.of(uri);
```

Mã trên là mảnh minh họa, cần import `java.net.URI` và `java.nio.file.Path`. `toUri()` sinh URI tương thích cho filesystem sở hữu `Path`; với provider mặc định, URI sinh ra có scheme `file`. `Path.of(uri)` diễn giải URI đó để trả về `Path`.

Đối với **filesystem mặc định**, Java đảm bảo `Path.of(p.toUri()).equals(p.toAbsolutePath())` khi các đối tượng được tạo trong cùng JVM theo điều kiện của API. Đối với provider khác, mức đảm bảo có thể khác. Dùng một `Path` có sẵn để tạo URI là cách thuận tiện hơn việc tự nối chuỗi `"file://"` với đường dẫn hệ điều hành.

**Lưu ý:** `file.toUri()` có thể mã hóa khoảng trắng và ký tự đặc biệt trong URI (ví dụ khoảng trắng thành `%20` ở dạng ASCII). Không tự ghép chuỗi chưa encode từ tên tệp có dấu hoặc dấu cách; đừng dùng kết quả của `URI.getRawPath()` như một đường dẫn chưa giải mã.

### 3.3. Tạo Path từ URI nhận được bên ngoài

```java
URI uri = URI.create("file:///tmp/notes.txt");
Path file = Path.of(uri);
```

Đoạn này minh họa cú pháp một file URI theo **đường dẫn kiểu Unix**. Trên Windows, URI của tệp cục bộ thường có dạng chứa ổ đĩa (ví dụ `file:///C:/data/notes.txt`); cách hiểu URI phụ thuộc provider và nền tảng. Đừng viết cố định đường dẫn Unix/Windows cho chương trình muốn chạy nhiều hệ điều hành. Ưu tiên nhận `URI` hợp lệ từ API tin cậy hoặc sinh từ `Path.toUri()`.

`URI.create(...)` tự phân tích cú pháp chuỗi URI và có thể ném `IllegalArgumentException` nếu chuỗi không hợp lệ (như khoảng trắng thô). `Path.of(uri)` tiếp tục kiểm tra xem scheme/provider và các thành phần có phù hợp với filesystem hay không.

Một URI **tương đối** như `URI.create("docs/notes.txt")` không có scheme, do đó không phù hợp cho `Path.of(URI)` theo hợp đồng provider file mặc định. Nếu đầu vào thực sự là **chuỗi đường dẫn tương đối**, hãy dùng `Path.of("docs", "notes.txt")`.

### 3.4. Provider: file, jar và scheme không hỗ trợ

Với `Path.of(URI)`, provider được tìm theo scheme. Có thể gặp:
- `IllegalArgumentException` nếu URI không thỏa tiền điều kiện của provider, ví dụ URI không có scheme phù hợp hoặc có query/fragment khi provider file không chấp nhận.
- `FileSystemNotFoundException` nếu provider cho scheme không được cài đặt, hoặc filesystem được chỉ định chưa tồn tại/không thể tự tạo.
- `SecurityException` trong các môi trường có kiểm soát quyền tương ứng.
- Các lỗi nhập URI trước đó từ `URI.create` nếu chuỗi URI sai cú pháp.

Với `jar:...`, khả năng dùng phụ thuộc provider ZIP/JAR và filesystem liên quan đã được khởi tạo đúng cách. `Path.of(URI)` không có lời hứa rằng mọi URI tùy ý được tự động chuyển thành `Path`. Chủ đề xử lý filesystem trong ZIP/JAR là bài toán riêng; khi viết code thư viện hỗ trợ nhiều filesystem, nên giữ `Path` đã nhận và gọi `resolve` trên nó, thay vì tùy tiện chuyển qua filesystem mặc định.

## 4. So sánh hai overload bằng ví dụ

| Tiêu chí | `Path.of(String, String...)` | `Path.of(URI)` |
| --- | --- | --- |
| Đầu vào | Một hoặc nhiều **chuỗi đường dẫn**. | Đối tượng `java.net.URI`. |
| Chọn filesystem | **Filesystem mặc định**. | Tìm **provider theo scheme** của URI. |
| Đường dẫn tương đối | Cho phép, ví dụ `Path.of("data", "notes.txt")`. | Provider `file` mặc định yêu cầu URI file có đường dẫn tuyệt đối. |
| Ghép tên thư mục | Có thể truyền nhiều thành phần vào `first, more...`. | Đọc vị trí từ các thành phần của URI; không tự ghép tên thư mục từ nhiều chuỗi. |
| Đọc/ghi tệp ngay? | Không; tạo `Path`. | Không; tạo `Path`. |
| Dùng phổ biến | Tên tệp, đường dẫn trong cấu hình, thư mục do ứng dụng lựa chọn. | Chuyển một URI file hợp lệ thành `Path`; roundtrip từ `Path.toUri()`. |
| Sai đầu vào thường gặp | `InvalidPathException` cho chuỗi không hợp lệ theo filesystem mặc định. | `IllegalArgumentException` hoặc `FileSystemNotFoundException` do URI/provider không phù hợp. |

Khi một API đã đưa cho bạn `Path`, thông thường **giữ nguyên `Path` đó** và gọi `resolve("child.txt")` sẽ tốt hơn việc chuyển qua chuỗi rồi tạo lại bằng `Path.of(...)`; như vậy thông tin về filesystem provider không bị mất.

## 5. Ví dụ Java hoàn chỉnh: cả String, URI và đọc tệp UTF-8

Tạo tệp **`PathOfDemo.java`** với nội dung sau (dùng Java 11+):

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class PathOfDemo {
    public static void main(String[] args) throws IOException {
        // 1) Tạo Path từ các chuỗi đường dẫn, chưa đọc/ghi tệp.
        Path relative = Path.of("notes", "draft.txt");
        Path longer = Path.of("notes", ".", "drafts", "..", "draft.txt");
        System.out.println("relative=" + !relative.isAbsolute());
        System.out.println("name=" + relative.getFileName());
        System.out.println("normalizedEqual=" + relative.equals(longer.normalize()));

        // 2) Tạo tệp thật trong thư mục tạm; thư mục được dọn ở finally.
        Path folder = Files.createTempDirectory("path-of-demo-");
        Path file = folder.resolve("greeting.txt");
        try {
            Files.writeString(file, "Xin chào Java 11\n", StandardCharsets.UTF_8);

            // 3) Chuyển Path thành URI file rồi lấy lại Path.
            URI uri = file.toUri();
            Path restored = Path.of(uri);
            System.out.println("scheme=" + uri.getScheme());
            System.out.println("absolute=" + restored.isAbsolute());
            System.out.println("roundTrip=" + restored.equals(file.toAbsolutePath()));

            // 4) Files mới kiểm tra tệp và đọc nội dung của nó.
            System.out.println("exists=" + Files.exists(restored));
            System.out.println("content=" +
                    Files.readString(restored, StandardCharsets.UTF_8).trim());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(folder);
        }
    }
}
```

Lệnh biên dịch và chạy với compiler còn hỗ trợ mức Java 11:

```bash
javac -encoding UTF-8 --release 11 PathOfDemo.java
java PathOfDemo
```

**Đầu ra đã kiểm chứng trên JDK 24 khi biên dịch bằng `--release 11`:**

```text
relative=true
name=draft.txt
normalizedEqual=true
scheme=file
absolute=true
roundTrip=true
exists=true
content=Xin chào Java 11
```

Giải thích theo từng nhóm dòng:

1. `Path.of("notes", "draft.txt")` tạo đường dẫn tương đối trong ví dụ; `getFileName()` là `draft.txt`. `normalize()` đưa đường dẫn có `.` và `..` về cùng cấu trúc tên, **không yêu cầu thư mục `notes` tồn tại**.
2. `Files.createTempDirectory(...)` mới thực sự tạo thư mục tạm. `folder.resolve("greeting.txt")` lấy đường dẫn tệp con; `Files.writeString` ghi tệp UTF-8. Không cần tạo thủ công `Path` từ chuỗi tuyệt đối phụ thuộc hệ điều hành.
3. `file.toUri()` và `Path.of(uri)` thực hiện roundtrip qua URI scheme `file` cho filesystem mặc định; `restored` là một đường dẫn tuyệt đối.
4. `Files.exists(restored)` kiểm tra tệp đã được tạo; `Files.readString` đọc nội dung theo UTF-8. `trim()` chỉ loại dấu xuống dòng của chuỗi đọc để in kết quả một dòng.
5. Khối `finally` xóa tệp và thư mục tạm đã tạo. Ví dụ chỉ dọn đúng những đường dẫn do chương trình tự tạo; trong ứng dụng thật cần xử lý cẩn thận lỗi I/O và chính sách lưu giữ dữ liệu.

`Files.readString` và `Files.writeString` có từ Java 11 và vẫn là API phù hợp cho **tệp văn bản nhỏ/vừa có thể xử lý trực tiếp thành một `String`**. Với tệp rất lớn, cân nhắc đọc/ghi dòng hoặc stream để tránh tải toàn bộ nội dung vào bộ nhớ.

## 6. Đường dẫn tương đối, tuyệt đối và cách giải quyết thư mục gốc

### 6.1. `Path.of` không “đứng ở thư mục source code”

```java
Path config = Path.of("config", "app.txt");
Path absolute = config.toAbsolutePath().normalize();
```

`config` là đường dẫn **tương đối**. `toAbsolutePath()` dựa trên working directory của JVM (thường xem bằng `System.getProperty("user.dir")`), có thể khác thư mục của dự án hoặc tệp chạy. Chạy cùng chương trình từ các thư mục terminal/IDE khác nhau có thể tìm tệp ở các vị trí khác nhau.

Khi cần vị trí xác định, dùng một **base directory** được cấu hình rõ:

```java
Path base = Path.of("storage").toAbsolutePath().normalize();
Path log = base.resolve("events.txt");
```

`resolve` nối đường dẫn con với một `Path` sẵn có, giữ filesystem provider của `base`. Nên dùng cách này khi base đến từ thư mục dữ liệu do người dùng hoặc hệ thống cấu hình.

### 6.2. `normalize`, `toAbsolutePath` và `toRealPath`

| Thao tác | Có cần tệp đang tồn tại? | Ý nghĩa |
| --- | --- | --- |
| `Path.of(...)` | Không | Tạo đối tượng biểu diễn vị trí. |
| `normalize()` | Không | Chuẩn hóa cú pháp, loại phần dư thừa như `.`/`..`. |
| `toAbsolutePath()` | Không | Chuyển về đường dẫn tuyệt đối theo filesystem. |
| `Files.exists(path)` | Có truy cập/check filesystem | Kiểm tra tồn tại; `false` cũng có thể do không xác định được tình trạng. |
| `toRealPath()` | Thông thường có | Trả đường dẫn thực và xử lý symlink theo tùy chọn; có thể ném `IOException`. |

**Không dùng `normalize()` như bằng chứng rằng tệp an toàn hoặc chắc chắn nằm trong một thư mục mong muốn**, nhất là khi người dùng có thể kiểm soát tên tệp hoặc filesystem có symbolic link.

## 7. Chuỗi chứa ký tự đặc biệt, dấu cách và Unicode

Một **chuỗi đường dẫn** và **chuỗi URI** có luật cú pháp khác nhau:

```java
Path name = Path.of("my documents", "ghi chú.txt"); // Đường dẫn theo filesystem
URI fileUri = name.toAbsolutePath().toUri();         // URI đã mã hóa cần thiết
Path again = Path.of(fileUri);                       // Chuyển trở lại Path
```

Với URI, những ký tự như dấu cách phải được mã hóa đúng theo luật URI. Ví dụ, `URI.create("file:///tmp/my notes.txt")` có dấu cách thô trong chuỗi và có thể bị từ chối ngay ở bước phân tích URI. Không giải quyết việc đó bằng cách tự thay một số ký tự theo cảm tính; hãy dùng API `Path.toUri()` hoặc trình tạo URI đúng cấu trúc từ nguồn tin cậy.

Tên tệp Unicode như `"ghi chú.txt"` được xử lý theo filesystem; lưu ý mỗi hệ điều hành/filesystem có thể có quy tắc riêng về ký tự hợp lệ, phân biệt chữ hoa và chữ thường hoặc chuẩn hóa Unicode. Tạo `Path` thành công trên máy này **không** chứng minh cùng tên sẽ hoạt động y hệt trên mọi máy.

Ngoài ra, dấu `~` trong `Path.of("~/notes.txt")` hay chuỗi `"$HOME"` không mặc nhiên được Java mở rộng thành thư mục người dùng. Đó là hành vi do shell, cấu hình hoặc mã ứng dụng thực hiện nếu cần. Nếu muốn thư mục home, dùng cấu hình rõ ràng, ví dụ:

```java
Path homeNote = Path.of(System.getProperty("user.home"), "notes.txt");
```

Đây vẫn chỉ là tạo `Path`; việc đọc/ghi cần `Files` và quyền trên thư mục đích.

## 8. Xử lý lỗi thực tế khi chuyển String/URI thành Path

### 8.1. `InvalidPathException` với đầu vào chuỗi

`Path.of("...")` có thể ném `java.nio.file.InvalidPathException` khi tên chứa ký tự/cú pháp không hợp lệ theo filesystem mặc định. Không có một bộ ký tự cấm giống nhau cho Windows, Linux và macOS.

Cùng một chuỗi có thể là đường dẫn hợp lệ trên nền tảng này nhưng không hợp lệ ở nền tảng khác. Đừng dựa vào việc chỉ kiểm tra bằng regex tự viết để đảm bảo đường dẫn hợp lệ trên mọi filesystem.

### 8.2. Lỗi URI/provider không phù hợp

Các trường hợp dễ nhầm:
- `Path.of(URI.create("https://example.org/notes.txt"))` không biến URI HTTP thành tệp. Nếu không có provider thích hợp, `FileSystemNotFoundException` có thể xảy ra; xử lý HTTP bằng API HTTP.
- `Path.of(URI.create("notes.txt"))`: URI không có scheme nên không đáp ứng tiền điều kiện của `Path.of(URI)`. Với đường dẫn tương đối, dùng `Path.of("notes.txt")`.
- URI file có query/fragment hoặc cấu trúc không phù hợp provider mặc định có thể bị từ chối bằng `IllegalArgumentException`.
- URI của ZIP/JAR chỉ giải quyết được khi filesystem/provider liên quan đã được cung cấp/khởi tạo đúng cách.

### 8.3. Có Path chưa có nghĩa thao tác Files thành công

`Files.readString` hoặc `Files.writeString` vẫn có thể ném `IOException` nếu tệp không tồn tại, thiếu quyền, đường dẫn cha không có, thư mục không cho ghi, đĩa lỗi hoặc encoding không hợp lệ. Hãy xử lý ngoại lệ ở tầng tương ứng với nghiệp vụ.

`Files.createDirectories(parent)` có thể tạo chuỗi thư mục cha nếu cần, nhưng việc tạo thư mục và tệp là **thao tác ghi thực tế**, cần lựa chọn rõ đường dẫn đích và quyền truy cập. Mã ví dụ hoàn chỉnh sử dụng thư mục tạm do chương trình tạo để tránh sửa dữ liệu có sẵn.

## 9. Lưu ý về an toàn khi đường dẫn do người dùng nhập

Khi dùng input từ người dùng, cần phân biệt **tạo một `Path`** với **cho phép truy cập tệp đó**:

```java
Path allowedRoot = Path.of("workspace").toAbsolutePath().normalize();
Path requested = allowedRoot.resolve(userInput).normalize();

if (!requested.startsWith(allowedRoot)) {
    throw new IllegalArgumentException("Outside allowed directory");
}
```

Đây là đoạn **minh họa kiểm tra vị trí theo cú pháp**, không phải cơ chế bảo mật hoàn chỉnh. `userInput` là một chuỗi đã có từ bên ngoài. `startsWith(Path)` xét quan hệ thành phần đường dẫn trên cùng filesystem; nó tốt hơn kiểm tra chuỗi bằng `startsWith(String)` vì chuỗi tiền tố như `"/safe"` cũng khớp với `"/safe-other"`.

Tuy vậy, phép kiểm tra cú pháp có thể bị vượt qua khi filesystem có **symlink**, đường dẫn được thay đổi giữa lúc kiểm tra và lúc mở tệp, mount point hoặc một chính sách quyền phức tạp. Khi cần bảo vệ dữ liệu nhạy cảm, phải thiết kế kiểm tra filesystem thật và cơ chế mở tệp phù hợp với mô hình đe dọa, không chỉ dựa vào `normalize()/startsWith()`.

Đối với ứng dụng chỉ tạo tên tệp từ dữ liệu tin cậy, `Path.of(base, child)` hoặc `base.resolve(child)` thường đủ rõ ràng; đừng biến những tình huống đơn giản thành cơ chế kiểm tra rườm rà.

## 10. Những lỗi học viên thường mắc

| Lỗi | Nguyên nhân | Cách làm đúng |
| --- | --- | --- |
| Nghĩ `Path.of("notes.txt")` đã tạo tệp | `Path.of` chỉ tạo mô tả đường dẫn. | Gọi `Files.writeString` hoặc API tạo tệp khi muốn ghi. |
| Dùng `Path.of("https://example.org/a.txt")` để đọc web | Chuỗi này không phải filesystem HTTP; dấu `:` có thể còn không hợp lệ trên một số hệ điều hành. | Dùng client HTTP cho HTTP(S); dùng `Path` cho filesystem. |
| Dùng `Path.of(URI.create("notes.txt"))` cho đường dẫn tương đối | URI không có scheme phù hợp. | `Path.of("notes.txt")`. |
| Tự ghép `"file://" + rawPath` | Phụ thuộc hệ điều hành, dễ sai escape và ký tự đặc biệt. | Dùng `path.toUri()` hoặc tạo URI hợp lệ bằng API đúng loại. |
| Chèn `"/"` hoặc `"\\"` cố định vào mọi đường dẫn | Dễ sai khi chuyển hệ điều hành/provider. | Dùng các thành phần `Path.of("a", "b")` hoặc `path.resolve("b")`. |
| Nghĩ `toAbsolutePath()` kiểm tra tồn tại | Nó chỉ tạo một dạng đường dẫn tuyệt đối. | Dùng `Files.exists`/`toRealPath` và xử lý lỗi I/O khi cần. |
| Nghĩ `normalize()` bảo vệ khỏi mọi `..`/symlink | Chỉ chuẩn hóa cú pháp. | Xây dựng giới hạn truy cập theo filesystem và chính sách thực tế. |
| Dùng đường dẫn tương đối, nhưng IDE/CLI đọc khác tệp | Working directory có thể khác nhau. | Cố định base directory rõ ràng. |
| Tin rằng `Path.of(uri)` tải file `https` | `Path.of` chọn provider, không phải HTTP downloader. | Dùng HTTP client nếu tài nguyên nằm trên web. |
| Dùng `Files.readString` cho tệp nhiều GB | Đọc toàn bộ nội dung vào một `String` có thể tốn nhiều bộ nhớ. | Chọn API stream/reader phù hợp quy mô dữ liệu. |

## 11. Bài tập tự kiểm tra

**Câu 1.** Cần mở file `notes.txt` trong thư mục `data` của working directory trên Windows/Linux. Viết dạng `Path.of` nào rõ ràng?

**Đáp án:** `Path.of("data", "notes.txt")`. Nó ghép các thành phần theo filesystem mặc định; còn muốn mở thực tế, gọi `Files.readString` hoặc API Files tương ứng.

**Câu 2.** Nếu `URI` được tạo từ `file.toUri()`, có thể dùng `Path.of(uri)` để lấy lại đường dẫn file không?

**Đáp án:** Có, với URI `file` do filesystem mặc định sinh ra, và API có bảo đảm roundtrip về dạng tuyệt đối trong điều kiện đã nêu. Không suy rộng bảo đảm này sang mọi provider tùy ý.

**Câu 3.** Vì sao `Path.of(URI.create("https://example.org/file.txt"))` không phải cách đọc một tệp văn bản từ website?

**Đáp án:** Vì `Path.of(URI)` yêu cầu filesystem provider tương ứng; nó không tải HTTP(S) qua mạng. Dùng Java HTTP Client hoặc công cụ HTTP phù hợp.

**Câu 4.** `Path.of("data", "..", "secret.txt").normalize()` có đảm bảo không thể thoát thư mục dữ liệu không?

**Đáp án:** Không. `normalize()` chỉ xử lý cú pháp đường dẫn; cần ràng buộc base directory và xét rủi ro symlink/quyền filesystem khi input không tin cậy.

**Câu 5.** Hai lệnh `Path.of("logs", "today.txt")` và `Files.writeString(path, "...")` khác nhau ở đâu?

**Đáp án:** Lệnh thứ nhất tạo `Path` mà không thực hiện I/O; lệnh thứ hai mới ghi file và có thể ném `IOException`.

**Câu 6.** Một tệp tên có dấu cách và tiếng Việt cần chuyển thành URI. Nên dùng `"file://" + path.toString()` không?

**Đáp án:** Không. Dùng `path.toUri()` giúp tạo URI đúng cho filesystem provider, bao gồm mã hóa các ký tự cần thiết.

## 12. Kết luận và tài liệu chính thức

- `Path.of(String, String...)` và `Path.of(URI)` có từ **Java 11** và vẫn là API chuẩn trong Java hiện đại.
- Chọn đầu vào đúng loại: **chuỗi đường dẫn** thì dùng `Path.of(String...)`; **URI file hợp lệ** thì dùng `Path.of(URI)`.
- `Path.of(String...)` dùng filesystem mặc định; `Path.of(URI)` tìm provider theo URI scheme. Không phải URI nào cũng biểu diễn đường dẫn của một filesystem đã có.
- `Path` là mô tả đường dẫn, không có nghĩa tệp đã tồn tại. Dùng `Files` cho các thao tác thật sự; với văn bản UTF-8, `Files.readString` và `Files.writeString` là lựa chọn thuận tiện khi nội dung vừa với bộ nhớ.
- Tránh đường dẫn cố định theo OS, URI ghép chuỗi thủ công, nhầm đường dẫn tương đối với thư mục source, và xem `normalize()` như biện pháp bảo mật hoàn chỉnh.

Nguồn tham khảo API Java chính thức:
- [Java SE 11 — Path.of(String...) và Path.of(URI)](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Path.html).
- [Java SE 11 — java.net.URI](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/URI.html).
- [Java SE 11 — Files.readString, Files.writeString và createTempDirectory](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html).
- [Java SE 11 — FileSystemProvider](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html).