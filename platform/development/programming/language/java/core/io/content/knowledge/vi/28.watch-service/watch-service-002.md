# ENTRY_CREATE, ENTRY_DELETE và ENTRY_MODIFY: Theo dõi thay đổi tệp bằng Java NIO.2

## 1. Mục tiêu của bài

Khi cần phát hiện một tệp mới được tạo, tệp cũ bị xóa hoặc nội dung của một tệp được chỉnh sửa, Java NIO.2 cung cấp **`WatchService`**. Cơ chế này theo dõi thay đổi của các **entry trong thư mục đã đăng ký**, rồi cung cấp các thông báo thông qua `WatchKey` và `WatchEvent`.

Ba sự kiện thường gặp nhất được định nghĩa trong `java.nio.file.StandardWatchEventKinds`:

- **`ENTRY_CREATE`**: một entry mới xuất hiện trong thư mục được theo dõi.
- **`ENTRY_DELETE`**: một entry biến mất khỏi thư mục được theo dõi.
- **`ENTRY_MODIFY`**: một entry trong thư mục được quan sát là đã thay đổi.

Bài này giải thích ý nghĩa và giới hạn của từng loại, cách đăng ký và xử lý sự kiện đúng vòng đời, ví dụ Java 17+ có thể chạy được, các lỗi thường gặp như mất sự kiện, đăng ký thiếu thư mục con và đọc tệp khi writer còn đang ghi.

**Tư tưởng quan trọng:** `WatchService` là một *cơ chế thông báo thay đổi*, **không phải nhật ký giao dịch có khả năng ghi nhận đầy đủ mọi thay đổi**. Khi ứng dụng cần trạng thái chính xác của dữ liệu, hãy dùng sự kiện làm tín hiệu để **kiểm tra trạng thái tệp thật** và đối chiếu với snapshot/chỉ mục.

## 2. Các thành phần trong một luồng xử lý

| Thành phần | Vai trò |
| --- | --- |
| `FileSystems.getDefault().newWatchService()` | Tạo dịch vụ tiếp nhận sự kiện file system |
| `Path.register(watchService, kinds...)` | Đăng ký thư mục với những loại sự kiện cần theo dõi |
| `WatchKey` | Đại diện một registration; được đánh dấu khi có sự kiện |
| `WatchService.take()` | Chờ một key có tín hiệu, có thể chặn thread |
| `WatchService.poll()` / `poll(timeout, unit)` | Lấy key ngay hoặc đợi có giới hạn thời gian |
| `WatchKey.pollEvents()` | Lấy danh sách sự kiện đã tích lũy của registration |
| `WatchEvent.kind()` | Loại sự kiện: CREATE / DELETE / MODIFY / OVERFLOW |
| `WatchEvent.context()` | Ngữ cảnh entry; với ba sự kiện chuẩn là `Path` tương đối |
| `WatchEvent.count()` | Số lần một sự kiện đã được cộng dồn theo cơ chế của provider |
| `WatchKey.reset()` | Sau khi xử lý xong, cho phép key được kích hoạt lại; trả `false` nếu không còn hợp lệ |
| `WatchKey.cancel()` | Hủy đăng ký |
| `WatchService.close()` | Giải phóng dịch vụ, đánh thức các thread đang chờ với lỗi đóng dịch vụ |

Một ví dụ khai báo cơ bản:

~~~java
Path directory = Path.of("data");
try (WatchService watcher =
             directory.getFileSystem().newWatchService()) {
    WatchKey key = directory.register(
            watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);
    // Vòng lặp nhận và xử lý sự kiện nằm tại đây.
}
~~~

Đây là **mảnh mã minh họa**, chưa phải chương trình hoàn chỉnh; cần import các lớp NIO và static import ba hằng trong `StandardWatchEventKinds`. Thư mục phải tồn tại, provider phải hỗ trợ cơ chế theo dõi.

Tại sao ví dụ dùng `directory.getFileSystem().newWatchService()` thay vì luôn `FileSystems.getDefault()`? Vì `Path` có thể thuộc một `FileSystem`/provider khác. Việc tạo dịch vụ từ cùng file system giúp tránh ghép một `Path` với watcher của provider không tương thích. Trên một số provider ảo, watch service có thể không được hỗ trợ; cần xử lý `UnsupportedOperationException` hoặc lỗi tương ứng.

## 3. ENTRY_CREATE: entry mới xuất hiện

`ENTRY_CREATE` được báo khi provider quan sát rằng một entry mới xuất hiện **trực tiếp** trong thư mục được đăng ký. Entry có thể là tệp, thư mục con hoặc dạng entry khác mà provider hỗ trợ.

Các thao tác có thể gây `ENTRY_CREATE`:

- `Files.createFile(folder.resolve("a.txt"))` tạo tệp mới.
- `Files.createDirectory(folder.resolve("child"))` tạo thư mục con.
- Chương trình khác tạo tệp hoặc di chuyển/đổi tên một entry **vào trong** thư mục được theo dõi.

Ví dụ một entry mới:

~~~text
Trước:  watched/
              notes.txt
Sau:    watched/
              notes.txt
              report.csv   <-- ENTRY_CREATE cho report.csv
~~~

Với `WatchEvent<Path>` của sự kiện chuẩn, `event.context()` thường là đường dẫn **tương đối với thư mục đã đăng ký**, ví dụ `Path.of("report.csv")`, không phải đường dẫn đầy đủ. Muốn tạo đường dẫn để kiểm tra:

~~~java
Path changed = directory.resolve(relativeName).normalize();
~~~

Đây là **mã minh họa**, giả sử `directory` là thư mục đã đăng ký và `relativeName` là `Path` context hợp lệ. Nếu cần chống đường dẫn đáng ngờ trong các hệ thống nhạy cảm, phải kiểm tra phạm vi trước khi đọc và cân nhắc symbolic link/race khi truy cập.

**Một CREATE không chứng minh tệp đã được ghi xong.** Writer có thể tạo tên tệp trước, rồi truyền nhiều MB nội dung vào đó. Watcher thấy entry mới trong lúc tệp còn rỗng hoặc chưa đủ dữ liệu. Nếu cần chỉ nhận file hoàn chỉnh, bên tạo có thể ghi vào tệp tạm, đóng/đồng bộ theo yêu cầu, rồi đổi tên sang tên chính thức; bên nhận chờ tên chính thức xuất hiện và xác thực kích thước, checksum hoặc marker hoàn tất.

Đổi tên một entry **vào** thư mục có thể được báo dưới dạng CREATE. Đây là thông báo về thay đổi entry, không phải khẳng định nội dung của file được tạo từ đầu.

Theo hợp đồng `StandardWatchEventKinds` của Java SE 17, `count()` đối với một sự kiện `ENTRY_CREATE` là 1; nhiều thao tác tạo khác nhau có thể sinh các event khác nhau, nhưng vẫn không được coi danh sách sự kiện là lịch sử bất biến trong mọi tình huống (vì provider có thể mất sự kiện và phát `OVERFLOW`).

## 4. ENTRY_DELETE: entry không còn trong thư mục

`ENTRY_DELETE` được báo khi một entry bị loại khỏi thư mục đang theo dõi. Nguyên nhân có thể là:

- `Files.delete(file)` hoặc ứng dụng khác xóa entry.
- Entry được **di chuyển ra ngoài** thư mục theo dõi.
- Tên entry thay đổi theo cách provider báo là xóa tên cũ và tạo tên mới.

Ví dụ:

~~~text
Trước:  watched/
              old.log
              config.yml
Sau:    watched/
              config.yml
          <-- ENTRY_DELETE cho old.log
~~~

Một DELETE **không nhất thiết chứng minh dữ liệu vật lý đã bị xóa vĩnh viễn**. Có thể file được di chuyển nơi khác, hoặc có process còn giữ handle mở tùy hệ điều hành. Sự kiện chỉ nói rằng tên/entry trong thư mục được theo dõi đã biến mất theo quan sát của watcher.

Ở thời điểm nhận event DELETE, gọi `Files.readString(changed)` thường không hợp lý: đường dẫn có thể không tồn tại. Trong khoảng thời gian giữa lúc nhận event và lúc kiểm tra, entry cùng tên cũng có thể **đã được tạo lại**; phải xem đây là trạng thái hiện tại, không phải bằng chứng về một lịch sử tuần tự của cùng đối tượng file.

Ứng dụng quản lý chỉ mục cần xử lý trường hợp file bị xóa rồi tạo lại nhanh, hoặc sự kiện đến muộn: nên đối chiếu lại danh sách thư mục và danh tính/metadata cần thiết thay vì xóa dữ liệu nghiệp vụ dựa hoàn toàn vào một thông báo.

Theo Java SE 17, `count()` của một sự kiện `ENTRY_DELETE` là 1. Nếu thay đổi xảy ra quá nhanh hoặc provider quá tải, sự kiện có thể không được quan sát đầy đủ; xem phần `OVERFLOW` và reconciliation.

## 5. ENTRY_MODIFY: entry đã thay đổi, không đồng nghĩa “ghi xong”

`ENTRY_MODIFY` được báo khi provider quan sát một entry đã thay đổi. Thay đổi có thể xuất phát từ cập nhật nội dung, metadata, thao tác lưu tệp từ editor hoặc những hành vi khác theo provider/file system.

Ví dụ:

~~~text
report.csv ban đầu:
id,total
1,100

Sau một lần ghi:
id,total
1,200

Watcher có thể báo ENTRY_MODIFY cho report.csv.
~~~

Những giới hạn phải nhớ:

1. **Một lần lưu có thể sinh nhiều MODIFY.** Editor có thể ghi từng phần, truncate, fsync, đổi metadata hoặc ghi file tạm/rename; watcher có thể phát nhiều event cho một thao tác “Save” ở tầng người dùng.
2. **Nhiều thay đổi có thể gộp thành một event**, với `event.count() > 1`. Tài liệu Java SE 17 cho phép `count()` của `ENTRY_MODIFY` bằng 1 hoặc lớn hơn.
3. **Nhận MODIFY không bảo đảm writer đã kết thúc**. Không đọc ngay rồi mặc định dữ liệu là hoàn chỉnh. Khi đọc được snapshot giữa lúc ghi, file có thể trống hoặc chứa một phần dữ liệu.
4. **Không có before/after payload.** `WatchEvent` không mang nội dung cũ, nội dung mới hoặc bản diff. Muốn biết thay đổi, ứng dụng phải tự đọc/so sánh trạng thái hiện tại.
5. **Không nên coi mọi MODIFY đều có ý nghĩa nghiệp vụ.** Một số ứng dụng thay đổi metadata hoặc ghi lại nội dung giống hệt; cần so sánh kích thước, timestamp, hash hay dữ liệu thực nếu muốn lọc.
6. **Không dùng `count()` làm số lần ghi business chính xác.** Count chỉ phản ánh cách provider gộp các thông báo, không tương đương số transaction hoặc lần gọi `Files.write`.

Một chiến lược khi nhận MODIFY:

~~~text
ENTRY_MODIFY
     ↓
Đưa đường dẫn vào hàng đợi "dirty paths" (set chống trùng)
     ↓
Chờ một khoảng debounce / xác nhận producer đã hoàn tất
     ↓
Đọc dữ liệu mới có kiểm tra lỗi và kích thước
     ↓
So sánh phiên bản/checksum và cập nhật chỉ mục
~~~

Debounce chỉ làm giảm xử lý trùng và tăng cơ hội dữ liệu ổn định, **không phải chứng minh tệp đã được ghi xong**. Khi yêu cầu mạnh hơn, cần phối hợp với producer bằng rename nguyên tử trong phạm vi được hỗ trợ, marker hoàn tất hoặc một giao thức khóa/phiên bản.

## 6. Ví dụ Java 17+ hoàn chỉnh: tạo, sửa, xóa một tệp

Ví dụ sau tự tạo thư mục tạm mới, đăng ký watcher với cả ba loại sự kiện, rồi thực hiện lần lượt:

1. Tạo `sample.txt` và chờ `ENTRY_CREATE`.
2. Ghi nội dung mới vào chính tệp này và chờ `ENTRY_MODIFY`.
3. Xóa file và chờ `ENTRY_DELETE`.

Ví dụ dùng `poll(timeout, unit)` với hạn 5 giây cho mỗi loại sự kiện để tránh treo vô hạn nếu provider không báo event theo kỳ vọng. Nó **không** giả định một operation chỉ sinh đúng một event; hàm `await` lọc theo loại và tên, bỏ qua event phụ không phải mục tiêu ở mỗi bước. Cách bỏ qua này chỉ phù hợp demo; chương trình production phải xử lý mọi sự kiện liên quan.

Lưu file **`WatchKindsDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.concurrent.TimeUnit;

import static java.nio.file.StandardWatchEventKinds.*;

public class WatchKindsDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watch-kinds-");
        Path file = directory.resolve("sample.txt");
        try (WatchService watcher = directory.getFileSystem().newWatchService()) {
            directory.register(watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);
            System.out.println("Watching sample.txt");

            Files.writeString(file, "first", StandardOpenOption.CREATE_NEW);
            await(watcher, ENTRY_CREATE, file.getFileName());

            Files.writeString(file, "second",
                    StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
            await(watcher, ENTRY_MODIFY, file.getFileName());

            Files.delete(file);
            await(watcher, ENTRY_DELETE, file.getFileName());
        } finally {
            if (Files.exists(file)) Files.delete(file);
            Files.delete(directory);
        }
    }

    private static void await(WatchService watcher, WatchEvent.Kind<Path> wanted,
                              Path filename) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (true) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) {
                throw new IOException("Timed out waiting for " + wanted.name());
            }
            WatchKey key = watcher.poll(remaining, TimeUnit.NANOSECONDS);
            if (key == null) throw new IOException("Timed out waiting for " + wanted.name());
            boolean matched = false;
            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == OVERFLOW) {
                    throw new IOException("WatchService overflow; rescan needed");
                }
                if (event.kind() == wanted && filename.equals(event.context())) {
                    matched = true;
                }
            }
            if (!key.reset()) throw new IOException("Watched directory unavailable");
            if (matched) {
                System.out.println(wanted.name() + ": " + filename);
                return;
            }
        }
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac WatchKindsDemo.java
java WatchKindsDemo
~~~

**Đầu ra quan sát được khi biên dịch và chạy trên môi trường kiểm thử hỗ trợ WatchService:**

~~~text
Watching sample.txt
ENTRY_CREATE: sample.txt
ENTRY_MODIFY: sample.txt
ENTRY_DELETE: sample.txt
~~~

Các dòng trên là **kết quả đã kiểm tra trên hệ thống thử nghiệm**, không phải lời bảo đảm tất cả hệ điều hành/file system đều phát event cùng cách và trong 5 giây. Nếu provider không hỗ trợ một sự kiện, hoặc báo chậm, chương trình có thể kết thúc bằng `IOException` timeout thay vì in đủ ba dòng; ứng dụng thực tế phải định nghĩa chính sách retry/reconciliation.

**Điểm quan trọng trong mã:**

- `Path directory` là thư mục được đăng ký; `file.getFileName()` chính là tên tương đối dùng để đối chiếu `event.context()`.
- `Files.writeString(..., CREATE_NEW)` tạo entry mới; lệnh ghi tiếp theo trên cùng file yêu cầu `TRUNCATE_EXISTING, WRITE`; thao tác thứ ba xóa entry.
- `watcher.poll(timeout, NANOSECONDS)` chờ sự kiện có giới hạn; `null` nghĩa là đã hết thời gian mà không có key sẵn sàng.
- `WatchKey.pollEvents()` cung cấp các event trong lần xử lý. `OVERFLOW` có thể xuất hiện ngay cả khi không đăng ký nó; khi gặp, demo dừng để tránh coi chuỗi sự kiện là đầy đủ.
- `key.reset()` **bắt buộc** sau khi xử lý batch để key có thể báo lại. Trả `false` nghĩa là key không còn hợp lệ; ví dụ báo lỗi thay vì chờ mãi.
- `try-with-resources` đóng WatchService; khối `finally` dọn tệp và thư mục tạm. Mã chạy trên dữ liệu riêng nên không động đến thư mục người dùng.
- Việc theo dõi ba thao tác **tuần tự** giảm nguy cơ sự kiện bị gộp làm demo khó quan sát. Tuy nhiên event phụ, thứ tự quan sát và thời điểm nhận vẫn phụ thuộc provider.
- Hàm `await` chủ ý tìm một sự kiện phù hợp; trong hệ thống thực tế không thể bỏ qua những event khác như vậy vì có thể bỏ sót thay đổi quan trọng.

## 7. Vòng lặp watcher có thể dùng lâu dài

Trong hệ thống chạy liên tục, thường dùng một thread tiêu thụ event và chuyển công việc sang queue. Trình tự đúng:

1. Tạo `WatchService` với file system thích hợp.
2. Đăng ký **thư mục** hiện có với những event kinds cần theo dõi.
3. Gọi `take()` (chặn tới khi có key) hoặc `poll(timeout, ...)`.
4. Lặp qua **toàn bộ** `key.pollEvents()`.
5. Phân nhánh `event.kind()`; nếu `OVERFLOW`, đánh dấu cần quét đối chiếu.
6. Với `ENTRY_CREATE`/`ENTRY_DELETE`/`ENTRY_MODIFY`, lấy context và ghép với thư mục tương ứng với key.
7. Đưa thay đổi vào hàng đợi xử lý phù hợp, tránh làm việc nặng trên watcher thread.
8. Gọi `key.reset()` **sau khi đã duyệt batch**. Nếu `false`, xóa registration khỏi registry và xử lý việc thư mục biến mất/không truy cập được.
9. Khi shutdown, đóng dịch vụ và dừng thread theo giao thức hủy đã định nghĩa.

Một đoạn minh họa về vòng lặp, **không phải chương trình độc lập**:

~~~java
while (running) {
    WatchKey key = watcher.take();
    Path watched = (Path) key.watchable();

    for (WatchEvent<?> event : key.pollEvents()) {
        WatchEvent.Kind<?> kind = event.kind();
        if (kind == OVERFLOW) {
            scheduleFullRescan(watched);
            continue;
        }
        if (kind == ENTRY_CREATE || kind == ENTRY_DELETE || kind == ENTRY_MODIFY) {
            Path relative = (Path) event.context();
            Path absolute = watched.resolve(relative);
            enqueueChange(kind, absolute, event.count());
        }
    }
    if (!key.reset()) {
        onRegistrationInvalid(watched);
    }
}
~~~

Giả định các biến `running`, `watcher` và các hàm `scheduleFullRescan`, `enqueueChange`, `onRegistrationInvalid` do chương trình sở hữu; imports cần thiết đến từ `java.nio.file`. Đoạn này trình bày flow, **không phải chương trình để copy và biên dịch độc lập**.

**Tại sao kiểm tra `OVERFLOW` trước khi ép kiểu context?** Vì `OVERFLOW` có kiểu `Kind<Object>` và context mang tính implementation-specific, có thể `null`. Không ép thẳng tất cả `WatchEvent<?>.context()` thành `Path` trước khi phân loại.

**Tại sao phải reset sau khi xử lý?** Theo hợp đồng API, WatchKey đã báo tín hiệu cần được reset để có thể báo lại. Nếu không reset, thread có thể xử lý batch đầu rồi không nhận các thay đổi tiếp theo theo kỳ vọng.

Nếu `key.reset()` trả `false`, thư mục được theo dõi có thể đã bị xóa, không còn truy cập được hoặc đăng ký đã hủy. Không reset liên tục để hy vọng key tự sống lại; cần xử lý state, bỏ key hoặc đăng ký lại thư mục khi điều kiện cho phép.

## 8. Cơ chế WatchKey, reset và coalescing

WatchService không đặt “một key trong queue cho mỗi event”. Mỗi registration có một `WatchKey`; nó được *signal* khi có event và được đưa vào queue nếu chưa ở trạng thái đã báo. Nhiều event có thể tích lũy trên cùng key trước khi consumer lấy ra.

Sơ đồ:

~~~text
Watchable directory
        │ create/modify/delete
        ▼
WatchService ghi nhận events cho WatchKey
        │ signal / queue key nếu chưa signalled
        ▼
watcher.take() hoặc watcher.poll()
        │
        ▼
key.pollEvents() → [event1, event2, ...]
        │
        └── xử lý xong → key.reset()
                             │
                             ├── true: sẵn sàng nhận các lượt event tiếp
                             └── false: registration không còn hợp lệ
~~~

Một số điểm cần nhớ:

- `pollEvents()` có thể cung cấp nhiều event cùng tên/loại hoặc event đã được **gộp**. Với `ENTRY_MODIFY`, `event.count()` có thể lớn hơn 1.
- `WatchService` có thể tích lũy event nhanh hơn consumer kịp xử lý; implementation có quyền giới hạn hàng đợi và báo `OVERFLOW` khi biết đã bỏ sự kiện.
- `WatchEvent.count()` không phải timestamp, version, byte count hay thứ tự transaction.
- Một event đã được báo không khóa file. Trong lúc consumer xử lý, file có thể lại bị sửa hoặc xóa. Bất biến “sự kiện nói rằng file hiện vẫn đang tồn tại” **không được bảo đảm**.
- Kể cả khi không thấy `OVERFLOW`, do sự khác biệt nền tảng và điều kiện I/O, không nên thiết kế nghiệp vụ yêu cầu event log hoàn chỉnh mà chỉ dựa vào WatchService.

## 9. Phân biệt ba event khi rename và move

WatchService chuẩn chỉ định `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY`, `OVERFLOW`; **không có sự kiện rename riêng trong StandardWatchEventKinds**.

Một thao tác rename/move có thể được phản ánh bằng những thay đổi entry:

| Thao tác | Những sự kiện có thể quan sát |
| --- | --- |
| Tạo `new.txt` trong thư mục được theo dõi | `ENTRY_CREATE new.txt`; có thể có thêm MODIFY khi ghi |
| Xóa `old.txt` | `ENTRY_DELETE old.txt` |
| Đổi tên `a.txt` thành `b.txt` trong cùng thư mục | Thường thấy DELETE tên cũ và CREATE tên mới, nhưng chi tiết phụ thuộc provider |
| Di chuyển file từ ngoài vào thư mục watched | Thường thấy CREATE cho tên được đưa vào |
| Di chuyển file từ watched ra ngoài | Thường thấy DELETE cho tên bị đưa ra |
| Ghi lại nội dung file bằng cách replace/rename temp file | Có thể xuất hiện CREATE/DELETE/MODIFY cho nhiều tên |

Không tự suy luận từ cặp `DELETE(old)` + `CREATE(new)` rằng đó chắc chắn là **cùng một file được rename**. Hai file không liên quan có thể bị xóa/tạo gần nhau. Nếu ứng dụng cần phát hiện move/rename chính xác, phải dùng thêm file identity/metadata phù hợp hoặc API native/giao thức của ứng dụng; `WatchEvent` tiêu chuẩn không cung cấp cặp source/destination như một transaction.

## 10. Theo dõi thư mục con: không tự động recursive

Một điểm dễ sai: đăng ký `root` **không mặc nhiên** theo dõi các thay đổi nằm sâu trong cây thư mục.

~~~text
root/                  <-- đã đăng ký watcher cho root
  a.txt                <-- thay đổi có thể báo qua root
  sub/                 <-- bản thân sub tạo/xóa trong root có thể báo qua root
    nested.txt         <-- thay đổi bên trong sub không mặc nhiên báo qua root
~~~

Nếu muốn theo dõi đệ quy:

1. Duyệt các thư mục con hiện có và đăng ký từng thư mục.
2. Khi quan sát `ENTRY_CREATE` cho một thư mục con mới, kiểm tra nó có thực sự là thư mục và đăng ký watcher tương ứng.
3. Cân nhắc các tệp/thư mục đã xuất hiện **trước khi** đăng ký thư mục con mới; cần quét lại thư mục đó để bắt các thay đổi đã xảy ra trong khoảng trống.
4. Khi thư mục bị xóa/move hoặc `reset()` báo invalid, cập nhật registry và các đăng ký liên quan.
5. Có chính sách với symlink, mount point, quyền truy cập và giới hạn số lượng registration của hệ điều hành.

Việc kiểm tra thư mục con bằng `Files.isDirectory(path)` sau event có **race**: entry có thể bị xóa hoặc thay thế trước khi kiểm tra. Trên hệ thống lớn, nên kết hợp watcher với snapshot/reconciliation định kỳ. Không theo dõi bừa mọi symbolic link vì có thể gây loop hoặc vượt phạm vi dữ liệu.

Không dùng một thread blocking riêng cho **mỗi tệp** chỉ để chờ sự kiện nếu thật ra muốn theo dõi các entry của cùng một thư mục. WatchService cho phép một watcher theo dõi nhiều directory registrations, nhưng chi phí và giới hạn thực tế phụ thuộc nền tảng.

## 11. OVERFLOW: trường hợp bắt buộc quét đối chiếu

`StandardWatchEventKinds.OVERFLOW` báo rằng **có thể đã có sự kiện bị mất hoặc bị bỏ**. Bạn **không cần đăng ký `OVERFLOW`** để nhận được nó; đó là tín hiệu đặc biệt của WatchService.

Nếu chỉ xử lý ba sự kiện chính mà bỏ qua `OVERFLOW`, index nội bộ có thể vĩnh viễn lệch so với thư mục thực tế. Cách tiếp cận an toàn hơn:

1. Đánh dấu directory hoặc subtree là **dirty / needs-reconcile**.
2. Đọc lại danh sách entry và metadata cần thiết.
3. So sánh với snapshot/index đang quản lý: phát hiện entry mới, entry mất và entry cần kiểm tra nội dung.
4. Cập nhật trạng thái nghiệp vụ theo giao thức idempotent; không giả định mỗi thay đổi chỉ được phát một lần.
5. Tiếp tục nghe sự kiện và lên lịch quét định kỳ để giảm tác động của mất/sai thứ tự event.

Ví dụ snapshot mức đơn giản có thể gồm `Map<Path, Metadata>`, trong đó Metadata lưu kích thước và `lastModifiedTime`. Tuy nhiên hai thuộc tính này cũng không phát hiện **mọi** thay đổi (độ chính xác timestamp, write same-size, metadata thay đổi, thao tác nhanh). Nếu cần xác thực nội dung, tính hash hoặc dùng version/commit marker do producer cung cấp.

### “Lấy snapshot trước hay đăng ký trước?”

Một vấn đề khởi tạo: nếu quét thư mục **trước** khi register, có thể có tệp được tạo trong khoảng trống giữa hai bước nên bị bỏ sót. Đăng ký **trước**, rồi quét snapshot và tiêu thụ events cũng phải xử lý những trùng lặp/race giữa snapshot và event.

Mẫu tốt: register → snapshot → drain events → reconcile (hoặc thiết kế tương đương), mọi thao tác update idempotent. Khi độ chính xác rất cao, cần hợp đồng nguồn dữ liệu chuyên dụng chứ không chỉ WatchService.

## 12. Cẩn thận khi xử lý tệp đang được ghi

Một chuỗi thường gặp:

~~~text
Writer:
  create("dataset.csv")
  write chunk 1
  write chunk 2
  write chunk 3
  close()

Watcher:
  ENTRY_CREATE
  ENTRY_MODIFY
  ENTRY_MODIFY ...
~~~

Watcher có thể chạy ngay giữa các chunk; nếu consumer parse khi chỉ có chunk đầu, sẽ thấy CSV/JSON/ZIP chưa hoàn chỉnh. Đây không phải lỗi riêng của Java mà là khác biệt giữa **entry đã thay đổi** và **đơn vị dữ liệu nghiệp vụ đã commit**.

Các giải pháp tùy mức độ yêu cầu:

- **Tệp tạm + đổi tên publish:** producer ghi vào tên tạm, xác thực/flush và đóng tệp, rồi chuyển sang tên publish. Nếu cùng file system hỗ trợ `StandardCopyOption.ATOMIC_MOVE`, có thể yêu cầu move nguyên tử; nếu không được hỗ trợ, phải quyết định fallback hoặc báo lỗi. Không tự khẳng định mọi rename trên network FS đều atomic/durable.
- **Marker hoàn tất:** producer ghi dữ liệu, sau đó tạo tệp sentinel như `dataset.csv.done`; watcher chỉ đưa dữ liệu vào xử lý sau marker và kiểm tra lại dữ liệu.
- **Lock hợp tác:** producer và consumer cùng thỏa thuận dùng khóa file hoặc lock khác. File locks phụ thuộc hệ điều hành và các bên phải thực sự tuân thủ; chúng không tự biến nhiều thao tác thành transaction.
- **Debounce:** gộp nhiều MODIFY trong khoảng lặng, sau đó kiểm tra size/mtime lần nữa. Cách này tiện cho file watcher UI nhưng **không đảm bảo hoàn tất** nếu writer tạm nghỉ lâu rồi ghi tiếp.
- **Checksum/version:** dữ liệu chỉ được nhận khi đáp ứng định dạng và phiên bản mong đợi; giúp phát hiện partial write hoặc trạng thái cũ.

Khi có DELETE rồi CREATE lại cùng tên, phải coi đó có thể là object mới. Cache nội dung theo tên file mà không xác thực version/identity dễ trả nhầm dữ liệu.

## 13. Tránh blocking event loop và xử lý trùng lặp

Nếu dùng `watcher.take()` trong một thread, đừng để event handler thực hiện đọc file cực lớn, upload mạng hay truy vấn database blocking ngay trên thread đó. Nếu handler chậm, event queue tích lũy, tăng khả năng `OVERFLOW`.

Kiến trúc gợi ý:

~~~text
WatchService thread
   │ take/poll → pollEvents → classify
   │
   ├── OVERFLOW ────────────> schedule full rescan
   │
   └── CREATE/DELETE/MODIFY -> dirtyPaths set / bounded task queue
                                        │
                                        ▼
                               Worker kiểm tra trạng thái thật
                                        │
                                        ▼
                               Update chỉ mục idempotent
~~~

Các quy tắc:

- Worker pool và queue cần **giới hạn** để tránh bộ nhớ tăng vô hạn.
- Có thể **deduplicate theo Path**: nhiều MODIFY cho cùng path chỉ cần một lần kiểm tra trạng thái sau cùng.
- Worker phải chịu được `NoSuchFileException`: file có thể biến mất trước khi đọc. Điều đó bình thường trong thiết kế theo dõi bất đồng bộ.
- Một file có thể được sửa lần nữa trong lúc worker đang đọc; có thể cần recheck version/hash sau khi xử lý.
- Không tự chia sẻ mutable `Map`/`Set` giữa watcher và worker nếu thiếu synchronized/concurrent collection.
- Nếu registration key đã invalid hoặc WatchService đóng, worker không được tùy tiện cho rằng sẽ có event tiếp theo để bù trạng thái.
- Cần xử lý shutdown/interrupt: `take()` có thể ném `InterruptedException`, đóng watcher khiến thread đang chờ ném `ClosedWatchServiceException`; dừng đúng vòng đời.

Tuy `WatchService` được thiết kế có thể sử dụng với nhiều consumer, ứng dụng đơn giản thường để **một thread sở hữu việc lấy key và reset sau khi xử lý batch**, tránh hai thread xử lý cùng một registration theo cách khó kiểm soát. Nếu nhiều consumer, cần đảm bảo `reset()` chỉ gọi sau khi sự kiện của key đã được xử lý xong theo giao thức của ứng dụng.

## 14. Hạn chế theo nền tảng và provider

WatchService dùng cơ chế thông báo native của hệ điều hành khi có, hoặc cơ chế khác như polling nếu không có native support. Điều này làm hành vi phụ thuộc:

| Môi trường/đặc tính | Cần lưu ý |
| --- | --- |
| Linux, Windows, macOS | Thời điểm giao sự kiện, cách gộp event, metadata được báo có thể khác nhau |
| Network FS / ổ đĩa đồng bộ cloud | Có thể chậm, thiếu, khác hành vi hoặc không đáp ứng kỳ vọng realtime |
| ZIP FS, file system ảo/provider riêng | Không mặc nhiên hỗ trợ watch; tạo/đăng ký có thể không được provider hỗ trợ |
| Thư mục bị xóa, rename, mất quyền | Registration có thể invalid; `reset() == false` |
| Rất nhiều thay đổi liên tục | Queue có thể quá tải dẫn tới `OVERFLOW` |
| Symlink, mounted folders | Cần chính sách phạm vi theo dõi và kiểm soát permission |
| Thay đổi metadata | Không có hợp đồng portable rằng mọi metadata change đều được báo giống nhau qua MODIFY |

Không sử dụng WatchService làm lớp **kiểm toán bảo mật duy nhất** hoặc cơ sở tính toán tài chính đòi hỏi mọi thao tác được ghi nhận chính xác. Trong các bài toán đó, cần hệ thống event log/transaction đáng tin, hoặc trạng thái chuẩn từ database, kết hợp watcher như cơ chế tối ưu để phát hiện cần đồng bộ.

## 15. Exceptions và lỗi thường gặp

| Hiện tượng | Nguyên nhân hoặc ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| `UnsupportedOperationException` khi tạo/register | Provider không hỗ trợ watcher hoặc event kind | Xem capabilities, fallback polling/reconciliation hoặc chọn provider khác |
| `IOException` | Không thể mở, đăng ký hoặc truy cập tài nguyên theo yêu cầu | Log đủ bối cảnh, kiểm tra path/quyền/file system |
| `ClosedWatchServiceException` | Thao tác trên watcher đã đóng hoặc thread đang chờ bị đánh thức do đóng | Kết thúc worker/watcher loop đúng lifecycle |
| `InterruptedException` khi `take()/poll(timeout)` | Thread được interrupt khi chờ | Thực thi chính sách hủy và bảo toàn trạng thái interrupt khi thích hợp |
| `WatchKey.reset() == false` | Registration không còn hợp lệ | Gỡ khỏi registry, xem xét đăng ký lại nếu directory phục hồi |
| `OVERFLOW` | Có thể đã bỏ event | Quét lại thư mục và đối chiếu snapshot |
| `ENTRY_MODIFY` phát nhiều lần | Provider có thể báo/gộp nhiều thay đổi | Debounce, idempotent updates, dựa trạng thái thật |
| Không thấy file trong `Files.exists()` sau CREATE | File bị xóa/rename nhanh hoặc thay đổi race | Đối chiếu trạng thái cuối, không tin sự kiện là snapshot |
| Không thấy event trong thư mục con | Đăng ký không tự recursive | Đăng ký các subdirectories phù hợp |
| Chỉ nhận batch đầu rồi ngừng | Quên `key.reset()` hoặc key invalid | Reset đúng vị trí, kiểm tra boolean |
| Chờ mãi ở `take()` | Không có event hoặc chưa shutdown, lỗi đăng ký | Dùng timeout/close/interrupt phù hợp với yêu cầu |
| Sai đường dẫn được xử lý | Hiểu `event.context()` thành đường dẫn tuyệt đối | Dùng `((Path) key.watchable()).resolve((Path) context)` |

**Trường hợp tệp đang được rename:** `Files.exists(path)` có thể trả false vì lỗi I/O, thiếu quyền hoặc symlink không đúng chứ không chỉ vì file thực sự bị xóa. Nếu cần quyết định chính xác, dùng thao tác đọc thông tin có xử lý ngoại lệ và kiểm tra chính sách symbolic link.

## 16. Checklist khi triển khai watcher thực tế

1. **Đã chọn đúng file system/provider chưa?** `Path` và `WatchService` có tương thích không?
2. **Đã register đúng thư mục chưa?** Đừng đăng ký “file mục tiêu” khi mục đích là theo dõi entry ở thư mục cha.
3. **Đã chọn ba `ENTRY_*` phù hợp chưa?** Nếu không muốn báo sửa, có thể chỉ đăng ký CREATE/DELETE, nhưng vẫn phải xử lý OVERFLOW.
4. **Đã duyệt mọi event trong key?** Không dừng sau event đầu rồi bỏ các entry còn lại.
5. **Đã xử lý OVERFLOW trước khi cast context?** `OVERFLOW` có thể có context null/không phải Path.
6. **Đã gọi reset sau batch và kiểm tra false?** Registration có thể bị hủy tự động.
7. **Có biết watcher không tự recursive?** Nếu cần theo dõi subtree, đăng ký từng thư mục và quét bổ sung khi thư mục mới xuất hiện.
8. **Có kiểm soát file readiness?** MODIFY không chứng minh writer hoàn tất; CREATE cũng không chứng minh file sẵn sàng.
9. **Có cơ chế reconcile?** Một event không phải event-log hoàn chỉnh; cần snapshot/dirty paths/periodic rescan.
10. **Có xử lý race?** File có thể biến mất, đổi tên, bị viết tiếp trước khi đọc.
11. **Có phân tách watcher thread khỏi xử lý nặng?** Tránh backlog/OVERFLOW.
12. **Có dừng sạch?** Đóng WatchService, ngừng worker, cancel key và giải phóng resource phù hợp.

## 17. Câu hỏi tự kiểm tra

1. Sự khác biệt cốt lõi giữa ba loại sự kiện là gì? **CREATE**: entry xuất hiện; **DELETE**: entry biến mất; **MODIFY**: entry được quan sát thay đổi.
2. File `a.txt` được tạo rồi liên tục ghi 100 khối dữ liệu. Có bắt buộc nhận đúng 1 CREATE và 100 MODIFY không? **Không**. Số MODIFY phụ thuộc provider và cơ chế gộp; có thể bị bỏ khi quá tải.
3. CREATE có chứng minh file đã ghi xong không? **Không**; có thể thấy entry ngay trước khi writer hoàn tất.
4. MODIFY có cung cấp nội dung mới/cũ không? **Không**; phải đọc trạng thái hiện tại và so sánh nếu cần.
5. DELETE có đồng nghĩa file bị xóa vĩnh viễn không? **Không**; có thể là move/rename khỏi thư mục hoặc chỉ mất tên trong thư mục đó.
6. Đăng ký `root` có tự bắt MODIFY của `root/sub/x.txt` không? **Không**; phải register `sub` riêng hoặc có cơ chế recursive do hệ thống triển khai.
7. Nhận event có `kind() == OVERFLOW` thì làm gì? **Quét đối chiếu (rescan/reconciliation)** vì có thể đã mất sự kiện.
8. `event.count() > 1` cho MODIFY có chứng minh đúng số lần người dùng nhấn Save không? **Không**; nó chỉ nói về sự kiện được gộp theo provider.
9. Nếu quên `key.reset()` sau `pollEvents()` thì sao? Key có thể không được báo lại theo kỳ vọng; phải reset sau khi xử lý.
10. Tại sao `key.watchable()` và `event.context()` thường cần ghép? Vì context của entry chuẩn là **đường dẫn tương đối** so với thư mục đã đăng ký.
11. Vì sao rename không có sự kiện riêng? `StandardWatchEventKinds` chỉ có CREATE, DELETE, MODIFY và OVERFLOW; move có thể được phản ánh qua đổi entry tên cũ/tên mới, tùy nền tảng.
12. Nếu watcher cho biết MODIFY nhưng `Files.readString(path)` ném `NoSuchFileException`, đó có phải lỗi API không? **Không nhất thiết**; entry có thể đã bị xóa/rename sau khi event được tạo.
13. Có nên dùng WatchService làm nguồn kiểm toán duy nhất nếu mọi thay đổi đều phải được ghi nhận không? **Không**; cần event log/transaction có bảo đảm riêng.
14. Có thể nhận OVERFLOW dù không đăng ký nó không? **Có**; đó là tín hiệu đặc biệt.
15. Vì sao ví dụ dùng poll với timeout mà không dùng take vô hạn? Để bài demo **không treo vô hạn** khi sự kiện không đến trên một môi trường cụ thể.

## Tài liệu API tham khảo

- [Java SE 17 — StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): định nghĩa chính thức của `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY` và `OVERFLOW`.
- [Java SE 17 — WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): cơ chế watcher, queue, take/poll, đóng và giới hạn nền tảng.
- [Java SE 17 — WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html): `pollEvents`, `reset`, `cancel`, `watchable`.
- [Java SE 17 — WatchEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html): `kind`, `context`, `count`.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `register` và xử lý đường dẫn.
- [Java — Watching a Directory for Changes](https://dev.java/learn/api/io/java-io/file-system/watching-dir-changes/): hướng dẫn WatchService và xử lý event.
