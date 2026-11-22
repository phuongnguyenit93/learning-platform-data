# Files.find với Path và BasicFileAttributes trong Java

> **Module:** Java 8 — **Tệp và I/O**. Bài học tập trung vào `Files.find` của NIO.2: cách tìm file đệ quy theo **đường dẫn** và **metadata** một cách hiệu quả, khai báo `maxDepth`, xử lý `Stream<Path>` và I/O exceptions, phân biệt symbolic links, rồi lựa chọn đúng giữa `find`, `walk`, `list` và `walkFileTree`. Những API được trình bày có từ Java 8 và **vẫn được dùng trên Java hiện hành**.

## 1. Tình huống thực tế: tìm file dựa trên tên và thuộc tính

Giả sử ứng dụng cần tìm tất cả file `.txt` lớn hơn một số byte nhất định trong cây thư mục:

~~~text
project/
├── root.txt               (4 bytes)
├── docs/
│   ├── alpha.txt          (5 bytes)
│   ├── beta.log           (9 bytes)
│   └── sub/
│       └── deep.txt       (7 bytes)
└── images/
    └── icon.bin           (4 bytes)
~~~

Có hai loại điều kiện khác nhau:

1. **Điều kiện trên `Path`:** tên file, đuôi mở rộng, parent, relative path hoặc cấu trúc thư mục.
2. **Điều kiện trên `BasicFileAttributes`:** loại tệp (regular file, directory, symlink), kích thước theo byte, thời điểm chỉnh sửa và metadata cơ bản khác.

`Files.find` kết hợp cả hai trong một `BiPredicate<Path, BasicFileAttributes>`:

~~~java
Path root = Paths.get("project");

try (Stream<Path> matches = Files.find(root, 3,
        (path, attrs) ->
                attrs.isRegularFile()
                && path.getFileName().toString().endsWith(".txt")
                && attrs.size() >= 5)) {
    matches.forEach(System.out::println);
}
~~~

Đây là **đoạn minh họa**: nó giả định thư mục `project` tồn tại và cần import `Path`, `Paths`, `Files`, `Stream`. Nếu không có thư mục thực trên máy, đoạn code sẽ ném lỗi I/O; chương trình runnable ở cuối bài sẽ tự tạo và dọn cây thư mục mẫu.

Với cây dữ liệu trên và `maxDepth=3`, `docs/alpha.txt` và `docs/sub/deep.txt` đạt điều kiện. `root.txt` bị loại vì chỉ 4 bytes; `beta.log` bị loại vì không có hậu tố `.txt`.

### 1.1. Vì sao không chỉ dùng Files.list?

`Files.list(dir)` liệt kê **một cấp** các entry trực tiếp của directory. Nếu muốn tìm sâu trong các thư mục con, cần đi sâu hơn bằng `Files.find`, `Files.walk` hoặc `walkFileTree`.

### 1.2. Vì sao không gọi Files.size cho mỗi path?

Một cách khác là duyệt mọi path rồi gọi `Files.isRegularFile` và `Files.size`:

~~~java
// Chỉ là một cách tương đương về mục tiêu, không nhất thiết tối ưu:
try (Stream<Path> paths = Files.walk(root, 3)) {
    // Lọc Path rồi gọi thêm các hàm đọc metadata.
}
~~~

`Files.walk` đã cần đọc `BasicFileAttributes` khi đi qua entries. `Files.find` đưa attributes đó trực tiếp vào matcher, nên **có thể tránh những lần đọc attributes dư thừa**, như Javadoc nêu. Tuy nhiên “có thể hiệu quả hơn” **không có nghĩa nhanh hơn trong mọi workload**; cần đo trong hệ thống thực.

## 2. Chữ ký chính xác của Files.find

Java 8 công bố method:

~~~java
public static Stream<Path> find(
        Path start,
        int maxDepth,
        BiPredicate<Path, BasicFileAttributes> matcher,
        FileVisitOption... options)
        throws IOException
~~~

Package và import thông dụng:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.FileVisitOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.function.BiPredicate;
import java.util.stream.Stream;
~~~

Giải thích từng tham số:

| Tham số | Kiểu | Vai trò |
| --- | --- | --- |
| `start` | `Path` | File hoặc thư mục bắt đầu tìm kiếm; bản thân start cũng thuộc tập được duyệt |
| `maxDepth` | `int` | Độ sâu **tối đa** tính từ `start`; 0 nghĩa chỉ kiểm tra start |
| `matcher` | `BiPredicate<Path,BasicFileAttributes>` | Nhận mỗi path và attrs, trả true nếu muốn đưa path đó vào stream |
| `options` | `FileVisitOption...` | Tùy chọn duyệt cây; thường bỏ trống hoặc `FOLLOW_LINKS` |
| Giá trị trả | `Stream<Path>` | Luồng path được lọc, **duyệt lazy**, phải đóng |

**Chỉ có overload `find(start,maxDepth,matcher,options...)`**, không có overload `Files.find(start,matcher)` chuẩn. Nếu muốn duyệt hết toàn bộ độ sâu, có thể truyền `Integer.MAX_VALUE` với ý thức về rủi ro tài nguyên.

### 2.1. Một matcher đơn giản

~~~java
BiPredicate<Path, BasicFileAttributes> onlyRegularFiles =
        (path, attrs) -> attrs.isRegularFile();

try (Stream<Path> found = Files.find(
        Paths.get("project"), 2, onlyRegularFiles)) {
    found.forEach(System.out::println);
}
~~~

Đây là **đoạn minh họa** cần directory thực. `BiPredicate` có hai tham số, khác `Predicate<Path>` của `Stream.filter`. Dù chưa dùng `path` trong predicate, tên tham số vẫn thể hiện cặp dữ liệu được truyền.

### 2.2. Trả true không có nghĩa dừng tìm kiếm

`matcher` chỉ quyết định **entry hiện tại có được phát vào stream không**. `false` đối với một directory **không mặc nhiên cắt bỏ nhánh con** của directory đó.

~~~java
try (Stream<Path> found = Files.find(root, 10,
        (path, attrs) -> attrs.isRegularFile())) {
    // Directory không được phát ra vì matcher trả false,
    // nhưng các directory được phép duyệt vẫn có thể được mở,
    // và file con vẫn có thể được xét.
}
~~~

Điều này khác `walkFileTree`, nơi `preVisitDirectory` có thể trả `SKIP_SUBTREE` để chủ động không đi vào một nhánh.

### 2.3. Path và attributes là dữ liệu của cùng entry

Với mỗi file/directory mà traversal xét, matcher nhận:

- Một `Path` được tạo khi đi từ `start` tới entry đó.
- `BasicFileAttributes` được traversal lấy để mô tả entry đó theo semantics của tùy chọn follow links.

Matcher có thể kết hợp:

~~~java
(path, attrs) -> attrs.isRegularFile()
        && attrs.size() > 1024
        && path.getFileName().toString().endsWith(".csv")
~~~

Không cần gọi lại `Files.readAttributes(path, BasicFileAttributes.class)` bên trong matcher chỉ để có cùng nhóm metadata — làm vậy có thể gây một I/O query nữa và tạo khoảng cách thời gian giữa hai lần quan sát.

## 3. maxDepth: mức 0, 1, 2 và sâu hơn

`maxDepth` **không** đếm số file; nó đếm khoảng cách theo mức thư mục từ `start`.

~~~text
project/                     depth 0
├── root.txt                 depth 1
├── docs/                    depth 1
│   ├── alpha.txt            depth 2
│   ├── beta.log             depth 2
│   └── sub/                 depth 2
│       └── deep.txt         depth 3
└── images/                  depth 1
    └── icon.bin             depth 2
~~~

Ví dụ:

| `maxDepth` | Entry nào được xét? | Các file `.txt` thường thấy |
| --- | --- | --- |
| 0 | Chỉ `project/` (start) | Không có, vì start là directory |
| 1 | Start và entry con trực tiếp | `root.txt` |
| 2 | Thêm entry ở cấp 2 | `root.txt`, `docs/alpha.txt` |
| 3 | Thêm entry cấp 3 | `root.txt`, `docs/alpha.txt`, `docs/sub/deep.txt` |

Nếu `start` trỏ tới **một regular file**, traversal vẫn xét chính file đó ở depth 0. Vì thế `Files.find(file,0,(p,a)->a.isRegularFile())` có thể trả stream chứa một Path.

### 3.1. Giá trị âm

~~~java
// PHẢN VÍ DỤ:
Files.find(root, -1, (path, attrs) -> true);
~~~

`maxDepth < 0` là tham số không hợp lệ và gây `IllegalArgumentException`. Đừng dùng số âm để mang nghĩa “không giới hạn”. Nếu thật sự cần duyệt toàn bộ, dùng `Integer.MAX_VALUE` hoặc giới hạn có chủ đích theo nhu cầu.

### 3.2. Không tự suy độ sâu từ số dấu phân cách

`Path` có khả năng xử lý separator theo filesystem provider; không nên tự đếm ký tự `'/'` trong path. Để kiểm tra relative path:

~~~java
Path relative = root.relativize(path);
int nameCount = relative.getNameCount();
~~~

Đây là đoạn minh họa với `root` và `path` tương thích. Lưu ý số lượng name components của start itself/các path rỗng có khác biệt biểu diễn giữa provider; **`maxDepth` của Files.find là nguồn hợp đồng chính**, không cần tự tính lại trong matcher.

### 3.3. Giới hạn độ sâu còn là giới hạn nguồn lực

Duyệt `Integer.MAX_VALUE` có thể đi rất sâu qua hàng triệu entries, mount lớn hoặc symbolic links (nếu follow). Đặt giới hạn phù hợp khi:

- Chỉ kiểm tra folder nhập liệu.
- Chỉ tìm trong cấu trúc project có độ sâu đã biết.
- Không tin tưởng đầy đủ vào cây thư mục user chọn.
- Muốn tránh đọc cả ổ đĩa khi một relative path sai.

Tuy nhiên `maxDepth` **không tự giới hạn số entry trong mỗi cấp**. Một directory cấp 1 có một triệu files vẫn có thể khiến traversal tốn I/O lớn.

## 4. BasicFileAttributes: dùng metadata đúng chỗ

`BasicFileAttributes` trong `java.nio.file.attribute` cung cấp các thuộc tính cơ bản chung cho nhiều file systems. Các method nổi bật:

| Method | Kiểu | Ý nghĩa/điều cần biết |
| --- | --- | --- |
| `isRegularFile()` | `boolean` | File thường; hay dùng để loại directories |
| `isDirectory()` | `boolean` | Entry thuộc loại directory |
| `isSymbolicLink()` | `boolean` | Entry được nhìn nhận là symbolic link theo chế độ duyệt |
| `isOther()` | `boolean` | Không thuộc regular/directory/symlink |
| `size()` | `long` | Kích thước **byte**, không phải số ký tự |
| `lastModifiedTime()` | `FileTime` | Mốc chỉnh sửa cuối; độ chính xác phụ thuộc file system |
| `lastAccessTime()` | `FileTime` | Mốc truy cập cuối, có thể không được hỗ trợ/chính xác như kỳ vọng |
| `creationTime()` | `FileTime` | Mốc tạo, có thể là default khi file system không lưu |
| `fileKey()` | `Object` | Khóa nhận dạng file tùy provider, **có thể null** |

### 4.1. isRegularFile trước khi đọc size

~~~java
(path, attrs) ->
        attrs.isRegularFile()
        && attrs.size() >= 5_000_000L
~~~

Đây là **lambda minh họa**. Số `5_000_000L` là **5 triệu byte**, không phải 5 MiB. Nếu muốn 5 MiB, dùng `5L * 1024 * 1024`.

`attrs.size()` với directory hoặc loại file đặc biệt có semantics phụ thuộc file system. Vì vậy, kiểm tra `attrs.isRegularFile()` trước bằng `&&` thường hợp lý khi business muốn tìm **file thường**.

### 4.2. byte khác character count

Một file UTF-8 chứa 1.000 ký tự tiếng Việt không nhất thiết có size=1.000. `size()` trả byte-level metadata, không mở file để đếm ký tự. Nếu bài toán cần số dòng, số ký tự hoặc phân tích nội dung, phải đọc file **sau khi đã chọn path** và với cơ chế streaming/charset phù hợp.

### 4.3. lastModifiedTime

Ví dụ chỉ chọn file chỉnh sửa sau một mốc:

~~~java
Instant cutoff = Instant.parse("2024-01-01T00:00:00Z");

BiPredicate<Path, BasicFileAttributes> recentRegular =
        (path, attrs) -> attrs.isRegularFile()
                && attrs.lastModifiedTime().toInstant().isAfter(cutoff);
~~~

Đây là **đoạn minh họa**, cần import `java.time.Instant` và khai báo trong method/class. `FileTime` không phải local date/time mang timezone người dùng; so sánh qua `Instant` giúp tránh gán nghĩa timezone tùy tiện.

**Hạn chế:** file system có thể chỉ lưu time với một độ phân giải nhất định, hoặc dùng default khi một loại timestamp không được hỗ trợ. Không biến metadata filesystem thành chứng cứ thời gian có độ chính xác pháp lý tuyệt đối.

### 4.4. creationTime và lastAccessTime có thể không như mong đợi

- Một số file system không lưu chính xác creation time và dùng default.
- Access time có thể bị cấu hình không cập nhật thường xuyên để giảm I/O.
- Copy/move file có thể làm thay đổi metadata tùy provider và option.

Khi nghiệp vụ cần “thời điểm upload” hay “đã xem lần cuối”, nguồn tin cậy thường là record ứng dụng/database, không nhất thiết là `attrs.creationTime()` hoặc `attrs.lastAccessTime()`.

### 4.5. fileKey có thể null và không phải business ID

`fileKey()` có thể được dùng bởi file tree traversal trong một số cơ chế phát hiện cycle, nhưng kiểu là `Object` provider-specific. Không serialize `fileKey().toString()` làm primary key cho database, không dựa vào nó ổn định xuyên restart/copy hoặc mọi OS.

~~~java
Object key = attrs.fileKey();
if (key != null) {
    // Chỉ dùng theo hợp đồng file system cụ thể nếu cần.
}
~~~

### 4.6. Attributes là một quan sát, không phải khóa file

`BasicFileAttributes` đã được lấy tại một thời điểm trong quá trình đi qua file. **Không có giao dịch giữ nguyên file giữa lúc matcher đọc metadata và lúc caller mở file sau đó.** File có thể bị rename/delete/sửa size; đây là vấn đề TOCTOU (*time of check to time of use*).

Nếu đúng đắn hoặc bảo mật yêu cầu file không bị thay giữa check và dùng, cần thiết kế file handle, resource ownership, atomic move, locking hoặc cơ chế dành riêng cho file provider; `Files.find` không tự đóng băng cây thư mục.

## 5. BiPredicate<Path,BasicFileAttributes>: kết hợp điều kiện

### 5.1. Chỉ các file có đuôi .txt

~~~java
BiPredicate<Path, BasicFileAttributes> txt =
        (path, attrs) ->
                attrs.isRegularFile()
                && path.getFileName() != null
                && path.getFileName().toString().endsWith(".txt");
~~~

Đây là **đoạn minh họa**, đã dùng attrs kiểm tra loại tệp và Path lấy tên. `getFileName()` có thể cần xử lý null nếu code thao tác với special root paths; thêm check phù hợp giúp predicate bền hơn.

### 5.2. Tên file không phân biệt chữ hoa/chữ thường theo policy ứng dụng

~~~java
BiPredicate<Path, BasicFileAttributes> txtIgnoreCase =
        (path, attrs) ->
                attrs.isRegularFile()
                && path.getFileName() != null
                && path.getFileName().toString()
                        .toLowerCase(Locale.ROOT).endsWith(".txt");
~~~

Đây là **đoạn minh họa**, cần import `java.util.Locale`. Không dựa vào locale máy để case-fold tên file. Tuy nhiên, **semantics case sensitivity thực tế của file system** khác giữa môi trường; việc hạ chữ chỉ là policy lọc của ứng dụng, không chứng minh hai file names có cùng identity.

### 5.3. Theo tên và kích thước

~~~java
BiPredicate<Path, BasicFileAttributes> largeLog =
        (path, attrs) -> attrs.isRegularFile()
                && attrs.size() > 10L * 1024 * 1024
                && path.getFileName() != null
                && path.getFileName().toString().endsWith(".log");
~~~

`10L * 1024 * 1024` biểu diễn 10 MiB theo bytes. Điều kiện `>` khác `>=`; phải chọn theo yêu cầu thật. Code không đọc nội dung log.

### 5.4. Theo thư mục tương đối

~~~java
BiPredicate<Path, BasicFileAttributes> insideReports =
        (path, attrs) -> attrs.isRegularFile()
                && root.relativize(path).startsWith("reports");
~~~

Đây là **đoạn minh họa**, `root` là Path start đã xác định; các Path phải cùng filesystem provider/kiểu absolute tương thích. `startsWith("reports")` so sánh **name component**, không phải một phép substring trên path string.

Tuy nhiên, predicate này **không prune** những directories khác: nó vẫn có thể duyệt các nhánh không bắt đầu bằng `reports` rồi loại file của nhánh đó khỏi kết quả. Nếu muốn thật sự tránh đi vào các nhánh khác, bắt đầu trực tiếp từ `root.resolve("reports")` khi được phép, hoặc dùng `walkFileTree` với `SKIP_SUBTREE`.

### 5.5. Theo suffix và file age

~~~java
Instant nowCutoff = Instant.parse("2025-01-01T00:00:00Z");

BiPredicate<Path, BasicFileAttributes> archiveCandidate =
        (path, attrs) -> attrs.isRegularFile()
                && attrs.size() > 0L
                && attrs.lastModifiedTime().toInstant()
                        .isBefore(nowCutoff)
                && path.getFileName().toString().endsWith(".log");
~~~

Đây là **đoạn minh họa**, không phải chương trình xóa file. Nếu sau khi tìm thấy bạn định xóa/di chuyển, cần một policy **revalidate** và xử lý race. Đừng chỉ dựa vào một metadata check để xóa file có thể đang bị ghi.

### 5.6. Matcher nên ngắn, thuần và ít tác dụng phụ

Tránh:

~~~java
(path, attrs) -> {
    Files.delete(path); // PHẢN VÍ DỤ: không xóa file trong predicate.
    return true;
}
~~~

Đoạn trên là **phản ví dụ không độc lập** vì `Files.delete` ném checked `IOException` mà lambda `BiPredicate.test` không khai báo; cũng không nên biến traversal thành thao tác sửa cây ngay trong matcher.

**Lý do thiết kế:** predicate có nhiệm vụ **quyết định file có được xuất hiện trong stream hay không**, không phải thực hiện side effect phức tạp. Mutation trong lúc traversal khiến danh sách đang duyệt thay đổi, tăng TOCTOU và làm lỗi xử lý khó suy luận. Nếu cần thao tác file, hãy thu thập danh sách với giới hạn rõ ràng, sau đó xử lý và revalidate theo một workflow riêng.

## 6. Duyệt lazy và nghĩa vụ đóng Stream

`Files.find` trả `Stream<Path>` **lazily populated**: file tree được đi qua khi bạn consume stream, không phải toàn bộ danh sách path đã được xây sẵn lúc gọi `Files.find`.

~~~java
try (Stream<Path> found = Files.find(
        root, 3, (path, attrs) -> attrs.isRegularFile())) {
    long count = found.count();
    System.out.println(count);
}
~~~

Đây là đoạn Java 8 minh họa. Vì traversal có thể giữ **một hoặc nhiều directory đang mở**, stream **phải được đóng**, kể cả khi terminal operation ném exception.

### 6.1. try-with-resources là mẫu mặc định

~~~java
try (Stream<Path> paths = Files.find(root, 5, matcher)) {
    paths.forEach(this::processPath);
}
~~~

Đây là đoạn minh họa trong một method có `root`, `matcher` và `processPath`; không phải source độc lập. Khi ra khỏi `try`, `close()` được gọi dù normal return hay exception.

**Đừng trả một Stream<Path> từ bên trong try-with-resources** nếu caller còn cần consume: stream đã bị đóng tại thời điểm method trả. Nếu API muốn trả lazy stream cho caller, phải **chuyển trách nhiệm đóng stream** một cách minh bạch; trong nhiều ứng dụng đơn giản hơn là trả `List<Path>` có giới hạn hoặc nhận callback xử lý bên trong method.

### 6.2. Short-circuit không tự đóng stream

~~~java
try (Stream<Path> found = Files.find(root, 10,
        (path, attrs) -> attrs.isRegularFile())) {
    Optional<Path> one = found.findFirst();
    // Dù chỉ lấy một, vẫn đóng stream nhờ try-with-resources.
}
~~~

Đây là đoạn minh họa cần `java.util.Optional`. Các terminal ops `findFirst()`, `anyMatch()`, `limit(n)` không tự thay thế việc gọi `close`. Chúng có thể dừng sớm một phần traversal, nhưng vẫn cần release resources.

### 6.3. Không giả định thứ tự file names

Files traversal theo cơ chế walk depth-first, nhưng **thứ tự giữa các siblings không được bảo đảm phù hợp cho một danh sách nghiệp vụ nhất quán**. Trên nhiều OS/filesystem, order có thể khác. Để có output deterministic, sort sau khi chuyển sang relative form.

~~~java
try (Stream<Path> found = Files.find(root, 3, matcher)) {
    List<Path> sorted = found.sorted().collect(Collectors.toList());
}
~~~

Đây là đoạn minh họa, cần import `Collectors`. `sorted()` có thể buộc materialize nhiều entries; với thư mục khổng lồ phải cân nhắc memory. Cũng đừng dựa vào `findFirst()` chọn đúng một file “đầu tiên theo alphabet”, trừ khi đã thiết lập thứ tự mà business thực sự yêu cầu và chi phí phù hợp.

### 6.4. Stream một lần

Một `Stream` không được thiết kế để chạy nhiều terminal operations trên cùng instance:

~~~java
// PHẢN VÍ DỤ:
Stream<Path> stream = Files.find(root, 5, matcher);
long count = stream.count();
// stream.forEach(...); // Không được reuse stream đã consumed.
~~~

Nếu muốn dùng tập kết quả nhiều lần, collect trong try-with-resources rồi sử dụng `List<Path>` sau đó; nhớ rằng paths có thể trở nên stale trong thời gian chờ xử lý.

### 6.5. Không mặc định parallel() sẽ tăng tốc

~~~java
try (Stream<Path> found = Files.find(root, 8, matcher)) {
    found.parallel().forEach(path -> processPath(path));
}
~~~

Đây là **đoạn minh họa**, cần method `processPath`. Traversal phụ thuộc directory I/O và file tree, không giống một mảng in-memory có thể chia đều tự do. `parallel()` không bảo đảm tốt hơn, và action phải thread-safe. Nếu tác vụ cần concurrency có giới hạn, có thể tách giai đoạn tìm path với giai đoạn xử lý trên executor riêng, đi kèm backpressure.

## 7. IOException khi mở và UncheckedIOException khi đang duyệt

`Files.find` khai báo `throws IOException` cho những lỗi xảy ra **khi mở/kiểm tra start**. Nhưng traversal là lazy, nên lỗi truy cập directory xảy ra **sau khi method đã trả stream** sẽ được gói trong `UncheckedIOException` và phát ra khi consume.

### 7.1. Mẫu xử lý hai đường

~~~java
try (Stream<Path> found = Files.find(
        root, 5, (path, attrs) -> attrs.isRegularFile())) {
    found.forEach(System.out::println);
} catch (UncheckedIOException ex) {
    // Lỗi I/O xảy ra trong quá trình duyệt lazy.
    IOException cause = ex.getCause();
    System.err.println("Traversal failed: " + cause.getMessage());
} catch (IOException ex) {
    // Lỗi I/O khi bắt đầu tìm kiếm hoặc lúc đóng stream.
    System.err.println("Cannot start search: " + ex.getMessage());
}
~~~

Đây là **đoạn minh họa**. Vị trí exception còn phụ thuộc trình tự acquire/consume/close; mẫu phân biệt checked và unchecked giúp tránh bỏ sót lỗi lazy.

### 7.2. Không bắt IOException rồi giả định mọi lỗi traversal đã được xử lý

~~~java
// PHẢN VÍ DỤ: chỉ catch checked IOException chưa bao quát lỗi lazy.
try (Stream<Path> found = Files.find(root, 100, matcher)) {
    found.forEach(System.out::println);
} catch (IOException ex) {
    log(ex);
}
~~~

`log` là method minh họa. Một `UncheckedIOException` trong terminal operation có thể đi qua catch này. Ứng dụng cần policy xử lý, báo cáo hoặc fail phù hợp.

### 7.3. Một thư mục không đọc được có thể làm dừng stream

Đừng coi `Files.find` là bộ crawler “bỏ qua mọi entry bị lỗi rồi cứ tiếp tục”. Tùy lúc phát sinh IOException, stream operation có thể ném `UncheckedIOException` và traversal bị dừng. Nếu cần **xử lý lỗi từng path/nhánh rồi tiếp tục**, `Files.walkFileTree` với `SimpleFileVisitor.visitFileFailed` và `postVisitDirectory` thường có quyền điều khiển tốt hơn.

### 7.4. Một file biến mất trong lúc duyệt

Nếu file bị delete/rename giữa lúc directory trả entry và lúc lấy attrs, traversal có thể gặp I/O error. Không kết luận “cây có file” từ result matcher rồi đảm bảo lần mở file tiếp theo chắc thành công. Với dữ liệu thay đổi đồng thời, mỗi thao tác phải chịu được trường hợp file không còn tồn tại.

### 7.5. maxDepth âm và matcher null

- `maxDepth < 0` là input không hợp lệ (IllegalArgumentException).
- `start`, `matcher` hoặc options không hợp lệ có thể gây những runtime exceptions tương ứng.
- Đừng biến exceptions do programmer error thành danh sách rỗng nếu app cần phát hiện sai cấu hình.

Cần validate đầu vào public API trước khi khởi tạo traversal lớn.

## 8. Symbolic links và FOLLOW_LINKS

Mặc định, `Files.find` và `Files.walk` **không tự động đi theo symbolic links**. Đó là một lựa chọn an toàn hơn cho traversal thông thường.

### 8.1. Không follow links

~~~java
try (Stream<Path> found = Files.find(root, 8,
        (path, attrs) -> attrs.isRegularFile())) {
    // Theo mặc định, symlink không được duyệt theo target.
}
~~~

Khi không follow, `BasicFileAttributes` của symbolic link thường xác định nó là symlink thay vì regular file của target. Vì thế, predicate `attrs.isRegularFile()` **không mặc nhiên nhận những symlink trỏ tới file thường**.

### 8.2. Có chủ đích follow links

~~~java
try (Stream<Path> found = Files.find(root, 8,
        (path, attrs) -> attrs.isRegularFile(),
        FileVisitOption.FOLLOW_LINKS)) {
    // Có thể tìm cả nội dung được truy cập qua symlink target.
}
~~~

Nếu tùy chọn `FOLLOW_LINKS` hiện diện, traversal đi theo symlinks tới target theo hợp đồng. **Rủi ro:** một link có thể dẫn tới thư mục ngoài phạm vi tưởng tượng ban đầu, dẫn đến trùng lặp dữ liệu, cây lớn hoặc vòng lặp.

### 8.3. Detect cycle

Khi follow links, Java cố phát hiện một directory trỏ về ancestor của nó bằng file keys hoặc so sánh cùng file; khi có cycle, lỗi được mô tả bằng `FileSystemLoopException`. Trong `Files.find` lazy traversal, lỗi có thể đến bên ngoài dạng `UncheckedIOException` với `getCause()` là `FileSystemLoopException`.

Không tự nuốt lỗi cycle rồi vô hạn retry. Cần chính sách path traversal rõ ràng.

### 8.4. LinkOption.NOFOLLOW_LINKS không phải FileVisitOption

Đây là lỗi compile-time rất phổ biến:

~~~java
// SAI KIỂU: find nhận FileVisitOption, không phải LinkOption.
// Files.find(root, 5, matcher, LinkOption.NOFOLLOW_LINKS);
~~~

`LinkOption.NOFOLLOW_LINKS` dùng trong những API như `Files.readAttributes`. `Files.find` dùng `FileVisitOption`; **không truyền FOLLOW_LINKS** là cách mặc định không follow.

### 8.5. Không giả định follow là an toàn với path không tin cậy

Nếu user có thể tạo/sửa symbolic links, một đường dẫn đang kiểm tra có thể bị đổi target giữa check và open. Với hệ thống bảo mật cao, cần cân nhắc provider support, permissions, restricted roots, atomic file handles hoặc API chuyên biệt. `Files.find` không tự cung cấp sandbox ngăn directory traversal attacks.

## 9. Files.find khác Files.walk, Files.list và walkFileTree thế nào?

| Công cụ | Độ sâu | Có attributes trong callback? | Dạng trả | Khi nào nên chọn |
| --- | --- | --- | --- | --- |
| `Files.list(dir)` | Một cấp con trực tiếp | Không truyền sẵn `BasicFileAttributes` | `Stream<Path>` | Liệt kê nhanh immediate entries |
| `Files.walk(root, depth)` | Đệ quy tới depth | Không trả attrs trong stream; cần đọc lại nếu filter theo metadata | `Stream<Path>` | Xử lý/path pipeline tổng quát |
| `Files.find(root,depth,matcher)` | Đệ quy tới depth | **Có**, trong `BiPredicate` | `Stream<Path>` chỉ matches | Tìm theo type, size, time, name |
| `Files.walkFileTree(root,visitor)` | Đệ quy, có maxDepth/options overload | **Có**, trong `visitFile`/`preVisitDirectory` | Điều khiển visitor | Cần prune, xử lý lỗi từng entry, xóa/copy traversal |
| `Files.newDirectoryStream(dir)` | Một cấp | Không sẵn `BasicFileAttributes` | `DirectoryStream<Path>` | Directory listing với resource quản lý rõ, provider-specific hiệu quả |

### 9.1. Dùng find khi điều kiện dựa vào metadata

Ví dụ lọc file lớn hơn 1 MiB bằng attrs:

~~~java
try (Stream<Path> found = Files.find(root, 10,
        (path, attrs) -> attrs.isRegularFile()
                && attrs.size() >= 1024L * 1024)) {
    long count = found.count();
}
~~~

Đây là đoạn minh họa. `find` nhận attrs ở matcher, có thể giúp giảm I/O metadata so với `walk(...).filter(p -> Files.size(p)...)` nếu logic cần cùng thông tin.

### 9.2. Dùng walk nếu chỉ cần đi qua Path hoặc áp dụng stream transforms

~~~java
try (Stream<Path> paths = Files.walk(root, 3)) {
    paths.forEach(System.out::println);
}
~~~

`walk` phát ra các paths khi duyệt mà không cần matcher. Lưu ý nếu muốn file-only, vẫn phải lọc; nếu filter bằng `Files.isRegularFile` có thể tạo các lần kiểm tra attributes khác.

### 9.3. Dùng list nếu không cần recursion

~~~java
try (Stream<Path> children = Files.list(root)) {
    children.forEach(System.out::println);
}
~~~

`list` chỉ phát entry trực tiếp của root, không tự đi vào thư mục con. Nó cũng trả resource-backed stream và phải đóng.

### 9.4. Dùng walkFileTree khi cần cắt nhánh

Ví dụ muốn tránh vào thư mục tên `.git`:

~~~java
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult preVisitDirectory(Path dir,
            BasicFileAttributes attrs) throws IOException {
        if (dir.getFileName() != null
                && dir.getFileName().toString().equals(".git")) {
            return FileVisitResult.SKIP_SUBTREE;
        }
        return FileVisitResult.CONTINUE;
    }

    @Override
    public FileVisitResult visitFile(Path file,
            BasicFileAttributes attrs) throws IOException {
        // Xử lý file theo nghiệp vụ.
        return FileVisitResult.CONTINUE;
    }
});
~~~

Đây là **đoạn minh họa trong method có `root`**, cần import `SimpleFileVisitor`, `FileVisitResult`, `IOException`. `SKIP_SUBTREE` giúp tránh descending vào nhánh không cần, khác matcher false của `Files.find`.

### 9.5. Dùng walkFileTree khi cần xử lý lỗi có chọn lọc

~~~java
@Override
public FileVisitResult visitFileFailed(Path file, IOException ex) {
    // Ghi nhận lỗi file, quyết định vẫn tiếp tục.
    return FileVisitResult.CONTINUE;
}
~~~

Đây là **đoạn method cần đặt trong FileVisitor**. Nó hữu ích trong utility scan lớn cho phép báo cáo những entries không đọc được mà không dừng toàn bộ công việc, nếu policy bảo mật/nghiệp vụ cho phép.

### 9.6. Không có “API nào mới hơn là tự động tốt hơn”

`Files.find` có từ Java 8 và vẫn hữu ích. `walkFileTree` được giới thiệu trước và vẫn rất phù hợp khi cần prune/error callbacks. `Files.list` vẫn là lựa chọn đúng cho một cấp. Chọn theo **loại traversal và mức điều khiển cần có**, không theo sự mới/cũ.

## 10. Hiệu năng và tài nguyên khi tìm file

### 10.1. Tránh đọc attrs hai lần nếu không cần

~~~java
// find đã cung cấp attrs:
try (Stream<Path> found = Files.find(root, 6,
        (path, attrs) -> attrs.isRegularFile()
                && attrs.size() >= 1000)) {
    // ...
}
~~~

`BasicFileAttributes` được cung cấp sẵn, không cần ngay lập tức gọi `Files.size(path)` chỉ để lặp lại cùng phép xét. Tuy nhiên, nếu ứng dụng cần trạng thái mới nhất ở thời điểm xử lý, nó có thể phải **đọc lại** và xử lý TOCTOU; lúc đó lần I/O bổ sung là yêu cầu correctness, không phải thừa.

### 10.2. Sử dụng maxDepth có chủ đích

`Files.find(root, Integer.MAX_VALUE, ...)` phù hợp khi thực sự cần scan toàn cây, nhưng với root do user truyền có thể rất tốn thời gian hoặc truy cập filesystem không mong đợi. Giới hạn độ sâu và thư mục gốc theo nghiệp vụ.

### 10.3. Filter kết quả không giống filter phần cây cần duyệt

Predicate chỉ lọc phát ra stream, không tránh chi phí đi vào directories. Một matcher:

~~~java
(path, attrs) ->
        attrs.isRegularFile()
        && path.toString().contains("reports")
~~~

không làm traversal bỏ qua thư mục `tmp`. Khi cần prune, dùng `walkFileTree` hoặc bắt đầu tìm từ subdirectory phù hợp.

### 10.4. File system là I/O, không phải array in-memory

Ngay cả với stream lazy, traversal phải mở thư mục và đọc metadata. Trên disk mạng, mount, container hoặc hàng triệu files, chi phí có thể lớn. Không gọi `Files.find` trực tiếp trên UI/event-loop thread nếu việc chờ I/O có thể gây trễ nghiêm trọng. Cân nhắc worker pool và cancellation/timeout theo kiến trúc ứng dụng.

### 10.5. sorted() và collect() có chi phí bộ nhớ

~~~java
try (Stream<Path> found = Files.find(root, 10, matcher)) {
    List<Path> paths = found.sorted()
            .collect(Collectors.toList());
}
~~~

Nếu 10 triệu matches, `collect` giữ một danh sách rất lớn. Cần thiết kế output streaming, phân trang ở tầng business hoặc giới hạn kết quả — nhưng giới hạn stream không làm biến `Files.find` thành một indexed search engine.

### 10.6. Không nhất thiết parallel hóa traversal

`parallel()` có thể làm complex processing chạy trên nhiều workers nhưng filesystem traversal bản thân có đặc thù I/O và không bảo đảm scale tốt. Điều khiển rõ giới hạn concurrency, tránh mở quá nhiều files đồng thời.

### 10.7. Không dùng một lần đo để khẳng định find nhanh hơn walk

Javadoc nói find **may be more efficient** khi tránh đọc lại BasicFileAttributes. Hiệu năng thật chịu ảnh hưởng OS cache, filesystem provider, device I/O, số file, predicate, tỷ lệ matches. Benchmark với directory fixture thực tế trước khi tối ưu.

## 11. Thiết kế API service trả kết quả từ Files.find

### 11.1. Trả về List<Path> nếu số match có giới hạn

~~~java
public static List<Path> findText(Path root, int depth)
        throws IOException {
    try (Stream<Path> paths = Files.find(root, depth,
            (path, attrs) -> attrs.isRegularFile()
                    && path.getFileName().toString().endsWith(".txt"))) {
        return paths.collect(Collectors.toList());
    }
}
~~~

Đây là **method minh họa** cần import các class phù hợp. Bên trong method, stream được đóng trước khi trả list. Caller không phải tự giải phóng directory handles, nhưng nếu kết quả rất lớn thì list có thể tốn memory và paths có thể stale sau đó.

### 11.2. Nếu cần streaming ra API, xác định ownership

Một phương thức trả `Stream<Path>` từ `Files.find` đặt trách nhiệm **đóng stream** lên caller. Nên ghi trong Javadoc của service, hoặc cung cấp helper nhận callback/function để đóng nội bộ. Không để stream tài nguyên sống qua nhiều request rồi hy vọng GC dọn kịp.

### 11.3. Không coi path là một file mở

`Path` chỉ mô tả vị trí theo một filesystem provider, không phải `FileChannel` hoặc handle cố định. Khi bạn gọi `Files.readAllBytes(path)` sau khi search, dữ liệu có thể đã thay và có thể ném lỗi. Nếu hệ thống xử lý dữ liệu không đáng tin, cần kiểm tra lại và thiết kế ranh giới an toàn.

### 11.4. Với API xóa hoặc archive file, phải thận trọng hơn

Predicate dựa vào `lastModifiedTime` và size có thể là bước chọn ứng viên. Nhưng trước khi xóa, ứng dụng phải xác định:

- Không còn process khác ghi file.
- Có policy về symlink, permissions và root boundary.
- Có revalidation hoặc atomic rename-to-quarantine khi phù hợp.
- Có log/audit và recovery khi xóa thất bại.
- Không cho phép đường dẫn do người dùng kiểm soát thoát khỏi vùng được phép.

`Files.find` không cung cấp transaction và không tự thay thế quy trình đó.

## 12. Ví dụ Java 8 hoàn chỉnh: tự tạo cây, tìm theo depth và attrs

Ví dụ này tránh phụ thuộc đường dẫn có sẵn trên máy bằng cách:

1. Tạo **một thư mục tạm** và các thư mục con.
2. Ghi năm file với **nội dung byte xác định**.
3. Tìm theo `maxDepth`, suffix `.txt`, `attrs.size()`, loại file.
4. Chuyển các paths thành đường dẫn tương đối và **sort** để stdout ổn định trên các file systems.
5. Dùng `try-with-resources` trong helper `search`.
6. Dọn toàn bộ cây thư mục tạm trong `finally` bằng `walkFileTree`.

Lưu thành **FilesFindDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.List;
import java.util.function.BiPredicate;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class FilesFindDemo {
    private static List<String> search(Path root, int maxDepth,
            BiPredicate<Path, BasicFileAttributes> matcher)
            throws IOException {
        try (Stream<Path> found = Files.find(root, maxDepth, matcher)) {
            return found.map(root::relativize)
                    .map(p -> p.toString().replace('\\', '/'))
                    .sorted()
                    .collect(Collectors.toList());
        }
    }

    private static boolean isTxt(Path path, BasicFileAttributes attrs) {
        return attrs.isRegularFile()
                && path.getFileName().toString().endsWith(".txt");
    }

    private static void cleanup(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(Path file,
                    BasicFileAttributes attrs) throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }
            @Override
            public FileVisitResult postVisitDirectory(Path dir,
                    IOException error) throws IOException {
                if (error != null) {
                    throw error;
                }
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("files-find-demo-");
        try {
            Path docs = Files.createDirectories(root.resolve("docs/sub"));
            Files.createDirectories(root.resolve("images"));

            Files.write(root.resolve("root.txt"),
                    "ROOT".getBytes(StandardCharsets.UTF_8));
            Files.write(root.resolve("docs/alpha.txt"),
                    "ALPHA".getBytes(StandardCharsets.UTF_8));
            Files.write(root.resolve("docs/beta.log"),
                    "BETA_LOG!".getBytes(StandardCharsets.UTF_8));
            Files.write(docs.resolve("deep.txt"),
                    "DEEPTXT".getBytes(StandardCharsets.UTF_8));
            Files.write(root.resolve("images/icon.bin"),
                    "ICON".getBytes(StandardCharsets.UTF_8));

            System.out.println("depth0 directories = "
                    + search(root, 0, (p, a) -> a.isDirectory()).size());
            System.out.println("depth1 txt = "
                    + search(root, 1, FilesFindDemo::isTxt));
            System.out.println("depth2 txt = "
                    + search(root, 2, FilesFindDemo::isTxt));
            System.out.println("depth3 txt = "
                    + search(root, 3, FilesFindDemo::isTxt));
            System.out.println("depth2 size>=5 = "
                    + search(root, 2,
                            (p, a) -> a.isRegularFile() && a.size() >= 5));
            System.out.println("depth3 files = "
                    + search(root, 3, (p, a) -> a.isRegularFile()).size());
            System.out.println("depth3 directories = "
                    + search(root, 3, (p, a) -> a.isDirectory()).size());
        } finally {
            cleanup(root);
        }
    }
}
~~~

Biên dịch bằng một JDK có `--release 8` (JDK 9+):

~~~bash
javac --release 8 FilesFindDemo.java
java FilesFindDemo
~~~

Nếu đang dùng chính JDK 8, có thể biên dịch bằng `javac FilesFindDemo.java` trên JDK 8. Tất cả API trong source đều tương thích Java 8. Các JDK hiện đại đôi khi in **compiler warning** về target/source cũ, nhưng không làm thay đổi chương trình nếu việc biên dịch thành công.

**Stdout thực tế đã được chạy xác minh:**

~~~text
depth0 directories = 1
depth1 txt = [root.txt]
depth2 txt = [docs/alpha.txt, root.txt]
depth3 txt = [docs/alpha.txt, docs/sub/deep.txt, root.txt]
depth2 size>=5 = [docs/alpha.txt, docs/beta.log]
depth3 files = 5
depth3 directories = 4
~~~

### 12.1. Tại sao depth 0 có một directory?

`root` cũng là entry được duyệt; ở depth 0, matcher `a.isDirectory()` nhận start directory và trả true. `search(...).size()` là 1. Không có nghĩa stream bao gồm contents của directory đó.

### 12.2. Depth 1, 2 và 3 cho kết quả khác nhau

- Depth 1 chỉ thấy `root.txt` trong các file `.txt`.
- Depth 2 có thêm `docs/alpha.txt`.
- Depth 3 có thêm `docs/sub/deep.txt`.
- `beta.log` và `icon.bin` không khớp suffix `.txt`.

### 12.3. Bộ lọc kích thước

Ở depth 2, các regular files đạt ít nhất 5 bytes là:

- `docs/alpha.txt`: 5 bytes.
- `docs/beta.log`: 9 bytes.

`root.txt` và `images/icon.bin` chỉ có 4 bytes; `deep.txt` ở depth 3 nên chưa được xét.

### 12.4. Vì sao có năm files và bốn directories?

Trong toàn cây thử nghiệm:

- Có **5 regular files**: `root.txt`, `alpha.txt`, `beta.log`, `deep.txt`, `icon.bin`.
- Có **4 directories**: `root`, `docs`, `docs/sub` và `images`.

Các dòng `depth3 files` và `depth3 directories` xác minh `BasicFileAttributes.isRegularFile` / `isDirectory`, không dựa vào tên extension.

### 12.5. Cách làm stdout deterministic

Thư mục tạm có tên ngẫu nhiên do JDK cấp, nhưng chương trình **không in absolute root path**. Hàm `search` dùng `root.relativize` rồi chuẩn hóa separator để in, cuối cùng `sorted`; vì thế stdout không phụ thuộc thứ tự directory listing ngẫu nhiên giữa các lần chạy.

Đây là test kỹ thuật, không phải cam kết mọi filesystem sẽ cho phép tạo file/thư mục. Khi môi trường bị giới hạn permissions, thao tác tạo thư mục tạm vẫn có thể ném IOException đúng hợp đồng.

### 12.6. Vì sao dùng walkFileTree để dọn?

Xóa thư mục không rỗng cần xóa contents trước rồi xóa các directories từ dưới lên. `walkFileTree` có `visitFile` và `postVisitDirectory` để thực hiện thứ tự đó. Trong khi đó `Files.find` rất tốt cho **tìm và lọc** nhưng không là API thuận tiện nhất để kiểm soát xóa đệ quy và xử lý lỗi từng directory.

## 13. Các lỗi phổ biến và cách khắc phục

### Lỗi 1 — Quên đóng stream

`Files.find` có thể giữ directory handles mở. **Sửa:** luôn dùng `try (Stream<Path> s = Files.find(...))` hoặc control structure tương đương.

### Lỗi 2 — Nghĩ Files.find duyệt ngay khi gọi

Traversal lazy; lỗi I/O có thể xảy ra khi terminal op consume. **Sửa:** xử lý cả checked `IOException` lẫn `UncheckedIOException` khi phù hợp.

### Lỗi 3 — Dùng Files.list để tìm nhiều cấp

`list` chỉ immediate children. **Sửa:** dùng `find`/`walk`/`walkFileTree` cho đệ quy.

### Lỗi 4 — Dùng maxDepth=1 rồi tưởng đi hết cây

Depth 1 chỉ start và một cấp con. **Sửa:** đếm depth từ start=0.

### Lỗi 5 — Dùng maxDepth âm làm “vô hạn”

Âm là invalid. **Sửa:** depth dương hoặc `Integer.MAX_VALUE` có kiểm soát.

### Lỗi 6 — Dùng filter false trên directory để prune

Matcher false chỉ loại entry khỏi stream kết quả; traversal vẫn có thể đi vào subtree. **Sửa:** dùng `walkFileTree`/`SKIP_SUBTREE` hoặc chọn root nhỏ hơn.

### Lỗi 7 — Gọi lại Files.readAttributes trong matcher

`Files.find` đã truyền BasicFileAttributes. **Sửa:** tận dụng attrs sẵn có để giảm I/O dư thừa, trừ khi cần revalidation riêng.

### Lỗi 8 — Nhầm bytes và ký tự

`attrs.size()` là bytes. **Sửa:** nếu muốn số ký tự thì phải đọc nội dung bằng charset phù hợp.

### Lỗi 9 — Gọi attrs.size mà không kiểm tra file type

Size directory hoặc file đặc biệt không luôn mang nghĩa business như file thường. **Sửa:** `attrs.isRegularFile() && attrs.size() ...`.

### Lỗi 10 — Nghĩ mọi filesystem lưu creationTime chính xác

Có thể trả default hoặc resolution hạn chế. **Sửa:** dùng timestamp ứng dụng nếu nghiệp vụ đòi metadata đáng tin hơn.

### Lỗi 11 — Xem fileKey là ID toàn cục

`fileKey` provider-specific và có thể null. **Sửa:** không dùng làm primary key bền vững.

### Lỗi 12 — Dùng lambda có side effect xóa file

Có thể phá traversal và tạo TOCTOU. **Sửa:** tách giai đoạn selection và mutation với policy an toàn.

### Lỗi 13 — Nuốt IOException rồi trả danh sách rỗng

Không phân biệt “không có file” với “không đọc được thư mục”. **Sửa:** trả lỗi/partial result rõ ràng theo contract.

### Lỗi 14 — Chỉ catch IOException

Lỗi khi consume stream lazy có thể là `UncheckedIOException`. **Sửa:** xử lý các đường exception tương ứng.

### Lỗi 15 — Nghĩ symlink được follow mặc định

Không. **Sửa:** chọn `FileVisitOption.FOLLOW_LINKS` chỉ khi thật sự cần, hiểu cycle/traversal risk.

### Lỗi 16 — Truyền LinkOption.NOFOLLOW_LINKS vào find

Sai loại option; `find` nhận `FileVisitOption`. **Sửa:** không đưa `FOLLOW_LINKS` nếu muốn no-follow.

### Lỗi 17 — Follow links mà không kiểm soát root

Symlink có thể đưa traversal ra khỏi phạm vi dự tính. **Sửa:** xác định boundary, permissions và security policy rõ ràng.

### Lỗi 18 — Coi một Path được tìm thấy là bằng chứng file vẫn tồn tại

File có thể bị xóa/rename trước khi open. **Sửa:** xử lý IOException/TOCTOU ở thời điểm sử dụng.

### Lỗi 19 — Đòi thứ tự kết quả theo tên

Directory listing/sibling order không mặc định sorted. **Sửa:** sort khi business cần, đồng thời tính chi phí memory.

### Lỗi 20 — Dùng findFirst để chọn file alphabetically first

Không có guarantee “tên nhỏ nhất” nếu không sort. **Sửa:** định nghĩa comparator và thực hiện phù hợp.

### Lỗi 21 — Reuse Stream đã count

Stream terminal operation tiêu thụ stream. **Sửa:** tạo traversal mới hoặc collect kết quả một lần.

### Lỗi 22 — Đóng stream trước khi caller consume

Try-with-resources trong method rồi trả stream bên ngoài sẽ làm stream đã closed. **Sửa:** trả List có giới hạn hoặc chuyển ownership đóng sang caller rõ ràng.

### Lỗi 23 — Collect hàng triệu Path không cân nhắc RAM

Collect/sort tích lũy nhiều kết quả. **Sửa:** streaming bounded processing, giới hạn root/depth, hoặc protocol batch riêng.

### Lỗi 24 — Cho rằng parallel luôn nhanh hơn

Filesystem traversal và processing khác nhau về đặc tính I/O. **Sửa:** benchmark, kiểm soát concurrency và side effects.

### Lỗi 25 — Đọc attrs xong rồi xóa file an toàn tuyệt đối

Metadata có thể stale, file bị thay thế giữa check và use. **Sửa:** revalidate và dùng workflow atomic/ownership phù hợp.

### Lỗi 26 — Dùng string path.contains cho permission boundary

Kiểm tra substring không xác định containment theo filesystem. **Sửa:** normalize/resolve/provider-aware validation và security policy phù hợp; tránh đi theo link không tin cậy.

### Lỗi 27 — Tưởng Files.find giải quyết lỗi từng nhánh để tiếp tục

Khi lazy stream ném `UncheckedIOException`, traversal không mặc định skip thành công. **Sửa:** `walkFileTree` với visitor error handling nếu cần.

### Lỗi 28 — Không kiểm thử file type khác regular file

Directory, symlink, special file có thuộc tính khác. **Sửa:** thêm cases type vào integration tests và kiểm tra portability.

### Lỗi 29 — Giả định file tree không đổi khi duyệt

Walk/find chỉ **weakly consistent** đối với mutations concurrent. **Sửa:** thiết kế theo eventual results hoặc bảo vệ snapshot ở tầng khác.

### Lỗi 30 — Bắt SecurityException theo giả định lịch sử là bảo mật đủ

Trên các JDK hiện đại, cơ chế Security Manager truyền thống không còn là nền tảng kiểm soát quyền khuyến nghị. **Sửa:** dựa vào OS permissions, sandbox/process identity, chính sách truy cập path và exception handling phù hợp thay vì kiến thức legacy.

## 14. Checklist thiết kế trước khi sử dụng Files.find

| Câu hỏi | Nếu câu trả lời là... |
| --- | --- |
| Root là directory thật hay regular file? | Xác định semantics depth 0 |
| Cần chỉ một cấp? | Cân nhắc `Files.list` |
| Cần duyệt đệ quy có lọc metadata? | `Files.find` phù hợp |
| Cần prune directory? | Dùng `walkFileTree` |
| maxDepth dự kiến? | Đặt giới hạn theo cấu trúc thực |
| Matcher cần tên/size/type/time? | Dùng `Path` và `BasicFileAttributes` |
| File size là bytes hay characters? | Định nghĩa đơn vị rõ |
| Có symbolic links? | Chọn follow/no-follow có chủ đích |
| Có quyền đọc mọi directory? | Xử lý I/O errors |
| Duyệt số lượng file lớn? | Cân nhắc memory và streaming |
| Có cần alphabetical order? | Sort và tính chi phí |
| Có dùng short-circuit? | Vẫn cần close stream |
| Có lazy I/O error? | Bắt `UncheckedIOException` phù hợp |
| Cần error handling per file? | `walkFileTree` có callbacks |
| Có mutate files sau khi chọn? | Kiểm soát TOCTOU và security |
| Cần result bền vững sau scan? | `Path` không đóng băng file |
| Code chạy Java 8? | Dùng API có từ Java 8 |
| Có integration tests trên nhiều OS? | Kiểm tra separators, links, permissions |
| Có nhu cầu benchmark? | Đo I/O và predicate với workload thật |

### 14.1. Ma trận test quan trọng

1. Root là directory và depth 0 trả directory nếu matcher chấp nhận.
2. Root là một regular file, depth 0 vẫn xét chính file.
3. depth 1 không đi vào grandchildren.
4. depth 2/3 có đúng số matches theo cây đã dựng.
5. Matcher true/false với `isRegularFile` và `isDirectory`.
6. File có suffix `.txt` nhưng size nhỏ bị loại theo size filter.
7. Đường dẫn có tên Unicode hoặc khoảng trắng vẫn được xử lý đúng theo provider.
8. Input không tồn tại có I/O error rõ, không trả empty list giả.
9. Negative maxDepth được báo tham số sai.
10. Bỏ `FOLLOW_LINKS` thì symbolic link không bị duyệt target.
11. Có `FOLLOW_LINKS` thì xử lý links/cycles phù hợp và không tràn sang root ngoài policy.
12. Stream được đóng cả khi terminal operation return sớm/throw.
13. Exception khi stream consume được xử lý theo contract.
14. Nếu filesystem đang thay đổi, reader xử lý stale path/permission.
15. Nếu cần determinism, sort kết quả trước khi assert.
16. Cleanup temp directory hoàn chỉnh sau khi test.
17. Unit test pure matcher không cần I/O khi tách logic đúng.
18. Integration test trên filesystem thực cho symlink/case sensitivity/time resolution.

## 15. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** `Files.find` trả về loại nào?

**Đáp án:** `Stream<Path>` được duyệt lazy; phải đóng.

**Câu 2.** Matcher nhận những tham số nào?

**Đáp án:** Một `Path` và một `BasicFileAttributes`, trả `boolean` qua `BiPredicate.test`.

**Câu 3.** `Files.find(root,0,...)` có thể trả kết quả không?

**Đáp án:** Có. Nó kiểm tra chính `root` ở depth 0.

**Câu 4.** `maxDepth=1` có duyệt file ở `root/docs/sub/deep.txt` không?

**Đáp án:** Không, nếu root là `root` thì file đó ở depth 3.

**Câu 5.** Matcher trả false cho directory `docs` có làm bỏ qua `docs/sub` không?

**Đáp án:** Không. Matcher chỉ lọc đầu ra của entry, không prune traversal.

**Câu 6.** Vì sao `Files.find` có thể tiết kiệm I/O so với `Files.walk(...).filter(Files::isRegularFile)`?

**Đáp án:** Vì `find` truyền sẵn attrs đã có trong traversal; filter trên walk có thể phải đọc metadata thêm.

**Câu 7.** `BasicFileAttributes.size()` trả đơn vị gì?

**Đáp án:** Bytes, không phải ký tự hoặc dòng.

**Câu 8.** `creationTime()` có luôn là ngày tạo thật chính xác tuyệt đối không?

**Đáp án:** Không. File system có thể thiếu hoặc làm tròn metadata và trả default.

**Câu 9.** `fileKey()` có luôn non-null hoặc ổn định toàn hệ thống không?

**Đáp án:** Không. Provider-specific và có thể null.

**Câu 10.** Vì sao cần `try-with-resources` khi dùng Files.find?

**Đáp án:** Vì stream có thể giữ directory handles; phải đóng để giải phóng tài nguyên.

**Câu 11.** `findFirst()` có tự đóng stream không?

**Đáp án:** Không. Vẫn dùng try-with-resources.

**Câu 12.** Một IOException khi đọc thư mục sau khi `find` trả stream có thể được thấy ở dạng gì?

**Đáp án:** `UncheckedIOException` tại terminal/stream operation, cần xem cause theo contract.

**Câu 13.** Mặc định `Files.find` có follow symbolic links không?

**Đáp án:** Không. Chỉ follow khi cung cấp `FileVisitOption.FOLLOW_LINKS`.

**Câu 14.** Có thể truyền `LinkOption.NOFOLLOW_LINKS` làm options của Files.find không?

**Đáp án:** Không; đó là kiểu option khác.

**Câu 15.** Có thể mặc định xóa một file vừa tìm thấy nếu attrs cho thấy nó cũ không?

**Đáp án:** Không nên. Metadata và path có thể stale, cần policy revalidation/ownership và xử lý race.

**Câu 16.** Khi cần bỏ qua một directory subtree ngay lập tức, nên chọn API nào?

**Đáp án:** `Files.walkFileTree` và `FileVisitResult.SKIP_SUBTREE` hoặc bắt đầu search từ một subdirectory nhỏ hơn.

**Câu 17.** `Files.list` và `Files.find` khác nhau ở điểm nào dễ nhớ?

**Đáp án:** `list` liệt kê một cấp; `find` duyệt cây theo maxDepth với matcher Path + attrs.

**Câu 18.** Muốn output có thứ tự tên ổn định giữa các hệ thống nên làm gì?

**Đáp án:** Chuyển về dạng relative path theo policy và sort; không phụ thuộc directory enumeration order.

**Câu 19.** `Files.find` có phải một database index tìm file tức thời không?

**Đáp án:** Không. Nó thực hiện filesystem traversal, có chi phí I/O và số entry phụ thuộc cây.

**Câu 20.** Khi dùng `Files.find` để rà file an toàn, có phải mọi nội dung sẽ không đổi sau khi match không?

**Đáp án:** Không. Path và attributes là quan sát theo thời điểm; cần xử lý TOCTOU và security riêng.

## 16. Tổng kết

- **`Files.find(start,maxDepth,matcher,options...)`** là API Java 8 **vẫn phù hợp hiện nay** để tìm Path trong cây thư mục bằng **tên/path và `BasicFileAttributes`**.
- **`maxDepth` tính từ start=0**; start cũng được xét. Matcher false **không prune** subtree.
- `BasicFileAttributes` cung cấp `isRegularFile`, `isDirectory`, `size` bytes, các `FileTime` và `fileKey` tùy provider; không mặc định metadata tuyệt đối chính xác hoặc file tồn tại mãi.
- API có thể tiết kiệm những lần đọc attributes dư thừa so với `walk` + lọc lại metadata, nhưng hiệu năng còn phụ thuộc filesystem và workload.
- **Stream lazy có giữ tài nguyên thư mục**, luôn dùng `try-with-resources`, kể cả khi `findFirst/limit`.
- **IOException** lúc mở khác **UncheckedIOException** có thể xảy ra khi consume stream.
- **Mặc định không follow symlink**; `FOLLOW_LINKS` cần đánh giá cycle và security. `LinkOption.NOFOLLOW_LINKS` không phải argument của `Files.find`.
- `Files.list` hợp lý cho một cấp; `Files.walk` khi cần stream Path; **`Files.walkFileTree` cho phép prune và xử lý lỗi từng nhánh**.
- **Kiểm thử Java 8 đầy đủ** ở mục 12 đã biên dịch/chạy, xác minh depths 0–3, lọc type/size/extension, deterministic output và cleanup.
- Khi search để xóa/move/archive, phải thiết kế revalidation và TOCTOU chứ không dựa vào attrs lúc traversal.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — Files.find, walk, list, walkFileTree](https://docs.oracle.com/javase/8/docs/api/java/nio/file/Files.html)
- [Oracle Java SE 8 — BasicFileAttributes](https://docs.oracle.com/javase/8/docs/api/java/nio/file/attribute/BasicFileAttributes.html)
- [Oracle Java SE 8 — Path](https://docs.oracle.com/javase/8/docs/api/java/nio/file/Path.html)
- [Oracle Java SE 8 — FileVisitOption](https://docs.oracle.com/javase/8/docs/api/java/nio/file/FileVisitOption.html)
- [Oracle Java SE 8 — SimpleFileVisitor](https://docs.oracle.com/javase/8/docs/api/java/nio/file/SimpleFileVisitor.html)
- [Oracle Java SE 8 — UncheckedIOException](https://docs.oracle.com/javase/8/docs/api/java/io/UncheckedIOException.html)
- [Oracle Java SE 8 — FileTime](https://docs.oracle.com/javase/8/docs/api/java/nio/file/attribute/FileTime.html)
- [Oracle Java SE 8 — Stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html)
- [Oracle Java SE 26 — Files.find hiện hành](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html)
