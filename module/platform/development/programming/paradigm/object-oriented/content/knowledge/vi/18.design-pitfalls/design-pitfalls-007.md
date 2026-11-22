# Phụ thuộc vòng và truy cập sâu vào đối tượng trong thiết kế OOP

**Chủ đề:** OOP → Lỗi thiết kế  
**Trọng tâm:** nhận diện hai mùi thiết kế thường xuất hiện cùng nhau — **phụ thuộc vòng (circular dependency)** và **truy cập sâu vào cấu trúc đối tượng (deep object navigation / message chain)** — rồi refactor mà không phá vỡ hành vi nghiệp vụ.

## 1. Một thay đổi nhỏ có thể kéo theo cả hệ thống

Giả sử ứng dụng bán hàng có hai dịch vụ:

- `OrderService` tiếp nhận đơn hàng và gọi `ShippingService` để gửi hàng.
- `ShippingService` cần địa chỉ giao hàng, nên gọi ngược `OrderService` để lấy thông tin đơn.

Đồ thị phụ thuộc:

~~~mermaid
flowchart LR
    O["OrderService"] -->|gọi ship| S["ShippingService"]
    S -->|gọi findOrder / findAddress| O
~~~

Trong code, ta dễ gặp:

~~~java
// Phác thảo mùi thiết kế — KHÔNG phải chương trình hoàn chỉnh.
final class OrderService {
    private final ShippingService shippingService;

    OrderService(ShippingService shippingService) {
        this.shippingService = shippingService;
    }

    void submit(Order order) {
        shippingService.ship(order.id());
    }
}

final class ShippingService {
    private final OrderService orderService;

    ShippingService(OrderService orderService) {
        this.orderService = orderService;
    }

    void ship(String orderId) {
        Order order = orderService.findOrder(orderId);
        // ...
    }
}
~~~

Hai đối tượng phải biết và có tham chiếu tới nhau. Nếu dùng constructor injection để tạo chúng, không thể đơn giản xây dựng `OrderService` trước khi có `ShippingService`, nhưng cũng không thể tạo `ShippingService` trước khi có `OrderService`.

Ở một nơi khác, mã tính phí giao hàng viết:

~~~java
// Phác thảo truy cập sâu — tên getter chỉ mang tính minh họa.
String city = order.getCustomer()
                   .getContactInfo()
                   .getDeliveryAddress()
                   .getCity();
~~~

Bên gọi phải hiểu cách dữ liệu nằm trong `Order → Customer → ContactInfo → DeliveryAddress`. Nếu mô hình thay đổi từ `getContactInfo()` sang một thực thể địa chỉ khác, nhiều nơi dùng chuỗi truy cập đó có thể phải sửa.

**Hai vấn đề có liên hệ nhưng không đồng nhất:** phụ thuộc vòng là **quan hệ phụ thuộc quay trở lại** giữa các thành phần; truy cập sâu là **phơi bày đường đi qua nhiều cấu trúc nội bộ**. Một hệ thống có thể mắc một lỗi mà không mắc lỗi còn lại.

## 2. Phụ thuộc vòng (Circular Dependency) là gì?

Xét một đồ thị có hướng: mỗi đỉnh là class, service, package hoặc module; cạnh `A → B` nghĩa là `A` **phụ thuộc vào** `B` theo tiêu chí đang xét (tham chiếu kiểu, gọi phương thức, import, cấu hình DI, phụ thuộc build...).

**Có chu trình** nếu tồn tại đường từ một thành phần quay lại chính nó qua các cạnh phụ thuộc, chẳng hạn:

~~~text
A → B → C → A
~~~

| Cấp độ | Ví dụ | Tác động có thể thấy |
| --- | --- | --- |
| Object/service | `OrderService → ShippingService → OrderService` | Khó khởi tạo, unit test và xác định chủ trách nhiệm |
| Package | `order → shipping → customer → order` | Ranh giới package không rõ, đổi một nơi lan sang nhiều nơi |
| Module/build | `module-a → module-b → module-a` | Một số hệ thống module/build không thể chấp nhận chu trình; tổ chức triển khai trở nên khó |
| Lớp ứng dụng | `controller → service → controller` | Đảo chiều trách nhiệm, khó hiểu kiến trúc |
| Chuỗi gọi runtime | `A.foo() → B.bar() → A.foo()` không có điểm dừng | Có thể gây đệ quy vô hạn/`StackOverflowError` |

**Phân biệt:** đồ thị phụ thuộc vòng không nhất thiết có lời gọi đệ quy vô hạn. Hai object có thể tham chiếu nhau mà chỉ tương tác một chiều trong một kịch bản cụ thể. Ngược lại, một hàm có thể tự đệ quy vô hạn mà không cần hai service phụ thuộc vòng.

Một số quan hệ hai chiều ở mô hình domain hoặc object graph có lý do hợp lệ (ví dụ parent/child có tham chiếu ngược), nhưng vẫn cần đánh giá ownership, vòng đời, serialization, equality và khả năng bảo trì. **Không phải mọi reference hai chiều đều tự động là một lỗi kiến trúc.**

## 3. Vì sao vòng phụ thuộc gây khó khăn?

### 3.1. Khởi tạo bằng dependency injection

Với constructor injection:

~~~java
// Phác thảo Spring beans.
@Service
class OrderService {
    OrderService(ShippingService shipping) { /* ... */ }
}

@Service
class ShippingService {
    ShippingService(OrderService orders) { /* ... */ }
}
~~~

Mỗi bean đòi bean kia trước khi constructor chạy xong. Các cấu hình Spring/Spring Boot thông dụng phát hiện và từ chối vòng constructor như vậy trong quá trình khởi tạo context.

Có thể bắt gặp cách né như setter injection, `@Lazy` hoặc `ObjectProvider`. Chúng có thể trì hoãn việc lấy bean hay cho phép một số tình huống khởi tạo, nhưng **không tự sửa vấn đề trách nhiệm và hướng phụ thuộc**. Nếu thực sự cần dùng một workaround, phải hiểu vòng đời, lỗi chỉ xuất hiện khi gọi runtime và lý do kiến trúc; đừng coi việc ứng dụng khởi động thành công là bằng chứng thiết kế tốt.

### 3.2. Test và thay đổi lan truyền

Muốn test riêng `OrderService` có thể phải dựng một `ShippingService`; muốn dựng `ShippingService` lại cần `OrderService`. Người viết test bị lôi vào mock lồng nhau hoặc cấu hình container phức tạp thay vì kiểm tra một hợp đồng rõ ràng.

Về bảo trì, khi hai service đều biết cấu trúc và chính sách của nhau, không rõ nơi nào sở hữu quyết định cuối cùng. Việc sửa hợp đồng nhỏ có thể làm hỏng cả hai chiều. Đặc biệt, vòng package/module dễ khiến thay đổi và phát hành độc lập trở nên tốn kém.

### 3.3. Không xác định rõ ranh giới nghiệp vụ

Vòng `Order ↔ Shipping` đôi khi là dấu hiệu hai thành phần cùng cố điều phối một quy trình. Hãy hỏi:

- Ai **ra quyết định** khi đơn đủ điều kiện bàn giao?
- Ai **sở hữu dữ liệu** địa chỉ giao?
- Ai **thực hiện** việc gọi nhà vận chuyển?
- Ai **điều phối** quy trình gồm nhiều bước?
- Thành phần nào chỉ cần dữ liệu giá trị mà không cần biết cả service kia?

Không có một công thức “tách interface là xong”. Ta cần xác định trách nhiệm thực sự trước khi đổi sơ đồ phụ thuộc.

## 4. Nhận diện vòng phụ thuộc từ đồ thị

~~~mermaid
flowchart LR
    subgraph "Trước"
      O1["OrderService"] --> S1["ShippingService"]
      S1 --> O1
    end
    subgraph "Sau"
      O2["OrderWorkflow"] --> S2["ShippingService"]
      O2 --> R2["OrderRepository"]
      S2 --> G2["DeliveryGateway"]
    end
~~~

**Cách đọc:** ở phía “sau”, quy trình cấp trên phụ thuộc vào các khả năng cấp dưới; không có mũi tên từ `ShippingService` quay lại `OrderWorkflow`. Đây là ví dụ định hướng, không phải khẳng định mọi dự án phải có lớp tên `OrderWorkflow`.

Nếu biểu diễn đồ thị bằng danh sách cạnh:

~~~text
Trước: OrderService -> ShippingService
       ShippingService -> OrderService

Sau:   OrderWorkflow -> OrderRepository
       OrderWorkflow -> ShippingService
       ShippingService -> DeliveryGateway
~~~

Một chu trình hình thành **strongly connected component** (thành phần liên thông mạnh) có nhiều đỉnh: từ bất kỳ thành phần nào trong nhóm có đường tới thành phần khác qua các phụ thuộc. Công cụ phân tích static có thể phát hiện chu trình ở cấp package/module bằng đồ thị import hoặc class reference. Nhưng một công cụ chỉ xem import **không nhất thiết tìm được mọi vòng** hình thành qua cấu hình DI, reflection hay lời gọi runtime.

Khi review, trước hết xác định rõ đang phân tích **dependency compile-time**, **bean runtime** hay **workflow nghiệp vụ**, bởi mỗi đồ thị trả lời câu hỏi khác nhau.

## 5. Các chiến lược phá vòng phụ thuộc

| Chiến lược | Khi phù hợp | Điều cần giữ |
| --- | --- | --- |
| **Chuyển dữ liệu cần thiết thành tham số** | B gọi A chỉ để lấy vài giá trị đã biết ở bước điều phối | Dữ liệu cần đúng, đủ, không lộ toàn bộ nội bộ |
| **Trích xuất service có trách nhiệm riêng** | Hai service cùng sử dụng một quy tắc chung | Service mới phải sở hữu một năng lực có ý nghĩa, không chỉ thành “GodService” thứ ba |
| **Orchestrator/application service** | Nhiều hoạt động cần phối hợp theo thứ tự | Quyền quyết định quy trình nằm ở một chỗ |
| **Đảo chiều phụ thuộc qua interface/port** | Logic lõi đang phụ thuộc trực tiếp hạ tầng/nhà cung cấp | Đặt abstraction ở ranh giới phù hợp, không chỉ thay class bằng interface cùng chiều |
| **Domain event** | Thành phần khác cần phản ứng sau một sự kiện đã xảy ra | Phải hiểu timing, thất bại, delivery semantics và eventual consistency |
| **Tách module/ownership** | Vòng xuất hiện vì các module chia sẻ cùng khái niệm | Định nghĩa lại trách nhiệm và hướng phụ thuộc, không chỉ đổi tên package |

Ví dụ **truyền dữ liệu thay cho gọi ngược**:

~~~java
// Trước: ShippingService tự tìm đơn thông qua OrderService.
shippingService.ship(orderId); // Bên trong gọi orderService.findOrder

// Sau: tầng điều phối đã có dữ liệu và truyền yêu cầu đúng nhu cầu.
shippingService.ship(
        new ShipmentRequest(order.id(), order.shippingDestination()));
~~~

`ShippingService` lúc này không cần biết `OrderService`; nó chỉ biết một **request** chứa mã đơn và đích giao.

**Chú ý:** truyền cả object `Order` khổng lồ cũng có thể phá vòng, nhưng khiến ShippingService bị phụ thuộc vào aggregate phức tạp. Chọn dữ liệu tối thiểu phù hợp với trách nhiệm: thường một value object như `ShipmentRequest` hoặc `DeliveryAddress` tốt hơn.

## 6. Truy cập sâu (Deep Object Navigation) là gì?

Một đoạn mã như:

~~~java
String city = order.getCustomer()
                   .getContactInfo()
                   .getDeliveryAddress()
                   .getCity();
~~~

thường được gọi là **message chain** hoặc **train wreck** khi bên gọi lần theo nhiều đối tượng chỉ để thực hiện một quyết định.

Vấn đề chính không phải **có bao nhiêu dấu chấm**. Các câu như `Math.max(a, b)`, `stream.map(...).filter(...).toList()` hoặc `builder.address(...).build()` cũng có nhiều dấu chấm mà có thể vẫn rất rõ ràng. Mùi thiết kế xuất hiện khi bên gọi **biết quá nhiều về cấu trúc, quan hệ và dữ liệu nội bộ của đối tượng cộng tác**.

Ba loại rủi ro:

1. **Coupling cấu trúc:** nếu đường `Order → Customer → ContactInfo → Address` thay đổi, các caller dùng đường này đều phải sửa.
2. **Nhiều điểm null/thiếu dữ liệu:** nếu một mắt xích có thể null, việc truy cập thẳng gây `NullPointerException`; thêm kiểm tra null dọc đường thường làm code rối.
3. **Sai ranh giới trách nhiệm:** nhiều caller tự quyết định thông tin giao hàng dựa vào cùng cấu trúc có thể dẫn tới diễn giải nghiệp vụ khác nhau.

### Law of Demeter — “chỉ nói với cộng tác viên gần mình”

Một cách diễn đạt thực dụng của **Law of Demeter (LoD)**: một phương thức nên hạn chế giao tiếp với những đối tượng mà nó biết trực tiếp, thay vì liên tục gọi phương thức của object nhận được từ object khác.

Quy tắc trực giác cho một method là ưu tiên tương tác với:

- Chính đối tượng hiện tại (`this`).
- Tham số được truyền vào.
- Field/thành phần cộng tác trực tiếp của mình.
- Object được tạo ra hoặc thuộc trách nhiệm trực tiếp của method.

Đây là **nguyên tắc gợi ý về coupling**, không phải luật compiler và không cấm mọi lời gọi nối chuỗi. Trong thực tế, object value/DTO, các builder, `Stream`, những API traversal có chủ đích và query projection có thể khiến một chuỗi method rất rõ ràng và hợp lý.

**Đừng chữa LoD bằng cách giấu traversal vào một lớp tiện ích tùy tiện**, ví dụ `DeepGetterUtil.getCity(order)`: caller có thể ít dấu chấm hơn, nhưng phụ thuộc cấu trúc vẫn nằm nguyên trong utility và lan rộng theo cách khác.

## 7. Refactor truy cập sâu theo ý định nghiệp vụ

### Cách 1: đặt câu hỏi ở object sở hữu tri thức

Thay vì bên gọi cần biết quan hệ customer/contact/address:

~~~java
// Dễ phụ thuộc sâu vào mô hình.
String city = order.getCustomer()
                   .getContactInfo()
                   .getDeliveryAddress()
                   .getCity();
~~~

ta có thể cung cấp một API rõ ngữ nghĩa:

~~~java
// Order công bố thông tin tối thiểu bên ngoài cần.
DeliveryAddress destination = order.shippingDestination();
~~~

`Order` vẫn biết cách truy cập dữ liệu bên trong của chính nó. Nhưng caller không bị buộc theo cùng sơ đồ object. Nếu cách lưu địa chỉ đổi, thay đổi được cô lập gần nơi sở hữu.

**Cảnh báo:** không thêm vào `Order` hàng trăm phương thức kiểu `getCustomerContactAddressCityCountryCode...`. Hãy đặt tên theo ý nghĩa nghiệp vụ (**shippingDestination**, **billingContact**, **eligibleForCancellation**) và chỉ giữ những trách nhiệm thuộc về aggregate đó.

### Cách 2: dùng Value Object/DTO hẹp

Nếu bên vận chuyển chỉ cần mã đơn và địa chỉ, truyền:

~~~java
record ShipmentRequest(
        String orderId,
        DeliveryAddress destination
) {}
~~~

Hợp đồng này giúp dịch vụ vận chuyển không cần biết `Customer`, `Order` hoặc nhiều lớp trung gian. Nếu cần chuẩn hóa dữ liệu, triển khai trong boundary/assembler thích hợp.

### Cách 3: “Tell, Don't Ask” khi có hành vi

Khi object sở hữu trạng thái liên quan tới quyết định nghiệp vụ, có thể yêu cầu nó thực hiện hành vi:

~~~java
// Mùi thiết kế nếu logic kiểm tra bị lặp ở nhiều nơi:
if (order.getStatus() == PAID
        && !order.getItems().isEmpty()) {
    order.setStatus(SHIPPED);
}

// API có ý định rõ, bảo vệ invariant:
order.markShipped(); // tự xác nhận precondition phù hợp
~~~

Đây là ví dụ phác thảo; `markShipped()` cần được thiết kế trong aggregate thực tế. Điều quan trọng là **bên ngoài không tự đọc các field rồi gán trạng thái tùy ý**, vượt qua bất biến của domain.

Tuy nhiên, không phải mọi dữ liệu đều cần biến thành behavior của object. Nếu UI chỉ hiển thị `city` từ một immutable DTO, truy cập `dto.address().city()` có thể hoàn toàn rõ và phù hợp.

## 8. Java 17 hoàn chỉnh: luồng giao hàng không có phụ thuộc vòng

Ví dụ này mô phỏng tạo yêu cầu giao hàng trong bộ nhớ. **Order** biết địa chỉ thuộc đơn, **OrderService** điều phối, **ShippingService** chỉ xử lý request và phụ thuộc vào **DeliveryGateway**. Không có một mũi tên từ `ShippingService` quay ngược về `OrderService`.

Lưu thành **DependencyRefactorDemo.java**:

~~~java
import java.util.Objects;

public class DependencyRefactorDemo {

    public record DeliveryAddress(String city, String street) {
        public DeliveryAddress {
            city = requiredText(city, "city");
            street = requiredText(street, "street");
        }
    }

    public record Customer(String id, DeliveryAddress address) {
        public Customer {
            id = requiredText(id, "customerId");
            Objects.requireNonNull(address, "address");
        }
    }

    public record Order(String id, Customer customer) {
        public Order {
            id = requiredText(id, "orderId");
            Objects.requireNonNull(customer, "customer");
        }

        // Công bố nhu cầu nghiệp vụ, không buộc caller lần theo Customer.
        public DeliveryAddress shippingDestination() {
            return customer.address();
        }
    }

    public record ShipmentRequest(
            String orderId,
            DeliveryAddress destination) {
        public ShipmentRequest {
            orderId = requiredText(orderId, "orderId");
            Objects.requireNonNull(destination, "destination");
        }
    }

    public record DispatchReceipt(String orderId, String trackingCode) {
        public DispatchReceipt {
            orderId = requiredText(orderId, "orderId");
            trackingCode = requiredText(trackingCode, "trackingCode");
        }
    }

    // Port: hợp đồng hạ tầng ở ranh giới gửi đơn.
    public interface DeliveryGateway {
        String dispatch(String orderId, DeliveryAddress destination);
    }

    // Fake adapter cho ví dụ; không có kết nối nhà vận chuyển thật.
    public static final class FakeDeliveryGateway implements DeliveryGateway {
        @Override
        public String dispatch(String orderId, DeliveryAddress destination) {
            Objects.requireNonNull(destination, "destination");
            return "TRACK-" + orderId;
        }
    }

    public static final class ShippingService {
        private final DeliveryGateway gateway;

        public ShippingService(DeliveryGateway gateway) {
            this.gateway = Objects.requireNonNull(gateway, "gateway");
        }

        public DispatchReceipt ship(ShipmentRequest request) {
            Objects.requireNonNull(request, "request");
            String trackingCode = gateway.dispatch(
                    request.orderId(), request.destination());
            return new DispatchReceipt(request.orderId(), trackingCode);
        }
    }

    public static final class OrderService {
        private final ShippingService shipping;

        public OrderService(ShippingService shipping) {
            this.shipping = Objects.requireNonNull(shipping, "shipping");
        }

        public DispatchReceipt requestShipment(Order order) {
            Objects.requireNonNull(order, "order");

            ShipmentRequest request = new ShipmentRequest(
                    order.id(),
                    order.shippingDestination());

            return shipping.ship(request);
        }
    }

    private static String requiredText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    name + " không được rỗng");
        }
        return value.trim();
    }

    public static void main(String[] args) {
        Order order = new Order(
                "ORD-42",
                new Customer(
                        "CUS-7",
                        new DeliveryAddress("Hà Nội", "Tràng Tiền")
                )
        );

        // Composition root: lắp ráp một chiều từ ngoài.
        DeliveryGateway gateway = new FakeDeliveryGateway();
        ShippingService shipping = new ShippingService(gateway);
        OrderService orders = new OrderService(shipping);

        DispatchReceipt receipt = orders.requestShipment(order);

        System.out.println(order.shippingDestination().city());
        System.out.println(receipt.trackingCode());
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac DependencyRefactorDemo.java
java DependencyRefactorDemo
~~~

Kết quả:

~~~text
Hà Nội
TRACK-ORD-42
~~~

### Vì sao ví dụ này cải thiện cả hai mùi thiết kế?

**Về phụ thuộc:**

~~~text
OrderService → ShippingService → DeliveryGateway
OrderService → Order (dữ liệu)
ShippingService → ShipmentRequest (dữ liệu)
~~~

Không có `ShippingService → OrderService`. Chính `OrderService` tạo **ShipmentRequest** và truyền xuống; `ShippingService` không phải gọi ngược để tải địa chỉ.

**Về truy cập sâu:** trước kia ShippingService có thể truy cập `Order.Customer.Address`. Sau refactor, nó chỉ biết **ShipmentRequest.destination()**. Nếu `Order` chuyển dữ liệu khách hàng sang cấu trúc khác, giao diện ShippingService không nhất thiết đổi.

**Về interface:** `DeliveryGateway` có vai trò thực tế: nó phân cách logic giao hàng với adapter gửi tới hệ thống bên ngoài. Đây không phải mẹo tạo một interface cho mọi class; chỉ tạo abstraction ở nơi có một phụ thuộc hạ tầng rõ.

**Về trách nhiệm:** `OrderService` được dùng như tầng điều phối trong ví dụ. Nếu hệ thống có nhiều bước phối hợp giữa kho, thanh toán và giao hàng, có thể đổi sang một `OrderWorkflow` hoặc application service phù hợp mà không cần cho các service chuyên biệt gọi vòng qua nhau.

**Giới hạn:** code chưa có database, quyền người dùng, giao dịch hoặc nhà vận chuyển thật. `TRACK-ORD-42` chỉ là mã giả; không có bảo đảm hàng đã được bàn giao. Khi tích hợp thật, phải định nghĩa trạng thái thành công và cơ chế xác nhận, retry/idempotency.

## 9. Unit test chứng minh đã giảm coupling

Khi `ShippingService` chỉ phụ thuộc vào interface `DeliveryGateway`, test không cần dựng `OrderService` để kiểm tra việc giao dữ liệu. Một fake ghi lại lời gọi đủ dùng:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class DependencyRefactorDemoTest {

    static final class RecordingGateway
            implements DependencyRefactorDemo.DeliveryGateway {
        String lastOrderId;
        DependencyRefactorDemo.DeliveryAddress lastAddress;
        int calls;

        @Override
        public String dispatch(
                String orderId,
                DependencyRefactorDemo.DeliveryAddress destination) {
            calls++;
            lastOrderId = orderId;
            lastAddress = destination;
            return "TEST-001";
        }
    }

    @Test
    void shippingChiCanRequestVaGateway() {
        var gateway = new RecordingGateway();
        var shipping = new DependencyRefactorDemo.ShippingService(gateway);

        var address = new DependencyRefactorDemo.DeliveryAddress(
                "Đà Nẵng", "Bạch Đằng");

        var receipt = shipping.ship(
                new DependencyRefactorDemo.ShipmentRequest(
                        "ORD-1", address));

        assertEquals("ORD-1", gateway.lastOrderId);
        assertEquals(address, gateway.lastAddress);
        assertEquals(1, gateway.calls);
        assertEquals("TEST-001", receipt.trackingCode());
    }

    @Test
    void orderServiceKhongCanShippingGoiNguoc() {
        var gateway = new RecordingGateway();
        var shipping = new DependencyRefactorDemo.ShippingService(gateway);
        var orders = new DependencyRefactorDemo.OrderService(shipping);

        var order = new DependencyRefactorDemo.Order(
                "ORD-2",
                new DependencyRefactorDemo.Customer(
                        "CUS-1",
                        new DependencyRefactorDemo.DeliveryAddress(
                                "Huế", "Hùng Vương")
                )
        );

        orders.requestShipment(order);

        assertEquals("ORD-2", gateway.lastOrderId);
        assertEquals("Huế", gateway.lastAddress.city());
    }

    @Test
    void duLieuDauVaoKhongHopLeBiTuChoiSom() {
        assertThrows(IllegalArgumentException.class,
                () -> new DependencyRefactorDemo.DeliveryAddress(
                        " ", "Đường A"));
    }
}
~~~

Test dùng **JUnit Jupiter 5** và được đặt trong **DependencyRefactorDemoTest.java**. File Java demo chính chạy độc lập, không cần JUnit. Test đo kết quả nghiệp vụ tại boundary thay vì phụ thuộc vào cấu trúc bên trong của `Order`.

Sau khi refactor code thật, nên bổ sung test tích hợp cho phần nghiệp vụ từng có trước đó: địa chỉ thiếu, đơn không đủ điều kiện gửi, sự cố gateway, timeout và nhiều lần gửi yêu cầu.

## 10. Trường hợp truy cập sâu không nhất thiết xấu

Một nguyên tắc hữu ích phải giúp **ra quyết định**, không chỉ tăng số lượng wrapper và method.

| Đoạn mã | Có đáng lo? | Lý do |
| --- | --- | --- |
| `order.customer().address().city()` trong nhiều service nghiệp vụ | **Có thể có** | Nhiều caller biết cấu trúc aggregate, dễ thay đổi dây chuyền |
| `order.shippingDestination()` | Thường rõ hơn | API dựa trên ý định nghiệp vụ, giảm tri thức nội bộ của caller |
| `dto.customer().address().city()` trong mapper/view | Tùy ngữ cảnh | DTO được thiết kế để đọc dữ liệu; các lớp mapping thường có trách nhiệm traversal |
| `stream.filter(...).map(...).toList()` | Không tự động | Đây là pipeline của một API có chủ đích |
| `builder.address(...).note(...).build()` | Không tự động | Chaining thể hiện quy trình dựng object |
| `config.getDb().getPool().getMaxConnections()` rải nhiều module | Đáng xem lại | Coupling tới chi tiết cấu hình qua nhiều tầng |
| `apiResponse.data().items()` ở boundary adapter | Thường chấp nhận được | Adapter vốn có trách nhiệm chuyển từ cấu trúc API ngoài sang kiểu nội bộ |

**Không đếm số dấu chấm rồi kết luận.** Hỏi: “Nếu cấu trúc bên trong đổi mà ý nghĩa nghiệp vụ giữ nguyên, bao nhiêu caller phải thay đổi?” Nếu câu trả lời là rất nhiều và những caller đó không thực sự sở hữu cấu trúc ấy, đây là dấu hiệu cần refactor.

Đừng “giấu” traversal bằng cách đặt mọi thao tác vào một **God object**. Mỗi method mới nên phản ánh trách nhiệm rõ và có khả năng bảo trì độc lập.

## 11. Bẫy thường gặp khi refactor vòng phụ thuộc

### 11.1. Trích interface nhưng vòng vẫn còn

Trước:

~~~text
AService → BService → AService
~~~

Sau khi chỉ thay class bằng interface:

~~~text
AService → BPort → BService → APort → AService
~~~

Nếu đồ thị thực tế vẫn quay lại theo hướng này, phụ thuộc vòng không biến mất. Sửa đúng nghĩa cần **đổi vị trí trách nhiệm hoặc hướng thông tin**, không chỉ đổi tên phụ thuộc. Interface là công cụ biểu diễn ranh giới, không phải thuốc trị mọi vòng.

### 11.2. Đưa mọi thứ vào “CommonService”

Nếu hai service gọi lẫn nhau vì có logic chung, trích logic chung sang lớp thứ ba chỉ tốt khi lớp thứ ba có **trách nhiệm hẹp và độc lập**. Nếu nó chứa cả order, shipping, payment, persistence và notification, ta đã đổi một vòng phụ thuộc thành một **God Service** khó bảo trì.

### 11.3. Dùng event để né gọi trực tiếp nhưng mất hợp đồng thời gian

Một event như `OrderPaid` có thể khiến Shipping phản ứng mà không cần OrderService gọi trực tiếp. Nhưng phải trả lời: giao hàng có thể đến sau không? Nếu consumer thất bại thì làm gì? Có thể nhận event trùng không? Transaction nào xác nhận sự kiện được phát?

Event giúp **tách giao tiếp** nhưng không tự đảm bảo transaction, exactly-once hay sự nhất quán tức thời. Những vấn đề này có thể quan trọng hơn vòng phụ thuộc ban đầu.

### 11.4. Lưu trạng thái trùng nhau ở nhiều nơi

Để phá deep navigation, có người sao chép toàn bộ dữ liệu `Customer` vào `Order`, rồi tiếp tục cho tất cả lớp sửa cả hai bản. Điều đó tạo rủi ro đồng bộ.

Hãy phân biệt:

- **Snapshot có chủ đích:** địa chỉ giao hàng tại thời điểm đặt đơn được cố định, dù khách đổi địa chỉ tài khoản sau đó — có thể là yêu cầu nghiệp vụ đúng.
- **Duplication vô tình:** hai bản cùng đại diện một sự thật hiện tại và phải sửa đồng thời — dễ lỗi.

Value object hoặc read model có thể trùng dữ liệu theo mục đích rõ ràng, nhưng cần biết bản nào có thẩm quyền và khi nào cập nhật.

## 12. Chẩn đoán trong dự án Java/Spring

Dấu hiệu từ code, test và vận hành:

- Spring bean tạo lỗi về circular reference hoặc lớp A yêu cầu B, B yêu cầu A.
- Nhiều lớp dùng `@Lazy` để vòng bean “đỡ lỗi” mà không giải thích được trách nhiệm.
- Unit test một service phải dựng sâu chuỗi service khác.
- Một thay đổi field trong object buộc sửa nhiều service dùng `getA().getB().getC()`.
- Rất nhiều helper làm thay việc đọc dữ liệu xuyên tầng nhưng không có tên nghiệp vụ.
- Module cao tầng import module hạ tầng, còn module hạ tầng lại import ngược package của module cao tầng.
- Debug phải nhảy giữa nhiều service mới biết nơi nào quyết định và nơi nào thực hiện.

### Quy trình kiểm tra

1. **Khoanh vùng triệu chứng:** bean cycle, compile/build cycle, vòng gọi runtime hay message chain?
2. **Vẽ cạnh phụ thuộc hiện tại:** `A → B` nghĩa gì; có vòng quay lại thật không?
3. **Xác định chủ sở hữu dữ liệu và hành vi:** object nào phải bảo vệ invariant? Service nào có quyền điều phối?
4. **Đo dữ liệu tối thiểu:** caller thực sự cần một value object, một quyết định, hay toàn bộ domain object?
5. **Chọn refactor nhỏ:** truyền tham số, chuyển hành vi, tách port hoặc thêm orchestrator; tránh thay toàn bộ kiến trúc chỉ để sửa một getter.
6. **Viết test behavior trước:** lưu lại kết quả và đường lỗi cũ; kiểm tra sau refactor vẫn giữ.
7. **Kiểm tra lại đồ thị:** đảm bảo cạnh gây vòng đã bị loại, không chỉ đổi thành tên interface khác.
8. **Kiểm tra thay đổi xuyên module:** một thay đổi nội bộ không nên kéo theo hàng loạt nơi chỉ vì truy cập sâu.

Có thể sử dụng IDE call hierarchy/dependency graph và công cụ static architecture testing (ví dụ các bài test dependency theo package) nếu dự án có sẵn. Công cụ hỗ trợ tìm cạnh; **quyết định ranh giới trách nhiệm vẫn cần phân tích domain**.

## 13. Khi nào *không* nên áp dụng máy móc?

### Với vòng phụ thuộc

Trong một mô hình dữ liệu graph/tree có tham chiếu ngược (ví dụ một node có parent và children), vòng tham chiếu có thể hữu ích và được quản lý bằng invariant rõ ràng. Vấn đề lớn hơn thường nằm ở **lifecycle, ownership, serialization/recursion và phụ thuộc module** chứ không phải chỉ nhìn thấy hai mũi tên.

Với code nghiệp vụ hay DI, vẫn cần cảnh giác khi hai service điều phối ngược nhau. Nhưng không nhất thiết phải tạo bốn interface, một event bus và hai adapter chỉ để thay một dependency đơn giản.

### Với truy cập sâu

Nếu đang chuyển một JSON response/DTO sang cấu trúc view, đường truy cập `response.data().user().name()` có thể là trách nhiệm bình thường của mapper. Dùng `Stream` hoặc fluent API cũng không tự vi phạm tinh thần Law of Demeter.

Câu hỏi chính là **bên gọi có đang phụ thuộc vào một cấu trúc nội bộ không thuộc trách nhiệm của nó?** Nếu chỉ truy cập một public data contract được thiết kế để đọc, mức coupling có thể đã nằm trong giới hạn chấp nhận được.

## 14. Bài tập refactor

Một hệ thống mượn sách có các thành phần:

~~~text
LoanService → MemberService
MemberService → NotificationService
NotificationService → LoanService
~~~

`NotificationService` gọi ngược `LoanService` để lấy ngày đến hạn và địa chỉ liên hệ. Đồng thời trong giao diện quản trị có nhiều đoạn:

~~~java
loan.getMember().getProfile().getContact().getEmail();
~~~

**Yêu cầu thực hành:**

1. Vẽ đồ thị phụ thuộc, chỉ ra chu trình và những phần code truy cập sâu.
2. Giải thích `LoanService` cần gì từ `MemberService`; `NotificationService` thực sự cần dữ liệu gì để gửi thông báo.
3. Thiết kế `ReminderRequest(loanId, dueDate, email)` hoặc value object thích hợp để thành phần điều phối truyền dữ liệu **theo nhu cầu** cho NotificationService.
4. Quyết định nơi quản lý trạng thái mượn, nơi lấy thông tin hội viên và nơi gửi email. Không đưa tất cả vào một service.
5. Viết interface cho cổng gửi thông báo nếu cần phân cách nhà cung cấp bên ngoài; không tạo interface cho mọi class theo phản xạ.
6. Viết unit test cho việc tạo reminder đúng dữ liệu, thiếu email, lỗi gateway và không lặp thông báo nếu nghiệp vụ yêu cầu idempotency.
7. Vẽ lại đồ thị, chứng minh không còn chu trình ở tầng service.
8. Trả lời: truy cập chuỗi `loan.member().profile().contact().email()` trong một DTO mapper có nhất thiết cần refactor không? Vì sao?

**Tiêu chí đánh giá:** luồng phụ thuộc một chiều dễ đọc; mỗi nơi giữ đúng trách nhiệm; bên gửi thông báo không cần hiểu cấu trúc sâu của đối tượng mượn; lỗi và kết quả nghiệp vụ không bị thay đổi vô ý; test có thể thiết lập các dịch vụ riêng biệt mà không phải dựng một vòng bean.

---

**Kết luận:** *phụ thuộc vòng* làm các thành phần khó tạo, kiểm thử và phát triển độc lập; *truy cập sâu* khiến bên gọi hiểu quá nhiều về cấu trúc nội bộ của đối tượng. Hướng cải thiện không phải “thêm interface” hoặc “xóa dấu chấm” cho đủ hình thức. Hãy tìm đúng nơi sở hữu dữ liệu, hành vi và điều phối; truyền hợp đồng dữ liệu hẹp, đóng gói quyết định nghiệp vụ và giữ hướng phụ thuộc rõ ràng.