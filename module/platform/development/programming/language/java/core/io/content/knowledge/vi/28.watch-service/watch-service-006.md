# OVERFLOW và nhu cầu quét lại trạng thái trong Java NIO WatchService

## 1. Tại sao WatchService có thể bỏ lỡ thay đổi?

`java.nio.file.WatchService` là cơ chế Java NIO.2 dùng để nhận thông báo khi nội dung một thư mục thay đổi. Ứng dụng thường đăng ký `ENTRY_CREATE`, `ENTRY_MODIFY` và `ENTRY_DELETE` để tự động xử lý file mới, làm mới chỉ mục, đọc lại cấu hình hoặc đồng bộ dữ liệu.

Tuy nhiên, WatchService **không phải nhật ký giao dịch bền vững**. Hệ điều hành, filesystem provider và hàng đợi thông báo có thể gộp hoặc loại bỏ sự kiện. Khi sự kiện bị mất, WatchService có thể báo loại sự kiện đặc biệt **`StandardWatchEventKinds.OVERFLOW`**.

~~~text
Thư mục: create A, modify B, delete C, create D, ...
                         |
                         v
             WatchService / provider
                         |
                   queue quá tải
                         |
             một số sự kiện bị mất
                         |
                         v
                WatchEvent OVERFLOW
                         |
                         v
                 ĐÁNH DẤU DIRTY
                         |
                         v
              QUÉT LẠI THƯ MỤC
                         |
                         v
             ĐỐI CHIẾU VỚI SNAPSHOT
~~~

**Ý nghĩa:** sau `OVERFLOW`, không còn bảo đảm ứng dụng đã biết tất cả thay đổi của thư mục chỉ nhờ những sự kiện đã nhận. Cách đúng là **quét lại trạng thái hiện có và đối chiếu với trạng thái đang lưu**, không đoán danh sách file từ những sự kiện bị mất.

## 2. Các loại sự kiện WatchEvent

| Loại sự kiện | Ý nghĩa | Thông tin thường dùng |
| --- | --- | --- |
| `ENTRY_CREATE` | Một entry xuất hiện | `event.context()` là tên `Path` tương đối của entry |
| `ENTRY_MODIFY` | Một entry có thay đổi | `event.context()` là tên `Path` tương đối |
| `ENTRY_DELETE` | Một entry biến mất | `event.context()` là tên `Path` tương đối |
| `OVERFLOW` | Sự kiện có thể đã mất hoặc bị loại bỏ | Không dùng context để suy ra file nào bị bỏ sót |

Đăng ký thư mục bằng:

~~~java
dir.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);
~~~

Đây chỉ là **mảnh Java minh họa**, với `Path dir` và `WatchService watcher` đã được tạo.

Không cần đăng ký `OVERFLOW` như một sự kiện file thông thường để xử lý tình huống event loss. Khi lấy các sự kiện, phải kiểm tra `event.kind() == StandardWatchEventKinds.OVERFLOW` **trước** khi ép kiểu context thành `Path`.

### OVERFLOW không có nghĩa là một file cụ thể đã thay đổi

Giả sử snapshot của ứng dụng là:

~~~text
a.txt = phiên bản cũ
b.txt = có tồn tại
~~~

Trong thời gian ứng dụng chưa lấy hết event:

~~~text
a.txt được sửa
b.txt bị xóa
c.txt được tạo
d.txt được tạo rồi bị xóa ngay
~~~

Hàng đợi có thể chỉ giữ được một phần các sự kiện đó và báo `OVERFLOW`. Khi quét lại, ứng dụng có thể nhận ra `a.txt` khác, `b.txt` mất, `c.txt` mới. Nhưng `d.txt` đã được tạo và xóa giữa hai lần quan sát có thể **không thể phát hiện**.

Do vậy:

- `OVERFLOW` cho biết **mất độ tin cậy về sự kiện đã xảy ra**, chứ không liệt kê sự kiện đã mất.
- Quét lại giúp tái lập **trạng thái quan sát được hiện tại**.
- Quét lại **không khôi phục đầy đủ lịch sử**, thứ tự và số lần sửa đã xảy ra.
- Một `ENTRY_MODIFY` cũng không bảo đảm tương ứng chính xác một lần ghi file; nhiều thay đổi có thể bị gộp và `WatchEvent.count()` có thể lớn hơn 1.

Nếu hệ thống phải xử lý từng giao dịch một cách chính xác dù file tồn tại rất ngắn, cần một giao thức hoặc hàng đợi bền vững khác, không thể chỉ dựa vào WatchService.

## 3. WatchService, WatchKey và reset

Chu trình WatchService cơ bản:

1. Tạo `WatchService` cho `FileSystem` phù hợp.
2. Đăng ký một thư mục với `Path.register(watcher, ...)`, nhận `WatchKey`.
3. Đợi `watcher.take()` hoặc gọi `poll()`.
4. Lấy sự kiện của key bằng `key.pollEvents()`.
5. Xử lý bình thường hoặc đánh dấu rescan nếu gặp `OVERFLOW`.
6. **Gọi `key.reset()`** để key có thể tiếp tục báo những sự kiện mới.
7. Nếu `reset()` trả `false`, key không còn hợp lệ; cần xử lý thay đổi vòng đời của directory hoặc đăng ký lại theo chính sách ứng dụng.

Một `WatchService` có thể quản lý nhiều thư mục. Mỗi `WatchKey` tương ứng một registration; dùng `key.watchable()` hoặc bản đồ `Map<WatchKey,Path>` để biết sự kiện thuộc thư mục nào.

Đặc biệt, **đăng ký thư mục cha không tự động theo dõi đệ quy** mọi thư mục con. Nếu muốn theo dõi cả cây, ứng dụng phải đăng ký từng thư mục con liên quan và duy trì các registration khi cây thay đổi.

### Mẫu phát hiện OVERFLOW

~~~java
WatchKey key = watcher.take();
boolean dirty = false;

for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        dirty = true;
        continue;
    }

    @SuppressWarnings("unchecked")
    WatchEvent<Path> typed = (WatchEvent<Path>) event;
    Path changed = watchedDir.resolve(typed.context());

    // Có thể cập nhật gia tăng theo ENTRY_CREATE / MODIFY / DELETE.
    // Không giả định file còn tồn tại khi thực sự truy cập.
}

if (dirty) {
    // Quét lại watchedDir; đối chiếu với trạng thái đã lưu.
}

if (!key.reset()) {
    // Key invalid: kiểm tra lại watcher và thư mục đã đăng ký.
}
~~~

Đây là **mảnh Java trong vòng xử lý sự kiện**, không phải chương trình độc lập. `watcher` và `watchedDir` cần được khai báo trong ứng dụng thực tế.

Với `OVERFLOW`, không ép `event.context()` thành `Path`; loại sự kiện này không cung cấp một danh sách tên file đã mất.

`key.reset()` cần được thực hiện trên đường xử lý bình thường, kể cả sau OVERFLOW. Nếu code có nhiều nhánh hoặc có thể ném ngoại lệ, nên tổ chức `finally` để không bỏ quên reset. `reset() == false` không thể được sửa chỉ bằng cách gọi `reset()` lặp vô hạn: cần kiểm tra thư mục có bị xóa, đổi tên, thay quyền hoặc filesystem ngừng theo dõi.

## 4. Tại sao một snapshot phải được quét lại?

Ứng dụng thường có **trạng thái nội bộ** khác với filesystem:

~~~text
Trạng thái RAM trước khi mất sự kiện:
  config.json → version 2
  report.csv  → tồn tại
  inbox/a.txt → tồn tại

Trạng thái thực tế sau khi mất sự kiện:
  config.json → version 3
  report.csv  → đã bị xóa
  inbox/a.txt → vẫn tồn tại
  inbox/b.txt → mới được tạo
~~~

Nếu không rescan, cache hoặc index vẫn nghĩ `config.json` ở phiên bản 2 và `report.csv` còn tồn tại. Sau OVERFLOW, ứng dụng cần:

- **Chụp lại trạng thái hiện tại** của những thư mục chịu ảnh hưởng.
- Phát hiện tên mới (added), tên không còn (removed), tên còn nhưng nội dung/thuộc tính đã thay đổi (changed).
- Cập nhật các cấu trúc dữ liệu, công việc chờ, index hoặc cache theo kết quả.
- Tiếp tục tiêu thụ sự kiện mới; nếu có thay đổi trong lúc quét, có thể cần quét thêm lượt nữa.

Mục tiêu là **reconciliation**: đưa biểu diễn của ứng dụng hội tụ về filesystem hiện tại, thay vì dựng lại một chuỗi sự kiện vốn đã thất lạc.

### Nên lưu gì trong snapshot?

| Dữ liệu snapshot | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Tên/đường dẫn | Đối chiếu tạo/xóa đơn giản | Không biết nội dung có thay đổi |
| `Files.size` | Rẻ, phát hiện thay đổi độ dài | Nội dung có thể thay đổi nhưng giữ nguyên size |
| `Files.getLastModifiedTime` | Tương đối nhanh | Độ phân giải thời gian khác nhau; metadata có thể bị giữ nguyên/đặt lại |
| `BasicFileAttributes.fileKey()` | Có thể giúp nhận diện một object filesystem | Có thể null hoặc không ổn định giữa provider |
| Hash nội dung | Nhận ra nhiều thay đổi mà metadata không thể hiện | Tốn đọc đĩa/CPU, khó dùng với file đang thay đổi |
| Version/manifest do ứng dụng quản lý | Có thể có nghĩa chính xác cho domain | Cần thiết kế giao thức từ đầu |

Không có một signature metadata rẻ tiền nào bảo đảm phát hiện mọi thay đổi nội dung trên mọi filesystem. Với yêu cầu độ chính xác cao, xây một protocol chứa version/checksum và quy tắc công bố file hoàn chỉnh.

## 5. Thuật toán rescan và đối chiếu

Một thuật toán đơn giản:

~~~text
known = snapshot đã lưu trước đó

khi nhận ENTRY_CREATE/MODIFY/DELETE:
    cập nhật từng mục hoặc đánh dấu mục cần kiểm tra

khi nhận OVERFLOW:
    dirty = true

nếu dirty:
    current = scanDirectory()
    added   = tên trong current nhưng không có trong known
    removed = tên trong known nhưng không có trong current
    changed = tên có trong cả hai nhưng signature khác
    cập nhật cache/index/job theo các khác biệt
    known = current
    chỉ xóa dirty nếu không có thay đổi mới trong lúc scan
~~~

Đây là pseudocode. Ứng dụng thật cần quyết định rõ xử lý thay đổi file trong lúc scan:

- **Register trước rồi mới lấy snapshot ban đầu.** Nếu scan trước và register sau, có một khoảng hở mà thay đổi không được watcher báo.
- **Scan không phải transaction nguyên tử.** File có thể xuất hiện/biến mất ngay sau khi liệt kê; `NoSuchFileException` khi đọc metadata là một tình huống cần xử lý.
- **Không mất cờ dirty mới.** Nếu OVERFLOW xảy ra trong lúc worker đang scan, không được đánh dấu sạch theo snapshot cũ. Dùng generation counter hoặc trạng thái đồng bộ rõ ràng.
- **Gộp nhiều yêu cầu quét lại.** Một directory thường chỉ nên có một lượt scan đang chạy; nếu dirty tiếp thì lên lịch thêm lượt sau.
- **Bảo vệ thread nhận sự kiện.** Nếu scan rất lâu trên watcher thread, hàng đợi có thể tiếp tục quá tải và gây thêm OVERFLOW.

Với thư mục nhỏ, chiến lược quét lại mọi khi có sự kiện có thể đơn giản và đáng tin hơn logic incremental phức tạp. Với cây hàng triệu file, thường cần cập nhật gia tăng và full rescan khi OVERFLOW hoặc theo lịch định kỳ.

## 6. Ví dụ Java 17+ chạy độc lập: mô phỏng mất sự kiện rồi rescan

**Không thể ép OVERFLOW thật xảy ra một cách di động và xác định**, vì nó phụ thuộc hệ điều hành và provider. Ví dụ sau tạo một `WatchService` thật, rồi **cố ý không dựa vào những event phát sinh** để mô phỏng tình huống đã bỏ lỡ thông báo. Nó gọi `reconcile` và đối chiếu trạng thái file bằng nội dung text để stdout xác định.

Bản demo chỉ dùng vài file UTF-8 nhỏ. Trong production, không nên đọc toàn bộ các file lớn vào RAM mỗi lần quét lại.

Lưu thành `OverflowRescanDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Stream;

public class OverflowRescanDemo {
    private static Map<String, String> snapshot(Path dir)
            throws IOException {
        Map<String, String> result = new TreeMap<>();

        try (Stream<Path> paths = Files.list(dir)) {
            for (Path file : paths.filter(Files::isRegularFile).toList()) {
                result.put(file.getFileName().toString(),
                        Files.readString(file, StandardCharsets.UTF_8));
            }
        }
        return result;
    }

    private static void reconcile(Path dir, Map<String, String> known)
            throws IOException {
        Map<String, String> current = snapshot(dir);
        Set<String> allNames = new TreeSet<>();
        allNames.addAll(known.keySet());
        allNames.addAll(current.keySet());

        for (String name : allNames) {
            if (!known.containsKey(name)) {
                System.out.println("ADDED " + name);
            } else if (!current.containsKey(name)) {
                System.out.println("REMOVED " + name);
            } else if (!known.get(name).equals(current.get(name))) {
                System.out.println("CHANGED " + name);
            }
        }

        known.clear();
        known.putAll(current);
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("watch-rescan-");

        try {
            Path alpha = dir.resolve("alpha.txt");
            Path old = dir.resolve("obsolete.txt");
            Path newest = dir.resolve("new.txt");

            Files.writeString(alpha, "A", StandardCharsets.UTF_8);
            Files.writeString(old, "old", StandardCharsets.UTF_8);

            try (WatchService watcher =
                         dir.getFileSystem().newWatchService()) {
                // Đăng ký trước khi chụp baseline.
                dir.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                Map<String, String> known = snapshot(dir);
                System.out.println("BASELINE " + known.keySet());

                // Giả lập ứng dụng mất thông báo về ba thao tác.
                Files.writeString(alpha, "A2", StandardCharsets.UTF_8);
                Files.delete(old);
                Files.writeString(newest, "new", StandardCharsets.UTF_8);

                System.out.println("RESCAN after missed events");
                reconcile(dir, known);
                System.out.println("CURRENT " + known.keySet());

                // Nếu có OVERFLOW thực trong các event đã được
                // chuyển tới queue, reconcile cũng là lối phục hồi.
                // Những ENTRY_* còn lại ở đây cố ý không dùng làm
                // nguồn sự thật, vì snapshot đã được làm mới.
                WatchKey key;
                while ((key = watcher.poll()) != null) {
                    boolean overflow = false;
                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.OVERFLOW) {
                            overflow = true;
                        }
                    }
                    if (overflow) {
                        reconcile(dir, known);
                    }
                    if (!key.reset()) {
                        break;
                    }
                }
            }
        } finally {
            try (Stream<Path> files = Files.list(dir)) {
                for (Path file : files.toList()) {
                    Files.deleteIfExists(file);
                }
            }
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac OverflowRescanDemo.java
java OverflowRescanDemo
~~~

Stdout khi chạy trong thư mục tạm không có thay đổi từ bên ngoài:

~~~text
BASELINE [alpha.txt, obsolete.txt]
RESCAN after missed events
CHANGED alpha.txt
ADDED new.txt
REMOVED obsolete.txt
CURRENT [alpha.txt, new.txt]
~~~

Thứ tự ổn định nhờ `TreeMap` và `TreeSet`:

1. Snapshot đầu có `alpha.txt = "A"` và `obsolete.txt = "old"`.
2. Sau đó `alpha.txt` đổi thành `"A2"`, `obsolete.txt` bị xóa và `new.txt` xuất hiện.
3. `reconcile` so sánh tên và nội dung, báo chính xác ba khác biệt còn quan sát được.
4. `known` được cập nhật, nên một lượt reconcile tiếp theo không in lại các khác biệt nếu directory không đổi.
5. Demo tạo watcher thực để minh họa registration và xử lý `OVERFLOW`, nhưng **không khẳng định OVERFLOW đã xảy ra thật**. Lời gọi rescan được thực hiện chủ động để mô phỏng hậu quả bỏ sót thông báo.
6. `key.reset()` được gọi với các key đã được lấy, các tài nguyên và file tạm được dọn sau khi dùng.

Phần demo chỉ quét một directory nông, nội dung text nhỏ; nó chưa có event loop production chạy liên tục, chính sách retry khi scan gặp race, hoặc registration đệ quy.

## 7. Mẫu vòng event loop cần có ở ứng dụng thực tế

Mảnh code xử lý một `WatchKey` với cờ dirty:

~~~java
WatchKey key = watcher.take();
boolean needsRescan = false;
Path dir = registrations.get(key);

try {
    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
            needsRescan = true;
            continue;
        }

        @SuppressWarnings("unchecked")
        WatchEvent<Path> typed = (WatchEvent<Path>) event;
        Path child = dir.resolve(typed.context());

        // Với ENTRY_* có thể cập nhật gia tăng hoặc
        // đánh dấu child cần được kiểm tra lại.
    }

    if (needsRescan) {
        // Đưa yêu cầu rescan(dir) vào hàng đợi công việc.
    }
} finally {
    if (!key.reset()) {
        // Registration invalid: điều tra và đăng ký lại nếu cần.
    }
}
~~~

Đây là **mảnh code minh họa**, cần `registrations`, `watcher` và chính sách ứng dụng đã được định nghĩa. Nếu nhiều thư mục được đăng ký, cần map key tới đúng directory. Nếu `key.reset()` thất bại, chỉ rescan thôi chưa đủ để tiếp tục nhận sự kiện mới: có thể cần đăng ký lại thư mục hoặc theo dõi parent.

Với số lượng file lớn, đừng đọc hàng trăm nghìn file ngay trong thread gọi `watcher.take()`. Tách một worker quét, tiếp tục lấy event và duy trì dirty flag/generation là cách giảm nguy cơ quá tải lặp lại.

### Đừng mất OVERFLOW xảy ra trong lúc đang quét

Một lỗi thiết kế thường gặp:

~~~text
Worker thấy dirty=true
Worker bắt đầu scan
Watcher thấy OVERFLOW mới → đặt dirty=true
Worker scan xong → gán dirty=false
Lần OVERFLOW mới bị xóa mất, không còn rescan!
~~~

Có thể quản lý số thế hệ:

~~~text
onOverflow: changeGeneration += 1

trước scan: capturedGeneration = changeGeneration
scan và áp dụng snapshot
nếu changeGeneration != capturedGeneration:
    phải quét tiếp
ngược lại:
    có thể đánh dấu đã bắt kịp thời điểm quan sát
~~~

Đây là pseudocode về **logic quản lý sự kiện**; trong nhiều thread cần synchronization hoặc kiểu atomic phù hợp. Không chỉ thay bool mà không có quy tắc ownership hoặc memory visibility.

## 8. Theo dõi cây thư mục và các cuộc đua khi quét lại

WatchService chuẩn đăng ký theo **từng directory**, không tự quét sâu toàn bộ cây. Nếu ứng dụng theo dõi một root có các thư mục con:

- Duyệt và đăng ký từng subdirectory cần theo dõi, chẳng hạn bằng `Files.walkFileTree`.
- Khi phát hiện directory mới, **đăng ký ngay** và quét nội dung directory đó vì file bên trong có thể xuất hiện trước khi registration hoàn tất.
- Khi key invalid hoặc một subdirectory bị xóa/đổi tên, cập nhật mapping registration.
- Khi có OVERFLOW ở một directory, quét lại phạm vi liên quan. Nếu cần bảo đảm trạng thái của cả cây, phải đối chiếu cả tập directory registration và những thư mục mới.
- Cần chính sách symlink rõ ràng, tránh vô tình duyệt ngoài root hoặc lặp qua đường dẫn liên kết.

### File đang được ghi dở

`ENTRY_CREATE` có thể đến khi producer mới mở file và chưa ghi hết. Trong lần rescan sau OVERFLOW cũng có thể thấy file chưa hoàn chỉnh. Nếu ứng dụng phải xử lý file nguyên vẹn, nên dùng giao thức như:

~~~text
Producer: ghi report.tmp → flush/close → rename thành report.ready
Consumer: chỉ xử lý file *.ready
~~~

Đây là mô hình thiết kế minh họa; tính nguyên tử của rename còn phụ thuộc filesystem và lựa chọn API, không nên giả định luôn đúng xuyên filesystem.

### File biến mất giữa list và read

Sau `Files.list(dir)`, file có thể bị xóa trước khi `Files.readAttributes(...)` hoặc `Files.readString(...)`. `NoSuchFileException` là một race bình thường trong môi trường có thay đổi liên tục. Một scanner production cần xử lý lỗi từng item, đánh dấu retry và giới hạn vòng scan khi thư mục không ổn định.

### Mức chính xác của metadata

Nếu file bị sửa nhưng vẫn giữ kích thước và timestamp, signature dựa trên `size + mtime` có thể không đổi. Hash nội dung phát hiện nhiều trường hợp hơn, nhưng đắt và cũng gặp race khi file đang ghi. Chọn cơ chế theo yêu cầu nghiệp vụ, thay vì mặc định metadata nhanh là bằng chứng file bất biến.

## 9. OVERFLOW không giải quyết bằng tăng tốc vô hạn

Nếu OVERFLOW thường xuyên, đó là tín hiệu hệ thống không theo kịp lưu lượng thay đổi hoặc provider có giới hạn riêng. Có thể cải thiện:

- Giữ thread lấy WatchKey nhẹ: nhanh chóng nhận, phân loại và reset key.
- Gộp nhiều sự kiện liên tiếp liên quan tới cùng file/directory.
- Hạn chế rescan trùng lặp và chia giai đoạn scan thư mục lớn.
- Ghi nhận số lần OVERFLOW, độ trễ từ event tới xử lý, độ dài backlog và thời gian quét để phát hiện quá tải.
- Nếu hệ thống phải xử lý từng tác vụ, chuyển nguồn sự thật sang journal/manifest/queue bền vững và dùng WatchService làm tín hiệu đánh thức.
- Định kỳ đối chiếu trạng thái ngay cả khi không có OVERFLOW nếu tính đúng đắn quan trọng hơn hiệu năng.

Không nên chỉ giả định cấp phát buffer ở tầng ứng dụng lớn hơn sẽ loại trừ mọi OVERFLOW: khả năng xếp hàng và thông báo nằm ở provider và OS, không hoàn toàn do kích thước ByteBuffer hay queue tự tạo trong Java quyết định.

## 10. Các lỗi phổ biến

**Lỗi 1 — Bỏ qua OVERFLOW.** Ứng dụng tiếp tục tin tưởng snapshot cũ và bỏ sót file. Cần đánh dấu dirty rồi reconcile.

**Lỗi 2 — Ép context của OVERFLOW thành Path.** OVERFLOW không mang danh sách file bị mất event. Không dựa vào context để đoán một đường dẫn cụ thể.

**Lỗi 3 — Nghĩ rescan phục hồi mọi sự kiện quá khứ.** Nó chủ yếu phục hồi trạng thái hiện tại; tạo-rồi-xóa rất nhanh có thể không còn dấu vết.

**Lỗi 4 — Quét baseline trước rồi mới register watcher.** Sự kiện ở khoảng hở có thể mất. Register trước, scan sau và xử lý event đến trong lúc scan.

**Lỗi 5 — Không reset key.** Sau `pollEvents()` phải `key.reset()`; nếu trả false thì xử lý registration không còn hiệu lực.

**Lỗi 6 — Cho rằng đăng ký root tự theo dõi đệ quy.** Cần đăng ký các subdirectory và tái đồng bộ chúng khi có thay đổi cây.

**Lỗi 7 — Quét rất lâu trong watcher thread.** Việc chậm lấy event có thể tạo OVERFLOW mới. Chuyển scan nặng sang worker có quản lý dirty.

**Lỗi 8 — Xóa dirty quá sớm.** Một OVERFLOW mới trong khi scan đang chạy có thể bị ghi đè trạng thái. Dùng generation hoặc chính sách đồng bộ.

**Lỗi 9 — Tin rằng mtime/size phát hiện mọi thay đổi.** Metadata có thể không đổi dù payload đã đổi; ứng dụng có yêu cầu chặt cần checksum/version.

**Lỗi 10 — Dùng WatchService như queue exactly-once.** API không lưu bền hoặc replay đầy đủ các sự kiện; cần giao thức xử lý công việc riêng.

## 11. Tự kiểm tra

1. `OVERFLOW` nói gì? **Có thể đã mất hoặc loại bỏ sự kiện**; danh sách sự kiện đã đọc không còn đầy đủ.
2. Vì sao phải quét lại? **So sánh trạng thái filesystem hiện tại với snapshot cũ** để tìm thêm/xóa/đổi vẫn quan sát được.
3. Có tìm được một file đã tạo rồi xóa giữa hai lần scan không? **Không bảo đảm**.
4. Có thể dùng `event.context()` từ OVERFLOW để tìm tên file bị mất event không? **Không**.
5. Sau `key.pollEvents()` cần gọi gì? **`key.reset()`**; xử lý khi kết quả false.
6. Theo dõi directory cha có tự theo dõi mọi cấp con không? **Không**.
7. Vì sao register trước baseline? **Giảm khoảng hở không có khả năng nhận event**.
8. Nếu filesystem thay đổi trong lúc scan, snapshot có atomic không? **Không**; cần retry/reconcile theo chính sách.
9. Nếu trùng thời điểm rescan xong lại có OVERFLOW, làm sao tránh mất tín hiệu? **Dùng dirty-generation và không xóa cờ mới một cách vô điều kiện**.
10. Nếu hệ thống cần exactly-once, có nên chỉ dùng WatchService không? **Không**; cần nguồn sự thật bền vững, idempotency và xác nhận xử lý.

**Ghi nhớ:** `WatchService` là cơ chế **thông báo**, không phải nhật ký thay đổi bảo đảm đầy đủ. `StandardWatchEventKinds.OVERFLOW` là tín hiệu phải **ngừng tin rằng mọi event đã được quan sát** và **quét lại trạng thái thực tế**. Hãy so sánh snapshot, cập nhật cache/index, tiếp tục xử lý event mới, quản lý `WatchKey.reset()`, registration đệ quy nếu cần và race khi quét. Mục tiêu đạt được là **hội tụ với trạng thái filesystem**, không phục hồi lịch sử đã mất.
