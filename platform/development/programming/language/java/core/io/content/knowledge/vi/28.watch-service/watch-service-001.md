# WatchService, Watchable và đăng ký thư mục trong Java NIO.2

## 1. Bài toán: biết khi nào một thư mục thay đổi

Một ứng dụng có thể cần cập nhật danh sách file sau khi người dùng tải ảnh lên, nhận biết file cấu hình mới được đặt vào thư mục, hoặc phản ứng khi file bị xóa. Việc liên tục gọi `Files.list()` hoặc `Files.exists()` để quét toàn bộ thư mục có thể gây tốn I/O và khó chọn chu kỳ kiểm tra hợp lý.

Từ Java 7, **Java NIO.2** cung cấp cơ chế theo dõi thay đổi thông qua `java.nio.file.WatchService`. Ứng dụng **đăng ký một thư mục** vào service và yêu cầu nhận các loại sự kiện; khi hệ thống tệp phát hiện thay đổi, service đưa một **`WatchKey`** vào hàng đợi để ứng dụng lấy ra và xử lý.

Một sơ đồ đơn giản:

```text
Path đại diện thư mục
       |
       | register(watchService, ENTRY_CREATE, ...)
       v
     WatchKey --------------------------+
       |                                |
       | tệp được thêm/xóa/sửa          | theo dõi vòng đời đăng ký
       v                                |
   WatchService                        |
       |                                |
       | take() / poll()                 |
       v                                |
  WatchKey được signal ----------------+
       |
       | pollEvents()
       v
 WatchEvent<?> gồm kind/count/context
       |
       | xử lý xong -> key.reset()
       v
 Tiếp tục chờ sự kiện mới
```

Ba đối tượng giữ ba trách nhiệm:

- **`WatchService`**: nguồn thông báo và hàng đợi các watch key đã có sự kiện.
- **`Watchable`**: đối tượng *có thể đăng ký* với watch service; trong học phần theo dõi thư mục, `Path` là kiểu được dùng.
- **`WatchKey`**: token đại diện cho **một lần đăng ký** và lưu những sự kiện đang chờ xử lý cho đăng ký đó.

**Lưu ý phạm vi:** đây là cơ chế *thông báo thay đổi trên đối tượng hệ thống tệp*, không phải cơ chế truyền nội dung file và không bảo đảm ghi nhận một bản ghi sự kiện cho mỗi thao tác vật lý trên mọi hệ điều hành.

## 2. Khái niệm và API nền tảng

Các lớp/interface liên quan ở package `java.nio.file`:

| Thành phần | Vai trò | Ví dụ API |
| --- | --- | --- |
| `WatchService` | Nhận key đang có tín hiệu; quản lý vòng đời watcher | `poll()`, `poll(timeout, unit)`, `take()`, `close()` |
| `Watchable` | Cho phép đăng ký theo dõi thay đổi | `register(watcher, events...)` |
| `Path` | Đại diện đường dẫn; triển khai `Watchable` | `dir.register(...)` |
| `WatchKey` | Quản lý một đăng ký, lấy event và tái kích hoạt | `pollEvents()`, `reset()`, `cancel()`, `isValid()`, `watchable()` |
| `WatchEvent<T>` | Một sự kiện được phát hiện | `kind()`, `count()`, `context()` |
| `StandardWatchEventKinds` | Các loại sự kiện chuẩn | `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY`, `OVERFLOW` |
| `FileSystem` | Tạo watch service ứng với file system | `newWatchService()` |

Quy trình khởi tạo thông dụng:

```java
try (WatchService watcher =
         FileSystems.getDefault().newWatchService()) {
    Path dir = Path.of("watched-directory");
    WatchKey key = dir.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_DELETE,
        StandardWatchEventKinds.ENTRY_MODIFY
    );

    // Lấy key từ watcher và xử lý WatchEvent<?>.
}
```

Đây là **đoạn minh họa**, chưa phải chương trình hoàn chỉnh: thư mục phải tồn tại, chương trình cần import, xử lý ngoại lệ và vòng lặp theo dõi. Nên dùng `try-with-resources` vì `WatchService` có thể đóng và nắm tài nguyên hệ điều hành.

### `Watchable` khác `WatchService`

`Watchable` chỉ định khả năng **đăng ký**. `Path` triển khai interface này, nên ta gọi `dir.register(watcher, ...)` trực tiếp. Ngược lại, `WatchService` **không chứa một phương thức `register(Path)` thông thường**; đối tượng được theo dõi tự đăng ký với watcher của nó.

Khai báo chuẩn của `Watchable` gồm hai dạng:

```java
WatchKey register(
        WatchService watcher,
        WatchEvent.Kind<?>... events) throws IOException;

WatchKey register(
        WatchService watcher,
        WatchEvent.Kind<?>[] events,
        WatchEvent.Modifier... modifiers) throws IOException;
```

Đoạn trên là các chữ ký API rút gọn. Với bài học căn bản, dùng phiên bản varargs các `StandardWatchEventKinds`, không cần modifier. Java SE 17 không định nghĩa **modifier chuẩn**; nếu có modifier của hệ thống tệp/JDK cụ thể, phải xét khả năng tương thích riêng.

## 3. Phải đăng ký **thư mục đã tồn tại**, không phải từng file

Trong Java SE 17 với cách dùng chuẩn của `Path.register`, đường dẫn đăng ký là **một thư mục hiện tồn tại**; các sự kiện đại diện cho thay đổi đối với **các entry của thư mục đó**.

Ví dụ cây thư mục:

```text
project/
├── config.json
├── a.txt
└── nested/
    └── x.txt
```

Nếu đăng ký `project/`:

- Tạo `project/new.txt` có thể sinh `ENTRY_CREATE`.
- Xóa `project/a.txt` có thể sinh `ENTRY_DELETE`.
- Sửa nội dung `project/config.json` có thể sinh `ENTRY_MODIFY`.
- Tạo `project/nested/new.txt` **không mặc nhiên được quan sát** vì `WatchService` không tự theo dõi toàn bộ cây thư mục.

**Đăng ký không đệ quy theo mặc định.** Muốn giám sát các thư mục con, cần đăng ký riêng từng thư mục hiện tại, đồng thời bổ sung đăng ký khi thư mục con mới xuất hiện. Những thay đổi xảy ra **giữa lúc phát hiện thư mục mới và lúc đăng ký nó** có thể bị bỏ lỡ; vì thế giải pháp mạnh phải có bước rà soát/bù trạng thái nếu không được mất thay đổi.

Nếu truyền đường dẫn là file thay vì thư mục, thao tác đăng ký không phù hợp với hợp đồng chuẩn và có thể gặp `NotDirectoryException` hoặc `IOException` tùy hệ thống. Thư mục không tồn tại cũng không thể được giám sát bằng cách “đăng ký trước rồi đợi nó được tạo” trên chính đường dẫn ấy. Hãy đăng ký **thư mục cha đang tồn tại** để theo dõi việc tạo entry con.

Ví dụ:

```java
Path parent = Path.of("/data").toAbsolutePath();
Path watchedChild = parent.resolve("incoming");

// Đăng ký parent trước, rồi nhận ENTRY_CREATE cho "incoming"
// nếu nó được tạo trực tiếp bên trong parent.
```

Đoạn này chỉ minh họa đường dẫn; không giả định thư mục `/data` tồn tại ở mọi môi trường và không phải chương trình chạy độc lập.

## 4. Ba loại sự kiện chuẩn cho directory entries

Các constant được định nghĩa trong `StandardWatchEventKinds`:

| Event kind | Khi nào thường được báo? | `context()` |
| --- | --- | --- |
| `ENTRY_CREATE` | Entry được tạo hoặc chuyển **vào** thư mục đang xem | `Path` tương đối chỉ entry vừa xuất hiện |
| `ENTRY_DELETE` | Entry bị xóa hoặc chuyển **ra khỏi** thư mục đang xem | `Path` tương đối chỉ entry đã biến mất |
| `ENTRY_MODIFY` | Entry trong thư mục được sửa | `Path` tương đối chỉ entry được sửa |
| `OVERFLOW` | Sự kiện có thể bị mất hoặc bị loại bỏ do vượt giới hạn | Thường `null`; không được ép kiểu như event của entry |

**Sự kiện create/modify/delete là tín hiệu, không phải nhật ký tuyệt đối chính xác.** Hệ điều hành có thể gộp nhiều lần modify thành một event, phát sinh nhiều event khi ứng dụng ghi một file, hoặc cung cấp hành vi khác nhau về thứ tự. Ví dụ editor thường ghi vào file tạm rồi rename để thay file gốc; bạn có thể thấy create/delete thay vì một modify đơn nhất.

`OVERFLOW` **được đăng ký tự động**, không cần và không nên dựa vào việc liệt kê nó trong mảng `events` để nhận thông báo.

Với `ENTRY_CREATE`, `ENTRY_DELETE` và `ENTRY_MODIFY` khi theo dõi thư mục, `event.context()` là **đường dẫn tương đối so với thư mục đã đăng ký**. Nó thường chỉ là tên entry, ví dụ `notes.txt`; không mặc định là đường dẫn tuyệt đối.

Cách xác định đường dẫn mục tiêu:

```java
Path watchedDir = (Path) key.watchable();

for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        // Không có context là tên file đáng tin trong event này.
        continue;
    }

    Path relative = (Path) event.context();
    Path affected = watchedDir.resolve(relative);

    System.out.println("Event: " + event.kind()
            + ", path: " + affected);
}
```

Đây là đoạn minh họa cần import và biến `key` hợp lệ. Dạng ép kiểu `(Path) event.context()` là phù hợp với **các entry events trên Path đã đăng ký theo dõi thư mục**; không nên áp dụng tùy tiện cho mọi implementation-specific kind hoặc `OVERFLOW`.

## 5. Đăng ký thư mục qua `Path.register`

Mẫu thường gặp:

```java
Path directory = Path.of("watch-me").toAbsolutePath();
try (WatchService service =
         directory.getFileSystem().newWatchService()) {

    WatchKey key = directory.register(
        service,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_DELETE,
        StandardWatchEventKinds.ENTRY_MODIFY);

    // Chờ thông báo và gọi key.reset().
}
```

Ở đây `getFileSystem().newWatchService()` đảm bảo watcher được tạo từ **cùng FileSystem** với path. Với đường dẫn trên default filesystem, `FileSystems.getDefault().newWatchService()` thường tương đương. Không trộn `Path` của provider này với `WatchService` của provider khác rồi giả định chúng tương thích.

**Cần kiểm tra sớm:**

- `Files.isDirectory(directory)` trả `true` tại thời điểm kiểm tra, nhưng thư mục vẫn có thể bị xóa/chuyển trong lúc đăng ký.
- Quyền truy cập của tiến trình phải cho phép theo dõi thư mục.
- FileSystem/provider có thể **không hỗ trợ watch service** hoặc một loại sự kiện/modifier nhất định.
- `register` có thể ném `IOException`, `UnsupportedOperationException`, `IllegalArgumentException` hoặc `ClosedWatchServiceException` tùy tình huống.

### Đăng ký lại đối tượng với cùng WatchService

Theo `Watchable.register`, nếu một đối tượng đã được đăng ký với **cùng WatchService**, gọi `register` lần nữa sẽ lấy lại key cho đăng ký đó đồng thời **cập nhật tập event kinds/modifiers** được theo dõi. Những sự kiện đang chờ không tự bị bỏ chỉ vì thay danh sách quan tâm.

Ví dụ ý tưởng:

```java
WatchKey first = dir.register(service,
        StandardWatchEventKinds.ENTRY_CREATE);

WatchKey second = dir.register(service,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_DELETE);

// Với cùng Path và service đang có đăng ký hợp lệ,
// đây là key đại diện cùng đăng ký được cập nhật.
```

Không sử dụng cách gọi lại `register` như một cách bảo đảm “xóa sạch queue cũ”, và không giả định `cancel()` một key vẫn được dùng để tiếp tục theo dõi; key đã hủy sẽ trở thành invalid.

## 6. `WatchKey`: vòng đời ready, signalled và reset

`WatchKey` là chìa khóa hiểu cơ chế:

```text
          đăng ký thành công
                 |
                 v
              READY
                 |
          event được phát hiện
                 |
                 v
             SIGNALLED ------> được đưa vào queue của WatchService
                 |                        |
                 |                        v
                 |                    take()/poll()
                 |                        |
                 |                        v
                 |                 key.pollEvents()
                 |                        |
                 |                        v
                 +<------ key.reset() sau khi xử lý
                             |
                      +------+-------+
                      |              |
               key còn valid     key invalid
                      |              |
              trở lại READY       hủy/cleanup
            hoặc requeue ngay
            nếu còn event chờ
```

**Khi một key đã signalled**, các event mới có thể tiếp tục được tích lũy cho key, nhưng key không được đưa lặp vào hàng đợi của service chỉ vì mỗi event mới xuất hiện. Sau khi xử lý xong event, ứng dụng phải gọi `key.reset()` để cho phép phát tín hiệu/đưa vào hàng đợi ở lần sau.

Các phương thức quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `key.pollEvents()` | Lấy danh sách event đã tích lũy và loại chúng khỏi danh sách pending |
| `key.reset()` | Hoàn tất lượt xử lý, đưa key về trạng thái có thể được signal tiếp; trả boolean |
| `key.isValid()` | Kiểm tra key còn đại diện cho đăng ký hợp lệ không |
| `key.cancel()` | Hủy đăng ký; key trở thành invalid |
| `key.watchable()` | Trả lại đối tượng đã đăng ký, ví dụ `Path` của thư mục |

`key.reset()` trả **`true`** nếu key còn hợp lệ và đã được reset; **`false`** nếu key không thể reset do không còn hợp lệ. Nếu sau khi reset còn event pending, key có thể **được đưa lại vào queue ngay**, chứ không nhất thiết phải chờ một thay đổi vật lý khác.

Một key có thể tự bị hủy nếu thư mục đang theo dõi bị xóa hoặc file system không còn truy cập được. Vì vậy, nếu `reset()` trả `false`, ứng dụng cần xóa đăng ký khỏi cấu trúc quản lý, xử lý cleanup hoặc khôi phục theo chính sách. Không được lặp vô hạn chỉ vì đã gọi `reset()` một lần.

### Vì sao reset quá sớm cũng nguy hiểm?

Nếu nhiều thread cùng lấy key từ một watch service, cần bảo đảm chỉ một consumer đang xử lý event cho cùng watchable ở một thời điểm. Gọi `reset()` **trước khi** xử lý xong có thể khiến key được signal và đưa vào queue tiếp, dẫn đến hai consumer xử lý đồng thời cùng thư mục và gây race condition. Dù WatchService cho phép nhiều consumer dùng chung, **thứ tự xử lý cùng một key** vẫn cần được điều phối rõ ràng.

## 7. `take()` và hai dạng `poll()`

`WatchService` cung cấp ba cách lấy key:

| Phương thức | Có chờ? | Kết quả khi chưa có key |
| --- | --- | --- |
| `watcher.poll()` | Không | Trả `null` ngay |
| `watcher.poll(timeout, TimeUnit.SECONDS)` | Có, tối đa timeout | Trả `null` nếu hết thời gian |
| `watcher.take()` | Có thể chờ đến khi có key | Không dùng `null` để báo timeout, vì không có timeout |

Mẫu xử lý chính:

```java
while (running) {
    WatchKey key = watcher.take();

    for (WatchEvent<?> event : key.pollEvents()) {
        // Xử lý event.
    }

    boolean valid = key.reset();
    if (!valid) {
        // Xóa đăng ký không còn hợp lệ khỏi ứng dụng.
    }
}
```

Đây là **pseudocode gần Java**; `running`, `watcher` và handler cần được định nghĩa. `take()` có thể ném `InterruptedException` nếu luồng bị ngắt trong lúc chờ, và `ClosedWatchServiceException` nếu service đã đóng.

Nếu chương trình cần kiểm tra điều kiện dừng định kỳ, `poll(timeout, unit)` thường dễ tổ chức hơn so với `take()` chờ vô hạn. Nếu muốn yêu cầu dừng từ thread khác, đóng WatchService sẽ đánh thức thread đang chờ và khiến lời gọi ném `ClosedWatchServiceException`; cần xử lý ngoại lệ đó như một phần của vòng đời shutdown, không tự mặc định đó là lỗi không thể phục hồi.

**Đừng busy-poll:**

```java
while (watcher.poll() == null) {
    // Vòng lặp rỗng có thể đốt CPU!
}
```

Dùng `take()` hoặc `poll(timeout, unit)` khi phù hợp.

## 8. Ví dụ Java 17+ chạy độc lập: đăng ký, kiểm tra và hủy WatchKey

Để có stdout **ổn định**, ví dụ đầu tập trung vào vòng đời đăng ký, không dựa vào thời điểm hệ điều hành phát sự kiện. Chương trình tạo một thư mục tạm, tạo watch service từ cùng file system, đăng ký ba event kind, kiểm tra key hợp lệ và hủy key có chủ đích.

**Tệp `WatchRegistrationDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;

public class WatchRegistrationDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("watch-demo-");

        try {
            try (WatchService service =
                     directory.getFileSystem().newWatchService()) {

                WatchKey key = directory.register(
                        service,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_DELETE,
                        StandardWatchEventKinds.ENTRY_MODIFY);

                System.out.println(
                        "Thu muc ton tai: " + Files.isDirectory(directory));
                System.out.println("Key hop le: " + key.isValid());
                System.out.println(
                        "Watchable trung Path: "
                        + key.watchable().equals(directory));

                key.cancel();
                System.out.println(
                        "Key sau cancel: " + key.isValid());
            }
        } finally {
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy với **JDK 17+** trên filesystem hỗ trợ watch service:

```bash
javac WatchRegistrationDemo.java
java WatchRegistrationDemo
```

**Stdout nếu tạo service, đăng ký và dọn dẹp thành công:**

```text
Thu muc ton tai: true
Key hop le: true
Watchable trung Path: true
Key sau cancel: false
```

Giải thích:

1. `Files.createTempDirectory` tạo thư mục thật, tránh lỗi đăng ký đường dẫn không tồn tại.
2. `directory.getFileSystem().newWatchService()` tạo watcher tương ứng với FileSystem của thư mục.
3. `directory.register(...)` trả về `WatchKey`; đây là đăng ký cho **thư mục**, không phải cho một file con.
4. `key.watchable().equals(directory)` kiểm chứng key tham chiếu tới đối tượng đã đăng ký.
5. `key.cancel()` làm key trở thành invalid, không cần có một event nào trước đó.
6. `try-with-resources` đóng watch service, và `finally` xóa thư mục tạm. Nếu nền tảng không hỗ trợ watcher hoặc có lỗi I/O, chương trình có thể ném ngoại lệ thay vì xuất stdout như trên.

**`cancel()` không phải `reset()`.** `cancel` kết thúc đăng ký; `reset` dùng sau mỗi lượt xử lý khi vẫn muốn giám sát thư mục.

## 9. Ví dụ Java 17+: theo dõi sự kiện của thư mục

Ví dụ sau tự tạo một file bên trong thư mục đã đăng ký. Nó dùng `poll(timeout)` để tránh chờ vô hạn, in event kind và entry name thực tế, xử lý `OVERFLOW`, gọi `reset()` sau khi đọc event rồi đóng mọi tài nguyên.

**Tệp `WatchEventsDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class WatchEventsDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watched-");
        Path file = directory.resolve("sample.txt");

        try {
            try (WatchService service =
                     directory.getFileSystem().newWatchService()) {

                directory.register(
                        service,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                Files.writeString(file, "Hello WatchService");
                WatchKey key = service.poll(3, TimeUnit.SECONDS);

                if (key == null) {
                    System.out.println("Khong co key trong 3 giay");
                } else {
                    List<WatchEvent<?>> events = key.pollEvents();

                    for (WatchEvent<?> event : events) {
                        if (event.kind() ==
                                StandardWatchEventKinds.OVERFLOW) {
                            System.out.println("OVERFLOW: can quet lai");
                            continue;
                        }

                        Path entry = (Path) event.context();
                        Path absolute = directory.resolve(entry);
                        System.out.println(event.kind().name()
                                + ": " + absolute.getFileName()
                                + " (count=" + event.count() + ")");
                    }

                    boolean valid = key.reset();
                    System.out.println("Key con hop le: " + valid);
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac WatchEventsDemo.java
java WatchEventsDemo
```

**Một kết quả có thể quan sát, không phải stdout được bảo đảm:**

```text
ENTRY_CREATE: sample.txt (count=1)
ENTRY_MODIFY: sample.txt (count=1)
Key con hop le: true
```

**Vì sao không được tuyên bố stdout chính xác?** WatchService nhận tín hiệu từ cơ chế filesystem có tính phụ thuộc nền tảng. Một hệ thống có thể phát thêm `ENTRY_MODIFY`, gộp sự kiện, hoặc chưa đưa key vào queue trong thời gian 3 giây. Thứ tự/số lượng/count của event có thể khác nhau. Do đó chương trình **in sự kiện thực tế**, không giả tạo thứ tự bắt buộc.

Một giới hạn khác: ví dụ chỉ gọi `poll(...)` một lần, đủ để minh họa cách lấy một key. Nếu sau `reset()` còn sự kiện chờ hoặc có event mới, một ứng dụng monitoring thực phải **tiếp tục vòng lặp** thay vì kết luận rằng một lần poll đã thu hết mọi thay đổi. Việc ghi bằng `Files.writeString` cũng có thể kích hoạt event modify ngoài create; đây không phải lỗi.

## 10. `WatchEvent.context()`, `count()` và cách xác định đường dẫn

Mỗi `WatchEvent<?>` có:

- `kind()`: loại sự kiện.
- `count()`: số lần sự kiện được tích lũy/gộp (không phải số byte hoặc kích thước file).
- `context()`: dữ liệu phụ thuộc kind, với entry event chuẩn thường là `Path` tương đối của entry.

Ví dụ:

```text
Thư mục đăng ký: /srv/inbox
event.kind(): ENTRY_CREATE
event.context(): daily.csv
event.count(): 1

Đường dẫn cần xử lý:
    /srv/inbox/daily.csv
```

Vì context là đường dẫn tương đối, dùng:

```java
Path directory = (Path) key.watchable();
Path relative = (Path) event.context();
Path fullPath = directory.resolve(relative);
```

Không dùng `Path.of(event.context().toString())` như thể nó luôn là absolute path. Nếu thư mục đăng ký được đại diện bằng đường dẫn tương đối, `resolve` cũng có thể cho kết quả tương đối; gọi `toAbsolutePath()` khi thực sự cần đường dẫn tuyệt đối, và cân nhắc symlink/canonicalization trong ứng dụng bảo mật.

Nếu một ứng dụng xử lý event bằng cách mở hoặc xóa file, hãy kiểm tra trạng thái **tại thời điểm sử dụng**: entry có thể đã bị xóa, di chuyển hoặc thay thế trong khoảng thời gian giữa lúc event được phát hiện và lúc handler thao tác (*time-of-check to time-of-use*). Sự kiện không cấp quyền truy cập, không giữ lock và không giữ một snapshot dữ liệu của file.

## 11. `OVERFLOW`: không thể coi thông báo là danh sách thay đổi hoàn chỉnh

WatchService có thể có giới hạn số event được tích lũy. Khi triển khai nhận biết rằng event đã bị loại bỏ, nó cung cấp `OVERFLOW`. Bạn có thể gặp `OVERFLOW` dù chỉ đăng ký create/delete/modify.

Cách xử lý đúng:

```java
if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
    // Đánh dấu trạng thái quan sát có thể thiếu.
    // Rà soát lại các entry của thư mục hoặc tái đồng bộ chỉ mục.
    continue;
}
```

Ý nghĩa không phải “thử đọc lại chính event đó” vì nội dung chi tiết đã mất. Ứng dụng nên **quét trạng thái hiện tại** của những thư mục cần theo dõi và đối chiếu với trạng thái/metadata đã ghi nhận để khôi phục tính nhất quán.

Thí dụ service dùng để duy trì cache file:

1. Khi bắt đầu, lấy danh sách file đang có.
2. Trong lúc chạy, áp dụng create/delete/modify để cập nhật cache.
3. Khi có `OVERFLOW`, đánh dấu cache có thể sai.
4. Quét lại thư mục và xây lại trạng thái cache.
5. Tiếp tục nhận event, có cơ chế phối hợp với các thay đổi phát sinh trong lúc quét.

**Không thể biến WatchService thành audit log không mất dữ liệu** chỉ bằng việc tăng tốc vòng đọc event. Nếu cần biết chắc *mọi* thay đổi (không bỏ sót) cho nghiệp vụ quan trọng, cần giao thức phát sự kiện/transaction log riêng, đối soát, hoặc nguồn dữ liệu có tính bền vững phù hợp.

## 12. Giới hạn về thời gian và nội dung file được sửa

`ENTRY_MODIFY` **không có nghĩa file đã ghi xong**. Ứng dụng khác có thể còn mở và tiếp tục ghi file trong khi bạn nhận được event. Vì thế một file watcher dùng để nhập dữ liệu cần thiết kế dấu hiệu “file đã sẵn sàng”, ví dụ:

- Bên sản xuất ghi vào một tên file tạm, đóng file, rồi đổi tên vào thư mục nhận nếu filesystem và chiến lược rename phù hợp.
- Bên nhận chờ một marker/manifest “complete” do bên sản xuất phát sau cùng.
- Ứng dụng xác minh tính toàn vẹn hoặc độ dài/metadata ổn định trong một khoảng phù hợp, đồng thời chấp nhận đây chỉ là **heuristic**, không phải bảo đảm tuyệt đối.

Nếu file vừa có `ENTRY_CREATE` rồi `ENTRY_DELETE` trước lúc handler xử lý, việc `Files.readAllBytes(fullPath)` có thể ném `NoSuchFileException`. Handler cần xem event như “gợi ý kiểm tra lại trạng thái” thay vì mệnh lệnh bắt buộc mở file luôn thành công.

Trong hệ thống nhiều writer, event của cùng một entry có thể xuất hiện liên tiếp. Cần **debounce/coalesce ở tầng ứng dụng** nếu xử lý quá nặng, nhưng không được đơn giản bỏ sự kiện theo thời gian rồi khẳng định không mất thay đổi nghiệp vụ.

## 13. Vòng lặp giám sát dài hạn đúng cách

Một khung event loop dùng `WatchService`:

```java
try (WatchService watcher =
         directory.getFileSystem().newWatchService()) {

    directory.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);

    while (!Thread.currentThread().isInterrupted()) {
        WatchKey key = watcher.take();

        try {
            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() ==
                        StandardWatchEventKinds.OVERFLOW) {
                    reconcileDirectory((Path) key.watchable());
                    continue;
                }

                Path root = (Path) key.watchable();
                Path entry = (Path) event.context();
                processEvent(event.kind(), root.resolve(entry));
            }
        } finally {
            boolean valid = key.reset();
            if (!valid) {
                break;
            }
        }
    }
}
```

**Đây là khung minh họa, không phải chương trình Java độc lập:** cần khai báo `directory`, `reconcileDirectory` và `processEvent`, import các API và xử lý `IOException`/`InterruptedException`/runtime exceptions. Dùng `finally` cho `reset()` bảo đảm vòng đời key được xử lý ngay cả khi handler ném lỗi, **nhưng không tự làm cho lỗi nghiệp vụ an toàn**; tùy ứng dụng, có thể cần đánh dấu cần đồng bộ lại nếu handler thất bại trước khi xử lý đủ event.

Nếu giám sát **nhiều thư mục**, không thể `break` toàn bộ event loop chỉ vì một key invalid nếu còn các key khác hợp lệ. Thay vào đó quản lý registry và chỉ kết thúc khi không còn mục tiêu cần theo dõi hoặc có tín hiệu shutdown.

### Registry của nhiều thư mục

Một cách tổ chức:

```java
Map<WatchKey, Path> roots = new HashMap<>();

WatchKey keyA = dirA.register(watcher, ENTRY_CREATE, ENTRY_DELETE);
roots.put(keyA, dirA);

WatchKey keyB = dirB.register(watcher, ENTRY_CREATE, ENTRY_DELETE);
roots.put(keyB, dirB);
```

Đây là đoạn minh họa với biến `dirA`, `dirB` và imports thích hợp; không phải chương trình chạy được độc lập. Lần `take()` kế tiếp có thể trả **key của bất kỳ thư mục nào có event**. Dùng `roots.get(key)` hoặc `(Path) key.watchable()` để xác định nguồn. Nếu `reset()` trả false, xóa key khỏi map. Không đánh đồng `watcher` với một thư mục duy nhất khi đã đăng ký nhiều nơi.

## 14. Theo dõi thư mục con: làm rõ tính **không đệ quy**

Giả sử cần theo dõi `root/sub1/sub2`. `root.register(watcher, ...)` chỉ cho bạn những thay đổi của entry **trực tiếp** dưới `root`. Để quan sát trong `sub1` và `sub2`, phải đăng ký chính chúng.

Quy trình cơ bản:

1. Duyệt cây thư mục hiện tại bằng `Files.walkFileTree` hoặc API phù hợp.
2. Đăng ký từng thư mục đang tồn tại, lưu `WatchKey → Path`.
3. Khi nhận `ENTRY_CREATE` của một thư mục con mới, kiểm tra `Files.isDirectory(path)` tại thời điểm xử lý và đăng ký thư mục ấy.
4. Có thể rà soát thêm nội dung bên dưới thư mục vừa xuất hiện để bù khoảng thời gian xảy ra trước khi đăng ký.
5. Khi key không còn hợp lệ, xóa registry và quyết định có cần thử đăng ký lại khi thư mục xuất hiện ở vị trí mới.

Cân nhắc thêm:

- Quy tắc theo symlink: có thể tạo vòng lặp hoặc đi ra ngoài thư mục gốc. Dùng chính sách follow/no-follow rõ ràng.
- Giới hạn số lượng watcher và tài nguyên OS khi cây có hàng trăm nghìn thư mục.
- Race condition khi thư mục bị xóa giữa `isDirectory` và `register`.
- Chuyển thư mục sang tên khác: không có bảo đảm mọi event tương ứng rename được biểu diễn theo một chuẩn duy nhất trên mọi platform.
- File system ảo, mạng hoặc container volume có thể có hành vi phát event khác local disk.

Không gọi một chương trình giám sát mỗi thư mục cha là “recursive watcher” nếu thực tế chưa đăng ký các cấp con.

## 15. Khác biệt với `Selector` và I/O mạng

Tuy `WatchService` và `Selector` đều có tác vụ “chờ có việc”:

| Khía cạnh | WatchService | Selector |
| --- | --- | --- |
| Đối tượng theo dõi | `Watchable`, thường là `Path` thư mục | `SelectableChannel`, thường là socket/pipe |
| Token | `WatchKey` | `SelectionKey` |
| Nguồn dữ liệu | Sự kiện thay đổi entry hệ thống tệp | Readiness của channel cho I/O |
| Cách đợi | `take()`, `poll()` | `select()`, `selectNow()` |
| Sau xử lý | **`WatchKey.reset()`** | Lấy/xóa key khỏi `selectedKeys()` theo event loop |
| Các kind/ops | `ENTRY_CREATE`/`DELETE`/`MODIFY`/`OVERFLOW` | `OP_ACCEPT`/`CONNECT`/`READ`/`WRITE` |

Một lỗi dễ mắc là nghĩ `WatchKey.reset()` tương đương `iterator.remove()` trên `Selector.selectedKeys()`. Chúng thuộc **hai API khác nhau**, vòng đời và nội dung sự kiện khác nhau. `WatchService` trả về key có danh sách `WatchEvent` đang chờ; `Selector` trả về key cho biết **loại I/O sẵn sàng**, không phải danh sách thay đổi file.

Cũng không dùng `FileChannel.configureBlocking(false)` để tạo watcher cho thay đổi thư mục. `FileChannel` không phải selectable socket channel; `WatchService` mới là API dành cho sự kiện directory entries.

## 16. Giới hạn phụ thuộc hệ điều hành và filesystem

Đặc tả Java cho phép triển khai WatchService dùng cơ chế thông báo native của hệ điều hành hoặc phương án khác như polling khi không có cơ chế native phù hợp. Vì vậy:

- **Thời điểm thông báo** có thể khác thời điểm thay đổi xảy ra.
- **Số lượng và thứ tự** event có thể khác nhau giữa Linux, Windows, macOS, file system provider hoặc JDK vendor.
- **Coalescing** có thể gộp các event cùng loại; `event.count()` phản ánh số lần tích lũy theo hợp đồng, không là bằng chứng của đầy đủ mọi thao tác.
- **OVERFLOW** báo khả năng sự kiện đã mất; ngay cả khi không nhận overflow, vẫn nên thiết kế có đối soát nếu tính đúng nghiệp vụ là yêu cầu nghiêm ngặt.
- **Quyền, symlink, rename và truncate** có thể gây hành vi phức tạp hoặc khác nhau.
- **File system không hỗ trợ watcher** có thể gây `UnsupportedOperationException` khi tạo dịch vụ; đừng giả định mọi `FileSystem` đều có khả năng theo dõi.

Đặc biệt, **không có bảo đảm một event modify tương ứng “bên ghi đã đóng file”**. Sự kiện là thông tin phát hiện thay đổi, không phải lời hứa dữ liệu đã ổn định và sẵn sàng nhập.

Ứng dụng cần độ tin cậy cao thường kết hợp watcher để phát hiện sớm với **cơ chế quét lại trạng thái**, nhật ký riêng hoặc giao thức đồng bộ hóa giữa các thành phần.

## 17. Những ngoại lệ và lỗi phổ biến

| Vấn đề | Kết quả / rủi ro | Cách xử lý |
| --- | --- | --- |
| Đăng ký `Path` là file thay vì thư mục | Không đúng mục tiêu; có thể `NotDirectoryException` | Đăng ký thư mục cha đã tồn tại |
| Đăng ký đường dẫn không tồn tại | Không thể đăng ký đúng đối tượng | Tạo/kiểm tra thư mục rồi đăng ký |
| Đăng ký event/modifier không được hỗ trợ | `UnsupportedOperationException` hoặc lỗi tham số | Chỉ dùng kinds chuẩn và kiểm tra provider |
| Quên gọi `key.reset()` | Key có thể không được tái xếp hàng cho lần xử lý sau | Reset sau khi xử lý pending events |
| Gọi `reset()` trước khi xử lý xong cùng một key | Có thể có consumer khác xử lý trùng | Quản lý một owner per key, reset sau |
| Nghĩ `pollEvents()` lấy event mãi mà không tiêu thụ | Bỏ qua đặc tính lấy và xóa pending events | Xử lý danh sách lấy ra một lần |
| Nghĩ `take()` luôn trả ngay | Luồng có thể chờ vô hạn nếu không có event | Có shutdown/interrupt/close hoặc poll timeout |
| Coi `OVERFLOW` là tên file | `context()` không phải Path của entry | Quét và đối soát lại thư mục |
| Ép `event.context()` thành Path với mọi kind | Có thể sai kiểu/null | Kiểm tra kind trước |
| Đọc `ENTRY_MODIFY` như file đã hoàn tất | Dữ liệu chưa ổn định | Giao thức hoàn tất, rename/marker/đối soát |
| Giám sát thư mục cha và tin theo dõi cả cây | Bỏ lỡ thay đổi trong thư mục con | Đăng ký từng thư mục |
| Đóng WatchService mà vẫn `take()` | `ClosedWatchServiceException` | Xử lý shutdown đúng cách |
| Bỏ qua `InterruptedException` | Worker khó dừng hợp lệ | Khôi phục cờ interrupt hoặc thoát theo chính sách |
| Không xử lý `reset()==false` | Vòng lặp giữ key invalid | Xóa registry, quyết định re-register |
| Dùng busy-poll liên tục | CPU tăng mạnh | `take()` hoặc `poll(timeout)` |
| Không đóng WatchService | Rò rỉ tài nguyên native | `try-with-resources` |
| Tin event cung cấp snapshot file | Race khi entry đã bị xóa/thay thế | Kiểm tra file tại thời điểm sử dụng |

## 18. Tự kiểm tra kiến thức

**Câu 1.** `WatchService` có phải đối tượng được gọi `register(ENTRY_CREATE)` trực tiếp hay không?

**Đáp án:** Thông thường **không**. Một `Watchable` (như `Path` đại diện thư mục) gọi `register(watcher, kinds...)` và trả `WatchKey`.

**Câu 2.** Khi `watcher.take()` trả một `WatchKey`, có thể quên `reset()` nếu muốn tiếp tục theo dõi không?

**Đáp án:** Không. Sau khi xử lý `pollEvents()`, phải gọi `reset()` và kiểm tra boolean hợp lệ. Nếu key vẫn ở trạng thái signalled, những event tiếp theo có thể được tích lũy nhưng key không được xếp lại vào queue theo cách bạn kỳ vọng.

**Câu 3.** Đăng ký `root` có nhận được `ENTRY_CREATE` của `root/a/b.txt` không?

**Đáp án:** Không mặc định. Watcher theo dõi các entry trực tiếp của `root`; phải đăng ký `root/a` nếu muốn theo dõi thay đổi của entry `b.txt`.

**Câu 4.** Khi `event.kind()==ENTRY_DELETE`, có thể mở file qua `dir.resolve(event.context())` và mong nó vẫn tồn tại không?

**Đáp án:** Không. Event báo entry đã bị xóa hoặc chuyển ra; đường dẫn có thể không tồn tại. Handler cần xử lý `NoSuchFileException` và kiểm tra trạng thái tại thời điểm dùng.

**Câu 5.** Khi có `OVERFLOW`, một sự kiện cụ thể có thể đã bị bỏ. Giải pháp nào đúng?

**Đáp án:** Đánh dấu trạng thái theo dõi không còn đầy đủ và **rà soát lại trạng thái** thư mục, khôi phục cache/chỉ mục theo thiết kế. Không thể khôi phục chính xác event đã mất chỉ bằng `pollEvents()` lần nữa.

**Câu 6.** Sau khi `WatchKey.cancel()`, `key.watchable()` có trả lại `Path` đã đăng ký không?

**Đáp án:** Có, theo hợp đồng `WatchKey.watchable()`, phương thức này vẫn trả đối tượng watchable ngay cả khi key đã bị hủy. Tuy nhiên điều đó **không** làm key valid lại hoặc chứng minh thư mục hiện còn tồn tại.

## 19. Tổng kết và tài liệu

Để dùng `WatchService` đúng cách, hãy ghi nhớ chuỗi thao tác:

1. **Tạo** `WatchService` từ `FileSystem` phù hợp.
2. **Đăng ký** một `Path` trỏ tới thư mục đang tồn tại bằng `Path.register(watcher, ENTRY_...)`.
3. **Đợi** `WatchKey` qua `take()` hoặc `poll(...)`.
4. **Duyệt** `key.pollEvents()`; xử lý kind, context tương đối, count và `OVERFLOW`.
5. **Reset** bằng `key.reset()`; nếu false, dọn đăng ký không còn hợp lệ.
6. **Đóng** watcher đúng vòng đời; xử lý interrupt, race, đồng thời và tình huống provider không hỗ trợ.

**Điểm cốt lõi:** `WatchService` là cơ chế **phát hiện thay đổi**, không phải log có bảo đảm ghi nhận mọi sự kiện. `Watchable` định nghĩa cách đăng ký, `WatchKey` đại diện đăng ký và cần reset sau mỗi lượt, còn `WatchEvent` chứa những thông tin được phát hiện. Khi độ chính xác quan trọng, kết hợp sự kiện với việc kiểm tra lại **trạng thái hệ thống tệp thực tế**.

**Tài liệu tham khảo chính thức cho Java SE 17:**

- [WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html)
- [Watchable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Watchable.html)
- [WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html)
- [Path.register](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html)
