# Phát hiện phụ thuộc vòng, truy cập tắt ngoài quy định và rò rỉ mô hình lưu trữ

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED** — **Học tổ chức phần mềm theo kiến trúc phân tầng**, trong chương **Sai lầm và đánh giá thiết kế**. Khi review một hệ thống phân tầng, ba dấu hiệu cần chú ý là phụ thuộc vòng giữa package hoặc module, đường truy cập tắt qua ranh giới đã quy định, và mô hình lưu trữ bị lộ sang các layer khác. Chúng thường xuất hiện cùng nhau: một module truy cập trực tiếp repository của module khác, rồi dùng luôn JPA entity làm dữ liệu trao đổi, khiến các ranh giới khó thay đổi và khó kiểm thử.

Mục tiêu của review không phải là cấm mọi quan hệ giữa các thành phần. Mục tiêu là xác định ai sở hữu trách nhiệm, ai được phép phụ thuộc vào hợp đồng nào và dữ liệu nào được phép đi qua từng ranh giới. Một thiết kế có thể có nhiều layer hoặc module khác nhau tùy quy mô; điều quan trọng là quy tắc phụ thuộc nhất quán, dễ giải thích và có thể kiểm tra.

## 1. Nhận diện phụ thuộc vòng

**Phụ thuộc mã nguồn** xuất hiện khi một package, module hoặc lớp cần biết kiểu/API của thành phần khác để biên dịch. Nếu A phụ thuộc B, ký hiệu A → B. Một chuỗi A → B → C → A tạo thành một chu trình: không có điểm bắt đầu độc lập khi xét toàn bộ nhóm thành phần đó.

Ví dụ, module đơn hàng cần kiểm tra tồn kho trước khi xác nhận; module kho lại import lớp đơn hàng để cập nhật trạng thái:

~~~text
orders.application  ───────> inventory.application
       ^                             |
       |                             |
       └─────────────────────────────┘
~~~

Hoặc ở mức package:

~~~java
// orders/application/OrderService.java
import com.example.shop.inventory.InventoryService;

public class OrderService {
    private final InventoryService inventory;
    // ...
}
~~~

~~~java
// inventory/application/InventoryService.java
import com.example.shop.orders.Order;

public class InventoryService {
    public void reserve(Order order) {
        // đọc dữ liệu đơn hàng để giữ hàng
    }
}
~~~

Trong ví dụ này, application của orders cần InventoryService, còn inventory cần kiểu Order do orders sở hữu. Hai module vì thế bị buộc phải biết cấu trúc nội bộ của nhau. Một thay đổi trong Order có thể buộc module inventory biên dịch lại hoặc sửa theo; thay đổi trong inventory cũng có thể tác động đến OrderService.

### Phân biệt chu trình mã nguồn và chu trình lời gọi

Không phải mọi chu trình lời gọi khi chạy đều là dependency cycle ở mức mã nguồn:

- **Chu trình mã nguồn:** package hoặc module A tham chiếu B, đồng thời B tham chiếu A. Nó làm ranh giới build và thay đổi bị đan xen.
- **Chu trình lời gọi:** trong một luồng runtime, A gọi B rồi B gọi lại A. Nó có thể gây đệ quy không chủ đích, khó theo dõi hoặc vòng lặp xử lý.
- **Chu trình dữ liệu:** các bản ghi hoặc event tham chiếu lẫn nhau, hoặc hai tiến trình chờ dữ liệu của nhau. Cần phân tích riêng theo ngữ nghĩa dữ liệu và quy trình.

Một callback có thể tạo lời gọi quay lại component ban đầu mà không tạo dependency mã nguồn vòng, nếu callback được biểu diễn qua interface do bên gọi sở hữu. Ngược lại, hai package có thể phụ thuộc vòng dù một request cụ thể không đi qua cả hai chiều. Khi review, hãy xác định rõ đang kiểm tra loại đồ thị nào.

### Vì sao phụ thuộc vòng gây khó khăn?

- **Thay đổi lan truyền:** chỉnh một kiểu hoặc hợp đồng ở module này có thể kéo theo module kia.
- **Khó kiểm thử độc lập:** khi khởi tạo một module thường phải dựng cả module còn lại hoặc mock nhiều lớp.
- **Khó tái sử dụng:** không thể dễ dàng sử dụng một module ở ứng dụng khác vì nó kéo theo phần còn lại của chu trình.
- **Build và phân phối phức tạp:** module build có thể không biên dịch độc lập; trong một số hệ thống build, dependency cycle bị từ chối ngay.
- **Trách nhiệm không rõ:** hai module cùng có vẻ sở hữu một phần quy tắc hoặc dữ liệu, khiến nhóm khó quyết định nơi sửa.

Không phải mọi quan hệ hai chiều ở mức nghiệp vụ đều sai. Hai khái niệm có thể liên hệ qua lại trong domain. Điều cần tránh là để mã nguồn của các module phụ thuộc trực tiếp vào nhau đến mức không thể xác định ranh giới và quyền sở hữu.

## 2. Cách tìm dependency cycle

Hãy bắt đầu từ cấu trúc thực tế, không chỉ từ tên package:

1. Xác định package hoặc module nào đang được review và quy tắc phụ thuộc dự kiến.
2. Lần theo import, field, constructor parameter, method signature, extends/implements và cấu hình build.
3. Vẽ mũi tên từ bên sử dụng sang kiểu hoặc module được sử dụng.
4. Tìm đường đi quay về thành phần ban đầu; ghi lại chu trình ngắn nhất cùng các lớp tạo ra nó.
5. Kiểm tra xem quan hệ đó có thực sự cần thiết hay chỉ xuất hiện vì một module đang truy cập dữ liệu hoặc implementation của module khác.

Ví dụ dependency graph:

~~~mermaid
flowchart LR
    O[Orders] --> I[Inventory]
    I --> O
    P[Payments] --> O
~~~

Ở đây, Orders và Inventory tạo thành một strongly connected component (thành phần liên thông mạnh): mỗi bên có đường phụ thuộc đến bên còn lại. Payments chỉ phụ thuộc Orders nên chưa tạo chu trình trong phần graph này.

Có thể dùng công cụ phân tích dependency hoặc test kiến trúc để phát hiện chu trình. Với ArchUnit, ví dụ kiểm tra các slice theo package:

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class ModuleDependencyTest {
    @ArchTest
    static final ArchRule modulesShouldBeFreeOfCycles =
            slices()
                    .matching("com.example.shop.(*)..")
                    .should()
                    .beFreeOfCycles();
}
~~~

Quy tắc này yêu cầu các slice được nhận diện theo mẫu package không phụ thuộc vòng. Cần điều chỉnh mẫu package để nó khớp cấu trúc thật của ứng dụng; nếu mẫu gom các lớp không cùng một ranh giới, kết quả có thể không phản ánh kiến trúc mong muốn. Test kiến trúc phát hiện quan hệ mã nguồn theo cấu hình của nó, không chứng minh luồng runtime hoặc quy trình nghiệp vụ đúng.

## 3. Cách tháo gỡ phụ thuộc vòng

Không nên giải quyết chu trình bằng cách chuyển import sang một package chung tùy tiện hoặc thêm interface cho mọi lớp. Trước hết hãy xác định **quyền sở hữu khái niệm**: dữ liệu và quy tắc nào thuộc module nào; module kia thực sự cần khả năng gì?

### Đảo chiều phụ thuộc bằng hợp đồng

Nếu Orders cần khả năng giữ hàng, nó có thể định nghĩa một port theo nhu cầu của use case:

~~~java
// orders/application/InventoryReservation.java
public interface InventoryReservation {
    ReservationResult reserve(
            OrderId orderId,
            List<RequestedItem> items);
}
~~~

Application service chỉ phụ thuộc vào hợp đồng:

~~~java
public class PlaceOrderService {
    private final InventoryReservation inventory;

    public PlaceOrderService(InventoryReservation inventory) {
        this.inventory = inventory;
    }

    public PlaceOrderResult place(PlaceOrderCommand command) {
        Order order = Order.place(command);
        ReservationResult reservation =
                inventory.reserve(order.id(), order.requestedItems());

        if (!reservation.accepted()) {
            return PlaceOrderResult.rejected(reservation.reason());
        }

        // Lưu đơn và trả kết quả theo chính sách của use case.
        return PlaceOrderResult.accepted(order.id());
    }
}
~~~

Module inventory cung cấp adapter triển khai port mà không cần import lớp Order:

~~~java
public class InventoryReservationAdapter
        implements InventoryReservation {
    private final StockReservationService stock;

    public InventoryReservationAdapter(StockReservationService stock) {
        this.stock = stock;
    }

    @Override
    public ReservationResult reserve(
            OrderId orderId,
            List<RequestedItem> items) {
        return stock.reserve(
                new ReservationRequest(orderId.value(), items));
    }
}
~~~

Khi đó, chiều phụ thuộc mã nguồn là:

~~~mermaid
flowchart LR
    O[Orders application] --> P[InventoryReservation port]
    I[Inventory adapter] --> P
    I --> S[Inventory domain/service]
~~~

Orders sở hữu hợp đồng vì nó mô tả khả năng use case cần. Inventory adapter biết hợp đồng để triển khai nó. Không cần để module inventory import Order aggregate. Trong một modular monolith, composition root có thể nối adapter vào port bằng dependency injection; nếu module được tách thành service, adapter có thể trở thành HTTP hoặc message client.

### Dùng event khi hai module cần thông báo sự kiện

Nếu một module chỉ cần biết điều gì đã xảy ra, event có thể phù hợp hơn lời gọi trực tiếp. Ví dụ, Orders phát OrderPlaced; Inventory nhận event và tạo reservation. Inventory sau đó phát InventoryReserved hoặc InventoryReservationRejected. Mỗi module sở hữu dữ liệu của mình và trao đổi qua hợp đồng event.

Event giúp giảm phụ thuộc trực tiếp nhưng không xóa mọi coupling: schema event vẫn là hợp đồng cần quản lý, consumer phải xử lý duplicate và thứ tự, và quy trình bất đồng bộ cần trạng thái để theo dõi. Không nên chuyển mọi lời gọi đồng bộ thành event nếu caller cần kết quả ngay để tiếp tục quyết định.

### Tách khái niệm dùng chung khi thực sự có quyền sở hữu chung

Đôi khi cả hai module đang phụ thuộc vào một khái niệm ổn định mà không module nào nên sở hữu độc quyền. Có thể tách hợp đồng hoặc value object nhỏ thành module API/shared kernel. Tuy nhiên, module chung phải có phạm vi rõ, được quản lý phiên bản và không trở thành nơi gom mọi lớp tiện ích. Nếu module chung phụ thuộc ngược vào các module sử dụng nó, chu trình chỉ bị chuyển vị trí.

### Xem lại ranh giới module

Nếu hai phần luôn thay đổi cùng nhau, chia chúng thành hai module độc lập có thể không phản ánh đúng miền nghiệp vụ. Khi đó, hợp nhất chúng dưới một module lớn hơn với API nội bộ rõ có thể hợp lý hơn. Mục tiêu là ranh giới phản ánh quyền sở hữu và lý do thay đổi, không phải tối đa hóa số module.

## 4. Nhận diện truy cập tắt ngoài quy định

Truy cập tắt (layer bypass) xảy ra khi một thành phần bỏ qua API hoặc layer chịu trách nhiệm và gọi thẳng vào implementation ở phía sau. Đường đi có thể vẫn chạy đúng trong một trường hợp, nhưng nó làm mất nơi tập trung để kiểm tra quyền, áp dụng quy tắc, quản lý transaction hoặc ghi nhận tác động.

Ví dụ controller gọi repository trực tiếp:

~~~java
@RestController
public class OrderController {
    private final OrderRepository orders;

    public OrderController(OrderRepository orders) {
        this.orders = orders;
    }

    @PostMapping("/orders/{id}/cancel")
    public void cancel(@PathVariable String id) {
        Order order = orders.findById(new OrderId(id)).orElseThrow();
        order.cancel();
        orders.save(order);
    }
}
~~~

Controller đang tự tải aggregate, quyết định hành vi và lưu dữ liệu. Nếu quy tắc hủy đơn yêu cầu kiểm tra quyền, trạng thái giao hàng, hoàn tiền hoặc phát event, các bước có thể bị bỏ qua hoặc bị sao chép ở endpoint khác.

Đường đi phù hợp hơn là controller gọi application use case:

~~~java
@RestController
public class OrderController {
    private final CancelOrderUseCase cancelOrder;

    public OrderController(CancelOrderUseCase cancelOrder) {
        this.cancelOrder = cancelOrder;
    }

    @PostMapping("/orders/{id}/cancel")
    public void cancel(@PathVariable String id) {
        cancelOrder.handle(new CancelOrderCommand(id));
    }
}
~~~

Application service điều phối repository và domain:

~~~java
public class CancelOrderService implements CancelOrderUseCase {
    private final OrderRepository orders;

    public CancelOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    public void handle(CancelOrderCommand command) {
        Order order = orders.getRequired(new OrderId(command.orderId()));
        order.cancel();
        orders.save(order);
    }
}
~~~

Phương thức order.cancel() bảo vệ bất biến domain. Application service xác định ranh giới use case và phối hợp lưu thay đổi. Với workflow có hoàn tiền hoặc giải phóng hàng, service còn điều phối các port tương ứng hoặc khởi tạo quy trình saga theo chính sách.

### Các dấu hiệu bypass thường gặp

| Dấu hiệu | Rủi ro |
|---|---|
| Controller gọi repository/DAO | Bỏ qua use case, kiểm tra quyền hoặc workflow |
| Domain gọi trực tiếp JPA repository hoặc HTTP client | Trộn quy tắc nghiệp vụ với I/O và framework |
| Module A truy cập repository hoặc bảng của module B | Bỏ qua API và quyền sở hữu dữ liệu của B |
| Application gọi implementation cụ thể ở infrastructure | Khó thay adapter, kiểm thử và giữ chiều phụ thuộc |
| Job nền tự sửa entity hoặc SQL mà không qua hành vi nghiệp vụ | Có thể bỏ qua bất biến mà request bình thường vẫn áp dụng |
| Mapper hoặc serializer tự tải quan hệ lazy | Truy vấn ẩn, hiệu năng khó dự đoán và lộ dữ liệu ngoài ý muốn |

Không phải mọi lời gọi bỏ qua một lớp trung gian đều là sai. Một thao tác truy vấn đơn giản có thể được thiết kế để dùng query service hoặc read model riêng. Cần đối chiếu với quy tắc kiến trúc đã chọn và xác định trách nhiệm nào đang bị bỏ qua. Một bypass được cho phép nên có lý do, phạm vi và cách kiểm thử rõ ràng.

## 5. Rò rỉ mô hình lưu trữ

**Mô hình lưu trữ (persistence model)** là các kiểu và cấu trúc phục vụ việc ghi/đọc dữ liệu, ví dụ JPA entity, document MongoDB, row mapper hoặc schema của database. Rò rỉ xảy ra khi những kiểu này đi qua ranh giới mà không thuộc trách nhiệm của layer nhận chúng.

Ví dụ controller trả trực tiếp JPA entity:

~~~java
@GetMapping("/orders/{id}")
public OrderEntity get(@PathVariable Long id) {
    return jpaOrderRepository.findById(id).orElseThrow();
}
~~~

Cách làm này gắn HTTP contract với cấu trúc database. Khi đổi tên cột, quan hệ entity hoặc chiến lược fetch, response API có thể thay đổi ngoài ý muốn. Entity còn có thể chứa trường nội bộ, quan hệ lazy, proxy Hibernate hoặc tham chiếu hai chiều khiến serialization lỗi, phát sinh truy vấn ẩn hay lộ dữ liệu không nên công khai.

Một ví dụ khác là domain aggregate dùng annotation JPA và kế thừa base class của persistence. Cách này có thể là lựa chọn có chủ đích trong một số mô hình đơn giản, nhưng nó khiến domain phụ thuộc framework lưu trữ và có thể làm việc thay đổi persistence khó hơn. Hãy cân nhắc mức coupling chấp nhận được thay vì mặc định mọi entity đều phải tách hoặc mặc định mọi entity phải là JPA entity.

### Phân biệt các loại model

| Model | Mục đích | Ví dụ |
|---|---|---|
| Request/response DTO | Hợp đồng giao tiếp với client | CreateOrderRequest, OrderResponse |
| Command/query model | Đầu vào và kết quả của use case | PlaceOrderCommand, OrderSummary |
| Domain model | Hành vi, trạng thái và bất biến nghiệp vụ | Order, OrderLine, Money |
| Persistence model | Ánh xạ dữ liệu vào database hoặc document store | OrderEntity, OrderRow |
| Event model | Thông tin được công bố giữa các thành phần | OrderPlaced |

Các model có thể chia sẻ một số giá trị đơn giản, nhưng không nên mặc định chúng là cùng một lớp. Chúng có lý do thay đổi khác nhau: API thay đổi theo client contract; domain thay đổi theo quy tắc nghiệp vụ; persistence thay đổi theo schema và chiến lược lưu trữ.

### Chuyển đổi tại ranh giới

Một adapter persistence có thể chuyển JPA entity thành domain object và ngược lại:

~~~java
@Repository
public class JpaOrderRepository implements OrderRepository {
    private final SpringDataOrderJpaRepository jpa;

    @Override
    public Optional<Order> findById(OrderId id) {
        return jpa.findById(id.value())
                .map(OrderEntity::toDomain);
    }

    @Override
    public void save(Order order) {
        jpa.save(OrderEntity.fromDomain(order));
    }
}
~~~

Controller dùng mapper hoặc factory để chuyển kết quả use case thành response:

~~~java
public record OrderResponse(
        String id,
        String status,
        BigDecimal total
) {
    public static OrderResponse from(OrderDetails details) {
        return new OrderResponse(
                details.id(),
                details.status().name(),
                details.total().amount());
    }
}
~~~

Mapper là nơi chuyển đổi cấu trúc, không phải nơi thực hiện quy tắc nghiệp vụ. Nếu cần tính tổng tiền hoặc quyết định đơn có thể hủy không, hãy gọi hành vi domain hoặc use case tương ứng thay vì đặt logic đó trong mapper.

Với truy vấn đọc cần dữ liệu tổng hợp, có thể dùng projection/read model riêng thay vì tải toàn bộ aggregate. Điều đó không phải rò rỉ persistence nếu kiểu được trả về là hợp đồng đọc có chủ đích, không phụ thuộc entity hoặc proxy của ORM. Hãy giữ ranh giới giữa kiểu đọc nội bộ và API response nếu chúng có vòng đời khác nhau.

## 6. Cách review ba vấn đề một cách có hệ thống

Khi review một module hoặc một luồng use case, có thể thực hiện theo thứ tự:

1. **Xác định ranh giới:** liệt kê layer, module, API công khai và dữ liệu do từng module sở hữu.
2. **Kiểm tra dependency graph:** tìm chu trình package/module; xem import và kiểu tham chiếu có vượt qua ranh giới không.
3. **Lần theo runtime call:** bắt đầu từ controller, listener hoặc job; xác định nơi workflow và quy tắc được thực thi.
4. **Lần theo data flow:** xem request, command, domain object, entity, event và response được tạo hoặc chuyển đổi ở đâu.
5. **Đối chiếu quy tắc:** xác định đường gọi nào bypass application/domain policy và kiểu persistence nào bị lộ ra ngoài.
6. **Đề xuất sửa theo nguyên nhân:** chuyển quyền sở hữu hợp đồng, tạo port, dùng event, điều chỉnh module boundary hoặc thêm mapper ở đúng adapter.
7. **Thêm kiểm tra tự động:** test kiến trúc cho dependency, unit test cho use case và integration test cho mapping/persistence.

Không nên chỉ dựa vào sơ đồ package. Một module có thể không có import trực tiếp nhưng vẫn truy cập dữ liệu module khác qua shared database hoặc SQL native. Vì thế, review cần xem cả code truy cập dữ liệu, cấu hình repository, migration và hợp đồng trao đổi.

## 7. Tự động hóa quy tắc kiến trúc

ArchUnit có thể kiểm tra một số quy tắc package. Ví dụ:

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class LayerRulesTest {
    @ArchTest
    static final ArchRule domainShouldNotDependOnInfrastructure =
            noClasses()
                    .that().resideInAPackage("..domain..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..infrastructure..");

    @ArchTest
    static final ArchRule controllersShouldNotUseRepositories =
            noClasses()
                    .that().resideInAPackage("..presentation..")
                    .should().dependOnClassesThat()
                    .resideInAPackage("..infrastructure.persistence..");
}
~~~

Các quy tắc trên là ví dụ. Nếu repository port được đặt trong application, controller có thể được phép phụ thuộc vào use case nhưng không được phụ thuộc vào adapter persistence. Nếu dự án có query path riêng, hãy mô hình hóa nó thành API đọc được phép và kiểm tra theo API đó thay vì cấm một cách tuyệt đối.

Ngoài ArchUnit, có thể dùng module system của Java, cấu hình module build hoặc quy tắc visibility để ngăn truy cập implementation. Với modular monolith, một module test có thể xác minh chỉ public API được phép sử dụng từ module khác. Các kiểm tra này biến quyết định kiến trúc thành quy tắc có thể chạy trong CI.

## 8. Những cách sửa dễ tạo vấn đề mới

- **Chuyển mọi thứ vào package common:** có thể che giấu dependency cycle trong một module chung lớn và làm mờ quyền sở hữu.
- **Tạo interface cho mọi class:** tăng số lượng abstraction mà không tạo hợp đồng có ý nghĩa; chu trình có thể vẫn tồn tại qua các interface.
- **Dùng event cho mọi lời gọi:** thêm eventual consistency và độ phức tạp vận hành ngay cả khi một lời gọi đồng bộ đơn giản là đủ.
- **Chỉ đổi tên package:** tên mới không thay đổi quan hệ dependency nếu import và quyền sở hữu vẫn như cũ.
- **Map entity sang DTO nhưng vẫn để controller truy cập repository:** rò rỉ persistence có thể giảm, nhưng bypass application vẫn còn.
- **Cấm tất cả quan hệ hai chiều:** có thể làm mô hình domain khó hiểu hoặc tạo abstraction nhân tạo. Hãy kiểm soát dependency mã nguồn và trách nhiệm thay vì áp một quy tắc máy móc.

## 9. Checklist review

Trước khi chấp nhận một thay đổi kiến trúc, hãy kiểm tra:

- Có package hoặc module nào tạo chu trình phụ thuộc không?
- Module nào sở hữu kiểu dữ liệu và quy tắc đang được module khác sử dụng?
- Controller, job hoặc consumer có đi tắt qua application service khi thao tác cần điều phối không?
- Một module có truy cập trực tiếp repository, bảng hoặc entity nội bộ của module khác không?
- JPA entity, ORM proxy hoặc kiểu database có xuất hiện trong API, command hoặc domain contract không?
- Việc chuyển đổi giữa request DTO, domain model và persistence model có nằm ở ranh giới phù hợp không?
- Các quy tắc phụ thuộc có được tự động kiểm tra trong CI không?
- Có unit test và integration test chứng minh hành vi, mapping và persistence đúng không?
- Mỗi abstraction hoặc event mới có giải quyết một nhu cầu cụ thể và có chi phí chấp nhận được không?

Phụ thuộc vòng làm các module khó thay đổi độc lập; truy cập tắt làm workflow và quy tắc bị bỏ qua; rò rỉ persistence khiến schema hoặc framework lưu trữ chi phối những layer không nên biết đến chúng. Khi review, hãy vẽ dependency graph, lần theo lời gọi và dữ liệu, xác định nơi sở hữu hợp đồng, rồi sửa tại ranh giới gây ra vấn đề. Mục tiêu là một kiến trúc mà đường đi của lời gọi và dữ liệu có chủ đích, các module có thể được kiểm tra độc lập và thay đổi một chi tiết lưu trữ không làm lan rộng sang toàn bộ ứng dụng.
