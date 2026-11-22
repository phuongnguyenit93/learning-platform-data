# Khóa tệp, WatchService và tài nguyên theo dõi hệ thống tệp

Ứng dụng Java có thể dùng khóa tệp để phối hợp quyền truy cập giữa nhiều tiến trình và dùng `WatchService` để nhận thông báo khi thư mục hoặc tệp thay đổi. Cả hai tính năng đều dựa vào tài nguyên của hệ điều hành: `FileLock` gắn với một `FileChannel`, còn `WatchService` thường sử dụng cơ chế theo dõi thư mục của nền tảng. Khi ứng dụng chạy với CRaC, không nên giả định các handle native này tiếp tục hợp lệ sau khi tiến trình được khôi phục.

Trong quy trình checkpoint–restore, ứng dụng cần đưa những tài nguyên đó về trạng thái an toàn trước checkpoint, sau đó mở lại khóa và đăng ký lại việc theo dõi sau restore. Với `WatchService`, cần đồng bộ lại nội dung thư mục vì sự kiện có thể phát sinh trong khoảng thời gian watcher đã đóng. Với `FileLock`, cần xử lý khả năng một tiến trình khác đã lấy khóa trong khoảng trống giữa lúc nhả khóa và lúc restore.

## 1. Vì sao phải quản lý file lock và watcher trong CRaC?

Checkpoint lưu trạng thái tiến trình, bao gồm trạng thái Java và những trạng thái runtime có thể phục hồi. Tuy nhiên, các tài nguyên gắn với hệ điều hành hoặc đối tượng bên ngoài tiến trình có vòng đời riêng. Một file descriptor, khóa hệ điều hành hoặc đăng ký theo dõi thư mục không thể được xem như một đối tượng Java thuần túy.

Hai nhóm tài nguyên thường gặp:

| Tài nguyên | Thành phần Java | Việc cần làm trước checkpoint | Việc cần làm sau restore |
|---|---|---|---|
| Khóa tệp | `FileChannel`, `FileLock` | Dừng thao tác đang dùng tệp, nhả khóa và đóng channel | Mở lại channel, thử lấy khóa và xác nhận quyền sở hữu |
| Theo dõi thư mục | `WatchService`, `WatchKey` | Dừng luồng xử lý sự kiện, đóng watcher và bỏ các key cũ | Tạo watcher mới, đăng ký lại thư mục và quét đối soát trạng thái |

Việc chỉ giữ tham chiếu Java tới `FileLock` hoặc `WatchService` trong heap không bảo đảm handle native bên dưới còn dùng được. Hãy coi checkpoint là ranh giới vòng đời: giải phóng tài nguyên trước khi chụp và tạo lại tài nguyên sau khi phục hồi.

## 2. Quản lý khóa tệp bằng `FileChannel` và `FileLock`

Java NIO cung cấp `FileChannel` để đọc, ghi và khóa một vùng của tệp. Gọi `FileChannel.lock()` để yêu cầu khóa có thể chờ, hoặc `tryLock()` để thử lấy khóa ngay. Khi lấy được khóa, ứng dụng nhận một `FileLock` và có thể kiểm tra trạng thái bằng `isValid()`.

Ví dụ cơ bản:

```java
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path lockPath = Path.of("/var/lib/myapp/state.lock");

try (FileChannel channel = FileChannel.open(
        lockPath,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE)) {

    try (FileLock lock = channel.tryLock()) {
        if (lock == null) {
            throw new IllegalStateException("Another process owns the lock");
        }

        // Thực hiện phần công việc cần quyền sở hữu khóa.
    }
}
```

`tryLock()` có thể trả về `null` nếu khóa không lấy được do tiến trình khác đang giữ khóa. Nếu cùng JVM đã giữ một khóa chồng lấn trên vùng tệp đó, API có thể ném `OverlappingFileLockException`. `lock()` có thể chờ cho tới khi lấy được khóa; vì vậy cần cân nhắc việc dùng phương thức chờ trong callback sau restore.

### 2.1. Đặc tính cần nhớ của file lock

- Khóa gắn với channel và vùng byte được khóa. Đóng channel sẽ giải phóng các khóa liên quan.
- Khóa có thể là exclusive hoặc shared, tùy cách mở channel và hỗ trợ của hệ thống tệp.
- Cách hệ điều hành thực thi khóa có thể khác nhau giữa các nền tảng; một số hệ thống dùng khóa advisory. Mọi tiến trình cùng truy cập tệp cần tuân thủ cùng giao thức khóa.
- `FileLock` không phải distributed lock và không thay thế cơ chế điều phối giữa các máy hoặc các hệ thống tệp có semantics khác nhau.
- Sau khi channel bị đóng hoặc khóa bị nhả, đối tượng `FileLock` cũ không thể được dùng như bằng chứng rằng tiến trình vẫn sở hữu khóa.

Đặc biệt, nhả khóa trước checkpoint tạo ra một khoảng thời gian mà tiến trình khác có thể lấy khóa. Sau restore, ứng dụng phải thử lấy khóa lại và xử lý trường hợp khóa đã thuộc về tiến trình khác. Nếu nghiệp vụ đòi hỏi quyền sở hữu liên tục xuyên suốt thời gian checkpoint, file lock không thể tự bảo đảm yêu cầu đó; cần một cơ chế lease hoặc điều phối bên ngoài có fencing token hay giao thức tương đương.

### 2.2. Đóng và lấy lại khóa theo lifecycle CRaC

Một resource có thể quản lý channel và lock. Trong `beforeCheckpoint`, resource nhả khóa và đóng channel. Trong `afterRestore`, resource mở lại tệp và thử lấy khóa mới.

```java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class FileLockResource implements Resource {
    private final Path lockPath;
    private FileChannel channel;
    private FileLock lock;

    public FileLockResource(Path lockPath) throws IOException {
        this.lockPath = lockPath.toAbsolutePath().normalize();
        openAndAcquire();
        Core.getGlobalContext().register(this);
    }

    private synchronized void openAndAcquire() throws IOException {
        channel = FileChannel.open(
                lockPath,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE);
        try {
            lock = channel.tryLock();
            if (lock == null) {
                throw new IOException("File lock is already held: " + lockPath);
            }
        } catch (IOException | RuntimeException e) {
            try {
                channel.close();
            } catch (IOException closeFailure) {
                e.addSuppressed(closeFailure);
            }
            channel = null;
            lock = null;
            throw e;
        }
    }

    private synchronized void releaseAndClose() throws IOException {
        IOException failure = null;

        if (lock != null) {
            try {
                if (lock.isValid()) {
                    lock.release();
                }
            } catch (IOException e) {
                failure = e;
            }
            lock = null;
        }

        if (channel != null) {
            try {
                channel.close();
            } catch (IOException e) {
                if (failure == null) {
                    failure = e;
                } else {
                    failure.addSuppressed(e);
                }
            }
            channel = null;
        }

        if (failure != null) {
            throw failure;
        }
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        releaseAndClose();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        openAndAcquire();
    }
}
```

Đây là ví dụ minh họa cho một khóa độc quyền trên file lock riêng. Trong ứng dụng thực tế, cần bổ sung cách đồng bộ với các luồng nghiệp vụ đang sử dụng tài nguyên, chính sách retry và logging. Nếu không lấy lại được khóa trong `afterRestore`, callback cần báo lỗi để ứng dụng không tiếp tục xử lý như thể vẫn sở hữu khóa.

### 2.3. Chọn chiến lược reacquire

Sau restore, có thể có tiến trình khác đã lấy khóa. Hãy chọn chính sách theo nghiệp vụ:

- **Khóa bắt buộc:** nếu ứng dụng chỉ được phép chạy khi có khóa, `afterRestore` phải thất bại khi không lấy được khóa. Readiness không được bật.
- **Khóa có thể chờ:** có thể dùng `lock()` hoặc vòng lặp retry có deadline, nhưng phải giới hạn thời gian và hỗ trợ hủy khi triển khai dừng.
- **Khóa có thể tranh chấp:** dùng `tryLock()` và chuyển ứng dụng sang trạng thái chờ hoặc standby khi khóa chưa sẵn sàng.
- **Cần bảo đảm ownership xuyên suốt:** dùng dịch vụ lease hoặc cơ chế coordination bên ngoài; không dựa vào việc giữ `FileLock` qua checkpoint.

Không nên retry vô hạn trong callback. Một callback bị treo có thể khiến tiến trình không đạt trạng thái restore hoàn chỉnh. Hãy ghi rõ timeout, số lần thử và hành vi khi thất bại.

### 2.4. Giữ ổn định lock file

Nên dùng một lock file có đường dẫn ổn định và không xóa hoặc thay thế file trong khi các tiến trình có thể đang dùng nó. Trên một số hệ thống tệp, xóa rồi tạo lại lock file có thể tạo ra một đối tượng file khác trong khi tiến trình cũ vẫn đang giữ tham chiếu tới đối tượng cũ. Khi đó hai tiến trình có thể nghĩ rằng chúng đang khóa cùng một tên đường dẫn nhưng thực tế khóa hai đối tượng khác nhau.

Hãy tách file dùng làm lock khỏi file dữ liệu nếu có thể. File lock chỉ dùng để điều phối; dữ liệu nghiệp vụ được ghi qua một giao thức riêng, có xử lý ghi nguyên tử, đồng bộ và phục hồi sau lỗi.

## 3. Theo dõi thay đổi bằng `WatchService`

`WatchService` thuộc Java NIO.2 và cung cấp cơ chế nhận thông báo về sự kiện hệ thống tệp. Ứng dụng tạo watcher bằng `FileSystem.newWatchService()`, đăng ký một thư mục với các loại sự kiện cần theo dõi và đọc sự kiện qua `WatchKey`.

```java
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchService;

Path directory = Path.of("/var/lib/myapp/inbox");

try (WatchService watcher = FileSystems.getDefault().newWatchService()) {
    directory.register(
            watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_MODIFY,
            StandardWatchEventKinds.ENTRY_DELETE);

    // Đọc WatchKey từ watcher và xử lý các event.
}
```

`WatchService` chỉ theo dõi các thư mục đã đăng ký. Đăng ký một thư mục không tự động đăng ký mọi thư mục con. Nếu cần theo dõi cây thư mục, ứng dụng phải duyệt cây và đăng ký từng thư mục, đồng thời đăng ký thêm các thư mục con mới khi phát hiện chúng được tạo.

### 3.1. Xử lý WatchKey và WatchEvent

Một vòng lặp theo dõi điển hình gọi `take()` để chờ key sẵn sàng, đọc các event, sau đó gọi `reset()` để tiếp tục nhận sự kiện:

```java
import java.nio.file.ClosedWatchServiceException;
import java.nio.file.Path;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;

static void processEvents(WatchService watcher) {
    while (true) {
        final WatchKey key;
        try {
            key = watcher.take();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        } catch (ClosedWatchServiceException closed) {
            return;
        }

        for (WatchEvent<?> event : key.pollEvents()) {
            if (event.kind() == java.nio.file.StandardWatchEventKinds.OVERFLOW) {
                // Phải quét lại thư mục để đối soát trạng thái.
                continue;
            }

            Path changedName = (Path) event.context();
            // Ghép changedName với thư mục đã đăng ký tương ứng rồi xử lý.
        }

        if (!key.reset()) {
            // Thư mục không còn được theo dõi qua key này.
            break;
        }
    }
}
```

Trong ứng dụng thật, cần ánh xạ mỗi `WatchKey` tới thư mục đã đăng ký để chuyển `event.context()` thành đường dẫn đầy đủ. Nếu `reset()` trả về `false`, key đã mất hiệu lực; hãy xóa key khỏi registry và quyết định có cần đăng ký lại thư mục nếu nó còn tồn tại hay không.

`OVERFLOW` có nghĩa một số sự kiện có thể đã bị mất. Không được coi event queue là nhật ký đầy đủ. Hãy quét lại trạng thái thư mục hoặc nguồn dữ liệu gốc để đồng bộ.

## 4. Dừng và khởi động lại WatchService qua checkpoint

Một watcher thường có một luồng nền bị chặn trong `WatchService.take()`. Trước checkpoint, cần ngừng nhận công việc mới, đóng watcher để đánh thức luồng đang chờ, chờ luồng kết thúc và xóa registry key cũ. Sau restore, tạo `WatchService` mới, đăng ký lại các thư mục, khởi động luồng mới và đối soát nội dung.

Một resource quản lý watcher có thể có cấu trúc như sau:

```java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.WatchService;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DirectoryWatchResource implements Resource {
    private final Path root;
    private final ConcurrentMap<java.nio.file.WatchKey, Path> directories =
            new ConcurrentHashMap<>();

    private volatile WatchService watcher;
    private volatile Thread worker;
    private volatile boolean stopping;

    public DirectoryWatchResource(Path root) throws IOException {
        this.root = root.toAbsolutePath().normalize();
        startWatching();
        Core.getGlobalContext().register(this);
    }

    private synchronized void startWatching() throws IOException {
        WatchService newWatcher = FileSystems.getDefault().newWatchService();
        try {
            registerTree(root, newWatcher);
        } catch (IOException e) {
            try {
                newWatcher.close();
            } catch (IOException closeFailure) {
                e.addSuppressed(closeFailure);
            }
            directories.clear();
            throw e;
        }

        stopping = false;
        watcher = newWatcher;
        Thread newWorker = new Thread(
                () -> processEvents(newWatcher), "directory-watch-worker");
        newWorker.setDaemon(true);
        worker = newWorker;
        newWorker.start();
    }

    private void registerTree(Path directory, WatchService target)
            throws IOException {
        // Duyệt root và các thư mục con, đăng ký từng thư mục với target.
        // Lưu mỗi WatchKey cùng đường dẫn thư mục vào directories.
    }

    private void processEvents(WatchService source) {
        // Đọc key, xử lý event, reset key và xử lý OVERFLOW.
        // Thoát khi source bị đóng hoặc luồng bị interrupt.
    }

    private void reconcileTree() throws IOException {
        // Quét lại cây thư mục và đồng bộ trạng thái ứng dụng với dữ liệu thật.
    }

    private void stopWatching() throws Exception {
        WatchService oldWatcher;
        Thread oldWorker;
        synchronized (this) {
            stopping = true;
            oldWatcher = watcher;
            watcher = null;
            oldWorker = worker;
            worker = null;
        }

        IOException closeFailure = null;
        if (oldWatcher != null) {
            try {
                oldWatcher.close();
            } catch (IOException e) {
                closeFailure = e;
            }
        }
        if (oldWorker != null) {
            oldWorker.interrupt();
            try {
                oldWorker.join(5_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                if (closeFailure != null) {
                    e.addSuppressed(closeFailure);
                }
                throw e;
            }
            if (oldWorker.isAlive()) {
                IllegalStateException e = new IllegalStateException(
                        "Directory watcher did not stop before checkpoint");
                if (closeFailure != null) {
                    e.addSuppressed(closeFailure);
                }
                throw e;
            }
        }
        directories.clear();
        if (closeFailure != null) {
            throw closeFailure;
        }
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        stopWatching();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        startWatching();
        reconcileTree();
    }
}
```

Các phương thức `registerTree`, `processEvents` và `reconcileTree` được để dưới dạng điểm mở rộng vì logic phụ thuộc cấu trúc thư mục và nghiệp vụ. Khi triển khai, `registerTree` cần đăng ký `ENTRY_CREATE`, `ENTRY_MODIFY` và `ENTRY_DELETE` cho từng thư mục cần theo dõi; `processEvents` cần xử lý `OVERFLOW`, key hết hiệu lực và việc tạo thư mục con mới.

Khi đóng `WatchService`, một luồng đang chờ trong `take()` sẽ được đánh thức bằng `ClosedWatchServiceException`. Luồng xử lý nên coi đây là tín hiệu dừng bình thường khi checkpoint. Việc `join()` bảo đảm luồng không còn xử lý event trước khi JVM chụp trạng thái. Nếu event handler có thể bị chặn lâu, hãy đặt deadline cho việc dừng và làm checkpoint thất bại nếu worker không dừng an toàn.

## 5. Sự kiện có thể bị mất trong khoảng checkpoint

`WatchService` không phải message broker và không bảo đảm lưu mọi sự kiện trong thời gian watcher đóng. Trong khoảng từ `beforeCheckpoint` tới `afterRestore`, tệp có thể được tạo, sửa hoặc xóa. Sau khi đăng ký lại, watcher mới không nhất thiết phát lại các thay đổi đã xảy ra trong khoảng trống đó.

Vì vậy, quy trình phục hồi phải dựa trên trạng thái hiện tại của filesystem:

1. Đóng watcher và dừng event worker trước checkpoint.
2. Sau restore, tạo watcher mới và đăng ký lại các thư mục hiện có.
3. Quét cây thư mục hoặc đọc metadata từ nguồn dữ liệu gốc để xác định trạng thái hiện tại.
4. So sánh với trạng thái ứng dụng đang giữ trong heap và áp dụng thay đổi còn thiếu.
5. Xử lý event mới theo cách idempotent để event phát sinh trong lúc quét không làm cập nhật hai lần gây sai dữ liệu.

Nên đăng ký watcher trước khi quét đối soát. Như vậy, thay đổi phát sinh trong lúc quét có cơ hội được đưa vào event queue; ứng dụng vẫn phải thiết kế thao tác đồng bộ idempotent vì một sự kiện có thể trùng hoặc bị overflow.

Với workload lớn, thay vì giữ một bản sao trạng thái đầy đủ trong heap, có thể dùng snapshot metadata, version, timestamp hoặc cursor nghiệp vụ để xác định phạm vi cần đối soát. Cơ chế chính xác phụ thuộc vào nguồn dữ liệu và semantics của ứng dụng.

## 6. Theo dõi cây thư mục và xử lý thư mục mới

`WatchService` đăng ký theo từng thư mục. Nếu cần theo dõi đệ quy:

- Duyệt cây thư mục ban đầu và đăng ký từng thư mục.
- Khi nhận `ENTRY_CREATE` và đối tượng mới là thư mục, đăng ký thư mục mới cùng các thư mục con đã tồn tại bên trong.
- Khi nhận `ENTRY_DELETE`, xóa registry của các key tương ứng nếu chúng không còn hợp lệ.
- Khi `WatchKey.reset()` trả về `false`, loại key đó khỏi map và kiểm tra thư mục còn tồn tại hay không.
- Sau restore, xây dựng lại toàn bộ registry từ filesystem hiện tại; không tái sử dụng `WatchKey` cũ.

Có thể xảy ra race khi một thư mục được tạo và chứa thêm file trước khi ứng dụng đăng ký watcher cho thư mục mới. Vì vậy, sau khi đăng ký thư mục mới, hãy quét thư mục đó để phát hiện nội dung đã có. Tương tự, nếu provider báo `OVERFLOW`, hãy lên lịch rescan thay vì cố suy luận trạng thái chỉ từ các event còn lại.

## 7. Điều phối nhiều tài nguyên tệp

Một ứng dụng có thể vừa giữ file lock, vừa theo dõi thư mục, vừa có worker xử lý file. Những thành phần này có quan hệ phụ thuộc:

- Worker xử lý file cần watcher để nhận tín hiệu công việc.
- Worker có thể cần file lock trước khi cập nhật trạng thái dùng chung.
- Watcher cần filesystem sẵn sàng trước khi đăng ký.
- Readiness chỉ được bật khi watcher đã đăng ký lại, trạng thái đã được đối soát và các khóa bắt buộc đã được lấy.

Hãy sắp xếp resource theo chiều dependency khi đăng ký với context CRaC: thành phần nền tảng trước consumer. Theo quy tắc callback của global context, `beforeCheckpoint` chạy theo thứ tự đăng ký đảo ngược, còn `afterRestore` chạy theo thứ tự đăng ký. Ví dụ, đăng ký lock và watcher trước worker; khi checkpoint worker dừng trước, còn khi restore lock và watcher được phục hồi trước khi worker hoạt động trở lại.

Không để worker tiếp tục xử lý file trong khi watcher hoặc lock đang ở trạng thái đóng. Có thể dùng một cổng readiness hoặc state machine chung để chuyển ứng dụng qua các trạng thái `RUNNING`, `QUIESCING`, `CHECKPOINT_READY` và `RESTORING`. Mọi thao tác ghi tệp cần kiểm tra trạng thái và phối hợp với lifecycle owner.

## 8. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `FileLock` cũ không còn hợp lệ | Channel đã đóng hoặc lock đã được nhả trước checkpoint | Mở channel mới và lấy lock mới trong `afterRestore` |
| Không lấy lại được lock | Tiến trình khác đã lấy khóa trong khoảng checkpoint | Thực hiện retry có giới hạn hoặc chuyển sang standby/fail restore |
| Hai tiến trình cùng ghi file | Các tiến trình không dùng cùng giao thức khóa hoặc thay thế lock file | Dùng lock file ổn định và thống nhất giao thức khóa |
| Watcher không nhận event sau restore | `WatchService` cũ đã đóng hoặc key cũ không còn hợp lệ | Tạo watcher mới và đăng ký lại tất cả thư mục |
| Thiếu thay đổi phát sinh khi checkpoint | Không có watcher hoạt động trong khoảng đó | Quét đối soát filesystem sau restore |
| Watcher dừng nhưng thread vẫn chạy | Event handler bị chặn hoặc không thoát khi service đóng | Đóng service, interrupt, join có deadline và fail checkpoint nếu không dừng |
| Bỏ sót thư mục con mới | Chỉ đăng ký thư mục gốc | Đăng ký đệ quy và đăng ký thêm thư mục khi nhận create event |
| Xử lý file hai lần | Event trùng hoặc vừa rescan vừa nhận event mới | Thiết kế xử lý idempotent và đối soát theo version |

Một lỗi thiết kế khác là mở lại watcher trong constructor của ứng dụng sau restore. Restore không chạy lại `main()` như một lần khởi động mới, vì vậy logic phục hồi tài nguyên phải nằm trong callback `afterRestore` hoặc lifecycle được CRaC gọi, không chỉ nằm trong startup path ban đầu.

## 9. Kiểm thử checkpoint–restore cho tài nguyên hệ thống tệp

Nên kiểm thử cả hành vi bình thường lẫn tình huống cạnh tranh:

1. Khởi động ứng dụng, xác nhận lock đã được lấy và watcher đã đăng ký các thư mục cần thiết.
2. Ghi log thời điểm resource nhận `beforeCheckpoint`; xác nhận worker đã dừng, lock được nhả, channel được đóng và watcher đã đóng.
3. Tạo checkpoint bằng runtime CRaC mục tiêu.
4. Trong khoảng checkpoint, thử tạo, sửa và xóa tệp bằng một tiến trình khác để mô phỏng thay đổi ngoài ứng dụng.
5. Restore ứng dụng; xác nhận channel mới được mở, lock được lấy lại theo chính sách, watcher mới được tạo và thư mục được đăng ký lại.
6. Xác nhận bước reconcile phát hiện các thay đổi trong khoảng watcher ngừng hoạt động.
7. Gửi thêm sự kiện mới sau restore và kiểm tra worker xử lý đúng một cách idempotent.
8. Chạy tình huống tiến trình khác giữ lock trong lúc restore để xác nhận ứng dụng không giả định rằng lock luôn sẵn sàng.
9. Lặp lại nhiều chu kỳ checkpoint/restore để phát hiện thread watcher bị nhân đôi, key cũ còn trong registry hoặc channel bị rò rỉ.

Khi đo hiệu năng, tách thời gian phục hồi JVM, thời gian lấy lại khóa, thời gian đăng ký watcher, thời gian quét đối soát và thời gian đạt readiness. Việc tách các mốc giúp xác định bước nào đang chi phối thời gian ứng dụng sẵn sàng.

## 10. Checklist triển khai

- [ ] Mỗi `FileChannel` và `FileLock` được quản lý bởi một resource CRaC rõ ràng.
- [ ] `beforeCheckpoint` dừng thao tác đang dùng tệp, nhả khóa và đóng channel.
- [ ] `afterRestore` mở channel mới và lấy khóa mới theo chính sách timeout/retry.
- [ ] Ứng dụng xử lý trường hợp tiến trình khác đã lấy khóa trong khoảng checkpoint.
- [ ] Lock file có đường dẫn ổn định và không bị xóa hoặc thay thế khi đang sử dụng.
- [ ] Watcher được đóng và worker thread đã kết thúc trước checkpoint.
- [ ] `afterRestore` tạo `WatchService` mới và đăng ký lại các thư mục.
- [ ] WatchKey cũ được loại bỏ; không dùng key từ trước checkpoint.
- [ ] Có xử lý `OVERFLOW`, key invalid và thư mục con mới.
- [ ] Có bước rescan/reconcile để bù các sự kiện phát sinh khi watcher đóng.
- [ ] Event handler idempotent và không xử lý song song gây sai trạng thái.
- [ ] Readiness chỉ bật sau khi lock, watcher và dữ liệu đã sẵn sàng.
- [ ] Đã thử restore trong tình huống có tiến trình khác tranh chấp khóa và có thay đổi filesystem.

## 11. Tài liệu tham khảo

- [Java NIO `FileLock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileLock.html): trạng thái, vùng khóa, shared/exclusive lock và đặc tính phụ thuộc nền tảng.
- [Java NIO `FileChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): mở channel, `lock()`, `tryLock()` và vòng đời channel.
- [Java NIO `WatchService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchService.html): tạo watcher, `take()` và đóng service.
- [Java NIO `WatchKey`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchKey.html): event queue, `reset()` và trạng thái key.
- [CRaC API — `Resource`](https://javadoc.io/doc/org.crac/crac/latest/org/crac/Resource.html): callback trước checkpoint và sau restore.

Khóa tệp và `WatchService` đều gắn với tài nguyên hệ thống tệp có vòng đời riêng. Trong CRaC, hãy nhả file lock và đóng channel trước checkpoint, rồi mở lại và xác nhận quyền sở hữu sau restore. Với watcher, hãy dừng worker, đóng service, tạo watcher mới và đăng ký lại thư mục sau restore. Vì sự kiện có thể bị mất trong khoảng watcher ngừng hoạt động, luôn đối soát trạng thái filesystem trước khi cho worker tiếp tục xử lý.
