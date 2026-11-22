# Mô hình đăng ký thư mục và nhận thông báo thay đổi với `WatchService` trong Java

## 1. Bài toán: ứng dụng muốn biết thư mục đã thay đổi

Một công cụ đồng bộ, trình quản lý tệp, dịch vụ xử lý file tải lên hoặc hệ thống tự cập nhật cấu hình thường cần biết **khi một entry trong thư mục được tạo, sửa hoặc xóa**. Nếu liên tục gọi `Files.list(...)` để quét toàn bộ thư mục mỗi vài mili-giây thì có thể tạo chi phí I/O lớn. Java NIO.2 cung cấp một mô hình **đăng ký quan sát thư mục và nhận thông báo** bằng `WatchService`.

Ví dụ khi một ứng dụng theo dõi thư mục `inbox`:

~~~text
Ứng dụng                                      File system
   |                                               |
   |  Tạo WatchService                             |
   |  Đăng ký inbox với CREATE, MODIFY, DELETE      |
   |---------------------------------------------->|
   |                                               |
   |                      Tạo inbox/new.txt        |
   |                                               |
   |  WatchKey được báo hiệu và đưa vào hàng đợi   |
   |<----------------------------------------------|
   |                                               |
   |  poll()/take() lấy WatchKey                    |
   |  pollEvents() đọc các WatchEvent               |
   |  Xử lý event, gọi reset()                      |
   |                                               |
   |  Tiếp tục nhận các thay đổi về sau            |
~~~

Đây là **sơ đồ vòng đời**, không phải mã Java hoặc cam kết rằng mọi nền tảng gửi sự kiện tức thì. `WatchService` thường ánh xạ xuống cơ chế notification bản địa của hệ điều hành; một số provider có thể dùng polling, vì vậy độ trễ và thứ tự event có thể khác.

**Đề bài chính:** *Mô hình đăng ký thư mục và nhận thông báo thay đổi*. Bài tập trung vào:

- `FileSystem.newWatchService()` tạo dịch vụ quan sát.
- `Path.register(...)` đăng ký **một thư mục** và các loại event muốn nhận.
- `WatchKey` đại diện cho một lượt đăng ký; quản lý trạng thái *ready/signalled/invalid*.
- `WatchService.poll()`, `poll(timeout, unit)` và `take()` lấy key từ hàng đợi.
- `WatchKey.pollEvents()` đọc các event và `WatchKey.reset()` kích hoạt khả năng được báo hiệu lại.
- `StandardWatchEventKinds.ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE` và `OVERFLOW`.
- Cách tạo path đầy đủ từ `WatchKey.watchable()` + `WatchEvent.context()`.
- Đóng service, hủy đăng ký, xử lý lỗi, trường hợp nhiều thư mục, recursive watching và các giới hạn chính xác.

**Phiên bản:** `WatchService` đã có từ Java 7; API này **vẫn được hỗ trợ trên Java 17, Java 21 và JDK hiện đại**. Code runnable dùng Java 21, `Path`/`Files`/`StandardCharsets` và try-with-resources. Nội dung chỉ sử dụng kiến thức đang áp dụng, **không đề xuất API lỗi thời hoặc legacy**.

## 2. Các thành phần trong mô hình WatchService

| Thành phần | Package / kiểu | Vai trò |
| --- | --- | --- |
| `FileSystem` | `java.nio.file.FileSystem` | Cung cấp `newWatchService()` của đúng filesystem |
| `WatchService` | `java.nio.file.WatchService` | Dịch vụ và hàng đợi các `WatchKey` được báo hiệu |
| `Path` | `java.nio.file.Path` | Đối tượng `Watchable` có thể gọi `register(...)` |
| `WatchKey` | `java.nio.file.WatchKey` | Token đăng ký một đối tượng, chứa các event đang chờ |
| `WatchEvent<?>` | `java.nio.file.WatchEvent` | Một sự kiện với `kind()`, `count()`, `context()` |
| `StandardWatchEventKinds` | `java.nio.file.StandardWatchEventKinds` | Các loại event chuẩn CREATE/MODIFY/DELETE/OVERFLOW |
| `TimeUnit` | `java.util.concurrent.TimeUnit` | Đơn vị thời gian cho `poll(timeout, unit)` |

Cần phân biệt ba khái niệm:

1. **`WatchService`** không trực tiếp là một event của file cụ thể. Nó chứa các key sẵn sàng xử lý.
2. **`WatchKey`** không chỉ tương ứng một event; một key cho **một đăng ký** có thể chứa **nhiều `WatchEvent`** đang chờ.
3. **`WatchEvent`** mô tả *kind*, *context* và *count* của thay đổi được quan sát. Nó **không phải một bản ghi transaction bất biến** của file system.

Một đối tượng `Path` có thể được đăng ký tới nhiều watch services. Mỗi đăng ký trả về một key liên quan đến service đó. Khi một thư mục đã đăng ký với chính service và đăng ký lại, Javadoc mô tả việc cập nhật tập event theo dõi và trả về key của đăng ký tương ứng; không cần tự tạo một dịch vụ mới cho mỗi loại event.

## 3. Bước 1 — tạo WatchService cho đúng file system

Cách cơ bản:

~~~java
Path directory = Path.of("inbox");

try (WatchService watcher =
        directory.getFileSystem().newWatchService()) {
    // Đăng ký và nhận event trong block này.
}
~~~

Đây là **đoạn minh họa**, cần import `java.nio.file.Path`, `WatchService` và xử lý `IOException`.

Tại sao `directory.getFileSystem().newWatchService()`?

- `Path` có thể thuộc default filesystem hoặc một provider khác.
- `WatchService` được tạo bởi filesystem, gắn với provider tương ứng.
- Dùng một watch service của provider không phù hợp để đăng ký `Path` có thể thất bại; đừng mặc định mọi provider tương thích.
- `FileSystem.newWatchService()` là **optional operation** đối với các file systems nói chung, có thể ném `UnsupportedOperationException` nếu không hỗ trợ. Theo Javadoc Java 21, default filesystem provider có hỗ trợ tạo watch service; các provider khác vẫn cần kiểm tra.

`WatchService` là `Closeable`, nên dùng `try-with-resources` để **đóng khi kết thúc**. Điều này đặc biệt quan trọng với dịch vụ chạy dài và các handles/resources hệ điều hành mà watcher giữ.

### 3.1. Không cần tạo một watcher mới cho mỗi file

Thông thường, ứng dụng có thể tạo **một WatchService cho một nhóm thư mục trong cùng filesystem**, rồi đăng ký nhiều `Path` vào dịch vụ đó và quản lý các `WatchKey`. Watcher theo dõi **các entry trong thư mục**, không phải mỗi lần mở/đọc từng file.

Nếu mục tiêu là theo dõi `report.txt`, cách thường dùng là **đăng ký thư mục cha** rồi lọc event có `context()` bằng tên `report.txt`. Không nên mặc định đăng ký trực tiếp một regular file bằng `Path.register` trên default provider: Javadoc Java 21 mô tả việc đăng ký một **directory tồn tại** để quan sát các entry của nó.

## 4. Bước 2 — đăng ký thư mục bằng `Path.register`

Ví dụ đăng ký ba loại event:

~~~java
WatchKey key = directory.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);
~~~

Đây là đoạn minh họa với `Path directory` và `WatchService watcher` đã được tạo trước đó.

**Các điều kiện cơ bản:**

- `directory` phải chỉ tới một thư mục có thật và có thể truy cập.
- `watcher` phải còn mở và phù hợp với filesystem của directory.
- Tập event yêu cầu phải được provider hỗ trợ.
- Có thể phát sinh `IOException`, `NotDirectoryException` (một subtype khi provider lựa chọn), `UnsupportedOperationException` đối với option/event không hỗ trợ, `ClosedWatchServiceException` nếu watcher đã đóng.
- Event được quan sát **sau khi đăng ký**; không coi registration là phép trả về danh sách file hiện đang có.

Có một overload khác nhận mảng kinds và các `WatchEvent.Modifier...`. Java SE 21 **không định nghĩa modifier chuẩn nào** cho việc đăng ký này; các modifier có thể phụ thuộc provider. Bài học cơ bản nên dùng `register(watcher, ENTRY_...)` thay vì dựa vào modifier không phổ quát.

### 4.1. Các loại sự kiện chuẩn

| Kind | Ý nghĩa | `context()` | `count()` |
| --- | --- | --- | --- |
| `ENTRY_CREATE` | Một entry được tạo **hoặc di chuyển vào** thư mục | `Path` tương đối tới tên entry | Theo Javadoc: `1` |
| `ENTRY_DELETE` | Một entry bị xóa **hoặc di chuyển ra khỏi** thư mục | `Path` tương đối tới tên entry | Theo Javadoc: `1` |
| `ENTRY_MODIFY` | Một entry trong thư mục được quan sát là đã sửa | `Path` tương đối tới tên entry | Có thể `1` hoặc lớn hơn |
| `OVERFLOW` | Provider biết có sự kiện bị mất/bỏ | Phụ thuộc provider, có thể `null` | Có thể lớn hơn `1` |

**`OVERFLOW` không cần đăng ký riêng** mà vẫn có thể được trả về. Khi nó xuất hiện, chương trình **không còn chắc mình đã thấy mọi thay đổi**; nên quét/đối chiếu lại trạng thái thư mục theo policy.

### 4.2. Rename và di chuyển không có một loại sự kiện chuẩn riêng

`StandardWatchEventKinds` không có event `ENTRY_RENAME` chuẩn. Một file được di chuyển **ra khỏi** thư mục có thể tạo `ENTRY_DELETE` tại nguồn; một entry được di chuyển **vào** có thể tạo `ENTRY_CREATE` tại đích. Việc ánh xạ rename cụ thể còn phụ thuộc filesystem/provider.

Đừng xây code dựa trên giả định rằng luôn nhận chính xác một cặp CREATE/DELETE, đúng thứ tự, kèm ID giao dịch. `WatchService` là cơ chế **thông báo về thay đổi được quan sát**, không phải nhật ký transaction chi tiết.

## 5. Bước 3 — nhận key qua `poll` hoặc `take`

Khi event liên quan đến thư mục được phát hiện, `WatchKey` có thể được **đánh dấu signalled** và đưa vào hàng đợi của `WatchService`.

### 5.1. Ba cách lấy key

| Phương thức | Khi không có key | Phù hợp |
| --- | --- | --- |
| `watcher.poll()` | Trả `null` ngay | Vòng lặp tích hợp với công việc khác, cần kiểm tra tức thì |
| `watcher.poll(timeout, unit)` | Chờ tối đa thời gian rồi trả `null` nếu vẫn chưa có | Worker có timeout hoặc cần phản hồi stop signal định kỳ |
| `watcher.take()` | Chờ cho đến khi có key | Luồng chuyên trách lắng nghe liên tục |

Cần lưu ý `poll(timeout, unit)` và `take()` có thể ném `InterruptedException` nếu luồng bị interrupt; chúng ném `ClosedWatchServiceException` nếu watcher đóng. Nếu dùng `take()` trong một thread riêng, thiết kế cách dừng thread bằng close/interruption có kiểm soát thay vì dùng vòng `while(true)` không thoát.

Ví dụ:

~~~java
WatchKey key = watcher.poll(5, TimeUnit.SECONDS);
if (key == null) {
    // Hết thời gian chờ, KHÔNG có key được trả về.
}
~~~

Đây là đoạn minh họa, cần `TimeUnit` và xử lý `InterruptedException`. **`null` không có nghĩa hệ thống tệp sẽ không thay đổi**; nó chỉ phản ánh tình trạng hàng đợi trong thời gian đã chờ.

### 5.2. WatchService trả **key**, không phải trả trực tiếp một `WatchEvent`

~~~text
WatchService queue:
    keyA -> event list [CREATE, MODIFY]
    keyB -> event list [DELETE]
    ...
~~~

Sơ đồ mang tính khái niệm. Một thư mục đăng ký có thể nhận nhiều event trong lúc key đã signalled. Do đó:

- Lấy một key bằng `poll` / `take`.
- Gọi `key.pollEvents()` để lấy và tiêu thụ tất cả event đang chờ tại thời điểm đó.
- Xử lý từng event dựa trên `kind` và `context`.
- **Gọi `key.reset()` sau khi xử lý**, nếu key vẫn còn hợp lệ.

Không được nhầm một vòng `poll()` trả một key với “chắc chắn chỉ có một file thay đổi”.

## 6. Bước 4 — đọc `WatchEvent` và dựng Path đầy đủ

Trong ba loại `ENTRY_*`, `event.context()` là tên `Path` **tương đối so với directory đã đăng ký**. Nó **không phải full absolute path**, và ở event `OVERFLOW` context có thể là `null`.

Một đoạn đọc event an toàn về kiểu:

~~~java
for (WatchEvent<?> event : key.pollEvents()) {
    WatchEvent.Kind<?> kind = event.kind();

    if (kind == StandardWatchEventKinds.OVERFLOW) {
        // Một số event đã mất: cần đánh giá/quét lại directory.
        continue;
    }

    if (event.context() instanceof Path relative) {
        Path watchedDirectory = (Path) key.watchable();
        Path affected = watchedDirectory.resolve(relative);

        System.out.println(kind.name() + ": " + affected);
    }
}
~~~

Đây là **đoạn minh họa**, `key` được lấy từ watcher của những directory dạng `Path`, cần import `WatchEvent`, `WatchKey`, `Path` và `StandardWatchEventKinds`. Kiểm tra `instanceof Path` giúp tránh ép context của `OVERFLOW` hoặc event khác sang `Path` bừa bãi.

**Tại sao dùng `key.watchable()`?** Vì với một watcher theo dõi nhiều thư mục, event đến từ **một registration cụ thể**. `key.watchable()` trả đối tượng đã đăng ký, thông thường là `Path` của thư mục. Kết hợp với `relative` mới có được tên file liên quan.

Ví dụ nếu `directory = /srv/inbox`, `context = note.txt`, thì tên đầy đủ được dựng bằng `directory.resolve(context)` là `/srv/inbox/note.txt` (đây là ví dụ về tên, không khẳng định file vẫn tồn tại).

### 6.1. Không dùng event như ảnh chụp bất biến

Một event `ENTRY_MODIFY` không bảo đảm thao tác ghi file đã hoàn tất. Javadoc cảnh báo khi nhận event MODIFY, chương trình khác **có thể vẫn đang viết**. Vì vậy:

- Trước khi đọc file, cân nhắc chính sách chờ/hoàn tất tải lên hoặc giao thức ghi tạm rồi đổi tên.
- Khi mở file, vẫn xử lý `IOException` / `NoSuchFileException`.
- Nếu file vừa bị xóa, `ENTRY_DELETE` cung cấp **tên cũ**, không thể kỳ vọng `Files.readString(deletedPath)` vẫn chạy.
- Không xem `CREATE` là bảo đảm file đã được ghi đủ; file có thể mới tạo rỗng rồi người viết bổ sung nội dung.
- Không dùng `WatchEvent.count()` để suy ra số lần ghi logic chính xác của ứng dụng.

## 7. Bước 5 — gọi `WatchKey.reset()` đúng thời điểm

**Đây là điểm quyết định để nhận các event tiếp theo.**

Theo mô hình trạng thái của `WatchKey`:

~~~text
register()
    |
    v
  READY
    |
    | có thay đổi được phát hiện
    v
  SIGNALLED ----> WatchService queue
    |                     |
    | <--- poll()/take() --|
    |
    | pollEvents() và xử lý
    | reset()
    v
  READY (nếu key còn valid)
    |
    | có event mới
    v
  SIGNALLED ...

CANCELLED / CLOSED / không còn truy cập được
    |
    v
  INVALID
~~~

**Khi key đã signalled nhưng chưa được reset**, các event mới có thể tiếp tục được gom vào key, nhưng key **không được xếp hàng lại** một lần nữa. Vì thế bỏ quên `reset()` có thể khiến bạn thấy ứng dụng “chỉ nhận thông báo lần đầu”.

Mẫu loop cốt lõi:

~~~java
WatchKey key = watcher.take();

for (WatchEvent<?> event : key.pollEvents()) {
    // Phân loại và xử lý từng event.
}

boolean valid = key.reset();
if (!valid) {
    // Đăng ký không còn hợp lệ: bỏ key, hoặc quyết định đăng ký lại.
}
~~~

Đây là **mẫu minh họa**, cần xử lý `InterruptedException`/các lỗi khác và watcher đã được tạo. Mẫu trên ngắn để nhấn vòng đời; ví dụ runnable trong phần 9 có xử lý timeout và `OVERFLOW`.

### 7.1. `reset()` trả false khi nào?

Nếu đăng ký đã bị hủy, watcher bị đóng hoặc đối tượng theo dõi không còn khả dụng theo provider, `key.reset()` có thể trả `false`. Trong tình huống đó:

- Không tiếp tục giả định watcher còn theo dõi thư mục.
- Xóa key khỏi bảng quản lý nếu có nhiều thư mục.
- Nếu directory được tạo lại sau khi bị xóa, có thể cần **đăng ký mới**, không coi key đã invalid tự phục hồi.
- Đừng gọi `reset()` rồi bỏ qua boolean mãi mãi trong một dịch vụ chạy dài.

### 7.2. `cancel` khác `close`

| Thao tác | Ảnh hưởng |
| --- | --- |
| `key.cancel()` | Hủy **một đăng ký**, key tương ứng trở thành invalid |
| `watcher.close()` | Đóng **cả WatchService**, làm các key liên quan invalid, giải phóng service |
| `key.isValid()` | Hỏi key hiện còn hợp lệ không |
| `key.watchable()` | Trả đối tượng đã đăng ký ngay cả sau khi key bị hủy |

Theo Javadoc, key đã queued khi `cancel()` có thể **vẫn còn trong queue** cho tới khi được poll/take ra; các event đang chờ cũng có thể vẫn được đọc. Vì vậy việc nhận một key từ queue **không đồng nghĩa key đó còn valid**.

Khi service đóng, thread đang chờ `take()` hoặc `poll(timeout)` có thể nhận `ClosedWatchServiceException`. Đây là cơ chế dừng hữu ích, nhưng cần tránh nhầm với lỗi file thay đổi bình thường.

## 8. Thứ tự và độ tin cậy của event: hiểu đúng giới hạn

Một chương trình có thể quan sát:

~~~text
ENTRY_CREATE note.txt
ENTRY_MODIFY note.txt
ENTRY_MODIFY note.txt
ENTRY_DELETE note.txt
~~~

Đây là **một minh họa khả dĩ**, không phải lời hứa về thứ tự và số lượng thông báo trên mọi nền tảng.

### 8.1. Một lần ghi có thể tạo nhiều MODIFY

Tùy filesystem và cách ứng dụng ghi, một thao tác ghi có thể dẫn đến một hoặc nhiều `ENTRY_MODIFY`, và những sự kiện có thể được **gộp/coalesce** bằng `event.count()`. Theo Javadoc, `ENTRY_MODIFY` có `count >= 1`. Không dùng số MODIFY nhận được để tính số lần lưu file chính xác.

### 8.2. Event có thể đến muộn, gộp hoặc thiếu

Javadoc `WatchService` nhấn mạnh tính phụ thuộc nền tảng:

- Có provider sử dụng thông báo native, có provider phát hiện bằng polling.
- Thời điểm phát hiện, độ trễ, thứ tự event có thể khác nhau.
- File được tạo rồi xóa quá nhanh có thể không được provider polling phát hiện.
- Với một số filesystem không nằm trên thiết bị local, thay đổi từ hệ thống từ xa có thể **không được bảo đảm** nhận diện.
- Provider có giới hạn dung lượng queue; khi mất event và biết điều đó, nó phát sinh `OVERFLOW`.

Đừng biến WatchService thành nguồn dữ liệu duy nhất cho một nghiệp vụ yêu cầu **không mất bất kỳ bản ghi nào**. Khi độ đúng quan trọng, phối hợp thông báo với **đối chiếu/snapshot** trạng thái thực và cơ chế định danh/version của hệ thống dữ liệu.

### 8.3. `OVERFLOW` yêu cầu đối chiếu lại, không bỏ qua

~~~java
if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
    // Đánh dấu trạng thái thư mục cần đồng bộ lại.
    // Quét lại nội dung và đối chiếu với index/trạng thái đã lưu.
}
~~~

Đây là mẫu minh họa. `OVERFLOW` có thể không chứa `Path`. Chương trình không nên cast `event.context()` thành tên file khi gặp `OVERFLOW`.

Nếu ứng dụng xây một chỉ mục file, cách xử lý hợp lý khi overflow là **đánh dấu chỉ mục không còn đáng tin, quét lại theo chính sách, cập nhật index và tiếp tục theo dõi**. Cần thiết kế chống race giữa lúc quét và lúc event tiếp tục đến, không ngầm hứa một lần scan là transaction.

## 9. Chương trình Java 21 chạy được: đăng ký, nhận CREATE/MODIFY/DELETE và cancel

Chương trình sau tạo **một thư mục tạm riêng** và một file `note.txt`. Trong cùng thread, nó:

1. Tạo WatchService bằng filesystem của directory.
2. Đăng ký directory với ba event chuẩn và lấy `WatchKey`.
3. Tạo file rồi đợi `ENTRY_CREATE` tương ứng.
4. Ghi nội dung rồi đợi `ENTRY_MODIFY`.
5. Xóa file rồi đợi `ENTRY_DELETE`.
6. Hủy đăng ký và xác minh key invalid.
7. Tự đóng WatchService và dọn các tài nguyên do chương trình tạo.

Vì đây là bài test hành vi của filesystem, nó dùng `poll(timeout)` tối đa 5 giây cho **từng event**, không dùng `Thread.sleep(...)` để giả định event đã xuất hiện. Helper `awaitEvent(...)`:

- Lấy key từ hàng đợi.
- Đọc **tất cả event** qua `pollEvents()`.
- Kiểm tra kind, context relative và directory được đăng ký.
- Gọi `reset()` sau mỗi batch event.
- Báo lỗi khi key invalid/overflow, vì demo không có cơ chế rescan.
- Trả `false` nếu hết timeout mà chưa thấy kind và tên mong đợi.

Đoạn này cố ý **không làm bộ monitor production đầy đủ**. Provider khác có thể không phát hiện MODIFY như Windows default filesystem, vì thế stdout dưới đây được ghi rõ là **kết quả thực tế trên môi trường đã thử**, không phải kết quả bắt buộc của mọi OS.

Tạo file `src/main/java/demo/WatchRegistrationExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.concurrent.TimeUnit;

public final class WatchRegistrationExample {
    private WatchRegistrationExample() {}

    private static boolean awaitEvent(WatchService watcher,
            Path expectedDirectory, Path expectedName,
            WatchEvent.Kind<Path> kind, long timeoutMillis)
            throws IOException, InterruptedException {
        long deadline = System.nanoTime()
                + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);

        for (;;) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0L) {
                return false;
            }

            WatchKey key = watcher.poll(remaining, TimeUnit.NANOSECONDS);
            if (key == null) {
                return false;
            }

            boolean found = false;
            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                    throw new IOException("Overflow: rescan directory required");
                }
                if (event.kind() == kind
                        && event.context() instanceof Path relative
                        && relative.equals(expectedName)
                        && key.watchable().equals(expectedDirectory)) {
                    found = true;
                }
            }

            if (!key.reset()) {
                throw new IOException("WatchKey was invalidated");
            }
            if (found) {
                return true;
            }
        }
    }

    public static void main(String[] args)
            throws IOException, InterruptedException {
        Path directory = Files.createTempDirectory("watch-lesson-");
        Path target = directory.resolve("note.txt");
        try {
            try (WatchService watcher =
                    directory.getFileSystem().newWatchService()) {
                WatchKey registration = directory.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                System.out.println("watchable-is-directory="
                        + directory.equals(registration.watchable()));
                System.out.println("key-valid-after-register="
                        + registration.isValid());

                Files.createFile(target);
                System.out.println("create-event="
                        + awaitEvent(watcher, directory, target.getFileName(),
                                StandardWatchEventKinds.ENTRY_CREATE, 5000));

                Files.writeString(target, "hello",
                        StandardCharsets.UTF_8,
                        StandardOpenOption.WRITE,
                        StandardOpenOption.TRUNCATE_EXISTING);
                System.out.println("modify-event="
                        + awaitEvent(watcher, directory, target.getFileName(),
                                StandardWatchEventKinds.ENTRY_MODIFY, 5000));

                Files.delete(target);
                System.out.println("delete-event="
                        + awaitEvent(watcher, directory, target.getFileName(),
                                StandardWatchEventKinds.ENTRY_DELETE, 5000));

                registration.cancel();
                System.out.println("key-valid-after-cancel="
                        + registration.isValid());
            }
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch/chạy từ thư mục chứa `src/` trên JDK 21:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/WatchRegistrationExample.java
java -cp out demo.WatchRegistrationExample
~~~

**Stdout chính xác trên default Windows filesystem đã kiểm thử:**

~~~text
watchable-is-directory=true
key-valid-after-register=true
create-event=true
modify-event=true
delete-event=true
key-valid-after-cancel=false
~~~

### 9.1. Giải thích stdout

**`watchable-is-directory=true`:** `WatchKey.watchable()` là `Path` directory đã đăng ký. Đây là cơ sở để ghép `event.context()` thành một tên đường dẫn trong thư mục.

**`key-valid-after-register=true`:** một `WatchKey` mới được đăng ký và đang hợp lệ.

**`create-event=true`:** sau `Files.createFile(target)`, watcher trả event `ENTRY_CREATE` có context là `note.txt` theo directory đã đăng ký. Chương trình **đợi đúng event**, không chỉ kiểm tra sự tồn tại của file.

**`modify-event=true`:** sau `Files.writeString(...)`, file system thử nghiệm gửi `ENTRY_MODIFY`. Các provider khác có thể coalesce hoặc không phát hiện tương tự; phải xử lý timeout và tính phụ thuộc nền tảng.

**`delete-event=true`:** sau `Files.delete(target)`, chương trình đã nhận `ENTRY_DELETE` đúng tên.

**`key-valid-after-cancel=false`:** hủy key bằng `cancel()` làm registration invalid. Đây là hành động tường minh, không cần xóa chính directory để minh họa.

### 9.2. Hạn chế của helper demo

Helper dùng `throw new IOException(...)` khi `OVERFLOW` hay key invalid để **không báo giả rằng chỉ mục dữ liệu còn đầy đủ**. Trong ứng dụng production, cần cơ chế rescan và khôi phục đăng ký thay vì chỉ thoát.

Timeout 5 giây là **giới hạn chờ của bài test**, không phải một bảo đảm Javadoc rằng mọi event sẽ đến trong 5 giây. Trên provider chậm, remote storage hoặc hệ thống hạn chế sự kiện, một trong các dòng quan sát có thể in `false`. Khi đó hãy xem lại khả năng hỗ trợ và chính sách kiểm thử; không lấy stdout của một máy làm hợp đồng chung.

Code kiểm tra nội dung event mà không in tên đường dẫn tuyệt đối của thư mục tạm, vì tên random của `createTempDirectory` khác nhau ở mỗi lần chạy. Toàn bộ file được tạo trong thư mục tạm riêng; chương trình không sửa file có sẵn ngoài phạm vi đó.

## 10. Vòng lặp theo dõi liên tục của một dịch vụ thực tế

Với ứng dụng đang chạy lâu dài, thay vì tự tạo/sửa/xóa trong main, một thread chuyên nhận event có thể dùng mẫu sau:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    WatchKey key = watcher.take();
    Path dir = (Path) key.watchable();

    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
            // Mark dirty/rescan dir: một số event có thể đã mất.
            continue;
        }

        if (event.context() instanceof Path relative) {
            Path changed = dir.resolve(relative);
            // Xếp job kiểm tra trạng thái hiện tại của changed vào queue.
        }
    }

    if (!key.reset()) {
        // Gỡ key không còn hợp lệ và quyết định có đăng ký lại.
    }
}
~~~

Đây là **mẫu minh họa vòng lặp**, không phải chương trình độc lập: `watcher` phải được khai báo và mở, code cần xử lý `InterruptedException`, `ClosedWatchServiceException` và dừng phù hợp. Phần xử lý event nên **nhanh**, đưa công việc nặng vào worker queue có kiểm soát để tránh làm tồn đọng events và `OVERFLOW`.

### 10.1. Quy tắc khi xử lý lâu dài

- **Luôn reset sau khi xử lý một key.** Nếu handler ném exception, cần chính sách `try/finally` hoặc xử lý riêng để không vô tình bỏ việc reset mãi mãi.
- **Đừng reset trước khi xử lý các event đã nhận** trong thiết kế nhiều luồng cùng tiêu thụ một key; điều này có thể khiến cùng một đăng ký được xử lý đồng thời. Javadoc khuyên chỉ reset **sau** khi xử lý xong event của key.
- **Kiểm tra `key.isValid()` / kết quả `reset()`** trước khi coi directory vẫn đang được theo dõi.
- **Không block vô hạn mà không có phương án shutdown.** `close()` của service sẽ đánh thức thread đang chờ với `ClosedWatchServiceException`; interrupt cũng cần được xử lý theo chính sách hủy công việc.
- **Không coi event là đơn vị công việc duy nhất.** Với file có nhiều MODIFY, có thể debounce/coalesce ở tầng ứng dụng và đọc trạng thái hiện tại một lần, nhưng phải giữ chính sách phát hiện lỗi/overflow.
- **Không tái phát sóng tên file chưa kiểm tra** như dữ liệu tin cậy cho consumer có quyền cao. File có thể bị thay qua symlink/rename giữa nhận event và mở.

### 10.2. `InterruptedException`

Trong method có `throws InterruptedException` (như ví dụ chạy), Java có thể truyền lỗi lên caller. Trong một worker loop tự catch:

~~~java
try {
    WatchKey key = watcher.take();
    // Xử lý key.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Thoát vòng lặp và giải phóng tài nguyên theo chính sách.
}
~~~

Đây là đoạn minh họa. Không tự nuốt interruption rồi tiếp tục vòng lặp bất tận. Nếu đã gọi `Thread.currentThread().interrupt()`, caller cần biết trạng thái interrupt để kết thúc/propagate đúng.

## 11. Theo dõi nhiều thư mục, không chỉ một directory

Một `WatchService` có thể nhận key từ nhiều thư mục đã đăng ký. Mẫu lưu mối liên hệ:

~~~java
Map<WatchKey, Path> watched = new HashMap<>();

WatchKey alphaKey = alpha.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE);
watched.put(alphaKey, alpha);

WatchKey betaKey = beta.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE);
watched.put(betaKey, beta);

// Khi poll/take một WatchKey:
// Path sourceDirectory = watched.get(key);
// Nếu reset() false: watched.remove(key);
~~~

Đây là đoạn minh họa có các `Path alpha`, `beta`, `WatchService watcher`; cần import `Map`, `HashMap`. Đối với các thư mục dạng `Path`, cũng có thể lấy ngay `(Path) key.watchable()`. Bảng `Map` có ích nếu ứng dụng cần thêm metadata, ID công việc hoặc policy cho từng đăng ký.

**Khi thư mục đã đăng ký bị xóa hoặc không còn khả dụng**, key có thể tự invalid. Thậm chí một thư mục được rename/move có thể có behavior phụ thuộc provider; `key.watchable()` không bảo đảm mãi là đường dẫn còn tồn tại. Phải xử lý key bị mất và cơ chế đăng ký lại với path hợp lệ nếu nghiệp vụ cần.

## 12. WatchService không theo dõi đệ quy tự động

Đây là giới hạn quan trọng của mô hình **đăng ký một thư mục**:

~~~text
project/                  Đã register WatchService
  README.md               Thấy event trực tiếp trong project/
  src/                    Thấy event tạo/xóa entry src/
    App.java              KHÔNG tự động theo dõi App.java nếu src/ chưa register
~~~

Nếu cần quan sát mọi thư mục con, ứng dụng phải quản lý **đăng ký từng directory cần thiết**:

1. Đăng ký directory gốc.
2. Duyệt các directory con ban đầu và đăng ký từng cái.
3. Khi nhận `ENTRY_CREATE` cho một entry có vẻ là thư mục mới, kiểm tra trạng thái thực và đăng ký directory đó.
4. Nếu directory mới đã có sẵn nhiều con khi nhận event, có thể cần quét/đăng ký ngay cả các descendants.
5. Khi directory biến mất hoặc key invalid, gỡ khỏi bảng quản lý.
6. Khi `OVERFLOW`, quét/đối chiếu lại cây và đăng ký thiếu.

**Có race trong bootstrap:** file có thể thay đổi giữa “duyệt cây ban đầu” và “đăng ký”. Chỉ register trước hoặc chỉ scan trước không tự biến hai thao tác thành snapshot atomic. Với mục tiêu kiểm kê chính xác, cần thiết kế gộp sự kiện/scan và reconciliation có thể lặp lại, hoặc dựa vào cơ chế snapshot/journal của storage khi cần bảo đảm mạnh hơn.

### 12.1. Recursive watching và symbolic links

Nếu dự định đăng ký mọi thư mục con, cần xác định chính sách **có đi theo symlink hay không**. Theo link có thể:

- Đưa watcher **ra ngoài root** ban đầu.
- Tạo cycle hoặc nhiều alias tới cùng directory.
- Làm số lượng đăng ký tăng lớn.
- Tạo rủi ro truy cập/xóa dữ liệu không thuộc phạm vi được phép.

`Files.walkFileTree` (khi được sử dụng để tìm các directory cần đăng ký) có `maxDepth` và `FileVisitOption.FOLLOW_LINKS`, nhưng **giới hạn độ sâu không tự là sandbox**. Không sao chép một ví dụ recursive registration có `FOLLOW_LINKS` vào ứng dụng quản trị file do người dùng chỉ định khi chưa có chính sách an toàn.

## 13. Khi cần một danh mục file chính xác, WatchService chỉ là tín hiệu

Một ứng dụng có thể duy trì index:

~~~text
Đăng ký watch + inventory ban đầu
            |
   nhận CREATE / MODIFY / DELETE
            |
   đánh dấu path cần cập nhật
            |
   đọc/kiểm tra trạng thái thực tế
            |
   cập nhật index có version
            |
   OVERFLOW -> rescan/reconcile
~~~

Đây là kiến trúc minh họa, không phải một protocol bảo đảm transaction.

Các lý do không thể xem event là nguồn dữ liệu đầy đủ duy nhất:

- Event có thể gộp hoặc được phát hiện trễ.
- Có thể có `OVERFLOW`.
- Remote changes có thể không được phát hiện.
- Directory/file có thể thay đổi **sau** khi event xảy ra nhưng **trước** khi ứng dụng đọc.
- Một file có thể bị tạo rồi xóa giữa các lần poll mà không có snapshot ở thời điểm trung gian.

Vì vậy khi xử lý file mới:

- Cân nhắc chiến lược uploader **ghi file tạm rồi rename** để thông báo “đã sẵn sàng” dựa trên giao thức riêng, không chỉ `ENTRY_CREATE`.
- Cần xử lý file biến mất, lỗi quyền, byte chưa ghi xong và file bị thay thế.
- Nếu phải bảo đảm không mất dữ liệu, dùng queue bền vững, journal, transactional storage hoặc reconciliation theo hệ thống đang dùng. WatchService **không cam kết** được tất cả thay đổi như một event log durable.

## 14. Những lỗi thường gặp

| Hiểu nhầm / lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| “WatchService theo dõi từng file bằng đăng ký file thường” | Không khớp hợp đồng `Path.register` chuẩn cho directory | Register thư mục cha, lọc `context` |
| Đăng ký sau khi file đã được tạo rồi trông đợi CREATE cũ | Không có cơ chế replay các entry đã tồn tại | Duyệt danh mục ban đầu riêng |
| Gọi `watcher.take()` một lần rồi kết thúc | Chỉ xử lý một batch | Loop cho tới khi dừng có kiểm soát |
| Xem mỗi `WatchKey` như một event duy nhất | Bỏ qua event khác trong `pollEvents()` | Duyệt toàn bộ list event |
| Bỏ quên `key.reset()` | Key đã signalled không được queue lại | Reset sau khi xử lý và xem boolean |
| Reset trước khi các thread xử lý xong key | Có thể xử lý cùng registration đồng thời | Phối hợp consumer, reset sau xử lý |
| Chỉ cast mọi `context()` thành `Path` | `OVERFLOW` có context null hoặc provider-specific | Kiểm tra kind và kiểu context |
| Nghĩ mọi `ENTRY_MODIFY` là file đã ghi xong | Đọc file dở hoặc race | Giao thức hoàn tất ghi/kiểm tra lại |
| Nghĩ số MODIFY bằng số lần ghi | Coalescing và platform differences | Reconcile trạng thái hiện tại |
| Bỏ qua `OVERFLOW` | Mất sự kiện nhưng không biết index sai | Đánh dấu dirty và rescan |
| Nghĩ WatchService tự recursive | Bỏ sót thay đổi trong thư mục con | Register từng directory cần thiết |
| Dùng `Files.walk` bootstrap mà không đóng stream | Rò rỉ directory resources | Try-with-resources |
| Tin remote/network FS phải phát event | Hỏng đồng bộ khi remote changes không phát hiện | Kiểm tra provider và có fallback |
| Bỏ qua `reset() == false` | Tiếp tục nghĩ key còn valid | Gỡ key và đăng ký lại khi hợp lý |
| Không đóng watcher khi shutdown | Rò rỉ OS resources/thread treo | Try-with-resources / close |
| Coi WatchService là hệ thống bảo mật | Symlink/file có thể đổi giữa event và open | Quyền OS, path validation, TOCTOU protection |
| Dùng busy loop `poll()` liên tục | Tốn CPU | `take()` hoặc `poll(timeout)` |
| Nuốt `InterruptedException` | Khó shutdown ứng dụng | Propagate hoặc restore interrupt và thoát |
| Cho rằng rename là một kind chuẩn | Bỏ event thực tế | Thiết kế theo CREATE/DELETE và state reconciliation |

## 15. Bài tập có đáp án

**Câu 1.** Khi chỉ muốn biết `config.json` trong `/app/config` có thay đổi, nên đăng ký `config.json` hay thư mục cha?

**Đáp án:** Đăng ký `/app/config` với những `StandardWatchEventKinds` cần thiết, rồi so `event.context()` với `Path.of("config.json")`. Event context cho ENTRY_* là đường dẫn tương đối so với directory được đăng ký.

**Câu 2.** `watcher.take()` trả trực tiếp `WatchEvent` không?

**Đáp án:** Không. Nó trả `WatchKey` đã signalled; gọi `key.pollEvents()` để lấy danh sách các event đã tích lũy.

**Câu 3.** Nếu quên `key.reset()`, điều gì có thể xảy ra?

**Đáp án:** Key vẫn ở trạng thái signalled; các event mới có thể dồn lại nhưng key không được queue lại, nên chương trình có vẻ ngừng được đánh thức.

**Câu 4.** `poll()` và `poll(5, SECONDS)` khác nhau ở điểm nào?

**Đáp án:** `poll()` trả ngay, có thể null; overload có timeout đợi tối đa khoảng thời gian được chỉ định trước khi trả null.

**Câu 5.** Có phải `ENTRY_CREATE` bảo đảm uploader đã ghi đủ nội dung file?

**Đáp án:** Không. Event chỉ cho biết entry được quan sát là đã tạo; writer có thể tiếp tục ghi sau đó.

**Câu 6.** Có phải hai lần sửa file luôn tạo chính xác hai `ENTRY_MODIFY` có `count=1`?

**Đáp án:** Không. Provider có thể phát nhiều hoặc coalesce; `count` của MODIFY có thể lớn hơn một. Không đếm số lần save logic bằng số event.

**Câu 7.** Khi gặp `OVERFLOW` có `context == null`, nên làm gì?

**Đáp án:** Không cast context thành `Path`. Đánh dấu dữ liệu theo dõi không còn đủ tin cậy, quét/đối chiếu lại directory theo chính sách.

**Câu 8.** Sau `key.cancel()`, `key.isValid()` là gì?

**Đáp án:** `false`. Hủy đăng ký là vĩnh viễn đối với key đó; nếu cần tiếp tục theo dõi phải đăng ký mới.

**Câu 9.** Watcher đăng ký thư mục `root`; file `root/sub/a.txt` bị sửa. Có chắc nhận event của `a.txt` không?

**Đáp án:** Không. Đăng ký root chỉ theo dõi các entry trực tiếp; cần đăng ký riêng `sub` nếu phải theo dõi file con trong đó.

**Câu 10.** `WatchService` có bảo đảm nhận tất cả sửa đổi trên remote filesystem và file tồn tại cực ngắn không?

**Đáp án:** Không. Javadoc nêu tính phụ thuộc provider, có thể dùng polling và không bảo đảm phát hiện thay đổi do hệ thống từ xa.

**Câu 11.** Vì sao cần `key.watchable()` nếu có nhiều thư mục đăng ký?

**Đáp án:** Để xác định directory gốc của những event trong key; ghép directory với relative context để có path liên quan.

**Câu 12.** `watcher.close()` có vai trò gì với một thread đang block `take()`?

**Đáp án:** Service đóng, các key bị invalid; thread chờ có thể bị đánh thức bằng `ClosedWatchServiceException`, giúp triển khai shutdown đúng cách.

**Câu 13.** Có thể chỉ dùng WatchService để bảo đảm index luôn khớp 100% trong hệ thống có write đồng thời và overflow không?

**Đáp án:** Không. Cần snapshot/reconciliation, xử lý race, nghiệp vụ ghi file và cơ chế durable khác nếu yêu cầu không mất dữ liệu.

**Câu 14.** Một application muốn bỏ lỡ ít sự kiện khi khởi động, đăng ký watch và scan ban đầu có tự là thao tác nguyên tử không?

**Đáp án:** Không. Cả hai là các thao tác riêng, file có thể thay giữa chúng. Thiết kế cần hợp nhất event với scan và đối chiếu lại theo chính sách.

## 16. Checklist và nguồn chính thức

- [ ] Tạo `WatchService` từ filesystem của directory, và đóng service khi kết thúc.
- [ ] Đăng ký **directory đang tồn tại**, không mặc định đăng ký regular file.
- [ ] Chọn kinds cần thiết: `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE`.
- [ ] Nhận `WatchKey` bằng `poll`/`poll(timeout)`/`take` theo mô hình thread.
- [ ] Gọi `pollEvents()` và xử lý tất cả events trong key.
- [ ] Với `ENTRY_*`, `context` là relative `Path`; dựng tên bằng `key.watchable()` và `resolve(...)`.
- [ ] Xử lý `OVERFLOW` bằng rescan/reconciliation, không ép context null sang `Path`.
- [ ] Luôn gọi `key.reset()` sau xử lý và kiểm tra kết quả.
- [ ] Phân biệt `cancel()` của key với `close()` của watcher.
- [ ] Khi shutdown, quản lý interruption và `ClosedWatchServiceException`.
- [ ] Không cho rằng có event MODIFY nghĩa là writer đã hoàn tất.
- [ ] Không giả định số lượng/thứ tự/timing event giống nhau trên mọi OS.
- [ ] Theo dõi subtree bằng cách quản lý đăng ký **từng thư mục**; chú ý symlink/cycle.
- [ ] Không coi event là snapshot hoặc log transaction bền vững.
- [ ] Nếu phải đồng bộ dữ liệu chính xác, có cơ chế scan, đối chiếu, overflow và xử lý race.
- [ ] Sử dụng API Java hiện đại đang được hỗ trợ; không lệ thuộc modifier/provider-specific khi không cần.

**Nguồn chính thức (Java SE 21 và hướng dẫn Java hiện hành):**

- [Java SE 21 — WatchService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchService.html): vòng đời service, queue, `poll`/`take`, platform limitations và `OVERFLOW`.
- [Java SE 21 — WatchKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchKey.html): ready/signalled, `pollEvents`, `reset`, `cancel`, `isValid`, `watchable`.
- [Java SE 21 — WatchEvent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchEvent.html): `kind`, `count`, `context`.
- [Java SE 21 — StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): CREATE/MODIFY/DELETE/OVERFLOW.
- [Java SE 21 — Path.register](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html#register(java.nio.file.WatchService,java.nio.file.WatchEvent.Kind...)): đăng ký directory và các loại event.
- [Java SE 21 — FileSystem.newWatchService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/FileSystem.html#newWatchService()): tạo service từ filesystem provider.
- [Java SE 21 — ClosedWatchServiceException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/ClosedWatchServiceException.html): thao tác khi service đóng.
- [Dev.java — Watching a Directory for Changes](https://dev.java/learn/api/io/java-io/file-system/watching-dir-changes/): hướng dẫn thao tác đăng ký và xử lý thông báo.

**Kết luận:** `WatchService` vận hành theo mô hình **đăng ký directory → key được signal → lấy các event → xử lý → reset key**. Để dùng đúng, phải hiểu rằng event chỉ là **thông báo từ filesystem**, không phải ảnh chụp dữ liệu hoặc cam kết sự kiện không mất. Cần quản lý `WatchKey` và `WatchService` đầy đủ, xử lý `OVERFLOW`, hỗ trợ nhiều directory/subtree có chủ đích và dựa trên trạng thái file thật khi đưa ra quyết định nghiệp vụ.
