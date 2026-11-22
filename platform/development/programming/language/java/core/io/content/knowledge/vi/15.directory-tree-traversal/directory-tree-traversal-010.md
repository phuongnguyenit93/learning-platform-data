# Sao chép hoặc xóa cây thư mục theo đúng thứ tự xử lý trong Java

## 1. Mục tiêu bài học

Khi thao tác với **cây thư mục**, thứ tự xử lý các phần tử là một phần quan trọng của tính đúng đắn. Khác với một file riêng lẻ, cây gồm thư mục cha, thư mục con và file ở nhiều cấp:

- **Sao chép cây:** phải chuẩn bị thư mục **cha trước khi** tạo file hoặc thư mục con trong đích.
- **Xóa cây:** phải xóa **file và thư mục con trước khi** xóa thư mục cha.

Java NIO.2 cung cấp `Files.walkFileTree()` kết hợp `FileVisitor` / `SimpleFileVisitor` để giải quyết bài toán này theo kiểu duyệt chiều sâu (*depth-first traversal*). Bài học tập trung vào hai thao tác ấy, không đánh đồng với `Files.copy(sourceDirectory, targetDirectory)` hay `Files.delete(root)` chỉ áp dụng cho một đối tượng đường dẫn.

Bạn sẽ học được:

1. Ý nghĩa của **pre-order** và **post-order** khi duyệt cây.
2. Cách dùng `preVisitDirectory`, `visitFile`, `postVisitDirectory` và `visitFileFailed`.
3. Ví dụ Java 17+ sao chép toàn cây, sau đó xóa cây đúng thứ tự.
4. Cách xử lý nguồn/đích, symlink, thuộc tính, các lỗi I/O, giới hạn độ sâu và an toàn khi xóa.
5. Khi nào nên dùng `Files.walk()`, vì sao duyệt xong không có nghĩa thứ tự xóa an toàn.

## 2. Cây thư mục và ràng buộc thứ tự

Giả sử có dữ liệu:

```text
source/
├── config.txt
└── reports/
    ├── january.csv
    └── history/
        └── old.csv
```

Để **sao chép** sang `backup/`, ứng dụng phải có một cấu trúc tương đương:

```text
backup/
├── config.txt
└── reports/
    ├── january.csv
    └── history/
        └── old.csv
```

Nếu thử tạo `backup/reports/history/old.csv` khi `backup/reports/history` chưa tồn tại, thao tác copy thông thường sẽ thất bại do chưa có thư mục cha. Vì thế thứ tự chuẩn bị đích thường là:

```text
Tạo backup/
Tạo backup/reports/
Tạo backup/reports/history/
Sao chép các file vào những thư mục đã được tạo
```

Thứ tự tương đối **giữa các file cùng cấp** không quan trọng với việc copy độc lập: file `config.txt` có thể được sao chép trước hoặc sau các file trong `reports/`, miễn cha của từng file đã có.

Khi **xóa** `backup/` thì ngược lại:

```text
Xóa file backup/reports/history/old.csv
Xóa thư mục backup/reports/history/
Xóa file backup/reports/january.csv
Xóa thư mục backup/reports/
Xóa file backup/config.txt
Xóa thư mục backup/
```

Các ví dụ trên chỉ minh họa một thứ tự hợp lệ; **thứ tự duyệt giữa các thư mục con cùng cấp không được bảo đảm** bởi `walkFileTree`. Điều luôn cần giữ là quan hệ cha–con, không phải thứ tự theo tên file.

### Vì sao `Files.delete(root)` chưa đủ?

`Files.delete(path)` xóa **một đối tượng**. Nếu `path` là thư mục còn phần tử con, nó thường ném `DirectoryNotEmptyException`. `Files.deleteIfExists(path)` cũng không tự xóa đệ quy.

Tương tự, `Files.copy(sourceDirectory, targetDirectory)` chỉ tạo một directory đích tương ứng mà **không tự sao chép các phần tử nằm trong directory nguồn**. Muốn sao chép đầy đủ phải duyệt từng phần tử và xử lý đúng thứ tự.

## 3. `walkFileTree()` và bốn callback quan trọng

`Files.walkFileTree(start, visitor)` duyệt cây theo chiều sâu (*depth-first*). Mặc định nó **không đi theo symbolic link**. Các callback của `SimpleFileVisitor<Path>` được gọi theo giai đoạn:

| Callback | Khi nào được gọi | Áp dụng trong bài toán |
| --- | --- | --- |
| `preVisitDirectory(dir, attrs)` | **Trước** khi duyệt các phần tử của thư mục | Tạo thư mục đích khi **copy** cây |
| `visitFile(file, attrs)` | Khi gặp một file, hoặc một entry không được coi là thư mục để đi sâu | Copy file hoặc xóa file/symlink |
| `postVisitDirectory(dir, exc)` | **Sau** khi duyệt xong thư mục hoặc sau lỗi duyệt bên trong | Xóa thư mục khi **delete**; có thể áp dụng metadata sau khi copy |
| `visitFileFailed(file, exc)` | Không thể lấy thuộc tính hoặc truy cập entry/thư mục để duyệt | Báo lỗi hoặc xử lý theo chính sách minh bạch |

Sơ đồ callback cho một cây chỉ có một nhánh:

```text
enter root                  -> preVisitDirectory(root)
  enter docs                -> preVisitDirectory(docs)
    visit hello.txt         -> visitFile(hello.txt)
  leave docs                -> postVisitDirectory(docs)
leave root                  -> postVisitDirectory(root)
```

**Pre-order**: thao tác trên thư mục **trước** nội dung của nó.

**Post-order**: thao tác trên thư mục **sau** khi các phần tử con đã xử lý.

Với `SimpleFileVisitor`, hành vi mặc định của `visitFileFailed` là **ném lại `IOException`**. Trong `postVisitDirectory`, đối số `exc` có thể khác `null` nếu việc lặp phần tử thư mục gặp lỗi; không được mặc nhiên bỏ qua lỗi này rồi xóa cha.

Các giá trị `FileVisitResult` phổ biến:

- `CONTINUE`: tiếp tục duyệt.
- `SKIP_SUBTREE`: tại `preVisitDirectory`, bỏ qua các con của thư mục hiện tại.
- `SKIP_SIBLINGS`: bỏ qua các entry cùng cấp còn lại theo hợp đồng visitor.
- `TERMINATE`: dừng chuyến duyệt.

**Cảnh báo:** Trong chương trình xóa toàn bộ cây, nếu đã `SKIP_SUBTREE` nhưng vẫn tìm cách xóa thư mục cha, thư mục có thể chưa rỗng. Phải xác định rõ chính sách bỏ qua và cách xử lý thất bại, không lờ đi ngoại lệ.

## 4. Java 17+: quan sát đúng trình tự callback

Chương trình bên dưới tạo một thư mục tạm `root`, bên trong có một thư mục `docs` và một file `note.txt`. Để stdout ổn định, ta chỉ có **một nhánh thư mục** và in tên phần tử, không in đường dẫn tuyệt đối.

Lưu thành **`TreeOrderDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class TreeOrderDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("tree-order-");

        try {
            Path docs = Files.createDirectory(root.resolve("docs"));
            Files.writeString(docs.resolve("note.txt"),
                    "content", StandardCharsets.UTF_8);

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                private String name(Path path) {
                    return path.equals(root)
                            ? "root" : path.getFileName().toString();
                }

                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    System.out.println("enter " + name(dir));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    System.out.println("file " + name(file));
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(
                        Path dir, IOException exc) throws IOException {
                    if (exc != null) throw exc;
                    System.out.println("leave " + name(dir));
                    return FileVisitResult.CONTINUE;
                }
            });
        } finally {
            // Dọn dữ liệu do chương trình tạo: file trước, thư mục sau.
            Files.deleteIfExists(root.resolve("docs").resolve("note.txt"));
            Files.deleteIfExists(root.resolve("docs"));
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac TreeOrderDemo.java
java TreeOrderDemo
```

Stdout trên filesystem tạm hoạt động bình thường:

```text
enter root
enter docs
file note.txt
leave docs
leave root
```

Thứ tự này cho thấy:

1. `preVisitDirectory(root)` xuất hiện trước `preVisitDirectory(docs)`.
2. `visitFile(note.txt)` xảy ra khi đang ở trong `docs`.
3. `postVisitDirectory(docs)` chạy trước `postVisitDirectory(root)`.
4. `postVisitDirectory` là điểm thích hợp để xóa một thư mục **sau khi** các con đã được xử lý.

Đây là minh họa vòng đời callback; phần dọn trong `finally` cố ý gọi `deleteIfExists` theo thứ tự từ sâu ra nông vì ta đã biết cấu trúc. Với cây bất kỳ không biết trước, phải duyệt để xác định tất cả các entry.

## 5. Công thức sao chép cây thư mục

Ta có:

- `source`: thư mục gốc nguồn, ví dụ `/data/project`.
- `target`: thư mục đích mới, ví dụ `/backup/project`.
- Với mỗi `dir` thuộc cây nguồn, đường dẫn tương ứng tại đích là `target.resolve(source.relativize(dir))`.
- Với mỗi `file`, cũng dùng phép ánh xạ tương tự.

Ví dụ:

```text
source = /data/project
target = /backup/project

file:       /data/project/docs/help.txt
relative:   docs/help.txt
destination: /backup/project/docs/help.txt
```

`source.relativize(path)` đưa ra **đường dẫn tương đối trong cây nguồn**, còn `target.resolve(...)` đặt nó vào cây đích. Nếu `source` và `path` cùng filesystem, cách ánh xạ này dễ hiểu và tránh thao tác thay chuỗi kiểu `replace("project", "backup")` có thể sửa nhầm cả tên tệp.

### Hai callback quan trọng khi copy

```java
// Đoạn minh họa; source và target là Path đã được xác định.
// Đây là callback bên trong một SimpleFileVisitor<Path>.
@Override
public FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs) throws IOException {
    Path destination = target.resolve(source.relativize(dir));
    Files.createDirectory(destination);
    return FileVisitResult.CONTINUE;
}

@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) throws IOException {
    Path destination = target.resolve(source.relativize(file));
    Files.copy(file, destination, LinkOption.NOFOLLOW_LINKS);
    return FileVisitResult.CONTINUE;
}
```

Đây **không phải chương trình độc lập**, vì `source`, `target` và các import được tạo bên ngoài. Callback đầu tiên tạo thư mục cha; callback thứ hai copy mỗi entry khi cha của nó đã có. Chương trình đầy đủ ở mục sau triển khai cùng nguyên tắc.

`Files.copy(file, destination, LinkOption.NOFOLLOW_LINKS)` nhằm **không theo symbolic link ở file nguồn**. Trên provider hỗ trợ link, thao tác này cố copy bản thân link; nếu provider đích không hỗ trợ, có thể xảy ra `IOException` hoặc ngoại lệ hỗ trợ tính năng thích hợp. Đừng mặc định bản sao của symbolic link luôn hoạt động xuyên hệ thống.

### Copy có sao chép tất cả metadata không?

Không. `Files.copy` không mặc nhiên giữ mọi quyền, owner, ACL, timestamp hoặc attributes. `StandardCopyOption.COPY_ATTRIBUTES` yêu cầu cố gắng sao chép metadata nhưng các thuộc tính được bảo toàn phụ thuộc provider và filesystem. Nếu bạn cần giữ thuộc tính thư mục, việc áp dụng **sau khi copy xong các con** có thể thích hợp hơn, vì tạo file trong thư mục có thể làm thay đổi timestamp của thư mục.

Bài này ưu tiên **cấu trúc và nội dung**; không hứa giữ mọi metadata.

## 6. Công thức xóa cây thư mục

Ngược lại với copy:

```java
// Đoạn minh họa callback của SimpleFileVisitor<Path>.
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) throws IOException {
    Files.delete(file);
    return FileVisitResult.CONTINUE;
}

@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) throw exc;
    Files.delete(dir);
    return FileVisitResult.CONTINUE;
}
```

Đây **chưa phải chương trình độc lập**. Mấu chốt:

- `visitFile`: xóa từng file và entry không được đi sâu như directory.
- `postVisitDirectory`: xóa thư mục **sau khi** các phần tử đã được xử lý.
- `if (exc != null) throw exc;`: nếu không thể duyệt hoàn chỉnh, **không vờ rằng thư mục đã được xử lý đầy đủ**.
- `visitFileFailed`: để hành vi mặc định của `SimpleFileVisitor` ném lỗi, hoặc override để báo thất bại theo chính sách riêng. Không chỉ `return CONTINUE` và đánh dấu thao tác thành công.

Cây bị thay đổi đồng thời, entry bị khóa hoặc thiếu quyền có thể khiến `Files.delete` thất bại. Thao tác xóa cây **không nguyên tử**: nếu lỗi giữa chừng, một phần cây có thể đã bị xóa và phần còn lại tồn tại.

## 7. Ví dụ Java 17+ hoàn chỉnh: sao chép rồi xóa cây

Chương trình **`TreeCopyDeleteDemo.java`** dưới đây:

1. Tạo sandbox trong một thư mục tạm riêng.
2. Tạo cây nguồn gồm thư mục con và hai file.
3. Copy cây sang một thư mục đích **chưa tồn tại** bằng `preVisitDirectory` và `visitFile`.
4. Kiểm tra nội dung và số lượng file bằng cách truy cập đích.
5. Xóa cây đích theo thứ tự `visitFile → postVisitDirectory`.
6. Dọn cây nguồn và sandbox tạm trong `finally`.

Chương trình dùng dữ liệu do chính nó tạo, **không xóa đường dẫn người dùng nhập từ bên ngoài**.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

public class TreeCopyDeleteDemo {
    static void copyTree(Path source, Path target) throws IOException {
        final Path src = source.toAbsolutePath().normalize();
        final Path dst = target.toAbsolutePath().normalize();

        // Chỉ là guard từ vựng; với input không tin cậy cần thêm biện pháp.
        if (src.equals(dst) || dst.startsWith(src)) {
            throw new IllegalArgumentException("target is inside source");
        }
        if (!Files.isDirectory(src, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("source must be a directory");
        }
        if (Files.exists(dst, LinkOption.NOFOLLOW_LINKS)) {
            throw new FileAlreadyExistsException(dst.toString());
        }

        Files.walkFileTree(src, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult preVisitDirectory(
                    Path dir, BasicFileAttributes attrs) throws IOException {
                Path destination = dst.resolve(src.relativize(dir));
                Files.createDirectory(destination);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) throws IOException {
                Path destination = dst.resolve(src.relativize(file));
                Files.copy(file, destination, LinkOption.NOFOLLOW_LINKS);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFileFailed(
                    Path file, IOException exc) throws IOException {
                throw exc;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException exc) throws IOException {
                if (exc != null) throw exc;
                return FileVisitResult.CONTINUE;
            }
        });
    }

    static void deleteTree(Path root) throws IOException {
        // Mặc định walkFileTree KHÔNG theo symbolic links.
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFileFailed(
                    Path file, IOException exc) throws IOException {
                throw exc;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException exc) throws IOException {
                if (exc != null) throw exc;
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws IOException {
        Path sandbox = Files.createTempDirectory("tree-demo-");
        Path source = sandbox.resolve("source");
        Path target = sandbox.resolve("copy");

        try {
            Files.createDirectory(source);
            Files.createDirectory(source.resolve("docs"));
            Files.writeString(source.resolve("note.txt"),
                    "hello", StandardCharsets.UTF_8);
            Files.writeString(source.resolve("docs").resolve("guide.txt"),
                    "guide", StandardCharsets.UTF_8);

            copyTree(source, target);

            System.out.println("root copied = "
                    + Files.isDirectory(target));
            System.out.println("nested file copied = "
                    + Files.isRegularFile(target.resolve("docs")
                            .resolve("guide.txt")));
            System.out.println("copied content = "
                    + Files.readString(target.resolve("note.txt"),
                            StandardCharsets.UTF_8));
            System.out.println("source remains = "
                    + Files.exists(source));

            deleteTree(target);
            System.out.println("copy deleted = "
                    + Files.notExists(target));
        } finally {
            // Dọn những dữ liệu do chính ví dụ tạo ra, kể cả sau lỗi copy.
            if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
                deleteTree(target);
            }
            if (Files.exists(source, LinkOption.NOFOLLOW_LINKS)) {
                deleteTree(source);
            }
            Files.deleteIfExists(sandbox);
        }
    }
}
```

Chạy:

```bash
javac TreeCopyDeleteDemo.java
java TreeCopyDeleteDemo
```

Stdout khi các thao tác file tạm thành công:

```text
root copied = true
nested file copied = true
copied content = hello
source remains = true
copy deleted = true
```

### Vì sao code này đúng thứ tự?

**Trong `copyTree`:**

- Lần đầu `preVisitDirectory(src)` tạo `dst`, tức thư mục gốc của cây đích.
- Với mỗi thư mục con, callback tạo thư mục tương ứng trước khi visitor đi sâu xuống các phần tử bên trong.
- `visitFile` thực hiện copy khi thư mục cha đã được tạo.
- `src.relativize(...)` và `dst.resolve(...)` bảo toàn cấu trúc tương đối của mỗi entry.
- `Files.copy` chỉ cần thao tác trên từng file/symlink riêng lẻ; thuật toán không giả định một lời gọi copy thư mục sẽ copy luôn nội dung đệ quy.

**Trong `deleteTree`:**

- `visitFile` xóa từng file/symlink khi nó được gặp.
- Chỉ sau khi các con của một directory đã được xử lý, `postVisitDirectory` mới xóa directory ấy.
- Thư mục gốc `target` cũng được xóa ở callback cuối, sau mọi nội dung bên trong.

### Hạn chế có chủ đích của ví dụ

Để giữ ví dụ dễ chạy, nó giả định **file và thư mục thường trên filesystem tạm có quyền ghi**. Đây không phải thư viện copy/delete production tổng quát:

- Chỉ từ chối đích nằm trong nguồn bằng **kiểm tra đường dẫn từ vựng**; chưa chống symlink/junction, mount, thay đổi đồng thời hoặc đối tượng được đổi tên khi đang thao tác.
- Không ghi đè đích đã tồn tại và không xử lý hợp nhất nội dung của các thư mục.
- Không copy đầy đủ ACL, owner, mọi timestamp, hard links hoặc các khả năng phụ thuộc provider.
- Không bảo đảm tính nguyên tử; nếu sao chép lỗi giữa chừng thì đích có thể chỉ được tạo một phần.
- Không giới hạn tổng số file, byte, độ sâu hay thời gian khi gặp dữ liệu ngoài hệ thống.
- `finally` minh họa cleanup trong sandbox riêng. Với dữ liệu quan trọng, xóa nguồn/đích sau một lỗi phải theo **chính sách phục hồi**, không được áp dụng vô điều kiện như với dữ liệu test.

## 8. Vì sao không nên sao chép cây vào bên trong chính nguồn?

Giả sử sao chép `source/` sang `source/backup/`. Khi visitor đi qua `source`, nó có thể nhìn thấy thư mục `backup` vừa được tạo trong lúc duyệt. Tùy thời điểm và thứ tự liệt kê, chương trình có thể vô tình copy thư mục đích vào chính nó, lặp không kiểm soát hoặc tạo cây phình to.

Vì vậy, đối với thuật toán copy cây cần:

1. Từ chối `source == target`.
2. Từ chối target là đường dẫn con của source theo chính sách đã định.
3. Giải quyết rõ trường hợp symbolic link hoặc mount khiến đường dẫn thật khác tên đường dẫn.
4. Tránh copy cây đang bị thay đổi đồng thời nếu định dạng kết quả yêu cầu snapshot nhất quán.

`dst.startsWith(src)` sau khi chuẩn hóa chỉ là một kiểm tra **cú pháp**, không phải đảm bảo bảo mật. Với đường dẫn do người dùng cung cấp, ứng dụng còn cần quản lý quyền truy cập, symlink, kiểm tra thư mục thực và biện pháp chống race nếu có thể.

Cũng không nên để target **bao trùm** source rồi vô tình ghi đè file nguồn qua một phép ánh xạ không được thiết kế cẩn thận. Khi quan hệ nguồn/đích phức tạp, hãy tách vùng lưu trữ/staging rõ ràng.

## 9. Symbolic link, symlink loop và file đặc biệt

Theo mặc định:

```java
Files.walkFileTree(start, visitor);
```

tương đương với duyệt không có `FileVisitOption.FOLLOW_LINKS`, theo mọi cấp. Vì vậy:

- Một symlink trỏ đến thư mục khác **không bị đi sâu theo thư mục đích** trong lần duyệt mặc định.
- `visitFile` có thể nhận entry symlink, dù nó không phải regular file.
- Khi xóa, `Files.delete(linkPath)` xóa **entry symlink**, không xóa cả cây mà link trỏ tới (theo ngữ nghĩa các provider thông thường có hỗ trợ symbolic link).
- Khi copy với `LinkOption.NOFOLLOW_LINKS`, ta yêu cầu copy **bản thân symbolic link**, không lấy dữ liệu ở đích mà link trỏ tới. Phải xác minh đích hỗ trợ kiểu entry ấy.
- Nếu dùng `FOLLOW_LINKS`, traversal có thể đi ra ngoài phạm vi ban đầu qua link. Java có cơ chế phát hiện chu trình và báo `FileSystemLoopException` qua `visitFileFailed`, nhưng điều đó **không thay thế chính sách bảo vệ đường dẫn**.

**Tại sao xóa cây thường không nên theo symbolic link?** Vì một link bên trong thư mục bạn định xóa có thể trỏ đến cây khác nằm ngoài phạm vi được phép. Việc vô tình đệ quy theo link có thể xóa dữ liệu **không thuộc** cây đích theo ý định ban đầu.

Còn có:

- File đặc biệt, FIFO/socket node hoặc filesystem ảo có ngữ nghĩa riêng.
- Permission và file đang được mở/khóa.
- Các giới hạn file name, path length, quota, max depth.
- Provider không hỗ trợ symlink, owner metadata hoặc thao tác đặc biệt.

Đối với input không tin cậy hoặc cần bảo đảm bảo mật cao, một phép duyệt `walkFileTree` đơn giản không tự khóa cây trước thay đổi đồng thời. Cần thiết kế việc cấp quyền, giới hạn phạm vi, chính sách symlink, và khi provider hỗ trợ có thể xem xét API tương đối với directory handle, chẳng hạn `SecureDirectoryStream`.

## 10. Xử lý lỗi trong callback như thế nào?

### Không thể đọc file hoặc mở directory

`visitFileFailed(file, exc)` nhận lỗi đã ngăn việc truy cập entry. Nếu mục tiêu là **copy đầy đủ** hoặc **xóa đầy đủ**, cách an toàn mặc định là **ném ngoại lệ**, không âm thầm bỏ qua.

```java
// Snippet callback, không phải chương trình độc lập.
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    throw exc;
}
```

Nếu nghiệp vụ cho phép **best-effort** (xử lý được bao nhiêu hay bấy nhiêu), có thể thu thập các lỗi theo từng đường dẫn. Nhưng phải báo kết quả là **hoàn tất một phần**, không được mô tả “đã sao chép/xóa toàn bộ cây” khi còn lỗi.

### Không thể liệt kê hết thư mục

`postVisitDirectory(dir, exc)` nhận `exc != null` khi traversal của directory bị lỗi; ví dụ không thể hoàn tất việc liệt kê entry. Nếu đang xóa, không thể mặc nhiên cho rằng thư mục đã trống và hợp lệ để xóa.

```java
// Snippet callback.
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) throw exc;
    Files.delete(dir);
    return FileVisitResult.CONTINUE;
}
```

### `DirectoryNotEmptyException` và race

Nếu một tiến trình khác tạo file mới trong directory sau khi visitor đã liệt kê xong nhưng trước `Files.delete(dir)`, việc xóa thư mục có thể thất bại. `DirectoryNotEmptyException` không có nghĩa Java duyệt sai thứ tự: cây có thể đã thay đổi.

Tương tự, file có thể bị xóa bởi tiến trình khác ngay trước lúc bạn gọi `Files.delete(file)` và phát sinh `NoSuchFileException`. Có thể chọn `deleteIfExists` nếu nghiệp vụ coi file đã biến mất là chấp nhận được; đừng tự động thay hết `delete` bằng `deleteIfExists` nếu việc tồn tại là ràng buộc quan trọng.

### Vì sao `try/catch` không làm thao tác nguyên tử?

Bọc toàn bộ traversal trong `try/catch(IOException)` giúp thông báo lỗi nhưng **không hoàn tác** những file đã copy hoặc xóa. Một số entry đã được tạo/xóa trước khi callback gặp lỗi vẫn có thể giữ nguyên trạng thái mới. Cần có cơ chế staging, rollback hoặc reconciliation nếu nghiệp vụ đòi hỏi trạng thái nhất quán.

## 11. `Files.walk()` so với `Files.walkFileTree()`

`Files.walk(root)` trả về `Stream<Path>` để xử lý các path trong cây. Nó có thể hữu ích khi bạn chỉ muốn lọc/tổng hợp danh sách file. Nhưng khi cần copy/delete có ràng buộc cha–con, `walkFileTree` thể hiện ý nghĩa callback rõ ràng hơn.

| Tiêu chí | `Files.walk(root)` | `Files.walkFileTree(root, visitor)` |
| --- | --- | --- |
| Kiểu trả về | `Stream<Path>`, cần đóng | Trả lại `Path` bắt đầu sau khi duyệt |
| Điều khiển pre/post | Không có callback tách rõ | Có `preVisitDirectory` và `postVisitDirectory` |
| Phân biệt lỗi | Lỗi khi duyệt stream có thể thành `UncheckedIOException` | Có `visitFileFailed` và đối số `exc` |
| Lọc/đếm path | Tiện với Stream API | Làm qua visitor/state |
| Copy cây theo điều kiện cha trước | Cần tự tổ chức ràng buộc | `preVisitDirectory` rất phù hợp |
| Xóa cây theo điều kiện con trước | Cần sắp thứ tự rõ ràng | `postVisitDirectory` rất phù hợp |
| Symlink | Mặc định không follow; có tùy chọn | Mặc định không follow; có tùy chọn |

Một số ví dụ trên mạng dùng:

```java
// Snippet, không phải chương trình độc lập:
try (Stream<Path> stream = Files.walk(root)) {
    stream.sorted(Comparator.reverseOrder())
          .forEach(path -> {
              // Thực hiện delete từng path...
          });
}
```

Cách này **không tự giải quyết** ngoại lệ I/O, phạm vi được xóa và vấn đề đường dẫn đang thay đổi. Nếu dùng Stream phải đóng stream, đồng thời xử lý `IOException` ở bước xóa (lambda có thể cần bọc thành unchecked). Thứ tự so sánh đường dẫn còn gắn với semantics của provider: đừng dùng chỉ `Path.toString()` theo thứ tự chữ như bằng chứng tổng quát về thứ tự cha–con. Đối với copy/delete, visitor có callback cha/trước và cha/sau thể hiện mục đích rõ hơn.

### `FileVisitor` có bảo đảm thứ tự tên file không?

Không. Thứ tự entry của một thư mục thường phụ thuộc filesystem/provider và trạng thái dữ liệu. Nếu cần xử lý theo tên tăng dần vì mục đích nghiệp vụ, phải thiết kế cơ chế liệt kê/sắp thứ tự riêng và kiểm soát tài nguyên. **Đừng làm bài copy/delete phụ thuộc vào thứ tự chữ cái** của sibling.

## 12. Metadata và thời điểm sao chép attributes

Bài toán “copy tree” đôi khi phải giữ permission, thời điểm sửa, owner hoặc ACL. Tuy nhiên `COPY_ATTRIBUTES` không bảo đảm mọi metadata được giữ và có thể hành xử khác giữa POSIX/Windows/ZIP/cloud provider.

Đặc biệt với **thư mục**, nếu copy timestamp quá sớm ở `preVisitDirectory`, các thao tác tạo file và subdirectory bên trong có thể làm thay đổi `lastModifiedTime` của thư mục. Một cách thiết kế là:

1. `preVisitDirectory`: tạo directory đích và chuẩn bị quyền ghi cần thiết.
2. `visitFile`: sao chép file và attributes nào thật sự được hỗ trợ.
3. `postVisitDirectory`: sau khi các con hoàn tất, đặt lại metadata thư mục theo hợp đồng (nếu có yêu cầu và provider hỗ trợ).
4. Nếu metadata bắt buộc mà không copy được, báo thất bại thay vì coi “copy thành công” không cần kiểm tra.

Ví dụ minh họa thuật toán, **không phải chương trình độc lập**:

```java
// Giả định source/destinationDirectory là Path hợp lệ;
// policies và handling lỗi được quyết định ở nơi gọi.
FileTime stamp = Files.getLastModifiedTime(sourceDirectory);
Files.setLastModifiedTime(destinationDirectory, stamp);
```

Đoạn này cần import `java.nio.file.attribute.FileTime` và các biến đã được khai báo. Không đảm bảo mọi provider cho phép đặt chính xác timestamp hoặc giữ owner/ACL.

## 13. Copy/xóa trên dữ liệu thực: an toàn và phục hồi

Sao chép hoặc xóa một cây lớn có nhiều điểm có thể thất bại: dung lượng đĩa, lỗi mạng, quyền truy cập, symlink, quá nhiều entry, giới hạn độ sâu, file bị thay đổi đồng thời hoặc ứng dụng bị dừng.

Một quy trình thực tế nên xác định:

1. **Nguồn và đích:** canonical/real location khi phù hợp, từ chối copy target nằm trong source và không trộn đường dẫn của provider khác trong phép `relativize` không tương thích.
2. **Loại đối tượng:** regular files, directories, symlinks, special files và chiến lược cho từng loại.
3. **Quota:** giới hạn số file, tổng byte, chiều sâu, thời gian thực thi; không cứ thấy file là copy vô hạn.
4. **Quy tắc ghi đè:** không ghi đè, ghi đè có xác minh hay tạo phiên bản mới; cần giải quyết xung đột tên/permission.
5. **Staging:** có thể copy vào một thư mục tạm của đích, xác minh xong mới công bố. Staging không mặc nhiên biến cả cây thành một giao dịch nguyên tử xuyên filesystem.
6. **Verify:** kiểm tra đủ file, kích thước, hash khi cần, attributes bắt buộc; không coi `Files.copy` trả về là đủ cho mọi yêu cầu nghiệp vụ.
7. **Lỗi giữa chừng:** báo các path đã làm, path thất bại, quyết định cleanup theo quyền sở hữu dữ liệu; không tự xóa bản duy nhất của dữ liệu nguồn.
8. **Xóa:** kiểm tra thư mục đích thật chính xác, có backup/confirmation khi nghiệp vụ đòi hỏi, không duyệt theo symlink ngoài phạm vi.
9. **Concurrency:** cân nhắc khóa, snapshot hoặc ngừng writer nếu nhất quán là yêu cầu bắt buộc; `walkFileTree` không chụp ảnh snapshot toàn bộ cây.
10. **Provider:** ZIP/network/cloud filesystem có giới hạn và ngoại lệ khác nhau; phải kiểm thử trên provider thật.

Đối với thao tác **xóa**, tuyệt đối không gọi `deleteTree` trên đường dẫn rỗng, đường dẫn gốc filesystem hoặc path từ request chưa được xác minh trong ứng dụng production. Một demo xóa thư mục tạm do nó tự tạo là an toàn trong phạm vi bài học; điều đó không cấp phép xóa dữ liệu người dùng tùy tiện.

## 14. Bảng tóm tắt thứ tự

| Bài toán | Thời điểm đúng | Callback |
| --- | --- | --- |
| Copy thư mục cha | Trước khi vào các phần tử con | `preVisitDirectory` |
| Copy file | Sau khi thư mục cha đích đã có | `visitFile` |
| Thiết lập metadata thư mục sau copy | Sau khi copy xong các con (khi cần) | `postVisitDirectory` |
| Xóa file/symlink | Khi gặp entry | `visitFile` |
| Xóa thư mục | Sau khi xóa hết các con | `postVisitDirectory` |
| Xử lý file không truy cập được | Tại lỗi truy cập | `visitFileFailed` |
| Phát hiện directory iteration lỗi | Trong callback hậu duyệt | Kiểm tra `exc` của `postVisitDirectory` |

## 15. Những lỗi phổ biến

1. **Gọi `Files.copy(sourceDir, targetDir)` và nghĩ toàn bộ con được copy.** API này không tự copy đệ quy.
2. **Gọi `Files.delete(root)` khi root còn file con.** Cần xóa các entry con trước khi xóa root.
3. **Tạo file đích trước khi có directory cha.** Dùng `preVisitDirectory` để tạo thư mục đích theo cấp.
4. **Xóa directory trong `preVisitDirectory`.** Các con chưa bị xóa, nên thường gặp `DirectoryNotEmptyException`.
5. **Copy target nằm bên trong source.** Có thể làm cây copy tự đi vào chính nó; phải chặn theo chính sách tin cậy.
6. **Dùng `Files.walk` mà quên đóng Stream.** Có thể giữ descriptor/directory handle; dùng `try-with-resources`.
7. **Mặc định theo symbolic link khi xóa.** Có thể đi ra ngoài phạm vi và gây mất dữ liệu khác; mặc định `walkFileTree` không follow.
8. **Nuốt `IOException` trong visitor rồi báo hoàn tất.** Dẫn tới bản copy thiếu file hoặc cây xóa dở.
9. **Bỏ qua `exc` của `postVisitDirectory`.** Không thể kết luận thư mục đã được duyệt đầy đủ.
10. **Cho rằng copy/delete đệ quy là một transaction.** Có thể thành công một phần; cần policy về retry/cleanup.
11. **Cho rằng mọi provider hỗ trợ symlink, ACL, owner/timestamp giống nhau.** Khả năng khác nhau, phải kiểm tra thực tế.
12. **Thử “xóa cho xong” cây khi có writer đang tạo file mới.** Có thể liên tục thất bại hoặc xóa ngoài dự tính.
13. **Chỉ so sánh tên đường dẫn để bảo vệ dữ liệu quan trọng.** Symlink và race có thể làm vị trí thực khác ý định.
14. **Dùng `FileVisitResult.SKIP_SUBTREE` nhưng vẫn tính là đã xử lý hết.** Những entry bỏ qua vẫn còn nguyên.
15. **Dựa vào thứ tự chữ cái của file siblings để bảo đảm đúng thuật toán.** `walkFileTree` không hứa thứ tự đó; phải dựa vào quan hệ cha–con.

## 16. Tự kiểm tra

**Câu 1.** Tại sao phải tạo thư mục đích ở `preVisitDirectory`, không phải `postVisitDirectory`?

**Trả lời:** Vì file và thư mục con cần cha tồn tại trước khi copy. `postVisitDirectory` chạy sau khi các con đã xử lý nên quá muộn để tạo cha.

**Câu 2.** Tại sao phải xóa thư mục ở `postVisitDirectory`, không phải `preVisitDirectory`?

**Trả lời:** Vì thư mục đang còn phần tử con thì chưa thể xóa như thư mục rỗng. Callback hậu duyệt chạy sau khi các con được xử lý.

**Câu 3.** Một file bị lỗi quyền đọc trong quá trình copy cây. Có nên `return CONTINUE` rồi báo “copy đầy đủ” không?

**Trả lời:** Không. Phải ném/báo lỗi, hoặc đánh dấu kết quả hoàn tất một phần nếu nghiệp vụ cho phép bỏ qua.

**Câu 4.** Duyệt để xóa cây có symbolic link trỏ sang thư mục khác; có nên tự bật `FOLLOW_LINKS` không?

**Trả lời:** Không nên mặc định. Cần bảo vệ phạm vi xóa; mặc định không theo link sẽ xử lý entry liên kết thay vì duyệt vào đích.

**Câu 5.** Tại sao `target.resolve(source.relativize(file))` hữu ích cho copy cây?

**Trả lời:** Nó giữ đường dẫn tương đối của file bên trong source và ghép vào target, bảo toàn cấu trúc thư mục.

**Câu 6.** Nếu copy lỗi sau khi tạo một phần file tại target, có bảo đảm rollback tự động không?

**Trả lời:** Không. Phải xây dựng chiến lược cleanup, staging và xác minh kết quả nếu nghiệp vụ yêu cầu.

**Câu 7.** Có thể dựa vào `Files.walkFileTree` để duyệt `a.txt` trước `b.txt` không?

**Trả lời:** Không. API không bảo đảm thứ tự tên của các entry cùng cấp; chỉ có quy tắc callback trước/sau các phần tử con.

**Câu 8.** `DirectoryNotEmptyException` khi xóa một directory đã duyệt xong luôn là lỗi sắp xếp thứ tự không?

**Trả lời:** Không. Một tiến trình khác có thể vừa tạo file mới; hoặc visitor đã bỏ qua/lỗi khi xử lý entry. Cần kiểm tra nguyên nhân.

## 17. Tài liệu Java 17

- [`Files.walkFileTree`, `Files.copy`, `Files.delete`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`FileVisitor` — callbacks của quá trình duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitor.html)
- [`SimpleFileVisitor` — hành vi mặc định và cách override](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SimpleFileVisitor.html)
- [`FileVisitResult` — CONTINUE, SKIP_SUBTREE, SKIP_SIBLINGS, TERMINATE](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitResult.html)

**Ghi nhớ:** Để **copy cây**, tạo thư mục đích khi bắt đầu duyệt thư mục (`preVisitDirectory`), sau đó copy từng file (`visitFile`). Để **xóa cây**, xóa file ở `visitFile` và xóa thư mục chỉ khi các con đã xử lý xong (`postVisitDirectory`). `Files.walkFileTree` giúp biểu diễn đúng quy tắc cha–con; kết quả cuối vẫn phụ thuộc xử lý lỗi, symlink, quyền truy cập và trạng thái filesystem.