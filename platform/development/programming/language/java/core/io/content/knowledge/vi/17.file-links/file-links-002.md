# Tạo, đọc và nhận biết symbolic link trong Java NIO.2

## 1. Symbolic link là gì?

**Symbolic link (liên kết tượng trưng, symlink)** là một mục trong hệ thống tệp chứa đường dẫn tham chiếu đến một tệp hoặc thư mục khác. Khi chương trình mở liên kết để đọc nội dung, hệ điều hành thường phân giải liên kết và truy cập đối tượng đích. Một liên kết có thể trỏ tới tệp, thư mục hoặc tới một liên kết khác.

Ví dụ, thư mục `docs` chứa `guide.txt` và `latest.txt` là symlink có nội dung đích `guide.txt`:

~~~text
docs/
├── guide.txt
└── latest.txt -> guide.txt
~~~

Ở ví dụ này, `latest.txt` vẫn là một mục riêng trong hệ thống tệp. Nó không chứa bản sao nội dung của `guide.txt`. Xóa `latest.txt` thông thường chỉ xóa liên kết; đổi tên hoặc xóa `guide.txt` có thể khiến liên kết không còn tìm thấy đích.

Phân biệt ngắn gọn:

| Loại | Đặc điểm |
| --- | --- |
| Tệp thông thường | Chứa dữ liệu thực tế của tệp. |
| Symbolic link | Chứa đường dẫn đến đối tượng đích; có thể trỏ qua thư mục hoặc tới đích chưa tồn tại. |
| Hard link | Là một tên khác tham chiếu cùng đối tượng tệp trên hệ thống tệp hỗ trợ; không lưu một đường dẫn đích theo cách symlink làm. |

Các API hiện đại để làm việc với symbolic link thuộc `java.nio.file`, chủ yếu là `Path`, `Files` và `LinkOption`.

## 2. Ba thao tác cốt lõi

| Mục đích | API | Kết quả và điểm cần nhớ |
| --- | --- | --- |
| Tạo liên kết | `Files.createSymbolicLink(link, target)` | Tạo mục `link` chứa đường dẫn `target`. Không tạo bản sao dữ liệu. |
| Đọc đường dẫn đích được lưu | `Files.readSymbolicLink(link)` | Trả về một `Path`; không đọc nội dung tệp đích và không tự chuyển thành đường dẫn tuyệt đối. |
| Nhận biết một đường dẫn có phải symlink | `Files.isSymbolicLink(path)` | Trả về `true` khi chính mục được chỉ ra là symbolic link, kể cả khi đích đã mất. |

Các tham số `link` và `target` đều là `Path`. Với đường dẫn đích tương đối, việc phân giải được hiểu **tương đối từ thư mục cha của chính liên kết**, không phải nhất thiết từ thư mục làm việc hiện tại.

Ví dụ:

~~~java
Path link = Path.of("/app/aliases/current.txt");
Path target = Path.of("../data/report.txt");
Files.createSymbolicLink(link, target);
~~~

Liên kết tại `/app/aliases/current.txt` tham chiếu `/app/data/report.txt` khi được phân giải. Ví dụ đường dẫn kiểu Unix này minh họa quy tắc; trên Windows dùng đường dẫn phù hợp với hệ thống tệp đang chạy.

**Quan trọng:** `Files.createSymbolicLink` không bắt buộc đối tượng đích đã tồn tại tại thời điểm tạo. Vì vậy, tạo thành công chưa bảo đảm đọc nội dung qua liên kết sẽ thành công.

## 3. Ví dụ hoàn chỉnh: tạo, đọc và nhận biết liên kết

Lưu mã dưới đây thành `SymbolicLinkDemo.java`. Chương trình tạo thư mục tạm, ghi tệp thật, tạo liên kết tương đối, kiểm tra trạng thái rồi xóa tệp thật để quan sát một **dangling/broken symbolic link**. Khối `finally` dọn các mục được ví dụ tạo ra.

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class SymbolicLinkDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("symbolic-link-demo-");
        Path realFile = dir.resolve("data.txt");
        Path link = dir.resolve("shortcut.txt");

        try {
            Files.writeString(realFile, "Java NIO");

            // "data.txt" được phân giải từ thư mục chứa shortcut.txt.
            Files.createSymbolicLink(link, Path.of("data.txt"));

            System.out.println("isSymbolicLink=" + Files.isSymbolicLink(link));
            System.out.println("storedTarget=" + Files.readSymbolicLink(link));
            System.out.println("content=" + Files.readString(link));
            System.out.println("existsFollow=" + Files.exists(link));
            System.out.println("existsNoFollow=" +
                    Files.exists(link, LinkOption.NOFOLLOW_LINKS));

            // Xóa đích, nhưng vẫn giữ mục symbolic link.
            Files.delete(realFile);
            System.out.println("afterDeleteIsLink=" + Files.isSymbolicLink(link));
            System.out.println("afterDeleteFollow=" + Files.exists(link));
            System.out.println("afterDeleteNoFollow=" +
                    Files.exists(link, LinkOption.NOFOLLOW_LINKS));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(realFile);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac SymbolicLinkDemo.java
java SymbolicLinkDemo
~~~

Khi hệ thống tệp và quyền người dùng cho phép tạo symbolic link, kết quả là:

~~~text
isSymbolicLink=true
storedTarget=data.txt
content=Java NIO
existsFollow=true
existsNoFollow=true
afterDeleteIsLink=true
afterDeleteFollow=false
afterDeleteNoFollow=true
~~~

Giải thích từng nhóm kết quả:

1. `isSymbolicLink=true`: bản thân `shortcut.txt` là liên kết tượng trưng.
2. `storedTarget=data.txt`: `readSymbolicLink` trả về đường dẫn tương đối **đã lưu**. Nó không trả về nội dung `Java NIO`.
3. `content=Java NIO`: `Files.readString(link)` mặc định đi theo liên kết để đọc dữ liệu của `data.txt`.
4. Trước khi xóa đích, kiểm tra `Files.exists` cả khi đi theo và không đi theo liên kết đều trả về `true`.
5. Sau khi xóa đích, liên kết vẫn tồn tại nên `isSymbolicLink` và `exists(..., NOFOLLOW_LINKS)` vẫn là `true`. Ngược lại, `exists(link)` mặc định đi theo đích, không tìm thấy nó và trả về `false`.

Nếu môi trường không hỗ trợ symbolic link hoặc không có quyền tạo, lệnh `createSymbolicLink` có thể ném ngoại lệ; đó là hạn chế của môi trường, không phải một biến thể của kết quả hiển thị ở trên.

## 4. Đường dẫn tương đối, tuyệt đối và đường dẫn thực

`Files.readSymbolicLink(link)` đọc **đường dẫn đích được ghi trong liên kết**, có thể là tương đối hoặc tuyệt đối. Nếu cần xác định đường dẫn mà một target tương đối ám chỉ theo vị trí liên kết, hãy xử lý rõ ràng:

~~~java
Path storedTarget = Files.readSymbolicLink(link);
Path referencedPath = storedTarget.isAbsolute()
        ? storedTarget
        : link.getParent().resolve(storedTarget).normalize();
~~~

Đây là phép **xây dựng/chuẩn hóa đường dẫn theo cú pháp**. `normalize()` xử lý các thành phần như `.` và `..`; nó không bảo đảm đối tượng tồn tại và không thay thế việc kiểm tra liên kết hoặc quyền truy cập thực tế.

Nếu muốn phân giải đến một đối tượng hiện có:

~~~java
Path actualPath = link.toRealPath();
~~~

`toRealPath()` mặc định phân giải symbolic link và yêu cầu đường dẫn có thể được truy cập, nên có thể ném `IOException` khi liên kết hỏng, mục đích không tồn tại hoặc quyền truy cập không cho phép. Truyền `LinkOption.NOFOLLOW_LINKS` làm thay đổi việc theo liên kết; không dùng tùy tiện nếu mục đích là tìm tệp đích thực sự.

Nên chọn target tương đối khi một nhóm tệp sẽ được di chuyển cùng nhau mà vẫn muốn quan hệ tham chiếu giữ nguyên. Target tuyệt đối thuận tiện khi vị trí đích được cố định, nhưng dễ hỏng khi di chuyển dự án sang máy khác.

## 5. Đi theo liên kết hay kiểm tra chính liên kết?

Đây là khác biệt dễ gây lỗi nhất trong các thao tác I/O.

| Biểu thức | Khi `link` trỏ tới tệp đang tồn tại | Khi `link` là symlink nhưng đích đã mất |
| --- | --- | --- |
| `Files.isSymbolicLink(link)` | `true` | `true` |
| `Files.exists(link)` | `true` | `false` trong trường hợp thông thường |
| `Files.exists(link, NOFOLLOW_LINKS)` | `true` | `true` nếu chính liên kết vẫn tồn tại và có thể kiểm tra |
| `Files.isRegularFile(link)` | `true` nếu đích là tệp thường | `false` |
| `Files.isRegularFile(link, NOFOLLOW_LINKS)` | `false` vì mục được kiểm tra là liên kết | `false` |
| `Files.readSymbolicLink(link)` | Trả đường dẫn được lưu | Vẫn trả đường dẫn được lưu |
| `Files.readString(link)` | Đọc nội dung đích | Thường ném `NoSuchFileException` |

`LinkOption.NOFOLLOW_LINKS` có nghĩa là thao tác hỗ trợ tùy chọn này sẽ xem chính liên kết thay vì tự đi theo nó. Nó không phải một cấu hình toàn cục của `Files`; từng phương thức có tập tham số và hành vi riêng.

Khi cần đọc metadata về bản thân liên kết:

~~~java
import java.nio.file.attribute.BasicFileAttributes;

BasicFileAttributes attrs = Files.readAttributes(
        link, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
System.out.println(attrs.isSymbolicLink());
~~~

Đoạn mã này là **mảnh minh họa**, sử dụng biến `link` đã có trong chương trình; nếu liên kết không tồn tại hoặc không thể đọc metadata, `readAttributes` có thể ném `IOException`.

Chú ý: `Files.exists(path) == false` **không tự chứng minh** mục hoàn toàn không có; một số lỗi I/O hoặc quyền truy cập cũng khiến API không xác định được sự tồn tại. Khi cần xử lý lỗi chính xác, thực hiện thao tác mong muốn và bắt ngoại lệ phù hợp thay vì phụ thuộc hoàn toàn vào một phép kiểm tra tồn tại trước đó.

## 6. Lỗi thường gặp và cách xử lý

- **Dùng đường dẫn tương đối sai gốc:** `Path.of("data.txt")` lưu target tương đối với thư mục chứa link. Nếu link nằm trong thư mục khác, phải chọn số lượng `..` hoặc cấu trúc thư mục phù hợp.
- **Nhầm đọc symlink với đọc nội dung:** `Files.readSymbolicLink` trả `Path` được lưu; `Files.readString`, `Files.newInputStream` và các thao tác mở tệp thông thường có thể đi theo liên kết.
- **Dùng `Files.exists(link)` để khẳng định link không còn:** một broken link vẫn còn mục liên kết. Kiểm tra `Files.isSymbolicLink(link)` hoặc `Files.exists(link, NOFOLLOW_LINKS)` khi muốn hỏi về chính mục đó.
- **Tạo link tại tên đã tồn tại:** `Files.createSymbolicLink` không ghi đè đường dẫn `link` có sẵn; thường ném `FileAlreadyExistsException`. Hãy chọn tên khác hoặc xử lý trạng thái hiện có có chủ đích.
- **Giả định mọi môi trường hỗ trợ:** hệ thống tệp, quyền truy cập, cấu hình Windows và chính sách bảo mật có thể chặn tạo liên kết; `UnsupportedOperationException` hoặc `IOException` (ví dụ `FileSystemException`) có thể xảy ra. Trên một số cấu hình Windows, tạo symlink cần quyền thích hợp hoặc Developer Mode; hãy kiểm tra chính sách máy thực tế.
- **Gọi `readSymbolicLink` trên tệp thường:** phương thức có thể ném `NotLinkException`. Kiểm tra loại mục trước chỉ giúp giao diện rõ ràng hơn, nhưng không loại bỏ khả năng thay đổi đồng thời giữa kiểm tra và thao tác.
- **Vô tình xóa hoặc sao chép sai đối tượng:** `Files.delete(link)` xóa chính mục symlink, không xóa đích; `Files.copy(link, destination)` mặc định đi theo link để sao chép đối tượng đích, còn dùng `NOFOLLOW_LINKS` thì yêu cầu sao chép chính liên kết (nếu provider hỗ trợ). `Files.move` khi nguồn là symlink di chuyển mục liên kết.
- **Quên xử lý liên kết vòng:** khi duyệt cây bằng `Files.walkFileTree`, mặc định không đi theo symlink; bật `FileVisitOption.FOLLOW_LINKS` có thể gặp vòng liên kết và `FileSystemLoopException`. Chỉ bật khi thực sự cần duyệt theo đích.

## 7. Lưu ý an toàn khi thao tác trên đường dẫn không tin cậy

Symbolic link có thể hướng một thao tác ghi/đọc đến vị trí ngoài thư mục bạn dự định xử lý. Nếu ứng dụng nhận tên tệp từ người dùng hoặc làm việc trong thư mục có thể bị tiến trình khác sửa, cần thiết kế quy tắc đường dẫn và quyền truy cập rõ ràng. Chỉ ghép chuỗi đường dẫn hoặc gọi `normalize()` không đủ để bảo đảm đường dẫn cuối vẫn nằm trong vùng cho phép, vì symlink có thể thay đổi điểm đến thực tế.

Đặc biệt, chuỗi thao tác “kiểm tra không phải symlink → mở/ghi tệp” có thể gặp **race condition** nếu một tác nhân khác thay mục đó giữa hai bước (TOCTOU). Với dữ liệu nhạy cảm, cân nhắc các thao tác gắn với thư mục an toàn như `SecureDirectoryStream` khi provider hỗ trợ, phân quyền hệ thống tệp và cơ chế mở tệp phù hợp. Không coi một lần gọi `isSymbolicLink` là biện pháp bảo vệ hoàn chỉnh.

## 8. Tự kiểm tra kiến thức

1. Nếu `docs/current.txt` lưu target `../backup/report.txt`, đích được diễn giải tương đối từ thư mục nào? **Từ thư mục `docs` chứa `current.txt`**, nên đường dẫn tương ứng theo cú pháp là `backup/report.txt` ở cùng cấp với `docs`.
2. Một symlink còn trên đĩa nhưng đích đã bị xóa: API nào nhận biết vẫn có liên kết? **`Files.isSymbolicLink(link)`** hoặc **`Files.exists(link, LinkOption.NOFOLLOW_LINKS)`** khi có thể truy cập metadata.
3. `Files.readSymbolicLink(link)` có đọc nội dung tệp đích không? **Không.** Nó trả về `Path` của target được lưu trong liên kết.
4. Muốn đọc nội dung qua link đang hợp lệ thì dùng gì? **Một thao tác đọc nội dung như `Files.readString(link)`**; theo mặc định thao tác này sẽ đi theo liên kết đến đích.
5. Tại sao cùng một link, `Files.exists(link)` có thể là `false` nhưng `Files.exists(link, NOFOLLOW_LINKS)` là `true`? **Vì phép kiểm tra thứ nhất đi theo đích đã mất, còn phép thứ hai kiểm tra bản thân mục liên kết còn tồn tại.**

**Ghi nhớ:** `createSymbolicLink` tạo đường dẫn tham chiếu, `readSymbolicLink` đọc target được lưu, `isSymbolicLink` nhận diện mục liên kết. Khi kiểm tra sự tồn tại hoặc metadata, hãy quyết định rõ bạn đang quan tâm **bản thân liên kết** hay **đối tượng đích**.