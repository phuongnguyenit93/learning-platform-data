# Provider, Supplier và ngữ nghĩa tạo mới hoặc trả về instance dùng chung

Trong **Dependency Injection (DI)**, truyền trực tiếp một dependency qua constructor là cách đơn giản để nói rằng service cần đối tượng ấy để làm việc. Tuy nhiên, có lúc service cần **lấy một đối tượng khi thực hiện nghiệp vụ**, chẳng hạn mở một phiên xuất tệp riêng cho từng lần chạy, tạo một đơn vị công việc theo request, hoặc trì hoãn việc khởi tạo một client tốn tài nguyên. Khi đó, ta có thể truyền **Supplier**, **Provider** hoặc **factory** thay cho một instance có sẵn.

Điểm dễ nhầm là: **việc nhận một `Supplier<T>` hoặc `Provider<T>` không tự nói lên mỗi lần gọi `get()` sẽ tạo đối tượng mới hay trả về cùng một đối tượng**. Quy tắc đó nằm ở cách đăng ký, cách triển khai, scope, và hợp đồng mà composition root cung cấp.

Bài học thuộc chương **Factory và Provider** của module Dependency Injection. Ta sẽ thực hành **constructor injection, composition root, quản lý scope và vòng đời bằng Java thuần**, sau đó liên hệ cách DI container giải quyết Provider theo cấu hình. Trọng tâm là xác định đúng **danh tính đối tượng, thời điểm cấp phát và quyền sở hữu tài nguyên**.

Sau bài này, bạn có thể:

- Phân biệt một **dependency instance** với một **đối tượng có khả năng cung cấp dependency**.
- Giải thích chính xác vai trò của `java.util.function.Supplier<T>` và Provider trong các DI framework.
- Phân biệt **tạo mới mỗi lần**, **dùng chung**, **khởi tạo lười rồi dùng chung** và **tái sử dụng trong một scope xác định**.
- Viết contract rõ ràng cho factory/provider, tránh lỗi lấy nhầm instance hoặc đóng một tài nguyên dùng chung.
- Lắp ghép chương trình Java thuần, kiểm thử số instance được tạo và trạng thái đóng tài nguyên.
- Nhận biết khi nào nên inject thẳng dependency qua constructor, khi nào nên dùng Supplier/Provider/factory.

## 1. Inject một instance khác với inject khả năng lấy instance

Với constructor injection trực tiếp:

~~~java
final class ReportService {
    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = java.util.Objects.requireNonNull(repository);
    }
}
~~~

Composition root đưa **một tham chiếu cụ thể** vào `ReportService` khi tạo service. Trong suốt vòng đời của service, trường `repository` trỏ đến tham chiếu đó, trừ khi thiết kế có cơ chế thay đổi riêng.

Nếu thay bằng `Supplier<ReportRepository>`:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

final class ReportService {
    private final Supplier<ReportRepository> repositories;

    ReportService(Supplier<ReportRepository> repositories) {
        this.repositories = Objects.requireNonNull(repositories);
    }

    void generate() {
        ReportRepository repository =
                Objects.requireNonNull(repositories.get());
        // Sử dụng repository cho lần generate hiện tại.
    }
}
~~~

Service giờ giữ một **đối tượng cung cấp dependency**. Nó quyết định **khi nào** cần gọi `get()`, nhưng **chưa biết** `get()` có tạo mới hay tái sử dụng một instance.

Có hai cấp danh tính cần phân biệt:

1. **Danh tính của Supplier/Provider**: service có thể giữ nguyên một object Supplier trong nhiều lần gọi.
2. **Danh tính của object được trả về**: Supplier có thể trả về cùng instance, tạo mới, hoặc lấy từ context hiện hành.

Vì vậy, việc thấy `this.repositories` là một field `final` **không** có nghĩa mọi kết quả `repositories.get()` đều là cùng một repository. `final` chỉ cố định tham chiếu tới Supplier.

## 2. `Supplier<T>` có và không có những bảo đảm gì?

`Supplier<T>` là functional interface của Java chuẩn, thuộc gói `java.util.function`. Nó có một phương thức:

~~~java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
~~~

Đó là chữ ký tối giản để **cung cấp một giá trị khi được yêu cầu**. Java **không mặc định cam kết**:

- Mỗi `get()` tạo một object mới.
- Mỗi `get()` trả cùng một instance.
- Đối tượng chỉ được khởi tạo đúng một lần.
- Supplier tự an toàn khi nhiều thread gọi đồng thời.
- `get()` không trả `null` hoặc không ném exception.
- Supplier sở hữu, đóng hoặc tự giải phóng tài nguyên đã trả về.

Đặc tính trên phải được mô tả trong **hợp đồng sử dụng** và hiện thực tại **composition root** hoặc factory cụ thể.

### Ba Supplier cùng kiểu, ba ý nghĩa khác nhau

~~~java
import java.util.function.Supplier;

// 1. Tạo mới trong mỗi lần get().
Supplier<Object> fresh = Object::new;

// 2. Trả về đối tượng đã tạo từ trước.
Object sharedInstance = new Object();
Supplier<Object> shared = () -> sharedInstance;

// 3. Chỉ tạo khi get() lần đầu, rồi trả lại cùng instance.
// Memoized được định nghĩa trong phần sau.
Supplier<Object> lazyShared = new Memoized<>(Object::new);
~~~

Khi gọi:

~~~java
System.out.println(fresh.get() == fresh.get());      // false
System.out.println(shared.get() == shared.get());    // true
System.out.println(lazyShared.get() == lazyShared.get()); // true
~~~

Trong ví dụ này, `Object::new` thực sự gọi constructor mỗi lần được thực thi, còn `shared` đã chụp lại tham chiếu tạo sẵn. `Memoized` thực hiện cơ chế nhớ giá trị để tránh gọi lại factory sau lần đầu.

**Không nên suy đoán từ kiểu `Supplier<Object>`**. Cả ba biến trên cùng kiểu biên dịch, nhưng tạo ra hành vi danh tính khác nhau. Nếu nghiệp vụ cần một session mới mỗi lần, hợp đồng phải ghi rõ yêu cầu đó và kiểm thử phải phát hiện một Supplier trả lại session cũ.

## 3. Provider khác Supplier như thế nào?

Trong ngữ cảnh DI, **Provider** thường là hợp đồng lấy dependency qua một API như `get()` và có thể được container quản lý. Ví dụ, một API theo Jakarta Inject sử dụng kiểu `jakarta.inject.Provider<T>`; một số framework còn có cơ chế provider riêng.

Điểm chung:

- Bên sử dụng giữ một **handle** để lấy dependency khi cần.
- `get()` trả một object theo chính sách được cấu hình hoặc hiện thực.
- Việc lấy dependency có thể diễn ra muộn hơn lúc tạo consumer.

Điểm khác biệt quan trọng:

| Tiêu chí | Java `Supplier<T>` | Provider do DI framework cung cấp |
| --- | --- | --- |
| Nơi định nghĩa | Thư viện chuẩn Java | API hoặc framework DI tương ứng |
| API cốt lõi | `T get()` | Thường là `T get()`; khả năng khác tùy API |
| Nguồn object | Lambda, method reference hoặc class tùy ý | Thường gắn với binding/registration của container |
| Ngữ nghĩa scope | Do code cấp Supplier quyết định | Do cấu hình scope và cách resolve của container quyết định |
| Cần DI container? | Không | Thường có nếu muốn container resolve; interface tự thân không cần một container cụ thể |
| Bảo đảm tạo mới mỗi `get()`? | Không | **Không mặc định**: phụ thuộc scope và framework |
| Kiểm thử Java thuần | Có thể truyền lambda/fake trực tiếp | Có thể dựng fake nếu API cho phép; không bắt buộc khởi động toàn bộ container cho unit test |

Không nên đồng nhất Provider với “factory luôn tạo mới”. Chẳng hạn, một container có thể được cấu hình cung cấp:

- **Singleton**: nhiều lần lấy một dependency trả cùng instance đã đăng ký.
- **Unscoped/transient**: có thể tạo instance mới trong mỗi lần resolve, theo quy tắc container.
- **Request-scoped**: trong một request trả đối tượng gắn với request đó; request khác có thể nhận instance khác.
- **Custom scope**: đối tượng được chia sẻ theo transaction, job hoặc phạm vi mà ứng dụng định nghĩa.

Chi tiết về khi nào provider trả proxy, object thật hoặc báo lỗi ngoài scope phụ thuộc framework. **Cần đọc hợp đồng scope của công nghệ đang dùng**, thay vì dùng kiểu Provider để tự suy ra hành vi.

## 4. Bốn ngữ nghĩa cần phân biệt: mới, chung, lazy và scoped

Hai câu hỏi độc lập là:

1. **Đối tượng được tạo/lấy khi nào?** Ngay khi bootstrap, khi gọi `get()` lần đầu hay ở mỗi lần cần?
2. **Đối tượng được tái sử dụng trong phạm vi nào?** Không tái sử dụng, toàn ứng dụng, trong một request, hay một unit of work?

| Cách cung cấp | Ví dụ cách tạo | Mỗi lần gọi nhận gì? | Khi nào thường phù hợp? |
| --- | --- | --- | --- |
| **Per-call / fresh** | `() -> new ExportSessionImpl()` | Instance mới cho từng `get()` | Phiên làm việc độc lập theo thao tác |
| **Shared / eager** | `T one = new T(); () -> one` | Cùng instance đã tạo từ trước | Cấu hình bất biến, collaborator dùng chung an toàn |
| **Lazy shared** | `new Memoized<>(T::new)` | Lần đầu tạo, các lần sau dùng lại | Khởi tạo tốn chi phí nhưng chỉ cần một instance |
| **Scoped** | Provider do scope quản lý | Có thể cùng instance trong một scope và khác giữa các scope | Request context, unit of work, session theo tác vụ |

Một Supplier **tạo lười** chưa chắc **dùng chung**: `() -> new T()` cũng chỉ tạo đối tượng khi gọi, nhưng có thể tạo mới mọi lần. Ngược lại, một **singleton** có thể được tạo sớm hoặc tạo lười.

~~~mermaid
flowchart TD
    S["Consumer gọi get()"] --> P{"Chính sách cấp đối tượng?"}
    P -->|"Mỗi lần tạo mới"| A["Instance A, rồi B, rồi C"]
    P -->|"Dùng chung"| B["Cùng instance đã tạo"]
    P -->|"Lazy + memoize"| C["Tạo ở lần đầu, sau đó cùng instance"]
    P -->|"Theo scope"| D["Cùng instance trong scope hiện tại"]
~~~

Dấu hiệu cần xem xét là **tính đúng của hợp đồng**. Một service xử lý hai bước thuộc cùng một unit of work có thể cần cùng session; một service xuất hai báo cáo độc lập có thể cần hai session. Không có một quy tắc “Provider luôn tốt hơn Supplier” hay “luôn tạo mới” cho mọi trường hợp.

## 5. Ví dụ hoàn chỉnh: một phiên mới cho mỗi lượt xuất tài liệu

Giả sử mỗi lần xuất tài liệu cần một `ExportSession` riêng vì session giữ trạng thái công việc và phải đóng khi xong. `ExportService` sống lâu hơn các lần xuất, do đó inject một **Supplier tạo session mới** thay vì một instance session cụ thể.

Lưu chương trình **Java 17+** sau vào `Main.java`. Không cần DI container hoặc thư viện ngoài.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

record Document(String id) {
    Document {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Invalid document id");
        }
    }
}

interface ExportSession extends AutoCloseable {
    void write(Document document);

    @Override
    void close();
}

interface ExportLog {
    void record(String documentId);
}

// Adapter mô phỏng: in ra console, không xuất file thật.
final class ConsoleExportSession implements ExportSession {
    private final int sequence;
    private boolean closed;

    ConsoleExportSession(int sequence) {
        this.sequence = sequence;
    }

    @Override
    public void write(Document document) {
        if (closed) {
            throw new IllegalStateException("Session already closed");
        }
        System.out.println(
                "WRITE " + document.id() + " via session " + sequence);
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("CLOSE session " + sequence);
        }
    }
}

final class InMemoryExportLog implements ExportLog {
    private final List<String> ids = new ArrayList<>();

    @Override
    public void record(String documentId) {
        ids.add(documentId);
    }

    List<String> ids() {
        return List.copyOf(ids);
    }
}

// Consumer: nhận khả năng mở session, không tự chọn implementation.
final class ExportService {
    private final Supplier<ExportSession> sessionFactory;
    private final ExportLog log;

    ExportService(
            Supplier<ExportSession> sessionFactory,
            ExportLog log) {
        this.sessionFactory =
                Objects.requireNonNull(sessionFactory, "sessionFactory");
        this.log = Objects.requireNonNull(log, "log");
    }

    void export(Document document) {
        Objects.requireNonNull(document, "document");

        // Hợp đồng của factory: trả session MỚI, do caller sở hữu.
        try (ExportSession session = Objects.requireNonNull(
                sessionFactory.get(), "sessionFactory.get()")) {
            session.write(document);
            log.record(document.id());
        }
    }
}

// Composition root: chọn, tạo và lắp ghép các collaborator.
public class Main {
    public static void main(String[] args) {
        AtomicInteger nextId = new AtomicInteger();

        // Mỗi lời gọi get() tạo một session độc lập.
        Supplier<ExportSession> perExport =
                () -> new ConsoleExportSession(nextId.incrementAndGet());

        // Một log dùng chung cho cả hai lần xuất trong ví dụ console.
        InMemoryExportLog log = new InMemoryExportLog();
        ExportService service = new ExportService(perExport, log);

        service.export(new Document("DOC-1"));
        service.export(new Document("DOC-2"));

        System.out.println("Log entries: " + log.ids().size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Kết quả dự kiến:

~~~text
WRITE DOC-1 via session 1
CLOSE session 1
WRITE DOC-2 via session 2
CLOSE session 2
Log entries: 2
~~~

### Đọc luồng tạo và đóng đối tượng

1. `Main` tạo `perExport`, một Supplier giữ công thức khởi tạo session. Bản thân việc tạo Supplier **chưa** tạo `ConsoleExportSession`.
2. `Main` inject Supplier và `ExportLog` vào constructor `ExportService`. Đây là **DI thủ công** tại composition root.
3. Khi `export(DOC-1)` chạy, `sessionFactory.get()` tạo session 1. `try-with-resources` đóng session 1 sau khi hoàn tất.
4. Khi `export(DOC-2)` chạy, `get()` tạo **session 2 khác**. Hai thao tác không chia sẻ trạng thái session.
5. `ExportLog` được tạo một lần và dùng chung; đây là lựa chọn scope của composition root, không do cú pháp Supplier quyết định.

`InMemoryExportLog` dùng `ArrayList` trong ví dụ chạy tuần tự. Nếu `ExportService` được dùng chung ở server nhiều thread, log adapter phải được thiết kế an toàn đồng thời hoặc thay bằng implementation thích hợp.

**Quy tắc ownership rất quan trọng:** trong ví dụ, `ExportService` được phép đóng session vì hợp đồng `sessionFactory.get()` hứa trả một session mới mà lượt xuất hiện tại sở hữu. Nếu ai đó thay factory bằng `() -> sharedSession`, lần xuất đầu sẽ đóng session dùng chung và lần xuất sau có thể thất bại. Đó là **vi phạm hợp đồng** ngay cả khi code vẫn biên dịch.

## 6. Khi muốn trả một instance dùng chung

Không phải mọi dependency nên được tạo lại khi gọi `get()`. Ví dụ, một chính sách tính phí **bất biến** và không giữ trạng thái của request có thể được dùng chung an toàn.

~~~java
record FeePolicy(long fixedCents) {
    FeePolicy {
        if (fixedCents < 0) {
            throw new IllegalArgumentException("Negative fee");
        }
    }

    long calculate(long amountCents) {
        return amountCents + fixedCents;
    }
}

// Composition root:
FeePolicy policy = new FeePolicy(500);
java.util.function.Supplier<FeePolicy> shared = () -> policy;

// Bất kể gọi bao lần, kết quả là cùng tham chiếu.
System.out.println(shared.get() == shared.get()); // true
~~~

Mã này là ví dụ về **chia sẻ được quyết định trước**, không phải lazy creation: `policy` được tạo ngay khi chạy composition root. `record` với giá trị bất biến giúp chia sẻ đơn giản hơn.

Tuy nhiên, nếu consumer **luôn** cần đúng một `FeePolicy`, constructor injection trực tiếp thường rõ hơn:

~~~java
final class PriceService {
    private final FeePolicy policy;

    PriceService(FeePolicy policy) {
        this.policy = java.util.Objects.requireNonNull(policy);
    }
}
~~~

Dùng `Supplier<FeePolicy>` chỉ để che một dependency bắt buộc không có lý do trì hoãn hay scope thường làm API khó hiểu hơn. Hãy dùng Supplier khi consumer thực sự cần **quyền quyết định thời điểm lấy** giá trị.

### Memoization: lần đầu tạo, về sau dùng lại

Một cách viết Java thuần để khởi tạo lười và dùng chung:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

final class Memoized<T> implements Supplier<T> {
    private final Supplier<? extends T> source;
    private boolean initialized;
    private T value;

    Memoized(Supplier<? extends T> source) {
        this.source = Objects.requireNonNull(source, "source");
    }

    @Override
    public synchronized T get() {
        if (!initialized) {
            T created = Objects.requireNonNull(source.get(), "source.get()");
            value = created;
            initialized = true;
        }
        return value;
    }
}
~~~

Với implementation này:

- Nếu khởi tạo thành công, mọi lần `get()` tiếp theo trả **cùng tham chiếu**.
- `synchronized` giúp nhiều thread không đồng thời chạy bước khởi tạo thành công; nó **không khiến đối tượng T trở nên thread-safe** khi các thread sử dụng T.
- Nếu `source.get()` ném exception hoặc trả `null`, lần lấy đó thất bại và lần lấy sau có thể thử tạo lại vì `initialized` vẫn là `false`.
- `Memoized` **không tự đóng** đối tượng đã tạo. Nếu T sở hữu socket, connection hoặc thread pool, phải bổ sung cơ chế ownership và shutdown phù hợp.

Không dùng kiểu memoize này cho session bắt buộc **mới mỗi lần**. Memoization chủ động biến chính sách từ “tạo mới” thành “dùng chung sau lần đầu”.

## 7. Provider theo scope: cùng instance trong một công việc, khác giữa các công việc

Khác với hai thái cực “mới mỗi lần” và “chung toàn ứng dụng”, nhiều hệ thống cần **cùng một đối tượng trong một unit of work**. Ví dụ, dịch vụ giảm giá và dịch vụ duyệt đơn phải dùng cùng một context đang quản lý trạng thái đơn hàng cho một thao tác.

~~~text
Công việc A:
  provider.get() -> WorkContext #A
  provider.get() -> WorkContext #A

Công việc B:
  provider.get() -> WorkContext #B
  provider.get() -> WorkContext #B

#A != #B
~~~

Trong các DI framework có scope, provider có thể được cấu hình để resolve từ context của công việc hiện tại. **Không nên coi `Provider.get()` tự động có ngữ nghĩa này**: kết quả phụ thuộc binding và scope. Việc gọi ngoài scope còn có thể báo lỗi, hoặc trả proxy theo cơ chế riêng của framework.

Với Java thuần, cách dễ nhìn thấy nhất là **tạo một context ở ranh giới công việc rồi truyền cùng tham chiếu**:

~~~java
// Giả định có WorkContext và hai service nhận nó qua constructor.
try (WorkContext context = new WorkContext(store)) {
    DiscountService discounts = new DiscountService(context);
    ApprovalService approvals = new ApprovalService(context);

    discounts.discount(orderId);
    approvals.approve(orderId);

    context.commit();
}
~~~

Đây là mã minh họa ranh giới scope, chưa phải ví dụ Java độc lập. Cùng một `context` được chia sẻ trong công việc, dù hai service có thể sống trong thời gian ngắn. Khi bắt đầu công việc mới, composition root tạo `WorkContext` khác.

**Lỗi phổ biến:** mỗi bước tự gọi một Supplier tạo mới:

~~~java
// Nếu factory tạo mới mỗi lần, hai service nhận hai context khác nhau.
DiscountService discounts =
        new DiscountService(contextFactory.get());
ApprovalService approvals =
        new ApprovalService(contextFactory.get());
~~~

Điều này có thể phá tính nhất quán danh tính của entity trong cùng thao tác. Nếu hợp đồng yêu cầu **một context mỗi công việc**, hãy lấy **một lần** tại ranh giới bắt đầu công việc rồi truyền cùng instance cho mọi bước.

Ngược lại, nếu provider của container đã quản lý unit-of-work scope, gọi `get()` nhiều lần có thể trả cùng instance khi scope còn hoạt động. Cần xác định điều đó bằng đặc tả scope và kiểm thử hành vi có ý nghĩa, tránh dựa vào giả định về số lần gọi.

## 8. Factory có tên rõ ràng giúp diễn đạt hợp đồng tạo đối tượng

`Supplier<T>` chỉ có `get()`, nên khi yêu cầu mạnh về vòng đời, có thể viết interface **theo ngôn ngữ của ứng dụng**:

~~~java
interface ExportSessionFactory {
    /**
     * Mở một session mới, độc lập, thuộc quyền sở hữu của caller.
     * Caller phải gọi close() sau khi sử dụng.
     */
    ExportSession open();
}
~~~

So với `Supplier<ExportSession>`, tên `open()` và Javadoc có thể giúp người đọc nhận ra việc tạo session có **tác dụng cấp phát tài nguyên** cùng nghĩa vụ đóng. Nếu việc tạo cần dữ liệu lúc chạy, factory có thể nhận tham số:

~~~java
interface ExportSessionFactory {
    ExportSession open(String tenantId);
}
~~~

Một `Supplier<T>` phù hợp khi không cần tham số runtime và `get()` đủ diễn đạt. Factory chuyên biệt phù hợp khi cần nhiều tham số, phân biệt loại kết quả hoặc cần hợp đồng ownership rõ ràng. Cả hai đều có thể được inject qua constructor.

**Không cần tạo interface factory cho mọi `new`.** Nếu đối tượng là giá trị ngắn hạn như `new Document(id)`, việc tạo nó trong nghiệp vụ có thể hoàn toàn bình thường. Điều quan trọng là tách **việc chọn, cấu hình và sở hữu collaborator** khỏi mã nghiệp vụ, không cấm mọi phép tạo object.

## 9. Ranh giới ownership và cách xử lý lỗi

Khi một factory trả về tài nguyên có thể đóng, ứng dụng phải nói rõ **ai sở hữu** kết quả:

| Hợp đồng provider/factory | Bên nào thường đóng? | Điều cần tránh |
| --- | --- | --- |
| Mở **instance mới do caller sở hữu** | Caller dùng `try-with-resources` hoặc đóng đúng lúc | Quên đóng khi lỗi xảy ra |
| Trả **instance dùng chung thuộc application runtime** | Composition root hoặc lifecycle manager | Consumer tự đóng sau một thao tác |
| Trả **instance theo request/work scope** | Bên quản lý scope | Giữ tham chiếu và dùng sau khi scope hết hạn |
| Trả **giá trị bất biến, không có tài nguyên** | Không cần đóng | Thêm cơ chế đóng không cần thiết |

Trong ví dụ `ExportService`, `try-with-resources` bảo đảm phiên được đóng nếu `write` hoặc `log.record` ném exception. Việc đóng session **không có nghĩa** xuất tài liệu đã được rollback hoặc không có tác dụng phụ bên ngoài. Nếu thao tác ghi một phần rồi thất bại, chính sách retry và tính nhất quán phải được thiết kế riêng.

Hãy cân nhắc thêm:

- **Null:** provider có được trả `null` hay phải luôn trả một instance hợp lệ? Ví dụ trên dùng `Objects.requireNonNull` để phát hiện lỗi ở ranh giới lấy tài nguyên.
- **Lỗi tạo:** nếu `get()` thất bại, consumer có retry không, hay báo lỗi? Không tự retry khi việc tạo có tác dụng phụ hoặc không bảo đảm idempotency.
- **Lỗi đóng:** tài nguyên có thể phát sinh lỗi khi `close()`. `try-with-resources` bảo toàn exception chính và lưu exception từ close dưới dạng suppressed theo quy tắc Java.
- **Scope:** một long-lived singleton không được giữ tham chiếu tới đối tượng ngắn hạn sau khi scope của nó kết thúc.
- **Concurrency:** nếu dùng chung một dependency mutable, phải xác minh tính an toàn luồng; `Supplier` hoặc Provider không tự đồng bộ những lời gọi tới object nhận được.

## 10. Kiểm thử hợp đồng: mới mỗi lượt, đóng đúng và không ghi log khi thất bại

Một test tốt cho provider cần kiểm tra **ngữ nghĩa mong đợi**, chứ không chỉ xác minh rằng `get()` trả về một object. Với `ExportService`, ta muốn mỗi lần xuất nhận một session mới; mỗi session được đóng; và session vẫn được đóng ngay cả khi `write` thất bại.

Lưu `ExportServiceTest.java` bên cạnh `Main.java` của phần 5:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class ExportServiceTest {
    static final class FakeSession implements ExportSession {
        final int id;
        final boolean failOnWrite;
        boolean closed;
        int writes;

        FakeSession(int id, boolean failOnWrite) {
            this.id = id;
            this.failOnWrite = failOnWrite;
        }

        @Override
        public void write(Document document) {
            if (closed) {
                throw new IllegalStateException("Use after close");
            }
            writes++;
            if (failOnWrite) {
                throw new IllegalStateException("Simulated write failure");
            }
        }

        @Override
        public void close() {
            closed = true;
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        AtomicInteger created = new AtomicInteger();
        List<FakeSession> opened = new ArrayList<>();

        Supplier<ExportSession> fresh = () -> {
            FakeSession session =
                    new FakeSession(created.incrementAndGet(), false);
            opened.add(session);
            return session;
        };

        InMemoryExportLog log = new InMemoryExportLog();
        ExportService service = new ExportService(fresh, log);

        service.export(new Document("TEST-1"));
        service.export(new Document("TEST-2"));

        check(created.get() == 2, "Must create two sessions");
        check(opened.get(0) != opened.get(1),
                "Must not reuse the same session");
        check(opened.get(0).closed && opened.get(1).closed,
                "Each session must be closed");
        check(opened.get(0).writes == 1 && opened.get(1).writes == 1,
                "Each session must be written once");
        check(log.ids().equals(List.of("TEST-1", "TEST-2")),
                "Successful exports must be logged");

        FakeSession failing = new FakeSession(99, true);
        ExportService failingService =
                new ExportService(() -> failing, id -> {
                    throw new AssertionError("Must not log failed write");
                });

        boolean failed = false;
        try {
            failingService.export(new Document("FAIL"));
        } catch (IllegalStateException expected) {
            failed = true;
        }
        check(failed, "Expected write failure");
        check(failing.closed, "Failed session must still be closed");

        System.out.println("PASS");
    }
}
~~~

Chạy:

~~~bash
javac Main.java ExportServiceTest.java
java ExportServiceTest
~~~

Kết quả dự kiến: `PASS`.

Test này xác minh **hợp đồng tạo mới và đóng tài nguyên** của một Supplier được cấp cho `ExportService`. Nếu vô tình thay `fresh` bằng một Supplier trả session dùng chung, điều kiện `opened.get(0) != opened.get(1)` hoặc kiểm tra thao tác trên session đã đóng sẽ giúp phát hiện sai lệch.

Lưu ý: test dùng `ArrayList` và trạng thái mutable trong một chương trình đơn luồng; nó không phải kiểm thử đồng thời của production provider. Nếu triển khai có nhiều thread gọi `get()`, cần bổ sung những tình huống cạnh tranh và scope phù hợp.

## 11. Những lỗi thiết kế thường gặp

| Dấu hiệu | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Inject `Supplier<T>` rồi mặc định mọi `get()` là object mới | Kiểu Supplier không có cam kết đó | Ghi rõ contract per-call và kiểm thử identity |
| Dùng Supplier `() -> sharedClient` nhưng consumer đóng mỗi lần dùng | Đóng nhầm tài nguyên dùng chung | Để owner tại composition root quản lý close |
| Inject `Provider<RequestContext>` vào singleton, gọi ngoài request | Scope hiện tại có thể không tồn tại | Chỉ resolve trong ranh giới scope hợp lệ |
| Consumer gọi provider hai lần trong một giao dịch cần chung session | Có thể nhận hai instance khác nhau | Lấy một lần tại ranh giới công việc, truyền cùng tham chiếu |
| Memoize một object mutable không an toàn luồng | Nhiều request dùng chung trạng thái nguy hiểm | Dùng object bất biến/thread-safe hoặc thay đổi scope |
| Dùng Provider chỉ để che chu trình A → B → A | Dời lỗi khởi tạo; phụ thuộc vòng vẫn còn | Xem lại ranh giới trách nhiệm và luồng dữ liệu |
| Để nghiệp vụ gọi `GlobalContainer.get(...)` | Biến provider thành service locator, ẩn dependency | Inject factory/provider có kiểu rõ ràng qua constructor |
| Dùng factory cho mọi giá trị nhỏ, kể cả DTO tạm thời | Tăng gián tiếp không cần thiết | Chỉ tạo abstraction khi có chính sách tạo hoặc scope thực sự |
| Test kiểm tra `get() != null` rồi coi đủ | Không xác nhận danh tính, ownership, lỗi hoặc scope | Kiểm tra số lần tạo, đóng, retry và hành vi theo scope |

### Phân biệt provider với cách né vòng phụ thuộc

Một chu trình như `A -> Provider<B> -> B -> A` có thể không cản trở khởi tạo ngay lập tức nếu việc lấy B bị trì hoãn. Tuy nhiên, **quan hệ nghiệp vụ hai chiều vẫn còn**, và lời gọi `get()` có thể chạm lại vòng ở runtime. Chỉ dùng provider khi nó giải quyết **nhu cầu tạo/lấy đối tượng hợp lệ**, không coi việc container khởi động thành công là bằng chứng chu trình đã được sửa.

## 12. Quy trình chọn Provider, Supplier hay instance trực tiếp

1. **Nêu rõ nhiệm vụ của collaborator:** dependency có bắt buộc ngay từ khi consumer được tạo không?
2. **Đặt câu hỏi về danh tính:** mỗi thao tác cần instance mới, cùng một instance toàn ứng dụng hay một instance trong scope?
3. **Đặt câu hỏi về thời điểm:** khởi tạo sớm, chỉ ở lần đầu sử dụng, hay mỗi lần gọi?
4. **Nêu rõ ownership:** ai đóng tài nguyên khi thành công hoặc thất bại?
5. **Chọn API đơn giản nhất:** truyền instance trực tiếp cho dependency ổn định; Supplier cho thao tác cung cấp đơn giản; factory có tên cho hợp đồng tạo phức tạp hoặc tham số runtime.
6. **Đưa quyết định vào composition root:** tạo, cấu hình, lắp ghép và chọn scope tại ranh giới ứng dụng; giữ service nghiệp vụ phụ thuộc vào hợp đồng phù hợp.
7. **Kiểm thử hợp đồng lifetime:** kiểm tra `==` khi cần cùng object, `!=` khi cần khác object, số lần tạo, ranh giới scope và hành vi `close()`.
8. **Mở rộng sang container một cách có chủ đích:** đăng ký binding/scope theo hợp đồng đã thống nhất; không mặc định ngữ nghĩa của Provider chỉ từ tên kiểu.

### Tự kiểm tra

**Tình huống A:** `Supplier<Worker> workers = Worker::new;`. Hai lần `workers.get()` có cho cùng Worker không?

**Không**, nếu `Worker::new` thực sự gọi constructor mới mỗi lần và không có lớp bọc khác. Nhưng đó là ngữ nghĩa của **implementation này**, không phải của interface Supplier nói chung.

**Tình huống B:** `Supplier<Client> clients = () -> sharedClient;` được inject vào một service dùng chung. Service có thể gọi `close()` sau mỗi lượt xử lý không?

**Không nếu sharedClient thuộc sở hữu của application runtime.** Consumer chỉ được sử dụng và cần để owner đóng ở cuối vòng đời; việc dùng Supplier không chuyển quyền sở hữu tài nguyên.

**Tình huống C:** `Provider<Context>` được container đăng ký theo request scope. Trong một request, hai lần `get()` luôn tạo mới?

**Không nên kết luận như vậy.** Với một request-scoped binding thông thường, các lần resolve trong cùng request có thể nhận cùng scoped instance. Cần xem hợp đồng scope, proxy và quy tắc của framework cụ thể.

**Tình huống D:** Service chỉ cần một cấu hình bất biến đã có sẵn, nhưng constructor nhận `Supplier<Config>` để tiết kiệm vài dòng wiring. Có cần thiết không?

**Thường không.** Truyền `Config` trực tiếp thể hiện dependency bắt buộc rõ ràng hơn. Supplier chỉ có lợi nếu thực sự cần trì hoãn hoặc thay đổi cách lấy theo scope.

**Tình huống E:** Một factory dùng `Memoized<ExportSession>` trong ví dụ xuất tài liệu. Lượt xuất thứ hai gặp lỗi “Session already closed”. Vì sao?

**Vì memoization làm mọi lượt nhận lại một session đã được đóng sau lượt đầu.** Hợp đồng “mới mỗi lần, caller sở hữu” đã bị thay bằng “dùng chung”. Cần bỏ memoization và cấp một session mới cho từng lần xuất.

## Ghi nhớ

**`Supplier<T>` và Provider biểu diễn khả năng cung cấp dependency; ngữ nghĩa danh tính và vòng đời nằm ở implementation, scope và hợp đồng lắp ghép.** Một `get()` có thể tạo mới, trả object dùng chung, khởi tạo lười rồi tái sử dụng, hoặc resolve từ scope hiện tại. Hãy lựa chọn dựa trên **đơn vị công việc, quyền sở hữu, nhu cầu đồng thời và thời điểm sử dụng**, truyền qua constructor injection và giữ composition root chịu trách nhiệm lắp ghép. Khi mở rộng sang DI container, các quy tắc đó vẫn cần được đặc tả và kiểm thử bằng hành vi cụ thể.
