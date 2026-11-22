# WatchKey, reset và khóa mất hiệu lực trong WatchService (Java NIO.2)

## 1. Mục tiêu bài học và tình huống thực tế

Giả sử ứng dụng Java cần biết khi có tệp mới trong thư mục `incoming`: dịch vụ theo dõi thư mục, nhận thông báo, đưa tên tệp vào hàng đợi xử lý, rồi tiếp tục chờ tệp tiếp theo. Mã sẽ không hoạt động ổn định nếu chỉ biết cách gọi `WatchService.take()` mà quên **đặt lại (reset) `WatchKey` sau khi xử lý sự kiện**.

Những câu hỏi quan trọng:

- **`WatchService`** và **`WatchKey`** là gì? Chúng khác gì `WatchEvent`?
- Vì sao gọi `take()` nhận được khóa nhưng không đồng nghĩa đã xử lý mọi event?
- `WatchKey.pollEvents()` lấy sự kiện như thế nào và khác `WatchKey.reset()` ra sao?
- Sau khi xử lý event, tại sao phải gọi `reset()` và xem kết quả `true`/`false`?
- Khi nào khóa **mất hiệu lực**: bị `cancel()`, thư mục bị xóa, filesystem không còn truy cập được, hay watcher bị đóng?
- Nếu nhận `OVERFLOW`, khóa vẫn hợp lệ nhưng dữ liệu sự kiện không còn đầy đủ thì cần làm gì?
- Làm sao thiết kế event loop, tái đăng ký, hủy tác vụ, thử nghiệm và cleanup an toàn?

Các API **`WatchService`, `WatchKey`, `WatchEvent` và `StandardWatchEventKinds`** thuộc Java NIO.2, xuất hiện từ **Java 7** và vẫn được sử dụng trong Java hiện đại. Ví dụ độc lập của bài được biên dịch ở mức **Java 17** và chạy trên file system mặc định hỗ trợ `WatchService`.

**Điểm phải nhớ:** `WatchKey` đại diện cho **một đăng ký theo dõi** có vòng đời riêng. Một lần nhận key không tự làm cho nó sẵn sàng phát thông báo tiếp theo. Sau khi lấy và xử lý event, mã thường cần **`key.reset()`** để tiếp tục nhận notification. Nếu `reset()` trả `false`, key đã không còn hợp lệ: không sử dụng lại key đó như một đăng ký đang hoạt động.

## 2. Ba đối tượng cốt lõi: service, key và event

| Đối tượng | Vai trò | Phương thức thường gặp |
| --- | --- | --- |
| `WatchService` | Hàng đợi thông báo của những đối tượng đã đăng ký, cung cấp key đang được signal | `take()`, `poll()`, `poll(timeout, unit)`, `close()` |
| `WatchKey` | Đại diện một đăng ký theo dõi; có trạng thái và danh sách event chờ | `pollEvents()`, `reset()`, `isValid()`, `cancel()`, `watchable()` |
| `WatchEvent<?>` | Thông tin về một sự kiện đã được quan sát | `kind()`, `context()`, `count()` |
| `Path` / `Watchable` | Đối tượng đăng ký, thông thường là thư mục cần theo dõi | `directory.register(watcher, kinds...)` |

`WatchService` không trả trực tiếp một đường dẫn tệp vừa tạo. `take()` trả về **`WatchKey`** đang có thông báo. Sau đó gọi `key.pollEvents()` mới lấy được danh sách những `WatchEvent` liên quan key.

### 2.1. Ví dụ tạo đăng ký

```java
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;

Path directory = Path.of("incoming");

// Đoạn minh họa nằm trong phương thức có xử lý IOException.
try (WatchService watcher = FileSystems.getDefault().newWatchService()) {
    WatchKey key = directory.register(
            watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_MODIFY,
            StandardWatchEventKinds.ENTRY_DELETE);

    System.out.println(key.isValid());
}
```

Đây là **đoạn minh họa**, giả sử thư mục `incoming` tồn tại, có thể đăng ký và provider hỗ trợ các kind đã chọn. `Path.of` có từ **Java 11**; với Java 7/8 có thể dùng `Paths.get("incoming")`. Tạo `WatchService` và đăng ký `Path` có thể phát sinh `IOException` hoặc lỗi đăng ký tùy provider. Trong ứng dụng thật, `try-with-resources` phải bao trùm toàn bộ thời gian cần theo dõi, **không đóng watcher ngay sau khi đăng ký** như đoạn demo phạm vi tài nguyên ngắn này.

### 2.2. `watchable()` và đối tượng đang theo dõi

`key.watchable()` trả đối tượng `Watchable` đã được đăng ký. Với đăng ký từ `Path` của directory thông thường, có thể lấy về `Path` tương ứng:

```java
Path watchedDirectory = (Path) key.watchable();
```

Đây là đoạn minh họa với `key` lấy từ một đăng ký `Path`. Không mặc định `watchable()` là tên tệp phát sinh sự kiện: **nó là đối tượng được đăng ký**, thường là thư mục cha.

Có thể đăng ký nhiều thư mục trên **một WatchService**, mỗi đăng ký thường được đại diện bởi key riêng. Khi nhận một key từ service, dùng `key.watchable()` hoặc bảng quản lý registration để biết sự kiện thuộc thư mục nào.

## 3. Vòng đời của `WatchKey`: READY và SIGNALLED

Hãy hình dung một WatchKey có hai trạng thái điều phối chính khi còn hợp lệ:

1. **READY:** đăng ký đang sẵn sàng được đưa vào hàng đợi khi có event.
2. **SIGNALLED:** key đã được báo hiệu và được đưa vào hoặc đang được người tiêu thụ lấy khỏi hàng đợi `WatchService`. Trong trạng thái này, những sự kiện mới có thể tích lũy nhưng key không đơn giản được đưa vào hàng đợi như một registration mới độc lập mỗi lần.

Sơ đồ khái niệm:

```text
directory.register(...)
        |
        v
   READY (valid)
        |
        | Có sự kiện phù hợp
        v
SIGNALLED -> key được xếp vào WatchService
        |
        | watcher.take() hoặc watcher.poll(...)
        v
SIGNALLED -> consumer nhận WatchKey
        |
        | key.pollEvents() lấy và xóa danh sách event đang chờ
        | xử lý event / ghi nhận trạng thái
        v
key.reset()
        |
        +-- true  -> key vẫn valid; có thể quay về READY,
        |            hoặc được queue lại nếu có event chưa xử lý
        |
        +-- false -> key invalid; không thể dùng tiếp registration cũ
```

**Lưu ý quan trọng:** Hình vẽ chỉ mô tả vòng đời thường gặp. `reset() == true` không bảo đảm rằng key luôn dừng ở READY ngay tại thời điểm bạn quan sát. Nếu trong khi key đang SIGNALLED đã xuất hiện **những event đang chờ**, việc reset có thể làm key **được xếp hàng lại ngay** để consumer xử lý tiếp.

### 3.1. Lúc mới đăng ký

Một `WatchKey` mới hợp lệ ban đầu ở trạng thái READY. `key.isValid()` cho biết đăng ký hiện có hợp lệ không; nó **không** cho biết key đang READY hay SIGNALLED. Java không cung cấp một getter enum công khai `getState()` cho vòng đời hai trạng thái này.

### 3.2. Khi có sự kiện được phát hiện

Provider đưa event vào danh sách gắn với key, signal key và đưa key vào queue của `WatchService`. Nếu có nhiều event trước khi consumer xử lý, chúng có thể được gộp hoặc cùng nằm trong một lần `pollEvents()`. **Một lần `take()` không tương đương đúng một sự kiện filesystem**.

### 3.3. Khi consumer lấy key

`watcher.take()` chờ đến khi có key được signal rồi **trả một `WatchKey`**. Nó không tự gọi `pollEvents()` và cũng không tự gọi `reset()`.

```java
WatchKey key = watcher.take();
```

Đây là đoạn minh họa trong phương thức xử lý `InterruptedException`. Nếu không có thông báo, `take()` có thể **chờ vô thời hạn** cho đến khi có key, thread bị interrupt hoặc service đóng. Khi service bị đóng, thao tác chờ hoặc gọi API tương ứng có thể ném `ClosedWatchServiceException`.

### 3.4. Khi đã đọc event

`key.pollEvents()` lấy và **loại các event hiện có khỏi danh sách pending** của key. Nó **không** tự rearm key bằng cách chuyển từ SIGNALLED sang READY.

### 3.5. Khi reset

`key.reset()` là bước **đặt lại trạng thái thông báo** để key hợp lệ tiếp tục nhận xử lý những đợt event sau. Nếu key không còn hợp lệ, kết quả là `false`. Nếu hợp lệ, kết quả là `true`, kể cả khi key có thể được queue lại ngay vì có event mới trong lúc xử lý.

## 4. Quy trình chuẩn: take → pollEvents → xử lý → reset

Một chu trình cơ bản:

```java
WatchKey key = watcher.take();

for (WatchEvent<?> event : key.pollEvents()) {
    // Kiểm tra kind, context, count; xử lý hoặc lên lịch xử lý.
}

boolean stillValid = key.reset();
if (!stillValid) {
    // Đăng ký này không còn hoạt động.
}
```

Đây là **đoạn minh họa trong phương thức có watcher hợp lệ và xử lý `InterruptedException`**, không phải chương trình chạy độc lập. Trong mã production, vòng lặp sẽ lặp lại bước `take` để theo dõi liên tục, đồng thời có cơ chế dừng, xử lý `OVERFLOW`, exception, cancellation và cleanup.

**Thứ tự nên dùng:** nhận key → lấy các event pending → xử lý nhanh hoặc đưa vào queue nội bộ → gọi `reset` → chờ key tiếp theo.

### 4.1. Vì sao thiếu `reset` khiến watcher có vẻ “đứng yên”?

Giả sử:

```java
while (true) {
    WatchKey key = watcher.take();
    for (WatchEvent<?> event : key.pollEvents()) {
        System.out.println(event.kind());
    }
    // Sai: không reset key.
}
```

Đoạn trên là **ví dụ cố ý sai**. Sau lần đầu, key có thể vẫn SIGNALLED nhưng **không được đưa lại vào hàng đợi** cho các lần thông báo tiếp theo. Consumer tiếp tục chờ `take()`, khiến người vận hành tưởng rằng WatchService không hoạt động dù thư mục vẫn thay đổi.

Sửa bằng:

```java
if (!key.reset()) {
    // Key không còn valid: loại khỏi danh sách đăng ký, phục hồi khi cần.
}
```

Điểm cần nhớ không phải cứ viết `reset` là đảm bảo không bỏ event: WatchService vẫn có cơ chế coalescing, `OVERFLOW`, thay đổi đồng thời và giới hạn provider. `reset` xử lý **vòng đời signal/queue của key**, không phải chức năng ghi log mọi sự kiện chính xác một-một.

### 4.2. Vì sao `pollEvents` không thay `reset`?

`pollEvents` nói “cho tôi danh sách event đang chờ và xóa chúng khỏi danh sách này”. `reset` nói “đã xử lý key đang SIGNALLED; cho phép key sẵn sàng/được queue lại theo trạng thái hiện tại”.

Hai thao tác khác nhau:

| Lời gọi | Kết quả | Không tự làm |
| --- | --- | --- |
| `watcher.take()` | Chờ và lấy một key được signal | Không đọc danh sách event, không reset |
| `watcher.poll()` | Lấy key ngay nếu đã có, có thể trả `null` | Không lấy event của key |
| `watcher.poll(timeout, unit)` | Chờ tối đa một khoảng thời gian để nhận key | Không đảm bảo sắp có event |
| `key.pollEvents()` | Trả và xóa pending events của key | Không rearm key |
| `key.reset()` | Đặt lại cơ chế signal nếu valid; báo `true`/`false` | Không trả danh sách event, không phục hồi key invalid |
| `key.cancel()` | Hủy đăng ký và làm key invalid | Không đóng toàn bộ `WatchService` |
| `watcher.close()` | Đóng service và vô hiệu hóa các key gắn với nó | Không tự xây dựng lại đăng ký |

### 4.3. Vì sao reset sau khi lấy event nhưng trước khi chờ tiếp?

Nếu gọi `reset` mà không drain event, các event còn pending có thể khiến key được queue lại ngay. Kết quả có thể là vòng lặp lấy lại những event cũ mà ứng dụng chưa thực sự tiêu thụ. Hãy quản lý vòng đời cẩn thận: đọc danh sách pending bằng `pollEvents`, xử lý các mục hoặc ghi vào queue xử lý riêng, rồi reset.

Không cần xóa thủ công danh sách event sau `pollEvents`; việc lấy pending events đã làm công việc đó. Và không gọi `cancel()` thay `reset()` nếu mục tiêu là tiếp tục theo dõi.

## 5. `reset()` trả `true` và `false` chính xác nghĩa là gì?

### 5.1. `reset() == true`

Nghĩa là tại lúc reset, **key vẫn là đăng ký hợp lệ** theo WatchService. Đây không phải lời đảm bảo:

- Tệp đã được xử lý thành công.
- Mọi thay đổi của thư mục đều đã được ghi nhận.
- Key có đúng một event.
- Event cuối cùng là event tạo tệp.
- Thư mục không thể bị xóa hoặc đổi quyền trong giây tiếp theo.

Nếu sự kiện mới đã tích lũy trong trạng thái SIGNALLED, key có thể nhanh chóng lại xuất hiện trong queue ngay sau `reset`. Đây là hành vi mong đợi, không phải lỗi “trả key trùng”.

### 5.2. `reset() == false`

Nghĩa là **key không còn hợp lệ**. Việc reset không thể biến một registration đã mất hiệu lực thành registration hợp lệ. Caller phải ngừng coi key đó là nguồn event mới đáng tin.

Các hướng xử lý tùy mục tiêu:

- Nếu ứng dụng chỉ theo dõi **một thư mục**, thoát event loop hoặc chuyển sang trạng thái chờ phục hồi.
- Nếu theo dõi **nhiều thư mục**, loại riêng key invalid ra khỏi danh sách registration; những key khác có thể vẫn hoạt động.
- Nếu đường dẫn vẫn cần theo dõi, thử **đăng ký mới** khi mục tiêu hiện tồn tại và phù hợp, có backoff và xử lý lỗi.
- Nếu thư mục đã bị xóa và cần phát hiện khi nó được tạo lại, có thể theo dõi **thư mục cha** với chính sách riêng hoặc thực hiện kiểm tra/phục hồi định kỳ; key đã invalid không tự “sống lại”.

### 5.3. `isValid()` không tương đương `reset()`

`key.isValid()` là kiểm tra trạng thái hợp lệ tại thời điểm gọi. Nó không thực hiện thao tác rearm key. Nếu mã làm:

```java
if (key.isValid()) {
    // Nhưng quên key.reset()...
}
```

thì vẫn có thể bị kẹt vòng đời SIGNALLED. Ngược lại, dù `isValid()` vừa trả `true`, key cũng có thể invalid trước khi reset vì filesystem thay đổi. **Luôn xử lý giá trị boolean trả về từ chính `reset`**.

### 5.4. Gọi `reset` trên key invalid

```java
key.cancel();
boolean valid = key.reset(); // false
```

Đây là đoạn minh họa khi `key` đang hợp lệ trước `cancel`. Sau `cancel`, `key.isValid()` là `false` và `reset()` trả `false`. Không có cách biến key cũ thành hợp lệ bằng cách gọi `reset` nhiều lần.

## 6. Khi nào `WatchKey` mất hiệu lực?

Theo vòng đời `WatchKey`, các tình huống phổ biến:

| Nguyên nhân | Điều gì xảy ra? | Hành động cần cân nhắc |
| --- | --- | --- |
| Ứng dụng gọi `key.cancel()` | Registration tương ứng bị hủy, key invalid | Ngừng dùng key đó; đăng ký lại nếu cần |
| `WatchService.close()` | Các key đăng ký với service bị vô hiệu hóa | Tạo WatchService/registration mới nếu muốn tiếp tục theo dõi |
| Directory được theo dõi bị xóa | Provider có thể đánh dấu key invalid | Ngừng tin key; đăng ký lại khi directory mới hợp lệ |
| Directory không còn truy cập được do thay đổi file system hoặc mount | Key có thể invalid theo provider | Báo lỗi/trạng thái và có cơ chế phục hồi |
| Ứng dụng đổi cấu hình và loại một directory khỏi tập theo dõi | Thường chủ động `cancel` key tương ứng | Xóa mapping key→directory và cleanup |

**Không suy ra ngược một-một:** `reset() == false` không chứng minh chắc chắn “thư mục đã bị xóa”, vì có nhiều lý do invalid. Muốn phục hồi cần xem ngữ cảnh, tình trạng WatchService, quyền và đường dẫn.

### 6.1. `cancel()` chỉ hủy một đăng ký

```java
WatchKey key = directory.register(
        watcher, StandardWatchEventKinds.ENTRY_CREATE);

// Sau khi không cần theo dõi directory này nữa:
key.cancel();
```

Đây là đoạn minh họa có `directory` là `Path` và `watcher` là `WatchService`. `cancel` **không phải** `watcher.close()`: service có thể vẫn dùng để theo dõi các directory khác.

Lưu ý: một key đã bị cancel nhưng đang **nằm trong queue** vẫn có thể được lấy ra bởi consumer tùy thời điểm. Vì vậy khi nhận một key, mã không nên giả định mọi key lấy từ queue đều còn valid. Hãy xử lý event theo chính sách và luôn kiểm tra kết quả reset hoặc trạng thái invalid.

### 6.2. `WatchService.close()` invalid các key của service

`WatchService` thực thi `Closeable`; dùng `try-with-resources` là cách hiện đại để đóng watcher khi ứng dụng kết thúc.

```java
WatchKey registered;

try (WatchService watcher =
             java.nio.file.FileSystems.getDefault().newWatchService()) {
    registered = directory.register(
            watcher, StandardWatchEventKinds.ENTRY_CREATE);
    System.out.println(registered.isValid()); // true khi đăng ký thành công
}

System.out.println(registered.isValid()); // false sau khi watcher đóng
```

Đây là mã minh họa trong phương thức có `directory` kiểu `Path` và xử lý `IOException`. Sau khi service đóng, các thao tác chờ notification bằng service không tiếp tục hoạt động như một watcher mở; ứng dụng có thể nhận `ClosedWatchServiceException`. Đừng nuốt exception rồi chạy một vòng lặp retry vô hạn trên **service đã đóng**.

### 6.3. Directory bị xóa hoặc không còn truy cập được

Khi đối tượng được đăng ký không còn hợp lệ, WatchService có thể làm key invalid. Provider có thể cần thời gian để quan sát thay đổi; không nên hardcode thời điểm chính xác mà một key chuyển thành invalid sau lệnh xóa directory.

Nếu tính đúng đắn phụ thuộc vào việc thư mục biến mất:

- Lưu trạng thái registration trong ứng dụng.
- Kiểm tra `key.reset()` sau khi nhận các notification.
- Có cơ chế đối soát trạng thái bằng filesystem I/O phù hợp.
- Không xem thông báo `ENTRY_DELETE` cho **một file con** là tương đương với việc key của **thư mục cha** đã invalid.

## 7. Đăng ký lại sau khi key không còn valid

Khi ứng dụng vẫn cần theo dõi một directory đã mất registration, có thể thử đăng ký lại:

```java
WatchKey newKey = directory.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_DELETE,
        StandardWatchEventKinds.ENTRY_MODIFY);
```

Đây là đoạn minh họa trong phương thức xử lý `IOException`, với watcher còn mở, thư mục phù hợp và provider hỗ trợ event kinds. Nếu directory đã bị xóa, việc đăng ký lại **có thể thất bại**, thường với một ngoại lệ I/O phù hợp. Phải tránh “thử lại liên tục không nghỉ” vì gây tải CPU và log.

### 7.1. Đăng ký lại khi key cũ vẫn hợp lệ

Nếu cùng một `Watchable` đã được đăng ký vào cùng WatchService và key cũ vẫn valid, lời gọi `register` lại thường **trả chính key hiện có** và cập nhật tập event kinds theo hợp đồng của registration. Nó không có nghĩa lúc nào cũng tạo ra key mới, và **không thay thế** nhiệm vụ reset key đang SIGNALLED.

### 7.2. Đăng ký lại khi key cũ bị hủy

Nếu key đã invalid do `cancel` nhưng thư mục còn tồn tại và watcher đang mở, `register` có thể tạo một key hợp lệ mới. Ví dụ đầy đủ của bài sẽ kiểm chứng điều này trên filesystem mặc định hỗ trợ.

### 7.3. Nếu cần theo dõi lúc thư mục được tạo lại

Một WatchKey đã invalid **không tự theo dõi lại** chỉ vì có một thư mục mới trùng tên xuất hiện. Có thể:

1. Giữ một registration cho **thư mục cha** để nhận biết con mục tiêu được tạo lại khi provider thông báo.
2. Định kỳ thử tìm/đăng ký mục tiêu bằng retry có backoff nếu hợp đồng cho phép.
3. Sau khi đăng ký thành công, **quét đối soát** để không mất thay đổi diễn ra trong khoảng thời gian không có registration.
4. Khi nhiều key/worker cùng hoạt động, cập nhật mapping từ key đến directory trong một chỗ quản lý.

Không chỉ dùng `Files.exists` trước `register` rồi nghĩ sẽ an toàn: directory có thể biến mất giữa bước kiểm tra và bước đăng ký. **Thử đăng ký thực tế và xử lý lỗi tại chỗ**.

## 8. `WatchEvent<?>`, `kind()`, `context()` và `count()`

`WatchKey.pollEvents()` trả danh sách event đã được phát hiện cho registration. Các kind phổ biến:

| Kind | Ý nghĩa thường gặp |
| --- | --- |
| `StandardWatchEventKinds.ENTRY_CREATE` | Một entry xuất hiện trong directory được theo dõi |
| `StandardWatchEventKinds.ENTRY_MODIFY` | Một entry có sự thay đổi thuộc tính/nội dung theo định nghĩa provider |
| `StandardWatchEventKinds.ENTRY_DELETE` | Một entry biến mất khỏi directory được theo dõi |
| `StandardWatchEventKinds.OVERFLOW` | Một phần sự kiện có thể đã bị mất/bỏ do giới hạn hệ thống theo dõi |

**Không coi một sự kiện là giao dịch đã hoàn tất.** Ví dụ `ENTRY_CREATE` có thể xuất hiện khi producer mới tạo file nhưng chưa ghi hết nội dung. Nếu ứng dụng bắt đầu parse file ngay lập tức, việc đọc có thể còn thấy dữ liệu chưa hoàn chỉnh. Hãy dùng quy trình publish file an toàn, như producer ghi file tạm rồi đổi tên theo hợp đồng đã định, hoặc cơ chế xác nhận hoàn tất riêng.

### 8.1. `context()` thường là tên tương đối so với directory đăng ký

Đối với ENTRY_CREATE/ENTRY_MODIFY/ENTRY_DELETE của một `Path` directory, `event.context()` thường là một `Path` **tương đối với directory được đăng ký**, không phải absolute path.

```java
for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        // Cần đối soát trạng thái; không ép kiểu context.
        continue;
    }
    if (event.context() instanceof Path relative) {
        Path directory = (Path) key.watchable();
        Path candidate = directory.resolve(relative);
        System.out.println(event.kind().name() + ": " + candidate);
    }
}
```

Đây là đoạn minh họa trong phương thức có `key` và các import tương ứng, dùng Java 17 pattern matching cho `instanceof`. `candidate` là **giá trị tên đường dẫn**, không tự xác nhận file còn tồn tại hoặc an toàn để mở.

### 8.2. `OVERFLOW` không có context Path bắt buộc

Với `OVERFLOW`, `context()` có thể là `null`; **kiểm tra kind trước khi cast context**. Khi có overflow, chương trình không còn cơ sở nói đã nhìn thấy đủ mọi sự kiện. Một cách phục hồi là:

- Đánh dấu dữ liệu chỉ mục/đếm file trong phạm vi đó **không còn đồng bộ**.
- Dùng `Files.walkFileTree` hoặc cơ chế snapshot/đối soát thích hợp để xây dựng lại trạng thái.
- Tiếp tục theo dõi bằng WatchService sau khi reset key còn valid, nhưng không nhầm việc reset với thao tác tự phục hồi các event đã mất.

**Chú ý:** `OVERFLOW` là vấn đề **độ đầy đủ event**, không nhất thiết là key invalid. Hai trường hợp cần xử lý khác nhau: key có thể vẫn valid sau overflow; ngược lại key có thể invalid dù không có overflow.

### 8.3. `count()` và gộp sự kiện

`WatchEvent.count()` có thể phản ánh việc những sự kiện tương ứng đã được **coalesce/gộp**; không nên giả định mỗi notification luôn mang `count == 1` hoặc mỗi thao tác thực tế đều sinh đúng một event.

Ngay cả khi `count()` bằng 1, không nên suy ra rằng toàn bộ lịch sử thao tác tệp trong khoảng thời gian đó đã được ghi lại chính xác. Provider được phép có những khác biệt về cách phát và gộp event, và `OVERFLOW` có thể xuất hiện khi số lượng thay đổi lớn.

### 8.4. Không phải watcher đệ quy mặc định

Đăng ký `root` thường giám sát **những entry trực tiếp trong root**, không tự đăng ký mọi directory con. Nếu muốn theo dõi toàn bộ cây:

1. Quét cây ban đầu bằng `Files.walkFileTree` và đăng ký từng directory thích hợp.
2. Khi thấy `ENTRY_CREATE` của directory mới, kiểm tra loại entry và đăng ký directory đó.
3. Xử lý khoảng thời gian giữa lúc tạo directory con và lúc đăng ký mới bằng đối soát, vì một số thay đổi có thể diễn ra trước khi có watch.
4. Khi xóa directory, hủy registration tương ứng và quản lý key invalid.
5. Đặt quota cho số thư mục/watchers và giới hạn tài nguyên OS.

Chỉ tăng số registration không tự làm cho sự kiện trở thành **nhật ký giao dịch đầy đủ**. Nếu yêu cầu chính xác tuyệt đối, cần thêm một nguồn trạng thái đáng tin hoặc snapshot reconciliation.

## 9. `take`, `poll` và cách thoát vòng lặp có kiểm soát

### 9.1. `take()` chờ đến khi có key

```java
WatchKey key = watcher.take();
```

Nếu chưa có key signal, thread có thể chờ. Phương thức khai báo `InterruptedException`, nên loop production cần chính sách khi thread bị interrupt.

Một chính sách thường dùng là **giữ lại interrupt flag** và rời khỏi vòng lặp:

```java
try {
    WatchKey key = watcher.take();
    // Xử lý key...
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Thoát khỏi worker theo chính sách shutdown.
}
```

Đây là đoạn minh họa trong code của thread worker. Không đơn thuần nuốt interrupt rồi chạy tiếp như chưa có gì nếu hệ thống dùng interrupt để yêu cầu dừng.

### 9.2. `poll(timeout, unit)` giới hạn thời gian chờ

```java
WatchKey key = watcher.poll(2, java.util.concurrent.TimeUnit.SECONDS);
if (key == null) {
    // Không có key được giao trong khoảng thời gian đã chờ.
}
```

Đây là đoạn minh họa có xử lý `InterruptedException`. `null` **không** có nghĩa watcher hỏng hay directory đã bị xóa; nó chỉ nói không nhận được key trong lần chờ đó.

Timed polling hữu ích khi worker cần thỉnh thoảng kiểm tra cờ shutdown, cập nhật health check hoặc thực hiện công việc khác. Không cần đặt timeout vài mili giây kèm busy loop không có lý do; chọn chính sách tương ứng độ trễ và tải CPU.

### 9.3. Watcher bị đóng

Nếu `watcher.close()` được gọi khi một thread khác đang `take()`, thread chờ có thể nhận `ClosedWatchServiceException`; đây là **unchecked exception** biểu thị service không còn hoạt động. Với shutdown có chủ đích, ứng dụng có thể coi đó là dấu hiệu kết thúc sạch; nếu đóng bất ngờ, cần báo lỗi phù hợp.

Không tiếp tục gọi `take()` vô hạn trên service đã đóng. Muốn phục hồi, phải **tạo service mới và đăng ký lại** những directory vẫn hợp lệ.

### 9.4. Một queue, nhiều registration

Một `WatchService` có thể có nhiều WatchKey. Khi nhận một key invalid, đừng lập tức đóng cả watcher nếu các key khác vẫn được dùng. Quản lý tập key:

```java
if (!key.reset()) {
    registrations.remove(key); // Map/Set do ứng dụng định nghĩa.
}
```

Đây là đoạn minh họa, cần khai báo `registrations` trong ứng dụng. Nếu có nhiều watcher hoặc worker thread tiêu thụ cùng queue, phải quản lý đồng bộ đúng để không xử lý event trùng lặp hay quên reset. Một **consumer chuyên trách cho mỗi WatchService** thường đơn giản và dễ hiểu hơn.

## 10. Ví dụ Java 17+ độc lập: hai lần reset, cancel, đăng ký lại và đóng watcher

Ví dụ sau kiểm thử **vòng đời thật của WatchKey**, không dùng WatchKey giả:

1. Tạo thư mục tạm và mở `WatchService`.
2. Đăng ký `ENTRY_CREATE` cho directory.
3. Tạo `first.txt`, chờ notification trong thời hạn tối đa 10 giây, đọc event và reset.
4. Tạo `second.txt`, lặp lại. **Việc nhận lần thứ hai chứng minh luồng rearm hoạt động** trên môi trường thử nghiệm.
5. Gọi `cancel()`, kiểm tra `isValid == false` và `reset == false`.
6. Đăng ký lại directory với cùng WatchService đang mở, nhận key valid.
7. Đóng WatchService, kiểm tra key đăng ký lại đã invalid.
8. Xóa chính các file/thư mục tạm đã tạo.

Chương trình sử dụng `poll(timeout, unit)` thay vì chờ vô hạn để không treo test khi provider không gửi notification như mong đợi. Nó có chính sách fail-fast nếu xuất hiện `OVERFLOW`, key bất ngờ hoặc hết timeout; trong production có thể thay bằng cơ chế rescan/retry.

Tạo file **`WatchKeyLifecycleDemo.java`**:

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

public final class WatchKeyLifecycleDemo {
    private static boolean awaitCreate(
            WatchService service, WatchKey registeredKey, String name)
            throws IOException, InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
        while (true) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) throw new IOException("Timed out waiting for " + name);
            WatchKey key = service.poll(remaining, TimeUnit.NANOSECONDS);
            if (key == null) throw new IOException("Timed out waiting for " + name);
            if (key != registeredKey) throw new IOException("Unexpected WatchKey");
            boolean found = false;
            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                    throw new IOException("Watch overflow: rescan required");
                }
                if (event.kind() == StandardWatchEventKinds.ENTRY_CREATE
                        && event.context() instanceof Path relative
                        && relative.getFileName().toString().equals(name)) {
                    found = true;
                }
            }
            if (!key.reset()) throw new IOException("WatchKey became invalid");
            if (found) return true;
        }
    }

    public static void main(String[] args)
            throws IOException, InterruptedException {
        Path directory = Files.createTempDirectory("watch-key-demo-");
        Path first = directory.resolve("first.txt");
        Path second = directory.resolve("second.txt");
        try {
            WatchKey keyAfterClose;
            try (WatchService service =
                         FileSystems.getDefault().newWatchService()) {
                WatchKey key = directory.register(
                        service, StandardWatchEventKinds.ENTRY_CREATE);
                System.out.println("registered valid = " + key.isValid());
                System.out.println("watchable matches directory = "
                        + directory.equals(key.watchable()));

                Files.createFile(first);
                System.out.println("first create received = "
                        + awaitCreate(service, key, "first.txt"));
                Files.createFile(second);
                System.out.println("second create received = "
                        + awaitCreate(service, key, "second.txt"));

                key.cancel();
                System.out.println("valid after cancel = " + key.isValid());
                System.out.println("reset after cancel = " + key.reset());

                keyAfterClose = directory.register(
                        service, StandardWatchEventKinds.ENTRY_CREATE);
                System.out.println("re-registered valid = "
                        + keyAfterClose.isValid());
            }
            System.out.println("valid after service close = "
                    + keyAfterClose.isValid());
        } finally {
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
            Files.deleteIfExists(directory);
        }
        System.out.println("cleanup = done");
    }
}
```

Biên dịch và chạy trên JDK có hỗ trợ Java 17:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 WatchKeyLifecycleDemo.java
java WatchKeyLifecycleDemo
```

**Stdout chính xác đã được kiểm thử trên Windows với filesystem mặc định hỗ trợ event kinds đã đăng ký:**

```text
registered valid = true
watchable matches directory = true
first create received = true
second create received = true
valid after cancel = false
reset after cancel = false
re-registered valid = true
valid after service close = false
cleanup = done
```

### 10.1. Vì sao `awaitCreate` dùng deadline và timeout?

`WatchService` phụ thuộc file-system provider. Việc tạo file có thể được thông báo sau một khoảng trễ, và có provider không hỗ trợ như mong đợi. `poll` với thời hạn giúp test **thất bại có kiểm soát** thay vì treo vô hạn. Nếu không nhận được key, phương thức ném `IOException` với thông tin timeout.

Hạn 10 giây là lựa chọn của **bài thử nghiệm**, không phải mặc định của Java. Trong hệ thống thật, chọn timeout theo yêu cầu độ trễ, shutdown và đặc tính lưu trữ.

### 10.2. Vì sao `awaitCreate` không giả định mỗi key có một event?

Mỗi lần nhận `key`, mã duyệt **toàn bộ `key.pollEvents()`** và kiểm tra có sự kiện CREATE cho tên mong đợi không. Mã không dùng `get(0)` hoặc giả định event index 0 chắc chắn là tên tệp vừa tạo.

Khi nhận những event không phù hợp trong lần poll, helper vẫn reset và chờ tiếp. Nếu nhận `OVERFLOW`, helper báo lỗi để tránh kết luận sai rằng đã theo dõi đầy đủ.

### 10.3. Vì sao so sánh `key != registeredKey`?

Trong bài thử, chỉ có **một directory được đăng ký tại một thời điểm**, nên key nhận được phải là key đại diện registration đó. Đây là bất biến của **fixture một directory**. Với watcher thực tế đăng ký nhiều directory, không được dùng điều kiện này; thay vào đó dùng bảng mapping và xử lý đúng từng key.

### 10.4. Vì sao sau `reset()` lại nhận được CREATE lần hai?

Sau sự kiện `first.txt`, helper gọi `pollEvents` rồi `reset` khi key còn hợp lệ. Điều này cho phép notification tiếp theo của `second.txt` đi qua cơ chế queue. Nếu quên `reset`, test theo dõi cùng key có thể dừng ở lần thứ hai hoặc nhận event không theo chu trình mong muốn.

### 10.5. Vì sao sau `cancel` không thể tiếp tục?

`cancel` làm key invalid. `isValid` trả `false`; `reset` cũng trả `false`, nên không thể “reset để cứu” đăng ký cũ. Thay vào đó, vì directory vẫn tồn tại và WatchService chưa đóng, mã `register` lại và kiểm tra được một key hợp lệ.

### 10.6. Vì sao sau khi đóng watcher, key mới lại invalid?

Kết thúc `try-with-resources` gọi `WatchService.close()`, làm các đăng ký còn lại invalid. Đây là lý do không được giữ một WatchKey rồi tiếp tục mong nhận event từ **service đã đóng**.

### 10.7. Giới hạn của test và cleanup

Test thực hiện I/O thật trong thư mục tạm. Nó có thể không chạy được trên một provider không hỗ trợ watch event, môi trường thiếu quyền tạo file, hoặc ổ đĩa có lỗi; đó là giới hạn hệ thống, không phải cú pháp của `WatchKey`.

`finally` chỉ xóa các tệp tạm do chính chương trình tạo. Nếu provider từ chối xóa, `IOException` có thể phát sinh; ứng dụng không nên nuốt hết lỗi cleanup và báo rằng test đã thành công.

## 11. Event loop production: xử lý sự kiện không đồng nghĩa xử lý tác vụ nặng ngay trong loop

Một chương trình theo dõi file lâu dài nên giữ phần tiêu thụ event **nhanh**, tránh đọc file nhiều gigabyte ngay khi đang giữ key SIGNALLED. Thay vào đó:

1. Nhận key từ queue.
2. Drain danh sách pending event.
3. Phân loại `kind/context/count`.
4. Đưa việc xử lý nội dung sang worker pool hoặc queue có backpressure, nếu hợp đồng cho phép.
5. Ghi nhận overflow và đánh dấu cần rescan.
6. Gọi reset để watcher tiếp tục được rearm.
7. Nếu reset trả false, cập nhật registration map và phục hồi/đóng theo chính sách.

Một mẫu khung với một registration:

```java
static void loop(WatchService watcher)
        throws InterruptedException {
    while (true) {
        WatchKey key = watcher.take();

        for (WatchEvent<?> event : key.pollEvents()) {
            if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                System.err.println("Rescan required");
                continue;
            }
            if (event.context() instanceof Path relative) {
                Path parent = (Path) key.watchable();
                Path candidate = parent.resolve(relative);
                System.out.println(event.kind().name() + " " + candidate);
            }
        }

        if (!key.reset()) {
            System.out.println("Registration invalid; stop this one-key loop");
            break;
        }
    }
}
```

Đây là **phương thức minh họa để đặt trong một lớp**, cần import `WatchService`, `WatchKey`, `WatchEvent`, `Path` và `StandardWatchEventKinds`. Nó chỉ là khung để dạy vòng đời, không có cơ chế quản lý đa directory hoặc khởi tạo watcher, không phải loop production hoàn chỉnh.

### 11.1. Xử lý event có thể ném exception

Khi worker xử lý event thất bại, cần phân biệt:

- **Lỗi ứng dụng đọc nội dung file:** file có thể đang được ghi dở, đã bị xóa hoặc quyền thay đổi; xử lý riêng theo chính sách.
- **Lỗi bookkeeping của consumer:** có thể làm vòng lặp crash trước khi reset; cần quyết định cho phép dừng watcher và báo lỗi hay tiếp tục.
- **Lỗi làm state index không còn đáng tin:** đánh dấu phải đối soát lại; không tuyên bố đã nhận đủ event.

Không được lạm dụng `finally { key.reset(); }` để che mọi exception: reset có thể được gọi trong `finally` khi cần duy trì watcher, nhưng **vẫn phải bảo toàn lỗi gốc, cập nhật trạng thái nghiệp vụ và quyết định có tiếp tục hay không**. Khi lỗi nghiêm trọng khiến task phải hủy, đóng watcher theo phạm vi tài nguyên có thể thích hợp hơn một vòng lặp retry mù quáng.

### 11.2. Backpressure

Một thư mục nhiều event có thể tạo ra hàng đợi tác vụ quá lớn nếu consumer chỉ đưa mọi notification sang một `ExecutorService` không giới hạn. Việc reset key nhanh không giải quyết được quota CPU/RAM/storage của phần xử lý nội dung.

Hãy chọn bounded queue, hạn mức song song, batch/debounce, worker cancellation và cơ chế rescan phù hợp. Một batch event có thể có nhiều mục trùng đường dẫn; không nhất thiết cần làm lại công việc nặng cho từng notification.

### 11.3. Định danh tác vụ không đồng nghĩa với event

Một file mới xuất hiện không có nghĩa quá trình ghi đã hoàn tất. Nếu nhận `ENTRY_MODIFY` nhiều lần, cũng không có bảo đảm file đã ổn định. Với producer do ứng dụng kiểm soát, có thể chọn giao thức ghi tệp tạm rồi publish bằng đổi tên; với nguồn bên ngoài, có thể cần kiểm tra kích thước ổn định, retry có giới hạn hoặc một marker “ready”.

**Không dùng một lần `ENTRY_CREATE` làm tín hiệu chắc chắn file đã ghi đủ byte**.

## 12. `OVERFLOW` và “event bị mất” khác “WatchKey invalid”

Hai trạng thái có thể cùng xuất hiện, nhưng cần phân loại riêng:

| Điều kiện | `key.isValid()` | Có chắc event đầy đủ? | Hành động |
| --- | --- | --- | --- |
| Key hợp lệ, không có overflow quan sát | Có thể `true` | Không có cam kết tuyệt đối về sự kiện ở mọi provider | Tiếp tục theo dõi + đối soát theo yêu cầu |
| Nhận `OVERFLOW` | Có thể vẫn `true` | **Không** | Rescan hoặc đối soát lại trạng thái |
| `key.reset() == false` | `false` | Không thể tiếp tục tin registration cũ | Ngừng dùng key, phục hồi hoặc loại registration |
| WatchService đã đóng | Các key bị invalid | Không còn nguồn notification hoạt động | Mở service/đăng ký mới nếu cần |

**Không giải quyết overflow bằng `reset` đơn độc.** `reset` tái kích hoạt vòng đời key hợp lệ, nhưng không tạo lại những event đã bị hệ thống bỏ. Để khôi phục một chỉ mục chính xác, phải đọc lại trạng thái **thực** của directory.

### 12.1. Chiến lược đối soát thực tế

Ví dụ indexer giữ map `Path → metadata/hash`:

1. Đăng ký watcher cho directory đã biết.
2. Quét trạng thái ban đầu để có baseline.
3. Mỗi event cập nhật hoặc đánh dấu đường dẫn cần quét lại.
4. Khi overflow, đánh dấu cả directory/cây tương ứng **dirty**.
5. Dùng `Files.walkFileTree`/`Files.readAttributes` để tạo lại baseline khi đủ điều kiện.
6. Xử lý những thay đổi diễn ra giữa các bước bằng watcher + chu kỳ reconciliation.
7. Nếu key invalid, khởi tạo lại registration trước khi tiếp tục phụ thuộc event.

Đây là mô hình tổng quan; việc kết hợp watcher và snapshot phải được thiết kế cẩn thận để tránh race. WatchService **không phải một transaction log bền vững** có thể replay mọi thay đổi sau khi ứng dụng ngừng chạy.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “`take()` trả một event.” | `take` trả `WatchKey`, không trả `WatchEvent` | Gọi `key.pollEvents()` |
| “Mỗi key nhận được có đúng một event.” | Key có thể gom nhiều event, có coalescing | Duyệt toàn bộ danh sách pending |
| “`pollEvents()` tự reset key.” | Hai chức năng khác nhau | Gọi `reset` sau khi drain và xử lý |
| “`reset() == true` nghĩa là đã quét đủ mọi thay đổi.” | Chỉ phản ánh key còn valid | Xử lý overflow và đối soát khi cần |
| “`reset() == false` có nghĩa chắc chắn directory bị xóa.” | Key có thể invalid vì cancel, watcher.close, mất truy cập | Kiểm tra ngữ cảnh; không suy nguyên nhân từ một boolean |
| “Gọi `reset()` nhiều lần sẽ sửa key đã cancel.” | Invalid key không được phục hồi bằng reset | Đăng ký mới nếu điều kiện cho phép |
| “`cancel()` đóng cả watcher.” | Chỉ hủy một registration | Có thể theo dõi các key khác |
| “Sau cancel queue không thể còn key đó.” | Key có thể đã được signal/queue trước cancel | Kiểm tra validity/reset khi nhận |
| “Đăng ký lại luôn sinh một key mới.” | Key valid đăng ký trùng có thể được dùng lại/cập nhật | Quản lý registration theo Watchable |
| “`poll(timeout)==null` nghĩa là key mất hiệu lực.” | Chỉ chưa có key trong lần chờ | Phân biệt timeout với invalidity |
| “`key.watchable()` là tệp gây event.” | Là đối tượng directory đăng ký | Dùng `event.context()` với directory |
| “`event.context()` luôn là absolute Path.” | Với ENTRY event thường là tương đối | `watchedDirectory.resolve(relative)` |
| “`OVERFLOW` luôn có context là Path.” | Có thể null và mang ý nghĩa mất event | Kiểm tra kind trước khi cast |
| “Không có `OVERFLOW` thì không thể mất event.” | Provider và filesystem có giới hạn | Reconciliation khi cần tính đúng đắn cao |
| “`ENTRY_CREATE` đồng nghĩa file đã ghi xong.” | Producer có thể tiếp tục ghi | Thiết kế giao thức ready/publish |
| “Theo dõi root tự theo dõi mọi subdirectory.” | Không tự động recursive | Đăng ký từng directory và xử lý thay đổi cây |
| “Key hợp lệ nghĩa là mọi lần I/O sau đó sẽ thành công.” | File có thể bị đổi/xóa/quyền thay đổi | Bắt lỗi tại lệnh I/O thật |
| “Đóng watcher rồi vẫn chờ `take` như cũ.” | Service đã đóng | Kết thúc worker hoặc tạo service mới |
| “Thread bị interrupt thì nuốt exception rồi tiếp tục.” | Có thể vi phạm shutdown policy | Khôi phục interrupt và dừng có kiểm soát |
| “`WatchService` thay thế snapshot/backup.” | Event không phải nhật ký giao dịch đầy đủ | Dùng quét trạng thái và đối soát |
| “Thứ tự event chính là thứ tự mọi thay đổi vật lý.” | Provider có thể coalescing/độ trễ/overflow | Không dựng thứ tự tuyệt đối từ notification |
| “Reset có thể dùng cho key bất kỳ từ watcher khác.” | Mỗi key thuộc đăng ký/service tương ứng | Quản lý key đúng nguồn và vòng đời |

## 14. Bài tập tự luyện và đáp án

### Bài 1 — Thiếu reset

Một loop gọi `watcher.take()`, lấy `key.pollEvents()` rồi chạy lại `take` mà không reset. Vì sao có thể chỉ nhận được thông báo đầu tiên?

**Đáp án:** Vì key đã SIGNALLED, sau khi được dequeue vẫn cần `reset()` để rearm trạng thái. `pollEvents` chỉ drain event, không chuyển key sang READY.

### Bài 2 — Giá trị reset

Sau khi xử lý batch, `key.reset()` trả `false`. Bạn nên gọi `reset` thêm nhiều lần hay làm gì khác?

**Đáp án:** Không gọi lặp với hy vọng khôi phục. Key đã invalid. Loại khỏi map registration; nếu cần theo dõi lại, đảm bảo watcher mở, directory hợp lệ rồi thử `register` mới và xử lý lỗi.

### Bài 3 — Cancel một directory

Ứng dụng đang theo dõi ba directory trên một WatchService. Khi không cần theo dõi một directory nữa, gọi `key.cancel()` trên key đó có đóng watcher và làm hai key còn lại vô hiệu hóa không?

**Đáp án:** Không. `cancel` hủy registration tương ứng. Hai key còn lại có thể tiếp tục hoạt động. `WatchService.close()` mới đóng toàn bộ service và làm invalid những đăng ký gắn với nó.

### Bài 4 — Key valid sau khi reset

`key.reset() == true` có đủ để đảm bảo mọi tệp đã được xử lý và không có event bị mất không?

**Đáp án:** Không. Nó chỉ cho biết key còn valid. Ứng dụng phải xử lý đủ các event lấy được, theo dõi `OVERFLOW` và dùng reconciliation khi yêu cầu đầy đủ.

### Bài 5 — Vì sao `pollEvents` trước `reset`?

Nếu reset trong khi vẫn còn pending events mà chưa gọi `pollEvents`, điều gì có thể xảy ra?

**Đáp án:** Key có thể được queue lại ngay do còn event đang chờ, nhưng các event đó chưa được ứng dụng xử lý. Chu trình thường dùng là drain pending events, xử lý/lên lịch và reset.

### Bài 6 — Watchable và context

Watcher đăng ký `Path.of("data","incoming")`, nhận ENTRY_CREATE có `context() = Path.of("a.txt")`. Đường dẫn ứng dụng nên tạo là gì?

**Đáp án:** `((Path) key.watchable()).resolve((Path) event.context())`, tương ứng `data/incoming/a.txt` về mặt tên. Nó chưa đảm bảo file vẫn tồn tại hoặc hoàn tất ghi.

### Bài 7 — OVERFLOW

`WatchKey` nhận event kind `OVERFLOW` nhưng `key.isValid() == true`. Chỉ cần reset rồi coi index vẫn chính xác được không?

**Đáp án:** Không. `OVERFLOW` cho biết có thể mất event. Cần đối soát/rescan để phục hồi trạng thái; reset chỉ xử lý vòng đời key.

### Bài 8 — Hết thời gian chờ

`watcher.poll(2, SECONDS)` trả `null`. Có phải watcher đã đóng?

**Đáp án:** Không. Nó chỉ có nghĩa không nhận key trong khoảng chờ đó. WatchService đóng thường biểu hiện khác, như `ClosedWatchServiceException`. Không suy invalidity từ `null`.

### Bài 9 — Directory bị xóa rồi tạo lại

Một directory được watch bị xóa, key invalid. Sau đó directory cùng tên được tạo lại. Key cũ có tự valid không?

**Đáp án:** Không. Cần đăng ký mới nếu mục tiêu tồn tại và watcher đang hoạt động, có chính sách phát hiện thư mục xuất hiện lại và rescan để giảm mất dữ liệu trong khoảng trống theo dõi.

### Bài 10 — Tại sao không đọc file nặng trong event loop?

Một consumer mở mọi file ngay trong lúc giữ key SIGNALLED và mất vài giây cho một lần parse. Hậu quả gì?

**Đáp án:** Notification có thể tích lũy, coalesce hoặc overflow; consumer có độ trễ cao. Nên drain nhanh, đưa tác vụ sang queue có backpressure, rồi reset và đối soát khi cần.

### Bài 11 — Event count

`WatchEvent.count()` lớn hơn 1 có nghĩa file đã được ghi chính xác `count` lần và mỗi thao tác đã hoàn tất không?

**Đáp án:** Không thể kết luận như vậy. Event có thể được coalesce theo provider; count thể hiện thông tin coalescing của notification, không phải nhật ký đầy đủ hay bảo đảm dữ liệu đã sẵn sàng.

### Bài 12 — Multiple registration

Cùng một directory đã đăng ký trên WatchService với key valid; ứng dụng gọi `register` lại với kinds mới. Có được bỏ qua reset của key đang SIGNALLED không?

**Đáp án:** Không. Đăng ký lại có thể trả key hiện có và thay đổi những event kinds được yêu cầu; nó không thay nghĩa vụ drain/reset khi consumer nhận key đang SIGNALLED.

### Bài 13 — Nhận key đã invalid

Một key đã bị cancel nhưng vẫn nằm trong queue. Consumer nhận nó. Có nên báo “directory vẫn valid vì tôi nhận được key” không?

**Đáp án:** Không. Queue có thể còn key invalid từ trước. Kiểm tra `isValid()`/`reset()` và chính sách trạng thái; nhận key từ queue không chứng minh registration còn hoạt động.

### Bài 14 — Xử lý interrupt

`watcher.take()` ném `InterruptedException` trong worker được yêu cầu shutdown. Nên làm gì?

**Đáp án:** Thường khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` và thoát worker có kiểm soát; đóng watcher khi hết vòng đời. Không tự nuốt interrupt rồi tiếp tục chờ vô hạn.

### Bài 15 — Không phải watcher đệ quy

Ứng dụng chỉ register `root`. Một file được tạo sâu trong `root/a/b`. Có luôn nhận ENTRY_CREATE trực tiếp cho file đó không?

**Đáp án:** Không. Đăng ký một directory thường nhận event của entry trực tiếp. Muốn theo dõi cây, đăng ký các directory con và xử lý việc tạo/xóa directory mới cùng reconciliation.

## 15. Checklist trước khi đưa WatchKey vào ứng dụng

- [ ] Đã phân biệt `WatchService`, `WatchKey` và `WatchEvent` rõ ràng.
- [ ] Registration được tạo trên directory hợp lệ với event kinds cần dùng; WatchService có vòng đời được quản lý.
- [ ] Vòng lặp luôn lấy `key.pollEvents()` và xử lý các event trước khi gọi `key.reset()`.
- [ ] Đã kiểm tra kết quả `reset()==false` và có hành vi dừng/loại key/đăng ký lại tương ứng.
- [ ] Không coi `isValid()` là thao tác rearm, cũng không coi `reset()==true` là xác nhận mọi event được ghi nhận.
- [ ] Đã phân biệt `cancel` trên một key với `close` trên toàn bộ service.
- [ ] Có thể xử lý key đã invalid nhưng vẫn được trả ra khỏi queue.
- [ ] Khi đăng ký lại, hiểu trường hợp key valid hiện có được tái sử dụng và trường hợp key invalid cần registration mới.
- [ ] Có xử lý `OVERFLOW` bằng rescan/đối soát, không chỉ reset.
- [ ] Với ENTRY events, kiểm tra context là `Path` tương đối và resolve theo `key.watchable()`; không cast context OVERFLOW.
- [ ] Không coi `ENTRY_CREATE` là tín hiệu file đã ghi xong.
- [ ] Không đòi watcher cung cấp mọi thay đổi chính xác một-một hoặc thứ tự tuyệt đối.
- [ ] Nếu theo dõi cây, có cơ chế đăng ký từng directory và quản lý directory mới/xóa.
- [ ] Có cơ chế dừng worker: timeout, interruption, WatchService.close và xử lý `ClosedWatchServiceException`.
- [ ] Không làm I/O quá nặng trên event-consumer thread; có quota/backpressure.
- [ ] Khi một registration invalid, không ngừng mọi registration khác nếu chúng vẫn cần thiết.
- [ ] Xử lý thay đổi đồng thời, quyền truy cập, file biến mất hoặc bị thay thế khi mở thực tế.
- [ ] Có test hai event sau reset, cancel/reset false, đăng ký lại và invalidation sau watcher.close.
- [ ] Đánh dấu API lõi `WatchService`/`WatchKey` có từ Java 7; `Path.of` và cú pháp `instanceof Path relative` trong demo yêu cầu Java 11/16+, ví dụ được biên dịch `--release 17`.

## 16. Tổng kết

`WatchKey` không phải một thông báo một lần rồi bỏ, mà là **đối tượng đại diện cho một registration có trạng thái**. Một key hợp lệ bắt đầu ở trạng thái READY, được SIGNALLED khi có sự kiện và được `WatchService` trả cho consumer. `pollEvents()` lấy các event pending, **`reset()` rearm key nếu còn valid**, còn `cancel()` hoặc `WatchService.close()` có thể khiến key invalid. Khi `reset()` trả `false`, đăng ký cũ không thể dùng tiếp; nếu vẫn cần theo dõi, phải quản lý vòng đời và đăng ký lại trong điều kiện phù hợp.

Ngoài reset/invalidation, phần mềm thực tế cần xử lý **OVERFLOW**, context tương đối, event coalescing, file biến động, race, nhiều directory, interruption và cleanup. `WatchService` hữu ích để biết “có thể đã có thay đổi” nhưng **không phải nguồn chân lý tuyệt đối** cho toàn bộ lịch sử filesystem. Kết hợp notification với quét/đối soát trạng thái khi cần độ đầy đủ giúp một hệ thống Java hiện đại theo dõi tệp tin đáng tin cậy hơn.