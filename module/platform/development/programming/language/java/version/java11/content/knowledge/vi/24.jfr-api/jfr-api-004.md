# JFR API: Thời hạn, đích lưu và ghi khi ứng dụng kết thúc (Java 11+)

> **Ngữ cảnh:** Java Flight Recorder (JFR) là cơ chế ghi sự kiện chẩn đoán hiệu năng của JVM. Bài này tập trung vào vòng đời **`jdk.jfr.Recording`**, đặc biệt là **`setDuration(Duration)`**, **`setDestination(Path)`**, **`setDumpOnExit(boolean)`**, **`dump(Path)`**, **`stop()`** và **`close()`**. Nội dung áp dụng từ Java 11 đến JDK hiện đại, không dùng tùy chọn kích hoạt thương mại của JFR trên JDK 8 cũ. Ví dụ chạy thật đã được kiểm bằng biên dịch `javac --release 11`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Thiết lập thời gian ghi cố định để recording **tự dừng**, thay vì để chạy vô thời hạn.
2. Chọn **đường dẫn file `.jfr`** sẽ được ghi **khi recording dừng**, và phân biệt đường dẫn đó với **JFR disk repository** dùng trong lúc ghi.
3. Bật **`setDumpOnExit(true)`** để yêu cầu JFR ghi dữ liệu khi **JVM kết thúc có kiểm soát**, hiểu giới hạn với `SIGKILL`/crash/mất điện.
4. Phân biệt **`dump(Path)`** chụp dữ liệu thủ công với **`setDestination(Path)`** cấu hình đích ghi khi `stop()`.
5. Chọn `setToDisk(true/false)`, `setMaxAge`, `setMaxSize` để cân bằng retention, RAM, I/O và dung lượng repository.
6. Theo dõi `RecordingState.NEW`/`DELAYED`/`RUNNING`/`STOPPED`/`CLOSED` mà không lẫn “JVM kết thúc” với “recording đã hết duration”.
7. Dùng `try-with-resources`/`close()` đúng lúc; tránh đóng recording trước khi cần file hoặc vô tình vô hiệu hóa ý đồ dump on exit.
8. Tạo một tệp JFR bằng API, đọc lại sự kiện bằng `RecordingFile`, rồi thử thêm một JVM kết thúc bình thường.
9. Hiểu điều gì xảy ra khi **duration kết thúc trước lúc JVM shutdown**, khi thiếu quyền ghi, disk đầy hoặc container bị cưỡng chế dừng.
10. Viết quy trình production có file path an toàn, giới hạn dữ liệu, kiểm chứng đầu ra và lịch xóa chứng cứ.

## 2. Bốn khái niệm tách biệt: thời hạn, nơi lưu, thời điểm xuất và kết thúc JVM

Một recording có thể được ghi vào **JFR repository** trong lúc ứng dụng chạy, sau đó xuất ra **file `.jfr`**. Đó không phải một file giống nhau trong mọi trường hợp.

~~~text
JVM chạy ứng dụng
       |
       v
Recording.NEW
       |
       | r.setDuration(10 phút)         [khi nào tự dừng?]
       | r.setToDisk(true)              [có dùng disk repository?]
       | r.setMaxAge(...)               [giữ dữ liệu repository bao lâu?]
       | r.setMaxSize(...)              [giữ bao nhiêu byte repository?]
       | r.setDestination(report.jfr)  [nếu dừng, xuất về đâu?]
       | r.setDumpOnExit(true)          [nếu JVM shutdown, xuất không?]
       |
       v
Recording.RUNNING --> các sự kiện được ghi nhận
       |
       +--> r.dump(snapshot.jfr)  [xuất snapshot; vẫn có thể chạy]
       |
       +--> hết duration --------+
       |                          |
       +--> r.stop() -------------+--> dữ liệu xuất ra destination
       |                          |    nếu đã set
       |                          v
       |                       STOPPED / hoàn tất đóng
       |
       +--> JVM shutdown bình thường và dumpOnExit=true
                                  |
                                  v
                          xuất dữ liệu ghi còn hoạt động
                          vào file; JVM kết thúc
~~~

**Lưu ý:** `setDestination` không bắt đầu recording, `setDuration` không chọn file, `setDumpOnExit` không thay `stop()` chủ động, và `setToDisk(true)` **không tự động** có nghĩa bạn đã có một file đầu ra ở đường dẫn mong muốn. Đừng suy luận một flag có tác dụng của flag khác.

### Bảng khái niệm

| Nhu cầu | API Java 11 | Tác dụng |
| --- | --- | --- |
| Bắt đầu ngay | `Recording.start()` | Chuyển recording từ `NEW` sang `RUNNING` |
| Bắt đầu sau thời gian chờ | `scheduleStart(Duration)` | Đặt lịch bắt đầu; trạng thái `DELAYED` |
| Tự dừng sau thời gian xác định | `setDuration(Duration)` | Định thời lượng **chạy** của recording |
| File xuất khi recording dừng | `setDestination(Path)` | Chỉ định file đích cho quá trình stop/duration |
| Xuất khi JVM kết thúc | `setDumpOnExit(true)` | Bật dump vào giai đoạn shutdown bình thường |
| Chụp file trong khi recording còn chạy | `dump(Path)` | Ghi snapshot ra file **không phải stop** |
| Ghi tạm vào disk repository | `setToDisk(true)` | Có thể duy trì dữ liệu lâu hơn memory buffers |
| Giữ lại tối đa một khoảng tuổi | `setMaxAge(Duration)` | Giới hạn tuổi chunks trong disk repository |
| Giữ tối đa một lượng dữ liệu | `setMaxSize(long)` | Giới hạn dung lượng dữ liệu được giữ trong repository |
| Dừng chủ động | `stop()` | Chấm dứt thu thập, không thể restart cùng Recording |
| Giải phóng recording data | `close()` | Giải phóng tài nguyên; trạng thái `CLOSED` |

## 3. Recording được cấu hình trước khi start

Cách khởi tạo có ý nghĩa là:

~~~java
Configuration configuration =
        Configuration.getConfiguration("default");

Recording recording = new Recording(configuration);

recording.setName("service-diagnostics");
recording.setToDisk(true);
recording.setMaxAge(Duration.ofMinutes(20));
recording.setMaxSize(128L * 1024L * 1024L);
recording.setDuration(Duration.ofMinutes(5));
recording.setDestination(Path.of("/secure/jfr/service-diagnostics.jfr"));

recording.start();
~~~

**Đoạn minh họa, không phải chương trình độc lập**: cần imports, thư mục `/secure/jfr` đã được cấp quyền, xử lý `IOException`/JFR exceptions và lifecycle `stop/close` thích hợp.

Javadoc `Recording.start()` khuyến nghị **thiết lập options và event settings trước khi gọi start**. Cấu hình trước giúp trạng thái recording nhất quán trong dữ liệu phân tích và có thể tránh thay đổi settings giữa chừng.

### Tại sao dùng Configuration.getConfiguration("default")?

- `new Recording()` tạo recording **không có event settings ban đầu**; rất dễ có file nhưng thiếu những sự kiện mong đợi.
- `new Recording(Configuration.getConfiguration("default"))` áp dụng cấu hình `default.jfc` do JDK cung cấp. Đây thường là điểm khởi đầu hợp lý cho monitoring.
- `"profile"` có thể thu thêm events/stack samples và làm overhead cao hơn. Không bật profile dài hạn chỉ vì muốn file “đầy dữ liệu”.
- Khi cần custom event, bạn có thể `recording.enable(MyEvent.class)` một cách có chủ đích.
- Không giả định mọi event luôn xuất hiện: một event có thể chưa được bật, không đạt threshold hoặc workload không phát sinh.

Một bản ghi hữu ích phải có đúng **settings + khoảng thời gian + nơi lưu + thông tin tải hệ thống**, chứ không chỉ tạo được file trống/nhỏ.

## 4. Vòng đời chính xác: NEW, DELAYED, RUNNING, STOPPED, CLOSED

`jdk.jfr.RecordingState` có các trạng thái chính:

| State | Khi nào gặp | Điều được phép suy luận |
| --- | --- | --- |
| `NEW` | Vừa tạo `Recording`, chưa start/schedule | Có thể cấu hình và start |
| `DELAYED` | Đã `scheduleStart(delay)` | Recording sẽ bắt đầu sau delay nếu không bị hủy/đóng |
| `RUNNING` | Đã start thành công, đang thu thập dữ liệu | Có thể `dump(...)` snapshot hoặc `stop()` |
| `STOPPED` | Recording đã ngừng thu thập | Không thể start lại cùng object; có thể dump nếu data còn được giữ |
| `CLOSED` | Đã giải phóng dữ liệu/tài nguyên | Không thể dùng như recording hoạt động |

Ví dụ kiểm tra:

~~~java
RecordingState state = recording.getState();

if (state == RecordingState.RUNNING) {
    recording.dump(snapshotPath);
}
~~~

**Đoạn minh họa**, cần `recording` đang có, `snapshotPath` là `Path` cho phép ghi.

### Sự khác nhau giữa stop và close

- `stop()` **dừng thu thập**. Một recording đã stop **không được restart**.
- Khi **không có destination**, Javadoc nói JFR giữ dữ liệu của recording cho đến khi `close()`; bạn có thể `dump(Path)` nếu trạng thái hợp lệ.
- Khi **có destination**, Javadoc mô tả khi stop, dữ liệu được sao chép tới destination và recording **được đóng sau khi sao chép thành công**.
- `close()` giải phóng toàn bộ dữ liệu gắn với Recording; **không đồng nghĩa “cứ close là tự tạo file”** nếu bạn chưa định nghĩa cách xuất.
- `try-with-resources` tự gọi `close()` khi ra khỏi scope; cần đặt thời điểm kết thúc scope **sau thao tác ghi file mà bạn muốn**.

**Không viết code dựa vào việc phải đọc ngay `CLOSED` ở cùng một thời điểm cố định sau auto-stop**. Quan sát thực tế có thể bắt được `STOPPED` ở giai đoạn hoàn tất; hãy xác minh outcome bằng file và phân tích sự kiện, không chỉ bằng state.

## 5. setDuration(Duration): giới hạn thời gian thu thập

~~~java
recording.setDuration(Duration.ofSeconds(30));
recording.start();
~~~

Đây là đoạn minh họa. Khi `start` thành công, JFR sẽ tự kết thúc recording sau **khoảng thời lượng được cấu hình**, không nhất thiết ứng dụng cũng kết thúc.

### Hợp đồng đáng chú ý

- `getDuration()` trả duration đã cấu hình, hoặc **`null` nếu chưa đặt**.
- Nếu không đặt, recording không có giới hạn thời lượng từ option đó. Một recording chạy liên tục phải có lifecycle/retention được quản lý.
- `setDuration` có thể ném `IllegalStateException` khi recording đã `STOPPED` hoặc `CLOSED`.
- Javadoc khuyến nghị đặt duration **trước `start()`** để nhất quán, dù signature hỗ trợ điều chỉnh ở một số trạng thái.
- Duration là **thời lượng chạy recording**, không tự động là timeout của `recording.dump(...)`, thời gian JVM sống hoặc hạn xử lý một request.
- Khi duration hết, recording dừng theo cơ chế JFR; nếu đã `setDestination(file)`, đường dẫn được dùng cho việc xuất khi dừng.
- Duration rất ngắn có thể bỏ lỡ hiện tượng cần quan sát; chọn cửa sổ bao phủ phần workload được điều tra.
- Với duration dài, cân nhắc `setMaxAge`/`setMaxSize`, disk capacity và schedule/retention.

### Nếu ứng dụng kết thúc trước khi hết duration?

Nếu JVM kết thúc có kiểm soát **trước** mốc duration:

- `setDuration(...)` **không tự bảo đảm file sẽ được xuất**.
- Nếu recording còn đang chạy và `setDumpOnExit(true)` được bật, JFR sẽ cố ghi dữ liệu khi JVM shutdown.
- Nếu ứng dụng chủ động `stop()` trước khi thoát và có destination, file được tạo theo đường stop.
- Nếu bị `SIGKILL`, `Runtime.halt`, container mất đột ngột hoặc mất điện, không được xem auto-dump là một bảo đảm.

**Phân biệt hai “đồng hồ”:** đồng hồ duration của Recording và thời điểm kết thúc của process JVM.

## 6. scheduleStart(Duration) khác setDuration(Duration)

Một tính năng dễ nhầm:

~~~java
recording.setDuration(Duration.ofSeconds(30));
recording.scheduleStart(Duration.ofSeconds(10));
~~~

**Mã minh họa**: đặt lịch bắt đầu sau 10 giây, và sau khi recording bắt đầu, nó chạy với thời lượng 30 giây. Hai duration có vai trò khác nhau:

- `scheduleStart(10s)`: trì hoãn **điểm bắt đầu**, đưa state vào `DELAYED`.
- `setDuration(30s)`: độ dài **khoảng chạy**.
- Không gọi `start()` lần nữa khi recording đã `DELAYED`, trừ khi API state cho phép theo hợp đồng mà bạn thực sự đã kiểm. `scheduleStart` yêu cầu `NEW`.
- Nếu ứng dụng dừng trước mốc khởi chạy, recording có thể chưa phát sinh event nào.
- `delay` không phải “sau 10 giây tự lưu file”; việc lưu phụ thuộc destination/dumpOnExit và thời điểm stop.

Đối với bài học và test, thường dùng `start()` ngay cho đơn giản, chỉ dùng `scheduleStart` nếu bạn có nhu cầu đo một thời đoạn cụ thể.

## 7. setDestination(Path): file được ghi khi recording dừng

~~~java
Path destination = Path.of("/secure/jfr/incident-2026-11-07.jfr");

recording.setDestination(destination);
recording.start();

// Sau khi ghi các sự kiện cần thiết:
recording.stop();
~~~

**Đoạn minh họa**. `setDestination` thiết lập file cuối, và **việc ghi file xảy ra khi recording dừng**, không phải vì vừa gọi setter.

### Những chi tiết cần hiểu

1. `getDestination()` trả `Path` đã cấu hình, hoặc **`null`** khi chưa có.
2. `setDestination(null)` có nghĩa **không tự ghi ra destination lúc stop**. Data có thể còn trong recording đến khi close, và bạn có thể dùng `dump(Path)` thủ công.
3. `setDestination(Path)` có thể ném **`IOException` nếu đường dẫn không ghi được**. Lỗi I/O/disk có thể xảy ra sau đó; xử lý cả giai đoạn xuất cuối.
4. Không đặt destination sau khi đã `STOPPED` hoặc `CLOSED`: Javadoc cho biết sẽ ném `IllegalStateException`.
5. Khi có destination và stop thành công, JFR ghi dữ liệu vào file, rồi quản lý/đóng recording theo contract. Đừng tự gọi `dump` thêm trên recording đã đóng để “đảm bảo”; việc đó có thể thất bại.
6. Đường dẫn phải tồn tại về mặt **thư mục cha**, có permission, quota, đủ dung lượng. Tên file nên duy nhất theo incident/deployment/time nếu nhiều recording cùng xuất.
7. Không đặt file JFR tại thư mục public/static website hoặc thư mục dùng chung không hạn chế quyền.
8. `destination` khác **JFR repository**, dù cả hai đều có thể ở disk.

### Nếu không đặt destination?

~~~java
try (Recording recording = new Recording(
        Configuration.getConfiguration("default"))) {

    recording.start();
    // Chạy workload cần ghi...
    recording.stop();
    recording.dump(Path.of("/secure/jfr/manual-final.jfr"));
}
~~~

**Mã minh họa** trong method có try/catch checked exceptions. Đây là cách hợp lệ khi **không có destination**, vì sau stop dữ liệu vẫn có thể được giữ cho đến close.

Không chuyển `recording.close()` lên trước `recording.dump(...)`: close giải phóng dữ liệu và không đảm bảo còn gì để xuất.

## 8. dump(Path): xuất snapshot mà không cần stop recording

~~~java
recording.start();

// Trong lúc recording đang chạy:
recording.dump(Path.of("/secure/jfr/snapshot.jfr"));

// Recording có thể tiếp tục phát sinh event sau snapshot.
~~~

**Mã minh họa**; ghi snapshot có thể cần thời gian/I/O và permission. Theo Javadoc, `dump(Path)` yêu cầu recording **đã được bắt đầu**, nhưng **không nhất thiết phải dừng**.

| Thao tác | Có tự dừng thu thập? | Có cần destination đã set? | File xuất ra đâu? |
| --- | --- | --- | --- |
| `setDestination(p)` | Không | Chính nó là setter | Chưa ghi file ngay; p dùng khi stop |
| `dump(p)` khi RUNNING | **Không** | **Không** | Ghi ngay snapshot vào p |
| `stop()` khi có destination | **Có** | Có | Ghi vào destination đã set |
| `stop()` khi không có destination | **Có** | Không | Không tự chọn một file output |
| `close()` | Chấm dứt/giải phóng | Không | Không thay dump/stop semantics |
| JVM shutdown và dumpOnExit | JVM kết thúc | Có thể đặt destination | JFR cố xuất dữ liệu còn hoạt động vào file theo policy |

**`dump(Path)` không phải lệnh đổi `RecordingState` sang `STOPPED`.** Một ứng dụng vận hành có thể snapshot JFR khi có incident mà giữ recording chạy để tiếp tục thu sự kiện.

### Vì sao không dump liên tục mỗi giây?

- Mỗi lần dump tạo I/O và file có thể lớn; nếu không giới hạn sẽ nhanh đầy disk.
- File đã ghi có thể chứa nhiều sự kiện trùng khi hai snapshot cùng lấy dữ liệu từ một recording có retention dài.
- Hãy đặt giới hạn số snapshot, kích thước, quyền và lịch dọn dẹp.
- Nếu cần dữ liệu tại từng khoảng chính xác, cân nhắc API `getStream(Instant, Instant)` hoặc phân tách recording có cấu hình phù hợp; Javadoc lưu ý stream có thể chứa một ít dữ liệu ngoài khoảng yêu cầu.

## 9. setDumpOnExit(true): ghi khi JVM kết thúc

~~~java
Recording recording = new Recording(
        Configuration.getConfiguration("default"));

recording.setDestination(Path.of("/secure/jfr/on-exit.jfr"));
recording.setDumpOnExit(true);
recording.start();

// Ứng dụng tiếp tục làm việc; đến lúc JVM shutdown bình thường,
// JFR cố xuất dữ liệu recording còn đang chạy.
~~~

**Đây là đoạn minh họa**, không phải chương trình độc lập; cần hoàn tất quy trình quản lý resource của ứng dụng.

### Những việc setDumpOnExit KHÔNG bảo đảm

- **Không** bảo đảm file tồn tại nếu process bị kill không cho JVM shutdown thông thường.
- **Không** thay thế chiến lược dump khi incident cần dữ liệu ngay: file exit có thể không có cho tới khi JVM kết thúc.
- **Không** bảo đảm ghi đủ dữ liệu nếu disk đầy/quyền ghi bị từ chối hoặc thời gian dừng process bị giới hạn.
- **Không** có nghĩa `setDuration(30s)` sẽ đợi đến khi JVM exit. Nếu duration kết thúc trước, recording đã stop và có thể đã xuất vào destination.
- **Không** có nghĩa application code có thể đóng recording từ sớm rồi kỳ vọng shutdown sẽ tự ghi lại data.
- **Không** biến `System.exit` hoặc cleanup application thành một bước được đảm bảo sẽ giải phóng hết mọi tài nguyên trong trường hợp crash nghiêm trọng.

### Vì sao phải tránh try-with-resources cho ví dụ exit-mode?

Nếu bạn viết:

~~~java
try (Recording r = new Recording(
        Configuration.getConfiguration("default"))) {

    r.setDumpOnExit(true);
    r.start();

    // Một vài thao tác, sau đó ra khỏi scope...
} // Tự close Recording tại đây.
~~~

Đây là **đoạn mã minh họa sai mục đích** nếu bạn trông đợi recording tiếp tục chạy cho đến lúc JVM shutdown. `try-with-resources` đóng recording **ngay khi rời scope**, trước khi process thực sự kết thúc; khi đã close, dữ liệu không còn được giữ để dump vào giai đoạn shutdown.

**Quy tắc:** dùng `try-with-resources` cho recording **sở hữu bởi một tác vụ hữu hạn** có dump/stop trước khi thoát; dùng một lifecycle manager ở cấp ứng dụng cho recording phải **sống tới shutdown**, có quy tắc chủ động stop/dump và cleanup rõ ràng. Không để đối tượng Recording chạy mãi không kiểm soát chỉ vì muốn dump on exit.

## 10. Ba tình huống kết thúc: duration, graceful shutdown và abrupt termination

| Tình huống | Recording được cấu hình | Kỳ vọng phù hợp | Không được kết luận |
| --- | --- | --- | --- |
| Duration hết trước khi JVM exit | `setDuration` + `setDestination` | Recording tự stop, file được xuất theo destination | `dumpOnExit` sẽ tạo thêm một bản sao khi exit |
| Ứng dụng gọi `stop` trước exit | `setDestination` | Dữ liệu được xuất tại stop | Phải đợi JVM exit mới có file |
| Ứng dụng dừng bình thường trước duration | `setDumpOnExit(true)` + destination | JFR cố dump trong JVM shutdown | File chắc chắn tồn tại dù disk lỗi |
| JVM chạy liên tục | `dumpOnExit=true` | File exit **chưa xuất** nếu chưa shutdown | Có thể phân tích file ngay |
| Container gửi SIGTERM có grace period đủ | `dumpOnExit=true` | Có thể hoàn thành shutdown/dump theo JVM + OS | Mọi platform/entrypoint chắc chắn xử lý như nhau |
| `SIGKILL` hoặc timeout cưỡng chế container | Bất kỳ flags | Có thể không dump file cuối | JFR chắc chắn phục hồi dữ liệu chỉ bằng exit flag |
| JVM/process crash nghiêm trọng hoặc mất điện | Bất kỳ flags | Không có bảo đảm cleanup/dump | File JFR luôn đầy đủ, không bị cắt |
| Recording bị `close()` trước exit | `dumpOnExit=true` | Không còn một recording RUNNING để auto dump | Bật flag từ trước là đủ |
| Đường dẫn destination không ghi được | `setDestination`/`dumpOnExit` | Lỗi I/O, có thể thiếu file | Không cần cảnh báo/monitor lỗi |

**Ứng dụng quan trọng cần vừa recording bounded vừa có cơ chế snapshot chủ động**, thay vì phụ thuộc duy nhất vào một dấu hiệu shutdown.

## 11. Ví dụ Java 11 hoàn chỉnh: duration và dump-on-exit

Ví dụ sau dùng **một file Java và ba chế độ chạy**:

- `duration`: đặt duration **800 ms**, destination, tạo 3 custom events, chờ recording tự dừng, xác nhận file và đếm sự kiện.
- `exit`: tạo recording không có duration, bật `setDumpOnExit(true)`, tạo 2 events, **không stop/close**, cho process Java kết thúc bình thường.
- `verify`: mở file được tạo bởi process `exit` (tức là ở **một process Java khác**) và kiểm 2 sự kiện.

Các custom events dùng tên `lesson.LifecycleMarker`, không mang dữ liệu nhạy cảm. Dùng `Configuration.getConfiguration("default")` để có settings hợp lý và `enable(Marker.class)` để bật event thử nghiệm.

Tạo file **`JfrLifecycleDemo.java`**:

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.RecordingState;
import jdk.jfr.consumer.RecordingFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Duration;

public class JfrLifecycleDemo {

    @Name("lesson.LifecycleMarker")
    static class Marker extends Event {
        int sequence;
    }

    static void emit(int n) {
        for (int i = 1; i <= n; i++) {
            Marker event = new Marker();
            event.sequence = i;
            event.commit();
        }
    }

    static long markerCount(Path file) throws Exception {
        long count = 0;

        try (RecordingFile reader = new RecordingFile(file)) {
            while (reader.hasMoreEvents()) {
                if ("lesson.LifecycleMarker".equals(
                        reader.readEvent().getEventType().getName())) {
                    count++;
                }
            }
        }

        return count;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: duration|exit|verify <file.jfr>");
        }

        Path file = Paths.get(args[1]).toAbsolutePath();

        if ("duration".equals(args[0])) {
            try (Recording recording = new Recording(
                    Configuration.getConfiguration("default"))) {

                recording.setName("duration-demo");
                recording.setToDisk(true);
                recording.setMaxSize(16L * 1024 * 1024);
                recording.setDuration(Duration.ofMillis(800));
                recording.setDestination(file);
                recording.enable(Marker.class);
                recording.start();

                emit(3);

                // Tránh đợi vô hạn. Chấp nhận STOPPED hoặc CLOSED
                // vì quá trình auto-stop/copy/close có thể có
                // bước chuyển trạng thái.
                long deadline = System.nanoTime()
                        + Duration.ofSeconds(8).toNanos();

                while (recording.getState() == RecordingState.RUNNING
                        && System.nanoTime() < deadline) {
                    Thread.sleep(50);
                }

                boolean finished =
                        recording.getState() == RecordingState.STOPPED
                        || recording.getState() == RecordingState.CLOSED;

                System.out.println(
                        "duration.finished=" + finished);
                System.out.println(
                        "duration.fileExists="
                                + Files.isRegularFile(file));
                System.out.println(
                        "duration.events=" + markerCount(file));
            }

        } else if ("exit".equals(args[0])) {
            // Recording sở hữu bởi process, không đóng trước exit.
            Recording recording = new Recording(
                    Configuration.getConfiguration("default"));

            recording.setName("exit-demo");
            recording.setToDisk(true);
            recording.setMaxSize(16L * 1024 * 1024);
            recording.setDestination(file);
            recording.setDumpOnExit(true);
            recording.enable(Marker.class);
            recording.start();

            emit(2);

            System.out.println(
                    "exit.dumpOnExit=" + recording.getDumpOnExit());

            // Không stop/close: JVM sẽ shutdown bình thường
            // khi method main hoàn tất và không còn thread khác.

        } else if ("verify".equals(args[0])) {
            System.out.println(
                    "exit.fileExists=" + Files.isRegularFile(file));
            System.out.println(
                    "exit.events=" + markerCount(file));

        } else {
            throw new IllegalArgumentException(
                    "Unknown mode: " + args[0]);
        }
    }
}
~~~

### Biên dịch và chạy

Tại thư mục có tệp `JfrLifecycleDemo.java`, tạo một thư mục lưu output riêng, giới hạn quyền truy cập nếu sử dụng trong môi trường chứa dữ liệu thật:

~~~bash
mkdir jfr-output
javac --release 11 JfrLifecycleDemo.java
java JfrLifecycleDemo duration jfr-output/duration.jfr
java JfrLifecycleDemo exit jfr-output/on-exit.jfr
java JfrLifecycleDemo verify jfr-output/on-exit.jfr
~~~

Chạy lần đầu với **hai đường dẫn file chưa tồn tại**, thư mục cha đã có và ghi được. Trên Windows có thể thay dấu gạch chéo đường dẫn cho hợp môi trường; JDK chấp nhận relative paths đã được xử lý qua `Paths.get`.

### Stdout đã kiểm chứng bằng thực thi JDK với javac --release 11

Ở **lần chạy mode duration**:

~~~text
duration.finished=true
duration.fileExists=true
duration.events=3
~~~

Ở **lần chạy mode exit**:

~~~text
exit.dumpOnExit=true
~~~

Ở **lần chạy mode verify sau khi process exit đã kết thúc**:

~~~text
exit.fileExists=true
exit.events=2
~~~

**Phân tích từng dòng:**

1. `duration.finished=true`: recording đã hết duration và đạt một trạng thái dừng/đóng phù hợp. Không chốt stdout vào `STOPPED` hoặc `CLOSED` cụ thể vì đó không phải điều bạn cần kiểm về chất lượng artifact.
2. `duration.fileExists=true`: có tệp đích đã cấu hình. `duration.events=3`: tệp này đọc được bằng `RecordingFile` và chứa 3 custom events.
3. `exit.dumpOnExit=true`: recording đã được bật cờ dump on exit. **Dòng này một mình không chứng minh đã ghi file**; cần chạy process thứ hai.
4. `exit.fileExists=true`: sau khi JVM ghi thoát bình thường, tệp được tạo tại destination.
5. `exit.events=2`: file hợp lệ và chứa 2 events từ process trước, không phải chỉ có một file rỗng.
6. Các số 3 và 2 là **số events do fixture tự tạo**; số lượng JDK events phụ thêm phụ thuộc JDK, settings và workload. Vì vậy program chỉ đếm đúng event type `lesson.LifecycleMarker`.
7. `setMaxSize(16 MiB)` trong demo giới hạn repository được giữ, **không phải cam kết mọi file cuối chính xác không vượt 16 MiB** hay bảo đảm tài nguyên disk của hệ thống luôn đủ.

**Lưu ý production:** mode `exit` cố ý để Recording còn hoạt động đến shutdown để minh họa tính năng; ứng dụng thật nên có một lifecycle manager có chủ sở hữu, xử lý shutdown/grace period rõ ràng và snapshot thủ công khi cần. Đừng dùng mẫu này để tạo nhiều recording không bao giờ được đóng trong long-running server.

## 12. Ví dụ Java 11: dump thủ công trong lúc recording vẫn chạy

Để thấy rõ khác biệt giữa `dump(Path)` và `stop()`, chương trình này tạo một event, dump trong khi RUNNING, xác nhận trạng thái vẫn RUNNING, sau đó mới stop và đóng.

Tạo file **`JfrManualDumpDemo.java`**:

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.RecordingState;
import jdk.jfr.consumer.RecordingFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public class JfrManualDumpDemo {

    @Name("lesson.ManualMarker")
    static class Marker extends Event {
        int value;
    }

    public static void main(String[] args) throws Exception {
        Path file = Paths.get(args[0]);

        try (Recording recording = new Recording(
                Configuration.getConfiguration("default"))) {

            recording.setToDisk(true);
            recording.setMaxSize(16L * 1024 * 1024);
            recording.enable(Marker.class);
            recording.start();

            Marker event = new Marker();
            event.value = 7;
            event.commit();

            // Xuất snapshot mà không stop.
            recording.dump(file);

            System.out.println(
                    "dump.keepsRunning="
                            + (recording.getState()
                                    == RecordingState.RUNNING));

            recording.stop();
            System.out.println(
                    "stop.state=" + recording.getState());
        }

        long count = 0;
        try (RecordingFile reader = new RecordingFile(file)) {
            while (reader.hasMoreEvents()) {
                if ("lesson.ManualMarker".equals(
                        reader.readEvent().getEventType().getName())) {
                    count++;
                }
            }
        }

        System.out.println(
                "dump.fileExists=" + Files.isRegularFile(file));
        System.out.println(
                "dump.customEvents=" + count);
    }
}
~~~

Chạy với destination chưa tồn tại:

~~~bash
javac --release 11 JfrManualDumpDemo.java
java JfrManualDumpDemo jfr-output/manual.jfr
~~~

**Stdout đã được kiểm chứng trên JDK:**

~~~text
dump.keepsRunning=true
stop.state=STOPPED
dump.fileExists=true
dump.customEvents=1
~~~

Điểm then chốt: **`dump(...)` không làm recording dừng**. Mục tiêu file đã được tạo và đọc được dù recording vẫn RUNNING ngay sau thao tác dump. Đây là lựa chọn thích hợp khi bạn muốn chụp hiện tượng giữa lúc ứng dụng còn hoạt động.

## 13. setToDisk, maxAge và maxSize: quản lý nơi giữ dữ liệu

Cần phân biệt **retention repository** với **đường dẫn file cuối**.

### 13.1. setToDisk(true)

~~~java
recording.setToDisk(true);
~~~

Theo Javadoc `Recording`, khi true, dữ liệu recording được flush vào **disk repository** trong quá trình ghi thay vì bị giới hạn chỉ bởi memory buffers. Mặc định của `Recording.isToDisk()` là **true** nếu không có giá trị riêng; tuy nhiên vẫn nên cấu hình tường minh khi làm ví dụ và thiết kế policy.

**Không nhầm `setToDisk(true)` với `setDestination(...)`**. Một cái nói cách giữ dữ liệu tạm khi recording đang chạy; cái kia nói file output mà JFR ghi khi recording dừng.

### 13.2. setToDisk(false)

~~~java
recording.setToDisk(false);
~~~

Lúc này dữ liệu bị giới hạn theo các buffers trong memory. Ưu điểm có thể ít ghi repository disk hơn; nhưng:

- Dữ liệu cũ có thể không được giữ đủ trong một recording dài.
- Không coi recording dài hơn 30 phút sẽ giữ mọi events.
- `Recording.getSize()` mô tả kích thước trong disk repository, nên có thể trả 0 khi không dùng disk repository; **0 không chứng minh không có event**.
- Không dùng `setToDisk(false)` chỉ để bảo đảm dump on exit luôn đầy đủ; ở crash/kill, RAM có thể mất.

### 13.3. setMaxAge(Duration)

~~~java
recording.setMaxAge(Duration.ofMinutes(20));
~~~

Theo Javadoc, chunks trong disk repository **cũ hơn giới hạn tuổi** sẽ bị JVM loại khỏi dữ liệu giữ lại. Dùng để giữ **cửa sổ gần đây** trong một recording chạy lâu.

### 13.4. setMaxSize(long)

~~~java
recording.setMaxSize(128L * 1024 * 1024);
~~~

`maxSize` tính theo **byte**; khi repository vượt mức được giữ, JVM có thể loại bỏ các chunks cũ hơn để dành chỗ cho chunks mới. Giá trị **0** theo contract mang ý nghĩa **không giới hạn**. Không dùng 0 cho recording vô hạn nếu không có quota/giám sát dung lượng.

### 13.5. Cả hai giới hạn phối hợp thế nào?

- `maxAge` hạn chế tuổi dữ liệu giữ lại.
- `maxSize` hạn chế dung lượng dữ liệu được giữ lại.
- Nếu cả hai không được đặt, recording ghi ra repository có thể tiếp tục tăng mà không có mức retention hữu ích.
- Giới hạn repository không nhất thiết là **hard quota** cho tổng filesystem usage, số file snapshot, file output cuối, JVM events của recording khác hoặc mọi temporary chunks.
- Đặt **volume quota, alert dung lượng, retention artifact và cleanup** ở tầng triển khai; không chỉ dựa vào hai setter.
- Nếu recording bị dừng sau khi các chunks cũ đã bị loại, file `.jfr` không thể chứa lại những events bị loại trước đó.

### Ví dụ tính chính sách

Giả sử một API gateway cần giữ **20 phút gần nhất** và tối đa **128 MiB** dữ liệu repository cho một recording:

~~~java
recording.setToDisk(true);
recording.setMaxAge(Duration.ofMinutes(20));
recording.setMaxSize(128L * 1024 * 1024);
recording.setDumpOnExit(true);
~~~

**Đoạn minh họa**. Vẫn phải kiểm recording có destination hoặc quy tắc file auto-name thích hợp, disk path hợp lệ và chính sách bảo vệ chứng cứ.

## 14. Chọn đích lưu: đường dẫn, quyền và an toàn vận hành

Một file JFR có thể chứa **stack traces, tên lớp, tên method, tên thread, đường dẫn I/O, thông số JVM** và **dữ liệu trong custom events**. Với ứng dụng nhiều tenant, nó có thể phản ánh cấu trúc nội bộ và các trường có tính nhạy cảm.

### Quy tắc đường dẫn

- Dùng thư mục **không public**, quyền truy cập chỉ cho service/operator được phép.
- Chọn file name duy nhất theo deployment/recording/session ID; tránh hai JVM cùng ghi một file.
- Dùng **absolute path** cho production để giảm nhập nhằng working directory.
- Kiểm thư mục cha đã tồn tại và JVM có quyền ghi, đủ disk space và quota.
- Đừng ghi vào đường dẫn nhận trực tiếp từ đầu vào người dùng không tin cậy.
- Tránh ghi tệp JFR vào persistent volume dùng chung không hạn chế quyền.
- Có chính sách backup, encryption, retention và xóa sau khi xử lý.
- Cân nhắc I/O ảnh hưởng ứng dụng khi ghi file rất lớn trong thời gian ngắn.

### Mẫu tạo tên file duy nhất

~~~java
Path directory = Path.of("/secure/jfr");

String fileName = "incident-"
        + java.util.UUID.randomUUID()
        + ".jfr";

Path destination = directory.resolve(fileName);
~~~

**Đoạn minh họa**, không tự tạo thư mục. `UUID` hỗ trợ tạo tên khác nhau, nhưng **không phải ACL, cơ chế xác thực hoặc bảo đảm quyền file**. Dùng trong môi trường đã phân quyền và có policy riêng.

### Kiểm file thực sự ghi được

Không chỉ gọi:

~~~java
System.out.println(recording.getDestination());
~~~

Lệnh trên chỉ in **path đã cấu hình**; chưa chứng minh file tồn tại, có dữ liệu hoặc nội dung hợp lệ.

Để kiểm outcome, hãy xác nhận:

1. Recording đã stop hoặc được dump;
2. `Files.isRegularFile(path)` và `Files.size(path)` hợp lý;
3. `RecordingFile`/`jfr summary` có thể đọc file;
4. Các custom/JVM events cần thiết có mặt và thuộc time window mong muốn;
5. File được bảo vệ/retained đúng policy;
6. Mọi lỗi tại `setDestination`, `stop` và `dump` được quan sát/alert thích hợp.

## 15. Liên hệ API và cờ khởi động JVM

Không nhất thiết viết code Java để sử dụng JFR. Java 11+ còn có cờ khởi động `-XX:StartFlightRecording=...`. Đây là lựa chọn thuận tiện nếu không thể chỉnh code ứng dụng.

### Ví dụ recording có thời hạn khi JVM khởi chạy

~~~bash
java -XX:StartFlightRecording=name=ShortCapture,settings=default,duration=60s,filename=/secure/jfr/short-capture.jfr -jar app.jar
~~~

**Lệnh minh họa**: dùng một JDK hỗ trợ JFR, đường dẫn file có quyền ghi và `app.jar` của ứng dụng thực. Cờ `duration=60s` làm recording kết thúc theo thời hạn; `filename` chọn file đầu ra. Không tự suy ra ứng dụng kết thúc sau 60 giây.

### Ví dụ giữ gần đây và dump khi JVM shutdown

~~~bash
java -XX:StartFlightRecording=name=ServiceRing,settings=default,disk=true,maxage=20m,maxsize=128m,dumponexit=true,filename=/secure/jfr/service-exit.jfr -jar app.jar
~~~

Lệnh này minh họa policy tương đương với API **setToDisk + setMaxAge + setMaxSize + setDumpOnExit + setDestination**. Khi JVM kết thúc bình thường trong lúc recording còn chạy, JFR cố xuất file vào đường dẫn đã chỉ định. File xuất khi exit vẫn không được bảo đảm nếu process bị kill cưỡng chế/disk lỗi.

**Không** dùng `-XX:+UnlockCommercialFeatures` và các bước licensing JFR của tài liệu JDK 8 Oracle cũ. Java 11+ có JFR API `jdk.jfr` sử dụng trực tiếp; các cờ thương mại cũ không còn là hướng dẫn hiện hành.

### Nếu không nêu filename?

Với cờ JVM/JFR có `dumponexit=true` nhưng không có filename, JDK có thể tự sinh tên file theo PID, recording ID và timestamp tại working directory. Điều này dễ gây khó tìm, rò file hoặc ghi vào nơi không có quyền. Trong production, hãy **chỉ định đường dẫn rõ**, không để output mặc định nếu không kiểm soát cwd.

### Đừng bật duplicate recordings ngoài ý muốn

Nếu ứng dụng **đã tạo Recording qua API**, và bạn thêm `-XX:StartFlightRecording`, có thể có **hai recording cùng tồn tại**, tăng event volume/overhead và tạo hai files. Xác nhận `jcmd <PID> JFR.check` hoặc monitoring quản trị trước khi bật thêm một recording từ dòng lệnh.

## 16. Liên hệ API và jcmd khi JVM đang chạy

`jcmd` dùng attach để điều khiển JFR trên JVM phù hợp. Cần quyền OS, namespace, hỗ trợ attach và quyền ghi file của process đích.

### Kiểm những lệnh thực sự có trên JDK mục tiêu

~~~bash
jcmd -l
jcmd <PID> help JFR.start
jcmd <PID> help JFR.dump
jcmd <PID> help JFR.stop
~~~

Đây là **lệnh minh họa**; thay `<PID>` bằng PID đã xác nhận và không chạy trên service không được phép. Tên option/thông tin hỗ trợ có thể khác theo JDK vendor/update; `jcmd help` trên đúng JVM mục tiêu là điểm kiểm tra chính xác.

### Recording bounded

~~~bash
jcmd <PID> JFR.start name=IncidentCapture settings=default duration=2m filename=/secure/jfr/incident.jfr
~~~

Đặt thời hạn để recording tự dừng, file xuất vào destination. Có thể dùng `settings=profile` khi điều tra có thời hạn nhưng cần đánh giá overhead.

### Snapshot khi JVM vẫn chạy

~~~bash
jcmd <PID> JFR.dump name=IncidentCapture filename=/secure/jfr/snapshot.jfr
~~~

Tương tự `Recording.dump(Path)` ở ý nghĩa **xuất snapshot**, không đồng nhất với việc dừng JVM hoặc ứng dụng.

### Dừng thủ công

~~~bash
jcmd <PID> JFR.stop name=IncidentCapture
~~~

**Lưu ý:** Không tự coi `JFR.stop` tương đương `Runtime.exit` hoặc `Recording.close` của một object Java do code sở hữu. Các công cụ có thể điều khiển recording qua lớp management, nên khi tích hợp hãy thống nhất ownership và kiểm kết quả/permission.

## 17. Chạy trong container/Kubernetes: graceful vs forced exit

Hệ thống container khiến tính năng “dump khi ứng dụng kết thúc” cần được đánh giá đặc biệt.

### Shutdown bình thường

1. Orchestrator yêu cầu dừng process.
2. JVM nhận tín hiệu được xử lý như shutdown bình thường, application shutdown hooks/lifecycle được thực thi trong giới hạn cho phép.
3. JFR có cơ hội hoàn tất dump on exit.
4. File tồn tại **trên filesystem của container hoặc volume đã mount**.
5. Artifact được operator/tool thu thập theo policy nếu vẫn còn truy cập được.

### Khi grace period quá ngắn

Nếu JVM cần vài giây để dump file lớn nhưng container chỉ có rất ít thời gian trước khi bị kill cưỡng chế:

- File có thể không được ghi hoặc không hoàn chỉnh;
- Tiến trình có thể bị `SIGKILL` trước khi shutdown hooks/JFR hoàn tất;
- Nếu file nằm trên ephemeral filesystem, pod bị xóa có thể khiến artifact không còn truy cập được.

**Không suy luận “có dumpOnExit là crash-proof”**. Dùng grace period hợp lý, persistent volume được kiểm soát, hoặc cơ chế snapshot on-demand để đảm bảo khả năng điều tra.

### Chiến lược thực tế

- Với service cần postmortem, cân nhắc **bounded continuous recording** và **snapshot theo cảnh báo** (ví dụ `jcmd JFR.dump` hoặc API).
- Khi shutdown có kiểm soát, service có thể **chủ động stop/dump** theo lifecycle manager rồi xác minh file thành công.
- Giữ `dumpOnExit` như **một lớp dự phòng** cho trường hợp ứng dụng rời process mà không chủ động stop.
- Giới hạn file size, số bản snapshot, quota disk và retention.
- Test thật việc rolling restart, scale-down, startup crash và out-of-disk trong staging.
- Không dùng JFR file thô làm public diagnostic endpoint.

## 18. Lỗi thường gặp và cách xử lý

| Vấn đề | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `getDestination()==null` | Chưa gọi `setDestination` | Chọn file cuối hoặc dùng `dump(Path)` thủ công |
| Recording tự dừng nhưng không thấy file | Không đặt destination, file ghi sai nơi, quyền ghi lỗi | Kiểm getDestination, logs, path, state và process cwd |
| `setDestination` ném `IOException` | Thư mục cha không tồn tại, thiếu quyền, file không ghi được | Tạo thư mục an toàn, cấp quyền và test filesystem |
| `dump(Path)` thất bại | Recording chưa start/đã close, path lỗi, disk đầy | Kiểm state, path/quota và exception |
| `stop()` ném `IllegalStateException` | Không ở trạng thái có thể stop | Kiểm lifecycle, không stop hai lần mù quáng |
| `start()` ném `IllegalStateException` | Đã start hoặc Recording đã close | Mỗi Recording start một lần, tạo recording mới nếu cần |
| `setDuration` sau STOPPED/CLOSED bị từ chối | Thay cấu hình quá muộn | Cấu hình trước `start()` |
| `setDestination` sau STOPPED/CLOSED bị từ chối | Đích được đặt quá muộn | Đặt trước, hoặc dùng dump nếu data còn |
| `dumpOnExit=true` nhưng không thấy file | JVM bị cưỡng chế dừng, recording đã close, path lỗi | Phân biệt graceful/forced shutdown, kiểm artifact |
| `duration` hết trước JVM exit | Recording đã stop từ trước | Kiểm file do stop; đừng chờ exit dump thứ hai |
| `try-with-resources` đóng recording quá sớm | Scope kết thúc trước lúc cần exit snapshot | Lifecycle manager cấp app, explicit stop/dump |
| Dùng `setToDisk(false)` nhưng muốn history dài | Memory buffers không giữ toàn bộ events | Dùng disk repository + retention hợp lý |
| `getSize()==0` và nghĩ không có events | No disk repository hoặc chưa flush | Đọc file/RecordingFile, hiểu semantics getSize |
| Recording chiếm nhiều disk | Không có maxAge/maxSize, snapshot quá nhiều | Cap retention, disk quota và cleanup |
| File `.jfr` đọc không được | Ghi dở, copy lỗi, không hoàn tất hoặc corruption | Kiểm lỗi/sha/checksum/copy, thử jfr summary và xem nguồn |
| File có ít events hơn mong đợi | Duration ngắn, event bị disable/threshold, chunks đã bị loại | Kiểm settings, retention và phạm vi thời gian |
| JVM nặng khi bật profile dài | Event volume/stack samples cao | Dùng default hoặc profile ngắn với overhead test |
| Hai recordings dùng cùng destination | Race/đè/khó audit | Tên file duy nhất, phân tách ownership |

**Đừng chỉ catch `Exception` rồi in “JFR failed”**. Phân biệt `IllegalStateException` (lifecycle), `IOException` (file/repository), `IllegalArgumentException` (tham số), `SecurityException` (quyền khi applicable), và lỗi cấu hình JFR trong môi trường thực.

## 19. Kiểm chứng file cuối với RecordingFile và jfr CLI

### Java API

~~~java
try (RecordingFile reader = new RecordingFile(output)) {
    while (reader.hasMoreEvents()) {
        RecordedEvent event = reader.readEvent();
        System.out.println(event.getEventType().getName());
    }
}
~~~

**Đoạn minh họa**, cần import `RecordingFile`, `RecordedEvent` và có `Path output`. Trong ứng dụng, không in mọi event nếu file rất lớn hoặc nội dung nhạy cảm. Lọc event types, aggregate counts/time window và giải phóng resource bằng try-with-resources.

### Công cụ dòng lệnh

~~~bash
jfr summary /secure/jfr/incident.jfr
jfr print --events lesson.LifecycleMarker /secure/jfr/incident.jfr
~~~

`jfr summary` giúp kiểm file hợp lệ, thời lượng/event type và tổng số events. `jfr print` chỉ xuất các events phù hợp; hạn chế dump stdout nếu có payload nhạy cảm.

### Những gì một file tồn tại KHÔNG chứng minh

- Không bảo đảm mọi sự kiện workload đều được ghi (event setting/threshold, buffer/retention).
- Không bảo đảm toàn bộ thời gian hoạt động của JVM được bao phủ.
- Không bảo đảm overhead bằng 0.
- Không bảo đảm file chứa đúng process nếu tên/path có thể bị trùng.
- Không chứng minh file an toàn để chia sẻ ngoài tổ chức.
- Không chứng minh shutdown JFR xảy ra nếu bạn chỉ kiểm một file cũ có sẵn ở path.

Vì vậy khi thu thập chứng cứ, hãy kết hợp **file metadata, tên recording, timestamp, process identity, JDK version và custom event/checkpoint** theo policy.

## 20. Checklist thiết kế cho hệ thống thật

- [ ] Đã xác định recording phục vụ **monitoring liên tục** hay **điều tra có thời hạn**.
- [ ] Dùng `Configuration.getConfiguration("default")` trừ khi có nhu cầu thu thêm event phù hợp.
- [ ] Có `setDuration(...)` cho recording hữu hạn; không để recording “chạy mãi” không kiểm soát.
- [ ] Với recording kéo dài, có `setMaxAge`, `setMaxSize`, quota, alert và retention.
- [ ] Phân biệt **disk repository** (`setToDisk`) với **file đích** (`setDestination`).
- [ ] Đã tạo thư mục cha của destination và kiểm quyền ghi cho process JVM.
- [ ] Tên file riêng cho mỗi incident/process/deployment; không overwrite vô ý.
- [ ] Dùng `dump(Path)` khi cần snapshot không dừng recording.
- [ ] Hiểu khi nào `stop()` tạo file, khi nào cần `dump()` thủ công.
- [ ] Không `close()` trước khi lấy được dữ liệu cần thiết.
- [ ] Nếu dùng `setDumpOnExit(true)`, đã test graceful JVM shutdown thật trên môi trường mục tiêu.
- [ ] Không kỳ vọng dumpOnExit sống sót qua `SIGKILL`/power failure.
- [ ] Nếu dùng Kubernetes, đã xét terminationGracePeriod, volume persistence và cleanup.
- [ ] Có kiểm hậu điều kiện: file hợp lệ, `jfr summary`/`RecordingFile` đọc được, event count hợp lý.
- [ ] File được xử lý như chứng cứ bảo mật, có ACL/encryption/retention.
- [ ] Kiểm version chính xác của JDK/vendor khi dùng `jcmd`/cờ startup.
- [ ] Không dùng hướng dẫn bật license JFR trên JDK 8 cho Java 11+.
- [ ] Không bật recording trùng không chủ ý giữa API/startup flags/jcmd.
- [ ] Có test lỗi path/quota/stop-state/exit-state và quan sát lỗi tương ứng.

## 21. Ma trận kiểm thử chức năng

| Ca kiểm thử | Kịch bản | Điều kiện PASS |
| --- | --- | --- |
| Duration ngắn | `setDuration(800ms)` + destination | Recording tự hoàn tất, file đọc được |
| Destination + auto-stop | `setDestination(path)` trước start | File có events sau stop |
| Destination + manual-stop | `stop()` chủ động | Có artifact tại path đã set |
| Manual dump while running | `dump(path)` khi RUNNING | File đọc được; state vẫn RUNNING ngay sau dump |
| Manual dump after stop (không destination) | `stop()` rồi `dump(path)` | File đọc được trước close |
| Dump-on-exit | `setDumpOnExit(true)`, recording đang RUNNING, JVM thoát bình thường | Process khác mở file và thấy custom events |
| Không có dump on exit | Recording chưa set flag và không stop/dump | Không mặc định chờ có file output |
| Duration hết trước exit | Recording auto-stop trước JVM shutdown | File đã có từ stop, không phụ thuộc exit |
| Recording đóng quá sớm | `close()` trước lúc JVM exit | Không dựa vào exit hook để lưu lại |
| Missing parent directory | Destination ở path không tồn tại | Báo lỗi, không silent success |
| Permission denied | Thư mục không ghi được | Lỗi quan sát được/alert |
| Hết disk/quota | Ghi file lớn | Không gây mất kiểm soát disk; có fallback phù hợp |
| setToDisk(false) | Dữ liệu chỉ trong memory buffers | Không giả định dữ liệu từ đầu process còn đủ |
| maxAge/maxSize nhỏ | Recording dài | Chunks cũ có thể bị loại; phân tích time range đúng |
| PID/container thay đổi | Cùng service restart | File name/process identity không nhập nhằng |
| JDK/security update | JFR API/commands vẫn có | Smoke test recording/readback thành công |
| Termination cưỡng chế | SIGKILL hoặc timeout container | Không assert dump file bắt buộc |
| JFR custom events | Ghi đúng n events | Đọc lại đúng n event type mục tiêu |

Các ví dụ `JfrLifecycleDemo` và `JfrManualDumpDemo` thực hiện lần lượt các phép kiểm duration, destination, dumpOnExit và snapshot thủ công với custom events. Các ca OS/permission/container cần kiểm trên **môi trường thử được phép**, không cố giả lập crash nguy hiểm trên service sản xuất.

## 22. Những ngộ nhận phổ biến

| Ngộ nhận | Sai ở đâu? | Cách hiểu đúng |
| --- | --- | --- |
| “`setDestination` ghi file ngay.” | Setter chỉ chọn nơi lưu | File được xuất lúc stop hoặc dump on exit theo policy |
| “`setDuration` làm JVM tắt.” | Chỉ giới hạn recording | JVM tiếp tục hoạt động sau khi recording dừng |
| “`setDumpOnExit` chắc chắn ghi khi process bị kill.” | Không bảo đảm shutdown hook có cơ hội chạy | Cần graceful exit và fallback |
| “Có `dumpOnExit` thì không cần set path.” | File có thể tự đặt tên/vị trí không mong muốn | Chọn destination rõ ràng |
| “`stop()` và `close()` là cùng thao tác.” | Stop ngừng capture, close giải phóng data | Dùng theo lifecycle |
| “`dump(Path)` khiến recording dừng.” | Dump là snapshot | Sau dump vẫn có thể RUNNING |
| “`setToDisk(true)` chính là setDestination.” | Repository khác file cuối | Dùng đúng cả hai theo nhu cầu |
| “`getSize()==0` nghĩa không ghi event.” | getSize phản ánh disk repository | Kiểm RecordingFile/event data |
| “`maxSize` là hard quota cho toàn JVM.” | Chỉ giới hạn retained repository data | Cần disk quota/file cleanup riêng |
| “Đặt `maxAge`=20m giữ 20m tuyệt đối.” | Retention còn chịu maxSize và event production | Hiểu cả hai giới hạn |
| “`try-with-resources` luôn đúng cho dump-on-exit.” | Có thể close trước shutdown | Sở hữu recording ở app lifecycle |
| “Sau stop có destination, nhất định có thể dump lại.” | Recording được close sau copy theo contract | Nếu cần snapshot khác, dump khi còn RUNNING |
| “`getDuration()==null` nghĩa recording bị lỗi.” | Null là không giới hạn duration | Đặt duration nếu muốn bounded |
| “File tồn tại = recording hợp lệ và đầy đủ.” | File có thể cũ/corrupt/thiếu events | Đọc bằng RecordingFile/jfr summary |
| “JFR không chứa dữ liệu nhạy cảm.” | Events/stack/paths có thể lộ thông tin | Bảo vệ file như diagnostic evidence |
| “JFR API Java 11 cần commercial unlock flag.” | Cũ từ JDK 8 | Dùng module `jdk.jfr` trực tiếp |
| “Có thể bật profile mãi vì overhead luôn thấp.” | Overhead phụ thuộc settings/workload | Benchmark và giới hạn duration/disk |
| “Một service chỉ có một recording.” | API/startup/jcmd có thể tạo nhiều | Kiểm ownership, names, limits |

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Bạn muốn recording tự dừng sau hai phút và có file `incident.jfr`. Dùng API nào?

**Trả lời:** `recording.setDuration(Duration.ofMinutes(2))` và `recording.setDestination(path)` **trước start**. Khi recording dừng, JFR xuất dữ liệu theo destination; phải kiểm file hợp lệ.

**Câu 2.** `setDestination(path)` vừa được gọi, nhưng JVM chưa start recording. File phải tồn tại ngay chưa?

**Không.** Nó thiết lập đích, không ghi file tức thì.

**Câu 3.** Muốn lấy snapshot JFR giữa lúc ứng dụng vẫn chạy, nên dùng `stop()` hay `dump(Path)`?

**`dump(Path)`**. Nó xuất dữ liệu ra file mà recording có thể tiếp tục chạy.

**Câu 4.** `getDuration()` trả `null`. Điều đó nghĩa là recording đang lỗi?

**Không.** Nó nghĩa là **không có duration được đặt**.

**Câu 5.** `dumpOnExit=true` và JVM bị SIGKILL. File có chắc được tạo không?

**Không.** SIGKILL không cho shutdown thông thường; exit dump không được bảo đảm.

**Câu 6.** Bạn đặt `setDuration(30s)` và JVM còn chạy thêm một giờ. Recording có tiếp tục ghi cả giờ không?

**Không.** Recording dừng theo duration; ứng dụng vẫn có thể chạy.

**Câu 7.** `setToDisk(true)` có đồng nghĩa `getDestination()!=null` không?

**Không.** Repository policy và file destination là hai lựa chọn độc lập.

**Câu 8.** `setMaxSize(128MiB)` có làm tổng disk usage của mọi file JFR trong pod luôn dưới 128MiB không?

**Không.** Nó kiểm retained repository data cho recording, không thay thế quota/cleanup của mọi artifact.

**Câu 9.** Vì sao code dùng try-with-resources có thể không tạo exit file dù `setDumpOnExit(true)`?

**Vì** block có thể gọi `close()` trước lúc JVM shutdown và release recording data.

**Câu 10.** Muốn chứng minh dump-on-exit hoạt động, chỉ kiểm `getDumpOnExit()==true` là đủ?

**Không.** Hãy cho JVM kết thúc bình thường, chạy process khác kiểm file và **đọc sự kiện** từ `RecordingFile`.

**Câu 11.** Nếu recording stop rồi file đích không ghi được, có nên coi là QA PASS vì `stop()` đã được gọi không?

**Không.** Cần quan sát lỗi, kiểm file, ghi nhận sự cố lưu trữ và có phương án vận hành.

**Câu 12.** Nếu muốn dùng JFR trên Java 11 có cần bật `-XX:+UnlockCommercialFeatures` như một số hướng dẫn cũ không?

**Không.** Đây là hướng dẫn thuộc môi trường JDK cũ, không dùng cho JFR tích hợp trong Java 11+ hiện đại.

## 24. Tài liệu tham khảo chính thức

1. [Java SE 11 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): `setDuration`, `setDestination`, `setDumpOnExit`, `setToDisk`, `dump`, `stop`, `close` và retention.
2. [Java SE 26 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Recording.html): đối chiếu các API vẫn hỗ trợ trên JDK hiện đại và hợp đồng về destination/auto-close.
3. [Java SE 11 — `RecordingState`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/RecordingState.html): `NEW`/`DELAYED`/`RUNNING`/`STOPPED`/`CLOSED`.
4. [Java SE 11 — `RecordingFile`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc và kiểm file `.jfr`.
5. [Java SE 11 — `Configuration`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Configuration.html): cấu hình `default`/`profile`.
6. [Java SE 11 — `Event`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html) và [`Name`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Name.html): custom events được dùng trong demo.
7. [Oracle JDK 27 — Java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `-XX:StartFlightRecording`, `duration`, `filename`, `dumponexit`, retention options.
8. [Oracle JDK 27 — jcmd Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): `JFR.start`, `JFR.dump`, `JFR.stop` và `JFR.check`.
9. [dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): cách đặt duration/destination/dumponexit, default/profile và quản lý recording.
10. [OpenJDK JFR — JEP 328](https://openjdk.org/jeps/328): cơ chế Flight Recorder trong OpenJDK, không cần dựa vào hướng dẫn thương mại của JDK 8.

**Tóm tắt:** `setDuration` quyết định **recording chạy bao lâu**; `setDestination` quyết định **file nào nhận dữ liệu khi recording dừng**; `dump(Path)` cho phép **chụp dữ liệu không cần stop**; `setDumpOnExit(true)` yêu cầu **ghi khi JVM shutdown có kiểm soát**. `setToDisk`, `setMaxAge` và `setMaxSize` quản lý dữ liệu repository tạm chứ không thay file destination. Trên production, hãy thêm giới hạn thời gian/dung lượng, quyền file, kiểm file bằng `RecordingFile` và cơ chế snapshot chủ động để không phụ thuộc duy nhất vào việc JVM kết thúc bình thường.