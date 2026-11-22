# Vòng phụ thuộc và cách phá vòng trong thiết kế OOP Java

> **Mục tiêu:** Nhận diện chu trình phụ thuộc (*circular dependency*) giữa các lớp, đối tượng, package, module hoặc bean; hiểu tác hại thực tế; và refactor thành luồng cộng tác một chiều mà vẫn giữ được hành vi nghiệp vụ.

## 1. Vòng phụ thuộc là gì?

Giả sử lớp `OrderService` cần `ShippingService` để giao hàng, nhưng `ShippingService` lại gọi ngược `OrderService` để cập nhật trạng thái đơn hàng.

~~~mermaid
flowchart LR
    O[OrderService] -->|cần để giao hàng| S[ShippingService]
    S -->|gọi để đổi trạng thái| O
~~~

Đây là **chu trình có hướng** trong đồ thị phụ thuộc: từ `OrderService` đi theo các cạnh phụ thuộc rồi quay lại chính nó. Khi một hệ thống có thêm lớp, chu trình có thể dài hơn: `A → B → C → A`.

Một số khái niệm cần tách biệt:

- **Phụ thuộc ở mức thiết kế:** `A` cần API, hành vi hay cấu trúc của `B` để thực hiện trách nhiệm của mình. Hai lớp hoặc hai module phụ thuộc ngược nhau làm việc sửa và kiểm thử khó phân tách.
- **Chu trình khởi tạo đối tượng:** muốn tạo `A` phải có `B`, nhưng muốn tạo `B` lại phải có `A`. Nếu cả hai yêu cầu qua constructor thì không tạo được cặp đối tượng hoàn chỉnh theo cách thông thường.
- **Chu trình gọi lúc chạy:** `A.method()` gọi `B.method()` và `B.method()` lại gọi `A.method()` không có điều kiện dừng. Vấn đề này có thể gây `StackOverflowError`, dù chương trình vẫn biên dịch và đối tượng đã được khởi tạo.
- **Vòng tham chiếu trong object graph:** đối tượng `Parent` chứa `Child` và `Child` giữ tham chiếu `parent` để điều hướng. Đây **không nhất thiết** là lỗi thiết kế hoặc lỗi bộ nhớ trong Java; tính hợp lý phụ thuộc mô hình, API và cách quản lý vòng đời.
- **Chu trình module/build:** module `orders` phụ thuộc `shipping`, trong khi `shipping` phụ thuộc `orders`. Công cụ build có thể từ chối chu trình project/module, trong khi hai lớp trong cùng compilation unit hoặc source set có thể tham chiếu lẫn nhau.

Vì thế câu hỏi chính không phải “có hai mũi tên ngược chiều không?”, mà là: **hai trách nhiệm có đang buộc phải biết chi tiết triển khai của nhau, gây khó khởi tạo, kiểm thử, thay thế hoặc phát triển không?**

## 2. Ví dụ thiết kế gây vòng

Mã sau biểu diễn hai service yêu cầu lẫn nhau qua constructor:

~~~java
final class OrderService {
    private final ShippingService shippingService;

    OrderService(ShippingService shippingService) {
        this.shippingService = shippingService;
    }

    void confirm(String orderId) {
        shippingService.schedule(orderId);
    }

    void markShipped(String orderId) {
        System.out.println("Order shipped: " + orderId);
    }
}

final class ShippingService {
    private final OrderService orderService;

    ShippingService(OrderService orderService) {
        this.orderService = orderService;
    }

    void schedule(String orderId) {
        // Giả lập thao tác giao hàng
        orderService.markShipped(orderId);
    }
}
~~~

Hai định nghĩa lớp có thể biên dịch khi cùng được biên dịch với nhau, nhưng việc lắp ghép đối tượng trở thành bài toán vòng tròn:

~~~java
// Không thể có đối tượng hoàn chỉnh để truyền vào ngay từ đầu.
// OrderService order = new OrderService(shipping);  // shipping chưa tồn tại
// ShippingService shipping = new ShippingService(order); // order chưa tồn tại
~~~

Truyền `null`, dùng setter để “vá” vòng, hoặc tạo một đối tượng bán khởi tạo làm giảm tính an toàn của thiết kế; đối tượng có thể bị gọi khi phụ thuộc chưa sẵn sàng. Nếu có DI container, container cũng phải đối mặt với chu trình khởi tạo.

**Nguyên nhân thiết kế:** `OrderService` vừa chịu trách nhiệm xác nhận đơn, vừa điều khiển vận chuyển; `ShippingService` vừa xử lý vận chuyển, vừa biết cách cập nhật nghiệp vụ đơn. Hai trách nhiệm bị kết dính qua lời gọi hai chiều.

## 3. Phá vòng bằng một lớp điều phối rõ trách nhiệm

Hướng refactor hợp lý là có một **use case coordinator** chịu trách nhiệm cho luồng “đặt đơn và yêu cầu giao hàng”, còn các thành phần bên dưới thực hiện từng nhiệm vụ độc lập.

~~~mermaid
flowchart TD
    C[CheckoutCoordinator] --> R[OrderRepository]
    C --> G[ShippingGateway]
    R --> D[(Order data)]
    G --> E[Hệ thống vận chuyển]
~~~

Trong thiết kế này, `OrderRepository` không gọi ngược `CheckoutCoordinator`, và `ShippingGateway` cũng không phụ thuộc ngược vào coordinator. Bản thân các thành phần cùng được dùng bởi coordinator không cần biết nhau.

**Ví dụ Java 17+ hoàn chỉnh, chạy độc lập trong một tệp `OrderFlowDemo.java`:**

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;

record Order(String id, long totalCents) {
    Order {
        Objects.requireNonNull(id, "id");
        if (id.isBlank() || totalCents <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
    }
}

interface OrderRepository {
    void save(Order order);
    Order findById(String id);
}

final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> data = new ConcurrentHashMap<>();

    @Override
    public void save(Order order) {
        data.put(order.id(), order);
    }

    @Override
    public Order findById(String id) {
        return data.get(id);
    }
}

interface ShippingGateway {
    void requestShipment(Order order);
}

final class ConsoleShippingGateway implements ShippingGateway {
    @Override
    public void requestShipment(Order order) {
        System.out.println("Request shipment for " + order.id());
    }
}

final class CheckoutCoordinator {
    private final OrderRepository orders;
    private final ShippingGateway shipping;

    CheckoutCoordinator(OrderRepository orders, ShippingGateway shipping) {
        this.orders = Objects.requireNonNull(orders, "orders");
        this.shipping = Objects.requireNonNull(shipping, "shipping");
    }

    void checkout(Order order) {
        Objects.requireNonNull(order, "order");
        orders.save(order);
        shipping.requestShipment(order);
    }
}

public class OrderFlowDemo {
    public static void main(String[] args) {
        OrderRepository repository = new InMemoryOrderRepository();
        ShippingGateway shipping = new ConsoleShippingGateway();
        CheckoutCoordinator checkout = new CheckoutCoordinator(repository, shipping);

        Order order = new Order("ORD-42", 250_000);
        checkout.checkout(order);

        System.out.println(repository.findById("ORD-42"));
    }
}
~~~

Chạy bằng `javac OrderFlowDemo.java` rồi `java OrderFlowDemo` với JDK 17 trở lên. Kết quả dự kiến:

~~~text
Request shipment for ORD-42
Order[id=ORD-42, totalCents=250000]
~~~

Mã này có những điểm quan trọng:

1. **Đồ thị phụ thuộc là một chiều:** `CheckoutCoordinator` biết hai cổng (`OrderRepository`, `ShippingGateway`); không cổng nào cần tham chiếu về coordinator.
2. **Constructor injection:** hai cộng tác viên được cung cấp ngay lúc xây dựng đối tượng, và `Objects.requireNonNull` bảo đảm chúng có mặt.
3. **Cổng là giao diện nhỏ:** repository quản lý lưu trữ, gateway quản lý yêu cầu vận chuyển. Triển khai thực tế có thể đổi mà không sửa luồng nghiệp vụ.
4. **Các trách nhiệm có biên rõ:** flow orchestration nằm ở coordinator, không dàn trải giữa hai service gọi ngược nhau.
5. **Không đánh tráo lỗi giao dịch:** đoạn trên chỉ minh họa cấu trúc phụ thuộc; nếu lưu đơn thành công mà gọi hệ thống giao hàng thất bại thì có thể để lại trạng thái chưa nhất quán. Trong hệ thống thật cần transaction phù hợp, retry/idempotency, hoặc *transactional outbox* khi giao tiếp giữa DB và hệ thống ngoài.

**Lưu ý:** Thêm interface **không tự phá vòng**. Nếu `OrderService → ShippingPort → ShippingService → OrderService`, chu trình vẫn tồn tại ở **đồ thị bean/triển khai**, dù một cạnh đã đi qua abstraction. Phải thay đổi hướng tương tác hoặc phân tách trách nhiệm thật sự.

## 4. Những cách phá vòng và khi nào áp dụng

| Cách xử lý | Ý tưởng | Phù hợp khi | Điều cần tránh |
|---|---|---|---|
| **Trích xuất trách nhiệm chung** | Di chuyển logic dùng chung sang `Policy`, `Calculator` hoặc domain service độc lập | Hai bên gọi nhau chỉ để dùng cùng một quy tắc | Tạo `Utils` khổng lồ, làm mất ranh giới miền nghiệp vụ |
| **Điều phối tại tầng trên** | Một coordinator/use case gọi các thành phần theo thứ tự | Hai service gọi ngược để hoàn thành một workflow | Coordinator ôm toàn bộ logic, biến thành “god object” |
| **Dependency Inversion** | Định nghĩa cổng nhỏ ở tầng phù hợp, tầng thấp triển khai cổng | Tầng nghiệp vụ phụ thuộc trực tiếp vào hạ tầng | Chỉ đổi tên hoặc chèn interface, để đồ thị runtime vẫn có vòng |
| **Domain event / message** | Bên phát thông báo sự kiện, bên xử lý đăng ký lắng nghe | Phản ứng sau thay đổi trạng thái, giảm gọi trực tiếp | Sự kiện đồng bộ vẫn có thể gây gọi lồng/đệ quy; bất đồng bộ cần idempotency/quan sát lỗi |
| **Tách module hợp đồng** | Đưa DTO/interface dùng chung sang module độc lập | Hai project/module import ngược nhau để lấy kiểu chung | Đưa toàn bộ nghiệp vụ vào “common” |
| **Gộp các lớp thật sự cùng trách nhiệm** | Một thành phần mới sở hữu cùng invariant và vòng đời | Ranh giới ban đầu bị chia tách nhân tạo | Gộp chỉ để qua kiểm tra build, tạo lớp quá lớn |
| **Xóa phụ thuộc không cần thiết** | Truyền dữ liệu tối thiểu như ID/value thay vì cả service | Chỉ gọi để lấy một vài trường hoặc trạng thái | Chuyển toàn bộ trạng thái qua DTO dư thừa gây coupling khác |

Chọn cách theo **nguồn gốc chu trình**. Nếu hai lớp chỉ dùng cùng một hàm tính phí, trích xuất tính phí thường gọn nhất. Nếu hai lớp điều phối tiến trình, đặt workflow vào coordinator. Nếu hai package import nhau do vài kiểu dữ liệu, tách contract module là ứng viên tốt. Không cần đưa event bus vào một luồng đồng bộ đơn giản chỉ để vẽ các mũi tên đẹp hơn.

## 5. Trích xuất phụ thuộc chung: từ A ↔ B thành A → C ← B

Giả sử `InvoiceService` cần `DiscountService` để tính tiền, nhưng `DiscountService` gọi ngược `InvoiceService` chỉ để biết mức trần chiết khấu. Cách thiết kế này khiến quy tắc “mức trần” bị đặt sai lớp.

**Trước:**

~~~mermaid
flowchart LR
    I[InvoiceService] --> D[DiscountService]
    D --> I
~~~

**Sau:** tách quy tắc giảm giá thành một policy độc lập.

~~~mermaid
flowchart TD
    I[InvoiceService] --> P[DiscountPolicy]
    D[DiscountService] --> P
~~~

Ví dụ các lớp Java (đặt trong một tệp hoặc các tệp tương ứng):

~~~java
final class DiscountPolicy {
    // Dùng long vì đơn vị là cents; không dùng double cho tiền.
    long apply(long originalCents, int percent) {
        if (originalCents < 0 || percent < 0 || percent > 30) {
            throw new IllegalArgumentException("Invalid discount");
        }
        long discount = Math.multiplyExact(originalCents, percent) / 100;
        return originalCents - discount;
    }
}

final class InvoiceService {
    private final DiscountPolicy policy;

    InvoiceService(DiscountPolicy policy) {
        this.policy = policy;
    }

    long amountAfterDiscount(long cents, int percent) {
        return policy.apply(cents, percent);
    }
}

final class DiscountService {
    private final DiscountPolicy policy;

    DiscountService(DiscountPolicy policy) {
        this.policy = policy;
    }

    long quote(long cents, int percent) {
        return policy.apply(cents, percent);
    }
}
~~~

`InvoiceService` và `DiscountService` đều biết `DiscountPolicy` nhưng không cần biết nhau. `Math.multiplyExact` báo lỗi nếu phép nhân số nguyên tràn phạm vi `long`; dùng `long` cho đơn vị cents cũng cần quy tắc làm tròn của nghiệp vụ, ví dụ này dùng phép chia nguyên.

Một đối tượng `DiscountPolicy` là thành phần độc lập, không duy trì trạng thái giữa hai lần gọi; việc chia sẻ một instance hay tạo riêng tùy vòng đời và cấu hình ứng dụng.

## 6. Dependency Inversion: điều gì thật sự đổi hướng?

Ở thiết kế phân tầng, domain thường không nên import hạ tầng trực tiếp.

**Thiết kế phụ thuộc vào triển khai:**

~~~mermaid
flowchart LR
    S[ApplicationService] --> J[JdbcOrderRepository]
~~~

**Thiết kế hướng vào contract do tầng nghiệp vụ sở hữu:**

~~~mermaid
flowchart LR
    S[ApplicationService] --> P[OrderRepository interface]
    J[JdbcOrderRepository] -. implements .-> P
~~~

Cổng `OrderRepository` được đặt trong module ứng dụng/domain thích hợp, adapter `JdbcOrderRepository` thực hiện nó. Package/module của adapter có thể phụ thuộc vào contract, còn application service không cần phụ thuộc trực tiếp vào adapter. Đây là **đảo chiều phụ thuộc mã nguồn**, dù tại runtime vẫn có object adapter thật được tiêm vào service.

Đừng chỉ kiểm tra import trong một file. Khi runtime wiring là:

~~~text
A -> PortB -> ImplementationB -> A
~~~

thì **vòng phụ thuộc đối tượng vẫn còn**. Hãy kiểm tra **đồ thị lớp** và **đồ thị thành phần được khởi tạo**; hai đồ thị không phải lúc nào cũng giống nhau.

## 7. Domain event có thể phá lời gọi trực tiếp, nhưng cần ranh giới rõ

Thay vì `OrderService` gọi `EmailService` rồi `EmailService` gọi ngược `OrderService` để tìm đơn, domain có thể phát `OrderPlaced(orderId, customerId)`. Một handler riêng đọc dữ liệu cần thiết và gửi email:

~~~mermaid
flowchart LR
    O[PlaceOrderUseCase] --> R[(OrderRepository)]
    O --> E[OrderPlaced event]
    E --> H[SendEmailHandler]
    H --> M[EmailGateway]
~~~

Chỉ dùng event khi “đơn đã được đặt” là một **sự kiện có ý nghĩa miền nghiệp vụ**. Nếu handler phải truy vấn dữ liệu mới, ranh giới contract nên ổn định (ID hoặc snapshot tối thiểu), tránh đưa nguyên entity có trạng thái ORM/lazy-loading sang message.

Phân biệt ba trường hợp:

- **Event đồng bộ trong cùng process:** giảm phụ thuộc trực tiếp nhưng handler vẫn chạy trên call stack của bên phát. Nếu handler lại kích hoạt event ban đầu, có thể tạo vòng gọi vô hạn.
- **Event bất đồng bộ:** người phát không chờ handler chạy trong cùng stack, nhưng xuất hiện bài toán giao hàng ít nhất một lần, retry, trùng thông điệp, sắp xếp thứ tự và xử lý nhất quán cuối cùng.
- **Transactional outbox:** ghi thay đổi dữ liệu và bản ghi outbox trong cùng transaction DB, một worker chuyển outbox thành message. Cần xử lý publish trùng và idempotency ở consumer; outbox không tự đảm bảo exactly-once end-to-end.

Nếu việc gửi email không ảnh hưởng tới khả năng tạo đơn, event là lựa chọn có thể hợp lý. Nếu quy tắc yêu cầu kiểm tra tồn kho **trước** khi xác nhận đơn, một lời gọi đồng bộ có contract rõ có thể dễ kiểm soát hơn.

## 8. Chu trình bean trong Spring và cách xử lý

Ví dụ sau minh họa vòng phụ thuộc qua **constructor injection**:

~~~java
import org.springframework.stereotype.Service;

@Service
class OrderApplicationService {
    OrderApplicationService(ShippingApplicationService shipping) {
    }
}

@Service
class ShippingApplicationService {
    ShippingApplicationService(OrderApplicationService orders) {
    }
}
~~~

Khi context cần tạo cả hai singleton bean, không bean nào có thể được tạo đầy đủ trước để cấp cho bean kia. Spring thường báo lỗi khởi tạo liên quan đến vòng phụ thuộc, chẳng hạn `BeanCurrentlyInCreationException` hoặc phân tích cycle tùy phiên bản và cách wiring.

**Cách sửa theo thiết kế:** tái cấu trúc thành `CheckoutCoordinator` với các cổng độc lập như ở mục 3. Spring nhận các implementation qua constructor; sơ đồ runtime còn một chiều. Nếu dùng annotation Spring, các class coordinator/adapter có thể được đánh dấu `@Service`/`@Repository` hoặc cấu hình qua `@Bean`; kiến trúc phải đúng trước, sau đó mới wiring.

Các cách né lỗi có giới hạn:

- `@Lazy` trên một cạnh có thể hoãn việc lấy bean, nhưng **không biến** vòng logic thành đồ thị lành mạnh. Nếu thao tác thực tế cứ gọi ngược nhau, vấn đề vẫn còn.
- `ObjectProvider<T>` hoặc `Provider<T>` cho phép lấy phụ thuộc muộn, hữu ích khi cần scope/lifecycle động, nhưng không phải giải pháp mặc định cho vòng kiến trúc.
- Setter/field injection có thể làm một số vòng singleton khởi tạo được ở cấu hình thích hợp, nhưng đối tượng dễ ở trạng thái chưa đủ phụ thuộc; vòng gọi phương thức vẫn tồn tại.
- Cấu hình cho phép circular references (nếu phiên bản framework hỗ trợ) là **biện pháp tương thích tạm thời**, không thay cho xử lý trách nhiệm.

**Một lỗi khác:** `@Transactional`, `@Async`, proxy AOP và các callback khởi tạo có thể làm thời điểm truy cập bean khác dự tính. Khi refactor, kiểm tra boundary giao dịch, lời gọi qua proxy, exception, rollback và việc phát event; tránh đổi kiến trúc rồi vô tình đổi semantics của transaction.

## 9. Phụ thuộc vòng ở package và module

Giả sử project Java có cấu trúc:

~~~text
orders/
    OrderService.java      -> import shipping.ShippingService
shipping/
    ShippingService.java   -> import orders.OrderService
~~~

Hai package trong cùng module vẫn có thể biên dịch, nhưng cấu trúc dễ tạo chu trình kiến trúc. Với project/module riêng biệt, nếu `orders` phụ thuộc `shipping` và `shipping` phụ thuộc `orders`, hệ thống build có thể không sắp xếp thứ tự build hợp lệ. Với Java Platform Module System (JPMS), đồ thị `requires` giữa named modules không được tạo chu trình.

Một cách tổ chức:

~~~text
order-contract/
    OrderId.java
    ShippingRequest.java
orders/
    OrderService.java      -> order-contract
shipping/
    ShippingAdapter.java   -> order-contract
application/
    CheckoutCoordinator.java -> orders, shipping, order-contract
~~~

`order-contract` chỉ chứa những contract thực sự dùng chung và ổn định; không nên trở thành “sọt rác” chứa mọi model và utility. Hướng phụ thuộc từ application vào cả hai adapter có thể phù hợp ở **composition root** nếu dự án khởi tạo các thành phần ở đó, nhưng code nghiệp vụ application nên ưu tiên interface và không import adapter cụ thể.

Đối với module hệ thống, hãy kiểm tra **cạnh build-time** (project dependency), **cạnh compile-time** (import/type reference), và **cạnh runtime** (bean/provider wiring). Phá được một vòng trong import chưa bảo đảm vòng runtime biến mất.

## 10. Cách chẩn đoán và refactor có kiểm soát

Một quy trình thực tế:

1. **Vẽ các cạnh thật:** ghi rõ lớp/module nào phụ thuộc lớp/module nào, dùng làm gì, và qua constructor, field, static call hay callback. Đừng suy luận quan hệ từ tên.
2. **Xác định mức độ:** vòng nằm ở import/project module, bean constructor, lời gọi runtime hay object graph thông thường? Vòng ở một mức không nhất thiết tồn tại ở mức khác.
3. **Lần theo nhu cầu mỗi cạnh:** bên gọi cần toàn bộ service, hay chỉ một giá trị, quy tắc, hoặc thông báo sự kiện? Từ đó xác định trách nhiệm đặt sai.
4. **Chọn điểm cắt có ý nghĩa:** bỏ lời gọi không cần thiết, trích xuất policy, đưa điều phối lên use case, dùng port đúng tầng, hoặc đưa contract dùng chung vào module độc lập.
5. **Di chuyển từng caller:** cập nhật constructor, phương thức và dependency injection configuration. Tránh giữ alias cũ vô thời hạn nếu nó kéo lại đường phụ thuộc vòng.
6. **Kiểm thử hành vi:** giữ thứ tự thao tác quan trọng, kết quả, exception, transaction và trạng thái. Với API công khai, kiểm tra ảnh hưởng tương thích nhị phân/nguồn.
7. **Kiểm tra đồ thị lại:** cả kiến trúc tĩnh và runtime wiring; thử khởi động ứng dụng từ một context sạch.
8. **Theo dõi giới hạn hoạt động:** nếu chuyển sang event, quan sát retry/duplicate và trạng thái chưa đồng bộ; nếu dùng coordinator, tránh cho nó trở thành lớp xử lý mọi việc.

Ví dụ các lệnh hỗ trợ kiểm tra (tùy build tool):

~~~bash
# Maven: xem quan hệ dependency giữa các artifact
mvn dependency:tree

# Gradle: xem project dependencies ở cấu hình phù hợp
./gradlew dependencies

# JDK: phân tích phụ thuộc class/package của mã đã biên dịch
jdeps -verbose:class -filter:none -cp target/classes target/classes
~~~

Đọc kết quả theo phạm vi: `mvn dependency:tree` và `gradlew dependencies` cho biết quan hệ artifact/project, **không đủ** để tìm vòng gọi giữa mọi class. `jdeps` giúp phân tích phụ thuộc tĩnh bytecode, nhưng không thấy đầy đủ reflection, callback động hay runtime bean wiring. Với Gradle Windows, có thể dùng `gradlew.bat dependencies`; đường dẫn `target/classes` là ví dụ thường gặp ở Maven và cần điều chỉnh theo dự án. Các kiến trúc phức tạp có thể dùng quy tắc kiểm soát dependency giữa package/module trong test kiến trúc.

## 11. Đảm bảo test phát hiện lỗi chứ không chỉ “tạo được bean”

Từ ví dụ `CheckoutCoordinator`, ta có thể kiểm tra **thứ tự** “save trước rồi request shipment”, dữ liệu được truyền đúng và phụ thuộc không gọi ngược coordinator. Dưới đây là test JUnit Jupiter 5 dùng fake, không cần framework mocking:

**`CheckoutCoordinatorTest.java`** (đặt cạnh các class từ `OrderFlowDemo.java` trong cùng package):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import java.util.List;

class CheckoutCoordinatorTest {
    @Test
    void savesThenRequestsShipment() {
        List<String> calls = new ArrayList<>();

        OrderRepository repository = new OrderRepository() {
            @Override
            public void save(Order order) {
                calls.add("save:" + order.id());
            }

            @Override
            public Order findById(String id) {
                return null;
            }
        };

        ShippingGateway gateway = order ->
                calls.add("ship:" + order.id());

        CheckoutCoordinator checkout =
                new CheckoutCoordinator(repository, gateway);

        checkout.checkout(new Order("ORD-42", 250_000));

        assertEquals(List.of("save:ORD-42", "ship:ORD-42"), calls);
    }

    @Test
    void missingDependenciesAreRejectedAtConstruction() {
        OrderRepository repository = new InMemoryOrderRepository();
        ShippingGateway shipping = new ConsoleShippingGateway();

        assertThrows(NullPointerException.class,
                () -> new CheckoutCoordinator(null, shipping));
        assertThrows(NullPointerException.class,
                () -> new CheckoutCoordinator(repository, null));
    }
}
~~~

Đây là test về contract và tương tác cần giữ. Một test chỉ dùng reflection để xác nhận lớp có trường `private final ShippingGateway` hoặc chỉ kiểm tra source không chứa chuỗi `extends` là quá lệ thuộc triển khai. Đối với ứng dụng Spring, bổ sung **integration test khởi tạo application context** nhằm phát hiện vòng bean; nếu kết nối DB/messaging, kiểm tra transaction và retry theo môi trường test riêng.

**Điểm cần cẩn trọng về lỗi giao hàng:** test trên đảm bảo thứ tự phương thức, không chứng minh tính nguyên tử của cập nhật DB và tác vụ hệ thống ngoài. Một bài test tích hợp cần kiểm tra kịch bản gọi gateway thất bại, liệu đơn được giữ ở trạng thái nào và luồng phục hồi ra sao.

## 12. Những hiểu lầm thường gặp

| Nhận định | Đánh giá chính xác |
|---|---|
| “Mọi đối tượng tham chiếu vòng đều sai” | Không. Quan hệ cha–con hai chiều có thể hữu ích; Java GC có thể thu hồi cả nhóm không còn reachable từ GC roots |
| “Chèn interface là đã phá vòng” | Chỉ đúng nếu **đồ thị phụ thuộc thực sự** đổi hướng, không còn đường quay về |
| “`@Lazy` xử lý triệt để circular dependency” | Thường chỉ hoãn khởi tạo; không sửa trách nhiệm hoặc vòng gọi runtime |
| “Event bus luôn giải quyết mọi vòng” | Có thể chuyển coupling sang schema/event và tạo vòng phản ứng; thêm độ phức tạp lỗi/nhất quán |
| “Lỗi Spring context là bằng chứng duy nhất có vòng” | Compiler, tests, runtime recursion, kiến trúc package/module cũng cần được kiểm tra |
| “Hai chiều sẽ gây memory leak trong Java” | Reference cycles tự chúng không ngăn GC thu hồi; leak xảy ra nếu còn đường tham chiếu từ các GC roots |
| “Coordinator càng nhiều dependency càng tốt” | Coordinator nên điều phối use case; quy tắc nghiệp vụ có trách nhiệm riêng cần đặt ở thành phần phù hợp |

## 13. Bài tập áp dụng: refactor notification cho đăng ký khóa học

**Thiết kế ban đầu:** `EnrollmentService` gọi `NotificationService` sau khi ghi danh, nhưng `NotificationService` gọi lại `EnrollmentService` để lấy email và tên khóa học. Hai service được constructor-inject lẫn nhau.

Hãy viết lại theo một trong hai phương án:

- **Đồng bộ:** `EnrollStudentUseCase` lấy thông tin bằng `EnrollmentRepository`/`StudentDirectory`, lưu ghi danh, rồi gọi `NotificationGateway.sendConfirmation(recipient, courseName)`. Gateway không gọi lại use case.
- **Bất đồng bộ:** Sau khi ghi danh thành công, phát `StudentEnrolled(enrollmentId)` và xử lý thông báo qua handler độc lập. Nếu có DB + message broker, hãy mô tả cách outbox/retry/idempotency bảo vệ luồng.

Tiêu chí tự kiểm tra: Có thể vẽ đồ thị dependency **không còn đường quay lại** use case không? Có thể constructor-inject mọi thành phần từ một composition root không? Dữ liệu có đủ ở ranh giới gọi hay event không? Khi gửi thông báo thất bại, trạng thái ghi danh có được xác định rõ không?

---

**Ghi nhớ:** Để phá vòng phụ thuộc, hãy tìm **trách nhiệm đang đi sai chiều**, đặt nó vào đúng thành phần hoặc lớp điều phối, rồi xác minh lại cả **đồ thị phụ thuộc** lẫn **hành vi thực tế**. Việc làm chương trình khởi tạo được là cần thiết, nhưng thiết kế còn phải dễ hiểu, kiểm thử được và đủ an toàn trước lỗi vận hành.