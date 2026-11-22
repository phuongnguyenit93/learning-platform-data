# Thời gian tạo, sửa, truy cập và `FileTime` trong Java NIO.2

## Mục tiêu bài học

Một file không chỉ có tên, kích thước và nội dung. Filesystem còn có thể lưu các **mốc thời gian** (*timestamps*), thường gồm **thời gian tạo** (*creation time*), **thời gian sửa nội dung gần nhất** (*last-modified time*) và **thời gian truy cập gần nhất** (*last-access time*). Trong Java NIO.2, `BasicFileAttributes` cho phép đọc ba thuộc tính này; `FileTime` là kiểu biểu diễn thời điểm dùng trong API filesystem.

Những mốc thời gian đó **không phải hợp đồng tuyệt đối giống nhau trên mọi hệ điều hành, thiết bị lưu trữ hay filesystem**. Một số timestamp không được hỗ trợ thật sự; giá trị có thể là giá trị thay thế, làm tròn theo độ phân giải, bị trì hoãn cập nhật hoặc thay đổi bởi công cụ sao chép/đồng bộ.

Sau bài này, bạn có thể:

- Phân biệt `creationTime()`, `lastModifiedTime()`, `lastAccessTime()` và tránh nhầm **Unix ctime** với creation time.
- Đọc thuộc tính qua `Files.readAttributes(..., BasicFileAttributes.class)`, `Files.getLastModifiedTime()`, hoặc `Files.getAttribute()`.
- Sử dụng `FileTime.fromMillis(...)`, `FileTime.from(Instant)`, `toMillis()`, `toInstant()`, `to(TimeUnit)`, `compareTo()`.
- Hiểu `Instant` là thời điểm độc lập múi giờ; múi giờ chỉ xuất hiện khi **hiển thị**, ví dụ `Asia/Ho_Chi_Minh`.
- Thay đổi `lastModifiedTime` bằng `Files.setLastModifiedTime()` và tìm hiểu `BasicFileAttributeView.setTimes()` cho các timestamp khác.
- Xử lý symbolic link với `LinkOption.NOFOLLOW_LINKS`, lỗi `IOException`, vấn đề độ phân giải, copy metadata và **TOCTOU**.
- Chạy các ví dụ Java 17+ và diễn giải đúng những kết quả **ổn định** so với kết quả **phụ thuộc filesystem**.

## 1. Ba loại thời gian chính

Giả sử một file được tạo, sau đó được ghi lại và được đọc:

```text
09:00   Tạo file "report.txt"
09:15   Sửa nội dung "report.txt"
09:20   Mở và đọc nội dung
            │
            ├─ creationTime       → thời điểm tạo (nếu filesystem hỗ trợ)
            ├─ lastModifiedTime   → thời điểm sửa nội dung theo metadata
            └─ lastAccessTime     → thời điểm truy cập theo metadata
```

Đây là **minh họa khái niệm**, không phải cam kết rằng mọi hệ thống sẽ lưu đúng 09:00, 09:15, 09:20. Trên một số filesystem, `lastAccessTime` không cập nhật theo mỗi lần đọc; `creationTime` có thể thiếu hoặc được mô phỏng.

| Timestamp | Java NIO.2 | Câu hỏi mà nó *thường* trả lời | Lưu ý |
|---|---|---|---|
| **Creation time** | `BasicFileAttributes.creationTime()` | Entry/file được tạo khi nào? | Không phải mọi filesystem đều lưu “birth time”; có thể trả giá trị mặc định của provider |
| **Last modified time** | `BasicFileAttributes.lastModifiedTime()` | Nội dung file được sửa gần đây nhất khi nào? | Có thể bị đặt lại bằng API, copy hoặc restore; không phải checksum nội dung |
| **Last access time** | `BasicFileAttributes.lastAccessTime()` | File được truy cập gần đây nhất khi nào? | Có thể tắt hoặc giảm tần suất cập nhật để tối ưu I/O |

### Creation time có luôn đáng tin?

Không. `creationTime()` là thời gian tạo **theo khả năng filesystem/provider cung cấp**. Nếu không hỗ trợ mốc tạo, Java cho phép provider trả một **giá trị mặc định tùy triển khai**, ví dụ dùng last-modified time. Giá trị không `null` không chứng minh đó là timestamp tạo gốc của file.

Ngoài ra:

- **Sao chép** một file có thể tạo entry mới nhưng **giữ metadata nguồn** nếu ứng dụng dùng cơ chế bảo toàn thuộc tính.
- **Move/rename** trên cùng filesystem thường không tương đương tạo mới nội dung, nhưng ngữ nghĩa timestamp phụ thuộc filesystem.
- File được **restore** từ backup hoặc archive có thể mang timestamp được phục hồi, không phải thời điểm thực sự xuất hiện ở đích.
- Có thể tạo file rồi đặt thủ công timestamp trong phạm vi filesystem cho phép.

Đừng dùng `creationTime()` như ID, bằng chứng pháp lý duy nhất, nguồn sự thật chống gian lận hoặc khóa giao dịch.

### Last modified time có ghi mọi thay đổi metadata?

Không nên giả định. Trong mô hình POSIX, một thay đổi nội dung thường cập nhật `mtime`; thay đổi metadata như mode/owner thường liên quan `ctime`. **Unix ctime thông thường là *status-change time*, không phải creation time**. Đây là một nhầm lẫn đặc biệt dễ gặp khi thấy chữ “c”.

`BasicFileAttributes` chuẩn có `creationTime`, `lastModifiedTime`, `lastAccessTime`; nó không định nghĩa một phương thức `ctime()` chuẩn tương đương POSIX status-change time. Nếu cần metadata đặc thù, phải kiểm tra khả năng của provider, OS hoặc API native tương ứng.

### Last access time có thay đổi sau mỗi `read()`?

**Không được bảo đảm.** Nhiều hệ thống có cơ chế tối ưu như không ghi access time hoặc chỉ cập nhật trong một số điều kiện (*noatime*, *relatime* trên một số môi trường Unix). Một số filesystem, thiết bị, cơ chế cache hoặc phương thức đọc cũng có hành vi riêng.

Vì vậy, không xây dựng thuật toán “file nào có atime cũ nhất thì chắc chắn chưa từng được dùng gần đây” nếu nghiệp vụ cần độ chính xác cao. Đối với sản phẩm theo dõi lượt truy cập, nên ghi sự kiện truy cập do **ứng dụng** quản lý, thay vì coi atime là log nghiệp vụ tuyệt đối.

## 2. Các API đọc timestamp trong Java 17

Import thường gặp:

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
```

### 2.1. Đọc cả ba thời gian trong một lần

```java
BasicFileAttributes attrs = Files.readAttributes(
    path,
    BasicFileAttributes.class
);

FileTime created = attrs.creationTime();
FileTime modified = attrs.lastModifiedTime();
FileTime accessed = attrs.lastAccessTime();
```

Đây là **đoạn minh họa**, `path` là một `Path` hợp lệ và caller phải xử lý `IOException`.

`BasicFileAttributes` còn có các phương thức như `size()`, `isRegularFile()`, `isDirectory()`, `isSymbolicLink()`, `fileKey()\). Nếu vừa cần loại file vừa cần nhiều timestamp, lấy chung `BasicFileAttributes` giúp biểu đạt rõ “đọc nhóm metadata” và thường tránh ba lời gọi metadata riêng lẻ.

**Không nên diễn giải “đọc cùng `BasicFileAttributes`” là một giao dịch filesystem hoàn toàn nguyên tử.** Provider có thể không thu thập mọi thuộc tính bằng một thao tác bất khả phân chia, và file vẫn có thể bị thay đổi đồng thời.

### 2.2. Đọc riêng last-modified time

```java
FileTime modified = Files.getLastModifiedTime(path);
```

Đây là **đoạn minh họa**, cần xử lý `IOException`. API này tiện nếu bài toán chỉ cần một timestamp. Mặc định nó **theo symbolic link**; có thể truyền `LinkOption.NOFOLLOW_LINKS` khi muốn đọc metadata của chính link:

```java
FileTime linkModified = Files.getLastModifiedTime(
    path, LinkOption.NOFOLLOW_LINKS
);
```

`NOFOLLOW_LINKS` có ý nghĩa khi `path` trỏ tới symbolic link. Nó không tự bảo đảm các filesystem hỗ trợ mọi thuộc tính của link hoặc loại bỏ race giữa các thao tác.

### 2.3. Đọc qua tên thuộc tính dạng chuỗi

Nếu API yêu cầu tên thuộc tính:

```java
FileTime modified = (FileTime) Files.getAttribute(
    path, "basic:lastModifiedTime"
);
```

Đây là **đoạn minh họa**, cần xử lý `IOException`. Provider có thể hỗ trợ attribute view `basic` và các view bổ sung. Khi biết trước mình cần ba mốc thời gian chuẩn, API **strongly typed** `BasicFileAttributes` thường rõ hơn và tránh cast nhầm.

Có thể đọc nhiều thuộc tính theo cú pháp:

```java
Map<String, Object> values = Files.readAttributes(
    path, "basic:creationTime,lastModifiedTime,lastAccessTime"
);
```

Đây là **đoạn minh họa**, cần import `java.util.Map` và xử lý `IOException`. Values có kiểu `Object`, nên code cần cast đúng `FileTime` khi lấy từng key. Nếu chỉ đang học ba timestamp cơ bản, ưu tiên `BasicFileAttributes` để compiler giúp kiểm tra kiểu dữ liệu.

### 2.4. Mặc định theo symbolic link

Các lời gọi đọc thuộc tính có thể được truyền `NOFOLLOW_LINKS` để đổi đối tượng đang kiểm tra. Mặc định, nhiều phép đọc NIO.2 **đi qua symbolic link** và lấy thông tin target. Điều này ảnh hưởng trực tiếp tới ý nghĩa “thời gian tạo của *cái gì*?”: **link entry** hay **file đích**.

## 3. `FileTime`: biểu diễn thời điểm cho filesystem

`java.nio.file.attribute.FileTime` là kiểu bất biến, biểu diễn một thời điểm trong API thuộc tính file. Đừng nhầm nó với `java.io.File`; cũng đừng nhầm `FileTime` với `LocalDateTime` (ngày-giờ địa phương không gắn rõ múi giờ).

Các phương thức hữu ích:

| API | Ý nghĩa |
|---|---|
| `FileTime.fromMillis(long value)` | Tạo từ milliseconds tính từ Unix epoch |
| `FileTime.from(long value, TimeUnit unit)` | Tạo từ số lượng đơn vị thời gian so với epoch |
| `FileTime.from(Instant instant)` | Tạo từ `java.time.Instant` |
| `fileTime.toMillis()` | Chuyển về milliseconds kể từ epoch, **có thể mất độ chính xác** |
| `fileTime.to(TimeUnit unit)` | Chuyển thành giá trị với đơn vị tương ứng |
| `fileTime.toInstant()` | Chuyển thành `Instant`, thuận tiện tính toán và hiển thị |
| `fileTime.compareTo(other)` | So sánh thứ tự thời điểm |
| `fileTime.equals(other)` | So sánh hai giá trị `FileTime` theo hợp đồng giá trị |
| `fileTime.toString()` | Dạng chuỗi timestamp theo hợp đồng API |

`FileTime` không phải số mili-giây thuần túy; nó có thể đại diện độ chính xác khác mili-giây. `FileTime.from(Instant)` còn giúp làm việc với nanoseconds nếu `Instant` chứa phần nano.

### Unix epoch và độ chính xác

**Unix epoch** là `1970-01-01T00:00:00Z`. Giá trị tính từ epoch có thể âm nếu thời điểm trước epoch. Ví dụ:

```java
FileTime epoch = FileTime.fromMillis(0);
FileTime plusOneSecond = FileTime.from(1, TimeUnit.SECONDS);
```

Đây là **đoạn minh họa**, cần `FileTime` và `TimeUnit` (`java.util.concurrent.TimeUnit`).

Những khác biệt:

- `fromMillis(1_000)` và `from(1, TimeUnit.SECONDS)` biểu diễn **cùng thời điểm**.
- `from(Instant.parse("2025-01-01T00:00:00.123456789Z"))` có phần nano chi tiết hơn một giá trị milliseconds.
- Khi gọi `toMillis()`, phần sub-millisecond **không còn được giữ**; không thể hoàn nguyên nanoseconds chỉ từ `long` milliseconds.
- Chuyển sang `TimeUnit.SECONDS` cũng mất chi tiết dưới giây.
- Với timestamp cực lớn/vượt vùng biểu diễn của kiểu đích, các phép chuyển có thể **saturate** ở biên giá trị thay vì cho kết quả toán học vô hạn. Không xây dựng thuật toán yêu cầu sự chính xác vô hạn của `long`.

Nói cách khác: **độ chính xác biểu diễn trong Java** khác với **độ phân giải thực tế mà filesystem lưu được**. Một `FileTime` với 9 chữ số phần thập phân không có nghĩa filesystem luôn sẽ lưu lại được đủ 9 chữ số.

### `FileTime` so với `Instant`

`Instant` thuộc `java.time` và mô tả một thời điểm trên timeline UTC, rất hợp để so sánh hoặc tính khoảng cách. `FileTime` là kiểu tương tác với thuộc tính file. Khi ứng dụng cần logic thời gian:

```java
Instant instant = fileTime.toInstant();
Duration age = Duration.between(instant, Instant.now());
```

Đây là **đoạn minh họa**, cần `Duration`, `Instant` và biến `fileTime` kiểu `FileTime`. `Instant.now()` phụ thuộc clock lúc thực thi; bài test deterministic nên cung cấp `Clock` hoặc `Instant` cố định thay vì so với thời gian hệ thống.

Không giả định một timestamp “cũ hơn 24 giờ” luôn là bằng chứng file không thay đổi hoặc chưa được ai đọc trong 24 giờ, vì metadata có thể bị thay đổi hoặc chưa cập nhật.

## 4. Ví dụ Java 17: chuyển đổi `FileTime`, `Instant` và múi giờ

Ví dụ đầu tiên **không truy cập filesystem**. Nó giúp kiểm tra API thời gian mà không bị nhiễu bởi độ phân giải, permission hay chính sách metadata của thiết bị.

Lưu **`FileTimeBasicsDemo.java`**:

```java
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.TimeUnit;

public class FileTimeBasicsDemo {
    public static void main(String[] args) {
        Instant point = Instant.parse(
            "2024-02-29T12:34:56.123456789Z"
        );
        FileTime fileTime = FileTime.from(point);

        System.out.println("instant: " + fileTime.toInstant());
        System.out.println("millis: " + fileTime.toMillis());
        System.out.println("round trip: " +
            fileTime.toInstant().equals(point));

        FileTime twoSeconds = FileTime.from(
            2, TimeUnit.SECONDS
        );
        System.out.println("two seconds: " +
            twoSeconds.toInstant());

        DateTimeFormatter local = DateTimeFormatter
            .ofPattern("uuuu-MM-dd HH:mm:ss")
            .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("Vietnam time: " +
            local.format(fileTime.toInstant()));
    }
}
```

Biên dịch và chạy:

```bash
javac FileTimeBasicsDemo.java
java FileTimeBasicsDemo
```

Stdout:

```text
instant: 2024-02-29T12:34:56.123456789Z
millis: 1709210096123
round trip: true
two seconds: 1970-01-01T00:00:02Z
Vietnam time: 2024-02-29 19:34:56
```

Giải thích:

1. `Instant.parse(...Z)` nhận thời điểm UTC. `FileTime.from(point)` tạo giá trị timestamp tương ứng.
2. `toInstant()` giữ được thời điểm gốc trong trường hợp giá trị bình thường này.
3. `toMillis()` trả milliseconds từ epoch; **phần `456789` nanoseconds nằm sau 123 milliseconds không được giữ**.
4. `FileTime.from(2, TimeUnit.SECONDS)` biểu diễn hai giây sau epoch.
5. Formatter dùng vùng `Asia/Ho_Chi_Minh` để hiển thị giờ địa phương: tháng 2/2024 thời điểm này là UTC+07, nên `12:34:56Z` thành `19:34:56`.

Thời điểm **không bị “đổi thành một thời điểm khác”** khi hiển thị theo múi giờ; chỉ đổi cách trình bày cùng một điểm trên timeline. Nếu cần lưu trạng thái để truyền giữa hệ thống, `Instant` hoặc thời gian epoch theo đơn vị đã quy ước thường phù hợp hơn chuỗi ngày-giờ địa phương không có zone.

## 5. Đọc timestamp thật với `BasicFileAttributes`

Một filesystem thực tế trả thời gian do nó quản lý. Hãy phân biệt **điều được bảo đảm bởi type/API** với **giá trị cụ thể phụ thuộc môi trường**.

Lưu **`ReadFileTimesDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class ReadFileTimesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("times-read-", ".txt");

        try {
            BasicFileAttributes attrs = Files.readAttributes(
                file, BasicFileAttributes.class
            );

            System.out.println("regular: " +
                attrs.isRegularFile());
            System.out.println("created available: " +
                (attrs.creationTime() != null));
            System.out.println("modified available: " +
                (attrs.lastModifiedTime() != null));
            System.out.println("accessed available: " +
                (attrs.lastAccessTime() != null));

            // Giá trị cụ thể sẽ khác mỗi lần chạy.
            System.out.println(
                "created value: " + attrs.creationTime());
            System.out.println(
                "modified value: " + attrs.lastModifiedTime());
            System.out.println(
                "accessed value: " + attrs.lastAccessTime());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy:

```bash
javac ReadFileTimesDemo.java
java ReadFileTimesDemo
```

Phần đầu stdout **thường** là:

```text
regular: true
created available: true
modified available: true
accessed available: true
```

Sau đó có ba dòng `created value: ...`, `modified value: ...`, `accessed value: ...`; **không có kết quả timestamp cố định**, vì thời gian tạo file tạm do filesystem cung cấp. API `BasicFileAttributes` trả các đối tượng `FileTime` cho ba phương thức thời gian, nhưng một timestamp có thể là **giá trị mặc định** khi filesystem không lưu thuộc tính thực; “available” trong chương trình chỉ kiểm tra **object khác null**, không phải bằng chứng “filesystem hỗ trợ timestamp tạo chính xác”.

Đừng viết unit test yêu cầu **ba timestamp bằng nhau** ngay sau `createTempFile`: độ phân giải hoặc cập nhật metadata có thể làm chúng khác nhau. Cũng không nên giả định creation time tồn tại trên Linux giống Windows; điều đó còn tùy filesystem và provider.

## 6. Đổi `lastModifiedTime`: `Files.setLastModifiedTime`

Nếu nghiệp vụ phải **đặt thời gian sửa đổi** của file:

```java
FileTime requested = FileTime.from(
    Instant.parse("2024-01-01T00:00:00Z")
);

Files.setLastModifiedTime(path, requested);
```

Đây là **đoạn minh họa**, cần xử lý `IOException`; `path` là `Path` cần sửa thuộc tính. `setLastModifiedTime` trả lại `Path`, thuận tiện khi chain nhưng không phải cam kết filesystem đã lưu **chính xác từng nanosecond**.

Những giới hạn cần nắm:

- Operation có thể thất bại do quyền truy cập, filesystem chỉ đọc, provider không hỗ trợ hoặc lỗi I/O.
- Filesystem có thể lưu thời gian ở **độ phân giải thấp hơn** hoặc làm tròn/cắt các phần lẻ.
- Nếu timestamp nằm ngoài dải filesystem có thể lưu, kết quả có thể bị giới hạn theo cách của API/provider hoặc ném lỗi.
- Một process khác có thể ghi file ngay sau khi bạn set timestamp, làm last-modified time đổi tiếp.
- Thay đổi mtime **không** đổi nội dung file. Vì thế metadata time **không phải checksum** hoặc bằng chứng dữ liệu giống nhau.

### Ví dụ Java 17: set và đọc lại mtime có kiểm tra

Lưu **`SetModifiedTimeDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Instant;

public class SetModifiedTimeDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("mtime-demo-", ".txt");
        FileTime requested = FileTime.from(
            Instant.parse("2020-01-01T00:00:00Z")
        );

        try {
            Files.setLastModifiedTime(file, requested);

            FileTime stored = Files.getLastModifiedTime(file);
            System.out.println("requested: " +
                requested.toInstant());
            System.out.println("stored: " +
                stored.toInstant());
            System.out.println("same instant: " +
                requested.toInstant().equals(stored.toInstant()));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac SetModifiedTimeDemo.java
java SetModifiedTimeDemo
```

Trên filesystem hỗ trợ và giữ chính xác mốc 2020-01-01 00:00:00 UTC theo đơn vị giây, stdout sẽ là:

```text
requested: 2020-01-01T00:00:00Z
stored: 2020-01-01T00:00:00Z
same instant: true
```

**Đây là output có điều kiện.** Filesystem có thể lưu timestamp khác yêu cầu do quy tắc provider/độ phân giải, hoặc `setLastModifiedTime` có thể ném `IOException`. Chương trình in cả giá trị `requested` và `stored` nhằm **quan sát thực tế**, không ngầm tuyên bố luôn bằng nhau.

Đặt thời điểm đúng đầu giây giúp ví dụ ít gặp sai khác do làm tròn hơn khi dùng thời điểm có nanoseconds. Trong chương trình xử lý chuyên nghiệp, nên đọc lại nếu việc lưu đúng thời điểm là yêu cầu, nhưng ngay cả readback cũng chỉ là trạng thái ở thời điểm quan sát.

## 7. Đặt nhiều timestamp qua `BasicFileAttributeView.setTimes`

Java cung cấp `BasicFileAttributeView` để làm việc với thuộc tính cơ bản của file. Với implementation hỗ trợ, bạn có thể yêu cầu cập nhật **mtime**, **atime** và **creation time**:

```java
BasicFileAttributeView view = Files.getFileAttributeView(
    path, BasicFileAttributeView.class
);

view.setTimes(modified, accessed, created);
```

Đây là **đoạn minh họa**, cần import `java.nio.file.attribute.BasicFileAttributeView`, `Files` và các biến `FileTime`, xử lý `IOException`. Không nên giả định mọi provider đều cho phép sửa cả ba timestamp, đặc biệt creation time.

Chữ ký:

```java
void setTimes(
    FileTime lastModifiedTime,
    FileTime lastAccessTime,
    FileTime createTime
) throws IOException;
```

Đây là **chữ ký API minh họa**, không phải định nghĩa mới. Ý nghĩa tham số:

1. `lastModifiedTime`: thời điểm sửa đổi nội dung.
2. `lastAccessTime`: thời điểm truy cập gần nhất.
3. `createTime`: thời điểm tạo.

**Truyền `null` cho một tham số** nghĩa là không yêu cầu cập nhật thuộc tính tương ứng, rất hữu ích khi chỉ muốn đặt một timestamp mà không làm thay đổi hai timestamp khác.

Ví dụ chỉ yêu cầu đặt access time:

```java
view.setTimes(null, desiredAccessTime, null);
```

Đây là **đoạn minh họa**. Lời gọi có thể ném `IOException`; provider có thể không hỗ trợ set access time theo ý ứng dụng. Tùy filesystem, thuộc tính không được hỗ trợ có thể bị bỏ qua theo hợp đồng provider hoặc không thể cập nhật; phải kiểm tra tài liệu/khả năng của môi trường.

### Đổi timestamp của chính symlink

Nếu cần xử lý thuộc tính của **entry link**, không phải target, lấy view với `NOFOLLOW_LINKS`:

```java
BasicFileAttributeView linkView =
    Files.getFileAttributeView(
        link,
        BasicFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS
    );
```

Đây là **đoạn minh họa**, `link` kiểu `Path`. Một filesystem có thể không cho sửa timestamp của symbolic link qua view này, hoặc có cách xử lý khác khi thiếu quyền. Không gọi `setTimes` khi `linkView == null` (nếu provider không hỗ trợ attribute view được yêu cầu); thông thường default filesystem có basic view, nhưng code sử dụng provider tùy ý nên kiểm tra capability.

**Chú ý về metadata khác:** Một lần set mtime/atime không có nghĩa mọi metadata khác bất biến. Filesystem có thể ghi timestamp status-change hoặc thông tin quản trị riêng; chương trình không nên khẳng định quá mức về những thuộc tính ngoài hợp đồng Java NIO.2.

## 8. Ví dụ Java 17: chỉ yêu cầu thay đổi access time

Để thấy rõ cách gọi `setTimes` với `null` và xử lý khác biệt provider, dùng chương trình sau.

Lưu **`SetAccessTimeDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
import java.time.Instant;

public class SetAccessTimeDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("atime-demo-", ".txt");

        try {
            BasicFileAttributeView view =
                Files.getFileAttributeView(
                    file, BasicFileAttributeView.class);

            if (view == null) {
                System.out.println("Basic view unavailable");
                return;
            }

            FileTime desired = FileTime.from(
                Instant.parse("2020-01-01T00:00:00Z")
            );

            try {
                view.setTimes(null, desired, null);
                BasicFileAttributes attrs = view.readAttributes();

                System.out.println("requested: " +
                    desired.toInstant());
                System.out.println("observed: " +
                    attrs.lastAccessTime().toInstant());
            } catch (IOException | UnsupportedOperationException ex) {
                System.out.println(
                    "Access-time update unavailable");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Chạy:

```bash
javac SetAccessTimeDemo.java
java SetAccessTimeDemo
```

Với một filesystem hỗ trợ thay đổi atime như yêu cầu, hai dòng quan sát thường là:

```text
requested: 2020-01-01T00:00:00Z
observed: 2020-01-01T00:00:00Z
```

Một số môi trường có thể hiển thị timestamp `observed` khác, in `Access-time update unavailable`, hoặc không cung cấp view được yêu cầu. Mục đích của ví dụ là **thực hiện và quan sát** lời gọi, chứ không quy kết một kết quả duy nhất cho mọi filesystem.

Đặc biệt, một lần **đọc metadata** không giống một lần đọc nội dung file. Nhưng provider có thể có chính sách cập nhật access time riêng, do đó không nên dựa vào kết quả thí nghiệm đơn lẻ để suy ra mọi thao tác sau sẽ không làm thay đổi atime.

## 9. Múi giờ, UTC và cách hiển thị timestamp

Các timestamp của `FileTime` đại diện **một thời điểm**, không phải một cặp ngày/giờ gắn với múi giờ của người xem. Để hiển thị đúng theo người dùng, chuyển sang `Instant`, sau đó dùng `ZoneId` và `DateTimeFormatter`:

```java
DateTimeFormatter fmt = DateTimeFormatter
    .ofPattern("uuuu-MM-dd HH:mm:ss z")
    .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(
    fmt.format(fileTime.toInstant())
);
```

Đây là **đoạn minh họa**, cần import `java.time.ZoneId`, `java.time.format.DateTimeFormatter` và biến `fileTime`.

**Không** diễn giải `toMillis()` là milliseconds theo giờ Việt Nam hoặc giờ máy: epoch milliseconds là số lượng milliseconds trên timeline UTC. Chuyển sang GMT+7 chỉ ảnh hưởng biểu diễn.

Một tình huống dễ nhầm:

- Java in timestamp `2024-02-29T12:34:56Z`.
- File manager trên máy ở Việt Nam có thể hiển thị `19:34:56`.
- Hai giá trị có thể chỉ **cùng một thời điểm**, không phải file bị sửa hai lần.

Khi trao đổi timestamp giữa dịch vụ, nên quy định một định dạng thời điểm rõ ràng như ISO-8601 có offset/UTC hoặc epoch milliseconds; không gửi riêng `"29/02/2024 19:34:56"` mà không nói múi giờ nếu hệ thống có nhiều vùng địa lý.

### `LocalDateTime` không phải `Instant`

`LocalDateTime` là ngày-giờ **không mang zone/offset**; `Instant` là một điểm thời gian có nghĩa tuyệt đối. Đừng làm:

```java
LocalDateTime local = LocalDateTime.parse("2024-02-29T19:34:56");
// Không thể suy ra một Instant duy nhất nếu chưa xác định zone/offset.
```

Đây là **đoạn minh họa**, cần import `LocalDateTime`. Cùng một ngày-giờ địa phương có thể ứng với thời điểm khác nhau trên thế giới, và ở một số múi giờ có chuyển DST còn có khoảng thời gian bị lặp hoặc không tồn tại.

## 10. Độ phân giải, làm tròn và tính nhất quán

Không phải mọi filesystem lưu timestamp chính xác tới nanosecond. Một ví dụ lý thuyết:

```text
Java yêu cầu mtime:
2024-01-01T00:00:00.123456789Z

Filesystem A lưu được:
2024-01-01T00:00:00.123456789Z

Filesystem B có thể chỉ lưu được:
2024-01-01T00:00:00.123Z

Filesystem C có thể lưu theo bước thô hơn:
2024-01-01T00:00:00Z
```

Đây là **minh họa**, không khẳng định một filesystem cụ thể luôn có chính xác một trong ba mức trên.

Các hệ quả:

1. **Không so sánh `FileTime` sát từng nanosecond** trong integration test portable sau khi set/read timestamp, trừ khi môi trường đã có hợp đồng về độ phân giải.
2. Khi kiểm tra “file có thay đổi”, mtime bằng nhau **không** bảo đảm nội dung giống nhau. Hai lần ghi có thể rơi vào cùng một tick timestamp hoặc mtime bị set trở lại.
3. Khi kiểm tra “mtime khác”, bản thân việc backup/restore/copy có thể thay timestamp mà không đổi nội dung.
4. `Files.readAttributes` trên network filesystem có thể phản ánh cache metadata; đừng mặc định giá trị luôn cập nhật ngay tức thì trên tất cả máy.
5. `FileTime.toMillis()` làm mất phần thời gian nhỏ hơn 1 ms; tránh chuyển qua milliseconds nếu nghiệp vụ cần độ phân giải cao và cả nguồn/đích thực sự hỗ trợ.
6. Các phép đo tuổi file dùng `Instant.now()` còn bị ảnh hưởng bởi clock skew hoặc đồng hồ hệ thống được điều chỉnh; không coi mtime như clock đơn điệu.

Nếu muốn đo **khoảng thời gian một tác vụ chạy**, dùng `System.nanoTime()` hoặc clock đơn điệu phù hợp, **không dùng thời gian sửa file** làm đồng hồ đo hiệu năng.

### Dùng mtime cho cache hoặc incremental scan

Một bộ quét file thường làm:

```text
Lần trước: lưu (đường dẫn, mtime, kích thước)
Lần sau: lấy metadata mới, nếu khác → xử lý lại
```

Đây là **heuristic tối ưu**, không phải bằng chứng mật mã rằng file không đổi nếu metadata trùng. Muốn tính toàn vẹn mạnh, có thể cần hash nội dung hoặc hệ thống version/commit ID được quản lý nhất quán. Hash cũng phải được tính từ dữ liệu được đọc đúng cách, trong khi file có thể bị thay đổi đồng thời; hệ thống nghiêm ngặt có thể cần snapshot hoặc cơ chế transaction của storage.

## 11. Sao chép, di chuyển và timestamp

Sao chép file không nhất thiết giữ mọi timestamp của nguồn. `Files.copy` có option `StandardCopyOption.COPY_ATTRIBUTES` để **cố gắng sao chép metadata** khi provider hỗ trợ:

```java
Files.copy(
    source,
    target,
    StandardCopyOption.COPY_ATTRIBUTES
);
```

Đây là **đoạn minh họa**, với `source`, `target` kiểu `Path`, đã import `Files`/`StandardCopyOption` và xử lý `IOException`. Có những thuộc tính không thể copy chính xác hoặc bị provider giới hạn; mức hỗ trợ cụ thể tùy filesystem. Chỉ vì `COPY_ATTRIBUTES` được yêu cầu **không nên kết luận** creation/modified/access time của file đích hoàn toàn giống nguồn trên mọi môi trường.

Một số câu hỏi phải xác định theo nghiệp vụ:

- File đích là **bản sao lịch sử** và nên giữ mtime nguồn?
- File đích là **tài liệu mới sinh**, nên có timestamp hiện tại?
- Khi restore, phải phục hồi metadata nào? Có quyền đặt creation time không?
- Nếu mục tiêu dùng mtime để invalid cache, việc copy giữ mtime có thể khiến cache bỏ qua nội dung khác không?

**Move/rename** cũng có thể ảnh hưởng mốc thời gian theo quy tắc khác copy. Với `ATOMIC_MOVE`, trọng tâm của option là tính nguyên tử của thao tác move ở mức provider hỗ trợ, không phải hứa hẹn mọi timestamp bất biến và durable sau sự cố.

## 12. Symbolic link và object identity

Khi làm việc với symlink:

```text
root/
├── target.txt          (nội dung thật)
└── shortcut.txt -> target.txt
```

Có ít nhất hai nhóm metadata được quan tâm:

- Metadata của **target.txt**.
- Metadata của chính **shortcut.txt** như một symbolic link entry.

`Files.readAttributes(link, BasicFileAttributes.class)` thường theo link và đọc thuộc tính target; `Files.readAttributes(link, BasicFileAttributes.class, NOFOLLOW_LINKS)` đọc thuộc tính link entry nếu provider hỗ trợ.

```java
BasicFileAttributes targetAttributes = Files.readAttributes(
    link, BasicFileAttributes.class
);

BasicFileAttributes linkAttributes = Files.readAttributes(
    link, BasicFileAttributes.class,
    LinkOption.NOFOLLOW_LINKS
);
```

Đây là **đoạn minh họa**, `link` là `Path`, cần các import tương ứng và xử lý `IOException`.

Nếu là **dangling link** (target bị xóa), lời gọi follow-link có thể thất bại hoặc không xác minh được target, còn `NOFOLLOW_LINKS` có thể đọc được metadata của entry link còn tồn tại. Việc link có mtime khác target là điều có thể xảy ra; không thể suy ra trạng thái link từ mtime của target và ngược lại.

### Không dùng timestamp như ID bền vững

Hai file có thể có cùng mtime; một file có thể bị thay bằng file khác **cùng tên, cùng kích thước và cùng mtime**. Nếu cần nhận diện object, `BasicFileAttributes.fileKey()` có thể giúp ở một số provider, nhưng **không được bảo đảm khác null hoặc bền qua mọi thao tác/khởi động**. Tùy mục tiêu, cần database ID, content hash, version hoặc handle mở an toàn.

## 13. Xử lý lỗi khi đọc và đặt timestamp

Các API metadata có thể ném:

| Lỗi/tình huống | Diễn giải |
|---|---|
| `NoSuchFileException` | Đường dẫn không còn tồn tại tại thời điểm thao tác (nếu provider báo subtype này) |
| `AccessDeniedException` | Không có quyền cho thao tác tương ứng |
| `FileSystemException` | Lỗi filesystem cụ thể, có thể kèm lý do |
| `IOException` | Lỗi I/O chung hoặc lỗi do provider |
| `UnsupportedOperationException` | Thao tác/thuộc tính/option không được hỗ trợ theo API/provider |
| `SecurityException` | Kiểm tra bảo mật runtime từ chối theo môi trường |
| Kết quả timestamp mặc định | Không phải lúc nào cũng là lỗi; provider có thể không hỗ trợ timestamp thực |

Không bắt mọi `IOException` rồi in “file không tồn tại”. Lỗi quyền, thiết bị và path missing cần chính sách retry/báo lỗi khác nhau.

Một đoạn xử lý:

```java
try {
    BasicFileAttributes attrs = Files.readAttributes(
        path, BasicFileAttributes.class
    );
    System.out.println(attrs.lastModifiedTime());
} catch (NoSuchFileException ex) {
    System.err.println("Path missing: " + path);
} catch (AccessDeniedException ex) {
    System.err.println("Access denied: " + path);
} catch (IOException ex) {
    System.err.println("Metadata I/O error: " + ex.getMessage());
}
```

Đây là **đoạn minh họa**, cần `Files`, `Path`, `BasicFileAttributes` và các subtype exception `java.nio.file`.

Với filesystem đa provider, exception subtype không phải lúc nào giống nhau. Trong ứng dụng cần kiểm soát việc retry/backup, hãy ghi log context, phân biệt lỗi tạm thời với lỗi chắc chắn và tránh xóa/cập nhật file chỉ vì không đọc được metadata.

## 14. TOCTOU: metadata vừa đọc có thể đã cũ

Một đoạn code:

```java
if (Files.getLastModifiedTime(path).toMillis() < cutoff) {
    Files.delete(path);
}
```

Đây là **phản ví dụ nguy hiểm nếu directory bị sửa đồng thời**. Sau lúc kiểm tra, process khác có thể ghi đè hoặc thay thế entry. Nếu xóa bằng pathname sau đó, chương trình có thể xóa **file mới**, không phải file cũ mà metadata vừa mô tả.

Lược đồ:

```text
T1  Scanner đọc mtime của report.txt → "cũ"
T2  Process khác thay report.txt bằng bản mới
T3  Scanner gọi Files.delete(report.txt)
T4  Bản mới bị xóa ngoài ý muốn
```

Đây là dạng **time-of-check-to-time-of-use**. Một lệnh `readAttributes` không giữ khóa filesystem sau khi hàm kết thúc.

Cách giảm rủi ro phụ thuộc môi trường:

- Giới hạn quyền ghi vào directory được quét; tránh cho untrusted process sửa cùng lúc.
- Dùng workflow version/snapshot/lock phù hợp hoặc lưu trạng thái qua transaction của ứng dụng.
- Với thao tác theo directory cần chống race đường dẫn, cân nhắc `SecureDirectoryStream` nếu provider hỗ trợ.
- Nếu cần xóa chỉ những file chắc chắn thuộc một phiên bản, thiết kế protocol với ID/version; không dựa độc nhất vào `mtime`/filename.
- Một lần kiểm tra lại ngay trước xóa có thể giảm xác suất race, nhưng **không loại bỏ** khoảng thời gian giữa kiểm tra và thao tác.

**Timestamp không phải cơ chế bảo mật hoặc đồng bộ.**

## 15. `java.io.File.lastModified()` so với NIO.2

Java I/O truyền thống có các phương thức:

```java
File f = new File("report.txt");
long modifiedMillis = f.lastModified();
boolean changed = f.setLastModified(
    1_700_000_000_000L
);
```

Đây là **đoạn minh họa**, cần import `java.io.File`. Có hai giới hạn đáng chú ý:

- `File.lastModified()` trả `long` milliseconds; **0L cũng có thể là giá trị báo không lấy được thông tin** theo hợp đồng, gây nhập nhằng với timestamp epoch thật.
- `File.setLastModified(long)` trả `boolean` báo thành công/thất bại, ít giàu thông tin lỗi hơn cách dùng `Files.setLastModifiedTime` và checked exceptions.

NIO.2 thường diễn đạt chính xác hơn:

```java
Path path = f.toPath();
FileTime mtime = Files.getLastModifiedTime(path);
Files.setLastModifiedTime(
    path, FileTime.fromMillis(1_700_000_000_000L)
);
```

Đây là **đoạn minh họa**, cần import `Files`, `Path`, `FileTime` và xử lý `IOException`.

Nếu mục tiêu là **creation/access time**, `BasicFileAttributes` và `BasicFileAttributeView` mới là API tổng quát phù hợp. Không cố đọc “creation time” từ `File.lastModified()` vì đó là hai thuộc tính khác nhau.

## 16. Các lỗi phổ biến

1. **Nhầm Unix `ctime` với creation time.** Trên nhiều hệ Unix, `ctime` nói về thay đổi trạng thái metadata, không phải “birth time”.
2. **Tin `creationTime()` luôn là timestamp tạo thật.** Provider có thể trả giá trị thay thế nếu không hỗ trợ.
3. **Tin `lastAccessTime()` luôn đổi sau mỗi lần đọc.** Chính sách noatime/relatime, cache và provider ảnh hưởng cập nhật.
4. **So sánh timestamp theo chuỗi ngày-giờ địa phương.** Dùng `Instant`/`FileTime` để so sánh thời điểm; dùng zone khi trình bày.
5. **Coi `FileTime.toMillis()` giữ nanoseconds.** Nó chỉ biểu diễn milliseconds; phần nhỏ hơn bị mất.
6. **Đặt mtime với nano bất kỳ rồi assert đọc lại giống 100%.** Filesystem có thể làm tròn hoặc có độ phân giải thấp.
7. **Coi file có mtime giống nhau là có nội dung giống nhau.** Cần thêm cơ chế kiểm tra phiên bản/hash nếu nghiệp vụ yêu cầu.
8. **Coi mtime khác là bằng chứng nội dung khác.** Metadata có thể bị đổi qua copy/restore hoặc API set time.
9. **Nhầm timestamp của symlink và target.** Chọn follow hoặc `NOFOLLOW_LINKS` theo câu hỏi.
10. **Bỏ qua `IOException` khi set time.** Quyền truy cập, filesystem chỉ đọc và provider có thể từ chối.
11. **Quên `null` trong `BasicFileAttributeView.setTimes`.** `null` nghĩa là không yêu cầu đặt timestamp tương ứng, không phải “đặt về epoch”.
12. **Dùng `Files.exists()` trước mỗi thao tác và nghĩ tránh race.** Kết quả check có thể lỗi thời; thao tác chính vẫn cần catch error.
13. **Dùng mtime làm ID file.** Timestamp không duy nhất và có thể bị giả lập/giữ nguyên khi file bị thay.
14. **Không phân biệt `FileTime` với `LocalDateTime`.** `FileTime` là thời điểm filesystem; `LocalDateTime` thiếu zone/offset.
15. **Coi Java API luôn tự đồng bộ metadata xuống đĩa bền vững.** Set time thành công không phải cam kết crash durability trên mọi thiết bị.
16. **Hiểu `Files.copy(..., COPY_ATTRIBUTES)` là bảo toàn mọi timestamp hoàn hảo.** Khả năng copy metadata tùy provider và storage.
17. **Không kiểm thử thực tế filesystem đích.** Local development, network mount, container và production có thể có cơ chế timestamp khác nhau.

## 17. Bảng chọn API theo tình huống

| Nhu cầu | API/thiết kế đề xuất |
|---|---|
| Xem thời gian sửa một file | `Files.getLastModifiedTime(path)` |
| Xem cả tạo/sửa/truy cập | `Files.readAttributes(path, BasicFileAttributes.class)` |
| Cần metadata của chính symbolic link | Truyền `LinkOption.NOFOLLOW_LINKS` khi API hỗ trợ |
| Đặt mtime | `Files.setLastModifiedTime(path, fileTime)` |
| Yêu cầu đặt atime/creation time | `BasicFileAttributeView.setTimes(...)` và kiểm tra provider |
| Lưu/truyền một thời điểm | `Instant` hoặc epoch millis với đơn vị được quy định |
| Hiển thị theo giờ Việt Nam | `fileTime.toInstant()` + `ZoneId.of("Asia/Ho_Chi_Minh")` |
| So sánh hai timestamp | `FileTime.compareTo` hoặc `Instant.compareTo` |
| Kiểm tra thay đổi nội dung mạnh | Hash/version và cơ chế đồng bộ phù hợp, không chỉ mtime |
| Theo dõi truy cập nghiệp vụ | Log/sự kiện truy cập do ứng dụng quản lý |
| Cần xác định lỗi I/O rõ ràng | API NIO.2 với `IOException`/subtype |
| Tạo/xóa theo trạng thái để tránh race | API thao tác trực tiếp, version/transaction thay vì check-then-act |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Ba phương thức thời gian quan trọng của `BasicFileAttributes` là gì?

**Đáp án:** `creationTime()`, `lastModifiedTime()`, `lastAccessTime()`; chúng trả `FileTime`.

**Câu 2.** `creationTime()` có luôn bằng thời điểm file xuất hiện lần đầu trên ổ đĩa không?

**Đáp án:** Không. Filesystem có thể không hỗ trợ timestamp tạo thực, provider có thể trả giá trị mặc định; copy/restore/set metadata có thể thay nghĩa của timestamp.

**Câu 3.** Unix `ctime` có phải creation time không?

**Đáp án:** Thông thường không. Unix `ctime` là thời gian thay đổi trạng thái inode/metadata; khác birth/creation time.

**Câu 4.** `FileTime.from(Instant)` và `toMillis()` có luôn bảo toàn nanosecond không?

**Đáp án:** `FileTime` có thể biểu diễn độ chính xác cao, nhưng `toMillis()` làm mất phần nhỏ hơn milliseconds. Filesystem thực tế còn có độ phân giải riêng.

**Câu 5.** Tại sao `lastAccessTime()` không phù hợp làm lịch sử lượt đọc đáng tin cậy?

**Đáp án:** OS/filesystem có thể không cập nhật atime mỗi lần đọc hoặc dùng chính sách tối ưu, cache; timestamp cũng có thể bị đặt lại.

**Câu 6.** Muốn đặt chỉ mtime qua `BasicFileAttributeView.setTimes`, truyền tham số nào?

**Đáp án:** `view.setTimes(desiredModified, null, null)`. Hai `null` nghĩa là không yêu cầu cập nhật atime và creation time.

**Câu 7.** Muốn đọc metadata của symlink, không phải target, làm thế nào?

**Đáp án:** `Files.readAttributes(link, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS)` khi provider hỗ trợ.

**Câu 8.** Có thể kết luận file nội dung không đổi khi mtime và size không đổi?

**Đáp án:** Không. Mtime có thể làm tròn, được đặt lại; nội dung có thể thay nhưng kích thước giữ nguyên. Đó chỉ là heuristic.

**Câu 9.** `Files.setLastModifiedTime` thành công có bảo đảm đọc lại chính xác timestamp nano không?

**Đáp án:** Không. Độ phân giải, dải thời gian, quyền và hành vi filesystem/provider có thể làm khác; nếu quan trọng phải đọc lại và kiểm chứng theo môi trường.

**Câu 10.** Đọc mtime rồi xóa file nếu mtime quá cũ có an toàn khi process khác cũng ghi directory đó?

**Đáp án:** Không chắc. Đây là TOCTOU: file có thể bị thay trước khi xóa. Cần cơ chế version, lock/snapshot hoặc API/thiết kế phù hợp.

**Câu 11.** Vì sao `File.lastModified()` cũ có thể ít rõ ràng hơn `Files.getLastModifiedTime()`?

**Đáp án:** `File.lastModified()` trả long milliseconds và giá trị 0 có thể biểu thị không lấy được thông tin; NIO.2 dùng `FileTime` và checked `IOException` giàu ngữ cảnh hơn.

**Câu 12.** Muốn hiển thị cùng thời điểm cho người dùng ở hai múi giờ khác nhau, có cần sửa timestamp file không?

**Đáp án:** Không. Dùng cùng `Instant`, format theo `ZoneId` tương ứng; timestamp gốc không thay đổi.

## Tổng kết

- **Creation**, **last modified** và **last access** là ba loại timestamp khác nhau, có thể thiếu hoặc không chính xác tuyệt đối tùy filesystem.
- `BasicFileAttributes` đọc ba timestamp dưới dạng `FileTime`; `Files.getLastModifiedTime` tiện khi chỉ cần mtime.
- `FileTime` là thời điểm, có thể chuyển qua `Instant` để so sánh/format; `toMillis()` không giữ độ chính xác dưới mili-giây.
- `Files.setLastModifiedTime` và `BasicFileAttributeView.setTimes` cho phép **yêu cầu** sửa metadata trong phạm vi provider hỗ trợ; không bảo đảm mọi timestamp đều đặt được hay được lưu nguyên vẹn.
- **Symlink**, **múi giờ**, **độ phân giải**, **copy/restore**, **quyền truy cập** và **thao tác đồng thời** đều ảnh hưởng cách đọc/diễn giải timestamp.
- Khi nghiệp vụ đòi hỏi tính toàn vẹn mạnh, đồng bộ hóa hoặc lịch sử truy cập, không xem timestamp của filesystem là nguồn sự thật duy nhất.
