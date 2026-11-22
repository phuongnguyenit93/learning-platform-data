# `Files.list` chỉ liệt kê con trực tiếp — duyệt thư mục một cấp trong Java

Trong Java NIO.2, `Files.list(Path)` là cách ngắn gọn để nhận một `Stream<Path>` của **các mục con trực tiếp trong một thư mục**. Nó không tự duyệt những mục nằm sâu trong thư mục con. Sự khác biệt này rất quan trọng: chương trình tìm một file bằng `Files.list(root)` có thể hoàn toàn không thấy file nằm ở `root/subdir/file.txt` dù file đó đang tồn tại.

Bài học thuộc phần **Duyệt cây thư mục** của Java Core I/O, tập trung chính xác vào **mức duyệt một cấp**: `Files.list` trả gì, không trả gì, làm thế nào lọc/sắp xếp/đếm, vì sao phải đóng stream, và khi nào chuyển sang `Files.walk`, `Files.find` hoặc `Files.walkFileTree`. Các ví dụ sử dụng Java 17+, tự tạo thư mục tạm, không yêu cầu dữ liệu có sẵn và đã được kiểm chứng bằng chương trình chạy thực tế.

## 1. Hiểu đúng “con trực tiếp” (direct children)

Xét cây thư mục:

```text
root/
├── alpha.txt
├── zeta.bin
└── docs/
    └── nested/
        └── deep.txt
```

Gọi:

```java
try (Stream<Path> entries = Files.list(root)) {
    entries.forEach(System.out::println);
}
```

Đây là **đoạn minh họa**: cần biến `Path root`, import `java.nio.file.Files` và `java.util.stream.Stream`, cùng xử lý `IOException`.

`Files.list(root)` trả các `Path` cho **ba mục con trực tiếp**:

- `root/alpha.txt` — file nằm ngay trong `root`.
- `root/zeta.bin` — file nằm ngay trong `root`.
- `root/docs` — **thư mục con** nằm ngay trong `root`.

Nó **không trả** `root/docs/nested`, cũng **không trả** `root/docs/nested/deep.txt`, vì hai mục này nằm ở độ sâu lớn hơn một cấp. `root` cũng **không nằm trong kết quả**, bởi `list` liệt kê **các mục trong thư mục**, không phải chính thư mục được truyền vào.

Một thư mục trống hợp lệ cho một stream không có phần tử. Điều đó khác với đường dẫn không tồn tại hoặc không thể truy cập, vốn có thể dẫn đến `IOException`.

**Quy tắc nhớ:** `Files.list(dir)` gần với thao tác “liệt kê nội dung của thư mục này”, không phải “tìm tất cả file phía dưới thư mục này”.

## 2. Cú pháp và kiểu trả về

API Java SE 17:

```java
public static Stream<Path> list(Path dir) throws IOException
```

Các điểm then chốt:

1. `dir` là `Path` tới **thư mục**. Tạo `Path.of("root")` không tự xác minh hay tạo thư mục.
2. Kết quả là **`Stream<Path>`** — mỗi phần tử là đường dẫn tới một mục con, **không** phải tên file dạng `String` hay nội dung file.
3. Các phần tử có thể đại diện cho **file thường, thư mục, symbolic link và loại entry khác**. `list` **không tự lọc** chỉ file thường.
4. `Files.list` không tự đảm bảo **thứ tự sắp xếp** của các entry. Kết quả phụ thuộc filesystem/provider; khi cần đầu ra ổn định, phải dùng `sorted(...)`.
5. Stream được tạo từ việc liệt kê thư mục có **tài nguyên hệ thống** phía dưới; **phải đóng** bằng `try-with-resources` hoặc một cách quản lý tương đương.
6. Việc lấy entry thường được tiến hành **lazily** khi tiêu thụ stream; khác với một snapshot bất biến toàn bộ cây tại thời điểm gọi.
7. Stream chỉ dùng **một lần** theo hợp đồng `Stream`. Muốn duyệt lại thư mục, tạo stream mới hoặc chủ động lưu kết quả vào collection nếu kích thước phù hợp.

`Files.list` có từ **Java 8**. NIO.2 `Path` và `Files` có từ Java 7, nhưng phương thức `list` trả stream là API Java 8+. Các ví dụ ở đây yêu cầu **Java 17+** do dùng `Path.of`, `Files.writeString` và `Stream.toList` ở những nơi phù hợp.

### `Path` không phải dữ liệu file

`Path path = Path.of("docs", "notes.txt");` chỉ mô tả tên/vị trí đường dẫn. Các thao tác như `path.getFileName()` hay `path.resolve("child")` phần lớn là thao tác **cú pháp**. `Files.isDirectory(path)` hoặc `Files.readString(path)` mới truy vấn/tác động đến filesystem và có thể thất bại do trạng thái hoặc quyền truy cập.

`Files.list` cho bạn **đường dẫn** để tiếp tục thao tác với `Files`; nó không tự đọc nội dung tất cả file, không giải mã charset và không mở từng file như `InputStream`.

## 3. Ví dụ 1 — chứng minh `Files.list` không đi sâu

Tạo file `ListOneLevelDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;

public class ListOneLevelDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("list-one-");
        try {
            Files.writeString(root.resolve("alpha.txt"), "A", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("zeta.bin"), "Z", StandardCharsets.UTF_8);
            Path nested = Files.createDirectories(root.resolve("docs").resolve("nested"));
            Files.writeString(nested.resolve("deep.txt"), "D", StandardCharsets.UTF_8);

            try (Stream<Path> entries = Files.list(root)) {
                entries.sorted(Comparator.comparing(
                        p -> p.getFileName().toString()))
                       .forEach(p -> System.out.println(
                               p.getFileName() + ":"
                                       + (Files.isDirectory(p) ? "directory" : "file")));
            }
            try (Stream<Path> entries = Files.list(root)) {
                System.out.println("direct children=" + entries.count());
            }
            try (Stream<Path> entries = Files.list(root)) {
                System.out.println("includes deep.txt=" + entries.anyMatch(
                        p -> p.getFileName().toString().equals("deep.txt")));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                paths.sorted(Comparator.reverseOrder()).forEach(p -> {
                    try { Files.deleteIfExists(p); }
                    catch (IOException e) { throw new UncheckedIOException(e); }
                });
            }
        }
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ListOneLevelDemo.java
java ListOneLevelDemo
```

Đầu ra đã kiểm thử:

```text
alpha.txt:file
docs:directory
zeta.bin:file
direct children=3
includes deep.txt=false
```

**Phân tích:**

- Thư mục tạm được tạo tự động. `Files.writeString` tạo hai file ở root, `Files.createDirectories` tạo thư mục `docs/nested` và một file `deep.txt` nằm sâu bên dưới.
- `Files.list(root)` chỉ thấy `alpha.txt`, `docs` và `zeta.bin`. Không thấy `nested` hay `deep.txt`.
- `sorted(Comparator.comparing(...))` sắp theo tên entry trước khi in; nếu bỏ `sorted`, **không có cam kết** rằng các file được in theo thứ tự chữ cái.
- `Files.isDirectory(p)` dùng để phân loại mỗi entry **tại thời điểm kiểm tra**; nó có thể theo symbolic link theo mặc định, nên ví dụ chỉ dùng thư mục/file thường do chương trình vừa tạo.
- Lời gọi `entries.count()` đếm **các entry trực tiếp**, gồm cả thư mục. Kết quả là 3, **không phải tổng số file toàn cây**.
- `anyMatch` hỏi có entry **trực tiếp** tên `deep.txt` không. Giá trị `false` không chứng minh file đó không có trong các thư mục sâu hơn.
- Khối `finally` dùng `Files.walk` để dọn **cây thư mục tạm do chương trình sở hữu**. Đây chỉ là bước dọn dữ liệu ví dụ, **không có nghĩa `Files.list` tự thực hiện duyệt đệ quy**.

Chương trình có thể ném `IOException` nếu filesystem tạm không cho phép thao tác. Các dòng stdout trên được ghi nhận khi ví dụ chạy thành công trên Java 17 với filesystem bình thường.

## 4. Lấy tên hay lấy đường dẫn đầy đủ?

`Files.list(dir)` trả `Path` đến mỗi mục con, thường bao gồm tiền tố đường dẫn của `dir`. Nếu bạn chỉ cần **tên cuối**, dùng `getFileName()`:

```java
try (Stream<Path> entries = Files.list(directory)) {
    entries.map(p -> p.getFileName().toString())
           .sorted()
           .forEach(System.out::println);
}
```

Đây là **đoạn minh họa**, cần `directory` hợp lệ, import `Files`, `Path`, `Stream` và xử lý `IOException`. `getFileName()` trả phần cuối; file `root/docs` cho tên `docs`.

Nếu cần thao tác file sau đó, **giữ `Path`** thay vì chỉ giữ tên: tên `"report.txt"` không đủ thông tin nếu có nhiều thư mục. Dùng `Path.resolve` khi cần xây một đường dẫn khác, tránh nối chuỗi `"dir/" + fileName` theo hệ điều hành.

Một số thông tin metadata có thể truy xuất qua `Files.size(path)`, `Files.isRegularFile(path)`, `Files.getLastModifiedTime(path)`, v.v.; các thao tác này **không được `Files.list` thực hiện tự động** và có thể phát sinh I/O hoặc race.

## 5. Lọc entry trực tiếp bằng Stream API

Vì kết quả là `Stream<Path>`, bạn có thể dùng `filter`, `map`, `sorted`, `limit`, `count` hay `collect` như các stream Java khác.

Ví dụ lấy **file thường ở ngay root** có đuôi `.txt`:

```java
try (Stream<Path> entries = Files.list(root)) {
    List<Path> files = entries.filter(Files::isRegularFile)
            .filter(p -> p.getFileName().toString().endsWith(".txt"))
            .sorted(Comparator.comparing(p -> p.getFileName().toString()))
            .toList();
}
```

Đây là **mã minh họa**, cần import `Files`, `Path`, `List`, `Comparator`, `Stream`, biến `root` và xử lý `IOException`. `Files.isRegularFile` kiểm tra loại mục; `endsWith(".txt")` chỉ kiểm tra tên **theo chuỗi**, không đọc nội dung hay xác định MIME type thật.

### Phân biệt lọc và duyệt sâu

`filter(Files::isRegularFile)` **không làm stream đệ quy**. Nếu `deep.txt` nằm bên dưới `root/docs/nested`, bộ lọc chỉ xét ba entry trực tiếp mà `Files.list(root)` đã cung cấp; nó không tự vào `docs` để tìm file sâu.

Nếu ý định là tìm “tất cả file `.txt` ở mọi cấp”, bạn cần chuyển sang một API duyệt sâu hoặc tự triển khai thuật toán đi qua thư mục con. `Files.walk(root)` hay `Files.find(root, maxDepth, ...)` thích hợp hơn.

### `limit` không bảo đảm lấy “N file đầu tiên theo bảng chữ cái”

Nếu không có `sorted` và thứ tự list là không được xác định, `limit(10)` chỉ lấy tối đa 10 entry theo thứ tự mà traversal nhìn thấy, **không nhất thiết là 10 tên nhỏ nhất**. Nếu cần thứ tự chính xác, phải sắp xếp trước; lưu ý `sorted` cần xử lý các entry để quyết định thứ tự, có thể tốn bộ nhớ cho thư mục rất lớn.

Nếu muốn phân trang ổn định giữa các lần truy vấn trong thư mục bị thay đổi đồng thời, `Files.list` một mình không đủ để cung cấp snapshot hay thứ tự toàn cục cố định.

## 6. Ví dụ 2 — lọc file trực tiếp, so với `Files.walk`

Tạo file `ListVsWalkDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public class ListVsWalkDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("list-walk-");
        try {
            Files.writeString(root.resolve("b.txt"), "B", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("a.txt"), "A", StandardCharsets.UTF_8);
            Files.writeString(root.resolve("data.csv"), "1", StandardCharsets.UTF_8);
            Path folder = Files.createDirectories(root.resolve("sub"));
            Files.writeString(folder.resolve("inside.txt"), "I", StandardCharsets.UTF_8);

            try (Stream<Path> direct = Files.list(root)) {
                List<String> txtNames = direct.filter(Files::isRegularFile)
                        .map(p -> p.getFileName().toString())
                        .filter(name -> name.endsWith(".txt"))
                        .sorted().toList();
                System.out.println("direct .txt=" + txtNames);
            }
            try (Stream<Path> direct = Files.list(root)) {
                System.out.println("direct entries=" + direct.count());
            }
            try (Stream<Path> all = Files.walk(root)) {
                System.out.println("recursive regular files="
                        + all.filter(Files::isRegularFile).count());
            }
            try (Stream<Path> depthOne = Files.walk(root, 1)) {
                System.out.println("walk maxDepth1 entries=" + depthOne.count());
            }
        } finally {
            try (Stream<Path> all = Files.walk(root)) {
                all.sorted(Comparator.reverseOrder()).forEach(p -> {
                    try { Files.deleteIfExists(p); }
                    catch (IOException e) { throw new UncheckedIOException(e); }
                });
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ListVsWalkDemo.java
java ListVsWalkDemo
```

```text
direct .txt=[a.txt, b.txt]
direct entries=4
recursive regular files=4
walk maxDepth1 entries=5
```

**Tại sao có các con số này?**

- `Files.list(root)` cho bốn mục **trực tiếp**: `a.txt`, `b.txt`, `data.csv` và thư mục `sub`. Do vậy `direct entries=4`.
- Lọc `isRegularFile` và phần mở rộng `.txt` chỉ cho `a.txt`/`b.txt` ở root. `inside.txt` không có trong nguồn `Files.list(root)` nên không xuất hiện.
- `Files.walk(root)` theo mặc định duyệt xuống cây (không theo symbolic link nếu không yêu cầu), gồm **cả root** và các entry con. Khi lọc file thường, cả `inside.txt` nằm sâu cũng được đếm; tổng số file thường là 4.
- `Files.walk(root, 1)` có phạm vi **root + các mục sâu một cấp**. `root` được tính thêm nên kết quả là 5, khác `Files.list(root)` vốn không gồm `root`.

Đây là một khác biệt dễ quên khi so sánh số lượng:

```text
Files.list(root)            -> mục con trực tiếp, KHÔNG gồm root
Files.walk(root, 1)         -> root VÀ mục con trực tiếp
Files.walk(root)            -> root và mục nằm ở nhiều độ sâu
Files.walk(root, 0)         -> chỉ có root
```

Số phần tử của `Files.walk` có thể bao gồm cả thư mục; muốn đếm số **file thường** phải lọc với `Files.isRegularFile` hoặc dựa vào `BasicFileAttributes` thích hợp.

## 7. Mỗi `Files.list` stream chỉ dùng một lần

Java Stream không phải `Collection` có thể tự động lặp lại tùy thích. Sau một terminal operation như `forEach`, `count` hoặc `toList`, stream được coi là đã tiêu thụ; gọi terminal operation thứ hai trên cùng stream thường ném `IllegalStateException`.

Ví dụ **sai**:

```java
// Minh họa lỗi: không dùng lại Stream sau terminal operation.
try (Stream<Path> entries = Files.list(dir)) {
    long count = entries.count();
    entries.forEach(System.out::println); // Sai: stream đã tiêu thụ.
}
```

Cách đúng khi cần duyệt nhiều lần:

- **Mở stream mới** với `Files.list(dir)` mỗi lượt và đóng mỗi stream.
- Hoặc nếu thư mục đủ nhỏ, **collect** vào `List<Path>` một lần trong `try-with-resources`, rồi làm việc với danh sách. Danh sách chỉ chứa các `Path` được liệt kê, không bảo đảm mỗi file còn tồn tại ở những thời điểm sau.

Ví dụ thu thập:

```java
List<Path> snapshotOfNames;
try (Stream<Path> entries = Files.list(dir)) {
    snapshotOfNames = entries.sorted().toList();
}
System.out.println("Entries recorded=" + snapshotOfNames.size());
```

Đây là **mã minh họa**. `toList()` là phương thức Java 16+; kết quả không phải một snapshot bất biến của **nội dung file**, chỉ là danh sách các đường dẫn nhìn thấy trong lúc traversal. File có thể thay đổi hoặc biến mất ngay sau đó.

Lưu ý `sorted()` ở đây sử dụng thứ tự so sánh của `Path`, chịu quy tắc provider. Nếu muốn sắp **theo tên file** thay vì theo toàn bộ đường dẫn, chọn comparator trên `getFileName()`.

## 8. Vì sao bắt buộc đóng stream?

`Files.list` mở một nguồn duyệt entry gắn với tài nguyên filesystem, ví dụ directory stream/handle. Tài liệu JDK quy định stream được trả về **chứa tham chiếu tới một directory mở**. Nếu không đóng, ứng dụng có thể làm rò rỉ file descriptor/handle hoặc giữ tài nguyên lâu hơn cần thiết.

Mẫu đúng:

```java
try (Stream<Path> entries = Files.list(dir)) {
    entries.forEach(this::processEntry);
}
```

Đây chỉ là **minh họa bên trong một phương thức instance** có `processEntry(Path)` và biến `dir`; không phải chương trình đầy đủ. Cần import các kiểu và xử lý `IOException`.

**Các hiểu nhầm:**

- `entries.count()` chạy xong **không tự đóng** stream theo contract.
- `entries.forEach(...)` kết thúc **không tự đóng** stream.
- `entries.toList()` hoàn tất **không tự đóng** stream.
- Gán kết quả `Files.list(dir)` cho một biến static rồi dùng dần trong suốt tuổi thọ service thường khiến khó quản lý vòng đời và dễ rò rỉ.
- `try-with-resources` đóng stream cả khi thao tác terminal throw exception.

Nếu thư viện/API nhận stream và xử lý bên ngoài phạm vi method, hãy xác định rõ **ai sở hữu trách nhiệm đóng**. Một lựa chọn gọn hơn là xử lý dữ liệu **ngay trong** khối `try`, hoặc collect những giá trị nhỏ không cần giữ file descriptor sau khi khối kết thúc.

### Phạm vi lazy traversal và closure

Các thao tác trung gian `filter`, `map`, `sorted` thường chỉ tạo pipeline; thao tác terminal như `count`, `forEach`, `toList` mới yêu cầu traversal. Directory có thể thay đổi ngay cả trong lúc traversal; không có nghĩa `Files.list` tạo ảnh chụp trạng thái cố định.

Hãy đặt việc tạo stream và terminal operation trong cùng `try-with-resources`, thay vì tạo stream trong một method rồi trả về caller không biết nghĩa vụ đóng.

## 9. Lỗi khi mở hoặc duyệt thư mục

`Files.list(dir)` khai báo `throws IOException`. Các tình huống có thể xảy ra:

- `dir` không tồn tại: với provider mặc định thường là `NoSuchFileException`.
- `dir` là một file thường thay vì thư mục: có thể là `NotDirectoryException` hoặc một `IOException` phù hợp với hệ thống.
- Không được phép mở/đọc thư mục: có thể là `AccessDeniedException` hoặc `IOException` khác.
- Directory thay đổi hoặc thiết bị gặp lỗi khi **đang duyệt**: có thể xuất hiện ngoại lệ I/O sau lúc tạo stream.

Các subtype không được bảo đảm giống hệt trên mọi hệ điều hành/provider. Nên xử lý `IOException` có ngữ cảnh, không chuyển mọi tình huống thành “thư mục trống”.

### Phân biệt exception ở bước mở và bước duyệt

Khi thất bại ngay ở `Files.list(dir)`, bạn có thể nhận `IOException`. Nếu lỗi I/O xảy ra **sau khi stream đã được tạo** trong lúc duyệt entry, nó có thể được bọc trong **`UncheckedIOException`**, vì cơ chế `Stream` không khai báo checked exception ở mọi bước traversal.

Mẫu xử lý minh họa:

```java
try (Stream<Path> entries = Files.list(dir)) {
    entries.forEach(System.out::println);
} catch (UncheckedIOException e) {
    // Lỗi I/O trong lúc duyệt stream; xem e.getCause().
} catch (IOException e) {
    // Lỗi khi mở directory hoặc đóng tài nguyên.
}
```

Đây là **mã minh họa**, cần import `Files`, `Path`, `Stream`, `IOException`, `UncheckedIOException` và biến `dir`. Các exception phát sinh trong callback `forEach` cũng cần được nhận diện theo ý nghĩa của chúng.

Cần tránh code:

```java
try (Stream<Path> entries = Files.list(dir)) {
    // ...
} catch (IOException e) {
    return List.of(); // Không phân biệt directory trống và lỗi I/O!
}
```

Đoạn trên chỉ minh họa anti-pattern, giả định một phương thức trả `List<Path>`. Nếu trả danh sách trống khi lỗi, hệ thống kiểm toán/tìm file có thể báo “không có dữ liệu” thay vì báo “đã không thể kiểm tra dữ liệu”.

## 10. Ví dụ 3 — directory không tồn tại, lỗi mở và vòng đời stream

Tạo file `ListErrorsDemo.java`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;

public class ListErrorsDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("list-error-");
        try {
            Path file = root.resolve("single.txt");
            Files.writeString(file, "x", StandardCharsets.UTF_8);
            Path missing = root.resolve("missing");
            try (Stream<Path> ignored = Files.list(missing)) {
                System.out.println("unexpected");
            } catch (NoSuchFileException e) {
                System.out.println("missing directory=" + e.getClass().getSimpleName());
            }
            try (Stream<Path> one = Files.list(root)) {
                System.out.println("listed file=" + one.findFirst()
                        .orElseThrow().getFileName());
            }
            System.out.println("still open for new traversal="
                    + Files.isDirectory(root));
        } finally {
            try (Stream<Path> all = Files.walk(root)) {
                all.sorted(Comparator.reverseOrder()).forEach(p -> {
                    try { Files.deleteIfExists(p); }
                    catch (IOException e) { throw new UncheckedIOException(e); }
                });
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ListErrorsDemo.java
java ListErrorsDemo
```

```text
missing directory=NoSuchFileException
listed file=single.txt
still open for new traversal=true
```

Diễn giải:

- `missing` chưa được tạo nên `Files.list(missing)` trên filesystem thông thường báo `NoSuchFileException`.
- `root` vẫn tồn tại với một file con. `Files.list(root)` cung cấp entry `single.txt`.
- `findFirst()` yêu cầu một phần tử đầu tiên từ stream **chưa xác định thứ tự**. Trong ví dụ chỉ có **một mục**, nên đầu ra ổn định. Nếu directory có nhiều mục, không được suy ra `findFirst` là tên nhỏ nhất theo alphabet.
- Stream đầu được tạo trong một `try-with-resources`. Nếu `Files.list(missing)` ném lỗi trước khi tạo stream, không có stream nào được gán cho tài nguyên đó; control chuyển sang `catch`. Với stream thành công, Java đóng khi rời khối.
- Sau đó ví dụ tiếp tục đọc directory bình thường. File ví dụ được dọn trong `finally` vì chương trình sở hữu duy nhất thư mục tạm này.

**Không kết luận** `Files.list` “đã đóng mới khiến directory vẫn tồn tại”. Đóng stream giải phóng handle, **không xóa** thư mục. Việc `Files.isDirectory(root)` trả `true` chỉ kiểm tra directory hiện còn tồn tại tại thời điểm gọi.

## 11. So sánh `Files.list`, `Files.walk`, `Files.find` và `walkFileTree`

| API | Phạm vi | Kết quả/hành vi | Lựa chọn phù hợp |
|---|---|---|---|
| `Files.list(dir)` | **Một cấp**, con trực tiếp | `Stream<Path>`, không gồm `dir` | Liệt kê file/thư mục ngay dưới một folder |
| `Files.walk(start)` | Đệ quy từ `start` (theo điều kiện depth/options) | `Stream<Path>` **gồm `start`** | Duyệt các mức, lọc đường dẫn |
| `Files.walk(start, maxDepth)` | Đệ quy giới hạn độ sâu | `Stream<Path>` gồm `start` | Giới hạn chi phí/quy mô duyệt |
| `Files.find(start, maxDepth, matcher, options...)` | Đệ quy giới hạn độ sâu | `Stream<Path>`, matcher nhận `Path` và `BasicFileAttributes` | Tìm theo đường dẫn cùng metadata |
| `Files.walkFileTree(start, visitor)` | Duyệt cây với callback | Gọi visitor vào/trước/sau directory, thông báo lỗi | Công cụ copy/delete/scan tree có kiểm soát |
| `Files.newDirectoryStream(dir)` | Một cấp, con trực tiếp | `DirectoryStream<Path>`, có thể lọc entry | Duyệt one-level với iterator và xử lý provider |

### Khi chỉ cần depth 1

`Files.list(root)` gần với `Files.walk(root, 1)` về phạm vi các **con trực tiếp**, nhưng hai API **không cùng tập kết quả**:

- `Files.list(root)` trả chỉ các entry con.
- `Files.walk(root, 1)` trả **root trước và các entry sâu tối đa một cấp**, theo quy tắc traversal của `walk`.

Nếu đang so sánh hoặc chuyển từ `list` sang `walk`, nhớ loại root ra nếu business logic chỉ muốn con trực tiếp.

### Khi muốn đệ quy

Đừng viết:

```java
Files.list(root).filter(p -> p.getFileName().toString().equals("deep.txt"))
```

rồi kết luận `deep.txt` không có ở đâu dưới `root`. File có thể nằm trong `root/docs/nested`.

Nếu yêu cầu thực sự là tìm mọi file ở các mức, ví dụ đơn giản:

```java
try (Stream<Path> entries = Files.walk(root)) {
    entries.filter(Files::isRegularFile)
           .filter(p -> p.getFileName().toString().endsWith(".txt"))
           .forEach(System.out::println);
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập; cần `root`, import và xử lý `IOException`. `Files.walk` đệ quy mặc định theo độ sâu hợp lệ của thư mục, **không tự theo symbolic link** nếu không truyền `FOLLOW_LINKS`. Cần tránh duyệt vô hạn hoặc tốn tài nguyên trên cây rất lớn; khi chỉ cần con trực tiếp, `Files.list` đơn giản hơn.

### Khi cần xử lý trạng thái của từng directory

`walkFileTree` phù hợp hơn nếu ứng dụng muốn biết lúc nào **vào** một thư mục, **rời** một thư mục, xử lý lỗi truy cập theo từng nhánh, hoặc thực hiện thao tác như xóa cây mà không chỉ dựa vào các đường dẫn. `Files.list` không phải một visitor cho cả cây.

## 12. `newDirectoryStream`: lựa chọn duyệt một cấp khác

`Files.newDirectoryStream(dir)` trả `DirectoryStream<Path>` với các entry trực tiếp. Nó cũng **phải được đóng**:

```java
try (DirectoryStream<Path> ds = Files.newDirectoryStream(dir)) {
    for (Path entry : ds) {
        System.out.println(entry.getFileName());
    }
}
```

Đây là **mã minh họa**, cần import `java.nio.file.DirectoryStream`, `Files`, `Path`, biến `dir` và xử lý `IOException`. API này hữu ích khi muốn kiểu iterator hoặc bộ lọc ở lúc lấy directory entry:

```java
try (DirectoryStream<Path> ds =
             Files.newDirectoryStream(dir, "*.txt")) {
    for (Path entry : ds) {
        System.out.println(entry.getFileName());
    }
}
```

Đây là **đoạn minh họa**; mẫu glob `"*.txt"` áp dụng **tên entry trực tiếp**, không làm đệ quy. Trong một số tình huống, `DirectoryStream.Filter<? super Path>` cho phép lọc theo điều kiện tùy chỉnh. Dù dùng `newDirectoryStream` hay `Files.list`, cả hai đều không tự đi qua mọi cây.

Khi đã xử lý data theo phong cách `Stream`, `Files.list` là lựa chọn gọn. Khi muốn vòng lặp directory entry trực tiếp, `newDirectoryStream` cũng phù hợp. Không có lý do phải buộc mọi đoạn code chuyển qua Stream khi API iterator giải quyết tốt hơn.

## 13. Filesystem, symbolic link và loại entry

### `Files.list` không có nghĩa chỉ “regular files”

`Files.list(dir)` trả directory entries. Trong thư mục có thể tồn tại:

- File thường.
- Thư mục con.
- Symbolic link.
- Các loại entry đặc biệt khác tùy filesystem.

`Files.isRegularFile(p)` dùng để kiểm tra một `Path` có đang trỏ tới file thường hay không. Mặc định nhiều phép kiểm tra theo đường dẫn **theo symbolic link** đến đích nếu có; nếu muốn kiểm tra chính link, truyền `LinkOption.NOFOLLOW_LINKS` tới những API hỗ trợ.

Ví dụ các kiểm tra (mã minh họa):

```java
boolean isRegular = Files.isRegularFile(entry);
boolean isDirectory = Files.isDirectory(entry);
boolean isLink = Files.isSymbolicLink(entry);
```

Cần có `Path entry`, import `Files`; mỗi kết quả là thông tin tại thời điểm kiểm tra và có thể thay đổi ngay sau đó.

### `Files.list` có tự theo symlink để đệ quy không?

**Không có bước đệ quy ngay từ đầu.** Nếu một entry là symlink tới một thư mục khác, `Files.list(root)` chỉ cung cấp **entry symlink trực tiếp** đó như một `Path`, không tự mở cây thư mục đích để thêm các entry cháu vào cùng stream.

Nếu bạn **truyền một `Path` trỏ qua symlink tới directory** làm chính tham số `dir`, cách provider resolve đường dẫn có thể cho phép liệt kê directory đích. Đó là câu chuyện khác với việc tự đi sâu từ một entry của root.

Với `Files.walk`, theo link hay không là quyết định option như `FOLLOW_LINKS`; khi theo link trên cây có vòng lặp, traversal có thể báo `FileSystemLoopException`. Vì vậy code thao tác sâu cần hiểu symlink trước khi bật follow links.

### “Hidden file” vẫn là một entry

`Files.list` không tự bỏ file ẩn, file có tên bắt đầu bằng dấu chấm hay entry khác chỉ vì giao diện file manager thường giấu chúng. Nếu muốn bỏ các entry được coi là hidden, có thể cân nhắc `Files.isHidden(path)` nhưng phương thức này có semantics tùy filesystem và có thể ném `IOException`. Không giả định “file bắt đầu bằng dấu `.`” là định nghĩa file ẩn chung trên mọi OS.

## 14. Những giới hạn của `Files.list` cần biết

### 14.1 Không có thứ tự mặc định

Nếu ứng dụng xây bảng UI hoặc xuất báo cáo đòi hỏi ổn định, phải quyết định sort theo **tên**, thời gian sửa, kích thước hoặc tiêu chí khác. Đừng dùng thứ tự ngẫu nhiên của hệ thống file để làm thứ tự dữ liệu nghiệp vụ.

### 14.2 Không tạo snapshot bất biến

Thư mục có thể bị thay đổi bởi thread/process khác khi stream còn mở. Các thao tác sửa đổi có thể có hoặc không được phản ánh trong các entry đã liệt kê; `Files.list` là phép duyệt **weakly consistent** theo tài liệu, không cung cấp snapshot nguyên tử.

Nếu cần bảo đảm “danh sách tại cùng một thời điểm”, phải dùng cơ chế snapshot, phối hợp với producer hoặc chiến lược phiên bản hóa/đồng bộ phù hợp. `toList()` chỉ lưu lại các `Path` đã thấy; không khóa file hoặc giữ metadata bất biến.

### 14.3 Không tự truy cập metadata để lọc

`Files.list` trả `Path`; một thao tác `Files.isRegularFile`, `Files.size` hoặc `Files.getLastModifiedTime` có thể thực hiện thêm truy vấn filesystem, và trạng thái có thể đổi giữa hai lần gọi. Nếu cần duyệt sâu và dùng metadata của từng mục, `Files.find` có predicate nhận `BasicFileAttributes` giúp diễn đạt đúng công việc.

### 14.4 Không tự khắc phục lỗi quyền truy cập

Có quyền thấy tên file chưa chắc có quyền mở/đọc nội dung file đó. Ngược lại, `Files.list` có thể thất bại khi không thể đọc directory dù một `Path` cụ thể ở nơi khác vẫn sử dụng được theo cách khác. Thiết kế phải phân biệt **liệt kê**, **đọc file**, **ghi file** và **duyệt thư mục sâu hơn**.

### 14.5 Duyệt directory rất lớn có chi phí

Tạo stream không có nghĩa giữ sẵn toàn bộ kết quả trong RAM. Tuy nhiên, `sorted()`, `toList()` hoặc `collect` có thể giữ nhiều entry trong bộ nhớ. Với thư mục có hàng triệu mục, cân nhắc giới hạn xử lý, batch, streaming, độ sâu, timeout và thiết kế storage/index thay vì vô thức collect toàn bộ.

### 14.6 Duyệt song song không phải mặc định tốt hơn

`entries.parallel()` không tự biến filesystem thành nguồn dữ liệu hỗ trợ parallel traversal hiệu quả. Các phép metadata I/O và ordering có thể làm kết quả không nhanh hơn hoặc khó kiểm soát tài nguyên. Ưu tiên cách tuần tự dễ quan sát cho bài toán liệt kê thông thường; chỉ tăng song song khi có yêu cầu và đo lường thực tế.

## 15. Khi nào dùng `Files.list` trong ứng dụng?

### Tình huống A — hiển thị nội dung ngay trong một folder

Ứng dụng quản lý file cần liệt kê các item dưới đường dẫn hiện tại: `Files.list(currentDirectory)` là mô hình đúng. Mỗi entry có thể được hiển thị thành tên, loại, kích thước và thao tác mở thư mục con khi người dùng bấm. **Chỉ khi người dùng chuyển vào thư mục con**, ứng dụng mới cần list thư mục con đó.

### Tình huống B — xử lý tất cả file import nằm ngay trong inbox

Một dịch vụ nhập file từ thư mục `inbox` có quy tắc: chỉ xử lý file nằm **ngay ở inbox**, không đi vào `inbox/archived` hoặc `inbox/failed`. `Files.list(inbox).filter(Files::isRegularFile)` phù hợp vì nó không vô tình quét thư mục con.

Dù vậy, nếu file đang được copy vào inbox, có thể thấy file còn dở hoặc entry thay đổi giữa khi list và khi đọc. Cần quy tắc publish file hoàn chỉnh (ví dụ tạo temp rồi rename/move theo contract) thay vì xem list là xác nhận file đã sẵn sàng.

### Tình huống C — tìm một file đúng tên ở cấp hiện tại

Nếu biết tên file, thường **không cần list**:

```java
Path candidate = dir.resolve("config.json");
if (Files.isRegularFile(candidate)) {
    // Làm việc với candidate và xử lý lỗi khi thực sự mở nó.
}
```

Đây là **mã minh họa**, cần biến `dir`, import các lớp và xử lý I/O. Việc dựng đúng đường dẫn rồi mở có thể đơn giản, hiệu quả hơn quét toàn bộ directory để tìm tên cố định.

Nếu phải tìm “file `config.json` ở bất kỳ thư mục con nào”, mới cân nhắc `Files.walk`/`Files.find` hoặc một chỉ mục file phù hợp.

### Tình huống D — báo cáo một cấp

Với yêu cầu thống kê **bao nhiêu entry con** hoặc **bao nhiêu file thường ở cấp hiện tại**, `Files.list` vừa khớp yêu cầu. Nếu chỉ cần đếm file thường:

```java
try (Stream<Path> entries = Files.list(dir)) {
    long directFiles = entries.filter(Files::isRegularFile).count();
}
```

Đây là **mã minh họa**, không phải chương trình độc lập. Kết quả không bao gồm file nằm ở sâu hơn. Cũng không có bảo đảm rằng filesystem không đổi trong suốt quá trình đếm.

## 16. Không dùng kết quả liệt kê như kiểm tra bảo mật đủ mạnh

`Path` từ `Files.list` có thể được sử dụng trong ứng dụng xóa, di chuyển, upload hoặc phân quyền. Nhưng **chỉ thấy một entry dưới root** không đảm bảo mọi thao tác tiếp theo đều an toàn:

- Symbolic link có thể dẫn tới nơi khác.
- File có thể bị thay đổi hoặc thay thế sau khi liệt kê (**TOCTOU**, time-of-check-to-time-of-use).
- Một entry được liệt kê có thể biến mất trước khi mở.
- Quyền đọc directory khác với quyền đọc nội dung file hoặc quyền ghi.
- Nếu ứng dụng tự thêm một tên do người dùng cung cấp vào đường dẫn, cần xử lý `..`, absolute path, root boundary và symlink theo threat model.

`normalize()` chỉ xử lý đường dẫn theo cú pháp, **không** khóa filesystem và không tự resolve mọi symlink. `Path.startsWith(root)` tốt hơn kiểm tra tiền tố chuỗi, nhưng vẫn chưa đủ chống symlink/race khi dữ liệu đầu vào không tin cậy.

Với chương trình quản lý file nhạy cảm, hãy thực hiện operation cần thiết và xử lý lỗi; cân nhắc directory-handle-based API như `SecureDirectoryStream` khi provider hỗ trợ, cùng quyền filesystem và chiến lược phòng TOCTOU phù hợp.

## 17. Tự kiểm tra và lỗi thường gặp

**Lỗi 1 — Tưởng `Files.list` đệ quy.** Chỉ có con trực tiếp; file sâu hơn không thuộc stream.

**Lỗi 2 — Quên rằng kết quả còn chứa thư mục.** Nếu đếm file thường, cần `filter(Files::isRegularFile)`.

**Lỗi 3 — Quên đóng stream.** Terminal operation không tự đảm bảo đóng directory handle; dùng `try-with-resources`.

**Lỗi 4 — Nghĩ danh sách đã sắp xếp.** Thứ tự không được cam kết; dùng comparator phù hợp.

**Lỗi 5 — Dùng lại stream sau `count()` hoặc `forEach()`.** Stream không thể tiêu thụ lại; mở stream mới hoặc collect khi quy mô cho phép.

**Lỗi 6 — Nhầm `Files.walk(dir, 1)` với `Files.list(dir)` ở số lượng.** `walk` còn bao gồm chính `dir`.

**Lỗi 7 — Dùng `.getFileName()` nhưng mong có đường dẫn file đầy đủ.** Chỉ giữ tên cuối, có thể mất ngữ cảnh directory.

**Lỗi 8 — Trả danh sách rỗng khi không có quyền duyệt.** “Thư mục trống” và “đọc thất bại” cần tách thành hai trạng thái.

**Lỗi 9 — Không xử lý `UncheckedIOException`.** Có thể phát sinh trong lúc stream traversal sau khi đã mở thành công.

**Lỗi 10 — Dùng `Files.isRegularFile` như bảo đảm file không thay đổi.** File có thể bị xóa/chuyển/đổi quyền sau kiểm tra.

**Lỗi 11 — Tự động theo link để duyệt sâu mà không tính vòng lặp.** `Files.list` không đệ quy; khi dùng `walk` với `FOLLOW_LINKS` phải có chiến lược xử lý link/loop.

**Lỗi 12 — Thu thập mọi entry của directory cực lớn rồi sort/collect.** Có thể tốn RAM và thời gian; chọn xử lý streaming hay indexing tùy mục tiêu.

**Lỗi 13 — Tưởng dấu `.txt` chứng minh nội dung text.** Phần mở rộng chỉ là tên, không bảo đảm charset/MIME/content hợp lệ.

**Lỗi 14 — Tưởng gọi `Files.list` đã đọc nội dung file.** Nó chỉ cấp đường dẫn; muốn đọc file cần API khác.

**Lỗi 15 — Dùng `limit(N)` trước sort rồi muốn “N file đầu alphabet”.** Phải xét thứ tự thao tác và yêu cầu đầu ra; list không có ordering mặc định.

**Lỗi 16 — Phụ thuộc vào filesystem không đổi.** `Files.list` không cung cấp snapshot nguyên tử và có thể phản ánh thay đổi trong khi duyệt.

## 18. Bảng quyết định nhanh

| Mục tiêu | API nên chọn | Lưu ý |
|---|---|---|
| Liệt kê các entry ở ngay một thư mục | `Files.list(dir)` | Một cấp, không gồm `dir`; nhớ đóng |
| Lấy tên file ở cấp hiện tại | `list(dir).map(p -> p.getFileName())` | Không tự sắp xếp |
| Đếm file thường trực tiếp | `list(dir).filter(Files::isRegularFile).count()` | Không tính file trong thư mục con |
| Lọc tên file bằng mẫu glob ở cấp hiện tại | `Files.newDirectoryStream(dir, "*.txt")` | Không đệ quy; phải đóng |
| Tìm file ở mọi cấp | `Files.walk(dir)` | Gồm root, có thể tốn tài nguyên |
| Chỉ duyệt đến độ sâu 1 tính từ root | `Files.walk(dir, 1)` | Gồm root; khác `list` |
| Tìm theo tên + metadata ở cây | `Files.find(dir, depth, predicate)` | Có `BasicFileAttributes` |
| Xử lý copy/delete tree có điều kiện | `Files.walkFileTree` | Visitor/error handling |
| Tìm file **đã biết đường dẫn chính xác** | `dir.resolve(name)` rồi open/check | Không cần list toàn bộ |
| Tạo giao diện browser file một cấp | `Files.list(currentDir)` | Hiển thị folder như entry, vào sâu khi yêu cầu |

## 19. Câu hỏi tự luyện

**Câu 1.** Thư mục `root` chứa `a.txt`, `docs`; `docs` chứa `b.txt`. `Files.list(root)` có trả `b.txt` không?  
**Đáp án:** Không. Chỉ `a.txt` và `docs` là con trực tiếp.

**Câu 2.** Kết quả `Files.list(root).count()` có phải tổng file trong cả cây không?  
**Đáp án:** Không. Nó đếm các entry ở một cấp; bao gồm thư mục, symlink hay entry khác nếu có.

**Câu 3.** Có thể dùng `Files.list(root).filter(Files::isRegularFile)` để tìm file thường trong `root/docs` không?  
**Đáp án:** Không; filter không làm đệ quy. Cần một API duyệt sâu hoặc mở riêng `docs`.

**Câu 4.** Vì sao `Files.walk(root, 1).count()` có thể lớn hơn `Files.list(root).count()` đúng 1?  
**Đáp án:** `walk(root, 1)` còn cung cấp chính `root`, trong khi `list` chỉ cung cấp các con trực tiếp.

**Câu 5.** Một stream `Files.list` đã gọi `count()`, có gọi tiếp `forEach()` được không?  
**Đáp án:** Không. Cần stream mới hoặc thu thập dữ liệu khi dùng lần đầu.

**Câu 6.** Sau `Files.list(dir).toList()`, directory handle có tự đóng không?  
**Đáp án:** Không có bảo đảm tự đóng chỉ nhờ terminal operation; hãy tạo stream trong `try-with-resources`.

**Câu 7.** `Files.list` luôn trả tên theo alphabet đúng không?  
**Đáp án:** Không; sắp xếp khi có yêu cầu.

**Câu 8.** `Files.list` thất bại vì không có quyền đọc directory, có nên báo “directory trống” không?  
**Đáp án:** Không; phải báo/ghi nhận lỗi truy cập riêng.

**Câu 9.** Một entry là symbolic link đến thư mục có nhiều file. `Files.list(root)` có tự thêm toàn bộ file của đích link vào kết quả không?  
**Đáp án:** Không; nó chỉ liệt kê entry link ở mức trực tiếp. Duyệt tiếp là quyết định riêng.

**Câu 10.** Vì sao gọi `Files.isRegularFile(p)` ngay sau khi list không đảm bảo `Files.readString(p)` sẽ thành công?  
**Đáp án:** Quyền và trạng thái filesystem có thể thay đổi giữa kiểm tra và mở; file còn có thể bị thay thế hoặc bị xóa.

## Kết luận

**`Files.list(dir)` chỉ liệt kê các mục con trực tiếp của `dir` — không tự đi vào thư mục con và không bao gồm chính `dir`.** Nó trả `Stream<Path>` để bạn lọc, ánh xạ, đếm hoặc sắp xếp, nhưng **không bảo đảm thứ tự**, **không tự lọc file thường** và **phải được đóng** vì giữ tài nguyên directory.

Khi nhiệm vụ chỉ yêu cầu một cấp, `Files.list` là công cụ đúng và đơn giản. Khi nhiệm vụ yêu cầu nhiều cấp, dùng `Files.walk`, `Files.find` hoặc `Files.walkFileTree` theo mức độ kiểm soát cần thiết. Trong mọi trường hợp, cần xử lý ngoại lệ I/O, symbolic link, vòng đời stream và trạng thái filesystem có thể thay đổi.

### Tài liệu Java SE 17

- [`Files.list(Path)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#list(java.nio.file.Path))
- [`Files.walk`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`Files.find` và `walkFileTree`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`DirectoryStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html)
- [`Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [`Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html)
- [`UncheckedIOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html)
