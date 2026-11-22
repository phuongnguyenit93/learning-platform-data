# Giới hạn phụ thuộc nền tảng và network file system khi theo dõi thay đổi bằng WatchService

## 1. Bối cảnh và mục tiêu

Java NIO.2 cung cấp `WatchService` (`java.nio.file.WatchService`) để ứng dụng theo dõi thay đổi ở những thư mục đã đăng ký. Các loại sự kiện tiêu chuẩn thường dùng là:

- `StandardWatchEventKinds.ENTRY_CREATE`: có mục mới xuất hiện trong thư mục.
- `StandardWatchEventKinds.ENTRY_DELETE`: một mục bị xóa hoặc không còn trong thư mục.
- `StandardWatchEventKinds.ENTRY_MODIFY`: một mục được ghi nhận đã thay đổi.
- `StandardWatchEventKinds.OVERFLOW`: bộ phát hiện đã bỏ lỡ một hoặc nhiều sự kiện do vượt khả năng ghi nhận/tích lũy.

Điểm quan trọng: **`WatchService` không phải một nhật ký thay đổi đầy đủ, bảo đảm chính xác và độc lập với hệ điều hành.** Khả năng phát hiện, độ trễ, thứ tự và mức độ gộp sự kiện phụ thuộc vào triển khai `FileSystemProvider`, cơ chế của hệ điều hành, file system và cả vị trí lưu dữ liệu. Với NFS, SMB hoặc các thư mục mạng được mount, ứng dụng đặc biệt cần kiểm tra khả năng phát hiện các sửa đổi thực hiện từ **máy khác**.

Bài này giúp bạn:

1. Hiểu hợp đồng API nào có thể tin cậy và phần nào phụ thuộc nền tảng.
2. Giải thích vì sao mạng chia sẻ tệp có thể không phát sự kiện đầy đủ hoặc kịp thời.
3. Xử lý `OVERFLOW`, sự kiện lặp, thay đổi tệp khi đang ghi và mất registration.
4. Kết hợp watch với **đối chiếu trạng thái (reconciliation)**, polling/snapshot và xử lý idempotent.
5. Thiết kế một ứng dụng Java 17+ chạy được và chọn giải pháp phù hợp yêu cầu nghiệp vụ.

## 2. Cơ chế cơ bản của WatchService

Một ứng dụng thường tạo service, đăng ký **thư mục**, lấy `WatchKey` và xử lý sự kiện:

~~~java
try (WatchService watcher = FileSystems.getDefault().newWatchService()) {
    WatchKey registration = directory.register(
            watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_MODIFY,
            StandardWatchEventKinds.ENTRY_DELETE);

    while (registration.isValid()) {
        WatchKey key = watcher.take(); // Chờ một key được báo có thay đổi.
        for (WatchEvent<?> event : key.pollEvents()) {
            System.out.println(event.kind() + ": " + event.context());
        }
        if (!key.reset()) {
            break; // Registration không còn hợp lệ.
        }
    }
}
~~~

Đây là **đoạn minh họa API**, không phải chương trình độc lập: cần các import trong `java.nio.file` và `directory` là một `Path` trỏ tới thư mục hiện có. Trong ứng dụng thật, thường quản lý nhiều key và không giả định key nhận về luôn là key của một thư mục duy nhất.

Các bước quan trọng:

- `directory.register(watcher, ...)` đăng ký thư mục; `WatchKey` đại diện cho registration.
- `watcher.take()` chặn đến khi có key sẵn sàng; `poll()` trả ngay hoặc `poll(timeout, unit)` chờ tối đa thời gian xác định.
- `key.pollEvents()` cung cấp các sự kiện đã ghi nhận của key. Với các sự kiện `ENTRY_*` tiêu chuẩn trên thư mục, `event.context()` thường là `Path` **tương đối với thư mục được theo dõi**.
- Phải gọi `key.reset()` sau khi xử lý; nếu bỏ qua, key có thể tiếp tục ở trạng thái signalled và không được đưa trở lại hàng đợi đúng cách.
- `reset() == false` báo key không còn hợp lệ: chẳng hạn registration đã bị hủy hoặc đối tượng không còn truy cập được. Cần xử lý tiếp theo chính sách ứng dụng.
- Khi service đóng, `take()`/`poll()` không thể tiếp tục sử dụng; chờ có thể kết thúc bằng `ClosedWatchServiceException`.

**Sự kiện mô tả điều được hệ thống ghi nhận tại một thời điểm; chúng không phải bảo đảm rằng tình trạng mục tệp còn y nguyên lúc handler xử lý.**

## 3. Phần nào phụ thuộc nền tảng?

Java định nghĩa các kiểu sự kiện và API để nhận sự kiện, nhưng cho phép provider sử dụng cơ chế giám sát native hoặc polling. Do đó, hai môi trường cùng chạy mã Java 17 có thể cho hành vi khác nhau:

| Khía cạnh | Điều cần hiểu |
| --- | --- |
| Thời gian nhận sự kiện | Có thể nhanh hoặc chậm tùy provider, tải hệ thống và cơ chế theo dõi |
| Số lần `ENTRY_MODIFY` | Một thay đổi logic có thể sinh một hoặc nhiều sự kiện; không giả định đúng một |
| Thứ tự sự kiện quan sát | Không xây quy trình nghiệp vụ dựa vào việc mọi môi trường giữ đúng một thứ tự tổng quát |
| Phát hiện tệp tồn tại rất ngắn | Hệ thống polling có thể không kịp thấy tệp vừa tạo rồi xóa |
| Giới hạn hàng đợi | Triển khai có thể giới hạn số sự kiện chờ; dùng `OVERFLOW` để báo mất sự kiện |
| Xử lý rename/move | Không có sự kiện rename tiêu chuẩn riêng cho mọi provider; thường phải xem như thay đổi trạng thái mục |
| Theo dõi cây thư mục | Đăng ký một thư mục không có nghĩa tự động theo dõi đệ quy mọi thư mục con |
| Quyền và tình trạng mount | Mất quyền, đường dẫn không truy cập được hoặc thay đổi mount có thể ảnh hưởng việc giám sát |
| Thư mục chia sẻ qua mạng | Thay đổi thực hiện ở máy khác **không được Java bảo đảm** sẽ phát hiện |

Trên một số nền tảng, provider tận dụng tính năng hệ điều hành; ở nơi không có hỗ trợ thích hợp, nó có thể dùng cách quét định kỳ. Không nên viết mã sản xuất phụ thuộc cứng vào tên một cơ chế cụ thể của Linux, Windows hay macOS trừ khi đã kiểm tra môi trường triển khai.

Ví dụ, việc tạo rồi sửa `config.yml` có thể phát `ENTRY_CREATE` tiếp theo là nhiều `ENTRY_MODIFY`; ở môi trường khác có thể quan sát ít sự kiện hơn. Tên file, thời điểm phát và số event **không phải hợp đồng chứng minh file đã được ghi xong**.

## 4. Network file system: điểm đặc biệt cần cảnh giác

### 4.1. NFS/SMB là gì trong bối cảnh này?

Một ứng dụng Java có thể truy cập thư mục `/mnt/share/data` hoặc `Z:\shared\data` bằng `Path` giống như đường dẫn cục bộ. Tuy nhiên, dữ liệu thực tế có thể nằm trên máy chủ khác, được truy cập qua giao thức chia sẻ tệp như NFS hoặc SMB.

**Việc `Files.exists(path)` và `Files.readString(path)` hoạt động không chứng minh `WatchService` sẽ nhìn thấy mọi thay đổi ở share.** API chỉ xác nhận hệ thống tệp cho phép các thao tác tệp tương ứng, không đưa ra cam kết riêng về khả năng giám sát sự kiện giữa các máy.

### 4.2. Thay đổi từ chính client và từ máy khác

Xét ba thành phần:

~~~text
Máy A: Java WatchService đăng ký /mnt/share/inbox
              |
              | mount NFS/SMB
              v
         Máy chủ lưu trữ
              ^
              | thay đổi tập tin
              |
Máy B: ứng dụng tạo report.csv
~~~

Có ít nhất hai tình huống phải thử nghiệm riêng:

1. **Máy A tự tạo/ghi tệp qua mount:** hệ điều hành hoặc provider của A có thể nhận biết một số sự kiện do chính client A gây ra. Mức độ hỗ trợ và cách báo vẫn phụ thuộc nền tảng.
2. **Máy B tạo/ghi/xóa tệp trên cùng share:** thông tin thay đổi có thể không được chuyển tới cơ chế watch của A. **Java không yêu cầu provider phải phát hiện thay đổi do máy khác thực hiện.**

Nếu A chỉ gọi `watcher.take()` và không có sự kiện, chương trình có thể ngủ mãi dù `report.csv` đã xuất hiện trên server. Nếu business flow cần xử lý file đó, chỉ dựa vào event là không đủ.

Không mặc định rằng một phiên bản Linux, Windows hay một bản NFS/SMB cụ thể luôn có cùng hành vi ở mọi cấu hình. Server, client cache, hệ thống mount, quyền và provider đều có thể làm kết quả khác nhau.

### 4.3. Cache và dữ liệu quan sát trễ

Network file system thường có cơ chế cache metadata hoặc nội dung để giảm round-trip. Vì thế, khi một client nhìn thấy sự kiện hoặc thực hiện `Files.size`, `Files.getLastModifiedTime` hay `Files.readAllBytes`, thời điểm dữ liệu/metadata trở nên quan sát được có thể khác với thời điểm máy khác vừa ghi.

Hệ quả:

- Một lần đọc trạng thái không phải ảnh chụp giao dịch của toàn bộ share.
- Một sự kiện `ENTRY_MODIFY` không chứng minh tác giả đã đóng file hoặc dữ liệu đã ổn định.
- Chỉ so sánh `lastModifiedTime` có thể bỏ sót thay đổi nếu độ phân giải timestamp thô, thời gian bị làm tròn hoặc hai lần ghi cho cùng metadata quan sát được.
- Tệp có thể bị thay thế giữa lúc kiểm tra và lúc mở; phải xử lý lỗi I/O và kiểm tra tính nhất quán theo yêu cầu nghiệp vụ.

Cách khắc phục hoàn toàn phụ thuộc nhu cầu: checksum, size/mtime, phiên bản hoặc manifest, giao thức “ghi tệp tạm rồi công bố” và cơ chế xác nhận của phía producer.

## 5. WatchService không phải cơ chế phát hiện chắc chắn mọi thay đổi

### 5.1. Sự kiện có thể bị gộp hoặc lặp

Nếu một ứng dụng ghi tệp theo nhiều lệnh, không được tính “số lần `ENTRY_MODIFY`” thành số lần hoàn chỉnh của file. Sự kiện có thể bị gộp hoặc xuất hiện nhiều lần cho một quá trình ghi.

**Mẫu tốt:** dùng sự kiện như lời nhắc “hãy kiểm tra mục này”, sau đó đọc trạng thái hiện tại. Handler cần idempotent: xử lý lại cùng một file không gây tác dụng phụ lặp ngoài ý muốn.

### 5.2. `OVERFLOW` là tín hiệu mất dữ liệu sự kiện

Hệ điều hành/provider có thể phát sự kiện nhanh hơn ứng dụng lấy ra. Nếu triển khai biết đã loại bỏ một số sự kiện, `WatchService` có thể đưa `OVERFLOW` vào danh sách sự kiện của key.

~~~java
for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        // Không thể biết đầy đủ file nào đã thay đổi.
        // Đánh dấu thư mục để quét lại trạng thái hiện tại.
        needsReconcile = true;
        continue;
    }

    Path changedName = (Path) event.context();
    Path changedPath = watchedDir.resolve(changedName);
    // Kiểm tra tình trạng thật của changedPath; tránh xử lý mù.
}
~~~

Đoạn này minh họa logic, cần `key`, `watchedDir`, `needsReconcile` đã được khai báo. Không giả định `OVERFLOW` có context là một tên file cụ thể. Khi có overflow, **không thể phục dựng đầy đủ lịch sử chỉ từ các event còn lại**; cần quét đối chiếu thư mục hoặc nguồn dữ liệu có lịch sử đáng tin.

### 5.3. Registration có thể không còn hợp lệ

Nếu thư mục bị xóa, quyền thay đổi hoặc file system mất khả năng truy cập, `WatchKey` có thể bị hủy. Hãy kiểm tra kết quả `reset()`:

~~~java
boolean valid = key.reset();
if (!valid) {
    // Ngừng tin tưởng registration cũ.
    // Ghi nhận lỗi và cân nhắc đăng ký lại khi thư mục sẵn sàng.
}
~~~

Cũng không nên giả định việc mount bị thay thế chắc chắn luôn làm key invalid ngay. Nếu một đường dẫn quan trọng trỏ tới mount mới nhưng watch cũ còn hiệu lực theo góc nhìn provider, ứng dụng vẫn cần cơ chế phát hiện/đối chiếu trạng thái ngoài event.

### 5.4. Đăng ký không hồi tố, không tự nhận snapshot

`WatchService` không tự phát toàn bộ các tệp đã có trong thư mục khi đăng ký. Nếu `inbox` đã có 1.000 file trước lúc ứng dụng chạy, không nên chờ `ENTRY_CREATE` để xử lý chúng.

Ngoài ra, trong khoảng thời gian thực hiện snapshot và đăng ký, một thay đổi có thể lọt qua nếu thứ tự không đúng. Đối với hệ thống cần phát hiện tối đa:

1. Đăng ký watch nếu provider hỗ trợ.
2. Quét trạng thái thực để lập baseline và nhận diện các file đã tồn tại.
3. Tiếp tục xử lý event và quét lại theo chu kỳ.
4. Chấp nhận event trùng rồi **lọc bằng idempotency/state**.

Cách này giảm khoảng trống phát hiện nhưng **không biến WatchService thành nhật ký sự kiện không mất dữ liệu**.

## 6. Ví dụ Java 17+ chạy độc lập: thấy sự khác nhau giữa event và trạng thái thực

Chương trình sau tạo một thư mục tạm, đăng ký theo dõi, tự tạo tệp `report.txt`, chờ tối đa hai giây để đọc event rồi kiểm tra trực tiếp sự tồn tại và nội dung file. Nó cố ý **không khẳng định luôn nhận được `ENTRY_CREATE`**: điều đó phụ thuộc provider và môi trường.

Lưu dưới tên **`WatchServicePlatformDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.concurrent.TimeUnit;

public class WatchServicePlatformDemo {

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watch-platform-");
        Path file = directory.resolve("report.txt");

        try {
            try (WatchService watcher =
                         FileSystems.getDefault().newWatchService()) {

                directory.register(
                        watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                // Tạo file sau khi đăng ký. Vẫn không giả định
                // provider phải phát một tập event cố định.
                Files.writeString(
                        file, "ready", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW);

                WatchKey key = watcher.poll(2, TimeUnit.SECONDS);
                boolean sawCreate = false;
                boolean sawOverflow = false;

                if (key != null) {
                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.OVERFLOW) {
                            sawOverflow = true;
                            continue;
                        }

                        Object context = event.context();
                        if (event.kind()
                                == StandardWatchEventKinds.ENTRY_CREATE
                                && file.getFileName().equals(context)) {
                            sawCreate = true;
                        }
                    }
                    if (!key.reset()) {
                        System.out.println("Watch key invalid");
                    }
                }

                boolean present = Files.isRegularFile(file);
                boolean correctContent = present
                        && "ready".equals(Files.readString(
                                file, StandardCharsets.UTF_8));

                System.out.println("Saw CREATE event: " + sawCreate);
                System.out.println("Saw OVERFLOW event: " + sawOverflow);
                System.out.println("Snapshot confirms file: "
                        + correctContent);
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 WatchServicePlatformDemo.java
java WatchServicePlatformDemo
~~~

**Một kết quả có thể gặp** trên file system cục bộ hỗ trợ việc giám sát:

~~~text
Saw CREATE event: true
Saw OVERFLOW event: false
Snapshot confirms file: true
~~~

**Nếu provider chưa phát event trong hai giây**, phần đầu có thể thay bằng:

~~~text
Saw CREATE event: false
Saw OVERFLOW event: false
Snapshot confirms file: true
~~~

Đây là hai **ví dụ kết quả minh họa**, không phải bảo đảm stdout giống nhau trên mọi hệ thống. Nếu key bị hủy, chương trình có thể in thêm `Watch key invalid`. Nếu `newWatchService` hoặc `register` không được hỗ trợ hay có lỗi I/O thì chương trình có thể ném exception; ứng dụng production phải bắt và chuyển sang chiến lược dự phòng phù hợp.

### Vì sao ví dụ được viết như vậy?

1. `directory.register(...)` diễn ra **trước** khi tạo `report.txt`; như vậy demo không phụ thuộc một event hồi tố cho file đã tồn tại.
2. `watcher.poll(2, SECONDS)` chờ có giới hạn; trả `null` nghĩa là **không có key sẵn sàng trong thời gian chờ**, không chứng minh thư mục không thay đổi.
3. `event.kind()` được so với `ENTRY_CREATE`, không suy ra event nào xảy ra chỉ từ một lần `Files.writeString`.
4. `event.context()` được so với `file.getFileName()`, là tên tương đối của mục trong thư mục watch. Không cần ghép đường dẫn tuyệt đối khi chỉ so sánh tên.
5. `OVERFLOW` được kiểm tra riêng vì không thể xử lý như một sự kiện của một file bình thường.
6. `key.reset()` được gọi sau khi lấy event; nếu invalid thì ứng dụng cần xem xét tình trạng đăng ký.
7. `Files.isRegularFile` và `Files.readString` **kiểm tra trạng thái thực** thay vì phỏng đoán từ việc event có/không đến. Dù không có `ENTRY_CREATE`, snapshot vẫn nhìn thấy file do chính chương trình vừa tạo.
8. `try-with-resources` đóng watcher trước khi xóa thư mục tạm; cleanup không phải minh họa cho tính năng đồng bộ dữ liệu từ máy từ xa.

**Hạn chế của demo:** chương trình chỉ đọc **một** key và một lô event trong thời gian ngắn; đây không phải vòng watch dùng liên tục hay test bao phủ NFS/SMB. Để đánh giá network file system, cần chạy watcher trên máy A và tạo/sửa/xóa file từ máy B theo kịch bản riêng.

## 7. Thiết kế vững hơn: Event là tín hiệu, snapshot là trạng thái

Một hệ thống xử lý file trong `inbox` không nên phụ thuộc việc nhận được đúng một event cho mỗi tệp. Có thể dùng kiến trúc:

~~~text
                +----------------------+
WatchService -->| Đánh dấu path "dirty"|----+
                +----------------------+    |
                                             v
Scheduled scan ------------------------> Reconciler
                                             |
                                             v
                                   Snapshot trạng thái file
                                             |
                                             v
                                   So sánh state đã xử lý
                                             |
                                  +----------+-----------+
                                  |                      |
                                 Mới/đổi               Không đổi
                                  |                      |
                             Xử lý idempotent          Bỏ qua
                                  |
                             Lưu checkpoint
~~~

### 7.1. Reconciliation là gì?

**Reconciliation** là thao tác đọc trạng thái tệp đang tồn tại, so với trạng thái đã biết, rồi xử lý những khác biệt cần thiết. Nó không cần biết chắc toàn bộ chuỗi event đã xảy ra; nó xác định **điều gì đang hiện diện hoặc khác với lần quan sát trước**.

Ví dụ snapshot đơn giản có thể bao gồm:

| Thuộc tính | Công dụng | Giới hạn |
| --- | --- | --- |
| Tên/path tương đối | Định danh đường dẫn trong thư mục đã giám sát | File bị rename/copy có thể đổi danh tính |
| Kích thước `Files.size` | Lọc tệp có lượng byte đổi | Hai nội dung khác nhau có thể cùng size |
| `lastModifiedTime` | Gợi ý có cập nhật | Độ phân giải timestamp/cache có thể bỏ sót |
| Hash nội dung (khi cần) | Phân biệt nội dung cùng size/mtime | Tốn đọc toàn bộ byte và CPU, có thể gặp file đang thay đổi |
| Version ID/manifest bên tạo | Nhận diện phiên bản đã công bố | Cần thiết kế phối hợp với producer |
| Checkpoint xử lý | Tránh xử lý lại tác dụng phụ đã hoàn tất | Phải lưu bền và có cơ chế cập nhật an toàn |

**Lưu ý về ảnh chụp:** quét thư mục bằng `DirectoryStream` hay `Files.list` không tự cung cấp snapshot nguyên tử; file có thể biến mất/đổi giữa lúc duyệt và lúc mở. Một reconciler phải chịu được `NoSuchFileException`, `AccessDeniedException` và lỗi mạng tạm thời.

### 7.2. Kịch bản quét đối chiếu đơn giản

~~~java
try (var entries = Files.list(inboxDirectory)) {
    for (Path candidate : entries.toList()) {
        if (!Files.isRegularFile(candidate)) {
            continue;
        }

        long size;
        try {
            size = Files.size(candidate);
        } catch (IOException transientFailure) {
            // File có thể vừa bị xóa hoặc share tạm không truy cập được.
            continue;
        }

        // So sánh metadata/hash/manifest với checkpoint.
        // Nếu có phiên bản mới và đã sẵn sàng, xử lý idempotent.
        // Chỉ checkpoint sau khi nghiệp vụ hoàn tất thành công.
    }
}
~~~

Đây là **đoạn minh họa**, sử dụng `inboxDirectory` được khai báo và import `java.nio.file.Files`, `Path`, `IOException`; không tự chạy độc lập. Với thư mục cực lớn, tránh `toList()` nếu cần hạn chế RAM; có thể duyệt stream khi còn mở hoặc dùng `DirectoryStream`. Với network share, từng thao tác lấy metadata cũng có chi phí mạng; cần giới hạn tần suất và mức đồng thời.

### 7.3. Kết hợp watchdog event với polling dự phòng

Một chu kỳ hoạt động thực tế:

1. Khi khởi động, cố đăng ký `WatchService` và thực hiện **full scan** ban đầu.
2. Khi nhận `ENTRY_CREATE`/`ENTRY_MODIFY`/`ENTRY_DELETE`, đánh dấu path/thư mục cần kiểm tra; không mặc định event chứa trạng thái cuối.
3. Nếu nhận `OVERFLOW`, đánh dấu **full rescan** vì danh sách event đã mất độ đầy đủ.
4. Dù không có event, sau một khoảng thời gian phù hợp vẫn chạy **scheduled reconciliation**, đặc biệt quan trọng với network mount.
5. Nếu watch không hỗ trợ, bị hủy hoặc lỗi, tiếp tục hoạt động theo **polling** với giám sát/cảnh báo; thử đăng ký lại khi thích hợp.
6. Sau khi xử lý xong file hoặc phiên bản, ghi checkpoint bền vững; chống trùng khi nhận thêm event hoặc ứng dụng khởi động lại.

**Tần suất polling** là lựa chọn dựa trên SLA và chi phí: quét mỗi giây có thể quá tải share nhiều triệu file; quét mỗi vài phút có thể không đủ nếu cần phản ứng rất nhanh. Dùng batch, phân vùng thư mục, chỉ mục/manifest hay thông báo từ producer khi hệ thống lớn.

## 8. “File đã thay đổi” không có nghĩa “File đã hoàn thành ghi”

Đây là rủi ro lớn của cả watch cục bộ lẫn remote. Khi observer nhận `ENTRY_CREATE` hoặc `ENTRY_MODIFY`, producer có thể còn đang ghi một file 5 GiB.

Nếu consumer xử lý ngay có thể đọc file thiếu, parse hỏng hoặc tính hash trên dữ liệu đang thay đổi. Các cách phối hợp tốt hơn:

### 8.1. Ghi tệp tạm rồi công bố

Producer ghi vào `report.csv.part`, đồng bộ/đóng theo nhu cầu, sau đó công bố bằng cách đổi tên sang `report.csv` **nếu phép move/rename thích hợp được hỗ trợ trong cùng file system**. Consumer chỉ xử lý tên hoàn chỉnh. Trên network file system, tính nguyên tử và khả năng nhìn thấy của rename phụ thuộc provider và hệ thống; không giả định mọi kiểu move đều atomic.

Nếu yêu cầu atomic move, Java hỗ trợ `StandardCopyOption.ATOMIC_MOVE` nhưng có thể ném `AtomicMoveNotSupportedException`; ứng dụng cần chiến lược dự phòng rõ ràng. Hệ thống phải kiểm tra khả năng triển khai thực tế trên share.

### 8.2. Manifest hoặc marker hoàn tất

Producer ghi dữ liệu, sau đó tạo file marker `report.csv.done` hoặc bản ghi manifest chứa tên, size, hash và version. Consumer chỉ xử lý khi marker và dữ liệu khớp.

Cách này vẫn cần quy định **thứ tự công bố**, kiểm tra đồng bộ và xử lý file marker tồn tại trước khi mọi client nhìn thấy dữ liệu do cache mạng. Khi yêu cầu độ tin cậy cao, có thể dùng một dịch vụ phân phối message hoặc cơ sở dữ liệu lưu transaction thay vì suy ra trạng thái hoàn tất chỉ từ sự kiện file.

### 8.3. “Đợi file ổn định” là heuristic

Một số ứng dụng chờ `size`/`mtime` không đổi qua vài lần quét rồi xử lý. Đây chỉ là **phỏng đoán**: producer có thể tạm nghỉ rồi ghi tiếp. Không sử dụng làm bằng chứng hoàn tất nếu nghiệp vụ cần chắc chắn.

## 9. Watch thư mục và giới hạn đệ quy

`Path.register(watcher, ...)` cho một thư mục không bảo đảm tự động đăng ký **toàn bộ cây con**. Nếu muốn giám sát `root/a/` và `root/b/`, thường phải đăng ký các thư mục con cần quan tâm.

Vấn đề khi có thư mục mới:

1. Nhận `ENTRY_CREATE` của một mục trong parent.
2. Kiểm tra mục đó có thực sự là thư mục hay không; nó có thể biến mất trước khi kiểm tra.
3. Nếu muốn theo dõi tiếp, đăng ký thư mục mới.
4. **Quét ngay nội dung thư mục vừa đăng ký**, vì bên trong có thể đã có file được tạo trước khi đăng ký xong.

Đối với cây nhiều thư mục hoặc share mạng, số registration, mức sâu, thay đổi quyền, symlink và lỗi khi duyệt đều cần giới hạn. **Không tự động đi theo symbolic link** đến thư mục ngoài phạm vi được phép nếu chưa có chính sách rõ ràng; có nguy cơ vòng lặp hoặc quét ra ngoài vùng tin cậy.

Một số file system provider có thể hỗ trợ modifier riêng, nhưng Java SE 17 **không định nghĩa một modifier đệ quy chuẩn áp dụng cho mọi nền tảng**. Tránh phụ thuộc API nội bộ chỉ vì môi trường phát triển đang hỗ trợ.

## 10. Các kiểu lỗi thường xuất hiện trên network share

| Tình huống | Triệu chứng | Hướng xử lý |
| --- | --- | --- |
| Máy B tạo file, máy A không nhận `ENTRY_CREATE` | Consumer không xử lý nếu chỉ dùng watcher | Full scan định kỳ, thông báo từ producer hoặc event bus |
| Sự kiện đến chậm | Xử lý trễ ngoài kỳ vọng | Đo latency thực, áp dụng polling/hệ thống thông báo theo SLA |
| Client cache metadata | Snapshot từ A chưa giống trạng thái vừa công bố ở B | Retry có giới hạn, manifest/version và quan sát tính nhất quán |
| Share tạm ngắt | `IOException`, tệp không truy cập được, key có thể invalid | Health check, backoff, reconnect, đăng ký/quét lại |
| Mount bị thay thế | Watch có thể gắn với đối tượng cũ hoặc trạng thái không đúng kỳ vọng | Theo dõi mount/file store và reconciliation; tái khởi tạo watcher nếu cần |
| File được tạo rồi xóa rất nhanh | Polling không nhìn thấy file từng xuất hiện | Nếu cần lịch sử mọi thao tác, dùng log/event có đảm bảo từ nguồn |
| Quá nhiều file đổi | `OVERFLOW`, tràn hàng đợi hoặc chậm xử lý | Full rescan, giới hạn tải, tối ưu xử lý |
| Producer ghi từng phần | Consumer đọc file chưa hoàn tất | Publish protocol bằng tệp tạm/marker/version |
| Rename/move | Quan sát delete/create hoặc sự kiện khác nhau | Dựa trên trạng thái thực và định danh nghiệp vụ |
| Mtime cùng giá trị qua hai phiên bản | Bỏ sót nếu chỉ so timestamp | Kết hợp size/hash/version/manifest |
| Một event bị xử lý nhiều lần | Tạo trùng record, gửi trùng thông báo | Idempotency và checkpoint bền vững |

**Không có cách polling snapshot đơn thuần nào phục dựng được toàn bộ lịch sử các file đã xuất hiện rồi biến mất giữa hai lần quét.** Nếu yêu cầu “nhìn thấy mọi thao tác tạo/xóa trong quá khứ”, phải dùng một cơ chế được thiết kế như event log/audit từ chính nguồn sinh ra thay đổi.

## 11. Kiểm thử khả năng hỗ trợ trước khi đưa vào production

Một smoke test chỉ tạo file ngay trong JVM trên máy chạy watcher là **chưa đủ** để kết luận NFS/SMB hoạt động đúng. Nên kiểm tra theo ma trận:

| Nguồn thao tác | Các thao tác cần thử | Những gì cần đo |
| --- | --- | --- |
| Cùng tiến trình/host với watcher | Create, modify, delete | Event có đến không, bao nhiêu lần, độ trễ |
| Máy khác cùng mount/share | Create, modify, delete, rename | Có phát hiện hay chỉ nhìn thấy qua snapshot |
| Dữ liệu lớn/ghi lâu | Ghi nhiều chunk, close/rename | Event xảy ra khi nào; consumer có đọc sớm không |
| Burst hàng nghìn file | Create/modify liên tiếp | Có `OVERFLOW`, mất event, thời gian full scan |
| File tuổi thọ ngắn | Create rồi delete rất nhanh | Có bị bỏ sót không |
| Gián đoạn kết nối | Ngắt/reconnect mạng, remount | `WatchKey` còn valid hay không, khi nào cần đăng ký lại |
| Khởi động/restart | Có file trước khi đăng ký | Initial scan có phát hiện và tránh trùng không |
| Thay quyền/di chuyển thư mục | Permission denied, thư mục mất | Lỗi và khả năng recovery |

**Đo các chỉ số có ý nghĩa:** tỉ lệ file đã công bố được phát hiện, độ trễ từ lúc “sẵn sàng” đến lúc xử lý, số `OVERFLOW`, số lần rescan, thời gian hoàn thành rescan, số lỗi I/O, độ sâu backlog, CPU và I/O trên server mạng.

Một triển khai có thể cho kết quả tốt khi thử nghiệm với 10 file nhưng thất bại khi production có 100.000 file hoặc mạng mất kết nối. Test cần dùng đúng loại mount, option, quyền, bản Java và tải gần với thực tế.

## 12. Quản lý concurrency và vòng đời an toàn

### 12.1. Không chặn thread nhận event bằng xử lý nặng

Nếu watcher xử lý trực tiếp việc parse/đọc hàng GiB trước khi `reset()`, hàng đợi sự kiện có thể tích tụ. Thiết kế hữu ích hơn:

- Thread watch chỉ nhận key, chuyển path/thư mục vào hàng đợi **có giới hạn** hoặc đánh dấu dirty.
- Worker/reconciler thực hiện I/O, validate, parse và nghiệp vụ.
- Các path trùng được gộp để giảm tải; khi queue quá lớn, ưu tiên rescan có kiểm soát.
- Theo dõi số item pending và thời gian chờ, không để backpressure biến thành tiêu thụ bộ nhớ vô hạn.

### 12.2. Kết thúc đúng cách

Dùng `try-with-resources` để đóng `WatchService`. Nếu thread khác gọi `close()` trong lúc `take()` đang chờ, thread chờ có thể nhận `ClosedWatchServiceException`; đó có thể là tín hiệu dừng có chủ đích.

Với `watcher.take()`, thread cũng có thể nhận `InterruptedException`; hãy phục hồi interrupt nếu không ném tiếp:

~~~java
try {
    WatchKey key = watcher.take();
    // Xử lý key.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Dừng vòng theo dõi theo chính sách ứng dụng.
}
~~~

Đây là đoạn minh họa, trong đó `watcher` đã được tạo và import `WatchKey`. Không gọi `reset()` một cách tùy tiện khi chưa xử lý xong lô sự kiện, và không để exception trong handler khiến toàn bộ watch loop dừng vĩnh viễn mà không có thông báo.

### 12.3. Path và an toàn thư mục

`WatchEvent.context()` chứa đường dẫn tương đối của mục trong thư mục đăng ký, nhưng trạng thái hệ thống tệp có thể thay đổi kể từ khi event xuất hiện. Trước khi mở file, kiểm tra phạm vi, quyền và loại đối tượng. Nếu vùng watch do tác nhân không tin cậy kiểm soát, phải xét symbolic link, thay thế file và rủi ro TOCTOU (time-of-check to time-of-use).

`watchedDir.resolve((Path) event.context())` chỉ **tạo một đường dẫn**, không bảo đảm mục còn tồn tại hay vẫn trỏ đến đối tượng ban đầu. Đặc biệt với share mạng, xử lý các lỗi truy cập là đường chạy bình thường.

## 13. Khi nào nên dùng WatchService thuần, khi nào cần phương án khác?

### Chỉ WatchService (có xử lý `OVERFLOW`) có thể đủ nếu

- Ứng dụng chủ yếu cần **làm mới giao diện** hoặc cache khi thư mục cục bộ thay đổi.
- Có thể chấp nhận mất một vài thông báo và tự kiểm tra lại trạng thái lúc cần.
- Không cần lưu lịch sử mọi thao tác tạo/xóa trong quá khứ.
- File system và hành vi provider đã được thử nghiệm ở quy mô phù hợp.

Ngay cả ở đây, nên có cơ chế refresh khi ứng dụng khởi động và khi key invalid.

### WatchService kết hợp polling/reconciliation nên dùng nếu

- Theo dõi **network share** hoặc bất kỳ storage nào mà event remote chưa được chứng minh đáng tin.
- Ứng dụng cần phát hiện tệp mới sau khi restart hoặc khi tạm mất kết nối.
- Một file có thể phát nhiều event hay có burst lớn.
- Cần tự phục hồi sau `OVERFLOW`, remount và lỗi I/O.
- Tính đúng đắn phụ thuộc **trạng thái hiện có**, không phải mọi bước lịch sử.

### Dùng notification/event log từ producer nếu

- Phải phát hiện **mọi** lần công bố kể cả file tồn tại cực ngắn.
- Cần thứ tự/định danh/ack/retry có hợp đồng rõ ràng.
- Xử lý nghiệp vụ yêu cầu kiểm soát đúng một lần theo ngữ nghĩa (thường qua idempotency + checkpoint).
- Nhiều máy xử lý cùng một thư mục và phải tránh nhận trùng hoặc xử lý đua.

Trong trường hợp đó, message queue, database outbox, manifest versioned hoặc một cơ chế phát sự kiện đáng tin từ chính hệ thống tạo file thường là nguồn sự thật rõ ràng hơn một watcher.

## 14. Lỗi phổ biến và cách khắc phục

**Lỗi 1 — “Java dùng WatchService nên sẽ nhận sự kiện từ mọi máy ghi vào SMB/NFS.”** Không có bảo đảm như vậy. Phải thử nghiệm thao tác từ client khác và có phương án quét lại.

**Lỗi 2 — “Không nhận event trong 5 giây chứng tỏ chưa có file.”** Sai. `poll(timeout) == null` chỉ nói chưa có key được phát hiện trong thời gian chờ. Kiểm tra snapshot và SLA.

**Lỗi 3 — “Một lần ghi file sẽ phát đúng một `ENTRY_MODIFY`.”** Sai. Sự kiện có thể lặp, gộp hoặc bị bỏ lỡ.

**Lỗi 4 — “Đã nhận modify thì file chắc chắn hoàn tất.”** Sai. Producer có thể vẫn đang ghi. Dùng giao thức công bố/marker hoặc xác thực readiness.

**Lỗi 5 — “Bỏ qua `OVERFLOW` vì không có context file.”** Sai. Đây là dấu hiệu đã mất tính đầy đủ của danh sách sự kiện; cần reconciliation/rescan.

**Lỗi 6 — “Gọi `pollEvents()` là đủ, không cần `reset()`.”** Sai. Sau khi xử lý key, phải reset để key trở lại trạng thái sẵn sàng nhận tín hiệu mới; kiểm tra kết quả boolean.

**Lỗi 7 — “Đăng ký root là tự động theo dõi đệ quy.”** Sai với hợp đồng chung của API. Muốn theo dõi thư mục con thì cần registration và xử lý thư mục mới.

**Lỗi 8 — “Chỉ cần so mtime là không thể mất cập nhật.”** Sai. Mtime bị ảnh hưởng bởi độ phân giải timestamp, cache, thao tác preserve metadata; bổ sung size/hash/version khi cần.

**Lỗi 9 — “Snapshot đầy đủ sẽ tái hiện mọi lịch sử file.”** Sai. File tạo rồi xóa giữa hai lần scan có thể không để lại trạng thái nào để phát hiện.

**Lỗi 10 — “Thay mount xong thì watch cũ tự phục hồi chắc chắn.”** Không được bảo đảm. Dùng health check, kiểm tra registration, đăng ký lại và rescan khi phát hiện thay đổi môi trường.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Máy A đăng ký watcher trên NFS; máy B tạo file. Máy A không nhận `ENTRY_CREATE`. Có thể coi JVM bị lỗi?

**Đáp án:** Không. Java không bảo đảm phát hiện thay đổi remote. Kiểm tra provider và thiết lập cơ chế polling/reconciliation hoặc notification từ nguồn.

**Câu 2.** Watcher nhận ba `ENTRY_MODIFY` cho một file. Có phải producer đã lưu file ba lần thành công?

**Đáp án:** Không. Số event không phải số lần commit nghiệp vụ. Chỉ xử lý theo trạng thái tệp và cơ chế nhận diện phiên bản.

**Câu 3.** Khi gặp `OVERFLOW`, có nên chỉ bỏ qua event đó và tiếp tục các event còn lại?

**Đáp án:** Không nếu cần đầy đủ trạng thái. Phải quét đối chiếu phạm vi liên quan; không thể suy ra chắc chắn file nào đã bị bỏ qua.

**Câu 4.** Đăng ký watch sau khi file đã tồn tại sẽ tự sinh `ENTRY_CREATE` cho file đó?

**Đáp án:** Không. Cần initial scan để nhận các mục có trước thời điểm đăng ký.

**Câu 5.** Với consumer xử lý báo cáo tài chính từ shared folder, một sự kiện `ENTRY_CREATE` có đủ để xác nhận file sẵn sàng?

**Đáp án:** Không. Cần giao thức công bố (file tạm rồi rename thích hợp, marker/manifest hoặc tín hiệu từ producer), kiểm tra nội dung và tính toàn vẹn.

**Câu 6.** Nếu cần ghi lại mọi lần tạo/xóa file rất ngắn trên nhiều máy, WatchService + polling có bảo đảm không bỏ sót lịch sử?

**Đáp án:** Không. Cần nguồn event log/audit đáng tin cậy tại nơi sinh sự kiện.

**Câu 7.** Tại sao một hệ thống vẫn nên quét định kỳ khi watcher có vẻ hoạt động tốt?

**Đáp án:** Để nhận các thay đổi bị bỏ sót, phục hồi sau outage/overflow và kiểm tra tính nhất quán giữa trạng thái đã lưu với trạng thái thực.

## 16. Ghi nhớ

- **WatchService là cơ chế thông báo thay đổi với hành vi phụ thuộc nền tảng**, không phải event log đầy đủ hay cơ chế giao dịch.
- **Network file system đặc biệt quan trọng:** thay đổi từ máy khác có thể không phát hiện; kiểm tra thực tế bằng NFS/SMB và đúng cấu hình triển khai.
- **`OVERFLOW`, event lặp, event đến trễ và key invalid** đều phải có nhánh xử lý rõ ràng.
- **Nhận event không đồng nghĩa file đã ghi xong**; dùng protocol công bố và xác thực trạng thái.
- **Kết hợp event + reconciliation định kỳ + checkpoint/idempotency** là cách thực tế cho các hệ thống quan trọng; nếu phải bảo toàn toàn bộ lịch sử, cần nguồn sự kiện đáng tin từ producer.

### Tài liệu tham khảo chính thức

- [Java SE 17 — WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): hợp đồng API, `OVERFLOW` và giới hạn phụ thuộc nền tảng/remote file systems.
- [Java SE 17 — WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html): `pollEvents()`, `reset()`, trạng thái valid/cancel.
- [Dev.java — Watching a Directory for Changes](https://dev.java/learn/api/io/java-io/file-system/watching-dir-changes/): quy trình đăng ký và xử lý directory watch.
