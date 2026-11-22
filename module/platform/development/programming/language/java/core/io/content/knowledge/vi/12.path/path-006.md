# `Path.toAbsolutePath()` khác `Path.toRealPath()` trong Java

Trong Java NIO.2, hai câu lệnh dưới đây đều có thể cho ra một đường dẫn **tuyệt đối**, nhưng chúng **không làm cùng một việc**:

~~~java
Path absolute = path.toAbsolutePath();
Path real = path.toRealPath();
~~~

`toAbsolutePath()` chủ yếu chuyển cách biểu diễn đường dẫn thành **dạng tuyệt đối**; đường dẫn được tạo **không cần trỏ tới tệp đang tồn tại**. `toRealPath()` đi xa hơn: nó xác định **đường dẫn thực của một đối tượng đã tồn tại trong hệ thống tệp**, thường loại bỏ các thành phần dư thừa và **giải quyết symbolic link theo mặc định**. Vì cần tra cứu hệ thống tệp, nó có thể ném `IOException`.

Nhầm hai phương thức này dễ dẫn đến các lỗi như hiển thị đường dẫn rồi tưởng tệp đã tồn tại, kiểm tra quyền truy cập sai chỗ, hoặc so sánh hai đường dẫn mà không nhận ra một bên đi qua symbolic link.

## 1. Nền tảng: `Path` mô tả đường dẫn, không phải tệp đã mở

`java.nio.file.Path` là đối tượng biểu diễn vị trí trong một hệ thống tệp. Bạn có thể tạo một `Path` bất kể đối tượng tương ứng có tồn tại không:

~~~java
import java.nio.file.Path;

Path relative = Path.of("data", "report.txt");
Path missing = Path.of("not-created-yet.txt");
~~~

Hai câu lệnh chỉ tạo **đối tượng đường dẫn**; không tự tạo file hay kiểm chứng file có tồn tại. Các thao tác trên `Path` như `resolve()`, `getParent()`, `getFileName()`, `startsWith()` và `normalize()` thường làm việc trên cấu trúc đường dẫn; chỉ những API thực sự yêu cầu tương tác với hệ thống tệp mới có ý nghĩa như mở, đọc metadata hoặc xác định đường dẫn thực.

Phân biệt:

- **Relative path (đường dẫn tương đối):** không có root tuyệt đối; ví dụ `docs/guide.txt` trên hệ Unix.
- **Absolute path (đường dẫn tuyệt đối):** chứa thông tin để diễn giải từ một root của file system; ví dụ `/home/app/docs/guide.txt` trên Unix hoặc đường dẫn có ổ đĩa/root thích hợp trên Windows.
- **Real path (đường dẫn thực):** đường dẫn tuyệt đối được suy ra bằng cách tham chiếu đối tượng thực trong hệ thống tệp, với quy tắc giải quyết liên kết và thành phần dư thừa.

Một đường dẫn tuyệt đối vẫn có thể **sai, chưa tồn tại, bị chặn truy cập hoặc chứa `..`**. Từ “absolute” mô tả **hình thức đường dẫn**, không phải một chứng nhận về trạng thái tệp.

## 2. `toAbsolutePath()` thực sự làm gì?

Cú pháp:

~~~java
Path absolute = path.toAbsolutePath();
~~~

Theo hợp đồng `Path` trong Java 17:

- Trả về `Path` biểu diễn đường dẫn **tuyệt đối**.
- Nếu `path` đã là đường dẫn tuyệt đối, phương thức trả về chính đối tượng đường dẫn đó theo hợp đồng API.
- Với đường dẫn tương đối trên provider mặc định, đường dẫn thường được **giải quyết dựa trên thư mục mặc định của hệ thống tệp / thư mục làm việc**.
- **Không tự kiểm tra tệp có tồn tại.**
- **Không tự chuẩn hóa** để xóa mọi thành phần `.` hoặc `..`.
- **Không tự giải quyết symbolic link** thành đường dẫn của đích.
- Việc chuyển đổi là phụ thuộc `FileSystemProvider` đối với một số chi tiết, nên không tự ghép chuỗi bằng dấu `/` hoặc `\\` thay cho API.

Ví dụ giả định thư mục làm việc là `/app` trên hệ Unix:

~~~text
Path.of("docs", "..", "report.txt")
    .toAbsolutePath()

Kết quả điển hình:
    /app/docs/../report.txt

Không nhất thiết là:
    /app/report.txt
~~~

Ở đây `/app/docs/../report.txt` đã là **tuyệt đối**, nhưng vẫn có `docs/..`. Và việc `/app/report.txt` có tồn tại hay không **không ảnh hưởng tới khả năng tạo đối tượng `Path` tuyệt đối**.

`toAbsolutePath()` có thể gặp lỗi theo hợp đồng provider (ví dụ `IOError` hoặc `SecurityException` ở một số cấu hình), nên không nên diễn đạt tuyệt đối rằng nó “không bao giờ có lỗi”. Khác biệt chính là **không bắt buộc xác thực tệp tồn tại để tạo đường dẫn tuyệt đối**.

### Khi nào cần `toAbsolutePath()`?

Nó phù hợp khi muốn:

1. Ghi log hoặc hiển thị đường dẫn đầy đủ để người dùng biết ứng dụng đang diễn giải đường dẫn tương đối từ đâu.
2. Tạo đường dẫn tuyệt đối cho **một tệp đầu ra chưa tồn tại**, ví dụ đường dẫn một báo cáo sẽ được tạo sau.
3. Chuẩn bị đường dẫn cho thao tác ở tầng tiếp theo, khi bạn **chưa cần** truy vấn hệ thống tệp.
4. So sánh cấu trúc đường dẫn theo quy ước riêng, nếu chấp nhận rằng việc so sánh chỉ mang ý nghĩa cú pháp.

Nếu muốn bỏ phần `.`/`..` về mặt cú pháp, bạn có thể gọi riêng `normalize()`:

~~~java
Path lexical = path.toAbsolutePath().normalize();
~~~

Nhưng đừng hiểu nhầm: **`normalize()` không truy cập filesystem để kiểm tra cấu trúc thật**. Trong môi trường có symbolic link, rút gọn `link/../file` bằng phép biến đổi thuần đường dẫn có thể **không giữ nguyên đối tượng được tham chiếu**. Đây là lý do phân biệt xử lý lexical với tra cứu real path.

## 3. `toRealPath()` thực sự làm gì?

Cú pháp:

~~~java
import java.io.IOException;
import java.nio.file.Path;

Path real = path.toRealPath(); // Có thể ném IOException.
~~~

`toRealPath(LinkOption... options)` trả đường dẫn thực của **một file/directory đang tồn tại** theo định nghĩa của provider. Trong trường hợp mặc định thông thường:

1. Nếu đầu vào tương đối, trước hết xác định đường dẫn tuyệt đối.
2. Kiểm tra và xử lý đường dẫn thông qua hệ thống tệp.
3. Loại bỏ các thành phần dư thừa trong kết quả; quy tắc chính xác có thể phụ thuộc provider.
4. **Theo mặc định, đi theo symbolic link** để xác định đích cuối.
5. Có thể phản ánh cách viết thực của tên file/thư mục trên hệ thống tệp, ví dụ cách viết hoa/thường thực tế khi provider hỗ trợ.
6. Trả về `Path` **tuyệt đối** định vị đối tượng thực, hoặc ném `IOException` nếu đối tượng không tồn tại/không truy cập được hoặc có lỗi I/O.

Trong trường hợp một đường dẫn trỏ tới tệp có thật:

~~~text
input:     /app/docs/../report.txt
              |
              | toRealPath()
              v
result:    /app/report.txt   (nếu docs tồn tại và hệ thống tệp có cấu trúc phù hợp)
~~~

Ngược lại, khi `docs` không tồn tại, không được giả định `toRealPath()` sẽ coi mọi `docs/..` là có thể lược bỏ vô điều kiện; hoạt động tra cứu thực có thể gặp lỗi tùy provider và cách diễn giải thành phần đường dẫn.

**Quan trọng:** `toRealPath()` không mở một file handle cho bạn sử dụng về sau và không “khóa” đối tượng vào vị trí đó. Đây là kết quả tra cứu **tại thời điểm gọi**. Nếu file hoặc symbolic link bị đổi ngay sau đó, thao tác mở file tiếp theo có thể thấy trạng thái khác.

## 4. Bảng so sánh trực tiếp

| Tiêu chí | `toAbsolutePath()` | `toRealPath()` |
|---|---|---|
| Mục tiêu | Có đường dẫn ở **dạng tuyệt đối** | Xác định **đường dẫn thực** của đối tượng hệ thống tệp |
| Có cần tệp/thư mục tồn tại? | **Không** | **Có**, theo hợp đồng xác định real path |
| Kết quả có tuyệt đối? | Có | Có |
| Có tự bỏ `.`, `..`? | Không phải mục tiêu; không tự `normalize` | Thường loại bỏ thành phần dư thừa khi xác định real path, theo provider |
| Có tự giải quyết symbolic link? | Không | **Có theo mặc định** |
| `NOFOLLOW_LINKS` | Không có tham số option này | Có, để thay đổi cách xử lý symbolic link |
| Có thể ném `IOException`? | Không khai báo `throws IOException`; có khả năng lỗi runtime theo provider | **Có**, khai báo `throws IOException` |
| Phải truy cập trạng thái tệp? | Không cần xác nhận tồn tại | Có, cần xác định đối tượng tệp tồn tại |
| Hợp cho tệp đầu ra chưa tạo? | Có | Không, cho đến khi đối tượng tồn tại |
| Hợp cho đường dẫn đã tồn tại đi qua symlink? | Cho ra absolute nhưng không biết đích symlink | Dùng để lấy real path, có thể giải quyết symlink |

Một biểu thức thường gây nhầm lẫn:

~~~java
path.toAbsolutePath().normalize()
~~~

**không tương đương một cách tổng quát với**:

~~~java
path.toRealPath()
~~~

Dù nhiều ví dụ đơn giản không có symlink cho kết quả giống nhau, ý nghĩa và các điều kiện bảo đảm của hai cách là khác nhau.

## 5. Ví dụ Java 17 chạy độc lập, không phụ thuộc đường dẫn máy

Để không phải dự đoán thư mục làm việc trên máy người học, ví dụ tạo một thư mục tạm có thật, một thư mục con `nested` và một tệp `info.txt`. Nó tạo một `Path` chứa `nested/../info.txt`, rồi so sánh đường dẫn tuyệt đối, đường dẫn chuẩn hóa thuần cú pháp và đường dẫn thực.

Lưu thành **`AbsoluteVsRealPathDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class AbsoluteVsRealPathDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("real-path-demo-").toRealPath();

        try {
            Path nested = Files.createDirectory(root.resolve("nested"));
            Path file = Files.writeString(
                    root.resolve("info.txt"), "OK", StandardCharsets.UTF_8);

            Path candidate = root.resolve(Path.of(
                    "nested", "..", "info.txt"));

            Path absolute = candidate.toAbsolutePath();
            Path normalized = absolute.normalize();
            Path real = candidate.toRealPath();

            System.out.println("Absolute? " + absolute.isAbsolute());
            System.out.println("Absolute keeps ..? "
                    + !absolute.equals(normalized));
            System.out.println("Normalized equals file path? "
                    + normalized.equals(file.toAbsolutePath().normalize()));
            System.out.println("Real equals file real path? "
                    + real.equals(file.toRealPath()));

            Path absent = root.resolve("missing.txt");
            System.out.println("Missing can be absolute? "
                    + absent.toAbsolutePath().isAbsolute());

            try {
                absent.toRealPath();
                System.out.println("Missing real lookup succeeded");
            } catch (IOException ex) {
                System.out.println("Missing real lookup failed");
            }
        } finally {
            Files.deleteIfExists(root.resolve("info.txt"));
            Files.deleteIfExists(root.resolve("nested"));
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 AbsoluteVsRealPathDemo.java
java AbsoluteVsRealPathDemo
~~~

Đầu ra kỳ vọng trên hệ thống tệp mặc định bình thường, nơi có quyền tạo/xóa thư mục tạm:

~~~text
Absolute? true
Absolute keeps ..? true
Normalized equals file path? true
Real equals file real path? true
Missing can be absolute? true
Missing real lookup failed
~~~

### Phân tích đầu ra

- `Files.createTempDirectory(...)` tạo một thư mục thực. Ta lấy `toRealPath()` của thư mục đó để xác định root có thật và dùng nó làm cơ sở.
- `Files.createDirectory(root.resolve("nested"))` tạo thư mục con thật. Đặt `nested/..` trong candidate giúp minh họa điểm khác biệt mà không phụ thuộc vào tên thư mục làm việc.
- `toAbsolutePath()` cho đường dẫn tuyệt đối nhưng **giữ thành phần `..`**, nên `absolute.equals(absolute.normalize())` là `false`.
- `normalize()` loại bỏ `nested/..` về mặt cú pháp. Vì trong ví dụ `nested` tồn tại và không có symlink, đường dẫn chuẩn hóa trùng vị trí `info.txt`.
- `candidate.toRealPath()` kiểm chứng file có thật, trả đường dẫn thực và bằng `file.toRealPath()`.
- `missing.txt` chưa được tạo vẫn có thể có `Path` tuyệt đối, nhưng gọi `toRealPath()` sẽ không xác định được real path; ví dụ bắt `IOException`.
- Khối `finally` cố gắng xóa các mục do chương trình tạo. Nếu người khác thao tác vào thư mục tạm cùng lúc hoặc môi trường hạn chế I/O, code có thể gặp `IOException`; ví dụ này minh họa hành vi trong điều kiện bình thường, không cố che giấu lỗi hệ thống tệp.

**Lưu ý:** `Path.equals()` so sánh hai đối tượng `Path` theo hợp đồng của provider; việc hai `Path` bằng nhau về cách biểu diễn không phải một cơ chế chứng minh chắc chắn hai thao tác file trong tương lai sẽ truy cập cùng một thực thể khi filesystem có thể thay đổi.

## 6. Symbolic link (liên kết mềm) là điểm khác biệt quan trọng

Một **symbolic link** là một mục trong filesystem tham chiếu tới mục tiêu khác. Hình dung trên Unix:

~~~text
/work/assets/logo.png       (tệp thật)
/work/public/logo.png  ----> /work/assets/logo.png
        ^ đường dẫn symlink
~~~

Nếu `Path link = Path.of("/work/public/logo.png")` đại diện cho symlink hợp lệ:

~~~java
Path a = link.toAbsolutePath();
Path b = link.toRealPath();
~~~

- `a` biểu diễn một **đường dẫn tuyệt đối tới chính vị trí symlink**; nó không tự xác định tệp mà symlink trỏ tới.
- `b` theo mặc định **giải quyết symlink**, nên có thể trở thành `/work/assets/logo.png`.
- Một cách viết đường dẫn đi qua nhiều symlink có thể trỏ tới cùng tệp thật với các đường dẫn có biểu diễn rất khác nhau.
- Trong trường hợp có symlink, `toAbsolutePath().normalize()` vẫn chỉ chuẩn hóa **cú pháp**, nên không thay thế việc giải quyết liên kết thật.

### `toRealPath(LinkOption.NOFOLLOW_LINKS)`

Khi muốn xác định đường dẫn thực **mà không theo symbolic link**, API hỗ trợ `LinkOption.NOFOLLOW_LINKS`:

~~~java
import java.nio.file.LinkOption;

Path withoutFollowing = link.toRealPath(LinkOption.NOFOLLOW_LINKS);
~~~

Đây là **đoạn minh họa**, `link` phải là `Path` đã được khai báo và đối tượng filesystem tương ứng phải thỏa hợp đồng của provider.

Khi có `NOFOLLOW_LINKS`, API không giải quyết symbolic link tới đích như chế độ mặc định. Nhưng **không nên đơn giản hóa thành “luôn lấy toAbsolutePath().normalize()”**: hợp đồng `toRealPath` vẫn phụ thuộc filesystem/provider, và cách xử lý `..` xung quanh symlink có thể khác để tránh thay đổi đối tượng được tham chiếu.

Trên hệ Windows, việc tạo symbolic link có thể phụ thuộc quyền hoặc chính sách hệ thống; do đó chương trình ở mục 5 cố ý không tạo symlink để không yêu cầu quyền đặc biệt. Ví dụ symlink ở trên là **mô hình tư duy**, không phải đường dẫn được bảo đảm tồn tại trên máy người học.

## 7. `normalize()`, `toAbsolutePath()` và `toRealPath()` không thể hoán đổi

Ba thao tác dễ lẫn:

### `normalize()`: chuẩn hóa về mặt lexical

~~~java
Path p = Path.of("a", "b", "..", "c");
Path n = p.normalize(); // Biểu diễn thường rút gọn thành a/c.
~~~

`normalize()` loại bỏ các thành phần `.`, hoặc cặp thành phần `name/..` theo quy tắc lexical. Nó **không cần kiểm tra `a` hoặc `b` có tồn tại**. Do đó không phải xác minh filesystem. Trên một số đường dẫn có symbolic link, bỏ `link/..` có thể khiến đường dẫn kết quả trỏ tới **vị trí khác** nếu truy cập thật.

### `toAbsolutePath()`: chuyển thành dạng tuyệt đối

~~~java
Path absolute = Path.of("a", "b", "..", "c")
        .toAbsolutePath();
~~~

`absolute` là đường dẫn tuyệt đối, nhưng `..` không bắt buộc được loại bỏ, và tệp có thể chưa tồn tại.

### `toRealPath()`: tìm đường dẫn thực

~~~java
Path real = Path.of("a", "b", "..", "c")
        .toRealPath(); // throws IOException
~~~

`real` chỉ được nhận thành công khi hệ thống tệp có thể xác định đối tượng theo hợp đồng. Nó mang thông tin về filesystem, không đơn thuần là thao tác chuỗi.

**Mẹo học:** normalize = *rút gọn biểu thức*, absolute = *đặt vào gốc*, real = *đối chiếu với filesystem*. Mẹo này giúp nhớ, nhưng khi xử lý symbolic link và provider khác nhau phải ưu tiên hợp đồng API.

## 8. Tình huống nên chọn phương thức nào?

| Yêu cầu | Cách tiếp cận | Lý do |
|---|---|---|
| Log vị trí dự kiến của file output chưa tạo | `path.toAbsolutePath()` | Không đòi file tồn tại |
| Hiển thị đường dẫn đã bỏ dấu `.`/`..` để người dùng dễ đọc | `path.toAbsolutePath().normalize()` | Chuẩn hóa thuần cú pháp, không xác thực |
| Lấy vị trí thực của tệp đang tồn tại | `path.toRealPath()` | Kiểm chứng và giải quyết liên kết mặc định |
| Giữ symlink mà không theo tới đích khi lấy real path | `path.toRealPath(NOFOLLOW_LINKS)` | Điều chỉnh hợp đồng xử lý liên kết |
| Muốn mở file ngay sau đó | `Files.newInputStream(path)` / `Files.newByteChannel(...)` | Phương thức mở mới thực sự cung cấp handle; `toRealPath` không mở sẵn |
| Muốn biết hai đường dẫn cùng trỏ tới một tệp hiện tại? | `Files.isSameFile(a, b)` nếu phù hợp | API dành cho kiểm tra danh tính file; không chỉ so sánh chuỗi |
| Kiểm tra đối tượng tệp có tồn tại không | `Files.exists(path)` trong ngữ cảnh đơn giản | Nhưng kết quả `false` có thể do không thể xác định trạng thái; không thay thế thao tác I/O chính |
| Xử lý input từ người dùng trong thư mục cho phép | Thiết kế chính sách đường dẫn và mở file an toàn | Chỉ gọi normalize/real path **chưa đủ** ngăn race hoặc traversal |

Một số đoạn code vô tình làm hai việc cùng lúc:

~~~java
Path target = userInput.toAbsolutePath().normalize();
if (Files.exists(target)) {
    // ...
}
~~~

Đoạn này **không tương đương** với việc đã có real path đáng tin và cũng không giữ file cố định giữa kiểm tra và sử dụng. Nếu cần chính sách an ninh, đừng áp dụng phép so sánh chuỗi đơn giản như một hàng rào an toàn duy nhất.

## 9. Xử lý lỗi của `toRealPath()` đúng cách

Vì có tra cứu filesystem, `toRealPath()` khai báo `throws IOException`. Các tình huống thất bại thường gặp:

- **Không tìm thấy đối tượng:** `NoSuchFileException` (một loại `IOException`) có thể được ném.
- **Không đủ quyền:** có thể gặp `AccessDeniedException` hoặc một ngoại lệ I/O khác, phụ thuộc hệ điều hành/provider.
- **Liên kết hỏng hoặc vòng liên kết:** quá trình giải quyết symlink có thể gặp lỗi.
- **Filesystem không sẵn sàng:** đường dẫn trên network filesystem hoặc thiết bị gắn ngoài có thể thất bại.
- **Thay đổi đồng thời:** file/directory có thể đã bị đổi hoặc xóa trong lúc truy vấn.

Ví dụ xử lý trong một hàm:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class RealPathLookup {
    static Path resolveExisting(Path input) throws IOException {
        try {
            return input.toRealPath();
        } catch (NoSuchFileException ex) {
            throw new IOException("Đường dẫn không tồn tại: " + input, ex);
        }
    }
}
~~~

Đây là **lớp Java có thể biên dịch** nhưng không có `main()`; import `Files` trong ví dụ chỉ minh họa ngữ cảnh `java.nio.file` và không cần cho thân hàm.

**Đừng bắt mọi `IOException` rồi tùy tiện dùng `toAbsolutePath()` làm phương án thay thế** nếu ứng dụng cần xác nhận file tồn tại: cách fallback đó thay đổi hợp đồng từ “đối tượng có thật” thành “đường dẫn có dạng tuyệt đối”, có thể che giấu lỗi quyền truy cập hoặc liên kết hỏng. Nếu ứng dụng chủ đích cho phép đường dẫn chưa tồn tại, hãy thể hiện như một nhánh nghiệp vụ rõ ràng.

Không được suy ra `Files.exists(path) == false` chắc chắn nghĩa là file vắng mặt: Java có thể không xác định được do lỗi hoặc quyền truy cập. Với tác vụ thực, xử lý lỗi khi **mở/đọc/ghi** mới là bước quan trọng.

## 10. Đường dẫn thực và an toàn ứng dụng

Một tình huống dễ gặp là ứng dụng chỉ được truy cập file trong thư mục `base`, nhưng nhận đường dẫn tương đối từ người dùng. Một phép kiểm tra cú pháp:

~~~java
Path candidate = base.resolve(userSupplied).normalize();
if (!candidate.startsWith(base.normalize())) {
    throw new IllegalArgumentException("Outside allowed directory");
}
~~~

Đây là **đoạn minh họa kiểm tra lexical** (cần có `base` và `userSupplied` kiểu `Path`), **không phải cơ chế bảo vệ filesystem đầy đủ**. Nếu `base` hoặc `candidate` có symbolic link, một đường dẫn nhìn như nằm dưới `base` có thể dẫn ra ngoài.

Nếu đối tượng **đã tồn tại**, việc so sánh các real path có thể phát hiện nhiều tình huống symlink làm thay đổi vị trí:

~~~java
Path realBase = base.toRealPath();
Path realTarget = candidate.toRealPath();
if (!realTarget.startsWith(realBase)) {
    throw new SecurityException("File outside permitted root");
}
~~~

Đoạn code trên là **minh họa**, chỉ áp dụng khi các đường dẫn hiện tồn tại và có xử lý `IOException`. `Path.startsWith(Path)` kiểm tra theo các thành phần đường dẫn với quy tắc provider, **không phải phép kiểm tra tiền tố chuỗi ký tự**.

Nhưng cần hiểu giới hạn: giữa bước `toRealPath` và bước mở tệp, một bên khác có thể thay symlink hoặc thay file, tạo tình huống **time-of-check to time-of-use (TOCTOU)**. Vì vậy, **không được tuyên bố `toRealPath` tự nó bảo vệ tuyệt đối trước path traversal hoặc symlink attack**. Tác vụ bảo mật nhạy cảm cần các API/thao tác mở theo thư mục và kiểm soát liên kết phù hợp nền tảng (chẳng hạn `SecureDirectoryStream` khi provider hỗ trợ), cùng chính sách quyền tệp thích hợp.

Đối với một file output **chưa tồn tại**, `toRealPath()` trên chính file đó thường thất bại. Nếu cần định tuyến output an toàn, hãy thiết kế dựa trên thư mục cha/handle được kiểm soát và thao tác tạo file thích hợp; đừng tạo một file “giả” chỉ để qua kiểm tra real path.

## 11. Những lỗi phổ biến cần tránh

| Nhầm lẫn | Vì sao sai? | Cách sửa |
|---|---|---|
| “`toAbsolutePath()` cho biết tệp tồn tại.” | Tạo `Path` tuyệt đối không cần file có thật. | Dùng API filesystem khi cần xác định file. |
| “`toAbsolutePath()` tự xóa `..`.” | Không thực hiện lexical normalization mặc định. | Dùng `normalize()` nếu thực sự muốn rút gọn cú pháp. |
| “`normalize()` cũng giống `toRealPath()`.” | Normalize không tra cứu filesystem, không giải quyết symlink. | Chọn đúng thao tác theo nhu cầu và hợp đồng. |
| “`toRealPath()` dùng cho file output chưa tạo.” | Yêu cầu đối tượng tồn tại theo hợp đồng. | Dùng absolute path để chuẩn bị nơi tạo, rồi tạo bằng Files API. |
| “Hai `toAbsolutePath()` trùng nhau chứng minh chúng là cùng file.” | Đường dẫn có thể thay đổi, hard link/symlink và provider có ngữ nghĩa riêng. | Cân nhắc `Files.isSameFile` khi cần kiểm tra file hiện tại. |
| “`toRealPath()` không theo symlink.” | Mặc định giải quyết symlink tới đích. | Dùng `NOFOLLOW_LINKS` khi yêu cầu không theo liên kết. |
| “`NOFOLLOW_LINKS` giống hệt `normalize()`.” | Quy tắc giữ nguyên đối tượng khi có `..` và symlink tinh vi hơn. | Đọc hợp đồng `toRealPath` và provider. |
| “Bắt `IOException` rồi dùng absolute path, coi như đã kiểm tra.” | Vô tình bỏ qua sai quyền truy cập hoặc file vắng mặt. | Tách rõ nghiệp vụ file tồn tại/chưa tồn tại. |
| “`toRealPath()` trả handle đã được khóa.” | Nó chỉ trả `Path`, file có thể thay đổi sau đó. | Dùng Files/Channel API để mở và kiểm soát vòng đời. |
| “Kiểm tra real path một lần đủ tránh race.” | Filesystem có thể thay đổi sau khi kiểm tra. | Dùng chiến lược mở/kiểm soát phù hợp yêu cầu bảo mật. |
| “Cùng một chuỗi path sẽ có cùng nghĩa trên mọi OS.” | Root, separator, case sensitivity và provider khác nhau. | Sử dụng `Path.of`, `resolve`, không tự ghép cú pháp hệ điều hành. |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Tệp `missing.txt` chưa tồn tại. Điều gì xảy ra khi gọi hai phương thức?

> `Path.of("missing.txt").toAbsolutePath()` vẫn có thể trả một đường dẫn tuyệt đối. `toRealPath()` cần xác định đối tượng tồn tại, nên sẽ thất bại với `IOException` trên trường hợp file không tồn tại.

**Câu 2.** Đường dẫn `/work/a/../b.txt` có gì khác khi xử lý bằng `toAbsolutePath()` và `toAbsolutePath().normalize()`?

> `toAbsolutePath()` giữ đường dẫn tuyệt đối như đầu vào; `normalize()` có thể rút gọn lexical thành `/work/b.txt`. Không phương thức nào trong hai phương thức này tự chứng thực rằng tệp tồn tại hoặc kiểm tra symlink thật.

**Câu 3.** Có một symlink `alias.txt` tới `/data/original.txt`. Khi nào `toRealPath()` và `toRealPath(NOFOLLOW_LINKS)` khác nhau?

> Chế độ mặc định giải quyết symlink để tìm đường dẫn thực của đích. Với `NOFOLLOW_LINKS`, API không theo symlink tới đích; đường dẫn kết quả tương ứng với việc giữ liên kết theo hợp đồng/provider.

**Câu 4.** Nếu tệp đã tồn tại nhưng ứng dụng không đủ quyền để xác định đường dẫn thực, liệu `toAbsolutePath()` trả thành công có chứng minh đủ quyền truy cập không?

> Không. Đường dẫn tuyệt đối chỉ nói về dạng biểu diễn. `toRealPath` có thể ném `IOException` do quyền hoặc lỗi filesystem; thao tác đọc/ghi vẫn cần kiểm tra và xử lý lỗi riêng.

**Câu 5.** Có nên thay mọi chỗ dùng `toRealPath()` bằng `normalize()` để tránh phải bắt `IOException`?

> Không. Đây là hai yêu cầu khác nhau: `normalize()` chỉ xử lý cú pháp; `toRealPath()` cần đối chiếu filesystem và có thể giải quyết symlink. Việc bỏ exception đồng nghĩa bỏ mất phần xác minh cần thiết của nghiệp vụ.

**Câu 6.** Tại sao kiểm tra `target.toRealPath().startsWith(base.toRealPath())` có ích nhưng vẫn chưa phải hàng rào bảo mật hoàn chỉnh?

> Nó có thể phát hiện target hiện trỏ ra ngoài thư mục qua symlink, nhưng filesystem có thể bị thay đổi **sau khi kiểm tra**. Cần chiến lược mở file và quyền hệ thống phù hợp nếu cần bảo đảm chống tấn công.

## Ghi nhớ

- **`toAbsolutePath()`:** có **đường dẫn tuyệt đối**, không yêu cầu file tồn tại, không tự normalize hay giải quyết symlink.
- **`toAbsolutePath().normalize()`:** có **đường dẫn tuyệt đối rút gọn cú pháp**, vẫn không xác minh file thực.
- **`toRealPath()`:** lấy **đường dẫn thực của file/directory đang tồn tại**, thường bỏ phần dư thừa và **giải quyết symbolic link mặc định**; có thể ném `IOException`.
- **`toRealPath(LinkOption.NOFOLLOW_LINKS)`:** lấy real path **mà không theo symbolic link**, với quy tắc provider phù hợp.
- **`toRealPath` không khóa file và không loại bỏ mọi nguy cơ thay đổi đồng thời**.

Câu hỏi quyết định trước khi chọn API là: **“Tôi chỉ cần một cách biểu diễn đường dẫn đầy đủ, hay cần xác định đối tượng thật hiện tồn tại trong filesystem?”** Trả lời được câu đó giúp sử dụng `Path` đúng ở cả I/O thông thường lẫn xử lý đường dẫn có liên kết.

**Tài liệu tham khảo:** [Java SE 17 — `java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html), [`java.nio.file.LinkOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html), [`java.nio.file.Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).