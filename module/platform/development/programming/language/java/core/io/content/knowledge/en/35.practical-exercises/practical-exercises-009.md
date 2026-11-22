# Thực hành: Theo dõi thư mục bằng WatchService có xử lý OVERFLOW

## 1. Kết quả cần đạt

Bài thực hành xây dựng một bộ theo dõi thư mục với Java NIO.2, sử dụng `WatchService` để nhận **tín hiệu thay đổi** và bổ sung cơ chế **rescan/reconciliation** để khôi phục trạng thái khi sự kiện bị mất, đặc biệt khi có `StandardWatchEventKinds.OVERFLOW`.

Sau bài này, bạn có thể:

1. Tạo và đăng ký `WatchService` theo dõi các mục trực tiếp trong một thư mục.
2. Nhận `WatchKey` bằng `take()` hoặc `poll(timeout, unit)`.
3. Xử lý `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE` và `OVERFLOW`.
4. Dùng `WatchEvent.context()` đúng như **đường dẫn tương đối** so với thư mục đã đăng ký.
5. Gọi `pollEvents()`, xử lý và `reset()` cho từng key.
6. Xây dựng snapshot trạng thái thư mục bằng `Files.newDirectoryStream` và `BasicFileAttributes`.
7. Khi nhận `OVERFLOW`, quét lại trạng thái hiện tại để hòa giải cache thay vì tưởng rằng có thể tái tạo từng thao tác đã mất.
8. Viết ví dụ Java 17+ độc lập, có stdout dự đoán được mà **không phải giả định thứ tự/số lượng sự kiện ổn định trên mọi OS**.
9. Biết cách mở rộng thành watcher chạy lâu dài, hỗ trợ nhiều thư mục, dừng sạch, kiểm thử và bảo vệ tài nguyên.

> **Ý chính:** WatchService không phải một transaction log hay audit log đáng tin cậy. Nó cung cấp tín hiệu để ứng dụng biết **nên kiểm tra lại filesystem khi nào**. Trạng thái thực tế của thư mục, không phải từng notification riêng lẻ, mới là nguồn sự thật khi cần đồng bộ nội dung hiện thời.

## 2. Chuẩn bị môi trường

Ví dụ sử dụng **JDK 17 trở lên** và các API trong Java Standard Library, không cần Maven/Gradle hay dependency ngoài.

Kiểm tra môi trường:

```bash
java -version
javac -version
```

Cần có quyền tạo, đọc, sửa và xóa trong thư mục tạm mà JVM đang dùng. Hầu hết phần thực hành có thể chạy trên Windows, Linux hoặc macOS, nhưng:

- Nền tảng/provider có thể khác nhau về thời điểm, thứ tự và số lượng `ENTRY_MODIFY`.
- WatchService có thể không hỗ trợ đầy đủ trên network filesystem, mount đặc biệt hoặc môi trường sandbox.
- Không cố ép hệ điều hành phát `OVERFLOW` thật bằng cách tạo một lượng tệp khổng lồ; điều đó có thể gây quá tải mà không cho kết quả lặp lại.
- Các bài kiểm tra quan trọng cần chạy trên **filesystem triển khai thực tế**, không chỉ trên máy phát triển.

Các loại import cần thiết thường từ `java.nio.file`, `java.nio.file.attribute`, `java.util` và `java.util.concurrent`.

## 3. Nhắc lại WatchService hoạt động ra sao

Một `WatchService` giữ hàng đợi **WatchKey đã được signalled**. Khi ứng dụng đăng ký một thư mục, filesystem/provider có thể ghi nhận thay đổi trực tiếp bên trong nó và đưa key tương ứng vào hàng đợi.

```text
                   Filesystem
          create / modify / delete
                      |
                      v
              Đăng ký thư mục
                WatchKey K1
                      |
              key được signalled
                      |
                      v
              WatchService queue
                      |
                      v
         take() / poll() / timed poll()
                      |
                      v
              K1.pollEvents()
                      |
             +--------+---------+
             |                  |
         ENTRY_*             OVERFLOW
             |                  |
         event hint         mất sự kiện?
             |                  |
             +--------+---------+
                      |
                      v
             Rescan / reconcile
                      |
                      v
                key.reset()
                      |
           true: tiếp tục theo dõi
           false: registration invalid
```

Với `Path.register(watcher, kinds...)`, một `WatchKey` đại diện cho registration của path đã theo dõi. Một key có thể gom **nhiều events**; một lần `take()` trả **key**, không nhất thiết trả đúng một thay đổi.

### Các event kinds

| Event kind | Nghĩa thường gặp | Việc nên làm |
|---|---|---|
| `ENTRY_CREATE` | Một mục trực tiếp trong thư mục xuất hiện | Kiểm tra trạng thái mục ở thời điểm xử lý |
| `ENTRY_MODIFY` | Provider quan sát có sửa đổi | Đọc lại metadata/nội dung nếu nghiệp vụ yêu cầu |
| `ENTRY_DELETE` | Mục trực tiếp không còn tồn tại dưới tên đã theo dõi | Cập nhật cache từ trạng thái hiện tại |
| `OVERFLOW` | Provider báo có thể đã mất/bỏ một số events | **Quét lại thư mục**, đối chiếu cache; không cố khôi phục thứ tự mọi thay đổi |

**Không có bảo đảm một lần user nhấn Save = một `ENTRY_MODIFY`.** Editor có thể tạo file tạm rồi rename; một lần ghi lớn có thể tạo nhiều modify events; hệ thống có thể gộp chúng.

## 4. OVERFLOW thực sự có ý nghĩa gì?

`OVERFLOW` là tín hiệu cho biết event stream **có thể không còn đầy đủ**. Những thay đổi đã bị bỏ không nhất thiết có thể được hỏi lại từ WatchService.

Ví dụ:

```text
Trạng thái ứng dụng nghĩ đang có:
  A.txt, B.txt

Filesystem thay đổi rất nhanh:
  delete A.txt
  create C.txt
  modify B.txt
  create D.txt
  delete C.txt

Hàng đợi sự kiện bị tràn:
  ... OVERFLOW ...

Filesystem hiện tại:
  B.txt, D.txt
```

Nếu chỉ dựa vào các events còn sót, cache có thể vẫn tin `A.txt` tồn tại hoặc bỏ lỡ `D.txt`. Khi thấy overflow, cần quét thư mục để biết **cái gì đang tồn tại hiện nay**.

Không thể dùng một snapshot cuối để suy luận đầy đủ chuỗi thao tác trung gian. Ví dụ file `C.txt` từng được tạo rồi xóa trước lúc rescan: trạng thái cuối không còn dấu vết của C. Nếu nghiệp vụ yêu cầu audit **mọi sự kiện**, cần nhật ký giao dịch/journal ở tầng nguồn hoặc một hệ thống theo dõi có hợp đồng bền, không thể chỉ thêm `rescan` vào WatchService là đạt exactly-once.

### Chính sách phục hồi phù hợp

- Đánh dấu registration/thư mục cần **full rescan**.
- Lấy snapshot mới từ filesystem.
- So với cache ứng dụng ở trạng thái trước đó.
- Xử lý các mục xuất hiện/biến mất/thay đổi theo logic **idempotent**.
- Thay cache bằng snapshot mới sau khi các bước cần thiết hoàn tất.
- Tiếp tục theo dõi bằng `reset()` nếu key còn hợp lệ.
- Ghi metrics/log về overflow, thời gian rescan, số mục và lỗi I/O.

Với hệ thống chỉ quan tâm **trạng thái hiện tại**, đây là một chiến lược hợp lý. Với hệ thống cần lịch sử đầy đủ, phải dùng nguồn sự kiện có độ tin cậy cao hơn.

## 5. Thiết kế giải pháp: notification là hint, snapshot là trạng thái

Để bài thực hành có thể phục hồi cả trường hợp mất notification, ta chọn một thiết kế đơn giản nhưng vững:

1. Tạo `WatchService`, đăng ký thư mục trước.
2. Tạo snapshot ban đầu từ các mục trực tiếp trong thư mục.
3. Chờ WatchKey.
4. Lấy danh sách events. `OVERFLOW` được nhận diện **trước** khi ép `context` thành `Path`.
5. Với **bất kỳ key nào có event**, ta **rescan toàn bộ một thư mục** thay vì chỉ cập nhật từng item dựa trên event. Nhờ vậy, nhánh overflow đương nhiên thực hiện reconciliation.
6. So snapshot cũ và mới, xác định mục mới, mục đã mất và mục có metadata khác.
7. Reset key; nếu key invalid, dừng hoặc lên lịch đăng ký lại theo policy.
8. Định kỳ rescan cả khi không có notification nếu yêu cầu phát hiện trạng thái chệch do sự cố hoặc mất event.

**Đánh đổi:** full rescan cho mỗi notification dễ hiểu, hữu ích cho thư mục nhỏ/vừa và bài học; nó có thể tốn tài nguyên với thư mục hàng triệu entries. Trong production có thể tối ưu cập nhật từng entry cho event bình thường, chỉ full rescan khi OVERFLOW, lúc khởi động và định kỳ. Dù tối ưu, vẫn phải giữ cơ chế reconciliation đầy đủ.

### Snapshot bao gồm gì?

Ví dụ lưu một dấu vết metadata (**fingerprint**) cho mỗi mục:

- Tên/`Path` tương đối.
- `size()`.
- `lastModifiedTime()`.
- `isDirectory()`.

Đây là **heuristic quan sát trạng thái**, không phải cryptographic digest. Có thể không phát hiện nội dung bị thay đổi nếu kích thước và mtime cuối vẫn giống nhau hoặc filesystem có độ phân giải thời gian thấp. Nếu ứng dụng cần biết nội dung có đổi một cách chắc hơn, phải thêm hash/checksum hoặc version do producer cung cấp, cân nhắc chi phí và race khi file đang ghi.

## 6. Trình tự đăng ký và snapshot ban đầu

Mẫu cơ bản:

```java
try (WatchService watcher =
         FileSystems.getDefault().newWatchService()) {

    root.register(
            watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_MODIFY,
            StandardWatchEventKinds.ENTRY_DELETE);

    Map<Path, Stamp> known = scanDirectory(root);
    // Vòng lấy keys và đối chiếu snapshots...
}
```

Đây là **mã minh họa**, cần khai báo `root` và các helper/import. Lý do đăng ký **trước** lần scan đầu tiên: nếu quét trước, sau đó một file thay đổi trong khoảng chưa đăng ký, bạn có thể không nhận được notification cho thay đổi ấy.

Tuy nhiên, đăng ký trước rồi scan **chưa biến hai bước thành một transaction nguyên tử**. Một mục có thể đổi trong khi đang quét; các event được queue trong lúc đó cần được tiêu thụ tiếp, và đối với dữ liệu quan trọng nên có thêm periodic reconciliation hoặc một snapshot protocol chuyên biệt.

Trong ví dụ bài học, mọi thay đổi được tạo trong cùng tiến trình sau khi đã đăng ký, nên trình tự dễ kiểm soát hơn.

## 7. WatchKey: take, poll và reset

Ba cách lấy key:

```java
WatchKey a = watcher.take();                          // Chờ.
WatchKey b = watcher.poll();                          // Không chờ.
WatchKey c = watcher.poll(1, TimeUnit.SECONDS);       // Chờ tối đa 1 s.
```

Các dòng là minh họa, **không gọi liên tiếp cả ba như một thủ tục bắt buộc**. Nếu `take()` được gọi khi không có event, thread có thể chờ không giới hạn.

- `take()` phù hợp watcher thread chuyên dụng, có shutdown qua interrupt/close.
- `poll()` phù hợp tích hợp vào một loop đã có công việc khác; tránh busy spin.
- `poll(timeout, unit)` thuận tiện cho watcher cần thời gian kiểm tra cờ dừng, metrics và periodic rescan.
- `pollEvents()` đọc/drain các events tích lũy cho key.
- `reset()` chuyển key về trạng thái sẵn sàng nếu registration hợp lệ.

Cần đặc biệt tránh quên `reset()`: một key đã được lấy có thể không tiếp tục cung cấp tín hiệu như mong đợi. Nếu `reset()` trả `false`, registration đã mất hiệu lực; không tiếp tục chờ nó như thể vẫn hoạt động.

## 8. Ví dụ Java 17+ hoàn chỉnh: WatchService và phục hồi snapshot

Ví dụ này được thiết kế **tự chạy trong một tiến trình**:

- Tạo thư mục riêng trong temp.
- Đăng ký sự kiện tạo/sửa/xóa.
- Chụp snapshot trống.
- Tạo file `item.txt`.
- Dùng `WatchService.poll(timeout)` để có cơ hội tiêu thụ WatchKey; nếu chưa nhận notification trong thời gian chờ, vẫn rescan để đối chiếu.
- Cố ý xóa **cache trong bộ nhớ** để mô phỏng việc chương trình đã bỏ lỡ thông báo; một full rescan tìm lại file.
- Xóa file, rescan xác nhận thư mục trở về trống.
- Dọn tài nguyên.

**Điểm chính:** bài thử **không giả mạo một `OVERFLOW` thật**, vì không thể ép provider phát overflow một cách ổn định. Nhưng nhánh khi OVERFLOW xuất hiện thật sử dụng **cùng cơ chế full rescan**, và bài thử chủ động xác minh chức năng reconciliation độc lập với tín hiệu OS.

Tạo file **`WatchOverflowRecoveryDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public class WatchOverflowRecoveryDemo {

    record Stamp(long size, long modifiedMillis, boolean directory) {}

    record KeyResult(
            Map<Path, Stamp> snapshot,
            boolean valid,
            boolean overflow) {}

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watch-overflow-");
        Path item = directory.resolve("item.txt");

        try {
            try (WatchService watcher =
                         FileSystems.getDefault().newWatchService()) {

                directory.register(
                        watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                Map<Path, Stamp> known = scan(directory);
                System.out.println("Initial entries: " + known.size());

                Files.writeString(
                        item, "v1\n", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);

                WatchKey key = watcher.poll(1500, TimeUnit.MILLISECONDS);
                if (key != null) {
                    KeyResult eventResult = consumeAndRescan(
                            directory, known, key);
                    known = eventResult.snapshot();

                    if (!eventResult.valid()) {
                        throw new IOException("Watch registration invalid");
                    }

                    // Thông tin overflow có thể được log/đếm trong
                    // ứng dụng thật; bài demo không in vì khác OS.
                } else {
                    // Không có event trong deadline: vẫn có thể
                    // đối chiếu trạng thái hiện tại.
                    known = scan(directory);
                }

                System.out.println("Exists after create: "
                        + known.containsKey(item.getFileName()));

                // Mô phỏng cache mất dữ liệu/sự kiện bị bỏ lỡ.
                // KHÔNG tuyên bố OS đã phát một OVERFLOW thật.
                Map<Path, Stamp> stale = Map.of();
                Map<Path, Stamp> recovered = scan(directory);
                System.out.println("Rescan restored entry: "
                        + (!stale.containsKey(item.getFileName())
                           && recovered.containsKey(item.getFileName())));

                Files.delete(item);
                Map<Path, Stamp> afterDelete = scan(directory);
                System.out.println("Entries after delete: "
                        + afterDelete.size());
            }
        } finally {
            Files.deleteIfExists(item);
            Files.deleteIfExists(directory);
        }
    }

    private static Map<Path, Stamp> scan(Path directory)
            throws IOException {

        Map<Path, Stamp> result = new HashMap<>();

        try (DirectoryStream<Path> entries =
                     Files.newDirectoryStream(directory)) {

            for (Path entry : entries) {
                try {
                    BasicFileAttributes attrs = Files.readAttributes(
                            entry,
                            BasicFileAttributes.class,
                            LinkOption.NOFOLLOW_LINKS);

                    result.put(
                            entry.getFileName(),
                            new Stamp(
                                    attrs.size(),
                                    attrs.lastModifiedTime().toMillis(),
                                    attrs.isDirectory()));

                } catch (NoSuchFileException ignored) {
                    // Mục biến mất giữa list và readAttributes:
                    // vòng rescan khác sẽ nhìn trạng thái mới.
                }
            }
        }

        return result;
    }

    private static KeyResult consumeAndRescan(
            Path directory,
            Map<Path, Stamp> oldSnapshot,
            WatchKey key) throws IOException {

        boolean overflow = false;

        for (WatchEvent<?> event : key.pollEvents()) {
            if (event.kind()
                    == StandardWatchEventKinds.OVERFLOW) {
                overflow = true;
                continue;
            }

            if (event.context() instanceof Path relativeName) {
                // Chỉ là gợi ý; có thể đã sửa/xóa/rename
                // trước khi ta thực sự truy cập tới mục này.
                Path candidate = directory.resolve(relativeName);
                // Không cần mở candidate trong bài demo.
            }
        }

        Map<Path, Stamp> latest;
        boolean valid;

        try {
            // Quét đầy đủ cho mọi key; nếu OVERFLOW,
            // đây chính là nhánh recovery.
            latest = scan(directory);
        } finally {
            // Trả key về trạng thái ready khi có thể,
            // kể cả khi scan ném IOException.
            valid = key.reset();
        }

        // oldSnapshot có thể so với latest để tìm
        // added/removed/changed tùy bài toán.
        return new KeyResult(latest, valid, overflow);
    }
}
```

Chạy:

```bash
javac WatchOverflowRecoveryDemo.java
java WatchOverflowRecoveryDemo
```

**Stdout dự kiến khi filesystem hỗ trợ watch, tiến trình có quyền I/O trong temp directory và không xảy ra lỗi:**

```text
Initial entries: 0
Exists after create: true
Rescan restored entry: true
Entries after delete: 0
```

Chương trình không in `ENTRY_CREATE` hay số lượng `ENTRY_MODIFY`, vì số lần/số kiểu event **không ổn định giữa các provider/OS**. `watcher.poll(1500, MILLISECONDS)` có thể nhận key hoặc trả null; cả hai nhánh vẫn lấy snapshot hiện thời nên các dòng output trên có ý nghĩa độc lập với việc notification tới đúng lúc hay không.

### Tại sao code vẫn có giới hạn?

- `Map<Path,Stamp>` là **cache trạng thái**, không phải nhật ký mọi thao tác.
- Fingerprint chỉ dựa trên `size`, `lastModifiedTime`, `isDirectory`; không phát hiện chắc chắn mọi sửa đổi nếu metadata không đổi.
- Việc scan có thể bị ảnh hưởng bởi concurrent rename/delete. Chỉ có một writer trong bài demo nên dễ kiểm chứng.
- Nếu directory bị xóa hoặc WatchKey trở thành invalid, chương trình ném lỗi thay vì im lặng treo.
- Đoạn code **không xử lý đệ quy** thư mục con.
- Demo dùng polling trong thời hạn hữu hạn để chạy xong. Watcher server thực tế thường có event loop lâu dài và hệ thống shutdown/cancel rõ ràng.
- Code không gây OVERFLOW thật; nhánh `event.kind() == OVERFLOW` đã được triển khai, còn cơ chế mất trạng thái được thử bằng cách làm cache `stale` rỗng.

## 9. Giải thích bước một: đăng ký trước rồi scan

Trong `main`:

```java
directory.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);

Map<Path, Stamp> known = scan(directory);
```

Việc đăng ký trước giúp WatchService có cơ hội ghi nhận những thay đổi đến sau lúc registration thành công. Khi lấy initial snapshot, ta biết các mục **đang có ở thời điểm quá trình quét quan sát**.

Điểm cần phân biệt:

- `WatchService` là nguồn notification.
- `scan(directory)` là cách đọc trạng thái hiện thời của các directory entries.
- Khi một event đến sau scan, xử lý key sẽ rescan.
- Khi đã mất một event, periodic rescan có thể sửa lại cache nếu thay đổi còn được phản ánh ở trạng thái hiện tại.
- Cả scan lẫn WatchService đều không tạo một snapshot filesystem **nguyên tử toàn thư mục** trước writer khác. Nếu yêu cầu snapshot nhất quán tuyệt đối, cần đồng bộ writer hoặc thiết kế lưu trữ/version phù hợp.

## 10. Giải thích bước hai: nhận key và kiểm tra overflow

Mã cốt lõi:

```java
WatchKey key = watcher.poll(1500, TimeUnit.MILLISECONDS);

if (key != null) {
    KeyResult result = consumeAndRescan(directory, known, key);
    known = result.snapshot();
}
```

`poll(timeout, unit)` chờ có giới hạn, thuận tiện để demo không đứng chờ vô hạn nếu platform không phát notification. Khi không có key, nó trả null; điều đó **không chứng minh thư mục không thay đổi**.

Trong `consumeAndRescan`, phải kiểm tra:

```java
if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
    overflow = true;
    continue;
}
```

**Trước** khi ép `event.context()` sang `Path`. Với `OVERFLOW`, không giả định `context` chứa tên file có thể resolve. `OVERFLOW` không xác định chính xác file nào đã thay đổi; không thể suy ra trạng thái từ nó.

`ENTRY_*` bình thường thì `context()` đối với Path watcher thường là **tên/path tương đối**, nên:

```java
Path candidate = directory.resolve(relativeName);
```

chỉ là candidate tại thời điểm xử lý. File có thể đã bị rename/delete, nên mọi thao tác mở/đọc phải sẵn sàng xử lý `NoSuchFileException` và các lỗi khác.

## 11. Giải thích bước ba: quét directory an toàn hơn

Trong helper `scan`:

```java
try (DirectoryStream<Path> entries =
         Files.newDirectoryStream(directory)) {
    for (Path entry : entries) {
        BasicFileAttributes attrs = Files.readAttributes(
                entry, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
    }
}
```

Đây là đoạn trích đã rút gọn; trong chương trình hoàn chỉnh có bắt `NoSuchFileException` cho từng entry.

Tại sao dùng `DirectoryStream`?

- Không bắt buộc đưa tất cả Path vào một danh sách trước khi bắt đầu vòng lặp.
- Dễ đóng tài nguyên bằng try-with-resources.
- Có thể kết hợp với `readAttributes` để lấy metadata cần so sánh.

### TOCTOU trong lúc rescan

Giữa `Files.newDirectoryStream` và `Files.readAttributes`, một mục có thể bị xóa. Demo bắt `NoSuchFileException` và bỏ mục đó trong lượt quét hiện tại. Một rescan sau sẽ giúp tiến gần trạng thái mới.

Nếu không đọc được directory vì permission hoặc lỗi I/O, **không tự đánh dấu thư mục rỗng**. Một cache chuyển từ “có 1.000 file” sang “rỗng” chỉ vì bị `AccessDeniedException` là lỗi nghiêm trọng. Nên giữ cache cũ ở trạng thái cần retry, báo metrics/error và có policy phục hồi. Code demo cho phép lỗi khác propagate.

### NOFOLLOW_LINKS

`LinkOption.NOFOLLOW_LINKS` yêu cầu thao tác metadata trên **mục link** thay vì tự đi theo symbolic link. Điều này giúp tránh vô tình đi theo symlink tới mục nằm ngoài root trong giai đoạn snapshot metadata. Nhưng nó không tự tạo một sandbox hoàn chỉnh; nếu ứng dụng sau đó mở nội dung file theo path, vẫn cần chính sách path/symlink và quyền OS phù hợp.

## 12. So sánh snapshot: mục mới, mục biến mất, mục có dấu vết khác

Giả sử trước:

```text
Snapshot cũ:
  A.txt -> size=10, mtime=100
  B.txt -> size=20, mtime=100
```

Và sau rescan:

```text
Snapshot mới:
  B.txt -> size=35, mtime=110
  C.txt -> size=8,  mtime=105
```

Đối chiếu:

- `A.txt`: không còn trong snapshot mới → **removed**.
- `B.txt`: vẫn tồn tại nhưng metadata khác → **changed**.
- `C.txt`: chỉ có trong snapshot mới → **added**.

Ví dụ helper minh họa:

```java
static void describeDifference(
        Map<Path, Stamp> previous,
        Map<Path, Stamp> current) {

    for (var entry : current.entrySet()) {
        Stamp old = previous.get(entry.getKey());

        if (old == null) {
            System.out.println("ADDED " + entry.getKey());
        } else if (!old.equals(entry.getValue())) {
            System.out.println("CHANGED " + entry.getKey());
        }
    }

    for (Path name : previous.keySet()) {
        if (!current.containsKey(name)) {
            System.out.println("REMOVED " + name);
        }
    }
}
```

Đây là một **method minh họa bổ sung** dùng record `Stamp` của chương trình chính, không thuộc stdout cố định của demo. `HashMap` không quy định thứ tự iteration, nên nếu in danh sách thay đổi có thể sort tên trước khi in cho test deterministic.

### Không khẳng định phát hiện mọi sửa đổi

Metadata fingerprint không bảo đảm phát hiện mọi thay đổi:

- Writer có thể ghi nội dung khác với **cùng kích thước**.
- Độ phân giải `mtime` có thể không đủ tinh trong một số filesystem.
- Thao tác restore timestamp có thể khiến metadata trông như cũ.
- File có thể bị thay bằng object khác mà dấu metadata tương tự.
- Entry có thể bị tạo rồi xóa giữa hai lần scan mà không xuất hiện trong snapshot.

Nếu nghiệp vụ cần phát hiện nội dung thực, có thể hash file với `MessageDigest`; nhưng hash tốn I/O, và file có thể thay đổi ngay trong khi hash. Muốn snapshot bất biến, nên yêu cầu producer công bố file đã đóng/immutable, dùng versioned directory hoặc một cơ chế giao dịch phù hợp.

## 13. Vì sao cần reconcile ngay cả khi không có OVERFLOW?

Có hai cách triển khai watcher:

**A. Event-driven incremental:** chỉ cập nhật mục được event nhắc đến. Nhanh hơn với thư mục lớn, nhưng nhạy cảm hơn với việc bỏ sót, coalescing và race.

**B. Rescan-driven:** event chỉ là tín hiệu để quét lại directory. Chậm hơn, nhưng dễ suy luận về **trạng thái cuối cùng** và phù hợp với bài học.

Khi filesystem provider phát `OVERFLOW`, cả hai phương án phải có cơ chế **full rescan**. Với A, có thể dùng snapshot hiện tại rồi diff; với B, handler đã dùng full rescan nên chỉ cần đánh dấu/log lý do và bảo đảm cache được cập nhật.

Một watcher production có thể dùng:

```text
START
  -> register
  -> initial full scan
  -> loop:
       wait timed poll
       if key:
         drain events
         if OVERFLOW:
           full rescan
         else:
           process changed paths as hints
         reset key
       if periodic interval elapsed:
         full rescan
       if invalid key:
         remove/re-register per policy
```

Periodic full scan là lớp **chống lệch trạng thái** bổ sung; nó không biến WatchService thành log đầy đủ hay bảo đảm thấy mọi trạng thái trung gian.

## 14. Xây watcher chạy liên tục

Ví dụ event loop minh họa (không phải class độc lập):

```java
while (running.get()) {
    WatchKey key;

    try {
        key = watcher.poll(1, TimeUnit.SECONDS);
    } catch (ClosedWatchServiceException ex) {
        break;
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        break;
    }

    if (key != null) {
        boolean overflow = false;

        try {
            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                    overflow = true;
                    continue;
                }
                // Thu thập path hints; không mở file mù quáng.
            }

            if (overflow) {
                // Full rescan + reconcile.
            } else {
                // Incremental handling hoặc rescan theo thiết kế.
            }
        } finally {
            if (!key.reset()) {
                // Hủy/loại bỏ registration invalid.
            }
        }
    }

    // Theo lịch: kiểm tra health, cờ dừng, periodic rescan.
}
```

Đây là **mã minh họa**, biến `running` (ví dụ `AtomicBoolean`), `watcher` và các hành động nội bộ cần được khai báo. Khi chạy lâu dài, phải có chính sách kiểm soát ngoại lệ I/O, backpressure và state.

### Dừng watcher

- Với `take()`, shutdown thường cần `Thread.interrupt()` hoặc đóng `WatchService` từ thread điều khiển.
- Với `poll(timeout)`, thread có thể kiểm tra cờ dừng sau timeout; vẫn nên đóng service khi thoát.
- `ClosedWatchServiceException` sau chủ động `close()` thường là tình huống shutdown hợp lệ, không nhất thiết là lỗi.
- `InterruptedException` cần được xử lý đúng, thường khôi phục interrupt flag nếu không có lý do nuốt tín hiệu.
- `finally` không chạy khi mất điện/kill tiến trình đột ngột; khi khởi động lại nên **rescan ban đầu**, không tin rằng events thời gian downtime còn được lưu.

## 15. WatchKey invalid: phải phục hồi registration

Nếu `key.reset()` trả `false`, `WatchKey` không còn hợp lệ. Một số nguyên nhân:

- Thư mục được theo dõi bị xóa hoặc trở nên không còn truy cập được theo cơ chế provider.
- Ứng dụng hủy registration bằng `key.cancel()`.
- `WatchService` đã đóng.
- Provider mất khả năng theo dõi mục.

Đừng chỉ `continue` vòng lặp và mong có thêm events từ key đó. Với watcher nhiều thư mục, cần loại key khỏi map và xác định có phải đăng ký lại hay không.

Nếu thư mục bị xóa rồi được tạo lại cùng đường dẫn, **registration cũ không phải lúc nào cũng tự phục hồi**. Một ứng dụng cần giám sát liên tục phải có timer kiểm tra parent/root, re-register path mới sau khi nó tồn tại trở lại và rescan lại.

Chú ý race: thư mục có thể thay đổi ngay giữa lúc kiểm tra tồn tại và register; luôn xử lý ngoại lệ và retry có giới hạn.

## 16. Khi theo dõi nhiều thư mục

Có thể đăng ký nhiều `Path` vào cùng `WatchService`. Gắn `WatchKey` với thư mục:

```java
Map<WatchKey, Path> registrations = new HashMap<>();

WatchKey key = directory.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);

registrations.put(key, directory);
```

Đây là đoạn minh họa cần biến `directory`, `watcher` và imports tương ứng.

Khi xử lý:

```java
Path root = registrations.get(key);
if (root != null) {
    // Resolve event context với đúng root tương ứng.
    // Nếu có OVERFLOW: rescan đúng root này.
}

if (!key.reset()) {
    registrations.remove(key);
}
```

Một sự kiện từ thư mục A **không** được resolve trên root B. Nếu muốn một cache snapshot cho mỗi thư mục, dùng `Map<Path, Snapshot>` hoặc state object gắn key.

Không dùng cùng một `WatchService` với nhiều consumer threads mà giả định **mọi thread đều nhận cùng một event**. Hàng đợi WatchKey thông thường được tiêu thụ bởi một trong các consumer; nên chọn một consumer loop có ownership rõ, rồi phân phối công việc nặng tới worker pool nếu cần.

## 17. Theo dõi cây thư mục đệ quy

Trong Java NIO.2 chuẩn, đăng ký thư mục thường chỉ nhận sự kiện với **các mục trực tiếp**:

```text
root/                  <- đăng ký root
  a.txt                <- quan sát trực tiếp
  sub/                 <- biết sub xuất hiện
    b.txt              <- KHÔNG tự nhận modify b.txt
```

Để theo dõi đệ quy:

1. Duyệt toàn bộ thư mục con hiện có và đăng ký **từng thư mục**.
2. Khi `ENTRY_CREATE` báo tên mới, kiểm tra mục đó có là directory không (và xử lý symlink policy).
3. Đăng ký directory mới và rescan nó.
4. Khi `OVERFLOW` ở một directory, rescan directory đó. Nếu không chắc cây đăng ký còn đầy đủ, cần tái duyệt cây để phát hiện thư mục con mới/đã mất.
5. Khi registration invalid, loại bỏ khỏi map và có kế hoạch tái đăng ký.
6. Giới hạn số watch registrations và chi phí I/O trên cây lớn.

Có race giữa việc duyệt và đăng ký thư mục con; một watcher recursive **không** có transaction bảo đảm nhìn thấy mọi biến động xảy ra cùng lúc. Đối với nghiệp vụ cần phát hiện trạng thái, periodic tree rescan là một lớp phục hồi hữu ích.

## 18. Debounce và file chưa ghi xong

Một `ENTRY_CREATE` không bảo đảm producer đã đóng file. Ví dụ:

```text
Producer:
  create report.csv
  write header
  write 10.000 rows
  close file

Consumer:
  thấy ENTRY_CREATE ngay sau create
  đọc report.csv lúc producer mới ghi 10 dòng
```

Nếu nghiệp vụ import file cần nhận nội dung hoàn chỉnh, có thể thỏa thuận **giao thức công bố**:

- Producer ghi vào file tạm trong thư mục staging.
- Producer hoàn tất write/flush/close và kiểm tra.
- Producer rename/move sang tên đích chính thức khi sẵn sàng; nếu yêu cầu atomicity, chỉ tuyên bố bảo đảm khi provider thực sự hỗ trợ.
- Consumer theo dõi tên file final, không parse temp file đang ghi.

Một chiến lược khác là **debounce** `ENTRY_MODIFY`: đợi file không thay đổi metadata trong một khoảng thời gian nhất định trước khi đọc. Nhưng debounce không chứng minh file đã hoàn chỉnh trong mọi trường hợp: producer có thể tạm ngừng lâu giữa các batch.

Điều này liên quan trực tiếp tới OVERFLOW: khi rescan thấy một file mới, vẫn cần xác định **file đã sẵn sàng** theo giao thức nghiệp vụ trước khi xử lý.

## 19. Idempotency: xử lý trùng tín hiệu không gây kết quả sai

WatchService có thể báo cùng file nhiều lần. Nếu mỗi event dẫn tới “gửi email” hoặc “trừ tiền” thì kết quả sẽ sai.

Thiết kế idempotency:

- Với mục tiêu đồng bộ cache, cập nhật theo trạng thái cuối cùng có thể lặp lại an toàn.
- Với import tệp, lưu file/version/hash/transaction ID đã xử lý để không import hai lần.
- Với một tác vụ có side effect, sử dụng queue/job state có trạng thái `PENDING/RUNNING/COMPLETED` và nguyên tắc retry rõ ràng.
- Nếu file bị thay dưới cùng tên, phân biệt phiên bản file dựa trên metadata đáng tin hoặc content version do producer công bố.
- Không coi `event.count()` là số lần nghiệp vụ cần thực hiện. Count có thể thể hiện sự gộp events, không phải số thao tác logic.

Khi overflow khiến mất thứ tự sự kiện, một state-based/idempotent consumer thường phục hồi dễ hơn một consumer cố thực hiện side effect trên từng notification.

## 20. Test OVERFLOW một cách xác định: mô phỏng mất sự kiện ở tầng xử lý

`OVERFLOW` thật phụ thuộc giới hạn hệ thống/provider; ép tạo hàng chục nghìn tệp vừa không portable vừa rủi ro. Thay vì đó, kiểm thử **hành vi phục hồi** bằng cách inject trạng thái “cache stale” hoặc một abstraction event handler.

Trong chương trình hoàn chỉnh, ta cố ý làm:

```java
Map<Path, Stamp> stale = Map.of();       // Cache mất một entry.
Map<Path, Stamp> recovered = scan(dir);  // Trạng thái thực tế.

boolean restored = recovered.containsKey(Path.of("item.txt"));
```

Đây là snippet minh họa, biến `dir` được khai báo trong bối cảnh phù hợp; ví dụ độc lập dùng `directory`.

Cách này **không chứng minh OS phát OVERFLOW**, nhưng chứng minh logic rescan có thể tái phát hiện file hiện hữu khi cache thiếu mục. Có thể mở rộng test:

1. Cache cũ có `deleted.txt` nhưng file thực tế đã bị xóa → rescan phải loại nó.
2. Cache cũ thiếu `new.txt` → rescan phải thêm nó.
3. Cache cũ có metadata cũ của `edited.txt` → rescan thấy fingerprint mới.
4. Một số file vừa tạo rồi xóa trước rescan → không thể tái tạo lịch sử, phải chấp nhận giới hạn này.
5. Scan thất bại vì `AccessDeniedException` → giữ cache ở trạng thái **không chắc chắn** và báo lỗi; không chuyển sang empty map.
6. Event handler nhận synthetic `OVERFLOW` qua abstraction test/stub (không giả là event thật từ OS) → đảm bảo gọi rescan và metrics.

Điểm cần kiểm thử là **reconciliation được kích hoạt và tính đúng của trạng thái cuối**, không phải “bao nhiêu events” mà một OS tình cờ phát trong vài mili-giây.

## 21. Kiểm thử thực tế khi thay đổi diễn ra liên tục

Một bộ tích hợp có thể:

- Tạo/sửa/xóa file giữa nhiều lượt `poll`.
- Rename file trong cùng thư mục.
- Tạo file ở thư mục con (xác nhận không tự watch recursive).
- Tạo nhiều file theo batch.
- Thay file trong khi handler đang quét.
- Khởi động watcher lại sau khi thay đổi đã xảy ra.
- Rút quyền đọc thư mục **chỉ trong test environment**, xác nhận không ghi nhận trạng thái rỗng giả.
- Dừng watcher bằng interrupt/close rồi kiểm tra giải phóng tài nguyên.
- Thực thi trên Linux/Windows/macOS và filesystem thật nếu sản phẩm hỗ trợ.

**Không viết assertion** rằng một lần `Files.writeString` luôn phát chính xác một `ENTRY_CREATE` và một `ENTRY_MODIFY` theo thứ tự cố định. Kiểm thử integration nên chờ **eventual state** trong một deadline hợp lý; kiểm thử thuật toán diff/recovery thì dùng snapshot giả lập để có output deterministic.

### Chuỗi thao tác ví dụ

```text
t0  register root
t1  initial scan: {}
t2  create a.txt
t3  event signal / rescan: {a.txt}
t4  modify a.txt
t5  event signal / rescan: {a.txt updated}
t6  delete a.txt
t7  rescan: {}
```

`t3` và `t5` có thể không tương ứng đúng một WatchKey trên mọi provider. Do đó test nên tập trung vào việc cuối cùng cache phản ánh `{a.txt}`, rồi `{}` khi file đã bị xóa, thay vì cố so event count.

## 22. Khi OVERFLOW nhiều lần: hiệu năng và backpressure

Một `OVERFLOW` lặp lại thường là tín hiệu rằng ứng dụng không theo kịp cường độ thay đổi, event processing quá chậm hoặc provider có giới hạn riêng.

Các biện pháp:

1. **Rút ngắn công việc trong watch loop:** chỉ thu nhận event hint và đưa công việc nặng sang queue có giới hạn.
2. **Gộp công việc theo đường dẫn:** nếu cùng file xuất hiện 100 modify events, chỉ lên lịch một lần kiểm tra trạng thái cuối theo policy.
3. **Thêm debouncing hợp lý** khi input producer có nhiều thao tác nhỏ.
4. **Giới hạn concurrency** của worker để không làm quá tải ổ đĩa/CPU.
5. **Rescan có điều phối:** không để 1.000 overflow events khởi tạo đồng thời 1.000 full scans cùng directory. Coalesce thành một “dirty” flag và một rescan đang chạy.
6. **Đo metrics:** overflow count, queue delay, scan duration, number of watched dirs, number of entries, error rate.
7. **Chạy periodic reconciliation** để bù đắp missed events hoặc downtime.
8. **Đánh giá kiến trúc:** nếu một directory có hàng triệu thay đổi/giây, WatchService + full rescan có thể không phải công cụ đáp ứng đúng nhu cầu. Chọn message queue, database change log hoặc upstream protocol thích hợp.

Không cố giải quyết overflow chỉ bằng cách **tăng kích thước ByteBuffer** trong Java; cơ chế queue/watch notification phụ thuộc OS/provider và không có một nút cấu hình portable cho mọi giới hạn.

## 23. Xử lý lỗi và trạng thái không chắc chắn

Một watcher chạy production cần phân biệt:

| Tình huống | Hành vi đề xuất |
|---|---|
| `watcher.poll(...) == null` | Chưa có key trong thời hạn; có thể periodic rescan |
| `OVERFLOW` | Đánh dấu dirty, full rescan, reconcile |
| `key.reset() == false` | Registration invalid; loại bỏ, cân nhắc đăng ký lại |
| `Files.newDirectoryStream` thất bại | Không tự coi thư mục rỗng; giữ cache cũ và báo lỗi |
| Mục biến mất khi `readAttributes` | Bỏ qua mục đó trong lượt hiện tại, retry/reconcile theo policy |
| `AccessDeniedException` | Kiểm tra process OS permissions, parent directory ACL, mount |
| `ClosedWatchServiceException` | Thường là shutdown; nếu không chủ đích, điều tra lifecycle |
| `InterruptedException` | Phục hồi interrupt flag và thoát/retry theo policy |
| `ENTRY_CREATE` trên file chưa hoàn tất | Chờ publish protocol, retry có giới hạn hoặc debounce |
| Hết bộ nhớ vì lưu snapshot lớn | Giới hạn dữ liệu, dùng index/state store, phân vùng watcher |
| File bị sửa trong khi hash | Dữ liệu không phải snapshot nguyên tử; cần producer contract |

Nếu full rescan thất bại, một thiết kế chặt nên đưa watcher vào trạng thái **DEGRADED/NEEDS_RESCAN**, không cập nhật cache theo một snapshot chưa đầy đủ. Để chạy ổn định, log lỗi và lập lịch retry có backoff; đừng loop nóng khiến lỗi I/O liên tục chiếm CPU.

## 24. Bảo mật khi xử lý file từ thư mục được theo dõi

Một số nguy cơ mà OVERFLOW recovery không giải quyết:

- **Path traversal / symlink escape:** `directory.resolve(event.context())` không phải ranh giới an ninh nếu attacker có thể thay namespace; xác thực root và giới hạn quyền process.
- **Symlink races:** file có thể bị thay giữa lúc kiểm tra metadata và lúc mở. `NOFOLLOW_LINKS` trong một lệnh readAttributes không đảm bảo mọi I/O sau đó an toàn.
- **Không tin file vừa xuất hiện:** một producer không tin cậy có thể tạo content sai, quá lớn, zip bomb hoặc file chứa script; phải validate định dạng và quota.
- **Các quyền OS:** WatchService không cấp quyền đọc file. Process có thể nhận notification nhưng bị từ chối đọc nội dung.
- **Tệp bí mật:** đừng in toàn bộ nội dung hoặc path chứa dữ liệu nhạy cảm trong logs.
- **Multi-tenant:** xác nhận quyền nghiệp vụ trước khi xử lý file của người khác. OS chỉ biết process identity, không tự biết tenant của từng request.
- **Chạy code từ watcher:** tuyệt đối không tự thực thi file mới được phát hiện mà không có kiểm soát nguồn tin cậy, chữ ký/approval và isolation.
- **Xóa nhầm:** reconciliation không phải lệnh `delete` tự động. Khi một entry vắng mặt trong scan, trước khi xóa dữ liệu tại database/backup nên có policy xác nhận trạng thái và xử lý lỗi I/O hợp lý.

File system events là **tín hiệu đầu vào không đáng tin về mặt nghiệp vụ**. Hãy validate nguồn, schema và trạng thái trước khi tạo side effects.

## 25. Mở rộng: thiết kế theo mô hình “dirty directory”

Đối với watcher có nhiều thay đổi liên tục, một cách tổ chức tốt là quản lý **dirty flag**:

```text
WatchService consumer:
  on ENTRY_*:
      đánh dấu path/dir cần kiểm tra
  on OVERFLOW:
      đánh dấu directory FULL_RESCAN_REQUIRED
  reset key

Reconciliation worker:
  if FULL_RESCAN_REQUIRED:
      scan directory
      so snapshot
      apply idempotent changes
      clear flag khi scan + commit thành công
  else:
      kiểm tra paths dirty
      apply state changes
```

Quy tắc quan trọng với đồng thời:

- Không xóa cờ dirty khi một thay đổi mới đã đến **trong lúc** rescan/commit. Cần version/generation counter hoặc cơ chế queue có khóa để không làm mất tín hiệu.
- Không chạy nhiều full rescans đồng thời cùng một directory nếu không có lý do.
- Retry scan/commit thất bại mà không tuyên bố dữ liệu đã đồng bộ.
- Có lịch periodic scan độc lập để bắt missed events.
- Nếu một entry được tạo và xóa trong lúc scan, không suy ra lịch sử đầy đủ từ snapshot cuối.
- Backpressure: khi công việc downstream chậm, không để queue unbounded gây OOM.

Đây là bước nâng cao từ demo single-thread. Không cần triển khai toàn bộ concurrency framework để hiểu trọng tâm WatchService và overflow.

## 26. Các lỗi phổ biến trong bài thực hành

1. **Không xử lý `OVERFLOW`**: cache có thể lệch vĩnh viễn sau khi mất event.
2. **Ép `event.context()` sang `Path` trước khi kiểm tra OVERFLOW**: dữ liệu overflow không đại diện cho file path hợp lệ.
3. **Tin rằng từng event là lịch sử chính xác**: có thể bị gộp hoặc mất, không có exactly-once.
4. **Không gọi `key.reset()`**: bỏ lỡ các tín hiệu tiếp theo.
5. **Không kiểm tra `reset() == false`**: registration invalid vẫn bị giữ trong cấu trúc quản lý.
6. **Dùng `take()` trong thread chính mà không có shutdown**: chờ vô hạn khi không còn sự kiện.
7. **Dùng `poll()` trong vòng busy loop**: CPU tăng cao khi không có key.
8. **Đăng ký sau khi đã scan rồi tưởng không có race**: thay đổi ở khoảng trước registration có thể bị bỏ lỡ.
9. **Đọc `ENTRY_CREATE` như “file đã ghi xong”**: producer có thể đang ghi nội dung.
10. **Chạy tác vụ nặng trực tiếp trong watcher event loop**: backlog tăng và dễ overflow.
11. **Dùng snapshot metadata để tuyên bố mọi nội dung luôn phát hiện được**: hash/version có thể cần thiết.
12. **Nếu scan lỗi thì trả `Map.of()` và xóa toàn bộ cache**: nhầm “không đọc được” với “thư mục rỗng”.
13. **Coi watch root là recursive**: directory con cần đăng ký riêng.
14. **Giải quyết OVERFLOW bằng cách tăng read buffer**: không sửa giới hạn provider event queue.
15. **Tạo hàng triệu file để “unit test overflow”**: không portable, gây áp lực máy; test recovery bằng injection/synthetic state.
16. **Chỉ tin output test ở một OS**: số lượng/thứ tự events thay đổi theo provider.
17. **Không quản lý symlink/TOCTOU**: có thể đọc nhầm file ngoài phạm vi.
18. **Không dùng idempotency**: một file modify có thể kích hoạt xử lý nhiều lần.
19. **Không khôi phục khi restart**: notification thời gian downtime không được WatchService lưu bền.
20. **Đóng watcher nhưng không xử lý ClosedWatchServiceException**: báo lỗi shutdown không cần thiết.
21. **Giữ các keys invalid trong map**: rò reference và mất khả năng theo dõi đúng.
22. **Dùng WatchService làm audit log tài chính/pháp lý**: không có bảo đảm đầy đủ mọi thao tác trung gian.
23. **Không giới hạn queue/concurrency**: memory/CPU exhaustion khi thư mục đổi nhanh.
24. **Xem kết quả scan là snapshot nguyên tử**: filesystem có thể đổi trong lúc duyệt, cần giao thức writer.
25. **Hòa giải cache xong nhưng không reset key đúng lúc**: mất khả năng nhận notification tiếp theo.

## 27. Bài tập mở rộng

### Bài 1 — Diff added/removed/changed

Viết hàm `diff(oldSnapshot, newSnapshot)` trả ba tập `added`, `removed`, `changed`. Dùng record `Stamp` trong ví dụ. Thử dữ liệu giả lập để stdout không phụ thuộc WatchService.

### Bài 2 — Force reconciliation khi mất sự kiện

Tạo file `A.txt` rồi không đưa event vào cache; gọi `scan` và cập nhật cache. Tiếp tục xóa file và quét lại để loại mục bị mất. Giải thích tại sao đây là test recovery nhưng **không khẳng định OS đã phát OVERFLOW**.

### Bài 3 — Watch loop chạy 30 giây

Dùng `poll(500, TimeUnit.MILLISECONDS)`, trong 30 giây cho phép bạn tạo/sửa/xóa file thủ công. Đừng in mỗi event không kiểm soát; tổng hợp số key, số overflow và số lần rescan.

### Bài 4 — Debounce

Thêm map `Path → lastHintTime`, gộp nhiều modify hints trong 300–500 ms và chỉ xử lý khi đã đủ thời gian; sau cùng vẫn validate file complete bằng producer contract.

### Bài 5 — Theo dõi đệ quy

Duyệt cây và đăng ký từng thư mục. Khi `ENTRY_CREATE` là directory, đăng ký rồi scan nội dung. Khi key invalid, loại khỏi map. Thêm periodic full tree rescan để phục hồi khoảng race.

### Bài 6 — Khôi phục sau restart

Chạy watcher, tạo file, tắt tiến trình, sửa/xóa/thêm file trong lúc watcher tắt, bật lại. Chứng minh initial scan tái lập **trạng thái cuối**, nhưng không cho biết chính xác mỗi thao tác xảy ra trong downtime.

### Bài 7 — Giới hạn tài nguyên

Giả lập 10.000 event hints cho cùng một tên file bằng unit test abstraction (không tạo 10.000 file thật). Đảm bảo scheduling coalesce thành một công việc kiểm tra trạng thái cuối và queue không tăng không giới hạn.

## 28. Câu hỏi tự kiểm tra

**1.** `OVERFLOW` có cung cấp tên những file đã bị mất event không?  
**Không.** Nó chỉ báo khả năng mất notification; phải rescan trạng thái hiện tại.

**2.** Sau full rescan, có thể biết file nào đã được tạo rồi xóa giữa hai lần scan không?  
**Không chắc.** Trạng thái cuối có thể không lưu dấu vết thao tác trung gian.

**3.** Vì sao event handler cần gọi `key.reset()`?  
**Để key có thể tiếp tục nhận báo hiệu** nếu registration còn hợp lệ.

**4.** `key.reset() == false` nghĩa là gì?  
**Registration invalid**, cần loại khỏi watcher state và cân nhắc đăng ký lại.

**5.** `poll(timeout)` trả null có chứng minh không có file đổi không?  
**Không.** Chỉ là chưa có key được lấy trong khoảng đợi, với mọi giới hạn của provider.

**6.** Vì sao snapshot nên đọc trực tiếp từ filesystem thay vì tin vào danh sách events?  
**Vì events có thể gộp, đến trễ hoặc bị mất**, còn snapshot phản ánh trạng thái được quan sát tại thời điểm scan.

**7.** Có thể xử lý `ENTRY_CREATE` bằng cách parse file ngay không?  
**Không nên mặc định.** Producer có thể còn ghi; dùng publish protocol/validation/debounce phù hợp.

**8.** `Files.newDirectoryStream(root)` có tự quét đệ quy không?  
**Không.** Nó liệt kê các mục trực tiếp trong root.

**9.** Fingerprint size + mtime có phát hiện mọi lần thay nội dung không?  
**Không.** Có thể cần digest/version/snapshot protocol khi yêu cầu cao hơn.

**10.** Vì sao không nên stress tạo hàng triệu file chỉ để unit test overflow?  
**Vì kết quả phụ thuộc provider và có thể làm quá tải môi trường**; nên test recovery độc lập với nguồn event.

**11.** Khi full rescan ném `AccessDeniedException` có nên gán cache bằng empty map không?  
**Không.** “Không đọc được” không đồng nghĩa “không có entry”; giữ trạng thái không chắc chắn và retry.

**12.** `WatchService` có thể dùng làm exactly-once audit log không?  
**Không.** Nó không bảo đảm lưu bền và phát lại mọi thay đổi.

## 29. Checklist trước khi triển khai

- [ ] Xác định directory root và file types cần theo dõi.
- [ ] Xác định permission của process và filesystem/provider hỗ trợ.
- [ ] Đăng ký root trước initial scan khi phù hợp.
- [ ] Định nghĩa snapshot cache và mức chính xác cần thiết của metadata/hash/version.
- [ ] Nhận `WatchKey` bằng take hoặc timed poll, có shutdown policy.
- [ ] Drain `pollEvents()` và **xử lý OVERFLOW trước context cast**.
- [ ] Với OVERFLOW, full rescan và reconcile theo trạng thái thực tế.
- [ ] Có periodic reconciliation/initial scan khi cần phục hồi missed events.
- [ ] Bảo đảm `key.reset()` và xử lý key invalid.
- [ ] Định nghĩa registration map nếu theo dõi nhiều thư mục.
- [ ] Không giả định recursive watch; đăng ký subdirectories riêng.
- [ ] Dùng idempotent processing, queue có giới hạn và debounce phù hợp.
- [ ] Xử lý file chưa hoàn tất, rename, symlink và TOCTOU.
- [ ] Không biến scan failure thành trạng thái rỗng giả.
- [ ] Thống kê overflow, latency, rescan errors, queue depth.
- [ ] Kiểm thử đúng/tái lập bằng synthetic state và trên OS thật cho integration.
- [ ] Không xác nhận số lượng hay thứ tự `ENTRY_MODIFY` cố định.
- [ ] Thử restart để xác nhận cache được xây lại từ snapshot.
- [ ] Đóng WatchService, xử lý interrupt, cancel keys khi không cần nữa.
- [ ] Nếu yêu cầu mọi thao tác chính xác, chọn journal/transaction log khác.

## 30. Tổng kết

- **WatchService là hệ thống thông báo thay đổi thư mục**, không phải log đầy đủ hay snapshot nhất quán của filesystem.
- **`OVERFLOW` là tín hiệu rằng một số events có thể đã bị mất**. Không thể khôi phục trực tiếp danh sách event bị bỏ; cần **quét lại trạng thái hiện tại**.
- Một thiết kế đơn giản đáng tin hơn cho bài thực hành là **register → scan → poll/take → drain events → rescan/reconcile → reset → lặp**.
- **WatchEvent.context()` với `ENTRY_*` thường là Path tương đối**; phải gắn đúng thư mục đã đăng ký. Với `OVERFLOW`, không ép context sang Path.
- **Snapshot metadata chỉ phát hiện được sự khác biệt mà nó lưu**; size/mtime không đủ cho mọi yêu cầu dữ liệu.
- **Unit test recovery bằng synthetic stale cache**, không phụ thuộc tạo overflow thật; integration test kiểm tra eventual state, không đếm số lượng events cố định.
- Khi cần production-grade watcher: thêm shutdown, re-registration, periodic rescan, xử lý race, idempotency, giới hạn tài nguyên và giám sát.

### Tài liệu tham khảo Java 17

- [WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html)
- [WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html)
- [WatchEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html)
- [StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html)
- [Path.register](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#register(java.nio.file.WatchService,java.nio.file.WatchEvent.Kind...))
- [Files.newDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newDirectoryStream(java.nio.file.Path))
- [BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html)
