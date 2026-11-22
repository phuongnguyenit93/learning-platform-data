# Lazy initialization và thời điểm lỗi được bộc lộ

## 1. Vì sao thời điểm tạo dependency ảnh hưởng đến độ tin cậy?

Trong **Dependency Injection (DI)**, một lớp nhận những đối tượng cần dùng từ bên ngoài thay vì tự khởi tạo chúng. Đây là một cách thực hiện **Inversion of Control (IoC)**: composition root quyết định cách tạo, cấu hình và lắp ghép các đối tượng. **Constructor injection** khiến dependency bắt buộc hiện diện rõ trong chữ ký constructor, nhưng nó **không bắt buộc mọi dependency phải được khởi tạo ngay khi ứng dụng bắt đầu**.

Ví dụ, `ReportService` cần một `ReportSource` để lấy dữ liệu báo cáo. Nếu composition root tạo `RemoteReportSource` ngay lúc khởi động, các lỗi trong quá trình tạo nguồn dữ liệu có cơ hội xuất hiện **trước khi ứng dụng nhận việc**. Nếu root truyền một **provider/factory** và chỉ tạo `RemoteReportSource` ở lần truy cập đầu tiên, lỗi tương tự có thể chỉ xuất hiện **khi một yêu cầu thật đi qua chức năng đó**.

Khác biệt này được gọi là **eager initialization** (khởi tạo sớm) và **lazy initialization** (khởi tạo trì hoãn). Lazy là quyết định về *thời điểm khởi tạo*, còn DI là quyết định về *ai cung cấp phụ thuộc*. Chúng có thể phối hợp với nhau nhưng không đồng nghĩa.

Sau bài này, bạn có thể:

- Phân biệt khởi tạo eager, lazy một lần và tạo instance mới cho mỗi lần gọi provider.
- Giải thích khi nào lỗi cấu hình/khởi tạo được bộc lộ ở startup, ở lần dùng đầu hoặc ở một request về sau.
- Thiết kế factory/provider tường minh bằng Java thuần và giữ application service độc lập với chi tiết tạo dependency.
- Kiểm thử số lần tạo, thời điểm lỗi, chính sách retry và thao tác `close()` của dependency được khởi tạo trễ.
- Đánh giá các rủi ro về concurrency, scope, ownership và điều kiện sẵn sàng của ứng dụng trước khi mở rộng sang DI container.

## 2. Eager và lazy trong cùng một đồ thị phụ thuộc

Giả sử đồ thị của ứng dụng cần một nguồn báo cáo:

```text
ReportController
       |
       v
  ReportService
       |
       v
   ReportSource <------- RemoteReportSource
   (hợp đồng)            (adapter cụ thể)
```

Hai cách lắp ghép đều có thể sử dụng constructor injection:

**Eager:** composition root tạo `RemoteReportSource`, sau đó truyền instance đã tạo vào `ReportService`.

```java
// Pseudocode: các type cụ thể chưa được khai báo ở đây.
RemoteReportSource source = new RemoteReportSource(config);
ReportService service = new ReportService(source);
```

**Lazy:** composition root tạo một đối tượng trì hoãn hoặc provider. Service vẫn nhận `ReportSource`, nhưng implementation bên trong chỉ tạo adapter từ xa khi thật sự cần.

```java
// Pseudocode: LazyReportSource đóng vai trò ReportSource.
ReportSource source = new LazyReportSource(
        () -> new RemoteReportSource(config));
ReportService service = new ReportService(source);
```

Cả hai ví dụ đều chuyển quyền chọn implementation về **composition root**. Sự khác biệt là cách root **định thời điểm tạo** adapter tốn kém hoặc dễ gặp lỗi.

### 2.1. Dòng thời gian của lỗi

```text
EAGER
  startup ---- create source ---- READY ---- request ---- use source
                  |
                  +-- lỗi khởi tạo: có thể chặn READY

LAZY
  startup ---- create provider ---- READY ---- request ---- first get()
                                            |
                                            +-- lỗi khởi tạo: request gặp lỗi

LAZY ĐƯỢC WARM-UP
  startup ---- create provider ---- warmUp() ---- READY ---- request
                                      |
                                      +-- lỗi warm-up: có thể chặn READY
```

**Điểm mấu chốt:** lazy có thể **dời thời điểm bộc lộ lỗi**, chứ không loại bỏ lỗi. Một ứng dụng có thể khởi động thành công, báo sẵn sàng, nhưng chức năng ít được gọi lại hỏng ở lần sử dụng đầu vì token sai, DNS không truy cập được hoặc thiếu cấu hình.

Ngược lại, eager cũng **không bảo đảm mọi lỗi sẽ được tìm thấy ở startup**. Constructor có thể không kiểm tra kết nối thực, credential có thể hết hạn sau đó, và mọi lời gọi mạng vẫn có thể thất bại trong lúc phục vụ. Muốn phát hiện vấn đề trước READY phải có **readiness check thực sự kiểm chứng điều kiện quan trọng**, không chỉ dựa vào việc gọi `new`.

## 3. Phân biệt thời điểm tạo, số lượng instance và phạm vi dùng chung

Ba thuộc tính dễ bị nhập nhằng:

| Câu hỏi | Ví dụ quyết định |
| --- | --- |
| **Tạo lúc nào?** | Khi bootstrap, ở lần truy cập đầu tiên, hoặc mỗi khi request bắt đầu. |
| **Tạo bao nhiêu instance?** | Một instance được cache, một instance mỗi lần gọi, hoặc một instance theo mỗi scope. |
| **Instance sống trong bao lâu?** | Suốt ứng dụng, trong một request/task hoặc tới khi phiên kết thúc. |

`Supplier<T>` trong Java đơn thuần là hợp đồng **trả về một giá trị khi gọi `get()`**. Nó không tự cam kết lazy singleton, không tự cache và không tự close tài nguyên.

```java
// Chỉ mang ý nghĩa tạo mới mỗi lần get() được gọi:
java.util.function.Supplier<Worker> factory = Worker::new;

// Chỉ mang ý nghĩa luôn trả về một instance đã có:
Worker shared = new Worker();
java.util.function.Supplier<Worker> provider = () -> shared;
```

Đoạn trên chỉ minh họa semantics; `Worker` là lớp giả định. Để có **lazy một lần**, phải thiết kế thêm cơ chế lưu instance và chính sách đồng thời. Một container có thể cung cấp những scope tương tự, nhưng ý nghĩa chính xác của `Provider.get()`, `@Lazy`, singleton và prototype phụ thuộc framework/cấu hình cụ thể.

### 3.1. Bảng so sánh

| Cách tạo | Thời điểm thực hiện công việc khởi tạo | Số lần tạo thường gặp | Nơi lỗi constructor xuất hiện |
| --- | --- | --- | --- |
| Eager ở composition root | Trước khi ứng dụng sẵn sàng. | Một lần cho instance root tạo, hoặc theo cấu hình. | Khi bootstrap. |
| Lazy cache một instance | Lần truy cập đầu tiên cần giá trị. | Một lần nếu thành công và có cache. | Lần truy cập đầu tiên. |
| Factory tạo mới | Mỗi lần factory được gọi. | Mỗi lần gọi, trừ khi factory tự quản lý cache. | Bất kỳ lần gọi nào. |
| Request-scoped provider | Lúc cần trong request, có thể tái sử dụng trong cùng request. | Một instance cho từng request nếu contract quy định. | Trong request nơi nó được tạo. |
| Lazy được warm-up trước READY | Khi gọi warm-up trong bootstrap. | Thường một lần nếu cache thành công. | Khi warm-up, trước READY. |

Tạo *mỗi lần gọi* chưa chắc là request scope; một request có thể gọi provider nhiều lần. Nếu muốn cùng request sử dụng cùng instance, cơ chế caching phải gắn với danh tính và vòng đời của request đó.

## 4. Ví dụ chạy được: factory, lazy decorator và Service giữ nguyên constructor

Ta xây một chương trình không cần DI container. `ReportService` luôn nhận `ReportSource` qua constructor. Composition root sẽ thử cả eager và lazy bằng adapter theo dõi sự kiện.

Để tập trung vào thời điểm tạo, `TrackedReportSource` chỉ giả lập việc mở nguồn dữ liệu. Nó không thực hiện HTTP hoặc database thật. Một `LazyReportSource` **triển khai cùng hợp đồng nghiệp vụ**, giữ factory và khởi tạo adapter vào lần `load` đầu tiên.

Đặt mã sau trong `LazyInitializationDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Supplier;

// Hợp đồng mà service sử dụng.
interface ReportSource {
    String load(String reportId);
}

// Adapter mô phỏng tài nguyên tốn kém, có thể đóng.
final class TrackedReportSource implements ReportSource, AutoCloseable {
    private final List<String> events;
    private boolean closed;

    TrackedReportSource(List<String> events, boolean failToCreate) {
        this.events = Objects.requireNonNull(events, "events");
        events.add("source:create");

        if (failToCreate) {
            events.add("source:failed");
            // Ví dụ giả định chưa cấp phát tài nguyên trước khi ném lỗi.
            throw new IllegalStateException("Không khởi tạo được source");
        }

        events.add("source:ready");
    }

    @Override
    public String load(String reportId) {
        if (closed) {
            throw new IllegalStateException("Source đã đóng");
        }
        events.add("source:load:" + reportId);
        return "data:" + reportId;
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            events.add("source:close");
        }
    }
}

// Một lazy decorator: tạo và cache source khi được sử dụng lần đầu.
// Mã này dành cho ví dụ chạy TUẦN TỰ, chưa thread-safe.
final class LazyReportSource implements ReportSource, AutoCloseable {
    private final Supplier<TrackedReportSource> factory;
    private TrackedReportSource instance;
    private boolean closed;

    LazyReportSource(Supplier<TrackedReportSource> factory) {
        this.factory = Objects.requireNonNull(factory, "factory");
    }

    private TrackedReportSource getOrCreate() {
        if (closed) {
            throw new IllegalStateException("Lazy source đã đóng");
        }
        if (instance == null) {
            instance = Objects.requireNonNull(
                    factory.get(), "Factory trả về null");
        }
        return instance;
    }

    // Có thể dùng khi cần kiểm tra sẵn sàng trước khi phục vụ.
    void warmUp() {
        getOrCreate();
    }

    @Override
    public String load(String reportId) {
        return getOrCreate().load(reportId);
    }

    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        if (instance != null) {
            instance.close();
        }
    }
}

// Không biết dependency được tạo eager hay lazy.
final class ReportService {
    private final ReportSource source;

    ReportService(ReportSource source) {
        this.source = Objects.requireNonNull(source, "source");
    }

    String export(String reportId) {
        if (reportId == null || reportId.trim().isEmpty()) {
            throw new IllegalArgumentException("Mã báo cáo không hợp lệ");
        }
        return "EXPORT[" + source.load(reportId) + "]";
    }
}

public class LazyInitializationDemo {
    public static void main(String[] args) {
        List<String> eagerEvents = new ArrayList<>();

        // EAGER: adapter được tạo trước khi công bố app sẵn sàng.
        try (TrackedReportSource source =
                     new TrackedReportSource(eagerEvents, false)) {
            ReportService service = new ReportService(source);
            eagerEvents.add("app:ready");
            eagerEvents.add(service.export("E1"));
        }
        System.out.println("EAGER = " + eagerEvents);

        List<String> lazyEvents = new ArrayList<>();

        // LAZY: tạo wrapper trước, adapter thật chưa được tạo.
        try (LazyReportSource source = new LazyReportSource(
                () -> new TrackedReportSource(lazyEvents, false))) {
            ReportService service = new ReportService(source);
            lazyEvents.add("app:ready");
            lazyEvents.add(service.export("L1"));
            lazyEvents.add(service.export("L2"));
        }
        System.out.println("LAZY  = " + lazyEvents);
    }
}
```

Biên dịch và chạy:

```bash
javac LazyInitializationDemo.java
java LazyInitializationDemo
```

Kết quả dự kiến (thứ tự sự kiện là phần cần quan sát):

```text
EAGER = [source:create, source:ready, app:ready, source:load:E1, EXPORT[data:E1], source:close]
LAZY  = [app:ready, source:create, source:ready, source:load:L1, EXPORT[data:L1], source:load:L2, EXPORT[data:L2], source:close]
```

### 4.1. Những gì ví dụ chứng minh

- Với **eager**, `source:create` xuất hiện trước `app:ready`; lỗi phát sinh trong constructor của source sẽ ngăn đi đến bước READY của ví dụ.
- Với **lazy**, `app:ready` xuất hiện trước `source:create`. Khi chỉ tạo `LazyReportSource`, source thật chưa được tạo.
- Hai lần `export` trong nhánh lazy chỉ xuất hiện **một** sự kiện `source:create`. `LazyReportSource` cache instance sau lần khởi tạo thành công.
- `ReportService` không thay đổi; dependency của nó vẫn là `ReportSource`. Cách khởi tạo được quyết định ở **composition root**, đúng tinh thần DI/IoC.
- `LazyReportSource` là chủ sở hữu của adapter do factory tạo; khi wrapper được đóng, adapter được đóng nếu nó đã được tạo. Nhánh eager lại do root sở hữu trực tiếp thông qua `try-with-resources`.

**Giới hạn:** đoạn `getOrCreate` và `close` dùng trường mutable mà không đồng bộ; ví dụ chỉ an toàn khi thao tác **tuần tự**. Không được inject nguyên implementation này làm singleton phục vụ request đồng thời trong web server.

### 4.2. Lazy không đồng nghĩa với chuyển quyền tạo vào service

Một anti-pattern là để `ReportService` tự chọn adapter cụ thể:

```java
// Mã minh họa cần tránh nếu muốn giữ DI tường minh:
final class HiddenCreationReportService {
    private ReportSource source;

    String export(String id) {
        if (source == null) {
            source = new RemoteReportSource(); // Chi tiết hạ tầng nằm trong service.
        }
        return source.load(id);
    }
}
```

`RemoteReportSource` ở đây là lớp giả định. Dù việc tạo diễn ra trễ, `HiddenCreationReportService` vẫn chịu trách nhiệm chọn implementation và quản lý khởi tạo. **Lazy initialization không tự tạo ra DI.** Chuyển lựa chọn về composition root, inject factory hoặc wrapper phù hợp rồi quản lý ownership rõ ràng.

## 5. Kiểm thử thời điểm lỗi: startup và lần sử dụng đầu

Điểm khác biệt quan trọng nhất không phải số dòng code mà là **vị trí xuất hiện lỗi quan sát được**. Lưu bài kiểm thử Java thuần sau vào `LazyInitializationTest.java`, cùng thư mục với file demo.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class LazyInitializationTest {
    static void assertEvents(
            List<String> actual, String... expected) {
        List<String> expectedList = Arrays.asList(expected);
        if (!expectedList.equals(actual)) {
            throw new AssertionError(
                    "Expected: " + expectedList + ", actual: " + actual);
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        // EAGER: lỗi khởi tạo xảy ra ngay ở bootstrap.
        List<String> eagerFailed = new ArrayList<>();
        boolean startupRejected = false;
        try {
            new TrackedReportSource(eagerFailed, true);
        } catch (IllegalStateException expected) {
            startupRejected = true;
        }
        check(startupRejected, "Eager phải báo lỗi khi tạo source");
        assertEvents(eagerFailed, "source:create", "source:failed");

        // LAZY: wrapper tạo thành công, lỗi xuất hiện khi dùng.
        List<String> lazyFailed = new ArrayList<>();
        boolean firstUseRejected = false;
        try (LazyReportSource lazy = new LazyReportSource(
                () -> new TrackedReportSource(lazyFailed, true))) {
            ReportService service = new ReportService(lazy);
            lazyFailed.add("app:ready");
            try {
                service.export("L1");
            } catch (IllegalStateException expected) {
                firstUseRejected = true;
            }
        }
        check(firstUseRejected, "Lazy phải báo lỗi ở lần dùng đầu");
        assertEvents(lazyFailed,
                "app:ready", "source:create", "source:failed");

        // LAZY: nếu không dùng, source thật không bị tạo hay đóng.
        List<String> unused = new ArrayList<>();
        try (LazyReportSource lazy = new LazyReportSource(
                () -> new TrackedReportSource(unused, false))) {
            check(unused.isEmpty(), "Tạo wrapper đã khởi tạo source");
        }
        check(unused.isEmpty(), "Không sử dụng nhưng vẫn tạo source");

        // LAZY: lần dùng thứ hai tái sử dụng instance thành công.
        List<String> used = new ArrayList<>();
        LazyReportSource lazy = new LazyReportSource(
                () -> new TrackedReportSource(used, false));
        ReportService service = new ReportService(lazy);
        check("EXPORT[data:A]".equals(service.export("A")),
                "Sai kết quả A");
        check("EXPORT[data:B]".equals(service.export("B")),
                "Sai kết quả B");
        lazy.close();
        lazy.close(); // Không đóng adapter lần thứ hai.
        assertEvents(used,
                "source:create", "source:ready",
                "source:load:A", "source:load:B",
                "source:close");

        boolean rejectedAfterClose = false;
        try {
            service.export("C");
        } catch (IllegalStateException expected) {
            rejectedAfterClose = true;
        }
        check(rejectedAfterClose, "Source đã đóng vẫn được sử dụng");

        // Khi warmUp chủ động kiểm tra, lỗi sẽ bộc lộ sớm.
        List<String> warmupFailed = new ArrayList<>();
        boolean warmupRejected = false;
        try (LazyReportSource warmup = new LazyReportSource(
                () -> new TrackedReportSource(warmupFailed, true))) {
            warmup.warmUp();
        } catch (IllegalStateException expected) {
            warmupRejected = true;
        }
        check(warmupRejected, "Warm-up không báo lỗi");
        assertEvents(warmupFailed, "source:create", "source:failed");

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac LazyInitializationDemo.java LazyInitializationTest.java
java LazyInitializationTest
```

Kết quả mong đợi: `PASS`.

Các phép kiểm thử xác minh:

1. **Eager lỗi ở bước tạo** và không có sự kiện `app:ready`.
2. **Lazy có thể công bố READY trước** khi source gặp lỗi ở lần truy cập đầu.
3. Không sử dụng thì **không khởi tạo** source, cũng không gọi `close` trên instance chưa tồn tại.
4. Hai lần dùng thành công chia sẻ **một** source; wrapper đóng source đúng một lần theo hợp đồng của ví dụ.
5. Cố dùng sau khi đóng phải bị từ chối.
6. Gọi `warmUp` khiến lỗi tạo source xuất hiện **ở bước chủ động kiểm tra**, trước khi công bố READY nếu composition root sắp xếp như vậy.

Test này kiểm tra **nghĩa của lazy và thời điểm lỗi trong mô hình đơn luồng**. Nó không chứng minh adapter từ xa thật kết nối được, không chứng minh thread safety hay tính đúng đắn của hệ thống khi lỗi kết nối xảy ra sau lúc READY.

## 6. Lỗi khởi tạo khác lỗi khi sử dụng

Cần phân biệt ít nhất ba nhóm lỗi:

| Nhóm lỗi | Ví dụ | Eager/Lazy tác động thế nào? |
| --- | --- | --- |
| **Lỗi cấu hình/khởi tạo** | Thiếu credential, URI sai cú pháp, constructor ném exception. | Eager có thể phát hiện tại startup; lazy trì hoãn đến khi factory được gọi. |
| **Lỗi kiểm tra sẵn sàng** | Không lấy được kết nối thử, không đọc được secret từ hệ thống cấu hình. | Chỉ phát hiện nếu startup/warm-up thật sự kiểm tra điều kiện này. |
| **Lỗi khi sử dụng** | Mất mạng, timeout, credential hết hạn sau nhiều giờ, dữ liệu sai. | Có thể xảy ra ở bất kỳ lần gọi nào, kể cả đã khởi tạo eager và health check thành công. |

Một lỗi khi tạo đối tượng cũng có thể bị trì hoãn thêm bởi thiết kế của adapter. Ví dụ, constructor HTTP client chỉ lưu URL, còn DNS lookup nằm ở lần `send` đầu tiên. Dù object graph được tạo eager, lỗi kết nối vẫn có thể xuất hiện sau READY.

### 6.1. Fail-fast và trải nghiệm người dùng

Với dependency **bắt buộc cho đường xử lý cốt lõi**, trì hoãn lỗi đến request đầu tiên có thể dẫn tới trải nghiệm không ổn định: ứng dụng khởi động báo thành công, nhưng request thực tế thất bại. Eager initialization hoặc một **readiness check** có thể phù hợp nếu kiểm tra đủ đáng tin cậy và chi phí chấp nhận được.

Với tính năng **ít sử dụng, tùy chọn hoặc tốn tài nguyên**, lazy có thể giảm thời gian khởi động và tránh tạo những đối tượng không dùng đến. Tuy nhiên, cần chấp nhận rằng request đầu tiên có thể chịu chi phí khởi tạo và gặp lỗi ở đó. Hệ thống phải có timeout, quan sát lỗi và xử lý tình huống này phù hợp.

Không có quy tắc “eager luôn tốt hơn” hoặc “lazy luôn tối ưu hơn”. Quyết định phụ thuộc **mức độ quan trọng của dependency**, **chi phí tạo**, **khả năng sẵn sàng khi khởi động** và **điểm chấp nhận bộc lộ lỗi**.

### 6.2. Warm-up là một quyết định cấu hình

Nếu có `LazyReportSource.warmUp()`, composition root có thể chủ động gọi:

```java
// Minh họa bootstrap; thông tin source và service được tạo như ở ví dụ.
LazyReportSource source = new LazyReportSource(
        () -> new TrackedReportSource(events, false));

source.warmUp();         // Lỗi khởi tạo sẽ xuất hiện tại đây.
events.add("app:ready");
ReportService service = new ReportService(source);
```

Khi warm-up tạo source thành công, lần sử dụng sau dùng lại instance cache. Với cấu hình đó, **các lỗi tạo source mà warm-up kiểm tra được** xuất hiện trước READY. Bù lại, ứng dụng phải trả chi phí khởi tạo tại startup, nên mất lợi ích trì hoãn phần đó. Những lỗi xảy ra trong lúc dùng sau này vẫn có thể phát sinh.

## 7. Nếu lần khởi tạo lazy thất bại, có thử lại không?

`LazyReportSource` ở mục 4 **chỉ gán `instance` sau khi `factory.get()` thành công**. Khi factory ném exception, `instance` còn `null`; lần truy cập kế tiếp sẽ thử tạo lại.

Đó là một **chính sách retry ngầm** của ví dụ, không phải đặc tính bắt buộc của lazy initialization. Một implementation khác có thể nhớ cả lỗi đầu tiên rồi ném lại cho mọi lần gọi sau.

| Chính sách khi tạo lỗi | Hành vi | Rủi ro/cân nhắc |
| --- | --- | --- |
| **Retry ở lần `get` sau** | Mỗi lần gọi có thể thử khởi tạo lại. | Có thể gây bão kết nối, tạo tài nguyên lặp và che lỗi cấu hình không thể hồi phục. |
| **Cache lỗi** | Lỗi lần đầu được lưu; các lần sau báo lại. | Một lỗi tạm thời khiến thành phần không thể phục hồi nếu không có reset/restart. |
| **Retry có kiểm soát** | Áp dụng backoff, giới hạn lần thử, timeout hoặc circuit breaker. | Cần state machine rõ ràng, observability, quy tắc concurrency và shutdown. |
| **Fail-fast ở startup** | Gọi warm-up/validation bắt buộc trước READY. | Có thể làm khởi động chậm hoặc chặn startup khi hệ thống tùy chọn đang lỗi. |

Hãy lựa chọn chính sách một cách **tường minh**. Nếu một factory thất bại **sau khi đã mở tài nguyên một phần**, chính factory/adapter phải dọn phần đã tạo trước khi ném lỗi. Wrapper lazy không thể đóng một instance mà nó chưa nhận được.

Ví dụ, khi tạo kết nối gồm hai bước “mở socket → xác thực”, lỗi xác thực phải đóng socket vừa mở. Không nên giả định rằng `try-with-resources` bên ngoài `new RemoteClient(...)` sẽ đóng được một đối tượng mà constructor chưa trả về.

**Kiểm thử cần có:** dùng một factory được điều khiển bởi biến đếm hoặc fake, khiến lần đầu lỗi, lần thứ hai thành công; xác minh số lần gọi đúng với chính sách đã chọn. Nếu chọn cache lỗi, kiểm tra factory không bị gọi lại. Với retry có backoff, nên kiểm tra lịch trình bằng clock/scheduler có thể điều khiển, tránh test phụ thuộc vào ngủ chờ thật.

## 8. Concurrent first use: nhiều luồng cùng đòi tạo dependency

Trong ứng dụng web, hai request có thể cùng sử dụng một lazy singleton lần đầu. Nếu chỉ kiểm tra `if (instance == null)` mà không đồng bộ, **cả hai thread có thể cùng tạo instance** hoặc nhìn thấy object chưa được công bố an toàn. Điều này vi phạm mục tiêu tạo một lần, có thể rò rỉ tài nguyên và gây lỗi khó tái hiện.

Một hướng thực hiện tạo một lần an toàn về **việc khởi tạo** trong Java là:

```java
// Minh họa một phần cơ chế cache; giả sử T và factory đã được khai báo.
private T instance;
private final java.util.function.Supplier<T> factory;

synchronized T getOrCreate() {
    if (instance == null) {
        instance = java.util.Objects.requireNonNull(
                factory.get(), "factory trả về null");
    }
    return instance;
}
```

Đây là **pseudocode đặt trong một lớp generic**, chưa phải file độc lập. `synchronized` đảm bảo những thread gọi cùng method không đồng thời chạy khởi tạo qua đường này, và đảm bảo công bố instance thông qua khóa tương ứng. Tuy nhiên:

- **Không tự bảo đảm thread safety của chính `T`**: mọi lời gọi nghiệp vụ trên instance dùng chung vẫn phải tuân theo contract concurrency của `T`.
- **Không xử lý đầy đủ vòng đời `close()`**: nếu một thread vừa lấy instance rồi dùng, thread khác đóng ngay có thể làm lời gọi đang chạy thất bại.
- **Không xử lý dependency cycle hoặc factory gọi ngược provider**: một cơ chế lazy có thể phải phát hiện tái nhập và báo lỗi thay vì lặp tạo vô hạn.
- **Không quyết định cách xử lý lỗi khởi tạo**: khi factory ném exception, method đồng bộ này cho phép lần gọi sau thử lại, trừ khi bổ sung state.
- **Có thể dồn tải lên request đầu**: một lần khởi tạo chậm sẽ làm các request cạnh tranh cùng khóa phải chờ.

Trong production, cần thiết kế **state machine** như `NEW`, `INITIALIZING`, `READY`, `FAILED`, `CLOSING`, `CLOSED`, với quy tắc cho việc chờ, hủy, retry và close khi đang phục vụ. Cũng có thể dùng cách đơn giản hơn: tạo dependency eager tại bootstrap hoặc để DI container quản lý theo scope được hỗ trợ.

## 9. Provider/factory nên đặt ở đâu trong kiến trúc?

Khi một service nhận thẳng `Supplier<ReportSource>`, nó có thể gọi `get()` mỗi lần xử lý. Khi đó service phải hiểu **bao giờ cần tạo**, **có được giữ lại instance hay không**, và có thể phải quan tâm đến vòng đời. Đôi lúc đây là nhiệm vụ hợp lệ, ví dụ tạo một `UnitOfWork` mới cho mỗi tác vụ, nhưng không nên làm mặc định cho dependency dùng chung.

Có ba cách thường gặp:

### 9.1. Inject instance đã lắp sẵn (ưu tiên với dependency bắt buộc, ổn định)

```java
ReportService service = new ReportService(new CachedReportSource(...));
```

`CachedReportSource` là tên minh họa cho một implementation cụ thể. Service nhận `ReportSource` và không biết cách tạo. Composition root nắm quyết định đầy đủ.

### 9.2. Inject một lazy decorator theo cùng interface nghiệp vụ

```java
ReportSource source = new LazyReportSource(
        () -> new TrackedReportSource(events, false));
ReportService service = new ReportService(source);
```

Đây là cách ở mục 4: service vẫn chỉ thấy `ReportSource`, trong khi decorator quản lý việc tạo trễ và cache. Composition root xác định ai đóng wrapper, từ đó đóng instance nếu đã khởi tạo.

### 9.3. Inject factory khi nghiệp vụ thực sự cần instance mới theo công việc

```java
interface UnitOfWork extends AutoCloseable {
    void commit();
    @Override
    void close();
}

interface UnitOfWorkFactory {
    UnitOfWork open();
}

final class ImportService {
    private final UnitOfWorkFactory workFactory;

    ImportService(UnitOfWorkFactory workFactory) {
        this.workFactory = java.util.Objects.requireNonNull(
                workFactory, "workFactory");
    }

    void importOne() {
        try (UnitOfWork work = workFactory.open()) {
            // Thực hiện nghiệp vụ trong một unit of work.
            work.commit();
        }
    }
}
```

Đoạn code minh họa giao diện và phương thức import; adapter thật phải định nghĩa thao tác dữ liệu, rollback, commit và close đúng hợp đồng. Ở đây **tạo mới theo mỗi công việc là chủ ý của use case**, nên inject factory là lựa chọn tự nhiên. Factory được chọn tại composition root; `ImportService` sở hữu unit of work trả về từ `open()` trong phạm vi phương thức, nếu contract quy định như vậy.

**Không nên dùng Service Locator** từ lớp nghiệp vụ:

```java
// Mã minh họa anti-pattern:
ReportSource source = GlobalContainer.get(ReportSource.class);
```

Lúc này dependency trở nên ẩn, lớp nghiệp vụ phụ thuộc vào API container toàn cục, và việc kiểm thử phải dựng registry ngầm. Provider được truyền rõ qua constructor có ý nghĩa khác với việc tự tìm provider ở bất kỳ đâu.

## 10. Scope và ownership khi khởi tạo trễ

**Lazy không định nghĩa scope.** Một wrapper có thể sống suốt ứng dụng, nằm trong request, hoặc được tạo lại cho mỗi task. Điều cần xác định là lifetime của wrapper, instance thật và những tài nguyên mà instance thật sở hữu.

| Cấu hình | Cách dùng phù hợp | Điều phải kiểm soát |
| --- | --- | --- |
| Application lazy singleton | Adapter đắt tiền, ít dùng, có thể chia sẻ an toàn. | First-use concurrency, cold-start latency, close sau khi drain. |
| Request-scoped lazy | Một dependency chỉ cần ở một số nhánh trong request. | Có cùng instance trong một request, cleanup kể cả khi lỗi, không giữ sang request sau. |
| Task-scoped factory | Một transaction, file tạm, unit of work riêng theo job. | Mỗi task mở/đóng đúng tài nguyên, hủy/retry an toàn. |
| Session-scoped lazy | Thành phần cần qua nhiều request của một phiên. | Concurrent requests, expiration, storage và dữ liệu được phép giữ. |

### 10.1. Close khi chưa từng tạo

Một wrapper lazy có thể đi qua cả vòng đời mà chưa gọi factory. Khi `close()`, nó phải **không khởi tạo tài nguyên mới chỉ để đóng**, và cần đánh dấu wrapper đã kết thúc để từ chối những lần sử dụng về sau. `LazyReportSource` trong ví dụ làm điều này.

### 10.2. Close sau khi đã tạo

Nếu wrapper **sở hữu instance** do factory tạo, nó cần đóng instance khi scope kết thúc theo hợp đồng. Nếu factory trả về một instance dùng chung **do composition root khác sở hữu**, wrapper thường không được tự đóng instance đó. Không có quy tắc “ai gọi `get()` thì người đó được `close()`”; ownership phải được thống nhất trong thiết kế.

### 10.3. Khởi tạo dang dở và shutdown đồng thời

Một request có thể đang tạo dependency lazy trong khi ứng dụng nhận tín hiệu tắt. Hệ thống phải chọn quy tắc: chờ khởi tạo hoàn tất rồi đóng, hủy khởi tạo nếu có thể, hoặc từ chối tạo mới khi shutdown đã bắt đầu. Không để trạng thái `CLOSED` rồi factory vẫn tạo tài nguyên mới mà không ai sở hữu để đóng.

Một thứ tự shutdown thường phù hợp là: **ngừng nhận việc mới → xử lý việc còn lại → đóng request/task scope → đóng application dependency**. Lưu ý đoạn demo chỉ minh họa trình tự đơn luồng; môi trường đa luồng cần đồng bộ và chính sách drain riêng.

## 11. Quyết định giữa eager và lazy: câu hỏi cần trả lời

Một hệ thống có thể dùng eager cho chức năng cốt lõi và lazy cho tính năng phụ. Trước khi chọn, hãy kiểm tra:

1. **Dependency có bắt buộc để báo READY không?** Nếu chức năng chính không hoạt động khi thiếu dependency, cần fail-fast hoặc readiness kiểm tra phù hợp.
2. **Chi phí tạo là gì?** Đo thời gian, kết nối, bộ nhớ và khởi động thực tế; không tối ưu theo giả định “lazy luôn nhanh”.
3. **Bao nhiêu request sẽ chịu first-use latency?** Một request hiếm có thể chấp nhận cold start; request đầu của luồng quan trọng có thể không.
4. **Failure policy là gì?** Retry, cache lỗi, timeout hoặc fail startup phải được quy định rõ, nhất là với dependency từ xa.
5. **Ai sở hữu instance và bao giờ đóng?** Factory có tạo object mới hay trả object dùng chung? Nếu tạo dang dở, ai cleanup?
6. **Mức độ đồng thời ra sao?** Có thể có hai lần truy cập đầu và shutdown cùng lúc không? Instance sau khi tạo có thread-safe không?
7. **Kiểm thử xác minh những gì?** Bao gồm eager bootstrap failure, lazy first-use failure, số lần tạo, cache, retry/đóng, và sự cố sau READY.

**Kết luận về thiết kế:** với dependency bắt buộc và nhỏ, constructor injection cùng eager wiring thường dễ lý giải. Với dependency đắt tiền hoặc ít sử dụng, lazy có thể đáng cân nhắc nếu **lỗi first-use, concurrency và ownership** đã được thiết kế có chủ ý.

## 12. Bài tập thực hành: chọn điểm bộc lộ lỗi cho các tính năng

**Bối cảnh:** một hệ thống có `PaymentGateway` phục vụ thanh toán chính, `RecommendationClient` phục vụ gợi ý sản phẩm và `ExportClient` dành cho job xuất dữ liệu hiếm khi chạy.

Hãy thực hiện:

1. Vẽ object graph cho `CheckoutService`, `RecommendationService`, `ExportJob`. Đánh dấu nơi composition root tạo instance và nơi provider/factory được inject.
2. Với `PaymentGateway`, quyết định nên tạo eager, warm-up hay lazy; nêu điều kiện thật sự cần có trước khi hệ thống được công bố READY.
3. Với `RecommendationClient`, đề xuất chính sách xử lý khi adapter không khởi tạo được lần đầu. Nếu gợi ý là tính năng tùy chọn, cần thể hiện điều đó như thế nào mà không che lỗi ở chức năng bắt buộc?
4. Với `ExportClient`, chọn tạo một lần hay mỗi job; nêu nơi đóng tài nguyên, cách xử lý retry và trường hợp job bị hủy.
5. Sử dụng `Supplier` có biến đếm để viết test xác nhận source chỉ được tạo khi cần, tạo đúng số lần và không bị tạo sau `close()`.
6. Cho factory thất bại ở lần gọi đầu và thành công ở lần thứ hai; mô tả kết quả nếu chọn retry, cache lỗi hoặc fail-fast.
7. Giả sử hai request đồng thời cùng gọi một lazy source, giải thích vì sao `if (instance == null)` đơn thuần là chưa đủ và thiết kế một phép kiểm thử concurrency phù hợp.
8. Nêu ít nhất hai lý do **constructor thành công** vẫn chưa chắc đồng nghĩa dependency có thể phục vụ request thật.

**Gợi ý đối chiếu:** `PaymentGateway` trên đường thanh toán chính thường cần điều kiện sẵn sàng được kiểm chứng trước nhận việc, nhưng không có kiểm tra nào loại bỏ mọi lỗi runtime. `RecommendationClient` có thể lazy nếu chính sách graceful degradation cho tính năng tùy chọn được xác định rõ. `ExportClient` có thể được tạo trong task scope nếu chứa tài nguyên riêng theo job; provider không tự tạo scope đúng nếu không có contract. Mọi phương án phải tách rõ *thời điểm tạo*, *số lượng instance*, *phạm vi dùng chung* và *quyền sở hữu tài nguyên*.

**Điểm cần nhớ:** Lazy initialization trong DI dịch chuyển **thời điểm tạo dependency** và có thể dịch chuyển **thời điểm lỗi được bộc lộ** từ startup sang first use. Factory/provider hỗ trợ việc trì hoãn hoặc tạo mới theo scope, nhưng không tự giải quyết caching, retry, thread safety hay lifecycle. Hãy lắp ghép tường minh ở composition root, kiểm chứng bằng Java thuần, và chỉ dùng DI container để tự động hóa sau khi đã hiểu rõ những quy tắc này.
