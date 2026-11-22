# walkFileTree, FileVisitor và SimpleFileVisitor trong Java

> **Chủ đề:** Java Core → I/O → **Duyệt cây thư mục**. Bài này giải thích cách đi qua toàn bộ cây thư mục theo chiều sâu bằng `Files.walkFileTree`, cách bốn callback của `FileVisitor` phối hợp, hành vi mặc định của `SimpleFileVisitor`, các giá trị `FileVisitResult`, giới hạn độ sâu, symbolic links, xử lý lỗi, và những mẫu ứng dụng như tìm file, loại nhánh, thống kê và xóa cây. Các ví dụ độc lập chạy bằng Java 17; các API NIO.2 cốt lõi xuất hiện từ Java 7.

## 1. Khi nào cần đi qua cả cây thư mục?

Giả sử ứng dụng nhận thư mục `project`:

~~~text
project/
├── README.md
└── docs/
    ├── a.txt
    └── b.txt
~~~

Bạn muốn duyệt từng mục trong `project`, phân biệt file và thư mục, có thể bỏ qua `build` hay `target`, tính tổng byte, hoặc làm cleanup sau khi xử lý các tệp con. Việc chỉ gọi `Files.list(project)` **không đủ**: nó liệt kê các mục con trực tiếp, không tự duyệt sâu.

`Files.walkFileTree(...)` là API dành cho trường hợp cần **điều khiển quy trình duyệt**: thực hiện hành động trước/sau khi đi vào directory, xử lý lỗi từng entry, yêu cầu dừng sớm hoặc bỏ một nhánh. Thuật toán đi theo chiều sâu (**depth-first**), chứ không đảm bảo các directory ngang cấp được thăm theo thứ tự tên.

**Phân biệt tạo đường dẫn và đọc filesystem:** `Path` chỉ biểu diễn một vị trí; `walkFileTree` thực sự truy cập provider, đọc `BasicFileAttributes` và mở/đóng các thư mục đang duyệt. Nó có thể ném `IOException` hoặc các lỗi runtime khác. Không được coi cây file là snapshot bất biến: file có thể bị đổi/xóa trong khi đang duyệt.

## 2. Hai overload chính của Files.walkFileTree

~~~java
// Duyệt hết cây, không theo symbolic link mặc định:
Files.walkFileTree(start, visitor);

// Chọn option, maxDepth và visitor:
Files.walkFileTree(start, options, maxDepth, visitor);
~~~

Đây là **fragment**. `start` có kiểu `Path`, `visitor` là `FileVisitor<? super Path>`, `options` là `Set<FileVisitOption>` và method khai báo `throws IOException`.

| Tham số / kết quả | Ý nghĩa |
| --- | --- |
| `start` | Path gốc bắt đầu duyệt; **chính start cũng được thăm** theo quy tắc độ sâu. Có thể là file thường, directory hoặc symbolic link. |
| `visitor` | Object có callback xử lý directory/file/lỗi. Method gọi callback khi duyệt, không trả `Stream<Path>`. |
| `options` | Tập option, thông dụng là `FileVisitOption.FOLLOW_LINKS` để yêu cầu theo symbolic links. Tập rỗng = không follow links. |
| `maxDepth` | Số cấp directory tối đa tính từ start. `0` nghĩa là chỉ xử lý start; `Integer.MAX_VALUE` thường dùng cho toàn bộ độ sâu. Giá trị âm không hợp lệ. |
| Kiểu trả về | `Path` **start** khi duyệt hoàn thành hoặc callback trả `TERMINATE`; không phải số file đã duyệt. |
| Ngoại lệ | `IOException` từ callback có thể truyền về caller; callback trả `null` sẽ gây `NullPointerException`. |

Overload hai tham số tương đương về hành vi với:

~~~java
Files.walkFileTree(
    start,
    java.util.EnumSet.noneOf(FileVisitOption.class),
    Integer.MAX_VALUE,
    visitor);
~~~

Vì vậy **mặc định không theo symlink**, không hạn chế độ sâu theo giới hạn hợp lý do provider áp dụng, và thực hiện các callback tuần tự trong cùng lời gọi. `FileVisitOption.FOLLOW_LINKS` cần được chọn **chủ động**, không tự suy ra chỉ vì tên file trông giống directory.

### 2.1. Vòng đời tài nguyên

`walkFileTree` tự quản lý các directory stream nội bộ trong quá trình gọi. Caller **không nhận một Stream mở** để phải `close()` sau khi hàm trả về. Tuy nhiên bất kỳ resource **bạn tự mở trong callback** (file channel, input stream, output stream, network connection) vẫn cần owner riêng đóng.

Đây là khác biệt với `Files.walk(...)` hoặc `Files.find(...)`: chúng trả về `Stream<Path>` được thực hiện lazily, có thể giữ directory handles nên **phải** được đóng bằng try-with-resources.

## 3. FileVisitor: bốn callback bắt buộc

`FileVisitor<T>` là interface generic. Với file system Java NIO thường dùng `FileVisitor<Path>`. Nó yêu cầu bốn phương thức:

| Callback | Khi được gọi | Ý nghĩa tham số |
| --- | --- | --- |
| `preVisitDirectory(Path dir, BasicFileAttributes attrs)` | Trước khi đi qua các entry của directory đã mở thành công | `dir` là directory; `attrs` chứa thuộc tính cơ bản của directory. |
| `visitFile(Path file, BasicFileAttributes attrs)` | Khi gặp file được duyệt (bao gồm mục không phải directory sau khi xử lý quy tắc symlink); ở giới hạn độ sâu có thể nhận **directory như file** | `attrs` là thuộc tính provider đã lấy cho entry, không cần bắt buộc gọi lại `Files.readAttributes`. |
| `visitFileFailed(Path file, IOException exc)` | Không thể đọc thuộc tính hoặc không mở được directory/file theo quy tắc của walker; cũng dùng để báo cycle khi theo symlink | `exc` là nguyên nhân I/O gắn với entry đó. |
| `postVisitDirectory(Path dir, IOException exc)` | Sau khi thăm entries/descendants của directory đã được mở và kết thúc việc liệt kê | `exc == null` nếu vòng lặp liệt kê directory không bị lỗi I/O; khác null nếu có lỗi lúc iteration. |

Mỗi callback trả `FileVisitResult` và có thể khai báo `throws IOException`.

**Thứ tự chiều sâu điển hình** nếu không gặp lỗi hoặc skip:

~~~text
preVisitDirectory(root)
  visitFile(root/README.md)         [vị trí thực giữa các sibling không cố định]
  preVisitDirectory(root/docs)
    visitFile(root/docs/a.txt)
    visitFile(root/docs/b.txt)
  postVisitDirectory(root/docs)
postVisitDirectory(root)
~~~

Đây là **một thứ tự khả dĩ**; không được viết test bắt buộc `README.md` đứng trước `docs` hay `a.txt` đứng trước `b.txt` trên mọi filesystem. Nếu cần output xác định, tích lũy kết quả rồi sắp xếp theo quy tắc do ứng dụng định nghĩa.

### 3.1. Chi tiết về pre và post

`preVisitDirectory` chỉ được gọi cho directory walker **mở thành công** để đi sâu trong giới hạn độ sâu. Nếu nó trả `SKIP_SUBTREE` hoặc `SKIP_SIBLINGS`, walker không thăm nội dung của directory đó và **không gọi `postVisitDirectory` cho directory bị bỏ qua**.

`postVisitDirectory` phù hợp cho thao tác **sau khi đã xử lý con** như xóa directory rỗng, tổng hợp thống kê từ các con hoặc áp dụng thuộc tính directory sau khi copy. Nếu liệt kê directory gặp I/O error, tham số `exc` báo lỗi; callback phải quyết định ném ra hay tiếp tục. Đừng nhầm `exc` ở `postVisitDirectory` với mọi lỗi con: lỗi thăm một entry có thể đã được chuyển riêng vào `visitFileFailed`.

### 3.2. Bản thực thi interface trực tiếp

Nếu triển khai `FileVisitor<Path>` trực tiếp, bạn phải cung cấp **cả bốn phương thức**, kể cả khi chỉ muốn làm việc với file:

~~~java
// Fragment lớp; cần import Path, FileVisitor, FileVisitResult,
// BasicFileAttributes, IOException.
final class CountingVisitor implements FileVisitor<Path> {
    long files;

    @Override
    public FileVisitResult preVisitDirectory(
            Path dir, BasicFileAttributes attrs) {
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        if (attrs.isRegularFile()) {
            files++;
        }
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
        if (exc != null) {
            throw exc;
        }
        return FileVisitResult.CONTINUE;
    }
}
~~~

Đây là **fragment có đủ method interface** nhưng chưa có `main`. Điểm quan trọng là method nào cũng trả một kết quả hợp lệ; `IOException` từ callback làm quá trình duyệt dừng và được truyền lên caller nếu không được xử lý.

## 4. SimpleFileVisitor: cách viết ngắn gọn hơn

`SimpleFileVisitor<T>` **triển khai sẵn** `FileVisitor<T>`, cho phép override chỉ callback bạn cần:

- `preVisitDirectory` mặc định trả `CONTINUE`.
- `visitFile` mặc định trả `CONTINUE`.
- `visitFileFailed` mặc định **ném lại `IOException`** đã nhận.
- `postVisitDirectory` mặc định trả `CONTINUE` nếu `exc == null`; nếu có lỗi liệt kê directory, **ném lại `exc`**.

Do đó, “Simple” **không có nghĩa nuốt mọi lỗi**. Nếu muốn xử lý một file không đọc được rồi bỏ qua, phải chủ động override `visitFileFailed` và nêu cách log/đo số lỗi. Nếu muốn theo dõi `postVisitDirectory` mà vẫn xử lý mặc định các lỗi, có thể gọi `super.postVisitDirectory(dir, exc)`.

Ví dụ fragment đếm số regular files:

~~~java
final java.util.concurrent.atomic.AtomicLong count =
        new java.util.concurrent.atomic.AtomicLong();

Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        if (attrs.isRegularFile()) {
            count.incrementAndGet();
        }
        return FileVisitResult.CONTINUE;
    }
});
~~~

Mã fragment nằm trong method xử lý `IOException`, cần import các lớp liên quan. `AtomicLong` **không bắt buộc** với walker thông thường gọi callback tuần tự; nó được dùng ở đây để cho thấy biến mutable từ anonymous class có thể được cập nhật. Trong code đơn giản, có thể dùng field trong lớp visitor để lưu count.

## 5. FileVisitResult điều khiển chính xác hướng duyệt

`FileVisitResult` có bốn hằng:

| Giá trị | Hành vi |
| --- | --- |
| `CONTINUE` | Tiếp tục duyệt các entry còn lại theo depth-first. |
| `TERMINATE` | Dừng **toàn bộ** hành trình ngay; không còn callback file-walk nào khác sau kết quả này. |
| `SKIP_SUBTREE` | Khi **preVisitDirectory** trả về: không duyệt các con của directory hiện tại; các sibling khác vẫn có thể duyệt. |
| `SKIP_SIBLINGS` | Bỏ qua các sibling **chưa thăm** trong directory cha; nếu trả từ preVisitDirectory thì cả subtree của directory hiện tại cũng bị bỏ qua. |

Hãy hiểu “sibling” theo **cùng thư mục cha** của entry ở thời điểm callback, không phải “mọi mục khác trên toàn filesystem”.

### 5.1. Những ngữ cảnh dễ nhầm

- `preVisitDirectory(dir) -> SKIP_SUBTREE`: **không** thăm entry con, không có `postVisitDirectory(dir)`. Sau đó vẫn có thể tiếp tục các directory ngang hàng.
- `preVisitDirectory(dir) -> SKIP_SIBLINGS`: bỏ directory này cùng các sibling còn lại, không có post của dir vừa bị skip.
- `visitFile(file) -> SKIP_SIBLINGS`: không thăm thêm các sibling của file trong directory cha; iterator hiện tại kết thúc sớm.
- `postVisitDirectory(dir) -> SKIP_SIBLINGS`: sau khi xong directory hiện tại, bỏ các sibling cùng cấp chưa duyệt.
- `visitFile(file) -> SKIP_SUBTREE`: vì file không có subtree, kết quả được xử lý tương tự `CONTINUE` theo hợp đồng.
- `TERMINATE` từ một callback: thoát traversal toàn cây; đừng kỳ vọng `postVisitDirectory` của mọi ancestor được gọi như `finally`. Nếu cần giải phóng resource riêng, dùng try/finally hoặc try-with-resources bên ngoài callback.
- Callback **không được trả `null`**: walker ném `NullPointerException`.

Ví dụ tìm file đầu tiên đáp ứng điều kiện:

~~~java
// Fragment: biến target do caller xác định, callback gọi trong method
// xử lý IOException.
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(
            Path file, BasicFileAttributes attrs) {
        if (attrs.isRegularFile()
                && file.getFileName().toString().equals(target)) {
            System.out.println("Found: " + file);
            return FileVisitResult.TERMINATE;
        }
        return FileVisitResult.CONTINUE;
    }
});
~~~

Do thứ tự duyệt sibling **không xác định**, nếu có nhiều file trùng tên tại các nhánh khác nhau, kết quả “đầu tiên” **không có nghĩa** đường dẫn ngắn nhất, gần nhất hoặc nhỏ nhất theo bảng chữ cái. Nếu cần lựa chọn deterministic, phải xác định quy tắc trước và cân nhắc thu thập/sắp xếp.

## 6. Ví dụ chạy được 1: duyệt và liệt kê cây thư mục

Tạo file **`TreeWalkDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class TreeWalkDemo {
    // Chỉ dọn cây tạm do chính demo tạo.
    static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException exc) throws IOException {
                if (exc != null) {
                    throw exc;
                }
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("tree-demo-");
        try {
            Files.createDirectory(root.resolve("docs"));
            Files.writeString(root.resolve("README.md"),
                    "root", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("docs/a.txt"),
                    "a", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("docs/b.txt"),
                    "b", StandardCharsets.UTF_8);

            List<String> found = new ArrayList<>();

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    if (!dir.equals(root)) {
                        found.add("D:" + dir.getFileName());
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    found.add("F:" + file.getFileName());
                    return FileVisitResult.CONTINUE;
                }
            });

            // Hệ thống tệp không bắt buộc trả sibling theo tên:
            // sort sau khi thu thập để stdout ổn định.
            Collections.sort(found);
            found.forEach(System.out::println);
        } finally {
            deleteTree(root);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 TreeWalkDemo.java
java TreeWalkDemo
~~~

**Stdout đã kiểm tra trên JDK:**

~~~text
D:docs
F:README.md
F:a.txt
F:b.txt
~~~

**Giải thích:** `root` là thư mục tạm do chương trình mới tạo, bên trong có `docs` và ba file. `preVisitDirectory` thêm directory trừ root; `visitFile` thêm file; `postVisitDirectory` không cần override trong vòng duyệt liệt kê vì mặc định của `SimpleFileVisitor` đã tiếp tục và báo lỗi khi cần. Sau khi xử lý, khối `finally` gọi một visitor **khác** để xóa toàn bộ cây tạm theo thứ tự an toàn: file trước, directory sau.

Ví dụ ghi `dir.getFileName()` và `file.getFileName()` với các tên độc lập, sau đó sort để không phụ thuộc ký tự separator Windows/Unix hoặc thứ tự duyệt directory. Trong bài toán thật, nếu có hai file cùng basename trong các nhánh khác nhau, chỉ ghi filename sẽ gây trùng tên; nên dùng `root.relativize(file)` hoặc một cấu trúc lưu đầy đủ Path.

**Cảnh báo an toàn:** phương thức `deleteTree` trong demo thật sự xóa dữ liệu. Chỉ gọi nó với cây **tạm do demo vừa tạo**. Không chuyển phương thức này sang một path do người dùng cung cấp mà chưa bổ sung xác nhận phạm vi, quyền, symlink và chính sách xóa dữ liệu.

## 7. Ví dụ chạy được 2: bỏ qua một nhánh thư mục

Một crawler không nên mở thư mục không cần thiết, ví dụ `node_modules`, `build` hoặc vùng dữ liệu nhạy cảm. Để cắt cả subtree, dùng `SKIP_SUBTREE` trong `preVisitDirectory`.

Tạo file **`SkipTreeDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.concurrent.atomic.AtomicInteger;

public class SkipTreeDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("skip-demo-");
        try {
            Files.createDirectory(root.resolve("public"));
            Files.createDirectory(root.resolve("private"));
            Files.writeString(root.resolve("public/hello.txt"), "ok");
            Files.writeString(root.resolve("private/secret.txt"), "skip");
            Files.writeString(root.resolve("root.txt"), "ok");

            AtomicInteger files = new AtomicInteger();
            AtomicInteger skipped = new AtomicInteger();

            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs) {
                    if (dir.getFileName().toString().equals("private")) {
                        skipped.incrementAndGet();
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(
                        Path file, BasicFileAttributes attrs) {
                    files.incrementAndGet();
                    return FileVisitResult.CONTINUE;
                }
            });

            System.out.println("files=" + files.get());
            System.out.println("skipped=" + skipped.get());
        } finally {
            TreeWalkDemo.deleteTree(root);
        }
    }
}
~~~

Để chạy **ví dụ này**, đặt cả `TreeWalkDemo.java` của mục trước và `SkipTreeDemo.java` trong **cùng thư mục** để tái sử dụng helper xóa cây:

~~~bash
javac --release 17 TreeWalkDemo.java SkipTreeDemo.java
java SkipTreeDemo
~~~

Stdout:

~~~text
files=2
skipped=1
~~~

`private/secret.txt` **không được thăm** do callback của chính thư mục `private` trả `SKIP_SUBTREE`. `public/hello.txt` và `root.txt` được tính: hai file. `skipped=1` vì có đúng một directory tên `private` trong cây giả lập.

**Lưu ý biên dịch:** `SkipTreeDemo.java` chủ động dùng helper package-private static `TreeWalkDemo.deleteTree` từ ví dụ trước. Nếu muốn file đứng độc lập hoàn toàn, copy helper đó vào cùng class hoặc thay bằng phương pháp cleanup phù hợp. Hai ví dụ cùng được cung cấp đầy đủ trong bài và lệnh biên dịch trên bao gồm cả hai nguồn.

Một mẫu thực tế thường so sánh **đường dẫn relative** hoặc cây được phép thay vì chỉ so tên: hai thư mục trùng tên `private` ở vị trí khác nhau có thể cần policy khác. Nếu bỏ qua directory, walker không đọc các file dưới đó; đừng gọi `Files.walkFileTree` trên directory đó lần thứ hai rồi vô hiệu hóa mục đích skip.

## 8. maxDepth: cấp 0, cấp 1 và directory ở giới hạn

Với overload:

~~~java
Files.walkFileTree(
    root,
    EnumSet.noneOf(FileVisitOption.class),
    1,
    visitor);
~~~

`maxDepth=0` chỉ thăm `root`; `maxDepth=1` xử lý `root` và các entry trực tiếp bên dưới, **không duyệt sâu hơn**. Một chi tiết bất ngờ từ Javadoc: entry là **directory ở chính `maxDepth` được chuyển tới `visitFile`**, không mở sâu và không gọi cặp `preVisitDirectory/postVisitDirectory` cho directory đó.

Ví dụ cây:

~~~text
root/                  độ sâu 0
└── child/             độ sâu 1
    └── note.txt       độ sâu 2
~~~

Khi duyệt `maxDepth=1`, callback `preVisitDirectory(root)` có thể được gọi, nhưng `child` được báo qua `visitFile(child, attrs)`; `note.txt` không được thăm. Điều này giải thích vì sao mã `visitFile` nên kiểm tra `attrs.isRegularFile()` thay vì mặc định mọi `file` nhận được ở đó đều là regular file.

### 8.1. Ví dụ chạy được 3: quan sát directory tại maxDepth

Tạo file **`DepthDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumSet;
import java.util.List;

public class DepthDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("depth-");
        try {
            Files.createDirectory(root.resolve("child"));
            Files.writeString(root.resolve("child/note.txt"), "x");

            List<String> found = new ArrayList<>();
            Files.walkFileTree(
                    root, EnumSet.noneOf(FileVisitOption.class), 1,
                    new SimpleFileVisitor<Path>() {
                        @Override
                        public FileVisitResult preVisitDirectory(
                                Path dir, BasicFileAttributes attrs) {
                            found.add("D:" + dir.getFileName());
                            return FileVisitResult.CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFile(
                                Path file, BasicFileAttributes attrs) {
                            found.add("F:" + file.getFileName());
                            return FileVisitResult.CONTINUE;
                        }
                    });

            Collections.sort(found);
            System.out.println("depthOneEntries=" + found.size());
            System.out.println("childAsFile="
                    + found.stream().anyMatch(s -> s.equals("F:child")));
        } finally {
            TreeWalkDemo.deleteTree(root);
        }
    }
}
~~~

Biên dịch cùng helper:

~~~bash
javac --release 17 TreeWalkDemo.java DepthDemo.java
java DepthDemo
~~~

Stdout:

~~~text
depthOneEntries=2
childAsFile=true
~~~

Tại `maxDepth=1`, callback có một entry cho root (`preVisitDirectory`) và một entry cho child (`visitFile`), tổng cộng 2; file `child/note.txt` sâu 2 nên không được duyệt. `Collections.sort` không cần thiết cho phép đếm, nhưng giúp minh họa cách chuẩn hóa danh sách khi muốn kiểm thử event names.

Nếu `maxDepth` âm, `Files.walkFileTree` ném `IllegalArgumentException`. Trong ứng dụng cho người dùng nhập độ sâu, hãy validate trước và đặt giới hạn hợp lý để tránh traversal khổng lồ vô ý.

## 9. Symbolic links: mặc định không follow

Mặc định `Files.walkFileTree(start, visitor)` **không tự đi theo symbolic links**. Nếu một entry bên trong cây là symbolic link trỏ tới thư mục khác, entry đó thường được đưa tới `visitFile` với thuộc tính của chính link. Điều này hữu ích khi duyệt file để không vượt khỏi root một cách vô ý.

Muốn follow links:

~~~java
// Fragment: root đã xác định, method throws IOException.
Files.walkFileTree(
        root,
        java.util.EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor);
~~~

Nhưng **FOLLOW_LINKS cần chính sách an toàn**:

- Một symbolic link có thể dẫn **ra ngoài** cây path ban đầu; `root.relativize(path)` đơn thuần không chứng minh dữ liệu thật nằm dưới root.
- Nhiều link có thể dẫn tới cùng file/directory, dẫn đến xử lý trùng lặp. Nếu đếm kích thước, thống kê có thể bị tăng gấp.
- Khi follow links, walker phát hiện cycle đường dẫn tới ancestor bằng file key hoặc `Files.isSameFile` theo provider. Nếu phát hiện vòng, `visitFileFailed` nhận `FileSystemLoopException`.
- Không phải mọi symbolic link trỏ tới mục tiêu hợp lệ. Nếu không đọc được attrs của target, walker có thể thử attrs của chính link rồi chuyển link qua `visitFile`; do đó `attrs` không nhất thiết mô tả target trong mọi trường hợp.
- Đặt `maxDepth` vẫn giới hạn số mức, nhưng **không** giới hạn số lượng entry tại mỗi mức. Cần thêm giới hạn thời gian/số file/bytes nếu input không đáng tin.

### 9.1. Xử lý cycle có chủ đích

~~~java
// Fragment: visitor dùng trong walkFileTree(... FOLLOW_LINKS ...).
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    if (exc instanceof java.nio.file.FileSystemLoopException) {
        // Báo hoặc đếm vòng symlink mà không nuốt các lỗi khác.
        System.err.println("Cycle at: " + file);
        return FileVisitResult.CONTINUE;
    }
    throw exc;
}
~~~

Đây là **method fragment** bên trong subclass `SimpleFileVisitor<Path>`, không phải chương trình độc lập. Trả `CONTINUE` ở đây có nghĩa chính sách cho phép bỏ qua entry bị cycle, không đảm bảo thông tin traversal hoàn chỉnh. Nếu bài toán yêu cầu snapshot/traversal đầy đủ, nên ném lỗi để caller biết kết quả thiếu.

## 10. Xử lý lỗi trong visitor một cách có kiểm soát

### 10.1. visitFileFailed không phải postVisitDirectory

Nếu walker **không thể đọc thuộc tính** một path, hoặc không thể **mở directory** đó, nó thường gọi `visitFileFailed(path, exc)`. Nếu đã **mở directory** nhưng gặp lỗi khi **liệt kê các entry**, walker đóng directory và gọi `postVisitDirectory(dir, exc)`.

Đừng gom hai trường hợp thành một callback: chúng xảy ra ở giai đoạn khác nhau và có thể dẫn tới khả năng phục hồi khác nhau.

Hành vi mặc định của `SimpleFileVisitor` là **ném lại** I/O error, nên traversal có thể dừng ngay khi gặp thư mục không thể đọc. Nếu nghiệp vụ cho phép “best effort”, bạn có thể ghi nhận lỗi và tiếp tục:

~~~java
// Method fragment bên trong SimpleFileVisitor<Path>.
@Override
public FileVisitResult visitFileFailed(
        Path path, IOException exc) {
    errors.add(path); // errors là collection được caller quản lý.
    return FileVisitResult.CONTINUE;
}
~~~

Nếu không muốn mất nguyên nhân, lưu cả `Path` và `IOException` hoặc log lỗi theo chính sách. Ví dụ `errors.add(path)` là **fragment**, chưa định nghĩa `errors`; trong production cần collection phù hợp với yêu cầu bảo mật và bộ nhớ.

### 10.2. Lỗi liệt kê trong postVisitDirectory

~~~java
@Override
public FileVisitResult postVisitDirectory(
        Path dir, IOException exc) throws IOException {
    if (exc != null) {
        throw exc;   // Fail fast, không báo thành công khi dữ liệu thiếu.
    }
    return FileVisitResult.CONTINUE;
}
~~~

Đây là method fragment. Nếu muốn tiếp tục trong một số lỗi directory, có thể log vào báo cáo của ứng dụng rồi `return CONTINUE`. Tuy nhiên khi đang **xóa/copy** cây, nuốt lỗi rồi giả định directory đã xử lý hết là nguy hiểm: có thể còn file con chưa thấy, thao tác xóa directory sau đó sẽ thất bại.

### 10.3. Ngoại lệ ném trong callback

Nếu `visitFile` ném `IOException` trực tiếp, `walkFileTree` kết thúc và truyền exception ra caller; nó **không mặc nhiên** bắt exception đó rồi gọi `visitFileFailed` cho chính callback đã lỗi. `visitFileFailed` chủ yếu cho lỗi do walker gặp khi truy cập entry theo hợp đồng. Nếu code tự mở/đọc nội dung file trong `visitFile`, bạn cần xác định **có catch/continue cục bộ hay propagate**.

Lỗi runtime hoặc `Error` phát sinh trong callback cũng không được tự động chuyển thành `FileVisitResult.CONTINUE`. Và nếu một callback trả `TERMINATE`, code bên ngoài không nên coi điều đó giống một exception có rollback: các side effect đã thực hiện vẫn còn.

## 11. Xóa cây bằng walkFileTree: vì sao cần postVisitDirectory?

Một directory chỉ xóa được bình thường sau khi các entry bên trong đã biến mất. Vì walker đi theo depth-first, cặp callback phù hợp là:

- `visitFile`: xóa file (kể cả symbolic link mặc định không follow).
- `postVisitDirectory`: sau khi các con được thăm/xóa, xóa directory đó.
- `visitFileFailed`: báo lỗi thay vì im lặng bỏ qua file không kiểm tra được.
- `preVisitDirectory`: thường giữ mặc định `CONTINUE`, trừ khi chính sách muốn từ chối nhánh.

Đây là chính thứ tự của helper `deleteTree` trong `TreeWalkDemo`. Nếu đảo thành xóa directory ở `preVisitDirectory`, `Files.delete(dir)` sẽ có nguy cơ `DirectoryNotEmptyException`.

**Mẫu dùng trong sản phẩm cần cẩn trọng hơn demo**, vì xóa là thao tác phá hủy:

1. Chỉ nhận một root rõ ràng do caller **được ủy quyền** chọn; chuẩn hóa và xác nhận phạm vi trước thao tác.
2. Không follow links khi xóa thông thường, để xóa **link itself** thay vì đi sâu vào target bên ngoài root.
3. Ghi nhận lỗi từng entry; không coi kết quả traversal lỗi là “đã xóa sạch”.
4. Nếu cây thư mục có thể bị actor khác thay đổi đồng thời, `Files.delete` qua Path có thể có **race**; một số provider hỗ trợ `SecureDirectoryStream` để thao tác tương đối với handle và giảm một số rủi ro, nhưng không phải provider nào cũng có.
5. Nếu cần thùng rác, backup hoặc khả năng phục hồi, **đừng** dùng đoạn demo gọi `Files.delete` trực tiếp làm API nghiệp vụ.
6. Đừng gọi traversal xóa trên filesystem root, home directory, thư mục dự án thật hoặc path lấy thẳng từ input không tin cậy.

### 11.1. Vì sao callback sau directory đặc biệt có giá trị?

Không chỉ xóa: khi **copy directory tree**, bạn thường tạo directory đích ở `preVisitDirectory`, copy file trong `visitFile`, rồi áp dụng một số metadata/permission cuối cùng của directory ở `postVisitDirectory` để tránh việc copy nội dung làm thời gian sửa đổi directory thay đổi. Đây là mẫu thao tác theo **thứ tự phụ thuộc cha/con** mà `Files.walk(...)` kèm `forEach` đơn giản không biểu diễn tự nhiên bằng callback có cấu trúc.

## 12. Đếm kích thước, tìm file và độ tin cậy của attrs

`BasicFileAttributes` cung cấp một số phương thức hữu ích:

| Thuộc tính | Cách dùng |
| --- | --- |
| `isRegularFile()` | Đếm/xử lý file thường; tránh cộng size của directory hoặc link theo nhầm nghĩa. |
| `isDirectory()` | Kiểm tra entry có thuộc tính directory; hữu ích tại `maxDepth` khi directory đi qua `visitFile`. |
| `isSymbolicLink()` | Phân biệt symlink khi không follow hoặc đọc attrs của chính link. |
| `size()` | Kích thước entry theo **byte** mà provider báo; không phải số ký tự text hoặc dung lượng disk được cấp. |
| `lastModifiedTime()` | Lọc theo timestamp nếu ứng dụng cần, có thể thay đổi đồng thời. |
| `fileKey()` | Id do provider cấp để có thể nhận dạng file, không đảm bảo khác null hoặc ổn định trên mọi provider. |

Trong callback, dùng `attrs` đã được walker cung cấp thay vì gọi `Files.readAttributes` lần nữa cho cùng entry nếu không có lý do xác thực mới. Việc gọi lại tạo thêm I/O và có thể trả trạng thái khác do concurrent modifications.

Ví dụ fragment đếm byte regular files:

~~~java
// Fragment: code nằm trong class extends SimpleFileVisitor<Path>.
private long totalBytes;

@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) {
    if (attrs.isRegularFile()) {
        totalBytes += attrs.size();
    }
    return FileVisitResult.CONTINUE;
}
~~~

`totalBytes` là tổng **logic file sizes** theo những entry được thăm, **không phải** lượng disk block đã cấp hay tổng byte không trùng lặp trên storage. Hard link, symlink-following, sparse files và dữ liệu đang bị sửa đồng thời làm diễn giải “dung lượng thư mục” phức tạp. Nếu số lượng file cực lớn, `long` về lý thuyết có thể overflow; nếu yêu cầu kiểm toán chính xác, cần chính sách xử lý cộng tràn và snapshot/lock ở cấp filesystem phù hợp.

## 13. So sánh với Files.walk, Files.find và Files.list

| API | Độ sâu / hướng | Phong cách | Cách dọn |
| --- | --- | --- | --- |
| `Files.list(dir)` | Một cấp trực tiếp | `Stream<Path>` từ một directory | **Đóng Stream** bằng try-with-resources |
| `Files.walk(start)` | Đệ quy theo chiều sâu | `Stream<Path>` lazy | **Đóng Stream**; I/O trong quá trình tiêu thụ có thể thành `UncheckedIOException` |
| `Files.walk(start, maxDepth)` | Đệ quy giới hạn độ sâu | `Stream<Path>` lazy | **Đóng Stream** |
| `Files.find(start, maxDepth, matcher, options...)` | Đệ quy, có predicate nhận path + attrs | `Stream<Path>` lazy | **Đóng Stream** |
| `Files.walkFileTree(start, visitor)` | Đệ quy depth-first không follow link mặc định | **Callback** pre/visit/fail/post; điều khiển skip/terminate | Walker tự đóng directory handles nội bộ |
| `Files.walkFileTree(start, options, depth, visitor)` | Có FOLLOW_LINKS và độ sâu tùy chọn | Callback có thể báo lỗi từng entry | Không có Stream trả về để đóng |

Nếu chỉ cần danh sách file đã lọc, `Files.walk(...)` + `filter` có thể gọn. Nếu cần **skip toàn bộ subtree theo nội dung directory**, cần callback `preVisitDirectory`. Nếu cần **xóa directory sau khi xóa hết con**, `walkFileTree` thường trực tiếp và rõ ràng hơn. Nếu dùng `Files.walk(...)`, cần ghi nhớ `Stream` lazy và giải phóng resource bằng:

~~~java
// Fragment: caller xử lý IOException từ Files.walk.
try (java.util.stream.Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile).forEach(System.out::println);
}
~~~

Đây là fragment: trong ngữ cảnh tương ứng và với filesystem bị thay đổi đồng thời, vẫn có thể gặp lỗi khi stream đang được tiêu thụ. `Files.walk` stream chỉ đóng khi `close()` hoặc try-with-resources kết thúc, **không** tự đóng khi terminal operation như `count()`/`forEach()` hoàn tất.

## 14. Bài toán thứ tự và tính nhất quán

`walkFileTree` có thứ tự **depth-first**, nhưng **không đảm bảo thứ tự các sibling**. Hệ thống file khác nhau, trạng thái thư mục khác nhau, hoặc việc tạo/xóa file đồng thời có thể làm thứ tự khác nhau.

**Nếu cần output deterministic**:

- Thu thập `Path` hoặc dữ liệu thống kê, rồi sắp xếp sau cùng.
- Dùng `root.relativize(path)` để có vị trí relative; lưu ý `toString()` thể hiện separator theo provider, nên khi serialize cho hệ thống khác cần format được định nghĩa rõ.
- Không dựa vào lần duyệt đầu tiên để chọn file “nhỏ nhất”, “mới nhất” hoặc “đầu tiên theo tên” trừ khi duyệt đủ và so sánh có chủ đích.
- Nếu quá nhiều entry không thể gom RAM, cần một chiến lược directory enumeration/sort riêng hoặc external sort; `walkFileTree` không cung cấp tùy chọn sắp xếp sibling sẵn có.
- `Path`, `BasicFileAttributes` và nội dung tệp không là snapshot đồng nhất; kết quả đếm/chọn có thể bị ảnh hưởng bởi file đang sửa.

## 15. Hiệu năng và giới hạn khi duyệt cây lớn

Một cây hàng triệu file có thể tiêu tốn thời gian đáng kể do truy cập metadata và mở thư mục. Hãy tránh các sai lầm thường gặp:

1. **Không giới hạn độ sâu khi chỉ cần một vài cấp**: dùng overload `maxDepth` phù hợp để tiết kiệm I/O.
2. **Vào directory không liên quan rồi mới bỏ file bên trong**: dùng `SKIP_SUBTREE` sớm trong `preVisitDirectory`.
3. **Mở file để kiểm tra nội dung khi tên/metadata đủ lọc**: tránh I/O thừa.
4. **Gọi `Files.size(path)` cho mọi file dù đã có `attrs.size()`**: có thể tăng số lần truy cập metadata.
5. **Thu tất cả Path vào List vô hạn**: xử lý streaming theo callback, chỉ giữ trạng thái tổng hợp nếu có thể.
6. **Bỏ qua lỗi để nhận báo cáo “đã duyệt hết”**: phân biệt đếm thành công, lỗi và nhánh bị bỏ.
7. **Chạy đồng thời nhiều walker trên cùng directory**: có thể tạo áp lực I/O và làm thứ tự/biến động phức tạp; chỉ làm nếu workload cần.
8. **FOLLOW_LINKS không kiểm soát**: dễ vượt boundary hoặc đếm trùng, tăng độ sâu và số file.
9. **Giữ resource riêng mở qua nhiều callback**: có thể cạn file descriptors; mở khi cần và đóng trong callback.
10. **Trông chờ callback được gọi trên thread khác**: `walkFileTree` là API traversal đồng bộ; parallelism phải do ứng dụng tổ chức riêng và tự bảo vệ state.

Nếu cần giới hạn **số lượng entry**, callback có thể tăng count và `return TERMINATE` khi đạt ngưỡng; tuy nhiên dừng sớm có nghĩa dữ liệu chưa hoàn chỉnh. Ghi rõ báo cáo bị cắt theo policy thay vì trả kết quả “đã duyệt xong”.

## 16. An toàn khi duyệt path do người dùng cung cấp

Ứng dụng sao lưu hoặc tìm kiếm có thể nhận root từ CLI/API. Duyệt một cây không tự là lỗ hổng, nhưng nếu callback **đọc nội dung bí mật, copy ra ngoài, xóa tệp hoặc thay quyền**, giới hạn phạm vi rất quan trọng.

- Chỉ chọn root được phép theo quyền truy cập và chính sách.
- Không dùng `normalize()` hay kiểm tra `startsWith(root)` như hàng rào duy nhất khi symlink và concurrent changes có thể tham gia.
- Với `FOLLOW_LINKS`, cần quyết định xử lý symlink trỏ ra ngoài root; symlink cycles được phát hiện nhưng không thay thế policy.
- Không ghi log đường dẫn/tên người dùng nhạy cảm không cần thiết.
- Dù không follow link, directory tree vẫn có thể bị đổi **giữa** lúc attrs được đọc và thao tác `Files.read`/`delete` xảy ra. Cần xét TOCTOU và quyền filesystem.
- Với xóa/copy, nên có dry-run, backup, xác thực root, xác nhận người dùng khi có thể; tránh biến ví dụ traversal thành xóa dữ liệu thật.
- Nếu caller cần biết kết quả hoàn chỉnh, không “thành công” khi `visitFileFailed` ghi lỗi rồi `CONTINUE`; trả thống kê gồm count lỗi và chính sách rõ ràng.

## 17. Các lỗi điển hình

1. **Dùng `Files.list` nhưng mong duyệt đệ quy.** `list` chỉ trả con trực tiếp.
2. **Cho rằng sibling được duyệt theo alphabet.** Không có cam kết như vậy.
3. **Dùng `SimpleFileVisitor` nhưng nghĩ lỗi I/O tự bị bỏ qua.** `visitFileFailed` mặc định ném lại exception.
4. **Override `visitFileFailed` rồi luôn `CONTINUE` mà không báo lỗi.** Kết quả im lặng thiếu dữ liệu.
5. **Cho rằng mọi directory đều đi qua `preVisitDirectory`.** Ở maxDepth, directory có thể đi qua `visitFile`.
6. **Đếm mọi callback `visitFile` là regular file.** Cần `attrs.isRegularFile()`.
7. **Dùng `SKIP_SUBTREE` trong `visitFile` để bỏ directory cha.** Nó chỉ hữu hiệu để cắt nhánh khi trả từ `preVisitDirectory`.
8. **Dùng `TERMINATE` rồi mong postVisitDirectory vẫn được gọi cho mọi ancestor.** Không có hợp đồng cleanup callback kiểu finally.
9. **Quên xử lý `postVisitDirectory(exc)`.** Lỗi liệt kê thư mục có thể bị bỏ qua hoặc báo cáo sai.
10. **Dùng `postVisitDirectory` để giả định mọi file con được xử lý thành công.** Có thể đã có callback lỗi được cho phép bỏ qua.
11. **Dùng `FOLLOW_LINKS` cho cây không tin cậy mà không giới hạn/kiểm tra.** Có thể đi ra ngoài root, gặp cycle hoặc trùng file.
12. **Xóa directory trong `preVisitDirectory`.** Chưa xóa con nên directory thường không rỗng.
13. **Gom tất cả file vào RAM dù chỉ cần đếm.** Với cây lớn, giữ state tổng hợp sẽ hiệu quả hơn.
14. **Giữ input/output streams mở trong nhiều callback.** Không quản lý resource tốt gây leak.
15. **Cho rằng walker khóa filesystem, không ai sửa được cây.** Filesystem biến động đồng thời là tình huống phải tính tới.
16. **Đóng resource mà walker tự mở bằng cách đóng file Path.** `Path` không có `close()`; walker quản lý directory handles nội bộ.
17. **Dùng `Files.walk` rồi quên đóng Stream.** Đây là API khác với `walkFileTree`.
18. **Gọi `Files.walkFileTree` với `maxDepth=-1`.** Bị `IllegalArgumentException`.
19. **Callback trả `null`.** Bị `NullPointerException` thay vì tiếp tục.
20. **Test với file thật và xóa nhầm dữ liệu.** Ví dụ xóa phải chỉ thao tác trên cây temp tạo trong test.

## 18. Câu hỏi tự kiểm tra

1. `Files.walkFileTree(root, visitor)` có tự follow symbolic links không?
2. Bốn method của `FileVisitor<Path>` là gì? Method nào xảy ra sau khi các con của directory đã xử lý?
3. `SimpleFileVisitor` làm gì mặc định khi không mở được file?
4. `SKIP_SUBTREE` và `SKIP_SIBLINGS` khác nhau thế nào khi trả từ `preVisitDirectory`?
5. `TERMINATE` có đảm bảo gọi `postVisitDirectory` cho mọi directory ancestor để cleanup không?
6. Với `maxDepth=1`, một directory con trực tiếp được báo qua callback nào?
7. Khi nào `visitFileFailed` nhận `FileSystemLoopException`?
8. Nếu chỉ muốn đếm regular files, cần kiểm tra `attrs` bằng method nào?
9. Vì sao xóa directory nên đặt trong `postVisitDirectory`?
10. `Files.walk(root)` trả về gì và có cần đóng không?
11. Có thể dựa vào thứ tự `visitFile` để lấy file nhỏ nhất theo tên không?
12. Khi `postVisitDirectory(dir, exc)` có `exc != null`, điều đó nói lên điều gì?
13. Trong walker, callback tự mở `Files.newInputStream(file)` thì ai đóng input stream?
14. Nếu callback trả `CONTINUE` sau lỗi đọc file, báo cáo thống kê có nên ghi nhận lỗi không?
15. Khi dùng `FOLLOW_LINKS` và root do user cung cấp, chỉ `normalize()` đã đủ an toàn chưa?

**Đáp án gợi ý:**

1. Không, mặc định không follow.
2. `preVisitDirectory`, `visitFile`, `visitFileFailed`, `postVisitDirectory`; method sau khi đi con là `postVisitDirectory` khi directory được mở/duyệt.
3. Ném lại `IOException`.
4. `SKIP_SUBTREE` bỏ subtree hiện tại nhưng có thể đi sibling; `SKIP_SIBLINGS` còn bỏ các sibling chưa thăm.
5. Không; dùng finally/try-with-resources cho resource tự quản lý.
6. Thường là `visitFile` ở giới hạn maxDepth.
7. Khi FOLLOW_LINKS làm walker phát hiện vòng link về ancestor.
8. `attrs.isRegularFile()`.
9. Phải xử lý/xóa file và thư mục con trước khi directory cha có thể rỗng để xóa.
10. Trả `Stream<Path>` lazy cần đóng.
11. Không; thứ tự sibling không được đảm bảo.
12. Lỗi I/O xảy ra khi liệt kê directory (không đồng nghĩa mọi lỗi file con đều nằm trong đó).
13. Chính callback hoặc owner ứng dụng, bằng try-with-resources.
14. Có, để caller biết traversal chỉ best effort và kết quả có thể thiếu.
15. Chưa, còn symlink, quyền, traversal ngoài root và TOCTOU.

## 19. Tài liệu chính thức

- [Oracle Java SE 21 — Files.walkFileTree](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): overload, độ sâu, FOLLOW_LINKS, lifecycle, xử lý lỗi và quy tắc callback.
- [Oracle Java SE 21 — FileVisitor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitor.html): bốn callback và hợp đồng `FileVisitResult`.
- [Oracle Java SE 21 — SimpleFileVisitor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): hành vi mặc định và exception propagation.
- [Oracle Java SE 21 — FileVisitResult](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitResult.html): `CONTINUE`, `TERMINATE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`.
- [Oracle Java SE 21 — FileVisitOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitOption.html): tùy chọn `FOLLOW_LINKS`.
- [Oracle Java SE 21 — BasicFileAttributes](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): size và loại entry.
- [Oracle Java SE 21 — FileSystemLoopException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystemLoopException.html): vòng symbolic links trong traversal.
- [Oracle Java Tutorial — Walking the File Tree](https://docs.oracle.com/javase/tutorial/essential/io/walk.html): ví dụ thực hành duyệt và kiểm soát flow.

**Ghi nhớ:** `Files.walkFileTree` đi sâu trong cây và giao quyền quyết định cho `FileVisitor`. Dùng `SimpleFileVisitor` khi chỉ cần override vài callback; `preVisitDirectory` giúp cắt nhánh, `visitFile` xử lý entry, `visitFileFailed` báo lỗi thăm entry, `postVisitDirectory` phù hợp cleanup/tổng hợp sau các con. Cần chú ý `maxDepth`, symbolic links, thứ tự không xác định và vòng đời tài nguyên trước khi áp dụng vào file thật.