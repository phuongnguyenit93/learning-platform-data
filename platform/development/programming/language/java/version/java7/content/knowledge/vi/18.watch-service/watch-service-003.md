# `WatchService` trong Java: Vòng nhận sự kiện bằng `take()` hoặc `poll()`

## 1. Mục tiêu: nhận sự kiện filesystem đúng cách, không quay vòng vô ích

Giả sử một ứng dụng cần theo dõi thư mục nhập liệu: khi có tệp mới, nó cập nhật danh sách; khi tệp bị xóa, nó loại khỏi chỉ mục; khi tệp bị sửa, nó chuẩn bị xử lý lại. Java cung cấp API **`java.nio.file.WatchService`**, được giới thiệu từ Java 7 và vẫn được hỗ trợ trong Java 17+.

Những câu hỏi quan trọng nhất không phải chỉ là “đăng ký theo dõi thế nào?”, mà là:

- Khi chưa có thay đổi, **luồng nhận sự kiện nên chờ hay làm việc khác**?
- Sự khác biệt giữa `take()`, `poll()` và `poll(timeout, unit)` là gì?
- Tại sao `WatchService` trả về **`WatchKey`** chứ không trả từng `WatchEvent`?
- Tại sao phải gọi `key.pollEvents()`, rồi **`key.reset()`**?
- Khi nào phải dừng vòng lặp vì key hết hiệu lực?
- Cách thoát an toàn khi người dùng dừng chức năng theo dõi, thread bị interrupt hoặc `WatchService` bị đóng?
- Có nên giả định một lần sửa file chỉ có một event không? Nếu bị `OVERFLOW` thì sao?

**Ý chính:** `WatchService` là một **nguồn thông báo thay đổi**; `take()`/`poll()` là cách lấy **watch key đã báo hiệu** từ hàng đợi. Muốn theo dõi liên tục, ứng dụng phải tự thiết kế vòng nhận key, duyệt các event trong key, xử lý những event liên quan, **reset key**, và dừng theo một điều kiện vòng đời rõ ràng.

Trong bài, ví dụ đầy đủ được viết và kiểm chứng trên **Java 17+**. Nội dung tập trung vào API còn áp dụng hiện nay, không đưa kỹ thuật lỗi thời hoặc phụ thuộc vào hành vi riêng của một OS làm bảo đảm chung.

## 2. Kiến trúc: từ thư mục được theo dõi đến event

### 2.1. Tạo `WatchService`

```java
import java.nio.file.Path;
import java.nio.file.WatchService;

Path directory = /* thư mục do ứng dụng chọn */;
try (WatchService watcher =
        directory.getFileSystem().newWatchService()) {
    // Đăng ký và nhận sự kiện ở đây.
}
```

Đây là **mã minh họa trong phương thức**, không phải chương trình chạy độc lập: `directory` phải được khai báo và có giá trị. `WatchService` triển khai `Closeable` nên có thể sử dụng `try-with-resources` để đóng tài nguyên.

Một cách khác trên filesystem mặc định:

```java
WatchService watcher =
        java.nio.file.FileSystems.getDefault().newWatchService();
```

Nếu `directory` thuộc ZIP filesystem hoặc provider khác, lựa chọn `directory.getFileSystem()` tránh ngộ nhận watcher của provider mặc định luôn dùng được cho mọi `Path`.

### 2.2. Đăng ký một thư mục vào service

```java
import static java.nio.file.StandardWatchEventKinds.*;

WatchKey registration = directory.register(
        watcher,
        ENTRY_CREATE,
        ENTRY_MODIFY,
        ENTRY_DELETE);
```

Đây là đoạn minh họa; cần import `java.nio.file.WatchKey` và xử lý `IOException` nếu provider gặp lỗi.

- `ENTRY_CREATE`: phát hiện một entry mới được tạo trong thư mục được đăng ký.
- `ENTRY_MODIFY`: phát hiện một entry bị thay đổi; **không đồng nghĩa file đã được ghi xong**.
- `ENTRY_DELETE`: phát hiện một entry bị xóa.
- `OVERFLOW`: thông báo có thể đã **mất/loại bỏ một số event**, được hỗ trợ ngầm; không cần truyền `OVERFLOW` vào lệnh register.

`directory.register(...)` trả về một `WatchKey` biểu diễn **registration**. Sau khi có thay đổi, service báo hiệu key; sau đó consumer lấy key khỏi hàng đợi qua `take()` hoặc `poll()`.

### 2.3. Service trả key, key chứa danh sách sự kiện

```text
Đăng ký:
directory.register(watcher, ENTRY_CREATE, ENTRY_MODIFY, ENTRY_DELETE)
                                 |
                                 v
                          WatchKey ở trạng thái READY
                                 |
                                 | có thay đổi được phát hiện
                                 v
                          WatchKey ở trạng thái SIGNALED
                                 |
                                 v
                   WatchService queue các KEY
                                 |
                       take() / poll()
                                 |
                                 v
                           WatchKey key
                                 |
                         key.pollEvents()
                                 |
                    +------------+------------+
                    |            |            |
              ENTRY_CREATE ENTRY_MODIFY ENTRY_DELETE
                    |
               xử lý từng event
                    |
                 key.reset()
                    |
            key còn hợp lệ? -> tiếp tục hoặc dừng
```

**Tách hai mức hàng đợi:** `watcher.take()` không trả `WatchEvent` trực tiếp; nó trả **`WatchKey`**. `key.pollEvents()` mới trả danh sách `WatchEvent<?>` tích lũy cho đối tượng được theo dõi.

Nếu bỏ qua `reset()`, một key đã báo hiệu có thể không quay lại trạng thái sẵn sàng để tiếp tục được queue đúng cách cho các đợt event sau. Đây là lỗi phổ biến khi viết vòng watch.

## 3. `take()`: chờ đến khi một key được báo hiệu

### 3.1. API và ý nghĩa

```java
WatchKey key = watcher.take();
```

`WatchService.take()`:

- Lấy và loại khỏi hàng đợi **watch key tiếp theo**.
- **Chờ (blocking)** nếu chưa có key.
- Nếu có key sẵn trong queue, trả về mà không cần chờ.
- Có thể ném **`InterruptedException`** nếu luồng bị interrupt trong lúc chờ.
- Có thể ném **`ClosedWatchServiceException`** nếu service đã đóng hoặc bị đóng trong lúc chờ.
- Không cung cấp một timeout qua chính overload `take()`.

Đây là lựa chọn phù hợp cho một **worker chuyên trách nhận sự kiện**: không cần vòng lặp gọi `poll()` liên tục khi thư mục không thay đổi.

### 3.2. Vòng lặp điển hình sử dụng `take()`

```java
while (running) {
    WatchKey key = watcher.take();

    for (WatchEvent<?> event : key.pollEvents()) {
        // Xử lý event; phân biệt OVERFLOW.
    }

    if (!key.reset()) {
        // Registration không còn hợp lệ.
        break;
    }
}
```

Đây là **mã minh họa**; `running`, `watcher` và chính sách xử lý event cần được định nghĩa trong ứng dụng. Phần thân cần đặt trong phương thức xử lý `InterruptedException` và tình huống đóng watcher.

**Không nên viết `take()` trên UI thread hoặc request thread** rồi hy vọng chúng luôn hoàn tất nhanh. Khi không có thay đổi, `take()` có thể chờ vô thời hạn; nó phù hợp hơn trên một worker/thread riêng hoặc trong một kiến trúc có cơ chế shutdown rõ.

### 3.3. Ví dụ luồng sinh sự kiện

Một chương trình thử có thể:

1. Đăng ký `ENTRY_CREATE` cho một thư mục trống.
2. Khởi chạy thread khác, đợi 150 ms rồi tạo `blocking.txt`.
3. Thread chính gọi `watcher.take()` và chờ.
4. Khi key được báo hiệu, đọc `key.pollEvents()`.
5. Thấy context `blocking.txt`, xử lý và gọi `key.reset()`.

**Không dựa vào `Thread.sleep` trong ứng dụng thật để bảo đảm event sẽ được phát hiện.** Giấc ngủ trong demo chỉ giúp quan sát cơ chế blocking. Thời điểm nhận event do filesystem provider quyết định; sự kiện có thể bị trễ hoặc bị gộp.

### 3.4. Dừng một `take()` đang chờ

Nếu thread bị interrupt, `take()` ném `InterruptedException`. Nếu `watcher.close()` được gọi từ thread khác, các thread đang đợi `take()` được đánh thức bằng `ClosedWatchServiceException` theo API.

Đây là hai chiến lược shutdown thường gặp; nên phân biệt **shutdown mong muốn** với **lỗi ứng dụng** và không bắt `RuntimeException` rồi tiếp tục quay vòng mãi.

## 4. `poll()`: kiểm tra hàng đợi ngay, không đợi

### 4.1. API

```java
WatchKey key = watcher.poll();

if (key == null) {
    // Không có watch key nào trong hàng đợi tại thời điểm kiểm tra.
} else {
    // Xử lý key.pollEvents(); sau đó key.reset().
}
```

`WatchService.poll()`:

- **Không chờ** khi hàng đợi rỗng.
- Trả `null` nếu hiện tại không có key đã được queue.
- Trả `WatchKey` nếu có, đồng thời loại key đó khỏi hàng đợi.
- Có thể ném `ClosedWatchServiceException` khi watcher đã đóng.
- Không khai báo `InterruptedException` như hai API chờ.

`poll() == null` **không có nghĩa thư mục không có file**, không có nghĩa không bao giờ có event, và cũng không chứng minh trước đó chưa hề có thay đổi. Nó chỉ nói rằng **không có key đang chờ được lấy từ queue tại thời điểm gọi**.

### 4.2. Khi nào chọn `poll()`?

`poll()` phù hợp nếu thread còn nhiều công việc khác và muốn kiểm tra sự kiện theo các thời điểm có chủ đích:

```java
WatchKey key = watcher.poll();

if (key != null) {
    for (WatchEvent<?> event : key.pollEvents()) {
        // Xử lý sự kiện.
    }

    if (!key.reset()) {
        // Xử lý registration hết hiệu lực.
    }
}

// Tiếp tục công việc khác.
```

Đoạn này là **minh họa** trong ngữ cảnh có watcher và phương thức xử lý.

### 4.3. Cạm bẫy busy-wait

Một vòng lặp như sau **không nên dùng mặc định**:

```java
while (running) {
    WatchKey key = watcher.poll();
    if (key == null) {
        continue; // Quay vô hạn, liên tục dùng CPU.
    }
    // ...
}
```

Trong trường hợp thư mục im lặng, vòng lặp có thể gọi `poll()` với tốc độ rất cao, tiêu tốn CPU nhưng không làm event đến sớm hơn.

**Cách sửa:**

- Dùng `take()` khi thread chuyên đợi event.
- Dùng `poll(timeout, unit)` nếu cần cả chờ sự kiện **lẫn** cập nhật công việc định kỳ.
- Hoặc tích hợp `poll()` vào một scheduler/event loop hiện có với nhịp gọi rõ, thay vì spin loop vô hạn.

Không nên thêm `Thread.sleep(1)` theo thói quen rồi cho rằng đã giải quyết mọi vấn đề: nó vẫn là polling thủ công khó điều chỉnh, và không có cơ chế kiểm soát timeout/shutdown bằng API có sẵn tốt bằng `poll(timeout)`.

## 5. `poll(timeout, TimeUnit)`: chờ có giới hạn

### 5.1. API

```java
import java.util.concurrent.TimeUnit;

WatchKey key = watcher.poll(2, TimeUnit.SECONDS);

if (key == null) {
    // Không có key được trả về trong khoảng chờ tối đa.
} else {
    // Xử lý event, sau đó reset key.
}
```

`poll(long timeout, TimeUnit unit)`:

- Nếu có key đã sẵn trong hàng đợi, có thể trả ngay.
- Nếu queue rỗng, chờ tối đa thời lượng quy định.
- Hết thời gian mà chưa có key thì trả `null`.
- Luồng bị interrupt trong lúc chờ có thể ném `InterruptedException`.
- WatchService bị đóng trong lúc chờ có thể ném `ClosedWatchServiceException`.

**Khác với `poll()` không tham số:** timed poll có khả năng chờ, giúp tránh busy-loop. **Khác với `take()`:** timed poll có một nhịp thức dậy tự nhiên để kiểm tra timeout, cancellation flag hoặc công việc định kỳ.

### 5.2. Bảng so sánh ba cách nhận key

| Lệnh | Khi hàng đợi rỗng | Giá trị khi không có key | `InterruptedException` | Tình huống dùng |
| --- | --- | --- | --- | --- |
| `take()` | Chờ cho tới khi có key/interrupt/close | Không có `null` vì timeout | Có | Worker theo dõi chuyên trách |
| `poll()` | Trả về ngay | `null` | Không khai báo | Event loop có công việc khác |
| `poll(2, SECONDS)` | Chờ tối đa 2 giây | `null` khi hết hạn | Có | Worker cần kiểm tra dừng/heartbeat định kỳ |

**Lưu ý:** Bảng mô tả các đường xử lý thông thường; `ClosedWatchServiceException` vẫn có thể xảy ra khi watcher bị đóng. Tất cả ba lệnh trả **`WatchKey`**, không phải từng event.

### 5.3. Ví dụ vòng nhận sự kiện có nhịp thức dậy

```java
while (!Thread.currentThread().isInterrupted()
        && running.get()) {

    WatchKey key = watcher.poll(1, TimeUnit.SECONDS);

    if (key == null) {
        // Không có key: có thể kiểm tra tín hiệu shutdown,
        // cập nhật metric hoặc thực hiện housekeeping.
        continue;
    }

    for (WatchEvent<?> event : key.pollEvents()) {
        // Xử lý event. Với OVERFLOW, yêu cầu quét lại.
    }

    if (!key.reset()) {
        // Một registration không còn hiệu lực.
        break;
    }
}
```

Đây là **mã minh họa**; `running` có thể là `AtomicBoolean` và xử lý exception/shutdown nằm bên ngoài vòng lặp. Nếu có **nhiều registration**, không thể mặc định một key invalid nghĩa là tất cả watcher không còn việc; có thể cần xóa registration đó khỏi map rồi tiếp tục với những key khác.

### 5.4. Timeout không phải “mất sự kiện”

`poll(1, SECONDS) == null` chỉ báo không lấy được key trước thời hạn chờ. Không nên log “file system đã bỏ sót event” hay coi timeout như một `IOException`.

Ngược lại, `poll(timeout)` cũng **không hứa** mọi filesystem thay đổi đã được phát hiện trong đúng khoảng timeout. Độ trễ và chất lượng phát hiện có thể phụ thuộc native API hoặc polling bên trong provider.

## 6. Vòng nhận key chuẩn: lấy, xử lý, reset, kiểm tra hợp lệ

Một ví dụ idiom ngắn cho worker riêng:

```java
for (;;) {
    WatchKey key = watcher.take();

    try {
        for (WatchEvent<?> event : key.pollEvents()) {
            if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                // Đánh dấu trạng thái chưa đáng tin và rescan.
                continue;
            }

            Path relativeName = (Path) event.context();
            Path affected = ((Path) key.watchable())
                    .resolve(relativeName);

            // Kiểm tra kind và đưa affected tới handler thích hợp.
        }
    } finally {
        if (!key.reset()) {
            // Registration này không còn hợp lệ.
            break;
        }
    }
}
```

Đây là **mã minh họa** trong một phương thức có `watcher`, `Path` và các import/exception handling phù hợp. Nó giả định **chỉ có một thư mục đăng ký** và handler không tự ném exception làm hỏng flow. Khi xử lý nhiều keys, code cần quản lý chúng riêng và không break chỉ vì một key bị hủy.

Có bốn điều quan trọng:

1. **Một key có thể chứa nhiều event.** `take`/`poll` không phải API “lấy đúng một file event”.
2. **`pollEvents()` rút hết những event đang tích lũy** trên key tại thời điểm gọi. Nó có thể trả list rỗng trong các tình huống nhất định.
3. **`reset()` được gọi sau khi xử lý** để key quay lại trạng thái ready hoặc được queue lại nếu có event pending.
4. **Giá trị boolean của `reset()` phải được kiểm tra.** Nếu `false`, registration đã invalid (do cancel, thư mục không còn truy cập, watcher đóng...); không giả định có thể tiếp tục nhận event từ key ấy.

### 6.1. WatchKey ở trạng thái READY và SIGNALED

Theo tài liệu `WatchKey`:

- Khi đăng ký, key có trạng thái **ready**.
- Khi có sự kiện, key trở thành **signalled** và được đưa vào queue nếu chưa signalled.
- Các event mới trong lúc key đang signalled vẫn có thể được tích lũy **nhưng key không bị queue lại chỉ vì thêm event**.
- Gọi `reset()` đưa key về ready nếu không còn pending event; nếu vẫn có pending event, key có thể được đưa lại vào queue ngay.
- Nếu key đã invalid thì `reset()` trả `false`.

Điều này giải thích vì sao một lần `take()` có thể trả **cả một nhóm event**, và vì sao gọi `reset()` là bước không thể bỏ qua.

### 6.2. Vì sao không reset ngay sau khi lấy key?

Sai về ý định:

```java
WatchKey key = watcher.take();
key.reset();              // Reset trước khi xử lý event.
for (WatchEvent<?> event : key.pollEvents()) {
    // ...
}
```

Việc reset quá sớm làm khó phối hợp key với nhiều consumer, có thể gây xử lý chồng chéo hoặc làm logic xử lý sự kiện mất nhất quán. API khuyến nghị **xử lý event xong rồi mới reset**; khi nhiều thread cùng nhận keys, điều đó càng quan trọng để không có hai thread xử lý đồng thời event của cùng một registration.

### 6.3. Khi handler lỗi, phải có chính sách rõ

Nếu handler ném exception trong lúc đang duyệt event, ứng dụng cần quyết định:

- Dừng watcher và báo lỗi cho caller?
- Retry event theo một hàng đợi riêng?
- Đánh dấu dữ liệu chưa đồng bộ và quét lại thư mục?
- Log/quarantine một file không đọc được rồi tiếp tục?

Không nên luôn `catch(Exception ignored)` và gọi `reset` như thể mọi event đã xử lý xong. Nếu dùng `finally` để reset, phải hiểu nó chỉ **khôi phục trạng thái watch registration**, không tự rollback việc xử lý nghiệp vụ thất bại.

## 7. `WatchEvent`: kind, count và context

### 7.1. `kind()` — loại thay đổi

```java
WatchEvent.Kind<?> kind = event.kind();

if (kind == StandardWatchEventKinds.ENTRY_CREATE) {
    // Một entry được tạo.
} else if (kind == StandardWatchEventKinds.ENTRY_MODIFY) {
    // Một entry được sửa.
} else if (kind == StandardWatchEventKinds.ENTRY_DELETE) {
    // Một entry bị xóa.
} else if (kind == StandardWatchEventKinds.OVERFLOW) {
    // Có thể mất các event; rescan.
}
```

Đây là **mã minh họa**; `event` có kiểu `WatchEvent<?>` đã lấy từ `key.pollEvents()`.

`ENTRY_CREATE`/`ENTRY_MODIFY`/`ENTRY_DELETE` mô tả thay đổi entry trong thư mục đăng ký, không phải luôn có khả năng suy ra chính xác một giao dịch nghiệp vụ. Ví dụ: ứng dụng lưu file qua tệp tạm và rename có thể tạo chuỗi event khác so với ứng dụng ghi trực tiếp vào file cũ.

### 7.2. `context()` — tên tương đối so với thư mục được đăng ký

Đối với ba loại event entry chuẩn, context là một `Path` **tương đối** từ thư mục đã đăng ký đến entry bị thay đổi.

```java
Path watchedDirectory = (Path) key.watchable();
Path name = (Path) event.context();
Path affected = watchedDirectory.resolve(name);
```

Giải thích:

- `key.watchable()` thường trả chính đối tượng `Path` đã đăng ký.
- `event.context()` cho ta tên entry tương đối, ví dụ `invoice.csv`.
- `resolve` ghép thành path trong thư mục đó.
- Không dùng `Path.of(event.context().toString())` rồi coi đó là absolute path: context **không mang đầy đủ root**.
- Không cast context một cách mù quáng đối với `OVERFLOW`; hãy xử lý loại này **trước khi** lấy `Path`.

**Cảnh báo bảo mật:** Path được báo qua event không phải bằng chứng rằng entry tồn tại vào thời điểm xử lý, cũng không phải bằng chứng file an toàn để đọc. Entry có thể đã bị xóa/đổi tên hoặc chuyển thành symlink; cần quyền/containment và I/O checks phù hợp.

### 7.3. `count()` — số lần event được ghi nhận

```java
int count = event.count();
```

Một event có thể được **gộp** nhiều lần và trả `count() > 1`. Không suy rằng mỗi sự kiện trong list luôn tương ứng đúng một lần ghi hoặc một transaction. `count` có thể hỗ trợ thông tin quan sát, nhưng **không phải** số byte sửa đổi và không chứng minh nội dung file đã hoàn tất.

### 7.4. `ENTRY_MODIFY` không báo “file đã sẵn sàng”

Giả sử một chương trình ghi 500 MiB vào file `upload.bin`. WatchService có thể nhận `ENTRY_CREATE` và nhiều `ENTRY_MODIFY` **trước khi chương trình đó đóng output stream**.

Vì vậy không nên bắt event MODIFY rồi ngay lập tức coi tệp là hoàn chỉnh để xử lý:

- Nếu bạn kiểm soát producer, ưu tiên **ghi vào tệp tạm rồi rename/publish** theo hợp đồng; consumer theo dõi tín hiệu publish.
- Nếu producer ngoài ứng dụng, cần giao thức file-ready, lock/metadata ổn định hay retry theo chính sách.
- Nếu xử lý file đang bị ghi, phải chấp nhận kết quả chưa hoàn chỉnh hoặc thiết kế snapshot khác.

## 8. `OVERFLOW` và thông báo bị mất

`WatchService` có thể nhận sự kiện nhanh hơn tốc độ consumer xử lý. Implementation có thể giới hạn số event tích lũy; khi biết đã loại bỏ event, service cung cấp `OVERFLOW`.

```java
if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
    // Không tin rằng toàn bộ event đã được nhận đầy đủ.
    // Đánh dấu directory/index cần được quét lại.
    scheduleRescan(watchedDirectory);
    continue;
}
```

Đây là **minh họa** có `scheduleRescan` do ứng dụng tự định nghĩa, không phải method JDK; đoạn này không chạy độc lập.

**Vì sao cần rescan?** Khi một số event đã bị bỏ, chỉ xử lý tiếp những event còn lại không thể tái tạo chính xác tất cả thay đổi. Cần đọc lại trạng thái thực tế của thư mục bằng `Files.list`, `Files.walk` hoặc `walkFileTree` tùy phạm vi và xây lại/đối chiếu index.

Một policy hợp lý:

1. Đánh dấu trạng thái watcher là **có thể không đầy đủ**.
2. Đưa công việc rescan vào hàng đợi chuyên biệt, tránh làm một thao tác scan rất lớn trực tiếp trong thread đang lấy key.
3. Từ thư mục root được phép, đọc lại trạng thái file.
4. Đối chiếu với dữ liệu/index đang quản lý.
5. Tiếp tục nhận event và xử lý thay đổi mới trong khi đồng bộ.
6. Có biện pháp chống bỏ sót trong khoảng giữa scan và xử lý event (ví dụ version/snapshot/scan định kỳ).

Không có API nào bảo đảm chỉ gọi `reset()` sẽ **khôi phục những sự kiện đã mất**.

## 9. Đóng watcher, interrupt và hủy registration

### 9.1. `WatchService.close()`

`WatchService` là tài nguyên cần đóng:

```java
try (WatchService watcher =
        directory.getFileSystem().newWatchService()) {
    // Register và vòng nhận sự kiện.
}
```

Gọi `watcher.close()`:

- Đóng watcher.
- Invalidate các key còn liên quan.
- Đánh thức những thread đang chờ `take()` hoặc `poll(timeout)`; chúng có thể nhận **`ClosedWatchServiceException`**.
- Các lần thao tác tiếp theo lên watcher đã đóng cũng có thể ném exception này.
- `close()` của watcher có thể ném `IOException`.

Trong một cơ chế shutdown có chủ đích, exception đóng watcher có thể là tín hiệu dừng **mong đợi**, không nhất thiết là lỗi cần retry. Nhưng không nên bắt mọi `ClosedWatchServiceException` rồi tiếp tục vòng lặp vô hạn.

### 9.2. `InterruptedException`

`take()` và `poll(timeout,unit)` là các phương thức chờ có thể bị interrupt. Trong một worker thread, cách thông thường là:

```java
try {
    watchLoop(watcher);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Thoát hoặc báo trạng thái hủy công việc.
}
```

Đây là **mã minh họa**; `watchLoop` là method ứng dụng khai báo `throws InterruptedException`. Nếu catch `InterruptedException` và quyết định dừng, thường cần **khôi phục interrupt flag** với `Thread.currentThread().interrupt()` trước khi trở về tầng cao hơn.

Đừng luôn `catch (InterruptedException ignore) { }` rồi gọi `take()` lại, vì có thể khiến ứng dụng không dừng đúng khi cancellation được yêu cầu.

### 9.3. `WatchKey.cancel()`

`registration.cancel()` hủy **đăng ký** tương ứng; `registration.isValid()` chuyển thành `false`. Nó **không nhất thiết đóng toàn bộ WatchService** hoặc hủy những registrations khác.

Một key đã được queue **có thể vẫn nằm trong hàng đợi dù vừa cancel**; consumer phải kiểm tra `isValid()` hoặc `reset()` và xử lý thay vì cho rằng queue tức khắc trống.

### 9.4. Tình huống tự hủy

Watch key có thể bị vô hiệu hóa nếu thư mục được theo dõi bị xóa hoặc filesystem không còn truy cập được. Tuy nhiên, sự kiện khi thư mục bị move/rename và `key.watchable()` trỏ đến gì sau đó là **phụ thuộc implementation**; không nên biến một đường dẫn cũ thành sự thật bất biến.

### 9.5. Một mẫu shutdown có chủ đích

Một service thật có thể lưu:

```java
private final AtomicBoolean running = new AtomicBoolean(true);
private final WatchService watcher;
private final Thread watchThread;
```

Khi dừng:

```java
running.set(false);
watchThread.interrupt();
watcher.close();
```

Đây là **phác thảo class-level**, không phải lớp Java hoàn chỉnh. Cần quản lý lifecycle tránh gọi start/stop nhiều lần, đóng watcher trong `finally` hoặc `try-with-resources`, và chờ worker hoàn tất nếu sản phẩm yêu cầu.

Nếu dùng `poll(timeout)`, có thể giảm nhu cầu đóng watcher chỉ để đánh thức bằng cách kiểm tra flag theo nhịp; nếu dùng `take()`, interrupt/close giúp thoát thay vì đợi một sự kiện tương lai.

## 10. Vòng nhận nhiều thư mục: không nhầm một key với cả watcher

Một `WatchService` có thể quản lý nhiều `WatchKey`, mỗi key tương ứng một registration. Khi nhiều thư mục được đăng ký, consumer cần biết key nào thuộc thư mục nào:

```java
Map<WatchKey, Path> directories = new HashMap<>();

WatchKey firstKey = firstDirectory.register(
        watcher, StandardWatchEventKinds.ENTRY_CREATE);

WatchKey secondKey = secondDirectory.register(
        watcher, StandardWatchEventKinds.ENTRY_CREATE);

directories.put(firstKey, firstDirectory);
directories.put(secondKey, secondDirectory);
```

Đây là **mã minh họa**, cần import `Map`/`HashMap`/`WatchKey` và các path hợp lệ.

Khi nhận:

```java
WatchKey key = watcher.take();
Path directory = directories.get(key);

for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        // Quét lại directory phù hợp.
        continue;
    }
    Path name = (Path) event.context();
    Path affected = directory.resolve(name);
    // Xử lý affected.
}

boolean valid = key.reset();
if (!valid) {
    directories.remove(key);
}
```

Đây là minh họa cho một vòng lặp lớn hơn, có xử lý trường hợp `directory == null` khi key không thuộc map và policy rescan/hủy.

**Nếu một key invalid, không mặc định phải dừng theo dõi tất cả key.** Khi map vẫn còn registration khác, vòng nhận sự kiện có thể tiếp tục. Nếu không còn registration nào, dừng watcher hoặc ngừng worker theo thiết kế.

### 10.1. Theo dõi cây thư mục không tự đệ quy

`directory.register(watcher, ...)` đăng ký **thư mục đó**, không mặc định mọi thư mục con. Một file mới tại `root/docs/a.txt` không nhất thiết tạo event ở registration của `root` nếu `docs` là một thư mục con.

Nếu muốn theo dõi toàn bộ cây:

1. Duyệt các thư mục con hiện hữu để đăng ký **mỗi directory**.
2. Khi nhận `ENTRY_CREATE` cho một thư mục mới, xác minh nó rồi đăng ký thư mục ấy.
3. Xử lý race: file có thể được tạo bên trong thư mục mới **trước khi registration con hoàn thành**; cần scan lại nếu muốn index đầy đủ.
4. Khi thư mục bị xóa, hủy/loại key invalid.
5. Có chiến lược giới hạn số registrations và tài nguyên OS.

Không tự suy ra `**` của `glob` là một tùy chọn đệ quy của WatchService; đó là hai cơ chế khác nhau.

## 11. Nền tảng và độ tin cậy của sự kiện

### 11.1. Tính implementation-dependent

API `WatchService` có thể map đến native notification facility hoặc cách polling nội bộ khi không có native facility. Do đó:

- **Độ trễ sự kiện** có thể khác.
- **Thứ tự sự kiện** không được bảo đảm đồng nhất trên mọi OS/provider.
- Một hành động nghiệp vụ có thể tạo nhiều event.
- Một số sự kiện nhanh có thể được gộp hoặc không được phát hiện bởi một triển khai polling thưa.
- Sửa file từ hệ thống từ xa trên network filesystem có thể không được hỗ trợ phát hiện.
- Tràn event queue có thể tạo `OVERFLOW`.

Không nên xây dựng bảo đảm “mọi file tạo sẽ tạo đúng một `ENTRY_CREATE` trong 100 ms” dựa trên một lần chạy trên máy phát triển.

### 11.2. Watcher có thể nhận thay đổi trước khi file hoàn tất

Như `ENTRY_MODIFY` đã nêu, file có thể còn đang được ghi. Để xử lý dữ liệu đáng tin cậy, cần thiết kế hợp đồng **producer–consumer**. Ví dụ producer ghi `report.partial`, đóng stream thành công rồi rename sang `report.ready`; consumer chỉ xử lý `.ready` sau khi kiểm tra nội dung, quyền và tính nhất quán.

Không nên chỉ chờ một khoảng cố định 50 ms rồi tuyên bố file đã hoàn chỉnh trên mọi máy; storage/network có thể chậm hơn nhiều.

### 11.3. WatchService không phải lịch sử thay đổi lâu dài

WatchService không phải durable message queue, journal hoặc nguồn sự thật của tất cả file từ quá khứ. Nó không tự cung cấp:

- Các thay đổi trước khi đăng ký.
- Log giao dịch để replay sau khi JVM crash.
- Đảm bảo phát hiện tất cả thay đổi dù ứng dụng tắt lâu.
- Checkpoint bảo đảm exactly-once.
- Trạng thái nhất quán của toàn bộ cây.
- Authorization để mở file được báo.

Nếu cần index chính xác, kết hợp **quét hiện trạng ban đầu và quét đối soát định kỳ** với watcher để phản ứng nhanh giữa các lần quét.

### 11.4. Nên coi event là “tín hiệu cần kiểm tra lại”

Một kiến trúc bền vững thường nhận `WatchEvent` như “đường dẫn này **có thể đã thay đổi**” rồi kiểm tra hiện trạng thực tế:

```text
WatchEvent
    |
Lấy path tương đối từ context
    |
Ghép với thư mục được watch
    |
Áp quyền và quy tắc root/escape
    |
Kiểm tra file hiện tại / metadata / trạng thái ready
    |
Cập nhật index hoặc enqueue công việc
```

Sự kiện `ENTRY_DELETE` không chứng minh file còn hay mất ở đúng lúc xử lý: một chương trình khác có thể đã tạo lại cùng tên. Tương tự, nhiều event MODIFY không đồng nghĩa có nhiều phiên bản nội dung cần xử lý riêng.

## 12. Chương trình Java 17+ độc lập: `take`, `poll`, timed poll, reset và cancel

Chương trình hoàn chỉnh sau tạo một **thư mục tạm riêng** và hai thư mục con:

- `blocking`: ví dụ `take()` chờ `ENTRY_CREATE` từ một thread tạo file sau 150 ms.
- `polling`: ví dụ `poll()` kiểm tra queue rỗng, tạo file, dùng `poll(5, SECONDS)` để nhận key, kiểm tra lần `poll()` sau khi rút event, thử timeout, sau đó hủy registration.
- Cả hai đều dùng **`pollEvents()` trước `reset()`**, kiểm tra context tên tương đối và xử lý `OVERFLOW` như một tình huống cần fail/rescan trong demo.
- Dữ liệu được tạo và xóa **chỉ bên trong workspace tạm của chương trình**.
- Stdout chỉ in boolean, không dựa vào tên đường dẫn ngẫu nhiên.

**Lưu ý về tính portable:** Chương trình đòi hỏi filesystem provider hỗ trợ WatchService và phát hiện event tạo file trong các thư mục thử. JDK đầy đủ trên filesystem thông thường có hỗ trợ; nhưng với provider/remote storage không phát event hoặc phát hiện quá chậm, ví dụ có thể timeout ở timed poll hoặc đứng đợi `take()`. Đây là giới hạn môi trường đã được nêu trong API, không phải lời hứa mọi provider đều đáp ứng đúng thời gian.

Lưu tệp **`WatchServiceTakePollDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static java.nio.file.StandardWatchEventKinds.ENTRY_CREATE;
import static java.nio.file.StandardWatchEventKinds.OVERFLOW;

public final class WatchServiceTakePollDemo {

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    static boolean sawExpectedCreate(WatchKey key, String expected) {
        boolean found = false;

        for (WatchEvent<?> event : key.pollEvents()) {
            if (event.kind() == OVERFLOW) {
                throw new IllegalStateException(
                        "Event overflow; rescan required");
            }

            if (event.kind() == ENTRY_CREATE) {
                Path name = (Path) event.context();

                if (!name.isAbsolute()
                        && name.equals(Path.of(expected))) {
                    found = true;
                }
            }
        }

        if (!key.reset()) {
            throw new IllegalStateException(
                    "Watched directory is no longer valid");
        }

        return found;
    }

    static void takeExample(Path directory) throws Exception {
        try (WatchService watcher =
                directory.getFileSystem().newWatchService()) {

            directory.register(watcher, ENTRY_CREATE);

            AtomicReference<Throwable> writerError =
                    new AtomicReference<>();

            Thread writer = new Thread(() -> {
                try {
                    Thread.sleep(150);

                    Files.writeString(
                            directory.resolve("blocking.txt"),
                            "created", StandardCharsets.UTF_8);
                } catch (Throwable error) {
                    writerError.set(error);
                }
            }, "demo-file-creator");

            writer.start();

            boolean found = false;

            while (!found) {
                WatchKey key = watcher.take();
                found = sawExpectedCreate(key, "blocking.txt");
            }

            writer.join();

            check(writerError.get() == null,
                    "producer failed: " + writerError.get());

            System.out.println("take.sawCreate=" + found);
        }
    }

    static void pollExample(Path directory) throws Exception {
        try (WatchService watcher =
                directory.getFileSystem().newWatchService()) {

            WatchKey registration =
                    directory.register(watcher, ENTRY_CREATE);

            boolean initiallyEmpty = watcher.poll() == null;

            Files.writeString(
                    directory.resolve("timed.txt"),
                    "created", StandardCharsets.UTF_8);

            WatchKey received =
                    watcher.poll(5, TimeUnit.SECONDS);

            boolean sawCreate = received != null
                    && sawExpectedCreate(received, "timed.txt");

            boolean nonBlockingEmpty = watcher.poll() == null;

            boolean timedOut =
                    watcher.poll(150, TimeUnit.MILLISECONDS) == null;

            boolean validBeforeCancel = registration.isValid();

            registration.cancel();

            boolean invalidAfterCancel =
                    !registration.isValid();

            System.out.println(
                    "poll.initiallyEmpty=" + initiallyEmpty);
            System.out.println(
                    "poll.sawCreate=" + sawCreate);
            System.out.println(
                    "poll.nowEmpty=" + nonBlockingEmpty);
            System.out.println(
                    "poll.timeoutEmpty=" + timedOut);
            System.out.println(
                    "key.validBeforeCancel=" + validBeforeCancel);
            System.out.println(
                    "key.invalidAfterCancel=" + invalidAfterCancel);

            check(initiallyEmpty && sawCreate && nonBlockingEmpty
                    && timedOut && validBeforeCancel
                    && invalidAfterCancel,
                    "poll assertions");
        }
    }

    static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs)
                    throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException error)
                    throws IOException {
                if (error != null) {
                    throw error;
                }

                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws Exception {
        Path workspace =
                Files.createTempDirectory("watchservice-loop-");

        try {
            Path blocking = Files.createDirectory(
                    workspace.resolve("blocking"));

            Path polling = Files.createDirectory(
                    workspace.resolve("polling"));

            takeExample(blocking);
            pollExample(polling);

            System.out.println("checks=PASS");
        } finally {
            deleteTree(workspace);
        }

        System.out.println(
                "workspace.cleaned=" + !Files.exists(workspace));
    }
}
```

Biên dịch và chạy với **JDK 17+** trên filesystem có hỗ trợ WatchService:

```bash
javac -encoding UTF-8 WatchServiceTakePollDemo.java
java WatchServiceTakePollDemo
```

**Stdout đã được kiểm chứng bằng `javac`/`java` trên môi trường thử nghiệm:**

```text
take.sawCreate=true
poll.initiallyEmpty=true
poll.sawCreate=true
poll.nowEmpty=true
poll.timeoutEmpty=true
key.validBeforeCancel=true
key.invalidAfterCancel=true
checks=PASS
workspace.cleaned=true
```

### 12.1. Giải thích nhóm `take`

`take.sawCreate=true` chứng tỏ thread consumer thực sự nhận được một key chứa event `ENTRY_CREATE` với context `blocking.txt`.

Do chương trình sinh event trong thread khác sau khi watcher đã đăng ký, ví dụ thể hiện được cơ chế `take()` chờ. Tuy nhiên, tốc độ event delivery thực tế vẫn phụ thuộc provider.

### 12.2. Giải thích nhóm `poll`

- `poll.initiallyEmpty=true`: thư mục thử mới đăng ký chưa có watch key trong queue khi kiểm tra lập tức.
- `poll.sawCreate=true`: sau khi tạo `timed.txt`, `poll(5, TimeUnit.SECONDS)` nhận được key chứa event tạo file.
- `poll.nowEmpty=true`: sau khi đã rút event và reset, lần `poll()` tiếp theo không lấy được key nào.
- `poll.timeoutEmpty=true`: nếu không có thay đổi mới, `poll(150, MILLISECONDS)` trả `null` khi hết thời gian chờ.
- `key.validBeforeCancel=true`: registration còn hiệu lực sau khi xử lý/reset.
- `key.invalidAfterCancel=true`: hủy bằng `cancel()` khiến key không còn hợp lệ.
- `checks=PASS`: các boolean quan trọng đáp ứng kiểm tra ở lần chạy.
- `workspace.cleaned=true`: toàn bộ workspace tạm do demo tạo được dọn.

### 12.3. Vì sao chương trình không in số lần event chính xác?

Các hệ điều hành/provider có thể phát event khác nhau, thậm chí gộp sự kiện; yêu cầu rằng “một file mới phải có chính xác một event theo đúng thứ tự và trong 100 ms” **không phải contract chung của WatchService**. Chương trình kiểm tra **điều kiện cần** là có event tạo file đúng context, thay vì bắt buộc event count/order không được đặc tả.

### 12.4. Vì sao demo ném lỗi khi `OVERFLOW`?

Demo nhỏ chỉ dùng một số file, nên nếu có `OVERFLOW` thì phép kiểm tra “đã quan sát đủ các event mong muốn” không còn đáng tin. Nó ném `IllegalStateException` để test không **báo thành công giả**.

Trong ứng dụng thật, nên chuyển sang chiến lược **rescan directory và đối chiếu trạng thái** như mục 8, thay vì chỉ ném lỗi và dừng mọi thứ không có khả năng phục hồi.

### 12.5. Vì sao demo dùng hai thư mục con riêng?

Tách thư mục `blocking` và `polling` giúp event của ví dụ này không ảnh hưởng ví dụ kia. Các file được tạo có tên cố định nhưng nằm trong **workspace tạm mới được tạo mỗi lần chạy**, tránh đụng tệp của người dùng hoặc những lần chạy trước.

## 13. Thiết kế vòng nhận sự kiện trong một dịch vụ thật

### 13.1. Một worker chuyên trách: `take()`

Nếu mục tiêu là indexer phản ứng nhanh khi có sự kiện và không có housekeeping định kỳ:

```text
start()
   |
tạo WatchService, register directories
   |
worker loop:
    key = take()
    |
    xử lý các event, enqueue công việc nặng
    |
    reset key
    |
    còn registrations? -> lặp
   |
close() / interrupt / clean shutdown
```

Ưu điểm của `take()`: không cần thức dậy định kỳ để dò queue rỗng. Hạn chế: nếu ngoài sự kiện còn phải kiểm tra trạng thái định kỳ thì cần một scheduler khác hoặc cơ chế dừng worker.

### 13.2. Một worker có heartbeat: timed `poll`

Nếu cần kiểm tra flag dừng, đồng bộ trạng thái, timeout metric hoặc quét lại theo nhịp:

```java
while (running.get()) {
    WatchKey key = watcher.poll(1, TimeUnit.SECONDS);

    if (key == null) {
        heartbeat();
        continue;
    }

    processEvents(key);
    if (!key.reset()) {
        unregister(key);
    }
}
```

Đây là **pseudocode Java minh họa**, không phải lớp chạy độc lập: `running`, `heartbeat()`, `processEvents()` và `unregister()` thuộc ứng dụng.

Ưu điểm: có nhịp thức dậy mỗi tối đa một giây để làm việc khác. Hạn chế: nếu gọi `heartbeat()` hoặc `processEvents()` quá lâu trên chính worker, sự kiện sẽ tồn đọng; cần tách việc xử lý nặng sang executor/queue phù hợp.

### 13.3. Event loop có nhiều nguồn công việc: `poll()`

Một scheduler xử lý cả network/job queue và event filesystem có thể gọi `poll()` **theo nhịp sẵn có**, miễn không busy-wait. Nếu việc theo dõi filesystem là nhiệm vụ chính duy nhất, `take()` hoặc timed poll thường đơn giản và tiết kiệm CPU hơn.

### 13.4. Không block nhận key bằng công việc xử lý nặng

Một ứng dụng xử lý file lớn trong chính `for (WatchEvent<?> event : key.pollEvents())` có thể khiến quá trình nhận key bị chậm, tăng nguy cơ `OVERFLOW`.

Một mô hình tốt hơn:

1. Worker WatchService **lấy và phân loại event nhanh**.
2. Chuyển đường dẫn cần kiểm tra vào hàng đợi công việc của ứng dụng.
3. Dùng executor với concurrency/queue limit phù hợp.
4. Đưa các event trùng path về một công việc tổng hợp nếu nghiệp vụ cho phép.
5. Xử lý backpressure và rescan khi queue đầy hoặc `OVERFLOW`.
6. Đóng watcher và worker theo vòng đời của service.

Không suy rằng chỉ cần tăng số consumer thread lên vô hạn sẽ tăng độ tin cậy: nhiều thread có thể tranh xử lý cùng registration và phải đồng bộ thứ tự `reset()`.

## 14. Lỗi thường gặp và cách khắc phục

| Sai lầm | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| Dùng `poll()` trong vòng `while(true)` không chờ | Tạo **busy-wait**, tốn CPU | `take()` hoặc `poll(timeout)` |
| Coi `take()` trả từng file event | Nó trả **WatchKey** | Duyệt `key.pollEvents()` |
| Lấy event xong nhưng không gọi `key.reset()` | Key có thể không quay lại trạng thái ready | Reset **sau xử lý** |
| Reset ngay trước khi xử lý | Dễ mất phối hợp giữa nhiều consumers | Xử lý event xong rồi reset |
| Bỏ qua boolean của `reset()` | Registration invalid nhưng vòng lặp vẫn coi hợp lệ | Khi false thì bỏ key/dừng phù hợp |
| Tưởng `poll()==null` nghĩa là thư mục không có file | Chỉ nói queue hiện tại không có key | Scan trạng thái nếu cần |
| Tưởng timed poll timeout là I/O error | Timeout là kết quả bình thường `null` | Housekeeping hoặc tiếp tục |
| Bắt `InterruptedException` rồi nuốt | Worker khó dừng theo cancellation | Khôi phục interrupt flag, thoát |
| Bắt `ClosedWatchServiceException` rồi retry vô hạn | Watcher đã đóng, không hoạt động nữa | Dừng/shutdown đúng |
| Cho rằng `cancel()` đóng cả service | Cancel chỉ hủy registration | Đóng `WatchService` riêng |
| Thấy `ENTRY_CREATE` và coi file sẵn sàng | Producer có thể chưa ghi xong | File-ready protocol/rename/check |
| Tin mỗi MODIFY đúng một lần | Có thể gộp/nhân nhiều event | Xử lý idempotent/debounce |
| Bỏ qua `OVERFLOW` | Có thể đã mất sự kiện | Rescan đối chiếu |
| Cast context thành `Path` trước khi xét kind | `OVERFLOW` không dùng cùng ngữ nghĩa | Kiểm tra kind trước |
| Coi context là absolute path | Context là path **tương đối** | Resolve với directory tương ứng |
| Đăng ký root rồi tưởng tự watch mọi subtree | WatchService không tự theo dõi cây đệ quy | Register từng thư mục |
| Xem `WatchService` là durable event journal | Không hứa replay sau crash | Scan ban đầu/định kỳ và reconcile |
| Dùng event path làm bằng chứng quyền truy cập | Event không làm authorization | Kiểm tra root/quyền/I/O |
| Không đóng watcher | Rò tài nguyên file watcher | `try-with-resources` hoặc close có chủ đích |
| Hard-code thời gian event trong test | Phụ thuộc provider/OS | Kiểm tra điều kiện, timeout hợp lý |

## 15. Kiểm thử vòng nhận sự kiện

### 15.1. Những tình huống tối thiểu

| Kiểm thử | Mục tiêu |
| --- | --- |
| `poll()` trên watcher mới | Trả `null` khi queue rỗng |
| `take()` với producer ở thread khác | Không busy-wait và nhận key khi có sự kiện |
| `poll(timeout)` với producer | Nhận key trong điều kiện provider phát hiện |
| `poll(timeout)` không có producer | Trả `null` sau khoảng chờ |
| `pollEvents()` sau khi lấy key | Đọc được các sự kiện của registration |
| `reset()` | Key tiếp tục hợp lệ khi thư mục còn tồn tại |
| `cancel()` | Key trở nên invalid |
| Event context | Tên tương đối so với watched directory |
| `OVERFLOW` | Có logic rescan và trạng thái partial |
| Interrupt worker đang chờ | Vòng nhận thoát và bảo toàn interrupt flag |
| Close watcher từ thread khác | Consumer chờ nhận `ClosedWatchServiceException` |
| Xóa thư mục đang watch | Key có thể invalid; chính sách xử lý |
| Nhiều thư mục | Map key → directory đúng |
| Thư mục con được tạo mới | Có register bổ sung nếu muốn recursive |
| `ENTRY_MODIFY` lặp | Handler idempotent, không tin file đã hoàn chỉnh |
| Crash/restart | Quét hiện trạng để đồng bộ lại |

### 15.2. Test không nên khẳng định một số lượng event cố định

`watcher.pollEvents()` có thể chứa khác số lượng/thứ tự giữa OS hoặc provider. Test nên tìm **đúng loại event và đúng context**, không assert rằng `events.size()==1` cho mọi thao tác tạo/ghi/xóa.

Đối với lệnh `poll(timeout)`, test cần một **timeout đủ rộng** và một filesystem thực có hỗ trợ; trong môi trường CI/remote mount, phải tránh treo không giới hạn và có thể cần bỏ qua integration test khi provider không hỗ trợ semantics mong muốn.

### 15.3. Kiểm thử shutdown và overflow

Không cần tạo hàng triệu file trên ổ đĩa thật chỉ để ép `OVERFLOW`. Có thể tách logic xử lý event vào method/unit-testable component và dùng fake events hoặc abstraction phù hợp để thử nhánh rescan.

Cũng nên thử:

- Worker bị interrupt khi đang đợi key.
- Watcher bị đóng khi worker còn trong `take()`.
- Key bị cancel nhưng vẫn còn trong queue.
- Exception từ handler mà không làm mất trách nhiệm reset/cleanup.
- Nhiều thay đổi trên cùng file trong thời gian ngắn.
- Directory bị thay tên hoặc mất truy cập.

## 16. Câu hỏi ôn tập

**Câu 1.** `WatchService.take()` có giống `WatchService.poll()` không?  
**Đáp án:** Không. `take()` chờ khi queue rỗng, còn `poll()` không chờ và có thể trả `null` ngay.

**Câu 2.** `poll(2, TimeUnit.SECONDS)` khác `take()` ở đâu?  
**Đáp án:** Timed poll chỉ chờ tối đa hai giây rồi có thể trả `null`; `take()` không có timeout được truyền vào.

**Câu 3.** Kết quả của ba phương thức này là `WatchEvent` hay `WatchKey`?  
**Đáp án:** Là **`WatchKey`**; muốn lấy event của key thì dùng `key.pollEvents()`.

**Câu 4.** Vì sao phải gọi `key.reset()` sau khi xử lý?  
**Đáp án:** Để key có thể quay về trạng thái ready/được queue lại cho các thay đổi tiếp theo.

**Câu 5.** `reset()` trả `false` nghĩa là gì?  
**Đáp án:** Registration không còn hợp lệ. Cần bỏ key hoặc dừng tương ứng thay vì tiếp tục xử lý như bình thường.

**Câu 6.** `poll() == null` có chứng minh thư mục rỗng không?  
**Đáp án:** Không. Nó chỉ nói không có key nào đang chờ trong service queue lúc kiểm tra.

**Câu 7.** `ENTRY_MODIFY` có chứng minh file đã ghi xong không?  
**Đáp án:** Không. Người ghi có thể vẫn đang cập nhật; cần chính sách file-ready/đối soát.

**Câu 8.** Khi có `OVERFLOW`, chỉ gọi `reset()` đã phục hồi đủ các event chưa?  
**Đáp án:** Chưa. Phải đánh dấu có thể mất event và thường cần scan lại trạng thái filesystem thực tế.

**Câu 9.** `event.context()` của `ENTRY_CREATE` là gì?  
**Đáp án:** `Path` tương đối từ thư mục được watch đến entry mới. Ghép với `(Path)key.watchable()` để tạo đường dẫn đầy đủ trong thư mục ấy.

**Câu 10.** Đăng ký thư mục `root` có tự theo dõi tất cả thư mục con không?  
**Đáp án:** Không. Muốn recursive cần quản lý thêm registrations cho từng thư mục và xử lý race.

**Câu 11.** Khi thread đang trong `take()`, gọi `watcher.close()` từ thread khác sẽ ra sao?  
**Đáp án:** Theo API, các thread đợi key sẽ nhận `ClosedWatchServiceException`.

**Câu 12.** `cancel()` và `close()` có giống nhau không?  
**Đáp án:** Không. `cancel()` hủy một registration; `close()` đóng toàn bộ WatchService và invalid các keys.

**Câu 13.** Tại sao không nên chỉ dùng WatchService để bảo đảm index file chính xác tuyệt đối?  
**Đáp án:** Event có thể bị gộp, mất khi overflow, chậm hoặc không hỗ trợ đầy đủ trên remote storage; cần scan ban đầu/định kỳ và cơ chế đối soát.

**Câu 14.** Khi nào nên chọn timed poll thay vì take?  
**Đáp án:** Khi cùng thread còn cần kiểm tra flag shutdown, heartbeat hoặc công việc định kỳ mà không muốn chờ vô thời hạn.

## 17. Checklist triển khai

- [ ] Dùng `newWatchService()` của đúng filesystem provider.
- [ ] Đăng ký directory thực với `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE` theo nhu cầu.
- [ ] Phân biệt **WatchKey queue** và danh sách `WatchEvent` của key.
- [ ] Chọn `take()` cho worker chuyên chờ, hoặc `poll(timeout)` nếu cần thức dậy định kỳ.
- [ ] Không tạo vòng `poll()` spin không có nhịp/scheduler.
- [ ] Khi `poll()==null`, không suy rằng directory không có file.
- [ ] Đọc `key.pollEvents()`, xử lý kind/context/count đúng nghĩa.
- [ ] Xử lý `OVERFLOW` bằng rescan/reconcile.
- [ ] Gọi `key.reset()` **sau xử lý**, kiểm tra `false`.
- [ ] Nếu có nhiều keys, lưu ánh xạ key → directory, bỏ từng key invalid riêng.
- [ ] Xử lý `InterruptedException` và `ClosedWatchServiceException` khi shutdown.
- [ ] Đóng WatchService theo vòng đời bằng `try-with-resources`/`close()`.
- [ ] Không coi `ENTRY_MODIFY` là file-ready hoặc exactly-once.
- [ ] Đã xác định theo dõi **một thư mục** hay cần quản lý **cả cây đệ quy**.
- [ ] Áp chính sách filesystem permissions, symbolic link, root, path traversal.
- [ ] Có scan ban đầu và đối soát định kỳ khi yêu cầu tính đầy đủ.
- [ ] Test create/modify/delete, timeout, interrupt, cancel, invalid key và overflow.
- [ ] Không hard-code event ordering, count hay latency thành bảo đảm chung.

## 18. Kết luận và tài liệu Java chính thức

**Vòng nhận `WatchService` đúng không chỉ là một lệnh `take()` hoặc `poll()`.** Cần hiểu cả lifecycle của `WatchKey`:

```text
take() / poll() / poll(timeout)
              |
           WatchKey
              |
          pollEvents()
              |
    xử lý kind, count, context,
    OVERFLOW, quyền truy cập, file-ready
              |
           reset()
              |
      key còn hợp lệ?
              |
        tiếp tục hoặc dừng
```

Chọn:

- **`take()`** nếu thread chuyên đợi event, không cần nhịp timeout.
- **`poll()`** nếu event loop đã có công việc/scheduler khác và kiểm tra queue không chờ.
- **`poll(timeout, TimeUnit)`** nếu muốn đợi có giới hạn để xử lý heartbeat, cancellation hoặc housekeeping.

Tất cả đều trả **`WatchKey`**; phải duyệt `pollEvents()` và gọi `reset()` sau xử lý. Với thay đổi quan trọng, dùng WatchService để **phát hiện sớm** và dùng quét/đối soát trạng thái thật để **khôi phục độ đầy đủ** khi cần.

### Tài liệu còn hiệu lực

- [Oracle Java SE 17 — `WatchService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): `take`, `poll`, timed poll, `close`, giới hạn nền tảng.
- [Oracle Java SE 17 — `WatchKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html): `pollEvents`, `reset`, `cancel`, `isValid`, trạng thái ready/signalled.
- [Oracle Java SE 17 — `WatchEvent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html): `kind`, `count`, `context` và đường dẫn tương đối.
- [Oracle Java SE 17 — `StandardWatchEventKinds`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE`, `OVERFLOW`.
- [Oracle Java SE 17 — `Path.register`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#register(java.nio.file.WatchService,java.nio.file.WatchEvent.Kind...)): cách đăng ký directory.
- [Oracle Java SE 17 — `FileSystem.newWatchService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html#newWatchService()): tạo watcher trên provider.
- [Dev.java — Watching a Directory for Changes](https://dev.java/learn/api/io/java-io/file-system/watching/): hướng dẫn dùng WatchService trong Java hiện hành.
