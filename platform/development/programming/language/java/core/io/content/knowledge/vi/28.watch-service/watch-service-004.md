# Java WatchService: take, poll và vòng xử lý sự kiện

## 1. Bài toán và phạm vi

Khi ứng dụng cần biết một thư mục có tệp mới, tệp bị sửa hoặc một mục bị xóa, Java NIO.2 cung cấp **`WatchService`** trong package `java.nio.file`. Thay vì liên tục quét lại cả thư mục bằng `Files.list(...)`, ứng dụng có thể đăng ký theo dõi và tiêu thụ các tín hiệu thay đổi thông qua **`WatchKey`**.

Ba cách lấy key phổ biến là:

- `watchService.take()`: **chờ** đến khi có key được báo hiệu.
- `watchService.poll()`: **kiểm tra ngay**; nếu chưa có key thì trả `null`.
- `watchService.poll(timeout, unit)`: **chờ có giới hạn thời gian**; hết hạn mà chưa có key thì trả `null`.

Đề bài “take, poll và vòng xử lý sự kiện” không chỉ là học ba cú pháp. Một vòng theo dõi đúng còn phải lấy danh sách `pollEvents()`, xử lý đường dẫn tương đối, luôn đưa key trở lại trạng thái sẵn sàng qua `reset()`, chú ý `OVERFLOW`, và đóng dịch vụ hợp lý khi dừng.

**Mục tiêu học tập:** hiểu chu trình đăng ký → chờ key → xử lý events → reset → lặp; chọn `take` hay `poll` theo yêu cầu latency và shutdown; tránh mất sự kiện do sử dụng sai `WatchKey`; xây một chương trình Java 17+ có thể chạy thử.

## 2. Các thành phần cốt lõi

| Thành phần | Ý nghĩa |
|---|---|
| `FileSystems.getDefault().newWatchService()` | Tạo dịch vụ theo dõi filesystem mặc định |
| `Path.register(watcher, kinds...)` | Đăng ký thư mục và các loại sự kiện quan tâm |
| `WatchKey` | Phiếu đăng ký nhận tín hiệu; liên kết với một đối tượng được theo dõi |
| `watchService.take()` | Chờ một key đã được báo hiệu |
| `watchService.poll()` | Lấy key báo hiệu ngay nếu có |
| `watchService.poll(timeout, unit)` | Lấy key nếu có trong thời hạn |
| `key.pollEvents()` | Lấy và xóa danh sách sự kiện đang chờ trong key |
| `key.reset()` | Đặt lại key để tiếp tục nhận báo hiệu, trả `false` nếu không còn hợp lệ |
| `key.watchable()` | Trả về đối tượng đã đăng ký (thường là `Path` thư mục) |
| `key.cancel()` | Hủy đăng ký của key |
| `watchService.close()` | Đóng dịch vụ và giải phóng tài nguyên |

Các loại sự kiện chuẩn thường dùng:

- `StandardWatchEventKinds.ENTRY_CREATE`: một mục xuất hiện trực tiếp trong thư mục đăng ký.
- `StandardWatchEventKinds.ENTRY_MODIFY`: một mục trực tiếp có thay đổi được provider nhận biết.
- `StandardWatchEventKinds.ENTRY_DELETE`: một mục trực tiếp bị xóa/biến mất.
- `StandardWatchEventKinds.OVERFLOW`: dấu hiệu sự kiện có thể đã bị mất/bị loại bỏ, cần đồng bộ lại trạng thái bằng cách quét thực tế.

Các loại `ENTRY_*` thường mang `WatchEvent<Path>`; `context()` là **tên/đường dẫn tương đối từ thư mục đã đăng ký**, không phải đường dẫn tuyệt đối. `OVERFLOW` có ngữ nghĩa khác và không được giả định cung cấp một Path hợp lệ.

## 3. Đăng ký trước khi đợi sự kiện

Ví dụ đăng ký một thư mục đã tồn tại:

```java
import java.nio.file.*;
import static java.nio.file.StandardWatchEventKinds.*;

Path directory = Path.of("inbox");
try (WatchService watcher =
         FileSystems.getDefault().newWatchService()) {

    WatchKey key = directory.register(
            watcher, ENTRY_CREATE, ENTRY_MODIFY, ENTRY_DELETE);
    // Tiêu thụ key bằng take/poll, đọc events và reset ở đây.
}
```

Đây là đoạn minh họa; mã cần đặt trong một method/class, thư mục `inbox` phải tồn tại và provider phải hỗ trợ đăng ký. Thường tạo thư mục trước bằng `Files.createDirectories(directory)` nếu nghiệp vụ cho phép.

- `WatchService` **không tự động theo dõi mọi thư mục trong hệ thống**. Đăng ký rõ từng thư mục.
- `Path.register` trả `WatchKey` cho lần đăng ký; bản thân nó **không phải** một lần gọi chờ.
- Loại sự kiện phụ thuộc provider. Một số filesystem hoặc môi trường chạy không hỗ trợ đầy đủ; khi đó có thể gặp `UnsupportedOperationException` hoặc ngoại lệ I/O.
- Đừng đăng ký path là tệp thông thường rồi giả định hành vi như directory watch trên mọi provider: ví dụ cơ bản nên theo dõi **thư mục chứa tệp**.
- Quyền truy cập và nền tảng (filesystem cục bộ, remote mount, container...) có thể ảnh hưởng sự kiện thực tế.

## 4. Chu trình sống của WatchKey

`WatchKey` có trạng thái **ready** và **signalled**. Khi có thay đổi, provider ghi nhận sự kiện vào key tương ứng rồi key có thể được đưa vào hàng đợi của `WatchService` để ứng dụng lấy ra.

```text
Đăng ký thư mục
      |
      v
Key READY  <------------------------+
      |                              |
Có event được ghi nhận              |
      v                              |
Key SIGNALLED, được enqueue         |
      |                              |
      v                              |
take() hoặc poll() lấy key           |
      |                              |
      v                              |
pollEvents(): lấy events đang chờ     |
      |                              |
      v                              |
Xử lý từng event                     |
      |                              |
      v                              |
reset() ------------------------------+
      |
      +-- false: key không hợp lệ -> bỏ đăng ký / dừng / phục hồi
```

Một `WatchKey` có thể tích lũy **nhiều events** trước khi ứng dụng gọi `pollEvents()`. Nếu một key vẫn đang signalled, các tín hiệu bổ sung được tích lũy theo cơ chế provider thay vì bảo đảm mỗi event lại tạo một key riêng trong hàng đợi.

**Bước `reset()` là bắt buộc về mặt chu trình xử lý**: sau khi lấy key, ứng dụng nên đọc events rồi reset để key có thể tiếp tục được thông báo đúng cách. Nếu không reset, vòng xử lý có thể không nhận được các tín hiệu tiếp theo như dự tính.

`reset()` trả `boolean`:

- `true`: key vẫn hợp lệ để tiếp tục theo dõi.
- `false`: key không còn hợp lệ, ví dụ đăng ký đã bị hủy, đối tượng không còn đủ điều kiện theo dõi, hoặc service đã đóng.

Khi `reset() == false`, cần bỏ key khỏi cấu trúc quản lý, xem xét đăng ký lại thư mục nếu nó được tạo lại và policy cho phép; không tiếp tục giả định key vẫn hoạt động.

## 5. `take()`: chờ cho đến khi có key

Chữ ký:

```java
WatchKey key = watcher.take();
```

`take()` là thao tác **blocking**: nếu chưa có key signalled, thread gọi sẽ chờ. Khi có key, nó trả key để ứng dụng lấy danh sách events.

Phù hợp khi:

- Có một worker chuyên theo dõi filesystem và thường không cần làm việc khác trong lúc chờ.
- Muốn tránh busy loop liên tục gọi `poll()`.
- Shutdown đã được thiết kế rõ bằng interrupt/đóng WatchService và xử lý ngoại lệ.

`take()` có thể ném `InterruptedException` nếu thread đang chờ bị interrupt. Sau khi service bị đóng, thao tác có thể ném `ClosedWatchServiceException`. Trong thiết kế event loop, hãy xử lý shutdown chủ động, không coi mọi ngoại lệ này là lỗi dữ liệu.

Ví dụ minh họa **không độc lập**:

```java
try {
    while (!Thread.currentThread().isInterrupted()) {
        WatchKey key = watcher.take();
        try {
            processEvents(key);
        } finally {
            if (!key.reset()) {
                break;
            }
        }
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
} catch (ClosedWatchServiceException ex) {
    // Service đã đóng, thường là một nhánh shutdown bình thường.
}
```

Biến `watcher` và hàm `processEvents` phải được khai báo ở chỗ khác. Trong chương trình thật, dùng map `WatchKey -> Path` và quyết định xử lý trường hợp một trong nhiều key không còn hợp lệ; không phải lúc nào một key invalid cũng buộc dừng toàn bộ service.

## 6. `poll()`: kiểm tra không chờ

```java
WatchKey key = watcher.poll();
if (key == null) {
    // Không có key signalled tại thời điểm kiểm tra.
}
```

`poll()` **trả ngay**:

- Có key → trả key cho vòng xử lý.
- Không có key → trả `null`.
- Service đã đóng → có thể ném `ClosedWatchServiceException`.

Phù hợp khi ứng dụng đã có một main loop làm việc khác và chỉ muốn kiểm tra sự kiện định kỳ mà không đứng chờ.

**Bẫy:** viết một vòng vô hạn chỉ gọi `poll()` rồi kiểm tra `null` liên tục có thể tiêu thụ CPU lớn:

```java
// KHÔNG khuyến nghị: vòng quay nóng khi không có sự kiện.
while (running) {
    WatchKey key = watcher.poll();
    if (key == null) {
        continue;
    }
    // ...
}
```

Nếu dùng `poll()`, nên lồng vào một chu kỳ có công việc thật, giới hạn tần suất hoặc dùng bản `poll(timeout, unit)`. Không nên tự thêm `Thread.sleep(...)` dài và bỏ qua nhu cầu shutdown/độ trễ; thường timed poll diễn đạt ý định rõ hơn.

## 7. `poll(timeout, unit)`: chờ có thời hạn

```java
WatchKey key = watcher.poll(500, TimeUnit.MILLISECONDS);
```

Khác với `poll()`, overload này có thể chờ tối đa khoảng thời gian yêu cầu khi hàng đợi chưa có key. Nếu chưa có tín hiệu trước khi hết hạn, trả `null`. Nó có thể ném `InterruptedException` và `ClosedWatchServiceException` tương ứng.

Phù hợp với vòng xử lý cần:

1. Thường xuyên xử lý sự kiện thay đổi tệp.
2. Sau mỗi khoảng thời gian thực hiện công việc nền, ví dụ kiểm tra cờ dừng, flush metrics hoặc quét phòng khi missed events.
3. Có cơ chế dừng có giới hạn độ trễ mà không phải đóng service ngay.

Ví dụ:

```java
while (running) {
    WatchKey key = watcher.poll(1, TimeUnit.SECONDS);

    if (key == null) {
        // Sau tối đa 1 giây không có key: làm việc định kỳ nếu cần.
        continue;
    }

    processEvents(key);
    if (!key.reset()) {
        // Loại bỏ đăng ký này / quyết định retry.
    }
}
```

Đây là đoạn minh họa có `running` và `processEvents` cần được xác định bên ngoài. Không coi timeout bằng chứng rằng filesystem không thay đổi — một sự kiện có thể bị mất, gộp, chậm hoặc thư mục chưa được đăng ký.

## 8. So sánh nhanh ba cách lấy key

| Tiêu chí | `take()` | `poll()` | `poll(timeout, unit)` |
|---|---|---|---|
| Có block khi chưa có key? | Có, có thể chờ vô hạn | Không | Có, tối đa thời hạn |
| Khi không có key | Tiếp tục chờ | Trả `null` ngay | Trả `null` sau timeout |
| Thường phù hợp | Worker chuyên xử lý event | Tích hợp main loop đang có | Watch loop + tác vụ định kỳ |
| Chú ý CPU | Không busy spin khi chờ | Dễ busy spin nếu lặp liên tục | Thường giảm busy spin |
| Interrupt | Có thể ném `InterruptedException` | Không chờ nên không có checked interrupt | Có thể ném `InterruptedException` |
| Khi WatchService đóng | `ClosedWatchServiceException` | `ClosedWatchServiceException` | `ClosedWatchServiceException` |
| Cần `pollEvents()/reset()`? | Có | Có, nếu trả key | Có, nếu trả key |

Không có lựa chọn nào “luôn tốt nhất”. Chọn theo nhu cầu chờ, công việc đồng thời trong thread, yêu cầu độ trễ shutdown, và hệ thống thực tế. Phần **xử lý WatchKey** về cơ bản giống nhau cho cả ba cách.

## 9. Xử lý events trong WatchKey

Sau khi lấy key:

```java
for (WatchEvent<?> event : key.pollEvents()) {
    WatchEvent.Kind<?> kind = event.kind();

    if (kind == StandardWatchEventKinds.OVERFLOW) {
        // Cần rescan / đồng bộ trạng thái.
        continue;
    }

    Path relativeName = (Path) event.context();
    Path directory = (Path) key.watchable();
    Path changed = directory.resolve(relativeName);

    System.out.println(kind.name() + ": " + changed);
}
boolean valid = key.reset();
```

Đây là ví dụ minh họa cần import `Path`, `WatchEvent`, `StandardWatchEventKinds` và khai báo `key`. Điểm cần hiểu:

- `key.pollEvents()` trả danh sách sự kiện đang chờ của **key đó**, đồng thời bỏ các sự kiện được lấy khỏi danh sách chờ tương ứng.
- `event.kind()` giúp phân biệt create/modify/delete/overflow.
- Với sự kiện `ENTRY_*` đăng ký trên `Path`, `context()` thường là `Path` **tương đối**. `directory.resolve(relativeName)` mới tạo đường dẫn dưới thư mục đang theo dõi.
- Không dùng `event.context().toString()` để tạo đường dẫn tuyệt đối rồi đoán thư mục.
- `OVERFLOW` cần được xử lý **trước** việc ép `context()` sang `Path`, vì context của overflow không phải một tên tệp hợp lệ để resolve.
- `event.count()` cho biết số lần sự kiện tương tự được tích lũy/gộp theo semantics watch service; **không** nên suy ra đó là số lần ghi chính xác hoặc số phiên bản file.
- Sau khi xử lý, `reset()` để tiếp tục hoạt động. Dù handler gặp lỗi nghiệp vụ, vòng điều phối phải có chính sách không bỏ quên reset hoặc đóng đăng ký.

### Một tên có thể phát nhiều sự kiện

Việc editor lưu file có thể tạo file tạm, ghi file, rename rồi xóa file cũ. Một hành động “Save” của người dùng có thể tạo nhiều sự kiện, và trình tự trên Windows/Linux/macOS khác nhau.

Ngay cả `ENTRY_MODIFY` cũng có thể phát nhiều lần cho một chuỗi ghi. Vì vậy:

- Thiết kế handler **idempotent**: xử lý cùng file nhiều lần không làm trạng thái nghiệp vụ sai.
- Có thể **debounce**: đợi một khoảng ngắn trước khi xử lý nội dung cuối, nhưng vẫn kiểm tra file có thật và đủ ổn định.
- Đừng cho rằng `ENTRY_CREATE` xảy ra tức file đã được ghi xong.
- Nếu muốn xử lý dữ liệu đầy đủ, ứng dụng thường kiểm tra nội dung/metadata sau sự kiện, có retry có giới hạn nếu file còn bị khóa hoặc chưa sẵn sàng.

## 10. Chương trình Java 17+ hoàn chỉnh với timed poll

Ví dụ tự tạo một thư mục tạm, đăng ký sự kiện, tạo rồi sửa một file bên trong, sau đó lấy các `WatchKey` trong khoảng thời gian hữu hạn. Chương trình không in số lượng/tên/thứ tự event như một đáp án cố định, vì các tín hiệu phụ thuộc filesystem.

Tạo file **`WatchServiceLoopDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.ClosedWatchServiceException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.concurrent.TimeUnit;

public class WatchServiceLoopDemo {

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watch-demo-");
        Path file = directory.resolve("sample.txt");

        try {
            try (WatchService watcher =
                         FileSystems.getDefault().newWatchService()) {

                directory.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                Files.writeString(file, "first\n", StandardCharsets.UTF_8);
                Files.writeString(file, "second\n", StandardCharsets.UTF_8);

                int receivedKeys = 0;
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(2);

                while (System.nanoTime() < deadline) {
                    long remaining = deadline - System.nanoTime();
                    if (remaining <= 0) {
                        break;
                    }

                    WatchKey key = watcher.poll(
                            remaining, TimeUnit.NANOSECONDS);

                    if (key == null) {
                        break;
                    }

                    receivedKeys++;
                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.OVERFLOW) {
                            System.out.println("Event: OVERFLOW");
                            continue;
                        }

                        Path name = (Path) event.context();
                        System.out.println("Event: "
                                + event.kind().name()
                                + ", name=" + name);
                    }

                    if (!key.reset()) {
                        System.out.println("WatchKey invalid");
                        break;
                    }
                }

                System.out.println("At least one key: "
                        + (receivedKeys > 0));
            } catch (ClosedWatchServiceException ex) {
                System.out.println("WatchService closed");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac WatchServiceLoopDemo.java
java WatchServiceLoopDemo
```

**Ví dụ stdout thường gặp** trên hệ thống phát đủ create/modify cho tệp:

```text
Event: ENTRY_CREATE, name=sample.txt
Event: ENTRY_MODIFY, name=sample.txt
At least one key: true
```

**Đây là output minh họa, không phải cam kết stdout chính xác trên mọi hệ thống.** Số lượng `ENTRY_MODIFY`, việc coalescing, thứ tự và thời điểm quan sát có thể khác nhau. Trên môi trường không phát event trong thời hạn 2 giây, chương trình có thể chỉ in:

```text
At least one key: false
```

Nếu provider không hỗ trợ watch service, thiếu quyền thư mục hoặc lỗi I/O, chương trình có thể ném ngoại lệ thay vì in kết quả trên. Trình biên dịch và runtime Java 17+ có thể chạy chương trình độc lập; khả năng quan sát sự kiện phụ thuộc filesystem thực tế.

Phân tích từng bước:

1. `Files.createTempDirectory` tạo thư mục riêng; `Files.writeString` tạo rồi ghi file để tạo các thay đổi có thể quan sát được.
2. Đăng ký `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE` **trước** khi ghi file, tránh bỏ lỡ ngay các thao tác do ví dụ thực hiện.
3. Vòng timed poll sử dụng `System.nanoTime()` để tính deadline tương đối, thay vì tiếp tục chờ 2 giây cho **mỗi** key. Nó dừng sau khoảng thời gian tối đa dành cho giai đoạn chờ.
4. `pollEvents()` lấy danh sách events; `OVERFLOW` được kiểm tra trước khi ép context sang Path.
5. `key.reset()` giúp key tiếp tục theo dõi nếu còn hợp lệ.
6. `WatchService` được đóng bằng try-with-resources. File và thư mục demo được xóa trong `finally`. Việc xóa cuối cùng xảy ra sau khi đóng watcher, vì vậy không phải sự kiện đáng mong chờ trong output.

Để test kỹ hơn, có thể đưa các thay đổi vào một thread writer riêng cách nhau vài trăm mili-giây. Vẫn không nên assert rằng từng lần ghi sẽ tương ứng chính xác một `ENTRY_MODIFY` trên mọi provider.

## 11. Khi có nhiều thư mục: map WatchKey -> Path

Một `WatchService` có thể nhận keys từ nhiều thư mục đã đăng ký. Mẫu phổ biến:

```java
Map<WatchKey, Path> directories = new HashMap<>();

WatchKey keyA = pathA.register(watcher, ENTRY_CREATE, ENTRY_DELETE);
WatchKey keyB = pathB.register(watcher, ENTRY_MODIFY);

directories.put(keyA, pathA);
directories.put(keyB, pathB);
```

Đây là đoạn minh họa, cần import `Map`, `HashMap`, các `Path` và static event kinds; `pathA`, `pathB` phải hợp lệ.

Khi lấy một key:

```java
Path directory = directories.get(key);
if (directory == null) {
    // Key không thuộc tập đăng ký do ứng dụng quản lý.
} else {
    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == OVERFLOW) {
            // Rescan directory.
            continue;
        }

        Path relative = (Path) event.context();
        Path changed = directory.resolve(relative);
        // Xử lý changed phù hợp loại event.
    }
}

if (!key.reset()) {
    directories.remove(key);
}
```

Đây cũng là đoạn minh họa, giả định các biến và constant đã được khai báo. Có thể dùng `(Path) key.watchable()` thay map cho trường hợp chỉ đăng ký trực tiếp Path. Map giúp ứng dụng gắn thêm metadata như tenant, project, cấu hình filter, policy retry hay trạng thái thư mục.

**Không reset key không thuộc về mình mà bỏ qua mãi** nếu đang dùng một WatchService dùng chung: cần chính sách quản lý ownership, cleanup và bảo vệ luồng xử lý rõ ràng.

## 12. Một thư mục không có nghĩa theo dõi đệ quy

Trong Java NIO.2 chuẩn, đăng ký một thư mục thường chỉ nhận sự kiện đối với **các mục trực tiếp** bên dưới:

```text
root/              <- đăng ký root
  a.txt            <- có thể nhận ENTRY_MODIFY cho a.txt
  nested/
    b.txt          <- không tự nhiên nhận event b.txt qua root watch
```

Để theo dõi cây thư mục:

1. Duyệt các thư mục con đang tồn tại và đăng ký **từng thư mục**.
2. Khi thấy `ENTRY_CREATE` đối với thư mục mới, kiểm tra đó là directory và đăng ký nó.
3. Với thư mục bị xóa/di chuyển, loại bỏ hoặc xử lý key invalid.
4. Có chiến lược chống race giữa lúc duyệt cây và lúc đăng ký. Một phần thay đổi có thể đã xảy ra trước khi thư mục con được đăng ký.
5. Cân nhắc symbolic link, vòng lặp đường dẫn, quyền truy cập, và giới hạn tài nguyên nếu cây rất lớn.

Không nên viết `root.register(watcher, ENTRY_CREATE)` rồi khẳng định có thể nhận mọi thay đổi sâu nhiều cấp. Nếu bài toán đòi hỏi phát hiện **chắc chắn mọi thay đổi**, WatchService thường cần bổ sung snapshot/rescan hoặc cơ chế theo dõi filesystem chuyên dụng với hợp đồng phù hợp.

## 13. OVERFLOW: sự kiện có thể bị mất

`StandardWatchEventKinds.OVERFLOW` báo rằng sự kiện có thể đã bị bỏ vì hàng đợi/quản lý tài nguyên không theo kịp số lượng thay đổi hoặc lý do provider khác.

Sai lầm nguy hiểm:

```java
for (WatchEvent<?> event : key.pollEvents()) {
    Path p = (Path) event.context(); // Sai với OVERFLOW.
    process(p);
}
```

Đây chỉ là đoạn **phản ví dụ**, `process` chưa được định nghĩa. Với `OVERFLOW`, hãy coi trạng thái cache theo dõi có nguy cơ **không đồng bộ với filesystem**:

- Đánh dấu thư mục/cây cần **rescan** để lấy trạng thái thực tế.
- So sánh snapshot mới với trạng thái ứng dụng lưu trước đó nếu nghiệp vụ cần.
- Thực hiện xử lý idempotent khi phát hiện thay đổi.
- Ghi log/metrics overflow, theo dõi khả năng event loop xử lý quá chậm.
- Tránh coi event stream là hệ thống event sourcing chuẩn xác: sau overflow bạn **không thể tái tạo mọi thao tác trung gian** chỉ từ các event còn lại.

Ngay cả khi không thấy `OVERFLOW`, filesystem notifications vẫn có thể gộp sự kiện, phụ thuộc provider, và không nên thay thế mọi kiểm tra trạng thái thực tế nếu bài toán cần độ chính xác cao.

## 14. Đọc file khi có ENTRY_CREATE/ENTRY_MODIFY

`WatchService` báo **thay đổi được quan sát**, không bảo đảm “file đã được ghi xong” hay “người ghi đã đóng handle”.

Ví dụ producer có thể:

1. Tạo `report.csv`.
2. Ghi header.
3. Ghi từng batch rows.
4. Flush và đóng file.

Consumer có thể nhận `ENTRY_CREATE` ngay sau bước 1 và đọc thấy file chưa hoàn chỉnh.

Chiến lược thiết kế tốt hơn:

- Producer ghi vào file tạm, đóng, rồi **rename/move** tới tên chính thức khi sẵn sàng, với hợp đồng filesystem phù hợp.
- Consumer xem `ENTRY_CREATE` là dấu hiệu cần kiểm tra trạng thái, không đồng nhất với transaction completed.
- Nếu chỉ có `ENTRY_MODIFY`, debounce và đọc lại sau khi file ổn định theo policy; cần xử lý file vẫn đang bị ghi/khóa.
- Thiết kế parser chịu được EOF và định dạng tạm thời không hợp lệ; retry có giới hạn thay vì loop vô hạn.
- Khi chỉ cần biết trạng thái hiện thời, đọc lại snapshot/file state thay vì cố phát lại mọi event riêng lẻ.

Đừng mở file rồi mặc định nó tồn tại: mục có thể đã bị xóa/rename **giữa event và lúc mở** (TOCTOU). Kiểm tra/đọc với xử lý `NoSuchFileException` và các lỗi quyền truy cập.

## 15. Dừng vòng lặp đúng cách

### Với vòng `take()`

`take()` có thể chờ vô hạn nếu không còn thay đổi nào. Những cách dừng thường dùng:

- **Interrupt thread** đang `take()`; bắt `InterruptedException`, đặt lại interrupt flag nếu phù hợp và kết thúc loop.
- **Đóng WatchService** từ thread điều khiển; thread đang chờ có thể nhận `ClosedWatchServiceException`.
- Dùng protocol shutdown riêng, đảm bảo không giữ lock gây deadlock khi watcher dừng.

Ví dụ minh họa:

```java
try {
    while (running) {
        WatchKey key = watcher.take();
        try {
            handle(key);
        } finally {
            key.reset();
        }
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
} catch (ClosedWatchServiceException ex) {
    // Phù hợp khi người điều khiển đã chủ động đóng service.
}
```

Đoạn này **không độc lập**; `running`, `watcher` và `handle` do ứng dụng định nghĩa. Khi có nhiều keys, vẫn phải kiểm tra giá trị trả về của `reset()` và hủy/loại đăng ký invalid; snippet tối giản chỉ minh họa lối thoát.

### Với timed poll

Khi dùng `poll(500, MILLISECONDS)`, thread có cơ hội kiểm tra cờ dừng đều đặn kể cả khi không có event. Có thể dùng `AtomicBoolean` hoặc cơ chế đồng bộ thích hợp cho `running` khi flag được thread khác cập nhật.

```java
while (running.get()) {
    WatchKey key = watcher.poll(500, TimeUnit.MILLISECONDS);
    if (key == null) {
        continue;
    }

    try {
        handle(key);
    } finally {
        if (!key.reset()) {
            // Hủy/loại khỏi cấu trúc đăng ký.
        }
    }
}
```

Mẫu này không có busy spin liên tục, thời gian nhận ra cờ dừng có thể bị giới hạn bởi timeout và thời gian xử lý callback. Nó không thay thế việc đóng service khi ứng dụng giải phóng tài nguyên.

### Đóng service

`WatchService` triển khai `Closeable`, nên dùng try-with-resources. Sau `close()`, `take/poll` không còn là các thao tác tiêu thụ key hợp lệ. `WatchKey.cancel()` hủy một đăng ký, không đồng nghĩa đóng toàn bộ service.

## 16. Độ tin cậy và các giới hạn thực tế

Không nên coi `WatchService` là một hàng đợi giao dịch/bản ghi thay đổi đầy đủ như message broker:

- **Số lượng và thứ tự sự kiện phụ thuộc provider.** Có thể gộp modify, bỏ event khi overflow, hoặc có tín hiệu muộn.
- **Rename/move** có thể thể hiện bằng create/delete, modify hoặc tổ hợp khác nhau tùy filesystem.
- **Remote mounts/network drives** có thể có semantics khác filesystem cục bộ hoặc không hỗ trợ đầy đủ.
- **Crash/restart**: WatchService không cung cấp lịch sử sự kiện bền để phát lại trong thời gian ứng dụng tắt. Cần rescan lúc khởi động.
- **Nội dung file** không có sẵn trong event; handler phải tự đọc, xử lý file đổi/xóa giữa chừng.
- **Nhiều thay đổi cùng lúc** có thể gây `OVERFLOW`. Ưu tiên xử lý event ngắn, đẩy tác vụ CPU/I/O nặng sang worker pool có giới hạn.
- **Bảo mật:** không coi path từ event là input đã được xác thực; kiểm soát thư mục gốc, symbolic links, quyền và dữ liệu không tin cậy.
- **Tài nguyên:** đăng ký hàng nghìn thư mục có chi phí OS/provider. Khi key invalid phải dọn map, tránh rò rỉ.
- **Nhiều consumer trên cùng service:** nếu các luồng cùng gọi take/poll, một key có thể được tiêu thụ bởi một consumer; cần điều phối ownership, không giả định mọi consumer đều nhận bản sao sự kiện.

Đối với tác vụ yêu cầu không bỏ lỡ thay đổi nào (ví dụ audit pháp lý), chỉ dựa vào WatchService thường không đủ. Cân nhắc nhật ký thay đổi ở nguồn dữ liệu hoặc transaction log được thiết kế cho mục tiêu đó.

## 17. Lỗi phổ biến

1. **Quên `reset()`**: key có thể ngừng phát tín hiệu tiếp theo như mong muốn.
2. **Gọi `reset()` trước khi xử lý events rồi quên trạng thái sự kiện**: làm flow khó hiểu; ưu tiên drain `pollEvents()` rồi reset có kiểm soát.
3. **Không xét `reset()==false`**: dùng một registration đã invalid, dẫn tới im lặng không thấy thay đổi.
4. **Nhầm `poll()==null` thành thư mục chắc chắn không thay đổi**: đó chỉ là không có key signalled trong hàng đợi ngay lúc kiểm tra.
5. **Dùng `poll()` trong vòng quay nóng**: CPU tăng cao khi không có event.
6. **Dùng `take()` nhưng không có cơ chế shutdown**: thread có thể chờ vô hạn.
7. **Không bắt `InterruptedException` ở take/timed poll**: mất cơ hội dừng lịch sự.
8. **Quên kiểm tra `OVERFLOW` trước khi cast `event.context()`**: context có thể không phải Path hợp lệ.
9. **Hiểu `event.context()` là đường dẫn tuyệt đối**: cần resolve với thư mục gắn key.
10. **Tưởng `ENTRY_CREATE` nghĩa file đã viết xong**: có thể đọc file còn đang ghi.
11. **Dựa vào đúng một `ENTRY_MODIFY` cho mỗi lần save**: provider có thể gộp/phát nhiều thông báo.
12. **Giả định theo dõi một root là theo dõi recursive**: phải đăng ký từng thư mục con.
13. **Xử lý file bằng một thao tác nặng ngay trong watch loop**: có thể làm backlog tăng và overflow.
14. **Không xử lý file bị xóa/rename trước khi handler đọc**: TOCTOU dễ xảy ra.
15. **Quên đăng ký thư mục mới khi theo dõi cây**: không nhận thay đổi sâu bên trong.
16. **Không rescan sau OVERFLOW hoặc restart**: trạng thái ứng dụng có thể không đồng bộ.
17. **Không đóng WatchService**: giữ tài nguyên OS hoặc thread đang chờ.
18. **Coi events như lịch sử chính xác**: WatchService là hệ thống thông báo thay đổi, không phải event journal.
19. **Chỉ có một map path nhưng không quản lý các WatchKey invalid**: rò rỉ reference và mất khả năng đăng ký lại.
20. **Giả định code sẽ phát stdout giống hệt trên mọi OS**: thứ tự và count không ổn định; test nên dựa vào eventual state và timeout phù hợp.

## 18. Lựa chọn take hay poll trong ứng dụng

### Trường hợp A — Dịch vụ import file chuyên dụng

Một thread theo dõi thư mục `incoming`, gần như chỉ làm việc khi có file. Dùng `take()` giúp ngủ chờ thay đổi, không cần đánh thức định kỳ. Khi shutdown, interrupt thread hoặc đóng service, bắt ngoại lệ thích hợp. Handler nên chuyển công việc import nặng sang queue/worker pool và xử lý file chưa ghi xong.

### Trường hợp B — Ứng dụng GUI hoặc chương trình có main loop

Main loop đã xử lý input và UI/tác vụ khác. `poll()` có thể phù hợp nếu được gọi với tần suất hợp lý, không busy spin. Tuy nhiên không nên chặn UI thread bằng `take()`; có thể dùng watcher thread riêng và gửi thông báo vào UI dispatcher.

### Trường hợp C — Watcher kiêm tác vụ định kỳ

Dùng `poll(1, TimeUnit.SECONDS)` để chờ event có giới hạn rồi kiểm tra health, cờ dừng và thực hiện rescan định kỳ nếu cần. Mỗi lần có key vẫn phải drain events + reset.

### Trường hợp D — Theo dõi cây thư mục lớn

Cần map keys, đăng ký từng directory, đăng ký directory vừa xuất hiện, xử lý invalid keys và overflow. Có thể dùng một `WatchService` và một consumer loop, phân phối công việc nặng sang executor. Trong bài toán rất lớn, cân nhắc giới hạn tài nguyên và đặc tính OS.

### Trường hợp E — Đồng bộ trạng thái quan trọng

WatchService là **trigger** để đọc trạng thái mới, không phải nguồn dữ liệu duy nhất. Đăng ký watch, quét snapshot ban đầu, xử lý thay đổi rồi rescan khi overflow hoặc khởi động lại. Với yêu cầu exactly-once, cần cơ chế transaction/idempotency và nhật ký khác.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `take()` trả `null` khi không có event không?  
**Không.** Bình thường nó chờ đến khi có key; khi bị interrupt/đóng service có thể ném ngoại lệ.

**Câu 2.** `poll()` trả `null` có nghĩa là filesystem không có thay đổi nào từ trước đến giờ?  
**Không.** Chỉ có nghĩa chưa có key signalled sẵn trong service tại thời điểm gọi.

**Câu 3.** `poll(2, TimeUnit.SECONDS)` khác `take()` thế nào?  
**Nó chờ tối đa thời hạn**, rồi có thể trả `null`; `take` có thể chờ vô hạn.

**Câu 4.** Vì sao cần `key.reset()` sau khi xử lý `pollEvents()`?  
**Để đưa key về trạng thái sẵn sàng** cho lần báo hiệu tiếp theo nếu đăng ký còn hợp lệ.

**Câu 5.** `reset()` trả `false` thì phải làm gì?  
**Không tiếp tục tin vào registration đó**; bỏ key/hủy theo policy, nếu cần thì chờ thư mục tồn tại rồi đăng ký lại.

**Câu 6.** Một `WatchService` đăng ký `root` có tự động nhận `ENTRY_MODIFY` cho `root/nested/a.txt` không?  
**Không nên giả định.** Java NIO.2 thường chỉ watch direct entries, cần đăng ký `nested` riêng.

**Câu 7.** Có thể gọi `(Path) event.context()` cho `OVERFLOW` không?  
**Không.** Phải nhận diện OVERFLOW trước; dùng rescan để đồng bộ trạng thái.

**Câu 8.** Vừa thấy `ENTRY_CREATE` có được hiểu rằng producer đã đóng file và file hoàn chỉnh không?  
**Không.** Có thể producer vẫn đang ghi; cần giao thức publish/rename hoặc kiểm tra ổn định.

**Câu 9.** Vì sao `poll()` chạy trong vòng `while(true)` không có chờ có thể gây hại?  
**Vì busy spin**, tiêu tốn CPU liên tục khi không có event.

**Câu 10.** Có một tiến trình cần audit chính xác mọi lần file được ghi, WatchService có đủ không?  
**Thông thường không.** Events có thể gộp/mất và không bền qua restart; cần cơ chế audit/journal ở tầng thích hợp.

## 20. Tóm tắt

- **`WatchService.take()`**: đợi key được báo hiệu; hợp với dedicated watcher thread.
- **`WatchService.poll()`**: kiểm tra ngay, trả `null` nếu không có key; tránh busy loop.
- **`WatchService.poll(timeout, unit)`**: đợi có hạn, phù hợp vòng xử lý có nhiệm vụ định kỳ và shutdown.
- **Chu trình đúng**: đăng ký → lấy key → `pollEvents()` → xử lý `ENTRY_*`/`OVERFLOW` → `reset()` → tiếp tục.
- **`WatchEvent.context()` là đường dẫn tương đối** của mục trực tiếp trong thư mục đã đăng ký; resolve với directory của key.
- **Key invalid, OVERFLOW, restart, file đang ghi và theo dõi đệ quy** cần được xử lý rõ để watcher đáng tin cậy hơn.
- **WatchService là tín hiệu thay đổi, không phải log chính xác từng thao tác filesystem.** Khi yêu cầu consistency cao, kết hợp kiểm tra trạng thái thực tế, idempotency và recovery.

### Tài liệu Java 17

- [WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html)
- [WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html)
- [WatchEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html)
- [StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html)
- [Path.register](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#register(java.nio.file.WatchService,java.nio.file.WatchEvent.Kind...))
