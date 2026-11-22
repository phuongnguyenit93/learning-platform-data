# Thay Service Locator bằng các phụ thuộc có kiểu rõ ràng

## 1. Vì sao cần refactor từ Service Locator sang Dependency Injection?

Trong **Dependency Injection (DI)**, một lớp **nhận** những đối tượng cộng tác từ bên ngoài thay vì chủ động tìm kiếm hoặc tự tạo chúng. Với **constructor injection**, các dependency bắt buộc xuất hiện trong chữ ký constructor; **composition root** chịu trách nhiệm chọn implementation, lắp ghép object graph và quản lý scope/vòng đời. Sự đảo chiều trách nhiệm tạo và sử dụng là một biểu hiện của **Inversion of Control (IoC)**.

Một ứng dụng Java cũ đôi khi sử dụng **Service Locator**: đối tượng nghiệp vụ gọi một registry, container hoặc singleton toàn cục để tìm những dịch vụ cần dùng.

```java
// Ví dụ minh họa cấu trúc cần refactor, chưa phải file chạy độc lập.
final class LegacyOrderService {
    void confirm(String orderId, long amountVnd) {
        OrderRepository repo =
                GlobalServices.get(OrderRepository.class);
        ReceiptSender sender =
                GlobalServices.get(ReceiptSender.class);

        OrderEntry order = new OrderEntry(orderId, amountVnd);
        repo.save(order);
        sender.send(order);
    }
}
```

Nhìn vào chữ ký `new LegacyOrderService()`, người dùng lớp **không biết** đối tượng cần repository và sender. Tới lúc chạy `confirm`, hệ thống mới cố tìm hai dependency bằng cơ chế nằm ngoài hợp đồng constructor. Một registry chưa đăng ký hoặc đăng ký sai instance có thể làm chương trình thất bại muộn; test thường phải sửa trạng thái toàn cục trước khi chạy.

Đề bài **“Thay Service Locator bằng các phụ thuộc có kiểu rõ ràng”** không chỉ có nghĩa bỏ phương thức `get()`. Mục tiêu là thay **phụ thuộc ẩn** bằng **hợp đồng có tên và có kiểu nằm ngay tại ranh giới tạo đối tượng**:

```java
// Hướng thiết kế mong muốn.
final class OrderService {
    private final OrderRepository repository;
    private final ReceiptSender sender;

    OrderService(OrderRepository repository, ReceiptSender sender) {
        this.repository = java.util.Objects.requireNonNull(
                repository, "repository");
        this.sender = java.util.Objects.requireNonNull(
                sender, "sender");
    }
}
```

Nhờ đó, composition root phải quyết định truyền gì vào lớp, test có thể truyền fake trực tiếp và việc thay adapter không còn đòi hỏi sửa logic nghiệp vụ.

**Mục tiêu học tập:**

1. Nhận diện Service Locator, kể cả khi được bọc dưới các tên như `Context`, `Registry`, `Container` hoặc một generic provider.
2. Giải thích sự khác biệt giữa “lookup có trả về kiểu Java” và “dependency được khai báo tường minh”.
3. Refactor tuần tự sang constructor injection mà vẫn giữ hành vi và kiểm soát thay đổi.
4. Lắp graph thủ công ở composition root, kiểm thử bằng Java thuần và fake.
5. Xử lý trường hợp chọn implementation lúc chạy bằng factory/resolver **theo vai trò nghiệp vụ**, không trở về một locator tổng quát.
6. Kiểm tra scope, ownership, circular dependencies và lỗi khởi động trước khi cân nhắc DI container.

## 2. Service Locator khác DI ở đâu?

Đặt hai thiết kế cạnh nhau:

```text
TRƯỚC: Service Locator

OrderService ------> GlobalServices / Container
     |                    |
     | gọi get(...)       +----> OrderRepository
     |                    +----> ReceiptSender
     |
  Các phụ thuộc thực tế ẩn khỏi constructor


SAU: Constructor Injection

Composition Root
     | tạo, cấu hình
     +----> OrderRepository implementation ----+
     +----> ReceiptSender implementation ------+----> OrderService
                                                        |
                                                 sử dụng qua interface
```

| Tiêu chí | Service Locator trong lớp nghiệp vụ | Constructor injection |
| --- | --- | --- |
| Nơi khai báo dependency | Rải trong các lời gọi `get`, thường ở bên trong method. | Thể hiện ở chữ ký constructor và các trường có kiểu cụ thể. |
| Ai tìm/chọn implementation? | Chính lớp sử dụng phụ thuộc gọi locator. | Composition root chọn và truyền instance. |
| Khả năng đọc và review | Chỉ xem constructor chưa biết cần gì; phải tìm các điểm lookup. | Người đọc thấy các dependency cần thiết khi tạo đối tượng. |
| Lỗi thiếu dependency | Có thể tới lúc gọi method lần đầu mới phát hiện. | Có thể fail-fast tại composition root/constructor khi tạo. |
| Unit test | Thường phải khởi tạo/reset registry hoặc container. | Tạo trực tiếp service với fake và stub. |
| Coupling | Phụ thuộc vào API locator, cách đăng ký và thời điểm registry sẵn sàng. | Phụ thuộc vào interface cộng tác viên có ý nghĩa với use case. |
| Quản lý scope | Lookup có thể lấy nhầm instance theo vòng đời ngầm. | Caller chọn instance đúng scope; vẫn phải thiết kế lifecycle. |

**Quan trọng:** `GlobalServices.get(OrderRepository.class)` vẫn có thể là API **trả về kiểu `OrderRepository` ở phía gọi**. Kiểu trả về có vẻ an toàn, nhưng **dependency vẫn ẩn**: constructor của `OrderService` không thông báo rằng repository bắt buộc, và implementation thực tế chỉ được quyết định trong registry khi chạy. “Có kiểu rõ ràng” trong bài này nhấn mạnh **hợp đồng được công bố tại ranh giới tạo và kiểm soát đối tượng**, không chỉ generic `get(Class<T>)`.

### 2.1. DI container không đồng nghĩa Service Locator

Một DI container có thể có API `getBean`, `resolve` hay `getInstance`. **Bản thân API này không tự khiến cả ứng dụng là Service Locator**. Nếu composition root dùng container **ở ranh giới khởi động** để lấy entry point đã được lắp ghép, rồi truyền các dependency tường minh cho service, thì cách sử dụng vẫn nhất quán với DI.

Vấn đề xuất hiện khi lớp nghiệp vụ tự gọi container để tìm các dependency tùy lúc:

```java
// Anti-pattern: che phụ thuộc bằng container được truyền vào.
final class CheckoutService {
    private final AppContainer container;

    CheckoutService(AppContainer container) {
        this.container = container;
    }

    void checkout() {
        PaymentGateway gateway =
                container.get(PaymentGateway.class);
        // ...
    }
}
```

Đoạn này chỉ **inject chính locator**. Dependency thực sự (`PaymentGateway`) vẫn ẩn; test phải chuẩn bị một container hoặc fake container, rồi đảm bảo khóa dịch vụ được đăng ký. Đổi `GlobalServices` thành `AppContainer` không đủ để hoàn tất refactor.

### 2.2. Phân biệt registry cho nghiệp vụ với locator tổng quát

Một `Map<PaymentMethod, PaymentProcessor>` được inject để **chọn processor theo phương thức thanh toán** là một dependency có vai trò rõ. Service chỉ được chọn trong một tập chiến lược cùng interface, với khóa nghiệp vụ hợp lệ.

Ngược lại, `Map<Class<?>, Object>`, `Context.get(String)` hoặc `resolve(Class<T>)` cho phép lấy **mọi loại service trong hệ thống**. Dùng cấu trúc này từ nghiệp vụ thường chỉ là đổi tên Service Locator.

Không phải mọi lookup đều sai: tra sản phẩm theo ID, lấy record từ repository hay chọn strategy theo loại giao dịch là **thao tác nghiệp vụ**. Service Locator bị phê bình vì **lookup dependency của chương trình**, không phải vì có bất kỳ thao tác tra cứu nào.

## 3. Nhận diện các dạng Service Locator trong mã cũ

Service Locator có nhiều hình dạng:

### 3.1. Singleton hoặc biến toàn cục

```java
// Ví dụ cấu trúc phụ thuộc ẩn:
EmailSender sender = Services.instance().get(EmailSender.class);
```

Các vấn đề thường gặp: test ảnh hưởng lẫn nhau do registry dùng chung, khó khởi tạo nhiều graph độc lập, khó dọn tài nguyên sau một test, và thứ tự đăng ký có thể quan trọng hơn hợp đồng constructor.

### 3.2. Framework container được truy cập sâu trong nghiệp vụ

```java
// Anti-pattern có thể gặp khi lớp nghiệp vụ biết API framework:
PaymentGateway gateway = applicationContext.getBean(
        PaymentGateway.class);
```

Khi đó, code nghiệp vụ phụ thuộc framework và chỉ hoạt động khi context đã tồn tại. Test đơn vị phải tải context hoặc tạo lớp giả cho một API quá rộng, dù logic chỉ cần một `PaymentGateway`.

### 3.3. Generic provider/registry trá hình

```java
interface Dependencies {
    <T> T get(Class<T> type);
}

final class ReportService {
    private final Dependencies dependencies;

    ReportService(Dependencies dependencies) {
        this.dependencies = dependencies;
    }

    void run() {
        ReportStore store = dependencies.get(ReportStore.class);
        // ...
    }
}
```

Đây là ví dụ minh họa, các kiểu `ReportStore` chưa khai báo trong đoạn. `Dependencies` không có vai trò nghiệp vụ riêng; nó chỉ chuyển dependency ẩn từ biến toàn cục sang field. Một object graph vẫn không có kiểm tra tĩnh rằng `ReportService` cần `ReportStore`.

### 3.4. Constructor tự tìm service thay vì nhận instance

```java
// Ví dụ anti-pattern khi khởi tạo:
OrderService() {
    this.repository = Services.get(OrderRepository.class);
    this.sender = Services.get(ReceiptSender.class);
}
```

Lỗi không cần chờ tới `confirm`, nhưng lớp vẫn tự tìm dependency; test vẫn cần một registry. **Eager lookup không biến Service Locator thành constructor injection.**

### 3.5. Lookup xuất hiện trong lambda hoặc async callback

Một `Runnable`, event handler hoặc background job có thể gọi locator khi chạy vài phút sau khi request kết thúc. Khi đó không chỉ có dependency ẩn mà còn có nguy cơ lấy nhầm request-scoped instance, chạy sau khi container đóng hoặc dùng context của người dùng khác.

Trong lúc kiểm tra mã cũ, đừng chỉ tìm constructor: cần xem những đường chạy bất đồng bộ và nơi resolver bị truyền đi qua các lớp.

## 4. Quy trình refactor từng bước, không thay toàn hệ thống một lần

Thay Service Locator là một thay đổi **kiến trúc và wiring**, không phải chỉ thay cú pháp. Một lộ trình an toàn gồm các bước sau.

### Bước 1: Liệt kê lookup và phân loại nhu cầu

Đối với mỗi `locator.get(...)`, ghi lại:

| Thông tin | Câu hỏi cần trả lời |
| --- | --- |
| Hợp đồng hiện được lấy | Lớp thực sự cần năng lực gì? Có đang dùng một API quá rộng không? |
| Thời điểm gọi | Tại constructor, mỗi request, khi chạy job hay chỉ trong nhánh hiếm? |
| Scope | Dependency là application-scoped, request-scoped hay task-scoped? |
| Ownership | Ai tạo, ai đóng kết nối, stream, client, executor? |
| Hành vi lỗi | Nếu lookup thiếu hoặc implementation lỗi, ứng dụng hiện phản ứng thế nào? |
| Các test hiện có | Test đang dựa vào singleton registry hoặc có thể dựng dependency độc lập? |

Đừng refactor tất cả `get` một cách máy móc. Có lời gọi dùng để **chọn chiến lược động** và cần chuyển thành factory theo vai trò; có lời gọi chỉ là hạ tầng được tạo một lần ở bootstrap và có thể chuyển thẳng thành constructor argument.

### Bước 2: Chọn hợp đồng nhỏ, đúng nhu cầu sử dụng

Thay vì inject `DatabaseConnection` rồi để service tự thực hiện SQL trong từng use case, có thể định nghĩa `OrderRepository` phản ánh nhu cầu lưu đơn hàng.

Ví dụ:

```java
interface OrderRepository {
    void save(OrderEntry order);
}

interface ReceiptSender {
    void send(OrderEntry order);
}
```

Hợp đồng nên đủ nhỏ để fake được, nhưng **không cần tạo một interface cho mọi lớp dữ liệu**. Nếu một value object không có tác dụng phụ và không có collaborator cần thay thế, nó có thể được tạo trực tiếp.

### Bước 3: Đưa dependency vào constructor và kiểm tra thiếu cấu hình

```java
OrderService(OrderRepository repository, ReceiptSender sender) {
    this.repository = Objects.requireNonNull(
            repository, "repository");
    this.sender = Objects.requireNonNull(sender, "sender");
}
```

Điều này làm lộ hai dependency bắt buộc. Java kiểm tra **kiểu tham số** tại thời điểm biên dịch; `requireNonNull` phát hiện giá trị `null` ở thời điểm khởi tạo. Chúng **không tự đảm bảo** adapter thật đã kết nối được hoặc mọi lỗi I/O sẽ biến mất.

### Bước 4: Chuyển lựa chọn implementation về composition root

Tạo adapter trước, sau đó truyền qua constructor của service. Các quyết định về môi trường, cấu hình, retry, logging, scope và quản lý tài nguyên được điều phối ở nơi khởi động, thay vì rải trong `OrderService`.

### Bước 5: Chuyển caller sang sử dụng đối tượng đã lắp ghép

Thay những đường:

```java
OrderService service = locator.get(OrderService.class);
service.confirm(...);
```

bằng một caller đã được inject `OrderService`, hoặc một entry point được root khởi tạo và truyền `OrderService` từ constructor. Caller không cần biết `OrderRepository` và `ReceiptSender` được tạo thế nào.

### Bước 6: Xóa lookup cũ, kiểm tra hành vi và dọn trạng thái toàn cục

Khi mọi đường sử dụng đã chuyển sang dependency tường minh, loại bỏ lời gọi locator và entry registry không còn cần. Việc gỡ dần giúp tránh một thay đổi lớn khó rollback. **Không giữ locator “phòng hờ” sâu trong nghiệp vụ**: nếu vẫn tồn tại, các dependency mới sẽ lại được tạo ngầm theo cách cũ.

## 5. Ví dụ Java thuần hoàn chỉnh: sau khi thay Service Locator

Bây giờ ta viết một phiên bản `OrderService` nhận đúng hai collaborator, không dùng static registry, framework hoặc DI container.

**Hành vi minh họa:** xác nhận đơn hàng có ID và số tiền hợp lệ, lưu đơn trước rồi gửi thông báo. Nếu lưu lỗi, không gửi thông báo. Ví dụ dùng bộ nhớ và console để tập trung vào refactor, **không có database hoặc email thật**.

Lưu toàn bộ đoạn sau vào `ServiceLocatorRefactorDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class OrderEntry {
    final String id;
    final long amountVnd;

    OrderEntry(String id, long amountVnd) {
        this.id = Objects.requireNonNull(id, "id");
        this.amountVnd = amountVnd;
    }
}

// Hai hợp đồng có ý nghĩa trực tiếp với use case.
interface OrderRepository {
    void save(OrderEntry order);
}

interface ReceiptSender {
    void send(OrderEntry order);
}

// Lớp nghiệp vụ không biết Registry, container, database hay SDK.
final class OrderService {
    private final OrderRepository repository;
    private final ReceiptSender sender;

    OrderService(OrderRepository repository, ReceiptSender sender) {
        this.repository = Objects.requireNonNull(
                repository, "repository");
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    OrderEntry confirm(String orderId, long amountVnd) {
        if (orderId == null || orderId.trim().isEmpty()) {
            throw new IllegalArgumentException("INVALID_ORDER_ID");
        }
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("INVALID_AMOUNT");
        }

        OrderEntry order = new OrderEntry(orderId, amountVnd);
        repository.save(order);
        sender.send(order);
        return order;
    }
}

// Adapter demo: dùng bộ nhớ, không lưu bền vững.
final class InMemoryOrderRepository implements OrderRepository {
    private final List<OrderEntry> orders = new ArrayList<>();

    @Override
    public void save(OrderEntry order) {
        orders.add(Objects.requireNonNull(order, "order"));
    }

    int count() {
        return orders.size();
    }
}

// Adapter demo: chỉ in console, không gửi thư thật.
final class ConsoleReceiptSender implements ReceiptSender {
    @Override
    public void send(OrderEntry order) {
        System.out.println("Receipt sent: " + order.id);
    }
}

// Entry point cũng nhận dependency tường minh.
final class OrderCommand {
    private final OrderService orders;

    OrderCommand(OrderService orders) {
        this.orders = Objects.requireNonNull(orders, "orders");
    }

    void execute(String orderId, long amountVnd) {
        OrderEntry result = orders.confirm(orderId, amountVnd);
        System.out.println("Confirmed: " + result.id);
    }
}

public class ServiceLocatorRefactorDemo {
    public static void main(String[] args) {
        // Composition root: biết và chọn các implementation cụ thể.
        InMemoryOrderRepository repository =
                new InMemoryOrderRepository();
        ReceiptSender sender = new ConsoleReceiptSender();
        OrderService orders = new OrderService(repository, sender);

        // Entry point chỉ nhận service đã lắp ghép.
        OrderCommand command = new OrderCommand(orders);
        command.execute("ORD-100", 250_000L);

        System.out.println("Saved orders: " + repository.count());
    }
}
```

Biên dịch và chạy:

```bash
javac ServiceLocatorRefactorDemo.java
java ServiceLocatorRefactorDemo
```

Kết quả dự kiến:

```text
Receipt sent: ORD-100
Confirmed: ORD-100
Saved orders: 1
```

### 5.1. So sánh trước và sau refactor

**Trước:**

```text
new LegacyOrderService()
   -> confirm(...)
       -> GlobalServices.get(OrderRepository.class)
       -> GlobalServices.get(ReceiptSender.class)
       -> dùng hai implementation tìm được khi chạy
```

**Sau:**

```text
main (composition root)
  -> new InMemoryOrderRepository()
  -> new ConsoleReceiptSender()
  -> new OrderService(repository, sender)
  -> new OrderCommand(orders)
  -> command.execute(...)
```

Điểm thay đổi quan trọng:

- **Phụ thuộc của `OrderService` xuất hiện trong chữ ký constructor**, thay vì bị giấu bên trong `confirm`.
- **Không có registry toàn cục** hoặc lookup về mặt kỹ thuật trong logic nghiệp vụ.
- **Caller nhận `OrderService`**, không phải container hoặc API tìm dịch vụ.
- **Root quyết định implementation**; thay adapter bộ nhớ bằng adapter SQL khi phù hợp không yêu cầu sửa logic xác nhận đơn.
- **Đối tượng thiếu dependency thất bại lúc tạo** qua `Objects.requireNonNull`, thay vì một lần gọi lookup bất kỳ sau này.

**Giới hạn quan trọng:** demo gọi `repository.save` rồi `sender.send`. Nếu gửi thông báo thất bại, đơn có thể đã được lưu. Refactor sang DI không tự tạo giao dịch phân tán; hệ thống thật có thể cần outbox, idempotency hoặc cơ chế retry tùy nghiệp vụ. Không nên dùng `ConsoleReceiptSender` như một giả định rằng email thật đã gửi thành công.

## 6. Kiểm thử sau refactor: fake và lỗi được tạo có chủ đích

Ưu điểm dễ thấy của dependency tường minh là unit test **không cần reset global registry**. Ta chỉ cần dựng object graph phù hợp cho từng tình huống.

Lưu `ServiceLocatorRefactorTest.java` cùng thư mục với file demo:

```java
final class RecordingRepository implements OrderRepository {
    int calls;
    OrderEntry saved;

    @Override
    public void save(OrderEntry order) {
        calls++;
        saved = order;
    }
}

final class RecordingSender implements ReceiptSender {
    int calls;
    OrderEntry sent;

    @Override
    public void send(OrderEntry order) {
        calls++;
        sent = order;
    }
}

final class FailingRepository implements OrderRepository {
    @Override
    public void save(OrderEntry order) {
        throw new IllegalStateException("TEST_STORAGE_FAILED");
    }
}

public class ServiceLocatorRefactorTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        RecordingRepository fakeRepository = new RecordingRepository();
        RecordingSender fakeSender = new RecordingSender();
        OrderService service =
                new OrderService(fakeRepository, fakeSender);

        OrderEntry confirmed = service.confirm("TEST-1", 70_000L);
        check(confirmed == fakeRepository.saved
                        && confirmed == fakeSender.sent,
                "Service không truyền cùng đơn sang hai cộng tác viên");
        check(fakeRepository.calls == 1 && fakeSender.calls == 1,
                "Số lần tương tác không đúng");
        check("TEST-1".equals(confirmed.id)
                        && confirmed.amountVnd == 70_000L,
                "Dữ liệu xác nhận không đúng");

        // Sai dữ liệu phải bị chặn trước khi phát sinh side effect.
        boolean invalidRejected = false;
        try {
            service.confirm(" ", 10_000L);
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        check(invalidRejected, "Không từ chối mã đơn rỗng");
        check(fakeRepository.calls == 1 && fakeSender.calls == 1,
                "Có side effect khi dữ liệu không hợp lệ");

        // Dependency bắt buộc thiếu phải báo lỗi khi lắp ghép.
        boolean nullRejected = false;
        try {
            new OrderService(null, fakeSender);
        } catch (NullPointerException expected) {
            nullRejected = true;
        }
        check(nullRejected, "Thiếu dependency nhưng vẫn tạo service");

        // Tạo object graph thứ hai độc lập, không thay registry toàn cục.
        RecordingSender senderOnFailure = new RecordingSender();
        OrderService failingService =
                new OrderService(new FailingRepository(),
                                 senderOnFailure);
        boolean storeFailed = false;
        try {
            failingService.confirm("TEST-FAIL", 80_000L);
        } catch (IllegalStateException expected) {
            storeFailed = true;
        }
        check(storeFailed, "Không truyền lỗi lưu trữ");
        check(senderOnFailure.calls == 0,
                "Đã gửi thông báo dù lưu đơn thất bại");

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac ServiceLocatorRefactorDemo.java ServiceLocatorRefactorTest.java
java ServiceLocatorRefactorTest
```

Kết quả dự kiến: `PASS`.

Bài test xác nhận:

1. `OrderService` sử dụng **chính xác** các dependency được truyền vào.
2. Dữ liệu không hợp lệ bị từ chối trước khi lưu hoặc gửi.
3. Thiếu dependency bắt buộc báo lỗi ở constructor.
4. Các test có thể tạo graph khác nhau mà **không phụ thuộc vào state toàn cục**.
5. Nếu lưu thất bại, sender không bị gọi theo thứ tự nghiệp vụ của ví dụ.

Bài test bằng fake không chứng minh SQL adapter thật, giao thức email hoặc cấu hình production hoạt động đúng. Sau refactor vẫn cần kiểm thử tích hợp các adapter, smoke test composition root và những luồng lifecycle phù hợp.

## 7. Khi implementation phải được chọn động: dùng factory/resolver có vai trò rõ

Không phải mọi dependency đều được chọn cố định một lần ở startup. Một checkout có thể cần sender theo `ReceiptChannel`, hoặc một job cần `UnitOfWork` mới mỗi lần chạy. Nếu thay mọi lookup động bằng một registry tổng quát, ta rất dễ tạo lại Service Locator.

**Hướng phù hợp:** inject **một factory hoặc resolver có hợp đồng nghiệp vụ hẹp**, chỉ giải quyết đúng loại đối tượng cần tạo/chọn.

### 7.1. Tra cứu chiến lược theo khóa nghiệp vụ

Giả sử `ReceiptSender` có hai implementation và request chọn kênh. Thay vì:

```java
// Anti-pattern: service tra bất kỳ bean nào bằng tên động.
ReceiptSender sender =
        container.get("sender." + requestedChannel);
```

hãy định nghĩa một hợp đồng chỉ dành cho receipt:

```java
import java.util.EnumMap;
import java.util.Map;
import java.util.Objects;

enum ReceiptChannel {
    CONSOLE, EMAIL
}

// Factory/resolver chỉ có trách nhiệm chọn ReceiptSender.
interface ReceiptSenderSelector {
    ReceiptSender select(ReceiptChannel channel);
}

final class MapReceiptSenderSelector implements ReceiptSenderSelector {
    private final Map<ReceiptChannel, ReceiptSender> senders;

    MapReceiptSenderSelector(Map<ReceiptChannel, ReceiptSender> source) {
        Objects.requireNonNull(source, "source");
        EnumMap<ReceiptChannel, ReceiptSender> copy =
                new EnumMap<>(ReceiptChannel.class);
        for (Map.Entry<ReceiptChannel, ReceiptSender> entry
                : source.entrySet()) {
            copy.put(
                    Objects.requireNonNull(entry.getKey(), "channel"),
                    Objects.requireNonNull(entry.getValue(), "sender"));
        }
        this.senders = java.util.Collections.unmodifiableMap(copy);
    }

    @Override
    public ReceiptSender select(ReceiptChannel channel) {
        Objects.requireNonNull(channel, "channel");
        ReceiptSender result = senders.get(channel);
        if (result == null) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_RECEIPT_CHANNEL");
        }
        return result;
    }
}
```

Đoạn này có thể đặt cùng package với `ReceiptSender` ở ví dụ trước; nó dùng `enum` và `Map` để loại bỏ lookup tùy ý theo tên service. Composition root xây `Map<ReceiptChannel, ReceiptSender>`, rồi truyền `ReceiptSenderSelector` cho use case **thực sự cần chọn kênh động**. Dù selector là một hình thức lookup, nó khác Service Locator tổng quát vì **giới hạn vào một vai trò nghiệp vụ rõ ràng**.

**Lưu ý:** ví dụ code `OrderService` ở mục 5 **không cần selector**, vì chỉ dùng một sender cố định. Đừng thêm factory chỉ để “đúng mô hình DI”; chỉ tạo khi tình huống runtime đòi hỏi.

### 7.2. Factory cho đối tượng theo tác vụ

Khi mỗi tác vụ cần mở transaction riêng, inject một factory có phương thức `open()` phù hợp hơn inject một transaction dùng chung:

```java
// Các interface dưới đây là hợp đồng minh họa riêng.
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
            // Thực thi các thao tác ghi theo use case.
            work.commit();
        }
    }
}
```

Factory được inject có **kiểu và ý nghĩa rõ ràng**; `ImportService` chỉ biết “mở unit of work”, không biết `AppContainer.get(...)`. `try-with-resources` đảm bảo gọi `close()` khi thoát scope, nhưng hành vi commit/rollback vẫn phải được quy định bởi implementation thật.

### 7.3. Dấu hiệu một factory đã biến thành locator

Hãy cảnh giác khi API tiến hóa thành:

```java
interface EverythingFactory {
    <T> T create(Class<T> type);
}
```

Nếu lớp nghiệp vụ có thể yêu cầu mọi service tùy thích, chữ ký constructor lại không nói rõ nó thật sự cần gì. Khi đó nên chia factory theo vai trò (`ReceiptSenderSelector`, `UnitOfWorkFactory`, `ReportExporterFactory`) hoặc chuyển đối tượng bắt buộc thành constructor argument trực tiếp.

## 8. Refactor từng phần trong ứng dụng đang chạy

Một hệ thống cũ có thể có hàng trăm caller dùng locator, không thể đổi tất cả một lúc. Có thể tiến hành theo **nhánh trách nhiệm**:

1. **Viết characterization test:** ghi nhận hành vi hiện tại, thứ tự side effect và đường lỗi trước khi thay wiring. Đừng mặc định mã cũ luôn đúng; xác định những hành vi cần giữ và những lỗi cần sửa riêng.
2. **Chọn một lớp có ranh giới rõ:** ví dụ `OrderService`, chưa cần đổi toàn bộ controller và background worker trong cùng commit.
3. **Định nghĩa interface/port nếu thật sự cần:** tách chi tiết SDK hoặc database khỏi use case.
4. **Thêm constructor nhận dependency:** nếu cần tương thích tạm với API cũ, có thể có một factory/adapter chuyển tiếp ở bootstrap, nhưng hạn chế để service chứa constructor không tham số tự gọi locator.
5. **Dịch chuyển nơi lookup:** chỉ vùng composition root/legacy bootstrap còn tra registry; các lớp nghiệp vụ mới nhận các instance tường minh.
6. **Chuyển từng caller:** controller, command, scheduler, consumer được root truyền service mới, không tự tìm nó.
7. **Chạy lại test unit và integration:** kiểm tra lựa chọn adapter, scope/lifecycle và hành vi lỗi.
8. **Xóa đường cũ:** khi không còn caller, bỏ API locator không còn cần, static state và cleanup đặc thù của registry.

Một ranh giới chuyển tiếp minh bạch có thể trông như:

```java
// Pseudocode: lớp adapter CHỈ đặt tại legacy bootstrap.
// Mục tiêu cuối cùng là bỏ lookup này khi callers chuyển xong.
static OrderService createLegacyCompatibleOrderService(
        LegacyRegistry legacy) {

    OrderRepository repository =
            legacy.get(OrderRepository.class);
    ReceiptSender sender =
            legacy.get(ReceiptSender.class);

    return new OrderService(repository, sender);
}
```

Mã này vẫn lookup nhưng **chỉ ở nơi lắp ghép**, không còn trong `OrderService`. Đây là bước trung gian hợp lý khi chưa thể thay cấu hình toàn bộ hệ thống. Mục tiêu cuối cùng là root trực tiếp chọn các adapter hoặc sử dụng DI container được giới hạn ở ranh giới bootstrap.

### 8.1. Tránh đổi API và hành vi cùng lúc không kiểm soát

Nếu trước kia locator cho phép chọn `ReceiptSender` theo request, đổi sang một sender singleton có thể thay đổi chức năng. Cần phân loại **dependency bắt buộc cố định** với **strategy chọn động** trước khi refactor.

Tương tự, nếu locator cũ luôn tạo repository theo request còn composition root mới tạo một singleton, ta có thể vô tình thay **scope** dù code vẫn biên dịch. Hãy lập bảng “trước/sau” về số lượng instance, thời điểm tạo, độ thread-safe và quyền đóng tài nguyên.

## 9. Scope và vòng đời: hai rủi ro thường bị bỏ sót

### 9.1. Không giữ instance request-scoped trong singleton

Giả sử trước đây `GlobalServices.get(CurrentRequest.class)` trả đúng request context trong mỗi lần xử lý. Nếu refactor một cách cơ học thành:

```java
// Sai nếu service này được dùng chung cho cả ứng dụng.
final class SharedOrderService {
    private final RequestContext firstRequest;

    SharedOrderService(RequestContext request) {
        this.firstRequest = request;
    }
}
```

Ta đã **capture một request cụ thể** vào service sống lâu. Request sau có thể đọc nhầm dữ liệu request đầu; service còn giữ reference sau khi request kết thúc.

Các hướng sửa, tùy use case:

- Truyền `RequestContext` hoặc dữ liệu request cần thiết **qua tham số method**, không lưu trong singleton.
- Tạo `OrderService` theo request nếu service thực sự có state theo request.
- Inject một factory/provider có contract về request scope để lấy instance trong scope hiện hành, khi framework yêu cầu.

`RequestContext` trong đoạn trên là kiểu minh họa. Điểm cần hiểu là **constructor injection không tự giải quyết scope**; nó làm quan hệ tường minh để người thiết kế có thể kiểm tra.

### 9.2. Quyền sở hữu tài nguyên cần chuyển cùng wiring

Trước đây locator/container có thể sở hữu `DataSource`, HTTP client hoặc connection pool. Khi composition root bắt đầu tự tạo các tài nguyên đó, **phải xác định lại ai sẽ đóng chúng**.

```text
Composition root:
  tạo client/pool  ---> tạo adapter ---> inject vào service
       |                                      |
       +-------- sở hữu quyền close            +-- chỉ sử dụng
```

Nếu nhiều service cùng dùng một repository adapter hoặc HTTP client, từng service **không nên tự gọi `close()`**. Root hoặc lifecycle manager phải ngừng nhận việc, xử lý tác vụ còn lại rồi đóng các tài nguyên mà nó sở hữu, theo contract của từng thư viện.

Việc truyền dependency qua constructor **không tự bảo đảm** client được đóng, không khiến singleton thread-safe và không sửa được resource leak vốn có trong adapter.

### 9.3. Thời điểm lỗi có thể thay đổi

- Với Service Locator, thiếu binding có thể chỉ gây lỗi khi method ít dùng được gọi.
- Với constructor injection và eager wiring, thiếu dependency bắt buộc có thể được phát hiện tại startup.
- Nếu root inject một provider lazy, lỗi tạo dependency vẫn có thể xuất hiện ở first use.

Đây là lựa chọn về **readiness và failure policy**. Với dependency thiết yếu, thường muốn biết lỗi sớm trước khi nhận request; với tính năng tùy chọn, lazy có thể hợp lý nếu first-use failure được xử lý rõ.

## 10. Các anti-pattern khi “đã chuyển sang DI”

### 10.1. Inject nguyên container

`CheckoutService(Container container)` rồi `container.get(PaymentGateway.class)` vẫn ẩn `PaymentGateway`. Sửa thành `CheckoutService(PaymentGateway gateway)` khi dependency cố định.

### 10.2. Gom mọi thứ vào một bag phụ thuộc

```java
final class AllDependencies {
    OrderRepository repository;
    ReceiptSender sender;
    Object cache;
    Object logger;
    Object client;
}
```

Nếu mọi service đều nhận `AllDependencies`, constructor có vẻ ngắn nhưng hợp đồng dependency mất độ chính xác. Chỉ dùng một **nhóm cấu hình/dependency** khi nó là một khái niệm ổn định và thực sự thuộc trách nhiệm của lớp; không biến nhóm đó thành một locator có field.

### 10.3. Chuyển `new` từ method sang constructor nhưng vẫn tạo implementation cụ thể

```java
// Vẫn tự chọn implementation:
OrderService() {
    this.repository = new SqlOrderRepository();
}
```

Đoạn minh họa này không chuyển trách nhiệm lựa chọn ra ngoài. Nếu adapter cần thay theo môi trường hoặc test, hãy đưa vào composition root.

### 10.4. Tạo interface cho mọi thứ

DI không yêu cầu mỗi value object, thuật toán cục bộ hoặc collection đều có interface. Dùng abstraction khi nó biểu diễn một năng lực/cộng tác viên có ranh giới rõ, cần thay thế, hoặc hỗ trợ test/lifecycle.

### 10.5. Constructor chứa quá nhiều tham số

Nếu sau khi refactor, một service nhận 18 dependency, vấn đề có thể là **trách nhiệm quá rộng**. Đừng giấu tất cả trong `Dependencies` để constructor ngắn hơn. Hãy xem service có đang làm quá nhiều use case, có thể chia thành các thành phần chuyên trách hay không.

### 10.6. Xóa registry nhưng bỏ qua composition root

Nếu mỗi controller lại `new SqlOrderRepository()` và `new SmtpReceiptSender()`, lựa chọn implementation vẫn bị phân tán. DI đạt mục tiêu tốt nhất khi **tạo và lắp ghép tập trung ở bootstrap**, còn controller/service chỉ sử dụng dependency được cấp.

### 10.7. Phá vòng phụ thuộc bằng cách thêm locator

Nếu `A` cần `B` và `B` cần `A`, constructor injection làm vòng phụ thuộc lộ rõ. Không nên giấu nó sau `get(A.class)` trong một method. Cần xem lại trách nhiệm, tách vai trò chung, hướng sự kiện hoặc kiến trúc callback; factory/provider chỉ nên được chọn khi vòng đời hoặc nhu cầu tạo động thực sự đòi hỏi.

## 11. Bảng kiểm chứng trước và sau refactor

| Câu hỏi | Trước với Service Locator | Sau với DI tường minh |
| --- | --- | --- |
| Có biết service cần dependency nào từ constructor? | Thường không; phải tìm lời gọi `get`. | Có; các contract được khai báo ở constructor. |
| Có thể tạo service độc lập mà không dựng registry toàn cục? | Khó nếu lookup sâu trong method. | Có, truyền fake/stub trong unit test. |
| Thiếu dependency bắt buộc có được phát hiện sớm? | Có thể lỗi muộn ở nhánh ít chạy. | Có thể fail-fast khi khởi tạo nếu được kiểm tra. |
| Ai quyết định implementation? | Registry được cấu hình ở nơi có thể không rõ. | Composition root và các factory có vai trò rõ. |
| Có vô tình thay scope khi chuyển wiring? | Cần khảo sát cơ chế cũ. | Cần xác minh instance và thời điểm tạo mới. |
| Ai đóng tài nguyên? | Locator/container hoặc code riêng. | Root/lifecycle manager theo ownership đã định. |
| Caller có biết framework container không? | Có thể biết hoặc lấy service từ global. | Caller nhận service/port rõ qua constructor. |
| Có test không phụ thuộc thứ tự chạy? | Dễ bị state registry ảnh hưởng. | Object graph test có thể tạo mới từng trường hợp. |

### 11.1. Những phép kiểm thử nên giữ và bổ sung

- **Characterization test:** xác nhận hành vi quan trọng trước khi thay wiring.
- **Unit test:** fake repository/sender, kiểm tra validation, thứ tự side effect và đường lỗi.
- **Composition smoke test:** khởi tạo graph như cấu hình thật, kiểm tra thiếu binding, `null`, chu trình khởi tạo và readiness cơ bản.
- **Integration test:** adapter SQL, email, queue hoặc HTTP được kiểm tra với môi trường thử an toàn.
- **Scope/lifecycle test:** hai request không giữ state của nhau; tài nguyên mở/đóng đúng số lần, kể cả khi startup hoặc request thất bại.
- **Regression test:** các caller đã chuyển sang API mới không còn truy cập locator và không làm thay đổi hành vi được yêu cầu.

Không thể chỉ dựa vào việc test unit PASS rồi kết luận toàn bộ cấu hình DI production đã đúng. Composition root cần được kiểm tra như một phần riêng của ứng dụng.

## 12. Bài tập thực hành: thay locator trong hệ thống thông báo

**Bối cảnh:** hệ thống có `NotificationService` gửi thông báo sau khi lưu đơn hàng. Hiện tại, nó sử dụng:

```java
// Mã ví dụ trước refactor.
final class LegacyNotificationService {
    void notifyOrder(String orderId) {
        MessageRepository repository =
                Services.get(MessageRepository.class);
        MessageSender sender =
                Services.get(MessageSender.class);
        repository.save(orderId);
        sender.send(orderId);
    }
}
```

Hãy thực hiện:

1. **Chỉ ra dependency ẩn:** lập danh sách các collaborator, thời điểm lookup và những lỗi có thể xuất hiện khi registry chưa có binding.
2. **Thiết kế interface phù hợp:** cho biết `MessageRepository` và `MessageSender` đã đủ hẹp hay cần chỉnh để phản ánh đúng use case.
3. **Refactor constructor:** viết `NotificationService(MessageRepository repository, MessageSender sender)`, kiểm tra `null`, loại bỏ mọi lời gọi `Services.get`.
4. **Tạo composition root:** lắp một `InMemoryMessageRepository` và `ConsoleMessageSender` cho demo; chỉ rõ cách thay bằng adapter thật mà không sửa service.
5. **Viết unit test:** truyền fake repository và spy sender; kiểm tra lưu thành công thì gửi một lần, lưu thất bại không gửi, thiếu dependency fail-fast.
6. **Xử lý chọn kênh động:** nếu thông báo có kênh `EMAIL`, `SMS`, `PUSH`, hãy thiết kế `MessageSenderSelector` dựa trên enum và map. Vì sao không inject `Container` để chọn sender?
7. **Phân tích scope:** nếu một sender giữ token người dùng theo request, có được đưa instance đó vào singleton notification service không? Đề xuất cách cấp đúng scope.
8. **Lập kế hoạch chuyển đổi:** nếu 40 caller còn gọi `Services.get(NotificationService.class)`, hãy nêu cách chuyển dần qua entry point/factory ở bootstrap trước khi xóa registry.
9. **Kiểm tra vận hành:** ai sở hữu và đóng SMTP/HTTP client? Nếu sender hoặc repository được khởi tạo lazy, thời điểm lỗi có thay đổi không?

**Gợi ý tự đối chiếu:** lớp nghiệp vụ chỉ nên nhận những hợp đồng nó thực sự cần; root lựa chọn implementation và quản lý lifecycle. Một resolver riêng cho kênh thông báo có hợp đồng hẹp hơn Service Locator tổng quát. Fake/test spy giúp kiểm chứng logic sử dụng mà không gửi thông báo thật, còn integration test kiểm tra adapter thực. Việc thay toàn cục `Services.get` bằng `new` rải rác trong controller **không** phải kết quả mong muốn của refactor DI.

**Điểm cần nhớ:** Refactor Service Locator sang DI là chuyển **quyền tìm và chọn dependency** từ lớp nghiệp vụ về **composition root**. Đích đến là những constructor và factory có **hợp đồng rõ ràng theo vai trò**, có thể lắp ghép và kiểm thử bằng Java thuần. Hãy làm từng bước, giữ hành vi, kiểm soát scope/lifecycle và chỉ sau đó dùng DI container để giảm wiring lặp, thay vì đưa container trở lại giữa logic nghiệp vụ.
