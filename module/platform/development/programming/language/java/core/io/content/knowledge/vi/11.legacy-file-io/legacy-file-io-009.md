# Chuyển đổi File.toPath và Path.toFile trong Java

## 1. Mục tiêu và phạm vi

Trong Java, **`java.io.File`** là biểu diễn đường dẫn tệp/thư mục theo API I/O truyền thống; **`java.nio.file.Path`** là biểu diễn đường dẫn thuộc một `FileSystem` theo API NIO.2 (có từ Java 7). Một dự án thực tế thường gặp cả hai: thư viện cũ trả `File`, còn mã mới dùng `Files`, `Path`, `DirectoryStream`, `FileChannel` hoặc `WatchService`.

Hai cầu nối trực tiếp là:

- **`File.toPath()`**: chuyển một `File` sang `Path` thuộc hệ thống tệp mặc định.
- **`Path.toFile()`**: chuyển một `Path` thuộc *default file system provider* sang `File`.

Chúng giúp tái sử dụng đường dẫn giữa API cũ và mới mà không phải tự nối chuỗi đường dẫn:

~~~text
                    File.toPath()
java.io.File ------------------------------> java.nio.file.Path
              <------------------------------
                    Path.toFile()
       Đường dẫn trên hệ thống tệp mặc định
~~~

Cần nắm năm giới hạn trước khi áp dụng:

1. **Chuyển đổi không tạo, mở, di chuyển hoặc đọc tệp.** Nó chuyển biểu diễn của đường dẫn, không thực hiện thao tác I/O trên nội dung.
2. **`Path.toFile()` không dùng được với mọi `Path`.** Đặc biệt, `Path` do provider không phải hệ thống tệp mặc định tạo ra (ví dụ ZIP filesystem) có thể ném `UnsupportedOperationException`.
3. **Đường dẫn tương đối vẫn là tương đối.** Chuyển đổi không tự gọi `toAbsolutePath()` hay `toRealPath()`.
4. **Chuyển đổi không chuẩn hóa và không xác nhận tệp tồn tại.** `..`, `.`, symbolic link, quyền truy cập và tình trạng tệp là các vấn đề khác.
5. **Khi cần thao tác thực tế, chọn API phù hợp.** Ví dụ `Files.readString(path, UTF_8)`, `Files.size(path)`, `Files.copy(...)` có hành vi/ngoại lệ của riêng chúng.

Bài học trình bày cú pháp, cơ chế, tình huống chuyển đổi, giới hạn provider, tính đúng đắn của đường dẫn và ví dụ Java 17 chạy độc lập.

## 2. File và Path đại diện cho điều gì?

### 2.1. File là một abstract pathname, không phải một tệp đã mở

`java.io.File` biểu diễn **đường dẫn trừu tượng** đến một tệp hoặc thư mục. Việc tạo đối tượng:

~~~java
File file = new File("data/report.txt");
~~~

không tạo `data/report.txt` trên ổ đĩa; cũng không kiểm tra file có tồn tại hay không. Đây chỉ là một đối tượng mô tả đường dẫn. Các phương thức truyền thống như `exists()`, `isFile()`, `length()`, `listFiles()`, `renameTo()` và `delete()` mới thực hiện các kiểm tra/thao tác tương ứng, với hợp đồng kết quả và xử lý lỗi riêng.

`File` có từ Java rất sớm và xuất hiện trong nhiều API, ví dụ:

~~~java
void uploadLegacy(File attachment);
File getLegacyConfigurationFile();
~~~

Đây là **chữ ký minh họa**, không phải chương trình chạy độc lập. Chúng vẫn có giá trị khi cần tích hợp thư viện cũ hoặc giao diện yêu cầu `File`.

### 2.2. Path nằm trong mô hình FileSystem của NIO.2

`java.nio.file.Path` là một **interface** biểu diễn đường dẫn trong một `FileSystem` nhất định. Đối với hệ thống tệp mặc định, có thể tạo bằng `Path.of(...)` (Java 11+) hoặc `Paths.get(...)`:

~~~java
Path path = Path.of("data", "report.txt");
~~~

Một `Path` cung cấp các thao tác xử lý thành phần đường dẫn như `getFileName()`, `getParent()`, `resolve()`, `relativize()`, `normalize()` và `toAbsolutePath()`. Những thao tác đó thường chỉ xử lý biểu diễn đường dẫn, không đọc nội dung tệp.

Hệ thống tệp NIO còn có thể đến từ provider khác, ví dụ một ZIP/JAR filesystem. Chính khả năng đa provider này giải thích tại sao `Path` không phải lúc nào cũng chuyển được thành `File`.

### 2.3. `Files` mới là nơi thực hiện nhiều thao tác NIO

`java.nio.file.Files` là lớp tiện ích có các phương thức tĩnh làm việc với `Path`:

~~~java
boolean regular = Files.isRegularFile(path);
long byteCount = Files.size(path);
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa với `Path path` đã có. Lời gọi `Files.size` và `Files.readString` có thể ném `IOException`; `Files.isRegularFile` có cách báo kết quả khác, và `false` không nhất thiết phân biệt “không phải tệp thường” với “không xác định được do lỗi”. Chuyển `File` thành `Path` trước khi dùng `Files` chỉ cung cấp đối tượng đường dẫn đúng kiểu; bản thân chuyển đổi không đọc dữ liệu.

## 3. File.toPath(): đưa API cũ sang Path

### 3.1. Cú pháp cơ bản

~~~java
import java.io.File;
import java.nio.file.Path;

File oldFile = new File("docs", "notes.txt");
Path path = oldFile.toPath();
~~~

`File.toPath()` trả một `Path` biểu diễn cùng đường dẫn trừu tượng trên **default file system**. Nếu `File` mô tả đường dẫn tương đối, `Path` nhận được cũng mang tính tương đối. Nếu `File` mô tả đường dẫn tuyệt đối, `Path` tương ứng cũng tuyệt đối.

Không có cuộc gọi mở hay kiểm tra quyền I/O chỉ vì sử dụng `toPath()`. Do đó mã có thể viết:

~~~java
File missing = new File("not-created.txt");
Path missingPath = missing.toPath();
~~~

ngay cả khi tệp `not-created.txt` không tồn tại. Điều đó không có nghĩa thao tác đọc tiếp theo sẽ thành công.

### 3.2. Chuyển để dùng Files API

Một lý do thực tế để gọi `File.toPath()` là tận dụng các API mới hơn:

~~~java
File oldFile = obtainLegacyFile();
Path path = oldFile.toPath();

long size = Files.size(path);
byte[] bytes = Files.readAllBytes(path);
~~~

Đây là **đoạn minh họa không độc lập**: `obtainLegacyFile()` đại diện một hàm có thật trong ứng dụng, và phương thức bao ngoài cần khai báo hoặc bắt `IOException`. `Files.readAllBytes` giữ toàn bộ dữ liệu trong RAM; với tệp lớn nên đọc theo luồng thay vì giả định có đủ bộ nhớ.

Một cách dùng thực tế khác là lấy metadata, di chuyển hoặc sao chép:

~~~java
Path source = oldFile.toPath();
Path target = Path.of("archive", oldFile.getName());
Files.copy(source, target);
~~~

Đây cũng là đoạn minh họa. `Files.copy` có thể ném `IOException` nếu tệp đích đã tồn tại, thiếu quyền, thư mục cha không có hoặc nguồn gặp lỗi. **`File.toPath()` không giải quyết các ngoại lệ này.**

### 3.3. `toPath()` không thay đổi đối tượng File

Sau lời gọi:

~~~java
Path path = oldFile.toPath();
~~~

đối tượng `oldFile` vẫn là `File`, không bị chuyển đổi “tại chỗ” và không bị vô hiệu. `path` là đối tượng khác, cùng mô tả đường dẫn theo mô hình NIO. Không cần “đổi lại” để tiếp tục dùng API cũ trên `oldFile`.

## 4. Path.toFile(): tích hợp API yêu cầu java.io.File

### 4.1. Cú pháp

~~~java
import java.io.File;
import java.nio.file.Path;

Path path = Path.of("docs", "notes.txt");
File file = path.toFile();
~~~

`Path.toFile()` chuyển một đường dẫn thuộc **hệ thống tệp mặc định** sang đối tượng `java.io.File`. Ví dụ thư viện bên thứ ba hoặc API lâu đời nhận `File`:

~~~java
Path path = Path.of("reports", "daily.txt");
legacyProcess(path.toFile());
~~~

Đoạn này là minh họa; `legacyProcess(File)` là hàm giả định do ứng dụng/thư viện cung cấp. Chọn `toFile()` khi thật sự cần một `File`; nếu mọi bước sau đều dùng NIO, không cần chuyển qua lại cho có.

### 4.2. Không gọi toFile() mù quáng trên Path của provider khác

Một `Path` có thể thuộc ZIP filesystem, filesystem ảo, hoặc provider khác. `Path.toFile()` có quyền ném `UnsupportedOperationException` nếu `Path` không liên kết với default provider. Ví dụ tư duy:

~~~text
Default FileSystem:
    Path.of("logs", "app.log")      → toFile() được hỗ trợ

ZIP/JAR FileSystem:
    zipFs.getPath("/entry.txt")     → toFile() không được hỗ trợ
                                      (UnsupportedOperationException)
~~~

Đây là mô hình, không phải lệnh Java độc lập. Nếu đang dùng ZIP filesystem, hãy dùng các API `Files` làm việc trực tiếp với `Path` đó thay vì cố ép nó sang `File`. Một đường dẫn bên trong tệp ZIP không tự nhiên là một tệp thường thuộc hệ thống tệp mặc định.

**Giới hạn provider là khác biệt quan trọng giữa hai chiều chuyển đổi:** `File.toPath()` đi vào default filesystem; `Path.toFile()` không bảo đảm đưa mọi provider về một `File` tương ứng.

### 4.3. Tại sao không dùng new File(path.toString()) thay cho toFile()?

Với `Path` thuộc hệ thống tệp mặc định, `path.toFile()` diễn đạt rõ ý định chuyển kiểu theo API. Việc tự gọi:

~~~java
File file = new File(path.toString());
~~~

có thể nhìn giống nhau trên máy đang chạy, nhưng nó **ném mất thông tin rằng Path thuộc FileSystem nào** và không tạo cầu nối chính thức cho provider khác. Với `Path` từ ZIP filesystem, chuỗi `"/entry.txt"` là đường dẫn nội bộ của ZIP; tạo `new File("/entry.txt")` lại trỏ tới đường dẫn trên filesystem mặc định, có nghĩa hoàn toàn khác.

Vì vậy, **không sử dụng việc chuyển thành chuỗi để giả lập hỗ trợ provider**. Nếu một API chỉ chấp nhận `File`, dữ liệu từ provider khác có thể cần được trích ra tệp tạm thuộc filesystem mặc định theo hợp đồng ứng dụng, hoặc cần một API nhận `InputStream`/`Path` để tránh trích xuất.

## 5. Ví dụ Java 17: chuyển hai chiều bằng đường dẫn tương đối

Lưu tệp **FilePathRoundTripDemo.java**:

~~~java
import java.io.File;
import java.nio.file.Path;

public class FilePathRoundTripDemo {
    public static void main(String[] args) {
        Path original = Path.of("data", "report.txt");
        File legacy = original.toFile();
        Path restored = legacy.toPath();

        System.out.println("Relative: " + !original.isAbsolute());
        System.out.println("Same path: " + original.equals(restored));
        System.out.println("Name: " + restored.getFileName());
        System.out.println("Absolute result: "
                + restored.toAbsolutePath().isAbsolute());
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FilePathRoundTripDemo.java
java FilePathRoundTripDemo
~~~

Kết quả trên default file system thông thường:

~~~text
Relative: true
Same path: true
Name: report.txt
Absolute result: true
~~~

Giải thích:

- `Path.of("data", "report.txt")` xây dựng đường dẫn tương đối theo cú pháp hệ điều hành.
- `original.toFile()` cung cấp một `File` cho API truyền thống; `legacy.toPath()` chuyển ngược lại.
- `Path.equals` ở đây trả true vì cả hai biểu diễn cùng đường dẫn tương đối trên default provider với cấu trúc thành phần tương ứng.
- `getFileName()` trả phần cuối của đường dẫn.
- `toAbsolutePath()` tạo biểu diễn tuyệt đối theo ngữ cảnh filesystem, **không xác nhận tệp tồn tại**.

Chương trình không tạo thư mục `data` hoặc tệp `report.txt`. Do đó không được suy luận từ dòng `Same path: true` rằng tệp đã tồn tại hay đã đọc được.

## 6. Chuyển đổi không phải kiểm tra tồn tại và cũng không mở tệp

Hãy phân biệt bốn thao tác:

| Lời gọi | Ý nghĩa | Truy cập nội dung tệp? |
| --- | --- | --- |
| `file.toPath()` | Biến biểu diễn File thành Path | Không |
| `path.toFile()` | Biến Path thuộc default FS thành File | Không |
| `Files.exists(path)` | Kiểm tra sự tồn tại theo hợp đồng API | Kiểm tra filesystem, không đọc nội dung |
| `Files.readString(path, UTF_8)` | Mở/đọc và giải mã văn bản | Có; có thể ném IOException |

`Files.exists(path)` trả false nếu không tồn tại **hoặc nếu không thể xác định** theo quyền, lỗi I/O hoặc các tình huống provider khác. Vì vậy không nên coi `false` là bằng chứng chắc chắn tệp không tồn tại trong mọi trường hợp. Với thao tác yêu cầu tệp thực, thực hiện thao tác và bắt ngoại lệ là cách đáng tin hơn việc tách “check then act”.

Ví dụ sai về kỳ vọng:

~~~java
File source = new File("missing.txt");
Path path = source.toPath();   // Vẫn có thể tạo Path.
String text = Files.readString(path); // Có thể ném IOException.
~~~

Đây là đoạn minh họa. `toPath()` không làm tệp “mất” hay “xuất hiện”; lỗi phát sinh từ hành động đọc.

### 6.1. TOCTOU: kiểm tra trước không bảo đảm thao tác sau

Ngay cả khi `Files.exists(path)` trả true tại thời điểm kiểm tra, một tiến trình khác có thể xóa hoặc thay tệp trước khi `Files.newInputStream(path)` thực sự mở nó. Đây là điều kiện *time-of-check to time-of-use* (TOCTOU).

Do đó, kiểm tra tồn tại có ích cho giao diện hoặc logic sơ bộ, nhưng **không thay thế xử lý IOException của thao tác thực sự**. Tương tự, chuyển đổi `File ↔ Path` không tạo bất kỳ khóa hoặc cam kết nào về trạng thái filesystem.

## 7. Đường dẫn tương đối, tuyệt đối và thư mục làm việc

### 7.1. Tương đối giữ nguyên nghĩa tương đối

~~~java
File oldFile = new File("reports", "2026.txt");
Path path = oldFile.toPath();

System.out.println(path.isAbsolute()); // false
~~~

Đây là đoạn minh họa. Chuyển đổi không tự nối đường dẫn tới thư mục làm việc. Một đường dẫn tương đối được diễn giải theo quy tắc thư mục mặc định của môi trường thực thi và filesystem khi thực hiện thao tác cần truy cập.

Để có biểu diễn tuyệt đối, gọi tường minh:

~~~java
Path absolute = path.toAbsolutePath();
~~~

`toAbsolutePath()` không buộc tệp tồn tại; nó làm việc ở mức biểu diễn đường dẫn. Đừng nhầm nó với đường dẫn thực đã giải quyết symbolic link.

### 7.2. normalize() xử lý cú pháp, không xác nhận filesystem

Ví dụ:

~~~java
Path raw = Path.of("docs", ".", "drafts", "..", "final.txt");
Path normalized = raw.normalize();
~~~

Sau normalize, đường dẫn logic là `docs/final.txt`. Tuy nhiên, `normalize()` là thao tác **từ vựng** (*lexical*); nó không cần mở tệp hoặc kiểm tra symbolic link. Khi đường dẫn đi qua symbolic link, loại bỏ `..` có thể thay đổi cách đường dẫn được giải quyết trong filesystem thực.

Do đó, chỉ normalize khi điều đó đúng với quy tắc của ứng dụng; không coi normalize là cách tự động làm đường dẫn an toàn hoặc đồng nhất mọi đường dẫn chỉ tới cùng một tệp.

### 7.3. toRealPath() mới kiểm tra thực tế

`path.toRealPath()` trả đường dẫn thực/canonical theo hợp đồng filesystem và yêu cầu đối tượng tồn tại khi áp dụng các option mặc định. Nó có thể ném `IOException` và thường giải quyết symbolic link; có thể cung cấp `LinkOption.NOFOLLOW_LINKS` để thay đổi xử lý liên kết.

Khác nhau:

~~~text
file.toPath()               Chuyển biểu diễn; không đọc filesystem
path.toAbsolutePath()       Tạo đường dẫn tuyệt đối; không kiểm tra tồn tại
path.normalize()            Rút gọn . và .. về mặt cú pháp
path.toRealPath()           Truy vấn filesystem, có thể ném IOException
~~~

Một đường dẫn tuyệt đối chưa chắc là đường dẫn thực; một đường dẫn đã normalize chưa chắc đã tồn tại.

## 8. Ví dụ Java 17: File cũ dùng API Files để đọc văn bản

Lưu tệp **LegacyFileModernFilesDemo.java**:

~~~java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class LegacyFileModernFilesDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("file-path-");
        Path path = directory.resolve("note.txt");

        try {
            Files.writeString(path, "Java 17", StandardCharsets.UTF_8);
            File legacyFile = path.toFile();

            Path converted = legacyFile.toPath();
            System.out.println("File exists: " + legacyFile.isFile());
            System.out.println("Path exists: "
                    + Files.isRegularFile(converted));
            System.out.println("Size: " + Files.size(converted));
            System.out.println("Text: "
                    + Files.readString(converted, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(path);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 LegacyFileModernFilesDemo.java
java LegacyFileModernFilesDemo
~~~

Kết quả trong môi trường tệp thông thường có quyền tạo/xóa tệp tạm:

~~~text
File exists: true
Path exists: true
Size: 7
Text: Java 17
~~~

Giải thích:

1. `Files.createTempDirectory` tạo một thư mục tạm thật, riêng cho chương trình.
2. `Files.writeString` ghi văn bản với UTF-8.
3. `path.toFile()` đưa `Path` về kiểu `File` để minh họa một API cũ giữ đối tượng này.
4. `legacyFile.toPath()` quay lại `Path` nhằm sử dụng `Files.isRegularFile`, `Files.size` và `Files.readString`.
5. `Files.size` trả **số byte**, không phải số code point hay ký tự. Văn bản ASCII `Java 17` có 7 byte.
6. `finally` xóa tệp rồi xóa thư mục tạm, kể cả khi thân `try` gặp lỗi. Trong phần mềm thực, nếu dọn dẹp cũng thất bại thì cần bảo toàn và ghi nhận cả lỗi chính và lỗi cleanup theo chiến lược ứng dụng.

Ví dụ này cho thấy ưu điểm của việc dùng cầu nối khi dữ liệu đang ở dạng `File` nhưng ta muốn thao tác bằng API hiện đại, **không cần** biến đường dẫn thành một chuỗi thủ công.

## 9. Dùng Path.toFile khi thư viện cũ bắt buộc nhận File

Giả sử một giao diện thư viện cũ là:

~~~java
void attachFile(File file);
~~~

Bạn đang quản lý đường dẫn trong một ứng dụng dùng NIO:

~~~java
Path attachment = Path.of("uploads", "image.png");
attachFile(attachment.toFile());
~~~

Hai đoạn này là **chữ ký/lời gọi minh họa**, không phải chương trình Java độc lập. Đây là kiểu chuyển đổi hợp lý nếu `attachment` thuộc default filesystem và thư viện thật sự yêu cầu `File`.

Cần hỏi thêm hai vấn đề:

- Thư viện cũ **chỉ dùng đường dẫn** hay yêu cầu tệp phải đã tồn tại và có quyền đọc? `toFile()` không thỏa mãn các điều kiện đó.
- `Path` có chắc thuộc default provider không? Nếu không, `toFile()` có thể ném `UnsupportedOperationException`.

Nếu API cũ chấp nhận `InputStream`, đôi khi mở `Files.newInputStream(path)` và truyền luồng phù hợp hơn việc phải chuyển đổi qua `File`. Cần xác định ai đóng stream; tài nguyên phải được quản lý đúng vòng đời.

## 10. Provider: giới hạn của Path.toFile và tình huống ZIP

`Path` được gắn với một `FileSystem`, còn `File` truyền thống chủ yếu làm việc với hệ thống tệp mặc định. Vì vậy:

~~~java
Path defaultPath = Path.of("data", "report.txt");
File legacy = defaultPath.toFile(); // Hợp lệ trên default filesystem.
~~~

Nhưng một `Path` tạo bởi ZIP filesystem có thể đại diện cho một entry *bên trong* tệp ZIP. Entry ấy không tự động trở thành một tệp OS riêng. Do đó gọi `toFile()` với provider không phải mặc định sẽ ném `UnsupportedOperationException`.

### 10.1. Phân biệt hai Path khi làm việc với ZIP

Giả sử tệp ZIP nằm tại `/tmp/archive.zip` và trong đó có `/docs/a.txt`:

~~~text
Path của ZIP trên hệ thống tệp mặc định:
    /tmp/archive.zip          → toFile() có thể dùng

Path của entry trong ZIP filesystem:
    /docs/a.txt               → không phải File OS trực tiếp
                                → toFile() không được hỗ trợ
~~~

Không được khắc phục bằng `new File(entry.toString())`: đường dẫn thu được khi đó có thể trỏ tới `/docs/a.txt` ngoài filesystem mặc định, chứ không phải entry trong ZIP.

### 10.2. Xử lý bằng Files API hoặc trích xuất có chủ đích

Nếu chỉ cần đọc entry, làm việc trực tiếp với `Path`:

~~~java
byte[] payload = Files.readAllBytes(zipEntryPath);
~~~

Đoạn minh họa với `Path zipEntryPath` của ZIP filesystem đã được mở. Không cần `File`.

Nếu thư viện bắt buộc phải nhận `File` thật, ứng dụng có thể **trích xuất vào một tệp tạm trên default filesystem**, truyền tệp đó, rồi quản lý việc xóa tệp tạm đúng lúc. Đây là việc sao chép dữ liệu có chủ đích, **không phải** chuyển đổi `Path.toFile`. Cần kiểm tra kích thước entry, quyền và rủi ro tệp ZIP không tin cậy trước khi trích xuất.

### 10.3. Khi nào bắt UnsupportedOperationException?

`UnsupportedOperationException` là unchecked exception. Nếu một API công khai nhận `Path` bất kỳ nhưng bên trong bắt buộc trả `File`, hãy công bố rõ giới hạn provider, hoặc chuyển đổi tại điểm tích hợp và xử lý trường hợp không hỗ trợ theo hợp đồng nghiệp vụ.

Đừng dùng `catch(Exception)` để biến mọi lỗi thành “không tìm thấy tệp”: `UnsupportedOperationException` chỉ ra **không hỗ trợ mô hình chuyển đổi**, không nhất thiết tệp bên trong provider không tồn tại.

## 11. Giữ nguyên ý nghĩa đường dẫn trên Windows, Linux và macOS

Cùng một chuỗi ký tự có thể được hiểu khác nhau giữa hệ điều hành và filesystem:

- Trên Windows có quy tắc ổ đĩa, UNC, ký tự phân cách và một số dạng đường dẫn đặc biệt.
- Trên Linux/macOS, quy tắc đường dẫn và xử lý dấu `\` khác Windows.
- Quy tắc phân biệt chữ hoa/chữ thường, Unicode và symbolic link có thể phụ thuộc filesystem, không chỉ hệ điều hành.

Thay vì tự nối:

~~~java
String name = folder + "/" + fileName;
~~~

nên dùng API đường dẫn:

~~~java
Path full = Path.of(folder).resolve(fileName);
~~~

Hai đoạn minh họa với `folder` và `fileName` là chuỗi được cung cấp. `Path.resolve` dùng quy tắc filesystem và mô tả rõ thao tác ghép thành phần. Nhưng cần thận trọng nếu `fileName` là đầu vào không tin cậy: nó có thể chứa `..` hoặc là đường dẫn tuyệt đối làm thay đổi ý định. `normalize()` một mình **không phải bảo đảm chống path traversal**, đặc biệt khi có symbolic link hoặc thay đổi filesystem đồng thời.

Để so sánh hai đường dẫn, không nên chỉ so chuỗi `file.getPath()` với `path.toString()` và kết luận chúng trỏ cùng một tệp. Hai biểu diễn có thể khác về tương đối/tuyệt đối, `.`/`..`, casing hoặc symbolic link.

Nên lựa chọn phép so sánh theo mục đích:

- `Path.equals`: so sánh các đối tượng Path theo quy tắc của provider và cấu trúc đường dẫn, không bảo đảm xác định cùng một tệp vật lý.
- `Path.normalize()`: so sánh sau chuẩn hóa cú pháp nếu hợp đồng cho phép.
- `Files.isSameFile(a, b)`: khi cần kiểm tra hai đường dẫn có cùng chỉ định tới một file theo filesystem; có thể truy cập filesystem và ném `IOException`.

## 12. File.toPath khác File.getAbsoluteFile, File.getCanonicalFile

Một ứng dụng cũ có thể dùng:

~~~java
File absolute = file.getAbsoluteFile();
File canonical = file.getCanonicalFile();
~~~

`getAbsoluteFile()` trả biểu diễn `File` tuyệt đối theo quy tắc môi trường. `getCanonicalFile()` cố tạo đường dẫn canonical theo filesystem; nó có thể ném `IOException` và bị ảnh hưởng bởi hiện trạng filesystem.

Cách diễn đạt tương đương về **mục đích** trong NIO thường là:

~~~java
Path absolutePath = file.toPath().toAbsolutePath();
Path normalizedPath = file.toPath().toAbsolutePath().normalize();
Path realPath = file.toPath().toRealPath();
~~~

Đây là các đoạn minh họa, yêu cầu `File file` đã có và xử lý `IOException` với `toRealPath()`. Không coi ba kết quả là hoàn toàn tương đương:

- `getCanonicalFile()` và `toRealPath()` có các hợp đồng, hành vi khi tệp chưa tồn tại và tùy chọn xử lý liên kết khác nhau.
- `normalize()` xử lý cú pháp; không tương đương với việc giải quyết toàn bộ đường dẫn vật lý.
- `toRealPath()` yêu cầu tệp tồn tại khi sử dụng mặc định, có thể ném lỗi hệ thống tệp.

Nếu đang chuyển đổi code cũ, hãy xác định mục đích thật của bước “canonicalize” trước khi thay bằng một lời gọi NIO cho giống cú pháp.

## 13. Chuyển đổi khi thao tác copy, move và delete

Một tình huống phổ biến khi hiện đại hóa ứng dụng là thay các phương thức `File` cũ bằng API `Files`:

| Mã File truyền thống | Hướng NIO với File.toPath() | Điểm cần nhớ |
| --- | --- | --- |
| `file.exists()` | `Files.exists(file.toPath())` | False có thể bao gồm trường hợp không thể xác định |
| `file.isDirectory()` | `Files.isDirectory(file.toPath())` | Liên quan symbolic link/option |
| `file.length()` | `Files.size(file.toPath())` | `Files.size` có thể ném IOException |
| `file.delete()` | `Files.delete(file.toPath())` | NIO ném ngoại lệ khi thất bại thay vì chỉ boolean |
| `file.renameTo(dest)` | `Files.move(file.toPath(), dest.toPath())` | Không phải hành vi tương đương tuyệt đối; các option/provider ảnh hưởng |
| `file.listFiles()` | `Files.list(file.toPath())` | Trả Stream<Path>; phải đóng luồng trả về |
| `file.mkdirs()` | `Files.createDirectories(file.toPath())` | NIO báo lỗi chi tiết hơn; vẫn có race/điều kiện filesystem |

Cẩn trọng khi chuyển đổi: API tương tự về ý định chưa chắc có cùng điều kiện ghi đè, cách xử lý symbolic link, quyền hoặc kết quả lỗi. Một số `File` method trả boolean; nhiều `Files` method ném `IOException` giúp phân loại lỗi rõ ràng hơn. Không nên nuốt ngoại lệ để cố tái tạo boolean nếu ứng dụng cần chẩn đoán.

Đặc biệt, `Files.list` trả `Stream<Path>` gắn với tài nguyên thư mục đang mở. Nếu sử dụng, đóng stream bằng `try-with-resources`; đây là ví dụ cụ thể mà `File.toPath()` tự nó **không** chịu trách nhiệm quản lý tài nguyên.

### 13.1. Ví dụ chuyển File.renameTo sang Files.move

Lưu **MoveWithPathDemo.java**:

~~~java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class MoveWithPathDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("move-bridge-");
        Path sourcePath = folder.resolve("old.txt");
        Path targetPath = folder.resolve("new.txt");

        try {
            Files.writeString(sourcePath, "moved", StandardCharsets.UTF_8);

            File legacySource = sourcePath.toFile();
            Files.move(legacySource.toPath(), targetPath);

            System.out.println("Old exists: "
                    + Files.exists(legacySource.toPath()));
            System.out.println("New content: "
                    + Files.readString(targetPath, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(targetPath);
            Files.deleteIfExists(sourcePath);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 MoveWithPathDemo.java
java MoveWithPathDemo
~~~

Kết quả trong filesystem thông thường có quyền ghi:

~~~text
Old exists: false
New content: moved
~~~

Điểm cần chú ý: nguồn và đích thuộc cùng thư mục tạm, đích chưa tồn tại. Đây là ví dụ đơn giản để tránh tranh cãi về ghi đè. `Files.move` có thể ném `IOException` (ví dụ thiếu quyền, target tồn tại, lỗi thiết bị) hoặc các ngoại lệ khác theo hợp đồng. Nếu yêu cầu di chuyển nguyên tử, xem xét `StandardCopyOption.ATOMIC_MOVE` và xử lý khi không được hỗ trợ; không suy ra rằng mọi lời gọi `move` mặc định luôn nguyên tử.

## 14. File, Path và URL/URI: tránh nhầm kiểu chuyển đổi

Ba lớp dễ bị nhầm:

- `File`: đường dẫn trừu tượng truyền thống.
- `Path`: đường dẫn trong một `FileSystem`.
- `URI`: định danh tài nguyên theo cú pháp URI, có thể chứa scheme như `file:` hoặc `jar:`.

Với một `File` thuộc default filesystem:

~~~java
URI uri = file.toURI();
Path path = file.toPath();
~~~

Hai lời gọi không tương đương về **kiểu kết quả**: `toURI()` tạo URI, `toPath()` tạo Path. Khi có một URI `file:` hợp lệ, `Path.of(uri)` có thể tạo Path nhờ filesystem provider hỗ trợ URI đó. Nhưng URI `jar:` hoặc URI của dịch vụ mạng không thể được đổi thành `File` bằng cách tùy tiện cắt bỏ scheme.

Cũng không dùng `Path.toString()` như một dạng URI để truyền qua mạng, vì đó là biểu diễn đường dẫn theo provider, không phải encoding URI.

### 14.1. Ví dụ minh họa URI không thay cho File

~~~java
Path path = Path.of("data", "report.txt");
File file = path.toFile();       // File cho API cũ.
URI uri = file.toURI();          // URI file: cho việc định danh.
Path recovered = Path.of(uri);   // Path trên provider tương ứng.
~~~

Đây là đoạn minh họa với import `java.net.URI`, `java.io.File`, `java.nio.file.Path`. `URI` ở đây đến từ `File.toURI()` nên có scheme `file`. Chỉ dùng `Path.of(uri)` với URI mà một provider thích hợp có thể xử lý; nó không mặc định hoạt động với mọi URL HTTP.

## 15. Ngoại lệ và vấn đề an toàn khi chuyển đổi

Bản thân thao tác cầu nối tương đối nhẹ, nhưng vẫn có thể gặp những tình huống quan trọng:

| Trường hợp | Ngoại lệ/hệ quả | Cách xử lý |
| --- | --- | --- |
| `File.toPath()` với tên đường dẫn không biểu diễn được thành Path hợp lệ của default FS | Có thể ném `InvalidPathException` | Kiểm tra/chuẩn hóa đầu vào theo hợp đồng ứng dụng; không đoán OS |
| `Path.toFile()` trên provider không mặc định | `UnsupportedOperationException` | Dùng Files trên Path hoặc trích xuất có chủ đích nếu API cũ bắt buộc |
| `Files.readString(path)` khi tệp thiếu | Thường `NoSuchFileException` | Bắt IOException theo ngữ cảnh |
| `Files.size(path)` khi thiếu quyền | Có thể `AccessDeniedException`/IOException khác | Báo lỗi đúng nguyên nhân |
| Đường dẫn đến file có symbolic link | Thao tác có thể theo liên kết tùy API/option | Chọn `LinkOption` phù hợp, kiểm thử |
| Ghép đường dẫn từ input không tin cậy | Có nguy cơ path traversal | Xác định root hợp lệ, kiểm tra an toàn thực tế |
| Mã cũ gọi `new File(path.toString())` với Path ngoại provider | Có thể trỏ sang **file khác** trên default FS | Không dùng cách ép chuỗi |

**`InvalidPathException`** là unchecked exception; trong một số hệ thống, chuỗi đường dẫn có ký tự không hợp lệ sẽ bị từ chối từ giai đoạn tạo Path. Còn lỗi thiếu tệp/quyền thường chỉ xuất hiện khi bắt đầu truy cập filesystem, chẳng hạn khi `Files.newInputStream` hoặc `Files.readAttributes`.

**`SecurityException`** có thể phát sinh trong một số môi trường có cơ chế bảo mật tương ứng; nó không phải là `IOException`. Không nên gom mọi lỗi của việc tạo/chuyển đổi đường dẫn vào một nhóm “đọc tệp thất bại”.

## 16. Quản lý tài nguyên: File và Path không cần close

`File` và `Path` là các đối tượng mô tả đường dẫn. Không phải vì tên `File` mà đối tượng này đã mở một file descriptor, và không có nhu cầu dùng `try-with-resources` chỉ để tạo/chuyển đổi:

~~~java
File file = new File("example.txt");
Path path = file.toPath();
// Không cần close file hoặc path.
~~~

Khi **mở stream, channel hoặc directory stream**, cần đóng đúng vòng đời:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    byte[] buffer = new byte[4096];
    int count;
    while ((count = input.read(buffer)) != -1) {
        // Xử lý buffer[0..count).
    }
}
~~~

Đoạn minh họa cần import `java.io.InputStream` và `java.nio.file.Files`, phương thức bao ngoài xử lý `IOException`. `try-with-resources` quản lý `InputStream`; nó không liên quan tới việc phải đóng `path`.

Tương tự, `Files.lines(path)` và `Files.list(path)` trả Stream cần được đóng khi kết thúc để giải phóng tài nguyên. Một phương thức đọc ngắn như `Files.readString(path)` tự quản lý việc mở/đóng theo hợp đồng của nó nhưng vẫn có thể báo lỗi.

## 17. Kiểm thử và tình huống thường gặp trong dự án

### 17.1. Legacy API trả File, mã mới cần metadata NIO

**Đề bài:** `legacyApi.getFile()` trả `File`; cần đọc metadata hoặc văn bản với `Files`.

~~~java
File file = legacyApi.getFile();
Path path = file.toPath();
long size = Files.size(path);
~~~

Đây là đoạn minh họa với `legacyApi` do thư viện cung cấp. Nếu tệp bị mất hoặc không truy cập được, `Files.size` sẽ báo lỗi theo hợp đồng, không phải `File.toPath()`.

### 17.2. Mã mới giữ Path, thư viện cũ chỉ nhận File

**Đề bài:** Đường dẫn NIO thuộc default filesystem, cần truyền vào thư viện cũ.

~~~java
Path report = Path.of("reports", "daily.pdf");
oldLibrary.upload(report.toFile());
~~~

Đoạn minh họa giả định `oldLibrary.upload(File)` tồn tại. Nếu đường dẫn thực sự thuộc ZIP filesystem, không dùng `toFile()` như một phép ép chung; phải thay luồng làm việc hoặc trích xuất theo quy định.

### 17.3. Muốn biết File và Path có cùng chỉ tới một tài nguyên?

Nếu cả hai trỏ tới default filesystem:

~~~java
boolean same = Files.isSameFile(file.toPath(), path);
~~~

Đây là đoạn minh họa; cần xử lý `IOException`. `isSameFile` đặt câu hỏi về thực thể trong filesystem chứ không chỉ so hai chuỗi. Tuy nhiên filesystem có thể thay đổi giữa lần kiểm tra và thao tác sau; đây không phải một cơ chế khóa.

### 17.4. Mã legacy dùng renameTo và không có thông báo lỗi chi tiết

Khi cải tiến:

~~~java
Files.move(sourceFile.toPath(), targetFile.toPath());
~~~

Đây là đoạn minh họa. `Files.move` có thể ném ngoại lệ cho lý do cụ thể thay vì trả một boolean giống `File.renameTo`. Cần xem lại chính sách về tệp đích đã tồn tại, symlink, di chuyển khác provider và atomicity, không chỉ thay tên phương thức.

### 17.5. Kiểm thử không nên phụ thuộc file có sẵn

Các chương trình ví dụ phía trên dùng `Files.createTempDirectory` để tạo thư mục riêng, thêm tệp do chính chương trình ghi và dọn cuối chương trình. Cách này hạn chế phụ thuộc máy người học, nhưng vẫn cần quyền tạo/xóa tệp tạm. Khi test lỗi, nên chủ động tạo tình huống tệp chưa tồn tại hoặc đã tồn tại thay vì giả định tên bất kỳ trong thư mục làm việc chắc chắn trống.

## 18. Các lỗi phổ biến khi học File.toPath / Path.toFile

| Hiểu sai | Hậu quả | Điều đúng |
| --- | --- | --- |
| `toPath()` “đổi file thành đối tượng đã mở” | Tưởng dữ liệu đã được đọc và quên IOException | Chỉ chuyển biểu diễn đường dẫn |
| `toFile()` tạo tệp vật lý | Tưởng file tồn tại sau khi gọi | Chỉ tạo đối tượng File |
| Mọi Path đều có thể `toFile()` | Crash trên ZIP/provider khác | Chỉ default filesystem hỗ trợ |
| `new File(path.toString())` luôn bằng `path.toFile()` | Mất ý nghĩa provider, có thể trỏ file khác | Dùng `toFile()` khi được hỗ trợ |
| Convert tự tạo đường dẫn tuyệt đối | Truy cập nhầm thư mục | Dùng `toAbsolutePath()` khi cần |
| Convert tự bỏ `.`/`..` và symlink | So sánh/bảo mật sai | Phân biệt normalize với toRealPath |
| `Files.exists` bảo đảm lần đọc sau thành công | TOCTOU, quyền thay đổi | Xử lý IOException từ thao tác thực |
| Dùng `File.exists()` để xử lý mọi trường hợp lỗi | Không biết rõ vì sao false | Chọn API Files có báo ngoại lệ khi cần |
| So sánh đường dẫn chỉ bằng chuỗi | Bỏ qua cấu trúc/provider/alias | So sánh theo mục đích, cân nhắc isSameFile |
| Tự nối `"/"` giữa các thành phần | Có thể sai quy tắc nền tảng | Dùng Path.of/resolve |
| Giả định `File.renameTo` và `Files.move` giống nhau mọi điểm | Sai chính sách thay thế, lỗi và atomicity | Đọc hợp đồng API, dùng option phù hợp |
| Đóng File hoặc Path như một stream | Nhầm mô hình tài nguyên | Đóng stream/channel chứ không đóng đối tượng path |
| Lấy Path từ ZIP rồi toFile để truyền thư viện cũ | UnsupportedOperationException | Dùng Files trực tiếp hoặc trích tệp tạm hợp lệ |

## 19. Bài tập thực hành

### Bài 1 — Đường dẫn tương đối và round-trip

Tạo `Path.of("logs", "app.log")`, chuyển sang `File` rồi về `Path`. Kiểm tra `isAbsolute()`, `getFileName()`, `equals()`. Vì sao tất cả đều có thể thực hiện dù không có tệp thật?

**Gợi ý:** Những thao tác này không cần mở nội dung. `toAbsolutePath()` cũng không bắt buộc tệp tồn tại.

### Bài 2 — Đọc metadata qua File.toPath

Tạo một tệp tạm trong thư mục tạm của chương trình, ghi `"12345"` theo UTF-8, chuyển tệp thành `File` rồi dùng `Files.size(file.toPath())`. Kết quả trong trường hợp này là bao nhiêu?

**Đáp án:** 5 byte. Đây là dữ liệu ASCII nên mỗi ký tự chiếm một byte UTF-8. Nếu đổi sang văn bản có dấu/emoji, không suy số byte từ `String.length()`.

### Bài 3 — Provider không mặc định

Giả sử một thư viện trả `Path` đến entry trong ZIP filesystem. Vì sao không thể đơn giản gọi `path.toFile()`? Nếu một thư viện cũ chỉ nhận `File` thật, cần làm gì?

**Đáp án:** `Path.toFile()` không hỗ trợ provider không mặc định. Có thể tiếp tục xử lý qua `Files` với Path gốc; nếu bắt buộc File OS, trích nội dung ra tệp tạm thuộc default filesystem và quản lý vòng đời tệp đó.

### Bài 4 — normalize không phải toRealPath

Với đường dẫn `a/./b/../c.txt`, `normalize()` làm gì? Nó có xác nhận `c.txt` tồn tại không?

**Đáp án:** Rút gọn cú pháp thành `a/c.txt`, không kiểm tra tệp tồn tại. Với symbolic link, phép biến đổi này không nhất thiết bảo toàn cách giải quyết đường dẫn vật lý.

### Bài 5 — Kiểm tra tính an toàn của chuyển mã cũ

Một đoạn cũ dùng `file.delete()` trả boolean. Nếu thay bằng `Files.delete(file.toPath())` thì phải thay đổi hợp đồng xử lý lỗi như thế nào?

**Đáp án:** `Files.delete` có thể ném `IOException`, bao gồm nguyên nhân file không tồn tại/không có quyền, và có các ngoại lệ runtime khác theo hợp đồng. Caller nên xử lý/khai báo lỗi thay vì chỉ kiểm tra true/false. Nếu muốn không coi file vắng là lỗi, xem `Files.deleteIfExists` nhưng vẫn phải xử lý khả năng I/O thất bại.

### Bài 6 — Xử lý đường dẫn từ người dùng

Đường dẫn con nhận từ bên ngoài là `"../../secrets.txt"`. Vì sao gọi `normalize()` rồi `toFile()` chưa đủ bảo đảm người dùng chỉ truy cập trong thư mục cho phép?

**Đáp án:** Chuỗi có thể đi ra ngoài root dự định; symlink và biến đổi filesystem có thể làm thay đổi đích thực tế. Phải có cơ chế kiểm soát phạm vi đường dẫn và quyền truy cập phù hợp, không dựa duy nhất vào việc chuyển kiểu hay normalize.

## 20. Ghi nhớ cốt lõi

- **`File.toPath()`** chuyển một đường dẫn theo API truyền thống thành `Path` thuộc hệ thống tệp mặc định.
- **`Path.toFile()`** chuyển ngược lại khi `Path` thuộc **default file system provider**; không phải mọi Path đều hỗ trợ.
- **Chuyển đổi chỉ đổi biểu diễn.** Nó không mở, đọc, ghi, tạo, xóa tệp; không tự bảo đảm đường dẫn tồn tại hoặc có quyền truy cập.
- **Tương đối/tuyệt đối và canonical path là vấn đề riêng.** Sử dụng `toAbsolutePath`, `normalize` và `toRealPath` đúng ý nghĩa, không hoán đổi tùy tiện.
- **Để hiện đại hóa mã cũ,** dùng `file.toPath()` tại ranh giới rồi thực hiện `Files` API có xử lý ngoại lệ rõ ràng.
- **Để tích hợp thư viện cũ,** chỉ dùng `path.toFile()` khi đã biết provider hỗ trợ; với ZIP/virtual filesystem, ưu tiên API nhận Path/stream hoặc xử lý trích xuất có chủ đích.
- **Không nhầm File/Path với một tài nguyên đã mở.** Đóng luồng/kênh/thư mục stream bằng `try-with-resources`, không phải đóng đối tượng biểu diễn đường dẫn.

### Tài liệu API chính thức (Java SE 17)

- [File.toPath() — java.io.File](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html#toPath())
- [Path.toFile() — java.nio.file.Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#toFile())
- [Path — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [Files — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [FileSystem — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html)
- [StandardCopyOption — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html)
