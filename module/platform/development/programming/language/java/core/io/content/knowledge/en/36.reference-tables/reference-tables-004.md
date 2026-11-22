# Bảng OpenOption, CopyOption, LinkOption và FileVisitOption trong Java NIO.2

## 1. Mục tiêu và bản đồ các nhóm option

Trong `java.nio.file` (NIO.2), cùng một đối tượng `Path` có thể được **mở để đọc/ghi**, **sao chép/di chuyển**, **kiểm tra symbolic link** hoặc **duyệt cây thư mục**. Mỗi thao tác nhận một họ option khác nhau. Đọc đúng chữ ký API quan trọng hơn việc nhớ tên một enum.

| Nhóm | Kiểu Java | Tác dụng chính | API điển hình |
| --- | --- | --- | --- |
| `OpenOption` | **Interface** | Quy định cách mở/tạo tệp hoặc channel | `Files.newOutputStream`, `Files.newByteChannel`, `FileChannel.open`, `Files.writeString` |
| `StandardOpenOption` | **Enum implements OpenOption** | `READ`, `WRITE`, `APPEND`, `CREATE`, ... | Các API nhận `OpenOption` tương ứng |
| `CopyOption` | **Interface** | Quy định cách copy/move | `Files.copy(Path, Path, CopyOption...)`, `Files.move` |
| `StandardCopyOption` | **Enum implements CopyOption** | `REPLACE_EXISTING`, `COPY_ATTRIBUTES`, `ATOMIC_MOVE` | `Files.copy` / `Files.move` tùy option |
| `LinkOption` | **Enum implements OpenOption, CopyOption** | `NOFOLLOW_LINKS`: không dereference symbolic link ở API hỗ trợ | `Files.exists`, `Files.readAttributes`, `Files.copy`, `Files.newByteChannel` |
| `FileVisitOption` | **Enum riêng** | `FOLLOW_LINKS`: đi qua symlink khi duyệt cây | `Files.walkFileTree`, `Files.walk` |

**Chú ý:** `OpenOption` và `CopyOption` *không phải enum*; không tồn tại `OpenOption.READ` hay `CopyOption.REPLACE_EXISTING`. Hằng số nằm trong `StandardOpenOption` và `StandardCopyOption`. `FileVisitOption` cũng không phải tham số cho `Files.copy`, còn `LinkOption.NOFOLLOW_LINKS` không phải tùy chọn cho `Files.walkFileTree`.

Các import thường gặp:

```java
import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.file.OpenOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.CopyOption;
import java.nio.file.StandardCopyOption;
import java.nio.file.LinkOption;
import java.nio.file.FileVisitOption;
```

## 2. Bảng tra cứu OpenOption / StandardOpenOption

`OpenOption` là kiểu tham số; `StandardOpenOption` cung cấp 10 giá trị chuẩn. Các provider có thể hỗ trợ option bổ sung, và từng phương thức có thể cho phép tập con khác nhau.

| `StandardOpenOption` | Ý nghĩa | Khi nào dùng / lưu ý |
| --- | --- | --- |
| `READ` | Mở tệp để đọc | Mặc định của `Files.newInputStream(path)` và `Files.newByteChannel(path)` nếu không chỉ định quyền ghi; tệp cần tồn tại. |
| `WRITE` | Mở tệp để ghi | Không tự hàm ý ghi nối cuối hoặc cắt nội dung; thường kết hợp `CREATE`, `TRUNCATE_EXISTING`. |
| `APPEND` | Mỗi lần ghi vào cuối tệp | Hàm ý quyền ghi ở các channel chuẩn; với `newByteChannel` không kết hợp `READ` hoặc `TRUNCATE_EXISTING`. Ghi nối cuối đồng thời không được bảo đảm atomic trên mọi hệ tệp. |
| `TRUNCATE_EXISTING` | Cắt tệp hiện có về độ dài 0 khi mở để ghi | Chỉ có tác dụng với quyền ghi; **nguy cơ mất dữ liệu** nếu dùng nhầm. |
| `CREATE` | Tạo tệp nếu chưa tồn tại, nếu đã có thì mở tệp đó | Hữu ích với ghi có thể tạo mới; bị bỏ qua khi đồng thời dùng `CREATE_NEW`, hoặc chỉ mở đọc. |
| `CREATE_NEW` | Chỉ tạo tệp mới, thất bại nếu đường dẫn đã có | Kiểm tra tồn tại và tạo tệp được thực hiện atomic đối với thao tác hệ tệp; hữu ích để tránh ghi đè ngoài ý muốn. |
| `DELETE_ON_CLOSE` | Nỗ lực xóa tệp lúc đóng handle | Là *best effort*, không phải lời hứa xóa an toàn; tránh dùng cho dữ liệu phải lưu. Có thể không cho mở symlink tùy provider. |
| `SPARSE` | Gợi ý tạo sparse file khi tạo tệp mới | Chỉ là hint; provider/hệ tệp không hỗ trợ có thể bỏ qua, không phải cách bảo đảm tiết kiệm dung lượng. |
| `SYNC` | Yêu cầu cập nhật nội dung **và metadata** đồng bộ xuống thiết bị lưu trữ | Có thể tốn chi phí I/O; khác với bảo đảm giao dịch hoặc ghi nguyên tử. |
| `DSYNC` | Yêu cầu đồng bộ các cập nhật **nội dung** xuống thiết bị lưu trữ | Phạm vi bảo đảm hẹp hơn `SYNC`; hiệu năng và hỗ trợ phụ thuộc hệ thống. |

### 2.1. Mặc định tùy theo phương thức

| Gọi API | Mặc định khi không truyền option | Hệ quả |
| --- | --- | --- |
| `Files.newInputStream(path)` | `READ` | Mở luồng đọc; lỗi nếu không đọc được. |
| `Files.newOutputStream(path)` | `CREATE + TRUNCATE_EXISTING + WRITE` | Ghi đè nội dung tệp cũ hoặc tạo tệp mới. |
| `Files.newByteChannel(path)` | `READ` | Channel chỉ đọc nếu không truyền option. |
| `Files.writeString(path, text)` | `CREATE + TRUNCATE_EXISTING + WRITE` | Lời gọi lần sau mặc định thay nội dung trước. |
| `Files.write(path, bytes)` | `CREATE + TRUNCATE_EXISTING + WRITE` | Hành vi tương tự khi ghi mảng byte. |

Hãy nhìn **chữ ký của API** khi áp dụng: `newByteChannel(Path, OpenOption...)` và `FileChannel.open` hỗ trợ tổ hợp quyền đọc/ghi, còn `newOutputStream` không nhận `READ`; `Files.newInputStream` không phải công cụ để tạo/ghi file. Tập option bổ sung không đồng nhất cho mọi overload.

### 2.2. Các tổ hợp điển hình

```java
Path path = Path.of("data.txt");

// Tạo mới duy nhất, lỗi nếu data.txt đã tồn tại:
Files.writeString(path, "first\n",
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);

// Ghi nối cuối tệp hiện có, không tự tạo mới:
Files.writeString(path, "next\n", StandardOpenOption.APPEND);

// Mở nối cuối, tạo mới nếu chưa có:
try (var out = Files.newOutputStream(path,
        StandardOpenOption.CREATE, StandardOpenOption.APPEND)) {
    out.write("tail\n".getBytes(java.nio.charset.StandardCharsets.UTF_8));
}

// Chủ động thay toàn bộ nội dung:
Files.writeString(path, "replaced\n",
        StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING);
```

Đoạn trên là *snippet* minh họa, với `path` nằm trong thư mục được phép ghi. Lệnh cuối đòi tệp đã tồn tại; để đồng thời cho phép tạo mới thì thêm `CREATE`. Dùng `try-with-resources` khi trực tiếp mở stream/channel để đóng tài nguyên kể cả khi có exception.

**So sánh `CREATE` và `CREATE_NEW`:** `CREATE` không ngăn việc mở tệp cũ; `CREATE_NEW` báo thất bại ngay khi đường dẫn đã tồn tại (kể cả symlink). `CREATE_NEW` hữu ích hơn chuỗi `if (!Files.exists(path)) Files.writeString(...)` vì phép kiểm tra rồi hành động tách rời có race condition (TOCTOU).

**So sánh `APPEND` và `TRUNCATE_EXISTING`:** `APPEND` bảo toàn byte hiện có và thêm byte vào cuối; `TRUNCATE_EXISTING` xóa byte hiện có ngay khi mở để ghi. Đừng kết hợp hai option này. `APPEND` không đồng nghĩa khóa tệp hoặc ghi một bản ghi log nguyên tử giữa nhiều process.

## 3. Bảng tra cứu CopyOption / StandardCopyOption

`CopyOption` là interface. `StandardCopyOption` chỉ có **ba** hằng số chuẩn:

| `StandardCopyOption` | Đối với `Files.copy` | Đối với `Files.move` |
| --- | --- | --- |
| `REPLACE_EXISTING` | Cho phép thay target đã có; target là thư mục không rỗng có thể không thay được. | Cho phép thay target đã có với giới hạn hệ tệp/tệp đích. |
| `COPY_ATTRIBUTES` | Thử sao chép thuộc tính của source (ví dụ last-modified time); nhóm thuộc tính và độ chính xác phụ thuộc hệ tệp/provider. | **Không phải** option chuẩn được `Files.move` liệt kê để cấu hình move; move có quy tắc giữ thuộc tính riêng. |
| `ATOMIC_MOVE` | **Không dùng cho `Files.copy`**; đây là option của move. | Yêu cầu move như một thao tác hệ tệp nguyên tử; nếu không hỗ trợ sẽ ném `AtomicMoveNotSupportedException`. Các option khác bị bỏ qua khi dùng `ATOMIC_MOVE`. |

Ví dụ:

```java
Path source = Path.of("source.txt");
Path target = Path.of("backup.txt");

// Sao chép, cho phép thay thế và cố gắng giữ metadata:
Files.copy(source, target,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES);

// Đổi tên hoặc chuyển sang vị trí khác:
Files.move(target, Path.of("archive.txt"),
        StandardCopyOption.REPLACE_EXISTING);

// Chỉ yêu cầu chuyển nguyên tử khi hệ tệp cho phép:
Files.move(Path.of("draft.txt"), Path.of("published.txt"),
        StandardCopyOption.ATOMIC_MOVE);
```

Đây là *snippet*, yêu cầu các đường dẫn nguồn tồn tại. Khi dùng `ATOMIC_MOVE`, đừng giả định rằng ghép thêm `REPLACE_EXISTING` sẽ bắt buộc thay thế target: tài liệu JDK quy định các option khác bị bỏ qua, và nếu target đã tồn tại thì provider có thể thay hoặc báo lỗi. Với ứng dụng cần chính sách ghi đè rõ ràng, hãy thiết kế xử lý ngoại lệ và xác minh hành vi trên hệ tệp triển khai.

### 3.1. Ba ngộ nhận thường gặp với copy/move

1. **Copy tệp khác với copy thư mục đệ quy.** `Files.copy(sourceDir, targetDir)` tạo thư mục đích rỗng, không tự sao chép toàn bộ con. Muốn copy cây thì kết hợp `walkFileTree` với xử lý tạo thư mục và copy từng file.
2. **`REPLACE_EXISTING` không biến copy thành một giao dịch atomic.** Nếu I/O thất bại giữa chừng, target có thể dở dang. Bảo đảm cần đến quy trình ghi file tạm + xác nhận + move thích hợp, và chỉ dựa vào `ATOMIC_MOVE` khi provider thực sự hỗ trợ.
3. **`Files.move` không phải lúc nào cũng là rename đơn giản.** Trong cùng file store có thể rename trực tiếp; qua file store khác có thể cần copy-xóa và có thể thất bại hoặc không nguyên tử. Không suy ra thao tác là atomic chỉ vì một lệnh Java trả về.

### 3.2. Symbolic link khi copy và move

Theo mặc định, `Files.copy(Path, Path, ...)` **đi theo symlink ở source** và copy nội dung *đối tượng mà link trỏ tới*. Thêm `LinkOption.NOFOLLOW_LINKS` để copy **chính đối tượng symbolic link** (nếu hệ thống hỗ trợ). Nếu target đã là symlink và dùng `REPLACE_EXISTING`, chính link ở target bị thay, không tự động đi theo link target.

`Files.move` di chuyển **chính symbolic link** nếu source là link. Không mặc nhiên giải tham chiếu link và di chuyển file mà link trỏ tới. Vì vậy dùng `NOFOLLOW_LINKS` cho thao tác copy có ý nghĩa khác hoàn toàn `FOLLOW_LINKS` khi duyệt cây.

## 4. LinkOption: NOFOLLOW_LINKS và ý nghĩa từng API

`LinkOption` chỉ có **`NOFOLLOW_LINKS`**. Nó implements *cả* `OpenOption` và `CopyOption`, nhưng khả năng chấp nhận option vẫn do từng API quyết định.

| Tác vụ | Mặc định | Khi truyền `LinkOption.NOFOLLOW_LINKS` |
| --- | --- | --- |
| `Files.exists(link)` / `notExists(link)` | Theo link đến target | Kiểm tra sự tồn tại của **link**; dangling symlink vẫn có thể là một link đang tồn tại. |
| `Files.isDirectory(link)` / `isRegularFile(link)` | Xét loại của target | Xét chính link; symlink không được coi là thư mục hoặc regular file do target thuộc loại đó. |
| `Files.readAttributes(link, BasicFileAttributes.class)` | Đọc thuộc tính target | Đọc thuộc tính chính symlink. |
| `Files.getLastModifiedTime(link)` | Thời điểm của target | Thời điểm của chính symlink khi provider hỗ trợ. |
| `Files.copy(link, target, NOFOLLOW_LINKS)` | Mặc định copy target mà link trỏ tới | Copy bản thân symlink, nếu hỗ trợ. |
| `Files.newByteChannel(link, ..., NOFOLLOW_LINKS)` | Có thể theo symlink khi mở | Chỉ mở khi đối tượng được mở đáp ứng quy tắc không theo link; có thể thất bại khi path là symlink. |

Phân biệt **symlink** với **hard link**: symlink là một entry trỏ tới path khác và có thể bị đứt; hard link là một tên khác của cùng file trong cùng file system. `NOFOLLOW_LINKS` nhắm vào symbolic link, không biến hard link thành một đối tượng đặc biệt để bỏ qua.

Ví dụ kiểm tra bản thân link:

```java
Path candidate = Path.of("alias");
boolean entryExists = Files.exists(candidate, LinkOption.NOFOLLOW_LINKS);
boolean isLink = Files.isSymbolicLink(candidate);
System.out.println("entry exists: " + entryExists);
System.out.println("symbolic link: " + isLink);
```

Kết quả hai dòng trên **phụ thuộc hệ tệp thực tế**, nên không gán stdout cố định. `Files.exists` và `Files.notExists` đều có thể trả `false` khi không xác định được trạng thái; chúng không phải hai phép phủ định logic hoàn hảo. Đừng dùng check-then-open để bảo đảm tuyệt đối chống thay thế link trong thao tác nhạy cảm; hãy cân nhắc API thao tác tương đối với directory handle (`SecureDirectoryStream` khi được hỗ trợ), quyền truy cập và xử lý ngoại lệ.

## 5. FileVisitOption: FOLLOW_LINKS khi duyệt cây

`FileVisitOption` chỉ có **`FOLLOW_LINKS`** trong Java 17/21.

| Gọi API | Không truyền `FOLLOW_LINKS` | Có `FOLLOW_LINKS` |
| --- | --- | --- |
| `Files.walkFileTree(start, visitor)` | Duyệt sâu nhưng **không đi vào thư mục mà symlink trỏ tới**. | Overload 4 tham số mới nhận tập option; có thể đi qua thư mục đích của symlink. |
| `Files.walkFileTree(start, options, maxDepth, visitor)` | `EnumSet.noneOf(FileVisitOption.class)`: không theo symlink. | `EnumSet.of(FileVisitOption.FOLLOW_LINKS)`: theo symlink đến mức sâu cho phép. |
| `Files.walk(start, maxDepth, options...)` | Không theo symlink, trả `Stream<Path>`. | Theo symlink, vẫn cần đóng stream sau khi dùng. |

Ví dụ cú pháp chuẩn:

```java
Files.walkFileTree(
    root,
    java.util.EnumSet.of(FileVisitOption.FOLLOW_LINKS),
    3,
    visitor
);
```

`root` và `visitor` là các biến đã được khai báo ở ngữ cảnh gọi; snippet này không phải chương trình độc lập. Tham số `3` là độ sâu tối đa: root ở độ sâu `0`, con trực tiếp ở `1`. `Integer.MAX_VALUE` thực tế có nghĩa không chủ động giới hạn độ sâu.

### 5.1. Callback của FileVisitor và kết quả điều khiển

Đây là kiến thức đi cùng `FileVisitOption`: option chọn cách duyệt, còn `FileVisitor` quyết định cách phản ứng với từng entry.

| Callback | Khi nào được gọi | Điểm cần nhớ |
| --- | --- | --- |
| `preVisitDirectory(dir, attrs)` | Trước khi duyệt con của một thư mục | Trả `SKIP_SUBTREE` để không xuống subtree. |
| `visitFile(file, attrs)` | Khi gặp file thường hoặc entry được xử lý như file | Hữu ích cho tìm kiếm hoặc copy từng file. |
| `visitFileFailed(file, exc)` | Khi không đọc được thuộc tính/mở thư mục hoặc phát hiện vòng lặp symlink | Có thể nhận `FileSystemLoopException` khi bật `FOLLOW_LINKS`. |
| `postVisitDirectory(dir, exc)` | Sau khi duyệt xong directory hoặc lỗi khi duyệt các entry | Phù hợp để xóa thư mục sau khi đã xử lý con; kiểm tra `exc`. |

| `FileVisitResult` | Ý nghĩa |
| --- | --- |
| `CONTINUE` | Tiếp tục duyệt. |
| `SKIP_SUBTREE` | Bỏ qua descendants của thư mục hiện tại (có ý nghĩa khi trả ở `preVisitDirectory`). |
| `SKIP_SIBLINGS` | Bỏ qua các entry anh em tiếp theo. |
| `TERMINATE` | Kết thúc duyệt ngay. |

Nếu return `null` từ visitor thì `walkFileTree` ném `NullPointerException`. Thứ tự các anh em trong directory **không được bảo đảm**; nếu cần thứ tự ổn định cho báo cáo, cần tự thiết kế cách sắp xếp.

### 5.2. Lý do FOLLOW_LINKS cần cẩn thận

Nếu trong cây có symlink trỏ ngược lên một thư mục tổ tiên, `FOLLOW_LINKS` có thể tạo vòng lặp. `walkFileTree` nhận diện chu trình và gọi `visitFileFailed` với `FileSystemLoopException`; đừng giả định nó sẽ đi vô hạn hoặc mọi symlink đều duyệt thành công. Với tác vụ xóa, sao lưu hoặc scan dữ liệu không đáng tin cậy, mặc định **không follow** thường giúp tránh đi ra ngoài cây mong muốn. Ngay cả với `maxDepth` hữu hạn, vẫn phải xử lý lỗi quyền truy cập và symlink thay đổi trong khi duyệt.

`Files.walk` trả về stream có thể giữ directory handles; luôn dùng `try-with-resources`:

```java
try (var paths = Files.walk(root, 2)) {
    long count = paths.filter(Files::isRegularFile).count();
    System.out.println("regular files: " + count);
}
```

Đây là snippet phụ thuộc thư mục `root`. Với `FOLLOW_LINKS`, lỗi I/O trong lúc stream đang tiêu thụ có thể bọc thành `UncheckedIOException`, khác với callback báo lỗi của `walkFileTree`. Lưu ý `Files.isRegularFile` mặc định theo symbolic link ở entry đang xét; nếu muốn chính symlink không được tính là file thường, truyền `LinkOption.NOFOLLOW_LINKS`.

## 6. Ví dụ Java 17+ chạy độc lập: mở, copy, move

Tạo tệp `OptionDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static java.nio.file.StandardOpenOption.*;
import static java.nio.file.StandardCopyOption.*;

public class OptionDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("nio-option-demo-");
        Path source = dir.resolve("source.txt");
        Path copy = dir.resolve("copy.txt");
        Path moved = dir.resolve("moved.txt");

        try {
            Files.writeString(source, "alpha\n", StandardCharsets.UTF_8,
                    CREATE_NEW, WRITE);
            Files.writeString(source, "beta\n", StandardCharsets.UTF_8, APPEND);

            Files.copy(source, copy, COPY_ATTRIBUTES);
            Files.writeString(copy, "gamma\n", StandardCharsets.UTF_8,
                    WRITE, TRUNCATE_EXISTING);
            Files.move(copy, moved);

            System.out.println(
                    Files.readString(source, StandardCharsets.UTF_8)
                            .replace("\n", "|"));
            System.out.println(
                    Files.readString(moved, StandardCharsets.UTF_8).trim());
            System.out.println(Files.exists(copy));
        } finally {
            Files.deleteIfExists(moved);
            Files.deleteIfExists(copy);
            Files.deleteIfExists(source);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa `OptionDemo.java`:

```bash
javac -encoding UTF-8 OptionDemo.java
java OptionDemo
```

Kết quả chính xác:

```text
alpha|beta|
gamma
false
```

Giải thích: `CREATE_NEW` tạo source và bảo vệ khỏi mở nhầm tệp cũ; `APPEND` thêm `beta` sau `alpha`; `COPY_ATTRIBUTES` yêu cầu giữ thuộc tính khi copy; `TRUNCATE_EXISTING` thay nội dung bản copy bằng `gamma`; `move` đổi tên tệp copy thành moved, khiến đường dẫn `copy` không còn tồn tại. Ví dụ tự dọn các tệp/tên thư mục tạm khi kết thúc bình thường; nếu có can thiệp từ tiến trình khác hoặc lỗi dọn dẹp, `IOException` vẫn có thể xuất hiện.

## 7. Ví dụ Java 17+ chạy độc lập: walkFileTree không theo symlink

Tạo `WalkDemo.java`:

```java
import java.io.IOException;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;
import java.util.concurrent.atomic.AtomicInteger;

public class WalkDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("nio-walk-demo-");
        Path sub = Files.createDirectory(root.resolve("sub"));
        Path one = root.resolve("a.txt");
        Path two = sub.resolve("b.txt");

        try {
            Files.writeString(one, "a");
            Files.writeString(two, "b");

            AtomicInteger directories = new AtomicInteger();
            AtomicInteger files = new AtomicInteger();

            Files.walkFileTree(root, EnumSet.noneOf(FileVisitOption.class),
                    Integer.MAX_VALUE, new SimpleFileVisitor<Path>() {
                        @Override
                        public FileVisitResult preVisitDirectory(
                                Path dir, BasicFileAttributes attrs) {
                            directories.incrementAndGet();
                            return FileVisitResult.CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFile(
                                Path file, BasicFileAttributes attrs) {
                            files.incrementAndGet();
                            return FileVisitResult.CONTINUE;
                        }
                    });

            System.out.printf("dirs=%d, files=%d%n",
                    directories.get(), files.get());
        } finally {
            Files.deleteIfExists(two);
            Files.deleteIfExists(one);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac -encoding UTF-8 WalkDemo.java
java WalkDemo
```

Kết quả chính xác trên cấu trúc mà chương trình tự tạo:

```text
dirs=2, files=2
```

Tệp gốc và một thư mục con tạo ra `2` lượt `preVisitDirectory`; hai tệp tạo ra `2` lượt `visitFile`. Chuyển `EnumSet.noneOf(FileVisitOption.class)` thành `EnumSet.of(FileVisitOption.FOLLOW_LINKS)` sẽ cho phép theo symlink, nhưng ví dụ không tạo symlink nên số đếm không thay đổi.

## 8. Chọn option theo tình huống

| Yêu cầu thực tế | Lựa chọn gợi ý | Vì sao |
| --- | --- | --- |
| Đọc tệp hiện có | `Files.readString(path)` hoặc mở `READ` | Không tạo/ghi file. |
| Ghi đè bằng nội dung hoàn toàn mới | `Files.writeString(path, text)` hoặc `WRITE + CREATE + TRUNCATE_EXISTING` | Cắt nội dung cũ trước khi ghi. |
| Ghi nối log, tự tạo nếu cần | `CREATE + APPEND` | Không cắt dữ liệu đã có, nhưng không bảo đảm bản ghi atomic liên tiến trình. |
| Chỉ tạo khi chưa có | `CREATE_NEW + WRITE` | Tránh cuộc đua “check rồi create”. |
| Sao lưu một tệp, ghi đè bản sao | `Files.copy(a, b, REPLACE_EXISTING, COPY_ATTRIBUTES)` | Sao chép nội dung cùng các thuộc tính được hỗ trợ. |
| Copy chính symbolic link | `Files.copy(link, dst, LinkOption.NOFOLLOW_LINKS)` | Không dereference link ở source. |
| Kiểm tra một entry là symlink | `Files.isSymbolicLink(path)` | Xem loại entry của path, không phụ thuộc target tồn tại. |
| Xem thuộc tính **chính link** | `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)` | Tránh đọc nhầm metadata của target. |
| Rename/move yêu cầu atomic | `Files.move(src, dst, ATOMIC_MOVE)`, bắt `AtomicMoveNotSupportedException` | Không giả định provider hỗ trợ. |
| Duyệt directory mặc định | `Files.walkFileTree(root, visitor)` | Không follow symlink. |
| Duyệt cả thư mục qua symlink | `Files.walkFileTree(root, EnumSet.of(FOLLOW_LINKS), maxDepth, visitor)` | Có thể đi ngoài cây logic và phải xử lý vòng lặp. |

### Các cặp dễ nhầm

- `NOFOLLOW_LINKS` và `FOLLOW_LINKS` **không phải hai hằng số đối xứng trong một enum**: cái đầu thuộc `LinkOption` cho API làm việc với link/thuộc tính/copy; cái sau thuộc `FileVisitOption` cho duyệt cây. Không truyền `FOLLOW_LINKS` cho `Files.copy`.
- `REPLACE_EXISTING` là thao tác **với đường dẫn đích khi copy/move**; `TRUNCATE_EXISTING` là thao tác **với nội dung của file đang mở để ghi**. Không thể hoán đổi.
- `CREATE`/**`CREATE_NEW`** dùng khi **mở để ghi/tạo file**; `COPY_ATTRIBUTES` dùng khi **copy file**; `ATOMIC_MOVE` chỉ dùng khi **move**.
- `FileVisitOption` chỉ thay cách duyệt cây. Nó không tự quyết định sẽ copy/xóa file nào, không thay cho `FileVisitor`, và không thay đổi cách hoạt động của `Files.exists`.

## 9. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `FileAlreadyExistsException` | `CREATE_NEW` tạo file đã có hoặc `Files.copy` gặp target đã tồn tại | Đổi tên, kiểm tra yêu cầu nghiệp vụ, hoặc sử dụng `REPLACE_EXISTING` chỉ khi thực sự muốn ghi đè. |
| `NoSuchFileException` | Source không tồn tại, parent directory chưa có, hoặc dùng `APPEND` mà file chưa có | Chuẩn bị parent; với mục tiêu tạo nếu thiếu, cân nhắc `CREATE + APPEND`. |
| `IllegalArgumentException` khi mở channel | Option không hợp lệ, ví dụ `READ + APPEND` hoặc `APPEND + TRUNCATE_EXISTING` | Chọn tổ hợp hợp lệ theo API và hành vi mong muốn. |
| `UnsupportedOperationException` | Provider không hỗ trợ option cụ thể | Chọn cách hỗ trợ bởi provider, có nhánh xử lý phù hợp. |
| `AtomicMoveNotSupportedException` | `ATOMIC_MOVE` không được hệ tệp/provider hỗ trợ | Quyết định rõ có cho phép fallback không nguyên tử hay báo lỗi. |
| `FileSystemLoopException` khi walk | Bật `FOLLOW_LINKS` và gặp chu trình symlink | Xử lý trong `visitFileFailed`; cân nhắc không follow link hoặc giới hạn độ sâu. |
| Dữ liệu cũ biến mất | Mặc định `writeString`/`newOutputStream` cắt file cũ | Chỉ dùng `APPEND` khi muốn nối; dùng `TRUNCATE_EXISTING` một cách có chủ ý. |
| `Files.exists` là `false` dù nghi ngờ path tồn tại | Dangling symlink, quyền truy cập hoặc trạng thái không xác định | Dùng `NOFOLLOW_LINKS` nếu cần xét link, và vẫn xử lý lỗi tại thao tác thực tế. |

Khi thao tác I/O thật, ngoài option còn phải tính tới quyền hệ điều hành, file system provider, symbolic link có thể thay đổi đồng thời, độ bền ghi xuống thiết bị, đóng tài nguyên và cách khôi phục sau lỗi. Tránh dùng option như một thay thế cho transaction, locking hoặc kiểm tra bảo mật.

## 10. Tự kiểm tra

1. Vì sao `OpenOption.READ` không biên dịch? **Vì `OpenOption` là interface; dùng `StandardOpenOption.READ`.**
2. Muốn vừa tạo log khi chưa có, vừa nối khi đã có? **Dùng `CREATE + APPEND`.**
3. `Files.copy(dirA, dirB)` có sao chép mọi file con không? **Không; cần duyệt cây và copy từng entry.**
4. Muốn copy chính symbolic link? **Dùng `Files.copy(link, target, LinkOption.NOFOLLOW_LINKS)` nếu provider hỗ trợ.**
5. Muốn walk qua link đến thư mục? **Dùng `FileVisitOption.FOLLOW_LINKS` trong overload cho phép option.**
6. Có được chắc chắn một lệnh `Files.move(..., ATOMIC_MOVE, REPLACE_EXISTING)` sẽ luôn ghi đè đích? **Không; với `ATOMIC_MOVE`, option khác bị bỏ qua và chính sách target tồn tại phụ thuộc implementation.**
7. `SYNC` có đồng nghĩa `ATOMIC_MOVE`? **Không; `SYNC` liên quan đồng bộ cập nhật file xuống storage, `ATOMIC_MOVE` liên quan tính nguyên tử khi đổi vị trí file.**

## Tài liệu đối chiếu (JDK 21)

- [OpenOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/OpenOption.html)
- [StandardOpenOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html)
- [CopyOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/CopyOption.html)
- [StandardCopyOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html)
- [LinkOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html)
- [FileVisitOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitOption.html)
- [Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
