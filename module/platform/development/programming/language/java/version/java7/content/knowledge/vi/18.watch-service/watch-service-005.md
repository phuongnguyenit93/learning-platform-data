# Chuyển context sự kiện thành đường dẫn cần xử lý trong WatchService (Java)

## 1. Vấn đề cần giải quyết

Khi đăng ký theo dõi thư mục `inbox/` bằng Java NIO.2 `WatchService`, ứng dụng có thể nhận `ENTRY_CREATE` cho entry tên `report.csv`. Nhưng `WatchEvent.context()` **không phải đường dẫn tuyệt đối tới file**, mà với các kind chuẩn `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY` là **một `Path` tương đối với thư mục đã đăng ký**.

Cách xử lý đúng:

~~~java
Path watchedDirectory = (Path) key.watchable();
Path relativeName = (Path) event.context();
Path changedEntry = watchedDirectory.resolve(relativeName);
~~~

Đây là **đoạn trong vòng lặp xử lý event**, chưa phải class độc lập. Việc ép kiểu phù hợp khi ứng dụng biết `key` đến từ đăng ký directory `Path` và `event` thuộc một trong ba kind chuẩn với context kiểu `Path`. **Không áp dụng mù quáng cho `OVERFLOW`.**

Mô hình:

~~~text
Đã đăng ký: /project/inbox/
                   |
WatchKey.watchable() = /project/inbox/
                   |
WatchEvent.kind()   = ENTRY_CREATE
WatchEvent.context()= report.csv
                   |
                   v
(Path)key.watchable().resolve((Path)event.context())
                   |
                   v
           /project/inbox/report.csv
                   |
                   v
        Kiểm tra, đọc hoặc cập nhật index
~~~

Công thức này là trọng tâm của bài. Nếu chỉ gọi `Path.of(event.context().toString()).toAbsolutePath()`, path có thể bị giải quyết từ **working directory của Java process**, không phải directory đang được theo dõi. Nếu đăng ký nhiều directory, hai event có context cùng tên vẫn có thể đại diện cho **hai file khác nhau**.

### Học xong, bạn cần làm được

1. Hiểu `WatchService`, `WatchKey` và `WatchEvent<?>`.
2. Lấy directory gốc từ `key.watchable()`, lấy context `Path` từ event rồi `resolve`.
3. Xử lý đúng ba kind `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY`.
4. Không ép kiểu context của `OVERFLOW` thành `Path`; biết đối soát directory khi có thể mất event.
5. Phân biệt `event.count()` với số file khác nhau.
6. Dùng `pollEvents()` và `reset()` theo vòng đời WatchKey.
7. Xử lý đúng event của nhiều directory và file trùng tên.
8. Hiểu vì sao DELETE có thể chỉ còn **tên cũ**, CREATE/MODIFY có thể đến trước khi ghi xong.
9. Biết rằng WatchService **không tự theo dõi thư mục con**.
10. Có chính sách hợp lý cho path bất thường, symlink, quyền truy cập, mất sự kiện và filesystem thay đổi đồng thời.
11. Phân biệt integration test dùng event thật với unit test tạo event mô phỏng.
12. Chạy các ví dụ Java 17+ độc lập và kiểm tra stdout.

**Phiên bản:** `WatchService`, `WatchKey`, `WatchEvent`, `Path.register` và `StandardWatchEventKinds` ra đời từ **Java 7**, vẫn được hỗ trợ hiện nay. Các chương trình minh họa dùng Java 17+ để có `instanceof Path name` và `Files.writeString` (Java 11+). Cơ chế giải quyết context không đổi.

## 2. WatchService trả event theo registration, không trả file hoàn chỉnh

Một WatchService có thể chứa nhiều đăng ký:

~~~java
try (WatchService watcher =
             FileSystems.getDefault().newWatchService()) {
    WatchKey inboxKey = inbox.register(
            watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_DELETE,
            StandardWatchEventKinds.ENTRY_MODIFY);

    WatchKey key = watcher.take();
    for (WatchEvent<?> event : key.pollEvents()) {
        // Xử lý event của directory thuộc key.
    }
    key.reset();
}
~~~

Đây là **đoạn minh họa trong phương thức**, có `inbox` là `Path` đã khai báo, import `java.nio.file.*` và phương thức có xử lý/khai báo ngoại lệ. Với chương trình chạy lâu dài, không chỉ lấy một WatchKey rồi thoát, mà dùng vòng lặp và chính sách shutdown phù hợp.

| Đối tượng | Ý nghĩa | Phương thức |
| --- | --- | --- |
| `WatchService` | Nơi các registration được theo dõi và signal | `take()`, `poll()`, `poll(timeout,TimeUnit)`, `close()` |
| `WatchKey` | Token cho **một registration**, giúp biết directory nào có event | `watchable()`, `pollEvents()`, `reset()`, `isValid()`, `cancel()` |
| `WatchEvent<?>` | Một loại sự kiện có context và số lần ghi nhận | `kind()`, `context()`, `count()` |
| `Path` | Đối tượng biểu diễn đường dẫn tệp/thư mục | `resolve()`, `normalize()`, `getFileName()` |

Diễn tiến:

~~~text
1. FileSystem.newWatchService()
2. watchedDir.register(watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY)
3. OS/provider phát hiện thay đổi entry trực tiếp
4. watcher.take() hoặc poll(...) lấy WatchKey đã signal
5. key.pollEvents() trả nhiều WatchEvent<?> có thể có
6. Đọc kind; nếu OVERFLOW => đánh dấu rescan
7. Với kind chuẩn => lấy Path context
8. (Path)key.watchable() + context => Path đầy đủ
9. Xử lý nghiệp vụ tùy CREATE / MODIFY / DELETE
10. key.reset() => chuẩn bị nhận signal tiếp
11. Đóng WatchService khi dừng
~~~

### Watchable là gì?

`WatchKey.watchable()` trả một `Watchable`, tức đối tượng đã đăng ký. Với API `Path.register` giám sát directory thông thường, đối tượng ấy là `Path`. Vì vậy có thể cast:

~~~java
Path watchedDir = (Path) key.watchable();
~~~

Nếu viết framework làm việc với các `Watchable` không chắc chắn là `Path`, kiểm tra:

~~~java
if (!(key.watchable() instanceof Path watchedDir)) {
    // Không xử lý như directory Path.
}
~~~

Khi một directory bị move/rename, Javadoc không bảo đảm path trả về từ `watchable()` luôn còn định vị directory như trước; phải có chính sách theo dõi lại và xử lý key invalid.

## 3. Hợp đồng về context và event kind

Với các sự kiện chuẩn:

| Kind | Context | Hướng xử lý thường gặp |
| --- | --- | --- |
| `ENTRY_CREATE` | `Path` **tương đối** của entry mới tạo/move vào | Ghép path, xác minh loại file, có thể đọc sau khi file hoàn chỉnh |
| `ENTRY_DELETE` | `Path` **tương đối** của entry bị xóa/move ra | Ghép path để biết tên cũ, cập nhật cache/index |
| `ENTRY_MODIFY` | `Path` **tương đối** của entry bị thay đổi | Ghép path, kiểm tra trạng thái mới, debounce/retry |
| `OVERFLOW` | `Object` do provider định nghĩa, **có thể null** | Không resolve file cụ thể; **rescan/reconcile directory** |
| Kind riêng của provider | Phụ thuộc provider | Không tự áp ngữ nghĩa Path của ba kind chuẩn |

Chú ý generic:

~~~java
WatchEvent.Kind<Path> createKind =
        StandardWatchEventKinds.ENTRY_CREATE;
WatchEvent.Kind<Object> overflowKind =
        StandardWatchEventKinds.OVERFLOW;
~~~

Đây là đoạn minh họa, không phải file độc lập. Ba kind entry chuẩn dùng `Path`. `OVERFLOW` dùng `Object`, nên `event.context()` có thể null hoặc loại khác và **không được ép kiểu Path chỉ vì mọi event nằm trong cùng `pollEvents()`**.

### `event.count()` không phải số file

Một `WatchEvent` có thể đại diện cho nhiều lần event cùng kind/context, chẳng hạn `ENTRY_MODIFY` lặp lại. Nếu `count()==3`, không có nghĩa ba path khác nhau. Một file có thể tạo nhiều MODIFY event; một hoặc nhiều event cũng có thể được gộp. WatchService không phải log đầy đủ của mọi thao tác filesystem.

### `Path.resolve` không cần nối chuỗi

Đúng:

~~~java
Path full = watchedDir.resolve(relativeName).normalize();
~~~

Không ưu tiên:

~~~java
Path full = Path.of(watchedDir.toString()
        + "/" + relativeName.toString());
~~~

Đoạn thứ hai tự nối separator theo chuỗi và dễ phát sinh lỗi khi chuyển môi trường/provider. `Path.resolve(Path)` hỗ trợ semantic path của provider. `normalize()` giúp bỏ thành phần `.`/`..` trên bình diện từ vựng, nhưng **không** giải quyết symbolic links hoặc cung cấp sandbox bảo mật.

Nguồn: [WatchEvent Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/WatchEvent.html), [Path.register Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html), [StandardWatchEventKinds Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html).

## 4. Ví dụ 1 — Nhận event tạo file thật và resolve context

Tạo file `ContextPathDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;
import static java.nio.file.StandardWatchEventKinds.*;

public class ContextPathDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("watch-path-");
        Path file = root.resolve("hello.txt");

        try (WatchService watcher =
                     FileSystems.getDefault().newWatchService()) {
            root.register(watcher, ENTRY_CREATE);
            Files.writeString(
                    file, "data", StandardCharsets.UTF_8);

            WatchKey key = watcher.poll(5, TimeUnit.SECONDS);
            if (key == null) {
                throw new AssertionError(
                        "No event: environment does not support test");
            }

            boolean relative = false;
            boolean resolved = false;
            boolean knownDir = false;

            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == ENTRY_CREATE
                        && event.context() instanceof Path name) {
                    Path directory = (Path) key.watchable();
                    relative |= !name.isAbsolute();
                    resolved |= directory.resolve(name).equals(file);
                    knownDir |= directory.equals(root);
                }
            }

            System.out.println("relativeContext=" + relative);
            System.out.println("rightDirectory=" + knownDir);
            System.out.println("resolvedMatches=" + resolved);
            System.out.println("resetValid=" + key.reset());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Lưu source UTF-8 và chạy:

~~~bash
javac -encoding UTF-8 --release 17 ContextPathDemo.java
java ContextPathDemo
~~~

Stdout đã kiểm chứng trên filesystem kiểm thử:

~~~text
relativeContext=true
rightDirectory=true
resolvedMatches=true
resetValid=true
~~~

Diễn giải:

1. Tạo directory tạm, tạo Path dự kiến cho file nhưng **chưa tạo file**.
2. Tạo WatchService, đăng ký `root` với `ENTRY_CREATE`.
3. **Sau khi đăng ký** mới gọi `Files.writeString` để phát sinh sự kiện.
4. `poll(5, TimeUnit.SECONDS)` có thời hạn; nếu OS không phát sự kiện, test thất bại có thông báo, không treo vô hạn.
5. `kind()==ENTRY_CREATE` được kiểm tra trước khi lấy context `Path`.
6. `key.watchable()` trả `root` đã đăng ký; `directory.resolve(name)` cho Path của file được tạo.
7. Kiểm tra boolean thay vì in đường dẫn tạm ngẫu nhiên, nên stdout dễ đối chiếu.
8. `key.reset()` cho phép key nhận signal mới nếu registration còn hợp lệ.
9. `try-with-resources` đóng WatchService; `finally` dọn file/thư mục.

**Chỉ khẳng định PASS trên môi trường đã chạy.** WatchService có khác biệt phát hiện sự kiện/độ trễ giữa providers. Timeout năm giây là giới hạn cho test, không phải cam kết Java rằng event luôn đến trong năm giây.

## 5. Ví dụ 2 — Hai directory có cùng filename: phải dùng đúng WatchKey

Cấu trúc:

~~~text
temp/
├── a/
│   └── same.txt
└── b/
    └── same.txt
~~~

Cả hai event `ENTRY_CREATE` có thể chứa context `same.txt`. Chỉ dựa trên context, ứng dụng không biết file thuộc `a` hay `b`. WatchKey giải quyết vấn đề đó.

Tạo `MultiDirectoryDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import static java.nio.file.StandardWatchEventKinds.*;

public class MultiDirectoryDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("watch-multi-");
        Path a = Files.createDirectory(root.resolve("a"));
        Path b = Files.createDirectory(root.resolve("b"));
        Path first = a.resolve("same.txt");
        Path second = b.resolve("same.txt");

        try (WatchService watcher =
                     FileSystems.getDefault().newWatchService()) {
            a.register(watcher, ENTRY_CREATE);
            b.register(watcher, ENTRY_CREATE);
            Files.createFile(first);
            Files.createFile(second);

            Set<Path> found = new HashSet<>();
            for (int i = 0; i < 2; i++) {
                WatchKey key = watcher.poll(5, TimeUnit.SECONDS);
                if (key == null) {
                    throw new AssertionError("Missing watch key");
                }

                Path dir = (Path) key.watchable();
                for (WatchEvent<?> event : key.pollEvents()) {
                    if (event.kind() == ENTRY_CREATE
                            && event.context() instanceof Path rel) {
                        found.add(dir.resolve(rel));
                    }
                }

                if (!key.reset()) {
                    throw new AssertionError("Invalid key");
                }
            }

            System.out.println("firstResolved=" +
                    found.contains(first));
            System.out.println("secondResolved=" +
                    found.contains(second));
            System.out.println("separateTargets=" +
                    !first.equals(second));
        } finally {
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MultiDirectoryDemo.java
java MultiDirectoryDemo
~~~

Stdout trên môi trường thử:

~~~text
firstResolved=true
secondResolved=true
separateTargets=true
~~~

Giải thích: Dù tên context giống nhau, `key.watchable()` cho ra `a` hoặc `b`, và `resolve` tạo hai `Path` khác nhau. Dùng `HashSet<Path>` để không phụ thuộc thứ tự WatchKeys mà OS trả. Trên ứng dụng thực, có thể dùng `Map<WatchKey, Path>` để giữ thêm thông tin đăng ký; map này phải được cập nhật khi `key.reset()` trả false hoặc directory bị thay.

**Sai lầm:** Luôn dùng `root.resolve(event.context())` trong ví dụ này sẽ cho `root/same.txt`, không phải `root/a/same.txt` hoặc `root/b/same.txt`. `root` chỉ là thư mục cha chung, **không** phải directory của registration vừa signal.

## 6. Ví dụ 3 — ENTRY_DELETE vẫn resolve được Path khi file đã mất

Khi file bị xóa, context vẫn cung cấp **tên/vị trí cũ**. `Path` không phải handle giữ nội dung file tồn tại, vì thế:

~~~java
Path removedPath = ((Path) key.watchable())
        .resolve((Path) event.context());
~~~

Đây là đoạn trong handler của `ENTRY_DELETE`, không thể tự chạy độc lập. Có thể lưu tên vừa bị xóa để cập nhật index/cache, nhưng **không** gọi `Files.readString(removedPath)` theo mặc định vì file có thể đã biến mất. Nếu một tiến trình khác tạo lại cùng tên ngay sau đó, `Files.exists(removedPath)` có thể true nhưng trỏ tới entry mới.

Tạo file `DeleteContextDemo.java`:

~~~java
import java.nio.file.*;
import java.util.concurrent.TimeUnit;
import static java.nio.file.StandardWatchEventKinds.*;

public class DeleteContextDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("watch-delete-");
        Path file = Files.createFile(root.resolve("gone.txt"));

        try (WatchService watcher =
                     FileSystems.getDefault().newWatchService()) {
            root.register(watcher, ENTRY_DELETE);
            Files.delete(file);

            WatchKey key = watcher.poll(5, TimeUnit.SECONDS);
            if (key == null) {
                throw new AssertionError("Missing delete event");
            }

            boolean matches = false;
            boolean pathStillExists = true;

            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == ENTRY_DELETE
                        && event.context() instanceof Path rel) {
                    Path changed =
                            ((Path) key.watchable()).resolve(rel);
                    if (changed.equals(file)) {
                        matches = true;
                        pathStillExists = Files.exists(changed);
                    }
                }
            }

            System.out.println("deletePathMatches=" + matches);
            System.out.println("pathExistsAfterDelete=" +
                    pathStillExists);
            System.out.println("resetValid=" + key.reset());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 DeleteContextDemo.java
java DeleteContextDemo
~~~

Stdout trong fixture không có tiến trình khác sửa directory:

~~~text
deletePathMatches=true
pathExistsAfterDelete=false
resetValid=true
~~~

**Không suy ra quy tắc rằng mọi ENTRY_DELETE phải có `Files.exists(path)==false` tại thời điểm consumer chạy.** WatchService quan sát thay đổi, còn hệ thống tệp có thể tiếp tục được sửa, và `Files.exists` cũng có thể false khi không kiểm tra được vì I/O hoặc quyền. Tùy mục tiêu, cập nhật index theo dữ liệu đã quản lý thay vì đọc file từ path đã bị xóa.

## 7. Xử lý `OVERFLOW` trước khi ép kiểu context

`StandardWatchEventKinds.OVERFLOW` mang kiểu `WatchEvent.Kind<Object>`, không phải `Kind<Path>`. Context có thể null hoặc do implementation định nghĩa. OVERFLOW thông báo rằng event có thể đã bị mất/loại bỏ và ứng dụng cần **đối soát trạng thái thư mục**, không xử lý một filename cụ thể.

Mẫu kiểm tra:

~~~java
for (WatchEvent<?> event : key.pollEvents()) {
    WatchEvent.Kind<?> kind = event.kind();

    if (kind == StandardWatchEventKinds.OVERFLOW) {
        // Đánh dấu directory cần quét lại.
        continue;
    }

    if (kind != StandardWatchEventKinds.ENTRY_CREATE
            && kind != StandardWatchEventKinds.ENTRY_DELETE
            && kind != StandardWatchEventKinds.ENTRY_MODIFY) {
        // Kind tùy provider: cần xử lý riêng nếu đã hiểu nó.
        continue;
    }

    if (!(event.context() instanceof Path relative)) {
        // Null / không phải Path => không xử lý như filename.
        continue;
    }

    Path directory = (Path) key.watchable();
    Path full = directory.resolve(relative).normalize();
    // Kiểm tra policy rồi xử lý full theo kind.
}
~~~

Đây là **đoạn minh họa trong event loop**, không phải class hoàn chỉnh. Production không được chỉ `continue` trên OVERFLOW rồi quên quét lại: cần đưa directory vào cơ chế rescan, so sánh danh sách file hiện có với state/index đã lưu.

### 7.1. Những việc OVERFLOW không cho bạn biết

- Không có danh sách chính xác tất cả tên file đã bị mất event.
- `event.count()` có thể lớn hơn 1 nhưng **không** phải cách dựng lại các path bị bỏ sót.
- Không thể đảm bảo feed event tạo thành lịch sử hoàn chỉnh như một database transaction log.
- Nếu có backlog quá lớn, cần giảm thời gian xử lý trong event loop, giao các công việc nặng ra queue và đối soát định kỳ theo nhu cầu.

Nguồn: [WatchService Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/WatchService.html), [StandardWatchEventKinds Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html).

## 8. Ví dụ 4 — Unit test resolver an toàn và OVERFLOW

Không nên cố tạo hàng nghìn file để “chắc chắn” gây overflow thật, vì ngưỡng và tốc độ sự kiện phụ thuộc provider. Ta có thể kiểm tra **logic** bằng WatchEvent mô phỏng; phải ghi rõ đây là **unit test**, không phải sự kiện filesystem thật.

Tạo `OverflowAndGuardDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;
import static java.nio.file.StandardWatchEventKinds.*;

public class OverflowAndGuardDemo {
    static final class FakeEvent<T> implements WatchEvent<T> {
        private final Kind<T> kind;
        private final T context;
        private final int count;

        FakeEvent(Kind<T> kind, T context, int count) {
            this.kind = kind;
            this.context = context;
            this.count = count;
        }

        public Kind<T> kind() { return kind; }
        public T context() { return context; }
        public int count() { return count; }
    }

    static Optional<Path> resolveKnownEntry(
            Path watchedDir, WatchEvent<?> event) {
        if (event.kind() == OVERFLOW) {
            return Optional.empty();
        }
        if (event.kind() != ENTRY_CREATE
                && event.kind() != ENTRY_DELETE
                && event.kind() != ENTRY_MODIFY) {
            return Optional.empty();
        }

        if (!(event.context() instanceof Path relative)
                || relative.isAbsolute()) {
            return Optional.empty();
        }

        Path base = watchedDir.toAbsolutePath().normalize();
        Path full = base.resolve(relative).normalize();
        if (!full.startsWith(base)) {
            return Optional.empty();
        }
        return Optional.of(full);
    }

    public static void main(String[] args) {
        Path directory =
                Path.of("inbox").toAbsolutePath().normalize();

        WatchEvent<Path> changed =
                new FakeEvent<>(
                        ENTRY_MODIFY, Path.of("report.txt"), 3);
        WatchEvent<Object> overflow =
                new FakeEvent<>(OVERFLOW, null, 2);
        WatchEvent<Path> escape =
                new FakeEvent<>(
                        ENTRY_CREATE, Path.of("..", "unsafe.txt"), 1);
        WatchEvent<Path> absolute =
                new FakeEvent<>(
                        ENTRY_CREATE, directory.resolve("oops"), 1);

        System.out.println("fileMatches=" +
                resolveKnownEntry(directory, changed)
                        .orElseThrow()
                        .equals(directory.resolve("report.txt")));
        System.out.println("repeatedCount=" + changed.count());
        System.out.println("overflowSkipped=" +
                resolveKnownEntry(directory, overflow).isEmpty());
        System.out.println("escapeSkipped=" +
                resolveKnownEntry(directory, escape).isEmpty());
        System.out.println("absoluteSkipped=" +
                resolveKnownEntry(directory, absolute).isEmpty());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 OverflowAndGuardDemo.java
java OverflowAndGuardDemo
~~~

Stdout:

~~~text
fileMatches=true
repeatedCount=3
overflowSkipped=true
escapeSkipped=true
absoluteSkipped=true
~~~

Giải thích:

1. `ENTRY_MODIFY` với context `report.txt` được ghép với watched directory.
2. `count=3` đại diện số lần sự kiện được ghi nhận/gộp, **không** phải ba file.
3. `OVERFLOW` được phát hiện qua kind trước khi dùng context; kết quả empty.
4. Context `../unsafe.txt` bị từ chối sau khi chuẩn hóa vì Path rời ra ngoài base **về mặt lexical**.
5. Context tuyệt đối cũng bị từ chối vì ba kind entry chuẩn có context tương đối.
6. `Optional.empty()` chỉ là kết quả từ hàm thử nghiệm. Trong production phải phân biệt nguyên nhân: **OVERFLOW cần rescan**, kind lạ cần xử lý tùy provider, context bất thường cần báo trạng thái.

**Cực kỳ quan trọng:** Kiểm tra `full.startsWith(base)` chỉ là **kiểm tra đường dẫn ở mức biểu diễn**, không bảo vệ đầy đủ trước symbolic links/TOCTOU. Một Path `base/link/secret.txt` có thể trỏ ngoài base qua symlink. Nếu cần bảo vệ dữ liệu nhạy cảm, cần chính sách quyền, kiểm tra target theo filesystem, API no-follow phù hợp và biện pháp mở file an toàn trong môi trường có attacker.

## 9. Ví dụ 5 — Kiểm thử quyết định rescan khi OVERFLOW

Tạo `OverflowReconcileDemo.java`:

~~~java
import java.nio.file.*;
import java.util.*;
import static java.nio.file.StandardWatchEventKinds.*;

public class OverflowReconcileDemo {
    static final class OverflowEvent
            implements WatchEvent<Object> {
        public Kind<Object> kind() { return OVERFLOW; }
        public int count() { return 4; }
        public Object context() { return null; }
    }

    static String action(WatchEvent<?> e) {
        if (e.kind() == OVERFLOW) {
            return "RESCAN";
        }
        if (e.context() instanceof Path) {
            return "RESOLVE";
        }
        return "IGNORE";
    }

    public static void main(String[] args) {
        WatchEvent<?> e = new OverflowEvent();
        System.out.println("kind=" + e.kind().name());
        System.out.println("contextNull=" +
                (e.context() == null));
        System.out.println("action=" + action(e));
        System.out.println("lostEventsMayExist=" +
                (e.count() > 0));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 OverflowReconcileDemo.java
java OverflowReconcileDemo
~~~

Stdout:

~~~text
kind=OVERFLOW
contextNull=true
action=RESCAN
lostEventsMayExist=true
~~~

Đây là **unit test với FakeEvent**, không phải integration test gây mất event. Ý nghĩa của `RESCAN` là quét lại directory bằng một API như `Files.newDirectoryStream` hoặc `Files.list`, đóng tài nguyên, rồi đối chiếu trạng thái với index/cache. Không chỉ log và tiếp tục như mọi thay đổi đã được nhận đầy đủ.

## 10. WatchKey.pollEvents() và reset() là một vòng đời

Javadoc mô tả key được signal/queue khi có thay đổi; `pollEvents()` lấy và loại các event đang chờ; `reset()` chuyển key trở lại trạng thái sẵn sàng cho lần signal tiếp theo. Nếu key đang signal, những event khác có thể tích lũy nhưng key không nhất thiết được queue thêm lần nữa.

~~~java
while (running) {
    WatchKey key = watcher.take();

    for (WatchEvent<?> event : key.pollEvents()) {
        // Xử lý event hoặc đưa sang queue nghiệp vụ.
    }

    boolean valid = key.reset();
    if (!valid) {
        // Directory/registration không còn hợp lệ.
    }
}
~~~

Đây là **đoạn trong method**, `running`/`watcher` đã khai báo. Production cần xử lý `InterruptedException`, `ClosedWatchServiceException`, errors từ handler và shutdown.

- **Đừng quên reset.** Nếu không, key có thể không được signal/requeue cho những thay đổi tiếp theo như kỳ vọng.
- **Đừng reset quá sớm** trong hệ thống nhiều consumers nếu muốn đảm bảo chỉ một consumer xử lý cùng registration tại một thời điểm.
- Nếu `reset()==false`, registration không còn valid; cần loại khỏi map hoặc quyết định đăng ký lại.
- `WatchKey.watchable()` vẫn có thể trả đối tượng cũ sau khi registration invalid, nên không đồng nghĩa directory hiện vẫn truy cập được.
- `WatchService.close()` giải phóng tài nguyên; thread đang chờ có thể nhận `ClosedWatchServiceException` khi service bị đóng.

### 10.1. Ví dụ 6 — Reset cho hai lượt tạo file

Tạo `ResetWatchKeyDemo.java`:

~~~java
import java.nio.file.*;
import java.util.concurrent.TimeUnit;
import static java.nio.file.StandardWatchEventKinds.*;

public class ResetWatchKeyDemo {
    static boolean contains(WatchKey key, Path filename) {
        for (WatchEvent<?> e : key.pollEvents()) {
            if (e.kind() == ENTRY_CREATE
                    && filename.equals(e.context())) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("watch-reset-");
        Path a = root.resolve("a.txt");
        Path b = root.resolve("b.txt");

        try (WatchService watcher =
                     FileSystems.getDefault().newWatchService()) {
            WatchKey registered =
                    root.register(watcher, ENTRY_CREATE);

            Files.createFile(a);
            WatchKey first =
                    watcher.poll(5, TimeUnit.SECONDS);
            if (first == null) {
                throw new AssertionError("first key absent");
            }

            boolean sawA = contains(first, Path.of("a.txt"));
            boolean valid = first.reset();

            Files.createFile(b);
            WatchKey second =
                    watcher.poll(5, TimeUnit.SECONDS);
            if (second == null) {
                throw new AssertionError("second key absent");
            }

            boolean sawB = contains(second, Path.of("b.txt"));
            boolean sameKey = second == registered;
            boolean validAgain = second.reset();

            System.out.println("firstEvent=" + sawA);
            System.out.println("firstReset=" + valid);
            System.out.println("secondEvent=" + sawB);
            System.out.println("sameKey=" + sameKey);
            System.out.println("secondReset=" + validAgain);
        } finally {
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ResetWatchKeyDemo.java
java ResetWatchKeyDemo
~~~

Stdout đã kiểm chứng:

~~~text
firstEvent=true
firstReset=true
secondEvent=true
sameKey=true
secondReset=true
~~~

Điểm rút ra: Reset **không tạo key mới**, mà phục hồi khả năng nhận signal của registration còn hợp lệ. Khi xử lý nhiều directory, nên giữ map WatchKey→Path/metadata hoặc dùng chính `watchable` để xác định thư mục nguồn.

## 11. WatchService không tự theo dõi toàn bộ thư mục con

Nếu chỉ đăng ký `root`, WatchService báo thay đổi entry **trực tiếp dưới root** theo contract. Nó không tự động báo mọi file trong `root/sub/`. Việc `sub` xuất hiện có thể là `ENTRY_CREATE` ở root, nhưng các file `sub/nested.txt` cần registration riêng cho `sub` nếu muốn theo dõi tiếp.

Muốn theo dõi đệ quy, ứng dụng thường phải:

1. Duyệt tree ban đầu và đăng ký mỗi directory đang tồn tại.
2. Khi có event tạo directory mới, kiểm tra nó thực sự là directory rồi đăng ký.
3. Scan directory mới sau đăng ký để giảm race khi file được tạo trước khi watcher kịp đăng ký.
4. Hủy đăng ký/loại map khi directory biến mất hoặc key invalid.
5. Xử lý symbolic links theo chính sách rõ ràng, tránh vòng lặp hoặc vượt root.
6. Có rescan khi OVERFLOW/mất event.

### 11.1. Ví dụ 7 — Đăng ký root và sub khác nhau

Tạo `NestedWatchDemo.java`:

~~~java
import java.nio.file.*;
import java.util.concurrent.TimeUnit;
import static java.nio.file.StandardWatchEventKinds.*;

public class NestedWatchDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("watch-nested-");
        Path sub = root.resolve("sub");
        Path file = sub.resolve("nested.txt");

        try (WatchService watcher =
                     FileSystems.getDefault().newWatchService()) {
            root.register(watcher, ENTRY_CREATE);
            Files.createDirectory(sub);

            WatchKey key = watcher.poll(5, TimeUnit.SECONDS);
            if (key == null) {
                throw new AssertionError("missing root key");
            }

            boolean sawSubdir = false;
            boolean sawNestedFile = false;
            for (WatchEvent<?> e : key.pollEvents()) {
                sawSubdir |= e.kind() == ENTRY_CREATE
                        && Path.of("sub").equals(e.context());
                sawNestedFile |= e.kind() == ENTRY_CREATE
                        && Path.of("nested.txt").equals(e.context());
            }
            key.reset();

            Files.createFile(file);
            WatchKey extra =
                    watcher.poll(300, TimeUnit.MILLISECONDS);
            if (extra != null) {
                for (WatchEvent<?> e : extra.pollEvents()) {
                    sawNestedFile |=
                            Path.of("nested.txt").equals(e.context());
                }
                extra.reset();
            }

            System.out.println("sawSubdirectory=" + sawSubdir);
            System.out.println("sawNestedFile=" + sawNestedFile);

            WatchKey nested =
                    sub.register(watcher, ENTRY_CREATE);
            Path second = sub.resolve("direct.txt");
            Files.createFile(second);

            WatchKey nestedKey =
                    watcher.poll(5, TimeUnit.SECONDS);
            if (nestedKey == null) {
                throw new AssertionError("missing nested key");
            }

            boolean nestedRecognized = false;
            for (WatchEvent<?> e : nestedKey.pollEvents()) {
                nestedRecognized |= e.kind() == ENTRY_CREATE
                        && Path.of("direct.txt").equals(e.context())
                        && sub.equals(nestedKey.watchable());
            }
            nestedKey.reset();

            System.out.println("nestedRegisteredWorks=" +
                    nestedRecognized);
            Files.delete(second);
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 NestedWatchDemo.java
java NestedWatchDemo
~~~

Stdout:

~~~text
sawSubdirectory=true
sawNestedFile=false
nestedRegisteredWorks=true
~~~

Chương trình xác nhận root watcher nhận create của `sub`; nó **không tự bắt** create của `sub/nested.txt`. Khi `sub` được đăng ký riêng, create `sub/direct.txt` được phát hiện với `key.watchable()==sub`.

**Giới hạn thực tế:** Event timing phụ thuộc OS; trong ứng dụng thật, giữa lúc phát hiện directory mới và đăng ký subdir, file có thể đã xuất hiện. Scan subdir sau đăng ký và xây cơ chế reconciliation nếu cần độ tin cậy cao.

## 12. Ví dụ 8 — Vì sao context.toAbsolutePath() sai mốc?

Giả sử:

~~~text
watchedDir = /workspace/logs
context    = app.log
~~~

Cần:

~~~java
Path full = watchedDir.resolve(context).normalize();
~~~

Nếu gọi `context.toAbsolutePath()` riêng, kết quả có thể dựa trên thư mục hiện tại của chương trình, chẳng hạn `/workspace/app.log`, không phải `/workspace/logs/app.log`.

Tạo `PathReconstructionDemo.java`:

~~~java
import java.nio.file.*;

public class PathReconstructionDemo {
    public static void main(String[] args) {
        Path dir = Path.of("workspace", "logs")
                .toAbsolutePath().normalize();
        Path context = Path.of("app.log");

        Path correct = dir.resolve(context).normalize();
        Path wrong = context.toAbsolutePath();

        System.out.println("contextRelative=" +
                !context.isAbsolute());
        System.out.println("baseIsDirectory=" +
                correct.getParent().equals(dir));
        System.out.println("fileName=" + correct.getFileName());
        System.out.println("relativeToDir=" +
                dir.relativize(correct));
        System.out.println("workingDirIsWrongBase=" +
                !wrong.equals(correct));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 PathReconstructionDemo.java
java PathReconstructionDemo
~~~

Stdout:

~~~text
contextRelative=true
baseIsDirectory=true
fileName=app.log
relativeToDir=app.log
workingDirIsWrongBase=true
~~~

Đây là ví dụ **thuần Path**, không dùng WatchService thật. Nó chứng minh rõ hai phép toán `resolve` và `toAbsolutePath` khác nhau về **mốc**. Kết luận áp dụng trực tiếp khi chuyển event context thành Path đích.

## 13. Event handler mẫu cho một ứng dụng thực

Vòng lặp dưới đây nhấn mạnh **thứ tự xử lý đúng**: nhận key, nhận directory, phân loại kind, kiểm tra context, ghép path, sau đó reset. Các hàm `handleCreate`, `handleModify`, `handleDelete` và `reconcile` là **hàm nghiệp vụ do ứng dụng định nghĩa**, nên đây **không phải chương trình độc lập**.

~~~java
for (;;) {
    WatchKey key;
    try {
        key = watcher.take();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        break;
    } catch (ClosedWatchServiceException e) {
        break;
    }

    if (!(key.watchable() instanceof Path watchedDir)) {
        key.cancel();
        continue;
    }

    boolean rescan = false;

    for (WatchEvent<?> event : key.pollEvents()) {
        WatchEvent.Kind<?> kind = event.kind();

        if (kind == StandardWatchEventKinds.OVERFLOW) {
            rescan = true;
            continue;
        }

        if (kind != StandardWatchEventKinds.ENTRY_CREATE
                && kind != StandardWatchEventKinds.ENTRY_MODIFY
                && kind != StandardWatchEventKinds.ENTRY_DELETE) {
            continue;
        }

        if (!(event.context() instanceof Path relative)
                || relative.isAbsolute()) {
            rescan = true;
            continue;
        }

        Path full = watchedDir.resolve(relative).normalize();

        // Trước khi truy cập full, áp dụng root/permission/symlink
        // policy của ứng dụng. normalize() không là sandbox.
        if (kind == StandardWatchEventKinds.ENTRY_CREATE) {
            handleCreate(full);
        } else if (kind == StandardWatchEventKinds.ENTRY_MODIFY) {
            handleModify(full);
        } else {
            handleDelete(full);
        }
    }

    if (rescan) {
        reconcile(watchedDir);
    }

    if (!key.reset()) {
        // Registration bị hủy, loại khỏi map/đăng ký lại.
        break;
    }
}
~~~

### 13.1. Những gì handler production còn phải bổ sung

- **Xử lý exception từ handler:** Nếu `handleCreate` ném lỗi trước khi reset, key có thể vẫn ở trạng thái signal. Sử dụng `try/finally`, điều phối retry hoặc ghi nhận lỗi sao cho lifecycle được đảm bảo.
- **Không làm việc nặng trực tiếp trong watcher thread:** Dùng queue xử lý nghiệp vụ; đảm bảo tránh backlog/OVERFLOW và quyết định lúc nào reset phù hợp.
- **Hủy WatchService khi shutdown:** Dùng `close()`, xử lý `ClosedWatchServiceException`/interrupt, không giữ thread chờ vô thời hạn.
- **Khi watch multiple roots:** Map key với quyền/tenant/root config để không trộn dữ liệu.
- **Khi OVERFLOW:** Rescan directory theo state của ứng dụng. Không chỉ bỏ qua.
- **Khi MOVE/RENAME:** Có thể thể hiện thành create/delete; không giả định một event rename riêng theo chuẩn.
- **Khi thấy directory mới:** Nếu cần recursive monitoring, đăng ký và scan nó.
- **Khi file chưa hoàn tất:** Phối hợp với producer để có tín hiệu hoàn thành, idempotent processing, retry khi I/O chập chờn.
- **Nếu mục tiêu là backup/index:** WatchService nên là trigger cập nhật state, không phải nguồn sự thật duy nhất.

## 14. Khi file tồn tại, đã hoàn tất hoặc là regular file?

Context được resolve **không tự xác thực** đối tượng được mở. Với `ENTRY_CREATE` hoặc `ENTRY_MODIFY`, thường có thể kiểm tra loại entry:

~~~java
if (Files.isRegularFile(changedEntry)) {
    // Đọc theo format/cơ chế phối hợp với producer.
}
~~~

Đây là đoạn minh họa. `Files.isRegularFile` mặc định có thể theo symbolic link; nếu không muốn theo link:

~~~java
if (Files.isRegularFile(
        changedEntry, LinkOption.NOFOLLOW_LINKS)) {
    // Kiểm tra loại entry mà không theo symbolic link.
}
~~~

**Những giới hạn quan trọng:**

- `Files.isRegularFile` có thể trả false khi không xác định được attributes, không chỉ khi đó là directory.
- File có thể biến mất giữa kiểm tra và mở, hoặc bị thay thế bằng symbolic link (**TOCTOU**).
- `ENTRY_CREATE` không đảm bảo file đã ghi xong; `ENTRY_MODIFY` không đảm bảo producer đã đóng stream.
- Một file có thể thay đổi nhiều lần trong khoảng cách xử lý; event chỉ là tín hiệu nên **cần làm việc với trạng thái filesystem hiện tại**.
- Với `ENTRY_DELETE`, không cố gọi `readString` theo mặc định; cần cập nhật trạng thái lưu trước đó.

### 14.1. Path lexical không phải hàng rào bảo mật

Một số code kiểm tra:

~~~java
Path base = watchedDir.toAbsolutePath().normalize();
Path full = base.resolve(relative).normalize();
if (!full.startsWith(base)) {
    // Từ chối escape '..' theo cú pháp path.
}
~~~

Đây chỉ là bước kiểm tra **lexical escape**. Một symlink bên trong base có thể trỏ ra ngoài base. Nếu xử lý file do người dùng hoặc tiến trình không tin cậy tạo, cần kiểm soát quyền root, symlink policy và phương thức mở file an toàn theo provider; không chỉ `normalize()`, `startsWith()` hoặc `exists()`.

## 15. Các giới hạn WatchService theo hệ điều hành và filesystem

Javadoc hiện hành nhấn mạnh những điều sau:

| Giới hạn | Tác động | Hướng giảm rủi ro |
| --- | --- | --- |
| Thời điểm event được báo phụ thuộc OS/provider | Delay khác nhau | Timeout trong test, monitoring trong production |
| Một thay đổi có thể gây nhiều MODIFY | Xử lý trùng | Debounce, idempotency |
| Một số event có thể bị coalesced hoặc bỏ | Không có log exactly-once | Rescan/reconciliation |
| OVERFLOW khi queue quá tải | Index/cache không đầy đủ | Đối soát trạng thái filesystem |
| File có thể chưa hoàn tất lúc có event | Đọc dữ liệu lỗi/thiếu | Giao thức hoàn tất với producer, retry |
| File sống rất ngắn có thể bị bỏ qua | Không đủ cho audit tuyệt đối | Quét định kỳ/giao thức riêng |
| Watch filesystem mạng không luôn đáng tin | Không phát hiện remote changes | Kiểm thử provider; polling/reconcile |
| Đổi tên/move watched directory | WatchKey/watchable có thể không còn path hợp lệ | Check validity, re-register |
| Directory mất quyền hoặc bị xóa | `reset()` có thể false | Remove registration hoặc recover |
| Không recursive | Không thấy file trong subdir | Register từng subdir + scan |
| Thứ tự event khác giữa providers | Không suy được lịch sử giao dịch | Dựa trên trạng thái thật, không log assumption |
| Symlink/permission | Có thể vượt root nghiệp vụ | Policy no-follow/secure access |

Không nên viết test phụ thuộc nguyên văn message lỗi, thứ tự event CREATE/MODIFY ngoài contract, hoặc đường dẫn tạm sinh ngẫu nhiên. Các ví dụ in boolean/số liệu ổn định; integration test vẫn có thể fail trên provider không phát sự kiện trong thời hạn.

## 16. Ngộ nhận phổ biến

| Ngộ nhận | Điều đúng |
| --- | --- |
| “`event.context()` đã là absolute path.” | Với các kind entry chuẩn, đó là `Path` tương đối. |
| “`context.toAbsolutePath()` sẽ ra đúng file watched.” | Có thể lấy working directory sai; dùng `watchedDir.resolve(context)`. |
| “Mọi WatchKey đều chỉ cùng directory.” | WatchService chứa nhiều registrations; lấy đúng `watchable` của key. |
| “Hai event cùng context tên `same.txt` là một file.” | Có thể thuộc hai directory khác nhau. |
| “Có thể cast context thành Path cho mọi kind.” | OVERFLOW có context Object, có thể null. |
| “OVERFLOW là filename tên OVERFLOW.” | Không; báo có thể mất event, phải rescan. |
| “`count=3` nghĩa ba file thay đổi.” | Count có thể gộp các lần nhận cùng event/context. |
| “ENTRY_DELETE có file để đọc khi xử lý.” | File có thể đã xóa/di chuyển hoặc tên đã dùng lại. |
| “ENTRY_CREATE chứng minh producer đã ghi xong.” | Không, file có thể đang được ghi. |
| “ENTRY_MODIFY luôn có chính xác một event mỗi lần lưu.” | Có thể nhiều hoặc gộp event. |
| “Dùng `pollEvents()` một lần chỉ có một event.” | Có thể là danh sách nhiều event. |
| “Không cần `reset()` sau xử lý.” | Reset cần cho vòng đời signal/ready. |
| “`reset()==false` vẫn theo dõi bình thường.” | Registration không còn hợp lệ. |
| “Register root là recursive watcher.” | Phải register subdirectory riêng. |
| “Code chạy trong Windows/Linux/macOS có thời điểm event giống hệt.” | Provider-dependent. |
| “`Files.exists()` là kiểm tra an ninh đủ.” | Race/permission/symlink vẫn tồn tại. |
| “`Path.normalize()` khóa được mọi symlink escape.” | Chỉ lexical normalization. |
| “WatchService đảm bảo không mất event.” | Có thể OVERFLOW/bỏ qua/thời điểm phụ thuộc provider. |
| “Một event là một commit giao dịch filesystem.” | Chỉ là notification, không chứa snapshot nhất quán. |
| “WatchService tự chặn app bị backlog do xử lý chậm.” | App phải thiết kế queue/reconcile riêng. |

## 17. Checklist triển khai

1. Đã đăng ký đúng `Path directory` với WatchService?
2. Đã giữ đúng WatchKey hoặc `Map<WatchKey, Path>`?
3. Đã xử lý `kind` trước khi đọc/ép kiểu context?
4. Đã xử lý `OVERFLOW` bằng rescan/reconcile thay vì resolve null?
5. Context chuẩn được kiểm tra là `Path` và tương đối?
6. Đã dùng `key.watchable()`/đúng registration directory khi resolve?
7. Đã tránh lấy `context.toAbsolutePath()` làm path đích?
8. Đã xử lý hai directory chứa cùng filename?
9. Đã phân biệt CREATE/MODIFY/DELETE về tính tồn tại/độ hoàn chỉnh file?
10. Đã có cơ chế idempotency/debounce/retry nếu cần?
11. Đã xử lý `event.count()>1` mà không hiểu nhầm là nhiều path?
12. Đã dùng `pollEvents()` để nhận cả batch?
13. Đã reset key và kiểm tra invalid?
14. Đã đóng WatchService/định nghĩa shutdown?
15. Có timeout khi test để tránh chờ vô hạn?
16. Có test tạo file **sau khi** register?
17. Có test event thật ở hai directory cùng filename?
18. Có test DELETE và file không còn tồn tại?
19. Có unit test OVERFLOW/context null rõ là simulated?
20. Có test subdir cần đăng ký riêng nếu muốn theo dõi sâu?
21. Có bảo vệ symlink/root/permission theo threat model?
22. Có tránh gọi `Files.isRegularFile` rồi tin file không đổi ngay sau đó?
23. Có đối soát nếu file nằm trên remote/network filesystem?
24. Có ghi rõ API cốt lõi Java 7 và cú pháp/tính năng ví dụ Java 17+?
25. Có test trên OS/FileStore thực mà sản phẩm hỗ trợ trước khi kết luận đa nền tảng?

## 18. Câu hỏi tự kiểm tra

**1.** Với event `ENTRY_CREATE`, `event.context()` là absolute path hay relative path?  
**Đáp án:** `Path` tương đối với directory đã register.

**2.** Lấy directory của event từ đâu?  
**Đáp án:** `key.watchable()` (đã đăng ký `Path`) hoặc map WatchKey→Path.

**3.** Công thức ghép file cần xử lý?  
**Đáp án:** `watchedDir.resolve(relativeContext)` sau khi kiểm tra kind/context.

**4.** Vì sao `context.toAbsolutePath()` có thể sai?  
**Đáp án:** Có thể resolve từ working directory thay vì watched directory.

**5.** Hai directory có cùng `same.txt`: phân biệt sao?  
**Đáp án:** Lấy base từ từng WatchKey; hai resolved paths khác nhau.

**6.** OVERFLOW có context Path không?  
**Đáp án:** Không được giả định; nó có kiểu Object và có thể null.

**7.** Gặp OVERFLOW thì nên làm gì?  
**Đáp án:** Quét/đối soát lại directory vì có thể đã mất event.

**8.** `event.count()==3` chứng minh ba file khác nhau?  
**Đáp án:** Không; có thể là sự kiện cùng kind/context được ghi nhận nhiều lần.

**9.** ENTRY_DELETE có thể resolve Path mặc dù file bị xóa?  
**Đáp án:** Có; Path chỉ là vị trí entry, không giữ file tồn tại.

**10.** ENTRY_CREATE báo file đã ghi xong?  
**Đáp án:** Không; producer có thể vẫn đang ghi.

**11.** `pollEvents()` trả một hay nhiều sự kiện?  
**Đáp án:** Một danh sách event của WatchKey đang chờ.

**12.** Sau xử lý phải gọi gì?  
**Đáp án:** `key.reset()` và kiểm tra trạng thái valid.

**13.** `reset()==false` có nghĩa gì?  
**Đáp án:** Registration không còn hợp lệ, cần xử lý lifecycle.

**14.** WatchService có tự watch `root/sub/` khi chỉ register `root` không?  
**Đáp án:** Không; phải register subdirectory riêng.

**15.** Test nên dùng `take()` chờ vô hạn?  
**Đáp án:** Với integration test nên dùng `poll(timeout, TimeUnit)` để có deadline.

**16.** `normalize()` có ngăn symlink trỏ ra ngoài root không?  
**Đáp án:** Không; đó là lexical operation.

**17.** Vì sao phải xử lý event kind không quen thuộc?  
**Đáp án:** Provider có thể định nghĩa event khác, context có kiểu khác.

**18.** Có phải WatchService lưu lịch sử sự kiện đầy đủ, không bị mất?  
**Đáp án:** Không; OVERFLOW và platform dependencies làm mất/gộp event có thể xảy ra.

**19.** Có cần `Files.isRegularFile` trước xử lý file không?  
**Đáp án:** Tùy nghiệp vụ, nhưng việc kiểm tra vẫn có thể race và kết quả false chưa chắc chứng minh directory.

**20.** Mấu chốt của toàn bài là gì?  
**Đáp án:** Lấy **đúng watched directory** từ WatchKey rồi resolve **relative event context**, phân loại OVERFLOW và xử lý đúng lifecycle WatchKey.

## 19. Nguồn chính thức

- [Oracle Java SE 26 — WatchEvent](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/WatchEvent.html): hợp đồng `context()`, `kind()`, `count()`.
- [Oracle Java SE 26 — WatchKey](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/WatchKey.html): `watchable`, `pollEvents`, `reset`, state machine.
- [Oracle Java SE 26 — WatchService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/WatchService.html): event loop, overflow và platform dependencies.
- [Oracle Java SE 26 — StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): các kind entry chuẩn và OVERFLOW.
- [Oracle Java SE 26 — Path.register](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html): registration directory và relative context.
- [Oracle Java SE 26 — Path.resolve/normalize](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Path.html): ghép context và lexical normalization.
- [Oracle Java SE 26 — FileSystem.newWatchService](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileSystem.html): tạo watcher theo provider.
- [Oracle Java SE 26 — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): `Files.isRegularFile`, `exists`, `newDirectoryStream`, `list`, `readAttributes`.
- [Oracle Java SE 26 — ClosedWatchServiceException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/ClosedWatchServiceException.html): service bị đóng.
- [Oracle Java SE 26 — LinkOption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/LinkOption.html): chính sách NOFOLLOW_LINKS.
- [Oracle Java SE 17 — WatchEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html): đối chiếu với JDK target của ví dụ.
- [Oracle Java SE 7 — WatchService](https://docs.oracle.com/javase/7/docs/api/java/nio/file/WatchService.html): mốc ra đời Java 7; dùng API hiện hành cho ứng dụng mới.

**Ghi nhớ:** `event.context()` của ENTRY_CREATE/ENTRY_DELETE/ENTRY_MODIFY là **relative Path**, không phải full path. Lấy **directory đúng từ `key.watchable()`**, ghép bằng `resolve()`, xử lý OVERFLOW trước khi cast, rồi gọi `key.reset()`. Việc nhận event không chứng minh file còn tồn tại, đã ghi xong hoặc mọi sự kiện đều đã tới; kiểm tra filesystem và quản lý đối soát phù hợp nghiệp vụ.