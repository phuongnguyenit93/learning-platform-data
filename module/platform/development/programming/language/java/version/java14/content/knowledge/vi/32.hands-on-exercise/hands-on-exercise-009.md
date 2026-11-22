# Tổng hợp số liệu từ repository hoặc tệp JFR

## 1. Bài toán thực hành tổng hợp

**Java Flight Recorder (JFR)** ghi các sự kiện có cấu trúc liên quan đến JVM và ứng dụng: garbage collection, CPU load, thread, I/O, allocation, exception, lock contention và những sự kiện nghiệp vụ do lập trình viên tự định nghĩa.

Giả sử bạn muốn tổng hợp một bản báo cáo trả lời:

- Trong khoảng thời gian quan sát có bao nhiêu request được ghi nhận?
- Bao nhiêu request thành công/thất bại, tỷ lệ lỗi là bao nhiêu?
- Tổng số byte xử lý và giá trị trung bình mỗi request?
- Endpoint nào xuất hiện nhiều nhất?
- Có bao nhiêu sự kiện GC, tổng thời lượng GC pause, phân bố duration ra sao?
- Số liệu đến từ **tệp `.jfr` đã kết thúc** hay từ **repository đang tiếp tục phát sinh chunks**?
- Khi nào một thống kê bằng 0 thực sự có nghĩa “không có hoạt động”, và khi nào có thể là “event chưa được bật/flush/đã bị sampling”?

Trong ngữ cảnh bài này, từ **repository** chủ yếu chỉ **JFR disk repository**: nơi JVM lưu các **recording chunks** phục vụ JFR. Nó **khác với Git/source-code repository**. Một source-code repository có thể chứa file `.jfr` đính kèm, nhưng bản thân thư mục chứa mã nguồn không tự trở thành JFR repository.

Mục tiêu: tạo một công cụ Java có **cùng logic tổng hợp** sử dụng được với:
1. **Tệp `recording.jfr`** đã thu thập (phân tích offline).
2. **Repository của JVM hiện tại** (tiêu thụ events gần thời gian thực).
3. **Một repository được chỉ định bằng `Path`** (theo dõi disk repository tin cậy).

Bài cung cấp chương trình **Java 17+ chạy thật**, stdout chính xác đã được kiểm chứng với một tập sự kiện mẫu và hướng dẫn mở rộng sang số liệu production. Special Note yêu cầu chỉ dùng kiến thức còn áp dụng: bài sử dụng **`jdk.jfr.consumer.EventStream`**, `Recording`, `RecordedEvent`, `RecordingFile` và CLI `jfr` hiện hành; không dùng JVM flags hoặc công cụ JFR legacy đã lỗi thời.

## 2. Tại sao Java 14 là mốc quan trọng?

**JEP 349 – JFR Event Streaming**, được phát hành trong **Java 14**, cung cấp khả năng **tiêu thụ JFR events khi chúng đang được JVM ghi**, thay vì chỉ thu thập tệp recording rồi mở bằng công cụ phân tích sau khi ứng dụng kết thúc.

Hai đường dữ liệu:

~~~text
                      Java application / JVM
                               |
                      JFR events được commit
                               |
               +---------------+----------------+
               |                                |
       JFR disk repository                 Recording / dump
       (chunks thay đổi theo thời gian)    tạo tệp .jfr
               |                                |
               v                                v
   EventStream.openRepository()       EventStream.openFile(path)
   EventStream.openRepository(path)    hoặc RecordingFile(path)
               |                                |
               +---------------+----------------+
                               |
                        RecordedEvent
                               |
                  lọc, đếm, cộng, nhóm, đo
                               |
                       Báo cáo / metrics
~~~

### 2.1. Những thứ không nên đồng nhất

| Khái niệm | Bản chất | Cách truy cập |
| --- | --- | --- |
| **JFR disk repository** | Vùng lưu các chunks của JFR khi ghi/stream | `EventStream.openRepository()` hoặc `openRepository(Path)` |
| **`recording.jfr`** | Tệp JFR để đọc offline, có thể chứa nhiều chunks | `EventStream.openFile(Path)`, `RecordingFile`, `jfr` CLI |
| **Live recording** | Một `Recording` đang thu sự kiện; có thể ghi xuống disk | `Recording` API, `RecordingStream`, `jcmd` |
| **Java source repository** | Git/SVN/thư mục chứa mã nguồn | Công cụ version control; không phải JFR API |
| **JDK Mission Control (JMC)** | Ứng dụng trực quan phân tích JFR | Mở recording và xem biểu đồ/thống kê |
| **`jfr summary`** | Lệnh thống kê số lượng event và kích thước theo loại | Dùng trên một tệp JFR |

**Cốt lõi:** `EventStream` cung cấp một abstraction chung để nhận `RecordedEvent`. Dù nguồn là file hay repository, ta có thể dùng **cùng callback tổng hợp**.

## 3. Các API hiện hành cần biết

JFR thuộc module **`jdk.jfr`** của JDK. API streaming trong package **`jdk.jfr.consumer`**.

| API | Công dụng |
| --- | --- |
| `EventStream.openFile(Path)` | Tạo luồng đọc một tệp `.jfr` |
| `EventStream.openRepository()` | Tạo luồng đọc JFR repository của **JVM hiện tại** |
| `EventStream.openRepository(Path)` | Tạo luồng từ **disk repository** tại đường dẫn chỉ định |
| `EventStream.onEvent(String, Consumer<RecordedEvent>)` | Đăng ký callback cho **một tên loại sự kiện** |
| `EventStream.onEvent(Consumer<RecordedEvent>)` | Callback cho **tất cả sự kiện** |
| `EventStream.onFlush(Runnable)` | Callback sau khi một batch JFR được flush/tiêu thụ |
| `EventStream.onError(Consumer<Throwable>)` | Xử lý lỗi trong hoạt động stream |
| `EventStream.setStartTime(Instant)` | Chọn mốc bắt đầu đọc trước khi start |
| `EventStream.setEndTime(Instant)` | Chọn mốc dừng theo thời gian |
| `EventStream.start()` | Bắt đầu xử lý **đồng bộ** trong thread gọi |
| `EventStream.startAsync()` | Xử lý **bất đồng bộ** trên một thread riêng |
| `EventStream.awaitTermination(Duration)` | Chờ stream kết thúc hoặc timeout |
| `EventStream.close()` | Yêu cầu đóng và giải phóng nguồn lực |
| `RecordedEvent.getEventType().getName()` | Tên loại sự kiện, chẳng hạn `jdk.GarbageCollection` |
| `RecordedEvent.getLong/getString/getBoolean/...` | Lấy trường typed của event |
| `RecordedEvent.getDuration()` | Thời lượng của event |
| `RecordingFile` | Đọc tuần tự tệp `.jfr` qua `hasMoreEvents()/readEvent()` |
| `RecordingFile.readAllEvents(Path)` | Tải mọi events vào bộ nhớ — chỉ thích hợp file nhỏ |
| `Recording` | Tạo, cấu hình, bắt đầu/dừng và dump một recording |

Các phương thức này **không bắt buộc ứng dụng phải sử dụng Java 14 đúng phiên bản**. Chúng hiện diện trong các JDK hiện đại. Ví dụ chính sử dụng `--release 17` để tránh lệ thuộc các API preview/lịch sử.

### 3.1. Chọn openFile hay openRepository

- Với **tệp đã được kết thúc/dump xong**, chọn **`openFile`**: mặc định đọc từ event đầu tiên trong file, kết thúc khi đã đọc xong.
- Với **repository đang có JVM ghi**, chọn **`openRepository`**: mặc định bắt đầu từ **sự kiện tiếp theo được flush**, có thể cần chờ dữ liệu mới xuất hiện. Đây **không phải một file đóng**.
- Với **repository của một JVM khác**, cần biết **đường dẫn thực** và quyền truy cập. `openRepository(Path)` không tự xác định PID hay truy cập một JVM qua mạng.
- Với **phân tích sau sự cố**, thường ưu tiên dump/ghép chunks thành file `.jfr` ổn định rồi phân tích offline, thay vì lệ thuộc repository vốn có vòng đời ngắn.

**Cảnh báo:** Tài liệu `EventStream` hiện hành nhấn mạnh chỉ mở **repository và recording files từ nguồn tin cậy**. Dữ liệu JFR có thể chứa thông tin nhạy cảm và không nên nhận tùy ý từ người lạ mà không có biện pháp bảo vệ.

## 4. Định nghĩa các chỉ số trước khi viết code

Một bảng tổng hợp chỉ có giá trị khi biết chính xác **đang đếm cái gì**.

| Metric | Định nghĩa | Đơn vị/công thức |
| --- | --- | --- |
| **Events / Requests** | Số `demo.Request` events được callback tiếp nhận | count |
| **Success** | Số events có field `success=true` | count |
| **Errors** | Số events có `success=false` | count |
| **Bytes** | Tổng giá trị field `bytes` của những events được đọc | bytes |
| **Average bytes** | Tổng bytes / số requests được quan sát | bytes/request |
| **Error rate** | Errors / Requests × 100% (nếu count khác 0) | % |
| **Per-endpoint count** | Nhóm theo field `endpoint`, đếm từng nhóm | count |
| **GC count** | Số `jdk.GarbageCollection` events được ghi nhận | events |
| **Total GC duration** | Tổng `getDuration()` của các GC events phù hợp | nanoseconds/milliseconds |
| **CPU load** | Giá trị lấy mẫu từ `jdk.CPULoad`, chẳng hạn `machineTotal` | ratio [0,1], có thể hiển thị % |

**Không đồng nhất:** “Số sự kiện JFR” **không luôn là số lần một hành động thực sự xảy ra trong ứng dụng**. Một loại event có thể:
- Bị tắt trong cấu hình recording.
- Có threshold, không ghi các sự kiện quá ngắn.
- Được sampling theo thời gian/rate.
- Chưa được flush trước khi chương trình tổng hợp dừng.
- Chỉ phát ra khi chức năng JVM tương ứng được sử dụng.

Với custom event trong ví dụ, ta chủ động bật loại `demo.Request` với threshold bằng 0 và commit **đúng năm sự kiện**, nên số đếm mong đợi là **5**. Với một event JDK được sampling, không tự suy ra “events count = số thao tác thật” nếu chưa kiểm tra event settings.

### 4.1. Mẫu số và điều kiện “không có dữ liệu”

Nếu `requests == 0`, không được thực hiện phép chia `bytes / requests`. Ví dụ chọn hiển thị **`n/a`** thay vì **0**, vì “chưa có quan sát” khác với “trung bình thật sự bằng 0”.

Nếu một cửa sổ thời gian có **0 events**, báo:
- Không ghi nhận events phù hợp.
- Có khả năng event type chưa bật hoặc threshold/sampling đã lọc.
- Với repository, có thể **chưa có flush** hoặc stream bắt đầu quá muộn.
- Với file, có thể đã chọn sai nguồn hoặc tên loại sự kiện.

Không kết luận máy chủ hoàn toàn không hoạt động chỉ từ một sự kiện có count bằng 0.

### 4.2. Một danh sách thống kê có ích

~~~text
Requests=5
Success=4
Errors=1
Bytes=1000
AverageBytes=200
Endpoint /a=3
Endpoint /b=2
~~~

Báo cáo trên là kết quả cụ thể của dữ liệu thử nghiệm sẽ được tạo trong phần 7. Chúng ta không giả định là số liệu hệ thống sản xuất.

## 5. Thu thập tệp JFR thực tế trước khi tổng hợp

### 5.1. Ghi ngay khi khởi động ứng dụng

Ví dụ lệnh (ứng dụng `app.jar` phải tồn tại):

~~~bash
java -XX:StartFlightRecording=filename=app.jfr,duration=60s,settings=profile -jar app.jar
~~~

Ý nghĩa:
- `-XX:StartFlightRecording` yêu cầu JVM bắt đầu recording.
- `filename=app.jfr` đặt đường dẫn output khi recording được ghi thành file.
- `duration=60s` chỉ định thời lượng ghi trong ví dụ.
- `settings=profile` là cấu hình JFR phục vụ profiling và có thể phát sinh overhead lớn hơn default settings; lựa chọn dựa trên mục tiêu đo đạc.

**Lệnh này là ví dụ áp dụng**, không phải stdout được xác nhận cho một `app.jar` bất kỳ. Với hệ thống thật, kiểm tra CPU/memory overhead, quyền ghi và chính sách dữ liệu trước khi mở recording.

### 5.2. Bật JFR trên JVM đang chạy

Khi biết đúng PID của JVM và có quyền:

~~~bash
jcmd <pid> JFR.start name=metrics settings=profile disk=true
jcmd <pid> JFR.check
jcmd <pid> JFR.dump name=metrics filename=app.jfr
jcmd <pid> JFR.stop name=metrics
~~~

Đây là **chuỗi lệnh mẫu**, trong đó `<pid>` là **placeholder của PID JVM**, không gõ nguyên dấu ngoặc góc. Gọi `JFR.dump` khi muốn **snapshot** ra file mà không cần kết thúc toàn bộ JVM; `JFR.stop` dừng recording được chỉ định.

Không dùng lệnh này nếu bạn chưa có quyền thao tác và chưa hiểu tác động bảo mật/lưu trữ trên tiến trình production.

### 5.3. Chọn cách đọc sau khi đã có file

~~~bash
jfr summary app.jfr
jfr print --events jdk.GarbageCollection app.jfr
jfr print --events jdk.CPULoad app.jfr
jfr metadata app.jfr
~~~

- `jfr summary`: thống kê **số lượng/size** theo event type — phù hợp để kiểm tra dữ liệu có hay không.
- `jfr print`: in events với trường và timestamp; có thể lọc theo tên.
- `jfr metadata`: xem định nghĩa field/type; hữu ích khi tên field khác kỳ vọng.
- Trên các JDK hiện đại hỗ trợ, `jfr view` cung cấp bảng/đồ thị số liệu tổng hợp; hãy kiểm tra `jfr help view` hoặc `jfr view types app.jfr` với đúng phiên bản công cụ.

**Không cần đọc cả file bằng `Files.readAllBytes`** để tự parse định dạng binary JFR. Dùng `EventStream`, `RecordingFile` hoặc CLI chính thức.

## 6. Repository JFR: dữ liệu được tạo và tiêu thụ thế nào?

JFR ghi dữ liệu thành **chunks** trong repository. Chunks có vòng đời riêng, có thể được rotate/cleanup khi recording dừng hoặc JVM kết thúc. Repository là **nơi trung gian phục vụ JFR**, không phải một directory backups bất biến.

### 6.1. Repository của JVM hiện tại

~~~java
try (EventStream stream = EventStream.openRepository()) {
    stream.onEvent("jdk.GarbageCollection", event -> {
        System.out.println(event.getDuration());
    });
    stream.start();
}
~~~

Đây là **snippet**, không phải chương trình có `main`. `start()` có thể chờ liên tục vì repository đang được ghi; cần cơ chế dừng/close thích hợp. Nếu chưa có `jdk.GarbageCollection` được ghi hoặc flush, callback không chạy.

### 6.2. Repository được chỉ định bằng Path

~~~java
Path repository = Path.of("C:/jfr-repository");
try (EventStream stream = EventStream.openRepository(repository)) {
    stream.onEvent("jdk.CPULoad", event -> {
        float machine = event.getFloat("machineTotal");
        System.out.println("Machine CPU %=" + (machine * 100.0f));
    });
    stream.start();
}
~~~

Đây là **mẫu sử dụng API**, chỉ hoạt động khi directory được chỉ định **thực sự là JFR repository hợp lệ đang có data**, và JFR producer ghi events `jdk.CPULoad`. `machineTotal` là tỷ lệ cần nhân 100 để hiển thị phần trăm; không lấy raw float rồi gắn ký hiệu %.

### 6.3. Cấu hình thư mục repository của JFR

Có thể cấu hình location qua công cụ VM:

~~~bash
jcmd <pid> JFR.configure repositorypath=/path/to/jfr-repository
~~~

Hoặc ở một số phiên bản HotSpot/JDK hỗ trợ:

~~~bash
java -XX:FlightRecorderOptions=repository=/path/to/jfr-repository -jar app.jar
~~~

Các lệnh này mang tính **cấu hình triển khai**, cần thay PID/path và kiểm tra `java -XX:FlightRecorderOptions=help`/`jcmd <pid> JFR.configure` theo JDK đang dùng. Repository phải nằm ở nơi JVM có quyền ghi, đủ dung lượng và được bảo vệ truy cập.

### 6.4. Open repository mặc định không replay toàn bộ lịch sử

Tài liệu `EventStream` mô tả **mặc định repository stream bắt đầu từ event được flush tiếp theo**. Vì vậy:
- Một event có thể đã commit, nhưng **chưa flush**, nên callback chưa nhận.
- Stream có thể bắt đầu **sau** những sự kiện cần quan sát.
- `close()` có thể dừng trước khi các sự kiện cuối cùng được callback xử lý.
- Dữ liệu cũ có thể bị repository cleanup, không còn để replay.

Nếu cần **mốc bắt đầu cụ thể**, dùng `setStartTime(Instant)` **trước `start()`**. Nhưng cũng phải hiểu: yêu cầu mốc thời gian trong quá khứ không khôi phục những chunks **đã bị xóa**. Kết quả phải được diễn giải như **events thực sự đọc được**, không phải bảo đảm bao phủ toàn bộ lịch sử.

### 6.5. Đừng nhầm snapshot và live report

- **File offline:** đợi stream đọc xong file rồi mới tổng hợp; thường có **tập dữ liệu ổn định**.
- **Repository live:** báo cáo là **snapshot tại một mốc xử lý**; các events chưa flush hoặc chưa được nhận sẽ **không nằm trong số liệu**.
- Khi cần báo cáo hoàn chỉnh theo khoảng thời gian, có thể **dump recording** tại thời điểm chốt rồi chạy phân tích offline, hoặc xây giao thức giám sát có flush/window/watermark và xử lý event đến trễ.

## 7. Chương trình Java 17+ hoàn chỉnh: cả file và repository

Để kiểm chứng có hệ thống và cho phép copy chạy được, chương trình dùng custom JFR event **`demo.Request`** với ba trường:
- `endpoint` (`String`).
- `bytes` (`long`).
- `success` (`boolean`).

Chương trình hỗ trợ bốn chế độ:
- `generate <file>`: tạo một `.jfr` chứa đúng năm request mẫu.
- `file <file>`: đọc file và tổng hợp.
- `live-current <dump>`: nghe repository **của JVM hiện tại** trong khi phát sinh dữ liệu mẫu.
- `live-path <repo> <dump>`: nghe repository theo `Path` đã cấu hình cho JVM.

**Tệp: `JfrSummaryDemo.java`**

~~~java
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;
import jdk.jfr.consumer.RecordedEvent;

public final class JfrSummaryDemo {
    @Name("demo.Request")
    @Label("Demo Request")
    @Category({"Demo", "Requests"})
    static final class RequestEvent extends Event {
        @Label("Endpoint") String endpoint;
        @Label("Bytes") long bytes;
        @Label("Success") boolean success;
    }

    static final class Summary {
        long count, successes, failures, bytes;
        final Map<String, Long> byEndpoint = new TreeMap<>();

        void add(RecordedEvent event) {
            count = Math.addExact(count, 1);
            if (event.getBoolean("success")) successes++;
            else failures++;
            bytes = Math.addExact(bytes, event.getLong("bytes"));
            byEndpoint.merge(event.getString("endpoint"),
                    1L, Math::addExact);
        }

        void print() {
            System.out.println("Requests=" + count);
            System.out.println("Success=" + successes);
            System.out.println("Errors=" + failures);
            System.out.println("Bytes=" + bytes);
            System.out.println("AverageBytes="
                    + (count == 0 ? "n/a"
                            : Long.toString(bytes / count)));
            byEndpoint.forEach((name, value) ->
                    System.out.println("Endpoint " + name + "=" + value));
        }
    }

    static Recording recording() {
        Recording r = new Recording();
        r.setToDisk(true);
        r.enable(RequestEvent.class)
                .withThreshold(Duration.ZERO)
                .withoutStackTrace();
        return r;
    }

    static void emit() {
        String[] endpoints = {"/a", "/b", "/a", "/b", "/a"};
        long[] sizes = {100, 200, 150, 300, 250};
        for (int i = 0; i < endpoints.length; i++) {
            RequestEvent e = new RequestEvent();
            e.endpoint = endpoints[i];
            e.bytes = sizes[i];
            e.success = i != 3;
            e.commit();
        }
    }

    static void generate(Path output) throws Exception {
        try (Recording r = recording()) {
            r.start();
            emit();
            r.stop();
            r.dump(output);
        }
        System.out.println("Recording created");
    }

    static void readFile(Path path) throws Exception {
        Summary summary = new Summary();
        try (EventStream stream = EventStream.openFile(path)) {
            stream.onEvent("demo.Request", summary::add);
            stream.start();
        }
        summary.print();
    }

    static void readRepository(Path repo, Path dump)
            throws Exception {
        Summary summary = new Summary();
        CountDownLatch received = new CountDownLatch(5);
        try (Recording r = recording();
                EventStream stream = repo == null
                        ? EventStream.openRepository()
                        : EventStream.openRepository(repo)) {

            stream.setStartTime(Instant.EPOCH);
            stream.onEvent("demo.Request", event -> {
                summary.add(event);
                received.countDown();
            });

            r.start();
            stream.startAsync();
            Thread.sleep(1500);
            emit();
            r.dump(dump);
            boolean complete =
                    received.await(5, TimeUnit.SECONDS);
            r.stop();
            stream.close();
            stream.awaitTermination(Duration.ofSeconds(3));
            System.out.println("LiveComplete=" + complete);
        }
        summary.print();
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 2 && args[0].equals("generate")) {
            generate(Path.of(args[1]));
        } else if (args.length == 2 && args[0].equals("file")) {
            readFile(Path.of(args[1]));
        } else if (args.length == 2
                && args[0].equals("live-current")) {
            readRepository(null, Path.of(args[1]));
        } else if (args.length == 3
                && args[0].equals("live-path")) {
            readRepository(Path.of(args[1]), Path.of(args[2]));
        } else {
            throw new IllegalArgumentException(
                    "generate <file> | file <file>"
                    + " | live-current <dump>"
                    + " | live-path <repo> <dump>");
        }
    }
}
~~~

### 7.1. Những đặc điểm của ví dụ

- Event được gắn **`@Name("demo.Request")`** nên consumer lọc chính xác theo tên.
- `Recording.setToDisk(true)` cho phép JFR lưu events trong repository khi recording hoạt động.
- `enable(RequestEvent.class).withThreshold(Duration.ZERO)` bật tất cả events mẫu, kể cả event rất ngắn.
- `TreeMap` sắp xếp endpoint ổn định theo tên, làm stdout dễ kiểm chứng.
- `Math.addExact` ngăn đếm/tổng byte âm thầm tràn `long`; nếu tràn thì demo báo lỗi, không tiếp tục với thống kê sai.
- Phép chia `bytes / count` cho **giá trị trung bình nguyên đã bỏ phần lẻ**, không phải một trung bình số thực có độ chính xác đầy đủ.
- `getBoolean("success")`, `getLong("bytes")` và `getString("endpoint")` truy cập fields **theo đúng tên và kiểu** của event đã định nghĩa.
- `CountDownLatch(5)` chỉ thích hợp vì **fixture lab biết chắc sẽ commit đúng năm events**. Một collector production không nên đặt số 5 cứng; phải dùng thời gian quan sát, windows hoặc cơ chế dừng khác.

### 7.2. Phần đọc file

~~~java
try (EventStream stream = EventStream.openFile(path)) {
    stream.onEvent("demo.Request", summary::add);
    stream.start();
}
~~~

**`openFile`** đọc một recording file; `start()` xử lý callback đồng bộ và trở về khi file đã hết. Sau đó in thống kê — không có race với background callback của stream.

### 7.3. Phần đọc repository

~~~java
stream.setStartTime(Instant.EPOCH);
stream.onEvent("demo.Request", event -> {
    summary.add(event);
    received.countDown();
});
r.start();
stream.startAsync();
Thread.sleep(1500);
emit();
r.dump(dump);
boolean complete = received.await(5, TimeUnit.SECONDS);
~~~

Đoạn trên là **trích từ chương trình chạy được**. Trong lab:
- `setStartTime(Instant.EPOCH)` cho phép đọc từ lịch sử **còn trong repository** khi thực sự có dữ liệu.
- `Thread.sleep(1500)` tạo thời gian để stream bất đồng bộ bắt đầu; đó là **biện pháp thực nghiệm cho fixture**, không phải cơ chế đồng bộ hóa production.
- `r.dump(dump)` tạo một **snapshot `.jfr`** và khiến dữ liệu được ghi/flush phục vụ quan sát; **không nên gọi dump liên tục chỉ để ép mọi metric ra ngay** trong hệ thống thật.
- `CountDownLatch.await(...)` xác nhận lab đã thấy **đủ năm events** trước khi in.
- `stream.close()` và `awaitTermination(...)` giúp dừng và chờ callback kết thúc, nhưng **close không bảo đảm tất cả events chưa flush đã được nhận**.

**Tại sao lab không chỉ dùng `openRepository()` rồi ngủ 1 giây và in số liệu?** Vì trong kiểm thử ban đầu, một stream ngắn **không nhận được events trước thời điểm đóng**, dẫn tới `Requests=0` dù producer đã commit. Khi dùng mốc đọc và flush đúng, cả hai repository modes nhận đủ events. Đây là giới hạn thật của dữ liệu live, không nên che bằng một output mẫu không kiểm chứng.

### 7.4. Lưu ý về `Instant.EPOCH`

`Instant.EPOCH` trong demo làm rõ khả năng yêu cầu đọc **từ mốc rất sớm**. Trong một repository production đã hoạt động từ lâu, giá trị này có thể:
- Đọc nhiều dữ liệu cũ **vẫn còn được lưu**, dẫn tới đếm lại khi collector restart.
- Tăng chi phí xử lý rất lớn.
- Không đảm bảo lấy được dữ liệu đã bị JVM xóa/rotate khỏi repository.

Một collector thực tế nên dùng:
- Mốc thời gian **bắt đầu cửa sổ** rõ ràng.
- Chế độ **start from next flushed event** nếu không muốn replay.
- Cơ chế idempotency/deduplication hoặc checkpoint phù hợp nếu yêu cầu “exactly-once” ở báo cáo cuối.
- Cách xác định **end time** và xử lý event đến trễ.

Không mặc định chuyển mọi ứng dụng production sang `setStartTime(Instant.EPOCH)`.

## 8. Biên dịch và chạy thực tế

Yêu cầu **JDK 17+** có module `jdk.jfr`. Ví dụ đã được kiểm chứng với `javac --release 17` trên **JDK 24**.

### 8.1. Biên dịch

~~~bash
javac -encoding UTF-8 --release 17 JfrSummaryDemo.java
~~~

### 8.2. Tạo và đọc tệp JFR

~~~bash
java JfrSummaryDemo generate requests.jfr
java JfrSummaryDemo file requests.jfr
~~~

**Stdout của lệnh generate:**

~~~text
Recording created
~~~

**Stdout chính xác của lệnh file:**

~~~text
Requests=5
Success=4
Errors=1
Bytes=1000
AverageBytes=200
Endpoint /a=3
Endpoint /b=2
~~~

Kết quả được tạo từ năm events theo thứ tự:

| Request | Endpoint | Bytes | Success |
| --- | --- | ---: | --- |
| 1 | `/a` | 100 | true |
| 2 | `/b` | 200 | true |
| 3 | `/a` | 150 | true |
| 4 | `/b` | 300 | false |
| 5 | `/a` | 250 | true |

Phép tính:
- `count = 5`.
- `successes = 4`.
- `failures = 1`.
- `bytes = 100 + 200 + 150 + 300 + 250 = 1000`.
- `average bytes = 1000 / 5 = 200`.
- `/a = 3`, `/b = 2`.
- Nếu tính tỷ lệ lỗi: `1 / 5 × 100 = 20%`, nhưng chương trình demo cố tình không in metric này để giữ output đơn giản.

### 8.3. Tổng hợp repository của JVM hiện tại

~~~bash
java JfrSummaryDemo live-current live-current.jfr
~~~

Trong **lần kiểm chứng thành công**, output:

~~~text
LiveComplete=true
Requests=5
Success=4
Errors=1
Bytes=1000
AverageBytes=200
Endpoint /a=3
Endpoint /b=2
~~~

**Giới hạn:** `LiveComplete=true` ở đây có nghĩa **CountDownLatch đã quan sát đủ năm events mẫu trong thời hạn lab**, không có nghĩa cả repository production đã được đọc tới event cuối. Một lần chạy trên máy chậm có thể chưa nhận đủ events trong timeout; chương trình sẽ in `LiveComplete=false` và số liệu quan sát được.

### 8.4. Tổng hợp repository theo Path trên Windows PowerShell

Trong thư mục chứa `JfrSummaryDemo.class`:

~~~powershell
New-Item -ItemType Directory -Force -Path repo | Out-Null

$repositoryPath = (Resolve-Path repo).Path
java "-XX:FlightRecorderOptions=repository=$repositoryPath" JfrSummaryDemo live-path $repositoryPath live-path.jfr
~~~

Lệnh dùng Java VM option để chỉ định vị trí **repository**, sau đó truyền cùng directory cho `EventStream.openRepository(Path)`.

**Stdout đã kiểm chứng trong môi trường thử nghiệm:**

~~~text
LiveComplete=true
Requests=5
Success=4
Errors=1
Bytes=1000
AverageBytes=200
Endpoint /a=3
Endpoint /b=2
~~~

### 8.5. Xác minh bằng JFR CLI độc lập

~~~bash
jfr summary requests.jfr
~~~

Trong bảng thống kê của `jfr summary` trên tệp thử nghiệm, loại event custom xuất hiện:

~~~text
demo.Request                                5            79
~~~

Dòng này trích từ **bảng Event Type / Count / Size (bytes)** của công cụ `jfr` trên máy kiểm chứng. **79** là số byte được công cụ gán cho loại event trong file demo, **không phải tổng `bytes=1000` trong field nghiệp vụ**. Phân biệt hai con số là điều rất quan trọng:

- `jfr summary` đếm **event records** và **kích thước dữ liệu JFR** của loại event trong recording.
- Chương trình tính **tổng field `bytes` do ứng dụng phát ra**.

**Không bao giờ lấy cột Size (bytes) từ `jfr summary` làm tổng “response bytes” của ứng dụng.**

## 9. Cách xây bộ tổng hợp thực tế ngoài ví dụ

Sau khi chạy được demo, hãy tách kiến trúc thành hai lớp:

~~~text
                  +----------------------+
  .jfr ---------> | Event source adapter |
                  | openFile              | ---+
                  +----------------------+    |
                                                v
                  +----------------------+  RecordedEvent
  repository ----> | Event source adapter |    |
                  | openRepository        | ---+
                  +----------------------+    |
                                                v
                                 +-------------------------+
                                 | Metric aggregator       |
                                 | type filters            |
                                 | counters / sums / groups|
                                 | time windows            |
                                 +-------------------------+
                                                |
                               +----------------+----------------+
                               v                                 v
                       JSON/CSV/DB/report                Dashboards/alerts
~~~

### 9.1. Định nghĩa schema dữ liệu trước

Ví dụ `demo.Request` có fields `endpoint`, `bytes` và `success`. Nếu sự kiện không có `bytes` hoặc `bytes` là kiểu khác, `getLong("bytes")` có thể lỗi.

Trong tool production:
- Kiểm tra event name bằng `event.getEventType().getName()`.
- Kiểm tra field tồn tại, ví dụ `event.hasField("bytes")` khi xử lý nhiều version schema.
- Kiểm tra kiểu field tương ứng trước khi ép kiểu.
- Quy định xử lý events thiếu field: bỏ qua có log, đánh dấu lỗi dữ liệu hay dùng giá trị mặc định được tài liệu hóa.
- Version schema các custom events và kiểm tra compatibility khi triển khai nhiều JDK.
- **Không âm thầm đổi missing data thành 0** nếu làm lệch báo cáo.

### 9.2. Chọn onEvent(String, ...) thay vì onEvent(e -> ...)

Khi chỉ cần một vài event types:

~~~java
stream.onEvent("jdk.GarbageCollection", event -> {
    // Tính GC count và tổng duration.
});
~~~

Ưu điểm: consumer có thể tránh giải mã/dispatch các event types không liên quan. Nếu dùng `onEvent(Consumer)` chung cho mọi event trong một file lớn rồi kiểm tra `getEventType().getName()` thủ công, chi phí có thể cao hơn.

Dùng `onEvent(Consumer)` toàn bộ khi thật sự cần:
- Khám phá nhiều event types.
- Tổng hợp count theo tất cả tên event.
- Kiểm tra event schema hoặc loại đang xuất hiện.

### 9.3. Chỉ giữ số liệu tổng hợp, không tích lũy mọi event

Một chương trình đọc hàng triệu events mà viết:

~~~java
List<RecordedEvent> all = new ArrayList<>();
stream.onEvent(all::add);
~~~

đang giữ toàn bộ objects trong bộ nhớ; đặc biệt **`EventStream` có thể tái sử dụng cùng `RecordedEvent` object** ở nhiều callbacks theo API. Vì vậy hai rủi ro:
1. **Tốn RAM** theo số lượng events.
2. References có thể trỏ tới object đã được **reuse**, làm báo cáo sai.

**Nên làm:** lấy field cần thiết **ngay trong callback** và cập nhật counter/aggregation, như `Summary.add` của demo.

Khi thật sự phải giữ `RecordedEvent` sau callback, hiểu và cấu hình `setReuse(false)` trước khi start; vẫn phải quản lý memory limit. Ngay cả khi tắt reuse, việc giữ tất cả events không phù hợp cho stream dài vô hạn.

## 10. Tổng hợp các event chuẩn của JDK

Custom events dễ kiểm thử nhưng trong hệ thống thật thường cần metric từ **`jdk.*` events**. Những ví dụ dưới đây là **snippets**, không phải phần của chương trình demo chính; cần một `EventStream stream` có sẵn.

### 10.1. Đếm sự kiện GC và cộng duration

~~~java
final long[] gcCount = {0};
final long[] gcNanos = {0};

stream.onEvent("jdk.GarbageCollection", event -> {
    gcCount[0] = Math.addExact(gcCount[0], 1);
    gcNanos[0] = Math.addExact(
            gcNanos[0],
            event.getDuration().toNanos());
});
~~~

Sau khi stream đọc xong:

~~~java
double gcMillis = gcNanos[0] / 1_000_000.0;
~~~

Cần import `java.time.Duration`? Snippet không yêu cầu import trực tiếp nếu chỉ gọi `getDuration()`. **Cẩn thận:** `getDuration()` trả duration của event; tùy loại GC event và configuration, cách diễn giải là **duration event theo JFR**, không phải tự động thời gian toàn ứng dụng không phục vụ request.

### 10.2. CPU load phải xử lý đơn vị

~~~java
stream.onEvent("jdk.CPULoad", event -> {
    float fraction = event.getFloat("machineTotal");
    double percent = fraction * 100.0;
    System.out.println("Machine CPU load (%)=" + percent);
});
~~~

`machineTotal` thường là **fraction**, không phải 80 khi CPU đang 80%. Không lấy `0.80` rồi báo `0.80%`.

CPU load là **số liệu lấy mẫu**, nên:
- Trung bình theo mẫu có thể không khớp hoàn toàn với trung bình trọng số theo thời gian.
- Một recording thiếu samples không thể suy ra CPU=0%.
- Cần xem event settings, khoảng cách giữa các samples và duration window nếu muốn báo cáo chính xác.

### 10.3. Phân tích contention và I/O

Các sự kiện thường dùng:
- `jdk.JavaMonitorEnter`: thời gian thread chờ monitor trong điều kiện được cấu hình.
- `jdk.FileRead` / `jdk.FileWrite`: I/O file theo threshold và setting.
- `jdk.SocketRead` / `jdk.SocketWrite`: I/O socket.
- `jdk.ExceptionThrown` / `jdk.JavaExceptionThrow`: sự kiện exception tùy bản JDK và configuration; **đừng tự đoán tên**, hãy dùng `jfr metadata` hoặc danh sách event types thật.

**Không suy ra** “không có FileRead events” = “ứng dụng không đọc file”. Nhiều event types có threshold hoặc không được bật để hạn chế overhead. Luôn kiểm tra tên và fields **trong JDK/recording thực tế**.

### 10.4. Khi event field là duration hoặc size

`RecordedEvent.getDuration()` và `RecordedObject.getDuration(fieldName)` giúp đọc duration theo semantics của JFR. Nếu field có annotation timespan hoặc data amount, có thể có những đơn vị cơ sở khác nhau; **không tự đoán** từ tên field mà không xem metadata.

Ví dụ:
- Một `duration` hiển thị trong `jfr print` có thể đã được format như `12.3 ms`; khi đọc API, `Duration` dùng các phép chuyển đơn vị tường minh.
- Event field ứng dụng `bytes` của chúng ta đã được định nghĩa rõ theo bytes.
- Cột `Size (bytes)` trong `jfr summary` nói về **dung lượng mã hóa sự kiện**, không phải bytes nghiệp vụ.

## 11. Group-by, average và tỷ lệ lỗi

### 11.1. Đếm theo endpoint

~~~java
byEndpoint.merge(event.getString("endpoint"),
        1L, Math::addExact);
~~~

`Map.merge` là API Java chuẩn; với `TreeMap`, các nhóm được in theo thứ tự tên, thuận tiện cho QA và báo cáo tái lập.

Ở production, endpoint có thể là path chứa IDs động như `/orders/1001`, `/orders/1002`. Nếu nhóm theo raw URL, số nhóm có thể tăng không giới hạn. Nên chuẩn hóa theo **route template** (ví dụ `/orders/{id}`) khi nguồn event cho phép, đồng thời không làm lộ dữ liệu nhạy cảm trong labels.

### 11.2. Tỷ lệ lỗi

Với `requests > 0`:

~~~java
double errorRate = 100.0 * errors / requests;
~~~

Cần tính trên **cùng tập events** và **cùng window**. Đừng cộng tỷ lệ lỗi của hai nhóm rồi chia đôi nếu lưu lượng của chúng khác nhau; hãy tổng hợp **errors và requests trước** rồi mới tính tỷ lệ.

Ví dụ:
- Endpoint A: 10 errors / 100 requests = 10%.
- Endpoint B: 1 error / 1 request = 100%.
- Tỷ lệ chung không phải trung bình `(10% + 100%) / 2 = 55%`.
- Tỷ lệ đúng là `11 / 101 × 100 ≈ 10.89%`.

### 11.3. Trung bình

`bytes / requests` trong chương trình trả **trung bình nguyên**. Nếu muốn có phần thập phân:

~~~java
double average = requests == 0
        ? Double.NaN
        : (double) bytes / requests;
~~~

Cần định nghĩa cách hiển thị `NaN` (hoặc `n/a`), precision và rounding. Đừng diễn giải phép cast `double` là đại diện chính xác tuyệt đối cho mọi số `long` lớn.

### 11.4. Percentiles: p50, p95, p99

Với latencies, một **p95** thường hữu ích hơn mean. Nhưng:
- Không thể tính p95 chính xác chỉ từ count + sum.
- **Không được lấy trung bình các p95** của những windows/servers rồi gọi đó là p95 tổng.
- Để lấy percentile gần đúng với dòng dữ liệu dài, dùng histogram/quantile sketch có error bounds rõ ràng.
- Nếu lưu toàn bộ durations để sort, chi phí RAM tăng tuyến tính theo số events; chỉ phù hợp dataset nhỏ.

Bài lab cố tình **không tạo số latency p95 giả** khi sự kiện mẫu không định nghĩa duration nghiệp vụ cụ thể.

## 12. Cửa sổ thời gian: event time và processing time

Khi tổng hợp theo thời gian, cần phân biệt:

- **Event time:** `RecordedEvent.getStartTime()` hoặc `getEndTime()`.
- **Processing time:** thời điểm callback được gọi trong consumer.
- **Recording time/window:** khoảng thời gian JFR thu thập có thể khác lúc consumer đọc.
- **Flush time:** thời điểm JFR đẩy dữ liệu để consumer có thể quan sát, thường **trễ hơn thời điểm event xảy ra**.

### 12.1. Đếm events theo phút

Một ý tưởng đơn giản, ở mức snippet:

~~~java
Instant eventTime = event.getEndTime();
long minuteBucket = eventTime.getEpochSecond() / 60;
countsByMinute.merge(minuteBucket, 1L, Math::addExact);
~~~

Cần import `java.time.Instant` và có `Map<Long,Long> countsByMinute`. Khi dùng epoch-based buckets:
- Giờ địa phương và timezone để **hiển thị** cần cấu hình rõ.
- Bắt đầu/kết thúc sự kiện có thể nằm ở hai buckets khác nhau; phải chọn quy tắc nhất quán.
- Events đến muộn có thể làm báo cáo của bucket trước **thay đổi** nếu chưa đóng window.

### 12.2. Tỷ lệ events/giây

~~~text
rate = countedEvents / windowDurationSeconds
~~~

Nếu stream đọc file chứa 10 phút events trong 2 giây, **đừng lấy số events chia 2 giây xử lý** rồi gọi đó là request rate thực của ứng dụng; phải dùng **10 phút thời gian recording/event window** theo định nghĩa. Ngược lại, nếu muốn đo tốc độ xử lý của chính parser, processing time lại là mẫu số phù hợp.

### 12.3. Cách tránh double counting khi restart

Nếu collector dùng `setStartTime(Instant.EPOCH)` hoặc quay lại một mốc cũ, repository stream có thể phát lại events **vẫn đang lưu**. Bạn cần:
- Checkpoint cửa sổ hoặc event offset phù hợp.
- Idempotent aggregation nếu flush/report nhiều lần.
- Nhận diện những events có thể trùng nếu chồng nhiều recordings.
- Lưu thông tin phiên bản producer và source identity khi kết hợp đa JVM.
- Có chiến lược cập nhật windows đã chốt khi events đến muộn.

Không nên hứa “exactly once” chỉ từ một lời gọi `onEvent`.

## 13. Độ tin cậy và tính đầy đủ của số liệu

### 13.1. JFR được thiết kế để quan sát với chi phí thấp, nhưng không phải audit log tuyệt đối

JFR tập trung vào quan sát hiệu năng và hành vi runtime. Tùy event type, configuration, threshold và sampling:
- Không ghi mọi thao tác.
- Có thể mất events do giới hạn memory/disk/flush.
- Có dữ liệu thống kê định kỳ chứ không phải từng request.
- Có thể chứa sự kiện đã bắt đầu trước hoặc kết thúc sau cửa sổ đọc.

Nếu nghiệp vụ yêu cầu **đếm tuyệt đối mọi giao dịch để thanh toán**, nguồn chuẩn thường phải là database, transactional log hoặc hệ thống telemetry được thiết kế cho độ chính xác đó. JFR hữu ích để **điều tra, phân tích và đối chiếu**, không tự thay thế ledger dữ liệu.

### 13.2. Phân biệt EventStream.close() và stream đã “hết dữ liệu”

Với **file**, `start()` thường trả về khi đọc hết file. Với **live repository**, `close()` có thể làm stream dừng **ngay hoặc sau một lần flush tiếp theo**; tài liệu nêu rõ close **không bảo đảm mọi callbacks đang đăng ký đã hoàn tất trước khi nó trả về**.

Sử dụng `awaitTermination(Duration)` để đợi stream kết thúc, nhưng cũng không được suy ra rằng **những events chưa flush đã được xử lý**. Kết luận đầy đủ phải dựa trên **mốc kết thúc, policy của producer và điều kiện đọc**.

### 13.3. onError và onClose

~~~java
stream.onError(error -> {
    System.err.println("JFR stream error: "
            + error.getClass().getSimpleName());
});
stream.onClose(() -> {
    System.out.println("JFR stream closed");
});
~~~

Đây là **snippet**, `stream` phải được cấu hình trước `start`. Trong production, ngoài log nên có **trạng thái failure** truyền về điều phối hoặc metrics hệ thống. Không chỉ in exception rồi tiếp tục báo tổng hợp thành công hoàn toàn.

### 13.4. onFlush không đồng nghĩa hoàn thành cả recording

~~~java
stream.onFlush(() -> {
    // Có thể chốt snapshot cửa sổ hoặc push các counters đang gom.
});
~~~

`onFlush` chạy sau khi một batch được xử lý; đối với live stream, những batch **sắp tới vẫn còn tiếp tục đến**. Không coi một lần `onFlush` là kết thúc ghi JFR hoặc đếm đủ tất cả hoạt động của ứng dụng.

## 14. So sánh EventStream và RecordingFile

Ngoài EventStream, JDK có **`RecordingFile`** để duyệt file sequentially:

~~~java
try (RecordingFile file = new RecordingFile(Path.of("requests.jfr"))) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if (event.getEventType().getName().equals("demo.Request")) {
            // Cập nhật Summary ở đây.
        }
    }
}
~~~

Đây là **snippet**, cần import `jdk.jfr.consumer.RecordingFile` và `RecordedEvent`. Nó thích hợp khi muốn kiểm soát vòng lặp đọc file và không cần API callbacks/stream.

### 14.1. Khi nào dùng RecordingFile?

- Chỉ đọc **file offline**.
- Muốn dừng khi đạt một số điều kiện.
- Muốn kiểm soát vòng lặp hoặc làm nhiều pass trên dataset khi có phương án mở lại file.
- Cần metadata từ recording để biết event types trước khi xử lý.

### 14.2. Khi nào dùng EventStream?

- Muốn **cùng cách callback** cho file và repository.
- Chỉ quan tâm đến một vài loại event cụ thể.
- Cần xử lý **asynchronous live events** và onFlush.
- Muốn gắn hooks về error/close và thời gian start/end.

### 14.3. Vì sao không dùng RecordingFile.readAllEvents cho file lớn?

~~~java
List<RecordedEvent> events = RecordingFile.readAllEvents(path);
~~~

Phương thức này có ích với **recording nhỏ đủ vừa bộ nhớ**. Với file nhiều GB, nó có thể tạo áp lực heap rất lớn. Bài tập thực hành ưu tiên **EventStream**/duyệt từng event để giữ memory gần tỷ lệ với số nhóm và các metric đang tổng hợp.

## 15. Thu thập nhiều JVM, nhiều file hoặc nhiều repository

Một dashboard thường tổng hợp từ nhiều nguồn JFR, nhưng không thể chỉ cộng mọi counter một cách mù quáng.

### 15.1. Cần xác định identity và tập nguồn

Ví dụ bạn có:
- `api-instance-1.jfr`.
- `api-instance-2.jfr`.
- Một live repository của instance 2.

Nếu file instance 2 và repository instance 2 bao phủ **cùng khoảng thời gian**, việc cộng cả hai có thể **đếm trùng**.

**Giải pháp:** Với mỗi nguồn, ghi:
- `service` và `instance`, nếu có thông tin đáng tin.
- JVM/version/recording identity.
- Mốc sự kiện bắt đầu/kết thúc.
- Recording settings/threshold.
- Trạng thái “snapshot” hay “live”.
- Chính sách deduplication hoặc chỉ chọn một nguồn đại diện.

### 15.2. Gộp nhiều file

Một chiến lược:
1. Đọc từng file bằng `EventStream.openFile`.
2. Chuẩn hóa schema và lọc khoảng thời gian cần phân tích.
3. Tổng hợp vào cùng một bộ counters/aggregates, **nếu đã loại nguồn trùng**.
4. Đối chiếu các tổng theo từng file với tổng chung.
5. Ghi số file đã đọc, file lỗi, file rỗng và độ bao phủ.

Không nên mở mọi file bằng `readAllEvents` đồng thời chỉ để tiện group-by; dữ liệu lớn có thể gây OOM.

### 15.3. Cách kiểm tra dữ liệu chéo với công cụ có sẵn

- `jfr summary file.jfr`: có event types và event counts mong đợi không?
- `jfr print --events ... file.jfr`: field names/values có đúng không?
- `jfr metadata file.jfr`: schema có đúng không?
- JDK Mission Control: quan sát phân phối theo thời gian và xác nhận bằng biểu đồ.
- Custom aggregator: tính những chỉ số nghiệp vụ mà CLI chuẩn không hiểu, như tổng `demo.Request.bytes`.

Đối chiếu đầu ra của nhiều công cụ giúp phát hiện **nhầm field, nhầm event type, nhầm đơn vị và nhầm phạm vi dữ liệu**.

## 16. Vấn đề hiệu năng của bộ tổng hợp

### 16.1. Tránh giữ từng RecordedEvent ngoài callback

Theo API, EventStream có thể **reuse một RecordedEvent object**. Code nên đọc fields và cập nhật metric ngay trong callback. Với ứng dụng nhiều events/giây, bộ nhớ phụ thuộc số endpoint/tags/histogram buckets, không phụ thuộc tổng số events đã xử lý.

### 16.2. Lọc càng sớm càng tốt

`stream.onEvent("demo.Request", ...)` hiệu quả và rõ hơn `stream.onEvent(e -> {...})` nếu chỉ cần một tên event. Đừng thực hiện I/O nặng hoặc database write cho từng event trong callback; batch/queue có giới hạn để tránh nghẽn consumer.

### 16.3. Cẩn thận với cardinality của group-by

Trong sản phẩm thật, việc group theo raw endpoint, user ID, stack trace hoặc exception message có thể tạo ra **hàng triệu nhóm**:
- Ngốn memory.
- Làm cardinality của metrics backend bùng nổ.
- Có thể chứa dữ liệu nhạy cảm.

Nên group theo **route template, event type, GC cause đã chuẩn hóa, thread group**, hoặc giới hạn số nhóm/top-N theo policy.

### 16.4. Có thể tắt sắp xếp nếu không cần thứ tự

~~~java
stream.setOrdered(false);
~~~

Cần gọi **trước `start`**. Nếu chỉ đếm/sum/merge độc lập với thứ tự, việc không yêu cầu sort có thể giảm chi phí. Nếu phân tích chuỗi nguyên nhân–kết quả hoặc timeline, cần xử lý timestamp/order và tính đến **batch ordering** của JFR.

### 16.5. Concurrent aggregation

Một stream thông thường xử lý callbacks trên thread riêng khi `startAsync()`. Nếu cùng lúc:
- Một HTTP endpoint đọc stats.
- Một scheduler định kỳ reset counters.
- Nhiều JFR streams cập nhật cùng một summary.

thì phải thiết kế **thread safety**. Có thể dùng `LongAdder`, `ConcurrentHashMap` hoặc snapshot/copy-on-write phù hợp; không dùng `TreeMap` không đồng bộ để vừa ghi vừa đọc từ nhiều threads.

Trong **demo**, chỉ một callback stream cập nhật `Summary`, và main thread in **sau `awaitTermination`**, nên mô hình đơn giản đó phù hợp phạm vi bài kiểm chứng.

## 17. Bảo mật, quyền truy cập và vòng đời dữ liệu

### 17.1. JFR có thể chứa dữ liệu nhạy cảm

Tùy event settings và custom fields, một recording có thể chứa:
- Tên class/method và stack traces.
- Tên thread, đường dẫn file, socket endpoints.
- Command line/VM flags.
- Trạng thái ứng dụng trong custom event.
- Chuỗi bất kỳ mà developer vô tình ghi từ request/response.

**Không nhúng secrets, token, mật khẩu, nội dung PII chưa được kiểm soát vào custom event.** Không gửi tệp JFR production lên dịch vụ bên ngoài khi chưa đánh giá dữ liệu và quyền chia sẻ.

### 17.2. Chỉ mở nguồn tin cậy

Theo Javadoc của `EventStream.openFile` và `openRepository(Path)` trong JDK hiện đại, **chỉ nên mở nguồn recording/repository đáng tin**. Tệp giả mạo hoặc cực lớn có thể tiêu tốn CPU/bộ nhớ, và dữ liệu ghi nhận có thể gây rò rỉ thông tin khi báo cáo.

### 17.3. Không tự xóa/chỉnh repository đang được JVM sử dụng

Repository là vùng hoạt động của JFR:
- JVM có thể đang ghi và rotate chunks.
- JVM có thể xóa file sau khi recording/VM kết thúc.
- Một consumer có thể chưa đọc xong chunk.

Không chuyển, rename hoặc xóa thủ công các file trong repository sống để “dọn chỗ”. Nếu cần giữ data, dùng các cơ chế **Recording.dump**, retention/size/age policy và backup phù hợp.

### 17.4. Đường dẫn file và quyền

Với file:
- Chọn một đường dẫn output đủ dung lượng.
- Dọn file lab sau khi không còn cần.
- Không ghi đè tệp production có ý nghĩa nếu chưa có chính sách overwrite.
- Lưu nhật ký metadata của recording và version JDK dùng để đọc.

Với repository:
- Xác nhận đường dẫn là một **JFR disk repository thật**, không phải thư mục rỗng tùy ý.
- Đảm bảo quyền read của consumer và write của JVM producer.
- Cân nhắc OS, container path mapping, user/group và tiến trình có thể đang thay đổi.
- Nếu đọc repository của JVM khác, cần hiểu vấn đề chia sẻ file hệ thống; `openRepository(Path)` tự nó không mở JMX/network connection.

## 18. Những lỗi thường gặp và cách xử lý

### Lỗi A — Nhầm JFR repository với thư mục Git

**Sai:** truyền `/src/my-java-repo` vào `EventStream.openRepository(Path)` chỉ vì đó là source repository.

**Sửa:** đường dẫn phải là **JFR disk repository** chứa chunks do JVM/JFR tạo ra. Với file `.jfr`, dùng `openFile(Path)`.

### Lỗi B — Dùng openRepository() rồi nghĩ đang đọc một .jfr file trên ổ đĩa

**Sai:** `openRepository()` đọc repository của **JVM hiện tại**, không nhận đường dẫn file.

**Sửa:** `openFile(Path.of("recording.jfr"))` để đọc tệp hoàn chỉnh.

### Lỗi C — Repository stream in 0 dù producer vừa commit 5 events

**Nguyên nhân có thể:** chưa flush, stream chưa bắt đầu, mặc định chỉ đọc events được flush tiếp theo, recording không ghi xuống disk, stream đóng quá sớm.

**Sửa:** đảm bảo recording đã bật/ghi disk, stream được khởi động đúng, mốc `setStartTime` phù hợp, cho event flush và kiểm soát thời gian chờ. Demo đã kiểm chứng trường hợp này.

### Lỗi D — Coi onFlush là đã đọc hết repository

**Sai:** repository đang tiếp tục ghi. `onFlush` chỉ nói một batch vừa được xử lý.

**Sửa:** xác định cửa sổ báo cáo, điều kiện dừng và chính sách xử lý events đến muộn.

### Lỗi E — Dùng cùng số liệu từ file snapshot và live repo

**Sai:** nếu bao phủ cùng sự kiện, sẽ đếm trùng.

**Sửa:** tránh overlap hoặc có cơ chế dedup/checkpoint, ghi rõ source và window.

### Lỗi F — Đọc mọi event rồi giữ list vô hạn

**Sai:** tốn RAM, có thể giữ các `RecordedEvent` bị reuse.

**Sửa:** aggregate ngay trong callback; chỉ lưu sample/histogram có giới hạn. Nếu bắt buộc giữ event object, xem `setReuse(false)` và memory budget.

### Lỗi G — Dùng jfr summary Size (bytes) làm tổng response bytes

**Sai:** đây là size của **dữ liệu sự kiện JFR**, không phải field `bytes` của custom event.

**Sửa:** đọc `RecordedEvent.getLong("bytes")` rồi cộng các giá trị nghiệp vụ.

### Lỗi H — Giả định mọi event đều được ghi

**Sai:** có threshold, sampling, enable/disable, buffer/flush và retention.

**Sửa:** xem settings, metadata và thời gian quan sát; không xem count JFR là audit transaction count nếu không có cơ sở.

### Lỗi I — Lấy trung bình % CPU sai

**Sai:** `machineTotal=0.76` bị báo là `0.76%`, hoặc lấy trung bình không xét thời gian sample không đồng đều.

**Sửa:** đổi ratio sang percentage khi hiển thị; dùng cách tổng hợp sample/window phù hợp.

### Lỗi J — Chia cho 0 khi không có events

**Sai:** `bytes / count` khi count bằng 0.

**Sửa:** báo `n/a` hoặc một trạng thái thiếu dữ liệu được thiết kế rõ.

### Lỗi K — Gộp p95 của hai JVM bằng phép trung bình

**Sai:** percentile không cộng/trung bình đơn giản.

**Sửa:** dùng dữ liệu phân phối/histograms có thể merge theo thuật toán phù hợp và có error bounds.

### Lỗi L — Close xong đã chắc chắn đọc hết events?

**Sai:** `close()` có thể dừng ngay hoặc sau flush tiếp theo; events chưa flush có thể không được callback.

**Sửa:** đo trạng thái bao phủ, await termination và nếu cần snapshot ổn định thì dump file rồi đọc offline.

### Lỗi M — Dùng CLI jfr version khác rồi khẳng định API không có

**Sai:** CLI subcommands và reporting views có thể được mở rộng qua JDK.

**Sửa:** kiểm tra `jfr help` và Javadoc của **đúng phiên bản JDK**, giữ APIs ổn định (EventStream, RecordingFile) cho code.

### Lỗi N — Tên field khác hoặc field thiếu

**Sai:** hard-code `getLong("bytes")` cho event `jdk.GarbageCollection` không có field này.

**Sửa:** lọc theo loại event, xác minh schema bằng `jfr metadata` / `getFields()` / `hasField`; không trộn fields giữa các event types.

### Lỗi O — Lạm dụng Math.addExact mà không xử lý exception

**Sai:** cho rằng `Math.addExact` tự làm báo cáo “chắc chắn an toàn” khi count cực lớn.

**Sửa:** nó **phát hiện tràn**, không tự mở rộng số; trong production cần policy về overflow, BigInteger hoặc phân mảnh cửa sổ.

### Lỗi P — Không có event nhưng báo "ứng dụng không có GC"

**Sai:** `jdk.GarbageCollection` có thể không được ghi, đã bị lọc, hoặc khoảng quan sát không có event.

**Sửa:** kiểm tra JFR settings và event types trong file; diễn giải đúng giới hạn quan sát.

## 19. Bài tập tổng hợp kèm đáp án

### Bài 1 — Tính metrics từ events

Có bốn events:

~~~text
endpoint=/a bytes=120 success=true
endpoint=/b bytes=80  success=false
endpoint=/a bytes=200 success=true
endpoint=/b bytes=100 success=true
~~~

Hỏi count, successes, errors, bytes, average bytes, error rate và group-by endpoint.

**Đáp án:**
- Count **4**, successes **3**, errors **1**.
- Tổng bytes **500**.
- Average **500 / 4 = 125 bytes/event**.
- Error rate **1 / 4 = 25%**.
- Endpoint `/a = 2`, `/b = 2`.

### Bài 2 — Chọn API

Có tệp `incident.jfr` đã dump xong. Dùng `EventStream.openRepository(Path)` hay `openFile(Path)`?

**Đáp án:** **`EventStream.openFile(Path.of("incident.jfr"))`**. `openRepository` dành cho disk repository, không phải file.

### Bài 3 — Repository không in gì

Một live stream mở thành công nhưng không thấy callback. Nêu bốn giả thuyết.

**Đáp án:** Event chưa bật; event chưa được commit/flush; stream mặc định bắt đầu từ flush tiếp theo và bỏ lỡ events cũ; sai tên event hoặc sai repository; recording không ghi disk; stream đóng quá sớm.

### Bài 4 — Hiểu đúng jfr summary

`jfr summary` cho `demo.Request Count=5, Size=79 bytes`. Program lại tính `Bytes=1000`. Hai con số có mâu thuẫn không?

**Đáp án:** **Không**. `79` mô tả dung lượng JFR event records của loại này trong recording; `1000` là tổng field ứng dụng `bytes` trong năm sự kiện.

### Bài 5 — Tính request rate

File chứa 6.000 request events trải từ 10:00 đến 10:10, parser đọc xong trong 2 giây.

**Đáp án:** Nếu cửa sổ quan sát đúng **600 giây**, request rate là **6000/600 = 10 req/s**, **không phải 3000 req/s** (đó là tốc độ parse).

### Bài 6 — Mẫu CPU

`jdk.CPULoad.machineTotal = 0.42`. Nếu muốn hiển thị theo phần trăm?

**Đáp án:** `42%`. Kiểm tra số liệu lấy mẫu trước khi tổng hợp qua thời gian.

### Bài 7 — Replay repository

Collector restart và dùng `setStartTime(Instant.EPOCH)`. Vì sao tổng request có thể tăng sai?

**Đáp án:** Các chunks cũ vẫn còn có thể được replay, khiến events đã tính lần trước được **đếm lại**. Cần checkpoint/dedup/window, hoặc chỉ đọc events mới tùy yêu cầu.

### Bài 8 — Tại sao không giữ List<RecordedEvent> vô hạn?

**Đáp án:** Tốn memory theo số event, và EventStream có thể **reuse event object** khiến references được giữ không phản ánh đúng từng event. Tổng hợp field values ngay trong callback.

### Bài 9 — P95 từ nhiều nguồn

Server A p95=10ms, server B p95=300ms. Có thể lấy trung bình thành p95 chung=155ms không?

**Đáp án:** **Không**. Cần phân bố durations/histogram có thể merge, cùng định nghĩa/cửa sổ thời gian, rồi tính percentile tổng.

### Bài 10 — Tổng hợp GC đúng nghĩa

Một chương trình đếm `jdk.GarbageCollection` và cộng durations. Nó có thể kết luận mọi thread JVM bị stop đúng bằng tổng durations không?

**Đáp án:** **Không tự động**. Duration của event GC theo schema JFR không nhất thiết đồng nghĩa tổng stop-the-world pause của mọi application threads. Muốn phân tích stop-the-world pause, cần chọn các JFR event types và metrics phù hợp, ví dụ một số `jdk.GCPhasePause` events, đối chiếu metadata và GC logs.

### Bài 11 — Chọn RecordingFile hay EventStream

Bạn muốn đọc tuần tự một recording nhỏ và xử lý một event ở mỗi vòng lặp.

**Đáp án:** `RecordingFile` phù hợp. Nếu muốn chung pipeline đọc **file và live repository**, chọn `EventStream`.

### Bài 12 — Bảo vệ dữ liệu JFR

Một custom event có thể ghi userId, authorization header và nội dung request body.

**Đáp án:** Không đưa secrets/PII chưa được phê duyệt vào JFR; thiết kế event schema tối thiểu, kiểm soát quyền truy cập, retention và chia sẻ recording. Chỉ mở nguồn JFR đáng tin cậy.

## 20. Checklist trước khi công bố một bản tổng hợp JFR

- [ ] Xác nhận **nguồn dữ liệu** là `.jfr`, JFR repository hiện tại hoặc repository theo Path.
- [ ] Với nguồn repository, biết **JVM producer**, đường dẫn thật, quyền và mốc bắt đầu đọc.
- [ ] Với nguồn file, biết **thời gian recording**, phiên bản JDK và event settings.
- [ ] Event type đã được bật; biết threshold/sampling/period nếu có.
- [ ] Không nhầm **event count** với **transaction count** nếu event được sample.
- [ ] Các fields, data types và units đã được xác minh.
- [ ] Công thức sum/avg/error rate có **mẫu số và thời gian** rõ ràng.
- [ ] Có chính sách cho **0 events**, missing fields và overflow.
- [ ] Group labels được chuẩn hóa, tránh cardinality quá cao.
- [ ] Không giữ `RecordedEvent` lâu ngoài callback khi EventStream có object reuse.
- [ ] Có time windows, source identity, checkpoints và xử lý trùng dữ liệu nếu cần.
- [ ] Có cách phân biệt **live snapshot** và **file offline hoàn chỉnh**.
- [ ] Hiểu `onFlush`, `close` và `awaitTermination` không đồng nghĩa đã nhìn thấy mọi event chưa flush.
- [ ] Với production, không dùng lab `CountDownLatch(5)` và `Instant.EPOCH` một cách máy móc.
- [ ] Với metrics chuẩn `jdk.*`, kiểm tra schema và units trước khi suy luận.
- [ ] Đã đối chiếu với `jfr summary`, `jfr print` hoặc JMC khi thích hợp.
- [ ] Đã kiểm tra permission, thông tin nhạy cảm, retention và nguồn recording tin cậy.
- [ ] Báo cáo nêu **độ bao phủ và giới hạn**, không tuyên bố tính đúng tuyệt đối khi thiếu dữ liệu.
- [ ] Quy trình đã test với một tệp nhỏ và một live repository trước khi dùng dữ liệu thật.

## 21. Kết luận

**Tổng hợp số liệu từ JFR là quá trình chuyển chuỗi `RecordedEvent` thành các phép đo có định nghĩa rõ ràng**, không phải chỉ đọc kích thước tệp hoặc đếm số dòng log.

- **`EventStream.openFile(Path)`** phù hợp cho tệp `.jfr` offline.
- **`EventStream.openRepository()`** hoặc **`openRepository(Path)`** phù hợp để xem JFR disk repository trong lúc dữ liệu được flush.
- **`onEvent(name, callback)`** cho phép lọc event type và cập nhật trực tiếp counters/sums/groups.
- **`RecordingFile`** là lựa chọn tốt nếu chỉ cần đọc tuần tự file; `readAllEvents` chỉ phù hợp recording nhỏ.
- **`jfr summary`** đếm events và dung lượng event records; muốn tổng hợp các trường nghiệp vụ phải đọc **field values**.
- **Repository là nguồn sống**; muốn số liệu đủ và đúng cửa sổ cần hiểu flush, start/end time, retention và close semantics.
- **JFR không tự bảo đảm đếm tuyệt đối** đối với mọi event type; threshold/sampling, recording config và lifecycle ảnh hưởng độ bao phủ.
- **Ví dụ thực hành đã kiểm chứng** trên JDK hiện đại với mã `--release 17`: cùng năm custom events tạo ra kết quả identical khi tổng hợp từ file, repository hiện tại và repository chỉ định.
- **Bảo mật và nguồn tin cậy** phải được xem là một phần thiết kế, vì JFR có thể chứa dữ liệu nhạy cảm.

**Nguồn tài liệu chính thức, còn áp dụng:**
- [Oracle JDK 25 — EventStream](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): `openFile`, `openRepository`, `onEvent`, `onFlush`, `setStartTime`, `setReuse`, `close`.
- [Oracle JDK 17 — EventStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): tương thích với `--release 17`.
- [Oracle JDK 25 — Recording](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): tạo, cấu hình, dump recording và `setToDisk`.
- [Oracle JDK 25 — RecordedEvent](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): typed fields, duration và timestamp.
- [Oracle JDK 25 — RecordingFile](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): xử lý offline và reading API.
- [Oracle JDK 25 — jfr Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `summary`, `print`, `metadata`, `view` và `assemble`.
- [Oracle JDK 21 — jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `JFR.start`/`JFR.dump`/`JFR.configure`.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): tính năng Java 14 và streaming events từ repository.
- [OpenJDK Dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): recording settings và repository configuration.
