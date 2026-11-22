# Giới hạn của setter, lazy và provider khi chỉ dùng để che vòng

Khi xây dựng **đồ thị đối tượng** (*object graph*) bằng Dependency Injection (DI), đôi lúc hai service cần tham chiếu lẫn nhau: A cần B trong constructor, còn B lại cần A. Mã lắp ghép bằng Java thuần không biết nên tạo đối tượng nào trước. Một cách chữa nhanh thường gặp là chuyển một dependency sang setter injection, trì hoãn nó bằng `Supplier`/**lazy**, hoặc inject một **provider** để lấy đối tượng về sau. Những kỹ thuật đó có thể giúp chương trình khởi động, nhưng **không nhất thiết xóa quan hệ phụ thuộc vòng**.

Trong module **Dependency Injection / Inversion of Control (IoC)**, việc nắm giới hạn này giúp bạn phân biệt ba vấn đề: *đồ thị mã nguồn*, *đồ thị phụ thuộc khi khởi tạo* và *chuỗi lời gọi lúc chạy*. Từ đó bạn có thể dùng constructor injection, composition root và cơ chế quản lý scope/vòng đời để sửa nguyên nhân thiết kế trước khi cân nhắc DI container.

Sau bài này, bạn có thể:

- Nhận diện vòng phụ thuộc trực tiếp và gián tiếp trong đồ thị đối tượng.
- Giải thích vì sao một chu trình constructor làm mã lắp ghép thủ công bị mắc kẹt.
- Phân tích chính xác setter, lazy và provider thay đổi **thời điểm lấy đối tượng** ra sao, và phần nào của vòng vẫn còn.
- Phân biệt lỗi khởi tạo với vòng lặp lời gọi gây `StackOverflowError`.
- Tái cấu trúc các service theo ranh giới trách nhiệm để loại bỏ vòng, rồi kiểm thử bằng Java thuần.
- Biết khi nào lazy/provider thực sự phù hợp với nhu cầu hiệu năng, scope hoặc tạo đối tượng theo yêu cầu.

## 1. Một vòng phụ thuộc là gì?

Ta biểu diễn đồ thị phụ thuộc bằng **đỉnh** là các đối tượng hoặc vai trò service và **cạnh có hướng** là quan hệ “A cần B”. Nếu đường đi từ một đỉnh quay trở về chính nó, đồ thị có **chu trình** (*cycle*).

Ví dụ:

~~~mermaid
flowchart LR
    O["OrderService"] -->|"cần"| A["AuditService"]
    A -->|"cần"| O
~~~

Nếu mở rộng thành chu trình gián tiếp, ta có thể gặp:

~~~mermaid
flowchart LR
    C["CheckoutService"] --> P["PaymentService"]
    P --> R["RiskService"]
    R --> C
~~~

Với một đồ thị chỉ gồm các phụ thuộc **bắt buộc khi tạo bằng constructor**, không có thứ tự khởi tạo tuyến tính hoàn chỉnh: muốn tạo `CheckoutService` phải có `PaymentService`; muốn có `PaymentService` phải có `RiskService`; muốn có `RiskService` lại phải có `CheckoutService`.

Để phân tích chính xác, phân biệt ba lớp quan hệ:

| Góc nhìn | Cạnh mô tả gì? | Vòng dẫn tới điều gì? |
| --- | --- | --- |
| **Phụ thuộc mã nguồn** | Lớp/module A tham chiếu kiểu hoặc interface B | Ghép nối và hướng phụ thuộc khó bảo trì, có thể là vấn đề kiến trúc |
| **Phụ thuộc khởi tạo** | Muốn tạo instance A hoàn chỉnh phải có instance B trước | Composition root không tìm được thứ tự constructor thuần túy |
| **Lời gọi lúc chạy** | Khi thực thi, phương thức A gọi phương thức B | Nếu lời gọi nối tiếp quay lại vô hạn có thể tràn ngăn xếp |

Một chu trình trong quan hệ đối tượng **không phải lúc nào cũng là lỗi**. Ví dụ, dữ liệu dạng cây có thể giữ tham chiếu parent ↔ child, hoặc callback có chủ đích có thể đi ngược tới chủ sở hữu. Điều cần đánh giá là **ai chịu trách nhiệm điều phối**, **đối tượng có hoàn chỉnh khi được dùng không**, **vòng đời có hợp lệ không**, và **lời gọi có điều kiện dừng không**.

Bài này tập trung vào trường hợp đáng nghi: **hai service nghiệp vụ/ứng dụng cần lẫn nhau để được khởi tạo hoặc hoạt động**, rồi dùng kỹ thuật injection để che dấu hiệu đó.

## 2. Vì sao constructor injection làm lộ vòng?

Xem hai lớp sau (đây là ví dụ minh họa cấu trúc):

~~~java
import java.util.Objects;

final class OrderService {
    private final AuditService audit;

    OrderService(AuditService audit) {
        this.audit = Objects.requireNonNull(audit);
    }
}

final class AuditService {
    private final OrderService orders;

    AuditService(OrderService orders) {
        this.orders = Objects.requireNonNull(orders);
    }
}
~~~

Hai lớp **có thể biên dịch**, nhưng nếu mỗi constructor yêu cầu một đối tượng còn lại đã được tạo xong, composition root không thể lắp ghép bằng các lời gọi constructor thông thường:

~~~java
// Mã giả để thấy bế tắc, không phải đoạn Java có thể biên dịch:
OrderService orders = new OrderService(audit); // audit từ đâu?
AuditService audit = new AuditService(orders); // orders phải có trước
~~~

Một số cách “lách” như truyền `null` rồi điền lại về sau phá điều kiện bắt buộc trong constructor; dùng đối tượng giả/chưa được gắn đầy đủ chỉ chuyển lỗi từ lúc khởi tạo sang lúc thực thi.

**Tác dụng tích cực của constructor injection:** phụ thuộc bắt buộc hiện rõ trên chữ ký. Nếu rơi vào chu trình, việc không thể lắp ghép thẳng buộc ta xem lại thiết kế, thay vì để trạng thái chưa sẵn sàng len vào runtime.

### Đồ thị có thể lắp theo thứ tự nào?

Một đồ thị không có vòng trên các cạnh bắt buộc lúc khởi tạo cho phép sắp xếp các bước tạo đối tượng theo dependency trước, consumer sau. Chẳng hạn:

~~~mermaid
flowchart LR
    Root["Composition root"] --> Store["OrderStore"]
    Root --> Audit["AuditTrail"]
    Root --> Service["OrderService"]
    Store -.->|"được truyền vào"| Service
    Audit -.->|"được truyền vào"| Service
~~~

Composition root có thể tạo `OrderStore` và `AuditTrail` trước, rồi truyền hai đối tượng này vào constructor `OrderService`. Đây là một đồ thị dễ hiểu, có điều kiện khởi tạo rõ ràng.

Trong hệ thống phức tạp, có thể phát hiện chu trình qua **topological sort** hoặc thành phần liên thông mạnh (*strongly connected components*) của đồ thị phụ thuộc. Nhưng công cụ phát hiện chỉ cho biết **ở đâu có vòng**, còn cách sửa thường cần xem trách nhiệm nghiệp vụ.

## 3. Setter injection: giải bài toán thứ tự bằng cách tạo đối tượng chưa hoàn chỉnh

Setter injection đưa dependency vào sau khi instance đã được tạo. Ta có thể lắp một vòng như sau:

~~~java
import java.util.Objects;

final class A {
    private B b;

    void setB(B b) {
        this.b = Objects.requireNonNull(b);
    }

    void work() {
        if (b == null) {
            throw new IllegalStateException("A chưa được lắp ghép");
        }
        b.handle();
    }
}

final class B {
    private final A a;

    B(A a) {
        this.a = Objects.requireNonNull(a);
    }

    void handle() {
        System.out.println("B đã xử lý");
    }
}

// Mã tại composition root:
A a = new A();
B b = new B(a);
a.setB(b);
a.work();
~~~

Ví dụ này minh họa **khả năng khép vòng tham chiếu** bằng bước setter; phương thức `B.handle()` chưa sử dụng tham chiếu ngược vì đang tập trung vào cơ chế lắp ghép. Trong hệ thống thực tế, nếu B giữ A để gọi một hành vi nào đó, cần xem vì sao B phải biết toàn bộ A và liệu có thể thay bằng dữ liệu, hợp đồng nhỏ hơn hay đối tượng điều phối.

Điểm đánh đổi của setter:

- Sau `new A()`, A đã tồn tại nhưng chưa sẵn sàng; cần thêm `setB` trước khi gọi `work`.
- Một lời gọi tới A hoặc B trong lúc đang lắp ghép có thể quan sát trạng thái trung gian.
- Phụ thuộc bắt buộc không còn hiện rõ ở constructor, nên unit test và những entry point khác dễ quên bước gán.
- Nếu setter cho phép gọi nhiều lần, tham chiếu có thể thay đổi khi service đang hoạt động; việc này đòi hỏi quy tắc vòng đời và an toàn luồng.
- Quan hệ A → B → A vẫn tồn tại sau khi lắp ghép; việc tạo được đối tượng **không chứng minh thiết kế đã hết vòng**.

**Setter injection hợp lý khi cấu hình thật sự có thể tùy chọn hoặc thay đổi sau lúc tạo**, và các trạng thái trước/sau cấu hình được định nghĩa rõ. Nếu dùng setter chỉ để chạy vòng một chu trình constructor bắt buộc, hãy coi đó là tín hiệu cần đánh giá lại trách nhiệm.

## 4. Lazy injection: dời thời điểm sử dụng, không tự xóa quan hệ

**Lazy** nghĩa là chỉ tính toán, khởi tạo hoặc lấy một dependency khi có nhu cầu đầu tiên, thay vì ngay lúc xây dựng đối tượng chứa nó. Java thuần có thể biểu diễn ý tưởng này bằng `Supplier<T>`:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

final class ReportService {
    private final Supplier<ReportClient> client;

    ReportService(Supplier<ReportClient> client) {
        this.client = Objects.requireNonNull(client);
    }

    void generate() {
        client.get().sendRequest();
    }
}
~~~

Đây có thể là thiết kế tốt nếu `ReportClient` khởi tạo đắt và chỉ một số đường nghiệp vụ cần nó. Nhưng một supplier được cấp **không bảo đảm** rằng nó chỉ tạo một đối tượng, cũng không tự an toàn luồng, tự cache hoặc tự quản lý thời điểm đóng. Điều đó phụ thuộc cách implement supplier.

Nếu đưa lazy vào một vòng A → B → A, ta có thể chỉ biến cạnh trực tiếp thành cạnh gián tiếp:

~~~mermaid
flowchart LR
    A["A"] --> S["Supplier&lt;B&gt;"]
    S -->|"get() khi chạy"| B["B"]
    B --> A
~~~

Thực chất, A vẫn có khả năng cần B và B vẫn cần A. Đồ thị khởi tạo tại thời điểm đầu có thể không buộc tạo B ngay, nhưng **đồ thị phụ thuộc hành vi của ứng dụng vẫn chứa vòng**. Nếu `get()` được gọi trong constructor hoặc trong một bước callback khởi động khi B chưa sẵn sàng, vòng hoặc lỗi khởi tạo có thể xuất hiện trở lại.

### Ví dụ hoãn lỗi bằng supplier

Đoạn dưới sử dụng `AtomicReference` để cho thấy một supplier có thể truy cập dependency đã được gán *về sau*:

~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

final class A {
    private final Supplier<B> next;

    A(Supplier<B> next) {
        this.next = Objects.requireNonNull(next);
    }

    void run() {
        next.get().execute();
    }
}

final class B {
    private final A previous;

    B(A previous) {
        this.previous = Objects.requireNonNull(previous);
    }

    void execute() {
        System.out.println("B thực thi");
    }
}

// Mã minh họa tại composition root:
AtomicReference<B> slot = new AtomicReference<>();
A a = new A(() -> Objects.requireNonNull(
        slot.get(), "B chưa được lắp ghép"));
B b = new B(a);
slot.set(b);
a.run();
~~~

`AtomicReference` trong ví dụ chỉ làm cho việc đọc/ghi tham chiếu có quy tắc hiển thị giữa các thread; nó **không thay thế một giao thức khởi tạo đúng** và không tự bảo vệ việc sử dụng object chưa sẵn sàng. Cấu trúc A → supplier → B → A vẫn là vòng.

Nếu gọi `a.run()` trước `slot.set(b)`, lỗi sẽ xuất hiện ở runtime. Nếu `B.execute()` lại gọi `previous.run()` vô điều kiện, lời gọi A → B → A → B sẽ lặp mãi và cuối cùng có thể gây `StackOverflowError`. Lazy không cung cấp điều kiện dừng cho luồng nghiệp vụ.

## 5. Provider: thay thời điểm lấy dependency, nhưng ai chịu trách nhiệm?

**Provider** là một abstraction cung cấp hoặc tra cứu dependency khi phương thức `get()` được gọi. Trong Java thuần, ta có thể dùng `Supplier<T>` như một provider đơn giản. Các DI container có thể cung cấp provider riêng, gắn với scope, cấu hình hoặc quản lý lifecycle.

Điểm cần phân biệt:

| Cơ chế | Điều nó thường thay đổi | Điều nó **không** tự bảo đảm |
| --- | --- | --- |
| Constructor injection trực tiếp | Yêu cầu instance hợp lệ ngay lúc tạo consumer | Không tự sửa kiến trúc hoặc chính sách vòng đời |
| Setter injection | Cho phép bổ sung/thay dependency sau khi tạo consumer | Không loại bỏ back-reference hoặc bảo đảm trạng thái sẵn sàng |
| Lazy dependency | Trì hoãn khởi tạo/lấy đối tượng đến khi dùng | Không nhất thiết cache, không tự phá chu trình |
| Provider / factory | Đưa thao tác lấy hoặc tạo dependency thành hợp đồng rõ ràng | Không tự đảm bảo scope đúng, không xóa chu trình nghiệp vụ |

Ví dụ provider có mục đích rõ ràng và **không tạo vòng**: mỗi lần gửi tệp cần một phiên xử lý mới.

~~~java
import java.util.Objects;
import java.util.function.Supplier;

interface UploadSession extends AutoCloseable {
    void send(byte[] data);
    @Override
    void close();
}

final class UploadService {
    private final Supplier<UploadSession> sessions;

    UploadService(Supplier<UploadSession> sessions) {
        this.sessions = Objects.requireNonNull(sessions);
    }

    void upload(byte[] bytes) {
        Objects.requireNonNull(bytes, "bytes");
        try (UploadSession session = sessions.get()) {
            Objects.requireNonNull(session, "session").send(bytes);
        }
    }
}
~~~

Ở đây, provider hỗ trợ **scope mỗi lần thao tác**: `UploadService` có thể sống lâu, còn `UploadSession` được tạo và đóng trong từng lần gọi `upload`. Đó là lý do sử dụng provider có ý nghĩa về vòng đời. Để chương trình hoạt động đúng, factory được inject phải thực sự trả về session mới hoặc session có quyền sở hữu phù hợp; không được trả về đối tượng dùng chung rồi để mỗi yêu cầu đóng nó.

Ngược lại, nếu `A` được inject `Provider<B>` chỉ để B có thể được tạo với `A`, ta mới **trì hoãn việc truy cập B**, chưa giải thích được tại sao A và B cần nhau. Đừng biến provider thành **service locator toàn cục** để mọi lớp tự tra cứu tùy ý: cách đó che mờ các phụ thuộc và đẩy quyết định lắp ghép vào mã nghiệp vụ.

## 6. Khi nào vòng thực sự nguy hiểm?

Không phải mọi chu trình đều có cùng mức độ rủi ro. Hãy xem vòng qua bốn câu hỏi:

1. **Vòng của cái gì?** Đây là chu trình giữa các constructor, giữa các module mã nguồn hay chỉ là back-reference của dữ liệu?
2. **Đối tượng hoàn chỉnh lúc nào?** Có ai quan sát service trước khi setter/provider hoàn tất không?
3. **Khi chạy có điều kiện dừng không?** A gọi B rồi B gọi A có thể là callback một lần, hay là recursion vô hạn?
4. **Vòng đời có xung đột không?** Một singleton có giữ đối tượng theo request, hoặc provider trả về tài nguyên cần đóng mà không ai quản lý không?

Một số hệ quả thường gặp:

| Triệu chứng | Căn nguyên có thể | Vì sao mẹo injection chưa đủ |
| --- | --- | --- |
| Container báo circular dependency / không dựng được bean | Chu trình constructor bắt buộc | Setter/lazy có thể giúp hoãn nhưng vẫn còn quan hệ hai chiều |
| `NullPointerException` hoặc lỗi chưa khởi tạo | Đối tượng được dùng trước khi setter chạy | Tách hai pha tạo và cấu hình mở ra trạng thái trung gian |
| `StackOverflowError` trong một use case | Lời gọi A → B → A không có điểm dừng | Lazy/provider chỉ đổi cách lấy instance, không sửa logic gọi |
| Cùng một dependency bị tạo nhiều lần ngoài ý muốn | Supplier/provider tạo instance mỗi `get()` | Cần quy định cache và scope cụ thể |
| Test chạy qua container nhưng `new Service()` lỗi | Dependency ẩn trong field/provider và cấu hình | Constructor tường minh hoặc factory cụ thể giúp test dễ dựng hơn |
| Tài nguyên bị đóng quá sớm hoặc rò | Không rõ bên sở hữu khi cấp bằng provider | Phải xác lập ownership và trách nhiệm `close()` |
| Thay đổi nhỏ ở B kéo theo A, rồi lại B | Hai service chia sẻ trách nhiệm hoặc biết quá nhiều về nhau | Cần refactor ranh giới, không chỉ đổi cơ chế inject |

**Đừng coi việc container khởi động thành công là bằng chứng đồ thị hợp lý.** Một container có thể hỗ trợ proxy, deferred lookup hoặc một số loại circular reference theo cấu hình; thành công kỹ thuật ở bước tạo đối tượng không đồng nghĩa quan hệ nghiệp vụ đã rõ ràng.

## 7. Sửa nguyên nhân: cắt cạnh phụ thuộc không cần thiết

Một bài toán thường gặp là:

- `OrderService` tạo đơn hàng và muốn ghi audit.
- `AuditService` muốn tra cứu chi tiết đơn, nên lại tham chiếu `OrderService`.

Sơ đồ ban đầu:

~~~mermaid
flowchart LR
    Order["OrderService"] --> Audit["AuditService"]
    Audit --> Order
~~~

Vòng này có thể đến từ việc `AuditService` đang nhận **quá nhiều quyền truy cập**: nó chỉ cần vài thuộc tính của đơn nhưng lại nhận toàn bộ `OrderService`. Nếu `OrderService` đã có đủ dữ liệu khi tạo đơn, hãy truyền dữ liệu đó trong lời gọi audit:

~~~mermaid
flowchart LR
    Root["Composition root"] --> Store["OrderStore"]
    Root --> Audit["AuditTrail"]
    Root --> Order["OrderService"]
    Order --> Store
    Order --> Audit
    Audit -.-> Event["OrderPlaced: dữ liệu sự kiện"]
    Order -.->|"truyền dữ liệu"| Event
~~~

Các bước refactor:

1. Xác định **lý do thật sự** khiến AuditService cần OrderService.
2. Nếu chỉ cần mã đơn, số tiền và thời điểm, định nghĩa một giá trị dữ liệu như `OrderPlaced`.
3. Cho `OrderService` gọi `audit.record(event)` và chuyển **dữ liệu cần thiết** qua tham số.
4. `AuditTrail` không tham chiếu lại `OrderService`; triển khai audit có thể ghi log/file/DB mà không truy xuất toàn bộ use case.
5. Lắp ghép những port độc lập ở composition root rồi truyền vào constructor `OrderService`.

Cách này giải quyết **nguyên nhân**: một collaborator đang phụ thuộc ngược vào consumer chỉ để lấy dữ liệu đã có sẵn. Tuy nhiên, nếu audit thực sự cần truy vấn trạng thái dài hạn, có thể trích xuất một **port đọc nhỏ** (ví dụ `OrderLookup`) do một adapter riêng triển khai và cho cả hai service dùng, thay vì cho audit phụ thuộc ngược vào toàn bộ service.

### Các mẫu tái cấu trúc khác

| Vòng phụ thuộc ban đầu | Cách xem lại trách nhiệm |
| --- | --- |
| A gọi B để làm việc, B gọi A để lấy ít thông tin | Truyền dữ liệu theo phương thức, hoặc trích xuất cổng truy vấn nhỏ |
| A và B gọi qua lại để điều phối một luồng | Đưa trình tự phối hợp lên service/use case thứ ba, A và B làm các bước độc lập |
| A và B cùng chứa một phần quy tắc giống nhau | Trích xuất chính sách/dịch vụ chung mà cả hai cùng dùng |
| A phụ thuộc B chỉ để thông báo trạng thái | Thiết kế callback/event với hợp đồng, ownership và điều kiện dừng rõ; không để event tự tạo back-reference ngầm |
| B cần một đối tượng theo request trong khi A sống toàn ứng dụng | Chuyển dữ liệu request thành tham số, hoặc inject factory/provider cho **nhu cầu scope thực sự** |

Đổi tên class hoặc tạo một interface trỏ ngược về A **không tự làm mất vòng**. Cần kiểm tra lại đường đi của các cạnh sau refactor: nếu A → B → InterfaceOfA → A thì chu trình logic vẫn còn.

## 8. Thực hành bằng Java thuần: đồ thị không vòng, phụ thuộc tường minh

Dưới đây là chương trình Java 17+ hoàn chỉnh cho ví dụ đặt đơn và ghi audit. `OrderService` không tự tạo adapter, `AuditTrail` không giữ tham chiếu ngược tới `OrderService`. Composition root tạo các dependency độc lập rồi truyền vào constructor.

Lưu toàn bộ đoạn mã vào `Main.java`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

record Order(String id, long amountInCents) {
    Order {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Ma don khong hop le");
        }
        if (amountInCents <= 0) {
            throw new IllegalArgumentException("So tien phai duong");
        }
    }
}

// Giá trị sự kiện chứa dữ liệu đủ dùng cho audit.
record OrderPlaced(
        String orderId,
        long amountInCents,
        Instant occurredAt) {}

interface OrderStore {
    void add(Order order);
}

interface AuditTrail {
    void record(OrderPlaced event);
}

final class InMemoryOrderStore implements OrderStore {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public void add(Order order) {
        Objects.requireNonNull(order, "order");
        if (orders.putIfAbsent(order.id(), order) != null) {
            throw new IllegalArgumentException(
                    "Ma don da ton tai: " + order.id());
        }
    }

    boolean contains(String id) {
        return orders.containsKey(id);
    }
}

final class InMemoryAuditTrail implements AuditTrail {
    private final List<OrderPlaced> events = new ArrayList<>();

    @Override
    public void record(OrderPlaced event) {
        events.add(Objects.requireNonNull(event, "event"));
    }

    List<OrderPlaced> events() {
        return List.copyOf(events);
    }
}

// Service nghiệp vụ nhận các collaborator qua constructor.
final class OrderService {
    private final OrderStore store;
    private final AuditTrail audit;
    private final Clock clock;

    OrderService(OrderStore store, AuditTrail audit, Clock clock) {
        this.store = Objects.requireNonNull(store, "store");
        this.audit = Objects.requireNonNull(audit, "audit");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    void place(Order order) {
        Objects.requireNonNull(order, "order");
        store.add(order);
        audit.record(new OrderPlaced(
                order.id(),
                order.amountInCents(),
                clock.instant()));
    }
}

// Composition root: không cần setter, lazy hay provider để che vòng.
public class Main {
    public static void main(String[] args) {
        InMemoryOrderStore store = new InMemoryOrderStore();
        InMemoryAuditTrail audit = new InMemoryAuditTrail();

        OrderService service =
                new OrderService(store, audit, Clock.systemUTC());

        service.place(new Order("ORD-001", 125_000));

        System.out.println("Da luu: " + store.contains("ORD-001"));
        System.out.println("So su kien audit: " + audit.events().size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Đầu ra dự kiến:

~~~text
Da luu: true
So su kien audit: 1
~~~

### Đồ thị nào được tạo?

- `Main` tạo `InMemoryOrderStore` và `InMemoryAuditTrail` trước.
- `Main` truyền chúng, cùng một `Clock`, vào constructor `OrderService`.
- Khi xử lý đơn, `OrderService` gọi `store.add(order)` rồi gửi một **giá trị dữ liệu** `OrderPlaced` tới `audit.record(event)`.
- `InMemoryAuditTrail` không cần biết `OrderService` hay gọi ngược lại nó.

Các cạnh quan trọng:

~~~text
OrderService --> OrderStore
OrderService --> AuditTrail
OrderService --> Clock

InMemoryOrderStore implements OrderStore
InMemoryAuditTrail implements AuditTrail
~~~

Đây là đồ thị lắp ghép đơn giản: có thể tạo mọi dependency trước khi tạo `OrderService`. Nhờ **constructor injection**, dependency bắt buộc tường minh và có thể kiểm tra `null` ngay lúc xây dựng đối tượng.

**Giới hạn ví dụ:** Nếu `store.add` thành công mà `audit.record` thất bại, đơn đã lưu nhưng audit chưa ghi. Việc loại bỏ vòng phụ thuộc **không tự giải quyết** tính nguyên tử hay độ tin cậy sự kiện. Hệ thống thực tế có thể cần giao dịch, outbox hoặc cơ chế retry phù hợp. Ngoài ra, `HashMap` và `ArrayList` minh họa ứng dụng đơn luồng; muốn dùng chung cho nhiều request phải xử lý thread-safety, scope và persistence.

## 9. Kiểm thử hành vi mà không cần DI container

Khi chu trình được cắt tại ranh giới trách nhiệm, việc test service không cần tạo cả đồ thị phức tạp. Ta có thể truyền fake vào constructor và chỉ quan sát những lời gọi thực sự cần.

Tạo `OrderServiceTest.java` trong cùng thư mục với `Main.java`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public class OrderServiceTest {
    public static void main(String[] args) {
        List<String> calls = new ArrayList<>();
        List<OrderPlaced> recorded = new ArrayList<>();

        OrderStore store = order -> calls.add("save:" + order.id());

        AuditTrail audit = event -> {
            calls.add("audit:" + event.orderId());
            recorded.add(event);
        };

        Instant fixed = Instant.parse("2026-01-01T00:00:00Z");
        Clock clock = Clock.fixed(fixed, ZoneOffset.UTC);

        OrderService service = new OrderService(store, audit, clock);
        service.place(new Order("TEST-001", 50_000));

        if (!calls.equals(List.of(
                "save:TEST-001", "audit:TEST-001"))) {
            throw new AssertionError("Sai thu tu loi goi: " + calls);
        }

        if (recorded.size() != 1
                || !recorded.get(0).equals(
                        new OrderPlaced("TEST-001", 50_000, fixed))) {
            throw new AssertionError("Su kien audit sai");
        }

        System.out.println("PASS");
    }
}
~~~

Chạy:

~~~bash
javac Main.java OrderServiceTest.java
java OrderServiceTest
~~~

Kết quả dự kiến: `PASS`.

Test xác nhận rằng service lưu đơn trước khi ghi audit và gửi dữ liệu sự kiện đúng, với thời gian được kiểm soát bằng `Clock.fixed`. Nó không cần database, email, DI framework hoặc cơ chế reflection. Test này không kiểm chứng độ bền dữ liệu hoặc việc adapter audit thật ghi thành công khi gặp sự cố hạ tầng; các yêu cầu đó phải được kiểm thử ở mức tích hợp tương ứng.

## 10. Khi lazy hoặc provider vẫn là lựa chọn tốt

Không nên chuyển mọi lazy/provider thành constructor dependency trực tiếp chỉ vì lo ngại vòng. Chúng giải quyết những nhu cầu có thật nếu được sử dụng đúng mục đích.

**Lazy có ích khi:**

- Đối tượng tạo đắt nhưng không phải luồng nào cũng cần, ví dụ một bộ phân tích tài liệu chỉ dùng khi chức năng đặc biệt được bật.
- Có yêu cầu trì hoãn I/O hoặc khởi động tài nguyên theo một thời điểm xác định.
- Việc tính toán hoặc tạo một đối tượng chỉ có ý nghĩa khi người dùng thực hiện chức năng liên quan.

Cần ghi rõ liệu giá trị được cache một lần hay tạo mới, cách xử lý khi tạo thất bại và đối tượng nào chịu trách nhiệm đóng tài nguyên.

**Provider hoặc factory có ích khi:**

- Một service sống lâu cần tạo collaborator ngắn hạn cho **mỗi request/tác vụ**.
- Đối tượng phụ thuộc vào **dữ liệu chỉ có lúc chạy**, chẳng hạn ID phiên làm việc hoặc cấu hình của mỗi công việc.
- Việc tạo đối tượng có điều kiện thuộc về một quy tắc factory có kiểu rõ ràng.

Một provider đúng nghĩa được cung cấp cho consumer qua constructor và định nghĩa rõ `get()` trả một đối tượng mới hay một đối tượng theo scope nào. Nhu cầu tạo theo request **khác với** việc dùng provider để tìm lại chính consumer và nối một vòng.

**Setter có ích khi:** một cấu hình thật sự tùy chọn hoặc có khả năng thay đổi sau lúc tạo; API cần diễn đạt trạng thái trước/sau cấu hình. Nếu collaborator là bắt buộc để thực hiện mọi phương thức nghiệp vụ, constructor injection thường minh bạch hơn.

### Hai câu hỏi quyết định

1. **Nếu bỏ setter/lazy/provider và thiết kế lại dòng dữ liệu, quan hệ A ↔ B có thực sự cần tồn tại không?** Nếu không, hãy refactor trách nhiệm và loại bỏ cạnh không cần thiết.
2. **Nếu quan hệ vẫn cần, kỹ thuật được chọn có bảo đảm hợp đồng khởi tạo, điều kiện dừng, scope, đồng thời và ownership không?** Nếu không thể giải thích những bảo đảm đó, cách lắp ghép có thể chỉ đang dời lỗi sang runtime.

## 11. Checklist kiểm tra chu trình trong object graph

Khi phát hiện vòng A → B → A hoặc chu trình dài hơn, có thể thực hiện theo thứ tự:

1. **Vẽ các cạnh phụ thuộc bắt buộc:** ghi rõ ai cần ai để tạo instance hoàn chỉnh; không tính quan hệ gọi hàm đơn lẻ thành constructor dependency.
2. **Đánh dấu vòng mã nguồn và vòng runtime riêng biệt:** một vòng lắp ghép không nhất thiết đang gọi đệ quy; một vòng lời gọi cũng có thể xuất hiện khi không có vòng constructor.
3. **Tìm ý định của mỗi cạnh:** A thực sự cần chức năng nào của B? B có chỉ cần một phần dữ liệu đã có ở A không?
4. **Đề xuất ranh giới mới:** chuyển dữ liệu qua phương thức, trích xuất port đọc, đưa điều phối lên use case cấp cao, hoặc tách chính sách dùng chung.
5. **Vẽ lại đồ thị sau refactor:** kiểm tra các dependency bắt buộc đã có thứ tự tạo hợp lệ tại composition root.
6. **Giữ constructor tường minh cho cộng tác viên bắt buộc:** kiểm tra `null`, tránh khởi tạo đối tượng nửa chừng rồi phó mặc cho setter.
7. **Chỉ dùng lazy/provider vì lý do thực tế:** nêu rõ cache, thời điểm tạo, scope, cách xử lý lỗi và ai đóng tài nguyên.
8. **Kiểm thử service bằng fake:** xác minh điều phối và dữ liệu truyền qua hợp đồng; không cần bật toàn bộ hạ tầng.
9. **Kiểm tra kết nối thật ở mức thích hợp:** test adapter, lifecycle, các lỗi I/O và tính nhất quán nếu use case có yêu cầu.
10. **Đánh giá kỹ thuật DI container sau khi hiểu đồ thị:** container tự động lắp ghép không thay thế việc sửa quan hệ phụ thuộc sai.

### Tự kiểm tra

**Tình huống A:** A phụ thuộc vào `Supplier<B>`, còn B phụ thuộc vào A. A gọi `supplier.get()` trong constructor. Lazy đã giải quyết vòng chưa?

**Chưa.** A vẫn yêu cầu lấy B ngay trong lúc tạo, nên lợi ích trì hoãn bị mất. Nếu B cần một A hoàn chỉnh, vấn đề khởi tạo vẫn tồn tại; còn nếu supplier được gán sau, có thêm rủi ro trạng thái chưa sẵn sàng.

**Tình huống B:** A và B được tạo rỗng rồi gọi `a.setB(b)`, `b.setA(a)`. Có thể kết luận code tốt vì đã chạy được không?

**Không.** Đã nối xong hai tham chiếu nhưng chưa chứng minh được sự cần thiết của vòng, tính an toàn trong quá trình lắp ghép hay điều kiện dừng khi gọi qua lại.

**Tình huống C:** Một singleton `JobScheduler` nhận `Supplier<JobContext>` để tạo context mới cho mỗi job, không có cạnh phụ thuộc ngược từ JobContext về scheduler. Có vấn đề vòng không?

**Không theo mô tả này.** Đây là ví dụ provider phù hợp khi factory bảo đảm mỗi job có context đúng scope và được giải phóng đúng lúc.

**Tình huống D:** `AuditTrail` cần mã và tổng tiền của đơn, nhưng lại nhận toàn bộ `OrderService` để tra cứu. Cách sửa đơn giản là gì?

Truyền một `OrderPlaced` bất biến vào `audit.record(event)`, hoặc cho audit phụ thuộc một port đọc nhỏ khi cần truy vấn thật sự. Cách đó loại bỏ nhu cầu audit biết nguyên use case.

**Tình huống E:** Đã bỏ vòng constructor nhưng `A.run()` gọi `B.run()` và `B.run()` lại gọi `A.run()` vô điều kiện. Đã giải quyết xong chưa?

**Chưa.** Đồ thị khởi tạo có thể hợp lệ nhưng luồng gọi vẫn đệ quy vô hạn. Cần sửa điều kiện dừng hoặc trách nhiệm điều phối.

## Ghi nhớ

**Setter, lazy và provider có thể thay đổi *thời điểm* tạo hoặc cung cấp dependency, nhưng không tự thay đổi *lý do* hai thành phần phụ thuộc lẫn nhau.** Nếu chúng chỉ được thêm vào để vượt qua một chu trình, hãy ưu tiên tìm cạnh không cần thiết trong đồ thị: truyền dữ liệu thay vì tham chiếu ngược tới cả service, trích xuất hợp đồng nhỏ hoặc đưa điều phối lên một use case độc lập. Khi đồ thị có ranh giới rõ ràng, **constructor injection** và **composition root** bằng Java thuần dễ kiểm tra hơn, còn DI container, scope và vòng đời được đưa vào đúng nhu cầu.
