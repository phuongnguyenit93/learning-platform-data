# JFR để tương quan GC, allocation và độ trễ ứng dụng (Java 15+)

## 1. Mục tiêu bài học

**Java Flight Recorder (JFR)** là hệ thống ghi nhận sự kiện hiệu năng tích hợp trong JDK/HotSpot. Thay vì chỉ nhìn một chỉ số “GC pause dài”, JFR giúp đặt nhiều sự kiện lên **cùng trục thời gian** để điều tra:

- **GC:** khi nào một đợt GC bắt đầu, khi nào ứng dụng bị dừng ở `jdk.GCPhasePause`, chu kỳ nào kéo dài.
- **Allocation:** thread/stack nào tạo áp lực cấp phát bộ nhớ; mức độ mẫu và độ chi tiết phụ thuộc sự kiện và phiên bản JDK.
- **Độ trễ ứng dụng:** request, job hoặc giao dịch nào mất nhiều thời gian; có thể ghi bằng **custom JFR events** với thời điểm bắt đầu/kết thúc, route và request ID không nhạy cảm.
- **Nguyên nhân khác:** CPU, safepoints, locks, thread parking, I/O, thread scheduling; không mặc định “request chậm = GC”.

Trọng tâm là **tương quan (correlation)**, không đánh đồng với **quan hệ nhân quả (causation)**. Nếu một request và GC pause chồng nhau, pause **có thể** góp phần vào độ trễ. Nhưng phải kiểm tra pause dài bao nhiêu, request có bị block bởi GC không, và các nguyên nhân cạnh tranh như database, network, queue hay locks.

### Ví dụ điều tra

Một dịch vụ có SLO **p99 request latency < 50 ms**, nhưng tại một thời điểm p99 tăng lên 200 ms. Trong recording có:

~~~text
12:00:00.100   request /checkout bắt đầu
12:00:00.105   allocation burst trên application threads
12:00:00.110   GC pause bắt đầu
12:00:00.118   GC pause kết thúc             (8 ms)
12:00:00.300   request /checkout kết thúc    (200 ms)
~~~

Ví dụ này cho thấy request **chồng lên** GC pause 8 ms, nhưng chưa giải thích 192 ms còn lại. Nếu dùng JFR chỉ để nói “request chậm 200 ms do GC” thì đã **kết luận vượt dữ liệu**.

Bài hướng dẫn cách ghi, xem và phân tích các loại sự kiện, xây ví dụ Java có thể biên dịch với **`--release 15`**, và phân biệt chức năng hiện hành với điểm khác biệt giữa các thế hệ JDK.

## 2. JFR là gì, và công cụ nào làm việc gì?

JFR ghi dữ liệu vào **recording `.jfr`**, gồm sự kiện JVM và **custom events** của ứng dụng. Mỗi loại sự kiện có metadata và fields, chẳng hạn `startTime`, `duration`, `eventThread`, GC ID, class được cấp phát hoặc route.

| Thành phần | Chức năng | Khi nào dùng |
| --- | --- | --- |
| **JFR runtime** (module `jdk.jfr`) | Thu thập các event đã bật, tạo recording. | Chạy trong JVM của ứng dụng. |
| **`-XX:StartFlightRecording`** | Khởi động recording khi JVM bắt đầu. | Khi khởi động service với cấu hình chủ động. |
| **`jcmd ... JFR.start/JFR.dump`** | Điều khiển recording của JVM đang chạy, khi cho phép attach. | Chẩn đoán một tiến trình hiện có. |
| **`jfr summary`** | Xem loại sự kiện, số lượng và kích thước trong file. | Kiểm tra dữ liệu thực sự được ghi. |
| **`jfr print`** | In chi tiết sự kiện theo tên loại. | Kiểm tra thời gian, duration, field cụ thể. |
| **`jdk.jfr.consumer.RecordingFile`** | Đọc/analyze events bằng Java. | Tạo công cụ phân tích/sanity checks. |
| **JDK Mission Control (JMC)** | Giao diện xem timeline, GC, allocations, hot methods, threads. | Điều tra trực quan, tìm mẫu tương quan. |

JFR được hỗ trợ từ trước Java 15 và **vẫn là công cụ hiện hành**. Không dùng những tùy chọn thương mại cũ như `-XX:+UnlockCommercialFeatures` từ các hướng dẫn JDK 8 đã lỗi thời. JMC là **ứng dụng phân tích riêng**, không phải class Java tiêu chuẩn tự động có trong mọi JDK.

### 2.1. `default.jfc` và `profile.jfc`

JFR cung cấp các profile cấu hình:

- **`default`**: hướng tới thu thập liên tục với overhead thấp.
- **`profile`**: thu nhiều dữ liệu hơn, hữu ích khi điều tra nguyên nhân nhưng có thể tăng overhead.

Không mặc định mọi loại sự kiện đều được bật ở mọi profile/JDK. **Bước đầu tiên sau khi ghi phải là `jfr summary`** để xem recording thực tế có chứa GC pause, allocation và custom request events hay không.

**Overhead cần đo:** JFR tương đối nhẹ khi dùng hợp lý, nhưng event volume lớn, stack traces, bật allocation events chi tiết hoặc recording ở profile mode có thể làm thay đổi chính latency mà ta muốn quan sát. Đánh giá overhead trên đúng workload, không coi luôn bằng 0.

## 3. Ba nhóm sự kiện cốt lõi để điều tra

### 3.1. `jdk.GCPhasePause`: đo thời gian ứng dụng tạm dừng

Đây là loại sự kiện quan trọng khi muốn trả lời **“GC đã dừng ứng dụng bao lâu?”**.

Một event thường mang:

- `startTime`: thời điểm bắt đầu pha dừng.
- `duration`: độ dài pha dừng.
- `gcId`: ID liên hệ các sự kiện trong cùng collection.
- `name`: nhãn pha, tùy collector/runtime.

Để in:

~~~bash
jfr print --events jdk.GCPhasePause run.jfr
~~~

**Không lấy `jdk.GarbageCollection.getDuration()` thay cho pause.** Một chu kỳ G1, ZGC hoặc Shenandoah có thể có phần lớn công việc **concurrent**, nghĩa là ứng dụng vẫn chạy trong khoảng thời gian ấy. Cần lấy những `GCPhasePause` events hoặc sự kiện pause tương ứng để tính histogram p50/p95/p99/max.

Có thể có nhiều phase pause trong cùng một GC cycle. Nếu muốn tính tổng pause theo một GC, nhóm theo `gcId` và cộng **chỉ những khoảng pause phù hợp**, tránh cộng concurrent duration hoặc đếm trùng các event phân cấp của pha.

### 3.2. Allocation: được cấp phát ở đâu, không phải mọi object còn sống

Allocation là quá trình tạo object mới. Allocation rate cao có thể tăng áp lực GC, nhưng **số bytes được cấp phát không đồng nghĩa live heap**, và phát hiện nơi cấp phát nhiều không tự chứng minh memory leak.

Các sự kiện có thay đổi quan trọng theo JDK:

| Sự kiện | Phạm vi Java | Đặc điểm |
| --- | --- | --- |
| `jdk.ObjectAllocationSample` | **JDK 16+** | Mẫu phân bổ object có `objectClass`, stack trace/thread tùy settings và **`weight`** ước lượng áp lực allocation. Được thiết kế cho allocation profiling overhead thấp hơn so với hai event TLAB chi tiết. |
| `jdk.ObjectAllocationInNewTLAB` | **Có ở Java 15** và các JDK tương ứng | Ghi các allocation khi tạo TLAB; phải hiểu sampling/semantics của event. Có thể tạo nhiều data và overhead. |
| `jdk.ObjectAllocationOutsideTLAB` | **Có ở Java 15** và các JDK tương ứng | Ghi các allocation ngoài TLAB; dùng bổ sung theo profile phù hợp. |
| `jdk.ThreadAllocationStatistics` | Có ở JFR trên các JDK tương ứng | Thống kê tổng lượng cấp phát theo thread ở những điểm đo, hữu ích để định hướng. Không thay object-level stack samples. |

**Điểm áp dụng Special Note:** Java 15 **không có** `jdk.ObjectAllocationSample`; event này được giới thiệu ở **JDK 16**, và JDK 16 bật nó trong `default`/`profile` với giới hạn event rate. Do vậy, một bài Java 15 không nên hướng dẫn “luôn dùng `jdk.ObjectAllocationSample`” mà bỏ qua khác biệt phiên bản.

Trên JDK 16+:

~~~bash
jfr print --events jdk.ObjectAllocationSample run.jfr
~~~

Trên JDK 15, cần xem `jdk.ObjectAllocationInNewTLAB` và `jdk.ObjectAllocationOutsideTLAB` nếu đã bật các event này trong cấu hình ghi.

**Không cộng số event để ra tổng số object thực tế.** Đối với `jdk.ObjectAllocationSample`, các events là **samples**, không phải một event cho mỗi object. Phân tích allocation theo loại class/stack nên cân nhắc `weight` và sample rate; số lượng samples nhỏ có độ bất định cao. Việc so sánh giữa hai recordings cần giữ settings và môi trường phù hợp.

### 3.3. Custom application event: quan sát độ trễ request

JFR không tự biết “thời điểm HTTP request của ứng dụng bắt đầu/kết thúc” theo semantic nghiệp vụ của bạn. Bạn có thể tạo event:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Label;
import jdk.jfr.Category;

@Name("lesson.Request")
@Label("Application request")
@Category({"Lesson", "Application"})
class RequestEvent extends Event {
    @Label("Route")
    public String route;

    @Label("Request id")
    public int requestId;
}
~~~

Một request được đo bằng:

~~~java
RequestEvent event = new RequestEvent();
event.route = "/api/items";
event.requestId = 42;
event.begin();
try {
    // Thuc thi request.
} finally {
    event.commit(); // Ghi duration tu begin den luc commit.
}
~~~

Hai đoạn trên **minh họa**; chương trình Java đầy đủ ở mục 7 có sẵn mọi imports và fields. Nên dùng `finally` để ghi event ngay cả khi công việc gặp lỗi; với production, cân nhắc thêm trạng thái `success/error` (không ghi raw payload nhạy cảm).

**Quan trọng:** JFR `Event` là dữ liệu đo **thời gian operation ở chính vị trí bạn đặt begin/commit**. Nếu request đi qua queue hoặc xử lý asynchronous, một event chỉ bọc method cục bộ có thể **không chứa thời gian chờ queue** hoặc toàn bộ lifecycle. Cần xác định điểm bắt đầu/kết thúc phù hợp với SLO của người dùng.

## 4. Tương quan trên timeline: cách đọc có trách nhiệm

Khi có ba nhóm sự kiện, đặt chúng lên **cùng trục thời gian của một recording**:

~~~text
Time ---+--------------------+-------------------+---->
Request A  [--------------------------------]
GC pause             [====]
Allocation             ^ ^ ^ ^ ^ ^ ^ 
DB call                     [----------------]
Request B                         [----]
~~~

Trong đó:

- `[====]` chỉ một GC pause.
- `^` chỉ các allocation samples, không phải tất cả allocation.
- Request durations bao gồm khoảng thời gian được custom event bọc.
- DB call cần được ghi bằng tracing hoặc JFR event phù hợp nếu muốn kiểm tra trực tiếp.

### 4.1. Tính giao nhau của hai khoảng thời gian

Gọi request có khoảng `[reqStart, reqEnd]` và GC pause có `[pauseStart, pauseEnd]`. Hai khoảng **có giao nhau** khi:

~~~text
reqEnd > pauseStart  AND  pauseEnd > reqStart
~~~

Đây là điều kiện **temporal overlap**. Nó giúp lập danh sách request cần điều tra, nhưng không chứng minh phần lớn độ trễ request do GC gây ra.

Nếu GC pause chỉ dài 2 ms, một request dài 200 ms có thể chồng lên pause đó trong 2 ms. Muốn ước lượng ảnh hưởng, cần lấy **độ dài phần giao** và xem các hoạt động khác; kể cả vậy, ảnh hưởng lên request phụ thuộc thread state và scheduling, không nhất thiết bằng đúng thời gian giao.

### 4.2. Dùng cùng đồng hồ và hiểu timestamp

Trong một recording, `RecordedEvent.getStartTime()`, `getEndTime()` và `getDuration()` là lựa chọn phù hợp để ghép các sự kiện.

Nếu ghép dữ liệu **nhiều JVM/server** hoặc với dashboard bên ngoài:

- Xác định timezone/timestamp format.
- Kiểm tra clock synchronization và sai lệch thời gian.
- Dùng trace/span IDs hoặc request IDs ổn định giữa các thành phần.
- Không kết luận sự kiện đồng thời chính xác nếu clocks lệch vài chục milliseconds.

JFR event mặc định không tự mang distributed trace ID của mọi framework. Bạn phải tự kết nối dữ liệu telemetry, custom fields hoặc context propagation theo thiết kế ứng dụng.

### 4.3. Tương quan với allocation stack và thread

Một quy trình điều tra hợp lý:

1. Chọn một cửa sổ request p99 tăng bất thường.
2. Tìm custom `lesson.Request` events trong cửa sổ, xem route, ID và duration.
3. Lọc `jdk.GCPhasePause` cùng khoảng thời gian, phân tích số lần, tổng và max pause.
4. Lọc allocation samples của thời đoạn trước/giữa spike, phân nhóm theo `objectClass`, stack trace và thread khi dữ liệu có.
5. Xác định hot allocation paths: JSON parsing, buffer copying, temporary collections, serialization...
6. Đối chiếu CPU, contention, I/O và database spans.
7. Đề xuất một giả thuyết có thể thử, ví dụ giảm allocations ở đoạn parse, điều chỉnh heap hoặc so sánh collector.
8. Đo lại dưới cùng workload và xem end-to-end SLO có cải thiện không.

**Không coi “stack có nhiều samples” là bằng chứng chắc chắn memory leak.** Allocation hotspot thường tạo nhiều object sống ngắn; memory leak là **retained heap/liveness** tăng không hợp lý, cần dữ liệu/điều tra khác.

## 5. Cách thu JFR từ tiến trình Java đang chạy

### 5.1. Khi khởi động JVM

Ví dụ:

~~~bash
java -Xms512m -Xmx512m -XX:+UseG1GC \
  -XX:StartFlightRecording=filename=service.jfr,settings=profile,dumponexit=true \
  -jar service.jar
~~~

Đây là lệnh **minh họa**, yêu cầu ứng dụng `service.jar` thực tế. Dấu `\` là nối dòng kiểu Bash; PowerShell có cú pháp khác, hoặc dùng một dòng.

- `settings=profile` thu thông tin chi tiết hơn `default`.
- `filename` xác định file ghi khi dump/stop.
- `dumponexit=true` ghi recording khi JVM kết thúc theo đường đi hỗ trợ.
- `-Xms/-Xmx` là heap ví dụ, không phải khuyến nghị phải bằng nhau cho mọi ứng dụng.

Một service sống lâu không cần đợi exit mới phân tích. Có thể lấy snapshot/dump khi ứng dụng đang chạy bằng `jcmd` (khi cho phép attach), lưu tập tin ngắn/đủ dài phù hợp.

### 5.2. Gắn recording vào process hiện có

Tìm PID bằng công cụ phù hợp trong môi trường rồi dùng:

~~~bash
jcmd 12345 JFR.start name=latency settings=profile duration=60s filename=latency.jfr
~~~

Trong đó `12345` là **PID ví dụ**; thay bằng PID JVM của bạn. `duration=60s` là thời lượng demo, không nhất thiết đủ thu event hiếm. Để dump trước/giữa vòng ghi, có thể dùng:

~~~bash
jcmd 12345 JFR.dump name=latency filename=latency-snapshot.jfr
~~~

Điều kiện: công cụ `jcmd` có quyền attach vào process, JDK/JVM hỗ trợ JFR và filesystem đủ dung lượng. Trong container hoặc server có chính sách bảo mật, attach có thể bị cấm; không tự thay đổi security controls.

### 5.3. Xác nhận sự kiện thực sự tồn tại

~~~bash
jfr summary latency.jfr
jfr print --events jdk.GCPhasePause latency.jfr
jfr print --events jdk.ObjectAllocationSample latency.jfr
~~~

Trên JDK 15, **thay allocation event** bằng `jdk.ObjectAllocationInNewTLAB` / `jdk.ObjectAllocationOutsideTLAB` đã bật. Nếu `summary` báo 0 event, không tự kết luận không có vấn đề: có thể chưa bật, chưa đủ thời gian, GC chưa xảy ra, sampling/threshold đã lọc, hoặc recording không bao phủ lúc sự cố.

### 5.4. Custom event có được ghi tự động không?

Cần JFR bật **đúng event name** và không bị lọc bởi threshold. Với một request event:

- `event.begin()` bắt đầu đo duration.
- `event.commit()` hoàn tất và ghi nếu event đang enabled và thỏa điều kiện.
- `@Threshold("20 ms")` sẽ làm event nhanh hơn ngưỡng có thể bị loại.
- `recording.enable(MyEvent.class).withThreshold(Duration.ZERO)` yêu cầu ghi cả event ngắn trong một recording thử nghiệm.
- `Event.shouldCommit()` có thể giúp tránh tính những fields đắt tiền khi event không cần lưu.

**Trong production, không nên ghi một custom event cho từng request nếu QPS rất lớn mà chưa tính overhead và volume.** Có thể áp sampling, threshold chỉ ghi request chậm, hoặc rút gọn fields theo nhu cầu.

## 6. Sự kiện allocation thay đổi theo phiên bản: cách viết code bền vững

Trong Java 15, `jdk.ObjectAllocationSample` **chưa được giới thiệu**. Nếu ứng dụng yêu cầu code chạy được ở Java 15 **và** JDK mới, hãy kiểm tra event types có sẵn thay vì bật cố định tên event của JDK 16+.

Ví dụ:

~~~java
boolean hasObjectAllocationSample =
    FlightRecorder.getFlightRecorder().getEventTypes().stream()
        .anyMatch(type ->
                type.getName().equals("jdk.ObjectAllocationSample"));

if (hasObjectAllocationSample) {
    recording.enable("jdk.ObjectAllocationSample");
} else {
    recording.enable("jdk.ObjectAllocationInNewTLAB");
    recording.enable("jdk.ObjectAllocationOutsideTLAB");
}
~~~

Đây là code **trong ngữ cảnh có `recording` và imports JFR**; chương trình hoàn chỉnh ở mục sau bao gồm đủ phần đó.

Không bật hai event TLAB cũ trong profile môi trường production chỉ vì muốn “có nhiều dữ liệu”, do chi phí có thể cao. JDK 16 đưa `jdk.ObjectAllocationSample` vào cấu hình mặc định/profile để hỗ trợ low-overhead allocation profiling. Ngược lại, **events TLAB chi tiết** phù hợp với việc điều tra chọn lọc ngắn hạn khi nhu cầu dữ liệu cụ thể rõ ràng.

### 6.1. Sample weight không phải một object byte-count chính xác

`jdk.ObjectAllocationSample` thường có `weight` là **trọng số mẫu**, giúp ước lượng phân bố allocation pressure khi tổng hợp nhiều samples. Không nên:

- Diễn giải “60 events” = chỉ có 60 objects được tạo.
- Dùng số lượng event theo class như lượng bytes cấp phát thật.
- Dùng sample trong 1 giây để xếp hạng p99 hay memory leak.
- Cộng fields từ hai loại event khác semantics mà không chuẩn hóa.
- Xem allocation samples là kết quả của retained-heap analysis.

JFR cung cấp thông tin **quan sát/thống kê**, không thay thế phép đo end-to-end và phân tích vùng heap còn sống.

## 7. Chương trình Java hoàn chỉnh: ghi request, GC pause và allocation vào một file JFR

Ví dụ sau có thể biên dịch bằng **API Java 15** và chạy trên JDK hỗ trợ JFR. Nó:

1. Tạo **custom event `lesson.Request`** với ID, route, cờ cố tình sleep và số bytes **ước tính theo code demo**.
2. Mở `Recording` với cấu hình `profile`.
3. Bật `jdk.GCPhasePause`, custom event, và allocation event phù hợp với phiên bản JDK.
4. Chạy **160 request mô phỏng**, mỗi request cấp phát nhiều byte arrays; 4 request cố tình sleep 12 ms để cho thấy **độ trễ có nguyên nhân không phải GC**.
5. Dump `gc-latency-demo.jfr`.
6. Đọc file qua `RecordingFile.readAllEvents`, đếm event, kiểm tra **giao nhau thời gian** giữa request và GC pause, rồi in số liệu.
7. Không cố quy kết mọi request chậm là vì GC, và không in payload bí mật.

### 7.1. Mã `JfrGcLatencyDemo.java`

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrGcLatencyDemo {
    @Name("lesson.Request")
    @Label("Simulated application request")
    @Category({"Lesson", "Application"})
    @StackTrace(false)
    @Threshold("0 ms")
    static final class RequestEvent extends Event {
        @Label("Request id")
        public int requestId;
        @Label("Route")
        public String route;
        @Label("Intentional delay")
        public boolean intentionalDelay;
        @Label("Bytes created by demonstration")
        public long allocatedBytes;
    }

    private static volatile int sink;

    private static void runRequests() throws InterruptedException {
        byte[][] retained = new byte[128][];
        for (int id = 0; id < 160; id++) {
            RequestEvent event = new RequestEvent();
            event.requestId = id;
            event.route = "/api/items";
            event.intentionalDelay = (id % 40 == 0);
            long allocated = 0;
            event.begin();
            try {
                for (int chunk = 0; chunk < 256; chunk++) {
                    byte[] data = new byte[8192 + ((id + chunk) % 4) * 1024];
                    data[0] = (byte) id;
                    data[data.length - 1] = (byte) chunk;
                    sink += data[0] + data[data.length - 1];
                    if ((chunk & 31) == 0) {
                        retained[(id + chunk) % retained.length] = data;
                    }
                    allocated += data.length;
                }
                if (event.intentionalDelay) {
                    Thread.sleep(12);
                }
            } finally {
                event.allocatedBytes = allocated;
                event.commit();
            }
        }
    }

    private static boolean overlaps(RecordedEvent request, RecordedEvent pause) {
        Instant startA = request.getStartTime();
        Instant endA = request.getEndTime();
        Instant startB = pause.getStartTime();
        Instant endB = pause.getEndTime();
        return endA.isAfter(startB) && endB.isAfter(startA);
    }

    private static void inspect(Path file) throws Exception {
        List<RecordedEvent> requests = new ArrayList<>();
        List<RecordedEvent> pauses = new ArrayList<>();
        long allocationSamples = 0;
        int intentionalDelays = 0;

        for (RecordedEvent event : RecordingFile.readAllEvents(file)) {
            String type = event.getEventType().getName();
            if (type.equals("lesson.Request")) {
                requests.add(event);
                if (event.getBoolean("intentionalDelay")) {
                    intentionalDelays++;
                }
            } else if (type.equals("jdk.GCPhasePause")) {
                pauses.add(event);
            } else if (type.equals("jdk.ObjectAllocationSample")
                    || type.equals("jdk.ObjectAllocationInNewTLAB")
                    || type.equals("jdk.ObjectAllocationOutsideTLAB")) {
                allocationSamples++;
            }
        }

        int requestsOverlappingPauses = 0;
        long slowestRequestMs = 0;
        for (RecordedEvent request : requests) {
            slowestRequestMs = Math.max(slowestRequestMs,
                    request.getDuration().toMillis());
            for (RecordedEvent pause : pauses) {
                if (overlaps(request, pause)) {
                    requestsOverlappingPauses++;
                    break;
                }
            }
        }

        System.out.println("recordingPresent=" + (Files.size(file) > 0));
        System.out.println("requestEvents=" + requests.size());
        System.out.println("intentionalDelays=" + intentionalDelays);
        System.out.println("gcPauseEvents=" + pauses.size());
        System.out.println("allocationSampleEvents=" + allocationSamples);
        System.out.println("requestsOverlappingGcPause=" + requestsOverlappingPauses);
        System.out.println("slowestRequestMs=" + slowestRequestMs);
        System.out.println("correlationInvariant=" +
                (requestsOverlappingPauses <= requests.size()));
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of(args.length > 0 ? args[0] : "gc-latency-demo.jfr");

        boolean modernAllocationEvent = FlightRecorder.getFlightRecorder()
                .getEventTypes().stream()
                .anyMatch(type ->
                        type.getName().equals("jdk.ObjectAllocationSample"));

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("profile"))) {
            recording.enable(RequestEvent.class)
                    .withThreshold(Duration.ZERO).withoutStackTrace();
            recording.enable("jdk.GCPhasePause")
                    .withThreshold(Duration.ZERO);
            if (modernAllocationEvent) {
                recording.enable("jdk.ObjectAllocationSample");
            } else {
                recording.enable("jdk.ObjectAllocationInNewTLAB");
                recording.enable("jdk.ObjectAllocationOutsideTLAB");
            }

            recording.start();
            runRequests();
            recording.stop();
            recording.dump(output);
        }

        System.out.println("allocationMode=" +
                (modernAllocationEvent ? "sample" : "tlab"));
        inspect(output);
    }
}
~~~

### 7.2. Cách biên dịch và chạy

Từ thư mục có file nguồn:

~~~bash
javac --release 15 -encoding UTF-8 JfrGcLatencyDemo.java
java -Xms64m -Xmx64m -XX:+UseG1GC JfrGcLatencyDemo gc-latency-demo.jfr
~~~

**`--release 15`** giúp kiểm tra mã chỉ dùng API/ngôn ngữ hỗ trợ Java 15. JFR thuộc module chuẩn `jdk.jfr` trong JDK, không cần Maven dependency.

Heap 64 MiB được chọn **riêng cho demo** để tạo áp lực allocation/GC trong thời gian ngắn; không có ý nghĩa tuning production. Nếu runtime cụ thể không hỗ trợ JFR hoặc ghi file, cần bật module/cấu hình phù hợp và quyền ghi filesystem.

### 7.3. Output thực tế đã kiểm thử

Chạy trên **JDK 24 Azul Zulu**, compiler `--release 15`, với G1 và heap 64 MiB:

~~~text
allocationMode=sample
recordingPresent=true
requestEvents=160
intentionalDelays=4
gcPauseEvents=11
allocationSampleEvents=60
requestsOverlappingGcPause=11
slowestRequestMs=13
correlationInvariant=true
~~~

Các số `gcPauseEvents`, `allocationSampleEvents`, `requestsOverlappingGcPause` và `slowestRequestMs` **không cố định**; chúng phụ thuộc JDK, CPU, JIT, GC, OS, sampling và tình trạng máy. Chúng là stdout của một lần kiểm thử thực, không phải “expected output” bất biến.

Trong lần thử đó, chạy:

~~~bash
jfr summary gc-latency-demo.jfr
~~~

xác nhận recording chứa:

~~~text
lesson.Request                     160 events
jdk.ObjectAllocationSample          60 events
jdk.GCPhasePause                    11 events
jdk.GarbageCollection               11 events
~~~

Đây là **bản tóm tắt đã lược các cột size**, không phải toàn bộ output của lệnh `jfr summary`. Nếu dùng JDK 15, `allocationMode=tlab` và tên allocation events có thể khác; số lượng mẫu sẽ khác.

### 7.4. Giải thích output

- `requestEvents=160`: 160 custom events đã được commit, chứng minh thao tác đo request có dữ liệu.
- `intentionalDelays=4`: request IDs 0, 40, 80, 120 đã gọi `Thread.sleep(12)`; vì vậy **có nguyên nhân chậm không liên quan GC** trong demo.
- `gcPauseEvents=11`: recording chứa 11 sự kiện `jdk.GCPhasePause`, không có nghĩa tất cả 11 pauses là nguyên nhân của request chậm.
- `allocationSampleEvents=60`: có 60 **allocation samples**, không phải ứng dụng chỉ cấp phát 60 objects.
- `requestsOverlappingGcPause=11`: 11 request intervals giao với ít nhất một GC pause. **Giao nhau không đồng nghĩa bị GC chi phối toàn bộ duration**.
- `slowestRequestMs=13`: duration làm tròn xuống millisecond của request chậm nhất trong một lần thử.
- `correlationInvariant=true`: số request giao với pause không vượt tổng số request — chỉ là sanity check.

Field `allocatedBytes` trong custom event được cộng từ độ dài mảng do **demo chủ động tạo**, không phải phép đo memory chính xác của JFR, không tính toàn bộ overhead/đối tượng khác, và không dùng thay `jdk.ObjectAllocationSample.weight`.

### 7.5. Tránh dùng `readAllEvents` cho recording quá lớn

`RecordingFile.readAllEvents(file)` tải **toàn bộ events vào memory**, phù hợp với file demo nhỏ. Với production recordings lớn, nên dùng `RecordingFile` đọc tuần tự hoặc công cụ phân tích/streaming thích hợp, giới hạn time range, tránh OOM trong công cụ phân tích.

Trong ứng dụng thật, không tự duyệt mỗi request × mọi GC pause khi lượng event rất lớn (thuật toán demo có thể gần `O(R×G)`). Có thể sắp xếp events theo thời gian và dùng sweep-line hoặc interval indexing để tính giao nhau hiệu quả.

## 8. Phân tích qua JDK Mission Control (JMC)

JMC giúp điều tra **trên cùng timeline**, thay vì tự đọc hàng nghìn dòng `jfr print`.

Một quy trình:

1. Mở file `.jfr` trong phiên bản JMC hỗ trợ các sự kiện của JDK đã ghi.
2. Xem **GC pauses/GC activity** theo thời gian; đánh dấu cửa sổ có pause dài.
3. Xem **Memory/Allocations**: loại object và call stacks có nhiều allocation samples (và trọng số nếu có).
4. Xem **Threads/CPU/Locking/I/O** để tìm contention hoặc hoạt động CPU dài.
5. Tìm **custom event `lesson.Request`** theo route/ID/duration.
6. Giới hạn cùng một **time range** và đối chiếu các sự kiện; xác định giả thuyết.
7. Kiểm chứng bằng traces ứng dụng, metrics và một phép thử tối ưu có kiểm soát.

Một số phiên bản JMC cũ không hiểu `jdk.ObjectAllocationSample` vì event được thêm từ JDK 16. **Hãy dùng phiên bản JMC phù hợp với JDK hiện đại**, không ép hệ thống ghi TLAB events nặng chỉ để tương thích một JMC không còn phù hợp.

## 9. Một ca phân tích đúng và một ca kết luận sai

### 9.1. Kết luận sai

> “JFR báo có 20 GC pauses trong lúc p99 request tăng, vì vậy toàn bộ 200 ms đều là lỗi GC.”

Vì sao sai:

- Không biết từng pause dài bao nhiêu.
- Không biết những request chậm cụ thể có chồng pause không.
- Có thể database hoặc queue là nguyên nhân chính.
- Một thời điểm có allocation burst có thể là **triệu chứng** của tải tăng, không phải nguồn gốc duy nhất.
- JFR allocation samples là mẫu, không phải toàn bộ mọi allocation.

### 9.2. Kết luận có căn cứ hơn

> “Trong cửa sổ 13:00–13:05, p99 request tăng từ 40 ms lên 75 ms. Custom request events cho thấy những requests chậm giao với nhiều `GCPhasePause` có duration 10–25 ms. Allocation samples cùng cửa sổ tập trung ở code JSON serialization. Sau khi giảm allocations và chạy lại cùng tải, tổng pause time và request p99 cùng giảm, trong khi CPU/RSS/error không tăng.”

Kết luận này vẫn phải được thử lặp và phân biệt correlation với causation, nhưng ít nhất nó có **chuỗi bằng chứng và kiểm chứng trước–sau**.

Các số trong ví dụ trên là **giả định để học cách viết báo cáo**, không phải đo từ chương trình ở mục 7.

## 10. Các rủi ro khi thu JFR trên môi trường thật

### 10.1. Recording có thể chứa thông tin nhạy cảm

Stack traces, process arguments, class names, thread names, socket endpoints và custom fields có thể chứa dữ liệu cần bảo vệ. Đừng ghi raw token, password, nội dung request/response nhạy cảm hoặc identifier định danh cá nhân vào custom event khi không thực sự cần.

Áp dụng access control và retention cho file `.jfr`; không đưa recording của production lên nguồn công khai nếu chưa rà soát.

### 10.2. Sampling, thresholds và missing events

Một recording không có `jdk.GCPhasePause` có thể do:

- Không có GC pause trong cửa sổ.
- Event chưa enabled hoặc threshold lọc.
- Recording bắt đầu/kết thúc lệch sự cố.
- Collector và JDK tạo events với tần suất khác mong đợi.
- File bị cắt/mất dữ liệu hoặc tool phân tích không hiểu event.

Allocation samples không có đủ chưa chắc do ứng dụng không cấp phát. Cần xem event configuration, thời gian ghi và `jfr summary`.

### 10.3. Không vô tình thêm một GC để “đo GC”

Một số thao tác heap statistics/old-object analysis hoặc `System.gc()` có thể **tạo thêm GC**. Nếu muốn ghi hành vi tự nhiên của ứng dụng, không bật tính năng khiến heap collection bị cưỡng bức mà không ghi rõ.

Cũng không bật allocation tracing quá chi tiết lâu dài nếu overhead chưa được đánh giá. Nên ưu tiên sampling hiện hành với JDK 16+; trên Java 15, dùng TLAB events **có chọn lọc** và quan sát overhead.

### 10.4. Tính đại diện của khoảng ghi

Một recording vài giây là đủ để kiểm tra code demo, **không đủ** để kết luận tail-latency SLO production. Cần:

- Warm-up, steady state và burst load.
- Đủ mẫu p99/p99.9; số lượng request và pauses kèm thời gian đo.
- Cùng JDK/hardware/container và workload khi so sánh trước–sau.
- Nhiều lần chạy; tránh chọn run đẹp nhất.
- Tương quan với CPU, RSS, GC log và traces.
- Kiểm tra khoảng clock skew nếu ghép nhiều máy.

## 11. Checklist điều tra GC, allocation và application latency

1. **Định nghĩa SLO**: p99/p99.9 request bao nhiêu ms, tại throughput nào, error budget nào?
2. **Ghi đúng vòng đời request**: custom JFR event hoặc traces có start/end rõ, route/trace ID không nhạy cảm.
3. **Kiểm tra JDK version và JFR event types**: JDK 15 TLAB events, JDK 16+ `jdk.ObjectAllocationSample`.
4. **Thu recording có thời gian bao phủ sự cố**: `default` hoặc `profile` theo mục đích và overhead budget.
5. **`jfr summary` trước**: kiểm tra các nhóm event có xuất hiện hay không.
6. **Đọc GC pause events**: histogram, p99, max và tổng pause; không đánh đồng với concurrent cycle.
7. **Tìm request events giao với pauses**: cùng timeline, tính duration phần giao thay vì chỉ đếm GC cycles.
8. **Phân tích allocation samples**: class, thread, stack và `weight`; không coi samples là retained heap.
9. **Kiểm tra nguyên nhân cạnh tranh**: CPU, queues, contention, I/O, database/network.
10. **Đề xuất và thử một thay đổi**: giảm allocation hotspot, đổi cache/lifetime, điều chỉnh heap hoặc collector khi có căn cứ.
11. **Benchmark lại**: latency, throughput, error, CPU/RSS và GC pauses đều phải đạt mục tiêu.
12. **Bảo vệ recording**: giới hạn sensitive fields, quyền truy cập, retention và chi phí ghi/đọc.

## 12. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Xem `jdk.GarbageCollection.duration` là STW pause. | Chu kỳ có concurrent phases. | Dùng `jdk.GCPhasePause` và phân tích GC-specific pauses. |
| Xem `ObjectAllocationSample` là toàn bộ allocations. | Đây là samples, có weight và sampling bias. | Phân tích phân bố/áp lực theo weight, ghi rõ sample policy. |
| Bật `jdk.ObjectAllocationSample` trên Java 15 rồi giả định có dữ liệu. | Event xuất hiện từ JDK 16. | Dùng TLAB events trên JDK 15 nếu cần, kiểm soát overhead. |
| Coi số mẫu allocation như live heap hoặc memory leak. | Allocation rate và object retention khác nhau. | Điều tra live heap/retained data riêng. |
| Không ghi custom events cho request. | JFR không tự biết boundary nghiệp vụ tùy biến. | Tạo `Event` đo operation đúng ranh giới SLO. |
| Tự suy timestamp trùng nhau nghĩa GC gây toàn bộ request delay. | Overlap không phải causation. | Tính giao nhau, phân tích các hoạt động khác, test giả thuyết. |
| Ghi event mọi request ở QPS cao không cân nhắc overhead. | Event volume lớn có thể gây overhead và file lớn. | Dùng threshold/sampling/fields vừa đủ. |
| Chỉ đo p99 operation nội bộ thay cho p99 HTTP. | Đường đo chưa bao gồm toàn bộ request. | Instrument ở ranh giới end-to-end. |
| Không ghi event trước khi bắt đầu ghi JFR. | Không có event để phân tích. | Start JFR trước workload/sự cố; kiểm tra summary. |
| Dùng `readAllEvents` với file vài GB. | Tốn heap của công cụ phân tích. | Đọc tuần tự/stream hoặc dùng JMC. |
| Bật heap dump/forced GC ngay khi benchmark. | Có thể thay đổi chính hành vi GC cần đo. | Ghi tự nhiên, tránh kích GC nhân tạo. |
| Không kiểm tra clock sync giữa nhiều JVM. | Timeline ghép lệch sẽ tạo correlation sai. | Đồng bộ giờ và dùng trace IDs/context. |
| Log raw tokens/passwords trong event. | File .jfr có thể làm lộ bí mật. | Giảm fields, scrub dữ liệu, bảo vệ file. |
| Chọn GC chỉ dựa vào pause thấp. | CPU, RSS, throughput hay p99 application có thể xấu hơn. | So sánh tất cả SLO và resource budgets. |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Một `jdk.GarbageCollection` có `duration=100 ms`. Có thể kết luận ứng dụng dừng 100 ms không?

**Đáp án:** Không. Chu kỳ có thể chạy phần lớn concurrent. Phải xem các `jdk.GCPhasePause` events thực tế để đo STW.

**Câu 2.** JDK 15 có `jdk.ObjectAllocationSample` chưa?

**Đáp án:** Chưa. Event này được giới thiệu từ **JDK 16**. Java 15 có các event TLAB (`jdk.ObjectAllocationInNewTLAB` / `jdk.ObjectAllocationOutsideTLAB`), cần bật với nhận thức về overhead.

**Câu 3.** Tại sao cần custom `lesson.Request` event?

**Đáp án:** Vì JVM không tự biết operation nào tương ứng với request/transaction của ứng dụng. Custom event cung cấp ranh giới start/end và metadata để ghép cùng timeline GC.

**Câu 4.** Một request 200 ms giao với GC pause 3 ms. Có được tuyên bố GC là nguyên nhân của toàn bộ 200 ms không?

**Đáp án:** Không. Có overlap nhưng pause chỉ chiếm một phần nhỏ; phải kiểm tra thread state, I/O, locks, queue và các yếu tố khác.

**Câu 5.** Có 100 `ObjectAllocationSample` events, nghĩa là ứng dụng tạo đúng 100 objects?

**Đáp án:** Không. Đây là samples. Để ước lượng allocation pressure cần cân nhắc weight, sampling và đầy đủ thời gian đo.

**Câu 6.** `Event.commit()` của JFR có tự bảo đảm request được commit ở database không?

**Đáp án:** Không. Nó chỉ kết thúc/ghi một **event đo lường JFR**, không liên quan đến transaction nghiệp vụ.

**Câu 7.** Có thể dùng JFR recording ngắn 2 giây để chọn GC cho production không?

**Đáp án:** Không. Demo ngắn chỉ xác minh code/công cụ. Cần workload thực, đủ sample, nhiều lần chạy, GC pause/latency/throughput/CPU/RSS và SLO.

**Câu 8.** Nếu `jfr summary` không thấy allocation events thì ứng dụng chắc chắn không tạo objects?

**Đáp án:** Không. Có thể do events chưa bật, threshold/sampling, phiên bản JDK hoặc khoảng ghi không phù hợp. Kiểm tra cấu hình và dữ liệu khác.

## 14. Ghi nhớ

- **JFR cho phép đặt GC, allocation và custom application events lên cùng timeline.**
- **GC pause khác concurrent GC cycle**, và **request latency khác GC pause**; phải đo đúng.
- **JDK 16+ dùng `jdk.ObjectAllocationSample`** cho allocation profiling hiện đại; **Java 15** dùng TLAB events khi được cấu hình, với overhead cần cân nhắc.
- **Custom `jdk.jfr.Event`** cho request giúp xác định start/end và dữ liệu ràng buộc; đừng ghi bí mật vào event.
- **Overlap thời gian không tự chứng minh nguyên nhân**; phải kiểm tra duration, stack, thread, I/O và test giả thuyết.
- **`jfr summary`, `jfr print`, JFR API và JMC** là các công cụ hiện hành để kiểm chứng và phân tích.
- **Một recording ngắn không thay benchmark production**; đo SLO end-to-end, throughput, errors, CPU, RSS và GC pause trong cùng điều kiện.
- **JFR recordings là dữ liệu cần bảo vệ** vì có thể chứa các thông tin vận hành nhạy cảm.

### Tài liệu còn áp dụng

- [Oracle Java 15 – JFR package `jdk.jfr`](https://docs.oracle.com/en/java/javase/15/docs/api/jdk.jfr/jdk/jfr/package-summary.html): custom events, annotations, settings, lifecycle.
- [Oracle Java 15 – `Recording`](https://docs.oracle.com/en/java/javase/15/docs/api/jdk.jfr/jdk/jfr/Recording.html): cấu hình, bắt đầu, stop và dump recording.
- [Oracle Java 15 – `RecordingFile`](https://docs.oracle.com/en/java/javase/15/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc sự kiện từ tệp JFR.
- [Oracle JDK 26 – Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html): GC pause, allocation và phân tích JFR.
- [Oracle JDK 16 Release Notes – ObjectAllocationSample](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html): sự kiện `jdk.ObjectAllocationSample` mới được đưa vào ở JDK 16.
- [dev.java – Configure JFR](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): `default.jfc`, `profile.jfc`, settings và các tùy chọn JFR hiện hành.
- [OpenJDK Java Flight Recorder](https://openjdk.org/jeps/328): nền tảng JFR trong OpenJDK.
- [Eclipse JDK Mission Control](https://projects.eclipse.org/projects/adoptium.jmc): JMC để phân tích JFR recordings theo timeline.
