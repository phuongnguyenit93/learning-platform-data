# Đóng Stream trả về từ Files.list, Files.walk và Files.find trong Java

## 1. Tại sao Stream duyệt thư mục phải được đóng?

Trong Java NIO.2, các phương thức **`Files.list(Path)`**, **`Files.walk(Path, ...)`** và **`Files.find(Path, ...)`** tạo **`Stream<Path>`** để duyệt nội dung thư mục hoặc cây thư mục. Chúng tận dụng cơ chế *lazy traversal*: chương trình chưa cần lấy toàn bộ danh sách đường dẫn vào bộ nhớ trước khi lọc, đếm hoặc tìm phần tử đầu tiên.

Nhưng Stream ở đây **không chỉ là một pipeline tính toán trên dữ liệu trong RAM**. Nó có thể giữ tham chiếu đến **thư mục đang mở**, bộ duyệt directory và tài nguyên hệ điều hành. Đặc biệt, `walk` và `find` có thể giữ **một hoặc nhiều thư mục đang mở** trong quá trình đi sâu vào cây.

**Quy tắc quan trọng nhất:**

> **Stream<Path> nhận từ `Files.list`, `Files.walk` hoặc `Files.find` phải được đóng bằng `close()` khi sử dụng xong; ưu tiên try-with-resources.** Việc gọi terminal operation như `forEach()`, `count()`, `findFirst()` hay `toList()` **không tự thay thế việc đóng Stream**.

~~~text
Files.list(dir) / Files.walk(root) / Files.find(root, ...)
             |
             v
Stream<Path> gắn với tài nguyên duyệt thư mục
             |
             | filter / map / limit / sorted ...
             v
Terminal operation: forEach / count / findFirst / toList
             |
             | Đã tính xong kết quả, nhưng không tự close
             v
Thoát try-with-resources
             |
             v
Stream.close() -> giải phóng directory resources liên quan
~~~

Nếu quên đóng, đặc biệt ở dịch vụ chạy lâu hoặc xử lý hàng nghìn thư mục, ứng dụng có thể giữ nhiều directory handle/file descriptor hơn cần thiết. Hệ quả tùy hệ điều hành và provider: cạn tài nguyên, lỗi mở file/thư mục, hoặc trở ngại khi sửa/xóa thư mục.

Lưu ý: **không phải mọi Stream trong Java đều buộc phải đóng**. Ví dụ `List.of(1, 2, 3).stream()` chỉ xử lý dữ liệu trong bộ nhớ. Với ba API Files nói trên, **hợp đồng API quy định tài nguyên mở cần giải phóng**, nên close không phải thao tác tùy chọn.

## 2. Phân biệt list, walk và find

| API | Phạm vi duyệt | Giá trị trả về | Điểm khác biệt | Vòng đời |
| --- | --- | --- | --- | --- |
| `Files.list(dir)` | Các mục trực tiếp trong `dir`, **không đệ quy** | `Stream<Path>` | Không tự bao gồm `dir`; không tự đi vào thư mục con | **Phải đóng** |
| `Files.walk(start)` | Duyệt đệ quy từ `start`; mặc định sâu tối đa theo giới hạn int | `Stream<Path>` | Bao gồm chính `start`; duyệt depth-first | **Phải đóng** |
| `Files.walk(start, maxDepth)` | Duyệt cây nhưng giới hạn độ sâu | `Stream<Path>` | `maxDepth=0` chỉ bao gồm `start`; độ sâu 1 có thể gồm các con trực tiếp | **Phải đóng** |
| `Files.find(start, maxDepth, matcher)` | Duyệt cây và chỉ trả các path khớp bộ lọc | `Stream<Path>` | `matcher` nhận cả `Path` và `BasicFileAttributes` | **Phải đóng** |

Các tên phương thức phản ánh **phạm vi và mục đích tìm kiếm**, không phản ánh một cơ chế cleanup khác nhau. Cả ba đều yêu cầu đóng tài nguyên sau khi xong.

**`Files.list` không phải `java.io.File.list()`**. Hai API thuộc lớp khác nhau:

- `Files.list(Path)`: trả `Stream<Path>` **gắn với thư mục mở**, nên phải đóng.
- `File.list()`: trả mảng `String[]` hoặc null theo hợp đồng riêng; không phải Stream và không có cùng vòng đời Stream trả về.

Cũng không nhầm `Files.find` với phép `stream.filter` thông thường. `Files.find` **tự duyệt cây thư mục** và cung cấp metadata cho matcher; `filter` chỉ là thao tác trung gian trên một Stream đã tồn tại.

## 3. Mẫu mặc định: try-with-resources

Để liệt kê một thư mục:

~~~java
// Mảnh code trong phương thức có Path directory và xử lý IOException.
try (Stream<Path> paths = Files.list(directory)) {
    paths.forEach(System.out::println);
}
~~~

Để đi qua cây thư mục:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

Để tìm file theo thuộc tính:

~~~java
try (Stream<Path> paths = Files.find(
        root,
        4,
        (path, attrs) -> attrs.isRegularFile()
                && path.getFileName().toString().endsWith(".txt"))) {
    paths.forEach(System.out::println);
}
~~~

Đây là **các mảnh code minh họa**, giả định `Path`, `Files`, `Stream` được import và IOException được xử lý.

Cơ chế:

1. Java gọi `Files.list/walk/find` và nhận về Stream gắn với nguồn.
2. Các intermediate operation `filter`, `map`... cấu hình pipeline.
3. Terminal operation duyệt phần tử theo nhu cầu.
4. Dù body kết thúc bình thường, `return` hay ném exception, **try-with-resources cố đóng Stream**.

Cú pháp `try (Stream<Path> paths = ...)` có thể dùng vì `Stream` kế thừa `BaseStream`, mà `BaseStream` hỗ trợ `AutoCloseable` và phương thức `close()`.

**Điều phải nhớ:** nếu gọi API Files tạo Stream **ngoài** phạm vi `try` rồi gặp lỗi trước khi vào một finally/try quản lý nó, tài nguyên có nguy cơ không được đóng. Nên đặt phép mở Stream trực tiếp trong khai báo resource của try-with-resources.

## 4. Lazy traversal không có nghĩa không mở tài nguyên

Một nhầm lẫn phổ biến là “Stream lười nên chưa cần đóng cho đến khi thực sự đọc được phần tử đầu tiên”. Thực tế, việc trả Stream có thể đã thiết lập cơ chế duyệt thư mục và giữ tham chiếu tài nguyên; **API bắt buộc đóng cả khi không tiêu thụ phần tử nào**.

~~~java
// SAI: tạo Stream rồi bỏ đi mà không đóng.
Files.list(directory);
~~~

Dù không hề có terminal operation, Stream trả về không được đóng đúng thời điểm. Tương tự, cấu hình `filter` hoặc `limit` rồi bỏ pipeline không tự đóng nguồn.

Một chương trình có thể làm cả ba việc:

~~~java
Stream<Path> stream = Files.walk(root);
Stream<Path> filtered = stream.filter(Files::isRegularFile);
// Vẫn chưa chạy terminal operation.
~~~

Đây chưa phải ví dụ cleanup hoàn chỉnh: mã phải đảm bảo **đóng pipeline cuối cùng hoặc nguồn cùng vòng đời**. Dùng TWR trên pipeline được tạo trực tiếp thường rõ ràng hơn:

~~~java
try (Stream<Path> paths = Files.walk(root)
        .filter(Files::isRegularFile)) {
    paths.forEach(System.out::println);
}
~~~

Đóng pipeline có nguồn `Files.walk` làm giải phóng tài nguyên do pipeline mang theo, thay vì tiếp tục để directory handles chờ GC. **Không dùng Stream lần thứ hai** sau khi đã gọi một terminal operation trên nó.

## 5. Chương trình Java 17+ so sánh cả ba API

Tạo file **DirectoryStreamsDemo.java**, lưu mã nguồn UTF-8:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class DirectoryStreamsDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("directory-streams-");
        Path nested = root.resolve("nested");
        Path alpha = root.resolve("alpha.txt");
        Path beta = nested.resolve("beta.txt");

        try {
            Files.createDirectory(nested);
            Files.writeString(alpha, "alpha", StandardCharsets.UTF_8);
            Files.writeString(beta, "beta", StandardCharsets.UTF_8);

            try (Stream<Path> entries = Files.list(root)) {
                List<String> names = entries
                        .map(p -> p.getFileName().toString())
                        .sorted()
                        .toList();
                System.out.println("list=" + names);
            }

            try (Stream<Path> tree = Files.walk(root, 2)) {
                List<String> names = tree
                        .map(p -> p.equals(root)
                                ? "."
                                : root.relativize(p).toString()
                                      .replace('\\', '/'))
                        .sorted()
                        .toList();
                System.out.println("walk=" + names);
            }

            try (Stream<Path> matches = Files.find(
                    root, 2,
                    (p, attrs) -> attrs.isRegularFile()
                            && p.getFileName().toString()
                                    .endsWith(".txt"))) {
                List<String> names = matches
                        .map(p -> p.getFileName().toString())
                        .sorted()
                        .toList();
                System.out.println("find=" + names);
            }
        } finally {
            Files.deleteIfExists(beta);
            Files.deleteIfExists(alpha);
            Files.deleteIfExists(nested);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 DirectoryStreamsDemo.java
java DirectoryStreamsDemo
~~~

Stdout mong đợi:

~~~text
list=[alpha.txt, nested]
walk=[., alpha.txt, nested, nested/beta.txt]
find=[alpha.txt, beta.txt]
~~~

**Giải thích chi tiết:**

- Thư mục demo có `alpha.txt` tại root và `nested/beta.txt` bên dưới một thư mục con.
- `Files.list(root)` chỉ trả **hai mục ngay bên trong root**: `alpha.txt` và `nested`. Nó **không** đi tiếp đến `beta.txt` và cũng không tự trả chính `root`.
- `Files.walk(root, 2)` trả cả `root` (depth 0), hai mục trực tiếp (depth 1), và `nested/beta.txt` (depth 2). Dòng `"."` là biểu diễn do ví dụ chủ động đặt cho chính root.
- `Files.find(root, 2, matcher)` duyệt với cùng giới hạn depth 2 nhưng chỉ **đưa vào Stream** những mục có `attrs.isRegularFile()` và tên kết thúc `.txt`.
- Dùng `sorted()` để ổn định stdout giữa các hệ điều hành, vì **thứ tự liệt kê directory không được bảo đảm**. `replace('\\', '/')` chỉ chuẩn hóa dấu phân cách khi **hiển thị tương đối trong ví dụ**, không sửa Path thật.
- Cả ba Stream đều được đặt riêng trong **try-with-resources**. Mỗi nguồn được đóng trước khi chuyển sang thao tác tiếp theo.
- Khối `finally` xóa các file/thư mục tạm do chương trình sở hữu; đây là **cleanup phụ** của demo, không thay thế việc đóng Stream.

Chương trình giả định môi trường được phép tạo file và thư mục tạm; nếu quyền, bộ nhớ đĩa hoặc hệ thống I/O gặp lỗi, phương thức sẽ ném IOException thay vì in đủ stdout dự kiến.

## 6. Độ sâu của Files.walk và Files.find

Cả `walk` và `find` có tham số **`maxDepth`**:

~~~text
root/                   depth 0
root/a.txt              depth 1
root/sub/               depth 1
root/sub/b.txt          depth 2
root/sub/inner/         depth 2
root/sub/inner/c.txt    depth 3
~~~

- `maxDepth=0`: chỉ xét chính `root`.
- `maxDepth=1`: xét root và các mục trực tiếp.
- `maxDepth=2`: xét thêm các mục ở độ sâu 2.
- `maxDepth` âm: ném `IllegalArgumentException`.
- `Files.walk(root)` không truyền giới hạn được quy định tương đương việc dùng độ sâu `Integer.MAX_VALUE`.

**Giới hạn độ sâu không thay thế close()**. Chỉ đi một cấp hoặc chỉ thăm vài phần tử vẫn dùng Stream có thể giữ tài nguyên thư mục mở.

`Files.walk` duyệt **depth-first** và trả mục bắt đầu trước các mục con. Đối với mỗi directory, các mục bên trong xuất hiện khi được gặp trong quá trình duyệt. Nhưng **thứ tự các sibling không được bảo đảm theo alphabet**. Nếu cần thứ tự ổn định, áp dụng `sorted()` hoặc một comparator phù hợp, và lưu ý việc sắp xếp có thể phải giữ nhiều phần tử trong bộ nhớ.

**`Files.walk` bao gồm chính `start` ngay cả khi start là file thường**. Khi start là file thường hợp lệ, Stream có thể chỉ gồm chính đường dẫn đó; đừng hiểu rằng walk chỉ trả các file *bên trong* một directory.

## 7. Files.find: matcher nhận Path và BasicFileAttributes

Cú pháp tiêu biểu:

~~~java
try (Stream<Path> results = Files.find(
        root,
        5,
        (path, attrs) -> attrs.isRegularFile()
                && attrs.size() > 0
                && path.getFileName().toString().endsWith(".json"))) {
    results.forEach(System.out::println);
}
~~~

`BiPredicate<Path, BasicFileAttributes>` nhận:

- **`path`**: đường dẫn của mục đang được xét.
- **`attrs`**: nhóm metadata cơ bản đã lấy cho mục đó, có các thông tin như `isRegularFile()`, `isDirectory()`, `size()`, thời điểm sửa đổi...

So với `Files.walk(root).filter(p -> ...)` mà **mỗi lần lọc lại gọi `Files.readAttributes(p, ...)`**, `Files.find` có thể tránh một số lần lấy metadata trùng lặp vì API vốn truy cập thuộc tính của các mục trong lúc duyệt.

Cần phân biệt:

- **`Files.find` chỉ đưa vào kết quả những path mà matcher chấp nhận**. Nó vẫn phải duyệt các phần của cây để tìm mục phù hợp; matcher trả false cho một directory **không có nghĩa tự động cắt bỏ toàn bộ nhánh**.
- Nếu muốn **chủ động bỏ qua một subtree** khi gặp directory nhất định, `Files.walkFileTree` với `FileVisitor` và kết quả `SKIP_SUBTREE` thường phù hợp hơn.
- Vì matcher thường gọi nhiều lần, tránh side effect không cần thiết. Nếu matcher có logic I/O riêng và ném unchecked exception, exception vẫn cần được ứng dụng xử lý.

**Không coi metadata là snapshot bất biến:** file có thể thay đổi sau khi attributes được đọc. Với ứng dụng cần tính nhất quán mạnh, vẫn phải xác định chính sách khóa/snapshot hoặc cách mở file theo danh tính phù hợp.

## 8. Short-circuit không tự giải phóng directory handles

Một trong các sai lầm phổ biến nhất:

~~~java
// SAI: findFirst trả kết quả nhưng không tự close nguồn.
Path first = Files.list(directory)
        .findFirst()
        .orElse(null);
~~~

Tương tự:

~~~java
// SAI: limit(3) giới hạn phần tử, không đóng Stream.
Files.walk(root)
        .limit(3)
        .forEach(System.out::println);
~~~

Hoặc:

~~~java
// SAI: count duyệt kết quả, không tự close Stream.
long amount = Files.find(root, 3, matcher).count();
~~~

Ở mảnh cuối, `matcher` là BiPredicate phù hợp được chương trình định nghĩa.

Sửa thành:

~~~java
try (Stream<Path> entries = Files.list(directory)) {
    Path first = entries.findFirst().orElse(null);
    // Xử lý first trong thời gian tài nguyên đang mở.
}
~~~

~~~java
try (Stream<Path> tree = Files.walk(root)) {
    tree.limit(3).forEach(System.out::println);
}
~~~

~~~java
try (Stream<Path> matches = Files.find(
        root, 3, (p, a) -> a.isRegularFile())) {
    long amount = matches.count();
    System.out.println(amount);
}
~~~

`findFirst()`, `anyMatch()`, `limit()` có thể ngừng lấy phần tử sớm. `count()` thường cần duyệt dữ liệu để đếm, còn `toList()` giữ các phần tử đã thu thập. Nhưng **dù đọc không phần tử, đọc vài phần tử hay duyệt đến hết, trách nhiệm đóng Stream vẫn y nguyên**.

**TWR với stream nguồn đóng tài nguyên ở cuối block**, kể cả khi một terminal operation đã kết thúc sớm.

## 9. Ví dụ runnable: terminal operation xong nhưng chưa close

Tạo file **ShortCircuitCloseDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Stream;

public class ShortCircuitCloseDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("stream-close-");
        Path file = root.resolve("one.txt");

        try {
            Files.writeString(file, "data", StandardCharsets.UTF_8);

            AtomicBoolean closeHandlerCalled = new AtomicBoolean();

            try (Stream<Path> entries = Files.list(root)
                    .onClose(() -> closeHandlerCalled.set(true))) {

                boolean found = entries.anyMatch(path ->
                        path.getFileName().toString().equals("one.txt"));

                System.out.println("found=" + found);
                System.out.println("closedInsideTry="
                        + closeHandlerCalled.get());
            }

            System.out.println("closedAfterTry="
                    + closeHandlerCalled.get());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Chạy với Java 17+:

~~~bash
javac -encoding UTF-8 ShortCircuitCloseDemo.java
java ShortCircuitCloseDemo
~~~

Stdout:

~~~text
found=true
closedInsideTry=false
closedAfterTry=true
~~~

Giải thích:

1. `Files.list(root)` tạo Stream từ một thư mục có `one.txt`.
2. `onClose(...)` gắn **handler sẽ chạy khi close Stream**, trong demo chỉ đổi một cờ.
3. `anyMatch(...)` tìm thấy file, có thể dừng sớm. Sau khi terminal operation kết thúc, cờ vẫn **false**: terminal operation chưa gọi close.
4. Rời try-with-resources thì `close()` được gọi và handler chạy, cờ trở thành **true**.
5. Demo cho thấy thời điểm **handler close** chạy, không phải phép đo trực tiếp file descriptor của hệ điều hành. Việc Stream từ Files.list đóng tài nguyên directory là hợp đồng của Files.

Từ đây có thể suy ra: **không chỉ Stream chưa đọc hết mới cần close; Stream đã xử lý xong một terminal operation cũng vẫn phải close**.

## 10. Lỗi I/O khi mở khác lỗi khi đang duyệt

Những phương thức này công bố `throws IOException` khi **khởi tạo nguồn** không thành công, chẳng hạn:

~~~java
Stream<Path> entries = Files.list(directory);
~~~

Nếu directory không tồn tại, không phải directory, hoặc không thể mở, lệnh trên có thể ném `IOException` hoặc subclass cụ thể như `NoSuchFileException` hay `NotDirectoryException` khi provider hỗ trợ.

Nhưng vì Stream được duyệt **lười**, I/O có thể xảy ra **sau khi Files.list/walk/find đã trả về**. Khi lỗi I/O phát sinh lúc tiếp tục đọc thư mục, tài liệu Java SE 17 nêu rằng nó được **bọc vào `UncheckedIOException`** và phát sinh từ terminal/intermediate traversal đã kích hoạt truy cập đó.

~~~text
Gọi Files.list/walk/find:
    thất bại khi mở       -> IOException (checked)

Tiêu thụ Stream<Path>:
    thất bại khi duyệt     -> UncheckedIOException
                              cause là IOException gốc
~~~

Mẫu chẩn đoán:

~~~java
// Mảnh code: import java.io.IOException, java.io.UncheckedIOException
// và các lớp Path, Files, Stream.
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
} catch (java.io.UncheckedIOException traversalFailure) {
    System.err.println("Traverse failed: "
            + traversalFailure.getCause());
} catch (IOException openingFailure) {
    System.err.println("Open failed: " + openingFailure);
}
~~~

Một số chú ý:

- `UncheckedIOException.getCause()` truy cập IOException gốc để ghi log/chẩn đoán.
- Nếu chương trình **không có khả năng phục hồi**, thường nên propagate lỗi sau khi bổ sung ngữ cảnh; đừng tự coi kết quả duyệt bị cắt ngắn là thành công.
- Exception từ **lambda người dùng** (ví dụ parse, network call, hoặc runtime exception trong matcher) là một nhóm lỗi riêng; không phải mọi lỗi pipeline đều do Files API.
- Khi body ném exception và cleanup cũng phát sinh lỗi, cơ chế **primary/suppressed exceptions** của TWR cần được xét; không nuốt mất lỗi ban đầu.
- `Files.list` và `Files.walk` có tính **weakly consistent**: không đóng băng thư mục/cây trong khi duyệt. Nếu đối tượng bị thêm/xóa/đổi tên trong lúc quét, kết quả có thể phản ánh hoặc không phản ánh thay đổi. Điều này cũng có thể gây lỗi I/O.

Đừng kết hợp `Files.exists(root)` trước rồi mặc định Files.walk luôn thành công. Kiểm tra và dùng là hai thời điểm khác nhau; tài nguyên có thể biến mất hoặc quyền truy cập thay đổi. Xử lý ngay tại thao tác thực tế.

## 11. Trả Stream ra khỏi phương thức: ai chịu trách nhiệm đóng?

Với một phương thức dịch vụ, có hai cách thiết kế rõ ràng.

### Cách A — xử lý trong phương thức và trả kết quả đã hoàn thành

~~~java
// Mảnh code, có imports thích hợp.
static long countDirectEntries(Path dir) throws IOException {
    try (Stream<Path> paths = Files.list(dir)) {
        return paths.count();
    }
}
~~~

Ưu điểm: phương thức **tự sở hữu và tự đóng** Stream. Caller nhận `long`, không phải quản lý directory handle. Điều này thường dễ dùng và khó bị leak hơn.

### Cách B — trả Stream sống và chuyển trách nhiệm close cho caller

~~~java
static Stream<Path> openTextFiles(Path root)
        throws IOException {
    return Files.walk(root)
            .filter(p -> Files.isRegularFile(p)
                    && p.getFileName().toString().endsWith(".txt"));
}
~~~

Caller phải đóng:

~~~java
try (Stream<Path> textFiles = openTextFiles(root)) {
    textFiles.forEach(System.out::println);
}
~~~

Cách B phù hợp nếu API thật sự muốn trả kết quả lazy. Nhưng **ownership đã chuyển cho caller**; tên/hợp đồng API nên nói rõ kết quả là Stream giữ directory resources cần close.

**Mẫu sai:**

~~~java
// SAI: đóng nguồn trong phương thức trước khi caller tiêu thụ.
static Stream<Path> broken(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths.filter(Files::isRegularFile);
    }
}
~~~

TWR chạy close **trước khi trả kết quả cho caller**. Stream trả về đã gắn với pipeline bị đóng, nên không thể dùng nó như một nguồn duyệt hợp lệ.

Có thể dùng `Stream.onClose(...)` cho cleanup tùy chỉnh khi xây API, nhưng cần hiểu *tài nguyên nào được sở hữu*. Với Files.list/walk/find, đóng đúng Stream được trả về là đủ; không tự tạo thêm close handler giả lập nếu chỉ để thay thế cơ chế vốn đã có.

## 12. Stream dùng một lần và xử lý trung gian

Một Stream chỉ dùng cho **một pipeline tiêu thụ**. Sau:

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    long n = paths.count();
    // paths.findFirst(); // Không hợp lệ: Stream đã được tiêu thụ.
}
~~~

Không gọi tiếp `findFirst()`, `forEach()` hoặc terminal operation khác trên cùng Stream. Một số thao tác có thể ném `IllegalStateException` vì stream đã vận hành hoặc đóng.

Nếu cần hai thống kê khác nhau, có thể thiết kế **một collector** tổng hợp trong một lượt duyệt, hoặc **mở Stream mới** cho lượt thứ hai; mỗi Stream phải có TWR của riêng nó.

Khi dùng derived pipeline:

~~~java
try (Stream<Path> result = Files.walk(root)
        .filter(Files::isRegularFile)
        .limit(10)) {
    result.forEach(System.out::println);
}
~~~

Đóng derived pipeline cũng đóng tài nguyên liên quan đến nguồn duyệt của pipeline. Không cần giữ ba biến Stream rồi cố đóng mỗi biến nhiều lần.

**Không đồng nhất lazy với tiết kiệm bộ nhớ ở mọi trường hợp.** `sorted()` và `toList()` có thể cần giữ rất nhiều `Path` trong bộ nhớ; các phép toán như `count()` hoặc `anyMatch()` thường chỉ giữ ít trạng thái. Nếu thư mục rất lớn, cân nhắc xử lý từng Path thay vì collect toàn bộ rồi mới thao tác.

## 13. Symbolic link, vòng lặp và tùy chọn FOLLOW_LINKS

Mặc định, `Files.walk` và `Files.find` **không tự theo các symbolic link tới directory con** theo cách duyệt đệ quy như một thư mục thực. Nếu muốn theo symlink, có thể chọn `FileVisitOption.FOLLOW_LINKS`:

~~~java
try (Stream<Path> paths = Files.walk(
        root, 10, java.nio.file.FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
}
~~~

Tuy nhiên:

- Theo link có thể dẫn cây duyệt ra ngoài vị trí mà ứng dụng ban đầu tưởng là root.
- Một symlink có thể quay lại thư mục tổ tiên, tạo **chu trình**. API duyệt file tree có quy tắc phát hiện loop và có thể phát sinh lỗi như `FileSystemLoopException` dưới dạng lỗi I/O trong quá trình duyệt.
- File system có thể thay đổi trong quá trình duyệt, nên các kết quả/thuộc tính không phải snapshot bất biến.
- Chọn có theo link hay không phải dựa trên nghiệp vụ và yêu cầu an toàn, không bật FOLLOW_LINKS chỉ để “tìm được nhiều file hơn”.

**Không dùng `normalize()` hoặc một lần kiểm tra `isDirectory()` để giả định traversal không chịu tác động từ symbolic link hay race.** Với đường dẫn không đáng tin, cần áp dụng chính sách quản lý file system phù hợp.

## 14. Vì sao filter không tự cắt nhánh duyệt cây?

Đoạn:

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    paths.filter(p -> !p.getFileName().toString()
                    .equals("node_modules"))
         .forEach(System.out::println);
}
~~~

Chỉ có nghĩa: **không đưa một số Path mang tên node_modules vào đầu ra**. Nó **không đảm bảo bỏ qua việc đi sâu vào bên trong thư mục node_modules**. `Files.walk` vẫn có thể tiếp tục thăm các mục con để tạo phần tử đầu vào cho `filter`.

Nếu cần **prune subtree** thật sự, dùng visitor:

~~~java
// Mảnh code: import Files, Path, FileVisitResult,
// SimpleFileVisitor, BasicFileAttributes và IOException.
Files.walkFileTree(root,
        new java.nio.file.SimpleFileVisitor<Path>() {
    @Override
    public java.nio.file.FileVisitResult preVisitDirectory(
            Path dir,
            java.nio.file.attribute.BasicFileAttributes attrs) {
        if (dir.getFileName() != null
                && dir.getFileName().toString()
                        .equals("node_modules")) {
            return java.nio.file.FileVisitResult.SKIP_SUBTREE;
        }
        return java.nio.file.FileVisitResult.CONTINUE;
    }
});
~~~

Đây là **mảnh code**, không phải class chạy độc lập. `Files.walkFileTree` dùng visitor/callback để kiểm soát traversal (bao gồm SKIP_SUBTREE) thay vì trả Stream<Path> cần đóng; visitor vẫn phải xử lý IOException và các callback lỗi theo hợp đồng.

Với tác vụ duyệt cây yêu cầu **xóa đệ quy, bỏ qua nhánh, phân loại lỗi từng nhánh hoặc xử lý trạng thái có cấu trúc**, `walkFileTree` thường phù hợp hơn `walk(...).filter(...)`.

## 15. Files.newDirectoryStream và DirectoryStream cũng phải đóng

Bên cạnh Stream API, Java có:

~~~java
try (java.nio.file.DirectoryStream<Path> entries =
        Files.newDirectoryStream(directory)) {
    for (Path p : entries) {
        System.out.println(p);
    }
}
~~~

`DirectoryStream<Path>` là **một API khác** với `Stream<Path>`, nhưng cũng mở directory và cần đóng sau khi duyệt. Nó hỗ trợ iterator và có thể dùng glob filter khi mở:

~~~java
try (java.nio.file.DirectoryStream<Path> textEntries =
        Files.newDirectoryStream(directory, "*.txt")) {
    for (Path p : textEntries) {
        System.out.println(p.getFileName());
    }
}
~~~

DirectoryStream có quy tắc lỗi và vòng đời riêng; đừng nhầm thao tác `iterator.hasNext()` với terminal operation của Java Stream. Việc dùng for-each **không tự đóng** DirectoryStream; TWR ở ví dụ là nơi đóng nó.

Nếu rất cần API **`Stream<Path>`**, dùng list/walk/find là lựa chọn tự nhiên. Nếu cần kiểm soát iterator và filter theo tên cho một directory, newDirectoryStream cũng đáng cân nhắc.

## 16. Chọn công cụ theo mục tiêu

| Nhu cầu | API thường phù hợp | Cách quản lý tài nguyên |
| --- | --- | --- |
| Liệt kê ngay các mục của một thư mục | `Files.list(dir)` | TWR trên Stream |
| Đếm mục trực tiếp | `Files.list(dir).count()` trong TWR | Đóng dù count xong |
| Duyệt cả cây | `Files.walk(root)` | TWR trên Stream |
| Duyệt cây đến độ sâu cố định | `Files.walk(root, maxDepth)` | TWR trên Stream |
| Tìm các mục theo metadata | `Files.find(root, depth, predicate)` | TWR trên Stream |
| Dừng sớm sau vài Path | `limit(n)`, `findFirst()` trong pipeline | **Vẫn đóng** dù short-circuit |
| Bỏ qua nguyên subtree | `Files.walkFileTree` + `SKIP_SUBTREE` | Kiểm soát callback và lỗi duyệt |
| Duyệt một thư mục bằng for-each | `Files.newDirectoryStream(dir)` | TWR trên DirectoryStream |
| Cần kết quả dùng sau khi đóng nguồn | Tính toán/collect trong TWR | Trả List/Map/giá trị, không trả Stream đã đóng |
| Cần trả kết quả lazy ra ngoài | Trả Stream còn mở có contract ownership | **Caller phải đóng** |

Nếu thư mục liên tục thay đổi, việc xử lý kết quả cũng phải chấp nhận trạng thái **weakly consistent** hoặc bổ sung chính sách snapshot/đồng bộ. **Close giải quyết vòng đời tài nguyên, không làm phép duyệt trở thành snapshot hay transaction.**

## 17. Các lỗi thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| `Files.list(dir).forEach(...)` rồi bỏ Stream | Không đóng directory resource đúng hạn | TWR quanh Stream |
| `Files.walk(root).count()` không close | Terminal operation không tự close | TWR độc lập với count |
| `Files.find(...).findFirst()` không close | Short-circuit vẫn giữ nguồn | Close Stream sau khi lấy kết quả |
| Tưởng Files.list duyệt đệ quy | Bỏ sót file bên dưới directory con | Dùng walk hoặc find |
| Tưởng Files.walk không trả chính root | Đếm hoặc xử lý sai một phần tử | Biết root là phần tử đầu của traversal |
| Dùng filter bỏ directory rồi tưởng bỏ cả subtree | Vẫn đi sâu vào nhánh | walkFileTree + SKIP_SUBTREE |
| Chỉ bắt IOException lúc gọi Files.walk | Bỏ lọt lỗi khi tiêu thụ dưới dạng UncheckedIOException | Xử lý cả hai giai đoạn |
| Trả Stream từ try-with-resources đã kết thúc | Caller nhận Stream đóng | Trả kết quả hoàn chỉnh hoặc chuyển ownership |
| Gọi count rồi findFirst trên cùng Stream | Stream đã tiêu thụ | Tạo Stream mới hoặc gom trong một lượt |
| Giả định thứ tự list ổn định | Kết quả phụ thuộc provider và directory | Sort khi cần; cân nhắc RAM |
| Bật FOLLOW_LINKS tùy tiện | Có thể đi ra ngoài cây hoặc gặp loop | Xác định chính sách link, giới hạn depth |
| Dùng sorted().toList() trên cây cực lớn | Giữ nhiều Path trong bộ nhớ | Xử lý streaming hoặc duyệt có kiểm soát |
| Không đóng DirectoryStream khi for-each | Duyệt xong chưa phải close | TWR trên DirectoryStream |
| Sửa/xóa trong khi vẫn dựa vào Stream traversal mở | Có thể không nhất quán hoặc gặp I/O lỗi | Thiết kế thao tác riêng, xử lý lỗi |
| Không cleanup khi terminal operation ném | Stream còn tài nguyên mở | TWR bao cả pipeline |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Ba API `Files.list`, `Files.walk` và `Files.find` có phải trả dữ liệu hoàn toàn trong bộ nhớ nên không cần đóng?  
**Đáp án:** Không. Stream của chúng có thể giữ directory resources đang mở. Cần close sau khi dùng, tốt nhất bằng TWR.

**Câu 2.** `Files.list(dir)` có trả các file trong thư mục con của dir không?  
**Đáp án:** Không. Nó chỉ liệt kê mục trực tiếp; dùng `walk` hoặc `find` nếu cần đệ quy.

**Câu 3.** `Files.walk(root, 0)` có trả Path nào không?  
**Đáp án:** Có. Nó bao gồm chính root nếu mở/truy cập start thành công; depth 0 chỉ xét start.

**Câu 4.** Vì sao `Files.find(root, 3, matcher)` có thể thích hợp hơn `Files.walk(root, 3).filter(...)` khi cần nhiều metadata?  
**Đáp án:** Matcher của find nhận sẵn BasicFileAttributes; có thể tránh lấy thuộc tính lặp lại. Nó vẫn cần duyệt cây để tìm phần tử.

**Câu 5.** Nếu `findFirst()` hoặc `limit(1)` chỉ dùng một phần tử, có cần close Stream không?  
**Đáp án:** Có. Việc dừng sớm của terminal/pipeline không đóng tài nguyên.

**Câu 6.** Lỗi khi mở thư mục và lỗi khi đang duyệt có thể khác kiểu exception như thế nào?  
**Đáp án:** Lỗi mở có thể là checked IOException; lỗi I/O xảy ra trong traversal sau khi API đã trả Stream được bọc thành UncheckedIOException.

**Câu 7.** Tại sao không nên return Stream từ khối try-with-resources trong factory?  
**Đáp án:** TWR đóng Stream trước khi caller nhận được, khiến pipeline trả về không thể sử dụng như một nguồn còn sống.

**Câu 8.** `Files.walk(root).filter(p -> !name.equals("cache"))` có tự bỏ qua toàn bộ nội dung thư mục cache?  
**Đáp án:** Không. Filter chỉ lọc phần tử ra khỏi đầu ra; dùng walkFileTree và SKIP_SUBTREE nếu cần cắt nhánh.

**Câu 9.** Nếu cần kết quả ổn định theo thứ tự alphabet trong một thư mục, có thể giả định Files.list sắp xếp sẵn không?  
**Đáp án:** Không. Dùng sorted() hoặc comparator phù hợp và hiểu chi phí giữ phần tử.

**Câu 10.** Nếu Stream đã được tiêu thụ hết bởi `forEach`, gọi `close()` còn cần thiết không?  
**Đáp án:** Có. Terminal operation hoàn tất khác với đóng nguồn I/O; close giải phóng resources theo hợp đồng.

## 19. Tài liệu Java SE 17

- [Files.list(Path)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#list(java.nio.file.Path)): duyệt trực tiếp directory và quy định đóng Stream.
- [Files.walk(Path, int, FileVisitOption...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walk(java.nio.file.Path,int,java.nio.file.FileVisitOption...)): duyệt depth-first, maxDepth, tài nguyên thư mục mở.
- [Files.find(Path, int, BiPredicate, FileVisitOption...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#find(java.nio.file.Path,int,java.util.function.BiPredicate,java.nio.file.FileVisitOption...)): matcher với BasicFileAttributes và vòng đời Stream.
- [BaseStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html): close(), onClose() và tính chất một lần dùng.
- [Files.walkFileTree](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.nio.file.FileVisitor)): visitor để điều khiển duyệt/cắt nhánh.
- [DirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html): iterator duyệt directory và quản lý close.

**Tổng kết:** **`list`** duyệt một cấp, **`walk`** duyệt cây, còn **`find`** duyệt cây và chọn path theo predicate có metadata. Cả ba đều trả Stream<Path> gắn với thư mục mở, nên **bắt buộc quản lý vòng đời bằng try-with-resources hoặc cơ chế tương đương**. Lazy traversal, terminal operation hoàn tất, short-circuit, `count`, `toList` hay kết quả đã tìm thấy **đều không tự làm tài nguyên được đóng**.
