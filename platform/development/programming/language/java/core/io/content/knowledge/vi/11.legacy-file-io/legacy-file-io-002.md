# Tạo `File` không đồng nghĩa tạo tệp vật lý trong Java

Khi viết `new File("report.txt")`, Java **chỉ tạo một đối tượng mô tả đường dẫn**, chưa tạo `report.txt` trên ổ đĩa. Đây là một điểm rất quan trọng trong nhóm **File truyền thống** (`java.io.File`): một đối tượng `File` có thể trỏ tới tệp đang tồn tại, thư mục, đường dẫn chưa tồn tại hoặc đường dẫn không truy cập được. Sự tồn tại của đối tượng Java và sự tồn tại của tài nguyên trên hệ thống tệp là **hai việc khác nhau**.

Ví dụ tối giản:

```java
File report = new File("report.txt"); // Chỉ tạo đối tượng biểu diễn tên/đường dẫn
boolean exists = report.exists();     // Hỏi hệ thống tệp có tài nguyên tương ứng không
```

Mảnh mã cần `import java.io.File;`. `new File(...)` không thực hiện thao tác tạo file vật lý. `exists()` mới kiểm tra trạng thái đường dẫn tại thời điểm gọi; nó có thể là `false` nếu file chưa tồn tại. Nếu file tồn tại từ trước, `exists()` có thể trả `true` ngay sau constructor, nhưng chính constructor **không phải tác nhân đã tạo file**.

Bài học này trình bày bản chất của `File`, các phương thức thực sự tạo tệp/thư mục, cách xử lý lỗi, ví dụ chạy được bằng JDK 17+ và những điểm cần biết khi chuyển sang `java.nio.file.Path` / `Files`.

## 1. Đối tượng File chỉ là biểu diễn đường dẫn

Tài liệu Java định nghĩa `File` là một **abstract representation of file and directory pathnames** — biểu diễn trừu tượng của đường dẫn tệp hoặc thư mục. Nó không phải là nội dung file, không phải một luồng byte đang mở và cũng không phải một handle bắt buộc đang liên kết tới file tồn tại.

Hãy hình dung:

```text
Trong JVM                             Trên ổ đĩa
----------------------------------   -------------------------------
File f = new File("data/a.txt");      data/a.txt có thể chưa tồn tại
        |
        +-- lưu thông tin đường dẫn
        +-- có getPath(), getName()
        +-- có thể gọi exists(), isFile()
        |
        +-- CHƯA tự mở, ghi hoặc tạo file vật lý
                                        |
f.createNewFile() ---------------------> tạo file rỗng nếu chưa có
Files.writeString(...) ---------------> có thể tạo/ghi file
new FileOutputStream(f) -------------> có thể tạo/mở file để ghi
```

Ba trường hợp đều hợp lệ:

1. `File f = new File("a.txt")` khi `a.txt` **chưa tồn tại**: vẫn tạo được đối tượng `f`.
2. `File f = new File("a.txt")` khi `a.txt` **đã tồn tại**: vẫn tạo đối tượng `f`, không tạo lại hoặc ghi đè.
3. `File f = new File("reports")` khi `reports` là **thư mục**: vẫn tạo đối tượng `f`; kiểm tra `isDirectory()` để xác định loại tài nguyên.

Constructor có thể báo các lỗi lập trình như đường dẫn `null`, nhưng **không** kiểm chứng rằng file hiện hữu hoặc tự tạo thư mục cha. Đừng coi thành công của constructor là bằng chứng đã ghi dữ liệu.

### Phân biệt tên đường dẫn và tài nguyên thực

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Đối tượng `File` | `new File("data.txt")` | Biểu diễn đường dẫn trong bộ nhớ JVM |
| Đường dẫn tương đối | `"data.txt"` | Được phân giải theo thư mục làm việc của tiến trình |
| Đường dẫn tuyệt đối | `"C:\\data\\data.txt"`, `"/tmp/data.txt"` | Chỉ định vị trí không phụ thuộc thư mục hiện hành (theo quy tắc hệ điều hành) |
| Tài nguyên trên hệ thống tệp | File thường, thư mục, symbolic link, v.v. | Chỉ tồn tại khi hệ thống tệp chứa mục tương ứng |
| Luồng mở | `FileInputStream` / `FileOutputStream` | Tương tác thực tế với byte của nguồn/đích, có vòng đời đóng |

`File` không đảm bảo rằng đường dẫn được định danh là file thường; nó có thể chỉ tới **thư mục**. Hơn nữa, tài nguyên có thể bị tiến trình khác tạo, xóa hoặc đổi tên **sau** khi đối tượng `File` đã được tạo.

## 2. Constructor nào cũng chỉ tạo đối tượng đường dẫn

Các cách khởi tạo phổ biến:

```java
File a = new File("notes.txt");
File b = new File("data", "notes.txt");
File parent = new File("data");
File c = new File(parent, "notes.txt");
```

Mảnh mã cần `java.io.File`.

Cả bốn dòng **không tạo file/thư mục**. `b` và `c` được dựng từ phần cha/con; phần cha chưa tồn tại trên ổ đĩa vẫn không cản trở việc tạo các đối tượng này. Dựng đối tượng đường dẫn không tự tạo đường dẫn cha trung gian.

Đặc biệt, hai dòng dưới đây không tương đương:

```java
new File("logs");  // Chỉ tạo đối tượng File mô tả "logs"
new File("logs").mkdir(); // Cố gắng tạo thư mục "logs" trên hệ thống tệp
```

Dòng thứ hai mới yêu cầu thao tác I/O, có thể thành công hoặc thất bại và phải kiểm tra kết quả.

Kể cả `getAbsolutePath()` cũng **chỉ trả thông tin đường dẫn**:

```java
File f = new File("missing.txt");
System.out.println(f.getAbsolutePath());
```

Lệnh in ra một chuỗi đường dẫn tuyệt đối dựa trên thư mục làm việc. Nó **không** tạo `missing.txt`, và kết quả không phải chứng cứ file có mặt. `getCanonicalPath()`/`getCanonicalFile()` có thể chuẩn hóa đường dẫn theo quy tắc hệ thống tệp và có thể ném `IOException`, nhưng không đồng nghĩa với thao tác tạo file vật lý.

## 3. Kiểm tra sự tồn tại và loại tài nguyên

`File` cung cấp một số phương thức thăm dò trạng thái:

| Phương thức | Ý nghĩa |
| --- | --- |
| `exists()` | Kiểm tra đường dẫn tương ứng hiện có tài nguyên truy cập được theo API |
| `isFile()` | Kiểm tra có phải **file thường** hay không |
| `isDirectory()` | Kiểm tra có phải **thư mục** hay không |
| `length()` | Lấy kích thước file theo byte; nếu không phải file thường hoặc lỗi xảy ra, kết quả không đủ để kết luận nội dung |
| `lastModified()` | Thời điểm sửa đổi cuối được báo bởi hệ thống tệp, có giá trị giới hạn khi không tồn tại/lỗi |
| `canRead()` / `canWrite()` | Kiểm tra khả năng đọc/ghi được báo tại thời điểm gọi |
| `getName()` / `getParent()` / `getPath()` | Trích xuất thông tin đường dẫn; không cần tài nguyên phải tồn tại |

Thí dụ:

```java
File candidate = new File("config/app.properties");
if (candidate.isFile()) {
    System.out.println("Đang trỏ tới một file thường");
} else if (candidate.isDirectory()) {
    System.out.println("Đang trỏ tới thư mục");
} else {
    System.out.println("Không có file thường/thư mục truy cập được tại đường dẫn");
}
```

Đây là mảnh mã với `import java.io.File;`.

**Không suy ra quá nhiều từ các kết quả boolean:**

- `exists() == false` có thể là chưa có đường dẫn, nhưng cũng có thể liên quan quyền truy cập/lỗi hệ thống. Chỉ dựa vào boolean không phân tích được mọi nguyên nhân.
- `isFile() == false` **không** khẳng định đường dẫn chắc chắn trống: nó có thể trỏ tới thư mục hoặc một loại mục hệ thống tệp khác.
- `length() == 0` **không** chứng minh file rỗng: có thể là đường dẫn chưa tồn tại hoặc lỗi.
- `canWrite() == true` không đảm bảo thao tác ghi sắp tới sẽ thành công; quyền và trạng thái có thể thay đổi.
- Sau khi kiểm tra `exists()`, một tiến trình khác vẫn có thể tạo/xóa file ngay trước thao tác tiếp theo. Đây là vấn đề **TOCTOU** (*time-of-check to time-of-use*).

Khi hành động cần đảm bảo “tạo mới nếu chưa có, nếu đã có thì thất bại”, ưu tiên chính thao tác tạo mới nguyên tử thay vì kiểm tra riêng bằng `exists()` rồi mới mở ghi.

## 4. Thao tác nào thực sự tạo file vật lý?

### 4.1. `File.createNewFile()`

```java
File output = new File("result.txt");
boolean created = output.createNewFile();
```

Đây là mảnh mã cần `java.io.File`, `IOException` phải được xử lý.

Ý nghĩa:

- Tạo **file rỗng** tại đường dẫn của `output` khi **chưa có mục cùng tên**, đồng thời kiểm tra tồn tại và tạo mới như một thao tác nguyên tử theo hợp đồng API.
- Trả `true` nếu **đã tạo mới thành công**.
- Trả `false` nếu mục cùng tên **đã tồn tại**; không tự ghi đè.
- Có thể ném `IOException` nếu không tạo được file vì lỗi I/O, thư mục cha thiếu, quyền truy cập hoặc điều kiện hệ thống khác.
- Không tự tạo những thư mục cha bị thiếu.
- File vừa tạo có độ dài 0 byte; nó chưa chứa văn bản hay nội dung ứng dụng.

Vì vậy:

```java
File f = new File("result.txt");
System.out.println(f.createNewFile()); // true khi mới tạo
System.out.println(f.createNewFile()); // false nếu file vẫn còn
```

Hai dòng `println` minh họa kết quả **trong điều kiện không có tác nhân khác thay đổi đường dẫn** và việc tạo lần đầu thành công. Không thể cam kết mọi hệ thống đều cho phép ghi tại đường dẫn ví dụ.

### 4.2. `Files.createFile(path)`

API NIO hiện đại:

```java
Path path = Path.of("result.txt");
Files.createFile(path);
```

Đây là mảnh mã cần `java.nio.file.*` và xử lý `IOException`.

`Files.createFile(...)` cũng yêu cầu tạo **file rỗng mới** với kiểm tra tồn tại và tạo mới nguyên tử. Khác biệt dễ quan sát là: **nếu đường dẫn đã tồn tại, nó thường ném `FileAlreadyExistsException`**, thay vì trả `false` như `File.createNewFile()`. Các lỗi khác cũng thường được cung cấp dưới dạng những subtype `IOException` giàu thông tin hơn.

Nên dùng `Files.createFile(...)` khi thiết kế mới với `Path`; dùng `createNewFile()` khi đang làm việc với API `java.io.File` truyền thống.

### 4.3. Mở luồng ghi cũng có thể tạo file

`new FileOutputStream(file)` hoặc `new FileWriter(file)` là thao tác mở **đích ghi thực tế**, và có thể:

- Tạo file mới nếu đường dẫn chưa tồn tại và thư mục cha hợp lệ.
- Ghi đè/truncate nội dung file đã có nếu dùng constructor mặc định không append.
- Thất bại nếu không có quyền, đường dẫn sai, thư mục cha chưa tồn tại, hoặc đang trỏ vào tài nguyên không ghi được.

Ví dụ:

```java
File f = new File("message.txt"); // Chưa tạo file
try (FileOutputStream out = new FileOutputStream(f)) {
    out.write(new byte[] { 65, 66, 67 }); // Ghi "ABC" ở dạng byte
}
```

Đây là mảnh mã; cần `java.io.File`, `java.io.FileOutputStream` và xử lý `IOException`. **Thao tác mở `FileOutputStream`** có thể tạo file; không phải `new File`. Với file đã tồn tại, `FileOutputStream(f)` mặc định làm trống nội dung cũ trước khi ghi. Để ghi nối, dùng constructor có cờ append phù hợp và hiểu quy tắc ghi nối của hệ thống.

Với dữ liệu văn bản, cũng có thể dùng:

```java
Files.writeString(Path.of("message.txt"), "Xin chào",
        StandardCharsets.UTF_8);
```

Trong Java 17, khi không truyền `OpenOption`, `Files.writeString` mặc định tương đương `CREATE`, `TRUNCATE_EXISTING` và `WRITE`: có thể **tạo file nếu chưa có hoặc ghi đè nội dung nếu đã có**. Cần import `java.nio.file.*`, `java.nio.charset.StandardCharsets` và xử lý `IOException`. Đừng dùng mặc định đó cho file người dùng quan trọng nếu không muốn ghi đè.

## 5. Tạo thư mục khác tạo file thường

`File` có hai phương thức quan trọng:

```java
File single = new File("logs");
boolean one = single.mkdir();

File nested = new File("reports/2026/october");
boolean many = nested.mkdirs();
```

Mảnh mã cần `java.io.File`. Trong đó:

- `mkdir()` cố gắng tạo **một thư mục**. Nếu thư mục cha còn thiếu thì thao tác thông thường thất bại.
- `mkdirs()` cố gắng tạo thư mục đích **và các thư mục cha còn thiếu**. Khi thất bại, một số thư mục cha **có thể đã được tạo**, nên thao tác không phải transaction rollback toàn bộ.
- Cả hai trả `true` khi thư mục mục tiêu **được tạo bởi lời gọi đó**, và `false` nếu không tạo được; `false` cũng có thể xảy ra vì thư mục đã tồn tại.
- `mkdirs()` không có nghĩa tạo file văn bản `october`; nó cố gắng tạo **thư mục** có tên đó.

Mẫu cho một file nằm trong thư mục chưa tồn tại:

```java
File file = new File("reports/2026/result.txt");
File parent = file.getParentFile();

if (parent != null && !parent.isDirectory()) {
    if (!parent.mkdirs() && !parent.isDirectory()) {
        throw new IOException("Cannot create parent directory");
    }
}
boolean created = file.createNewFile();
```

Đây là mảnh mã; cần `java.io.*`. Kiểm tra lần hai bằng `isDirectory()` giúp xử lý trường hợp một tác nhân khác vừa tạo thư mục trước khi `mkdirs()` trả về. Tuy vậy, filesystem có thể tiếp tục thay đổi giữa các lệnh; đoạn mã không loại bỏ mọi race.

NIO thường rõ hơn khi tạo nhiều cấp thư mục:

```java
Path folder = Path.of("reports", "2026");
Files.createDirectories(folder);
Path file = folder.resolve("result.txt");
Files.createFile(file);
```

Mảnh mã cần `java.nio.file.*` và xử lý `IOException`. `Files.createDirectories` không phải `Files.createFile`: lệnh đầu tạo **thư mục**, lệnh sau tạo **file thường**.

## 6. Ví dụ Java 17+ chạy độc lập và kiểm tra được

Ví dụ dùng **thư mục tạm riêng** để không phụ thuộc một file có sẵn trong thư mục dự án. Nó cho thấy điều gì xảy ra tại mỗi bước, sau đó xóa những tài nguyên đã tạo.

Lưu thành `FileObjectVsDiskDemo.java`:

```java
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileObjectVsDiskDemo {
    public static void main(String[] args) throws IOException {
        // Phương thức này thực sự tạo một thư mục tạm trên ổ đĩa.
        Path root = Files.createTempDirectory("file-path-demo-");

        // resolve(...) và toFile() chỉ chuẩn bị các đường dẫn/đối tượng.
        Path parent = root.resolve("reports").resolve("2026");
        Path name = parent.resolve("lesson.txt");
        Path generated = parent.resolve("generated.txt");

        try {
            File f = name.toFile();

            System.out.println("after new File: " + f.exists());
            System.out.println("parent exists: " + Files.exists(parent));

            System.out.println("mkdirs: " + parent.toFile().mkdirs());

            System.out.println("first createNewFile: " + f.createNewFile());
            System.out.println("second createNewFile: " + f.createNewFile());

            System.out.println("isFile: " + f.isFile());
            System.out.println("isDirectory: " + f.isDirectory());

            Files.writeString(generated, "Hello", StandardCharsets.UTF_8);
            System.out.println("writeString created: "
                    + Files.isRegularFile(generated));
            System.out.println("read: "
                    + Files.readString(generated, StandardCharsets.UTF_8));
        } finally {
            // Dọn từ con tới cha; deleteIfExists không tự xóa cây thư mục.
            Files.deleteIfExists(generated);
            Files.deleteIfExists(name);
            Files.deleteIfExists(parent);
            Files.deleteIfExists(root.resolve("reports"));
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac FileObjectVsDiskDemo.java
java FileObjectVsDiskDemo
```

Stdout trong môi trường tệp tạm ghi được và không có tác nhân thay đổi đường dẫn giữa các thao tác:

```text
after new File: false
parent exists: false
mkdirs: true
first createNewFile: true
second createNewFile: false
isFile: true
isDirectory: false
writeString created: true
read: Hello
```

Giải thích:

1. `Files.createTempDirectory(...)` **thực sự tạo một thư mục tạm** để chứa ví dụ. Việc này khác với `new File(...)`.
2. `root.resolve(...)` tạo `Path` trỏ tới tên chưa tồn tại; `name.toFile()` tạo một đối tượng `File`. `exists()` vẫn là `false` vì chưa có tệp vật lý.
3. `parent.toFile().mkdirs()` tạo `reports` và `reports/2026`, nên kết quả là `true`.
4. `f.createNewFile()` lần đầu tạo file rỗng `lesson.txt` nên trả `true`; lần sau trả `false` vì mục đã có.
5. `f.isFile()` xác nhận file thường; `f.isDirectory()` là `false`.
6. `Files.writeString(generated, ...)` tạo file `generated.txt` và ghi byte của `"Hello"` theo UTF-8; `readString` đọc lại.
7. `finally` xóa file trước, thư mục con sau. Nếu một thao tác dọn dẹp gặp lỗi I/O, Java sẽ ném ngoại lệ; ví dụ không được xem là cơ chế dọn dẹp bền vững cho mọi hệ điều hành/điều kiện race.

Ví dụ được thiết kế với đường dẫn tạm mới, nhưng đầu ra vẫn phụ thuộc quyền tạo tệp/thư mục và hệ thống tệp không bị thay đổi đồng thời. Không mã hóa cứng đường dẫn tuyệt đối vào stdout để giữ bài kiểm thử dễ tái lập trên Windows, Linux và macOS.

## 7. Các cách tạo file đều có hành vi khác nhau

| Cách gọi | Có tự tạo file/thư mục vật lý không? | Nếu đường dẫn đã có |
| --- | --- | --- |
| `new File(path)` | **Không** | Chỉ tạo đối tượng đường dẫn |
| `Path.of(path)` | **Không** | Chỉ tạo đối tượng `Path` |
| `file.getAbsolutePath()` | **Không** | Chỉ trả chuỗi đường dẫn |
| `file.exists()` | **Không** | Chỉ thăm dò trạng thái |
| `file.createNewFile()` | **Có: file rỗng** nếu chưa có | Trả `false` |
| `Files.createFile(path)` | **Có: file rỗng** nếu chưa có | Thường ném `FileAlreadyExistsException` |
| `file.mkdir()` | **Có: một thư mục** nếu tạo được | Trả `false` |
| `file.mkdirs()` | **Có: chuỗi thư mục cần thiết** nếu tạo được | Có thể trả `false` |
| `Files.createDirectories(path)` | **Có: các thư mục cần thiết** | Thành công nếu đường dẫn đã là thư mục phù hợp |
| `new FileOutputStream(file)` | Có thể tạo/mở file để ghi | Mặc định truncate file đang có |
| `new FileOutputStream(file, true)` | Có thể tạo file nếu chưa có | Mở để ghi nối |
| `Files.writeString(path, text, UTF_8)` | Có thể tạo và ghi file | Mặc định truncate nội dung cũ |
| `File.createTempFile(...)` | **Có: tạo file tạm rỗng thực** | API chọn tên phù hợp theo cơ chế tạo tạm |
| `Files.createTempFile(...)` | **Có: tạo file tạm rỗng thực** | API chọn tên phù hợp theo cơ chế tạo tạm |
| `Files.createTempDirectory(...)` | **Có: tạo thư mục tạm thực** | API chọn tên phù hợp theo cơ chế tạo tạm |

Sự tương phản `new File(...)` với `File.createTempFile(...)` rất đáng nhớ: tên hai API cùng nhắc tới `File`, nhưng **constructor chỉ tạo đối tượng**, còn **factory `createTempFile` có tác dụng phụ lên hệ thống tệp**.

## 8. File có thể tồn tại nhưng không phải file thường

Giả sử một thư mục tên `data` đã tồn tại:

```java
File candidate = new File("data");
System.out.println(candidate.exists());
System.out.println(candidate.isFile());
System.out.println(candidate.isDirectory());
```

Mảnh mã chỉ minh họa. Trong điều kiện `data` là thư mục truy cập được, kết quả lần lượt là `true`, `false`, `true`.

Điều đó có nghĩa:

- `exists()` kiểm tra có tài nguyên tại đường dẫn, **không** kiểm tra loại mong muốn.
- Nếu chương trình cần đọc một file thường, hãy kiểm tra `isFile()` hoặc sử dụng API đọc với xử lý lỗi thích hợp.
- Nếu chương trình cần tạo file `data` nhưng đã có thư mục cùng tên, `createNewFile()` không thể biến thư mục đó thành file thường.
- Nếu chương trình cần tạo thư mục `data` nhưng đã có file thường cùng tên, `mkdirs()` không biến file đó thành thư mục.

Trong nhiều trường hợp, bạn không cần gọi trước `exists()` hay `isFile()`; thực hiện thao tác đọc/ghi đúng yêu cầu và xử lý `IOException` sẽ tránh được một khoảng race giữa kiểm tra và sử dụng.

## 9. Đường dẫn tương đối, thư mục làm việc và vị trí thật

`new File("output.txt")` tạo đối tượng với **đường dẫn tương đối**. Vị trí mà chương trình nhìn tới phụ thuộc thư mục làm việc hiệu dụng của JVM. Không được đồng nhất với thư mục chứa tệp `.java`, vị trí IDE hiển thị hay thư mục chứa `.class`.

Ví dụ:

```java
File f = new File("output.txt");
System.out.println(f.getPath());
System.out.println(f.getAbsolutePath());
System.out.println(f.getCanonicalPath());
```

Mảnh mã cần `java.io.File` và xử lý `IOException` từ `getCanonicalPath()`. Ba kết quả có thể khác về việc chứa đường dẫn tương đối, tuyệt đối và canonical. **Không có phương thức nào trên đây tạo file.**

Một số lưu ý:

- Tùy hệ điều hành, dấu phân cách đường dẫn có thể là `/` hoặc `\`. Đừng tự nối đường dẫn bằng ký tự không phù hợp khi có thể dùng `new File(parent, child)` hoặc `Path.resolve(...)`.
- `getAbsolutePath()` không cam kết mọi thành phần `.`/`..` đã được chuẩn hóa như đường dẫn thực. `getCanonicalPath()` trả dạng canonical theo quy tắc hệ thống và có thể cần tương tác với filesystem.
- `Path.toAbsolutePath()` và `Path.normalize()` cũng **không tạo file**. `normalize()` chủ yếu chuẩn hóa cú pháp và không thay thế xác thực tài nguyên thực.
- `Path.toRealPath()` khác: nó truy vấn filesystem và thường yêu cầu đường dẫn thực sự tồn tại. Nó cũng **không tạo tài nguyên**.
- Nếu chuỗi đường dẫn do người dùng cung cấp, phải kiểm tra phạm vi truy cập được cho phép ở ứng dụng; việc tạo `File` không đảm bảo đường dẫn an toàn hoặc nằm trong thư mục dự kiến.

## 10. Thư mục cha chưa tồn tại: lỗi thường gặp

Đây là lỗi rất điển hình:

```java
File file = new File("reports/2026/summary.txt");
file.createNewFile();
```

Nếu `reports/2026` chưa tồn tại, `createNewFile()` không có trách nhiệm tạo những thư mục đó; thao tác có thể ném `IOException`. Khi bài toán yêu cầu tạo file nằm trong cấu trúc thư mục mới, cần:

1. Xác định đúng đường dẫn cha.
2. Tạo/công nhận các thư mục cha bằng `mkdirs()` hoặc `Files.createDirectories(...)`.
3. Tạo file thực bằng `createNewFile()`/`Files.createFile(...)` hoặc mở stream với tùy chọn mong muốn.
4. Ghi nội dung và đóng tài nguyên, rồi kiểm tra kết quả hoặc xử lý ngoại lệ.

Ví dụ NIO:

```java
Path target = Path.of("reports", "2026", "summary.txt");
Files.createDirectories(target.getParent());
Files.writeString(target, "Báo cáo",
        StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
```

Đây là **mảnh mã**; cần `java.nio.file.*`, `java.nio.charset.StandardCharsets` và xử lý `IOException`. `StandardOpenOption.CREATE_NEW` yêu cầu tạo file mới và thất bại nếu đường dẫn đã có; cách viết này giúp tránh ghi đè dữ liệu hiện có. Nó khác hành vi mặc định của `Files.writeString` khi không có tùy chọn.

Nếu bạn chỉ muốn “tạo file rỗng và chắc chắn không ghi đè”, dùng `Files.createFile(target)` sau khi đã chuẩn bị thư mục cha. Nếu muốn “mở file để ghi và có thể ghi đè”, chọn rõ `CREATE`/`TRUNCATE_EXISTING` theo hợp đồng nghiệp vụ.

## 11. Kiểm tra tồn tại trước khi tạo không phải một transaction

Mã này có vấn đề nếu hai tiến trình đồng thời chạy:

```java
if (!file.exists()) {
    // Giữa hai dòng, tiến trình khác có thể tạo file cùng tên.
    Files.writeString(file.toPath(), "content",
            StandardCharsets.UTF_8);
}
```

Bên khác có thể tạo file **sau** `exists()` nhưng **trước** `writeString(...)`. Khi đó, vì cách ghi mặc định có thể truncate file hiện hữu, chương trình có nguy cơ ghi đè nội dung không thuộc về nó.

Nếu yêu cầu chỉ tạo khi chưa tồn tại, dùng thao tác create-new:

```java
try {
    Files.writeString(file.toPath(), "content",
            StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
} catch (FileAlreadyExistsException e) {
    // Xử lý trạng thái tên file đã được sử dụng.
}
```

Đây là mảnh mã cần import `java.nio.file.*`, `java.nio.charset.StandardCharsets`; vẫn phải xử lý các `IOException` khác.

`File.createNewFile()` cũng kết hợp kiểm tra và tạo file rỗng theo hợp đồng nguyên tử. Nhưng sau khi tạo file rỗng, nếu chương trình đóng mở lại để ghi, tiến trình khác vẫn có thể thay đổi filesystem trong khoảng đó. Muốn an toàn hơn, lựa chọn mở bằng `CREATE_NEW` để giữ đúng yêu cầu tạo và ghi ngay trong cùng thao tác mở phù hợp với provider.

Không dùng file tồn tại/không tồn tại để tạo cơ chế khóa liên tiến trình tự chế. Java có `FileLock` và những cơ chế phối hợp phù hợp hơn; ngay cả thao tác tạo mới nguyên tử cũng không thay thế được mọi yêu cầu đồng bộ/quyền truy cập.

## 12. Xóa đối tượng File không xóa tệp vật lý

Một nhầm lẫn ngược lại cũng rất phổ biến:

```java
File f = new File("report.txt");
f = null;
```

Việc bỏ tham chiếu tới `File` hoặc để đối tượng được garbage collector thu gom **không xóa file trên đĩa**, không đóng một luồng mở độc lập và không tác động lên đường dẫn thực. Tài nguyên file được thay đổi bởi những thao tác I/O cụ thể như `delete()`, `Files.delete(...)` hoặc ghi/move tương ứng.

Ví dụ:

```java
File f = new File("report.txt");
boolean deleted = f.delete();
```

`delete()` mới yêu cầu xóa mục tương ứng và trả `boolean`. Nó có thể thất bại, và không xóa đệ quy thư mục không rỗng. Với NIO, `Files.delete(path)` hoặc `Files.deleteIfExists(path)` cung cấp thao tác xóa phù hợp và có thể báo lỗi chi tiết hơn.

Cũng không nên gọi `deleteOnExit()` rồi nghĩ rằng tài nguyên đã bị xóa ngay. Đây chỉ là **yêu cầu xóa lúc JVM kết thúc bình thường**, không thay cho vòng đời tài nguyên và kiểm tra lỗi của thao tác xóa thực.

## 13. Tài nguyên và quyền sở hữu khi mở stream

Đối tượng `File` thường không cần `close()`, vì nó chỉ biểu diễn đường dẫn và bản thân không có phương thức `close()`. Nhưng các stream/reader/channel dùng để thao tác dữ liệu thật thường phải đóng:

```java
File f = new File("input.txt");
try (FileInputStream in = new FileInputStream(f)) {
    int firstByte = in.read();
    // Xử lý firstByte; -1 nghĩa EOF.
}
```

Đây là mảnh mã cần `java.io.*`, xử lý `IOException`. Constructor `FileInputStream` mở tài nguyên để **đọc** và có thể ném `FileNotFoundException` khi file không tồn tại/không thể đọc; **nó không tự tạo file bị thiếu**.

Ngược lại, constructor `FileOutputStream` dùng để **ghi** có thể tạo file mới. Vì vậy hai tên lớp gần giống nhau có hành vi tạo file khác nhau. Từ `new File(...)` không suy ra rằng file được mở cho đọc hoặc ghi.

Đặt try-with-resources quanh stream/reader để giải phóng handle ngay cả khi gặp ngoại lệ. Không cần tự ý đóng tài nguyên hệ thống dùng chung do thành phần khác sở hữu.

## 14. Chọn File hay Path/Files?

`java.io.File` vẫn phổ biến khi tương tác với API cũ, thư viện yêu cầu `File` hoặc khi học nền tảng I/O. Nhưng Java NIO có `java.nio.file.Path` và lớp tiện ích `Files` cung cấp các thao tác file rõ ràng hơn:

| Nhiệm vụ | java.io.File truyền thống | Java NIO |
| --- | --- | --- |
| Biểu diễn đường dẫn, chưa tạo tài nguyên | `new File("data.txt")` | `Path.of("data.txt")` |
| Kiểm tra tồn tại | `file.exists()` | `Files.exists(path)` |
| Kiểm tra file thường | `file.isFile()` | `Files.isRegularFile(path)` |
| Tạo file rỗng mới | `file.createNewFile()` | `Files.createFile(path)` |
| Tạo một thư mục | `file.mkdir()` | `Files.createDirectory(path)` |
| Tạo cả cây thư mục cha | `file.mkdirs()` | `Files.createDirectories(path)` |
| Ghi văn bản UTF-8 | `FileWriter` với charset phù hợp | `Files.writeString(path, text, UTF_8)` |
| Xóa đường dẫn | `file.delete()` | `Files.delete(path)` |
| Chuyển giữa hai loại | `file.toPath()` | `path.toFile()` trên default filesystem |

`Files.exists(...)` và các thao tác thăm dò NIO cũng có giới hạn về race/quyền truy cập. Khi thao tác cần phân biệt nguyên nhân thất bại, các phương thức NIO ném `IOException` cụ thể thường hữu ích hơn những boolean của `File`.

Một lý do khác để chọn NIO là quyền truy cập filesystem/metadata, đường dẫn biểu diễn symbolic link và các thao tác nâng cao có API chuyên biệt. Dù dùng loại nào, **đối tượng đường dẫn luôn khác với việc tạo tài nguyên trên ổ đĩa**.

## 15. Những lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `new File("a.txt")` rồi cho rằng `a.txt` đã tồn tại | Đọc/ghi thất bại khi file thiếu | Thực hiện thao tác tạo hoặc mở ghi phù hợp |
| Dựa vào `getAbsolutePath()` như bằng chứng file đã có | Nhầm chuỗi tên với trạng thái filesystem | `exists()`/`isFile()` khi cần thông tin tức thời |
| Dùng `createNewFile()` trên đường dẫn thiếu thư mục cha | Có thể ném `IOException` | `mkdirs()` / `Files.createDirectories(...)` trước |
| Dùng `mkdirs()` để tạo file văn bản | Tạo thư mục thay vì file | Tạo thư mục cha rồi tạo file thường |
| Bỏ qua boolean từ `createNewFile()` | Không biết file đã có hay mới tạo | Kiểm tra `true`/`false` hoặc dùng `Files.createFile` |
| Dùng `exists() == true` thay cho `isFile()` | Có thể xử lý thư mục như file | Kiểm tra loại hoặc để API đọc/ghi xác thực |
| Dùng `exists() == false` rồi ghi mặc định | Dễ race và có thể ghi đè file của tiến trình khác | `CREATE_NEW` hoặc tạo mới nguyên tử |
| Dùng `Files.writeString` mà không biết mặc định | Có thể truncate dữ liệu cũ | Chọn `CREATE_NEW`/`APPEND`/`TRUNCATE_EXISTING` theo yêu cầu |
| Cho rằng `FileInputStream` tạo file còn thiếu | Ném lỗi khi mở file để đọc | Tạo tài nguyên trước nếu nghiệp vụ đòi hỏi |
| Cho rằng `new FileOutputStream` chỉ tạo đối tượng trong bộ nhớ | Có thể tạo/truncate file thật ngay lúc mở | Quản lý đường dẫn và tuỳ chọn ghi rõ ràng |
| Quên đóng stream sau khi mở tệp | Rò handle và tài nguyên | Dùng try-with-resources |
| Xóa tham chiếu `File` rồi cho rằng file đã bị xóa | File thực vẫn tồn tại | Gọi `delete()`/`Files.delete(...)` nếu cần xóa |
| Dùng đường dẫn tương đối nhưng tưởng nằm cạnh source code | Đọc/ghi sai vị trí | Kiểm tra thư mục làm việc, dùng `Path`/đường dẫn tuyệt đối khi cần |
| Dùng boolean tồn tại làm kiểm tra an toàn cuối cùng | Kết quả có thể lỗi thời do race | Thao tác mở/tạo trực tiếp với error handling |
| Không kiểm tra ngoại lệ/quyền filesystem | Ghi báo thành công giả | Xử lý `IOException`, xác minh thao tác đã hoàn tất |

## 16. Câu hỏi tự kiểm tra

1. **`new File("hello.txt")` có tạo file rỗng trên ổ đĩa không?** Không. Nó tạo đối tượng đường dẫn.
2. **`File` có thể trỏ tới thư mục không?** Có. Dùng `isDirectory()` để thăm dò loại tài nguyên.
3. **Nếu file chưa tồn tại, `getAbsolutePath()` có trả đường dẫn được không?** Có. Nó tạo dạng đường dẫn tuyệt đối, không tạo file.
4. **`createNewFile()` trả gì nếu file đã có?** Trả `false`, không ghi đè nội dung.
5. **`Files.createFile(path)` khác gì khi file đã có?** Thường ném `FileAlreadyExistsException`.
6. **`mkdir()` và `mkdirs()` khác nhau như thế nào?** `mkdir()` tạo một cấp thư mục, `mkdirs()` cố tạo cả các thư mục cha cần thiết.
7. **Vì sao `new File("a/b/c.txt").createNewFile()` có thể thất bại?** Vì thư mục cha `a/b` chưa có hoặc không thể truy cập.
8. **`new FileOutputStream(file)` có thể tạo file mới không?** Có, khi mở đích ghi với đường dẫn/quyền hợp lệ; nếu đã có có thể truncate.
9. **`new FileInputStream(file)` có tự tạo file thiếu không?** Không. Đây là thao tác đọc, có thể báo `FileNotFoundException`.
10. **Có nên kiểm tra `!exists()` rồi gọi `Files.writeString` để bảo đảm không ghi đè?** Không. Có race. Dùng `CREATE_NEW` khi yêu cầu chỉ tạo mới.
11. **`File` bị garbage collector thu gom có xóa file thật không?** Không.
12. **Tạo file tạm bằng `File.createTempFile(...)` có tạo tệp vật lý không?** Có. Đây là factory thực hiện thao tác tạo, khác với constructor `new File(...)`.

## Nguồn API Java 17

- [`java.io.File`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html): constructor, `createNewFile`, `mkdir`, `mkdirs`, `exists`, `delete`.
- [`java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): biểu diễn và thao tác đường dẫn.
- [`java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): tạo/ghi/đọc/xóa tệp và thư mục.
- [`java.nio.file.StandardOpenOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `CREATE`, `APPEND` và `TRUNCATE_EXISTING`.
- [`java.io.FileOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileOutputStream.html): mở và ghi luồng byte, có thể tạo file.
- [`java.io.FileInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileInputStream.html): mở và đọc luồng byte.
- [`java.io.IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): xử lý lỗi khi thao tác filesystem.

**Ghi nhớ:** `new File(path)` chỉ nói với JVM **đường dẫn nào đang được nhắc đến**. `createNewFile()`, `mkdir()/mkdirs()`, `Files.createFile(...)`, `Files.writeString(...)` và các thao tác mở ghi mới là những hành động có thể **tạo hoặc thay đổi tài nguyên thật trên hệ thống tệp**. Chọn đúng thao tác theo việc cần tạo file, tạo thư mục, chỉ đọc, ghi mới hay ghi đè và luôn xử lý lỗi I/O.
