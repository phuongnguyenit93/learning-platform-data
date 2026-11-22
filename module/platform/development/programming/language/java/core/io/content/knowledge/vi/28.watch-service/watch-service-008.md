# Sự kiện lặp, gộp và thời điểm nội dung tệp chưa hoàn tất trong Java WatchService

## 1. Vấn đề cần hiểu

`WatchService` của Java NIO.2 báo cho ứng dụng biết **trạng thái của thư mục có thể đã thay đổi**. API này hữu ích cho công cụ tự tải lại cấu hình, đồng bộ tệp, phát hiện tài liệu đầu vào, tự động xử lý file hoặc giám sát thư mục. Tuy nhiên, các sự kiện **không phải nhật ký giao dịch chính xác**, không phải một hàng đợi bền vững và **không đảm bảo file đã ghi hoàn tất** khi consumer nhận được thông báo.

Ba hiện tượng phải thiết kế trước:

1. **Sự kiện lặp:** một thao tác lưu file có thể sinh nhiều `ENTRY_MODIFY`; cùng một path có thể xuất hiện trong nhiều đợt.
2. **Sự kiện gộp và mất sự kiện:** provider có thể gộp các thay đổi cùng loại/ngữ cảnh trong một `WatchEvent` có `count()` lớn hơn một; khi tích lũy không kịp, có thể phát `OVERFLOW` vì một số event đã bị loại.
3. **File chưa sẵn sàng:** `ENTRY_CREATE` hoặc `ENTRY_MODIFY` có thể tới trước khi writer đóng file hoặc hoàn tất record cuối cùng. Đọc ngay có thể lấy được chỉ một phần JSON, CSV, ZIP hoặc nội dung nhị phân.

Nguyên tắc thiết kế: **coi event là tín hiệu cần đối chiếu lại trạng thái file, không coi event là lệnh nhập dữ liệu đúng một lần hoặc dấu hiệu producer đã kết thúc.**

## 2. Phạm vi bảo đảm của WatchService

Ứng dụng tạo một `WatchService` qua `FileSystems.getDefault().newWatchService()`, rồi đăng ký **thư mục** bằng `Path.register(...)`. Các event chuẩn:

| Kind | Điều thể hiện | Điều không được bảo đảm |
| --- | --- | --- |
| `ENTRY_CREATE` | Một entry xuất hiện trong thư mục đã đăng ký. | File chứa đầy đủ bytes, hoặc producer không còn ghi. |
| `ENTRY_MODIFY` | Provider quan sát thấy thay đổi của một entry. | Chỉ có một lần sửa, thay đổi đã kết thúc hoặc dữ liệu hợp lệ. |
| `ENTRY_DELETE` | Entry không còn hiện diện ở vị trí được quan sát. | Đây chắc chắn là xóa nghiệp vụ thay vì move/rename. |
| `OVERFLOW` | Một số thông báo có thể đã không được giữ trong queue. | Các event còn lại đủ để phục dựng mọi thay đổi. |

Với các event entry tiêu chuẩn, `event.context()` là đường dẫn tương đối tới mục bên trong thư mục đã đăng ký. Đường dẫn đầy đủ thường lấy bằng:

```java
// Snippet minh họa, key là WatchKey hợp lệ.
Path watched = (Path) key.watchable();
Path relative = (Path) event.context();
Path full = watched.resolve(relative);
```

Không được cast `event.context()` sang `Path` trước khi kiểm tra `OVERFLOW`, vì overflow không đại diện một file riêng. `Path.register` trong Java SE 17/21 chủ yếu theo dõi các entry của **thư mục**, không tự động theo dõi cây thư mục con. Muốn giám sát cây phải đăng ký từng thư mục, kể cả các thư mục con mới tạo.

Với filesystem mạng, provider tùy chỉnh hoặc cơ chế theo dõi bằng polling, độ trễ và khả năng nhận sự kiện có thể khác. Javadoc Java nói rõ thời điểm phát hiện, thứ tự event và khả năng phát hiện thay đổi trên remote filesystem **phụ thuộc implementation**; file tồn tại rất ngắn đôi khi không được phát hiện. Không đặt giả định “sửa một lần chắc chắn nhận một event ngay lập tức”.

## 3. Vì sao cùng một file có nhiều ENTRY_MODIFY?

Một writer có thể mở file rồi ghi lần lượt:

```text
open("data.csv")
write("id,amount\n")
flush()
write("1,100\n")
write("2,200\n")
close()
```

Từ phía watcher, có thể thấy một chuỗi `ENTRY_CREATE` và nhiều `ENTRY_MODIFY`, hoặc chỉ một số sự kiện, tùy OS và cách JDK nhận native notifications.

Nguyên nhân bao gồm:

- Producer ghi theo từng khối nhỏ hoặc nhiều lần flush.
- File được truncate rồi viết lại; metadata và nội dung thay đổi ở các thời điểm khác nhau.
- Một editor lưu nội dung qua tên tạm rồi rename; watcher có thể quan sát tạo/xóa/modify ở đường dẫn khác nhau.
- Provider tổng hợp event theo đợt; cùng path xuất hiện lại sau khi WatchKey được reset.
- Hoạt động đồng bộ, backup, antivirus hoặc process khác tạo thêm metadata/content changes.

**Sai lầm:** mỗi lần nhận `ENTRY_MODIFY` lại gọi `importFile(path)` và chèn toàn bộ record vào database. Cùng file có thể bị import nhiều lần, sinh duplicated invoices hoặc gửi notification lặp.

**Thiết kế đúng:** event chỉ đánh dấu path là “dirty”; worker xử lý trạng thái hiện tại theo một **idempotency key** (artifact ID + phiên bản/checksum/transaction ID), ghi nhận kết quả chỉ khi commit thành công. Nếu cùng một phiên bản xuất hiện qua nhiều event, xử lý lại phải không gây side effect lặp.

## 4. Ý nghĩa của WatchEvent.count và coalescing

`WatchEvent<T>` có ba thành phần chính:

- `kind()`: loại sự kiện.
- `context()`: thông tin gắn với sự kiện, thường là tên path tương đối.
- `count()`: số lần event được quan sát và biểu diễn chung trong đối tượng event.

Ví dụ:

```text
kind=ENTRY_MODIFY
context=report.csv
count=4
```

Dòng ví dụ không nói rằng producer đã gọi `write` đúng 4 lần, cũng không có nghĩa file có đúng 4 phiên bản hợp lệ. Đây là **count của notification mà provider ghi nhận/gộp**, không phải đếm giao dịch kinh doanh.

Cùng một `kind` và `context` có thể được gộp để giảm số đối tượng event. Khi hai thao tác không giống nhau hoặc đến ở thời điểm khác, không có quy tắc portable buộc mọi hệ thống phải gộp thành cùng một cách.

Không dùng vòng xử lý file `count()` lần:

```java
// Anti-pattern: số notification không phải số phiên bản dữ liệu.
for (int i = 0; i < event.count(); i++) {
    processFile(path);
}
```

Đoạn trên chỉ là **minh họa lỗi**, không phải source độc lập. `event.count()` hữu ích cho metrics hoặc cảnh báo burst changes, nhưng **nội dung file lúc đọc mới là trạng thái cần kiểm chứng**.

### Coalescing khác OVERFLOW

| Hiện tượng | Ý nghĩa | Hướng ứng xử |
| --- | --- | --- |
| Duplicate events | Cùng mục được thông báo lặp qua một hay nhiều đợt. | Dedup/debounce và idempotent processing. |
| Coalesced event | Một WatchEvent biểu diễn nhiều lần quan sát cùng kind/context. | Không import theo count; xác định file version cần xử lý. |
| `OVERFLOW` | Hệ thống có thể đã bỏ thông tin sự kiện do giới hạn queue. | **Rescan/reconcile thư mục**, không dựa vào danh sách event hiện có. |
| Không nhận event sau restart | WatchService không phải durable message log. | Startup scan; processed-version state bền vững. |

Javadoc `WatchService` quy định khi implementation biết đã bỏ event, nó đưa `OVERFLOW`. Nhưng việc **không thấy** overflow không phải lời chứng minh mọi thay đổi ở mọi OS/remote filesystem đã được phát hiện.

## 5. Vòng đời WatchKey và xử lý batch đúng cách

`WatchService` đưa **WatchKey** đại diện cho một đăng ký đã được signal vào queue. Consumer dùng:

- `watcher.take()`: đợi tới khi có key.
- `watcher.poll()`: lấy ngay hoặc trả `null`.
- `watcher.poll(timeout, unit)`: đợi có hạn.
- `key.pollEvents()`: lấy và loại các event đang tích lũy của key.
- `key.reset()`: đưa key trở lại trạng thái ready sau khi xử lý batch; trả `false` nếu key không còn hợp lệ.

Luồng xử lý:

```text
key READY
  |
FileSystem quan sát thay đổi
  v
key SIGNALED -> được đưa vào queue
  |
watcher.take / poll
  |
key.pollEvents -> duyệt event
  |                ENTRY_*  -> đánh dấu path dirty
  |                OVERFLOW -> cần full rescan
  v
key.reset()
  +-> true : tiếp tục giám sát
  +-> false: mất đăng ký, cần phục hồi
```

Nếu quên `reset()`, watcher có thể không tiếp tục nhận những event mới như mong đợi. Nếu trì hoãn `reset()` hàng chục giây để xử lý file lớn trong cùng thread, backlog có thể tăng và làm mất sự kiện. Vì thế trong production, watcher nên **lấy sự kiện nhanh, cập nhật trạng thái nhẹ, reset đúng lúc**, còn parse/import được giao cho worker có giới hạn queue.

Một snippet hướng dẫn xử lý:

```java
// Bên trong vòng lặp watcher, rescanNeeded đã được khai báo.
WatchKey key = watcher.take();
Path dir = (Path) key.watchable();

for (WatchEvent<?> ev : key.pollEvents()) {
    if (ev.kind() == StandardWatchEventKinds.OVERFLOW) {
        rescanNeeded = true;
        continue;
    }
    Path child = dir.resolve((Path) ev.context());
    markDirty(child, ev.kind(), ev.count());
}
if (!key.reset()) {
    handleInvalidRegistration(dir);
}
```

Đây là **snippet kiến trúc**, không phải chương trình độc lập: `markDirty`, `handleInvalidRegistration` và `rescanNeeded` do ứng dụng định nghĩa. `OVERFLOW` không mang một path file hợp lệ để đưa thẳng vào `markDirty`. Các lỗi như `ClosedWatchServiceException`, `InterruptedException` cần được xử lý theo vòng đời ứng dụng.

## 6. Một event MODIFY không nói writer đã đóng tệp

Javadoc của `WatchService` nói rõ: khi có event báo file trong thư mục được sửa, **không bảo đảm chương trình thực hiện sửa đổi đã hoàn tất**.

Minh họa diễn biến:

```text
Producer                     Watcher / consumer
--------                     ------------------
CREATE input.json
write("{ \"items\": [")
                             ENTRY_CREATE tới
                             đọc file, JSON chưa đóng
write("{ \"id\": 1 }")
                             ENTRY_MODIFY tới
                             retry parse, vẫn có thể sai
write("] }")
close writer
                             không có event chuẩn "WRITE_COMPLETED"
```

Đây chỉ là **một lịch xen kẽ có thể xảy ra**, không phải số lượng hoặc thứ tự event portable. Ngay cả khi `Files.exists(path)` là `true` và `Files.size(path) > 0`, producer vẫn có thể tiếp tục ghi.

Các dạng file dễ bị đọc dở:

- JSON/XML chưa có dấu đóng, parser ném lỗi.
- CSV chưa có dòng cuối hoặc ký tự newline cuối.
- ZIP/JAR có central directory ở cuối, có thể chưa đọc được.
- Record nhị phân chứa length/header đã ghi nhưng payload/checksum chưa hoàn tất.
- Ảnh/video được tạo header trước khi ghi hết frame.

Đừng coi mọi parse exception đều do writer chưa xong: file cũng có thể hỏng thật. Ứng dụng phải có **giới hạn retry, timeout, kiểm tra cấu trúc và quarantine**.

## 7. Chiến lược mạnh nhất: file tạm rồi công bố atomically

Khi có thể chỉnh producer, hãy dùng một **giao thức công bố** thay vì đoán từ `ENTRY_MODIFY`:

1. Producer tạo tệp dưới tên tạm như `report.csv.tmp`; consumer bỏ qua `.tmp`.
2. Producer ghi đủ nội dung, kiểm tra nội bộ và **đóng file**.
3. Producer gọi `Files.move(temp, ready, StandardCopyOption.ATOMIC_MOVE)` trong cùng filesystem, nếu được hỗ trợ.
4. Consumer **chỉ xử lý** `report.csv.ready` sau khi nó xuất hiện; theo dõi event là trigger để scan candidate.
5. Consumer xác nhận version, độ dài/checksum/schema, xử lý idempotent và lưu kết quả.

`ATOMIC_MOVE` làm thao tác đổi tên/move ở cấp filesystem có tính nguyên tử khi provider hỗ trợ; nó không bảo đảm mọi filesystem hỗ trợ hay thay thế target đã tồn tại giống nhau. Nếu không hỗ trợ, Java ném `AtomicMoveNotSupportedException`. Khi atomic publication là yêu cầu bắt buộc, **không lặng lẽ fallback sang copy/move không nguyên tử**.

**Atomic rename không đồng nghĩa durability khi mất điện.** Nếu yêu cầu dữ liệu và directory entry sống sót sau crash, cần chính sách `FileChannel.force`/synchronization phù hợp filesystem/OS. Và `WatchService` vẫn có duplicate/overflow: consumer phải reconcile chứ không dựa hoàn toàn event.

### Ví dụ Java 17+: tạo bản tạm và công bố

Tạo file `AtomicPublishDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class AtomicPublishDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("publish-demo-");
        Path temp = dir.resolve("message.tmp");
        Path ready = dir.resolve("message.ready");
        try {
            Files.writeString(temp, "PART", StandardCharsets.US_ASCII,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            System.out.println("partial-temp=" + Files.readString(temp));
            Files.writeString(temp, "DONE", StandardCharsets.US_ASCII,
                    StandardOpenOption.APPEND);
            Files.move(temp, ready, StandardCopyOption.ATOMIC_MOVE);
            System.out.println("published=" + Files.readString(ready));
            System.out.println("temp-exists=" + Files.exists(temp));
        } finally {
            Files.deleteIfExists(temp);
            Files.deleteIfExists(ready);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac --release 17 AtomicPublishDemo.java
java AtomicPublishDemo
```

Kết quả đã kiểm chứng trên filesystem hỗ trợ atomic move:

```text
partial-temp=PART
published=PARTDONE
temp-exists=false
```

Đầu tiên producer mới có `PART`. Consumer không được xem nội dung tạm là một artifact đã sẵn sàng. Sau khi app ghi thêm `DONE` và đóng stream, tên `message.ready` mới được công bố. **Chính quy tắc công bố tên** mang ý nghĩa hoàn tất, không phải số notification nhận được. Khi dùng mô hình này với watcher, chỉ enqueue những file `.ready`/manifest hợp lệ, không xử lý mọi `ENTRY_CREATE`.

## 8. Marker file hoặc manifest có checksum

Một biến thể là producer xuất hiện tệp dữ liệu trước, nhưng chỉ tạo file marker `.done` hoặc `.ready` **sau khi hoàn tất**:

```text
batch-0007.data
batch-0007.ready
```

Manifest có thể chứa tên, version/sequence, kích thước, checksum, tổng số record và schema version. Consumer theo dõi marker, sau đó xác minh tệp dữ liệu.

**Lưu ý:** nếu producer tạo marker trước khi hoàn tất dữ liệu hoặc ghi marker không nguyên tử, chính marker cũng có thể bị đọc dở. Vì vậy marker cần một contract rõ: viết tạm rồi công bố, metadata/manifest có định dạng kiểm chứng được; consumer cần xử lý file bị xóa, thiếu, thay thế hoặc có checksum sai.

Dùng producer sequence hoặc content hash để idempotency sẽ mạnh hơn chỉ dùng path. Nếu file mới thay thế cùng tên `batch.data`, consumer không thể coi đó là cùng version chỉ vì path giống nhau.

## 9. Không kiểm soát producer: debounce và kiểm tra ổn định chỉ là heuristic

Khi không thể yêu cầu file tạm + atomic move hoặc marker, consumer có thể dùng thời gian yên lặng và so sánh metadata:

1. Khi nhận create/modify, đặt path vào danh sách dirty và ghi lại thời điểm sự kiện mới nhất.
2. Sau khoảng quiet period được cấu hình theo nguồn (ví dụ một vài trăm mili-giây hoặc vài giây), kiểm tra `size` và `lastModifiedTime`.
3. Chờ thêm rồi kiểm tra lại; nếu không đổi, thử mở và parse file theo định dạng.
4. Đọc/parse có giới hạn, xác minh file chưa đổi sau khi xử lý; nếu thay đổi, đánh dấu dirty để thử lại.
5. Sau deadline hoặc số lần retry tối đa, báo lỗi/quarantine thay vì lặp vô hạn.

**Không được tuyên bố file hoàn tất chỉ nhờ size/mtime ổn định.** Writer có thể tạm dừng lâu hơn quiet period, ghi đè cùng size, OS có timestamp độ phân giải thấp hoặc file bị thay thế sau khi đọc metadata. Race giữa `Files.exists` và `Files.readAllBytes` cũng tồn tại. Nếu phải đảm bảo mạnh, cần giao thức hợp tác từ producer hoặc định dạng có commit marker/transaction log.

Đừng dùng `Thread.sleep(...)` ngay trong watch loop: nó chặn xử lý event của thư mục khác, làm backlog tăng và tăng nguy cơ overflow. Dùng `ScheduledExecutorService` hoặc một worker scheduler riêng, giới hạn queue và backpressure.

### Mô hình debounce per-path bằng generation

```java
// Snippet minh họa, không độc lập:
// versions: ConcurrentHashMap<Path, Long>
// scheduler: ScheduledExecutorService
long generation = versions.merge(path, 1L, Long::sum);
scheduler.schedule(() -> {
    Long current = versions.get(path);
    if (current == null || current.longValue() != generation) return;
    enqueueForReadinessCheck(path);
}, 700, TimeUnit.MILLISECONDS);
```

Nếu event mới tới cùng path, generation tăng; callback lịch cũ không enqueue. Tuy vậy, snippet này không xử lý toàn bộ tình huống: task cũ vẫn có thể tồn tại trong scheduler, file tiếp tục đổi mà event không tới, và logic worker phải có trạng thái “dirty during processing”. Production cần giới hạn số lịch hẹn, đồng bộ state và xử lý xóa/tạo lại path. Chỉ dùng ví dụ để hiểu **debounce không đồng nghĩa readiness guarantee**.

## 10. Ví dụ Java 17+: WatchService và vòng đời WatchKey

Demo tạo thư mục tạm, đăng ký watcher **trước khi tạo file**, sau đó lấy `ENTRY_CREATE` trong vòng tối đa 5 giây. Vì số modify events phụ thuộc OS, demo chỉ kiểm tra create, không in số lượng modify.

Tạo file `WatchEventDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;

public class WatchEventDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("watch-demo-");
        Path file = dir.resolve("report.txt");
        try (WatchService watcher = FileSystems.getDefault().newWatchService()) {
            dir.register(watcher, StandardWatchEventKinds.ENTRY_CREATE,
                    StandardWatchEventKinds.ENTRY_MODIFY,
                    StandardWatchEventKinds.ENTRY_DELETE);
            Files.writeString(file, "READY", StandardCharsets.US_ASCII,
                    StandardOpenOption.CREATE_NEW);
            boolean created = false;
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
            while (!created && System.nanoTime() < deadline) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) break;
                WatchKey key = watcher.poll(remaining, TimeUnit.NANOSECONDS);
                if (key == null) break;
                for (WatchEvent<?> event : key.pollEvents()) {
                    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                        throw new IllegalStateException("Rescan needed after OVERFLOW");
                    }
                    if (event.kind() == StandardWatchEventKinds.ENTRY_CREATE
                            && Path.of("report.txt").equals(event.context())) {
                        created = true;
                    }
                }
                if (!key.reset()) throw new IllegalStateException("Invalid watch key");
            }
            if (!created) throw new IllegalStateException("Create event not observed");
            System.out.println("created-observed=" + created);
            System.out.println("file-content=" + Files.readString(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac --release 17 WatchEventDemo.java
java WatchEventDemo
```

Kết quả đã kiểm chứng trên local filesystem có native notification:

```text
created-observed=true
file-content=READY
```

**Giải thích:** watcher được đăng ký trước thời điểm file xuất hiện, `poll(timeout)` có giới hạn chờ, `pollEvents()` lấy các event trong batch, `event.context()` được so theo relative path và `reset()` tái kích hoạt key. Demo báo lỗi khi `OVERFLOW` vì đây không phải consumer production; consumer thật phải rescan.

Điều khiến file có nội dung `READY` lúc đọc ở chương trình này là **`Files.writeString` đã trả về và đóng stream trước khi chúng ta lấy event**, không phải vì `ENTRY_CREATE` tự bảo đảm producer đã đóng file. Trên polling filesystem hoặc remote mount, event có thể không tới trước deadline. Không coi stdout trên là cam kết universal.

## 11. Thiết kế xử lý lặp, overflow và tệp thay đổi trong lúc xử lý

Một consumer thực tế nên tách watcher và processing workers:

```text
WatchService / WatchKey
   |
   +-- ENTRY_CREATE / ENTRY_MODIFY ---> markDirty(path)
   |                                      |
   |                                      v
   |                               debounce / readiness
   |                                      |
   |                                      v
   |                              validate + parse
   |                                      |
   |                                      v
   |                              idempotent commit
   |
   +-- ENTRY_DELETE -------------------> reconcile missing entry
   |
   +-- OVERFLOW -----------------------> full directory rescan

Startup scan / periodic reconciliation -> same processing pipeline
```

### Không đánh mất event mới khi worker đang xử lý

Một Set chứa các path pending tránh queue trùng, nhưng có race:

1. Worker đang đọc file A.
2. Producer sửa file A lần nữa; watcher thấy event nhưng Set đã có A nên không enqueue.
3. Worker xóa A khỏi Set khi xử lý xong.
4. Không còn task nào xử lý phiên bản mới.

Hãy dùng state rõ:

```text
IDLE -> DIRTY -> PROCESSING
                   |
                   +-- có event trong lúc xử lý -> DIRTY_AGAIN
                   |
                   +-- xong và dirty_again -> PROCESSING lần nữa
                   |
                   +-- xong và không dirty -> IDLE
```

State phải được cập nhật thread-safe (`ConcurrentHashMap.compute`, mutex per-key hoặc event loop owner duy nhất). Worker có thể so sánh producer version/hash trước và sau import; nếu nội dung đổi, chạy lại. **Không có state machine nào tự biến WatchService thành reliable event log**, nên khi restart/overflow vẫn phải reconcile.

### Idempotency với cơ sở dữ liệu

Nếu input artifact có `artifactId` và `version`, hãy dùng chúng làm khóa duy nhất ở nơi lưu trạng thái xử lý. Ví dụ bảng `processed_files` có unique key trên cặp identity/version; transaction vừa ghi dữ liệu nghiệp vụ vừa ghi processed marker nếu được phép trong cùng storage. Nhờ đó, xử lý lại duplicate notification không phát sinh duplicate invoice hoặc gửi cùng job hai lần. Nếu việc thực hiện side effect bên ngoài database (gửi email, thanh toán), cần thêm outbox/idempotency protocol phù hợp, không dựa riêng vào Set trong RAM.

## 12. Rescan và xử lý tình huống mất event

Khi `OVERFLOW`, có thể đã bỏ event cho những path chưa từng được consumer thấy. Không thể lấy `event.count()` hoặc event cuối để khôi phục danh sách path đã mất. Phải **scan trạng thái thư mục** rồi đối chiếu với durable processed state.

Các thời điểm nên rescan:

- Sau khi đăng ký watcher lúc startup, để phát hiện files có sẵn và hạn chế khe race giữa scan/registration.
- Khi có `OVERFLOW`.
- Khi `WatchKey.reset() == false`, thư mục được tạo lại hoặc mount bị thay đổi.
- Sau restart/redeploy của ứng dụng.
- Định kỳ nếu độ tin cậy quan trọng hoặc filesystem có giới hạn event.

Một lộ trình hợp lý: **đăng ký watcher → scan snapshot hiện tại → bắt đầu xử lý queue event → rescan khi cần**. Dù vậy không thể có snapshot transaction tuyệt đối với directory đang đổi chỉ nhờ `Files.list` và WatchService; cần idempotency, versioning và kiểm tra lại. Nếu phải lưu mọi thay đổi trung gian, dùng producer log, message queue hoặc versioned manifest làm nguồn sự thật.

Với thư mục rất lớn, rescan có thể tốn I/O: chia batch, dùng bounded worker queues, ghi trạng thái processing, tránh đọc toàn bộ tệp vào heap và dùng streaming parse.

## 13. Hệ điều hành và loại filesystem ảnh hưởng thế nào?

| Môi trường | Khác biệt cần kiểm tra |
| --- | --- |
| Linux / Windows / macOS local | Provider có thể dùng native notifications nhưng số modify events và thời điểm nhận thay đổi theo OS, filesystem, editor và cách ghi file. |
| Remote filesystem NFS/SMB | Thay đổi từ host khác **không được Java bảo đảm luôn phát hiện**; cache, polling và network latency có thể làm event trễ/mất. |
| Container / bind mount / overlay | Native event propagation và permission phụ thuộc cách mount/host/provider; kiểm thử đúng cấu hình triển khai. |
| Polling-based provider | File vừa tạo vừa xóa rất nhanh có thể không được phát hiện; các đợt thay đổi có thể gộp. |
| Filesystem ảo/custom provider | Có thể không hỗ trợ WatchService hoặc có semantics khác; xử lý `UnsupportedOperationException`/`IOException` và fallback phù hợp. |

Đừng cố suy ra “file đã sẵn sàng” từ việc nhận event nhanh hay chậm. Phải xác định **producer protocol**, file type, yêu cầu consistency và recovery.

## 14. Lỗi phổ biến và hướng xử lý

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Mỗi `ENTRY_MODIFY` đều import dữ liệu. | Duplicate records, nhiều side effects. | Dedup và idempotency theo phiên bản. |
| Vòng `for` chạy `event.count()` lần. | Count không phải số transaction nghiệp vụ. | Xử lý state/manifest hiện tại. |
| Đọc ngay sau `ENTRY_CREATE`. | File có thể đang ghi dở. | Temp + atomic publish hoặc ready marker. |
| Coi file size không đổi 1 giây là “đã hoàn tất”. | Writer có thể tạm dừng hoặc overwrite cùng size. | Chỉ coi heuristic; validate/retry có deadline. |
| Bỏ qua `OVERFLOW`. | Mất sự kiện mà không tự chữa. | Full rescan/reconciliation. |
| Quên `WatchKey.reset()`. | Key không được kích hoạt đúng cho event tiếp theo. | Reset mỗi batch và kiểm tra boolean. |
| Dùng watcher thread để parse file hàng GB. | Backlog, tăng nguy cơ overflow. | Offload bounded worker, stream file. |
| Cast `OVERFLOW.context()` thành Path. | Sai ngữ cảnh, có thể lỗi. | Phân nhánh kind trước khi đọc context. |
| Giám sát thư mục cha và tưởng là recursive. | Bỏ qua nhiều file trong subdirectory. | Đăng ký từng thư mục. |
| Chỉ dựa vào queue event để phục hồi sau restart. | WatchService không replay durable. | Startup scan + durable processed state. |
| Có atomic rename rồi khẳng định dữ liệu bền sau mất điện. | Atomic rename khác durability. | File sync, directory sync/recovery theo OS/FS. |
| Retry mọi parse error mãi mãi. | Quá tải, stuck pipeline. | Deadline, backoff, quarantine và metrics. |
| File mới dùng lại path cũ, dedup theo tên. | Mất phiên bản dữ liệu. | Version/sequence/hash và idempotency. |

## 15. Checklist ứng dụng thật

1. Đăng ký đúng thư mục, đúng event kinds; chuyển `context()` từ relative sang full path phù hợp.
2. Mỗi WatchKey được `pollEvents` và `reset`; xử lý invalid key.
3. Phân nhánh `OVERFLOW` trước các event khác, chạy full rescan.
4. Watch thread chỉ cập nhật dirty state nhanh; không parse file dài ngay trong vòng lấy key.
5. Debounce và worker queue có giới hạn, có backpressure.
6. Ưu tiên producer temp file + atomic move hoặc marker/manifest kiểm chứng được.
7. Nếu chỉ dùng size/mtime quiet period, luôn ghi nhận đây là **heuristic** và có timeout, validation.
8. Dữ liệu có format version/checksum/length; parse dữ liệu dở đúng cách.
9. Import idempotent dựa trên artifact/version, không dựa vào event count.
10. Có startup/periodic reconciliation và xử lý restart.
11. Xử lý `NoSuchFileException`/`IOException`, file bị thay thế, mất quyền, writer lỗi.
12. Kiểm thử burst events, partial writes, overwrite, rename, network mounts và file cực ngắn trên đúng OS.

### Tự kiểm tra

**1. `ENTRY_MODIFY` có `count() == 3` đồng nghĩa producer viết ba record hoàn chỉnh?**  
Không. Count là số event tương ứng được WatchService biểu diễn gộp, không phải record count.

**2. Vì sao nhận `ENTRY_CREATE` chưa đủ để parse JSON?**  
Producer có thể mới tạo file rồi ghi tiếp, nên JSON đang thiếu dữ liệu.

**3. Gặp `OVERFLOW` có thể bỏ qua nếu event cuối cùng đã được xử lý?**  
Không. Các file khác có thể đã thay đổi mà không còn event; phải rescan.

**4. Debounce cố định 500 ms có chắc loại bỏ file chưa hoàn tất?**  
Không. Producer có thể dừng lâu hơn hoặc ghi lại cùng kích thước; đây chỉ là heuristic.

**5. Cách hợp tác tốt khi kiểm soát producer?**  
Ghi file tạm, đóng/validate, công bố bằng atomic move cùng filesystem hoặc manifest/ready marker có contract rõ.

**6. Vì sao vẫn cần idempotency sau atomic publication?**  
Watcher còn có duplicate/coalescing/overflow/restart; consumer có thể thử lại cùng artifact/version.

**7. Một WatchService có cung cấp exactly-once delivery và durable replay không?**  
Không. Muốn bảo đảm nghiệp vụ phải xây dựng transaction/state bền vững hoặc dùng event log/message broker.

## Nguồn chính thức

- [Java SE 21 — WatchService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchService.html): tính phụ thuộc platform, `OVERFLOW` và cảnh báo file chưa được writer hoàn tất.
- [Java SE 21 — WatchEvent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchEvent.html): `kind()`, `count()`, `context()` và coalescing.
- [Java SE 21 — WatchKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchKey.html): queue, `pollEvents()`, `reset()`.
- [Java SE 21 — Path](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): `register` và đường dẫn tương đối trong event context.
- [Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `move` với `ATOMIC_MOVE` và giới hạn tính nguyên tử.
- [Oracle Java Tutorials — Watching a Directory for Changes](https://docs.oracle.com/javase/tutorial/essential/io/notification.html): mô hình theo dõi thư mục và vòng xử lý WatchKey (hướng dẫn gốc dùng JDK 8).

**Kết luận:** `WatchService` là **tín hiệu quan sát**, không phải tín hiệu transaction commit. Hãy xử lý lặp/gộp bằng dedup + idempotency, khôi phục `OVERFLOW` bằng rescan, và xác nhận file hoàn tất bằng giao thức công bố phù hợp. Khi không có giao thức từ producer, debounce/metadata chỉ là phương án tốt nhất có giới hạn chứ không phải bảo đảm tuyệt đối.