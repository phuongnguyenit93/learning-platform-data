# Gộp sự kiện trùng và tránh xử lý khi tệp chưa ghi xong với WatchService

**Chủ đề:** Java 7 — `WatchService`  
**Bài học:** Gộp sự kiện trùng và tránh xử lý khi tệp chưa ghi xong  
**Phạm vi:** Java 17+ dùng NIO.2 (`java.nio.file.WatchService`, `WatchKey`, `WatchEvent`, `StandardWatchEventKinds` và `Files`). API WatchService có từ Java 7 nhưng vẫn là API tiêu chuẩn hiện hành. Bài ưu tiên hành vi được JavaDoc bảo đảm, phân biệt phần phụ thuộc filesystem/provider và không dựa vào workaround lỗi thời.

## 1. Bài toán thực tế: một lần lưu file có thể tạo nhiều sự kiện

Giả sử một chương trình A xuất `orders.csv` và chương trình B dùng `WatchService` giám sát thư mục `inbox`. Nếu B xử lý dữ liệu ngay lần đầu nhận `ENTRY_CREATE` hoặc `ENTRY_MODIFY`, có thể xảy ra:

- A mới **tạo tên file** nhưng chưa ghi một byte nào.
- A đã ghi một phần CSV/JSON/ZIP rồi tiếp tục ghi trong vài giây.
- Hệ điều hành phát ra **nhiều `ENTRY_MODIFY`** trong quá trình A ghi, flush, sửa metadata hoặc một ứng dụng chỉnh sửa thực hiện nhiều thao tác.
- Các sự kiện **trùng ngữ nghĩa** được gửi nhiều lần, hoặc được provider/JDK **gộp** thành `WatchEvent` có `count() > 1`.
- B xử lý cùng một file nhiều lần, đọc dữ liệu chưa hoàn chỉnh, tạo duplicate records hoặc báo lỗi giả.
- Có thể mất event do `OVERFLOW`, ứng dụng ngừng hoạt động hoặc filesystem không quan sát đầy đủ thay đổi từ xa.

**Điều quan trọng nhất:** `WatchService` cung cấp **tín hiệu về thay đổi trong thư mục**, không phải giao thức “người ghi đã đóng file”, không phải event log chính xác một-một, không phải transaction và không bảo đảm mỗi file chỉ được xử lý một lần.

Một kiến trúc phù hợp thường gồm ba lớp riêng:

1. **Capture:** nhận event nhanh, lưu ý `OVERFLOW` và giữ vòng watcher hoạt động.
2. **Coalesce/debounce:** gom các event trùng/đến gần nhau theo pathname, trì hoãn xử lý cho đến khi có một **quiet window** hoặc tín hiệu hoàn tất được định nghĩa.
3. **Validate/process:** xác minh file đúng điều kiện đọc/parse, xử lý theo chính sách **idempotent**, retry có giới hạn và reconcile khi sự kiện bị mất.

Nếu **kiểm soát được bên ghi**, giải pháp tốt hơn đoán thời điểm là dùng **giao thức công bố**: ghi vào tên tạm, đóng dữ liệu, rồi move/rename sang tên sẵn sàng, hoặc tạo marker `.ready` sau khi đóng. Nếu **không kiểm soát được bên ghi**, debounce + quan sát độ ổn định + validate là chiến lược giảm rủi ro, **không phải bằng chứng tuyệt đối file đã ghi xong**.

## 2. Cơ chế WatchService và hai cấp độ “gộp”

Một thư mục được đăng ký qua `Path.register(watcher, ENTRY_CREATE, ENTRY_MODIFY, ENTRY_DELETE)`. Watcher cung cấp các `WatchKey`; mỗi key gom một hoặc nhiều `WatchEvent<?>`. Luồng cơ bản:

```text
Producer                  WatchService                 Consumer
   |                            |                           |
   | create orders.csv          |                           |
   |--------------------------->| ENTRY_CREATE              |
   | write chunk #1             |                           |
   |--------------------------->| ENTRY_MODIFY              |
   | write chunk #2             |                           |
   |--------------------------->| ENTRY_MODIFY              |
   | close file                 |                           |
   |                            |                           |
   |                      WatchKey queued                   |
   |                            |------- pollEvents() ----->|
   |                            |             enqueue pathname, not parse now
   |                            |<--------- reset() --------|
   |                            |                           |
   |                            |       debounce + validate |
   |                            |                           |--> process
```

Sơ đồ chỉ là một **tình huống minh họa**, không cam kết thứ tự/số lượng sự kiện thật trên mọi provider. Có filesystem chỉ báo event sau một khoảng trễ; có provider không báo mọi lần sửa.

### 2.1. Cấp 1: WatchEvent.count() — gộp ở tầng JDK/provider

Một `WatchEvent<T>` chứa:

- `kind()`: loại sự kiện, ví dụ `ENTRY_MODIFY`.
- `context()`: với các entry events chuẩn, là `Path` **tương đối với thư mục đã đăng ký**.
- `count()`: số lần event được quan sát trong một event đại diện nếu được gộp.

Theo Java SE 21, `ENTRY_MODIFY` có `count()` bằng **1 hoặc lớn hơn**. Các event chuẩn `ENTRY_CREATE` và `ENTRY_DELETE` có `count()` là **1**. `OVERFLOW` có thể có count lớn hơn 1 và context của nó không phải `Path` được bảo đảm.

Ví dụ một `ENTRY_MODIFY` có `count() == 5` **không** có nghĩa file đã ghi chính xác năm chunk, thay đổi năm dòng, hay đã đóng. Đây là số lần một **loại sự kiện** được ghi nhận theo cơ chế gom của hệ thống, không phải số byte hoặc số lượt ghi nghiệp vụ.

### 2.2. Cấp 2: ứng dụng tự gom theo đường dẫn

Ngay cả khi `count() == 1`, ứng dụng vẫn có thể nhận nhiều `WatchEvent` khác nhau về **cùng `Path`**:

```text
ENTRY_CREATE  report.json
ENTRY_MODIFY  report.json
ENTRY_MODIFY  report.json
ENTRY_MODIFY  report.json
```

Thường chỉ nên giữ **một pending job cho `report.json`**, cập nhật thời điểm nhận event mới nhất. Đó là **application-level coalescing**. Nó không phải chức năng mà WatchService tự giải quyết toàn bộ.

**Cần hai bộ đo riêng:** raw events / `count` để quan sát tải hệ thống, và **số pathname cần xử lý** để lập lịch nghiệp vụ. Nếu tự tăng số job bằng `event.count()`, bạn đã biến một file bị sửa liên tiếp thành nhiều lần đọc không cần thiết.

### 2.3. WatchKey không phải file path

Một `WatchKey` đại diện **đối tượng được đăng ký** (thường là directory), không đại diện một file cụ thể. Với nhiều directory, ánh xạ `WatchKey -> Path registeredDir`. Khi event đến:

```java
WatchEvent.Kind<?> kind = event.kind();

if (kind == StandardWatchEventKinds.OVERFLOW) {
    // Mất event; yêu cầu đối chiếu trạng thái directory.
} else if (event.context() instanceof Path relative) {
    Path file = watchedDir.resolve(relative).normalize();
    // Lưu pathname vào hàng đợi theo chính sách.
}
```

Đây là **snippet**, các biến `event` và `watchedDir` có từ vòng watcher. Phải **kiểm tra OVERFLOW trước** khi cast context sang `Path`, vì context overflow có thể là null hoặc implementation-specific.

Phép `resolve` ở đây khôi phục pathname dựa trên directory đã đăng ký; phép `normalize` chỉ xử lý cú pháp, **không phải kiểm tra an ninh đầy đủ** khi có symlink/TOCTOU.

## 3. Ví dụ chạy được: gộp WatchEvent và đếm event đúng

Ví dụ sử dụng `WatchEvent` giả lập trong bộ nhớ để kiểm tra logic xác định. Không phụ thuộc việc Windows/Linux/macOS phát bao nhiêu event thật.

Tạo file `WatchEventCoalescingDemo.java`:

```java
import java.nio.file.Path;
import java.nio.file.WatchEvent;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import static java.nio.file.StandardWatchEventKinds.*;

public class WatchEventCoalescingDemo {
    record Sample<T>(
            WatchEvent.Kind<T> kind,
            int count,
            T context) implements WatchEvent<T> {
    }

    public static void main(String[] args) {
        List<WatchEvent<?>> events = List.of(
                new Sample<>(ENTRY_CREATE, 1,
                        Path.of("a.txt")),
                new Sample<>(ENTRY_MODIFY, 3,
                        Path.of("a.txt")),
                new Sample<>(ENTRY_MODIFY, 2,
                        Path.of("b.txt")),
                new Sample<>(ENTRY_DELETE, 1,
                        Path.of("b.txt")),
                new Sample<>(OVERFLOW, 1, null));

        Set<String> pending = new TreeSet<>();
        int modifyObservations = 0;
        boolean overflow = false;
        boolean contextsRelative = true;

        for (WatchEvent<?> event : events) {
            if (event.kind() == OVERFLOW) {
                overflow = true;
                continue;
            }

            if (!(event.context() instanceof Path relative)) {
                continue;
            }

            contextsRelative &= !relative.isAbsolute();

            if (event.kind() == ENTRY_DELETE) {
                pending.remove(relative.toString());
            } else {
                pending.add(relative.toString());
            }

            if (event.kind() == ENTRY_MODIFY) {
                modifyObservations += event.count();
            }
        }

        System.out.println(
                "modify-observations=" + modifyObservations);
        System.out.println("pending=" + pending);
        System.out.println("overflow=" + overflow);
        System.out.println(
                "contexts-relative=" + contextsRelative);
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all WatchEventCoalescingDemo.java
java WatchEventCoalescingDemo
```

**stdout chính xác:**

```text
modify-observations=5
pending=[a.txt]
overflow=true
contexts-relative=true
```

**Giải thích:**

1. `a.txt` có event tạo và một event sửa được gộp `count=3`, nhưng vẫn là **một candidate** cần xử lý.
2. `b.txt` có event sửa `count=2` rồi xóa, nên candidate `b.txt` được hủy.
3. `modifyObservations` là `3+2=5`, **không phải năm file cần xử lý**.
4. `OVERFLOW` được xử lý riêng; sau khi overflow, danh sách `pending` không thể được tin là đủ; thực tế phải **reconcile directory**, không chỉ giữ `a.txt`.
5. `TreeSet` cho thứ tự in ổn định và không làm mất thông tin ngoài ra. Trong production, key nên là `Path` và có trạng thái/time/version của từng candidate thay vì chỉ tên file.

Event giả lập dùng để kiểm thử **policy**. Nó không khẳng định filesystem thật sẽ phát đúng thứ tự hoặc count như ví dụ.

## 4. Vì sao không xử lý trực tiếp ngay trong vòng pollEvents?

Một anti-pattern:

```java
for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == ENTRY_MODIFY) {
        Path file = directory.resolve(
                (Path) event.context());
        parseAndImport(file); // Có thể đọc file chưa ghi xong.
    }
}
key.reset();
```

Đây là snippet minh họa một cách làm **không nên áp dụng máy móc**, `parseAndImport` là nghiệp vụ tùy chỉnh. Các rủi ro:

- Người ghi có thể còn giữ handle và bổ sung dữ liệu.
- Một file được parse nhiều lần qua nhiều event.
- Parser chậm giữ watcher thread quá lâu, event mới tích lũy gây `OVERFLOW`.
- Thời gian xử lý một file không có quan hệ trực tiếp với tín hiệu event.
- Nếu key không được reset kịp thời, watcher mất khả năng phân phối sự kiện mới theo cách ứng dụng kỳ vọng.

**Thiết kế tách hai luồng công việc**:

```text
WatchService polling loop (nhanh)
  └── nhận batch từ WatchKey
      ├── OVERFLOW -> lên lịch reconcile toàn thư mục
      ├── ENTRY_DELETE -> hủy pending/ghi trạng thái xóa
      └── ENTRY_CREATE / MODIFY -> update pending[path].lastSeen
      └── reset WatchKey

Scheduler / worker (có giới hạn)
  └── kiểm tra quiet period / readiness contract
      ├── chưa sẵn sàng -> retry có giới hạn
      ├── mất file      -> cancel/ghi trạng thái phù hợp
      ├── đọc/parse sai -> phân loại lỗi và retry / dead-letter
      └── sẵn sàng     -> xử lý idempotent, ghi checkpoint
```

Điều này giữ watcher loop ngắn và cho phép giới hạn **concurrency**, backlog và retry theo nhu cầu. Với hệ thống thực tế, cần bounded queue hoặc giới hạn số pathname pending, không để một đối tượng tràn tải ăn vô hạn RAM.

## 5. Debounce khác throttle

**Debounce theo file:** chỉ xử lý một candidate khi không có event mới về path đó trong ít nhất một khoảng, ví dụ 300 ms. Mỗi event mới cập nhật `lastSeen` và **dời thời điểm xử lý ra sau**.

**Throttle:** cố không xử lý quá một lần mỗi khoảng, nhưng có thể xử lý **ngay ở đầu burst**. Nó giúp giảm tần suất, song vẫn có thể đọc file khi người ghi mới bắt đầu.

Ví dụ:

```text
t(ms):   0     50     110           250         500
         |------|------|-------------|-----------|
event:   C      M      M
throttle process? X
debounce (quiet=100 ms)                         ^ earliest after t=210
```

Sơ đồ cho thấy **throttle leading-edge** có thể đọc giữa lần ghi. Debounce chờ được một khoảng im lặng, nhưng vẫn không bảo đảm file hoàn tất: bên ghi có thể tạm ngừng lâu hơn khoảng quiet rồi tiếp tục.

**Đặt quiet interval thế nào?**

- Theo kích thước và hành vi của bên ghi (editor, upload, network share, scanner).
- Theo độ trễ chấp nhận được ở pipeline.
- Theo số event burst thực tế, nhưng không lấy count làm độ dài file.
- Theo phương án fallback khi quá thời gian mà file vẫn chưa hợp lệ.
- Không hard-code 200/500 ms như một “chuẩn Java”; Java không định nghĩa khoảng đợi an toàn cố định cho mọi file.

### 5.1. Ví dụ runnable: debounce bằng đồng hồ giả lập

Tạo `DebounceByPathDemo.java`:

```java
import java.nio.file.Path;
import java.nio.file.WatchEvent;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import static java.nio.file.StandardWatchEventKinds.*;

public class DebounceByPathDemo {
    static final class Debouncer {
        private final Map<Path, Long> lastSeen =
                new HashMap<>();

        void observe(
                Path path, WatchEvent.Kind<Path> kind,
                long atMillis) {
            if (kind == ENTRY_DELETE) {
                lastSeen.remove(path);
            } else if (kind == ENTRY_CREATE
                    || kind == ENTRY_MODIFY) {
                lastSeen.put(path, atMillis);
            }
        }

        List<String> due(
                long nowMillis, long quietMillis) {
            List<String> result = new ArrayList<>();
            Iterator<Map.Entry<Path, Long>> iterator =
                    lastSeen.entrySet().iterator();

            while (iterator.hasNext()) {
                Map.Entry<Path, Long> entry =
                        iterator.next();
                if (nowMillis - entry.getValue()
                        >= quietMillis) {
                    result.add(
                        entry.getKey().toString());
                    iterator.remove();
                }
            }
            result.sort(String::compareTo);
            return result;
        }
    }

    public static void main(String[] args) {
        Debouncer buffer = new Debouncer();
        Path a = Path.of("a.txt");
        Path b = Path.of("b.txt");
        Path c = Path.of("c.txt");

        buffer.observe(a, ENTRY_CREATE, 0);
        buffer.observe(b, ENTRY_CREATE, 20);
        buffer.observe(a, ENTRY_MODIFY, 80);

        System.out.println(
                "at-150=" + buffer.due(150, 100));

        buffer.observe(a, ENTRY_MODIFY, 160);
        System.out.println(
                "at-200=" + buffer.due(200, 100));
        System.out.println(
                "at-300=" + buffer.due(300, 100));

        buffer.observe(c, ENTRY_CREATE, 310);
        buffer.observe(c, ENTRY_DELETE, 320);
        System.out.println(
                "after-delete=" + buffer.due(500, 100));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all DebounceByPathDemo.java
java DebounceByPathDemo
```

```text
at-150=[b.txt]
at-200=[]
at-300=[a.txt]
after-delete=[]
```

**Đọc kết quả:** `b.txt` đã yên lặng 130 ms ở `t=150` nên đến hạn. `a.txt` vừa sửa ở `t=80`, lúc đó mới qua 70 ms. Sau event ở `t=160`, nó đủ yên lặng khi `t=300`. Một event xóa `c.txt` hủy candidate của file.

Đây là **mô phỏng deterministic**, không dùng `Thread.sleep` hay thời gian đồng hồ thật. Nếu muốn dùng production scheduler, nên đo khoảng thời gian bằng **đồng hồ monotonic** (như `System.nanoTime()`), không dùng ngày-giờ tường `Instant.now()` để so quiet window nếu đồng hồ hệ thống có thể điều chỉnh.

**Giới hạn cố ý:** class demo chỉ lập lịch theo path và xóa candidate khi `due`; nó chưa kiểm tra file ổn định, chưa chống việc job cũ chạy đồng thời với event mới. Hai lớp đó được thêm ở phần tiếp theo.

## 6. Chống job cũ chạy sau event mới: generation/version ticket

Nếu bạn dùng `ScheduledExecutorService.schedule` để đặt một task sau 500 ms, mỗi event mới có thể tạo task mới. Có thể gọi `future.cancel(false)` cho task cũ, nhưng **cancel không bảo đảm một task đã bắt đầu sẽ dừng lại**.

Hãy gắn mỗi pathname với **generation/version**:

1. Event mới → tăng generation.
2. Job được hẹn giờ giữ generation tại lúc tạo.
3. Trước khi bắt đầu xử lý/commit, job so generation hiện tại với generation của nó.
4. Nếu đã có event mới, job cũ bỏ qua.
5. Nếu event xóa file, invalidate pending ticket và hủy lịch phù hợp.

### 6.1. Ví dụ runnable: ticket của job cũ bị loại

Tạo `WatchGenerationTicketDemo.java`:

```java
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

public class WatchGenerationTicketDemo {
    static final class Tickets {
        private final Map<Path, Long> current =
                new HashMap<>();

        long newEvent(Path path) {
            long next = current.getOrDefault(
                    path, 0L) + 1L;
            current.put(path, next);
            return next;
        }

        boolean stillCurrent(
                Path path, long expected) {
            return current.getOrDefault(path, 0L)
                    == expected;
        }

        void delete(Path path) {
            current.remove(path);
        }
    }

    public static void main(String[] args) {
        Tickets tickets = new Tickets();
        Path file = Path.of("orders.csv");

        long old = tickets.newEvent(file);
        long newer = tickets.newEvent(file);

        System.out.println(
                "old-valid="
                + tickets.stillCurrent(file, old));
        System.out.println(
                "new-valid="
                + tickets.stillCurrent(file, newer));
        tickets.delete(file);
        System.out.println(
                "after-delete="
                + tickets.stillCurrent(file, newer));
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all WatchGenerationTicketDemo.java
java WatchGenerationTicketDemo
```

```text
old-valid=false
new-valid=true
after-delete=false
```

**Giới hạn quan trọng:** đây là ví dụ khái niệm chạy đơn luồng. Khi tích hợp với nhiều worker thread, phải đồng bộ/atomicize việc đọc-ghi state (ví dụ dùng `ConcurrentHashMap` với `compute` và một state object an toàn), đảm bảo không có khoảng race giữa **check generation** và **ghi kết quả nghiệp vụ**.

Một worker có thể vừa check ticket hợp lệ, sau đó event mới xuất hiện, rồi worker vẫn commit. Để đạt bảo đảm cao hơn, cần **versioned transaction/CAS hoặc idempotent sink** ở tầng nghiệp vụ; một biến generation trong bộ nhớ không tự cấp exactly-once guarantee.

### 6.2. Key cho coalescing là gì?

Trong một watcher đăng ký nhiều directory, `context()` thường chỉ là relative name. Hai thư mục khác nhau đều có `report.csv` nên **không** được gộp cùng một job theo mỗi `context.toString()`.

Hãy dùng `registeredDirectory.resolve(context).normalize()` làm key theo pathname đã biết, hoặc một **logical resource ID** do ứng dụng định nghĩa. Khi filesystem case-insensitive hoặc alias qua symlink, hai `Path` khác nhau có thể chỉ cùng file; coalescing theo lexical Path không tự dedupe mọi alias. Ngược lại, dựa vào `toRealPath` trên file mới chưa tồn tại có thể gây `IOException`. Định nghĩa chiến lược identity phù hợp data model.

## 7. “Tệp đã yên lặng” không đồng nghĩa “ghi đã xong”

Một cách kiểm tra thường gặp:

1. Chờ không có `ENTRY_MODIFY` trong một khoảng.
2. Đọc `Files.size(path)` và `Files.getLastModifiedTime(path)`.
3. Chờ thêm một khoảng.
4. Đọc lại, nếu kích thước và mtime không đổi thì cho là “ready”.

Đây là **heuristic**, không phải hợp đồng hoàn tất của Java. Có thể sai vì:

- Người ghi tạm ngừng 2 giây rồi tiếp tục.
- File bị thay thế bằng file mới **cùng kích thước và cùng timestamp**.
- Độ phân giải timestamp của filesystem khá thô.
- Byte có thể được ghi lại tại vị trí cũ mà kích thước không đổi.
- Metadata có thể được cache hoặc remote provider báo chậm.
- Một producer có thể giữ handle mở sau khi dữ liệu trông có vẻ ổn.
- Một file lớn có thể đổi nội dung trong khi consumer đang parse, dù trước đó đã có hai samples giống nhau.

**Kết luận an toàn:** size/mtime stability chỉ **giảm khả năng đọc giữa lúc ghi**, không chứng minh hoàn tất. Nếu là ingest dữ liệu quan trọng, cần **protocol** của producer (phần 9/10), checksums/format validation, và cách phát hiện revision mới.

### 7.1. BasicFileAttributes và NOFOLLOW_LINKS

Thay vì gọi `size` và `getLastModifiedTime` trong hai lời gọi rời, có thể yêu cầu `BasicFileAttributes`:

```java
BasicFileAttributes attrs = Files.readAttributes(
        candidate,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);

if (!attrs.isRegularFile()) {
    // Không xử lý directory hoặc symlink entry
}
long bytes = attrs.size();
FileTime updated = attrs.lastModifiedTime();
Object identity = attrs.fileKey(); // Có thể null.
```

Đây là snippet; cần import `Files`, `BasicFileAttributes`, `LinkOption`, `FileTime`, `Path` và xử lý `IOException`.

**Tại sao NOFOLLOW_LINKS?** Nếu ứng dụng chấp nhận symlink không kiểm soát, event dẫn tới pathname có thể trỏ ngoài root. Đọc attrs không theo link là một lớp kiểm tra; nó **không** bảo vệ mọi thành phần parent trong pathname hay ngăn TOCTOU. Với root không đáng tin, cần chính sách bảo mật filesystem đầy đủ.

`fileKey()` có thể giúp phân biệt một số file replacements trên filesystem hỗ trợ nhưng **có thể null**, và không phải UUID portable/trường vĩnh viễn. Không coi `(size,mtime,fileKey)` là fingerprint bảo đảm duy nhất cho mọi file revision.

### 7.2. Ví dụ runnable: metadata ổn định qua hai lần quan sát

Tạo `MetadataStabilityDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
import java.util.HashMap;
import java.util.Map;

public class MetadataStabilityDemo {
    record Fingerprint(
            long size, FileTime modified, Object key) {
    }

    static final class State {
        Fingerprint seen;
        long unchangedSince;

        State(Fingerprint seen, long since) {
            this.seen = seen;
            this.unchangedSince = since;
        }
    }

    static final class Probe {
        private final Map<Path, State> states =
                new HashMap<>();

        boolean seemsStable(
                Path file, long nowMillis,
                long requiredQuietMillis) throws IOException {
            BasicFileAttributes attrs =
                    Files.readAttributes(
                        file, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS);

            if (!attrs.isRegularFile()) {
                states.remove(file);
                return false;
            }

            Fingerprint actual = new Fingerprint(
                    attrs.size(),
                    attrs.lastModifiedTime(),
                    attrs.fileKey());
            State previous = states.get(file);

            if (previous == null
                    || !previous.seen.equals(actual)) {
                states.put(
                    file, new State(actual, nowMillis));
                return false;
            }

            return nowMillis - previous.unchangedSince
                    >= requiredQuietMillis;
        }
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("stable-");
        Path file = dir.resolve("data.txt");

        try {
            Probe probe = new Probe();

            Files.writeString(
                    file, "A", StandardCharsets.UTF_8);
            System.out.println(
                    "first=" + probe.seemsStable(file, 0, 200));

            Files.writeString(
                    file, "ABCDEF", StandardCharsets.UTF_8);
            System.out.println(
                    "changed="
                    + probe.seemsStable(file, 100, 200));

            System.out.println(
                    "after-quiet="
                    + probe.seemsStable(file, 350, 200));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all MetadataStabilityDemo.java
java MetadataStabilityDemo
```

```text
first=false
changed=false
after-quiet=true
```

Lần ghi thứ hai đổi **kích thước từ 1 byte thành 6 byte**, nên probe phát hiện change ngay cả khi timestamp có độ phân giải thô. `nowMillis` là đồng hồ giả lập do test truyền vào, không dùng `sleep`. Trong production, thời gian dùng cho quiet window cần lấy từ monotonic clock và được quản lý đúng thread-safety.

**Rất quan trọng:** kết quả `after-quiet=true` chỉ nghĩa **ba thành phần được quan sát đã giữ nguyên đủ lâu trong test**. Nó **không phải xác nhận người ghi đã close**, không tự bảo đảm parser có snapshot nhất quán. Đừng xây dựng hệ thống giao dịch quan trọng chỉ dựa vào kết quả này.

## 8. Kiểm tra định dạng và hoàn tất theo hợp đồng của producer

Nếu ingest `CSV`, `JSON`, `ZIP`, protobuf hoặc file riêng của doanh nghiệp, cần một bước **validate** độc lập với việc tệp có vẻ im lặng:

- Parse toàn bộ nội dung và từ chối truncated/corrupt files.
- Kiểm tra schema/version/các trường bắt buộc.
- Nếu producer định nghĩa **EOF marker**, checksum hoặc expected length, kiểm tra các giá trị đó.
- Nếu producer cung cấp manifest gồm size/hash và phát hành sau khi đóng dữ liệu, dùng manifest làm một tín hiệu readiness mạnh hơn mtime.
- Nếu file quá lớn, đọc theo stream, giới hạn bytes và dùng parser streaming; không `Files.readAllBytes` không giới hạn trên dữ liệu chưa tin cậy.
- Nếu dữ liệu nhạy cảm, kiểm tra authentication/authorization, nội dung và đường dẫn trước khi đưa vào hệ thống.

**Lưu ý:** parser thành công không tự chứng minh file sẽ không bị viết thêm về sau. Với dữ liệu tuân theo một giao thức chặt, bên ghi phải cam kết không sửa sau khi phát tín hiệu hoàn tất.

### 8.1. Ví dụ runnable: EOF marker do producer và consumer cùng quy ước

Ví dụ dùng format giáo dục: một tệp hợp lệ phải có dòng cuối `END` và kết thúc bằng newline. Đây **không phải quy tắc chung của CSV/Java**, mà là **giao thức tùy chỉnh** giữa producer và consumer.

Tạo `FramedPayloadDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FramedPayloadDemo {
    static boolean validPayload(Path file)
            throws IOException {
        String text = Files.readString(
                file, StandardCharsets.UTF_8);

        String[] lines = text.split("\n", -1);
        return lines.length == 4
                && lines[0].equals("id,qty")
                && lines[1].matches("[0-9]+,[0-9]+")
                && lines[2].equals("END")
                && lines[3].isEmpty();
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("frame-");
        Path file = dir.resolve("orders.csv");

        try {
            Files.writeString(
                    file,
                    "id,qty\n7,2\n",
                    StandardCharsets.UTF_8);
            System.out.println(
                    "partial-valid=" + validPayload(file));

            Files.writeString(
                    file,
                    "id,qty\n7,2\nEND\n",
                    StandardCharsets.UTF_8);
            System.out.println(
                    "complete-valid=" + validPayload(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all FramedPayloadDemo.java
java FramedPayloadDemo
```

```text
partial-valid=false
complete-valid=true
```

Nếu consumer không biết producer có cam kết chỉ thêm `END` **sau khi toàn bộ dữ liệu đã hoàn tất** hay không, marker này cũng có thể bị sao chép vào một file chưa xong rồi bị ghi tiếp. **Giá trị của marker nằm ở hợp đồng producer, không phải phép màu của chuỗi ký tự.**

Trong hệ thống có schema thực, sử dụng parser phù hợp chứ không chỉ regex trên một dòng. Tránh upload zip bombs, nội dung vượt quota, path traversal từ tên entry archive và các nội dung không tin cậy.

## 9. Giải pháp ưu tiên khi kiểm soát producer: ghi tạm rồi công bố

Nếu có quyền thiết kế cả bên ghi và bên xử lý, hãy tách rõ hai giai đoạn:

1. Producer **ghi dữ liệu** vào một pathname tạm mà consumer không theo dõi để ingest, ví dụ `.orders-uuid.part`.
2. Producer đóng writer/stream, hoàn tất checksum/validation hoặc metadata cần thiết.
3. Producer **công bố** kết quả dưới pathname chính thức `orders-uuid.csv`.
4. Consumer chỉ quan sát/ingest **tên chính thức**, không xử lý `.part`.

Một cách publish là move/rename trong cùng filesystem:

```java
Files.move(
        staging,
        published,
        StandardCopyOption.ATOMIC_MOVE);
```

Đây là **snippet**, không phải guarantee bất kể filesystem. `ATOMIC_MOVE` yêu cầu thực hiện move theo cơ chế atomic của provider; nếu không hỗ trợ, `AtomicMoveNotSupportedException` được ném.

**Không nhầm atomic move với:**

- **Atomic copy:** `Files.copy` không tự atomic.
- **Atomicity của cả giao dịch dữ liệu:** một rename atomic không đồng nghĩa mọi producer phụ thuộc lẫn nhau đều hoàn tất.
- **Durability qua mất điện:** cần flush/fsync/metadata durability theo hệ điều hành và yêu cầu ứng dụng; `close()` đơn lẻ không đồng nghĩa dữ liệu đã chắc chắn được đồng bộ xuống đĩa.
- **Portable atomic overwrite:** khi target đã tồn tại và dùng `ATOMIC_MOVE`, semantics thay thế target là **implementation-specific**. Không tùy tiện thêm `REPLACE_EXISTING` rồi tuyên bố mọi provider đều atomic replace.
- **Exactly-once:** watcher có thể báo event nhiều lần sau publish; consumer vẫn cần idempotency.

### 9.1. Ví dụ runnable: dùng tên publish mới để tránh overwrite

Tạo `AtomicPublicationDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class AtomicPublicationDemo {
    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("publish-");
        Path stage = Files.createTempFile(
                dir, ".orders-", ".part");
        Path published = dir.resolve("orders-001.csv");

        try {
            Files.writeString(
                    stage,
                    "id,qty\n7,2\n",
                    StandardCharsets.UTF_8);

            try {
                Files.move(
                        stage, published,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException ex) {
                System.out.println("atomic=UNAVAILABLE");
                return;
            }

            System.out.println("atomic=SUPPORTED");
            System.out.println(
                    "published-content="
                    + Files.readString(
                        published, StandardCharsets.UTF_8)
                        .contains("7,2"));
        } finally {
            Files.deleteIfExists(stage);
            Files.deleteIfExists(published);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AtomicPublicationDemo.java
java AtomicPublicationDemo
```

**stdout nếu provider hỗ trợ atomic move trong cùng directory:**

```text
atomic=SUPPORTED
published-content=true
```

**stdout nếu không hỗ trợ atomic move:**

```text
atomic=UNAVAILABLE
```

Trong ví dụ, `published` là **một pathname mới trong directory tạm riêng**, không cố thay file người dùng đang tồn tại. Nếu target đã tồn tại trong sản phẩm thật, phải quyết định chính sách conflict/versioning riêng; không suy provider luôn từ chối hoặc luôn cho overwrite trong chế độ atomic move.

Nếu atomic move không hỗ trợ, ví dụ **không tự âm thầm hạ cấp** sang non-atomic move. Trong hệ thống coi publication atomic là điều kiện bắt buộc, đây là FAIL/capability error. Nếu sản phẩm cho phép fallback, phải định nghĩa cơ chế marker/manifest, verify và khả năng consumer nhìn thấy file giữa lúc publish.

**WatchService vẫn cần lọc `.part`:** watcher thường nhận event của cả file staging vì nó nằm trong directory được đăng ký. Consumer chỉ enqueue tên có dạng chính thức (`orders-*.csv`) và bỏ qua suffix tạm; việc lọc file name phải thực hiện theo chính sách ứng dụng, không tin mọi rename được báo bằng chính xác một `ENTRY_CREATE` trên mọi provider.

## 10. Giao thức thay thế: marker .ready

Với filesystem hoặc pipeline không thể bảo đảm một rename atomic phù hợp, producer và consumer có thể thỏa thuận:

1. Producer ghi tệp dữ liệu vào pathname do nó sở hữu.
2. Producer đóng file, verify dữ liệu và **không sửa file nữa**.
3. **Sau cùng**, producer tạo file marker `orders.csv.ready` hoặc manifest có checksum/length.
4. Consumer coi marker là trigger để mở **tệp dữ liệu liên quan**.
5. Consumer sau ingest có thể rename/archive marker hoặc ghi trạng thái đã xử lý.

**Quan trọng:** marker chỉ đáng tin khi **producer tuân thủ hợp đồng**. Một actor khác có thể tạo marker giả, producer có thể crash trước/sau marker, consumer có thể mất marker event, và tạo marker không tự làm tệp dữ liệu đã durable sau mất điện.

### 10.1. Ví dụ runnable: marker chỉ xuất hiện sau khi ghi xong

Tạo `ReadyMarkerProtocolDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadyMarkerProtocolDemo {
    static boolean ready(
            Path data, Path marker) {
        return Files.isRegularFile(data)
                && Files.isRegularFile(marker);
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("ready-");
        Path data = dir.resolve("orders.csv");
        Path marker = dir.resolve("orders.csv.ready");

        try {
            System.out.println(
                    "before=" + ready(data, marker));

            Files.writeString(
                    data,
                    "id,qty\n7,2\n",
                    StandardCharsets.UTF_8);

            Files.createFile(marker);
            System.out.println(
                    "after=" + ready(data, marker));
            System.out.println(
                    "payload-correct="
                    + Files.readString(
                        data, StandardCharsets.UTF_8)
                        .contains("7,2"));
        } finally {
            Files.deleteIfExists(marker);
            Files.deleteIfExists(data);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ReadyMarkerProtocolDemo.java
java ReadyMarkerProtocolDemo
```

```text
before=false
after=true
payload-correct=true
```

`Files.writeString` trả về sau khi operation ghi/đóng stream nội bộ hoàn tất; ở đây producer chỉ tạo marker **sau** bước ghi. `ready` trong demo chỉ kiểm tra sự tồn tại của hai files: production nên có id/schema/checksum/expected length trong manifest, chính sách bảo vệ marker và kiểm tra phiên bản.

**Không dùng marker theo tên file cố định mà không có version/job ID** trong hệ thống nhiều writer: một marker cũ có thể bị nhầm với file phiên bản mới. Có thể dùng tên chứa opaque job id và atomic state transition theo thiết kế ứng dụng.

## 11. Nếu chỉ kiểm soát consumer: kiểm tra readiness theo tầng

Khi editor hoặc ứng dụng bên thứ ba ghi file theo cách không kiểm soát, có thể dùng quy trình best-effort:

```text
Watch event
  -> coalesce(Path)
  -> debounce(quiet window)
  -> kiểm tra entry/file type và quyền theo policy
  -> lấy fingerprint (size, mtime, fileKey nếu có)
  -> sau khoảng nhỏ lấy fingerprint lần 2
  -> nếu khác: lùi lịch lại
  -> nếu giống: mở/đọc/parse, kiểm tra schema/checksum phù hợp
  -> xác nhận lại fingerprint/version nếu cần
  -> ghi kết quả idempotent hoặc retry có giới hạn
```

**Giới hạn từng tầng:**

| Tầng | Giúp gì? | Không chứng minh được gì? |
| --- | --- | --- |
| Watch event | Có thay đổi được quan sát | Không chứng minh file đã đóng |
| Debounce | Đợi burst ngừng một khoảng | Không phát hiện khoảng nghỉ dài giữa các lần ghi |
| 2 lần size/mtime | Phát hiện một số thay đổi trực tiếp | Không phát hiện mọi rewrite same-size/same-mtime |
| `fileKey` | Phát hiện một số file replacements | Có thể null/khác provider |
| Parser/schema | Phát hiện format chưa đầy đủ/sai | Không ngăn producer sửa tiếp |
| Checksum do producer phát sau khi hoàn tất | Xác minh byte theo manifest | Không tự bảo vệ nếu manifest giả/đã cũ |
| Producer publish protocol | Tín hiệu hoàn tất có ý nghĩa nghiệp vụ | Không loại bỏ mọi OS crash, race hoặc lỗi consumer |

Nếu một candidate chưa hợp lệ, không nên báo “đã ingest” rồi hy vọng WatchService sẽ tự gửi event tiếp; việc ghi có thể đã dừng và không có event mới. Cần **retry có backoff** hoặc reconciliation định kỳ.

### 11.1. Phân loại lỗi đọc file

- `NoSuchFileException`: file bị delete/move hoặc path chưa hiện ra ở thời điểm I/O; thường hủy/reconcile thay vì retry mù quáng vô hạn.
- `AccessDeniedException`: có thể do permission/chính sách, không mặc nhiên kết luận file vẫn đang được ghi.
- `FileSystemException`: OS/provider-specific; có thể lock, sharing violation, mount error.
- Parser báo file chưa đủ: có thể retry trong giới hạn nếu hợp đồng cho phép nội dung xuất hiện muộn.
- Parser báo dữ liệu sai vĩnh viễn: dead-letter/quarantine hoặc trả lỗi rõ thay vì retry mãi.
- `IOException` khác: phân loại, lưu cause/metrics và retry có kiểm soát nếu là lỗi transient.

**Không dùng mỗi `Files.isReadable`/`Files.isWritable` làm tín hiệu “writer đã close”.** Hai phép thử này không nói có process khác còn mở file hay không; kết quả chỉ là quan sát quyền ở thời điểm gọi.

**Không dùng `FileLock` như cách phổ quát để hỏi “file đã ghi xong chưa”.** Lock có thể advisory, một writer có thể không dùng lock, locking behavior khác giữa OS/providers. Chỉ dùng locking khi **cả hai bên tuân thủ giao thức** và đã thử đúng filesystem.

## 12. Gộp duplicate cả sau khi file “ready”: xử lý idempotent

Một file đã hoàn chỉnh vẫn có thể sinh thêm event:

- Provider phát nhiều event cho metadata.
- Một lần ghi/chuyển tên có thể được phản ánh bằng create + modify.
- Ứng dụng restart quét startup và nhận lại event cùng path.
- Worker retry sau khi mạng hoặc database time out.
- Bên ghi publish file mới cùng tên sau khi file cũ xử lý xong.

Chỉ dùng `Set<Path> processed` là chưa đủ: một pathname như `orders.csv` có thể được **tái sử dụng cho phiên bản khác**. Cần định nghĩa **idempotency key** theo nghiệp vụ, ví dụ:

- Unique upload ID do producer cấp.
- Tenant ID + document ID + revision/version.
- Digest nội dung (ví dụ SHA-256) khi data model cho phép “nội dung giống nhau = đã xử lý”.
- Đường dẫn + source identifier + revision metadata được xác thực.
- Message ID được lưu trong file/manifest.

Nếu dùng checksum, nhớ digest chỉ xác minh byte được đọc **tại thời điểm đó**; nó không tự khóa file, không xác thực người gửi và không bảo đảm không có write race. Với file rất lớn, đọc bằng stream để tính digest và giới hạn tài nguyên.

### 12.1. Ví dụ runnable: ghi nhớ phiên bản bằng SHA-256

Tạo `ContentIdempotenceDemo.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;

public class ContentIdempotenceDemo {
    static String sha256(Path file)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest hash =
                MessageDigest.getInstance("SHA-256");

        try (InputStream in = Files.newInputStream(file)) {
            byte[] buffer = new byte[4096];
            int n;
            while ((n = in.read(buffer)) != -1) {
                hash.update(buffer, 0, n);
            }
        }
        return HexFormat.of().formatHex(hash.digest());
    }

    static boolean changed(
            Map<Path, String> processed,
            Path file)
            throws IOException, NoSuchAlgorithmException {
        String digest = sha256(file);
        String previous = processed.put(file, digest);
        return !digest.equals(previous);
    }

    public static void main(String[] args)
            throws IOException, NoSuchAlgorithmException {
        Path dir = Files.createTempDirectory("digest-");
        Path file = dir.resolve("record.txt");

        try {
            Map<Path, String> processed = new HashMap<>();

            Files.writeString(
                    file, "V1", StandardCharsets.UTF_8);

            System.out.println(
                    "first=" + changed(processed, file));
            System.out.println(
                    "duplicate=" + changed(processed, file));

            Files.writeString(
                    file, "V2", StandardCharsets.UTF_8);
            System.out.println(
                    "new-revision="
                    + changed(processed, file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ContentIdempotenceDemo.java
java ContentIdempotenceDemo
```

```text
first=true
duplicate=false
new-revision=true
```

**Cảnh báo thiết kế production:** method `changed` ở ví dụ này ghi nhớ digest **trước** khi có “commit nghiệp vụ”. Nếu downstream thất bại sau đó, một retry có thể bị coi là duplicate và mất dữ liệu. Thực tế cần ghi checkpoint/version **sau khi transaction thành công**, hoặc dùng một unique constraint và transaction/idempotency table của nơi nhận.

Một producer có thể sửa file trong lúc bạn hash. Với pipeline quan trọng, hãy dùng publication protocol, snapshot/immutable input hoặc cơ chế version identity thích hợp; không dùng checksum như bảo đảm file không thay đổi trong tương lai.

## 13. OVERFLOW: không thể chỉ debounce các event đã nhận

`StandardWatchEventKinds.OVERFLOW` là tín hiệu rằng watcher **có thể đã đánh mất sự kiện** do giới hạn hàng đợi/provider. Consumer không thể khôi phục danh sách chính xác những sự kiện đã mất từ `count()`.

Cần làm:

1. Đánh dấu directory/key tương ứng là **cần reconcile**.
2. Nhanh chóng `pollEvents()` các event hiện có rồi `reset()` key (nếu hợp lệ).
3. Đặt lịch quét **trạng thái thật hiện tại của directory**, không cố suy ra tên những file đã mất.
4. So sánh snapshot/index đã xử lý với trạng thái hiện tại và enqueue các ứng viên mới hoặc thay đổi.
5. Xử lý mối quan hệ file rename/delete/recreation theo policy.
6. Có kế hoạch **startup scan** khi watcher mới đăng ký, vì sự kiện trong lúc ứng dụng tắt không được WatchService giữ lịch sử.
7. Đặt reconciliation định kỳ nếu môi trường có nguy cơ bỏ sót remote events.

### 13.1. Ví dụ runnable: reconcile danh sách file khi mất sự kiện

Tạo `OverflowReconcileDemo.java`:

```java
import java.nio.file.Path;
import java.util.Set;
import java.util.TreeSet;

public class OverflowReconcileDemo {
    static Set<String> names(Set<Path> entries) {
        Set<String> result = new TreeSet<>();
        for (Path p : entries) {
            result.add(p.getFileName().toString());
        }
        return result;
    }

    public static void main(String[] args) {
        Set<Path> previous = Set.of(
                Path.of("a.txt"), Path.of("old.txt"));
        Set<Path> actual = Set.of(
                Path.of("a.txt"), Path.of("b.txt"));

        Set<String> added = names(actual);
        added.removeAll(names(previous));

        Set<String> deleted = names(previous);
        deleted.removeAll(names(actual));

        Set<String> unchanged = names(previous);
        unchanged.retainAll(names(actual));

        System.out.println("new=" + added);
        System.out.println("missing=" + deleted);
        System.out.println("same-name=" + unchanged);
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all OverflowReconcileDemo.java
java OverflowReconcileDemo
```

```text
new=[b.txt]
missing=[old.txt]
same-name=[a.txt]
```

Đây là **ví dụ về phép so sánh hai sets**, chưa phải chương trình quét thư mục thật. Nếu `a.txt` bị thay nội dung nhưng vẫn giữ cùng tên, phép so tên **không phát hiện version change**. Reconciliation production phải lưu thông tin identity/version/digest phù hợp (phần 12), đọc attributes có xử lý lỗi và không khẳng định một scan directory là snapshot nhất quán khi đang có writer.

### 13.2. OVERFLOW không phải lỗi có thể “bỏ qua”

Nếu bạn drop `OVERFLOW` rồi chỉ đợi event mới, một file đã bị bỏ lỡ có thể **không bao giờ được xử lý**. Một hệ thống cần độ tin cậy cao phải có cơ chế reconcile thay vì coi WatchService là nguồn dữ liệu duy nhất.

**`OVERFLOW` không cần đăng ký tường minh** cùng các kinds khác; nó là event đặc biệt được WatchService cung cấp khi cần. Context của nó có thể null, vì vậy không cast sang `Path` trước khi kiểm tra kind.

## 14. Mẫu WatchService thực tế: polling có giới hạn và reset WatchKey

Các thao tác tiêu chuẩn:

```java
try (WatchService watcher =
        root.getFileSystem().newWatchService()) {

    WatchKey registration = root.register(
            watcher,
            ENTRY_CREATE,
            ENTRY_MODIFY,
            ENTRY_DELETE);

    while (!Thread.currentThread().isInterrupted()) {
        WatchKey key = watcher.poll(
                200, TimeUnit.MILLISECONDS);

        if (key == null) {
            // Có thể kiểm tra jobs đã qua quiet window.
            continue;
        }

        for (WatchEvent<?> event : key.pollEvents()) {
            if (event.kind() == OVERFLOW) {
                // Trigger reconciliation.
                continue;
            }
            if (event.context() instanceof Path relative) {
                Path changed = root.resolve(relative);
                // Enqueue coalesced candidate.
            }
        }

        if (!key.reset()) {
            // Directory không còn watch hợp lệ.
            break;
        }
    }
}
```

Đây là **snippet**, cần imports các static event kinds, `WatchService`, `WatchKey`, `WatchEvent`, `Path`, `TimeUnit` và xử lý `IOException`/`InterruptedException`. Nó không cung cấp scheduler thật, chỉ chỉ ra ranh giới rõ ràng giữa event loop và xử lý công việc.

**`WatchKey.reset()` rất quan trọng:** sau khi đã `pollEvents()` và xử lý nhanh batch, reset key để WatchService có thể báo các thay đổi tiếp theo theo state machine của API. Nếu `reset()` trả `false`, key không còn hợp lệ: thư mục có thể đã bị xóa hoặc registration bị hủy. Đừng tiếp tục chờ key đó như thể vẫn active; cần re-register/alert theo mục tiêu service.

Nếu nhiều directory cùng được đăng ký, `key.watchable()` giúp lấy watchable hoặc giữ `Map<WatchKey,Path>`. Không dùng một biến `root` duy nhất cho tất cả event khi key thuộc các directory khác nhau.

### 14.1. Ví dụ runnable: WatchService thật nhưng không hard-code số event

Tạo `WatchServicePollingDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.concurrent.TimeUnit;
import static java.nio.file.StandardWatchEventKinds.*;

public class WatchServicePollingDemo {
    public static void main(String[] args)
            throws IOException, InterruptedException {
        Path dir = Files.createTempDirectory("watch-poll-");
        Path file = dir.resolve("data.txt");

        try {
            try (WatchService watcher =
                    FileSystems.getDefault()
                        .newWatchService()) {
                WatchKey registered = dir.register(
                        watcher,
                        ENTRY_CREATE,
                        ENTRY_MODIFY,
                        ENTRY_DELETE);

                Files.writeString(
                        file, "ready", StandardCharsets.UTF_8);

                WatchKey key = watcher.poll(
                        500, TimeUnit.MILLISECONDS);

                if (key != null) {
                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind() == OVERFLOW) {
                            // Reconcile would be scheduled here.
                            continue;
                        }
                        if (event.context() instanceof Path relative) {
                            Path changed =
                                    dir.resolve(relative).normalize();
                            if (!changed.startsWith(dir)) {
                                throw new IOException("Invalid context");
                            }
                            // Enqueue changed path (not parse here).
                        }
                    }

                    if (!key.reset()) {
                        throw new IOException("Watch key invalid");
                    }
                }

                System.out.println(
                        "registered=" + registered.isValid());
                System.out.println("poll-completed=true");
            }
        } catch (UnsupportedOperationException ex) {
            System.out.println("watch=UNAVAILABLE");
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all WatchServicePollingDemo.java
java WatchServicePollingDemo
```

**stdout khi WatchService/default provider đăng ký được:**

```text
registered=true
poll-completed=true
```

**stdout khi provider không hỗ trợ WatchService:**

```text
watch=UNAVAILABLE
```

**Lưu ý:** ví dụ **không** in số event vì số lượng và thời gian phát event **không được bảo đảm giống nhau** trên Windows/Linux/macOS hoặc remote storage. Một lần poll hết hạn với `key == null` **không có nghĩa file không được tạo**; nó chỉ có nghĩa lúc poll không có key sẵn sàng. Ví dụ cố ý giữ output cố định cho cả trường hợp có và không có event trong giới hạn 500 ms.

Khi cần một watcher chạy lâu, dùng cancellation/interrupt/close policy, thiết kế shutdown an toàn và định nghĩa deadline. `WatchService.close()` giúp giải phóng tài nguyên; `take()` có thể block, còn `poll(timeout)` giúp vòng loop có cơ hội xử lý công việc định kỳ.

## 15. Sắp xếp đúng thứ tự khi phối hợp WatchService với scheduler

Với service sử dụng cả watcher thread và worker executor:

1. **Ngay khi có key**, đọc hết `pollEvents()` của key. Mỗi event chỉ cập nhật state và enqueue nhẹ.
2. Nếu `OVERFLOW`, set flag reconcile cho **registered directory tương ứng**. Không bỏ qua để lấy event tiếp.
3. Với `ENTRY_DELETE`, xóa candidate đang chờ hoặc tạo tombstone event. Nếu task cũ đã bắt đầu, cần generation/transaction để tránh commit stale.
4. Với `ENTRY_CREATE`/`MODIFY`, update `lastEventNanos` và `generation` của candidate tương ứng.
5. **Reset key** nhanh. Nếu false, xử lý registration invalid.
6. Scheduler kiểm tra quiet window bằng monotonic time, thực hiện readiness check theo policy.
7. Worker chỉ xử lý file khi có **publication protocol** hoặc các điều kiện best-effort được thỏa. Nếu thấy file đổi trong lúc xử lý, discard/retry theo version.
8. Sink ghi kết quả trong transaction/idempotency mechanism phù hợp.
9. Dọn state đã xử lý, nhưng giữ thông tin đủ để nhận ra revision mới.
10. Định kỳ reconcile và kiểm soát backlog/metrics.

**Tránh lock quá rộng:** nếu giữ synchronized lock trên pending map trong lúc parse file lớn hoặc gọi database, watcher thread có thể bị block lâu. Tách cập nhật state ngắn khỏi I/O dài và dùng các cấu trúc concurrent phù hợp.

**Hạn chế thứ tự:** event queue không phải total order xuyên nhiều file/directory. Một rename có thể phát ra create/delete tùy provider; ứng dụng không nên suy ra transaction ordering tuyệt đối giữa hai watch keys.

## 16. Retry policy, backoff và dead-letter

Một scheduler tử tế nên có các trạng thái rõ:

| State | Ý nghĩa | Hành động |
| --- | --- | --- |
| `PENDING` | Vừa nhận event hoặc còn quá gần event mới | Chờ quiet window |
| `PROBING` | Kiểm tra attributes/readiness | So mẫu tiếp theo/validate |
| `RETRYABLE` | Chưa ready hoặc gặp lỗi transient có giới hạn | Retry với backoff và deadline |
| `PROCESSING` | Worker đang ingest phiên bản cụ thể | Guard generation/version |
| `COMPLETED` | Downstream commit thành công | Ghi checkpoint idempotent |
| `DELETED` | Entry đã biến mất theo policy | Hủy/ghi tombstone |
| `FAILED`/`QUARANTINED` | Lỗi dài hạn/invalid data | Ghi nguyên nhân, dead-letter |
| `RECONCILE_REQUIRED` | WatchService overflow/restart/lost events | Quét filesystem và so state |

**Một chiến lược retry có giới hạn**:

- Quiet window khởi đầu ví dụ 200–1000 ms **chỉ là giá trị cấu hình**, không phải chuẩn.
- Retry khi probe thay đổi hoặc parser báo dữ liệu chưa hoàn chỉnh; tăng backoff có giới hạn.
- Đặt max attempts hoặc deadline theo SLA file size thực tế.
- Với bất kỳ event mới nào, **làm mới generation và quiet timer**; không để retry cũ commit sai phiên bản.
- Ghi metrics: queue size, pending age, duplicated events, parse retry, overflow, rescan duration, failed attempts, latency to ingest.
- Khi retry hết hạn, **đưa vào trạng thái lỗi rõ ràng** để người vận hành/producer khắc phục; không retry vô hạn và chiếm CPU/threads.

**Không lạm dụng `Thread.sleep` trong watcher loop** để chờ file “xong”: nó chặn việc nhận key và có thể làm backlog tăng. Scheduler/worker có thể dùng delayed executor, nhưng watcher loop nên trả về polling nhanh.

### 16.1. Các lỗi phải phân biệt

| Lỗi | Có thể là | Chính sách |
| --- | --- | --- |
| `NoSuchFileException` | Delete/move giữa event và read | Hủy candidate/reconcile, không giả định forever absent |
| `AccessDeniedException` | ACL/quyền của OS | Báo lỗi/quan sát transient nếu môi trường cho phép |
| `FileSystemException` | Lock, mount, provider condition | Xem cause/reason, retry có giới hạn nếu phù hợp |
| `ClosedWatchServiceException` | Watcher đã đóng | Dừng event loop/chuyển shutdown |
| `InterruptedException` | Thread bị interrupt khi poll/take | Hoàn tất shutdown và phục hồi interrupt status ở boundary phù hợp |
| `OVERFLOW` | Có thể mất events | Trigger reconciliation |
| `WatchKey.reset() == false` | Registration không còn valid | Register lại nếu được hoặc báo trạng thái |
| Parser/validation failure | File chưa đầy đủ hoặc file thật sự hỏng | Có version/deadline rồi retry/quarantine |
| Duplicate downstream record | Một file/version được xử lý >1 lần | Idempotency transaction/unique key |

## 17. Security: file mới xuất hiện không mặc nhiên đáng tin

Một event `ENTRY_CREATE` cho biết một entry được quan sát tại pathname tương đối của directory đã đăng ký. Nó **không xác thực người tạo** và **không chứng minh nội dung an toàn**.

Các nguy cơ:

- **Symlink:** entry có thể trỏ ngoài thư mục ingest; `Files.isRegularFile(path)` mặc định follow symlink.
- **TOCTOU:** file có thể bị thay thế sau khi `isRegularFile`/`size` và trước khi mở.
- **Path traversal:** ghép context sai/root kiểm tra bằng `String.startsWith` có thể mở rộng ngoài vùng tin cậy.
- **Directory đổi thành symlink:** kiểm tra `NOFOLLOW_LINKS` cho final entry không chứng minh các ancestor cũng an toàn.
- **File size/quota:** một file rất lớn hoặc ZIP bomb có thể làm quá tải RAM/disk/CPU.
- **Malformed input:** CSV formula injection, JSON/ZIP parser issues, untrusted binary payload và schema sai.
- **Wrong tenant:** source có thể thuộc một tenant khác dù path hợp lệ; cần authorization theo domain.
- **Race cùng tên:** file bị xóa/tạo lại cùng tên trong khi pending state cũ vẫn giữ version; cần identity/version protocol.

**Phòng vệ nhiều lớp:** hạn chế process permissions, chỉ nhận file trong root do server quản lý, từ chối symlink nếu domain không cần, validate tên/size/type/schema, giới hạn resource, idempotent sink và audit có chọn lọc. Với yêu cầu TOCTOU khắt khe, cân nhắc `SecureDirectoryStream` nếu provider hỗ trợ và thiết kế thao tác qua directory handle, không chỉ lexical path.

## 18. Những anti-pattern dễ làm production hỏng dữ liệu

| Anti-pattern | Tại sao sai | Thiết kế phù hợp hơn |
| --- | --- | --- |
| `ENTRY_CREATE` → parse ngay | File có thể mới được tạo, chưa có dữ liệu | Publish protocol hoặc debounce + validate |
| `ENTRY_MODIFY` → parse ngay | Writer có thể vẫn đang ghi | Quiet window và readiness policy |
| `count()` chính là số lần ingest | Count là số event quan sát/gộp, không phải jobs | Một pending job/path/version |
| Dùng throttle leading-edge để tránh đọc dở | Có thể chạy ở đầu burst | Debounce trailing-edge hoặc producer signal |
| Chờ 500 ms rồi tuyên bố file đã close | Writer có thể tạm nghỉ lâu hơn | Giao thức công bố, parser/checksum |
| Hai lần size bằng nhau nghĩa file hoàn chỉnh | Có thể rewrite same size hoặc pause | Dùng thêm metadata/validation nhưng hiểu giới hạn |
| `Files.isReadable` chứng minh writer đã release lock | Access check không nói về trạng thái writer | Hợp đồng producer hoặc retry khi I/O fail |
| Dùng `FileLock` như “check closed” phổ quát | Advisory/provider-dependent | Chỉ dùng khi cả hai bên tuân thủ lock protocol |
| Parse file trong watcher thread | Event queue có thể overflow | Tách queue + worker |
| Quên `key.reset()` | Registration không tiếp tục theo hợp đồng | Poll events rồi reset |
| Không xử lý `OVERFLOW` | Có thể mất file mãi mãi | Rescan/reconcile |
| Cast event.context() trước khi xem kind | OVERFLOW context có thể null | Kiểm tra `OVERFLOW` trước |
| Gộp theo mỗi tên `report.csv` | Nhiều directory có tên trùng | Dùng registered root + relative context |
| Bỏ event DELETE nhưng không invalidate job | Worker cũ có thể đọc file bị thay thế | Generation/tombstone/version |
| `cancel(false)` chắc chắn ngăn task cũ commit | Task có thể đã chạy | Generation và transaction/version check |
| Check metadata một lần rồi commit vài phút sau | File có thể thay đổi | Quản lý phiên bản/snapshot trước commit |
| Ghi digest vào processed map trước khi downstream thành công | Lỗi downstream gây mất retry | Commit checkpoint cùng transaction hoặc sau success |
| Chỉ dùng Set<Path> cho idempotency vĩnh viễn | File mới cùng tên sẽ bị bỏ lỡ | Version/job ID/hash đúng domain |
| Rely trên event khi service tắt | WatchService không lưu history mọi lúc | Startup scan/reconcile |
| Rely trên watcher remote FS tuyệt đối | Provider có thể bỏ sót remote changes | Quét định kỳ/producer message |
| Thêm `ATOMIC_MOVE` rồi nghĩ overwrite portable | Target-exists semantics phụ thuộc provider | Unique names hoặc policy kiểm chứng provider |
| Nuốt `AtomicMoveNotSupportedException` rồi tự non-atomic publish bí mật | Consumer có thể thấy file chưa hoàn chỉnh | Fail closed hoặc marker/fallback có contract |
| Không giới hạn pending map | Memory tăng vô hạn khi burst | Bounded queue, backpressure, metrics |
| Retry vô hạn malformed file | CPU/I/O tốn, dữ liệu không tự sửa | Deadline/quarantine |
| Dùng lexical normalize như sandbox tuyệt đối | Symlink/TOCTOU còn tồn tại | Root/permission/handle-relative policy |

## 19. Kiểm thử đáng tin trên nhiều hệ điều hành

Không nên viết một unit test đòi hỏi **chính xác hai `ENTRY_MODIFY`** cho một lần `Files.writeString`. Số lượng/timing là implementation-dependent.

**Phân tầng test:**

1. **Pure unit tests** cho coalescing logic, debounce, ticket version và reconciliation, dùng event giả/dồng hồ giả: `WatchEventCoalescingDemo`, `DebounceByPathDemo`, `WatchGenerationTicketDemo` và `OverflowReconcileDemo`.
2. **Filesystem tests** với temp directory, tạo file thật, đọc metadata/format, marker và digest: `MetadataStabilityDemo`, `FramedPayloadDemo`, `ReadyMarkerProtocolDemo`, `ContentIdempotenceDemo`.
3. **Provider integration tests** cho `WatchService` và `ATOMIC_MOVE` trên file store thật: `WatchServicePollingDemo`, `AtomicPublicationDemo`. Chấp nhận outcome được API cho phép, không hard-code event count hoặc giả định mọi file store atomic.
4. **End-to-end tests** có producer ghi nhiều chunk, consumer nhận event, xác minh **chỉ commit sau publish marker** và không ingest duplicate revisions. Test này cần giả lập hoặc kiểm soát producer/sink thay vì phụ thuộc cơ may event timing.
5. **Failure injection**: overflow, watch key invalid, shutdown giữa xử lý, file delete/recreate, parser error, disk full/quota, network storage disconnection, concurrent writer, backlog và retry deadline.

### 19.1. Chú ý khi test độ ổn định

Thay vì `Thread.sleep(50)` rồi hy vọng event đến, dùng **fake monotonic clock** cho logic debounce và capture event thật trong một integration test có deadline/timeout hợp lý. Tuy nhiên event arrival time vẫn phụ thuộc provider; test nên đánh giá behavior quan trọng, không ép một mẫu event count cố định.

Nếu service phải xử lý NFS/SMB/cloud mount, chạy integration tests trên chính mount đó. Một test WatchService PASS trên local NTFS/ext4 không chứng minh remote changes luôn được phát hiện.

### 19.2. Kiểm thử trạng thái quan trọng nhất

- Nhiều modify của cùng path → **1 pending candidate**.
- Modify của hai path khác nhau → **2 candidates**.
- Delete xảy ra sau create/modify → candidate cũ bị hủy hoặc tombstone.
- Event mới đến trong quiet window → deadline dời lại.
- Job cũ chạy sau generation mới → không được commit stale state.
- Metadata thay đổi giữa hai probes → chưa ready.
- Size/mtime không đổi nhưng parser incomplete → chưa được ingest.
- Marker tạo sau khi data close → ingest một phiên bản.
- Duplicate watcher event sau commit → không tạo duplicate downstream record.
- Một pathname được tái sử dụng cho revision mới → không bỏ sót revision.
- `OVERFLOW` → trigger rescan; scan phát hiện file bị missed.
- Watcher restart sau downtime → scan lại directory.
- Invalid WatchKey hoặc ClosedWatchService → shutdown/re-register theo policy.
- Symlink/path/permission invalid → không mở ngoài root.
- Atomic move không hỗ trợ → không giả mạo atomic publish.
- File store remote/nơi event không đầy đủ → reconciliation định kỳ.

## 20. Checklist review một pipeline WatchService

1. `ENTRY_CREATE`/`ENTRY_MODIFY` có được xem như **tín hiệu thay đổi**, không phải đóng file không?
2. Đã hiểu `WatchEvent.count()` và việc event lặp được gộp ở tầng provider/JDK chưa?
3. Đã gộp **application-level** theo pathname + registered directory hoặc logical ID chưa?
4. Có xử lý `ENTRY_DELETE` để hủy pending và làm mới generation không?
5. Có xử lý `OVERFLOW` để reconcile directory chứ không chỉ log rồi bỏ qua không?
6. Có call `key.reset()` sau khi xử lý batch nhanh không?
7. Nếu `reset() == false`, có handling key invalid/re-registration không?
8. Có giữ watcher thread nhẹ, tránh parse/file I/O chậm trong loop không?
9. Debounce có trailing-edge, quiet window theo cấu hình và monotonic clock không?
10. Có hiểu debounce/mtime/size **không chứng minh writer đã close** không?
11. Có thể thiết kế producer dùng temp file + atomic rename hoặc marker/manifest không?
12. Nếu dùng `ATOMIC_MOVE`, có kiểm tra support và chính sách target đã tồn tại không?
13. Có phân biệt atomic visibility với durability/transaction/exactly-once không?
14. Có kiểm tra file type, schema/size/hash và security boundary trước ingest không?
15. Có retry có giới hạn/backoff và dead-letter/quarantine cho file không hợp lệ không?
16. Có idempotency key theo revision/tenant/job ID thay vì chỉ path không?
17. Checkpoint có được commit sau khi sink thành công hoặc cùng transaction không?
18. Có ngăn task cũ commit sau event mới qua generation/version ở sink không?
19. Có startup scan và reconcile định kỳ cho remote FS/khả năng miss events không?
20. Có tránh hard-code số event/timing cho các platform tests không?
21. Có giới hạn pending map/queue, số worker, độ dài file và thời gian xử lý không?
22. Có teardown watcher/executor đúng khi shutdown, cancel hoặc interrupt không?
23. Có tách metric `rawEventCount` khỏi `uniqueFilesPending` và `completedJobs` không?
24. Có handle lỗi `IOException`, `ClosedWatchServiceException` và parser errors rõ không?
25. Có ghi nhận stalled jobs và thời điểm file-ready đủ để điều tra sự cố không?

## 21. Bài tập

**Bài 1 — Count vs duplicate.** Chạy `WatchEventCoalescingDemo`. Thêm ba `ENTRY_MODIFY` cho `a.txt` có `count=1`. Tại sao `pending` vẫn chỉ có một file? Vì sao `modifyObservations` khác số job?

**Bài 2 — Debounce.** Chạy `DebounceByPathDemo`. Đổi quiet window từ 100 lên 200 ms. Dự đoán danh sách đến hạn ở `t=150`, `t=200`, `t=300`. Giải thích vì sao dùng throttle leading-edge có thể đọc file chưa xong.

**Bài 3 — Generation.** Chạy `WatchGenerationTicketDemo`. Thêm trường hợp file bị delete rồi tạo lại cùng tên. Vì sao chỉ dùng generation trong bộ nhớ và `Set<Path>` vẫn có race nếu commit downstream không được đồng bộ?

**Bài 4 — Metadata stability.** Chạy `MetadataStabilityDemo`, sửa hai phiên bản file cùng kích thước rồi làm giả mtime giống nhau. Phân tích vì sao fingerprint có thể tạo false ready. Dùng kiểm tra format hoặc version do producer cấp để cải thiện.

**Bài 5 — Validation.** Chạy `FramedPayloadDemo`. Thiết kế manifest chứa expected length và hash SHA-256; chỉ accept file khi producer đã phát manifest sau khi đóng file.

**Bài 6 — Atomic publish.** Chạy `AtomicPublicationDemo` trên file store khác. Nếu `ATOMIC_MOVE` không hỗ trợ, thiết kế fallback có marker và ghi rõ consumer không bao giờ parse một file staging.

**Bài 7 — Marker.** Chạy `ReadyMarkerProtocolDemo`; đổi marker thành `job-id.ready` và kèm target filename/hash. Vì sao marker cũ hoặc marker bị giả mạo có thể gây duplicate ingestion?

**Bài 8 — Content idempotency.** Chạy `ContentIdempotenceDemo`. Tạo một downstream sink giả lập thất bại ở lần đầu. Sửa code để chỉ ghi checkpoint sau khi xử lý thành công.

**Bài 9 — OVERFLOW.** Chạy `OverflowReconcileDemo`. Thử thay nội dung `a.txt` nhưng giữ cùng tên; cập nhật thuật toán để dùng revision/hash thay vì chỉ set names.

**Bài 10 — Integration WatchService.** Chạy `WatchServicePollingDemo`, rồi thay bằng một loop có timeout và event queue. Không assert số modify events; chỉ assert dữ liệu cuối cùng được xử lý đúng once theo idempotency key sau khi producer publish.

**Bài 11 — File lớn.** Thiết kế consumer nhận file vài GiB. Không đọc toàn bộ vào RAM; dùng streaming parser/digest, bounded worker pool và kiểm soát shutdown.

**Bài 12 — Concurrency.** Mô phỏng event mới đến sau khi worker đã check generation nhưng trước commit DB. Đề xuất optimistic concurrency/version check hoặc unique constraint tại transaction boundary.

**Bài 13 — Recovery.** Tắt watcher trong lúc producer tạo file, bật lại và chạy startup reconciliation. Giải thích vì sao tin vào `ENTRY_CREATE` đơn thuần sẽ bỏ lỡ file.

**Bài 14 — Security.** Tạo symlink bên trong watched directory trỏ ngoài root, kiểm tra khác biệt giữa `Files.isRegularFile(path)` và `Files.isRegularFile(path,NOFOLLOW_LINKS)`. Đề xuất cách giảm TOCTOU.

**Bài 15 — Metrics và SLA.** Chọn quiet interval/retry deadline phù hợp với loại file và producer cụ thể, đo số `OVERFLOW`, queue age và duplicate rate; chỉ điều chỉnh cấu hình từ số đo, không áp một ngưỡng ms cố định cho mọi môi trường.

## 22. Tổng kết

- **`WatchService` báo thay đổi, không báo “file write complete”**. `ENTRY_MODIFY` có thể lặp và `count() > 1`; con số đó không phải số file/job.
- **Coalescing** gom nhiều sự kiện về **một pending candidate theo pathname/version**, còn **debounce** chờ khoảng yên lặng sau event cuối cùng. Chúng xử lý duplicate nhưng **không tự chứng minh readiness**.
- **`ENTRY_DELETE`** phải hủy/invalidate pending; **`OVERFLOW`** phải trigger reconciliation; `WatchKey.reset()` cần thực hiện sau batch.
- **Size/mtime/fileKey ổn định** là heuristic; file có thể tạm ngừng ghi hoặc bị thay thế. Parser, checksum, deadline và idempotency giúp tăng độ tin cậy nhưng không thay thế producer protocol.
- **Nếu kiểm soát producer, ưu tiên ghi tạm và công bố sau khi đóng** bằng `ATOMIC_MOVE` khi provider hỗ trợ, hoặc marker/manifest có hợp đồng rõ. Atomic rename không tự bảo đảm disk durability hay exactly-once processing.
- **Nếu không kiểm soát producer**, dùng debounce + nhiều samples + validation + retry/backoff và báo trạng thái lỗi đúng; không hứa loại bỏ mọi race.
- **Idempotency phải ở tầng nghiệp vụ**, dựa vào job/version/hash phù hợp và checkpoint/transaction sau xử lý thành công, không chỉ `Set<Path>`.
- **WatchService có thể mất events** khi overflow, shutdown hoặc provider hạn chế; startup scan/reconciliation định kỳ là cơ chế phục hồi quan trọng.
- **Java 17+ vẫn dùng NIO.2 hiện hành**; khác biệt hệ điều hành và filesystem phải được xử lý minh bạch qua integration tests, không dựa vào các giả định cố định về số sự kiện.

## Tài liệu chính thức

- [WatchService — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchService.html): giới hạn quan sát, event overflow, lifecycle, take/poll và khác biệt provider.
- [WatchKey — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchKey.html): pollEvents, reset, watchable và invalid keys.
- [WatchEvent — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchEvent.html): kind, count và context.
- [StandardWatchEventKinds — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): CREATE, MODIFY, DELETE, OVERFLOW và event count contract.
- [Path.register — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): đăng ký directory với WatchService.
- [Files.move — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): ATOMIC_MOVE và các giới hạn khi target tồn tại.
- [Files.readAttributes — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#readAttributes(java.nio.file.Path,java.lang.Class,java.nio.file.LinkOption...)): metadata và NOFOLLOW_LINKS.
- [Dev.java — Watching a Directory for Changes](https://dev.java/learn/api/io/java-io/file-system/watching-dir-changes/): tài liệu hướng dẫn chính thức về vòng đời WatchService.
