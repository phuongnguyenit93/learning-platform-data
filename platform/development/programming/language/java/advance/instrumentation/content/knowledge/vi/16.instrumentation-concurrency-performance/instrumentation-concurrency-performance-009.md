# Tránh giữ đối tượng ứng dụng trong dữ liệu đo lâu hơn vòng đời cần thiết

Trong Java Instrumentation, một điểm đo có thể được thêm vào hàng nghìn phương thức để ghi thời gian, tần suất gọi, lỗi, trace hoặc số liệu hiệu năng. Một lỗi nghiêm trọng không nằm ở bytecode được chèn mà ở **dữ liệu được giữ lại sau khi lời gọi đã kết thúc**: helper đưa `request`, `response`, `Throwable` hoặc `Object[] args` vào queue/static map/`ThreadLocal`, rồi vô tình kéo dài vòng đời cả một đồ thị đối tượng ứng dụng.

Điều cần nhớ: **đối tượng đã hết ích lợi về nghiệp vụ chưa chắc đã có thể được GC thu hồi**. Nếu vẫn còn một đường **strong reference** từ GC root đến đối tượng đó, nó còn được coi là reachable. Một sự kiện đo rất nhỏ về mặt số ô dữ liệu có thể giữ **hàng megabyte dữ liệu gián tiếp** nếu nó chứa tham chiếu tới một request có payload, session, cache hoặc class loader.

Bài này thuộc nhóm **Đồng thời và hiệu năng** của Java Instrumentation. Mục tiêu là thiết kế điểm đo không làm đổi vòng đời của dữ liệu ứng dụng: chỉ lưu snapshot nhỏ, không giữ object gốc, giới hạn bộ đệm và thời gian tồn tại, cleanup ngữ cảnh thread/async, tránh pin class loader, phân biệt weak references với giải pháp bảo đảm và kiểm tra bằng thử nghiệm cũng như công cụ heap.

## 1. Phân biệt thời gian thực thi với thời gian giữ tham chiếu

Một HTTP request kết thúc sau 20 ms không có nghĩa mọi object của request được thu gom ở mili-giây 21. JVM chỉ có thể thu gom theo điều kiện reachability và chính sách GC; thời điểm GC là **không xác định**. Một object còn dùng để xử lý request có thể hoàn toàn hợp lệ khi reachable. Vấn đề xảy ra khi một phần **không cần nữa** tiếp tục giữ tham chiếu lâu hơn vòng đời đã định.

Sơ đồ:

```text
Request bắt đầu
      |
      v
Request object + payload + user context
      |
      +-- method đang chạy: reference hợp lệ
      |
      +-- ProbeHelper.capture(request)
               |
               v
          static queue / ThreadLocal / callback / cache
               |
      Request hoàn tất, stack frame được tháo
               |
               v
    Điểm đo vẫn giữ strong reference tới request
               |
               v
    Payload và đồ thị liên quan vẫn reachable
    (dù không còn giá trị cho việc đo)
```

Vấn đề ở đây không nhất thiết là một “memory leak” vĩnh viễn. Một sự kiện bị giữ thêm 30 giây trong queue trước khi exporter xử lý vẫn có thể là **retention quá lâu**, làm tăng peak heap, pause GC, áp lực old generation và độ trễ. Trong thời kỳ traffic đỉnh, hàng nghìn object cùng bị giữ thêm vài giây có thể gây tình trạng rất nặng.

### 1.1. Những trạng thái không được đánh đồng

| Trạng thái | Ý nghĩa | Có chứng minh đã hết giữ object không? |
|---|---|---|
| Method gốc đã `return` | Stack frame của lời gọi đã kết thúc | **Không** nếu queue/callback/ThreadLocal còn reference |
| Trace/span đã “end” | Dữ liệu logic đã kết thúc | **Không** nếu exporter hoặc baggage còn giữ object |
| Queue đã `poll()` một event | Đã bỏ một reference từ queue | **Không** nếu consumer/in-flight batch còn reference |
| `WeakReference.get()==null` | Referent đã bị clear khỏi weak ref | Không chứng minh toàn bộ hệ thống không còn các object khác bị giữ |
| `WeakReference.get()!=null` | Referent chưa bị clear tại thời điểm kiểm tra | **Không** tự chứng minh bị leak; GC có thể chưa chạy |
| `System.gc()` được gọi | Có một yêu cầu/hint GC | **Không** bảo đảm collection tức thời |
| Class loader đã không còn dùng | Ứng dụng đã undeploy/reload plugin | **Không** nếu metadata cache/queue agent còn giữ class/loader |
| Heap dump cho thấy GC root path | Có một đường tham chiếu giữ object | Có bằng chứng mạnh về retention path **tại thời điểm chụp** |

### 1.2. Định nghĩa GC root và strong reachability

GC roots có thể bao gồm các tham chiếu từ stack của thread còn chạy, các static fields của các class đang sống, JNI references và một số vùng giữ đối tượng khác do VM quản lý. Nếu từ root có một chuỗi **strong references** tới object, object đó vẫn strongly reachable.

```text
GC root
  └─ agent class đang sống
      └─ static Queue<ProbeEvent>
          └─ ProbeEvent.argument: Request
              ├─ Request.payload: byte[]
              ├─ Request.session: Session
              └─ Request.owner: ApplicationService
                  └─ Class<?> / ClassLoader / resource graph...
```

Một event tưởng chỉ có `methodId` và `argument` nhưng trường `argument` làm sống **toàn bộ graph reachable** từ request. Vì thế kích thước trực tiếp của event object **không phản ánh retained heap size**.

**Đừng suy từ biểu đồ heap rằng object A “chiếm toàn bộ” graph của nó theo cách độc quyền nếu object khác cũng tham chiếu cùng graph.** Công cụ có thể hiển thị shallow size, retained size và dominator tree với những ý nghĩa khác nhau; cần đọc đúng chỉ số khi chẩn đoán.

## 2. Những nơi instrumentation thường giữ object quá lâu

| Điểm giữ reference | Ví dụ anti-pattern | Vì sao sống lâu? | Hướng sửa |
|---|---|---|---|
| `static List<Object[]>` | `EVENTS.add(args)` | Agent class/static sống rất lâu | Event chỉ chứa primitive/snapshot đã duyệt |
| Queue exporter | `queue.offer(request)` | Backpressure hoặc network chậm | Giới hạn queue, drop; không enqueue object gốc |
| `ThreadLocal<Request>` | `CURRENT.set(request)` mà không `remove` | Thread pool thread tái sử dụng lâu | `try/finally` + `remove`; lưu context nhỏ |
| `InheritableThreadLocal` | Copy context có object tới child thread | Child thread có thể sống lâu/không liên quan | Không truyền toàn bộ request; quản lý explicit scope |
| Lambda/callback | `() -> report(request)` | Closure capture `request`; timer giữ callback | Chụp trước ID/timing nhỏ; hủy callback khi hết hạn |
| `CompletableFuture`/retry task | `thenApply(x -> use(request))` | Future stage chưa hoàn thành | Không capture app graph; timeout/cancel/cleanup có kiểm soát |
| Listener registration | `registry.addListener(listenerWithRequest)` | Registry sống vượt request | Unregister trong `finally`/lifecycle closure |
| Metric labels | `label = request.toString()` | Series/cache cardinality cao và giữ string | Nhãn enum/nhóm hữu hạn, không stringify args |
| Metadata cache | `Map<Class<?>,Metadata>` của agent | Class key kéo theo defining class loader | Scoped cache lifecycle, weak keys khi an toàn, clear đúng lúc |
| Weak cache sai | `WeakHashMap<Key,Value>` nhưng value tham chiếu key | Value strong giữ lại key | Loại chu trình tham chiếu, thử bằng heap path |
| Throwable retention | `event.error = throwable` | Cause/suppressed/fields và type/classloader có thể được giữ | Mã lỗi ngắn/được phê duyệt; không giữ raw Throwable |
| Logger async | Tham số log `{request}` được giữ để format sau | Formatting trì hoãn nhưng reference tồn tại | Log snapshot scalar/trusted text, không đẩy raw args |
| Native callback handle | Global JNI reference hoặc tag map giữ object | Native side giữ ngoài Java queue | Release global ref/tag theo lifecycle rõ |

**Ranh giới sở hữu:** Nếu dữ liệu bắt nguồn từ ứng dụng, agent nên coi nó là **borrowed** chỉ trong lúc đang xử lý điểm đo. Việc giữ vượt phạm vi cần một hợp đồng dữ liệu độc lập (loại, quyền, giới hạn kích thước và lifetime), không được mặc định vì callback nhìn thấy nó.

## 3. Anti-pattern phổ biến: “cứ đưa Object[] sang exporter xử lý sau”

Một transformer có thể chèn call đến helper kiểu:

```java
// Ví dụ API minh họa; không phải chương trình độc lập.
ProbeHelper.enter(int methodId, Object[] arguments);
```

Nếu helper làm:

```java
// ANTI-PATTERN: giữ nguyên references của đối số.
static final java.util.Queue<Object[]> EVENTS =
        new java.util.concurrent.ConcurrentLinkedQueue<>();

static void enter(int methodId, Object[] arguments) {
    EVENTS.offer(arguments);
}
```

thì `arguments` vẫn chứa references tới mọi đối số và các object chúng tham chiếu. `ConcurrentLinkedQueue` không có giới hạn số phần tử mặc định. Một exporter chậm hoặc chết làm queue tăng không giới hạn; mỗi reference có thể giữ graph rất lớn.

**Chú ý:** Thay bằng `arguments.clone()` hoặc `Arrays.copyOf(arguments,...)` không giải quyết retention: đó chỉ là **shallow copy**; những object trong mảng vẫn được tham chiếu mạnh.

```java
Object[] snapshot = arguments.clone(); // Không copy object graph.
EVENTS.offer(snapshot);                // Vẫn giữ các đối số.
```

Tương tự, đóng gói vào `record ProbeEvent(Object[] args)` hoặc `Map<String,Object>` vẫn giữ object. Tên “snapshot” không khiến một bộ tham chiếu trở thành dữ liệu độc lập.

### 3.1. Async logging và delayed serialization vẫn giữ reference

Một số logger/encoder không format giá trị ngay mà đưa event chứa object sang thread xử lý nền. Điều đó có thể giảm latency producer nhưng **kéo dài thời gian sống của object ứng dụng**. Nếu async log event giữ `request`, giá trị có thể chỉ được `toString` sau hàng giây; vừa có retention, vừa có nguy cơ chạy user code muộn.

Thay:

```java
logger.debug("request={}", request); // Có thể được format muộn.
```

bằng:

```java
logger.debug("methodId={} outcome={}", methodId, outcomeCode);
```

với `methodId` và `outcomeCode` là metadata đáng tin, số lượng giá trị hữu hạn. **Không** tạo chuỗi `request.toString()` trước rồi mới cắt 100 ký tự: việc chuỗi hóa đã chạy và có thể tốn nhiều tài nguyên, lộ bí mật hoặc gọi lại mã ứng dụng. Khi sự kiện không cần payload, đừng đọc payload.

### 3.2. Throwable và object trả về cũng có vòng đời

`Throwable` là một object thật, có stack trace, cause và suppressed exceptions, và trong trường hợp custom subclass có thể giữ thêm state. Nếu agent giữ raw `Throwable` trong batch để upload về sau, nó có thể giữ class và dữ liệu đi kèm lâu hơn cần thiết.

Tương tự, `returnValue` có thể là domain model/cached proxy/lazy object. Đừng xem `null`-check rồi `new ProbeEvent(returnValue)` là an toàn chỉ vì chưa gọi `toString`: retention phát sinh ngay khi event giữ reference.

Một event lỗi thường chỉ cần:

```json
{
  "methodId": 241,
  "durationNanos": 72000,
  "outcomeCode": 2,
  "sampled": true
}
```

Đây là schema minh họa. Không có raw `Throwable`, `request`, `response`, `Object[]` hoặc giá trị bí mật. Nếu cần tên lỗi, dùng phân loại có tập giá trị được phê duyệt; không mặc định lấy toàn bộ message hoặc stack trace vào high-cardinality metric label.

## 4. Nguyên tắc snapshot tối thiểu

**Snapshot phù hợp** là dữ liệu đo tự đứng độc lập, được lấy có chủ đích, không tham chiếu về đồ thị object ứng dụng và không cần gọi lại phương thức của object gốc sau khi request đã kết thúc.

### 4.1. Ví dụ model nên ưu tiên

```java
// Một schema đơn giản phù hợp Java 17+.
public record Measurement(
        int methodId,
        long durationNanos,
        int outcomeCode,
        boolean sampled) {
}
```

Đây là một record chỉ có primitive fields. Không chứa `Object`, `Throwable`, `Class<?>` hay `Map<String,Object>`. Việc giữ event trong queue có giới hạn **không tự giữ request instance** qua các fields của record này.

**Nhưng** vẫn cần giới hạn số record: record nhỏ tích tụ vô hạn vẫn gây tốn heap. Và `durationNanos` là một khoảng đo bằng đồng hồ đơn điệu `System.nanoTime()`, **không** phải timestamp epoch; nếu cần wall-clock timestamp riêng phải có thiết kế đồng bộ phù hợp.

### 4.2. Data policy theo từng mức

| Mục tiêu quan sát | Dữ liệu tối thiểu | Có cần object gốc? |
|---|---|---|
| Số lượt gọi method | `methodId` và counter | Không |
| Latency | `methodId` + `durationNanos` | Không |
| Success/error rate | `methodId` + `outcomeCode` | Không |
| Tracing cơ bản | ID chuỗi ngắn đã duyệt, span ID, timing | Không cần domain object |
| Request size | Primitive size do tầng ứng dụng cung cấp theo hợp đồng | Không cần giữ `Request` |
| Phân loại lỗi | Enum/int code do probe chọn theo policy | Không giữ raw `Throwable` |
| Đánh giá một field nghiệp vụ | Giá trị đã được phép và cap từ API chuyên biệt | Không lưu cả object graph |
| Điều tra lỗi hiếm cần payload | Opt-in đặc biệt, privacy review, TTL/budget, nguồn an toàn | Chỉ nếu được phê duyệt và không còn cách ít xâm nhập hơn |

**Lưu ý:** Một `String` là immutable nhưng vẫn có thể chứa dữ liệu nhạy cảm hoặc dài; giữ `String` của ứng dụng không phải lúc nào vô hại. Một trace ID được cho phép cần có cap, chính sách cardinality, retention và kiểm tra trước khi copy/emit. Hash không khóa của ID ít entropy cũng không tự bảo đảm ẩn danh.

### 4.3. Không dùng generic serialization để “snapshot”

Các cách sau có thể tạo thêm vấn đề:

- JSON serialization từ object bất kỳ có thể gọi getters, custom serializer, proxy interceptors hoặc lazy loading, tùy thư viện/cấu hình.
- Java `ObjectOutputStream` có thể duyệt object graph và kích hoạt serialization hooks như `writeObject`/`writeReplace`.
- Deep-copy một graph lớn vẫn tốn heap, CPU, có thể tiết lộ dữ liệu và chiếm queue lâu, dù không giữ reference gốc.
- Cắt kích thước chuỗi **sau** khi serialize chỉ giới hạn phần được xuất, không giới hạn chi phí trước đó.
- Lưu raw bytes của payload thành telemetry cũng là dữ liệu nhạy cảm và có thể rất lớn.

Giải pháp là **schema đo được khai báo trước**, không phải generic serialize-everything. Nếu business cần trường cụ thể, ứng dụng nên cung cấp một adapter an toàn với hợp đồng dữ liệu, phiên bản và quyền truy cập rõ ràng.

## 5. Thời điểm chụp snapshot và thời điểm thả reference

Một pipeline tốt xác định lifetime của mỗi dữ liệu:

```text
Application method entry
  |
  +-- xác định methodId / sampling / privacy policy
  |
  +-- tạo timing state nhỏ, nếu cần
  |
  v
Application method body
  |
  v
Method exit (success/exception)
  |
  +-- duration = now - start
  +-- outcome = mã hữu hạn
  +-- tạo Measurement chỉ chứa scalar
  +-- offer vào bounded buffer, nếu đầy thì drop + counter
  +-- xóa ThreadLocal/context trong finally
  |
  v
Request kết thúc
  |
  v
Exporter lấy Measurement, serialize và gửi
  (không còn request/args/return object cần giữ)
```

Ba chỗ đặt ranh giới:

1. **Trước capture:** sampling, allowlist, privacy và budget phải được quyết định **trước** việc đọc/copy/serialize dữ liệu đắt đỏ.
2. **Trước enqueue:** chuyển thành dữ liệu nhỏ **không phụ thuộc domain object**; không đẩy một supplier/lambda giữ object để “snapshot sau”.
3. **Sau hoàn tất:** clear references/ThreadLocal/listeners, và không giữ event vô hạn trong retry backlog.

Cũng cần phân biệt **event lifetime** với **request lifetime**: event đo có thể sống lâu hơn request để exporter gửi đi, nhưng nó không nên kéo dài vòng đời **object ứng dụng**.

### 5.1. Bounded queue là cần nhưng chưa đủ

`ArrayBlockingQueue<Measurement>(1024)` có giới hạn **số phần tử**. Nhưng nếu kiểu event là `Object` và mỗi phần tử tham chiếu một request lớn, 1024 phần tử vẫn có thể giữ một lượng heap rất lớn. **Đơn vị giới hạn phải xét retained graph**, không chỉ số event.

Nên phối hợp:

- Max event count/byte budget.
- Max in-flight batches và thời gian chờ xuất.
- Timeout/backoff có giới hạn.
- Chính sách drop khi exporter chậm.
- Không giữ raw request sau khi enqueued.
- Xử lý shutdown/drain có deadline và giải phóng event references.
- Số liệu accepted/dropped/queue depth/export lag/bytes.
- Policy xóa dữ liệu sau TTL, có kiểm soát dữ liệu nhạy cảm.

`offer` trên queue có giới hạn hữu ích hơn `put` trong hot path nếu không muốn chặn request, nhưng phải đo hiệu năng/semantics trên workload thật. Một `offer` thành công **không** có nghĩa thông tin đã xuất ra external sink; cần báo `ENQUEUED` khác `EXPORTED`.

## 6. Ví dụ Java 17+ chạy được: queue giữ request và event chỉ có scalar

Ví dụ cố ý viết một nhánh **không an toàn** để nhìn rõ strong reference, và một nhánh **tốt hơn** dùng record không chứa object. Chương trình không gọi `System.gc()`, không đoán GC chạy vào lúc nào và cho stdout **deterministic**.

### 6.1. File `RetentionDemo.java`

```java
import java.util.ArrayDeque;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class RetentionDemo {
    private static final int MAX_SAFE_EVENTS = 2;

    // ANTI-PATTERN: static queue giữ chính Request object.
    private static final ArrayDeque<Request> RAW_EVENTS =
            new ArrayDeque<>();

    // Event độc lập với Request, giới hạn số phần tử.
    private static final ArrayDeque<Measurement> SAFE_EVENTS =
            new ArrayDeque<>();

    // Dùng để minh họa nguy cơ context tràn qua task trong pool.
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    private static final class Request {
        final byte[] payload = new byte[1024 * 1024];
    }

    private record Measurement(
            int methodId,
            long durationNanos,
            int outcomeCode) {
    }

    private static boolean recordSafe(
            int methodId, long durationNanos, int outcomeCode) {
        if (SAFE_EVENTS.size() >= MAX_SAFE_EVENTS) {
            return false;
        }
        return SAFE_EVENTS.offerLast(
                new Measurement(methodId, durationNanos, outcomeCode));
    }

    public static void main(String[] args) throws Exception {
        Request request = new Request();

        RAW_EVENTS.addLast(request);
        System.out.println(
                "RAW_HOLDS_REQUEST="
                + (RAW_EVENTS.peekFirst() == request));

        System.out.println(
                "SAFE_ACCEPTED_1=" + recordSafe(101, 2500L, 0));
        System.out.println(
                "SAFE_ACCEPTED_2=" + recordSafe(102, 5000L, 0));

        System.out.println("SAFE_EVENT=" + SAFE_EVENTS.peekFirst());

        boolean thirdAccepted = recordSafe(103, 7500L, 1);
        System.out.println(
                "THIRD_DROPPED=" + !thirdAccepted);

        // Bỏ strong reference do chính static queue giữ.
        RAW_EVENTS.clear();
        System.out.println(
                "RAW_QUEUE_EMPTY=" + RAW_EVENTS.isEmpty());

        // Không kiểm thử thời điểm GC: request còn có thể nằm
        // ở local hoặc các reference không hiển thị khác.
        request = null;

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            // Task A cố tình không remove context.
            pool.submit(() -> CONTEXT.set("request-A")).get();

            boolean stale = pool.submit(
                    () -> "request-A".equals(CONTEXT.get())).get();
            System.out.println("STALE_CONTEXT_SEEN=" + stale);

            // Xóa context trên đúng worker thread.
            pool.submit(() -> CONTEXT.remove()).get();

            // Task B: cleanup đúng trong finally.
            pool.submit(() -> {
                CONTEXT.set("request-B");
                try {
                    // Mô phỏng công việc; không giữ Request.
                } finally {
                    CONTEXT.remove();
                }
            }).get();

            boolean cleaned = pool.submit(
                    () -> CONTEXT.get() == null).get();
            System.out.println("AFTER_FINALLY_CLEAN=" + cleaned);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Chương trình cố ý chạy **một main thread và một executor thread**, không phải queue production đa thread. `ArrayDeque` không thread-safe; demo chỉ truy cập các queue trong main. `Measurement` là nested record có ba trường primitive, nên chính record không tham chiếu `Request`. `ThreadLocal<String>` dùng chuỗi ngắn vì mục tiêu là chứng minh **context cũ chảy sang task mới**; nếu đặt `Request` vào ThreadLocal trong production, rủi ro giữ graph sẽ nặng hơn.

### 6.2. Biên dịch và chạy

Dùng JDK 17 hoặc mới hơn trong thư mục chứa file:

```shell
javac RetentionDemo.java
java RetentionDemo
```

**Stdout của logic code:**

```text
RAW_HOLDS_REQUEST=true
SAFE_ACCEPTED_1=true
SAFE_ACCEPTED_2=true
SAFE_EVENT=Measurement[methodId=101, durationNanos=2500, outcomeCode=0]
THIRD_DROPPED=true
RAW_QUEUE_EMPTY=true
STALE_CONTEXT_SEEN=true
AFTER_FINALLY_CLEAN=true
```

Giải thích:

- `RAW_HOLDS_REQUEST=true` chứng minh queue static đang giữ **đúng cùng một Request instance** khi nó chưa được `clear()`.
- `SAFE_ACCEPTED_1/2` là true vì queue chưa chạm giới hạn 2 event. Record được in ra chỉ có metadata scalar.
- `THIRD_DROPPED=true` là kết quả của policy từ chối event thứ ba, không phải một giả định rằng mạng đã gửi thành công hai event đầu.
- `RAW_QUEUE_EMPTY=true` chứng minh đã **bỏ reference khỏi queue này**; **không** chứng minh object chắc chắn đã bị GC reclaim.
- `STALE_CONTEXT_SEEN=true`: cùng worker thread của executor chạy task B tiếp sau task A, nên thấy giá trị ThreadLocal mà task A quên xóa.
- `AFTER_FINALLY_CLEAN=true`: task dùng `finally` đã remove context trên chính thread đó; task kế tiếp không thấy dữ liệu cũ.

**Điều bài lab không chứng minh:** nó không đo chính xác retained bytes, không chứng minh lúc nào GC thu object, không stress multi-thread access vào queue, không có một Java agent thực sự chèn bytecode. Mục tiêu là cho thấy reference ownership và scope cleanup bằng lệnh Java phổ thông.

### 6.3. Cách biến demo thành pattern tốt

Không sao chép `RAW_EVENTS` vào helper thật. Trong instrumentation production:

- Không tạo mảng `Object[] args` nếu phép đo không cần arguments.
- Nếu helper chỉ cần `methodId` và `durationNanos`, bytecode nên đẩy đúng các primitive đó.
- Dùng một queue thread-safe có capacity và chính sách drop, ví dụ `ArrayBlockingQueue<Measurement>` cho một pipeline phù hợp.
- Khi async exporter lấy event ra, không khôi phục lại `Request` bằng lookup cache để serialize về sau.
- Xóa context trong `finally` ở đúng thread; với async flow cần kế hoạch chuyển **ID nhỏ có phạm vi** chứ không mang cả request.
- Chỉ giữ một khoảng thời gian hợp lý cho retry/backlog, thiết kế shutdown và cleanup.

## 7. ThreadLocal: một thread có thể sống lâu hơn nhiều request

`ThreadLocal<T>` cung cấp một giá trị **riêng cho từng thread**, không phải scope tự động theo request. Theo Javadoc, mỗi thread giữ tham chiếu đến bản giá trị thread-local của nó trong những điều kiện được mô tả bởi vòng đời thread và ThreadLocal. Nếu thread thuộc pool có thời gian sống nhiều giờ, một request object bị đặt vào ThreadLocal có thể bị giữ sau khi task đã hoàn tất.

```java
// ANTI-PATTERN minh họa, không phải file độc lập:
private static final ThreadLocal<Object> CURRENT_REQUEST =
        new ThreadLocal<>();

void handle(Object request) {
    CURRENT_REQUEST.set(request);
    process(request);              // Nếu throw, không remove.
}
```

Kết quả không chỉ là áp lực heap: task của request B trên cùng thread có thể đọc **context của request A**, gây sai trace ID hoặc rò rỉ dữ liệu giữa yêu cầu.

**Mẫu sửa:**

```java
// Mẫu minh họa, process(...) là method của ứng dụng.
void handle(Object request, String approvedTraceId) {
    try {
        CURRENT_TRACE_ID.set(approvedTraceId);
        process(request);
    } finally {
        CURRENT_TRACE_ID.remove();
    }
}
```

Đoạn này giả định `CURRENT_TRACE_ID` là `ThreadLocal<String>` đã khai báo; còn `request` chỉ được truyền cho ứng dụng, **không đưa vào ThreadLocal của agent**. Trace ID phải có schema/budget/privacy policy, và `remove` phải chạy trong **chính thread đã gọi `set`**.

### 7.1. Nested calls và scope phục hồi

Nếu helper dùng `ThreadLocal` để truyền context qua các method lồng nhau, một `remove()` không điều kiện ở scope bên trong có thể xóa context của scope bên ngoài. Ví dụ:

```text
outer request scope: trace A
  enter nested operation: trace B
  nested operation exits
  outer expects trace A restored
```

Với nesting thực sự, cần chính sách **save/restore previous value**:

```java
// Mẫu minh họa có biến CONTEXT kiểu ThreadLocal<String>.
String previous = CONTEXT.get();
try {
    CONTEXT.set(childTraceId);
    runNested();
} finally {
    if (previous == null) {
        CONTEXT.remove();
    } else {
        CONTEXT.set(previous);
    }
}
```

Điều này chỉ an toàn nếu `previous` là **một context nhỏ được phép tồn tại ở outer scope**, không phải reference đến object request khổng lồ. Khi outer scope kết thúc, chính outer cũng phải cleanup. Thay `remove` bằng `set(null)` không phải lúc nào cũng tương đương về vòng đời và semantics của initial value; ưu tiên `remove` ở ranh giới kết thúc thực.

### 7.2. Async thread và virtual threads

`ThreadLocal` không tự trở thành “request scoped” vì thread được tạo từ executor. Với `CompletableFuture.supplyAsync`, callback có thể chạy trên thread pool khác; context có thể **không hiện diện** hoặc bị giữ trên thread worker nếu việc cleanup sai.

Với virtual threads (Java 21), mỗi virtual thread cũng hỗ trợ ThreadLocal nhưng có số lượng lớn và vòng đời riêng. Việc lạm dụng dữ liệu lớn trong ThreadLocal vẫn tăng memory footprint, còn framework/job có thể sinh threads mới thường xuyên. Không dùng ThreadLocal như kho lưu `Request` xuyên suốt asynchronous transaction; chuyển **metadata tối thiểu** trong một scope rõ ràng.

`InheritableThreadLocal` có thể truyền giá trị tới thread con trong những điều kiện xác định, nhưng điều đó có thể **mở rộng reachability** tới nhiều thread. Không chọn nó làm đường truyền payload của agent chỉ để tránh thêm tham số method.

### 7.3. MDC/tracing context cũng là dữ liệu có vòng đời

Mapped Diagnostic Context (MDC) của logger và “current span” của thư viện tracing thường dựa vào context storage kiểu thread-local hoặc scope. Hãy đảm bảo đóng scope token và xóa context trong `finally`, đặc biệt ở worker pools. Khi chuyển context sang task khác, chỉ sao chép **trace/span identifiers** và baggage đã được phép; không gắn nguyên request/session/Throwable vào baggage.

## 8. Callback, lambda, Future, timer: reference ẩn bên trong công việc hoãn

Một lambda có thể capture biến từ scope hiện tại. Nếu lambda được giữ trong scheduler hoặc retry queue lâu hơn request, object bị capture cũng có thể sống lâu hơn.

```java
// ANTI-PATTERN, snippet minh họa:
Request request = ...;
scheduler.schedule(
    () -> exporter.export(request), 60, TimeUnit.SECONDS);
```

Ở ví dụ này, lambda có thể giữ `request` ít nhất đến khi scheduler giải phóng task/callback; thực tế còn tùy lifecycle, cancellation và cấu trúc scheduler. Một callback được đăng ký vào listener registry có thể còn tồn tại vô thời hạn nếu không unregister.

**Cách tốt hơn:** chuyển sang snapshot primitive trước lúc tạo callback:

```java
// Các biến/scheduler/exporter được giả định ở code minh họa.
int methodIdSnapshot = methodId;
long elapsedSnapshot = elapsedNanos;
int outcomeSnapshot = outcome;

scheduler.schedule(
    () -> exporter.export(
        methodIdSnapshot, elapsedSnapshot, outcomeSnapshot),
    60, TimeUnit.SECONDS);
```

Dù vậy, lambda còn capture `exporter` và có thể kéo dài lifetime exporter. Điều này có thể chủ ý nếu exporter là component agent global; phải kiểm soát nơi schedule task, shutdown/cancel, tránh mỗi request tạo một exporter object mới.

### 8.1. Future chờ mãi không đồng nghĩa giải phóng callback

Một `CompletableFuture` chưa hoàn thành, một `FutureTask` nằm trong queue, hoặc retry closure có thể còn giữ captured references. Gọi `cancel` không luôn có nghĩa task được xóa ngay khỏi mọi queue/graph; hành vi phụ thuộc executor/implementation. Đặt timeout và cleanup, đo pending tasks và kiểm tra heap path thay vì suy GC đã giải phóng object sau một lệnh cancel.

### 8.2. Listener registration và class-loader leak

`static listenerRegistry.add(listener)` với listener là anonymous inner class/lambda capture object từ module ứng dụng có thể giữ cả listener, owner object và class loader của plugin. Khi undeploy, registry thuộc agent/JVM vẫn sống nên plugin loader không được GC unload.

Cần dùng registration handle để **unregister** ở lifecycle tương ứng, hoặc cấu trúc weak-listener đúng ngữ nghĩa nếu thực sự phù hợp. Weak listener có thể bị GC trước khi tác vụ hoàn thành; vì vậy không phải giải pháp mặc định nếu callback là trách nhiệm bắt buộc.

### 8.3. Dùng `Supplier<?>` không làm dữ liệu tự an toàn

Một “lazy event” như:

```java
queue.offer(() -> request.toString());
```

không gọi `toString` ngay, nhưng **closure vẫn giữ request**. Khi consumer xử lý muộn, nó vừa giữ graph lâu hơn vừa gọi mã ứng dụng ở thread khác. Đây có thể còn khó chẩn đoán hơn synchronous stringify. Nếu không cần nội dung object, không tạo supplier capture object ngay từ đầu.

## 9. Metadata cache và class-loader unloading

Java agent thường sống suốt JVM, trong khi webapp/plugin có thể redeploy nhiều lần với **class loaders khác nhau**. Một agent cache dùng key/value mạnh tham chiếu tới class ứng dụng có thể ngăn class loader cũ được GC:

```java
// ANTI-PATTERN minh họa:
static final Map<Class<?>, Object> METADATA =
        new ConcurrentHashMap<>();

METADATA.put(applicationClass, metadata);
```

`Class<?>` gắn với class definition, metadata có thể chứa `Method`, `Field`, `MethodHandle`, `ClassLoader`, callback hoặc lambda capture application class. Một static map được giữ bởi agent class có vòng đời dài có thể tạo retention chain tới loader của ứng dụng.

```text
Agent singleton
  └─ static metadata map
      └─ key: Class<?> của webapp V1
          └─ defining ClassLoader V1
              └─ nhiều classes/resources/caches của webapp
```

Không chỉ key: value cũng có thể giữ loader, ngay cả nếu key là `String` binary name. Và cùng binary name có thể được các loaders khác nhau định nghĩa, nên cache theo tên string đơn lẻ còn có nguy cơ **trả nhầm metadata** giữa deployments.

### 9.1. Cách quản lý cache

- Chỉ cache khi thật sự cần; ưu tiên ID/descriptor nhỏ, không giữ `Class<?>` vô hạn.
- Đặt cache theo **class-loader/deployment lifecycle**, và clear khi ứng dụng unload nếu có hook đáng tin cậy.
- Nếu dùng weak keys, đảm bảo values **không tham chiếu ngược** tới keys/classloaders.
- Kiểm tra các references bên trong `MethodHandle`/reflection metadata, callback và executor task; chúng có thể gián tiếp giữ declaring class.
- Cân nhắc cấu trúc cache với eviction/LRU/size/TTL, nhưng TTL không phải chính sách dọn class loader tuyệt đối nếu một object vẫn được value giữ ngoài cache.
- Đừng dựa vào `ClassLoader.finalize` hoặc “chờ GC là tự hết”; cần ownership/lifecycle rõ.

### 9.2. `WeakHashMap` có thể gây hiểu nhầm

`WeakHashMap<K,V>` giữ **key bằng weak reference** nhưng **value bằng strong reference**. Nếu value giữ key (trực tiếp hoặc qua chuỗi object), key không weakly reachable và entry có thể không biến mất.

```java
// Minh họa nguy cơ (không khuyến nghị dùng như cache production):
Map<Object, Object> cache = new WeakHashMap<>();

Object key = new Object();
Object value = new Object() {
    final Object owner = key;
};
cache.put(key, value);

// Value -> key: khi map giữ value mạnh, key vẫn reachable.
```

Đây là ý tưởng minh họa, không phải test GC. Trong Java source thật, biến local `key` capture trong anonymous class phải **final hoặc effectively final**; snippet trên không gán lại key nên thỏa. Nhưng trong trường hợp cache metadata thực tế, cycles có thể gián tiếp qua class/method/loader.

**Không khẳng định “dùng WeakHashMap là hết class-loader leaks”**. Phải phân tích strong-reference graph của cả keys và values và bảo đảm structure/callbacks không pin loader ở nơi khác.

### 9.3. `WeakReference` không thay thế policy dữ liệu

`WeakReference<Request>` không tự giữ referent strongly reachable, nên có thể hữu ích cho bảng quan sát best-effort. Nhưng:

- `weak.get()` có thể trả `null` tại bất kỳ thời điểm phù hợp với GC, không bảo đảm dữ liệu sẽ còn để exporter đọc.
- Một đối tượng khác vẫn có thể giữ request qua strong reference, nên chỉ đổi **một field** sang weak không chứng minh hết retention.
- Nếu mỗi event cần payload để bảo đảm xuất chính xác, dùng weak reference có thể khiến dữ liệu mất không kiểm soát.
- Không nên gọi `System.gc()` trong hot path và chờ thu gom để xác minh logic.

Với telemetry, tốt hơn là event **không cần referent**, chỉ chứa snapshot đã duyệt.

## 10. Dữ liệu bí mật, kích thước và cardinality

Một reference leak thường đi kèm rủi ro privacy: object `Request` có thể giữ request body, headers, token, session, account identifiers, credentials hoặc dữ liệu người dùng. Khi queue lưu reference, dữ liệu ấy có thể tồn tại lâu trong heap và xuất hiện trong heap dump, dù pipeline chỉ định xuất latency.

### 10.1. Chính sách dữ liệu nên có trước khi instrument

- **Mặc định không lấy đối số, return object hay Throwable**.
- Chỉ ghi `methodId`, duration, outcome và trace/span ID được kiểm soát.
- Nếu buộc lấy một field, phải có allowlist, privacy review, cap, TTL, ownership và test riêng.
- Không dùng raw user ID/order ID/exception message làm metric label: cardinality lớn và dễ lộ dữ liệu.
- Đừng chuyển raw payload thành Base64/JSON rồi gọi là “snapshot nhỏ” — bản sao vẫn là dữ liệu và vẫn chiếm bộ nhớ.
- Giới hạn log/heap dump access; heap dump có thể chứa secrets đang nằm trong memory.
- Phân quyền và audit thay đổi cấu hình capture; có cách tắt tính năng khi phát hiện lỗi retention.

### 10.2. Budget phải áp trước khi copy

Một policy mẫu:

```text
captureMode                = NO_RAW_ARGUMENTS
maxEventCountInQueue        = 1024
maxEventPayloadBytes        = 256
maxExporterBatchEvents      = 256
maxPendingRetries           = 2
maxEventAgeMillis           = 5000
overflowPolicy              = DROP_WITH_COUNTER
captureSensitiveData        = false
```

Các con số là **ví dụ cấu hình**, không phải mặc định an toàn cho mọi hệ thống. `maxEventPayloadBytes` chỉ hữu ích khi event đã được thiết kế chứa dữ liệu bounded, **không chứa raw object reference**. Một reference duy nhất có thể pin graph lớn ngoài mọi dự tính “256 bytes”.

**Ngân sách thời gian giữ:**
`t_lifetime = t_last_reference_release - t_capture`, không phải chỉ `t_export - t_capture`. Một exporter có thể báo thành công nhưng còn giữ event trong last-batch list hoặc retry closure; cần xóa references khi hoàn tất.

## 11. Đo overhead và phát hiện retention bằng công cụ

### 11.1. Không kết luận leak từ một phép thử `System.gc()`

`System.gc()` là yêu cầu/hint; JVM có thể phản ứng khác theo cấu hình collector. Local variable trong frame đang chạy hoặc JIT optimization cũng ảnh hưởng reachability. Vì vậy test kiểu:

```java
WeakReference<Request> ref = new WeakReference<>(request);
request = null;
System.gc();
assert ref.get() == null; // SAI nếu coi đây là kiểm thử tất định.
```

không đáng tin nếu khẳng định “GC phải thu object ngay”. Đoạn là **anti-pattern minh họa**, không phải test unit nên sao chép. Thay vào đó dùng các chứng cứ như số phần tử queue, số event đang xử lý, class-loader counts, heap dump/retained-size path và thử nghiệm load có kiểm soát.

### 11.2. Các chỉ số nên theo dõi

```text
probe_events_accepted_total
probe_events_dropped_total{reason}
probe_queue_depth
probe_inflight_batches
probe_oldest_event_age_seconds
probe_capture_bytes_estimated_total
probe_export_retries_total
probe_export_latency_seconds
probe_context_cleanup_errors_total
probe_active_registrations
probe_metadata_cache_entries
probe_classloaders_observed
```

Các tên metric là **gợi ý**, không phải API chuẩn. Không thêm label là request ID, raw class loader identity string vô hạn, arguments hoặc email. Theo dõi từ thời điểm bật agent so với baseline khi không bật, và để ý peak heap, allocation rate, p95/p99 latency, GC pause time và memory sau một chu kỳ traffic + nghỉ.

### 11.3. Chẩn đoán với `jcmd` (HotSpot JDK 17+)

Với một Java process có PID thực, sau khi được cấp quyền vận hành:

```shell
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump /secure/path/heap.hprof
```

**Hai lệnh trên là mẫu**: thay `<pid>` bằng PID số thực và đường dẫn bằng nơi được phép ghi. Theo tài liệu `jcmd`, các lệnh histogram/heap dump có thể **tác động mạnh đến tiến trình** (đặc biệt heap lớn) và heap dump có thể chứa credential/PII. Chỉ chạy sau khi đánh giá tác động, trong môi trường có quyền truy cập thích hợp, không chụp heap production theo thói quen.

Trong công cụ phân tích heap như Eclipse MAT hoặc profiler tương ứng, tìm:

1. Các instances của `Request`/`Payload` còn sống sau khi traffic ngừng.
2. **Path to GC Roots**: ai giữ `Request` (static `EVENTS`, `ThreadLocalMap`, task queue, listener registry, metadata cache)?
3. **Dominator tree/retained size**: object nào có vai trò giữ graph đáng kể?
4. Số lượng class loaders sau nhiều lần redeploy/attach agent.
5. Trạng thái queue và các in-flight/retry events tại thời điểm chụp.
6. Có sự khác biệt giữa “đang xử lý hợp lệ” và “đã hết vòng đời nhưng vẫn bị giữ” không?

Một class histogram chỉ cho biết số lượng và kích thước theo lớp, **không tự chỉ ra object nào đang giữ reference**; cần heap graph/path để kết luận retention chain. Khi phân tích, tránh đưa heap dump lên nơi lưu trữ không được bảo vệ.

### 11.4. Test có kiểm soát theo hai pha

**Pha A – agent chưa bật:** tạo một lượng request đại diện, kết thúc toàn bộ request, đo steady-state heap/GC và class loader lifecycle.

**Pha B – agent đã bật:** cùng traffic, cùng thời gian quan sát, exporter bị làm chậm có kiểm soát, so sánh queue depth, retained heap, latency, pending tasks và counts. Sau khi traffic về 0, xác minh các queues/callbacks/context đều được cleanup; nếu có object còn sống, truy path to GC roots.

Chạy nhiều lần vì GC, JIT warm-up và allocation behavior có độ biến thiên. **Không tự đưa ra một ngưỡng “0 object request còn sống”** trong lúc thread/task còn xử lý hoặc heap dump có cả đối tượng reachable hợp lệ.

## 12. Thiết kế điểm đo tương thích với callback/bytecode instrumentation

Một helper production không nên nhận mọi đối số dưới dạng object chỉ để tính latency:

```java
// API thiết kế nên ưu tiên:
void onEnter(int methodId);
void onExit(int methodId, long elapsedNanos, int outcomeCode);
```

Đây là **interface mô tả**, không phải source file chạy độc lập. Khi chèn bytecode, bạn có thể truyền primitive method ID và elapsed time, không phải `this`, `args`, return value hoặc exception object. Điều này giảm các reference còn sống trong helper và giảm nguy cơ lộ dữ liệu.

### 12.1. Không giữ `this` chỉ để liên kết enter/exit

Một thiết kế thường làm:

```text
onEnter(this, args) -> tạo event có object identity
onExit(this, result) -> tìm event để hoàn tất
```

Nếu event map keyed by `this`, mỗi instance có thể bị giữ đến khi exit hoặc lâu hơn khi method throw/task bị cancel. Dùng một token/ID vô hướng được phát sinh an toàn, hoặc lưu start time vào local variable của **lời gọi được instrument** khi thiết kế bytecode cho phép. Khi method exit, phát event nhỏ rồi giải phóng state của invocation.

### 12.2. Guard và helper lifecycle

Một reentrancy guard kiểu `ThreadLocal<Boolean>` có thể chặn helper tự gọi lại probe trên cùng thread, nhưng guard cũng phải `remove()` trong `finally`. Không đặt raw `Request` trong guard. Một boolean/enum có footprint thấp, nhưng nếu logic guard lưu Throwable hoặc full argument context thì lại tạo một nguồn retention mới.

### 12.3. Khi instrument async APIs

Một điểm đo quanh `CompletableFuture`/executor thường muốn đo thời gian “từ submit tới complete”. Nếu chỉ giữ request object để chờ callback, đó là thiết kế sai. Nên tạo **span/token** rất nhỏ, liên kết bằng ID hoặc context record không chứa domain objects, và xóa registration khi complete/timeout/cancel.

Nếu cần map pending operations, nó phải có **bounded entries, timeout, cleanup, và chống race** giữa complete/timeout/cancel. Một static `ConcurrentHashMap<UUID,Request>` không an toàn chỉ vì dùng concurrent data structure.

### 12.4. Tương tác với class loading

Java agent chạy dài hơn nhiều webapp class loaders. Không giữ `Class<?>`/`ClassLoader` từ callback `ClassFileTransformer.transform(...)` vào static metadata map vĩnh viễn trừ khi có chính sách lifecycle chắc chắn. Những cache này có thể ngăn class unloading qua nhiều đợt deploy.

Nếu cần metadata, dùng descriptors/định danh nhẹ và cache theo loader có cơ chế release, kiểm tra weak-key cycles. Cũng không lưu raw `ProtectionDomain` hoặc `Module` cùng với class loader vô hạn chỉ để chẩn đoán mỗi method invocation.

## 13. Checklist triển khai an toàn

### Trước khi ghi dữ liệu đo

- [ ] Điểm đo có thực sự cần arguments/return value/exception object không? Nếu không, **không truyền chúng**.
- [ ] Event schema có chỉ dùng primitive/metadata hữu hạn hoặc snapshot đã duyệt?
- [ ] Sampling/policy được quyết định trước mọi copy/serialization nặng?
- [ ] Kích thước/TTL/cardinality đều được giới hạn và có hành vi rõ khi vượt budget?
- [ ] Không có default `Object.toString()`/JSON serialize/Java Serialization trên object bất kỳ?
- [ ] Queue/async logger không giữ `Object[] args` hay `Supplier` capture request?
- [ ] Throwable/stack/context và các string nhạy cảm được xử lý theo data policy?

### Trong lúc xử lý request

- [ ] ThreadLocal, MDC, tracing scope được restore/remove trong `finally`?
- [ ] Nếu nested calls, context bên ngoài được khôi phục đúng?
- [ ] Nếu task nhảy sang thread khác, dữ liệu chuyển tiếp chỉ chứa metadata tối thiểu?
- [ ] Không tạo callback/lambda giữ request lâu hơn nhiệm vụ?
- [ ] Không giữ lock hoặc block thread ứng dụng chỉ để chờ exporter?
- [ ] Instrumentation giữ nguyên return value và exception semantics của ứng dụng?

### Sau khi kết thúc và khi ứng dụng undeploy

- [ ] Producer không còn references tới object gốc trong queued event?
- [ ] Consumer giải phóng batch/callback sau khi xuất hoặc drop?
- [ ] Cancellation/timeout/unregister được thực hiện ở đúng lifecycle?
- [ ] Cache metadata không pin `Class<?>`/classloader đã không còn dùng?
- [ ] Heap path không cho thấy static agent roots giữ request/session vượt request scope?
- [ ] Queue full/backpressure vẫn bounded theo retained memory, không chỉ số entries?
- [ ] Không lưu heap dump/trace chứa dữ liệu nhạy cảm ở nơi không được cấp phép?

## 14. Những hiểu nhầm cần tránh

1. **“Request đã return nên mọi request object đều có thể GC ngay.”** Sai nếu queue/callback/ThreadLocal còn strong reference.
2. **“Chỉ giữ một Object reference là rẻ.”** Một reference có thể giữ đồ thị object rất lớn.
3. **“Clone Object[] trước enqueue là snapshot độc lập.”** Sai, clone array là shallow; các element vẫn cùng object.
4. **“Queue bounded 1000 events chắc chắn bounded 1000 × vài chục byte.”** Sai nếu mỗi event giữ raw request.
5. **“Async log không làm chậm request thì cũng không giữ object.”** Sai; async event có thể giữ reference và format muộn.
6. **“Khi ThreadLocal key không còn, value chắc chắn được giải phóng ngay.”** Không được giả định vậy; quản lý lifecycle/remove rõ ràng.
7. **“ThreadLocal tự xóa sau mỗi HTTP request.”** Sai; nó gắn với thread, không mặc định gắn với request.
8. **“Executor task kết thúc thì callback đã được giải phóng ở mọi nơi.”** Không nhất thiết; registry/Future/listener/retry vẫn có thể giữ.
9. **“WeakHashMap đảm bảo không leak classloader.”** Sai nếu value giữ key hoặc loader qua đường khác.
10. **“WeakReference luôn trả object đủ lâu cho exporter.”** Sai; GC có thể clear nó trước lúc dùng.
11. **“System.gc() rồi weakRef không null chứng minh có leak.”** Sai; không bảo đảm GC chạy/sẵn sàng collect.
12. **“Class<?> chỉ là metadata nhỏ, giữ vô hạn không sao.”** Nó có quan hệ tới class definition/defining loader.
13. **“Hash user ID thì chắc chắn ẩn danh.”** Sai; các ID ít entropy có thể dò ngược và vẫn gây cardinality.
14. **“Snapshot là serialize mọi field rồi cắt 256 byte.”** Sai; trước khi cắt đã duyệt graph và tốn bộ nhớ/CPU, có thể chạy user code.
15. **“Exporter đã gửi xong nghĩa là mọi reference đã được xóa.”** Cần kiểm batch, retry buffers, callbacks và caches.
16. **“Mọi object sống lâu đều là leak.”** Không: phải đối chiếu lifetime hợp lệ và root path.
17. **“GC.class_histogram chỉ ra code giữ request.”** Không; cần heap graph/path to GC roots.
18. **“Instrumentation không chỉnh class fields thì không thể gây memory leak.”** Sai; chính static fields của helper có thể giữ app objects.
19. **“Cần giữ exception object để biết có lỗi.”** Thường chỉ cần outcome code hoặc classification đã duyệt.
20. **“Cứ thêm timeout là xong.”** Timeout hữu ích, nhưng object vẫn có thể bị giữ trong queue/callback mà cleanup không xóa.

## 15. Câu hỏi tự kiểm tra

1. **Điều kiện quan trọng khiến GC chưa thể reclaim một request object?** Còn đường strong reference từ GC root đến object.
2. **Vì sao `static Queue<Object[]>` nguy hiểm?** Giữ trực tiếp references tới mọi argument và graph liên quan; queue có thể sống lâu hơn request.
3. **`arguments.clone()` giải quyết object retention không?** Không, clone mảng là shallow copy.
4. **Vì sao event chỉ có `methodId,durationNanos,outcomeCode` phù hợp hơn?** Không cần tham chiếu tới domain objects và có schema nhỏ, ổn định.
5. **Bị drop một event khi queue đầy có phải lỗi đo đạc âm thầm?** Không nếu được thiết kế là policy có counter/trạng thái rõ; phải phân biệt drop với export success.
6. **ThreadLocal giữ giá trị theo request hay thread?** Theo thread; phải cleanup ở ranh giới task/request.
7. **Vì sao `remove()` đặt trong `finally`?** Để xóa context cả khi business code ném exception.
8. **Vì sao nested scope đôi khi cần restore previous value?** Một scope con kết thúc không được vô tình xóa context hợp lệ của scope cha.
9. **`CompletableFuture` có thể giữ request bằng cách nào?** Callback/lambda hoặc pipeline stage capture request trong closure.
10. **Tại sao một event chứa `Throwable` có thể giữ nhiều dữ liệu?** Object Throwable, cause/suppressed/custom fields và classloader có thể nằm trong graph reachable.
11. **Lưu `Class<?>` trong agent static map có thể gây gì?** Giữ class/defining loader của app, cản class unloading.
12. **`WeakHashMap` có hoàn toàn giải quyết vấn đề không?** Không nếu value giữ key trực tiếp hoặc gián tiếp.
13. **`WeakReference.get()==null` có đảm bảo exporter luôn lấy được payload không?** Không, ngược lại có thể đã mất referent.
14. **Tại sao không nên dựa vào `System.gc()` để assert đối tượng thu gom?** GC timing không tất định.
15. **Một bounded queue chứa Request lớn có thật sự bounded retained bytes không?** Không theo một giới hạn chặt nếu graph size thay đổi vô hạn.
16. **Điều gì trong demo làm `STALE_CONTEXT_SEEN=true`?** Một task quên remove ThreadLocal, task sau chạy trên cùng worker thread.
17. **Điều gì làm `AFTER_FINALLY_CLEAN=true`?** Task đã remove context trong finally trên đúng thread.
18. **Tại sao event được exporter giữ lâu hơn request vẫn có thể chấp nhận?** Nếu event chỉ chứa snapshot được phép, giới hạn và không pin object ứng dụng.
19. **Bước đầu khi nghi ngờ leak do agent là gì?** Xác định reference graph/GC roots và so vòng đời thực tế, không chỉ quan sát heap tăng.
20. **Khi business cần payload chi tiết nhưng privacy/retention không cho phép, nên làm gì?** Bỏ feature hoặc thiết kế API capture chuyên biệt được phê duyệt; không tự giữ toàn graph.

## 16. Tài liệu tham khảo chính thức

- [Java SE 21 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html): từng thread giữ bản giá trị riêng và `remove()`, lifecycle theo thread.
- [Java SE 21 — `java.lang.ref`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/package-summary.html): strongly/softly/weakly/phantom reachable và reference queues.
- [Java SE 21 — `WeakReference`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/WeakReference.html): weak reference và clearing behavior.
- [Java SE 21 — `WeakHashMap`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/WeakHashMap.html): weak keys nhưng strong values, cảnh báo value giữ lại key.
- [Java SE 21 — `ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): queue có capacity và `offer`/`put`.
- [Java SE 21 — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): task execution, shutdown và lifecycle.
- [Java SE 21 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): asynchronous stages và callbacks.
- [Java SE 21 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent lifecycle và instrumentation entrypoints.
- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer callbacks, class loaders và phạm vi transformation.
- [Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `GC.class_histogram`, `GC.heap_dump` và tác động vận hành.
- [Java SE 21 — `Object`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html): `toString` và hợp đồng của object methods.
- [Oracle Java SE Core Libraries Developer Guide](https://docs.oracle.com/en/java/javase/21/core/java-core-libraries-developer-guide.pdf): mô tả rủi ro ThreadLocal sống quá scope và cleanup trong thread pools.

**Kết luận:** để đo hiệu năng mà không đổi vòng đời ứng dụng, **đừng để event/queue/ThreadLocal/callback/cache của agent giữ `Request`, `Object[] args`, `Throwable`, `Class<?>` hay graph của ứng dụng lâu hơn nhu cầu**. Hãy đưa vào pipeline một **snapshot tối thiểu, đã duyệt, có budget và không tham chiếu về object gốc**, cleanup ở đúng lifecycle, theo dõi retained heap và kiểm tra đường tới GC roots. Một phép đo tốt không chỉ đúng số liệu mà còn **trả lại quyền thu gom dữ liệu cho ứng dụng ngay khi nó hết cần dùng**.