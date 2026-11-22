# Chọn loại sự kiện JFR phù hợp với câu hỏi cần đo (Java 17+)

## 1. Nguyên tắc: bắt đầu từ câu hỏi, không bắt đầu từ danh sách event

Java Flight Recorder (**JFR**) là công cụ ghi nhận sự kiện (event) tích hợp trong JVM, phục vụ phân tích hiệu năng, tài nguyên và hành vi runtime. Một recording có thể chứa nhiều loại thông tin: mẫu thực thi, tải CPU, garbage collection, cấp phát bộ nhớ, tranh chấp khóa, I/O, exception, sự kiện ứng dụng tự định nghĩa và nhiều loại khác.

Vấn đề thường gặp: **bật càng nhiều event càng tốt** rồi mở tệp `.jfr` và tìm bất kỳ biểu đồ nào có vẻ bất thường. Cách này dễ tạo dữ liệu dư thừa, tăng chi phí ghi nhận, khó xác định quan hệ nhân quả và bỏ lỡ event thực sự cần cho câu hỏi đang điều tra.

Quy trình tốt hơn:

1. Đặt **một câu hỏi đo được**: “CPU tăng vì đoạn mã nào?”, “Vì sao thời gian đáp ứng đôi lúc tăng?”, “GC có gây ra các khoảng dừng không?”, “Luồng nào bị chờ khóa?”.
2. Xác định **đại lượng cần quan sát**: tải CPU, stack sample, thời lượng pause, số byte/độ trễ I/O, thời gian monitor contention, số lượng allocation, v.v.
3. Chọn **event types hỗ trợ trực tiếp** đại lượng đó, rồi chỉ thêm event phụ giúp giải thích nguyên nhân.
4. Chọn **cửa sổ ghi**, `threshold`, `period`, stack traces và độ chi tiết phù hợp.
5. Thu thập trong **giai đoạn thật sự xảy ra vấn đề**, phân tích, đối chiếu với metric/log/tracing khác, và chỉ mở rộng event khi còn giả thuyết chưa kiểm tra.

**Ngữ cảnh phiên bản:** Java 14 có nhiều cải tiến liên quan quan sát và JFR, nhưng JFR vẫn là công cụ hiện hành trên các JDK hiện đại. Bài dùng các event và API **ổn định, phù hợp Java 17/21+**; không yêu cầu chế độ preview hoặc kiến thức legacy. Tập event cụ thể và mặc định có thể khác giữa phiên bản JVM, vendor và cấu hình recording; phải kiểm tra môi trường thực tế.

## 2. JFR event là gì, có những thuộc tính nào?

Một **event** là một bản ghi về một hoạt động hoặc trạng thái runtime. Nó có **event type** (ví dụ `jdk.CPULoad` hoặc `jdk.GarbageCollection`), thời điểm xảy ra và những trường do type đó định nghĩa. Một số event có **duration**, **thread**, **stack trace** hoặc các trường chỉ số như mức tải CPU, dữ liệu heap, lượng byte đọc/ghi.

Không phải mọi loại event đều giống nhau:

| Nhóm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Sample** | Lấy mẫu hoạt động theo tần suất, không ghi mọi lần gọi | `jdk.ExecutionSample` |
| **Periodic/statistical** | Ghi snapshot chỉ số theo chu kỳ | `jdk.CPULoad`, `jdk.ThreadCPULoad` |
| **Duration event** | Ghi hoạt động có thời điểm bắt đầu/kết thúc; thường có threshold | `jdk.SocketRead`, `jdk.JavaMonitorEnter` |
| **Lifecycle/count** | Ghi sự kiện đã xảy ra, hoặc tổng hợp theo chu kỳ | `jdk.GarbageCollection`, `jdk.ExceptionStatistics` |
| **Custom application event** | Gắn nghiệp vụ vào thời gian và thông tin runtime | `demo.WorkStep` do ứng dụng định nghĩa |

**Một event được bật không có nghĩa nhất định xuất hiện trong recording.** Có thể không có hoạt động thuộc loại đó, duration chưa đạt threshold, chu kỳ sampling chưa đủ dài hoặc giai đoạn recording không trùng thời điểm phát sinh vấn đề.

Ngược lại, **một loại event xuất hiện nhiều không tự chứng minh nó là nguyên nhân**. Cần xem thời điểm, duration, stack trace, event đi kèm và cơ sở so sánh.

## 3. Bảng chọn event theo câu hỏi thực tế

| Câu hỏi cần đo | Event bắt đầu nên xem | Event bổ sung nếu cần | Chú ý cách đọc |
| --- | --- | --- | --- |
| **CPU của JVM tăng lúc nào?** | `jdk.CPULoad` | `jdk.ThreadCPULoad`, `jdk.ExecutionSample` | CPU load cho biết mức sử dụng; không tự chỉ ra hàm gây ra |
| **Hàm/call stack nào hoạt động nhiều?** | `jdk.ExecutionSample` | `jdk.NativeMethodSample`, `jdk.CPULoad` | Mẫu stack cho xu hướng hotspot; không phải số lần gọi chính xác |
| **Dịch vụ chậm khi GC?** | `jdk.GarbageCollection`, `jdk.GCPhasePause` | `jdk.GCHeapSummary`, allocation events | So sánh khoảng pause và thời điểm latency tăng |
| **Bộ nhớ cấp phát ở đâu?** | `jdk.ObjectAllocationSample` | `jdk.ThreadAllocationStatistics` | Event sample giúp định vị nguồn; không phải kiểm kê mọi object |
| **Luồng chờ do `synchronized`?** | `jdk.JavaMonitorEnter` | `jdk.ThreadPark`, stack trace | Monitor contention khác với thread park và các dạng chờ khác |
| **Đọc mạng bị chậm?** | `jdk.SocketRead` | `jdk.SocketWrite`, custom request event | Thời gian socket I/O không tự chứng minh máy chủ bên kia chậm |
| **Đọc/ghi tệp chậm?** | `jdk.FileRead`, `jdk.FileWrite` | custom event theo tác vụ | Dùng thời gian, byte, file và luồng để nhận diện |
| **Exception xuất hiện bất thường?** | `jdk.ExceptionStatistics` | `jdk.JavaExceptionThrow` với thời gian/phạm vi giới hạn | Event từng lần throw có thể rất nhiều và tốn chi phí |
| **Khởi động/chạy tác vụ mất nhiều thời gian?** | `jdk.ExecutionSample`, `jdk.ClassLoad` | custom duration event | Cần thời điểm bắt đầu/kết thúc tác vụ để phân biệt các pha |

Đây là **gợi ý điểm xuất phát**, không phải danh sách mặc định phải bật cùng lúc. Một bài đo CPU có thể chỉ cần CPU load và execution samples; một bài đo latency do network lại cần socket events và dấu mốc request. Chọn dựa trên **giả thuyết đang kiểm tra**.

### Kiểm tra tên event trên JVM của bạn

Tên như `jdk.GarbageCollection` hay `jdk.ObjectAllocationSample` là tên event type, không phải tên class Java tùy ý. Khi chuyển sang JDK/vendor khác, hãy xác nhận sự kiện có sẵn và được hỗ trợ.

Có thể dùng JFR API:

```java
import jdk.jfr.FlightRecorder;
import jdk.jfr.EventType;

for (EventType type : FlightRecorder.getFlightRecorder().getEventTypes()) {
    if (type.getName().startsWith("jdk.")) {
        System.out.println(type.getName());
    }
}
```

Đây là **đoạn đặt trong một phương thức** của chương trình có JFR module; không phải lớp Java độc lập. Nó liệt kê các event type mà JFR runtime hiện tại biết. Danh sách cụ thể phụ thuộc runtime. Khi cần đọc metadata từ bản ghi, có thể dùng công cụ `jfr metadata` trong JDK nếu phiên bản công cụ hỗ trợ.

## 4. Ví dụ 1: CPU cao — ghép chỉ số CPU với mẫu thực thi

**Câu hỏi:** “Từ 14:00 đến 14:02, CPU của tiến trình tăng mạnh. Hàm nào hoạt động nhiều trong giai đoạn đó?”

Bắt đầu bằng:

- `jdk.CPULoad`: chỉ số tải CPU của JVM/máy theo thời gian.
- `jdk.ExecutionSample`: lấy mẫu stack hoạt động của các Java thread; dùng để nhận diện code path thường xuất hiện.
- `jdk.ThreadCPULoad`: giúp phân biệt những thread có mức dùng CPU đáng chú ý khi phiên bản/config có sự kiện này.

**Cách phân tích:** Tìm khoảng CPU cao, lọc mẫu thực thi trong khoảng ấy, nhóm theo stack/frame hoặc thread rồi so sánh với khoảng bình thường. Không kết luận rằng một hàm dùng đúng “40% CPU” chỉ vì chiếm 40% số event trong một tập chưa được chuẩn hóa: số mẫu, loại thread, cơ chế sampling và khoảng thời gian đều ảnh hưởng cách diễn giải.

Đừng bật toàn bộ allocation events chỉ vì thấy CPU cao; trước tiên cần bằng chứng CPU được dùng để cấp phát/GC nhiều hay chạy nghiệp vụ. Nếu nhiều GC event xuất hiện đồng thời, khi đó thêm event về GC và allocation sẽ có cơ sở.

## 5. Ví dụ 2: độ trễ ứng dụng tăng — cần cả event hạ tầng lẫn mốc nghiệp vụ

**Câu hỏi:** “Vì sao một API lâu lâu mất vài giây dù median nhanh?”

Có thể chia giả thuyết:

- **Chờ network:** xem `jdk.SocketRead` và `jdk.SocketWrite`.
- **Chờ file:** xem `jdk.FileRead` / `jdk.FileWrite`.
- **Tranh chấp monitor:** xem `jdk.JavaMonitorEnter`.
- **Thread park/chờ scheduler hoặc đồng bộ:** xem `jdk.ThreadPark`.
- **Dừng vì GC:** đối chiếu `jdk.GarbageCollection` và `jdk.GCPhasePause`.
- **CPU-bound:** đối chiếu `jdk.ExecutionSample` và CPU load.

Tuy nhiên, sự kiện JFR ở cấp JVM không nhất thiết biết **request ID** hoặc ranh giới của mỗi HTTP request. Muốn trả lời câu hỏi *request nào chậm*, nên bổ sung:

1. Custom JFR event cho một pha nghiệp vụ có duration, ví dụ `demo.WorkStep`.
2. Request tracing/log/metric ngoài JFR để liên kết giai đoạn người dùng cảm nhận độ trễ với giai đoạn runtime.
3. Đồng bộ hóa khoảng thời gian và định danh cần thiết, tránh ghi thông tin nhạy cảm không cần thiết.

**Không đánh đồng `jdk.SocketRead` có duration dài với “đường truyền chậm”.** Duration đó mô tả thời gian liên quan thao tác đọc; phải kiểm tra đặc điểm tải, lượng byte, thời điểm và logic ứng dụng. Tương tự `jdk.ThreadPark` mô tả việc park, nhưng lý do chờ có thể là cơ chế đồng bộ bình thường chứ chưa chắc là lỗi.

## 6. Ví dụ 3: GC và áp lực cấp phát — hai câu hỏi khác nhau

**Câu hỏi A:** “GC có gây ra những khoảng dừng làm latency tăng không?”

Ưu tiên:

- `jdk.GarbageCollection` để theo dõi các lần GC.
- `jdk.GCPhasePause` để xem những pha dừng phù hợp với collector/runtime.
- `jdk.GCHeapSummary` để nhìn thay đổi trạng thái heap quanh các sự kiện được ghi.

So sánh **thời điểm pause** với **spike latency**. Một JVM có nhiều sự kiện GC không đồng nghĩa tất cả chúng đều tạo ra pause dài; cần xét collector, pause duration, và bối cảnh ứng dụng.

**Câu hỏi B:** “Hàm nào tạo nhiều đối tượng khiến allocation rate cao?”

Ưu tiên `jdk.ObjectAllocationSample` (nếu có trên JVM sử dụng) để lấy **mẫu nguồn cấp phát**, hoặc `jdk.ThreadAllocationStatistics` cho số liệu tổng hợp theo thread. Nếu cần đo chi tiết hơn, có thể xem các sự kiện allocation chuyên biệt như `jdk.ObjectAllocationInNewTLAB` và `jdk.ObjectAllocationOutsideTLAB` khi môi trường hỗ trợ và sau khi đánh giá overhead.

**Phân biệt:**

- Sample allocation **không** cho biết chính xác mọi đối tượng từng được tạo.
- Allocation rate cao **không** tự chứng minh memory leak.
- Memory leak cần thêm bằng chứng về đối tượng giữ sống, xu hướng heap sau GC và phân tích phù hợp; JFR allocation samples chủ yếu giúp tìm nơi cấp phát.

## 7. Ví dụ 4: khóa và tranh chấp thread

**Câu hỏi:** “Các request chờ nhau khi nhiều luồng cùng sửa tài nguyên?”

Sự kiện đầu tiên thường là `jdk.JavaMonitorEnter`, báo các lần cố vào monitor gây **contention** và đạt điều kiện ghi. Khi chọn threshold, ví dụ `20 ms`, ta tập trung vào những lần chờ đủ dài để ảnh hưởng latency.

Có thể thêm:

- `jdk.ThreadPark` khi luồng thường park qua `LockSupport` hoặc cơ chế đồng bộ sử dụng nó.
- Stack traces để xác định code path dẫn tới chờ.
- Custom event cho pha request, để gắn một lần chờ dài với tác vụ đang thực thi.

**Bẫy:** Không phải mọi lần đi vào khối `synchronized` đều tạo `jdk.JavaMonitorEnter` event; event này tập trung vào **monitor contention** theo cấu hình, không đếm mọi lần vào monitor thành công. Một luồng ở trạng thái `WAITING` không tự động chứng minh deadlock. Nếu nghi deadlock, dùng thêm thread dump và công cụ chẩn đoán thích hợp, thay vì suy luận chỉ từ một loại event.

## 8. Ba nút điều chỉnh quan trọng: enabled, threshold, period

Một event type thường có **settings**. Một số settings phổ biến:

| Setting | Ý nghĩa | Khi điều chỉnh |
| --- | --- | --- |
| `enabled` | Có ghi type này hay không | Tắt nhóm không liên quan, bật nhóm phục vụ giả thuyết |
| `threshold` | Duration tối thiểu để một **duration event** được ghi | Chọn theo độ trễ có ý nghĩa; threshold cao có thể bỏ lỡ thao tác ngắn nhưng lặp rất nhiều |
| `period` | Khoảng thời gian giữa các lần ghi/sampling cho event phù hợp | Chu kỳ ngắn giúp quan sát chi tiết hơn nhưng có thể làm tăng khối lượng |
| `stackTrace` | Có kèm stack trace nếu event hỗ trợ | Bật khi cần quy về code path; có thêm overhead và dữ liệu |
| `cutoff` | Cấu hình liên quan duration trong một số event/settings | Không phải event nào cũng có; kiểm tra metadata của loại event cụ thể |

**Không phải mọi event đều hỗ trợ hoặc cần mọi setting.** Ví dụ `jdk.CPULoad` phù hợp với `period`, còn `jdk.JavaMonitorEnter` phù hợp với `threshold`. Không áp dụng một setting chung cho mọi type rồi nghĩ kết quả chắc chắn như nhau.

Ví dụ ứng dụng JFR API:

```java
recording.enable("jdk.CPULoad")
         .withPeriod(java.time.Duration.ofSeconds(1));

recording.enable("jdk.JavaMonitorEnter")
         .withThreshold(java.time.Duration.ofMillis(20))
         .withStackTrace();
```

Đoạn trên nằm trong một phương thức có biến `recording` kiểu `jdk.jfr.Recording`, không phải một chương trình độc lập. Nó minh họa **chọn riêng cách thu thập** cho hai loại event.

### Chọn ngưỡng để trả lời câu hỏi, không để làm đẹp số liệu

Nếu vấn đề là request đôi khi mất `1 s`, ngưỡng sự kiện socket `20 ms` có thể hữu ích để lọc những lần đọc chậm. Nhưng nếu vấn đề là `1000` thao tác `1 ms` cộng dồn, ngưỡng `20 ms` sẽ bỏ qua toàn bộ những thao tác đó. Cần xem **cơ chế gây chậm là vài lần đắt hay nhiều lần nhỏ** trước khi đặt threshold.

Sampling cũng tương tự: chu kỳ thưa bỏ lỡ hoạt động ngắn; chu kỳ dày có thể tăng overhead và kích thước recording. Không có một thiết lập luôn đúng cho mọi môi trường.

## 9. Cấu hình record có mục tiêu bằng API JFR

Ví dụ Java 17+ sau tạo một recording chỉ bật các loại event cần cho giả thuyết về **CPU, GC và monitor contention**, cộng thêm **custom event** mô tả một pha xử lý nghiệp vụ. Sau đó chương trình tự đọc recording để xác nhận custom event được lưu.

**Tệp `Main.java`:**

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class Main {
    @Name("demo.WorkStep")
    @Label("Work Step")
    static class WorkStep extends Event {
        @Label("Operation")
        String operation;
        @Label("Items")
        int items;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("targeted.jfr");
        try (Recording recording = new Recording()) {
            recording.enable(WorkStep.class)
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();
            recording.enable("jdk.CPULoad")
                    .withPeriod(Duration.ofSeconds(1));
            recording.enable("jdk.GarbageCollection");
            recording.enable("jdk.JavaMonitorEnter")
                    .withThreshold(Duration.ofMillis(20))
                    .withStackTrace();

            recording.start();

            WorkStep event = new WorkStep();
            event.operation = "validate";
            event.items = 3;
            event.begin();

            long sum = 0;
            for (int i = 0; i < 100_000; i++) {
                sum += i;
            }
            if (sum < 0) {
                throw new IllegalStateException();
            }

            event.end();
            event.commit();
            recording.stop();
            recording.dump(output);
        }

        List<RecordedEvent> all = RecordingFile.readAllEvents(output);
        long count = all.stream()
                .filter(e -> e.getEventType().getName().equals("demo.WorkStep"))
                .count();
        RecordedEvent step = all.stream()
                .filter(e -> e.getEventType().getName().equals("demo.WorkStep"))
                .findFirst().orElseThrow();

        System.out.println("CUSTOM_COUNT=" + count);
        System.out.println("OPERATION=" + step.getString("operation"));
        System.out.println("ITEMS=" + step.getInt("items"));
        System.out.println("DURATION_VALID=" + !step.getDuration().isNegative());
        System.out.println("FILE_EXISTS=" + (Files.size(output) > 0));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

**Stdout đã kiểm chứng:**

```text
CUSTOM_COUNT=1
OPERATION=validate
ITEMS=3
DURATION_VALID=true
FILE_EXISTS=true
```

Chương trình tạo tệp `targeted.jfr` trong thư mục làm việc hiện tại. Đây là dữ liệu chẩn đoán: hãy quản lý vòng đời và quyền truy cập của tệp khi chạy trên hệ thống thật.

**Phân tích cơ chế:**

1. `recording.enable(WorkStep.class)` chỉ định loại event ứng dụng `demo.WorkStep`. `begin()`/`end()` đo thời lượng pha xử lý và `commit()` ghi event vào JFR.
2. `recording.enable("jdk.CPULoad").withPeriod(...)` cho phép có dữ liệu CPU trong khoảng recording **nếu event được phát sinh**. Vì chương trình chạy nhanh hơn một giây, có thể không có `jdk.CPULoad` event thực tế trong tệp; đây **không phải lỗi**.
3. `jdk.GarbageCollection` và `jdk.JavaMonitorEnter` được bật nhưng có thể không xảy ra trong ca ví dụ. Tránh viết test yêu cầu mọi loại event đều có ít nhất một bản ghi.
4. `RecordingFile.readAllEvents` đọc dữ liệu từ file và lọc bằng **tên event type** để lấy custom event. Với recording rất lớn, việc tải toàn bộ event vào bộ nhớ có thể tốn tài nguyên; khi phân tích bản ghi lớn, cân nhắc API đọc tuần tự hoặc công cụ phân tích JFR.
5. `DURATION_VALID=true` chỉ xác nhận duration không âm; nó **không** khẳng định pha nghiệp vụ đủ lâu để coi là vấn đề hiệu năng. Cần số liệu cơ sở, so sánh và giả thuyết thực tế.

Những annotation `@Name`, `@Label` và API từ `jdk.jfr` là cơ chế hiện hành để tự định nghĩa event. Thay vì ghi mọi thông tin nghiệp vụ, chỉ nên ghi các trường phục vụ đo lường; tránh đưa mật khẩu, token hoặc dữ liệu cá nhân không cần thiết vào event.

## 10. Thu thập trên JVM đang chạy bằng công cụ `jcmd` và `jfr`

Không bắt buộc sửa code để bắt đầu một phép đo. Trên JDK có công cụ `jcmd`, trước tiên xác định PID của Java process:

```bash
jcmd -l
```

Giả sử Java process mục tiêu trong ví dụ có PID `4242`. Để ghi trong 60 giây bằng cấu hình profiling tiêu chuẩn:

```bash
jcmd 4242 JFR.start name=investigate settings=profile duration=60s filename=investigate.jfr
```

Với mục tiêu production, hãy **đánh giá overhead** và chính sách vận hành trước khi chọn `settings=profile`; không coi đây là cấu hình mặc định an toàn cho mọi workload. JDK có các cấu hình tích hợp như `default` và `profile`, còn bộ sự kiện và settings thực tế có thể khác giữa các phiên bản.

Trong lúc recording chạy, có thể xem trạng thái:

```bash
jcmd 4242 JFR.check
```

Nếu cần chụp dữ liệu khi recording còn hoạt động, có thể dùng `JFR.dump` với tên recording tương ứng và đường dẫn tệp phù hợp:

```bash
jcmd 4242 JFR.dump name=investigate filename=investigate-now.jfr
```

Cú pháp trên minh họa quy trình; PID `4242` chỉ là số ví dụ, cần thay bằng PID thực tế lấy từ `jcmd -l`. Khả năng attach còn phụ thuộc quyền hệ điều hành, phiên bản công cụ và cấu hình tiến trình.

Khi đã có file, xem **tóm tắt số lượng event** rồi lọc những type phục vụ câu hỏi:

```bash
jfr summary investigate.jfr
jfr print --events jdk.CPULoad,jdk.ExecutionSample investigate.jfr
```

`jfr summary` giúp nhìn thấy loại event, số lượng và kích thước trong recording. `jfr print --events ...` chọn những event type để xem chi tiết. Các công cụ JFR có thể cung cấp thêm cách xem/hiển thị, nhưng không cần liệt kê toàn bộ JFR ngay từ đầu.

### Lưu ý về output

Không có stdout cố định cho `jcmd JFR.start` hoặc `jfr summary` trong mọi máy. PID, thời gian ghi, CPU, hoạt động thread, dung lượng, số lượng và thứ tự sự kiện phụ thuộc **ứng dụng thực tế**. Không sao chép output mẫu rồi coi là kết quả phải xuất hiện ở mọi lần đo.

## 11. Cách xác định event nào thực sự cần bật

Để giảm rủi ro ghi dữ liệu vô ích, hãy viết một bảng đo nhỏ trước khi bật recording:

| Thành phần quyết định | Câu hỏi cần trả lời |
| --- | --- |
| **Mục tiêu** | Người dùng thấy chậm, CPU cao, bộ nhớ tăng hay có deadlock? |
| **Metric quan sát** | Latency, CPU%, duration GC pause, byte I/O, thời gian tranh chấp? |
| **Event chính** | Type nào đo trực tiếp chỉ số đó? |
| **Event giải thích** | Cần stack trace, allocation sample, custom event hay correlation timestamp nào? |
| **Phạm vi** | Một request, một phút cao điểm, vài chu kỳ GC hay giai đoạn startup? |
| **Độ phân giải** | Sampling `period` và duration `threshold` nào đủ để nhận diện hiện tượng? |
| **Chi phí** | Dung lượng, overhead, dữ liệu nhạy cảm, khả năng lưu trữ/thu thập? |
| **Tiêu chí kết luận** | Quan sát nào xác nhận hoặc bác bỏ giả thuyết ban đầu? |

Ví dụ một phép đo có chủ đích:

- **Giả thuyết:** API chậm do cạnh tranh trên monitor.
- **Event chính:** `jdk.JavaMonitorEnter` với threshold phục vụ latency đang điều tra.
- **Event phụ:** custom event ghi duration của pha API, có thể thêm `jdk.ThreadPark` nếu nghi chờ qua park.
- **Phân tích:** tìm những lần chờ dài trùng khoảng API chậm, kiểm tra stack trace của luồng bị chờ; nếu không thấy bằng chứng, chuyển sang kiểm tra network/GC/CPU.
- **Không bắt đầu bằng:** bật exception throw, mọi allocation event, class loading và file I/O cùng lúc nếu chưa có giả thuyết liên quan.

## 12. Phân tích kết quả và tránh kết luận sai

### 12.1. Nhìn tỷ lệ, thời gian và tương quan

Một event duration dài không luôn tạo ra toàn bộ thời gian chậm của request; một request có thể đồng thời có network, CPU và GC. Nên:

1. Chọn **cửa sổ thời gian có vấn đề**.
2. Đối chiếu các event cùng thời gian.
3. Kiểm tra stack trace/luồng hoặc custom marker liên quan.
4. So sánh với **cửa sổ bình thường** có tải tương tự.
5. Kiểm tra lại sau thay đổi hệ thống.

### 12.2. Không coi số mẫu là số lần thực thi

`jdk.ExecutionSample` không ghi tất cả method invocations. Nhiều mẫu ở một frame cho thấy frame xuất hiện thường xuyên trong các thời điểm lấy mẫu; không phải “phương thức được gọi đúng N lần”. Với allocation samples cũng tương tự: số mẫu không bằng tổng số object được tạo.

### 12.3. Không coi vắng event là không có vấn đề

`jdk.SocketRead` có thể không ghi một lần đọc nhanh vì threshold; `jdk.CPULoad` có thể không xuất hiện nếu recording ngắn hơn period; GC event vắng mặt có thể đơn giản vì chưa có GC trong cửa sổ ấy. Trước khi kết luận “không xảy ra”, kiểm tra **type đã bật chưa, event có hỗ trợ trên runtime không, threshold/period và recording window**.

### 12.4. Chi phí và độ tin cậy

JFR được thiết kế để thu thập sự kiện với overhead thấp trong các cấu hình phổ biến, nhưng **không phải mọi type/settings đều miễn phí**. Ghi các sự kiện xảy ra rất thường xuyên, stack trace sâu hay exception throw ở tải lớn có thể làm tăng overhead và dung lượng. Cần thử với workload đại diện.

Một bản recording cũng chưa phải bằng chứng tự đủ cho nguyên nhân gốc. Tình huống CPU cao có thể liên quan GC, JIT compilation, ứng dụng hoặc native code; tình huống latency có thể liên quan hệ thống ngoài JVM. Dùng JFR như một phần trong hệ thống quan sát, không thay metric, log, distributed trace và benchmark.

## 13. Lỗi thường gặp khi chọn sự kiện

| Sai lầm | Vì sao dẫn đến kết luận sai | Cách sửa |
| --- | --- | --- |
| Bật tất cả event trước khi đặt câu hỏi | Dữ liệu lớn, nhiều nhiễu, overhead khó kiểm soát | Chọn một giả thuyết và 2–4 event quan trọng trước |
| Muốn biết hotspot nhưng chỉ xem `jdk.CPULoad` | Chỉ có chỉ số CPU, thiếu stack | Thêm `jdk.ExecutionSample` và lọc theo thời gian |
| Muốn biết nguồn allocation nhưng chỉ xem heap size | Heap tổng quan không chỉ nơi tạo object | Thêm `jdk.ObjectAllocationSample` phù hợp |
| Coi mọi `jdk.GarbageCollection` là pause dài | Không phân biệt collector/pha/duration | Xem `jdk.GCPhasePause` và đối chiếu latency |
| Coi `jdk.JavaMonitorEnter` đếm mọi `synchronized` | Nó tập trung vào contention được ghi | Xem threshold và dạng chờ cụ thể |
| Không thấy `jdk.SocketRead` nên kết luận không I/O | Có thể event tắt, threshold cao hoặc không trùng cửa sổ | Kiểm tra settings, period, loại I/O và workload |
| Coi số event `jdk.ExecutionSample` là số lần gọi | Đây là mẫu, không phải trace từng invocation | Dùng phân tích tỷ lệ mẫu và các số đo bổ sung |
| Bật `jdk.JavaExceptionThrow` ở mọi workload không kiểm soát | Event có thể rất nhiều | Bắt đầu từ thống kê hoặc recording ngắn |
| Mặc định event type luôn có trên mọi JDK | JVM/vendor/phiên bản có thể khác | Kiểm tra API/metadata trên môi trường đo |
| Chỉ ghi khi không có tải | Không thấy vấn đề chỉ xuất hiện giờ cao điểm | Chọn recording window đúng thời điểm |
| Tạo JFR lớn rồi tải toàn bộ vào heap phân tích | Tốn bộ nhớ, tăng thời gian xử lý | Dùng công cụ lọc/stream khi phân tích dữ liệu lớn |
| Ghi ID/token người dùng vào event | Có nguy cơ lộ thông tin trong tệp phân tích | Giới hạn trường và phân quyền tệp chẩn đoán |

## 14. Tự kiểm tra

**Câu 1.** CPU JVM tăng, bạn nên bắt đầu bằng `jdk.SocketRead` hay `jdk.CPULoad` và `jdk.ExecutionSample`?

**Đáp án:** Bắt đầu bằng CPU load để biết *khi nào/bao nhiêu*, execution samples để tìm *code path nào* hoạt động nhiều. Socket event chỉ thêm khi có giả thuyết về I/O.

**Câu 2.** Vì sao không dùng chỉ số `jdk.GCHeapSummary` để khẳng định một object bị leak?

**Đáp án:** Heap summary phản ánh trạng thái heap, không xác định chính xác object nào bị giữ sống và tại sao. Cần phân tích sự tồn tại/retention của object và thêm bằng chứng phù hợp.

**Câu 3.** `jdk.JavaMonitorEnter` không xuất hiện sau 10 giây ghi. Có thể khẳng định chương trình không bao giờ tranh chấp khóa không?

**Đáp án:** Không. Kiểm tra event đã bật chưa, threshold là bao nhiêu, recording có trúng lúc tranh chấp không và dạng khóa/chờ có thật sự được type này phản ánh không.

**Câu 4.** Mỗi `jdk.ObjectAllocationSample` có đại diện cho chính xác một object trong toàn bộ chương trình không?

**Đáp án:** Không. Đó là cơ chế lấy mẫu, không phải nhật ký đầy đủ mọi allocation.

**Câu 5.** Nếu quan tâm duration của một pha nghiệp vụ riêng mà event JVM không biết, làm thế nào?

**Đáp án:** Tạo custom JFR duration event (hoặc bổ sung dấu mốc phù hợp), ghi tên pha và chỉ số tối thiểu cần thiết, sau đó đối chiếu với event JVM trong cùng khoảng thời gian.

**Ghi nhớ:** Chọn JFR event **theo câu hỏi đo**, sau đó mới đặt `enabled`, `period`, `threshold` và stack trace. Kết hợp một số **event chính** với **event giải thích** và **mốc nghiệp vụ**, phân tích trong đúng cửa sổ có vấn đề, kiểm tra metadata/cấu hình thực tế rồi xác nhận giả thuyết. JFR là nguồn bằng chứng mạnh, nhưng không thay thế phương pháp đo lường và đối chiếu.

### Tài liệu tham khảo chính thức

- [JDK Flight Recorder API — Package `jdk.jfr`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- [JDK Flight Recorder consumer API — `RecordingFile`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- [Java SE — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Java `jcmd` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Java `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
