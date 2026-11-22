# TOCTOU: khoảng trống giữa kiểm tra và thao tác trong Java I/O

## 1. TOCTOU là gì và vì sao nguy hiểm?

**TOCTOU** viết tắt của **Time-of-Check to Time-of-Use**: ứng dụng kiểm tra một điều kiện ở thời điểm **T1**, nhưng chỉ thực hiện hành động dựa trên điều kiện đó tại **T2**. Trong khoảng T1 → T2, trạng thái được kiểm tra có thể đã thay đổi. Nếu ứng dụng mặc nhiên tin rằng kết quả kiểm tra vẫn còn đúng, nó có thể làm sai nghiệp vụ hoặc tạo lỗ hổng bảo mật.

Trong Java I/O, đối tượng hay gặp nhất là file và đường dẫn: ứng dụng kiểm tra một `Path` rồi mở, ghi, đổi tên hoặc xóa file tương ứng. Một tiến trình khác có thể thay file bằng symbolic link (symlink), đổi tên thư mục, tạo trước file hoặc điều chỉnh quyền giữa hai thao tác.

~~~text
Thời điểm        Luồng ứng dụng                 Tác nhân khác
T1               Kiểm tra: file chưa tồn tại
                 |                             Tạo file cùng tên
                 |                             hoặc thay symlink
T2               Ghi file theo tên đã kiểm tra
                 |
Kết quả          Thao tác có thể tác động lên đối tượng
                 khác với đối tượng ứng dụng dự định.
~~~

Có thể có race dù **không có attacker**: hai request đồng thời, hai worker, nhiều JVM, tác vụ dọn rác hoặc tiến trình ngoài đều có thể thay đổi trạng thái. Khi có đối thủ chủ động điều khiển thư mục/đường dẫn, đây còn là một dạng tấn công **race condition**.

**Phân biệt ba yếu tố:**

- **Check:** một lần hỏi hoặc kiểm tra trạng thái, chẳng hạn `Files.exists(path)`, `Files.isReadable(path)`, `Files.isRegularFile(path)`, `Files.notExists(path)`, `Files.readAttributes(path, ...)` hoặc bước kiểm tra tên file.
- **Gap:** khoảng thời gian giữa check và thao tác tiếp theo; dù rất ngắn vẫn tồn tại và thread scheduling có thể đổi thứ tự thực thi.
- **Use:** thao tác tạo, mở, đọc, ghi, di chuyển, thay thế, xóa hoặc chỉnh metadata của file.

Không phải mọi chuỗi có hai thao tác I/O đều là lỗ hổng. Vấn đề xuất hiện khi tính đúng đắn hoặc bảo mật **phụ thuộc vào giả định trạng thái ở T1 vẫn đúng ở T2**.

## 2. Cách TOCTOU xuất hiện trên filesystem

Giả sử chương trình nhận tên file từ client và chỉ muốn tạo file mới khi chưa có file đó:

~~~java
Path target = uploadDir.resolve(requestedName);
if (Files.notExists(target)) {
    Files.writeString(target, content);
}
~~~

Đây là **đoạn minh họa lỗi**, không phải chương trình độc lập. Phần nguy hiểm nằm ở:

1. `Files.notExists(target)` chỉ phản ánh trạng thái được quan sát **ngay lúc gọi**. Nó không đặt khóa và không “đặt chỗ” tên file.
2. Tác nhân khác có thể tạo `target` sau khi phương thức trả `true`.
3. Lệnh `Files.writeString(target, content)` mặc định mở file với hành vi tương đương `CREATE`, `TRUNCATE_EXISTING` và `WRITE`. Vì vậy file vừa được tạo có thể bị **ghi đè/truncate**, thay vì được bảo vệ bằng điều kiện “chỉ tạo nếu chưa có”.
4. Nếu một phần của đường dẫn là symlink mà bên khác có thể đổi, thao tác có thể bị hướng đến một file khác dự kiến.

`Files.exists` / `notExists` còn có chi tiết quan trọng: khi không xác định được trạng thái, **cả hai có thể trả `false`**. Kết quả không tồn tại không tự mang ý nghĩa chứng minh chắc chắn rằng có thể tạo file; không được dùng hai hàm này làm cơ chế đồng bộ hay kiểm soát quyền.

### 2.1. Các tình huống điển hình

| Kiểm tra trước | Thao tác sau | Rủi ro khi trạng thái đổi giữa hai bước |
| --- | --- | --- |
| `if (!Files.exists(p))` | `Files.writeString(p, ...)` | File xuất hiện, dữ liệu của bên khác bị ghi đè |
| `Files.isRegularFile(p)` | `Files.newInputStream(p)` | File bị thay hoặc symlink đổi mục tiêu, ứng dụng đọc file khác |
| `Files.isWritable(p)` | `Files.newOutputStream(p)` | Quyền/trạng thái thay đổi; mở file thất bại hoặc trúng đối tượng khác |
| Kiểm tra owner/permission/path | `Files.delete(p)` | Xóa một entry khác với entry đã kiểm tra |
| `Files.size(p) <= limit` | `Files.readAllBytes(p)` | File tăng kích thước, tiêu thụ nhiều bộ nhớ hơn dự kiến |
| Kiểm tra thư mục upload có tồn tại | Tạo file con trong thư mục | Thư mục có thể bị thay bằng symlink hoặc đổi sang nơi khác |

Ví dụ kiểm tra `Files.size(p)` rồi dùng `readAllBytes(p)` **không** tạo hạn mức an toàn. Nếu kích thước tối đa là bất biến bảo mật, hãy giới hạn số byte **trong lúc đọc** và từ chối khi vượt hạn mức.

### 2.2. Mối đe dọa thực tế phụ thuộc quyền của tác nhân khác

Một attacker chỉ có thể tận dụng race khi họ có cách tác động trạng thái có liên quan: chẳng hạn quyền thay entry trong thư mục chứa file upload, quyền chỉnh symlink, hoặc khả năng gửi các request cạnh tranh. Trong thư mục chỉ chương trình đáng tin cậy có quyền sửa, rủi ro bị lợi dụng thường thấp hơn, nhưng vẫn có thể gặp lỗi do tiến trình nội bộ.

Vì thế trước khi sửa lỗi phải xác định **ai sở hữu thư mục, ai có quyền đổi các entry, ai quyết định tên file và thao tác nào phải an toàn**. Không nên chỉ đổ lỗi cho JVM hay độ trễ của hệ điều hành.

## 3. Ví dụ Java 17+: tái hiện sai sót check → write

Ví dụ sau **mô phỏng chính xác thứ tự interleaving**, nên kết quả ổn định mà không phải hy vọng hai thread đua đúng thời điểm. Nó tạo toàn bộ file trong một thư mục tạm riêng.

Tạo file `ToctouCreateDemo.java`:

~~~java
import java.nio.file.*;

import static java.nio.file.StandardOpenOption.*;

public class ToctouCreateDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("toctou-demo-");
        Path unsafe = dir.resolve("unsafe.txt");
        Path safe = dir.resolve("safe.txt");

        try {
            // T1: Ứng dụng quan sát file chưa tồn tại.
            boolean absent = Files.notExists(unsafe);

            if (absent) {
                // Mô phỏng một tiến trình khác tạo file giữa T1 và T2.
                Files.writeString(unsafe, "other", CREATE_NEW, WRITE);

                // T2: Ứng dụng làm theo kết quả kiểm tra cũ.
                Files.writeString(unsafe, "app",
                        CREATE, TRUNCATE_EXISTING, WRITE);
            }

            System.out.println("unsafe=" + Files.readString(unsafe));

            // File đã có trước: CREATE_NEW từ chối ghi đè.
            Files.writeString(safe, "other", CREATE_NEW, WRITE);
            try {
                Files.writeString(safe, "app", CREATE_NEW, WRITE);
            } catch (FileAlreadyExistsException expected) {
                System.out.println("safe=rejected");
            }

            System.out.println("safe-content=" + Files.readString(safe));
        } finally {
            Files.deleteIfExists(unsafe);
            Files.deleteIfExists(safe);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Chạy:

~~~bash
javac ToctouCreateDemo.java
java ToctouCreateDemo
~~~

Stdout:

~~~text
unsafe=app
safe=rejected
safe-content=other
~~~

**Diễn giải:** Ở nhánh đầu, kết quả `notExists` từng đúng, nhưng đến lúc `writeString` chạy, file đã tồn tại. Các option `CREATE` và `TRUNCATE_EXISTING` khiến ứng dụng ghi đè chuỗi `other` thành `app`.

Ở nhánh sau, `CREATE_NEW` làm điều kiện “file chưa tồn tại” và việc tạo file thành **một thao tác atomic đối với việc tạo entry cùng tên** theo hợp đồng `Files`. Khi entry đã có, nó báo `FileAlreadyExistsException` (trên provider minh họa), giữ nguyên nội dung. Không cần gọi `Files.notExists` trước.

**Giới hạn của `CREATE_NEW`:** tính atomic áp dụng cho thao tác tạo entry tại đường dẫn mà filesystem đã phân giải. Nếu **thư mục cha hay các thành phần tổ tiên** do attacker thay đổi được, bản thân `CREATE_NEW` không phải giải pháp đầy đủ chống chuyển hướng qua symlink ở các thành phần đó. Đồng thời “không bị ghi đè lúc tạo” không có nghĩa file sẽ không bị thay sau khi tạo.

## 4. Giảm khoảng trống bằng thao tác atomic, không phải bằng kiểm tra nhanh hơn

Một nguyên tắc thực tế: nếu điều kiện phải đúng **ngay tại lúc thao tác**, hãy tìm API thực hiện kiểm tra điều kiện và hành động **trong cùng thao tác**.

### 4.1. Tạo file nếu chưa có

- `Files.createFile(path)` kiểm tra tên chưa có và tạo file rỗng như **một thao tác atomic**; nếu tồn tại thì thất bại.
- `Files.newByteChannel(path, Set.of(CREATE_NEW, WRITE))` mở channel và yêu cầu tạo mới độc quyền, tránh chuỗi check rồi mở.
- `Files.writeString(path, text, CREATE_NEW, WRITE)` làm tương tự cho nội dung chuỗi trong ví dụ trên.

Đừng diễn giải “atomic create” thành “ghi toàn bộ nội dung atomic”. `CREATE_NEW` bảo vệ bước tạo tên file; một process khác có thể quan sát file đang được ghi dở. Muốn người đọc chỉ thấy **phiên bản nội dung hoàn chỉnh**, cần chiến lược **ghi vào file staging rồi publish**.

### 4.2. Ghi staging rồi publish bằng atomic move

Mô hình phổ biến đối với một file kết quả:

1. Tạo file tạm mới bằng `Files.createTempFile(parent, prefix, suffix)` **trong thư mục đích hoặc cùng FileStore**, với quyền thích hợp.
2. Ghi toàn bộ nội dung vào file tạm, hoàn tất xử lý và đóng stream/channel.
3. Gọi `Files.move(temp, destination, StandardCopyOption.ATOMIC_MOVE)` để yêu cầu filesystem đổi entry trong một thao tác atomic.
4. Nếu provider ném `AtomicMoveNotSupportedException`, xử lý theo hợp đồng của ứng dụng: từ chối publish, chọn cơ chế có kiểm soát hoặc rollback. Không âm thầm fallback sang `move` thường rồi tuyên bố thao tác vẫn atomic.

Ví dụ logic publish (mã nằm **bên trong method có `throws IOException`**, với `parent` và `destination` đã được xác định an toàn):

~~~java
Path staging = Files.createTempFile(parent, ".publish-", ".part");
try {
    Files.writeString(staging, payload,
            StandardOpenOption.WRITE,
            StandardOpenOption.TRUNCATE_EXISTING);

    // Có thể ném AtomicMoveNotSupportedException.
    Files.move(staging, destination, StandardCopyOption.ATOMIC_MOVE);
} finally {
    Files.deleteIfExists(staging);
}
~~~

Có hai điều phải ghi nhớ:

- Với `ATOMIC_MOVE`, tài liệu Java quy định **các option khác bị bỏ qua**; khi `destination` đã tồn tại, hành vi thay thế hay từ chối **phụ thuộc implementation**. Vì vậy **`ATOMIC_MOVE` không cung cấp cam kết “create only, tuyệt đối không overwrite”** cho đích đã tồn tại. Nếu cần cả atomic publish lẫn exclusive creation, phải chọn giao thức/storage hỗ trợ đúng tính chất đó và kiểm thử trên filesystem mục tiêu.
- Atomic rename/move chủ yếu bảo vệ **tính nhất quán của việc nhìn thấy entry**, không tự bảo đảm dữ liệu đã được flush bền vững xuống storage sau mất điện. Nếu cần durability, còn phải xét `FileChannel.force(...)`, flush thư mục và bảo đảm của hệ điều hành/filesystem.

### 4.3. File lock và mutex có đủ không?

- `synchronized`, `ReentrantLock` chỉ phối hợp các luồng **cùng chia sẻ đúng lock** trong JVM. Process khác không phải tham gia.
- `FileChannel.lock()` / `tryLock()` là một cơ chế phối hợp khóa file; cách cưỡng chế khóa và phạm vi của chúng phụ thuộc platform. Nhiều filesystem dùng khóa advisory hoặc có hành vi khác trên mạng; process không tuân giao thức lock vẫn có thể gây vấn đề.
- Distributed lock cũng chỉ có hiệu lực khi **mọi writer tuân giao thức** và điều kiện hết hạn/fencing được xử lý đúng.

Nếu cần tránh ghi đè, `CREATE_NEW` thường mạnh và đơn giản hơn “check bằng `exists` rồi lock/ghi”. Nếu bài toán là nhiều writer cùng cập nhật một giá trị, cần thiết kế concurrency control phù hợp, không chỉ thêm khóa quanh một `Path`.

## 5. Symlink race: kiểm tra một đường dẫn, mở một đối tượng khác

### 5.1. Cơ chế

Giả sử một service chạy với quyền cao nhận tên `report.txt` bên trong thư mục mà user có thể thay đổi entry:

~~~text
T1: /uploads/report.txt -> file bình thường, kiểm tra hợp lệ
       |
       | attacker đổi report.txt thành symlink
       v
T2: /uploads/report.txt -> /some/other/location
    service mở theo path, hành động bị chuyển hướng
~~~

Symlink không phải nguyên nhân duy nhất. Đối tượng file còn có thể bị **rename/replace**, và một thành phần đường dẫn cha như `/uploads/current` có thể bị đổi thành symlink; chỉ kiểm tra symlink của **tên file cuối** chưa bảo vệ được mọi thành phần.

Các thao tác như `Path.normalize()` và `Path.toAbsolutePath()` là xử lý tên đường dẫn, không khóa filesystem và không bảo đảm đối tượng đang được mở chính là đối tượng đã kiểm tra trước đó. `toRealPath()` giải quyết symlink để lấy real path tại **thời điểm gọi**, nhưng file vẫn có thể đổi trước lần sử dụng sau. Vì vậy “gọi `toRealPath` rồi mở file” vẫn có TOCTOU.

### 5.2. `NOFOLLOW_LINKS` giúp gì?

`LinkOption.NOFOLLOW_LINKS` yêu cầu API có hỗ trợ **không đi theo symbolic link** ở phép truy cập tương ứng. Ví dụ:

~~~java
import java.nio.channels.SeekableByteChannel;
import java.nio.file.*;
import java.util.Set;

try (SeekableByteChannel channel = Files.newByteChannel(
        path, Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
    // Đọc từ channel đã mở.
}
~~~

Đây là **đoạn minh họa**, giả định biến `path` đã được khai báo và code ở trong method có `throws IOException`. `NOFOLLOW_LINKS` trong lời gọi mở channel này giúp tránh follow **symlink cuối cùng** theo quy tắc provider. Nó không biến một lần `Files.isRegularFile(path, NOFOLLOW_LINKS)` trước đó thành thao tác atomic, không tự bảo vệ đường dẫn cha có thể bị thay, và không thay thế kiểm soát quyền của thư mục.

Chỉ truyền `NOFOLLOW_LINKS` cho API thực sự chấp nhận nó; đừng suy luận mọi API nhận `Path` sẽ tuân cùng semantics.

### 5.3. `SecureDirectoryStream`: thao tác tương đối với thư mục đang mở

Java NIO.2 có interface `java.nio.file.SecureDirectoryStream<Path>` dành cho chương trình cần thực hiện file operation tương đối với một **handle của thư mục đã mở**. Tài liệu Java mô tả mục tiêu là tránh race khi di chuyển, xóa và truy cập file trong cây thư mục mà path có thể bị thay trong lúc chạy.

Điểm khác với cách `Files.isRegularFile(fullPath)` rồi `Files.newInputStream(fullPath)`:

- `SecureDirectoryStream` định vị tên **tương đối với thư mục đã mở**, thay vì mỗi lần đi từ pathname đầy đủ.
- Có thể mở entry con bằng `newByteChannel(relativeName, options)`, dùng `getFileAttributeView` cho file con, `deleteFile(relativeName)`, `move(...)` hoặc mở thư mục con bằng `newDirectoryStream(relativeDir, NOFOLLOW_LINKS)`.
- Những thao tác mở thư mục con có thể giữ xử lý tương đối với handle qua từng mức cây, tránh phụ thuộc vào tên thư mục ngoài vốn có thể bị rename/replace.
- **Không phải provider nào cũng hỗ trợ**. `Files.newDirectoryStream(dir)` chỉ trả về một đối tượng triển khai `SecureDirectoryStream` nếu hệ điều hành và provider cung cấp cơ chế tương ứng. Không được cast bừa và giả định tính năng luôn có.

Ví dụ file `SecureDirectoryStreamDemo.java`, chỉ đọc một file nằm trong thư mục tạm do chương trình tạo:

~~~java
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Set;

public class SecureDirectoryStreamDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("secure-dir-");
        Path file = dir.resolve("data.txt");

        try {
            Files.writeString(file, "hello",
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);

            try (DirectoryStream<Path> raw = Files.newDirectoryStream(dir)) {
                if (!(raw instanceof SecureDirectoryStream<?>)) {
                    System.out.println("secure-stream=unavailable");
                } else {
                    @SuppressWarnings("unchecked")
                    SecureDirectoryStream<Path> secure =
                            (SecureDirectoryStream<Path>) raw;

                    try (SeekableByteChannel channel = secure.newByteChannel(
                            Path.of("data.txt"),
                            Set.of(StandardOpenOption.READ,
                                   LinkOption.NOFOLLOW_LINKS))) {
                        ByteBuffer buffer = ByteBuffer.allocate(64);
                        channel.read(buffer);
                        buffer.flip();
                        System.out.println(
                                StandardCharsets.UTF_8.decode(buffer));
                    }
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch:

~~~bash
javac SecureDirectoryStreamDemo.java
java SecureDirectoryStreamDemo
~~~

Có **hai kết quả hợp lệ tùy provider**:

~~~text
hello
~~~

hoặc:

~~~text
secure-stream=unavailable
~~~

Trong nhánh hỗ trợ, `newByteChannel` nhận tên tương đối `data.txt` và làm việc với directory stream đang mở. Đây là ví dụ API cho entry đơn giản; trong dịch vụ thực tế phải kiểm tra tên đầu vào, tránh tên tuyệt đối hoặc `..`, bảo đảm handle ban đầu mở từ thư mục tin cậy và triển khai chính sách **fail closed** nếu môi trường bắt buộc race resistance mà provider không hỗ trợ.

**Giới hạn quan trọng:** giữ handle thư mục chưa tự xác nhận **quyền truy cập của ứng dụng đối với nội dung** hoặc dữ liệu đang đọc. Cần xác minh input, đối tượng và permissions tại thời điểm thích hợp. Khi cần kiểm soát chính xác các thao tác cấp hệ điều hành, có thể cần API native tương đương `openat` hoặc cơ chế hệ thống riêng — Java NIO.2 không đảm bảo tất cả các thuộc tính bảo mật của mọi filesystem.

## 6. Kiểm tra đường dẫn: cần làm nhưng chưa đủ

Giả sử chỉ cho phép tên file trực tiếp bên trong thư mục `root`:

~~~java
Path root = approvedRoot.toAbsolutePath().normalize();
Path candidate = root.resolve(requestedName).normalize();

if (!candidate.startsWith(root)) {
    throw new SecurityException("Path escapes root");
}
~~~

Đây là **mã minh họa nằm trong method** với hai biến đầu vào `approvedRoot` và `requestedName` đã khai báo. Nó giúp loại bỏ trường hợp path traversal **theo tên** như `../../outside.txt` sau khi normalize. Tuy nhiên:

- `startsWith` là kiểm tra theo các thành phần path, không kiểm tra real target trên filesystem.
- Symlink có thể trỏ ra ngoài dù pathname đã chuẩn hóa vẫn nằm bên dưới `root`.
- Nếu một tiến trình khác có quyền thay directory entry, kiểm tra ở T1 không bảo vệ cho lần mở ở T2.
- Nếu chỉ cho phép **tên file một cấp**, nên kiểm tra `requestedName` thực sự là filename đơn, không có separator hoặc thành phần `..`, trước khi resolve.
- Nên giới hạn quyền sửa của thư mục, đặt tên file do server kiểm soát khi phù hợp và dùng API thao tác tương đối với handle hoặc các lựa chọn mở atomic.

Kiểm tra path đầu vào vẫn cần thiết vì giúp xác định phạm vi. Hãy phân biệt rõ **path validation** với **filesystem object identity**; hai vấn đề phải được giải quyết bằng các cơ chế phù hợp.

## 7. Đọc, ghi, sửa và xóa: chọn biện pháp theo hành động

| Mục tiêu | Cách không đủ | Hướng thiết kế tốt hơn |
| --- | --- | --- |
| Chỉ tạo mới, không ghi đè | `if (!exists) write` | `CREATE_NEW` hoặc `Files.createFile` |
| Không cho đọc qua symlink cuối | `isSymbolicLink` rồi `newInputStream` | Mở bằng API hỗ trợ `NOFOLLOW_LINKS`; xem cả đường dẫn cha |
| Làm việc trong cây thư mục có thể bị thay | Kiểm tra real path rồi nhiều lần mở bằng full path | `SecureDirectoryStream` khi provider hỗ trợ; policy nếu không hỗ trợ |
| Publish file hoàn chỉnh | Ghi trực tiếp vào file kết quả | Ghi staging rồi `ATOMIC_MOVE`, kiểm tra semantics thay thế đích |
| Chỉ xóa entry đã được chọn | `isRegularFile(p)` rồi `delete(p)` | Định vị entry tương đối với handle thư mục tin cậy; khi phù hợp, `SecureDirectoryStream.deleteFile` |
| Giới hạn số byte đọc | `Files.size(p)` rồi `readAllBytes(p)` | Đọc stream/channel với bộ đếm byte và ngừng ngay khi vượt giới hạn |
| Cập nhật một record theo phiên bản | `read -> validate -> write` không khóa | Compare-and-set, optimistic locking với version, transaction hoặc unique constraint phù hợp |

Không phải atomic ở một bước nghĩa là cả nghiệp vụ đa bước atomic. Ví dụ tạo file thành công và sau đó insert DB row thất bại vẫn để lại trạng thái dở dang; khi cần nhất quán xuyên tài nguyên phải có transaction/compensation hoặc giao thức tương ứng.

## 8. Ví dụ TOCTOU ngoài file: giới hạn của check-before-update

TOCTOU cũng xuất hiện trong API/DB. Giả sử hai request cùng xử lý một mã coupon:

~~~text
A: SELECT remaining -> 1
B: SELECT remaining -> 1
A: UPDATE remaining -> 0; cho phép dùng
B: UPDATE remaining -> 0; cũng cho phép dùng
~~~

Nếu ứng dụng chỉ dựa vào lần `SELECT` trước đó, hai request có thể cùng được chấp nhận. Hướng đúng là biến điều kiện thành một **thao tác có kiểm soát cạnh tranh** ở storage, chẳng hạn:

~~~sql
UPDATE coupon
SET remaining = remaining - 1
WHERE id = ? AND remaining > 0;
~~~

Đoạn SQL này chỉ minh họa một thao tác decrement có điều kiện. Ứng dụng phải kiểm tra **số hàng bị cập nhật**, bảo đảm khóa/định danh và transaction/isolation phù hợp. Nếu `UPDATE` ảnh hưởng 0 hàng thì từ chối sử dụng; không xác nhận thành công bằng kết quả `SELECT` cũ.

Bài toán file và DB chung bản chất: một “lần kiểm tra đúng” không phải cam kết rằng điều kiện vẫn đúng khi thao tác khác bắt đầu.

## 9. Những giải pháp tưởng đúng nhưng còn race

### 9.1. “Kiểm tra lại ngay trước lúc mở”

~~~java
if (Files.exists(path) && Files.isReadable(path)) {
    // Race vẫn có thể xảy ra ngay tại đây.
    try (var in = Files.newInputStream(path)) {
        // ...
    }
}
~~~

Khoảng thời gian có thể ngắn hơn, nhưng chưa biến check+open thành một thao tác. `exists` và `isReadable` còn có semantics không bảo đảm lần mở sau sẽ thành công. Cần thiết kế trên **open/operation có ràng buộc thích hợp** rồi xử lý kết quả tại chính thao tác đó.

### 9.2. “Dùng `synchronized` là xong”

`synchronized` chỉ có ý nghĩa giữa những code path dùng **cùng monitor** trong một JVM; worker khác, JVM khác, process ngoài và attacker không bắt buộc tuân nó. Dùng khi cần đồng bộ nội bộ, không lấy nó làm bảo vệ file upload dùng chung.

### 9.3. “Dùng `NOFOLLOW_LINKS` ở lần check”

`Files.isRegularFile(path, NOFOLLOW_LINKS)` quan sát link tại một thời điểm. Nếu sau đó mở bằng lệnh không dùng `NOFOLLOW_LINKS`, vẫn có cửa sổ hoán đổi. Ngay cả `NOFOLLOW_LINKS` ở lần mở cũng phải được xem cùng rủi ro **ancestor path**.

### 9.4. “So `fileKey` trước và sau”

`BasicFileAttributes.fileKey()` đôi khi giúp nhận diện file trên provider hỗ trợ, nhưng không phải tất cả provider trả khóa đáng tin cậy hoặc ổn định. So sánh hai lần vẫn là **phát hiện sau sự kiện**, không thay thế phép mở và xử lý gắn với cùng object. Khi thao tác ghi/xóa đã diễn ra trên sai file, phát hiện sau đó có thể quá muộn.

### 9.5. “Chỉ xử lý `IOException` rồi retry”

Retry cùng đường dẫn mà không xem lại điều kiện an toàn có thể lặp lại race hoặc tác động lên entry mới. Phân biệt `FileAlreadyExistsException`, `NoSuchFileException`, `AccessDeniedException` và `AtomicMoveNotSupportedException`; phản ứng phụ thuộc hợp đồng của thao tác.

### 9.6. “Di chuyển file là atomic trên mọi ổ đĩa”

`Files.move` bình thường không có bảo đảm atomic chung cho mọi provider. `ATOMIC_MOVE` cũng có thể không được hỗ trợ, đặc biệt nếu khác filesystem. Không tự giả định việc kiểm tra trước `exists` giải quyết chuyện replace target trong `ATOMIC_MOVE`, vì đặc tả cho phép semantics khác nhau nếu target đã tồn tại.

## 10. Quy trình thiết kế chống TOCTOU

1. **Xác định bất biến cần giữ**: không overwrite; không đọc ra ngoài thư mục; không xóa sai file; chỉ một request được claim job; không xử lý quá dung lượng cho phép.
2. **Xác định tác nhân và phạm vi cạnh tranh**: thread cùng JVM, process khác, người dùng có quyền sửa directory entry, symlink, network filesystem hay transaction DB.
3. **Tìm một primitive atomic đúng hợp đồng**: `CREATE_NEW`, directory-handle operations, conditional update, transaction, compare-and-set hoặc commit protocol.
4. **Giữ handle/reference ổn định khi cần**: sau khi mở file/channel phù hợp, ưu tiên xử lý chính handle đó. Tránh kiểm tra trên path rồi mở lại cùng tên nếu sự thay đổi identity gây nguy hiểm.
5. **Bảo vệ directory entry và kiểm soát quyền**: tên server sinh, directory chỉ service được sửa, option chống follow link thích hợp và provider hỗ trợ `SecureDirectoryStream` nếu cần.
6. **Định nghĩa hành vi khi race thất bại**: thông thường coi “file đã tồn tại” là conflict hợp lệ, không phải lý do fallback sang overwrite. Ghi log bối cảnh tối thiểu rồi trả lỗi phù hợp.
7. **Kiểm thử thứ tự đan xen có kiểm soát**: dùng latch/barrier, hook giả lập hoặc fixture để cưỡng bức T1–tác nhân đổi trạng thái–T2. Không dựa vào `Thread.sleep(...)` để hy vọng race tự xuất hiện.
8. **Xác minh trên filesystem triển khai thực tế**: provider khác nhau ở hỗ trợ symlink, `SecureDirectoryStream`, atomic move, ACL và khả năng khóa.

Một phép thử âm tính hữu ích là tạo entry từ actor thứ hai **ngay sau check**, rồi xác minh ứng dụng không ghi đè. Với symlink race, cần kiểm thử trên hệ điều hành/provider thực sự có quyền tạo symlink và giới hạn rõ điều gì được bảo vệ; không suy diễn từ kết quả trên máy dev.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `Files.notExists(path)` trả `true`; có bảo đảm lệnh `Files.writeString(path, ...)` tiếp theo được phép tạo file mới mà không ghi đè không?

**Đáp án:** Không. Entry có thể xuất hiện sau lần check. Nếu yêu cầu là “chỉ tạo mới”, truyền `CREATE_NEW` tại chính lần mở/ghi.

**Câu 2.** `Files.createFile(path)` atomic có nghĩa là toàn bộ nội dung file do nhiều lần `write` sau đó cũng atomic?

**Đáp án:** Không. Atomic ở đây là hành vi check-and-create đối với entry. Publication nội dung hoàn chỉnh là bài toán khác, thường cần staging + atomic move và hiểu rõ guarantee của filesystem.

**Câu 3.** Sau `Path.toRealPath()`, service chắc chắn không thể bị symlink race nếu tiếp tục mở bằng đường dẫn đó?

**Đáp án:** Không. `toRealPath` phản ánh thực trạng lúc gọi, không khóa các entry. Cần xem ai có thể thay parent và tận dụng open tương đối với directory handle hoặc API có option an toàn.

**Câu 4.** Vì sao `NOFOLLOW_LINKS` ở một lần `isRegularFile` chưa đủ?

**Đáp án:** Đó vẫn là phép kiểm tra tách khỏi lần mở, nên entry có thể bị thay sau check. Option tại thao tác mở có hiệu lực thích hợp hơn đối với final symlink, nhưng chưa tự bảo vệ ancestor path.

**Câu 5.** Tại sao chỉ dùng `synchronized` không chống được attacker sửa file qua process khác?

**Đáp án:** Monitor Java chỉ đồng bộ những thread chung JVM dùng chính monitor đó. Process khác không chịu ràng buộc.

**Câu 6.** Nếu provider không hỗ trợ `SecureDirectoryStream` mà hệ thống yêu cầu chống đổi directory entry khi đọc/xóa, nên làm gì?

**Đáp án:** Không âm thầm cast hoặc dùng fallback dựa vào các bước check/open nếu điều đó phá bất biến bảo mật. Từ chối tính năng, đổi provider/môi trường, siết quyền directory hoặc xây dựng cơ chế native phù hợp và kiểm thử.

## 12. Tài liệu tham khảo

- [Java SE 17 `Files` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `exists`, `notExists`, `createFile`, `newByteChannel`, `move` và option `ATOMIC_MOVE`.
- [Java SE 17 `SecureDirectoryStream` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): truy cập tương đối với directory handle, các thao tác mở/xóa/move tránh race theo mục tiêu của interface.
- [Java SE 17 `LinkOption` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): semantics của `NOFOLLOW_LINKS`.
- [Java SE 17 `StandardOpenOption` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE_NEW`, `CREATE`, `TRUNCATE_EXISTING`, `WRITE`.
- [Java SE 17 `FileChannel` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `lock`, `tryLock` và `force`.

**Điểm cốt lõi:** TOCTOU là lỗi của **giao thức nhiều bước dựa trên trạng thái có thể thay đổi**. Giải pháp không phải giảm vài microsecond giữa check và use, mà là thiết kế để điều kiện được xác nhận **ngay trong thao tác có ràng buộc phù hợp**, hoặc giữ reference ổn định tới đúng đối tượng cần xử lý.
