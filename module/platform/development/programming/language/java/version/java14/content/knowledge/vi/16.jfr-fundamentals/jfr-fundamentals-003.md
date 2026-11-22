# Recording, repository và các khối dữ liệu trên đĩa trong Java Flight Recorder (JFR)

## 1. Bức tranh tổng thể

**Java Flight Recorder (JFR)** là hệ thống ghi nhận sự kiện chẩn đoán hiệu năng và hành vi JVM với chi phí thu thập tương đối thấp. Một **recording** là phiên ghi nhận có cấu hình, thời điểm bắt đầu/kết thúc và chính sách giữ dữ liệu. Một **repository** là nơi JFR sử dụng để lưu tạm dữ liệu trên đĩa. Dữ liệu trong repository được tổ chức thành các **chunk** (khối dữ liệu), thay vì mặc định được lưu ngay vào một file `.jfr` duy nhất do người dùng đặt tên.

Ba khái niệm dễ bị lẫn:

- **Recording:** phạm vi logic của việc thu thập; có thể bật/tắt sự kiện, giới hạn lịch sử, chọn ghi ra đĩa hay chỉ dùng buffer bộ nhớ, dừng và xuất dữ liệu.
- **Repository:** khu vực lưu trữ **tạm thời** do JFR quản lý khi thu thập ra đĩa. Không nên coi đó là thư mục archive lâu dài, càng không nên tự ý xóa các file đang được JVM sử dụng.
- **Chunk:** đơn vị dữ liệu JFR trên đĩa, có thông tin cần thiết để công cụ JFR phân tích. Một file recording `.jfr` được xuất có thể gồm nhiều chunk được nối theo thứ tự thời gian.

Luồng khái niệm:

~~~text
Ứng dụng/JVM phát sinh các JFR events
                 |
                 v
           Bộ đệm JFR
      (thread/global buffers)
                 |
          +------+------+
          |             |
    disk=true       disk=false
          |             |
          v             v
 Repository tạm     Dữ liệu trong
  chứa các chunk    bộ đệm bộ nhớ
          |             |
          +------+------+
                 |
          Khi dump/xuất
                 |
                 v
        file recording .jfr
                 |
                 v
     jfr summary/print, JMC
~~~

Đây là mô hình học tập, không phải cam kết rằng mọi event được đồng bộ ghi ngay vào file tại đúng thời điểm phát sinh: buffer, hoạt động flush và chunk rotation ảnh hưởng thời điểm dữ liệu xuất hiện trên đĩa. **`disk=false` không đồng nghĩa JFR không hoạt động**; khi đó lịch sử khả dụng bị giới hạn bởi bộ đệm bộ nhớ.

**Tính hiện hành:** JFR là một phần của OpenJDK/JDK hiện đại; `jdk.jfr.Recording` và các công cụ `jcmd`, `jfr` được dùng ổn định trong Java 17 trở đi. Bài này chỉ trình bày các API và cách vận hành còn áp dụng, không sử dụng yêu cầu mở khóa thương mại của các JDK/JFR đời cũ.

## 2. Recording là gì trong API Java?

Lớp `jdk.jfr.Recording` cung cấp API cấu hình và quản lý một phiên ghi. Có thể tạo recording từ cấu hình định sẵn:

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

Recording recording =
        new Recording(Configuration.getConfiguration("default"));
~~~

Đây là **đoạn mã minh họa** đặt trong một phương thức khai báo hoặc xử lý ngoại lệ được báo bởi API. Cấu hình `default` phù hợp cho quan sát liên tục thông thường; `profile` có thể bật nhiều loại dữ liệu hơn để phân tích sâu, nhưng cần cân nhắc chi phí và khối lượng dữ liệu.

Một vòng đời điển hình:

~~~text
NEW --start()--> RUNNING --stop()--> STOPPED --close()--> CLOSED
                       |                  |
                       +------dump()------+
                              (xuất .jfr)
~~~

- **`NEW`:** recording được tạo và có thể được cấu hình.
- **`RUNNING`:** thu thập dữ liệu theo các event settings của recording.
- **`STOPPED`:** dừng ghi sự kiện mới; vẫn có thể xuất dữ liệu còn được giữ lại nếu recording chưa bị đóng.
- **`CLOSED`:** giải phóng dữ liệu và tài nguyên gắn với recording. Sau khi đóng không thể dùng đối tượng đó để dump.
- **`DELAYED`:** trạng thái có thể xuất hiện nếu sử dụng `scheduleStart(Duration)`; không phải mọi ứng dụng đều cần nó.

**Phân biệt `stop()`, `dump(Path)` và `close()`:**

1. `stop()` dừng recording; một recording đã dừng **không thể khởi động lại**. Nếu đã thiết lập destination qua `setDestination(Path)`, dữ liệu được viết ra destination và recording được đóng theo hợp đồng API.
2. `dump(Path)` ghi dữ liệu khả dụng ra một file `.jfr`; recording cần đã được bắt đầu nhưng **không nhất thiết đã dừng**. Đây là cách lấy một bản chụp trong lúc vẫn đang ghi.
3. `close()` giải phóng dữ liệu gắn với recording. Đừng gọi `close()` trước khi dump dữ liệu mà bạn cần giữ lại.
4. `setDestination(Path)` đặt **đích xuất file khi stop**, **khác** với thư mục repository tạm. Đừng nghĩ rằng việc đặt destination sẽ chuyển toàn bộ quá trình ghi chunk sang đó.

Nếu chỉ gọi `stop()` mà không đặt destination hay không tự `dump()`, **đừng kỳ vọng tự nhiên xuất hiện file `.jfr` với tên bạn mong muốn**. Việc recording dữ liệu lên repository tạm không tự thay thế cho xuất bản ghi.

## 3. Disk repository dùng để làm gì?

Repository là nơi JVM/JFR quản lý các file tạm chứa dữ liệu đã được flush trong quá trình thu thập có ghi đĩa. Vị trí mặc định thường dựa trên **thư mục tạm của hệ thống**; có thể cấu hình vị trí khác khi khởi động JVM bằng tùy chọn được JDK hỗ trợ.

Điểm quan trọng:

- Repository không phải lúc nào cũng là một thư mục chứa một file `.jfr` duy nhất tương ứng với một recording.
- Các file tạm/chunk do JFR quản lý có thể có cách đặt tên, thư mục con và vòng đời phụ thuộc phiên bản, trạng thái JVM và cấu hình. **Không viết code ứng dụng phụ thuộc vào tên file nội bộ của repository**.
- Các recording đồng thời có thể dùng hạ tầng thu thập chung của JVM; không nên giả định mỗi recording sở hữu độc quyền một hệ thống chunk riêng biệt hoặc có thể copy nguyên một file tạm để được chính xác dữ liệu của recording đó.
- Repository có thể chứa dữ liệu đang còn được sử dụng. **Không xóa, sửa, nén, đổi tên hay di chuyển thủ công các chunk của một JVM đang chạy**.
- Khi cần file dùng để phân tích/chia sẻ, hãy xuất bằng `Recording.dump(...)` hoặc `jcmd ... JFR.dump`. File `.jfr` đã dump là một artifact khác với các file tạm phục vụ vận hành.

### Chọn thư mục repository

Ví dụ minh họa cách cấu hình lúc chạy ứng dụng (trên hệ thống có thư mục `/var/tmp/jfr-repository` đã tạo, có quyền ghi):

~~~bash
java -XX:FlightRecorderOptions=repository=/var/tmp/jfr-repository -XX:StartFlightRecording=name=service,disk=true,settings=default,maxage=1h,maxsize=128m -jar my-app.jar
~~~

Lệnh này là **mẫu triển khai**, không phải lệnh chạy được nếu chưa có `my-app.jar` và thư mục tương ứng. Các tham số đáng chú ý:

- `-XX:FlightRecorderOptions=repository=...`: chỉ định **vị trí lưu tạm** cho repository.
- `-XX:StartFlightRecording=...`: yêu cầu JVM bắt đầu một recording khi khởi chạy.
- `disk=true`: cho phép ghi dữ liệu ra repository trên đĩa trong khi recording đang diễn ra.
- `maxage=1h` và `maxsize=128m`: giới hạn lịch sử và dung lượng dữ liệu được giữ, thay vì để một recording chạy dài không giới hạn.
- `settings=default`: dùng cấu hình thu thập sự kiện mặc định.

Đường dẫn ở trên chỉ là ví dụ POSIX/Linux. Trong môi trường container, cần chọn volume thích hợp và chính sách disk/quota phù hợp. Đừng đặt repository vào thư mục mà hệ thống quét/xóa file tạm quá tích cực trong khi ứng dụng đang chạy.

### Repository khác destination thế nào?

| Tiêu chí | JFR repository | Dump/destination `.jfr` |
|---|---|---|
| Mục đích | Lưu tạm chunk khi recording dùng đĩa | Đầu ra để phân tích, lưu trữ hay chuyển giao |
| Quản lý | JVM/JFR | Ứng dụng hoặc người vận hành sở hữu file đầu ra |
| Thời điểm tạo | Trong tiến trình thu thập/flush | Khi dump, khi recording stop với destination, hoặc theo chính sách dump-on-exit |
| Thời hạn tồn tại | Phụ thuộc JVM, recordings, retention, cleanup | Theo chính sách lưu giữ artifact của ứng dụng |
| Nên đọc trực tiếp? | Chỉ khi có nhiệm vụ phục hồi đặc biệt và hiểu rõ trạng thái chunk | Có: dùng `jfr`, JDK Mission Control hoặc JFR consumer API |
| Có phải cùng một file? | **Không** | **Không** |

Một recording có thể dùng repository trong một khoảng thời gian dài và tạo ra nhiều bản dump khác nhau mà không cần dừng recording.

## 4. Chunk là gì và vì sao JFR chia nhỏ dữ liệu?

JFR không nhất thiết giữ mọi event trong một file khổng lồ đang mở. Dữ liệu trên đĩa được chia thành **chunk**:

- Mỗi chunk chứa thông tin để công cụ JFR có thể đọc, phân tích; trong các chunk có dữ liệu sự kiện, thông tin metadata và những cấu trúc phục vụ giải mã.
- Các chunk được hoàn tất/luân chuyển theo quá trình ghi; kích thước và tần suất luân chuyển tùy workload và cấu hình JVM.
- Một recording được xuất thành file `.jfr` có thể chứa **nhiều chunk**, không phải chỉ một.
- Không nhất thiết mọi event nằm đúng thứ tự thời gian hiển thị theo từng dòng: công cụ phân tích có thể dùng timestamp để dựng lại tiến trình; việc thu thập đến từ nhiều thread/buffer.

**Không đoán kích thước chunk từ dung lượng dump.** JFR có tùy chọn `maxchunksize` ở mức cấu hình Flight Recorder; giá trị mặc định và giới hạn chi tiết phụ thuộc JDK. Ví dụ một số tài liệu JDK 17 mô tả mặc định cỡ **12 MB** cho `maxchunksize`, nhưng đây **không phải bảo đảm** mọi chunk sẽ có đúng 12 MB hay mọi file dump sẽ có kích thước là bội số của 12 MB.

### Vì sao chia chunk hữu ích?

1. **Quản lý retention:** khi recording vượt một ngưỡng dung lượng, JFR có thể bỏ các chunk cũ để dành chỗ cho dữ liệu mới.
2. **Hạn chế dữ liệu cần xử lý cùng lúc:** công cụ có thể làm việc với các khối dữ liệu riêng.
3. **Phục hồi sự cố:** các chunk đã hoàn tất có thể còn khả dụng sau khi JVM gặp sự cố, dù không phải toàn bộ dữ liệu gần nhất đều được ghi xuống đĩa.
4. **Tách lưu trữ tạm và xuất file:** JFR có thể quản lý chunk trong repository và tạo bản dump mà không yêu cầu người dùng tự nối file.

Hãy coi chunk là **đơn vị lưu trữ của JFR**, không phải một file log văn bản chứa từng sự kiện thành dòng. Không dùng `cat` hay trình biên tập văn bản để phân tích nội dung nhị phân của chunk.

## 5. disk=true so với disk=false

JFR có hai chế độ lưu dữ liệu với ý nghĩa vận hành khác nhau:

| Thuộc tính | `disk=true` | `disk=false` |
|---|---|---|
| Nơi giữ dữ liệu | Bộ đệm và repository trên đĩa | Giới hạn theo bộ đệm trong bộ nhớ |
| Khả năng giữ lịch sử dài | Phù hợp hơn khi thiết lập retention | Giới hạn bởi bộ đệm, dữ liệu cũ có thể bị ghi đè |
| Chi phí I/O | Có hoạt động ghi đĩa | Tránh hoạt động ghi dữ liệu recording thường xuyên lên disk repository |
| Khả năng lấy dữ liệu khi cần | Có thể dump dữ liệu còn được giữ | Có thể dump dữ liệu còn khả dụng trong bộ đệm; lịch sử có thể ngắn |
| `Recording.getStream(...)` | Có thể tạo stream cho khoảng thời gian có dữ liệu | API trả `null` nếu recording không dùng đĩa |
| Trường hợp dùng | Ghi liên tục, chẩn đoán cần lịch sử | Quan sát ngắn hạn/đệm vòng khi không muốn ghi disk thường xuyên |

Trên `jdk.jfr.Recording`:

~~~java
recording.setToDisk(true);
boolean usingDisk = recording.isToDisk();
~~~

Đây là đoạn minh họa với đối tượng `Recording recording` đã khởi tạo. Theo API Java 17, nếu không cấu hình khác, recording mặc định **dùng đĩa** (`isToDisk()` trả `true`). Tuy vậy, nên cấu hình tường minh để reviewer hiểu nhu cầu lưu lịch sử.

**Quan trọng:** `disk=false` không có nghĩa “giữ mọi sự kiện trong RAM vô hạn”. Buffer có giới hạn; khi dữ liệu mới đến, lịch sử cũ có thể không còn. `disk=true` cũng không tự bảo đảm không mất sự kiện dưới mọi điều kiện: áp lực cao, giới hạn buffer, disk full hoặc I/O chậm có thể khiến dữ liệu bị thiếu.

## 6. Giới hạn retention: maxAge, maxSize và chunk rotation

Một recording chạy lâu với `disk=true` cần có chính sách giữ dữ liệu. Hai thiết lập chính:

~~~java
recording.setMaxAge(java.time.Duration.ofMinutes(30));
recording.setMaxSize(128L * 1024 * 1024);
~~~

Đây là đoạn Java trong ngữ cảnh có `Recording recording`:

- `setMaxAge(Duration)` giới hạn **khoảng thời gian lịch sử** được giữ trong disk repository cho recording.
- `setMaxSize(long)` giới hạn **lượng byte dữ liệu** được giữ trong repository cho recording.
- Khi vượt giới hạn, JFR có thể bỏ các **chunk cũ nhất**, thay vì xóa ngẫu nhiên từng event riêng lẻ.
- Nếu không đặt giới hạn tuổi hoặc kích thước, lịch sử lưu trên đĩa có thể **tăng vô hạn về mặt cấu hình**, cho đến khi chạm giới hạn môi trường hoặc gặp vấn đề vận hành.
- Việc giữ dữ liệu phụ thuộc chunk; giới hạn tuổi/kích thước không nên được hiểu là “mọi thời điểm đều chính xác tuyệt đối từng byte và từng mili giây”.
- Giới hạn liên quan đến lịch sử **đang được recording giữ**, không phải cơ chế tự động đặt hạn sử dụng cho file `.jfr` đã dump và nằm tại một thư mục lưu trữ của người dùng.

### Hai tham số có tên gần giống nhưng chức năng khác

- **`maxsize` của recording:** tổng lượng dữ liệu mà recording muốn giữ (tùy cơ chế retention).
- **`maxchunksize` của Flight Recorder:** kích thước tối đa cấu hình cho từng chunk trong hạ tầng ghi.

Không nên lấy `maxsize` để suy ra kích thước của một chunk hoặc dùng `maxchunksize` làm giới hạn dung lượng tổng của toàn repository.

Ví dụ chiến lược vận hành: giữ **1 giờ gần nhất** và đặt ngân sách **128 MB** cho một recording liên tục. Khi sự cố xảy ra, dump dữ liệu còn được giữ lại để phân tích. Nếu tiến trình sinh sự kiện với tốc độ rất cao, ranh giới tuổi và kích thước sẽ ảnh hưởng lượng lịch sử thực tế có thể phục hồi.

## 7. Java 17+ runnable: recording ra đĩa, dump và đọc lại

Ví dụ sau tạo **ba custom JFR events** đã được bật tường minh, ghi recording theo chế độ disk, xuất thành `jfr-pulse-demo.jfr`, rồi dùng `jdk.jfr.consumer.RecordingFile` đọc lại để đếm những sự kiện vừa ghi.

Chạy trong một thư mục mới, có quyền ghi, với JDK hỗ trợ JFR. Tạo file **`JfrDiskRepositoryDemo.java`**:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

public class JfrDiskRepositoryDemo {
    @Name("demo.Pulse")
    @Label("Pulse")
    static class Pulse extends Event {
        @Label("Sequence")
        int sequence;
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of("jfr-pulse-demo.jfr");

        try (Recording recording = new Recording()) {
            recording.setName("jfr-pulse-demo");
            recording.setToDisk(true);
            recording.setMaxAge(Duration.ofMinutes(10));
            recording.setMaxSize(64L * 1024 * 1024);
            recording.enable(Pulse.class)
                    .withThreshold(Duration.ZERO)
                    .withoutStackTrace();

            recording.start();
            for (int i = 1; i <= 3; i++) {
                Pulse pulse = new Pulse();
                pulse.sequence = i;
                pulse.commit();
            }
            recording.stop();
            recording.dump(file);

            long pulseCount = RecordingFile.readAllEvents(file).stream()
                    .filter(event -> event.getEventType().getName()
                            .equals("demo.Pulse"))
                    .count();

            System.out.println("toDisk=" + recording.isToDisk());
            System.out.println("events=" + pulseCount);
            System.out.println("file=" + file.getFileName());
            System.out.println("bytesPositive=" + (Files.size(file) > 0));
        }
    }
}
~~~

Biên dịch và chạy (đã kiểm tra thực tế với compiler hỗ trợ `--release 17`):

~~~bash
javac --release 17 JfrDiskRepositoryDemo.java
java JfrDiskRepositoryDemo
~~~

**Standard output của chương trình:**

~~~text
toDisk=true
events=3
file=jfr-pulse-demo.jfr
bytesPositive=true
~~~

**Giải thích:**

1. `Recording` được tạo từ API `jdk.jfr`. `setToDisk(true)` cho biết recording sử dụng repository trên đĩa.
2. `setMaxAge` và `setMaxSize` hạn chế lượng dữ liệu lịch sử được lưu giữ trong repository.
3. `enable(Pulse.class).withThreshold(Duration.ZERO)` bật sự kiện tùy biến và không áp ngưỡng thời gian dương; ba lần `commit()` tạo ba sự kiện `demo.Pulse`.
4. `stop()` ngừng thu thập. `dump(file)` sau khi dừng xuất dữ liệu thành **file `.jfr` do chương trình đặt tên**, độc lập với đường dẫn repository nội bộ.
5. `RecordingFile.readAllEvents(file)` đọc file đã dump và lọc riêng các event có tên `demo.Pulse`. Trong ví dụ có đúng ba event đó.
6. `Files.size(file) > 0` xác nhận file được ghi dữ liệu; nhưng kích thước cụ thể, số chunk, metadata và các event JVM nền **không cố định**, nên chương trình chỉ in Boolean ổn định.
7. `try-with-resources` gọi `close()` khi thoát block. File dump vẫn tồn tại trong thư mục làm việc vì nó là artifact đã xuất, không phải tài nguyên repository của `Recording`.

Ví dụ đã được biên dịch với `--release 17` và chạy thành công trong môi trường JDK hiện đại có JFR; kết quả ngoài thực tế vẫn phụ thuộc quyền ghi và hỗ trợ JFR của JVM.

### Kiểm tra file sau khi chạy

~~~bash
jfr summary jfr-pulse-demo.jfr
jfr print --events demo.Pulse jfr-pulse-demo.jfr
~~~

Hai lệnh dùng **công cụ `jfr` có sẵn trong JDK**, được chạy bên ngoài chương trình. `jfr summary` hiển thị thông tin tổng quan như số chunk và số lượng event theo loại; `jfr print` lọc các event `demo.Pulse`. **Không đưa một output cố định cho hai lệnh này** vì các timestamp, độ dài recording, metadata và những sự kiện bổ sung khác có thể khác nhau giữa các lần chạy.

## 8. Dùng jcmd với JVM đang chạy

Không phải lúc nào cũng có thể sửa mã ứng dụng để dùng `jdk.jfr.Recording`. Công cụ `jcmd` cho phép quản trị JFR của một tiến trình JVM đang chạy (khi attach được và có quyền phù hợp).

### Bắt đầu và lấy bản dump không dừng recording

Đầu tiên xác định PID Java:

~~~bash
jcmd -l
~~~

Thay `<PID>` dưới đây bằng PID thật:

~~~bash
jcmd <PID> JFR.start name=service-diagnostics settings=default disk=true maxage=1h maxsize=128m
jcmd <PID> JFR.check
jcmd <PID> JFR.dump name=service-diagnostics filename=/var/tmp/service-diagnostics.jfr
jcmd <PID> JFR.stop name=service-diagnostics
~~~

Đây là **chuỗi lệnh minh họa dành cho JVM đã chạy**, không phải chương trình độc lập. File `/var/tmp/service-diagnostics.jfr` là **đích xuất bản ghi**, không phải repository. Bạn phải có quyền ghi vào thư mục đó.

Ý nghĩa từng lệnh:

1. `JFR.start` tạo phiên ghi tên `service-diagnostics`, cho phép ghi lên đĩa và giới hạn lịch sử.
2. `JFR.check` hiển thị thông tin về các recording đang hoạt động.
3. `JFR.dump` xuất dữ liệu còn giữ được thành file mà **không bắt buộc dừng** recording. Vì vậy có thể dùng lệnh này để lấy snapshot khi ứng dụng vẫn phục vụ traffic.
4. `JFR.stop` dừng recording; sau đó chính recording ấy không tiếp tục thu thập nữa.

Dùng `jcmd <PID> help JFR.start` và `jcmd <PID> help JFR.dump` để xem cú pháp chính xác do JVM mục tiêu hỗ trợ. Khả năng attach và tên tùy chọn có thể khác theo môi trường/JDK vendor.

### Khi nào nên dump mà không stop?

Nếu hệ thống đang chẩn đoán một lỗi diễn ra ngắt quãng và muốn lưu bằng chứng **ngay lúc sự cố**, có thể dùng `JFR.dump` để xuất một file rồi tiếp tục ghi. Tuy nhiên, phần lịch sử cũ đã bị loại do `maxage`/`maxsize` sẽ **không được khôi phục** bằng cách dump muộn.

## 9. Khi chạy nhiều recording cùng lúc

Một JVM có thể có nhiều recording hoạt động đồng thời, với tên, thời gian và event settings khác nhau. Về mặt logic, mỗi recording mô tả dữ liệu mà người dùng muốn giữ. Về mặt triển khai, JFR dùng hạ tầng thu thập và quản lý dữ liệu bên trong JVM chung.

Điều này kéo theo những nguyên tắc:

- Đừng giả định mỗi `Recording` tương ứng **một thread ghi file riêng** hoặc **một chunk file riêng** trong repository.
- Đừng quan sát số file đang có trong repository rồi suy ra đó là **số recording**.
- Muốn lấy dữ liệu đúng khoảng thời gian/phiên ghi, sử dụng `dump`/API của recording cụ thể, không tự chép một file ngẫu nhiên từ repository.
- Cân nhắc chi phí tổng khi bật nhiều event settings cùng lúc; việc có thêm recording không có nghĩa JFR không phải thu thập thêm loại sự kiện nào.

Ví dụ tình huống: một recording liên tục `baseline` giữ 1 giờ với `settings=default`, trong khi một recording ngắn `investigation` dùng `settings=profile` để chẩn đoán. Khi dump, bạn nên dùng đúng **tên recording** và chính sách lưu trữ kết quả rõ ràng.

## 10. Recovery khi JVM crash: các chunk hoàn tất và jfr assemble

Nếu JVM thoát bất thường trước khi có bản dump, repository có thể còn **các chunk hoàn tất**. Công cụ `jfr assemble` được thiết kế để ghép các chunk hợp lệ theo thời gian thành file `.jfr`, phục vụ phục hồi sau sự cố.

Cú pháp:

~~~bash
jfr assemble /path/to/repository /path/to/recovered.jfr
~~~

Đây là ví dụ cú pháp; hai đường dẫn phải thay bằng nơi lưu chunk và nơi muốn tạo file. Theo hướng dẫn `jfr`, các chunk **chưa hoàn tất**, ví dụ file có phần mở rộng `.part`, **không được đưa vào bản ghép**.

**Giới hạn của khả năng phục hồi:**

- Chỉ có thể khôi phục những chunk còn tồn tại, đã được ghi ra đĩa và đủ hợp lệ.
- Dữ liệu còn trong buffer khi JVM crash hoặc bị mất nguồn **không được bảo đảm** có mặt trong repository.
- `jfr assemble` không phải công cụ sửa được mọi chunk bị hỏng, cũng không tái tạo dữ liệu đã bị retention xóa.
- Nếu repository nằm trên thư mục tạm bị dọn sạch sau restart, những chunk cần phục hồi có thể biến mất.
- Nên thao tác với **bản sao** của dữ liệu phục hồi khi phù hợp, không sửa/xóa repository của JVM vẫn hoạt động.

Sau khi ghép, dùng:

~~~bash
jfr summary /path/to/recovered.jfr
jfr print /path/to/recovered.jfr
~~~

Nếu cần hiểu cấu trúc nhiều chunk của một file dump đã hoàn chỉnh, công cụ `jfr disassemble` có thể **tách file recording thành các chunk file** để kiểm tra/phục vụ xử lý đặc biệt:

~~~bash
jfr disassemble --output /path/to/chunks /path/to/recording.jfr
~~~

Tùy chọn này không phải thao tác cần thiết cho công việc đọc event thông thường; `jfr summary`, `jfr print` hoặc JDK Mission Control thường tiện hơn. Không nên hiểu việc disassemble rồi assemble là cách tăng chất lượng hay phục hồi các event đã bị mất.

## 11. Vận hành an toàn: disk space, retention, quyền và dữ liệu nhạy cảm

### 11.1. Lên ngân sách lưu trữ trước khi chạy liên tục

Một cấu hình giữ vô hạn dữ liệu trong repository có thể tạo áp lực lên dung lượng đĩa. Xem xét:

- Giới hạn `maxage` và `maxsize` của recording.
- Lưu lượng event thực tế, độ chi tiết của event settings và thời gian recording hoạt động.
- Vùng lưu trữ có đủ dung lượng, quyền ghi và không bị chính sách dọn temp xóa bất ngờ.
- Chiến lược đẩy **file dump** sang kho lưu trữ dài hạn và xóa artifact theo vòng đời riêng.
- Sự khác nhau giữa byte trong repository tạm và byte của file `.jfr` đã dump.

**Đừng coi `maxsize` là giới hạn tổng tuyệt đối cho mọi file trong cả hệ thống**: một JVM có thể có nhiều recording, còn dump file và repository là hai loại dữ liệu khác nhau.

### 11.2. Sự kiện có thể bị mất khi có áp lực

Vì JFR thu thập qua bộ đệm và ghi dữ liệu bất đồng bộ theo cơ chế riêng, không nên hứa “bật `disk=true` là mọi event sẽ luôn tồn tại trên đĩa”. Những tình huống như disk đầy, I/O chậm, JVM crash và các giới hạn buffer có thể làm thiếu dữ liệu. Khi phân tích sự cố, kiểm tra log/cảnh báo của JVM và khoảng thời gian dữ liệu thực sự có trong recording.

### 11.3. Bảo mật file recording

Một file JFR có thể chứa thông tin vận hành đáng chú ý: class/method names, thread names, stack traces, allocation profiles, I/O và các event ứng dụng tự tạo. **Không đưa mật khẩu, token, dữ liệu khách hàng hoặc payload nhạy cảm vào custom event nếu không có nhu cầu và biện pháp bảo vệ rõ ràng.**

- Phân quyền thư mục repository và nơi lưu dump.
- Dùng các đường dẫn có chính sách backup/retention phù hợp.
- Không tự động đưa dump ra hệ thống giám sát công khai hoặc log chat.
- Khi chuyển file để hỗ trợ sự cố, xem xét lọc/kiểm tra dữ liệu nhạy cảm trước khi chia sẻ.
- Không khởi chạy nhiều recording `profile` rất chi tiết mà không đánh giá chi phí và yêu cầu điều tra.

## 12. Phân biệt các lệnh và API trong một bảng

| Công việc | API / công cụ | Điều cần nhớ |
|---|---|---|
| Tạo phiên ghi trong code | `new Recording(...)` | Chưa bắt đầu cho đến khi gọi `start()` |
| Ghi qua repository | `recording.setToDisk(true)` | Dữ liệu được quản lý trong repository tạm |
| Chỉ sử dụng buffer bộ nhớ | `recording.setToDisk(false)` | Lịch sử có thể ngắn do giới hạn buffer |
| Giới hạn lịch sử | `setMaxAge(...)`, `setMaxSize(...)` | Có thể xóa chunk cũ, không xóa file dump đã xuất |
| Dừng thu thập | `recording.stop()` | Không thể khởi động lại recording đã stop |
| Xuất khi đang chạy hoặc sau stop | `recording.dump(path)` | Tạo file `.jfr` từ dữ liệu còn khả dụng |
| Tự xuất khi stop | `recording.setDestination(path)` | Khác với repository path; tự đóng sau khi xuất thành công |
| Giải phóng tài nguyên | `recording.close()` | Không thể dùng recording đã close để dump |
| Quan sát phiên ghi đang chạy | `jcmd PID JFR.check` | Không phải đọc repository thủ công |
| Lấy bản dump ngoài ứng dụng | `jcmd PID JFR.dump ...` | Có thể dump mà không dừng recording |
| Xem tóm tắt file | `jfr summary file.jfr` | Số event/chunk tùy dữ liệu thực |
| Xem event | `jfr print file.jfr` | Có thể lọc sự kiện |
| Cứu chunk hoàn tất sau crash | `jfr assemble repository output.jfr` | Không ghép file `.part` chưa hoàn tất |

## 13. Các nhầm lẫn phổ biến và cách sửa

**Nhầm lẫn 1 — “`disk=true` tạo ngay file `service.jfr` ở repository.”**  
Sai. Repository là vùng tạm JFR quản lý. Nếu cần file có tên cụ thể để phân tích, gọi `dump` hoặc cấu hình `destination/filename` phù hợp. Không suy ra đường dẫn export từ repository.

**Nhầm lẫn 2 — “`stop()` có nghĩa chắc chắn đã có file dump.”**  
Không phải mặc định. Nếu không đặt destination và không dump tường minh, dữ liệu có thể chỉ còn được quản lý nội bộ cho đến khi đóng.

**Nhầm lẫn 3 — “Mỗi recording là một chunk.”**  
Sai. Một recording có thể có nhiều chunk; số chunk phụ thuộc dữ liệu, thời lượng và cấu hình.

**Nhầm lẫn 4 — “`maxsize` là kích thước tối đa của mỗi chunk.”**  
Sai. `maxsize` giới hạn dữ liệu giữ lại của recording; `maxchunksize` điều chỉnh kích thước chunk ở mức cấu hình JFR.

**Nhầm lẫn 5 — “Vì `disk=true`, mọi event đều được bảo toàn ngay lập tức kể cả khi mất điện.”**  
Không. Buffer và hoạt động flush tạo khoảng trễ; dữ liệu chưa ghi xuống đĩa hoặc chunk chưa hoàn tất có thể không phục hồi được.

**Nhầm lẫn 6 — “File `.part` cũng có thể cứ ghép bằng `jfr assemble`.”**  
Không. Theo hướng dẫn công cụ, chunk chưa hoàn tất với hậu tố `.part` không được đưa vào bản assemble. Cần chấp nhận có thể mất đoạn dữ liệu cuối.

**Nhầm lẫn 7 — “Có thể xóa các chunk khi recording còn chạy nếu folder đầy.”**  
Không nên. Làm như vậy có thể phá dữ liệu JFR đang được JVM dùng. Hãy đặt retention trước, kiểm tra mức event thu thập, điều chỉnh dung lượng và dùng quy trình vận hành được hỗ trợ.

**Nhầm lẫn 8 — “`close()` xóa luôn file `.jfr` do `dump()` tạo.”**  
Sai. `close()` giải phóng dữ liệu gắn với recording; file dump đã tạo là artifact riêng mà ứng dụng/người vận hành phải quản lý.

**Nhầm lẫn 9 — “Dùng `disk=false` thì không thể xuất dữ liệu.”**  
Không chính xác. Có thể lấy dữ liệu còn khả dụng trong bộ đệm bằng thao tác dump phù hợp, nhưng dữ liệu cũ có thể đã bị ghi đè; `getStream(...)` cho recording không dùng disk trả `null` theo hợp đồng API.

**Nhầm lẫn 10 — “Nhìn số file trong repository là biết số recording đang chạy.”**  
Sai. Cần dùng `JFR.check` hoặc API trạng thái thay vì suy luận từ file nội bộ.

## 14. Bài tập tự kiểm tra

**Câu 1.** Ứng dụng có recording `disk=true` và bạn nhìn thấy nhiều file tạm trong repository. File nào nên gửi đồng nghiệp để phân tích?

**Đáp án:** Xuất file `.jfr` bằng `Recording.dump(path)` hoặc `JFR.dump filename=...`. Không tự chọn một chunk đang chạy để coi là toàn bộ recording.

**Câu 2.** `maxage=30m` và `maxsize=64m` liên quan đến điều gì?

**Đáp án:** Chúng điều khiển lịch sử và lượng dữ liệu **được giữ trong disk repository** cho recording; dữ liệu cũ có thể bị loại theo chunk. Không phải thiết lập độ lớn mỗi chunk và không tự xóa file đã dump.

**Câu 3.** Sau khi `recording.stop()`, còn có thể `recording.start()` lần nữa không?

**Đáp án:** Không. Recording đã dừng không thể khởi động lại; cần tạo recording mới. Nếu chưa đóng và dữ liệu còn khả dụng, có thể dump recording đã dừng.

**Câu 4.** Tại sao không thể đảm bảo dữ liệu vừa phát sinh trước khi crash đều có trong repository?

**Đáp án:** Event có thể còn trong bộ đệm hoặc chunk chưa hoàn tất; cơ chế flush không phải cam kết đồng bộ từng event vào disk. Chỉ các chunk đã tồn tại, hợp lệ mới có cơ hội phục hồi.

**Câu 5.** `setDestination(path)` và `-XX:FlightRecorderOptions=repository=path` có cùng tác dụng không?

**Đáp án:** Không. Destination là **file đích lúc xuất/dừng recording**; repository là **thư mục lưu tạm** trong quá trình recording dùng disk.

**Câu 6.** Nếu `disk=false` thì `Recording.getStream(...)` trả gì?

**Đáp án:** Theo Java 17 API, `getStream(...)` trả `null` nếu recording không được ghi lên đĩa. Điều này khác với `dump(...)`, có thể xuất dữ liệu còn khả dụng trong buffer.

**Câu 7.** Sau khi đã gọi `dump(...)` thành công, có thể dùng `jfr summary` trên file mới không?

**Đáp án:** Có, đó là tác vụ đọc file `.jfr`. Số chunk, timestamp, loại và số lượng event trong tóm tắt phụ thuộc dữ liệu thu được thực tế.

**Câu 8.** Một recording chạy nhiều giờ không đặt `maxAge` và `maxSize` có rủi ro gì?

**Đáp án:** Dung lượng dữ liệu trong repository có thể tăng kéo dài mà không có giới hạn retention do recording cấu hình. Cần lên ngân sách disk và đặt chính sách lưu giữ phù hợp.

## 15. Checklist khi triển khai JFR thu thập dài hạn

1. **Định nghĩa mục tiêu:** muốn lịch sử liên tục hay chụp nhanh sự cố?
2. **Chọn settings:** `default` cho quan sát liên tục; `profile` khi điều tra có mục đích.
3. **Chọn chế độ lưu:** `disk=true` khi cần repository giữ lịch sử; `disk=false` khi chấp nhận bộ đệm ngắn.
4. **Đặt retention:** `maxage` và `maxsize` sát nhu cầu chẩn đoán, theo dõi dung lượng thực.
5. **Chọn repository:** đường dẫn đủ dung lượng, có quyền ghi, không bị dọn file khi JVM còn chạy.
6. **Tách đường dẫn dump:** chọn nơi lưu file `.jfr` độc lập và vòng đời artifact rõ ràng.
7. **Xác minh recording:** dùng `JFR.check` hoặc `Recording.getState()`; không dựa vào số file trong repository.
8. **Thử dump khi vẫn đang chạy:** bảo đảm hệ thống có thể lấy dữ liệu lúc sự cố mà không phải dừng JVM.
9. **Kiểm tra file đã dump:** `jfr summary`, `jfr print` hoặc JDK Mission Control.
10. **Lập kế hoạch crash recovery:** biết thư mục repository, chỉ phục hồi từ chunk hợp lệ và chấp nhận mất dữ liệu gần thời điểm crash.
11. **Bảo vệ dữ liệu:** phân quyền file và tránh nhúng thông tin nhạy cảm vào custom events.
12. **Ghi rõ giới hạn:** không hứa event loss bằng 0 hay kích thước chunk cố định trong mọi tình huống.

## Tài liệu tham khảo chính thức

- [Java SE 17 API — jdk.jfr.Recording](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): `start`, `stop`, `dump`, `close`, `setToDisk`, `setMaxAge`, `setMaxSize`, `setDestination` và `getStream`.
- [Java SE 17 API — jdk.jfr.consumer.RecordingFile](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc event từ file `.jfr`.
- [JDK 17 Tool Guide — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- [JDK 17 Tool Guide — jfr](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `summary`, `print`, `assemble`, `disassemble`.
- [dev.java — Configuring JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): `disk`, `maxage`, `maxsize`, `maxchunksize` và `repository`.
- [Oracle Java SE 17 — Flight Recorder API Programmer's Guide](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.pdf): cấu hình, sử dụng API và mô hình thu thập.

**Tóm lại:** **Recording là phiên ghi logic; repository là vùng tạm do JVM quản lý; chunk là đơn vị dữ liệu trên đĩa; file `.jfr` là bản xuất phục vụ phân tích.** Đừng đồng nhất chúng. Để JFR dùng được trong điều tra sự cố, hãy cấu hình disk/retention hợp lý, lấy dump bằng API/công cụ chính thức và xử lý phục hồi chunk như trường hợp đặc biệt sau crash.