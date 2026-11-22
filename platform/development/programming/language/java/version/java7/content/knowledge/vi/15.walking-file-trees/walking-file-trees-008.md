# Giới hạn độ sâu và tùy chọn theo liên kết khi duyệt cây tệp trong Java

## 1. Bài toán và mục tiêu

Khi duyệt một thư mục bằng Java, chúng ta thường không muốn truy cập mọi thứ ở mọi cấp. Ví dụ:

- Quét tệp cấu hình chỉ trong thư mục gốc và **hai cấp con**.
- Tìm các tệp `.json` dưới một thư mục dự án nhưng không đi sâu vô hạn.
- Đếm hoặc lọc các tệp của một cây thư mục theo giới hạn độ sâu.
- Lựa chọn có đi theo **symbolic link** (*symlink*, liên kết tượng trưng) hay chỉ coi link là một phần tử được phát hiện trong cây.
- Tránh vòng lặp link dẫn trở lại thư mục tổ tiên và tránh vô tình duyệt ra ngoài phạm vi dự kiến.

Java NIO.2 cung cấp hai nhóm API quan trọng:

~~~java
// Duyệt có Stream<Path>; nhớ đóng stream:
Files.walk(start, maxDepth);

// Duyệt bằng FileVisitor với giới hạn và tùy chọn:
Files.walkFileTree(start, options, maxDepth, visitor);
~~~

Đoạn này là **cú pháp minh họa**, giả sử `start` là `Path`, `maxDepth` là `int` không âm, `options` là `Set<FileVisitOption>` và `visitor` là `FileVisitor<? super Path>`. Cả `Files.walk` và `Files.walkFileTree` có thể duyệt theo độ sâu, nhưng **cách trả kết quả và xử lý lỗi khác nhau**.

**Điểm cốt lõi:** `maxDepth` là **số mức có thể đi xuống tính từ `start`**, còn `FOLLOW_LINKS` là **quy tắc xử lý symbolic link**. Giới hạn độ sâu và quyết định đi theo link là **hai chiều cấu hình độc lập**.

**Mục tiêu học tập:**

1. Xác định đúng độ sâu `0`, `1`, `2` và tính bao gồm đường dẫn bắt đầu.
2. Phân biệt các overload của `walk`, `find` và `walkFileTree`.
3. Hiểu mặc định **không theo symbolic link** và cách dùng `FileVisitOption.FOLLOW_LINKS`.
4. Biết giới hạn độ sâu không phải giới hạn số file, I/O hay ranh giới bảo mật.
5. Hiểu `FileSystemLoopException` khi theo link tạo chu trình.
6. Xử lý `Stream`, `IOException`, `UncheckedIOException`, các callback của `FileVisitor` và các tình huống thư mục thay đổi khi đang duyệt.
7. Viết mã Java 21 chạy được, có đầu ra chính xác, có kiểm thử trên filesystem tạm, không yêu cầu quyền đặc biệt để chạy bài chính.

**Phiên bản:** `FileVisitOption.FOLLOW_LINKS` và `Files.walkFileTree` đã có từ Java 7; `Files.walk` và `Files.find` bổ sung từ Java 8. **Tất cả vẫn là API đang được hỗ trợ trên JDK hiện đại**. Ví dụ dùng Java 21 và không khuyến nghị API legacy.

## 2. Khái niệm độ sâu: bắt đầu từ số 0

Giả sử cây thư mục có cấu trúc sau, với `root` là điểm bắt đầu duyệt:

~~~text
root/                         depth = 0
├── root.txt                  depth = 1
└── team/                     depth = 1
    ├── member.txt            depth = 2
    └── deep/                 depth = 2
        └── details.txt       depth = 3
~~~

Bất kỳ tên nào được đi tới bằng `start.resolve(...)` đều có mức bằng **số thành phần tên bổ sung tính từ start** trong một cây không thay đổi. Vì vậy:

| `maxDepth` | Những phần tử được nhìn thấy khi dùng `Files.walk(root, maxDepth)` |
| --- | --- |
| `0` | Chỉ có `root`, không có con |
| `1` | `root`, `root.txt`, `team` |
| `2` | Các phần tử mức 0, 1 và thêm `team/member.txt`, `team/deep` |
| `3` | Các phần tử mức 0–2 và thêm `team/deep/details.txt` |
| `Integer.MAX_VALUE` | Mức giới hạn rất lớn; thường dùng để biểu diễn muốn duyệt toàn cây |

**Mốc tính:** `start` có **depth 0**, kể cả khi chính `start` nằm sâu dưới ổ đĩa. `maxDepth=1` bao gồm **con trực tiếp** chứ không chỉ những file con; directory tại depth 1 vẫn xuất hiện trong kết quả.

Hai sai lầm thường gặp:

- Tưởng `maxDepth=1` sẽ duyệt tiếp một cấp bên dưới các thư mục con. Thực tế các thư mục con **được phát hiện** ở depth 1, nhưng **không mở** để duyệt cháu của chúng.
- Tưởng `maxDepth=0` sẽ không thấy gì. Theo hợp đồng `Files.walk`, stream vẫn chứa **phần tử start**, nếu việc truy cập start được cho phép.

**Giới hạn độ sâu không có nghĩa số lượng mục tối đa.** Một thư mục có hàng triệu tệp con vẫn có thể tạo lượng công việc rất lớn với `maxDepth=1`. `maxDepth` cũng không phải giới hạn kích thước byte hay thời gian chạy.

### 2.1. Giá trị âm

`Files.walk(start, -1)` và `Files.walkFileTree(start, options, -1, visitor)` ném `IllegalArgumentException`: `maxDepth` phải không âm. Nếu giá trị đến từ cấu hình/người dùng, hãy kiểm tra trước thay vì coi số âm là “không giới hạn”.

## 3. `Files.walk`: duyệt bằng một Stream có giới hạn

Cú pháp:

~~~java
try (Stream<Path> stream = Files.walk(start, 2)) {
    stream.forEach(System.out::println);
}
~~~

Đoạn minh họa cần import `java.nio.file.Files`, `Path`, `java.util.stream.Stream` và xử lý `IOException`.

**Hợp đồng chính:**

- Trả `Stream<Path>`, bao gồm `start`.
- Stream được **populate lười** (*lazy*) theo chiều sâu (*depth-first*) trong lúc tiêu thụ.
- Mặc định **không theo symbolic links**.
- Có thể truyền `FOLLOW_LINKS` nếu muốn duyệt vào target của symbolic link tới thư mục.
- Thứ tự các mục con **không được bảo đảm** theo bảng chữ cái. Khi cần kết quả tái lập được cho bài test, có thể `sorted()` sau khi chuyển sang tên ổn định.
- Stream giữ các directory resource đang mở; **phải đóng bằng try-with-resources**.
- Stream **weakly consistent**, không đóng băng cây; thay đổi diễn ra trong lúc duyệt có thể được phản ánh hoặc không.
- Lỗi I/O khi mở `start` có thể được ném dưới dạng checked `IOException`; nếu phát sinh trong quá trình lazy iteration sau khi phương thức trả về, có thể được bọc thành `UncheckedIOException`.

Ví dụ lọc **file thường** trong hai cấp:

~~~java
try (Stream<Path> entries = Files.walk(start, 2)) {
    List<Path> regularFiles = entries
            .filter(p -> Files.isRegularFile(p, LinkOption.NOFOLLOW_LINKS))
            .toList();
}
~~~

Đây là **đoạn minh họa**; `List`, `LinkOption` phải được import và `start` có trước. `Files.isRegularFile` thực hiện kiểm tra thuộc tính tại thời điểm gọi; cây tệp có thể thay đổi khi đang duyệt. Với yêu cầu xét attributes hiệu quả hơn, `Files.find` cung cấp sẵn `BasicFileAttributes` cho predicate.

### 3.1. Đóng Stream dù chỉ lấy một phần

Ngay cả với `limit(10)` hoặc `findFirst()`, vẫn phải đóng stream:

~~~java
try (Stream<Path> entries = Files.walk(start, 3)) {
    entries.limit(10).forEach(System.out::println);
}
~~~

Đây là ví dụ minh họa. `limit(10)` chỉ giới hạn **số phần tử trả ra** cho pipeline; nó không thay thế `maxDepth` và không cho một hàng rào bảo mật. `findFirst()` hoặc `limit(...)` cũng không tự đóng stream có tài nguyên I/O.

### 3.2. `Files.find` khi cần lọc theo thuộc tính

~~~java
try (Stream<Path> matches = Files.find(
        start, 2,
        (path, attrs) -> attrs.isRegularFile())) {
    matches.forEach(System.out::println);
}
~~~

Đây là đoạn minh họa, cần `start` và import `Stream`, `Path`, `Files`. `Files.find` duyệt tương tự `Files.walk`, nhưng nhận `BiPredicate<Path, BasicFileAttributes>`. Nó có thể tránh việc đọc lại attributes trong bước `filter`. Quy tắc **maxDepth**, mặc định **không theo link**, lỗi I/O và **đóng Stream** vẫn cần ghi nhớ.

Dù dùng `find`, việc kiểm tra attributes cũng chỉ là một quan sát: file có thể bị sửa/xóa/thay link ngay sau đó, nên thao tác đọc hoặc ghi thực tế vẫn cần xử lý exception.

## 4. `Files.walkFileTree`: dùng FileVisitor có kiểm soát callback

Hai overload chính:

~~~java
Files.walkFileTree(start, visitor);

// Có options và maxDepth:
Files.walkFileTree(start, options, maxDepth, visitor);
~~~

Đoạn minh họa; `visitor` là đối tượng triển khai `FileVisitor` hoặc lớp con của `SimpleFileVisitor`, `options` là `Set<FileVisitOption>`.

Khác với `Files.walk`:

- `walkFileTree` chủ động **gọi visitor** khi duyệt, không trả `Stream<Path>`.
- `preVisitDirectory(dir, attrs)` chạy trước khi đi vào các mục con của directory thực sự được mở ở mức thấp hơn giới hạn.
- `visitFile(file, attrs)` chạy với file hoặc các mục không duyệt xuống tiếp.
- `postVisitDirectory(dir, exc)` chạy sau khi hoàn thành traversal bên trong directory đã mở.
- `visitFileFailed(file, exc)` xử lý lỗi không đọc được thuộc tính, không mở được directory hoặc lỗi vòng lặp link.
- Visitor trả `FileVisitResult.CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS` hoặc `TERMINATE` để điều khiển công việc.
- Nếu callback ném `IOException` chưa xử lý, `walkFileTree` dừng và truyền exception cho caller. Callback mặc định của `SimpleFileVisitor.visitFileFailed` thường ném lại lỗi.

### 4.1. Chi tiết rất quan trọng ở đúng mức `maxDepth`

Theo Javadoc, với `Files.walkFileTree(start, options, maxDepth, visitor)`, **một thư mục ở chính depth = maxDepth được báo qua `visitFile`**, chứ **không** qua `preVisitDirectory` để duyệt con.

Ví dụ cây:

~~~text
root/                     depth 0
└── team/                 depth 1
    └── deep/             depth 2
        └── details.txt   depth 3
~~~

Nếu gọi `walkFileTree(root, emptyOptions, 2, visitor)`:

- `root` (depth 0) và `team` (depth 1) được gọi `preVisitDirectory`.
- `deep` (depth 2) **không** được mở để duyệt, nhưng được gọi `visitFile`; attributes của nó có thể có `attrs.isDirectory() == true`.
- `details.txt` (depth 3) **không** được duyệt.

Đây là điểm khác với ngộ nhận “`visitFile` chỉ có thể nhận regular file”. Tại ranh giới maxDepth, `visitFile` **có thể nhận directory**.

Muốn biết loại phần tử, dùng `BasicFileAttributes` mà callback cung cấp. Khi viết logic copy/xóa, đừng xử lý mọi `visitFile` như file thường mà không kiểm tra.

### 4.2. Có thể bỏ qua một nhánh cụ thể bằng `SKIP_SUBTREE`

Ví dụ minh họa trong một `SimpleFileVisitor<Path>`:

~~~java
@Override
public FileVisitResult preVisitDirectory(
        Path dir, BasicFileAttributes attrs) throws IOException {
    if (!dir.equals(start)
            && dir.getFileName().toString().equals(".git")) {
        return FileVisitResult.SKIP_SUBTREE;
    }
    return FileVisitResult.CONTINUE;
}
~~~

Đây là **callback minh họa**, không phải một class độc lập: cần biến `Path start` trong phạm vi phù hợp. `SKIP_SUBTREE` giúp bỏ một directory và các con của nó, bổ sung cho giới hạn `maxDepth` toàn cục. Nếu muốn bỏ **các thư mục anh em còn lại**, dùng `SKIP_SIBLINGS` theo hợp đồng visitor; `TERMINATE` dừng traversal.

**Không tự suy luận:** `SKIP_SUBTREE` không giới hạn các nhánh khác trừ khi callback trả trạng thái tương ứng. `maxDepth` mới là giới hạn độ sâu chung.

## 5. Chương trình Java 21 hoàn chỉnh: kiểm tra depth và callback ở ranh giới

Ví dụ sau **không cần quyền tạo symlink**, nên chạy được trên filesystem bình thường. Chương trình tạo riêng một cây tạm, ghi vài file mẫu, duyệt ở các mức `0–3`, lọc regular files bằng `Files.find`, ghi lại callback của `walkFileTree` ở depth 2, kiểm tra đầu vào âm, rồi dọn file tạm đã tạo.

Để stdout giống nhau trên Windows/Linux, code dùng `root.relativize(path)`, thay dấu phân cách thành `/` **chỉ để in**, và `sorted()` **chỉ để ổn định thứ tự trình bày**. Bản thân traversal không hứa sắp xếp theo tên.

Tạo file `src/main/java/demo/TreeDepthExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.stream.Stream;

public final class TreeDepthExample {
    private TreeDepthExample() {}

    private static String label(Path root, Path path) {
        if (root.equals(path)) {
            return ".";
        }
        return root.relativize(path).toString().replace('\\', '/');
    }

    static List<String> walkNames(Path root, int maxDepth) throws IOException {
        try (Stream<Path> entries = Files.walk(root, maxDepth)) {
            return entries.map(p -> label(root, p)).sorted().toList();
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("tree-depth-");
        Path team = root.resolve("team");
        Path deep = team.resolve("deep");
        try {
            Files.createDirectories(deep);
            Files.writeString(root.resolve("root.txt"), "root", StandardCharsets.UTF_8);
            Files.writeString(team.resolve("member.txt"), "member", StandardCharsets.UTF_8);
            Files.writeString(deep.resolve("details.txt"), "details", StandardCharsets.UTF_8);

            System.out.println("depth0=" + walkNames(root, 0));
            System.out.println("depth1=" + walkNames(root, 1));
            System.out.println("depth2=" + walkNames(root, 2));
            System.out.println("depth3=" + walkNames(root, 3));

            try (Stream<Path> files = Files.find(root, 2,
                    (path, attrs) -> attrs.isRegularFile())) {
                List<String> found = files.map(p -> label(root, p)).sorted().toList();
                System.out.println("regular2=" + found);
            }

            List<String> events = new ArrayList<>();
            boolean[] boundaryWasVisitFile = {false};
            Files.walkFileTree(root,
                    EnumSet.noneOf(FileVisitOption.class),
                    2,
                    new SimpleFileVisitor<>() {
                        @Override
                        public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                            events.add("D:" + label(root, dir));
                            return FileVisitResult.CONTINUE;
                        }

                        @Override
                        public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                            events.add("F:" + label(root, file));
                            if (file.equals(deep) && attrs.isDirectory()) {
                                boundaryWasVisitFile[0] = true;
                            }
                            return FileVisitResult.CONTINUE;
                        }
                    });
            System.out.println("visitorDepth2=" + events.stream().sorted().toList());
            System.out.println("boundaryDirViaVisitFile=" + boundaryWasVisitFile[0]);

            try {
                Files.walk(root, -1);
            } catch (IllegalArgumentException ex) {
                System.out.println("negativeDepth=IllegalArgumentException");
            }
        } finally {
            try (Stream<Path> cleanup = Files.walk(root)) {
                for (Path path : cleanup.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

Dùng JDK 21 từ thư mục chứa `src/`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/TreeDepthExample.java
java -cp out demo.TreeDepthExample
~~~

**Stdout chính xác** trên môi trường filesystem được kiểm thử:

~~~text
depth0=[.]
depth1=[., root.txt, team]
depth2=[., root.txt, team, team/deep, team/member.txt]
depth3=[., root.txt, team, team/deep, team/deep/details.txt, team/member.txt]
regular2=[root.txt, team/member.txt]
visitorDepth2=[D:., D:team, F:root.txt, F:team/deep, F:team/member.txt]
boundaryDirViaVisitFile=true
negativeDepth=IllegalArgumentException
~~~

### Giải thích chi tiết output

1. **`depth0=[.]`:** `Files.walk(root,0)` chỉ trả lại chính `root`. Hàm `label` hiển thị nó thành `.`.
2. **`depth1`:** thêm file `root.txt` và directory `team`. Chưa vào `team` để thấy `member.txt`.
3. **`depth2`:** thêm `team/member.txt` và `team/deep`. Directory `deep` ở ranh giới được thấy nhưng con `details.txt` chưa xuất hiện.
4. **`depth3`:** thêm `team/deep/details.txt` vì lúc này được phép đi xuống mức 3.
5. **`regular2`:** `Files.find(root,2, (p,attrs) -> attrs.isRegularFile())` chỉ lấy hai regular file ở mức không quá 2, bỏ directories.
6. **`visitorDepth2`:** `D` là callback `preVisitDirectory`, `F` là callback `visitFile`. `team/deep` là directory nhưng vẫn đi qua `visitFile` ở mức tối đa.
7. **`boundaryDirViaVisitFile=true`:** chương trình xác nhận thuộc tính `isDirectory()` của `team/deep` trong `visitFile`; không được cho rằng visitor chỉ gửi file thường.
8. **`negativeDepth=IllegalArgumentException`:** giá trị depth âm bị bác bỏ.

Đây là bài test **có kiểm soát**, không cố tình tạo symlink hoặc vòng lặp nguy hiểm. Thứ tự in được `sorted()` sau traversal, vì thứ tự filesystem entries không phải điều cần kiểm chứng ở đây.

## 6. Mặc định **không theo symbolic link**

**Symbolic link** là một đối tượng filesystem chứa đường dẫn tới một file hoặc directory khác. Khi phát hiện symlink tới thư mục, chương trình có hai lựa chọn khác biệt:

- **Không theo link (mặc định):** symlink có thể xuất hiện như một phần tử trong kết quả, nhưng **không duyệt vào các con của thư mục đích** thông qua nó.
- **Theo link (`FOLLOW_LINKS`):** traversal có thể đi qua symlink vào directory target, rồi tiếp tục duyệt sâu, trong phạm vi `maxDepth`.

Ví dụ:

~~~text
/work/root/
  link -> /other/archive/
               record.json
~~~

Đây là sơ đồ ý nghĩa, không phải cú pháp tạo symlink của Java. Nếu `start=/work/root`:

| Lời gọi | Kết quả liên quan tới link |
| --- | --- |
| `Files.walk(start, 1)` | Có thể thấy `link` ở depth 1; không thấy `link/record.json` |
| `Files.walk(start, 2)` | Vẫn không đi qua link nếu không bật FOLLOW_LINKS |
| `Files.walk(start, 1, FOLLOW_LINKS)` | Thấy `link` tại depth 1; không có chỗ để đi vào con vì đã chạm giới hạn |
| `Files.walk(start, 2, FOLLOW_LINKS)` | Có thể thấy `link/record.json` tại depth 2 |
| `Files.walkFileTree(start, Set.of(FOLLOW_LINKS), 2, visitor)` | Có thể vào thư mục đích qua link và gọi visitor cho con ở depth 2 |

Kết quả thực tế cần file/link tồn tại, provider hỗ trợ link và quyền truy cập đủ. **`FOLLOW_LINKS` không xóa giới hạn độ sâu**; nó chỉ thay quyết định đi qua link.

### 6.1. Cú pháp cấu hình đúng cho hai API

Với `Files.walk`, tùy chọn là **varargs `FileVisitOption...`**:

~~~java
try (Stream<Path> entries = Files.walk(
        start, 2, FileVisitOption.FOLLOW_LINKS)) {
    entries.forEach(System.out::println);
}
~~~

Với `Files.walkFileTree`, tùy chọn là **`Set<FileVisitOption>`**:

~~~java
Files.walkFileTree(
        start,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        2,
        visitor);
~~~

Đây đều là đoạn minh họa với biến đầu vào phù hợp và xử lý `IOException`.

**Không nhầm:** `LinkOption.NOFOLLOW_LINKS` dùng cho các API hỏi thuộc tính/đường dẫn hỗ trợ `LinkOption` (ví dụ `Files.isDirectory`, `Files.readAttributes` hoặc `Path.toRealPath`). Nó **không phải** `FileVisitOption` truyền cho `Files.walk`. Với traversal, **mặc định đã là không theo link**; `FileVisitOption` công khai trên Java 21 chỉ có `FOLLOW_LINKS`.

### 6.2. `Files.isDirectory` và quan sát symlink

Với `link` trỏ tới một directory tồn tại:

~~~java
boolean directoryThroughLink = Files.isDirectory(link);
boolean linkItselfIsDirectory =
        Files.isDirectory(link, LinkOption.NOFOLLOW_LINKS);
boolean symbolicLink = Files.isSymbolicLink(link);
~~~

Đây là đoạn minh họa, cần `Path link`. Thông thường:

- `directoryThroughLink` là `true` vì kiểm tra mặc định theo link tới target directory.
- `linkItselfIsDirectory` là `false` vì khi không theo link, đối tượng được xét là symlink, không phải directory thường.
- `symbolicLink` là `true`.

Chú ý: đây là các kết quả kiểm tra **tại thời điểm gọi**; link/target có thể thay đổi trước khi duyệt hoặc trước khi mở file.

## 7. Chương trình Java 21 tùy chọn: kiểm tra link trỏ ra ngoài cây bắt đầu

Phần này cần filesystem và tài khoản có **quyền tạo symbolic link**. Một số môi trường Windows hoặc filesystem không hỗ trợ; chương trình **bỏ qua riêng bài thử link** nếu tạo link không thành công, không giả vờ đã xác minh hành vi follow trong trường hợp đó.

Ví dụ tạo một vùng tạm gồm `start/` và `outside/`, đặt file `secret.txt` trong `outside/`, rồi tạo `start/alias` làm symlink tới `outside/`. Cả hai thư mục đều ở **vùng tạm do chương trình tạo**, nhưng `outside` nằm **ngoài root traversal `start`**.

Tạo file `src/main/java/demo/SymlinkDepthExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitOption;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public final class SymlinkDepthExample {
    private SymlinkDepthExample() {}

    static List<String> names(Path root, int depth, FileVisitOption... options)
            throws IOException {
        try (Stream<Path> entries = Files.walk(root, depth, options)) {
            return entries.map(p -> root.equals(p)
                    ? "." : root.relativize(p).toString().replace('\\', '/'))
                    .sorted()
                    .toList();
        }
    }

    public static void main(String[] args) throws IOException {
        Path space = Files.createTempDirectory("walk-link-");
        Path start = space.resolve("start");
        Path outside = space.resolve("outside");
        try {
            Files.createDirectories(start);
            Files.createDirectories(outside);
            Files.writeString(outside.resolve("secret.txt"), "data", StandardCharsets.UTF_8);

            Path link = start.resolve("alias");
            boolean supported = true;
            try {
                Files.createSymbolicLink(link, outside);
            } catch (UnsupportedOperationException | SecurityException | IOException ex) {
                supported = false;
            }

            if (!supported) {
                System.out.println("symlinks=unavailable");
            } else {
                System.out.println("nofollow-depth2=" + names(start, 2));
                System.out.println("follow-depth1="
                        + names(start, 1, FileVisitOption.FOLLOW_LINKS));
                System.out.println("follow-depth2="
                        + names(start, 2, FileVisitOption.FOLLOW_LINKS));
                System.out.println("is-link=" + Files.isSymbolicLink(link));
                System.out.println("is-dir-follow=" + Files.isDirectory(link));
                System.out.println("is-dir-no-follow="
                        + Files.isDirectory(link, LinkOption.NOFOLLOW_LINKS));
                System.out.println("outside-when-followed="
                        + !link.resolve("secret.txt").toRealPath()
                                .startsWith(start.toRealPath()));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(space)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

Chạy tương tự bài chính:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/SymlinkDepthExample.java
java -cp out demo.SymlinkDepthExample
~~~

**Nếu tạo symbolic link không được phép trong môi trường thử nghiệm**, output là:

~~~text
symlinks=unavailable
~~~

Đây cũng là kết quả tại môi trường Windows dùng để kiểm thử ví dụ này: biên dịch sạch và kết thúc an toàn, **không** tuyên bố đã duyệt symlink thật.

**Nếu filesystem cho phép tạo và theo symlink** như mô tả, output của các thao tác liên quan là:

~~~text
nofollow-depth2=[., alias]
follow-depth1=[., alias]
follow-depth2=[., alias, alias/secret.txt]
is-link=true
is-dir-follow=true
is-dir-no-follow=false
outside-when-followed=true
~~~

Cần phân biệt: trường hợp trên là **kỳ vọng theo cấu trúc test khi link thực sự được tạo**, không phải stdout đã quan sát ở môi trường không cấp quyền tạo link.

Ý nghĩa: mặc định không theo link nên chỉ thấy `alias`; bật `FOLLOW_LINKS` và cho phép depth 2 thì thấy thêm `alias/secret.txt`. Mục tiêu thật của đường dẫn đó **nằm ngoài `start`**, dù tên trả về do `root.relativize(...)` trông như một file con.

## 8. Theo liên kết có thể tạo **chu trình**

Giả sử:

~~~text
root/
  dir/
    back -> root/
~~~

Nếu bật `FOLLOW_LINKS`, đường dẫn có thể tạo chuỗi `root/dir/back/dir/back/...` nếu traversal không phát hiện chu trình.

Theo Javadoc, khi `FOLLOW_LINKS` được bật, Java theo dõi tổ tiên của các thư mục đã duyệt để phát hiện **vòng lặp tới directory tổ tiên**. Nó có thể dùng `file-key` hoặc `Files.isSameFile` nếu key không có sẵn.

- Với `Files.walkFileTree`, một chu trình được báo tới callback `visitFileFailed` bằng `FileSystemLoopException`.
- Với `Files.walk` / `Files.find`, lỗi I/O phát sinh trong quá trình lazy iteration có thể xuất hiện dưới dạng `UncheckedIOException`, trong đó cause là `FileSystemLoopException`.
- Việc phát hiện chu trình giúp traversal không cứ thế đi vô hạn qua tổ tiên, nhưng **không bảo đảm** mọi đồ thị link với nhiều đường trỏ chéo sẽ được duyệt **chỉ một lần**. Một file hoặc directory ngoài tổ tiên có thể được đi tới bằng các alias khác nhau.

Ví dụ minh họa trong visitor:

~~~java
@Override
public FileVisitResult visitFileFailed(Path file, IOException exc)
        throws IOException {
    if (exc instanceof FileSystemLoopException) {
        System.err.println("Cycle: " + file);
        return FileVisitResult.CONTINUE;
    }
    throw exc;
}
~~~

Đây là **callback minh họa**, cần import `FileSystemLoopException`, `IOException`, `Path`, `FileVisitResult` và đặt bên trong lớp extends `SimpleFileVisitor<Path>`. Chỉ tiếp tục (`CONTINUE`) nếu chính sách ứng dụng cho phép bỏ qua chu trình; các lỗi truy cập khác nên được báo hoặc xử lý minh bạch.

**Không dùng `FOLLOW_LINKS` một cách vô điều kiện trong chương trình copy, xóa hoặc scan file untrusted.** Nó có thể đưa traversal ra khỏi directory gốc; việc phát hiện vòng lặp **không thay thế** chính sách an toàn phạm vi.

## 9. `maxDepth` **không phải sandbox**

Một hiểu nhầm nguy hiểm là: “Đã giới hạn depth 2 thì chắc chắn không thể truy cập dữ liệu bên ngoài thư mục tôi chọn.”

Sai. Nếu `start/alias` là symlink tới `/outside`, bật `FOLLOW_LINKS` cho phép đạt tới `alias/file` ở depth 2 dù **đích thực** nằm ở ngoài `start`. Độ sâu mô tả **mức duyệt qua các đường dẫn theo traversal**, không phải kiểm tra ranh giới real path của filesystem.

Vì vậy, khi xử lý dữ liệu không tin cậy:

1. Xác định rõ có cần follow symlink hay không. **Mặc định không theo** thường là lựa chọn an toàn hơn cho việc lập chỉ mục/copy/xóa cây mà bạn không muốn đi ra ngoài phạm vi dự kiến.
2. Nếu bắt buộc follow, cần định nghĩa **phạm vi real directory** hợp lệ, kiểm tra link target và quyền truy cập trong kiến trúc thao tác file thực tế.
3. Không xem `Path.normalize()` hoặc `Path.startsWith(root)` trên đường dẫn lexical là chứng minh một path không thoát root.
4. Nếu attacker có thể thay đổi link giữa kiểm tra và mở file, có thể xảy ra **TOCTOU**. `toRealPath` cũng chỉ xác minh ở thời điểm gọi; cần cơ chế bảo vệ mạnh hơn như permission isolation/directory-handle APIs trong môi trường phù hợp.
5. `maxDepth` không phải giới hạn số mục, CPU, tổng bytes hoặc thời gian chạy. Nếu cần *budget*, thêm đếm mục/size/thời gian và chính sách dừng riêng.

### 9.1. Đọc/copy/xóa cây có mục tiêu khác nhau

- **Duyệt để hiển thị:** có thể liệt kê symlink như một entry mà không cần follow.
- **Tìm file:** cần chính sách rõ ràng về việc có tính target của link và có cho cùng file xuất hiện qua nhiều alias không.
- **Copy cây:** nếu follow, phải quyết định copy nội dung target hay bản thân link, rủi ro vượt root, cycles và metadata. Không suy ra từ tên.
- **Xóa cây:** việc follow link có thể dẫn tới duyệt và xóa nội dung **ngoài** thư mục muốn dọn. Không sao chép máy móc ví dụ walker có `FOLLOW_LINKS` vào code xóa production.

**Một lựa chọn API không thay thế policy bảo mật.** Dù Java phát hiện ancestor loops, nó không xác định hộ bạn đâu là dữ liệu được phép đọc/xóa.

## 10. Xử lý IOException khác nhau giữa Stream và FileVisitor

### 10.1. `Files.walk` và `Files.find`

Cần tách hai giai đoạn:

~~~java
try (Stream<Path> paths = Files.walk(start, 3)) {
    paths.forEach(System.out::println);
}
~~~

Đây là đoạn minh họa. `Files.walk(...)` có thể ném checked `IOException` ngay lúc tạo stream nếu có lỗi truy cập start. Sau khi tạo thành công, thao tác `forEach` có thể ném **`UncheckedIOException`** khi lỗi xảy ra trong quá trình lazy iteration.

Mẫu xử lý có phân biệt:

~~~java
try (Stream<Path> paths = Files.walk(start, 3)) {
    paths.forEach(System.out::println);
} catch (UncheckedIOException ex) {
    IOException cause = ex.getCause();
    // Xử lý lỗi I/O phát sinh trong lúc duyệt lười.
} catch (IOException ex) {
    // Xử lý lỗi mở start / các lỗi checked từ Files.walk/close.
}
~~~

Đây là đoạn minh họa, cần import `java.io.UncheckedIOException` và `java.io.IOException`. Tùy use case, có thể để các lỗi truyền lên thay vì bắt ngay trong pipeline.

**Không quên try-with-resources:** ngay cả khi `Stream` ném lỗi trong terminal operation, các directory handles nó sở hữu vẫn cần được đóng kịp thời.

### 10.2. `Files.walkFileTree`

Với visitor:

~~~java
Files.walkFileTree(start, options, maxDepth, new SimpleFileVisitor<>() {
    @Override
    public FileVisitResult visitFileFailed(Path file, IOException exc)
            throws IOException {
        throw exc;
    }
});
~~~

Đây là đoạn minh họa. Khi lỗi thuộc tính, mở directory hoặc symlink loop, visitor có thể quyết định:

- **Báo lỗi:** ném lại `exc`.
- **Bỏ qua có chủ đích:** log/ghi nhận và trả `CONTINUE` nếu chính sách cho phép.
- **Dừng traversal:** trả `TERMINATE` khi gặp trường hợp cần dừng.

Không bỏ mọi lỗi rồi coi kết quả là “đã quét đủ”. Bỏ lỗi quyền truy cập có thể làm mất file trong tập kết quả; quyết định này cần được thể hiện trong báo cáo/telemetry của ứng dụng.

### 10.3. `postVisitDirectory` và lỗi duyệt directory

Nếu không thể đọc hết các entry trong một directory, `postVisitDirectory(dir, exc)` có thể được gọi với `exc != null`. Một ứng dụng quét cần ghi nhận hoặc ném lại lỗi đó; đừng chỉ xử lý `visitFileFailed` rồi nghĩ toàn bộ traversal đã chắc chắn không lỗi.

## 11. Tối ưu phạm vi và hiệu năng

`maxDepth` là một công cụ để giảm vùng cần đi qua, nhưng chưa đủ để tối ưu mọi trường hợp:

| Nhu cầu | Gợi ý |
| --- | --- |
| Chỉ xem thư mục gốc | `Files.walk(root, 0)` |
| Chỉ xem trực tiếp mục con | `Files.walk(root, 1)` |
| Chỉ xem hai cấp con | `Files.walk(root, 2)` |
| Cần attributes và lọc | `Files.find(root, depth, predicate)` |
| Cần bỏ thư mục `.git` và điều khiển callback | `walkFileTree` + `SKIP_SUBTREE` |
| Cần xử lý lỗi theo từng phần tử | `walkFileTree` + `visitFileFailed` |
| Có nhu cầu follow symlink thật sự | `FileVisitOption.FOLLOW_LINKS`, kèm chính sách real-path/cycle |
| Chỉ muốn symlink là một entry | Không truyền `FOLLOW_LINKS` |
| Chỉ muốn một số lượng kết quả | `limit(n)` hoặc bộ đếm riêng; **không thay `maxDepth`** |
| Muốn bỏ tất cả file ngoài thư mục được phép | Không chỉ dựa vào depth; cần thiết kế access giới hạn thật |

Đừng dùng `Files.walk(root, Integer.MAX_VALUE)` làm mặc định mọi lúc. Với cây lớn, có thể phát sinh chi phí lớn và giữ open directories trong lúc stream được tiêu thụ. Nếu không cần đi sâu, đặt maxDepth nhỏ nhất phù hợp.

### 11.1. Thứ tự duyệt và thứ tự hiển thị

Traversal là **depth-first** nhưng Javadoc không cam kết danh sách entry của mỗi directory được sắp theo tên. Trong test, `sorted()` giúp có stdout tái lập được; trong ứng dụng sản xuất, `sorted()` trên một stream có thể cần giữ nhiều phần tử trước khi xuất, tốn bộ nhớ.

Nếu dữ liệu rất lớn và cần thứ tự, cân nhắc sắp thứ tự từng thư mục theo use case hoặc lưu kết quả ra hệ thống index; không mặc định toàn bộ cây vừa đủ nhỏ để `sorted().toList()`.

### 11.2. Cây thay đổi trong lúc đang quét

`Files.walk` là **weakly consistent**, không tạo snapshot bất biến. Một file vừa được tạo có thể xuất hiện hoặc không, một file vừa xóa có thể gây lỗi hoặc không còn được thấy. Vì vậy:

- Không dùng một lần walk để cam kết danh mục file đã hoàn chỉnh dưới concurrent writes, trừ khi storage có snapshot/locking phù hợp.
- Khi mở một file được walker trả về, vẫn xử lý `IOException`: file có thể biến mất hoặc bị thay đổi.
- Không coi `Files.isDirectory(path)` trước traversal là bảo đảm directory sẽ còn tồn tại.

## 12. Edge cases và các hiểu nhầm quan trọng

**Trường hợp 1 — `maxDepth=0`.** Stream chỉ có `start`. Với `walkFileTree`, một directory là `start` ở độ sâu 0 được gửi qua `visitFile` ở ranh giới, không vào `preVisitDirectory` để duyệt con.

**Trường hợp 2 — `maxDepth=1`.** Stream chứa `start` và các con trực tiếp. Link directory tại depth 1 vẫn xuất hiện nhưng không được vào con, kể cả khi bật `FOLLOW_LINKS`.

**Trường hợp 3 — link tới file thường.** Dù theo link, link tới file không trở thành directory; traversal không có “các con” để đi sâu. Việc muốn biết link là symbolic link hay thuộc tính của target là một câu hỏi về ``FileVisitOption` và `LinkOption` phù hợp.

**Trường hợp 4 — dangling symlink.** Khi `FOLLOW_LINKS` nhưng target không thể đọc, Javadoc cho biết walker thử lấy attributes của **bản thân link**; nếu lấy được thì có thể gọi `visitFile` cho link, không nhất thiết luôn ném `NoSuchFileException` ngay. Trường hợp không thể lấy attributes thì `visitFileFailed` hoặc lỗi iteration xảy ra theo API.

**Trường hợp 5 — symlink loop.** Bật `FOLLOW_LINKS` có thể dẫn tới `FileSystemLoopException`. Với walker Stream, lỗi có thể được wrap trong `UncheckedIOException`; với visitor, nó được báo qua `visitFileFailed`.

**Trường hợp 6 — đường dẫn bắt đầu không tồn tại.** `Files.walk` có thể ném `IOException` khi truy cập start. `Files.walkFileTree` có thể báo lỗi qua visitor. Đừng giả định mọi lần walk đều trả một stream rỗng.

**Trường hợp 7 — depth âm.** `IllegalArgumentException` chứ không phải yêu cầu “toàn bộ cây”.

**Trường hợp 8 — chỉ số depth không giới hạn số item.** Một triệu file ngay dưới root có thể được tìm thấy ở depth 1. Hãy đặt resource budget riêng nếu cần.

**Trường hợp 9 — filesystem provider và quyền.** Có môi trường không cho tạo symbolic links, hoặc không hỗ trợ chúng. Code không nên thất bại chỉ vì một ví dụ phụ cần quyền đặc biệt; tách test symlink optional và phân biệt trường hợp test bị bỏ qua với trường hợp follow-links đã xác nhận.

**Trường hợp 10 — non-follow không đồng nghĩa “chống mọi race”.** Nếu một actor có thể thay đường dẫn trong lúc duyệt, bất kỳ thao tác file nào cũng cần xử lý tính biến động và policy an toàn tương ứng.

## 13. Lỗi phổ biến và cách sửa

| Sai lầm | Điều thực sự xảy ra | Cách đúng |
| --- | --- | --- |
| Nghĩ depth 0 là “không duyệt gì” | `start` vẫn được xét | Nhớ start ở level 0 |
| Nghĩ depth 2 là “đi thêm 2 cấp dưới cháu” | Mức 0 là start, mức 1 con, mức 2 cháu | Vẽ cây và đánh level |
| Duyệt `walkFileTree` mà chỉ xử lý regular file trong `visitFile` | Directory ở đúng `maxDepth` cũng vào `visitFile` | Kiểm tra `attrs.isDirectory()` |
| Nghĩ walker tự theo symlink | Mặc định không theo | Chỉ bật `FOLLOW_LINKS` khi cần |
| Truyền `LinkOption.NOFOLLOW_LINKS` cho `Files.walk` | Sai kiểu option | Không truyền option để không theo link; `FileVisitOption.FOLLOW_LINKS` để theo |
| Dùng `FOLLOW_LINKS` nhưng không nghĩ đến loop | Có thể gặp `FileSystemLoopException` | Xử lý visitor failure hoặc `UncheckedIOException` |
| Tin maxDepth giữ dữ liệu trong root thật | Symlink có thể đưa tới file ngoài root | Thiết kế real-directory security riêng |
| Quên đóng `Files.walk`/`find` Stream | Giữ directory resources mở | `try-with-resources` |
| Chỉ catch `IOException` sau khi stream đã tạo | Lazy iteration có thể ném `UncheckedIOException` | Phân biệt hai giai đoạn |
| Nghĩ traversal luôn theo thứ tự ABC | Không có bảo đảm tên sorted | Sort có chủ đích nếu cần |
| Tin tập tệp không đổi trong lúc walk | Stream weakly consistent | Snapshot/locking/bắt lỗi khi cần |
| Dùng `find` nhưng bỏ qua attrs có sẵn | Có thể đọc lại thuộc tính không cần thiết | Sử dụng `BasicFileAttributes` trong predicate |
| Dùng `maxDepth` để giới hạn số file hoặc byte | Không giải quyết resource budget | Thêm giới hạn riêng về count/size/time |
| Quên xử lý lỗi trong `postVisitDirectory` | Có thể hiểu nhầm scan đã hoàn tất | Xem `exc` và báo lỗi khi cần |
| Theo link lúc xóa cây tệp tùy ý | Có thể ảnh hưởng nội dung ngoài root | Không follow trừ khi thật sự an toàn và được cho phép |

## 14. Bài tập và đáp án

**Bài 1.** Một cây có `root/a/b/file.txt`, root ở depth 0. `Files.walk(root, 2)` có trả `file.txt` không?

**Đáp án:** Không. `a` depth 1, `b` depth 2 và `file.txt` depth 3. Ở maxDepth 2, `b` có thể xuất hiện nhưng không được đi vào con.

**Bài 2.** `Files.walk(root, 0)` trả gì nếu root tồn tại và truy cập được?

**Đáp án:** Stream gồm chính `root`, không gồm mục con.

**Bài 3.** Một visitor giới hạn `maxDepth=2` nhận directory ở depth 2 qua callback nào?

**Đáp án:** `visitFile`, không phải `preVisitDirectory` cho directory đó; không duyệt con của nó.

**Bài 4.** Có thể dùng `LinkOption.NOFOLLOW_LINKS` làm tham số `FileVisitOption` của `Files.walk` không?

**Đáp án:** Không. Hai enum có mục đích khác nhau; `Files.walk` mặc định đã không theo link. Khi cần theo link, truyền `FileVisitOption.FOLLOW_LINKS`.

**Bài 5.** Nếu `root/alias` trỏ tới directory bên ngoài root, bật `FOLLOW_LINKS` và `maxDepth=2` có chắc dữ liệu vẫn nằm trong root thật không?

**Đáp án:** Không. Walker có thể tới `root/alias/file` ở depth 2, nhưng real path thực sự là file ở bên ngoài root. Depth không phải ranh giới bảo mật.

**Bài 6.** Một symlink ở depth 1 trỏ tới thư mục có file con. `FOLLOW_LINKS` bật nhưng `maxDepth=1` có thấy file con không?

**Đáp án:** Không. Link ở depth 1 được xét; không thể đi sâu hơn vì đã chạm giới hạn.

**Bài 7.** `FileSystemLoopException` xảy ra khi nào và xử lý ra sao?

**Đáp án:** Có thể xuất hiện khi bật `FOLLOW_LINKS` và gặp link đưa vào directory tổ tiên. `walkFileTree` báo qua `visitFileFailed`; `Files.walk` có thể ném `UncheckedIOException` lúc iterator chạy. Xử lý có chủ đích, không nuốt mọi lỗi.

**Bài 8.** Stream của `Files.walk` chỉ dùng `findFirst()` rồi bỏ, có cần đóng không?

**Đáp án:** Có. Stream giữ directory resources; luôn đóng bằng `try-with-resources` hoặc cơ chế tương đương.

**Bài 9.** `Files.find(root, depth, (path,attrs) -> attrs.isRegularFile())` hơn gì so với `Files.walk(...).filter(p -> Files.isRegularFile(p))`?

**Đáp án:** `Files.find` đưa sẵn `BasicFileAttributes` vào predicate, có thể tránh đọc lại attributes. Vẫn cần đóng stream và xử lý I/O.

**Bài 10.** `maxDepth=1` có đảm bảo duyệt tối đa 10 file không?

**Đáp án:** Không. Nó chỉ giới hạn cấp; root có thể chứa số lượng file trực tiếp rất lớn. Cần giới hạn count/bytes/time riêng.

**Bài 11.** Có nên dùng `FOLLOW_LINKS` mặc định cho công cụ xóa thư mục do người dùng chỉ định không?

**Đáp án:** Không. Link có thể dẫn ra ngoài cây được chọn. Nếu không có chính sách đặc biệt cho phép, nên giữ mặc định không theo link và thiết kế thao tác xóa an toàn trước symlink/race.

## 15. Checklist và tài liệu chính thức

- [ ] Xác định `start` là depth 0 và chọn `maxDepth >= 0` đúng mức.
- [ ] Nhớ `Files.walk` trả cả start, không chỉ file con.
- [ ] Chọn `walk` / `find` khi muốn stream; `walkFileTree` khi cần callback và điều khiển subtree/error.
- [ ] Ở ranh giới `maxDepth` của `walkFileTree`, xét directory trong `visitFile` bằng attributes.
- [ ] Mặc định không theo symlink; chỉ bật `FOLLOW_LINKS` khi thật sự cần.
- [ ] Không nhầm `FileVisitOption.FOLLOW_LINKS` với `LinkOption.NOFOLLOW_LINKS`.
- [ ] Nếu theo link, lên kế hoạch xử lý `FileSystemLoopException` và target nằm ngoài root.
- [ ] Đóng mọi stream `Files.walk`/`find` bằng `try-with-resources`.
- [ ] Phân biệt checked `IOException` lúc mở với `UncheckedIOException` khi lazy iteration.
- [ ] Không coi `maxDepth` là giới hạn số file/bytes/thời gian hay sandbox.
- [ ] Không tin vào thứ tự entry theo tên nếu chưa tự sắp xếp.
- [ ] Không mặc định traversal là snapshot bất biến của filesystem.
- [ ] Với bộ công cụ copy/xóa, kiểm soát phạm vi thực, symlink và quyền truy cập bằng policy riêng.
- [ ] Chạy bài Java 21 để quan sát depth 0–3 và optional symlink test nếu provider hỗ trợ.

**Tài liệu chính thức (API vẫn áp dụng trên Java hiện đại):**

- [Java SE 21 — Files.walk](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#walk(java.nio.file.Path,int,java.nio.file.FileVisitOption...)): độ sâu, stream lười, FOLLOW_LINKS và lỗi duyệt.
- [Java SE 21 — Files.walkFileTree](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.util.Set,int,java.nio.file.FileVisitor)): callback, maxDepth, cycle handling và directory ở boundary.
- [Java SE 21 — Files.find](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#find(java.nio.file.Path,int,java.util.function.BiPredicate,java.nio.file.FileVisitOption...)): filter theo `BasicFileAttributes` và giới hạn độ sâu.
- [Java SE 21 — FileVisitOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitOption.html): enum `FOLLOW_LINKS`.
- [Java SE 21 — FileVisitResult](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileVisitResult.html): `CONTINUE`, `SKIP_SUBTREE`, `SKIP_SIBLINGS`, `TERMINATE`.
- [Java SE 21 — SimpleFileVisitor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/SimpleFileVisitor.html): callback mặc định và xử lý thất bại.
- [Java SE 21 — FileSystemLoopException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystemLoopException.html): lỗi chu trình khi theo link.
- [Java SE 21 — LinkOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/LinkOption.html): phân biệt chính sách không theo symlink khi kiểm tra thuộc tính/real path.

**Kết luận:** `maxDepth` định nghĩa **mức duyệt tính từ start**, còn `FOLLOW_LINKS` quyết định có đi qua symbolic link tới directory hay không. Giới hạn độ sâu giúp kiểm soát phạm vi logic, nhưng **không tự ngăn truy cập ngoài root qua symlink** và không thay thế kiểm soát lỗi, resource budget hay bảo mật. Với chương trình hiện đại, hãy dùng `Files.walk`/`find` có đóng stream, hoặc `walkFileTree` có visitor phù hợp, và chỉ theo link khi chính sách ứng dụng cho phép.
