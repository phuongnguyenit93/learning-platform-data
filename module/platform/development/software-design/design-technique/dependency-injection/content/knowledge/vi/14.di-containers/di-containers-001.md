# Container là gì và phần công việc được tự động hóa

Khi thực hành **Dependency Injection (DI)** bằng Java thuần, ta có thể tự tạo `OrderRepository`, `PaymentGateway`, rồi truyền chúng vào constructor của `CheckoutService`. Cách này giúp tách **mã sử dụng dependency** khỏi **mã chọn, tạo và lắp ghép dependency**, đúng tinh thần Inversion of Control (IoC). Tuy nhiên, khi ứng dụng có hàng trăm đối tượng, nhiều môi trường cấu hình và những vòng đời khác nhau, composition root có thể phải thực hiện rất nhiều bước lặp lại.

**DI container** (bộ chứa Dependency Injection) là thành phần phần mềm **quản lý cách tạo, cung cấp, nối và thường cả vòng đời của các đối tượng** theo cấu hình hoặc quy tắc đăng ký. Một container có thể thay chúng ta thực hiện phần lớn những thao tác lắp ghép lặp lại; các class nghiệp vụ vẫn có thể nhận dependency qua constructor như khi dùng Java thuần.

Điểm cốt lõi của bài học thuộc chương **Bộ chứa DI** là nhận ra **container tự động hóa việc gì**, **cần cấu hình/hợp đồng gì để làm được**, và **những quyết định thiết kế nào vẫn thuộc trách nhiệm của lập trình viên**. Ta sẽ bắt đầu từ composition root thủ công, mô phỏng cơ chế của container bằng Java 17, rồi mới xem khái niệm tương ứng trong framework.

Sau bài này, bạn có thể:

- Phân biệt **DI**, **IoC**, **Dependency Inversion Principle (DIP)** và **DI container**.
- Giải thích cơ chế **đăng ký (registration/binding)**, **giải quyết phụ thuộc (resolution)** và **lắp ghép đồ thị đối tượng (object graph)**.
- Hiểu cách container có thể quản lý singleton, đối tượng tạo mới, scope theo request và lifecycle.
- Chỉ ra những việc container **không** tự quyết định: ranh giới nghiệp vụ, interface, tính an toàn luồng, tính đúng của scope và giao dịch.
- Chạy một ví dụ Java thuần mô phỏng container rất nhỏ để thấy rõ việc container gọi constructor và tái sử dụng đối tượng.
- Nhận diện lỗi thiếu binding, binding mơ hồ, chu trình phụ thuộc và việc lạm dụng container như service locator.

## 1. Từ DI thủ công đến DI container

Giả sử chức năng checkout cần repository và bộ gửi thông báo:

~~~java
interface OrderRepository {
    void save(Order order);
}

interface NotificationSender {
    void notifyOrder(Order order);
}

final class CheckoutService {
    private final OrderRepository orders;
    private final NotificationSender notifications;

    CheckoutService(
            OrderRepository orders,
            NotificationSender notifications) {
        this.orders = java.util.Objects.requireNonNull(orders);
        this.notifications = java.util.Objects.requireNonNull(notifications);
    }

    void checkout(Order order) {
        orders.save(order);
        notifications.notifyOrder(order);
    }
}
~~~

Bản thân `CheckoutService` chỉ mô tả **hợp đồng cần dùng**; nó không quan tâm repository dùng JDBC hay dữ liệu trong RAM, thông báo được gửi qua email hay in console.

Với DI thủ công, mã khởi động thực hiện:

~~~java
OrderRepository orders = new InMemoryOrderRepository();
NotificationSender sender = new ConsoleNotificationSender();
CheckoutService checkout = new CheckoutService(orders, sender);
~~~

Trong một DI container, thay vì tự viết toàn bộ chuỗi tạo đối tượng tại mọi entry point, ta **khai báo hoặc đăng ký** quy tắc tương tự:

~~~text
OrderRepository       -> InMemoryOrderRepository
NotificationSender    -> ConsoleNotificationSender
CheckoutService       -> constructor(OrderRepository, NotificationSender)
~~~

Khi thành phần khởi động ứng dụng yêu cầu `CheckoutService`, container có thể:

1. Xác định class/factory nào tạo `CheckoutService`.
2. Đọc hoặc đã biết những dependency mà constructor cần.
3. Tìm các binding tương ứng với `OrderRepository` và `NotificationSender`.
4. Tạo hoặc lấy các dependency theo scope được cấu hình.
5. Truyền chúng vào constructor và trả về instance `CheckoutService` hoàn chỉnh.
6. Quản lý các hoạt động lifecycle cần thiết theo khả năng của container.

**Container không thay đổi ý nghĩa nghiệp vụ của `checkout()`.** Nó chịu trách nhiệm *cách có được đối tượng checkout hợp lệ*, còn service chịu trách nhiệm *thao tác checkout thực hiện gì*.

### Một hình dung về điểm bàn giao

~~~mermaid
flowchart TD
    Boot["Bootstrap / composition root"] --> Config["Đăng ký binding, scope, cấu hình"]
    Config --> Container["DI container"]
    Boot -->|"Yêu cầu CheckoutService"| Container
    Container -->|"Tạo/lấy theo binding"| Repo["OrderRepository adapter"]
    Container -->|"Tạo/lấy theo binding"| Sender["NotificationSender adapter"]
    Repo -->|"constructor argument"| Service["CheckoutService"]
    Sender -->|"constructor argument"| Service
    Container -->|"Trả instance đã lắp ghép"| Service
    Service -->|"Xử lý yêu cầu"| Behavior["Logic checkout"]
~~~

Trong sơ đồ, các mũi tên dựng dependency thể hiện vai trò của container; lời gọi nghiệp vụ diễn ra sau khi service được cung cấp. Thứ tự khởi tạo cụ thể có thể khác nhau tùy container, factory và cơ chế eager/lazy.

## 2. Các thuật ngữ thường dùng

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Registration / binding** | Quy tắc liên kết một hợp đồng hoặc khóa đăng ký với cách cung cấp object | `OrderRepository -> JdbcOrderRepository` |
| **Resolution** | Quá trình container tìm và cung cấp đối tượng theo binding | Resolve `CheckoutService` |
| **Object graph** | Các instance và quan hệ phụ thuộc giữa chúng | Checkout → repository → data source |
| **Factory / provider** | Hàm hoặc đối tượng tạo/lấy dependency khi được yêu cầu | `() -> new Repository(client)` |
| **Scope** | Ranh giới tái sử dụng một instance | Một instance toàn ứng dụng hoặc một instance mỗi request |
| **Lifecycle** | Quá trình tạo, chuẩn bị, sử dụng và giải phóng | Khởi tạo client, sử dụng, đóng khi ứng dụng dừng |
| **Composition root** | Ranh giới nơi ứng dụng quyết định cách lắp ghép và bắt đầu sử dụng đồ thị | Main, bootstrap, cấu hình ứng dụng |
| **Container-managed object** | Instance được container tạo/cung cấp và thường được quản lý theo quy tắc của nó | Một bean/service đăng ký trong container |

Tên gọi và API cụ thể có thể khác nhau: một framework dùng `bean`, framework khác dùng `component` hoặc `service`. Ý tưởng chung vẫn là container có **quy tắc cấp dependency** và dùng chúng để lắp ghép đồ thị.

## 3. Container thường tự động hóa những công việc nào?

Không phải mọi container có mọi tính năng dưới đây, nhưng đây là các nhóm chức năng quan trọng cần hiểu.

| Công việc | DI thủ công | Container thường hỗ trợ thế nào? |
| --- | --- | --- |
| **Chọn implementation** | Tự `new JdbcOrderRepository(...)` trong bootstrap | Binding interface → implementation hoặc factory |
| **Tạo đối tượng và truyền dependency** | Gọi từng constructor theo thứ tự | Resolve quan hệ phụ thuộc, gọi constructor/factory |
| **Tái sử dụng instance** | Giữ tham chiếu và truyền lại thủ công | Cache theo singleton, request scope hoặc scope khác |
| **Tạo mới khi cần** | Viết factory/Supplier và truyền vào | Binding transient, provider/factory do container cấp |
| **Đọc cấu hình cho adapter** | Bootstrap tự chuyển giá trị cấu hình thành tham số | Một số container/framework hỗ trợ cấu hình được inject |
| **Khởi tạo/giải phóng tài nguyên** | Tự quản lý `AutoCloseable` và trình tự đóng | Có thể quản lý lifecycle callback/disposal trong scope |
| **Phát hiện lỗi lắp ghép** | Thường phát hiện lúc biên dịch/gọi constructor hoặc chạy startup | Có thể báo thiếu binding, vòng phụ thuộc, binding mơ hồ |
| **Tích hợp entry point** | Mỗi main/handler tự nhận service từ bootstrap | Framework có thể cấp service đã lắp vào handler/controller |

Câu “container tự động hóa” **không có nghĩa mọi thứ đều chạy mà không cần quyết định**. Lập trình viên vẫn phải chỉ ra **hợp đồng**, **implementation**, **scope**, **cấu hình**, **điểm khởi động** và **quy tắc sở hữu tài nguyên**. Framework có thể suy luận một phần thông tin qua annotation, reflection, convention hoặc mã được tạo lúc build, nhưng không thể suy ra toàn bộ ý định nghiệp vụ.

### Những công việc container không tự làm thay

- Chọn ranh giới hợp lý giữa `CheckoutService`, `PaymentGateway` và `OrderRepository`.
- Viết hợp đồng đúng về lỗi, retry, idempotency và tính nhất quán.
- Bảo đảm adapter thread-safe chỉ vì nó được cấu hình singleton.
- Bảo đảm transaction nguyên tử giữa gọi API thanh toán, lưu DB và gửi email.
- Tự sửa vòng phụ thuộc vốn xuất phát từ trách nhiệm hai chiều không hợp lý.
- Tự làm cho unit test nghiệp vụ chính xác khi fake không giữ đúng hợp đồng.
- Quyết định một request có tương đương một unit of work hay không.

Những nội dung ấy thuộc **thiết kế kiến trúc, hợp đồng và yêu cầu vận hành**. Container chủ yếu giúp biến quyết định đã có thành quy trình tạo và cấp đối tượng nhất quán.

## 4. Chu trình làm việc: đăng ký, resolve, sử dụng, đóng

Có thể hình dung một ứng dụng theo các giai đoạn:

~~~mermaid
flowchart TD
    A["1. Bootstrap"] --> B["2. Đăng ký binding và scope"]
    B --> C["3. Validate cấu hình / đồ thị khi được hỗ trợ"]
    C --> D["4. Resolve entry service"]
    D --> E["5. Lấy hoặc tạo dependency"]
    E --> F["6. Constructor injection"]
    F --> G["7. Thực hiện nghiệp vụ"]
    G --> H["8. Kết thúc scope / ứng dụng"]
    H --> I["9. Giải phóng tài nguyên thuộc quyền quản lý"]
~~~

Một số điểm cần phân biệt:

**Đăng ký không nhất thiết đồng nghĩa tạo object ngay.** Một container có thể lưu factory trước và chỉ gọi nó khi có lần resolve đầu tiên; container khác tạo sẵn một số singleton lúc startup. Điều đó phụ thuộc chế độ eager/lazy và cấu hình.

**Resolve không nhất thiết tạo instance mới.** Cùng một yêu cầu có thể trả về singleton đã tạo, đối tượng thuộc request hiện tại hoặc instance mới, tùy scope.

**Validate không đồng nghĩa chạy thử toàn bộ nghiệp vụ.** Container có thể phát hiện lỗi binding hoặc chu trình phụ thuộc trong lúc khởi tạo, nhưng thường không biết nội dung SQL, tình trạng API bên ngoài hoặc quy tắc checkout có đúng không. Một số lỗi vẫn chỉ xuất hiện khi đường xử lý tương ứng được gọi.

**Đóng container không đồng nghĩa đóng mọi object từng được trả ra.** Chính sách disposal khác nhau theo framework, scope và ownership. Đối tượng tạo ngoài container, đối tượng được caller sở hữu hoặc đối tượng trong scope riêng có thể cần quy trình đóng khác. Phải đọc hợp đồng lifecycle của container cụ thể.

## 5. Bắt đầu bằng Java thuần: một composition root rõ ràng

Đây là phiên bản đơn giản không cần container; các lớp nhận dependency qua constructor. Nó là đường cơ sở để thấy những thao tác container sẽ thay ta thực hiện.

~~~java
// Các interface và adapter nằm trong ứng dụng.
OrderRepository orders = new InMemoryOrderRepository();
NotificationSender notifications = new ConsoleNotificationSender();

CheckoutService checkout =
        new CheckoutService(orders, notifications);

checkout.checkout(new Order("ORD-01", 125_000));
~~~

Ngay cả khi đổi sang container, **chữ ký constructor của `CheckoutService` vẫn có thể giữ nguyên**. Điều thay đổi là nơi mô tả và thực thi wiring, không phải thuật toán checkout.

Việc sử dụng interface ở đây phù hợp **Dependency Inversion Principle (DIP)**: phần nghiệp vụ phụ thuộc abstraction; adapter cụ thể thực hiện abstraction. **DI** là kỹ thuật cung cấp dependency từ bên ngoài; **IoC** mô tả quyền điều khiển quá trình tạo và lắp ghép được đưa ra khỏi service. **DI container** chỉ là công cụ tự động hóa việc cung cấp này.

## 6. Thực hành Java 17: mô phỏng một container rất nhỏ

Để thấy chính xác container phải làm gì, ta viết một **MiniContainer** giáo dục chỉ có ba chức năng:

1. Đăng ký factory theo một kiểu Java (`Class<T>`).
2. Resolve dependency thông qua factory đã đăng ký.
3. Tái sử dụng singleton hoặc tạo instance mới ở mỗi lần resolve, đồng thời phát hiện vòng lặp trực tiếp trong quá trình resolve.

Nó **không** phải container production: chưa có request scope, quản lý shutdown, đa luồng, annotation scanning, qualifier, cấu hình, graph validation toàn diện hay xử lý sự cố khởi tạo phức tạp. Việc tự viết lớp nhỏ này nhằm **minh họa cơ chế**, không phải đề xuất xây một DI framework riêng cho sản phẩm.

Lưu toàn bộ đoạn sau vào `Main.java`. Ví dụ chạy với Java 17+ và không cần thư viện ngoài.

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Supplier;

record Order(String id, long amountCents) {
    Order {
        if (id == null || id.isBlank() || amountCents <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
    }
}

interface OrderRepository {
    void save(Order order);
    int count();
}

interface NotificationSender {
    void notifyOrder(Order order);
}

final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public void save(Order order) {
        if (orders.putIfAbsent(order.id(), order) != null) {
            throw new IllegalArgumentException("Duplicate order");
        }
    }

    @Override
    public int count() {
        return orders.size();
    }
}

final class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void notifyOrder(Order order) {
        System.out.println("Confirmed: " + order.id());
    }
}

final class CheckoutService {
    private final OrderRepository orders;
    private final NotificationSender notifications;

    CheckoutService(
            OrderRepository orders,
            NotificationSender notifications) {
        this.orders = Objects.requireNonNull(orders, "orders");
        this.notifications =
                Objects.requireNonNull(notifications, "notifications");
    }

    void checkout(Order order) {
        Objects.requireNonNull(order, "order");
        orders.save(order);
        notifications.notifyOrder(order);
    }
}

// Container tối giản để quan sát registration và resolution.
final class MiniContainer {
    private final Map<Class<?>, Supplier<?>> registrations =
            new HashMap<>();
    private final Set<Class<?>> singletonKeys = new HashSet<>();
    private final Map<Class<?>, Object> singletons = new HashMap<>();
    private final Set<Class<?>> resolving = new HashSet<>();

    <T> void singleton(Class<T> type, Supplier<? extends T> factory) {
        register(type, factory);
        singletonKeys.add(type);
    }

    <T> void transientType(Class<T> type, Supplier<? extends T> factory) {
        register(type, factory);
    }

    private <T> void register(
            Class<T> type, Supplier<? extends T> factory) {
        Objects.requireNonNull(type, "type");
        Objects.requireNonNull(factory, "factory");
        if (registrations.putIfAbsent(type, factory) != null) {
            throw new IllegalStateException(
                    "Already registered: " + type.getName());
        }
    }

    <T> T resolve(Class<T> type) {
        Objects.requireNonNull(type, "type");

        Object existing = singletons.get(type);
        if (existing != null) {
            return type.cast(existing);
        }

        Supplier<?> factory = registrations.get(type);
        if (factory == null) {
            throw new IllegalStateException(
                    "Missing binding: " + type.getName());
        }

        if (!resolving.add(type)) {
            throw new IllegalStateException(
                    "Circular resolution: " + type.getName());
        }
        try {
            Object created = Objects.requireNonNull(
                    factory.get(), "Factory returned null");
            T result = type.cast(created);

            if (singletonKeys.contains(type)) {
                singletons.put(type, result);
            }
            return result;
        } finally {
            resolving.remove(type);
        }
    }
}

public class Main {
    public static void main(String[] args) {
        MiniContainer container = new MiniContainer();

        // Chỉ vùng bootstrap biết các implementation cụ thể.
        container.singleton(
                OrderRepository.class,
                InMemoryOrderRepository::new);
        container.singleton(
                NotificationSender.class,
                ConsoleNotificationSender::new);

        // Factory thể hiện constructor injection.
        container.transientType(
                CheckoutService.class,
                () -> new CheckoutService(
                        container.resolve(OrderRepository.class),
                        container.resolve(NotificationSender.class)));

        CheckoutService first =
                container.resolve(CheckoutService.class);
        CheckoutService second =
                container.resolve(CheckoutService.class);

        System.out.println("Different services: " + (first != second));
        System.out.println(
                "Shared repository: "
                + (container.resolve(OrderRepository.class)
                   == container.resolve(OrderRepository.class)));

        first.checkout(new Order("ORD-01", 125_000));
        System.out.println(
                "Saved orders: "
                + container.resolve(OrderRepository.class).count());
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
Different services: true
Shared repository: true
Confirmed: ORD-01
Saved orders: 1
~~~

### Vì sao code cho kết quả đó?

- `container.singleton(OrderRepository.class, ...)` **đăng ký** cách tạo repository và cách tái sử dụng. Lần resolve đầu tiên tạo object; lần sau trả đúng instance đã giữ.
- `container.transientType(CheckoutService.class, ...)` yêu cầu **gọi factory mỗi lần resolve**; vì vậy hai `CheckoutService` là hai object khác nhau.
- Factory của `CheckoutService` tự yêu cầu container resolve các dependency. Đây là cơ chế **đồ thị được dựng qua factory**, được khai báo ở bootstrap.
- Khi `first.checkout(...)` chạy, nó gọi collaborator qua interface. Nó **không biết `MiniContainer` tồn tại**, nên vẫn test độc lập được bằng constructor.
- Cặp `HashMap`/`HashSet` và thao tác `resolve` trong ví dụ **không an toàn cho concurrent access**. Nếu nhiều thread cùng resolve, có thể tạo sai số instance hoặc gây lỗi; một container thực tế phải có chính sách đồng thời phù hợp.

### Vì sao không thể xem MiniContainer là production container?

Mục tiêu của `MiniContainer` chỉ là cho thấy logic cơ bản của registry, scope đơn giản và resolution. Một container thực tế có thể phải xử lý qualifier cho nhiều implementation cùng interface, vòng phụ thuộc phức tạp, constructor/factory discovery, lỗi khi tạo giữa chừng, scope lồng nhau, lifecycle callback, đóng tài nguyên và validation.

Ví dụ này cũng không tự quét annotation. Dù `CheckoutService` có constructor rõ ràng, factory vẫn được **đăng ký thủ công**. Những framework cung cấp component scanning hoặc constructor inspection có thể giảm phần boilerplate, nhưng mỗi framework có quy tắc riêng và vẫn cần cấu hình khi có nhiều lựa chọn.

## 7. Điều gì xảy ra khi có nhiều implementation?

Giả sử cả `EmailNotificationSender` và `SmsNotificationSender` cùng thực hiện `NotificationSender`:

~~~java
interface NotificationSender {
    void notifyOrder(Order order);
}
~~~

Container không thể tự suy ra người dùng muốn gửi email, SMS hay cả hai nếu không có quy tắc lựa chọn rõ ràng. Có thể chọn một trong những cách sau, tùy framework:

- Khai báo một implementation mặc định.
- Dùng **qualifier / named binding** để phân biệt các bản đăng ký.
- Đăng ký một collection và để consumer nhận nhiều implementation nếu đó là hợp đồng cần thiết.
- Dùng factory hoặc policy chọn adapter theo cấu hình tại bootstrap.

**Vấn đề thiếu/mơ hồ binding là vấn đề cấu hình của đồ thị, không phải lỗi mà service nghiệp vụ nên tự chữa.** Không nên để `CheckoutService` hỏi container có implementation nào, rồi tự quyết định chọn email/SMS. Quyết định đó thuộc về chính sách lắp ghép hoặc một hợp đồng nghiệp vụ cụ thể nếu nó thực sự thay đổi theo yêu cầu.

Một container có thể cho phép nhiều binding; cách chọn khi resolve interface cụ thể khác nhau theo sản phẩm. Không nên giả định rằng “lớp nào được đăng ký cuối sẽ thắng” là quy tắc chung.

## 8. Scope: container cung cấp cùng instance trong phạm vi nào?

Khi học container, một hiểu nhầm phổ biến là “inject bằng container thì service là singleton”. Thực tế **scope là quyết định tách biệt với việc sử dụng DI**.

| Phạm vi | Ý nghĩa | Ví dụ phù hợp | Điều cần kiểm tra |
| --- | --- | --- | --- |
| **Singleton / application** | Một instance tái sử dụng trong phạm vi container ứng dụng | Cấu hình bất biến, client dùng chung an toàn | Trạng thái mutable và thread safety |
| **Transient / prototype** | Tạo instance mới theo quy tắc của container mỗi lần được yêu cầu | Đối tượng không có trạng thái dùng chung cần thiết | Chi phí tạo và quyền sở hữu khi được trả ra |
| **Request-scoped** | Cùng instance trong một request; khác giữa các request | Request context, dữ liệu gắn với request | Không inject sai vào object sống lâu hơn request |
| **Job / unit-of-work scope** | Cùng instance trong một công việc | Context giao dịch hoặc phiên xử lý | Ranh giới bắt đầu/kết thúc và commit/rollback |
| **Custom scope** | Ứng dụng/framework định nghĩa miền tái sử dụng riêng | Session theo tenant hoặc workflow | Chính sách đóng, đồng thời và isolation |

Một số framework dùng tên khác nhau hoặc có thêm scope đặc thù. Đặc biệt, **các framework khác nhau có thể định nghĩa singleton theo phạm vi container/context riêng**, không có nghĩa mọi JVM đều có một object duy nhất.

### Cẩn thận khi một singleton nhận dependency ngắn hạn

Giả sử `ReportScheduler` là singleton nhưng constructor nhận `WorkContext` có scope mỗi job. Nếu container cung cấp một object job rồi singleton giữ nó mãi, các job sau có thể dùng trạng thái cũ.

Có một số cách thiết kế:

1. Truyền dữ liệu của job thành tham số phương thức nếu đây chỉ là thông tin của từng lần chạy.
2. Inject **factory/provider** có hợp đồng rõ ràng để tạo/lấy `WorkContext` khi job bắt đầu.
3. Tại composition root hoặc bộ điều phối, tạo một work scope rồi truyền cùng context cho những bước thuộc **cùng job**.

Provider không mặc định tạo mới: `Provider.get()` có thể trả cùng instance trong scope hiện tại hoặc một instance mới tùy binding. Vì vậy khi dùng container, cần kiểm tra **scope của binding**, **đường đi của provider** và **quyền sở hữu tài nguyên**.

## 9. Lifecycle và sở hữu tài nguyên

Ngoài việc tạo đối tượng, một số container còn quản lý callback chuẩn bị và hủy đối tượng. Ví dụ một gateway có thể sở hữu HTTP client, connection pool hoặc thread pool. Nếu đối tượng được container tạo và quản lý, framework có thể hỗ trợ giải phóng khi scope kết thúc.

Tuy nhiên, không được suy ra “mọi object implement `AutoCloseable` đều sẽ luôn được container đóng đúng lúc”. Quy tắc tùy container và cách đăng ký factory; đặc biệt object do caller tự tạo hoặc object trong scope tùy chỉnh có thể cần owner riêng.

Trong DI thủ công, quyền sở hữu thường hiện rõ:

~~~java
// Minh họa: một dependency là tài nguyên do bootstrap sở hữu.
try (ExternalClient client = new ExternalClient(/* config */)) {
    OrderRepository repo = new RemoteOrderRepository(client);
    CheckoutService service = new CheckoutService(repo, sender);
    service.checkout(order);
}
~~~

Đoạn trên là mã minh họa, chưa khai báo các class kỹ thuật. Khi dùng container, cần đạt **bảo đảm tương đương**: client được tạo/cấp theo đúng scope và được đóng bởi đúng chủ sở hữu khi không còn được sử dụng.

Đặc biệt, service chỉ được **inject một client dùng chung để sử dụng** không nên tự gọi `client.close()` sau mỗi request. Cách đóng đó có thể khiến các service khác sử dụng cùng client bị lỗi.

### Nếu bootstrap thất bại giữa chừng?

Giả sử container tạo pool A thành công, rồi không tạo được gateway B do thiếu cấu hình. Một framework có thể hỗ trợ giải phóng tài nguyên đã khởi tạo theo lifecycle được quy định; không nên mặc định mọi trường hợp đều tự rollback hoàn hảo. Với nguồn lực đặc biệt hoặc factory tự viết, cần đọc quy tắc exception handling và shutdown, đồng thời có kiểm thử tích hợp phù hợp.

## 10. Phát hiện sớm lỗi cấu hình và đồ thị

Một ưu điểm tiềm năng của container là tập trung quy tắc lắp ghép ở một chỗ để phát hiện lỗi sớm hơn, tùy khả năng và cách khởi động của framework.

| Lỗi | Triệu chứng | Kiểm tra nên thực hiện |
| --- | --- | --- |
| **Thiếu binding** | Không thể tạo `CheckoutService` vì thiếu `OrderRepository` | Khởi tạo/resolve entry service trong test khởi động |
| **Binding mơ hồ** | Có nhiều implementation, không biết chọn cái nào | Chọn qualifier hoặc cấu hình rõ ràng |
| **Vòng constructor** | A cần B, B cần A | Xem lại ranh giới trách nhiệm và hướng phụ thuộc |
| **Scope không tương thích** | Singleton giữ request context, dữ liệu rò giữa yêu cầu | Kiểm tra lifetime của dependency và consumer |
| **Factory trả null / sai kiểu** | Resolution lỗi lúc chạy | Đặt hợp đồng factory và validate khi phù hợp |
| **Cấu hình chưa hợp lệ** | Gateway không tạo được do endpoint/secret thiếu | Xác thực cấu hình ở bootstrap, không đợi đến request hiếm gặp |
| **Quản lý tài nguyên không đúng** | Client/pool bị rò hoặc đóng quá sớm | Xác định owner, scope và hành vi shutdown |

**Không phải container nào cũng phát hiện tất cả lỗi ở startup.** Chẳng hạn binding lazy có thể chỉ được resolve khi dùng; provider có thể dời việc lấy dependency sang thời điểm runtime; lỗi kết nối tới hệ thống ngoài có thể xuất hiện sau khi container đã khởi động thành công.

Nếu cần bảo đảm một chức năng quan trọng thực sự lắp được, hãy có **smoke test khởi động** hoặc bài kiểm thử tích hợp resolve những entry service cần thiết theo đúng môi trường thử nghiệm.

## 11. Vì sao không nên gọi container trực tiếp trong service nghiệp vụ?

Một ứng dụng có thể cho lớp nghiệp vụ giữ tham chiếu đến container rồi tự gọi `resolve`:

~~~java
// Minh họa một kiểu thiết kế nên tránh trong service.
final class CheckoutService {
    private final Container container;

    CheckoutService(Container container) {
        this.container = container;
    }

    void checkout(Order order) {
        OrderRepository repository =
                container.resolve(OrderRepository.class);
        repository.save(order);
    }
}
~~~

Điều đó biến container thành **service locator** mà nghiệp vụ chủ động tra cứu dependency. Vấn đề là:

- Constructor không cho thấy `CheckoutService` thực sự cần `OrderRepository`.
- Test phải chuẩn bị container hoặc giả lập cơ chế resolve, thay vì truyền fake repository thẳng vào constructor.
- Logic nghiệp vụ bị ghép nối với API container.
- Lỗi thiếu binding có thể dời đến đúng thời điểm phương thức được gọi.

Cách rõ hơn:

~~~java
final class CheckoutService {
    private final OrderRepository repository;

    CheckoutService(OrderRepository repository) {
        this.repository = java.util.Objects.requireNonNull(repository);
    }

    void checkout(Order order) {
        repository.save(order);
    }
}
~~~

Container chỉ xuất hiện tại vùng khởi động hoặc cấu hình để gọi constructor này. **Dùng DI container không đòi hỏi service biết container tồn tại**. Cách thiết kế đó giúp giữ unit test bằng Java thuần, ngay cả khi production dùng một framework lớn.

## 12. Liên hệ với framework: điều gì được khai báo thay cho mã `new`?

Các container có cơ chế đăng ký khác nhau. Có framework dùng configuration code, có framework dùng annotation/scanning, có framework sinh code ở thời điểm build. Ví dụ dưới đây minh họa *ý tưởng* cấu hình trong Spring; nó **cần Spring dependency và import phù hợp**, không phải chương trình Java thuần có thể biên dịch độc lập:

~~~java
@Configuration
class ApplicationWiring {
    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    CheckoutService checkoutService(
            OrderRepository repository,
            NotificationSender sender) {
        return new CheckoutService(repository, sender);
    }
}
~~~

Các phương thức cấu hình cung cấp cách tạo đối tượng, còn framework điều phối và quản lý chúng theo quy tắc của container. Ví dụ Spring với `@Bean` thường dùng singleton scope theo mặc định trong một application context, nhưng có thể cấu hình scope khác khi cần. Các container khác có mặc định khác nhau.

Từ góc nhìn `CheckoutService`, không có thay đổi bắt buộc nào: class vẫn nhận interface qua constructor. Ta chỉ thay **cơ chế wiring** tại bootstrap.

Điều này cũng giải thích tại sao DI container không đồng nghĩa annotation. **Annotation là một cách cung cấp metadata**, không phải bản chất của DI. Dù dùng Java configuration, XML, module registration hay code generation, trọng tâm vẫn là **đăng ký và cung cấp đúng dependency theo scope và lifecycle**.

## 13. Kiểm thử: unit test không cần container, wiring test có thể cần

Có hai mức kiểm thử giải quyết hai loại câu hỏi riêng:

**Unit test của `CheckoutService`:** Khi repository và notifier hành xử theo hợp đồng, service có gọi chúng đúng hay không? Ta truyền fake vào constructor, không phải khởi động container.

**Wiring/boot test:** Container có được cấu hình đủ binding và scope để dựng service production hay không? Mức này có thể cần khởi động container với cấu hình kiểm thử tương ứng.

Ví dụ Java thuần dùng lại `Main.java` ở phần 6, đặt đoạn sau vào `CheckoutServiceTest.java` cùng thư mục:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CheckoutServiceTest {
    public static void main(String[] args) {
        List<String> calls = new ArrayList<>();

        OrderRepository orders = new OrderRepository() {
            private int count;

            @Override
            public void save(Order order) {
                calls.add("save:" + order.id());
                count++;
            }

            @Override
            public int count() {
                return count;
            }
        };

        NotificationSender sender =
                order -> calls.add("notify:" + order.id());

        CheckoutService service =
                new CheckoutService(orders, sender);
        service.checkout(new Order("TEST-1", 10_000));

        if (!calls.equals(
                List.of("save:TEST-1", "notify:TEST-1"))) {
            throw new AssertionError("Unexpected calls: " + calls);
        }
        if (orders.count() != 1) {
            throw new AssertionError("Order must be saved once");
        }

        System.out.println("PASS");
    }
}
~~~

Chạy:

~~~bash
javac Main.java CheckoutServiceTest.java
java CheckoutServiceTest
~~~

Đầu ra kỳ vọng: `PASS`.

Test này **không kiểm tra container**, vì nó đang kiểm tra đúng trách nhiệm của service. Bổ sung một test riêng cho registry/configuration nếu cần xác nhận bootstrap:

~~~java
// Mã minh họa kiểm tra wiring qua container của phần 6.
MiniContainer container = new MiniContainer();
container.singleton(OrderRepository.class, InMemoryOrderRepository::new);
container.singleton(NotificationSender.class, ConsoleNotificationSender::new);
container.transientType(CheckoutService.class, () ->
        new CheckoutService(
                container.resolve(OrderRepository.class),
                container.resolve(NotificationSender.class)));

if (container.resolve(CheckoutService.class) == null) {
    throw new AssertionError("Wiring failed");
}
~~~

Kiểm tra bootstrap thành công chỉ xác minh một phần cấu hình. Nó không thay thế unit test quy tắc nghiệp vụ, contract test cho adapter và kiểm thử tích hợp mạng/database.

## 14. Khi nào nên cân nhắc một DI container?

**DI thủ công là đủ** khi ứng dụng có đồ thị nhỏ, composition root dễ đọc, scope và ownership có thể được thể hiện rõ ràng, và các thay đổi triển khai không đòi sửa nhiều điểm wiring.

**DI container có thể đem lại lợi ích** khi:

- Ứng dụng có nhiều đồ thị con, entry point và môi trường cấu hình.
- Cùng quy tắc chọn và tạo adapter đang bị lặp lại.
- Scope request/job/session hoặc lifecycle callback cần được quản lý thống nhất.
- Việc resolve và kiểm tra binding trở thành công việc lặp đi lặp lại.
- Framework hiện có đã cung cấp container và nhóm có kinh nghiệm dùng đúng phạm vi của nó.

Một số đánh đổi cần tính đến là **chi phí học quy tắc framework**, cấu hình ẩn, lỗi có thể xảy ra ở runtime, khởi động và khả năng hiểu đồ thị khi số binding lớn. Các lựa chọn reflection, code generation và scanning cũng có đặc điểm triển khai riêng.

Không có mốc cố định “sau N class phải dùng container”. Hãy đo **độ khó thực tế của việc lắp ghép, thay thế và kiểm thử**, thay vì chọn công cụ chỉ theo số lớp.

## 15. Quy trình chuyển từ DI thủ công sang container

1. **Giữ dependency bắt buộc trong constructor.** Đảm bảo service không tự tạo adapter hoặc lấy từ global registry.
2. **Xác định interface và hành vi contract.** Đừng để container trở thành giải pháp che một abstraction thiết kế sai.
3. **Vẽ đồ thị và đánh dấu scope.** Chỉ rõ đối tượng dùng chung, per-request, per-job và tài nguyên cần đóng.
4. **Tập trung cấu hình tại composition root.** Chọn implementation và chính sách môi trường ở bootstrap.
5. **Chuyển từng nhóm wiring sang registration/binding.** Bắt đầu từ những phần ít rủi ro, giữ nguyên API service nếu có thể.
6. **Kiểm tra lỗi thiếu/mơ hồ binding và chu trình.** Resolve các entry service quan trọng trong môi trường test.
7. **Kiểm tra lifecycle.** Xác nhận ai tạo/đóng client, session, scheduler và cách scope kết thúc.
8. **Giữ unit test dùng Java thuần.** Test service qua fake; chỉ dùng container trong test thật sự cần xác nhận wiring hoặc tích hợp.
9. **Đọc quy tắc của framework cụ thể.** Mặc định scope, proxy, eager/lazy, injection order và disposal không hoàn toàn giống nhau giữa các container.

### Tự kiểm tra

**Tình huống A:** `CheckoutService` nhận `OrderRepository` qua constructor. Chuyển từ `new CheckoutService(repo)` sang đăng ký binding rồi để container tạo service có thay đổi thuật toán checkout không?

**Không.** Đây chủ yếu là thay đổi cơ chế tạo/lắp ghép. Service vẫn dùng cùng hợp đồng và giữ quy tắc nghiệp vụ.

**Tình huống B:** Hai bean đều triển khai `PaymentGateway`, không có qualifier hay chính sách chọn. Container có tự biết bên nào là cổng sản xuất không?

**Không thể dựa vào điều đó.** Phải cấu hình rõ lựa chọn hoặc cơ chế phân biệt theo API của container cụ thể.

**Tình huống C:** Một đối tượng singleton giữ `RequestContext` mutable của request đầu tiên. Có thể cho rằng container đã đảm bảo an toàn vì nó quản lý scope không?

**Không.** Đây có thể là lỗi phạm vi và rò dữ liệu giữa các request. Cần thiết kế lại cách cấp context và kiểm tra tính an toàn đồng thời.

**Tình huống D:** Một service gọi `container.resolve(OrderRepository.class)` ngay trong `checkout()`. Đã áp dụng DI theo cách tường minh nhất chưa?

**Chưa.** Đó là kiểu service locator khiến dependency bị ẩn. Constructor injection trực tiếp vào service giúp contract rõ và dễ kiểm thử hơn.

**Tình huống E:** Container khởi động thành công, nhưng một lần checkout thật vẫn gặp lỗi timeout database. Có mâu thuẫn không?

**Không.** Container chỉ bảo đảm được những điều nằm trong phạm vi validation và lifecycle của nó. Tính sẵn sàng của hệ thống ngoài, quy tắc retry và tính nhất quán giao dịch cần thiết kế và kiểm thử riêng.

## Ghi nhớ

**DI container tự động hóa việc đăng ký, tìm, tạo, nối và thường là quản lý scope/vòng đời của dependency trong object graph.** Container giúp composition root gọn và thống nhất khi ứng dụng phức tạp; nó không thay thế các quyết định về ranh giới nghiệp vụ, hợp đồng, danh tính đối tượng, giao dịch hay concurrency. Khi **constructor injection** và **DIP** đã rõ trong Java thuần, việc chuyển sang DI container chủ yếu là thay cách tổ chức wiring, còn mã nghiệp vụ vẫn có thể độc lập và kiểm thử trực tiếp.
