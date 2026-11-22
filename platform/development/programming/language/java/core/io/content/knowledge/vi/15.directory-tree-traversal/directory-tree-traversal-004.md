# Files.find kết hợp Path với BasicFileAttributes trong Java

Khi cần **tìm những mục trong cây thư mục theo điều kiện**, Java NIO.2 cung cấp phương thức `Files.find(...)`. Điểm mạnh của API này là hàm điều kiện nhận **đồng thời `Path` và `BasicFileAttributes`**: bạn vừa kiểm tra được **tên/vị trí** tệp, vừa kiểm tra **loại, kích thước và thời gian** mà không phải tự đọc lại thuộc tính ở từng bộ lọc.

Một ví dụ thực tế: tìm tất cả tệp có đuôi `.txt`, kích thước từ 4 byte trở lên, nằm trong tối đa 3 cấp từ thư mục gốc. `Files.find` trả về `Stream<Path>` để tiếp tục `map`, `filter`, `sorted` hoặc `forEach`.

Tuy nhiên, stream này gắn với tài nguyên duyệt hệ thống tệp và có thể ném lỗi khi đang tiêu thụ; **phải đóng bằng `try-with-resources`**. Cũng cần hiểu chính xác `maxDepth`, quy tắc symbolic link, thứ tự duyệt và giới hạn của thông tin thuộc tính.

## 1. Chữ ký và ý nghĩa từng tham số

Trong `java.nio.file.Files` (Java 17+), overload cơ bản có dạng:

~~~java
public static Stream<Path> find(
        Path start,
        int maxDepth,
        BiPredicate<Path, BasicFileAttributes> matcher,
        FileVisitOption... options) throws IOException
~~~

Các loại cần import:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.FileVisitOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.function.BiPredicate;
import java.util.stream.Stream;
~~~

Đây là hai **mảnh mã minh họa chữ ký API và import**, không phải một file Java tự chạy.

| Thành phần | Ý nghĩa |
|---|---|
| `start` | Đường dẫn bắt đầu duyệt; có thể là thư mục hoặc một tệp đơn |
| `maxDepth` | Độ sâu tối đa: `0` là chỉ đối tượng bắt đầu, `1` thêm các con trực tiếp |
| `matcher` | Hàm kiểm tra hai đối số `(Path path, BasicFileAttributes attrs)`, trả `true` khi cần đưa đường dẫn vào kết quả |
| `options` | Các lựa chọn duyệt, thường là `FileVisitOption.FOLLOW_LINKS` nếu muốn theo symbolic link |
| `Stream<Path>` | Stream các đường dẫn **khớp điều kiện**, được tạo trong quá trình duyệt |

Ví dụ ngắn:

~~~java
// Mảnh mã minh họa: root là Path đã được xác định.
try (Stream<Path> matches = Files.find(
        root,
        2,
        (path, attrs) -> attrs.isRegularFile())) {
    matches.forEach(System.out::println);
}
~~~

Phương thức `find` chỉ đưa các `Path` có `matcher.test(path, attrs) == true` vào stream kết quả. Nếu predicate là `(path, attrs) -> true`, các mục đã duyệt đều có thể xuất hiện trong kết quả, bao gồm cả đường dẫn `start`.

**Không nhầm** `Files.find` với tìm kiếm tên theo chuỗi thuần túy, chẳng hạn `String.contains(...)`. `Files.find` **thực sự duyệt hệ thống tệp**; nó cần quyền truy cập và có thể gặp lỗi I/O.

## 2. Path và BasicFileAttributes đảm nhiệm hai vai trò khác nhau

### Path: địa chỉ và các thành phần tên

`Path` trả lời câu hỏi “mục nằm ở đâu, được đặt tên như thế nào?”:

- `path.getFileName()`: tên cuối của đường dẫn (có thể `null` đối với đường dẫn chỉ gồm root).
- `path.getParent()`: thư mục cha nếu có.
- `path.startsWith(base)`: kiểm tra tiền tố theo **thành phần đường dẫn**, không phải chuỗi ký tự.
- `path.endsWith(otherPath)`: kiểm tra hậu tố theo thành phần đường dẫn; **không** phải kiểm tra phần mở rộng `.txt`.
- `root.relativize(path)`: lấy đường dẫn tương đối từ `root` tới `path`, nếu hai `Path` tương thích theo provider.

### BasicFileAttributes: thông tin cơ bản về mục hệ thống tệp

`BasicFileAttributes` là giao diện chứa thông tin lấy từ file system:

| API của `BasicFileAttributes` | Ý nghĩa |
|---|---|
| `isRegularFile()` | Mục được xác định là tệp thường theo quy tắc truy cập thuộc tính |
| `isDirectory()` | Mục là thư mục |
| `isSymbolicLink()` | Mục được nhận dạng là symbolic link nếu việc đọc thuộc tính không đi theo nó |
| `isOther()` | Loại mục không thuộc ba nhóm trên |
| `size()` | Kích thước được báo cáo, đơn vị byte; có quy tắc riêng với mục không phải tệp thường |
| `creationTime()` | Thời gian tạo do provider báo |
| `lastModifiedTime()` | Thời gian sửa đổi cuối |
| `lastAccessTime()` | Thời gian truy cập cuối |
| `fileKey()` | Khóa nhận dạng tệp nếu provider hỗ trợ, có thể `null` |

Không nên suy diễn rằng `size()` của **thư mục** có ý nghĩa “tổng số byte của các tệp con”; đối với mục không phải tệp thường, kích thước có thể mang ý nghĩa khác hoặc không được xác định một cách hữu ích. Nếu cần tính tổng dung lượng cây thư mục, phải duyệt và cộng **kích thước các tệp phù hợp**, đồng thời xử lý hard link/symbolic link nếu muốn tránh đếm trùng.

Đối với thời gian tạo, một số file system không có thông tin ngày tạo thực sự; provider có thể cung cấp giá trị thay thế. Thời gian được trả dưới dạng `FileTime`, không nên tự giả định timezone hoặc độ chính xác cố định.

## 3. Cách viết matcher đúng và rõ nghĩa

Một `matcher` thường kết hợp điều kiện trên `Path` và `BasicFileAttributes`:

~~~java
// Mảnh mã minh họa: thuộc phần tham số của Files.find.
(path, attrs) ->
        attrs.isRegularFile()
        && path.getFileName() != null
        && path.getFileName().toString().endsWith(".txt")
        && attrs.size() >= 4
~~~

Ý nghĩa của từng điều kiện:

1. Chỉ nhận **tệp thường**, loại trừ thư mục.
2. Bảo vệ trường hợp `getFileName() == null` trước khi gọi `toString()`.
3. Kiểm tra phần mở rộng bằng **chuỗi tên tệp**, không dùng `Path.endsWith(".txt")`.
4. Kiểm tra kích thước được cung cấp trong thuộc tính, tránh gọi thêm `Files.size(path)` bên trong predicate chỉ để có cùng thông tin.

Có thể tách predicate để tái sử dụng:

~~~java
BiPredicate<Path, BasicFileAttributes> isNonEmptyText =
        (path, attrs) ->
                attrs.isRegularFile()
                && path.getFileName() != null
                && path.getFileName().toString().endsWith(".txt")
                && attrs.size() > 0;
~~~

Đây là **mảnh mã minh họa**: cần import `BiPredicate`, `Path`, `BasicFileAttributes`. Tên `isNonEmptyText` chỉ khẳng định tệp **có tên kết thúc `.txt` và kích thước khác 0**, chứ **không** xác minh nội dung là văn bản hợp lệ. Phần mở rộng tệp không phải chứng nhận về định dạng hay độ an toàn của nội dung.

Lưu ý predicate có thể được gọi với **thư mục gốc** hoặc **thư mục trung gian**, không chỉ với tệp. Không được giả định mọi `path.getFileName()` luôn khác `null` hoặc mọi `attrs` đều biểu diễn một tệp thường.

## 4. maxDepth: cấp 0, cấp 1, cấp 2...

Giả sử cây sau đây:

~~~text
root/                       ← depth 0
├── note.txt                ← depth 1
├── app.log                 ← depth 1
└── docs/                   ← depth 1
    ├── guide.txt           ← depth 2
    ├── empty.txt           ← depth 2
    └── nested/             ← depth 2
        └── deep.txt        ← depth 3
~~~

Nếu matcher nhận mọi mục:

| `maxDepth` | Những mục có thể được xét |
|---:|---|
| `0` | Chỉ `root` |
| `1` | `root` và các con trực tiếp `note.txt`, `app.log`, `docs` |
| `2` | Thêm `guide.txt`, `empty.txt`, `nested` |
| `3` | Thêm `deep.txt` |
| `Integer.MAX_VALUE` | Duyệt không có giới hạn độ sâu hữu ích ở mức tham số (vẫn chịu giới hạn tài nguyên/khả năng truy cập) |

Nếu matcher chỉ nhận `attrs.isRegularFile()`, đường dẫn thư mục vẫn có thể được **duyệt** để tìm các tệp con, nhưng sẽ **không xuất hiện trong stream kết quả**.

`maxDepth` âm không hợp lệ và gây `IllegalArgumentException`. Đối với cây lớn, hãy giới hạn độ sâu phù hợp nghiệp vụ thay vì mặc định `Integer.MAX_VALUE` một cách vô điều kiện.

Quan trọng: **trả `false` từ matcher cho thư mục không có nghĩa là không đi xuống các con của thư mục đó**. `Files.find` là cơ chế chọn các mục phù hợp; muốn chủ động **cắt bỏ cả một nhánh** (skip subtree) khi duyệt, dùng `Files.walkFileTree` với `FileVisitor`/`SimpleFileVisitor` và trả `FileVisitResult.SKIP_SUBTREE` ở `preVisitDirectory`.

## 5. Ví dụ hoàn chỉnh: tìm file theo tên, kích thước và độ sâu

Tệp **`FilesFindDemo.java`**, tương thích Java 17+:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FilesFindDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("find-demo-");
        Path docs = root.resolve("docs");
        Path nested = docs.resolve("nested");

        try {
            Files.createDirectories(nested);
            Files.writeString(root.resolve("note.txt"), "abc",
                    StandardCharsets.UTF_8);
            Files.writeString(root.resolve("app.log"), "1234567",
                    StandardCharsets.UTF_8);
            Files.writeString(docs.resolve("guide.txt"), "hello",
                    StandardCharsets.UTF_8);
            Files.writeString(docs.resolve("empty.txt"), "",
                    StandardCharsets.UTF_8);
            Files.writeString(nested.resolve("deep.txt"), "four",
                    StandardCharsets.UTF_8);

            System.out.println("maxDepth=2:");
            printMatches(root, 2);

            System.out.println("maxDepth=3:");
            printMatches(root, 3);
        } finally {
            Files.deleteIfExists(nested.resolve("deep.txt"));
            Files.deleteIfExists(docs.resolve("empty.txt"));
            Files.deleteIfExists(docs.resolve("guide.txt"));
            Files.deleteIfExists(root.resolve("app.log"));
            Files.deleteIfExists(root.resolve("note.txt"));
            Files.deleteIfExists(nested);
            Files.deleteIfExists(docs);
            Files.deleteIfExists(root);
        }
    }

    private static void printMatches(Path root, int maxDepth)
            throws IOException {
        try (Stream<Path> matches = Files.find(
                root,
                maxDepth,
                (path, attrs) ->
                        attrs.isRegularFile()
                        && path.getFileName() != null
                        && path.getFileName().toString().endsWith(".txt")
                        && attrs.size() >= 3)) {

            matches.map(root::relativize)
                    .map(Path::toString)
                    .map(name -> name.replace('\\', '/'))
                    .sorted()
                    .forEach(System.out::println);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FilesFindDemo.java
java FilesFindDemo
~~~

Stdout trên file system mặc định phổ biến, khi các thao tác tạo tệp thành công:

~~~text
maxDepth=2:
docs/guide.txt
note.txt
maxDepth=3:
docs/guide.txt
docs/nested/deep.txt
note.txt
~~~

Giải thích:

- `note.txt` có 3 byte, `guide.txt` có 5 byte, `deep.txt` có 4 byte; đều thỏa `attrs.size() >= 3` và tên kết thúc `.txt`.
- `empty.txt` có kích thước 0 nên không khớp. `app.log` không có đuôi `.txt`.
- `deep.txt` nằm sâu 3 cấp, nên bị loại khi `maxDepth == 2` và xuất hiện khi `maxDepth == 3`.
- `map(root::relativize)` đổi đường dẫn tuyệt đối ngẫu nhiên của tệp tạm thành dạng tương đối dễ đọc.
- `replace('\\', '/')` chỉ chuẩn hóa **chuỗi được in** giữa Windows/Unix; nó không đổi cách đối tượng `Path` được duyệt.
- `sorted()` tạo thứ tự xuất hiện có thể dự đoán. Nếu bỏ `sorted()`, không có bảo đảm chung rằng thứ tự duyệt từng mục sẽ giống nhau giữa các file system.

Chương trình chỉ thao tác trong thư mục tạm mà nó tự tạo. `finally` xóa các tệp rồi xóa thư mục từ cấp sâu lên, vì `Files.deleteIfExists(dir)` không tự xóa đệ quy một thư mục còn chứa nội dung.

## 6. Tìm bằng thời gian, kích thước và loại file

`BasicFileAttributes` cho phép xây dựng nhiều dạng bộ lọc.

### Tìm file sửa đổi sau một thời điểm

~~~java
// Mảnh mã minh họa: root và cutoff đã được xác định,
// cutoff có kiểu java.nio.file.attribute.FileTime.
try (Stream<Path> found = Files.find(
        root,
        4,
        (path, attrs) ->
                attrs.isRegularFile()
                && attrs.lastModifiedTime().compareTo(cutoff) >= 0)) {
    found.forEach(System.out::println);
}
~~~

`lastModifiedTime()` trả `FileTime`, có thể so sánh qua `compareTo(...)` hoặc đổi sang `Instant` khi cần, tùy mục tiêu xử lý. Nếu hệ thống cần lọc theo “ngày” ở múi giờ địa phương, phải xác định timezone và thời điểm cắt chính xác; file timestamp không tự mang khái niệm “hôm nay” theo timezone của người dùng.

### Tìm các thư mục

~~~java
try (Stream<Path> directories =
             Files.find(root, 2, (p, attrs) -> attrs.isDirectory())) {
    directories.forEach(System.out::println);
}
~~~

Đây là **mảnh mã minh họa**. Lưu ý `root` cũng có thể được trả về nếu `root` là thư mục; muốn chỉ nhận thư mục con, thêm `!p.equals(root)` hoặc kiểm tra độ sâu qua `root.relativize(p).getNameCount()` với những điều kiện bảo vệ thích hợp.

### Kết hợp điều kiện và tránh đọc lại thuộc tính

~~~java
try (Stream<Path> matches = Files.find(
        root,
        3,
        (p, a) -> a.isRegularFile()
                && a.size() > 1_024
                && p.getFileName() != null
                && p.getFileName().toString().endsWith(".log"))) {
    matches.forEach(System.out::println);
}
~~~

Các đoạn trên minh họa **cách đặt điều kiện vào matcher**. Khi `Files.find` duyệt mục, nó đọc `BasicFileAttributes` và đưa dữ liệu đó vào predicate. Dùng ngay `a.size()`, `a.isRegularFile()` thường tránh một lần truy vấn thuộc tính riêng mà bạn có thể phải tự viết khi dùng `Files.walk(...).filter(p -> Files.size(p) > ...)`.

Tuy nhiên, hiệu quả thực tế còn tùy provider, độ sâu, số file, thiết bị lưu trữ và chi phí xét predicate. Đừng khẳng định `find` luôn nhanh hơn bất kỳ cách duyệt nào trong mọi môi trường.

## 7. Stream<Path> được tiêu thụ như thế nào?

`Files.find(...)` trả về **stream duyệt lười (lazy)**: việc tạo stream không đồng nghĩa mọi mục đã được duyệt/đọc ngay. Phần lớn công việc xảy ra khi gọi terminal operation như `forEach`, `count`, `collect` hoặc `toList`.

~~~java
// Mảnh mã minh họa: root là Path hợp lệ.
try (Stream<Path> found = Files.find(
        root, 2, (p, attrs) -> attrs.isRegularFile())) {
    long total = found.count();
    System.out.println(total);
}
~~~

**Luôn đóng stream**: cơ chế duyệt có thể giữ tài nguyên mở, ví dụ directory handle. `Stream<Path>` từ `Files.find` phải được đóng bằng `try-with-resources` khi không còn dùng, kể cả khi terminal operation ném ngoại lệ.

Các điểm cần nhớ:

1. Một stream thông thường chỉ được tiêu thụ **một lần**. Sau `count()`, không gọi tiếp `forEach()` trên cùng stream với hy vọng duyệt lại.
2. Các intermediate operation như `filter`/`map` tự chúng thường không chạy thao tác I/O ngay; terminal operation kích hoạt pipeline.
3. Dùng `sorted()` hoặc `toList()` sẽ cần giữ các mục tương ứng trong bộ nhớ; một kết quả khổng lồ có thể gây tốn RAM. Nếu chỉ cần xử lý tuần tự và không cần thứ tự ổn định, `forEach` có thể phù hợp hơn.
4. Một số thao tác như `findFirst()`/`limit(...)` có thể ngừng tiêu thụ sớm. Nhưng vẫn phải đóng stream, và không nên coi `limit` là giới hạn chắc chắn cho mọi chi phí truy cập tài nguyên phía dưới.
5. `Stream` đi kèm tài nguyên file system không nên được trả ra khỏi phương thức rồi đóng mất ở trong `try`. Nếu muốn trả danh sách, hãy thu thập và đóng stream bên trong; nếu muốn trả stream, cần định rõ người gọi chịu trách nhiệm đóng.

Ví dụ **sai về vòng đời**:

~~~java
// Mảnh mã minh họa: KHÔNG làm thế nếu trả stream cho caller.
Stream<Path> leaked() throws IOException {
    return Files.find(root, 10, (p, a) -> a.isRegularFile());
}
// Caller có thể quên đóng stream.
~~~

Một giải pháp là xử lý trong scope:

~~~java
// Mảnh mã minh họa: kết quả là List<Path> trong RAM.
try (Stream<Path> stream = Files.find(
        root, 10, (p, a) -> a.isRegularFile())) {
    return stream.toList(); // Java 16+, đóng stream sau khi thu thập.
}
~~~

Nhưng nếu kết quả có thể rất lớn, giải pháp trên lại chuyển rủi ro từ open stream sang **tích lũy danh sách trong RAM**. Hãy cân nhắc xử lý streaming, giới hạn kết quả hoặc API xử lý theo lô tùy yêu cầu.

## 8. Theo symbolic link: mặc định và FOLLOW_LINKS

Mặc định, `Files.find` **không đi theo symbolic link** khi duyệt. Nếu muốn xử lý các thư mục được trỏ tới bởi symbolic link, có thể truyền `FileVisitOption.FOLLOW_LINKS`:

~~~java
// Mảnh mã minh họa, cần import FileVisitOption.
try (Stream<Path> found = Files.find(
        root,
        5,
        (p, attrs) -> attrs.isRegularFile(),
        FileVisitOption.FOLLOW_LINKS)) {
    found.forEach(System.out::println);
}
~~~

Cần phân biệt hai điều:

- **Quy tắc duyệt:** có đi sâu vào thư mục được trỏ đến bằng symbolic link hay không.
- **Thuộc tính mà matcher nhìn thấy:** theo cách đọc thuộc tính trong quá trình duyệt, khi đi theo link có thể thấy thuộc tính của **đích**; không theo link thì có thể thấy thuộc tính của chính **link**. Vì vậy `attrs.isRegularFile()`, `attrs.isDirectory()` và `attrs.isSymbolicLink()` cần được hiểu trong chế độ duyệt đã chọn.

Các rủi ro với `FOLLOW_LINKS`:

1. Cây duyệt có thể sang vị trí khác dự kiến, kể cả bên ngoài `root` về mặt vật lý.
2. Một đường dẫn symbolic link có thể dẫn ngược về một tổ tiên, tạo **vòng lặp**. Khi phát hiện loop, thao tác duyệt có thể phát sinh `FileSystemLoopException` được bọc trong `UncheckedIOException` khi tiêu thụ stream.
3. Cùng một đối tượng file có thể được gặp qua nhiều alias khác nhau; kết quả tìm kiếm không mặc nhiên “deduplicate” theo file identity.
4. Symbolic link và nội dung có thể đổi trong khi duyệt, gây race hoặc lỗi I/O.

Với công cụ rà soát hoặc xóa file, **không nên bật FOLLOW_LINKS chỉ vì muốn tìm nhiều kết quả hơn**. Cần chính sách rõ về quyền truy cập, phạm vi dữ liệu, giới hạn độ sâu và hành vi khi gặp link.

## 9. Files.find khác gì Files.walk và walkFileTree?

| API | Đầu ra/cơ chế | Khi nào nên dùng |
|---|---|---|
| `Files.find(start, depth, matcher, options...)` | `Stream<Path>` các mục khớp; matcher nhận `Path` **và** `BasicFileAttributes` | Cần lọc trực tiếp theo loại/kích thước/thời gian cùng tên đường dẫn |
| `Files.walk(start, depth, options...)` | `Stream<Path>` của các mục được duyệt | Muốn duyệt rồi dùng các thao tác Stream khác; tự lấy thuộc tính nếu cần |
| `Files.walkFileTree(start, visitor)` | Callback `preVisitDirectory`, `visitFile`, `visitFileFailed`, `postVisitDirectory` | Muốn kiểm soát nhánh duyệt, bỏ qua subtree, xử lý lỗi từng mục và luồng công việc tùy chỉnh |

Một lợi thế của `Files.find` so với viết `Files.walk(...).filter(path -> Files.readAttributes(...))` là thuộc tính đã có sẵn trong predicate. Ngược lại, khi cần **chỉ duyệt một số nhánh** hoặc **tiếp tục/loại bỏ dựa trên lỗi của từng mục** theo cách tùy biến, `walkFileTree` với `FileVisitor` thể hiện ý định tốt hơn.

Quan trọng: `find` không hỗ trợ `SKIP_SUBTREE` từ matcher. Ngay cả khi predicate trả `false` cho một thư mục, việc duyệt con của thư mục đó vẫn có thể diễn ra. Đừng dùng một matcher trả `false` để kỳ vọng nó tự tiết kiệm công duyệt cả nhánh.

## 10. Ngoại lệ I/O khi tạo và khi tiêu thụ stream

`Files.find(...)` có thể ném `IOException` **ngay lúc tạo stream** nếu không mở được nguồn ban đầu. Khi đang duyệt lười, một lỗi I/O xuất hiện sau đó có thể được biểu diễn dưới dạng `UncheckedIOException`, với `getCause()` là một `IOException` cụ thể.

~~~java
// Mảnh mã minh họa, cần import IOException và UncheckedIOException.
try (Stream<Path> found = Files.find(
        root, 5, (p, a) -> a.isRegularFile())) {
    found.forEach(this::processFile);
} catch (java.io.UncheckedIOException ex) {
    // Lỗi phát sinh khi stream đang được tiêu thụ.
    java.io.IOException cause = ex.getCause();
    // Ghi nhận và xử lý nguyên nhân I/O.
} catch (java.io.IOException ex) {
    // Lỗi mở nguồn/tạo stream.
}
~~~

Đây là **mảnh mã minh họa bên trong phương thức của một lớp có `processFile`**, không phải chương trình độc lập. Nếu dùng trong method `static`, cần thay `this::processFile` bằng method reference thích hợp.

Không phải mọi lỗi bên trong `matcher` tự động biến thành `UncheckedIOException`: nếu predicate của bạn tự ném một `RuntimeException` khác, ngoại lệ đó có thể lan truyền theo hợp đồng Stream thông thường. Tránh bọc mọi lỗi vào một catch chung rồi lờ đi, vì kết quả tìm kiếm có thể chỉ là **một phần**.

Ngoài ra, thư mục và các tệp có thể thay đổi giữa lần đọc thuộc tính và lúc bạn mở đường dẫn để xử lý. `BasicFileAttributes` là ảnh chụp thuộc tính tại thời điểm được đọc; nó **không khóa file**, không cho một giao dịch duy nhất và không bảo đảm nội dung không thay đổi sau đó. Nếu nghiệp vụ đòi mức nhất quán mạnh hơn, cần chiến lược đồng bộ hoặc thao tác file phù hợp.

## 11. Ví dụ Java 17+: dùng thuộc tính mà không in timestamp phụ thuộc máy

Ví dụ sau tạo một cấu trúc có nội dung xác định và minh họa phép tìm dựa trên nhiều thuộc tính mà vẫn có stdout ổn định.

Tạo file **`FilesFindAttributesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FilesFindAttributesDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("find-attrs-");
        Path sub = root.resolve("sub");

        try {
            Files.createDirectory(sub);
            Files.writeString(root.resolve("small.txt"), "a",
                    StandardCharsets.UTF_8);
            Files.writeString(root.resolve("large.txt"), "12345",
                    StandardCharsets.UTF_8);
            Files.writeString(sub.resolve("deep.txt"), "1234",
                    StandardCharsets.UTF_8);

            try (Stream<Path> found = Files.find(
                    root, 1,
                    (p, a) -> a.isRegularFile() && a.size() >= 4)) {
                System.out.println("level1Count=" + found.count());
            }

            try (Stream<Path> found = Files.find(
                    root, 2,
                    (p, a) -> a.isRegularFile()
                            && a.size() >= 4
                            && a.lastModifiedTime() != null)) {
                System.out.println("level2Count=" + found.count());
            }

            try (Stream<Path> found = Files.find(
                    root, 0, (p, a) -> a.isDirectory())) {
                System.out.println("rootOnly=" + found.count());
            }
        } finally {
            Files.deleteIfExists(sub.resolve("deep.txt"));
            Files.deleteIfExists(root.resolve("large.txt"));
            Files.deleteIfExists(root.resolve("small.txt"));
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FilesFindAttributesDemo.java
java FilesFindAttributesDemo
~~~

Stdout:

~~~text
level1Count=1
level2Count=2
rootOnly=1
~~~

Giải thích:

- `level1Count=1` vì chỉ `large.txt` nằm ngay dưới root với 5 byte và khớp điều kiện; `small.txt` có 1 byte, `deep.txt` ở cấp 2.
- `level2Count=2` vì khi mở rộng đến cấp 2, `deep.txt` có 4 byte cũng được nhận. `lastModifiedTime()` là thuộc tính `FileTime` do provider cung cấp; ví dụ kiểm tra sự hiện diện của đối tượng thay vì in một ngày giờ thay đổi theo máy.
- `rootOnly=1` minh họa `maxDepth=0` chỉ xét chính thư mục bắt đầu và matcher nhận nó vì `isDirectory()`.

Dù ví dụ cho stdout cố định trong môi trường bình thường, quyền tệp, thời điểm bị xóa bởi tiến trình khác hoặc file system đặc biệt vẫn có thể tạo lỗi I/O mà chương trình phải xử lý.

## 12. Đường dẫn tương đối, tuyệt đối và so sánh với root

Khi xử lý kết quả của `Files.find`, `Path` trả về có ngữ cảnh tương ứng với `start`; code hiển thị thường dùng:

~~~java
// Mảnh mã minh họa: path được tạo từ kết quả tìm kiếm dưới root.
Path relative = root.relativize(path);
System.out.println(relative);
~~~

`Path.relativize(...)` yêu cầu các đường dẫn có thể tương đối hóa theo quy tắc của provider (trên default file system, không trộn bừa absolute và relative). Để logic dễ kiểm chứng, nên chuẩn hóa cách xác định `root` trước khi gọi `find` và không ghép string từ nhiều file system không tương thích.

Nếu muốn đối chiếu path theo **thành phần**, dùng `startsWith(Path)`/`endsWith(Path)` chứ không dùng tiền tố ký tự trên `toString()`. Nhưng phép kiểm tra lexical `candidate.normalize().startsWith(root.normalize())` **không phải hàng rào bảo mật đầy đủ** khi có symbolic link và thay đổi đồng thời của filesystem.

### Một số matcher hữu ích

~~~java
// Mảnh mã minh họa (cần đặt trong một phương thức).
(path, attrs) ->
        attrs.isRegularFile()
        && path.getFileName() != null
        && path.getFileName().toString().startsWith("report-")
~~~

~~~java
// Mảnh mã minh họa.
(path, attrs) -> attrs.isDirectory() && !path.equals(root)
~~~

~~~java
// Mảnh mã minh họa: chỉ lấy tên file, không dựa vào tên thư mục cha.
(path, attrs) -> attrs.isRegularFile()
        && path.getFileName() != null
        && path.getFileName().toString().endsWith(".json")
~~~

Các predicate trên kiểm tra điều kiện **tên hoặc loại mục**, không tự đọc hay xác thực nội dung JSON/tệp báo cáo. Nếu cần phân tích nội dung, thực hiện sau khi tìm được đường dẫn, với cơ chế đọc và kiểm tra bảo mật phù hợp.

## 13. Hiệu năng và tài nguyên khi tìm trong cây lớn

`Files.find` là lựa chọn gọn, nhưng cần cân nhắc chi phí:

- **Tổng số thư mục/mục được duyệt:** matcher đơn giản không có nghĩa chỉ truy cập những mục đã khớp; cây lớn vẫn có thể cần đi qua rất nhiều thư mục.
- **Giới hạn độ sâu:** `maxDepth` giúp ngăn duyệt vào vùng quá sâu, nhưng không giới hạn số mục trong các cấp đó.
- **Chi phí thuộc tính:** `Files.find` lấy `BasicFileAttributes` cho từng mục được xét. Trên ổ mạng hoặc provider từ xa, thao tác truy vấn thuộc tính có thể đáng kể.
- **Ngưỡng bộ nhớ:** `Stream` lazy giảm nhu cầu tích lũy khi tiêu thụ tuần tự, nhưng `sorted()`, `toList()`, `collect(...)` có thể giữ hàng nghìn/hàng triệu kết quả trong RAM.
- **Không có thứ tự duyệt ổn định theo hợp đồng:** nếu yêu cầu thứ tự chính xác, cần sắp xếp có chủ đích, đồng thời chấp nhận chi phí bộ nhớ.
- **Không tự xử lý lỗi từng nhánh theo policy tùy chỉnh:** nếu cần bỏ qua một thư mục lỗi mà vẫn tiếp tục các nhánh khác, `walkFileTree` với `visitFileFailed` có thể phù hợp hơn.
- **Không suy ra nội dung file từ thuộc tính:** `attrs.size()` giúp lọc kích thước, không đảm bảo file có nội dung đúng định dạng, cũng không chống nội dung thay đổi sau khi kiểm tra.
- **Không tự giới hạn thời gian duyệt:** khi cây hoặc file system bị chậm, cần cân nhắc chạy trong thành phần có quản lý tài nguyên, giới hạn tác vụ và chính sách hủy phù hợp với API/hệ điều hành.

Nếu chỉ cần kiểm tra một file đã biết, gọi trực tiếp `Files.readAttributes(path, BasicFileAttributes.class)` hoặc phương thức chuyên dụng có thể đơn giản hơn việc duyệt cả cây.

## 14. Các lỗi thường gặp

| Sai sót | Hệ quả | Cách đúng |
|---|---|---|
| Gọi `Files.find` rồi không đóng stream | Rò rỉ handle duyệt thư mục, đặc biệt trong chương trình chạy lâu | Dùng `try-with-resources` |
| Nghĩ `maxDepth=1` chỉ duyệt root | Root là cấp 0; cấp 1 còn có các con trực tiếp | Vẽ rõ cây và cấp |
| Nghĩ matcher `false` cho thư mục sẽ bỏ qua toàn bộ cây con | `Files.find` chọn kết quả, không hỗ trợ `SKIP_SUBTREE` từ matcher | Dùng `walkFileTree` khi cần prune |
| Dùng `Path.endsWith(".txt")` để kiểm tra extension | `Path.endsWith` so thành phần tên | `getFileName().toString().endsWith(".txt")` |
| Không kiểm tra `getFileName() == null` | Đường dẫn root có thể không có phần tử tên cuối | Kiểm tra null |
| Dùng `Files.size(path)` cho mọi kết quả | Truy vấn I/O thừa và có thể gặp race | Tận dụng `attrs.size()` khi phù hợp |
| Mặc định bật `FOLLOW_LINKS` mà không xét vòng lặp | Có thể duyệt ngoài phạm vi dự tính hoặc gặp loop | Chọn chính sách link tường minh |
| Cho rằng `Files.find` trả danh sách đã duyệt hoàn tất | Stream lazy, lỗi có thể xảy ra lúc terminal operation | Xử lý `IOException` và `UncheckedIOException` |
| Cho rằng kết quả có thứ tự alphabet | Không được bảo đảm | `sorted()` nếu cần và bộ nhớ cho phép |
| Dùng `count()` xong tiếp tục `forEach` cùng stream | Stream chỉ tiêu thụ một lần | Tạo stream mới hoặc thiết kế pipeline một lượt |
| Cho rằng timestamp/size không bao giờ đổi | File system có thể thay đổi trong khi duyệt | Xử lý trạng thái thực tế khi mở/sử dụng |
| Dùng đường dẫn tìm thấy như chứng nhận truy cập an toàn | Symlink/TOCTOU có thể làm thay đổi đích vật lý | Kết hợp chính sách filesystem và thao tác mở an toàn |

## 15. Checklist trước khi dùng trong ứng dụng thật

1. Xác định `start` và `maxDepth`, tránh duyệt cả ổ đĩa nếu chỉ cần một cây con.
2. Viết predicate kết hợp `Path` và `BasicFileAttributes`; kiểm tra `attrs.isRegularFile()` trước khi dùng size theo nghĩa file thường.
3. Kiểm tra `path.getFileName() != null` trước khi xử lý tên.
4. Quyết định chính sách **có theo symbolic link không**, hiểu các rủi ro về loop và vượt phạm vi.
5. Đặt `Files.find(...)` trong `try-with-resources`, kể cả khi chỉ dùng `count()` hoặc `findFirst()`.
6. Xử lý cả ngoại lệ lúc tạo stream và lỗi được bọc `UncheckedIOException` khi duyệt.
7. Nếu kết quả cần ổn định thứ tự, dùng `sorted()`; nếu dữ liệu rất lớn, cân nhắc chi phí bộ nhớ.
8. Nếu cần bỏ qua nhánh hoặc điều khiển lỗi từng file, chuyển sang `walkFileTree`.
9. Không coi `BasicFileAttributes` là trạng thái bất biến; có thể phải kiểm tra lại khi truy cập file thật.
10. Kiểm thử với cây có thư mục rỗng, file có size 0, độ sâu biên, symlink và file biến mất trong khi tìm.

## 16. Tóm tắt

`Files.find(start, maxDepth, matcher, options...)` duyệt một cây đường dẫn và trả `Stream<Path>` gồm các mục khớp **`BiPredicate<Path, BasicFileAttributes>`**. `Path` mô tả tên/vị trí, còn `BasicFileAttributes` cung cấp loại mục, kích thước và thời gian. Dùng `maxDepth` để giới hạn độ sâu, chọn `FOLLOW_LINKS` có chủ đích và **luôn đóng stream**.

So với `Files.walk(...)`, `Files.find(...)` đặc biệt hữu ích khi matcher cần thuộc tính file sẵn có. Nhưng nếu phải cắt bỏ một cây con hoặc điều khiển lỗi theo từng nhánh, `Files.walkFileTree(...)` phù hợp hơn. Không nhầm việc lọc thuộc tính với xác thực nội dung hay kiểm soát quyền truy cập filesystem.

### Tham khảo chính thức

- [Java SE 17 — Files.find](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#find(java.nio.file.Path,int,java.util.function.BiPredicate,java.nio.file.FileVisitOption...))
- [Java SE 17 — BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html)
- [Java SE 17 — FileVisitOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html)
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
