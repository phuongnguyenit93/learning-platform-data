# 16.2 Vòng đời tạo, cấu hình, start, stop, dump và close của Recording

## Mục tiêu học tập

`jdk.jfr.Recording` là API dùng để điều khiển một phiên **Java Flight Recorder (JFR)** từ mã Java: tạo recording, cấu hình event, khởi động, ghi dữ liệu ra tệp `.jfr`, dừng và giải phóng tài nguyên. Trọng tâm không chỉ là biết tên phương thức, mà còn hiểu **trạng thái hợp lệ và dữ liệu còn được giữ hay đã bị giải phóng** sau mỗi lời gọi.

Sau bài này bạn có thể:

1. Phân biệt `NEW`, `DELAYED`, `RUNNING`, `STOPPED` và `CLOSED`, cùng các chuyển trạng thái hợp lệ.
2. Chọn constructor/configuration, bật event, đặt threshold, storage, duration và chính sách retention trước khi `start()`.
3. Giải thích vì sao `dump(Path)` không dừng recording, vì sao `stop()` không mặc nhiên tạo file, và vì sao `close()` không thay thế thao tác lưu.
4. Chọn đúng giữa hai quy trình: **dump thủ công sau stop** và **`setDestination` tự ghi file khi stop**.
5. Viết, biên dịch, chạy một chương trình Java 17+ minh họa toàn bộ chuỗi `NEW → RUNNING → STOPPED → CLOSED`; đọc lại event đã ghi.
6. Xử lý tình huống exception, recording dừng tự động, disk/memory retention và dữ liệu JFR thiếu.

Ví dụ sử dụng API `jdk.jfr` trên HotSpot/OpenJDK Java 17+; đoạn Java chạy được bên dưới đã kiểm chứng bằng OpenJDK 24. API `RecordingStream` phục vụ tiêu thụ event gần thời gian thực và có vòng đời riêng; bài này chỉ nói về `Recording`.

## 1. Phân biệt đối tượng Recording, phiên thu event và file JFR

Một `Recording` là handle trong ứng dụng: nó có ID, tên, cấu hình event, policy lưu giữ và `RecordingState`. **Bản ghi đang chạy** là khoảng thời gian thực sự nhận event; tệp `.jfr` là một kết quả trích xuất dữ liệu đã được recording giữ. Ba thực thể này có vòng đời liên quan nhưng khác nhau.

| API | Ý nghĩa | Điều không được ngầm hiểu |
| --- | --- | --- |
| `new Recording(...)` | Tạo handle, trạng thái ban đầu `NEW` | Chưa thu event, chưa có file đích |
| `start()` | Bắt đầu thu event theo settings, state `RUNNING` | Không tự xuất file `.jfr` |
| `dump(path)` | Sao chép dữ liệu hiện còn sẵn sang file | **Không tự stop** recording `RUNNING` |
| `stop()` | Kết thúc cửa sổ thu, recording không restart được | Không nhất thiết tự có file |
| `setDestination(path)` | Đặt file tự ghi **khi stop** | Bản thân thao tác này chưa ghi file; stop thành công có thể **tự close** |
| `close()` | Giải phóng dữ liệu/tài nguyên gắn với handle | Không phải lệnh dump/export dữ liệu |

Điểm dễ sai nhất là đồng nhất `stop()` với `close()`: không đặt destination thì một recording đã **STOPPED** vẫn giữ dữ liệu để `dump()` sau đó khi `toDisk=true`; **CLOSED** nghĩa là dữ liệu do handle giữ đã được giải phóng. Nếu gọi close trước dump, cơ hội xuất file từ handle đó mất đi.

## 2. Máy trạng thái của Recording

```text
               new Recording(...)
                       |
                       v
                      NEW
                       |
             +---------+------------------+
             |                            |
           start()                scheduleStart(delay)
             |                            |
             v                            v
           RUNNING                     DELAYED
             |                            |
             |                       hết thời gian chờ
             |                            |
             |<---------------------------+
             |
             +---- dump(path) ----> RUNNING (không dừng)
             |
             +---- stop() --------> STOPPED
                                       |
                                       +-- dump(path), nếu toDisk=true
                                       |
                                       +-- close() --> CLOSED

  close() có thể kết thúc handle còn mở.
  Khi setDestination(path) được đặt và stop ghi file thành công,
  recording tự đóng thay vì ở lại để dump thủ công.
```

| Trạng thái | Nguồn gốc | Có thể làm gì? |
| --- | --- | --- |
| `NEW` | Vừa tạo | Đặt settings, `start()` hoặc `scheduleStart()` |
| `DELAYED` | Sau `scheduleStart(delay)` | Chờ thời điểm start; đừng suy rằng event đã được thu |
| `RUNNING` | `start()` thành công hoặc hết delay | Thu event; `dump(path)` để lấy snapshot mà vẫn tiếp tục chạy; `stop()` để kết thúc |
| `STOPPED` | `stop()` thành công, hoặc recording tự dừng do duration | Không `start()` lại; có thể dump nếu `toDisk=true` và chưa close |
| `CLOSED` | `close()` hoặc stop với destination được ghi thành công | Không dùng lại handle để dump/start |

**Những quy tắc phải nhớ:**

- Recording là phiên **một lần**. Sau khi đã stop, muốn bắt đầu lượt đo khác thì tạo một `Recording` mới; không gọi `start()` lần hai.
- `start()` trên recording đã bắt đầu/đã CLOSED và `stop()` khi chưa start hoặc đã stop là các trường hợp sai trạng thái có thể gây `IllegalStateException`.
- `dump(Path)` theo Javadoc chỉ thành công khi recording đang **RUNNING**, hoặc đang **STOPPED và toDisk=true**. Ở NEW/DELAYED/CLOSED, hoặc STOPPED nhưng không dùng disk repository, có thể ném `IOException`.
- `getState()` phản ánh trạng thái quan sát tại lúc gọi. Nếu có nhiều luồng điều khiển cùng recording, việc check trạng thái rồi thực hiện thao tác vẫn cần đồng bộ/owner rõ ràng để tránh race.
- `scheduleStart(Duration)` tạo giai đoạn DELAYED; `setDuration(Duration)` có thể làm recording tự dừng sau thời gian được đặt. Đừng luôn giả định recording vẫn RUNNING trong callback cleanup.
- Nếu có `setDestination(path)`, stop sẽ ghi dữ liệu sang file và **tự động đóng recording sau khi sao chép thành công**. Không cố dump lần nữa trên handle đã đóng.

## 3. Tạo recording đúng cách

### 3.1. Constructor và template

Ba kiểu tạo thường gặp:

```java
// Các dòng minh họa bên trong method, chưa bao gồm import và xử lý exception:
Recording r1 = new Recording();
Recording r2 = new Recording(Configuration.getConfiguration("default"));
Recording r3 = new Recording(Configuration.getConfiguration("profile"));
```

Đây là các **đoạn minh họa**, không phải chương trình độc lập. `Recording` và `Configuration` thuộc `jdk.jfr`; mọi handle cần close khi kết thúc.

- `new Recording()` tạo recording **không có sẵn event settings**. Không được mặc định nó tương đương template `default.jfc`.
- `Configuration.getConfiguration("default")` lấy bộ cấu hình mặc định JDK, hữu ích cho thu thường xuyên với overhead tương đối thấp.
- `Configuration.getConfiguration("profile")` lấy template phục vụ phân tích sâu hơn, có thể tạo nhiều dữ liệu và overhead hơn. Hai template không bật mọi event; kiểm tra phiên bản JDK và thiết lập thực.
- `new Recording(Map<String,String>)` nhận settings do ứng dụng dựng; `setSettings(map)` **thay thế** tập settings đang có. `getSettings()` trả về map để kiểm tra/điều chỉnh bản sao; thay đổi map đó không tự cập nhật recording nếu không gọi `setSettings`.

**Nên hoàn tất cấu hình trước `start()`**: Javadoc khuyến nghị để các event và tùy chọn được áp dụng nhất quán, giảm thay đổi giữa phiên làm phép đo khó so sánh.

### 3.2. Chọn event và setting

Ví dụ về API event:

```java
// Đoạn trong method, giả định biến recording và class MyEvent đã tồn tại:
recording.enable(MyEvent.class).withThreshold(Duration.ZERO);
recording.enable("jdk.JavaMonitorEnter")
         .withThreshold(Duration.ofMillis(10))
         .withStackTrace();
recording.disable("jdk.ExceptionThrow");
```

Đây là **mã minh họa chưa độc lập**: cần class `MyEvent extends jdk.jfr.Event`, `Duration` và một `Recording` hợp lệ.

Các lựa chọn thường gặp:

- **enabled:** event type có được recording cho phép thu không.
- **threshold:** với event có thời lượng, những event ngắn hơn ngưỡng không được lưu. `Duration.ZERO` có thể dùng trong một cửa sổ đo hẹp để nhìn cả event rất ngắn.
- **stackTrace:** thu stack trace của event, có chi phí bổ sung.
- **period:** một số event phát định kỳ; số mẫu không phải số lần một phương thức đã chạy.

Bật event không đảm bảo nó sẽ xuất hiện: workload phải thực sự tạo event, event phải qua ngưỡng, recording phải đang RUNNING, và dữ liệu phải còn được giữ đến khi dump.

### 3.3. Các tùy chọn cấp recording

| Phương thức | Vai trò | Lưu ý vận hành |
| --- | --- | --- |
| `setName(String)` | Đặt tên dễ đọc cho recording | `getId()` cung cấp ID riêng; không dựa duy nhất vào tên nếu có nhiều recording |
| `setToDisk(true)` | Cho phép JFR dùng disk repository; mặc định `true` | Là lựa chọn phù hợp khi cần dump sau stop |
| `setToDisk(false)` | Không liên tục flush đến disk repository; bị giới hạn bởi buffer trong bộ nhớ | `getSize()` bằng 0 theo API; sau stop không có đường dump hợp lệ |
| `setMaxAge(Duration)` | Giới hạn tuổi dữ liệu giữ trong repository | Chunk cũ bị loại, không thể phục hồi bằng dump sau đó |
| `setMaxSize(long)` | Giới hạn lượng dữ liệu giữ (byte); `0` là không giới hạn | Dữ liệu cũ có thể bị loại nếu vượt giới hạn |
| `setDuration(Duration)` | Tự dừng sau thời lượng chỉ định | Đặt trước start, rồi kiểm tra state trước thao tác sau thu |
| `scheduleStart(Duration)` | Bắt đầu sau một khoảng chờ | State ban đầu DELAYED; chưa thu trước lúc thực sự start |
| `setDestination(Path)` | Chỉ định file xuất khi stop | Ghi thành công sẽ tự close recording |
| `setDumpOnExit(true)` | Yêu cầu dump khi JVM thoát theo cơ chế JFR hỗ trợ | Không thể bảo đảm đủ dữ liệu khi kill cứng/crash |

Lưu ý `setToDisk(true)` là **disk repository nội bộ của JFR**, không đồng nghĩa đã có file báo cáo cuối cùng ở đường dẫn bạn muốn. Tệp xuất cuối phải đến từ `dump(path)` hoặc `setDestination(path)` khi stop.

Với ứng dụng chạy lâu, nếu không đặt max age/max size, dữ liệu trong repository có thể tăng mạnh; hãy chọn retention theo chi phí và cửa sổ sự cố cần phân tích.

## 4. Hai chuỗi thao tác hợp lệ

### 4.1. Chuỗi A: tự điều khiển dump

Khi cần snapshot lúc đang xử lý và file cuối sau khi kết thúc:

```text
create & configure (toDisk=true, không setDestination)
        |
      start
        |
  chạy workload A
        |
 dump(snapshot.jfr)  -- vẫn RUNNING
        |
  chạy workload B
        |
      stop            -- STOPPED
        |
 dump(final.jfr)     -- hợp lệ vì toDisk=true
        |
      close           -- CLOSED
```

`dump(Path)` ở RUNNING không dừng recording. Snapshot chỉ có dữ liệu có sẵn **đến lúc dump**, không tự cập nhật khi event phát sinh sau đó. `stop()` kết thúc thu, và `dump(finalPath)` trên STOPPED có thể xuất file cuối nếu recording dùng disk repository và vẫn giữ dữ liệu.

### 4.2. Chuỗi B: tự ghi file khi stop

Khi chỉ cần một file cuối:

```java
// Mẫu bên trong method; doWork() là hàm ứng dụng cần tự định nghĩa.
Path output = Path.of("final.jfr");
try (Recording r =
        new Recording(Configuration.getConfiguration("default"))) {
    r.setName("one-shot");
    r.setDestination(output);
    r.start();
    doWork();
    r.stop(); // Tự ghi final.jfr và đóng recording khi thành công.
}
```

Đoạn **minh họa**, chưa độc lập vì `doWork()` không được định nghĩa. `setDestination` chỉ đăng ký vị trí đầu ra. Dữ liệu được ghi khi stop; sau khi ghi thành công, recording đã tự close, nên **không gọi tiếp `r.dump(...)`**.

Nếu định dùng `setDuration` để tự stop, việc có destination giúp file được xuất ở thời điểm tự dừng (với điều kiện quá trình hoàn tất thành công). Nếu cần kiểm soát lỗi lưu/timestamp, kiểm tra file thực sự tồn tại và đọc được, không dựa vào suy đoán.

### 4.3. Stop khác Close ra sao?

Trong chuỗi A, `stop()` dừng tạo dữ liệu mới nhưng giữ nội dung để dump sau đó; `close()` giải phóng nội dung được giữ. Trình tự **stop → close → dump** là sai. Thực hiện **stop → dump → close**.

Trong chuỗi B, stop thành công **đã bao gồm file export và close** do destination được thiết lập. Một lệnh dump tiếp trên recording đó sẽ thất bại. Nếu muốn thêm file snapshot, dump **trước** stop, khi còn RUNNING, hoặc dùng chuỗi A.

## 5. Chương trình Java 17+ chạy được, đã kiểm chứng stdout

Ví dụ tạo custom event `demo.Milestone` để không phụ thuộc vào GC/I/O xảy ra ngẫu nhiên. Chương trình tạo hai event, dump một snapshot lúc RUNNING, stop, dump file cuối, đếm số event, và close bằng `try-with-resources`.

```java
// File: RecordingLifecycleDemo.java
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

public class RecordingLifecycleDemo {
    @Name("demo.Milestone")
    static class Milestone extends Event {
        String step;
    }

    static void emit(String step) {
        Milestone event = new Milestone();
        event.step = step;
        event.commit();
    }

    static long countMilestones(Path path) throws Exception {
        try (RecordingFile reader = new RecordingFile(path)) {
            long count = 0;
            while (reader.hasMoreEvents()) {
                if ("demo.Milestone".equals(reader.readEvent().getEventType().getName())) {
                    count++;
                }
            }
            return count;
        }
    }

    public static void main(String[] args) throws Exception {
        Path snapshot = Files.createTempFile("jfr-running-", ".jfr");
        Path result = Files.createTempFile("jfr-final-", ".jfr");
        Recording recording = new Recording(Configuration.getConfiguration("default"));
        try {
            try (recording) {
                recording.setName("lifecycle-demo");
                recording.setToDisk(true);
                recording.enable(Milestone.class).withThreshold(Duration.ZERO);
                System.out.println("created=" + recording.getState());

                recording.start();
                System.out.println("started=" + recording.getState());
                emit("first");

                recording.dump(snapshot);
                System.out.println("after-running-dump=" + recording.getState());
                emit("second");

                recording.stop();
                System.out.println("stopped=" + recording.getState());
                recording.dump(result);
                System.out.println("saved-events=" + countMilestones(result));
            }
            System.out.println("closed=" + recording.getState());
        } finally {
            Files.deleteIfExists(snapshot);
            Files.deleteIfExists(result);
        }
    }
}
```

Lưu file đúng tên `RecordingLifecycleDemo.java`. Biên dịch/chạy bằng JDK 17+:

```bash
javac RecordingLifecycleDemo.java
java RecordingLifecycleDemo
```

Stdout chính xác đã kiểm chứng trên OpenJDK 24:

```text
created=NEW
started=RUNNING
after-running-dump=RUNNING
stopped=STOPPED
saved-events=2
closed=CLOSED
```

Giải thích:

1. `NEW`: đã có handle, chưa thu event.
2. `RUNNING` sau start: recording nhận event đã bật. `emit("first")` commit event đầu.
3. `after-running-dump=RUNNING`: `dump(snapshot)` xuất snapshot nhưng recording tiếp tục chạy; event `second` được commit sau dump.
4. `STOPPED` sau stop: recording không nhận event mới, vẫn giữ dữ liệu để dump bởi `toDisk=true` và không có destination.
5. `saved-events=2`: file cuối chứa cả hai instance của `demo.Milestone`. `RecordingFile` duyệt event type và đếm đúng hai event.
6. `CLOSED` sau khi rời try-with-resources: handle đã được close.

Tệp snapshot và final được tạo trong thư mục tạm của hệ điều hành rồi xóa sau phép kiểm tra. Nếu cần mở tệp trong JDK Mission Control, hãy chủ động lưu bản chẩn đoán ở một đường dẫn cần giữ và không xóa nó trước khi phân tích. Ví dụ này không minh họa lỗi disk, crash hoặc quyền ghi; production cần xử lý riêng.

## 6. Stop, dump, close trong luồng có exception

`Recording` triển khai `AutoCloseable`/`Closeable`. `try-with-resources` đảm bảo `close()` chạy khi ra khỏi scope, cả khi workload ném exception; **nhưng nó không tự đảm bảo file đã được dump**.

Xét đoạn minh họa:

```java
// Minh họa logic trong method; configuration, work và destination do ứng dụng cung cấp.
try (Recording r = new Recording(configuration)) {
    r.setToDisk(true);
    r.start();
    work();             // Nếu ném exception, các dòng dưới bị bỏ qua.
    r.stop();
    r.dump(destination);
}
```

Nếu `work()` ném exception, recording được close khi thoát try, **trước khi stop/dump** trong nhánh bình thường. Do đó không nên hứa sẽ có file khi xảy ra lỗi. Khi yêu cầu là giữ bằng chứng ngay cả nếu nghiệp vụ thất bại, thực hiện cleanup trong `finally` có kiểm tra trạng thái và xử lý lỗi xuất file riêng.

Mẫu tư duy (pseudocode, **không phải Java chạy nguyên văn**):

```text
create + configure
try:
    start
    run workload
finally:
    if getState() == RUNNING:
        stop (nếu chính sách yêu cầu)
    if getState() == STOPPED and isToDisk():
        dump(result.jfr) nếu cần chứng cứ
    close dù dump/stop thất bại
```

Vì `stop()`/`dump()` có thể ném exception, code thật cần giữ lỗi gốc, log lỗi cleanup bổ sung và luôn close. Nếu có destination và stop đã tự close, đừng chạy nhánh dump trên handle CLOSED.

Có hai tình huống cần cẩn trọng:

- **Duration/đối tượng khác tự stop:** callback finally không được `stop()` lần nữa nếu state đã STOPPED.
- **Nhiều thread cùng điều khiển:** check `getState()` rồi stop không tránh race; chỉ định một owner chịu trách nhiệm lifecycle hoặc dùng cơ chế đồng bộ phù hợp.

## 7. File, repository và sự đầy đủ của dữ liệu

Một file `.jfr` tồn tại **chưa chắc chứa đầy đủ event mà bạn mong đợi**.

- Event chưa được enable hoặc không đạt threshold.
- Event diễn ra **trước start** hay **sau stop**.
- Snapshot được dump khi RUNNING **trước** khi event cần phân tích xảy ra.
- `maxAge`/`maxSize` làm loại chunk cũ khỏi disk repository.
- `toDisk=false` giới hạn dữ liệu bởi bộ đệm; `dump` sau STOPPED không khả dụng.
- Disk không ghi được, JVM bị dừng bất thường hoặc file dump lỗi.
- Công cụ xem file áp bộ lọc loại event, time range hoặc thread.

Phân biệt file đích với repository: `setToDisk(true)` làm JFR có thể flush vào repository nội bộ; nó không chọn file `result.jfr` cho bạn. Cần gọi `dump(Path)` hoặc `setDestination(Path)` + stop. `getSize()` phản ánh kích thước dữ liệu recording trong repository sau flush (theo tài liệu API), **không phải số byte chính xác file export**; khi `toDisk=false`, phương thức này trả về 0, nhưng không có nghĩa không tồn tại event trong buffer.

Nếu đã lưu file thật, kiểm tra bằng JDK tools:

```bash
jfr summary path/to/result.jfr
jfr metadata path/to/result.jfr
jfr print --events demo.Milestone path/to/result.jfr
```

`path/to/result.jfr` chỉ là đường dẫn minh họa. `jfr summary` cho số event thực sự có trong file; `metadata` mô tả schema event, không chứng minh đã có instance; `print` liệt kê những instance phù hợp bộ lọc. Khi kết luận thiếu event, kiểm tra cả setting, thời gian, và file có chứa đủ lịch sử hay không.

## 8. Các tình huống lỗi và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `start()` ném `IllegalStateException` | Recording đã start, đã STOPPED hoặc CLOSED | Tạo recording mới cho vòng đo mới |
| `stop()` ném `IllegalStateException` | Chưa chạy, đã stop, hoặc xử lý shutdown gọi trùng | Kiểm tra state và chỉ định một owner |
| `dump()` ném `IOException` | NEW/DELAYED/CLOSED, STOPPED mà toDisk=false, hoặc path không ghi được | Đúng state; chọn `toDisk=true` khi cần dump sau stop; kiểm tra filesystem |
| Stop xong không có file | Không gọi dump và không đặt destination | Chọn một trong hai chuỗi export ở mục 4 |
| Stop xong dump lần nữa không được | `setDestination` đã tự đóng recording khi ghi thành công | Dùng file destination; nếu cần snapshot bổ sung, dump trước stop |
| Không thấy event trong file | Event không bật, threshold, sai cửa sổ, retention hoặc sai loại event | Kiểm tra cấu hình và event count, thu lại khi cần |
| File quá lớn | Không giới hạn retention, nhiều event chi tiết, duration dài | `maxAge`/`maxSize`/threshold; chọn event đủ dùng |
| `getSize()==0` với `toDisk=false` | Không dùng disk repository | Đừng kết luận recording không có event |
| Cleanup làm mất dữ liệu điều tra | `close()` trước `dump()` | Dump trước close; thiết kế error path |
| File không đọc được sau crash | Chưa dump hoàn tất hoặc dữ liệu chưa được flush | Kiểm tra log/file thực tế; đừng coi dump-on-exit là bảo đảm chống crash |

### Những hiểu lầm cần loại bỏ

**“Gọi dump là dừng recording.”** Không. `dump` lúc RUNNING tạo snapshot và recording vẫn RUNNING. Bằng chứng là ví dụ in đúng state sau live dump.

**“Stop và close tương đương.”** Không. Với `toDisk=true` không destination, STOPPED vẫn có thể dump, CLOSED không thể.

**“Đã gọi start thì mọi event có mặt.”** Không. Recording chỉ ghi những event được cấu hình, xảy ra trong cửa sổ đo và đạt bộ lọc.

**“Đặt destination là file xuất ngay lập tức.”** Không. File được ghi khi stop; còn việc export thành công phải được kiểm chứng.

**“STOPPED luôn dump được.”** Không. Javadoc đòi `toDisk=true` nếu dump sau stop. `toDisk=false` chỉ phù hợp với chiến lược lưu theo bộ đệm và cần xử lý khi đang RUNNING nếu phải xuất snapshot.

**“JFR dùng disk repository nghĩa là tự có file phân tích cuối.”** Không. Repository không đồng nhất với file export; chọn đường dẫn rõ ràng.

**“Close trong finally là đủ để lưu dữ liệu khi có lỗi.”** Không. Close giải phóng dữ liệu. Cần chính sách stop/dump trước close trên cả đường thành công và lỗi.

## 9. Quy trình áp dụng cho ứng dụng thật

1. **Xác định mục tiêu đo:** CPU, lock contention, allocation, GC, I/O hay custom event? Chọn `default`/`profile` và những event/threshold cần thiết.
2. **Quyết định thời lượng và cửa sổ:** start ngay, schedule delay, hay set duration? Dự tính các mốc workload.
3. **Chọn chiến lược file:** manual `dump` (nhất là khi cần live snapshot) hay `setDestination` (một file khi stop). Ghi rõ nơi lưu, retention và disk budget.
4. **Tạo và cấu hình Recording:** event settings, name, `toDisk`, `maxAge`, `maxSize`, duration/destination trước start; log ID và mốc thời gian cần thiết.
5. **Start và chạy workload:** kiểm tra state khi có auto-stop; đừng thay cấu hình tùy tiện giữa phiên.
6. **Dump/stop theo chiến lược đã chọn:** kiểm tra từng thao tác trả về thành công và không trộn hai quy trình gây auto-close bất ngờ.
7. **Close bảo đảm:** dùng try-with-resources/finally, quản lý exception, tránh hai nơi cùng stop.
8. **Kiểm chứng dữ liệu:** file tồn tại và đọc được; `jfr summary` có khoảng thời gian và loại event dự kiến. Trình bày giới hạn nếu event thiếu.

### Checklist bàn giao

- [ ] Dùng đúng JDK hỗ trợ `jdk.jfr`; chọn đúng template và event settings.
- [ ] Hiểu state hiện tại; NEW, DELAYED, RUNNING, STOPPED, CLOSED có ý nghĩa khác nhau.
- [ ] Đặt event, threshold, storage, duration và retention trước start khi có thể.
- [ ] Không restart recording đã STOPPED; tạo handle mới.
- [ ] Live dump không dừng recording; file snapshot không tự nhận event tương lai.
- [ ] Dùng `toDisk=true` nếu cần dump sau stop.
- [ ] Nếu dùng `setDestination`, stop thành công sẽ xuất file rồi tự close, không dump lại.
- [ ] Gọi close để giải phóng tài nguyên sau khi đã lưu dữ liệu cần thiết.
- [ ] Error path không làm mất chứng cứ do close trước dump.
- [ ] File đã được đọc lại, đúng thời gian và event mong đợi; không kết luận từ file thiếu dữ liệu.

**Điểm cốt lõi:** `start()` mở cửa sổ ghi; `dump(Path)` lấy một bản sao dữ liệu và có thể diễn ra khi recording vẫn RUNNING; `stop()` kết thúc thu; `close()` giải phóng dữ liệu. Việc đặt `setDestination(Path)` quyết định recording **tự xuất và tự đóng** lúc stop. Hãy thiết kế đúng chuỗi lifecycle theo nhu cầu file, xác nhận state và kiểm chứng nội dung tệp trước khi dùng JFR làm bằng chứng chẩn đoán.

## Tài liệu API chính thức

- Oracle JDK 21 — `Recording`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Oracle JDK 21 — `RecordingState`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/RecordingState.html
- Oracle JDK 21 — `Configuration`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Configuration.html
- Oracle JDK 21 — `EventSettings`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html
- Oracle JDK 21 — `RecordingFile`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html
