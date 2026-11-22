# 14.6 Điều chỉnh enabled, threshold, period và stackTrace của event trong JFR

## 1. Học cách kiểm soát bằng chứng JFR

Java Flight Recorder (JFR) ghi các **event** về JVM và ứng dụng: GC, CPU, thread, lock, I/O, allocation, class loading và event do ứng dụng định nghĩa. Không nên bật tất cả loại event ở mức chi tiết tối đa một cách mặc định: dữ liệu có thể rất lớn, gây khó phân tích và tăng chi phí giám sát. Ngược lại, cấu hình quá chặt có thể bỏ sót đúng hiện tượng đang điều tra.

Bốn setting cốt lõi của một **event type** là:

- `enabled`: event type đó có được ghi hay không.
- `threshold`: thời lượng tối thiểu để giữ một **duration event**.
- `period`: chu kỳ phát/lấy mẫu của **periodic event** có hỗ trợ.
- `stackTrace`: ghi kèm call stack hay không.

Đây là **event settings**. Chúng khác với **recording options** như `name`, `duration`, `filename`, `disk`, `maxsize`, `maxage`; các tùy chọn này điều khiển vòng đời và nơi lưu của cả recording. Một JVM có thể có nhiều recording; muốn diễn giải dữ liệu phải biết event type, recording, JDK và cấu hình hiệu lực.

Ví dụ bài toán: p99 request tăng mạnh, nghi có thread phải chờ lock lâu. Thay vì bật mọi thứ, bạn có thể bật `jdk.JavaMonitorEnter`, dùng `threshold=20 ms` để tập trung vào các lần chờ đáng kể, bật `stackTrace=true` để biết điểm gọi code, đồng thời ghi thêm CPU định kỳ bằng `jdk.CPULoad#period=1 s`. Sau đó kiểm tra log thực tế để biết thu đúng hay chưa.

Phạm vi: JDK 17+ với cú pháp và API được minh họa theo JDK 21. Tên event, default và setting descriptor tùy từng JDK/build. Một setting không được event type hỗ trợ không tự trở nên có hiệu lực chỉ vì ta viết nó vào cấu hình.

## 2. Bảng ý nghĩa chính xác

| Setting | Ý nghĩa | Giá trị ví dụ | Không nên nhầm |
| --- | --- | --- | --- |
| `enabled` | Cho phép hoặc không cho phép ghi event loại đó | `true`, `false` | Không bật/tắt toàn bộ JVM hay JFR |
| `threshold` | Bỏ event có duration **nhỏ hơn** ngưỡng | `0`, `10 ms`, `1 s` | Không phải số event mỗi giây hay timeout ứng dụng |
| `period` | Nhịp thu event định kỳ/lấy mẫu | `20 ms`, `1 s`, `everyChunk` | Không phải bộ lọc độ dài của sự kiện lock/I/O |
| `stackTrace` | Có thêm stack trace tại điểm phát/commit phù hợp event | `true`, `false` | Không phải distributed trace hoặc automatic root-cause analysis |

### 2.1. `enabled`

Khi `enabled=false`, JFR không ghi event type đó vào recording áp dụng cấu hình ấy. Các hoạt động Java thật vẫn diễn ra: thread vẫn chờ lock, CPU vẫn chạy, I/O vẫn thực hiện. Giá trị `true` chỉ là điều kiện cần: nếu không có hoạt động phát event, threshold lọc hết, hoặc recording không trùng cửa sổ lỗi, bạn vẫn có thể nhận 0 sự kiện.

Ví dụ:

```text
jdk.JavaMonitorEnter#enabled = true
jdk.CPULoad#enabled = true
```

Đừng coi “default enabled=true” trong phần mô tả `jdk.jfr` là bằng chứng mọi event JDK đang có trong file. Annotation mặc định có thể bị `default.jfc`, `profile.jfc` hoặc override khi tạo recording thay đổi. Hãy kiểm tra **effective settings** của recording cụ thể.

### 2.2. `threshold`

Đây là **bộ lọc theo duration** của event type có hỗ trợ ngưỡng. `threshold=20 ms` có nghĩa event kéo dài 8 ms bị loại; event kéo dài 45 ms được phép ghi nếu `enabled=true` và không có điều kiện nào khác loại nó. `threshold=0` nghĩa là không đặt giới hạn tối thiểu theo duration.

Tình huống hợp lý:

- `jdk.JavaMonitorEnter#threshold=20 ms`: tập trung vào các lần chờ monitor tương đối lâu.
- `jdk.FileRead#threshold=50 ms`: tìm thao tác đọc file chậm, sau đó dùng stack trace để xác định caller.
- Custom duration event `demo.Operation#threshold=25 ms`: ghi các tác vụ ứng dụng mất ít nhất khoảng 25 ms.

Ngưỡng không đổi thời lượng hoạt động; nó chỉ quyết định lưu thông tin. Nếu 10.000 thao tác mỗi thao tác chậm 5 ms cùng gây tổng độ trễ lớn, `threshold=100 ms` có thể làm file gần như không có event dù ứng dụng thực sự chậm. Đặt quá thấp lại có thể ghi quá nhiều event và stack.

Cú pháp chuẩn trong Java API: `"20 ms"`, `"1 s"`; các đơn vị hỗ trợ gồm `ns`, `us`, `ms`, `s`, `m`, `h` và `d`. Với CLI, giá trị `20ms` bỏ khoảng trắng thường được chấp nhận. Không viết số trần khi chưa biết parser quy định đơn vị ra sao.

### 2.3. `period`

`period` áp dụng cho **periodic events** hoặc sampling events có công bố setting này. `jdk.CPULoad#period=1 s` yêu cầu mẫu CPU theo nhịp khoảng một giây. Một event execution sampling có thể có period riêng để đổi mật độ mẫu.

Giá trị `everyChunk` nghĩa phát theo chu kỳ chunk dữ liệu JFR, **không có nghĩa đúng mỗi N mili giây**. Với `1 s` hay `20 ms`, cũng phải chấp nhận sai lệch do scheduling/implementation; đây là nhịp mục tiêu, không phải bộ đồng hồ độ chính xác tuyệt đối.

Không thể dùng `period` để biến `jdk.JavaMonitorEnter` thành ticker phát mỗi giây: event này là hoạt động chờ monitor, không phải loại định kỳ. Muốn tìm lần chờ dài, dùng `threshold`. Muốn lấy trend CPU, dùng `period` trên event đúng loại.

### 2.4. `stackTrace`

`stackTrace=true` yêu cầu JFR lưu Java call stack cho event type hỗ trợ. Với custom event phát bằng `Event.commit()`, stack trace được thu tại điểm commit; với event JVM cung cấp, vị trí thu stack còn phụ thuộc event type. Stack giúp quy về call site, nhưng không tự giải thích toàn bộ chuỗi request hay tác nhân bên ngoài JVM.

`stackTrace=false` vẫn cho phép ghi các trường khác: thời điểm, duration, thread, payload và một số thông tin riêng của event. Tắt stack có thể giảm overhead/dung lượng, nhưng khiến việc truy đến code giữ lock hoặc làm I/O chậm khó hơn.

Chi phí stack trace lớn hay nhỏ phụ thuộc **số event**, độ sâu stack, cách JVM thu mẫu và cấu hình runtime. Một vài stack của những lần contention dài thường hữu ích; hàng triệu event rất ngắn kèm stack có thể gây nhiễu đáng kể.

## 3. Phân biệt duration event và periodic event

Hai loại cơ chế có thể hình dung như sau:

```text
Duration event (lock, file read, custom operation)
    hoạt động diễn ra -> có event với duration
          |
          +-- enabled=false ------------------> không ghi
          |
          +-- duration < threshold -----------> không ghi
          |
          +-- đạt điều kiện ------------------> ghi field/duration
                                                   |
                                                   +-- stackTrace=true -> thêm stack nếu hỗ trợ
```

```text
Periodic/sampling event (ví dụ jdk.CPULoad)
    enabled=true
          |
          +-- period=1 s -> yêu cầu nhịp phát khoảng mỗi giây
          |
          +-- thu mẫu/thống kê -> ghi event nếu có mẫu và các điều kiện thỏa
```

Đây là hình khái niệm, không phải sơ đồ triển khai nội bộ JFR. Quy tắc phân tích vẫn là: **threshold lọc duration của từng event; period chi phối nhịp periodic/sampling**.

| Câu hỏi vận hành | Event phù hợp | Setting trọng tâm |
| --- | --- | --- |
| Những lần thread chờ `synchronized` trên 20 ms nằm ở đâu? | `jdk.JavaMonitorEnter` | `enabled=true`, `threshold=20 ms`, `stackTrace=true` |
| CPU có spike trong 10 phút không? | `jdk.CPULoad` | `enabled=true`, `period=1 s` |
| File read nào kéo dài trên 50 ms? | `jdk.FileRead` | `enabled=true`, `threshold=50 ms`, tùy nhu cầu `stackTrace` |
| Đang nghi CPU hotspot ngắn | `jdk.ExecutionSample` | `enabled` và `period` nếu event descriptor cho phép |
| Muốn ghi tác vụ nghiệp vụ do mình định nghĩa trên 25 ms | `demo.Operation` | `enabled=true`, `threshold=25 ms`, `stackTrace=true` |

Các giá trị trên chỉ là điểm khởi đầu, không phải “mức tốt nhất” cho mọi service. Nên đo event count, kích thước file, CPU và tác động lên latency khi điều chỉnh.

## 4. Cú pháp event setting và cấu hình có hiệu lực

### 4.1. Dạng khóa `event#setting`

Theo API của JFR, key gồm tên đầy đủ của event và tên setting, phân cách bằng `#`:

```text
jdk.JavaMonitorEnter#enabled=true
jdk.JavaMonitorEnter#threshold=20 ms
jdk.JavaMonitorEnter#stackTrace=true
jdk.CPULoad#enabled=true
jdk.CPULoad#period=1 s
```

Trong `.jfc`, mỗi setting được đặt bên trong một phần tử `<event name="...">`. Trong lệnh `jfr configure` hay `JFR.start`, dùng `event#setting=value`, thường viết `20ms` không có khoảng trắng. Trong Java API, một map có key `"jdk.CPULoad#period"`, value `"1 s"`.

Nếu event class trùng tên giữa nhiều classloader, API còn có dạng `<event-id>#<setting>`. Event ID chỉ có ý nghĩa ở JVM instance hiện tại, vì vậy không lưu số ID cứng để dùng cho tất cả môi trường.

### 4.2. Không phải event nào cũng hỗ trợ cả bốn setting

Kiểm tra `EventType.getSettingDescriptors()` trong JVM thật. Với event duration, có thể thấy `threshold`; với event định kỳ như `jdk.CPULoad`, thường có `period`. Đừng đoán rằng mọi sự kiện có `stackTrace` hay `period`. Custom event không tự động trở thành periodic chỉ vì bạn truyền một chu kỳ.

Tương tự, một số event có setting riêng hoặc sử dụng cơ chế lấy mẫu riêng. Đọc tên và default setting từ chính JDK. Metadata này là **khả năng của event type**, còn cấu hình recording thực tế có thể override default.

### 4.3. Các tầng cấu hình

- **Annotation trên class** như `@Enabled`, `@Threshold`, `@Period` và `@StackTrace` cung cấp default của event type nếu được khai báo.
- **JFC file** (`default.jfc` hoặc `profile.jfc`, hoặc bản tùy chỉnh) mô tả settings đưa vào một recording.
- **Override trong lệnh start** `-XX:StartFlightRecording` hay `jcmd ... JFR.start` có thể đặt giá trị ưu tiên hơn JFC cho recording mới.
- **Java API** `Recording.enable(...).with...` và `Recording.setSettings(...)` cấu hình riêng recording do chương trình quản lý.

`default.jfc` được thiết kế cho ghi liên tục với chi phí thấp; `profile.jfc` chứa nhiều dữ liệu hơn và thường phù hợp phiên profiling ngắn. Không sửa bản JFC chuẩn bên trong `JAVA_HOME/lib/jfr`: tạo bản mới để dễ đối chiếu/reproduce. Mỗi recording có cấu hình riêng; khi nhiều recording đồng thời, tổng chi phí JVM có thể tăng.

## 5. Tạo cấu hình JFC bằng `jfr configure`

### 5.1. Tạo file từ default profile

JDK 19+ khuyến khích sử dụng `jfr configure` để sinh file cấu hình. Ví dụ (thực hiện trong thư mục có quyền ghi):

```bash
jfr configure --output diagnostics.jfc jdk.JavaMonitorEnter#enabled=true jdk.JavaMonitorEnter#threshold=20ms jdk.JavaMonitorEnter#stackTrace=true jdk.CPULoad#enabled=true jdk.CPULoad#period=1s
```

Khi không có `--input`, công cụ dùng cấu hình mặc định làm nền. File kết quả `diagnostics.jfc` giữ những setting khác từ template và thay các setting được chỉ định. Nếu event chưa hiện diện trong template, `jfr configure` có cú pháp thêm mới với dấu `+` trước tên event; kiểm tra `jfr help configure` trong JDK đang dùng.

Về ý nghĩa, những phần tương ứng trong XML có hình dạng:

```xml
<event name="jdk.JavaMonitorEnter">
    <setting name="enabled">true</setting>
    <setting name="threshold">20 ms</setting>
    <setting name="stackTrace">true</setting>
</event>
<event name="jdk.CPULoad">
    <setting name="enabled">true</setting>
    <setting name="period">1 s</setting>
</event>
```

Đây chỉ là **trích đoạn**, chưa phải file JFC hoàn chỉnh; tệp thật phải có phần tử `<configuration ...>` bao quanh và các event khác nếu muốn giữ cấu hình từ template.

### 5.2. Ghi JFR trên JVM đang chạy

Xác định PID JVM:

```bash
jcmd -l
```

Chạy ví dụ sau, **thay PID 12345 và các đường dẫn bằng giá trị thực**; sử dụng đường dẫn tuyệt đối cho service/container để tránh nhầm thư mục:

```bash
jcmd 12345 JFR.start name=lock_diagnostics settings=diagnostics.jfc duration=2m filename=lock_diagnostics.jfr
jcmd 12345 JFR.check name=lock_diagnostics verbose=true
```

`JFR.start` tạo recording với settings đã chọn. `JFR.check verbose=true` giúp xem event settings của recording **khi vẫn còn hoạt động**. Đừng chỉ dựa vào thông báo “Started recording”; xác minh đúng JVM/PID và cấu hình thực.

Có thể override nhanh các setting khi start:

```bash
jcmd 12345 JFR.start name=lock_short settings=default duration=60s filename=lock_short.jfr jdk.JavaMonitorEnter#enabled=true jdk.JavaMonitorEnter#threshold=10ms jdk.JavaMonitorEnter#stackTrace=true
```

Ở CLI, từng cặp `event#setting=value` là một token; thời lượng `10ms` viết liền để tránh bị shell tách thành hai phần. Override áp dụng cho recording mới, không ngầm thay mọi recording đang hoạt động.

Nếu muốn dừng trước thời hạn và xuất file:

```bash
jcmd 12345 JFR.stop name=lock_diagnostics filename=lock_diagnostics.jfr
```

Không chạy lệnh stop lại khi recording đã kết thúc theo `duration`. Các lệnh attach bằng `jcmd` cần quyền phù hợp; kết quả có thể khác giữa JVM trong container và tiến trình trên máy host.

### 5.3. Đọc file, kiểm tra kết quả thay vì tin cấu hình

```bash
jfr summary lock_diagnostics.jfr
jfr print --events jdk.JavaMonitorEnter lock_diagnostics.jfr
jfr print --events jdk.CPULoad lock_diagnostics.jfr
jfr print --stack-depth 20 --events jdk.JavaMonitorEnter lock_diagnostics.jfr
```

`jfr summary` hiển thị số lượng từng loại event được ghi trong file; `jfr print` cho phép lọc event cụ thể. `--stack-depth 20` chỉ điều chỉnh số frame **hiển thị** từ stack đã ghi, không khôi phục stack chưa được thu.

Ví dụ không thấy `jdk.JavaMonitorEnter` thì có nhiều khả năng: không xảy ra contention, những lần chờ đều dưới ngưỡng, recording không trùng cửa sổ sự cố, event chưa bật, hoặc nhầm JVM/file. **0 event chưa chứng minh “không có vấn đề lock”.**

Khi có file, JDK Mission Control (JMC) giúp đối chiếu thống kê theo thời gian, nhóm stack trace và xem biểu đồ cùng GC/CPU/thread. Cần giữ nguyên metadata thời gian, cấu hình và workload khi so sánh trước–sau.

## 6. Java 17+ runnable: event tùy chỉnh + periodic event

Một custom event không tự phát theo `period`; ứng dụng phải tạo và `commit` event. Chương trình dưới đây ghi một duration event tên `demo.Operation` cho hai thao tác, đặt threshold 25 ms và bật stack. Đồng thời bật periodic event `jdk.CPULoad` để minh họa `period` độc lập.

Tạo file **`JfrSettingsDemo.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Enabled;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;

public final class JfrSettingsDemo {
    @Name("demo.Operation")
    @Label("Demo operation")
    @Category({"Demo", "Diagnostics"})
    @Enabled(false)
    @Threshold("0 ms")
    @StackTrace(false)
    public static final class OperationEvent extends Event {
        @Label("Operation name")
        public String operation;
    }

    private static void measure(String name, long milliseconds)
            throws InterruptedException {
        OperationEvent event = new OperationEvent();
        event.operation = name;
        event.begin();
        Thread.sleep(milliseconds);
        event.end();
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("jfr-settings-demo.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(OperationEvent.class)
                    .withThreshold(Duration.ofMillis(25))
                    .withStackTrace();

            recording.enable("jdk.CPULoad")
                    .withPeriod(Duration.ofSeconds(1));

            recording.start();
            measure("fast", 1);
            measure("slow", 80);
            Thread.sleep(1200);
            recording.stop();
            recording.dump(output);
        }

        System.out.println("Recording completed");
    }
}
```

Biên dịch và chạy:

```bash
javac JfrSettingsDemo.java
java JfrSettingsDemo
jfr summary jfr-settings-demo.jfr
jfr print --events demo.Operation jfr-settings-demo.jfr
jfr print --events jdk.CPULoad jfr-settings-demo.jfr
```

**Stdout của riêng chương trình Java khi ghi file thành công:**

```text
Recording completed
```

Các lệnh `jfr summary`/`jfr print` sinh output thay đổi theo máy, phiên bản JDK, scheduling và dữ liệu thu được; không có transcript cố định để chép. Trong điều kiện thông thường, `slow` sẽ dài hơn 25 ms và được giữ, còn `fast` khoảng 1 ms sẽ bị lọc. `Thread.sleep` không bảo đảm độ trễ tuyệt đối khi máy rất bận, vì vậy không tuyên bố số event luôn bằng 1.

Các điểm cần giải thích:

1. `@Enabled(false)`, `@Threshold("0 ms")` và `@StackTrace(false)` mô tả default của custom event class.
2. `recording.enable(OperationEvent.class)` bật event trong recording đang tạo; `withThreshold(Duration.ofMillis(25))` và `withStackTrace()` ghi đè cấu hình mặc định cho recording này.
3. `event.begin()` và `event.end()` tạo duration; `event.commit()` gửi event để JFR xét điều kiện thu. `Event.shouldCommit()` có thể giúp tránh tạo payload đắt khi event sẽ không được ghi.
4. `recording.enable("jdk.CPULoad").withPeriod(...)` cấu hình **một event định kỳ khác**, không biến `OperationEvent` thành periodic.
5. Stack của custom event được thu theo điểm `commit`. Muốn gắn context nghiệp vụ chuẩn, nên đặt payload và nơi commit phù hợp; stack đơn lẻ không thay thế trace từ đầu đến cuối request.
6. `stop()` ngừng recording; `dump(output)` lưu file để quan sát; `try-with-resources` đóng recording. File có thể chứa thông tin runtime nhạy cảm, cần quản lý quyền truy cập.

### 6.1. Thay toàn bộ setting map bằng `Recording.setSettings`

Java API còn hỗ trợ:

```java
// Fragment dùng trong nơi đã có biến recording kiểu jdk.jfr.Recording.
recording.setSettings(java.util.Map.of(
    "demo.Operation#enabled", "true",
    "demo.Operation#threshold", "25 ms",
    "demo.Operation#stackTrace", "true",
    "jdk.CPULoad#enabled", "true",
    "jdk.CPULoad#period", "1 s"
));
```

Đây là **fragment minh họa, không phải chương trình độc lập**. `setSettings` **thay toàn bộ map settings** của recording: nếu chỉ truyền một entry, bạn có thể vô tình xóa cấu hình khác đang có. Khi chỉ sửa vài lựa chọn, chuỗi `enable(...).with...` thường rõ và an toàn hơn. Có thể xem map settings của recording bằng `recording.getSettings()`.

## 7. Truy vấn setting được event type thật sự hỗ trợ

Không cần đoán tên setting: API `FlightRecorder.getEventTypes()` và `EventType.getSettingDescriptors()` cho phép hỏi JVM. Tạo file **`ListJfrSettings.java`**:

```java
import java.util.Set;
import jdk.jfr.EventType;
import jdk.jfr.FlightRecorder;
import jdk.jfr.SettingDescriptor;

public final class ListJfrSettings {
    public static void main(String[] args) {
        Set<String> targets = Set.of(
                "jdk.JavaMonitorEnter", "jdk.CPULoad");

        for (EventType type
                : FlightRecorder.getFlightRecorder().getEventTypes()) {
            if (!targets.contains(type.getName())) {
                continue;
            }
            System.out.println(type.getName());
            for (SettingDescriptor setting
                    : type.getSettingDescriptors()) {
                System.out.println("  " + setting.getName()
                        + " = " + setting.getDefaultValue());
            }
        }
    }
}
```

```bash
javac ListJfrSettings.java
java ListJfrSettings
```

Thứ tự và các dòng output phụ thuộc JDK và danh sách event types, không cố định. Hãy xác nhận `jdk.JavaMonitorEnter` có `threshold`/`stackTrace` và `jdk.CPULoad` có `period`. `SettingDescriptor.getDefaultValue()` là default **của event type**; nó không phải cam kết rằng recording hiện tại giữ nguyên giá trị ấy. Cấu hình recording có thể kiểm tra bằng `Recording.getSettings()` hoặc `jcmd ... JFR.check verbose=true`.

Nếu custom event class được tải qua nhiều classloader, cần thận trọng phân biệt event name với event ID. Không hardcode ID cho các lần chạy khác nhau.

## 8. Chiến lược chỉnh setting để tìm nguyên nhân

Giả sử latency p99 tăng và nghi monitor contention:

1. **Nêu giả thuyết cụ thể:** có những lần chờ lock dài làm request chậm, hay có rất nhiều lần chờ ngắn cộng dồn?
2. **Chọn event đúng:** `jdk.JavaMonitorEnter` cho monitor contention; nếu nghi CPU, xem thêm `jdk.ExecutionSample` và `jdk.CPULoad`; nếu nghi I/O, chọn `jdk.FileRead`/`jdk.SocketRead` phù hợp.
3. **Đặt mức đầu tiên:** với giả thuyết lock dài, thử `enabled=true`, `threshold=20 ms` và `stackTrace=true`, ghi ngắn khoảng 1–2 phút ở đúng thời gian sự cố.
4. **Kiểm tra hiệu lực:** `JFR.check verbose=true` trước khi kết thúc, `jfr summary` và `jfr print` sau khi dump. Đừng gộp dữ liệu của nhiều PID/recording.
5. **Điều chỉnh nếu bỏ sót:** nếu 0 event nhưng request vẫn chậm, kiểm tra đúng event trước; sau đó cân nhắc hạ threshold trong một phép đo mới, hoặc điều tra nguyên nhân khác.
6. **Đối chiếu bối cảnh:** timeline từ JFR, request trace, CPU, thread dump, GC pauses, thread pool và thông tin OS/container.
7. **Đo overhead:** số event/giây, kích thước recording, CPU, disk I/O và tác động latency; giữ mức thấp nhất đủ giải thích hiện tượng.
8. **Ghi lại cấu hình và kết quả:** JDK version, collector, workload, thời gian, settings, event counts và các thay đổi đã thử.

| Thao tác | Lợi ích | Đánh đổi |
| --- | --- | --- |
| `enabled=false → true` | Bắt đầu có thể thu event type liên quan | Tăng chi phí/volume; có thể vẫn 0 event nếu không phát sinh |
| `threshold=100 ms → 5 ms` | Nhìn thấy nhiều duration events ngắn | File lớn hơn; nhiều stack hơn nếu bật |
| `threshold=0 → 50 ms` | Tập trung vào các thao tác dài | Không thấy tích lũy của nhiều thao tác ngắn |
| `period=1 s → 20 ms` | Lấy mẫu dày hơn cho event hỗ trợ | Sampling overhead; không bảo đảm mọi spike |
| `stackTrace=false → true` | Có thêm bối cảnh code | Có thể tăng overhead đáng kể trên event dày |
| `stackTrace=true → false` | Ít dữ liệu/chi phí hơn | Thiếu caller context khi phân tích |

Để so sánh hai recording, dùng cùng workload/giới hạn tài nguyên/JDK và thời lượng tương đương. So sánh số lượng **theo thời gian**, phân phối duration và vị trí stack thay vì chỉ so raw count giữa các file khác thời lượng.

## 9. Các lỗi tư duy và cấu hình phổ biến

**Lỗi 1: Dùng `period` như `threshold`.** `jdk.CPULoad#period=1 s` điều chỉnh nhịp ghi thông tin CPU; `jdk.JavaMonitorEnter#threshold=1 s` chỉ giữ các lần chờ lock kéo dài ít nhất khoảng 1 giây. Hai cấu hình không có chung nghĩa “mỗi giây một event”.

**Lỗi 2: Dùng `threshold` trên periodic event không hỗ trợ.** Nếu event type không công bố setting đó, phải dùng setting đúng (thường là `period`). `jfr configure` không biến một setting không hỗ trợ thành cơ chế mới.

**Lỗi 3: Kết luận không có sự cố vì event count bằng 0.** Có thể threshold quá cao, recording sai thời điểm/PID, event disable, hoặc không có hoạt động tương ứng trong khoảng đo. Kiểm tra điều kiện phát sinh trước khi suy luận.

**Lỗi 4: Bật mọi event và stack trace mà không kiểm tra overhead.** Hãy ưu tiên các event giải quyết giả thuyết; thay đổi từng nhóm nhỏ và xem `jfr summary`, CPU, disk, latency.

**Lỗi 5: Chỉ đọc default annotation.** Cấu hình JFC và override của recording mới quyết định event thực tế ghi những gì. `@Enabled(true)` không chứng minh file JFR đang có event.

**Lỗi 6: Dùng `Recording.setSettings(Map.of(...))` như phép cập nhật một khóa.** API này **replace** toàn bộ map, không merge; dùng `EventSettings` hoặc tạo map mới đã hợp nhất những lựa chọn cần giữ.

**Lỗi 7: Thấy thiếu stack rồi tăng `jfr print --stack-depth`.** Lệnh in không tạo ra frame chưa được ghi. Cần thu recording mới với `stackTrace=true` nếu event hỗ trợ và yêu cầu nghiệp vụ cần.

**Lỗi 8: Gọi `jcmd JFR.configure` để kỳ vọng đổi mọi event trong recording đang chạy.** `jfr configure` là công cụ tạo JFC; `JFR.start` chọn settings cho recording mới; `JFR.configure` của `jcmd` phục vụ các lựa chọn cấu hình JFR ở mức JVM, không tương đương việc gọi `Recording.setSettings` trên một recording đã tồn tại.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Cần tìm lần chờ monitor trên 30 ms kèm code call site. Nên dùng gì?

*Đáp án:* Chọn event `jdk.JavaMonitorEnter` và thử `enabled=true`, `threshold=30 ms`, `stackTrace=true`. Kiểm tra event descriptor trước, thu đúng thời điểm lỗi, đối chiếu với thread/request traces.

**Câu 2.** Cần CPU trend mỗi 2 giây trong 10 phút, có nên dùng `threshold=2 s` trên `jdk.CPULoad`?

*Đáp án:* Không. Sử dụng `jdk.CPULoad#period=2 s` nếu event hỗ trợ; `threshold` không mô tả chu kỳ của sự kiện này.

**Câu 3.** Khi `enabled=true` và `threshold=100 ms`, `jfr summary` có 0 `jdk.FileRead` events, có thể kết luận toàn bộ file I/O đều nhanh không?

*Đáp án:* Không. Có thể có nhiều file reads dưới 100 ms, hoặc recording không trúng tải, hoặc sai JVM/file. Muốn biết chính xác phải kiểm tra cửa sổ đo, cấu hình và có thể hạ threshold trong phép thu mới.

**Câu 4.** Tăng `stackTrace=true` khi ghi CPU load định kỳ có chắc tạo ra execution flame graph không?

*Đáp án:* Không. CPU load là thống kê định kỳ; muốn phân tích nơi CPU được tiêu tốn, dùng execution sampling/profiling events phù hợp và kiểm tra khả năng stack của event đó.

**Câu 5.** Khi custom event khai `@Enabled(false)`, có thể bật bằng Java API không?

*Đáp án:* Có. `recording.enable(CustomEvent.class)` có thể bật trong recording đó; config lớp là baseline và có thể bị override.

## 11. Checklist khi bàn giao một bản ghi JFR

- [ ] Ghi rõ **JDK/build**, JVM/PID, thời gian bắt đầu/kết thúc, tên recording và tên file.
- [ ] Phân biệt event settings với recording options.
- [ ] Kiểm tra event type có thật và hỗ trợ `enabled`, `threshold`, `period`, `stackTrace` nào.
- [ ] Chọn `threshold` cho duration events; `period` cho periodic/sampling events.
- [ ] Ghi rõ stack trace bật hay tắt, và không kỳ vọng công cụ đọc phục hồi dữ liệu thiếu.
- [ ] Nắm nguồn cấu hình: annotation → JFC → CLI hoặc Java API override.
- [ ] Dùng `JFR.check verbose=true` hoặc `Recording.getSettings()` để kiểm tra thực tế.
- [ ] Dùng `jfr summary`/`jfr print` để xác nhận dữ liệu đã được thu.
- [ ] Đối chiếu event với request timeline, CPU/GC/thread/I/O và workload.
- [ ] Kiểm tra overhead, số lượng event, dung lượng recording và chính sách lưu trữ.

**Nguyên tắc cốt lõi:** `enabled` trả lời *có ghi loại event này không?*; `threshold` trả lời *event duration bao lâu mới được giữ?*; `period` trả lời *periodic event được phát/lấy mẫu theo nhịp nào?*; `stackTrace` trả lời *có kèm call stack để tìm vị trí code không?*. Cấu hình đúng chỉ có ý nghĩa khi được xác minh trên **recording thực tế** và đặt trong câu hỏi chẩn đoán cụ thể.

## Tài liệu tham khảo

- Oracle JDK 21 — [`jdk.jfr` package: Settings and configuration](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- Oracle JDK 21 — [`EventSettings` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html).
- Oracle JDK 21 — [`Recording` API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- Oracle JDK 21 — [`jfr` command: configure/print/summary](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- Oracle JDK 21 — [`jcmd` command: JFR.start/check/stop](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- Dev.java — [Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/jfr/configure/).
- Oracle JDK 21 — [Flight Recorder Configurations](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html).