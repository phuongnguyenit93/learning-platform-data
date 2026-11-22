# 16.5 begin, end, commit, isEnabled và shouldCommit trong đường xử lý

## Mục tiêu

Trong ứng dụng Java, tự định nghĩa sự kiện **Java Flight Recorder (JFR)** giúp gắn thời gian, trạng thái và một vài thuộc tính nghiệp vụ vào những đoạn xử lý cần quan sát. Tuy nhiên, đặt nhầm vị trí **begin()**, **end()** hoặc kiểm tra **shouldCommit()** sai thời điểm có thể tạo duration gây hiểu lầm; thu thập dữ liệu đắt tiền trước khi kiểm tra điều kiện ghi cũng làm tăng overhead.

Sau bài này, bạn có thể:

1. Phân biệt vai trò của **Event.begin()**, **Event.end()**, **Event.commit()**, **Event.isEnabled()** và **Event.shouldCommit()** trong vòng đời một custom event.
2. Thiết kế đúng **ranh giới đo** quanh đoạn xử lý thật, kể cả khi có exception, interruption hoặc nhánh return sớm.
3. Phân biệt kiểm tra **enabled** trước xử lý với kiểm tra **duration threshold** sau khi đo.
4. Tránh tính toán field/stack/debug payload đắt tiền khi event không được lưu.
5. Cấu hình event settings bằng **Recording.enable(...).withThreshold(...)**, rồi kiểm chứng file JFR bằng **jfr summary** và **jfr print**.
6. Hiểu sự khác nhau giữa event **tức thời (instant)**, event **có thời lượng (duration)** và tính chất của nhiều recording đang chạy đồng thời.

Bài sử dụng **jdk.jfr.Event** và các API có từ Java 9, kèm một chương trình **Java 17+** độc lập. Ví dụ kiểm chứng tham chiếu Java/JFR 21, không phụ thuộc vào Spring Boot hay trình giám sát bên ngoài.

## 1. Đặt năm phương thức vào cùng một sơ đồ

~~~text
Có một đoạn xử lý cần quan sát
             |
             v
     new CustomEvent()
             |
             v
      isEnabled() ?
       /        \
     false      true
       |          |
       |        begin()
       |          |
       |       xử lý thực tế
       |          |
       |        end()          (nên đặt trong finally)
       |          |
       |    shouldCommit() ?
       |       /       \
       |     false     true
       |       |         |
       |       |    điền dữ liệu tốn chi phí
       |       |         |
       |       |      commit()
       |       |         |
       +-------+---------+
             |
          kết thúc
~~~

Đây là sơ đồ tối ưu hóa **quan sát**; đường xử lý nghiệp vụ phải chạy dù JFR đang tắt. Không bao giờ đặt toàn bộ business logic vào nhánh isEnabled() rồi bỏ qua khi false.

| Phương thức | Ý nghĩa chính | Khi nào sử dụng |
| --- | --- | --- |
| **begin()** | Đánh dấu thời điểm bắt đầu đo duration của instance | Ngay trước phạm vi công việc muốn đo |
| **end()** | Đánh dấu kết thúc duration; phải được gọi sau begin | Sau công việc được đo, thường trong finally |
| **commit()** | Gửi timestamp, duration và các field đến JFR theo effective settings | Sau khi field cần lưu đã sẵn sàng |
| **isEnabled()** | True khi có ít nhất một recording đang chạy và event type được bật trong một recording | Kiểm tra sớm để tránh instrumentation tốn chi phí khi JFR tắt |
| **shouldCommit()** | True khi event đang được bật và duration đáp ứng threshold áp dụng | Sau end, trước khi tạo dữ liệu field tốn chi phí và commit |

**Lưu ý:** JFR tự quyết định một event có đủ điều kiện được ghi hay không khi gọi commit(). **shouldCommit() không phải lệnh bật/tắt event** và không thay thế commit(); nó là kiểm tra có ích để tránh làm những công việc chuẩn bị vốn sẽ bị bỏ đi.

## 2. Vòng đời của một Event: object, đo thời gian và ghi dữ liệu

### 2.1. Tạo instance không đồng nghĩa phát một event record

Một class kế thừa **jdk.jfr.Event** là định nghĩa event type. Tạo **new RequestEvent()** mới có một Java object dùng để chuẩn bị event; nó **chưa xuất hiện** trong bản ghi JFR chỉ vì được tạo.

Ví dụ tối giản, đây là đoạn mã nằm trong một phương thức có import thích hợp:

~~~java
RequestEvent event = new RequestEvent();
event.operation = "lookup";
event.commit();
~~~

Khi type được bật và threshold cho phép, **commit()** phát một **instant event** nếu không gọi begin(). Instant event có start/end time trùng nhau theo mô hình RecordedEvent; không thích hợp để suy thời lượng nghiệp vụ.

**Không cần gọi begin()/end() cho mọi event.** Nếu bạn chỉ muốn đánh dấu “cache refreshed”, “feature toggled” hoặc “job accepted”, một instant event có thể đúng nghĩa hơn.

### 2.2. begin() đánh dấu điểm bắt đầu đo

~~~java
RequestEvent event = new RequestEvent();
event.begin();
// Thực thi công việc được đo.
~~~

Từ thời điểm này JFR có thể xác định duration khi có điểm kết thúc. Gọi begin() **sau** đoạn xử lý cần quan sát sẽ bỏ sót thời gian thực. Gọi quá sớm sẽ tính cả thời gian chờ, chuẩn bị dữ liệu hoặc setup không thuộc phạm vi định đo.

Ví dụ: nếu muốn đo riêng thao tác truy vấn database, đặt begin ngay trước lần gọi truy vấn; nếu muốn đo toàn bộ request từ lúc nhận đến lúc trả response, phạm vi begin/end phải bao gồm toàn bộ các bước đó. Cả hai đều hợp lệ nhưng có **nghĩa khác nhau**.

### 2.3. end() chốt thời điểm kết thúc

~~~java
event.begin();
try {
    processRequest();
} finally {
    event.end();
}
~~~

**end() phải đến sau begin().** Đặt trong finally tránh bỏ quên khi method return sớm hoặc ném exception. Bắt exception để điền trạng thái là tùy yêu cầu, nhưng không nên nuốt exception chỉ vì đang ghi JFR.

Có thể gọi **commit()** sau begin() mà không gọi end(); theo API, **commit() sẽ tự kết thúc duration** trong trường hợp đó. Tuy nhiên, nếu còn phải tính thông tin bổ sung sau công việc, **end() tường minh** giữ ranh giới đo chính xác và cho phép gọi shouldCommit() dựa trên duration đã hoàn tất.

### 2.4. commit() gửi dữ liệu của event

~~~java
event.begin();
try {
    processRequest();
} finally {
    event.end();
    event.operation = "lookup";
    event.commit();
}
~~~

**commit()** ghi **các field đã điền, timestamp và duration** theo settings. Khi event type bị tắt hoặc duration dưới threshold, event không có record tương ứng dù code có gọi commit(). Đây là hành vi lọc thông thường, không phải lỗi.

Thực hành tốt: mỗi operation có một instance Event và một commit có chủ đích. Đừng dùng chung một instance Event được mutate đồng thời giữa nhiều request/thread; dữ liệu có thể chồng chéo và ranh giới thời gian trở nên khó giải thích. Với luồng xử lý async, dùng correlation ID ở field sự kiện và xác định rõ đơn vị công việc muốn đo.

## 3. isEnabled(): kiểm tra nhanh trước khi làm việc tốn chi phí

**Event.isEnabled()** trả true khi **ít nhất một recording đang RUNNING** và setting **enabled=true** cho event type tương ứng. False có thể do không có recording, event bị tắt theo configuration hoặc chưa bắt đầu thu thập.

Điều quan trọng: **isEnabled() không kiểm tra duration threshold** và **không bảo đảm instance sẽ xuất hiện trong file**. Một event 1 ms có thể isEnabled()=true nhưng không được ghi khi threshold=20 ms.

Cách dùng:

~~~java
StepEvent event = new StepEvent();
boolean tracing = event.isEnabled();

if (tracing) {
    event.begin();
}

try {
    businessLogic(); // Luôn chạy dù tracing=false.
} finally {
    if (tracing) {
        event.end();
        event.commit();
    }
}
~~~

*Đây là fragment minh họa; StepEvent và businessLogic() phải được định nghĩa trong class ứng dụng.* Đoạn này hợp lý khi chỉ cần ghi duration và vài field rẻ, nhưng commit() sẽ tự bỏ event không đạt threshold. Nếu cần tạo thông điệp tốn chi phí, nên thêm shouldCommit() như phần tiếp theo.

### Tại sao không nên chỉ viết điều kiện bao quanh business logic?

**Đoạn sai về nghiệp vụ:**

~~~java
StepEvent event = new StepEvent();
if (event.isEnabled()) {
    event.begin();
    businessLogic(); // Khi JFR tắt, nghiệp vụ không chạy.
    event.commit();
}
~~~

Nghiệp vụ phải **độc lập với bật/tắt JFR**. Bật recording để quan sát không được phép làm thay đổi việc xử lý request. Tách logic xử lý ra khỏi instrumentation, hoặc dùng một nhánh guard chỉ để quyết định có bắt đầu đo hay không.

### isEnabled() có phải điều kiện ổn định trong cả operation?

Không. Recording có thể bắt đầu/dừng hoặc settings thay đổi khi operation đang chạy. Kiểm tra lúc đầu chỉ là **tối ưu hóa tại một thời điểm**. JFR có thể áp dụng settings tại lúc ghi; đừng cam kết “isEnabled() true thì chắc chắn file có event”. Khi cần phân tích sau sự cố, xem bản ghi thực tế và thời điểm recording.

## 4. shouldCommit(): kiểm tra duration threshold sau khi end

Theo API Java 21, **shouldCommit()** trả true nếu event được bật và duration đáp ứng threshold áp dụng. Threshold là **thời lượng tối thiểu**, nên:

- **duration dưới threshold**: event không được ghi.
- **duration đủ threshold**: event *có thể* được ghi, nếu event type còn enabled và recording/settings cho phép.
- **threshold = 0**: không lọc dựa trên thời lượng.
- **isEnabled() = true** không kéo theo shouldCommit() = true.

Cách dùng thông thường:

~~~java
event.begin();
try {
    processRequest();
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.description = buildExpensiveDescription();
        event.commit();
    }
}
~~~

*Fragment minh họa; processRequest() và buildExpensiveDescription() là phương thức do ứng dụng định nghĩa.*

**Vì sao gọi sau end?** Lúc này duration cuối đã được xác định. Nếu dùng shouldCommit() ở đầu operation, bạn không thể dùng kết quả đó để quyết định đúng về ngưỡng thời lượng của **công việc chưa xảy ra**. Đầu operation phù hợp với isEnabled(); cuối operation phù hợp với shouldCommit().

**Vì sao điền field đắt tiền sau shouldCommit?** Nếu duration bị lọc, bạn không phải tạo chuỗi lớn, serialize object, format stack trace, gọi database bổ sung hay đọc thêm các dữ liệu chỉ phục vụ telemetry. Với field rất rẻ như status code đã có, điền trước cũng được.

**Cần tránh tác dụng phụ:** buildExpensiveDescription() chỉ nên chuẩn bị dữ liệu quan sát; không đặt thao tác có side effect nghiệp vụ, cập nhật database hoặc quyết định trả response trong nhánh shouldCommit(). Thời điểm recording bật/tắt sẽ khiến nhánh đó chạy khác nhau.

### Threshold trong nhiều recording đồng thời

Nếu recording A và B cùng bật một event type với threshold khác nhau, tài liệu API cho biết **shouldCommit() xét ngưỡng nhỏ nhất trong các recording đang chạy**.

Ví dụ minh họa:

| Recording | Event enabled | Threshold |
| --- | --- | --- |
| A | Có | 10 ms |
| B | Có | 100 ms |

Một operation 50 ms có thể **shouldCommit()=true** vì đáp ứng ngưỡng 10 ms của A, dù chưa đáp ứng ngưỡng của B. **Không hiểu true là event đã xuất hiện trong tất cả file recording**. Mỗi recording có settings và kết quả lọc riêng. Bật/tắt settings, buffer/loss và thời gian dump còn ảnh hưởng việc quan sát sau đó.

### shouldCommit() không phải điều kiện bắt buộc để commit đúng

Bạn có thể gọi:

~~~java
event.begin();
try {
    doWork();
} finally {
    event.commit(); // Tự end nếu chưa gọi end, và tự áp dụng settings.
}
~~~

*Đây là fragment minh họa.* Hợp lệ nếu không cần xem duration trước và không có bước tạo payload đắt tiền cần tránh. Tuy nhiên, phạm vi duration sẽ bao gồm mọi công việc diễn ra cho đến commit(); nếu bên trong finally có cleanup, log hoặc serialization trước commit thì chúng cũng nằm trong khoảng đo.

## 5. Cấu hình event: enabled, threshold và stack trace

Với **jdk.jfr.Recording**, có thể cấu hình từng custom event:

~~~java
try (Recording recording = new Recording()) {
    recording.enable(StepEvent.class)
            .withThreshold(Duration.ofMillis(25))
            .withStackTrace();

    recording.start();
    // Chạy workflow phát các StepEvent.
    recording.stop();
    recording.dump(Path.of("workflow.jfr"));
}
~~~

*Fragment minh họa cần định nghĩa StepEvent và import Recording, Duration, Path.* Những điều cần hiểu:

- **enable(StepEvent.class)**: bật event type này cho recording. Không mặc nhiên bật mọi event type.
- **withThreshold(25 ms)**: chỉ những instance đủ duration mới phù hợp ngưỡng này. Có thể dùng **withoutThreshold()** hoặc duration 0 cho instant event.
- **withStackTrace()**: yêu cầu ghi stack trace khi event được commit và JFR có dữ liệu; stack nằm ở nơi commit và không phải toàn bộ lịch sử call graph của request.
- **recording.start()**: bắt đầu thu thập. Nếu chạy business logic trước start, isEnabled() không thể thay mặt một recording chưa chạy.
- **recording.stop()** và **dump(Path)**: kết thúc và xuất dữ liệu. Với Recording dùng disk repository mặc định, dump sau stop là hợp lệ nếu recording chưa đóng.

Ngoài Recording API, có thể đặt annotation trên event class như **@Enabled(false)**, **@Threshold("20 ms")**, **@StackTrace(false)** để xác định mặc định. Settings của recording có thể điều chỉnh hành vi thu thập thực tế; đừng dựa riêng annotation để suy kết quả nếu có nhiều recording.

**Khác nhau giữa các loại cấu hình:**

| Loại | Có tác dụng gì? | Có nên kiểm chứng lúc nào? |
| --- | --- | --- |
| @Enabled / enabled setting | Event type có được ghi không | Trước/đang recording |
| @Threshold / threshold setting | Thời lượng ngắn hơn ngưỡng bị lọc | Sau khi event kết thúc |
| @StackTrace / stackTrace setting | Có tạo stack snapshot ở commit không | Khi xem event trong file |
| @Category, @Label, @Description | Metadata giúp hiểu type/field | Khi đọc metadata, không phải bộ lọc nghiệp vụ tự động |
| Thu thập file JFR | File được dump đúng khoảng thời gian không | Khi phân tích recording thực tế |

Các JDK và phiên bản Flight Recorder có thể hỗ trợ setting mở rộng; phần này tập trung vào những setting chuẩn liên quan trực tiếp đến năm phương thức.

## 6. Mẫu đúng trong request/service: try, catch, finally

Giả sử cần đo một operation xử lý đơn hàng. Khi ứng dụng ném exception, event vẫn phải kết thúc; trạng thái lỗi chỉ là một **field ghi nhận**, không được làm thay đổi luồng ném exception.

~~~java
StepEvent event = new StepEvent();
boolean trace = event.isEnabled();
if (trace) {
    event.begin();
}

String outcome = "ok";
try {
    return processOrder(orderId);
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    if (trace) {
        event.end();
        if (event.shouldCommit()) {
            event.operation = "processOrder";
            event.outcome = outcome;
            event.commit();
        }
    }
}
~~~

*Fragment này cần đặt trong method có kiểu trả về phù hợp và có định nghĩa StepEvent, processOrder, orderId.*

Vì sao có các bước:

1. **isEnabled()** kiểm tra sớm, để có thể bỏ phần đo JFR khi không có recording phù hợp.
2. **begin()** nằm ngay trước toàn bộ operation.
3. **try** luôn thực hiện nghiệp vụ.
4. **catch** ghi trạng thái rồi **throw lại** lỗi; không cố biến lỗi nghiệp vụ thành success.
5. **finally** gọi **end()** cả khi return lẫn exception.
6. **shouldCommit()** dùng duration đã chốt để quyết định có đáng tạo field hoặc commit hay không.
7. **commit()** chỉ làm sau khi field được gán đầy đủ.

Đối với **InterruptedException**, nên khôi phục interrupt flag khi ứng dụng chủ động bắt exception để xử lý, rồi tiếp tục tuân theo hợp đồng hủy tác vụ; có thể đánh dấu outcome **interrupted**. Không nên nuốt interrupt để hoàn tất ghi event. Chương trình chạy được dưới đây thực hiện cả nhánh này.

**Chọn ranh giới cleanup có chủ đích:** Nếu cleanup là một phần latency muốn quan sát, hãy gọi end sau cleanup. Nếu chỉ muốn đo business computation mà không tính telemetry, gọi end trước xử lý field/logging phục vụ JFR. Phạm vi được đo phải rõ trong tên event và phần mô tả.

## 7. Chương trình Java 17+ độc lập: instant marker, fast step, slow step và failed step

Ví dụ đầy đủ sau cho thấy:

- **WorkflowMarker**: event tức thời chỉ gọi commit().
- **StepTiming**: event có duration đo bằng begin()/end().
- **isEnabled()** bảo đảm công việc vẫn thực thi khi JFR bị tắt.
- **shouldCommit()** lọc việc tạo field theo threshold 25 ms.
- **finally** đóng khoảng đo cả khi xử lý thất bại.
- **Recording** xuất file **step-events.jfr** để đọc lại bằng CLI.

Tạo file **JfrEventLifecycleDemo.java**:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import java.util.Locale;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class JfrEventLifecycleDemo {

    @Name("demo.WorkflowMarker")
    @Label("Workflow Marker")
    @Category({"Demo", "Workflow"})
    public static class WorkflowMarker extends Event {
        @Label("Action")
        public String action;
    }

    @Name("demo.StepTiming")
    @Label("Step Timing")
    @Category({"Demo", "Workflow"})
    public static class StepTiming extends Event {
        @Label("Step Name")
        public String step;

        @Label("Outcome")
        public String outcome;
    }

    private static String work(String name, long sleepMillis,
                               boolean fail) throws InterruptedException {
        if (sleepMillis > 0) {
            Thread.sleep(sleepMillis);
        }
        if (fail) {
            throw new IllegalStateException("simulated failure");
        }
        return name.toUpperCase(Locale.ROOT);
    }

    private static String runStep(String name, long sleepMillis,
                                  boolean fail) throws InterruptedException {
        StepTiming event = new StepTiming();
        boolean trace = event.isEnabled();

        if (trace) {
            event.begin();
        }

        String outcome = "ok";
        try {
            return work(name, sleepMillis, fail);
        } catch (InterruptedException ex) {
            outcome = "interrupted";
            Thread.currentThread().interrupt();
            throw ex;
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            if (trace) {
                event.end();

                if (event.shouldCommit()) {
                    event.step = name;
                    event.outcome = outcome;
                    event.commit();
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("step-events.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(WorkflowMarker.class).withoutThreshold();
            recording.enable(StepTiming.class)
                    .withThreshold(Duration.ofMillis(25))
                    .withStackTrace();

            recording.start();

            WorkflowMarker marker = new WorkflowMarker();
            if (marker.isEnabled()) {
                marker.action = "workflow-start";
                marker.commit();
            }

            System.out.println(runStep("fast", 0, false));
            System.out.println(runStep("slow", 80, false));

            try {
                runStep("failed", 80, true);
            } catch (IllegalStateException ex) {
                System.out.println("Handled: " + ex.getMessage());
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("Created " + output);
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac --add-modules jdk.jfr JfrEventLifecycleDemo.java
java --add-modules jdk.jfr JfrEventLifecycleDemo
~~~

Đầu ra **stdout do chương trình tự in**, khi chương trình hoàn tất bình thường và thư mục cho phép ghi:

~~~text
FAST
SLOW
Handled: simulated failure
Created step-events.jfr
~~~

Không có sự phụ thuộc vào PID, số thread, timezone hoặc thời lượng thực tế trong stdout trên. Tập event ghi vào file có thể khác nhau tùy scheduling/JIT/VM. Điều chắc chắn về nghiệp vụ là nhánh fast và slow trả kết quả, nhánh failed ném exception nhưng được main xử lý.

### Đọc kết quả JFR

~~~bash
jfr summary step-events.jfr
jfr metadata --events demo.StepTiming,demo.WorkflowMarker step-events.jfr
jfr print --events demo.StepTiming,demo.WorkflowMarker step-events.jfr
~~~

Kỳ vọng trong môi trường HotSpot thông thường:

- **demo.WorkflowMarker** có một instant event action=workflow-start, vì threshold được bỏ và recording chạy.
- **demo.StepTiming** thường ghi **slow** và **failed** vì hai lệnh sleep(80 ms) vượt ngưỡng 25 ms.
- **fast** thường bị lọc vì duration rất ngắn. Tuy nhiên **không khẳng định chắc Count=2**: thread có thể bị scheduler tạm dừng hoặc các bước JIT/class-loading khiến cả fast cũng vượt 25 ms; recording có thể có những bất thường về thu thập. Dùng dữ liệu thật từ jfr summary/print để kiểm chứng.
- **failed** vẫn có outcome=error khi được ghi, chứng minh finally chạy dù exception xảy ra.

Thời điểm, thread, duration và stack frames sẽ khác theo lần chạy. **jfr summary** cho Count theo type; **jfr print** mới cho các giá trị field từng instance. Một bản ghi không có event thuộc type nào đó không nhất thiết có nghĩa operation không xảy ra: có thể bị lọc bởi setting/threshold hoặc recording không bao phủ khoảng cần đo.

### Điều gì xảy ra nếu tắt recording?

Trong ví dụ, nếu JFR không có recording đang chạy, isEnabled() sẽ false và business logic vẫn phải chạy. Bạn có thể tách runStep() ra để chạy trong ứng dụng không tạo Recording; phương thức **không phụ thuộc kết quả nghiệp vụ vào trạng thái JFR**.

### Điều gì xảy ra nếu bỏ shouldCommit()?

Thay nhánh cuối thành:

~~~java
event.end();
event.step = name;
event.outcome = outcome;
event.commit();
~~~

JFR vẫn áp dụng threshold khi commit. Với field rẻ như hai chuỗi tham chiếu đã có, chênh lệch overhead có thể nhỏ. Với payload đắt tiền, thiếu shouldCommit() sẽ phí công chuẩn bị cho các events bị bỏ. Thứ tự **end → shouldCommit → build fields → commit** bảo vệ chi phí trong trường hợp thường gặp.

## 8. Chọn pattern theo mục đích

| Mục đích | Pattern đề xuất | Điều kiện cần chú ý |
| --- | --- | --- |
| Dấu mốc ngay tại một thời điểm | Điền fields → commit() | Không cần begin/end; kiểm tra event type enabled nếu payload đắt |
| Đo độ dài của đoạn đồng bộ | begin → try work → finally end → commit | Thiết kế rõ điểm bắt đầu/kết thúc |
| Đo duration và lọc bước ngắn | isEnabled → begin → work → end → shouldCommit → fields → commit | Đừng dùng shouldCommit trước khi có final duration |
| Theo dõi exception | begin → try/catch ghi outcome → finally end/commit | Rethrow lỗi, không bỏ commit vì return/throw sớm |
| Span xử lý bất đồng bộ | Một event per logical operation, đo từ lúc bắt đầu đến khi callback hoàn thành nếu đó là phạm vi cần đo | Dùng correlation ID, ownership rõ ràng; không mutate cùng instance đồng thời |
| Recording chờ được bật động | isEnabled guard trong đường nóng | Guard là quyết định tại một thời điểm, có thể thay đổi theo recording |
| Trường telemetry tốn chi phí | shouldCommit sau end rồi mới tính field | Tránh side effect nghiệp vụ trong nhánh telemetry |

**Không nhầm duration với CPU time.** Một event có 500 ms duration vì chờ khóa, chờ socket hoặc Thread.sleep vẫn chỉ đo **elapsed time**. Nếu cần CPU time, allocation hoặc lock contention, nên thu thêm event chuẩn thích hợp (ExecutionSample, ThreadPark, JavaMonitorEnter, File/Socket I/O) và tương quan timestamps.

## 9. Hiểu overhead và tránh ghi quá nhiều dữ liệu

JFR được thiết kế cho quan sát hiệu quả, nhưng **custom event vẫn có chi phí**. Tần suất event, stack recording, số lượng field, công việc tạo payload và phạm vi retention của recording đều ảnh hưởng đến CPU, bộ nhớ và kích thước file.

Một số thực hành tốt:

1. Chỉ phát event ở **điểm có ý nghĩa**: request hoàn tất, batch xử lý, truy vấn chậm, retry đáng chú ý. Tránh phát ở mỗi vòng lặp hạt nhỏ khi không có nhu cầu.
2. Dùng **threshold** để ưu tiên operation chậm, nhưng biết rằng sample đã bị lọc không thể phục hồi từ file sau đó.
3. Đặt **isEnabled()** trước logic chỉ dành cho instrumentation; đặt **shouldCommit()** sau duration để tránh serialize, format string hoặc chụp dữ liệu đắt tiền không cần.
4. **Không đưa toàn bộ HTTP body, thông tin xác thực, token, SQL params nhạy cảm hoặc đối tượng lớn vào event**. Dùng status, số lượng, loại operation, correlation ID không nhạy cảm và các trường nhỏ.
5. JFR Event fields được hỗ trợ trực tiếp là **primitive, String, Thread, Class**. Các reference field như Map, List, Throwable, mảng hoặc enum không trở thành payload tuỳ ý trong recording theo cơ chế mặc định; chúng có thể bị JFR bỏ qua khi tạo event type. Chuyển thông tin thành trường nhỏ có kiểu được hỗ trợ.
6. Tránh tạo **stack trace thủ công** trong code chỉ để điền String khi JFR có thể thu stack tại commit bằng setting phù hợp.
7. Không xem event như cơ chế audit transaction bắt buộc hoặc message queue bảo đảm giao nhận; recording có chính sách lưu trữ và có thể bị tắt, lọc, hết dung lượng hoặc chỉ được dump sau khi sự cố đã qua.
8. Giới hạn maxAge/maxSize và áp dụng chính sách bảo vệ file khi dùng recording lâu; JFR có thể chứa class, method, thread, path và thông tin nghiệp vụ nhạy cảm.

### Khi nào dùng isEnabled() mà không dùng shouldCommit()?

Với event instant hoặc threshold=0, isEnabled() có thể đủ cho phần guard. Nếu field luôn rất rẻ, gọi commit() trực tiếp cũng hợp lệ. Nhưng trong đoạn xử lý có threshold >0 và payload phải format đáng kể, nên dùng cả hai: **isEnabled sớm, shouldCommit muộn**.

### Khi nào không nên bắt đầu event quá sớm?

Nếu begin() chạy trước khi request được đưa vào queue, duration đo cả **queue wait + execution**. Nếu mục tiêu là **execution time**, begin() phải nằm ở worker lúc thực sự bắt đầu xử lý. Nếu muốn đo end-to-end latency, bao gồm queue wait lại là chủ ý đúng. Đặt tên event và mô tả để người đọc không nhầm hai loại thời gian.

## 10. Chẩn đoán khi custom event “biến mất”

Khi đã gọi commit() mà file không có type/instance mong đợi, kiểm tra theo thứ tự:

1. **Đúng JVM/file/period chưa?** Recording phải chạy lúc operation diễn ra; file phải được dump từ recording đó.
2. **Event type có enabled trong ít nhất một recording đang chạy không?** Kiểm tra cấu hình và isEnabled() tại điểm chạy; tên event có thể khác tên class nếu dùng @Name.
3. **Threshold có loại event không?** Một 2 ms operation không xuất hiện với threshold 25 ms là bình thường. Đừng xóa threshold trong production chỉ để nhìn thấy dữ liệu mà không cân nhắc overhead.
4. **Event có được commit() trên đường thực tế không?** Return/exception có thể bỏ qua nếu không đặt trong finally.
5. **begin/end có bao lấy công việc không?** Commit instant hoặc kết thúc quá sớm tạo duration gần zero và bị threshold loại.
6. **shouldCommit() có được gọi sau end không?** Gọi trước khi công việc kết thúc có thể dẫn đến quyết định lọc sai hoặc khiến bạn hiểu sai cơ chế.
7. **Có nhiều recording với thresholds khác nhau không?** shouldCommit() dựa trên ngưỡng tối thiểu từ những recording đang chạy; không có nghĩa mọi file đều có instance.
8. **File JFR đã stop/dump đủ dữ liệu và đọc đúng event type chưa?** Dùng **jfr summary**, **jfr metadata** và **jfr print --events**.
9. **Có dữ liệu bị giới hạn/lost, recording rotation hoặc khác biệt JDK không?** Đừng dùng sự vắng mặt của event như bằng chứng duy nhất về hành vi ứng dụng.

### Ba mẫu lỗi thường gặp

**Lỗi A — đo sai phạm vi**

~~~java
doBusinessWork();
event.begin();
event.end();
event.commit();
~~~

Duration gần zero và không phản ánh doBusinessWork(). Đặt begin trước phần cần đo và end sau phần cần đo.

**Lỗi B — mất event khi xử lý lỗi**

~~~java
event.begin();
doBusinessWork(); // Nếu throw, hai lệnh sau không chạy.
event.end();
event.commit();
~~~

Dùng finally để đóng event; catch nếu cần ghi outcome. Vẫn bảo toàn exception.

**Lỗi C — tính payload tốn chi phí dù event không đạt threshold**

~~~java
event.end();
event.details = expensiveSerialize();
if (event.shouldCommit()) {
    event.commit();
}
~~~

Đặt shouldCommit() **trước expensiveSerialize()**. Nhưng nếu expensiveSerialize() là việc nghiệp vụ cần chạy bất kể JFR, không được chuyển nó vào nhánh điều kiện; tách dữ liệu nghiệp vụ và telemetry.

## 11. Bài tập phân tích trước–sau

### Bài 1. Tại sao nên gọi end() trước buildDetails()?

Một request chạy 12 ms, buildDetails() chạy 80 ms, threshold 50 ms.

- Nếu gọi **commit() sau buildDetails()** mà chưa end(), duration có thể bao gồm cả 80 ms của telemetry và event trông như một request chậm.
- Nếu **end() ngay sau business work**, duration phản ánh 12 ms; **shouldCommit()** loại event theo ngưỡng 50 ms, tránh chạy buildDetails().

Đó là lý do ranh giới đo và thứ tự kiểm tra phải do mục tiêu phân tích quyết định.

### Bài 2. Hai recordings, một event

Recording A bật event threshold=20 ms; B bật cùng event threshold=200 ms. Operation mất 75 ms.

**Kết luận:** isEnabled() có thể true; shouldCommit() có thể true do ngưỡng nhỏ nhất là 20 ms. Sự kiện phù hợp ngưỡng của A, chưa phù hợp ngưỡng của B. Không được kỳ vọng cả hai file chứa record của operation này.

### Bài 3. Event type enabled nhưng method không chạy

Ứng dụng chỉ gọi operation khi có request, recording bật nhưng không có request nào trong khoảng thu. Summary không thấy event. Có lỗi JFR không?

**Kết luận:** không thể kết luận là lỗi. Không có instance vì điểm instrumented không được chạy; cần đối chiếu traffic, invocation và recording interval.

### Bài 4. Code có return trong try

~~~java
event.begin();
try {
    if (cacheHit()) {
        return cached();
    }
    return compute();
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.commit();
    }
}
~~~

**Kết luận:** finally vẫn thực thi khi return bình thường; event kết thúc và được commit nếu settings/threshold cho phép. Để biết cache hit hay miss, bổ sung field hợp lệ trước commit.

### Bài 5. Có 500 ms duration trong JFR, suy CPU cao được không?

**Kết luận:** chưa đủ. 500 ms là elapsed duration theo begin/end. Có thể là chờ I/O, lock, sleep, scheduling hoặc CPU. Cần correlation với CPU samples, lock/park và I/O events để xác định nguyên nhân.

## 12. Checklist dùng trong code review

- **Event class** có tên và category dễ tra cứu? Field chỉ chứa kiểu được hỗ trợ, ngắn gọn, không rò thông tin nhạy cảm?
- **Business logic** luôn chạy dù JFR tắt? Không đặt side effect nghiệp vụ sau điều kiện shouldCommit?
- **begin/end** bao đúng đoạn cần đo? Có try/finally bảo đảm end trên return/throw?
- **commit** được gọi với field đã điền? Nếu không cần duration, instant commit có phù hợp hơn không?
- **isEnabled** đặt sớm cho instrumentation tốn chi phí? **shouldCommit** đặt sau end trước bước tạo payload đắt tiền?
- **Settings** có xác định threshold, enabled và stackTrace rõ ràng? Có cân nhắc nhiều recording đang chạy?
- **Java exceptions/interruption** được giữ đúng hợp đồng, outcome được ghi mà không nuốt lỗi?
- **QA thực tế** có chạy jfr summary/print để xác nhận instances, field, duration và filtering, đồng thời ghi rõ khoảng recording?

## Tài liệu tham khảo

- [Oracle JDK 21 — jdk.jfr.Event API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html): begin, end, commit, isEnabled, shouldCommit và kiểu field hỗ trợ.
- [Oracle JDK 21 — jdk.jfr.EventSettings API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): enabled, threshold, stack trace và settings.
- [Oracle JDK 21 — jdk.jfr.Recording API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): enable, start, stop, dump và vòng đời recording.
- [Oracle JDK 21 — jdk.jfr.Threshold annotation](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Threshold.html): mặc định threshold theo event type.
- [Oracle JDK 21 — jdk.jfr.consumer.RecordedEvent API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): duration, startTime, endTime, thread và stack khi đọc lại.
- [Oracle JDK 21 — JFR package và predefined settings](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html): enabled, threshold, stackTrace semantics.
- [Oracle JDK 21 — jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): summary, metadata và print trên file .jfr.
