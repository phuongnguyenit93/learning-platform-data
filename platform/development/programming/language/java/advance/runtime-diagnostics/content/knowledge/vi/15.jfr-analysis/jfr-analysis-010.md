# 15.10 Giới hạn của lấy mẫu và ngưỡng event; tương quan thời gian không tự chứng minh quan hệ nhân quả

## 1. Mục tiêu: biết JFR đã quan sát gì trước khi suy luận vì sao

**Java Flight Recorder (JFR)** cho phép quan sát CPU, allocation, GC, lock, I/O, thread và sự kiện riêng của ứng dụng. Tuy nhiên, một tệp `.jfr` **không phải bản ghi đầy đủ mọi thao tác đã xảy ra**. Một số loại event được phát ra theo lần xảy ra, một số chỉ xuất hiện sau khi vượt **ngưỡng thời lượng** (`threshold`), một số được **lấy mẫu** (`sampling`), và một số xuất hiện theo **chu kỳ** (`period`). Chưa kể event có thể bị tắt, thiếu stack trace, nằm ngoài cửa sổ ghi hoặc bị mất trong điều kiện tài nguyên bất lợi.

Khi thấy biểu đồ JFR ghi “GC pause tăng cùng lúc latency tăng” hoặc “method X chiếm 40% mẫu”, cần tách ba cấp độ kết luận:

1. **Quan sát:** dữ liệu có gì? Loại event nào, mẫu nào, thời điểm nào, cấu hình ra sao?
2. **Giả thuyết cơ chế:** có phải một đường thực thi, một nguồn tải hay một sự kiện khác cùng gây ra hai hiện tượng?
3. **Quan hệ nhân quả:** thay đổi nguyên nhân được giả định, trong điều kiện kiểm soát hợp lý, có thực sự làm thay đổi kết quả và lặp lại được không?

Mục tiêu bài này là đọc đúng độ tin cậy của JFR: phân biệt mẫu với số lần gọi, nhận diện sai lệch do ngưỡng event, ghép sự kiện theo thời gian mà không “kết án” từ trùng timestamp, và thiết kế phép kiểm chứng có phản chứng.

Phạm vi kỹ thuật: Java 17+ trên HotSpot, minh họa bằng JDK 21. Tên loại event và cấu hình mẫu có thể thay đổi theo bản JDK/JVM và file `.jfc`; xác nhận cấu hình **thực tế** trước khi phân tích.

## 2. Bốn kiểu quan sát dễ bị đánh đồng

| Cách thu thập | Ví dụ JFR | Event xuất hiện khi nào? | Không được suy ra |
| --- | --- | --- | --- |
| **Event theo lần xảy ra** | `jdk.ThreadStart`, event do ứng dụng `commit()` | Khi event được bật và việc ghi thành công | Mọi action trong hệ thống đều có một event tương ứng. |
| **Duration event có threshold** | `jdk.JavaMonitorEnter`, `jdk.ThreadSleep`, custom event có `begin()/end()` | Event có thời lượng thỏa ngưỡng cấu hình | Các thao tác vắng mặt không xảy ra. |
| **Sampling/profiling event** | `jdk.ExecutionSample`, `jdk.NativeMethodSample`, `jdk.ObjectAllocationSample` | Công cụ ghi một quan sát được lấy mẫu từ hoạt động, theo chính sách của loại event | Số sample bằng số lời gọi, số allocation hoặc tổng thời gian CPU chính xác. |
| **Periodic event** | Một số thống kê thread/CPU/JVM định kỳ | Mỗi lần điểm thu thập định kỳ đến hạn | Có một event cho mỗi lần biến động, mọi biến động giữa các điểm đều được nhìn thấy. |

Các event dạng instant, duration, periodic, sampling khác nhau về **mẫu số**. Nếu một bảng của JDK Mission Control (JMC) trộn nhiều event, phải đọc tên event và setting trước khi lấy tần suất hay quy tỷ lệ.

Ví dụ:

- 500 `jdk.ExecutionSample`: khoảng 500 quan sát thực thi trong điều kiện recorder thu được mẫu, **không phải** 500 lần method được gọi.
- 20 `jdk.JavaMonitorEnter` với `threshold=20 ms`: 20 lần chờ monitor **được ghi** và thỏa ngưỡng. Không chứng minh cả ứng dụng chỉ xảy ra 20 lần lock contention.
- 30 event kiểu periodic ở khoảng 1 giây: 30 mốc thống kê; không có nghĩa chỉ xảy ra 30 thay đổi trong JVM.
- 0 event một loại có thể đơn giản vì `enabled=false` hoặc threshold cao; không đủ để kết luận hoạt động tương ứng bằng 0.

## 3. Kiểm tra cấu hình event trước khi đọc kết quả

JFR có các setting cơ bản được định nghĩa trong API `jdk.jfr`:

| Setting | Ý nghĩa | Câu hỏi nên hỏi |
| --- | --- | --- |
| `enabled` | Có thu event này hay không | Event có được bật trong recording đang phân tích? |
| `threshold` | Duration thấp hơn ngưỡng sẽ không được ghi với event hỗ trợ threshold | Có bao nhiêu hoạt động ngắn bị lọc? |
| `period` | Tần suất hoặc thời điểm dự kiến cho periodic/sampled event phù hợp | Khoảng lấy mẫu có đủ để nhìn hiện tượng ngắn? |
| `stackTrace` | Có thu stack trace cho event hay không | Thiếu stack trace là do cấu hình hay do không lấy được? |

Không phải event nào cũng dùng đủ bốn setting. Chẳng hạn `jdk.ExecutionSample` dùng chính sách lấy mẫu; cố đặt `threshold` cho event này không biến nó thành bộ đo thời lượng của **mọi** method. Với duration event, `threshold` có ý nghĩa; với event instant, nó không tự tạo thông tin thời lượng.

Tài liệu `jdk.jfr` mô tả mặc định *theo cơ chế setting*, nhưng **giá trị đang dùng được quyết định bởi file cấu hình và các ghi đè**. Không nên ghi trong báo cáo “threshold mặc định của event là 0” nếu file `default.jfc` hoặc `profile.jfc` đã đặt 20 ms. Trên JDK 21, các profile đi kèm thường đặt ngưỡng cho những event như `jdk.JavaMonitorEnter` hoặc `jdk.ThreadSleep` và period cho `jdk.ExecutionSample`; các giá trị này là **cấu hình**, không phải định luật của JVM.

Cách xem trên JVM đang chạy, dùng PID thực tế thay `12345`:

```bash
jcmd -l
jcmd 12345 JFR.check verbose=true
```

`JFR.check verbose=true` giúp xem setting của recording hiện có. Sau khi có tệp kết quả, kiểm tra loại event:

```bash
jfr summary incident.jfr
jfr metadata incident.jfr
```

`jfr summary` cho số event và phạm vi thời gian trong file; `jfr metadata` cho thông tin về kiểu event/trường dữ liệu. Chúng không tự thay thế việc biết cấu hình `.jfc` đã áp dụng. Lưu lại `default`, `profile` hay đường dẫn custom `.jfc`, cùng mọi ghi đè qua `JFR.start`, `-XX:StartFlightRecording` hoặc API `Recording`.

## 4. Threshold: bộ lọc thời lượng, không phải sự thật về toàn bộ request

Giả sử có năm thao tác thực tế với thời lượng **đã đo độc lập**:

| Lần | Thời lượng | `threshold=0 ms` | `threshold=20 ms` | `threshold=50 ms` |
| --- | ---: | --- | --- | --- |
| A | 3 ms | Đủ điều kiện | Bị lọc | Bị lọc |
| B | 9 ms | Đủ điều kiện | Bị lọc | Bị lọc |
| C | 25 ms | Đủ điều kiện | Đủ điều kiện | Bị lọc |
| D | 32 ms | Đủ điều kiện | Đủ điều kiện | Bị lọc |
| E | 70 ms | Đủ điều kiện | Đủ điều kiện | Đủ điều kiện |

Với threshold 20 ms, JFR chỉ có cơ hội ghi **ba event chậm** của ví dụ. Số lần gọi thực tế vẫn là **năm**. Dữ liệu thu được bị **selection bias**: tập quan sát thiên về những thao tác lâu hơn.

Nếu tính trung bình từ ba event còn lại:

```text
Trung bình THỰC TẾ của 5 thao tác = (3 + 9 + 25 + 32 + 70) / 5 = 27.8 ms
Trung bình 3 event qua ngưỡng 20 ms = (25 + 32 + 70) / 3 ≈ 42.3 ms
```

Con số `42,3 ms` là trung bình **có điều kiện trên tập event được ghi**, không thể được dùng làm latency trung bình mọi request. Ngược lại, đếm “ba event chậm” không chứng minh chỉ ba request xảy ra hoặc toàn bộ service đã xử lý ba request.

**Hệ quả quan trọng:**

- `threshold=20ms` hữu ích khi mục tiêu là **chẩn đoán các lần chậm bất thường**, không phù hợp để đo toàn bộ latency distribution.
- Không lấy số event chậm chia cho tổng số event JFR để gọi là “tỷ lệ request chậm”: mẫu số phải là **tổng request thực tế** từ metric/đếm độc lập phù hợp.
- Nếu thay threshold từ 50 ms xuống 10 ms, số event tăng ngay cả khi ứng dụng **không hề chậm đi**.
- Với event stack trace, giảm threshold quá sâu có thể làm tăng chi phí ghi/dung lượng dữ liệu. Chọn ngưỡng theo câu hỏi và kiểm thử overhead.
- Event phải kết thúc và được ghi trong cửa sổ recording phù hợp; một công việc còn dang dở khi file đã kết thúc có thể chưa tạo event hoàn chỉnh để phân tích.

Điểm bằng ngưỡng và cách biểu diễn thời lượng ở ranh giới nhỏ có thể chịu ảnh hưởng độ phân giải/timestamp. Không diễn giải sự khác biệt vài microgiây thành một thay đổi hành vi lớn khi hệ thống có scheduler/GC jitter.

## 5. Sampling: ảnh chụp theo thời điểm không phải kiểm kê mọi lời gọi

Với **execution sampling**, recorder quan sát một số trạng thái thread/stack trong khoảng thời gian để thấy **hot paths**. Một lời gọi chạy rất nhanh có thể không xuất hiện trong bất cứ sample nào. Một method giữ CPU lâu có thể xuất hiện trong nhiều sample dù nó chỉ được gọi một lần.

### Ví dụ tư duy

Một thread chạy tuần tự:

```text
0 ms        2 ms                  20 ms
| method A |------- method B -------|
           ^                       ^
        A rất ngắn             B tương đối dài

Các thời điểm sample dự kiến: 0, 20, 40, 60 ms, ...
```

Tùy vị trí tương đối của các điểm sample và tiến trình, method A dài 2 ms dễ bị bỏ qua, còn method B dài 18 ms có khả năng xuất hiện hơn. Điều đó **không có nghĩa** A ít được gọi hơn B. Nếu A được gọi rất thường xuyên nhưng mỗi lần cực ngắn, số lần gọi và sample percentage vẫn có thể khác nhau rất xa.

Theo mô hình **giả định đơn giản** có thời điểm sample phân bố đều ngẫu nhiên trên khoảng `T` và một hoạt động không chồng lấn kéo dài `d<T`, xác suất bắt trúng một lần có thể xấp xỉ `d/T`. Ví dụ `d=2 ms`, `T=20 ms` ⇒ khoảng 10%. Đây là **mô hình trực giác**, không phải công thức hiệu chuẩn chính xác cho sampler của HotSpot: scheduling, collector, safepoint, trạng thái thread, stack availability, bias và mất mẫu đều có thể làm khác.

### Những sai lệch điển hình

1. **Short-lived operation:** đoạn thực thi vài microgiây có thể vắng mặt dù tổng số lần gọi rất nhiều.
2. **Sampling bias:** thread/state dễ được quan sát có thể xuất hiện nhiều; thời gian mẫu không nhất thiết đồng nhất với CPU time trên mọi JVM/cấu hình.
3. **Aliasing:** nếu chu kỳ sample trùng nhịp với workload định kỳ, có thể thấy quá nhiều hoặc quá ít một pha của ứng dụng.
4. **Thời gian ngắn:** chỉ 10 mẫu trong một phút không đủ kết luận phân bố các method hiếm.
5. **Chi phí/khả năng lấy stack:** stack trace có thể thiếu, bị giới hạn độ sâu, bị truncated hoặc việc lấy mẫu thất bại.
6. **Chế độ recording:** `default`, `profile`, custom settings có thể bật/tắt và đổi period của sampler; kết quả không so được trực tiếp khi cấu hình thay đổi.
7. **Thread khác nhau:** hotspot theo số mẫu có thể do một thread chi phối; cần nhìn thread/group và workload khi kết luận cho cả service.
8. **Tỷ lệ mẫu:** “40% samples ở method X” là tỷ lệ trong **các mẫu có được**, không chứng minh X chiếm chính xác 40% wall-clock time, request time hoặc toàn bộ CPU ở mọi thread.

`jdk.ObjectAllocationSample` cũng là **mẫu allocation**, không phải danh sách đầy đủ mọi lần `new`. Một event có thể mang trọng số/ước lượng để suy ra áp lực allocation; cần đọc rõ cách công cụ/JMC tổng hợp, đừng coi từng sample bằng đúng một object mới hoặc một byte cấp phát.

## 6. Period không tương đương threshold

`period` đặt khoảng/tần suất dự kiến đối với event có cơ chế định kỳ hoặc lấy mẫu; `threshold` lọc **theo thời lượng của event**. Đổi period 20 ms thành 10 ms có thể tăng số điểm quan sát, nhưng không làm một duration event 5 ms tự xuất hiện nếu threshold của nó vẫn là 20 ms.

| Tình huống | Điều bị thay đổi | Điều **không** thể tự suy ra |
| --- | --- | --- |
| `jdk.ExecutionSample#period=20ms` → `10ms` | Mật độ thời điểm lấy mẫu mong muốn | Số sample tăng đúng 2 lần hoặc kết quả CPU chính xác hơn gấp đôi |
| `jdk.JavaMonitorEnter#threshold=20ms` → `5ms` | Chấp nhận thêm các lần monitor enter ngắn hơn | Lock contention đã tăng |
| `jdk.ThreadSleep#enabled=false` → `true` | Bắt đầu thu sleep event phù hợp | Ngủ nhiều hơn so với trước |
| `stackTrace=false` → `true` | Bổ sung attribution cho event | Sự kiện hoặc thời lượng đã tăng |
| `settings=default` → `profile` | Gói event và chính sách thu khác nhau | Ứng dụng chậm đi chỉ vì lượng event nhiều hơn |

Một periodic event xuất ra mỗi 5 giây không tái dựng được những đỉnh cao kéo dài 100 ms giữa hai lần ghi. Đây là **giới hạn độ phân giải theo thời gian**, không phải lỗi vẽ biểu đồ.

## 7. Kiểm tra chất lượng dữ liệu JFR trước khi tính toán

Đừng bắt đầu từ biểu đồ nóng nhất. Trước tiên xác nhận “khung quan sát”:

| Cần ghi | Cách kiểm tra | Hậu quả nếu thiếu |
| --- | --- | --- |
| Java/JDK/JVM, PID, recording name | `java -version`, `jcmd -l`, metadata file | Có thể nhầm tiến trình hoặc phiên bản cấu hình |
| Bắt đầu/kết thúc, timezone, duration | `jfr summary`; thống nhất UTC/offset | Trộn sự kiện ở thời điểm khác nhau |
| `.jfc`, event enabled/threshold/period/stackTrace | `JFR.check verbose=true` khi recording chạy; lưu config | Sai lệch do thay đổi cách thu |
| Event count theo loại | `jfr summary` | “Không thấy event” có thể là event bị tắt hoặc lọc |
| Thread, stack depth, event start/duration | `jfr print` và JMC | Không biết event xảy ra ở luồng nào hoặc kéo dài bao lâu |
| Repository retention/recording coverage | Thời gian recording, `maxage/maxsize`, dump thực tế | Mất phần đầu/cuối; nhầm vùng dữ liệu thiếu là 0 sự kiện |
| Throughput, active requests, queue size, GC counters | Metric/log/trace độc lập | Không phân biệt chung nguyên nhân từ workload |
| Overhead/ảnh hưởng của recording | So baseline cùng tải, xem volume/CPU/latency | Công cụ quan sát có thể thay đổi đối tượng đo |

Ví dụ lệnh kiểm tra tệp đã export:

```bash
jfr summary incident.jfr
jfr print --events jdk.ExecutionSample --stack-depth 16 incident.jfr
jfr print --events jdk.JavaMonitorEnter incident.jfr
```

Lệnh `jfr print` chỉ hiển thị event có mặt trong tệp, không đảm bảo một event chưa thấy là chưa xảy ra. File có nhiều event thì stdout có thể lớn; dùng JMC hoặc công cụ phân tích phù hợp để lọc theo thread/cửa sổ thời gian.

Khi cần đối chiếu với application log, ưu tiên ghi timestamp **có timezone**, PID/instance ID, request hoặc trace ID, và cùng định nghĩa “latency” (end-to-end, server handling, waiting, database round-trip). Không dùng mỗi vị trí trên trục X để kết luận hai event có quan hệ nhân quả.

## 8. Cách lấy recording phục vụ phân tích có kiểm soát

Trên HotSpot JDK 21+, có thể khởi động một recording ngắn để phân tích:

```bash
jcmd 12345 JFR.start name=triage settings=profile duration=60s filename=triage.jfr
jcmd 12345 JFR.check name=triage verbose=true
```

Phải thay PID `12345`. Lệnh đầu chỉ chạy thành công khi attach được vào **đúng JVM** và có quyền phù hợp. `settings=profile` có thể bật nhiều event/thu mẫu dày hơn `default`; đừng so raw counts với recording `default` khác rồi kết luận workload thay đổi.

Muốn ghi minh bạch cấu hình của hai loại event cụ thể:

```bash
jcmd 12345 JFR.start name=sample20 settings=profile duration=60s filename=sample20.jfr jdk.ExecutionSample#period=20ms
```

Và một thí nghiệm khác:

```bash
jcmd 12345 JFR.start name=monitor20 settings=profile duration=60s filename=monitor20.jfr jdk.JavaMonitorEnter#enabled=true jdk.JavaMonitorEnter#threshold=20ms
```

Hai lệnh là **hai cấu hình minh họa**, nên chạy theo phiên tách biệt hoặc với ý thức rằng nhiều recording cùng lúc sẽ có tải/setting tương tác. Tập kết quả chỉ có thể so khi cùng workload, cùng thời lượng quan sát, cùng version, và đã biết các event cần phân tích thật sự có mặt.

Các event setting của `JFR.start` dùng mẫu `<event-name>#<setting-name>=<value>`; file `.jfc` có thể ghi đè bằng setting dòng lệnh, tùy precedence của JDK. Hãy đọc lại `JFR.check verbose=true` thay vì giả định câu lệnh đã tạo đúng nội dung mong muốn.

**Đọc kết quả:**

- `jfr summary` cho biết file chứa bao nhiêu event kiểu `jdk.ExecutionSample` và `jdk.JavaMonitorEnter`.
- Trong JMC, nhóm biểu đồ CPU/method profiling sử dụng **sampled stacks**; bảng monitor contention dựa trên **duration events** đã qua threshold.
- Một recording 60 giây có `0` mẫu cho một method nhỏ là bình thường nếu sampler không bắt trúng; một recording có `0` JavaMonitorEnter vượt 20 ms chỉ nói không thấy event thỏa điều kiện và cấu hình tương ứng trong cửa sổ đã ghi.

## 9. Ví dụ Java 17+ chạy được: cùng thao tác, kết quả đếm event khác nhau

Ví dụ này tạo **custom duration event**; nó không cố mô phỏng thuật toán sampling CPU của HotSpot. Mục tiêu là nhìn tận mắt tác động của `threshold` lên số event: chương trình thực hiện cùng **8 thao tác** ở hai lần chạy, nhưng điều kiện ghi thay đổi.

Lưu file **`JfrThresholdDemo.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrThresholdDemo {
    @Name("demo.WorkInterval")
    @Label("Work interval")
    @Category({"Demo", "Diagnostics"})
    static final class WorkInterval extends Event {
        @Label("Planned sleep (ms)")
        int plannedSleepMs;
    }

    private static void runOperation(int millis)
            throws InterruptedException {
        WorkInterval event = new WorkInterval();
        event.plannedSleepMs = millis;
        event.begin();
        Thread.sleep(millis);
        event.end();
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        long thresholdMs = args.length == 0
                ? 20
                : Long.parseLong(args[0]);
        if (thresholdMs < 0) {
            throw new IllegalArgumentException(
                    "threshold must be >= 0");
        }

        Path output = Path.of("threshold-" + thresholdMs + "ms.jfr");
        int[] waits = {5, 40, 5, 80, 5, 40, 5, 80};
        int attempts = 0;

        try (Recording recording = new Recording()) {
            recording.setToDisk(true);
            recording.enable(WorkInterval.class)
                     .withThreshold(Duration.ofMillis(thresholdMs))
                     .withStackTrace();
            recording.start();

            for (int ms : waits) {
                runOperation(ms);
                attempts++;
            }

            recording.stop();
            recording.dump(output);
        }

        long recorded = 0;
        try (RecordingFile file = new RecordingFile(output)) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                if ("demo.WorkInterval".equals(
                        event.getEventType().getName())) {
                    recorded++;
                }
            }
        }

        System.out.println("attempted=" + attempts);
        System.out.println("recorded=" + recorded);
        System.out.println("file=" + output);
    }
}
```

Biên dịch và chạy bằng **JDK 17+**, ở thư mục có quyền ghi tệp `.jfr`:

```bash
javac JfrThresholdDemo.java
java JfrThresholdDemo 0
java JfrThresholdDemo 20
jfr summary threshold-0ms.jfr
jfr summary threshold-20ms.jfr
jfr print --events demo.WorkInterval threshold-20ms.jfr
```

Hai lần chạy tạo hai tệp `threshold-0ms.jfr` và `threshold-20ms.jfr`. Dòng `attempted=8` là **kết quả xác định từ mã** ở cả hai lần chạy. Dòng `recorded=...` là **số event thực sự đọc được** và phải lấy từ output thật, không bịa một số cố định:

- Khi `threshold=0`, cả tám thao tác có cơ hội xuất hiện; trong thí nghiệm đủ tài nguyên thông thường mong đợi đếm gần **8**.
- Khi `threshold=20 ms`, bốn lần ngủ kế hoạch 40/80 ms có xu hướng đạt ngưỡng, bốn lần 5 ms thường bị lọc. Tuy nhiên `Thread.sleep` có thể bị kéo dài bởi scheduling, GC hoặc CPU contention; do đó một thao tác “5 ms” cũng có thể vượt 20 ms và được ghi.
- Nếu `recorded` khác dự kiến, xem **duration thực** trong từng event bằng `jfr print`; không mặc định demo hỏng. Trọng tâm là số **attempted** không đổi trong khi tập **recorded** phụ thuộc filter/điều kiện ghi.

Chương trình minh họa ba việc: `event.begin()` đánh dấu bắt đầu, `event.end()` kết thúc đo, `event.commit()` đề nghị ghi, nhưng **JFR áp dụng setting của recording** trước khi xuất thành event quan sát được. Đây là một ví dụ duration event. Đừng suy từ đó rằng `jdk.ExecutionSample` cũng được tạo ra mỗi lần method gọi rồi mới lọc theo threshold; đó là **cơ chế lấy mẫu khác**.

### Vì sao nên dùng metric ứng dụng song song?

Chỉ `attempts` trong code mới cho mẫu số thật của phép đếm ở thí nghiệm này. Trong production, có thể cần đồng bộ `http.server.requests`, số task dequeued, số retry hoặc request ID từ tracing để xác nhận “bao nhiêu lần thao tác đã xảy ra”. JFR cung cấp chi tiết quan sát hoạt động JVM; thống kê nghiệp vụ cung cấp **mẫu số** và điều kiện tải.

## 10. Tương quan thời gian không chứng minh nhân quả

Giả sử dashboard có ba đợt:

- `10:00:00–10:00:15`: request latency tăng.
- Cũng khoảng đó, JFR cho thấy nhiều allocation samples và một số GC pause.
- CPU sampling bắt được stack ở method `parsePayload` thường xuyên hơn.

Một kết luận hấp tấp là “`parsePayload` gây GC, và GC là nguyên nhân duy nhất làm chậm request”. Nhưng có ít nhất bốn cơ chế khác nhau phù hợp với timeline:

1. **Tải chung làm cả hai cùng tăng:** burst requests → parse nhiều → allocation nhiều → GC; đồng thời DB/queue cũng chậm. GC có thể chỉ là một phần.
2. **Phụ thuộc ngược chiều:** request bị giữ lâu do upstream timeout → buffer/scope sống lâu → heap pressure tăng; GC diễn ra **sau** khi latency bắt đầu xấu.
3. **Một nút nghẽn thứ ba:** CPU throttling, lock contention hoặc I/O chậm làm sampling/GC scheduling và latency thay đổi cùng lúc.
4. **Sai lệch do cách đo:** JFR `threshold` khác, sample density khác, ghi cuối cửa sổ hoặc lệch timestamp làm hai đường đồ thị trông đồng pha dù chúng không cùng nguyên nhân.

Có thể phác họa quan hệ giả định:

```text
Load tăng ──> allocation tăng ──> GC hoạt động nhiều
    │
    ├───────> queue/backlog tăng ──> latency tăng
    │
    └───────> DB/CPU contention ──> latency tăng

GC pause có thể góp phần vào latency,
nhưng đồ thị đồng thời chưa tách được mức đóng góp.
```

Để chứng minh GC *góp phần trực tiếp*, cần thêm bằng chứng về **request cụ thể bị dừng**, thời điểm pause phủ lên đoạn xử lý của request, thời lượng pause phù hợp độ trễ tăng thêm, lặp lại ở nhiều đợt và kiểm soát các nguyên nhân khác. Ngay cả bằng chứng một pause trùng request cũng chưa nói nó là **nguyên nhân duy nhất**.

## 11. Cách ghép timeline không tự gây ngộ nhận

### 11.1. Phân biệt timestamp của event

Các event JFR có thời điểm bắt đầu và, với duration event, có thời lượng; event chỉ có thể được hoàn tất/commit sau thao tác đo. Khi vẽ chart gộp theo **start time**, **end time** hay bucket 1 giây, thứ tự nhìn thấy có thể khác.

Ví dụ, một operation bắt đầu `12:00:00.100`, mất 900 ms và kết thúc `12:00:01.000`. Nếu bảng được nhóm theo thời điểm kết thúc, nó nằm ở bucket 12:00:01; một GC pause lúc `12:00:00.500` nằm giữa duration của operation, nhưng nhìn hai cột aggregate có thể tưởng operation xảy ra sau GC.

### 11.2. Đồng bộ đồng hồ và độ phân giải

- JFR timestamp trong một JVM dễ tương quan nội bộ hơn so với hệ thống phân tán; cần xử lý UTC/timezone khi ghép application logs, trace, OS metrics, APM.
- Đồng hồ giữa server/container khác nhau có thể có clock skew; cùng “12:00:00” trên hai hệ thống không nhất thiết là cùng thời điểm vật lý.
- Bucket theo phút che mất sự kiện 20 ms; bucket quá nhỏ làm tín hiệu nhiễu khi sample hiếm.
- Event có duration 50 ms là một khoảng **[start, end]**, không chỉ một chấm trên đồ thị.
- Recording chỉ phủ T0–T1, repository đã discard dữ liệu cũ hoặc mất mẫu thì chart trống không đồng nghĩa hệ thống yên ổn.

### 11.3. Tìm độ trễ và chuỗi cơ chế, không chỉ đồng thời

Nếu giả thuyết “GC pause gây tăng tail latency”, hãy kiểm tra request start/end, pause start/end, duration pause và hiệu ứng trước–trong–sau pause. Nếu latency tăng **trước** GC trong nhiều đợt, giả thuyết đơn giản đó yếu đi, nhưng GC vẫn có thể là yếu tố bổ sung. Một mối quan hệ lặp lại dưới các điều kiện tương đương mạnh hơn một lần trùng timestamp.

## 12. Chuyển từ biểu đồ sang một giả thuyết kiểm chứng được

Quy trình điều tra thực dụng:

1. **Định nghĩa triệu chứng độc lập:** ví dụ p99 server latency tăng từ 80 ms lên 400 ms ở cùng API khi RPS ~500/s. Đo số đó từ request metrics/traces, không từ count JFR duration events đã qua threshold.
2. **Ghi chính xác cấu hình quan sát:** JDK/GC, recording profile, enabled, threshold, period, stackTrace, mốc thu, số mẫu/events, file có đầy đủ cửa sổ hay không.
3. **Tạo cửa sổ baseline và incident cùng định nghĩa:** chọn giai đoạn tải, traffic mix, số request đồng thời, dataset, JVM warm-up và trạng thái cache tương đương; ghi những khác biệt còn lại.
4. **Phát biểu cơ chế và dự báo:** “Nếu lock L làm request chờ, những request chậm sẽ có đoạn wait phù hợp, event `jdk.JavaMonitorEnter` vượt ngưỡng trên đường code này, và giảm tranh chấp L sẽ giảm tail latency.” Dự báo phải phân biệt được với giả thuyết khác.
5. **Thu bằng chứng độc lập:** request span, queue depth, DB latency, CPU throttling, GC log/pause, monitor event, mẫu thread và chỉ số ứng dụng.
6. **Kiểm tra chiều thời gian và đối tượng:** event có nằm trên thread/request/correlation ID của request chậm không? Hay chỉ xuất hiện đồng thời ở thread khác?
7. **Thử thay đổi một nhân tố khi có thể:** giảm concurrency, giảm critical section, tăng/giảm payload, thay chính sách cache hoặc xử lý queue. Lặp lại dưới cùng điều kiện, so latency/GC/lock cùng lúc.
8. **Tìm phản chứng:** nếu contention giảm mà latency không thay đổi, hoặc latency cao khi không có contention, cần xem xét cơ chế khác.
9. **Báo kết luận có giới hạn:** nêu “phù hợp với”, “có bằng chứng trực tiếp của”, hay “đã được xác nhận qua thí nghiệm” dựa trên mức chắc chắn thực tế.

Trong production không nên thay đổi cấu hình tùy tiện chỉ để “chứng minh”. Có thể làm controlled load test trên staging hoặc thử canary khi có quy trình phù hợp. Bước kiểm soát và lặp lại giúp giảm confounding; nó không phải phép màu loại bỏ mọi biến ngoại lai.

## 13. Số mẫu và sai số: đừng suy từ tỷ lệ nhỏ thành chân lý

Giả sử cùng một khoảng ghi, phương pháp JMC cho thấy:

| Method | Số execution samples | Tỷ lệ trong 100 sample hợp lệ |
| --- | ---: | ---: |
| A | 20 | 20% |
| B | 50 | 50% |
| C và các method khác | 30 | 30% |

Điều có thể nói: “Trong **100 mẫu quan sát được** theo bộ lọc hiện tại, A có mặt ở 20 mẫu.” Điều không thể nói ngay: “A gây đúng 20% tổng CPU” hoặc “A được gọi ít hơn B 2,5 lần”.

Về trực giác thống kê, nếu 100 quan sát là **độc lập, đại diện và giống phép thử Bernoulli** với `p=0,2`, standard error ước tính sẽ là:

```text
SE ≈ sqrt(p × (1 - p) / n)
   = sqrt(0.2 × 0.8 / 100)
   = 0.04 = 4 điểm phần trăm
```

Khoảng 95% rất thô kiểu `p ± 2 SE` là khoảng 12–28%. **Không lấy khoảng này làm confidence interval chuẩn cho JFR**: các execution samples trong cùng thread/workload thường tương quan, thời điểm sample có bias và mẫu không nhất thiết ngẫu nhiên độc lập. Đây chỉ là minh họa vì sao một tỷ lệ tính từ ít sample vốn đã nhiều bất định *ngay cả trong điều kiện thống kê đẹp*.

Khi số mẫu ít hoặc đường chạy hiếm, tăng cửa sổ quan sát, dùng điều kiện tái hiện và đối chiếu với metrics/tracing khác hữu ích hơn việc lấy tỷ lệ 3 chữ số thập phân trên một chart.

## 14. Phân tích threshold theo “sensitivity analysis”

Giả sử một event loại wait được ghi dưới hai cấu hình; số liệu sau hoàn toàn **giả định**:

| Mốc chạy | Workload | Threshold | Số wait event trong 1 phút | p99 request latency |
| --- | --- | --- | ---: | ---: |
| Run A | 500 req/s | 20 ms | 120 | 240 ms |
| Run B | 500 req/s | 5 ms | 2.400 | 245 ms |

Tăng từ 120 lên 2.400 event là điều **có thể dự kiến** khi ngưỡng hạ xuống: thêm các wait 5–20 ms được ghi. Việc số event tăng **không chứng minh contention xấu đi 20 lần**. p99 gần tương đương cũng không nói event 5–20 ms “không có ảnh hưởng”: cần biết chờ xảy ra trên đường xử lý request nào, phân bố, độ đồng thời, overhead đo và ảnh hưởng tới p99.

Ngược lại, nếu cả threshold và sampling period **giữ nguyên**, workload tương đương, mà tỷ lệ event chậm và p99 cùng tăng ở nhiều mốc, đó là bằng chứng **mạnh hơn cho một bất thường**, nhưng vẫn chưa cho nguyên nhân.

Ghi rõ cấu hình của từng run trong mọi bảng so sánh. Tránh phép trừ thẳng hai số event nếu khoảng thời gian khác; tối thiểu quy về `events / phút ghi hợp lệ`, sau đó tiếp tục chuẩn hóa theo workload và chế độ thu. **Normalization không sửa được selection bias** do threshold hay sampler khác nhau.

## 15. Các giả thuyết sai và cách kiểm tra

| Kết luận vội | Vì sao sai | Cách kiểm tra |
| --- | --- | --- |
| “Không có event lock nên không có lock contention” | Event có thể tắt, threshold cao hoặc recording không phủ đúng cửa sổ | `JFR.check verbose`, kiểm tra threshold, log/thread dump, metric chờ |
| “Method X hiện 30% mẫu nên gây 30% request latency” | CPU sample ≠ thời gian request chờ; pool/thread/workload có thể khác | Ghép với request traces và thread state; đo CPU trực tiếp |
| “Allocation sample tăng 2 lần = tạo đúng 2 lần object” | Allocation là sample và cách ước lượng có thể dùng trọng số | So allocation rate/heap/GC, cùng cấu hình lấy mẫu |
| “Latency và GC trùng nhau, vậy GC là thủ phạm duy nhất” | Tải/CPU/DB/queue cũng có thể cùng tác động | Pause interval, request spans, workload và controlled test |
| “Event count tăng sau khi bật `profile` = ứng dụng tệ đi” | Gói event và độ nhạy thu khác nhau | Giữ cấu hình cố định khi so hoặc chỉ so metric có cùng định nghĩa |
| “Có một sample stack ở method Y = Y luôn chạy chậm” | Một sample không đại diện cho phân bố lần gọi | Lấy thêm mẫu, phân nhóm thread, direct timing |
| “Event bắt đầu trước metric nên chắc chắn là nguyên nhân” | Có thể cùng chịu tác động bởi biến thứ ba hoặc sai lệch timestamp | Kiểm tra cơ chế, chiều thời gian trên cùng request và phản chứng |
| “Nhiều lần lặp lại tương quan là đủ chứng minh” | Confounder có thể lặp lại cùng tải; causal pathway chưa kiểm chứng | Thay một nhân tố, so dưới điều kiện kiểm soát, đo chuỗi trung gian |

## 16. Checklist trước khi viết báo cáo sự cố

**Về dữ liệu JFR:**

- Đúng **PID/JVM/build**, cùng version/GC/recording settings ở các mốc so sánh?
- Biết event này là **sample, periodic, duration hay instant**?
- Biết `enabled`, `threshold`, `period`, `stackTrace` thực tế?
- Kiểm tra file chỉ phủ đúng khoảng nào, có rơi/chưa có mẫu hoặc retention gap không?
- Count/tỷ lệ có mẫu số phù hợp và có nhãn điều kiện quan sát không?
- Mỗi duration event có được xem như **một khoảng thời gian**, không chỉ một timestamp?

**Về nguyên nhân:**

- Có metric nghiệp vụ độc lập xác nhận triệu chứng không?
- Có **cơ chế cụ thể** kết nối event tới request/latency/throughput không?
- Đã xem tải, CPU, DB, I/O, GC, lock, queue và các nguồn confounding khả dĩ?
- Có đối chứng trước/sau cùng điều kiện và nhiều đợt tương tự?
- Có tìm được **phản chứng** hoặc thử thay đổi để đánh giá giả thuyết?
- Câu kết luận đã phân biệt **quan sát**, **nghi vấn** và **điều đã xác nhận**?

## 17. Mẫu báo cáo có giới hạn chứng cứ

**Cách viết phù hợp:**

> Trong recording HotSpot JDK 21, cấu hình `profile`, `jdk.JavaMonitorEnter#threshold=20ms` và `jdk.ExecutionSample#period=20ms`, vùng 10:00–10:02 ghi nhận số event monitor enter vượt 20 ms tăng cùng lúc p99 của API tăng từ 90 lên 350 ms. Đây là tương quan đáng điều tra. Các event dưới 20 ms không được đưa vào count và số execution sample không phải số lần method được gọi. Hiện chưa xác minh những event chờ monitor đó thuộc request chậm nào hoặc tải/DB có thay đổi hay không. Bước tiếp theo là ghép request spans với stack/thread ở JFR, kiểm soát workload, rồi kiểm tra giả thuyết contention qua một thí nghiệm có đối chứng.

**Cách viết quá mức:**

> Trong cùng phút, lock event và p99 cùng tăng. Vì vậy lock chắc chắn là nguyên nhân duy nhất; method có 40% sample chiếm đúng 40% CPU.

Mẫu thứ hai không chứng minh được từ dữ liệu: nó thiếu cơ chế, mẫu số, cấu hình sampling, kiểm soát confounder và phép kiểm chứng.

## 18. Bài tập tự đánh giá

**Bài 1 — threshold.** Một service xử lý 1.000 request/phút. JFR ghi 80 event `jdk.JavaMonitorEnter` với `threshold=20ms` trong phút đó. Có thể nói “8% request bị lock contention” không?

**Gợi ý:** Không. 80 là số event monitor enter thỏa ngưỡng; một request có thể có nhiều event hoặc không event; không có mapping event→request và chưa biết event coverage. Muốn tỷ lệ request bị ảnh hưởng cần request ID/trace và điều kiện đo phù hợp.

**Bài 2 — sampling.** Một method xuất hiện ở 1 trong 200 execution samples. Có thể nói nó chỉ được gọi một lần?

**Gợi ý:** Không. Có thể bị gọi hàng nghìn lần nhưng mỗi lần ngắn. Sample count là quan sát theo thời điểm.

**Bài 3 — cấu hình.** Run A dùng `JavaMonitorEnter#threshold=20ms` và Run B dùng `5ms`. Số event B lớn gấp 5 lần. Đã chứng minh lock contention tăng 5 lần?

**Gợi ý:** Chưa. Thay đổi threshold làm nhiều event ngắn hơn đủ điều kiện xuất hiện. Cần so dưới cùng cấu hình.

**Bài 4 — causality.** Gặp GC pause 150 ms cùng khoảng request 300 ms. Có thể khẳng định toàn bộ 300 ms do GC?

**Gợi ý:** Không. Kiểm tra thời điểm pause tương đối với xử lý của request, phần latency trước/sau pause, DB, queuing, CPU; pause tối đa chỉ giải thích một phần phù hợp về mặt thời gian trong trường hợp request thực sự bị ảnh hưởng.

**Bài 5 — làm thí nghiệm.** Chạy `JfrThresholdDemo` với threshold 0 và 20 ms. Ghi dòng `attempted`, `recorded` và duration các event thật trong hai tệp. Vì sao số `recorded` có thể thay đổi dù danh sách `waits` giống hệt?

**Gợi ý:** Threshold lọc theo **thời lượng thực tế**; scheduler/GC làm actual duration thay đổi và trạng thái recorder có giới hạn thực tế. Đếm từ output/file thật, không suy số event từ planned sleeps.

**Thực hành cuối bài:** Chọn một recording JFR có `jdk.ExecutionSample` và một loại duration event. Lập bảng cho mỗi event: setting, cơ chế thu, cửa sổ thời gian, số quan sát, mẫu số phù hợp, điều được suy ra và điều chưa thể suy ra. Đặt hai giả thuyết có khả năng tạo cùng timeline; đề xuất phép đo hoặc thí nghiệm phân biệt chúng.

## 19. Nguồn chính thức để đối chiếu

- [Oracle Java 21 — `jdk.jfr`: định nghĩa `enabled`, `threshold`, `period`, `stackTrace`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- [Oracle Java 21 — `EventSettings`: `withThreshold`, `withPeriod` và stack trace](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html).
- [Oracle Java 21 — `Recording`: vòng đời, cấu hình, `stop` và `dump`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html).
- [Oracle Java 21 — `RecordingFile`: đọc lại event thực sự được ghi](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
- [Oracle JDK 21 — `jcmd`: `JFR.start`, override event settings, `JFR.check`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `jfr`: `summary`, `metadata`, `print`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/jfr/configure/).

**Nguyên tắc cuối:** `threshold` trả lời “event nào vượt ngưỡng và đã được ghi”; `sampling` trả lời “sampler đã thấy trạng thái nào tại các điểm lấy mẫu”; biểu đồ thời gian trả lời “các quan sát diễn ra gần nhau ra sao”. Để trả lời “*vì sao*” cần cơ chế hợp lý, dữ liệu độc lập, kiểm soát biến gây nhiễu và bằng chứng có thể lặp lại.
