# `NoSuchFileException`, `AccessDeniedException` và các lỗi NIO trong Java

Khi làm việc với file, thư mục hoặc hệ thống tệp bằng API `java.nio.file`, một lệnh như `Files.readString(path)`, `Files.copy(source, target)` hay `Files.move(source, target)` có thể thất bại vì **đường dẫn không tồn tại**, **quyền truy cập bị từ chối**, **đích đã tồn tại**, **thư mục chưa rỗng**, **không hỗ trợ di chuyển nguyên tử**, hoặc nhiều điều kiện khác.

Java NIO.2 (có từ Java 7, được mở rộng ở các phiên bản sau) cung cấp những lớp ngoại lệ cụ thể để phân biệt tình huống. Hai lớp đáng chú ý nhất là:

- **`NoSuchFileException`**: thao tác cố truy cập một file hoặc đường dẫn không tồn tại trong điều kiện hệ thống tệp đang xét.
- **`AccessDeniedException`**: thao tác bị từ chối truy cập đến file hoặc đường dẫn trong ngữ cảnh của hệ thống tệp.

Cả hai đều là **checked exceptions**, kế thừa `FileSystemException` → `IOException`. Có thể bắt riêng từng loại để triển khai chính sách phù hợp, nhưng **không được mặc định rằng mọi hệ điều hành và mọi file-system provider đều luôn phát ra cùng một subclass cho cùng một lỗi cấp thấp**.

**Nguyên tắc chính:** chọn handler theo *loại ngoại lệ và ngữ nghĩa thao tác*, xem thông tin path/reason có cấu trúc, giữ `cause` khi chuyển lỗi và luôn có phương án cho các `IOException` chưa phân loại.

## 1. API NIO.2 và các lớp nền tảng

Trong Java, các API file thường dùng nằm ở:

| Kiểu/API | Package | Vai trò |
| --- | --- | --- |
| `Path` | `java.nio.file` | Biểu diễn đường dẫn trong hệ thống file; không tự chứng minh file tồn tại |
| `Files` | `java.nio.file` | Thao tác mở/đọc/ghi/copy/move/delete, thuộc tính và duyệt cây thư mục |
| `FileSystem`, `FileSystems` | `java.nio.file` | Trừu tượng file-system provider và các file system đang dùng |
| `OpenOption`, `StandardOpenOption` | `java.nio.file` | Quy định cách mở/tạo/ghi file |
| `CopyOption`, `StandardCopyOption` | `java.nio.file` | Điều khiển sao chép hoặc di chuyển |
| `LinkOption` | `java.nio.file` | Quy định có theo symbolic link ở những API hỗ trợ hay không |
| `BasicFileAttributes` | `java.nio.file.attribute` | Thông tin thuộc tính file |
| `IOException` | `java.io` | Lớp checked chung cho nhiều thất bại I/O |
| `FileSystemException` | `java.nio.file` | Checked exception gắn với file, file khác và lý do lỗi |
| `NoSuchFileException`, `AccessDeniedException` | `java.nio.file` | Hai phân loại file-system error cụ thể |

`Path.of("data", "input.csv")` **chỉ tạo đối tượng biểu diễn đường dẫn**. Nó không đọc đĩa để xác minh path thật sự tồn tại. Vì vậy, lỗi “không tìm thấy file” thường xuất hiện lúc **thực hiện thao tác I/O**, không phải chỉ vì đã tạo `Path`.

Ví dụ:

```java
Path path = Path.of("data", "input.csv");
String content = Files.readString(path);
```

Đây là **đoạn minh họa** cần import `java.nio.file.Path`, `java.nio.file.Files` và xử lý checked `IOException`. Lệnh `readString` có thể ném lỗi vì path thiếu, quyền không cho phép, file không phù hợp thao tác hoặc lỗi I/O khác.

## 2. Quan hệ kế thừa của các ngoại lệ NIO

Trích đoạn phân cấp thường gặp:

```text
java.lang.Throwable
└── java.lang.Exception
    └── java.io.IOException
        ├── java.io.FileNotFoundException
        └── java.nio.file.FileSystemException
            ├── NoSuchFileException
            ├── AccessDeniedException
            ├── FileAlreadyExistsException
            ├── DirectoryNotEmptyException
            ├── NotDirectoryException
            ├── FileSystemLoopException
            └── AtomicMoveNotSupportedException
```

Đây là **sơ đồ rút gọn**, không liệt kê mọi subtype, không có nghĩa tất cả lỗi NIO đều nằm dưới `FileSystemException`.

Mỗi lớp trong nhánh `FileSystemException` nêu một tình huống khác nhau. Vì tất cả đều thuộc `IOException`, một `catch (IOException ex)` có thể bắt chúng, nhưng dùng chỉ một handler chung sẽ bỏ lỡ cơ hội phục hồi có chủ đích.

Ngoài checked exception, một số thao tác NIO có thể ném **unchecked exceptions** như `InvalidPathException`, `ClosedFileSystemException`, `FileSystemNotFoundException`, `ProviderNotFoundException`, `UnsupportedOperationException` hoặc `SecurityException` trong những điều kiện và môi trường tương ứng. Không được coi `catch (IOException)` là “bắt mọi lỗi của NIO”.

### Vì sao `FileNotFoundException` và `NoSuchFileException` khác nhau?

`java.io.FileNotFoundException` là một checked subtype của `IOException` thường gặp từ các API I/O truyền thống như `FileInputStream`. `java.nio.file.NoSuchFileException` là subtype của **`FileSystemException`**, hướng tới lỗi file-system trong NIO. **Hai lớp không phải cha/con trực tiếp của nhau**.

Không nên luôn chuyển từ `FileInputStream` sang `Files.newInputStream` rồi giả định loại ngoại lệ chính xác không thay đổi. Caller cần đọc hợp đồng API cụ thể và giữ một handler `IOException` phù hợp.

## 3. `NoSuchFileException`: file hoặc một thành phần đường dẫn không tồn tại

`NoSuchFileException` biểu diễn việc thao tác thất bại vì file/đường dẫn được yêu cầu không tồn tại trong tình huống hiện tại.

Ví dụ điển hình:

```java
Path path = Path.of("data", "never-created.txt");
String text = Files.readString(path);
```

Nếu path thực sự không tồn tại, file-system provider mặc định thường ném `NoSuchFileException`. Tuy nhiên, đừng dùng ví dụ này để khẳng định **mọi provider** phải luôn cung cấp cùng subtype trong mọi hoàn cảnh; lỗi I/O cụ thể có thể phụ thuộc provider và trạng thái hệ thống.

Các nguyên nhân phổ biến:

- Sai tên file, đường dẫn tương đối được hiểu khác dự kiến, sai chữ hoa/thường trên file system phân biệt case.
- File từng tồn tại nhưng đã bị xóa hoặc di chuyển giữa lúc kiểm tra và lúc mở.
- Một thư mục cha không tồn tại.
- Một symbolic link trỏ đến đích đã bị xóa, tùy cách thao tác theo link.
- Đường dẫn được tạo từ một cấu hình không đúng, hoặc process đang chạy ở working directory khác dự kiến.

### Đường dẫn tương đối và working directory

`Path.of("config", "app.properties")` là đường dẫn tương đối. Nó được giải nghĩa trong ngữ cảnh file system và working directory của process khi API thực hiện thao tác.

Không nên suy đoán rằng nó luôn trỏ đến thư mục chứa tệp `.java` hay thư mục của IDE project. Với một chương trình đóng gói và chạy như service, working directory có thể khác đáng kể.

Có thể hỗ trợ chẩn đoán bằng:

```java
Path requested = Path.of("config", "app.properties");
System.out.println(requested.toAbsolutePath().normalize());
```

Đây là **mã minh họa**; `toAbsolutePath()` không có nghĩa xác thực file tồn tại. Nó giúp hiển thị đường dẫn được suy ra, không thay thế quyền truy cập hoặc phép mở.

### Khi file thiếu là kết quả bình thường

Không phải mọi trường hợp thiếu file đều là sự cố. Ví dụ một cấu hình tùy chọn chưa có thể được xử lý bằng default được xác định rõ. Khi đó có thể bắt **riêng `NoSuchFileException`** và trả một kết quả mô tả “không có cấu hình tùy chọn”.

Ngược lại, với file dữ liệu bắt buộc, nên báo rõ thất bại và không coi missing như dữ liệu rỗng thành công giả.

## 4. `AccessDeniedException`: bị từ chối quyền hoặc truy cập

`AccessDeniedException` thường xuất hiện khi file-system provider từ chối một thao tác truy cập vào file hoặc một thành phần đường dẫn.

Ví dụ:

```java
Path path = Path.of("private", "credentials.txt");
String text = Files.readString(path);
```

Đây là **đoạn minh họa**, không đảm bảo sẽ ném `AccessDeniedException` trên máy đang chạy. Quyền thực tế phụ thuộc tài khoản người dùng, ACL, quyền thư mục cha, mount, cơ chế bảo mật, file-system provider và môi trường.

Những tình huống thường gặp:

- User/process không được phép đọc file.
- Thư mục cha không cho phép đi qua/duyệt theo quy tắc quyền của hệ điều hành.
- Process không được phép ghi hoặc xóa file theo ACL/chính sách của hệ thống.
- Một số thao tác bị từ chối bởi provider hoặc chính sách truy cập nơi lưu trữ.

### Không trộn lẫn với `SecurityException`

`AccessDeniedException` là **checked `IOException`**, còn `SecurityException` là **unchecked `RuntimeException`**. `SecurityException` có thể liên quan kiểm tra bảo mật cấp Java, chẳng hạn trong môi trường có cơ chế security manager hỗ trợ; nó không phải tên đồng nghĩa với mọi lỗi quyền của hệ điều hành.

Một API có thể báo lỗi quyền bằng một `IOException` khác hoặc bằng exception cụ thể tùy provider. Vì vậy:

- `catch (AccessDeniedException ex)` chỉ bắt chính subclass này.
- `catch (IOException ex)` còn bắt các lỗi I/O checked khác.
- `catch (IOException ex)` **không** bắt `SecurityException`.

Trong mã thông thường không nên `catch (Throwable)` chỉ để ép mọi lỗi quyền và lỗi lập trình thành một trạng thái “không có file”.

### Tại sao tự đổi quyền file trong demo không đảm bảo gây lỗi?

Một bài học có thể thử `Files.setPosixFilePermissions` trên POSIX, nhưng API đó có thể không được hỗ trợ trên Windows hoặc một provider khác. Kể cả thay quyền thành chỉ đọc, process có quyền cao, ACL đặc biệt hoặc policy của hệ thống vẫn có thể làm kết quả khác dự kiến.

Do đó, các ví dụ bên dưới sẽ **không phụ thuộc vào việc cưỡng ép lỗi quyền thật trên máy học**. Thay vào đó, một chương trình dựng các đối tượng ngoại lệ để học cách phân loại, và một chương trình thao tác file thực trong thư mục tạm để học API.

## 5. `FileSystemException` giữ thông tin lỗi có cấu trúc nào?

`FileSystemException` cung cấp:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `getFile()` | `String` | File/path chính có liên quan đến lỗi, có thể `null` |
| `getOtherFile()` | `String` | File/path thứ hai trong thao tác như copy/move, có thể `null` |
| `getReason()` | `String` | Lý do bổ sung, có thể `null` |
| `getMessage()` | `String` | Chuỗi chẩn đoán do exception cung cấp |
| `getCause()` | `Throwable` | Nguyên nhân nếu được gắn, có thể `null` |

Cách dùng:

```java
catch (java.nio.file.FileSystemException ex) {
    String file = ex.getFile();
    String other = ex.getOtherFile();
    String reason = ex.getReason();
    // Ghi log nội bộ an toàn hoặc ánh xạ mã lỗi.
}
```

Đây là **mảnh handler minh họa**, cần nằm trong cấu trúc `try` thích hợp.

**Điểm tinh tế:** `getFile()` và `getOtherFile()` trả **chuỗi**, không trả `Path`. Không nên tin rằng chuỗi đó luôn tương đương một path đã được chuẩn hóa/canonical hóa hoặc luôn an toàn để gửi cho client.

### Cần phân biệt dữ liệu và message

Với một `AccessDeniedException`, ứng dụng có thể ghi nhận:

- Loại: `AccessDeniedException`.
- File chính: `getFile()`.
- File thứ hai: `getOtherFile()` nếu có.
- Lý do: `getReason()` nếu provider cung cấp.

Đừng phân nhánh chỉ bằng `ex.getMessage().contains("Permission denied")`. Câu chữ/locale khác nhau, `reason` có thể không tồn tại, và message có thể lộ đường dẫn.

Trong API công khai nên ánh xạ **loại lỗi → mã lỗi do ứng dụng định nghĩa**, rồi tạo thông điệp an toàn theo nhu cầu người dùng. Thông tin path đầy đủ chỉ nên đi vào hệ thống log có quyền truy cập thích hợp.

## 6. Các lỗi NIO khác cần phân biệt

| Ngoại lệ | Trường hợp thường gặp | Hướng xử lý tùy ngữ cảnh |
| --- | --- | --- |
| `NoSuchFileException` | File/thành phần path được yêu cầu không tồn tại | Kiểm tra path, missing là optional hay bắt buộc |
| `AccessDeniedException` | Truy cập bị từ chối | Kiểm tra quyền process/ACL/provider; không mặc định retry |
| `FileAlreadyExistsException` | Tạo file/dir mới hoặc copy vào đích đã tồn tại | Chọn tên khác, từ chối ghi đè, hoặc xử lý overwrite theo hợp đồng |
| `DirectoryNotEmptyException` | Xóa thư mục khi còn phần tử | Không tự xóa đệ quy nếu chưa được phép |
| `NotDirectoryException` | Một thành phần path được mong đợi là thư mục nhưng không phải | Kiểm tra cấu trúc path và dữ liệu đầu vào |
| `FileSystemLoopException` | Gặp vòng lặp khi duyệt theo symbolic links | Kiểm tra link policy và cách walk tree |
| `AtomicMoveNotSupportedException` | Yêu cầu `ATOMIC_MOVE` nhưng provider không hỗ trợ | Chọn thất bại an toàn hoặc fallback không nguyên tử có chủ đích |
| `IOException` khác | Lỗi thiết bị, hỏng dữ liệu, mạng, quota, provider... | Không suy diễn là missing hoặc denied |

**Chú ý:** phân loại này là **các trường hợp thường gặp**, không đảm bảo duy nhất một ngoại lệ cho mỗi sự cố vật lý. Một lỗi disk, mount hoặc provider có thể xuất hiện dưới loại rộng hơn.

### `FileAlreadyExistsException` không tự động có nghĩa nên ghi đè

Ví dụ `Files.createFile(target)` cố tạo file mới, nhưng file đã tồn tại. Đây có thể là **tín hiệu hợp đồng đúng**: không được làm mất dữ liệu cũ. Không nên tự đổi thành `Files.writeString(target, ...)` theo tùy chọn mặc định vì thao tác ghi có thể **truncate** dữ liệu hiện có.

Nếu muốn tạo file mới **chỉ khi chưa tồn tại**, ưu tiên thao tác hỗ trợ `CREATE_NEW` hoặc `Files.createFile` thay vì làm `if (!Files.exists(path))` rồi mới tạo.

### `DirectoryNotEmptyException` không cho phép tự dọn cả cây

Một handler kiểu:

```java
catch (DirectoryNotEmptyException ex) {
    // ĐỪNG tự động xóa mọi file con nếu hợp đồng không cho phép.
}
```

nên xem đây là tín hiệu cần chính sách rõ: từ chối xóa, yêu cầu xác nhận, di chuyển sang vùng lưu trữ, hoặc thực hiện xóa đệ quy chỉ khi được thiết kế và cấp quyền.

Lệnh `Files.delete(path)` không mặc định xóa cả cây thư mục.

## 7. Ví dụ Java 17+ hoàn chỉnh: phân loại exception không phụ thuộc OS

Để kiểm chứng các loại lỗi và thông tin `FileSystemException` với **stdout ổn định**, chương trình dưới đây chủ động **tạo các đối tượng exception** chứ không giả định rằng hệ điều hành sẽ từ chối quyền theo cách nhất định.

Lưu tệp **`NioExceptionCatalogDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.FileSystemException;
import java.nio.file.FileSystemLoopException;
import java.nio.file.NoSuchFileException;
import java.nio.file.NotDirectoryException;

public class NioExceptionCatalogDemo {

    static String classify(IOException error) {
        if (error instanceof NoSuchFileException) {
            return "MISSING";
        }
        if (error instanceof AccessDeniedException) {
            return "DENIED";
        }
        if (error instanceof FileAlreadyExistsException) {
            return "ALREADY_EXISTS";
        }
        if (error instanceof DirectoryNotEmptyException) {
            return "NOT_EMPTY";
        }
        if (error instanceof NotDirectoryException) {
            return "NOT_DIRECTORY";
        }
        if (error instanceof FileSystemLoopException) {
            return "LINK_LOOP";
        }
        if (error instanceof AtomicMoveNotSupportedException) {
            return "NO_ATOMIC_MOVE";
        }
        return "IO_OTHER";
    }

    static String display(String value) {
        return value == null ? "-" : value;
    }

    static void show(IOException error) {
        System.out.println(
                classify(error)
                + " | " + error.getClass().getSimpleName());

        if (error instanceof FileSystemException fs) {
            System.out.println(
                    "file=" + display(fs.getFile())
                    + "; other=" + display(fs.getOtherFile())
                    + "; reason=" + display(fs.getReason()));
        }
    }

    public static void main(String[] args) {
        show(new NoSuchFileException("data/missing.csv"));

        show(new AccessDeniedException(
                "private/report.txt", null, "permission denied"));

        show(new FileAlreadyExistsException("output/result.csv"));

        show(new DirectoryNotEmptyException("archive/old"));

        show(new NotDirectoryException("data/items"));

        show(new FileSystemLoopException("links/current"));

        show(new AtomicMoveNotSupportedException(
                "diskA/input.csv",
                "diskB/input.csv",
                "atomic move unsupported"));

        show(new IOException("general I/O problem"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 NioExceptionCatalogDemo.java
java NioExceptionCatalogDemo
```

**Stdout chính xác:**

```text
MISSING | NoSuchFileException
file=data/missing.csv; other=-; reason=-
DENIED | AccessDeniedException
file=private/report.txt; other=-; reason=permission denied
ALREADY_EXISTS | FileAlreadyExistsException
file=output/result.csv; other=-; reason=-
NOT_EMPTY | DirectoryNotEmptyException
file=archive/old; other=-; reason=-
NOT_DIRECTORY | NotDirectoryException
file=data/items; other=-; reason=-
LINK_LOOP | FileSystemLoopException
file=links/current; other=-; reason=-
NO_ATOMIC_MOVE | AtomicMoveNotSupportedException
file=diskA/input.csv; other=diskB/input.csv; reason=atomic move unsupported
IO_OTHER | IOException
```

### Vì sao đây là demo phân loại đáng tin?

- Nó không phụ thuộc tài khoản hiện hành có quyền root/administrator hay không.
- Nó không cần tạo file rồi thay quyền theo đặc thù Linux/Windows.
- Mỗi constructor cung cấp dữ liệu file/reason cụ thể; những trường không được truyền có thể là `null` và được in thành dấu `-`.
- Handler nhận kiểu chung `IOException` nhưng phân nhánh bằng `instanceof` của exception, **không parse text message**.
- Ví dụ cho thấy `FileSystemException` chứa thông tin đường dẫn phụ và lý do, **không chỉ message một dòng**.

**Giới hạn cần hiểu:** chương trình tạo exception để học cách phân loại; nó **không chứng minh** một thao tác file thực trong mọi provider sẽ ném đúng subclass giống tên ở mỗi dòng.

## 8. Bắt ngoại lệ theo thứ tự đúng

Khi xử lý NIO, các subclass nên xuất hiện **trước** handler cho superclass:

```java
try {
    String text = Files.readString(path);
    useText(text);

} catch (NoSuchFileException ex) {
    handleMissing(ex);

} catch (AccessDeniedException ex) {
    handleDenied(ex);

} catch (IOException ex) {
    handleOtherIo(ex);
}
```

Đây là **khung minh họa**, với import và các phương thức `useText`/`handleMissing`/`handleDenied`/`handleOtherIo` hợp lệ. Cách viết này cho phép chính sách riêng từng lỗi, sau đó xử lý fallback cho mọi `IOException` khác.

### Vì sao không bắt `IOException` trước?

Đoạn sau không hợp lệ:

```java
// Cố ý KHÔNG BIÊN DỊCH.
try {
    Files.readString(path);
} catch (IOException ex) {
    handleOtherIo(ex);
} catch (NoSuchFileException ex) {
    handleMissing(ex);
}
```

Vì `NoSuchFileException` là subclass của `IOException`, nhánh `catch (NoSuchFileException)` phía sau **không thể tới được**: nhánh cha trước đó đã bắt tất cả những đối tượng thuộc subclass này.

### Có thể dùng multi-catch không?

Nếu hai lỗi có cùng chính sách:

```java
catch (NoSuchFileException | AccessDeniedException ex) {
    reportUnavailable(ex);
}
```

Đây là handler minh họa. `NoSuchFileException` và `AccessDeniedException` là hai sibling trong cây kiểu nên multi-catch hợp lệ.

Tuy vậy, **đừng gộp chỉ vì chúng đều thất bại**. Nếu thiếu file là optional còn bị từ chối quyền là lỗi vận hành cần báo động, chúng **phải có hai chính sách khác nhau**.

## 9. Ví dụ Java 17+ hoàn chỉnh: thao tác NIO thật trong thư mục tạm

Ví dụ tiếp theo thực hiện tạo/đọc/copy file, sau đó mô phỏng các trường hợp đích đã có và file thiếu bằng thao tác NIO thật. Không dùng tên file cố định trong project để tránh ghi đè dữ liệu của người học.

Lưu tệp **`NioFileWorkflowDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class NioFileWorkflowDemo {

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("nio-lesson-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("copy.txt");
        Path missing = directory.resolve("missing.txt");

        try {
            Files.writeString(
                    source,
                    "alpha",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);

            System.out.println(
                    "source="
                    + Files.readString(source, StandardCharsets.UTF_8));

            Files.copy(source, target);

            System.out.println(
                    "copy="
                    + Files.readString(target, StandardCharsets.UTF_8));

            try {
                Files.copy(source, target);
                System.out.println("unexpected overwrite");
            } catch (FileAlreadyExistsException ex) {
                System.out.println("copy=ALREADY_EXISTS");
            }

            try {
                Files.readString(missing, StandardCharsets.UTF_8);
                System.out.println("unexpected missing read");
            } catch (NoSuchFileException ex) {
                System.out.println("read=MISSING");
            }

        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(missing);
            Files.deleteIfExists(directory);
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 NioFileWorkflowDemo.java
java NioFileWorkflowDemo
```

**Stdout trên file system mặc định thông thường**, khi tạo/xóa file được cấp quyền và provider trả subclass cụ thể như trong ví dụ:

```text
source=alpha
copy=alpha
copy=ALREADY_EXISTS
read=MISSING
```

**Không khẳng định stdout này tuyệt đối trong mọi môi trường.** Chương trình dùng API file thực; quyền, provider, bộ lọc antivirus, tình trạng ổ đĩa và race với tiến trình khác có thể gây `IOException` khác, hoặc cách phân loại không giống file system thông thường. Trong trường hợp đó chương trình để ngoại lệ chưa xử lý lên caller/JVM (qua `main throws IOException`) thay vì che bằng giá trị thành công giả.

### Vì sao dùng `CREATE_NEW` ở file nguồn?

`Files.writeString` khi không khai báo option thường dùng hành vi tạo nếu chưa có và truncate file hiện có. Ở đây dùng `StandardOpenOption.CREATE_NEW` để **chỉ tạo file mới**, tránh vô tình ghi đè.

Với `CREATE_NEW`, kiểm tra tồn tại và tạo file được thực hiện như một thao tác nguyên tử đối với việc tạo mới theo hợp đồng API, thay vì `if (!Files.exists(...))` rồi `Files.writeString(...)` có cửa sổ race.

### Vì sao không dùng `REPLACE_EXISTING` khi copy lần hai?

`Files.copy(source, target)` theo mặc định không tự động thay thế đích hiện hữu trong trường hợp thông thường. Lần copy thứ hai nhằm minh họa rằng **“đích đã tồn tại” là một loại thất bại có ý nghĩa**, không phải lệnh nên tự overwrite ngay.

`StandardCopyOption.REPLACE_EXISTING` có thể được dùng khi hợp đồng **chủ động cho phép thay thế**, sau khi xét an toàn dữ liệu. Không nên tự thêm option này chỉ để khỏi thấy `FileAlreadyExistsException`.

### Vì sao dùng `finally` để dọn thư mục tạm?

Ví dụ mở/ghi nhiều file rồi cố ý gây ngoại lệ được bắt. `finally` thử xóa các file và thư mục đã tạo dù có lỗi trong thân. Tuy nhiên, **xóa cũng có thể ném `IOException`**, và một ngoại lệ phát sinh trong `finally` có thể che một lỗi từ thân `try`. Với tài nguyên `AutoCloseable` như stream/channel, thường nên dùng `try-with-resources`; với xóa tệp trong ví dụ ngắn, `finally` cho thấy mục đích cleanup, không phải công thức rollback tổng quát.

Trong production, nếu cleanup có thể thất bại đồng thời với thao tác chính, cần một chiến lược giữ được cả hai lỗi, ví dụ lưu ngoại lệ chính và thêm lỗi phụ bằng `addSuppressed` khi phù hợp.

## 10. Thiếu file có thể xử lý bằng kết quả tùy chọn; lỗi quyền thì không nên

Một file cấu hình **không bắt buộc** có thể có hợp đồng:

- Có file và đọc được: trả nội dung.
- Không có file: trả kết quả “vắng mặt”, caller dùng default.
- Bị từ chối truy cập hoặc lỗi I/O khác: **báo lỗi**, không giả làm “vắng mặt”.

Ví dụ Java 17+ dưới dạng phương thức:

```java
static java.util.Optional<String> readOptionalConfig(
        java.nio.file.Path path) throws java.io.IOException {

    try {
        return java.util.Optional.of(
                java.nio.file.Files.readString(path));

    } catch (java.nio.file.NoSuchFileException missing) {
        return java.util.Optional.empty();
    }
}
```

Đây là **phương thức minh họa chạy được khi đặt trong một lớp**. Nó chỉ chuyển `NoSuchFileException` sang `Optional.empty()`. Nếu `AccessDeniedException` hoặc một `IOException` khác xuất hiện, phương thức **vẫn ném ra** cho caller xử lý.

**Lưu ý hợp đồng:** `Optional.empty()` ở đây thể hiện thiếu file theo chính sách của chính API này, không khẳng định path luôn mất trong mọi thời điểm tiếp theo. Một thread/process khác có thể tạo file ngay sau khi thao tác thất bại.

### Trường hợp file là bắt buộc

Với file import bắt buộc:

```java
static String readRequired(
        java.nio.file.Path path) throws java.io.IOException {

    return java.nio.file.Files.readString(path);
}
```

Không cần bắt `NoSuchFileException` chỉ để ném lại nếu không bổ sung ngữ cảnh. Nếu tầng service phải chuyển từ lỗi filesystem sang lỗi nghiệp vụ, hãy bọc **đúng ngữ nghĩa và giữ cause**:

```java
try {
    return Files.readString(path);
} catch (NoSuchFileException cause) {
    throw new RequiredInputMissingException(
            "Required import source is missing", cause);
}
```

Đoạn này là **khung minh họa** với một custom exception `RequiredInputMissingException` do ứng dụng định nghĩa, có constructor nhận `Throwable cause`. Không dùng `new RuntimeException(cause.getMessage())` nếu muốn giữ stack/cause của lỗi gốc.

## 11. Đừng dùng `Files.exists` làm bằng chứng đủ cho thao tác kế tiếp

Một mẫu code phổ biến:

```java
if (Files.exists(path)) {
    return Files.readString(path);
}
return "";
```

Đoạn này có hai vấn đề:

1. **Time-of-check-to-time-of-use (TOCTOU):** file có thể bị xóa/thay thế hoặc quyền có thể thay đổi giữa `exists` và `readString`.
2. **`Files.exists` không chứng minh đọc được file:** path có thể có nhưng bị từ chối quyền, là thư mục hoặc file-system provider bị lỗi.

Ngay cả khi `Files.exists(path)` trả `false`, điều đó **không luôn chứng minh file không tồn tại**; một số trường hợp trạng thái tồn tại không xác định được. Theo hợp đồng của `Files.exists`/`Files.notExists`, có thể cả hai đều trả `false` nếu không xác định được một cách chắc chắn.

Vì vậy, để đọc file theo chính sách:

- **Thực hiện thao tác `Files.readString` hoặc mở file trực tiếp**.
- Bắt những subclass ngoại lệ mà caller có chính sách rõ.
- Để `IOException` khác tiếp tục đi lên hoặc được chuyển có cause.
- Không dựa vào chuỗi kiểm tra trước làm thay thế cho việc xử lý lỗi thực tế.

### `Files.isReadable` cũng không phải một giấy phép vĩnh viễn

`Files.isReadable(path)` có thể hữu ích cho UI hoặc kiểm tra sơ bộ, nhưng một kết quả `true` không bảo đảm lần mở sau sẽ thành công. Trạng thái quyền và hệ thống có thể thay đổi; một số provider có cách biểu diễn quyền khác nhau.

Không viết:

```java
// Chống mẫu: giả định isReadable loại bỏ mọi IOException.
if (Files.isReadable(path)) {
    return Files.readString(path);
}
```

mà không có hợp đồng xử lý lỗi của thao tác đọc.

## 12. Path normalization, symbolic link và rủi ro bảo mật

`Path.normalize()` loại bỏ những thành phần thừa như `.` và `..` bằng **quy tắc cú pháp**; nó không nhất thiết truy cập file system hay phân giải symbolic link.

`Path.toRealPath(...)` có thể yêu cầu file thực tồn tại để phân giải path, liên quan tới I/O và có thể ném `IOException`. Việc kiểm tra path có nằm trong một thư mục cho phép hay không chỉ bằng `normalize` và `startsWith` có thể không đủ trong môi trường có symbolic link hoặc đối tượng bị thay đổi đồng thời.

Ví dụ:

```java
Path root = Path.of("uploads");
Path requested = root.resolve(userSuppliedName).normalize();
```

Đây là khung minh họa; `userSuppliedName` đến từ nguồn không đáng tin. Kiểm tra lexical path là **một bước**, không phải toàn bộ giải pháp sandbox:

- Chuỗi `..` có thể khiến path rời khỏi thư mục dự kiến.
- Symbolic link có thể trỏ tới vị trí ngoài root.
- Một thread/process khác có thể thay đổi entry giữa bước kiểm tra và bước mở.
- Quyền truy cập ở hệ điều hành hoặc container vẫn là lớp bảo vệ riêng.

Với thao tác bảo mật nhạy cảm, cần thiết kế quyền của process, chính sách link, và cơ chế mở/duyệt thư mục chống race phù hợp, có thể cân nhắc `SecureDirectoryStream` ở provider hỗ trợ. Đừng tuyên bố `normalize()` một mình chặn hết path traversal.

### `NOFOLLOW_LINKS` thay đổi một số phép kiểm tra

Một số API cho phép `LinkOption.NOFOLLOW_LINKS` để kiểm tra **bản thân symbolic link** thay vì đi theo đích. Ví dụ:

```java
boolean isLink = Files.isSymbolicLink(path);
boolean presentWithoutFollowing =
        Files.exists(path, LinkOption.NOFOLLOW_LINKS);
```

Đây là đoạn minh họa. Một dangling symlink có thể tồn tại dưới dạng link ngay cả khi đích của nó không tồn tại; bởi vậy việc hỏi “file có tồn tại không?” cần nói rõ đang hỏi **link** hay **đích của link**.

Việc dùng `NOFOLLOW_LINKS` không phải phép đảm bảo an toàn duy nhất chống race. Cần hiểu từng API và provider có hỗ trợ option đó ở thao tác đang xét không.

## 13. `FileSystemLoopException` và duyệt cây thư mục

`Files.walkFileTree` cho phép duyệt cây thư mục với các callback như `visitFile` và `visitFileFailed`. Khi yêu cầu theo symbolic links (ví dụ với `FileVisitOption.FOLLOW_LINKS`), một chuỗi link có thể tạo **vòng lặp**.

Trong trường hợp phát hiện loop, `FileSystemLoopException` có thể được đưa vào `visitFileFailed` để ứng dụng quyết định báo lỗi hay bỏ qua theo chính sách.

Khung minh họa:

```java
Files.walkFileTree(
        root,
        java.util.EnumSet.of(
                java.nio.file.FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        new java.nio.file.SimpleFileVisitor<Path>() {

            @Override
            public java.nio.file.FileVisitResult visitFileFailed(
                    Path file, IOException ex) throws IOException {

                if (ex instanceof
                        java.nio.file.FileSystemLoopException) {
                    throw ex; // Thất bại có chủ đích.
                }
                throw ex;
            }
        });
```

Đây là **đoạn minh họa**, cần import `Path`, `Files`, `IOException` và biến `root` hợp lệ. Handler có thể gộp thành `throw ex;` nếu chính sách là fail-fast với mọi lỗi; việc xét `FileSystemLoopException` chỉ để làm rõ tình huống.

Không nên tự động bỏ mọi `visitFileFailed` khi quét file bảo mật hoặc backup, bởi kết quả duyệt sẽ thiếu dữ liệu nhưng vẫn có thể bị báo nhầm “thành công”.

### Duyệt tất cả file có đảm bảo không lỗi race?

Không. Trong lúc duyệt, file có thể được tạo/xóa/đổi quyền bởi tiến trình khác. `visitFileFailed` cần có chính sách rõ. Nếu một ứng dụng yêu cầu snapshot nhất quán, chỉ dùng `Files.walkFileTree` không tự tạo transaction hoặc snapshot của toàn hệ thống tệp.

## 14. `AtomicMoveNotSupportedException` khi yêu cầu di chuyển nguyên tử

`Files.move(source, target, StandardCopyOption.ATOMIC_MOVE)` yêu cầu thao tác chuyển tên/file theo khả năng **atomic move** của provider:

```java
Files.move(
        source,
        target,
        java.nio.file.StandardCopyOption.ATOMIC_MOVE);
```

Đoạn này là mã minh họa. Nếu không thể thực hiện như một thao tác nguyên tử, provider có thể ném **`AtomicMoveNotSupportedException`**.

### Fallback từ atomic sang non-atomic: không phải lúc nào cũng an toàn

Một số ứng dụng chọn:

```java
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    Files.move(source, target);
}
```

Đây là đoạn minh họa với import và biến path phù hợp. Chính sách này chỉ hợp lý khi **ứng dụng cho phép di chuyển không nguyên tử** và đã xét các hệ quả nếu process crash giữa chừng.

Nếu ứng dụng cần đảm bảo file đầu ra được công bố nguyên vẹn hoặc dữ liệu không rơi vào trạng thái dở dang, fallback không nguyên tử có thể **phá vỡ tính đúng đắn**. Khi đó nên truyền lỗi cho caller và báo rằng provider không đáp ứng yêu cầu.

Cũng cần lưu ý: cách xử lý **đích đã tồn tại** khi `ATOMIC_MOVE` có thể mang quy định đặc thù implementation. Đừng mặc định mọi option copy/move khác đều giữ nguyên cùng ý nghĩa khi kết hợp `ATOMIC_MOVE`.

## 15. Phân loại loại lỗi cho API/service thay vì phân tích `getMessage()`

Một service có thể muốn chuyển lỗi NIO thành mã công khai. Ví dụ:

| Loại exception gốc | Mã ứng dụng gợi ý | Cần kiểm tra ngữ cảnh trước khi trả client |
| --- | --- | --- |
| `NoSuchFileException` | `RESOURCE_NOT_FOUND` | File thiếu có thật sự là tài nguyên client được phép biết? |
| `AccessDeniedException` | `STORAGE_ACCESS_DENIED` | Không tiết lộ path nội bộ hoặc cấu hình quyền |
| `FileAlreadyExistsException` | `DESTINATION_EXISTS` | Có phải thao tác tạo mới và xung đột hợp đồng? |
| `DirectoryNotEmptyException` | `DIRECTORY_NOT_EMPTY` | Có cho phép xóa cả cây không? |
| `AtomicMoveNotSupportedException` | `ATOMIC_MOVE_UNAVAILABLE` | Có cần đảm bảo atomicity không? |
| `IOException` còn lại | `STORAGE_IO_ERROR` | Cần log kỹ thuật và chính sách retry riêng |

Các mã chỉ là **ví dụ do ứng dụng định nghĩa**, không phải các constant chuẩn của NIO.

Không thể tự động suy ra `NoSuchFileException` luôn phải là HTTP 404 hay `AccessDeniedException` luôn phải là HTTP 403. Lỗi file nội bộ có thể là **lỗi server**, không phải lỗi của client. Mapping HTTP cần dựa vào hợp đồng API và các thông tin được phép công bố.

### Không biến permission error thành missing một cách tùy tiện

Trong hệ thống bảo mật, đôi khi API chủ động trả một thông điệp “không tìm thấy” thay vì xác nhận có tài nguyên nhưng bị cấm, để tránh lộ sự tồn tại của tài nguyên. Nếu có lựa chọn đó, nó phải thuộc **chính sách bảo mật ở ranh giới API**, không phải logic generic mặc định che mọi `AccessDeniedException` thành `NoSuchFileException` ở tầng file.

Ghi log nội bộ nên vẫn giữ **phân loại lỗi gốc** để vận hành biết vấn đề quyền thực sự xảy ra.

## 16. Retry và race: lỗi nào có thể thử lại?

Không có quy tắc “mọi `IOException` đều retry” hoặc “mọi `NoSuchFileException` là tạm thời”.

- **NoSuchFileException:** nếu file do một producer bất đồng bộ sẽ tạo trong tương lai theo hợp đồng, retry có giới hạn đôi khi hợp lý. Nếu path sai vì cấu hình, retry vô hạn vô ích.
- **AccessDeniedException:** thường cần sửa permission/credentials/policy, retry tức thời không giúp; nhưng môi trường xác thực hoặc mount động có thể có trường hợp khác.
- **FileAlreadyExistsException:** đôi khi là race bình thường giữa hai tác vụ tạo cùng tên; cần chính sách idempotency hoặc tên duy nhất, không overwrite mù.
- **AtomicMoveNotSupportedException:** không thể “thử lại nhiều lần” để tự nhiên biến provider thành hỗ trợ atomic move, trừ khi môi trường đích thay đổi có chủ đích.
- **IOException khác:** cần biết lỗi cụ thể, loại thao tác, an toàn khi lặp lại và trạng thái tác động trước đó.

Đặc biệt với **ghi hoặc di chuyển**, khi exception xảy ra không phải lúc nào caller cũng biết chắc **chưa có side effect nào**. Một lần retry có thể tạo bản sao, ghi đè hoặc làm hỏng tính nhất quán nếu không có cơ chế idempotency.

Không đặt vòng retry chung quanh tất cả thao tác Files mà không có timeout, retry limit và tiêu chí phục hồi.

## 17. Dùng `try-with-resources` với file streams và channels

Một số `Files` API trả về các đối tượng `AutoCloseable` như `InputStream`, `OutputStream`, `BufferedReader`, `Stream<Path>` trong trường hợp `Files.list`, hoặc `Stream<String>` với `Files.lines`. Khi scope hiện tại sở hữu tài nguyên, nên đóng đúng lúc:

```java
static long countLines(Path path) throws IOException {
    try (java.util.stream.Stream<String> lines =
                 Files.lines(path)) {
        return lines.count();
    }
}
```

Đây là **phương thức minh họa**, cần import `Path`, `Files` và `IOException`.

Để phân tích đầy đủ lỗi:

1. **Mở nguồn** có thể ném checked `IOException`, bao gồm subclass NIO.
2. **Đọc trong pipeline** có thể xuất hiện `UncheckedIOException` theo hợp đồng `Files.lines` khi I/O trong lúc duyệt lỗi.
3. **Đóng nguồn** vẫn chạy khi rời `try-with-resources`; nếu body và close cùng lỗi, một lỗi có thể được gắn **suppressed** dưới ngoại lệ chính.
4. `getCause()` và `getSuppressed()` giúp điều tra mối liên hệ, không chỉ `getMessage()` ngoài cùng.

**Không trả một `Stream` sống ra khỏi scope đã đóng** rồi mong caller tiếp tục duyệt. Nếu API chuyển giao stream cho caller, phải công bố ai có trách nhiệm đóng và khi nào lỗi có thể phát sinh.

## 18. Thao tác file có thể ném nhiều loại lỗi ở các thời điểm khác nhau

Một lời gọi `Files.copy` hoặc `Files.move` có thể liên quan:

- Đường dẫn nguồn.
- Đường dẫn đích.
- Quyền đọc/ghi/truy cập directory.
- Tình trạng file đích tồn tại.
- Hành vi theo symbolic link.
- Tùy chọn copy/move được provider hỗ trợ.
- Lỗi I/O sau khi thao tác đã bắt đầu.

Không nên chỉ đọc tên method rồi đoán “nếu lỗi thì chắc là `AccessDeniedException`”. Mỗi thao tác có các điều kiện lỗi khác nhau; cần dùng javadoc API đang gọi khi triển khai chính sách đặc thù.

Ví dụ `Files.copy` có thể ném `FileAlreadyExistsException` nếu đích đã có và không chọn policy ghi đè, nhưng cũng có thể ném `NoSuchFileException` nếu nguồn bị xóa ngay trước lúc thực hiện, hoặc `IOException` khác vì thiết bị/network.

### Tùy chọn tạo mới và ghi đè

`Files.writeString(path, content)` theo cấu hình mặc định có thể tạo file nếu chưa tồn tại và ghi/truncate file hiện có. Nếu chỉ được phép tạo mới, thêm `StandardOpenOption.CREATE_NEW` phù hợp.

`Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING)` diễn đạt yêu cầu thay thế đích nếu được phép, nhưng không phải bảo đảm một giao dịch nguyên tử tổng quát. Đừng gộp khái niệm **cho phép overwrite** với **khả năng khôi phục nếu copy thất bại**.

## 19. Phân tích stack trace và message sao cho đúng

Ví dụ minh họa định dạng:

```text
java.nio.file.NoSuchFileException: data/missing.csv
    at ... <provider frame>
    at ... <application frame>
```

Hoặc:

```text
java.nio.file.AccessDeniedException: private/report.txt
    at ... <provider frame>
    at ... <application frame>
```

Đây **không phải bản stdout cố định**; số dòng, lớp nội bộ, provider và thông điệp có thể khác. Trên một số provider, reason có thể được thêm vào thông điệp. Đừng dựa vào exact text của stack trace để ra quyết định.

Quy trình chẩn đoán tốt:

1. **Đọc loại exception thực tế**.
2. **Xác định thao tác `Files` đang chạy** và vai trò source/target.
3. **Đọc `getFile()`, `getOtherFile()`, `getReason()`** nếu có `FileSystemException`.
4. **Kiểm tra đường dẫn tương đối/tuyệt đối**, file system, mount, quyền và sự tồn tại tại thời điểm cần điều tra; không mặc định trạng thái hiện tại giống lúc lỗi.
5. **Xem cause và suppressed** ở những tầng wrapper khi cần.
6. **Phân biệt lỗi kỹ thuật với chính sách nghiệp vụ**: missing optional khác missing required; denied có thể cần hành động vận hành.
7. **Bảo vệ dữ liệu nhạy cảm** khi ghi log và trả thông báo.

Không nên chỉ:

```java
System.out.println(ex.getMessage());
```

rồi coi đó là toàn bộ chẩn đoán. Khi logger hỗ trợ đối tượng `Throwable`, truyền cả exception ở ranh giới phù hợp để giữ stack/cause/suppressed, nhưng tránh log cùng sự cố nhiều lần ở mọi tầng.

## 20. Các tình huống thực tế để chọn handler

### Tình huống A: đọc cấu hình tùy chọn

**Quy tắc:** thiếu cấu hình thì dùng default; bị từ chối quyền phải báo lỗi.

Gợi ý: catch `NoSuchFileException` và trả `Optional.empty()`, để `IOException` khác đi lên. Chỉ dùng default khi missing thật sự là điều kiện nghiệp vụ hợp lệ.

### Tình huống B: upload file với tên không được trùng

**Quy tắc:** nếu tên đã tồn tại, từ chối thao tác thay vì ghi đè.

Gợi ý: dùng tạo file với `CREATE_NEW`; catch `FileAlreadyExistsException` và trả lỗi xung đột có cấu trúc. Không dựa vào `Files.exists` trước khi tạo vì race.

### Tình huống C: deploy file cấu hình phải được công bố nguyên tử

**Quy tắc:** chỉ xuất bản bản hoàn chỉnh.

Gợi ý: viết file tạm trong đúng vùng phù hợp, kiểm tra hoàn tất, sau đó cân nhắc `Files.move(..., ATOMIC_MOVE)`. Nếu nhận `AtomicMoveNotSupportedException`, phải **đánh giá lại yêu cầu**, không fallback không nguyên tử một cách mù quáng.

### Tình huống D: xóa thư mục chứa dữ liệu người dùng

**Quy tắc:** xóa một thư mục chỉ khi nó rỗng hoặc có xác nhận/chính sách riêng cho xóa đệ quy.

Gợi ý: `Files.delete`; nếu `DirectoryNotEmptyException`, từ chối hoặc chuyển sang quy trình được ủy quyền. Không tự chạy recursive delete chỉ để “fix exception”.

### Tình huống E: thống kê cây thư mục có symbolic links

**Quy tắc:** báo chính xác rằng có phần tử chưa duyệt được.

Gợi ý: `Files.walkFileTree` với chính sách `FOLLOW_LINKS` rõ, phân biệt `FileSystemLoopException` trong `visitFileFailed` khi cần, không nuốt mọi `IOException` rồi báo đã quét đủ.

## 21. Những hiểu lầm và sai sót thường gặp

| Sai lầm hoặc nhầm lẫn | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| “`NoSuchFileException` và `FileNotFoundException` là cùng một lớp” | Chúng là hai subtype khác nhau của `IOException` | Xem hierarchy và API nguồn |
| “Mọi file thiếu luôn báo `NoSuchFileException`” | Provider và ngữ cảnh có thể khác | Catch subtype hữu ích và fallback `IOException` |
| “`AccessDeniedException` là một `SecurityException`” | Một bên checked, một bên unchecked | Phân biệt chính sách hệ điều hành/provider và kiểm tra Java |
| “`Files.exists` trả false chứng minh file chắc chắn không tồn tại” | Có thể không xác định được trạng thái | Dựa vào thao tác thật và exception |
| “`isReadable` true thì `readString` không thể lỗi” | TOCTOU, quyền thay đổi, lỗi I/O khác | Xử lý lỗi tại thao tác thực |
| “`Path.of` tự kiểm tra file tồn tại” | Chỉ tạo đối tượng path | Kiểm tra khi thực hiện I/O |
| “Catch `IOException` trước subclass để tiện” | Nhánh subclass sau có thể unreachable | Bắt subtype trước |
| “Lỗi denied thì trả `Optional.empty()`” | Che sự cố vận hành/quyền | Chỉ dùng empty cho missing hợp lệ |
| “Thiếu file tức nên tạo file rỗng” | Có thể làm sai hợp đồng và che cấu hình hỏng | Phân biệt optional/required |
| “Đích tồn tại thì luôn cho `REPLACE_EXISTING`” | Có thể mất dữ liệu hoặc vi phạm idempotency | Yêu cầu overwrite rõ |
| “Không hỗ trợ atomic move thì luôn fallback” | Có thể phá yêu cầu nhất quán | Chỉ fallback khi chính sách cho phép |
| “`normalize()` đủ chặn mọi path traversal” | Symbolic links/race vẫn tồn tại | Có cơ chế kiểm soát path và quyền |
| “`Files.copy` lỗi nghĩa là chưa thay đổi gì” | Copy/di chuyển có thể có side effect một phần | Thiết kế phục hồi, kiểm tra trạng thái |
| “`getReason()` luôn có text” | Có thể null | Kiểm tra null và log có cấu trúc |
| “`FileSystemException.getFile()` trả `Path`” | Nó trả `String` | Không giả định canonical path |
| “`IOException` bắt tất cả lỗi NIO” | `InvalidPathException` và các lỗi unchecked không được bắt | Hiểu contract từng API |
| “Retry mọi `IOException` là an toàn” | Ghi file có thể không idempotent | Phân loại và giới hạn retry |
| “`Files.lines` tự đóng sau `count()`” | Terminal operation không tự đảm bảo `close` | Dùng `try-with-resources` |
| “Có message là đủ” | Mất loại lỗi, path phụ, cause và suppressed | Ghi log Throwable có ngữ cảnh an toàn |

## 22. Bài tập tự kiểm tra

**Bài A — Phân loại ngoại lệ**

`NoSuchFileException` và `AccessDeniedException` có phải checked exception không?

**Có.** Cả hai kế thừa `FileSystemException`, rồi `IOException`, nên compiler yêu cầu bắt hoặc khai báo khi lời gọi có thể để chúng thoát dưới một checked contract.

**Bài B — Catch theo thứ tự**

Có thể đặt `catch (IOException)` trước `catch (NoSuchFileException)` không?

**Không.** Handler cho subclass phía sau là unreachable vì handler cha đã bắt toàn bộ subclass.

**Bài C — Hai thuộc tính path**

Muốn lấy file chính và file thứ hai từ `FileSystemException`, gọi gì?

**`getFile()` và `getOtherFile()`**, với kết quả là chuỗi có thể null. `getReason()` cung cấp lý do bổ sung nếu có.

**Bài D — Optional config**

`NoSuchFileException` khi đọc một file cấu hình tùy chọn nên luôn làm ứng dụng crash không?

**Không nhất thiết.** Nếu hợp đồng cho phép missing, có thể dùng default hoặc `Optional.empty()`. Nhưng đừng áp dụng cùng chính sách cho `AccessDeniedException`.

**Bài E — Đếm quyền truy cập**

Nếu `Files.exists(path)` trả `true`, có được bỏ xử lý `IOException` ở `Files.readString(path)` không?

**Không.** File có thể bị xóa, thay đổi quyền hoặc gặp lỗi I/O giữa kiểm tra và đọc.

**Bài F — Đích đã tồn tại**

Khi `Files.createFile(path)` ném `FileAlreadyExistsException`, có nên tự động overwrite?

**Không mặc định.** Cần hợp đồng tạo mới, tránh mất dữ liệu và xử lý race bằng primitive phù hợp.

**Bài G — Không có atomic move**

Nếu `Files.move(..., ATOMIC_MOVE)` ném `AtomicMoveNotSupportedException`, fallback thường sang `Files.move(...)` có thể làm thay đổi điều gì?

**Mất bảo đảm nguyên tử của yêu cầu ban đầu.** Chỉ fallback nếu nghiệp vụ cho phép di chuyển không nguyên tử.

**Bài H — `getReason()` null**

Có thể nối `getReason().toLowerCase()` mà không kiểm tra không?

**Không.** `getReason()` có thể null; hơn nữa không nên phân loại lỗi bằng văn bản của reason.

**Bài I — File thiếu qua đường dẫn tương đối**

`Path.of("config/app.txt")` có đảm bảo tham chiếu thư mục chứa source code không?

**Không.** Nó được giải nghĩa theo ngữ cảnh file system/working directory của process.

**Bài J — Một lỗi đọc có thể phát sinh muộn**

`Files.lines(path)` mở thành công. Terminal `toList()` có thể gặp lỗi I/O trong lúc duyệt không?

**Có.** Một số lỗi trong quá trình duyệt stream có thể biểu hiện thành `UncheckedIOException`. Việc mở thành công không bảo đảm đọc toàn bộ thành công.

**Bài K — File-system provider không giống nhau**

Một demo cố thay quyền POSIX rồi kỳ vọng `AccessDeniedException` có đáng tin trên mọi Windows/Linux không?

**Không.** Hệ quyền, provider và đặc quyền process khác nhau. Muốn dạy phân loại, có thể dựng exception có cấu trúc; muốn test integration, phải có môi trường quyền được kiểm soát rõ.

**Bài L — Xóa thư mục**

`DirectoryNotEmptyException` có nghĩa `Files.delete` sẽ tự xóa các file con không?

**Không.** Nó báo rằng yêu cầu xóa thư mục không rỗng không thể được thực hiện theo điều kiện hiện tại; dọn cả cây là quyết định riêng.

## 23. Checklist áp dụng trong mã nguồn thực tế

Trước khi xử lý một thao tác NIO có thể thất bại:

1. **Biết hợp đồng của thao tác:** `Files.readString`, `copy`, `move`, `delete`, `walkFileTree` hay API nào?
2. **Biết file cần thiết hay tùy chọn:** missing là lỗi hay kết quả vắng mặt hợp lệ?
3. **Xử lý subtype trước:** `NoSuchFileException`, `AccessDeniedException`, `FileAlreadyExistsException`... khi chính sách thực sự khác nhau.
4. **Có fallback cho `IOException` còn lại:** không đoán mọi thất bại thuộc hai loại quen thuộc.
5. **Không nhầm checked và unchecked:** `InvalidPathException`/`SecurityException` không bị bắt bởi `IOException`.
6. **Giữ nguyên nhân gốc:** nếu bọc lỗi ở tầng service, truyền object `cause` thay vì chỉ sao chép message.
7. **Đọc thông tin path có cấu trúc:** `getFile()`, `getOtherFile()`, `getReason()`, kiểm tra null.
8. **Không lộ path nội bộ:** log và response phải theo phân quyền; không in secret/đường dẫn nhạy cảm ra client.
9. **Tránh kiểm tra trước rồi tin tuyệt đối:** `exists`/`isReadable` không ngăn race.
10. **Dùng option tạo mới/ghi đè rõ:** `CREATE_NEW` khác `CREATE` và `REPLACE_EXISTING`.
11. **Kiểm soát overwrite và delete:** không tự động xóa/ghi đè dữ liệu ngoài hợp đồng.
12. **Cân nhắc symbolic links và traversal:** xác định chính sách `NOFOLLOW_LINKS` và phạm vi path.
13. **Với atomic move, đừng fallback tùy tiện:** giữ đúng yêu cầu nhất quán.
14. **Đóng tài nguyên đúng scope:** dùng `try-with-resources` cho streams/channels/`Files.lines`/`Files.list`.
15. **Kiểm tra trạng thái sau lỗi copy/move:** có thể xuất hiện tác động một phần, tùy thao tác.
16. **Đánh giá retry và idempotency:** chỉ thử lại khi có căn cứ và giới hạn.
17. **Kiểm thử trên provider mục tiêu:** không suy ra hành vi quyền Linux cho Windows hoặc provider zip/cloud.
18. **Không lấy message làm giao thức:** loại exception và mã ứng dụng ổn định mới là cơ sở phân nhánh.

## Kết luận

`NoSuchFileException`, `AccessDeniedException` và các subclass của `FileSystemException` giúp Java NIO phân biệt **đường dẫn thiếu**, **quyền bị từ chối** và những thất bại filesystem khác. Phân biệt đúng tạo điều kiện cho ứng dụng xử lý **missing optional**, **permission failure**, **xung đột đích đã tồn tại**, **không hỗ trợ atomic move** hoặc **thư mục chưa rỗng** theo những chính sách khác nhau.

Dù vậy, **loại lỗi cụ thể còn phụ thuộc thao tác và file-system provider**; không có một quy tắc “mọi lỗi thiếu/denied đều luôn biểu diễn duy nhất một subtype” trên mọi môi trường. Hãy bắt subtype khi có chính sách rõ ràng, giữ handler `IOException` tổng quát, đọc `getFile()/getOtherFile()/getReason()` có kiểm tra null, bảo toàn cause và xử lý tài nguyên/race/permissions một cách có trách nhiệm. Một chương trình quản lý file đáng tin phải xem **lỗi là một phần của hợp đồng I/O**, không phải sự cố để nuốt rồi tiếp tục như đã thành công.