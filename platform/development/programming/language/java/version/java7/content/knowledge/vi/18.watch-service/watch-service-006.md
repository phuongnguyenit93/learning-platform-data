# `OVERFLOW` và việc quét lại trạng thái thực với `WatchService` trong Java

## 1. Khi thông báo thay đổi không còn đầy đủ

Một ứng dụng theo dõi thư mục bằng `WatchService` có thể cần biết file nào mới được tạo, file nào bị xóa và file nào đã sửa. Quy trình bình thường là đăng ký thư mục, nhận `WatchKey`, xử lý các `WatchEvent`, gọi `reset()` rồi tiếp tục lắng nghe. Nhưng khi hệ điều hành hoặc implementation không theo kịp tốc độ thay đổi, **một số sự kiện có thể bị mất hoặc bị bỏ đi**.

Java cung cấp sự kiện đặc biệt:

~~~java
StandardWatchEventKinds.OVERFLOW
~~~

`OVERFLOW` là tín hiệu **có khả năng mất sự kiện**, không phải tên file bị mất. Nó yêu cầu chương trình đánh giá lại độ tin cậy của danh mục dữ liệu đang giữ và, khi cần tính đúng, **quét lại trạng thái thực của thư mục/file system**.

Ví dụ:

~~~text
Thư mục inbox/               Chỉ mục mà chương trình đang giữ
    old.txt                      old.txt
    keep.txt                     keep.txt

Có rất nhiều thay đổi nhanh; một số event bị bỏ.
    old.txt bị xóa
    new.txt được tạo
    keep.txt đổi nội dung

WatchService báo OVERFLOW.
    |
    v
Không đoán các tên file đã mất từ event.
    |
    v
Quét lại inbox/ và so sánh trạng thái mới với chỉ mục cũ.
    |
    +-- added: new.txt
    +-- removed: old.txt
    +-- modified: keep.txt
~~~

Đây là **sơ đồ minh họa**, không phải lời hứa rằng mọi lần quét đều cho một snapshot nguyên tử. Học phần này thuộc chủ đề **`WatchService`** trong Java NIO.2.

**Mục tiêu sau bài học:**

1. Giải thích đúng `StandardWatchEventKinds.OVERFLOW`, các tình huống có thể phát sinh và giới hạn thông tin của nó.
2. Phân biệt `OVERFLOW` với `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY` và event coalescing.
3. Hiểu vì sao `event.context()` của `OVERFLOW` **không được mặc định ép sang `Path`**.
4. Thiết kế cơ chế đánh dấu *dirty* và **reconciliation** (quét lại để đối chiếu trạng thái thực).
5. Giữ vòng đời `WatchKey.pollEvents()` → `reset()` → tiếp tục nhận sự kiện, kể cả khi cần rescan.
6. Biết điều gì có thể và không thể suy ra từ tên file, size, modified time, hash, metadata và filesystem snapshot.
7. Xử lý mất đăng ký, nhiều thư mục, subtree, giới hạn provider, remote filesystem và các tình huống cạnh tranh khi quét.
8. Biên dịch/chạy ví dụ Java 21 có kiểm thử nhánh `OVERFLOW` **mô phỏng có chủ đích**, thay vì giả vờ đã làm overflow thật của OS.

**Tính hiện hành:** `WatchService`, `WatchKey` và `StandardWatchEventKinds` có từ Java 7 và **vẫn áp dụng trên Java 21 cùng các JDK hiện đại**. Bài dùng các API chuẩn, không đề xuất cách làm legacy hoặc coi WatchService như một event journal có bảo đảm mà nó không có.

## 2. Mô hình xử lý bình thường của `WatchService`

Một chương trình tiêu thụ event thường có vòng đời:

~~~text
Tạo WatchService
     |
Đăng ký directory với các ENTRY_* kinds
     |
Lấy WatchKey qua poll() / poll(timeout) / take()
     |
key.pollEvents() -> duyệt WatchEvent
     |
Xử lý event; gặp OVERFLOW thì đánh dấu cần quét lại
     |
key.reset() -> kiểm tra boolean còn valid
     |
Theo dõi tiếp / dừng khi đóng watcher
~~~

Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `Path.register(...)` | Đăng ký directory với `WatchService` |
| `WatchService.poll()` | Lấy một key sẵn sàng hoặc trả `null` ngay |
| `WatchService.poll(timeout, unit)` | Đợi tối đa thời gian, có thể trả `null` |
| `WatchService.take()` | Đợi cho tới khi có key |
| `WatchKey.pollEvents()` | Lấy và xóa danh sách event đang chờ của key |
| `WatchKey.watchable()` | Trả đối tượng đã đăng ký, thường là `Path` directory |
| `WatchKey.reset()` | Đưa key về trạng thái có thể được báo hiệu lại; trả false nếu invalid |
| `WatchKey.cancel()` | Hủy một đăng ký |
| `WatchService.close()` | Đóng toàn bộ service và các đăng ký liên quan |

Một key có thể tích lũy **nhiều event**. Nó được đưa vào queue khi từ trạng thái *ready* chuyển sang *signalled*; các event đến trong lúc key vẫn signalled có thể được tích lũy mà không enqueue cùng key lần nữa. Sau khi xử lý batch, phải gọi `reset()` để hệ thống tiếp tục đánh thức đúng vòng đời.

**Không có `reset()` thì không có mô hình quan sát bền vững đúng đắn**, dù phần xử lý `OVERFLOW` của bạn có viết tốt đến đâu. Tuy nhiên `reset()` cũng **không khôi phục các event đã bị mất**.

## 3. `OVERFLOW` là gì theo hợp đồng API?

Hằng số:

~~~java
WatchEvent.Kind<Object> overflowKind = StandardWatchEventKinds.OVERFLOW;
~~~

Đây là đoạn minh họa với import `WatchEvent` và `StandardWatchEventKinds`.

Javadoc Java SE 21 mô tả `OVERFLOW` là một sự kiện đặc biệt chỉ ra **các sự kiện có thể đã bị mất hoặc bị loại bỏ**.

Khi filesystem tạo ra thay đổi nhanh hơn ứng dụng/provider có thể nhận và xử lý, implementation có thể đặt giới hạn về lượng event tích lũy. Khi implementation **biết mình đã loại bỏ event**, nó sắp xếp để `pollEvents()` trả một sự kiện `OVERFLOW`. Điều này không biến WatchService thành nhật ký đầy đủ: còn các tình huống provider không thể quan sát hoặc không phát hiện thay đổi, đặc biệt trên một số hệ thống remote/network.

### 3.1. Không cần đăng ký `OVERFLOW`

Bạn thường đăng ký:

~~~java
WatchKey key = directory.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);
~~~

Đây là đoạn minh họa, cần directory tồn tại và watcher tương thích. **Không phải** đăng ký `OVERFLOW` riêng để nhận nó. Nó có thể được báo bất kể tập `ENTRY_*` đã đăng ký.

**Không thêm `OVERFLOW` như một loại bắt buộc trong lời gọi register để “bật” phát hiện mất event.** Javadoc quy định đây là sự kiện đặc biệt, không cần đăng ký.

### 3.2. `context()` không nhất thiết là tên file

Các event `ENTRY_CREATE`/`ENTRY_DELETE`/`ENTRY_MODIFY` chuẩn có `WatchEvent.Kind<Path>`; `context()` thường là tên entry tương đối với directory đã đăng ký. `OVERFLOW` có **`WatchEvent.Kind<Object>`**:

- `context()` của `OVERFLOW` **implementation-specific** và **có thể `null`**.
- `count()` của `OVERFLOW` có thể lớn hơn `1`.
- `count()` **không phải** một danh sách tên file đã mất hoặc một bằng chứng cho phép phục dựng chúng.
- Một event `OVERFLOW` không cho biết file nào được tạo/xóa/sửa, thứ tự thay đổi hay nội dung cũ.
- Không cast mọi `WatchEvent<?>.context()` sang `Path` trước khi xét `kind()`.

Mẫu phân loại đúng:

~~~java
for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        directoryIsDirty = true;  // Cần đồng bộ lại.
        continue;                 // Không suy đoán event.context() là Path.
    }
    if (event.context() instanceof Path relative) {
        Path changed = ((Path) key.watchable()).resolve(relative);
        // Đây chỉ là một gợi ý rằng tên changed cần kiểm tra lại.
    }
}
boolean stillValid = key.reset();
~~~

Đây là **mẫu minh họa**, cần các biến và xử lý ngoại lệ phù hợp. Mục tiêu là ưu tiên phân loại `OVERFLOW` trước khi dùng `context()`. `stillValid == false` nghĩa đăng ký đã invalid; tiếp tục đọc thông báo từ cùng key như thể nó còn valid là sai.

### 3.3. Khác biệt giữa gộp event và mất event

| Hiện tượng | Ý nghĩa | Hành động gợi ý |
| --- | --- | --- |
| Nhiều `ENTRY_MODIFY` được gộp, `count() >= 1` | Provider tóm gọn những thông báo sửa | Xem lại **trạng thái hiện tại**; không đếm số lần lưu bằng số event |
| `ENTRY_CREATE` có `count()==1` | Một entry được quan sát là tạo/di chuyển vào | Kiểm tra file thực tế nếu sẽ đọc nó |
| `ENTRY_DELETE` có `count()==1` | Một entry được quan sát là xóa/di chuyển ra | Cập nhật index theo chính sách, xét file có thể được tạo lại |
| `OVERFLOW` | Có thể đã mất/bỏ event | Đánh dấu **không đủ tin cậy**, quét lại/reconcile |

**Coalescing không đồng nghĩa OVERFLOW.** Một file được sửa liên tục có thể chỉ tạo một event MODIFY có count lớn hơn một mà provider không phải đã bỏ mất thông tin theo cùng nghĩa với overflow. Dù vậy, ngay cả khi không có overflow, WatchService vẫn không hứa mọi lần ghi logic sẽ có một event riêng.

## 4. Tại sao xử lý mỗi event còn lại là không đủ?

Giả sử chỉ mục được xây từ các event:

~~~text
Trạng thái index tại t0: [old.txt, keep.txt]

Thực tế:
t1: old.txt bị xóa, event DELETE bị bỏ
t2: new.txt được tạo, event CREATE bị bỏ
t3: keep.txt đổi nội dung, MODIFY bị bỏ
t4: OVERFLOW được trả về

Nếu chỉ duyệt những event còn lại:
- old.txt vẫn tồn tại sai trong index.
- new.txt không bao giờ được thêm.
- keep.txt mang dữ liệu cũ.
~~~

Nếu sau `OVERFLOW` bạn chỉ bỏ qua event và `reset()`, chương trình có thể tiếp tục nhận thông báo mới trong tương lai nhưng **không tự sửa các sai lệch quá khứ**. Chính vì vậy nó cần một **nguồn sự thật khác**: danh sách file/metadata/nội dung thực tế ở hệ thống lưu trữ.

**Nguyên tắc:** WatchService là **tín hiệu phát hiện thay đổi**, không phải cơ sở dữ liệu đầy đủ về trạng thái. Khi thông tin có thể mất, phải **đối chiếu lại với trạng thái thật**.

Quá trình đối chiếu được gọi là **reconciliation**: thu một ảnh chụp logic hiện tại từ filesystem, so với index cũ, rồi sinh các thay đổi tương ứng hoặc thay thế index.

## 5. Thuật toán tối thiểu: đánh dấu dirty → quét lại → so sánh → cập nhật index

Một workflow tổng quát:

~~~text
                          +---------------------+
                          | Watch event batch   |
                          +---------------------+
                                     |
                    +----------------+------------------+
                    |                                   |
             ENTRY_* events                         OVERFLOW
                    |                                   |
          Đánh dấu tên liên quan                Đánh dấu directory
          cần kiểm tra lại                      DIRTY/UNTRUSTED
                    |                                   |
          Thử đọc trạng thái tên đó            Xếp lịch full rescan
                    |                                   |
                    +----------------+------------------+
                                     |
                       Đọc trạng thái filesystem
                                     |
                     So sánh với snapshot/index cũ
                                     |
                     Thêm / xóa / sửa các index entry
                                     |
                     Xác minh, tiếp tục theo dõi
~~~

Một cách tổ chức đơn giản:

1. Giữ một `Map<RelativePath, FileState>` cho directory đang quan sát.
2. Khi nhận `ENTRY_*` bình thường, xem event là **gợi ý** rồi kiểm tra lại mục đó; có thể gộp tên trùng để giảm I/O.
3. Khi gặp `OVERFLOW`, đặt cờ `dirty=true` cho directory hoặc subtree thích hợp, không cố suy đoán các mục đã mất.
4. Lên lịch **full scan** toàn bộ phạm vi được index và đăng ký tương ứng.
5. So `snapshot trước` và `snapshot mới` để tìm added, removed, modified.
6. Cập nhật index dựa trên kết quả scan thành công; không đánh dấu “đã đồng bộ” nếu scan lỗi hay chưa có cơ chế xử lý race.
7. Tiếp tục nhận/thu các event phát sinh trong quá trình scan và có chiến lược lặp lại scan khi cần.
8. Định kỳ reconcile lại nếu yêu cầu độ đúng, kể cả khi **không có `OVERFLOW`**, vì không phải mọi nguồn thay đổi đều được provider phát hiện.

### 5.1. “Trạng thái thực” là gì?

Phụ thuộc use case:

| Mục tiêu ứng dụng | FileState có thể chứa | Giới hạn |
| --- | --- | --- |
| Hiển thị danh sách tên file | `Path` tương đối / loại entry | Không phát hiện thay đổi nội dung cùng tên |
| Ghi nhận file được cập nhật | Size + lastModifiedTime + metadata | Có thể không phát hiện sửa cùng kích thước hoặc timestamp không đủ chính xác |
| Đồng bộ nội dung | Content hash từ bytes đã đọc | Phải đọc dữ liệu, tốn I/O/CPU; có race nếu file bị sửa khi hash |
| Quản lý đối tượng có version | Version/generation/ETag từ backend có hỗ trợ | Không phải thuộc tính chung của mọi `Path` |
| Kiểm kê subtree | Cấu trúc thư mục + file + symlink policy | Phải quản lý recursive registration và xử lý tạo/xóa directory |

**Không chọn “chỉ tên file”** nếu yêu cầu phải biết nội dung đã thay đổi. Trong ví dụ Java dưới đây, ta cố ý lưu **toàn bộ nội dung của vài file UTF-8 nhỏ** để có thể phát hiện `modified` rõ ràng. Đây là lựa chọn **cho bài học**, không phải cách index file lớn trong sản phẩm thực tế.

### 5.2. So sánh hai snapshot

Giả sử:

~~~text
Snapshot trước: {keep.txt=one, old.txt=gone}
Snapshot sau:   {keep.txt=two, new.txt=new}

Added:    new.txt
Removed:  old.txt
Modified: keep.txt
~~~

Thuật toán:

- `added` = tên trong snapshot mới nhưng không có trong snapshot cũ.
- `removed` = tên trong snapshot cũ nhưng không còn trong snapshot mới.
- `modified` = tên có trong cả hai nhưng giá trị `FileState` khác nhau.
- Sau khi xử lý thành công, cập nhật index thành snapshot mới.

**Lưu ý:** nếu một file bị xóa rồi tạo lại với cùng tên **và nội dung giống hệt**, hai snapshot theo mô hình tên+nội dung sẽ không thấy khác biệt. Nếu nghiệp vụ quan tâm tới **identity** hoặc từng thao tác lịch sử, phải dùng cơ chế version/fileKey/provider journal phù hợp. WatchService cũng không bảo đảm tái tạo lịch sử như transaction log.

## 6. Chương trình Java 21 hoàn chỉnh: mô phỏng OVERFLOW và quét file thật

Để kiểm thử code xử lý overflow **đúng và lặp lại được**, chúng ta không cố “làm đầy” queue của hệ điều hành bằng hàng nghìn lệnh ghi rồi đoán xem `OVERFLOW` có xuất hiện hay không. Giới hạn queue, cách phát event và timing là đặc thù provider, nên bài test đó rất dễ không ổn định.

Thay vào đó, ví dụ làm hai việc **tách bạch**:

1. Thao tác thật trên một thư mục tạm: tạo hai file, lấy snapshot, sửa một file, xóa một file, tạo file mới.
2. Đưa **một `WatchEvent<Object>` giả lập kind `OVERFLOW`** vào hàm tiếp nhận sự kiện, đánh dấu dirty rồi quét lại filesystem thật để phát hiện chính xác `added`/`removed`/`modified`.

Ví dụ **không khẳng định hệ điều hành thực sự đã phát sinh OVERFLOW**. Nó kiểm thử logic xử lý tín hiệu mất event và thuật toán rescan theo cách có thể tái hiện.

Tạo file `src/main/java/demo/OverflowReconciliationExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Stream;

public final class OverflowReconciliationExample {
    private OverflowReconciliationExample() {}

    record Changes(List<String> added, List<String> removed,
                   List<String> modified) {}

    static TreeMap<String, String> scanSmallTextFiles(Path directory)
            throws IOException {
        TreeMap<String, String> files = new TreeMap<>();
        try (Stream<Path> stream = Files.list(directory)) {
            for (Path entry : stream.toList()) {
                if (Files.isRegularFile(entry, LinkOption.NOFOLLOW_LINKS)) {
                    files.put(entry.getFileName().toString(),
                            Files.readString(entry, StandardCharsets.UTF_8));
                }
            }
        }
        return files;
    }

    static Changes difference(Map<String, String> before,
                              Map<String, String> after) {
        TreeSet<String> added = new TreeSet<>(after.keySet());
        added.removeAll(before.keySet());

        TreeSet<String> removed = new TreeSet<>(before.keySet());
        removed.removeAll(after.keySet());

        List<String> modified = new ArrayList<>();
        for (String name : before.keySet()) {
            if (after.containsKey(name)
                    && !before.get(name).equals(after.get(name))) {
                modified.add(name);
            }
        }
        modified.sort(String::compareTo);
        return new Changes(List.copyOf(added), List.copyOf(removed),
                List.copyOf(modified));
    }

    static final class Index {
        private Map<String, String> files;
        private boolean dirty;

        Index(Map<String, String> initial) {
            this.files = Map.copyOf(initial);
        }

        void accept(WatchEvent<?> event) {
            if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                dirty = true;
                return; // No file name can be trusted for OVERFLOW.
            }

            if (event.kind() == StandardWatchEventKinds.ENTRY_CREATE
                    || event.kind() == StandardWatchEventKinds.ENTRY_DELETE
                    || event.kind() == StandardWatchEventKinds.ENTRY_MODIFY) {
                dirty = true;
            }
        }

        Changes reconcile(Path directory) throws IOException {
            TreeMap<String, String> fresh = scanSmallTextFiles(directory);
            Changes changes = difference(files, fresh);
            files = Map.copyOf(fresh);
            dirty = false; // Valid only for this successful scan in this demo.
            return changes;
        }

        boolean isDirty() {
            return dirty;
        }

        TreeSet<String> names() {
            return new TreeSet<>(files.keySet());
        }
    }

    // Synthetic test double, NOT an event sent by the real file system.
    static final class SimulatedOverflow implements WatchEvent<Object> {
        @Override
        public Kind<Object> kind() {
            return StandardWatchEventKinds.OVERFLOW;
        }

        @Override
        public int count() {
            return 2;
        }

        @Override
        public Object context() {
            return null;
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("overflow-snapshot-");
        Path keep = directory.resolve("keep.txt");
        Path old = directory.resolve("old.txt");
        Path added = directory.resolve("new.txt");

        try {
            Files.writeString(keep, "one", StandardCharsets.UTF_8);
            Files.writeString(old, "gone", StandardCharsets.UTF_8);

            try (WatchService watcher =
                    directory.getFileSystem().newWatchService()) {
                WatchKey key = directory.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                Index index = new Index(scanSmallTextFiles(directory));
                System.out.println("watch-key-valid=" + key.isValid());
                System.out.println("initial=" + index.names());

                // These mutations are deterministic; real event delivery is not.
                Files.writeString(keep, "two", StandardCharsets.UTF_8);
                Files.delete(old);
                Files.writeString(added, "new", StandardCharsets.UTF_8);

                WatchEvent<Object> simulated = new SimulatedOverflow();
                index.accept(simulated);
                System.out.println("overflow-simulated="
                        + (simulated.kind() == StandardWatchEventKinds.OVERFLOW));
                System.out.println("overflow-context-null="
                        + (simulated.context() == null));
                System.out.println("dirty-after-overflow=" + index.isDirty());

                Changes changes = index.reconcile(directory);
                System.out.println("added=" + changes.added());
                System.out.println("removed=" + changes.removed());
                System.out.println("modified=" + changes.modified());
                System.out.println("dirty-after-reconcile=" + index.isDirty());
                System.out.println("reconciled=" + index.names());

                key.cancel();
                System.out.println("key-valid-after-cancel=" + key.isValid());
            }
        } finally {
            Files.deleteIfExists(keep);
            Files.deleteIfExists(old);
            Files.deleteIfExists(added);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Dùng **JDK 21** từ thư mục chứa `src/`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/OverflowReconciliationExample.java
java -cp out demo.OverflowReconciliationExample
~~~

**Stdout chính xác đã kiểm thử trên default filesystem Windows:**

~~~text
watch-key-valid=true
initial=[keep.txt, old.txt]
overflow-simulated=true
overflow-context-null=true
dirty-after-overflow=true
added=[new.txt]
removed=[old.txt]
modified=[keep.txt]
dirty-after-reconcile=false
reconciled=[keep.txt, new.txt]
key-valid-after-cancel=false
~~~

### 6.1. Giải thích output

- `watch-key-valid=true`: directory tạm được đăng ký thành công với WatchService của filesystem đó. Đây **không** chứng minh watcher đã phát sinh `OVERFLOW`.
- `initial=[keep.txt, old.txt]`: index ban đầu có hai file.
- `overflow-simulated=true`: đối tượng test double trả kind `OVERFLOW`. Nó **không phải** notification thật từ kernel hay filesystem provider.
- `overflow-context-null=true`: mô phỏng một trường hợp context rỗng được Javadoc cho phép; code không cần tên file của event.
- `dirty-after-overflow=true`: handler đánh dấu index chưa đủ tin cậy.
- `added=[new.txt]`: scan thực thấy một tên mới.
- `removed=[old.txt]`: tên cũ không còn.
- `modified=[keep.txt]`: tên giữ nguyên nhưng nội dung khác (`"one"` → `"two"`), vì vậy so tên đơn thuần sẽ bỏ sót.
- `dirty-after-reconcile=false`: trong bài test **không có tác nhân sửa đồng thời khi scan**, nên index được xem là đồng bộ sau lần quét thành công. Điều này **không phải** cam kết rescan luôn là atomic trong hệ thống thật.
- `reconciled=[keep.txt, new.txt]`: snapshot mới phản ánh hai file còn lại.
- `key-valid-after-cancel=false`: hủy đăng ký bằng `cancel`; `WatchService` còn được đóng trong try-with-resources.

### 6.2. Vì sao code dùng `Files.list` và `NOFOLLOW_LINKS`?

`Files.list(directory)` trả một `Stream<Path>` giữ tài nguyên directory, nên ví dụ bọc trong try-with-resources. `Files.isRegularFile(entry, LinkOption.NOFOLLOW_LINKS)` chỉ lấy regular files trực tiếp, **không** tự theo symbolic link vào file hoặc thư mục ngoài phạm vi.

Đây là **một lựa chọn policy của demo**, không có nghĩa `NOFOLLOW_LINKS` tự giải quyết mọi path race. Nếu actor khác có thể thay entry sau kiểm tra `isRegularFile` nhưng trước `readString`, vẫn có TOCTOU. Trong demo một thread riêng kiểm soát toàn bộ thao tác nên kết quả ổn định.

### 6.3. Tại sao lưu toàn bộ chuỗi nội dung?

Các file thử chỉ có vài byte và là UTF-8 hợp lệ, nên `Map<String,String>` đủ để nhìn rõ sự thay đổi nội dung. Trong ứng dụng sản xuất:

- Không dùng `Files.readString` cho hàng triệu file/gigabyte một cách mù quáng.
- Nếu cần phát hiện thay đổi, có thể dùng checksum/hash trên dữ liệu và metadata thích hợp, nhưng phép đọc có I/O cost và race riêng.
- Nếu chỉ cần danh sách file, lưu tên và loại entry có thể đủ.
- Nếu muốn theo dõi object identity/version chặt chẽ, dùng khả năng snapshot/journal/versioning của storage, không tự suy ra từ tên file hoặc timestamp.
- Khi đọc file thất bại giữa scan, nên **không đánh dấu rescan thành công** cho phần đã lỗi; giữ trạng thái dirty và retry có kiểm soát.

### 6.4. Sự kiện mô phỏng kiểm thử được điều gì?

Chúng ta đã kiểm thử **logic khi có loại event OVERFLOW**: đánh dấu dirty, đối chiếu với filesystem, cập nhật map. Chúng ta **chưa** kiểm thử rằng default filesystem sẽ tự phát `OVERFLOW` nếu queue quá tải trong một thời gian nhất định.

Để kiểm tra integration với provider thật, có thể tạo workload thay đổi nhiều và theo dõi quan sát, nhưng không nên viết unit test giả định “sau N file thì chắc chắn OVERFLOW”, vì event batching, coalescing, queue capacity và provider có thể đổi theo OS/JDK. Unit test dùng test double hoặc tách hàm xử lý sự kiện sẽ ổn định và tập trung vào hành vi phải có.

## 7. Cách nhận `OVERFLOW` trong vòng lặp WatchService thật

Ví dụ **mẫu code production skeleton**, không phải chương trình độc lập:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    WatchKey key = watcher.take(); // Có thể InterruptedException.
    Path directory = (Path) key.watchable();
    boolean fullRescanNeeded = false;
    Set<Path> changedNames = new HashSet<>();

    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
            fullRescanNeeded = true;
            continue;
        }

        if (event.context() instanceof Path relative) {
            changedNames.add(relative);
        }
    }

    boolean valid = key.reset();

    if (!valid) {
        // Đánh dấu mất đăng ký, thông báo/quét lại và xử lý việc đăng ký mới.
    }

    if (fullRescanNeeded) {
        // Xếp một công việc full rescan cho directory, KHÔNG cần tên event.
    } else {
        // Xếp các tên trong changedNames để kiểm tra trạng thái hiện tại.
    }
}
~~~

Đoạn này cần `watcher`, `Set`, `HashSet` và các import tương ứng. Phải xử lý `InterruptedException`, `ClosedWatchServiceException`, I/O và kiểm soát vòng đời watcher ở tầng bên ngoài. Nó **cố ý chưa triển khai worker queue/reconciliation**, để không giả vờ một vòng ngắn là hệ monitor production hoàn chỉnh.

Những điều quan trọng:

1. **Đọc toàn bộ batch** từ `pollEvents()`, không dừng ở event đầu.
2. **Ưu tiên `OVERFLOW`**: một khi thấy overflow, việc chỉ xử lý `changedNames` **không đủ** để khôi phục các entry có thể bị mất.
3. **`reset()` vẫn cần gọi** sau xử lý batch; `OVERFLOW` không thay reset.
4. Nếu `reset()` trả false, registration invalid: phải xem lại directory và đăng ký mới nếu cần. Rescan không tự làm key valid trở lại.
5. Xếp công việc quét ra thread/queue có kiểm soát nếu scan rất tốn thời gian; tránh để event-consumer đứng yên quá lâu khiến queue tiếp tục ùn.
6. Số lượng scan không nên tăng vô hạn khi có 100 event overflow liên tiếp: gộp cờ dirty theo directory, giới hạn số job đồng thời, và cho phép rescan lại nếu có thay đổi trong quá trình đang scan.
7. Khi một directory bị xóa/rename, `key.watchable()` vẫn có thể trả path cũ; điều đó **không bảo đảm path còn hợp lệ**, nên việc đăng ký lại phải xác minh đối tượng mới.

### 7.1. Khi xử lý event bằng nhiều thread

`WatchService` và `WatchKey` được thiết kế có thể được dùng bởi các luồng, nhưng nếu nhiều consumer cùng nhận key:

- Chỉ một worker nên sở hữu xử lý event của **một key** trong một thời điểm.
- Không `reset()` key **trước** khi xử lý xong batch của key; Javadoc cảnh báo có thể dẫn tới concurrent processing cho cùng đối tượng.
- Có thể đưa công việc nặng như đọc file lớn/scan vào worker queue, nhưng phải quản lý trách nhiệm ghi index và trạng thái dirty phù hợp.
- Watcher event pipeline và reconciliation worker cần phối hợp bằng lock, serial executor, version/generation hoặc một phương pháp đồng bộ khác, không cùng sửa `Map` không thread-safe tùy tiện.

Ví dụ `Index` ở phần 6 chỉ chạy một luồng, không phải thiết kế thread-safe cho dịch vụ nhiều worker.

## 8. Quét lại trong lúc file system tiếp tục biến động: bài toán race

**Một lần `Files.list` hoặc `Files.walk` không phải snapshot transaction của toàn bộ directory.** Trong lúc bạn liệt kê entry, actor khác có thể tạo/xóa/sửa file. Vì thế **việc một lần scan trả thành công không tự chứng minh index đã phản ánh mọi thay đổi ở đúng cùng một thời điểm**.

Một kịch bản:

~~~text
t0: nhận OVERFLOW, đánh dấu directory DIRTY
t1: bắt đầu quét directory
t2: trong khi quét, another process tạo z.txt
t3: scan kết thúc nhưng z.txt không được quan sát
t4: code xóa cờ DIRTY một cách vô điều kiện
t5: không còn event mới để báo z.txt
=> index vẫn thiếu z.txt
~~~

**Cách khắc phục ở mức kiến trúc:** không chỉ quét một lần rồi coi đã hoàn tất. Phối hợp trạng thái dirty, event đang đến, cơ chế quét lại khi có mutation xảy ra trong scan, hoặc dùng storage snapshot/journal nếu cần tính đúng mạnh.

### 8.1. Một chiến lược best effort có kiểm soát

Với hệ thống đồng bộ **eventual consistency** (chấp nhận trễ hội tụ):

1. Đăng ký watch cho directory cần quan sát.
2. Quét xây baseline index; trong lúc quét **tiếp tục thu các event** hoặc để queue giữ chúng trong giới hạn.
3. Gộp các event nhận được và đánh dấu tên/directory cần đối chiếu; khi có `OVERFLOW` phải full rescan.
4. Sau scan, xử lý những event đến trong giai đoạn quét, hoặc khởi động một vòng đối chiếu tiếp nếu dirty vẫn được đánh dấu.
5. Dùng một **generation counter**/phiên bản công việc để không có worker quét cũ ghi đè snapshot mới.
6. Có giới hạn tài nguyên/backoff; nếu lỗi scan thì giữ dirty và báo tình trạng chưa đồng bộ.
7. Thực hiện **đối chiếu định kỳ** theo nhu cầu vận hành, kể cả khi watcher không phát sự kiện.
8. Ghi metric cho số overflow, tuổi của bản scan mới nhất, số lần scan lỗi, số directory đăng ký và độ trễ hội tụ.

Đây là **chiến lược best effort**, không phải một proof rằng registration + scan + event drain tạo một snapshot atomic. Với nghiệp vụ cần lịch sử chính xác từng thao tác hoặc nhất quán mạnh, phải dùng transaction/snapshot/journal hoặc interface lưu trữ phù hợp.

### 8.2. Gợi ý state machine

~~~text
CLEAN
  | ENTRY_*              | OVERFLOW
  v                      v
PENDING_NAMES          DIRTY_FULL
  |                      |
  | xử lý tên             | quét đủ phạm vi
  v                      v
CLEAN hoặc DIRTY       VALIDATING
                         |
                +--------+--------+
                |                 |
         có event mới, lỗi     scan hoàn tất,
         hoặc version đổi      không còn dirty
                |                 |
                v                 v
            DIRTY_FULL          CLEAN
~~~

Dù dùng state machine nào, cần phân biệt:

- **Đã scan xong** là thông tin về công việc quét.
- **Đã bắt kịp trạng thái thật** là yêu cầu consistency mạnh hơn.
- **Không có event mới** không chứng minh hệ thống file đã bất biến.
- **Đã reset key** chỉ liên quan vòng đời notification, không đồng nghĩa chỉ mục được khôi phục.

## 9. Quét lại một thư mục hay toàn cây?

`WatchService` thường theo dõi **entry trực tiếp của từng directory** được đăng ký; nó **không tự đăng ký đệ quy tất cả thư mục con**.

Ví dụ:

~~~text
project/               key A đã đăng ký
   src/                key B đã đăng ký
      App.java
      util/             chưa đăng ký
         Codec.java
~~~

Nếu một `OVERFLOW` liên quan đến `key A`, cần xét ít nhất thư mục `project/` mà key A theo dõi. Nhưng nếu ứng dụng quản lý cả subtree, các event mất có thể bao gồm **việc tạo/xóa một directory con**: bạn có thể đã bỏ lỡ cơ hội đăng ký watcher cho subtree mới.

Do đó, khi mô hình theo dõi toàn cây, reconciliation thường phải:

- Quét lại thư mục bị dirty để xác định những directory/file mới hoặc bị xóa.
- **Đối chiếu cả tập đăng ký directory**, không chỉ danh sách file.
- Đăng ký watcher cho directory mới mà chính sách yêu cầu quan sát.
- Loại bỏ/hủy key cho directory đã không còn phù hợp.
- Khi cần, quét sâu vào các directory mới phát hiện để thu các descendants đã tồn tại trước lúc đăng ký.
- Cân nhắc full subtree rescan nếu không thể xác định phạm vi biến động từ một key duy nhất.

Không dùng `Files.walk(root, Integer.MAX_VALUE)` không điều kiện trên dữ liệu không tin cậy. Hãy đặt giới hạn sâu, số lượng mục, time budget và chính sách symlink rõ ràng.

### 9.1. Symlink có thể dẫn ra ngoài phạm vi mong muốn

Nếu một thư mục trong subtree là symbolic link tới directory ở ngoài root, việc vô tình đi theo link khi scan/đăng ký có thể dẫn ứng dụng tới vùng ngoài dự kiến. Trong bài thử, `Files.isRegularFile(..., LinkOption.NOFOLLOW_LINKS)` chủ ý bỏ symlink khi lấy snapshot. Trong ứng dụng thật, cần quyết định:

- Có theo symlink khi tìm directory cần đăng ký không?
- Root có phải vùng được phép truy cập không?
- Người dùng khác có thể đổi symlink sau bước kiểm tra không?
- Cơ chế nào bảo vệ trước TOCTOU cho các thao tác đọc/ghi nhạy cảm?

**Rescan không tự cung cấp ranh giới bảo mật**. Đây là vấn đề phân quyền và truy cập filesystem riêng với việc xử lý event loss.

## 10. OVERFLOW không phải trường hợp duy nhất cần rescan

Ngay cả khi **không bao giờ quan sát được `OVERFLOW`**, một index có thể lệch trạng thái thật bởi vì:

- File được tạo rồi xóa quá nhanh giữa các lần polling của provider.
- Filesystem từ xa không báo hoặc báo thiếu thay đổi.
- Process đã ngừng chạy trong lúc có thay đổi; khi khởi động lại không có replay lịch sử event.
- Một directory con chưa kịp được đăng ký (recursive watcher bootstrap race).
- Sự kiện được gộp hoặc đến sau khi logic nghiệp vụ đã dự đoán sai thứ tự.
- Một file đổi nội dung khi indexer chưa mở được nó vì đang bị ghi hoặc bị khóa.
- Đăng ký WatchKey invalid mà ứng dụng không biết/không khôi phục kịp.

Vì thế **rescan sau overflow là bắt buộc theo chính sách tính đúng, nhưng rescan định kỳ cũng thường hữu ích** khi yêu cầu phải hội tụ với filesystem.

Một hệ thống có yêu cầu rất mạnh về dữ liệu không nên dựa vào WatchService làm **nguồn sự thật duy nhất**. Nên sử dụng version, content-addressed storage, journal, file system snapshot hoặc transactional metadata nếu hạ tầng hỗ trợ.

## 11. Quản lý lỗi trong quá trình quét

| Tình huống | Ví dụ | Ứng xử |
| --- | --- | --- |
| Directory không còn | `NoSuchFileException` hoặc key invalid | Gỡ đăng ký, xác minh path, đăng ký lại khi phù hợp |
| Không có quyền liệt kê | `AccessDeniedException` | Báo lỗi và giữ trạng thái chưa đồng bộ, không trả một snapshot rỗng giả |
| File biến mất giữa list và read | `NoSuchFileException` khi đọc entry | Chấp nhận tính biến động, retry/rescan theo chính sách |
| File đang được ghi | Nội dung đọc có thể chưa hoàn chỉnh | Dùng giao thức hoàn tất ghi hoặc nguồn có snapshot |
| Sai charset khi đọc text | `MalformedInputException` | Không nuốt lỗi như “không có file”; dùng định dạng đúng |
| `OVERFLOW` trong lúc quét | Có khả năng mất thêm event | Đánh dấu cần một vòng reconcile tiếp hoặc validate generation |
| WatchKey invalid | `reset() == false` | Xem lại đăng ký và phạm vi quét |
| WatchService đóng | `ClosedWatchServiceException` | Dừng monitor và giải phóng tài nguyên |
| Thread bị interrupt | `InterruptedException` | Propagate hoặc restore interrupt/thoát |
| Quá nhiều tệp | Scan gây quá tải RAM/IO | Chia công việc, giới hạn/batch, metrics và backoff |

Một **điểm phải nhớ**: xử lý `IOException` bằng cách trả về bản map rỗng là nguy hiểm. Nó có thể khiến reconciliation kết luận **mọi file đã bị xóa**, trong khi thực tế chỉ là ứng dụng không có quyền đọc directory.

Mẫu kết quả tốt hơn là một kiểu có trạng thái: `SUCCESS(snapshot)` hoặc `FAILURE(cause)`. Chỉ commit snapshot mới vào index khi scan được xem là thành công theo định nghĩa nghiệp vụ.

### 11.1. Khi nào cần hash nội dung?

Nếu yêu cầu phát hiện thay đổi nội dung cùng tên, chỉ so metadata `Files.size` và `Files.getLastModifiedTime` đôi khi chưa đủ:

- Hai nội dung có thể có cùng số byte.
- Timestamp resolution khác theo file system; một số thao tác có thể giữ hoặc thay timestamp.
- Có thể có rename/hard links/atomic replacement mà tên và size không đổi.
- Việc đọc metadata ở nhiều thời điểm cũng không tạo snapshot transaction.

Content hash có thể tăng độ tin cậy khi so sánh **bytes đã đọc**, nhưng việc hash vẫn có race nếu file đổi trong lúc đọc và chi phí I/O cao cho file lớn. Khi cần nhất quán mạnh, dùng cơ chế định danh/version/snapshot thích hợp; không tự biến hash vào một bảo đảm atomic về toàn bộ filesystem.

## 12. Testing: kiểm thử xử lý overflow khác với cố tạo overflow thật

### 12.1. Unit test phải có tính quyết định

Nên tách:

1. **Hàm nhận một `WatchEvent<?>`**, xác định `kind` và đánh dấu trạng thái.
2. **Hàm quét directory** trả snapshot.
3. **Hàm so sánh** hai snapshot.
4. **Hàm áp dụng kết quả** vào index và quản lý generation/dirty.

Như vậy có thể tạo một test double `WatchEvent<Object>` trả `OVERFLOW` để xác nhận handler đúng mà **không cần** tạo hàng chục nghìn file ngoài hệ thống. Chương trình phần 6 làm đúng cách này.

Có thể test thêm:

- `OVERFLOW` có context `null`.
- `OVERFLOW` có context kiểu khác `Path`.
- `count()` lớn hơn `1` mà logic vẫn chỉ đánh dấu dirty, không suy đoán tên.
- File mới, file xóa, file sửa cùng tên; đổi nội dung mà giữ size.
- Scan bị lỗi giữa chừng: **không commit** snapshot một phần.
- Event mới đến trong lúc scan: generation mới không bị bỏ quên.
- Nhiều OVERFLOW liên tiếp: gộp công việc, tránh chạy nhiều rescan cùng một directory.
- Key bị cancel hoặc watcher đóng: không vô tình tiếp tục dùng đăng ký cũ.

### 12.2. Integration test với OS/provider thật

Có thể thử tạo/xóa hàng loạt file để **quan sát** cách một provider cụ thể gộp và báo overflow. Nhưng:

- Không giả định một ngưỡng cố định N sẽ luôn gây overflow.
- Không lấy số sự kiện quan sát ở Windows làm quy tắc trên Linux/macOS hoặc network FS.
- Không cố dựa vào timing của `Thread.sleep` để chứng minh “sau 100 ms sự kiện chắc chắn tới”.
- Không giả vờ test đã xác minh `OVERFLOW` của kernel nếu chỉ đưa vào event mô phỏng.
- Không dùng test tạo hàng triệu file trong thư mục dùng chung chỉ để gây quá tải.

Các bài test quan trọng nhất là: **dù mất event**, hệ thống có cách **hội tụ lại** với trạng thái file thật hay không.

## 13. Những lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Bỏ qua `OVERFLOW` như một event không quan trọng | Index có thể thiếu/thừa item | Mark dirty, full rescan và reconcile |
| Cast `event.context()` của mọi event thành `Path` | OVERFLOW có thể có context `null` | Phân loại `kind()` trước |
| Nghĩ `count()` cho biết danh sách file đã mất | Count không chứa tên file/lịch sử | Tìm trạng thái bằng scan |
| Nghĩ OVERFLOW phải được register riêng | API trả overflow ngay cả khi không đăng ký | Register các `ENTRY_*` cần theo dõi |
| Chỉ reset key và coi đã sửa xong sai lệch | Reset chỉ khôi phục vòng đời key | Reconcile index với filesystem |
| Nghe thấy OVERFLOW rồi xử lý tên từ các event còn lại là đủ | Những event bị mất không còn tên | Quét phạm vi liên quan đầy đủ |
| Nghĩ một scan là snapshot transaction | File có thể đổi trong lúc quét | Lưu dirty/generation, lặp scan hoặc storage snapshot |
| Chỉ so tên file để phát hiện MODIFY | Nội dung cùng tên có thể đổi | Định nghĩa FileState phù hợp |
| Chỉ so size để xác định file không đổi | Hai nội dung có thể có cùng size | Bổ sung hash/version khi cần |
| Coi `Files.list` kết quả rỗng khi I/O lỗi | Có thể xóa sai mọi entry trong index | Báo lỗi, không commit snapshot thất bại |
| Quên try-with-resources cho `Files.list` / `Files.walk` | Rò rỉ file/directory resources | Đóng stream đúng vòng đời |
| Quên `key.reset()` | Key không sẵn sàng được báo lại | Reset sau xử lý batch |
| Bỏ qua `reset() == false` | Registration đã invalid | Gỡ key, kiểm tra directory, đăng ký mới |
| Quét toàn bộ cây trên thread lấy events | Dồn queue và gây thêm overflow | Dùng worker có giới hạn/backpressure |
| Nghĩ WatchService tự đăng ký descendants | Có thể mất file trong subtree mới | Reconcile cả danh sách directory watchers |
| Tin rằng không có OVERFLOW nghĩa không mất gì | Provider có thể không phát hiện thay đổi | Periodic reconciliation và nguồn thật |
| Ghi đè index bằng một scan cũ trong race | Làm mất trạng thái mới | Serialize/generation + commit có kiểm soát |
| Dùng symlink từ event mà không kiểm tra | Có thể truy cập ngoài root hoặc file bị thay | Chính sách OS/path/TOCTOU rõ ràng |
| Coi WatchService là transaction log durable | Không bảo đảm replay/history | Snapshot/journal/versioning khi cần |

## 14. Bài tập có đáp án

**Bài 1.** `OVERFLOW` báo điều gì?

**Đáp án:** Nó chỉ rằng các event **có thể đã bị mất hoặc bị loại bỏ**. Không cung cấp danh sách tên file hay diễn tiến thay đổi bị mất.

**Bài 2.** Có phải gọi `directory.register(watcher, OVERFLOW)` mới nhận được overflow?

**Đáp án:** Không. OVERFLOW có thể được trả bất kể các loại `ENTRY_*` đã đăng ký.

**Bài 3.** Với `OVERFLOW`, `event.context()` có nhất thiết là `Path` không?

**Đáp án:** Không. Hợp đồng API cho `WatchEvent.Kind<Object>` và context implementation-specific, có thể `null`.

**Bài 4.** Vì sao sau `OVERFLOW` phải quét lại trạng thái thực?

**Đáp án:** Vì event bị mất không thể khôi phục chỉ từ những event còn lại. Phải hỏi filesystem để biết file nào hiện có và những metadata/nội dung phù hợp với index.

**Bài 5.** `key.reset()` có tự phục hồi những `ENTRY_CREATE` đã mất không?

**Đáp án:** Không. Nó đặt lại trạng thái ready/signalled của key khi key valid, không tái tạo lịch sử event.

**Bài 6.** Snapshot A có `a.txt` với nội dung `"hello"`, snapshot B cũng có `a.txt` nhưng nội dung `"world"`. Nếu chỉ so tên file, phát hiện gì?

**Đáp án:** Không phát hiện sự thay đổi nội dung. Muốn biết modified, phải có `FileState` phản ánh nội dung/metadata/version phù hợp.

**Bài 7.** Quét directory thất bại do `AccessDeniedException`. Có nên cập nhật index thành rỗng không?

**Đáp án:** Không. “Không đọc được trạng thái” khác hoàn toàn với “thư mục rỗng”. Giữ dirty, log lỗi và retry/escalate theo policy.

**Bài 8.** Đã đăng ký root nhưng chưa đăng ký directory mới tạo bên dưới root. Nếu event tạo directory đó bị mất do overflow, cần làm gì?

**Đáp án:** Quét lại tree theo policy và đối chiếu cả **các directory cần đăng ký WatchKey**, không chỉ file names, rồi đăng ký thêm các directory mới phù hợp.

**Bài 9.** Tại sao JDK không đảm bảo OVERFLOW xảy ra sau đúng 512 event trong mọi test?

**Đáp án:** Batching, coalescing, implementation, system property và provider có thể khác nhau; Javadoc không cam kết một ngưỡng queue phổ quát cho mọi file system và mọi phiên bản. Không viết unit test phụ thuộc con số cụ thể.

**Bài 10.** Có thể quét xong một lần rồi luôn khẳng định index khớp 100% khi có process khác đang ghi liên tục không?

**Đáp án:** Không. Scan của `Files.list`/`walk` không phải snapshot toàn cục nguyên tử, nên cần concurrency policy, generation/retry hoặc backend có snapshot/version khi cần.

**Bài 11.** Vì sao không nên cho một lần quét lớn chạy đồng bộ trên thread chuyên xử lý event?

**Đáp án:** Khi thread chậm nhận/reset key, queue có thể tích lũy event và tăng rủi ro overflow mới; có thể đưa scan vào worker có backpressure và giới hạn số công việc.

**Bài 12.** Nếu `key.reset()` trả false sau khi xử lý overflow, chỉ cần scan là đăng ký sẽ hoạt động lại không?

**Đáp án:** Không. Key đã invalid; phải xác minh directory, đăng ký một key mới nếu cần theo dõi tiếp.

**Bài 13.** Vì sao chương trình demo dùng `SimulatedOverflow` thay vì cố ép file system phát overflow?

**Đáp án:** Đây là unit/integration test **xử lý nhánh event**, có tính quyết định. Việc provider báo overflow thực phụ thuộc tải, hàng đợi và OS; dùng test double giúp khẳng định thuật toán rescan mà không tuyên bố đã thử đặc tính kernel.

**Bài 14.** Một file bị xóa và tạo lại cùng tên, cùng nội dung giữa hai scan. Một index chỉ lưu `Map<name, content>` có phát hiện được identity đã thay không?

**Đáp án:** Không. Muốn phân biệt đối tượng/lịch sử phải có version/fileKey hoặc cơ chế lưu trữ phù hợp; WatchService cũng không tự cung cấp lịch sử đầy đủ trong tình huống mất event.

## 15. Checklist code review

- [ ] Biết `OVERFLOW` là tín hiệu mất event **có thể** đã xảy ra, không phải đường dẫn.
- [ ] Không bắt buộc đăng ký OVERFLOW riêng; luôn kiểm tra kind trước khi dùng context.
- [ ] Khi overflow, đánh dấu directory/subtree `dirty` và xếp lịch full reconciliation.
- [ ] Không dùng `event.count()` để dự đoán những path chưa thấy.
- [ ] Tiếp tục xử lý vòng đời `pollEvents()` và `reset()`; kiểm tra key invalid.
- [ ] Không coi reset là khôi phục event đã mất.
- [ ] Định nghĩa `FileState` phù hợp với nghiệp vụ: tên, metadata, nội dung/hash hay version.
- [ ] Không commit snapshot scan thất bại hoặc chỉ hoàn tất một phần.
- [ ] Đóng `Files.list`/`walk` Stream bằng try-with-resources.
- [ ] Đưa full rescan nặng sang worker có giới hạn; gộp nhiều dirty notification.
- [ ] Có chính sách event đến trong lúc scan và generation tránh stale write.
- [ ] Với recursive watcher, quét/đăng ký các directory con còn thiếu.
- [ ] Không theo symlink không kiểm soát hoặc dùng kết quả kiểm tra path như sandbox.
- [ ] Có periodic reconciliation khi yêu cầu dữ liệu hội tụ, không chỉ phụ thuộc OVERFLOW.
- [ ] Không khẳng định một test double đã kiểm thử overflow thật từ provider.
- [ ] Đọc Javadoc hiện hành và tuân thủ Special Note: chỉ học các API/quy tắc vẫn còn áp dụng, không tái sử dụng kiến thức legacy.

## 16. Tài liệu chính thức

- [Java SE 21 — WatchService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchService.html): giới hạn queue, lost/discarded events, `OVERFLOW`, xử lý thực tế và platform dependencies.
- [Java SE 21 — StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): `OVERFLOW` có `Kind<Object>`, context có thể `null`, `count` có thể lớn hơn 1.
- [Java SE 21 — WatchEvent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchEvent.html): `kind()`, `count()`, `context()`.
- [Java SE 21 — WatchKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchKey.html): `pollEvents()`, `reset()`, `cancel()`, `watchable()` và state machine của key.
- [Java SE 21 — Path.register](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): đăng ký directory với `WatchService` và các `ENTRY_*`.
- [Java SE 21 — Files.list](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): đọc danh sách entries, stream lifetime và xử lý I/O.
- [Dev.java — Watching a Directory for Changes](https://dev.java/learn/api/io/java-io/file-system/watching-dir-changes/): hướng dẫn `WatchService` và cách xử lý `OVERFLOW`.

**Kết luận:** khi `OVERFLOW` xuất hiện, không tìm cách suy ra tên file từ event không còn tồn tại. Hãy coi chỉ mục theo dõi là **không đủ tin cậy**, quét lại trạng thái thực, đối chiếu added/removed/modified, quản lý dirty/race và tiếp tục theo dõi đúng vòng đời key. Ngay cả khi không có overflow, `WatchService` vẫn chỉ là cơ chế thông báo: những ứng dụng cần độ đúng phải thiết kế **reconciliation và nguồn sự thật độc lập**.
