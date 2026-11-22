# Chi phí bộ nhớ khi mỗi virtual thread giữ một bản sao dữ liệu

Virtual thread giúp tạo nhiều tác vụ đồng thời với chi phí luồng thấp hơn platform thread, nhưng không làm cho mỗi tác vụ trở nên miễn phí về bộ nhớ. Mỗi virtual thread vẫn cần đối tượng thread, trạng thái thực thi, stack chunks trên heap và các dữ liệu mà tác vụ giữ lại. Nếu mỗi virtual thread còn lưu một bản sao lớn của request context, buffer hoặc dữ liệu nghiệp vụ trong `ThreadLocal`, mức dùng heap có thể tăng gần theo số virtual thread đang giữ dữ liệu đó.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), cần phân biệt một slot `ThreadLocal` riêng với một bản sao độc lập của object được lưu trong slot. Mỗi thread có vùng ánh xạ ThreadLocal riêng, nhưng nhiều thread có thể cùng giữ tham chiếu đến một object dùng chung. Bộ nhớ tăng mạnh khi ứng dụng thực sự tạo bản sao hoặc tạo object graph mới cho từng virtual thread.

## Virtual thread nhẹ hơn platform thread nhưng vẫn dùng bộ nhớ

Platform thread thường gắn với một OS thread và có stack native tương ứng. Virtual thread do JVM quản lý, có stack được lưu thành các heap stack chunks và có thể được mount lên carrier khi chạy rồi unmount khi chờ. Vì không cần một OS thread riêng cho mỗi virtual thread, ứng dụng có thể quản lý số lượng tác vụ đồng thời lớn hơn.

Tuy nhiên, mỗi virtual thread vẫn cần bộ nhớ cho:

- Đối tượng `Thread` và trạng thái lập lịch, interruption, tên, ID.
- Stack chunks chứa trạng thái thực thi khi virtual thread chạy hoặc tạm dừng.
- Các tham chiếu và dữ liệu mà tác vụ đang giữ trong local variables, closure hoặc context.
- Các cấu trúc `ThreadLocal`/`InheritableThreadLocal` đã được sử dụng bởi thread đó.
- Những object được giữ gián tiếp qua các giá trị ThreadLocal, chẳng hạn map, buffer, request metadata hoặc object graph lớn.

Vì vậy, giảm số OS thread không đồng nghĩa với việc heap không tăng khi số virtual thread tăng. Nếu mỗi tác vụ giữ nhiều dữ liệu trong suốt thời gian chờ I/O, các object đó vẫn là live objects và chưa thể được garbage collector thu hồi.

## ThreadLocal tạo vùng giá trị riêng cho từng thread

`ThreadLocal<T>` cho phép mỗi thread có một giá trị riêng gắn với cùng một đối tượng `ThreadLocal`. Khi một thread gọi `set()` hoặc lần đầu gọi `get()` với `withInitial()`, giá trị được lưu trong vùng ThreadLocal của thread đó.

```java
private static final ThreadLocal<byte[]> BUFFER =
        ThreadLocal.withInitial(() -> new byte[1024 * 1024]);

static void process() {
    byte[] buffer = BUFFER.get();
    useBuffer(buffer);
}
```

Mỗi thread lần đầu gọi `BUFFER.get()` sẽ nhận một mảng 1 MiB riêng do initializer tạo ra. Nếu 10.000 virtual thread cùng gọi `process()` và đồng thời giữ giá trị này, riêng các mảng có thể chiếm khoảng 10.000 MiB, tương đương gần 9,77 GiB, chưa tính đối tượng thread, stack chunks, bảng ThreadLocal và các dữ liệu khác.

`ThreadLocal.withInitial()` khởi tạo giá trị khi thread lần đầu gọi `get()`, không phải ngay khi tạo thread. Do đó, virtual thread không truy cập `BUFFER` sẽ không tạo mảng này. Chi phí thực tế phụ thuộc vào số thread đã truy cập, số ThreadLocal được dùng trên mỗi thread, kích thước object graph và thời gian các giá trị còn được giữ.

Một cách ước lượng sơ bộ cho phần dữ liệu riêng là:

\[
M_{values} \approx N_{threads} \times S_{per\ thread}
\]

Trong đó `S_per thread` gồm giá trị ThreadLocal và object graph chỉ thuộc về thread đó. Đây không phải công thức tính chính xác heap: còn có header, alignment, bảng map, stack chunks, dữ liệu dùng chung và chi phí GC.

## Một ThreadLocal riêng không đồng nghĩa với một bản sao object

Điểm quan trọng nhất khi đánh giá bộ nhớ là phân biệt tham chiếu với object được tham chiếu.

```java
private static final RequestPolicy POLICY = loadImmutablePolicy();
private static final ThreadLocal<RequestPolicy> CURRENT_POLICY =
        ThreadLocal.withInitial(() -> POLICY);
```

Mỗi thread có một entry riêng trong ThreadLocal map, nhưng initializer trả về cùng tham chiếu `POLICY`. Nếu object đó thực sự immutable và có thể chia sẻ an toàn, payload lớn của policy không bị nhân bản cho từng thread. Vẫn có chi phí entry và tham chiếu trên mỗi thread, nhưng không phải toàn bộ object graph được sao chép.

Ngược lại, nếu initializer tạo object mới hoặc mã gọi `new RequestContext(...)`, `new HashMap<>(...)`, `clone()` hay deep copy cho từng virtual thread, mỗi thread có thể giữ một bản sao riêng. Khi đó, bộ nhớ tăng theo số bản sao đang sống.

| Cách lưu dữ liệu | Hành vi bộ nhớ thường gặp |
| --- | --- |
| Mỗi thread giữ một tham chiếu đến cùng object immutable | Có entry theo thread; payload object có thể được chia sẻ |
| Mỗi thread tạo một object nhỏ riêng | Có object riêng cho từng thread |
| Mỗi thread deep-copy một object graph lớn | Payload có thể tăng gần tuyến tính theo số thread |
| Nhiều ThreadLocal cùng được truy cập trên mỗi thread | Số entry và giá trị được giữ tăng theo số cặp thread/ThreadLocal |

Không nên dùng chung object mutable chỉ để tiết kiệm heap nếu nhiều thread có thể sửa nó đồng thời. Chia sẻ dữ liệu cần có tính bất biến hoặc cơ chế đồng bộ hóa phù hợp. Tiết kiệm bộ nhớ không được đánh đổi tính đúng đắn của dữ liệu.

## InheritableThreadLocal có thể truyền tham chiếu, không tự deep-copy

Virtual thread mặc định kế thừa các giá trị `InheritableThreadLocal` từ thread tạo nó. Cần lưu ý: hành vi mặc định của `InheritableThreadLocal.childValue(parentValue)` trả lại chính `parentValue`. Điều đó có nghĩa thread con nhận một tham chiếu đến cùng object, không tự động tạo bản sao độc lập.

```java
import java.util.HashMap;
import java.util.Map;

private static final InheritableThreadLocal<Map<String, String>> CONTEXT =
        new InheritableThreadLocal<>();

static void startChild() throws InterruptedException {
    Map<String, String> parentContext = new HashMap<>();
    parentContext.put("tenant", "tenant-a");
    CONTEXT.set(parentContext);

    Thread child = Thread.ofVirtual().start(() -> {
        Map<String, String> inherited = CONTEXT.get();
        System.out.println(inherited.get("tenant"));
    });

    child.join();
    CONTEXT.remove();
}
```

Trong ví dụ, giá trị map được kế thừa theo tham chiếu. Nếu thread cha và thread con cùng sửa map, chúng có thể quan sát thay đổi của nhau và phát sinh race condition. Nếu override `childValue()` để sao chép map hoặc object graph, mỗi lần tạo thread con có thể phát sinh allocation và tăng bộ nhớ theo số thread.

Thread builder cho phép tắt kế thừa khi không cần truyền context:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

ThreadFactory factory = Thread.ofVirtual()
        .inheritInheritableThreadLocals(false)
        .factory();

try (var executor = Executors.newThreadPerTaskExecutor(factory)) {
    executor.submit(() -> processWithoutInheritedContext());
}
```

Mặc định của builder là kế thừa inheritable thread locals. Chỉ tắt khi ứng dụng đã có cách truyền context cần thiết qua tham số hoặc cơ chế khác; nếu tắt tùy tiện, thông tin như security context hoặc trace context có thể không còn sẵn trong tác vụ con.

## Thời gian sống của ThreadLocal value ảnh hưởng peak heap

Giá trị ThreadLocal được giữ trong suốt thời gian thread còn giữ entry đó. Nếu một virtual thread chờ network trong vài giây và trong thời gian đó giữ một buffer 20 MiB, buffer vẫn là live object trong suốt thời gian chờ. Khi hàng nghìn tác vụ cùng chờ, các buffer có thể tạo ra peak heap rất lớn dù CPU không bận.

Với virtual thread theo mô hình một thread cho mỗi task, thread thường kết thúc khi task hoàn tất. Khi thread kết thúc và không còn tham chiếu giữ nó hoặc dữ liệu của nó, các giá trị gắn với thread có thể trở nên eligible for garbage collection. Tuy nhiên, không nên dựa vào việc thu hồi xảy ra ngay lập tức: GC hoạt động theo chu kỳ và dữ liệu có thể còn được giữ bởi tham chiếu khác.

`ThreadLocal.remove()` xóa giá trị của thread hiện tại khỏi ThreadLocal đó. Dùng `remove()` khi context hoặc buffer không còn cần thiết, nhất là trong tác vụ dài hoặc khi cùng thread tiếp tục xử lý nhiều đơn vị công việc. Với virtual thread chuyên biệt cho một task, việc thread kết thúc cũng kết thúc vòng đời của map, nhưng `remove()` vẫn hữu ích để giải phóng sớm dữ liệu lớn trước khi task hoàn toàn kết thúc.

```java
private static final ThreadLocal<RequestContext> CURRENT = new ThreadLocal<>();

static void handle(RequestContext context) {
    CURRENT.set(context);
    try {
        callBusinessLogic();
    } finally {
        CURRENT.remove();
    }
}
```

Không nhầm hành vi này với platform thread pool. Trong pool, một platform thread được tái sử dụng cho nhiều task; nếu không gọi `remove()`, context của task trước có thể còn hiện diện khi thread chạy task sau. Virtual thread thường không được tái sử dụng cho task tiếp theo, nhưng dữ liệu lớn vẫn chiếm heap trong suốt vòng đời của virtual thread.

## Không dùng ThreadLocal để tạo một pool tài nguyên cho mỗi virtual thread

Một anti-pattern là khởi tạo tài nguyên nặng trong ThreadLocal với giả định mỗi thread sẽ được tái sử dụng lâu dài:

```java
private static final ThreadLocal<DatabaseConnection> CONNECTION =
        ThreadLocal.withInitial(Database::openConnection);
```

Nếu mỗi request chạy trên một virtual thread, mỗi thread có thể mở một connection riêng khi lần đầu truy cập. Một lượng lớn request đồng thời có thể tạo quá nhiều kết nối, vượt giới hạn database. Virtual thread không phải connection pool.

Với tài nguyên có giới hạn như database connection, HTTP connection hoặc client session, hãy dùng pool hoặc semaphore được thiết kế để quản lý số lượng tài nguyên. Mỗi task lấy tài nguyên trong phạm vi cần thiết rồi trả lại bằng `try-with-resources` hoặc API tương ứng. Không giữ connection trong ThreadLocal chỉ để tránh truyền tham số.

Tương tự, tránh cấp một buffer lớn cho mọi virtual thread nếu buffer chỉ cần trong một đoạn ngắn. Có thể dùng buffer nhỏ hơn, tái sử dụng theo cơ chế pool có giới hạn, hoặc xử lý dữ liệu theo chunk để giảm peak heap. Pool cần có giới hạn và chính sách back-pressure; nếu không, nó chỉ chuyển nơi tích tụ bộ nhớ.

## Ưu tiên truyền context tường minh khi có thể

Nếu một phương thức cần request context để làm việc, truyền context qua tham số thường giúp nhìn rõ dependency và vòng đời dữ liệu:

```java
record RequestContext(String requestId, String tenantId) {}

static void handle(RequestContext context) {
    validateTenant(context.tenantId());
    processRequest(context.requestId());
}
```

Khi submit task, có thể truyền cùng một context immutable cho tác vụ nếu nó được chia sẻ an toàn:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

static void submit(String requestId, String tenantId) throws Exception {
    RequestContext context = new RequestContext(requestId, tenantId);

    try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
        Future<?> task = executor.submit(() -> handle(context));
        task.get();
    }
}
```

Việc truyền tham số không tự sao chép object. Nếu context immutable, nhiều task có thể dùng chung tham chiếu và tránh tạo bản sao không cần thiết. Nếu mỗi task cần dữ liệu mutable độc lập, hãy tạo bản sao có chủ đích và tính trước chi phí của nó.

ThreadLocal vẫn có chỗ dùng khi cần tích hợp với API đồng bộ hiện hữu hoặc framework dựa trên thread context. Tuy nhiên, chỉ nên giữ dữ liệu nhỏ, cần thiết trong phạm vi task và có quy tắc cleanup rõ ràng.

## Đo bộ nhớ thay vì đoán từ số virtual thread

Để xác định ThreadLocal có đang tạo áp lực heap hay không, hãy đo trong tải đại diện:

1. Ghi nhận số virtual thread đồng thời và số task thực sự truy cập từng ThreadLocal.
2. Dùng Java Flight Recorder với allocation profiling để tìm nơi tạo buffer, context hoặc object graph lớn.
3. Chụp heap dump khi heap đang cao và xem dominator tree/retained size để xác định object nào giữ dữ liệu.
4. Kiểm tra đường tham chiếu từ thread, ThreadLocal value hoặc closure tới object lớn.
5. So sánh peak heap, allocation rate, GC frequency và latency trước/sau khi bỏ bản sao hoặc rút ngắn thời gian giữ dữ liệu.
6. Thử ở nhiều mức concurrency; một giá trị nhỏ trên một task có thể trở thành vấn đề lớn khi nhân lên hàng nghìn task.

Không dùng số lượng OS thread làm đại diện cho số virtual thread hoặc số bản sao dữ liệu. Cũng không kết luận ThreadLocal là nguyên nhân chỉ vì heap tăng; cần kiểm tra object allocation và retained size để tìm đúng nguồn giữ bộ nhớ.

## Phân biệt với ScopedValue trong Java 21

Java 21 có Scoped Values ở trạng thái preview (JEP 446). API này hướng tới truyền dữ liệu bất biến theo phạm vi thực thi và có thể phù hợp với một số trường hợp context chỉ đọc. Tuy nhiên, trong phạm vi Java 21, đây vẫn là preview feature, cần bật `--enable-preview` và không nên trình bày như API ổn định mặc định cho production.

Với mã Java 21 không dùng preview, có thể truyền context tường minh qua tham số hoặc dùng `ThreadLocal` với giá trị nhỏ, phạm vi rõ và cleanup phù hợp. Nếu chủ động thử Scoped Values, cần đánh giá trạng thái preview, khả năng tương thích JDK và kế hoạch nâng cấp riêng.

## Quy trình kiểm soát bộ nhớ cho virtual thread

1. **Ước lượng concurrency thực tế.** Xác định số virtual thread có thể cùng sống và thời gian mỗi task giữ dữ liệu.
2. **Kiểm kê ThreadLocal.** Liệt kê các giá trị được tạo bởi `withInitial()`, `set()` và `InheritableThreadLocal`; xác định kích thước và vòng đời của chúng.
3. **Phân biệt tham chiếu và bản sao.** Kiểm tra initializer hoặc `childValue()` có tạo object mới/deep copy hay chỉ trả lại tham chiếu dùng chung.
4. **Giảm dữ liệu theo thread.** Chỉ lưu request ID hoặc context tối thiểu; truyền object immutable dùng chung khi an toàn.
5. **Dọn dẹp đúng thời điểm.** Dùng `remove()` sau phạm vi sử dụng nếu dữ liệu không cần giữ đến cuối thread.
6. **Giới hạn tài nguyên nặng.** Dùng connection pool, semaphore hoặc pool có giới hạn thay cho một resource trong mỗi ThreadLocal.
7. **Kiểm soát kế thừa.** Chỉ truyền `InheritableThreadLocal` khi cần; cân nhắc `inheritInheritableThreadLocals(false)` nếu context được truyền theo cách khác.
8. **Đo lại dưới tải.** Dùng JFR, heap dump và load test để xác nhận peak heap, allocation rate và latency cải thiện.

Virtual thread giúp giảm chi phí quản lý OS thread, nhưng dữ liệu mà mỗi task giữ vẫn tiêu tốn heap. Nếu mỗi virtual thread tạo một bản sao context hoặc buffer lớn, tổng bộ nhớ có thể tăng theo số task đồng thời. Hãy phân biệt entry ThreadLocal với object được tham chiếu, tránh deep-copy không cần thiết, giới hạn vòng đời dữ liệu và đo retained heap trên tải thực tế.
