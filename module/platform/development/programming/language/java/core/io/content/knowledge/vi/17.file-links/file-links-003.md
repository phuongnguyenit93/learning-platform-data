# Đường dẫn đích tương đối của symbolic link trong Java NIO.2

## 1. Mục tiêu và bối cảnh

**Symbolic link (liên kết tượng trưng, hay symlink)** là một mục trong hệ thống tệp chứa đường dẫn trỏ đến tệp hoặc thư mục khác. Khi chương trình mở symlink để đọc nội dung, hệ điều hành thường lần theo đường dẫn đó đến đối tượng đích.

Một symlink có thể lưu **đường dẫn tuyệt đối** hoặc **đường dẫn tương đối**. Bài này tập trung vào câu hỏi: *Nếu đích là một đường dẫn tương đối, nó được hiểu tương đối với đâu, và Java NIO.2 tạo/đọc/xử lý đường dẫn đó như thế nào?*

Sau bài học, bạn có thể:

- Xác định đúng đích của một symlink chứa `..` hoặc các thành phần đường dẫn tương đối.
- Tạo và kiểm tra symlink bằng `java.nio.file.Files` và `Path`.
- Phân biệt đường dẫn **được lưu trong symlink**, đường dẫn **đã ghép với thư mục chứa symlink**, và đường dẫn **thực** trên hệ thống tệp.
- Hiểu vì sao di chuyển symlink có thể làm nó mất đích, và xử lý các trường hợp symlink bị đứt.

## 2. Quy tắc cốt lõi: tương đối với thư mục chứa chính symlink

Giả sử có cây thư mục:

~~~text
workspace/
├── data/
│   └── report.txt
└── links/
    └── latest.txt -> ../data/report.txt
~~~

`latest.txt` là symlink nằm trong `workspace/links/`. Bên trong nó lưu chuỗi đường dẫn tương đối `../data/report.txt`.

Hệ điều hành diễn giải mục tiêu theo quy tắc:

~~~text
thư_mục_chứa_symlink / đường_dẫn_đích_đã_lưu
= workspace/links/../data/report.txt
= workspace/data/report.txt
~~~

**Điểm quyết định:** Đích tương đối được giải quyết dựa trên **thư mục cha của symlink** (`workspace/links/`), **không dựa trên thư mục làm việc hiện tại** (`user.dir`) của chương trình Java. Đích không được diễn giải tương đối với chính `latest.txt` như thể symlink là một thư mục.

Cần phân biệt hai đường dẫn độc lập:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Đường dẫn đến symlink | `workspace/links/latest.txt` | Xác định *mục liên kết* được tạo hoặc truy cập |
| Đường dẫn đích ghi trong symlink | `../data/report.txt` | Xác định *đối tượng đích* tương đối với thư mục chứa liên kết |
| Đường dẫn sau khi ghép và chuẩn hóa | `workspace/data/report.txt` | Vị trí dự kiến sau khi xử lý `..`, chưa đồng nghĩa với việc tệp chắc chắn tồn tại |

Đường dẫn **đến symlink** có thể là tuyệt đối dù **đường dẫn đích** vẫn tương đối. Một symlink cũng có thể trỏ đến thư mục thay vì tệp; cùng quy tắc về thư mục cha được áp dụng.

## 3. Tạo symlink với đường dẫn đích tương đối bằng Java 17+

Trong Java NIO.2, lời gọi chính là:

~~~java
Path link = linksDirectory.resolve("latest.txt");
Path relativeTarget = Path.of("..", "data", "report.txt");
Files.createSymbolicLink(link, relativeTarget);
~~~

- Tham số `link` là nơi tạo **mục symlink**.
- Tham số `relativeTarget` là đường dẫn **được lưu làm đích**. Vì `relativeTarget.isAbsolute()` bằng `false`, đích sẽ được hiểu tương đối với thư mục chứa `link`.
- `Path.of("..", "data", "report.txt")` dùng cách ghép tên theo hệ thống tệp hiện hành, tránh tự viết dấu phân cách theo một hệ điều hành cố định.
- `Files.createSymbolicLink` không tự sửa đường dẫn tương đối thành tuyệt đối. Nó có thể tạo liên kết đến đích chưa tồn tại trên các hệ thống hỗ trợ; không được dùng việc tạo thành công để kết luận rằng đích tồn tại.

### Ví dụ hoàn chỉnh, chạy độc lập

Lưu mã dưới tên `RelativeSymlinkDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.FileSystems;

public class RelativeSymlinkDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("relative-symlink-");
        Path dataDir = root.resolve("data");
        Path linksDir = root.resolve("links");
        Path targetFile = dataDir.resolve("report.txt");
        Path link = linksDir.resolve("latest.txt");

        try {
            Files.createDirectories(dataDir);
            Files.createDirectories(linksDir);
            Files.writeString(targetFile, "Xin chào NIO.2", StandardCharsets.UTF_8);

            // Đường dẫn đích được lưu tương đối với linksDir.
            Path relativeTarget = Path.of("..", "data", "report.txt");
            Files.createSymbolicLink(link, relativeTarget);

            // Đọc đúng đường dẫn đích đã lưu, chưa lần theo symlink.
            Path storedTarget = Files.readSymbolicLink(link);

            // Ghép với thư mục cha của symlink để suy ra vị trí đích.
            Path resolved = link.getParent().resolve(storedTarget).normalize();

            String portableTarget = storedTarget.toString()
                    .replace(FileSystems.getDefault().getSeparator(), "/");

            System.out.println("Stored target: " + portableTarget);
            System.out.println("Target is relative: " + !storedTarget.isAbsolute());
            System.out.println("Resolved matches file: " + resolved.equals(targetFile));
            System.out.println("Content through link: "
                    + Files.readString(link, StandardCharsets.UTF_8));
            System.out.println("Is symbolic link: " + Files.isSymbolicLink(link));
        } finally {
            // Xóa liên kết, rồi tệp đích và các thư mục đã tạo.
            Files.deleteIfExists(link);
            Files.deleteIfExists(targetFile);
            Files.deleteIfExists(linksDir);
            Files.deleteIfExists(dataDir);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp Java:

~~~bash
javac -encoding UTF-8 RelativeSymlinkDemo.java
java RelativeSymlinkDemo
~~~

Với hệ thống tệp hỗ trợ symlink và tài khoản có quyền tạo symlink, stdout là:

~~~text
Stored target: ../data/report.txt
Target is relative: true
Resolved matches file: true
Content through link: Xin chào NIO.2
Is symbolic link: true
~~~

**Giải thích kết quả:**

1. `Files.readSymbolicLink(link)` trả về `Path` biểu diễn đích được lưu (`../data/report.txt`), không đọc nội dung `report.txt` và không tự chuyển thành đường dẫn tuyệt đối.
2. `link.getParent().resolve(storedTarget).normalize()` ghép đích tương đối với `linksDir` và rút gọn `links/..` về `data/report.txt`. Ví dụ dùng một cây tạm đã biết nên phép so sánh `equals` với `targetFile` cho `true`.
3. `Files.readString(link, UTF_8)` truy cập nội dung qua symlink; hệ thống tệp lần theo liên kết tới `report.txt`.
4. `Files.isSymbolicLink(link)` kiểm tra bản thân mục `latest.txt` có phải symlink, không xét file đích thuộc loại nào.
5. Khối `finally` xóa riêng liên kết trước khi xóa file đích. `Files.deleteIfExists(link)` xóa symlink, **không xóa nội dung file đích** mà liên kết chỉ tới.

Ví dụ không giả định tên thư mục tạm, vì `Files.createTempDirectory` sinh tên khác nhau mỗi lần chạy. Chạy trên một số bản Windows cần bật Developer Mode hoặc quyền phù hợp để tạo symlink; hệ thống tệp không hỗ trợ chức năng này cũng có thể từ chối lời gọi `createSymbolicLink`.

## 4. Đọc đường dẫn đích và xác định vị trí được tham chiếu

Có ba thao tác dễ bị nhầm:

~~~java
Path stored = Files.readSymbolicLink(link);
Path lexicalDestination = link.getParent().resolve(stored).normalize();
Path realDestination = link.toRealPath();
~~~

| Thao tác | Kết quả | Có cần đích tồn tại? |
| --- | --- | --- |
| `Files.readSymbolicLink(link)` | Đường dẫn được **lưu trong symlink**, có thể tương đối | Không cần đích tồn tại, nhưng bản thân symlink phải tồn tại |
| `link.getParent().resolve(stored).normalize()` | Đường dẫn suy ra bằng phép ghép và rút gọn từ vựng `.`/`..` | Không |
| `link.toRealPath()` | Đường dẫn thực được phân giải theo hệ thống tệp, mặc định lần theo các symlink | Có, nên liên kết bị đứt sẽ gây lỗi |

`normalize()` xử lý thành phần tên đường dẫn theo cú pháp, **không truy cập hệ thống tệp**; nó không xác nhận đối tượng tồn tại, không tự giải quyết các symlink trung gian và không chứng minh hai đường dẫn trỏ cùng đối tượng. Khi cần xác định hai đường dẫn thực sự cùng file đang tồn tại, có thể dùng `Files.isSameFile(path1, path2)`; phương thức này truy cập hệ thống tệp và có thể phát sinh `IOException`.

**Lưu ý cho đường dẫn `link` tương đối:** `link.getParent()` có thể trả `null`, ví dụ `Path.of("alias.txt")`. Khi đó cần xác định vị trí tuyệt đối của liên kết trước khi lấy thư mục cha:

~~~java
Path absoluteLink = link.toAbsolutePath().normalize();
Path stored = Files.readSymbolicLink(link);
Path destination = absoluteLink.getParent().resolve(stored).normalize();
~~~

Ở đây `toAbsolutePath()` dùng thư mục làm việc để xác định **vị trí của chính symlink tương đối**. Sau khi đã xác định thư mục cha đó, **đường dẫn đích được lưu** vẫn được diễn giải tương đối với thư mục cha của symlink. `toAbsolutePath()` cũng không xác minh đích tồn tại.

## 5. Symlink bị đứt (dangling/broken symlink)

Một symlink bị đứt khi mục liên kết vẫn tồn tại nhưng đích được tham chiếu không thể tìm thấy (ví dụ file đích bị xóa, đổi tên hoặc liên kết bị chuyển sang thư mục khác).

Ví dụ, tại `workspace/links/latest.txt` vẫn lưu `../data/report.txt` nhưng `workspace/data/report.txt` đã bị xóa:

- `Files.isSymbolicLink(link)` → `true`: symlink còn tồn tại.
- `Files.readSymbolicLink(link)` → đường dẫn tương đối đã lưu: vẫn đọc được.
- `Files.exists(link)` → thông thường `false`: mặc định phép kiểm tra đi theo symlink để tìm đích.
- `Files.exists(link, LinkOption.NOFOLLOW_LINKS)` → `true`: kiểm tra chính mục symlink, không lần theo đích.
- `Files.readString(link)` hoặc `link.toRealPath()` → phát sinh `IOException`, thường là `NoSuchFileException`, nếu đích không tồn tại.

Trường hợp quyền truy cập bị từ chối hoặc trạng thái không thể xác định, `Files.exists` cũng có thể trả `false`; không nên hiểu `false` luôn chắc chắn là “không có file”.

Khi cần kiểm tra chính liên kết, sử dụng `LinkOption.NOFOLLOW_LINKS`. Ví dụ:

~~~java
import java.nio.file.LinkOption;

// link trỏ đến symlink cần kiểm tra.
boolean linkEntryExists = Files.exists(link, LinkOption.NOFOLLOW_LINKS);
boolean destinationAccessible = Files.exists(link);
boolean isLink = Files.isSymbolicLink(link);
~~~

Đây là **đoạn minh họa bổ sung**, dùng biến `link` và import `Files`, `Path` từ ví dụ đầy đủ phía trên; không phải chương trình Java độc lập.

## 6. Di chuyển thư mục: vì sao đích tương đối có thể còn đúng hoặc bị sai?

Đường dẫn đích tương đối đặc biệt hữu ích khi đóng gói hoặc sao chép **cả cấu trúc thư mục** mà giữ nguyên quan hệ giữa symlink và đích.

Ví dụ ban đầu:

~~~text
app/
├── data/report.txt
└── links/latest.txt -> ../data/report.txt
~~~

Nếu chuyển nguyên vẹn cây `app/` sang một nơi khác và **giữ symlink dưới dạng liên kết**, quan hệ `links/../data` không đổi, nên liên kết thường vẫn hoạt động mà không cần lưu đường dẫn tuyệt đối của máy cũ.

Ngược lại, nếu chỉ chuyển `app/links/latest.txt` vào `app/links/archive/latest.txt` mà giữ nguyên đích đã lưu `../data/report.txt`, vị trí được suy ra sẽ là:

~~~text
app/links/archive/../data/report.txt
= app/links/data/report.txt
~~~

Đó không còn là `app/data/report.txt`. Do vậy **di chuyển riêng symlink** có thể làm liên kết bị đứt. Muốn symlink tại `app/links/archive/latest.txt` trỏ về `app/data/report.txt` thì đường dẫn tương đối phù hợp là `../../data/report.txt`.

Khi sao chép bằng Java NIO.2, hành vi cũng cần được chỉ định rõ:

- `Files.copy(sourceLink, destination)` mặc định **theo symlink nguồn** và sao chép đối tượng được trỏ tới, nếu không có tùy chọn khác.
- `Files.copy(sourceLink, destination, LinkOption.NOFOLLOW_LINKS)` sao chép **bản thân liên kết** theo cơ chế được nhà cung cấp hệ thống tệp hỗ trợ; đường dẫn đích tương đối được giữ theo liên kết nên phải kiểm tra cấu trúc đích sau khi copy.
- `Files.move(sourceLink, destination)` di chuyển **mục liên kết**, không tự viết lại đường dẫn đích để giữ nguyên đối tượng mà symlink từng trỏ tới.

Đừng suy đoán rằng sao chép thư mục luôn bảo tồn symlink; điều đó phụ thuộc công cụ, tùy chọn và hệ thống tệp.

## 7. Các lỗi phổ biến và cách tránh

**Lỗi 1 — Hiểu đích tương đối theo `user.dir`.** Chương trình được chạy từ thư mục nào không quyết định cách hệ điều hành lần theo đích tương đối đã lưu. Hãy dùng thư mục chứa **symlink** làm điểm gốc để tính đích.

**Lỗi 2 — Ghép đích với bản thân đường dẫn symlink.** Viết `link.resolve(stored)` coi tên symlink như một thư mục và thường tạo ra đường dẫn sai. Cần dùng `link.getParent().resolve(stored)` (sau khi xử lý trường hợp `getParent() == null`).

**Lỗi 3 — Nhầm `normalize()` với giải quyết đường dẫn thực.** `normalize()` chỉ bỏ `.`/`..` về mặt cú pháp; muốn xác minh đường dẫn tồn tại và giải quyết symlink thực tế thì xét `toRealPath()`, `Files.isSameFile` và các lỗi I/O có thể xảy ra.

**Lỗi 4 — Dùng `Files.exists(link)` để quyết định có mục symlink hay không.** Một liên kết bị đứt thường cho `false`. Dùng `Files.exists(link, LinkOption.NOFOLLOW_LINKS)` để kiểm tra mục liên kết và `Files.isSymbolicLink(link)` để nhận biết loại mục.

**Lỗi 5 — Cho rằng tạo symlink đồng nghĩa đích tồn tại.** Một liên kết có thể được tạo trước file đích hoặc trở nên bị đứt sau đó. Đọc qua symlink vẫn có thể thất bại.

**Lỗi 6 — Cho rằng di chuyển symlink vẫn giữ đích cũ.** Đích tương đối không được tự động tính lại khi symlink đổi vị trí. Phải kiểm tra quan hệ thư mục và tạo lại liên kết với đích tương đối mới nếu cần.

**Lỗi 7 — Bỏ qua quyền và khác biệt hệ điều hành.** `Files.createSymbolicLink` có thể ném `UnsupportedOperationException` nếu provider không hỗ trợ, `FileAlreadyExistsException` nếu tên symlink đã tồn tại, hoặc `IOException` khi quyền/hệ thống tệp không cho phép. Một số cấu hình Windows yêu cầu Developer Mode hoặc đặc quyền phù hợp. Hãy kiểm tra môi trường và xử lý lỗi, thay vì giả định mọi máy đều cho phép tạo symlink.

**Lỗi 8 — Tin tưởng đường dẫn từ nguồn không đáng tin.** Đích tương đối có thể chứa `..` để đi ra ngoài thư mục dự kiến; các thành phần trung gian cũng có thể là symlink. Kiểm tra từ vựng với `normalize()` một mình **không đủ** để bảo đảm đường dẫn thực nằm trong thư mục an toàn. Khi làm việc với dữ liệu do người dùng kiểm soát, cần xác minh đối tượng thực, giới hạn quyền truy cập và xét cả rủi ro thay đổi hệ thống tệp giữa lúc kiểm tra và lúc sử dụng (TOCTOU).

## 8. Khi nào nên dùng đường dẫn đích tương đối?

Nên cân nhắc đích tương đối khi liên kết và tài nguyên đích thuộc cùng một cây triển khai, ví dụ `app/links/latest.txt -> ../data/report.txt`; cấu trúc có thể được chuyển sang máy hoặc đường dẫn gốc khác mà quan hệ nội bộ vẫn giữ nguyên.

Ngược lại, nếu symlink trỏ tới tài nguyên cố định nằm ngoài cây triển khai, đích tương đối có thể khiến cấu hình khó hiểu hoặc dễ đứt khi di chuyển các thư mục. Chọn đường dẫn tuyệt đối hoặc một cơ chế cấu hình phù hợp khi đó; cũng cần hiểu rằng đường dẫn tuyệt đối thường khó di chuyển giữa môi trường.

## 9. Câu hỏi tự kiểm tra

1. `project/bin/current -> ../config/settings.json` trỏ tới đâu? **Đáp án:** `project/config/settings.json`, vì điểm gốc là `project/bin/`.
2. Nếu chạy Java từ `/tmp` nhưng symlink vẫn ở `project/bin/`, đích tương đối có đổi không? **Không**; chỉ cách tìm symlink bằng đường dẫn tương đối trong chương trình có thể chịu ảnh hưởng của thư mục làm việc.
3. Vì sao `Files.readSymbolicLink(link)` có thể thành công trong khi `Files.readString(link)` thất bại? **Vì** thao tác đầu đọc đường dẫn được lưu trong symlink, còn thao tác sau phải truy cập đối tượng đích.
4. Sau khi chuyển symlink từ `project/bin/current` sang `project/bin/archive/current`, giữ nguyên `../config/settings.json` có chắc đúng không? **Không**; lúc này nó được hiểu từ `project/bin/archive/` và sẽ tìm `project/bin/config/settings.json`, trừ khi cấu trúc thư mục khác làm đường dẫn này hợp lệ.

**Ghi nhớ:** Với đích tương đối, hãy bắt đầu từ **thư mục chứa symlink**, ghép với **đường dẫn đã lưu**, và phân biệt phép tính đường dẫn theo cú pháp với việc hệ thống tệp thực sự lần theo liên kết.
