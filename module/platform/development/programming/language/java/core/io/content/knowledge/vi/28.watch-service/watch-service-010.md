# Đóng WatchService và dừng luồng chờ trong Java NIO.2

## 1. Vấn đề: luồng theo dõi thư mục có thể chờ vô hạn

`WatchService` thuộc `java.nio.file` cho phép ứng dụng nhận thông báo khi các mục trong một thư mục thay đổi, ví dụ tạo, xóa hoặc sửa tệp. Một chương trình theo dõi thường chạy vòng lặp ở một thread:

```java
while (running) {
    WatchKey key = watcher.take();
    // Xử lý event...
    key.reset();
}
```

Đoạn trên là **mã minh họa chưa độc lập**, giả định `watcher` là `WatchService`, `running` do ứng dụng quản lý. `take()` **chặn** khi chưa có key nào được báo sự kiện. Nếu ứng dụng chỉ đặt `running = false` lúc cần tắt, luồng đang đứng ở `take()` có thể không bao giờ quay lại để kiểm tra biến này.

Bài học tập trung vào hai hành động phải phối hợp:

1. **Dừng chờ và dừng vòng lặp xử lý sự kiện** theo một cơ chế được API hỗ trợ.
2. **Đóng `WatchService` để giải phóng tài nguyên** và vô hiệu hóa các đăng ký (`WatchKey`) còn liên quan.

Cách shutdown thông thường, khi đã quyết định không dùng lại dịch vụ theo dõi, là **gọi `watcher.close()` từ luồng điều khiển**, bắt `ClosedWatchServiceException` ở luồng chờ để kết thúc vòng lặp, rồi `join()` để xác nhận luồng đã thoát. Khi cần giữ dịch vụ mở, một phương án khác là `Thread.interrupt()` hoặc `poll(timeout)`, nhưng mỗi cách có ý nghĩa và hệ quả riêng.

### 1.1. Bốn đối tượng cần phân biệt

| Thành phần | Vai trò |
|---|---|
| `WatchService` | Dịch vụ nhận và xếp hàng các key có sự kiện, quản lý đăng ký |
| `WatchKey` | Token của đăng ký một đối tượng theo dõi, thông thường là thư mục |
| `WatchEvent<?>` | Một sự kiện cụ thể lấy qua `key.pollEvents()` |
| Thread theo dõi | Luồng do ứng dụng tạo, gọi `take()`/`poll(...)` và xử lý các key |

**Đóng WatchService không phải API kill thread.** Nó khiến thao tác chờ trên dịch vụ bị đánh thức bằng ngoại lệ và làm các key không hợp lệ; thread vẫn phải có logic thoát. Nếu thread đang xử lý nghiệp vụ lâu hoặc đang chặn ở API khác, `close()` của WatchService không đảm bảo dừng tức thì các công việc đó.

## 2. Luồng hoạt động bình thường trước khi shutdown

Để theo dõi một thư mục:

```java
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;

Path directory = Path.of("incoming");

try (WatchService watcher =
        FileSystems.getDefault().newWatchService()) {

    WatchKey registration = directory.register(
            watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_DELETE,
            StandardWatchEventKinds.ENTRY_MODIFY);

    // Chương trình xử lý sự kiện ở đây.
}
```

Đây là **đoạn minh họa trong phương thức có `throws IOException`**; cần thư mục `incoming` tồn tại và provider hỗ trợ các event này. `try-with-resources` bảo đảm gọi `watcher.close()` khi rời scope. Nếu đã tạo một thread riêng đang gọi `watcher.take()`, việc đóng service cần kết hợp với chờ thread thoát, không chỉ đóng ở cuối scope mà bỏ mặc thread.

Thông thường:

```text
directory.register(...) ──► WatchKey (trạng thái ready)
                                 │
                        phát hiện thay đổi
                                 ▼
                           key signalled
                                 │
                watcher.take() lấy key được báo
                                 │
                        key.pollEvents()
                                 │
                         xử lý các event
                                 │
                          key.reset()
                                 │
                    chờ sự kiện tiếp theo
```

Theo contract, sau khi một key được báo (`signalled`), nó cần `reset()` sau khi xử lý để trở lại trạng thái chờ tín hiệu mới. Nếu bỏ `reset()`, key có thể không được xếp hàng lại như mong đợi dù sự kiện vẫn tích lũy. `key.pollEvents()` rút các event hiện có ra khỏi key; không có nghĩa hủy đăng ký.

### 2.1. API lấy key và trạng thái khi chưa có event

| Phương thức | Khi chưa có key | Có thể bị ngắt? | Khi WatchService đã đóng |
|---|---|---|---|
| `watcher.take()` | Chờ cho đến khi có key hoặc bị đánh thức theo quy tắc API | Có, ném `InterruptedException` | Ném `ClosedWatchServiceException` |
| `watcher.poll()` | Trả `null` ngay | Không chờ theo thời gian | Ném `ClosedWatchServiceException` |
| `watcher.poll(timeout, unit)` | Chờ tối đa thời gian yêu cầu; nếu hết hạn trả `null` | Có, ném `InterruptedException` | Ném `ClosedWatchServiceException` |

Đây là điểm mấu chốt khi shutdown: `take()` không bị ảnh hưởng bởi một biến boolean mà ứng dụng vừa đổi; muốn thread rời trạng thái chặn, bạn phải tác động đến **thao tác chờ** (`close` hoặc `interrupt`), hoặc không dùng chờ vô hạn ngay từ đầu (`poll(timeout)`).

## 3. `WatchService.close()`: cách kết thúc dịch vụ theo dõi

Contract của `WatchService.close()` (Java 17/21):

- Đóng dịch vụ theo dõi và giải phóng tài nguyên liên quan.
- Nếu có thread đang chặn trong `take()` hoặc `poll(timeout)` để chờ key, thread đó được **đánh thức** bằng `ClosedWatchServiceException`.
- Các `WatchKey` còn hợp lệ gắn với dịch vụ bị **vô hiệu hóa**.
- Sau khi service đã đóng, những thao tác khác trên service như `take()`, `poll()` hoặc đăng ký mới đều không còn hợp lệ và có thể ném `ClosedWatchServiceException`.
- Gọi `close()` trên service đã đóng **không có tác dụng thêm** (idempotent).
- `close()` có chữ ký `throws IOException`; caller vẫn phải xử lý lỗi đóng trong những tình huống bất thường.

Cách dùng tối thiểu:

```java
WatchService watcher = FileSystems.getDefault().newWatchService();

Thread worker = new Thread(() -> {
    try {
        for (;;) {
            WatchKey key = watcher.take();
            // Xử lý key khi còn hoạt động.
            if (!key.reset()) {
                break;
            }
        }
    } catch (ClosedWatchServiceException ex) {
        // Kết thúc bình thường khi controller đóng WatchService.
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        // Kết thúc theo yêu cầu ngắt.
    }
});

worker.start();

// Ở một luồng khác khi cần shutdown:
watcher.close();
worker.join();
```

Đây là **đoạn minh họa** cần các import và phạm vi `throws IOException, InterruptedException`. Nó tập trung vào tín hiệu shutdown, chưa phải implementation xử lý event đầy đủ. Khi service đóng, `take()` bị đánh thức hoặc, nếu nó chưa kịp gọi `take()`, lần gọi tiếp theo phát hiện service đã đóng. Trong cả hai trường hợp, vòng lặp phải bắt `ClosedWatchServiceException` để thoát mà không log shutdown bình thường thành lỗi bất ngờ.

### 3.1. `ClosedWatchServiceException` là unchecked

`ClosedWatchServiceException` kế thừa `IllegalStateException`, không phải `IOException` hay `InterruptedException`. Vì vậy, một khối:

```java
try {
    watcher.take();
} catch (IOException ex) {
    // KHÔNG bắt được ClosedWatchServiceException.
}
```

Đoạn minh họa trên còn có vấn đề biên dịch ở vài ngữ cảnh vì `WatchService.take()` không khai báo `IOException`; nó chỉ nhằm chỉ ra **đừng bắt nhầm loại ngoại lệ**, không được chép như một ví dụ độc lập. Cách đúng:

```java
try {
    WatchKey key = watcher.take();
    // Xử lý key.
} catch (ClosedWatchServiceException ex) {
    // Dịch vụ đã đóng, thoát vòng theo dõi.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Thread bị yêu cầu ngắt; thoát hoặc xử lý theo policy.
}
```

Đây là snippet có thể đặt trong method đã khai báo `watcher` và import `java.nio.file.ClosedWatchServiceException` cùng `WatchKey`. Nếu bất ngờ log toàn bộ `ClosedWatchServiceException` như failure cấp cao, ứng dụng có thể ghi báo động sai mỗi lần được shutdown hợp lệ.

### 3.2. `close()` không phải “gửi một WatchEvent shutdown”

`close()` không tạo một `ENTRY_DELETE` hoặc `OVERFLOW` giả để đưa vào `key.pollEvents()`. Tín hiệu shutdown đi qua **trạng thái dịch vụ đóng / ngoại lệ trên phương thức chờ**, không phải một event nghiệp vụ.

Hệ quả: code xử lý event không nên cố suy luận shutdown bằng cách chờ một tệp “stop.signal” xuất hiện. Đó là một giao thức khác, có thể không nhận event hoặc bị trễ; `close()` là tín hiệu trực tiếp của API phù hợp khi sẽ không tái sử dụng WatchService.

## 4. Ví dụ Java 17+ độc lập: đóng dịch vụ đánh thức luồng `take()`

Ví dụ tạo thư mục tạm, đăng ký nhận event tạo tệp, khởi chạy thread gọi `take()`, sau đó đóng service từ thread main. Kết quả được lưu trong `AtomicReference` và **chỉ in sau khi `join()` thành công**, nhờ đó thứ tự stdout không phụ thuộc scheduler. Không cần tạo file để “đánh thức” watcher.

**Tệp:** `WatchCloseDemo.java`

```java
import java.nio.file.ClosedWatchServiceException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchService;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class WatchCloseDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watch-close-");

        try {
            try (WatchService watcher =
                    FileSystems.getDefault().newWatchService()) {

                directory.register(
                        watcher, StandardWatchEventKinds.ENTRY_CREATE);

                CountDownLatch aboutToWait = new CountDownLatch(1);
                AtomicReference<String> result =
                        new AtomicReference<>("not finished");

                Thread worker = new Thread(() -> {
                    aboutToWait.countDown();

                    try {
                        watcher.take();
                        result.set("key received");
                    } catch (ClosedWatchServiceException ex) {
                        result.set("service closed");
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        result.set("interrupted");
                    }
                }, "watch-worker");

                // Chỉ là hàng rào an toàn của demo khi có lỗi môi trường.
                // Daemon KHÔNG thay thế close/join trong ứng dụng thật.
                worker.setDaemon(true);
                worker.start();

                // Biết worker sắp gọi take, nhưng chưa chắc đã chặn.
                aboutToWait.await();

                // Đây là tín hiệu shutdown thật sự.
                watcher.close();

                worker.join(5000);
                if (worker.isAlive()) {
                    throw new IllegalStateException(
                            "watcher did not stop");
                }

                System.out.println("watcher stopped: "
                        + !worker.isAlive());
                System.out.println("result: " + result.get());

                try {
                    watcher.take();
                } catch (ClosedWatchServiceException ex) {
                    System.out.println(
                            "take after close: ClosedWatchServiceException");
                }
            }
        } finally {
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac WatchCloseDemo.java
java WatchCloseDemo
```

**Stdout dự kiến trong môi trường filesystem bình thường:**

```text
watcher stopped: true
result: service closed
take after close: ClosedWatchServiceException
```

**Giải thích kỹ từng bước:**

1. `Files.createTempDirectory` tạo nơi đăng ký sự kiện thật, không trùng với thư mục dự án.
2. `directory.register(watcher, ENTRY_CREATE)` tạo `WatchKey`. Chương trình **không tạo tệp trong thư mục**, vì mục tiêu là minh họa `take()` có thể đứng chờ khi không có event.
3. `CountDownLatch` thông báo worker đã tới gần lệnh `take()`; nó **không chứng minh** worker đang chặn. Ví dụ vẫn đúng nếu main đóng service trước khi worker thực sự gọi `take()`.
4. Main gọi `watcher.close()`. Nếu worker đang chặn, nó được đánh thức bằng `ClosedWatchServiceException`. Nếu chưa chặn, `take()` sau đó cũng gặp service đã đóng.
5. Worker bắt ngoại lệ và ghi kết quả `service closed`, không giữ vòng lặp vô hạn.
6. `join(5000)` đợi worker kết thúc tối đa khoảng 5 giây; nếu không kết thúc, ví dụ báo lỗi thay vì khẳng định thành công. Trong điều kiện bình thường với demo đơn giản này, worker dừng ngay.
7. In kết quả **sau join** nên không có race về thứ tự giữa stdout worker/main. Lần gọi `take()` thêm sau khi đóng chứng minh service không còn sử dụng được.
8. `try-with-resources` đóng lại service ở cuối (đóng lặp là không có tác dụng). `finally` xóa thư mục tạm.

Ví dụ đã được kiểm tra với JDK trên môi trường hỗ trợ WatchService. Nếu môi trường đặc biệt không hỗ trợ đăng ký sự kiện hoặc I/O thất bại, ngoại lệ sẽ được báo ra thay vì bịa stdout “thành công”.

### 4.1. Vì sao không cần tạo tệp để đánh thức `take()`?

Tạo một tệp chỉ tạo **event nghiệp vụ** có thể làm `take()` trả về `WatchKey` bình thường. Đó không phải tín hiệu kết thúc toàn bộ dịch vụ; sau khi xử lý và `reset()`, watcher có thể chờ tiếp vô hạn.

`close()` khác ở chỗ nó kết thúc dịch vụ, làm key bị vô hiệu và ngăn thao tác tiếp. Đây là lựa chọn hợp lý khi ứng dụng đang tắt hoặc watcher không còn được sử dụng.

## 5. So sánh `close()`, `interrupt()`, `cancel()` và timeout

Các kỹ thuật dừng phổ biến không tương đương:

| Kỹ thuật | Có đánh thức `take()` đang chặn? | WatchService còn mở? | WatchKey còn hợp lệ? |
|---|---|---|---|
| `watcher.close()` | Có; nhận `ClosedWatchServiceException` | Không | Các key liên quan bị vô hiệu |
| `worker.interrupt()` | Có; nhận `InterruptedException` nếu đang chờ theo kiểu interruptible | Có, trừ khi code tự đóng | Thông thường vẫn hợp lệ |
| `key.cancel()` | **Không bảo đảm** đánh thức một luồng đang `take()` khi không có key được xếp hàng | Có | Key bị hủy, trở nên invalid |
| `watcher.poll(timeout, unit)` với cờ dừng | Không cần đánh thức nếu đợi tới hết timeout | Có cho tới khi tự đóng | Tùy việc ứng dụng cancel/close |
| Chỉ gán `running=false` | Không | Có | Không đổi |

### 5.1. `Thread.interrupt()`: yêu cầu ngắt luồng, không đóng WatchService

`WatchService.take()` và `poll(timeout, unit)` là các điểm chờ có thể bị ngắt, khai báo `throws InterruptedException`. Nếu interrupt luồng đang đợi:

```java
worker.interrupt();
```

Luồng chờ thường nhận `InterruptedException`. WatchService **không tự đóng** vì một thread bị interrupt. Ứng dụng có thể tiếp tục dùng service trên một thread khác hoặc trong một giai đoạn sau, nếu đó là chính sách cần thiết.

Cách xử lý được khuyến nghị khi quyết định dừng:

```java
try {
    WatchKey key = watcher.take();
    // Xử lý key.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Thoát; caller quyết định có đóng WatchService hay không.
}
```

Khôi phục interrupt status qua `Thread.currentThread().interrupt()` là thực hành phổ biến để không nuốt tín hiệu điều khiển. Tuy nhiên **không khôi phục interrupt rồi tiếp tục gọi `take()` vô điều kiện** trong một vòng lặp vô hạn: việc đó có thể gây vòng lặp lỗi hoặc bỏ qua ý định shutdown, tùy cách bạn thiết kế xử lý interrupt.

Nếu một watcher có tài nguyên thuộc sở hữu riêng, việc nhận interrupt thường nên đưa nó vào nhánh dọn dẹp (`finally`/`try-with-resources`), đóng WatchService do chính nó sở hữu, rồi thoát. Nếu WatchService thuộc một controller bên ngoài, hai bên cần thống nhất ai được quyền đóng.

### 5.2. `WatchKey.cancel()`: hủy **một đăng ký**, không dừng cả service

`WatchKey.cancel()` vô hiệu hóa key của đăng ký tương ứng:

```java
WatchKey key = directory.register(
        watcher, StandardWatchEventKinds.ENTRY_CREATE);

key.cancel();
System.out.println(key.isValid()); // false
```

Đoạn minh họa ở trong method xử lý `IOException`, với `directory` tồn tại và WatchService đã mở. Theo API, cancel không có tác dụng thêm nếu key đã bị cancel; key đã cancel **không thể trở lại valid** chỉ bằng `reset()`.

**Đặc biệt quan trọng:** cancel key không được tài liệu mô tả là tín hiệu bắt buộc phải giải phóng ngay thread đang `take()` không có event. Một key đã ở hàng đợi có thể vẫn ở đó cho đến khi được lấy; events pending có thể vẫn lấy qua `pollEvents()` sau cancel. Bởi vậy, **không** dùng `key.cancel()` làm cơ chế shutdown chắc chắn cho một loop đang chờ vô hạn.

Nếu toàn bộ dịch vụ không còn cần thiết, đóng service là cơ chế trực tiếp. Nếu chỉ không cần theo dõi một thư mục trong nhiều thư mục, cancel key đó và tiếp tục vận hành WatchService cho các đăng ký còn lại.

### 5.3. `poll(timeout)`: kiểm tra cờ dừng định kỳ

Một lựa chọn khác:

```java
while (running) {
    WatchKey key = watcher.poll(500, TimeUnit.MILLISECONDS);

    if (key == null) {
        continue; // Hết thời gian chờ, quay lại xem running.
    }

    for (WatchEvent<?> event : key.pollEvents()) {
        // Xử lý event.
    }

    if (!key.reset()) {
        break;
    }
}
```

Đây là **snippet minh họa**, cần `watcher`, cờ `running` có cơ chế memory visibility (`volatile` hoặc atomic), import `TimeUnit`, `WatchKey`, `WatchEvent` và xử lý `InterruptedException` / `ClosedWatchServiceException`. `poll(500, MILLISECONDS)` đợi tối đa 500 ms, trả `null` nếu chưa có key; không đợi vô hạn như `take()`.

Đánh đổi: độ trễ phản hồi cờ stop có thể gần timeout trong trường hợp không có event. Timeout ngắn tăng tần suất wake/check không cần thiết; timeout quá dài làm shutdown chậm. Nếu yêu cầu dừng nhanh và dứt khoát, `close()` thường rõ ràng hơn, nhất là khi WatchService không còn dùng lại.

### 5.4. `poll()` không tham số

`watcher.poll()` trả `null` ngay khi không có key và ném `ClosedWatchServiceException` khi service đã đóng. Một vòng:

```java
while (running) {
    WatchKey key = watcher.poll();
    // Nếu không có key mà cứ lặp không nghỉ, CPU có thể tăng cao.
}
```

là ví dụ **busy polling cần tránh**. Nếu không cần polling thực sự, dùng `take()` hoặc `poll(timeout)`. Đừng dùng `Thread.sleep(...)` để che mọi vấn đề mà không có cơ chế đóng và dọn dẹp rõ ràng.

## 6. Mẫu vòng lặp watcher đúng với việc đóng dịch vụ

Vòng lặp hoạt động thực tế phải xử lý ba điều: các key được báo, tình huống key invalid, và tín hiệu shutdown.

```java
static void runLoop(WatchService watcher, Path directory) {
    try {
        for (;;) {
            WatchKey key = watcher.take();

            for (WatchEvent<?> event : key.pollEvents()) {
                WatchEvent.Kind<?> kind = event.kind();

                if (kind == StandardWatchEventKinds.OVERFLOW) {
                    System.out.println("Rescan required");
                    continue;
                }

                Path relative = (Path) event.context();
                Path changed = directory.resolve(relative);

                // Gọi handler ứng dụng, tránh chặn quá lâu.
                System.out.println(kind.name() + ": "
                        + changed.getFileName());
            }

            if (!key.reset()) {
                // Directory không còn được theo dõi qua key này.
                break;
            }
        }
    } catch (ClosedWatchServiceException ex) {
        // Normal shutdown do WatchService.close().
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        // Dừng theo chính sách interrupt.
    }
}
```

Đây là **method helper dùng trong một class**, với các import `WatchService`, `WatchKey`, `WatchEvent`, `StandardWatchEventKinds`, `ClosedWatchServiceException`, `Path`; nó không phải một tệp có `main`. Bản này giả định **chỉ theo dõi đúng một thư mục**, và event kinds là những loại `ENTRY_*` có context `Path`. Khi watch nhiều thư mục, phải ánh xạ từng `WatchKey` về đúng đường dẫn, không dùng một `directory` duy nhất.

Những điểm cần hiểu:

1. `watcher.take()` có thể chặn. Khi một thread khác đóng service, luồng bắt `ClosedWatchServiceException` và thoát.
2. `key.pollEvents()` có thể trả nhiều event; không chỉ xử lý phần tử đầu.
3. `OVERFLOW` là thông báo có thể mất event. Context của nó có thể là `null` hoặc phụ thuộc implementation; **không cast sang Path** khi gặp `OVERFLOW`. Ứng dụng cần quét lại trạng thái thư mục khi tính chính xác là quan trọng.
4. Với event bình thường `ENTRY_CREATE`/`ENTRY_MODIFY`/`ENTRY_DELETE`, `context()` là tên tương đối với thư mục đăng ký. Ghép `directory.resolve(relative)` để xác định đường dẫn tương ứng.
5. Sau khi xử lý batch, `reset()` làm key sẵn sàng để được báo lại. Nếu trả `false`, key không còn valid; chương trình một-thư-mục thường kết thúc loop.
6. `runLoop` **không tự đóng watcher** ở đây vì ownership được để cho controller. Nếu worker là owner, cần bao `watcher` trong `try-with-resources` hoặc `finally` phù hợp.

### 6.1. `reset()` không phải cách đóng service

`key.reset()` làm key đã signalled quay lại trạng thái chờ báo mới, nếu key còn hợp lệ. Nó **không hủy** key và **không đóng** service. `reset()` có thể trả `false` khi đăng ký đã invalid (chẳng hạn directory không còn truy cập được, key đã cancel, hoặc service bị đóng).

Nếu bạn chỉ có một registration, `reset()==false` là tín hiệu hợp lý để thoát và dọn dẹp. Nếu có nhiều directory, nên xóa key invalid khỏi bảng ánh xạ và tiếp tục nếu còn registration hợp lệ. Không ép key invalid “chạy lại” bằng cách gọi `reset()` liên tục.

## 7. Shutdown có trình tự: signal → close → join → cleanup

Một shutdown đáng tin cậy thường gồm:

```text
Thread điều khiển:
  1. Đặt trạng thái stopping (ngăn đăng ký/thêm handler mới).
  2. Gọi watcher.close() để đánh thức take/poll và vô hiệu key.
  3. Chờ worker thoát bằng join/termination handle.
  4. Giải phóng tài nguyên ứng dụng còn liên quan.
  5. Chỉ sau bước 3 mới công bố "watcher stopped".
```

Ở thread worker:

```text
RUNNING:
  lấy WatchKey
  xử lý event (có thể kiểm tra stopping giữa các event)
  reset key

KHI CLOSE:
  take/poll -> ClosedWatchServiceException
  thoát loop
  finally: cleanup của worker
  kết thúc thread
```

Đừng thay bước 3 bằng `Thread.sleep(100)` rồi giả định thread đã chết. Scheduler, tải hệ thống và thời lượng callback khác nhau; `join()` hoặc một completion signal có tính xác nhận rõ hơn.

### 7.1. `close()` giải phóng thao tác chờ, không hủy handler tùy ý

Một lỗi thiết kế phổ biến:

```java
for (WatchEvent<?> event : key.pollEvents()) {
    doSlowWork(event); // Có thể chặn ở network/database/hàng đợi.
}
```

Đây là pseudocode theo cú pháp Java, `doSlowWork` do ứng dụng định nghĩa. Nếu main gọi `watcher.close()` trong khi worker đang đứng ở `doSlowWork`, việc đóng service **không** tự ngắt hàm nghiệp vụ đó. Worker chỉ gặp `ClosedWatchServiceException` khi thao tác lên WatchService sau đó.

Giải pháp:

- Giữ callback xử lý WatchEvent ngắn; nếu công việc dài, chuyển sang executor/task queue riêng.
- Sử dụng timeout/cancellation policy cho I/O của handler, không trông đợi `close(WatchService)` hủy một network call khác.
- Có cờ `stopping` an toàn đa luồng để worker tránh bắt đầu batch công việc mới.
- Khi chờ thread thoát, có thể dùng `join(timeout)` và báo rõ nếu thread vẫn sống; đừng khẳng định hoàn tất khi chưa dừng.
- Nếu sử dụng `interrupt()` như tín hiệu bổ sung, handler cần xử lý interrupt đúng; việc ngắt không phải cơ chế kill mọi code Java.

### 7.2. Ví dụ class quản lý lifecycle (không có stdout cố định)

Một wrapper có thể tạo, chạy, đóng và đợi thread theo dõi:

```java
import java.io.IOException;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;

public final class DirectoryWatcher implements AutoCloseable {
    private final WatchService service;
    private final Thread thread;
    private volatile boolean stopping;

    public DirectoryWatcher(Path directory) throws IOException {
        service = directory.getFileSystem().newWatchService();

        try {
            directory.register(service,
                    StandardWatchEventKinds.ENTRY_CREATE,
                    StandardWatchEventKinds.ENTRY_DELETE,
                    StandardWatchEventKinds.ENTRY_MODIFY);
        } catch (IOException | RuntimeException ex) {
            service.close();
            throw ex;
        }

        thread = new Thread(this::loop, "directory-watcher");
        thread.start();
    }

    private void loop() {
        try {
            while (!stopping) {
                WatchKey key = service.take();

                if (stopping) {
                    break;
                }

                for (WatchEvent<?> event : key.pollEvents()) {
                    if (stopping) {
                        break;
                    }

                    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                        // Lên lịch quét lại directory theo chính sách app.
                        continue;
                    }

                    // Chỉ xử lý ngắn; phần việc dài nên chuyển queue.
                    System.out.println(event.kind().name()
                            + ": " + event.context());
                }

                if (!key.reset()) {
                    break;
                }
            }
        } catch (ClosedWatchServiceException ex) {
            // Normal shutdown khi controller đóng service.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } finally {
            stopping = true;
            try {
                service.close();
            } catch (IOException ex) {
                // Trong app thật: báo lỗi cleanup qua logging/monitoring.
            }
        }
    }

    @Override
    public void close() throws IOException {
        stopping = true;

        // Close là bước đánh thức take(), không chỉ đổi biến.
        service.close();

        try {
            thread.join(TimeUnit.SECONDS.toMillis(5));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IOException("Interrupted waiting for watcher", ex);
        }

        if (thread.isAlive()) {
            throw new IOException("Watcher thread did not stop");
        }
    }
}
```

Đây là class **có thể biên dịch** trong `DirectoryWatcher.java`, không có `main` và **không có stdout ổn định** vì sự kiện thực tế phụ thuộc thư mục, OS và lịch thực thi. Nó nhấn mạnh lifecycle hơn là tối ưu hiệu năng.

Những điểm production cần cải thiện tùy yêu cầu:

- Constructor khởi chạy thread ngay; nếu muốn tránh `this` escape khi khởi tạo object, tách constructor và `start()`, quản lý trạng thái STARTING/RUNNING/STOPPING/CLOSED.
- Xử lý lỗi `service.close()` trong worker `finally` không nên im lặng ở ứng dụng thật; log hoặc đưa lỗi về bộ điều phối.
- Nếu `close()` bị gọi **ngay từ thread watcher**, `thread.join(...)` tự đợi chính mình sẽ không có ý nghĩa; thiết kế nên cấm hoặc tách phương thức `requestStop()` khỏi `awaitStopped()`.
- Nếu `service.close()` ném `IOException`, wrapper đang chọn chuyển lỗi ra ngoài; caller nên có cleanup/fallback phù hợp và không khẳng định thread đã dừng khi chưa join.
- Event loop ở đây chỉ xử lý một key và không hỗ trợ tự động theo dõi thư mục con. Nếu cần cây thư mục, phải đăng ký thêm thư mục và quản lý map key–directory.
- `volatile stopping` bảo đảm visibility của cờ, nhưng cờ riêng **không** đánh thức `take()`; `service.close()` đảm nhiệm việc đó.
- Có thể thay `thread.join(...)` bằng một `CountDownLatch terminated` và đợi completion, đặc biệt khi cần báo lỗi worker sang controller.
- Không dùng `daemon thread` hoặc JVM shutdown hook làm cơ chế dọn dẹp duy nhất cho ứng dụng chạy lâu.

Ví dụ sử dụng trong một method (đoạn minh họa):

```java
try (DirectoryWatcher watcher =
        new DirectoryWatcher(Path.of("incoming"))) {
    // Ứng dụng thực hiện công việc khác.
    // Khi thoát scope, close() dừng watcher và đợi tối đa 5 giây.
}
```

`incoming` phải là directory tồn tại; caller cần xử lý `IOException`. Những lỗi khi `close()` báo timeout nghĩa là không nên log “shutdown complete” nếu worker vẫn hoạt động.

## 8. Interrupt status và các race khi shutdown

### 8.1. Thread đang chờ `take()`, controller gọi đồng thời `close()` và `interrupt()`

Nếu hai tín hiệu đến gần nhau, thứ tự chính xác ngoại lệ được quan sát có thể khác nhau. Không viết logic chỉ coi **một** trong hai ngoại lệ là shutdown hợp lệ rồi gán ngoại lệ còn lại thành lỗi không thể phục hồi.

Một watcher có yêu cầu đóng rõ ràng thường xử lý cả:

```java
try {
    watcher.take();
} catch (ClosedWatchServiceException ex) {
    // WatchService đã đóng.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Thread được yêu cầu ngắt.
}
```

Nếu `watcher.close()` là bước shutdown chủ đạo, tránh interrupt “dự phòng” quá sớm khi chưa xác minh tình trạng thread; việc interrupt là một hành động mạnh hơn ở mức thread và có thể ảnh hưởng những đoạn code khác đang sử dụng interrupt.

### 8.2. Chỉ `running=false` chưa đủ

Ngay cả khi biến được khai báo:

```java
private volatile boolean running = true;
```

và thread khác gán `running=false`, `volatile` chỉ giải quyết **visibility** khi thread đọc biến. Nếu thread đang blocked ở `take()`, nó chưa đọc lại `running`. Không có cơ chế tự đánh thức. Cần `close()` hoặc `interrupt()`, hoặc dùng `poll(timeout)` để kiểm tra cờ định kỳ.

### 8.3. Không nuốt `InterruptedException` rồi lặp ngay

Một pattern sai:

```java
for (;;) {
    try {
        watcher.take();
    } catch (InterruptedException ignored) {
        // SAI nếu đây là yêu cầu shutdown.
    }
}
```

Nếu controller mong interrupt dừng luồng, code trên làm mất ý nghĩa tín hiệu và có thể chờ tiếp. Hãy có chính sách rõ: khôi phục interrupt và thoát, hoặc nếu chủ đích tiếp tục, phải có lý do, trạng thái và quy tắc xử lý interruption phù hợp.

### 8.4. Đừng giả định có đúng một luồng chờ

Có thể nhiều worker đang gọi `take()` trên cùng WatchService. `close()` có contract đánh thức **các** thread đang chờ, và key liên quan đều invalid. Tuy nhiên nếu có nhiều worker cùng xử lý các key, chương trình phải điều phối `pollEvents()` và `reset()` tránh hai worker thao tác cùng một key không đúng thứ tự.

Tài liệu `WatchKey` khuyến cáo reset sau khi xử lý hết các event, nhất là trong thiết kế nhiều thread. Tạo nhiều thread watcher hiếm khi cần thiết cho ứng dụng đơn giản; một consumer đọc key và giao công việc qua executor thường dễ đảm bảo thứ tự và shutdown hơn.

## 9. Sự kiện có thể bị mất và lúc nào cần quét lại thư mục

`WatchService` là cơ chế **notification**, không phải một log giao dịch đầy đủ của filesystem. Sự kiện có thể bị gộp, trễ hoặc mất tùy provider và tải. `StandardWatchEventKinds.OVERFLOW` báo rằng một số event có thể đã bị mất hoặc bỏ qua.

```java
for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        // Đọc lại trạng thái directory bằng Files.list/walk theo chính sách.
        continue;
    }

    Path name = (Path) event.context();
    Path changed = directory.resolve(name);
    // Xử lý đúng nghĩa của ENTRY_CREATE/DELETE/MODIFY.
}
```

Đoạn minh họa yêu cầu `key` hợp lệ, directory đã đăng ký và imports tương ứng. Khi shutdown, ưu tiên **ngăn lịch công việc mới**; không nên bắt đầu quét lại thư mục lớn sau khi cờ stopping đã bật, trừ khi yêu cầu nghiệp vụ bắt buộc hoàn thành lượt đang xử lý.

Các giới hạn:

- Theo dõi một directory thường thông báo thay đổi **entry trực tiếp**, không tự động theo dõi sâu toàn bộ cây.
- `ENTRY_MODIFY` có thể được gom và có `event.count()` lớn hơn 1.
- File có thể đã bị xóa hoặc đổi tên trước khi code xử lý event. Đọc đường dẫn cần chuẩn bị xử lý `NoSuchFileException` hoặc sai khác trạng thái.
- Trên một số provider, sự kiện có thể đến muộn hoặc có ngữ nghĩa khác nhau; không dùng một event `ENTRY_CREATE` làm bằng chứng nội dung tệp đã ghi xong hoàn toàn.
- Khi đóng WatchService, những event đang chờ có thể không được ứng dụng xử lý; lựa chọn **drain trước shutdown** hay **ngừng ngay** cần thuộc policy ứng dụng, không thể tự mặc định mọi event đã được tiêu thụ.

### 9.1. Shutdown “graceful” và “immediate” khác nhau

Một số hệ thống cần xử lý xong batch đã nhận rồi mới tắt, một số khác cần dừng ngay. Hai chiến lược hợp lý:

**Ngừng ngay:** đánh dấu stopping, đóng WatchService để wake `take()`, handler kiểm tra stopping và thoát, rồi controller đợi worker. Có thể bỏ qua event chưa xử lý; cần cơ chế quét/reconcile lại khi khởi động nếu tính đầy đủ quan trọng.

**Hoàn thành batch:** đánh dấu stopping để không bắt đầu lấy thêm key mới, cho batch đang xử lý kết thúc có giới hạn thời gian, rồi đóng service để bảo đảm không còn chờ ở `take()`. Nếu handler có thể chặn, cần timeout/cancellation riêng. Không sử dụng `close()` như một lời hứa “mọi event đã được xử lý”.

Định nghĩa rõ **khi nào ứng dụng báo STOPPED**: ví dụ service đã đóng, thread đã kết thúc và mọi tác vụ đã nhận được bàn giao hoặc dọn dẹp. Không chỉ dựa vào `watcher.close()` trả về mà không biết trạng thái các executor/handler khác.

## 10. Ownership: ai là người được phép đóng WatchService?

Một WatchService thường là tài nguyên dùng chung giữa controller và thread consumer. Có hai mô hình:

1. **Controller sở hữu:** Controller tạo service, đăng ký các directory, khởi worker và gọi `close()` khi cần shutdown. Worker bắt `ClosedWatchServiceException` và kết thúc. Đây là mô hình rõ ràng cho server/service.
2. **Worker sở hữu:** Worker tự tạo service trong `try-with-resources` và cung cấp API `requestStop()`. Khi nhận tín hiệu, worker đóng service trong `finally`, nhưng phải có cách đánh thức `take()` (ví dụ controller có quyền gọi `worker.interrupt()` hoặc đóng service qua một thread-safe handle do worker cung cấp).

Tránh “double ownership” mơ hồ, nơi handler sự kiện gọi `close()` bất ngờ trong khi module khác vẫn đang đăng ký directory mới. Cần quy định service lifecycle là một phần contract của thư viện.

### 10.1. `try-with-resources` đủ trong ứng dụng một luồng nhưng chưa đủ cho worker

Trong một method chạy watcher trên chính thread caller:

```java
try (WatchService watcher =
        FileSystems.getDefault().newWatchService()) {
    // Chạy loop và thoát theo chính sách của cùng thread.
}
```

`try-with-resources` sẽ đóng service khi rời khối. Nhưng nếu một thread **khác** đang gọi `take()`, chủ sở hữu còn cần `join` hoặc termination mechanism để xác nhận thread đó đã kết thúc. Tránh scope kết thúc “mất dấu” worker vì giữ một WatchService đã đóng chỉ là một phần shutdown.

### 10.2. Đóng service có làm `WatchKey` sống lại sau khi tạo mới service không?

Không. Khi service đã đóng, các key của nó invalid. Bạn không thể `reset` một key cũ để biến nó thành key của WatchService mới.

Nếu muốn bắt đầu theo dõi lại:

```java
try (WatchService replacement =
        directory.getFileSystem().newWatchService()) {
    WatchKey newKey = directory.register(
            replacement,
            StandardWatchEventKinds.ENTRY_CREATE);
    // Khởi động consumer trên replacement.
}
```

Đoạn này nằm trong method xử lý `IOException`, directory tồn tại. Tạo **dịch vụ mới**, đăng ký **key mới**, tạo/điều phối **consumer mới** theo lifecycle ứng dụng.

## 11. Kiểm thử shutdown một cách đáng tin cậy

Một test ngẫu nhiên tạo tệp rồi chờ event thường dễ bị ảnh hưởng bởi OS và thời điểm lập lịch. Để kiểm thử `close()` đánh thức thread `take()`, nên tạo một tình huống **không có event**, đồng bộ thời điểm thread sắp chờ và xác nhận nó kết thúc sau khi close.

Các điểm nên kiểm tra:

- Thread worker thực sự khởi động trước khi controller đóng (dùng `CountDownLatch`; latch chỉ xác nhận sắp tới đoạn chờ).
- `close()` từ thread khác không cần một file-event giả.
- Worker bắt được `ClosedWatchServiceException` và không tạo vòng lặp không kết thúc.
- `join(timeout)` hoặc `terminated.await(timeout)` trả đúng kết quả; nếu timeout, test thất bại thay vì ngủ thêm không có giới hạn.
- Service đã đóng thì `take()`/`poll()` sau đó ném `ClosedWatchServiceException`.
- Key đã đăng ký không còn valid theo `key.isValid()` sau đóng.
- `close()` lặp lại không gây lỗi vì service đã đóng.
- Test cleanup thư mục tạm trong `finally`.
- Không đòi hỏi thứ tự giữa các lần báo file-event thực tế nếu contract không bảo đảm.

### 11.1. Ví dụ kiểm tra key invalid sau khi đóng

```java
Path dir = Files.createTempDirectory("watch-key-");
try {
    WatchKey key;
    try (WatchService watch =
            dir.getFileSystem().newWatchService()) {
        key = dir.register(
                watch, StandardWatchEventKinds.ENTRY_CREATE);
        System.out.println("before close: " + key.isValid());
    }
    System.out.println("after close: " + key.isValid());
} finally {
    Files.deleteIfExists(dir);
}
```

Đây là snippet trong một phương thức xử lý `IOException`; khi provider hỗ trợ đăng ký, output dự kiến:

```text
before close: true
after close: false
```

Nó chứng minh khóa đăng ký bị vô hiệu theo contract của close, **không** chứng minh thread đã dừng vì không khởi tạo worker trong snippet này.

### 11.2. Test `interrupt()` không phải test `close()`

Nếu chỉ interrupt worker và thấy `InterruptedException`, bạn mới kiểm tra được **tính interruptible của thao tác chờ** và chính sách interrupt; bạn chưa kiểm tra tác dụng của việc đóng service hoặc vô hiệu key.

Các bài test nên có những trường hợp riêng: close khi đang chờ, interrupt khi đang chờ, timeout polling, cancel một key trong khi vẫn còn key khác, và đóng service khi worker đang xử lý event dài. Mỗi case có điều kiện “STOPPED” và yêu cầu cleanup khác nhau.

## 12. Những lỗi phổ biến cần tránh

1. **Chỉ gán `running=false` mà không wake thread.** `take()` có thể chờ vô hạn nên không đọc lại cờ.
2. **Chỉ gọi `WatchKey.cancel()` để dừng watcher.** Cancel hủy đăng ký, không bảo đảm giải phóng luồng `take()` đang chờ.
3. **Nghĩ `close()` trả về là mọi worker đã kết thúc.** Close làm wake thao tác chờ, nhưng thread vẫn phải xử lý ngoại lệ và thoát; dùng `join`/completion.
4. **Không bắt `ClosedWatchServiceException`.** Normal shutdown thành stack trace không cần thiết hoặc task kết thúc bằng exception không được ghi nhận đúng.
5. **Bắt `IOException` thay cho `ClosedWatchServiceException`.** Exception của dịch vụ đóng là unchecked `IllegalStateException` subclass, không phải IOException.
6. **Nhầm `ClosedWatchServiceException` với `InterruptedException`.** Close dịch vụ khác interrupt thread; service sau interrupt có thể vẫn mở.
7. **Nuốt `InterruptedException` rồi gọi `take()` tiếp.** Có thể bỏ qua yêu cầu shutdown.
8. **Gọi `watcher.take()` sau `close()` và mong được `null`.** Nó ném `ClosedWatchServiceException`.
9. **Nghĩ `poll()` sau đóng trả `null`.** Khi service đóng, nó ném exception, không phải “chưa có event”.
10. **Cho rằng `close()` tự phát sinh một `WatchEvent` shutdown.** Không có event giả như vậy; luồng được wake bởi closed state.
11. **Dựa vào `Thread.sleep(...)` thay `join()`.** Sleep không xác nhận worker đã kết thúc.
12. **Gọi `join()` từ chính worker lên nó.** Tự chờ chính mình có thể gây treo; thiết kế phân vai requestStop/awaitStop.
13. **Dùng daemon thread để né cleanup.** Daemon chỉ không giữ JVM sống, không bảo đảm dọn tài nguyên hoặc hoàn thành event.
14. **Dùng `poll()` trong tight loop.** Gây busy spin; dùng `take()` hoặc `poll(timeout)`.
15. **Nhầm `poll(timeout)` = `take()`.** Poll timeout trả `null` khi hết thời gian; take chờ tới khi key/event hoặc tín hiệu đặc biệt.
16. **Không gọi `key.reset()` sau khi xử lý.** Key đã signalled có thể không được xếp hàng lại để nhận notification mới.
17. **Tin `key.reset()` sẽ làm key invalid hợp lệ trở lại.** Reset trả false nếu key bị cancel/invalid; cần đăng ký lại với service phù hợp.
18. **Dùng context `OVERFLOW` như `Path`.** Context có thể null/implementation-specific; hãy quét lại trạng thái.
19. **Chỉ đọc một event trong `key.pollEvents()`.** Có thể có nhiều event và `count` lớn hơn 1.
20. **Giả định close bảo đảm xử lý hết event đang chờ.** Shutdown và xử lý queue là hai chính sách độc lập.
21. **Để handler lâu hoặc chặn I/O khác rồi mong `close()` dừng ngay.** Close chỉ wake thao tác trên WatchService.
22. **Quên close WatchService khi key cuối không còn valid.** Không còn key không tự động giải phóng service.
23. **Cố tái sử dụng service đã close.** Cần tạo WatchService mới và đăng ký key mới.
24. **Không có contract ownership.** Nhiều module có thể close service bất ngờ khi module khác còn cần.
25. **Tin filesystem events luôn đầy đủ và đúng thứ tự.** Có coalescing, overflow, khác biệt provider; cần reconcile khi cần sự thật đầy đủ.
26. **Xóa thư mục tạm trước khi watcher dừng.** Có thể tạo event bất ngờ hoặc lỗi cleanup; dừng/đóng rồi mới dọn.
27. **Báo “stopped” trước khi kiểm tra thread còn sống.** Đóng service và hoàn tất worker là hai mốc riêng.
28. **Quên xử lý IOException từ `close()`.** API có checked exception; log hoặc chuyển lỗi theo hợp đồng.
29. **Dùng interrupt để kill mọi callback.** Interrupt là cooperative mechanism, không ngăn được mọi công việc blocking tùy loại API.
30. **Giả định một WatchService theo dõi sâu mọi cây thư mục.** Thường cần đăng ký các directory con riêng nếu muốn recursive monitoring.

## 13. Tự kiểm tra

**1.** Tại sao `volatile boolean running=false` vẫn chưa đủ để dừng một thread đang `watcher.take()`?  
**Trả lời:** `volatile` cho phép nhìn thấy giá trị mới khi đọc biến, nhưng `take()` đang chặn và chưa quay lại đọc. Cần close, interrupt hoặc polling có timeout.

**2.** Khi thread A chặn ở `watcher.take()`, thread B gọi `watcher.close()`, thread A nhận gì?  
**Trả lời:** `ClosedWatchServiceException`, loại unchecked `IllegalStateException`. Thread A phải bắt và thoát loop.

**3.** Đóng WatchService có làm các `WatchKey` liên quan còn valid không?  
**Không.** Những key còn valid bị vô hiệu hóa.

**4.** `WatchKey.cancel()` có đóng toàn bộ WatchService không?  
**Không.** Nó hủy một đăng ký, không đóng service và không là tín hiệu đánh thức `take()` được bảo đảm.

**5.** `Thread.interrupt()` có đóng WatchService không?  
**Không.** Nó có thể khiến `take()` ném `InterruptedException`, trong khi service vẫn mở trừ khi code đóng riêng.

**6.** `watcher.poll(200, MILLISECONDS)` trả `null` nghĩa là service đã đóng?  
**Không.** Trong trường hợp đang mở, đó là timeout chưa có key. Service đã đóng gây `ClosedWatchServiceException`.

**7.** Tại sao sau `close()` vẫn cần `thread.join()`?  
**Vì** close không phải lệnh chờ thread kết thúc. Join xác nhận thread đã xử lý tín hiệu, chạy cleanup và thực sự rời trạng thái running.

**8.** Sau `key.pollEvents()` nên làm gì nếu tiếp tục theo dõi?  
**Trả lời:** `key.reset()` và kiểm tra giá trị trả về; nếu false, key không còn hợp lệ.

**9.** Trong event loop, `OVERFLOW` có an toàn để ép `(Path)event.context()` không?  
**Không.** Context có thể null hoặc do provider quyết định. Cần nhánh xử lý riêng, thường quét lại.

**10.** Có thể đăng ký một `WatchKey` invalid vào service mới bằng `reset()` không?  
**Không.** Tạo WatchService mới nếu cần và gọi `directory.register(...)` để nhận key mới.

**11.** Nếu `close()` được gọi khi worker đang thực hiện `doSlowWork(event)`, worker có dừng ngay không?  
**Không bảo đảm.** Close wake các phương thức chờ của WatchService; handler ứng dụng cần cancellation, timeout và điểm kiểm tra stopping riêng.

**12.** “Shutdown graceful” có nghĩa WatchService phải xử lý mọi event queued không?  
**Tùy chính sách ứng dụng.** Java close không bảo đảm drain mọi event. Ứng dụng phải thiết kế xử lý batch, bàn giao task hoặc reconcile khi restart.

## 14. Ghi nhớ và tài liệu tham khảo

**Nguyên tắc thực hành:** Khi dịch vụ theo dõi sẽ kết thúc, **đóng WatchService để giải phóng `take()` đang chờ**, bắt `ClosedWatchServiceException` để thoát bình thường, **đợi thread kết thúc** bằng `join`/completion, rồi dọn tài nguyên liên quan. `interrupt` là tín hiệu cho **thread**, `cancel` là tín hiệu hủy **một key**, còn `poll(timeout)` là cơ chế **kiểm tra định kỳ**. Đừng xem bốn việc này là tương đương.

Tài liệu Java SE 21 chính thức:

- `WatchService` — `close`, `take`, `poll` và cơ chế đánh thức thread: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchService.html
- `WatchKey` — trạng thái signalled/ready, `pollEvents`, `reset`, `cancel`, `isValid`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchKey.html
- `ClosedWatchServiceException` — unchecked exception khi service đã đóng: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/ClosedWatchServiceException.html
- `StandardWatchEventKinds` — ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY, OVERFLOW: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html
- `Path.register` — đăng ký directory với WatchService: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html
- Oracle Java Tutorials — Watching a Directory for Changes: https://docs.oracle.com/javase/tutorial/essential/io/notification.html
