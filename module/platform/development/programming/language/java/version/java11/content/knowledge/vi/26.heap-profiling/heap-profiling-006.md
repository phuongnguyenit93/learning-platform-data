# Theo dõi đối tượng sống và đã chết bằng heap profiling trong Java 11+

## 1. Phân biệt đối tượng sống, đã mất khả năng truy cập và đã được GC thu hồi

**Heap profiling** giúp tìm hiểu Java heap có gì, những đối tượng nào còn tồn tại và vì sao bộ nhớ tăng. Muốn giải thích chính xác chủ đề **“Theo dõi đối tượng sống và đã chết”**, trước tiên phải phân biệt các trạng thái khác nhau. Java quản lý bộ nhớ tự động bằng **garbage collector (GC)**, chứ không xóa object ngay khi một dòng code hết scope.

| Trạng thái / thuật ngữ | Nghĩa | Có thể suy ra điều gì? |
| --- | --- | --- |
| **Allocated** | Đối tượng/mảng đã được cấp phát trên heap | Tồn tại tại thời điểm cấp phát; không chứng minh còn sống về sau |
| **Strongly reachable** | Có đường tham chiếu mạnh từ một **GC root** tới object | GC thường không thu hồi object đó trong lúc còn reachable |
| **Eligible for GC / unreachable** | Không còn đường tham chiếu giữ object sống theo quy tắc reachability | Đủ điều kiện để GC thu hồi, **chưa chắc đã thu hồi** |
| **Reclaimed** | GC đã xử lý object và vùng bộ nhớ liên quan có thể được sử dụng lại | Không có nghĩa JFR phát sự kiện “Object X died” |
| **Live after GC** | Đối tượng vẫn tồn tại sau một lần GC ở điểm đo phù hợp | Không mặc nhiên là leak; có thể là trạng thái hợp lệ |
| **Long-lived / retained** | Object được giữ lâu, có thể do collection, thread, static field hay cache | Là đối tượng đáng kiểm tra, nhưng “sống lâu” không đồng nghĩa “rò rỉ” |

Ví dụ minh họa:

```java
byte[] data = new byte[4096]; // Đối tượng được cấp phát.
cache.put("request-42", data); // Cache giữ tham chiếu mạnh.
data = null;                  // VẪN có thể sống trong cache.
cache.remove("request-42");   // Có thể trở thành ứng viên GC.
```

Đây là **đoạn minh họa không độc lập**, cần biến `cache` đã được định nghĩa. Sau `data=null`, object vẫn có thể tồn tại vì `cache` giữ nó. Sau `remove`, object có thể vẫn có references khác hoặc GC chưa chạy. Không được diễn giải câu lệnh gán `null` như một dấu thời gian đối tượng đã chết hoặc bộ nhớ đã được trả lại.

**Kết luận quan trọng:** “Dead” có thể có nghĩa *không còn reachable* hoặc *đã được thu hồi*. Đây là **hai mốc khác nhau**, và trình phân tích heap không được trộn chúng làm một. Đối tượng có thể trở nên unreachable rất nhanh nhưng chưa bị GC thu hồi ngay.

## 2. Reachability và GC roots: vì sao object còn sống?

Một object được giữ sống bởi **đường tham chiếu** xuất phát từ một **GC root**. Những root thông dụng có thể gồm stack locals có hiệu lực, static fields reachable, thread và các handle/runtime references JVM quản lý. Một object lớn có thể không còn được biến local trực tiếp trỏ tới nhưng vẫn được giữ bởi cấu trúc dữ liệu ở nơi khác.

```text
GC ROOT
  |
  +-- Static Application.sessions
          |
          +-- ConcurrentHashMap
                 |
                 +-- Session("s-123")
                       |
                       +-- List<RequestContext>
                               |
                               +-- byte[large]
```

Mảng có thể vẫn sống dù request tạo ra nó đã kết thúc. Muốn sửa leak, phải tìm **owner** và thời điểm phải xóa reference, không chỉ cố tăng tần suất chạy GC.

Lưu ý rằng Java compiler/JIT có thể rút ngắn hoặc thay đổi khoảng sống thực tế của local references; phạm vi dấu ngoặc trong source không phải chứng cứ tuyệt đối object còn reachable tại mọi nanosecond. Một object có thể được giữ hợp lệ bởi cache TTL, pool hoặc session còn hoạt động. Vì vậy, **cần hiểu nghiệp vụ trước khi kết luận một long-lived object là leak**.

### Strong, weak và phantom references

- **Strong reference** thông thường có thể giữ referent sống nếu nó nằm trên đường đi từ root.
- **`WeakReference<T>`** không tự giữ referent sống. Sau khi GC xác định referent chỉ còn weakly reachable, weak reference có thể bị clear; `ref.get()==null` không cho bạn thời điểm chính xác vùng heap đã được tái sử dụng.
- **`ReferenceQueue`** dùng để nhận tín hiệu khi các Reference được enqueue theo chính sách GC. Nó không phải event stream ghi lại cái chết của mọi object.
- **`PhantomReference`** có ứng dụng trong quản lý cleanup phù hợp, nhưng cũng không là cơ chế đếm mọi object death.

**Không dùng `finalize()` làm bộ đếm cái chết của object**: finalization không có timing tin cậy, hiện là hướng cần tránh trên Java hiện đại. Các resource cần đóng phải được giải phóng bằng lifecycle tường minh (`try-with-resources`, `AutoCloseable`, cơ chế quản lý phù hợp), không chờ GC.

## 3. Java Flight Recorder theo dõi được những gì?

**Java Flight Recorder (JFR)** là hệ thống ghi sự kiện hiệu năng và chẩn đoán tích hợp trong JDK; OpenJDK Java 11 có tính năng chính thức qua **JEP 328**. Khi **heap profiling**, JFR cung cấp **allocation-related samples**, **old object samples** và **GC/heap events**. Nó **không bảo đảm theo dõi mọi đối tượng từ lúc sinh tới đúng thời điểm chết**.

| Event / nguồn | Đo gì? | Hạn chế |
| --- | --- | --- |
| `jdk.ObjectAllocationInNewTLAB` | Thông tin allocation khi sử dụng TLAB mới; class/kích thước/stack khi bật | Không ghi mỗi object; là các allocation-related observations |
| `jdk.ObjectAllocationOutsideTLAB` | Một số allocation không thực hiện qua TLAB | Không phản ánh trực tiếp object sống/chết |
| `jdk.OldObjectSample` | **Mẫu những object tồn tại lâu**; có thể có thời điểm cấp phát, độ tuổi, root path | Không liệt kê tất cả live objects, không chứng minh mọi sample là leak |
| `jdk.GarbageCollection` | Một lần GC và thời gian/metadata liên quan | Không là danh sách object được thu hồi |
| `jdk.GCHeapSummary` | Các số đo heap gần GC, giúp phân tích xu hướng | Không có object identity/path đến từng object |
| `jdk.ObjectCount` / `jdk.ObjectCountAfterGC` | Thống kê số lượng/kích thước theo class tại thời điểm phù hợp, khi được bật và hỗ trợ | Tốn chi phí hơn; không phải “death ledger” |
| Custom `jdk.jfr.Event` | Sự kiện nghiệp vụ do ứng dụng phát, ví dụ mốc giữ/nhả cache | Chỉ là số do ứng dụng tự ghi, không thay GC reachability |

**JFR không cung cấp một danh sách “mỗi object đã chết lúc 10:25:30.123” trong recording thông thường.** Không có cam kết mỗi `new` phát một event, hoặc sau GC có `ObjectDeath` cho từng đối tượng bị thu hồi. Sự kiện JFR có thể bị sampling, filtering, threshold và retention ảnh hưởng; lấy mẫu nhiều không tạo thành toàn bộ lịch sử heap.

### Cẩn thận về JDK version

Với Java 11, nên học các event `jdk.ObjectAllocationInNewTLAB` và `jdk.ObjectAllocationOutsideTLAB`. Các JDK mới (như 16+) có thêm `jdk.ObjectAllocationSample` cho cơ chế sampling khác; **không nên sao chép cấu hình `jdk.ObjectAllocationSample` rồi khẳng định nó luôn có trên Java 11**. Tên event, cấu hình mặc định và metadata có thể khác theo bản JDK/GC/provider: xem những gì JVM thực sự hỗ trợ bằng `jfr metadata` hoặc `RecordingFile.readEventTypes()`.

## 4. Allocation rate khác live set

Có hai chỉ số thường bị nhầm:

- **Allocation rate:** bao nhiêu dữ liệu được cấp phát mỗi giây và ở đâu. Nhiều object tạm khiến allocation rate cao, gây áp lực lên GC, nhưng có thể không tạo leak.
- **Live set sau GC:** lượng đối tượng còn được giữ sau một điểm GC phù hợp. Nếu live set **tăng dần qua các GC tương đương** trong workload đã kiểm soát, đó là tín hiệu memory retention/leak đáng điều tra.

```text
Heap used
  ^
  |  /\\       /\\         /\\          /\\
  | /  \\     /  \\       /  \\        /  \\
  |/    \\___/    \\_____/    \\______/    \\__
  +------------------------------------------> time
            các lần GC tạo dạng răng cưa
```

Sơ đồ chỉ để hiểu hiện tượng, không phải đồ thị từ một recording thật. Heap used tăng giữa hai lần GC là **bình thường**. Đáng quan tâm hơn là đường “đáy sau GC” liên tục tăng trong nhiều chu kỳ có tính chất tương đương, không giảm về ngưỡng hợp lý khi tải trở lại bình thường.

Ví dụ:

- Một API tạo 20 MB object tạm mỗi request, nhưng chúng trở nên unreachable ngay sau request. Allocation cao, **live set có thể ổn định**.
- Một map static thêm 1 MB mỗi phút nhưng không xóa entry. Allocation không quá cao, nhưng **live set có thể tăng liên tục**.
- Cache có giới hạn 256 MB tăng trong giai đoạn warm-up rồi ổn định. Nó giữ object sống lâu nhưng **không nhất thiết bị leak**.

Dùng `Runtime.totalMemory()-Runtime.freeMemory()` để xem heap used chỉ là một **snapshot thô** có thể bị GC timing ảnh hưởng. Không kết luận object đã chết hay bộ nhớ đã được reclaim chỉ vì số đo giảm một lần.

## 5. `jdk.OldObjectSample`: tìm những object sống lâu

`jdk.OldObjectSample` là một sự kiện quan trọng để phân tích **potential memory leaks**. Nó cho biết thông tin về **một mẫu đối tượng còn tồn tại lâu**, đôi khi gồm chuỗi tham chiếu tới GC root.

Trong một recording có cấu hình phù hợp, các field thường được mô tả là:

| Field | Ý nghĩa |
| --- | --- |
| `allocationTime` | Thời điểm mẫu được cấp phát; giúp phân biệt object sinh khi khởi động với object gần thời điểm dump |
| `objectAge` | Tuổi của object tại thời điểm lấy mẫu |
| `lastKnownHeapUsage` | Bối cảnh heap usage được JFR ghi nhận gần lần quan sát; **không phải retained size của chính object** |
| `object` | Mô tả sample, class và một phần reference structure khi có dữ liệu |
| `root` | Thông tin GC root liên quan nếu thu được |
| `eventThread` | Thread liên quan tới allocation được ghi trong sample |
| `stackTrace` | Allocation stack trace khi bật và có dữ liệu |

**Không khẳng định mọi recording đều có đủ các field/value này**, và không dùng tên field thuộc JDK mới mà chưa xác minh JFR metadata của file Java 11. Nếu không có `OldObjectSample` trong file, đó có thể chỉ là do sampling/thiết lập/recording quá ngắn hoặc chưa bật đường về roots.

### Minh họa một leak candidate

```text
OldObjectSample
  object: java.util.HashMap$Node
  allocationTime: trước đây ~90 giây
  objectAge: ~90 giây
  root: Thread -> Application.sessions -> HashMap -> Node
```

Đây **không phải stdout cố định**. Nếu ứng dụng có nhiều session đã logout mà `Application.sessions` vẫn giữ reference, root path gợi ý nơi cần kiểm tra `remove` hoặc chính sách TTL. Nhưng nếu tất cả session đều còn hợp lệ thì object sống lâu chưa phải bug.

**Live sample không tự động là leak.** Cần hỏi: Ai đang giữ nó? Có còn hợp lệ về nghiệp vụ? Bao nhiêu object tương tự? Có tăng qua nhiều GC? Có tham chiếu trùng/không xóa không?

## 6. Thu đường về GC root: lợi ích và overhead

Trong HotSpot/JFR, khi cần tìm **đường tham chiếu giữ đối tượng sống**, có thể yêu cầu lúc dump:

```bash
jcmd <PID> JFR.dump name=HeapDiag filename=heap-investigation.jfr path-to-gc-roots=true
```

Đây là **mẫu lệnh**, thay `<PID>` bằng process ID thật và đảm bảo recording `HeapDiag` đã chạy. `path-to-gc-roots=true` giúp ghi đường tham chiếu từ root tới những old-object samples đủ điều kiện.

**Chi phí:** Tìm đường về GC root có thể gây pause/CPU overhead tương đối lớn, được Oracle mô tả là có thể tương tự thao tác GC đáng kể. Chỉ bật khi đang điều tra memory leak, trong cửa sổ vận hành có kiểm soát. Không để mọi lần dump tự động đều yêu cầu GC roots nếu chưa đánh giá ảnh hưởng production.

**Phân biệt:** Một allocation stack trace chỉ chỉ ra **ở đâu object được tạo**, còn path to GC root chỉ ra **ai đang giữ object**. Một object có thể được tạo ở thư viện chung nhưng bị giữ bởi static map ở module khác. Muốn sửa leak, thông tin “ai giữ” có thể quan trọng hơn thông tin “ai tạo”.

Ngoài ra, đừng suy diễn rằng một sample không có root path đồng nghĩa đã chết; có thể đơn giản đường chưa được thu, không tìm được trong budget hoặc schema của file không chứa thông tin đó.

## 7. Chênh lệch số object sau hai lần GC không phải số object chết

Giả sử thống kê theo class:

```text
Sau GC tại t1: com.example.Session = 1000 instances
Sau GC tại t2: com.example.Session = 1200 instances
Chênh lệch ròng: +200
```

Con số `+200` **không có nghĩa** đúng 200 object mới đã được tạo và tất cả object cũ vẫn sống. Trong khoảng đó có thể tạo 10.000 session và GC thu 9.800. Nếu số lượng giảm `-300`, cũng không suy ra chính xác chỉ có 300 object đã “chết”.

Tương tự, `jdk.ObjectCountAfterGC` nếu được bật/hỗ trợ cung cấp **thống kê một thời điểm**, không phải danh sách định danh của từng object được thu hồi. Những event class-count/heap statistics có thể tốn chi phí; chỉ bật khi cần và đã đo ảnh hưởng.

**Sự vắng mặt của một `OldObjectSample` cũng không chứng minh một object đã chết**: nó có thể không trúng mẫu, đã bị loại do retention, record chưa được bật hoặc không được dump đúng lúc.

## 8. Ví dụ hoàn chỉnh Java 11: đánh dấu object được giữ và tham chiếu được nhả

Ví dụ này dùng **custom JFR events** để ghi hai thời điểm ứng dụng **còn giữ bao nhiêu payload**. Nó cố ý **không giả làm công cụ kiểm kê GC** và không dùng `System.gc()` làm phép thử đáng tin.

Kịch bản:

1. Tạo bốn đối tượng `Payload`, mỗi object có mảng byte 64 KiB.
2. Giữ cả bốn trong `List<Payload>`; ghi custom event `held`.
3. Gỡ hai object khỏi list và tạo `WeakReference` để có thể quan sát mà không giữ object sống bằng strong reference.
4. Ghi custom event `released`; ứng dụng biết còn giữ **hai references trong list**, nhưng không biết hai object kia đã được GC thu hồi chưa.
5. Đọc file `.jfr` bằng `RecordingFile` và in dữ liệu custom events ở hai checkpoint.

Lưu file **`JfrReachabilityDemo.java`**:

```java
import java.lang.ref.WeakReference;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrReachabilityDemo {
    private static final int PAYLOAD_BYTES = 64 * 1024;

    static final class Payload {
        final byte[] data = new byte[PAYLOAD_BYTES];
    }

    @Name("demo.RetentionCheckpoint")
    static class RetentionCheckpoint extends Event {
        String phase;
        int strongReferences;
        long applicationPayloadBytes;
        int referencesReleased;
    }

    private static void checkpoint(
            String phase, List<Payload> retained, int released) {
        RetentionCheckpoint event = new RetentionCheckpoint();
        event.phase = phase;
        event.strongReferences = retained.size();
        event.applicationPayloadBytes =
                (long) retained.size() * PAYLOAD_BYTES;
        event.referencesReleased = released;
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("jfr-retain-");
        Path output = dir.resolve("reachability.jfr");
        try {
            List<Payload> retained = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                retained.add(new Payload());
            }
            List<WeakReference<Payload>> observations = new ArrayList<>();

            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(RetentionCheckpoint.class)
                        .withThreshold(Duration.ZERO);
                recording.enable("jdk.GarbageCollection")
                        .withThreshold(Duration.ZERO);
                recording.start();
                checkpoint("held", retained, observations.size());

                for (int i = 0; i < 2; i++) {
                    Payload item = retained.remove(retained.size() - 1);
                    observations.add(new WeakReference<>(item));
                }
                checkpoint("released", retained, observations.size());

                // Không gọi System.gc(): GC chạy khi nào là tùy JVM.
                recording.stop();
                recording.dump(output);
            }

            Map<String, String> report = new TreeMap<>();
            try (RecordingFile file = new RecordingFile(output)) {
                while (file.hasMoreEvents()) {
                    RecordedEvent event = file.readEvent();
                    if (!event.getEventType().getName()
                            .equals("demo.RetentionCheckpoint")) {
                        continue;
                    }
                    report.put(event.getString("phase"),
                            event.getInt("strongReferences") + ":" +
                            event.getLong("applicationPayloadBytes") + ":" +
                            event.getInt("referencesReleased"));
                }
            }

            System.out.println("checkpointEvents=" + report.size());
            for (Map.Entry<String, String> entry : report.entrySet()) {
                System.out.println(entry.getKey() + "=" + entry.getValue());
            }
            System.out.println("weakObservers=" + observations.size());
            System.out.println("outputFileExists=" +
                    Files.isRegularFile(output));
        } finally {
            Files.deleteIfExists(output);
            Files.deleteIfExists(dir);
        }
    }
}
```

**Biên dịch và chạy** trên JDK 11 trở lên (module `jdk.jfr` có sẵn và có quyền ghi thư mục tạm):

```bash
javac --release 11 JfrReachabilityDemo.java
java JfrReachabilityDemo
```

**Stdout chính xác** trên OpenJDK có JFR hoạt động:

```text
checkpointEvents=2
held=4:262144:0
released=2:131072:2
weakObservers=2
outputFileExists=true
```

Đã kiểm thử bằng **`javac --release 11` và Java/OpenJDK 24**, kết quả đúng năm dòng như trên. Không có kết quả nào phụ thuộc tên file tạm hoặc thời điểm GC.

### Cách hiểu kết quả đúng

- **`checkpointEvents=2`**: hai custom events đã được ghi và đọc từ file. Không phải hai lần GC.
- **`held=4:262144:0`**: ứng dụng giữ bốn `Payload` trong list; tổng kích thước **mảng payload do ứng dụng tính** là 4 × 65.536 = 262.144 byte. Không phải tổng retained heap size thực tế (còn object headers, alignment, collection overhead...).
- **`released=2:131072:2`**: list còn giữ hai `Payload` và đã gỡ hai references trước đó; số byte là **payload của các phần tử còn trong list**, không phải số byte vừa được GC reclaim.
- **`weakObservers=2`**: còn hai weak reference wrappers; chúng không giữ referent sống như strong references. **Không suy ra** hai referents đã bị thu hồi.
- **`outputFileExists=true`**: JFR đã dump một file hợp lệ rồi được đọc. Chương trình xóa file trong `finally`.
- Chương trình bật thêm `jdk.GarbageCollection` nhưng **không assert event GC nào xuất hiện**, vì một ví dụ ngắn có thể không có GC trong cửa sổ recording.

**Lưu ý:** custom event `demo.RetentionCheckpoint` chỉ đánh dấu **quyết định giữ/nhả references của ứng dụng**. Muốn biết đối tượng sống thật sau GC, phải quan sát thêm các JFR GC/OldObjectSample events, heap statistics, hoặc heap dump. Không có lời khẳng định “GC đã giải phóng 131.072 byte” trong stdout.

### Vì sao không ép GC trong demo?

`System.gc()` là một lời **đề nghị**, không phải cam kết thời điểm GC xảy ra. Kể cả khi GC chạy, phép kiểm tra `weak.get()==null` có thể phụ thuộc collector, timing và những references khác. Các assertions dựa vào GC chính xác từng object dễ làm integration test thất thường; kiểm thử logic ứng dụng bằng dữ liệu nó quản lý, rồi phân tích GC với workload có kiểm soát.

## 9. Quy trình JFR thực tế để điều tra suspected leak

### Bước 1 — Chạy recording trong một khoảng có workload thật

Trên một JVM mà bạn có quyền chẩn đoán, với PID và file path hợp lệ:

```bash
jcmd <PID> JFR.start name=HeapDiag settings=profile disk=true maxage=20m maxsize=256m
jcmd <PID> JFR.check
```

Đây là **mẫu lệnh**, không chạy nguyên văn `<PID>`. `settings=profile` thu nhiều dữ liệu/stack hơn `default`, có thể làm tăng overhead; không bật profiling nặng vô hạn trên mọi JVM production. Với hệ thống nhạy cảm, bắt đầu từ `settings=default` rồi chỉ thêm event/stack-trace cần thiết.

### Bước 2 — Quan sát nhiều chu kỳ GC

Tái tạo tải làm bộ nhớ tăng (login/logout, cache warm-up, queue buildup...). Đọc GC timeline, heap usage và live-set trend; so sánh các điểm **sau GC tương đương**. Đừng chỉ so sánh hai lần `Runtime.freeMemory()` giữa các burst khác nhau.

### Bước 3 — Dump với GC roots khi cần

```bash
jcmd <PID> JFR.dump name=HeapDiag filename=heap-investigation.jfr path-to-gc-roots=true
```

**Cảnh báo:** Thu path-to-GC-roots có thể gây pause/CPU overhead đáng kể. Nếu không cần root paths, dump không bật tùy chọn này và bắt đầu với các thống kê nhẹ hơn. Không xem `path-to-gc-roots=true` là flag miễn phí.

### Bước 4 — Xem mẫu và bối cảnh bằng CLI/JMC

```bash
jfr summary heap-investigation.jfr
jfr print --events jdk.OldObjectSample heap-investigation.jfr
jfr print --events jdk.GCHeapSummary heap-investigation.jfr
```

**JDK Mission Control (JMC)** có các màn hình Memory/Live Objects/Memory Leak Detection để xem trends và tham chiếu. Nếu không có mẫu `OldObjectSample`, không kết luận “không leak” ngay; có thể thiếu điều kiện sampling/thời gian. Khi xem object mẫu, phân biệt **allocation stack trace** (nơi sinh) với **GC root path** (nơi giữ).

### Bước 5 — Sửa đúng owner của reference

Tìm collection, cache, listener, queue, `ThreadLocal`, future hoặc session giữ object không cần thiết. Thêm TTL, giới hạn dung lượng, hủy đăng ký listener, `ThreadLocal.remove()` hay cancel pending task theo vòng đời. Khi đã sửa, chạy lại trên workload tương đương, so sánh live set sau GC và hành vi retention; kết quả samples có thể biến động giữa các lượt.

### Bước 6 — Kết thúc chẩn đoán

```bash
jcmd <PID> JFR.stop name=HeapDiag
```

Bảo vệ và xóa file `.jfr` theo policy. File có thể chứa class names, stack traces, thread names và business identifiers. Không đăng nguyên file JFR hoặc heap dump lên nơi công khai chỉ để hỏi đáp.

## 10. Truy vấn `OldObjectSample` bằng Java 11

Với Java 11, dùng `jdk.jfr.consumer.RecordingFile` để đọc file `.jfr` hoàn tất. Đoạn sau **chỉ minh họa** (cần biến `path` kiểu `Path` và các import):

```java
try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if (!"jdk.OldObjectSample".equals(
                event.getEventType().getName())) {
            continue;
        }
        if (event.hasField("allocationTime")) {
            System.out.println("allocated=" +
                    event.getInstant("allocationTime"));
        }
        if (event.hasField("objectAge")) {
            System.out.println("age=" +
                    event.getDuration("objectAge"));
        }
        if (event.hasField("lastKnownHeapUsage")) {
            System.out.println("heapUsage=" +
                    event.getLong("lastKnownHeapUsage"));
        }
    }
}
```

**Kiểm tra schema:** `hasField` mới chỉ xét có field, không xét type/annotation. Với dữ liệu `.jfr` từ JDK khác, nên dùng `event.getEventType().getField(name)` và `ValueDescriptor.getTypeName()/getAnnotation(...)` để xác nhận tương thích trước khi dùng `getInstant`/`getDuration`. Một event type có mặt trong metadata **không bảo đảm** có bất kỳ event instance trong file.

JFR đọc dữ liệu **theo sample**; code trên không là một bộ quét mọi live objects. `RecordingFile` đọc file theo luồng, phù hợp hơn `readAllEvents` khi file lớn. Nó không phải API real-time streaming được bổ sung trong JDK mới hơn (ví dụ `RecordingStream` sau Java 11).

## 11. Khi cần chi tiết hơn: histogram và heap dump

**Histogram** cho biết số instance/bytes theo class tại một thời điểm. Trên HotSpot:

```bash
jcmd <PID> GC.class_histogram
```

Lệnh có thể gây GC/overhead tùy tùy chọn, JVM và lượng heap. Hai histogram chỉ cho thấy **chênh lệch count theo class**, không phải danh sách per-object birth/death.

**Heap dump** (thường là file `.hprof`):

```bash
jcmd <PID> GC.heap_dump heap.hprof
```

Heap dump cho công cụ như Eclipse Memory Analyzer phân tích object graph, paths to GC roots, dominator tree và retained size. Nó có thể **rất lớn, gây pause và chứa dữ liệu nhạy cảm** (token, mật khẩu, payload, user IDs), nên chỉ tạo khi được cấp quyền, đủ disk và có biện pháp bảo vệ/xóa.

Heap dump là **ảnh chụp tại một thời điểm**, không phải lịch sử đầy đủ. Nếu muốn xác định chính xác thời điểm object trở nên unreachable, snapshot cuối không thể hồi tưởng từng lần thay đổi references trước đó.

## 12. Các nguồn giữ object gây leak phổ biến

| Pattern | Đường giữ object thường thấy | Gợi ý sửa |
| --- | --- | --- |
| **Cache không giới hạn** | `static Map` hoặc singleton giữ value của request cũ | TTL, size bound, eviction, kiểm soát key cardinality |
| **Session registry** | Map lưu session đã logout nhưng không xóa | Cleanup ở logout/timeout, tests vòng đời |
| **Listener/callback** | Registry dài hạn giữ listener của component đã đóng | `removeListener`/unsubscribe theo lifecycle |
| **`ThreadLocal`** | Worker threads tái sử dụng giữ dữ liệu cũ | `remove()` trong `finally` theo mỗi task |
| **Queue không giới hạn** | Backlog giữ request/messages lớn | Bounded queue, backpressure, timeout, metrics |
| **Pending future/task** | Completion callback giữ closure và object graph | Cancel, timeout, dọn listener/callback |
| **ClassLoader retention** | Threads/caches giữ class loader từ bản deploy cũ | Dọn resource/threads và references khi undeploy |

Ví dụ minh họa một cache cần kiểm soát vòng đời:

```java
static final Map<String, byte[]> CACHE = new HashMap<>();

static void remember(String key, byte[] value) {
    CACHE.put(key, value); // Không có TTL hoặc giới hạn kích thước.
}
```

Đây **không phải chương trình độc lập**; cần import `Map`, `HashMap` và đặt trong class. GC không thể giải phóng value khi cache còn giữ đường strong reference tới nó. Gọi `System.gc()` thường xuyên hơn **không sửa được** lỗi logic này.

Một memory leak thực tế là **object được giữ lại không cần thiết theo vòng đời nghiệp vụ**, chứ không phải “bất kỳ object nào sống lâu”. Một cache được cấu hình đúng có thể giữ object lâu một cách hoàn toàn hợp lệ.

## 13. Lỗi thường gặp khi theo dõi “sống” và “đã chết”

| Sai lầm | Điều cần nhớ |
| --- | --- |
| `obj=null` nghĩa object đã chết ngay | Có thể còn đường tham chiếu khác, GC chưa chạy |
| Ra khỏi method là mọi object đã được reclaim | Object có thể thoát ra map/list/closure |
| `System.gc()` bảo đảm một full GC hoàn tất | Đây là lời đề nghị; không dùng làm assert chắc chắn |
| `WeakReference.get()==null` chứng minh thời điểm reclaim | Không, chỉ phản ánh weak reachability/clearing |
| Có `OldObjectSample` tức object đó là bug | Có thể là object hợp lệ sống lâu |
| Không thấy `OldObjectSample` tức không có leak | Sampling có thể bỏ lỡ mẫu |
| Allocation cao chứng minh leak | Cần xem live set và root path, không chỉ allocation rate |
| TLAB allocation event là một event cho mọi `new` | Không, đây là sampling/observations liên quan allocation |
| Giảm 300 object ở histogram nghĩa 300 object đã chết | Chỉ là **net count change** giữa hai điểm |
| `ObjectCountAfterGC` là nhật ký từng object chết | Nó là thống kê khi được bật/hỗ trợ |
| Root path luôn được thu miễn phí | Cần bật, có thể gây pause |
| `lastKnownHeapUsage` là retained size của sample | Đó là bối cảnh heap, không phải size riêng của mẫu |
| Heap used tăng một lần là leak | Cần trend sau GC qua nhiều chu kỳ và workload tương đương |
| JFR chứa mọi event từ lúc JVM khởi động | Recording settings, retention và sampling quyết định dữ liệu |
| Mã Java 11 luôn có `jdk.ObjectAllocationSample` | Event thuộc những JDK mới hơn; kiểm tra JVM hiện tại |
| Có thể đọc file JFR và dump ở nơi công khai | File có thể chứa dữ liệu nhạy cảm; bảo vệ quyền đọc/retention |
| Dùng finalizer để đếm object death | Không tin cậy, không phải hướng tiếp cận Java hiện đại |

## 14. Câu hỏi tự kiểm tra

**Câu 1:** Một mảng đã bị gỡ khỏi `List` nhưng còn được lưu trong `static Map`. Nó đã chết chưa?

**Đáp án:** Chưa. Nếu `Map` còn reachable từ GC root và giữ mạnh mảng, object vẫn sống.

**Câu 2:** Có thể dùng `System.gc()` để chứng minh mọi object không còn reference đã được thu hồi tức thì không?

**Đáp án:** Không. GC timing, thuật toán và việc thực hiện lời đề nghị không được bảo đảm.

**Câu 3:** Vì sao `jdk.ObjectAllocationInNewTLAB` không chứng minh một object sống hay chết?

**Đáp án:** Đây là event liên quan cấp phát ở TLAB; không ghi việc object còn reachable sau các lần GC hay thời điểm reclaim.

**Câu 4:** `jdk.OldObjectSample` có cho biết tất cả live objects của JVM không?

**Đáp án:** Không. Nó lấy mẫu những object tồn tại lâu; với cấu hình thích hợp có thể mang thông tin về allocation và GC root path.

**Câu 5:** Chênh lệch class count sau hai lần GC là `+200`. Có thể kết luận chỉ có 200 object được tạo và không object nào chết không?

**Đáp án:** Không. Có thể có nhiều allocation và reclamation bù trừ nhau. `+200` chỉ là chênh lệch ròng.

**Câu 6:** Trong demo, `released=2:131072:2` có nghĩa JVM vừa giải phóng 131.072 byte không?

**Đáp án:** Không. 131.072 là tổng bytes của hai payload còn được ứng dụng giữ qua list. Hai references đã được gỡ, nhưng chưa có phép đo reclaimed heap bytes.

**Câu 7:** Tại sao path-to-GC-roots hữu ích để sửa memory leak nhưng không nên bật mọi lúc?

**Đáp án:** Nó cho biết đường giữ object từ GC root, nhưng việc tìm đường có chi phí CPU/pause đáng kể.

**Câu 8:** Tại sao nên so sánh “đáy sau GC” thay vì heap-used ngẫu nhiên?

**Đáp án:** Vì heap-used giữa hai lần GC có nhiều đối tượng tạm; dữ liệu sau những GC tương đương phản ánh tốt hơn xu hướng live set.

**Câu 9:** Khi nào heap dump phù hợp hơn JFR?

**Đáp án:** Khi cần phân tích sâu object graph, dominators, retained sizes và JFR samples không đủ để xác nhận nguyên nhân, nếu có đủ quyền/tài nguyên và chấp nhận chi phí.

**Ghi nhớ:** Với **heap profiling trên Java 11+**, **sống** nghĩa là còn reachable/giữ lại ở điểm đo phù hợp; **không còn reachable** mới là ứng viên GC, chưa chắc đã **được GC thu hồi**. JFR dùng **`jdk.OldObjectSample`** để thấy mẫu object sống lâu và đường giữ, **allocation events** để tìm nơi cấp phát, **GC events/statistics** để quan sát live-set trend, và **heap dump/histogram** khi cần snapshot đầy đủ hơn. Không diễn giải JFR như nhật ký chết của từng object; hãy điều tra root references và vòng đời dữ liệu của ứng dụng.

**Tài liệu chính thức:** [Oracle Java SE 11 — Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshooting-memory-leaks.html); [OpenJDK — JEP 328 Flight Recorder](https://openjdk.org/jeps/328); [Java SE 11 — JFR Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html); [Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html); [Java SE 11 — RecordedObject](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html); [Java SE 11 — WeakReference](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/ref/WeakReference.html); [Dev.java — Configuring JFR](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/).
