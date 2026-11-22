# Java 7 — WatchService: `ENTRY_CREATE`, `ENTRY_DELETE` và `ENTRY_MODIFY`

## Mục tiêu bài học

Khi muốn một ứng dụng phản ứng với việc **file được tạo, xóa hoặc sửa đổi trong một thư mục**, Java NIO.2 cung cấp `WatchService` và ba loại sự kiện chuẩn:

- `StandardWatchEventKinds.ENTRY_CREATE` — một **directory entry** được tạo hoặc chuyển vào thư mục đang theo dõi.
- `StandardWatchEventKinds.ENTRY_DELETE` — một directory entry bị xóa hoặc chuyển khỏi thư mục đang theo dõi.
- `StandardWatchEventKinds.ENTRY_MODIFY` — một entry trong thư mục đang theo dõi được quan sát là đã sửa đổi.

`WatchService`, `WatchKey`, `WatchEvent` và `StandardWatchEventKinds` có từ **Java 7**, vẫn là API hiện hành trên Java 17+. Bạn dùng chúng để cập nhật danh sách file, thông báo có dữ liệu mới, kích hoạt đồng bộ hoặc kiểm kê, **nhưng không được coi WatchService là nhật ký sự kiện đầy đủ, chính xác một-lần, hoặc transaction log**.

Sau bài học, bạn sẽ:

1. Phân biệt chính xác ba `ENTRY_*` event với `OVERFLOW`.
2. Biết **đăng ký một directory trước khi thay đổi xảy ra**, chọn ba event kinds qua `Path.register(...)`.
3. Hiểu luồng `WatchService` → `WatchKey` → `WatchEvent`, trạng thái key *ready/signalled*, `pollEvents()` và `reset()`.
4. Lấy `event.kind()`, `event.count()`, `event.context()` và ghép `watchedDir.resolve(relativePath)` đúng cách.
5. Nắm nguyên lý sự kiện của **entry trong thư mục được đăng ký**, không mặc nhiên theo dõi mọi thư mục con.
6. Hiểu rằng rename/move có thể biểu hiện dưới dạng create/delete, không có event `ENTRY_RENAME` tiêu chuẩn.
7. Không giả định mỗi lần ghi sẽ có đúng một `ENTRY_MODIFY`, hoặc một create–modify–delete nhanh luôn tạo đủ ba sự kiện.
8. Xử lý `OVERFLOW`, key hết hiệu lực, đóng watcher, timeout và thread interruption.
9. Biết vì sao file có `ENTRY_MODIFY` không nhất thiết đã ghi xong và không thể luôn đọc file sau `ENTRY_DELETE`.
10. Thiết kế watcher chịu được coalescing, event loss, backend khác nhau, network filesystem và file-system races.
11. Chạy sáu chương trình Java 17+ hoàn chỉnh minh họa khai báo event kinds, vòng đời key, quan sát sự kiện, giới hạn một cấp, synthetic event và đóng watcher.
12. Viết test kiểm đúng **hợp đồng API**, tránh đặt assertion không portable cho số lượng/thứ tự/timing của events.

**Phạm vi:** Bài tập trung vào ba sự kiện trong `StandardWatchEventKinds` và cách dùng đúng trong `WatchService`. `OVERFLOW`, vòng đời key và lỗi nền tảng là kiến thức thiết yếu để sử dụng ba event ấy chính xác. Những API được giới thiệu đều **còn sử dụng hiện nay**; các tiện ích Java 9+/11+ trong ví dụ được ghi rõ.

## 1. Tư duy đúng: theo dõi một directory, không theo dõi “một file bất biến”

Giả sử có cây:

```text
workspace/
  inbox/
    first.txt
    reports/
      summary.csv
```

Nếu đăng ký thư mục `inbox` với `WatchService`:

```java
WatchKey key = inbox.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_DELETE,
        StandardWatchEventKinds.ENTRY_MODIFY);
```

đây là **đoạn minh họa**, yêu cầu `inbox` là `Path` của directory và `watcher` là `WatchService` hợp lệ. Khi một entry trực tiếp dưới `inbox` thay đổi, watcher có thể được thông báo.

Ví dụ sự kiện gần giống:

```text
inbox/new.txt     được tạo        -> ENTRY_CREATE, context new.txt
inbox/first.txt   bị xóa         -> ENTRY_DELETE, context first.txt
inbox/first.txt   được sửa       -> ENTRY_MODIFY, context first.txt
inbox/reports     được tạo       -> ENTRY_CREATE, context reports
```

**Không suy ra** rằng đăng ký `inbox` tự theo dõi mọi `inbox/reports/summary.csv`. Theo mô hình chuẩn của `Path.register`, `WatchService` theo dõi **entries trong directory đã đăng ký**. Muốn theo dõi thay đổi trực tiếp **bên trong `reports`**, thường phải **đăng ký chính directory `reports`**.

### 1.1. Sự kiện là thông báo, không phải snapshot của file

`WatchEvent` mô tả rằng một loại thay đổi **đã được quan sát**, thường với context là tên entry tương đối. Sự kiện **không chứa nội dung file**, không cung cấp một transaction ID cho thao tác sửa đổi, và không bảo đảm entry vẫn tồn tại khi code xử lý.

Ví dụ:

```text
10:00:00.000  producer tạo result.txt
10:00:00.003  producer ghi nhiều byte
10:00:00.006  producer xóa result.txt
10:00:00.200  consumer xử lý event
```

Đến khi consumer nhận `ENTRY_CREATE`, file có thể đã bị xóa. Đây không phải lỗi logic của `WatchService`; watcher là công cụ **thông báo thay đổi**, không khóa trạng thái filesystem tại thời điểm event.

### 1.2. “File mới” và “entry mới” khác nhau

`ENTRY_CREATE` có thể xuất hiện khi một **file hoặc directory mới được tạo**, hoặc khi một entry **được rename/move vào** directory đang theo dõi. Nó không bảo đảm file trước đó chưa tồn tại ở nơi khác, không nói file đã hoàn tất và không phải chứng nhận identity lâu dài.

Tương tự, `ENTRY_DELETE` diễn tả entry bị xóa hoặc **move/rename ra ngoài** directory được theo dõi. Nó không bảo đảm dữ liệu bị hủy vĩnh viễn; file có thể được move sang directory khác hoặc còn trong backup.

`ENTRY_MODIFY` chỉ ra entry được quan sát là thay đổi. Nó không tự nói *trường metadata nào*, *bao nhiêu byte* hay *dữ liệu đã được ghi xong hay chưa*.

## 2. Ba event kinds: định nghĩa chính xác

Ba hằng số được định nghĩa trong `java.nio.file.StandardWatchEventKinds`:

| Event kind | Kiểu context | Khi một directory được đăng ký cho event | `count()` |
| --- | --- | --- | --- |
| `ENTRY_CREATE` | `Path` | Quan sát entry được **tạo hoặc rename/move vào** directory | **Luôn 1** cho một WatchEvent loại này |
| `ENTRY_DELETE` | `Path` | Quan sát entry bị **xóa hoặc rename/move ra khỏi** directory | **Luôn 1** cho một WatchEvent loại này |
| `ENTRY_MODIFY` | `Path` | Quan sát entry của directory được **sửa đổi** | Có thể **1 hoặc lớn hơn** |

Trong thực tế, **số event objects và thời điểm nhận** khác nhau theo hệ thống. Với `ENTRY_MODIFY`, implementation có thể gộp nhiều tín hiệu sửa đổi cùng loại/context, nên `count()` có thể lớn hơn 1. Tại một số provider, cùng một thao tác save có thể phát ra nhiều modify events; ở provider khác có thể chỉ một.

**Không tự suy ra** rằng `ENTRY_CREATE` hoặc `ENTRY_DELETE` “chỉ xảy ra một lần mỗi file trong đời” từ quy tắc `count()==1`. Quy tắc này nói về **giá trị count của từng WatchEvent object**. Một đường dẫn có thể bị tạo–xóa–tạo nhiều lần qua thời gian, và các thông báo có thể bị mất nếu hệ thống quá tải.

### 2.1. `ENTRY_CREATE` — khi có entry mới trong directory

Các tình huống thường gặp:

- `Files.createFile(dir.resolve("new.txt"))`.
- `Files.createDirectory(dir.resolve("new-dir"))`.
- Một process move/rename entry **vào** directory.
- Một editor ghi một file tạm rồi rename vào directory.

Những điều **không được hứa**:

- File đã được ghi xong, được đóng hoặc có kích thước cuối cùng.
- Sẽ không còn `ENTRY_MODIFY` tiếp theo.
- Một quá trình ghi rất nhanh hoặc entry tồn tại rất ngắn luôn được phát hiện.
- Mỗi sự kiện được nhận theo một thứ tự thống nhất ở mọi OS/filesystem.

**Ứng dụng:** Cập nhật UI file list, đánh dấu entry cần kiểm tra, hoặc bắt đầu quy trình xử lý có bước chờ file sẵn sàng.

### 2.2. `ENTRY_DELETE` — khi entry rời directory

Các tình huống:

- `Files.delete(dir.resolve("old.txt"))`.
- Một entry được rename ra ngoài directory đang theo dõi.
- Một chương trình khác xóa/move file.

**Không được suy ra**:

- Dữ liệu đã bị xóa khỏi mọi backup/snapshot.
- File không thể được tạo lại cùng tên ngay sau đó.
- Consumer có thể đọc nội dung file đã bị xóa.
- Có event rename riêng kèm oldPath/newPath.

**Ứng dụng:** Xóa entry khỏi cache danh sách, đánh dấu index cần xác minh lại, thu hồi trạng thái theo path — nhưng nên có bước reconciliation khi correctness quan trọng.

### 2.3. `ENTRY_MODIFY` — khi một entry thay đổi

Những thao tác có thể dẫn đến thông báo tùy provider:

- Ghi, append hoặc truncate nội dung file.
- Thay đổi một số thuộc tính filesystem nếu provider coi là modification event.
- Các bước save/phối hợp rename của editor hoặc công cụ đồng bộ.

**Ngữ nghĩa rộng, không phải “đã hoàn tất ghi”:**

- Một lần ghi có thể tạo **nhiều** modify notifications.
- Một event có thể có `count() > 1` vì lặp/gộp.
- Event có thể được consumer nhận trong khi producer **vẫn đang giữ file mở**.
- Không có payload cho biết phần byte nào đã đổi.
- Một phần thay đổi metadata có thể cho hành vi khác giữa OS/providers.

**Ứng dụng:** Đánh dấu một file “dirty”, debounce/throttle xử lý, đợi producer xuất bản file theo protocol được thống nhất hoặc kiểm tra lại trạng thái hiện hành.

## 3. `OVERFLOW` không phải loại sửa file thứ tư

`StandardWatchEventKinds.OVERFLOW` là một **event đặc biệt**: một số thông báo có thể đã bị loại bỏ hoặc không còn được giữ đủ trong hàng đợi.

| Thuộc tính | Ba `ENTRY_*` | `OVERFLOW` |
| --- | --- | --- |
| Ý nghĩa | Tạo, xóa hoặc sửa entry | Có thể mất/bỏ bớt events |
| `Kind` generic | `WatchEvent.Kind<Path>` | `WatchEvent.Kind<Object>` |
| Context | `Path` tương đối đến entry | Implementation-specific, **có thể null** |
| Count | Create/Delete = 1, Modify ≥1 | Có thể >1 |
| Cần register riêng? | Có, đăng ký các kinds muốn nhận | **Không cần register OVERFLOW** để nhận |
| Xử lý thường gặp | Xác minh entry và cập nhật state | **Rescan/reconcile** directory do app quản lý |

Ví dụ xử lý:

```java
for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        scheduleFullRescan(watchedDir);
        continue;
    }
    Path child = (Path) event.context();
    Path fullPath = watchedDir.resolve(child);
    // Xác minh trạng thái hiện tại trước khi hành động.
}
```

Đây là **mảnh minh họa**, cần định nghĩa `key`, `watchedDir` và phương thức `scheduleFullRescan` theo hệ thống của bạn. Nó minh họa **check OVERFLOW trước khi cast context**: không được cast mọi `WatchEvent<?>.context()` thành `Path` vì `OVERFLOW` có thể có context null.

**Quy tắc phục hồi:** `OVERFLOW` không cho biết chính xác file nào bị mất event, vì vậy không thể chỉ xử lý một tên file cụ thể rồi coi đã đồng bộ. Cần quét lại danh sách/trạng thái của directory và đối chiếu với trạng thái nội bộ.

## 4. Đăng ký directory với WatchService

Chu trình khởi tạo căn bản:

```java
Path dir = Path.of("watched");
WatchService watcher = dir.getFileSystem().newWatchService();
WatchKey key = dir.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_DELETE,
        StandardWatchEventKinds.ENTRY_MODIFY);
```

Đây là **đoạn minh họa**: directory `watched` phải đã tồn tại và có thể đăng ký; cần import `Path`, `WatchService`, `WatchKey`, `StandardWatchEventKinds` và xử lý `IOException`. `Path.of` được giới thiệu từ **Java 11**; nếu phải biên dịch đúng Java 7 có thể dùng `Paths.get(...)`.

### 4.1. Các bước có ý nghĩa gì?

1. `Path dir` xác định **directory** bạn có quyền theo dõi.
2. `dir.getFileSystem().newWatchService()` tạo dịch vụ theo dõi thuộc filesystem/provider ấy.
3. `dir.register(watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY)` yêu cầu provider theo dõi các entry events được liệt kê.
4. `register` trả `WatchKey` đại diện cho registration.
5. Consumer lấy **WatchKey được signal**, không lấy trực tiếp từng WatchEvent từ `WatchService`.
6. `key.pollEvents()` trả các events đã tích lũy cho key ấy.
7. Sau khi xử lý events, **`key.reset()`** cho phép key quay lại trạng thái ready/được queue lại.

### 4.2. Vì sao phải đăng ký **trước** khi producer tạo file?

`WatchService` không phải máy đọc lại lịch sử quá khứ. Nếu bạn:

```java
Files.createFile(dir.resolve("already.txt"));
dir.register(watcher, StandardWatchEventKinds.ENTRY_CREATE);
```

thì **không có bảo đảm** watcher sẽ phát event cho file đã tồn tại trước lúc đăng ký.

Nếu ứng dụng cần biết cả các file đã có lẫn thay đổi trong tương lai:

- Lấy baseline bằng cách **liệt kê/truy vấn trạng thái directory** theo nhu cầu.
- Đăng ký watcher đủ sớm.
- Xác định cách **reconcile** khoảng thời gian giữa snapshot và registration để tránh bỏ sót hoặc xử lý lặp.
- Thiết kế logic **idempotent** vì startup/rescan có thể nhìn cùng một entry hơn một lần.

Không có thao tác Java NIO.2 duy nhất tự tạo một **snapshot nguyên tử đồng thời đăng ký watcher** cho mọi filesystem.

### 4.3. Đăng ký directory khác đăng ký regular file

`Path.register` của default provider được thiết kế để theo dõi **entries của directory hiện hữu**. Đừng giả định truyền `Path` tới một regular file cho `register` sẽ biến nó thành “watch riêng nội dung file”. Provider có thể từ chối bằng `NotDirectoryException` hoặc `IOException` phù hợp.

Nếu chỉ quan tâm một file `important.txt`, hãy đăng ký **directory chứa nó**, rồi filter các `event.context()` tương ứng.

### 4.4. Event kinds không có rename riêng

`StandardWatchEventKinds` có ba `ENTRY_*` và `OVERFLOW`. Không có `ENTRY_RENAME` tiêu chuẩn trong Java NIO.2. Khi ứng dụng cần biết một thao tác rename gồm oldPath và newPath, đôi khi chỉ thấy delete/create ở hai directory; không có correlation ID chuẩn đảm bảo hai sự kiện thuộc cùng một operation.

Muốn theo dõi move/rename **chính xác theo nghiệp vụ**, cần protocol hoặc metadata/versioning bên ngoài watcher, không suy từ timestamp/khoảng cách hai events.

## 5. Chương trình A — Liệt kê các event kinds và generic context

Bắt đầu bằng ví dụ **không phụ thuộc file-system notifications**, nên stdout xác định trên Java 17+.

Lưu **`WatchKindsDemo.java`**:

```java
import java.nio.file.*;

public final class WatchKindsDemo {
    public static void main(String[] args) {
        WatchEvent.Kind<?>[] kinds = {
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_DELETE,
            StandardWatchEventKinds.ENTRY_MODIFY,
            StandardWatchEventKinds.OVERFLOW
        };

        for (WatchEvent.Kind<?> kind : kinds) {
            System.out.println(
                    kind.name() + " type=" + kind.type().getSimpleName());
        }

        System.out.println("allEntryKindsArePath=" + (
            StandardWatchEventKinds.ENTRY_CREATE.type() == Path.class &&
            StandardWatchEventKinds.ENTRY_DELETE.type() == Path.class &&
            StandardWatchEventKinds.ENTRY_MODIFY.type() == Path.class));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 WatchKindsDemo.java
java WatchKindsDemo
```

**Stdout đã kiểm chứng:**

```text
ENTRY_CREATE type=Path
ENTRY_DELETE type=Path
ENTRY_MODIFY type=Path
OVERFLOW type=Object
allEntryKindsArePath=true
```

### 5.1. Kiến thức quan trọng từ generics

Ba hằng số `ENTRY_*` có kiểu `WatchEvent.Kind<Path>`. `OVERFLOW` có kiểu `WatchEvent.Kind<Object>`. Bởi vậy, trong event loop thực tế, dùng `WatchEvent<?>` để duyệt mọi events và **kiểm tra kind trước khi xử lý context**.

Ví dụ:

```java
WatchEvent.Kind<?> kind = event.kind();

if (kind == StandardWatchEventKinds.OVERFLOW) {
    // Rescan; context có thể null.
} else if (kind == StandardWatchEventKinds.ENTRY_CREATE) {
    Path relative = (Path) event.context();
    // Entry mới trong directory đã đăng ký.
}
```

Đây là mảnh minh họa, `event` cần là `WatchEvent<?>` và có import tương ứng. Cast `(Path)` là hợp lệ cho event kinds `ENTRY_*` theo contract, nhưng application vẫn phải xử lý tình huống provider có các kinds mở rộng, exception hoặc trạng thái file đã thay đổi.

## 6. WatchKey: ready, signalled, queued và reset

`WatchKey` không phải “event duy nhất”; nó là **token đại diện một registration** với WatchService.

Quá trình thường gặp:

```text
watch key created → READY
        |
        | provider quan sát một thay đổi đã đăng ký
        v
SIGNALLED + queued vào WatchService
        |
        | consumer gọi take()/poll()
        v
consumer có WatchKey, đọc key.pollEvents()
        |
        | consumer đã xử lý xong
        v
key.reset()
        |
        +--> key hợp lệ và không còn events: READY
        +--> key hợp lệ và còn events: có thể được queue lại
        +--> key invalid: reset() trả false
```

Một key đã **signalled** có thể tích lũy thêm events nhưng **không phải được queue thêm một bản key cho từng event**. Vì vậy, nếu chỉ gọi `watcher.take()` rồi `key.pollEvents()` mà **quên `key.reset()`**, ứng dụng có thể xử lý một đợt rồi không nhận key trở lại như mong đợi.

### 6.1. API cơ bản của WatchService

| API | Hành vi |
| --- | --- |
| `watcher.poll()` | Lấy key ngay nếu có; không chờ, có thể trả `null` |
| `watcher.poll(timeout, TimeUnit.MILLISECONDS)` | Chờ tối đa khoảng timeout được yêu cầu, có thể trả `null` |
| `watcher.take()` | Chờ đến khi có key, bị interrupt hoặc watcher bị đóng |
| `watcher.close()` | Đóng dịch vụ, làm các keys không hợp lệ; đánh thức consumer đang chờ bằng `ClosedWatchServiceException` |

Không dùng `Thread.sleep(1000)` rồi poll như cách đồng bộ đáng tin; nếu cần chờ có giới hạn, `poll(timeout, unit)` thể hiện nhu cầu rõ. Với tác vụ chạy liên tục, `take()` hợp lý nhưng phải có cách dừng watcher, xử lý interruption và đóng resource.

### 6.2. API cơ bản của WatchKey

| API | Vai trò |
| --- | --- |
| `key.pollEvents()` | Lấy và loại khỏi queue những events đang được tích lũy |
| `key.reset()` | Chuyển key về ready hoặc queue lại; trả boolean validity |
| `key.isValid()` | Kiểm tra registration còn hợp lệ ở thời điểm hỏi |
| `key.cancel()` | Hủy registration |
| `key.watchable()` | Lấy `Watchable` đã đăng ký, thường là directory `Path` |

`key.watchable()` có thể vẫn trả đối tượng `Path` ban đầu **ngay cả sau khi key invalid**. Nếu directory đã được move/rename, một `Path` lấy từ `watchable()` không tự chứng minh location hiện tại còn như ban đầu.

### 6.3. Reset sau khi xử lý xong, không reset tùy tiện quá sớm

Khi có nhiều threads cùng dùng watcher, `WatchService` được thiết kế hỗ trợ multi-consumer, nhưng ứng dụng nên bảo đảm **một người xử lý một key tại một thời điểm**, và chỉ reset sau khi các events của key đã xử lý xong. Nếu reset trước khi xong, cùng một registration có thể được xử lý xen kẽ, gây race trong cache/index ứng dụng.

Với pipeline nặng, có thể queue công việc sang executor, nhưng phải thiết kế rõ việc reset, thứ tự, backpressure và xử lý exception.

## 7. Chương trình B — Vòng đời WatchKey và đóng dịch vụ

Lưu **`RegistrationLifecycleDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.*;

public final class RegistrationLifecycleDemo {
    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("watch-registration-");

        try (WatchService watcher =
                     root.getFileSystem().newWatchService()) {
            WatchKey key = root.register(
                    watcher,
                    StandardWatchEventKinds.ENTRY_CREATE,
                    StandardWatchEventKinds.ENTRY_DELETE,
                    StandardWatchEventKinds.ENTRY_MODIFY);

            System.out.println("keyValidInitially=" + key.isValid());
            System.out.println("watchableIsRoot=" +
                    key.watchable().equals(root));
            System.out.println("pollInitiallyNull=" +
                    (watcher.poll() == null));
            System.out.println("keyResetValid=" + key.reset());

            key.cancel();
            System.out.println("keyInvalidAfterCancel=" +
                    !key.isValid());
            System.out.println("resetInvalidKey=" + key.reset());

            watcher.close();
            try {
                watcher.poll();
                System.out.println("closedPollThrows=false");
            } catch (ClosedWatchServiceException expected) {
                System.out.println("closedPollThrows=true");
            }
        } finally {
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 RegistrationLifecycleDemo.java
java RegistrationLifecycleDemo
```

**Stdout đã kiểm chứng:**

```text
keyValidInitially=true
watchableIsRoot=true
pollInitiallyNull=true
keyResetValid=true
keyInvalidAfterCancel=true
resetInvalidKey=false
closedPollThrows=true
```

### 7.1. Giải thích từng bước

- `newWatchService` tạo watcher cho filesystem của `root`.
- `root.register` trả key, ban đầu `isValid()==true`.
- `key.watchable()` trả chính directory đã đăng ký trong bài thử.
- Chưa làm thao tác với entries khi gọi `poll()`, nên trong môi trường kiểm thử queue đang trống và trả `null`.
- `reset()` trên key hợp lệ ở trạng thái ready giữ key hợp lệ và trả true.
- `key.cancel()` hủy registration; `isValid()` false.
- `reset()` của key đã invalid không làm nó hợp lệ trở lại, trả false.
- `watcher.close()` đóng watcher. `watcher.poll()` sau đó ném `ClosedWatchServiceException`.
- Vì đã dùng try-with-resources, watcher được đóng lại khi ra khỏi block; gọi `close` lại theo API là an toàn. **Trong production thường chỉ cần try-with-resources/đường shutdown rõ; lời gọi close tường minh trong ví dụ dùng để minh họa exception.**

Đây là test vòng đời key trên directory tạm, không dựa vào event notification timing.

## 8. `WatchEvent`: `kind`, `context` và `count`

Với một event thông thường:

```java
WatchEvent.Kind<?> kind = event.kind();
Object context = event.context();
int count = event.count();
```

Cần chú ý:

- `kind()` cho biết `ENTRY_CREATE`/`ENTRY_DELETE`/`ENTRY_MODIFY`/`OVERFLOW` hoặc kind mở rộng do provider định nghĩa.
- `context()` với ba kinds chuẩn là **`Path` tương đối** từ directory đã đăng ký tới entry bị tác động, không phải absolute path hoàn chỉnh.
- `count()` cho biết số lần sự kiện cùng loại/context được đếm theo mô hình coalescing. `ENTRY_CREATE` và `ENTRY_DELETE` có `count=1`; `ENTRY_MODIFY` có thể lớn hơn 1.
- `OVERFLOW` có context implementation-specific, có thể null. Phải kiểm tra riêng trước khi cast.

### 8.1. Ghép đường dẫn đúng

Giả sử directory `watchedDir` là:

```text
/tmp/inbox/
```

và event context là:

```text
new.txt
```

đường dẫn tới entry tại thời điểm bạn xử lý có thể được xây bằng:

```java
Path relative = (Path) event.context();
Path absolute = watchedDir.resolve(relative);
```

Đây là **mảnh minh họa**; `event` phải là một trong ba `ENTRY_*` có context `Path` và `watchedDir` là directory tương ứng với **WatchKey đã được trả về**, không phải một directory lấy từ nơi khác.

**Không dùng `Paths.get(event.context().toString())` rồi nghĩ đó là absolute path**: context tương đối có ý nghĩa so với directory được watch.

### 8.2. Một WatchService có thể quản lý nhiều directories

Khi đăng ký nhiều directories vào cùng watcher, cần biết **key nào thuộc directory nào**:

```java
Map<WatchKey, Path> directories = new HashMap<>();
WatchKey a = firstDir.register(watcher, ENTRY_CREATE);
WatchKey b = secondDir.register(watcher, ENTRY_CREATE);
directories.put(a, firstDir);
directories.put(b, secondDir);
```

Đây là **mảnh minh họa**, cần import `Map`, `HashMap` và static import `ENTRY_CREATE` hoặc dùng tên fully qualified. Khi xử lý `WatchKey`, tra `directories.get(key)` rồi resolve context, thay vì luôn resolve mọi event theo một root cố định.

`key.watchable()` thường là directory `Path` đã đăng ký, nhưng map tường minh giúp bạn quản lý resource, danh sách registrations và policy khi key bị invalid.

### 8.3. Không truy cập file đã biến mất mà không xử lý lỗi

`ENTRY_DELETE` có thể đến sau khi entry đã bị xóa. Gọi:

```java
Files.readString(absolute);
```

sẽ có thể ném `NoSuchFileException`. Đây là **mảnh minh họa**; `Files.readString` xuất hiện từ Java 11. Khi nhận `ENTRY_DELETE`, nhiều ứng dụng chỉ cần cập nhật cache/index và đối chiếu state thay vì tìm cách đọc nội dung đã mất.

Với `ENTRY_CREATE` và `ENTRY_MODIFY`, file cũng có thể đã biến mất hoặc còn đang được ghi; luôn có đường xử lý `IOException` và race.

## 9. Chương trình C — Theo dõi create, modify, delete một file tạm

Đây là demo **đụng thật đến filesystem**. Nó đăng ký watcher **trước** các thao tác, tạo file, append, xóa và dùng polling có **thời hạn 3 giây** để thu events. Số lượng/thứ tự events không được giả định giống nhau trên mọi provider.

Lưu tệp **`EntryEventsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;

import static java.nio.file.StandardWatchEventKinds.*;

public final class EntryEventsDemo {
    public static void main(String[] args)
            throws IOException, InterruptedException {
        Path root = Files.createTempDirectory("watch-events-");
        Path file = root.resolve("data.txt");

        int creates = 0;
        int deletes = 0;
        int modifies = 0;
        int overflows = 0;
        int modifyEventCount = 0;

        try (WatchService watcher =
                     root.getFileSystem().newWatchService()) {
            WatchKey registration = root.register(
                    watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);

            Files.writeString(file, "a", StandardCharsets.UTF_8);
            Files.writeString(file, "b", StandardCharsets.UTF_8,
                    StandardOpenOption.APPEND);
            Files.delete(file);

            long deadline =
                    System.nanoTime() + TimeUnit.SECONDS.toNanos(3);

            while (System.nanoTime() < deadline) {
                WatchKey key =
                        watcher.poll(150, TimeUnit.MILLISECONDS);
                if (key == null) continue;

                for (WatchEvent<?> event : key.pollEvents()) {
                    if (event.kind() == OVERFLOW) {
                        overflows++;
                        continue;
                    }

                    Object context = event.context();
                    if (!(context instanceof Path)) continue;
                    Path relative = (Path) context;
                    Path absolute =
                            ((Path) key.watchable()).resolve(relative);

                    if (!absolute.equals(file)) continue;

                    if (event.kind() == ENTRY_CREATE) {
                        creates++;
                    } else if (event.kind() == ENTRY_DELETE) {
                        deletes++;
                    } else if (event.kind() == ENTRY_MODIFY) {
                        modifies++;
                        modifyEventCount += event.count();
                    }
                }

                if (!key.reset()) break;
                if (creates > 0 && deletes > 0 && modifies > 0) break;
            }

            System.out.println("actionsPerformed=true");
            System.out.println("createObserved=" + (creates > 0));
            System.out.println("deleteObserved=" + (deletes > 0));
            System.out.println("modifyObserved=" + (modifies > 0));
            System.out.println("modifyEventCountAtLeastOne=" +
                    (modifyEventCount >= 1));
            System.out.println("overflowObserved=" + (overflows > 0));
            System.out.println("registrationStillValid=" +
                    registration.isValid());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 EntryEventsDemo.java
java EntryEventsDemo
```

**Stdout đã quan sát trên Windows/JDK trong hai lần chạy thử:**

```text
actionsPerformed=true
createObserved=true
deleteObserved=true
modifyObserved=true
modifyEventCountAtLeastOne=true
overflowObserved=false
registrationStillValid=true
```

**Quan trọng:** Các dòng `createObserved`, `deleteObserved`, `modifyObserved` và `overflowObserved` là **kết quả quan sát trên môi trường thử**, không phải một bản cam kết stdout cho mọi OS, filesystem, timing, volume hoặc network mount. Những event xảy ra rất nhanh có thể bị coalesce hoặc bỏ lỡ. Nếu `modifyObserved=false` trên môi trường khác thì trước hết kiểm tra provider, lịch xử lý và thời hạn polling; đừng kết luận `WatchService` không có API `ENTRY_MODIFY`.

### 9.1. Tại sao `Files.writeString` ở ví dụ này hợp lệ?

`Files.writeString` là tiện ích có từ **Java 11**, được phép vì mã biên dịch với `--release 17`. Bản chất `ENTRY_*`, `WatchService`, `WatchKey`, `WatchEvent` là API **Java 7** và vẫn hiện hành.

Nếu bắt buộc biên dịch đúng Java 7, có thể dùng `Files.write` cùng byte array/`StandardOpenOption.APPEND` hoặc stream API tương ứng. Mục tiêu bài học không thay đổi.

### 9.2. Tại sao chương trình không in tất cả events theo từng dòng?

Cùng một thao tác save hoặc append có thể phát nhiều `ENTRY_MODIFY`, số events được gộp có thể khác, và thứ tự/độ trễ phụ thuộc provider. Chương trình tổng hợp boolean để cho thấy **những kind nào đã được quan sát** trong cửa sổ thời gian test, thay vì trình bày một thứ tự tuyệt đối “create → modify → delete” mà Java API không hứa trên mọi nền tảng.

### 9.3. `WatchKey.reset()` là bắt buộc trong loop thực tế

Bên trong while:

1. `poll` lấy một key đã được signal.
2. `pollEvents` lấy các events hiện có của key.
3. Code nhận diện `OVERFLOW` trước, rồi xử lý `ENTRY_*` theo context.
4. Code gọi `key.reset()`.
5. Nếu reset trả false, key đã invalid và loop dừng.

Nếu bỏ bước 4, key có thể không được queue lại cho các changes tiếp theo. Nếu xử lý nhiều keys, không nhất thiết phải dừng toàn bộ watcher khi **một** key invalid; hãy loại key ấy khỏi map và tiếp tục các keys còn hợp lệ.

### 9.4. Phần nào cần cải thiện để dùng production?

Ví dụ cố ý chỉ có một directory và một file để đọc dễ. Trong sản phẩm:

- Có vòng lặp sống dài đến khi shutdown.
- Có map `WatchKey → Path` cho nhiều directories.
- Có chính sách xử lý `OVERFLOW` bằng rescan.
- Có cách dừng bằng interruption/close.
- Có log lỗi/metrics và backpressure.
- Có state reconciliation và xử lý file chưa ổn định.
- Có giới hạn path/authorization trước khi mở nội dung.
- Có handling khi watcher không hỗ trợ trên provider hoặc mất quyền truy cập.
- Có logic tiếp tục khi một key invalid nhưng các keys khác vẫn còn.

**Đừng dùng code demo để chứng minh event không thể bị mất.**

## 10. Đăng ký một cấp: WatchService không tự đệ quy

Với cây:

```text
root/
  sub/
    inside.txt
```

đăng ký `root` không đồng nghĩa tự đăng ký `root/sub`. Thay đổi của một **file nằm sâu trong `sub`** cần registration của `sub` nếu muốn nhận các `ENTRY_*` cho chính file đó.

### 10.1. Chương trình D — `OneLevelScopeDemo.java`

Ví dụ tạo `sub` trước khi đăng ký root. Ban đầu chỉ watch root, sau đó tạo `inside.txt` bên trong `sub`. Tiếp theo đăng ký chính `sub`, tạo `watched.txt` và quan sát event của nó.

```java
import java.io.IOException;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;

import static java.nio.file.StandardWatchEventKinds.*;

public final class OneLevelScopeDemo {
    private static boolean watchCreate(
            WatchService watcher, Path expected, long milliseconds)
            throws InterruptedException {
        long deadline = System.nanoTime() +
                TimeUnit.MILLISECONDS.toNanos(milliseconds);
        boolean found = false;

        while (System.nanoTime() < deadline) {
            WatchKey key =
                    watcher.poll(100, TimeUnit.MILLISECONDS);
            if (key == null) continue;

            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() != ENTRY_CREATE ||
                        !(event.context() instanceof Path)) continue;

                Path absolute = ((Path) key.watchable())
                        .resolve((Path) event.context());
                if (absolute.equals(expected)) {
                    found = true;
                }
            }

            if (!key.reset()) break;
        }
        return found;
    }

    public static void main(String[] args)
            throws IOException, InterruptedException {
        Path root = Files.createTempDirectory("watch-scope-");
        Path sub = root.resolve("sub");
        Path nested = sub.resolve("inside.txt");
        Path registered = sub.resolve("watched.txt");

        try {
            Files.createDirectory(sub);
            try (WatchService watcher =
                         root.getFileSystem().newWatchService()) {
                root.register(watcher, ENTRY_CREATE);

                Files.createFile(nested);
                System.out.println("nestedDetectedFromRoot=" +
                        watchCreate(watcher, nested, 400));

                sub.register(watcher, ENTRY_CREATE);
                Files.createFile(registered);
                System.out.println("nestedDetectedFromSub=" +
                        watchCreate(watcher, registered, 1000));
            }
        } finally {
            Files.deleteIfExists(registered);
            Files.deleteIfExists(nested);
            Files.deleteIfExists(sub);
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 OneLevelScopeDemo.java
java OneLevelScopeDemo
```

**Stdout trên Windows/JDK đã thử:**

```text
nestedDetectedFromRoot=false
nestedDetectedFromSub=true
```

Đây là kết quả quan sát trong các cửa sổ polling của test. `nestedDetectedFromRoot=false` cũng thể hiện **nguyên tắc không tự đăng ký recursively** của API chuẩn. `nestedDetectedFromSub=true` cho thấy provider Windows kiểm thử đã báo event khi `sub` được đăng ký trực tiếp.

### 10.2. Muốn watch cả cây thì phải làm gì?

Một chiến lược phổ biến:

1. Liệt kê các directories dưới root thuộc phạm vi ứng dụng, ví dụ qua `Files.walkFileTree`.
2. Đăng ký **mỗi directory** cần theo dõi với watcher.
3. Khi nhận `ENTRY_CREATE` cho một entry mới mà thực tế hiện là directory, đăng ký directory ấy; nếu subtree đã được producer tạo nhanh, cần xem xét scan thêm directories bên trong.
4. Nếu một directory bị xóa/move, quản lý keys liên quan và cập nhật map.
5. Sau `OVERFLOW`, rescan/reconcile cả vùng có thể bị ảnh hưởng.
6. Đánh giá races giữa *scan* và *register*, giữa *create* và *register*, giữa việc rename/move và xử lý.
7. Không tự follow symlinks ra ngoài root nếu chưa có policy rõ.
8. Giới hạn tổng số directories/keys/CPU, vì tree rất lớn có thể tiêu thụ tài nguyên.

**Không có một flag chuẩn `recursive=true` cho `Path.register(watcher, ENTRY_*)` trong Java 7/17**. Một số providers có modifiers implementation-specific, nhưng không nên dựa vào API nội bộ hoặc code platform-specific khi bài học cần kiến thức portable, hiện hành.

## 11. `WatchEvent.count()` và coalescing

Giả sử một chương trình liên tục cập nhật cùng một file:

```text
append #1
append #2
append #3
append #4
```

`WatchService` có thể báo một hoặc nhiều `ENTRY_MODIFY` events. Một `WatchEvent< Path >` có thể có `count() == 4` nếu implementation đã gộp những lần lặp thích hợp, nhưng đây **chỉ là ví dụ minh họa**, không phải kết quả bắt buộc cho bốn lần append.

### 11.1. Cách đọc `count`

- Với `ENTRY_CREATE` và `ENTRY_DELETE`, Java API quy định `count` của **mỗi event** là **1**.
- Với `ENTRY_MODIFY`, `count` có thể **1 hoặc lớn hơn**.
- Với `OVERFLOW`, `count` cũng có thể lớn hơn 1.
- `count > 1` không nhất thiết cho bạn số lần *save logic* của ứng dụng, số byte đã thay đổi hoặc số OS system calls.

Không viết logic:

```java
for (int i = 0; i < event.count(); i++) {
    processWholeFileAgain(path);
}
```

như một quy tắc không thể sai. Với `ENTRY_MODIFY`, thường **xử lý trạng thái hiện tại** của file theo cơ chế idempotent, debounce hoặc versioning, không tái chạy toàn bộ nghiệp vụ số lần đúng bằng count.

### 11.2. Một modify event không xác nhận producer đã đóng file

Java API nêu rõ khi `ENTRY_MODIFY` được báo, **không có bảo đảm chương trình ghi file đã hoàn tất**. Nếu consumer mở đọc ngay, có thể đọc một phần, bị khóa file hoặc thấy file đổi tiếp.

Các hướng xử lý tùy sản phẩm:

- Producer ghi vào tên tạm rồi move/rename sang tên final theo protocol publish rõ.
- Consumer nhận event rồi đối chiếu trạng thái hiện tại, debounce và xác nhận file đã sẵn sàng.
- Consumer đọc stream với xử lý retry có giới hạn khi lỗi tạm.
- Dùng checksum, marker, manifest hoặc version ID do producer tạo nếu cần integrity.
- Dùng database/queue/message protocol thay vì chỉ WatchService khi event delivery phải đáng tin như một business transaction.

**Không dùng thời gian “ngủ 500 ms” như bằng chứng chắc chắn file đã hoàn tất** trên mọi hệ thống. Delay là một heuristic, không phải protocol.

## 12. Chương trình E — Minh họa synthetic events để học kiểu và count

Để kiểm tra cách xử lý `event.kind()`, `event.context()` và `event.count()` mà **không phụ thuộc OS notifications**, ví dụ sau tự tạo các `WatchEvent<Path>` giả lập. Nó **không chứng minh filesystem thực** phát một modify event count=3; nó chỉ dạy cách đọc cấu trúc event hợp lệ.

Lưu **`EventInterpretationDemo.java`**:

```java
import java.nio.file.*;
import java.util.List;

public final class EventInterpretationDemo {
    private static final class Sample implements WatchEvent<Path> {
        private final Kind<Path> kind;
        private final Path name;
        private final int count;

        Sample(Kind<Path> kind, Path name, int count) {
            this.kind = kind;
            this.name = name;
            this.count = count;
        }

        public Kind<Path> kind() {
            return kind;
        }

        public int count() {
            return count;
        }

        public Path context() {
            return name;
        }
    }

    public static void main(String[] args) {
        Path name = Path.of("sample.txt");
        List<WatchEvent<Path>> events = List.of(
            new Sample(StandardWatchEventKinds.ENTRY_CREATE, name, 1),
            new Sample(StandardWatchEventKinds.ENTRY_MODIFY, name, 3),
            new Sample(StandardWatchEventKinds.ENTRY_DELETE, name, 1));

        for (WatchEvent<Path> event : events) {
            System.out.println(
                    event.kind().name() +
                    " name=" + event.context() +
                    " count=" + event.count());
        }

        System.out.println("sampleEventsAreSynthetic=true");
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 EventInterpretationDemo.java
java EventInterpretationDemo
```

**Stdout chính xác:**

```text
ENTRY_CREATE name=sample.txt count=1
ENTRY_MODIFY name=sample.txt count=3
ENTRY_DELETE name=sample.txt count=1
sampleEventsAreSynthetic=true
```

### 12.1. Ý nghĩa và giới hạn

- `Sample` triển khai `WatchEvent<Path>`, mô tả kind, context và count theo dữ liệu test.
- `Path.of` có từ Java 11 và `List.of` có từ Java 9; ví dụ được biên dịch trên Java 17+. **`WatchEvent` là API Java 7**.
- Create/Delete count=1, modify count=3 minh họa hợp đồng đếm; đó là giá trị **do test tự tạo**, không phải event được OS phát.
- Bạn có thể dùng synthetic events để unit-test logic mapping, filtering, debounce và xử lý context.
- Cần thêm integration tests với WatchService thật trên OS/provider cần hỗ trợ để xác minh hoạt động thực tế.

Không trộn stdout của synthetic test vào bằng chứng “Windows đã phát modify count=3”. **Đây là hai loại test khác nhau.**

## 13. `ENTRY_CREATE` và `ENTRY_DELETE` trong rename/move

Hai directory:

```text
root/
  incoming/
    task.dat
  processed/
```

Nếu `task.dat` được move/rename **từ incoming sang processed**, provider có thể báo:

```text
incoming/: ENTRY_DELETE task.dat
processed/: ENTRY_CREATE task.dat
```

Kết quả này đặc biệt hữu ích với các hệ thống dùng **atomic-publish pattern**: producer tạo file tạm, ghi hoàn tất rồi move sang một directory hoặc tên mà consumer theo dõi.

Nhưng **không được suy ra**:

- Hai notifications nhất định cùng đến.
- Chúng luôn đến đúng thứ tự thực tế.
- Mọi filesystem hỗ trợ một move atomic qua hai directories/file stores.
- `ENTRY_DELETE` của tên cũ và `ENTRY_CREATE` của tên mới có một transaction ID chuẩn.
- Chỉ vì vừa nhận `ENTRY_CREATE` thì file đã được “publish complete” theo protocol, trừ khi producer và consumer **đã quy ước** rằng chỉ move tới final name khi ghi và kiểm tra xong.

### 13.1. Save của editor có thể là “replace”, không chỉ modify

Một editor có thể:

1. Ghi nội dung mới vào temp file.
2. Flush/close.
3. Rename/move temp file để thay bản cũ.
4. Xóa entry tạm hoặc bản backup.

Trong watcher, hệ quả có thể là chuỗi `ENTRY_CREATE`/`ENTRY_DELETE`/`ENTRY_MODIFY` **khác với suy nghĩ đơn giản “bấm Save = đúng một modify event”**. Một file watcher chỉ phát hiện modify mà bỏ qua create/delete sẽ dễ bỏ sót các cơ chế save dạng replace.

### 13.2. Rename trong cùng directory

Nếu một entry đổi tên từ `old.txt` thành `new.txt` trong cùng directory, cách biểu diễn có thể là sự kiện delete tên cũ và create tên mới, nhưng bạn không được giả định mọi provider đều phát chính xác một cặp tương ứng, nhất là khi bị coalescing/overflow hoặc có hoạt động đồng thời.

Nên cập nhật state theo **danh sách mục thực sự tồn tại** và nghiệp vụ, thay vì cố đoán object identity duy nhất từ hai events thiếu correlation ID.

## 14. `OVERFLOW` và tái đồng bộ trạng thái

Hãy giả sử watcher đã xử lý được 5.000 events, nhưng provider phát sinh nhiều events hơn hàng đợi có thể giữ. Nếu events bị loại bỏ, consumer có thể nhận `OVERFLOW`.

Một chiến lược bền vững:

1. Đánh dấu registry/cache của directory liên quan là **có thể chưa đồng bộ**.
2. Lên lịch quét lại directory hoặc subtree thuộc phạm vi được phép.
3. Lấy trạng thái thực `Files.list`/`walkFileTree` với error handling.
4. Đối chiếu với danh sách file/metadata/version đã lưu.
5. Thực hiện các thao tác idempotent để sửa chênh lệch.
6. Đồng thời tiếp tục xử lý notifications mới với thứ tự và khóa phù hợp.
7. Ghi metrics overflow, thời lượng rescan và số entry, nếu cần.
8. Không xóa dữ liệu người dùng hoặc metadata quan trọng chỉ vì một event có thể đã mất.

**Không có cách từ `OVERFLOW` xác định đầy đủ danh sách những events đã mất.** Nó là dấu hiệu cần khôi phục tính đúng đắn bằng một nguồn sự thật khác: trạng thái file hiện hành, database/manifest hoặc business event log đáng tin.

### 14.1. Watcher là “signal to investigate”, không phải event sourcing

Một ứng dụng event sourcing cần chuỗi sự kiện bền vững, xác định, có ID và khả năng replay. `WatchService` không cung cấp toàn bộ các bảo đảm ấy. Nếu mất event làm mất tiền, mất đơn hàng hoặc gây vi phạm nghiệp vụ, hãy dùng cơ chế bền vững (database transaction + outbox, queue phù hợp, workflow persisted) và xem WatchService như tín hiệu tăng tốc phản ứng, **không là nguồn sự thật duy nhất**.

### 14.2. Đừng block watcher loop bằng I/O nặng

Nếu mỗi `ENTRY_MODIFY` kích hoạt parse hàng GB ngay trong thread gọi `pollEvents()`, events mới có thể tích tụ nhanh, làm tăng độ trễ và nguy cơ overflow. Một kiến trúc thường dùng là:

- Watcher thread nhận, phân loại, ghi nhận path/kind và enqueue **tác vụ nhẹ**.
- Worker pool có giới hạn concurrency và queue/backpressure thực hiện xử lý nặng.
- Logic xử lý công việc theo path có thể **deduplicate** các modify notifications trùng nhau.
- Khi quá tải hoặc overflow, ưu tiên **reconciliation**.

Đặt giới hạn queue, metrics và lifecycle; không dùng executor vô hạn với số lượng task tăng theo mọi modify count.

## 15. Đóng WatchService và xử lý chờ vô hạn

`WatchService` là `Closeable`/`AutoCloseable` và nên đóng khi không cần theo dõi nữa.

```java
try (WatchService watcher =
        FileSystems.getDefault().newWatchService()) {
    // Đăng ký directories, chạy loop.
}
```

Đây là **mảnh minh họa**, cần import `FileSystems`, `WatchService`. Khi `watcher.close()` được gọi, threads đang chờ ở `take()` hoặc `poll(timeout)` sẽ nhận `ClosedWatchServiceException`. Đừng bắt exception ấy rồi log như một lỗi production nếu đó là **shutdown được chủ động yêu cầu**.

### 15.1. Chương trình F — `CloseWatchServiceDemo.java`

Chương trình có worker thread chờ `watcher.take()`, main thread đóng watcher và xác minh lệnh chờ được giải phóng.

```java
import java.io.IOException;
import java.nio.file.*;
import java.util.concurrent.*;

public final class CloseWatchServiceDemo {
    public static void main(String[] args)
            throws IOException, InterruptedException,
                   ExecutionException, TimeoutException {
        Path root = Files.createTempDirectory("watch-close-");
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try (WatchService watcher =
                     root.getFileSystem().newWatchService()) {
            root.register(watcher,
                    StandardWatchEventKinds.ENTRY_CREATE);
            CountDownLatch running = new CountDownLatch(1);

            Future<Boolean> finished = pool.submit(() -> {
                running.countDown();
                try {
                    watcher.take();
                    return false;
                } catch (ClosedWatchServiceException expected) {
                    return true;
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return false;
                }
            });

            running.await();
            watcher.close();

            System.out.println("closedUnblocksTake=" +
                    finished.get(2, TimeUnit.SECONDS));
        } finally {
            pool.shutdownNow();
            Files.deleteIfExists(root);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CloseWatchServiceDemo.java
java CloseWatchServiceDemo
```

**Stdout đã kiểm chứng:**

```text
closedUnblocksTake=true
```

### 15.2. Giải thích

- `newSingleThreadExecutor` chạy consumer chờ `take()`.
- `CountDownLatch` chỉ xác nhận thread bắt đầu tiến vào đoạn chờ; main có thể đóng watcher **trước hoặc sau** khi lệnh `take()` thực sự block. Trong cả hai trường hợp, lệnh lấy key sau khi watcher đóng sẽ nhận `ClosedWatchServiceException`.
- `watcher.close()` giải phóng hệ thống theo dõi.
- `Future.get(2, TimeUnit.SECONDS)` tránh để test treo mãi khi có lỗi.
- `pool.shutdownNow()` dọn executor.
- `Files.deleteIfExists(root)` xóa directory tạm mà test đã tạo.

Đây là ví dụ kiểm tra shutdown, không dùng polling để đo timing events. Trong production, cần phối hợp vòng đời thread pool và watcher để tránh log spam hay mất task đang xử lý dở.

### 15.3. Interruption khác close

`watcher.take()` và `watcher.poll(timeout, ...)` có thể ném `InterruptedException` nếu thread bị interrupt. Khi đó, tùy contract của loop, thường nên dừng một cách có kiểm soát hoặc khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` trước khi thoát.

`ClosedWatchServiceException` là **unchecked exception** khi watcher đóng; đừng bắt `IOException` và nghĩ đã xử lý được cả trường hợp close. Với một service dừng có chủ đích, cả hai tình huống cần policy rõ.

## 16. Khung event loop có xử lý ba kinds và overflow

Đây là **mảnh minh họa**, không phải lớp standalone, nhưng phản ánh một flow nên review kỹ:

```java
while (running) {
    WatchKey key;
    try {
        key = watcher.take();
    } catch (ClosedWatchServiceException closed) {
        break;  // Watcher bị đóng (shutdown).
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        break;
    }

    Path directory = watchedDirectories.get(key);
    boolean needRescan = false;

    for (WatchEvent<?> event : key.pollEvents()) {
        WatchEvent.Kind<?> kind = event.kind();

        if (kind == StandardWatchEventKinds.OVERFLOW) {
            needRescan = true;
            continue;
        }
        if (!(event.context() instanceof Path relative)) {
            needRescan = true;
            continue;
        }
        if (directory == null) {
            needRescan = true;
            continue;
        }

        Path affected = directory.resolve(relative);
        if (kind == StandardWatchEventKinds.ENTRY_CREATE) {
            onPotentialCreate(affected);
        } else if (kind == StandardWatchEventKinds.ENTRY_DELETE) {
            onPotentialDelete(affected);
        } else if (kind == StandardWatchEventKinds.ENTRY_MODIFY) {
            onPotentialModify(affected, event.count());
        }
    }

    boolean valid = key.reset();
    if (!valid) {
        watchedDirectories.remove(key);
        // Nếu cần, đăng ký lại sau khi đã xác minh directory.
    }
    if (needRescan && directory != null) {
        scheduleRescan(directory);
    }
}
```

Các biến `running`, `watcher`, `watchedDirectories` và các method `onPotentialCreate`/`onPotentialDelete`/`onPotentialModify`/`scheduleRescan` là **phần tích hợp phải do ứng dụng định nghĩa**. Syntax `instanceof Path relative` là pattern matching hiện có trên Java 17+, **không phải syntax Java 7**; với Java 7 viết `instanceof Path` rồi cast riêng.

### 16.1. Vì sao callback được đặt tên “potential”?

Đến lúc xử lý, file có thể đã bị move/delete/recreate. Tên `onPotentialCreate` nhấn mạnh đây là **thông báo cần kiểm tra lại state**, không phải bằng chứng một object còn tồn tại hoặc vẫn mang cùng nội dung/identity.

### 16.2. Khi xử lý lỗi trong callback

Nếu `onPotentialModify` có thể ném exception, code production cần catch ở boundary thích hợp để:

- Không làm consumer loop chết âm thầm.
- Bảo đảm reset key theo contract dù một event handler lỗi.
- Ghi lại failed item để retry/reconcile.
- Không tiếp tục xóa/copy dữ liệu nếu chưa có quyền hoặc trạng thái không chắc chắn.
- Không coi handler thành công chỉ vì event object đã được đọc.

Một pattern thường dùng là đặt xử lý events trong `try` và `key.reset()` trong `finally`, nhưng cần phối hợp đúng với việc key invalid hoặc watcher bị đóng. Tránh `return` giữa chừng khiến key không reset.

## 17. WatchService có những giới hạn nền tảng nào?

Tài liệu Java mô tả cơ chế notification có thể dựa trên facilities native của OS, hoặc một số phương án dựa trên **polling**. Vì vậy nhiều đặc điểm là implementation-specific:

| Yếu tố | Không có bảo đảm portable |
| --- | --- |
| Độ trễ nhận event | Không có một latency cố định cho mọi hệ thống |
| Thứ tự giữa events | Không có ordering toàn cục bắt buộc qua providers/dirs |
| Số `ENTRY_MODIFY` khi sửa một file | Có thể một hoặc nhiều |
| Coalescing | Có thể gộp repeated modifications |
| File tồn tại rất ngắn | Có thể không được phát hiện bởi polling implementation |
| Remote/network filesystem | Không bắt buộc nhìn thấy changes do hệ thống remote tạo ra |
| Watcher khi directory bị move/rename | Path/registration có thể stale hoặc invalid theo provider |
| File được producer ghi xong | `ENTRY_MODIFY` không bảo đảm completed write |
| Event storage capacity | Có giới hạn implementation-dependent; có thể `OVERFLOW` |
| Hành vi symlink registration | Cần kiểm tra theo filesystem/provider |
| Thay đổi metadata nào tạo modify event | Phụ thuộc provider |

### 17.1. Đừng coi một test Windows là chứng minh tính portable

Ở QA Windows/JDK, việc tạo–ghi–xóa file trong temp directory đã báo ba event kinds. Trên provider khác, đặc biệt polling/network/virtual filesystem, thông báo có thể khác hoặc một số events không đến trong timeout của demo.

Bởi vậy, khi học:

- Dùng stdout **đã đo** để biết API hoạt động trong môi trường thử.
- Dùng **hợp đồng API** để biết điều gì được bảo đảm.
- Không viết test CI yêu cầu số modify events cố định trên mọi máy.
- Không đánh đồng "đã đăng ký đủ ba kinds" với "không bao giờ bỏ sót thay đổi".

### 17.2. Không tự động rơi vào busy polling

Vòng lặp:

```java
while (running) {
    WatchKey key = watcher.poll();
    if (key == null) continue;
    // ...
}
```

có thể spin nhanh khi không có events, gây CPU cao. Với thread watcher riêng, `take()` hoặc `poll(timeout, unit)` thường thích hợp hơn. Có cách dừng vòng lặp bằng close/interrupt thay vì chỉ kiểm tra một flag nhưng vẫn bị block vô hạn.

## 18. Xử lý path và rủi ro bảo mật

Event context của ba `ENTRY_*` là `Path` tương đối từ directory đã đăng ký. Khi ghép:

```java
Path child = (Path) event.context();
Path affected = watchedDir.resolve(child).normalize();
```

bạn đã tạo một path để **xác minh lại**, chứ chưa chứng minh file đó được phép mở, xóa hay xử lý.

### 18.1. Context không cấp quyền

Một notification không cho biết caller hay actor nào tạo/sửa/xóa entry. Nếu watcher phục vụ một tính năng nhạy cảm:

- Dùng directory root do service quản lý.
- Giữ quyền filesystem theo nguyên tắc least privilege.
- Xác minh **định danh nghiệp vụ** của resource.
- Đừng tự mở/execute một file vừa xuất hiện nếu không có validation.
- Kiểm soát symlinks, path traversal, file types và TOCTOU.
- Không đặt bất kỳ nội dung nhận được trong file thành lệnh shell không được kiểm chứng.

### 18.2. Symlink có thể làm path khác nơi bạn mong đợi

`affected` có thể là symlink hoặc nằm dưới một directory có symlink. Nếu xử lý dựa trên `Files.readAllBytes`/`Files.readString` theo mặc định, nó có thể đi vào target ngoài directory intended.

`Path.normalize()`, `Path.startsWith(base)` là kiểm tra từ vựng hữu ích nhưng **không tự trở thành security boundary** đối với intermediate symlink hoặc entry bị thay khi có race. Khi threat model cho phép attacker chỉnh directory entries, cần quyền/dir-handle strategy phù hợp.

### 18.3. Event path không phải file identity

Cùng tên `result.csv` có thể được xóa rồi tạo lại. Một `ENTRY_MODIFY` nhận sau đó không xác nhận file hiện tại là object mà producer vừa sửa. Nếu identity hoặc thứ tự nghiệp vụ quan trọng, dùng version ID/hash/transaction protocol và đối chiếu state thay vì chỉ dùng path.

### 18.4. Khi đọc file lớn theo event

Không nên load toàn bộ file vào memory vì chỉ nhận một `ENTRY_MODIFY`. Cân nhắc stream, giới hạn kích thước, charset, timeout, kiểm tra schema, kiểm soát duplicate và nguồn dữ liệu không tin cậy. WatchService chỉ nói có một loại thay đổi được quan sát; nó không kiểm tra tính hợp lệ của nội dung.

## 19. Luồng khởi động và trạng thái đã có trước khi watcher chạy

Một service restart phải xử lý trường hợp file đã tồn tại sẵn khi khởi động. `WatchService` không replay các events đã xảy ra trước registration.

Một thiết kế nên xác định:

1. **State of record**: metadata store/cache/database hay tình trạng file trực tiếp?
2. **Registration**: khi nào bắt đầu watch để giảm blind window?
3. **Initial scan**: có cần tìm những file đã có sẵn không?
4. **Reconciliation**: nếu event xảy ra giữa scan và registration, phát hiện bằng cách nào?
5. **Recovery**: nếu consumer crash hoặc watcher quá tải, quét lại thế nào?
6. **Duplicates**: một file xuất hiện trong scan và event thì có xử lý an toàn hơn một lần không?
7. **Idempotency**: nếu một modify event được quan sát nhiều lần, job xử lý có làm hỏng dữ liệu hoặc tạo duplicate record không?
8. **Shutdown**: có hoàn tất hoặc lưu tiến độ những tasks đang chạy không?

### 19.1. Trường hợp hợp lý: cập nhật UI danh sách file

UI có thể dùng watcher như trigger, rồi đọc lại danh sách file hiện hành trong directory sau mỗi nhóm events. Nếu trễ/thiếu một notification, một lần refresh đầy đủ sau đó có thể phục hồi trạng thái. Mất event nhỏ có thể chấp nhận về UX nếu có recheck định kỳ.

### 19.2. Trường hợp cần thêm cơ chế: xử lý giao dịch

Nếu mỗi file đại diện một **đơn hàng duy nhất** và không được bỏ sót, watcher đơn lẻ là không đủ. Cần một giao thức publish/acknowledge bền vững, persisted inbox/outbox, consumer checkpoint và retries. WatchService có thể đánh thức consumer nhanh hơn, nhưng **source of truth** phải là nơi có bảo đảm giao dịch cần thiết.

### 19.3. File publish hoàn chỉnh

Một workflow hợp lý:

- Producer ghi file vào tên tạm/working location.
- Producer flush/close và xác minh nội dung theo contract.
- Producer move sang tên final (atomic move chỉ khi provider hỗ trợ và scope phù hợp).
- Consumer watch directory final nhận `ENTRY_CREATE`/events phù hợp.
- Consumer kiểm tra file hiện hành và xử lý idempotent.

Đây là mô hình thiết kế; một hệ thống vẫn cần xét backup, perms, rename-over-existing, cross-file-store move, liveness và notification loss. **Không suy ra atomic publish chỉ từ việc có `ENTRY_CREATE`**.

## 20. Xử lý exception và lifecycle khi làm việc với WatchService

| Trường hợp | Điều có thể xảy ra | Hướng xử lý |
| --- | --- | --- |
| Path đăng ký không là directory | `NotDirectoryException` hoặc `IOException` khác | Xác minh directory và ownership |
| Provider không hỗ trợ watcher/event kind | `UnsupportedOperationException` | Fallback bằng scan/poll có kiểm soát |
| Watcher đã đóng | `ClosedWatchServiceException` | Kết thúc loop/shutdown hoặc báo lifecycle error |
| Thread bị interrupt khi chờ | `InterruptedException` | Tuân thủ cancellation policy, thường khôi phục interrupt flag |
| WatchKey invalid do directory bị xóa/mất truy cập | `key.reset() == false` | Bỏ registration, reconcile hoặc đăng ký lại khi phù hợp |
| Event context không phù hợp kind mở rộng | Cast/validation có thể thất bại | Kiểm tra kind/context trước xử lý |
| `OVERFLOW` | Event có thể mất | Quét lại state và metrics |
| File đã bị xóa trước lúc consumer đọc | `NoSuchFileException` / `IOException` | Recheck/skip/retry theo business policy |
| File đang được process khác ghi | Partial data, lock/share errors | Đợi publish protocol, bounded retry, validation |
| Directory bị move sau registration | Path/key semantics tùy provider | Revalidate `watchable` và registration |
| Watcher close khi đang block | `ClosedWatchServiceException` | Kết thúc worker sạch |
| `Files.createTempDirectory`/cleanup thất bại | `IOException` | Propagate/report, tránh xóa ngoài scope |

### 20.1. `key.reset() == false` phải được xem là trạng thái thực

Một registration có thể bị hủy không chỉ vì code gọi `cancel()`, mà còn vì directory không còn truy cập được hoặc watcher đã đóng. Không tiếp tục tin key đã invalid sẽ tạo events trong tương lai.

Khi quản lý nhiều directories, loại key invalid ra khỏi map, theo dõi lý do nếu có và quyết định đăng ký lại sau khi revalidate path. `key.watchable()` vẫn có thể trả path cũ nhưng path đó không bảo đảm còn hợp lệ sau move.

### 20.2. Xử lý lỗi file đọc sau event là trách nhiệm ứng dụng

Nếu `ENTRY_CREATE` đến, bạn mở file mà bị `AccessDeniedException`, điều đó không phải “event sai”. Thay đổi file và việc consumer có thể đọc được nó là hai vấn đề độc lập. Thiết kế quyền, file-sharing, retry và thông báo lỗi phù hợp.

### 20.3. Close service không đồng nghĩa xóa file

`WatchService.close()` chỉ đóng cơ chế watch. Nó **không xóa directory** và không “rollback” những file được producer tạo. Trong các demo, `Files.deleteIfExists` ở `finally` là cleanup tách biệt cho những file tạm do chính test tạo.

## 21. Lỗi phổ biến: nhận định và cách sửa

### 21.1. Đăng ký một file rồi mong nhận mọi thay đổi file đó

Default WatchService theo dõi **entries của directory**. Đăng ký directory cha và filter event context phù hợp với tên file cần quan tâm.

### 21.2. Quên `key.reset()`

Key có thể ở trạng thái signalled và không được queue lại như mong đợi. Sau xử lý events hãy reset, kiểm tra boolean validity.

### 21.3. Nghĩ `watcher.take()` trả WatchEvent

`take()` trả **WatchKey**. Phải gọi `key.pollEvents()` để lấy `List<WatchEvent<?>>`.

### 21.4. Cast mọi event.context thành Path

`OVERFLOW` có `Kind<Object>` và context có thể null. Kiểm tra OVERFLOW trước, sau đó xử lý `ENTRY_*` hoặc provider-specific event kinds.

### 21.5. Ghép context với working directory hiện tại

Context là `Path` **tương đối với directory đã đăng ký**, không tự là absolute path. Lấy directory từ registration/key phù hợp và resolve.

### 21.6. Coi mỗi lần save là một `ENTRY_MODIFY`

Một thao tác save có thể tạo nhiều modify events hoặc dùng temp-file rename dẫn đến create/delete. Không đặt business logic phụ thuộc đúng một modify mỗi save.

### 21.7. Coi `ENTRY_MODIFY` là “file đã hoàn tất ghi”

Không có bảo đảm. Dùng publish protocol, validation, versioning hoặc bounded retry phù hợp.

### 21.8. Bỏ qua `ENTRY_CREATE` vì chỉ quan tâm file bị sửa

Một editor dùng replace-via-rename có thể tạo entry final mới. Nếu watcher chỉ đăng ký MODIFY, logic có thể không nhận tín hiệu phù hợp.

### 21.9. Coi `ENTRY_DELETE` là chứng nhận xóa vĩnh viễn nội dung

Event báo directory entry mất hoặc moved-out, không báo dữ liệu trên backup hoặc vị trí mới đã bị xóa.

### 21.10. Cho rằng `ENTRY_CREATE` có count > 1 sau nhiều creates

Theo `StandardWatchEventKinds`, count của từng create event là 1. `ENTRY_MODIFY` mới có count 1 hoặc lớn hơn theo contract; không trộn tính chất.

### 21.11. Đăng ký root rồi nghĩ đã watch recursive

Không mặc định. Đăng ký từng subdirectory cần theo dõi; chú ý khoảng race khi subdirectory được tạo rất nhanh.

### 21.12. Coi `OVERFLOW` là một file có context Path

`OVERFLOW` có thể có null/context implementation-specific, và không chỉ ra file cụ thể. Rescan và reconcile thay vì cast hoặc bỏ qua.

### 21.13. Không có cách thoát `take()`

`take()` có thể chặn vô hạn nếu không có event. Thiết kế shutdown bằng `watcher.close()`/interrupt hoặc dùng `poll(timeout)`.

### 21.14. Busy spin với `poll()`

Không có event thì `poll()` trả null ngay; loop không backoff có thể tiêu thụ CPU. Dùng `take()` hoặc timed poll.

### 21.15. Một handler ném lỗi làm chết watcher thread

Bắt/xử lý lỗi theo boundary, bảo đảm quản lý reset/key validity và ghi lại công việc cần retry.

### 21.16. Đếm event như số giao dịch chính xác

WatchService không cung cấp exactly-once, replayable log hoặc ordering tuyệt đối. Nếu cần đếm business events, dùng hệ thống persisted và idempotency keys.

### 21.17. Không kiểm tra support trên network/virtual filesystem

Remote changes có thể không được phát hiện. Cần test provider thực tế và fallback scan khi cần.

### 21.18. Không xử lý symlink và path traversal

Context có thể chỉ tới file đã bị thay, hoặc path có symlink. Validate và giới hạn quyền trước khi mở nội dung hoặc thực hiện side effects.

### 21.19. Hardcode stdout chính xác theo thời gian của OS

Số modify events, timing và thứ tự không phải invariant portable. Test nên kiểm cơ chế xử lý logic bằng synthetic events và integration theo môi trường.

### 21.20. Dùng API không chuẩn để chỉnh watcher sensitivity

Những modifiers không chuẩn có thể là implementation-specific. Với mục tiêu kiến thức Java hiện hành, chỉ dùng API chuẩn `ENTRY_*` và xác minh provider cần thiết; tránh lệ thuộc một API nội bộ `com.sun.*` làm giải pháp portable.

## 22. Ma trận kiểm thử

| Test | Điều nên xác minh | Điều không nên giả định |
| --- | --- | --- |
| Kind definitions | Tên kinds và `Kind.type()` | Provider sẽ luôn phát đủ mọi kind trong mọi môi trường |
| Registration | WatchKey hợp lệ, watchable là directory đã register | Regular file có thể register như directory trên mọi provider |
| Poll chưa có event | Có thể `null` | Luôn có event ngay sau register |
| Create direct entry | `ENTRY_CREATE` có ý nghĩa entry mới hoặc moved-in | File chắc chắn đã ghi xong |
| Delete direct entry | `ENTRY_DELETE` có ý nghĩa entry biến mất/moved-out | File đã bị xóa vĩnh viễn |
| Modify direct entry | `ENTRY_MODIFY` có thể thông báo thay đổi | Đúng một event, đúng thứ tự, đúng timing |
| Event context | `Path` tương đối ở ba kinds chuẩn | Context là absolute path |
| Create/Delete event count | `count()==1` cho mỗi event | File chỉ tạo/xóa một lần trong cả đời |
| Modify event count | ≥1; có thể được gộp | Count là số lần save logic |
| OVERFLOW | Có tín hiệu phải reconcile | Có danh sách events đã mất |
| Nonrecursive | Root registration không tự subscribe grandchildren | Watch root đủ cho toàn bộ tree |
| Subdirectory register | Watch subdir để nhận direct-child events của nó | Registration bảo đảm 0ms delivery |
| Key reset | Key hợp lệ có thể trở về ready | Reset tự khôi phục registration invalid |
| Key cancel | Hủy subscription | Cancel xóa directory hoặc các file |
| Close watcher | Đánh thức `take/poll` bằng closed exception | Close rollback file changes |
| Interrupted wait | Thoát theo cancellation policy | Interrupt bị bỏ qua an toàn |
| Remote filesystem | Có thể thiếu notification | Native local filesystem behavior áp dụng y hệt |
| Rename/move | Có thể biểu hiện create/delete | Có `ENTRY_RENAME` chuẩn hoặc transaction ID |
| File đang ghi | Consumer có thể gặp partial content | `ENTRY_MODIFY` bảo đảm complete |
| Symlink/path race | Phải revalidate/trust boundary | Event bảo đảm identity và authorization |

### 22.1. Hai lớp test: synthetic unit vs OS integration

**Synthetic unit test** như `EventInterpretationDemo` phù hợp để test:

- Mapper `kind → action`.
- Logic event count.
- Handling OVERFLOW branch.
- Chuyển context tương đối sang path dự kiến.
- Deduplication và idempotency ở tầng ứng dụng.

**Integration test** với watcher thật như `EntryEventsDemo` phù hợp để test:

- Provider hỗ trợ registration.
- Thư mục tạm có thể nhận create/delete/modify events trong khoảng thời gian nhất định.
- `reset()` được gọi.
- `close()` giải phóng resource.
- Hệ thống thật có thể gặp timing/coalescing.

Không dùng một lớp test thay thế hoàn toàn lớp kia. Nếu CI chạy trên nhiều OS, test integration cần xử lý timeout và những tính chất implementation-specific theo thiết kế.

### 22.2. Vì sao không in full event stream làm expected output?

Nếu bạn in từng `ENTRY_MODIFY` và thời điểm nhận, output của một lần chạy có thể khác lần tiếp theo, ngay trên cùng máy. Dữ liệu event stream thật phù hợp để **quan sát/debug**, còn assertion portable nên kiểm những điều Java API hứa, như kiểu context, ý nghĩa event kind và vòng đời WatchKey.

## 23. Bài tập thực hành

**Bài 1 — Chọn event.** Với một directory `inbox`, sự kiện nào có thể xuất hiện khi một file mới được tạo? Khi file bị move ra ngoài? Khi producer append nội dung?

**Bài 2 — Đăng ký.** Viết đoạn `Path.register(watcher, ...)` nhận đúng ba kinds và giải thích vì sao phải đăng ký **trước** khi producer thay đổi file.

**Bài 3 — `WatchKey`.** Vì sao `watcher.take()` không thể đem cast trực tiếp thành `WatchEvent<Path>`? Cần gọi method gì để lấy events?

**Bài 4 — Context.** Một watcher đăng ký `/data/jobs`, event context trả `report.csv`. Hãy dựng path tới entry; vì sao không tự dùng `Paths.get("report.csv")` như absolute path?

**Bài 5 — Event count.** Đọc `StandardWatchEventKinds` để giải thích vì sao create/delete count của một event là 1 nhưng modify count có thể lớn hơn 1.

**Bài 6 — OVERFLOW.** Tại sao phải nhận `OVERFLOW` dù không register riêng? Vì sao context của nó không nên cast vô điều kiện sang `Path`?

**Bài 7 — Reset.** Điều gì có thể xảy ra nếu một consumer gọi `key.pollEvents()` nhưng quên `key.reset()`?

**Bài 8 — Key invalid.** Nếu `key.reset()` trả false, một chương trình đang watch 10 directories nên xử lý thế nào?

**Bài 9 — Editor save.** Vì sao bấm Save trong editor không luôn tương ứng đúng một modify event? Nêu một workflow temp file + rename.

**Bài 10 — One-level.** Tại sao đăng ký `root` không tự theo dõi `root/sub/deep.txt`? Làm sao đăng ký các thư mục con khi cần?

**Bài 11 — Create of directory.** Một directory mới `sub` được tạo dưới root đã watch. Sau khi nhận create `sub`, có bảo đảm mọi file được tạo nhanh trong `sub` đều được báo không? Giải thích cửa sổ race trước khi register `sub`.

**Bài 12 — Delete event.** Sau `ENTRY_DELETE`, gọi `Files.readString` vào path có luôn thành công không? Vì sao nên xử lý như state change và recheck?

**Bài 13 — Rename.** Một file move từ `incoming` sang `processed`. Có chuẩn `ENTRY_RENAME` với old/new name không? Nếu chỉ thấy delete/create, làm thế nào để tránh giả định cặp events?

**Bài 14 — Tính toàn vẹn.** Bạn cần xử lý mỗi file đơn hàng **không được bỏ sót**. Vì sao chỉ dựa vào WatchService không đủ? Đề xuất persisted inbox/outbox hoặc reconciliation protocol.

**Bài 15 — Debounce.** Một file phát nhiều modify events khi ghi. Tại sao không nên parse cả file trong watcher thread mỗi lần nhận event?

**Bài 16 — Chờ.** So sánh `poll()`, `poll(timeout,unit)` và `take()`. Cách nào phù hợp với thread chạy dài? Cần shutdown thế nào?

**Bài 17 — Close.** Nếu watcher đang block ở `take()` mà thread khác gọi `close()`, chuyện gì xảy ra? Bắt loại exception nào?

**Bài 18 — Interrupt.** Khi `take()` ném `InterruptedException`, vì sao thường cần khôi phục interrupt flag trước khi thoát?

**Bài 19 — Permission/race.** Một entry được thông báo mới nhưng đến lúc consumer đọc đã bị xóa. Có phải `ENTRY_CREATE` sai không? Code xử lý ra sao?

**Bài 20 — Bài thực nghiệm.** Chạy `EntryEventsDemo` trên Windows hoặc Linux. So kết quả 3 lượt chạy mà không coi số modify events phải cố định. Ghi rõ các thuộc tính nào theo contract và những gì phụ thuộc provider.

**Bài 21 — Synthetic test.** Tạo `WatchEvent<Path>` giả lập cho create/delete count=1 và modify count=3. Test handler mà không cần thao tác file thật. Vì sao loại test này không chứng minh OS sẽ phát modify count=3?

**Bài 22 — Network filesystem.** Ứng dụng đang watch một network mount. Tại sao không nên hứa phát hiện mọi thay đổi được thực hiện từ máy khác? Thiết kế fallback nào hợp lý?

**Bài 23 — Startup gap.** Một file xuất hiện trước khi đăng ký watcher. Làm thế nào quét file có sẵn, bắt events mới và reconcile tránh bỏ sót?

**Bài 24 — Untrusted file.** Tại sao sự kiện new file không phải authorization mở/execute file? Phân tích symlink, file type, content validation và least privilege.

### Đáp án gợi ý

- **1:** Tạo → CREATE; moved-out/delete → DELETE; sửa → có thể MODIFY.
- **2:** `dir.register(watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY)`; watcher không replay lịch sử.
- **3:** `take()` trả WatchKey; dùng `key.pollEvents()`.
- **4:** `watchedDir.resolve((Path)event.context())`; context tương đối.
- **5:** Create/Delete count từng event luôn 1; modify có thể 1 hoặc lớn hơn.
- **6:** OVERFLOW có thể báo events bị loại; context có thể null; rescan.
- **7:** Key signalled có thể không được requeued nếu không reset.
- **8:** Loại key invalid, giữ keys khác, revalidate/re-register khi phù hợp.
- **9:** Editor có thể temp-write, rename/move, tạo/deletion notifications.
- **10:** WatchService đăng ký directories, không recursive mặc định; register mỗi directory.
- **11:** Không; tạo sub nhanh trước khi register có thể làm mất các notifications sâu.
- **12:** Không; file đã mất/move, cần xử lý `IOException` và reconcile.
- **13:** Không có chuẩn rename kind; cần metadata/protocol nếu muốn xác định identity.
- **14:** Watcher có event loss/overflow và không replay; dùng persisted source of truth.
- **15:** Dễ backlog/overflow; deduplicate và xử lý ở worker có giới hạn.
- **16:** `poll` nonblocking, timed poll chờ giới hạn, `take` chờ; close/interrupt cho shutdown.
- **17:** `ClosedWatchServiceException`.
- **18:** Không nuốt cancellation signal; khôi phục flag rồi thoát theo contract.
- **19:** Không; event phản ánh quan sát trước đó, trạng thái có thể đổi.
- **20:** Kết quả phụ thuộc OS/provider/timing, không assert đủ events portable.
- **21:** Synthetic unit test chỉ xác minh handler logic, không xác nhận actual notification.
- **22:** Remote changes có thể không được phát hiện; cần rescan/persisted state.
- **23:** Kết hợp scan, registration và reconciliation, xử lý duplicates idempotent.
- **24:** Event không chứng minh trust/permission; revalidate symlink, path, type và content.

## 24. Checklist trước khi đưa WatchService vào dự án

- [ ] Chỉ sử dụng `WatchService` cho notification phù hợp, không như durable transaction log.
- [ ] Directory được tạo/xác minh trước khi đăng ký.
- [ ] Các event kinds được đăng ký đúng nhu cầu: CREATE, DELETE, MODIFY.
- [ ] Có đường xử lý `OVERFLOW` dù không đăng ký riêng.
- [ ] Đọc events qua `WatchKey.pollEvents()`.
- [ ] Luôn có bước `WatchKey.reset()` sau xử lý.
- [ ] Xử lý `reset() == false` và loại invalid keys.
- [ ] Hiểu event context là `Path` tương đối với directory đăng ký.
- [ ] Phân biệt `WatchEvent.Kind<Path>` với `OVERFLOW Kind<Object>`.
- [ ] Không cast `OVERFLOW.context()` thành `Path`.
- [ ] Không dựa vào thứ tự/độ trễ/số lần modify event cố định.
- [ ] Không coi `ENTRY_MODIFY` là dấu hoàn tất ghi.
- [ ] Xử lý rename/save-via-rename qua CREATE/DELETE khi cần.
- [ ] Không tự giả định một WatchKey theo dõi recursive.
- [ ] Có kế hoạch đăng ký thư mục mới và xử lý race trước registration.
- [ ] Có cơ chế rescan/reconcile khi startup/overflow/restart.
- [ ] Các handler idempotent nếu nhận duplicate notifications.
- [ ] Có cách shutdown `take()` bằng close/interrupt.
- [ ] Dùng try-with-resources hoặc lifecycle rõ để đóng watcher.
- [ ] Không block watcher loop bằng tác vụ I/O nặng.
- [ ] Có giới hạn queue, worker, metrics, log lỗi và backpressure.
- [ ] Đường dẫn/filename được revalidate trước khi mở hoặc xử lý.
- [ ] Có chính sách symlink và dữ liệu chưa tin cậy.
- [ ] Tính đến provider, local/remote filesystem và quyền truy cập.
- [ ] Unit test được với synthetic events; integration test không đòi stdout cố định về timing.
- [ ] Chỉ dùng API chuẩn hiện hành; tránh modifiers không portable trừ khi có yêu cầu platform-specific được xác minh.

## 25. Nguồn chính thức còn hiệu lực

- [Java SE 17 — `WatchService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): registration, key queue, reset, overflow, file may still be changing, platform-dependent delivery, close và methods poll/take.
- [Java SE 17 — `WatchKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html): ready/signalled, pollEvents, reset/cancel/isValid/watchable.
- [Java SE 17 — `WatchEvent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html): kind, context tương đối và count.
- [Java SE 17 — `StandardWatchEventKinds`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): hợp đồng ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY, OVERFLOW và count từng kind.
- [Java SE 17 — `Path.register`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#register(java.nio.file.WatchService,java.nio.file.WatchEvent.Kind...)): đăng ký directory và các event kinds.
- [Java SE 17 — `FileSystem.newWatchService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html#newWatchService()): tạo WatchService theo provider.
- [Java SE 17 — `ClosedWatchServiceException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/ClosedWatchServiceException.html): watcher đã đóng.
- [Dev.java — Watching a Directory for Changes](https://dev.java/learn/api/io/java-io/file-system/watching-dir-changes/): hướng dẫn Java về đăng ký, key và events.

**Kết luận:** `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY` là ba loại notification chuẩn cho **entry trong directory đã được đăng ký**. Nhận key qua `take`/`poll`, lấy events bằng `pollEvents`, đọc `kind/context/count` đúng kiểu và **`reset` key** sau xử lý. Luôn có đường xử lý `OVERFLOW`, key invalid, shutdown và thay đổi filesystem đồng thời. Vì Java **không bảo đảm mọi sự kiện đều đến đúng một lần, đúng thứ tự hoặc ngay khi file đã ghi xong**, sử dụng WatchService như *tín hiệu để kiểm tra lại trạng thái*, kết hợp reconciliation và business protocol nếu yêu cầu độ tin cậy cao.