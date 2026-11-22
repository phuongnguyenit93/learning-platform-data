# Threshold và lựa chọn độ chi tiết trong JFR API — Java 11+

## 1. Tổng quan: vì sao cần điều chỉnh lượng thông tin JFR ghi?

**Java Flight Recorder (JFR)** là hệ thống thu thập sự kiện (event) bên trong JVM và ứng dụng để điều tra hiệu năng, độ trễ, I/O, tranh chấp khóa, GC, CPU và những diễn biến khó tái hiện. API Java chuẩn nằm trong module `jdk.jfr`; khả năng này có mặt trên **Java 11** và tiếp tục được hỗ trợ trên các phiên bản JDK hiện đại.

Một vấn đề thường gặp là: bật recording không có nghĩa JFR sẽ lưu **mọi sự kiện**, **mọi stack trace** hoặc **mọi lần lấy mẫu** ở mức chi tiết tối đa. Việc ghi quá nhiều sự kiện có thể làm tăng dung lượng, chi phí xử lý và cả lượng dữ liệu nhạy cảm trong file `.jfr`. Ngược lại, lọc quá mạnh có thể làm biến mất bằng chứng của một lỗi ngắn nhưng quan trọng.

Các nút điều chỉnh trọng tâm:

1. **`enabled`:** loại sự kiện nào được bật để thu thập.
2. **`threshold`:** thời lượng tối thiểu của một **duration event** để nó được ghi.
3. **`stackTrace`:** có ghi vết ngăn xếp tại thời điểm event được commit hay không.
4. **`period`:** khoảng thời gian phát sự kiện **tuần hoàn** (*periodic event*) nếu event đó có setting period.
5. **Cấu hình `default`/`profile`**, lọc theo loại event, số trường dữ liệu và thời gian recording: phối hợp các nút trên thành một mức chi tiết có ý nghĩa.

**Phân biệt quan trọng:** `threshold` **không phải tần suất sampling**. Nó là **ngưỡng thời lượng**: sự kiện có duration dưới ngưỡng sẽ không được ghi. `period` mới là tham số liên quan đến khoảng phát sự kiện định kỳ. `maxAge`/`maxSize` lại quản lý **dữ liệu đã giữ trong repository**, không thay thế hai setting nói trên.

### Mục tiêu bài học

- Giải thích đúng ý nghĩa của `@Threshold("25 ms")` và `EventSettings.withThreshold(Duration)`.
- Biết khi nào dùng `withoutThreshold()` và hiểu tại sao nó tăng độ chi tiết nhưng có thể tăng overhead.
- Điều khiển stack trace, sự kiện được bật, và chu kỳ cho periodic events.
- Dùng `Event.isEnabled()`, `begin()`, `end()`, `shouldCommit()` và `commit()` đúng mục đích.
- Đọc thông tin từ `EventType`, `Recording.getSettings()` và file JFR bằng `RecordingFile`.
- Chạy một chương trình Java 11 thực tế để so sánh mức **lọc mạnh**, **tổng quan không stack**, và **chi tiết có stack**.
- Xây chính sách thay đổi ngưỡng có kiểm soát khi xử lý sự cố production.

## 2. Nguyên lý threshold cho duration event

Giả sử một loại event theo dõi hoạt động I/O, tranh chấp monitor hoặc một nghiệp vụ do ứng dụng định nghĩa. Mỗi event có thể có **thời điểm bắt đầu** và **thời điểm kết thúc**:

```text
Event A: begin ---------------- end     duration  =  5 ms
Event B: begin -------------------------------- end = 25 ms
Event C: begin ------------------------------------------------- end = 60 ms

Threshold = 20 ms
  A -> KHÔNG ghi (dưới ngưỡng)
  B -> ghi (đủ ngưỡng)
  C -> ghi (trên ngưỡng)
```

Với `threshold=20 ms`, hệ thống chỉ hướng tới các operation có duration **ít nhất 20 ms**. Đây là cách tập trung vào **outlier** thay vì mọi thao tác rất ngắn.

### 2.1. Quy tắc so sánh

Theo API, threshold là thời lượng **dưới đó event không được ghi**. Với một duration event đã bật:

- Duration **nhỏ hơn** threshold: bị lọc.
- Duration **bằng hoặc lớn hơn** threshold: vượt qua điều kiện thời gian; event vẫn phải thỏa các điều kiện ghi khác.
- Threshold **0**: không có giới hạn thời lượng; ngay cả instant event có duration gần bằng 0 cũng có thể được ghi.
- Event bị **disable**: threshold bằng 0 cũng **không** tự bật event.
- Repository/memory retention và cơ chế JFR có thể giới hạn dữ liệu tồn tại trong file; **vượt threshold không bảo đảm event sẽ được giữ vô thời hạn**.

Đây là quy tắc **lọc theo sự kiện**, không phải thời gian chạy recording. Một recording dài 5 phút có thể dùng threshold 20 ms cho `jdk.SocketRead`; hai cấu hình không mâu thuẫn vì đo hai đối tượng khác nhau.

### 2.2. Threshold không phải timer, timeout hay latency SLA

`threshold=20 ms` không có nghĩa Java tự:

- Hủy I/O hoặc task chậm hơn 20 ms.
- Ném `TimeoutException` khi duration vượt ngưỡng.
- Ngăn thread chờ khóa.
- Làm một hàm ứng dụng chạy chậm hơn/nhiều lần hơn.
- Đảm bảo đo được percentile p95/p99 ngay từ các sự kiện đã lọc.

Nó chỉ quyết định mức độ **quan sát và giữ lại event**. Muốn áp đặt timeout, cần dùng API timeout/đồng bộ hóa của chính nghiệp vụ; muốn thống kê latency chính xác, cần xem xét sai lệch do event filtering và sampling.

### 2.3. Đừng mặc định mọi event có ngưỡng 20 ms

Một số template JFR cấu hình threshold cho các loại event liên quan I/O hoặc monitor contention, và các tài liệu hướng dẫn thường nhắc tới mức **20 ms** cho một số loại event. Nhưng **đó không phải mặc định toàn cục của mọi JDK/event**.

Ở cấp event setting, mặc định tổng quát của `threshold` có thể là `0`, hoặc được thay bởi:

- Annotation `@Threshold` trên event type.
- Cấu hình `.jfc` được chọn (`default`, `profile` hoặc file tùy chỉnh).
- Lời gọi `EventSettings.withThreshold(...)`, `withoutThreshold()` hoặc `with("threshold", "...")`.
- Cấu hình từ công cụ chẩn đoán/JFR runtime, tùy JDK và thời điểm.

**Hãy xác nhận event type và cấu hình thực tế trên JVM**, không đưa “20 ms cho mọi thứ” vào quy tắc ứng dụng.

## 3. Đặt ngưỡng mặc định bằng @Threshold trên custom event

Khi tạo event riêng trong ứng dụng, Java 11 có annotation `jdk.jfr.Threshold`:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Threshold;

@Name("demo.TimedOperation")
@Threshold("25 ms")
public class TimedOperation extends Event {
    public String operation;
}
```

Đây là **mảnh mã minh họa event type**. Annotation `@Threshold("25 ms")` đặt **giá trị mặc định** cho event: nếu có hoạt động đo duration, những sự kiện kết thúc nhanh hơn 25 ms không được ghi theo threshold đó, **trừ khi recording đang áp dụng một setting khác**.

Chuỗi setting dùng định dạng duration của JFR:

```text
"0 ns"
"10 ms"
"1 s"
"2 m"
"1 h"
```

Đây là ví dụ các giá trị hợp lệ; các đơn vị được JDK hỗ trợ gồm `ns`, `us`, `ms`, `s`, `m`, `h`, `d`. Với API `EventSettings.withThreshold(Duration)`, truyền đối tượng `java.time.Duration` sẽ rõ kiểu hơn việc tự ghép chuỗi.

**Đừng nhầm `@Threshold` với `@Timespan`.** `@Threshold` là annotation **trên event type** để đặt ngưỡng lọc; `@Timespan` thường mô tả một **trường dữ liệu** mang giá trị thời lượng. Trường `long elapsedNanos` tự đặt trong event **không thay thế** phần timing được JFR ghi khi gọi `begin()/end()`.

### 3.1. Annotation là mặc định, không khóa cứng recording

Nếu event được khai báo:

```java
@Threshold("25 ms")
class SlowTaskEvent extends Event {
}
```

thì recording có thể ghi đè bằng:

```java
recording.enable(SlowTaskEvent.class)
        .withThreshold(Duration.ofMillis(5));
```

Như vậy cùng một event type có thể được thu chi tiết hơn hoặc ít hơn theo mục đích quan sát. **Không cần sửa source hoặc deploy lại event class chỉ để thay threshold** khi có quyền cấu hình recording.

Mảnh `SlowTaskEvent`/`recording` trong phần này chỉ là cú pháp minh họa, không phải chương trình hoàn chỉnh. Chương trình đầy đủ ở mục 9 dùng `TimedOperation` và kiểm chứng ba cấu hình.

## 4. Thiết lập threshold bằng Recording.enable và EventSettings

Đối với Java 11, API thông dụng:

```java
import java.time.Duration;
import jdk.jfr.Recording;

try (Recording recording = new Recording()) {
    recording.enable("jdk.FileWrite")
            .withThreshold(Duration.ofMillis(10))
            .withoutStackTrace();

    recording.start();
    // Phát sinh thao tác cần quan sát.
    recording.stop();
}
```

Đây là **mảnh mã cấu hình**, chưa xuất file vì không có `dump(Path)` hay `setDestination(Path)`. `jdk.FileWrite` là event loại I/O do JDK cung cấp trên các runtime hỗ trợ. Event setting được gán cho một **recording**, không phải một biến toàn cục vĩnh viễn của JVM.

### 4.1. Những cách đặt ngưỡng phổ biến

| API | Ý nghĩa thực tế |
| --- | --- |
| `withThreshold(Duration.ofMillis(20))` | Chỉ quan tâm event có duration ít nhất 20 ms |
| `withThreshold(Duration.ofSeconds(1))` | Chỉ giữ những operation rất chậm, từ một giây |
| `withThreshold(Duration.ZERO)` | Không lọc theo thời lượng |
| `withoutThreshold()` | Cách viết rõ nghĩa của việc không dùng threshold, tương đương setting `"0 s"` |
| `with("threshold", "5 ms")` | Đặt setting bằng tên và chuỗi giá trị khi cần thao tác generic |
| `enable(EventClass.class)` | Bật một event class cụ thể để thiết lập tiếp |
| `disable(EventClass.class)` | Tắt event type đó trong recording; **khác** với nâng threshold |

Các method `withThreshold`, `withoutThreshold`, `withStackTrace` và `withoutStackTrace` trả `EventSettings` để gọi nối tiếp.

### 4.2. Nhận biết setting không hợp lệ hoặc không áp dụng

Không phải mọi event đều có cùng tập setting. Ví dụ:

- **Duration event** thích hợp cho `threshold`.
- **Periodic event** thích hợp cho `period`.
- **Instant event** có duration gần 0; threshold dương có thể khiến nó bị lọc toàn bộ.
- Một số event runtime có ràng buộc riêng; tên và ý nghĩa setting cần kiểm tra metadata trước khi áp dụng.

Việc method `with("threshold", value)` có thể lưu một cặp tên/giá trị trong recording **không bảo đảm event type đó có setting tương ứng hoặc setting có tác dụng như người dùng nghĩ**. Khi cấu hình theo tên, lấy danh sách setting từ `EventType.getSettingDescriptors()`.

### 4.3. Bật event khác với bỏ threshold

Xem hai dòng:

```java
recording.disable(TimedOperation.class);
recording.enable(TimedOperation.class).withoutThreshold();
```

Dòng một **tắt** event. Dòng hai vừa **bật** event vừa **bỏ lọc duration**. Không có khái niệm “withoutThreshold có nghĩa là không thu event”.

Khi cần giảm overhead, thường hiệu quả hơn nếu **tắt một event không phục vụ mục tiêu phân tích** thay vì giữ nó bật nhưng thu tất cả; nếu cần một ít bằng chứng về outlier thì bật event với threshold phù hợp.

## 5. Lifecycle của một duration event: begin, end, shouldCommit, commit

`jdk.jfr.Event` có các phương thức:

```java
TimedOperation event = new TimedOperation();
event.operation = "load-customer";
event.begin();

// Code nghiệp vụ cần đo nằm ở đây.

event.end();
if (event.shouldCommit()) {
    event.commit();
}
```

Đoạn trên là mảnh code, giả định `TimedOperation` là event type được khai báo và đang có recording hoạt động.

- `begin()` đánh dấu **bắt đầu** thời gian event.
- `end()` đánh dấu **kết thúc**. Nếu không gọi `end()` mà gọi `commit()`, API có thể tự kết thúc tại thời điểm commit.
- `shouldCommit()` cho biết event đang enabled và duration có đáp ứng threshold hay không ở runtime.
- `commit()` gửi sự kiện tới Flight Recorder; JFR tiếp tục áp dụng các điều kiện thu thập/retention của recording.

### 5.1. Vì sao gọi isEnabled() trước công việc tốn chi phí?

Trong custom event có payload xây dựng đắt tiền:

```java
TimedOperation event = new TimedOperation();
if (event.isEnabled()) {
    event.begin();
    performBusinessOperation();
    event.end();
    if (event.shouldCommit()) {
        event.operation = describeOperationSafely();
        event.commit();
    }
} else {
    performBusinessOperation();
}
```

Đây là **mảnh mã minh họa**; các hàm `performBusinessOperation` và `describeOperationSafely` do ứng dụng định nghĩa. Mục đích là chỉ tạo mô tả bổ sung khi event thật sự đáng ghi, tránh ghép chuỗi/stack trace/payload tốn kém cho những event đã bị lọc.

**Không nên viết business operation hai lần hoặc thay đổi hành vi nghiệp vụ theo event setting.** Trong code thật, ưu tiên cấu trúc không lặp logic (ví dụ method bọc instrumentation, `try/finally` để `end()` khi có exception).

### 5.2. isEnabled và shouldCommit không giống nhau

| Phương thức | Câu hỏi trả lời |
| --- | --- |
| `event.isEnabled()` | Có recording đang chạy mà event type này được bật hay không? |
| `event.shouldCommit()` | Event đã enabled và duration của event có đủ threshold để commit hay không? |

`isEnabled() == true` **không** đồng nghĩa event chắc chắn vượt threshold. Một operation chỉ mất 2 ms có thể enabled, nhưng `shouldCommit() == false` nếu threshold 20 ms.

`shouldCommit()` hữu ích để tránh xây dựng payload không cần thiết **sau khi operation hoàn tất**. Tuy nhiên, đây không phải “bảo đảm event sẽ nằm mãi trong `.jfr`”: event vẫn có thể mất do giới hạn lưu trữ, điều kiện vòng đời hoặc các yếu tố vận hành khác.

### 5.3. Nếu có nhiều recordings đồng thời?

Điểm dễ nhầm trên Java 11: `Event.shouldCommit()` xét ngưỡng nhỏ nhất trong các recording **đang chạy** cho event type đó. Ví dụ một recording cần threshold 50 ms, một recording khác cần threshold 0 ms, thì cơ chế phát event phải hỗ trợ nhu cầu chi tiết hơn.

Vì vậy:

- Đừng lấy `shouldCommit() == true` làm bằng chứng mọi recording đều sẽ có event đó.
- Một recording “chi tiết” cùng JVM có thể làm tăng công việc thu thập ngay cả khi một recording khác đã cấu hình ít dữ liệu.
- Không dùng `isEnabled()` hoặc `shouldCommit()` làm cơ chế phân quyền để quyết định có được thực hiện nghiệp vụ hay không.
- Nếu cần phép so sánh overhead rõ ràng giữa các cấu hình, hãy thử **tuần tự** các recording, tránh một recording thứ hai làm thay đổi kết quả quan sát.

Chương trình kiểm thử mục 9 áp dụng đúng nguyên tắc này: tạo và đóng từng recording trước khi chạy trường hợp tiếp theo.

## 6. Chọn mức chi tiết: bật loại event, stack trace, period và payload

Threshold chỉ là **một nút điều chỉnh**. Mức chi tiết thực tế còn phụ thuộc vào **sự kiện được bật** và **metadata được ghi**.

| Nút điều chỉnh | Giảm độ chi tiết | Tăng độ chi tiết | Tác động/rủi ro |
| --- | --- | --- | --- |
| **enabled** | Tắt event không liên quan | Bật event phục vụ giả thuyết lỗi | Thu thêm event có thể tăng overhead |
| **threshold** | Tăng, ví dụ 100 ms | Giảm xuống 5 ms hoặc 0 | Ngưỡng thấp tạo nhiều duration events |
| **stackTrace** | `withoutStackTrace()` | `withStackTrace()` | Stack giúp tìm call site nhưng tốn metadata, có thể lộ tên class/method |
| **period** (periodic) | Lấy thưa hơn, ví dụ 5 s | Lấy thường hơn, ví dụ 100 ms | Lượng event định kỳ tăng; không áp dụng cho mọi type |
| **loại cấu hình** | `default` | `profile` hay cấu hình điều tra tùy chỉnh | Khác nhau theo JDK; cần đo overhead |
| **custom fields** | Ghi ít metadata thiết yếu | Thêm khóa liên kết/ngữ cảnh phù hợp | Payload lớn và dữ liệu nhạy cảm tăng |
| **duration recording** | Cửa sổ ngắn | Cửa sổ dài | Tăng dữ liệu/thời gian lưu, không tự đổi threshold |

**Lựa chọn độ chi tiết không có nghĩa “bật tất cả setting ở giá trị cao nhất”.** Nên khởi đầu từ **câu hỏi chẩn đoán**: đang muốn tìm I/O chậm, khóa bị contention, phương thức tốn CPU hay giao dịch thất bại? Sau đó bật những loại event và mức chi tiết đủ trả lời câu hỏi đó.

### 6.1. Stack trace: nơi event được commit, không phải cả lịch sử request

`EventSettings.withStackTrace()` bật stack trace của event. Trong Java 11 Javadoc, dữ liệu stack trace được thu **từ thời điểm `Event.commit()`**, nên đối với custom event, nó mô tả stack khi event được ghi, không có nghĩa JFR tự lưu mọi stack đã đi qua giữa `begin()` và `end()`.

```java
recording.enable(TimedOperation.class)
        .withoutThreshold()
        .withStackTrace();
```

Nếu muốn giảm dữ liệu:

```java
recording.enable(TimedOperation.class)
        .withThreshold(Duration.ofMillis(20))
        .withoutStackTrace();
```

`RecordedEvent.getStackTrace()` trả `null` nếu event **không có stack trace**. Trong một số ngữ cảnh, stack trace có thể bị giới hạn bởi cấu hình độ sâu hoặc tình trạng runtime, vì vậy đừng xây code giả định nó luôn tồn tại chỉ vì setting là `true`.

**Trade-off:** stack trace giúp xác định đường dẫn code gây latency, nhưng có thể tăng bytes/event và chi phí khi tần suất event cao. Với số lượng hàng triệu event nhỏ, cân nhắc lọc theo duration trước, chỉ bật stack trace trong một khoảng điều tra ngắn.

### 6.2. Period chỉ dành cho periodic events

Ví dụ Java 11 trên một sự kiện định kỳ của JDK:

```java
recording.enable("jdk.CPULoad")
        .withPeriod(Duration.ofSeconds(1));
```

`period=1s` nhằm yêu cầu khoảng phát định kỳ của `jdk.CPULoad`. Nó **không** có nghĩa “chỉ ghi duration event chạy hơn một giây”, và `withPeriod` **không làm một custom TimedOperation được phát tự động mỗi giây**.

Muốn custom periodic event, phải định nghĩa và đăng ký theo cơ chế **periodic event** của JFR (ví dụ `FlightRecorder.addPeriodicEvent` cùng metadata phù hợp), hoặc dùng event JDK đã có. Không gắn `withPeriod` một cách máy móc cho mọi event type.

### 6.3. Threshold khác với sampling

Một cơ chế sampling chỉ quan sát **một tập con các thời điểm hoặc các sự kiện** theo chu kỳ/tần suất được cấu hình. Threshold của duration event thì xét **thời lượng của từng lần phát sinh** khi event type được bật.

Ví dụ:

- `jdk.CPULoad`: periodic measurement, điều khiển bằng `period` khi event có setting đó.
- `jdk.SocketRead`: duration event, thường quan tâm những lần đọc socket mất nhiều thời gian; threshold lọc độ trễ.
- `jdk.JavaMonitorEnter`: duration event có thể dùng để điều tra lock contention.
- `demo.TimedOperation`: event tự viết với begin/end, threshold lọc thao tác ngắn.

Chọn cấu hình theo **tên event và các settings hiện có trên đúng JDK**, không coi cách cấu hình một event JDK là quy tắc mặc định cho tất cả event types.

### 6.4. Không sử dụng custom fields như nơi lưu log không giới hạn

Các trường `String`, `long`, identifier hoặc nhãn có ích khi phân tích, nhưng:

- Tránh ghi mật khẩu, token, nội dung PII hoặc SQL đầy đủ chứa dữ liệu nhạy cảm.
- Không đưa payload hàng megabyte vào event field để thay cho logging/storage.
- Tránh biến động cardinality quá lớn nếu mục tiêu chỉ cần histogram hoặc nhóm operation.
- Nếu chi phí xây chuỗi metadata cao, dùng `isEnabled()`/`shouldCommit()` để lược bỏ việc tạo trường không cần thiết.
- Lưu ý stack trace cũng có thể tiết lộ tên package, class, method và đường dẫn nội bộ.

## 7. Đọc và chỉnh EventSettings, EventType, Recording settings

### 7.1. EventType cho biết event nào có setting nào

```java
import jdk.jfr.EventType;
import jdk.jfr.SettingDescriptor;

EventType type = EventType.getEventType(TimedOperation.class);
for (SettingDescriptor setting : type.getSettingDescriptors()) {
    System.out.println(setting.getName() + " = "
            + setting.getDefaultValue());
}
```

Đây là **mảnh mã**, cần class `TimedOperation` đã khai báo. `getSettingDescriptors()` giúp xem các setting như `enabled`, `threshold` và `stackTrace` có thực sự tồn tại cho event type hay không. Danh sách có thể khác theo event/JDK/provider. Không giả định thứ tự in ra cố định hoặc tất cả event có `period`.

`EventType.getEventType(Class)` có trong Java 11, tương tự `EventType.getName()` và `getId()`. Nếu hai custom event có cùng tên do các classloaders khác nhau, name-based configuration có thể ảnh hưởng nhiều event; chọn `Recording.enable(Class)` hoặc ID tùy yêu cầu để phân biệt.

### 7.2. Cú pháp tên setting trong cấu hình dạng Map

Tên setting theo Java 11 là:

```text
<event-name>#<setting-name>
```

Ví dụ:

```text
demo.TimedOperation#enabled    = true
demo.TimedOperation#threshold  = 25 ms
demo.TimedOperation#stackTrace = false
jdk.CPULoad#period              = 1 s
```

Đây là ví dụ **các cặp tên/giá trị**, không phải tuyên bố tất cả chúng được bật cùng lúc trên một JVM. `enabled`, `threshold`, `stackTrace` và `period` là tên setting đã được định nghĩa trong package `jdk.jfr`; việc áp dụng cần đúng event type.

Có thể cấu hình có chủ đích từ Java:

```java
import java.util.HashMap;
import java.util.Map;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

try (Recording recording = new Recording(
        Configuration.getConfiguration("default"))) {

    Map<String, String> settings =
            new HashMap<>(recording.getSettings());

    settings.put("jdk.SocketRead#threshold", "5 ms");
    settings.put("jdk.SocketRead#stackTrace", "true");
    recording.setSettings(settings);

    recording.start();
    // Chạy workload cần điều tra, rồi stop/dump trước khi close.
}
```

Đây là **mảnh code minh họa**, chưa có dump nên không tạo file. Chỉ áp dụng tên setting sau khi kiểm tra event phù hợp trên runtime. Quan trọng:

**`Recording.setSettings(Map)` thay thế TOÀN BỘ settings của recording**, không phải tự merge. Nếu có template `default` hay `profile`, nên copy `recording.getSettings()` rồi bổ sung những cặp cần sửa như ví dụ, thay vì truyền Map có hai mục rồi vô tình bỏ tất cả event settings khác.

**Sửa Map trả về từ `getSettings()` không tự cấu hình lại Recording**; phải gọi `setSettings(...)`. Nếu không cần thay toàn bộ cấu hình, dùng `recording.enable("jdk.SocketRead").withThreshold(...)` thường đơn giản, rõ ràng và ít nguy cơ nhầm.

### 7.3. Cấu hình trước start

`Recording` cho phép thay settings trong vòng đời phù hợp; tuy nhiên Javadoc khuyến nghị cấu hình **trước `recording.start()`** để các settings có thể được áp dụng nhất quán và hiệu quả hơn.

Nếu thay settings khi recording đang chạy, các event sát thời điểm đổi cấu hình có thể khác mức chi tiết. Không dùng một vài events ở ranh giới chuyển đổi để kết luận chính xác timing của từng thiết lập trên mọi JVM.

## 8. Quy trình chọn mức chi tiết trong thực tế

### 8.1. Mức 1 — quan sát thường xuyên, ít overhead

Phù hợp khi chưa có sự cố hoặc cần giữ dữ liệu liên tục trong production:

- Dùng `Configuration.getConfiguration("default")` nếu JDK cung cấp profile tương ứng.
- Chỉ bật event và fields phục vụ chẩn đoán thường xuyên.
- Giữ threshold đủ cao với các event tần suất lớn nhưng hiếm khi chậm.
- Tắt stack trace cho những event không cần tìm đường gọi cụ thể.
- Với periodic event, chọn chu kỳ phù hợp thay vì lấy mẫu quá dày.
- Giới hạn thời gian/dữ liệu lưu trong repository và kiểm tra overhead dưới tải thật.

Không áp dụng mù quáng “20 ms cho mọi event” hoặc “tắt stack trace hết” vì loại sự kiện quan trọng có thể bị mất khả năng điều tra.

### 8.2. Mức 2 — khoanh vùng event đáng nghi

Khi thấy các request có p99 latency cao hoặc I/O chậm:

- Chỉ tập trung loại event liên quan, ví dụ `jdk.SocketRead`, `jdk.FileRead`, `jdk.JavaMonitorEnter` khi có trong runtime.
- Giảm threshold có kiểm soát, ví dụ từ 20 ms xuống 5 ms để xem những thao tác ngắn hơn.
- Có thể bật stack trace cho **đúng event type** để tìm call site.
- Giữ recording đủ dài để tái hiện vấn đề, nhưng không tăng vô hạn volume.
- Kiểm tra số event, kích thước file và ảnh hưởng tới CPU/latency.

### 8.3. Mức 3 — điều tra sâu, ngắn hạn

Phù hợp khi đã xác định cửa sổ sự cố hẹp:

- Dùng `profile` hoặc cấu hình chuyên biệt đã được review.
- Giảm threshold về 0 **chỉ với những event cần điều tra**, không tự bật toàn bộ.
- Bật stack trace khi biết cần tìm nơi phát sự kiện.
- Có thể giảm period cho những periodic events liên quan.
- Chạy trong khoảng ngắn với giới hạn dung lượng, quyền lưu file và cơ chế dừng rõ ràng.
- Sau khi lấy snapshot, khôi phục cấu hình nhẹ hơn.

**Mức chi tiết cao hơn không luôn cho kết luận tốt hơn**: dữ liệu quá nhiều có thể che khuất tín hiệu, tăng chi phí ghi, khó lọc, và tạo ảnh hưởng lên workload. Cần đặt giả thuyết trước khi tăng độ chi tiết.

### 8.4. Cấu hình default và profile không giống "ngưỡng chung"

Java 11 cung cấp cấu hình JFR mặc định và profile trong JDK. Các cấu hình này xác định **nhiều event settings riêng theo loại event**, không chỉ một threshold toàn cục.

```java
Configuration defaultConfig =
        Configuration.getConfiguration("default");
Configuration profileConfig =
        Configuration.getConfiguration("profile");
```

Đây là mảnh mã, cần import `jdk.jfr.Configuration` và xử lý ngoại lệ thích hợp. **Tập event và giá trị chi tiết thay đổi theo JDK/update/vendor**. Đừng hardcode rằng mọi JDK 11/17/25 có đúng một tập `jdk.*` events hoặc threshold giống hệt.

Muốn kiểm tra thay vì đoán, đọc `Configuration.getSettings()` hoặc các `EventType.getSettingDescriptors()` trên runtime thật.

## 9. Chương trình Java 11 kiểm thử threshold và ba mức chi tiết

Ví dụ sau **chạy độc lập** bằng Java 11 trở lên, không cần thư viện ngoài JDK và không truy cập Internet. Chương trình tạo một event tùy chỉnh có:

- `@Name("demo.TimedOperation")` để đặt tên type có thể lọc khi đọc file.
- `@Threshold("25 ms")` đặt **giá trị mặc định** cho type.
- `@StackTrace(true)` đặt **giá trị mặc định** cho stack trace.
- `operation` là field mô tả event.

Sau đó ghi ba recording **tuần tự**:

1. **filtered:** override threshold thành **1 giờ**; hai thao tác chỉ khoảng 0/80 ms nên không có custom event được ghi.
2. **summary:** gọi `withoutThreshold()` và `withoutStackTrace()`, ghi một thao tác tức thời, đọc thấy **một custom event không có stack trace**.
3. **detailed:** gọi `withoutThreshold()` và `withStackTrace()`, ghi thao tác ngắn và thao tác `sleep(80)`, đọc thấy **hai events và hai stack traces**, xác nhận thời lượng của thao tác chậm là dương.

**Giới hạn kiểm thử:** con số `80 ms` chỉ để dễ tạo một duration dương; chương trình **không cố chứng minh ranh giới lọc chính xác 25 ms** trong điều kiện scheduler biến động. Nó kiểm thử chắc chắn trường hợp ngưỡng rất cao và không có ngưỡng, đồng thời quan sát metadata và stack trace.

Tạo file **`JfrThresholdDetailDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.stream.Collectors;
import jdk.jfr.Event;
import jdk.jfr.EventType;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrThresholdDetailDemo {
    @Name("demo.TimedOperation")
    @Label("Timed Operation")
    @Threshold("25 ms")
    @StackTrace(true)
    public static class TimedOperation extends Event {
        @Label("Operation")
        public String operation;
    }

    private static void emit(String name, int waitMillis)
            throws Exception {
        TimedOperation event = new TimedOperation();
        if (!event.isEnabled()) return;

        event.operation = name;
        event.begin();
        if (waitMillis > 0) Thread.sleep(waitMillis);
        event.end();

        if (event.shouldCommit()) event.commit();
    }

    private static List<RecordedEvent> read(Path file)
            throws Exception {
        return RecordingFile.readAllEvents(file).stream()
                .filter(e -> e.getEventType().getName()
                        .equals("demo.TimedOperation"))
                .collect(Collectors.toList());
    }

    private static void check(boolean pass, String message) {
        if (!pass) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass output folder");
        }
        Path folder = Path.of(args[0]);
        Files.createDirectories(folder);
        Path filteredFile = folder.resolve("filtered.jfr");
        Path summaryFile = folder.resolve("summary.jfr");
        Path detailedFile = folder.resolve("detailed.jfr");

        String defaultThreshold =
                TimedOperation.class.getAnnotation(
                        Threshold.class).value();
        boolean settingAvailable =
                EventType.getEventType(TimedOperation.class)
                        .getSettingDescriptors().stream()
                        .anyMatch(s -> s.getName().equals("threshold"));

        check(defaultThreshold.equals("25 ms")
                        && settingAvailable,
                "Event metadata not registered");
        System.out.println("annotation threshold = "
                + defaultThreshold);
        System.out.println("threshold setting available = "
                + settingAvailable);

        try (Recording r = new Recording()) {
            r.setName("filtered");
            r.setToDisk(true);
            r.enable(TimedOperation.class)
                    .withThreshold(Duration.ofHours(1))
                    .withoutStackTrace();

            r.start();
            emit("quick", 0);
            emit("slow", 80);
            r.stop();
            r.dump(filteredFile);
        }

        List<RecordedEvent> filtered = read(filteredFile);
        check(filtered.isEmpty(),
                "Hour-long threshold should filter events");
        System.out.println("filtered events = "
                + filtered.size());

        try (Recording r = new Recording()) {
            r.setName("summary");
            r.setToDisk(true);
            r.enable(TimedOperation.class)
                    .withoutThreshold()
                    .withoutStackTrace();

            r.start();
            emit("summary", 0);
            r.stop();
            r.dump(summaryFile);
        }

        List<RecordedEvent> summary = read(summaryFile);
        check(summary.size() == 1
                        && summary.get(0).getStackTrace() == null,
                "Expected one event without stack trace");
        System.out.println("summary events = "
                + summary.size());
        System.out.println("summary has stack = "
                + (summary.get(0).getStackTrace() != null));

        try (Recording r = new Recording()) {
            r.setName("detailed");
            r.setToDisk(true);
            r.enable(TimedOperation.class)
                    .withoutThreshold()
                    .withStackTrace();

            r.start();
            emit("quick", 0);
            emit("slow", 80);
            r.stop();
            r.dump(detailedFile);
        }

        List<RecordedEvent> detail = read(detailedFile);
        long stacks = detail.stream()
                .filter(e -> e.getStackTrace() != null)
                .count();
        boolean positiveDuration = detail.stream()
                .anyMatch(e ->
                        e.getValue("operation").equals("slow")
                        && e.getDuration().toNanos() > 0);

        check(detail.size() == 2
                        && stacks == 2 && positiveDuration,
                "Detailed recording missing event/stack/duration");
        System.out.println("detailed events = "
                + detail.size());
        System.out.println("detailed stack traces = "
                + stacks);
        System.out.println("slow duration positive = "
                + positiveDuration);
        System.out.println("ALL CHECKS PASSED");
    }
}
```

**Cách chạy** bằng JDK 11 trở lên:

```bash
javac --release 11 JfrThresholdDetailDemo.java
java JfrThresholdDetailDemo .
```

Dấu `.` cuối truyền thư mục đầu ra hiện tại. Chương trình tạo **`filtered.jfr`**, **`summary.jfr`** và **`detailed.jfr`**. Hãy chạy trong **một thư mục test riêng có quyền ghi**, không phải repository mã nguồn chính; sau khi xem kết quả có thể xóa ba file test.

**Đầu ra thực tế đã kiểm chứng:**

```text
annotation threshold = 25 ms
threshold setting available = true
filtered events = 0
summary events = 1
summary has stack = false
detailed events = 2
detailed stack traces = 2
slow duration positive = true
ALL CHECKS PASSED
```

Chương trình đã được biên dịch bằng `javac --release 11` và chạy thành công trên JDK có JFR. Một lượt kiểm tra bổ sung bằng `jfr summary detailed.jfr` cũng cho thấy **2 sự kiện `demo.TimedOperation`**; thứ tự và số lượng **những event JDK khác** trong file có thể thay đổi.

### 9.1. Diễn giải kết quả

- **`annotation threshold = 25 ms`:** class annotation tồn tại và có đúng giá trị mặc định khai báo. Recording có thể override nó.
- **`threshold setting available = true`:** metadata `EventType.getSettingDescriptors()` công bố setting `threshold` cho custom type.
- **`filtered events = 0`:** một giờ là ngưỡng lớn hơn rất nhiều thời gian thực thi thử, nên hai custom events bị lọc.
- **`summary events = 1`:** `withoutThreshold()` cho phép ghi event ngắn, dù annotation mặc định là 25 ms.
- **`summary has stack = false`:** `withoutStackTrace()` đã loại stack trace của custom event trong file summary.
- **`detailed events = 2`:** `withoutThreshold()` thu cả quick và slow.
- **`detailed stack traces = 2`:** `withStackTrace()` đã tạo stack trace cho hai event trong môi trường test.
- **`slow duration positive = true`:** JFR ghi duration dương cho event có `begin`, `sleep` và `end`.
- **`ALL CHECKS PASSED`:** toàn bộ assertion thành công.

Mỗi recording **dùng `setToDisk(true)`**, `stop()` rồi `dump(Path)` trước khi `close()`. Không nhầm việc **đã commit** với việc file đã được ghi: cần stop/dump và kiểm tra file thực tế.

### 9.2. Những gì không nên suy ra từ bài test

- Không khẳng định threshold **25 ms** đã được kiểm thử tại boundary; chỉ kiểm tra annotation, threshold 1 giờ và không threshold.
- Không khẳng định stack trace luôn có mọi frame tới tận gốc: có thể chịu giới hạn cấu hình và ảnh hưởng của runtime.
- Không đo overhead production bằng vài event trong một chương trình ngắn.
- Không khẳng định `RecordingFile.readAllEvents` thích hợp cho file `.jfr` khổng lồ; hàm đọc **toàn bộ event vào memory**, nên với file lớn dùng API streaming `RecordingFile`.
- Không coi thời lượng `80 ms` là thời gian thực thi chính xác từng nanosecond trên mọi hệ thống.
- Không giả định các sự kiện JDK khác trong file có cùng số lượng giữa các lần chạy.
- Không coi việc đặt ngưỡng thấp là bảo đảm không mất event khi repository bị giới hạn theo age/size hoặc process đột ngột dừng.

## 10. Kiểm tra file và kết quả bằng công cụ JFR

Sau khi có file demo:

```bash
jfr summary filtered.jfr
jfr summary summary.jfr
jfr summary detailed.jfr
jfr print --events demo.TimedOperation detailed.jfr
```

`jfr summary` hiển thị các event types cùng số lượng; `jfr print` in chi tiết event đã chọn (có thể gồm duration, thread, stack trace, fields). Với demo, bạn nên quan sát `demo.TimedOperation` có **0** trong filtered (có thể không xuất hiện trong thống kê), **1** trong summary và **2** trong detailed.

Mục tiêu khi so sánh:

- **Số event:** đã lọc đúng đối tượng quan tâm chưa?
- **Duration:** có sự kiện ngắn hay chậm như giả thuyết không?
- **Stack trace:** có xuất hiện khi bật, có cung cấp call site hữu ích không?
- **Dữ liệu trường:** label/operation có giúp liên hệ ngữ cảnh, hay chỉ tăng noise?
- **Kích thước file:** thay đổi ra sao khi bật stack trace/lower threshold?
- **Overhead:** CPU, throughput, latency thực tế có bị ảnh hưởng?

Không chia sẻ nguyên file `.jfr` ra ngoài nếu chứa tên class, stack traces, đường dẫn hay dữ liệu nhạy cảm chưa được kiểm tra.

### 10.1. Vì sao không lấy file size để chứng minh threshold đúng?

Trong file `.jfr` còn có metadata, chunk header và các sự kiện hệ thống của JVM. Bởi vậy:

```text
filtered.jfr có thể > 0 byte
ngay cả khi số demo.TimedOperation = 0.
```

Một file không rỗng **không chứng minh custom event vượt threshold**. Hãy lọc **đúng event type** bằng `RecordedEvent.getEventType().getName()` hoặc `jfr summary`.

### 10.2. Đọc duration và stack trace qua RecordingFile

Mảnh Java dùng trong xử lý file nhỏ:

```java
for (RecordedEvent event :
        RecordingFile.readAllEvents(Path.of("detailed.jfr"))) {
    if (event.getEventType().getName()
            .equals("demo.TimedOperation")) {
        Duration duration = event.getDuration();
        boolean hasStack = event.getStackTrace() != null;
        System.out.println(duration + " / " + hasStack);
    }
}
```

Đây là **mảnh code minh họa**, cần import `Duration`, `Path`, `RecordedEvent` và `RecordingFile`. Output duration thay đổi mỗi lần chạy, do đó không đưa ra dòng stdout cố định cho đoạn này. Với file lớn, dùng iterator của `RecordingFile` để xử lý tuần tự.

## 11. Chẩn đoán performance bằng cấu hình phù hợp

### 11.1. Ví dụ đọc socket chậm

Nếu bạn nghi ngờ network I/O làm tăng response time, cân nhắc recording với các event:

- `jdk.SocketRead`, `jdk.SocketWrite` nếu có trên runtime.
- `jdk.FileRead`/`jdk.FileWrite` nếu giả thuyết là I/O file.
- Các event monitor/park/thread thích hợp nếu nghi ngờ tranh chấp hoặc chờ.

Ban đầu chọn threshold vừa phải cho socket duration events, ví dụ `20 ms`, rồi giảm xuống `5 ms` trong một recording ngắn để kiểm tra nhiều lần đọc nhỏ có tạo ra tổng độ trễ đáng kể hay không. Bật stack trace khi cần xác định code nào thực hiện thao tác.

**Lưu ý:** chỉ dùng đúng tên setting/event mà JVM đó công bố. Không khẳng định mọi template bật sẵn tất cả các event này; `default` và `profile` có thể chọn khác nhau.

### 11.2. Ví dụ lock contention

Nếu ứng dụng có biến động latency do khóa Java:

- Bật loại event contention phù hợp, ví dụ `jdk.JavaMonitorEnter` trên runtime hỗ trợ.
- Chọn threshold hướng tới các lần block đủ dài để phân tích.
- Nếu cần biết nơi tranh chấp, bật stack trace cho loại event đó.
- Nếu ngưỡng 20 ms không cho thấy vấn đề nhưng log ứng dụng có dấu hiệu nhiều lần chờ ngắn, thử ngưỡng thấp hơn trong cửa sổ ngắn, đo overhead.

Không nhầm **“một lần chờ 50 ms”** với **“nhiều lần chờ 1 ms tạo thành 50 ms”**. Threshold 20 ms sẽ lọc bỏ các lần 1 ms riêng lẻ; nếu muốn thấy tổng tác động, cần hạ threshold hoặc dùng phương pháp đo khác.

### 11.3. CPU profiling không chỉ phụ thuộc threshold

Đối với CPU sampling, các event và setting như sample period quan trọng hơn threshold duration của I/O/monitor events. Tìm đúng event type trên JVM hiện tại, dùng cấu hình profile được JDK hỗ trợ và quan sát chi phí. Không áp dụng `withThreshold(20ms)` lên mọi CPU sample với kỳ vọng “lấy mẫu mỗi 20 ms”.

## 12. Dùng jcmd và cấu hình .jfc trên JVM đang chạy

Với JVM có JFR và quyền attach, có thể bắt đầu recording theo profile:

```bash
jcmd <PID> JFR.start name=Focused settings=profile duration=60s filename=focused.jfr
```

`<PID>` là **ký hiệu phải thay bằng process ID thật**, không được gõ nguyên dấu ngoặc vào shell. `settings=profile` là bộ setting mẫu có thể thu nhiều thông tin hơn so với default tùy JDK; `duration=60s` là **thời gian recording chạy**, không phải event threshold. `filename` quy định file được lưu khi dừng theo cách công cụ hỗ trợ.

Để xem các tham số và trạng thái thực tế:

```bash
jcmd <PID> help JFR.start
jcmd <PID> JFR.check
```

**Không coi dòng `JFR.start` trên là cách sửa threshold của mọi event đồng thời.** Để điều chỉnh threshold riêng lẻ trong recording vận hành, dùng:

- `Recording.enable(eventName).withThreshold(...)` từ Java API trong ứng dụng.
- File cấu hình `.jfc` có giá trị cho `eventName#threshold` hoặc cơ chế cấu hình JFR tương ứng với runtime.
- Công cụ JDK Mission Control/recording settings khi được phép sử dụng.
- Kiểm tra cuối cùng bằng `Recording.getSettings()` và kết quả file `.jfr`.

Không sửa trực tiếp tập tin template cài trong JDK nếu chưa có quy trình quản lý cấu hình; ưu tiên một bản cấu hình tùy chỉnh được version control và kiểm thử.

### 12.1. Period và threshold là hai nút độc lập trong .jfc

Trong một file cấu hình JFR, bạn có thể có các khái niệm:

```text
jdk.CPULoad#period = 1 s
jdk.SocketRead#threshold = 10 ms
jdk.SocketRead#stackTrace = true
```

Đây là **biểu diễn các cặp setting**, **không phải cú pháp XML hoàn chỉnh của file `.jfc`**. Để tạo `.jfc` thật, dùng công cụ/template phù hợp với JDK đích và cấu trúc XML được định nghĩa cho JFR configuration.

Trước khi áp dụng trên production, dùng file trong môi trường staging, kiểm tra loại event và overhead, nhất là khi giảm threshold hoặc tăng sampling frequency.

## 13. Lỗi thường gặp và cách giải quyết

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không có event dù đã start recording | Event chưa enabled hoặc không phát sinh trong cửa sổ | Kiểm tra `enable(...)`, `getSettings()`, thời gian recording |
| Event chậm bị mất | Threshold quá cao, hoặc repository loại dữ liệu | Hạ threshold khi có lý do, kiểm tra maxAge/maxSize |
| Bật event nhưng `isEnabled()` false | Chưa có recording đang chạy bật event đó | Kiểm tra `Recording.start()` và lifecycle |
| `shouldCommit()` false | Event disabled hoặc duration dưới threshold | Kiểm tra `end()` trước khi xét duration, cấu hình threshold |
| Muốn lấy nhiều event nhưng chỉ điều chỉnh `maxSize` | MaxSize là retention repository, không phải event filter | Thay `threshold` và `enabled` theo event type |
| `@Threshold("25 ms")` có vẻ không được áp dụng | Recording có setting override annotation | Kiểm tra `Recording.getSettings()` |
| Tưởng `withoutThreshold()` tắt event | Phương thức này bỏ lọc thời lượng, không disable | Dùng `Recording.disable(...)` khi muốn tắt |
| Stack trace luôn `null` | `withoutStackTrace()`, không có stack hoặc giới hạn runtime | Kiểm tra event setting và `RecordedEvent.getStackTrace()` |
| Không cần stack nhưng file quá lớn | StackTrace đang bật trên nhiều event tần suất cao | Tắt cho event không cần và hạ số lượng event |
| `withPeriod` không có tác dụng với custom event | Event không được đăng ký như periodic event | Xem metadata và cơ chế periodic event phù hợp |
| Cấu hình tên `jdk.*` không tồn tại | Khác JDK/version hoặc typo tên event | Dùng `FlightRecorder.getEventTypes()` và metadata |
| `setSettings` làm mất cấu hình template | Truyền Map mới, thay toàn bộ settings | Copy `recording.getSettings()`, merge rồi `setSettings` |
| Rất nhiều event ngắn gây overhead | Threshold thấp/0 hoặc quá nhiều event types | Giới hạn thời gian điều tra, nâng threshold có chọn lọc |
| p95/p99 suy ra không đúng từ JFR | Event filtering/sampling gây selection bias | Dùng đo latency đầy đủ theo thống kê ứng dụng phù hợp |
| File `.jfr` có dữ liệu nhưng không thấy custom event | File chứa JDK/metadata events, custom type không vượt filter | Lọc theo exact event type name khi đọc |
| `RecordingFile.readAllEvents` thiếu heap | File lớn nạp tất cả events vào List | Đọc tuần tự qua `RecordingFile` |
| Khó tái hiện trên JDK khác | Template, event settings, stack depth và policy thay đổi | Ghi rõ JDK/version/config và kiểm thử runtime |
| Quan sát một mức ghi quá nhiều dữ liệu nhạy cảm | Stack trace/custom fields chứa thông tin nội bộ | Giảm fields, quyền truy cập, redaction và retention |
| Hai recordings cùng chạy gây kết quả không như dự kiến | Global event emission chịu tác động nhiều settings | So sánh tuần tự, kiểm tra mỗi recording và runtime metadata |

## 14. Checklist triển khai có trách nhiệm

1. **Xác định câu hỏi chẩn đoán:** đang đo slow I/O, contention, CPU hay một custom business operation?
2. **Chọn event types đúng:** dùng metadata JFR runtime, không bật mọi event type theo thói quen.
3. **Đặt threshold rõ ý nghĩa:** giữ outliers hay cần mọi occurrence? Mức 0 không mặc định là lựa chọn an toàn cho production.
4. **Quyết định stack trace:** có cần nơi phát sinh không? Nếu không, `withoutStackTrace()` giúp giảm dữ liệu.
5. **Phân biệt periodic/sampling:** chỉ dùng `withPeriod` cho event phù hợp và đo chi phí theo tần suất.
6. **Dùng annotations cho default của custom type:** `@Threshold`/`@StackTrace`; recording có thể override theo mục đích.
7. **Đo đúng duration:** `begin()/end()` bao quanh thao tác cần quan sát; dùng `shouldCommit()` sau duration để tránh payload đắt tiền.
8. **Cấu hình trước `start()`** khi có thể để giữ nhất quán.
9. **Xem trạng thái khi nhiều recordings cùng chạy:** đừng giả định một config cao sẽ cô lập hoàn toàn tác động của recording chi tiết khác.
10. **Kiểm chứng sau khi lưu file:** dùng `RecordingFile` hoặc `jfr summary`, xem đúng event type/count/duration/stack.
11. **Kiểm tra overhead thực:** CPU, latency, throughput, kích thước file và chi phí xử lý analytics.
12. **Bảo vệ file `.jfr`:** phân quyền và retention, tránh ghi bí mật trong custom fields.
13. **Quay về cấu hình nhẹ sau điều tra:** tránh giữ threshold 0 hoặc period quá thấp vô thời hạn.
14. **Ghi nhận JDK vendor/version:** sự kiện và settings được JDK cung cấp có thể thay đổi qua bản cập nhật.

## 15. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** `@Threshold("25 ms")` làm gì?  
**Đáp án:** Đặt giá trị mặc định cho ngưỡng duration của custom event; recording có thể override. Event có duration dưới ngưỡng sẽ không được ghi nếu không có setting khác cho phép.

**Câu 2.** `withThreshold(Duration.ofMillis(20))` có khiến thao tác vượt 20 ms bị hủy không?  
**Đáp án:** Không. Nó chỉ điều chỉnh việc ghi event, không phải timeout của business operation.

**Câu 3.** `withoutThreshold()` có nghĩa là tắt event không?  
**Đáp án:** Không. Nó bỏ lọc theo duration, tương đương threshold bằng 0. Muốn tắt event dùng `Recording.disable(...)`.

**Câu 4.** `event.isEnabled()` khác `event.shouldCommit()` thế nào?  
**Đáp án:** `isEnabled()` hỏi event có được bật ở recording đang chạy hay không; `shouldCommit()` còn xét duration so với threshold.

**Câu 5.** Tại sao JFR chỉ ghi event có duration trên threshold mà vẫn thiếu một phần lịch sử?  
**Đáp án:** Threshold quyết định event có được thu, còn retention repository/đóng recording hoặc những điều kiện vận hành khác quyết định dữ liệu được giữ bao lâu.

**Câu 6.** `withStackTrace()` thu stack ở thời điểm nào đối với custom event?  
**Đáp án:** Stack trace của event gắn với thời điểm `Event.commit()`, không phải tự ghi toàn bộ call stack history từ begin đến end.

**Câu 7.** `withPeriod(Duration.ofSeconds(1))` có nghĩa lọc event chậm hơn 1 giây không?  
**Đáp án:** Không. Đó là chu kỳ phát event định kỳ nếu event có setting `period`; lọc duration dùng `threshold`.

**Câu 8.** Vì sao nên so sánh ba recording theo thứ tự thay vì chạy đồng thời?  
**Đáp án:** Với nhiều recordings, `shouldCommit()` xét threshold nhỏ nhất và cơ chế phát event có thể chịu ảnh hưởng cấu hình cùng lúc, nên thử tuần tự giúp phân lập kết quả hơn.

**Câu 9.** `Recording.setSettings(map)` có merge tự động với cấu hình hiện có không?  
**Đáp án:** Không. Nó thay thế toàn bộ settings; muốn merge phải đọc/copy Map hiện tại, bổ sung và gọi lại `setSettings`.

**Câu 10.** Nếu `RecordingFile.readAllEvents` cho ra nhiều sự kiện JDK, làm sao xác định có custom event?  
**Đáp án:** Lọc `event.getEventType().getName().equals("demo.TimedOperation")`. Không dựa vào file size hoặc tổng số event.

**Câu 11.** Muốn điều tra nhiều lần gọi hàm rất nhanh, nên tăng threshold hay giảm?  
**Đáp án:** Giảm threshold hoặc bỏ threshold trong recording ngắn, sau khi đánh giá overhead và chỉ với các event type cần thiết.

**Câu 12.** Làm sao tìm những setting có thể dùng cho một event type?  
**Đáp án:** Lấy `EventType.getEventType(EventClass.class).getSettingDescriptors()` với custom class, hoặc tìm event qua `FlightRecorder.getEventTypes()` rồi xem descriptors.

## 16. Tổng kết

```text
             JFR event type
                   |
              enabled = true?
                   |
          +--------+---------+
          |                  |
         NO                 YES
          |                  |
      Không ghi        Duration >= threshold?
                             |
                    +--------+--------+
                    |                 |
                   NO                YES
                    |                 |
                Không ghi        Ghi event
                                  |
                    +-------------+-------------+
                    |                           |
             stackTrace=false            stackTrace=true
               Ít metadata              Thêm stack trace
                                  |
                                  v
                   Dữ liệu vào JFR recording
                                  |
                                  v
                  Disk/memory retention, dump
```

- **`threshold`**: lọc các **duration events** theo thời gian thực thi. Hạ threshold → tăng độ chi tiết và thường tăng số event.
- **`enabled`**: quyết định có quan sát event type hay không.
- **`stackTrace`**: thêm ngữ cảnh call stack, hữu ích nhưng có chi phí.
- **`period`**: điều khiển periodic events, **không** phải threshold.
- **`@Threshold`** là mặc định của event type; **`EventSettings.withThreshold/withoutThreshold`** có thể override tại recording.
- **`isEnabled()`** và **`shouldCommit()`** không đồng nghĩa; `shouldCommit` có thể chịu tác động nhiều recordings đang chạy.
- **Tuning tốt** là chọn đúng event, đủ mức chi tiết để trả lời câu hỏi, đo overhead và xác minh file kết quả.

JFR API này **vẫn áp dụng từ Java 11 đến JDK hiện đại**. Khi vận hành, luôn tra metadata thực trên runtime đang sử dụng và kiểm soát dữ liệu nhạy cảm trong recording.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 11 — jdk.jfr.EventSettings: withThreshold, withoutThreshold, withStackTrace, withPeriod](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html)
- [Oracle Java SE 11 — jdk.jfr.Event: begin, end, isEnabled, shouldCommit, commit](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Oracle Java SE 11 — jdk.jfr.Threshold annotation](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Threshold.html)
- [Oracle Java SE 11 — jdk.jfr.StackTrace annotation](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/StackTrace.html)
- [Oracle Java SE 11 — jdk.jfr.Recording: enable/disable/getSettings/setSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle Java SE 11 — jdk.jfr.EventType và SettingDescriptor](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventType.html)
- [Oracle Java SE 11 — jdk.jfr package settings, threshold/period/stackTrace](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Oracle Java SE 11 — jdk.jfr.consumer.RecordedEvent.getDuration/getStackTrace](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html)
- [Oracle Java SE 11 — JFR performance troubleshooting và threshold](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [OpenJDK — JEP 328: Flight Recorder](https://openjdk.org/jeps/328)
- [Oracle Java SE 26 — EventSettings API còn được hỗ trợ](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/EventSettings.html)
