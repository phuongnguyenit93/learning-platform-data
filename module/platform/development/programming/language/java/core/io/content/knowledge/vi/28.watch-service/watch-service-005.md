# WatchKey.reset() và trạng thái đăng ký không còn hợp lệ trong Java NIO.2

Khi theo dõi thay đổi trong thư mục bằng `WatchService`, chương trình đăng ký một `Path` để nhận các sự kiện `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE`. Lời gọi đăng ký trả về một `WatchKey` đại diện cho **đăng ký của thư mục với WatchService**. Sau khi lấy key ra khỏi hàng đợi và xử lý sự kiện, ứng dụng cần gọi **`key.reset()`** để đăng ký có thể tiếp tục được báo hiệu.

Điểm cốt lõi: `reset()` trả `true` nếu key **vẫn hợp lệ** và có thể được đặt lại trạng thái; trả `false` nếu đăng ký không còn hợp lệ. `false` **không có nghĩa là tạm thời chưa có sự kiện**, cũng không có nghĩa là cần gọi `reset()` lặp liên tục cho đến khi thành công. Khi key đã bị hủy hoặc tài nguyên đang theo dõi không còn truy cập được, cần quyết định **dừng theo dõi, loại bỏ đăng ký cũ hoặc đăng ký mới** theo chính sách của ứng dụng.

Bài viết giải thích vòng đời `WatchKey`, trạng thái `READY/SIGNALLED`, cách dùng `pollEvents()` và `reset()` đúng thứ tự, ý nghĩa của `isValid()`, `cancel()`, xử lý mất sự kiện và lỗi phổ biến khi xây dựng một watcher chạy lâu dài.

## 1. WatchService và WatchKey có vai trò khác nhau

Các thành phần thường gặp:

| Thành phần | Vai trò |
| --- | --- |
| `WatchService` | Dịch vụ nhận thông báo và giữ hàng đợi các key đã được báo hiệu |
| `Path` / `Watchable` | Đối tượng được đăng ký để theo dõi; trong tình huống thông thường là thư mục |
| `WatchKey` | Đăng ký cụ thể giữa thư mục với một `WatchService`, có trạng thái hợp lệ/không hợp lệ và khả năng được báo hiệu |
| `WatchEvent<?>` | Một sự kiện đã nhận, gồm loại `kind()`, số lần `count()` và ngữ cảnh `context()` |
| `StandardWatchEventKinds` | Các loại sự kiện tiêu chuẩn như `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY`, `OVERFLOW` |

Đăng ký cơ bản với Java 17:

```java
import java.nio.file.*;
import static java.nio.file.StandardWatchEventKinds.*;

// Đoạn minh họa trong phương thức đã xử lý IOException.
Path directory = Path.of("watched-folder");
try (WatchService watcher =
        FileSystems.getDefault().newWatchService()) {
    WatchKey key = directory.register(
            watcher, ENTRY_CREATE, ENTRY_MODIFY, ENTRY_DELETE);
    System.out.println(key.isValid());
}
```

Đây là một **đoạn minh họa**: thư mục `watched-folder` phải tồn tại và filesystem phải hỗ trợ đăng ký loại sự kiện yêu cầu. Việc đăng ký thất bại có thể ném `IOException`, `UnsupportedOperationException` hoặc ngoại lệ phù hợp khác. Khi thành công, `key` đại diện cho **thư mục được theo dõi**, không đại diện cho một sự kiện cụ thể hoặc một file con.

`WatchService.take()` chờ đến khi có key báo hiệu; `poll()` không chờ và có thể trả `null`; `poll(timeout, unit)` chờ tối đa thời gian chỉ định. **`null` từ `watcher.poll()` và `false` từ `key.reset()` là hai trạng thái hoàn toàn khác nhau.**

## 2. Trạng thái READY và SIGNALLED của WatchKey

Theo mô hình của `WatchKey`, một đăng ký hợp lệ có trạng thái nội bộ **READY** hoặc **SIGNALLED**. Những trạng thái này khác với thuộc tính **valid/invalid**.

- **READY:** Key đang sẵn sàng nhận và báo hiệu sự kiện tiếp theo. Key không cần hiện diện trong hàng đợi lúc này.
- **SIGNALLED:** Một hoặc nhiều sự kiện đã khiến key được báo hiệu; key được đưa vào hàng đợi thông báo của `WatchService` theo quy tắc của provider.
- **INVALID:** Đăng ký không còn sử dụng được, chẳng hạn đã `cancel()`, thư mục không còn truy cập được hoặc `WatchService` đã đóng. `reset()` không thể làm cho key invalid hợp lệ trở lại.

Sơ đồ tư duy:

```text
register(directory) --> WatchKey hợp lệ, READY
                               |
                               | Sự kiện được phát hiện
                               v
                      SIGNALLED / queued
                               |
                               | take() hoặc poll() lấy key
                               | pollEvents() đọc danh sách sự kiện
                               v
                        gọi key.reset()
                         /           \
                 true                false
                  |                    |
             hợp lệ; READY         đăng ký không hợp lệ
             có thể được           dừng dùng key đó;
             báo hiệu nữa          cleanup hoặc re-register
```

**Lấy key ra khỏi hàng đợi không tự động reset key.** Nếu chỉ gọi `pollEvents()` rồi bỏ qua `reset()`, đăng ký vẫn có thể ở trạng thái SIGNALLED và không tiếp tục cung cấp chu kỳ thông báo như mong muốn. Đây là lý do vòng lặp xử lý key luôn có bước reset sau khi hoàn tất phần sự kiện hiện có.

Nếu các sự kiện mới đến trong khi key còn SIGNALLED, provider có thể tích lũy thêm event trong danh sách chờ; việc gọi `reset()` cho phép key lại được đưa vào hàng đợi theo quy tắc báo hiệu. Không diễn giải một lần `take()` là một sự kiện duy nhất, vì một key có thể chứa **nhiều `WatchEvent`**.

### Mệnh đề dễ nhớ

**`isValid()` nói về đăng ký**, còn **`reset()` điều khiển vòng báo hiệu tiếp theo và báo về tính hợp lệ**. Một key hợp lệ có thể đang READY hoặc SIGNALLED; ngược lại key invalid không trở lại valid chỉ nhờ reset.

## 3. Cách xử lý đúng: take → pollEvents → reset

Một vòng lặp cơ bản:

```java
// Phác thảo, watcher đã được mở và các thư mục đã đăng ký.
while (true) {
    WatchKey key = watcher.take(); // Có thể chờ; ném InterruptedException.
    Path directory = (Path) key.watchable();

    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
            System.out.println("Event loss; rescan needed");
            continue;
        }

        Path relative = (Path) event.context();
        Path changed = directory.resolve(relative);
        System.out.println(event.kind().name() + ": " + changed);
    }

    boolean stillValid = key.reset();
    if (!stillValid) {
        System.out.println("Registration is no longer valid: " + directory);
        // Cập nhật registry; đăng ký lại nếu directory có thể theo dõi.
    }
}
```

Đây là **phác thảo**, không phải chương trình độc lập vì chưa cung cấp quản lý ngoại lệ, chính sách dừng vòng lặp và cleanup. Hành vi cần nắm:

1. `take()` lấy **một key đã được signal**, không phải một `WatchEvent` lẻ.
2. `key.pollEvents()` trả danh sách event đang tích lũy và lấy chúng ra khỏi danh sách của key. Một lần gọi có thể chứa nhiều event.
3. Với sự kiện thư mục tiêu chuẩn không phải `OVERFLOW`, `event.context()` thường là `Path` tương đối với thư mục mà key theo dõi; dùng `((Path) key.watchable()).resolve(relative)` để có đường dẫn file bị ảnh hưởng.
4. Sau khi xử lý danh sách, gọi `key.reset()` **một lần** rồi kiểm tra boolean trả về.
5. Nếu trả `false`, bỏ giả định đăng ký còn hoạt động: không tiếp tục chờ event từ key cũ như bình thường.

Trong code thực tế, nên ghi trạng thái `WatchKey → Path` bằng `Map` khi theo dõi nhiều thư mục; `key.watchable()` cũng giúp truy ngược đối tượng được đăng ký. Số lượng key còn hợp lệ quyết định có cần tiếp tục vòng lặp hay có thể dừng.

## 4. Ý nghĩa của reset(): true không phải “có event”, false không phải “hết event”

API:

```java
boolean valid = key.reset();
```

Một số tình huống:

| Tình huống | Kết quả mong đợi | Giải thích |
| --- | --- | --- |
| Key được đăng ký, vẫn hợp lệ, chưa có event | `true` | Đang hợp lệ; reset không yêu cầu phải có event trước đó |
| Key được `take()`, xử lý event, thư mục vẫn theo dõi được | `true` | Key tiếp tục chu kỳ báo hiệu |
| Đã gọi `key.cancel()` | `false` | Key đã invalid; reset không đăng ký lại |
| Dịch vụ watcher đã đóng | `false` đối với key không còn hợp lệ | Các đăng ký bị vô hiệu hóa; không thể mở lại bằng reset |
| Thư mục bị xóa / không còn truy cập được | Có thể `false` khi provider đã phát hiện mất hiệu lực | Thời điểm phát hiện phụ thuộc provider và hệ điều hành |
| `watcher.poll()` trả `null` | Không suy ra kết quả reset | Chưa có key nào sẵn sàng trong queue; không nói key nào invalid |

**Không viết logic `if (!key.reset()) { key.reset(); }` để “khôi phục” key.** Reset lần tiếp theo không tự tạo lại registration. Nếu thư mục đã được xóa và tạo lại cùng tên, cần nhận thức đường dẫn mới không nhất thiết còn liên kết với đăng ký theo dõi cũ.

### isValid() và reset() có phải thay thế nhau?

Không hoàn toàn:

```java
boolean registered = key.isValid();
boolean canContinue = key.reset();
```

`isValid()` giúp quan sát key còn hiệu lực **tại thời điểm kiểm tra**. `reset()` là thao tác cần thiết trong chu trình tiêu thụ sự kiện để key trở lại READY, đồng thời trả về trạng thái hợp lệ. Kiểm tra `isValid()` rồi **bỏ `reset()`** là lỗi phổ biến. Cũng không dùng một lần `isValid()` làm cam kết rằng registration không thể bị vô hiệu hóa ở bước tiếp theo; có thể có luồng khác `cancel()` hoặc filesystem thay đổi.

## 5. Tại sao WatchKey trở nên không hợp lệ?

Có nhiều nguyên nhân:

### 5.1. Hủy tường minh bằng cancel()

`key.cancel()` vô hiệu hóa đăng ký của key. Sau đó `key.isValid()` trả `false`, và `key.reset()` cũng trả `false`. `cancel()` không có nghĩa xóa thư mục trên đĩa, cũng không đóng toàn bộ `WatchService` nếu watcher còn được dùng cho đăng ký khác.

```java
// Đoạn minh họa: key được register thành công trước đó.
System.out.println(key.isValid()); // true
key.cancel();
System.out.println(key.isValid()); // false
System.out.println(key.reset());   // false
```

Nếu cùng một thư mục cần theo dõi lại sau hủy, gọi `directory.register(watcher, kinds...)` để nhận một đăng ký hợp lệ. Đừng tiếp tục sử dụng `key` đã hủy.

### 5.2. Đóng WatchService

`watcher.close()` đóng dịch vụ và vô hiệu hóa các key của nó. Luồng đang chờ `watcher.take()` có thể nhận `ClosedWatchServiceException`. Đây thường là **tín hiệu dừng có chủ đích** khi ứng dụng shutdown, không phải cơ hội để reset từng key rồi tiếp tục dùng watcher đã đóng.

### 5.3. Thư mục không còn khả dụng

Nếu thư mục bị xóa, unmount, mất quyền hoặc filesystem không thể tiếp tục giám sát, provider có thể vô hiệu hóa đăng ký. Cách thức và thời điểm nhận biết **không đồng nhất giữa hệ điều hành và provider**.

Một trường hợp rất dễ gây lỗi:

```text
Đăng ký theo dõi: /data/incoming   --> key A hợp lệ
Một tác nhân xóa /data/incoming    --> key A có thể trở nên invalid
Một tác nhân tạo lại /data/incoming --> không có bảo đảm key A tự theo dõi
                                      đối tượng thư mục mới
```

Ngay cả khi đường dẫn có cùng chuỗi ký tự, đối tượng thư mục đã được tạo lại có thể khác. Nếu muốn tiếp tục giám sát, ứng dụng phải có chiến lược **phát hiện + đăng ký lại**, không chỉ tin rằng đường dẫn vừa xuất hiện lại sẽ kích hoạt key cũ.

### 5.4. Đăng ký lại và key hợp lệ

Theo hợp đồng `Watchable.register`, khi đối tượng đã được đăng ký với cùng `WatchService` và key tương ứng còn hợp lệ, đăng ký lại có thể trả về **key hiện có** và cập nhật tập sự kiện theo yêu cầu. Ngược lại, sau khi đã `cancel()` hoặc key invalid, việc đăng ký mới có thể tạo key hợp lệ mới nếu thư mục và dịch vụ vẫn sử dụng được.

Điều cần kiểm tra là **`newKey.isValid()`** và cập nhật bảng ánh xạ key của ứng dụng, không khẳng định key cũ sẽ hồi sinh.

## 6. Java 17 chạy độc lập: quan sát reset, cancel và đăng ký lại

Chương trình sau tạo thư mục tạm, đăng ký các event chuẩn, tạo một file nhỏ để kích hoạt thông báo, đọc event nếu provider chuyển tới trước timeout, thử `reset()`, rồi **chủ động hủy key để chứng minh chắc chắn trạng thái invalid**. Sau đó nó đăng ký lại cùng thư mục và cuối cùng dọn tài nguyên.

Tạo file **`WatchKeyResetDemo.java`**:

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

import static java.nio.file.StandardWatchEventKinds.*;

public final class WatchKeyResetDemo {
    private WatchKeyResetDemo() {}

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watch-key-demo-");
        Path sample = directory.resolve("sample.txt");

        try {
            try (WatchService watcher =
                    FileSystems.getDefault().newWatchService()) {

                WatchKey key = directory.register(
                        watcher, ENTRY_CREATE, ENTRY_MODIFY, ENTRY_DELETE);

                System.out.println("registered valid=" + key.isValid());
                System.out.println("reset while ready=" + key.reset());

                Files.writeString(sample, "hello");

                WatchKey signalled = watcher.poll(5, TimeUnit.SECONDS);
                if (signalled == null) {
                    System.out.println("no event within timeout");
                } else {
                    for (WatchEvent<?> event : signalled.pollEvents()) {
                        if (event.kind() ==
                                StandardWatchEventKinds.OVERFLOW) {
                            System.out.println("OVERFLOW: rescan needed");
                            continue;
                        }
                        System.out.println("event=" + event.kind().name()
                                + " relative=" + event.context());
                    }
                    System.out.println("reset after events="
                            + signalled.reset());
                }

                key.cancel();
                System.out.println("after cancel valid=" + key.isValid());
                System.out.println("after cancel reset=" + key.reset());

                WatchKey newKey =
                        directory.register(watcher, ENTRY_CREATE);
                System.out.println(
                        "new registration valid=" + newKey.isValid());
                newKey.cancel();
            }
        } finally {
            Files.deleteIfExists(sample);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac WatchKeyResetDemo.java
java WatchKeyResetDemo
```

Đầu ra *thường gặp* trên filesystem cục bộ hỗ trợ watcher:

```text
registered valid=true
reset while ready=true
event=ENTRY_CREATE relative=sample.txt
event=ENTRY_MODIFY relative=sample.txt
reset after events=true
after cancel valid=false
after cancel reset=false
new registration valid=true
```

**Không có bảo đảm hai dòng `event=...` luôn xuất hiện đúng số lần hoặc đúng thứ tự như trên.** Provider có thể gộp `ENTRY_MODIFY`, trả nhiều event, chỉ trả một số event trong lần `pollEvents()`, hoặc chưa giao thông báo trong 5 giây. Khi không nhận được key trước timeout, chương trình in `no event within timeout` thay cho các dòng event và `reset after events`. Các dòng kiểm tra trước và sau `cancel()` là điểm chính: **key không hợp lệ không thể được khôi phục bằng `reset()`**.

### Phân tích từng bước

1. `directory.register(watcher, ...)` nhận `WatchKey` hợp lệ. `isValid()` là `true`.
2. `key.reset()` khi chưa có sự kiện vẫn có thể trả `true` vì key hợp lệ; điều này không chứng minh đã nhận event.
3. `Files.writeString(sample, "hello")` tạo tệp nên là một hành động mà provider có thể phát `ENTRY_CREATE` và `ENTRY_MODIFY` theo quy tắc của nó.
4. `watcher.poll(5, TimeUnit.SECONDS)` chờ một key đã signal tối đa 5 giây. Nếu nhận được, `pollEvents()` lấy event để xử lý, sau đó `reset()` cho phép tiếp tục nhận thông báo.
5. `key.cancel()` vô hiệu hóa đăng ký; `key.isValid()` và `key.reset()` đều trả `false`.
6. `directory.register(watcher, ENTRY_CREATE)` cấp một key hợp lệ khi đăng ký lại thành công; cần thay key cũ trong state của chương trình.
7. `try-with-resources` đóng watcher, khối `finally` xóa file/thư mục tạm do chương trình sở hữu.

Ví dụ ưu tiên tính dễ quan sát hơn tính ổn định thời gian sự kiện. Một ứng dụng thật không nên dựa vào timeout 5 giây như bảo đảm sự kiện đã xảy ra, và cũng không nên lấy một sự kiện duy nhất làm bằng chứng không có thay đổi nào khác trong thư mục.

## 7. Xử lý key.reset() == false trong ứng dụng chạy lâu dài

Khi key không thể reset, logic cần phụ thuộc **ý định theo dõi** của ứng dụng. Các khả năng:

- **Directory bị hủy có chủ đích:** Xóa key ra khỏi registry, không đăng ký lại.
- **Ứng dụng đang shutdown:** Đóng watcher, dừng các luồng nhận sự kiện và dọn bộ nhớ.
- **Directory bị xóa hoặc tạm thời không truy cập được:** Đánh dấu thư mục đang offline, quyết định retry/backoff và kiểm tra khả năng đăng ký lại ở một thời điểm sau.
- **Directory được tạo lại:** Đăng ký mới và thực hiện đối chiếu trạng thái thư mục nếu yêu cầu không bỏ sót thay đổi.
- **Tất cả key của watcher đều invalid:** Nếu watcher không còn mục tiêu theo dõi và không có chính sách tự phục hồi, có thể dừng vòng lặp thay vì chờ vô hạn.

Phác thảo xử lý nhiều thư mục:

```java
// Phác thảo trong lớp điều phối watcher, chưa phải chương trình hoàn chỉnh.
Map<WatchKey, Path> registrations = new HashMap<>();

while (running) {
    WatchKey key = watcher.take();
    Path dir = registrations.get(key);

    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
            scheduleRescan(dir);
        } else if (dir != null && event.context() instanceof Path path) {
            processChange(dir.resolve(path), event.kind());
        }
    }

    if (!key.reset()) {
        Path lost = registrations.remove(key);
        if (lost != null && shouldRetry(lost)) {
            scheduleReRegistration(lost);
        }
    }
}
```

Đây là **pseudocode Java mang tính phác thảo**: `watcher`, `running` và các hàm `scheduleRescan`, `processChange`, `shouldRetry`, `scheduleReRegistration` chưa định nghĩa. Chương trình thật cần quản lý `InterruptedException`, `ClosedWatchServiceException`, IOException và shutdown.

**Không đăng ký lại một key invalid chỉ bằng cách bỏ `reset()` rồi tiếp tục gọi `take()`**. Một đăng ký đã mất hiệu lực có thể không bao giờ báo sự kiện trở lại; phải có một đường phục hồi riêng nếu ứng dụng vẫn cần theo dõi thư mục.

### Quy trình phục hồi nên có

1. **Loại key cũ:** Bỏ entry tương ứng trong `Map<WatchKey, Path>` và các cấu trúc quản lý liên quan; không giữ key invalid như một đăng ký đang hoạt động.
2. **Kiểm tra mục tiêu:** Nếu thư mục đã không tồn tại, chờ sự kiện từ **thư mục cha còn được theo dõi** hoặc một lịch kiểm tra/backoff khác; không kỳ vọng key invalid sẽ tự báo thư mục được tạo lại.
3. **Đăng ký lại:** Khi thư mục hợp lệ và provider hỗ trợ, gọi `directory.register(watcher, kinds...)` để nhận key mới.
4. **Đồng bộ hiện trạng:** Quét trạng thái thư mục nếu ứng dụng cần biết chính xác danh sách file, vì giữa lúc đăng ký cũ mất hiệu lực và đăng ký mới có thể đã xảy ra thay đổi không có event.
5. **Giới hạn retry:** Tránh vòng lặp retry không nghỉ khi thư mục không có quyền truy cập, provider lỗi liên tục hoặc filesystem bị tháo gỡ.

Nếu ứng dụng không kiểm soát được tác nhân sửa thư mục, việc đăng ký lại vẫn có khoảng hở thời gian; **WatchService không tự cung cấp nhật ký thay đổi chính xác, bền vững như cơ sở dữ liệu**.

## 8. OVERFLOW và sự kiện bị bỏ lỡ không đồng nghĩa key invalid

`StandardWatchEventKinds.OVERFLOW` biểu thị các sự kiện có thể đã bị mất hoặc loại bỏ. Điều này có thể xảy ra khi ứng dụng tiêu thụ sự kiện không đủ nhanh hay provider có giới hạn hàng đợi. Key **vẫn có thể hợp lệ**, và `reset()` vẫn có thể trả `true`.

| Dấu hiệu | Ý nghĩa | Hành động |
| --- | --- | --- |
| `key.pollEvents()` chứa `OVERFLOW` | Độ đầy đủ của sự kiện không còn được đảm bảo | Quét lại trạng thái thư mục, đồng bộ với dữ liệu thực |
| `key.reset()==false` | Đăng ký không còn hợp lệ | Xóa key khỏi registry, dừng hoặc re-register |
| `watcher.poll()==null` | Chưa có key đang đợi trong queue lúc kiểm tra | Tiếp tục chờ theo chính sách, không tự hủy đăng ký |
| `key.pollEvents().isEmpty()` | Không có event tích lũy tại thời điểm đọc danh sách | Vẫn gọi `reset()` nếu key cần tiếp tục theo dõi |
| `key.isValid()==true` | Đăng ký đang được provider xem là hợp lệ | Tiếp tục vòng xử lý đúng quy trình; không bỏ qua reset |

Khi gặp `OVERFLOW`, `event.context()` không phải một đường dẫn file con sử dụng được. Không cast context của `OVERFLOW` sang `Path`. Các loại sự kiện chuẩn khác thường cung cấp `Path` tương đối; dù vậy ứng dụng nên kiểm tra kiểu dữ liệu của event nếu có provider mở rộng.

### Event không phải nhật ký thay đổi đầy đủ

`ENTRY_MODIFY` có thể được gộp, `count()` có thể lớn hơn 1, thứ tự và thời điểm thông báo phụ thuộc provider. Tạo file rồi đổi tên nhanh có thể sinh chuỗi event khác nhau tùy nền tảng. Một event create không bảo đảm file đã ghi hoàn tất; một event delete không bảo đảm ứng dụng có thể suy ra nội dung file bị xóa. Nếu yêu cầu tính đúng đắn cao, dùng WatchService để **kích hoạt bước kiểm tra trạng thái thực tế** thay vì xem event là nguồn dữ liệu duy nhất.

## 9. WatchService khác với FileChannel và Selector

Nhìn qua các API Java NIO, chữ “key” dễ gây nhầm:

| API | Key / thao tác | Ý nghĩa |
| --- | --- | --- |
| `WatchService` | `WatchKey`, `reset()`, `isValid()` | Theo dõi thay đổi của đối tượng được đăng ký với filesystem |
| `Selector` | `SelectionKey`, `isValid()`, `interestOps()` | Theo dõi readiness của `SelectableChannel`, thường dùng cho socket |
| `FileChannel` | `position()`, `size()`, `force()` | Đọc/ghi tệp; không phải bộ máy phát sự kiện WatchKey |

**`WatchKey.reset()` không có cùng ý nghĩa với `ByteBuffer.reset()`**. `ByteBuffer.reset()` đưa position về mark (nếu mark tồn tại), còn `WatchKey.reset()` điều khiển chu kỳ báo hiệu của đăng ký filesystem và trả boolean về hiệu lực.

Một `WatchKey` có thể còn hợp lệ dù tệp con cụ thể vừa bị xóa; key gắn với **thư mục được đăng ký**, không gắn với từng file con. Xóa tệp con thường tạo `ENTRY_DELETE` và không tự vô hiệu hóa key của thư mục cha. Ngược lại, xóa chính thư mục đang theo dõi có thể làm đăng ký mất hiệu lực.

## 10. Thread interruption, close và vòng lặp shutdown

`WatchService.take()` và `WatchService.poll(timeout, unit)` có thể chờ. Nếu luồng đang đợi bị interrupt, chúng có thể ném `InterruptedException`; nếu watcher đã đóng, chúng có thể ném `ClosedWatchServiceException`.

Một khung điều phối phù hợp:

```java
// Phác thảo trong phương thức watcherLoop(WatchService watcher).
try {
    while (!Thread.currentThread().isInterrupted()) {
        WatchKey key = watcher.take();
        try {
            for (WatchEvent<?> event : key.pollEvents()) {
                process(event, key); // Hàm nghiệp vụ, chưa định nghĩa.
            }
        } finally {
            if (!key.reset()) {
                unregisterLostKey(key); // Hàm nghiệp vụ.
            }
        }
    }
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
} catch (ClosedWatchServiceException shutdown) {
    // Shutdown có chủ đích hoặc watcher bị đóng từ luồng khác.
}
```

Đoạn này **không độc lập** vì `process` và `unregisterLostKey` chưa định nghĩa. Nó nhấn mạnh: khi xử lý event thất bại nhưng key vẫn cần tiếp tục, việc reset phải nằm trong luồng cleanup có chủ đích. Tuy vậy nếu lỗi xử lý có nghĩa ứng dụng phải dừng hoàn toàn, có thể chọn đóng watcher thay vì đặt lại key một cách máy móc; thiết kế error policy rõ ràng.

Đừng cố gọi `take()` vô hạn sau khi `ClosedWatchServiceException` xuất hiện; phải thoát vòng lặp và giải phóng state. Đừng nuốt `InterruptedException` rồi tiếp tục nếu đó là tín hiệu shutdown.

## 11. Giới hạn thực tế khi theo dõi hệ thống tệp

- **Theo dõi thư mục, không tự động đệ quy:** Đăng ký một thư mục không bảo đảm nhận event trong mọi thư mục con sâu bên dưới. Muốn giám sát cả cây, ứng dụng thường phải đăng ký riêng từng thư mục con và xử lý khi thư mục mới xuất hiện.
- **Provider phụ thuộc hệ điều hành:** Khả năng và độ trễ event khác nhau giữa filesystem cục bộ, network filesystem, môi trường container và JDK/provider.
- **Không bảo đảm mọi thay đổi đều sinh một event duy nhất:** Có thể có sự kiện gộp, OVERFLOW, sự kiện đến trễ hoặc các thay đổi diễn ra giữa lúc app xử lý.
- **Xử lý quyền truy cập:** Thư mục có thể bị di chuyển/xóa/mất quyền; khi không truy cập được, vòng phục hồi phải tránh retry quá nhanh.
- **Vùng nhớ và registry:** Nếu theo dõi nhiều thư mục, cần quản lý map từ key tới path, đếm số key valid và dọn key invalid để không giữ bộ nhớ/tài nguyên lâu dài.
- **Không thực hiện I/O nặng trong vòng nhận event nếu không kiểm soát tốc độ:** Những thao tác nặng có thể khiến watcher bị nghẽn và tăng nguy cơ OVERFLOW.
- **Đóng tài nguyên đúng lúc:** `WatchService` là `AutoCloseable`, thích hợp với `try-with-resources`; khi watcher đóng, mọi key của nó không còn phục vụ theo dõi.

Nếu cần đồng bộ chính xác trạng thái tệp giữa các tiến trình hoặc máy, `WatchService` chỉ nên là **tín hiệu phát hiện thay đổi**, không phải nguồn chân lý duy nhất. Có thể cần quét định kỳ, checksum/version, metadata hoặc cơ chế đồng bộ ở tầng ứng dụng.

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Quên `key.reset()` sau `pollEvents()` | Key có thể không tiếp tục chu kỳ báo hiệu | Gọi reset sau xử lý, kiểm tra boolean trả về |
| Coi `reset()==false` là “hôm nay không có event” | Giữ đăng ký đã invalid, có thể chờ vô hạn | Cleanup key và chọn chính sách re-register |
| Gọi `reset()` nhiều lần nhằm hồi sinh key đã cancel | Không tạo được đăng ký hợp lệ mới | `directory.register(watcher, kinds...)` khi còn hợp lệ |
| Coi `watcher.poll()==null` là key invalid | Dừng watcher đúng lúc chưa có event | Phân biệt queue trống và key invalid |
| Dùng `reset()` mà không đọc `pollEvents()` | Không xử lý các event đã tích lũy, khó kiểm soát mất event | Lấy/xử lý event rồi mới reset |
| Chỉ xử lý event đầu tiên trong danh sách | Bỏ thay đổi khác trong cùng lần báo hiệu | Duyệt toàn bộ `pollEvents()` |
| Không xử lý `OVERFLOW` | Bỏ lỡ thay đổi mà ứng dụng không biết | Quét lại thư mục và đồng bộ với thực tế |
| Cast `OVERFLOW.context()` thành `Path` | Sai dữ liệu, có thể `ClassCastException` | Kiểm tra kind trước khi đọc context |
| Xóa/tạo lại thư mục rồi tin key cũ tự hoạt động | Bỏ sót sự kiện sau khi thư mục thay thế | Phát hiện invalid, đăng ký mới và rescan |
| Nghĩ đăng ký thư mục cha bao phủ tự động toàn cây | Không nhận thay đổi sâu ở thư mục con | Đăng ký từng thư mục khi cần recursive watch |
| Không gỡ `WatchKey` đã invalid khỏi map | State sai, tăng bộ nhớ và báo cáo sai số watcher | Xóa registry entry, cập nhật mục tiêu còn active |
| Lờ `InterruptedException` hoặc `ClosedWatchServiceException` | Vòng lặp không shutdown đúng cách | Phân biệt interrupt/close, dừng có chủ đích |

**Ghi nhớ:** Đối với `WatchService`, mỗi lần nhận một key đã được signal, hãy **đọc các `WatchEvent`, xử lý hoặc ghi nhận khả năng mất sự kiện, rồi gọi `WatchKey.reset()` và kiểm tra kết quả**. `true` nghĩa đăng ký còn hợp lệ để tiếp tục theo dõi; `false` nghĩa đăng ký đã invalid và cần cleanup hoặc re-register theo nhu cầu. `reset()` không thể khôi phục một key đã hủy, không thay thế việc đăng ký lại và không bảo đảm toàn bộ lịch sử thay đổi của filesystem.