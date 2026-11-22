# Phát hiện vòng lặp liên kết trong cây tệp với Java NIO

## 1. Mục tiêu và phạm vi

Khi duyệt một cây thư mục, các entry không nhất thiết tạo thành **cây thực sự**. Một symbolic link (liên kết tượng trưng, thường gọi là *symlink*) có thể trỏ tới một thư mục cha hoặc chính gốc đang duyệt. Nếu chương trình **đi theo liên kết** một cách thiếu kiểm soát, nó có thể quay lại thư mục từng đi qua rồi lặp vô hạn, quét trùng dữ liệu, tiêu tốn thời gian hoặc vượt khỏi khu vực tệp mà ứng dụng dự định xử lý.

Java NIO.2, được giới thiệu từ **Java 7**, hỗ trợ duyệt cây an toàn bằng `Files.walkFileTree` và cung cấp `FileVisitOption.FOLLOW_LINKS` cùng `FileSystemLoopException`. Các API này **vẫn được hỗ trợ trong Java hiện hành**. Bài này giải thích chính xác thế nào là vòng lặp, cách Java nhận diện, phân biệt kết quả khi **không theo** và **có theo** symbolic link, và cách xử lý lỗi mà không nhầm với symlink hợp lệ.

Kết thúc bài, bạn sẽ:

1. Vẽ và nhận ra vòng lặp trong cây file do liên kết trỏ ngược về **tổ tiên**.
2. Phân biệt `Path`/tên đường dẫn với **định danh file hoặc thư mục thực**, và hiểu vai trò của `BasicFileAttributes.fileKey()` cùng `Files.isSameFile()`.
3. Hiểu rằng `Files.walkFileTree(root, visitor)` **không theo symbolic links theo mặc định**.
4. Bật `FOLLOW_LINKS` có chủ đích, phát hiện `FileSystemLoopException` trong callback `visitFileFailed`, và chọn `CONTINUE` hoặc dừng/lan truyền lỗi theo nghiệp vụ.
5. Phân biệt **vòng lặp thực** với trường hợp cùng một thư mục được đến qua hai alias ở **hai nhánh không phải tổ tiên của nhau**.
6. Biết `Files.walk(..., FOLLOW_LINKS)` (Java 8+) đưa lỗi I/O phát sinh trong khi tiêu thụ stream ra dưới dạng `UncheckedIOException`.
7. Biết `maxDepth` giới hạn độ sâu duyệt, **không** phải bằng chứng đã kiểm tra hết mọi liên kết hay một sandbox giới hạn đường dẫn.
8. Nhận ra liên kết hợp lệ nhưng dẫn **ra ngoài root** — không tạo cycle nhưng vẫn có thể vi phạm chính sách truy cập.
9. Viết kiểm thử thực trên filesystem hỗ trợ symbolic links; xử lý trung thực trường hợp test bị **SKIPPED** do không có quyền tạo link.
10. Chọn cách duyệt phù hợp cho backup, indexing, tìm kiếm tệp hoặc quét nội dung với chính sách symlink rõ ràng.

**Phiên bản ví dụ:** Tất cả chương trình hoàn chỉnh sử dụng cú pháp **Java 17+**, biên dịch bằng `javac -encoding UTF-8 --release 17`. `Files.walkFileTree`, `FOLLOW_LINKS`, `FileSystemLoopException`, `SimpleFileVisitor`, `isSameFile` đã tồn tại từ Java 7; `Files.walk` xuất hiện từ Java 8. Không cần dùng API đã lỗi thời.

**Giới hạn môi trường:** Các ví dụ được biên dịch và chạy trên OpenJDK 21 với `--release 17`. Phần có symlink thật đã được kiểm chứng trên filesystem Linux cho phép tạo symbolic link. Trong một môi trường Windows không có quyền phù hợp, lời gọi `Files.createSymbolicLink` bị từ chối; các chương trình tương ứng in `symlinkTest=SKIPPED`. Đó **không phải** kết quả kiểm thử cycle đã PASS trên Windows; phải chạy lại trên filesystem có quyền hoặc cấu hình phù hợp.

## 2. Vì sao cây thư mục có thể chứa chu trình?

Hãy tưởng tượng:

~~~text
root/
└── child/
    └── back -> root/
~~~

`back` là một symlink nằm trong `child` nhưng **trỏ về `root`**, tức một thư mục tổ tiên. Nếu luôn follow link, đường đi logic có thể trông như:

~~~text
root
  -> child
     -> back (đích là root)
        -> child
           -> back (đích là root)
              -> ...
~~~

Đó là một **cycle**. Cơ chế phát hiện vòng lặp cần quan tâm **thư mục đích thực sự**, chứ không chỉ nhìn chuỗi đường dẫn khác nhau. Hai đường dẫn:

~~~text
/tmp/root
/tmp/root/child/back
~~~

có thể là hai `Path` khác nhau nhưng trỏ tới **cùng một thư mục**.

### 2.1. Symlink không giống shortcut văn bản

- **Symbolic link:** Một entry trong filesystem tham chiếu tới một đường dẫn khác. Đích có thể là file, thư mục, không tồn tại hoặc trỏ qua nhiều lớp liên kết.
- **Hard link:** Một tên khác cùng liên hệ tới một đối tượng file theo cơ chế của filesystem; không đồng nghĩa với symlink và không nhất thiết được hỗ trợ cho directory. Bài này tập trung vào **symlink tạo vòng lặp thư mục**.
- **Path:** Cách biểu diễn một đường dẫn. `Path.equals()` thường là so sánh theo biểu diễn/path provider, không tự thực hiện phép kiểm tra hai đường dẫn cùng một thực thể tệp.
- **File identity:** Khái niệm thư mục thực mà filesystem cho phép xác định bằng attributes/file key hoặc `Files.isSameFile`.
- **Ancestor:** Một thư mục đang nằm trên **đường đi từ gốc tới node hiện tại**; khác với “mọi thư mục đã từng duyệt ở bất cứ nhánh nào”.

**Quan trọng:** Một chu trình trong DFS xuất hiện khi ta định đi vào **thư mục đã có trên chuỗi tổ tiên hiện tại**, không phải chỉ vì thư mục ấy từng được thấy ở một nhánh trước đó.

### 2.2. Hai hình cần phân biệt

Vòng lặp cần chặn:

~~~text
root/
└── child/
    └── back -> root/
~~~

Không phải vòng lặp dù có alias trùng đích:

~~~text
root/
├── shared/
├── alias-a -> shared/
└── alias-b -> shared/
~~~

Trong trường hợp thứ hai, khi duyệt `root/alias-a` hoặc `root/alias-b`, thư mục `shared` **không phải tổ tiên của chính alias đang duyệt**. Nếu theo liên kết, thuật toán có thể duyệt cùng nội dung `shared` nhiều lần, nhưng đó là **duplicate traversal**, không phải cycle theo định nghĩa của `walkFileTree`.

## 3. Hai chế độ duyệt cây trong `Files.walkFileTree`

### 3.1. Mặc định: không đi theo symbolic link

Lời gọi:

~~~java
Files.walkFileTree(root, visitor);
~~~

tương đương về cấu hình với:

~~~java
Files.walkFileTree(
        root,
        EnumSet.noneOf(FileVisitOption.class),
        Integer.MAX_VALUE,
        visitor);
~~~

Đây là **đoạn minh họa trong phương thức**, với `root` kiểu `Path` và `visitor` kiểu `FileVisitor<Path>`.

- Symlink không được tự động theo để mở thư mục đích.
- Symlink vẫn có thể xuất hiện dưới callback `visitFile` như một entry; `BasicFileAttributes.isSymbolicLink()` có thể dùng nhận diện nó.
- Vì không đi theo link, bộ duyệt sẽ không bị dẫn theo symlink `child/back → root` vào một nhánh vô hạn.
- Mặc định này thường phù hợp cho ứng dụng muốn **kiểm kê cây theo cấu trúc vật lý entry** mà không đưa các target liên kết vào phạm vi duyệt.

**Không diễn giải “không theo liên kết” thành “không thấy liên kết”.** Nếu hệ thống cần backup metadata của symlink, việc nhìn thấy entry symlink rất quan trọng.

### 3.2. Bật `FOLLOW_LINKS`

Lời gọi:

~~~java
Files.walkFileTree(
        root,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor);
~~~

cho phép đi theo symbolic link khi có thể. Lúc này một symlink trỏ tới directory thường được xử lý như đi vào thư mục đích, trừ khi có lỗi hoặc một vòng lặp.

Khi `FOLLOW_LINKS` bật, Java **theo dõi các thư mục trên nhánh hiện tại** để phát hiện nếu một entry dẫn về một thư mục tổ tiên. Theo Javadoc:

- Java dùng `BasicFileAttributes.fileKey()` để nhận diện thư mục nếu hệ thống cung cấp key;
- nếu key không khả dụng, cơ chế có thể dùng `Files.isSameFile()` để so sánh với tổ tiên;
- khi phát hiện vòng lặp, bộ duyệt coi đó là một **I/O error** và gọi `visitor.visitFileFailed(path, new FileSystemLoopException(...))`.

Bằng cách này, vòng lặp được **báo thành một sự kiện có kiểm soát**, thay vì đi vào mãi.

Nguồn: [Oracle Java SE 26 — Files.walkFileTree](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html) và [Oracle Java SE 26 — FileVisitOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileVisitOption.html).

### 3.3. Các callback chính của FileVisitor

| Callback | Khi nào xảy ra | Điều nên làm |
| --- | --- | --- |
| `preVisitDirectory(dir, attrs)` | Trước khi đi vào một directory | Quyết định `CONTINUE` hoặc `SKIP_SUBTREE` theo chính sách |
| `visitFile(file, attrs)` | Khi gặp file/entry được thăm mà không đi sâu | Xử lý file, symlink không theo, hoặc entry tại `maxDepth` |
| `visitFileFailed(file, exc)` | Khi không thể thăm entry, kể cả khi phát hiện cycle | Phân loại `FileSystemLoopException` và lỗi khác |
| `postVisitDirectory(dir, exc)` | Sau khi xử lý xong nội dung directory, hoặc lỗi khi lặp directory | Ghi nhận thành công/lỗi, kiểm soát tiến trình |

Class `SimpleFileVisitor<Path>` cung cấp các cài đặt mặc định; đặc biệt, `visitFileFailed` theo mặc định **ném lại lỗi I/O**. Nếu muốn **bỏ qua cycle và tiếp tục**, cần override có chủ đích. Đừng bắt mọi lỗi rồi `return CONTINUE` không điều kiện trong một công cụ backup hoặc kiểm toán dữ liệu.

## 4. Ví dụ 1 — Duyệt cây bình thường không theo link

Tạo file `NoFollowTreeDemo.java`. Ví dụ này **không cần quyền tạo symlink**, kiểm thử cấu trúc visitor cơ bản, đếm thư mục và file thường.

~~~java
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.concurrent.atomic.AtomicInteger;

public class NoFollowTreeDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("nofollow-");
        Path sub = Files.createDirectory(root.resolve("sub"));
        Path a = root.resolve("a.txt");
        Path b = sub.resolve("b.txt");

        try {
            Files.createFile(a);
            Files.createFile(b);

            AtomicInteger dirs = new AtomicInteger();
            AtomicInteger files = new AtomicInteger();

            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    dirs.incrementAndGet();
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    if (attrs.isRegularFile()) {
                        files.incrementAndGet();
                    }
                    return FileVisitResult.CONTINUE;
                }
            });

            System.out.println("directories=" + dirs.get());
            System.out.println("regularFiles=" + files.get());
        } finally {
            Files.deleteIfExists(b);
            Files.deleteIfExists(a);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 NoFollowTreeDemo.java
java NoFollowTreeDemo
~~~

Stdout:

~~~text
directories=2
regularFiles=2
~~~

Có hai thư mục `root` và `sub`, hai file `a.txt` và `b.txt`. Thứ tự file do filesystem trả về không ảnh hưởng kết quả đếm. Chương trình chỉ chứng minh visitor/cleanup hoạt động; kiểm tra hành vi với **symlink thực** nằm ở ví dụ kế tiếp.

**Tại sao phải dọn từ dưới lên?** `Files.deleteIfExists` không xóa một directory còn chứa entry. Xóa file con trước, rồi thư mục con, cuối cùng mới xóa root. Đây cũng là quy tắc quan trọng nếu đang viết công cụ cleanup — đừng theo symlink ngoài ý muốn khi xóa.

## 5. Ví dụ 2 — Tạo vòng lặp symlink thật và phát hiện bằng visitor

Dựng:

~~~text
root/
└── child/
    └── back -> root/
~~~

Ví dụ sau có hai lượt:

- **Không FOLLOW_LINKS:** đếm symlink như một entry, không đi sâu vào target.
- **Có FOLLOW_LINKS:** bộ duyệt thấy target là tổ tiên, gọi `visitFileFailed` với `FileSystemLoopException` và tiếp tục vì visitor trả `CONTINUE`.

Tạo file `FollowLinksCycleDemo.java`:

~~~java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;
import java.util.concurrent.atomic.AtomicInteger;

public class FollowLinksCycleDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("cycle-demo-");
        Path child = Files.createDirectory(root.resolve("child"));
        Path back = child.resolve("back");

        try {
            try {
                Files.createSymbolicLink(back, root);
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException e) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            AtomicInteger symlinks = new AtomicInteger();
            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult visitFile(
                        Path p, BasicFileAttributes attrs) {
                    if (attrs.isSymbolicLink()) {
                        symlinks.incrementAndGet();
                    }
                    return FileVisitResult.CONTINUE;
                }
            });

            AtomicInteger loops = new AtomicInteger();
            AtomicInteger dirs = new AtomicInteger();

            Files.walkFileTree(
                    root,
                    EnumSet.of(FileVisitOption.FOLLOW_LINKS),
                    Integer.MAX_VALUE,
                    new SimpleFileVisitor<>() {
                        @Override
                        public FileVisitResult preVisitDirectory(
                                Path p, BasicFileAttributes attrs) {
                            dirs.incrementAndGet();
                            return FileVisitResult.CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFileFailed(
                                Path p, IOException e)
                                throws IOException {
                            if (e instanceof FileSystemLoopException) {
                                loops.incrementAndGet();
                                return FileVisitResult.CONTINUE;
                            }
                            throw e;
                        }
                    });

            System.out.println("nofollowSawLink=" +
                    (symlinks.get() == 1));
            System.out.println("followDirs=" + dirs.get());
            System.out.println("loopEvents=" + loops.get());
            System.out.println("sameTarget=" +
                    Files.isSameFile(back, root));
        } finally {
            Files.deleteIfExists(back);
            Files.deleteIfExists(child);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 FollowLinksCycleDemo.java
java FollowLinksCycleDemo
~~~

Stdout đã kiểm chứng **trên Linux cho phép tạo symlink**:

~~~text
nofollowSawLink=true
followDirs=2
loopEvents=1
sameTarget=true
~~~

Nếu môi trường **không cho tạo symbolic link**, ví dụ in:

~~~text
symlinkTest=SKIPPED
~~~

rồi dọn thư mục. **SKIPPED không phải PASS** cho việc phát hiện vòng lặp. Trong CI, hãy phân loại test bị thiếu quyền/hỗ trợ hoặc đảm bảo runner có khả năng tạo symlink trước khi yêu cầu test pass.

Giải thích:

1. `Files.createTempDirectory` tạo root duy nhất; `Files.createDirectory` tạo child bên trong.
2. `Files.createSymbolicLink(back, root)` tạo entry `child/back` trỏ về root. API tạo link là **optional operation** và quyền tạo link phụ thuộc filesystem/OS.
3. Lượt không follow coi `back` là symbolic-link entry và `visitFile` nhận thuộc tính có `isSymbolicLink()==true`.
4. Lượt follow vào hai directory `root` và `child`. Khi sắp đi vào `back` dẫn tới root đang là tổ tiên, visitor nhận một `FileSystemLoopException`, tăng `loops`.
5. Vì nhánh lỗi cycle trả `CONTINUE`, bộ duyệt **không đi vào vòng lặp**, nhưng có thể tiếp tục những entry khác.
6. `Files.isSameFile(back, root)` trả `true` khi cùng trỏ tới một thư mục thực, dù đường dẫn khác nhau.
7. Với lỗi I/O khác cycle, visitor **ném lại lỗi** thay vì bỏ qua và khiến kết quả có thể thiếu dữ liệu.
8. `Files.deleteIfExists(back)` xóa **entry liên kết**, không có ý định duyệt theo link để xóa nội dung root; cleanup diễn ra từ dưới lên.

**Lưu ý khi làm sản phẩm:** Khối `catch(IOException | UnsupportedOperationException | SecurityException)` trong ví dụ dùng để cho phép chạy ở OS thiếu hỗ trợ/đặc quyền và báo `SKIPPED`. Trong CI nghiêm ngặt, nên phân loại lý do thật, không gộp mọi lỗi I/O thành “thiếu quyền”; lỗi như ổ đĩa hỏng hoặc thiếu dung lượng cần được báo riêng.

## 6. `FileSystemLoopException` được truyền ở đâu?

Một nhầm lẫn thường gặp là chờ xử lý vòng lặp trong `preVisitDirectory` hoặc bắt ở lời gọi `walkFileTree` ngoài cùng. **Khi dùng visitor**, API quy định lúc phát hiện cycle sẽ gọi:

~~~java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    if (exc instanceof FileSystemLoopException) {
        // Ghi nhận link quay về tổ tiên.
        return FileVisitResult.CONTINUE;
    }
    throw exc;
}
~~~

Đây là **đoạn trong class kế thừa `SimpleFileVisitor<Path>`**, không phải class chạy độc lập.

Vì sao không đặt vòng lặp trong `preVisitDirectory`?

- `preVisitDirectory` chỉ được gọi khi bộ duyệt đã xác định có thể đi vào directory theo quy tắc traversal.
- Một entry phát hiện cycle được coi là lỗi trước khi đi sâu và chuyển vào `visitFileFailed`.
- Không cần tự gọi `Files.isSameFile` cho mọi tổ tiên chỉ để thay lại cơ chế mà `walkFileTree(FOLLOW_LINKS)` đã có.

Với một ứng dụng cần **dừng toàn bộ tiến trình** khi phát hiện cycle, có thể ném lại exception hoặc trả `TERMINATE` theo thiết kế. Nếu chỉ muốn thống kê và bỏ qua link lỗi để xử lý entry khác, `CONTINUE` là lựa chọn thích hợp.

**Tuyệt đối tránh:**

~~~java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) {
    return FileVisitResult.CONTINUE;
}
~~~

Đây là đoạn minh họa **không phù hợp cho nhiều bài toán sản phẩm**: nó bỏ qua **mọi lỗi** kể cả permission denied, I/O failure hoặc không thể đọc directory. Một kết quả “quét xong” có thể thực chất đã bỏ sót nhiều tệp. Hãy quyết định lỗi nào được phép tiếp tục và phải báo cáo rõ tình trạng thiếu dữ liệu.

Nguồn: [Java SE 26 — FileSystemLoopException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileSystemLoopException.html) và [Java SE 26 — SimpleFileVisitor](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/SimpleFileVisitor.html).

## 7. Ví dụ 3 — Kiểm thử chính sách visitor không cần quyền tạo symlink

Trong môi trường không cho tạo symlink, vẫn có thể **kiểm thử riêng nhánh xử lý lỗi**, nhưng đó không thay thế thử nghiệm end-to-end phát hiện cycle trên filesystem thật.

Chương trình bên dưới **tự đưa một exception giả lập vào callback** để xác nhận:

- Với `FileSystemLoopException`, policy ghi nhận và trả `CONTINUE`.
- Với `AccessDeniedException`, policy **ném lại** thay vì nuốt lỗi.

Tạo file `VisitorErrorPolicyDemo.java`:

~~~java
import java.io.IOException;
import java.nio.file.*;
import java.util.concurrent.atomic.AtomicInteger;

public class VisitorErrorPolicyDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger count = new AtomicInteger();

        SimpleFileVisitor<Path> visitor =
                new SimpleFileVisitor<>() {
            @Override
            public FileVisitResult visitFileFailed(
                    Path p, IOException e) throws IOException {
                if (e instanceof FileSystemLoopException) {
                    count.incrementAndGet();
                    return FileVisitResult.CONTINUE;
                }
                throw e;
            }
        };

        FileVisitResult action = visitor.visitFileFailed(
                Path.of("back"),
                new FileSystemLoopException("back"));

        boolean otherWasPropagated = false;
        try {
            visitor.visitFileFailed(
                    Path.of("private"),
                    new AccessDeniedException("private"));
        } catch (AccessDeniedException e) {
            otherWasPropagated = true;
        }

        System.out.println("simulatedLoopAction=" + action);
        System.out.println("simulatedLoopEvents=" + count.get());
        System.out.println("otherErrorPropagated=" +
                otherWasPropagated);
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 VisitorErrorPolicyDemo.java
java VisitorErrorPolicyDemo
~~~

Stdout trên JDK kiểm thử:

~~~text
simulatedLoopAction=CONTINUE
simulatedLoopEvents=1
otherErrorPropagated=true
~~~

**Giới hạn quan trọng:** `new FileSystemLoopException("back")` trong ví dụ **chỉ mô phỏng lỗi được truyền vào visitor**. Nó không tạo chu trình trong hệ thống tệp và không chứng minh walker thực sự phát hiện cycle. Muốn kiểm thử cả cơ chế của Java NIO với filesystem, chạy ví dụ `FollowLinksCycleDemo` trên nơi cho phép tạo symlink.

## 8. `Files.walk` và lỗi được bọc trong `UncheckedIOException`

Từ Java 8, có thể duyệt bằng Stream API:

~~~java
try (Stream<Path> paths =
             Files.walk(root, FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(path -> process(path));
}
~~~

Đây là đoạn trong phương thức có `root` và `process(Path)` đã định nghĩa, cùng import `Files`, `Path`, `FileVisitOption` và `Stream`.

`Files.walk` có thể đưa ra một Stream lazy; một số lỗi I/O, gồm lỗi cycle khi follow symlink, xuất hiện **trong lúc tiêu thụ Stream**, không nhất thiết ngay tại lời gọi tạo Stream. Đối với lỗi I/O phát sinh trong khi đi tiếp, API đưa ra `UncheckedIOException` chứa nguyên nhân `IOException`.

### 8.1. Ví dụ 4 — Stream gặp vòng lặp

Tạo `WalkStreamCycleDemo.java`:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.*;
import java.util.stream.Stream;

public class WalkStreamCycleDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("stream-cycle-");
        Path child = Files.createDirectory(root.resolve("child"));
        Path back = child.resolve("back");

        try {
            try {
                Files.createSymbolicLink(back, root);
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException e) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            boolean detected = false;
            try (Stream<Path> paths =
                         Files.walk(
                                 root, FileVisitOption.FOLLOW_LINKS)) {
                paths.forEach(path -> { });
            } catch (UncheckedIOException e) {
                detected =
                        e.getCause() instanceof FileSystemLoopException;
            }

            System.out.println("streamLoopDetected=" + detected);
        } finally {
            Files.deleteIfExists(back);
            Files.deleteIfExists(child);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 WalkStreamCycleDemo.java
java WalkStreamCycleDemo
~~~

Stdout trên Linux có hỗ trợ symlink:

~~~text
streamLoopDetected=true
~~~

Nếu không thể tạo symlink:

~~~text
symlinkTest=SKIPPED
~~~

**So sánh hai kiểu API:**

| API | Cách nhận lỗi cycle | Quản lý tài nguyên |
| --- | --- | --- |
| `Files.walkFileTree(... FOLLOW_LINKS ..., visitor)` | `visitFileFailed(path, FileSystemLoopException)` | Walker đóng các directory mà nó mở |
| `Files.walk(root, FOLLOW_LINKS)` | Có thể thấy `UncheckedIOException` khi duyệt Stream; `getCause()` là `FileSystemLoopException` | Đóng Stream trong try-with-resources |
| `Files.find(root, depth, matcher, FOLLOW_LINKS)` | Cơ chế lỗi Stream tương tự khi duyệt | Đóng Stream trong try-with-resources |

Khi cần kiểm soát tiếp tục sau một lỗi cụ thể theo từng đường dẫn, **visitor** thường rõ hơn. Với pipeline dữ liệu mà lỗi phải khiến tác vụ thất bại, `Files.walk` thuận tiện nhưng phải chuẩn bị xử lý lỗi phát sinh lúc tiêu thụ Stream.

**Đừng viết:**

~~~java
Stream<Path> stream =
        Files.walk(root, FileVisitOption.FOLLOW_LINKS);
// Không close, cũng không xử lý lỗi có thể xảy ra khi iterate.
~~~

Đây là đoạn minh họa **thiếu quản lý tài nguyên**. Stream chứa resource filesystem, phải close. Tránh chỉ bắt `IOException` bao quanh lúc tạo Stream rồi bỏ qua `UncheckedIOException` trong terminal operation.

## 9. Hiểu đúng `maxDepth` và thời điểm vòng lặp được báo

`walkFileTree(start, options, maxDepth, visitor)` giới hạn số cấp thư mục được đi vào:

- Gốc `start` ở độ sâu **0**.
- Entry trực tiếp dưới root ở độ sâu **1**.
- Entry nằm trong một thư mục con ở độ sâu **2**, v.v.
- Khi ở đúng `maxDepth`, một directory có thể được chuyển cho `visitFile` thay vì được mở và đi sâu. Vì không đi vào, nó có thể **chưa làm phát sinh cycle**.

Với:

~~~text
root/          depth 0
└── child/     depth 1
    └── back   depth 2 (symlink -> root)
~~~

một giới hạn dừng ở entry `back` chưa chắc đã kích hoạt cơ chế phát hiện loop. Chỉ khi bộ duyệt thật sự định **đi vào** target ở độ sâu cho phép thì cycle mới trở thành vấn đề cần báo.

### 9.1. Ví dụ 5 — `maxDepth=1/2/3` trên cùng cycle

Tạo `MaxDepthCycleDemo.java`:

~~~java
import java.io.IOException;
import java.nio.file.*;
import java.util.EnumSet;
import java.util.concurrent.atomic.AtomicInteger;

public class MaxDepthCycleDemo {
    static int loops(Path root, int depth) throws IOException {
        AtomicInteger events = new AtomicInteger();

        Files.walkFileTree(
                root,
                EnumSet.of(FileVisitOption.FOLLOW_LINKS),
                depth,
                new SimpleFileVisitor<>() {
                    @Override
                    public FileVisitResult visitFileFailed(
                            Path p, IOException e) throws IOException {
                        if (e instanceof FileSystemLoopException) {
                            events.incrementAndGet();
                            return FileVisitResult.CONTINUE;
                        }
                        throw e;
                    }
                });
        return events.get();
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("depth-cycle-");
        Path nested = Files.createDirectory(root.resolve("nested"));
        Path back = nested.resolve("back");

        try {
            try {
                Files.createSymbolicLink(back, root);
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException e) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            System.out.println("depth1Loops=" + loops(root, 1));
            System.out.println("depth2Loops=" + loops(root, 2));
            System.out.println("depth3Loops=" + loops(root, 3));
        } finally {
            Files.deleteIfExists(back);
            Files.deleteIfExists(nested);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MaxDepthCycleDemo.java
java MaxDepthCycleDemo
~~~

Stdout đã kiểm chứng với filesystem Linux trong bài:

~~~text
depth1Loops=0
depth2Loops=0
depth3Loops=1
~~~

Khi không tạo được symlink: `symlinkTest=SKIPPED`.

Giải thích:

1. Ở depth 1, bộ duyệt mới tới `nested` như boundary, chưa tiến vào `back`.
2. Ở depth 2, `back` ở boundary, có thể được trao cho `visitFile` chứ không đi vào target; vòng lặp chưa được báo.
3. Ở depth 3, bộ duyệt có thể tiến tới target của `back`, phát hiện nó trùng thư mục tổ tiên `root` và báo một loop.
4. Kết quả minh họa các ranh giới trên filesystem được kiểm thử, không phải quy tắc “mọi cycle luôn xuất hiện tại depth 3”. Với cấu trúc thư mục sâu hơn, vị trí phát hiện có thể khác.

**Tác dụng của maxDepth:** Hữu ích để tránh quét quá sâu hoặc vượt ngân sách, **nhưng không tự giải quyết** giới hạn security domain. Một symlink ở mức nông có thể trỏ tới nơi hoàn toàn khác mà không tạo vòng lặp.

Nguồn: [Files.walkFileTree — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html) — mô tả `maxDepth` và cơ chế callback ở độ sâu giới hạn.

## 10. Thư mục từng thăm không nhất thiết là vòng lặp

Cấu trúc:

~~~text
root/
├── shared/
├── a -> shared/
└── b -> shared/
~~~

Khi bật `FOLLOW_LINKS`, bộ duyệt có thể tới **cùng thư mục `shared` ba lần**: qua đường dẫn thật và qua hai alias. Nếu `shared` không phải **tổ tiên của a/b** trên stack hiện tại, Java không coi đó là loop.

Đây là điểm quan trọng khi xây công cụ index/search:

- **Cycle detection** phải ngăn lặp vô hạn do gặp lại **tổ tiên**.
- **Deduplication** là việc khác: tránh xử lý **cùng một thư mục/file** nhiều lần khi có các đường dẫn khác nhau.
- Không nên áp dụng một global `visited` set rồi gọi mọi lần tái xuất hiện là “cycle”. Điều đó có thể chặn những nhánh hợp lệ, dù đôi khi là chính sách dedup mà ứng dụng muốn.
- Nếu cần dedup toàn cục, phải định nghĩa identity/ownership/path semantics, file keys/provider, permission và những thay đổi đồng thời.

### 10.1. Ví dụ 6 — Hai alias không tạo cycle

Tạo `RepeatedAliasDemo.java`:

~~~java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;
import java.util.concurrent.atomic.AtomicInteger;

public class RepeatedAliasDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("alias-demo-");
        Path target = Files.createDirectory(
                root.resolve("shared"));
        Path a = root.resolve("a");
        Path b = root.resolve("b");

        try {
            try {
                Files.createSymbolicLink(a, target);
                Files.createSymbolicLink(b, target);
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException e) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            AtomicInteger visits = new AtomicInteger();
            AtomicInteger loops = new AtomicInteger();

            Files.walkFileTree(
                    root,
                    EnumSet.of(FileVisitOption.FOLLOW_LINKS),
                    Integer.MAX_VALUE,
                    new SimpleFileVisitor<>() {
                        @Override
                        public FileVisitResult preVisitDirectory(
                                Path dir, BasicFileAttributes attrs)
                                throws IOException {
                            if (Files.isSameFile(dir, target)) {
                                visits.incrementAndGet();
                            }
                            return FileVisitResult.CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFileFailed(
                                Path dir, IOException e)
                                throws IOException {
                            if (e instanceof FileSystemLoopException) {
                                loops.incrementAndGet();
                                return FileVisitResult.CONTINUE;
                            }
                            throw e;
                        }
                    });

            System.out.println("visitsToSameDirectory=" +
                    visits.get());
            System.out.println("loopEvents=" + loops.get());
        } finally {
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(target);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 RepeatedAliasDemo.java
java RepeatedAliasDemo
~~~

Stdout trên filesystem Linux được kiểm thử:

~~~text
visitsToSameDirectory=3
loopEvents=0
~~~

Nếu không tạo được symlink: `symlinkTest=SKIPPED`.

Lý do:

1. `Files.isSameFile(dir, target)` trả true khi dir thực sự là thư mục `shared`, dù đến qua alias.
2. Có ba đường dẫn đến cùng một directory: `shared`, `a` và `b`. Mỗi nhánh kết thúc bình thường.
3. Không có alias nào trỏ ngược về một ancestor trên **chính nhánh ấy**, nên `loops=0`.
4. Tránh nhầm “visited 3 times” với “bị loop”. Nếu nghiệp vụ không muốn quét trùng, thêm **chính sách dedup riêng**; cycle detection built-in không hứa chỉ duyệt mỗi identity đúng một lần.

## 11. So sánh identity: `Path.equals`, `normalize`, `toRealPath` và `isSameFile`

Bạn có thể gặp các đường dẫn:

~~~text
root/note.txt
root/sub/../note.txt
~~~

Cả hai có thể dẫn tới **cùng file** khi `sub` tồn tại. Nhưng đối tượng `Path` có các thành phần khác nhau; `equals` trên Path không tự truy cập filesystem để suy ra file identity.

### 11.1. Bảng so sánh

| API | Bản chất | Dùng khi nào |
| --- | --- | --- |
| `Path.equals(other)` | So sánh path theo biểu diễn và provider | Kiểm tra hai Path trực tiếp có bằng nhau theo API |
| `path.normalize()` | Loại các thành phần `.`/`..` mang tính từ vựng; không nhất thiết truy cập filesystem | Rút gọn biểu diễn, **không** bảo đảm an toàn symlink hoặc identity |
| `path.toRealPath()` | Giải quyết đường dẫn thực trên filesystem theo options; mặc định theo symlink | Khi cần canonical path tại một thời điểm, có thể ném IOException |
| `Files.isSameFile(a,b)` | Kiểm tra hai Path có định vị **cùng một file/directory** hay không | Kiểm tra identity theo filesystem, có thể ném IOException |
| `BasicFileAttributes.fileKey()` | Opaque key định danh file nếu provider cung cấp; **có thể null** | Dùng làm thành phần thuật toán trong phạm vi điều kiện provider cho phép |

Không dùng `path.toAbsolutePath().toString()` hoặc `normalize()` làm cơ chế cycle detection chính thức. Một symbolic link có thể tạo ra hai path trông khác nhau nhưng dẫn về cùng đối tượng; ngược lại các biểu diễn `..` có thể chịu tác động của symlink khi thực sự giải quyết tên.

### 11.2. Ví dụ 7 — Hai Path khác biểu diễn nhưng cùng file

Không cần quyền tạo symlink; test hoạt động với các thành phần `..` hợp lệ:

Tạo `IdentityVsPathDemo.java`:

~~~java
import java.nio.file.*;

public class IdentityVsPathDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("identity-");
        Path sub = Files.createDirectory(root.resolve("sub"));
        Path real = root.resolve("note.txt");
        Path alias = sub.resolve("..").resolve("note.txt");

        try {
            Files.createFile(real);

            System.out.println("lexicallyEqual=" +
                    real.equals(alias));
            System.out.println("normalizedEqual=" +
                    real.normalize().equals(alias.normalize()));
            System.out.println("sameFile=" +
                    Files.isSameFile(real, alias));
            System.out.println("realPathsEqual=" +
                    real.toRealPath().equals(alias.toRealPath()));
        } finally {
            Files.deleteIfExists(real);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 IdentityVsPathDemo.java
java IdentityVsPathDemo
~~~

Stdout trên filesystem kiểm thử:

~~~text
lexicallyEqual=false
normalizedEqual=true
sameFile=true
realPathsEqual=true
~~~

Kết quả cho thấy: **khác biểu diễn path không đồng nghĩa khác identity**. Tuy nhiên, không nên suy ra `normalize()` luôn xác định identity trong trường hợp symlink; `normalize` chỉ xử lý thành phần đường dẫn trên bình diện từ vựng.

**Cảnh báo file key:** Đừng lưu `fileKey()` vào cơ sở dữ liệu và giả định nó là UUID toàn cầu, tồn tại vĩnh viễn hoặc luôn có giá trị. Javadoc mô tả nó là đối tượng **opaque** và có thể `null`; tính ổn định/giới hạn phụ thuộc filesystem. Để kiểm tra cycle khi dùng `walkFileTree(FOLLOW_LINKS)`, ưu tiên cơ chế built-in đã thực hiện xử lý key và fallback `isSameFile` cho bạn.

Nguồn: [BasicFileAttributes.fileKey — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html#fileKey()), [Files.isSameFile](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#isSameFile(java.nio.file.Path,java.nio.file.Path)) và [Path.normalize/toRealPath](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html).

## 12. Phân biệt vòng lặp với liên kết trỏ ra ngoài thư mục gốc

Một link có thể làm chương trình quét **ngoài phạm vi mong muốn** nhưng không tạo loop:

~~~text
root/
└── external -> /outside/

outside/
└── marker.txt
~~~

Nếu bật `FOLLOW_LINKS`, `walkFileTree(root,...)` có thể đi đến `/outside/marker.txt` thông qua đường dẫn link `root/external/marker.txt`. Vì `outside` không phải ancestor của `root/external`, bộ duyệt **không báo `FileSystemLoopException`**.

Điều này ảnh hưởng trực tiếp đến ứng dụng backup, antivirus, import dữ liệu hoặc tìm kiếm trên thư mục do người dùng cung cấp. **Cycle detection không phải sandbox đường dẫn**.

### 12.1. Ví dụ 8 — Link ra ngoài root nhưng không có vòng lặp

Tạo file `OutsideRootDemo.java`:

~~~java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;
import java.util.concurrent.atomic.AtomicInteger;

public class OutsideRootDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("inside-");
        Path outside = Files.createTempDirectory("outside-");
        Path alias = root.resolve("external");
        Path marker = outside.resolve("marker.txt");

        try {
            Files.createFile(marker);

            try {
                Files.createSymbolicLink(alias, outside);
            } catch (IOException
                     | UnsupportedOperationException
                     | SecurityException e) {
                System.out.println("symlinkTest=SKIPPED");
                return;
            }

            AtomicInteger outsideVisits = new AtomicInteger();
            AtomicInteger loops = new AtomicInteger();

            Files.walkFileTree(
                    root,
                    EnumSet.of(FileVisitOption.FOLLOW_LINKS),
                    Integer.MAX_VALUE,
                    new SimpleFileVisitor<>() {
                        @Override
                        public FileVisitResult visitFile(
                                Path p, BasicFileAttributes attrs) {
                            if (p.getFileName().toString()
                                    .equals("marker.txt")) {
                                outsideVisits.incrementAndGet();
                            }
                            return FileVisitResult.CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFileFailed(
                                Path p, IOException e) throws IOException {
                            if (e instanceof FileSystemLoopException) {
                                loops.incrementAndGet();
                                return FileVisitResult.CONTINUE;
                            }
                            throw e;
                        }
                    });

            System.out.println("visitedOutsideRoot=" +
                    (outsideVisits.get() == 1));
            System.out.println("cycleEvents=" + loops.get());
        } finally {
            Files.deleteIfExists(alias);
            Files.deleteIfExists(marker);
            Files.deleteIfExists(outside);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 OutsideRootDemo.java
java OutsideRootDemo
~~~

Stdout trên Linux có quyền tạo link:

~~~text
visitedOutsideRoot=true
cycleEvents=0
~~~

Khi không thể tạo symlink: `symlinkTest=SKIPPED`.

**Điều rút ra:**

- Dù root ban đầu chỉ là một thư mục tạm, follow link vẫn có thể truy cập entry nằm bên ngoài khu vực root thực.
- Không có `FileSystemLoopException` vì symlink không dẫn tới tổ tiên.
- Nếu ứng dụng chỉ được phép xử lý các file **thực sự nằm trong root**, chính sách an toàn thường đơn giản hơn khi **không bật FOLLOW_LINKS**.
- Nếu bắt buộc follow link, phải có **quy tắc bảo vệ root** thích hợp, kiểm tra target/canonical paths, quyền và race theo threat model. Chỉ dùng `String.startsWith(root.toString())` để kiểm tra path là nguy hiểm: chuỗi prefix và identity filesystem không tương đương.
- Kiểm tra `toRealPath()` tại một thời điểm cũng **không tự loại bỏ race** khi một process không tin cậy có thể đổi symlink giữa lúc kiểm tra và mở file. Với ứng dụng bảo mật cao, cần các primitive/permission và cơ chế mở file an toàn ở mức filesystem.

Đây là phần về **tránh traversal ngoài root**, không phải bài toán phát hiện cycle thuần túy, nhưng phải phân biệt để dùng `FOLLOW_LINKS` đúng trong sản phẩm.

## 13. Cách triển khai chính sách an toàn cho công cụ duyệt cây

### 13.1. Chính sách A: không follow links — đơn giản nhất

Nếu mục tiêu là “quét các file nằm thực sự dưới root, không đi theo symlink”:

~~~java
Files.walkFileTree(root, new SimpleFileVisitor<>() {
    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        if (attrs.isSymbolicLink()) {
            // Ghi nhận entry link nhưng không mở target.
            return FileVisitResult.CONTINUE;
        }

        if (attrs.isRegularFile()) {
            // Xử lý file thông thường theo chính sách ứng dụng.
        }
        return FileVisitResult.CONTINUE;
    }
});
~~~

Đây là đoạn minh họa trong phương thức với `root` và import NIO/attributes. `walkFileTree` mặc định không follow links nên không cần thêm một lệnh đặc biệt để cắt symlink ở mức traversal.

### 13.2. Chính sách B: follow nhưng xử lý cycle riêng

Nếu ứng dụng cần đi vào target symlink, ví dụ công cụ tìm kiếm **có chủ đích** duyệt các thư mục liên kết:

~~~java
Files.walkFileTree(
        root,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        maxDepth,
        new SimpleFileVisitor<>() {
            @Override
            public FileVisitResult visitFileFailed(
                    Path file, IOException exc)
                    throws IOException {
                if (exc instanceof FileSystemLoopException) {
                    // Log/đếm cycle rồi bỏ qua entry gây vòng lặp.
                    return FileVisitResult.CONTINUE;
                }
                throw exc;
            }
        });
~~~

Đây là đoạn trong một phương thức với `root` và `maxDepth` đã khai báo. **Không tự thay mọi lỗi thành CONTINUE**. Với một tác vụ không cho phép kết quả thiếu dữ liệu, có thể dừng/hủy toàn bộ khi phát hiện cycle thay vì bỏ qua.

### 13.3. Chính sách C: nhiều liên kết hợp lệ nhưng không muốn quét trùng

Với backup/indexer, bạn có thể muốn duyệt mỗi directory **identity** một lần trên toàn công việc. Đây là **deduplication**, cần thiết kế riêng:

- Xác định identity bằng cơ chế filesystem phù hợp, cân nhắc `fileKey` có thể `null` và fallback `isSameFile`.
- Phải phân biệt **visited globally** với **ancestors in active traversal**.
- Quyết định có giữ nhiều đường dẫn alias hay chỉ một canonical path trong output.
- Nếu dùng map/set để lưu key, bảo đảm phạm vi và độ ổn định của key trong phiên duyệt; tránh giả định file key là bất biến vĩnh viễn.
- Nếu filesystem thay đổi đồng thời, một list visited hoặc một lần `Files.isSameFile` không tự tạo snapshot nhất quán.

Trong đa số ứng dụng, **dùng built-in cycle detection của Files.walkFileTree(FOLLOW_LINKS)** trước khi cân nhắc tự xây DFS trên filesystem. Tự triển khai phát hiện chu trình bằng so sánh chuỗi đường dẫn dễ sai với symlink và các filesystem provider.

## 14. Khi nào cần `Files.isSymbolicLink` và `NOFOLLOW_LINKS`?

Một số API bổ trợ:

~~~java
boolean isLink = Files.isSymbolicLink(path);

BasicFileAttributes attrs = Files.readAttributes(
        path,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
~~~

Đây là đoạn trong phương thức với `path` kiểu `Path` và các import phù hợp.

- `Files.isSymbolicLink(path)` hỏi entry được biểu diễn bởi path có phải symlink không.
- `Files.readAttributes(..., NOFOLLOW_LINKS)` đọc thông tin của **entry link**, thay vì mặc định theo link tới đích.
- `attrs.isSymbolicLink()` và `attrs.isDirectory()` có nghĩa theo cách đọc attributes đã chọn.
- `Files.isDirectory(path)` khi không có `NOFOLLOW_LINKS` thường có thể theo symlink tới directory target, trong khi `Files.isDirectory(path, NOFOLLOW_LINKS)` không coi chính link ấy là directory target.
- Các phép kiểm tra thuộc tính có thể thất bại hoặc trả kết quả không xác định khi filesystem thay đổi; không coi chúng là thao tác bảo vệ atomic với lời gọi mở sau đó.

**Symlink hỏng:** Một link tồn tại nhưng đích không tồn tại (dangling/broken symlink). Với `FOLLOW_LINKS`, Javadoc cho phép bộ duyệt **thử đọc attributes của link** nếu đọc target thất bại; nếu đọc được attributes của link, `visitFile` có thể được gọi với attrs của link, thay vì luôn `visitFileFailed`. **Không mặc định mọi link hỏng đều tạo FileSystemLoopException**. Đó là trường hợp lỗi/entry khác với cycle về tổ tiên.

Nguồn: [Files.readAttributes — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html), [LinkOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/LinkOption.html).

## 15. Những lỗi liên quan cần xử lý ngoài vòng lặp

| Tình huống | Có phải cycle không? | Cách xử lý |
| --- | --- | --- |
| Symlink trỏ về root/tổ tiên và follow được bật | **Có** | `visitFileFailed` nhận `FileSystemLoopException` |
| Symlink trỏ tới một sibling directory | Không nhất thiết | Có thể duyệt trùng, cần dedup riêng nếu muốn |
| Symlink trỏ ra ngoài root | Không nhất thiết | Chính sách phạm vi/permission/sandbox |
| Symlink đứt đích | **Không tự động** | Có thể `visitFile` cho attrs link hoặc `visitFileFailed` nếu attributes không đọc được |
| Không có quyền vào directory | Không | IOException/AccessDeniedException; không nuốt |
| Filesystem bị thay đổi khi đang duyệt | Không tự động | Có thể lỗi hoặc dữ liệu không nhất quán, cần chính sách retry/abort |
| Đặt maxDepth quá thấp | Không | Không kiểm tra những nhánh chưa đi vào; không suy ra cây không có cycle |
| `Path.equals` false với hai alias | Không đủ kết luận | Cần identity-based test |
| `fileKey()==null` | Không phải lỗi cycle | Java có thể fallback isSameFile trong thuật toán |
| Hard link tới cùng file dữ liệu | Không phải symlink cycle thư mục theo mặc định | Xử lý duplicate file identity riêng |
| Lỗi lúc tiêu thụ `Files.walk` Stream | Có thể do cycle hoặc I/O khác | Kiểm tra cause của `UncheckedIOException` |
| Có hai alias cùng trỏ một target không phải tổ tiên | Không phải cycle | Có thể được duyệt nhiều lần |

**Tại sao phân loại quan trọng?** Một công cụ sao lưu không nên âm thầm bỏ qua một thư mục không thể đọc và báo đã sao lưu đủ. Một công cụ tìm kiếm mang tính best-effort có thể được phép skip cycle, nhưng phải báo số entry bị bỏ qua hoặc trạng thái partial results cho caller.

## 16. Giới hạn chi phí, độ sâu và bảo vệ đầu vào

Ngay cả khi thuật toán chặn được cycle, một cây vẫn có thể rất lớn. Khi duyệt filesystem bên ngoài kiểm soát của ứng dụng, đặt giới hạn theo yêu cầu thực:

1. **Giới hạn `maxDepth`** nếu không cần quét vô hạn cấp. Độ sâu không phải ranh giới bảo mật.
2. **Giới hạn thời gian và số entry** ở tầng điều phối; Java NIO không tự áp đặt ngân sách tài nguyên cho yêu cầu nghiệp vụ của bạn.
3. **Giới hạn quyền truy cập** của process và xác định root được phép; không dùng việc không phát hiện cycle làm bằng chứng an toàn.
4. **Không follow symlink** nếu sản phẩm không yêu cầu.
5. **Đóng Files.walk/find Stream** bằng try-with-resources; không giữ directory handles lâu hơn cần thiết.
6. **Phân biệt hoàn thành thành công và kết quả từng phần** do lỗi I/O.
7. **Không giả định thứ tự duyệt ổn định** trên mọi filesystem/OS; sort khi cần báo cáo quyết định nhưng cân nhắc bộ nhớ.
8. **Tránh TOCTOU** khi môi trường có process không tin cậy sửa directory hoặc symlink.
9. **Không tự duyệt lại một subtree** chỉ vì tên alias khác; khi cần dedup, định nghĩa theo identity.
10. **Sử dụng thống kê riêng** cho symlinks, cycles, skipped errors, processed entries để debug và QA.

## 17. Tổ chức kiểm thử trên Windows, Linux và macOS

Một test suite nghiêm túc cần có hai tầng:

**Tầng 1: luôn chạy được trên filesystem cơ bản**

- Test `walkFileTree` với file/dir thật không cần symlink.
- Test code policy `visitFileFailed` bằng exception giả lập (đã nêu rõ không kiểm chứng cycle filesystem).
- Test so sánh path representation, `normalize`, `isSameFile` cho các alias `..` đơn giản.
- Test các loại lỗi I/O và permission trong môi trường được kiểm soát.

**Tầng 2: cần quyền tạo symbolic link thật**

- Tạo `root/child/back -> root` và đếm event `FileSystemLoopException` khi `FOLLOW_LINKS`.
- Xác nhận **không** follow links ở overload mặc định, và symlink được nhận diện trong `visitFile`.
- Kiểm tra `Files.walk(FOLLOW_LINKS)` báo `UncheckedIOException` với cause phù hợp.
- Kiểm thử `maxDepth` và ranh giới khi entry link ở boundary.
- Kiểm tra hai alias trỏ cùng sibling target **không** bị đánh thành cycle.
- Kiểm tra symlink trỏ ra ngoài root **không tự động** gây cycle.
- Test dangling link theo filesystem/provider khi sản phẩm có yêu cầu.

| Nền tảng | Điều cần xác minh |
| --- | --- |
| Linux | Quyền tạo link, behavior của filesystem đang dùng, traversal và cleanup |
| macOS | Cùng bộ test trên filesystem cụ thể; không suy luận từ Linux |
| Windows | Quyền tạo symlink/Developer Mode/policy và provider; nếu thiếu quyền thì test thực phải **SKIPPED**, không coi PASS |
| CI container | Quyền mount/filesystem hỗ trợ link; đừng mặc định giống host |
| Network filesystem | fileKey có thể khác/null, lỗi I/O và timing có thể khác local disk |
| ZIP filesystem/provider khác | Khả năng hỗ trợ symlink có thể hạn chế, cần kiểm tra contract của provider |

**Cách báo cáo trung thực:** ghi OS, JDK, filesystem, link creation supported? test actual-cycle PASS/FAIL/SKIPPED, số loop events và exception khác. Nếu có SKIPPED, tính năng không được coi đã kiểm chứng trên nền tảng đó; có thể bố trí runner được cấp quyền phù hợp.

### 17.1. Vì sao không nên hardcode đường dẫn thực trong expected stdout?

- `Files.createTempDirectory` sinh tên ngẫu nhiên và có root path khác giữa OS.
- `FileSystemLoopException.getMessage()` có thể chứa path và thông tin của provider.
- Thứ tự entry của directory không được đảm bảo.
- Symlink có thể không được phép tạo trên Windows hoặc không được hỗ trợ trên provider.

Các ví dụ dùng boolean hoặc **số lượng sự kiện** để tạo stdout ổn định trên môi trường thực sự hỗ trợ link. Với test portable, tránh dùng chuỗi đường dẫn tuyệt đối hoặc nguyên văn message của JVM làm assertion.

## 18. Sai lầm phổ biến

| Sai lầm | Điều đúng |
| --- | --- |
| “Cây tệp luôn là tree, không bao giờ có chu trình.” | Khi follow symlink, cấu trúc duyệt có thể là graph có cycle. |
| “`Path.equals()` true/false đủ để biết hai path là cùng file.” | Cần identity theo filesystem; `Files.isSameFile` khi thích hợp. |
| “`normalize()` là cách phát hiện mọi vòng lặp.” | Nó xử lý cú pháp `.`/`..`, không giải quyết symlink identity. |
| “`walkFileTree(root, visitor)` sẽ follow symlink theo mặc định.” | **Không**. Cần bật `FOLLOW_LINKS`. |
| “Không follow link là không thấy entry symlink.” | Entry có thể được thăm như một file trong `visitFile`. |
| “Cycle phát sinh do tên đường dẫn trùng nhau.” | Phải xét cùng **thư mục thực** trên nhánh tổ tiên. |
| “Bật `FOLLOW_LINKS` sẽ quét vòng lặp mãi.” | API built-in có cơ chế phát hiện và báo `FileSystemLoopException`. |
| “Vòng lặp luôn được báo qua `preVisitDirectory`.” | Với `walkFileTree`, báo qua `visitFileFailed`. |
| “Chỉ cần catch IOException ngoài lời gọi walker là đủ để skip riêng cycle.” | Visitor quyết định lỗi/cách tiếp tục. |
| “Bắt mọi IOException trong visitor rồi CONTINUE luôn an toàn.” | Có thể che permission errors và quét thiếu dữ liệu. |
| “Mọi lần gặp lại thư mục đã từng thăm đều là cycle.” | Chỉ quay về **tổ tiên của nhánh hiện tại** mới là cycle; alias khác có thể chỉ gây duplicate. |
| “File key luôn có và là id toàn cầu bất biến.” | `fileKey()` opaque, có thể null và phụ thuộc provider. |
| “`Files.walk(FOLLOW_LINKS)` luôn throw checked IOException ngay khi tạo Stream.” | Lỗi có thể xảy ra **khi tiêu thụ** dưới dạng UncheckedIOException. |
| “Đặt maxDepth nhỏ chứng minh cây không có cycle.” | Có thể chưa đi đủ sâu để phát hiện. |
| “Không có cycle nghĩa là không rời root.” | Symlink có thể trỏ tới một directory bên ngoài root mà không tạo loop. |
| “`toRealPath` một lần đủ khóa đường dẫn chống thay đổi sau đó.” | Có thể có TOCTOU khi filesystem bị sửa đồng thời. |
| “Test không tạo được symlink tức là cycle test PASS.” | Đó là SKIPPED, cần runner đủ quyền/hỗ trợ để kiểm chứng. |
| “Dùng `FOLLOW_LINKS` mặc định cho tác vụ xóa thư mục.” | Rất nguy hiểm nếu link dẫn ra ngoài; cần chính sách tường minh. |
| “Hai symlink cùng target chắc chắn kích hoạt FileSystemLoopException.” | Nếu target không phải ancestor, có thể chỉ bị duyệt lặp. |
| “Broken symlink luôn được báo như cycle.” | Không, có quy tắc fallback thuộc tính link khi follow target thất bại. |

## 19. Checklist triển khai thực tế

1. Bài toán cần **theo symlink** không? Nếu không, giữ default no-follow.
2. Có hiểu cấu trúc symlink trỏ về **ancestor** tạo cycle như thế nào không?
3. Visitor có xử lý `FileSystemLoopException` riêng trong `visitFileFailed` không?
4. Những lỗi khác (AccessDenied, NoSuchFile, IO errors) có được **lan truyền hoặc báo cáo** đúng không?
5. Nếu `CONTINUE` sau một cycle, có đếm/log các event để biết kết quả đã skip gì không?
6. Có phân biệt duplicate via alias với cycle via ancestor không?
7. Có cần dedup toàn cục? Nếu có, identity và xử lý `fileKey==null` ra sao?
8. Có dựa nhầm vào `Path.equals` hoặc `normalize` làm file identity không?
9. Có giới hạn `maxDepth` theo nhu cầu mà không coi nó là sandbox không?
10. Có chặn symlink trỏ **ra ngoài allowed root** theo threat model không?
11. Có tránh theo symlink khi xóa, ghi hoặc thay đổi file không đáng tin cậy không?
12. Với `Files.walk/find` Stream, có đóng đúng tài nguyên và bắt UncheckedIOException tại terminal operation không?
13. Có test cùng một root không có symlink để kiểm tra traversal cơ bản không?
14. Có test tạo **cycle thật** ở filesystem cho phép symlink, không chỉ đưa exception giả lập cho visitor không?
15. Có test cùng target qua hai alias mà không đánh nhầm là loop không?
16. Có test link nằm ở ranh giới `maxDepth` không?
17. Có test broken link và quyền truy cập nếu sản phẩm cần xử lý không?
18. Có ghi rõ trong CI symlink test PASS/FAIL/SKIPPED, không quy đổi SKIPPED thành PASS không?
19. Có kiểm tra trên Windows/Linux/macOS dự kiến hỗ trợ, vì filesystem/provider có thể khác không?
20. Có thiết kế dọn test fixture mà không đi theo link và xóa nhầm nội dung bên ngoài không?

## 20. Câu hỏi tự kiểm tra

**1.** Một symlink trong `root/child` trỏ về `root` có thể gây gì khi follow?  
**Đáp án:** Một cycle trở về ancestor `root`.

**2.** `Files.walkFileTree(root, visitor)` có follow symlink theo mặc định không?  
**Đáp án:** Không.

**3.** Muốn follow symlink, bật option nào?  
**Đáp án:** `FileVisitOption.FOLLOW_LINKS`.

**4.** Khi `walkFileTree` thấy cycle, callback nào nhận lỗi?  
**Đáp án:** `visitFileFailed(Path, IOException)`, với một `FileSystemLoopException`.

**5.** Nếu muốn bỏ qua cycle nhưng không che lỗi khác, visitor nên làm gì?  
**Đáp án:** Kiểm tra `exc instanceof FileSystemLoopException`, trả `CONTINUE` cho cycle và ném lại exception khác.

**6.** Nếu không follow, entry symlink có biến mất khỏi mọi callback không?  
**Đáp án:** Không. Có thể được thăm như một entry qua `visitFile`, attrs.isSymbolicLink()==true.

**7.** Java xác định cycle bằng cách so sánh các chuỗi path đơn giản?  
**Đáp án:** Không. Dựa vào file-key hoặc so sánh identity `isSameFile` với tổ tiên.

**8.** Hai alias trỏ cùng thư mục không phải tổ tiên có nhất thiết báo cycle không?  
**Đáp án:** Không; có thể chỉ làm duyệt trùng dữ liệu.

**9.** `Path.normalize` có theo symlink để tìm directory thực không?  
**Đáp án:** Không; đó là thao tác từ vựng, không phải giải quyết identity filesystem.

**10.** `Files.isSameFile` có thể dùng để kiểm tra hai path dẫn tới cùng file không?  
**Đáp án:** Có, với xử lý I/O exceptions và nhận thức filesystem có thể thay đổi.

**11.** `BasicFileAttributes.fileKey()` luôn khác null không?  
**Đáp án:** Không. Key tùy provider, có thể null.

**12.** `Files.walk(root, FOLLOW_LINKS)` gặp vòng lặp có thể throw gì khi tiêu thụ Stream?  
**Đáp án:** `UncheckedIOException` chứa `FileSystemLoopException` làm cause.

**13.** Nếu `maxDepth=2` không báo cycle, có chứng minh cây không có cycle không?  
**Đáp án:** Không. Có thể bộ duyệt chưa được phép đi sâu vào target để gặp ancestor.

**14.** Liên kết trỏ đến thư mục **ngoài root** có nhất thiết tạo cycle không?  
**Đáp án:** Không. Có thể không loop nhưng vẫn vượt khỏi phạm vi nghiệp vụ.

**15.** Test không tạo được symlink trên Windows nên được báo thế nào?  
**Đáp án:** SKIPPED hoặc setup failure theo chính sách CI, không coi đã PASS chức năng phát hiện cycle.

**16.** `Files.createSymbolicLink` có được bảo đảm hỗ trợ trên mọi filesystem không?  
**Đáp án:** Không, đó là optional operation; quyền và provider có thể từ chối.

**17.** Vì sao không bắt mọi IOException trong visitor rồi tiếp tục?  
**Đáp án:** Có thể che lỗi permission/IO và tạo kết quả quét không đầy đủ.

**18.** Khi cần xóa cây thư mục, có nên follow symlink mặc định không?  
**Đáp án:** Không; phải có chính sách rõ để tránh tác động tới target ngoài root.

**19.** Một symlink hỏng đích có tự động thành `FileSystemLoopException` không?  
**Đáp án:** Không. Khi follow target thất bại, API có thể dùng attributes của link hoặc báo lỗi khác.

**20.** Mục tiêu khác nhau giữa cycle detection và deduplication là gì?  
**Đáp án:** Cycle detection chặn quay về tổ tiên trên một nhánh; dedup muốn tránh xử lý một identity nhiều lần trên toàn công việc.

## 21. Tài liệu chính thức

- [Oracle Java SE 26 — Files.walkFileTree / Files.walk / Files.find](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): mặc định không follow symlink, FOLLOW_LINKS, maxDepth, cycle detection bằng file-key/isSameFile và callback.
- [Oracle Java SE 26 — FileSystemLoopException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileSystemLoopException.html): checked exception khi gặp vòng lặp filesystem, có từ Java 7.
- [Oracle Java SE 26 — FileVisitOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileVisitOption.html): cấu hình FOLLOW_LINKS.
- [Oracle Java SE 26 — SimpleFileVisitor](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): callback và hành vi mặc định khi visit thất bại.
- [Oracle Java SE 26 — FileVisitResult](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileVisitResult.html): CONTINUE, TERMINATE, SKIP_SUBTREE và SKIP_SIBLINGS.
- [Oracle Java SE 26 — BasicFileAttributes.fileKey](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html#fileKey()): file identity key phụ thuộc provider, có thể null.
- [Oracle Java SE 26 — Files.isSameFile](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#isSameFile(java.nio.file.Path,java.nio.file.Path)): so sánh hai Path có cùng file identity không.
- [Oracle Java SE 26 — Path](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html): equals, normalize, toRealPath.
- [Oracle Java SE 26 — LinkOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/LinkOption.html): NOFOLLOW_LINKS cho kiểm tra thuộc tính.
- [Oracle Java SE 26 — Files.createSymbolicLink](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#createSymbolicLink(java.nio.file.Path,java.nio.file.Path,java.nio.file.attribute.FileAttribute...)): khả năng tạo symlink và ngoại lệ do provider/quyền.
- [Oracle Java SE 26 — UncheckedIOException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/UncheckedIOException.html): wrapper cho IOException trong Stream.
- [Oracle Java SE 7 — Files](https://docs.oracle.com/javase/7/docs/api/java/nio/file/Files.html): mốc ra đời của walkFileTree/FOLLOW_LINKS từ Java 7, không thay thế Javadoc hiện hành.
- [Dev.java — Walking the File Tree](https://dev.java/learn/api/io/java-io/file-system/walking-tree/): hướng dẫn chính thức xử lý cycle qua visitFileFailed.
- [Oracle Java Tutorial — Walking the File Tree](https://docs.oracle.com/javase/tutorial/essential/io/walk.html): ví dụ visitor và FileSystemLoopException, hữu ích để đối chiếu ý tưởng; ưu tiên Javadoc hiện hành để xác nhận hợp đồng API.

**Ghi nhớ:** **Không bật FOLLOW_LINKS khi không có nhu cầu.** Nếu phải follow, dùng `Files.walkFileTree` với callback `visitFileFailed` để nhận `FileSystemLoopException`, kiểm tra các thư mục **tổ tiên** thay vì chỉ so tên path, và không che các lỗi I/O khác. Một alias trùng target chưa chắc tạo cycle; một symlink ra ngoài root chưa chắc loop nhưng vẫn có thể nguy hiểm. Kiểm thử cycle thật phải chạy trên filesystem có quyền tạo link; trường hợp bị thiếu quyền là **SKIPPED**, không phải PASS.