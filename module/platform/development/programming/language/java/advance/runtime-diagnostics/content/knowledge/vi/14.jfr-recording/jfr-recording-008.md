# 14.8 Hiểu dữ liệu có thể bị thiếu do chưa bật event, ngưỡng hoặc mất dữ liệu

## Mục tiêu

Một bản ghi Java Flight Recorder (JFR) **không có event bạn đang tìm** không chứng minh rằng sự kiện tương ứng chưa từng xảy ra. Giữa hành vi thực tế của ứng dụng và dữ liệu bạn đọc trong tệp `.jfr` có nhiều bước lựa chọn, lọc, ghi đệm, lưu trữ và trích xuất. Thiếu dữ liệu có thể hoàn toàn đúng với cấu hình, nhưng cũng có thể khiến điều tra đi đến kết luận sai.

Sau bài này, bạn có thể:

1. Giải thích tại sao event không xuất hiện do **chưa bật**, **không đạt ngưỡng**, **được lấy mẫu theo chu kỳ**, **không thuộc cửa sổ ghi**, hoặc **bị mất/không còn được giữ**.
2. Kiểm tra cấu hình đang chạy bằng `jcmd ... JFR.check verbose=true` và kiểm tra tệp bằng `jfr summary`, `jfr metadata`, `jfr print`.
3. Chọn event/threshold và độ dài recording phù hợp mục tiêu, rồi thu lại dữ liệu có khả năng trả lời câu hỏi.
4. Phân biệt “không thấy event”, “không có stack trace”, “không lưu toàn bộ lịch sử” và “mất dữ liệu khi ghi”.
5. Viết kết luận với mức tin cậy đúng: **không thấy dấu vết trong bản ghi này** khác với **chứng minh hệ thống không xảy ra sự cố**.

Bài dùng tên lệnh và API phù hợp JFR của **HotSpot/OpenJDK Java 17+**, tham chiếu cách dùng JDK 21. Tên event, tập event sẵn có và nội dung template `default`/`profile` cần được kiểm tra lại trên **chính JDK/phiên bản đang chạy**.

## 1. Dữ liệu JFR đi qua những “cửa” nào?

JFR ghi lại các **event** có tên/loại, mốc thời gian và các trường mô tả. Với event kéo dài, thường có thời lượng; một số event có thread hoặc stack trace. Tùy loại event, JVM hoặc ứng dụng phải thực sự phát sinh và commit event trước khi engine có dữ liệu để thu.

Đường đi khái niệm:

```text
Hành vi xảy ra trong JVM/ứng dụng
    |
    v
Có event type và cơ chế phát event tương ứng?
    |
    v
Event có được enable trong recording có liên quan?
    |
    v
Event có vượt các bộ lọc/threshold/period/sampling?
    |
    v
Event được ghi vào các buffer/chunk của JFR
    |
    v
Dữ liệu còn được giữ trong cửa sổ thời gian/dung lượng?
    |
    v
Dump/export đúng recording và đúng khoảng thời gian?
    |
    v
Công cụ phân tích có hiển thị đúng loại event/bộ lọc?
```

Ở **bất kỳ bước nào**, bạn đều có thể không thấy event ở đầu ra. Vì thế cần định vị chỗ thiếu trước khi tối ưu JVM hoặc sửa code.

| Hiện tượng quan sát | Cơ chế có thể xảy ra | Điều chưa thể kết luận |
| --- | --- | --- |
| Không có `jdk.JavaMonitorEnter` trong file | Event chưa enable, chưa có lock contention phù hợp, duration chưa đạt ngưỡng, hoặc sai cửa sổ | Không thể kết luận ứng dụng không hề dùng `synchronized` hoặc không có tranh chấp nào |
| Có event nhưng không có stack trace | `stackTrace=false`, stack không được thu ở thời điểm đó, hoặc cách hiển thị giới hạn stack | Không thể kết luận event không xảy ra |
| Có vài CPU/Execution Sample | Sampling thu mẫu định kỳ/xác suất, không phải nhật ký từng lần method chạy | Không thể đếm chính xác số lần gọi method từ số sample |
| File chỉ còn thời gian gần đây | `maxage`/`maxsize` đã loại phần cũ, `disk=false` chỉ giữ một cửa sổ trong bộ nhớ, hoặc dump bị giới hạn | Không thể kết luận thời gian trước đó không có sự cố |
| Số liệu có khoảng trống khi hệ thống quá tải | Buffer, ghi chunk, I/O, dừng đột ngột hoặc lỗi thu/đọc có thể làm thiếu dữ liệu | Không thể lấy “0 sự kiện” làm bằng chứng tuyệt đối |

## 2. Trường hợp 1 — Event chưa được bật

JFR có hai mẫu cấu hình đi kèm JDK: `default.jfc` ưu tiên overhead thấp và `profile.jfc` thu thêm một số dữ liệu để phân tích sâu. **Hai template này không bật mọi event**, và cấu hình thực tế có thể đã bị sửa hoặc được override khi khởi động recording.

Mỗi event type thường có các setting:

| Setting | Tác dụng |
| --- | --- |
| `enabled=true/false` | Có cho phép ghi event đó không |
| `threshold` | Với event có thời lượng, chỉ giữ event đạt điều kiện thời lượng |
| `period` | Với event periodic, tần suất yêu cầu phát event |
| `stackTrace=true/false` | Có yêu cầu thu stack trace kèm event không |

Ngoài các setting chung còn có tùy chọn đặc thù theo event/JDK, ví dụ chính sách sampling hoặc throttle. Không suy mọi event đều có `threshold` hoặc `period` hữu ích.

Đặc biệt, **event type xuất hiện trong `jfr metadata` không chứng minh một instance đã được ghi**. Metadata mô tả schema/loại event mà bản ghi biết; số instance thực tế phải đọc bằng thống kê và dữ liệu event.

### Kiểm tra recording đang hoạt động

Lấy PID của tiến trình Java thực tế:

```bash
jcmd -l
jcmd 12345 JFR.check
jcmd 12345 JFR.check name=diagnostics verbose=true
```

Thay `12345` bằng PID thực. `diagnostics` là tên recording **minh họa**; nếu không có recording đó, xem danh sách từ `JFR.check` và chọn đúng tên/ID đang chạy. Với `verbose=true`, HotSpot có thể in các setting event hiện tại của recording. Khi cần cú pháp đúng với bản JDK đang dùng:

```bash
jcmd 12345 help JFR.check
jcmd 12345 help JFR.start
```

Đối chiếu **loại event, đúng recording và đúng thời điểm**. Một recording có thể thay đổi setting trong quá trình chạy; `JFR.check` chỉ cho biết trạng thái tại lúc kiểm tra, không chứng minh toàn bộ khoảng lịch sử luôn dùng đúng setting ấy. Nếu recording đã dừng, cần lưu cấu hình `.jfc` và nhật ký lệnh đã dùng để thu.

### Tập trung vào một event đang thiếu

Ví dụ muốn quan sát thời gian thread thực sự phải chờ để **vào một Java monitor** thì `jdk.JavaMonitorEnter` có ý nghĩa. Chỉ cần code đi vào khối `synchronized` không đảm bảo phát sinh sự kiện này: phải có hành vi tương ứng, đặc biệt là cạnh tranh monitor thực tế.

Nếu mục tiêu là các lần chờ ngắn, hãy kiểm tra `jdk.JavaMonitorEnter#enabled` và `jdk.JavaMonitorEnter#threshold`. Không dùng việc thiếu event để chứng minh “không có lock contention” trước khi xác minh hai setting này.

## 3. Trường hợp 2 — Event có bật nhưng không đạt ngưỡng

`threshold` quy định **thời lượng dưới ngưỡng thì event duration không được ghi**. Ví dụ một cấu hình theo dõi tranh chấp monitor:

- `jdk.JavaMonitorEnter#enabled=true`
- `jdk.JavaMonitorEnter#threshold=20ms`

Giả sử trong một cửa sổ có bốn lần tranh chấp kéo dài 3 ms, 8 ms, 14 ms và 36 ms. Nếu các lần đó đều thuộc loại event này và không có cơ chế thiếu dữ liệu khác, các lần **dưới 20 ms** sẽ bị lọc; sự kiện 36 ms có thể xuất hiện. Dữ liệu chỉ còn phần đuôi chậm, không còn đại diện cho toàn bộ số lần tranh chấp.

| Hiện tượng thực | Cấu hình | Điều dự kiến trong file |
| --- | --- | --- |
| Tranh chấp kéo dài 8 ms | `threshold=20ms` | Không ghi event đó |
| Tranh chấp kéo dài 36 ms | `threshold=20ms` | Có thể ghi event tương ứng |
| Tranh chấp kéo dài 8 ms | `threshold=0ms` | Có thể ghi nếu event enable và các điều kiện khác đạt |
| Event đã được ghi nhưng `stackTrace=false` | Event enable | Event có thể hiện diện nhưng không có stack đi kèm |

Giảm threshold có thể tăng mạnh số lượng event và overhead. Mức `0ms` hữu ích để **tái hiện trong cửa sổ ngắn**, không nên bật tràn lan trên hệ thống tải lớn chỉ vì muốn “đủ mọi dữ liệu”. Ngoài ra, không thể thay threshold sau khi ghi rồi làm xuất hiện những event trước đó đã bị lọc: cần **thu recording mới**.

### Phân biệt threshold với period và sampling

- **Threshold** lọc theo duration trên các event phù hợp (ví dụ blocked I/O hoặc monitor contention).
- **Period** quy định chu kỳ phát cho event dạng thống kê/periodic, ví dụ `jdk.CPULoad`. Một mẫu mỗi giây không mô tả mọi biến động giữa hai giây.
- **Execution sampling** chỉ quan sát các stack tại những thời điểm lấy mẫu. Một method không xuất hiện trong sample không chứng minh method không từng chạy; số sample không bằng số invocation.
- **Stack trace setting** kiểm soát dữ liệu đi kèm, không phải việc event có xảy ra hay không.

Hai recording dùng period/threshold khác nhau **không nên so số event thô như thể độ bao phủ như nhau**. Ví dụ số lần `JavaMonitorEnter` giảm sau khi nâng threshold có thể chỉ vì thu ít hơn.

## 4. Trường hợp 3 — Dữ liệu bị mất hoặc không còn trong phần được lưu

Cần tách hai ý nghĩa thường bị gọi chung là “mất dữ liệu”.

### 4.1. Dữ liệu chưa từng được giữ đầy đủ khi ghi

JFR truyền dữ liệu qua buffer của từng thread và các buffer/chunk. Khi hoạt động rất mạnh hoặc tài nguyên ghi hạn chế, một số dữ liệu có thể không được lưu đầy đủ. JVM crash hoặc tắt bất thường cũng có thể khiến phần dữ liệu chưa kịp flush không nằm trong file.

Các dấu hiệu nên đối chiếu:

- Lưu lượng event tăng đột biến sau khi bật nhiều event chi tiết/ngưỡng rất thấp.
- Nhật ký JVM/JFR báo lỗi hoặc cảnh báo liên quan việc ghi recording, buffer, repository hoặc mất dữ liệu (cách thông báo phụ thuộc JDK).
- File không bao phủ đủ mốc thời gian đã quan sát, hoặc dữ liệu có khoảng trống bất thường.
- Công cụ đọc báo lỗi file/chunk hoặc recording bị cắt vì tiến trình kết thúc đột ngột.

**Không phải mọi bản JDK và mọi trường hợp đều đưa ra một event “data loss” dễ tìm trong file.** Không thấy chỉ dấu mất dữ liệu cũng không chứng minh 100% event đã được ghi đầy đủ. Khi nghi mất dữ liệu thực, cần đối chiếu log, file, khoảng thời gian, cấu hình recorder và chỉ số hệ thống. Không tự biến một khoảng thiếu trong biểu đồ thành số byte/event đã mất nếu chưa có nguồn đếm đáng tin.

### 4.2. Dữ liệu từng được ghi nhưng bị loại theo chính sách giữ

Recording dài hạn có thể được giữ dạng **cửa sổ trượt**. Khi vượt giới hạn `maxage` (tuổi dữ liệu) hoặc `maxsize` (dung lượng dữ liệu lưu), những chunk cũ có thể bị loại để giữ phần mới.

Với `disk=false`, recording không duy trì đầy đủ lịch sử trên disk repository như `disk=true`; buffer trong bộ nhớ có dung lượng hữu hạn và có thể chỉ giữ khoảng thời gian gần đây. Đây là **retention policy**, khác với việc event không enable hoặc bị mất do ghi đệm quá tải.

Ví dụ người vận hành muốn điều tra lỗi tại 10:00, nhưng đến 11:00 mới dump một recording chỉ giữ 20 phút gần nhất: file có thể hoàn toàn hợp lệ mà **không còn dữ liệu của 10:00**. Tăng `maxage` sau đó không phục hồi chunk đã bị loại.

Ngoài ra, lệnh `JFR.dump` có thể chọn khoảng thời gian và giới hạn dữ liệu xuất bằng `begin`, `end`, `maxage` hoặc `maxsize`; công cụ hiển thị cũng có time filter. Vì vậy file trống ở khoảng đang tìm có thể do **trích xuất sai cửa sổ**, dù recording gốc từng có dữ liệu.

### Bảng phân biệt nhanh

| Nguyên nhân | Dữ liệu cũ có thể lấy lại từ file đang có? | Cách xử lý |
| --- | --- | --- |
| Event chưa bật khi sự cố xảy ra | Không | Thu lại với đúng event, nếu tái hiện được |
| Threshold đã loại event khi commit | Không | Hạ threshold phù hợp và thu lại |
| Sampling/period không bắt đúng thời điểm | Không thể suy ra các event không được lấy mẫu | Tăng độ phân giải hoặc bổ sung metric khác |
| Dữ liệu bị drop/ghi lỗi | Không thể tái tạo chính xác phần đã mất từ file thiếu | Khắc phục pipeline/overhead, đối chiếu nguồn khác, thu lại |
| Chunk cũ bị loại do `maxage`/`maxsize` | Không từ bản dump hiện có; chỉ có thể còn ở bản sao khác đã lưu trước | Tăng retention **trước** cửa sổ sự cố, dump kịp thời |
| Export/dump hoặc giao diện đang lọc | Có thể có trong recording đầy đủ nếu còn lưu | Dùng đúng recording, bỏ lọc hoặc dump lại |
| Không có stack trace | Event có thể vẫn tồn tại | Bật `stackTrace` và thu lại khi cần phân tích call site |

## 5. Kiểm tra tệp `.jfr` trước khi suy diễn

Có hai lớp cần kiểm chứng: **recording đang chạy** và **artifact sau khi dump**. Chúng không tự động giống nhau nếu recording được sửa cấu hình hoặc bị giới hạn khi export.

### 5.1. Thu một bản ghi có tên và cửa sổ rõ ràng

Ví dụ đang chạy Java 17+ và chưa có recording phù hợp, sau khi xác nhận PID là `12345`:

```bash
jcmd 12345 JFR.start name=diagnostics settings=profile disk=true duration=120s filename=diagnostics.jfr
jcmd 12345 JFR.check name=diagnostics verbose=true
```

Đây là lệnh **bắt đầu recording mới trong JVM đang chạy**, không phải chạy file Java. `settings=profile` dùng template có sẵn và có thể thu nhiều dữ liệu hơn `default`; không đảm bảo event bạn cần đã bật hoặc threshold phù hợp. Cửa sổ 120 giây chỉ hữu ích khi thao tác tái hiện lỗi **xảy ra trong khoảng đó**.

Nếu cần lấy snapshot trước khi recording tự kết thúc:

```bash
jcmd 12345 JFR.dump name=diagnostics filename=diagnostics-now.jfr
```

`JFR.dump` ghi dữ liệu ra file và **recording đang chạy tiếp tục chạy**. Xác nhận đường dẫn thực tế, timestamp, thời điểm bắt đầu/dừng và PID. Nếu lệnh thất bại, không coi file cũ cùng tên là bản thu thành công mới.

### 5.2. Đọc file bằng công cụ `jfr`

Các lệnh sau đọc file đã có, không thay đổi những event ban đầu được ghi:

```bash
jfr summary diagnostics-now.jfr
jfr metadata --events jdk.JavaMonitorEnter diagnostics-now.jfr
jfr print --events jdk.JavaMonitorEnter diagnostics-now.jfr
```

- `jfr summary` cho thời lượng/thống kê event type và số event **được lưu trong file**. Đây là điểm bắt đầu để biết “thiếu một loại” hay “toàn bộ cửa sổ” có vấn đề.
- `jfr metadata` hiển thị mô tả event type và trường; **có metadata không đồng nghĩa có instance**.
- `jfr print --events ...` chỉ in event phù hợp bộ lọc; đầu ra trống chưa đủ chứng minh event không từng xảy ra. Kiểm tra đúng tên đầy đủ, file đúng và bộ lọc khác đang áp dụng.
- Trong công cụ giao diện như JDK Mission Control, kiểm tra thêm **time range**, lựa chọn event type, bộ lọc thread và cách tổng hợp. Một đồ thị trống có thể do view đang lọc.

Nếu chưa chắc tên event chính xác:

```bash
jfr metadata diagnostics-now.jfr
jfr summary diagnostics-now.jfr
```

Dùng tên event thực tìm được để chạy `jfr print`. JDK cho phép nhiều event type nên output `metadata` có thể dài; đọc có chọn lọc theo vấn đề.

### 5.3. “Không có event” phải được ghi thành điều gì?

Không đủ: “Trong JFR không có monitor contention, nên ứng dụng không bị contention.”

Cách kết luận chính xác hơn:

> Trong tệp `diagnostics-now.jfr` của JVM đã kiểm tra, trong khoảng thời gian được lưu, không thấy instance `jdk.JavaMonitorEnter`. Chưa thể loại trừ contention ngắn hơn threshold, xảy ra ngoài cửa sổ, bị sampling/loss, hoặc khác với loại event đang tìm. Cần xác minh cấu hình active và tái hiện với ngưỡng phù hợp.

Nếu đã xác nhận event enable, threshold hợp lý, cửa sổ bao phủ workload và không phát hiện dấu hiệu mất dữ liệu, mức tin cậy tăng, nhưng vẫn mô tả **giới hạn quan sát của JFR** khi báo cáo.

## 6. Bật đúng event/threshold bằng cấu hình riêng

Khi mục tiêu đã rõ là monitor contention rất ngắn, tạo một template riêng dựa trên `default.jfc`. Ví dụ trong Bash/Linux/macOS, với `JAVA_HOME` trỏ tới JDK đầy đủ:

```bash
jfr configure --input "$JAVA_HOME/lib/jfr/default.jfc" \
  --output contention-debug.jfc \
  "jdk.JavaMonitorEnter#enabled=true" \
  "jdk.JavaMonitorEnter#threshold=0ms" \
  "jdk.JavaMonitorEnter#stackTrace=true"
```

`jfr configure` tạo file `contention-debug.jfc`, **không tự áp dụng cho recording cũ**. Khi thu mới:

```bash
jcmd 12345 JFR.start name=contention-check settings=contention-debug.jfc \
  duration=60s disk=true filename=contention-check.jfr
jcmd 12345 JFR.check name=contention-check verbose=true
```

Sau khi chạy workload gây tranh chấp thật và file được ghi ra, kiểm tra:

```bash
jfr summary contention-check.jfr
jfr print --events jdk.JavaMonitorEnter contention-check.jfr
```

Cần chú ý:

1. **Lệnh trên dùng cú pháp shell Bash.** Trên Windows PowerShell, dùng đường dẫn `.jfc` của JDK thực tế và chạy lệnh trên một dòng hoặc ngắt dòng bằng cú pháp PowerShell phù hợp; không dùng dấu `\` nối dòng Bash như nguyên mẫu.
2. `threshold=0ms` làm tăng khả năng thu các contention ngắn nhưng không biến một event không phát sinh thành event có thật, cũng không đảm bảo ghi đủ khi hệ thống quá tải.
3. Event stack trace cho biết stack tại thời điểm ghi phù hợp khả năng event; có thể tăng overhead và kích thước file.
4. Không áp dụng toàn bộ event ở ngưỡng 0 và stack trace trên production trong thời gian dài khi chưa đánh giá overhead.
5. Muốn quan sát periodic event hoặc execution sampling, sửa **`period`/cơ chế sampling của chính event đó**, không áp dụng máy móc `threshold`.

## 7. Thí nghiệm Java 17+: chứng minh vắng mặt do `enabled` và `threshold`

Đoạn chương trình độc lập sau tạo **ba recording tuần tự** trong cùng một JVM với một custom event. Mỗi recording commit một event, nhưng chỉ trường hợp đầu được lưu. Ví dụ cố ý chọn threshold **một ngày** cho một event có thời lượng gần bằng 0, giúp kết quả tránh phụ thuộc vào độ chính xác của lệnh sleep.

```java
// File: JfrSettingsDemo.java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

public class JfrSettingsDemo {
    @Name("demo.Work")
    public static class Work extends Event {
        public String label;
    }

    private static long record(String label, boolean enabled, Duration threshold)
            throws Exception {
        Path file = Files.createTempFile("jfr-settings-demo-", ".jfr");
        try (Recording recording = new Recording()) {
            if (enabled) {
                recording.enable(Work.class).withThreshold(threshold);
            } else {
                recording.disable(Work.class);
            }
            recording.start();

            Work event = new Work();
            event.label = label;
            event.begin();
            event.end();
            event.commit();

            recording.stop();
            recording.dump(file);
        }
        try {
            return RecordingFile.readAllEvents(file).stream()
                    .filter(e -> e.getEventType().getName().equals("demo.Work"))
                    .count();
        } finally {
            Files.deleteIfExists(file);
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("enabled=" + record("visible", true, Duration.ZERO));
        System.out.println("disabled=" + record("disabled", false, Duration.ZERO));
        System.out.println("threshold=" + record("filtered", true, Duration.ofDays(1)));
    }
}
```

Với JDK 17+ có module chuẩn `jdk.jfr`, lưu tên file **đúng `JfrSettingsDemo.java`**, rồi chạy:

```bash
javac JfrSettingsDemo.java
java JfrSettingsDemo
```

Stdout kỳ vọng; ví dụ đã được biên dịch và chạy kiểm chứng với OpenJDK 24:

```text
enabled=1
disabled=0
threshold=0
```

Giải thích:

- **`enabled=1`**: custom event `demo.Work` được bật, threshold bằng 0; một event đã commit có mặt trong file đầu tiên.
- **`disabled=0`**: cùng hành vi gọi `event.commit()` nhưng recording cấu hình không thu loại event đó.
- **`threshold=0`**: event vẫn được enable và commit, nhưng thời lượng rất ngắn, dưới ngưỡng một ngày, nên không xuất hiện trong file thứ ba.

Các tệp `.jfr` tạm được tạo trong thư mục temp của hệ điều hành và xóa sau khi đếm; đây là thí nghiệm API, không giả lập hiện tượng **mất dữ liệu do quá tải buffer**. Nếu muốn mô phỏng thực tế lỗi nghi ngờ, hãy dùng workload/recording thật và đo thêm độ trễ, số lượng request, kích thước recording.

**Điều cần nhớ:** hai con số 0 trông giống nhau khi đọc `jfr summary`, nhưng **nguyên nhân khác nhau**. Không thể chỉ lấy số 0 để chọn sửa code hay kết luận không có hành vi xảy ra.

## 8. Quy trình điều tra khi JFR thiếu dữ liệu

### Bước 1 — Xác định chính xác bạn kỳ vọng thấy gì

Nói rõ: “Tôi kỳ vọng `jdk.FileRead` khi đọc file chậm trong khoảng 14:20–14:25”, hoặc “Tôi muốn thấy contention hơn 2 ms”, thay vì chỉ viết “JFR thiếu log”. Ghi JDK, OS, build, PID/container và cách tạo workload.

Nếu nghi ngờ **loại event không tương ứng với hành vi**, ví dụ xem `JavaMonitorEnter` khi vấn đề nằm ở `LockSupport.park` hoặc I/O, hãy chọn event/metric đúng thay vì ép threshold của event sai.

### Bước 2 — Xác nhận recording thật sự chạy đúng thời điểm

Kiểm tra `JFR.check`, recording name, `delay`, `duration`, mốc bắt đầu/dừng, timezone và thời điểm sự cố. `duration` hết hoặc `delay` chưa qua thì event ở ngoài recording không thể xuất hiện. Nếu sự cố trước khi recorder bật, cần kích hoạt sớm hơn ở vòng tái hiện sau.

### Bước 3 — Kiểm tra “bật gì” chứ không chỉ “đặt tên profile gì”

Đọc `JFR.check verbose=true` khi đang chạy; lưu file `.jfc`/lệnh start và so với event setting thực. Đừng suy `settings=profile` nghĩa là mọi event đều enable. Nếu có nhiều recording, xác nhận chính xác recording nào được dump; không nhầm PID hoặc tên.

### Bước 4 — Kiểm tra threshold, period, sampling và stack trace

Nếu event type có instance nhưng quá ít: xem threshold, period và bản chất sampling. Nếu event có mặt nhưng thiếu stack: xem `stackTrace` và cách trình bày/`--stack-depth` của công cụ, không đổi thành giả thuyết event bị mất.

### Bước 5 — Kiểm tra dữ liệu đầu ra và retention

Chạy `jfr summary` cho file, xem start/end thực tế, số event, dung lượng; kiểm tra `maxage`/`maxsize`, `disk`, `begin/end` khi dump, lỗi ghi file, stop đột ngột, và filter của công cụ. Khi cần lịch sử dài, định nghĩa chính sách lưu trước sự cố: dung lượng repository, rolling window, thời điểm dump, lưu file trong thư mục có đủ chỗ.

### Bước 6 — Đặt giả thuyết mất dữ liệu có bằng chứng

Chỉ nghi recorder loss khi có tín hiệu như cảnh báo/ghi lỗi, đoạn thời gian thiếu bất thường, file không hoàn chỉnh, event rate quá lớn so với khả năng lưu, hoặc so sánh được với nguồn độc lập. Mất event do **threshold** là lọc theo thiết kế; dữ liệu cũ bị xóa do **retention** là chính sách lưu; cần gọi đúng tên vấn đề.

### Bước 7 — Thu lại bản có khả năng kiểm chứng

Chỉ bật event cần cho câu hỏi, chọn threshold nhỏ vừa đủ, dùng khoảng thời gian ngắn và workload có thể tái hiện; cân nhắc tăng tài nguyên/giảm lượng event để hạn chế overhead. Lặp phép thử ít nhất hai lần nếu dấu hiệu không ổn định. Nếu thiếu từ event streaming/dashboard, đối chiếu **tệp JFR gốc** trước khi quy trách nhiệm cho producer.

### Bước 8 — Ghi kết luận cùng giới hạn

Ví dụ:

- “`jdk.JavaMonitorEnter` không xuất hiện vì recording có `enabled=false`; cần thu lại, không có bằng chứng về lượng contention tại thời điểm cũ.”
- “`jdk.FileRead` có threshold 20 ms, nên file hiện tại chỉ phản ánh phần I/O đủ chậm; không dùng số event để tính tổng số lần đọc.”
- “File chỉ giữ 15 phút cuối, nên không thể xác minh incident xảy ra 45 phút trước từ artifact này.”
- “Có bằng chứng lỗi ghi/thiếu chunk trong khoảng X–Y; không dùng dữ liệu trong khoảng này để kết luận hiện tượng không tồn tại.”

## 9. Bảng quyết định nhanh theo triệu chứng

| Triệu chứng | Kiểm tra ưu tiên | Hành động phù hợp |
| --- | --- | --- |
| `jfr print --events X` trống | Đúng tên X, `jfr summary`, recording window, `enabled` | Bật X/đổi event đúng và thu lại nếu cần |
| Metadata có event type, summary không có instance | `enabled`, event đã phát sinh chưa, threshold, time window | Không coi metadata là bằng chứng đã thu |
| Event chỉ xuất hiện khi tác vụ rất chậm | `threshold` trên duration event | Hạ threshold có kiểm soát |
| Event thống kê rất thưa | `period` hoặc sampling | Tăng độ phân giải nếu chi phí chấp nhận |
| Có event nhưng stack trống/ngắn | `stackTrace`, stack depth và view | Thu lại với stackTrace hoặc chỉnh hiển thị |
| File thiếu những phút đầu | `maxage`/`maxsize`, `disk=false`, dump range | Điều chỉnh retention **trước khi tái hiện** |
| File/chunk bị lỗi hoặc khoảng thiếu bất thường | Log JVM/JFR, lưu trữ, buffer, sự cố tiến trình | Khắc phục lỗi ghi, giảm event volume, thu lại |
| Dashboard trống nhưng `jfr print` có event | Bộ lọc thời gian, loại event, thread, pipeline import | Sửa filter/import, giữ nguyên file gốc |
| File thu đủ nhưng count thấp hơn số request | Event không ứng 1:1 với request, filter/sampling, timestamp | Xác định denominator và quan hệ event→request |

## 10. Những sai lầm cần tránh

1. **“Không có event tức là không có lỗi.”** Chỉ đúng khi đã chứng minh event đó sẽ được phát và thu trong đúng điều kiện; trong thực tế thường không đủ bằng chứng để kết luận tuyệt đối.
2. **“Profile đã bật tất cả.”** `profile.jfc` có phạm vi và threshold riêng; kiểm tra chính JDK và setting của recording.
3. **“Threshold 20 ms nghĩa là sự cố dưới 20 ms không xảy ra.”** Sự cố có thể xảy ra, chỉ không vào file theo bộ lọc.
4. **“Đếm execution sample là đếm số lần chạy method.”** Sampling là quan sát thống kê, không phải execution tracing đầy đủ.
5. **“JFR metadata có schema nên phải có dữ liệu.”** Schema khác instance.
6. **“Thiếu stack trace là mất event.”** Cần phân biệt trường payload không được thu với cả event không được ghi.
7. **“JFR.dump phục hồi mọi thứ từng xảy ra.”** Dump chỉ lấy những gì còn trong recording và trong khoảng trích xuất; phần đã lọc/mất/xóa không thể tạo lại.
8. **“Tăng maxsize sau sự cố phục hồi lịch sử.”** Không phục hồi chunk đã bị loại.
9. **“Cứ bật tất cả event ngưỡng 0, không tốn chi phí.”** Ghi dày hơn làm tăng overhead/khối lượng dữ liệu, thậm chí làm khó phân tích.
10. **“Một file trống chứng minh JVM không hoạt động.”** Xác minh PID, tên recording, thời gian, đường dẫn artifact, time filter và loại event trước.

## 11. Checklist khi bàn giao bản JFR

- [ ] Có PID/JDK/build/JFR recording name và mốc thời gian chính xác.
- [ ] Biết `delay`, `duration`, thời điểm start/stop và thời điểm xảy ra workload.
- [ ] Đã xác minh `enabled` cùng `threshold`/`period`/sampling của event cần tìm.
- [ ] Nếu cần stack trace, đã kiểm tra `stackTrace` và giới hạn trình bày.
- [ ] Đã chạy `jfr summary`, kiểm tra metadata/event count và đọc đúng file.
- [ ] Đã đối chiếu `disk`, `maxage`, `maxsize`, cửa sổ dump và file repository.
- [ ] Đã kiểm tra lỗi recorder/ghi dữ liệu hoặc sự cố tiến trình; không tự giả định không có data loss.
- [ ] Có ít nhất một số đo độc lập khi kết luận quan trọng (log/request/metric/GC/OS), đặc biệt nếu dữ liệu JFR thiếu.
- [ ] Kết luận ghi rõ điều **đã quan sát**, điều **chưa thể suy ra**, cùng cách thu lại để kiểm chứng.

**Kết luận:** “Không thấy event” là kết quả của **phép quan sát có cấu hình và giới hạn**, không phải phủ định tự động đối với hành vi trong ứng dụng. Hãy kiểm tra lần lượt **đúng event → enabled → threshold/period/sampling → recording window → buffer/retention → dump và bộ lọc phân tích** trước khi giải thích khoảng trống trong JFR.

### Tài liệu tra cứu chính thức

- Oracle JDK 21 — `jdk.jfr` event settings (`enabled`, `threshold`, `period`, `stackTrace`): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle JDK 21 — `jcmd` (`JFR.start`, `JFR.check`, `JFR.dump`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — công cụ `jfr` (`summary`, `metadata`, `print`, `configure`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- Dev.java — cấu hình recording và `.jfc`: https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/
