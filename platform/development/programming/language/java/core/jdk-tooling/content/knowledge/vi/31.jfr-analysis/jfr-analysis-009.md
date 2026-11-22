# Tạo custom JFR event trong Java

**Custom JFR event** cho phép ứng dụng tự ghi lại những sự kiện nghiệp vụ hoặc kỹ thuật mà các event dựng sẵn của JVM không mô tả đủ chi tiết. Ví dụ: thời gian xử lý một request, quyết định cache hit/miss, thời gian chờ queue, kết quả một batch, số bản ghi xử lý hoặc trạng thái một bước trong workflow.

JFR (Java Flight Recorder) lưu event vào recording .jfr. Sau đó có thể dùng lệnh jfr, JDK Mission Control (JMC) hoặc JFR Consumer API để đọc và phân tích dữ liệu.

Một custom event thường được tạo bằng cách kế thừa lớp jdk.jfr.Event, khai báo metadata bằng annotation, bật event trong recording, rồi gọi commit() khi đã có dữ liệu cần ghi.

Ví dụ ngắn:

~~~java
@Name("com.example.RequestEvent")
@Label("Request event")
@Category({"Demo", "Application"})
public static class RequestEvent extends Event {
    public String requestId;
    public int statusCode;
}
~~~

Nếu event đo thời gian, dùng begin(), end() và commit(). Nếu event ghi một quyết định tại một thời điểm, chỉ cần gán field rồi commit().

## 1. Khi nào nên tạo custom event?

JFR đã có nhiều event cho hoạt động của JVM như garbage collection, thread, allocation, class loading, compilation, file I/O, socket I/O và monitor contention. Custom event bổ sung ngữ cảnh mà chỉ ứng dụng mới biết.

Một số tình huống phù hợp:

- Đo thời gian xử lý một loại request hoặc một bước nghiệp vụ.
- Ghi lại cache hit/miss.
- Đo thời gian chờ message queue hoặc semaphore.
- Theo dõi batch job: tên job, số bản ghi, kết quả và thời gian.
- Ghi nhận retry, timeout hoặc circuit breaker transition.
- Kết nối sự kiện nghiệp vụ với CPU, GC, thread và I/O event của JVM.
- Đánh dấu thời điểm deploy, bắt đầu một workflow hoặc hoàn tất một tác vụ.

Ví dụ, JFR có thể ghi socket read kéo dài 400 ms, nhưng custom event giúp biết request nào đang chờ và thao tác nghiệp vụ nào thực hiện request đó. Hai nhóm event có thể được đối chiếu theo timestamp và thread.

Không nên tạo event cho mọi phép tính nhỏ hoặc mọi dòng log. Chỉ ghi dữ liệu có ích cho một câu hỏi chẩn đoán cụ thể. Event quá dày, field quá lớn hoặc stack trace bật ở mọi event có thể làm recording phình to và tăng overhead.

## 2. Cấu trúc một custom event

Một custom event thường gồm ba phần:

1. **Event class:** kế thừa jdk.jfr.Event.
2. **Metadata:** tên, nhãn, mô tả, category và field.
3. **Lifecycle:** tạo event, đo thời gian nếu cần, gán field và commit.

JFR nhận diện event class và tạo metadata cho recording. Không cần tự thiết kế file nhị phân hoặc tự serialize object.

### Event class

~~~java
public final class RequestEvent extends Event {
    public String requestId;
    public String operation;
    public int statusCode;
}
~~~

Các field public được đưa vào metadata của event. Hãy ưu tiên kiểu dữ liệu nhỏ và có ý nghĩa: boolean, số nguyên, số thực, String ngắn hoặc giá trị định danh đã được kiểm soát.

Không đưa toàn bộ request/response, object graph lớn hoặc nội dung nhạy cảm vào event. Nếu cần liên kết với log, ghi một correlation ID không chứa bí mật.

### Annotation mô tả event

Các annotation phổ biến:

| Annotation | Mục đích |
|---|---|
| @Name | Tên kỹ thuật ổn định của event type |
| @Label | Nhãn thân thiện hiển thị trong công cụ |
| @Description | Mô tả event hoặc field |
| @Category | Nhóm event trong JMC và metadata |
| @Timespan | Đơn vị thời gian cho field duration tự định nghĩa |
| @Timestamp | Đơn vị timestamp cho field thời điểm tự định nghĩa |
| @DataAmount | Đơn vị dung lượng như bytes |

Ví dụ:

~~~java
@Name("com.example.RequestEvent")
@Label("Request event")
@Description("Records the duration and result of a request")
@Category({"Demo", "Application"})
public static final class RequestEvent extends Event {
    @Label("Request ID")
    @Description("Synthetic request identifier")
    public String requestId;

    @Label("Payload size")
    @DataAmount(DataAmount.BYTES)
    public long payloadBytes;

    @Label("Queue wait")
    @Timespan(Timespan.MILLISECONDS)
    public long queueWaitMillis;
}
~~~

Nên dùng tên event có namespace, ví dụ com.example.RequestEvent, để tránh trùng với event của JDK hoặc thư viện khác. Giữ tên event ổn định giữa các phiên bản để công cụ phân tích có thể nhận diện cùng một loại dữ liệu.

### Field tự định nghĩa và field có sẵn

JFR tự cung cấp các field chuẩn cho event, tùy loại và cấu hình:

- startTime: thời điểm bắt đầu event.
- duration: thời lượng event.
- eventThread: thread liên quan tới event.
- stackTrace: stack trace nếu event được cấu hình ghi.

Với duration event, begin() và end() thiết lập thời điểm bắt đầu và thời lượng. Với instant event, duration thường bằng 0 vì event được commit tại một thời điểm.

Không cần tự khai báo lại field startTime hoặc duration. Hãy đặt tên riêng cho field nghiệp vụ như queueWaitMillis, payloadBytes hoặc statusCode.

## 3. Duration event và instant event

Hai kiểu event phổ biến có lifecycle khác nhau.

### Duration event

Duration event đo khoảng thời gian một thao tác diễn ra:

~~~java
RequestEvent event = new RequestEvent();
event.begin();

performRequest();

event.end();
event.commit();
~~~

- begin() ghi lại thời điểm bắt đầu.
- end() ghi lại thời điểm kết thúc và tính duration.
- commit() gửi event vào recording nếu event được bật và đáp ứng settings.

Đặt begin() ngay trước vùng cần đo và end() ngay sau vùng đó. Tránh đặt thao tác không liên quan vào giữa vì sẽ làm duration bị phóng đại.

### Instant event

Instant event ghi nhận một sự kiện xảy ra tại một thời điểm, không cần đo thời lượng:

~~~java
CacheDecision event = new CacheDecision();
event.cacheKey = "product:42";
event.hit = true;
event.commit();
~~~

Event được ghi tại thời điểm commit(). Không cần gọi begin() hoặc end().

Dùng instant event cho các chuyển trạng thái, quyết định, kết quả hoặc dấu mốc. Dùng duration event cho request, transaction, batch step hoặc thao tác cần đo latency.

## 4. Enable event và recording settings

Khai báo class không có nghĩa event tự động xuất hiện trong mọi recording. Event phải được bật bằng recording settings.

Khi dùng JFR API:

~~~java
try (Recording recording =
         new Recording(Configuration.getConfiguration("profile"))) {
    recording.enable(RequestEvent.class)
             .withThreshold(Duration.ofMillis(10))
             .withStackTrace();

    recording.enable(CacheDecision.class)
             .withStackTrace();

    recording.start();

    // Application work

    recording.stop();
    recording.dump(Path.of("custom-events.jfr"));
}
~~~

Các method:

- enable(EventClass.class): bật event type trong recording.
- withThreshold(Duration): chỉ ghi duration event đạt ngưỡng thời gian.
- withStackTrace(): yêu cầu lưu stack trace cho event.
- withoutStackTrace(): tắt stack trace nếu không cần.
- start(): bắt đầu ghi.
- stop(): dừng recording.
- dump(Path): ghi recording ra file.

Trong ví dụ, RequestEvent chỉ được ghi khi duration đạt ít nhất 10 ms. CacheDecision là instant event nên không đặt threshold duration.

### default và profile

JDK cung cấp các cấu hình JFC phổ biến:

- default: ít dữ liệu hơn, overhead thấp, phù hợp recording kéo dài hoặc liên tục.
- profile: thu thập thêm dữ liệu để điều tra sâu hơn, thường có overhead cao hơn và nên dùng trong khoảng thời gian ngắn khi cần.

Có thể tạo Recording từ cấu hình default hoặc profile. Hãy chọn theo workload và mục tiêu. Không mặc định dùng profile ở mọi JVM production.

### Cấu hình event qua .jfc

Có thể bật custom event bằng file JFC:

~~~bash
jfr configure --input default.jfc \
    +com.example.RequestEvent#enabled=true \
    +com.example.RequestEvent#stackTrace=true \
    +com.example.CacheDecision#enabled=true \
    --output custom-events.jfc
~~~

Dấu + thêm cấu hình event mới vào JFC. File JFC có thể được dùng khi khởi chạy recording:

~~~bash
jcmd <pid> JFR.start name=CustomEvents settings=custom-events.jfc duration=60s filename=custom-events.jfr
~~~

Hoặc truyền cấu hình khi JVM khởi chạy bằng StartFlightRecording. Kiểm tra cú pháp của JDK đang dùng bằng jfr help configure và jcmd <pid> help JFR.start.

Khi dùng Recording API, có thể cấu hình event trực tiếp bằng recording.enable(). Khi dùng JFC hoặc jcmd, cần bảo đảm event type đã được định nghĩa trong ứng dụng và tên event khớp chính xác.

## 5. Kiểm soát chi phí bằng isEnabled() và shouldCommit()

Custom event được thiết kế để ghi dữ liệu với overhead thấp, nhưng việc tạo String, serialize dữ liệu, lấy stack trace hoặc tính toán field vẫn có chi phí.

Hai method hữu ích:

- isEnabled(): kiểm tra event có được bật trong recording hiện tại không.
- shouldCommit(): kiểm tra event có nên commit theo settings, bao gồm duration threshold, sau khi đã kết thúc event.

Ví dụ duration event:

~~~java
RequestEvent event = new RequestEvent();

if (event.isEnabled()) {
    event.begin();
    performRequest();
    event.end();

    if (event.shouldCommit()) {
        event.requestId = requestId;
        event.operation = operation;
        event.statusCode = 200;
        event.commit();
    }
}
~~~

isEnabled() giúp bỏ qua công việc chuẩn bị field khi event không được bật. shouldCommit() phù hợp sau end() để tránh tạo thêm dữ liệu cho event quá ngắn hoặc không đạt threshold.

Nếu event không được bật, không cần tạo payload lớn chỉ để gán vào field rồi gọi commit(). Nếu field được lấy từ một phép tính đắt tiền, chỉ tính khi event thực sự cần được ghi.

Đối với instant event, có thể kiểm tra isEnabled() trước khi lấy field tốn kém:

~~~java
CacheDecision event = new CacheDecision();

if (event.isEnabled()) {
    event.cacheKey = buildShortCacheKey();
    event.hit = cacheHit;
    event.commit();
}
~~~

Không đặt threshold lớn cho instant event vì duration của nó thường bằng 0. Threshold chủ yếu có ý nghĩa với event đo thời gian.

## 6. Đo thời gian an toàn với try/finally

Khi thao tác có thể ném exception, cần bảo đảm end() vẫn được gọi để event có duration hợp lệ.

Ví dụ:

~~~java
RequestEvent event = new RequestEvent();

if (event.isEnabled()) {
    event.begin();

    try {
        performRequest();
        event.statusCode = 200;
    } catch (RuntimeException ex) {
        event.statusCode = 500;
        throw ex;
    } finally {
        event.end();

        if (event.shouldCommit()) {
            event.requestId = requestId;
            event.operation = "loadProduct";
            event.commit();
        }
    }
}
~~~

Exception vẫn được ném lại để giữ nguyên hành vi lỗi của ứng dụng. Custom event chỉ bổ sung dữ liệu chẩn đoán.

Nếu muốn ghi loại lỗi, chỉ ghi exception class hoặc mã lỗi đã kiểm soát. Không mặc định ghi message đầy đủ vì message có thể chứa SQL, URL, dữ liệu người dùng hoặc secret.

Nếu cần đo thời gian cả khi có checked exception, giữ nguyên khai báo throws hoặc xử lý theo chính sách exception của ứng dụng. Không nuốt exception chỉ để ghi event.

## 7. Các field có đơn vị và metadata

Một field số nguyên có thể không đủ ngữ nghĩa nếu người đọc không biết đơn vị. Annotation giúp công cụ hiểu và hiển thị dữ liệu đúng hơn.

### @Timespan

~~~java
@Timespan(Timespan.MILLISECONDS)
public long queueWaitMillis;
~~~

Field được mô tả là khoảng thời gian tính bằng milliseconds. JMC và công cụ JFR có thể hiển thị field với đơn vị tương ứng.

### @Timestamp

~~~java
@Timestamp(Timestamp.MILLISECONDS_SINCE_EPOCH)
public long externalTimestamp;
~~~

Dùng khi thật sự cần lưu một timestamp tự định nghĩa. Nếu event đã có startTime mặc định, thường không cần thêm timestamp trùng lặp.

### @DataAmount

~~~java
@DataAmount(DataAmount.BYTES)
public long payloadBytes;
~~~

Giúp hiển thị dung lượng theo bytes và đơn vị thích hợp.

Không gán đơn vị sai. Nếu lưu microseconds nhưng gắn annotation milliseconds, báo cáo sẽ gây hiểu nhầm nghiêm trọng.

## 8. Custom event class và EventFactory

Cách phổ biến nhất là định nghĩa class kế thừa Event. Cách này có type safety, dễ refactor và dễ kiểm tra bằng compiler.

JFR cũng cung cấp EventFactory để tạo event type động khi schema chỉ được biết tại runtime. Đây là lựa chọn nâng cao cho framework hoặc hệ thống plugin cần tạo event từ metadata động.

Với ứng dụng thông thường, ưu tiên class kế thừa Event. Chỉ dùng EventFactory khi có yêu cầu rõ ràng về event schema động; API này cần định nghĩa AnnotationElement và ValueDescriptor chính xác, vì vậy phức tạp hơn và khó kiểm tra compile-time.

Dù dùng class hay factory, hãy giữ tên event, field, label và đơn vị ổn định để dữ liệu recording có thể được đọc nhất quán.

## 9. Đọc custom event bằng jfr command

Sau khi tạo file, kiểm tra summary:

~~~bash
jfr summary custom-events.jfr
~~~

Tìm event type do ứng dụng tạo. Summary hiển thị số event và dung lượng ghi nhận.

Xem metadata:

~~~bash
jfr metadata --events com.example.RequestEvent,com.example.CacheDecision custom-events.jfr
~~~

Metadata cho biết label, category, description và field layout. Dùng bước này để kiểm tra annotation có được nhận diện đúng không.

In các event:

~~~bash
jfr print --events com.example.RequestEvent,com.example.CacheDecision custom-events.jfr
~~~

Chỉ in RequestEvent:

~~~bash
jfr print --events com.example.RequestEvent custom-events.jfr
~~~

Xuất JSON:

~~~bash
jfr print --json --events com.example.RequestEvent custom-events.jfr
~~~

Xuất XML:

~~~bash
jfr print --xml --events com.example.RequestEvent custom-events.jfr
~~~

Có thể lọc theo category nếu event được gắn @Category:

~~~bash
jfr print --categories "Demo,Application" custom-events.jfr
~~~

Nếu event không xuất hiện, kiểm tra lần lượt:

1. Event class có được dùng trong recording không?
2. Event type đã được enable chưa?
3. Recording đã start trước khi event commit chưa?
4. Event có đạt threshold không?
5. Recording có được stop và dump đúng file không?
6. Tên event trong metadata có đúng không?

Không nhầm việc metadata xuất hiện với việc đã có event instance. Metadata mô tả event type; summary count và print output mới cho biết event đã được ghi.

## 10. Đọc custom event bằng JDK Mission Control

JDK Mission Control (JMC) đọc recording .jfr và hiển thị custom event cùng các event dựng sẵn.

Quy trình:

1. Mở JMC.
2. Chọn File > Open File.
3. Mở custom-events.jfr.
4. Chờ JMC đọc metadata.
5. Mở Event Browser.
6. Tìm category Demo hoặc event Request event.
7. Chọn event để xem timestamp, duration, field và stack trace.

@Label và @Category giúp event dễ tìm trong giao diện. @Description và label của field giúp người đọc hiểu ý nghĩa dữ liệu.

Với event duration, sắp xếp theo duration để tìm request chậm. Lọc theo request ID hoặc operation để xem nhóm sự kiện liên quan. Có thể đối chiếu custom event với GC pause, CPU sample, monitor contention và socket event trong cùng timeline.

JMC có thể hiển thị event theo category hoặc event type. Nếu event không xuất hiện, kiểm tra Event Browser filter và xác nhận event thực sự có trong file bằng jfr summary/print.

## 11. Đọc custom event bằng RecordingFile API

JDK cung cấp package jdk.jfr.consumer để đọc event theo cấu trúc từ file.

Các lớp quan trọng:

| API | Vai trò |
|---|---|
| RecordingFile | Mở và đọc recording tuần tự |
| RecordedEvent | Đại diện một event đã ghi |
| getEventType() | Lấy tên event type |
| getStartTime() | Lấy timestamp |
| getDuration() | Lấy duration |
| getThread() | Lấy thread liên quan nếu có |
| getStackTrace() | Lấy stack trace nếu có |
| getString()/getInt()/getBoolean() | Đọc field theo kiểu |
| getValue(name) | Đọc field theo tên |

Ví dụ:

~~~java
try (RecordingFile file = new RecordingFile(Path.of("custom-events.jfr"))) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();

        if (event.getEventType().getName()
                .equals("com.example.RequestEvent")) {
            String requestId = event.getString("requestId");
            int statusCode = event.getInt("statusCode");

            System.out.println(requestId + " status=" + statusCode);
        }
    }
}
~~~

Đọc tuần tự phù hợp với file lớn hơn so với việc tải toàn bộ event vào một collection. Đóng RecordingFile bằng try-with-resources và kiểm tra schema trước khi giả định field luôn tồn tại.

Khi xây dựng bộ phân tích, nên lọc event type sớm, chỉ đọc field cần thiết và tổng hợp số liệu thay vì giữ mọi RecordedEvent trong bộ nhớ.

## 12. Ví dụ Java 17+ hoàn chỉnh

Ví dụ tạo hai loại custom event:

- RequestEvent: duration event, chỉ commit khi duration đạt threshold 10 ms.
- CacheDecision: instant event, ghi cache hit/miss.

Chương trình thứ hai đọc file bằng RecordingFile và in các field đã ghi.

Cấu trúc thư mục:

~~~text
custom-jfr-event/
└── src/
    └── com/
        └── example/
            ├── CustomJfrEventDemo.java
            └── CustomJfrEventReader.java
~~~

### CustomJfrEventDemo.java

~~~java
package com.example;

import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.DataAmount;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.Timespan;

public final class CustomJfrEventDemo {
    @Name("com.example.RequestEvent")
    @Label("Request event")
    @Description("Records the duration and result of a demo request")
    @Category({"Demo", "Application"})
    public static final class RequestEvent extends Event {
        @Label("Request ID")
        @Description("Synthetic request identifier")
        public String requestId;

        @Label("Operation")
        public String operation;

        @Label("Status code")
        public int statusCode;

        @Label("Payload size")
        @DataAmount(DataAmount.BYTES)
        public long payloadBytes;

        @Label("Queue wait")
        @Timespan(Timespan.MILLISECONDS)
        public long queueWaitMillis;

        @Label("Simulated work")
        public int simulatedWorkMillis;
    }

    @Name("com.example.CacheDecision")
    @Label("Cache decision")
    @Description("Records a cache hit or miss as an instant event")
    @Category({"Demo", "Application"})
    public static final class CacheDecision extends Event {
        @Label("Cache key")
        public String cacheKey;

        @Label("Cache hit")
        public boolean hit;
    }

    private CustomJfrEventDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path destination = Path.of(args[0]).toAbsolutePath();
        int requestCount = 0;
        int cacheCount = 0;

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("profile"))) {
            recording.setName("Custom JFR event demo");
            recording.setToDisk(true);

            recording.enable(RequestEvent.class)
                    .withThreshold(Duration.ofMillis(10))
                    .withStackTrace();

            recording.enable(CacheDecision.class)
                    .withStackTrace();

            recording.start();

            for (int i = 1; i <= 3; i++) {
                RequestEvent event = new RequestEvent();

                if (event.isEnabled()) {
                    event.begin();
                    Thread.sleep(i == 1 ? 2 : 20 + i * 5);
                    event.end();

                    if (event.shouldCommit()) {
                        event.requestId = "REQ-" + i;
                        event.operation = "loadProduct";
                        event.statusCode = 200;
                        event.payloadBytes = 1024L * i;
                        event.queueWaitMillis = i * 2L;
                        event.simulatedWorkMillis = 10 + i * 10;
                        event.commit();
                        requestCount++;
                    }
                }
            }

            CacheDecision hit = new CacheDecision();
            if (hit.isEnabled()) {
                hit.cacheKey = "product:42";
                hit.hit = true;
                hit.commit();
                cacheCount++;
            }

            CacheDecision miss = new CacheDecision();
            if (miss.isEnabled()) {
                miss.cacheKey = "product:99";
                miss.hit = false;
                miss.commit();
                cacheCount++;
            }

            recording.stop();
            recording.dump(destination);
        }

        System.out.println("Recording written: " + destination.getFileName());
        System.out.println("Request events committed: " + requestCount);
        System.out.println("Cache events committed: " + cacheCount);
    }
}
~~~

### CustomJfrEventReader.java

~~~java
package com.example;

import java.nio.file.Path;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class CustomJfrEventReader {
    private CustomJfrEventReader() {
    }

    public static void main(String[] args) throws Exception {
        int requests = 0;
        int cacheDecisions = 0;

        try (RecordingFile file = new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                String type = event.getEventType().getName();

                if (type.equals("com.example.RequestEvent")) {
                    System.out.printf("request %s work=%dms%n",
                            event.getString("requestId"),
                            event.getInt("simulatedWorkMillis"));
                    requests++;
                } else if (type.equals("com.example.CacheDecision")) {
                    System.out.printf("cache key=%s hit=%s%n",
                            event.getString("cacheKey"),
                            event.getBoolean("hit"));
                    cacheDecisions++;
                }
            }
        }

        System.out.println("Matched request events=" + requests);
        System.out.println("Matched cache events=" + cacheDecisions);
    }
}
~~~

### Biên dịch

Từ thư mục gốc custom-jfr-event:

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/CustomJfrEventDemo.java \
    src/com/example/CustomJfrEventReader.java
~~~

### Tạo recording

~~~bash
java -cp build/classes \
    com.example.CustomJfrEventDemo custom-events.jfr
~~~

Output:

~~~text
Recording written: custom-events.jfr
Request events committed: 2
Cache events committed: 2
~~~

Event đầu tiên có thời gian ngủ khoảng 2 ms, thấp hơn threshold 10 ms nên không được commit. Hai request event còn lại vượt threshold. Hai CacheDecision là instant event nên đều được ghi.

### Đọc recording

~~~bash
java -cp build/classes \
    com.example.CustomJfrEventReader custom-events.jfr
~~~

Output chính xác:

~~~text
request REQ-2 work=30ms
request REQ-3 work=40ms
cache key=product:42 hit=true
cache key=product:99 hit=false
Matched request events=2
Matched cache events=2
~~~

### Kiểm tra bằng JFR CLI

~~~bash
jfr summary custom-events.jfr

jfr metadata \
    --events com.example.RequestEvent,com.example.CacheDecision \
    custom-events.jfr

jfr print \
    --events com.example.RequestEvent,com.example.CacheDecision \
    custom-events.jfr
~~~

Trong print output, RequestEvent có duration, requestId, operation, statusCode, payloadBytes, queueWaitMillis, eventThread và stackTrace. CacheDecision có timestamp, cacheKey, hit và eventThread.

Duration thực tế phụ thuộc scheduler và môi trường, nhưng số event và các field mô phỏng trong ví dụ được xác định bởi chương trình.

## 13. Kiểm tra metadata và threshold

Khi custom event không xuất hiện, hãy phân biệt ba trường hợp:

- Event type chưa được bật.
- Event đã bật nhưng không có instance được commit.
- Event có instance nhưng bị loại bởi threshold hoặc recording filter.

Dùng metadata để xác nhận event type và field:

~~~bash
jfr metadata --events com.example.RequestEvent custom-events.jfr
~~~

Dùng summary để kiểm tra count:

~~~bash
jfr summary custom-events.jfr
~~~

Dùng print để đọc event thực tế:

~~~bash
jfr print --events com.example.RequestEvent custom-events.jfr
~~~

Nếu metadata có event type nhưng count bằng 0, kiểm tra event settings và code path gọi commit(). Nếu event duration thấp hơn threshold, event sẽ không được ghi theo cấu hình đó.

Nếu field không xuất hiện, kiểm tra tên field, schema của event và liệu code có gán giá trị trước commit() hay không.

## 14. Thiết kế custom event tốt

### Đặt tên ổn định

Tên event nên có namespace và mô tả chức năng:

~~~text
com.example.RequestEvent
com.example.CacheDecision
com.example.BatchCompleted
com.example.RetryScheduled
~~~

Tránh đổi tên tùy tiện giữa các release vì dashboard, script và JMC filter có thể phụ thuộc tên này.

### Field có ngữ nghĩa rõ

Tên field cần cho biết nội dung và đơn vị. Dùng queueWaitMillis thay vì wait; dùng payloadBytes thay vì size nếu giá trị là byte.

Dùng @Label và @Description để người phân tích không phải đọc source code mới hiểu field.

### Ghi đủ context nhưng không quá nhiều

Field hữu ích có thể gồm operation, status code, duration, số bản ghi, payload size, retry count và correlation ID. Không ghi nội dung payload đầy đủ hoặc object graph lớn.

### Chọn threshold phù hợp

Threshold giúp giảm event ngắn không có giá trị. Chọn ngưỡng dựa trên latency budget và câu hỏi điều tra. Threshold quá cao có thể bỏ qua sự kiện cần tìm; threshold quá thấp có thể làm recording lớn.

### Bật stack trace có chọn lọc

Stack trace giúp tìm vị trí phát sinh event nhưng tăng dữ liệu và chi phí. Bật cho event cần tìm call site; cân nhắc tắt với event có tần suất rất cao hoặc khi không cần stack.

### Không ghi event trùng lặp

JFR đã có event về GC, thread, allocation, monitor và I/O. Trước khi tạo custom event, xem event dựng sẵn có đủ thông tin không. Custom event nên bổ sung ngữ cảnh nghiệp vụ, không sao chép toàn bộ dữ liệu runtime đã có.

## 15. Bảo mật và quyền riêng tư

JFR recording có thể chứa thông tin nội bộ của ứng dụng. Custom event còn có thể làm lộ dữ liệu do chính developer đưa vào field.

Không ghi:

- Password, API key, access token hoặc session secret.
- Cookie hoặc header xác thực.
- Nội dung request/response đầy đủ.
- Dữ liệu cá nhân hoặc thông tin khách hàng không cần thiết.
- SQL chứa giá trị nhạy cảm.
- URL có query string chứa token.
- Đường dẫn hoặc cấu hình nội bộ nếu không cần chẩn đoán.

Ưu tiên correlation ID giả lập hoặc đã được kiểm soát, enum trạng thái, mã lỗi, số lượng và duration. Giữ file JFR trong vùng lưu trữ có quyền truy cập hạn chế và rà soát trước khi chia sẻ.

Không coi việc scrub một số event là bảo đảm toàn bộ recording đã sạch dữ liệu. Field custom vẫn có thể chứa secret; hãy kiểm tra nội dung thực tế.

## 16. Overhead và giới hạn

JFR được thiết kế để ghi dữ liệu runtime với overhead thấp, nhưng overhead không bằng 0. Tác động phụ thuộc:

- Tần suất event.
- Số field và kích thước dữ liệu.
- Threshold.
- Stack trace có được bật không.
- Recording settings default hay profile.
- Thời lượng recording và giới hạn file.
- Số lượng recording đồng thời.

Một số cách giảm overhead:

- Chỉ bật event cần thiết.
- Dùng threshold theo latency budget.
- Dùng isEnabled() trước khi tạo field tốn kém.
- Dùng shouldCommit() sau end() để tránh chuẩn bị dữ liệu cho event không đạt threshold.
- Giảm stack trace khi không cần.
- Không ghi String lớn hoặc serialize object.
- Giới hạn maxage/maxsize của recording khi chạy lâu dài.
- Đo overhead trên workload đại diện trước khi triển khai rộng.

JFR không thay thế logging, metrics hoặc tracing phân tán. JFR cung cấp dữ liệu runtime chi tiết trong JVM; trace phân tán kết nối request giữa nhiều service; metrics cho xu hướng và alert; log lưu thông điệp và lỗi nghiệp vụ. Các công cụ này bổ trợ nhau.

## 17. Lỗi thường gặp

### Event class không xuất hiện trong metadata

Kiểm tra class có kế thừa Event, có annotation @Name hợp lệ và đã được dùng trong recording. Kiểm tra event class có được enable trong Recording hoặc JFC không.

### Event type có metadata nhưng không có event

Kiểm tra code có gọi commit(), recording đã start chưa và event có bị filter hoặc threshold loại bỏ không.

### Duration luôn bằng 0

Kiểm tra begin() và end() có được gọi đúng thứ tự trước commit(). Với instant event, duration bằng 0 là bình thường.

### Event duration lớn hơn mong đợi

Đặt begin() sát vùng cần đo và end() ngay sau vùng đó. Không để thao tác logging, serialize hoặc xử lý không liên quan nằm trong khoảng đo.

### Stack trace trống

Kiểm tra withStackTrace() hoặc setting stackTrace=true. Không phải mọi recording đều bật stack trace cho custom event.

### Field không có trong file

Field phải được khai báo trong event class và gán trước commit(). Kiểm tra metadata của đúng file để xác nhận schema.

### Event bị ghi quá nhiều

Tăng threshold, giảm tần suất event, bỏ field không cần thiết hoặc chỉ bật recording trong khoảng điều tra. Kiểm tra recording settings trước khi thay đổi code.

### Event không hiển thị trong JMC

Dùng jfr summary và jfr print để xác nhận event có trong file. Kiểm tra filter, category, time range và JMC version.

## 18. Checklist trước khi đưa custom event vào ứng dụng

- [ ] Event có mục đích chẩn đoán cụ thể.
- [ ] Event name có namespace và ổn định.
- [ ] Có @Label, @Description và @Category phù hợp.
- [ ] Field có tên, kiểu dữ liệu và đơn vị rõ ràng.
- [ ] Duration event gọi begin(), end() và commit() đúng thứ tự.
- [ ] Instant event commit tại thời điểm cần ghi.
- [ ] Recording bật đúng event type.
- [ ] Threshold phù hợp với latency cần theo dõi.
- [ ] isEnabled()/shouldCommit() được dùng khi cần giảm chi phí.
- [ ] Stack trace chỉ bật khi có giá trị.
- [ ] Không ghi secret, payload hoặc dữ liệu cá nhân không cần thiết.
- [ ] Đã kiểm tra metadata, summary và print output.
- [ ] Đã đo overhead trên workload đại diện.
- [ ] Đã thử đọc event bằng JMC hoặc RecordingFile.
- [ ] Có quy tắc bảo vệ và lưu trữ file recording.

## 19. Các lệnh cần nhớ

~~~bash
# Inspect available JFR commands
jfr help

# Configure custom event settings
jfr configure --input default.jfc \
    +com.example.RequestEvent#enabled=true \
    +com.example.RequestEvent#stackTrace=true \
    --output custom-events.jfc

# Start a recording using a custom JFC
jcmd <pid> JFR.start name=CustomEvents settings=custom-events.jfc duration=60s filename=custom-events.jfr

# Check active recordings
jcmd <pid> JFR.check

# Dump a running recording
jcmd <pid> JFR.dump name=CustomEvents filename=custom-events-snapshot.jfr

# Stop a recording
jcmd <pid> JFR.stop name=CustomEvents

# Inspect the recording
jfr summary custom-events.jfr
jfr metadata --events com.example.RequestEvent custom-events.jfr
jfr print --events com.example.RequestEvent custom-events.jfr
jfr print --json --events com.example.RequestEvent custom-events.jfr
~~~

Custom JFR event biến ngữ cảnh riêng của ứng dụng thành dữ liệu runtime có thể phân tích cùng event của JVM. Hãy đặt tên và metadata ổn định, chọn đúng lifecycle duration hoặc instant, bật threshold và stack trace có chủ đích, rồi kiểm tra recording bằng summary, metadata, print, JMC hoặc RecordingFile. Thiết kế field nhỏ, rõ đơn vị và không chứa bí mật để recording hữu ích trong điều tra mà vẫn dễ bảo vệ.

## Tài liệu tham khảo

- [JDK Flight Recorder API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/module-summary.html)
- [Event API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Recording API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [EventSettings API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/EventSettings.html)
- [RecordingFile API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [The jfr Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [The jcmd Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
