# Đưa phụ thuộc ra constructor bằng các bước nhỏ

Một ứng dụng Java lâu năm có thể hoạt động ổn định nhưng rất khó kiểm thử và thay đổi vì lớp nghiệp vụ **tự tạo mọi cộng tác viên bên trong**. Khi cần đổi database, thay adapter gửi thông báo hoặc kiểm thử một đường lỗi, lập trình viên phải sửa chính lớp nghiệp vụ thay vì chỉ thay cấu hình lắp ghép.

Trong **Dependency Injection (DI)**, hướng thiết kế tốt hơn là để lớp **nhận dependency qua constructor**, còn nơi khởi động ứng dụng (*composition root*) chịu trách nhiệm tạo và nối các đối tượng. Tuy nhiên, chuyển cả một hệ thống sang DI bằng một lần chỉnh sửa lớn thường rất rủi ro: nhiều constructor thay đổi cùng lúc, caller bị hỏng, scope bị đổi và hành vi cũ có thể vô tình khác đi.

Bài học thuộc chương **Refactor sang DI** của module **Dependency Injection**. Ta sẽ thực hiện một lộ trình **từng bước nhỏ, có điểm kiểm tra sau mỗi bước**: chụp lại hành vi hiện tại, tạo ranh giới phụ thuộc, đưa từng dependency ra constructor, giữ tương thích tạm thời, chuyển việc lắp ghép về composition root và cuối cùng thu hồi lối tạo cũ. Mọi ví dụ dùng **Java thuần** trước khi cần tới DI container.

## 1. Vấn đề ban đầu: lớp tự tạo dependency

Giả sử một service dùng để nhận đơn hàng, lưu đơn vào kho và ghi nhận một sự kiện audit:

~~~java
// Mã minh họa trước refactor; các kiểu được định nghĩa ở phần thực hành.
final class OrderService {
    private final InMemoryOrderRepository repository =
            new InMemoryOrderRepository();
    private final ConsoleAuditSink audit =
            new ConsoleAuditSink();

    Receipt place(Order order) {
        repository.save(order);
        audit.record("order-placed:" + order.id());
        return new Receipt(order.id(), order.quantity());
    }
}
~~~

Nhìn từ ngoài, chỉ cần gọi `new OrderService()`. Nhưng bên trong, service tự quyết định **repository nào** và **cách ghi audit ra đâu**. Các quyết định này không thuộc trách nhiệm của nghiệp vụ đặt hàng.

Hệ quả:

- **Thay implementation khó:** muốn chuyển từ kho trong bộ nhớ sang database phải sửa `OrderService`.
- **Kiểm thử đường lỗi khó:** không thể dễ dàng truyền repository giả cố tình ném ngoại lệ.
- **Không kiểm soát quan hệ chia sẻ:** mỗi `OrderService` tự tạo kho riêng, kể cả khi nhiều service cần cùng một nguồn trạng thái.
- **Vòng đời không rõ:** nếu thay repository bằng adapter có connection pool, service dễ kiêm luôn trách nhiệm mở/đóng tài nguyên.
- **Khó cấu hình theo môi trường:** production, staging và test đều bị buộc cùng lựa chọn ở bên trong class.

**Mục tiêu refactor không phải xóa hết mọi lệnh `new`.** Tạo một đối tượng giá trị hoặc một collection dùng nội bộ thường không phải vấn đề. Ta chỉ cần đưa ra ngoài **những dependency có chính sách triển khai, cấu hình, scope hoặc test double cần thay đổi**.

## 2. Nguyên tắc refactor an toàn: mỗi bước phải giữ một hợp đồng rõ ràng

Một quá trình tốt có hai trục cần theo dõi:

1. **Hành vi:** dữ liệu đầu vào, giá trị trả về, ngoại lệ, trạng thái được lưu, side effect quan trọng và điều kiện phát sinh chúng.
2. **Wiring:** ai tạo dependency, instance có được chia sẻ không, cấu hình lấy từ đâu và resource thuộc vòng đời của ai.

Các bước nhỏ cho phép kiểm tra **cả hai trục** sau mỗi lần thay đổi, thay vì tranh luận rất nhiều lỗi xuất hiện trong một bản diff lớn.

| Giai đoạn | Thay đổi nhỏ | Điều kiện chấp nhận |
| --- | --- | --- |
| **0. Đóng băng hành vi** | Viết characterization test quanh API hiện có | Nắm được kết quả đúng của những luồng quan trọng |
| **1. Tạo seam/port** | Đặt một abstraction quanh dependency biến động | Logic nghiệp vụ và hành vi công khai không đổi |
| **2. Đưa dependency thứ nhất ra constructor** | Constructor mới nhận repository; đường tạo cũ ủy quyền tạm thời | Caller cũ vẫn hoạt động, test có thể tiêm fake repository |
| **3. Đưa dependency tiếp theo ra constructor** | Constructor đầy đủ nhận thêm audit sink | Kiểm thử được side effect mà không cần console thật |
| **4. Di chuyển lệnh tạo về composition root** | Root chọn adapter và truyền đúng instance | Không còn production caller nào lệ thuộc đường tự tạo cũ |
| **5. Thu hồi cầu nối tạm** | Bỏ hoặc deprecate constructor mặc định theo kế hoạch | API cuối rõ ràng, ownership/scope không bị che giấu |

**Không nhất thiết thực hiện tất cả trong một commit.** Đặc biệt với dự án đang phục vụ traffic, có thể tách từng bước thành thay đổi nhỏ và triển khai độc lập sau khi kiểm chứng.

## 3. Bước 0 — Characterization test: xác nhận hành vi đang có

**Characterization test** ghi lại các hành vi quan sát được của mã hiện tại trước khi chỉnh cấu trúc. Nó khác với việc khẳng định mọi chi tiết cũ đều là thiết kế tốt: test nhằm tạo **mạng an toàn khi thay đổi**, đồng thời cung cấp bằng chứng để thảo luận nếu muốn sửa hành vi sau này.

Với `OrderService`, các điều kiện nên ghi nhận có thể là:

- Một đơn hợp lệ được lưu và trả biên nhận đúng mã, đúng số lượng.
- Không lưu hai lần đơn có cùng mã, theo chính sách hiện hành.
- Chỉ ghi audit khi lưu đơn thành công.
- Khi lưu thất bại, lỗi được truyền ra theo hợp đồng và không phát sự kiện audit thành công.

Trước khi có dependency injection, một số side effect khó quan sát trực tiếp. Có thể kiểm tra qua **API công khai** hoặc tạo seam mỏng ở ranh giới I/O mà không đổi nghiệp vụ.

**Tránh kiểm tra quá sâu nội bộ.** Một test yêu cầu `repository.save()` được gọi đúng một lần khi bản thân số lần gọi không thuộc hợp đồng sẽ rất dễ vỡ khi ta refactor. Cần ưu tiên **kết quả và side effect có ý nghĩa**, không ép nguyên vẹn mọi đường gọi private helper.

### Khi hành vi cũ có lỗi thì làm sao?

Đừng tự động lấy tất cả lỗi cũ làm “chuẩn bất biến”. Hãy phân loại rõ:

- **Hành vi hiện hành cần giữ** trong giai đoạn refactor cấu trúc.
- **Lỗi đã biết** cần sửa bằng một thay đổi nghiệp vụ riêng, có test và quyết định rõ.
- **Điểm chưa chắc chắn** cần thêm dữ liệu hoặc làm rõ hợp đồng trước khi đổi.

Nếu vừa thay API DI, vừa đổi quy tắc lưu, vừa sửa retry, bản diff sẽ khó kiểm tra và rollback. Tách refactor **không đổi hành vi** khỏi thay đổi hành vi giúp tìm nguyên nhân chính xác hơn.

## 4. Bước 1 — Tạo một ranh giới phụ thuộc nhỏ

Ở phiên bản cũ, trường của `OrderService` có kiểu implementation cụ thể:

~~~java
private final InMemoryOrderRepository repository =
        new InMemoryOrderRepository();
~~~

Ta tạo một **port** nhỏ mô tả điều service cần, không mô tả toàn bộ khả năng của adapter:

~~~java
interface OrderRepository {
    void save(Order order);

    java.util.Optional<Order> findById(String id);
}

final class InMemoryOrderRepository implements OrderRepository {
    // Implementation hiện tại vẫn có thể giữ nguyên.
}
~~~

Sau đó, có thể đổi kiểu trường sang interface mà vẫn giữ cách khởi tạo hiện tại:

~~~java
private final OrderRepository repository =
        new InMemoryOrderRepository();
~~~

Bước này **chưa phải constructor injection**, nhưng nó tạo một **seam**: service bắt đầu phụ thuộc vào một hợp đồng đủ nhỏ thay vì trực tiếp gắn với class cụ thể.

Lưu ý quan trọng:

- Đặt interface theo **nhu cầu của consumer**, không tự động sao chép 30 phương thức từ adapter hạ tầng.
- Nếu code có nhiều implementation hoặc cần test double, port thường có giá trị rõ.
- Nếu hiện tại chỉ có một class và không có lý do thay thế, không bắt buộc tạo interface chỉ để “đúng bài DI”. Constructor có thể nhận một class cụ thể nếu đó là hợp đồng hợp lý.
- Giữ nguyên semantics của adapter cũ; tránh thay cả logic lưu trữ trong bước chỉ tạo abstraction.

**Điểm kiểm tra sau bước 1:** các luồng đã mô tả ở bước 0 vẫn cho kết quả như cũ.

## 5. Bước 2 — Inject dependency đầu tiên, giữ đường tạo cũ tạm thời

Bây giờ đưa **repository** ra constructor. Để không phải sửa tất cả caller cùng lúc, thêm constructor nhận dependency và cho constructor không tham số **ủy quyền**:

~~~java
final class OrderService {
    private final OrderRepository repository;
    private final ConsoleAuditSink audit;

    // Cầu nối tạm thời để caller hiện có vẫn biên dịch.
    OrderService() {
        this(new InMemoryOrderRepository());
    }

    // Đường mới cho test và composition root.
    OrderService(OrderRepository repository) {
        this.repository = java.util.Objects.requireNonNull(
                repository, "repository");
        this.audit = new ConsoleAuditSink(); // Chưa refactor dependency này.
    }

    // Các phương thức nghiệp vụ giữ nguyên.
}
~~~

Bước này vừa đủ nhỏ để thay thế repository khi test, nhưng **chưa buộc đổi tất cả nơi tạo service**. Constructor mặc định vẫn biểu diễn lựa chọn cũ; phải coi nó là **cầu nối có kế hoạch thu hồi**, không phải cách cấu hình vĩnh viễn.

### Vì sao constructor chaining hữu ích?

Sử dụng `this(new InMemoryOrderRepository())` khiến cả đường cũ và đường mới đi qua **một nơi gán trường và kiểm tra null**, tránh hai constructor có logic lắp ghép khác nhau. Có thể giữ trường `final` để bảo đảm dependency bắt buộc sẵn sàng ngay sau constructor.

Không nên viết:

~~~java
OrderService(OrderRepository repository) {
    this.repository = repository != null
            ? repository
            : new InMemoryOrderRepository();
}
~~~

Nếu một caller mới vô tình truyền `null`, fallback như trên **che lỗi wiring**. Với dependency bắt buộc, hãy **fail fast** bằng `Objects.requireNonNull`. Nếu cần đường mặc định để tương thích, hãy cung cấp **một constructor hoặc factory có tên rõ**, thay vì âm thầm thay giá trị null.

**Điểm kiểm tra sau bước 2:** đường tạo cũ hoạt động; đường tạo mới tiêm fake repository được; logic đặt hàng và lỗi lưu không đổi.

## 6. Bước 3 — Đưa dependency thứ hai ra constructor

Sau khi repository đã có thể inject, ta tách tiếp **audit sink**:

~~~java
final class OrderService {
    private final OrderRepository repository;
    private final AuditSink audit;

    // Cầu nối cũ được gom về constructor đầy đủ.
    OrderService() {
        this(new InMemoryOrderRepository(), new ConsoleAuditSink());
    }

    // Constructor dành cho caller mới.
    OrderService(OrderRepository repository, AuditSink audit) {
        this.repository = java.util.Objects.requireNonNull(
                repository, "repository");
        this.audit = java.util.Objects.requireNonNull(audit, "audit");
    }

    // Các phương thức nghiệp vụ không phải biết cách tạo adapter.
}
~~~

`AuditSink` là interface nhỏ:

~~~java
@FunctionalInterface
interface AuditSink {
    void record(String event);
}
~~~

Tại thời điểm này, **mọi dependency cần thay đổi chính sách** đã có thể được cung cấp từ ngoài. Bài test có thể dùng một `RecordingAuditSink` để kiểm tra sự kiện thay vì bắt và phân tích output của console. Đây là **kiểm thử kết quả ở ranh giới side effect**; không cần test biết service có bao nhiêu helper nội bộ.

**Một bước nhỏ thực sự:** nếu code còn `Clock.systemUTC()`, `new JdbcClient()` hoặc `System.getenv()` bên trong use case, hãy đánh giá từng dependency còn lại theo cùng cách, không nhất thiết thay cả ba cùng một lần. Chỉ đưa ra constructor những thứ có **vòng đời hoặc chính sách phụ thuộc** cần được quản lý từ bên ngoài.

### Đừng làm thay đổi hành vi mặc định trong lúc chuyển

Nếu chương trình cũ gửi audit ra console, constructor không tham số nên tiếp tục dùng `ConsoleAuditSink` trong giai đoạn tương thích. Thay bằng `event -> { }` (No-Op) chỉ để test chạy yên là một **thay đổi hành vi**; trong hệ thống yêu cầu audit, cách đó còn có thể làm mất sự kiện quan trọng.

## 7. Bước 4 — Di chuyển việc tạo phụ thuộc về composition root

Đến đây, constructor mới đã đủ để composition root lắp ghép:

~~~java
// Đặt tại phần khởi động ứng dụng, không đặt trong OrderService.
OrderRepository repository = new InMemoryOrderRepository();
AuditSink audit = new ConsoleAuditSink();

OrderService orders = new OrderService(repository, audit);
~~~

Trong production, root có thể chọn `JdbcOrderRepository` hoặc adapter khác và cung cấp cấu hình, connection pool, executor tương ứng. Trong test, root sử dụng `InMemoryOrderRepository` cùng `RecordingAuditSink`.

~~~mermaid
flowchart TD
    subgraph Before["Trước refactor"]
        OldCaller["Caller"] --> OldService["OrderService"]
        OldService -->|"tự new"| OldRepo["InMemoryOrderRepository"]
        OldService -->|"tự new"| OldAudit["ConsoleAuditSink"]
    end
    subgraph After["Sau refactor"]
        Root["Composition root"] -->|"tạo"| Repo["OrderRepository adapter"]
        Root -->|"tạo"| Sink["AuditSink adapter"]
        Root -->|"constructor injection"| NewService["OrderService"]
        Repo -->|"được truyền"| NewService
        Sink -->|"được truyền"| NewService
        NewCaller["Caller"] --> NewService
    end
~~~

Quan hệ dùng dependency không đổi: `OrderService` vẫn lưu đơn và ghi audit. Chỉ có **quyền quyết định implementation** được di chuyển ra ngoài. Đây là điểm thực hành **IoC** trong thiết kế: lớp nghiệp vụ được sử dụng phụ thuộc nhưng không còn tự chọn cách tạo và lắp ghép chúng.

### Chia sẻ instance có chủ đích

Nếu nhiều service cần cùng một repository có trạng thái trong bộ nhớ, root có thể tạo **một instance** rồi truyền cho cả hai. Nếu không cần chia sẻ, root có thể tạo instance riêng. Hãy xác định từ yêu cầu về **scope**, không cố biến class thành Singleton pattern.

Với adapter kết nối database, nhiều repository instance có thể cùng dùng pool mà không phải cùng identity. Chia sẻ **pool/factory thread-safe** khác với chia sẻ **một session hoặc transaction đang mang trạng thái request**.

## 8. Ví dụ Java 17 hoàn chỉnh: giữ đường cũ, thêm đường DI và kiểm thử

Ví dụ dưới đây là **trạng thái trung gian có chủ đích**: `OrderService` đã có constructor injection đầy đủ nhưng vẫn còn constructor không tham số để người dùng cũ chuyển dần. Nó minh họa cách một thay đổi nhỏ vừa giữ tương thích vừa tạo **seam cho kiểm thử**.

Lưu mã vào một file `Main.java`. Các loại trừ `Main` được khai báo package-private để chạy trong một file. Khi đưa vào thư viện thực tế, hãy phân chia kiểu public/package phù hợp.

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

record Order(String id, int quantity) {
    Order {
        Objects.requireNonNull(id, "id");
        if (id.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
    }
}

record Receipt(String orderId, int quantity) {}

interface OrderRepository {
    void save(Order order);
    Optional<Order> findById(String id);
}

final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public void save(Order order) {
        Objects.requireNonNull(order, "order");
        if (orders.containsKey(order.id())) {
            throw new IllegalArgumentException("Duplicate order");
        }
        orders.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}

@FunctionalInterface
interface AuditSink {
    void record(String event);
}

final class ConsoleAuditSink implements AuditSink {
    @Override
    public void record(String event) {
        System.out.println("AUDIT " + event);
    }
}

final class RecordingAuditSink implements AuditSink {
    private final List<String> events = new ArrayList<>();

    @Override
    public void record(String event) {
        events.add(event);
    }

    List<String> events() {
        return List.copyOf(events);
    }
}

final class OrderService {
    private final OrderRepository repository;
    private final AuditSink audit;

    // CẦU NỐI: giữ lại trong giai đoạn migrate caller cũ.
    OrderService() {
        this(new InMemoryOrderRepository(), new ConsoleAuditSink());
    }

    // ĐƯỜNG DI: ứng dụng/test tự chọn dependency.
    OrderService(OrderRepository repository, AuditSink audit) {
        this.repository = Objects.requireNonNull(
                repository, "repository");
        this.audit = Objects.requireNonNull(audit, "audit");
    }

    Receipt place(Order order) {
        Objects.requireNonNull(order, "order");

        // Giữ thứ tự nghiệp vụ: lưu thành công rồi mới ghi audit.
        repository.save(order);
        audit.record("order-placed:" + order.id());
        return new Receipt(order.id(), order.quantity());
    }

    Optional<Order> findById(String id) {
        return repository.findById(id);
    }
}

public class Main {
    public static void main(String[] args) {
        // 1. Đường tạo cũ vẫn dùng được.
        OrderService legacy = new OrderService();
        Order oldOrder = new Order("LEG-1", 1);
        Receipt oldReceipt = legacy.place(oldOrder);
        check(oldReceipt.equals(new Receipt("LEG-1", 1)),
                "Đường cũ phải trả biên nhận đúng");
        check(legacy.findById("LEG-1").equals(Optional.of(oldOrder)),
                "Đường cũ vẫn phải lưu đơn");

        // 2. Đường DI cho phép dùng test double và quan sát behavior.
        InMemoryOrderRepository store = new InMemoryOrderRepository();
        RecordingAuditSink recorder = new RecordingAuditSink();
        OrderService injected = new OrderService(store, recorder);

        Order order = new Order("NEW-1", 2);
        Receipt receipt = injected.place(order);
        check(receipt.equals(new Receipt("NEW-1", 2)),
                "Đường DI phải trả biên nhận đúng");
        check(store.findById("NEW-1").equals(Optional.of(order)),
                "Đường DI phải lưu đúng đơn vào store được tiêm");
        check(recorder.events().equals(List.of("order-placed:NEW-1")),
                "Đường DI phải ghi đúng audit theo hợp đồng");

        // 3. Trùng mã: không thay đơn đã lưu và không thêm audit.
        boolean duplicateRejected = false;
        try {
            injected.place(new Order("NEW-1", 99));
        } catch (IllegalArgumentException expected) {
            duplicateRejected = true;
        }
        check(duplicateRejected, "Đơn trùng phải bị từ chối");
        check(store.findById("NEW-1").equals(Optional.of(order)),
                "Đơn cũ phải giữ nguyên");
        check(recorder.events().size() == 1,
                "Đơn trùng không được phát audit thành công mới");

        // 4. Fake repository gây lỗi: dễ test mà không cần DB thật.
        OrderRepository failingStore = new OrderRepository() {
            @Override
            public void save(Order ignored) {
                throw new IllegalStateException("Storage failure");
            }

            @Override
            public Optional<Order> findById(String id) {
                return Optional.empty();
            }
        };
        RecordingAuditSink failureRecorder = new RecordingAuditSink();
        OrderService failingService =
                new OrderService(failingStore, failureRecorder);

        boolean storageFailed = false;
        try {
            failingService.place(new Order("FAIL-1", 1));
        } catch (IllegalStateException expected) {
            storageFailed = true;
        }
        check(storageFailed, "Lỗi lưu phải được chuyển ra caller");
        check(failureRecorder.events().isEmpty(),
                "Không ghi audit thành công khi save thất bại");

        // 5. Dependency bắt buộc: không âm thầm thay null bằng default.
        boolean nullRejected = false;
        try {
            new OrderService(null, recorder);
        } catch (NullPointerException expected) {
            nullRejected = true;
        }
        check(nullRejected, "Constructor phải từ chối thiếu repository");

        // 6. Root quyết định instance nào được chia sẻ hoặc tách biệt.
        OrderService isolated = new OrderService(
                new InMemoryOrderRepository(), new RecordingAuditSink());
        check(isolated.findById("NEW-1").isEmpty(),
                "Repository khác phải có trạng thái riêng");

        System.out.println("PASS");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả mong đợi:

~~~text
AUDIT order-placed:LEG-1
PASS
~~~

Những điều test xác minh:

1. **Tương thích hành vi:** đường `new OrderService()` cũ vẫn lưu đơn và trả biên nhận đúng.
2. **Có thể thay thế dependency:** `OrderService(repo, audit)` nhận được fake/test double tùy ý.
3. **Kết quả nghiệp vụ:** lưu đúng, không ghi audit mới khi trùng mã và không ghi audit thành công khi lưu thất bại.
4. **Fail fast về wiring:** truyền `null` cho dependency bắt buộc bị từ chối.
5. **Quyền quyết định scope:** caller có thể cung cấp repository riêng cho service mới.

**Giới hạn cố ý:** ví dụ dùng `HashMap` nên không có kiểm soát concurrency; việc kiểm tra và lưu trùng khóa nằm trong một phương thức đơn giản chứ không là transaction production. Nếu adapter JDBC thực phải xử lý hai request đồng thời, cần ràng buộc unique/atomicity ở tầng lưu trữ. Việc lưu thành công nhưng audit thất bại cũng cần chính sách riêng nếu audit là bắt buộc; DI tự nó không tạo được transaction xuyên qua hai hệ thống.

## 9. Bước 5 — Di chuyển tất cả caller rồi mới thu hồi cầu nối

Khi production code đã được chuyển sang constructor nhận dependency và điểm lắp ghép đã nằm ở root, có thể xóa constructor mặc định **sau khi đánh giá ảnh hưởng tương thích**:

~~~java
final class OrderService {
    private final OrderRepository repository;
    private final AuditSink audit;

    OrderService(OrderRepository repository, AuditSink audit) {
        this.repository = java.util.Objects.requireNonNull(repository);
        this.audit = java.util.Objects.requireNonNull(audit);
    }

    // Không còn OrderService() tự new các adapter.
}
~~~

Đây là **hướng đích cuối**; không cần áp dụng ngay trong chính commit đưa constructor vào. Với một thư viện public đã phát hành, xóa constructor có thể là **breaking change** cả ở mức mã nguồn lẫn binary compatibility. Có thể đánh dấu deprecated và đặt mốc loại bỏ theo phiên bản, thay vì bỏ đột ngột.

Quy trình migration thích hợp:

1. Tạo constructor mới và giữ đường cũ.
2. Chuyển **một nhóm caller** sang composition root.
3. Kiểm tra behavior, đường lỗi và scope.
4. Chuyển tiếp các caller còn lại, tìm mọi điểm tạo trực tiếp.
5. Khi không còn phụ thuộc vào cầu nối và chính sách tương thích cho phép, bỏ constructor cũ hoặc công bố deprecation.

Nếu một caller thực sự cần cấu hình mặc định có chủ đích, có thể tạo **factory tên rõ ràng ở tầng ứng dụng**. Tránh để service nghiệp vụ tự mang một loạt default hạ tầng không kiểm soát được.

## 10. Scope và quyền sở hữu không được đổi ngầm khi refactor

DI không chỉ thay cú pháp tạo object. Khi chuyển dependency ra composition root, bạn có thể **vô tình đổi vòng đời của nó**.

Trước refactor, mỗi `OrderService` có một `InMemoryOrderRepository` riêng. Sau refactor, nếu root cung cấp cùng một repository cho nhiều service, chúng bỗng **chia sẻ dữ liệu**. Điều đó có thể là mục tiêu hoặc là một bug.

Tương tự, nếu trước đây service mở kết nối cho từng thao tác nhưng root chuyển sang tạo một session duy nhất cho toàn ứng dụng, bạn có thể tạo lỗi thread safety hoặc lẫn transaction. Không nên coi “ít lệnh `new` hơn” đồng nghĩa với thiết kế tốt hơn.

| Câu hỏi kiểm tra | Vì sao quan trọng |
| --- | --- |
| Dependency trước đây được tạo **mỗi service/mỗi request/mỗi lần gọi**? | Giữ hoặc chủ động thay đổi scope dựa trên yêu cầu thực |
| Nó có trạng thái mutable không? | Chia sẻ instance có thể tạo tranh chấp hoặc rò rỉ dữ liệu |
| Nó có `close()` hoặc giữ resource ngoài không? | Phải chỉ rõ ai là owner sau khi chuyển |
| Có nhiều service dùng chung nó không? | Đảm bảo đúng instance được tiêm khi cần chia sẻ |
| Có callback hoặc async task còn chạy sau khi method trả về không? | Resource phải sống đến lần sử dụng cuối |
| Có DI container quản lý nó sau migration không? | Xác minh cách container tạo, quản lý và đóng instance theo registration |

### Ví dụ ownership khi chuyển một repository JDBC

Giả sử root tạo `ConnectionPool` dùng chung, rồi tạo `JdbcOrderRepository(pool)`, cuối cùng tiêm repository vào `OrderService`. Khi đó:

- **Composition root hoặc lifecycle manager** thường sở hữu pool.
- `JdbcOrderRepository` **mượn** pool; không nên tự đóng pool sau một lệnh `save`.
- Một transaction/connection được mượn cho từng thao tác phải được trả theo hợp đồng của adapter.
- Service nghiệp vụ không được gọi `pool.close()` vì không sở hữu pool.

Vì vậy refactor constructor injection cần đi kèm việc **định nghĩa ownership**. Không nên đẩy phương thức `close()` vào mọi consumer chỉ vì trước đó consumer từng tạo resource trực tiếp.

## 11. Thứ tự refactor khi có nhiều dependency

Trong một class có 5–10 dependency, việc đưa tất cả ra constructor ngay có thể gây xung đột code và khiến kiểm thử khó tập trung. Có thể ưu tiên theo tiêu chí:

- **Phụ thuộc gây side effect khó kiểm soát** như database, network, filesystem.
- **Phụ thuộc làm test không ổn định** như đồng hồ hệ thống, random generator, biến môi trường.
- **Phụ thuộc cần thay implementation theo môi trường**.
- **Phụ thuộc có scope/ownership chưa rõ**.
- **Phụ thuộc đang làm tăng trách nhiệm của class**.

Một thứ tự điển hình: tách port cho repository → inject repository → inject notifier/audit → đưa cấu hình và clock ra root → xác định vòng đời resource → chuyển caller → bỏ đường cũ.

Đừng biến DI thành mục tiêu “mỗi field có một interface”. Những đối tượng giá trị như `Order`, `Receipt`, `Money` hoặc collection phục vụ một thuật toán có thể vẫn được tạo cục bộ. Constructor nên biểu diễn **những cộng tác viên dài hạn bắt buộc để object thực hiện trách nhiệm**, không trở thành nơi nhận mọi tham số phương thức.

### Nếu constructor đã có quá nhiều tham số?

Đó có thể là tín hiệu class đang gánh quá nhiều trách nhiệm, không nhất thiết là vấn đề giải quyết bằng một “bag of services” hoặc service locator. Hãy xem xét:

- Có thể tách một nhóm trách nhiệm thành collaborator rõ ràng không?
- Có nhiều dependency chỉ được dùng trong một phương thức và phù hợp để truyền qua method parameter không?
- Có cấu hình **giá trị** nào nên nhóm thành immutable config có tên không?
- Những dependency nào thực sự bắt buộc để object luôn ở trạng thái hợp lệ?

Tránh đưa mọi thứ vào `Map<String, Object>` hoặc một `GlobalServices.get(...)`. Chúng giấu phụ thuộc thay vì giải quyết vấn đề thiết kế.

## 12. Cạm bẫy trong quá trình chuyển

### 12.1. Đổi mọi thứ trong một lần

Tách port, thay database, đổi strategy retry, thêm cache và sửa nghiệp vụ cùng lúc khiến rất khó xác định lỗi đến từ đâu. Giữ mỗi bước đủ nhỏ để rollback và so sánh kết quả.

### 12.2. Dùng fallback cho null để tránh sửa caller

~~~java
OrderService(OrderRepository repository) {
    this.repository = repository == null
            ? new InMemoryOrderRepository()
            : repository;
}
~~~

Cách này che lỗi cấu hình và có thể khiến production âm thầm chạy với kho trong bộ nhớ. Với dependency bắt buộc, dùng `requireNonNull` và sửa wiring ở composition root.

### 12.3. Vừa dùng constructor injection vừa tiếp tục new trong method

~~~java
void place(Order order) {
    OrderRepository repository = new InMemoryOrderRepository();
    repository.save(order);
}
~~~

Dù constructor đã nhận `repository`, việc tự tạo repository bên trong method vẫn bỏ qua instance đã tiêm. Hãy dùng `this.repository` đúng nhất quán ở mọi đường code.

### 12.4. Đưa dependency vào static global registry

Thay `new X()` bằng `GlobalRegistry.get(X.class)` trong service chuyển việc tạo đối tượng thành **tra cứu phụ thuộc ngầm**. Caller/test vẫn khó nhìn thấy và thay thế quan hệ phụ thuộc. Constructor injection phù hợp hơn cho dependency bắt buộc.

### 12.5. Giữ constructor mặc định vĩnh viễn dù nó chọn hạ tầng

Một constructor mặc định cần giữ tương thích tạm thời có thể hữu ích. Nhưng để nó trở thành đường production lâu dài làm phân tán cấu hình, che cách lựa chọn adapter và khó chứng minh scope. Theo dõi việc loại bỏ như một bước migration riêng.

### 12.6. Thay đổi instance identity ngoài ý muốn

Ví dụ chuyển từ mỗi service một `InMemoryOrderRepository` riêng sang một repository dùng chung thay đổi kết quả quan sát được. Phải quyết định và test scope theo yêu cầu, không tự cho là tương đương.

### 12.7. Không có đường cleanup khi chuyển quyền tạo

Khi root bắt đầu tạo pool/client dùng chung, nó cũng cần quy tắc đóng sau khi các consumer ngừng sử dụng. Nếu một factory vẫn tạo session theo từng lời gọi, mỗi session tiếp tục cần owner và cleanup riêng.

### 12.8. Dùng unit test fake thay cho kiểm thử wiring thật

Unit test chứng minh service hoạt động với dependency được tiêm; nó **không chứng minh** production root đã nối đúng repository, audit sink, config và scope. Cần thêm một số test wiring/integration phù hợp khi chuyển caller.

## 13. Kiểm thử trong từng lát refactor

Mỗi lát nên có **điểm dừng để xác nhận**, không chỉ chạy test cuối cùng.

| Lát thay đổi | Điều nên kiểm tra |
| --- | --- |
| Trước refactor | Hành vi hiện có ở API và side effect quan trọng |
| Sau tạo interface/port | Không thay đổi kết quả; adapter cũ vẫn triển khai đúng |
| Sau inject repository | Test có thể tiêm fake lỗi; caller cũ vẫn chạy |
| Sau inject audit | Event đúng khi thành công, không phát success khi lưu thất bại |
| Sau chuyển composition root | Production dùng đúng adapter, đúng cùng instance khi cần |
| Sau sửa scope/lifecycle | Có quy tắc đóng tài nguyên, không giữ context ngắn hạn quá lâu |
| Sau bỏ đường cũ | Không còn caller phụ thuộc constructor mặc định; kiểm tra compatibility theo chính sách |

Trong ví dụ `Main.java`, các phép kiểm `check(...)` là test bằng Java thuần để người học tập trung vào DI. Trong dự án thật có thể dùng JUnit và test double framework, nhưng cần giữ nguyên nguyên tắc: **test behavior và contract trước, chi tiết tương tác nội bộ sau**.

Một *wiring test* có thể tạo object graph như production và xác minh đúng implementation được cung cấp; một *integration test* với database thật cần kiểm tra constraint và quản lý transaction. Đừng cố kiểm tra mọi thứ bằng một loại test duy nhất.

## 14. Checklist trước khi xem một đợt refactor đã hoàn tất

Có thể rà soát ngắn gọn theo các nhóm:

**Hành vi:** đầu vào, đầu ra, ngoại lệ và side effect quan trọng vẫn giữ theo hợp đồng đã chọn. Những lỗi sửa thêm được tách rõ khỏi refactor cấu trúc.

**Độ hiển thị dependency:** constructor nêu đủ cộng tác viên bắt buộc; dependency không còn bị ẩn trong lệnh `new` của use case, static registry hoặc đọc môi trường bên trong service.

**Composition root:** tạo và cấu hình adapter theo môi trường; cung cấp đúng instance vào đúng consumer; chọn scope có chủ đích.

**Vòng đời:** resource do root/factory tạo có owner rõ ràng; không đóng resource được mượn hoặc quên đóng resource caller-owned; task async được xử lý theo vòng đời thật.

**Kiểm thử:** có characterization test, unit test qua fake và test wiring/integration khi cần; assertion không trói buộc tùy tiện vào helper hoặc thứ tự gọi nội bộ.

**Tương thích:** constructor cũ được giữ/deprecate/bỏ theo một kế hoạch công bố; không để fallback ẩn gây sai cấu hình production.

## 15. Bài tập thực hành

**Bài 1 — Chia refactor thành ba commit.** Một `ReportService` tự tạo `JdbcReportRepository` và `EmailSender`. Đề xuất ba commit nhỏ để đưa hai dependency ra constructor mà caller cũ vẫn chạy trong giai đoạn chuyển. Ghi test bảo vệ ở cuối từng commit.

**Bài 2 — Test lỗi lưu.** Với `Main.java`, thay fake repository bằng implementation ném `IllegalStateException` tại `save()`. Xác minh service truyền lỗi và không ghi sự kiện audit thành công.

**Bài 3 — Scope.** Hai service cần đọc cùng trạng thái trong một repository bộ nhớ, nhưng các request khác nhau phải dùng `RequestContext` riêng. Hãy vẽ composition root tạo dependency dùng chung và scope theo request; giải thích tại sao không được dùng một context toàn cục.

**Bài 4 — Quy tắc ownership.** Trong quá trình refactor, service chuyển từ tự tạo HTTP client sang nhận client do root cấp. Ai đóng client? Nếu client đã được service khác dùng chung, việc service cũ gọi `close()` có vấn đề gì?

**Bài 5 — Constructor compatibility.** Một thư viện đã công bố `OrderService()`. Hãy đề xuất lộ trình chuyển sang `OrderService(OrderRepository, AuditSink)` có chú ý đến deprecation và khả năng tương thích nguồn/binary.

## 16. Tự kiểm tra mức độ hiểu

**Câu 1.** Vì sao nên có characterization test trước refactor? **Để** quan sát và bảo vệ behavior quan trọng, tránh vô tình đổi nghiệp vụ trong lúc thay cấu trúc phụ thuộc.

**Câu 2.** Có cần đưa tất cả dependency ra constructor trong một commit không? **Không.** Có thể đưa từng dependency, giữ đường tạo cũ tạm thời và kiểm tra ở mỗi điểm.

**Câu 3.** Constructor mặc định gọi `this(new DefaultRepository(), new DefaultAudit())` có luôn là thiết kế cuối tốt không? **Không.** Nó hữu ích như cầu nối tương thích; về lâu dài, nơi lắp ghép nên quyết định adapter và scope rõ ràng.

**Câu 4.** Vì sao không nên cho phép `null` rồi tự tạo repository mặc định? **Vì** che lỗi wiring và có thể khiến production chạy với implementation không mong muốn.

**Câu 5.** Sau refactor, vì sao cần quan tâm đến resource ownership? **Vì** vị trí tạo pool/client đã đổi, nên người đóng và thời điểm đóng phải được xác định để tránh rò rỉ hoặc đóng sớm.

**Câu 6.** Unit test với fake có thay thế được integration test composition root không? **Không.** Unit test kiểm tra behavior của service; integration/wiring test kiểm tra lựa chọn adapter, scope, lifecycle và hạ tầng thật.

## Ghi nhớ

- **Refactor sang DI theo từng lát nhỏ**: bảo vệ hành vi trước, tạo seam, đưa một dependency ra constructor, kiểm tra, rồi mới chuyển dependency tiếp theo.
- **Constructor injection** công khai dependency bắt buộc; dùng `Objects.requireNonNull` thay vì fallback ngầm gây che lỗi cấu hình.
- **Constructor chaining** có thể giữ caller cũ hoạt động trong giai đoạn chuyển, nhưng đường tạo mặc định phải có **kế hoạch thu hồi hoặc chính sách tương thích rõ**.
- **Composition root** là nơi chọn implementation, tạo đúng instance, quyết định scope và quản lý resource. Đừng thay lệnh `new` bằng service locator hoặc global registry.
- **Giữ behavior không có nghĩa giữ mọi chi tiết implementation**. Kiểm thử kết quả/side effect quan trọng sau mỗi bước, rồi bổ sung wiring/integration test để xác nhận object graph production.
