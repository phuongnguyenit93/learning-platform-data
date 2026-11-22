# Khi nào cần trì hoãn hoặc lặp lại việc tạo phụ thuộc

## 1. Constructor injection thông thường phù hợp khi nào?

Trong **Dependency Injection (DI)**, lớp sử dụng nhận các phụ thuộc từ bên ngoài; nơi lắp ghép chọn hiện thực, tạo đối tượng và quản lý vòng đời. Với Java thuần, cách phổ biến là tạo đầy đủ phụ thuộc tại **composition root** rồi truyền qua constructor:

~~~java
PaymentGateway gateway = new BankPaymentGateway(config);
OrderService orders = new OrderService(gateway);
~~~

Đoạn mã mang tính minh họa: các kiểu là thành phần giả định của ứng dụng. Thiết kế này dễ hiểu khi `OrderService` luôn cần gateway, gateway được dùng chung trong suốt vòng đời service và việc tạo đối tượng ở startup là phù hợp.

Nhưng có những nhu cầu khác:

- Một báo cáo chỉ được xuất khi người dùng yêu cầu; không cần mở file hoặc chuẩn bị phiên xuất báo cáo ngay từ lúc khởi động.
- Mỗi lần xuất báo cáo phải dùng **một phiên làm việc riêng**, sau đó đóng phiên đó.
- Một chỉ mục tìm kiếm tốn chi phí xây dựng và chỉ được sử dụng bởi một phần nhỏ chức năng; có thể **chờ đến lần dùng đầu tiên** rồi giữ lại kết quả.
- Một tác vụ cần đối tượng được tạo bằng dữ liệu chỉ biết khi tác vụ bắt đầu, ví dụ `reportId`, tenant hoặc tên file.
- Một service sống lâu cần lấy đối tượng có hiệu lực trong **scope hiện hành**; giữ trực tiếp instance của một request cũ sẽ sai vòng đời.

Khi đó, thay vì tiêm ngay **sản phẩm đã được tạo**, ta có thể tiêm một **factory** hoặc **provider** để lấy sản phẩm tại thời điểm phù hợp. Đây vẫn là DI: lớp nghiệp vụ được cung cấp cơ chế tạo/lấy phụ thuộc từ bên ngoài, trong khi chi tiết xây dựng vẫn nằm ở phía khác.

Cần phân biệt hai lý do quan trọng:

1. **Trì hoãn (defer):** chưa tạo ngay, chỉ tạo khi thực sự cần.
2. **Lặp lại (repeat):** tạo một instance mới cho từng lần gọi, request hoặc tác vụ, nhằm tách trạng thái và vòng đời.

Hai lý do có thể xuất hiện cùng nhau, nhưng không đồng nghĩa: một phụ thuộc tạo trễ có thể chỉ được tạo **một lần**, còn factory có thể tạo **mỗi lần**.

## 2. Factory, Provider, Supplier và lazy initialization khác nhau thế nào?

Tên gọi không quyết định hành vi. Hợp đồng của từng API mới cho biết `get()` hoặc `create()` trả lại cùng một instance hay một instance mới.

| Cơ chế | Ý nghĩa điển hình | Ví dụ | Điều phải nêu rõ |
| --- | --- | --- | --- |
| **Constructor injection trực tiếp** | Nhận phụ thuộc đã được tạo | `new OrderService(gateway)` | Ai tạo/đóng gateway, scope sử dụng |
| **Factory** | Yêu cầu tạo đối tượng với tham số tại thời điểm cần | `factory.open(reportId)` | Có tạo mới mỗi lần không, ai sở hữu sản phẩm |
| **Provider** | Yêu cầu cung cấp đối tượng hiện phù hợp | `provider.get()` | Có cache không, instance theo scope nào, có thể trả `null` không |
| **`Supplier<T>` của JDK** | Hợp đồng hàm không đối số trả về `T` | `supplier.get()` | JDK **không hứa** tạo mới, lazy hay memoization |
| **Lazy initialization** | Trì hoãn tạo đến lần cần đầu tiên | `lazyIndex.get()` | Lần sau có dùng lại không, thread safety và xử lý lỗi |
| **Object pool** | Mượn và trả lại tài nguyên được quản lý | `pool.acquire()` | Phải release đúng hạn; không nhầm với factory tạo mới |

`Supplier<T>` là functional interface đơn giản của Java, có thể được dùng để **biểu diễn** factory, provider hoặc lazy access. Bản thân kiểu `Supplier<T>` không nói số lần tạo hoặc thời điểm tạo. Ví dụ:

~~~java
Supplier<Worker> alwaysNew = Worker::new;  // Mỗi get() tạo một Worker.
Worker one = new Worker();
Supplier<Worker> alwaysSame = () -> one;   // Mỗi get() trả lại cùng tham chiếu.
~~~

Đây là hai biểu thức minh họa, giả định đã định nghĩa kiểu `Worker` và import `java.util.function.Supplier`. Cùng một chữ ký `get()`, nhưng hành vi scope hoàn toàn khác.

**Một quy tắc thiết kế:** khi có yêu cầu về lifecycle hoặc tham số runtime, một interface riêng như `ExportSessionFactory.open(reportId)` thường diễn đạt chính xác hơn `Supplier<ExportSession>` vì chính chữ ký nêu rõ **dữ liệu cần để tạo sản phẩm**.

## 3. Dấu hiệu nên trì hoãn tạo phụ thuộc

Trì hoãn hữu ích khi tất cả hoặc một vài điều sau đúng:

- **Tạo đối tượng tốn kém:** cần đọc cấu hình lớn, xây index, chuẩn bị bộ máy xử lý hoặc thiết lập tài nguyên.
- **Không phải đường đi nào cũng sử dụng:** tính năng thỉnh thoảng mới được gọi; tạo sớm làm tăng chi phí khởi động mà chưa mang lại giá trị.
- **Chỉ biết thông số khi chạy:** tenant, file, định dạng xuất, ngôn ngữ hoặc thông tin tác vụ chưa có ở composition root.
- **Cần chờ scope tồn tại:** phụ thuộc theo request không thể được phân giải hợp lệ tại startup.
- **Muốn tách phần có thể lỗi khỏi startup:** một tính năng tùy chọn có thể báo lỗi khi người dùng thực sự dùng đến, thay vì khiến toàn bộ ứng dụng không khởi động.

Tuy nhiên, trì hoãn không phải lúc nào cũng tốt. Nó có thể **chuyển lỗi cấu hình** từ lúc startup sang request đầu tiên, làm tăng độ trễ lần đầu và khiến lỗi xuất hiện khó dự đoán. Nếu một phụ thuộc là bắt buộc để ứng dụng nhận lưu lượng, khởi tạo và kiểm tra nó ở startup thường là lựa chọn dễ vận hành hơn.

Đừng dùng lazy chỉ vì muốn thay toàn bộ lệnh `new` bằng `Supplier`. Khi dependency rẻ, luôn dùng và có vòng đời trùng với service, constructor injection trực tiếp thường rõ ràng hơn.

## 4. Dấu hiệu nên tạo lại phụ thuộc cho từng thao tác

Lặp lại việc tạo đối tượng đặc biệt cần thiết khi mỗi tác vụ có **trạng thái độc lập**:

| Trường hợp | Vì sao không nên giữ cùng một instance? | Cách cấp phù hợp |
| --- | --- | --- |
| Phiên xuất file/báo cáo | File đích và trạng thái ghi khác nhau; phiên cần đóng sau mỗi lần xuất | Factory `open(reportId)`, caller đóng phiên |
| Transaction/unit of work | Transaction thuộc đúng một tác vụ, không được dùng lại sau commit/rollback | Factory hoặc request scope |
| Bộ giải mã có bộ đệm mutable riêng | Dữ liệu xử lý của một tác vụ có thể ảnh hưởng tác vụ khác | Instance mới mỗi tác vụ |
| Context xác thực theo request | Context hết hiệu lực khi request kết thúc | Tham số phương thức, request factory hoặc scoped provider |
| Bộ tạo mã cần cấu hình thay đổi mỗi lần gọi | Thông số chỉ có lúc chạy | Factory nhận thông số runtime |

Nếu dữ liệu đầu vào chỉ là một số hoặc một value object đơn giản, không nhất thiết phải tạo dependency mới: có thể truyền nó **trực tiếp qua tham số phương thức**. Factory thích hợp khi việc tạo một **đối tượng có hành vi/vòng đời riêng** cần được trừu tượng hóa.

## 5. Ví dụ chạy được: factory tạo một phiên xuất báo cáo mới mỗi lần

Giả sử `ReportService` chịu trách nhiệm quy tắc xuất báo cáo, còn `ExportSession` đại diện cho một phiên xuất có thể đóng. Một phiên chỉ phục vụ **một báo cáo**. `ReportService` có thể sống suốt ứng dụng, nhưng nó không giữ một `ExportSession` đã mở trong field.

Thiết kế:

~~~mermaid
flowchart TD
    Root["Composition root: App.main()"] -->|"tiêm một lần"| Service["ReportService sống lâu"]
    Root -->|"tạo"| Factory["ExportSessionFactory"]
    Service -->|"giữ tham chiếu"| Factory
    Service -->|"export A: open(A)"| A["ExportSession A"]
    Service -->|"export B: open(B)"| B["ExportSession B"]
    Factory -.->|"tạo riêng"| A
    Factory -.->|"tạo riêng"| B
    A -->|"write / close"| EndA["Kết thúc tác vụ A"]
    B -->|"write / close"| EndB["Kết thúc tác vụ B"]
~~~

Lưu chương trình sau thành **`FactoryProviderDemo.java`** (Java 11 trở lên):

~~~java
import java.util.Objects;

public final class FactoryProviderDemo {

    // Sản phẩm có vòng đời một lần xuất.
    public interface ExportSession extends AutoCloseable {
        void writeLine(String line);

        @Override
        void close();
    }

    // Hợp đồng tạo phiên mới, dùng thông tin chỉ biết tại runtime.
    @FunctionalInterface
    public interface ExportSessionFactory {
        ExportSession open(String reportId);
    }

    public static final class ConsoleExportSession implements ExportSession {
        private final String reportId;
        private boolean closed;

        public ConsoleExportSession(String reportId) {
            this.reportId = Objects.requireNonNull(reportId, "reportId");
            System.out.println("OPEN " + reportId);
        }

        @Override
        public void writeLine(String line) {
            if (closed) {
                throw new IllegalStateException("Phiên đã đóng");
            }
            System.out.println("WRITE " + reportId + ": " + line);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("CLOSE " + reportId);
            }
        }
    }

    public static final class ReportService {
        private final ExportSessionFactory sessions;

        public ReportService(ExportSessionFactory sessions) {
            this.sessions = Objects.requireNonNull(sessions, "sessions");
        }

        public void export(String reportId, String line) {
            // Kiểm tra trước khi tạo sản phẩm và thực hiện tác dụng phụ.
            if (reportId == null || !reportId.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException("reportId không hợp lệ");
            }
            if (line == null || line.isBlank()) {
                throw new IllegalArgumentException("Dòng báo cáo không hợp lệ");
            }

            // Mỗi lần export() mở một phiên riêng và đóng đúng scope.
            try (ExportSession session = Objects.requireNonNull(
                    sessions.open(reportId), "factory trả về null")) {
                session.writeLine(line);
            }
        }
    }

    public static void main(String[] args) {
        // Composition root chọn cách tạo phiên.
        ExportSessionFactory factory = ConsoleExportSession::new;
        ReportService reports = new ReportService(factory);

        reports.export("R-001", "Doanh thu: 100");
        reports.export("R-002", "Doanh thu: 200");
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac FactoryProviderDemo.java
java FactoryProviderDemo
~~~

Kết quả:

~~~text
OPEN R-001
WRITE R-001: Doanh thu: 100
CLOSE R-001
OPEN R-002
WRITE R-002: Doanh thu: 200
CLOSE R-002
~~~

**Điều gì đã thay đổi so với tiêm sản phẩm trực tiếp?** Constructor của `ReportService` nhận **một factory dùng lâu dài**, thay vì nhận một phiên xuất đang mở. Mỗi lần `export()`, service yêu cầu factory mở một phiên mới với `reportId` của tác vụ hiện tại. `try-with-resources` đảm bảo gọi `close()` khi thoát khối, kể cả khi ghi thất bại.

Trong ví dụ, `ConsoleExportSession` chỉ in ra console và dùng `close()` để minh họa. Khi thay bằng adapter ghi file thật, giao diện `writeLine` và `close` có thể khai báo `throws IOException`; khi đó service phải truyền hoặc xử lý ngoại lệ theo hợp đồng nghiệp vụ. Điểm quan trọng là **ai cấp phiên, ai dùng và ai chịu trách nhiệm đóng**.

### Factory sở hữu thứ gì?

Factory **quyết định cách tạo** phiên, nhưng theo hợp đồng ví dụ, service **sở hữu phiên được trả về** cho đến cuối lần gọi và phải đóng nó. Bản thân factory có thể sử dụng tài nguyên dùng chung như cấu hình hoặc connection pool; những tài nguyên đó có thể thuộc quyền sở hữu của composition root.

Nếu mở một phiên cần nhiều bước và bước giữa thất bại, **factory phải dọn những tài nguyên nó đã mở nhưng chưa chuyển giao thành công**. Caller chỉ có thể đóng sản phẩm sau khi factory thực sự trả về nó.

## 6. Kiểm thử factory: tạo đúng lúc, tạo riêng và luôn đóng

DI giúp kiểm thử mà không cần mở file hay dùng framework mocking. Ta thay factory bằng fake ghi lại từng phiên được mở. Bài kiểm thử cần chứng minh:

1. Constructor của `ReportService` không tạo phiên.
2. Đầu vào không hợp lệ bị chặn trước khi gọi factory.
3. Hai lần xuất hợp lệ tạo **hai phiên khác nhau** và đóng từng phiên.
4. Nếu ghi ném ngoại lệ, phiên tương ứng **vẫn được đóng**.

Lưu đoạn sau thành **`FactoryProviderDemoTest.java`** cạnh file chính:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class FactoryProviderDemoTest {

    static final class RecordingFactory
            implements FactoryProviderDemo.ExportSessionFactory {
        final List<RecordingSession> created = new ArrayList<>();
        boolean nextWriteFails;

        @Override
        public FactoryProviderDemo.ExportSession open(String reportId) {
            RecordingSession session =
                    new RecordingSession(reportId, nextWriteFails);
            nextWriteFails = false;
            created.add(session);
            return session;
        }
    }

    static final class RecordingSession
            implements FactoryProviderDemo.ExportSession {
        final String reportId;
        final boolean failOnWrite;
        boolean closed;
        int writes;

        RecordingSession(String reportId, boolean failOnWrite) {
            this.reportId = reportId;
            this.failOnWrite = failOnWrite;
        }

        @Override
        public void writeLine(String line) {
            if (failOnWrite) {
                throw new IllegalStateException("Lỗi ghi mô phỏng");
            }
            writes++;
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    static void check(boolean actual, String message) {
        if (!actual) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        RecordingFactory factory = new RecordingFactory();
        FactoryProviderDemo.ReportService service =
                new FactoryProviderDemo.ReportService(factory);

        check(factory.created.isEmpty(), "Constructor không được mở phiên");

        try {
            service.export("sai mã", "Dòng dữ liệu");
            throw new AssertionError("Phải từ chối reportId");
        } catch (IllegalArgumentException expected) {
            check(factory.created.isEmpty(),
                    "Đầu vào sai không được gọi factory");
        }

        service.export("R-001", "Dòng đầu tiên");
        service.export("R-002", "Dòng thứ hai");

        check(factory.created.size() == 2, "Phải mở hai phiên");
        RecordingSession first = factory.created.get(0);
        RecordingSession second = factory.created.get(1);
        check(first != second, "Hai lần xuất phải dùng hai phiên riêng");
        check(first.closed && second.closed, "Mỗi phiên phải được đóng");
        check(first.writes == 1 && second.writes == 1,
                "Mỗi phiên phải ghi một dòng");
        check("R-001".equals(first.reportId), "Sai tham số phiên đầu");
        check("R-002".equals(second.reportId), "Sai tham số phiên thứ hai");

        factory.nextWriteFails = true;
        try {
            service.export("R-003", "Dòng sẽ lỗi");
            throw new AssertionError("Phải báo lỗi ghi");
        } catch (IllegalStateException expected) {
            check(factory.created.size() == 3, "Phải tạo phiên thứ ba");
            check(factory.created.get(2).closed,
                    "Phiên lỗi vẫn phải được đóng");
        }

        System.out.println("Tất cả kiểm thử đều đạt.");
    }
}
~~~

Chạy:

~~~bash
javac FactoryProviderDemo.java FactoryProviderDemoTest.java
java FactoryProviderDemoTest
~~~

Test fake không có tài nguyên hệ điều hành, nên có thể ghi nhận số lần tạo, hành vi và thời điểm đóng mà không phụ thuộc vào kết nối mạng hoặc khả năng khóa file trên từng hệ điều hành. Trong dự án thật, nên có thêm test adapter I/O và trường hợp **factory ném lỗi trước khi trả sản phẩm** để xác nhận quy tắc cleanup ở bên trong factory.

## 7. Lazy initialization: tạo muộn nhưng chỉ một lần

Nhu cầu “chưa tạo ngay” **không nhất thiết có nghĩa “tạo mới mỗi lần”**. Một chỉ mục tìm kiếm lớn có thể được xây dựng khi nhận truy vấn đầu tiên, rồi **dùng lại cùng instance** cho những truy vấn tiếp theo.

Mã Java thuần dưới đây dùng `Supplier<T>`, một lớp bao (wrapper) có ghi nhớ kết quả và một service tiêu thụ. Lưu thành **`LazyCatalogDemo.java`**:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public final class LazyCatalogDemo {

    public static final class CatalogIndex {
        private final List<String> entries;

        CatalogIndex(List<String> entries) {
            // Tạo bản sao để dữ liệu không bị sửa qua tham chiếu gốc.
            this.entries = List.copyOf(entries);
        }

        String find(String keyword) {
            return entries.stream()
                    .filter(item -> item.contains(keyword))
                    .findFirst()
                    .orElse("Không tìm thấy");
        }
    }

    // Memoization: tạo trễ một lần và lưu kết quả.
    public static final class LazyCatalogProvider
            implements Supplier<CatalogIndex> {
        private final Supplier<CatalogIndex> initializer;
        private CatalogIndex cached;

        LazyCatalogProvider(Supplier<CatalogIndex> initializer) {
            this.initializer =
                    Objects.requireNonNull(initializer, "initializer");
        }

        @Override
        public synchronized CatalogIndex get() {
            if (cached == null) {
                cached = Objects.requireNonNull(
                        initializer.get(), "initializer trả về null");
            }
            return cached;
        }
    }

    public static final class SearchService {
        private final Supplier<CatalogIndex> index;

        SearchService(Supplier<CatalogIndex> index) {
            this.index = Objects.requireNonNull(index, "index");
            // Không gọi index.get() ở constructor.
        }

        String search(String keyword) {
            if (keyword == null || keyword.isBlank()) {
                throw new IllegalArgumentException("keyword không hợp lệ");
            }
            return index.get().find(keyword);
        }
    }

    public static void main(String[] args) {
        AtomicInteger buildCount = new AtomicInteger();
        Supplier<CatalogIndex> lazyIndex = new LazyCatalogProvider(() -> {
            buildCount.incrementAndGet();
            return new CatalogIndex(List.of(
                    "Dependency Injection", "Composition Root", "Scope"));
        });

        SearchService search = new SearchService(lazyIndex);
        System.out.println("Trước khi tìm: " + buildCount.get());
        System.out.println(search.search("Dependency"));
        System.out.println(search.search("Scope"));
        System.out.println("Sau hai lần tìm: " + buildCount.get());
    }
}
~~~

Chạy:

~~~bash
javac LazyCatalogDemo.java
java LazyCatalogDemo
~~~

Kết quả:

~~~text
Trước khi tìm: 0
Dependency Injection
Scope
Sau hai lần tìm: 1
~~~

Phân biệt chính xác:

- `SearchService` được tạo trước khi `CatalogIndex` tồn tại.
- `index.get()` chỉ được gọi lúc xử lý truy vấn.
- `LazyCatalogProvider` ghi nhớ index sau khi tạo, nên **hai lần `get()` trả cùng một instance**.
- Cách triển khai này đồng bộ hóa `get()` để tránh hai luồng cùng khởi tạo index, nhưng chính instance được chia sẻ vẫn phải an toàn cho các lời gọi đồng thời. Ví dụ `CatalogIndex` bất biến nên phù hợp với cách dùng này.
- Nếu `initializer.get()` ném lỗi, `cached` vẫn là `null` và lần `get()` sau sẽ **thử lại**; đây là một chính sách lỗi cần được quyết định, không phải hành vi chung của mọi lazy provider.

Với đối tượng `AutoCloseable`, chỉ memoization thôi chưa đủ: nơi sở hữu provider phải theo dõi đối tượng đã được khởi tạo chưa và đóng nó khi hết vòng đời, với cơ chế đồng bộ tương ứng. Không được giả định garbage collector sẽ đóng tài nguyên đúng lúc.

### Không tự động gọi `get()` trong constructor

Nếu viết:

~~~java
SearchService(Supplier<CatalogIndex> index) {
    this.index = Objects.requireNonNull(index, "index");
    CatalogIndex eager = index.get(); // Làm mất mục tiêu tạo muộn.
}
~~~

thì dù constructor nhận provider, sản phẩm vẫn được tạo ngay. Trì hoãn hay không phụ thuộc **thời điểm phương thức tạo/lấy được gọi**, không phụ thuộc tên kiểu dữ liệu.

## 8. Provider theo scope: lấy đối tượng phù hợp vào thời điểm sử dụng

Một provider có thể không tạo instance mới, cũng không giữ duy nhất một instance. Trong hệ thống có scope request, ý nghĩa của `get()` có thể là: **trả về đối tượng thuộc request đang hoạt động**.

Giả sử một service sống suốt ứng dụng muốn truy cập context của request hiện hành. Nếu nó lưu `RequestContext` thật trong field lúc startup hoặc trong request đầu tiên, service sẽ giữ state ngắn hạn quá lâu (captive dependency). Một scoped provider có thể giải quyết **cách phân giải vào đúng thời điểm** trong hệ sinh thái hỗ trợ nó.

~~~java
// Phác họa hợp đồng; các kiểu do ứng dụng định nghĩa.
interface CurrentRequestProvider {
    RequestContext current();
}

final class AuditService {
    private final CurrentRequestProvider requestProvider;

    AuditService(CurrentRequestProvider requestProvider) {
        this.requestProvider = requestProvider;
    }

    void recordAction(String action) {
        RequestContext request = requestProvider.current();
        audit(request.actorId(), action);
        // Không lưu request vào field.
    }

    private void audit(String actorId, String action) {
        // Ghi sự kiện.
    }
}
~~~

Đây là mã phác họa để giải thích API, không phải chương trình độc lập: cần định nghĩa `RequestContext` và môi trường phân giải scope tương ứng.

**Điều kiện bắt buộc:** phải có scope đang hoạt động khi gọi `current()`, và kết quả không được giữ lại sau khi scope kết thúc. Nếu service được gọi trong công việc bất đồng bộ ở thread khác, phải tuân thủ cơ chế truyền context của ứng dụng; provider không tự làm cho request cũ còn sống.

Khi dữ liệu request có thể đi vào phương thức trực tiếp, **method injection** thường rõ ràng hơn:

~~~java
void recordAction(RequestContext request, String action) {
    audit(request.actorId(), action);
}
~~~

Không nên tạo provider chỉ để che giấu một tham số vốn có thể truyền qua API. Provider có giá trị khi việc phân giải phụ thuộc thực sự cần trì hoãn hoặc phụ thuộc vào một scope được quản lý.

## 9. Ownership: tạo, mượn, sử dụng và đóng khác nhau

Factory/provider làm **thời điểm tạo hoặc lấy phụ thuộc** trở nên linh hoạt, nhưng không tự quyết định **quyền sở hữu (ownership)**. Hợp đồng phải quy định đối tượng được trả về có cần đóng không và ai đóng.

| Hợp đồng | Ai thường đóng sản phẩm? | Ví dụ |
| --- | --- | --- |
| `factory.open(reportId)` tạo phiên riêng mỗi lần | Caller nhận phiên và đóng sau tác vụ | `try (ExportSession s = factory.open(id))` |
| `provider.get()` trả singleton do ứng dụng quản lý | Composition root/container sở hữu singleton | Service chỉ mượn để dùng |
| Scoped provider trả context thuộc request hiện hành | Ranh giới request hoặc scope manager | Service không đóng context tùy tiện |
| Factory trả object thuần túy không giữ resource | Không có thao tác close | Calculator mới cho từng cấu hình |
| Pool trả tài nguyên theo phiên mượn | Caller release về pool, pool được đóng lúc ứng dụng dừng | JDBC connection từ pool |

Hai ý cần nhớ:

**Thứ nhất, tạo mới không tự động đồng nghĩa sở hữu.** Ví dụ pool có thể tạo vật lý một connection mới nhưng trả cho caller một đối tượng cần **trả về pool**, không được hủy pool.

**Thứ hai, provider có thể giữ tài nguyên dài hạn.** Nếu provider tạo lazy một client có socket và cache client ấy, provider hoặc lifecycle manager phải biết đóng client khi ứng dụng dừng.

Nếu factory tạo sản phẩm bằng nhiều bước và bị lỗi trước khi trả về, **factory phải cleanup phần đã tạo**. Nếu caller đã nhận tài nguyên thành công, caller đóng theo hợp đồng. Với nhiều tài nguyên, lưu lỗi chính và suppressed exceptions khi cleanup thất bại, tránh bỏ sót resource khác.

## 10. Scope, concurrency và các cạnh vòng đời dễ sai

Tiêm factory vào singleton thường hợp lý vì factory có thể sống cùng ứng dụng trong khi sản phẩm chỉ sống một request. Nhưng thiết kế đúng vẫn cần các điều kiện:

**Mỗi sản phẩm mới cho mỗi tác vụ.** Nếu factory giữ một instance mutable và trả lại nó cho tất cả request, tên `create()` không bảo vệ khỏi trộn trạng thái. Có thể viết test kiểm tra hai lần `open()` trả hai tham chiếu khác nhau khi đó là hợp đồng.

**Sản phẩm không thoát khỏi phạm vi hợp lệ.** Nếu mở một `ExportSession` trong `try-with-resources` rồi đưa vào lambda chạy nền sau khi khối kết thúc, task sẽ sử dụng session đã đóng. Muốn xử lý bất đồng bộ, cho tác vụ **tự mở và đóng** resource của nó hoặc chuyển dữ liệu độc lập rồi tạo phiên trong scope của worker.

**Factory dùng chung có thể chứa state.** Tạo instance mới không làm factory thread-safe; bộ đếm, cache hoặc collection mutable trong factory cần kiểm soát khi có gọi đồng thời.

**Lazy một lần cần đồng bộ phù hợp.** Hai request đồng thời cùng yêu cầu index có thể gây khởi tạo hai lần nếu memoization không an toàn luồng. Lớp `LazyCatalogProvider` ở trên dùng `synchronized` để minh họa; trong ứng dụng có chi phí lớn, cần đánh giá contention, hủy, retry và shutdown.

**Thứ tự shutdown phải phù hợp đồ thị.** Dừng nhận tác vụ, chờ tác vụ đang dùng sản phẩm hoàn thành, đóng các phiên còn thuộc quyền sở hữu, sau đó đóng resource dùng chung. Factory không nên tạo sản phẩm mới sau khi hệ thống đã chuyển sang trạng thái dừng nếu hợp đồng không cho phép.

~~~mermaid
sequenceDiagram
    participant R as Request
    participant S as ReportService sống lâu
    participant F as ExportSessionFactory
    participant E as ExportSession riêng
    R->>S: export(reportId, data)
    S->>S: xác thực dữ liệu
    S->>F: open(reportId)
    F-->>S: phiên E
    S->>E: writeLine(data)
    S->>E: close()
    S-->>R: hoàn tất hoặc báo lỗi
    Note over S,F: Factory và service tiếp tục sống cho request sau
~~~

## 11. Những lựa chọn sai thường gặp

| Cách làm | Vấn đề | Cách sửa |
| --- | --- | --- |
| Tiêm sẵn một `ExportSession` vào singleton `ReportService` | Một phiên bị dùng lại nhiều tác vụ hoặc sau khi đóng | Tiêm factory, tạo/đóng mỗi lần xuất |
| Đặt `Supplier<T>` nhưng gọi `get()` ngay trong constructor | Thực tế vẫn eager | Chỉ resolve lúc có nhu cầu |
| Cho rằng provider luôn tạo mới | Có provider cache hoặc trả đối tượng scoped | Làm rõ và kiểm thử hợp đồng `get()` |
| Cho rằng factory luôn “lazy một lần” | Factory có thể tạo lần nào cũng mới | Viết rõ `createNew`, `open` hoặc dùng memoizing provider |
| Inject nguyên DI container để gọi `getBean(...)` ở mọi nơi | Dependency trở thành ẩn; business logic biết container | Tiêm factory/provider chuyên biệt có kiểu rõ |
| Trả một interface chung `Object create(String type)` | Mất hợp đồng tĩnh, dễ ép kiểu và sai runtime | Dùng factory diễn đạt sản phẩm và tham số cụ thể |
| Factory mở resource rồi lỗi nhưng không cleanup | Rò rỉ resource khi khởi tạo một phần | Factory chịu trách nhiệm rollback bước tạo dở |
| Singleton cache sản phẩm request-scoped | Captive dependency, dữ liệu request cũ | Resolve trong scope rồi dùng ngắn hạn, hoặc method injection |
| Tạo connection pool mới cho mỗi request | Tốn chi phí, có thể cạn tài nguyên | Một pool app-scoped; connection mượn theo request |
| Tạo mới mọi helper không trạng thái | Độ phức tạp và allocation không cần thiết | Dùng instance chia sẻ hoặc inject trực tiếp |
| Dùng provider như cách vá dependency cycle | Che mối quan hệ vòng, lỗi có thể xuất hiện khi chạy | Thiết kế lại trách nhiệm, coordinator hoặc abstraction |
| Không quy định caller có đóng sản phẩm không | Đóng quá sớm hoặc không bao giờ đóng | Ghi rõ ownership trong factory contract |

Factory là một **ranh giới thiết kế có chủ đích**, không phải cơ chế thay mọi constructor trong toàn bộ hệ thống. Số lượng factory lớn bất thường cũng có thể báo hiệu đang mô hình hóa một service làm quá nhiều việc hoặc dùng provider như service locator.

## 12. Từ Java thuần đến DI container

Trong Java thuần, ta đã có thể:

- Tiêm factory qua constructor.
- Truyền tham số runtime khi gọi factory.
- Tạo instance mới theo tác vụ.
- Dùng `try-with-resources` để đóng resource.
- Xây một lazy provider có cache và quy tắc đồng bộ.
- Kiểm thử việc tạo, dùng, đóng bằng fake không cần framework.

Một DI container có thể hỗ trợ khai báo factory method, provider, scope, lazy bean hoặc proxy. Nhưng **tên annotation và cách phân giải phụ thuộc không đồng nhất giữa các container**. Cần xác định rõ: `get()` có thể trả singleton, đối tượng request-scoped hay một instance mới; ai quyết định đóng; và lỗi xuất hiện ở startup hay lần dùng đầu tiên.

Khi chuyển sang container, phần quan trọng nhất vẫn là **chính sách thiết kế**: vòng đời nào hợp lệ cho sản phẩm, factory/provider sống bao lâu, lúc nào phải tạo, khi lỗi thì ai thu hồi và lúc shutdown phải giải phóng theo thứ tự nào. Container giúp thực hiện những chính sách ấy, không tự suy ra chúng từ mỗi constructor.

## 13. Câu hỏi tự đánh giá và bài tập

**Bài tập 1 — Nhận diện lý do cần factory.** Xét `EmailService` luôn dùng chung một client HTTP, nhưng mỗi email phải có `MessageBuilder` mutable riêng. Thành phần nào nên tiêm trực tiếp, thành phần nào cần factory? Phác thảo constructor, phương thức `send` và điểm lắp ghép trong `main`.

**Bài tập 2 — Kiểm tra lazy chính xác.** Sửa `LazyCatalogProvider` để lần khởi tạo đầu tiên ném lỗi. Xác định lần `get()` tiếp theo sẽ làm gì với cách triển khai hiện tại. Sau đó thảo luận một chính sách khác: ghi nhớ lỗi và không thử lại. Chính sách nào hợp lý hơn nếu lỗi đến từ cấu hình cố định? Nếu lỗi đến từ mạng tạm thời?

**Bài tập 3 — Vòng đời tài nguyên.** Thay `ConsoleExportSession` bằng phiên ghi file thật dùng `BufferedWriter`. Thiết kế hợp đồng ném `IOException`, đảm bảo session được đóng kể cả khi ghi lỗi; mô phỏng việc factory thất bại sau khi đã mở một tài nguyên thứ nhất.

**Bài tập 4 — Scoped provider.** Một singleton `AuditService` cần actor của request hiện tại. So sánh truyền `RequestContext` qua phương thức với tiêm `CurrentRequestProvider`. Xác định nơi đóng scope và điều kiện nào khiến provider không thể resolve, chẳng hạn task chạy ngoài request.

**Bài tập 5 — Truy vết graph.** Vẽ object graph cho `ReportService → ExportSessionFactory → ExportSession` và `ReportService → Supplier<CatalogIndex> → CatalogIndex`. Ghi rõ thứ tự tạo, số lượng instance sau ba tác vụ, ai sở hữu và ai đóng từng node.

Bạn có thể chọn thiết kế bằng ba câu hỏi: **Phụ thuộc có cần tồn tại ngay không? Mỗi lần sử dụng cần cùng một instance hay một instance độc lập? Ai quản lý scope và đóng tài nguyên được cấp?** Nếu ba câu trả lời rõ ràng, việc dùng constructor injection, factory, provider hay lazy initialization sẽ trở thành quyết định có căn cứ trong Dependency Injection, trước khi cần đến DI container.
