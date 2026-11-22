# Giới hạn thông tin lỗi của API trả về boolean trong java.io.File

Trong Java I/O truyền thống, nhiều phương thức của **`java.io.File`** chỉ trả về `boolean`: `delete()`, `mkdir()`, `mkdirs()`, `renameTo()`, `setLastModified()`, `setReadable()`, `setWritable()`, `setExecutable()` và `setReadOnly()`. Một số phương thức kiểm tra trạng thái như `exists()`, `isFile()`, `isDirectory()`, `canRead()` cũng trả về boolean.

Thiết kế này giúp câu lệnh ngắn gọn, nhưng **một giá trị `false` không đủ để biết tại sao thao tác thất bại**. Chẳng hạn, `file.delete() == false` có thể có nghĩa đường dẫn không tồn tại, thư mục không rỗng, quyền truy cập không đủ hoặc hệ thống tập tin đang gặp trở ngại. `false` chỉ báo thao tác không thành công theo hợp đồng, **không chứa `IOException`, error code, nguyên nhân hoặc stack trace từ hệ điều hành**.

Khi cần xử lý lỗi rõ ràng, Java cung cấp **`java.nio.file.Files`** với các phương thức như `Files.delete`, `Files.createDirectory`, `Files.move` hoặc `Files.readAttributes`. Nhiều phương thức này ném `IOException` hoặc lớp con cụ thể, cung cấp tín hiệu chẩn đoán tốt hơn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **boolean cho kết quả thao tác**, **boolean để kiểm tra trạng thái**, và **ngoại lệ I/O**.
- Chỉ ra vì sao `File.delete()`, `mkdir()`, `mkdirs()` và `renameTo()` thường không cung cấp đủ thông tin nguyên nhân khi trả `false`.
- Nhận diện ngoại lệ đặc biệt: `File.createNewFile()` cũng trả boolean nhưng **ném `IOException` khi lỗi I/O xảy ra**.
- Viết cách xử lý tương đương bằng `Files.delete`, `Files.deleteIfExists`, `Files.createDirectory`, `Files.createDirectories` và `Files.move`.
- Phân biệt tình trạng “không tồn tại” với “không xác định được” ở các API kiểm tra `Files.exists`/`Files.notExists`.
- Tránh **TOCTOU** (*time-of-check to time-of-use*): kiểm tra trước không bảo đảm thao tác sau thành công.
- Viết log thông tin lỗi vừa đủ, bảo toàn nguyên nhân, và quyết định retry hoặc báo thất bại phù hợp.
- Hiểu hạn chế về quyền truy cập, symbolic link, thư mục không rỗng và tính phụ thuộc nền tảng của file API.

## 2. `java.io.File` đại diện cho đường dẫn, không phải một file đã mở

`File` biểu diễn **abstract pathname**: đường dẫn tới một file hoặc thư mục tiềm năng. Tạo đối tượng `File` không tự tạo file, không tự mở file và không chứng minh đối tượng thực sự tồn tại:

~~~java
java.io.File file = new java.io.File("reports/output.txt");
~~~

Dòng trên chỉ tạo đối tượng mô tả đường dẫn. Khi gọi `file.exists()` hoặc `file.delete()`, phương thức mới truy vấn/yêu cầu thao tác trên hệ thống tập tin.

Các phương thức boolean legacy có **những ý nghĩa khác nhau**, không thể gom mọi kết quả `false` thành “I/O bị lỗi”:

| Nhóm | Phương thức | `true` thường có nghĩa | `false` có thể là |
| --- | --- | --- | --- |
| Thao tác xóa | `delete()` | Đã xóa file/thư mục | Không tìm thấy hoặc không xóa được vì lý do khác |
| Tạo thư mục đơn | `mkdir()` | Tạo thư mục đích thành công | Đã tồn tại, cha không tồn tại, thiếu quyền hoặc lỗi |
| Tạo nhiều cấp | `mkdirs()` | Đã tạo thư mục cần thiết theo hợp đồng trả về | Thư mục đích đã tồn tại hoặc không tạo được; có thể đã tạo một số thư mục cha |
| Đổi tên/di chuyển | `renameTo(dest)` | Đổi tên theo provider/nền tảng đã thành công | Thất bại vì nhiều nguyên nhân; không có `IOException` chi tiết |
| Thay metadata | `setLastModified(...)`, `setReadOnly()`, `setWritable(...)`... | Thao tác cập nhật thành công | Thiếu quyền, nền tảng không hỗ trợ, đường dẫn không phù hợp... |
| Kiểm tra tồn tại | `exists()` | Đường dẫn tồn tại tại thời điểm kiểm tra | Đường dẫn không tồn tại hoặc truy vấn không xác định chính xác trạng thái |
| Kiểm tra loại | `isFile()`, `isDirectory()` | Đúng loại tương ứng tại lúc kiểm tra | Không tồn tại, loại khác hoặc không xác định chắc chắn |
| Kiểm tra quyền | `canRead()`, `canWrite()`, `canExecute()` | Ứng dụng được báo là có khả năng tương ứng | Không tồn tại, không có quyền hoặc không xác định chắc chắn |

Nhóm **thao tác** thường dùng boolean để báo thành công/thất bại. Nhóm **kiểm tra** dùng boolean để mô tả một đặc tính tại thời điểm hỏi. Phải đọc riêng hợp đồng của từng API: ví dụ `isDirectory()==false` **không khẳng định** rằng file tồn tại và là file thường.

## 3. Ví dụ: `File.delete() == false` không nói lý do

Theo hợp đồng `File.delete()`, giá trị `true` nghĩa là file/thư mục được xóa thành công; `false` nghĩa là không xóa được. Một số khả năng khi false:

1. Đường dẫn không tồn tại.
2. Đường dẫn chỉ đến một thư mục còn chứa mục con.
3. Quyền xóa trên thư mục cha hoặc chính sách hệ thống tập tin không cho phép.
4. File đang được sử dụng theo cách khiến nền tảng không cho xóa.
5. File system/thiết bị không sẵn sàng, lỗi I/O hoặc các giới hạn khác.

**Chỉ từ `false` bạn không thể kết luận nguyên nhân nào đã xảy ra.** Nếu sau đó gọi `exists()` và thấy `false` cũng không chứng minh file vốn đã thiếu: tác vụ khác có thể vừa xóa nó hoặc quyền truy vấn có thể khác.

### Java 17: tái hiện trường hợp không tồn tại

Tạo file **`BooleanDeleteDemo.java`**:

~~~java
import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class BooleanDeleteDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("boolean-delete-");
        Path missing = root.resolve("never-created.txt");
        File legacy = missing.toFile();

        try {
            System.out.println("File.delete=" + legacy.delete());

            try {
                Files.delete(missing);
                System.out.println("unexpected success");
            } catch (NoSuchFileException exception) {
                System.out.println("Files.delete="
                        + exception.getClass().getSimpleName());
            }

            System.out.println("Files.deleteIfExists="
                    + Files.deleteIfExists(missing));
        } finally {
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 BooleanDeleteDemo.java
java BooleanDeleteDemo
~~~

Kết quả khi không có tác nhân ngoài can thiệp vào thư mục tạm:

~~~text
File.delete=false
Files.delete=NoSuchFileException
Files.deleteIfExists=false
~~~

Cùng tình huống thiếu file, ba API báo kết quả theo ba **hợp đồng khác nhau**:

- `File.delete()` → `false`, không có lý do được truyền lên.
- `Files.delete(path)` → ném `NoSuchFileException` (một dạng `FileSystemException`/`IOException`).
- `Files.deleteIfExists(path)` → `false` vì file không tồn tại; tuy vẫn trả boolean, phương thức **có thể ném `IOException` cho lỗi xóa**. Đây là lựa chọn phù hợp nếu nghiệp vụ coi “đã không còn file” là kết quả chấp nhận được.

`Files.deleteIfExists` không cam kết tính nguyên tử tuyệt đối trong mọi hệ thống tập tin; kiểm tra/xóa và các thao tác khác vẫn có thể tương tác với nhau.

## 4. Ví dụ: thư mục không rỗng cho thấy lợi ích của ngoại lệ cụ thể

Khi muốn xóa một thư mục, `File.delete()` chỉ xóa được nếu thư mục rỗng. Nếu thư mục còn file con, nó thường trả `false` mà không cho biết lý do cụ thể.

Tạo file **`NonEmptyDirectoryDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.Files;
import java.nio.file.Path;

public class NonEmptyDirectoryDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("nonempty-");
        Path child = Files.createFile(directory.resolve("item.txt"));

        try {
            System.out.println("legacyDelete="
                    + directory.toFile().delete());

            try {
                Files.delete(directory);
                System.out.println("unexpected success");
            } catch (DirectoryNotEmptyException exception) {
                System.out.println("nioDelete="
                        + exception.getClass().getSimpleName());
            }
        } finally {
            Files.deleteIfExists(child);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NonEmptyDirectoryDemo.java
java NonEmptyDirectoryDemo
~~~

Kết quả điển hình trên hệ thống tập tin thông thường:

~~~text
legacyDelete=false
nioDelete=DirectoryNotEmptyException
~~~

`DirectoryNotEmptyException` là **ngoại lệ cụ thể được API cho phép**, nhưng không phải mọi file system provider đều buộc phải dùng đúng lớp con này: đặc tả Java đánh dấu một số ngoại lệ đặc thù của `Files.delete` là *optional specific exception*. Một provider vẫn có thể báo `IOException` tổng quát. Vì thế:

- Bắt `DirectoryNotEmptyException` để xử lý trường hợp đó khi provider cung cấp.
- Bắt hoặc cho phép lan truyền `IOException` cho các lỗi còn lại.
- Không kết luận mọi lỗi xóa thư mục không rỗng nhất định luôn có đúng kiểu exception như ví dụ.

Một ứng dụng thực tế **không tự động xóa hết thư mục con** chỉ vì thấy thư mục chưa rỗng. Việc xóa đệ quy là một quyết định có tính phá hủy khác, cần xác nhận phạm vi rõ ràng.

## 5. `mkdir()` và `mkdirs()`: false có thể là “đã tồn tại”

Xem hai lần gọi trên cùng đường dẫn:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class DirectoryBooleanDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("mkdir-demo-");
        Path child = root.resolve("cache");

        try {
            System.out.println("first=" + child.toFile().mkdir());
            System.out.println("second=" + child.toFile().mkdir());
            System.out.println("isDirectory=" + Files.isDirectory(child));
        } finally {
            Files.deleteIfExists(child);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DirectoryBooleanDemo.java
java DirectoryBooleanDemo
~~~

Output trong môi trường bình thường, không có thay đổi đồng thời:

~~~text
first=true
second=false
isDirectory=true
~~~

Lần đầu tạo thành công, lần thứ hai trả `false` vì đích **đã là thư mục**. Đây không nhất thiết là lỗi nghiệp vụ: nếu mục tiêu “bảo đảm thư mục tồn tại”, trạng thái hiện tại là hợp lệ.

### Khác nhau giữa `mkdir` và `mkdirs`

- `mkdir()` chỉ cố tạo **thư mục cuối cùng**; các thư mục cha phải tồn tại.
- `mkdirs()` cũng cố tạo các **thư mục cha còn thiếu**.
- Cả hai có thể trả `false` nếu không tạo được thư mục hoặc thư mục đích đã tồn tại.
- `mkdirs()` có thể tạo thành công **một phần cây thư mục** trước khi thất bại; không giả định false nghĩa là không có thay đổi nào trên đĩa.

Đối chiếu NIO:

~~~java
Path dir = Path.of("data", "archive");

Files.createDirectory(dir);   // Tạo đúng một cấp; có thể ném IOException.
Files.createDirectories(dir); // Tạo các cấp còn thiếu; nếu đã là thư mục, thành công.
~~~

Đây là **mảnh mã** cần `import java.nio.file.Files;`, `Path` và xử lý `IOException`. Không nên gọi hai lệnh liên tiếp như trên trong cùng bài toán nếu không có lý do; chúng thể hiện hai chiến lược khác nhau.

`Files.createDirectory` có thể ném `FileAlreadyExistsException` khi đích đã tồn tại; `Files.createDirectories` hỗ trợ yêu cầu “thư mục cuối cùng phải tồn tại”, nhưng nếu đường dẫn tồn tại mà là một file không phải thư mục, hoặc không đủ quyền, vẫn sẽ lỗi. Việc tạo nhiều cấp không bảo đảm toàn bộ chuỗi tạo thư mục là một transaction nguyên tử.

## 6. `renameTo()`: trường hợp false khó chẩn đoán hơn

`File.renameTo(File dest)` có hợp đồng phụ thuộc nền tảng: có hệ thống không đổi tên được khi nguồn/đích nằm ở file system khác, hoặc không thay thế được đích có sẵn, hoặc có quy tắc riêng khi file đang mở. Theo Java API, nhiều khía cạnh như liệu thao tác di chuyển giữa các file system có thành công, liệu thao tác có tính nguyên tử, và xử lý đích tồn tại phụ thuộc nền tảng.

~~~java
File source = new File("old.txt");
File destination = new File("new.txt");

if (!source.renameTo(destination)) {
    // Không biết chắc: nguồn không tồn tại, đích xung đột,
    // sai quyền, khác file system hay một vấn đề khác.
}
~~~

Đây là **mảnh mã** cần import `java.io.File`. Không được tự lập trình kiểu “thử lại không giới hạn” trên `false`, vì không rõ điều kiện sẽ biến mất hay thao tác đã có tác dụng một phần.

Với NIO:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class MoveExample {
    private MoveExample() {}

    public static Path replace(Path source, Path destination)
            throws IOException {
        return Files.move(source, destination,
                StandardCopyOption.REPLACE_EXISTING);
    }
}
~~~

Đây là lớp có thể biên dịch (không có `main`), với việc **cho phép thay thế đích** là lựa chọn nghiệp vụ chủ động. `Files.move` có thể ném `IOException`; thao tác `REPLACE_EXISTING` **không tự hứa nguyên tử** hoặc bảo toàn mọi thuộc tính trên mọi provider.

Nếu cần atomic move, có thể yêu cầu `StandardCopyOption.ATOMIC_MOVE`, nhưng phải xử lý `AtomicMoveNotSupportedException` nếu provider không hỗ trợ. Không âm thầm bỏ yêu cầu atomic mà không đánh giá tính nhất quán dữ liệu. Với move qua file system khác, triển khai có thể phải copy rồi delete nên phải cân nhắc lỗi, dữ liệu dở dang và bước rollback.

## 7. Một ngoại lệ quan trọng: `File.createNewFile()` không chỉ trả boolean

Không nên phát biểu “mọi phương thức `File` trả boolean đều nuốt lỗi I/O”. `File.createNewFile()` **vừa trả boolean vừa khai báo `throws IOException`**:

~~~java
boolean created = file.createNewFile();
~~~

Ý nghĩa:

- `true`: file mới đã được tạo thành công.
- `false`: tên đích đã có file/đường dẫn tồn tại tại thời điểm thực hiện thao tác tạo.
- `IOException`: lỗi I/O khi cố tạo file.

Tài liệu cũng quy định phép kiểm tra tên chưa tồn tại và tạo file mới là **một thao tác nguyên tử** so với các hoạt động liên quan trên file system, trong phạm vi hợp đồng của API.

### Java 17: phân biệt đã tồn tại và thất bại I/O

Tạo file **`CreateNewFileDemo.java`**:

~~~java
import java.io.File;
import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreateNewFileDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("create-new-");
        Path path = root.resolve("report.txt");
        File file = path.toFile();

        try {
            System.out.println("first=" + file.createNewFile());
            System.out.println("second=" + file.createNewFile());

            try {
                Files.createFile(path);
                System.out.println("unexpected success");
            } catch (FileAlreadyExistsException exception) {
                System.out.println("nio=" +
                        exception.getClass().getSimpleName());
            }
        } finally {
            Files.deleteIfExists(path);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Chạy:

~~~bash
javac CreateNewFileDemo.java
java CreateNewFileDemo
~~~

Kết quả trên file system thông thường:

~~~text
first=true
second=false
nio=FileAlreadyExistsException
~~~

Vì thế khi review code, phải hỏi **boolean này có ý nghĩa gì và phương thức còn khai báo exception nào?** `File.createNewFile()` vẫn cung cấp `IOException` cho lỗi I/O, khác với `File.mkdir()`/`File.delete()`.

Tương tự, `Files.deleteIfExists` cũng trả boolean nhưng **không giấu tất cả lỗi**: nếu file không tồn tại thì false, còn xóa không thành công có thể ném `IOException`.

## 8. Giá trị `false` từ phương thức *kiểm tra* cũng có giới hạn

### `exists()`, `isFile()` và `isDirectory()`

~~~java
File candidate = new File("incoming/data.bin");

if (!candidate.isFile()) {
    // Chưa đủ để nói "file không tồn tại".
}
~~~

`isFile()==false` có thể là vì đích là thư mục, đường dẫn chưa tồn tại, hoặc không thể xác định chính xác. `isDirectory()==false` cũng không chứng minh đích là file thường.

Một số API truy vấn dưới `java.nio.file.Files` **vẫn trả boolean** và cũng có thể không phân biệt lý do nếu trạng thái không xác định:

~~~java
boolean present = Files.exists(path);
boolean absent = Files.notExists(path);
~~~

**`Files.notExists(path)` không phải đơn giản là `!Files.exists(path)`.** Có ba nhóm kết quả cần phân biệt:

| `Files.exists(path)` | `Files.notExists(path)` | Diễn giải |
| --- | --- | --- |
| `true` | `false` | Xác định được file tồn tại tại thời điểm hỏi |
| `false` | `true` | Xác định được file không tồn tại tại thời điểm hỏi |
| `false` | `false` | Không xác định được trạng thái tồn tại hoặc không tồn tại |

Hai phép kiểm tra là **hai thao tác riêng theo thời gian**, nên khi file system thay đổi đồng thời, cặp giá trị đọc thực tế có thể không phản ánh một snapshot nhất quán. Bảng diễn giải điều kiện trạng thái ổn định tại lúc truy vấn và không thể thay thế bằng khóa/giao dịch file system.

Khi cần một lỗi cụ thể (ví dụ tồn tại nhưng không đọc được metadata), gọi API như `Files.readAttributes(path, BasicFileAttributes.class)`; nó có thể ném `IOException`/`NoSuchFileException` thay vì chỉ trả false.

### `canRead()`, `canWrite()`, `canExecute()`

Các phép kiểm tra quyền mô tả khả năng được ghi nhận ở một thời điểm, **không phải bảo đảm** lần mở file kế tiếp sẽ thành công:

- Quyền file/ACL có thể đổi.
- File có thể bị xóa hoặc thay thế.
- File system có thể có chính sách khác tùy loại hoạt động.
- Hệ điều hành có thể áp đặt chế độ chia sẻ/khóa hoặc các giới hạn khác.
- Symbolic link có thể trỏ sang mục khác.

Nên **thực hiện thao tác thực sự** (`Files.newInputStream`, `Files.newOutputStream`, `Files.readAttributes`...) và xử lý `IOException`, thay vì dùng `canRead() == true` như chứng nhận tương lai.

## 9. TOCTOU: “kiểm tra trước” không sửa được nhược điểm của boolean

Cách thường gặp:

~~~java
if (file.exists()) {
    if (!file.delete()) {
        // ...
    }
}
~~~

Có hai vấn đề độc lập:

1. `delete()==false` vẫn không cho biết nguyên nhân.
2. **Race condition**: file có thể bị xóa, thay thế hoặc thay đổi quyền ngay sau `exists()` và trước `delete()`.

Tương tự:

~~~java
if (!Files.exists(target)) {
    Files.createFile(target); // Vẫn có thể lỗi vì ai đó đã tạo trước.
}
~~~

Ngay cả khi `Files.exists(target)` trả false, điều đó **không chứng minh** file chưa tồn tại; trạng thái có thể không xác định. Và kể cả xác định được không tồn tại, kết quả đã có thể lỗi thời.

**Cách tốt hơn:** dùng thao tác trực tiếp có hợp đồng phù hợp:

- “Phải xóa file, nếu không có thì báo lỗi” → `Files.delete(path)`.
- “Đảm bảo sau thao tác file không còn, thiếu file được chấp nhận” → `Files.deleteIfExists(path)`, xử lý `IOException` khi không xóa được.
- “Tạo file mới và không được ghi đè” → `Files.createFile(path)` hoặc `CREATE_NEW`.
- “Đảm bảo thư mục tồn tại” → `Files.createDirectories(path)`.
- “Di chuyển file, cần xử lý xung đột/lỗi chi tiết” → `Files.move(...)` với options phù hợp.

API mạnh hơn giúp phân biệt lỗi, nhưng **không làm biến mất mọi race condition**. Đặc biệt với yêu cầu bảo mật liên quan symlink, quyền hoặc cây thư mục có người khác sửa, cần dùng API/thao tác và thiết kế có tính nguyên tử cần thiết thay vì nối nhiều bước kiểm tra mong manh.

## 10. `list()` và `listFiles()`: còn có trường hợp trả về `null`

Không phải API truyền thống nào thất bại cũng trả boolean. `File.list()` và `File.listFiles()` trả mảng, nhưng có thể trả **`null`** nếu đường dẫn không chỉ đến thư mục hoặc lỗi I/O xảy ra trong quá trình liệt kê.

~~~java
File directory = new File("reports");
File[] entries = directory.listFiles();

if (entries == null) {
    // Không được giả định "thư mục rỗng".
    // Có thể không phải thư mục hoặc đã gặp lỗi đọc.
} else {
    for (File entry : entries) {
        System.out.println(entry.getName());
    }
}
~~~

`entries.length == 0` mới là mảng rỗng được trả từ thao tác liệt kê thành công; `entries == null` là trường hợp khác.

Khi cần chẩn đoán tốt hơn, dùng:

~~~java
try (java.nio.file.DirectoryStream<java.nio.file.Path> entries =
             java.nio.file.Files.newDirectoryStream(path)) {
    for (java.nio.file.Path entry : entries) {
        System.out.println(entry.getFileName());
    }
}
~~~

Đây là **mảnh mã**, cần biến `path` kiểu `Path` và xử lý `IOException`. `DirectoryStream` là tài nguyên phải đóng; lỗi duyệt có thể xuất hiện dưới dạng `DirectoryIteratorException` (bọc nguyên nhân `IOException`), khác với lỗi lúc mở stream. Không mặc định danh sách trả về theo thứ tự cố định.

`Files.list(path)` cũng tạo `Stream<Path>` cần đóng bằng `try-with-resources`; lỗi khi duyệt lazy có thể được bọc trong `UncheckedIOException`. Đây là một sắc thái khác: dùng NIO không có nghĩa toàn bộ API đều truyền đúng một loại exception hoặc không cần quản lý tài nguyên.

## 11. Xử lý ngoại lệ chi tiết: điều gì có thể quan sát được?

Các thao tác NIO điển hình có thể báo:

- `NoSuchFileException`: đường dẫn/file cần thiết không tồn tại.
- `FileAlreadyExistsException`: đích đã tồn tại khi thao tác không cho phép.
- `DirectoryNotEmptyException`: thư mục không rỗng khi yêu cầu xóa.
- `AccessDeniedException`: không đủ quyền/truy cập bị từ chối.
- `AtomicMoveNotSupportedException`: provider không hỗ trợ di chuyển nguyên tử được yêu cầu.
- `FileSystemException`: thông tin liên quan đến file, file khác và lý do (khi provider cung cấp).
- `IOException` chung: một lỗi I/O khác hoặc provider không báo bằng lớp con cụ thể.

Các lớp con đặc thù không luôn được bảo đảm với mọi provider/OS. Hãy xử lý ngoại lệ cụ thể mà ứng dụng thực sự cần phân biệt rồi để `IOException` bao quát trường hợp còn lại.

### Mẫu log/biểu diễn lỗi có thông tin

~~~java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public final class DeleteWithReason {
    private DeleteWithReason() {}

    public static void deleteRequired(Path path) throws IOException {
        try {
            Files.delete(path);
        } catch (NoSuchFileException exception) {
            throw new IOException("Required file is missing: " + path,
                    exception);
        } catch (AccessDeniedException exception) {
            throw new IOException("Cannot delete due to access policy: "
                    + path, exception);
        }
    }
}
~~~

Đây là lớp có thể biên dịch nhưng **không có `main`**. Nó minh họa cách giữ **cause** bằng constructor `IOException(message, cause)`, giúp log còn stack trace và thông tin nhà cung cấp gửi. Phương thức tiếp tục ném các `IOException` khác mà không đoán lý do.

Trong sản phẩm thật, tránh ghi đường dẫn nhạy cảm, tên tài khoản hoặc dữ liệu riêng vào log công khai. Chọn log level/structured logging theo mục đích; thêm path đã được xử lý phù hợp và nguyên nhân thực tế, không tạo thông điệp kiểu “permission denied” khi chỉ có `File.delete()==false`.

### Không “sửa” dữ liệu dựa trên một nguyên nhân phỏng đoán

Không nên:

~~~java
if (!file.delete()) {
    file.setWritable(true);
    file.delete();
}
~~~

Đây chỉ là **mảnh mã minh họa cách làm không an toàn**: không biết lý do thất bại, có thể thay đổi quyền file ngoài phạm vi mong muốn, vẫn không kiểm tra kết quả lần hai và có thể gây sai lệch bảo mật. Không sử dụng trong chương trình thật.

Nếu thao tác cần retry, phải xác định lỗi nào là tạm thời, giới hạn số lần và thời gian retry, kiểm soát tính idempotent, đồng thời tránh thay đổi permission hoặc xóa nhầm một file vừa bị thay thế.

## 12. Đặc điểm nền tảng: quyền, symbolic link và file system provider

### Quyền truy cập

Cùng một thao tác có thể thành công trên hệ thống này nhưng thất bại trên hệ thống khác. Đặc biệt, quyền xóa trên Unix-like thường liên quan tới **thư mục cha**, không đơn giản chỉ đọc bit writable của chính file. Trên Windows, file đang được mở với chế độ chia sẻ không phù hợp có thể bị từ chối xóa/di chuyển.

`File.setReadable/setWritable/setExecutable/setReadOnly` là API tiện lợi có mức độ biểu đạt hạn chế; khi cần quyền POSIX hoặc ACL, xem xét các API thuộc `java.nio.file.attribute` như `PosixFilePermissions`, `PosixFileAttributeView` hoặc `AclFileAttributeView` nếu file system hỗ trợ. Nên kiểm tra capability và xử lý lỗi thay vì giả định mọi OS đều có cùng mô hình permission.

### Symbolic link

Các API có những quy tắc riêng khi đụng symbolic link:

- Xóa **symbolic link** thông thường xóa chính link, không xóa target.
- Các truy vấn `Files.exists`/`isRegularFile` mặc định thường **theo link**; có thể dùng `LinkOption.NOFOLLOW_LINKS` ở nơi API hỗ trợ.
- Khi giải quyết đường dẫn trong thư mục do bên ngoài kiểm soát, symlink có thể thay đổi giữa các thao tác; nếu có rủi ro bảo mật, cần thiết kế hạn chế di chuyển qua đường dẫn và sử dụng cơ chế file-system an toàn phù hợp.

### File system provider

`Path`/`Files` hỗ trợ nhiều provider, không chỉ ổ đĩa local mặc định. Một provider có thể không hỗ trợ atomic move, view thuộc tính hoặc thao tác permission nhất định; ngoại lệ và thông điệp lỗi cũng có thể khác.

`File` truyền thống chủ yếu làm việc với hệ thống tập tin mặc định; `Path` mở rộng các khả năng NIO và thường có API thao tác chi tiết hơn. Chuyển từ `File` sang `Path` thông qua `file.toPath()` phù hợp khi dùng default provider; không giả định mọi `Path` có thể chuyển thành `File` (một số provider không hỗ trợ `toFile()`).

## 13. Kiểm thử đúng khi API báo boolean

Đừng kiểm thử bằng giả định “file bị khóa chắc chắn không xóa được” hoặc “đổi quyền sẽ gây AccessDenied trên mọi OS”. Kết quả như vậy có thể khác Windows/Linux, quyền tài khoản, mount và file system provider.

Ưu tiên các tình huống **kiểm soát được**:

1. File thiếu trong một thư mục tạm mới → `File.delete()` trả `false`; `Files.delete` có cơ hội báo `NoSuchFileException`.
2. Một thư mục con đã tồn tại → lần tạo `mkdir()` tiếp theo trả `false`, dù mục tiêu “thư mục tồn tại” đã đạt.
3. Một thư mục có file con → `File.delete()` không thể xóa trực tiếp; `Files.delete` báo lỗi, trên nhiều provider là `DirectoryNotEmptyException`.
4. File đã tồn tại → `File.createNewFile()` trả `false`; `Files.createFile` có thể báo `FileAlreadyExistsException`.
5. Với lỗi do quyền hoặc thiết bị, dùng file system giả lập/provider kiểm thử có thể chủ động phát sinh lỗi, hoặc integration test theo môi trường đã xác định; đừng ép lỗi hệ điều hành trên máy developer/CI bằng hành vi không ổn định.

Khi test logic nghiệp vụ, đừng chỉ assert boolean của API hệ thống. Hãy kiểm tra **trạng thái cuối** và rằng chương trình phân loại lỗi theo hợp đồng đã chọn; cleanup dữ liệu test bằng `try/finally` hoặc tài nguyên tạm mà test framework quản lý.

## 14. So sánh cách xử lý từng yêu cầu nghiệp vụ

| Yêu cầu | Legacy API | Cách NIO phù hợp | Tín hiệu lỗi |
| --- | --- | --- | --- |
| Xóa file bắt buộc có mặt | `file.delete()` | `Files.delete(path)` | `IOException`/lớp con |
| Xóa nếu có, thiếu file được chấp nhận | `file.delete()` + tự suy luận | `Files.deleteIfExists(path)` | `false` nếu không có; lỗi xóa có thể ném |
| Tạo một thư mục mới, đã tồn tại là lỗi | `file.mkdir()` | `Files.createDirectory(path)` | `FileAlreadyExistsException` (khi provider cung cấp) |
| Đảm bảo cây thư mục tồn tại | `file.mkdirs()` | `Files.createDirectories(path)` | Lỗi ném, phân biệt tồn tại loại khác |
| Di chuyển/đổi tên file | `file.renameTo(dest)` | `Files.move(source, target, options)` | `IOException`/options rõ |
| Xác định metadata thay vì boolean | `file.isFile()`/`isDirectory()` | `Files.readAttributes(path, ...)` | Có thể biết lỗi truy vấn |
| Liệt kê thư mục | `file.listFiles()` trả mảng hoặc `null` | `Files.newDirectoryStream`/`Files.list` | Có lỗi rõ hơn, cần đóng tài nguyên |
| Tạo mới file không ghi đè | `file.createNewFile()` | `Files.createFile(path)` | Legacy **cũng có IOException**; NIO có lớp con |

Không phải lúc nào NIO cũng là lựa chọn bắt buộc: nếu `false` đúng là thông tin duy nhất nghiệp vụ cần, một API boolean có thể đủ. Ví dụ một thao tác dọn file tạm “nếu còn thì thử xóa” có thể chấp nhận thất bại có ghi log phù hợp. Nhưng nếu xóa tài liệu quan trọng, thực hiện giao dịch, cập nhật cấu hình hoặc cần chẩn đoán lỗi cho người vận hành, **boolean không đủ làm kết quả nghiệp vụ cuối cùng**.

## 15. Những hiểu nhầm thường gặp

**“`File.delete() == false` nghĩa là file không tồn tại.”**  
Sai. Có nhiều nguyên nhân không thể xóa; dùng `Files.delete` nếu muốn biết lỗi cụ thể.

**“`mkdirs() == false` nghĩa là không có thư mục nào được tạo.”**  
Sai. Nó có thể thất bại sau khi đã tạo một phần cây thư mục; hoặc đích đã tồn tại từ trước.

**“`File.isFile() == false` nghĩa là nó chắc chắn là thư mục.”**  
Sai. Đường dẫn có thể không tồn tại, là loại khác hoặc không xác định được.

**“Mọi phương thức boolean của `File` đều không bao giờ ném `IOException`.”**  
Sai. `createNewFile()` trả boolean **và** khai báo `IOException`. Ngoài ra, các phương thức khác có thể ném ngoại lệ không phải I/O (ví dụ `SecurityException` trong môi trường có security manager phù hợp).

**“`Files.exists(path) == false` tức `Files.notExists(path) == true`.”**  
Sai. Nếu không xác định được trạng thái, cả hai đều có thể false.

**“Kiểm tra `exists()` trước sẽ bảo đảm thao tác sau không lỗi.”**  
Sai. File system có thể đổi trạng thái ngay lập tức; đây là nguy cơ TOCTOU.

**“Dùng `Files.move` sẽ luôn là atomic rename.”**  
Sai. Tính nguyên tử tùy provider/option; phải yêu cầu `ATOMIC_MOVE` và xử lý khi không được hỗ trợ nếu đó là điều kiện bắt buộc.

**“Catch IOException là luôn có thông báo đầy đủ từ OS.”**  
Sai. Provider có thể chỉ cung cấp lỗi chung; thông điệp lỗi có thể vắng hoặc khác theo môi trường. Tuy vậy exception và nguyên nhân vẫn cung cấp kênh chẩn đoán tốt hơn một boolean đơn lẻ.

**“False nghĩa là nên retry ngay.”**  
Sai. Nếu nguyên nhân là đường dẫn sai, quyền truy cập, đích xung đột hoặc thư mục không rỗng, retry có thể vô ích. Phải biết điều kiện nào thực sự tạm thời và tác dụng phụ có thể xảy ra.

## 16. Checklist khi review một đoạn code dùng `java.io.File`

- [ ] Phương thức trả boolean đang là **thao tác** hay **kiểm tra trạng thái**?
- [ ] Đã kiểm tra giá trị trả về chưa, hay bỏ qua thất bại?
- [ ] Nếu false, có đang suy đoán một nguyên nhân mà API **không bảo đảm** không?
- [ ] Nếu cần biết chính xác lý do, có phương thức `Files` tương ứng ném `IOException` không?
- [ ] Đã phân biệt `File.createNewFile` với các API chỉ trả boolean chưa?
- [ ] Đã xử lý tình huống đường dẫn đã tồn tại, đường dẫn không tồn tại và trạng thái **không xác định được**?
- [ ] Có tránh dựa vào `exists/canWrite/isFile` như bằng chứng cho thao tác tương lai?
- [ ] Với rename/move, đã làm rõ overwrite, atomicity, và khác file system?
- [ ] Có bảo toàn exception cause khi báo lỗi lên tầng nghiệp vụ?
- [ ] Log có tránh lộ thông tin đường dẫn nhạy cảm không?
- [ ] Nếu có retry/cleanup, đã giới hạn số lần và kiểm tra tác dụng phụ?
- [ ] Nếu file có thể thay đổi từ bên ngoài, đã đánh giá symlink và TOCTOU?
- [ ] Test có dùng tình huống ổn định thay vì phụ thuộc hành vi khóa/permission của từng OS?

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `File.delete()` trả false. Có thể kết luận file không tồn tại không?  
**Đáp án:** Không. Nó chỉ cho biết xóa không thành công; nguyên nhân cần tín hiệu khác hoặc API chi tiết hơn.

**Câu 2.** Nếu cần xóa file và chấp nhận nó đã không tồn tại, nên chọn API nào?  
**Đáp án:** `Files.deleteIfExists(path)`; khi file thiếu trả `false`, còn lỗi xóa có thể ném `IOException`.

**Câu 3.** `mkdirs()` trả false nhưng `isDirectory()` trả true. Trường hợp thường gặp là gì?  
**Đáp án:** Đích có thể đã là thư mục từ trước; cũng cần tính đến concurrency. Không có đủ dữ liệu để quy false thành thất bại nghiệp vụ.

**Câu 4.** `Files.exists(path)` và `Files.notExists(path)` có thể cùng false không?  
**Đáp án:** Có, khi không thể xác định trạng thái.

**Câu 5.** `File.createNewFile()` trả false khi nào, và vẫn có ngoại lệ gì?  
**Đáp án:** False khi đường dẫn đích đã tồn tại tại thời điểm tạo; lỗi I/O có thể ném `IOException`.

**Câu 6.** `File.renameTo()` trả false. Có nên tự động dùng `setWritable(true)` rồi retry không?  
**Đáp án:** Không. Nguyên nhân chưa biết; thay đổi quyền là một hành động khác, có rủi ro và không bảo đảm giải quyết được lỗi.

**Câu 7.** `File.listFiles() == null` có nghĩa thư mục rỗng không?  
**Đáp án:** Không. Có thể đích không phải thư mục hoặc liệt kê gặp lỗi. Mảng rỗng và `null` có ý nghĩa khác nhau.

**Câu 8.** Vì sao `Files.move(..., ATOMIC_MOVE)` vẫn cần xử lý lỗi?  
**Đáp án:** Provider có thể không hỗ trợ atomic move hoặc thao tác vẫn gặp lỗi I/O; yêu cầu atomicity phải được kiểm tra và xử lý khi không thể thực hiện.

**Ghi nhớ:** Các API `java.io.File` trả `boolean` thường phản ánh **kết quả rất ít thông tin**. Đừng tự suy ra lý do từ `false`, và đừng coi một phép kiểm tra trạng thái là bảo đảm tương lai. Khi cần xử lý lỗi có thể kiểm toán, ưu tiên thao tác `java.nio.file.Files` với `IOException` và phân biệt rõ trường hợp “đã không tồn tại” với “không thao tác được”.

## Tài liệu API chính thức (Java 17)

- [`java.io.File`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html)
- [`java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`java.nio.file.FileSystemException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystemException.html)
- [`java.nio.file.LinkOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)