# `Files.walk` và độ sâu tối đa khi duyệt cây thư mục trong Java

Trong ứng dụng thực tế, đôi khi bạn cần tìm các tệp trong một thư mục, nhưng **chỉ đi sâu đến một số cấp nhất định**: duyệt thư mục hiện tại, thư mục con trực tiếp, hoặc thêm một vài tầng nữa. Java NIO.2 cung cấp `Files.walk(...)` để duyệt cây và tham số `maxDepth` để **giới hạn việc đi xuống các thư mục con**.

Ví dụ, nếu một thư mục chứa nhiều nhánh sâu hàng trăm cấp, `Files.walk(root, 2)` chỉ duyệt đến các đối tượng có khoảng cách tối đa **hai cạnh** so với `root`. Điều này khác với duyệt toàn bộ cây rồi mới lọc kết quả theo độ sâu: tham số `maxDepth` cho phép **không cần đi xuống** các nhánh vượt mức cho phép.

Bài này tập trung vào cách hiểu độ sâu, các overload của `Files.walk`, vòng đời `Stream<Path>`, cách lọc tệp/thư mục, symbolic link, lỗi I/O và một ví dụ Java 17 có kết quả kiểm chứng được.

## 1. `Files.walk` trả về gì?

Hai chữ ký quan trọng của `java.nio.file.Files`:

~~~java
Stream<Path> paths = Files.walk(start);
Stream<Path> limited = Files.walk(start, maxDepth);
~~~

Có overload tổng quát thêm tùy chọn duyệt:

~~~java
Stream<Path> paths = Files.walk(
        start, maxDepth, FileVisitOption.FOLLOW_LINKS);
~~~

Trong đó:

- `start`: đối tượng `Path` chỉ điểm bắt đầu; thông thường là một thư mục.
- `maxDepth`: số nguyên `int` không âm, giới hạn mức sâu lớn nhất được đưa vào kết quả.
- `FileVisitOption...`: tùy chọn như `FOLLOW_LINKS` để thay đổi cách xử lý symbolic link.
- **Giá trị trả về:** `Stream<Path>` duyệt các đường dẫn phát hiện được, trong đó **`start` cũng là một phần tử**.
- `Files.walk(start)` tương đương đi sâu tối đa theo giá trị không giới hạn thực tế của `Integer.MAX_VALUE`, không phải chỉ một cấp.

**Điều kiện đặc biệt:** `maxDepth < 0` là tham số không hợp lệ và có thể gây `IllegalArgumentException`; đừng dùng số âm để biểu diễn “không giới hạn”. Muốn không đặt giới hạn thực tế, gọi overload `Files.walk(start)`.

`Files.walk` sử dụng cách đi qua cây **depth-first**: bắt đầu từ `start` rồi duyệt các mục bên dưới trước khi chuyển sang nhánh khác. **Thứ tự các mục cùng thư mục không được bảo đảm** bởi API, nên đừng mong tệp được trả về tự động theo tên tăng dần.

Kết quả là **luồng xử lý lười (lazy stream)**: không nên hiểu lời gọi `Files.walk` đã đọc toàn bộ cây vào bộ nhớ. Các thao tác terminal như `forEach`, `count` và `toList` mới kích hoạt việc tiêu thụ stream.

## 2. Hiểu chính xác `maxDepth`: cấp 0 là điểm bắt đầu

Xét cây ví dụ:

~~~text
root/                       (depth 0)
├── root.txt                (depth 1)
├── docs/                   (depth 1)
│   ├── readme.txt          (depth 2)
│   └── archive/            (depth 2)
│       └── old.txt         (depth 3)
└── images/                 (depth 1)
    └── logo.bin            (depth 2)
~~~

`maxDepth` đếm **số cạnh đường đi từ `start` tới mỗi mục**, không phải số dấu `/` trong đường dẫn tuyệt đối.

| Lệnh | Những mục nằm trong phạm vi | Số đường dẫn của cây ví dụ |
|---|---|---:|
| `Files.walk(root, 0)` | Chỉ `root` | 1 |
| `Files.walk(root, 1)` | `root` và các mục con trực tiếp | 4 |
| `Files.walk(root, 2)` | Thêm `docs/readme.txt`, `docs/archive`, `images/logo.bin` | 7 |
| `Files.walk(root, 3)` | Thêm `docs/archive/old.txt` | 8 |
| `Files.walk(root)` | Tất cả các cấp, nếu không bị lỗi hoặc hạn chế khác | 8 |

Từ đó rút ra:

1. **`maxDepth = 0`:** vẫn nhận **một mục `start`**, nếu điểm bắt đầu hợp lệ; không phải luồng rỗng.
2. **`maxDepth = 1`:** gồm `start` **và** các tệp, thư mục con trực tiếp. Đây không giống hoàn toàn `Files.list(root)`, vì `Files.list` không tự đưa `root` vào kết quả.
3. **`maxDepth = 2`:** gồm các mục cách `root` nhiều nhất hai cấp. Thư mục `docs/archive` có trong kết quả ở cấp 2 nhưng **không đi xuống** để nhận `old.txt` ở cấp 3.
4. Nếu `start` là một tệp thường, việc duyệt không có cây con để đi xuống; khi `maxDepth` hợp lệ và tệp truy cập được, kết quả thường chỉ gồm đường dẫn tệp đó.
5. Mức sâu luôn tính **tương đối với đối số `start`**. Nếu gọi `Files.walk(root.resolve("docs"), 1)` thì `docs` trở thành cấp 0, không phải cấp 1.

Mẹo dễ nhớ: **`maxDepth` là độ sâu tối đa được *xuất hiện* trong stream**, và một thư mục ở đúng mức đó **không được duyệt tiếp vào bên trong**.

## 3. Ví dụ Java 17 chạy độc lập: duyệt có giới hạn độ sâu

Chương trình tạo cây ở mục trên trong một thư mục tạm, đếm số `Path` tại từng độ sâu và hiển thị danh sách **được sắp xếp** để kết quả không phụ thuộc thứ tự duyệt của filesystem.

Lưu nguyên mã thành **`FilesWalkDepthDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public class FilesWalkDepthDemo {
    static long countAtDepth(Path root, int maxDepth)
            throws IOException {
        try (Stream<Path> paths = Files.walk(root, maxDepth)) {
            return paths.count();
        }
    }

    static List<String> listAtDepth(Path root, int maxDepth)
            throws IOException {
        try (Stream<Path> paths = Files.walk(root, maxDepth)) {
            return paths
                    .map(root::relativize)
                    .map(path -> path.toString().isEmpty()
                            ? "."
                            : path.toString().replace('\\', '/'))
                    .sorted()
                    .toList();
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("files-walk-demo-");

        try {
            Files.createDirectories(root.resolve("docs/archive"));
            Files.createDirectory(root.resolve("images"));
            Files.writeString(root.resolve("root.txt"), "ROOT",
                    StandardCharsets.UTF_8);
            Files.writeString(root.resolve("docs/readme.txt"), "README",
                    StandardCharsets.UTF_8);
            Files.writeString(root.resolve("docs/archive/old.txt"), "OLD",
                    StandardCharsets.UTF_8);
            Files.write(root.resolve("images/logo.bin"),
                    new byte[] {1, 2, 3});

            for (int depth = 0; depth <= 3; depth++) {
                System.out.println("Depth " + depth + ": "
                        + countAtDepth(root, depth));
            }

            System.out.println("Depth 2 paths: "
                    + listAtDepth(root, 2));
            System.out.println("All paths: "
                    + countAtDepth(root, Integer.MAX_VALUE));
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                List<Path> reverse = paths
                        .sorted(Comparator.reverseOrder())
                        .toList();
                for (Path path : reverse) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 FilesWalkDepthDemo.java
java FilesWalkDepthDemo
~~~

Trong filesystem thông thường, khi chương trình có quyền tạo/xóa dữ liệu tạm, output là:

~~~text
Depth 0: 1
Depth 1: 4
Depth 2: 7
Depth 3: 8
Depth 2 paths: [., docs, docs/archive, docs/readme.txt, images, images/logo.bin, root.txt]
All paths: 8
~~~

**Vì sao output đáng tin:**

- Tổng đối tượng trong cây là **8**: một root, ba đường dẫn cấp 1, ba đường dẫn cấp 2 và một đường dẫn cấp 3.
- `Files.walk(root, 2)` trả root và mọi mục tới cấp 2; nó không cần trả `old.txt`.
- `countAtDepth` đóng stream trong `try-with-resources` ngay khi đếm xong.
- `listAtDepth` gọi `root.relativize(path)` để tạo đường dẫn tương đối, chuyển dấu phân cách của kết quả hiển thị về `/` rồi `sorted()`. Vì vậy **không phụ thuộc thứ tự liệt kê của hệ điều hành**.
- `root.relativize(root)` tạo path rỗng theo quy tắc của provider mặc định; ví dụ cố ý hiển thị nó thành ký hiệu `.`. Đây chỉ là **nhãn trình bày**.
- Khối `finally` duyệt cây một lần nữa, sắp theo thứ tự ngược và xóa các mục con trước thư mục cha. Ở đây cây nhỏ do chính chương trình tạo, nên dùng `toList()` để đơn giản hóa dọn dẹp; với cây lớn, nên dùng `Files.walkFileTree` hoặc chiến lược dọn riêng thay vì gom toàn bộ đường dẫn vào RAM.
- Các lời gọi `Files.writeString` có charset rõ ràng đối với tệp văn bản; `Files.write` dành cho ba byte nhị phân. Charset **không quyết định cách đếm độ sâu**.

Lưu ý: chương trình sử dụng đường dẫn tương đối với root do ứng dụng tạo. Nếu một tác nhân ngoài thay đổi cây tạm đồng thời hoặc provider có hành vi đặc biệt, thao tác có thể ném lỗi. Ví dụ chứng minh quy tắc API trong điều kiện bình thường, không phải một công cụ xóa thư mục bất kỳ.

## 4. Cần `try-with-resources` vì stream có tài nguyên hệ thống

Đây là lỗi hay gặp:

~~~java
// Không nên để Stream<Path> mở không có giới hạn vòng đời.
Stream<Path> paths = Files.walk(root);
paths.forEach(System.out::println);
// Quên paths.close().
~~~

Khác một số stream tính toán thuần bộ nhớ, `Files.walk` có thể giữ **directory stream / handle** khi đang duyệt. Tài liệu yêu cầu đóng stream trả về để giải phóng tài nguyên kịp thời. Mẫu dùng chuẩn là:

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.forEach(System.out::println);
}
~~~

Đây là hai đoạn **minh họa**, `root` là `Path` đã khai báo, cần import `java.nio.file.*` và `java.util.stream.Stream`, đồng thời xử lý `IOException`.

Đừng hiểu rằng gọi `count()`, `forEach()` hoặc `toList()` sẽ tự động gọi `close()`. Các thao tác terminal **không thay thế việc đóng stream**. `try-with-resources` đảm bảo đóng cả khi thân khối xử lý gặp lỗi.

### Vì sao không giữ stream cho nhiều truy vấn?

Một `Stream` trong Java thường chỉ được tiêu thụ **một lần**:

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    long count = paths.count();
    // Không dùng lại chính paths để gọi paths.forEach(...).
}
~~~

Nếu cần đếm và liệt kê riêng, hãy mở **hai lượt duyệt** (như ví dụ Java ở trên), hoặc thu kết quả một lần vào `List` khi số lượng mục đủ nhỏ và chấp nhận dùng bộ nhớ để lưu. Việc duyệt hai lượt có thể quan sát **hai trạng thái filesystem khác nhau** nếu file thay đổi giữa hai lần.

## 5. `maxDepth` giới hạn thăm dò; `filter` chỉ lọc phần đã duyệt

So sánh hai cách:

~~~java
// Giới hạn phần cây mà traversal đi xuống.
try (Stream<Path> paths = Files.walk(root, 2)) {
    long count = paths.count();
}
~~~

và:

~~~java
// Vẫn duyệt toàn bộ cây; filter chỉ chọn phần tử ở mức <= 2.
try (Stream<Path> paths = Files.walk(root)) {
    long count = paths
            .filter(p -> root.relativize(p).getNameCount() <= 2)
            .count();
}
~~~

Đây là **đoạn minh họa**. Biểu thức lọc theo `getNameCount()` còn cần cân nhắc trường hợp `root` tương đối với chính nó và quy tắc provider; không dùng nó như bản sao tổng quát của `maxDepth`.

**Điểm quan trọng:** cách thứ hai vẫn có thể **đi vào các thư mục sâu hơn** trước khi filter loại kết quả, do đó có thể đọc rất nhiều metadata, gặp lỗi ở nhánh mà bạn thực sự không muốn duyệt, hoặc tốn thời gian đáng kể. Nếu nghiệp vụ chỉ cần hai cấp, hãy dùng **`Files.walk(root, 2)` ngay tại nguồn**.

Dùng `filter` để chọn **loại mục** sau khi giới hạn độ sâu, ví dụ chỉ lấy tệp thường:

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

`Files.isRegularFile(path)` kiểm tra metadata filesystem và theo symbolic link theo hợp đồng mặc định của phương thức đó. Nếu bạn cần không theo link trong bước kiểm tra loại tệp, hãy dùng:

~~~java
paths.filter(p -> Files.isRegularFile(
        p, LinkOption.NOFOLLOW_LINKS))
~~~

Dòng sau là **biểu thức minh họa bên trong pipeline**, cần `LinkOption` tương ứng. Không áp dụng `filter` thứ hai trên chính stream đã tiêu thụ bởi `forEach` ở ví dụ trước; phải tạo stream mới.

**Chọn đúng nhiệm vụ:** `maxDepth` giới hạn **đi sâu**, còn `filter` giới hạn **các kết quả được giữ lại**.

## 6. Độ sâu tối đa **không** đồng nghĩa số lượng tệp tối đa

Một thư mục gốc có thể có hàng triệu file con trực tiếp. `Files.walk(root, 1)` vẫn có thể phải liệt kê tất cả chúng: giới hạn độ sâu **không tự giới hạn số mục** hoặc số byte đọc từ metadata.

Do đó, khi tối ưu hóa:

- Xác định `maxDepth` phù hợp để tránh những nhánh không cần duyệt.
- Nếu chỉ cần một số kết quả, có thể dùng thao tác ngắn mạch như `findFirst()` hoặc `limit(n)`, nhưng không nên mặc định mọi filesystem ngừng mọi I/O đúng tại cùng một thời điểm.
- Tránh `toList()` hoặc `collect(toList())` trên cây có số mục quá lớn nếu không cần toàn bộ kết quả trong RAM.
- Chọn `forEach` hoặc xử lý tuần tự từng mục nếu đầu ra có thể xử lý theo dòng.
- Với yêu cầu kiểm soát nhánh, hủy duyệt hoặc quyết định `SKIP_SUBTREE`, cân nhắc `Files.walkFileTree` và `FileVisitor` thay vì ép mọi trường hợp vào một stream filter.

`Files.walk` phù hợp cho nhu cầu duyệt và pipeline tương đối đơn giản; đó không phải sự bảo đảm rằng mọi thao tác trên một cây lớn sẽ nhanh hoặc nhẹ chỉ nhờ đặt `maxDepth`.

## 7. Symbolic link và tùy chọn `FOLLOW_LINKS`

Mặc định, `Files.walk` **không theo symbolic link**. Giả sử có một symlink `root/linked-docs` trỏ tới một thư mục khác:

~~~text
root/
├── linked-docs -> /elsewhere/docs
└── local.txt
~~~

Với lời gọi:

~~~java
Files.walk(root, 2);
~~~

symlink có thể xuất hiện như một `Path` được liệt kê, nhưng traversal **không tự đi theo nó để duyệt toàn bộ nội dung thư mục đích**.

Để yêu cầu theo symbolic link, truyền `FileVisitOption.FOLLOW_LINKS`:

~~~java
try (Stream<Path> paths = Files.walk(
        root, 2, FileVisitOption.FOLLOW_LINKS)) {
    paths.forEach(System.out::println);
}
~~~

**Độ sâu vẫn tính theo tuyến duyệt bắt đầu tại `root`**, bao gồm đường đi qua liên kết nếu được theo. Không được giả định độ sâu bằng số thành phần trong real path của tệp đích symlink; đường đi logic qua liên kết và đường dẫn thực có thể khác nhau.

Khi theo symlink, một cây có thể chứa **vòng liên kết** như A → B → A. `Files.walk` phát hiện vòng trong quá trình duyệt theo hợp đồng và có thể báo `FileSystemLoopException` (thuộc `IOException`; trong giai đoạn tiêu thụ stream, có thể xuất hiện dưới dạng `UncheckedIOException`). Một hệ thống từ xa hoặc cây thay đổi liên tục cũng có thể sinh lỗi I/O.

**Điểm phân biệt:** `Files.walk(root, 2)` giới hạn tối đa số cấp được duyệt, nhưng không phải cơ chế bảo mật để ngăn symlink trỏ ra ngoài thư mục gốc. Nếu phải xử lý nội dung không tin cậy, xác định chính sách liên kết và quyền truy cập riêng.

### Ví dụ khi maxDepth = 0 hoặc 1 có FOLLOW_LINKS

`FOLLOW_LINKS` không có nghĩa API luôn duyệt thư mục mà symlink trỏ đến bất chấp giới hạn. Với `maxDepth = 0`, chỉ `start` thuộc phạm vi kết quả. Với `maxDepth = 1`, chỉ các mục con trực tiếp xuất hiện; API không đi sâu hơn vào bên trong một mục liên kết ở cấp 1.

Tóm lại, **`FOLLOW_LINKS` thay quy tắc có được đi theo liên kết hay không**, còn **`maxDepth` vẫn quyết định sâu nhất tới đâu**.

## 8. IOException khi mở stream và UncheckedIOException khi duyệt

Đây là chi tiết quan trọng trong API stream:

~~~java
try (Stream<Path> paths = Files.walk(root, 3)) {
    paths.forEach(path -> System.out.println(path));
}
~~~

`Files.walk(...)` khai báo `throws IOException`. Lỗi có thể xảy ra khi gọi phương thức, ví dụ không đọc được thuộc tính của điểm bắt đầu hoặc đối tượng đầu vào không tồn tại theo provider.

Nhưng việc duyệt là **lazy**. Sau khi đã nhận `Stream<Path>`, lỗi xuất hiện trong lúc xử lý directory tiếp theo có thể được đưa ra dưới dạng **`UncheckedIOException`** vì pipeline `Stream` không khai báo checked exception trên `forEach`, `count`, v.v.

Mẫu phân biệt lỗi:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class WalkErrors {
    static void printTree(Path root, int maxDepth)
            throws IOException {
        try (Stream<Path> paths = Files.walk(root, maxDepth)) {
            paths.forEach(System.out::println);
        } catch (UncheckedIOException ex) {
            throw ex.getCause(); // Đưa lại IOException gốc cho caller.
        }
    }
}
~~~

Đây là **lớp tiện ích Java 17 biên dịch được**, nhưng không có `main`. Nó minh họa cách chuyển lỗi unchecked trong lúc duyệt về checked `IOException` để caller dùng cùng một chính sách xử lý. Trong hệ thống thực, bạn có thể chọn báo lỗi, retry có giới hạn hoặc ghi lại nhánh lỗi theo chính sách; đừng âm thầm nuốt ngoại lệ rồi tuyên bố đã duyệt đủ cây.

Không nên mặc định mọi lỗi trong một pipeline đều do filesystem: code bên trong `map`, `filter` hoặc `forEach` cũng có thể ném runtime exception riêng. Việc xử lý lỗi cần giữ lại nguyên nhân để chẩn đoán đúng.

## 9. Kết hợp maxDepth với một vài tác vụ thường gặp

### Liệt kê tệp thường đến hai cấp

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.filter(Files::isRegularFile)
         .forEach(System.out::println);
}
~~~

Phương thức `Files::isRegularFile` có thể truy cập metadata và mặc định theo link khi kiểm tra loại tệp; nếu cần cùng một chính sách no-follow xuyên suốt, truyền `NOFOLLOW_LINKS` cho phép kiểm tra tương ứng.

### Liệt kê thư mục (gồm cả gốc) đến ba cấp

~~~java
try (Stream<Path> paths = Files.walk(root, 3)) {
    paths.filter(Files::isDirectory)
         .forEach(System.out::println);
}
~~~

Nếu muốn **loại root** khỏi output:

~~~java
try (Stream<Path> paths = Files.walk(root, 3)) {
    paths.filter(Files::isDirectory)
         .filter(path -> !path.equals(root))
         .forEach(System.out::println);
}
~~~

Dù loại root khỏi kết quả sau `filter`, nó vẫn là **điểm bắt đầu** và được traversal xét đến ở cấp 0.

### Đếm tệp đến một cấp giới hạn

~~~java
long files;
try (Stream<Path> paths = Files.walk(root, 2)) {
    files = paths.filter(Files::isRegularFile).count();
}
~~~

Lưu ý `count()` trên stream đường dẫn không tương đương số byte tệp, số dòng, hoặc kích thước lưu trữ; đó chỉ là **số phần tử `Path` thỏa điều kiện**.

### Lấy đường dẫn tương đối để in báo cáo

~~~java
try (Stream<Path> paths = Files.walk(root, 2)) {
    paths.map(root::relativize)
         .map(Path::toString)
         .sorted()
         .forEach(System.out::println);
}
~~~

Khi root và các phần tử thuộc cùng filesystem/provider, `relativize` phù hợp để tạo nhãn tương đối. Nếu mục đích là xuất ra file báo cáo có thứ tự ổn định, `sorted()` hữu ích nhưng có thể cần **giữ nhiều phần tử trong bộ nhớ** để sắp xếp.

## 10. `Files.walk`, `Files.list`, `Files.find` và `Files.walkFileTree`

| API | Phạm vi | Điểm cần nhớ |
|---|---|---|
| `Files.list(dir)` | Liệt kê **một cấp con trực tiếp**; không bao gồm chính `dir` | Trả `Stream<Path>` cũng phải được đóng |
| `Files.walk(start)` | Duyệt từ `start` xuống các cấp bên dưới | Bao gồm `start`; không đặt giới hạn sâu hữu hạn |
| `Files.walk(start, maxDepth)` | Duyệt và dừng ở mức sâu cho phép | Bao gồm `start`, cấp 0 |
| `Files.find(start, maxDepth, matcher, options...)` | Tìm các mục phù hợp predicate dựa trên `Path` và `BasicFileAttributes` | Có thể tránh đọc attributes hai lần so với một số cách `walk().filter(...)`; cũng trả stream cần đóng |
| `Files.walkFileTree(start, visitor)` | Duyệt với `FileVisitor`, điều khiển tại từng thư mục/mục | Hợp khi cần `SKIP_SUBTREE`, xử lý lỗi theo từng node, cleanup/copy cây |

`Files.walkFileTree` còn có overload nhận `maxDepth` và `FileVisitOption`. Khi cần chính sách dừng nhánh tùy biến, nó thường rõ hơn một pipeline `Files.walk`. Nhưng nếu chỉ cần “liệt kê các tệp đến hai cấp rồi lọc”, `Files.walk(root, 2)` là một cách ngắn gọn, có sẵn trong Java NIO.2.

## 11. Những lỗi thường gặp

| Hiểu sai | Hậu quả | Cách làm đúng |
|---|---|---|
| Nghĩ `maxDepth = 0` là không có kết quả | Bỏ sót chính `start` | Nhớ root ở **depth 0** |
| Nghĩ `maxDepth = 1` chỉ trả các con của root | Đếm thừa/thiếu vì có root | Muốn loại root thì filter riêng |
| Gọi `Files.walk(root)` rồi mới filter theo depth | Vẫn đi vào nhánh sâu không cần thiết | Dùng overload `Files.walk(root, maxDepth)` |
| Cho rằng `maxDepth` giới hạn số mục được trả | Thư mục một cấp vẫn có thể chứa rất nhiều file | Giới hạn số kết quả/thiết kế xử lý riêng |
| Quên đóng `Stream<Path>` | Có thể giữ handle thư mục hoặc tài nguyên I/O | Dùng `try-with-resources` |
| Dùng cùng một stream cho hai terminal operation | `IllegalStateException` hoặc hành vi stream đã tiêu thụ | Mở lượt duyệt mới hoặc lưu danh sách có kiểm soát |
| Giả định thứ tự tệp trong mỗi thư mục ổn định | Kết quả khác nhau theo filesystem | `sorted()` nếu thứ tự là yêu cầu |
| Cho rằng luôn theo symbolic link | Mặc định không theo liên kết | Truyền `FOLLOW_LINKS` khi chủ đích |
| Theo symlink mà không kiểm soát vòng lặp | Có thể gặp `FileSystemLoopException` | Xử lý lỗi và đặt giới hạn phù hợp |
| Chỉ bắt `IOException` ngoài `Files.walk` mà quên lỗi lazy | Bỏ sót `UncheckedIOException` khi tiêu thụ stream | Phân biệt giai đoạn mở và duyệt |
| Gọi `toList()` trên toàn bộ cây khổng lồ | Dùng nhiều RAM | Xử lý dạng stream hoặc walkFileTree |
| Nhầm đường dẫn con ở maxDepth với tên file có số dấu `/` nhất định | Sai phạm vi khi root có nhiều thành phần | Đếm độ sâu tương đối với `start` |

## 12. Tự kiểm tra

**Câu 1.** Với cây có `root/a/file.txt`, gọi `Files.walk(root, 1)` có thấy `file.txt` không?

> **Không.** `root` là cấp 0, `a` cấp 1, `file.txt` cấp 2. `maxDepth = 1` không đi tới cấp 2.

**Câu 2.** Muốn đếm tệp con trực tiếp mà không đếm root, dùng `Files.list(root)` hay `Files.walk(root, 1)`?

> Cả hai có thể hỗ trợ nếu lọc đúng, nhưng `Files.list(root)` phù hợp trực tiếp hơn vì nó chỉ liệt kê con của thư mục, **không gồm root**. `Files.walk(root, 1)` gồm cả root và các con; có thể filter loại root.

**Câu 3.** Vì sao `Files.walk(root).filter(p -> depth(p) <= 2)` có thể kém hơn `Files.walk(root, 2)`?

> Cách đầu vẫn có thể duyệt các nhánh rất sâu rồi mới bỏ phần tử bằng filter. `maxDepth` giới hạn **việc đi xuống cây** ngay từ API, không chỉ loại kết quả.

**Câu 4.** Thư mục cấp 2 có rất nhiều file bên trong. `Files.walk(root, 2)` có đi vào thư mục ấy để đọc các file cấp 3 không?

> **Không.** Thư mục ở độ sâu tối đa được trả về như một mục, nhưng traversal không đi sâu hơn mức cho phép.

**Câu 5.** Có cần đóng stream của `Files.walk` sau khi `count()` đã chạy xong không?

> **Có.** Terminal operation không tự thay thế `close()`; dùng `try-with-resources` để giải phóng tài nguyên thư mục.

**Câu 6.** Nếu dùng `FOLLOW_LINKS` mà gặp vòng symlink, có thể gặp ngoại lệ gì?

> **`FileSystemLoopException`**, có thể được bọc trong `UncheckedIOException` khi lỗi phát sinh lúc tiêu thụ stream. Caller cần xử lý theo chính sách lỗi I/O.

**Câu 7.** `Files.walk(root, 2)` có đảm bảo chỉ sinh tối đa hai kết quả không?

> **Không.** Số 2 là **độ sâu**, không phải số tệp/thư mục. Số phần tử phụ thuộc độ rộng của cây ở các cấp được phép.

## Ghi nhớ

- `Files.walk(start, maxDepth)` duyệt từ **`start` là cấp 0** đến mức sâu tối đa.
- `0` lấy root, `1` lấy root + con trực tiếp, `2` thêm cháu; mọi đường dẫn đều được tính tương đối với `start`.
- Khác với `filter` sau khi duyệt, `maxDepth` giúp **không đi sâu hơn** ngưỡng.
- `Files.walk` trả **`Stream<Path>` có tài nguyên I/O**, phải đóng bằng `try-with-resources`.
- Mặc định **không theo symbolic link**; `FOLLOW_LINKS` thay đổi điều đó nhưng có nguy cơ vòng liên kết và lỗi I/O.
- Kết quả có thể phụ thuộc filesystem về thứ tự và trạng thái; **sort khi cần**, xử lý `IOException` / `UncheckedIOException` và đừng nhầm giới hạn độ sâu với giới hạn số lượng.

**Tài liệu tham khảo:** [Java SE 17 — `Files.walk`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [`FileVisitOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html), [`Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).