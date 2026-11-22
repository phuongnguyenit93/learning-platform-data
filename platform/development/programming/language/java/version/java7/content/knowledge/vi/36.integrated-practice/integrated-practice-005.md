# Theo dõi thay đổi thư mục có cơ chế khôi phục sau OVERFLOW

## 1. Bài toán thực tế và mục tiêu

Bạn cần theo dõi một thư mục để cập nhật chỉ mục tài liệu, đồng bộ file, kích hoạt tác vụ nhập dữ liệu, hoặc phản ánh trạng thái file mới nhất lên giao diện. Với Java 17+ hiện đại, có thể sử dụng API `java.nio.file.WatchService` (có từ Java 7 và **vẫn được hỗ trợ**) để nhận thông báo khi entry trong thư mục được tạo, xóa hoặc sửa.

Tuy nhiên, một bộ theo dõi file đúng **không thể giả định mọi thay đổi đều đi qua hàng đợi sự kiện**. Nếu producer ghi quá nhanh hoặc consumer xử lý quá chậm, hệ thống có thể không giữ được tất cả sự kiện. `StandardWatchEventKinds.OVERFLOW` cho biết **có thể đã mất hoặc bỏ một số sự kiện**.

Yêu cầu quan trọng nhất của bài thực hành là: **khi xuất hiện `OVERFLOW`, không dựa tiếp vào chuỗi event thiếu hụt; phải quét lại trạng thái thư mục thực và đối soát với snapshot đã lưu**. Chương trình cần duy trì tính đúng đắn của **trạng thái hiện tại** theo khả năng quan sát của hệ thống file, chứ không hứa hẹn khôi phục lại toàn bộ lịch sử thay đổi đã mất.

Trong bài này:
- Theo dõi **các entry trực tiếp trong một thư mục**, gồm file và thư mục con như một entry; **không theo dõi đệ quy nội dung thư mục con**.
- Xử lý `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE`, `OVERFLOW`.
- Duy trì `snapshot` gồm kích thước, thời gian sửa, loại entry và `fileKey` (nếu hệ thống file cung cấp).
- Khi overflow hoặc đọc thuộc tính lỗi: đánh dấu trạng thái **dirty**, quét lại tất cả entry; chỉ thay snapshot cũ nếu quét thành công.
- Có `--demo` mô phỏng mất event để kiểm tra được việc khôi phục, không phải cố ép WatchService thật xảy ra overflow.

## 2. Hiểu chính xác cơ chế WatchService

Các thành phần đang được hỗ trợ trong Java hiện đại:

| API | Vai trò |
| --- | --- |
| `FileSystems.getDefault().newWatchService()` | Tạo dịch vụ lắng nghe thay đổi hệ thống file |
| `Path.register(watcher, ...)` | Đăng ký **thư mục** và các loại sự kiện cần quan sát |
| `WatchKey` | Đại diện đăng ký đang có; gắn với một thư mục |
| `watcher.take()` / `watcher.poll(...)` | Nhận key đã báo có sự kiện; `take()` chờ vô hạn còn `poll(timeout)` cho phép thực hiện việc kiểm tra định kỳ |
| `key.pollEvents()` | Lấy các event đang đợi cho key đó |
| `key.reset()` | Đưa key về trạng thái có thể nhận thông báo mới; `false` nghĩa là key đã mất hiệu lực |
| `WatchService.close()` | Giải phóng tài nguyên khi dừng theo dõi |

Ba loại sự kiện thông thường:

- `ENTRY_CREATE`: một entry xuất hiện trong thư mục, kể cả đổi tên/di chuyển từ nơi khác vào.
- `ENTRY_DELETE`: một entry biến mất, kể cả đổi tên/di chuyển đi nơi khác.
- `ENTRY_MODIFY`: entry được báo đã thay đổi. Hệ thống có thể gửi **nhiều sự kiện** cho một lần ghi; `count()` có thể lớn hơn 1.

`OVERFLOW` là sự kiện **đặc biệt**, tự động được quan sát khi dùng `WatchService`; **không cần đăng ký** nó trong `Path.register`. `OVERFLOW` có `context()` phụ thuộc implementation, thậm chí `null`; **không ép kiểu `context()` thành `Path` trước khi kiểm tra `kind()`**.

Đối với các sự kiện entry thông thường, `context()` thường là **đường dẫn tương đối** từ thư mục đã đăng ký. Khi cần đường dẫn đầy đủ, dùng `root.resolve(relative)`; không hiểu sai thành đường dẫn tuyệt đối.

### Vì sao phải reset key?

```text
WatchKey READY
    │ phát hiện event
    ▼
WatchKey SIGNALED ──► watcher.poll()/take() ──► key.pollEvents()
                                                      │
                                             xử lý / ghi nhận
                                                      │
                                             key.reset()
                                               ├── true ─► READY
                                               └── false ─► INVALID
```

Nếu bỏ `reset()`, key có thể không được xếp lại để gửi thông báo tiếp theo. Nếu `reset()` trả `false`, thư mục có thể đã bị xóa hoặc không thể truy cập: **đây không phải `OVERFLOW` thông thường**; cần xử lý tình huống mất thư mục và đăng ký lại khi đã có một thư mục hợp lệ. Ví dụ bên dưới chọn **dừng với thông báo rõ ràng** khi key mất hiệu lực, để không giả vờ vẫn đang theo dõi.

## 3. Nguyên tắc thiết kế cơ chế khôi phục

### 3.1. Snapshot và đối soát

Giả sử snapshot đang lưu:

```text
known = {
  kept.txt    -> size=3,  modified=t0
  removed.txt -> size=3,  modified=t0
}
```

Trong thời gian xử lý chậm, ứng dụng khác sửa `kept.txt`, xóa `removed.txt`, tạo `added.txt`. Nếu hàng đợi báo `OVERFLOW`, ta **không thể biết chuỗi event đầy đủ** nhưng có thể đọc trạng thái hiện tại:

```text
fresh = {
  kept.txt  -> size=6, modified=t1
  added.txt -> size=3, modified=t1
}
```

Lấy hợp của hai tập đường dẫn để so sánh:

| Trạng thái snapshot | Trạng thái hiện tại | Kết luận đối soát |
| --- | --- | --- |
| Không có | Có | `CREATE` |
| Có | Không có | `DELETE` |
| Có | Có, thuộc tính khác | `MODIFY` |
| Có | Có, thuộc tính giống | Không phát hiện khác biệt tại mức snapshot |

**Đây là mô hình đồng bộ trạng thái**, không phải khôi phục lịch sử theo thứ tự. Một file được tạo rồi xóa giữa hai lần quét có thể không để lại dấu vết; một file bị sửa nội dung nhưng giữ cùng kích thước/thời gian sửa và `fileKey` có thể bị bỏ sót khi chỉ so metadata. Nếu nghiệp vụ cần xác minh byte-for-byte, phải bổ sung hash hoặc kiểm chứng nội dung; vẫn **không thể tái tạo thay đổi ngắn ngủi đã biến mất** từ snapshot sau cùng.

### 3.2. Khi nào phải full rescan?

Đánh dấu `dirty` và quét lại khi:
1. Gặp `OVERFLOW`, vì các event thông thường của cùng batch **không đủ tin cậy** để mô tả toàn bộ thay đổi.
2. Đọc thuộc tính cho một entry bị lỗi, vì có thể đã mất đồng bộ snapshot.
3. Đến kỳ kiểm tra nền (ví dụ mỗi 30 giây) để giảm nguy cơ sai lệch do race hoặc một số hệ thống file không cung cấp notification đủ tốt.

**Quy tắc commit:** tạo `fresh` hoàn chỉnh rồi so với `known`. **Chỉ khi quét toàn thư mục thành công** mới thay `known = fresh`. Nếu quét lỗi, giữ snapshot cũ và thử lại sau, không báo `RECOVER DONE` giả. Kết quả giữa hai lần quét vẫn có thể bị ảnh hưởng do thư mục thay đổi đồng thời; theo dõi dài hạn cần tiếp tục nhận event và đối soát định kỳ.

### 3.3. Luồng điều khiển

```text
Tạo WatchService, register thư mục
                │
                ▼
        Chụp snapshot ban đầu
                │
                ▼
      poll(timeout) lấy WatchKey
                │
       ┌────────┴────────┐
       │ Có event         │ Không có event
       ▼                  ▼
  pollEvents()        Đến kỳ rescan?
       │                  │
       ├── có OVERFLOW    └── Có ─┐
       │      │                  │
       │      ▼                  │
       │   dirty=true            │
       │                         │
       └── chỉ event thường ─► reconcile từng path
                 │
             key.reset()
                 │
              valid?
              ├── false: dừng/cần đăng ký lại
              └── true
                     │
               dirty / đến kỳ?
                 ├── Có: quét toàn thư mục + diff + commit
                 └── Không: quay lại poll
```

## 4. Chương trình hoàn chỉnh: DirectoryRecoveryWatcher.java

Ví dụ dùng **Java 17+**, không phụ thuộc thư viện bên ngoài. `record Stamp` (ổn định từ Java 16) được dùng để so sánh snapshot dễ đọc. File và thư mục con đều được xem như **entry trực tiếp**; không đi theo symbolic link khi đọc thuộc tính (`NOFOLLOW_LINKS`).

Cách tổ chức:
- `scan()`: lấy snapshot toàn bộ các entry ngay dưới root.
- `reconcileOne()`: cập nhật snapshot từ một đường dẫn có event thông thường, tránh quét toàn bộ cho mọi lần ghi.
- `reconcile()`: quét lại, so với snapshot cũ, in các khác biệt; chỉ commit sau thành công.
- `watchForever()`: gom các event theo đường dẫn, xử lý `OVERFLOW`, `reset`, retry và quét kiểm tra định kỳ.
- `--demo`: tạo thư mục tạm và tạo 3 thay đổi không được đưa qua event loop, sau đó **gọi đúng hàm khôi phục dùng bởi nhánh OVERFLOW thật**. Nhờ vậy output kiểm thử xác định và không phụ thuộc nền tảng.

Lưu dưới tên **`DirectoryRecoveryWatcher.java`** (UTF-8):

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
import java.util.*;
import java.util.concurrent.TimeUnit;
import static java.nio.file.StandardWatchEventKinds.*;

public class DirectoryRecoveryWatcher implements AutoCloseable {
    record Stamp(boolean directory, long size, FileTime modified, String fileKey) {}

    private final Path root;
    private final WatchService watcher;
    private Map<Path, Stamp> known;

    DirectoryRecoveryWatcher(Path dir) throws IOException {
        root = dir.toAbsolutePath().normalize();
        watcher = FileSystems.getDefault().newWatchService();
        try {
            if (!Files.isDirectory(root)) {
                throw new IOException("Not a directory: " + root);
            }
            root.register(watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);
            known = scan();
        } catch (IOException | RuntimeException e) {
            watcher.close();
            throw e;
        }
    }

    private static Stamp readStamp(Path path) throws IOException {
        try {
            BasicFileAttributes a = Files.readAttributes(
                    path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            return new Stamp(a.isDirectory(), a.size(), a.lastModifiedTime(),
                    String.valueOf(a.fileKey()));
        } catch (NoSuchFileException e) {
            return null; // Entry vanished between listing and stat.
        }
    }

    private Map<Path, Stamp> scan() throws IOException {
        Map<Path, Stamp> result = new HashMap<>();
        try (DirectoryStream<Path> entries = Files.newDirectoryStream(root)) {
            for (Path path : entries) {
                Stamp stamp = readStamp(path);
                if (stamp != null) {
                    result.put(path.toAbsolutePath().normalize(), stamp);
                }
            }
        } catch (DirectoryIteratorException e) {
            throw e.getCause(); // Treat an interrupted directory scan as failed.
        }
        return result;
    }

    private void report(String label, Path path, Stamp before, Stamp after) {
        String kind = before == null ? "CREATE"
                : after == null ? "DELETE"
                : !before.equals(after) ? "MODIFY" : null;
        if (kind != null) {
            System.out.println(label + " " + kind + " " + root.relativize(path));
        }
    }

    private boolean reconcile(String label) {
        try {
            Map<Path, Stamp> fresh = scan();
            SortedSet<Path> all = new TreeSet<>(Comparator.comparing(Path::toString));
            all.addAll(known.keySet());
            all.addAll(fresh.keySet());
            for (Path path : all) {
                report(label, path, known.get(path), fresh.get(path));
            }
            known = fresh; // Commit only after a successful complete scan.
            System.out.println(label + " DONE entries=" + known.size());
            return true;
        } catch (IOException e) {
            System.err.println(label + " RETRY: " + e.getMessage());
            return false; // Keep old snapshot; retry instead of claiming recovery.
        }
    }

    private void reconcileOne(Path path) throws IOException {
        Stamp after = readStamp(path);
        Stamp before = known.get(path);
        report("LIVE", path, before, after);
        if (after == null) {
            known.remove(path);
        } else {
            known.put(path, after);
        }
    }

    void watchForever() throws InterruptedException {
        System.out.println("WATCHING " + root);
        boolean dirty = false;
        long lastScan = System.nanoTime();
        while (true) {
            WatchKey key = watcher.poll(2, TimeUnit.SECONDS);
            if (key != null) {
                boolean overflow = false;
                SortedSet<Path> changed = new TreeSet<>(Comparator.comparing(Path::toString));
                for (WatchEvent<?> event : key.pollEvents()) {
                    if (event.kind() == OVERFLOW) {
                        overflow = true;
                        continue; // OVERFLOW context need not be a Path.
                    }
                    if (!(event.context() instanceof Path relative)) {
                        overflow = true;
                        continue;
                    }
                    Path path = root.resolve(relative).normalize();
                    if (!path.startsWith(root)) {
                        overflow = true;
                    } else {
                        changed.add(path);
                    }
                }

                if (overflow) {
                    dirty = true; // Drop unreliable deltas; rescan the directory.
                    System.out.println("OVERFLOW: snapshot reconciliation requested");
                } else if (!dirty) {
                    for (Path path : changed) {
                        try {
                            reconcileOne(path);
                        } catch (IOException e) {
                            System.err.println("Read failed; full rescan required: "
                                    + e.getMessage());
                            dirty = true;
                            break;
                        }
                    }
                }

                if (!key.reset()) {
                    System.err.println("WatchKey invalid: directory removed or inaccessible.");
                    return; // Recreate/re-register after the directory is restored.
                }
            }

            if (dirty || System.nanoTime() - lastScan
                    >= TimeUnit.SECONDS.toNanos(30)) {
                if (reconcile(dirty ? "RECOVER" : "CHECK")) {
                    dirty = false;
                }
                lastScan = System.nanoTime();
            }
        }
    }

    @Override
    public void close() throws IOException {
        watcher.close();
    }

    private static void demo() throws IOException {
        Path dir = Files.createTempDirectory("watch-demo-");
        Path kept = dir.resolve("kept.txt");
        Path removed = dir.resolve("removed.txt");
        Path added = dir.resolve("added.txt");
        try {
            Files.writeString(kept, "old", StandardCharsets.UTF_8);
            Files.writeString(removed, "bye", StandardCharsets.UTF_8);
            try (DirectoryRecoveryWatcher monitor = new DirectoryRecoveryWatcher(dir)) {
                Files.writeString(kept, "longer", StandardCharsets.UTF_8);
                Files.delete(removed);
                Files.writeString(added, "new", StandardCharsets.UTF_8);
                System.out.println("SIMULATED OVERFLOW");
                monitor.reconcile("RECOVER"); // Same recovery method as real OVERFLOW.
            }
        } finally {
            Files.deleteIfExists(added);
            Files.deleteIfExists(kept);
            Files.deleteIfExists(removed);
            Files.deleteIfExists(dir);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--demo".equals(args[0])) {
            demo();
        } else if (args.length == 1) {
            try (DirectoryRecoveryWatcher monitor =
                    new DirectoryRecoveryWatcher(Path.of(args[0]))) {
                monitor.watchForever();
            }
        } else {
            System.out.println("Usage: java DirectoryRecoveryWatcher <directory>");
            System.out.println("   or: java DirectoryRecoveryWatcher --demo");
        }
    }
}
```

### 4.1. Biên dịch và kiểm tra nhánh khôi phục

```bash
javac --release 17 -encoding UTF-8 DirectoryRecoveryWatcher.java
java DirectoryRecoveryWatcher --demo
```

Stdout chính xác của `--demo` (đã biên dịch/chạy kiểm chứng):

```text
SIMULATED OVERFLOW
RECOVER CREATE added.txt
RECOVER MODIFY kept.txt
RECOVER DELETE removed.txt
RECOVER DONE entries=2
```

Ở chế độ demo, watcher được tạo và chụp snapshot trước khi các file bị thay đổi. Các event thực được phát ra trong hệ thống file (nếu có) **không được lấy khỏi hàng đợi**; thay vào đó code chủ động gọi `reconcile("RECOVER")` để chứng minh thao tác **khôi phục trạng thái sau khi mất event**. Dòng `SIMULATED OVERFLOW` **không tuyên bố JVM đã thực sự phát ra `OVERFLOW`**.

Kết quả đối soát là tất định theo trạng thái file đã tạo:
- `added.txt`: không có trong snapshot cũ, có trong snapshot mới.
- `kept.txt`: tồn tại cả hai, nhưng kích thước từ 3 sang 6 byte.
- `removed.txt`: có trong snapshot cũ, biến mất trong snapshot mới.

### 4.2. Theo dõi một thư mục thật

Tạo thư mục trước rồi chạy (ví dụ đường dẫn có thể thay theo hệ điều hành):

```bash
java DirectoryRecoveryWatcher "/duong/dan/thu-muc-can-theo-doi"
```

Trên Windows có thể truyền một đường dẫn thực tế như `"C:\\data\\inbox"`. Chương trình chờ và in thông báo khi các entry **trực tiếp** xuất hiện, biến mất hoặc đổi thuộc tính. Ví dụ minh họa (thứ tự và số lần in không cố định):

```text
WATCHING <duong-dan-tuy-may>
LIVE CREATE new.txt
LIVE MODIFY new.txt
LIVE DELETE new.txt
CHECK DONE entries=0
```

Nếu WatchService báo `OVERFLOW`, chương trình có thể in `OVERFLOW: snapshot reconciliation requested` và sau đó `RECOVER ...` khi quét thành công. Không thể ấn định số event hay vị trí overflow trên tất cả filesystem; **không dùng đoạn stdout minh họa này như tiêu chí kiểm thử cố định**.

Dừng bằng **Ctrl+C**. `try-with-resources` đóng WatchService khi luồng `main` rời `watchForever()` bình thường hoặc khi exception được ném; khi dừng tiến trình trực tiếp, hệ điều hành sẽ giải phóng tài nguyên tiến trình.

## 5. Phân tích các điểm tránh mất đồng bộ

### Kiểm tra OVERFLOW trước khi ép kiểu context

Mẫu quan trọng trong event loop:

```java
if (event.kind() == OVERFLOW) {
    overflow = true;
    continue;
}
if (!(event.context() instanceof Path relative)) {
    overflow = true;
    continue;
}
```

`OVERFLOW` thường không có `Path context` thích hợp; cast ngầm/ép kiểu vội có thể gây `ClassCastException`. Event không nhận diện được cũng kích hoạt full rescan theo nguyên tắc thận trọng.

### Gom event, dùng trạng thái hiện tại làm nguồn sự thật

Một thao tác ghi của ứng dụng khác có thể tạo nhiều `ENTRY_MODIFY` hoặc `CREATE` rồi `MODIFY` liên tiếp. Chương trình **gom đường dẫn duy nhất** vào `SortedSet` trong một batch rồi `reconcileOne()` trên từng path, thay vì mặc định mỗi event là một transaction duy nhất.

Lợi ích: giảm xử lý lặp và không phải tin tuyệt đối thứ tự event. Đổi lại, chỉ những khác biệt ở **snapshot quan sát được** mới in thành `CREATE/MODIFY/DELETE`; thông báo event có thể tới sau khi file đã lại đổi hoặc biến mất.

### Reset WatchKey dù batch chứa overflow

Mỗi lần lấy key, phải gọi `key.reset()` sau khi xử lý batch. Nhánh `OVERFLOW` trong ví dụ **đánh dấu dirty**, không cố đọc context, rồi **reset key** và bắt đầu rescan. Nếu `reset()` trả `false`, code dừng vì đăng ký không còn hợp lệ.

**Không nhầm:** mất event nhưng key còn hiệu lực (`OVERFLOW`) khác hoàn toàn việc root bị xóa/key mất hiệu lực (`reset=false`). Trường hợp sau cần khôi phục khả năng đăng ký hoặc yêu cầu operator tạo lại root; quét lại thôi không đủ.

### Thất bại khi quét không làm mất snapshot tốt cuối cùng

`reconcile()` đặt thao tác `scan()` trong `try/catch`: nếu bị từ chối quyền hoặc có lỗi I/O, nó trả `false`, giữ `known` cũ và vòng lặp tiếp tục retry trong chu kỳ sau. `DirectoryIteratorException` do đọc danh sách thư mục bị lỗi cũng được chuyển về `IOException` để đi cùng nhánh retry.

Cách này giúp tránh ghi đè snapshot tốt cuối cùng bằng một danh sách chỉ đọc được một phần. Trong hệ thống cần độ tin cậy cao, nên phát cảnh báo/metric theo số lần retry, đặt backoff hợp lý và dừng nhận nhiệm vụ xử lý file khi chưa tái đồng bộ.

### Vì sao còn quét định kỳ 30 giây?

Đăng ký event rồi chụp snapshot giúp giảm khoảng trống giữa việc thiết lập watcher và lấy baseline. Tuy nhiên, **không có giao dịch atomic** nối API hệ thống file, snapshot và hàng đợi WatchService. Thư mục có thể thay đổi ngay trong khi quét; event có thể bị gộp hoặc bị mất vì filesystem/provider.

Chu kỳ `CHECK` mỗi khoảng 30 giây là lớp an toàn bổ sung, không phải bảo đảm không bao giờ mất cập nhật. Với thư mục lớn, rescan có chi phí **O(số entry)** về thời gian và dung lượng snapshot, nên chọn chu kỳ theo yêu cầu consistency, tải và khả năng filesystem.

## 6. Các giới hạn quan trọng trong production

### 6.1. WatchService không phải cơ sở dữ liệu lịch sử sự kiện

API không bảo đảm event sẽ tương ứng 1-1 với mỗi lần ghi. Hệ điều hành và provider quyết định thứ tự, số lượng và độ trễ; có thể thấy nhiều `MODIFY` cho một file hoặc mất event. Các thay đổi trên network filesystem cũng không bắt buộc được phát hiện. `OVERFLOW` chỉ báo **có thể đã mất sự kiện**, không cho biết danh sách file bị bỏ sót.

**Sau OVERFLOW bạn có thể khôi phục snapshot hiện tại, không thể tái tạo chắc chắn toàn bộ lịch sử.** Nếu cần audit mọi lần thay đổi, event stream đáng tin cậy từ nguồn dữ liệu, transaction log, outbox hoặc manifest có version mới là cơ sở phù hợp hơn.

### 6.2. Snapshot metadata không phải checksum nội dung

`Stamp` ở ví dụ chứa `directory`, `size`, `lastModifiedTime`, `fileKey`. Thuộc tính có thể có độ phân giải khác nhau giữa hệ thống file; `fileKey` có thể `null` và không phải id dùng để theo dõi rename xuyên thư mục. Thay đổi nội dung nhưng giữ cùng metadata có thể không được phát hiện.

Nếu cần kiểm chứng nội dung, kết hợp hash (như SHA-256) khi file đã **ổn định/đóng ghi**, đối chiếu với dữ liệu đã xử lý và bảo đảm phép xử lý **idempotent**. Việc hash tất cả file lớn ở mỗi lần quét có chi phí I/O cao và vẫn không phục hồi được các trạng thái đã xuất hiện rồi biến mất giữa hai lần quét.

### 6.3. Đọc ngay lúc ENTRY_MODIFY không có nghĩa file đã hoàn tất

Một chương trình ghi file có thể đang mở stream khi `ENTRY_CREATE` hoặc `ENTRY_MODIFY` tới. Không xử lý file như “đã hoàn chỉnh” chỉ vì thấy event; cần giao thức producer-consumer rõ ràng, ví dụ **ghi vào file tạm rồi đổi tên atomically nếu filesystem hỗ trợ**, hoặc kiểm tra ổn định kích thước/hash trước khi xử lý. Khi xử lý job, dùng retry và tính idempotent vì một file có thể được phát hiện nhiều lần.

### 6.4. Ví dụ chỉ theo dõi trực tiếp, không theo dõi đệ quy

`Path.register` đăng ký **một thư mục**, không tự đăng ký mọi thư mục con. Để theo dõi cây lớn, cần:
1. Dùng `Files.walkFileTree` để đăng ký mỗi thư mục đang tồn tại; giữ `Map<WatchKey,Path>`.
2. Khi có `ENTRY_CREATE` cho thư mục mới, đăng ký thư mục mới và các thư mục con đã tồn tại trong đó.
3. Sau bất kỳ `OVERFLOW` hoặc phát hiện mất đồng bộ, **quét và đối soát toàn bộ cây cần theo dõi**, đăng ký những thư mục mới xuất hiện và hủy những key không còn hợp lệ.
4. Không theo symlink bừa bãi vì có thể tạo vòng lặp hoặc quét ngoài phạm vi. Chú ý quyền, số lượng key và chi phí I/O khi số thư mục lớn.

Đây là **hướng mở rộng**, không phải tính năng của mã chạy đầy đủ ở trên. Nếu nghiệp vụ thật cần recursive watch, phải triển khai rõ ràng các bước trên trước khi sử dụng.

### 6.5. Khi root biến mất hoặc service bị đóng

`key.reset()==false` nghĩa là đăng ký không còn hợp lệ. Mã mẫu dừng và thông báo để tránh tiếp tục chạy im lặng với watcher hỏng. Một hệ thống phải tự phục hồi sau khi thư mục root bị xóa rồi tạo lại cần có **state machine tái đăng ký**, kiểm tra root tồn tại, tạo `WatchService`/key mới khi cần và chụp lại snapshot phù hợp trước khi nhận việc.

Nếu `WatchService.close()` được gọi lúc có thread đang `take()` hoặc `poll()`, thread có thể nhận `ClosedWatchServiceException`; ứng dụng đa luồng phải quản lý vòng đời và dừng watcher có chủ đích. Việc retry liên tục trên thư mục bị xóa hoặc không được cấp quyền mà không có cảnh báo là không an toàn trong vận hành.

## 7. Kế hoạch kiểm thử và checklist vận hành

| Tình huống kiểm thử | Kỳ vọng đúng |
| --- | --- |
| Tạo file mới khi watcher chạy | Sau event hoặc rescan, snapshot có entry; có thể in `LIVE CREATE` |
| Chỉnh sửa file đang tồn tại | Snapshot được cập nhật; có thể in `LIVE MODIFY` nếu metadata đổi |
| Xóa file | Snapshot không còn entry; có thể in `LIVE DELETE` |
| Mô phỏng mất event bằng `--demo` | Kết quả chính xác gồm một `CREATE`, một `MODIFY`, một `DELETE` |
| Event batch có `OVERFLOW` thật | Không cast context, đánh dấu dirty, reset key, quét lại toàn thư mục và đối soát |
| Quét lỗi tạm thời | Giữ snapshot cũ, retry và phát cảnh báo, không thông báo đồng bộ thành công |
| `reset()` trả `false` | Dừng và thông báo cần đăng ký lại |
| Tạo rồi xóa file trước lần quét kế tiếp | **Không hứa hẹn** phát hiện nếu không còn dấu vết ở snapshot |
| Thay đổi trong thư mục con | **Không được theo dõi** trong phiên bản một thư mục này |
| File ghi dang dở | Không xử lý nội dung cho đến khi đáp ứng điều kiện hoàn tất file của ứng dụng |

Khi đưa vào vận hành, nên có metric `overflow_count`, `reconcile_failures`, `last_successful_scan_time`, `snapshot_entry_count`, số lần key không hợp lệ và độ trễ xử lý. Nếu quét mất nhiều thời gian, cần kiểm soát backpressure và không thực hiện xử lý nghiệp vụ tốn thời gian ngay trên luồng nhận WatchKey.

## 8. Những lỗi hay gặp

- **Bỏ qua `OVERFLOW`**: trạng thái đã mất đồng bộ và có thể không tự sửa. **Giải pháp:** full rescan, diff với snapshot.
- **Cố đọc `(Path) event.context()` của `OVERFLOW`**: context có thể `null` hoặc kiểu khác. **Giải pháp:** kiểm tra `kind()` trước.
- **Không gọi `key.reset()`**: key có thể không được báo thêm event. **Giải pháp:** reset sau mỗi batch và kiểm tra boolean.
- **Nhầm `reset=false` với overflow**: key invalid không tự sống lại nhờ rescan. **Giải pháp:** dừng/re-register khi root hợp lệ.
- **Ghi đè snapshot cũ ngay sau khi quét được một phần**: có thể tạo sai `DELETE` hàng loạt. **Giải pháp:** chỉ commit sau scan thành công.
- **Tin rằng `ENTRY_MODIFY` = producer ghi xong**: có thể đọc dữ liệu dở dang. **Giải pháp:** phối hợp giao thức rename/commit/retry.
- **Cho rằng `register(root)` sẽ theo dõi toàn bộ thư mục con**: API mặc định không recursive. **Giải pháp:** đăng ký từng thư mục hoặc giới hạn scope rõ ràng.
- **Xem snapshot metadata là bằng chứng nội dung không thay đổi**: thay đổi same-size/same-mtime có thể bị bỏ qua. **Giải pháp:** dùng checksum/manifest khi cần.
- **Xử lý event bằng tác vụ nặng trong watcher loop**: consumer không kịp đọc queue, tăng rủi ro overflow. **Giải pháp:** tách event ingestion với worker/queue có giới hạn và cơ chế đối soát.

## 9. Ghi nhớ

Một `WatchService` đáng tin cậy cho tác vụ theo dõi thư mục **không dựa vào event stream như nguồn sự thật tuyệt đối**. Hãy đăng ký đúng loại event, kiểm tra `OVERFLOW` trước `context`, reset `WatchKey`, lưu snapshot đã xử lý và khi mất event thì **quét lại trạng thái thực rồi đối soát/commit nguyên khối**. Nếu quét thất bại, giữ snapshot cũ và retry; nếu key không còn hợp lệ, phải tái đăng ký thay vì giả vờ đang theo dõi. Đặt rõ giới hạn: snapshot cho biết **trạng thái quan sát được**, không phục hồi được mọi lần sửa/rename thoáng qua.

### Tài liệu chính thức vẫn còn áp dụng

- [Java SE 25 — `WatchService`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/WatchService.html)
- [Java SE 25 — `WatchKey`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/WatchKey.html)
- [Java SE 25 — `StandardWatchEventKinds`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html)
- [Dev.java — Watching a Directory for Changes](https://dev.java/learn/api/io/java-io/file-system/watching-dir-changes/)
