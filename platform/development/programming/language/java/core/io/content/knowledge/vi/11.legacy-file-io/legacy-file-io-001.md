# File là biểu diễn đường dẫn, không phải nội dung tệp trong Java

`java.io.File` là lớp truyền thống của Java đại diện cho **một đường dẫn trừu tượng (*abstract pathname*)** tới tệp hoặc thư mục trong hệ thống tệp. Đối tượng `File` giúp chương trình **mô tả và thao tác với một vị trí**: lấy tên/đường dẫn, kiểm tra tồn tại, hỏi thông tin metadata, tạo, đổi tên hoặc xóa đối tượng hệ thống tệp khi gọi đúng phương thức.

**Điểm quan trọng nhất:** tạo `new File(...)` **không tạo tệp trên ổ đĩa, không đọc nội dung và không tải dữ liệu vào RAM**. Nó chỉ tạo một **đối tượng Java chứa thông tin đường dẫn**. Nội dung của tệp được đọc/ghi bằng các API I/O thích hợp như `Files.readString`, `Files.writeString`, `FileInputStream` hoặc `FileOutputStream`.

## 1. Hai đối tượng khác nhau: đường dẫn và tệp trên hệ thống tệp

Xét đoạn mã:

```java
File file = new File("data/report.txt");
```

Đây là một khai báo Java; để chạy cần `import java.io.File;` và đặt trong class/phương thức. Sau lệnh này:

- Java đã tạo một **đối tượng `File`** chứa đường dẫn tương đối `data/report.txt`.
- Có thể đường dẫn chưa tồn tại; `new File(...)` không kiểm tra và không tạo tệp chỉ vì gọi constructor.
- Không byte nào từ `report.txt` được tự động đọc vào đối tượng; `File` **không phải mảng byte, không phải nội dung `String` và không phải một luồng đã mở**.
- Đường dẫn có thể chỉ tới **tệp**, **thư mục** hoặc một vị trí chưa tồn tại. Chỉ nhìn tên `report.txt` hoặc phần mở rộng `.txt` không chứng minh đó là tệp văn bản.

```text
Đối tượng Java:
  File("data/report.txt")
        |
        | mô tả một vị trí
        v
Hệ thống tệp:
  data/report.txt   -> có thể đang tồn tại hoặc không
                         |
                         | khi có tệp thực, có các byte nội dung
                         v
                       [byte][byte][byte]...

new File(...)  : chỉ tạo đối tượng đường dẫn
Files.read...  : đọc nội dung từ hệ thống tệp
Files.write... : ghi nội dung và có thể tạo tệp, tùy API/tùy chọn
```

Điều này tương tự ghi một **địa chỉ nhà** lên giấy: có địa chỉ không có nghĩa tại đó đã có ngôi nhà hoặc giấy đã chứa đồ đạc trong nhà. Đối tượng `File` không giữ “ảnh chụp” bất biến của metadata; mỗi lần gọi các phương thức như `exists()` có thể tra lại trạng thái hiện tại của hệ thống tệp.

## 2. `File` biểu diễn đường dẫn như thế nào?

Lớp `File` thuộc package `java.io`; các cách tạo thông dụng:

```java
import java.io.File;

File relative = new File("docs", "note.txt");
File absolute = new File("/var/tmp/note.txt"); // Ví dụ đường dẫn Unix.
File current = new File(".");
```

Trên Windows, dạng tuyệt đối có thể là `C:\temp\note.txt` (trong Java string literal cần viết `"C:\\temp\\note.txt"`). Không giả định đường dẫn Unix là tuyệt đối trên mọi nền tảng. Có thể dùng API hiện đại `Path.of("docs", "note.txt")` để ghép các phần đường dẫn theo hệ điều hành.

Các phương thức thông dụng:

| API `File` | Ý nghĩa | Có tự đọc nội dung tệp? |
| --- | --- | --- |
| `getName()` | Lấy thành phần tên cuối đường dẫn | Không |
| `getPath()` | Trả cách biểu diễn đường dẫn được lưu trong đối tượng | Không |
| `getParent()` / `getParentFile()` | Trả phần đường dẫn cha, nếu có | Không |
| `isAbsolute()` | Đường dẫn là tuyệt đối theo quy tắc nền tảng? | Không |
| `getAbsolutePath()` | Biểu diễn đường dẫn tuyệt đối | Không |
| `getCanonicalPath()` | Tạo đường dẫn canonical theo hệ thống tệp; có thể ném `IOException` | Không đọc nội dung |
| `toPath()` | Chuyển sang đối tượng `java.nio.file.Path` | Không |
| `exists()` | Kiểm tra vị trí đang tồn tại, phụ thuộc quyền/trạng thái FS | Không đọc nội dung |
| `isFile()` / `isDirectory()` | Kiểm tra loại đối tượng FS tại thời điểm gọi | Không đọc nội dung |
| `length()` | Trả kích thước tính bằng **byte** trong trường hợp tệp thích hợp | Không trả nội dung |
| `listFiles()` | Liệt kê các entry con của thư mục dưới dạng `File[]` | Không đọc nội dung từng tệp |

`getCanonicalPath()` có thể yêu cầu truy vấn hệ thống tệp và chuẩn hóa đường dẫn theo nền tảng. `getAbsolutePath()` chỉ tạo biểu diễn tuyệt đối, **không chứng minh tệp tồn tại**. Cả hai không phải cách mở/đọc file.

### Tương đối và tuyệt đối

`new File("report.txt")` thường biểu diễn đường dẫn **tương đối** so với thư mục làm việc của tiến trình Java tại thời điểm giải quyết đường dẫn. Giá trị `System.getProperty("user.dir")` cho biết thư mục làm việc thường được JVM dùng khi xử lý đường dẫn tương đối. Khi chạy từ IDE, terminal hoặc hệ thống build, thư mục làm việc có thể khác nhau.

```java
File file = new File("report.txt");
System.out.println(file.isAbsolute());      // Thường false.
System.out.println(file.getAbsolutePath()); // Phụ thuộc thư mục làm việc.
```

Không nên ghi cố định stdout của `getAbsolutePath()` trong ví dụ học tập vì kết quả phụ thuộc máy. Một đường dẫn tuyệt đối chưa chắc trỏ tới tệp tồn tại; tên file có phần mở rộng cũng không xác định được loại hay nội dung thực tế.

## 3. Tạo `File` khác với tạo tệp thực

Các thao tác cần phân biệt:

```java
File file = new File("note.txt");     // Chỉ tạo đối tượng đường dẫn.
boolean created = file.createNewFile(); // Yêu cầu tạo tệp rỗng trên đĩa.
```

`createNewFile()` có thể ném `IOException`; nếu tệp đã tồn tại, nó trả `false` và không ghi đè nội dung có sẵn. Phép kiểm tra và tạo này là một thao tác nguyên tử về mặt API, trong phạm vi cơ chế hệ thống tệp hỗ trợ. Không nên gọi nó khi chỉ muốn **đọc** một tệp.

Các thao tác truyền thống khác:

| Phương thức | Việc có thể làm trên hệ thống tệp |
| --- | --- |
| `new File(path)` | Không tạo file hay thư mục |
| `createNewFile()` | Tạo **tệp rỗng** nếu chưa tồn tại |
| `mkdir()` | Tạo một thư mục tại đường dẫn khi điều kiện cho phép |
| `mkdirs()` | Tạo thư mục cùng các thư mục cha còn thiếu |
| `delete()` | Yêu cầu xóa entry được trỏ tới; trả `boolean` |
| `renameTo(dest)` | Yêu cầu đổi tên/di chuyển; hành vi phụ thuộc nền tảng, kết quả có thể thất bại |
| `setReadable(...)`, `setWritable(...)` | Yêu cầu thay đổi thuộc tính/quyền, có giới hạn theo hệ điều hành |

Những phương thức trên **có tác dụng lên hệ thống tệp khi được gọi**; đối tượng `File` bản thân nó vẫn chỉ là biểu diễn đường dẫn.

**Không nhầm `createNewFile()` với việc ghi nội dung.** Nếu cần tạo file kèm dữ liệu, API đọc/ghi mới như `Files.writeString(...)` hoặc stream đầu ra sẽ phù hợp hơn và phải xác định chính sách tạo mới/ghi đè rõ ràng.

## 4. Chương trình Java 17+ chạy được: trước và sau khi tệp tồn tại

Để kiểm tra mà không làm ảnh hưởng file sẵn có, chương trình tạo một **thư mục tạm mới**, rồi tạo đối tượng `File` cho một tên tệp chưa tồn tại trong đó. Chỉ sau khi gọi `Files.writeString`, tệp mới có nội dung.

Lưu mã sau vào **`FilePathDemo.java`**:

```java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FilePathDemo {

    public static void main(String[] args) throws IOException {
        Path temporaryDirectory =
                Files.createTempDirectory("java-file-demo-");
        File file = temporaryDirectory.resolve("note.txt").toFile();

        try {
            // Tạo đối tượng File chưa làm xuất hiện file thật.
            System.out.println("Name: " + file.getName());
            System.out.println("Before exists: " + file.exists());
            System.out.println("Before isFile: " + file.isFile());

            // Đây mới là thao tác I/O thực sự tạo và ghi nội dung.
            Files.writeString(
                    file.toPath(), "Java I/O", StandardCharsets.UTF_8);

            System.out.println("After exists: " + file.exists());
            System.out.println("After isFile: " + file.isFile());
            System.out.println("Length in bytes: " + file.length());
            System.out.println("Text: " + Files.readString(
                    file.toPath(), StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file.toPath());
            Files.deleteIfExists(temporaryDirectory);
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac -encoding UTF-8 FilePathDemo.java
java FilePathDemo
```

**Stdout dự kiến khi thao tác hệ thống tệp thành công:**

```text
Name: note.txt
Before exists: false
Before isFile: false
After exists: true
After isFile: true
Length in bytes: 8
Text: Java I/O
```

Giải thích:

1. `Files.createTempDirectory(...)` tạo thư mục có tên riêng để ví dụ không đụng đến dữ liệu đang có.
2. `temporaryDirectory.resolve("note.txt").toFile()` tạo **đối tượng `File`** cho tệp chưa tồn tại; `exists()` và `isFile()` đều trả `false`.
3. `Files.writeString(..., UTF_8)` mới thực sự tạo và ghi file. Chuỗi `Java I/O` gồm 8 ký tự ASCII, do đó mã hóa thành **8 byte UTF-8**.
4. Sau khi ghi, `exists()` và `isFile()` là `true`; `file.length()` báo 8 **byte**, không trả nội dung.
5. `Files.readString(...)` đọc byte từ tệp thật và giải mã UTF-8 thành `String`.
6. `finally` xóa file và thư mục tạm; nếu môi trường cấm tạo/ghi/xóa, chương trình có thể ném `IOException`, không phải vì constructor `File` tự đọc hoặc tạo tệp.

Chương trình không in đường dẫn thư mục tạm vì đường dẫn đó khác nhau giữa các lần chạy. Nó kiểm chứng rõ rằng **`File` tồn tại trong bộ nhớ trước khi tệp vật lý được tạo**.

## 5. Metadata không phải nội dung

Ví dụ:

```java
File file = new File("data.bin");

boolean exists = file.exists();
boolean regular = file.isFile();
long bytes = file.length();
```

Đây là đoạn minh họa cần đặt bên trong một class/phương thức. Nó **không đọc từng byte** của `data.bin` vào ứng dụng. Các phép truy vấn có thể tương tác với hệ thống tệp để lấy metadata.

Các giới hạn cần hiểu:

- `exists() == false` không phải bằng chứng chắc chắn rằng không có đường dẫn trên thế giới: trạng thái có thể thay đổi, quyền truy cập hoặc lỗi hệ thống tệp có thể ảnh hưởng kết quả.
- `isFile()` có nghĩa là đường dẫn hiện liên kết tới tệp thông thường theo kiểm tra của Java; nếu trỏ tới thư mục, dùng `isDirectory()`.
- `length()` dùng để hỏi **kích thước tính bằng byte** trong bối cảnh tệp thông thường. `0` có thể là tệp rỗng, nhưng cũng có thể là đường dẫn không tồn tại hoặc loại đối tượng mà kích thước không được xác định theo `File.length()`. **Không dùng `length() == 0` để chứng minh file không tồn tại.**
- Metadata có thể đổi **ngay sau khi kiểm tra**, ví dụ luồng khác xóa hoặc sửa tệp. Không coi `exists()` rồi `open()` là một hành động nguyên tử.

Nếu thật sự cần đọc nội dung, dùng API phù hợp với định dạng: `Files.readString` với file văn bản và charset đã biết; `Files.readAllBytes` cho file nhị phân nhỏ; hoặc stream để xử lý file lớn.

## 6. `File` so với `FileInputStream` và `FileOutputStream`

Tên gần nhau nhưng nhiệm vụ khác nhau:

| API | Vai trò | Có trực tiếp đọc/ghi dữ liệu? |
| --- | --- | --- |
| `java.io.File` | Biểu diễn đường dẫn; metadata và thao tác hệ thống tệp | Không qua constructor; bản thân không cung cấp các phương thức đọc byte nội dung |
| `FileInputStream` | Mở luồng **đọc byte** từ tệp | Có, khi gọi `read(...)` |
| `FileOutputStream` | Mở luồng **ghi byte** ra tệp | Có, khi gọi `write(...)`; constructor có thể tạo/cắt ngắn file |
| `FileReader` / `FileWriter` | Luồng **ký tự** cho file; dùng charset tương ứng | Có, khi gọi `read/write`; cần xác định charset |
| `Files` (`java.nio.file.Files`) | API tĩnh cho tạo/đọc/ghi/sao chép/di chuyển/xóa và metadata | Có, tùy phương thức |
| `Path` (`java.nio.file.Path`) | Biểu diễn đường dẫn kiểu NIO.2 | Không tự đọc nội dung |

Ví dụ đọc file qua `FileInputStream`:

```java
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;

static int firstByte(File file) throws IOException {
    try (FileInputStream input = new FileInputStream(file)) {
        return input.read(); // 0..255 hoặc -1 nếu EOF.
    }
}
```

Đây là **phương thức minh họa**, cần đặt trong một class. `new FileInputStream(file)` có thể ném lỗi nếu tệp không tồn tại, không đọc được hoặc là thư mục. Chỉ **khi mở stream và gọi `read()`**, nội dung mới được lấy từ tệp.

Đừng nhầm `new FileInputStream(file)` với `new File(filePath)`: constructor đầu tiên có thể mở tài nguyên thật và thất bại do I/O; constructor thứ hai chủ yếu chỉ xác lập đối tượng đường dẫn.

## 7. Lớp `Path` và `Files` trong Java hiện đại

Từ Java 7, API NIO.2 (`java.nio.file`) giới thiệu `Path` và `Files`, thường giúp xử lý đường dẫn và thao tác hệ thống tệp rõ ràng hơn:

```java
import java.nio.file.Path;
import java.nio.file.Files;

Path path = Path.of("data", "report.txt");   // Chỉ mô tả đường dẫn.
boolean found = Files.exists(path);           // Kiểm tra metadata.
```

`Path.of(...)` **không tự tạo file**, giống ý nghĩa cốt lõi của `new File(...)`. Còn `Files.*` thường là nơi gọi những thao tác thật:

```java
Files.createDirectories(path.getParent()); // Tạo thư mục cha nếu cần.
Files.writeString(path, "Xin chào");       // Tạo/ghi nội dung theo API.
String content = Files.readString(path);   // Đọc nội dung.
```

Đây là mã minh họa; việc thực thi có thể tạo/ghi đè file tùy tùy chọn. `Files.writeString(path, text)` sử dụng UTF-8 theo hợp đồng mặc định; khi cần rõ ý định, có thể truyền `StandardCharsets.UTF_8`. Trong ứng dụng thực tế nên xác định đường dẫn, chính sách ghi đè và xử lý `IOException` trước khi thao tác.

Chuyển đổi giữa hai kiểu:

```java
File legacy = new File("report.txt");
Path modern = legacy.toPath();
File back = modern.toFile();
```

`toPath()` và `toFile()` chuyển **biểu diễn đường dẫn**, không sao chép hoặc tự đọc nội dung tệp. `Path` thường được ưu tiên cho mã Java mới bởi nhiều API xử lý file, link, attributes và ngoại lệ phong phú hơn; `File` vẫn phổ biến trong thư viện/ứng dụng legacy.

## 8. Đường dẫn chưa chắc tồn tại, đúng loại hoặc được truy cập

Một đối tượng `File` hợp lệ về mặt Java vẫn có thể đại diện cho:

- Một đường dẫn đến file đang tồn tại;
- Một thư mục đang tồn tại;
- Một đường dẫn chưa tồn tại;
- Một liên kết tượng trưng (*symbolic link*) và đối tượng đích theo quy tắc API;
- Một vị trí mà tiến trình không có quyền truy cập;
- Một đường dẫn có trạng thái thay đổi giữa các lần kiểm tra.

Vì vậy, không suy luận rằng “khởi tạo thành công” thì “đọc được”.

Ví dụ kiểm tra **trước khi xử lý**:

```java
if (!file.exists()) {
    throw new IllegalArgumentException("Đường dẫn không tồn tại");
}
if (!file.isFile()) {
    throw new IllegalArgumentException("Đây không phải tệp thông thường");
}
```

Đoạn minh họa này có thể giúp báo lỗi sớm trong UI, nhưng **không thay thế xử lý `IOException` khi mở/đọc**. Một tiến trình khác có thể xóa hoặc thay file sau khi bạn kiểm tra, hoặc quyền truy cập có thể thay đổi. Đây là lỗi *time-of-check to time-of-use* (TOCTOU). Với dữ liệu quan trọng hoặc không tin cậy, hãy chọn API mở file an toàn, kiểm soát quyền và xử lý lỗi trên chính thao tác thật.

Thêm nữa, các kiểm tra path như `getCanonicalPath()` không tự động biến đường dẫn do người dùng nhập thành an toàn: khi ứng dụng ghép đường dẫn từ input, cần giới hạn thư mục được phép, xử lý `..`, symlink và quyền truy cập theo yêu cầu bảo mật.

## 9. Lỗi thường gặp khi học `java.io.File`

| Quan niệm hoặc thao tác sai | Vì sao sai? | Cách hiểu/cách xử lý |
| --- | --- | --- |
| `new File("a.txt")` là đã tạo file | Constructor chỉ tạo đối tượng đường dẫn | Dùng API tạo/ghi riêng như `createNewFile` hoặc `Files.writeString` |
| `new File(...)` đã đọc file vào RAM | `File` không chứa nội dung | Mở `InputStream` hoặc dùng `Files.read*` |
| `file.toString()` trả nội dung file | `toString()` chủ yếu trả biểu diễn đường dẫn | `Files.readString(file.toPath(), charset)` để đọc văn bản |
| `file.getName()` trả tên thật từ nội dung | Nó lấy phần cuối của đường dẫn | Phân biệt tên path với dữ liệu trong file |
| `file.exists()` là bằng chứng đọc được | File có thể không có quyền đọc hoặc thay đổi sau check | Xử lý lỗi khi mở file |
| `file.length()` cho số ký tự trong file văn bản | `length()` là byte, có thể khác số ký tự UTF-8 | Chọn cách đếm ký tự sau decode nếu cần |
| `file.length() == 0` nghĩa là không tồn tại | File rỗng cũng có thể dài 0 byte | Kiểm tra tồn tại và loại file riêng |
| Đường dẫn có đuôi `.txt` chắc chắn là văn bản | Phần mở rộng chỉ là quy ước tên | Biết rõ định dạng và charset thực tế |
| `getAbsolutePath()` là tệp đã tồn tại | Chỉ biểu diễn path tuyệt đối | `exists()`/`Files.readAttributes` khi cần metadata |
| `File` và `Path` là hai file khác nhau | Chúng có thể mô tả cùng vị trí | `toPath()`/`toFile()` không tạo bản sao dữ liệu |
| Chỉ cần `exists()` trước khi đọc là không thể lỗi | Có race và lỗi I/O | Xử lý ngoại lệ từ thao tác đọc thực |
| Mở `FileOutputStream` để “xem đường dẫn” | Nó là API ghi, có thể tạo hoặc làm mất nội dung cũ | Dùng `File`/`Path` để mô tả, không mở writer ngoài ý muốn |

## 10. Khi nào chọn `File`, khi nào chọn `Path`?

Dùng `File` khi phải làm việc với API hoặc thư viện legacy nhận `java.io.File`; lớp này vẫn hữu ích cho bài học về **đường dẫn** và các thao tác filesystem truyền thống.

Với code Java hiện đại, nên ưu tiên `Path` + `Files`, đặc biệt khi cần:

- Đọc/ghi nội dung có charset xác định;
- Xử lý nhiều loại thao tác file, thuộc tính và link;
- Thông báo lỗi I/O chi tiết thông qua ngoại lệ;
- Sao chép, di chuyển, tạo thư mục và dùng tùy chọn rõ ràng.

Điều quan trọng vẫn như nhau ở cả hai hệ API:

```text
File hoặc Path = thông tin về vị trí
Files / Stream  = hành động đọc, ghi, tạo, xóa hoặc xử lý
byte[] / String = nội dung đã đọc vào bộ nhớ của chương trình
```

Ngay cả khi đối tượng `File` đã tồn tại lâu trong chương trình, trạng thái file thực tế vẫn có thể thay đổi theo thời gian; không sử dụng `File` như một bộ nhớ đệm nội dung hoặc chứng nhận “file luôn sẵn sàng”.

## 11. Bài tập tự kiểm tra

1. **`new File("missing.txt")` có ném lỗi ngay nếu file không tồn tại?** Thông thường **không**; nó chỉ tạo đối tượng biểu diễn đường dẫn.
2. **Cần tạo tệp rỗng mới từ `File` thì dùng gì?** `createNewFile()`, đồng thời xử lý `IOException` và kết quả `boolean`.
3. **`File.length()` trả gì?** Giá trị metadata kích thước **byte** trong trường hợp phù hợp, không phải chuỗi nội dung hay số ký tự.
4. **`new File("notes.txt").getName()` cho kết quả gì?** `notes.txt`, không phải văn bản bên trong.
5. **`File.toPath()` có tạo bản sao file không?** **Không**; chỉ chuyển biểu diễn đường dẫn.
6. **Muốn đọc UTF-8 từ tệp hiện có thì dùng gì?** `Files.readString(file.toPath(), StandardCharsets.UTF_8)` hoặc `InputStreamReader` phù hợp.
7. **`exists()` trả true thì lần đọc sau chắc chắn thành công?** **Không**; quyền, trạng thái và đối tượng hệ thống tệp có thể thay đổi.
8. **Có thể có một `File` trỏ tới thư mục?** **Có**; dùng `isDirectory()` để kiểm tra trạng thái tại thời điểm gọi.
9. **Vì sao không dùng `FileOutputStream` chỉ để “xác minh file”?** Vì constructor có thể tạo hoặc cắt ngắn file, gây thay đổi dữ liệu ngoài ý muốn.
10. **Nếu code mới chỉ cần mô tả đường dẫn, nên xem API nào?** `Path.of(...)`; khi thực sự cần thao tác nội dung thì dùng `Files` hoặc stream.

**Kết luận thực hành:** `File` là **một đối tượng mang đường dẫn**, không phải đối tượng lưu nội dung. **Khởi tạo `File` không đồng nghĩa tạo file; hỏi metadata không đồng nghĩa đọc nội dung; đọc/ghi dữ liệu phải dùng đúng API I/O.**