# FOLLOW_LINKS, vòng liên kết và FileSystemLoopException trong Java

Khi duyệt cây thư mục với Java NIO.2, **symbolic link (liên kết tượng trưng)** có thể trỏ tới file, thư mục khác, thư mục nằm ngoài gốc duyệt, hoặc trỏ ngược về chính một tổ tiên. Nếu đi theo liên kết mà không hiểu cơ chế này, chương trình có thể đọc trùng dữ liệu, đi ra ngoài phạm vi dự kiến, gặp chu trình (*cycle*) hoặc nhận lỗi `FileSystemLoopException`.

Các API chủ yếu liên quan:

- `Files.walkFileTree(...)`: duyệt cây và gọi các callback của `FileVisitor`; hỗ trợ tùy chọn `FileVisitOption.FOLLOW_LINKS`.
- `Files.walk(...)` và `Files.find(...)`: tạo `Stream<Path>` và cũng có thể đi theo liên kết nếu truyền `FileVisitOption.FOLLOW_LINKS`.
- `FileSystemLoopException`: ngoại lệ khi quá trình duyệt phát hiện một vòng liên kết trong lúc cố đi theo symbolic link; cách nhận/lan truyền lỗi khác nhau giữa visitor và stream.
- `Files.isSymbolicLink(...)` và `LinkOption.NOFOLLOW_LINKS`: giúp kiểm tra **bản thân liên kết** thay vì mặc định xem thuộc tính của mục tiêu.

**Mặc định, Java không đi theo symbolic link khi duyệt cây với những API trên.** Chỉ bật `FOLLOW_LINKS` khi nghiệp vụ thực sự yêu cầu khám phá cả những thư mục được liên kết tới, và cần có chiến lược về quyền truy cập, giới hạn độ sâu, vòng liên kết và đường dẫn ngoài phạm vi.

## 1. Symbolic link là gì? Vì sao có vòng lặp?

Symbolic link là một entry của hệ thống tệp trỏ đến một đường dẫn khác. Nó không giống “sao chép thư mục”: đi theo symlink đưa chương trình tới mục tiêu hiện tại của liên kết. Symlink có thể trỏ tới file, thư mục hoặc đường dẫn đã mất (*dangling link*).

Ví dụ:

```text
workspace/
└── project/
    ├── README.md
    └── back -> workspace/      (symbolic link trỏ về tổ tiên)

Duyệt workspace/ có FOLLOW_LINKS:
workspace/
  -> project/
      -> back (trỏ lại workspace/)
          -> project/
              -> back
                  -> ...
```

Trên một cây thực không có vòng liên kết, duyệt sâu theo `project` rồi hết các file con là hữu hạn. Nhưng khi `back` đưa ta quay lại `workspace`, đường đi có thể lặp **vô hạn về mặt cấu trúc** nếu không có kiểm tra vòng.

Một ví dụ khác không phải vòng trực tiếp:

```text
safe-root/
└── shortcut -> /other/location/
```

Nếu bật `FOLLOW_LINKS`, chương trình có thể duyệt nội dung `/other/location`, dù vị trí đó **nằm ngoài thư mục gốc ban đầu**. Không có `FileSystemLoopException` không có nghĩa là đã giữ đúng ranh giới dữ liệu.

## 2. Mặc định không theo link khác gì khi bật FOLLOW_LINKS?

Với `Files.walkFileTree`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;

// Minh họa: root là Path đã xác định; xử lý IOException.
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {});
```

Overload này **không theo symbolic link**. Nếu gặp một symlink, visitor thông thường nhận nó ở `visitFile(...)` như một entry dạng file/leaf, kể cả khi nó trỏ tới thư mục. Không có việc tự động mở và duyệt thư mục đích qua liên kết.

Để yêu cầu đi theo symbolic link, dùng overload có tập tùy chọn:

```java
import java.nio.file.FileVisitOption;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.util.EnumSet;

// Minh họa: root là Path đã xác định; xử lý IOException.
Files.walkFileTree(
        root,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        new SimpleFileVisitor<Path>() {}
);
```

Hai điểm quan trọng:

1. `FileVisitOption.FOLLOW_LINKS` có nghĩa là **khi gặp liên kết tới thư mục, cố đi vào thư mục đích** thay vì chỉ xử lý bản thân entry link. Nếu đích không thể truy cập, chương trình phải xử lý lỗi thích hợp.
2. `Integer.MAX_VALUE` ở đây là `maxDepth`: số cấp tối đa tính từ root, **không phải** giới hạn số lượng file hay giới hạn bộ nhớ. Chỉ dùng giới hạn rất sâu khi đã hiểu quy mô dữ liệu. Nếu không cần theo link, nên để mặc định.

### Bảng so sánh

| Nội dung | Mặc định (không `FOLLOW_LINKS`) | Có `FOLLOW_LINKS` |
| --- | --- | --- |
| Symlink trỏ tới file | Xử lý bản thân liên kết như một entry | Cố truy cập file đích, nếu có thể |
| Symlink trỏ tới thư mục | Xem như entry lá, **không** duyệt thư mục đích | Cố duyệt thư mục đích |
| Symlink trỏ về tổ tiên | Không đi theo nên không tạo vòng duyệt từ link | Có thể phát hiện vòng và báo `FileSystemLoopException` |
| Symlink trỏ ra ngoài root | Không truy cập cây ngoài qua link | **Có thể** đi ra ngoài root |
| Dangling symlink | Có thể vẫn được xử lý như entry link | Cố theo đích; nếu không theo được, hành vi callback/phần tử có thể phản ánh link hoặc lỗi theo API |
| Khả năng truy cập lặp các entry | Hạn chế trùng từ các symlink | Có thể duyệt cùng dữ liệu qua nhiều đường liên kết |
| Rủi ro khi sử dụng để xóa cây | Thường dễ giới hạn hơn, vẫn cần quyền và kiểm tra | **Không nên bật tùy tiện**, có thể chạm đối tượng ngoài phạm vi |

**Không nhầm `FileVisitOption.FOLLOW_LINKS` với `LinkOption.NOFOLLOW_LINKS`.** Một bên là tùy chọn **duyệt** cây; một bên là tùy chọn được dùng trong **một số phương thức kiểm tra thuộc tính và đường dẫn** để không theo liên kết khi lấy thông tin.

## 3. `FileSystemLoopException` biểu thị điều gì?

`java.nio.file.FileSystemLoopException` là một subclass của `FileSystemException` và `IOException`, báo rằng hệ thống đang thực hiện thao tác có liên quan tới đường dẫn đã gặp **vòng trong cấu trúc hệ thống tệp**.

Khi `walkFileTree` có `FOLLOW_LINKS`, Java cần kiểm tra thư mục mới chuẩn bị đi vào có trùng một thư mục **tổ tiên của nhánh hiện tại** không. Việc nhận diện vòng thường dựa trên file key từ thuộc tính filesystem, và có thể dùng kiểm tra tương đương `Files.isSameFile(...)` khi cần.

Đừng suy luận rằng “hai đường dẫn có chuỗi khác nhau” thì chắc chắn là hai thư mục khác nhau. Symlink, hard link (đối với đối tượng được phép hard-link), mount hoặc cách provider biểu diễn tên có thể khiến nhiều tên tham chiếu tới cùng tài nguyên.

Trong `walkFileTree`, khi phát hiện chu trình do đi theo symlink, lỗi được cung cấp tới callback:

```java
@Override
public FileVisitResult visitFileFailed(
        Path file, IOException exc) throws IOException {
    if (exc instanceof FileSystemLoopException) {
        System.err.println("Đã phát hiện vòng tại: " + file);
        return FileVisitResult.CONTINUE;
    }
    throw exc;
}
```

Đây là **phương thức override minh họa** cần nằm bên trong `FileVisitor` hoặc `SimpleFileVisitor`, với import `Path`, `IOException`, `FileVisitResult` và `FileSystemLoopException`. Việc trả `CONTINUE` có nghĩa **không tiếp tục đi vào nhánh gây vòng**, nhưng tiếp tục duyệt những nhánh còn lại.

Nếu dùng `new SimpleFileVisitor<Path>() {}` và không override `visitFileFailed`, implementation mặc định ném lại `IOException` nhận được. Khi đó toàn bộ `walkFileTree` thường kết thúc bằng ngoại lệ ngay khi gặp vòng.

### `FileSystemLoopException` không bao quát mọi lỗi

Một lỗi ở entry khác có thể là:

- `AccessDeniedException` nếu bị từ chối quyền;
- `NoSuchFileException` nếu đường dẫn biến mất hoặc không thể truy cập theo trạng thái filesystem;
- `FileSystemException` khác nếu provider báo lỗi;
- `IOException` do I/O chung.

**Không phải mọi `IOException` đều là vòng liên kết.** Nếu chỉ muốn bỏ qua một vòng đã nhận diện, hãy xử lý riêng `FileSystemLoopException` và cho những lỗi khác lan ra ngoài (hoặc xử lý theo chính sách đã xác định).

## 4. Chương trình Java 17+ chạy độc lập

Ví dụ dưới đây tạo một thư mục tạm với một file và cố tạo một symlink từ thư mục con trỏ về thư mục gốc. Nếu môi trường cho phép tạo symbolic link, đây là một **vòng liên kết** thật. Ví dụ duyệt lần đầu **không** theo link, lần hai bật `FOLLOW_LINKS` và đếm callback `FileSystemLoopException`.

Một số hệ điều hành hoặc tài khoản (đặc biệt Windows không có quyền tạo symbolic link) có thể **không cho phép** tạo link. Chương trình vẫn chạy và in kết quả không có link, vì hành vi này phụ thuộc môi trường. Chỉ trong bài demo chúng ta mới bỏ qua lỗi tạo symlink để xem luồng duyệt không có link; ứng dụng thật phải phân biệt và xử lý lỗi theo nghiệp vụ.

Lưu thành file **`FollowLinksLoopDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystemLoopException;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;

public class FollowLinksLoopDemo {

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("java-follow-links-");
        Path child = Files.createDirectory(root.resolve("child"));
        Path file = child.resolve("note.txt");
        Path link = child.resolve("back-to-root");

        boolean linkCreated = false;

        try {
            Files.writeString(file, "Java", StandardCharsets.UTF_8);

            try {
                // Tạo vòng: child/back-to-root -> root.
                Files.createSymbolicLink(link, root);
                linkCreated = true;
            } catch (UnsupportedOperationException
                     | SecurityException | IOException unsupported) {
                // Riêng demo này vẫn chạy nếu không tạo được link.
            }

            final int[] linkLeaves = {0};
            Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult visitFile(
                        Path path, BasicFileAttributes attrs) {
                    if (Files.isSymbolicLink(path)) {
                        linkLeaves[0]++;
                    }
                    return FileVisitResult.CONTINUE;
                }
            });

            final int[] loopErrors = {0};
            Files.walkFileTree(
                    root,
                    EnumSet.of(FileVisitOption.FOLLOW_LINKS),
                    16,
                    new SimpleFileVisitor<Path>() {
                        @Override
                        public FileVisitResult visitFileFailed(
                                Path path, IOException exc)
                                throws IOException {
                            if (exc instanceof FileSystemLoopException) {
                                loopErrors[0]++;
                                return FileVisitResult.CONTINUE;
                            }
                            throw exc;
                        }
                    });

            System.out.println("Symlink created: " + linkCreated);
            System.out.println("No-follow link leaves: "
                    + linkLeaves[0]);
            System.out.println("Detected link loops: "
                    + loopErrors[0]);
            System.out.println("Traversal completed: true");
        } finally {
            // Chỉ xóa những entry do chính ví dụ tạo.
            Files.deleteIfExists(link);
            Files.deleteIfExists(file);
            Files.deleteIfExists(child);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 FollowLinksLoopDemo.java
java FollowLinksLoopDemo
```

**Stdout nếu môi trường cho phép tạo symlink và callback vòng được phát hiện:**

```text
Symlink created: true
No-follow link leaves: 1
Detected link loops: 1
Traversal completed: true
```

**Stdout nếu không được phép tạo symlink:**

```text
Symlink created: false
No-follow link leaves: 0
Detected link loops: 0
Traversal completed: true
```

Giải thích:

1. `Files.createTempDirectory` tạo vùng thử riêng, tránh đụng dữ liệu người dùng. `root.resolve(...)` chỉ tính đường dẫn; các lệnh `Files.createDirectory`, `Files.writeString` và `Files.createSymbolicLink` mới có tác động I/O.
2. Nếu link tạo thành công, `child/back-to-root` trỏ ngược về `root` — đúng là một vòng theo nhánh `root → child → back-to-root → root`.
3. Lần `walkFileTree(root, visitor)` mặc định **không theo link**; symlink được gọi qua `visitFile`, nên `linkLeaves=1`.
4. Lần `walkFileTree` thứ hai có `FOLLOW_LINKS`. Khi cố đi vào link trỏ về tổ tiên, `visitFileFailed` nhận `FileSystemLoopException` và tăng `loopErrors`.
5. Trả `FileVisitResult.CONTINUE` để duyệt xong thay vì dừng với ngoại lệ. Không có vòng thì callback đó không tăng bộ đếm.
6. `finally` dọn **entry link** trước, sau đó file, thư mục con và gốc. Xóa symlink **không xóa thư mục đích** `root`. Nếu trong thực tế có tiến trình ngoài can thiệp, dọn dẹp vẫn có thể phát sinh `IOException`; ví dụ dùng thư mục tạm riêng để giảm nguy cơ.

**Không dùng chương trình này để thử nghiệm trên thư mục sản xuất.** Nó chỉ tạo thư mục riêng và không xóa đệ quy thư mục bất kỳ mà người dùng truyền vào.

## 5. Phân biệt `Files.walkFileTree`, `Files.walk` và `Files.find` khi có vòng

### `walkFileTree`: lỗi đi qua `FileVisitor`

Với `Files.walkFileTree`, callback quan trọng là:

```java
Files.walkFileTree(
        root,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        20,
        new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFileFailed(
                    Path file, IOException exc)
                    throws IOException {
                if (exc instanceof FileSystemLoopException) {
                    return FileVisitResult.CONTINUE;
                }
                throw exc;
            }
        });
```

Đây là mã minh họa trong class/phương thức với import các kiểu tương ứng và biến `root` đã có. Nếu muốn ghi nhận lỗi chứ không bỏ qua, có thể lưu path vào danh sách chẩn đoán, nhưng việc lưu quá nhiều entry có thể tăng dùng RAM.

Ưu điểm của `walkFileTree` là bạn có callback riêng:

- `preVisitDirectory(dir, attrs)`: được gọi trước khi xử lý nội dung thư mục;
- `visitFile(file, attrs)`: xử lý một entry file/leaf;
- `visitFileFailed(file, exc)`: xử lý việc duyệt/thăm một entry không thành công, gồm lỗi vòng nếu đi theo link;
- `postVisitDirectory(dir, exc)`: được gọi sau khi xử lý thư mục; `exc` có thể phản ánh lỗi khi duyệt thư mục.

Các callback trả `FileVisitResult` để quyết định tiếp tục hay bỏ qua nhánh/anh em, hoặc kết thúc. Khi muốn **theo link nhưng vẫn kiểm soát vòng và lỗi cụ thể**, `walkFileTree` thường là lựa chọn dễ diễn đạt chính sách hơn.

### `Files.walk`: trả về `Stream<Path>`

`Files.walk(root)` theo mặc định không đi theo symbolic link. Để theo link:

```java
import java.nio.file.FileVisitOption;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<Path> paths =
        Files.walk(root, 20, FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
}
```

Đây là đoạn minh họa cần `root` đã xác định và xử lý ngoại lệ phù hợp. `Files.walk` tạo stream **lazy**: lỗi đọc directory có thể xuất hiện trong quá trình tiêu thụ stream, không chỉ lúc gọi `walk(...)`. Khi có lỗi I/O trong quá trình duyệt, API có thể bọc `IOException` thành **`UncheckedIOException`**; với vòng liên kết, `FileSystemLoopException` có thể nằm ở **`getCause()`**.

```java
try (Stream<Path> paths =
        Files.walk(root, 20, FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
} catch (java.io.UncheckedIOException e) {
    if (e.getCause() instanceof FileSystemLoopException) {
        System.err.println("Đã gặp vòng liên kết");
    } else {
        throw e;
    }
}
```

Đây là đoạn minh họa cần import `Path`, `Files`, `FileVisitOption`, `Stream` và xử lý lỗi `IOException` có thể xảy ra ngay khi mở stream. Với stream, không có `visitFileFailed` để chọn tiếp tục qua đúng một vòng; khi iterator/stream báo lỗi, pipeline đang tiêu thụ thường không có cơ chế tương đương visitor để bỏ qua riêng nhánh đó rồi đi tiếp.

**Luôn đóng `Stream<Path>`** từ `Files.walk` hoặc `Files.find` bằng `try-with-resources`; stream có thể giữ tài nguyên thư mục đang mở.

### `Files.find`: tìm theo thuộc tính nhưng vẫn có rủi ro tương tự

`Files.find(root, maxDepth, matcher, options...)` có thể dùng `FOLLOW_LINKS`. Nó cung cấp `BasicFileAttributes` cho predicate, thích hợp khi cần lọc theo metadata, nhưng **không tự loại bỏ vòng liên kết hoặc bảo vệ khỏi traversal ra ngoài root** khi theo link. Trên stream lazy, ngoại lệ I/O có thể xuất hiện khi duyệt và cần đóng stream.

Không nên viết `Files.find(... FOLLOW_LINKS)` rồi cho rằng đã miễn nhiễm với chu trình chỉ vì predicate chỉ chọn file `.txt`: chương trình vẫn cần **duyệt** thư mục để tìm các file phù hợp.

## 6. Độ sâu tối đa và chính sách bỏ qua nhánh

`maxDepth` là công cụ giới hạn phạm vi, nhưng **không thay cho nhận diện vòng hoặc kiểm tra bảo mật**.

```java
Files.walkFileTree(
        root,
        EnumSet.of(FileVisitOption.FOLLOW_LINKS),
        3,
        visitor);
```

Đây là đoạn minh họa giả định có `root`, `visitor` và import phù hợp. `maxDepth=0` chỉ duyệt entry root; khi độ sâu chạm giới hạn, API không đi xuống sâu hơn (entry ở độ sâu cuối được xử lý như leaf theo hợp đồng của visitor). `maxDepth=3` cho phép xem tới ba cấp tính từ root.

Tuy nhiên:

- Một directory ở độ sâu 1 có thể chứa hàng triệu entry; **giới hạn độ sâu không giới hạn tổng số entry**.
- Một symlink ở độ sâu nhỏ có thể dẫn ra ngoài cây gốc dù chưa tạo vòng.
- Nếu chỉ duyệt sâu tới một mức chưa chạm mắt xích tạo vòng, bạn có thể **không quan sát được `FileSystemLoopException`**, nhưng bản thân liên kết vẫn tồn tại.
- Với tree lớn, vẫn cần kiểm soát thời gian, số entry, quyền, và cách xử lý I/O.

Trong `FileVisitor`, có thể trả:

| Giá trị | Ý nghĩa khi callback hỗ trợ |
| --- | --- |
| `CONTINUE` | Tiếp tục duyệt bình thường |
| `SKIP_SUBTREE` | Bỏ qua thư mục con của entry hiện tại, phù hợp ở `preVisitDirectory` |
| `SKIP_SIBLINGS` | Bỏ qua những entry anh em còn lại trong ngữ cảnh callback |
| `TERMINATE` | Kết thúc toàn bộ cuộc duyệt |

Ví dụ nếu chỉ cần biết thư mục nào có tài liệu, bạn có thể bỏ qua những nhánh lớn mà nghiệp vụ không dùng ngay tại `preVisitDirectory`. Không bật `FOLLOW_LINKS` nếu việc đi vào các symlink không phải yêu cầu.

## 7. `NOFOLLOW_LINKS` dùng ở đâu?

`LinkOption.NOFOLLOW_LINKS` **khác** `FileVisitOption.FOLLOW_LINKS`. Nó được truyền vào một số API hỏi metadata:

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

boolean entryExists = Files.exists(
        path, LinkOption.NOFOLLOW_LINKS);

BasicFileAttributes attrs = Files.readAttributes(
        path, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);

System.out.println("Is symbolic link: " + attrs.isSymbolicLink());
```

Đây là đoạn minh họa trong phương thức xử lý `IOException`, với `path` đã khai báo. Khi truyền `NOFOLLOW_LINKS`, metadata có thể phản ánh **chính entry liên kết**, thay vì thuộc tính của đích.

Để kiểm tra nhanh:

```java
boolean link = Files.isSymbolicLink(path);
```

`Files.isSymbolicLink(path)` kiểm tra entry có là symbolic link hay không và không buộc bạn phải mở/duyệt thư mục đích.

**Dangling link:** `Files.exists(link)` mặc định thường theo link nên có thể trả `false` khi mục tiêu biến mất, trong khi `Files.exists(link, NOFOLLOW_LINKS)` vẫn có thể `true` vì entry liên kết còn ở đó. Đừng dùng `exists` mặc định để xác nhận chính symlink đã bị xóa.

## 8. Vòng liên kết so với truy cập lặp không tạo vòng

Hai trường hợp cần phân biệt:

**Vòng (cycle):**

```text
A/child/back -> A
Đi theo link từ A/child/back sẽ quay lại tổ tiên A.
```

**Truy cập trùng nhưng không là vòng trên nhánh hiện tại:**

```text
root/
├── original/
│   └── x.txt
└── alias -> original/
```

Khi đi theo `alias`, cùng file `x.txt` có thể được truy cập lần nữa qua một đường dẫn khác. Vì `original` chưa chắc là **tổ tiên của alias trong nhánh hiện tại**, việc này **không nhất thiết** tạo `FileSystemLoopException`.

Nếu nghiệp vụ cần xử lý **mỗi đối tượng vật lý chỉ một lần**, phát hiện vòng không đủ: phải có chiến lược deduplicate theo định danh của filesystem hoặc `Files.isSameFile` khi thích hợp. So sánh `Path.toString()` không chứng minh hai file khác nhau; ngược lại, các chỉ báo như `BasicFileAttributes.fileKey()` có thể `null` hoặc có đặc tính phụ thuộc filesystem/provider.

Một tập hợp `Set<Path>` chứa chuỗi path khác nhau **không đủ** để khẳng định không trùng nội dung khi có symlink hoặc hard link. Cần xác định rõ bạn muốn “duyệt mỗi **đường dẫn**” hay “xử lý mỗi **đối tượng tệp thực**”.

## 9. Bảo mật: không tùy tiện theo link khi xử lý dữ liệu không tin cậy

Nguy cơ lớn nhất không chỉ là vòng liên kết làm chậm chương trình. Với `FOLLOW_LINKS`, một link có thể trỏ tới cây thư mục mà ứng dụng **không dự định** truy cập.

Ví dụ cấu trúc:

```text
uploads/
└── external -> /private-data/
```

Nếu code scan toàn bộ `uploads` và bật `FOLLOW_LINKS`, tiến trình có thể đọc metadata hoặc nội dung của `/private-data` nếu quyền cho phép. Với chương trình **xóa thư mục**, bật `FOLLOW_LINKS` có thể dẫn đến thao tác sai phạm vi gây mất dữ liệu nghiêm trọng.

Khuyến nghị:

1. **Mặc định không theo symlink** nếu không có yêu cầu nghiệp vụ rõ ràng.
2. Xác định phạm vi root được phép, quyền sở hữu và chính sách xử lý symbolic link.
3. Với path do người dùng đưa vào, kiểm tra thành phần đường dẫn `..`, đường dẫn tuyệt đối, và ảnh hưởng của symlink; `normalize()` chỉ là xử lý cú pháp và **không tạo ra ranh giới bảo mật hoàn chỉnh**.
4. Áp giới hạn độ sâu và số entry/thời gian/bộ nhớ; riêng `maxDepth` chưa đủ.
5. Nếu phải theo link, cân nhắc canonical/real path, `Files.isSameFile`, đánh dấu đối tượng đã thăm và chiến lược xử lý lỗi, đồng thời lưu ý thay đổi filesystem giữa lúc kiểm tra và sử dụng (TOCTOU).
6. Không dùng một bộ quét có `FOLLOW_LINKS` như một công cụ xóa file đệ quy trong thư mục người dùng chỉ định mà không có thiết kế an toàn.

Ngay cả khi không bật `FOLLOW_LINKS`, tên đường dẫn và nội dung hệ thống tệp vẫn có thể thay đổi đồng thời. Không coi kết quả `Files.exists`, `normalize` hoặc một lần duyệt là bảo đảm file không bị thay đổi sau đó.

## 10. Xử lý lỗi khi duyệt thật

Một visitor có chiến lược minh bạch thường xử lý **vòng** khác với các lỗi không mong đợi:

```java
import java.io.IOException;
import java.nio.file.FileSystemLoopException;
import java.nio.file.FileVisitResult;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;

class LoopAwareVisitor extends SimpleFileVisitor<Path> {
    @Override
    public FileVisitResult visitFileFailed(
            Path file, IOException exc) throws IOException {

        if (exc instanceof FileSystemLoopException) {
            System.err.println("Bỏ qua vòng tại: " + file);
            return FileVisitResult.CONTINUE;
        }

        // Không che giấu lỗi quyền truy cập hoặc I/O khác.
        throw exc;
    }
}
```

Đây là một **class minh họa có thể đặt trong file riêng hoặc class bao ngoài phù hợp**. Để dùng, truyền instance cho `Files.walkFileTree(root, EnumSet.of(FOLLOW_LINKS), maxDepth, new LoopAwareVisitor())`. Trong ứng dụng thật, có thể thay in console bằng ghi log có cấu trúc, đếm số vòng hoặc kết thúc traversal theo yêu cầu.

### Với `postVisitDirectory`

`postVisitDirectory(Path dir, IOException exc)` nhận một `exc` khác `null` nếu gặp lỗi khi duyệt nội dung của thư mục đó. Một visitor tổng quát cần quyết định ném lại, ghi nhận, hay bỏ qua lỗi tùy yêu cầu; không giả định mọi lỗi đều phải đi qua `visitFileFailed`.

### Với `Files.walk`

Vì đây là `Stream<Path>`, bạn cần đóng stream và chuẩn bị xử lý `UncheckedIOException` trong giai đoạn tiêu thụ. Nếu mục tiêu là **tiếp tục sau một FileSystemLoopException cụ thể**, `walkFileTree` với visitor được thiết kế đúng thường rõ ràng hơn một pipeline stream cần thoát ra khi iterator ném lỗi.

## 11. Lỗi phổ biến

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| “Java luôn theo symlink khi `Files.walkFileTree`” | Hiểu sai cây đang được duyệt | Mặc định **không theo**, chỉ thêm `FOLLOW_LINKS` khi muốn |
| “`FOLLOW_LINKS` chỉ để tìm file nhanh hơn” | Có thể đọc trùng, ra ngoài root và gặp vòng | Xác định mục tiêu nghiệp vụ trước khi bật |
| “Vòng link làm visitor treo vô hạn chắc chắn” | Java có cơ chế phát hiện loop, thường báo `FileSystemLoopException` | Xử lý `visitFileFailed` hoặc ngoại lệ thích hợp |
| “`FileSystemLoopException` xuất hiện ở `visitFile` bình thường” | Bỏ qua callback báo lỗi | Kiểm tra `visitFileFailed(file, exc)` khi `walkFileTree` |
| “`Files.walk` ném trực tiếp cùng lỗi checked ngay khi tạo stream” | Lỗi lazy có thể xuất hiện lúc duyệt | Xử lý `UncheckedIOException` và `getCause()`, đóng stream |
| “`CONTINUE` sau loop sẽ vào lại link” | Nó bỏ qua nhánh lỗi và đi tiếp | Không tự gọi lại traversal trên cùng link |
| “Giới hạn maxDepth ngăn mọi rủi ro” | Có thể nhiều entry, dữ liệu ngoài root | Thêm giới hạn entry/thời gian/ownership |
| “Không có FileSystemLoopException nghĩa là không duyệt trùng” | Alias cùng target nhưng không là tổ tiên vẫn gây trùng | Deduplicate nếu nghiệp vụ cần |
| “`Files.exists(link)` chắc chắn kiểm tra entry link” | Có thể theo symlink tới đích | Dùng `NOFOLLOW_LINKS` khi muốn hỏi về entry link |
| “`Path.normalize()` ngăn mọi truy cập ngoài root” | Symlink và race thay đổi nghĩa đường dẫn | Kiểm tra real path và thực hiện chính sách an toàn |
| “Duyệt với FOLLOW_LINKS rồi xóa toàn bộ thì an toàn” | Có thể xóa ngoài root | Tránh theo link trong chương trình xóa nhạy cảm |
| “Trả `CONTINUE` cho mọi `IOException`” | Che giấu quyền và lỗi I/O nghiêm trọng | Phân loại loop riêng, báo các lỗi khác |
| “Bỏ quên đóng `Files.walk` stream không sao” | Có thể giữ resource mở | `try-with-resources` |
| “Windows nào cũng tạo symlink được” | Phụ thuộc quyền/chế độ và filesystem | Thử trên thư mục tạm, có nhánh không hỗ trợ |

## 12. Bài tập tự kiểm tra

1. **Nếu gọi `Files.walkFileTree(root, visitor)` mà không có `FOLLOW_LINKS`, symlink tới thư mục có được duyệt sâu không?** Không; liên kết được xem như leaf entry.
2. **`FileVisitOption.FOLLOW_LINKS` được truyền ở đâu?** Vào overload của `walkFileTree` hoặc varargs của `Files.walk` / `Files.find`.
3. **Link `A/child/back -> A` có thể gây lỗi gì khi đi theo?** `FileSystemLoopException` vì link đưa về tổ tiên.
4. **Trong `walkFileTree`, nên bắt vòng ở đâu?** `visitFileFailed(Path, IOException)`, rồi kiểm tra `exc instanceof FileSystemLoopException`.
5. **Trả `FileVisitResult.CONTINUE` khi bắt một vòng có đi vào lại nhánh vòng không?** Không; bỏ qua entry lỗi và duyệt phần còn lại.
6. **Không có vòng có chắc không đi ra ngoài root?** Không; link có thể trỏ sang thư mục bên ngoài.
7. **`maxDepth=3` có bảo đảm chỉ duyệt 100 file trở xuống không?** Không; giới hạn độ sâu, không giới hạn số entry.
8. **`Files.walk` có thể báo lỗi vòng như thế nào trong lúc tiêu thụ?** Dưới dạng `UncheckedIOException` với nguyên nhân `FileSystemLoopException`.
9. **Symlink bị mất target còn có thể hiện diện như một entry không?** Có; dùng `Files.exists(link, LinkOption.NOFOLLOW_LINKS)` hoặc `Files.isSymbolicLink` để kiểm tra entry.
10. **`FileSystemLoopException` có thay cho việc chống xử lý trùng không?** Không; cùng target được tham chiếu từ nhánh khác có thể không là vòng theo tổ tiên.
11. **Có nên bật `FOLLOW_LINKS` khi viết chương trình xóa toàn bộ thư mục upload của người dùng?** Không nếu chưa có thiết kế bảo vệ chặt chẽ; thường nên không theo link.
12. **Khi symlink không tạo được trong chương trình demo, đó có chứng minh FOLLOW_LINKS không hoạt động không?** Không; việc tạo link phụ thuộc quyền và provider, còn `FOLLOW_LINKS` là hành vi duyệt khi liên kết tồn tại.

**Ghi nhớ:** mặc định, Java duyệt cây **không theo symbolic link**. `FOLLOW_LINKS` cho phép đi vào thư mục được link trỏ tới, nhưng cũng mở ra rủi ro **vòng, duyệt trùng và vượt root**. Với `Files.walkFileTree`, dùng `visitFileFailed` để nhận `FileSystemLoopException` và quyết định `CONTINUE` hay báo lỗi; với `Files.walk`/`find`, lưu ý I/O exception có thể xuất hiện khi tiêu thụ stream.