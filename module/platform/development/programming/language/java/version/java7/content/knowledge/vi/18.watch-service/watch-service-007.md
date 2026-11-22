# `WatchService` trong Java: Đăng ký từng thư mục khi theo dõi cả cây

## 1. Bài toán: theo dõi một thư mục không tự động theo dõi tất cả thư mục con

Một dịch vụ Java theo dõi thư mục `project/` để cập nhật chỉ mục, tạo thumbnail, kiểm tra tệp cấu hình hoặc xử lý file mới. Cây thư mục có thể như sau:

```text
project/
├── README.md
├── src/
│   ├── Main.java
│   └── app/
│       └── Config.java
├── docs/
│   └── guide.md
└── uploads/
    └── incoming/
```

Nếu chỉ gọi:

```java
WatchKey key = root.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);
```

thì ta đăng ký **một thư mục `root`**, không đăng ký tự động `src`, `src/app`, `docs` hay `uploads/incoming`. Sự kiện tạo `project/src/app/New.java` là thay đổi của entry **nằm trực tiếp trong `src/app`**; không được mặc định kỳ vọng registration ở `project` sẽ nhận sự kiện đó.

**Muốn theo dõi cả cây bằng API `WatchService` chuẩn của Java, phải quản lý việc đăng ký từng thư mục.** Thuật toán gồm:

1. Đi qua cây ban đầu bằng `Files.walkFileTree(root, visitor)` và gọi `dir.register(watcher, ...)` cho **mỗi thư mục có thật**.
2. Lưu ánh xạ `WatchKey → Path` để biết sự kiện đến từ thư mục nào.
3. Khi `ENTRY_CREATE` báo một entry là **thư mục mới**, đăng ký **toàn bộ cây con** của entry đó, không chỉ một cấp.
4. Đối soát/scan các nội dung đã xuất hiện trong thư mục mới **trước khi watcher kịp đăng ký**; việc chỉ register không phát lại những sự kiện trong quá khứ.
5. Gọi `key.pollEvents()`, xử lý `OVERFLOW`, rồi `key.reset()`; khi key invalid thì loại bỏ mapping.
6. Dừng và đóng `WatchService` đúng vòng đời; quét lại trạng thái khi có race hoặc thông báo bị mất.

`WatchService` và `Files.walkFileTree` đều là NIO.2 có từ Java 7 và **vẫn được sử dụng trong Java 17+**. Ví dụ độc lập trong bài dùng JDK 17+ và một filesystem mặc định có khả năng báo event; các giới hạn provider và đồng thời được trình bày rõ.

### 1.1. Đăng ký event khác với duyệt cây

`Files.walkFileTree` cho ứng dụng **đi qua những thư mục đang tồn tại** ở thời điểm duyệt. `WatchService` cho ứng dụng **nhận tín hiệu thay đổi sau khi đăng ký**. Không API nào riêng lẻ tạo một snapshot nhất quán của cây trong lúc các tiến trình khác tiếp tục ghi dữ liệu.

Vì vậy, hệ thống theo dõi cây bền vững thường có ba thành phần:

```text
Cây tệp đã tồn tại
      |
Duyệt và đăng ký từng thư mục  ->  WatchService + Map<WatchKey, Path>
      |                                   |
Quét trạng thái ban đầu                  event loop
      |                                   |
      +-----------> Đối soát <-------------+
                      |
               Chỉ mục / nghiệp vụ
```

**Thông điệp chính:** watcher là **nguồn tín hiệu**, còn trạng thái thật của filesystem cùng cơ chế quét/đối soát mới giúp ứng dụng khôi phục khi bỏ sót event.

## 2. Các API cần hiểu

| API | Trách nhiệm | Không tự làm |
| --- | --- | --- |
| `FileSystem.newWatchService()` | Tạo dịch vụ theo dõi của provider | Không đăng ký bất cứ thư mục nào |
| `Path.register(watcher, kinds...)` | Đăng ký **một thư mục** cho các loại event | Không tự đăng ký tất cả hậu duệ |
| `Files.walkFileTree(root, visitor)` | Duyệt cây thư mục | Không liên tục theo dõi sau khi hoàn tất |
| `WatchKey` | Đại diện một registration | Không chứa nội dung file hoàn chỉnh |
| `WatchService.take()/poll()` | Nhận key đã báo hiệu | Không trả một `WatchEvent` riêng lẻ |
| `WatchKey.pollEvents()` | Lấy event được tích lũy trên key | Không phục hồi event đã mất vì overflow |
| `WatchKey.reset()` | Cho key sẵn sàng nhận/lên queue lần sau | Không đăng ký lại key invalid |
| `WatchEvent.context()` | Đường dẫn tương đối của entry thay đổi đối với thư mục được watch | Không phải path tuyệt đối/an toàn để mở |
| `WatchKey.cancel()` | Hủy một registration | Không đóng toàn bộ watcher |
| `WatchService.close()` | Đóng watcher, invalid các key và đánh thức threads chờ | Không tự đồng bộ index dữ liệu |

### 2.1. Khởi tạo watcher thuộc đúng FileSystem

```java
Path root = Path.of("project").toAbsolutePath().normalize();

try (WatchService watcher =
        root.getFileSystem().newWatchService()) {
    // Register và xử lý các directory ở đây.
}
```

Đây là **mã minh họa bên trong một phương thức** có xử lý `IOException`. Trước khi sử dụng, `root` phải là thư mục hợp lệ đã tồn tại. `Path.of` có từ Java 11; chương trình đầy đủ dùng Java 17+.

Không tự động giả định watcher tạo bằng `FileSystems.getDefault()` sẽ dùng được cho một `Path` thuộc ZIP filesystem hoặc provider không mặc định.

### 2.2. Các event standard

```java
import static java.nio.file.StandardWatchEventKinds.*;

WatchKey key = directory.register(
        watcher,
        ENTRY_CREATE,
        ENTRY_MODIFY,
        ENTRY_DELETE);
```

Các loại:

- `ENTRY_CREATE`: một entry được tạo hoặc được đưa/rename **vào** thư mục đã đăng ký.
- `ENTRY_MODIFY`: entry trong thư mục đã được sửa; không nói file đã ghi xong.
- `ENTRY_DELETE`: entry bị xóa hoặc được đưa/rename **ra khỏi** thư mục.
- `OVERFLOW`: implementation đã loại bỏ hoặc không giữ đầy đủ một số event; event này **được hỗ trợ ngầm** và không cần truyền vào `register`.

Theo API Java, registration với cùng watchable và watch service có thể trả lại **key đang đăng ký** sau khi cập nhật tập event, không nhất thiết tạo một key mới mỗi lần. Vì vậy, khi xây bộ quản lý registration, phải hiểu và xử lý việc đăng ký lặp.

### 2.3. `WatchKey.watchable()` và mapping

`WatchKey.watchable()` trả object được đăng ký, thường là `Path` của thư mục. Tuy nhiên, với một watcher quản lý nhiều thư mục, lưu map **`Map<WatchKey, Path>`** là cách tiện lợi để:

- Xác định thư mục gốc của `event.context()`.
- Quản lý số registration còn hoạt động.
- Loại key đã invalid khỏi dữ liệu nội bộ.
- Kết hợp với map ngược `Map<Path, WatchKey>` để tránh việc đăng ký thừa.

**Cần nhớ:** nếu thư mục bị di chuyển/đổi tên, API không bảo đảm key luôn bị hủy ngay; `watchable()` có thể không còn là path hợp lệ của đối tượng cũ. Map không phải cơ chế bảo vệ trước rename/race. Cần đối soát filesystem thật.

## 3. Bước thứ nhất: đăng ký tất cả thư mục đang tồn tại

### 3.1. Dùng `Files.walkFileTree` với `preVisitDirectory`

```java
static void registerTree(
        Path start,
        WatchService watcher,
        Map<WatchKey, Path> directories) throws IOException {

    Files.walkFileTree(
            start,
            new SimpleFileVisitor<Path>() {
                @Override
                public FileVisitResult preVisitDirectory(
                        Path dir, BasicFileAttributes attrs)
                        throws IOException {

                    WatchKey key = dir.register(
                            watcher,
                            StandardWatchEventKinds.ENTRY_CREATE,
                            StandardWatchEventKinds.ENTRY_MODIFY,
                            StandardWatchEventKinds.ENTRY_DELETE);

                    directories.put(key, dir);
                    return FileVisitResult.CONTINUE;
                }
            });
}
```

Đây là **phương thức minh họa** cần import `java.nio.file.*`, `BasicFileAttributes`, `java.util.Map` và `IOException`.

`preVisitDirectory` được gọi trước khi duyệt các entry bên trong thư mục. Đó là vị trí thích hợp để **đăng ký watcher trước khi tiếp tục đi vào cây con**, giảm khoảng thời gian thư mục tồn tại nhưng chưa được đăng ký.

Với cây:

```text
root/
├── existing/
│   └── inner/
└── README.md
```

Visitor đăng ký đúng **3 thư mục**: `root`, `existing` và `inner`. `README.md` là file thường, không phải directory nên không có registration riêng.

### 3.2. Vì sao không đăng ký trong `visitFile`?

`visitFile` trong mô hình duyệt mặc định xử lý các entry không phải thư mục đang được đi vào, bao gồm regular files hoặc symbolic links. `WatchService` chuẩn theo dõi **entry changes trong thư mục**, không yêu cầu đăng ký watcher riêng cho từng regular file.

Đặt `register` ở `preVisitDirectory` giúp phân biệt điều muốn theo dõi là **directory containing entries**, không phải mỗi file.

### 3.3. Vì sao chưa thể coi “đã duyệt hết” là “không bỏ sót event”?

Có khoảng trống thời gian:

```text
T0: Chưa đăng ký /src
T1: file được tạo trong /src
T2: ứng dụng đăng ký /src
T3: ứng dụng kết thúc traversal
```

Event tại T1 có thể **không được phát lại** vì khi đó watcher chưa theo dõi `/src`. Ngay cả khi đăng ký `preVisitDirectory`, một entry có thể xuất hiện/biến mất giữa thời điểm directory được liệt kê và đăng ký.

Cách thiết kế: **sau khi đăng ký, scan trạng thái file thực tế** theo phạm vi đã được phép, đối chiếu với chỉ mục và tiếp tục tiêu thụ events; nếu cần nhất quán nghiêm ngặt, cần snapshot/version/coordination ở tầng lưu trữ.

Không khẳng định `walkFileTree` hoặc WatchService có tính atomic toàn cây.

## 4. Bước thứ hai: lưu map để xác định thư mục của mỗi event

### 4.1. Tại sao key → directory là bắt buộc trong nhiều registrations?

Khi watcher trả `WatchKey`, nó không tự đưa ra một `Path` tuyệt đối cho từng event. Với ba thư mục:

```text
keyRoot   -> root/
keySrc    -> root/src/
keyDocs   -> root/docs/
```

Giả sử `event.context()` là `report.txt`. Tệp đó có thể là:

- `root/report.txt` nếu key là `keyRoot`.
- `root/src/report.txt` nếu key là `keySrc`.
- `root/docs/report.txt` nếu key là `keyDocs`.

Vì vậy map giúp xác định **đúng nơi phát sinh sự kiện**.

```java
Map<WatchKey, Path> dirsByKey = new HashMap<>();

WatchKey key = directory.register(
        watcher, StandardWatchEventKinds.ENTRY_CREATE);

dirsByKey.put(key, directory);
```

Đây là mã minh họa; các biến cần có sẵn trong phương thức.

### 4.2. Ghép context với directory

```java
WatchKey key = watcher.take();
Path parent = dirsByKey.get(key);

for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        // Đánh dấu cần quét lại. Không cast context.
        continue;
    }

    Path relativeName = (Path) event.context();
    Path affected = parent.resolve(relativeName);

    // Kiểm tra thay đổi tại affected theo kind.
}

boolean valid = key.reset();
if (!valid) {
    dirsByKey.remove(key);
}
```

Đây là mã minh họa nằm trong một vòng nhận nhiều key; cần bảo vệ trường hợp `parent == null`, xử lý interrupted/closed watcher và quy trình rescan phù hợp.

**Quan trọng:**

- `event.context()` cho các event entry chuẩn là **relative Path**, thường là tên entry trực tiếp.
- `OVERFLOW` có context phụ thuộc provider, có thể `null`; không cast nó thành `Path`.
- Sau khi ghép, entry có thể **đã biến mất hoặc bị đổi thành symlink**; xử lý I/O không thể dựa duy nhất vào event.
- `Path.normalize()`/`startsWith(root)` chỉ kiểm tra cấu trúc lexical, không chống được mọi symlink/path race.

### 4.3. Map ngược path → key tránh đăng ký trùng

Nếu app thấy một event `ENTRY_CREATE` cho directory nhưng trước đó đã đăng ký subtree đó do quét đối soát, việc register lại không nhất thiết tạo key mới; một số provider dùng lại key và cập nhật event kinds.

Một lớp quản lý thực tế có thể giữ:

```java
Map<WatchKey, Path> dirsByKey = new HashMap<>();
Map<Path, WatchKey> keysByDir = new HashMap<>();
```

Trước khi đăng ký directory, kiểm tra:

```java
WatchKey old = keysByDir.get(directory);

if (old == null || !old.isValid()) {
    WatchKey next = directory.register(
            watcher, ENTRY_CREATE, ENTRY_MODIFY, ENTRY_DELETE);
    keysByDir.put(directory, next);
    dirsByKey.put(next, directory);
}
```

Đây là mã minh họa trong method có các import static phù hợp. Đối với input không tin cậy/multi-thread, cần thêm đồng bộ và kiểm tra các path alias hoặc rename; map theo `Path.equals` không phải cơ chế nhận biết object filesystem tuyệt đối.

## 5. Bước thứ ba: gặp thư mục mới thì đăng ký cả subtree của nó

### 5.1. Không chỉ đăng ký một cấp

Nếu `root` đang được watch và một tiến trình khác **di chuyển một thư mục có sẵn** chứa các thư mục con vào root:

```text
Trước sự kiện:
root/
└── existing/

Nguồn được đưa tới:
incoming/
├── deep/
│   └── existing.txt
└── other/

Sau rename/move:
root/
├── existing/
└── incoming/
    ├── deep/
    │   └── existing.txt
    └── other/
```

WatchService ở `root` có thể phát `ENTRY_CREATE` cho entry `incoming`, nhưng **không hứa** nó sẽ phát lại `ENTRY_CREATE` cho `incoming/deep` hoặc `incoming/deep/existing.txt`.

Nếu handler chỉ gọi `incoming.register(watcher,...)`, các thư mục `deep` và `other` vẫn **chưa được đăng ký**. File mới trong `deep` sau đó có thể bị bỏ qua.

Vì vậy, khi nhận một `ENTRY_CREATE` và entry hiện là directory:

```java
if (kind == StandardWatchEventKinds.ENTRY_CREATE
        && Files.isDirectory(
                affected, LinkOption.NOFOLLOW_LINKS)) {

    registerTree(affected); // Duyệt từ directory mới xuống toàn bộ subtree.
    needsReconciliation = true;
}
```

Đây là minh họa; `registerTree` và `needsReconciliation` là các thành phần do ứng dụng xây dựng.

### 5.2. Vì sao phải đối soát trạng thái sau khi đăng ký?

Ngay cả với việc đăng ký toàn bộ subtree, các file đã tồn tại trước lúc register **không phát lại sự kiện tạo file từ quá khứ**. Ví dụ `incoming/deep/existing.txt` đã ở đó khi subtree được chuyển vào.

Đăng ký để **theo dõi thay đổi từ bây giờ**, đồng thời scan subtree để **nhận biết trạng thái đã có**:

```java
registerTree(incoming);
List<Path> currentFiles;

try (var paths = Files.walk(incoming)) {
    currentFiles = paths
            .filter(p -> Files.isRegularFile(
                    p, LinkOption.NOFOLLOW_LINKS))
            .toList();
}
```

Đây là đoạn minh họa Java 17+ trong phương thức có xử lý `IOException`. `Files.walk` trả stream cần đóng; trong cây lớn không nhất thiết gom toàn bộ vào `List` mà có thể xử lý trực tiếp theo visitor.

**Khác biệt giữa các kết quả:**

- Register thành công: thư mục có registration.
- Scan thành công: có một danh sách những file tồn tại tại thời điểm quét.
- Chưa phải bảo đảm snapshot toàn cây và chưa nói các event đến đồng thời đã được xử lý không trùng/không thiếu.

### 5.3. Race khi directory mới biến mất

`ENTRY_CREATE` chỉ nói event đã xảy ra **trong quá khứ tương đối với lúc handler đọc**. Directory có thể bị xóa hoặc chuyển đi ngay trước khi `Files.isDirectory` hay `registerTree` chạy.

Các tình huống:

- `Files.isDirectory(..., NOFOLLOW_LINKS)` trả false vì entry đã biến mất.
- `walkFileTree` ném `NoSuchFileException`/`IOException` do subtree thay đổi giữa chừng.
- `register` thất bại vì quyền hoặc provider.
- Thư mục là symbolic link thay vì directory thật.
- Filesystem bị unmount/remount và key không còn hợp lệ.

Không được nuốt lỗi rồi báo “theo dõi đầy đủ”. Ứng dụng nên đánh dấu state **cần reconciliation**, retry có giới hạn hoặc báo trạng thái partial/failed theo contract.

## 6. Bước thứ tư: nhận event bằng vòng lặp và reset đúng lúc

### 6.1. Vòng nhận chuẩn

```java
for (;;) {
    WatchKey key = watcher.take();
    Path watchedDirectory = dirsByKey.get(key);

    try {
        for (WatchEvent<?> event : key.pollEvents()) {
            if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                // Cần quét lại trạng thái.
                continue;
            }

            Path affected = watchedDirectory.resolve(
                    (Path) event.context());

            if (event.kind() == StandardWatchEventKinds.ENTRY_CREATE
                    && Files.isDirectory(
                            affected, LinkOption.NOFOLLOW_LINKS)) {
                registerTree(affected);
            }
        }
    } finally {
        if (!key.reset()) {
            dirsByKey.remove(key);
        }
    }
}
```

Đây là **mã minh họa**, chưa phải một vòng dịch vụ production hoàn chỉnh. Nó giả định biến `dirsByKey`, `watcher`, `registerTree` tồn tại; cần xử lý `watchedDirectory == null`, shutdown, overflow, transient I/O, stopped flag và các loại event khác.

`WatchService.take()` **chờ khi hàng đợi rỗng**. `poll()` trả `null` ngay nếu rỗng; `poll(timeout, TimeUnit)` chờ tối đa một khoảng. Cả ba trả **WatchKey**, không trả từng `WatchEvent`. Chọn theo mô hình worker của ứng dụng, không quay vòng `poll()` không ngủ dẫn tới busy-wait.

### 6.2. Một key có thể có nhiều event

`key.pollEvents()` lấy **danh sách các event đang tích lũy**, không bảo đảm đúng một event cho mỗi lần `take()`. Nếu file liên tục bị sửa, `ENTRY_MODIFY` có thể được gộp. Thứ tự và độ trễ event phụ thuộc provider.

Do đó, vòng lặp cần duyệt hết `pollEvents()`, xử lý `OVERFLOW` rồi gọi `key.reset()` **sau khi xử lý**. Nếu có nhiều consumer threads, `reset` phải được phối hợp để tránh hai thread xử lý cùng một registration tại cùng thời điểm.

### 6.3. `reset()` trả false: loại registration invalid

`WatchKey` có thể trở nên invalid vì:

- Ứng dụng gọi `key.cancel()`.
- Directory được watch không còn truy cập được.
- `WatchService` bị đóng.

`key.reset()` trả `false` khi registration không còn hợp lệ. Khi đó loại mapping khỏi `dirsByKey` và `keysByDir`.

**Nếu một key invalid, không nhất thiết phải đóng toàn bộ watcher:** các thư mục khác có thể vẫn đang được theo dõi. Nhưng nếu root không còn truy cập được, sản phẩm có thể phải dừng toàn bộ watch tree theo policy.

### 6.4. Watch key bị cancel có thể vẫn ở queue

Theo `WatchService` API, một key đã được queue trước khi `cancel()` **có thể vẫn nằm trong queue** cho tới khi consumer lấy nó. Do vậy không suy rằng cancel làm queue trống ngay hoặc map không bao giờ nhận key invalid.

Kiểm tra `key.isValid()` và kết quả `reset()`; không dùng một key invalid như registration đang hoạt động.

## 7. Sự kiện `OVERFLOW` không được bỏ qua

`OVERFLOW` xảy ra khi provider biết đã mất hoặc phải bỏ một số event do giới hạn hàng đợi/khả năng tiêu thụ. Khi đó, bộ lập chỉ mục có thể không còn đồng bộ với trạng thái thật của cây.

Với watcher theo dõi hàng ngàn thư mục, việc xử lý nghiệp vụ rất lâu trong event thread làm rủi ro mất event tăng lên.

### 7.1. Đánh dấu cần đối soát, không chỉ tiếp tục im lặng

```java
if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
    dirty = true;
    scheduleFullReconciliation();
    continue;
}
```

Đây là **pseudocode Java minh họa**; `dirty` và `scheduleFullReconciliation()` không thuộc JDK, cần được triển khai theo kiến trúc ứng dụng.

Một quy trình recovery đầy đủ có thể:

1. Đánh dấu toàn bộ phạm vi liên quan **có thể thiếu event**.
2. Tạo lịch scan hiện trạng directory tree từ root được phép.
3. Đăng ký lại những thư mục mới chưa có registration, đồng thời loại mappings không còn hợp lệ.
4. Xây lại hoặc đối chiếu index các file hiện tại với dữ liệu cũ.
5. Trong lúc scan, tiếp tục lưu/tiêu thụ events mới để giảm rủi ro chồng lấn.
6. Chỉ đánh dấu index “đã đồng bộ” khi quy trình reconciliation thành công theo contract.

**Chỉ gọi `registerTree(root)` khi OVERFLOW là chưa đủ để khôi phục các event tạo/xóa/sửa file đã bị mất.** Phải có bước quét trạng thái file thực tế.

### 7.2. Event ENTRY_DELETE không đủ để biết cả subtree đã biến mất

Nếu xóa hoặc move cả một directory được watch, có thể phát event delete ở cha, các keys con lần lượt invalid, hoặc một số event không tới như mong đợi tùy provider.

Với index cây, không chỉ loại entry cha khỏi map; cần:

- Xác định đường dẫn subtree trong index.
- Dọn các registration liên quan theo thực trạng.
- Đồng bộ lại các entries của subtree.
- Xử lý trường hợp directory đã bị tạo lại với cùng tên.

Đặc biệt trong hệ thống có symlink/rename, path theo từ vựng có thể không đại diện cho object filesystem trước đó.

## 8. Bảo mật: không tự follow symlink khi duyệt cây được watch

### 8.1. Mặc định `walkFileTree` không theo symlink

`Files.walkFileTree(start, visitor)` mặc định **không dùng `FileVisitOption.FOLLOW_LINKS`**, nên không tự đi theo symbolic links tới các thư mục bên ngoài.

Ví dụ:

```text
root/
├── own/
└── link-to-outside -> /private/other/
```

Nếu code cho phép follow symlink một cách vô điều kiện, ứng dụng có thể bắt đầu watch hoặc đọc dữ liệu **ngoài root đã được cấp quyền**, hoặc gặp vòng lặp symlink.

Với môi trường không tin cậy, nên định nghĩa rõ:

- Root đã được ứng dụng xác minh và cấp quyền.
- Có theo symbolic link hay không.
- Có cho phép mount points bên trong root không.
- Có giới hạn độ sâu/số directory không.
- Có kiểm tra race giữa lúc `isDirectory` và `register` không.
- Có cần cơ chế chống path traversal hoặc thay đổi component của path không.

### 8.2. `NOFOLLOW_LINKS` và lexical checks không phải sandbox tuyệt đối

`Files.isDirectory(path, NOFOLLOW_LINKS)` là cách tránh tự follow **entry cuối** nếu nó là link. `Path.normalize()` và `startsWith(root)` kiểm tra quan hệ **lexical** của path.

Nhưng các component trung gian có thể là symlink hoặc bị thay đổi đồng thời, mount alias có thể làm path logic khác path vật lý. Với security boundary thật, cần quyền OS, trusted root, kiểm soát quyền người tạo file và cơ chế chống race theo provider nếu có.

**Không tự xem một `ENTRY_CREATE` là quyền hợp lệ để mở bất cứ file nào được báo.** Kiểm tra authorization và trạng thái filesystem ở thời điểm sử dụng.

### 8.3. Root là symbolic link

Nếu chương trình muốn bảo đảm chỉ watch cây thư mục mà ứng dụng sở hữu, có thể yêu cầu root là directory **thật**, dùng:

```java
if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) {
    throw new IOException("Root is not a real directory");
}
```

Đây là chính sách lựa chọn, không phải quy tắc bắt buộc của mọi watcher. Một số ứng dụng cho phép root là symlink có chủ đích, nhưng phải giải quyết đường vật lý, ownership, rename/race rõ ràng.

## 9. Kiểm soát tài nguyên: số directory có thể rất lớn

Mỗi registration có thể tiêu tốn tài nguyên OS hoặc provider. Một cây chứa 500.000 thư mục không nhất thiết phù hợp để đăng ký từng entry mà không có giới hạn.

### 9.1. Đặt giới hạn và quan sát

Một dịch vụ có thể theo dõi:

- Số `WatchKey` còn hiệu lực.
- Số directories đã đăng ký.
- Tốc độ event/giây và hàng đợi công việc.
- Số lần `OVERFLOW`.
- Số lần registration thất bại.
- Độ trễ xử lý event.
- Số lần scan/reconcile đang chạy.
- Số paths bị bỏ qua vì quyền/symlink/quota.

Đây là các metric **do ứng dụng xây dựng**, không phải metric `WatchService` tự cung cấp dưới đúng tên đó.

### 9.2. Không chạy xử lý file lớn trong event thread

Khi watcher nhận event `ENTRY_CREATE` cho file dung lượng GB, không nên mở/parse toàn bộ file ngay trong vòng nhận key nếu điều đó khiến consumer bị chặn lâu.

Tách:

```text
WatchService receiver (nhanh)
       |
Phân loại event, xác định Path, đánh dấu dirty khi cần
       |
Hàng đợi có giới hạn / executor
       |
File processing workers (có quota, retry, file-ready protocol)
       |
Index/storage update
```

Nếu queue công việc đầy, phải có chính sách backpressure hoặc đánh dấu cần reconciliation; không được bỏ âm thầm sự kiện quan trọng.

### 9.3. Đăng ký lặp và memory leak

Nếu mỗi event MODIFY đều gọi `directory.register` mà không kiểm tra map, ứng dụng có thể làm map nội bộ phình không cần thiết, hoặc thay đổi event set ngoài ý muốn. Dùng `keysByDir`, kiểm tra `isValid`, và loại các mappings invalid khi `reset()` trả false hoặc sau scan.

Cũng cần dọn state khi thư mục không còn tồn tại. Việc Java tự invalidate một số keys không đồng nghĩa ứng dụng tự xóa mọi entry khỏi `HashMap`.

## 10. Chương trình Java 17+ đầy đủ: đăng ký cây hiện có và subtree mới

Ví dụ này tạo toàn bộ dữ liệu trong **thư mục tạm riêng do chương trình sở hữu**, không chỉnh sửa dự án hiện có. Chương trình chứng minh các tình huống:

1. Ban đầu có ba directories: `root`, `existing`, `existing/inner`. Việc register bằng `walkFileTree` tạo **3 registrations**.
2. Một file mới được tạo trong thư mục **`existing/inner`** sau registration; watcher nhận được `ENTRY_CREATE` đúng ở thư mục sâu.
3. Một cây mới `incoming/deep` với file `already.txt` được tạo **trước khi consumer xử lý event của root**. Chỉ cần thấy `ENTRY_CREATE` cho `incoming`, code đăng ký **toàn bộ subtree**, nên có tổng cộng **5 directories**.
4. `already.txt` không được giả định sẽ có event tạo file sau khi đăng ký. Chương trình **scan trạng thái hiện tại** của subtree, xác nhận file đã có.
5. Sau khi đăng ký subtree, một file `incoming/deep/next.txt` được tạo; watcher nhận được event ở thư mục mới đăng ký.
6. Cờ `needsReconciliation` bật khi subtree mới xuất hiện, nhấn mạnh registration chưa phải đồng bộ index đầy đủ.
7. Sau khi watcher đóng, các keys đã đăng ký đều invalid.
8. Workspace riêng được dọn trong `finally`.

**Giới hạn kiểm thử:** Sự kiện WatchService phụ thuộc filesystem provider. Ví dụ được biên dịch và chạy trên một filesystem thử nghiệm thực hỗ trợ thông báo sự kiện; với provider không hỗ trợ hoặc phát hiện chậm, `poll(timeout)` có thể hết hạn và test báo lỗi thay vì khẳng định thành công giả. Đây là **integration demo**, không phải bảo đảm mọi OS/network share phát event theo cùng độ trễ.

Tạo tệp **`RecursiveWatchRegistrationDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.concurrent.TimeUnit;

import static java.nio.file.StandardWatchEventKinds.*;

public final class RecursiveWatchRegistrationDemo {

    static void check(boolean value, String detail) {
        if (!value) throw new AssertionError(detail);
    }

    static int countRegularFiles(Path root) throws IOException {
        final int[] count = {0};

        Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs) {
                if (attrs.isRegularFile()) count[0]++;
                return FileVisitResult.CONTINUE;
            }
        });

        return count[0];
    }

    static final class TreeWatcher implements AutoCloseable {
        final Path root;
        final WatchService service;
        final Map<WatchKey, Path> dirsByKey = new HashMap<>();
        final Map<Path, WatchKey> keysByDir = new HashMap<>();
        boolean needsReconciliation;

        TreeWatcher(Path root) throws IOException {
            this.root = root.toAbsolutePath().normalize();

            if (!Files.isDirectory(
                    this.root, LinkOption.NOFOLLOW_LINKS)) {
                throw new IOException("Root is not an ordinary directory");
            }

            service = this.root.getFileSystem().newWatchService();

            try {
                registerTree(this.root);
            } catch (IOException | RuntimeException error) {
                try {
                    service.close();
                } catch (IOException closeError) {
                    error.addSuppressed(closeError);
                }
                throw error;
            }
        }

        void registerTree(Path start) throws IOException {
            if (!start.toAbsolutePath().normalize().startsWith(root)) {
                throw new IOException(
                        "Subtree escapes the declared root");
            }

            Files.walkFileTree(
                    start,
                    new SimpleFileVisitor<Path>() {
                        @Override
                        public FileVisitResult preVisitDirectory(
                                Path directory,
                                BasicFileAttributes attrs)
                                throws IOException {

                            WatchKey oldKey = keysByDir.get(directory);

                            if (oldKey == null || !oldKey.isValid()) {
                                WatchKey key = directory.register(
                                        service,
                                        ENTRY_CREATE,
                                        ENTRY_MODIFY,
                                        ENTRY_DELETE);

                                keysByDir.put(directory, key);
                                dirsByKey.put(key, directory);
                            }

                            return FileVisitResult.CONTINUE;
                        }
                    });
        }

        boolean awaitEvent(
                WatchEvent.Kind<?> expectedKind,
                Path expectedRelative,
                long timeoutMillis)
                throws IOException, InterruptedException {

            long deadline = System.nanoTime()
                    + TimeUnit.MILLISECONDS.toNanos(timeoutMillis);

            for (;;) {
                long remaining = deadline - System.nanoTime();

                if (remaining <= 0) return false;

                WatchKey key = service.poll(
                        remaining, TimeUnit.NANOSECONDS);

                if (key == null) return false;

                Path watchedDir = dirsByKey.get(key);
                boolean found = false;

                try {
                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind() == OVERFLOW) {
                            needsReconciliation = true;
                            registerTree(root);
                            continue;
                        }

                        if (watchedDir == null) continue;

                        Object context = event.context();

                        if (!(context instanceof Path)) continue;

                        Path relative = (Path) context;

                        if (relative.isAbsolute()) continue;

                        Path affected = watchedDir
                                .resolve(relative).normalize();

                        if (!affected.startsWith(root)) continue;

                        if (event.kind() == ENTRY_CREATE
                                && Files.isDirectory(
                                        affected,
                                        LinkOption.NOFOLLOW_LINKS)) {

                            registerTree(affected);
                            needsReconciliation = true;
                        }

                        if (event.kind() == expectedKind
                                && root.relativize(affected)
                                        .equals(expectedRelative)) {
                            found = true;
                        }
                    }
                } finally {
                    if (!key.reset() && watchedDir != null) {
                        dirsByKey.remove(key);
                        keysByDir.remove(watchedDir, key);
                        needsReconciliation = true;
                    }
                }

                if (found) return true;
            }
        }

        int registeredDirectories() {
            return keysByDir.size();
        }

        boolean allInvalid() {
            return dirsByKey.keySet().stream()
                    .noneMatch(WatchKey::isValid);
        }

        @Override
        public void close() throws IOException {
            service.close();
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
                if (error != null) throw error;
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws Exception {
        Path workspace =
                Files.createTempDirectory("recursive-watch-");

        try {
            Path root = Files.createDirectory(
                    workspace.resolve("root"));

            Path inner = Files.createDirectories(
                    root.resolve("existing").resolve("inner"));

            Files.writeString(
                    inner.resolve("before.txt"),
                    "old", StandardCharsets.UTF_8);

            TreeWatcher watcher = new TreeWatcher(root);

            try (watcher) {
                System.out.println(
                        "initial.directories="
                                + watcher.registeredDirectories());

                Files.writeString(
                        inner.resolve("later.txt"),
                        "new", StandardCharsets.UTF_8);

                boolean existing = watcher.awaitEvent(
                        ENTRY_CREATE,
                        Path.of("existing", "inner", "later.txt"),
                        5000);

                System.out.println(
                        "existing.createSeen=" + existing);

                Path incoming = Files.createDirectories(
                        root.resolve("incoming").resolve("deep"));

                Files.writeString(
                        incoming.resolve("already.txt"),
                        "arrived", StandardCharsets.UTF_8);

                boolean created = watcher.awaitEvent(
                        ENTRY_CREATE, Path.of("incoming"), 5000);

                System.out.println(
                        "subtree.createSeen=" + created);

                System.out.println(
                        "subtree.directories="
                                + watcher.registeredDirectories());

                System.out.println(
                        "subtree.preexistingFiles="
                                + countRegularFiles(
                                        root.resolve("incoming")));

                Files.writeString(
                        incoming.resolve("next.txt"),
                        "new", StandardCharsets.UTF_8);

                boolean nested = watcher.awaitEvent(
                        ENTRY_CREATE,
                        Path.of("incoming", "deep", "next.txt"),
                        5000);

                System.out.println(
                        "nested.createSeen=" + nested);

                System.out.println(
                        "reconcile.flag="
                                + watcher.needsReconciliation);

                check(watcher.registeredDirectories() == 5
                        && existing && created && nested
                        && countRegularFiles(
                                root.resolve("incoming")) == 2
                        && watcher.needsReconciliation,
                        "watch tree conditions");
            }

            System.out.println(
                    "close.keysInvalid=" + watcher.allInvalid());

            check(watcher.allInvalid(),
                    "watcher close invalidates keys");

            System.out.println("checks=PASS");
        } finally {
            deleteTree(workspace);
        }

        System.out.println(
                "workspace.cleaned=" + !Files.exists(workspace));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 RecursiveWatchRegistrationDemo.java
java RecursiveWatchRegistrationDemo
```

**Stdout chính xác đã kiểm chứng trên filesystem thử nghiệm:**

```text
initial.directories=3
existing.createSeen=true
subtree.createSeen=true
subtree.directories=5
subtree.preexistingFiles=1
nested.createSeen=true
reconcile.flag=true
close.keysInvalid=true
checks=PASS
workspace.cleaned=true
```

### 10.1. Giải thích từng dòng

- `initial.directories=3`: đăng ký `root`, `existing` và `existing/inner` qua `walkFileTree`.
- `existing.createSeen=true`: file được tạo trong `existing/inner` đã được watch, dù root trực tiếp không theo dõi entry sâu đó.
- `subtree.createSeen=true`: nhận event `ENTRY_CREATE` cho directory `incoming` trong root.
- `subtree.directories=5`: handler đã duyệt và đăng ký cả `incoming` và `incoming/deep`.
- `subtree.preexistingFiles=1`: file `already.txt` có mặt trong subtree khi quét, không được giả định là có event tạo file sau registration.
- `nested.createSeen=true`: file `incoming/deep/next.txt` được tạo **sau khi** thư mục sâu đã đăng ký và event được quan sát.
- `reconcile.flag=true`: cần đối soát nghiệp vụ vì tree mới có thể chứa những nội dung đã tồn tại trước event processing.
- `close.keysInvalid=true`: watcher đóng làm các keys không còn valid.
- `checks=PASS` và `workspace.cleaned=true`: điều kiện kiểm tra và việc dọn workspace trong test thành công.

### 10.2. Giới hạn cố ý của mã demo

`TreeWatcher` trong bài chỉ quản lý registrations và **đánh dấu** cần reconciliation. Nó **chưa phải bộ đồng bộ index production**: không chứa database index, không có queue/background reconciler, không tự bảo đảm mọi event trong lúc rescan được hợp nhất, và không chống mọi race từ path không tin cậy.

`countRegularFiles(...)` là một thao tác **quét hiện trạng**, không phải khôi phục lịch sử event. Khi `OVERFLOW`, chương trình đánh dấu `needsReconciliation` và gọi `registerTree(root)` để tìm registration thiếu; để đồng bộ index thật, ứng dụng phải thực hiện **full rescan/compare** ở tầng cao hơn. Việc không xóa cờ trong demo là có chủ đích: cờ vẫn còn cho tới khi một quy trình reconciliation hoàn chỉnh được triển khai và xác nhận.

`Files.createTempDirectory` chỉ tạo workspace tạm mới. Hàm `deleteTree` **xóa đệ quy**, chỉ được gọi trên chính workspace do chương trình sở hữu; không áp dụng trực tiếp lên thư mục người dùng hoặc dự án thật.

### 10.3. Vì sao không kiểm tra số event chính xác?

WatchService phụ thuộc OS/provider. Một hành động ghi có thể sinh thêm `ENTRY_MODIFY`, event có thể được gộp, thứ tự không hứa giống nhau mọi môi trường. Bài kiểm tra **đúng loại + đúng relative Path cần thiết**, không so `pollEvents().size()==1`. Điều đó tránh biến hành vi ngẫu nhiên của một máy thành yêu cầu API chung.

## 11. Vòng đời watcher và shutdown

### 11.1. `try-with-resources` đóng `WatchService`

`WatchService` là `Closeable`. Ví dụ:

```java
try (WatchService watcher =
        root.getFileSystem().newWatchService()) {
    registerTree(root, watcher, directories);
    // Nhận và xử lý events...
}
```

Đây là mã minh họa, các biến và method cần được khai báo.

Khi gọi `close()`:

- WatchService được đóng.
- Những keys liên quan bị invalid.
- Các thread đang `take()`/`poll(timeout)` có thể nhận `ClosedWatchServiceException`.
- Mọi thao tác trên watcher đã đóng không nên retry vô hạn.

### 11.2. Interrupt và hủy công việc

`take()` và timed `poll(...)` có thể ném `InterruptedException`. Khi worker bị yêu cầu dừng, bắt lỗi ở tầng phù hợp, khôi phục interrupt flag nếu dừng và đóng watcher.

```java
try {
    watchLoop();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
} finally {
    // Đóng watcher và tài nguyên có ownership thích hợp.
}
```

Đoạn này là **phác thảo**; `watchLoop()` thuộc ứng dụng. Không `catch(InterruptedException ignored)` rồi tiếp tục chờ vô hạn nếu cancellation cần được tôn trọng.

### 11.3. Thư mục bị xóa/rename

Nếu watched directory bị xóa, một key có thể tự invalid. Nếu directory bị move/rename, hành vi và path từ `watchable()` là **implementation-specific**; không có bảo đảm key luôn tự invalidate đúng lúc.

Ứng dụng nên định kỳ kiểm tra/đối soát các registered directories, loại mappings obsolete và xử lý cây được di chuyển vào/ra root.

## 12. Tại sao `ENTRY_MODIFY` không đồng nghĩa “tệp đã sẵn sàng”?

File có thể đang được ghi, tệp đích có thể nhận thêm nội dung sau event đầu tiên. Không bắt event MODIFY rồi xử lý file như bản hoàn chỉnh nếu producer chưa đóng stream.

Một giao thức ổn định hơn:

```text
Producer:
    ghi output.partial
    flush/close thành công
    rename/publish thành output.ready

Consumer:
    watch directory
    thấy output.ready
    xác minh quyền, file hiện tại và nội dung
    đưa vào hàng đợi xử lý
```

Ngay cả rename/publish cũng cần kiểm tra provider và contract lưu trữ; WatchService vẫn chỉ là cơ chế thông báo thay đổi chứ không xác thực toàn vẹn của file.

Khi nhận event từ thư mục sâu, đừng suy rằng `affected` còn tồn tại. Tên entry có thể đã bị xóa, ghi lại hoặc chuyển thành symbolic link trước lúc handler mở file.

## 13. Kiểm thử: cần kiểm tra cả cây ban đầu, cây mới và lỗi

### 13.1. Ma trận kiểm thử hành vi

| Ca kiểm thử | Điều cần chứng minh |
| --- | --- |
| Root trống | Một registration cho root, không có giả định về event cũ |
| Root có nhiều thư mục lồng | `walkFileTree` đăng ký mọi directory hiện hữu |
| Tạo file tại root | Key của root được báo với context tương đối |
| Tạo file sâu trong cây cũ | Key của directory cha trực tiếp được báo |
| Tạo directory mới một cấp | Handler đăng ký directory đó |
| Di chuyển vào subtree có nhiều directory | Handler đăng ký **toàn bộ** directories trong subtree |
| File đã nằm trong subtree mới | Scan nhận biết hiện trạng dù không có event replay |
| Tạo file trong subtree sau registration | Nhận event từ key của thư mục mới |
| Xóa directory đang được watch | Key invalid được dọn mapping |
| Key bị `cancel()` | Không tiếp tục coi key là registration hoạt động |
| `OVERFLOW` | Đánh dấu dirty và chạy reconciliation thật |
| Source tree có symlink | Policy không tự follow ra ngoài root |
| Không có quyền đăng ký | Báo lỗi/partial, không báo đầy đủ |
| Watcher bị close | Consumer dừng, các key invalid |
| Interrupt khi chờ | Worker thoát theo policy |
| Provider phát event chậm | Timed poll không treo vô hạn trong test |
| Multi-consumer | Không reset key trước khi hoàn thành xử lý |

### 13.2. Tránh test phụ thuộc lượng event cố định

Không assert “tạo một file luôn sinh đúng một event” hoặc “sự kiện file luôn xuất hiện trong 10 ms”. Theo Java API, provider có thể dùng native facility hoặc polling bên trong; thứ tự/độ trễ/gộp event thay đổi.

Test tốt thường:

1. Đăng ký **trước** khi tạo file thử.
2. Dùng worker/timeout rõ ràng.
3. Tìm event `kind` mong muốn và `context` đúng.
4. Bỏ qua event bổ sung không ảnh hưởng mục tiêu.
5. Xử lý `OVERFLOW` như khả năng bỏ sót.
6. Dọn đúng workspace test trong `finally`.

Với integration test WatchService trên network shares hoặc provider ít được hỗ trợ, cần có điều kiện môi trường và chính sách timeout/failure rõ.

## 14. Những sai lầm hay gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Đăng ký mỗi root rồi giả định watch đệ quy | Bỏ các event nằm trong thư mục con | Đăng ký từng directory |
| Chỉ dùng `Files.walkFileTree` một lần | Không biết cây con mới thêm sau startup | Khi `ENTRY_CREATE` là dir, register subtree |
| Chỉ `register` thư mục mới một cấp | Bỏ hậu duệ của subtree được move vào | `walkFileTree(newDir)` |
| Chỉ register mà không scan trạng thái | Bỏ file có trước registration | Reconcile directory/files |
| Thấy `ENTRY_CREATE` là file luôn | Có thể là directory, link hoặc entry đã biến mất | `Files.isDirectory(path, NOFOLLOW_LINKS)` và xử lý race |
| Lấy `event.context()` làm absolute path | Ghép sai file khi nhiều directories | Map key→directory rồi resolve |
| Không tách `OVERFLOW` trước cast `Path` | Context có thể `null` hoặc khác | Xử lý OVERFLOW trước |
| Không gọi `key.reset()` | Key không tiếp tục được queue theo chu kỳ | Reset sau xử lý |
| Bỏ qua `reset()==false` | Map chứa key không hợp lệ | Dọn cả map key/path |
| Chỉ kiểm tra `key.isValid()` ở startup | Key có thể invalid sau đó | Theo dõi lifecycle/reconcile |
| Bắt mọi `IOException` rồi tiếp tục | Index được báo đầy đủ dù thiếu registration | Báo partial và retry/rescan theo policy |
| Dùng `poll()` trong vòng quay liên tục | Tốn CPU | `take()` hoặc `poll(timeout)` |
| Bật FOLLOW_LINKS tùy ý | Nguy cơ đi ngoài root/vòng lặp | Định nghĩa symlink policy |
| Xử lý file lớn trực tiếp trong event thread | Tồn đọng và `OVERFLOW` | Queue có giới hạn, workers |
| Coi event là durable journal | Mất thay đổi khi offline/crash/overflow | Scan ban đầu và định kỳ |
| Dựa vào lexical startsWith làm security boundary | Symlink/race có thể phá mô hình | Quyền OS và root trusted |
| Quên close watcher | Rò resource | `try-with-resources` hoặc close |
| Không dọn key của directory bị xóa | Map rò bộ nhớ và báo số đăng ký sai | Loại invalid, reconcile |
| Giả định rename/move luôn phát cùng chuỗi event | Provider khác nhau | Dựa trên state reconciliation |

## 15. Thiết kế cho cây lớn và các provider khác nhau

### 15.1. Số lượng thư mục và giới hạn OS

Đăng ký từng directory có chi phí. Với cây rất lớn, có thể gặp giới hạn descriptors/handles, quota watcher của OS, phí I/O duyệt ban đầu hoặc lỗi provider.

Một ứng dụng production nên:

- Giới hạn root và phạm vi theo quyền.
- Giới hạn số directory registrations theo cấu hình.
- Báo lỗi nếu không thể watch đầy đủ.
- Theo dõi số keys valid và số lần OVERFLOW.
- Có chiến lược fallback: quét định kỳ nếu không thể đặt watchers cho tất cả directories.
- Dọn mappings và watcher khi job kết thúc.

Không giả định `register` luôn thành công cho mọi provider hoặc mọi số lượng thư mục.

### 15.2. Nhiều thread và map

`WatchService` có thể an toàn khi được nhiều consumer dùng; **không có nghĩa `HashMap` trong ví dụ tự trở thành thread-safe**. Chương trình demo dùng **một consumer** để đơn giản hóa việc đăng ký, map và reset.

Nếu cần nhiều consumers, dùng synchronization/concurrent collection thích hợp và bảo đảm **không reset một key trước khi tất cả event của registration đó đã xử lý**. Nếu không, các xử lý đồng thời có thể trùng hoặc thiếu logic nghiệp vụ.

### 15.3. Theo dõi nhiều root

Một watcher có thể quản lý nhiều directories từ cùng provider, nhưng root nào cũng cần initial registration và state reconciliation riêng. Nên tách:

- Registered roots và ownership.
- Key → directory.
- Directory → key.
- Dirty/overflow status theo root.
- Các hàng đợi nghiệp vụ.
- Lifecycle và shutdown.

Nếu hai roots chồng lấn nhau, có thể đăng ký trùng một directory; cần xác định policy để không nhân đôi xử lý.

### 15.4. Khi WatchService không phù hợp

Nếu yêu cầu là **giám sát sự thay đổi một cách chính xác tuyệt đối trên mọi loại filesystem, qua crash và network**, WatchService không đủ làm nguồn dữ liệu duy nhất.

Cân nhắc kết hợp:

- Snapshot của storage khi cần tính nhất quán.
- Periodic inventory/rescan.
- Durable message queue từ chính producer.
- File-ready/publish protocol.
- Metadata/versioning/checksum.
- API/notification của storage provider được thiết kế cho môi trường đó.

WatchService hữu ích để **giảm độ trễ phát hiện**, không thay cho hệ thống bảo đảm exactly-once hoặc transaction log.

## 16. Checklist trước khi triển khai

- [ ] Đã chọn đúng **root directory** và xác minh nó tồn tại.
- [ ] Tạo `WatchService` từ filesystem của root.
- [ ] Dùng `walkFileTree` để đăng ký **mọi thư mục hiện có**.
- [ ] Không coi `root.register` là recursive watch.
- [ ] Lưu map `WatchKey → Path`; có thể dùng map ngược để tránh trùng.
- [ ] Đã xác định chính sách symlink và mount.
- [ ] Khi `ENTRY_CREATE` cho directory, đăng ký **toàn bộ subtree mới**.
- [ ] Scan/đối soát file đã xuất hiện trước khi directory mới được đăng ký.
- [ ] Đã xử lý race khi directory bị xóa/thay đổi giữa event và register.
- [ ] Phân biệt `OVERFLOW` với các event có Path context.
- [ ] Không coi `registerTree` một lần là đã khôi phục các event bị mất.
- [ ] Gọi `key.pollEvents()` và `key.reset()` đúng thứ tự.
- [ ] Dọn mappings khi key invalid hoặc cancel.
- [ ] Không dừng watcher toàn bộ chỉ vì một key con invalid nếu còn công việc.
- [ ] Xử lý `take/poll/timeout`, `InterruptedException` và `ClosedWatchServiceException`.
- [ ] Đóng watcher đúng vòng đời.
- [ ] Giới hạn số registrations, độ sâu, queue và xử lý nặng.
- [ ] Có scan ban đầu/định kỳ khi tính đầy đủ là bắt buộc.
- [ ] Test cây hiện có, cây move vào, file sâu và cây con có file tồn tại sẵn.
- [ ] Không dùng sự kiện làm bảo đảm authorization hoặc file-ready.

## 17. Câu hỏi ôn tập

**Câu 1.** Đăng ký `root.register(watcher, ENTRY_CREATE)` có tự theo dõi `root/a/b/file.txt` không?  
**Đáp án:** Không. Nó theo dõi các entry trực tiếp của `root`. Muốn event trực tiếp trong `b` cần đăng ký `b`.

**Câu 2.** Cách nào đăng ký tất cả thư mục đã có khi chương trình khởi động?  
**Đáp án:** `Files.walkFileTree(root)` và gọi `register` trong `preVisitDirectory` cho mỗi thư mục.

**Câu 3.** Khi nhận `ENTRY_CREATE` cho `incoming` chứa sẵn `incoming/deep`, nên làm gì?  
**Đáp án:** Duyệt `walkFileTree(incoming)` để đăng ký **tất cả thư mục con**, và scan trạng thái file đã có.

**Câu 4.** Tại sao chỉ đăng ký thư mục mới là chưa đủ?  
**Đáp án:** Các file tạo trước khi đăng ký không được tự phát lại như event, nên phải quét đối soát trạng thái thực.

**Câu 5.** Vì sao cần map `WatchKey → Path`?  
**Đáp án:** Để biết `event.context()` tương đối từ thư mục nào, giúp resolve đúng path khi nhiều thư mục được watch.

**Câu 6.** `pollEvents()` lấy một hay nhiều event?  
**Đáp án:** Danh sách các event đã tích lũy trên key, có thể rỗng hoặc nhiều; không có bảo đảm đúng một.

**Câu 7.** `reset()` trả false nghĩa là gì?  
**Đáp án:** Key/registration đã invalid, cần loại khỏi map và xử lý vòng đời.

**Câu 8.** `OVERFLOW` có nghĩa gì trong recursive watcher?  
**Đáp án:** Có thể đã mất event, cần scan/đối soát lại trạng thái, không chỉ reset key.

**Câu 9.** Tại sao không nên follow symlink một cách mặc định?  
**Đáp án:** Có thể đi ra ngoài root, tạo vòng lặp và theo dõi dữ liệu ngoài phạm vi được phép.

**Câu 10.** Directory `incoming` bị xóa trước lúc xử lý event tạo; có lỗi Java không?  
**Đáp án:** Không nhất thiết. Event là tín hiệu về thay đổi đã xảy ra, còn trạng thái hiện tại có thể khác; cần xử lý race.

**Câu 11.** WatchService có lưu lịch sử event sau khi JVM ngừng chạy không?  
**Đáp án:** Không. Nó không phải durable journal; cần scan lại hoặc hệ thống logging khác.

**Câu 12.** Vì sao không chạy công việc đọc file nặng ngay trong event thread?  
**Đáp án:** Có thể khiến consumer chậm, queue đầy và xảy ra OVERFLOW; nên đẩy sang worker queue có giới hạn.

**Câu 13.** Hai thread đồng thời cùng sửa map `HashMap` của watcher có an toàn không?  
**Đáp án:** Không nếu không đồng bộ. `WatchService` thread-safe không làm state ứng dụng tự thread-safe.

**Câu 14.** Có thể bảo đảm event tới theo đúng thứ tự, đúng một lần trên mọi filesystem?  
**Đáp án:** Không. Provider/OS khác nhau, event có thể gộp, mất hoặc trễ; dùng reconciliation cho yêu cầu độ đầy đủ.

## 18. Kết luận và tài liệu Java chính thức

**Khi theo dõi một cây tệp bằng `WatchService`, đăng ký `root` chỉ là điểm bắt đầu.** Cần đăng ký **từng directory hiện tại**, đồng thời quản lý **các directory xuất hiện sau khi chương trình chạy**. Khi phát hiện `ENTRY_CREATE` là directory, phải duyệt toàn bộ subtree đó và quét trạng thái thực tế vì các file có trước registration không tự sinh lại event.

Vòng event tiêu chuẩn cần: lấy `WatchKey` qua `take/poll`, tìm directory từ map, duyệt `key.pollEvents()`, xử lý `OVERFLOW`, gọi `key.reset()` và loại key invalid. Để có index chính xác, kết hợp watcher với scan ban đầu, đối soát sau subtree mới và reconciliation khi overflow/race; luôn quản lý vòng đời, symlink, quyền và giới hạn tài nguyên.

### Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 17 — `WatchService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): queue, `take`/`poll`/`close`, `OVERFLOW`, giới hạn nền tảng.
- [Oracle Java SE 17 — `WatchKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html): `pollEvents`, `reset`, `cancel`, `isValid`, trạng thái ready/signalled.
- [Oracle Java SE 17 — `Path.register`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#register(java.nio.file.WatchService,java.nio.file.WatchEvent.Kind...)): đăng ký một directory với service.
- [Oracle Java SE 17 — `Watchable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Watchable.html): cùng watchable được register lại có thể dùng lại key.
- [Oracle Java SE 17 — `WatchEvent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html): `kind`, `count`, `context`.
- [Oracle Java SE 17 — `Files.walkFileTree`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): traversal và visitor.
- [Dev.java — Watching a Directory for Changes](https://dev.java/learn/api/io/java-io/file-system/watching-dir-changes/): hướng dẫn WatchService và vòng xử lý event.
