# Thời gian tạo, sửa đổi và truy cập của tệp với `FileTime` trong Java 7+

> **Chủ đề:** Đọc và xử lý ba mốc thời gian của tệp/thư mục: **thời gian tạo** (`creationTime`), **lần sửa đổi cuối** (`lastModifiedTime`) và **lần truy cập cuối** (`lastAccessTime`). Java NIO.2 cung cấp `java.nio.file.attribute.FileTime`, `BasicFileAttributes`, `BasicFileAttributeView` cùng các phương thức của `Files` từ **Java 7**. Các API này **vẫn được sử dụng trong Java 17+**. Bài phân biệt rõ giá trị trên trục thời gian, cách hiển thị theo múi giờ, độ chính xác của filesystem, tính khả dụng của từng thuộc tính, thao tác cập nhật và rủi ro khi dùng timestamp làm bằng chứng nghiệp vụ.

## 1. Một tệp có thể có những mốc thời gian nào?

Một đường dẫn như `reports/summary.txt` không chỉ có tên và nội dung. Filesystem có thể quản lý metadata mô tả **những thời điểm liên quan đến đối tượng**.

| Thuộc tính | API Java | Câu hỏi trả lời | Chú ý |
| --- | --- | --- | --- |
| **Thời gian tạo** | `creationTime()` | Đối tượng được tạo vào lúc nào theo metadata của filesystem? | Không phải hệ thống nào cũng lưu được creation time thực |
| **Lần sửa đổi cuối** | `lastModifiedTime()` | Nội dung/metadata được xem là sửa đổi gần nhất vào lúc nào theo provider? | Có thể thay khi ghi, được cập nhật thủ công, hoặc bị làm tròn |
| **Lần truy cập cuối** | `lastAccessTime()` | Metadata ghi nhận lần truy cập cuối lúc nào? | Nhiều filesystem tắt, trì hoãn hoặc giới hạn việc cập nhật atime |

Chúng thường được gọi bằng các thuật ngữ **birth/creation time**, **mtime** và **atime** trong tài liệu hệ điều hành. Không nên đồng nhất **creation time** với trường **ctime** của Unix/POSIX: trong nhiều ngữ cảnh Unix, *ctime* là **thời điểm thay đổi trạng thái/metadata**, không phải thời điểm tạo tệp. API `BasicFileAttributes.creationTime()` không được mặc định hiểu là Unix ctime.

### 1.1. Ví dụ tình huống

Một tệp được tạo lúc 09:00, được viết lại lúc 10:30, sau đó được đọc lúc 11:00 có thể có:

```text
creationTime      = 09:00  (khi tạo theo metadata)
lastModifiedTime  = 10:30  (khi nội dung được sửa)
lastAccessTime    = 11:00  (nếu filesystem có cập nhật access time)
```

Đây là **mô hình để hình dung**, không phải quy luật tất cả filesystem luôn lưu ba giá trị như vậy. Một số hệ thống không có creation time, có hệ thống không cập nhật last access trên mỗi lần đọc, và có ứng dụng chủ động chỉnh sửa timestamp sau khi copy/import.

**Bài học chính:** ba thuộc tính có tên và ý nghĩa khác nhau nhưng không nhất thiết phản ánh một nhật ký hoạt động chính xác, đầy đủ hoặc không thể sửa đổi.

### 1.2. `Path` và `FileTime` có vai trò khác nhau

- `Path` xác định **vị trí tệp/thư mục** theo provider, chẳng hạn `Path.of("data","report.txt")`.
- `Files` thực hiện **truy cập filesystem** và đọc/ghi metadata.
- `BasicFileAttributes` là **tập thuộc tính được đọc** ở một thời điểm, gồm ba mốc thời gian và các thuộc tính như `size`, `isRegularFile`.
- `FileTime` là **kiểu dữ liệu biểu diễn một mốc thời gian**, không phải object mở file, không chứa đường dẫn và không tự cập nhật khi file thay đổi.

Đừng nhầm việc tạo một `FileTime` mới với việc thay đổi timestamp của file. Chỉ những lời gọi tới `Files.setLastModifiedTime`, `BasicFileAttributeView.setTimes` hoặc các API thuộc tính tương ứng mới **yêu cầu cập nhật metadata** của file.

## 2. Những import và API cần biết

Các import thông dụng:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.LinkOption;
import java.nio.file.attribute.FileTime;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.BasicFileAttributeView;
import java.time.Instant;
import java.time.ZoneId;
import java.util.concurrent.TimeUnit;
```

Các API thường dùng:

```java
BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);

FileTime created = attrs.creationTime();
FileTime modified = attrs.lastModifiedTime();
FileTime accessed = attrs.lastAccessTime();

FileTime justModified = Files.getLastModifiedTime(path);
Files.setLastModifiedTime(path, desiredModifiedTime);

BasicFileAttributeView view =
        Files.getFileAttributeView(path, BasicFileAttributeView.class);
view.setTimes(newModified, newAccessed, newCreated);
```

Đây là **các snippet trong một method có biến `path` và các giá trị FileTime tương ứng**, cần xử lý hoặc khai báo `IOException`. Không phải một chương trình Java độc lập để chép nguyên vào file.

### 2.1. Có cần cài thư viện ngoài?

Không. `FileTime` nằm trong `java.base` của JDK; `Files`, `Path` và các basic attribute interfaces cũng là Java standard library.

**Các mốc phiên bản:**

- **Java 7:** NIO.2 `Path`, `Files`, `FileTime`, `BasicFileAttributes`, `BasicFileAttributeView`, `FileTime.fromMillis`, `FileTime.from(long,TimeUnit)`, `FileTime.toMillis` và `setTimes`.
- **Java 8:** `java.time.Instant` và các chuyển đổi `FileTime.from(Instant)`/`toInstant()`; cách biểu đạt UTC/zone hiện đại.
- **Java 11:** `Path.of(...)`, `Files.writeString(...)` và `Files.readString(...)` được dùng để làm ví dụ Java 17 ngắn hơn.
- **Java 17+:** các API trên tiếp tục được hỗ trợ. Khi dự án build target Java 7 thật, hãy thay các helper mới hơn cho phù hợp, nhưng không cần quay về `java.io.File` để đọc ba timestamp này.

## 3. `FileTime` biểu diễn điều gì?

`FileTime` là một value type bất biến đại diện cho **một thời điểm trên trục thời gian**. Nó không chứa múi giờ hiển thị, không là “ngày giờ theo máy local” và cũng không cho biết tệp được tạo ra ở vị trí nào.

Khi `FileTime` dùng giá trị epoch, mốc cơ sở là:

```text
1970-01-01T00:00:00Z  (Unix epoch / UTC)
```

Chữ `Z` biểu thị múi giờ UTC. Các số epoch có thể âm cho thời điểm **trước** epoch.

Tạo FileTime:

```java
FileTime t1 = FileTime.fromMillis(1_577_934_245_123L);
FileTime t2 = FileTime.from(1_577_934_245L, TimeUnit.SECONDS);
FileTime t3 = FileTime.from(
        Instant.parse("2020-01-02T03:04:05.123Z"));
```

Đây là snippet Java 8+ vì sử dụng `Instant`. Lưu ý: `t1` và `t3` cùng thời điểm tới millisecond trong ví dụ, nhưng `t2` chỉ có precision tới giây và sớm hơn 123 millisecond.

Đọc FileTime:

```java
long epochMilliseconds = t1.toMillis();
Instant instant = t1.toInstant();
long seconds = t1.to(TimeUnit.SECONDS);
```

Đây là snippet với `t1` đã khai báo.

### 3.1. Không nhân/chia 1.000 bằng cảm tính

`FileTime.fromMillis(value)` hiểu tham số là **milli-giây tính từ epoch**. `FileTime.from(value, TimeUnit.SECONDS)` lại hiểu tham số là **giây**. Nếu nhập 1.577.934.245 vào overload milliseconds trong khi nguồn thật là seconds, kết quả sai rất xa thời điểm mong muốn.

Hãy lưu kèm tên trường rõ ràng như `epochMillis`, `epochSeconds`; dùng `TimeUnit` hoặc `Instant` để tránh sai đơn vị.

### 3.2. `equals` và `compareTo`

`FileTime` hỗ trợ `equals` và `compareTo` để kiểm tra **cùng thời điểm** hoặc **thứ tự thời gian**. Không cần lấy `toString()` rồi so sánh từ điển.

Ví dụ:

```java
boolean same = first.equals(second);
boolean newer = first.compareTo(second) > 0;
```

Đây là snippet với hai biến `FileTime first` và `second`. So sánh theo thời điểm, không phụ thuộc vào cách chuỗi được format cho UI.

### 3.3. `FileTime` là immutable, nhưng metadata tệp không bất biến

`FileTime.fromMillis(...)` tạo một value object. Sau khi `Files.readAttributes` trả về đối tượng FileTime, nếu một tiến trình khác sửa timestamp trên đĩa, **FileTime đã đọc không tự thay đổi**. Muốn nhận dữ liệu mới, cần đọc lại attributes từ filesystem.

Ngược lại, giá trị được tạo bằng `FileTime.from(...)` không tự được lưu lên tệp. Phải sử dụng một API ghi metadata và xử lý các lỗi có thể xảy ra.

## 4. Chương trình 1: `FileTime`, `Instant`, UTC và múi giờ

Lưu thành `FileTimeValuesDemo.java`:

```java
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.time.ZoneId;
import java.util.concurrent.TimeUnit;

public class FileTimeValuesDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2020-01-02T03:04:05.123Z");
        FileTime exact = FileTime.from(instant);
        FileTime millis = FileTime.fromMillis(instant.toEpochMilli());
        FileTime seconds = FileTime.from(instant.getEpochSecond(), TimeUnit.SECONDS);

        System.out.println("instant=" + exact.toInstant());
        System.out.println("epochMillis=" + exact.toMillis());
        System.out.println("millisEqual=" + exact.equals(millis));
        System.out.println("secondsEqual=" + exact.equals(seconds));
        System.out.println("secondsInstant=" + seconds.toInstant());
        System.out.println("hcmLocal=" +
                exact.toInstant().atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                        .toLocalDateTime());
        System.out.println("exactIsLater=" + (exact.compareTo(seconds) > 0));
    }
}
```

Lệnh biên dịch và chạy với JDK 17:

```bash
javac -encoding UTF-8 --release 17 FileTimeValuesDemo.java
java FileTimeValuesDemo
```

Stdout **đã được biên dịch và chạy kiểm chứng**:

```text
instant=2020-01-02T03:04:05.123Z
epochMillis=1577934245123
millisEqual=true
secondsEqual=false
secondsInstant=2020-01-02T03:04:05Z
hcmLocal=2020-01-02T10:04:05.123
exactIsLater=true
```

### 4.1. Giải thích từng dòng

- `instant` có `Z` → thời điểm ở UTC.
- `epochMillis=1577934245123` là số millisecond tính từ epoch, không gắn với timezone.
- `millisEqual=true` vì nguồn có độ chính xác millisecond; `FileTime.fromMillis` khôi phục cùng thời điểm.
- `secondsEqual=false` vì phiên bản theo seconds mất 123 millisecond lẻ.
- `hcmLocal` hiển thị **cùng thời điểm** trong múi giờ `Asia/Ho_Chi_Minh` tại ngày ví dụ, tức UTC+07:00. Không có thao tác “đổi giá trị timestamp file” nào.
- `exactIsLater=true` vì `exact` muộn hơn `seconds` 123 millisecond.

Trong ứng dụng, `FileTime.toInstant()` phù hợp để dùng với `ZonedDateTime` hoặc `DateTimeFormatter` nếu muốn hiển thị theo múi giờ người dùng. **Không** tự cộng 7 giờ vào epoch millisecond rồi lưu lại như một timestamp khác.

### 4.2. `Instant` và `LocalDateTime` khác nhau ở điểm nào?

`Instant` xác định một thời điểm tuyệt đối trên UTC timeline. `LocalDateTime` là biểu diễn ngày giờ **không kèm thông tin timezone/offset**. Trong demo, `atZone(ZoneId.of(...))` chuyển `Instant` thành giờ địa phương **để hiển thị**. `toLocalDateTime()` chỉ bỏ thông tin zone ở **giá trị hiển thị** cuối cùng.

Nếu ứng dụng lưu `LocalDateTime` thay cho `Instant` mà không lưu timezone hoặc quy tắc offset, có thể gặp sai lệch khi chuyển máy, đổi múi giờ, DST ở các khu vực khác hoặc parse thời điểm lịch sử. Ưu tiên lưu `Instant`/epoch hoặc `FileTime` theo hợp đồng, rồi format ở giao diện.

## 5. Độ chính xác: nano-giây, milli-giây và giới hạn provider

`FileTime` có thể biểu diễn thời điểm ở các độ phân giải khác nhau, nhưng **filesystem không bắt buộc lưu chính xác tới nano-giây**.

Có **hai tầng độ chính xác**:

1. **Giá trị Java `FileTime`:** có thể được tạo từ số nano-giây, micro-giây, milli-giây, giây... theo `TimeUnit`.
2. **Timestamp trên filesystem:** bị giới hạn bởi độ phân giải, epoch và phạm vi mà file store/provider hỗ trợ. Khi set, giá trị có thể bị làm tròn/cắt bớt hoặc không được hỗ trợ.

Đừng nhầm “kiểu dữ liệu có thể biểu diễn nano-second” với “ổ đĩa của người dùng luôn lưu timestamp tới nano-second”.

### 5.1. Chương trình 2: precision loss khi chuyển sang millisecond

Lưu thành `FileTimePrecisionDemo.java`:

```java
import java.nio.file.attribute.FileTime;
import java.util.concurrent.TimeUnit;

public class FileTimePrecisionDemo {
    public static void main(String[] args) {
        FileTime precise = FileTime.from(1_234_567_890L, TimeUnit.NANOSECONDS);
        FileTime truncated = FileTime.fromMillis(precise.toMillis());
        System.out.println("instant=" + precise.toInstant());
        System.out.println("millis=" + precise.toMillis());
        System.out.println("millisEqual=" + precise.equals(truncated));
        System.out.println("negativeSecond=" +
                FileTime.from(-1, TimeUnit.SECONDS).toInstant());
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileTimePrecisionDemo.java
java FileTimePrecisionDemo
```

Stdout đã kiểm chứng:

```text
instant=1970-01-01T00:00:01.234567890Z
millis=1234
millisEqual=false
negativeSecond=1969-12-31T23:59:59Z
```

**Tại sao `millisEqual=false`?** Giá trị gốc có 1 giây + 234.567.890 nano-giây. `toMillis()` đưa về **1.234 millisecond**, mất 567.890 nano-giây cuối; tạo lại `FileTime.fromMillis(1234)` chỉ biểu diễn thời điểm 1.234.000.000 nano-giây kể từ epoch.

`negativeSecond` cho thấy cách biểu diễn thời điểm trước 1970: giá trị âm là hoàn toàn hợp lệ, không phải “lỗi timestamp”.

### 5.2. `toMillis()` có luôn là cách so sánh tốt nhất không?

Không. Hai FileTime khác nhau vài micro-/nano-giây có thể có **cùng** `toMillis()`. Nếu muốn biết FileTime nào mới hơn ở precision có sẵn, dùng `compareTo`; nếu cần làm việc theo trục thời gian Java 8+, dùng `toInstant()` nhưng lưu ý phạm vi cực lớn có thể được clamp khi chuyển đổi.

Theo Javadoc, `FileTime` có thể biểu diễn thời điểm xa hơn phạm vi của `Instant`; `toInstant()` trong trường hợp vượt phạm vi sẽ bão hòa về `Instant.MIN`/`Instant.MAX`. `toMillis()` cũng có quy tắc bão hòa khi phép chuyển đổi vượt phạm vi `long`. Với metadata thông thường của tệp, ít khi chạm điều kiện này, nhưng đừng dùng việc convert rồi so sánh như một phép chứng minh exact cho mọi giá trị cực hạn.

### 5.3. Kiểm thử setter phải chấp nhận khả năng làm tròn

Nếu ứng dụng set `2020-01-02T03:04:05.123456789Z` rồi đọc lại chỉ còn `.123Z`, điều đó **có thể do precision của filesystem**. Khi test trên nhiều provider, nên:
- Chọn giá trị trong phạm vi được hỗ trợ.
- Định nghĩa mức sai lệch cho phép theo hợp đồng filesystem.
- Phân biệt lỗi “không hỗ trợ timestamp” với kết quả “bị làm tròn”.
- Không mặc định kết quả `actual.equals(requested)` luôn true ở mọi file store.

## 6. Đọc ba mốc thời gian với `BasicFileAttributes`

Đây là cách học trực tiếp và thực tế nhất:

```java
BasicFileAttributes attributes =
        Files.readAttributes(path, BasicFileAttributes.class);

FileTime created = attributes.creationTime();
FileTime modified = attributes.lastModifiedTime();
FileTime accessed = attributes.lastAccessTime();
```

Đây là snippet với `Path path` đã có, trong method xử lý hoặc khai báo `IOException`.

`BasicFileAttributes` còn có thông tin như `size()`, `isRegularFile()`, `isDirectory()`, `isSymbolicLink()` và `fileKey()`. Vì vậy với một tệp cần đọc **cả ba timestamp cùng loại**, đọc attributes trong một lời gọi thường rõ hơn gọi nhiều method riêng.

**Tuy nhiên:** `readAttributes` đọc một tập thuộc tính như một bulk operation, nhưng Javadoc **không bắt buộc mọi provider đọc chúng nguyên tử với mọi thao tác filesystem khác**. Nếu file đang bị sửa đồng thời, đừng coi đó là snapshot bất biến của toàn hệ thống.

### 6.1. Những mốc thời gian nào có thể thiếu?

API `BasicFileAttributes` trả về kiểu `FileTime` cho cả ba method, nhưng **giá trị không nhất thiết là thời gian thực được filesystem theo dõi**:

- Nếu không hỗ trợ **creation time**, provider có thể trả về giá trị mặc định, thường là last-modified-time hoặc epoch.
- Nếu không hỗ trợ **last-access-time**, provider có thể trả về last-modified-time hoặc epoch.
- Nếu không hỗ trợ **last-modified-time**, provider có thể trả một giá trị mặc định, thường là epoch.

Đây là hành vi **được tài liệu hóa**, không phải lý do để giả định “creationTime() luôn đo chính xác lúc file được tạo”. Đặc biệt, một object `FileTime` **khác null** không chứng minh underlying file store thật sự hỗ trợ birth time.

### 6.2. Vì sao ba timestamp có thể bằng nhau?

Có nhiều khả năng:

- File được tạo và ghi trong cùng một khoảng thời gian rất ngắn.
- Hệ thống chỉ lưu độ phân giải thô (ví dụ làm tròn tới giây).
- Một thuộc tính không được hỗ trợ và provider dùng fallback như `lastModifiedTime`.
- File được copy/import với metadata đã được giữ hoặc bị viết lại.
- Ứng dụng có quyền đã cố ý chỉnh mốc thời gian.

Không nên dùng phép so sánh `created.equals(modified)` để suy ra một sự kiện chắc chắn như “file chưa từng được sửa sau khi tạo”.

## 7. Chương trình 3: đọc thời gian tạo/sửa/truy cập và file attributes

Lưu thành `FileTimesReadDemo.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.BasicFileAttributes;

public class FileTimesReadDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("file-times-read-");
        Path file = directory.resolve("sample.bin");
        try {
            Files.write(file, new byte[] {1, 2, 3, 4});
            BasicFileAttributes attrs =
                    Files.readAttributes(file, BasicFileAttributes.class);
            BasicFileAttributeView view =
                    Files.getFileAttributeView(file, BasicFileAttributeView.class);

            System.out.println("regular=" + attrs.isRegularFile());
            System.out.println("bytes=" + attrs.size());
            System.out.println("viewName=" + view.name());
            System.out.println("threeFileTimesPresent=" +
                    (attrs.creationTime() != null &&
                     attrs.lastModifiedTime() != null &&
                     attrs.lastAccessTime() != null));
            System.out.println("modifiedMatchesConvenience=" +
                    attrs.lastModifiedTime().equals(Files.getLastModifiedTime(file)));
            System.out.println("modifiedMatchesView=" +
                    attrs.lastModifiedTime().equals(view.readAttributes().lastModifiedTime()));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileTimesReadDemo.java
java FileTimesReadDemo
```

Stdout **đã chạy thành công trên provider mặc định của môi trường kiểm thử**:

```text
regular=true
bytes=4
viewName=basic
threeFileTimesPresent=true
modifiedMatchesConvenience=true
modifiedMatchesView=true
```

### 7.1. Vì sao không in ngày giờ tạo/touch thực tế?

Vì `Files.createTempDirectory` và `Files.write` chạy ở thời điểm **khác nhau trên mỗi máy**, in trực tiếp các timestamp sẽ tạo stdout không tái lập. Demo thay bằng những kiểm tra mà người học có thể quan sát ổn định trong môi trường filesystem bình thường.

- `regular=true`: tệp tạm vừa ghi là regular file.
- `bytes=4`: bốn byte được ghi bằng `Files.write`.
- `viewName=basic`: basic attribute view có tên `"basic"` theo hợp đồng.
- `threeFileTimesPresent=true`: các method trả các FileTime, **không phải bằng chứng hỗ trợ ba timestamp gốc**.
- Hai dòng `modifiedMatches...` so sánh last-modified đọc qua ba đường API khác nhau khi test **không có writer đồng thời**.

Nếu một tiến trình khác sửa file giữa các lần đọc, hai phép so sánh có thể false mà không chứng minh JDK lỗi.

### 7.2. `BasicFileAttributeView` dùng để làm gì?

`Files.getFileAttributeView(path, BasicFileAttributeView.class)` cung cấp view để:

1. Gọi `view.readAttributes()` lấy `BasicFileAttributes`.
2. Gọi `view.setTimes(modified, access, created)` yêu cầu cập nhật một hoặc nhiều timestamp.

Nếu provider không có attribute view yêu cầu, method có thể trả `null`; code production cần kiểm tra capability hoặc xử lý phù hợp, thay vì luôn dereference `view`. Provider mặc định trong ví dụ hỗ trợ `basic`.

## 8. `Files.getLastModifiedTime`: tiện ích cho một timestamp

Khi chỉ cần **lần sửa đổi cuối**, bạn không nhất thiết phải đọc cả bộ thuộc tính:

```java
FileTime modified = Files.getLastModifiedTime(path);
```

Method còn có overload với `LinkOption...`:

```java
FileTime linkOwnTime =
        Files.getLastModifiedTime(link, LinkOption.NOFOLLOW_LINKS);
```

Đây là snippets trong method có `throws IOException`, với `path`/`link` đã có.

**Khác biệt quan trọng:** không có các tiện ích `Files.getCreationTime(path)` hay `Files.getLastAccessTime(path)` riêng tương đương trong API `Files`. Với hai thuộc tính đó, dùng `BasicFileAttributes`/`BasicFileAttributeView` hoặc dynamic attribute API.

### 8.1. Khi nào dùng `readAttributes` thay vì `getLastModifiedTime`?

- Cần đồng thời creation/access/modified → `BasicFileAttributes` thường rõ ràng nhất.
- Chỉ cần modified → `getLastModifiedTime` ngắn hơn.
- Đang có `BasicFileAttributeView` để setTimes và đọc lại → `view.readAttributes()` thuận tiện.
- Muốn lấy một tên thuộc tính theo chuỗi hoặc làm công cụ introspection → cân nhắc dynamic API, nhưng mất type safety và cần validate tên/value.

### 8.2. Đường dẫn không tồn tại có gì khác?

`Files.getLastModifiedTime` và `Files.readAttributes` thực hiện truy vấn hệ thống tệp thật, nên có thể ném `IOException` như `NoSuchFileException` hoặc `AccessDeniedException`. Không được dựa vào `Files.exists` trước đó như cách bảo đảm tệp vẫn tồn tại: file có thể bị xóa/thay thế giữa check và read.

## 9. Đọc thuộc tính theo tên động: `Files.getAttribute`/`readAttributes`

NIO.2 còn có cách làm việc theo tên thuộc tính:

```java
FileTime created = (FileTime) Files.getAttribute(
        path, "basic:creationTime");

FileTime modified = (FileTime) Files.getAttribute(
        path, "basic:lastModifiedTime");

FileTime accessed = (FileTime) Files.getAttribute(
        path, "basic:lastAccessTime");
```

Đây là snippets với `Path path` đã có và method phải xử lý `IOException`. Tiền tố `basic:` chỉ attribute view, còn phần sau là tên thuộc tính. Với API generic, `getAttribute` trả `Object` nên cần cast đúng kiểu.

Muốn đọc nhiều thuộc tính bằng tên động:

```java
java.util.Map<String, Object> times =
        Files.readAttributes(
            path, "basic:creationTime,lastModifiedTime,lastAccessTime");
```

Đây là snippet. Các value tương ứng có kiểu `FileTime`; key trong map là tên thuộc tính (ví dụ `"creationTime"`). Cách dùng này phù hợp với công cụ generic nhưng ít type-safe hơn `BasicFileAttributes` cho mã nghiệp vụ bình thường.

### 9.1. Không tự đoán tên thuộc tính

`BasicFileAttributes.creationTime()` không đồng nghĩa mọi filesystem luôn có trường tên `"birthtime"` hoặc `"ctime"` trong dynamic basic view. Các tên chuẩn trong `basic` là:

```text
creationTime
lastModifiedTime
lastAccessTime
```

Nếu cần thuộc tính đặc thù POSIX/DOS, phải xem attribute view/provider cụ thể. Các trường bổ sung không nhất thiết portable.

### 9.2. Số lần đọc không phải một transaction

Nếu gọi ba lần `Files.getAttribute` riêng, một writer khác có thể thay đổi file giữa các lần. Một lần `readAttributes` bulk giúp gom metadata trong một operation API, nhưng **không có bảo đảm toàn hệ thống bị đóng băng**. Với logic đòi hỏi tính nhất quán cao, cần cơ chế cấp filesystem/ứng dụng riêng.

## 10. Sửa thời gian chỉnh sửa cuối bằng `Files.setLastModifiedTime`

Đây là setter tiện nhất khi chỉ cần cập nhật **last-modified time**:

```java
FileTime chosen = FileTime.fromMillis(1_577_934_245_000L);
Files.setLastModifiedTime(path, chosen);
```

Đây là snippet. Kết quả return là `Path` đã cung cấp, còn giá trị thực lưu trên filesystem cần **đọc lại** để kiểm chứng độ chính xác/provider support. Method có thể ném `IOException` và mất precision theo file store.

### 10.1. Khi nào cần set mtime có chủ đích?

- Khôi phục metadata khi di chuyển/sao chép từ một nguồn tin cậy.
- Tạo fixture kiểm thử cho bộ lọc “thay đổi sau mốc T”.
- Tích hợp công cụ đồng bộ/backup với một metadata policy đã định nghĩa.
- Cài đặt một bước import có yêu cầu giữ thời gian sửa đổi ban đầu.

**Không coi setter này là cách lưu “sự kiện sửa đổi đã được chứng thực”.** Timestamp có thể bị thay bằng API, bởi hệ điều hành hoặc bởi người có quyền; nó không phải audit log bất biến.

### 10.2. Mtime khác content hash

Hai file có cùng `lastModifiedTime` nhưng **nội dung khác nhau** là điều có thể xảy ra, ví dụ:
- Timestamp bị làm tròn tới cùng một đơn vị thời gian.
- Một file được chỉnh sửa rồi mtime được đặt lại.
- Một công cụ copy bảo toàn thời gian cũ.
- Thời gian hệ thống có vấn đề hoặc metadata cache đã cũ.

Vì thế bộ đồng bộ dữ liệu có thể dùng mtime như **heuristic hiệu năng**, nhưng nếu tính đúng đắn quan trọng hãy kết hợp size, checksum/hash, version hoặc cơ chế consistency khác.

## 11. `BasicFileAttributeView.setTimes`: cập nhật một hoặc nhiều mốc

Để yêu cầu cập nhật ba thuộc tính, NIO.2 cung cấp:

```java
view.setTimes(lastModifiedTime, lastAccessTime, createTime);
```

**Thứ tự tham số rất quan trọng:**

1. `lastModifiedTime`.
2. `lastAccessTime`.
3. `createTime`.

Đừng chuyển nhầm `creationTime` vào tham số đầu chỉ vì bài học đang nói ba mốc theo thứ tự tạo/sửa/truy cập.

### 11.1. `null` nghĩa là giữ thuộc tính tương ứng

Các cách gọi:

```java
view.setTimes(newModified, null, null);
view.setTimes(null, newAccessed, null);
view.setTimes(null, null, newCreated);
```

Đây là các snippet với `BasicFileAttributeView view` và ba biến `FileTime` đã có.

Theo hợp đồng API, `null` nghĩa là không yêu cầu thay đổi thuộc tính tương ứng. Nếu **cả ba** là null thì method không có tác dụng.

**Cảnh báo tinh tế:** implementation có thể cần **đọc các thuộc tính hiện tại rồi ghi lại** khi chỉ cập nhật một vài giá trị; các thao tác đó có thể không atomic với thao tác filesystem khác và có thể làm giảm precision. Vì thế “tham số null không thay đổi thuộc tính” không phải lời hứa về một transaction đọc-sửa-ghi không mất độ chính xác trong mọi race.

### 11.2. Có setter riêng cho creationTime/lastAccessTime không?

Không có `Files.setCreationTime(...)` hay `Files.setLastAccessTime(...)` riêng theo kiểu `setLastModifiedTime` trong API `Files`. Muốn cập nhật chúng, dùng `BasicFileAttributeView.setTimes` hoặc `Files.setAttribute` (đều phụ thuộc provider support).

Ví dụ:

```java
Files.setAttribute(
        path,
        "basic:lastAccessTime",
        newAccessed);
```

Đây là snippet trong method có `throws IOException`. Khi sử dụng `setAttribute`, truyền đúng `FileTime` thay vì String dạng ngày giờ; phương thức làm việc với Java object theo attribute view đã chọn.

### 11.3. Creation time có phải lúc nào cũng sửa được?

**Không.** Một số filesystem không theo dõi birth time, một số provider chỉ đọc hoặc không cho phép cập nhật, và có hệ thống hạn chế phạm vi thời gian. Javadoc của `setTimes` cho biết hành vi khi cố set một timestamp **không hỗ trợ** hoặc giá trị ngoài phạm vi file store là **không được xác định cứng**: implementation có thể ném IOException hoặc không.

Vì vậy:
- Không hứa `setTimes(null,null,newCreated)` luôn đổi creation time.
- Không hứa nếu method trả bình thường thì mọi timestamp đã được ghi **chính xác từng nanosecond**.
- Nếu metadata có ý nghĩa nghiệp vụ, cần đọc lại và so theo chính sách precision.
- Nếu không thể giữ creation time nhưng ứng dụng bắt buộc cần nó, lưu **metadata nghiệp vụ riêng** có nguồn tin cậy, thay vì bịa một timestamp “tạo gốc” từ filesystem.

### 11.4. `setTimes` có atomic không?

Không có bảo đảm portable rằng cập nhật nhiều timestamp bằng `setTimes` là một thao tác nguyên tử. Provider có thể thực hiện đọc/sửa/ghi một hoặc nhiều thuộc tính. Cũng không có bảo đảm rằng một thao tác ghi file thực tế cùng với `setTimes` là **một transaction**.

Không dùng ba timestamp như trạng thái commit duy nhất nếu các thao tác khác cần nhìn thấy chúng đồng bộ cùng nội dung.

## 12. Chương trình 4: sửa mtime, dùng `BasicFileAttributeView` và thử atime

Lưu thành `FileTimeUpdateDemo.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
import java.time.Instant;

public class FileTimeUpdateDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("file-time-update-");
        Path file = dir.resolve("sample.bin");
        try {
            Files.write(file, new byte[] {10});
            FileTime modified = FileTime.from(Instant.parse("2020-01-02T03:04:05Z"));
            Files.setLastModifiedTime(file, modified);
            FileTime readBack = Files.getLastModifiedTime(file);
            System.out.println("modifiedRequested=" + modified.toInstant());
            System.out.println("modifiedReadBack=" + readBack.toInstant());
            System.out.println("modifiedMatches=" + readBack.equals(modified));

            BasicFileAttributeView view =
                    Files.getFileAttributeView(file, BasicFileAttributeView.class);
            FileTime older = FileTime.from(Instant.parse("2019-05-06T07:08:09Z"));
            view.setTimes(older, null, null);
            BasicFileAttributes attrs = view.readAttributes();
            System.out.println("viewModified=" + attrs.lastModifiedTime().toInstant());
            System.out.println("viewMatches=" + attrs.lastModifiedTime().equals(older));

            try {
                FileTime accessed = FileTime.from(Instant.parse("2018-07-08T09:10:11Z"));
                view.setTimes(null, accessed, null);
                FileTime actual = view.readAttributes().lastAccessTime();
                System.out.println("accessUpdate=" +
                        (actual.equals(accessed) ? "EXACT" : "ROUNDED_OR_DIFFERENT"));
            } catch (IOException | UnsupportedOperationException exception) {
                System.out.println("accessUpdate=UNAVAILABLE");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileTimeUpdateDemo.java
java FileTimeUpdateDemo
```

Stdout **đã kiểm chứng trên file store của môi trường thử nghiệm**:

```text
modifiedRequested=2020-01-02T03:04:05Z
modifiedReadBack=2020-01-02T03:04:05Z
modifiedMatches=true
viewModified=2019-05-06T07:08:09Z
viewMatches=true
accessUpdate=EXACT
```

### 12.1. Vì sao test cố ý dùng thời điểm cũ?

Dùng một timestamp cố định tách biệt với **thời điểm hiện tại** giúp quan sát setter đã hoạt động, không phụ thuộc ngày giờ lúc test chạy. Nó cũng giúp tránh sai khi gọi `FileTime.fromMillis(System.currentTimeMillis())` rồi kết quả đọc lại có chênh lệch ít millisecond do tiến trình chạy.

### 12.2. Có phải mọi filesystem đều cho output như trên?

**Không.** Những giá trị `modifiedReadBack` và `viewModified` phản ánh file store của máy đã thử. Provider khác có thể:
- Giữ timestamp với precision thô hơn.
- Làm tròn số fractional second.
- Không cho cập nhật atime/creation time.
- Từ chối sửa do quyền truy cập hoặc giới hạn metadata.
- Trả một giá trị đại diện khác nếu thuộc tính không được hỗ trợ.

Đó là lý do `accessUpdate` trong code có **ba trạng thái**: `EXACT`, `ROUNDED_OR_DIFFERENT` hoặc `UNAVAILABLE`. Nếu trả `ROUNDED_OR_DIFFERENT`, cần phân tích tiếp xem đó là precision loss, giới hạn provider hay thao tác khác đã đổi timestamp; **không tự khẳng định cập nhật thành công đúng nghĩa nghiệp vụ**.

### 12.3. Tại sao không có bước sửa creationTime trong demo?

Vì mục tiêu là ví dụ **có thể chạy trên nhiều hệ thống** và thuộc tính creation time có thể không hỗ trợ set. Việc “cố sửa ngày tạo” có thể thành công, bị bỏ qua hoặc lỗi tùy provider, nên không đưa nó vào expected stdout chuẩn cho mọi máy. Phần 11 đã chỉ cách gọi `setTimes(null,null,newCreated)` theo API và nêu điều kiện hỗ trợ; khi cần nghiệp vụ thật, hãy kiểm thử trên filesystem được triển khai.

### 12.4. Cẩn trọng khi viết lại file sau khi set mtime

Một lần `Files.write(...)` hoặc `Files.writeString(...)` thực hiện **sau** `Files.setLastModifiedTime(...)` có thể làm mtime đổi thêm lần nữa. Nếu muốn preserve một mtime từ nguồn sau khi chuyển nội dung, hãy hoàn tất ghi nội dung trước, rồi set mtime sau, và vẫn xử lý thay đổi đồng thời theo chính sách.

## 13. Đọc/ghi timestamps với symbolic link

Một `Path` có thể là **symbolic link**, không phải file thông thường. Cần phân biệt:

- **Thời gian của file đích** mà symlink trỏ tới.
- **Thời gian metadata của chính symbolic link**.

Theo mặc định, các phương thức `Files.readAttributes`/`Files.getLastModifiedTime` thường **theo symbolic link** khi provider hỗ trợ. Để lấy thuộc tính **của link**, truyền `LinkOption.NOFOLLOW_LINKS`:

```java
BasicFileAttributes attrsOfLink = Files.readAttributes(
        symlink,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS
);
FileTime mtimeOfLink = Files.getLastModifiedTime(
        symlink,
        LinkOption.NOFOLLOW_LINKS
);
```

Đây là snippet có `Path symlink` đã có và cần xử lý IOException.

**Không nhầm hai câu hỏi:** nếu muốn biết mtime của **file mà người dùng thực sự sẽ đọc khi đi theo link**, đọc attributes theo link có thể là đúng. Nếu muốn kiểm tra **entry symbolic link**, NOFOLLOW_LINKS phù hợp. Đây là quyết định rõ ràng về semantics, không phải “flag lúc nào cũng phải bật”.

### 13.1. Cập nhật timestamp của link có khác không?

`Files.setLastModifiedTime(path,time)` không có overload nhận `LinkOption...`, nên đừng mặc nhiên xem nó là cách cập nhật **chính symlink** mà không đi theo link.

Nếu provider hỗ trợ attribute view trên link, bạn có thể lấy view có `NOFOLLOW_LINKS`:

```java
BasicFileAttributeView linkView =
        Files.getFileAttributeView(
            symlink,
            BasicFileAttributeView.class,
            LinkOption.NOFOLLOW_LINKS
        );
```

Đây là snippet. Sau đó các thao tác `linkView.readAttributes()` và `linkView.setTimes(...)` sẽ áp dụng theo semantics của view và provider. **Không có bảo đảm mọi filesystem cho phép đặt timestamp của symbolic link**; các quyền và đặc tính hệ thống phải được kiểm thử.

### 13.2. Không dùng metadata precheck như bảo đảm chống race

Giả sử bạn kiểm tra `Files.isSymbolicLink(path)==false` rồi mới sửa mtime. Một tác nhân khác có quyền đổi directory entry có thể thay đường dẫn giữa check và use. Đây là **time-of-check to time-of-use** (TOCTOU). Nếu security boundary quan trọng, cần kiểm soát quyền thư mục, mô hình symlink và thao tác mở/truy cập dựa trên handle hoặc API phù hợp, không chỉ một lần `NOFOLLOW_LINKS`.

## 14. Chương trình 5: phân biệt mốc thời gian của symlink và đích

Lưu thành `FileTimeSymlinkDemo.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;

public class FileTimeSymlinkDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("file-time-link-");
        Path target = dir.resolve("target.bin");
        Path link = dir.resolve("shortcut");
        try {
            Files.write(target, new byte[] {1});
            try {
                Files.createSymbolicLink(link, target.getFileName());
            } catch (IOException | UnsupportedOperationException | SecurityException exception) {
                System.out.println("symlink=SKIPPED");
                return;
            }
            BasicFileAttributes followed =
                    Files.readAttributes(link, BasicFileAttributes.class);
            BasicFileAttributes own =
                    Files.readAttributes(link, BasicFileAttributes.class,
                            LinkOption.NOFOLLOW_LINKS);
            System.out.println("followRegular=" + followed.isRegularFile());
            System.out.println("noFollowIsLink=" + own.isSymbolicLink());
            System.out.println("noFollowModifiedAvailable=" +
                    (Files.getLastModifiedTime(link, LinkOption.NOFOLLOW_LINKS) != null));
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileTimeSymlinkDemo.java
java FileTimeSymlinkDemo
```

**Nếu tạo symlink được hỗ trợ và cho phép**, chương trình dự kiến in:

```text
followRegular=true
noFollowIsLink=true
noFollowModifiedAvailable=true
```

**Kết quả thật trên môi trường kiểm thử không có quyền tạo symbolic link:**

```text
symlink=SKIPPED
```

Không tuyên bố nhánh symlink đã được kiểm chứng thực nghiệm chỉ vì class biên dịch và thoát thành công ở nhánh SKIPPED. Nếu chức năng production dựa vào hành vi symbolic link, cần chạy integration test trên OS/provider có capability và quyền cần thiết.

### 14.1. Tại sao không so sánh hai mốc time bằng cách phải khác nhau?

Thời gian của link và thời gian của file đích **có thể vô tình bằng nhau**, ví dụ do chúng được tạo gần cùng lúc hoặc filesystem làm tròn timestamp. Sự khác biệt chính xác cần quan sát ở đây là **loại đối tượng được đọc** (`regular file` hay `symbolic link`), không phải bắt buộc giá trị millisecond phải khác.

## 15. Sao chép file có giữ nguyên timestamps không?

`Files.copy(source,target)` về nguyên tắc tạo target với metadata theo chính sách mặc định của provider, **không mặc nhiên sao chép mọi timestamp/ACL**.

Nếu mục tiêu là sao chép thuộc tính theo khả năng hỗ trợ, có option:

```java
Files.copy(source, target, StandardCopyOption.COPY_ATTRIBUTES);
```

Đây là snippet. Javadoc cho biết `COPY_ATTRIBUTES` yêu cầu copy metadata; những thuộc tính nào được bảo toàn và precision ra sao vẫn phụ thuộc file stores/providers, đặc biệt giữa các kiểu filesystem khác nhau.

**Đừng khẳng định:** “COPY_ATTRIBUTES luôn giữ cả creationTime, lastAccessTime, lastModifiedTime, quyền POSIX, owner và ACL y hệt”. Những metadata nào có thể copy cần kiểm tra từng môi trường. Với đồng bộ dữ liệu, thường nên thiết kế tính đúng đắn dựa trên **nội dung và quy tắc version** thay vì chỉ dựa vào timestamps.

### 15.1. Chương trình 6: copy có `COPY_ATTRIBUTES`

Lưu thành `FileTimeCopyDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.FileTime;
import java.time.Instant;

public class FileTimeCopyDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("file-time-copy-");
        Path source = dir.resolve("source.txt");
        Path target = dir.resolve("target.txt");
        try {
            Files.writeString(source, "COPY", StandardCharsets.UTF_8);
            FileTime requested = FileTime.from(Instant.parse("2021-02-03T04:05:06Z"));
            Files.setLastModifiedTime(source, requested);
            Files.copy(source, target, StandardCopyOption.COPY_ATTRIBUTES);

            System.out.println("dataMatches=" +
                    Files.readString(source, StandardCharsets.UTF_8)
                            .equals(Files.readString(target, StandardCharsets.UTF_8)));
            System.out.println("copyModifiedMatches=" +
                    Files.getLastModifiedTime(source)
                            .equals(Files.getLastModifiedTime(target)));
            System.out.println("sourceStillExists=" + Files.exists(source));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileTimeCopyDemo.java
java FileTimeCopyDemo
```

Stdout đã xác minh **trên provider mặc định của máy kiểm thử**:

```text
dataMatches=true
copyModifiedMatches=true
sourceStillExists=true
```

**Đọc output đúng mức:** có `COPY_ATTRIBUTES` và local file store đã giữ lastModified chính xác trong test. Kết quả này **không chứng minh** các file stores/provider khác giữ được tất cả metadata, và cũng không chứng minh creation/access time luôn được sao chép y hệt.

`sourceStillExists=true` là đúng vì `Files.copy` tạo bản sao, không di chuyển/xóa source. Nếu muốn chuyển file, dùng `Files.move` với policy riêng; việc một move giữ metadata nào và có nguyên tử hay không là vấn đề khác.

### 15.2. “Giữ mtime” trong backup có đủ không?

Không. Một bản backup muốn có tính khôi phục cần kiểm tra file content, versioning, quyền, metadata quan trọng, trạng thái partial failure và khả năng file đã thay đổi trong lúc copy. Chỉ thấy hai mtime giống nhau không chứng minh nội dung giống nhau; demo có kiểm tra String để minh họa hai yếu tố **khác nhau**.

## 16. Khi tệp không tồn tại hoặc không có quyền đọc metadata

API đọc/ghi timestamp làm việc với **filesystem thật** nên có thể phát sinh lỗi:

- `NoSuchFileException`: đường dẫn không tìm thấy tại thời điểm gọi, nếu provider sử dụng subclass này.
- `AccessDeniedException`: không đủ quyền theo provider/OS.
- `IOException` khác: network I/O, file store lỗi, trạng thái không đọc được.
- `UnsupportedOperationException` ở một số API/provider hoặc cấu hình capability.
- `IllegalArgumentException`/`NullPointerException` khi caller truyền tham số không hợp lệ theo hợp đồng.

**Đừng biến tất cả thành epoch.** Nếu một call thật sự thất bại và bạn tự trả `FileTime.fromMillis(0)`, caller có thể hiểu nhầm đó là metadata gốc của file. Giá trị fallback do provider trả ra qua `BasicFileAttributes` là một khái niệm khác với việc ứng dụng **tự nuốt lỗi** và bịa timestamp.

### 16.1. Chương trình 7: xử lý file không tồn tại

Lưu thành `FileTimeMissingDemo.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;

public class FileTimeMissingDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("file-time-missing-");
        Path missing = dir.resolve("not-here.txt");
        try {
            try {
                Files.readAttributes(missing, BasicFileAttributes.class);
                throw new AssertionError("read must fail");
            } catch (NoSuchFileException expected) {
                System.out.println("readMissing=NoSuchFileException");
            }
            try {
                Files.getLastModifiedTime(missing);
                throw new AssertionError("get must fail");
            } catch (NoSuchFileException expected) {
                System.out.println("getMissing=NoSuchFileException");
            }
            try {
                Files.setLastModifiedTime(missing, FileTime.fromMillis(0));
                throw new AssertionError("set must fail");
            } catch (NoSuchFileException expected) {
                System.out.println("setMissing=NoSuchFileException");
            }
        } finally {
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FileTimeMissingDemo.java
java FileTimeMissingDemo
```

Stdout đã kiểm chứng trên provider mặc định:

```text
readMissing=NoSuchFileException
getMissing=NoSuchFileException
setMissing=NoSuchFileException
```

**Hàm ý:** cả ba API đều thật sự tra filesystem và ném lỗi khi file không có. `NoSuchFileException` là kết quả kiểm chứng trên provider này; code đa provider vẫn nên có lối xử lý IOException thích hợp.

### 16.2. Tại sao không làm `Files.exists` trước?

Mẫu:

```java
if (Files.exists(path)) {
    FileTime mtime = Files.getLastModifiedTime(path);
}
```

Đây là **snippet**, không bảo đảm `getLastModifiedTime` thành công, vì file có thể biến mất **sau khi** `exists` trả true. Mỗi thao tác I/O phải xử lý lỗi của chính nó. `Files.exists` còn có thể trả false khi không đủ thông tin để xác nhận sự tồn tại, không nhất thiết chứng minh đối tượng chắc chắn không có.

Đối với quy trình xử lý dữ liệu, hãy quyết định rõ:
- File không có → bỏ qua, báo lỗi, hay tạo mới?
- Không đủ quyền → báo lỗi riêng hay yêu cầu quản trị?
- File store không hỗ trợ thuộc tính → fallback nghiệp vụ nào (nếu có)?
- Metadata thay đổi trong lúc đọc → cần xác minh lại hay chấp nhận?

## 17. `lastAccessTime` và atime không phải nhật ký truy cập

Một hiểu nhầm dễ gặp là “mỗi khi tôi gọi `Files.readString`, `lastAccessTime` phải đổi sang `Instant.now()`”. Thực tế không có cam kết như vậy.

Các filesystem/mount/configuration có thể:
- Không hỗ trợ last-access timestamp.
- Tắt cập nhật access time để giảm I/O.
- Cập nhật có điều kiện hoặc trễ (ví dụ mô hình tương tự `relatime`).
- Bị ảnh hưởng bởi caching, đồng bộ metadata hoặc các thao tác mở file khác.
- Có độ phân giải timestamp không đủ để phân biệt hai lần đọc liên tiếp.
- Trả fallback value như `lastModifiedTime` khi không lưu atime thực.

### 17.1. Dùng atime để biết “ai đã đọc file” có đúng không?

Không. `lastAccessTime` chỉ là metadata về **một mốc thời gian** khi provider có hỗ trợ; nó **không lưu danh tính**, số lần truy cập hay nội dung truy cập. Kể cả khi timestamp được cập nhật, bạn không thể suy ra **người dùng nào** đọc file chỉ từ atime.

Nếu cần audit truy cập, hãy dùng audit log/event system có xác thực và chính sách lưu trữ phù hợp. Đừng dùng atime như bằng chứng pháp lý hoặc security log duy nhất.

### 17.2. Vì sao không nên test `lastAccessTime` phải tăng sau một lần read?

Vì test như vậy có thể thất bại hoàn toàn đúng trên hệ thống không cập nhật atime mỗi lần đọc. Bộ test nên tập trung vào:
- API trả/đọc `FileTime` được hay không.
- Khi thử set atime, provider có trả sai số/lỗi/capability phù hợp không.
- Hệ thống nghiệp vụ có xử lý việc atime thiếu/không đáng tin không.

Nếu sản phẩm **bắt buộc** kiểm soát last access, hãy lưu sự kiện truy cập tại **tầng ứng dụng** thay vì dựa vào một tùy chọn filesystem.

## 18. `creationTime` không phải một mã định danh bất biến của file

Một số người muốn dùng bộ ba `(path, creationTime, size)` để xác minh “đây đúng là cùng một file”. Cách đó có thể sai vì:

- Path có thể bị đổi tên hoặc thay thế bằng entry khác.
- Creation time không được hỗ trợ và provider trả fallback.
- Timestamp có thể bị sao chép/đặt lại.
- Một file mới có thể trùng kích thước và timestamp với file cũ.
- Đồng bộ tệp có thể tạo file mới rồi giữ lại mtime từ nguồn.
- Hệ thống có nhiều file stores dùng các quy tắc thời gian khác nhau.

Nếu cần đối chiếu danh tính đối tượng filesystem trong phạm vi phù hợp, xem `BasicFileAttributes.fileKey()`, nhưng key đó cũng **có thể null**, semantics phụ thuộc provider và không phải ID nghiệp vụ portable qua tất cả lần copy/rename. Nếu cần kiểm tra nội dung, dùng hash có điều kiện và mô hình quyền/khóa phù hợp.

Đừng dùng `creationTime()==lastModifiedTime()` để kết luận file chưa từng được sửa. Provider có thể làm tròn thời gian hoặc dùng lastModified làm fallback cho creation time.

## 19. Dữ liệu thời gian khi tạo, sửa, sao chép, đổi tên và xóa

Các operation filesystem có thể ảnh hưởng timestamp, nhưng mức độ và thời điểm cập nhật phụ thuộc provider:

| Operation | Điều có thể xảy ra | Điều không được tự khẳng định |
| --- | --- | --- |
| Tạo file mới | Provider thiết lập creation/modified/access phù hợp | Cả ba giá trị đều độc lập và chính xác nanosecond |
| Ghi nội dung | Thường làm lastModified thay đổi | Mỗi byte ghi đều tạo mtime riêng biệt được đọc thấy |
| Đọc nội dung | Có thể cập nhật lastAccess theo cấu hình | Mỗi lần đọc đều cập nhật atime |
| `Files.setLastModifiedTime` | Yêu cầu cập nhật mtime | Provider giữ đúng từng nano-second |
| `view.setTimes` | Yêu cầu sửa một/vài timestamp | Cập nhật nhiều timestamp như một transaction |
| `Files.copy(..., COPY_ATTRIBUTES)` | Cố sao chép các thuộc tính theo provider | Giữ toàn bộ creation/access/mtime/ACL giống hệt trên mọi hệ thống |
| Đổi tên/di chuyển | Metadata có thể được giữ hoặc thay đổi tùy thao tác | “creationTime luôn giữ nguyên tuyệt đối” trên mọi provider |
| Xóa rồi tạo lại cùng tên | Một object mới tại cùng Path | File đó vẫn có identity và timestamp giống file cũ |

### 19.1. Vì sao phải tách timestamp của **nội dung** với timestamp của **directory entry**?

Khi tạo hoặc xóa một file trong thư mục, filesystem có thể cập nhật metadata của **thư mục cha** vì danh sách entry trong thư mục đã thay đổi. Điều đó không nhất thiết đồng nghĩa nội dung của một file con khác đã đổi. Vì thế khi xây bộ theo dõi thay đổi, phải hiểu đang quan sát **mtime của tệp**, **mtime của thư mục**, hay cả hai.

### 19.2. Filesystem thời gian không phải đồng hồ nghiệp vụ

Clock hệ điều hành có thể được điều chỉnh; file store có thể ghi thời gian ở precision khác; ứng dụng có thể khôi phục metadata. Nếu ứng dụng cần sự kiện “người dùng tải tài liệu lên lúc T”, hãy ghi **server-side event timestamp** trong database/audit log theo hợp đồng, không dùng creation time của filesystem làm nguồn duy nhất.

## 20. Lọc file theo thời điểm: `FileTime.compareTo` và `Instant`

Giả sử ứng dụng duyệt danh sách file và muốn chọn file có thời gian sửa đổi sau một mốc quy định:

```java
FileTime threshold = FileTime.from(
        Instant.parse("2024-01-01T00:00:00Z"));

FileTime actual = Files.getLastModifiedTime(path);
if (actual.compareTo(threshold) > 0) {
    // File có reported mtime sau threshold.
}
```

Đây là snippet với `Path path` đã có; method xử lý `IOException`. Ngữ nghĩa `> 0` là **sau mốc**, khác `>= 0` cho phép bằng nhau. Chú ý precision và timestamp do provider báo.

### 20.1. Lọc theo “24 giờ gần nhất” cần tránh timezone nhầm

Một ranh giới hợp lý cho “trong 24 giờ vừa qua” theo **khoảng thời gian trôi qua** là:

```java
Instant threshold = Instant.now().minus(
        java.time.Duration.ofHours(24));
boolean recent =
        Files.getLastModifiedTime(path).toInstant().isAfter(threshold);
```

Đây là snippet Java 8+; `path` đã khai báo và method xử lý IOException.

Nhưng “hôm nay theo giờ Việt Nam” là một **khoảng ngày lịch theo một timezone**, không nhất thiết giống “24 giờ vừa qua”. Khi xử lý lịch theo ngày, hãy dùng `ZoneId`, mốc đầu ngày/đầu ngày tiếp theo theo zone của người dùng; không tự trừ 24h rồi giả định đó luôn là toàn bộ một ngày địa phương ở mọi timezone/DST.

### 20.2. Dùng lastModified cho incremental backup có đủ không?

mtime giúp tìm **ứng viên có thể thay đổi**, nhưng không bảo đảm phát hiện mọi sửa đổi. Một tệp có thể đổi nội dung nhưng mtime bị giữ lại hoặc nằm trong cùng độ phân giải của filesystem. Với yêu cầu đúng tuyệt đối, dùng thêm metadata versioning, checksums, manifests hoặc cơ chế change journal/provider phù hợp.

### 20.3. Kiểm tra hash và metadata trước/sau đọc

Nếu file có thể thay trong lúc hash hoặc copy, việc đọc `lastModifiedTime` trước và sau có thể là một lớp phát hiện, nhưng **không chứng minh tuyệt đối file không hề thay** (có thể bị thay rồi đặt lại mtime, precision không đủ, thay đổi đồng thời). Khi cần snapshot nhất quán, dùng cơ chế filesystem snapshot/locking hoặc storage version model phù hợp.

## 21. Múi giờ, DST và hiển thị `FileTime` trong giao diện

`FileTime` là mốc thời gian, không phải **giờ được tạo ở địa phương nào**. Khi hiển thị:

- Dùng `toInstant()` để có một thời điểm UTC.
- Dùng `atZone(ZoneId.of("..."))` để biểu diễn theo vùng địa lý.
- Dùng `DateTimeFormatter` theo locale/zone của người dùng khi cần UI.
- Không tự format thời gian bằng cách sửa `toMillis()` cộng hoặc trừ offset thủ công.
- Không giả định timezone luôn có cùng offset suốt lịch sử; các zone có quy tắc chuyển đổi qua thời gian.

Một snippet format tùy chỉnh:

```java
java.time.format.DateTimeFormatter fmt =
        java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss XXX")
                .withZone(java.time.ZoneId.of("Asia/Ho_Chi_Minh"));

String displayed = fmt.format(fileTime.toInstant());
```

Đây là snippet Java 8+ với `FileTime fileTime` đã có. `Instant` giữ nguyên mốc, còn `String displayed` là cách hiển thị. Nếu mục tiêu là lưu dữ liệu trao đổi, ưu tiên biểu diễn rõ UTC/ISO-8601 hoặc epoch có đơn vị, thay vì chuỗi local không có zone.

### 21.1. Chuỗi `FileTime.toString()` có phù hợp lưu làm khóa không?

`FileTime.toString()` cung cấp biểu diễn text của thời điểm nhưng không nên tự coi đó là **khóa nghiệp vụ ổn định** hay bằng chứng duy nhất để nhận diện một đối tượng. Nếu cần dữ liệu có thể trao đổi giữa các hệ thống, dùng schema rõ: milliseconds/seconds UTC, ISO instant, định nghĩa precision và nullable/unsupported policy.

### 21.2. Không nhầm ngày tạo của file với ngày tạo nội dung

Một file được tải từ nơi khác về có thể là **file mới trên máy đích** nhưng nội dung có nguồn gốc lâu trước đó. Creation time của file tại nơi đích và ngày tài liệu được biên soạn là **hai dữ kiện khác nhau**. Ứng dụng quản lý tài liệu nên có metadata nghiệp vụ riêng khi cần nguồn gốc thông tin.

## 22. Những lỗi phổ biến và cách khắc phục

| Lỗi hoặc giả định sai | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Coi `FileTime` là “giờ địa phương” | FileTime đại diện một mốc thời gian | Dùng `Instant`/`ZoneId` để hiển thị |
| Coi `FileTime.fromMillis(x)` nghĩa là x giây | Hàm nhận milliseconds | Đặt đúng đơn vị hoặc `from(x,SECONDS)` |
| Dùng `toMillis` rồi tin giữ nguyên nano-second | Conversion có thể mất phần lẻ | Giữ `FileTime`/`Instant` ở precision cần thiết |
| So sánh `toString` thay vì thời điểm | Chỉ là biểu diễn text | `compareTo`/`equals` |
| Nghĩ `creationTime()` chắc chắn là birth time thực | Provider có thể trả fallback | Kiểm tra khả năng/đặc tính filesystem |
| Nghĩ atime luôn đổi khi đọc | Filesystem có thể tắt/hoãn cập nhật | Không làm audit dựa trên atime |
| Nghĩ `lastModifiedTime` không thể bị chỉnh | `setLastModifiedTime` có thể đổi nó | Đừng coi mtime là chứng thực bất biến |
| Nghĩ `BasicFileAttributes` là snapshot toàn cây | Chỉ một lần đọc metadata có giới hạn | Xử lý concurrency/snapshot riêng |
| Gọi `Files.getCreationTime` | Không có method tiện ích cùng tên | `readAttributes` hoặc `getAttribute` |
| Dùng `BasicFileAttributeView.setTimes` sai thứ tự | Thứ tự là modified/access/creation | Dùng tên biến rõ ràng |
| Nghĩ `null` trong `setTimes` xóa timestamp | `null` yêu cầu không đổi timestamp đó | Dùng null để bỏ qua trường không định set |
| Cho rằng `setTimes` atomic | Implementation có thể read/modify/write | Không dùng làm transaction |
| Nghĩ set creation luôn được hỗ trợ | Provider có thể bỏ qua hoặc báo lỗi | Kiểm tra capability/readback |
| Nghĩ setter giữ nano-second chính xác | File store có độ phân giải riêng | Chấp nhận chính sách precision |
| Set mtime rồi ghi lại file và mong mtime giữ nguyên | Ghi file có thể cập nhật mtime | Hoàn tất ghi trước, set sau |
| Đọc metadata của symlink mà quên follow policy | Có thể đọc target thay vì link | `NOFOLLOW_LINKS` nếu cần metadata link |
| Tin `isSymbolicLink` rồi open không còn race | Directory entry có thể thay | Mô hình quyền/TOCTOU phù hợp |
| Coi `COPY_ATTRIBUTES` giữ mọi thuộc tính giống nhau | Phụ thuộc file stores | Test theo provider và metadata cần thiết |
| Bắt IOException rồi tự trả epoch 0 | Che lỗi không tìm thấy/quyền | Phân biệt lỗi với unsupported/default |
| Tin `Files.exists` đảm bảo lần get sau thành công | Có race check-then-use | Xử lý IOException tại operation |
| Dùng mtime làm định danh tài liệu | Nhiều file trùng/được reset mtime | ID/version/hash phù hợp |
| Dùng atime để suy ra ai đã đọc file | Atime không lưu identity | Audit log ở tầng ứng dụng |
| Coi Unix ctime bằng Java creationTime | POSIX ctime thường là status change | Dùng đúng khái niệm per provider |
| Dùng `Path.of` rồi biên dịch source target Java 7 | API này từ Java 11 | Java 7 dùng `Paths.get` |
| Nghĩ mọi chương trình phải in cùng timestamp thực | Tạo file xảy ra ở thời điểm khác | Test theo invariant/readback thay vì giờ thực |

## 23. Checklist trước khi dùng timestamp filesystem trong ứng dụng

1. Bạn đang cần **creation**, **modified** hay **access**? Có định nghĩa chính xác từ nghiệp vụ chưa?
2. Hệ thống triển khai dùng file store/provider nào? Có hỗ trợ thuộc tính đó thật không?
3. Nếu creation/access không hỗ trợ, có policy hợp lý cho fallback/unknown chưa?
4. Timestamp cần precision bao nhiêu: giây, millis, micros hay nanos?
5. Dữ liệu cần lưu là `FileTime`, `Instant` hay chuỗi hiển thị theo múi giờ?
6. Bạn có đang vô tình so sánh local date-time với UTC epoch không?
7. Nếu đọc ba trường, có dùng `BasicFileAttributes` thay vì gọi lặp nhiều lần không?
8. Nếu sửa mtime, có dùng `setLastModifiedTime` và **đọc lại** để xác minh khi cần không?
9. Nếu gọi `setTimes`, thứ tự modified/access/creation đã đúng chưa?
10. Có dựa vào `setTimes` như một thao tác atomic không? Nếu có thì thiết kế cần đổi.
11. Nếu path có symlink, bạn muốn đọc timestamp của link hay target?
12. Nếu tệp có thể bị xóa/đổi trong lúc làm, có xử lý IOException và race không?
13. Nếu đang copy file, việc giữ metadata có yêu cầu `COPY_ATTRIBUTES` và provider hỗ trợ không?
14. Nếu file mới trên host đích, có cần giữ creation time từ nguồn hay lưu metadata nguồn riêng?
15. Có đang dùng atime làm hệ thống audit? Nếu có, hãy dùng log ứng dụng thay thế.
16. Có đang dùng mtime làm cơ chế xác nhận nội dung không? Cần hash/version thêm ở mức yêu cầu.
17. Các test có tách thời gian **cố định** với file creation time thực đang thay đổi không?
18. Các test symlink có kiểm tra capability hay báo `SKIPPED` đúng nghĩa không?
19. Có phân biệt API có từ Java 7 với `Instant` (Java 8) và `Path.of` (Java 11) không?
20. Dữ liệu/error response có vô tình tiết lộ full server path, timezone hay metadata nhạy cảm không?

## 24. Bài tập thực hành có đáp án

**Câu 1.** Muốn lấy ba timestamp trong một lần đọc theo kiểu Java, dùng API nào?  
**Đáp án:** `Files.readAttributes(path, BasicFileAttributes.class)`; sau đó gọi `creationTime()`, `lastModifiedTime()`, `lastAccessTime()`.

**Câu 2.** Có thể lấy last-modified mà không đọc BasicFileAttributes không?  
**Đáp án:** Có, dùng `Files.getLastModifiedTime(path)`.

**Câu 3.** `FileTime.fromMillis(1000)` là mốc nào?  
**Đáp án:** Một giây sau epoch, tức `1970-01-01T00:00:01Z`.

**Câu 4.** `FileTime.from(1000, TimeUnit.SECONDS)` có bằng trường hợp trên không?  
**Đáp án:** Không. Nó là 1000 giây sau epoch, không phải 1000 milliseconds.

**Câu 5.** Làm sao hiển thị timestamp theo múi giờ Việt Nam mà không đổi thời điểm gốc?  
**Đáp án:** Dùng `fileTime.toInstant().atZone(ZoneId.of("Asia/Ho_Chi_Minh"))`.

**Câu 6.** Một `FileTime` có 1.234567890 giây từ epoch; `toMillis()` rồi `fromMillis(...)` có giữ nano-second không?  
**Đáp án:** Không. Nó chỉ giữ 1234 millisecond, phần lẻ nano-giây bị mất.

**Câu 7.** Nếu `attrs.creationTime()` không null, có chắc filesystem hỗ trợ thời gian tạo thực không?  
**Đáp án:** Không. Javadoc cho phép dùng fallback timestamp khi creation time không được hỗ trợ.

**Câu 8.** Nếu vừa đọc file nhưng `lastAccessTime()` không thay đổi, Java có chắc lỗi không?  
**Đáp án:** Không. Chính sách atime do OS/provider quyết định, có thể không cập nhật trên mỗi lần đọc.

**Câu 9.** `view.setTimes(null, newTime, null)` cập nhật trường nào?  
**Đáp án:** `lastAccessTime`, vì tham số thứ hai là access time.

**Câu 10.** `view.setTimes(newTime,null,null)` có đảm bảo không ảnh hưởng precision của các trường khác trên mọi provider không?  
**Đáp án:** Không tuyệt đối. Implementation có thể phải read/rewrite các trường hiện tại; một số trường có thể mất precision theo Javadoc.

**Câu 11.** Muốn set creationTime bằng API chuẩn, có method `Files.setCreationTime` không?  
**Đáp án:** Không. Có thể thử `BasicFileAttributeView.setTimes(null,null,newCreated)` hoặc dynamic `setAttribute`, nhưng mức hỗ trợ là provider-specific.

**Câu 12.** `Files.readAttributes(link, BasicFileAttributes.class)` và có `NOFOLLOW_LINKS` khác gì nhau?  
**Đáp án:** Trường hợp mặc định thường lấy metadata đích theo symlink; `NOFOLLOW_LINKS` yêu cầu metadata của chính link.

**Câu 13.** `Files.copy(source,target,COPY_ATTRIBUTES)` có buộc mọi timestamp giống nhau ở mọi filesystem không?  
**Đáp án:** Không. Khả năng bảo toàn thuộc tính và precision phụ thuộc provider/file stores.

**Câu 14.** Nên so sánh hai mốc FileTime bằng String hay `compareTo`?  
**Đáp án:** `compareTo` để so thời điểm; String chỉ nên phục vụ hiển thị.

**Câu 15.** Nếu file không tồn tại, có nên trả `FileTime.fromMillis(0)` như một timestamp “mặc định” không?  
**Đáp án:** Không. Hãy xử lý `IOException`/`NoSuchFileException` rõ ràng để không nhầm lỗi truy cập với một timestamp có nghĩa.

**Câu 16.** Có thể xác định chính xác ai đã đọc file từ `lastAccessTime` không?  
**Đáp án:** Không. Nó không chứa danh tính hay lịch sử thao tác; cần audit log ứng dụng.

**Câu 17.** Sao chép file rồi sửa mtime đích có tự làm nội dung file giống nhau không?  
**Đáp án:** Không. Timestamp và nội dung là hai yếu tố độc lập; cần kiểm tra nội dung bằng hash, kích thước, version hay chính sách khác.

**Câu 18.** Tại sao output thời điểm tạo file tạm không nên hard-code trong test Java?  
**Đáp án:** Vì file được tạo tại thời điểm thực tế khác mỗi lần chạy; hãy test invariant, thử timestamp cố định bằng setter hoặc in loại dữ liệu thay vì phụ thuộc clock.

### Thực hành A — Ba timestamps

Chạy `FileTimesReadDemo`; bổ sung lệnh in `attrs.creationTime().toInstant()`, `attrs.lastModifiedTime().toInstant()` và `attrs.lastAccessTime().toInstant()`. Ghi chú vì sao ba giá trị có thể bằng nhau và vì sao output thực thay đổi qua các lần chạy.

### Thực hành B — FileTime ở giây và milli-giây

Sửa `FileTimeValuesDemo` để tạo cùng một thời điểm bằng `fromMillis` và `from(..., TimeUnit.SECONDS)` khi timestamp không có phần lẻ. Kiểm tra `equals` và `compareTo`.

### Thực hành C — Precision

Chạy `FileTimePrecisionDemo` và đổi `1_234_567_890L` thành một thời điểm có đúng mili-giây (bội số 1.000.000 nano-giây). Quan sát tại sao `millisEqual` có thể đổi thành true.

### Thực hành D — Setter mtime

Chạy `FileTimeUpdateDemo`, thay thời điểm yêu cầu thành một ngày khác trong năm 2022. Đọc lại trên file store hiện tại, ghi rõ mức precision quan sát được. Không lấy một kết quả exact làm bảo đảm cho filesystem khác.

### Thực hành E — Thử creationTime

Trong một thư mục tạm do mình sở hữu, thử `view.setTimes(null,null,newCreated)` trong `try/catch` thích hợp. Đọc lại attributes. Phân loại thành accepted-exact, rounded/changed, unsupported hoặc error; không giả định mọi OS đều cho sửa birth time.

### Thực hành F — Link và target

Chạy `FileTimeSymlinkDemo` trên môi trường có quyền tạo symlink. Nếu ra `symlink=SKIPPED`, thực hiện test trong CI/provider hỗ trợ rồi ghi nhận `isSymbolicLink` khi NOFOLLOW và `isRegularFile` khi follow.

### Thực hành G — COPY_ATTRIBUTES

Chạy `FileTimeCopyDemo`, sau đó bỏ `COPY_ATTRIBUTES` và đối chiếu lastModified của target. Tách biệt quan sát local file store với yêu cầu portable của ứng dụng.

### Thực hành H — Không có file

Chạy `FileTimeMissingDemo`, thay policy bắt `NoSuchFileException` thành một method trả kết quả `Optional<FileTime>` khi business thực sự cho phép “file không có”. Các IOException khác vẫn phải được báo ra, không âm thầm coi là empty.

### Thực hành I — Đồng bộ dữ liệu

Tạo hai file có cùng nội dung và mtime khác nhau, rồi hai file có nội dung khác nhau nhưng set mtime giống nhau. Viết kết luận về vì sao mtime là một heuristic chứ không phải checksum.

### Thực hành J — Bộ lọc theo UTC

Viết method nhận `Path` và `Instant threshold`, trả true khi `Files.getLastModifiedTime(path).toInstant().isAfter(threshold)`. Thử boundary bằng nhau, cũ hơn, mới hơn; dùng file tạm và timestamp cố định để test không phụ thuộc đồng hồ thực.

## 25. Tham chiếu Java chính thức

- [Oracle Java SE 17 — FileTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileTime.html): `fromMillis`, `from(long,TimeUnit)`, `from(Instant)`, `toMillis`, `toInstant`, `compareTo`, độ chính xác và giá trị cực hạn.
- [Oracle Java SE 17 — BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): `creationTime`, `lastModifiedTime`, `lastAccessTime`, các fallback khi filesystem không hỗ trợ.
- [Oracle Java SE 17 — BasicFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributeView.html): `readAttributes`, `setTimes`, thứ tự tham số, `null` semantics và sự thiếu bảo đảm atomicity/precision.
- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `readAttributes`, `getAttribute`, `setAttribute`, `getLastModifiedTime`, `setLastModifiedTime`, `copy` và `getFileAttributeView`.
- [Oracle Java SE 17 — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [Oracle Java SE 17 — StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): `COPY_ATTRIBUTES`.
- [Oracle Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) và [ZoneId](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): điểm thời gian tuyệt đối và cách hiển thị theo múi giờ.
- [Oracle Java SE 17 — TimeUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): đơn vị thời gian khi tạo `FileTime`.

**Ghi nhớ:** `FileTime` là một **giá trị thời điểm**, còn `BasicFileAttributes` là cách đọc các mốc thời gian mà filesystem báo cho **một file cụ thể**. Dùng `creationTime()`, `lastModifiedTime()`, `lastAccessTime()` để đọc; `Files.getLastModifiedTime` khi chỉ cần mtime; `setLastModifiedTime` hoặc `BasicFileAttributeView.setTimes` khi cần cập nhật. Hãy tách **UTC timestamp** khỏi **giờ hiển thị**, xét **độ phân giải và mức hỗ trợ của provider**, không dùng atime/creation/mtime như bằng chứng bất biến và luôn xử lý `IOException`/symlink/concurrency theo hợp đồng ứng dụng.
