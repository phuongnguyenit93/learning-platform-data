# Stack cấp phát, kích thước đối tượng và sai số — Heap profiling bằng JFR trong Java 11+

## 1. Mục tiêu và bối cảnh

**Heap allocation profiling** dùng để trả lời: ứng dụng Java đang tạo các đối tượng nào, những lệnh gọi nào dẫn tới cấp phát, và lượng cấp phát đó có làm tăng áp lực GC, latency hoặc CPU không?

**Java Flight Recorder (JFR)** ghi các sự kiện (*events*) của JVM và ứng dụng thành file `.jfr`. Trong **Java 11**, ta có thể dùng các allocation events theo TLAB để quan sát **allocation stack**, **kích thước object gắn với event**, **kích thước TLAB mới** và những giới hạn suy luận. API đọc file nằm trong module `jdk.jfr`.

Đề bài có ba trục:

1. **Stack cấp phát:** call chain tại điểm allocation được JFR ghi nhận; không phải toàn bộ call stacks của tất cả object.
2. **Kích thước đối tượng:** phân biệt `allocationSize`, `tlabSize`, kích thước mảng ở source, shallow size và retained size.
3. **Sai số:** TLAB chỉ ghi một phần các allocation sites; JIT, lựa chọn event, stack depth, retention, thời gian recording và statistical sampling khiến kết luận có sai lệch.

**Quy tắc trọng tâm:** một bản ghi JFR về cấp phát **không đồng nghĩa một object duy nhất đã tồn tại trong toàn bộ heap**, và số lượng event **không phải** tổng số object do ứng dụng tạo.

Bài ưu tiên **API Java 11 vẫn dùng được trên JDK hiện đại**. Cần phân biệt một cải tiến về sau: `jdk.ObjectAllocationSample` được giới thiệu ở **JDK 16**, nên không giả định có sẵn trong Java 11. Không dùng mẹo profiling lỗi thời hoặc công cụ không còn được hỗ trợ làm cách khuyến nghị.

## 2. Allocation rate không phải heap size hay memory leak

| Câu hỏi | Thuật ngữ | Cần quan sát |
| --- | --- | --- |
| Ứng dụng cấp phát bao nhiêu byte mỗi giây? | **Allocation rate** | Allocation statistics, weighted samples hoặc metrics tương ứng |
| Call chain nào thường gắn với nhiều allocations? | **Allocation hot spot** | JFR allocation events, stack và class |
| Bao nhiêu byte heap còn sống sau GC? | **Live heap** | Heap/GC metrics, object liveness |
| Một object đang giữ sống các object khác ra sao? | **Retained heap** | Heap dump, reference graph, dominator tree |
| Object sống lâu không còn cần dùng ở đâu? | **Leak diagnosis** | `jdk.OldObjectSample`, GC roots, heap analysis |

Một chương trình có thể tạo 100 MB đối tượng tạm mỗi giây, nhưng sau GC chỉ giữ vài MB. Đó là **áp lực cấp phát**, chưa đủ để kết luận leak.

Ngược lại, cache hoặc listener giữ lại một số object nhỏ mỗi phút có thể gây leak chậm; nếu chỉ xem allocation hot spots của mảng lớn, bạn có thể bỏ qua nguyên nhân giữ tham chiếu.

**Khi phân tích:** dùng allocation stacks để tìm nơi tạo object, kết hợp GC events để xác minh tác động, và dùng công cụ liveness/retained heap khi cần xác định object không được thu hồi.

## 3. TLAB và vì sao số event không bằng số object

**TLAB (Thread Local Allocation Buffer)** là một vùng bộ nhớ trong Java heap mà JVM dành cho một thread nhằm cấp phát các object nhỏ với chi phí đồng bộ thấp.

Mô hình:

```text
Thread A
   |
   | new Object(), new byte[1024], ...
   v
TLAB hiện tại  [đã dùng................][còn trống]
   |
   | nhiều lần cấp phát nhỏ, không phát mỗi lần một event TLAB mới
   v
TLAB sắp hết [đã dùng........................][ít chỗ]
   |
   | object tiếp theo cần TLAB khác
   v
Nhận TLAB mới
   |
   +-- jdk.ObjectAllocationInNewTLAB
   |
   v
Tiếp tục cấp phát object trong TLAB mới

Một số object lớn:
   new byte[512 * 1024]
      |
      +-- có thể cấp phát ngoài TLAB
             |
             +-- jdk.ObjectAllocationOutsideTLAB
```

**`ObjectAllocationInNewTLAB` không tạo một event cho mọi phép `new`.** Một thread có thể cấp phát hàng nghìn đối tượng nhỏ trong cùng TLAB. Sự kiện này gắn với lần cấp phát dẫn đến việc nhận TLAB mới, không ghi lại đầy đủ những cấp phát đã đi qua TLAB trước đó.

Còn `ObjectAllocationOutsideTLAB` phản ánh những lần cấp phát ngoài TLAB. Object lớn thường đi theo đường này, nhưng ranh giới phụ thuộc JVM/GC/heap và cấu hình TLAB; không được tuyên bố rằng mọi object lớn hơn một số byte cố định đều outsideTLAB ở mọi runtime.

**Quan trọng:** OutsideTLAB vẫn là cấp phát object trong Java heap theo cơ chế tương ứng; nó **không có nghĩa object được cấp phát native/off-heap** và **không đồng nghĩa OutOfMemoryError**.

## 4. Những event liên quan đến heap profiling

### 4.1. Event có trên HotSpot Java 11

| Event | Trường cần đọc | Dùng để làm gì? |
| --- | --- | --- |
| `jdk.ObjectAllocationInNewTLAB` | `objectClass`, `allocationSize`, `tlabSize`, `eventThread`, `stackTrace` | Phân tích những lần allocation gắn với TLAB mới |
| `jdk.ObjectAllocationOutsideTLAB` | `objectClass`, `allocationSize`, `eventThread`, `stackTrace` | Phân tích allocations ngoài TLAB |
| `jdk.ThreadAllocationStatistics` | `thread`, `allocated`, thời điểm ghi | Đối chiếu xu hướng bytes cấp phát theo thread |
| `jdk.OldObjectSample` | `object`, `objectAge`, `objectSize` cùng ngữ cảnh tùy recording | Điều tra những object sống lâu và nghi leak |

Các tên trường được nêu với mục đích phân tích JFR Java 11/HotSpot. **JFR events và field set có thể khác theo bản JDK, vendor hoặc JVM**, nên consumer phải kiểm tra runtime metadata bằng `FlightRecorder.getFlightRecorder().getEventTypes()` hoặc `event.hasField(name)`.

Một recording bình thường **không nhất thiết bật sẵn** cả hai allocation event chi tiết. Muốn đo phải chủ động bật bằng `Recording.enable(eventName)` hoặc dùng cấu hình recording phù hợp.

### 4.2. ObjectAllocationSample chỉ có từ JDK 16

Theo JDK 16 release notes, event **`jdk.ObjectAllocationSample`** được thêm để hỗ trợ **low-overhead sampled allocation profiling**. Các trường đáng chú ý có `objectClass`, `weight`, `eventThread` và `stackTrace`.

- `weight` là **trọng số thống kê**, thể hiện lượng allocation pressure tương đối được sample đại diện.
- **Không** được gọi `weight` là kích thước thật của object đang hiện trong mẫu.
- Tổng hợp weights trên đủ nhiều sample theo class/thread/stack có thể ước lượng allocation pressure, với sai số chọn mẫu.
- Runtime/phần mềm profiling có thể áp dụng throttling và settings khác nhau; số mẫu không cố định.
- **Java 11 không có event này**. Không viết mã `recording.enable("jdk.ObjectAllocationSample")` trong ví dụ Java 11 rồi mặc định nó ghi dữ liệu.

Đối với Java 11, các event `InNewTLAB` và `OutsideTLAB` vẫn là lựa chọn có ý nghĩa, nhưng thường phù hợp hơn cho **điều tra ngắn hạn** vì overhead và volume. Trên JDK 16+, nếu mục tiêu là profiling thường trực, cân nhắc allocation sampling thế hệ mới và kiểm chứng trên chính runtime.

### 4.3. Sự kiện cấp phát khác với sự kiện GC

Một lần GC có thể thu hồi hàng triệu object được cấp phát trong nhiều giây trước đó. Event cấp phát ghi **vị trí và kích thước khi object xuất hiện**, không phải thời điểm object chết hoặc được thu hồi.

Không cộng những `allocationSize` rồi tuyên bố đó là **used heap sau GC**. Nếu muốn biết leak, cần dữ liệu về liveness, reference graph, heap growth và đối chứng qua nhiều GC cycles.

## 5. Stack cấp phát: đọc gì từ một RecordedEvent?

JFR có thể gắn **stack trace** với allocation event, cho biết các method nằm trên đường gọi gần thời điểm ghi nhận allocation.

Ví dụ minh họa:

```text
RequestHandler.handle()
  -> JsonSerializer.serialize()
      -> BufferFactory.newBuffer()
          -> new byte[...]
```

Stack trace giúp đặt câu hỏi: chính serializer là nơi cần tối ưu, hay caller đã đưa dữ liệu vào serializer quá nhiều lần?

Tuy nhiên **đừng coi stack của `ObjectAllocationInNewTLAB` là stack của mọi object nằm trong TLAB**. Nó chỉ gắn với object gây ra event khi TLAB mới được cấp. Rất nhiều allocations tiếp theo trong TLAB có thể đến từ các method khác.

### 5.1. Java 11 API đọc stack

```java
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedStackTrace;

RecordedStackTrace stack = event.getStackTrace();
if (stack != null) {
    for (RecordedFrame frame : stack.getFrames()) {
        if (frame.getMethod() != null) {
            String methodName = frame.getMethod().getName();
            System.out.println(methodName);
        }
    }
    System.out.println("truncated = " + stack.isTruncated());
}
```

Đây là **mảnh code** với biến `RecordedEvent event` có sẵn. Nó không biên dịch độc lập nếu chưa được đặt vào một phương thức.

- `getStackTrace()` có thể là `null` nếu event không ghi stack.
- `getFrames()` trả các Java frames được ghi lại.
- `isTruncated()` phản ánh stack bị cắt vì giới hạn độ sâu.
- Mỗi frame có metadata về method, line number và loại frame khi có dữ liệu tương ứng.

**Không mặc định top frame luôn là controller/service gốc.** Có thể thấy constructors, helpers, framework, method đã inline hoặc compiler-generated code. Để xác định nguyên nhân nghiệp vụ, xem call chain rộng hơn.

### 5.2. Bật/tắt stack trace

```java
Recording recording = new Recording();
recording.enable("jdk.ObjectAllocationInNewTLAB")
        .withStackTrace();
recording.enable("jdk.ObjectAllocationOutsideTLAB")
        .withStackTrace();
```

Đây là mảnh cấu hình Java, cần import `jdk.jfr.Recording` và quản lý vòng đời `start/stop/dump/close`.

Bật stack traces giúp phân tích allocation site nhưng tăng kích thước file và chi phí ghi. `withoutStackTrace()` giảm dữ liệu, đổi lại không còn call chain đầy đủ để chẩn đoán.

Độ sâu stack cũng có giới hạn. Trên HotSpot, nếu đã xác minh stack bị truncate, có thể cân nhắc tùy chọn JVM như:

```bash
java -XX:FlightRecorderOptions=stackdepth=128 ...
```

Đây là **mẫu lệnh**, dấu `...` chỉ command/arguments ứng dụng cần cung cấp, không phải một lệnh độc lập chạy được. Stack sâu hơn tăng overhead; không cấu hình quá sâu trên mọi hệ thống khi chưa có nhu cầu.

### 5.3. Nguyên nhân có stack thiếu hoặc khác dự kiến

- Event bị disable hoặc `stackTrace` setting là false.
- Call path quá sâu; `RecordedStackTrace.isTruncated()` là true.
- JIT inlining, escape analysis hay optimized code làm frame khác source.
- Allocation xảy ra trong helper, callback hoặc framework.
- Thread khác tạo object, không phải thread đang đọc request.
- File recording không bao trùm thời điểm cấp phát.
- Chỉ có các mẫu gắn với thời điểm TLAB refill; không nhất thiết chọn đúng call site nhiều allocation nhất.

Vì vậy stack trace là **tín hiệu phân tích**, không phải bảng thống kê exact byte attribution theo mọi method.

## 6. allocationSize, tlabSize và object layout

### 6.1. allocationSize là kích thước object được báo trong event

Trong hai event TLAB của Java 11:

```java
long allocationBytes = event.getLong("allocationSize");
```

Trường này biểu diễn số byte cấp phát cho **object gây sự kiện** theo JVM. Nó không phải số lần object được tạo, không phải toàn bộ heap và không phải retained size.

Ví dụ:

```java
byte[] data = new byte[1024];
System.out.println(data.length); // 1024
```

`1024` là **số byte phần tử trong mảng**, không phải kích thước object thực tế trong heap. Array object còn có header, trường length và padding/alignment. Kích thước thực phụ thuộc JDK/JVM/architecture và compressed references; không tự gán một số header cố định cho mọi máy.

### 6.2. tlabSize là kích thước buffer mới

Chỉ `jdk.ObjectAllocationInNewTLAB` có thêm:

```java
long newTlabBytes = event.getLong("tlabSize");
```

Đây là kích thước **TLAB mới được cấp cho thread**, không phải kích thước object gây event.

Ví dụ **giá trị giả lập để giải thích**, không phải stdout:

```text
objectClass    = byte[]
allocationSize = 1040 bytes      (minh họa)
tlabSize       = 262144 bytes    (minh họa)
```

**Sai:** “Method tạo array trên stack này đã cấp phát đúng 262144 byte object vì `tlabSize` bằng con số đó.”

**Đúng:** “Một event gắn với việc lấy TLAB mới; trường `tlabSize` mô tả kích thước buffer, còn `allocationSize` mô tả object kích hoạt event. Attribution byte theo site cần thêm nhiều mẫu và đối chứng.”

TLAB có thể còn phần trống chưa dùng. Nếu gán toàn bộ `tlabSize` cho call site khiến refill, bạn có thể đổ nhầm những bytes mà sau đó các method khác mới dùng.

### 6.3. OutsideTLAB không có tlabSize

`jdk.ObjectAllocationOutsideTLAB` có `allocationSize` nhưng **không có `tlabSize`**. Khi viết consumer tổng quát, phải kiểm tra:

```java
if (event.hasField("tlabSize")) {
    long bytes = event.getLong("tlabSize");
}
```

Nếu gọi `getLong("tlabSize")` trên event không có field này, API có thể ném `IllegalArgumentException`. Đừng dùng cùng một schema cứng cho mọi JFR allocation event.

### 6.4. Shallow size, retained size và sample weight

| Loại size | Ý nghĩa |
| --- | --- |
| **Shallow size** | Byte trực tiếp của bản thân object trong heap; không cộng object mà nó tham chiếu |
| **Retained size** | Byte có thể được giải phóng theo reference/dominator model khi object không còn giữ một tập object khác |
| **allocationSize** | Byte cấp phát của object gắn với event |
| **tlabSize** | Kích thước TLAB mới của thread, không phải object |
| **weight** (JDK 16+ sample) | Trọng số thống kê đại diện allocation pressure |
| **OldObjectSample.objectSize** | Kích thước object sống lâu được lấy mẫu, không phải toàn bộ retained graph |

Ví dụ một `Order` có reference tới một `List<OrderItem>`. Cấp phát một `Order` không có nghĩa `allocationSize` của nó bằng tổng bytes của toàn bộ danh sách. Object graph có thể sống lâu hoặc ngắn độc lập với nơi object mẹ được tạo.

Java 11 **không có `Object.getSize()`**. `java.lang.instrument.Instrumentation.getObjectSize(Object)` cần Java agent và chỉ trả một **ước lượng implementation-specific của shallow size**, không tự đo retained graph.

## 7. Những nguồn sai số quan trọng

### 7.1. Sai số do sampling/TLAB refill

`ObjectAllocationInNewTLAB` chỉ chọn những allocation gắn với TLAB mới. **Count event không bằng count object**. Trong cùng một TLAB, hàng trăm object có thể được cấp phát mà không phát thêm event.

Đặc biệt, **allocation kích hoạt refill có thể thuộc method khác** với các allocations đã lấp TLAB hoặc sẽ dùng TLAB sau đó. Vì vậy cộng toàn bộ `tlabSize` theo stack của event rồi gọi là “số byte chính xác do stack đó tạo” là sai.

Đối với `ObjectAllocationSample` JDK 16+, `weight` dùng cho ước lượng; cần đủ số mẫu và chấp nhận sampling variance. Một sample đơn lẻ không đại diện tuyệt đối cho một class, một request hay một method.

### 7.2. Sai số do JIT và runtime

Một phép `new` trong source có thể bị JIT tối ưu, scalar replacement hoặc escape analysis; không phải mọi `new` đều tương ứng một object heap hiển thị trong JFR.

JIT inlining còn ảnh hưởng stack frames. Cùng source code nhưng ở hai giai đoạn warm-up khác nhau có thể cho profiler output khác biệt. GC, kích thước heap, TLAB resizing và collector cũng thay đổi số event.

**Không đếm keyword `new` trong source rồi coi là object count thật.**

### 7.3. Sai số do recording window

Nếu recording bắt đầu **sau khi cache được xây**, các allocation lúc khởi động không xuất hiện. Nếu chỉ ghi 1 giây trong workload có burst, kết quả dễ thiên lệch.

Để so sánh before/after, giữ cùng workload và khung thời gian, đo nhiều lượt. Trong dịch vụ, ghi rõ request rate, JDK, GC, heap, configs và thời điểm incident.

### 7.4. Sai số do stack và dữ liệu thiếu

- `getStackTrace() == null` vì không ghi stack.
- Stack bị truncate hoặc không thấy caller do inlining.
- Object class có nhiều classloaders khác nhau.
- Event type không được bật hoặc runtime không phát event tương ứng.
- JFR repository xóa chunk cũ do maxAge/maxSize, hoặc file dump thiếu cửa sổ quan sát.
- Một số event bị sample/throttled hoặc có overhead giới hạn capture.

**Sai số thống kê** khác với **nhầm định nghĩa**. Thu thêm dữ liệu không thể sửa lỗi lấy `tlabSize` làm object size.

### 7.5. So sánh môi trường phải có đối chứng

Nếu lượng TLAB events giảm 20%, có thể do ít allocation hơn, **hoặc** TLAB lớn hơn/khác GC hoặc workload. Hãy đối chiếu với:

- `jdk.ThreadAllocationStatistics` và các metrics thread allocation khi phù hợp.
- GC frequency, pause time, heap used, throughput.
- Allocation weighted sampling trên JDK mới nếu được hỗ trợ.
- Benchmark/production workload được lặp lại với input và warm-up tương đương.

Không tuyên bố tiết kiệm chính xác X byte chỉ từ tỷ lệ event count giảm.

## 8. Cách tổng hợp dữ liệu cho đúng

### 8.1. Không cộng allocationSize của InNewTLAB để có toàn bộ bytes

Ví dụ giả lập:

```text
100 InNewTLAB events, mỗi allocationSize = 1 KiB
10 OutsideTLAB events, mỗi allocationSize = 512 KiB
```

**Không kết luận** tổng cấp phát của ứng dụng là `100 KiB + 5 MiB`. Nhiều object nhỏ đã được cấp phát trong các TLAB nhưng không tạo event riêng.

`sum(allocationSize)` khi đọc InNewTLAB là tổng size của **các object gây sự kiện đã được ghi**, không bao gồm toàn bộ object khác.

### 8.2. Tổng tlabSize chỉ là tín hiệu áp lực TLAB

Tổng `tlabSize` của những lần lấy TLAB mới có thể là một **chỉ báo ước lượng** về lượng buffer được cấp trong cửa sổ quan sát, nhưng không phải số byte object thực dùng tuyệt đối vì có waste, chunk/event coverage và TLAB adaptive sizing.

Đặc biệt, **không phân bổ toàn bộ tlabSize cho chính stack của object trigger** như số liệu exact về allocation site. Đây là vấn đề attribution bias.

### 8.3. Weighted samples trên JDK 16+

Nếu runtime có `jdk.ObjectAllocationSample` và đủ mẫu, thường có thể tính:

```text
estimatedBytes(group) = sum(weight của các samples thuộc group)
estimatedRate(group)  = estimatedBytes(group) / durationSeconds
```

Đây là **ước lượng** theo điều kiện sampling; cần chú thích thời gian quan sát, độ phủ mẫu và sai số. **Không áp công thức `weight` này cho `allocationSize` của event TLAB Java 11**.

### 8.4. Nhóm theo stack, class và thread

Dữ liệu hữu ích khi nhóm theo:

- **objectClass:** loại object hay xuất hiện.
- **top frame:** method gần điểm phát event.
- **full stack/call path:** xác định đường nghiệp vụ tạo allocation.
- **eventThread:** phân biệt các luồng cùng cấp phát loại object.
- **time window:** xem allocation burst thay vì trung bình nhiều giờ.

Cần thận trọng: chỉ nhóm theo top frame có thể đổ mọi chi phí về helper như `Arrays.copyOf` dù caller nghiệp vụ mới là nguyên nhân. Chỉ nhóm theo class có thể trộn nhiều allocation sites.

## 9. Chương trình Java 11 độc lập: ghi JFR allocation events thật

Chương trình sau **không cần dependency bên ngoài JDK**. Nó:

1. Xác minh `jdk.ObjectAllocationInNewTLAB` và `jdk.ObjectAllocationOutsideTLAB` có trên runtime, cùng các field cần thiết.
2. Bật hai loại event với stack trace.
3. Trong recording, tạo 40.000 mảng byte nhỏ (`1024` phần tử) và 128 mảng lớn (`512 * 1024` phần tử).
4. Dùng `volatile` field `escape` để hạn chế JIT loại bỏ toàn bộ allocation như dead code.
5. Stop/dump ra file `heap-allocations.jfr`.
6. Đọc file tuần tự qua `RecordingFile`, kiểm tra event, size dương, tlabSize dương và stack có method `allocateSmall`/`allocateLarge`.
7. **Không in số event như một con số bất biến** vì event count phụ thuộc JVM/GC/TLAB.

Đây là demo cho **HotSpot JFR events có từ Java 11**; nếu JVM/vendor không hỗ trợ các event này, code báo lỗi cụ thể. Trên hệ thống có GC hoặc heap configuration khác, có thể cần điều chỉnh workload cho đủ mẫu.

Tạo file **`HeapAllocationProfileDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import jdk.jfr.EventType;
import jdk.jfr.FlightRecorder;
import jdk.jfr.Recording;
import jdk.jfr.ValueDescriptor;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordingFile;

public class HeapAllocationProfileDemo {
    private static volatile Object escape;
    private static final String IN_TLAB =
            "jdk.ObjectAllocationInNewTLAB";
    private static final String OUT_TLAB =
            "jdk.ObjectAllocationOutsideTLAB";

    private static void allocateSmall() {
        for (int i = 0; i < 40_000; i++) {
            byte[] array = new byte[1024];
            array[0] = (byte) i;
            escape = array;
        }
    }

    private static void allocateLarge() {
        for (int i = 0; i < 128; i++) {
            byte[] array = new byte[512 * 1024];
            array[0] = (byte) i;
            escape = array;
        }
    }

    private static boolean hasField(EventType type, String name) {
        for (ValueDescriptor field : type.getFields()) {
            if (field.getName().equals(name)) return true;
        }
        return false;
    }

    private static boolean hasDemoAllocationFrame(
            RecordedStackTrace stack) {
        if (stack == null) return false;
        for (RecordedFrame frame : stack.getFrames()) {
            if (frame.getMethod() != null
                    && frame.getMethod().getType() != null
                    && frame.getMethod().getType().getName()
                            .equals(HeapAllocationProfileDemo.class.getName())
                    && (frame.getMethod().getName().equals("allocateSmall")
                    || frame.getMethod().getName().equals("allocateLarge"))) {
                return true;
            }
        }
        return false;
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass output directory");
        }

        Path dir = Path.of(args[0]);
        Files.createDirectories(dir);
        Path target = dir.resolve("heap-allocations.jfr");

        List<EventType> allTypes =
                FlightRecorder.getFlightRecorder().getEventTypes();
        EventType inType = allTypes.stream()
                .filter(e -> e.getName().equals(IN_TLAB))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "Missing InNewTLAB event"));
        EventType outType = allTypes.stream()
                .filter(e -> e.getName().equals(OUT_TLAB))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "Missing OutsideTLAB event"));

        boolean schema =
                hasField(inType, "objectClass")
                && hasField(inType, "allocationSize")
                && hasField(inType, "tlabSize")
                && hasField(outType, "objectClass")
                && hasField(outType, "allocationSize");

        require(schema, "Allocation event fields not available");
        System.out.println("JFR allocation schema = true");

        try (Recording recording = new Recording()) {
            recording.setToDisk(true);
            recording.enable(IN_TLAB).withStackTrace();
            recording.enable(OUT_TLAB).withStackTrace();

            recording.start();
            allocateSmall();
            allocateLarge();
            recording.stop();
            recording.dump(target);
        }

        long inCount = 0;
        long outCount = 0;
        long withStack = 0;
        long demoStacks = 0;
        boolean inTlabSizePositive = false;
        boolean sizePositive = true;

        try (RecordingFile file = new RecordingFile(target)) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();
                String type = event.getEventType().getName();
                if (!type.equals(IN_TLAB) && !type.equals(OUT_TLAB)) {
                    continue;
                }

                if (type.equals(IN_TLAB)) {
                    inCount++;
                    inTlabSizePositive |=
                            event.getLong("tlabSize") > 0;
                } else {
                    outCount++;
                }

                sizePositive &=
                        event.getLong("allocationSize") > 0;
                RecordedStackTrace stack = event.getStackTrace();

                if (stack != null && !stack.getFrames().isEmpty()) {
                    withStack++;
                }
                if (hasDemoAllocationFrame(stack)) {
                    demoStacks++;
                }
            }
        }

        require(Files.size(target) > 0,
                "Recording not saved");
        require(inCount > 0 && outCount > 0,
                "Expected both allocation event types");
        require(withStack > 0 && demoStacks > 0,
                "Allocation stack missing");
        require(sizePositive && inTlabSizePositive,
                "Invalid event sizes");

        System.out.println("recording saved = true");
        System.out.println("in-TLAB events present = " + (inCount > 0));
        System.out.println("outside-TLAB events present = " + (outCount > 0));
        System.out.println("allocation sizes positive = " + sizePositive);
        System.out.println("new TLAB sizes positive = "
                + inTlabSizePositive);
        System.out.println("allocation stack present = " + (withStack > 0));
        System.out.println("demo stack frame present = " + (demoStacks > 0));
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Chạy trên JDK 11+ trong thư mục test có quyền ghi:

```bash
javac --release 11 HeapAllocationProfileDemo.java
java HeapAllocationProfileDemo .
```

Dấu `.` truyền thư mục đầu ra, chương trình sẽ tạo `heap-allocations.jfr` ở đó. **Đầu ra đã kiểm chứng khi biên dịch `--release 11` và chạy với HotSpot JDK 21:**

```text
JFR allocation schema = true
recording saved = true
in-TLAB events present = true
outside-TLAB events present = true
allocation sizes positive = true
new TLAB sizes positive = true
allocation stack present = true
demo stack frame present = true
ALL CHECKS PASSED
```

Trong lần thử, file chứa cả event `InNewTLAB` và `OutsideTLAB`, và stack có frame từ chương trình. **Output chỉ báo true/false** thay vì đóng đinh số lượng event vào assertion của demo.

### 9.1. Tại sao dùng volatile escape?

`escape` là một field `static volatile Object`. Việc gán mỗi mảng mới vào field này làm allocation có tác động quan sát được và hạn chế JIT loại bỏ hoàn toàn mảng.

Đây **không phải** bằng chứng mọi mảng còn sống: những array cũ không còn được tham chiếu qua `escape` có thể bị GC thu hồi. Cũng không biến profiling thành phép đo exact bytes.

### 9.2. Đọc và kiểm tra file bằng jfr

Sau khi chạy:

```bash
jfr summary heap-allocations.jfr
jfr print --events jdk.ObjectAllocationInNewTLAB heap-allocations.jfr
jfr print --events jdk.ObjectAllocationOutsideTLAB heap-allocations.jfr
```

`jfr summary` cho biết event types/count; `jfr print` giúp xem fields và stack. Với file lớn, không in toàn bộ event ra terminal production; dùng JDK Mission Control hoặc chương trình tổng hợp streaming.

**Ví dụ quan sát một lần chạy JDK 21:** có 157 InNewTLAB events và 129 OutsideTLAB events. Các con số này **không cố định**, cũng **không phải** count tất cả objects. Trên môi trường khác, heap/TLAB sizing và số lần GC sẽ ảnh hưởng tới số sự kiện.

### 9.3. Giới hạn thực nghiệm

- Chương trình kiểm thử **có event** và size/stack hợp lệ, không đo exact object bytes toàn heap.
- Nó không xác minh mọi phép `new` đều có event.
- Nó không đo retained heap, lifetime hay leak.
- Nó không so sánh overhead dưới tải production.
- Stack traces có thể khác khi JIT/GC/JDK thay đổi.
- Nếu một provider không có những event đã nêu, chương trình dừng với thông báo thiếu event/schema thay vì hiển thị số liệu sai.

## 10. Phân tích hot spot theo stack, class và thread

Một số hướng nhóm dữ liệu:

1. **Theo class** để tìm object family tạo áp lực.
2. **Theo full stack** để thấy đường nghiệp vụ dẫn đến nơi tạo object.
3. **Theo top frame** khi chỉ cần vị trí gần allocation, nhưng vẫn phải xem caller.
4. **Theo thread** để phân biệt request threads, background jobs, GC helpers.
5. **Theo thời gian** để xác định allocation bursts.
6. **Theo cấu hình/môi trường** để kiểm chứng before/after tối ưu.

Những helper như `Arrays.copyOf`, `StringBuilder` hoặc serializer có thể xuất hiện trong nhiều call chains. Nếu top frame của một allocation sample là thư viện, **nguyên nhân nghiệp vụ** có thể nằm ở caller cấp trên đã gọi thư viện quá thường xuyên.

**Đối với InNewTLAB, không coi ranking của `sum(tlabSize)` theo stack là exact allocation-by-site.** Nó chỉ là một cách nhìn sampling cần đối chứng. Với runtime hỗ trợ weighted sample, có thể kiểm tra tổng `weight` và độ ổn định khi lặp lại nhiều lần.

### 10.1. Quy trình so sánh before/after

- Warm up JVM tương đương, giữ cùng input và request volume.
- Giữ cùng JDK vendor/version, GC, heap size, stackdepth và JFR settings khi có thể.
- Ghi tối thiểu vài runs để nhận diện biến động ngẫu nhiên.
- So sánh **bytes allocated/thread**, GC behavior và application latency.
- Đối chiếu stack/class hotspots; tránh kết luận từ một event hiếm.
- Báo cáo xu hướng và giới hạn sai số, thay vì gán độ chính xác giả tạo.

## 11. Kiểm tra khả năng runtime và cấu hình an toàn

Java 11 cho phép xem event types hiện hữu:

```java
for (EventType type :
        FlightRecorder.getFlightRecorder().getEventTypes()) {
    if (type.getName().contains("ObjectAllocation")) {
        System.out.println(type.getName());
    }
}
```

Đây là mảnh code cần import `EventType` và `FlightRecorder`; nó in các tên event mà JVM thực có, không đảm bảo một danh sách giống nhau ở mọi JDK.

Một đoạn cấu hình đơn giản:

```java
try (Recording r = new Recording()) {
    r.setToDisk(true);
    r.enable("jdk.ObjectAllocationInNewTLAB").withStackTrace();
    r.enable("jdk.ObjectAllocationOutsideTLAB").withStackTrace();

    r.start();
    // Chạy workload cần quan sát.
    r.stop();
    r.dump(Path.of("allocations.jfr"));
}
```

Đây là **mảnh code**, chưa có method main và cần import `jdk.jfr.Recording`, `java.nio.file.Path` cùng xử lý exception.

**Trên production:** không bật mọi allocation event với stack traces vô thời hạn. Recording tần suất cao có thể gây overhead, file lớn hoặc chứa thông tin nhạy cảm. Ưu tiên cấu hình mặc định đã được kiểm chứng, chỉ bật profiling chi tiết trong cửa sổ ngắn khi cần, và đo tác động thực tế.

Với `-XX:StartFlightRecording` hoặc `jcmd JFR.start`, event settings cụ thể cần đưa qua `.jfc` hoặc một công cụ cấu hình tương thích. Không tự suy ra rằng chỉ cần `settings=profile` sẽ bật đúng cả hai event TLAB trên mọi JDK; template đã thay đổi theo phiên bản.

## 12. Bảo mật và vận hành file JFR

JFR có thể chứa tên class/method, thread name, stack traces, đường dẫn, metadata JVM hoặc thông tin trong custom events. Vì vậy:

- Lưu file `.jfr` ở thư mục hạn chế quyền đọc/ghi.
- Không ghi credential, token hay dữ liệu cá nhân vào custom event fields.
- Thiết lập retention và xóa/rotate file đã xuất; `setMaxAge` của repository không dọn tất cả file dump.
- Không mở stackdepth tối đa khi chưa đo chi phí.
- Tránh tải toàn bộ file lớn bằng `RecordingFile.readAllEvents`; dùng streaming.
- Kiểm tra file có đủ khoảng thời gian trước/sau incident.
- Nếu muốn điều tra leak, cân nhắc `OldObjectSample`, GC roots hoặc heap dump với quy trình có kiểm soát; thu GC root path có thể tốn tài nguyên.
- Khi chia sẻ dữ liệu profiler, ghi kèm JDK version, settings, workload và số liệu kiểm chứng.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Không có InNewTLAB event | Chưa enable, workload ít refill hoặc runtime khác | Kiểm tra event metadata, workload và recording lifecycle |
| Không có OutsideTLAB event | Object không đi ngoài TLAB hoặc event chưa bật | Dùng workload phù hợp, kiểm tra JVM/GC |
| `ObjectAllocationSample` không tồn tại trên Java 11 | Chỉ được giới thiệu từ JDK 16 | Dùng event Java 11 và ghi rõ giới hạn |
| `getLong("tlabSize")` thất bại | OutsideTLAB không có trường này | Kiểm tra event name/`hasField` |
| `allocationSize != array.length` | Header, alignment, object layout | Phân biệt payload size và heap allocation size |
| `tlabSize` rất lớn so với `allocationSize` | TLAB là buffer, không phải object | Không gán toàn bộ TLAB cho stack này |
| Event count thấp dù có nhiều `new` | Sampling theo TLAB refill, JIT | Không dùng count làm tổng số object |
| Stack trace null | Stack bị tắt hoặc không được ghi | Bật `withStackTrace()`, kiểm tra config |
| Không thấy business caller | Stack truncate, runtime/inlining/helper | Kiểm tra `isTruncated()` và call chain |
| File lớn, ứng dụng chậm | Thu quá nhiều event/stack | Giới hạn cửa sổ profiling và event types |
| Heap tăng mà allocation sample ít | Retained objects/leak không trùng allocation hot spots | Dùng heap dump/OldObjectSample |
| Heap nhỏ nhưng allocation nhiều | Objects được GC thu hồi nhanh | Đánh giá allocation rate và GC overhead |
| Kết quả khác giữa hai JVM | JIT, GC, TLAB sizing, settings, workload khác | Chuẩn hóa môi trường, đo nhiều lần |
| Đọc file hết RAM | Nạp tất cả RecordedEvents vào List | Dùng `RecordingFile` theo streaming |
| Kết luận exact allocation theo stack từ sum(tlabSize) | Attribution bias của TLAB event | Đối chiếu thống kê thread/GC và sampling khác |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `ObjectAllocationInNewTLAB` có một event cho mọi object Java không?  
**Trả lời:** Không. Nó chỉ ghi các điểm cấp phát liên quan tới TLAB mới; nhiều object khác trong TLAB không sinh event riêng.

**Câu 2.** `allocationSize` khác `tlabSize` thế nào?  
**Trả lời:** `allocationSize` là kích thước object gắn với event; `tlabSize` là kích thước TLAB mới, không phải object size.

**Câu 3.** Vì sao `byte[1024]` có thể tốn nhiều hơn 1.024 byte trên heap?  
**Trả lời:** Array object có header, length, alignment/padding và cấu trúc JVM phụ thuộc môi trường.

**Câu 4.** Có thể dùng số InNewTLAB events để đếm chính xác số objects được tạo không?  
**Trả lời:** Không. TLAB events không ghi mọi allocation, còn JIT có thể tối ưu một số allocations.

**Câu 5.** `getStackTrace() == null` có chứng minh object không có call site không?  
**Trả lời:** Không. Stack có thể chưa được ghi hoặc bị vô hiệu hóa.

**Câu 6.** Vì sao stack của event gây TLAB refill không phải stack của mọi byte trong TLAB đó?  
**Trả lời:** TLAB được nhiều lần cấp phát sau đó sử dụng, có thể từ những method khác.

**Câu 7.** `jdk.ObjectAllocationSample` có trên Java 11 không?  
**Trả lời:** Không; event được thêm từ JDK 16.

**Câu 8.** `weight` của ObjectAllocationSample có phải object size chính xác không?  
**Trả lời:** Không, đó là trọng số thống kê dùng cho ước lượng allocation pressure.

**Câu 9.** Allocation rate cao có nhất thiết là memory leak không?  
**Trả lời:** Không. Objects tạm có thể được GC thu hồi nhanh; leak liên quan object sống không cần thiết và retained references.

**Câu 10.** Khi nào dùng `OldObjectSample` và heap dump?  
**Trả lời:** Khi cần xác định object sống lâu, reference chains và retained heap, không chỉ nơi object được cấp phát.

**Câu 11.** Muốn phân tích stack của file JFR bằng Java 11, dùng API nào?  
**Trả lời:** `RecordingFile`, `RecordedEvent.getStackTrace()`, `RecordedStackTrace.getFrames()` và `isTruncated()`.

**Câu 12.** Cách báo cáo hiệu quả tối ưu allocation đáng tin là gì?  
**Trả lời:** Giữ workload và JDK settings gần tương đương, đo nhiều lần, tổng hợp stack/class, đối chiếu bytes allocated/thread, GC và latency; công bố giới hạn sai số.

## 15. Tổng kết

```text
Java 11 heap allocation profiling qua JFR
  |
  +-- jdk.ObjectAllocationInNewTLAB
  |     allocationSize = size object kích hoạt event
  |     tlabSize = size TLAB mới, KHÔNG phải object
  |     stackTrace = stack gắn với event refill
  |
  +-- jdk.ObjectAllocationOutsideTLAB
  |     allocationSize = size object ngoài TLAB
  |     KHÔNG có tlabSize
  |
  +-- JDK 16+ (nếu runtime hỗ trợ)
  |     jdk.ObjectAllocationSample
  |     weight = trọng số thống kê, KHÔNG là object size
  |
  +-- Phân tích
        class + stack + thread + time
        đối chiếu GC, heap metrics, workload
        leak/retained graph cần công cụ riêng
```

**Ghi nhớ:** Stack cấp phát chỉ chỉ ra những điểm JVM **thực sự ghi sự kiện**; `allocationSize` không bằng payload array length, `tlabSize` không bằng object size, và event count không bằng object count. Muốn kết luận có trách nhiệm, phải đặt các con số trong **ngữ cảnh sampling, JIT, TLAB và recording window**.

Tất cả API Java 11 chính của bài vẫn còn hữu ích hiện nay; khi sử dụng JDK mới, kiểm tra event set thực tế và lựa chọn cơ chế allocation sampling phù hợp.

### Tài liệu chính thức

- [Oracle Java 11 — Troubleshoot Memory Leaks, TLAB allocations và OldObjectSample](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshooting-memory-leaks.html)
- [Oracle Java 11 — JFR Recording API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle Java 11 — FlightRecorder API](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/FlightRecorder.html)
- [Oracle Java 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html)
- [Oracle Java 11 — RecordedObject.getLong/getClass/hasField](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html)
- [Oracle Java 11 — RecordedStackTrace.getFrames/isTruncated](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedStackTrace.html)
- [Oracle Java 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Oracle JDK 16 release notes — ObjectAllocationSample ra mắt](https://www.oracle.com/java/technologies/javase/16all-relnotes.html)
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328)
- [OpenJDK JFR metadata — kiểm tra đúng event/field trên runtime](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/jfr/metadata/metadata.xml)
- [Dev.java — Configure Flight Recorder và stackdepth](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/)
