# Java 7 — WatchService: Giới hạn bảo đảm theo nhà cung cấp và hệ thống tệp

## 1. Bài toán cần hiểu: sự kiện tệp không phải nhật ký đầy đủ

`java.nio.file.WatchService` là API NIO.2 giúp chương trình **nhận thông báo khi các entry trong thư mục được đăng ký có thay đổi**. Ví dụ, ứng dụng muốn biết có file mới trong thư mục nhập dữ liệu, IDE muốn cập nhật cây dự án khi tên tệp đổi, hoặc một dịch vụ muốn quét lại khi người dùng thêm/xóa tài liệu.

API này có từ **Java 7**, và vẫn là kiến thức **hiện hành trong Java 17+**. Tuy nhiên, nó không cung cấp một nhật ký sự kiện có các bảo đảm chặt chẽ giống transaction log hoặc message queue bền vững. Theo đặc tả Java SE 17:

- Cách provider phát hiện thay đổi có thể dựa trên **cơ chế thông báo native** của hệ điều hành hoặc **polling**.
- **Thời điểm** nhận sự kiện, **thứ tự** và **số lần** một thay đổi được báo có thể khác nhau.
- Một file được tạo rồi xóa rất nhanh **có thể không được quan sát**, đặc biệt với provider quét theo chu kỳ.
- Thay đổi trên **network/remote filesystem** do hệ thống khác thực hiện **không được bảo đảm phát hiện**.
- Sự kiện `ENTRY_MODIFY` **không bảo đảm người ghi đã ghi xong**.
- Hệ thống có thể gộp sự kiện trùng, mất sự kiện khi hàng đợi đầy và báo `OVERFLOW` khi implementation biết có sự kiện bị loại bỏ.
- `WatchService` không lưu lại sự kiện qua lúc tiến trình bị dừng; không thay thế việc **quét trạng thái thực tế** của thư mục.

**Mục tiêu của bài:** hiểu ranh giới giữa điều Java API bảo đảm và điều thuộc về `FileSystemProvider`/hệ điều hành, để viết bộ theo dõi thư mục có khả năng **đối soát trạng thái, phát hiện mất sự kiện, phục hồi và xử lý đồng thời**.

Bài không giả định mọi OS đều là Windows hoặc Linux, không dựa vào API nội bộ của JDK và không hứa rằng một thử nghiệm đơn lẻ chứng minh mọi filesystem đều hành xử giống nhau.

## 2. Mô hình cơ bản: FileSystem, WatchService, Watchable, WatchKey và WatchEvent

Một lượt theo dõi thông thường có sơ đồ:

```text
FileSystem (provider)
  │
  └── newWatchService() ───────────────► WatchService
                                         │
Path của thư mục ─ register(...) ──────► WatchKey
                                         │
Hệ thống phát hiện thay đổi                │
   → key signalled                         │
   → key enqueued ────────────────────────► watcher.poll()/take()
                                         │
                                         ▼
                                    key.pollEvents()
                                         │
                                         ├─ ENTRY_CREATE
                                         ├─ ENTRY_DELETE
                                         ├─ ENTRY_MODIFY
                                         └─ OVERFLOW
                                         │
                                         ▼
                                 Xử lý + key.reset()
                                         │
                                         ▼
                                Lắng nghe lượt tiếp theo
```

**Các thành phần:**

- `FileSystem` thuộc một provider cụ thể. Gọi `fileSystem.newWatchService()` để tạo dịch vụ theo dõi của provider đó.
- `Path` là một `Watchable` và được đăng ký qua `path.register(watcher, kinds...)`.
- `WatchService` là tài nguyên phải **đóng**; nó sở hữu hàng đợi các key đã được báo hiệu.
- `WatchKey` đại diện cho **đăng ký** của một Watchable với một WatchService, không phải một sự kiện riêng lẻ.
- `WatchEvent<?>` chứa `kind()`, `context()` và `count()`.
- `StandardWatchEventKinds` có các kind chuẩn `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY` và `OVERFLOW`.

Trong ví dụ phổ biến, một **thư mục** được đăng ký; các sự kiện entry là **mục con trực tiếp** của thư mục đó, không phải thông tin đầy đủ về nội dung file. Không tự coi việc đăng ký một thư mục là đăng ký toàn bộ cây đệ quy.

### 2.1. Đoạn đăng ký tối thiểu

```java
Path directory = Path.of("incoming");
try (WatchService watcher =
        directory.getFileSystem().newWatchService()) {

    WatchKey key = directory.register(watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_DELETE,
            StandardWatchEventKinds.ENTRY_MODIFY);

    // Đọc WatchKey và xử lý sự kiện trong phạm vi watcher còn mở.
}
```

Đây là **snippet đặt trong một phương thức** có imports thuộc `java.nio.file` và xử lý `IOException`. `Path.of` có từ Java 11 nên phù hợp Java 17+; `WatchService`, `register` và các event kinds đã có từ Java 7.

**Đừng tạo một WatchService của default FileSystem rồi đăng ký Path thuộc ZIP/custom provider khác.** Tốt nhất dùng `directory.getFileSystem().newWatchService()` để lấy service phù hợp với Path, đồng thời chuẩn bị xử lý provider không hỗ trợ theo dõi.

### 2.2. Những điều không được suy ra từ việc đăng ký thành công

`directory.register(...)` trả một WatchKey hợp lệ không có nghĩa:

- Tất cả loại sự kiện có thể xảy ra trong tương lai đều sẽ được giao.
- Toàn bộ thao tác trên file bên trong directory đều được phát hiện.
- File từ network share sẽ báo sự kiện do một máy khác ghi.
- Mọi thư mục con cũng được tự động theo dõi.
- Sẽ có đúng một WatchEvent cho một hành động của người dùng.
- Event sẽ đến ngay sau một số mili giây cố định.
- Path được đăng ký sẽ giữ nguyên nội dung hoặc vị trí khi thư mục bị đổi tên.

Đăng ký chỉ thiết lập **một hợp đồng theo dõi theo khả năng của provider**, với các giới hạn nêu trong Java API.

## 3. Bảng phân biệt điều được bảo đảm và điều phụ thuộc provider

| Khía cạnh | Điều Java SE 17 bảo đảm ở mức API | Điều không được bảo đảm |
| --- | --- | --- |
| Kinds chuẩn | Có `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY`, `OVERFLOW`; sự kiện được phân loại bằng `kind()` | Provider nào cũng phát hiện mọi thay đổi cụ thể |
| Thông báo | Key có thể được signalled/queued; caller dùng `poll/take` và `pollEvents` | Độ trễ cố định, thông báo thời gian thực |
| Số lượng | `count()` cho biết số lần sự kiện cùng kind/context được quan sát/gộp | Một lần lưu file = đúng một sự kiện |
| Thứ tự | Key và event có cơ chế hàng đợi được định nghĩa | Thứ tự tuyệt đối của mọi thao tác filesystem/OS được giữ trên mọi provider |
| Nội dung `context` | Với ENTRY event chuẩn, là `Path` **tương đối** so với thư mục được đăng ký | CONTEXT là absolute Path; context OVERFLOW luôn là Path |
| `OVERFLOW` | Khi implementation biết đã bỏ sự kiện, nó báo overflow để caller xem xét quét lại | Không có overflow ⇒ chắc chắn chưa bỏ sót thay đổi |
| `ENTRY_MODIFY` | Có thay đổi được quan sát đối với entry | Writer đã đóng file, flush, fsync, hoàn tất transaction |
| Directory recursion | Theo dõi entries của đường dẫn được đăng ký theo hợp đồng | Đăng ký parent sẽ tự đăng ký mọi subdirectory |
| WatchKey lifecycle | `reset()` trả tính hợp lệ; `cancel/close` làm key invalid | WatchKey của directory được move luôn lập tức invalid |
| Network filesystem | Có thể đăng ký khi provider cho phép | Thay đổi từ remote clients nhất định được phát hiện |
| Short-lived files | Có thể nhận thông báo nếu cơ chế phát hiện thấy | File tạo/xóa nhanh chắc chắn được ghi nhận |
| Sau restart | Tạo lại WatchService/đăng ký mới | Có replay lịch sử sự kiện khi service đã tắt |

**Nguyên tắc vận hành:** WatchService cung cấp **gợi ý rằng nên kiểm tra lại trạng thái**, không phải một nguồn sự thật duy nhất cho mọi thay đổi lịch sử.

## 4. Native notification và polling: vì sao hành vi khác nhau?

Java SE 17 cho phép provider ánh xạ tới cơ chế thông báo native của hệ điều hành khi có sẵn, hoặc dùng một giải pháp như **quét filesystem định kỳ**. Ứng dụng dùng cùng một mã Java nhưng nhận trải nghiệm khác nhau.

### 4.1. Provider dùng native notification

Một provider có thể đăng ký với cơ chế hệ điều hành để nhận tín hiệu thay đổi. Điều này thường có độ trễ thấp, nhưng không có nghĩa:

- Không bao giờ tràn hàng đợi OS.
- Mọi event đến đúng thứ tự của mọi thao tác đang diễn ra ở nhiều thread/process.
- Một lệnh ghi text chỉ tạo một `ENTRY_MODIFY`.
- Rename được diễn tả bằng một loại sự kiện đổi tên portable.
- File được báo modify đã ở trạng thái ổn định để parse.

Một chương trình có thể viết file bằng nhiều đợt, gây nhiều sự kiện modify, hoặc thư viện/IDE lưu file theo kiểu ghi file tạm rồi move vào vị trí đích, gây sự kiện create/delete khác với điều người dùng nghĩ là “Save”.

### 4.2. Provider dùng polling

Một provider kiểm tra trạng thái định kỳ có thể chỉ so sánh các bản chụp tình trạng thư mục theo chu kỳ.

```text
T=0 ms:  kiểm tra directory
T=80ms: file X được tạo
T=90ms: file X bị xóa
T=200ms: kiểm tra directory lần nữa
```

Trong ví dụ này, nếu provider chỉ nhìn trạng thái tại T=0 và T=200, nó có thể **không phát hiện** việc X từng xuất hiện. Đây là hạn chế được Javadoc `WatchService` nêu rõ cho file sống rất ngắn.

Vì vậy **đừng thiết kế job xử lý đúng-một-lần chỉ dựa vào event create** nếu một producer có thể tạo rồi xóa tệp giữa hai lần thăm dò. Nếu yêu cầu chắc chắn không mất job, dùng giao thức giao nhận có acknowledgement, durable queue, database hoặc cơ chế quản lý trạng thái khác.

### 4.3. Java không chuẩn hóa tần suất polling của provider

Không có một giá trị “mỗi 100 ms” hoặc “mỗi 5 giây” do WatchService API bắt buộc. Nếu cần thời gian phản hồi tối đa, phải thiết kế SLO ở tầng ứng dụng, chọn provider/hệ thống lưu trữ phù hợp, kiểm thử thực tế, và có chiến lược đối soát/tối ưu riêng.

**Không sử dụng các modifier nội bộ của nhà cung cấp JDK làm “chuẩn Java”.** `WatchEvent.Modifier` cho phép provider mở rộng việc đăng ký, nhưng tên/ý nghĩa modifier đặc thù không là hợp đồng portable của Java SE. Những thư viện nội bộ như các sensitivity modifiers ngoài API chuẩn có thể thay đổi hoặc không có trên JVM/provider khác.

## 5. Không có bảo đảm một thay đổi = một event

Ba loại entry-event chuẩn:

| Kind | Ý nghĩa trong API | Cần thận trọng |
| --- | --- | --- |
| `ENTRY_CREATE` | Một directory entry được tạo hoặc được rename **vào** directory được theo dõi | Không bảo đảm nội dung file đã hoàn tất |
| `ENTRY_DELETE` | Một directory entry bị xóa hoặc rename **ra khỏi** directory | Không nhất thiết có dữ liệu trước đó để xác định nó là file/thư mục |
| `ENTRY_MODIFY` | Một directory entry được phát hiện là đã sửa | Một thao tác ghi có thể tạo nhiều thông báo; count có thể lớn hơn 1 |

Một thao tác logic “lưu một tài liệu” của ứng dụng có thể gồm:

1. Tạo file tạm.
2. Ghi dữ liệu thành nhiều lần.
3. Flush/close file.
4. Đổi tên hoặc thay file cũ.
5. Cập nhật thuộc tính/metadata.

Trong WatchService, điều này có thể hiện ra thành **nhiều `ENTRY_CREATE/ENTRY_MODIFY/ENTRY_DELETE`** và số lượng/ thứ tự thay đổi theo hệ điều hành và cách triển khai. Java SE không định nghĩa một event “SAVE_COMPLETED” hay “TRANSACTION_COMMITTED”.

### 5.1. count() là gì?

`WatchEvent.count()` là số lần sự kiện cùng loại/ngữ cảnh được ghi nhận trong quá trình biểu diễn/gộp. Theo Javadoc Java SE 17:

- `ENTRY_CREATE` và `ENTRY_DELETE` có `count() == 1`.
- `ENTRY_MODIFY` có thể có `count() >= 1`.
- `OVERFLOW` có `count() >= 1` và context có thể null.

`count()` **không** đồng nghĩa số byte viết, số lần save thành công, số bản ghi trong file, hoặc số thao tác nghiệp vụ. Nó cũng không phải sequence number toàn cục để phát hiện mọi khoảng trống sự kiện.

### 5.2. Rename không có kind portable riêng

API chuẩn không có `ENTRY_RENAME` chung. Rename vào/ra một thư mục có thể được phản ánh qua create/delete, nhưng cách tạo chuỗi event cụ thể phụ thuộc provider. Không được xây thuật toán “ghép mọi DELETE với CREATE kế tiếp thành rename của cùng file” rồi coi đó là chắc chắn: có thể là hai file khác nhau hoặc có nhiều writer đồng thời.

Nếu ứng dụng cần biết danh tính hoặc quan hệ rename chính xác, phải có metadata hoặc giao thức tên/ID riêng được producer cung cấp, thay vì đoán từ thứ tự WatchEvent.

## 6. OVERFLOW: khi provider biết đã làm mất hoặc loại bỏ sự kiện

`StandardWatchEventKinds.OVERFLOW` là tín hiệu rằng **events may have been lost or discarded**. WatchService có thể có giới hạn hàng đợi sự kiện không được chuẩn hóa; khi implementation biết đã bỏ event, nó báo OVERFLOW qua `key.pollEvents()`. OVERFLOW tự được đăng ký theo hợp đồng; không cần đặt nó trong danh sách kinds khi gọi `register`.

Lỗi thường gặp là chỉ xử lý create/modify/delete và bỏ qua overflow:

```java
for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        // Không được giả định có đầy đủ lịch sử; cần đối soát lại.
        dirty = true;
        continue;
    }

    // Xử lý thông báo thông thường ở đây.
}
```

Đây là snippet **trong phương thức** với biến `WatchKey key` và boolean `dirty` đã được khai báo. Nó chỉ trình bày nhánh xử lý OVERFLOW.

### 6.1. Vì sao OVERFLOW cần quét lại?

Giả sử folder từng chứa `A.csv` và `B.csv`, sau đó rất nhiều event xảy ra khi consumer bận xử lý. Nếu queue tràn, danh sách sự kiện bạn nhận được không đầy đủ. Chỉ suy luận “tên được tạo/tên bị xóa” từ những event còn lại sẽ tạo một tập trạng thái sai.

Cách phục hồi đúng là **reconcile**: đọc lại **trạng thái hiện tại** bằng `DirectoryStream` hoặc `Files.list`, so sánh với catalog trạng thái do ứng dụng quản lý, rồi quyết định những mục cần xử lý. Nếu bạn cần lịch sử chính xác về các file đã có rồi biến mất trước khi quét, WatchService **không cung cấp** thông tin bị mất đó — phải dùng durable queue/log từ producer.

### 6.2. OVERFLOW không bảo đảm phát hiện mọi kiểu bỏ sót

Không được đảo ngược mệnh đề:

> Có OVERFLOW ⇒ có rủi ro thiếu sự kiện, cần quét lại.

thành:

> Không có OVERFLOW ⇒ đã nhận đủ 100% mọi thay đổi.

Ví dụ native watcher không thấy thay đổi từ remote machine, hoặc polling không bắt kịp file được tạo/xóa cực nhanh: đó là giới hạn phát hiện của provider, **không nhất thiết dẫn đến OVERFLOW**. Vì vậy một hệ thống cần tính nhất quán phải đối soát **định kỳ**, không chỉ sau OVERFLOW.

### 6.3. Không giả định context() của OVERFLOW là Path

Theo đặc tả, `WatchEvent.context()` của OVERFLOW có thể `null` hoặc chứa dữ liệu tùy implementation. Không ép kiểu `(Path) event.context()` **trước** khi kiểm tra kind, vì OVERFLOW không có hợp đồng context là Path.

```java
WatchEvent.Kind<?> kind = event.kind();
if (kind == StandardWatchEventKinds.OVERFLOW) {
    scheduleFullRescan(watchedDirectory);
    continue;
}

Object context = event.context();
if (context instanceof Path relativeName) {
    Path candidate = watchedDirectory.resolve(relativeName);
    scheduleCheck(candidate);
}
```

Đây là snippet Java 17+ **trong phương thức**. `scheduleFullRescan` và `scheduleCheck` là **hàm nghiệp vụ giả định**, chưa được định nghĩa; không phải chương trình độc lập.

## 7. Thời điểm nhận sự kiện không có giới hạn độ trễ chuẩn

`WatchService.poll()` là truy vấn không đợi; nếu chưa có key thì trả `null`. `poll(timeout, TimeUnit)` chờ tối đa theo timeout và có thể trả `null` khi không nhận key; `take()` đợi tới khi có key, hoặc bị interrupt/đóng service.

**Không được diễn giải `poll(timeout) == null` là “thư mục chắc chắn không đổi trong khoảng thời gian đó”.** Nó chỉ nói **không có signalled key được lấy từ service trong khung đợi**. Thay đổi có thể chưa được provider phát hiện hoặc đã không được thông báo.

### 7.1. Ví dụ chọn API chờ

```java
WatchKey key = watcher.poll(2, TimeUnit.SECONDS);
if (key == null) {
    // Timeout: không có key lúc này; có thể kích hoạt quét định kỳ.
}
```

Đây là snippet trong phương thức với biến `WatchService watcher`, import `java.util.concurrent.TimeUnit` và xử lý `InterruptedException`. Không hứa sẽ nhận event trong đúng hai giây; timeout chỉ giới hạn thời gian consumer chờ trong lời gọi.

### 7.2. Thời điểm giao sự kiện không phải thời điểm file sẵn sàng

Khi nhận `ENTRY_CREATE`, file có thể vừa được tạo **trước khi producer ghi toàn bộ dữ liệu**. Khi nhận `ENTRY_MODIFY`, producer **có thể vẫn đang mở file và tiếp tục ghi**, như Javadoc nói rõ.

Ví dụ producer ghi một file JSON 20 MB thành nhiều lần. Consumer bắt gặp create rồi mở file và parse ngay có thể đọc chuỗi JSON dở dang, nhận `EOFException` hoặc lỗi parser. **Đó là race hợp lệ**, không phải bug của parser.

Không chữa bằng một lệnh `Thread.sleep(500)` cố định rồi cho rằng dữ liệu đã đầy đủ. Cơ chế ổn định cần được **thỏa thuận với producer**, chẳng hạn:

- Producer ghi file tạm vào cùng filesystem, flush/close theo yêu cầu, rồi **publish bằng rename/move** có tính nguyên tử nếu supported.
- Producer tạo marker/manifest “ready” **sau khi hoàn tất nội dung**.
- Consumer dùng checksum, size expected, schema và retry có giới hạn.
- Nếu cần durability/crash consistency, thỏa thuận riêng về sync file/rename/directory metadata; một event không bảo đảm durable commit.

### 7.3. Không suy ra nội dung hoặc kiểu file từ event

`WatchEvent` không chứa bytes của file, owner, checksum, size hay kiểu entry. Khi nhận event, consumer cần đọc trạng thái thực bằng API `Files` và xử lý:

- File đã bị xóa/rename ngay sau event.
- File thay đổi giữa lúc kiểm tra size và lúc mở.
- Symlink dẫn ra ngoài thư mục allowed.
- Quyền/ACL và filesystem provider khác nhau.

Dùng event như một **trigger để kiểm tra trạng thái**, không dùng nó làm dữ liệu nguồn của file.

## 8. WatchKey: queued/signalled/reset và những giới hạn vòng đời

Mỗi đăng ký có WatchKey. Khi phát hiện thay đổi, key ở trạng thái **signalled** và được xếp vào WatchService queue. Một key đã signalled **không bị xếp vào queue lại liên tục** chỉ vì event mới tới: các event mới có thể được tích lũy trên chính key đó.

Sau khi xử lý các event, caller phải gọi:

```java
boolean valid = key.reset();
if (!valid) {
    // Directory không còn được đăng ký; quyết định tái lập theo dõi.
}
```

Đây là snippet trong phương thức có `WatchKey key`. Nếu key không valid do bị cancel, thư mục không thể truy cập hoặc service đóng, `reset()` trả false. Không dùng key đó như một đăng ký còn hoạt động.

### 8.1. Vì sao reset sau xử lý?

Một idiom chuẩn:

```java
while (true) {
    WatchKey key = watcher.take();
    for (WatchEvent<?> event : key.pollEvents()) {
        handleEvent(key, event);
    }
    if (!key.reset()) {
        break;
    }
}
```

Đây là **snippet minh họa**, `handleEvent` là hàm của ứng dụng, watcher được tạo trước và cần xử lý `InterruptedException`/`ClosedWatchServiceException`. Nếu không reset, key có thể vẫn signalled và bạn không nhận tiếp những lượt queue như mong muốn.

Trong chương trình nhiều consumer, tránh để hai thread cùng xử lý event cho một key và reset trước khi tất cả event được xử lý, vì điều đó phá cách phối hợp theo đăng ký.

### 8.2. WatchKey có thể invalid vì directory bị xóa

Một key có thể được cancel thủ công bằng `key.cancel()` hoặc bị vô hiệu khi directory không thể theo dõi nữa. Service đóng sẽ invalidate mọi key.

Đặc tả **không hứa directory bị đổi tên/move luôn tự động invalid WatchKey**. Javadoc của `WatchKey.watchable()` nói rõ khi directory được move/rename, việc key có bị cancel hay không và tính hợp lệ của Path trả về phụ thuộc implementation.

**Hệ quả:** `key.isValid() == true` không có nghĩa `(Path)key.watchable()` vẫn là tên directory hiện tồn tại ở vị trí cũ. Nếu ứng dụng yêu cầu path cố định, phải xác minh lại và có khả năng đăng ký mới.

### 8.3. pollEvents làm gì?

`key.pollEvents()` lấy và **loại khỏi hàng chờ của key** tất cả event đang tích lũy tại thời điểm gọi; nó có thể trả list rỗng. Đây không phải API truy vấn toàn bộ lịch sử. Sau khi key được reset, những event mới có thể lại khiến key signalled.

Một key có thể đã bị cancel nhưng còn nằm trong WatchService queue để consumer lấy ra; đừng giả định `cancel()` sẽ xóa ngay mọi thứ khỏi hàng đợi. Sau khi xử lý, kiểm tra `reset()`/`isValid()`.

## 9. Phạm vi theo dõi không tự recursive

Đăng ký:

```java
root.register(watcher, StandardWatchEventKinds.ENTRY_CREATE);
```

thường được dùng để theo dõi **entry trực tiếp** trong `root`. Nếu `root/sub/child.txt` được tạo, việc chỉ đăng ký root **không bảo đảm** nhận event cho file nằm sâu trong subdirectory. Bạn có thể nhận event khi `sub` được tạo — vì sub là **entry trực tiếp** — nhưng không tự được đăng ký thay đổi bên trong sub.

### 9.1. Muốn theo dõi cả cây, phải quản lý nhiều đăng ký

Một kiến trúc phổ biến:

1. Quét toàn bộ cây thư mục hiện có.
2. Đăng ký mỗi directory cần theo dõi.
3. Khi thấy directory mới được tạo hoặc di chuyển vào cây, đăng ký nó và **quét các file bên trong** để tránh khoảng mù giữa create và register.
4. Khi một key invalid, cập nhật bản đồ đăng ký và xem xét có cần đăng ký lại không.
5. Theo chu kỳ, **đối soát lại cây** để tìm directory bị bỏ sót do overflow/race.
6. Có giới hạn độ sâu, số lượng WatchKey và chính sách symbolic link.

Một đoạn mã minh họa đăng ký một directory:

```java
WatchKey key = directory.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_DELETE,
        StandardWatchEventKinds.ENTRY_MODIFY);

directoriesByKey.put(key, directory);
```

Đây là snippet có `WatchService watcher`, `Path directory` và `Map<WatchKey, Path> directoriesByKey` đã khai báo. Nó **không** thể tự đăng ký toàn cây; cần thêm vòng quét và xử lý lifecycle. Không lưu Path parent duy nhất để resolve context của key đến từ subdir: mỗi key phải được map tới directory tương ứng.

### 9.2. Vấn đề lúc đăng ký directory mới

Khi thấy event báo có `sub/` mới:

- Producer có thể đã tạo `sub/a.csv` trước khi consumer kịp đăng ký `sub`.
- Event tạo `a.csv` **có thể bị bỏ lỡ** vì lúc đó `sub` chưa có key.
- Vì vậy sau khi đăng ký `sub` phải **quét nội dung thực** trong `sub` để xử lý những file đã có.

Không thể bảo đảm bỏ hết mọi race với một lần scan đơn giản nếu producer tiếp tục thay đổi; workflow quan trọng cần idempotency, phối hợp với producer hoặc durable queue.

## 10. Network filesystem, ZIP và các FileSystemProvider khác

### 10.1. Local file store không đại diện cho mọi provider

Trên một hệ thống, Path có thể đến từ:

- Filesystem native/default trên ổ đĩa cục bộ.
- Network share hoặc mount từ máy khác.
- ZIP file system do `jdk.zipfs` cung cấp.
- Memory/virtual file system hoặc provider do bên thứ ba phát triển.

Các provider không bắt buộc có cùng cơ chế theo dõi, độ trễ, coverage và modifiers. `Path.register` có thể thành công nhưng semantics cụ thể vẫn khác. Với provider không hỗ trợ tạo WatchService hoặc loại event được yêu cầu, có thể nhận `UnsupportedOperationException` hoặc một lỗi phù hợp.

**Không dựa vào tên hệ điều hành để đoán.** Điều cần biết là provider cụ thể của Path, FileStore nằm dưới, môi trường triển khai và quyền truy cập thực.

### 10.2. Trường hợp remote là giới hạn đã được đặc tả

Javadoc `WatchService` ghi rằng nếu file không nằm trên local storage device thì việc có phát hiện được thay đổi hay không **phụ thuộc implementation**. Đặc biệt, API **không yêu cầu** phát hiện thay đổi được thực hiện từ remote systems.

Ví dụ hai máy A/B cùng thấy network directory:

```text
Máy A: Java WatchService đăng ký \\server\shared\incoming
Máy B: ứng dụng khác tạo new.csv trên network share
Máy A: có thể nhận hoặc không nhận ENTRY_CREATE
```

Đây là tình huống khái niệm, không phải cú pháp chạy được trên mọi OS. Một thử nghiệm mà bạn thấy event trên một network share không biến hành vi đó thành bảo đảm chung cho mọi share/provider/version.

Nếu nghiệp vụ yêu cầu **không mất dữ liệu khi thay đổi đến từ xa**, dùng giao thức publish/queue, API sự kiện của hệ thống lưu trữ có hợp đồng rõ, hoặc quét định kỳ và đối soát thay vì chỉ lắng nghe WatchService.

### 10.3. ZIP FileSystem không được mặc định có WatchService

ZIP filesystem cung cấp các thao tác Path/Files nhưng không có nghĩa mọi API NIO.2 đều được hỗ trợ giống thư mục native. Với Path nằm trong ZIP, hãy hỏi chính `path.getFileSystem()` và xử lý khi `newWatchService/register` không hỗ trợ. Không nhận WatchService của default filesystem rồi cố đăng ký Path của ZIP vào đó.

### 10.4. Mount, rename, permission và thư mục biến mất

Một directory có thể bị:

- Đổi tên hoặc move.
- Xóa hay thay thế.
- Unmount.
- Mất quyền đọc.
- Network disconnect.
- Trở thành một đối tượng khác ở cùng đường dẫn.

Khi đó key có thể invalid, có thể tiếp tục hợp lệ nhưng `watchable()` chứa path không còn đúng, hoặc service có thể không báo đầy đủ biến động. Ứng dụng cần **kiểm tra tính sẵn sàng**, log tình trạng watch và tái lập đăng ký khi cần; không coi một key đã cấp là bất biến vĩnh viễn.

## 11. Java 17+ — chương trình hoàn chỉnh minh họa giới hạn của provider

Ví dụ dưới đây an toàn cho học tập: nó tạo một thư mục tạm, đăng ký WatchService của **cùng FileSystem**, tạo file và thư mục con, nhận thông báo **có timeout** rồi **quét lại trạng thái thực**. Nó **không** cố chứng minh mỗi thao tác phải sinh một event; các con số quan sát được được in ra để người học thấy tính biến thiên.

Tạo file **`WatchLimitsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class WatchLimitsDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("watch-limits-demo-");
        try {
            try (WatchService watcher = root.getFileSystem().newWatchService()) {
                WatchKey registration = root.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_DELETE,
                        StandardWatchEventKinds.ENTRY_MODIFY);
                System.out.println("registered = " + registration.isValid());

                Files.writeString(root.resolve("report.txt"), "ready",
                        StandardCharsets.UTF_8);
                Files.createDirectory(root.resolve("child"));
                Files.writeString(root.resolve("child").resolve("deep.txt"),
                        "nested", StandardCharsets.UTF_8);

                int received = 0;
                int overflow = 0;
                int relativePaths = 0;

                WatchKey signalled = watcher.poll(2, TimeUnit.SECONDS);
                while (signalled != null) {
                    for (WatchEvent<?> event : signalled.pollEvents()) {
                        if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                            overflow++;
                            continue;
                        }
                        if (event.context() instanceof Path relative) {
                            relativePaths++;
                            Path changed = ((Path) signalled.watchable())
                                    .resolve(relative);
                            // "changed" là Path ứng viên, không bảo đảm còn tồn tại.
                        }
                        received += event.count();
                    }
                    boolean valid = signalled.reset();
                    if (!valid) break;
                    signalled = watcher.poll();
                }

                List<String> direct = new ArrayList<>();
                try (DirectoryStream<Path> children =
                        Files.newDirectoryStream(root)) {
                    for (Path entry : children) {
                        direct.add(entry.getFileName().toString());
                    }
                }
                Collections.sort(direct);

                System.out.println("rescan direct = " + direct);
                System.out.println("nested listed directly = " +
                        direct.contains("deep.txt"));
                System.out.println("registration still valid = " +
                        registration.isValid());
                System.out.println("observed notifications = " + received);
                System.out.println("relative-path contexts = " + relativePaths);
                System.out.println("overflow indications = " + overflow);
            }
        } finally {
            Files.deleteIfExists(root.resolve("child").resolve("deep.txt"));
            Files.deleteIfExists(root.resolve("child"));
            Files.deleteIfExists(root.resolve("report.txt"));
            Files.deleteIfExists(root);
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 17 WatchLimitsDemo.java
java WatchLimitsDemo
```

**Kết quả thực nghiệm trên Windows với JDK 24 và local filesystem (chỉ là một lần quan sát):**

```text
registered = true
rescan direct = [child, report.txt]
nested listed directly = false
registration still valid = true
observed notifications = 4
relative-path contexts = 3
overflow indications = 0
```

**Ý nghĩa cần đọc đúng:**

1. `registered = true`: provider cho đăng ký watch đối với thư mục tạm ở lần chạy này.
2. `rescan direct = [child, report.txt]`: việc **quét filesystem thật** cho thấy hai entry trực tiếp vẫn hiện hữu sau khi các thao tác tạo đã hoàn tất.
3. `nested listed directly = false`: file `deep.txt` ở trong `child/`, không là entry trực tiếp của root; đăng ký root không có nghĩa tự theo dõi file sâu này.
4. `registration still valid = true`: trong thử nghiệm này key chưa bị hủy; không có nghĩa key vĩnh viễn hợp lệ.
5. `observed notifications = 4`: tổng `count()` của những entry events mà provider đã đưa tới trong vòng poll ngắn. Đây **không phải số file, số thao tác ghi hay số job thành công**.
6. `relative-path contexts = 3`: có ba WatchEvent thông thường mang context là Path. Một event có thể có `count() > 1`, nên con số 3 và 4 **có thể khác nhau**.
7. `overflow indications = 0`: lần chạy đó không nhận OVERFLOW; điều này **không chứng minh mọi thay đổi khác trên filesystem đều được phát hiện**.

**Các dòng phụ thuộc môi trường:** `observed notifications`, `relative-path contexts`, `overflow indications`. Nếu provider không phát hiện sự kiện trước timeout, hai con số observed có thể bằng 0 dù file đã tồn tại. Nếu có gộp nhiều modify, số notifications có thể lớn hơn số context. Không đưa một stdout duy nhất làm yêu cầu bắt buộc trên mọi OS.

**Giới hạn của ví dụ:** Nó chỉ đăng ký một thư mục local; không cố ép queue tràn, không mô phỏng mọi network provider và không thiết kế xử lý crash/retry hoàn chỉnh. Nếu provider không hỗ trợ `newWatchService` hoặc các event kinds, có thể ném `UnsupportedOperationException`. Nếu lỗi tạo/quét/xóa file, có thể ném `IOException`. `try-with-resources` đóng watcher và directory stream, còn `finally` chỉ xóa file/thư mục tạm mà chương trình tạo.

### 11.1. Tại sao ví dụ quét lại ngay cả khi event đã đến?

Vì câu hỏi nghiệp vụ thường là **“những file nào đang hiện hữu và cần xử lý?”**, không phải **“provider vừa thông báo bao nhiêu event?”**. Quét thực tế cung cấp dữ liệu hiện tại tốt hơn việc đếm event để suy luận trạng thái.

Tuy nhiên, một lượt `DirectoryStream`/`Files.list` cũng **không phải snapshot nguyên tử** nếu directory thay đổi đồng thời. Với yêu cầu chính xác cao, cần coordinator/producer contract, idempotency hoặc storage khác.

## 12. context() của WatchEvent phải được resolve theo key.watchable()

Với `ENTRY_CREATE`, `ENTRY_DELETE` và `ENTRY_MODIFY`, `event.context()` có kiểu `Path` và **tương đối với directory được đăng ký**. Nó không phải absolute Path, không chứa nội dung file, và không bảo đảm entry vẫn tồn tại khi caller xử lý.

Mẫu đúng:

```java
Object context = event.context();
if (context instanceof Path relativeName) {
    Path watchedDir = (Path) key.watchable();
    Path candidate = watchedDir.resolve(relativeName);

    // Kiểm tra trạng thái tại thời điểm sử dụng candidate.
}
```

Đây là snippet Java 17+ bên trong phương thức với `WatchEvent<?> event` và `WatchKey key`. Vì `watchable()` là một Watchable, cast sang Path thích hợp trong trường hợp ta đăng ký **Path directory**. Nếu provider đăng ký loại Watchable khác, không được ép kiểu như vậy.

**Lỗi phổ biến:** gọi `Path.of(event.context().toString())`, làm mất directory gốc và có thể tạo Path của default provider khác. Khi theo dõi nhiều thư mục con, dùng `key.watchable()` hoặc map `WatchKey → Path` chính xác cho từng registration.

### 12.1. Không giả định candidate còn tồn tại

Tại thời điểm nhận `ENTRY_CREATE`:

```java
if (Files.isRegularFile(candidate)) {
    // Có thể là file thường ngay lúc kiểm tra; nhưng có thể đổi sau đó.
}
```

File có thể đã bị xóa hoặc thay thế bởi symbolic link. Nếu hệ thống lấy Path từ directory không tin cậy, còn có rủi ro *time-of-check/time-of-use* (TOCTOU). Không dùng `event.kind() == ENTRY_CREATE` làm chứng cứ tệp an toàn để mở hoặc nằm trong root được phép.

### 12.2. OVERFLOW không có relative Path bắt buộc

Vì context của OVERFLOW có thể null/implementation-specific, hãy **kiểm tra kind trước**, rồi chỉ resolve những event chuẩn có context là Path. Đây là pattern portable Java 17+.

## 13. Thiết kế đối soát: WatchService chỉ là bộ kích hoạt

Một thiết kế thực tế thường gồm hai luồng logic:

1. **Thông báo sớm:** WatchService đánh dấu thư mục/entry “cần kiểm tra”, để giảm độ trễ khi thay đổi được nhận.
2. **Đối soát theo trạng thái:** định kỳ quét những nơi được quản lý, tìm file hiện hữu, so với danh sách/id nghiệp vụ và xử lý theo logic idempotent.

```text
                    WatchService
                       │
          CREATE / DELETE / MODIFY / OVERFLOW
                       │
                       ▼
                Mark directory dirty
                       │
                       ▼
           Queue bounded, coalesced rescan
                       │
                       ▼
                 Scan current state ◄── periodic reconciliation
                       │
                       ▼
                 Validate candidates
                       │
                       ▼
               Claim / process / ack
                       │
                       ▼
          Persist durable result or checkpoint
```

**Điểm mạnh:** hệ thống không bắt buộc tin rằng mọi event được phát hiện. Nếu đã có thay đổi nhưng event bị bỏ sót, periodic reconciliation có cơ hội nhận ra **file còn hiện hữu**.

**Giới hạn:** Một file được tạo rồi xóa trước cả sự kiện lẫn lượt quét không thể được phục hồi bằng việc đọc trạng thái hiện tại. Nếu phải chứng minh nó từng tồn tại, cần một **nguồn lịch sử bền vững từ producer** — queue/database/append-only log hoặc giao thức tương đương.

### 13.1. Quét một cấp với DirectoryStream

```java
static List<Path> snapshotDirectEntries(Path directory) throws IOException {
    List<Path> result = new ArrayList<>();
    try (DirectoryStream<Path> stream =
            Files.newDirectoryStream(directory)) {
        for (Path entry : stream) {
            result.add(entry);
        }
    } catch (DirectoryIteratorException ex) {
        throw ex.getCause();
    }
    return result;
}
```

Đây là **phương thức minh họa**, cần import `List`, `ArrayList`, `DirectoryStream`, `Files`, `Path`, `DirectoryIteratorException` và `IOException`. Kết quả là các entry *được thấy trong lần duyệt*, không phải snapshot atomic. Stream được đóng nhờ TWR.

Trong bộ theo dõi có tính sẵn sàng cao, đừng chạy một lượt scan lớn **bên trong loop xử lý key** nếu có thể gây chậm nhận event và tăng nguy cơ overflow. Đánh dấu dirty rồi chuyển công việc scan cho worker pool có giới hạn và chống trùng.

### 13.2. Dùng set tên có đủ không?

Nếu chỉ quan tâm file tồn tại hay không, một tập tên có thể đủ để phát hiện nhiều thay đổi. Nhưng để xử lý `ENTRY_MODIFY` hoặc update in place, cần cân nhắc thêm size, lastModifiedTime, checksum, version hoặc ID do producer cung cấp. **Không dùng riêng size + mtime làm danh tính tuyệt đối của nội dung**: hai phiên bản có thể có cùng size và timestamp resolution phụ thuộc filesystem.

Nếu nghiệp vụ cần exactly-once, phải thiết kế transaction/acknowledgement ở tầng ứng dụng; không dựa vào WatchEvent count, mtime hay tên file duy nhất.

## 14. Khoảng mù giữa đăng ký và quét ban đầu

Có hai cách khởi tạo tưởng hợp lý nhưng đều có race nếu không phối hợp:

### 14.1. Quét trước rồi đăng ký

```text
T1: ứng dụng quét incoming/
T2: producer tạo A.csv
T3: ứng dụng mới register WatchService
```

Nếu A.csv được tạo ở T2, ứng dụng có thể **không thấy A ở scan T1** và cũng **không nhận event cho thay đổi xảy ra trước T3**.

### 14.2. Đăng ký trước rồi quét

```text
T1: ứng dụng register WatchService
T2: ứng dụng quét incoming/
T3: producer tạo A.csv
T4: WatchService báo ENTRY_CREATE
```

Cách này thường phù hợp hơn để giảm khoảng mù ban đầu, nhưng có thể tạo **xử lý trùng**: một entry xuất hiện trong kết quả quét và cũng có event. Ngoài ra, bản thân lượt scan không atomic nếu thư mục thay đổi liên tục.

### 14.3. Thiết kế đúng theo yêu cầu

Một quy trình tham khảo:

1. Register watcher.
2. Quét trạng thái hiện tại.
3. Xử lý event đã tích lũy, nhưng **idempotent** theo ID và version.
4. Đối soát lại khi cần và tiếp tục quét định kỳ.
5. Nếu yêu cầu chính xác tuyệt đối về mọi thao tác lịch sử, sử dụng giao thức bền vững từ producer.

Không có một câu thần chú “watch rồi scan” bảo đảm exactly-once mà không cần điều phối các writer. Cần xác định bài toán chỉ muốn “cuối cùng xử lý mọi file còn nằm trong thư mục” hay bắt buộc “lưu vết từng lần xuất hiện”.

## 15. Crash, restart, mất kết nối và nguồn sự kiện không bền vững

Một `WatchService` sống trong tiến trình. Khi ứng dụng dừng hoặc mất kết nối, **không có cơ chế replay chuẩn của WatchService** cho những thay đổi xảy ra trong thời gian tắt.

Sau restart:

- Tạo WatchService mới.
- Đăng ký lại các directory cần theo dõi.
- Quét đầy đủ trạng thái hiện tại để khôi phục catalog.
- Xử lý những file hiện còn nhưng chưa được xử lý/acknowledged.
- Dùng checkpoint bền vững và idempotency để tránh xử lý trùng.
- Nếu file đã bị xóa trước restart, phải dựa vào nguồn lịch sử khác để biết đã từng có file đó.

### 15.1. Invalid key và service closed

`WatchKey.reset() == false` là tín hiệu đăng ký không còn hợp lệ. Tùy nguyên nhân, có thể cần kiểm tra directory còn tồn tại không và đăng ký lại sau khi phục hồi. Không retry vô hạn với một Path đã mất quyền truy cập.

Khi `WatchService.close()` được gọi, các lời gọi `take/poll` sẽ ném `ClosedWatchServiceException`. Đây là điều kiện lifecycle bình thường nếu shutdown được chủ động thực hiện. Hãy thiết kế cờ dừng và đóng service có chủ đích thay vì catch mọi runtime exception rồi tiếp tục vòng lặp vô hạn.

### 15.2. InterruptedException của take/poll

`take()` và `poll(timeout, unit)` có thể ném `InterruptedException`. Trong ứng dụng nhiều thread, nếu thread bị interrupt, thường cần **khôi phục interrupt flag** và thoát loop hoặc để tầng trên xử lý:

```java
try {
    WatchKey key = watcher.take();
    processKey(key);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là **snippet trong phương thức** cho phép `return`, với hàm `processKey` của ứng dụng. Cần xử lý `ClosedWatchServiceException` trong luồng shutdown hoặc tùy mục tiêu quản lý vòng đời.

### 15.3. Không nuốt mọi exception

Nếu code có `catch (Exception ignored)` quanh vòng WatchService, service có thể dừng theo dõi âm thầm: đã đóng, key invalid, provider lỗi hoặc thread bị interrupt. Cần log/metric và chính sách xử lý lỗi rõ ràng. Bắt lỗi I/O/unsupported ở giai đoạn tạo/đăng ký khác với nhận event và khác với lỗi trong job xử lý file.

## 16. Rủi ro OVERFLOW do consumer chậm

Ngay cả khi provider phát hiện được events, **ứng dụng xử lý quá chậm** cũng có thể làm hàng đợi tích lũy vượt giới hạn.

Phương án hữu ích:

- Đọc và nhận key kịp thời, nhưng **không xử lý file hàng phút ngay trong thread listener**.
- Dùng bounded queue để chuyển các Path/dirty-directory cho worker; khi quá tải, gộp các yêu cầu scan cùng directory.
- Ghi metrics về `OVERFLOW`, timeout, invalid keys, số directory được đăng ký, thời gian xử lý event và thời gian đối soát.
- Khi quá tải, ưu tiên **rescan trạng thái** thay vì cố diễn giải một danh sách event đã biết là thiếu.
- Nếu queue nội bộ bị tràn, cũng cần có cơ chế **mark dirty** thay vì âm thầm bỏ nhiệm vụ.
- Sử dụng rate limit/backpressure cho producer nếu có quyền điều phối.

**Không dùng count() để biết chắc mức độ tổn thất.** Nó đếm repeated events đã quan sát/gộp, không đo số sự kiện không được provider phát hiện hoặc đã bị đánh mất trước khi vào WatchService.

## 17. Security: symlink, đường dẫn tương đối và TOCTOU

`event.context()` đối với ENTRY events là một **relative Path**. Nhưng:

1. Relative Path không tự chứng minh entry an toàn hoặc vẫn nằm dưới root sau khi theo symlink.
2. Một entry có thể bị xóa/đổi giữa lúc event được ghi nhận và lúc ứng dụng mở.
3. Symlink trong thư mục được theo dõi có thể trỏ ra ngoài vùng được phép.
4. Nếu directory cha bị move/rename, `key.watchable()` có thể trỏ tới path không còn hiện hữu.
5. Một chương trình khác có thể cố tạo nhiều entry để gây bão sự kiện/overflow, hoặc tạo file có tên bất thường để kích hoạt parser/logging bug.

Mẫu bảo mật:

- Giữ **root cố định và do ứng dụng kiểm soát**.
- Không mở path từ event mà không kiểm tra loại entry và quyền tại thời điểm I/O.
- Nếu không được theo symlink, dùng `LinkOption.NOFOLLOW_LINKS` ở những thao tác có hỗ trợ và thiết kế chống race.
- Có chính sách giới hạn kích thước, tên, định dạng, charset, depth và tổng thời gian xử lý.
- Xử lý `NoSuchFileException` hợp lệ khi file biến mất.
- Không tự chạy hoặc parse nội dung file chỉ vì event CREATE/ MODIFY.
- Nếu yêu cầu bảo mật cao, xem `SecureDirectoryStream` khi provider hỗ trợ và kiểm soát directory handle/ownership.

**Quan trọng:** `Path.normalize()` hoặc `startsWith(root)` chỉ giải quyết/so sánh đường dẫn dạng lexical, **không** thay thế việc xác minh symlink và race. WatchService không tự sandbox mọi I/O thực hiện từ một event.

## 18. Các loại thao tác có thể cho ra event khác kỳ vọng

### 18.1. Ghi file theo nhiều lần

Producer mở file, ghi header, ghi body, ghi footer. WatchService có thể báo một hoặc nhiều `ENTRY_MODIFY`; consumer không biết ghi xong chỉ từ event.

### 18.2. Trình soạn thảo dùng file tạm và rename

Một lần nhấn Save có thể tạo file tạm, ghi, xóa hoặc đổi tên bản cũ, rồi move tệp mới vào. Watcher có thể thấy chuỗi create/delete/modify chứ không phải một modify duy nhất. Không dùng chuỗi event để suy ra giao dịch của editor.

### 18.3. File được tạo rồi xóa nhanh

Provider polling có thể không quan sát. Nếu ứng dụng cần kiểm toán mọi lần xuất hiện, dùng nguồn sự kiện bền vững khác.

### 18.4. File được sửa qua remote client

API không yêu cầu tất cả thay đổi từ remote được phát hiện. Thêm periodic rescan và kiểm tra tính bền vững/consistency của remote storage nếu nghiệp vụ quan trọng.

### 18.5. Thư mục được di chuyển

WatchKey có thể invalid hoặc chưa invalid theo provider; Path trong `watchable()` có thể stale. Không chỉ xem `key.isValid()`, hãy xác minh directory thực và đăng ký lại khi cần.

### 18.6. Đăng ký nhiều event kinds trên cùng directory

Khi gọi `register` lần nữa trên cùng WatchService đối với cùng watchable, API có thể **trả cùng key** và cập nhật tập kinds/modifiers theo đăng ký mới. Đừng coi mỗi lần register là một key độc lập cho cùng directory. Javadoc nói pending events không bị bỏ chỉ vì thay đổi tập đăng ký; điều đó cũng không làm history trở nên durable.

## 19. Điều gì xảy ra khi không hỗ trợ event kind hoặc modifier?

Lời gọi `Path.register(...)` có thể ném:

- `UnsupportedOperationException` khi kinds hoặc modifiers không được provider hỗ trợ.
- `IllegalArgumentException` khi tổ hợp kinds/modifiers không hợp lệ.
- `ClosedWatchServiceException` nếu service đã đóng.
- `IOException` do lỗi file system hoặc đăng ký.
- `SecurityException` trong môi trường có cơ chế kiểm soát quyền tương ứng.

`FileSystem.newWatchService()` có thể không được provider hỗ trợ. Trên FileSystem có hỗ trợ, vẫn phải kiểm tra **kinds được phép đăng ký**, tình trạng path là directory, quyền và loại provider.

**Tránh workaround rủi ro:** không tự động thay `ENTRY_MODIFY` bằng polling dày 1 ms ở mọi nơi khi unsupported, vì có thể tạo I/O khổng lồ. Nếu cần fallback, đặt cadence quét có thể cấu hình, giới hạn tải, metrics và yêu cầu bảo đảm được công bố rõ.

### 19.1. WatchEvent.Modifier chỉ là chỗ mở rộng của provider

API cho phép truyền `WatchEvent.Modifier` khi register, nhưng Java SE không cung cấp một bộ sensitivity modifiers chung đảm bảo latency cụ thể. **Không phụ thuộc các class thuộc namespace nội bộ** như một phần giao diện portable của ứng dụng, nhất là khi module JDK và provider có thể thay đổi.

## 20. Kiến trúc tham khảo: hệ thống ingest file không mất job còn tồn tại

Giả sử producer đưa file CSV vào `incoming/`. Mục tiêu **không bỏ sót các file cuối cùng vẫn nằm trong thư mục**, đồng thời chấp nhận rằng WatchService chỉ tăng tốc phát hiện.

Một chính sách hợp lý:

1. **Producer có hợp đồng publish:** ghi `*.partial`, hoàn tất và đóng file; chỉ sau đó đổi sang `*.csv` hoặc tạo marker `*.ready`. Nếu yêu cầu crash durability, kiểm soát sync/atomic move trên file store thực tế.
2. **Consumer đăng ký watcher trước lượt quét đầu**, nhưng vẫn quét mọi `*.csv` hiện hữu để khôi phục file đã có.
3. Khi có `ENTRY_CREATE/MODIFY/DELETE`, đánh dấu directory cần đối soát; không parse file ngay trong listener.
4. Với `OVERFLOW` hoặc khi key invalid, kích hoạt **full rescan** và cập nhật đăng ký phù hợp.
5. **Periodic scan** theo thời gian độc lập với event: để bù thay đổi do remote/polling không thông báo và những đợt downtime.
6. Chọn file ứng viên theo trạng thái hiện tại; kiểm tra file type, root, permission, schema và size.
7. **Claim/ack idempotent** bằng ID bền vững, tránh xử lý lại khi scan và event cùng thấy một file.
8. Sau xử lý, ghi checkpoint/commit vào storage bền vững; không dựa vào việc đã gọi `pollEvents`.
9. Giám sát độ trễ từ lúc publish tới lúc xử lý, tỉ lệ overflow, số lần recovery và số file pending.
10. Nếu cần audit đúng từng lần tạo/xóa file, dùng durable event source: WatchService một mình không đủ.

### 20.1. Những gì hợp đồng này vẫn chưa bảo đảm

Ngay cả kiến trúc hybrid WatchService + periodic scan vẫn không ghi lại **mọi biến động đã biến mất giữa hai lần quét**. Nó phù hợp với bài toán reconcile **trạng thái tồn tại**. Để bảo đảm “mọi job đều được giao đúng một lần”, producer và consumer phải chia sẻ một protocol idempotent/durable queue hay transactional store.

### 20.2. Cập nhật từng file sau khi được thông báo

Nếu file vừa có event modify, có thể có một worker queue với retry có giới hạn. Worker phải **mở file thật** và handle `NoSuchFileException`, quyền, file đang ghi dở, charset và schema. Không cần giữ event object qua nhiều giờ như một “file handle”; context chỉ là tên tương đối, có thể stale.

## 21. Testing: kiểm thử đúng cái gì, không hard-code gì?

Unit/integration test cho WatchService cần tách:

**A. Hợp đồng ổn định của API Java:**

- Tạo service bằng `fileSystem.newWatchService()` khi supported.
- Đăng ký Path hợp lệ và lấy WatchKey.
- Xử lý event kind bằng cách so với `StandardWatchEventKinds`.
- Với event ENTRY, context là Path tương đối; với OVERFLOW, context không được giả định là Path.
- Gọi `pollEvents()` và `reset()` đúng vòng đời.
- Key bị cancel/đóng trở nên invalid.
- `close()` làm listener đang block nhận `ClosedWatchServiceException`.

**B. Hành vi phụ thuộc provider cần integration test tại môi trường đích:**

- Event có xuất hiện khi file được tạo qua API và khi công cụ khác ghi hay không.
- Độ trễ thực tế theo percentile, không dựa vào một lần chạy.
- Một lần ghi tạo bao nhiêu modify events.
- Rename directory khiến key invalid/còn valid thế nào.
- Thay đổi trên network share từ **máy khác** có được nhận không.
- Hành vi khi queue tràn/consumer bận.
- File được tạo/xóa nhanh có bị bỏ sót không.
- Tác động của mount/permission/provider restart.

**C. Các lỗi cần mô phỏng:**

- Invalid key, watcher đã đóng, thread bị interrupt.
- `poll(timeout)` trả null.
- `OVERFLOW` có context null hoặc dữ liệu không phải Path.
- Event đến khi file đã bị xóa.
- Producer thay file bằng symlink.
- Nội dung chưa ghi xong.
- Mất kết nối remote và khởi tạo lại.
- Scanner thất bại giữa chừng.
- Queue của ứng dụng quá tải.
- Duplicate event khiến worker bị kích hoạt lặp.

### 21.1. Không khẳng định expected number cố định trong test portable

Một test như “tạo file và assert **chính xác 1 ENTRY_CREATE + 1 ENTRY_MODIFY** trong 100 ms trên mọi OS” là test không portable, bởi đặc tả không đưa ra bảo đảm đó. Hãy assert **logic xử lý kết quả phù hợp với những event đã nhận** và **kết quả reconcile của filesystem**, kết hợp integration tests có timeout rộng hơn ở môi trường kiểm soát.

### 21.2. Không xây test phải gây OVERFLOW thật

Giới hạn hàng đợi là implementation-specific. Cố tạo hàng triệu file chỉ để tràn queue là tốn tài nguyên và không bảo đảm tái hiện. Tốt hơn: tách logic xử lý `OVERFLOW` vào một hàm testable, tạo `WatchEvent` giả định hoặc gọi trực tiếp logic “mark dirty + rescan” trong unit test; integration test stress chạy riêng có giới hạn.

## 22. Lỗi phổ biến và cách sửa

**1. “WatchService là event log đầy đủ.”** Sai; nó chỉ báo các biến đổi mà provider quan sát, có thể gộp/mất.

**2. “Mỗi lần Save sinh đúng một MODIFY.”** Sai; một lần Save có thể tạo nhiều hoặc không tạo event đúng như mong đợi.

**3. “Nhận MODIFY nghĩa là writer đã xong.”** Sai; producer có thể đang ghi.

**4. “Không có OVERFLOW thì chắc chắn không bỏ sót.”** Sai; remote changes/short-lived files có thể không được phát hiện mà không có OVERFLOW.

**5. “OVERFLOW có context là Path.”** Sai; context có thể null/provider-specific.

**6. “event.context() là absolute path.”** Sai; ENTRY context là Path tương đối với registered directory.

**7. “poll(timeout) trả null nghĩa là không ai đã sửa thư mục.”** Sai; chỉ là chưa lấy được key trong thời gian đợi.

**8. “WatchKey tự reset sau khi pollEvents.”** Sai; caller phải gọi `reset()`.

**9. “Một key đang signalled sẽ được queue lại cho mỗi event.”** Sai; event mới có thể tích lũy trên cùng key cho tới khi reset.

**10. “WatchKey valid chứng minh directory vẫn ở path cũ.”** Sai khi directory bị move/rename, provider có thể giữ key valid.

**11. “Đăng ký root sẽ theo dõi mọi subdirectory.”** Sai; cần đăng ký riêng từng directory khi cần.

**12. “Đăng ký subdir khi thấy CREATE sẽ thấy mọi file đã tạo trong nó.”** Sai; có race trước khi đăng ký, phải scan sau đăng ký.

**13. “Một đường dẫn Java cho WatchService nào cũng được.”** Không; phải phù hợp FileSystem/provider.

**14. “Remote share sẽ luôn phát hiện thay đổi từ máy khác.”** Không có bảo đảm đó trong Java SE.

**15. “Thay đổi không báo event ⇒ ứng dụng có thể kết luận file không tồn tại.”** Sai; phải quét trạng thái thật.

**16. “Đọc event nghĩa là đã acknowledge job.”** Sai; pollEvents chỉ lấy thông báo khỏi key, không đánh dấu business job đã commit.

**17. “System.currentTimeMillis() lúc nhận event là thời điểm chính xác file bị sửa.”** Sai; đó là lúc consumer quan sát. WatchEvent không chuẩn hóa timestamp thay đổi.

**18. “Gộp create/delete liền nhau thành rename là đúng.”** Không chắc; không có rename pairing portable.

**19. “Không cần close watcher vì program chạy lâu.”** Sai; cần lifecycle/shutdown, release resource và xử lý key invalid.

**20. “Catch RuntimeException rồi retry vô hạn bảo đảm watcher sống.”** Sai; ClosedWatchServiceException/unsupported/programming errors cần xử lý rõ.

**21. “Cứ scan toàn bộ file trong listener ở mọi event là an toàn hơn.”** Không nhất thiết; listener chậm làm queue tích lũy/overflow.

**22. “normalize() là đủ bảo vệ root khi có symlink.”** Sai; cần chính sách filesystem security/TOCTOU.

**23. “Nên bắt đầu scanner rồi register sau để khỏi event trùng.”** Có blind window; watch trước rồi scan kèm idempotency phù hợp hơn.

**24. “Có thể khôi phục sự kiện cũ sau restart bằng WatchService.”** Không có replay chuẩn; cần checkpoint/durable source.

**25. “Có thể so sánh event.count để xác định đúng số job.”** Sai; count là số lần kind/context được quan sát/gộp, không phải nghiệp vụ.

**26. “Modifier sensitivity nội bộ là chuẩn Java.”** Không; provider-specific, không được dựa làm cam kết portable.

## 23. Checklist khi review code WatchService

- [ ] Đã xác định rõ mục tiêu là **UI notification**, **trigger reconcile**, hay **durable audit** chưa?
- [ ] Nếu cần lưu lịch sử chính xác, có durable queue/producer protocol thay vì chỉ WatchService?
- [ ] `WatchService` được tạo từ **đúng FileSystem** của directory?
- [ ] Có xử lý provider không hỗ trợ watch, kinds hoặc modifiers?
- [ ] Có dùng `try-with-resources` hoặc shutdown đóng watcher?
- [ ] Có xử lý `ClosedWatchServiceException` và `InterruptedException` đúng lifecycle?
- [ ] Có gọi `pollEvents()` và **reset() sau xử lý**?
- [ ] Có kiểm tra kết quả `reset()` để nhận ra key invalid?
- [ ] Có lưu map WatchKey → directory khi theo dõi nhiều thư mục?
- [ ] Có kiểm tra `OVERFLOW` **trước khi cast context sang Path**?
- [ ] Có kế hoạch **full rescan** khi OVERFLOW/invalid key?
- [ ] Có **periodic rescan độc lập** với event để bù polling/remote gaps?
- [ ] Có tránh khẳng định một event = một file save?
- [ ] Có hiểu `count()` không phải job count?
- [ ] Có chấp nhận event ordering/timeliness phụ thuộc provider?
- [ ] Có xử lý thay đổi file **trước khi writer hoàn tất**?
- [ ] Có dùng publish protocol như temp+rename/ready marker và validate nội dung?
- [ ] Có biết WatchService **không recursive**?
- [ ] Có đăng ký/scan subdirs mới một cách có kiểm soát?
- [ ] Có tính race giữa register, scan, events và xử lý file?
- [ ] Có xử lý file biến mất sau event và symlink trỏ ra ngoài root?
- [ ] Có bounded queue/worker để listener không bị chậm và overflow?
- [ ] Có metrics: overflow, invalid keys, latency, rescan age, scanner error, pending jobs?
- [ ] Có test trên **filesystem/provider thực tế** gồm network mount nếu dùng?
- [ ] Có test stop/restart/cancel/move directory và fallback khi provider không nhận event?
- [ ] Có giải thích rõ những guarantees **không** được API cung cấp cho khách hàng và vận hành?

## 24. Câu hỏi tự kiểm tra

**1.** WatchService dùng để làm gì? — Theo dõi **những thay đổi được provider quan sát** đối với các đối tượng đã đăng ký, thường là directory entries.

**2.** Java SE bảo đảm event đến trong 100 ms không? — **Không**; timeliness phụ thuộc provider.

**3.** Provider được phép dùng polling thay native notification không? — **Có**.

**4.** File tạo rồi xóa rất nhanh có thể bị bỏ sót không? — **Có**, nhất là khi provider polling.

**5.** Remote change từ máy khác có bắt buộc phát hiện không? — **Không**.

**6.** `ENTRY_MODIFY` có chứng minh file đã ghi xong không? — **Không**.

**7.** `ENTRY_CREATE` có luôn xảy ra đúng một lần cho thao tác Save logic không? — **Không**; Save có thể gồm nhiều thao tác.

**8.** Có kind `ENTRY_RENAME` portable không? — **Không**; create/delete có thể phản ánh rename nhưng không bảo đảm pairing.

**9.** `OVERFLOW` báo gì? — Implementation biết có nguy cơ sự kiện bị mất/loại bỏ; cần rescan.

**10.** Không thấy OVERFLOW có nghĩa chắc chắn đủ event không? — **Không**.

**11.** Context của ENTRY events là gì? — Một `Path` **tương đối** với directory được đăng ký.

**12.** Context của OVERFLOW có luôn là Path không? — **Không**, có thể null.

**13.** `WatchEvent.count()` có phải số lần ghi bytes/file records? — **Không**.

**14.** `poll(timeout) == null` nghĩa là không có thay đổi thật? — **Không**, chỉ là không lấy được key khi đợi.

**15.** Vì sao phải gọi `key.reset()`? — Đưa key về trạng thái sẵn sàng để được báo hiệu/queue tiếp.

**16.** `reset() == false` nghĩa là gì? — Key không còn valid/được đăng ký.

**17.** Đổi tên directory có luôn làm key invalid ngay? — **Không**, phụ thuộc implementation.

**18.** Đăng ký root có tự theo dõi file ở mọi subdir không? — **Không**.

**19.** Khi một subdir mới xuất hiện, cần làm gì? — Đăng ký subdir nếu cần và **scan bên trong** để giảm khoảng mù.

**20.** Vì sao periodic scan vẫn cần khi đã có WatchService? — Để bù event bỏ sót/remote/polling và khôi phục trạng thái.

**21.** WatchService có replay sự kiện trong lúc ứng dụng tắt không? — **Không**.

**22.** Làm sao xử lý duplicate events? — Idempotency, persistent job ID/claim/ack, không dựa vào event count.

**23.** Khi listener quá chậm phải làm gì? — Đưa I/O nặng ra worker queue bounded, mark dirty và rescan nếu cần.

**24.** Một file không còn khi nhận CREATE có phải bug WatchService? — Không; filesystem có thể thay đổi giữa detection và consumption.

**25.** Nếu cần bảo đảm đã nhận mọi file được tạo rồi xóa, WatchService + periodic scan đủ không? — **Không**; cần lịch sử từ producer/durable source.

**26.** Dùng `key.watchable()` làm Path sau khi directory move có chắc đúng không? — **Không**, key/path semantics có thể stale tùy provider.

## Tài liệu chính thức vẫn áp dụng

- [Java SE 17 — WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): contract về queue, close, overflow, việc MODIFY không đồng nghĩa writer xong và toàn bộ **platform dependencies** (native/polling/timeliness/order/short-lived/remote).
- [Java SE 17 — WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html): signalled/ready state, `pollEvents`, `reset`, `cancel`, invalid key và caveat directory move/rename.
- [Java SE 17 — WatchEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html): `kind`, `count` và `context`.
- [Java SE 17 — StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY`, `OVERFLOW`.
- [Java SE 17 — Watchable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Watchable.html): `register`, event kinds và modifiers.
- [Java SE 17 — FileSystem](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileSystem.html): `newWatchService()`, quan hệ provider/Path.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `newDirectoryStream`, `walkFileTree`, `isRegularFile`, `readAttributes`, `move` và các thao tác đối soát.

**Ghi nhớ:** `WatchService` **không** bảo đảm độ trễ, thứ tự, số lượng hoặc tính đầy đủ của mọi thay đổi filesystem trên mọi provider. Nó có thể dùng native notification hoặc polling; file sống rất ngắn và thay đổi từ remote system có thể không được phát hiện; `ENTRY_MODIFY` không chứng minh writer đã hoàn tất; và `OVERFLOW` đòi quét lại. Hãy dùng WatchService để **kích hoạt xử lý nhanh**, kết hợp **periodic reconciliation**, kiểm tra file thật, idempotent processing, key lifecycle và nguồn sự kiện bền vững khi yêu cầu độ tin cậy cao.