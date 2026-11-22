# Kiểm tra tồn tại, loại tệp, kích thước và quyền truy cập với `java.io.File`

`java.io.File` là API truyền thống của Java để **biểu diễn tên đường dẫn** của tệp hoặc thư mục và truy vấn một số thuộc tính liên quan đến hệ thống tệp. Nó không đồng nghĩa với một tệp đang mở, cũng không chứng minh một đối tượng thực sự tồn tại chỉ vì bạn gọi `new File(...)`.

Các câu hỏi thông dụng là:

- Đường dẫn này có tồn tại không?
- Nó là **tệp thông thường** (regular file) hay **thư mục**?
- Tệp có bao nhiêu **byte**?
- Tiến trình Java hiện tại có thể **đọc**, **ghi** hoặc **thực thi** đường dẫn không?
- Khi kiểm tra xong, điều gì đảm bảo thao tác I/O tiếp theo thành công?

Bài học tập trung vào `File.exists()`, `isFile()`, `isDirectory()`, `length()`, `canRead()`, `canWrite()`, `canExecute()` và những giới hạn quan trọng của chúng; đồng thời chỉ rõ khi nào nên chuyển sang `java.nio.file.Path`/`Files` để lấy metadata và xử lý lỗi chính xác hơn.

## 1. `File` là biểu diễn đường dẫn, không phải file handle

```java
File file = new File("data/report.txt");
```

Đây là **đoạn minh họa** (cần `import java.io.File;`). Constructor nhận chuỗi đường dẫn và tạo một đối tượng `File`. Nó **không tự tạo** tệp `data/report.txt`, không mở luồng đọc/ghi và không bảo đảm đường dẫn hợp lệ hoặc đang tồn tại.

Phân biệt:

| Đối tượng/API | Vai trò chính | Có mở tài nguyên I/O ngay khi tạo không? |
| --- | --- | --- |
| `new File("report.txt")` | Đại diện cho pathname, truy vấn thuộc tính/đường dẫn | Không |
| `Path.of("report.txt")` | Biểu diễn đường dẫn theo API NIO.2 | Không |
| `new FileInputStream(file)` | Mở tệp để đọc byte | Có, có thể ném `FileNotFoundException` |
| `new FileOutputStream(file)` | Mở tệp để ghi byte; mặc định có thể tạo/ghi đè | Có, có thể ném lỗi |
| `Files.newInputStream(path)` | Mở byte stream với các tùy chọn tương ứng | Có, có thể ném `IOException` |
| `Files.readAttributes(...)` | Truy vấn thuộc tính theo API NIO.2 | Có thao tác truy vấn hệ thống tệp, có thể ném `IOException` |

Đường dẫn tương đối như `"data/report.txt"` được giải quyết theo **working directory** của tiến trình Java, không tự động theo thư mục chứa file `.java` hoặc `.class`. Dấu `/` và `\` là những dấu phân cách có chi tiết phụ thuộc nền tảng; dùng `Path.of("data", "report.txt")` hoặc `new File(parent, child)` giúp biểu diễn đường dẫn rõ ràng hơn.

`getName()`, `getParent()`, `getPath()` chủ yếu xử lý thông tin đường dẫn; chúng **không** xác nhận file tồn tại. `getAbsolutePath()` tạo đường dẫn tuyệt đối nhưng không mặc nhiên giải quyết symbolic link hoặc kiểm tra tệp. `getCanonicalPath()` có thể cần truy cập hệ thống tệp và ném `IOException`; không nên đồng nhất nó với `getAbsolutePath()`.

## 2. Các phép kiểm tra chính của `java.io.File`

| Phương thức | Giá trị và ý nghĩa | Giới hạn quan trọng |
| --- | --- | --- |
| `exists()` | `true` nếu đối tượng mà đường dẫn trỏ tới tồn tại theo phép truy vấn | `false` không cung cấp nguyên nhân rõ ràng; có thể do thiếu file hoặc không xác định được |
| `isFile()` | `true` khi là **regular file** theo cách nhận diện của hệ thống tệp | `false` nếu thư mục, không tồn tại hoặc thuộc loại khác |
| `isDirectory()` | `true` khi là thư mục | `false` không nhất thiết nghĩa là file thường |
| `length()` | Độ dài file theo **byte**, kiểu `long` | Với đường dẫn không tồn tại có thể trả `0`; với thư mục giá trị **không xác định** |
| `canRead()` | Kiểm tra quyền đọc theo cơ chế mà Java/hệ điều hành cung cấp | Là tín hiệu tham khảo, không bảo đảm thao tác đọc tiếp theo thành công |
| `canWrite()` | Kiểm tra quyền ghi | Không thay thế thao tác ghi thật và xử lý exception |
| `canExecute()` | Kiểm tra quyền thực thi | Phụ thuộc nền tảng, chính sách/permission, không đảm bảo lệnh chạy thành công |
| `isHidden()` | Kiểm tra thuộc tính tệp ẩn theo quy ước của nền tảng | Không nên chỉ dựa vào tiền tố dấu chấm trên mọi hệ điều hành |

**Quan trọng:** `isFile()` và `isDirectory()` không phải hai phép phủ định của nhau. `!file.isFile()` **không có nghĩa** `file.isDirectory()`: file có thể vắng mặt, là symbolic link hỏng, thiết bị, socket đặc biệt hoặc không thể truy vấn. Tương tự, `exists() == true` không nhất thiết có nghĩa là tệp **thông thường**.

### Ví dụ 1 — tệp, thư mục và đường dẫn không tồn tại

Chương trình Java 17+ sau tạo thư mục tạm và một tệp có dữ liệu ASCII đã biết, không phụ thuộc vào đường dẫn hay tệp do người học chuẩn bị.

```java
// FileTypeDemo.java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileTypeDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("file-type-");
        Path text = root.resolve("notes.txt");
        Path folder = root.resolve("folder");
        Path missing = root.resolve("missing.txt");

        try {
            Files.writeString(text, "ABC", StandardCharsets.UTF_8);
            Files.createDirectory(folder);

            File file = text.toFile();
            File directory = folder.toFile();
            File absent = missing.toFile();

            System.out.println("file.exists=" + file.exists());
            System.out.println("file.isFile=" + file.isFile());
            System.out.println("file.isDirectory=" + file.isDirectory());
            System.out.println("file.length=" + file.length());

            System.out.println("dir.exists=" + directory.exists());
            System.out.println("dir.isFile=" + directory.isFile());
            System.out.println("dir.isDirectory=" + directory.isDirectory());

            System.out.println("missing.exists=" + absent.exists());
            System.out.println("missing.isFile=" + absent.isFile());
            System.out.println("missing.isDirectory=" + absent.isDirectory());
            System.out.println("missing.length=" + absent.length());
        } finally {
            Files.deleteIfExists(text);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FileTypeDemo.java
java FileTypeDemo
```

Đầu ra khi các thao tác tạo tệp/thư mục thành công:

```text
file.exists=true
file.isFile=true
file.isDirectory=false
file.length=3
dir.exists=true
dir.isFile=false
dir.isDirectory=true
missing.exists=false
missing.isFile=false
missing.isDirectory=false
missing.length=0
```

`missing.length=0` là lý do không thể dùng `length()==0` để khẳng định “đây là file rỗng”: đường dẫn không tồn tại cũng có thể cho ra `0`. File **rỗng thật sự** cũng có `length()==0`. Kiểm tra `exists()` và `isFile()` có thể giúp diễn đạt điều bạn muốn, nhưng với mã cần xử lý lỗi chính xác vẫn nên thực hiện thao tác I/O và bắt exception.

`length()` của **thư mục** không nên được dùng để hỏi “thư mục chứa bao nhiêu dữ liệu” hoặc “có bao nhiêu file con”. Giá trị trả về cho thư mục không được bảo đảm. Muốn liệt kê file con, dùng API liệt kê thư mục; muốn đo dung lượng toàn bộ cây thư mục, phải duyệt các mục bên trong theo chính sách rõ ràng.

## 3. Kích thước `length()` đo byte, không đo ký tự

Một file văn bản chứa ký tự Unicode có thể có số byte khác số `char` và Unicode code point. Ví dụ trong UTF-8:

- Chữ `A` có 1 byte.
- Emoji `😀` có 4 byte UTF-8.
- Chuỗi `"A😀"` có 5 byte, nhưng `String.length()` trả 3 đơn vị mã UTF-16 và số code point là 2.

### Ví dụ 2 — so sánh dung lượng tệp và độ dài chuỗi

```java
// FileByteLengthDemo.java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileByteLengthDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("byte-size-", ".txt");
        String text = "A😀";

        try {
            Files.writeString(path, text, StandardCharsets.UTF_8);

            File file = path.toFile();
            System.out.println("fileBytes=" + file.length());
            System.out.println("stringChars=" + text.length());
            System.out.println("codePoints=" +
                    text.codePointCount(0, text.length()));
            System.out.println("nioBytes=" + Files.size(path));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FileByteLengthDemo.java
java FileByteLengthDemo
```

Đầu ra:

```text
fileBytes=5
stringChars=3
codePoints=2
nioBytes=5
```

Số byte thực tế phụ thuộc **charset** dùng khi ghi. Nếu file được ghi bằng encoding khác, `length()` vẫn trả số byte lưu trữ (khi thông tin có thể lấy được), không tự giải mã để đếm ký tự.

`File.length()` trả `long`; không chuyển về `int` khi file có thể lớn hơn giới hạn `int`. Một số thuộc tính file có thể thay đổi sau khi truy vấn, đặc biệt khi có tiến trình khác ghi hoặc xóa file. Đừng dùng `length()` như một cam kết dữ liệu sẽ không đổi trong lúc đọc.

### Tệp lớn và dữ liệu chưa flush

Nếu ghi qua `BufferedOutputStream` hoặc `BufferedWriter`, có thể còn dữ liệu ở bộ đệm tầng ứng dụng chưa chuyển đến file. Khi cần quan sát nội dung vừa ghi, hãy `flush()` hoặc đóng writer phù hợp trước khi kiểm tra; tuy nhiên `flush()` **không tự đảm bảo dữ liệu được ghi bền vững xuống phần cứng**. Ngay cả khi đã flush, một tiến trình khác vẫn có thể thay đổi file.

## 4. Quyền đọc, ghi, thực thi: ba câu hỏi khác nhau

```java
File file = new File("data/report.txt");
boolean readable = file.canRead();
boolean writable = file.canWrite();
boolean executable = file.canExecute();
```

Đây là **đoạn minh họa**, không phải chương trình độc lập.

Các phương thức trên kiểm tra trạng thái được nền tảng báo cáo cho tiến trình đang chạy. Ý nghĩa trong thực tế phụ thuộc hệ điều hành, hệ thống tệp, quyền người dùng, ACL, volume gắn từ xa, chính sách sandbox, quyền của thư mục cha và trạng thái đối tượng.

| Phép kiểm tra | Câu hỏi dự kiến | Điều **không được suy ra** |
| --- | --- | --- |
| `canRead()` | Đường dẫn hiện có thể đọc theo thông tin mà nền tảng cung cấp không? | Một thao tác mở/đọc sau đó chắc chắn thành công |
| `canWrite()` | Đường dẫn hiện có thể ghi theo thông tin mà nền tảng cung cấp không? | Ghi chắc chắn thành công; dung lượng đĩa đủ; file có thể bị ghi đè |
| `canExecute()` | Có quyền thực thi theo mô hình nền tảng không? | Tệp là chương trình hợp lệ hay `ProcessBuilder` sẽ chạy được |
| `exists()` | Đối tượng được truy vấn có tồn tại không? | Caller có quyền đọc nội dung hoặc mở tệp |

Một file có thể tồn tại nhưng `canRead()==false`; thư mục có thể tồn tại nhưng không thể liệt kê; file có thể ghi được ở thời điểm kiểm tra rồi đổi quyền ngay sau đó. Trên một số nền tảng hoặc khi chạy bằng tài khoản có đặc quyền, kết quả kiểm tra quyền có thể khác kỳ vọng từ bit POSIX. Không viết bài test cứng rằng một file tạm bất kỳ nhất thiết `canExecute()==false` trên mọi hệ điều hành.

Đối với thư mục, quyền “thực thi” trên POSIX thường liên quan khả năng **traverse/search** thư mục, không phải “chạy thư mục như ứng dụng”. Khả năng tạo file mới còn phụ thuộc quyền của thư mục chứa, không chỉ `canWrite()` trên file chưa tồn tại.

**Không dùng các phép kiểm tra này như cơ chế phân quyền bảo mật cho hệ thống nhiều người dùng.** Server cần cơ chế xác thực/ủy quyền độc lập và vẫn phải xử lý lỗi truy cập thật khi thao tác.

### Ví dụ 3 — quan sát quyền mà không giả định một kết quả nền tảng duy nhất

```java
// FilePermissionsDemo.java
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FilePermissionsDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("permissions-", ".txt");

        try {
            Files.writeString(path, "data", StandardCharsets.UTF_8);
            File file = path.toFile();

            System.out.println("exists=" + file.exists());
            System.out.println("regularFile=" + file.isFile());

            System.out.println("canRead=" + file.canRead());
            System.out.println("canWrite=" + file.canWrite());
            System.out.println("canExecute=" + file.canExecute());

            System.out.println("nioReadable=" + Files.isReadable(path));
            System.out.println("nioWritable=" + Files.isWritable(path));
            System.out.println("nioExecutable=" + Files.isExecutable(path));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Chạy:

```bash
javac FilePermissionsDemo.java
java FilePermissionsDemo
```

Hai dòng đầu thông thường là:

```text
exists=true
regularFile=true
```

Sáu dòng sau in `true` hoặc `false` **theo môi trường chạy**, nên không có một stdout chuẩn duy nhất cho toàn bộ chương trình. Bạn có thể thấy các phương thức `File` và `Files` cho kết quả tương tự trên file cục bộ, nhưng đó không phải cam kết chung cho mọi provider hoặc trạng thái chạy.

Đặt quyền bằng `setReadable()`, `setWritable()`, `setExecutable()` hoặc `setReadOnly()` có nhiều điều kiện phụ thuộc nền tảng; giá trị trả về chỉ cho biết thao tác yêu cầu thay đổi theo hợp đồng API, không làm các kiểm tra quyền trở thành cơ chế bảo mật hoàn chỉnh. Với quyền POSIX, có thể cân nhắc `Files.getPosixFilePermissions()`/`setPosixFilePermissions()` trên provider hỗ trợ; Windows và các hệ thống khác có mô hình quyền khác. Các lời gọi không được provider hỗ trợ có thể ném `UnsupportedOperationException`.

## 5. Bốn trạng thái thường bị nhầm lẫn

Đừng dùng logic `if (file.exists())` như thể nó đồng nghĩa với một trong bốn nhận định sau:

1. **Có đối tượng hệ thống tệp:** `exists()` có thể trả `true` cho file, thư mục hoặc một loại đối tượng khác.
2. **Là file thường:** `isFile()` mới kiểm tra loại này; đường dẫn trỏ tới thư mục phải trả `false`.
3. **Có dữ liệu:** file thường có thể **rỗng**, `length()==0`, và vẫn tồn tại hoàn toàn hợp lệ.
4. **Có thể thực hiện thao tác mong muốn:** đọc/ghi/xóa/đổi tên còn phụ thuộc quyền, tình trạng hiện thời, quyền của thư mục cha, file lock, provider và những ràng buộc khác.

Ví dụ các trạng thái:

| Trường hợp | `exists()` | `isFile()` | `isDirectory()` | `length()` | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| File thường, có nội dung | Thường `true` | `true` | `false` | Số byte nếu xác định được | Đọc/ghi vẫn có thể lỗi |
| File thường, rỗng | `true` | `true` | `false` | `0` | File rỗng hợp lệ |
| Thư mục | `true` | `false` | `true` | **Không xác định theo hợp đồng** | Không dùng `length()` để đếm file con |
| Đường dẫn không tồn tại | `false` | `false` | `false` | `0` theo hành vi của `File.length()` khi tệp không tồn tại | Không phân biệt được với file rỗng chỉ từ `length()` |
| Đường dẫn không thể truy vấn đầy đủ | Có thể là `false` | Có thể là `false` | Có thể là `false` | Không tin cậy để suy loại | Cần thao tác thực hoặc API có exception |
| Symbolic link trỏ tới file thường | Thường xét **đích liên kết** | Có thể `true` | Thường `false` | Thường theo đích | NIO.2 cho phép lựa chọn không đi theo link |

Các trường trong bảng mô tả tình huống **thông thường**, không đảm bảo kết quả không thay đổi giữa những lời gọi, hoặc provider nào cũng hỗ trợ cùng loại đối tượng.

## 6. Symbolic link: “đường dẫn” có thể trỏ tới đối tượng khác

Một symbolic link là mục hệ thống tệp chứa tham chiếu đến một đường dẫn khác. Vì vậy cần hỏi rõ: bạn muốn kiểm tra **link** hay **đích của link**?

Ví dụ về mặt khái niệm:

```text
notes-link.txt  -->  documents/notes.txt
       ^                    ^
       |                    |
     link                target
```

- Nếu target tồn tại và là file thường, các phép truy vấn `File` thông dụng thường báo theo target.
- Nếu target bị xóa, link trở thành **broken/dangling symbolic link**; `File.exists()` có thể trả `false` mặc dù **bản thân link vẫn còn**.
- Nếu cần quản lý chính link (kiểm tra link hỏng, xóa link, xem loại mà không theo link), dùng `Path` và `Files` với `LinkOption.NOFOLLOW_LINKS` ở API hỗ trợ.

```java
Path path = Path.of("notes-link.txt");

// Mã minh họa: cần import java.nio.file.Files,
// java.nio.file.Path và java.nio.file.LinkOption.
boolean targetExists = Files.exists(path);
boolean linkItselfExists =
        Files.exists(path, LinkOption.NOFOLLOW_LINKS);
boolean isLink = Files.isSymbolicLink(path);
```

`Files.exists(path)` theo link ở mặc định theo lựa chọn của API; `Files.exists(path, NOFOLLOW_LINKS)` hỏi về **mục link** (nếu xác định được); `Files.isSymbolicLink(path)` xác định loại mục. Với broken symbolic link, điều này cho phép phân biệt target không còn với link còn tồn tại. Trên một số nền tảng tạo symbolic link yêu cầu quyền đặc biệt hoặc không được provider hỗ trợ; không ép một bài test về symbolic link phải chạy thành công trên mọi máy.

Nếu áp dụng chính sách bảo mật liên quan thư mục gốc, cần thận trọng với symbolic link, canonicalization và **đường dẫn bị đổi trong lúc kiểm tra**. Một kiểm tra `startsWith` trên đường dẫn chuỗi chưa chuẩn hóa không phải cơ chế confinement đáng tin cậy trước input độc hại. Dùng APIs thao tác qua directory handle, các tùy chọn không theo link hoặc kiểm soát truy cập của hệ điều hành khi bài toán yêu cầu.

## 7. So sánh `java.io.File` với `java.nio.file.Files`

`File` có API tiện lợi và vẫn gặp trong thư viện cũ. Tuy nhiên `java.nio.file.Path` + `Files` thường phù hợp hơn khi cần truy vấn trạng thái, xử lý lỗi, symbolic link và thuộc tính chi tiết.

| Nhu cầu | `File` truyền thống | NIO.2 (`Path`/`Files`) |
| --- | --- | --- |
| Tồn tại | `file.exists()` | `Files.exists(path)` |
| Không tồn tại | `!file.exists()` thường bị dùng sai ngữ nghĩa | `Files.notExists(path)` (có thể cùng `exists()` là `false` nếu trạng thái không xác định) |
| File thường | `file.isFile()` | `Files.isRegularFile(path)` |
| Thư mục | `file.isDirectory()` | `Files.isDirectory(path)` |
| Byte length | `file.length()` | `Files.size(path)` có thể ném `IOException` |
| Đọc/ghi/thực thi được? | `canRead/canWrite/canExecute` | `Files.isReadable/isWritable/isExecutable` |
| Xem thuộc tính cơ bản | `lastModified()`, một số tiện ích | `Files.readAttributes(path, BasicFileAttributes.class)` |
| Symbolic link | Khó kiểm soát hành vi theo link | `LinkOption.NOFOLLOW_LINKS`, `isSymbolicLink`, `readSymbolicLink` |
| Loại file đặc biệt | Thông tin hạn chế | `BasicFileAttributes.isOther()` và file attribute views |
| Khi truy vấn lỗi | Nhiều phương thức trả `false`/`0` | Nhiều thao tác đọc metadata ném `IOException` với thông tin hữu ích |

Đừng hiểu `Files.exists(path)==false` là `Files.notExists(path)==true`. Java NIO.2 có **ba trạng thái có thể xảy ra** khi hỏi hệ thống tệp: xác định tồn tại, xác định không tồn tại, hoặc **không thể xác định**. Trong trạng thái thứ ba, **cả `exists()` và `notExists()` có thể đều trả `false`**. Khi cần phân biệt rõ lỗi quyền truy cập, hệ thống tệp hay I/O, hãy thực hiện truy vấn/hoạt động có thể báo `IOException`, thay vì chỉ dựa vào boolean.

### Ví dụ 4 — lấy metadata có kiểm soát lỗi với `Files`

```java
// NioFileAttributesDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class NioFileAttributesDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("nio-meta-", ".txt");

        try {
            Files.writeString(file, "Hello", StandardCharsets.UTF_8);

            BasicFileAttributes attributes =
                    Files.readAttributes(file, BasicFileAttributes.class);

            System.out.println("regular=" + attributes.isRegularFile());
            System.out.println("directory=" + attributes.isDirectory());
            System.out.println("size=" + attributes.size());
            System.out.println("filesSize=" + Files.size(file));
            System.out.println("exists=" + Files.exists(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy:

```bash
javac NioFileAttributesDemo.java
java NioFileAttributesDemo
```

Đầu ra khi thao tác thành công:

```text
regular=true
directory=false
size=5
filesSize=5
exists=true
```

`BasicFileAttributes` còn có `creationTime()`, `lastModifiedTime()`, `lastAccessTime()`, `fileKey()`, `isSymbolicLink()`, `isOther()`; ý nghĩa và mức hỗ trợ phụ thuộc file-system provider. Không tự mặc định mọi timestamp có độ chính xác giống nhau hoặc `fileKey()` luôn khác `null`.

`Files.readAttributes(...)` cho phép yêu cầu truy vấn nhiều thuộc tính cơ bản trong cùng một lời gọi và báo lỗi qua `IOException`. Tuy nhiên không mặc định đây là **snapshot nguyên tử** của mọi thuộc tính đối với mọi provider: file vẫn có thể thay đổi giữa lúc lấy attributes và lúc ứng dụng sử dụng.

## 8. Thao tác I/O mới là phép kiểm tra thực tế: TOCTOU

Một lỗi thiết kế phổ biến là **check-then-act**:

```java
if (file.exists() && file.canRead()) {
    // Một tiến trình khác có thể xóa hoặc đổi quyền
    // ngay sau khi kiểm tra.
    readTheFile(file);
}
```

Đây là **mã minh họa**, không chạy độc lập. Giữa thời điểm **kiểm tra** (*time of check*) và thời điểm **sử dụng** (*time of use*) có một khoảng trống. Trong khoảng này, file có thể bị xóa, bị thay bằng thư mục, đổi nội dung, đổi quyền hoặc bị chuyển hướng bởi link. Vì vậy các kết quả preflight không phải sự bảo đảm cho thao tác tiếp theo.

Cách ứng dụng nên làm khi mục tiêu là **đọc nội dung**:

```java
try (InputStream input = Files.newInputStream(path)) {
    // Đọc bằng stream; vẫn xử lý IOException khi cần.
} catch (NoSuchFileException ex) {
    // File không còn tồn tại tại thời điểm mở.
} catch (AccessDeniedException ex) {
    // Provider báo lỗi truy cập.
} catch (IOException ex) {
    // Lỗi I/O khác.
}
```

Đây là **mã minh họa**, cần import `InputStream`, `Files`, `Path`, `IOException`, `NoSuchFileException`, `AccessDeniedException`; `path` phải được khai báo. Các loại exception cụ thể phụ thuộc provider và thao tác; không phải mọi lỗi thiếu quyền đều được phân loại thành `AccessDeniedException`.

### Ví dụ 5 — kiểm tra tồn tại thành công nhưng thao tác sau đó vẫn lỗi

Chương trình sau **mô phỏng một cách xác định** thay đổi trạng thái bằng cách tự xóa file giữa hai bước. Nó không tạo race thật, nhưng cho thấy về mặt logic vì sao câu lệnh `exists()` không thể bảo đảm kết quả của lời gọi tiếp theo.

```java
// CheckThenActDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class CheckThenActDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("check-act-", ".txt");

        try {
            Files.writeString(path, "data", StandardCharsets.UTF_8);

            System.out.println("before=" + Files.exists(path));

            // Một thay đổi có thể xuất hiện sau bước kiểm tra.
            Files.delete(path);

            try {
                Files.readString(path, StandardCharsets.UTF_8);
                System.out.println("read succeeded");
            } catch (NoSuchFileException ex) {
                System.out.println("read failed: file was removed");
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Chạy:

```bash
javac CheckThenActDemo.java
java CheckThenActDemo
```

Stdout khi các thao tác hệ thống tệp thực hiện bình thường:

```text
before=true
read failed: file was removed
```

Kết luận **không phải** “hãy kiểm tra `exists()` lần nữa trước khi đọc”. Kiểm tra thêm vẫn có cửa sổ race. Thay vào đó:

- Với thao tác đọc, **mở** file rồi xử lý kết quả của chính lần mở/đọc; thực hiện thêm kiểm tra metadata nếu nghiệp vụ cần.
- Với ghi/tạo file mới, dùng các tùy chọn mở mang tính thao tác như `StandardOpenOption.CREATE_NEW` để yêu cầu tạo **chỉ nếu chưa tồn tại**, thay vì tự `if (!exists) createFile()` rồi hy vọng không có đối thủ.
- Với xử lý file nhiều bước hoặc yêu cầu bảo mật, sử dụng các kỹ thuật quản lý handle, atomic rename, giao dịch ứng dụng hoặc API chuyên dụng tùy hệ thống tệp và mức đảm bảo cần đạt.

## 9. Liệt kê thư mục và kiểm tra loại đối tượng

Để liệt kê thành viên thư mục theo API cũ, `File.list()` hoặc `File.listFiles()` có thể được sử dụng. Tuy nhiên `listFiles()` **có thể trả `null`** nếu đường dẫn không phải thư mục hoặc xảy ra lỗi I/O, thay vì luôn trả mảng rỗng:

```java
// Mã minh họa với directory là File đã khai báo.
File[] children = directory.listFiles();

if (children == null) {
    // Không thể coi đây là thư mục được liệt kê thành công.
} else {
    for (File child : children) {
        System.out.println(child.getName());
    }
}
```

`children.length == 0` nghĩa là việc liệt kê **thành công và không có phần tử**; `children == null` nghĩa là **không lấy được danh sách**. Không viết `for (File child : directory.listFiles())` mà không xét `null` nếu đầu vào có thể không hợp lệ hoặc không truy cập được.

Với NIO.2, `Files.newDirectoryStream(path)` hoặc `Files.list(path)` cung cấp cơ chế liệt kê và có thể báo lỗi bằng exception; phải **đóng** directory stream/stream trong `try-with-resources`. Các dòng được liệt kê có thể thay đổi khi có tiến trình khác chỉnh thư mục; không mặc định thứ tự liệt kê cố định, và không coi kết quả liệt kê là một snapshot nhất quán cho thao tác tiếp theo.

## 10. Chọn API theo câu hỏi thực sự cần trả lời

| Mục tiêu của chương trình | Cách tiếp cận |
| --- | --- |
| Hiển thị thông tin tham khảo trong giao diện | Có thể dùng `File.exists()/isFile()/length()/canRead()`, kèm khả năng trạng thái thay đổi |
| Kiểm tra file thường trước khi đề xuất chọn file | `isFile()` hoặc `Files.isRegularFile()` hữu ích, nhưng vẫn bắt lỗi khi mở |
| Cần lý do lỗi chính xác khi metadata không đọc được | `Files.readAttributes`, `Files.size` với `IOException` |
| Kiểm tra broken symbolic link | `Files.exists(path, NOFOLLOW_LINKS)` và `Files.isSymbolicLink(path)` |
| Đọc một file phục vụ nghiệp vụ | Mở stream hoặc dùng `Files.readString` phù hợp, bắt và xử lý lỗi thật |
| Tạo file mới mà không ghi đè file đã tồn tại | Dùng `CREATE_NEW` thay vì check rồi create |
| Đếm số file trong thư mục | Liệt kê bằng directory stream/listFiles và xử lý lỗi; không dùng `File.length()` |
| Xác thực quyền truy cập người dùng đến dữ liệu | Cơ chế phân quyền ứng dụng/hệ điều hành, không chỉ `canRead/canWrite` |
| Nhận thuộc tính của nhiều loại file | API NIO.2 và attribute view/provider tương ứng |

Các phép `exists`, `canRead`, `canWrite` rất có ích để hỗ trợ điều kiện UI, cảnh báo sớm và hiển thị trạng thái. Nhưng **quyết định nghiệp vụ cuối cùng** thường phụ thuộc kết quả thao tác thật và hợp đồng của hệ thống.

## 11. Lỗi phổ biến khi dùng `File`

1. **Nhầm `new File(path)` với tạo tệp:** constructor không tạo file. Dùng phương thức tạo tệp phù hợp và xử lý exception.
2. **Dùng `!isFile()` để kết luận là thư mục:** có nhiều loại/ trạng thái khác nhau; kiểm tra `isDirectory()` riêng.
3. **Dùng `length()==0` để xác định tệp rỗng:** file không tồn tại cũng cho `0`. Đừng quên kiểm tra loại file và tình trạng lỗi.
4. **Nhầm byte với ký tự:** `length()` là số byte; UTF-8 và UTF-16 có số đơn vị khác nhau.
5. **Tin tuyệt đối `canRead()`/`canWrite()`:** quyền, file và hệ thống có thể thay đổi; một check không thay cho thao tác và `IOException`.
6. **Không xét symbolic link:** link hỏng có thể làm `exists()` trả `false`; nếu muốn hỏi về link, dùng `NOFOLLOW_LINKS`.
7. **Không phân biệt không tồn tại và không thể xác định:** `Files.exists()==false` và `Files.notExists()==false` có thể cùng đúng nếu provider không thể xác định.
8. **Dùng `File.length()` cho thư mục:** độ dài thư mục không mang nghĩa số file hoặc tổng dung lượng cây.
9. **Gọi `listFiles()` rồi duyệt ngay:** mảng có thể là `null`, gây `NullPointerException`.
10. **Cho rằng có đường dẫn tuyệt đối là file tồn tại:** `getAbsolutePath()` xử lý đường dẫn, không xác thực file.
11. **Tạo trước bằng `exists()` rồi tạo file:** có thể dính race; ưu tiên `CREATE_NEW` cho yêu cầu tạo mới không ghi đè.
12. **Bỏ qua exception khi mở/đọc/ghi:** xử lý lỗi thật là yêu cầu bắt buộc, dù đã kiểm tra quyền.
13. **Không đóng stream/directory stream:** dễ rò rỉ file descriptor hoặc resource; dùng `try-with-resources`.
14. **Dùng kết quả phân quyền như kiểm soát bảo mật:** kiểm tra file không thay thế authorization theo người dùng và nghiệp vụ.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Sau `File f = new File("missing.txt");`, file đã được tạo chưa?

**Đáp án:** Chưa. Đối tượng `File` mới biểu diễn pathname; không có thao tác mở hoặc tạo file.

**Câu 2.** `f.exists()` trả `true`. Có thể kết luận `f.isFile()` cũng `true` không?

**Đáp án:** Không. Nó có thể là thư mục hoặc đối tượng khác.

**Câu 3.** `f.length() == 0` có nghĩa file đang rỗng không?

**Đáp án:** Không nhất thiết. File không tồn tại cũng có thể cho `0`; thư mục có độ dài không xác định.

**Câu 4.** Ghi `"A😀"` bằng UTF-8, `File.length()` và `String.length()` bằng bao nhiêu?

**Đáp án:** Lần lượt 5 **byte** và 3 đơn vị `char` UTF-16; chuỗi chứa 2 Unicode code point.

**Câu 5.** `canRead()==true` thì lần `new FileInputStream(f)` kế tiếp chắc chắn thành công?

**Đáp án:** Không. File/quyền có thể thay đổi, hoặc thao tác còn bị giới hạn bởi các điều kiện khác.

**Câu 6.** `Files.exists(path)==false` có luôn nghĩa `Files.notExists(path)==true`?

**Đáp án:** Không. Nếu không thể xác định trạng thái, cả hai có thể cùng trả `false`.

**Câu 7.** Một symbolic link tồn tại nhưng target đã bị xóa. Muốn kiểm tra chính link thì dùng gì?

**Đáp án:** `Files.exists(path, LinkOption.NOFOLLOW_LINKS)` và, khi phù hợp, `Files.isSymbolicLink(path)`.

**Câu 8.** Vì sao `if (!Files.exists(path)) { Files.createFile(path); }` không phải cách bảo đảm tạo mới an toàn khi có đồng thời?

**Đáp án:** Hai thao tác tách biệt có khoảng TOCTOU. Với yêu cầu không ghi đè, dùng API tạo mới có kiểm tra nguyên tử tương ứng như `Files.createFile(path)` hoặc mở với `StandardOpenOption.CREATE_NEW` và xử lý `FileAlreadyExistsException`.

**Câu 9.** `listFiles()` trả `null` và mảng rỗng có ý nghĩa như nhau?

**Đáp án:** Không. `null` có thể chỉ không phải thư mục hoặc lỗi I/O; mảng rỗng nghĩa là liệt kê thành công nhưng không có mục nào.

**Câu 10.** Nếu mục tiêu là đọc nội dung để xử lý nghiệp vụ, nên dừng sau khi `exists()` và `canRead()` đều đúng?

**Đáp án:** Không. Phải mở/đọc file, kiểm tra kết quả và xử lý `IOException`; các phép kiểm tra chỉ mang tính tham khảo tại thời điểm gọi.

**Quy tắc nhớ:** `File` đại diện cho **đường dẫn**; `exists()/isFile()/isDirectory()` trả lời những câu hỏi khác nhau; `length()` đo **byte** và không phân biệt được mọi trạng thái bằng `0`; `canRead()/canWrite()/canExecute()` phản ánh quyền theo môi trường hiện tại nhưng **không bảo đảm thao tác sau thành công**. Khi cần lỗi rõ ràng, kiểm soát symbolic link hoặc thao tác an toàn hơn, ưu tiên `Path` và `Files`, đồng thời xử lý exception của thao tác thật.
