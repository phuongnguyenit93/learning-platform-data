# Vòng liên kết và giới hạn khi duyệt cây tệp trong Java NIO

Khi duyệt một cây thư mục, mỗi thư mục có vẻ như dẫn tới các thư mục con. Tuy nhiên, **symbolic link** (liên kết tượng trưng, gọi tắt là symlink) có thể trỏ tới một thư mục đã đi qua, tới tổ tiên của nó hoặc tới một nhánh bên ngoài thư mục bắt đầu. Nếu chương trình đi theo các liên kết mà không kiểm soát, nó có thể duyệt lặp, xử lý trùng dữ liệu, đi ra ngoài phạm vi mong muốn hoặc tốn quá nhiều tài nguyên.

Java NIO.2 cung cấp hai cơ chế quan trọng: **chọn có đi theo symbolic link hay không** và **giới hạn độ sâu duyệt**. Với API `Files.walkFileTree`, Java còn phát hiện một số vòng liên kết để báo cho `FileVisitor` xử lý.

## 1. Hiểu liên kết và vòng liên kết

Một symbolic link là một mục trong hệ thống tệp chứa tham chiếu tới đường dẫn đích. Nó có thể trỏ tới tệp, thư mục, đích chưa tồn tại hoặc đường dẫn bên ngoài cây đang duyệt. Ví dụ:

```text
project/
├── docs/
│   ├── guide.txt
│   └── back -> ../        # symlink trỏ về project/
└── output/
```

Nếu đi theo `docs/back`, từ `project/docs` ta trở lại `project`, rồi lại có thể đi vào `docs/back`. Đây là **vòng liên kết (link cycle)**.

Cần phân biệt ba tình huống:

- **Vòng liên kết:** Đường đi đang duyệt dẫn lại tới một thư mục *tổ tiên trên chính nhánh duyệt hiện tại*. Ví dụ `docs/back -> ../`. Khi bật theo symlink, `walkFileTree` phát hiện vòng này và chuyển lỗi `FileSystemLoopException` cho `visitFileFailed`.
- **Duyệt trùng nhưng không tạo vòng trên nhánh hiện tại:** Hai symlink khác nhau cùng trỏ tới một thư mục. Cơ chế phát hiện vòng của `walkFileTree` không hứa loại bỏ mọi lần thăm trùng; một thư mục vẫn có thể được xử lý nhiều lần qua các nhánh khác nhau.
- **Liên kết vượt ra ngoài cây bắt đầu:** Ví dụ `project/external -> /other/data`. Đây không nhất thiết là vòng, nhưng có thể vượt ranh giới nghiệp vụ hoặc bảo mật nếu bật theo symlink.

**Hard link** là tên đường dẫn khác cùng tham chiếu tới một đối tượng tệp; nó khác symlink. Trên các hệ thống tệp thông dụng, hard link tới thư mục thường bị cấm, nên bài toán vòng khi duyệt thư mục chủ yếu liên quan tới symbolic link, mount point và những cách hệ thống tệp biểu diễn lại một vị trí. Không nên coi việc tránh symlink là cơ chế loại trừ mọi tệp trùng nhau.

## 2. Hành vi mặc định của Java NIO

`Files.walkFileTree(start, visitor)` duyệt từ `start` với hành vi mặc định **không theo symbolic link** và độ sâu tối đa về mặt API là `Integer.MAX_VALUE`. `Files.walk(start)` cũng không theo symlink nếu không truyền `FileVisitOption.FOLLOW_LINKS`.

| Cấu hình | Gặp symlink tới thư mục | Hệ quả |
| --- | --- | --- |
| Không có `FOLLOW_LINKS` (mặc định) | Xem symlink như một mục tệp được thăm qua `visitFile`, không đi sâu vào đích | Tránh vòng gây ra bởi việc đi theo symlink đó |
| Có `FOLLOW_LINKS` | Cố đọc thuộc tính và duyệt thư mục đích | Có thể duyệt trùng, ra khỏi gốc; vòng trên nhánh hiện tại được báo bằng `FileSystemLoopException` |
| Có hoặc không theo link, kèm `maxDepth` | Chỉ xuống tới độ sâu đã định | Giới hạn mức lồng nhau, không giới hạn số mục ở mỗi mức |

Ví dụ hai cách gọi tương ứng:

```java
// Không theo symbolic link, giới hạn đến độ sâu 3.
Files.walkFileTree(root, EnumSet.noneOf(FileVisitOption.class), 3, visitor);

// Theo symbolic link, cũng chỉ xuống đến độ sâu 3.
Files.walkFileTree(root, EnumSet.of(FileVisitOption.FOLLOW_LINKS), 3, visitor);
```

Đây là những **đoạn lệnh minh họa**, cần đặt trong chương trình có `root` kiểu `Path`, `visitor` kiểu `FileVisitor<Path>` và phần import thích hợp. Chương trình đầy đủ nằm ở phần 5.

Lưu ý: `Files.isSymbolicLink(path)` kiểm tra chính mục liên kết. Trong khi đó, `attrs.isSymbolicLink()` phản ánh bộ thuộc tính mà thao tác duyệt đã đọc; khi bật `FOLLOW_LINKS`, bộ thuộc tính có thể thuộc **đối tượng đích**, vì vậy hai kiểm tra không phải lúc nào cũng cho cùng kết quả.

## 3. Giới hạn độ sâu `maxDepth` hoạt động thế nào?

Độ sâu được tính từ đường dẫn `start`:

- **Độ sâu 0:** Chính `start`.
- **Độ sâu 1:** Các mục con trực tiếp.
- **Độ sâu 2:** Các mục cháu; tiếp tục tương tự.

Với cây `project/docs/chapters/intro.md`, nếu `project` là gốc thì `docs` ở độ sâu 1, `chapters` ở độ sâu 2, `intro.md` ở độ sâu 3. Khi `maxDepth = 2`, Java không duyệt tới `intro.md`.

Chi tiết dễ nhầm của `walkFileTree`: **một thư mục nằm đúng mức `maxDepth` được đưa tới `visitFile`, chứ không gọi `preVisitDirectory` rồi mở các mục con của nó**. Tương tự, `maxDepth = 0` đưa chính gốc tới `visitFile`, kể cả khi gốc là thư mục. Vì vậy mã trong `visitFile` không nên giả định mọi đường dẫn nhận được đều là tệp thông thường.

Tham số `maxDepth` phải không âm. Giá trị nhỏ giúp tránh đi quá sâu, nhưng không chặn một thư mục ở độ sâu 1 chứa hàng triệu mục. Nó cũng **không phải** hạn mức thời gian, tổng số tệp, dung lượng đọc hay công cụ ngăn theo symlink đi ra ngoài gốc.

## 4. Đường đi vòng được báo và xử lý ra sao?

Khi có `FOLLOW_LINKS`, `walkFileTree` kiểm tra một thư mục trước khi đi sâu để nhận diện việc nó trùng với một tổ tiên trên nhánh hiện tại. Java có thể dùng `fileKey` từ thuộc tính tệp hoặc so sánh tính đồng nhất của tệp khi cần. Nếu phát hiện vòng, API **không tiếp tục đệ quy vô hạn qua liên kết đó**; nó gọi:

```java
visitFileFailed(Path file, IOException exc)
```

với `exc` thuộc loại `FileSystemLoopException`. Đây là nơi chương trình quyết định ghi log và tiếp tục, hay dừng.

Một số kết quả của `FileVisitResult`:

| Kết quả | Ý nghĩa trong `FileVisitor` |
| --- | --- |
| `CONTINUE` | Tiếp tục duyệt theo quy tắc hiện hành |
| `SKIP_SUBTREE` | Khi trả từ `preVisitDirectory`, bỏ qua các mục con của thư mục đó |
| `SKIP_SIBLINGS` | Bỏ qua các mục anh em còn lại tại mức liên quan |
| `TERMINATE` | Kết thúc toàn bộ cuộc duyệt |

Chỉ nên chủ động bỏ qua lỗi `FileSystemLoopException` nếu chính sách ứng dụng cho phép. Không nên viết `visitFileFailed(...){ return CONTINUE; }` cho **mọi** `IOException`: lỗi phân quyền, I/O hoặc thư mục biến mất cần được báo cáo hay xử lý có chủ đích, nếu không dữ liệu kết quả có thể thiếu mà người dùng không biết.

Với symbolic link hỏng (đích không tồn tại) hoặc đích không thể truy cập, hành vi cần xử lý cẩn thận: khi đang bật theo link mà không đọc được thuộc tính của đích, API có thể thử lấy thuộc tính của **chính link** và gọi `visitFile`; không nên giả định mọi link hỏng đều đi vào `visitFileFailed`. Nếu cần phân biệt rõ, kiểm tra `Files.isSymbolicLink(path)` và chính sách tồn tại/truy cập đích tại thời điểm xử lý.

## 5. Chương trình Java 17+ có thể biên dịch và chạy

Chương trình dưới đây cho người chạy chọn giới hạn độ sâu và bật/tắt theo symbolic link. Nó in nhãn `DIR`, `DIR_LIMIT`, `FILE`, `LINK` và `LOOP` để dễ quan sát hành vi. `FileSystemLoopException` được ghi nhận rồi bỏ qua đường vòng; các lỗi I/O khác được ném lại để người chạy biết cuộc duyệt không đầy đủ.

Tạo tệp **`TreeLinkWalk.java`**:

```java
import java.io.IOException;
import java.nio.file.FileSystemLoopException;
import java.nio.file.FileVisitOption;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.EnumSet;

public final class TreeLinkWalk {
    private TreeLinkWalk() {}

    public static void main(String[] args) throws IOException {
        if (args.length < 1 || args.length > 3) {
            System.out.println("Usage: java TreeLinkWalk <root> [maxDepth] [followLinks]");
            return;
        }

        Path root = Path.of(args[0]).toAbsolutePath().normalize();
        int maxDepth = args.length >= 2 ? Integer.parseInt(args[1]) : 3;
        if (maxDepth < 0) {
            throw new IllegalArgumentException("maxDepth must be >= 0");
        }
        if (args.length == 3
                && !args[2].equalsIgnoreCase("true")
                && !args[2].equalsIgnoreCase("false")) {
            throw new IllegalArgumentException("followLinks must be true or false");
        }

        boolean followLinks = args.length == 3 && Boolean.parseBoolean(args[2]);
        EnumSet<FileVisitOption> options = followLinks
                ? EnumSet.of(FileVisitOption.FOLLOW_LINKS)
                : EnumSet.noneOf(FileVisitOption.class);

        Files.walkFileTree(root, options, maxDepth,
                new SimpleFileVisitor<Path>() {
                    @Override
                    public FileVisitResult preVisitDirectory(
                            Path dir, BasicFileAttributes attrs) {
                        System.out.println("DIR       " + relative(root, dir));
                        return FileVisitResult.CONTINUE;
                    }

                    @Override
                    public FileVisitResult visitFile(
                            Path file, BasicFileAttributes attrs) {
                        String kind = Files.isSymbolicLink(file) ? "LINK"
                                : attrs.isDirectory() ? "DIR_LIMIT" : "FILE";
                        System.out.printf("%-9s %s%n", kind, relative(root, file));
                        return FileVisitResult.CONTINUE;
                    }

                    @Override
                    public FileVisitResult visitFileFailed(
                            Path file, IOException exc) throws IOException {
                        if (exc instanceof FileSystemLoopException) {
                            System.out.println("LOOP      " + relative(root, file));
                            return FileVisitResult.CONTINUE;
                        }
                        throw exc;
                    }
                });
    }

    private static String relative(Path root, Path item) {
        String name = root.relativize(item).toString();
        return name.isEmpty() ? "." : name;
    }
}
```

Biên dịch rồi chạy, thay `project` bằng thư mục thực tế:

```bash
javac TreeLinkWalk.java
java TreeLinkWalk project 3 false
java TreeLinkWalk project 3 true
java TreeLinkWalk project 1 false
```

Trên Windows, có thể dùng đường dẫn đầy đủ đặt trong dấu nháy, chẳng hạn `java TreeLinkWalk "C:\data\project" 3 false`. Mã dùng API thuộc Java 17+ và không tự tạo, xóa hoặc ghi các tệp đang duyệt.

Với cây ở phần 1, nếu hệ thống hỗ trợ symlink và liên kết `back` tồn tại, kết quả **minh họa** khi giới hạn đủ sâu có thể chứa:

```text
# followLinks=false:
DIR       .
DIR       docs
FILE      docs/guide.txt
LINK      docs/back
DIR       output

# followLinks=true:
DIR       .
DIR       docs
FILE      docs/guide.txt
LOOP      docs/back
DIR       output
```

Đây là ví dụ về các dòng sẽ thấy, **không đảm bảo thứ tự**: hệ thống tệp không bắt buộc trả các mục con theo thứ tự hiển thị; dấu phân cách đường dẫn cũng khác nhau giữa Windows và Unix. Nếu thư mục nằm tại biên `maxDepth`, chương trình có thể in `DIR_LIMIT` thay cho `DIR`. Nếu không tạo được symlink vì quyền hệ thống hay hệ thống tệp không hỗ trợ, đừng giả định sẽ có dòng `LINK` hoặc `LOOP`.

Trong ví dụ, `visitFile` dùng `Files.isSymbolicLink(file)` để nhận diện *đường dẫn* là một link kể cả khi đang theo link; việc Java có gọi `preVisitDirectory`, `visitFile` hay `visitFileFailed` vẫn phụ thuộc loại đích, độ sâu và lỗi phát sinh.

## 6. Giữ cuộc duyệt trong vùng được phép

Giới hạn độ sâu **không bảo đảm** cuộc duyệt nằm bên trong thư mục gốc. Một symlink ở độ sâu 1 có thể dẫn ngay tới thư mục ngoài phạm vi. Khi ứng dụng chỉ cần quản lý tệp vật lý dưới gốc, lựa chọn đơn giản và an toàn hơn là **không bật `FOLLOW_LINKS`**.

Nếu nghiệp vụ buộc phải theo symlink nhưng không muốn xử lý mục nằm ngoài gốc, có thể kiểm tra đường dẫn thực trước khi xử lý:

```java
Path allowedRoot = root.toRealPath(); // Tính một lần trước khi walk.
Path realDirectory = dir.toRealPath();
if (!realDirectory.startsWith(allowedRoot)) {
    return FileVisitResult.SKIP_SUBTREE; // Trong preVisitDirectory.
}
```

Đây là **đoạn minh họa đặt trong `preVisitDirectory`**, với `root` và `dir` đã được khai báo. Với tệp thường trong `visitFile`, cần kiểm tra tương tự trước khi đọc nội dung; chỉ chặn thư mục sẽ bỏ sót symlink trỏ tới **tệp** ngoài gốc. `Path.startsWith(Path)` so sánh theo thành phần đường dẫn, không thay bằng `path.toString().startsWith(prefix)` vì tiền tố chuỗi như `/data/root-else` có thể bị nhận nhầm thành `/data/root`.

Kiểm tra `toRealPath()` có thể ném `IOException` nếu đích biến mất, bị từ chối truy cập hoặc không còn giải quyết được; cần xử lý theo chính sách lỗi. Hơn nữa, giữa lúc kiểm tra và lúc mở tệp, liên kết có thể bị thay đổi (**TOCTOU**). Do đó kiểu kiểm tra trên phù hợp làm hàng rào logic cho một cây tương đối ổn định, **không phải sandbox bảo mật tuyệt đối** trước tác nhân có khả năng sửa hệ thống tệp đồng thời. Với dữ liệu không tin cậy, ưu tiên không theo link, hạn chế quyền truy cập hệ điều hành và thiết kế cách mở tệp chống thay đổi đường dẫn phù hợp nền tảng.

## 7. Tránh nhầm giữa API duyệt và giới hạn tài nguyên

`Files.walk` trả về `Stream<Path>` và cần đóng:

```java
try (var paths = Files.walk(root, 2)) {
    paths.forEach(System.out::println);
}
```

Đây là đoạn minh họa trong phương thức có xử lý `IOException`. Theo mặc định stream không theo symlink. Khi dùng biến thể có `FOLLOW_LINKS`, lỗi I/O lúc lấy phần tử trong stream (kể cả vòng liên kết) có thể được bọc trong `UncheckedIOException`; mô hình callback `FileVisitor.visitFileFailed` chỉ thuộc `walkFileTree`. Dùng `walkFileTree` khi cần chính sách riêng cho từng thư mục và từng lỗi.

Một chương trình duyệt cây trong thực tế có thể cần thêm các giới hạn **độc lập**:

- **Số mục đã thăm:** Tăng bộ đếm; trả `TERMINATE` khi vượt ngưỡng.
- **Thời gian chạy:** So sánh thời điểm bắt đầu với deadline, kiểm tra trong callback; `maxDepth` không giới hạn thời gian.
- **Tổng dung lượng hoặc số byte đọc:** Kiểm tra trước và trong quá trình xử lý nội dung; việc duyệt đường dẫn chưa đồng nghĩa với đọc nội dung tệp.
- **Xử lý trùng:** Nếu không được xử lý cùng tệp/thư mục nhiều lần, quản lý tập đối tượng đã thấy theo danh tính tệp (`fileKey` khi đáng tin, hoặc phép so sánh `Files.isSameFile` khi thích hợp). Không dùng mỗi chuỗi đường dẫn làm định danh vật lý; hai đường dẫn khác nhau có thể tới cùng một đối tượng. `fileKey` cũng có thể `null`, và chi phí của các phép so sánh cần được cân nhắc.

Nếu muốn đếm hoặc giới hạn số mục bằng callback, nhớ rằng một mục ở biên độ sâu có thể được báo trong `visitFile`, ngay cả khi nó là thư mục.

## 8. Lỗi thường gặp và cách kiểm tra

| Lỗi thường gặp | Vì sao sai / cách khắc phục |
| --- | --- |
| Bật `FOLLOW_LINKS` nhưng nghĩ rằng mọi thư mục chỉ thăm một lần | Java phát hiện vòng với tổ tiên của nhánh hiện tại; các liên kết khác vẫn có thể khiến duyệt trùng. Cần chính sách chống trùng riêng nếu nghiệp vụ yêu cầu. |
| Nghĩ `maxDepth = 2` cho phép đi qua hai thư mục *con* rồi đọc mọi tệp trong đó | Gốc đã là độ sâu 0; mục ở độ sâu 2 là biên và không được mở thêm. |
| Trong `visitFile` luôn coi `attrs` là tệp thông thường | Ở mức độ sâu tối đa, callback có thể nhận đường dẫn thư mục; khi không theo link có thể nhận symlink. |
| Bỏ qua mọi `IOException` bằng `CONTINUE` | Cuộc duyệt có thể thiếu dữ liệu do từ chối truy cập hoặc I/O lỗi. Chỉ bỏ qua lỗi đã chấp nhận và ghi nhận đầy đủ. |
| Dùng `maxDepth` để ngăn đi ra ngoài gốc | Một liên kết nông có thể trỏ ra ngoài. Không theo link hoặc áp dụng chính sách đường dẫn thực và quyền truy cập. |
| Dùng `Files.walk` mà không đóng stream | Stream giữ tài nguyên của hệ thống tệp. Dùng `try-with-resources`. |

Có thể tự kiểm chứng trên một thư mục thử nghiệm riêng:

1. Tạo một cây ít nhất ba mức, rồi chạy `maxDepth` lần lượt bằng 0, 1, 2 và 3 để quan sát `DIR_LIMIT`.
2. Nếu hệ thống cho phép, tạo symlink từ thư mục con về thư mục tổ tiên; so sánh `followLinks=false` và `true`.
3. Thử một symlink trỏ tới thư mục bên ngoài gốc và một symlink có đích không tồn tại; quan sát sự khác nhau giữa vòng, vượt gốc và link hỏng.
4. Thử thư mục không có quyền truy cập nếu điều kiện môi trường cho phép; xác nhận lỗi không bị âm thầm bỏ qua.

**Quy tắc chọn mặc định:** Đối với bài toán tìm kiếm, thống kê hay xử lý tệp thông thường, hãy bắt đầu bằng **không theo symbolic link**, đặt một `maxDepth` phù hợp và xử lý tường minh lỗi I/O. Chỉ bật `FOLLOW_LINKS` khi thực sự cần duyệt cả đối tượng đích, đồng thời xác định cách xử lý vòng, duyệt trùng và giới hạn phạm vi.