# WatchService: đăng ký đệ quy và theo dõi thư mục được tạo mới trong Java NIO

Trong Java NIO, `java.nio.file.WatchService` theo dõi **các sự kiện thay đổi của thư mục**: tạo, xóa, sửa entry và mất sự kiện do tràn hàng đợi. Khi xây trình theo dõi toàn bộ cây thư mục, khó khăn lớn nhất là: **WatchService không tự đăng ký đệ quy**. Đăng ký thư mục cha **không** mặc nhiên đăng ký các thư mục con đã tồn tại; khi một thư mục mới xuất hiện, ứng dụng cũng phải đăng ký nó và các thư mục con của nó.

Vì vậy một watcher đệ quy đúng cần hai phần phối hợp: **quét cây hiện có để đăng ký ban đầu** và **xử lý sự kiện `ENTRY_CREATE` để mở rộng phạm vi giám sát**. Ngoài ra cần kiểm soát race condition, mất sự kiện (`OVERFLOW`), vòng đời `WatchKey`, symbolic link và chính sách đối chiếu lại filesystem khi tính chính xác quan trọng.

## 1. WatchService quan sát cái gì?

Ba thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `WatchService` | Dịch vụ thu nhận thay đổi, được tạo từ `FileSystem.newWatchService()`. |
| `Path.register(watcher, kinds...)` | Đăng ký **một thư mục** với dịch vụ để quan sát các loại sự kiện. |
| `WatchKey` | Đại diện một đăng ký, được trả khi đăng ký và được đưa vào hàng đợi khi có sự kiện. |

Những loại sự kiện thường gặp:

- **`ENTRY_CREATE`**: một entry mới xuất hiện trong thư mục được đăng ký, có thể là file hoặc thư mục.
- **`ENTRY_DELETE`**: một entry biến mất khỏi thư mục đã đăng ký.
- **`ENTRY_MODIFY`**: một entry có thay đổi thuộc loại provider báo theo cơ chế giám sát.
- **`OVERFLOW`**: đã có sự kiện có thể bị mất hoặc bị loại bỏ; đây là tín hiệu cần đối chiếu lại filesystem.

`WatchEvent.context()` đối với các event entry chuẩn thường là **tên entry tương đối với thư mục được đăng ký**, không phải đường dẫn tuyệt đối. Vì vậy ứng dụng cần lưu quan hệ `Map<WatchKey, Path>` để ghép:

```java
Path directory = registeredDirectories.get(key);
Path affected = directory.resolve((Path) event.context());
```

Đây là snippet; `event.context()` phải được cast phù hợp cho entry events; **không** xử lý `OVERFLOW` như một `Path` bình thường vì context của nó có thể là `null`.

### Vì sao chỉ đăng ký cha là chưa đủ?

```text
root/                 <- Đã register(root)
  report.txt          <- CREATE/DELETE/MODIFY có thể xuất hiện ở root
  docs/               <- Không tự được giám sát!
    guide.md          <- Sự kiện trực tiếp trong docs có thể không được thấy
    images/           <- Cũng không được giám sát
      logo.png
```

Đăng ký `root` chỉ theo dõi **entry nằm ngay trong root**. Muốn nhận sự kiện cho `docs/guide.md`, cần đăng ký `docs`; muốn theo dõi `docs/images/logo.png`, cần đăng ký `docs/images`.

**Không có một lời gọi chuẩn kiểu `watchRecursively(root)` trong WatchService API của Java SE 17.** Đăng ký đệ quy là thuật toán do ứng dụng viết bằng các API như `Files.walkFileTree`.

## 2. Hai pha của đăng ký đệ quy

**Pha A — Đăng ký các thư mục đã tồn tại:**

1. Kiểm tra đường dẫn gốc là thư mục và có quyền truy cập phù hợp.
2. Tạo một `WatchService`.
3. Duyệt cây thư mục với `Files.walkFileTree(root, visitor)`.
4. Trong `preVisitDirectory`, gọi `dir.register(watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY)`.
5. Lưu `WatchKey → Path` để khi nhận sự kiện biết thư mục chứa entry.

**Pha B — Đăng ký thư mục mới khi đang chạy:**

1. Lấy `WatchKey` từ `watcher.take()` hoặc `watcher.poll(...)`.
2. Tra thư mục tương ứng trong map, duyệt `key.pollEvents()`.
3. Nếu nhận `ENTRY_CREATE` và entry vừa tạo hiện là thư mục, gọi **đăng ký đệ quy trên chính thư mục mới**, không chỉ đăng ký một cấp.
4. Xử lý business event theo yêu cầu, sau đó gọi `key.reset()`.
5. Nếu `reset() == false`, khóa không còn hợp lệ; xóa khỏi map và quyết định có cần khôi phục/đăng ký lại hay không.

Sơ đồ:

```text
root/ ── walkFileTree ──> watch root, old/, old/sub/
  |
  +── ENTRY_CREATE new/ ──> isDirectory(new/, NOFOLLOW_LINKS)?
                                  |
                                 Có
                                  |
                                  v
                         walkFileTree(new/)
                           ├── register(new/)
                           └── register(new/sub/) nếu đã tồn tại

Mọi entry nằm dưới new/sub/ xuất hiện SAU khi đăng ký thành công
có thể được đưa vào hàng đợi WatchService của new/sub/.
```

**Lý do cần `walkFileTree(newDir)` thay vì chỉ `newDir.register(...)`:** bên khác có thể tạo cả `new/sub/deep` rất nhanh trước khi event của `new` được xử lý. Khi ấy việc duyệt cây mới có thể tìm được các thư mục con đã xuất hiện, dù ứng dụng chưa kịp theo dõi chúng lúc được tạo.

## 3. Hàm đăng ký đệ quy dùng Files.walkFileTree

API `Files.walkFileTree` duyệt từng directory và cho phép register đúng ở thời điểm vào thư mục:

```java
// Snippet: watcher là WatchService đang mở,
// directories là Map<WatchKey, Path>.
Files.walkFileTree(root, new SimpleFileVisitor<>() {
    @Override
    public FileVisitResult preVisitDirectory(
            Path dir, BasicFileAttributes attrs) throws IOException {
        WatchKey key = dir.register(watcher,
                StandardWatchEventKinds.ENTRY_CREATE,
                StandardWatchEventKinds.ENTRY_DELETE,
                StandardWatchEventKinds.ENTRY_MODIFY);
        directories.put(key, dir);
        return FileVisitResult.CONTINUE;
    }
});
```

Đoạn này **không độc lập**: cần các imports từ `java.nio.file`, `java.nio.file.attribute.BasicFileAttributes`, `java.io.IOException`, và các biến `root`, `watcher`, `directories`.

Mặc định overload trên không đi theo symbolic link. Khi phải giới hạn cây trong một root đáng tin cậy, **không tùy tiện bật `FOLLOW_LINKS`**, vì symlink có thể tạo vòng hoặc dẫn ra ngoài vùng cho phép. Nếu ứng dụng chủ động hỗ trợ symlink, cần giải bài toán canonical path, quyền truy cập, vòng lặp và chính sách giới hạn phạm vi.

`preVisitDirectory` có thể ném `IOException`/`AccessDeniedException` hoặc provider không hỗ trợ đăng ký. Tùy yêu cầu, ứng dụng nên ghi nhận lỗi và tiếp tục với nhánh khác, hoặc coi đây là lỗi khiến watcher chưa giám sát đầy đủ. Đừng thông báo “theo dõi toàn bộ” nếu có nhánh không đăng ký thành công.

## 4. Chương trình Java 17+ hoàn chỉnh: theo dõi thư mục mới và con cháu

Chương trình tự tạo một cây thư mục tạm, đăng ký ban đầu, tạo một subtree mới rồi đợi `ENTRY_CREATE` của thư mục cha mới. Khi xử lý sự kiện đó, nó dùng `walkFileTree` để đăng ký cả subtree (bao gồm thư mục con đã có), sau đó tạo file nằm sâu bên trong để chứng minh watcher đã giám sát được thư mục mới.

Ví dụ sử dụng **một thread**, không cần chương trình bên ngoài tạo file. Kết quả được in ở dạng đường dẫn tương đối để không phụ thuộc vị trí thư mục tạm trên Windows/Linux/macOS.

Lưu thành **`RecursiveWatchDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

import static java.nio.file.StandardWatchEventKinds.*;

public class RecursiveWatchDemo {
    private static void registerTree(Path start, WatchService watcher,
                                     Map<WatchKey, Path> directories)
            throws IOException {
        Files.walkFileTree(start, new SimpleFileVisitor<>() {
            @Override
            public FileVisitResult preVisitDirectory(
                    Path dir, BasicFileAttributes attrs) throws IOException {
                WatchKey key = dir.register(watcher,
                        ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);
                directories.put(key, dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    private static void awaitCreated(Path expected, WatchService watcher,
                                     Map<WatchKey, Path> directories)
            throws IOException, InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            WatchKey key = watcher.poll(1, TimeUnit.SECONDS);
            if (key == null) {
                continue;
            }

            Path dir = directories.get(key);
            boolean seen = false;
            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == OVERFLOW) {
                    throw new IOException("WatchService overflow: need rescan");
                }
                if (dir == null) {
                    continue;
                }
                Path child = dir.resolve((Path) event.context());
                if (event.kind() == ENTRY_CREATE) {
                    if (Files.isDirectory(child, LinkOption.NOFOLLOW_LINKS)) {
                        registerTree(child, watcher, directories);
                    }
                    if (child.equals(expected)) {
                        seen = true;
                    }
                }
            }

            if (!key.reset()) {
                directories.remove(key);
            }
            if (seen) {
                return;
            }
        }
        throw new IOException("Timed out waiting for " + expected.getFileName());
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("recursive-watch-");
        try {
            Files.createDirectories(root.resolve("existing/deep"));
            try (WatchService watcher = FileSystems.getDefault()
                    .newWatchService()) {
                Map<WatchKey, Path> directories = new HashMap<>();
                registerTree(root, watcher, directories);
                System.out.println("initial directories=" + directories.size());

                Path fresh = root.resolve("new");
                Files.createDirectories(fresh.resolve("sub"));
                awaitCreated(fresh, watcher, directories);
                System.out.println("after new subtree=" + directories.size());

                Path file = fresh.resolve("sub/hello.txt");
                Files.writeString(file, "hello");
                awaitCreated(file, watcher, directories);
                System.out.println("created=" +
                        root.relativize(file).toString().replace('\\', '/'));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder())
                        .toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac -encoding UTF-8 RecursiveWatchDemo.java
java RecursiveWatchDemo
```

Stdout đã được xác nhận bằng biên dịch và chạy thực tế trên một filesystem hỗ trợ WatchService:

```text
initial directories=3
after new subtree=5
created=new/sub/hello.txt
```

**Phân tích từng bước:**

1. Trước khi đăng ký, ví dụ tạo `root/`, `root/existing/` và `root/existing/deep/`. Duyệt cây đã có sẽ đăng ký đúng **3 thư mục**.
2. `Files.createDirectories(root.resolve("new/sub"))` tạo `new/` và `new/sub/`. Khi observer xử lý `ENTRY_CREATE` của `new`, cả hai thư mục mới đã tồn tại.
3. `registerTree(new, ...)` đi xuống `new/sub/` và tạo thêm hai đăng ký, nên tổng là **5**.
4. Chương trình **đợi đăng ký hoàn tất rồi mới tạo file** `new/sub/hello.txt`. Đây là điểm rất quan trọng để tránh race trong demo: nếu tạo file trước khi `new/sub` được đăng ký, sự kiện của file có thể không được ghi nhận.
5. Khi source thư mục `new/sub/` phát `ENTRY_CREATE`, `context()` là tên `hello.txt`, ghép với `Path` của khóa thành đường dẫn chính xác.
6. Hàm dùng `watcher.poll(1, TimeUnit.SECONDS)` để không chờ vĩnh viễn trong demo; deadline tổng thể giới hạn 5 giây. Nếu provider/file system không hỗ trợ sự kiện kịp thời, nó báo lỗi thay vì khẳng định mọi môi trường đều có output giống nhau.
7. Mỗi key đã nhận được gọi `reset()`. Nếu key invalid, map được cập nhật. Cuối cùng `try-with-resources` đóng WatchService và `finally` dọn cây thư mục tạm sau khi đã dừng giám sát.

**Phạm vi ví dụ:** cố ý chỉ chờ hai event cụ thể, ném lỗi khi nhận `OVERFLOW` và không triển khai recovery đầy đủ. Để xây watcher production, xem các chiến lược rescan, giám sát quyền truy cập và dừng dịch vụ ở các phần tiếp theo.

## 5. Tại sao đăng ký thư mục mới vẫn có khoảng trống sự kiện?

Đây là điểm cần hiểu sâu nhất. Xét trật tự sau:

```text
T0: root đã được đăng ký.
T1: Tiến trình khác tạo root/new/.
T2: Tiến trình khác tạo root/new/a.txt.
T3: Thread watcher lấy ENTRY_CREATE của root/new/.
T4: Watcher mới gọi register(root/new/).
```

Sự kiện `a.txt` ở **T2** xảy ra trước khi `root/new/` được register tại **T4**. `WatchService` không có lời hứa cung cấp lịch sử thay đổi trước khi đăng ký, nên ứng dụng **có thể bỏ lỡ sự kiện tạo `a.txt`**, dù hiện tại file đó tồn tại.

Đăng ký `new/` và các thư mục con bằng `walkFileTree` chỉ giải quyết **phạm vi các directory hiện còn tồn tại**, không tái tạo đầy đủ những sự kiện file đã bị bỏ lỡ.

### Chiến lược: đăng ký rồi đối chiếu trạng thái

Khi cần đồng bộ file đáng tin, không chỉ phụ thuộc `ENTRY_CREATE`:

1. Đăng ký các thư mục trong subtree mới nhanh nhất có thể.
2. Sau khi đăng ký, quét danh sách file/thư mục hiện tại của subtree.
3. So sánh với **snapshot/index trạng thái đã biết**, phát hiện file mới, file đã xóa, file đã sửa, có thể dựa trên metadata và khi cần là hash nội dung.
4. Xử lý event trong lúc quét cùng quá trình đối chiếu; thiết kế **idempotency/deduplication** vì một file có thể vừa xuất hiện trong scan, vừa xuất hiện trong event queue.
5. Nếu có `OVERFLOW` hoặc nghi ngờ thiếu dữ liệu, quét lại subtree/root theo chính sách.

Không có phép quét + register nào mặc nhiên tạo ra một **snapshot atomic của toàn bộ cây filesystem đang bị sửa đồng thời**. Nếu thực sự cần bảo đảm không mất thay đổi giữa nhiều tiến trình, cân nhắc giao thức phối hợp writer, snapshot filesystem, change journal native hoặc cơ chế lưu lịch sử giao dịch; `WatchService` chỉ là nguồn thông báo, không phải log sự kiện bền vững.

## 6. Cách đối chiếu (reconciliation) thay vì tin mọi event là đầy đủ

Ứng dụng đồng bộ thư mục thường giữ index:

```text
Map<Path, FileInfo> knownFiles
Map<WatchKey, Path> registeredDirectories

FileInfo có thể chứa:
  isDirectory
  size
  lastModifiedTime
  optional fileKey / contentHash
```

Một vòng reconciliation:

```text
Scan filesystem root
     |
     v
Lập snapshot quan sát hiện tại
     |
     +-- Path mới: bổ sung/index, xử lý ingest
     +-- Path mất: đánh dấu/xử lý delete
     +-- Metadata/hash đổi: cập nhật/xử lý modify
     |
     v
Đăng ký lại các directory còn thiếu
     |
     v
Áp dụng tiếp các event đã đến (dedup theo trạng thái/id)
```

Điều kiện vận hành quan trọng:

- `Files.exists(path)` và `Files.isDirectory(path)` chỉ là **trạng thái ở thời điểm gọi**. Entry có thể biến mất hoặc đổi loại ngay sau đó.
- Khi một file vừa được tạo, writer có thể chưa ghi xong. Nếu yêu cầu xử lý một file hoàn chỉnh, dùng quy ước publish qua rename, marker/manifest, kiểm tra kích thước ổn định hoặc phối hợp bên tạo file.
- Timestamp/kích thước có giới hạn độ phân giải và không chứng minh nội dung không đổi. Nếu correctness cao, cân nhắc content hash hoặc protocol phù hợp.
- Rename/move có thể được báo bằng chuỗi delete/create/modify khác nhau giữa provider; WatchService chuẩn không cung cấp transaction rename với cả source và destination một cách portable.
- Sau quét, ứng dụng có thể tiếp tục nhận event trùng cho cùng trạng thái; handler nên **idempotent** để tránh nhập lại cùng file nhiều lần.

## 7. OVERFLOW: không thể lờ đi như một event bình thường

`OVERFLOW` biểu thị rằng một phần sự kiện có thể đã bị bỏ sót. Không được làm như sau:

```java
// SAI: nếu OVERFLOW là event duy nhất, vẫn coi như đã đồng bộ.
if (event.kind() == OVERFLOW) {
    continue;
}
```

Khi xử lý filesystem cho mục đích đồng bộ, hãy **đánh dấu trạng thái không còn đáng tin** rồi thực hiện reconciliation trên root hoặc subtree tương ứng, tùy mức độ provider biết được. Có thể giảm áp lực bằng cách xử lý event nhanh, batch công việc sang worker queue và tránh chạy tác vụ tốn thời gian trong thread lấy events.

Ví dụ ý tưởng:

```java
// Snippet: scanAndReconcile là hàm do ứng dụng triển khai.
if (event.kind() == OVERFLOW) {
    needsFullRescan = true;
} else {
    // Xử lý entry event, tránh blocking lâu.
}
// Ở điểm thích hợp:
if (needsFullRescan) {
    scanAndReconcile(root);
    needsFullRescan = false;
}
```

Đây là **snippet**, không phải API có sẵn. Việc gọi quét toàn bộ có thể tốn chi phí lớn nên cần quota, coalescing và chính sách tần suất; không nên mặc định hàng đợi sự kiện sẽ giữ mọi thay đổi vô hạn.

## 8. WatchKey: nhận, pollEvents, reset và trường hợp vô hiệu hóa

Mẫu event loop căn bản:

```java
// Snippet: watcher và directories đã khai báo.
// Map chỉ được cập nhật trong thread event loop này.
while (running) {
    WatchKey key = watcher.take();  // Chờ key có tín hiệu.
    Path dir = directories.get(key);

    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == OVERFLOW) {
            scheduleRescan();
            continue;
        }

        if (dir == null) {
            continue;
        }
        Path affected = dir.resolve((Path) event.context());

        if (event.kind() == ENTRY_CREATE &&
                Files.isDirectory(affected, LinkOption.NOFOLLOW_LINKS)) {
            registerTree(affected, watcher, directories);
        }

        handleChange(affected, event.kind());
    }

    if (!key.reset()) {
        directories.remove(key);
        handleInvalidRegistration(dir);
    }
}
```

Đoạn mã trên là **pseudocode kiểu Java**; `running`, `scheduleRescan`, `registerTree`, `handleChange`, `handleInvalidRegistration` do ứng dụng xây dựng.

**Các nguyên tắc không được quên:**

- Một `WatchKey` có thể chứa **nhiều `WatchEvent`**; phải duyệt tất cả hoặc có chiến lược bỏ/scan lại rõ ràng.
- `WatchEvent.count()` cho biết số lần event cùng loại/context có thể đã bị gộp, không nhất thiết mỗi thay đổi cho một object event riêng.
- Sau xử lý, **`key.reset()`** cho phép tiếp tục nhận tín hiệu. Nếu quên reset, có thể khiến key không được đưa vào hàng đợi đúng như mong đợi.
- `reset() == false` nghĩa là key không còn hợp lệ; không xem thư mục đó vẫn được bảo vệ. Một thư mục bị xóa, filesystem mất kết nối, đăng ký bị hủy hoặc watcher đóng đều có thể liên quan.
- Không `cancel()` một key còn cần theo dõi; `key.cancel()` hủy đăng ký.
- Khi `watcher.close()`, thread đang chờ `take()`/`poll()` có thể bị đánh thức bằng `ClosedWatchServiceException`; quản lý shutdown một cách có chủ đích.

Sự kiện `ENTRY_DELETE` có thể báo một thư mục bị xóa khỏi cha. Không có ý nghĩa đi đăng ký vào path đó; hãy cập nhật index, xử lý các key con có thể bị vô hiệu hóa và chuẩn bị đăng ký lại nếu path được tạo lại.

## 9. Thư mục mới đã bị xóa hoặc thay thế trước khi register

Một tình huống race khác:

```text
root đã đăng ký
  |
  +-- CREATE root/tmp
  +-- DELETE root/tmp
  +-- CREATE root/tmp   (có thể là đối tượng khác)
  |
Watcher giờ mới xử lý ENTRY_CREATE đầu tiên.
```

Khi watcher thực hiện `Files.isDirectory(root/tmp)`, nó chỉ thấy **đối tượng đang tồn tại lúc đó** (nếu có), không bảo đảm đó là thư mục xuất hiện ở event đầu tiên. Sau khi kiểm tra, nó vẫn có thể bị xóa trước khi `register`.

Chiến lược đúng không phải “bắt buộc register thành công” bằng vòng retry vô hạn. Hãy:

- Chấp nhận `NoSuchFileException`/`NotDirectoryException` hoặc IOException phù hợp như trạng thái cây đã thay đổi, lên lịch rescan.
- Giới hạn số lần thử và giới hạn công việc mỗi chu kỳ.
- Không dùng đường dẫn ngoài phạm vi root; kiểm soát symbolic link/path traversal khi path chứa phần người dùng có thể tác động.
- Nếu thư mục gốc biến mất, quyết định watcher sẽ dừng, thử khôi phục theo deadline, hay theo dõi thư mục cha để biết khi root được tạo lại. Không thể mặc định watcher của root đã xóa sẽ tự sống lại.
- Dùng khóa/coordination với producer hoặc snapshot filesystem nếu nghiệp vụ đòi đảm bảo mạnh hơn mức “eventual reconciliation”.

## 10. Không đi theo symlink một cách vô tình

Với một cây chứa symbolic link:

```text
root/
  docs/
  external -> /outside-root/private
  loop -> root/
```

Nếu `Files.walkFileTree` được gọi với `FOLLOW_LINKS` không kiểm soát, crawler có thể đi ra ngoài khu vực được phép hoặc gặp vòng lặp đường dẫn. Do đó:

- Mặc định **không bật `FOLLOW_LINKS`** khi giám sát một cây root.
- Khi quyết định một `ENTRY_CREATE` có là directory để đăng ký hay không, dùng `Files.isDirectory(affected, LinkOption.NOFOLLOW_LINKS)`.
- Nếu cần hỗ trợ symlink theo sản phẩm, xác định chính sách: theo dõi đối tượng link, theo dõi target, hay bỏ qua. Kiểm tra quyền, giới hạn root thực, tránh vòng và suy luận thay đổi đường dẫn.
- Với cây do actor không đáng tin sửa đồng thời, `NOFOLLOW_LINKS` ở một điểm kiểm tra vẫn không loại bỏ mọi race TOCTOU khi path bị thay thế. Dùng APIs/giao thức quản lý quyền truy cập phù hợp rủi ro.

WatchService cũng không cam kết mọi thay đổi về metadata/symlink được báo giống nhau trên tất cả hệ điều hành.

## 11. Mở nhiều thư mục có thể tốn tài nguyên hệ thống

Mô hình “register mỗi directory” thường cần tài nguyên kernel/provider cho **mỗi đăng ký**, đặc biệt trên hệ điều hành có giới hạn số watcher/inotify watch. Một cây rất sâu hoặc nhiều thư mục có thể gặp hạn mức, thiếu file descriptor, hoặc lỗi khi đăng ký thêm.

Các biện pháp vận hành:

1. Đếm số thư mục đã đăng ký thực tế và số đăng ký lỗi.
2. Đặt giới hạn hợp lý về chiều sâu, số thư mục và thời gian scan nếu cây không tin cậy.
3. Có chiến lược degrade: thông báo một phần cây chưa được giám sát và thực hiện periodic scan hoặc từ chối khởi động tính năng.
4. Hạn chế event storm; xử lý nhanh và chuyển các tác vụ nặng sang queue có giới hạn.
5. Dọn key không còn hợp lệ để map không tăng vô hạn; đóng WatchService khi shutdown.
6. Khi hệ thống triển khai có network filesystem, container hoặc thiết bị gắn ngoài, kiểm thử đúng provider/mount, không suy ra hành vi native chỉ từ ví dụ trên filesystem cục bộ.

Việc đăng ký quá nhiều không được giải bằng cách “đăng ký root một lần là đủ”: theo API chuẩn, root register **không cung cấp recursive watch**.

## 12. Thời gian, thứ tự và nội dung sự kiện không phải nhật ký đáng tin

Các giới hạn cần nhớ:

| Vấn đề | Hậu quả | Phương án |
| --- | --- | --- |
| Sự kiện có thể trễ | File hiện đã đổi nhưng watcher xử lý sau. | Chấp nhận eventual consistency hoặc phối hợp writer. |
| Sự kiện có thể được gộp | Nhiều lần sửa không thành từng event riêng lẻ. | Đọc lại trạng thái thực, dùng `event.count()` để ghi nhận. |
| `OVERFLOW` | Một số sự kiện không còn trong queue. | Rescan và đồng bộ theo snapshot/index. |
| Tạo thư mục con quá nhanh | Thay đổi xảy ra trước khi register con. | Register cả subtree, sau đó reconcile. |
| Rename hoặc move | Có thể xuất hiện delete/create theo provider. | Phân tích trạng thái và protocol file thay vì dựa một event. |
| Symlink/permission thay đổi | Mất quyền, ra ngoài root, lỗi đăng ký. | Không follow mặc định; kiểm soát quyền và xử lý IOException. |
| Đường dẫn bị xóa rồi tạo lại | WatchKey cũ không tự ràng buộc tới đối tượng mới. | Đăng ký lại và reconcile khi cần. |
| Shutdown/close | Key invalid; thread chờ có thể nhận exception. | Đóng service có điều phối và giải phóng tài nguyên. |

**Không suy “đã thấy `ENTRY_MODIFY` là file đã ghi xong”.** Tác giả file có thể vẫn đang ghi, hoặc file được thay đổi thêm. Với pipeline ingest nghiêm ngặt, đặt hợp đồng publish cụ thể (ghi file tạm rồi rename khi sẵn sàng, sidecar marker, manifest, checksum...) và xử lý duplicate.

## 13. Xử lý ENTRY_CREATE của cả file và thư mục

Một handler thường có hai nhánh:

```java
// Snippet: affected đã được resolve từ key directory + context.
if (event.kind() == ENTRY_CREATE) {
    if (Files.isDirectory(affected, LinkOption.NOFOLLOW_LINKS)) {
        registerTree(affected, watcher, directories);
        // Quét và reconcile subtree để tìm các file đã có.
    } else if (Files.isRegularFile(
            affected, LinkOption.NOFOLLOW_LINKS)) {
        // Đưa file vào queue ingest có giới hạn, nếu đủ điều kiện.
    } else {
        // Entry không còn tồn tại/không phải regular file
        // hoặc trạng thái không kiểm tra được: hẹn rescan.
    }
}
```

Hãy **đăng ký subtree** trước khi dành nhiều thời gian xử lý nghiệp vụ để giảm cửa sổ bỏ lỡ events tương lai. Nếu nghiệp vụ xử lý file nặng, nên đưa nó vào worker queue có giới hạn thay vì xử lý trực tiếp trong thread lấy `WatchKey`, nhưng đồng thời phải có cơ chế backpressure và phối hợp snapshot/event để tránh mất consistency.

Đừng tin chỉ mỗi kiểm tra `Files.isDirectory` rồi khẳng định đó chính là directory được tạo bởi event: path có thể bị đổi giữa các bước. Chỉ có chính sách kết hợp reconciliation và giới hạn race mới mang lại độ tin cậy phù hợp.

## 14. Vòng đời và dừng watcher đúng cách

Một watcher có thể chạy trong thread riêng:

```java
// Snippet: thread phụ đang gọi watcher.take() trong vòng xử lý.
try {
    while (!Thread.currentThread().isInterrupted()) {
        WatchKey key = watcher.take();
        processKey(key);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
} catch (ClosedWatchServiceException e) {
    // Dịch vụ đã đóng: thoát vòng giám sát.
} finally {
    // Dọn state của thread này; chủ sở hữu sẽ đóng watcher
    // nếu chưa đóng từ đường điều khiển khác.
}
```

`processKey` là hàm ứng dụng được triển khai để pollEvents/reset và xử lý overflow. Với service chạy lâu, một luồng điều phối có thể gọi `watcher.close()` để giải phóng tài nguyên và làm `take()` đang chờ kết thúc theo cơ chế của API.

Trình tự shutdown nên xác định: ngừng chấp nhận công việc mới → báo thread watcher dừng/đóng service → giải phóng đăng ký → hoàn tất hoặc hủy các nhiệm vụ đã queue theo deadline → báo trạng thái cuối. **Không xóa toàn bộ map trong khi worker còn đang truy cập** nếu không có chính sách đồng bộ thread-safe.

Dùng `try-with-resources` với `WatchService` nếu chủ sở hữu của dịch vụ có vòng đời rõ ràng. `WatchService.close()` giải phóng tài nguyên, khác việc gọi `key.cancel()` cho từng thư mục.

## 15. Phân biệt nhu cầu “thông báo” và “phát hiện đầy đủ”

**Chỉ cần gợi ý làm mới giao diện:** WatchService có thể phù hợp. Nếu bỏ lỡ một vài event, giao diện có thể quét lại khi người dùng mở hoặc khi timer kích hoạt.

**Đồng bộ thư mục:** cần WatchService kết hợp snapshot/index và xử lý idempotent. Đăng ký lại khi có directory mới, rescan khi overflow và có periodic reconciliation để chống sai lệch kéo dài.

**Ingest file quan trọng:** cần hợp đồng file hoàn tất, queue bounded, xử lý retry/dedup, logging và recovery khi crash. WatchService không thể tự chứng minh publisher đã ghi xong.

**Audit đầy đủ mọi thay đổi trong cây:** WatchService chuẩn **không đủ làm log audit không mất sự kiện**. Cần change journal native, audit subsystem phù hợp hoặc producer viết nhật ký giao dịch bền vững, tùy hệ điều hành và yêu cầu pháp lý/kỹ thuật.

Khi muốn “theo dõi đệ quy”, hãy hỏi thêm câu kỹ thuật quan trọng: **Mục tiêu là thông báo cập nhật nhanh hay chứng minh toàn bộ trạng thái luôn nhất quán?** Chiến lược xử lý lỗi/scan khác nhau rõ rệt.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Không thấy file tạo trong `root/a/b` | Chỉ `register(root)`. | Duyệt `walkFileTree` và register mỗi thư mục. |
| Thấy thư mục mới nhưng không thấy file con | Chưa register directory mới, hoặc file đã tạo trước khi register. | Register toàn subtree, reconcile sau đăng ký. |
| Cast context gây lỗi/null | Coi `OVERFLOW` như entry event. | Kiểm tra kind trước rồi mới cast `(Path) event.context()`. |
| Lặp vài event rồi watcher dừng nhận | Quên `key.reset()`. | Reset sau khi poll/process; kiểm tra boolean trả về. |
| Map giữ key của thư mục đã xóa | Không xử lý `reset() == false`. | Xóa key, rescan/re-register khi thích hợp. |
| Bỏ sót sự kiện khi thay đổi nhanh | Event gộp hoặc `OVERFLOW`, registration race. | Dùng index/snapshot + reconciliation. |
| Đường dẫn affected sai | Dùng context là path tuyệt đối hoặc ghép với root thay vì thư mục key. | Dùng `directories.get(key).resolve(context)`. |
| Watcher nhìn ra ngoài vùng root | Tự ý đi theo symlink. | `NOFOLLOW_LINKS`, policy cho symlink, kiểm tra quyền. |
| File được xử lý khi còn dang dở | Xem `ENTRY_CREATE` hoặc `ENTRY_MODIFY` là tín hiệu “ghi xong”. | Giao thức publish/marker, xác minh file hoàn chỉnh. |
| CPU cao, queue tràn | Handler làm việc nặng hoặc producer tạo quá nhiều event. | Thread xem event ngắn, bounded queue, rescan có ngân sách. |
| Đóng watcher làm thread ném exception | `watcher.close()` làm `take()` ngừng chờ. | Bắt `ClosedWatchServiceException` trong shutdown. |
| Đăng ký lỗi khi cây lớn | Hạn mức kernel/provider/permission. | Giới hạn số watch, cảnh báo, fallback rescan. |

## 17. Bài tập thực hành

**Bài 1 — Bổ sung OVERFLOW recovery.** Thay `throw new IOException` khi gặp `OVERFLOW` trong demo thành đánh dấu `needsRescan`. Viết một hàm scan root để tìm file mới và register lại thư mục chưa được theo dõi. Giải thích vì sao cần dedup giữa event và scan.

**Bài 2 — Race trước đăng ký.** Sửa demo: tạo `root/new/sub/hello.txt` **trước** khi hàm `awaitCreated(root/new)` xử lý event. Theo dõi khả năng không thấy `ENTRY_CREATE` của file. Dùng scan ngay sau register để vẫn phát hiện file đã tồn tại.

**Bài 3 — Thư mục lồng sâu.** Tạo `root/a/b/c/d` trong một lệnh `Files.createDirectories` rồi quan sát số directory được register khi nhận `ENTRY_CREATE` của `a`. Sau đó tạo `d/file.txt` và xác minh được phát hiện.

**Bài 4 — Xóa rồi tạo lại.** Tạo một thư mục có watcher, xóa nó rồi tạo lại cùng tên. Quan sát `WatchKey.reset()` và các sự kiện ở thư mục cha. Giải thích vì sao phải register đối tượng mới và đối chiếu snapshot.

**Bài 5 — Symlink và bảo mật.** Trên hệ thống hỗ trợ symbolic links và có quyền tạo link, tạo một symlink trong root trỏ ra ngoài. Kiểm chứng watcher mẫu không đi theo link. Viết chính sách rõ ràng nếu sản phẩm yêu cầu hỗ trợ link mà không mở rộng phạm vi dữ liệu nhạy cảm.

**Bài 6 — File được ghi dần.** Một producer tạo file rồi ghi năm chunk cách nhau. Quan sát `ENTRY_CREATE/ENTRY_MODIFY` có thể khác nhau theo OS. Đưa ra quy tắc “file đã sẵn sàng” bằng rename từ file tạm sang tên chính thức hoặc marker riêng, thay vì suy luận từ event count.

**Bài 7 — Nhiều thay đổi/OVERFLOW.** Tạo hàng nghìn file ở thư mục thử nghiệm, đo event queue và thời gian xử lý. Không cố ý gây áp lực lên hệ thống sản xuất. Khi có `OVERFLOW` hoặc event không khớp snapshot, thử rescan và thống kê độ trễ.

**Bài 8 — Shutdown.** Chạy watcher trong thread phụ, cho thread chính đóng `WatchService` rồi `join()` có deadline. Xác nhận vòng lấy event thoát không kẹt và không để thread sống rò rỉ.

### Câu hỏi tự kiểm tra

1. Đăng ký `root` có tự theo dõi `root/sub/file.txt` không?
2. Vì sao xử lý `ENTRY_CREATE` của directory cần đăng ký **cả subtree mới**?
3. Tại sao một file tạo ngay sau directory có thể không có event dù `registerTree(newDir)` chạy thành công?
4. `WatchEvent.context()` có phải lúc nào cũng là đường dẫn tuyệt đối không?
5. Vì sao phải xử lý `OVERFLOW` bằng rescan?
6. Quên `key.reset()` gây vấn đề gì và `reset() == false` có ý nghĩa gì?
7. Vì sao nên dùng `NOFOLLOW_LINKS` khi giám sát cây có phạm vi tin cậy?
8. File đã có `ENTRY_CREATE` có chắc là đã ghi đủ nội dung để ingest chưa?
9. Khi cần audit không mất sự kiện, WatchService có phải nguồn lịch sử bền vững không?

## 18. Tài liệu chính thức

- [Java SE 21 — WatchService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchService.html): vòng đời dịch vụ, key, queue, close và hành vi provider.
- [Java SE 21 — WatchKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchKey.html): `pollEvents()`, `reset()`, `cancel()` và hiệu lực đăng ký.
- [Java SE 21 — WatchEvent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchEvent.html): `kind()`, `context()` và `count()`.
- [Java SE 21 — StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): các kind `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY`, `OVERFLOW`.
- [Java SE 21 — Files.walkFileTree](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.nio.file.FileVisitor)): duyệt và xử lý cây directory.
- [Java SE 21 — Path.register](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html#register(java.nio.file.WatchService,java.nio.file.WatchEvent.Kind...)): đăng ký watch cho từng directory.

**Ghi nhớ:** WatchService không theo dõi đệ quy một cách tự động. Dùng `Files.walkFileTree` đăng ký mọi thư mục hiện có; khi có `ENTRY_CREATE` cho thư mục mới, đăng ký **toàn bộ subtree**, xử lý `WatchKey.reset()` và `OVERFLOW`, đồng thời **reconcile filesystem state** để khắc phục race và event bị mất. Khi cần dữ liệu đúng tuyệt đối, phải bổ sung giao thức và nguồn sự thật mạnh hơn một luồng thông báo filesystem.
