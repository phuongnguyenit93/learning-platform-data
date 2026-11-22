# createTempFile, createTempDirectory và phạm vi dọn dẹp trong Java

Ứng dụng Java thường phải tạo dữ liệu trung gian: file tải về đang xử lý, dữ liệu export, file đầu vào cho thư viện khác, vùng giải nén, ảnh chuyển đổi, hoặc nơi kiểm thử có thể ghi dữ liệu mà không chạm vào file thật của người dùng. Java NIO.2 cung cấp **`Files.createTempFile(...)`** và **`Files.createTempDirectory(...)`** để tạo file/thư mục tạm với tên riêng trong một filesystem.

Điều quan trọng không chỉ là tạo được file tạm. Ứng dụng còn phải xác định rõ **nơi tạo**, **ai sở hữu**, **khi nào dọn**, **chỉ được xóa những gì**, **thứ tự đóng tài nguyên và xóa**, và **cách xử lý lỗi dọn dẹp**. Từ “temporary” không có nghĩa “JVM tự động xóa an toàn mọi thứ sau khi dùng”.

Bài này thuộc nhóm **Thao tác tệp** trong Java Core I/O; ví dụ dùng Java 17+.

## 1. Temporary file và temporary directory là gì?

- **Temporary file (tệp tạm):** tệp được tạo cho một mục đích có vòng đời giới hạn, ví dụ ghi nội dung trước khi upload hoặc lưu kết quả trung gian.
- **Temporary directory (thư mục tạm):** thư mục được tạo để gom một nhóm file/thư mục tạm phục vụ cùng một tác vụ, ví dụ một lượt xử lý ảnh.
- **Phạm vi dọn dẹp (cleanup scope):** tập hợp tài nguyên mà thành phần hiện tại có quyền và trách nhiệm xóa sau khi công việc kết thúc.

Sơ đồ:

```text
Ứng dụng
   |
   | Files.createTempDirectory("my-job-")
   v
[temp root do ứng dụng tạo]
   |
   +-- Files.createTempFile(root, "input-", ".bin")
   |       -> file trung gian
   |
   +-- Files.createTempDirectory(root, "stage-")
           |
           +-- file đầu ra
           +-- nhiều file nhỏ

Công việc kết thúc (thành công hoặc lỗi)
   |
   +-- đóng stream/channel/writer đang mở
   +-- xóa file và mục con thuộc root
   +-- xóa root sau cùng
   |
   v
KHÔNG xóa cha chung của root hoặc file của người khác
```

Nếu ứng dụng tạo thư mục gốc riêng bằng `createTempDirectory`, nơi đó thường là **ranh giới cleanup thích hợp** cho một công việc. Nhưng nếu ứng dụng chỉ tạo một file tạm trong thư mục chung, quyền dọn dẹp thông thường chỉ áp dụng cho **file đó**, không phải toàn bộ thư mục chứa nó.

## 2. API tạo file/thư mục tạm: các overload chính

Các phương thức thuộc `java.nio.file.Files`:

```java
// Không truyền thư mục: tạo ở vị trí tạm mặc định của provider.
Path file1 = Files.createTempFile("demo-", ".txt");
Path dir1  = Files.createTempDirectory("demo-");

// Chọn thư mục cha đã tồn tại:
Path base  = Path.of("work");
Path file2 = Files.createTempFile(base, "part-", ".bin");
Path dir2  = Files.createTempDirectory(base, "job-");
```

Đây là **mảnh mã minh họa**: cần import `java.nio.file.*`; `base` phải tồn tại, là thư mục và có quyền tạo mục. Các lời gọi có thể ném `IOException` và những ngoại lệ khác khi đối số/thuộc tính không hợp lệ.

Chữ ký tổng quát có tham số `FileAttribute<?>...` tùy chọn:

```java
Files.createTempFile(String prefix, String suffix,
                     FileAttribute<?>... attrs)

Files.createTempFile(Path dir, String prefix, String suffix,
                     FileAttribute<?>... attrs)

Files.createTempDirectory(String prefix,
                          FileAttribute<?>... attrs)

Files.createTempDirectory(Path dir, String prefix,
                          FileAttribute<?>... attrs)
```

**Kết quả là một `Path` trỏ tới tài nguyên đã thực sự được tạo** — khác `Path.of(...)` hay `new File(...)` chỉ dựng đối tượng biểu diễn đường dẫn. Nếu tạo thành công, file tạm là file mới (ban đầu rỗng), còn thư mục tạm là thư mục mới.

| Lệnh | Tạo gì? | Kết quả | Yêu cầu |
| --- | --- | --- | --- |
| `Path.of("x.tmp")` | Không tạo gì trên đĩa | `Path` | Chỉ cần đường dẫn hợp lệ |
| `Files.createTempFile("x-", ".tmp")` | File tạm thật | `Path` | Có vị trí tạm mặc định khả dụng |
| `Files.createTempDirectory("x-")` | Thư mục tạm thật | `Path` | Có vị trí tạm mặc định khả dụng |
| `Files.createTempFile(base, "x-", ".tmp")` | File mới bên trong `base` | `Path` | `base` là thư mục hiện có |
| `Files.createTempDirectory(base, "x-")` | Thư mục mới bên trong `base` | `Path` | `base` là thư mục hiện có |
| `Files.createFile(path)` | File mới tại tên `path` do ứng dụng chọn | `Path` | Path chưa tồn tại |
| `Files.createDirectory(path)` | Thư mục mới tại tên `path` do ứng dụng chọn | `Path` | Path cha tồn tại |

### Prefix, suffix và tên tạo ra

- `prefix` là phần đầu của tên do hệ thống tạo, ví dụ `report-`.
- `suffix` là phần cuối **chỉ của file tạm**, ví dụ `.csv` hoặc `.tmp`.
- Phần tên ở giữa do provider tạo để chọn một tên chưa được sử dụng.
- Java không bảo đảm tên cụ thể hoặc một độ dài cố định cho đoạn được sinh tự động. **Đừng kiểm thử bằng cách đoán tên file đầy đủ**.
- Nếu `prefix` hoặc `suffix` chứa ký tự/chuỗi path không được filesystem chấp nhận, thao tác có thể thất bại.
- Với overload file, `suffix == null` thường được xử lý như hậu tố mặc định `.tmp` theo hợp đồng API; hãy truyền rõ hậu tố khi ứng dụng cần một đuôi cụ thể.
- Đừng đưa dữ liệu bí mật như token, mã xác thực hoặc thông tin cá nhân vào prefix/suffix: tên mục có thể lộ trong log, công cụ quản lý file, trace hoặc danh sách thư mục.

Tên tạm là một **danh tính đường dẫn**, không phải mật khẩu hoặc cơ chế bảo mật. Độ khó đoán tên không thay cho quyền truy cập filesystem.

## 3. Tạo ở đâu: thư mục tạm mặc định và thư mục cụ thể

Khi dùng overload không nhận `Path dir`:

```java
Path temp = Files.createTempFile("app-", ".tmp");
Path folder = Files.createTempDirectory("app-");
```

Java dùng **vị trí tạm mặc định của provider**. Trong môi trường JDK thông thường, cấu hình liên quan đến thư mục tạm có thể được quan sát qua system property `java.io.tmpdir`:

```java
String configured = System.getProperty("java.io.tmpdir");
System.out.println(configured);
```

Mảnh mã trên cho biết cấu hình tại thời điểm đọc, **không phải bảo đảm** tất cả FileSystemProvider sẽ dùng chính đường dẫn đó. Không mã hóa cứng `/tmp` hay `C:\Temp` trong chương trình chạy đa nền tảng. Cũng đừng kết luận file tạm nằm trong thư mục dự án hoặc thư mục chứa class.

Nếu muốn kiểm soát rõ nơi tạo, truyền `Path dir` đã được tạo:

```java
Path workspace = Files.createTempDirectory("my-app-");
Path tempFile = Files.createTempFile(workspace, "data-", ".txt");
```

`tempFile` thuộc thư mục `workspace` do lượt chạy của ứng dụng tạo ra. Dùng đường dẫn rõ ràng này thường giúp **theo dõi ownership và cleanup** tốt hơn so với tạo rải rác nhiều file trong thư mục tạm chung.

### Những điều không nên giả định

- Thư mục tạm mặc định luôn có dung lượng đủ hoặc còn hoạt động.
- Mọi máy đều dùng cùng hệ thống tệp, separator và quy tắc quyền truy cập.
- File tạm chắc chắn bị xóa khi JVM kết thúc.
- `createTempFile` tự tạo mọi thư mục cha được đưa vào.
- Hai chương trình có cùng prefix sẽ tạo đúng cùng tên.
- Một đường dẫn đã tạo sẽ không bao giờ bị tiến trình khác xóa hoặc đổi tên.

Nếu file tạm tham gia xử lý dữ liệu quan trọng, phải có kiểm soát lỗi I/O, giới hạn kích thước và chính sách lưu trữ/khôi phục phù hợp.

## 4. Tạo là thật và thường có kiểm tra tên mới nguyên tử

Khi `Files.createTempFile(...)` thành công, provider tạo một file **mới**; phương thức không chỉ trả một cái tên để “có thể tạo sau”. Tương tự, `Files.createTempDirectory(...)` tạo thư mục mới.

Điểm thuận lợi về an toàn:

```java
Path output = Files.createTempFile("download-", ".part");
```

`output` đã là file được tạo, không phải tên dự kiến lấy từ bộ tạo số ngẫu nhiên của bạn. Provider chọn tên mới và thực hiện thao tác tạo theo hợp đồng API, tránh kiểu mã dễ bị race:

```java
// Không nên tự thiết kế:
Path candidate = Path.of("work", "temp-" + System.currentTimeMillis());
if (!Files.exists(candidate)) {
    Files.createFile(candidate); // Một tiến trình khác có thể chen vào.
}
```

Mảnh mã thứ hai chỉ minh họa lỗi thiết kế (*time-of-check to time-of-use*). Khi cần file tạm mới, gọi trực tiếp `Files.createTempFile(...)`. Khi cần tạo file tại một **tên cố định** và thất bại nếu đã có, dùng `Files.createFile(...)` hoặc `StandardOpenOption.CREATE_NEW`.

Tuy nhiên, sau khi tài nguyên được tạo, ứng dụng vẫn có thể gặp race nếu đóng rồi mở lại tên file trong thư mục có thể bị người khác sửa. Không cho rằng việc tạo mới ở ban đầu làm mọi thao tác sau đó trở thành an toàn tuyệt đối. Với dữ liệu nhạy cảm, quan tâm quyền truy cập thư mục cha, owner, symlink/hard link, và giữ handle khi cần.

## 5. Một ví dụ Java 17+ hoàn chỉnh: tạo rồi dọn một workspace tạm

Ví dụ sử dụng **root tạm riêng** cho một lượt chạy. Bên trong root, ta tạo một thư mục con, một file text và một file nhị phân; ghi, đọc, kiểm tra rồi dọn tất cả bằng `Files.walkFileTree(...)`.

Lưu vào file `TempWorkspaceDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class TempWorkspaceDemo {

    private static void deleteOwnedTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(Path file,
                                             BasicFileAttributes attrs)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(Path dir,
                                                      IOException error)
                    throws IOException {
                if (error != null) {
                    throw error;
                }
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws IOException {
        // Root được tạo mới riêng cho lần chạy này.
        Path root = Files.createTempDirectory("lesson-temp-");

        try {
            Path nested = Files.createTempDirectory(root, "batch-");
            Path text = Files.createTempFile(root, "note-", ".txt");
            Path binary = Files.createTempFile(nested, "data-", ".bin");

            Files.writeString(text, "Hello", StandardCharsets.UTF_8);
            Files.write(binary, new byte[] { 1, 2, 3 });

            System.out.println("root directory: "
                    + Files.isDirectory(root));
            System.out.println("nested directory: "
                    + Files.isDirectory(nested));
            System.out.println("text file: "
                    + Files.isRegularFile(text));
            System.out.println("text: "
                    + Files.readString(text, StandardCharsets.UTF_8));
            System.out.println("binary length: " + Files.size(binary));
        } finally {
            // Chỉ xóa root mà lượt chạy vừa tạo và các mục bên trong.
            deleteOwnedTree(root);
        }

        System.out.println("root removed: " + Files.notExists(root));
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac TempWorkspaceDemo.java
java TempWorkspaceDemo
```

Stdout trong điều kiện thư mục tạm tạo/ghi/xóa được và không có tiến trình khác can thiệp:

```text
root directory: true
nested directory: true
text file: true
text: Hello
binary length: 3
root removed: true
```

Đã kiểm tra hành vi tương ứng với JDK. Tên root, folder và file được tạo là **khác nhau ở mỗi lần chạy**; ví dụ không in tên động nên đầu ra dễ đối chiếu.

Giải thích chi tiết:

1. `Files.createTempDirectory("lesson-temp-")` **tạo thư mục thật**, được xem là phạm vi mà ví dụ sở hữu.
2. `Files.createTempDirectory(root, "batch-")` tạo thư mục con bên trong root; `Files.createTempFile(root, "note-", ".txt")` và `Files.createTempFile(nested, "data-", ".bin")` tạo **hai file rỗng**.
3. `Files.writeString(...)` và `Files.write(...)` đưa dữ liệu vào file đã tồn tại. Trong ví dụ, ta dùng API ghi tiện ích với các tùy chọn mặc định để minh họa, nên có thể truncate nội dung có sẵn tại đường dẫn. Với pipeline cần bảo đảm danh tính file trước nguy cơ thay thế đường dẫn, nên kiểm soát cách mở stream và quyền truy cập thư mục.
4. `Files.readString(...)` và `Files.size(...)` kiểm tra nội dung, kích thước file.
5. `finally` được chạy khi khối `try` hoàn tất bình thường hoặc phát sinh ngoại lệ Java. Nó gọi `deleteOwnedTree(root)` để dọn cây thư mục.
6. `walkFileTree` mặc định **không theo symbolic link** vì ví dụ không truyền `FileVisitOption.FOLLOW_LINKS`. `visitFile` xóa file/link, còn `postVisitDirectory` chỉ xóa thư mục khi đã xử lý con của nó.
7. `Files.notExists(root)` sau đó cho biết root đã biến mất trong trường hợp thành công. Nó không phải bằng chứng vĩnh viễn rằng đường dẫn sẽ không bị tạo lại.

Với ứng dụng thật, cả giai đoạn xử lý và cleanup có thể ném `IOException`; phải thiết kế cách ưu tiên và ghi nhận lỗi thay vì luôn coi cleanup không bao giờ thất bại.

## 6. Vì sao dọn thư mục phải theo thứ tự con trước cha?

`Files.delete(path)` xóa file hoặc thư mục **rỗng** tương ứng; Java không coi lời gọi này là lệnh xóa đệ quy tùy tiện. Nếu thư mục còn phần tử:

```java
Files.delete(root);
```

có thể ném `DirectoryNotEmptyException`. `Files.deleteIfExists(root)` chỉ khác ở việc không ném lỗi riêng khi **root không tồn tại**; nó **không** tự động xóa các phần tử con.

Vì vậy:

```text
my-job-123/
  note-12.txt
  batch-34/
    data-56.bin
```

Thứ tự hợp lý là xóa `data-56.bin`, xóa `batch-34`, xóa `note-12.txt`, rồi xóa `my-job-123`. Khi có nhiều cấp và số mục lớn, `Files.walkFileTree` phù hợp hơn nhiều lệnh delete thủ công.

Các hook của `SimpleFileVisitor`:

| Phương thức | Vai trò trong cleanup |
| --- | --- |
| `visitFile(file, attrs)` | Xóa file thường hoặc entry được thăm như file; theo mặc định symbolic link không bị truy theo |
| `postVisitDirectory(dir, error)` | Sau khi duyệt xong con, xóa chính thư mục |
| `visitFileFailed(path, error)` | Quyết định làm gì nếu một mục không thể được truy cập |
| `preVisitDirectory(dir, attrs)` | Trước khi duyệt phần con của thư mục |

Nếu một thao tác duyệt/xóa thất bại, xử lý đúng `IOException`; không nên bỏ qua mọi lỗi một cách im lặng. Trong code ví dụ, `postVisitDirectory` kiểm tra `error != null` trước khi xóa. Nếu muốn dọn “best effort”, có thể tập hợp nhiều lỗi để báo cáo sau, nhưng phải có chủ đích và tránh tuyên bố đã dọn sạch khi vẫn còn dữ liệu.

### Một cách khác: Files.walk với thứ tự ngược

Có thể thu các đường dẫn bằng `Files.walk(root)`, sắp xếp sao cho các con đứng trước cha và gọi `Files.delete(...)`. Tuy nhiên, `Files.walk(...)` trả về **Stream có tài nguyên phải đóng**, logic sắp xếp/duyệt phải xử lý ngoại lệ và symbolic link rõ ràng. `walkFileTree` thường dễ kiểm soát lỗi I/O, thứ tự và callback hơn cho cleanup đệ quy.

Dù chọn cách nào, **chỉ bắt đầu từ root do ứng dụng thực sự sở hữu**.

## 7. Phạm vi dọn dẹp: xóa đúng phần mình tạo

Ba kịch bản phổ biến:

| Mô hình tạo tạm | Phạm vi được quản lý | Khi kết thúc |
| --- | --- | --- |
| Một `createTempFile(...)` trong thư mục tạm dùng chung | **Chính file đó** | `Files.deleteIfExists(tempFile)` sau khi đóng nguồn |
| Một `createTempDirectory(...)` riêng cho job | **Thư mục đó và con thuộc job** | Xóa con trước, xóa root sau |
| Tạo file tạm trong thư mục người dùng chỉ định | **File do ứng dụng tạo**, không phải toàn bộ thư mục người dùng | Xóa file do mình sở hữu; không xóa directory cha |
| Job tạo output cuối cùng cần giữ | Chỉ các file trung gian; **output hoàn chỉnh không phải rác** | Giữ/publish output, dọn intermediate |
| Temp resource được bàn giao cho component khác | Theo hợp đồng quyền sở hữu | Không xóa trước khi bên nhận hoàn tất |

**Một quy tắc tuyệt đối:** Đừng lấy `System.getProperty("java.io.tmpdir")` rồi xóa toàn bộ nội dung của thư mục đó. Nhiều ứng dụng và tài khoản có thể dùng chung nơi này. Root tạm do một job tạo khác với **thư mục tạm dùng chung của hệ điều hành**.

Trước khi gọi hàm xóa cây thư mục:

1. Bảo đảm root được trả về bởi thao tác tạo **dành riêng cho job này**.
2. Không chấp nhận root tùy ý từ input chưa được kiểm tra.
3. Không dùng đường dẫn rỗng, thư mục home hoặc thư mục tạm hệ thống làm root cleanup.
4. Không chủ động theo symbolic link trỏ ra ngoài root.
5. Tính đến việc dữ liệu có thể đổi tên, chuyển vị trí hoặc bị tác nhân khác thay thế giữa lúc tạo và dọn.
6. Không xóa output cuối đã được bàn giao hoặc dữ liệu được yêu cầu lưu lại.

Trong hệ thống xử lý nhiều job, một workspace tạm riêng cho mỗi job giúp theo dõi và dọn dẹp đúng phần thuộc job đó, thay vì quét một thư mục chung rồi đoán file nào là “của mình”.

## 8. try-with-resources cho stream khác với cleanup file/thư mục

`try-with-resources` tự gọi `close()` với những đối tượng `AutoCloseable` như `InputStream`, `OutputStream`, `Reader`, `Writer` và `FileChannel`. Tuy nhiên, **`Path` và `File` không phải tài nguyên `AutoCloseable`**. Đóng một stream không mặc định xóa file vật lý nằm bên dưới.

Ví dụ:

```java
Path temp = Files.createTempFile("download-", ".bin");

try {
    try (OutputStream out = Files.newOutputStream(temp)) {
        out.write(new byte[] { 1, 2, 3 });
    } // Stream đã đóng trước khi file bị xóa.

    // Dùng dữ liệu tại temp khi stream không còn mở.
} finally {
    Files.deleteIfExists(temp);
}
```

Đây là mảnh mã cần import `java.nio.file.Files`, `Path` và `java.io.OutputStream`, đồng thời xử lý `IOException`. Với ví dụ này, resource lifecycle có hai tầng:

- **Tầng 1:** Đóng stream bằng `try-with-resources`.
- **Tầng 2:** Xóa file tạm bằng `finally`.

Trên một số hệ điều hành (đặc biệt Windows), file đang mở có thể bị từ chối xóa do chia sẻ handle. Trên hệ khác, unlink file đang mở có thể thành công nhưng handle vẫn tồn tại cho tới khi đóng. Không xây dựng code dựa trên một hành vi duy nhất của mọi OS. **Đóng handle trước rồi dọn file** là nguyên tắc portable.

### Không quên resource khi cleanup lỗi

`try-with-resources` còn xử lý ngoại lệ *suppressed* khi cả phần xử lý chính và thao tác `close()` báo lỗi. Nhưng đoạn `try { work(); } finally { cleanup(); }` thông thường có thể để exception từ `cleanup()` che khuất exception gốc của `work()` nếu cả hai cùng thất bại.

Với logic phức tạp, có thể bọc workspace tạm vào lớp `AutoCloseable` để dùng `try-with-resources`:

```java
final class TempWorkspace implements AutoCloseable {
    private final Path root;

    TempWorkspace() throws IOException {
        this.root = Files.createTempDirectory("job-");
    }

    Path root() {
        return root;
    }

    @Override
    public void close() throws IOException {
        // deleteOwnedTree(root) là helper duyệt/xóa riêng
        // được triển khai theo mô hình walkFileTree ở phần trên.
        deleteOwnedTree(root);
    }
}
```

Đây là **mảnh mã thiết kế**, không độc lập: cần helper `deleteOwnedTree` và import `java.nio.file.*`/`java.io.IOException`. Khi có lớp hoàn chỉnh, sử dụng:

```java
try (TempWorkspace workspace = new TempWorkspace()) {
    process(workspace.root());
}
```

Đây cũng là mảnh mã có `process` do ứng dụng định nghĩa. Nếu `process` ném exception và `close` cũng thất bại, try-with-resources sẽ đặt lỗi đóng ở danh sách **suppressed** thay vì thay thế lỗi chính, giúp chẩn đoán. Phải đảm bảo `close()` chỉ dọn root do đối tượng tạo, tránh vô ý nhận một thư mục người dùng làm root.

## 9. deleteOnExit không phải giải pháp cleanup tổng quát

`java.io.File.deleteOnExit()` đăng ký xóa một **đường dẫn** khi JVM kết thúc **bình thường**:

```java
File temp = File.createTempFile("demo-", ".tmp");
temp.deleteOnExit();
```

Mảnh mã cần import `java.io.File` và xử lý `IOException`.

Giới hạn rất quan trọng:

- Không xóa ngay sau khi công việc hoàn tất.
- Không đảm bảo chạy khi tiến trình bị kill, mất điện hoặc JVM dừng bất thường.
- Không tự dọn toàn bộ cây thư mục đệ quy. Nếu đăng ký directory còn chứa file, việc xóa directory có thể không thành công.
- Danh sách đường dẫn đã đăng ký được JVM giữ tới lúc kết thúc; đăng ký rất nhiều file trong chương trình server chạy lâu có thể gây tích lũy thông tin không cần thiết.
- Không cho biết ngay tại thời điểm xử lý rằng xóa đã thành công.
- Không thay cho đóng stream/handle.

Do đó `deleteOnExit()` có thể phù hợp làm phương án phụ cho ví dụ CLI nhỏ, nhưng **cleanup tường minh** trong `finally` hoặc một workspace có `AutoCloseable` là cách tốt hơn để quản lý vòng đời một lượt xử lý.

Nếu ứng dụng cần khôi phục rác tạm sau sự cố, một tác vụ dọn rác theo tuổi file (*janitor*) có thể là bổ trợ, nhưng phải sử dụng **namespace/metadata sở hữu rõ ràng**, giới hạn tuổi, kiểm soát quyền và tránh xóa tác vụ còn chạy. Không chỉ dựa vào file có hậu tố `.tmp`.

## 10. Quyền truy cập khi tạo dữ liệu tạm nhạy cảm

File tạm có thể chứa thông tin nội bộ hoặc cá nhân. Đừng mặc định rằng “ở thư mục tạm” nghĩa là “chỉ tiến trình hiện tại đọc được”.

Theo tài liệu Java, `Files.createTempFile`/`createTempDirectory` có thể tạo tài nguyên với thuộc tính/quyền được quy định bằng `FileAttribute<?>... attrs`, nếu provider hỗ trợ. Ở filesystem POSIX, ví dụ file chỉ owner đọc/ghi:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

Path secret = Files.createTempFile(
        "secret-", ".bin",
        PosixFilePermissions.asFileAttribute(
                PosixFilePermissions.fromString("rw-------")));
```

Đây là **mảnh mã trên filesystem hỗ trợ POSIX attributes**. Không phải mọi Windows hoặc provider NIO đều hỗ trợ attribute `posix:permissions`; có thể ném `UnsupportedOperationException` hoặc lỗi khác. Đừng giả vờ ví dụ portable nguyên xi.

Nếu cần workspace riêng với quyền owner:

```java
Path privateRoot = Files.createTempDirectory(
        "private-job-",
        PosixFilePermissions.asFileAttribute(
                PosixFilePermissions.fromString("rwx------")));
```

Mảnh mã cần import `java.nio.file.*` và `java.nio.file.attribute.PosixFilePermissions`, xử lý `IOException`, chỉ dùng khi provider hỗ trợ POSIX. Trên các nền tảng khác, thiết kế ACL/permissions phù hợp với hệ điều hành và tổ chức.

**Các nguyên tắc chung:**

1. Đặt file nhạy cảm trong thư mục riêng có quyền hạn chế.
2. Không dựa chỉ vào tên ngẫu nhiên như một biện pháp bảo vệ.
3. Không lưu mật khẩu/token trong tên file hoặc ghi nguyên nội dung bí mật ra log.
4. Hạn chế file tạm tồn tại quá lâu và tránh chia sẻ không cần thiết với ứng dụng khác.
5. Không giả định `Files.delete` tương đương xóa an toàn không thể khôi phục ở cấp thiết bị lưu trữ; filesystem, snapshot hoặc backup có thể vẫn lưu dấu dữ liệu.
6. Sử dụng đúng chiến lược cho dữ liệu rất nhạy cảm, bao gồm mã hóa và chính sách lưu trữ khi cần.

## 11. Lỗi thường gặp trong cleanup thực tế

### 11.1. Chỉ gọi deleteIfExists trên thư mục cha

`Files.deleteIfExists(workspace)` không xóa mọi file con. Nếu còn entry bên dưới, nó có thể ném `DirectoryNotEmptyException`. Cần xóa file và thư mục con trước (hoặc dùng visitor).

### 11.2. Xóa root chưa chắc thuộc về mình

Một biến `Path root` lấy từ config chưa đảm bảo nó là workspace do ứng dụng tạo. Nếu truyền nhầm `Path.of(System.getProperty("java.io.tmpdir"))` vào helper đệ quy, hậu quả có thể phá hủy dữ liệu của chương trình khác. Chỉ dọn cây root **mới được tạo riêng và đã ghi nhận ownership**.

### 11.3. Không đóng file stream trước khi xóa

Tệp có thể còn handle đang mở; Windows thường hạn chế xóa tùy kiểu chia sẻ. Dùng try-with-resources bao bọc stream trước, rồi xóa file khi handle đã đóng.

### 11.4. Coi cleanup trong finally là luôn thành công

`finally` bảo đảm **thử chạy** cleanup khi luồng điều khiển Java đi qua, không đảm bảo thao tác xóa thực sự thành công. Disk lỗi, permission đổi, file bị khóa, race hoặc process chết đều có thể để lại file tạm. Ghi nhận lỗi dọn dẹp và thiết kế xử lý rác còn sót.

### 11.5. Dựa vào tên để quyết định quyền xóa

Tên bắt đầu `temp-` không chứng minh file do ứng dụng tạo. Một phần mềm khác có thể dùng prefix tương tự. Cần danh sách tài nguyên đã tạo hoặc root riêng và xác thực phạm vi.

### 11.6. Theo symlink ra ngoài root

`Files.walkFileTree(root)` **mặc định không bật `FOLLOW_LINKS`**. Đừng bật option này khi dọn cây tạm nếu không có nhu cầu và mô hình bảo mật rõ, vì một link bên trong root có thể trỏ tới vị trí khác ngoài phạm vi. Ngay cả khi không theo links, vẫn có rủi ro race nếu người khác được phép sửa cây trong lúc duyệt; thư mục root chỉ owner ghi giúp giảm rủi ro.

### 11.7. Không kiểm soát dung lượng

File tạm có thể làm đầy ổ đĩa. Một ứng dụng upload/giải nén có thể bị “zip bomb” hoặc input quá lớn làm tăng số file và byte. Đặt giới hạn tổng bytes, số file, độ sâu thư mục, thời gian xử lý; không xem thư mục tạm là bộ nhớ không giới hạn.

### 11.8. Tạo quá nhiều file chỉ để xử lý dữ liệu rất nhỏ

Một vài byte cần xử lý nhanh có thể giữ trong `byte[]`/`ByteArrayOutputStream` thay vì tạo file tạm thật. File tạm có chi phí I/O và đồng bộ metadata, nên dùng khi thư viện yêu cầu `Path`, cần xử lý dữ liệu lớn hoặc muốn tránh giữ toàn bộ dữ liệu trong RAM.

## 12. Cách tổ chức scope trong ứng dụng nhiều bước

Một pipeline xử lý file thường có ba dạng tài nguyên:

| Loại | Ví dụ | Quy tắc vòng đời |
| --- | --- | --- |
| **Intermediate** | `raw-input.tmp`, file giải nén, preview | Dọn sau khi job xong |
| **Output đã publish** | `reports/final.csv` | Giữ lại theo chính sách dữ liệu |
| **Shared external input** | File upload đã chuyển quyền cho storage khác, file người dùng cung cấp | Không xóa trừ khi hợp đồng cho phép |

Ví dụ quy trình export an toàn hơn việc ghi trực tiếp vào file cuối:

```text
(1) Tạo temp file cùng filesystem/thư mục đích khi phù hợp
(2) Ghi kết quả vào temp, flush và đóng stream
(3) Xác minh output
(4) Thử chuyển file tạm sang file đích bằng Files.move(...)
(5) Dọn file tạm nếu chưa được chuyển giao thành công
```

Một ví dụ *mảnh mã* minh họa:

```java
Path finalPath = Path.of("reports", "final.txt");
Path parent = finalPath.toAbsolutePath().getParent();
Files.createDirectories(parent);

Path temp = Files.createTempFile(parent, "final-", ".tmp");
try {
    Files.writeString(temp, "Kết quả", StandardCharsets.UTF_8);
    Files.move(temp, finalPath, StandardCopyOption.REPLACE_EXISTING);
} finally {
    Files.deleteIfExists(temp);
}
```

Cần import `java.nio.file.*`, `java.nio.charset.StandardCharsets` và xử lý `IOException`. File tạm được tạo **cùng thư mục cha** với đích để tránh một số vấn đề di chuyển qua filesystem khác, nhưng **`Files.move` không mặc nhiên bảo đảm atomic**. Nếu định dạng và provider cần tính nguyên tử, có thể xem xét `StandardCopyOption.ATOMIC_MOVE`, đồng thời phải xử lý trường hợp provider không hỗ trợ bằng `AtomicMoveNotSupportedException`. Không giả định một lần `Files.move(..., REPLACE_EXISTING)` đảm bảo độ bền dữ liệu sau sự cố mất điện.

Đặc biệt, khi `move` thành công, `temp` không còn là file ở path cũ, vì thế `deleteIfExists(temp)` trong `finally` sẽ không xóa output cuối. Khi `move` thất bại, `finally` thử dọn temp. Nếu file kết quả đã được publish và phải giữ lại, **không đưa `finalPath` vào scope dọn rác**.

## 13. Xử lý lỗi khi đang tạo tài nguyên tạm

Các phương thức tạo temp có thể thất bại:

- `IOException` do quyền, đĩa đầy, hết inode, thư mục cha biến mất, provider không đáp ứng hoặc lỗi I/O khác.
- `SecurityException` khi môi trường/chính sách bảo mật không cho phép thao tác tương ứng.
- `IllegalArgumentException` hoặc ngoại lệ tương tự khi prefix/suffix hoặc thuộc tính không hợp lệ với filesystem.
- `UnsupportedOperationException` khi dùng file attribute mà provider không hỗ trợ.

Không nên bắt `IOException` rồi chỉ trả `null` và làm chương trình tiếp tục như thể đã có file; trạng thái đó thường dẫn tới `NullPointerException` ở nơi khác và che giấu lỗi thật. Báo lỗi với ngữ cảnh đủ rõ (job ID, loại thao tác và vị trí được phép ghi log) mà không vô tình ghi dữ liệu nhạy cảm.

**Một bẫy về vị trí `try/finally`:**

```java
Path temp = Files.createTempFile("job-", ".tmp");
try {
    use(temp);
} finally {
    Files.deleteIfExists(temp);
}
```

Đây là mảnh mã; `use` là hàm của ứng dụng. Nếu `createTempFile` thất bại, chưa có file mới để dọn. Nếu thành công, `finally` sẽ chạy cho đoạn `use` theo luồng Java thông thường. Nhưng nếu `use` tạo thêm file con ở vị trí khác ngoài `temp`, việc chỉ xóa `temp` không dọn được các tài nguyên đó. Do vậy mô hình root workspace riêng là giải pháp dễ mở rộng khi một job tạo nhiều file.

## 14. Khả năng di động giữa filesystem providers

`Files.createTempFile(Path dir, ...)` tạo trong **filesystem provider của `dir`**. Không phải mọi provider đều hỗ trợ đầy đủ attribute, quyền, cách dọn hay khả năng move giống local disk.

Một số điểm cần cân nhắc:

- Filesystem mặc định trên Windows và Unix có quy tắc tên/permission khác nhau.
- ZIP filesystem provider có thể có hành vi write/delete khác local disk, và đóng `FileSystem` là bước riêng.
- Hệ thống tệp network có thể phát sinh độ trễ, mất kết nối hoặc lỗi quyền không giống thư mục tạm cục bộ.
- Symlink/junction và case sensitivity có thể khác theo provider.
- `Path.toFile()` không bắt buộc hoạt động cho Path thuộc provider phi mặc định.
- `File.createTempFile(...)` thuộc API legacy, thường phục vụ filesystem mặc định; với Path/provider tùy biến, ưu tiên API `Files` và truyền `Path dir`.

Đừng dùng các giả định kiểu “có file tạm là chắc chắn nó nằm trong ổ C:” hoặc “xóa file khi stream mở giống nhau trên mọi hệ điều hành”. Nếu ứng dụng phụ thuộc một đặc tính provider, kiểm thử chính xác trên runtime/filesystem mục tiêu.

## 15. So sánh với java.io.File.createTempFile

API truyền thống:

```java
File legacy = File.createTempFile("demo-", ".tmp");
```

Mảnh mã cần `java.io.File` và xử lý `IOException`. Khác với `new File("demo.tmp")`, **`File.createTempFile` thực sự tạo file tạm rỗng** rồi trả đối tượng `File` trỏ tới nó.

Bảng tóm tắt:

| API | Tạo tài nguyên thật? | Kiểu trả về | Điểm nổi bật |
| --- | --- | --- | --- |
| `new File("x.tmp")` | Không | `File` | Chỉ biểu diễn pathname |
| `File.createTempFile(prefix, suffix)` | Có: file | `File` | Legacy; dùng default filesystem |
| `File.createTempFile(prefix, suffix, directory)` | Có: file | `File` | Legacy; đặt file trong directory |
| `Files.createTempFile(prefix, suffix)` | Có: file | `Path` | NIO; hỗ trợ file attributes |
| `Files.createTempFile(dir, prefix, suffix)` | Có: file | `Path` | NIO; tạo trong thư mục/provider được chọn |
| `Files.createTempDirectory(prefix)` | Có: thư mục | `Path` | NIO; tạo namespace riêng |
| `Files.createTempDirectory(dir, prefix)` | Có: thư mục | `Path` | NIO; tạo directory con trong `dir` |

Một khác biệt đáng lưu ý từ tài liệu JDK: khi **không truyền thuộc tính** và trên một số hệ thống, `Files.createTempFile` có thể tạo file với quyền hạn chế hơn so với `File.createTempFile`. Dù vậy, chính sách bảo mật vẫn phải dựa vào provider/OS thực, không lấy câu này làm cam kết cứng cho mọi môi trường.

## 16. Câu hỏi thường gặp

### 16.1. `createTempFile` có tạo tên duy nhất không?

Nó tạo **mục mới** với tên do provider sinh ra, tránh đụng tên đã được dùng trong quá trình tạo. Không nên hiểu là cam kết một tên chưa từng được dùng ở mọi thời điểm hoặc là mã định danh không thể đoán. Khi file bị xóa, một tên có thể được dùng lại theo cơ chế provider.

### 16.2. Tôi chỉ muốn một đường dẫn tạm, chưa tạo file, dùng `createTempFile` được không?

Không đúng mục đích: `createTempFile` **đã tạo file**. Nếu thư viện cần Path tồn tại thì đó là ưu điểm. Nếu bạn cần file có tên cố định hoặc tạo lúc khác, hãy thiết kế cách đặt tên và thao tác `CREATE_NEW` phù hợp; đừng tạo file rồi xóa ngay chỉ để lấy tên và hy vọng tên đó an toàn về sau.

### 16.3. File tạm có tự biến mất khi close stream không?

Không. `close()` giải phóng handle và xả dữ liệu của stream theo hợp đồng; xóa file trên filesystem là thao tác riêng. Một số API đặc biệt như mở bằng `StandardOpenOption.DELETE_ON_CLOSE` có thể yêu cầu xóa khi đóng trên provider hỗ trợ, nhưng có giới hạn triển khai và không phải lựa chọn mặc định.

### 16.4. Nếu ứng dụng bị kill thì `finally` có chạy không?

Không thể bảo đảm. `finally` hoạt động trong cơ chế kiểm soát luồng Java bình thường; dừng tiến trình đột ngột, mất điện hoặc sự cố môi trường có thể không cho cleanup chạy. Nếu hậu quả file rác là quan trọng, cần có chiến lược xử lý sau sự cố phù hợp.

### 16.5. Có nên dọn toàn bộ `java.io.tmpdir` lúc startup?

Không. Đó có thể là thư mục chung của nhiều chương trình. Chỉ xét những workspace mang danh tính và ownership do ứng dụng của bạn quản lý, có chính sách tuổi/thời gian hoạt động rõ ràng.

### 16.6. Dọn bằng cách đi theo symbolic link có an toàn không?

Mặc định `walkFileTree` không theo symlink, hợp lý cho cleanup. Đừng bật `FOLLOW_LINKS` trừ khi hiểu chính xác đích và bảo đảm không lan ra ngoài phạm vi sở hữu. Chống race và giới hạn quyền sửa root vẫn cần thiết.

### 16.7. Dọn trong `finally` có thể che lỗi chính không?

Có. Nếu cả xử lý và cleanup ném exception, lỗi cleanup có thể khiến lỗi gốc bị thay thế. Dùng mô hình `AutoCloseable` + try-with-resources hoặc thu gom suppressed exceptions có kiểm soát để bảo toàn thông tin chẩn đoán.

### 16.8. Nên dùng file tạm trong thư mục hệ thống hay trong thư mục đích?

Tùy tác vụ. Với xử lý trung gian thông thường, dùng default temp location riêng cho job. Với chiến lược ghi file rồi move tới đích và muốn có khả năng move cùng filesystem, tạo temp trong **thư mục đích hoặc filesystem đích** có thể phù hợp. Trong cả hai trường hợp, phải kiểm soát quyền, không dùng directory của người khác làm phạm vi xóa đệ quy.

## 17. Lỗi thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Cho rằng “temp” sẽ tự xóa lúc kết thúc chương trình | File rác tồn tại lâu, tốn dung lượng | Cleanup tường minh; có chính sách xử lý rác sau sự cố |
| Dùng `Path.of(...)` rồi nghĩ đã tạo file | Tệp chưa có khi thư viện mở | Dùng `Files.createTempFile` nếu cần file mới có thật |
| Dùng `Files.createTempDirectory` rồi gọi `Files.delete` ngay khi còn con | `DirectoryNotEmptyException` | Dọn con trước, cha sau |
| Xóa cả thư mục tạm hệ thống | Phá hủy dữ liệu của tác vụ khác | Chỉ dọn root riêng do job sở hữu |
| Quên đóng stream trước khi xóa | Khóa file/handle tồn tại | try-with-resources rồi cleanup |
| Dùng `deleteOnExit` cho mọi file ở server sống lâu | Tích lũy đăng ký, không dọn kịp | Cleanup theo scope của từng request/job |
| Tin rằng `finally` bảo đảm xóa thành công | Ẩn lỗi I/O hoặc để lại rác | Kiểm tra/log lỗi dọn, khôi phục theo chính sách |
| Quét theo prefix `temp-` để xóa cả thư mục chung | Xóa nhầm file không thuộc ứng dụng | Workspace riêng và quyền sở hữu rõ |
| Theo symlink khi xóa đệ quy | Có thể vượt ra ngoài scope | Không bật `FOLLOW_LINKS`, hạn chế quyền thay đổi root |
| Dùng tên tạm làm biện pháp bảo mật | Nguy cơ bị đọc/ghi trái phép | Dùng quyền/ACL/owner và thư mục riêng |
| Không kiểm soát kích thước/số lượng file | Đầy disk/inode | Giới hạn byte, mục và thời gian |
| Tin `File.delete()` trả `false` nghĩa chắc chắn file chưa có | Mất thông tin nguyên nhân lỗi | Dùng `Files.delete(...)` khi cần ngoại lệ chi tiết |
| Ghi output cuối vào temp rồi dọn cùng output | Mất dữ liệu đã publish | Tách “intermediate” và “output cần giữ” |
| Dùng temp mặc định để suy ra mọi file đều cùng filesystem với đích | Move có thể không atomic/không hỗ trợ | Chọn dir trên filesystem đích khi cần |
| Tạo temp tên đẹp và mở lại không bảo vệ race | File có thể bị thay bởi tác nhân khác | Quyền thư mục, chính sách handle, thao tác mở an toàn |
| Giả định POSIX permission có trên Windows | `UnsupportedOperationException` | Kiểm tra provider/OS và dùng ACL phù hợp |

## 18. Câu hỏi tự kiểm tra

1. **`Files.createTempFile("a-", ".tmp")` có thực sự tạo file không?** Có; trả về `Path` của file mới đã tạo.
2. **`Files.createTempDirectory("job-")` khác gì `Path.of("job")`?** Lệnh đầu tạo directory vật lý; lệnh sau chỉ tạo đối tượng Path.
3. **Có thể đoán chính xác tên file tạm không?** Không; phần tên được sinh ra tùy provider.
4. **File tạm được tạo ở đâu nếu không truyền `dir`?** Ở vị trí tạm mặc định của provider; không mặc nhiên là thư mục dự án.
5. **`createTempFile(dir, ...)` có tự tạo `dir` nếu thiếu không?** Không; phải chuẩn bị thư mục cha.
6. **Đóng `OutputStream` có tự xóa file tạm không?** Không theo hành vi mặc định.
7. **`Files.deleteIfExists(directory)` có xóa đệ quy không?** Không; directory còn mục con có thể ném `DirectoryNotEmptyException`.
8. **Vì sao dùng `walkFileTree` để dọn root?** Có thể xử lý file trước thư mục, kiểm soát lỗi và mặc định không theo symlink.
9. **Root cleanup nên là `java.io.tmpdir` hay folder riêng do job tạo?** Folder riêng do job tạo.
10. **`deleteOnExit()` có bảo đảm xóa trong trường hợp JVM bị kill?** Không.
11. **Nếu cleanup cũng lỗi khi xử lý chính lỗi, điều gì cần lưu ý?** Giữ thông tin exception gốc, có thể dùng suppression/try-with-resources.
12. **Khi file có dữ liệu nhạy cảm cần quan tâm gì?** Quyền/ACL, vị trí root, người sở hữu, thời gian lưu, nhật ký và dọn dẹp.
13. **Có nên tạo file tạm trong thư mục đích trước khi publish?** Có thể, nếu cần cùng filesystem; nhưng phải chọn move semantics đúng, không giả định atomic mặc định.
14. **Vì sao không bật `FOLLOW_LINKS` khi cleanup?** Có thể khiến traversal chạm tài nguyên bên ngoài root.
15. **Vì sao hệ thống server có thể cần janitor bổ sung?** Vì crash/kill/dọn lỗi có thể để lại workspace cũ dù có `finally`.
16. **File tạm chứa dữ liệu binary lớn cần giới hạn gì?** Tổng dung lượng, số file, thời gian, quyền truy cập và tác vụ có thể đang sử dụng.

## Tham khảo API Java 17

- [`Files.createTempFile` / `Files.createTempDirectory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [`Files.walkFileTree`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.nio.file.FileVisitor)).
- [`FileVisitor` / `SimpleFileVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html).
- [`Files.delete` / `Files.deleteIfExists`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [`java.io.File.createTempFile` / `deleteOnExit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/File.html).
- [`PosixFilePermissions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html).
- [`StandardOpenOption.DELETE_ON_CLOSE`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html).
- [`StandardCopyOption.ATOMIC_MOVE`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html).

**Ghi nhớ:** `createTempFile` và `createTempDirectory` tạo tài nguyên **thật** với tên mới, nhưng không tự xác lập chính sách xóa. Cách sử dụng an toàn là cấp một **workspace tạm có ownership rõ**, mở/đóng tài nguyên bằng try-with-resources, dọn file/thư mục con trước root bằng cơ chế phù hợp, giữ output chính thức ngoài phạm vi xóa và chấp nhận rằng cleanup có thể thất bại hoặc không chạy khi tiến trình dừng bất thường.
