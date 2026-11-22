# 15.2 Đọc jfr summary và metadata trước khi chọn nhóm sự kiện cần xem

## Mục tiêu

Khi nhận một file **Java Flight Recorder (JFR)**, bước đầu tiên là hiểu **file đã ghi những gì, trong khoảng thời gian nào và mỗi loại sự kiện có cấu trúc ra sao**. Không nên lập tức in toàn bộ file hoặc kết luận từ một event có tên nghe giống vấn đề đang điều tra.

Sau bài này, bạn có thể:

1. Dùng **jfr summary** để kiểm tra file, khoảng thời gian, số chunk, **Count** và **Size** theo event type.
2. Dùng **jfr metadata** để tìm tên event chính xác, category, mô tả và schema của từng event, trước khi viết truy vấn.
3. Phân biệt **event type được định nghĩa** với **event thực sự xuất hiện** trong bản ghi.
4. Chọn nhóm event phù hợp với câu hỏi về CPU, GC, allocation, lock contention, thread park, I/O, class loading và runtime.
5. Lọc event bằng **jfr print --events** hoặc **--categories**, hiểu giới hạn của sampling, threshold, event settings và stack traces.
6. Tự tạo một bản ghi JFR nhỏ bằng Java 17+ và kiểm tra từng bước với công cụ đi kèm JDK.

**Phạm vi:** các lệnh và ví dụ ưu tiên **HotSpot/OpenJDK 21**; Java 17 cũng có các lệnh cơ bản summary, metadata và print. Tập event, category, trường dữ liệu và một số lệnh phụ có thể thay đổi theo phiên bản/vendor JDK.

## 1. JFR file là gì và vì sao phải kiểm kê trước?

JFR thu thập các **event** do JVM hoặc ứng dụng phát ra: ví dụ bắt đầu/kết thúc GC, mẫu thực thi, cấp phát bộ nhớ, thread park, truy cập file/socket, hoạt động class loading. Dữ liệu thường được lưu ở file nhị phân có đuôi **.jfr**, kèm thông tin kiểu dữ liệu cho các event và timestamps.

Hãy phân biệt ba cấp:

- **Recording:** một khoảng quan sát có thời gian bắt đầu/kết thúc, các chunks và cấu hình event được thu thập.
- **Event type:** kiểu sự kiện, ví dụ **jdk.GarbageCollection** hoặc **jdk.ExecutionSample**, có tên, category, nhãn, mô tả và danh sách trường.
- **Event instance:** một lần xảy ra được ghi vào file, với startTime, các trường dữ liệu và có thể có duration, thread hoặc stack trace tùy type/cấu hình.

Một file có hàng trăm nghìn **jdk.ExecutionSample** không có nghĩa CPU đã chạy “hàng trăm nghìn lần”, và một event type được mô tả trong metadata không có nghĩa file có instance tương ứng.

**Thứ tự đọc đúng:**

~~~text
Có file .jfr
    |
    v
jfr summary: file có đúng thời gian, event types và mật độ dữ liệu?
    |
    v
jfr metadata: tên, category và field của event đáng xem là gì?
    |
    v
Chọn event types có liên quan và thực sự có dữ liệu
    |
    v
jfr print --events / --categories: chỉ in tập mục tiêu
    |
    v
Phân tích duration, stackTrace, thread, object/GC IDs, correlation
~~~

Nếu summary cho thấy file không bao phủ thời điểm sự cố hoặc thiếu nhóm event cần thiết, cần điều chỉnh recording và thu lại, thay vì ép kết luận từ file thiếu dữ liệu.

## 2. Điều kiện trước khi chạy

Cần **JDK đầy đủ** có công cụ **jfr**, không chỉ JRE rút gọn. Kiểm tra JDK đang chạy và khả năng dùng CLI:

~~~bash
java -version
jfr --version
jfr help
jfr help summary
jfr help metadata
jfr help print
~~~

Tùy OS, phải mở terminal có **JDK/bin** trong PATH. Một JDK mới có thể đọc nhiều file tạo bởi JDK cũ; ngược lại tính tương thích không phải lúc nào hai chiều, vì metadata, định dạng và event types thay đổi. Đối với phân tích khó, ghi lại **vendor/phiên bản JVM đã ghi file** và phiên bản **jfr CLI** dùng để đọc.

Khi file đã có sẵn, đặt tên **recording.jfr** làm ví dụ (thay bằng đường dẫn thực tế). Không cần kết nối đến JVM gốc để chạy **jfr summary/metadata/print** trên một file đã lưu.

~~~bash
jfr summary recording.jfr
jfr metadata recording.jfr
~~~

Nếu **recording.jfr không tồn tại, bị cắt hoặc hỏng**, các lệnh có thể báo lỗi đọc. Giải quyết nguồn file trước. Không tự coi “lệnh không in event” là tín hiệu của ứng dụng khi bản ghi không hợp lệ.

### Ghi file ở mức tối thiểu khi chưa có .jfr

Có thể tạo recording cho một ứng dụng Java ở lần khởi động mới:

~~~bash
java -XX:StartFlightRecording=filename=recording.jfr,duration=60s,settings=profile -jar app.jar
~~~

Lệnh dùng **HotSpot** có JFR và cần đường dẫn ghi file hợp lệ. Sau khoảng thời gian cấu hình, JVM xuất recording; ứng dụng có thể tiếp tục chạy. Với process đã chạy, có thể dùng **jcmd PID JFR.start** và **JFR.dump** theo khả năng attach/quyền truy cập, nhưng bài này tập trung vào *đọc bản ghi đã xuất*, không đi sâu quản lý recording live.

**Không mặc định profile chứa mọi event:** settings=default/profile, thay đổi threshold, sampling rate, stackTrace và JDK quyết định những gì được ghi. Một file có thể rất “đầy” event loại A nhưng hoàn toàn không đo loại B.

## 3. jfr summary: đọc bản đồ tổng thể trước khi xem chi tiết

Lệnh:

~~~bash
jfr summary recording.jfr
~~~

Tùy phiên bản JDK, đầu ra thường có **version/file**, **chunks**, **start/duration**, rồi bảng event type với **Count** và **Size**. Ví dụ rút gọn, **số liệu minh họa hoàn toàn giả định**:

~~~text
Version: 2.x
Chunks: 1
Start: 2026-10-29 09:00:00 (UTC)
Duration: 60 s

Event Type                         Count       Size (bytes)
jdk.CPULoad                           60              2400
jdk.ExecutionSample                  800             50000
jdk.GarbageCollection                  8              1600
jdk.GCHeapSummary                     16              2200
jdk.JavaMonitorEnter                   0                 0
jdk.SocketRead                         0                 0
...
~~~

Cách trình bày, sort order, timestamp và số event có thể khác. **Không xem khối minh họa này là stdout đảm bảo của một file thực tế.**

### 3.1. Start, Duration, Chunks: kiểm tra tính phù hợp của khoảng đo

- **Start**: mốc bắt đầu của recording/chunks; kiểm tra múi giờ và thời điểm xảy ra hiện tượng.
- **Duration**: khoảng thời gian file ghi lại, không phải duration của từng event.
- **Chunks**: JFR lưu dữ liệu theo các chunk, có metadata và event records; một file có thể gồm nhiều chunk.
- **Version/format**: giúp xác nhận khả năng đọc với công cụ đang dùng.

Giả sử lỗi latency xảy ra lúc **15:35**, nhưng file ghi **15:10–15:15**: dù nội dung file hợp lệ, nó **không đại diện** khoảng lỗi. Hoặc file ghi 10 phút nhưng vấn đề chỉ xuất hiện ở 5 giây cuối: tổng Count/Size của cả file không tự cho biết phân bố theo thời gian; cần xem startTime các event sau khi lọc.

### 3.2. Count là gì?

**Count** là số **event instances được ghi nhận** theo type trong file. Nó **không nhất thiết bằng** số lần hoạt động thực tế trong ứng dụng:

- **Periodic event**, ví dụ CPU load: Count phụ thuộc chu kỳ phát event và thời gian ghi.
- **Sampling event**, ví dụ execution/allocation sample: Count phản ánh **mẫu đã thu**, không phải tổng số lệnh CPU, tổng số object cấp phát hay số lần phương thức được gọi.
- **Threshold event**, ví dụ một số I/O/lock event: operation dưới ngưỡng có thể **không được ghi**.
- **Disabled event**: type có thể không được thu ở cấu hình hiện hành.
- **Event dropped/truncated** hoặc recording đã được lọc/scrub: dữ liệu quan sát có thể không đầy đủ.

Do đó **Count=0 không chứng minh hiện tượng không xảy ra**. Nó chỉ nói file không chứa instance thuộc type đó theo cách summary đang đọc. Trước khi kết luận, kiểm tra **event settings, coverage, duration, thresholds và file integrity**.

### 3.3. Size là gì?

**Size** trong bảng summary là lượng **dung lượng serialized của event records** theo từng event type (cách tính chính xác phụ thuộc phiên bản công cụ). Đây không phải:

- Dung lượng RAM dùng bởi các Java objects của loại đó.
- Thời gian CPU chạy event.
- Dung lượng heap bị leak.
- Số byte file hoặc socket mà event I/O đã xử lý.

Một loại event ít instance nhưng chứa stack hoặc payload metadata lớn có thể có **Size** lớn. Một event type có Count lớn nhưng mỗi instance nhỏ cũng có thể đóng góp nhiều dung lượng recording. **Size hữu ích để biết loại dữ liệu nào chiếm file và độ nặng của recording**, không phải một chỉ số sức khỏe ứng dụng.

### 3.4. Summary đủ cho những câu hỏi nào?

Summary trả lời nhanh: “File có event loại nào, bao nhiêu instances, recording bao lâu, type nào chiếm phần lớn record bytes?”. Summary **không chỉ ra** stack trace, thread cụ thể, nguyên nhân GC, nơi phát sinh allocation, duration từng lần block, hoặc phép tương quan nhiều event. Những câu hỏi này thuộc bước sau.

Ví dụ: thấy **jdk.GarbageCollection: 8** chỉ nói có 8 event GC đã ghi. Nó không chứng minh GC là lý do latency cao. Cần xem **startTime, duration, loại GC, heap before/after và thời điểm latency**.

## 4. jfr metadata: đọc schema trước khi viết bộ lọc

Lệnh cơ bản:

~~~bash
jfr metadata recording.jfr
~~~

Khác summary, **metadata** mô tả *định nghĩa kiểu dữ liệu*: event names, categories, labels, descriptions, fields và một số annotation liên quan đến semantic/đơn vị. Nó không liệt kê tất cả event instances và không cho bạn tổng số instance của một type.

Với JDK 21 có thể lọc phần metadata cần xem:

~~~bash
jfr metadata --events jdk.GarbageCollection recording.jfr
jfr metadata --events jdk.ExecutionSample recording.jfr
jfr metadata --events jdk.JavaMonitorEnter,jdk.ThreadPark recording.jfr
~~~

Có thể lọc theo category nếu category của file phù hợp:

~~~bash
jfr metadata --categories "Garbage Collection" recording.jfr
~~~

**Tên category chính xác khác tên event** và có thể là nhãn dạng đường dẫn/hierarchy tùy event. Nếu không tìm thấy gì, xem metadata không lọc hoặc dùng **jfr help metadata** để xác nhận cú pháp và tên category thực tế.

### 4.1. Đọc một event definition như thế nào?

Một event type có thể gồm:

| Thành phần metadata | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| **Name** | Tên máy đọc được, thường dạng **jdk.SomeEvent** hoặc tên custom như **demo.WorkPhase** | Dùng với **--events** |
| **Label/Description** | Nhãn và lời mô tả mang tính người đọc | Chọn event đúng hiện tượng cần điều tra |
| **Category** | Phân nhóm một hoặc nhiều cấp, ví dụ nhóm GC, Profiling, I/O | Chọn cả nhóm khi cần khám phá |
| **startTime / duration** | Timestamp và/hoặc độ dài hoạt động khi event type có trường phù hợp | Lọc khoảng thời gian, tìm operation chậm |
| **thread / eventThread** | Thông tin thread nếu event type/cấu hình ghi nhận | Phân biệt thread xảy ra event với thread được lấy mẫu |
| **stackTrace** | Các frames được lưu khi có hỗ trợ và được bật | Truy nguồn code path; không tự giả định luôn có |
| **Field riêng** | GC id, class, monitor, allocation size, address, bytesRead... tùy event | Quyết định có đủ dữ liệu trả lời câu hỏi không |
| **Unit/content annotations** | Time span, bytes, percentage, data amount... | Tránh nhầm đơn vị, conversion |

**Tên trường trong bảng là khái niệm chung**, không phải schema cố định cho tất cả event. Ví dụ event sample CPU và event GC không nhất thiết có cùng fields; một event có thể không có duration có ý nghĩa. Đọc schema thật của **type trong đúng recording** trước khi lấy giá trị hoặc viết tool parser.

### 4.2. metadata có file và metadata không có file khác nhau

~~~bash
# Định nghĩa type được lấy từ recording:
jfr metadata recording.jfr

# Khi bỏ tham số file, dùng metadata của JDK đang chạy công cụ jfr:
jfr metadata
~~~

Cách thứ hai tiện để tìm tên event **JDK hiện tại hỗ trợ**, nhưng không chứng minh file cũ có type đó, và type/field có thể đã thay đổi giữa JDK ghi file với JDK dùng đọc. Đối với một incident cụ thể, ưu tiên **jfr metadata recording.jfr**.

**Metadata có định nghĩa không đồng nghĩa Count > 0.** Một type có thể xuất hiện trong metadata mà không có event instance. Vì vậy luôn đọc **summary** để xác nhận dữ liệu thực sự có trong file, rồi dùng **metadata** để hiểu cách diễn giải.

### 4.3. Metadata không phải bản sao toàn bộ recording settings

Metadata cho biết *kiểu event và các field có thể có*, đôi khi kèm setting definitions/annotations. Nó **không thay thế việc xác minh effective event settings** của recording: event có được bật không, threshold bao nhiêu, period thế nào, stackTrace có lưu không, và toàn bộ cấu hình giai đoạn thu thập ra sao. Muốn xác minh settings thực tế, phải xem cấu hình recording (.jfc / JFR APIs / JFR configuration metadata nếu đã được ghi và có thể phân tích), cùng ghi chú lúc thu thập.

**Đặc biệt:** thấy field **stackTrace** trong schema **không đảm bảo** mọi instance có stack trace đầy đủ. Có thể stack bị tắt, frame bị rút gọn, sampling bỏ qua frame hoặc chỉ có các stack frames không phù hợp với điều bạn định truy tìm.

## 5. Chọn event theo câu hỏi: từ summary đến shortlist

Cách chọn hiệu quả là bắt đầu bằng **triệu chứng**, sau đó đối chiếu với những type thực sự có Count trong file, rồi kiểm tra metadata.

| Triệu chứng/câu hỏi | Event cần tìm trước | Vì sao nên xem | Lưu ý |
| --- | --- | --- | --- |
| CPU cao, hotspot xử lý | **jdk.ExecutionSample**, **jdk.CPULoad**, có thể thêm native/CPU samples theo JDK | Mẫu stack và xu hướng CPU | Sample count không phải CPU time hoặc số method calls |
| Pause/latency quanh GC | **jdk.GarbageCollection**, **jdk.GCPhasePause**, **jdk.GCHeapSummary**, event GC cụ thể | Timeline, duration, heap và pha GC | Có event theo GC collector và cấu hình khác nhau |
| Tạo nhiều object tạm | **jdk.ObjectAllocationSample**, và event allocation khác nếu đã bật | Class/stack allocation có thể gây pressure | Sampling/weight; không suy ra live heap hay leak trực tiếp |
| Contention khi vào synchronized | **jdk.JavaMonitorEnter** | Monitor contention vượt ngưỡng được ghi | Count thấp có thể do threshold |
| Thread bị park hoặc chờ | **jdk.ThreadPark** | Duration, thread và stack nếu có | Park không phải cứ xuất hiện là lỗi |
| Đọc socket chậm | **jdk.SocketRead**, **jdk.SocketWrite** | Duration và liên quan I/O | Event dưới threshold có thể không được ghi |
| File I/O | **jdk.FileRead**, **jdk.FileWrite** | Operation, bytes, duration | Count không phải số syscall; I/O nhỏ có thể vắng mặt |
| Class loading bất thường | **jdk.ClassLoad**, **jdk.ClassLoadingStatistics** hoặc type thực tế có trong file | Biến động class loading/metaspace | Type/field phụ thuộc JDK và profile |
| Thread churn | **jdk.ThreadStart**, **jdk.ThreadEnd**, **jdk.ThreadCPULoad** nếu có | Thread tạo/kết thúc và hoạt động | Không tương đương toàn bộ virtual threads trên mọi JDK |
| Custom business timing | Event name do ứng dụng đặt, ví dụ **demo.WorkPhase** | Đo đúng nghiệp vụ, transaction spans | Tên/fields do tác giả event định nghĩa |

Các ví dụ event **chỉ là điểm bắt đầu**. Hãy xem metadata thật trong file; khi event không hiện diện hoặc Count=0, đánh giá lại cách thu dữ liệu. Các nhóm GC, CPU, I/O thường phải **tương quan theo timestamp** thay vì chọn một event rồi suy luận nguyên nhân.

**Ví dụ:** production p99 latency tăng nhưng summary chỉ có CPULoad và ExecutionSample, không có event FileRead/SocketRead. Bạn **có thể phân tích CPU**, nhưng chưa thể kết luận “I/O không gây ra latency”; cần một recording có dữ liệu I/O phù hợp.

## 6. Khi nào lọc theo event, khi nào theo category?

### 6.1. Chọn event name khi đã xác định mục tiêu

~~~bash
jfr print --events jdk.GarbageCollection recording.jfr
jfr print --events jdk.ExecutionSample recording.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark recording.jfr
~~~

**--events** nhận tên type (tên đơn giản hoặc đầy đủ theo cú pháp công cụ, có hỗ trợ bộ lọc). Đối với quy trình có thể lặp lại, ưu tiên **tên đầy đủ từ metadata**, nhất là khi có custom event trùng simple name.

### 6.2. Chọn category để khám phá nhiều event cùng chủ đề

~~~bash
jfr print --categories GC recording.jfr
~~~

Lệnh dùng category filter. Đối chiếu category thực từ **jfr metadata**, tránh giả định tất cả event liên quan GC đều chỉ ở một category tên “GC” hoặc được gộp giống nhau ở mọi JDK.

Nếu kết hợp **--categories** và **--events** trong **jfr print**, theo hướng dẫn JDK 21, kết quả là **hợp/union** của các event thỏa từng filter, không phải giao/intersection:

~~~bash
jfr print --categories GC --events jdk.CPULoad recording.jfr
~~~

Lệnh trên có thể in cả event thuộc category GC **và** CPULoad; nó **không có nghĩa** chỉ chọn CPULoad thuộc GC. Điều này quan trọng khi muốn bộ lọc hẹp.

### 6.3. Chọn độ sâu stack và định dạng output

~~~bash
# Xem thêm frames nếu recording có lưu stack:
jfr print --events jdk.ExecutionSample --stack-depth 20 recording.jfr

# Chọn định dạng cấu trúc phục vụ xử lý bằng script:
jfr print --json --events jdk.GarbageCollection recording.jfr
~~~

**--stack-depth** chỉ thay đổi số frame mà CLI **hiển thị**, không bổ sung stack chưa được ghi trong file. **--json** giúp parsing tự động, nhưng cấu trúc JSON phụ thuộc schema và phiên bản; kiểm tra dữ liệu thật trước khi viết parser. Không nên in toàn file nếu recording lớn: event output có thể hàng triệu dòng và chứa dữ liệu nhạy cảm.

### 6.4. Khi có jfr view

JDK 21 có **jfr view** để xem dữ liệu dạng tổng hợp. Bạn có thể kiểm tra các view hỗ trợ:

~~~bash
jfr help view
jfr view types recording.jfr
~~~

Đây là bước **sau** summary/metadata khi cần bảng tổng hợp thuận tiện; **không cần jfr view để hiểu cấu trúc file**. Một số phiên bản JDK cũ có tập subcommands ít hơn, vì vậy nếu view không có, tiếp tục dùng summary, metadata và print.

## 7. Thực hành Java 17+: tự tạo file JFR với event có schema dễ kiểm tra

Mục tiêu ví dụ là **đảm bảo có event custom do chính bạn phát ra**, rồi so khớp summary, metadata và print. Ví dụ không cần web server hoặc dữ liệu production.

Tạo file **JfrInventoryDemo.java**:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class JfrInventoryDemo {
    @Name("demo.WorkPhase")
    @Label("Work Phase")
    @Category({"Demo", "JFR"})
    public static class WorkPhase extends Event {
        @Label("Phase Name")
        public String phase;

        @Label("Processed Items")
        public long items;
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of("jfr-inventory-demo.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(WorkPhase.class)
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();
            recording.start();

            for (int i = 1; i <= 3; i++) {
                WorkPhase event = new WorkPhase();
                event.phase = "phase-" + i;
                event.items = i * 100L;
                event.begin();
                event.end();
                event.commit();
            }

            recording.stop();
            recording.dump(file);
        }

        System.out.println("Created " + file);
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac --add-modules jdk.jfr JfrInventoryDemo.java
java --add-modules jdk.jfr JfrInventoryDemo
~~~

Khi chạy thành công và thư mục cho phép ghi file, **stdout do chương trình tự in** chính xác là:

~~~text
Created jfr-inventory-demo.jfr
~~~

File **jfr-inventory-demo.jfr** được tạo trong working directory. Event **demo.WorkPhase** có ba lần commit trong chương trình; khi không có lỗi thu thập dữ liệu, summary sẽ cho thấy type này với **Count=3**. Các event JVM phụ trợ, timestamp, chunk count và kích thước file không cố định, nên không đưa ra stdout đầy đủ giả định.

### 7.1. Đọc summary của file vừa tạo

~~~bash
jfr summary jfr-inventory-demo.jfr
~~~

Tìm dòng **demo.WorkPhase** trong bảng **Event Type / Count / Size**. Có thể xuất hiện nhiều event types khác do runtime/JFR tạo ra; không phải lỗi. Đối chiếu **Count** với số event code đã commit. **Size** là byte records, không phải tổng **items=600**; items là dữ liệu nghiệp vụ của event, có đơn vị riêng.

### 7.2. Đọc metadata của event custom

~~~bash
jfr metadata --events demo.WorkPhase jfr-inventory-demo.jfr
~~~

Tìm tên **demo.WorkPhase**, label **Work Phase**, category **Demo, JFR**, và các trường **phase** (String), **items** (long). Runtime có thể thêm fields chuẩn liên quan startTime/duration/eventThread/stackTrace vào biểu diễn event. Mô tả metadata và cách in có thể khác chút giữa JDK.

Đây là minh chứng rõ: metadata cho biết **items là long**, nhưng **không tự cho biết items=100, 200, 300**; muốn xem values của từng lần xảy ra phải **jfr print**.

### 7.3. In đúng instance cần xem

~~~bash
jfr print --events demo.WorkPhase jfr-inventory-demo.jfr
~~~

Bạn sẽ tìm thấy ba lần xảy ra với phase **phase-1**, **phase-2**, **phase-3** và items **100**, **200**, **300** theo thứ tự phát trong chương trình. Timestamps, duration và stack frames phụ thuộc execution/JDK.

Lúc này bạn đã kiểm tra được ba lớp:

| Bước | Thông tin mới thu được |
| --- | --- |
| summary | Recording tồn tại; demo.WorkPhase có số instances/serialized size |
| metadata | demo.WorkPhase có tên, nhãn, category và fields đúng schema |
| print | Các instance cụ thể với values và thời điểm |

### 7.4. Thử một bộ lọc không có event

~~~bash
jfr print --events jdk.SocketRead jfr-inventory-demo.jfr
~~~

Không có SocketRead trong output **không chứng minh** chương trình JVM chưa hề thực hiện I/O mạng trong toàn bộ vòng đời, và không khẳng định event đã được bật/đủ threshold; lệnh chỉ phản ánh **những instances của type đó đã nằm trong file được lọc**.

Có thể dùng **jfr metadata --events jdk.SocketRead** không kèm file để xem kiểu sự kiện do JDK hiện tại biết, nhưng phải tránh suy ngược rằng recording custom đã thu event đó.

## 8. Một checklist ngắn khi nhận file JFR từ production

Trước khi quyết định phân tích nhóm nào, kiểm tra:

| Kiểm tra | Câu hỏi cần trả lời | Hành động |
| --- | --- | --- |
| **File/Provenance** | File do JVM/JDK nào, ứng dụng nào, khi nào tạo? | Ghi JDK/version, tên file, host/PID nếu đã được cung cấp |
| **Thời gian** | Start/Duration có phủ incident? | Nếu không, tìm recording khác hoặc thu lại |
| **Chunks / tình trạng** | File đọc được, có đủ phần cần thiết? | Chạy summary; xử lý file hỏng hoặc cắt |
| **Event presence** | Type mong muốn Count > 0 hay hoàn toàn vắng? | Không phỏng đoán có dữ liệu khi Count=0 |
| **Volume** | Event types nào chiếm nhiều Count/Size? | Chọn lọc trước khi print; chú ý overhead |
| **Schema** | Tên/catégory/field chính xác là gì? | Chạy metadata theo đúng recording |
| **Collection settings** | Có sampling/threshold/period/stackTrace không? | Kiểm tra cấu hình ghi JFR và điều kiện lúc thu |
| **Correlation keys** | Có startTime, duration, thread, gcId, stackTrace hoặc IDs phù hợp? | Thiết kế truy vấn theo các trường thực tế |
| **Quyền riêng tư** | File có class names, thread names, command line, stack/payload nhạy cảm? | Giới hạn lưu trữ, chia sẻ và redaction theo chính sách |

**Không được nhầm “JFR có dữ liệu” với “JFR có bằng chứng về nguyên nhân lỗi”**. Đôi khi summary báo hàng nghìn GC events nhưng sự cố là nghẽn network; nếu không có I/O events hoặc correlation, cần thu đúng nhóm và đúng khoảng thời gian.

## 9. Phân tích ba tình huống chọn sai event

### Tình huống A: CPU cao nhưng summary chủ yếu có jdk.CPULoad

**Câu hỏi:** có thể tìm hot method từ CPULoad đơn lẻ không?

**Trả lời:** CPULoad chủ yếu phản ánh mức tải, không nhất thiết kèm application call stacks. Nếu summary có **jdk.ExecutionSample** và metadata xác nhận có stackTrace, hãy in mẫu thực thi rồi phân tích; nếu không, cần recording có sampling/profiling phù hợp. Một giá trị CPU cao không tự gán cho một method.

### Tình huống B: Nghi contention nhưng JavaMonitorEnter Count=0

Có ít nhất bốn khả năng: event không được bật, threshold bỏ qua lần chờ ngắn, lỗi xảy ra ngoài khoảng ghi, hoặc ứng dụng không có contention loại được event này đo. Từ Count=0 **không thể chọn duy nhất một giải thích**. Hãy đối chiếu file, settings, timeline, ThreadPark/monitor-related events và thực tế lock sử dụng.

### Tình huống C: Nghi allocation pressure, thấy ObjectAllocationSample Count rất lớn

Đọc metadata để biết event có các trường về **objectClass**, thread/stack, **weight** hoặc thông tin kiểu sampling phù hợp với JDK. Count lớn chỉ là **số mẫu**, không phải số object đã cấp phát. Không dùng nó để tính số object còn sống hoặc leak. Nếu cần biết retained heap và GC roots, dùng heap dump/đồ thị object như một phép đo bổ sung riêng; không làm biến dạng ý nghĩa JFR.

## 10. Cấu trúc phân tích tốt từ một file JFR

Một bản ghi chẩn đoán ngắn nên tách rõ ba cấp bằng chứng:

**1. Khả năng quan sát đã xác minh:** “Recording bắt đầu vào thời điểm X, kéo dài Y; summary có GC và execution samples, không có JavaMonitorEnter instances; metadata cho biết schema của GC/CPU event”.

**2. Quan sát từ dữ liệu có thật:** “Trong khoảng sự cố có những event GC duration dài” hoặc “Các ExecutionSample stacks tập trung vào phương thức A”. Những kết luận này phải dựa trên **jfr print/view hoặc phân tích event instances**, không lấy từ bảng Count đơn thuần.

**3. Giả thuyết cần kiểm chứng:** “GC hoặc lock contention có thể gây latency; cần đối chiếu request timestamps, GC logs, metrics, hoặc thu thêm event classes”. Ghi rõ trường hợp thiếu mẫu/đo không đúng khoảng thời gian.

Tách ba cấp giúp tránh biến **khả năng đo** thành **bằng chứng nguyên nhân**, và giúp người nhận file biết lúc nào cần thu lại recording.

## 11. Lỗi phổ biến và cách sửa

1. **In toàn file trước khi xem summary.** File lớn sẽ sinh output khổng lồ; chạy summary, lọc theo type, rồi print.
2. **Dùng metadata để đếm event.** Metadata mô tả type; phải dùng summary/đọc instances để đếm.
3. **Dùng summary để tìm field/stack.** Summary không thay thế metadata hoặc print.
4. **Tưởng Size là heap bytes hoặc I/O bytes.** Đó là độ lớn dữ liệu event đã ghi trong file.
5. **Tưởng Count của sample bằng số operation thật.** Sampling, thresholds và period làm Count khác tổng hoạt động.
6. **Thấy event trong metadata rồi khẳng định file có event đó.** Phải kiểm tra instance count.
7. **Count=0 rồi kết luận “không có vấn đề”.** Có thể event chưa bật, threshold loại bỏ hoặc recording trượt thời điểm.
8. **Giả định jfr metadata không có file mô tả recording của ứng dụng.** Nó mô tả JDK đang chạy lệnh, có thể khác producer JDK.
9. **Viết bộ lọc category theo tên tự nghĩ.** Xem category thật trong metadata; khi cần chính xác dùng event name đầy đủ.
10. **Kết hợp --events và --categories rồi tưởng là phép giao.** Trong jfr print của JDK 21, chúng chọn **union**.
11. **Tăng --stack-depth rồi tưởng tạo ra stack chưa ghi.** Chỉ tăng phần in ra khi dữ liệu stack có sẵn.
12. **Bỏ qua startTime và múi giờ.** Incident không trùng recording làm mọi phân tích lạc hướng.
13. **Coi mọi GC event là pause của ứng dụng.** Cần loại GC/phase/duration và mối tương quan với độ trễ.
14. **Trộn event fields giữa nhiều JDK.** Kiểm tra schema từ chính .jfr và phiên bản công cụ.
15. **Gắn root cause từ tên event.** Cần xem values/timeline và kiểm chứng bằng evidence khác.
16. **Gửi file JFR ra ngoài tùy tiện.** File có thể chứa command-line flags, arguments, class/method names, paths, network info và custom event data nhạy cảm; chỉ chia sẻ theo quy định.

## 12. Câu hỏi tự kiểm tra

**Câu 1:** summary báo **jdk.ExecutionSample Count=10.000**. Có thể nói JVM đã thực thi đúng 10.000 method calls không?  
**Đáp án:** Không. Đây là số mẫu execution được ghi, không phải call count.

**Câu 2:** metadata hiển thị **jdk.JavaMonitorEnter**, nhưng summary báo Count=0. Điều gì đã được xác nhận?  
**Đáp án:** Có định nghĩa type trong phạm vi metadata; không có instance type đó trong file. Chưa chứng minh không hề có contention hoặc event đã được bật.

**Câu 3:** summary báo **jdk.SocketRead Size=80 KB**. Có phải ứng dụng đã đọc 80 KB từ socket?  
**Đáp án:** Không. Đây là serialized event data size. Muốn đọc số byte I/O phải xem field tương ứng trong event instances và semantics của event.

**Câu 4:** cần tìm trường **duration** hoặc **stackTrace** của type jdk.JavaMonitorEnter trước khi viết parser. Dùng lệnh nào?  
**Đáp án:** **jfr metadata --events jdk.JavaMonitorEnter recording.jfr**, rồi xác nhận dữ liệu instance qua **jfr print** và cấu hình đã thu stack.

**Câu 5:** muốn xem GC lẫn CPULoad mà không in mọi event. Lệnh?  
**Đáp án:** **jfr print --categories GC --events jdk.CPULoad recording.jfr** (kết hợp là **union**, không phải intersection).

**Câu 6:** metadata không có file trên máy A khác với metadata trong recording từ máy B. Cách đọc nào phù hợp để hiểu chính recording?  
**Đáp án:** **jfr metadata recording.jfr**; đồng thời ghi producer JDK và reader JDK.

**Câu 7:** recording dài 30 giây, sự cố kéo dài 2 phút xảy ra 10 phút sau. Có thể suy nguyên nhân từ file này không?  
**Đáp án:** Không đủ cơ sở trực tiếp; cần recording phủ đúng khoảng sự cố hoặc nguồn dữ liệu khác tương quan.

## Tài liệu tham khảo

- [Oracle JDK 21 — The jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): cú pháp **summary, metadata, print, view**, bộ lọc và stack-depth.
- [Oracle JDK 17 — The jfr Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): bộ lệnh nền tảng khi dùng JDK 17.
- [Oracle JDK 21 — jdk.jfr package](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html): event model, annotations, settings và schema.
- [Oracle JDK 21 — Recording API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): tạo/enable/start/stop/dump recording.
- [Oracle JDK 21 — EventSettings API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): threshold, period và stackTrace.
- [Oracle dev.java — JFR command line tool](https://dev.java/learn/jvm/jfr/tools/): hướng dẫn chính thức thực hành từ file JFR.
