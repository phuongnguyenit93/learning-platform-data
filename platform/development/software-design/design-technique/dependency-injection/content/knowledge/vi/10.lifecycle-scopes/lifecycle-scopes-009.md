# Tính nhất quán của danh tính đối tượng trong một đơn vị công việc

Trong một ứng dụng sử dụng **Dependency Injection (DI)**, việc truyền đúng interface vào constructor mới giải quyết phần **cấu trúc phụ thuộc**. Khi nhiều service cùng xử lý một đơn hàng, còn một câu hỏi quan trọng về **vòng đời và phạm vi (lifecycle & scope)**: hai service đang nhìn **cùng một phiên bản đối tượng** hay hai bản sao độc lập đại diện cho cùng một đơn?

Ví dụ, service A tải đơn hàng `ORD-100` rồi giảm giá; service B cũng tải `ORD-100` để duyệt. Nếu mỗi lần tải tạo ra một đối tượng mới, B có thể kiểm tra trạng thái chưa được A cập nhật. Điều này có thể xảy ra ngay cả khi hai đối tượng có cùng mã đơn và các lớp đều nhận dependency bằng constructor injection.

Bài học này tập trung vào **tính nhất quán của danh tính đối tượng trong một đơn vị công việc** (*object identity consistency within a unit of work*): khi cùng một thực thể logic được truy cập nhiều lần trong phạm vi một thao tác nghiệp vụ, hệ thống có thể cần bảo đảm mọi bên nhận **cùng một đối tượng đang được quản lý**. Ta sẽ thực hành bằng **Java thuần**, composition root và scope tự quản lý trước khi liên hệ với persistence context và DI container.

Sau bài này, bạn có thể:

- Phân biệt **danh tính đối tượng Java**, **bằng nhau về giá trị**, và **định danh nghiệp vụ**.
- Mô tả thế nào là một *unit of work*, đâu là ranh giới scope phù hợp và vì sao nó khác singleton.
- Phân tích rủi ro khi hai service nhận repository/session khác nhau trong cùng một thao tác.
- Thiết kế một **Identity Map** bảo đảm một thực thể chỉ có một đối tượng được quản lý trong một unit of work.
- Lắp ghép các service qua constructor injection để chia sẻ đúng unit of work.
- Viết kiểm thử xác minh cùng tham chiếu trong một scope, khác tham chiếu giữa các scope, và việc kết thúc/loại bỏ công việc.
- Nêu rõ những gì Identity Map **không** tự bảo đảm: transaction, đồng thời, tính bền vững và nhất quán giữa nhiều tiến trình.

## 1. Ba khái niệm thường bị nhập làm một

Giả sử có hai đối tượng Java cùng đại diện cho đơn hàng có mã `ORD-100`.

~~~java
Order first = repositoryA.getById("ORD-100");
Order second = repositoryB.getById("ORD-100");
~~~

Cần tách ba câu hỏi:

| Khái niệm | Câu hỏi | Cách quan sát |
| --- | --- | --- |
| **Object identity** (danh tính đối tượng) | Hai biến có trỏ vào **cùng một instance** Java không? | `first == second` |
| **Value equality** (bằng nhau về giá trị) | Hai đối tượng có nội dung được quy ước là bằng nhau không? | `first.equals(second)`, nếu được định nghĩa phù hợp |
| **Business identity** (định danh nghiệp vụ) | Hai đối tượng có đại diện cho **cùng một đơn hàng** không? | `first.id().equals(second.id())`, nếu mã đơn là khóa định danh |

Hai đối tượng có thể có cùng mã đơn nhưng `first != second`. Nếu mỗi đối tượng giữ trạng thái mutable riêng, thay đổi trên `first` không tự xuất hiện trên `second`.

~~~java
// Minh họa: hai bản sao của cùng một bản ghi.
Order first = new Order("ORD-100", 10_000);
Order second = new Order("ORD-100", 10_000);

System.out.println(first == second); // false
~~~

Đoạn minh họa trên giả định có constructor `Order(String, long)`. Trong ví dụ chạy được bên dưới, `Order` sẽ được tạo từ một `OrderSnapshot`.

Lệnh `==` kiểm tra **cùng tham chiếu**, trong khi `equals` có thể so sánh giá trị hoặc business key tùy cách viết lớp. Kể cả khi ta ghi đè `equals` để hai đối tượng cùng ID được xem là bằng nhau, điều đó **không hợp nhất trạng thái**, không biến chúng thành một instance và không khiến hai thay đổi được đồng bộ.

**Bảo đảm cần học trong bài:** *Trong một unit of work, nếu cùng một thực thể được yêu cầu nhiều lần thông qua cùng cơ chế quản lý, các lần truy cập sẽ trả về cùng một instance* (với những ranh giới và tiền điều kiện đã được định nghĩa).

## 2. “Một đơn vị công việc” là phạm vi nào?

**Unit of work** thường chỉ một chuỗi hành động liên quan cùng tạo ra một thay đổi nghiệp vụ hợp lý: ví dụ kiểm tra giá, giảm giá, duyệt đơn và ghi kết quả. Trong thiết kế lưu trữ, *Unit of Work pattern* thường theo dõi những entity được tải, thêm, sửa hoặc xóa để phối hợp ghi lại thay đổi.

Đơn vị công việc không nhất thiết trùng với:

- **Một HTTP request:** một request có thể chứa nhiều thao tác độc lập; một công việc nền có thể không có HTTP request nào.
- **Một transaction database:** hai khái niệm thường được gắn với nhau, nhưng scope đối tượng và cơ chế commit/rollback ở DB là những trách nhiệm khác nhau.
- **Một thread:** thread pool có thể tái sử dụng thread cho nhiều công việc; một công việc cũng có thể đi qua nhiều bước bất đồng bộ.
- **Toàn bộ ứng dụng:** đây thường là phạm vi quá dài đối với entity có trạng thái mutable theo thao tác.

Trong ví dụ của bài, ta chọn **mỗi lần xử lý một yêu cầu thay đổi đơn hàng** là một unit of work. Mỗi unit sở hữu **Identity Map riêng**, tồn tại từ khi bắt đầu công việc đến khi commit hoặc đóng/bỏ công việc.

| Đối tượng | Phạm vi hợp lý trong ví dụ | Tại sao? |
| --- | --- | --- |
| Cấu hình bất biến | Toàn ứng dụng | Không chứa trạng thái thay đổi của một đơn |
| Kho dữ liệu gốc `InMemoryOrderStore` | Dùng chung trong chương trình console | Giữ snapshot để các unit khác nhau có thể tải dữ liệu đã lưu |
| `WorkUnit` / Identity Map | **Mỗi đơn vị công việc** | Bảo đảm danh tính và trạng thái được chia sẻ chỉ bên trong thao tác đó |
| `DiscountService` và `ApprovalService` | Tạo hoặc lắp cho công việc hiện tại | Cùng nhận repository được quản lý bởi một `WorkUnit` |
| `Order` mutable đã tải | Trong unit sở hữu nó | Các bước xử lý cùng ID cần thấy cùng trạng thái đang được sửa |

**Scope** trả lời “instance nào được dùng lại trong bao lâu?”. **Lifecycle** mô tả “được tạo, sử dụng, commit/loại bỏ và giải phóng khi nào?”. Trong DI thủ công, composition root có trách nhiệm lựa chọn và lắp ghép những phạm vi này. DI container chỉ có thể tự động hóa việc cấp instance nếu ta chọn scope và chính sách phù hợp.

## 3. Lỗi điển hình: cùng ID nhưng hai đối tượng độc lập

Xét một repository cứ đọc lại dữ liệu rồi tạo `new Order(...)` ở mỗi lời gọi:

~~~java
// Mã minh họa vấn đề, chưa phải chương trình độc lập.
Order getById(String id) {
    OrderSnapshot snapshot = store.read(id);
    return new Order(snapshot); // mỗi lần tạo một instance khác
}
~~~

Một use case gọi lần lượt:

~~~java
Order a = discountService.discount("ORD-100", 1_000);
Order b = approvalService.approve("ORD-100");

// Hai service có thể đã thao tác trên hai bản sao khác nhau.
System.out.println(a == b); // có thể false
~~~

Nếu `discountService` giữ một bản sao đã giảm giá, còn `approvalService` lấy bản sao khác từ kho dữ liệu chưa được cập nhật, bước duyệt có thể dùng số tiền cũ. Nếu cả hai sau đó ghi toàn bộ snapshot riêng của mình, lần ghi sau còn có thể **ghi đè thay đổi** từ lần ghi trước.

Vấn đề không nằm riêng ở chỗ hai service dùng hai biến Java. Vấn đề là **hợp đồng trạng thái của một đơn vị công việc** đòi hỏi các bước cùng nhìn một thực thể đang được quản lý, trong khi các repository lại tạo những instance độc lập.

Cũng cần tránh sửa sai bằng cách lưu **mọi entity vào một singleton Map tồn tại toàn ứng dụng**. Việc đó giữ cùng instance qua nhiều request, dễ chia sẻ trạng thái chưa commit, giữ dữ liệu cũ quá lâu, làm tăng bộ nhớ và mở ra lỗi đồng thời. Ta cần **đúng cùng một instance trong một scope xác định**, thay vì cùng một instance ở mọi nơi và mọi thời điểm.

## 4. Identity Map: bảo đảm một instance cho mỗi business key trong một scope

**Identity Map** là cấu trúc ánh xạ từ khóa định danh entity sang đối tượng đang được quản lý:

~~~text
Identity Map của unit A
  "ORD-100"  ──>  Order instance #A1
  "ORD-101"  ──>  Order instance #A2

Identity Map của unit B
  "ORD-100"  ──>  Order instance #B1
~~~

Khi unit A yêu cầu `ORD-100` lần đầu, repository tải snapshot và tạo `#A1`. Lần thứ hai trong **cùng unit A**, repository trả lại đúng `#A1`; do đó mọi bước trong unit đều thấy những thay đổi chưa commit trên instance đó. Unit B có bản đồ riêng nên tạo `#B1` khi tải cùng mã đơn.

~~~mermaid
flowchart TB
    Root["Composition root"] --> UA["WorkUnit A"]
    Root --> UB["WorkUnit B"]
    UA --> MA["Identity Map A"]
    UB --> MB["Identity Map B"]
    SA["DiscountService A"] -->|"getById(ORD-100)"| MA
    SB["ApprovalService A"] -->|"getById(ORD-100)"| MA
    MA --> OA["Order #A1"]
    MB --> OB["Order #B1"]
    OA -.->|"cùng business ID; khác instance"| OB
~~~

Điều kiện để bảo đảm có ý nghĩa:

1. **Khóa định danh ổn định:** dùng một business key duy nhất trong phạm vi loại entity, ví dụ loại entity + mã đơn khi map quản lý nhiều loại.
2. **Tra cứu qua cùng một cơ chế quản lý:** các bước trong unit phải đi qua cùng repository/context hoặc các adapter dùng chung Identity Map.
3. **Không tự tạo bản sao rồi sử dụng song song:** nếu service gọi `new Order(...)` từ dữ liệu thô ngoài context, Identity Map không thể kiểm soát instance đó.
4. **Kết thúc scope rõ ràng:** map phải được bỏ khi unit kết thúc để không giữ tham chiếu và trạng thái mutable vô thời hạn.
5. **Quy tắc đồng thời rõ ràng:** map trong ví dụ là cấu trúc dành cho một luồng xử lý tuần tự, không được chia sẻ tùy ý giữa nhiều thread.

**Identity Map là cơ chế giữ danh tính bên trong một đơn vị công việc, không phải cache toàn cục.** Nó cũng không tự bảo đảm dữ liệu đã được ghi bền vững hoặc tách biệt giữa các giao dịch đồng thời.

## 5. Tách hai dạng “chia sẻ cùng instance” trong DI

Cùng một yêu cầu về danh tính thường xuất hiện ở **hai lớp** khác nhau của đồ thị:

**A. Danh tính collaborator được inject**

Trong một unit, `DiscountService` và `ApprovalService` cần dùng **cùng một repository/context**:

~~~java
WorkUnit unit = new WorkUnit(store);
DiscountService discounts = new DiscountService(unit);
ApprovalService approvals = new ApprovalService(unit);
~~~

Đây là quyết định của **composition root**: tạo một `WorkUnit` và truyền cùng tham chiếu cho các service, thông qua interface `OrderRepository`.

**B. Danh tính entity được tải qua repository**

Ngay cả khi cả hai service dùng cùng repository, repository phải có **hợp đồng và cách triển khai phù hợp** để nhiều lần gọi `getById("ORD-100")` trả lại cùng instance trong unit. Chỉ cùng một repository object **chưa đủ** nếu repository luôn trả về `new Order(...)`.

Ngược lại, dùng hai instance repository có thể vẫn hợp lệ nếu chúng được thiết kế để **cùng chia sẻ một identity context** trong scope. Điều quan trọng là ranh giới được đặc tả, thay vì suy từ tên biến hay số lượng constructor.

| Việc cần bảo đảm | Cơ chế điển hình | Chủ thể chịu trách nhiệm |
| --- | --- | --- |
| Hai service nhận cùng collaborator trong unit | Constructor injection, composition root | Mã lắp ghép |
| Hai lần tải cùng business key cho ra cùng entity instance | Identity Map / persistence context | Repository hoặc unit-of-work context |
| Entity không sống quá lâu ngoài công việc | Scope + lifecycle rõ ràng | Composition root và bên sở hữu unit |
| Các thay đổi được lưu hợp lệ | Unit of Work + cơ chế persistence/transaction thực tế | Storage adapter, transaction manager và ứng dụng |
| Hai công việc đồng thời không ghi đè lẫn nhau | Locking, versioning, isolation phù hợp | Cơ chế hạ tầng và thiết kế nghiệp vụ |

Đây là lý do cần phân biệt **DI** (ai cung cấp dependency), **IoC** (chuyển quyền tạo và lắp ghép ra bên ngoài) với **hợp đồng danh tính** (repository/context trả instance nào trong scope).

## 6. Thực hành Java 17: một WorkUnit sở hữu Identity Map

Ví dụ bên dưới là chương trình Java thuần hoàn chỉnh, tập trung vào **danh tính trong scope**, không phụ thuộc DI container, ORM hoặc database. Kho lưu trữ gốc giữ các **snapshot bất biến**, còn từng unit tạo các `Order` mutable từ snapshot và lưu vào Identity Map.

Để dễ quan sát, phương thức `commit()` ghi các snapshot hiện tại từ map vào kho trong RAM. Đây **không phải** transaction database hoặc cơ chế commit bền vững; mọi thao tác trong ví dụ được thực hiện tuần tự trên một luồng.

Lưu toàn bộ mã sau vào `Main.java`:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Objects;

// Bản chụp bất biến, đại diện dữ liệu đã lưu.
record OrderSnapshot(String id, long totalCents, boolean approved) {
    OrderSnapshot {
        if (id == null || id.isBlank() || totalCents <= 0) {
            throw new IllegalArgumentException("Invalid order snapshot");
        }
    }
}

// Entity đang được quản lý trong một unit of work.
final class Order {
    private final String id;
    private long totalCents;
    private boolean approved;

    Order(OrderSnapshot snapshot) {
        Objects.requireNonNull(snapshot, "snapshot");
        this.id = snapshot.id();
        this.totalCents = snapshot.totalCents();
        this.approved = snapshot.approved();
    }

    String id() {
        return id;
    }

    long totalCents() {
        return totalCents;
    }

    boolean approved() {
        return approved;
    }

    void applyDiscount(long cents) {
        if (approved) {
            throw new IllegalStateException("Approved order is immutable");
        }
        if (cents <= 0 || cents >= totalCents) {
            throw new IllegalArgumentException("Invalid discount");
        }
        totalCents -= cents;
    }

    void approve() {
        if (approved) {
            throw new IllegalStateException("Order already approved");
        }
        approved = true;
    }

    OrderSnapshot snapshot() {
        return new OrderSnapshot(id, totalCents, approved);
    }
}

// Kho lưu gốc để minh họa, chia sẻ qua nhiều unit.
// Không dùng chung HashMap này giữa các luồng trong ví dụ.
final class InMemoryOrderStore {
    private Map<String, OrderSnapshot> saved = new HashMap<>();

    void seed(OrderSnapshot initial) {
        Objects.requireNonNull(initial, "initial");
        saved.put(initial.id(), initial);
    }

    OrderSnapshot read(String id) {
        return saved.get(id);
    }

    // Công bố một bản đồ mới sau khi chuẩn bị toàn bộ snapshot.
    // Đây chỉ là thao tác RAM tuần tự, không phải DB transaction.
    void writeAll(List<OrderSnapshot> snapshots) {
        Map<String, OrderSnapshot> next = new HashMap<>(saved);
        for (OrderSnapshot snapshot : snapshots) {
            next.put(snapshot.id(), snapshot);
        }
        saved = next;
    }
}

// Port mà các service nghiệp vụ cần.
interface OrderRepository {
    Order getById(String id);
}

// WorkUnit nắm Identity Map riêng của một công việc.
final class WorkUnit implements OrderRepository, AutoCloseable {
    private final InMemoryOrderStore store;
    private final Map<String, Order> identityMap = new HashMap<>();
    private boolean open = true;

    WorkUnit(InMemoryOrderStore store) {
        this.store = Objects.requireNonNull(store, "store");
    }

    private void requireOpen() {
        if (!open) {
            throw new IllegalStateException("WorkUnit is closed");
        }
    }

    @Override
    public Order getById(String id) {
        requireOpen();
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Invalid order id");
        }

        return identityMap.computeIfAbsent(id, key -> {
            OrderSnapshot snapshot = store.read(key);
            if (snapshot == null) {
                throw new NoSuchElementException("Missing order: " + key);
            }
            return new Order(snapshot);
        });
    }

    void commit() {
        requireOpen();
        List<OrderSnapshot> changes = new ArrayList<>();
        for (Order order : identityMap.values()) {
            changes.add(order.snapshot());
        }
        store.writeAll(changes);
        open = false;
    }

    @Override
    public void close() {
        open = false;
        identityMap.clear();
    }
}

// Service A: không tạo repository, chỉ sử dụng hợp đồng.
final class DiscountService {
    private final OrderRepository orders;

    DiscountService(OrderRepository orders) {
        this.orders = Objects.requireNonNull(orders, "orders");
    }

    Order discount(String id, long cents) {
        Order order = orders.getById(id);
        order.applyDiscount(cents);
        return order;
    }
}

// Service B: cùng sử dụng hợp đồng.
final class ApprovalService {
    private final OrderRepository orders;

    ApprovalService(OrderRepository orders) {
        this.orders = Objects.requireNonNull(orders, "orders");
    }

    Order approve(String id) {
        Order order = orders.getById(id);
        order.approve();
        return order;
    }
}

public class Main {
    public static void main(String[] args) {
        InMemoryOrderStore store = new InMemoryOrderStore();
        store.seed(new OrderSnapshot("ORD-100", 10_000, false));

        Order firstUnitEntity;

        // Composition root của một công việc: hai service dùng cùng unit.
        try (WorkUnit unit = new WorkUnit(store)) {
            DiscountService discounts = new DiscountService(unit);
            ApprovalService approvals = new ApprovalService(unit);

            Order discounted = discounts.discount("ORD-100", 2_000);
            Order approved = approvals.approve("ORD-100");

            System.out.println("Cung instance: " + (discounted == approved));
            System.out.println(
                    "Da luu truoc commit: "
                    + store.read("ORD-100").totalCents());

            firstUnitEntity = approved;
            unit.commit();
        }

        // Công việc sau tạo Identity Map mới.
        try (WorkUnit next = new WorkUnit(store)) {
            Order reloaded = next.getById("ORD-100");
            System.out.println(
                    "Khac instance: " + (firstUnitEntity != reloaded));
            System.out.println("Tong sau commit: " + reloaded.totalCents());
            System.out.println("Da duyet: " + reloaded.approved());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Kết quả mong đợi:

~~~text
Cung instance: true
Da luu truoc commit: 10000
Khac instance: true
Tong sau commit: 8000
Da duyet: true
~~~

### Đọc kết quả theo từng thời điểm

1. **Bắt đầu unit:** composition root tạo `WorkUnit` đúng một lần, rồi truyền cùng đối tượng vào constructor của `DiscountService` và `ApprovalService`.
2. **Tải lần đầu:** `getById("ORD-100")` không thấy key trong Identity Map, đọc `OrderSnapshot` từ kho và tạo một `Order`.
3. **Tải lần hai:** Identity Map đã có key, nên trả **đúng đối tượng vừa giảm giá** cho `ApprovalService`. Vì vậy `discounted == approved` là `true`.
4. **Trước commit:** kho snapshot vẫn giữ `10000`; thay đổi `8000` nằm trên entity được unit quản lý.
5. **Commit:** unit chuyển trạng thái entity thành snapshot và ghi vào kho RAM, sau đó đánh dấu unit đóng.
6. **Unit mới:** tạo Identity Map rỗng nên tải lại cùng business key thành **instance Java khác** (`firstUnitEntity != reloaded`), nhưng giá trị quan sát là dữ liệu mới lưu.

**Điều được bảo đảm chỉ trong ví dụ này:** một instance cho mỗi mã đơn **trên cùng WorkUnit**, các thay đổi mutable được các bước trong unit nhìn thấy và snapshot được lưu khi gọi `commit()`. Chưa có database thật, transaction phân tán, isolation hoặc bảo đảm chống ghi đè giữa các unit đồng thời.

### Vì sao dùng `close()` dù đã `commit()`?

`try-with-resources` gọi `close()` khi kết thúc khối, kể cả khi xảy ra exception. `close()` giải phóng tham chiếu trong Identity Map. Nếu không gọi `commit()`, thay đổi chỉ tồn tại trên các object đang được unit giữ và **không được ghi vào kho RAM** trong mô hình này.

Khi có tài nguyên thật (connection, session, file), unit hoặc chủ sở hữu phù hợp cũng phải giải phóng chúng. Tuy nhiên, chỉ cài `AutoCloseable` không tự biến mã này thành cơ chế rollback database. Đó là trách nhiệm của adapter và transaction manager thực tế.

## 7. Kiểm thử tính nhất quán danh tính và ranh giới scope

Với unit of work, chỉ kiểm tra số tiền cuối cùng là chưa đủ. Ta còn muốn kiểm tra **cùng tham chiếu trong unit**, **không dùng lại instance ở unit khác**, và **thay đổi không commit không xuất hiện trong kho**.

Đặt đoạn sau vào `IdentityScopeTest.java` trong cùng thư mục với `Main.java`:

~~~java
public class IdentityScopeTest {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        InMemoryOrderStore store = new InMemoryOrderStore();
        store.seed(new OrderSnapshot("TEST-1", 10_000, false));

        Order original;

        try (WorkUnit unit = new WorkUnit(store)) {
            Order first = unit.getById("TEST-1");
            Order second = unit.getById("TEST-1");

            check(first == second, "Same unit must keep one identity");

            first.applyDiscount(1_000);
            check(second.totalCents() == 9_000,
                    "Second reference must observe in-unit changes");
            check(store.read("TEST-1").totalCents() == 10_000,
                    "Store must stay unchanged before commit");

            original = first;
            unit.commit();
        }

        try (WorkUnit next = new WorkUnit(store)) {
            Order reloaded = next.getById("TEST-1");
            check(reloaded != original,
                    "A new unit must create a new instance");
            check(reloaded.totalCents() == 9_000,
                    "Committed amount must be visible in next unit");
        }

        try (WorkUnit abandoned = new WorkUnit(store)) {
            abandoned.getById("TEST-1").applyDiscount(2_000);
            // Không commit: chỉ close, bỏ phiên bản đang sửa.
        }

        check(store.read("TEST-1").totalCents() == 9_000,
                "Uncommitted change must not reach the store");

        System.out.println("PASS");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java IdentityScopeTest.java
java IdentityScopeTest
~~~

Kết quả mong đợi: `PASS`.

Bài test này xác minh **hợp đồng scope cục bộ** của adapter trong bộ nhớ. Nó chưa kiểm tra những tình huống khó hơn như hai unit cùng commit trên một mã đơn, transaction bị gián đoạn, hoặc có lỗi giữa nhiều lần ghi dữ liệu xuống hệ thống ngoài.

Để kiểm thử nghiệp vụ ở mức unit mà không dựng kho thật, các service vẫn có thể nhận một `OrderRepository` fake qua constructor. Identity Map cần được kiểm thử **riêng tại nơi nó được triển khai**, thay vì giả định mọi fake đều phải dùng chung chính xác một instance.

## 8. Những giới hạn không thể giải quyết chỉ bằng Identity Map

### 8.1. Hai unit đồng thời có thể nhìn snapshot khác nhau

Ví dụ, unit A và unit B đều tải `ORD-100` khi tổng tiền đang là `10000`:

~~~text
Unit A: load 10000  -> discount 1000 -> dự định ghi 9000
Unit B: load 10000  -> discount 2000 -> dự định ghi 8000

Unit A commit: store = 9000
Unit B commit: store = 8000  (ghi đè cập nhật của A)
~~~

Mỗi unit đều **nhất quán về danh tính của chính nó** nhưng vẫn xảy ra **lost update** giữa các unit. Identity Map không tự bảo đảm isolation hoặc kiểm soát phiên bản. Hệ thống thực tế có thể cần optimistic locking (cột version, compare-and-swap), pessimistic locking, transaction isolation phù hợp hoặc chiến lược giải quyết xung đột.

Vì vậy, **identity consistency trong một unit** khác với **consistency giữa các unit đang chạy song song**.

### 8.2. Cùng instance mutable không có nghĩa thread-safe

Hai service cùng nhận một `WorkUnit` không nên đồng thời sửa một `Order` mutable nếu chưa có chính sách đồng bộ. `HashMap` và entity mutable trong ví dụ được thiết kế để chạy **tuần tự trên một luồng**.

Nếu công việc có bước bất đồng bộ, cần xác định ai sở hữu context, các thao tác được tuần tự hóa ra sao, và context có được phép chuyển thread không. **Không dùng thread ID thay cho business unit ID**; thread pool tái sử dụng thread và một công việc bất đồng bộ có thể đi qua nhiều thread.

### 8.3. Không nên để entity sống ngoài unit sở hữu

Một tham chiếu `Order` mà mã bên ngoài vẫn giữ sau `close()` không biến mất khỏi JVM; biến `firstUnitEntity` trong ví dụ chứng minh điều đó. Tuy nhiên, đối tượng ấy **không còn được context quản lý**. Sửa nó sau khi unit đóng không tự ghi vào kho; sử dụng nó trong một công việc mới có thể dẫn đến dữ liệu cũ hoặc hành vi sai.

Ứng dụng nên tránh để entity mutable được quản lý bởi một unit “lọt ra” khỏi ranh giới công việc. Dữ liệu cần trả ra ngoài thường nên được chuyển thành **DTO hoặc snapshot bất biến**, và công việc mới nên tải entity qua context mới. Một persistence framework có thể gọi entity sau khi tách khỏi context là *detached entity*; ngữ nghĩa cập nhật trở lại cần được quy định riêng.

### 8.4. Bộ nhớ đệm cấp ứng dụng là vấn đề khác

Một cache dùng chung có thể giữ dữ liệu đọc hoặc snapshot để giảm I/O. Cache ấy thường có yêu cầu về invalidation, versioning, TTL và đồng thời. **Identity Map thuộc một unit of work** tập trung vào *một instance mutable được quản lý trên mỗi business key trong scope*.

Đừng dùng một singleton `Map<String, Order>` làm cách thay thế Identity Map cho mọi request. Những tham chiếu mutable được dùng chung qua nhiều đơn vị công việc có thể làm lộ thay đổi chưa commit và khó xác định nơi nào sở hữu đối tượng.

### 8.5. Commit ở ví dụ không phải một giao dịch cơ sở dữ liệu

Trong `InMemoryOrderStore.writeAll`, ta tạo bản sao map rồi thay tham chiếu trong một chương trình console. Cách viết đó minh họa việc công bố snapshot khi hoàn tất công việc **trong điều kiện chạy tuần tự**. Nó không có bảo đảm ACID, lưu bền xuống đĩa, xử lý mất điện, rollback qua nhiều hệ thống hoặc bảo vệ commit đồng thời.

Khi dùng JDBC/ORM, cần thiết kế transaction boundary, connection/session lifecycle, rollback khi lỗi, locking và commit đúng mức bảo đảm nghiệp vụ. **DI container không tự tạo bảo đảm giao dịch chỉ vì các dependency có cùng scope.**

## 9. So sánh các lựa chọn scope khi lắp ghép

| Cách lắp ghép | Kết quả về identity | Đánh đổi/rủi ro |
| --- | --- | --- |
| Một `WorkUnit` cho tất cả các service trong **một công việc** | Cùng business key → cùng instance trong unit | Phải đóng unit đúng lúc và không chia sẻ ngoài phạm vi |
| Một `WorkUnit` mới cho **mỗi lời gọi repository** | Thường tạo nhiều instance cùng ID trong cùng quy trình | Các bước có thể thấy trạng thái khác nhau |
| Một `WorkUnit` singleton cho toàn ứng dụng | Nhiều công việc dùng chung instance lâu dài | Rò state, stale data, bộ nhớ lớn, lỗi đồng thời |
| Một `WorkUnit` cho mỗi request HTTP | Có thể phù hợp với request tương ứng một công việc | Không đúng nếu request gồm nhiều công việc hoặc công việc trải qua nhiều request |
| Một `WorkUnit` cho mỗi batch item | Identity nhất quán trong từng item | Cần quy định item nào được commit độc lập và xử lý lỗi ra sao |
| Provider tạo unit có scope theo từng công việc | Linh hoạt khi service sống lâu tạo công việc ngắn hạn | Cần hợp đồng ownership, đóng resource và không gọi provider tùy ý giữa các bước |

**Provider/factory** hữu ích khi cần tạo một `WorkUnit` mới cho mỗi công việc. Nhưng nếu các service trong cùng công việc đều gọi `provider.get()` riêng và provider trả unit mới mỗi lần, danh tính vẫn bị tách. **Cách dùng đúng:** tạo một unit tại điểm bắt đầu công việc, truyền cùng repository/context vào tất cả bước cần chia sẻ nó, rồi commit/đóng tập trung.

Ví dụ một application coordinator có thể tổ chức:

~~~java
// Giả định các class đã được khai báo như ví dụ đầy đủ.
try (WorkUnit unit = new WorkUnit(store)) {
    DiscountService discounts = new DiscountService(unit);
    ApprovalService approvals = new ApprovalService(unit);

    discounts.discount("ORD-100", 1_000);
    approvals.approve("ORD-100");

    unit.commit();
}
~~~

Một DI container có thể cung cấp **request scope**, **transaction scope** hoặc một custom scope (tùy framework), nhưng yêu cầu nghiệp vụ vẫn là lựa chọn **đúng ranh giới của một unit of work**. Nếu scope container khác ranh giới thực của công việc, việc đăng ký bean tự động chưa giải quyết được vấn đề danh tính.

## 10. Liên hệ với ORM và persistence context

Nhiều ORM dùng một **persistence context / session** có cơ chế gần với Identity Map: trong cùng context, việc truy xuất cùng một entity theo khóa định danh thường trả lại **cùng một object đang được quản lý**. Context còn có thể theo dõi thay đổi (*dirty checking*) để ghi chúng khi flush/commit.

Cần phân biệt:

- **Identity Map** giữ quy tắc một instance cho mỗi key trong scope.
- **Unit of Work** tổ chức thay đổi cần ghi của một hoạt động nghiệp vụ.
- **Persistence context** có thể kết hợp Identity Map, state tracking, dirty checking, load/flush và quản lý entity.
- **Database transaction** cung cấp những bảo đảm giao dịch cụ thể theo hệ quản trị và mức isolation được cấu hình.
- **DI scope** quyết định container cấp cùng bean/session/repository cho những consumer nào.

Các cơ chế đó có thể cùng tồn tại nhưng **không đồng nghĩa nhau**. Một session có thể được dùng ở các thời điểm khác nhau của transaction; một transaction có thể ảnh hưởng nhiều loại tài nguyên; việc đóng session không nhất thiết tương đương một thao tác rollback theo cách bạn mong đợi. Luôn dựa trên hợp đồng và lifecycle cụ thể của công nghệ đang sử dụng.

Trong Java thuần, việc tự viết `WorkUnit` như ở phần thực hành làm rõ mối quan hệ mà các framework thường quản lý giúp. Khi chuyển sang ORM hoặc DI container, nên giữ các **interface nghiệp vụ**, constructor injection và ranh giới composition root, rồi thay cơ chế quản lý scope/persistence phù hợp.

## 11. Dấu hiệu đang có lỗi danh tính hoặc scope

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Hai lần tải cùng ID trong một use case tạo hai instance | Repository không có Identity Map hoặc mỗi bước dùng context khác | Kiểm tra scope của repository/context và hợp đồng `getById` |
| Một bước cập nhật nhưng bước tiếp theo vẫn thấy giá trị cũ | Các bước làm việc với bản sao khác nhau hoặc snapshot cũ | Kiểm tra tham chiếu, thứ tự flush/load và transaction boundary |
| Thay đổi của request A xuất hiện trong request B trước commit | Entity/context bị chia sẻ quá rộng | Tránh singleton mutable context; xác định owner theo công việc |
| Số lượng entity giữ trong bộ nhớ tăng không giảm | Context sống quá lâu, giữ tham chiếu qua nhiều công việc | Đóng/clear context đúng scope và đo retained references |
| Unit test pass nhưng production xảy ra lost update | Chưa kiểm tra nhiều unit đồng thời | Bổ sung versioning/locking và kiểm thử cạnh tranh |
| Repository được inject giống nhau nhưng identity vẫn khác | Cùng repository chưa chắc có identity caching | Kiểm tra implementation của `getById` và scope Identity Map |
| Dữ liệu thay đổi sau khi unit đã đóng nhưng không được lưu | Entity sống ngoài lifecycle được quản lý | Trả DTO/snapshot, tải lại ở công việc mới và tránh sửa detached entity |
| Tất cả service gọi provider để lấy session mỗi lần dùng | Provider tạo phiên mới cho từng lời gọi | Lấy một lần tại đầu công việc và truyền cùng unit cho các bước |

## 12. Quy trình thiết kế và kiểm thử một unit of work

1. **Định nghĩa ranh giới nghiệp vụ:** unit bắt đầu ở đâu và kết thúc ở đâu? Có một hay nhiều bước phải nhìn chung trạng thái?
2. **Xác định business key và loại entity:** ví dụ `(Order, orderId)`; bảo đảm ID được dùng ổn định trong scope.
3. **Chọn chủ sở hữu context:** composition root, application coordinator hoặc transaction boundary chịu trách nhiệm tạo và đóng.
4. **Thiết kế repository contract:** nêu rõ cùng key trong một unit có trả về cùng managed instance không, cách xử lý không tìm thấy và trạng thái hết hạn.
5. **Dùng constructor injection:** các service dùng chung cùng `OrderRepository` hoặc context của unit, không tự gọi `new WorkUnit(...)`.
6. **Quản lý Identity Map cục bộ:** lần tải đầu tạo entity, lần sau trả lại instance trong map; tránh map singleton ngoài công việc.
7. **Đặc tả commit/discard:** thay đổi nào được ghi, lỗi nào làm công việc thất bại, dữ liệu chưa commit có bị loại bỏ không.
8. **Kiểm tra đồng thời và quyền sở hữu:** unit có bị chia sẻ giữa thread/request không, entity có thoát scope không, ai đóng tài nguyên?
9. **Kiểm thử các ranh giới:** cùng ref trong unit, khác ref giữa unit, trạng thái trước/sau commit, thay đổi bỏ dở, và cạnh tranh giữa nhiều unit nếu hệ thống cho phép.
10. **Chỉ sau đó cân nhắc DI container/ORM:** công cụ giúp tự động hóa lifecycle và identity management; ranh giới đúng phải do thiết kế ứng dụng xác định.

### Câu hỏi tự kiểm tra

**Tình huống A:** Hai biến `orderA` và `orderB` có cùng `id`, và `orderA.equals(orderB)` trả `true`. Có thể kết luận hai service đang dùng cùng managed instance không?

**Không.** Chỉ `orderA == orderB` mới kiểm tra hai biến trỏ tới cùng đối tượng Java. So sánh `equals` hoặc business key không bảo đảm trạng thái mutable được chia sẻ.

**Tình huống B:** Trong cùng một công việc, hai service được inject hai `OrderRepository` khác nhau. Điều này chắc chắn vi phạm tính nhất quán danh tính chứ?

**Chưa chắc.** Nếu hai repository dùng **cùng Identity Map/context**, chúng vẫn có thể trả cùng entity instance. Nhưng nếu mỗi repository sở hữu map riêng hoặc mỗi lần load đều tạo object mới, tính nhất quán theo unit sẽ bị phá.

**Tình huống C:** Một `WorkUnit` được giữ singleton cho mọi request để “đảm bảo luôn cùng instance”. Có đúng mục tiêu không?

**Không.** Phạm vi quá rộng dẫn đến dữ liệu cũ, giữ trạng thái chưa commit giữa các công việc, nguy cơ đồng thời và rò bộ nhớ. Yêu cầu là cùng identity **trong một công việc**, không phải một identity vĩnh viễn.

**Tình huống D:** Hai unit độc lập đều tải cùng bản ghi, một unit sửa giá và unit còn lại sửa trạng thái. Mỗi unit giữ identity riêng rất tốt. Hệ thống đã tránh lost update chưa?

**Chưa.** Identity Map xử lý danh tính **bên trong** từng scope, không giải quyết xung đột **giữa** các unit. Cần cơ chế locking, versioning và transaction phù hợp.

**Tình huống E:** Một controller nhận `WorkUnit` từ container theo request scope, nhưng một request xử lý ba đơn hàng như ba công việc độc lập. Request scope có luôn đúng không?

**Không tự động.** Nếu mỗi đơn cần một đơn vị công việc và commit/loại bỏ độc lập, cần tạo ba unit khác nhau hoặc định nghĩa lại ranh giới cho rõ, dù cả ba nằm trong cùng HTTP request.

## Ghi nhớ

**Tính nhất quán của danh tính đối tượng** nghĩa là khi những bước trong **cùng một đơn vị công việc** truy cập cùng một thực thể logic, chúng nhận đúng **instance đang được quản lý** để cùng thấy trạng thái của thao tác đó. **Identity Map** có thể bảo đảm một instance trên mỗi key trong scope, còn **constructor injection** và **composition root** giúp những service liên quan được cấp chung repository/context. Khi công việc kết thúc, context cần được commit hoặc loại bỏ và đóng đúng vòng đời. Điều đó tách biệt với transaction database, concurrency và persistence, vốn đòi hỏi các bảo đảm kỹ thuật riêng.
