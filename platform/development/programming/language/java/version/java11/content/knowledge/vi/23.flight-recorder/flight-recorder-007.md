# Duration, max age, max size và lưu dữ liệu trong Java Flight Recorder (JFR) — Java 11+

## 1. Mục tiêu và ý nghĩa của việc giới hạn recording

**Java Flight Recorder (JFR)** là hệ thống thu thập sự kiện chẩn đoán hiệu năng và hoạt động JVM, hỗ trợ profiler, điều tra CPU, GC, bộ nhớ, thread, exception và sự kiện ứng dụng. Từ **Java 11**, JFR được cung cấp trong OpenJDK theo **JEP 328**; API tiêu chuẩn nằm tại module `jdk.jfr`. Đây là công nghệ **vẫn được sử dụng trên các JDK hiện đại**.

Một recording có thể phát sinh nhiều dữ liệu. Khi chạy dịch vụ dài ngày, ba cấu hình dễ bị nhầm với nhau:

- **Duration (thời lượng):** recording **chạy trong bao lâu** rồi tự dừng?
- **Max age (tuổi tối đa):** JFR **giữ lại dữ liệu đã thu trong bao lâu** trong *disk repository*?
- **Max size (dung lượng tối đa):** JFR **giữ lại bao nhiêu byte dữ liệu** trong *disk repository*?

Đây là **ba trục độc lập**. Duration điều khiển **vòng đời thu thập**; max age và max size điều khiển **cửa sổ dữ liệu được giữ lại**. Việc **lưu file `.jfr`** lại là hoạt động khác, thông qua `dump(Path)`, `setDestination(Path)` hoặc công cụ `jcmd`.

Ví dụ: một recording chạy **2 giờ** nhưng chỉ giữ dữ liệu **15 phút gần nhất** (max age) và **không quá khoảng 100 MiB theo cơ chế chunk** (max size). Nó không tự giữ đủ 2 giờ chỉ vì duration dài. Ngược lại, đặt max age = 1 giờ **không làm recording tự dừng sau 1 giờ**.

Mục tiêu bài học:

1. Cấu hình và đọc lại `setDuration`, `setMaxAge`, `setMaxSize` trên `jdk.jfr.Recording`.
2. Hiểu việc JVM xóa những **chunk cũ** khi giới hạn giữ lại bị vượt.
3. Phân biệt `setToDisk(true)` với lưu file đích; khi nào dữ liệu chỉ nằm trong memory buffer.
4. Dùng `dump` để lấy **snapshot mà recording tiếp tục chạy**.
5. Dùng `setDestination` và duration để tự tạo file khi recording kết thúc.
6. Vận hành qua `jcmd JFR.start/JFR.dump/JFR.stop` và kiểm tra file bằng `jfr summary` hoặc `RecordingFile`.
7. Tránh mất dữ liệu do giới hạn quá thấp, đường dẫn không ghi được, đóng recording sớm hoặc lưu dữ liệu nhạy cảm thiếu kiểm soát.

## 2. Mô hình dữ liệu: buffer, repository và file xuất

Một cách nhìn đơn giản:

```text
Ứng dụng / JVM phát JFR events
            |
            v
     Thread / global buffers
            |
            +-- setToDisk(false) --> giữ trong memory buffers
            |                        (dung lượng hữu hạn)
            |
            +-- setToDisk(true)  --> disk repository (tạm)
                                         |
                                         | maxAge/maxSize
                                         v
                                giữ/xóa các chunk cũ
                                         |
                       +-----------------+------------------+
                       |                                    |
                  dump(Path)                           stop + destination
                  lấy snapshot                         xuất recording cuối
                       |                                    |
                       v                                    v
                snapshot.jfr                          final.jfr
                       |
                       v
           jfr summary / RecordingFile
```

**Disk repository** là kho tạm mà JFR sử dụng khi recording được cấu hình ghi ra đĩa. Nó **không đồng nghĩa** với file `.jfr` mà bạn chủ động lưu để phân tích hoặc chia sẻ.

- **Repository chunks:** JVM quản lý vòng đời, có thể xóa dữ liệu cũ theo `maxAge`/`maxSize` và giải phóng khi recording bị đóng.
- **File dump/final:** file người dùng yêu cầu ở một `Path` cụ thể, có thể giữ lại sau khi recording đóng. Nó cần quản lý retention, quyền truy cập và dung lượng ở **cấp vận hành hệ thống**.
- **Memory-only recording:** dùng `setToDisk(false)`; phần dữ liệu giữ được phụ thuộc memory buffers và có thể mất sự kiện cũ nếu ghi quá nhiều trước khi dump.

**Lưu ý chính:** `maxSize` **không phải quota chính xác cho mọi file `.jfr` đã xuất**, và `maxAge` **không làm file dump cũ tự bị xóa** sau khoảng thời gian đó. Muốn dọn file đã xuất, cần chính sách bên ngoài JFR.

## 3. Duration — thời gian thu thập, không phải tuổi dữ liệu

API Java 11:

```java
import java.time.Duration;
import jdk.jfr.Recording;

Recording recording = new Recording();
recording.setDuration(Duration.ofMinutes(10));
```

Đây là **mảnh mã**; ứng dụng cần `start()`/`close()` phù hợp. `setDuration(Duration)` chỉ định **thời gian chạy recording sau khi bắt đầu**, rồi JFR tự dừng khi hết hạn. Dùng thời lượng dương hợp lý để thu thập sự kiện trong khoảng mong muốn.

Những điểm cần biết:

- `getDuration()` trả `Duration` đã đặt; mặc định **`null`**, nghĩa là **không có thời lượng tự dừng**.
- Đặt duration **trước `start()`** là cách cấu hình rõ ràng, dễ kiểm soát và tương thích.
- Khi đến thời hạn, recording chuyển khỏi trạng thái `RUNNING`; nếu đã có `setDestination(path)`, JFR ghi file và **đóng recording** sau khi copy thành công.
- Một khoảng thời gian chạy dài **không bảo đảm toàn bộ dữ liệu từ đầu** vẫn có trong file cuối, vì `maxAge`/`maxSize` có thể đã loại bỏ chunk cũ.
- **`Thread.sleep(duration)` không thay thế `setDuration`:** sleep chỉ dừng một thread; nó không tự thiết lập chính sách vòng đời cho recording.

### 3.1. Thời lượng và thời điểm bắt đầu

`Recording.start()` bắt đầu ngay. Nếu cần khởi động sau một khoảng trễ:

```java
recording.scheduleStart(Duration.ofSeconds(5));
```

Đây là mảnh mã; `scheduleStart` đặt trạng thái `DELAYED` và yêu cầu recording còn ở trạng thái `NEW`. **Delay** là thời gian chờ **trước khi bắt đầu**, **duration** là thời gian recording hoạt động. Không cộng nhầm hai con số khi ước lượng khoảng quan sát.

Nếu dùng CLI, định dạng thời lượng thường có hậu tố `s`, `m`, `h`, `d` tùy lệnh; API Java nhận `java.time.Duration` và không parse chuỗi `"10m"` trực tiếp.

### 3.2. Khi cần dừng thủ công

```java
try (Recording recording = new Recording()) {
    recording.start();
    // Thực hiện công việc cần quan sát.
    recording.stop();
}
```

`stop()` chỉ hợp lệ khi recording đang chạy; recording đã dừng **không được start lại**. `close()` giải phóng dữ liệu/tài nguyên gắn với recording. Nếu muốn giữ dữ liệu để xuất file, cần `dump` hoặc cấu hình destination **trước khi dữ liệu bị giải phóng**.

## 4. Max age — tuổi tối đa của dữ liệu còn giữ

API:

```java
recording.setMaxAge(Duration.ofMinutes(15));
```

Khi ghi vào **disk repository**, JFR loại bỏ những dữ liệu/chunk cũ vượt quá giới hạn tuổi. Về khái niệm, tại thời điểm hiện tại, nó ưu tiên giữ **cửa sổ gần nhất** thay vì lưu mãi từ lúc bắt đầu.

| Giá trị Java API | Nghĩa |
| --- | --- |
| `setMaxAge(Duration.ofMinutes(15))` | Giữ dữ liệu trong khoảng 15 phút gần đây, phụ thuộc ranh giới chunk và flush |
| `setMaxAge(null)` | **Không giới hạn tuổi** theo maxAge |
| `getMaxAge()` | Trả Duration hiện hành hoặc `null` |

**Không tính retention chính xác từng millisecond.** JFR ghi dữ liệu theo **chunk**, flush định kỳ và xóa/giữ chunk dựa trên cơ chế nội bộ. Một sự kiện sát ranh giới có thể bị giữ hoặc bị loại theo mốc chunk, không phải lời hứa “mọi sự kiện mới hơn 15 phút đều luôn được giữ, mọi sự kiện cũ hơn đều bị cắt chính xác”.

### 4.1. Max age không làm recording tự dừng

```java
recording.setDuration(Duration.ofHours(2));
recording.setMaxAge(Duration.ofMinutes(10));
```

Đây là mảnh mã cấu hình. Recording vẫn có kế hoạch chạy **2 giờ**, nhưng lúc dump ở cuối, tập dữ liệu có thể chỉ gồm **khoảng 10 phút gần nhất** (hoặc ít hơn nếu max size loại thêm chunk).

Nếu cần bản ghi **đủ hai giờ**, đừng đặt max age thấp hơn cửa sổ cần giữ. Nếu cần xem **last 10 minutes liên tục** khi chẩn đoán dịch vụ, max age có ích để hạn chế repository.

### 4.2. Giá trị sai và kỳ vọng sai

- `setMaxAge(Duration.ofSeconds(-1))` không hợp lệ; API ném `IllegalArgumentException`.
- `null` là cách thể hiện không giới hạn tuổi theo Java API; không tự suy ra `Duration.ZERO` luôn có ý nghĩa “tắt giới hạn” cho mọi API/công cụ.
- `maxAge` chủ yếu kiểm soát **disk repository retention**; với `setToDisk(false)`, không nên lấy max age làm cơ chế bảo đảm dữ liệu còn nằm trong bộ nhớ.
- Nếu cần dữ liệu cũ hơn max age đã bị loại, không thể “tăng max age sau đó” để khôi phục sự kiện đã mất.

## 5. Max size — giới hạn lượng dữ liệu giữ trong repository

API:

```java
recording.setMaxSize(64L * 1024 * 1024);
```

`maxSize` có đơn vị **byte** trong Java API. Ví dụ trên là **64 MiB = 67.108.864 byte**. Khi repository vượt giới hạn, JVM **bỏ các chunk cũ** để nhường chỗ cho dữ liệu mới. Nó **không** tự dừng recording.

| Giá trị Java API | Nghĩa |
| --- | --- |
| `setMaxSize(64L * 1024 * 1024)` | Mục tiêu giữ tối đa khoảng 64 MiB theo chunk retention |
| `setMaxSize(0)` | **Không giới hạn dung lượng** theo maxSize |
| `getMaxSize()` | Trả giá trị byte đã cấu hình; `0` là không giới hạn |

Những điều cần nhớ:

1. **Đây không phải giới hạn cứng byte-by-byte.** JFR lưu trong chunk; một chunk đang được tạo hoặc kích thước chunk tối thiểu có thể khiến mức sử dụng tạm thời vượt mức đặt. Không sử dụng `maxSize` làm quota đĩa duy nhất của máy chủ.
2. **Không phải kích thước file dump:** file đích có headers, metadata và tập chunk tùy thời điểm snapshot. Một số thao tác dump có thể tạo kích thước khác với `getSize()` của repository. Không lấy `maxSize=64M` làm lời hứa file luôn `<=64M`.
3. **Không phải RAM limit:** cấu hình memory buffers là nhóm tham số khác, ví dụ `-XX:FlightRecorderOptions=memorysize=...`; `setMaxSize` không giới hạn chính xác RAM mà JFR sử dụng.
4. **Không phải số lượng event:** kích thước event phụ thuộc cấu hình JFR, sampling, stack trace, payload và metadata.
5. **Có thể mất dữ liệu cũ:** nếu tốc độ thu thập cao, max size có thể khiến retention thực tế ngắn hơn max age.

Javadoc nêu rõ `setMaxSize` nhận giá trị âm là không hợp lệ và ném `IllegalArgumentException`. Đặt `0` là không giới hạn size; nếu `maxAge=null` đồng thời, recording ghi disk có thể **tăng kích thước repository không giới hạn theo hai tham số này** cho đến khi gặp các ràng buộc khác. Dịch vụ chạy lâu cần cân nhắc giới hạn phù hợp và giám sát dung lượng đĩa.

### 5.1. Khi cả max age và max size cùng được đặt

```java
recording.setMaxAge(Duration.ofMinutes(10));
recording.setMaxSize(64L * 1024 * 1024);
```

JFR phải tuân thủ **cả hai** hạn mức retention; nếu một trong hai buộc loại bỏ chunk cũ, tập dữ liệu giữ lại có thể nhỏ hơn giới hạn kia. Có thể hiểu thực dụng:

```text
Dữ liệu được giữ ~= phần mới nhất
                    thỏa cửa sổ maxAge
                    VÀ giới hạn maxSize (theo chunk)
```

Ví dụ: phát sinh 100 MiB mỗi phút, max size 64 MiB sẽ làm cửa sổ dữ liệu thực ngắn hơn rất nhiều so với max age 10 phút. Ngược lại, hệ thống rất ít event có thể chỉ dùng 2 MiB dù max size 64 MiB.

**Không thể xác nhận retention thực tế chỉ bằng hai giá trị cấu hình**; phải quan sát kích thước và timestamp của dữ liệu xuất ra.

## 6. Disk hay memory: setToDisk quyết định gì?

`Recording.setToDisk(boolean)` kiểm soát JFR có **liên tục flush dữ liệu vào disk repository** hay chỉ dựa vào memory buffers:

```java
recording.setToDisk(true);   // Ghi dữ liệu vào disk repository.
```

Đối với Java API `new Recording()`, `isToDisk()` **mặc định trả `true`** nếu chưa cấu hình. Tuy nhiên, **đừng suy diễn mọi entry point JFR đều có cùng default**: các cờ JVM và lệnh `jcmd` có thể có giá trị mặc định/điều kiện khác nhau theo công cụ và bản JDK. Với chương trình yêu cầu retention bằng max age/size, hãy **đặt rõ `setToDisk(true)`**.

### 6.1. Chế độ disk=true

- Event được buffer trong memory rồi flush ra **disk repository tạm**.
- `maxAge`/`maxSize` điều khiển retention của dữ liệu trên disk repository.
- `Recording.getSize()` trả kích thước hiện tại trong repository, đo bằng byte, được cập nhật khi buffer được flush.
- `dump(path)` tạo file snapshot từ dữ liệu recording đang còn.
- Sau `stop()`, recording disk-based chưa đóng vẫn có thể dump dữ liệu; `close()` giải phóng dữ liệu tạm.

### 6.2. Chế độ disk=false

```java
recording.setToDisk(false); // Chỉ giữ những gì memory buffers còn chứa.
```

- Không có retention dài hạn trong disk repository; dữ liệu bị giới hạn bởi **bộ đệm trong memory**.
- `getSize()` **trả `0`** theo Java 11 Javadoc, ngay cả khi đã có event trong buffer; đó không phải phép đo “số byte event đã thu”.
- `maxAge`/`maxSize` **không kiểm soát memory buffer** theo cách chúng kiểm soát disk repository.
- Có thể yêu cầu `dump(path)` khi recording **đang chạy** để lấy dữ liệu hiện có, nhưng không bảo đảm tất cả sự kiện kể từ đầu còn tồn tại.
- Đừng giả định recording memory-only đã dừng vẫn có dữ liệu để dump theo mọi phiên bản. Để giữ đủ lịch sử hoặc dump sau stop, dùng `disk=true` hoặc xuất dữ liệu đúng lúc khi vẫn đang chạy.

**Lựa chọn thực tế:** cần “rolling history” cho dịch vụ dài hạn thì thường chọn `disk=true` với retention phù hợp. Cần snapshot ngắn và rất ít disk I/O có thể xem xét memory-only, nhưng phải hiểu rủi ro mất event và giới hạn bộ đệm.

## 7. Lưu file: dump, stop, destination và close khác nhau thế nào?

### 7.1. dump(Path) — xuất snapshot, không dừng recording

```java
Path snapshot = Path.of("snapshot.jfr");
recording.dump(snapshot);
```

`dump(Path)` ghi dữ liệu hiện có ra một file `.jfr`. Với recording đang chạy và có dữ liệu, **dump không có nghĩa stop**. Có thể tiếp tục thu event sau đó và dump một snapshot khác.

Nếu file đích không ghi được, disk đầy, không có quyền hoặc trạng thái recording không phù hợp, lệnh có thể thất bại (`IOException`, `SecurityException` hoặc lỗi trạng thái theo API). Phải kiểm tra thông báo lỗi và không coi đường dẫn file là đã được lưu chỉ vì đã khởi tạo Path.

### 7.2. stop() — ngừng thu; chưa chắc đã có file đích

```java
recording.stop();
```

`stop()` chấm dứt recording đang chạy. **Nếu chưa set destination**, recording có thể ở `STOPPED` và dữ liệu disk repository vẫn có thể được dump trước khi gọi `close()`. **Nếu đã set destination**, `stop()` sẽ ghi dữ liệu đến file đích rồi **tự đóng recording** sau khi copy thành công.

Đừng cho rằng `stop()` đơn thuần luôn tạo `recording.jfr` trong thư mục hiện hành — cần cấu hình `setDestination`, `dump` hoặc công cụ CLI thích hợp.

### 7.3. setDestination(Path) — xuất tự động khi stop

```java
Path finalFile = Path.of("final.jfr");
recording.setDestination(finalFile);
```

Phương thức này thiết lập **đường dẫn ghi file khi recording dừng**, không đồng nghĩa với việc event ngay lập tức được ghi liên tục vào file `final.jfr` trong lúc recording chạy. JFR vẫn quản lý repository/buffers theo cơ chế riêng.

Nếu destination được set, sau khi copy thành công recording **chuyển tới CLOSED**, vì vậy **không** tiếp tục gọi `dump` trên đối tượng đã CLOSED với kỳ vọng đọc lại dữ liệu tạm. File đã xuất nằm ở Path và có thể phân tích độc lập.

`setDestination(null)` có nghĩa không tự dump khi stop. Nếu dùng relative path như `final.jfr`, vị trí thực phụ thuộc **working directory** của process. Đối với dịch vụ thực, nên dùng **đường dẫn tuyệt đối đã kiểm tra quyền**, không ghi bừa vào thư mục nguồn hoặc thư mục public.

### 7.4. close() — giải phóng dữ liệu/tài nguyên

`Recording` triển khai `AutoCloseable`, vì vậy:

```java
try (Recording recording = new Recording()) {
    recording.start();
    // Dump/stop theo đúng chiến lược lưu.
} // recording.close() tự chạy.
```

`close()` giải phóng dữ liệu gắn với recording. Nếu muốn giữ file, **dump hoặc đặt destination trước khi close**. **Không dựa vào close() để tự ghi file nếu chưa cấu hình**. File `.jfr` đã được lưu thành công không bị xóa chỉ vì đối tượng `Recording` được đóng.

### 7.5. setDumpOnExit(boolean)

```java
recording.setDumpOnExit(true);
```

Đây là lựa chọn yêu cầu dump khi JVM kết thúc theo cơ chế JFR. Nó hữu ích cho một số tác vụ chẩn đoán dài hạn, nhưng **không thay thế backup/retention của file**, và không được bảo đảm với mọi kiểu crash, mất điện hoặc kill cưỡng bức.

Nếu muốn file đích xác định, cần kiểm tra kết hợp `setDestination`, quyền ghi và cách JVM dừng. Tránh dựa vào event shutdown trong hệ thống có yêu cầu giữ dữ liệu bắt buộc; dùng periodic snapshots hoặc hệ thống thu thập ngoài process.

## 8. Java API: cấu hình hợp lý trong một recording

Ví dụ cấu hình khái niệm:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

try (Recording recording =
        new Recording(Configuration.getConfiguration("default"))) {

    recording.setName("service-sample");
    recording.setToDisk(true);
    recording.setDuration(Duration.ofMinutes(3));
    recording.setMaxAge(Duration.ofMinutes(2));
    recording.setMaxSize(64L * 1024 * 1024);
    recording.setDestination(Path.of("service-sample.jfr"));

    recording.start();
    // Công việc của ứng dụng chạy ở đây.
    // Nếu không tự stop, recording có thể tự dừng theo duration.
}
```

**Đây là mảnh mã minh họa, không phải chương trình hoàn chỉnh để chạy nguyên xi.** Lưu ý: khi `try-with-resources` kết thúc, `close()` chạy. Nếu công việc ở trong block kết thúc **sớm hơn 3 phút**, recording **bị đóng sớm**, chứ không được bảo đảm sẽ tự chạy đủ 3 phút. Muốn chờ duration hoàn tất, phải giữ vòng đời đối tượng và process đủ lâu hoặc chủ động `stop` khi đã thu đủ dữ liệu. Chương trình ở mục 10 kiểm thử đúng nhánh tự dừng.

`Configuration.getConfiguration("default")` tải cấu hình sự kiện JFR mặc định của JDK. Nếu muốn nhiều event hoặc profile khác, có thể dùng `Configuration.getConfiguration("profile")` nếu JDK cung cấp cấu hình đó và chấp nhận overhead cao hơn. **Duration/age/size không tự bật những loại event chưa được enable.**

### 8.1. Kiểm tra giá trị cấu hình bằng getter

```java
Duration duration = recording.getDuration();
Duration age = recording.getMaxAge();
long bytes = recording.getMaxSize();
boolean disk = recording.isToDisk();
Path destination = recording.getDestination();
long repositoryBytes = recording.getSize();
```

Các getter có ý nghĩa khác nhau:

- `getDuration()` / `getMaxAge()` có thể là `null` khi không giới hạn.
- `getMaxSize() == 0` nghĩa là không giới hạn size.
- `isToDisk()` kiểm tra đường lưu trữ đang chọn.
- `getDestination()` có thể `null` khi không đặt file xuất.
- `getSize()` là **kích thước hiện tại trong disk repository**, cập nhật khi buffer được flush; không phải kích thước tệp đích và không đo RAM của JFR.

Dùng getter để xác minh **cấu hình**, nhưng vẫn phải kiểm tra file và event thật để biết recording chứa gì.

## 9. Điều khiển JFR qua công cụ JDK: java, jcmd, jfr

Các lệnh sau là **mẫu sử dụng dành cho JVM mà bạn có quyền quản trị**. Tên PID, đường dẫn và thời gian là minh họa. Các lệnh trên Windows và Linux có thể khác về dấu phân cách đường dẫn; `jcmd`/`jfr` phải thuộc JDK tương thích với process.

### 9.1. Khởi động JFR ngay khi chạy JVM

Tham số JVM `-XX:StartFlightRecording` có trong Java 11:

```bash
java -XX:StartFlightRecording=name=service,disk=true,duration=60s,maxage=30s,maxsize=64m,filename=service.jfr -cp . MyApplication
```

Đây là **mẫu lệnh**, `MyApplication` là tên class **do ứng dụng cung cấp**, không phải class mẫu có sẵn trong README. Theo tài liệu Java 11:

- `duration=60s`: recording dự kiến chạy 60 giây.
- `maxage=30s`: chỉ giữ cửa sổ dữ liệu gần nhất trong repository.
- `maxsize=64m`: giới hạn retention theo đơn vị mà launcher chấp nhận, **không phải quota chính xác của file cuối**.
- `disk=true`: bật lưu repository disk để giới hạn age/size có ý nghĩa.
- `filename=service.jfr`: vị trí xuất khi recording kết thúc.

**Đừng dùng duration ngắn hơn 60 giây mà kỳ vọng thu đủ nhiều sự kiện hiếm gặp;** chọn độ dài dựa trên mục đích. **Đừng ngầm hiểu `maxage=30s` vẫn có đầy đủ 60 giây dữ liệu**: nó có thể giữ một phần cuối.

Tùy công cụ khởi động, mặc định `disk` có thể khác. Ví dụ tài liệu `java` của Java 11 liệt kê `disk=false` là mặc định cho `-XX:StartFlightRecording`, trong khi Java API `Recording.isToDisk()` mặc định `true`. Vì vậy nên **khai báo `disk=true` minh bạch** khi cần retention trên disk.

### 9.2. Start/dump/stop trên JVM đang chạy bằng jcmd

Khi biết PID của JVM ứng dụng, có thể tạo recording:

```bash
jcmd <PID> JFR.start name=rolling settings=default disk=true maxage=10m maxsize=64m
```

Trong dòng lệnh mẫu, thay `<PID>` bằng PID thực tế; `<PID>` là placeholder **trong tài liệu CLI**, không phải cú pháp gõ nguyên dấu ngoặc nhọn hay redirect shell.

Sau đó lấy snapshot **mà recording vẫn chạy**:

```bash
jcmd <PID> JFR.dump name=rolling filename=rolling-snapshot.jfr
```

Cuối cùng dừng recording khi không cần thu tiếp:

```bash
jcmd <PID> JFR.stop name=rolling
```

**JFR.dump và JFR.stop là hai hành động khác nhau**. Dump để phân tích snapshot **không tự thay thế stop**; stop ngừng tạo dữ liệu mới và giải phóng theo vòng đời recording. Nếu cần file sau stop, hãy đặt filename/destination theo tham số công cụ hoặc dump **trước khi** stop, không dựa vào giả định “stop sẽ tự tạo file”.

`jcmd` hỗ trợ các lệnh `JFR.check`, `JFR.start`, `JFR.dump`, `JFR.stop` trên JDK có JFR. Đầu ra cụ thể/đơn vị được chấp nhận có thể khác giữa các dòng JDK; với process đang chạy, xem:

```bash
jcmd <PID> help JFR.start
jcmd <PID> help JFR.dump
jcmd <PID> JFR.check
```

Việc attach `jcmd` có thể bị ngăn bởi quyền OS/container, attach mechanism hoặc process policy; không xem đó là bằng chứng Java code recording bị lỗi.

### 9.3. Đọc file .jfr bằng jfr command

Sau khi đã có file:

```bash
jfr summary rolling-snapshot.jfr
jfr print --events demo.RetentionEvent rolling-snapshot.jfr
```

`jfr summary` xem thông tin và thống kê số sự kiện; `jfr print` in sự kiện đã chọn. Tên `demo.RetentionEvent` chỉ có trong chương trình demo ở mục 10; với recording ứng dụng thực, hãy chọn tên event hiện có trong file hoặc xem summary trước.

Không đưa toàn bộ output `jfr print` chứa path, thread name, stack trace hoặc thông tin vận hành nhạy cảm lên log công khai.

## 10. Chương trình Java 11 chạy thật: duration, maxAge, maxSize và xuất file

Chương trình dưới đây **biên dịch bằng `javac --release 11`**, không cần thư viện ngoài. Nó tạo một **JFR custom event** để việc kiểm tra không phụ thuộc vào khả năng JVM tình cờ phát GC, JIT hay CPU sampling event.

Chương trình thực hiện hai ca:

**Ca 1 — Manual snapshot và stop:**

- Tạo `Recording`, chọn `disk=true`, `maxAge=10s`, `maxSize=32 MiB`.
- Enable event `demo.RetentionEvent`, phát **3 events**.
- `dump(snapshot.jfr)` khi recording vẫn đang chạy.
- Kiểm tra `RecordingState.RUNNING` ngay sau dump.
- `stop()` rồi `dump(stopped.jfr)` khi dữ liệu disk repository vẫn còn.
- Đọc cả file và kiểm tra đúng **3 custom events**.

**Ca 2 — Duration và destination:**

- Tạo recording mới với `duration=2s` và `setDestination(automatic.jfr)`.
- Phát **1 custom event** khi recording đang chạy.
- Chờ có giới hạn để recording tự kết thúc, chuyển sang `CLOSED` do destination đã được xuất.
- Kiểm tra file có dữ liệu và đúng **1 event**.

Lưu file **`JfrRetentionDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.RecordingState;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrRetentionDemo {
    @Name("demo.RetentionEvent")
    @Label("Retention demo event")
    public static class RetentionEvent extends Event {
        @Label("Sequence")
        public int sequence;
    }

    private static void emit(int sequence) {
        RetentionEvent event = new RetentionEvent();
        event.sequence = sequence;
        event.commit();
    }

    private static long eventCount(Path path) throws Exception {
        List<RecordedEvent> all = RecordingFile.readAllEvents(path);
        return all.stream().filter(e ->
                e.getEventType().getName()
                        .equals("demo.RetentionEvent")).count();
    }

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass output directory");
        }
        Path dir = Path.of(args[0]);
        Files.createDirectories(dir);
        Path snapshot = dir.resolve("snapshot.jfr");
        Path stopped = dir.resolve("stopped.jfr");
        Path automatic = dir.resolve("automatic.jfr");

        try (Recording r = new Recording()) {
            r.setName("bounded-buffer");
            r.setToDisk(true);
            r.setMaxAge(Duration.ofSeconds(10));
            r.setMaxSize(32L * 1024 * 1024);
            r.enable(RetentionEvent.class)
                    .withThreshold(Duration.ZERO);

            check(r.isToDisk()
                    && r.getMaxAge()
                            .equals(Duration.ofSeconds(10))
                    && r.getMaxSize() == 32L * 1024 * 1024,
                    "Unexpected recording retention");

            r.start();
            for (int i = 1; i <= 3; i++) emit(i);

            r.dump(snapshot);
            check(r.getState() == RecordingState.RUNNING,
                    "Dump must not stop a running recording");
            check(Files.size(snapshot) > 0
                            && eventCount(snapshot) == 3,
                    "Snapshot event count mismatch");

            r.stop();
            r.dump(stopped);
            check(Files.size(stopped) > 0
                            && eventCount(stopped) == 3,
                    "Stopped recording event count mismatch");

            System.out.println("disk mode = " + r.isToDisk());
            System.out.println("retention limits = true");
            System.out.println("snapshot saved = true");
            System.out.println("snapshot event count = "
                    + eventCount(snapshot));
            System.out.println(
                    "dump keeps recording running = true");
            System.out.println("stopped file saved = true");
        }

        try (Recording r = new Recording()) {
            r.setName("automatic-stop");
            r.setToDisk(true);
            r.setDuration(Duration.ofSeconds(2));
            r.setDestination(automatic);
            r.enable(RetentionEvent.class)
                    .withThreshold(Duration.ZERO);

            r.start();
            emit(4);

            long deadline = System.nanoTime()
                    + Duration.ofSeconds(7).toNanos();
            while (r.getState() == RecordingState.RUNNING
                    && System.nanoTime() < deadline) {
                Thread.sleep(100);
            }

            check(r.getState() == RecordingState.CLOSED,
                    "Timed recording with destination must close");
            check(Files.size(automatic) > 0
                            && eventCount(automatic) == 1,
                    "Timed destination file mismatch");

            System.out.println("duration auto stop = true");
            System.out.println("destination saved = true");
            System.out.println("destination event count = "
                    + eventCount(automatic));
        }
        System.out.println("ALL CHECKS PASSED");
    }
}
```

**Biên dịch và chạy bằng JDK 11 trở lên:**

```bash
javac --release 11 JfrRetentionDemo.java
java JfrRetentionDemo .
```

Dấu `.` cuối là **thư mục đầu ra hiện tại**. Chạy trong một thư mục test mới và có quyền ghi; chương trình sẽ tạo ba file `snapshot.jfr`, `stopped.jfr` và `automatic.jfr` ở đó. Không chạy trực tiếp trong repository nguồn nếu không muốn thêm file tạm; hãy xóa chúng khi đã kiểm chứng. Nếu JVM không cung cấp module `jdk.jfr` hoặc bị cấu hình chặn JFR, cần dùng một JDK có hỗ trợ JFR.

**Đầu ra đã kiểm chứng bằng biên dịch/chạy thực tế:**

```text
disk mode = true
retention limits = true
snapshot saved = true
snapshot event count = 3
dump keeps recording running = true
stopped file saved = true
duration auto stop = true
destination saved = true
destination event count = 1
ALL CHECKS PASSED
```

### 10.1. Giải thích các kiểm tra

- `disk mode = true`: `setToDisk(true)` có hiệu lực theo `isToDisk()`.
- `retention limits = true`: `getMaxAge() == 10s` và `getMaxSize() == 32 MiB` sau cấu hình. **Đây chỉ là kiểm tra cấu hình**, không tuyên bố đã đẩy repository quá giới hạn.
- `snapshot saved = true`: `Files.size(snapshot) > 0` và `RecordingFile` đọc được event trong file snapshot.
- `snapshot event count = 3`: đúng ba lần `RetentionEvent.commit()` xuất hiện trong snapshot, được lọc theo event type name.
- `dump keeps recording running = true`: ngay sau `dump`, state vẫn là `RUNNING`; snapshot **không phải stop**.
- `stopped file saved = true`: `stop()` rồi `dump(stopped)` thành công với recording disk-based chưa đóng.
- `duration auto stop = true`: ở ca 2, recording với `setDuration(2s)` rời trạng thái RUNNING và tự thành `CLOSED` sau khi ghi destination.
- `destination saved = true` và `destination event count = 1`: file tự xuất tồn tại, `RecordingFile` đọc lại đúng event phát ra.
- `ALL CHECKS PASSED`: các phép kiểm tra thành công. Trong thử nghiệm, `jfr summary snapshot.jfr` cũng xác nhận event type `demo.RetentionEvent` có count **3**.

### 10.2. Thử nghiệm này không chứng minh điều gì?

- Demo **không chờ hơn 10 giây** hay cố tạo trên 32 MiB event, nên **không kiểm thử sự kiện cũ thực tế bị eviction**. Hành vi `maxAge`/`maxSize` trong phần lý thuyết được lấy từ **Javadoc chính thức**.
- Hai file `snapshot.jfr` và `stopped.jfr` có thể chứa cả **JDK events** khác do runtime phát ra. Chương trình chỉ đếm **custom event** theo tên; không giả định tổng số event trong file là 3.
- File `.jfr` có thể chứa metadata và nhiều event types, vì thế **Files.size() không bằng 3 lần kích thước một event**.
- Thời gian thực thi và kích thước file có thể khác theo máy/JDK. Chương trình in các kết luận Boolean và custom count, không in byte size hoặc thời điểm tuyệt đối.
- Với workload thật, cần chọn duration/maxage/maxsize theo volume event, dung lượng đĩa và tình huống phân tích; đừng sao chép 10s/32MiB làm mặc định production.

### 10.3. Kiểm tra file bằng JFR CLI

Sau khi chạy trong thư mục có ba file:

```bash
jfr summary snapshot.jfr
jfr print --events demo.RetentionEvent snapshot.jfr
jfr summary automatic.jfr
```

Khi dùng `jfr print`, chỉ chọn file tin cậy và lưu ý có thể thấy stack trace, thread name hoặc dữ liệu application event. `RecordingFile.readAllEvents` hữu ích cho **file nhỏ**; với file lớn, dùng iterator `RecordingFile` để đọc từng event, tránh load toàn bộ lên heap cùng lúc.

## 11. Mối liên hệ giữa retention, event settings và hiệu năng

**Duration và retention không quyết định loại event nào được ghi.** Danh sách sự kiện, sampling period, stack trace và threshold nằm trong **recording configuration**:

```java
Configuration config =
        Configuration.getConfiguration("default");
Recording recording = new Recording(config);
```

Hoặc chỉ bật event cụ thể như chương trình demo:

```java
recording.enable(RetentionEvent.class)
        .withThreshold(Duration.ZERO);
```

Các mảnh code này cần import tương ứng và đặt trong chương trình hợp lệ.

Nếu cấu hình event dày đặc, có stack trace lớn hoặc ứng dụng phát event custom liên tục:

- Repository có thể đầy nhanh hơn, khiến **maxSize** buộc giữ cửa sổ ngắn hơn.
- File dump có thể tăng và gây disk I/O; giảm duration không giải quyết được nếu event rate quá cao trong khoảng ngắn.
- Memory-only buffers có thể ghi đè hoặc bỏ sự kiện cũ nếu không dump kịp.
- Profiling quá nặng có thể ảnh hưởng tới latency/throughput; dùng `default`/`profile` tùy mục tiêu và đo overhead.

Một chính sách hợp lý phải phối hợp **event settings + duration + age + size + disk + thời điểm dump**.

## 12. Mẫu cấu hình theo tình huống

| Mục tiêu | Duration | Max age | Max size | Disk / lưu file |
| --- | --- | --- | --- | --- |
| Điều tra lỗi xảy ra trong vài phút | Có thể `2m`–`5m` | Ít nhất bằng cửa sổ muốn giữ, nếu cần toàn bộ | Đủ chứa dữ liệu theo event rate | `disk=true`; destination khi dừng |
| Quan sát service dài ngày, chỉ giữ cửa sổ gần đây | Không giới hạn tự dừng hoặc rất dài | Ví dụ `15m` | Ví dụ `128m` | `disk=true`; dump định kỳ/khi có sự cố |
| Lấy snapshot nhanh theo yêu cầu | Recording vẫn chạy | Giữ vài phút gần nhất | Bảo đảm đủ dữ liệu cho phân tích | `JFR.dump`; stop khi không cần |
| Môi trường hạn chế disk I/O | Thường ngắn | Max age không quản lý RAM | Max size không quản lý RAM | `disk=false`; dump khi vẫn chạy, hiểu rủi ro thiếu event |
| Giữ hồ sơ sự cố theo chính sách tuân thủ | Đủ thời gian bao phủ sự cố | Không cho eviction sớm hơn yêu cầu | Tránh giới hạn làm mất dữ liệu bắt buộc | Export file, quyền truy cập, backup và retention hệ thống riêng |

**Các số là ví dụ**, không phải cấu hình chung cho mọi workload. Nếu event production chứa thông tin nhạy cảm hoặc khối lượng lớn, phải xác nhận chính sách trước khi ghi. Đặc biệt, đừng dùng `disk=false` chỉ vì muốn “không ghi file”. JFR có thể cần dump để giữ lại dữ liệu; trong memory-only mode lịch sử có thể biến mất trước khi bạn nhận ra.

### 12.1. Có nên bật đồng thời duration và maxAge?

Có, nếu bạn chủ ý chỉ cần **phần cuối** của một phiên chẩn đoán dài. Ví dụ duration 1 giờ, maxAge 10 phút thích hợp khi chỉ quan tâm trạng thái trước lúc recording dừng. Nhưng nếu điều tra lỗi có thể xảy ra **bất cứ lúc nào trong 1 giờ**, retention 10 phút có nguy cơ xóa mất bằng chứng của lỗi xảy ra sớm.

### 12.2. Có nên đặt maxSize rất nhỏ?

Không nên đặt thấp hơn kích thước chunk thực tế mà JFR sử dụng. Theo tài liệu launcher Java 11, `maxsize` dùng với `-XX:StartFlightRecording` không được nhỏ hơn `maxchunksize`. Vì cơ chế lưu theo chunk, size quá nhỏ có thể gây lỗi cấu hình hoặc không đạt kỳ vọng retention. Dùng giá trị đủ lớn, kiểm tra với runtime thật và giám sát disk usage.

### 12.3. Nhiều recordings trong cùng JVM

JFR có thể cho phép **nhiều recordings** với cấu hình và vòng đời riêng. Không nên cộng các số `maxSize` của từng recording rồi xem đó là quota tổng JVM/OS được bảo đảm: repository có thể chia sẻ dữ liệu/chunk giữa các recordings, và overhead/metadata/tệp dump còn tiêu thụ thêm disk. **Giám sát dung lượng ổ đĩa thực tế và giới hạn hệ thống** là trách nhiệm của vận hành.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Recording chạy mãi | `setDuration(null)` hoặc chưa đặt duration | Đặt duration khi muốn tự dừng; hoặc gọi `stop()` thủ công |
| Recording dừng nhưng không thấy file | Không `setDestination` và không `dump` | Đặt file đích trước stop hoặc dump khi còn dữ liệu |
| Dùng `close()` rồi mới dump | Dữ liệu gắn với recording đã bị giải phóng | Dump trước close; dùng try-with-resources đúng thứ tự |
| `dump()` xong tưởng recording đã dừng | Dump chỉ lấy snapshot | Kiểm tra `Recording.getState()`, gọi `stop()` khi muốn kết thúc |
| File dump chỉ có phần cuối | `maxAge`/`maxSize` đã loại chunk cũ | Tăng hạn mức hoặc snapshot sớm hơn |
| Repository vẫn tăng dù đã đặt duration | Recording chưa kết thúc hoặc có recording khác | Kiểm tra state, danh sách recordings và disk usage |
| File `.jfr` lớn hơn số maxSize dự tính | MaxSize là retention repository theo chunk, file dump không phải quota chính xác | Kiểm tra `Files.size()`, `jfr summary` và giới hạn disk |
| Không còn dữ liệu cũ sau tăng maxAge | Chunk đã bị xóa trước đó | Không thể khôi phục bằng cách thay cấu hình; cần dump/backup sớm |
| `getSize() == 0` trong memory-only mode | API chỉ báo kích thước disk repository | Dùng `RecordingFile` kiểm tra snapshot, không dùng getSize đo memory |
| Không thấy event mong muốn | Event chưa bật, threshold cao, sampling hoặc thời gian không đủ | Kiểm tra `Configuration`, `enable`, time window và `jfr summary` |
| File không ghi được | Sai path, thiếu quyền, ổ đĩa đầy, destination directory không có | Tạo directory, kiểm tra path/quyền và `IOException` |
| `IllegalArgumentException` khi đặt age/size | Duration âm hoặc maxSize âm | Dùng Duration không âm và maxSize `>=0` theo API |
| `IllegalStateException` khi start lại | Recording đã STOPPED/CLOSED | Tạo một `Recording` mới |
| Dùng `Thread.sleep` để “hẹn giờ tự dừng” | Sleep chỉ tạm dừng thread của ứng dụng | Dùng `setDuration`/`stop`, quản lý vòng đời rõ |
| Script jcmd không attach được | Thiếu quyền hoặc chính sách attach OS/container | Xác minh PID, user, JDK tools, attach policy |
| Dùng memory-only nhưng cần toàn bộ lịch sử | Buffer có thể ghi đè dữ liệu cũ | `disk=true` và retention đủ lớn |
| Ghi file vào thư mục không được bảo vệ | JFR có thể chứa dữ liệu vận hành nhạy cảm | Lưu trong thư mục hạn chế quyền; mã hóa/retention theo policy |
| Đọc file JFR lớn bằng `readAllEvents` gây thiếu heap | Hàm nạp toàn bộ event vào List | Dùng `RecordingFile` đọc tuần tự từng event |

## 14. An toàn dữ liệu và chính sách vận hành

JFR có thể lưu dữ liệu nhạy cảm như **tên class/method, call stack, đường dẫn file, thread name, thông tin runtime, hostname hoặc event fields do ứng dụng chủ động ghi**. Vì vậy:

1. **Dùng thư mục xuất an toàn:** chọn đường dẫn nằm ngoài thư mục web public, giới hạn quyền đọc/ghi theo user vận hành.
2. **Không in credential/secrets vào custom events:** tránh đưa token, mật khẩu, nội dung PII hay payload nguyên văn vào trường JFR; redact ngay ở nguồn sự kiện nếu cần.
3. **Thiết kế retention bên ngoài repository:** dọn/rotate/archive những file `.jfr` đã dump, vì `maxAge` không tự xóa các file này.
4. **Giới hạn dung lượng ở tầng OS/container:** JFR `maxSize` không thay thế filesystem quota, disk usage alert hoặc volume retention.
5. **Bảo vệ kênh gửi file:** nếu upload `.jfr` cho hệ thống chẩn đoán, dùng kênh được xác thực/mã hóa và giới hạn chia sẻ.
6. **Kiểm thử dưới tải thực:** tốc độ event phát sinh và chunk size thay đổi theo workload/JDK/settings; cần quan sát mức dùng disk thực tế.
7. **Không dựa tuyệt đối vào dumponexit:** crash, kill cưỡng bức hay mất điện có thể ngăn file được xuất; snapshot định kỳ giúp giảm rủi ro mất lịch sử.
8. **Giữ tương thích JDK:** sử dụng API `jdk.jfr` có từ Java 11, xác minh `jcmd`/`jfr` của JDK đang triển khai và ưu tiên cập nhật bảo mật.

## 15. Câu hỏi tự kiểm tra

**1.** `setDuration(Duration.ofMinutes(5))` có nghĩa “chỉ giữ 5 phút gần nhất” không?  
**Đáp án:** Không. Nó điều khiển recording chạy **5 phút** rồi dừng. Retention trong repository do maxAge/maxSize quyết định.

**2.** `setMaxAge(Duration.ofMinutes(10))` có tự dừng recording sau 10 phút không?  
**Đáp án:** Không. Nó chủ yếu giới hạn **tuổi dữ liệu giữ trong disk repository**, recording có thể tiếp tục chạy.

**3.** `setMaxSize(64L * 1024 * 1024)` có bảo đảm mọi file dump luôn nhỏ hơn chính xác 64 MiB không?  
**Đáp án:** Không. Retention dựa trên **chunk**; file export và dung lượng hệ thống không bị chặn tuyệt đối bởi con số này.

**4.** Làm sao đặt không giới hạn tuổi và kích thước theo Java API?  
**Đáp án:** `setMaxAge(null)` và `setMaxSize(0)`. Nhưng phải giám sát dung lượng nếu recording ghi disk chạy dài ngày.

**5.** `setToDisk(false)` thì `maxAge` và `maxSize` có quản lý memory buffers không?  
**Đáp án:** Không theo cơ chế disk repository. `getSize()` trả 0 và dữ liệu phụ thuộc memory buffers có giới hạn.

**6.** `dump(snapshot)` có ngừng recording đang RUNNING không?  
**Đáp án:** Không. Demo chứng minh state vẫn là RUNNING sau khi lấy snapshot.

**7.** `stop()` lúc chưa có destination có bảo đảm đã tạo file `.jfr` không?  
**Đáp án:** Không. Cần `dump(Path)` lúc dữ liệu còn hoặc `setDestination(Path)` trước khi dừng.

**8.** Vì sao recording có `setDuration(2s)` và `setDestination(path)` lại chuyển sang CLOSED sau khi hết hạn?  
**Đáp án:** Duration gây tự dừng; destination khiến JFR xuất file và tự đóng sau khi copy thành công.

**9.** JFR dùng disk repository nhưng `getSize()` bằng 0 ngay sau start có nhất thiết là không có event không?  
**Đáp án:** Không. Giá trị kích thước được cập nhật khi buffers được flush; nên kiểm tra file dump và event thực thay vì chỉ xem getSize.

**10.** Tại sao file snapshot có 3 custom events nhưng tổng event đếm bằng `jfr summary` có thể nhiều hơn 3?  
**Đáp án:** JFR/JDK cũng có thể phát sự kiện khác. Demo chỉ lọc theo `demo.RetentionEvent`.

**11.** Muốn lấy snapshot của một recording đang chạy qua `jcmd` thì dùng lệnh nào?  
**Đáp án:** `jcmd PID JFR.dump name=rolling filename=rolling-snapshot.jfr`; khi cần ngừng mới dùng `JFR.stop`.

**12.** Nếu maxAge là 15 phút, duration là 1 giờ và maxSize rất nhỏ, dữ liệu cuối chắc đủ 15 phút không?  
**Đáp án:** Không. Giới hạn size có thể khiến dữ liệu bị loại còn sớm hơn, tùy tốc độ event và kích thước chunk.

## 16. Tóm tắt

```text
setDuration(Duration)    = recording chạy bao lâu, rồi tự dừng
setMaxAge(Duration)      = tuổi tối đa của dữ liệu trong disk repository
setMaxSize(long bytes)   = dung lượng giữ lại trong disk repository
setToDisk(true/false)    = disk repository hay memory-only buffers

dump(Path)               = xuất snapshot; không tự stop
stop()                   = ngừng recording
setDestination(Path)     = file được ghi khi recording stop
close()                  = giải phóng dữ liệu/tài nguyên của recording
getSize()                = dung lượng repository, KHÔNG là dung lượng file dump
```

Nếu cần một recording dài hạn có rolling history, hãy kết hợp **disk=true**, **maxAge**, **maxSize** và các snapshot khi cần. Nếu cần tạo báo cáo đo đạc ngắn, dùng **duration + destination** hoặc chủ động **stop + dump**. Luôn xác minh **file được ghi thật và chứa event cần thiết**, và bảo vệ file `.jfr` theo chính sách bảo mật và retention của ứng dụng.

### Tài liệu chính thức còn áp dụng

- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328)
- [Java SE 11 — jdk.jfr.Recording: setDuration, setMaxAge, setMaxSize, setToDisk, dump, setDestination](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Java SE 11 — jdk.jfr.RecordingState](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/RecordingState.html)
- [Java SE 11 — jdk.jfr.Configuration](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Configuration.html)
- [Java SE 11 — jdk.jfr.Event, custom event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Java SE 11 — jdk.jfr.consumer.RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Java SE 11 — java launcher: -XX:StartFlightRecording, maxage/maxsize/duration/disk](https://docs.oracle.com/en/java/javase/11/tools/java.html)
- [Java SE 11 — jcmd: JFR.start, JFR.dump, JFR.stop](https://docs.oracle.com/en/java/javase/11/tools/jcmd.html)
- [Java SE 25 — jdk.jfr.Recording API hiện hành](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html)
