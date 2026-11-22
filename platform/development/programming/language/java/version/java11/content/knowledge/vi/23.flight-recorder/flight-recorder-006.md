# Cấu hình JDK Flight Recorder: `default`, `profile` và tệp `.jfc` (Java 11+)

## 1. Mục tiêu bài học

**JDK Flight Recorder (JFR)** là hệ thống ghi sự kiện chẩn đoán được tích hợp trong JVM. JFR có thể thu thập thông tin về CPU, thread, GC, allocation, lock, I/O, class loading và các **sự kiện ứng dụng tự định nghĩa** với overhead có thể được kiểm soát qua cấu hình. Trong Java 11, Flight Recorder đã có mặt trong OpenJDK theo **JEP 328** và vẫn là công cụ giám sát, profiling hiện hành trên các JDK mới.

Bài học này tập trung vào **ba đối tượng rất dễ nhầm**:

1. **`default` / `default.jfc`:** cấu hình JFR dựng sẵn, hướng tới thu thập thường xuyên với overhead tương đối thấp.
2. **`profile` / `profile.jfc`:** cấu hình dựng sẵn, bật nhiều thông tin hơn để điều tra hiệu năng trong một khoảng thời gian được kiểm soát.
3. **Tệp `.jfc` tùy chỉnh:** một **JFR configuration file** dạng XML, xác định event nào được bật và những event setting như `threshold`, `period`, `stackTrace`, cùng các control của template nếu có.

Sau bài học, bạn có thể:

- Quyết định dùng `default`, `profile` hay một cấu hình riêng theo tình huống.
- Khởi động hoặc điều chỉnh một recording bằng **JVM startup option**, **`jcmd`**, hoặc **API `jdk.jfr`**.
- Hiểu tệp `.jfc` ảnh hưởng đến event settings ra sao và phân biệt nó với tệp **`.jfr`** chứa kết quả ghi.
- Tạo một `.jfc` tối giản, tạo cấu hình từ template có sẵn và kiểm chứng bằng ví dụ Java 11 **thực sự biên dịch và chạy được**.
- Tránh những lỗi khi cấu hình recording quá nặng, thiếu sự kiện, lưu trữ vô hạn hoặc kỳ vọng lệnh JDK mới hoạt động trên mọi JDK 11.

**Special Note áp dụng:** chỉ sử dụng **API và cách làm còn áp dụng hiện nay**. Các hướng dẫn dùng `jfr configure` trên một số JDK mới sẽ được ghi rõ **không mặc nhiên có trên JDK 11**; ví dụ runnable chính chỉ dùng public API Java 11.

## 2. JFR hoạt động ở mức nào?

JFR có các **event types**, mỗi loại chứa metadata và dữ liệu; ví dụ:

- `jdk.ExecutionSample`: mẫu thực thi để xem CPU hot methods.
- `jdk.CPULoad`: thông tin CPU load theo chu kỳ.
- `jdk.GarbageCollection`: sự kiện garbage collection.
- `jdk.JavaMonitorEnter`: dữ liệu về monitor contention trong điều kiện event được cấu hình phù hợp.
- `jdk.SocketRead` / `jdk.SocketWrite`: sự kiện liên quan I/O socket nếu được bật/đáp ứng ngưỡng.
- `lesson.Work`: ví dụ event tùy chỉnh mà ứng dụng tự khai báo bằng `jdk.jfr.Event`.

Các event **không luôn luôn được bật** và **không nhất thiết được ghi mỗi lần hoạt động xảy ra**. Cấu hình JFR có thể đặt `enabled=false`, threshold, sampling period hoặc giới hạn stack traces. Vì vậy, một tệp `.jfr` không có sự kiện mong muốn **chưa đủ để kết luận** sự kiện đó chưa từng diễn ra.

Sơ đồ:

```text
JDK/JVM + ứng dụng đang chạy
   |  phát ra event types: CPU/GC/Thread/I/O/custom...
   v
JFR event settings từ default/profile/custom .jfc
   |  enabled, threshold, period, stackTrace, ...
   v
Recording đang chạy
   |  retention/buffer/disk/limits
   v
Tệp kết quả .jfr
   |  jfr summary / jfr print / JDK Mission Control / consumer API
   v
Phân tích: CPU, GC, contention, allocation, latency, custom events
```

Một JVM có thể quản lý **nhiều recording** với settings và vòng đời riêng. Không nên suy luận rằng “bật JFR” nghĩa là mọi event đều xuất hiện trong mọi recording. File recording, tệp cấu hình, bộ nhớ/buffer và các giới hạn lưu trữ là các vấn đề khác nhau.

## 3. Phân biệt `.jfc`, `.jfr` và JFR recording

| Khái niệm | Định dạng / vai trò | Được đọc hoặc tạo bởi |
| --- | --- | --- |
| **`default.jfc`** | XML event configuration dựng sẵn, thiên về overhead thấp | JFR khi dùng `settings=default` hoặc API `Configuration.getConfiguration("default")` |
| **`profile.jfc`** | XML event configuration dựng sẵn, thiên về điều tra sâu hơn | JFR khi dùng `settings=profile` hoặc API `Configuration.getConfiguration("profile")` |
| **`custom.jfc`** | XML event configuration ứng dụng tự thiết kế | JFR với `settings=/path/custom.jfc`, hoặc `Configuration.create(Path)` |
| **Recording** | Đối tượng/công việc ghi một tập sự kiện trong JVM, có lifecycle | `-XX:StartFlightRecording`, `jcmd JFR.start`, `jdk.jfr.Recording` |
| **`snapshot.jfr`** | File **binary recording** chứa event data thực tế | `jcmd JFR.dump`, recording dump/stop hoặc `dumponexit` |
| **JDK Mission Control (JMC)** | Công cụ giao diện phân tích recording và hỗ trợ thiết kế cấu hình | Mở file `.jfr` và quản lý template theo phiên bản công cụ |

**`.jfc` không phải một bản ghi sự kiện**. Mở một `.jfc` sẽ thấy XML chứa cấu hình, không phải thời điểm/thread của các sự kiện đã xảy ra. **`.jfr` không phải file thiết lập**; nó chứa dữ liệu runtime.

Cách nhớ:

```text
*.jfc = CONFIGURE what/how to record
*.jfr = RESULTS of recording
```

Cả hai file có thể chứa metadata nhạy cảm: `.jfr` có thể lộ stack trace, tên thread, class, đường dẫn, thuộc tính môi trường hay payload của event ứng dụng; bảo vệ file, nơi lưu và quyền truy cập cho phù hợp.

## 4. `default` so với `profile`: ưu tiên và đánh đổi

Hai template thường có sẵn trong JDK tại:

```text
<JAVA_HOME>/lib/jfr/default.jfc
<JAVA_HOME>/lib/jfr/profile.jfc
```

Thư mục chính xác phụ thuộc JDK runtime được cài đặt; với container và runtime image tùy chỉnh, cần kiểm tra trong **JDK/JRE đang chạy chương trình**, không chỉ JDK dùng để build.

### 4.1. Bảng so sánh

| Tiêu chí | `default` | `profile` |
| --- | --- | --- |
| Mục tiêu | Ghi **liên tục hoặc dài hạn** với cân bằng dữ liệu/chi phí | Ghi **ngắn hạn** để điều tra hiệu năng chi tiết |
| Overhead | Tương đối thấp trong nhiều workload | Thường cao hơn do nhiều sự kiện/lấy mẫu hơn |
| Dung lượng | Thường thấp hơn với cùng khoảng thời gian | Thường nhiều dữ liệu hơn, cần kiểm soát thời gian/kích thước |
| Mức độ chi tiết | Đủ cho telemetry/triage thường xuyên | Dễ thấy hot methods, allocation/sampling, blocking và các triệu chứng chi tiết hơn |
| Khi dùng | Baseline production, quan sát dài hạn, giữ history vừa phải | Phân tích một sự cố CPU/GC/latency, load test, performance investigation |
| Tên settings | `settings=default` hoặc `default.jfc` | `settings=profile` hoặc `profile.jfc` |
| Rủi ro | Có thể **không bật** event cụ thể bạn cần | Có thể **tạo chi phí đáng kể** trên workload nhạy cảm và sinh nhiều dữ liệu |

JFR documentation mô tả `default.jfc` là cấu hình chi phí thấp, phù hợp recording liên tục, còn `profile.jfc` thu thập nhiều hơn và hướng tới profiling. **Không cam kết con số overhead cố định** cho mọi JVM: nó phụ thuộc CPU, số sự kiện, tần suất stack traces, tốc độ cấp phát, I/O, bộ lọc threshold, JDK version và ứng dụng.

### 4.2. Tên template không phải danh sách event bất biến

Đừng giả định `default`/`profile` luôn bật **cùng một tập event và cùng giá trị threshold** trên tất cả JDK 11, 17, 21, 25 hoặc 26. Nội dung template có thể thay đổi theo phiên bản JDK, vendor và update bảo mật.

Khi cần chứng minh event đang bật:

1. Xác định **JDK runtime thực tế**.
2. Đọc file `$JAVA_HOME/lib/jfr/default.jfc` / `profile.jfc` tương ứng hoặc sử dụng `jdk.jfr.Configuration`.
3. Kiểm tra event type và setting cụ thể, ví dụ `jdk.ExecutionSample#enabled` hoặc `jdk.SocketRead#threshold` nếu event đó có setting tương ứng.
4. Kiểm tra kết quả recording và phân biệt **event không bật** với **event không phát sinh** hoặc **được lọc do threshold/sampling**.

Mã ví dụ Java ở mục 9 so sánh hai cấu hình bằng Map thực tế, không ghi cứng số lượng hoặc thứ tự sự kiện của một bản JDK.

### 4.3. Chọn template theo bài toán

- **Theo dõi một service lâu dài:** bắt đầu bằng `default`, giới hạn độ tuổi/dung lượng recording, có chính sách dump và bảo vệ file.
- **Điều tra CPU spike:** có thể mở một recording **`profile` trong thời gian ngắn**, so sánh với baseline, xem method samples và stack traces.
- **Giải thích pause/GC bất thường:** bắt đầu từ default; nếu thiếu dữ liệu cần thiết, mở profile hoặc chọn event settings riêng theo mục tiêu chẩn đoán.
- **Chỉ cần một custom event nghiệp vụ:** có thể giữ default rồi thêm `lesson.Work#enabled=true`, tránh bật cả profile nếu không cần.
- **Máy production cực nhạy cảm với latency:** benchmark overhead ở workload thật và bật event tối thiểu cần thiết. Không dùng profile liên tục chỉ vì “dữ liệu nhiều hơn”.

## 5. Những gì được điều khiển bởi `.jfc` và những gì thuộc recording options

Phân biệt **event settings** và **recording options**:

| Nhóm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Event setting** | `jdk.ExecutionSample#enabled=true` | Thu thập loại event nào |
| **Event setting** | `jdk.ExecutionSample#period=20 ms` | Nhịp thu thập cho event hỗ trợ `period` |
| **Event setting** | `jdk.SocketRead#threshold=20 ms` | Chỉ ghi event vượt ngưỡng duration khi event hỗ trợ |
| **Event setting** | `lesson.Work#stackTrace=false` | Có gắn stack trace cho loại event được hỗ trợ hay không |
| **Recording option** | `name=baseline` | Đặt tên recording để tìm, dump, stop |
| **Recording option** | `duration=60s` | Thời gian recording được chạy |
| **Recording option** | `filename=/path/report.jfr` | Đường dẫn file kết quả |
| **Recording option** | `maxage=1h`, `maxsize=256m` | Ràng buộc dữ liệu được giữ trong repository |
| **Recording option** | `dumponexit=true` | Ghi kết quả khi JVM kết thúc theo ngữ nghĩa startup recording |

**`.jfc` chủ yếu định nghĩa event settings và các control/metadata hỗ trợ cấu hình.** Nó không tự tạo một recording dài 60 giây, không tự chọn PID, không bảo đảm đích filename hay cơ chế cleanup. Các yếu tố đó được cung cấp khi tạo/điều khiển recording.

Một số công cụ JFR mới hỗ trợ cấu hình event setting từ dòng lệnh và có quy tắc override; **đừng bê tùy chọn CLI event-level mới vào bài Java 11** khi chưa kiểm tra bản JDK. Trên Java 11, cách nhất quán là chọn `settings=default/profile/path` hoặc dùng **`Recording.enable(...)`/`setSettings(...)`** qua public API.

## 6. Bắt đầu recording với `-XX:StartFlightRecording`

Nếu có quyền chạy JVM từ đầu, bạn có thể bật JFR trong startup command:

```bash
java -XX:StartFlightRecording=settings=default,dumponexit=true,filename=baseline.jfr MyApp
```

Đây là **lệnh minh họa**. `MyApp` phải là class/application có thật và classpath/module path phải được bổ sung tương ứng.

Ý nghĩa:

- `settings=default`: chọn template tích hợp `default.jfc`.
- `filename=baseline.jfr`: file .jfr sẽ được ghi theo path (đường dẫn tương đối phụ thuộc **working directory của JVM**).
- `dumponexit=true`: khi JVM kết thúc theo cơ chế được hỗ trợ, ghi dữ liệu đã thu thập vào file. Không coi đây là đảm bảo có file nếu process bị `kill -9`, crash trước khi kịp dump hoặc không có quyền ghi.
- `-XX:StartFlightRecording`: JVM option của JFR, được dùng **trước class/jar application**.

Với điều tra có giới hạn thời gian:

```bash
java -XX:StartFlightRecording=settings=profile,duration=60s,filename=profile.jfr MyApp
```

Nếu ứng dụng chạy lâu hơn 60 giây, recording chạy theo duration đã cấu hình, sau đó ghi file theo tùy chọn. Nếu ứng dụng rất ngắn, kết thúc trước duration, hãy cân nhắc `dumponexit=true`, hoặc dùng chương trình đủ lâu để thu thập dữ liệu có ý nghĩa.

### 6.1. Cú pháp option và dấu phân cách

Cú pháp đúng:

```text
-XX:StartFlightRecording=name=bootstrap,settings=default,filename=boot.jfr
```

**Các tùy chọn được phân cách bằng dấu phẩy `,`** trong một JVM option. Đừng viết `-XX:StartFlightRecording=settings=default settings=profile` như thể đó là nhiều tham số JVM độc lập.

Lệnh shell Windows PowerShell:

```powershell
java '-XX:StartFlightRecording=settings=profile,dumponexit=true,filename=profile.jfr' -cp . MyApp
```

Dấu nháy bảo vệ chuỗi option khi đường dẫn hoặc shell có quy tắc đặc biệt. Với đường dẫn chứa khoảng trắng, cẩn trọng cách shell truyền một JVM argument nguyên vẹn.

**Một lưu ý về file:** `profile.jfc` là **config**, còn `profile.jfr` là **result**. Nên đặt tên file đầu ra thể hiện thời gian và mục đích để tránh ghi đè/nhầm cấu hình.

### 6.2. Kiểm thử command startup tối giản

Một chương trình chỉ để kiểm tra JVM option:

```java
public class JfrStartupDemo {
    public static void main(String[] args) {
        long sum = 0;
        for (int i = 0; i < 100000; i++) {
            sum += i;
        }
        System.out.println("calculated: " + sum);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 11 JfrStartupDemo.java
java -XX:StartFlightRecording=settings=default,dumponexit=true,filename=startup.jfr JfrStartupDemo
jfr summary startup.jfr
```

**Dòng stdout của `JfrStartupDemo` đã kiểm thử:**

```text
calculated: 4999950000
```

JFR startup có thể in thêm các dòng **`[info][jfr,startup]`** trên console tùy JDK/log configuration; thời điểm, PID, đường dẫn và thống kê `jfr summary` thay đổi mỗi lần chạy. Không coi chúng là phần stdout cố định của code.

Lưu ý chương trình rất ngắn nên sample CPU có thể ít; sự tồn tại của một file .jfr hợp lệ **không bảo đảm đã thu được đủ số mẫu** để phân tích CPU hotspot.

## 7. Khởi động recording trên JVM đang chạy bằng `jcmd`

Khi service đã chạy, công cụ `jcmd` của JDK có thể gửi lệnh chẩn đoán đến JVM đích (khi được cho phép):

```bash
jcmd -l
jcmd 12345 JFR.start name=baseline settings=default maxage=1h maxsize=256m
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=baseline filename=baseline-snapshot.jfr
jcmd 12345 JFR.stop name=baseline
```

Thay `12345` bằng **PID thật của JVM cần chẩn đoán**. Các lệnh là minh họa; không chạy trực tiếp vào JVM production mà thiếu quyền và mục tiêu rõ ràng.

**Luồng:**

1. `jcmd -l` giúp liệt kê JVM nhìn thấy được trong môi trường hiện tại. Nó không nhất thiết tìm được mọi JVM ở container/user namespace khác.
2. `JFR.start` tạo một recording `baseline`, dùng `settings=default`.
3. `JFR.check` xem recording đang chạy và thông tin nhận diện.
4. `JFR.dump name=baseline filename=...` chụp dữ liệu ra file `.jfr` mà **không bắt buộc dừng** recording đang chạy.
5. `JFR.stop name=baseline` dừng recording đã được đặt tên.

Để tạo một recording profiling ngắn hạn:

```bash
jcmd 12345 JFR.start name=investigation settings=profile duration=60s filename=investigation.jfr
```

Để dùng file tùy chỉnh:

```bash
jcmd 12345 JFR.start name=custom settings=/opt/app/jfr/custom.jfc duration=60s filename=/opt/app/recordings/custom.jfr
```

**Khác cú pháp startup:** sau `jcmd PID JFR.start`, các `key=value` thường cách nhau bằng **dấu cách**. `jcmd` attach phải được phép bởi hệ điều hành/quyền process, cách đóng gói JVM và cấu hình attach mechanism. Trên container, cần xác định đúng namespace PID và nơi ghi file của **process đích**.

### 7.1. Không nhầm `maxage` / `maxsize` với kích thước output cố định

`maxage` và `maxsize` kiểm soát dữ liệu giữ lại trong repository; chúng hữu ích cho continuous recording. `maxsize=256m` **không có nghĩa** snapshot luôn đúng 256 MB. Số sự kiện, chunking, buffer flush và retention đều ảnh hưởng kích thước.

Không đặt `maxage=0` hoặc `maxsize=0` rồi hiểu là “tắt giới hạn” một cách vô hại: tùy option, `0` có thể biểu thị **không giới hạn**. Đối với service chạy dài, thiết kế giới hạn rõ ràng và theo dõi dung lượng disk để tránh lấp đầy ổ.

## 8. Cấu trúc tệp `.jfc`: XML và event settings

Một cấu hình JFC có phần tử root `<configuration>` và các phần tử `<event>` chứa `<setting>`. Có thể có `<control>` và metadata để biểu diễn các tùy chọn cao cấp mà JDK Mission Control đọc.

Một **tệp tối giản hợp lệ** dùng cho event do ứng dụng tự định nghĩa:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration version="2.0" label="Minimal" provider="Local">
  <event name="lesson.JfcOnly">
    <setting name="enabled">true</setting>
    <setting name="stackTrace">false</setting>
  </event>
</configuration>
```

Ví dụ này đã được kiểm tra bằng `Configuration.create(Reader)` trên JDK hỗ trợ Java 11 và được dùng để ghi event. Nó **không thay thế `default.jfc` trong production**, vì thiếu phần lớn cấu hình sự kiện hệ thống. Hãy hiểu nó là một **fixture** để nghiên cứu cú pháp, không phải template giám sát JVM đầy đủ.

### 8.1. Ý nghĩa các trường

- `configuration version="2.0"`: phiên bản cấu trúc JFC, **không phải** phiên bản Java 2.0.
- `label`: tên hiển thị trong công cụ đọc configuration.
- `provider`: đơn vị cung cấp file config, dùng cho metadata.
- `event name="lesson.JfcOnly"`: **tên đầy đủ** của event type, ví dụ từ annotation `@Name("lesson.JfcOnly")` trên lớp Java kế thừa `jdk.jfr.Event`.
- `setting name="enabled"`: bật/tắt sự kiện.
- `setting name="stackTrace"`: yêu cầu có/không có stack trace khi event hỗ trợ setting tương ứng.

Ví dụ cấu hình event JDK khác:

```xml
<event name="jdk.SocketRead">
  <setting name="enabled">true</setting>
  <setting name="threshold">20 ms</setting>
  <setting name="stackTrace">true</setting>
</event>
```

Đây chỉ là **đoạn XML minh họa đặt bên trong một `<configuration>` hợp lệ**. Tên setting phụ thuộc EventType; không tự gán `period` cho mọi event hoặc `threshold` cho một event vốn không hỗ trợ threshold.

### 8.2. Những event settings thường gặp

| Setting | Giá trị ví dụ | Khi nào hữu ích? |
| --- | --- | --- |
| `enabled` | `true`, `false` | Bật/tắt loại event để điều chỉnh overhead |
| `threshold` | `20 ms` | Chỉ lưu các duration events vượt ngưỡng |
| `period` | `20 ms` hoặc `1 s` | Điều khiển nhịp event định kỳ/sampling nếu event hỗ trợ |
| `stackTrace` | `true`, `false` | Xác định vị trí gọi/hot path nhưng có thêm chi phí |

**Không phải mọi event đều có đủ bốn setting.** Để xem metadata của runtime, có thể dùng API `FlightRecorder.getFlightRecorder().getEventTypes()` và xem `EventType.getSettingDescriptors()`, hoặc công cụ JFR/JMC tùy phiên bản JDK. Việc một setting có tên gần giống chưa chứng minh JVM đang áp dụng nó vào event đó.

### 8.3. File JFC có thể chứa controls/expressions

Hai template tích hợp có thể có các control cho cấu hình qua UI hoặc qua công cụ được hỗ trợ, như việc chọn cấp độ profiling hoặc group setting. Nếu sửa file thủ công, **giữ XML hợp lệ** và các reference/control expression liên quan. Đừng cắt bớt block control khi chưa hiểu tác động, vì các setting có thể phụ thuộc control đó.

Khi cần kiểm tra file sau chỉnh sửa:

1. Parse bằng `Configuration.create(Path)` trên **chính JDK runtime mục tiêu**.
2. Kiểm tra `Configuration.getSettings()` xem event-setting map đã nhận đúng chưa.
3. Thử tạo `Recording` và thực sự ghi một event cần thiết.
4. Dùng `jfr summary` / `jfr print` để xác nhận output, thay vì chỉ thấy XML đọc được.

## 9. Cách tạo `custom.jfc` an toàn từ template chuẩn

### 9.1. Khuyến nghị: copy thay vì sửa file của JDK

Không sửa trực tiếp:

```text
$JAVA_HOME/lib/jfr/default.jfc
$JAVA_HOME/lib/jfr/profile.jfc
```

Lý do: file chuẩn được quản lý bởi bản JDK, có thể bị ghi đè khi update, và thay đổi sẽ ảnh hưởng không mong đợi đến tất cả process dùng cùng runtime.

Quy trình hợp lý:

1. Chọn `default.jfc` hoặc `profile.jfc` làm bản gốc.
2. Copy sang **thư mục cấu hình do ứng dụng quản lý**, ví dụ `config/jfr/service.jfc`.
3. Bật/tắt đúng những event cần và chỉnh threshold/period/stackTrace có cơ sở.
4. Xác thực bằng `Configuration.create(Path)` và chạy recording ngắn trong môi trường test.
5. Đánh giá overhead, dung lượng, dữ liệu nhạy cảm và chính sách rollout.
6. Gọi bằng `settings=/path/to/service.jfc` hoặc `new Recording(Configuration.create(path))`.

Ví dụ trên shell POSIX:

```bash
cp "$JAVA_HOME/lib/jfr/default.jfc" ./service.jfc
```

Trên Windows PowerShell:

```powershell
Copy-Item -LiteralPath "$env:JAVA_HOME\lib\jfr\default.jfc" -Destination .\service.jfc
```

**Đảm bảo `JAVA_HOME` đang trỏ đến JDK runtime đúng**. Trong môi trường Java chạy trên container/image nhiều lớp, cấu hình được test trên một JDK khác có thể có event/setting không hoàn toàn giống.

### 9.2. Công cụ hiện hành để chỉnh .jfc

- **JDK Mission Control (JMC)** cung cấp giao diện để tạo hoặc điều chỉnh recording template và phân tích kết quả. Giữ một bản copy của template gốc, không sửa file được JDK cung cấp.
- **Trên các JDK mới có hỗ trợ lệnh `jfr configure`** (ví dụ JDK 21/25), có thể sinh config từ template và override event settings; **đừng giả định lệnh này tồn tại trên mọi bản JDK 11**. Kiểm tra `jfr help configure` trên bản JDK đang dùng.
- **Trên Java 11**, cách chắc chắn và portable là dùng copy tệp `.jfc` hiện có + chỉnh theo cú pháp được hỗ trợ, hoặc dùng `jdk.jfr.Configuration`/`Recording` trong ứng dụng.

Ví dụ **chỉ dành cho JDK mới có `jfr configure`**:

```bash
jfr configure --input default.jfc --output service.jfc
jfr help configure
```

Cú pháp minh họa dựa trên JDK hiện đại; **không đưa nó vào yêu cầu chạy Java 11**. Khi cần override setting cụ thể, kiểm tra đúng tên event, setting và quy tắc quoting của shell qua `jfr help configure`.

### 9.3. Đừng thay default bởi một JFC “rỗng” trừ khi chủ đích

Nếu bạn tạo một `.jfc` chỉ bật `lesson.JfcOnly`, các event JDK có thể không nhận các setting như ở `default.jfc`. Điều đó phù hợp cho **unit test một event**, nhưng có thể làm mất CPU/GC/lock telemetry mà production đang kỳ vọng.

Nếu muốn “default + thêm một event”, nên copy từ `default.jfc` rồi bổ sung/chỉnh phần tử `<event>`, hoặc trong code Java dùng một map **sao chép từ `Configuration.getConfiguration("default").getSettings()`** rồi override có chủ đích.

## 10. Public API `jdk.jfr.Configuration` (Java 11+)

Không cần chạy lệnh `jcmd` để kiểm tra file JFR trong Java. `jdk.jfr.Configuration` hỗ trợ:

| API | Vai trò |
| --- | --- |
| `Configuration.getConfiguration("default")` | Lấy cấu hình dựng sẵn default |
| `Configuration.getConfiguration("profile")` | Lấy cấu hình dựng sẵn profile |
| `Configuration.getConfigurations()` | Danh sách cấu hình dựng sẵn JVM đang cung cấp |
| `Configuration.create(Path)` | Đọc, parse và tạo config từ file `.jfc` |
| `Configuration.create(Reader)` | Đọc JFC từ luồng ký tự, hữu ích cho test/generator |
| `configuration.getName()` | Tên nhận diện config, ví dụ default/profile |
| `configuration.getSettings()` | Map `event-name#setting-name` → giá trị setting |
| `configuration.getContents()` | Nội dung text của cấu hình, hữu ích để xuất ra bản sao |
| `new Recording(configuration)` | Tạo recording từ cấu hình đã tải |

**`getSettings()` trả một Map theo nội dung configuration**. Thay đổi Map đó **không tự sửa** `Configuration`. Tương tự, `Recording.getSettings()` không phải tham chiếu “live” để bạn ghi một key vào rồi mặc nhiên áp dụng; muốn thay toàn bộ settings dùng `recording.setSettings(map)`.

`Configuration.create(Path)` có thể ném `IOException` nếu file không đọc được hoặc `ParseException` nếu file lỗi cấu trúc. Đừng chỉ bắt `Exception` rồi bỏ qua: phải báo đường dẫn, JDK version và thông tin nguyên nhân thích hợp (không log secret).

### 10.1. Có cần module flags không?

Module **`jdk.jfr`** là module chuẩn được JDK cung cấp; ví dụ ở bài đã biên dịch bằng `javac --release 11` mà không dùng API nội bộ. Nếu ứng dụng của bạn có `module-info.java` trong một **named module** và gọi JFR API trực tiếp, khai báo:

```java
module example.monitoring {
    requires jdk.jfr;
}
```

Đó là **đoạn descriptor minh họa**, không phải standalone Java app. Với classpath/unnamed module theo cách chạy demo, không cần tạo `module-info.java`.

## 11. Ví dụ Java 11 hoàn chỉnh: đọc default/profile, tạo bản sao .jfc, ghi .jfr

Ví dụ được thiết kế để:

1. Lấy hai cấu hình **`default`** và **`profile`** bằng `Configuration.getConfiguration`.
2. So sánh **cấu hình thực của JDK đang chạy** thay vì hardcode số lượng event hoặc threshold.
3. Ghi **một bản sao nguyên văn** của default dưới tên `custom-default.jfc` trong thư mục test, rồi parse lại với `Configuration.create(Path)`.
4. Dùng `new Recording(readBack)` để tạo recording từ cấu hình đó.
5. Bật thêm custom event `lesson.Work` bằng API `Recording.enable(Work.class)`.
6. Commit 3 event, dừng recording và dump ra `sample.jfr`.
7. Đọc .jfr bằng `RecordingFile.readAllEvents`, xác nhận số event và tổng dữ liệu.

**Tệp `JfrSettingsDemo.java`:**

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.util.List;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrSettingsDemo {
    @Name("lesson.Work")
    @Label("Work unit")
    public static class Work extends Event {
        @Label("Unit number")
        public int unit;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass a writable directory");
        }

        Configuration low = Configuration.getConfiguration("default");
        Configuration detail = Configuration.getConfiguration("profile");
        System.out.println("default name: " + low.getName());
        System.out.println("profile name: " + detail.getName());
        System.out.println("configurations differ: " +
                !low.getSettings().equals(detail.getSettings()));

        Path custom = Path.of(args[0], "custom-default.jfc");
        Files.writeString(custom, low.getContents(), StandardCharsets.UTF_8);
        Configuration readBack = Configuration.create(custom);
        System.out.println("custom .jfc settings match: " +
                low.getSettings().equals(readBack.getSettings()));

        Path output = Path.of(args[0], "sample.jfr");
        try (Recording recording = new Recording(readBack)) {
            recording.setName("java11-jfr-demo");
            recording.setMaxSize(16L * 1024 * 1024);
            recording.enable(Work.class).withoutStackTrace();

            recording.start();
            for (int unit = 1; unit <= 3; unit++) {
                Work event = new Work();
                event.unit = unit;
                event.commit();
            }
            recording.stop();
            recording.dump(output);
        }

        List<RecordedEvent> events = RecordingFile.readAllEvents(output);
        long count = events.stream()
                .filter(event -> event.getEventType()
                        .getName().equals("lesson.Work"))
                .count();
        int sum = events.stream()
                .filter(event -> event.getEventType()
                        .getName().equals("lesson.Work"))
                .mapToInt(event -> event.getInt("unit"))
                .sum();
        System.out.println("custom event count: " + count);
        System.out.println("custom event units sum: " + sum);
        System.out.println("recording file nonempty: " +
                (Files.size(output) > 0));
    }
}
```

**Chạy:** tạo thư mục `jfr-output` trước khi chạy; với hệ điều hành có terminal hỗ trợ:

```bash
mkdir jfr-output
javac --release 11 -encoding UTF-8 JfrSettingsDemo.java
java JfrSettingsDemo jfr-output
jfr summary jfr-output/sample.jfr
jfr print --events lesson.Work jfr-output/sample.jfr
```

Với PowerShell trên Windows có thể dùng:

```powershell
New-Item -ItemType Directory -Force -Path .\jfr-output
javac --release 11 -encoding UTF-8 JfrSettingsDemo.java
java JfrSettingsDemo .\jfr-output
jfr summary .\jfr-output\sample.jfr
jfr print --events lesson.Work .\jfr-output\sample.jfr
```

**Đầu ra chính xác của Java `JfrSettingsDemo` đã kiểm thử (7 dòng):**

```text
default name: default
profile name: profile
configurations differ: true
custom .jfc settings match: true
custom event count: 3
custom event units sum: 6
recording file nonempty: true
```

Output riêng của `jfr summary` và `jfr print` có **metadata, thời gian, event size, runtime/JDK-specific fields** nên không cần khớp từng dòng. Trong lần kiểm thử, `jfr summary` nhận diện tệp hợp lệ và liệt kê `lesson.Work` với **3 sự kiện**.

### 11.1. Vì sao output đáng tin cậy?

- `default name` và `profile name`: các cấu hình tích hợp theo tên chuẩn.
- `configurations differ: true`: những file mặc định và profile được JDK đang chạy cung cấp có các event settings khác nhau. **Không ghi cứng số settings** vì thay đổi theo JDK.
- `custom .jfc settings match: true`: một bản sao nguyên văn của default được parse lại, rồi so sánh các map setting.
- `recording.enable(Work.class)` chủ động bật event tùy chỉnh dù default template không cần định nghĩa event này.
- `count=3` và `sum=6`: chương trình commit các giá trị 1, 2, 3; JFR ghi đúng những event đó.
- `recording.dump(output)` sau `stop()` ghi kết quả khi recording chưa đóng; `try-with-resources` giải phóng tài nguyên sau đó.
- `RecordingFile.readAllEvents` tiện cho **file demo nhỏ**, không nên dùng để đưa tệp .jfr nhiều GB vào RAM. Với file lớn dùng `RecordingFile` và duyệt event theo dòng, hoặc công cụ JMC/JFR hỗ trợ phân tích.

**Lưu ý về môi trường:** chương trình cần JDK có Flight Recorder được hỗ trợ và quyền ghi thư mục. Một runtime image bị loại bỏ module `jdk.jfr` có thể không chạy được; sử dụng JDK đầy đủ hoặc đóng gói module cần thiết.

### 11.2. Ví dụ minh họa cách đọc file recording lớn hơn

```java
try (RecordingFile file = new RecordingFile(recordingPath)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if ("lesson.Work".equals(event.getEventType().getName())) {
            System.out.println(event.getInt("unit"));
        }
    }
}
```

Đây là **snippet không độc lập**: cần imports `RecordingFile`, `RecordedEvent` và biến `recordingPath`. Duyệt streaming/iteration là cách phù hợp hơn việc `readAllEvents(...)` trả toàn bộ List khi file lớn. Tuy nhiên vẫn cần xem giới hạn bộ nhớ, tệp không tin cậy và hiệu năng phân tích.

## 12. Ví dụ custom JFC tối giản đã kiểm thử với Java 11

Phần này chỉ nhằm học **định dạng JFC và cách apply event settings**. Nó không lấy default làm nền nên **không phải cấu hình giám sát production**.

Chương trình sau tạo XML JFC trong một `StringReader` rồi gọi `Configuration.create(Reader)`. Event `lesson.JfcOnly` được bật **bởi JFC**, không gọi `recording.enable(...)`. Sau đó xác minh event đã ghi.

**Tệp `MinimalJfcDemo.java`:**

```java
import java.io.StringReader;
import java.nio.file.Path;
import java.util.List;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class MinimalJfcDemo {
    @Name("lesson.JfcOnly")
    public static class Sample extends Event {
        public int number;
    }

    public static void main(String[] args) throws Exception {
        String xml =
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" +
                "<configuration version=\"2.0\" label=\"Minimal\" provider=\"Local\">\n" +
                "  <event name=\"lesson.JfcOnly\">\n" +
                "    <setting name=\"enabled\">true</setting>\n" +
                "    <setting name=\"stackTrace\">false</setting>\n" +
                "  </event>\n" +
                "</configuration>\n";

        Configuration cfg = Configuration.create(new StringReader(xml));
        System.out.println("custom enabled: " +
                cfg.getSettings().get("lesson.JfcOnly#enabled"));
        System.out.println("custom stackTrace: " +
                cfg.getSettings().get("lesson.JfcOnly#stackTrace"));

        EventType.getEventType(Sample.class);
        Path file = Path.of(args[0], "custom-minimal.jfr");
        try (Recording r = new Recording(cfg)) {
            r.start();
            Sample e = new Sample();
            e.number = 123;
            e.commit();
            r.stop();
            r.dump(file);
        }

        List<RecordedEvent> events = RecordingFile.readAllEvents(file);
        long count = events.stream()
                .filter(e -> e.getEventType().getName()
                        .equals("lesson.JfcOnly"))
                .count();
        System.out.println("custom event count: " + count);
    }
}
```

**Chạy với thư mục output đã tồn tại:**

```bash
javac --release 11 -encoding UTF-8 MinimalJfcDemo.java
java MinimalJfcDemo jfr-output
```

**Đầu ra chính xác đã kiểm thử:**

```text
custom enabled: true
custom stackTrace: false
custom event count: 1
```

Hai cách cấu hình đã được minh họa:

- `Configuration.create(Path)` trong mục 11: đọc **file `.jfc` thật**.
- `Configuration.create(Reader)` trong mục 12: đọc **nội dung JFC từ StringReader**, hữu ích cho unit test hoặc config được cung cấp bởi hệ thống khác.

Dù XML ở dạng file hay Reader, các điều kiện bảo mật/hiệu năng vẫn áp dụng như nhau: chỉ dùng cấu hình từ nguồn tin cậy và kiểm tra setting thực tế trước khi dùng với workload production.

## 13. Điều chỉnh event settings có chọn lọc qua Java API

Nếu muốn giữ nguyên template default nhưng chỉnh một event:

```java
Configuration standard = Configuration.getConfiguration("default");
Map<String, String> selected = new HashMap<>(standard.getSettings());

// Ví dụ: bật ExecutionSample và đặt period theo chính sách test.
selected.put("jdk.ExecutionSample#enabled", "true");
selected.put("jdk.ExecutionSample#period", "20 ms");

try (Recording recording = new Recording(selected)) {
    recording.start();
    // ... chương trình thực hiện workload ...
    recording.stop();
    recording.dump(Path.of("diagnostic.jfr"));
}
```

Đây là **snippet minh họa**, cần imports `Configuration`, `Map`, `HashMap`, `Recording`, `Path`, exception handling và một workload chạy trong recording. Tên event/period cần kiểm tra lại theo JDK và nhu cầu profiling.

**Tại sao tạo `new HashMap<>(standard.getSettings())`?**

- `recording.setSettings(map)` **thay thế** toàn bộ map cấu hình, không phải phép merge ngầm.
- Nếu chỉ tạo một map với một entry `"jdk.ExecutionSample#enabled"`, những event setting từ default có thể bị mất ở recording đó.
- Nếu muốn thêm đúng một setting khi recording đang tồn tại, có thể dùng `recording.enable("jdk.ExecutionSample").withPeriod(...)` hoặc lấy map hiện tại, thêm phần muốn thay, rồi gọi `setSettings(...)` đúng contract.
- Không giả định thay `standard.getSettings().put(...)` sẽ tự chỉnh `Configuration`; nó trả Map dữ liệu không sống.

Các overload của `Recording.enable(String)` hoặc `enable(Class<? extends Event>)` trả `EventSettings` để thiết lập threshold, period, stack trace theo event được hỗ trợ; mục tiêu là **chỉ tăng lượng thông tin cần thiết**, không bật dồn tất cả sự kiện.

### 13.1. Thứ tự áp dụng và cách kiểm tra

Hãy cấu hình recording **trước `recording.start()`** để trạng thái thu thập nhất quán và dễ so sánh. `Recording` có thể cho thay settings khi chạy theo contract, nhưng cần hiểu ảnh hưởng đến giai đoạn dữ liệu trước/sau thay đổi.

Khi cần biết rốt cuộc cái gì được bật:

```java
Map<String, String> effective = recording.getSettings();
System.out.println(effective.get("jdk.ExecutionSample#enabled"));
```

Đây là snippet minh họa; không suy luận giá trị cụ thể nếu chưa đặt setting. Map mô tả cấu hình **của recording**, không phải bản sao 100% mọi quyết định thấp cấp của provider hoặc bằng chứng event đã phát sinh. Hãy kiểm tra thêm output `.jfr` và môi trường thực thi.

## 14. Kiểm tra recording với `jfr` và JDK Mission Control

Các lệnh phổ biến tương thích với Java 11:

```bash
jfr summary jfr-output/sample.jfr
jfr print --events lesson.Work jfr-output/sample.jfr
jfr metadata jfr-output/sample.jfr
```

- **`jfr summary`:** thống kê tổng quan file và số lượng event theo loại.
- **`jfr print`:** xem nội dung các sự kiện, có thể lọc bằng `--events` để tránh in cả file lớn.
- **`jfr metadata`:** xem mô tả event types/fields được biết trong recording.
- **JDK Mission Control:** thuận tiện khi phân tích tương quan CPU/GC/thread/lock theo timeline, hoặc xây template từ cấu hình có sẵn.

**Tránh đọc toàn bộ file .jfr khổng lồ ra terminal**: output có thể tràn console, gây chi phí xử lý lớn hoặc đưa dữ liệu nhạy cảm vào log. Lọc event name, thời gian hoặc dùng công cụ phân tích phù hợp.

### 14.1. Tại sao `jfr summary` không có fixed expected output?

Thông tin trong một recording gồm thời điểm, JDK version, GC/JVM events phát sinh, chunk count, event size và sampling. Các trường này phụ thuộc:

- Runtime và vendor.
- Thời lượng/khối lượng workload.
- Template default/profile/custom.
- Chính sách chunk/retention.
- JFR event type và setting đã áp dụng.

Vì vậy kiểm thử Java trong mục 11 **chỉ in 7 bất biến**; còn `jfr summary` dùng để xác nhận file hợp lệ và chứa `lesson.Work=3`, không hardcode timestamp hay tổng số event hệ thống.

## 15. Overhead, retention và an toàn production

### 15.1. Giữ overhead ở mức có thể dự đoán

- Bắt đầu với **`default`** cho ghi dài hạn, kiểm tra số event và overhead trên workload thật.
- Khi cần thông tin sâu hơn, bật **`profile` trong khoảng ngắn** hoặc thêm những event cụ thể vào custom config.
- Cân nhắc `threshold` cho duration events: bật mọi socket read/monitor enter ngắn có thể tạo event volume lớn.
- `stackTrace=true` hữu ích để truy nguồn nhưng có thêm chi phí và dữ liệu; chọn có mục đích.
- `period` nhỏ cho sampling/periodic events có thể tăng dữ liệu; không đặt mọi event thành 1 ms một cách máy móc.
- So sánh **CPU, wall-clock latency, GC, disk I/O và kích thước .jfr** khi thử cấu hình mới.

Đừng diễn giải lời giới thiệu “low overhead” thành cam kết JFR miễn phí. Với workload rất nhạy cảm, event tùy chỉnh ghi payload lớn hoặc stack traces tần suất cao có thể tạo tác động đáng kể.

### 15.2. Giới hạn dung lượng và vòng đời

Một recording liên tục không có giới hạn tuổi/kích thước có thể tiêu thụ không gian repository quá mức. Thiết lập giới hạn phù hợp, ví dụ `maxage=1h` và `maxsize=256m`, rồi theo dõi thực tế:

- Chu kỳ dump/snapshot và nơi lưu.
- Dung lượng disk trước/sau dump; retention theo chunks có thể làm kích thước dao động.
- Quản lý vòng đời của các .jfr đã export: lưu bao lâu, ai được xem, khi nào xóa.
- Quy tắc cảnh báo khi ghi file thất bại do permission/volume.
- Với `Recording` API, dùng `try-with-resources` để đóng và giải phóng tài nguyên.

### 15.3. Bảo vệ dữ liệu và endpoint

JFR có thể ghi:

- Tên thread, class, stack traces và tên phương thức.
- Thông tin JVM/process/platform trong các event/metadata tương ứng.
- File path, socket endpoint hoặc command-line arguments tùy cấu hình/runtime.
- Trường của **custom events** mà chính ứng dụng cung cấp.

Đừng commit .jfr chứa dữ liệu production, token, nội dung khách hàng hay cấu hình nhạy cảm vào repository. Đừng tự đưa password, access token, payload người dùng vào field custom event. File JFR cần ACL, encryption-at-rest/transport và retention theo chính sách vận hành.

## 16. Các lỗi thường gặp và hướng xử lý

| Vấn đề | Nguyên nhân phổ biến | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Gọi `settings=profile.jfr` | Nhầm recording file với config | Dùng `settings=profile` hoặc `profile.jfc` |
| Đưa `.jfc` cho `jfr summary` | `jfr summary` cần file **.jfr** | Ghi một recording trước rồi đọc output .jfr |
| `profile` bị chạy mãi trên production | Quên duration/stop và không đánh giá overhead | Ghi ngắn hạn, đo overhead, đặt lifecycle rõ |
| `default` thiếu một loại event | Template default không nhất thiết bật mọi event | Kiểm tra getSettings và tạo custom từ default |
| Sao chép minimal JFC vào prod | Nó không có những event settings JVM như default | Copy đúng default/profile rồi chỉnh có chọn lọc |
| `Configuration.create(Path)` báo `IOException` | Sai file path, working directory, thiếu quyền | Dùng absolute path/đúng runtime, kiểm tra file thực |
| `Configuration.create(...)` báo `ParseException` | XML không hợp lệ, setting/control syntax sai | Kiểm tra JFC root/attributes và parse bằng JDK mục tiêu |
| `jfr configure` không tìm thấy trên JDK 11 | Lệnh cấu hình thuộc công cụ JDK mới, không phải yêu cầu Java 11 | Dùng JMC/copy .jfc/API; kiểm tra `jfr help configure` nếu nâng JDK |
| Đổi `Map getSettings()` mà recording không đổi | Map là bản sao/đối tượng dữ liệu | Gọi `Recording.setSettings(...)` hoặc `enable(...)` |
| `setSettings` chỉ có một entry rồi mất event khác | `setSettings` **replace**, không merge | Bắt đầu bằng copy map default rồi override |
| Không có `jdk.ExecutionSample` trong .jfr | Event chưa bật, workload quá ngắn hoặc lấy mẫu không xuất hiện | Kiểm tra profile/custom, duration và metadata |
| Custom event không xuất hiện | Tên `@Name` khác JFC, event disabled hoặc commit ngoài thời gian recording | So khớp full name, bật event, kiểm tra start/stop và file |
| Ghi file không được | Path của JVM đích khác shell, permission hoặc disk đầy | Dùng absolute path, kiểm tra container/PID/ACL |
| `jcmd` không attach được | Sai PID, khác user/container namespace hoặc disable attach | Chạy đúng quyền/JDK và cơ chế diagnostics cho phép |
| JVM ngừng trước khi `duration` kết thúc | Không đủ thời gian thu dữ liệu | Dùng `dumponexit=true`, chạy workload đủ dài |
| Cố định exact số event của default giữa JDK | Template có thể thay đổi theo JDK/vender | So sánh runtime hiện tại, không hardcode event count |
| Tệp .jfr lớn gây OOM khi parse | `RecordingFile.readAllEvents` gom toàn bộ List | Dùng vòng `RecordingFile.readEvent` hoặc công cụ phân tích |
| Debug output làm lộ dữ liệu | Ghi mọi event/stack/metadata vào log | Lọc, mask và bảo vệ nơi lưu |
| Sai cú pháp dấu phân cách `jcmd` | Nhầm với startup option comma-separated | `jcmd PID JFR.start key=value key=value` dùng dấu cách |
| Giữ file JDK default.jfc đã sửa | Update JDK ghi đè hoặc tác động nhiều process | Copy vào config ứng dụng rồi version control bản **không chứa secret** |

**Quan trọng về lỗi:** nếu một recording không có CPU hotspot sample, đừng kết luận CPU không có tải. Sampling phụ thuộc period, thời lượng, thread state và event settings; phân biệt **không quan sát được** với **không tồn tại**.

## 17. Chọn cấu hình thực tế theo mục tiêu

| Tình huống | Cấu hình khởi đầu | Cần chú ý |
| --- | --- | --- |
| Theo dõi service ổn định 24/7 | `default` | Đặt retention, dump định kỳ, đánh giá overhead |
| CPU đột ngột tăng | `profile` 30–120 giây | Quan sát sampling, stack traces; không bật vô hạn |
| Theo dõi custom business events | `default` + `Recording.enable(CustomEvent.class)` hoặc custom JFC | Không ghi PII/secret; giới hạn tần suất event |
| Một loại I/O event bị thiếu | Copy `default.jfc` rồi bật event/điều chỉnh threshold | Xác minh tên setting trên JDK đang dùng |
| Muốn ghi trace chi tiết ở load test | `profile` hoặc custom JFC | Đo thêm overhead để diễn giải kết quả load test |
| Service chạy trong container | `default` với path/retention tường minh | Kiểm tra PID namespaces, disk volume và quyền attach |
| JDK nâng từ 11 lên 21/25 | Đánh giá lại template `.jfc` | Event types/defaults có thể khác, không giữ giả định cũ |
| Chỉ cần đo một custom event ngắn | Minimal JFC trong test | Không coi cấu hình minimal là production monitoring |

## 18. Tự kiểm tra kiến thức

**Câu 1.** `default` và `profile` khác nhau chủ yếu ở đâu?  
**Đáp án:** Cả hai là **event configurations**, nhưng `default` cân bằng dữ liệu và overhead cho ghi dài hạn; `profile` tăng lượng thông tin cho profiling ngắn hạn.

**Câu 2.** `custom.jfc` có phải file kết quả ghi CPU/GC không?  
**Đáp án:** Không. Nó là XML configuration. Kết quả được ghi trong file **.jfr**.

**Câu 3.** `jcmd PID JFR.start settings=default` và `-XX:StartFlightRecording=settings=default` có dùng cùng dấu phân cách không?  
**Đáp án:** Không. `jcmd` dùng các `key=value` cách nhau bằng **dấu cách**, còn một JVM `-XX:StartFlightRecording` option dùng **dấu phẩy**.

**Câu 4.** Nếu `default.jfc` không bật event `jdk.SocketRead`, có chứng minh hệ thống không có socket reads không?  
**Đáp án:** Không. Chỉ chứng minh recording không thu thập loại event theo cách cần thiết; có thể thiếu cả do threshold/sampling.

**Câu 5.** Làm sao thêm `lesson.Work` mà vẫn giữ các settings default?  
**Đáp án:** Tạo `new Recording(Configuration.getConfiguration("default"))` rồi `recording.enable(Work.class)`, hoặc sao chép đầy đủ map default rồi thêm key, không thay bằng map chỉ có một entry.

**Câu 6.** Trên Java 11, có thể đọc tệp `.jfc` qua API nào?  
**Đáp án:** `Configuration.create(Path)` hoặc `Configuration.create(Reader)`.

**Câu 7.** `Configuration.getSettings().put(...)` có tự đổi file default.jfc không?  
**Đáp án:** Không. `getSettings()` là dữ liệu trả về, không chỉnh template gốc. Muốn đổi recording cần dùng API cấu hình đúng.

**Câu 8.** `jfr summary` có dùng để đọc .jfc không?  
**Đáp án:** Không. Nó dùng để xem **recording file .jfr**.

**Câu 9.** Tại sao không nên bật mọi event với threshold thấp cho production?  
**Đáp án:** Event volume, stack traces và overhead/dung lượng có thể tăng mạnh; chỉ bật theo mục tiêu và đo hiệu năng thực tế.

**Câu 10.** Bài test Java có đúng 3 `lesson.Work` events thì chứng minh mọi JDK đều có cùng số CPU sample không?  
**Đáp án:** Không. Chỉ số custom event được chương trình commit là 3; số event JVM/sampling của JFR thay đổi theo runtime và workload.

**Câu 11.** Nếu dùng JDK 11 không có `jfr configure`, làm sao custom JFC?  
**Đáp án:** Copy file `default.jfc`, chỉnh hợp lệ, sử dụng JDK Mission Control hoặc `Configuration.create(Path)`/`Recording` API; không phụ thuộc lệnh chỉ có trên JDK mới.

**Câu 12.** Nếu recording được bật mặc định và không giới hạn size/age, nguy cơ gì?  
**Đáp án:** Có thể tạo dữ liệu quá lớn, chiếm repository/disk. Thiết lập retention và giám sát phù hợp.

## 19. Ghi nhớ và nguồn tham khảo

- **`default.jfc`**: cấu hình JFR dựng sẵn, overhead thấp hơn về ý định, phù hợp baseline/continuous.
- **`profile.jfc`**: cấu hình nhiều thông tin hơn, hữu ích cho profiling có thời lượng giới hạn.
- **`.jfc` là XML config**, **`.jfr` là binary recording**; chọn config bằng `settings=default`, `settings=profile` hoặc `settings=/path/custom.jfc`.
- **`jcmd JFR.start`**, **`-XX:StartFlightRecording`** và **`jdk.jfr.Recording`** đều còn được hỗ trợ; cú pháp và vòng đời khác nhau.
- **`Configuration.getConfiguration(...)`**, **`Configuration.create(Path/Reader)`** và **`Recording( Configuration )`** dùng được từ Java 11.
- **Đừng chỉnh template trong JDK**; tạo bản sao cấu hình cho ứng dụng, validate và kiểm thử .jfr thật.
- **Chỉ thêm event cần**, kiểm soát threshold/sampling/stack trace, giới hạn maxage/maxsize/duration, bảo vệ dữ liệu JFR.
- **Không hardcode số event, overhead hoặc cú pháp lệnh JDK mới** cho tất cả phiên bản; đọc đúng runtime đang chạy.
- Các ví dụ Java 11 đã chạy và cho output tương ứng: **7 dòng** trong `JfrSettingsDemo`, **3 dòng** trong `MinimalJfcDemo`, và startup JFR tạo file .jfr đọc được bằng `jfr summary`.

**Tài liệu chính thức còn áp dụng:**

1. [Oracle Java 11 — JFR Diagnostic Tools](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html).
2. [Oracle Java 11 — Configuration API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Configuration.html).
3. [Oracle Java 11 — Recording API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html).
4. [Oracle Java 11 — RecordingFile API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
5. [Oracle Java 24 — Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html).
6. [Oracle Java 25 — jfr Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html).
7. [Oracle Java 26 — Configuration API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Configuration.html).
8. [Dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/).
9. [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328).
