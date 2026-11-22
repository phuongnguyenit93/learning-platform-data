# `WatchKey`, `pollEvents()` và đường dẫn tương đối của sự kiện trong Java NIO.2

## 1. Mục tiêu bài học

`java.nio.file.WatchService` (Java NIO.2) giúp chương trình nhận thông báo về những thay đổi **trong thư mục đã đăng ký**: một mục mới được tạo, một mục bị xóa, hoặc mục bị sửa đổi. Nhưng kết quả từ watcher không phải một chuỗi đường dẫn tuyệt đối sẵn dùng; mỗi lần thông báo, bạn nhận một **`WatchKey`**, lấy danh sách sự kiện bằng `pollEvents()`, rồi kết hợp **`WatchEvent.context()`** với thư mục gắn với key.

Đây là ba mắt xích phải dùng đúng:

- **`WatchKey`**: đại diện cho lần đăng ký của một đối tượng `Watchable` (thường là một thư mục `Path`) với một `WatchService`. Key quản lý hàng đợi sự kiện của registration và trạng thái cần `reset()`.
- **`key.pollEvents()`**: trả danh sách những sự kiện đang chờ của **key đó** và loại những sự kiện đã lấy khỏi hàng đợi của key.
- **`event.context()`**: với các event của thư mục qua provider mặc định, thường là một `Path` **tương đối với thư mục đã đăng ký**, ví dụ `report.txt`, không phải đường dẫn tuyệt đối của tệp.

Sau bài này, bạn có thể tạo watcher, hiểu vòng đời key, ghép `watchable.resolve(context)` đúng cách, tránh nhầm `WatchService.poll()` và `WatchKey.pollEvents()`, xử lý `ENTRY_CREATE`/`ENTRY_DELETE`/`ENTRY_MODIFY`/`OVERFLOW`, quản lý nhiều thư mục và biết giới hạn độ tin cậy của thông báo filesystem.

Ví dụ ưu tiên Java 17+, không yêu cầu thư viện ngoài. Đầu ra có điều kiện về môi trường sẽ được ghi rõ: WatchService phụ thuộc provider, filesystem, OS và thời điểm phát hiện sự kiện.

## 2. Các đối tượng và phương thức quan trọng

| Đối tượng / API | Vai trò |
| --- | --- |
| `WatchService` | Dịch vụ tập trung nhận các **watch key đã được signal**, do `FileSystems.getDefault().newWatchService()` tạo |
| `Path.register(service, kinds...)` | Đăng ký một `Path` (thường là thư mục) và các loại thay đổi với service, trả `WatchKey` |
| `WatchKey` | Registration cụ thể: biết `watchable()`, `pollEvents()`, `reset()`, `isValid()`, `cancel()` |
| `WatchService.take()` | **Chặn** tới khi có key được báo hoặc dịch vụ đóng |
| `WatchService.poll()` | Thử lấy key đang chờ, trả `null` nếu chưa có |
| `WatchService.poll(timeout, unit)` | Đợi tối đa thời hạn để lấy key, có thể trả `null` |
| `WatchKey.pollEvents()` | Rút danh sách sự kiện của **một key** hiện có |
| `WatchEvent.kind()` | Loại sự kiện, chẳng hạn `ENTRY_CREATE` hoặc `OVERFLOW` |
| `WatchEvent.context()` | Context gắn với sự kiện: đối với entry event, thường là `Path` tương đối |
| `WatchEvent.count()` | Số lần sự kiện cùng loại/context đã được gộp theo hợp đồng |
| `WatchKey.reset()` | Xác nhận đã xử lý và đưa key về trạng thái có thể tiếp tục nhận signal; trả `false` nếu key không còn valid |
| `WatchKey.cancel()` | Hủy registration, không xóa file và không tự đóng service |

Một `WatchService` có thể phục vụ nhiều thư mục. Mỗi thư mục đăng ký có `WatchKey` riêng; khi nhận một key, trước tiên phải biết **key thuộc thư mục nào** rồi mới giải quyết event context.

### Hai chữ “poll” nhưng làm hai việc khác nhau

```text
watcher.poll()  hoặc watcher.take()
   |
   v
WatchKey key                 <-- lấy key đã được signal
   |
   +--> key.watchable()      <-- thư mục đã đăng ký
   |
   +--> key.pollEvents()     <-- lấy List<WatchEvent<?>>
          |                       của key này
          v
      kind / context / count
   |
   +--> key.reset()          <-- cho phép theo dõi tiếp
```

`watcher.poll()` **không** trả danh sách event; nó trả `WatchKey` hoặc `null`. Ngược lại, `key.pollEvents()` không dùng để chờ service có sự kiện mới; nó chỉ lấy các event đã được tích lũy trên key đó.

## 3. Đăng ký một thư mục

Đoạn mẫu cơ bản:

```java
Path watchedDir = Path.of("inbox").toAbsolutePath().normalize();

try (WatchService watcher =
        FileSystems.getDefault().newWatchService()) {

    WatchKey registration = watchedDir.register(
            watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_DELETE,
            StandardWatchEventKinds.ENTRY_MODIFY);

    // Sau đó gọi watcher.take() hoặc watcher.poll(timeout, unit).
}
```

Đây là **snippet**, chưa phải chương trình độc lập. Nó giả định `inbox` đã tồn tại, là thư mục mà provider hỗ trợ theo dõi; cần import `java.nio.file.*` và xử lý `IOException`.

Ý nghĩa của từng kind:

- `ENTRY_CREATE`: phát hiện một entry được tạo trong thư mục.
- `ENTRY_DELETE`: phát hiện một entry bị xóa khỏi thư mục.
- `ENTRY_MODIFY`: phát hiện một entry được sửa đổi, theo khả năng và chính sách provider.
- `OVERFLOW`: một hoặc nhiều sự kiện có thể bị bỏ hoặc mất; **không đăng ký `OVERFLOW` như một loại watch event thông thường**; watcher có thể báo nó bất kể các kind cụ thể đã đăng ký.

Đối tượng được đăng ký **là thư mục** (theo cách dùng chuẩn của default filesystem provider) chứ không phải tên của một file riêng lẻ. Đăng ký `inbox` tức là theo dõi các entry **trực tiếp** bên dưới `inbox`, chứ không tự động theo dõi toàn bộ cây thư mục con.

Nếu ứng dụng cần giám sát `inbox/a/b/file.txt` mà chỉ đăng ký `inbox`, bạn không nên tin rằng sẽ có `ENTRY_MODIFY` cho một tệp sâu nhiều cấp. Hãy đăng ký thư mục con cần thiết và xử lý trường hợp thư mục mới được tạo trong lúc chạy.

## 4. `WatchKey` đại diện cho cái gì?

Một `WatchKey` là một registration với watcher. Sau khi đăng ký, nó cung cấp:

```java
Watchable observed = key.watchable();
boolean valid = key.isValid();
List<WatchEvent<?>> events = key.pollEvents();
boolean stillValid = key.reset();
```

**Snippet minh họa**: biến `key` được giả định tồn tại, cần import `Watchable`, `WatchKey`, `WatchEvent` và `List`. Với watcher thư mục đăng ký bằng `Path.register`, `key.watchable()` là `Path` của thư mục đã đăng ký. Không nên tự động hiểu mọi implementation `Watchable` đều là `Path`; ở đây phạm vi là watcher filesystem thư mục.

Một số điểm quan trọng:

1. `key.watchable()` trả **đối tượng gốc được đăng ký**, không phải file vừa thay đổi.
2. `key.isValid()` có thể trở thành false khi registration bị cancel, watcher bị đóng hoặc đối tượng không còn theo dõi được (ví dụ thư mục bị xóa).
3. `key.cancel()` dừng theo dõi; nó không thực hiện xóa hay chuyển file.
4. `key.reset()` phải được gọi sau khi xử lý event; kết quả `false` là tín hiệu không nên chờ registration ấy nữa.
5. Khi nhiều thay đổi xảy ra nhanh trước khi thread lấy key, một key có thể chứa **nhiều event**, và cùng loại event có thể được gộp với `count()`.
6. Khi `WatchService` bị đóng, các lời gọi chờ và thao tác liên quan có thể báo `ClosedWatchServiceException`; quản lý vòng đời service đúng cách.

### Trạng thái ready và signalled

Khái niệm trạng thái của một key:

```text
Đã register
    |
    v
 READY -- có sự kiện --> SIGNALLED và được đưa vào hàng đợi của WatchService
    |                       |
    |                       v
    |             watcher.take() / poll()
    |                       |
    |                       v
    |               key.pollEvents()
    |                       |
    |                       v
    +<--------- key.reset() nếu valid
                            |
                            +-- nếu có thêm event đang chờ,
                                key có thể tiếp tục được đưa vào
                                hàng đợi của WatchService
```

`pollEvents()` chỉ lấy event; **nó không tự đưa key về READY**. Vì vậy nếu quên `reset()`, chương trình có thể xử lý một đợt rồi không được báo đợt mới như mong đợi.

Không được thay `reset()` bằng `cancel()` sau mỗi lần xử lý: `cancel()` hủy registration, trong khi `reset()` xác nhận key và tiếp tục giám sát.

## 5. `pollEvents()`: lấy danh sách sự kiện đúng cách

`WatchKey.pollEvents()` trả `List<WatchEvent<?>>`:

```java
WatchKey key = watcher.take();
for (WatchEvent<?> event : key.pollEvents()) {
    WatchEvent.Kind<?> kind = event.kind();
    Object context = event.context();
    int count = event.count();
    // Xử lý loại, context và số lần sự kiện đã gộp.
}
boolean valid = key.reset();
```

Đây là đoạn minh họa cần `watcher` đã tạo/đăng ký và các import. Điểm cần nhớ:

- `pollEvents()` chỉ lấy các event **đang chờ của một key**; danh sách có thể rỗng trong một số tình huống, không có nghĩa watcher hỏng.
- Nó **loại những event vừa lấy khỏi hàng đợi của key**. Gọi lại `pollEvents()` ngay thường sẽ không trả lại cùng các object event cũ.
- `pollEvents()` có thể chứa nhiều kind khác nhau; không suy ra “một `take` ứng với đúng một file”.
- `event.count()` có thể lớn hơn 1 do nhiều sự kiện giống nhau được gộp. Không thiết kế logic “mỗi event object == đúng một lần sửa file”.
- Có thể có `OVERFLOW`, kể cả khi bạn đăng ký chỉ `ENTRY_CREATE`.
- Sau khi xử lý cần gọi `reset()`, kể cả khi bạn bỏ qua một số kind; nếu false, loại registration khỏi state nội bộ.

Đừng giữ kết quả `pollEvents()` làm danh sách tuyệt đối phản ánh mọi thay đổi trên filesystem. Nó là thông báo để ứng dụng **kiểm tra lại trạng thái** khi cần.

### `WatchService.take()` / `poll()` / `poll(timeout)`

| Cách lấy key | Khi nào hợp lý |
| --- | --- |
| `take()` | Vòng watch chuyên dụng, chấp nhận chặn đến khi có key |
| `poll()` | Event loop đã có công việc khác, chỉ kiểm tra không chờ |
| `poll(5, TimeUnit.SECONDS)` | Muốn chờ có giới hạn, xử lý timeout/hủy |
| `close()` | Đóng WatchService, giải phóng resource, đánh thức thread đang chờ qua ngoại lệ tương ứng |

`take()` có thể ném `InterruptedException` khi thread bị interrupt. `poll(timeout, unit)` cũng có thể bị interrupt và trả `null` khi hết thời hạn không có key. Đừng biến timeout thành “file không còn tồn tại”: chỉ kết luận **không có key được lấy trong khoảng chờ ấy**.

## 6. `WatchEvent.context()` là đường dẫn tương đối

Đây là trọng tâm của bài.

Giả sử đăng ký thư mục:

```text
/opt/app/inbox
```

Một file được tạo:

```text
/opt/app/inbox/report.csv
```

Với event thuộc `ENTRY_CREATE`, context thường là:

```text
report.csv
```

Chứ không phải `/opt/app/inbox/report.csv`. Cách tạo đường dẫn đến entry bị tác động:

```java
Path registeredDirectory = (Path) key.watchable();
Path relative = (Path) event.context();
Path changed = registeredDirectory.resolve(relative);
```

Ba dòng là **snippet**, chỉ dùng khi `event.kind()` là một entry event có `Path` context và key thực sự đến từ `Path.register()`. Có thể thêm `toAbsolutePath().normalize()` khi cần một dạng địa chỉ thống nhất cho log hoặc so sánh.

Quan trọng:

- **Relative to watched directory**, không phải relative to current working directory của Java process.
- Nếu watcher đăng ký nhiều thư mục, phải lấy thư mục từ **đúng key** đang xử lý; nếu lấy nhầm thư mục, đường dẫn ghép sẽ sai.
- `WatchEvent.context()` được khai báo kiểu generic `T`, nhưng danh sách `pollEvents()` có kiểu `WatchEvent<?>`. Không nên cast `Path` với `OVERFLOW`: context của `OVERFLOW` có thể là `null`.
- `ENTRY_DELETE` thông báo một entry từng tồn tại bị xóa; sau đó `Files.exists(changed)` có thể false, không thể mặc định mở nội dung.
- `ENTRY_CREATE`/`ENTRY_MODIFY` không bảo đảm file còn tồn tại hoặc vẫn ở trạng thái lúc sự kiện xảy ra khi code xử lý.
- `normalize()` chỉ chuẩn hóa cú pháp `.`/`..`; không chứng minh một đường dẫn có được phép truy cập hay tránh escape qua symbolic links. Với đường dẫn không đáng tin, bổ sung kiểm tra an toàn phù hợp.

### Nên giữ `Path` tuyệt đối ngay khi đăng ký

Ví dụ:

```java
Path watchedDir = Path.of("inbox").toAbsolutePath().normalize();
WatchKey key = watchedDir.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE);
```

Nếu dùng thư mục relative `Path.of("inbox")` để đăng ký, `key.watchable()` có thể là `Path` relative giống giá trị đã đăng ký. Khi dùng tiếp trong một hệ thống phức tạp hoặc lưu log, dạng absolute normalized thường giúp tránh nhầm với đường dẫn ở subsystem khác. Nó vẫn không loại bỏ mọi race condition/symlink.

### Mô hình kết hợp nhiều thư mục

```text
WatchService
   |
   +--> WatchKey A --> watchable() = /data/a
   |                          context() = first.txt
   |                          resolved = /data/a/first.txt
   |
   +--> WatchKey B --> watchable() = /data/b
                              context() = second.txt
                              resolved = /data/b/second.txt
```

Cả hai event đều có thể dùng cùng một tên `output.log`. Chỉ dùng `context().toString()` làm khóa định danh duy nhất trên toàn bộ watcher là sai nếu đang theo dõi nhiều thư mục. Khóa có thể cần bao gồm thư mục/watch registration cộng relative context.

## 7. Ví dụ Java 17+ chạy được: quan sát event và ghép `Path`

Ví dụ đầu tiên tạo thư mục tạm, đăng ký watch, tạo file `note.txt`, chờ `ENTRY_CREATE` rồi in loại sự kiện, tên tương đối và kết quả giải quyết vào thư mục gốc. Lệnh chỉ in event **đúng tên** nên không phụ thuộc vào số `ENTRY_MODIFY` bổ sung được OS phát ra.

Lưu thành **`WatchKeyRelativePathDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.concurrent.TimeUnit;

public class WatchKeyRelativePathDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("watch-relative-")
                        .toAbsolutePath().normalize();
        Path file = dir.resolve("note.txt");

        try {
            try (WatchService watcher =
                         FileSystems.getDefault().newWatchService()) {

                dir.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY);

                Files.writeString(file, "hello");
                boolean found = false;
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (!found) {
                    long left = deadline - System.nanoTime();
                    if (left <= 0) {
                        throw new IOException("ENTRY_CREATE not reported");
                    }

                    WatchKey key = watcher.poll(
                            left, TimeUnit.NANOSECONDS);
                    if (key == null) {
                        throw new IOException("Timed out waiting for event");
                    }

                    Path watchedDir = (Path) key.watchable();

                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.OVERFLOW) {
                            // Ứng dụng thật cần rescan thư mục.
                            continue;
                        }

                        if (event.kind()
                                != StandardWatchEventKinds.ENTRY_CREATE) {
                            continue;
                        }

                        // Với entry events của Path watcher, context là Path.
                        Path relative = (Path) event.context();
                        if (relative.equals(Path.of("note.txt"))) {
                            Path changed = watchedDir.resolve(relative)
                                    .toAbsolutePath().normalize();
                            System.out.println("kind="
                                    + event.kind().name());
                            System.out.println("relative=" + relative);
                            System.out.println("resolvedMatches="
                                    + changed.equals(file));
                            found = true;
                        }
                    }

                    boolean valid = key.reset();
                    if (!valid) {
                        throw new IOException("Directory registration invalid");
                    }
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy:

```bash
javac WatchKeyRelativePathDemo.java
java WatchKeyRelativePathDemo
```

**Stdout điển hình khi filesystem/provider báo `ENTRY_CREATE` trong thời hạn:**

```text
kind=ENTRY_CREATE
relative=note.txt
resolvedMatches=true
```

Đây là output **có điều kiện**, không phải lời hứa mọi platform đều phát event giống nhau. Nếu provider không gửi `ENTRY_CREATE` trong năm giây, chương trình ném `IOException` nêu rõ lý do. Các event `ENTRY_MODIFY` bổ sung không được in nên không gây sai dữ liệu mẫu.

Vì sao `resolvedMatches=true`? Khi đăng ký, `dir` đã là absolute normalized. `event.context()` cho file mới là `Path.of("note.txt")` tương đối với `dir`. `watchedDir.resolve(relative)` ghép lại đúng đường dẫn `file` đã dùng để tạo entry.

Ví dụ còn thể hiện `key.reset()` **sau khi lấy và xử lý danh sách sự kiện**. Không gọi `reset()` sớm khi chương trình vẫn chưa quyết định xử lý payload vì có thể phức tạp hóa việc điều phối event ở ứng dụng thực tế.

## 8. Ví dụ Java 17+ chạy được: một service, nhiều thư mục

Khi theo dõi nhiều folder, `key.watchable()` hoặc một `Map<WatchKey, Path>` là cách lấy root đúng. Nếu mỗi thư mục dùng một watcher riêng sẽ tốn thêm tài nguyên và gây khó quản lý; một service có thể đủ cho một nhóm thư mục cùng filesystem/provider.

Ví dụ có hai thư mục `a` và `b`. Chương trình cố ý sắp xếp kết quả trước khi in để output không phụ thuộc vào thứ tự watcher giao key.

Lưu file **`MultiDirectoryWatchDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.TimeUnit;

public class MultiDirectoryWatchDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("multi-watch-");
        Path dirA = Files.createDirectory(root.resolve("a"));
        Path dirB = Files.createDirectory(root.resolve("b"));
        Path fileA = dirA.resolve("first.txt");
        Path fileB = dirB.resolve("second.txt");

        try {
            try (WatchService watcher =
                         FileSystems.getDefault().newWatchService()) {

                Map<WatchKey, Path> roots = new HashMap<>();
                roots.put(dirA.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE), dirA);
                roots.put(dirB.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE), dirB);

                Files.createFile(fileA);
                Files.createFile(fileB);

                Set<String> found = new TreeSet<>();
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (found.size() < 2) {
                    long left = deadline - System.nanoTime();
                    if (left <= 0) {
                        throw new IOException("Missing create notifications");
                    }

                    WatchKey key = watcher.poll(
                            left, TimeUnit.NANOSECONDS);
                    if (key == null) {
                        throw new IOException("Watcher timeout");
                    }

                    Path watched = roots.get(key);
                    if (watched == null) {
                        throw new IOException("Unknown watch key");
                    }

                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.OVERFLOW) {
                            throw new IOException(
                                    "Overflow; directory rescan required");
                        }

                        if (event.kind()
                                != StandardWatchEventKinds.ENTRY_CREATE) {
                            continue;
                        }

                        Path relative = (Path) event.context();
                        Path changed = watched.resolve(relative);

                        if (changed.equals(fileA)) {
                            found.add("a/" + relative);
                        } else if (changed.equals(fileB)) {
                            found.add("b/" + relative);
                        }
                    }

                    if (!key.reset()) {
                        roots.remove(key);
                        throw new IOException("Watched directory invalid");
                    }
                }

                for (String item : found) {
                    System.out.println(item);
                }
                System.out.println("createdEntries=" + found.size());
            }
        } finally {
            Files.deleteIfExists(fileA);
            Files.deleteIfExists(fileB);
            Files.deleteIfExists(dirA);
            Files.deleteIfExists(dirB);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac MultiDirectoryWatchDemo.java
java MultiDirectoryWatchDemo
```

**Stdout khi cả hai thông báo được nhận thành công:**

```text
a/first.txt
b/second.txt
createdEntries=2
```

Điểm học được:

- `Map<WatchKey, Path>` gắn registration với thư mục của chính nó. `key.watchable()` cũng có thể được cast thành `Path` vì các key trong ví dụ được tạo từ `Path.register()`.
- Hai key có thể được watcher trả về theo bất kỳ thứ tự nào. `TreeSet` sắp xếp để minh họa output ổn định khi cùng hai entry đã được phát hiện.
- `Files.createFile` tạo file trống; event `ENTRY_CREATE` ở đây chỉ cần xác định việc tạo entry, không cần đọc nội dung.
- Khi một key invalid, code loại nó khỏi `roots` và báo lỗi. Ứng dụng vận hành lâu dài phải quyết định đăng ký lại hoặc ngừng theo dõi thư mục tương ứng.
- Đây không phải hệ thống theo dõi sản xuất có thể tự hồi phục sau `OVERFLOW`. Trong trường hợp đó, **phải quét lại trạng thái** và đối chiếu với snapshot của ứng dụng.

**Chú ý:** thứ tự thông báo OS/provider, thời điểm sẵn sàng và độ hỗ trợ `WatchService` phụ thuộc môi trường. Nếu không nhận đủ event, chương trình ném lỗi thay vì in kết quả thành công giả. Việc in sắp xếp không làm một provider thiếu event trở nên đáng tin hơn.

## 9. `OVERFLOW` và `count()`: tại sao không coi event là nhật ký đầy đủ?

Các thay đổi filesystem có thể xảy ra dồn dập, ví dụ một tiến trình chép hàng nghìn file vào thư mục hoặc chương trình khác sửa cùng file rất nhiều lần. Watch service có thể:

1. Gộp nhiều sự kiện có cùng kind và context thành một `WatchEvent` với `count()` lớn hơn 1.
2. Không phân biệt hết mọi thay đổi nếu hệ thống/provider không có chi tiết ấy.
3. Thông báo `OVERFLOW` khi sự kiện đã bị mất hoặc bỏ qua vì quá nhiều sự kiện.

Ví dụ kiểm tra event:

```java
for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        System.err.println("Changes were lost; rescan required");
        continue;
    }

    System.out.println(event.kind().name()
            + " " + event.context()
            + " count=" + event.count());
}
```

Đây là snippet chỉ dành cho minh họa. `count()` là số lần sự kiện cụ thể được tích lũy/gộp, **không** phải số file khác nhau bị tác động. Nếu nhận `ENTRY_MODIFY` với `count=5`, không kết luận chính xác có năm lần người dùng lưu file theo ý nghĩa nghiệp vụ.

### Chiến lược đúng sau `OVERFLOW`

- Quét lại thư mục/thư mục con cần theo dõi.
- Đối chiếu snapshot hiện tại (tên, kích thước, timestamp, checksum nếu thật sự cần) với trạng thái đã biết.
- Đồng bộ lại cache/chỉ mục công việc hoặc đánh dấu cần kiểm tra lại.
- Tiếp tục xử lý các event mới và `reset()` theo trạng thái key.
- Nếu cần audit tuyệt đối mọi lần đổi tên/nội dung theo thứ tự, `WatchService` **không đủ**; cần giao thức sự kiện hay nhật ký chuyên dụng do nguồn phát thay đổi quản lý.

`OVERFLOW` không nên được cast `event.context()` sang `Path`. Với event loại này context có thể `null`, và không có “file cụ thể” nào bảo đảm khôi phục được chỉ từ bản thân event.

## 10. `reset()`, hủy key và đóng service

Ba hành động bị nhầm:

| Thao tác | Ý nghĩa |
| --- | --- |
| `key.pollEvents()` | Lấy danh sách event đang đợi của key, không tự re-arm key |
| `key.reset()` | Xác nhận đã xử lý và cho key cơ hội được signal ở lượt tiếp; trả false nếu invalid |
| `key.cancel()` | Hủy đăng ký; không xóa directory hoặc đóng watcher |
| `watcher.close()` | Đóng toàn bộ WatchService, không còn dùng để nhận key |
| `key.isValid()` | Kiểm tra key hiện còn hợp lệ; không xác nhận dữ liệu event đầy đủ |

Mẫu xử lý chuẩn:

```java
while (running) {
    WatchKey key = watcher.take();
    try {
        for (WatchEvent<?> event : key.pollEvents()) {
            // Xử lý sự kiện, kể cả OVERFLOW.
        }
    } finally {
        boolean valid = key.reset();
        if (!valid) {
            // Loại key khỏi map registration, xử lý directory đã mất...
        }
    }
}
```

**Snippet không độc lập**; `running`, `watcher` và xử lý ngoại lệ do ứng dụng cung cấp. Mẫu này nhấn mạnh reset sau khi tiêu thụ event, ngay cả khi xử lý gặp vấn đề có thể khôi phục. Với chương trình thật, ngoại lệ nặng có thể dẫn đến đóng watcher thay vì tiếp tục.

Khi `reset()` trả `false`:

- Key không còn được dùng để chờ thay đổi mới.
- Có thể directory đã bị xóa, resource không còn truy cập được hoặc registration bị cancel.
- Loại nó khỏi `Map<WatchKey, Path>`, đóng các resource liên quan nếu không còn cần.
- Nếu directory xuất hiện trở lại, phải có cơ chế thích hợp để **đăng ký lại**; key cũ không tự sống lại.

Đừng coi `reset() == false` là một tín hiệu đủ để suy ra **lý do duy nhất** là directory bị xóa. Lý do cụ thể có thể phụ thuộc provider/lifecycle.

## 11. Path tương đối, thư mục công tác và tránh ghép sai

### 11.1. Không phải relative với current working directory

Ví dụ:

```text
Current working directory:  /home/app
Watched directory:          /home/data/input
WatchEvent.context():       report.csv
```

Sai về mặt ý nghĩa:

```java
Path wrong = Path.of(event.context().toString());
// Tại đây wrong được diễn giải theo working directory,
// không phải thư mục watcher đã đăng ký.
```

Đúng:

```java
Path watchedDir = (Path) key.watchable();
Path changed = watchedDir.resolve((Path) event.context());
```

Hai đoạn snippet trên chỉ minh họa, cần event entry có Path context. Nếu chương trình chạy trong thư mục khác, cách đúng vẫn lấy root từ key chứ không dựa vào `user.dir`.

### 11.2. Có thể chọn lưu mapping riêng

Nếu ứng dụng cần thêm metadata cho mỗi đăng ký (mã dự án, loại xử lý, snapshot), dùng cấu trúc:

```java
Map<WatchKey, Path> dirByKey = new HashMap<>();
WatchKey key = watchedDir.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE);
dirByKey.put(key, watchedDir);
```

Trong các hàm xử lý khác, lấy `watchedDir = dirByKey.get(key)`. Cần loại mapping khi key invalid hoặc service đóng. Không suy ra key cũ hợp lệ sau khi directory bị xóa và tạo lại.

### 11.3. Đường dẫn đã ghép không đảm bảo file còn tồn tại

Một watcher báo `ENTRY_CREATE`, nhưng khi handler chạy, file có thể đã bị xóa hoặc rename. Với `ENTRY_DELETE`, file hầu như thường không mở được nữa. Vì vậy quy trình tốt:

1. Tạo đường dẫn bằng đúng root và context.
2. Nếu định đọc, kiểm tra loại sự kiện và truy cập file với exception handling thực tế.
3. Chấp nhận rằng `Files.exists` rồi `Files.readAllBytes` vẫn có race giữa hai lời gọi.
4. Nếu nghiệp vụ cần bảo đảm file “đã hoàn tất ghi”, hãy có protocol publish rõ ràng (ví dụ tạo tệp tạm, ghi xong, đổi tên) thay vì dựa vào một `ENTRY_MODIFY`.
5. Với đầu vào không tin cậy, kiểm tra đường dẫn, symlink và quyền truy cập; không lấy `normalize()` làm biện pháp bảo mật duy nhất.

## 12. Không theo dõi đệ quy mặc định

Watch service thường phát event cho **entry trực tiếp** của directory đăng ký, không phải mọi file dưới các directory con.

```text
root/                      <- đăng ký WatchKey R
  a.txt                    <- event ở R
  nested/                  <- tạo nested -> event ở R
    b.txt                  <- sửa b.txt KHÔNG được R tự động
                               hứa phát event
```

Để theo dõi cả cây thư mục:

- Đầu tiên duyệt những directory hiện có và đăng ký từng directory.
- Khi nhận `ENTRY_CREATE` cho một directory mới, đăng ký directory đó và duyệt những directory con đã có.
- Khi nhận key invalid, loại mapping tương ứng.
- Xử lý race trong lúc quét/đăng ký: file có thể xuất hiện, biến mất hoặc thay đổi giữa các bước.
- Đối phó `OVERFLOW` bằng rescan; không giả định mọi thư mục mới đều đã được đăng ký đầy đủ nếu bị mất sự kiện.

Chức năng watch thư mục đệ quy cần thêm logic đáng kể; không có cờ `recursive=true` tiêu chuẩn của `Path.register(...)` cho mọi provider Java 17. Một số provider có modifier riêng, nhưng không lấy đặc tính riêng của platform làm cam kết portable.

## 13. Event name và hành vi nhà cung cấp

### `ENTRY_CREATE`

Một entry xuất hiện trong thư mục. Đây không nhất thiết là “file cuối cùng đã ghi đủ và sẵn sàng parse”. Một công cụ có thể tạo file rồi ghi tiếp trong nhiều lần. Để xử lý nội dung hoàn chỉnh, cần giao thức với nhà sản xuất file, ví dụ ghi file tạm và rename khi hoàn tất.

### `ENTRY_MODIFY`

Một entry bị sửa. Số lượng event có thể khác nhau theo OS/provider, kể cả nhiều event trong một thao tác nghiệp vụ hoặc event được gộp. Đừng coi `count()` là số lần lưu văn bản.

### `ENTRY_DELETE`

Entry bị xóa. Path context mô tả **tên entry đã biến mất**; thường không còn đối tượng để mở. Việc rename/move có thể được báo như delete ở một thư mục và create ở thư mục khác, nhưng không có yêu cầu portable rằng các sự kiện được liên kết thành một giao dịch rename duy nhất.

### `OVERFLOW`

Thay đổi có thể đã bị mất. Rescan; không có entry Path bắt buộc trong context.

### Phụ thuộc filesystem/provider

`WatchService` có thể được triển khai bằng notification native của OS hoặc bằng polling. Độ trễ, khả năng hỗ trợ, tính liên tục khi mất kết nối mạng, cách theo dõi mount từ xa, và việc xử lý symlink khác nhau theo provider.

Không thiết kế kiểm thử portable yêu cầu:

- Mọi lần ghi phát đúng một `ENTRY_MODIFY`.
- Mọi thao tác rename tạo event theo thứ tự tuyệt đối được bảo đảm.
- Có một thời gian cố định tính bằng mili-giây cho việc phát event.
- Mọi filesystem mạng hoạt động như ổ local.
- `pollEvents()` là audit trail đầy đủ của tất cả thay đổi.

Bản thân một thông báo chỉ nói “hãy quan sát lại state liên quan”, không thay thế API đọc/kiểm tra dữ liệu.

## 14. Quản lý các event trong hệ thống thật

Trong ứng dụng import file, thường phải xử lý một lượng lớn thay đổi nhanh. Cách tổ chức hữu ích:

1. Một thread watcher dùng `take()` hoặc `poll(timeout)` để lấy key.
2. Duyệt `pollEvents()`, xác định root qua key, lấy relative context và tạo Path hoàn chỉnh.
3. Chuyển việc đọc file/giải mã/parse tốn thời gian sang executor có giới hạn, tránh khiến watcher loop bỏ lỡ quá nhiều event.
4. `reset()` và kiểm tra kết quả; loại registration không hợp lệ.
5. Khi `OVERFLOW`, xếp lịch rescan có giới hạn và đồng bộ lại trạng thái.
6. Thiết kế tính idempotent (xử lý trùng event vẫn cho kết quả hợp lệ), snapshot/checksum nếu cần và backpressure cho hàng đợi.
7. Bảo đảm đóng `WatchService` và worker pool trong quy trình shutdown.

Nếu callback xử lý `ENTRY_MODIFY` quá chậm trước khi reset key, các thay đổi tiếp theo có thể bị dồn lại/gộp; queue của watcher có thể tràn. Điều phối watcher loop nhẹ nhàng và tách phần việc tốn thời gian thường là quyết định tốt.

**Lưu ý đặc biệt về race:** đưa một Path vào queue để worker mở sau đó **không** bảo đảm worker sẽ thấy chính nội dung file tại thời điểm event. Nếu cần version nhất quán, producer và consumer phải có protocol phối hợp (rename file hoàn thiện, manifest, khóa phù hợp hoặc content-addressed artifact).

## 15. Các lỗi thường gặp và cách sửa

1. **Nhầm `watcher.poll()` với `key.pollEvents()`.** Một cái lấy key; cái kia lấy sự kiện của key.
2. **Quên `key.reset()`.** Sau một đợt signal, key có thể không được nhận lại như mong muốn.
3. **Gọi `key.cancel()` thay `reset()`.** Cancel hủy theo dõi, không phải xác nhận đã xử lý.
4. **Giả định `event.context()` luôn là absolute Path.** Với entry event của directory, nó tương đối với watched directory; phải resolve đúng root.
5. **Resolve với working directory thay vì `key.watchable()`.** Có thể mở nhầm file ở location khác.
6. **Cast context sang Path trước khi kiểm tra `OVERFLOW`.** Context overflow có thể null; phân nhánh theo kind trước.
7. **Bỏ qua `WatchEvent.count()`.** Không cần xử lý lại nhiều lần bằng mọi giá, nhưng cần hiểu event có thể bị gộp; count không phải số file.
8. **Không xử lý `OVERFLOW`.** Có nguy cơ bỏ lỡ file; phải rescan khi yêu cầu tính đúng đắn.
9. **Nhìn thấy `ENTRY_MODIFY` rồi coi file đã ghi xong.** Có thể là file đang được ghi; cần protocol hoàn tất.
10. **Giả định watcher đệ quy.** Phải đăng ký directory con nếu cần theo dõi sâu.
11. **Dùng một watched root cho mọi key.** Với nhiều thư mục, cùng relative filename có thể dẫn đến chọn nhầm tệp.
12. **Cố mở file sau `ENTRY_DELETE`.** Entry có thể không còn; cập nhật chỉ mục bằng path/context đã biết.
13. **Không kiểm tra `reset() == false`.** Key không còn valid thì phải loại khỏi map và quyết định re-register.
14. **Chặn watcher loop bằng xử lý dài.** Event bị dồn/gộp/tràn; tách sang worker executor có giới hạn.
15. **Dùng watcher như hệ thống audit tuyệt đối.** OS/provider có thể gộp/mất event; muốn audit cần nguồn thay đổi có log đáng tin riêng.
16. **Không đóng `WatchService`.** Resource và thread đang chờ có thể tồn tại lâu hơn dự kiến; cần chiến lược shutdown.
17. **Suy luận thời gian sự kiện bằng thứ tự tuyệt đối.** Thông báo có thể đến sau thay đổi, giữa lúc state đã biến động tiếp.
18. **Dùng `normalize()` để thay việc bảo vệ path.** Chuẩn hóa cú pháp không xử lý hết symlink/race và quyền truy cập.

## 16. Bài tập thực hành

### Bài A — xem sự khác nhau giữa hai loại poll

Tạo watcher cho một thư mục tạm. Gọi `watcher.poll()` khi chưa tạo file và quan sát rằng có thể trả `null`. Sau khi tạo file và nhận `WatchKey`, gọi `key.pollEvents()` rồi thử gọi lần nữa ngay. Tại sao danh sách lần hai thường rỗng? Sau xử lý, hàm nào cần gọi để tiếp tục theo dõi?

### Bài B — kiểm tra context tương đối

Giả sử `key.watchable()` trả `/tmp/receive` và event context là `data.csv`. Đường dẫn nào đúng để đọc file? Vì sao `Path.of("data.csv")` không tương đương nếu chương trình chạy tại `/home/app`?

### Bài C — nhiều registration

Đăng ký `dirA` và `dirB` trên cùng một `WatchService`. Tạo file cùng tên `data.json` trong cả hai thư mục. Hãy xây `Map<WatchKey, Path>` và in các path sau khi resolve sao cho không nhầm lẫn hai file.

### Bài D — tình huống `OVERFLOW`

Giả sử watcher bỏ lỡ một số `ENTRY_CREATE` vì queue quá tải. Hãy giải thích tại sao `event.count()` không đủ để khôi phục danh sách file đã tạo, và viết các bước quét lại/đối chiếu snapshot.

### Bài E — thiếu tính recursive

Bạn đăng ký `inbox`, sau đó chương trình khác tạo `inbox/newFolder/item.bin`. Vì sao watcher của `inbox` chưa đủ để đảm bảo nhận event tạo `item.bin`? Bạn sẽ đăng ký thêm root nào và cần xử lý race ra sao?

### Bài F — lifecycle và shutdown

Một watcher thread đang chặn trong `take()`. Thread điều phối muốn tắt ứng dụng. Nên quản lý `WatchService.close()`, xử lý `ClosedWatchServiceException` và đóng executor ra sao để không bỏ quên resource?

## 17. Câu hỏi tự kiểm tra

1. `Path.register(watcher, kinds...)` trả kiểu gì, và `WatchKey.watchable()` thường đại diện cho gì?
2. `WatchService.poll()` và `WatchKey.pollEvents()` khác nhau về object trả về và nhiệm vụ như thế nào?
3. `WatchEvent.context()` với `ENTRY_CREATE` trên directory thường là Path absolute hay relative? Relative với đâu?
4. Nếu chương trình giám sát ba thư mục, làm sao xác định Path đầy đủ cho cùng một tên `log.txt` từ ba key khác nhau?
5. Vì sao phải kiểm tra `event.kind() == OVERFLOW` trước khi cast context sang `Path`?
6. `pollEvents()` có xóa key khỏi watch service hay tự `reset` không?
7. `key.reset()` trả `false` mang ý nghĩa gì? Có bắt buộc chứng minh thư mục bị xóa không?
8. `WatchEvent.count()` có đồng nghĩa số file thay đổi không?
9. Nếu file bị tạo rồi xóa trước khi watcher xử lý `ENTRY_CREATE`, có thể mặc định `Files.readAllBytes` thành công không?
10. `WatchService` có bảo đảm quan sát toàn bộ cây directory một cách đệ quy trên mọi provider không?
11. Sự khác nhau giữa `key.cancel()` và `watcher.close()` là gì?
12. `ENTRY_MODIFY` có bảo đảm producer đã đóng file, dữ liệu không còn thay đổi nữa không?
13. Vì sao một watcher nhập dữ liệu nên có chiến lược rescan/snapshot khi `OVERFLOW`?
14. `watcher.take()` có thể chặn; làm sao kết thúc thread đang chờ khi ứng dụng shutdown?
15. Tại sao không dùng event watcher làm cơ chế audit thay thế log giao dịch có thứ tự?

## 18. Tài liệu Java SE 17

- [`WatchService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): `take()`, `poll()`, `poll(timeout, unit)`, vòng đời dịch vụ.
- [`WatchKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html): `pollEvents()`, `reset()`, `cancel()`, `watchable()`, `isValid()`.
- [`WatchEvent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html): `kind()`, `context()`, `count()`.
- [`StandardWatchEventKinds`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE`, `OVERFLOW`.
- [`Path.register`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): đăng ký Path với WatchService.

## 19. Ghi nhớ

**`WatchService` trả `WatchKey`; `WatchKey.pollEvents()` trả danh sách `WatchEvent`.** Với sự kiện thay đổi entry trong thư mục, `event.context()` là tên/đường dẫn **tương đối so với thư mục đã đăng ký**, vì vậy phải ghép với `(Path) key.watchable()` hoặc mapping root tương ứng.

Sau khi tiêu thụ event, gọi **`key.reset()`** và kiểm tra kết quả để tiếp tục theo dõi. Phân biệt `reset()` với `cancel()`, xử lý `OVERFLOW` bằng quét lại trạng thái, không giả định watch là recursive hay ghi nhận đầy đủ mọi thay đổi. Watcher là **cơ chế nhận tín hiệu để kiểm tra filesystem**, không phải bản sao filesystem hay nhật ký kiểm toán tuyệt đối.
