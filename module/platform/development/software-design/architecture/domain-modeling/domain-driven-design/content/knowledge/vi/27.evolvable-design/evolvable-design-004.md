# Giảm phụ thuộc để các thành phần có thể được hiểu độc lập

Một thay đổi nhỏ trong quy tắc tính phí đôi khi buộc đội phát triển phải sửa hàng chục lớp: controller, service, repository, mapper, module báo cáo và cả những thành phần không trực tiếp liên quan. Nguyên nhân thường không nằm ở độ khó của phép tính. Các thành phần đã phụ thuộc quá chặt vào cấu trúc, dữ liệu hoặc cách triển khai của nhau, khiến một thay đổi lan rộng qua toàn hệ thống.

Thiết kế dễ thay đổi cần giữ cho mỗi phần có thể được hiểu, kiểm thử và thay thế trong phạm vi rõ ràng. Trong Domain-Driven Design (DDD), Bounded Context xác định ranh giới mô hình và ngôn ngữ; Aggregate bảo vệ invariant; Application Service điều phối use case; repository và các port giúp cô lập domain khỏi chi tiết hạ tầng. Những cơ chế này hỗ trợ giảm phụ thuộc, nhưng chỉ hiệu quả khi contract và quyền sở hữu được thiết kế rõ.

**Giảm phụ thuộc không có nghĩa là loại bỏ mọi liên kết.** Các thành phần vẫn cần cộng tác để hoàn thành nghiệp vụ. Mục tiêu là làm cho mối liên kết có chủ đích, nhỏ, ổn định và dễ quan sát, để thay đổi bên trong một thành phần không buộc các thành phần khác phải hiểu chi tiết triển khai của nó.

Sau bài học này, bạn có thể:

- Giải thích coupling và cohesion, cũng như ảnh hưởng của chúng đến khả năng thay đổi.
- Nhận diện phụ thuộc về mã nguồn, dữ liệu, điều khiển, thời gian và triển khai.
- Thiết kế hướng phụ thuộc vào abstraction và contract ổn định.
- Dùng Dependency Inversion Principle và Ports and Adapters để bảo vệ domain model.
- Tổ chức package/module theo năng lực nghiệp vụ và Bounded Context.
- Chọn giữa lời gọi trực tiếp, event và API tích hợp theo yêu cầu nhất quán.
- Phát hiện dependency cycle, shared database coupling và các contract dễ vỡ.
- Kiểm tra kiến trúc bằng test, module boundary và ví dụ thay đổi thực tế.

## 1. Coupling và cohesion

Hai khái niệm cơ bản giúp đánh giá khả năng thay đổi của thiết kế là **coupling** (mức độ phụ thuộc giữa các thành phần) và **cohesion** (mức độ gắn kết trách nhiệm bên trong một thành phần).

### Coupling

Hai thành phần có coupling khi một thành phần cần biết hoặc dựa vào điều gì đó từ thành phần còn lại để hoạt động. Ví dụ:

- Order Service gọi trực tiếp một class cụ thể của Payment Provider.
- Controller đọc trực tiếp field nội bộ của Aggregate.
- Module báo cáo truy vấn các bảng riêng của Inventory.
- Một module import package implementation không được công bố của module khác.
- Consumer phụ thuộc vào thứ tự event hoặc cấu trúc payload không có contract rõ ràng.

Không phải mọi coupling đều xấu. Một use case cần gọi repository là mối phụ thuộc có lý do. Vấn đề xuất hiện khi phụ thuộc không cần thiết, quá rộng, thay đổi thường xuyên hoặc khiến một thành phần phải hiểu cách thành phần khác hoạt động bên trong.

### Cohesion

Cohesion mô tả mức độ các phần bên trong một module cùng phục vụ một mục tiêu rõ ràng. Một module có cohesion tốt thường chứa những quy tắc, dữ liệu và hành vi thay đổi cùng nhau vì cùng một lý do nghiệp vụ.

Ví dụ, Sales có thể sở hữu Order, chính sách chấp nhận đơn và quy trình xác nhận đơn. Nếu một module chứa Order, logic gửi email, truy vấn báo cáo nhân sự và thao tác cấu hình máy chủ chỉ vì các lớp đó được dùng trong cùng một controller, cohesion sẽ thấp.

### Mối quan hệ giữa hai khái niệm

Một thiết kế thường hướng tới:

- Cohesion cao bên trong mỗi thành phần: trách nhiệm liên quan được đặt gần nhau.
- Coupling thấp giữa các thành phần: tương tác qua contract nhỏ, rõ và ổn định.

Không nên tối ưu hai chỉ số này một cách máy móc. Tách một module thành quá nhiều service nhỏ có thể làm tăng số lời gọi, cấu hình và contract mà không tạo ra ranh giới nghiệp vụ hữu ích. Hãy đánh giá theo khả năng hiểu, thay đổi, kiểm thử và triển khai của hệ thống.

## 2. Một thay đổi lan rộng như thế nào?

Giả sử Sales cần thay đổi cách tính tổng tiền đơn hàng. Nếu nhiều module trực tiếp đọc và tự tính từ cấu trúc Order, thay đổi có thể lan rộng:

~~~text
Order
  |
  +--> SalesController
  +--> InvoiceService
  +--> ShippingService
  +--> CustomerDashboard
  +--> DataExportJob
  +--> NotificationService
~~~

Các thành phần có thể đang:

- Đọc trực tiếp danh sách OrderLine.
- Tự tính discount hoặc tax.
- Giả định field luôn tồn tại.
- Dùng cùng một enum nội bộ.
- Ghi trực tiếp vào bảng Order.

Khi Sales đổi cách lưu giá đã chốt hoặc thay đổi quy tắc khuyến mại, tất cả caller có thể phải cập nhật.

Thiết kế có ranh giới tốt hơn để Sales sở hữu quy tắc và cung cấp contract phù hợp:

~~~text
                 +----------------------+
                 |     Sales Context    |
                 |                      |
                 | Order + Pricing Rule |
                 |                      |
                 | Public Contract      |
                 +----------+-----------+
                            |
                 stable API / event
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
       Billing          Fulfillment        Customer View
~~~

Billing, Fulfillment và Customer View chỉ phụ thuộc vào dữ liệu được Sales công bố. Sales có thể thay đổi cách tổ chức class hoặc lưu trữ nội bộ mà không buộc các consumer sửa theo, miễn contract vẫn giữ ý nghĩa đã cam kết.

## 3. Các dạng coupling thường gặp

Nhận diện đúng dạng phụ thuộc giúp chọn cách giảm nó. Một thành phần có thể đồng thời có nhiều dạng coupling.

| Dạng coupling | Mô tả | Ví dụ | Cách giảm |
|---|---|---|---|
| Content coupling | Thành phần truy cập hoặc sửa nội bộ của thành phần khác | Sửa field private qua reflection hoặc cập nhật trực tiếp bảng nội bộ | Đóng gói state, dùng hành vi và contract |
| Common coupling | Nhiều thành phần cùng dùng dữ liệu mutable toàn cục | Global mutable configuration hoặc static registry | Truyền dependency rõ ràng, giới hạn quyền sở hữu |
| Control coupling | Caller truyền cờ để điều khiển nhánh xử lý nội bộ của callee | processOrder(order, mode=3) | Tách hành vi có ý nghĩa thành use case/operation rõ |
| Stamp coupling | Truyền một cấu trúc lớn trong khi caller chỉ cần một phần | Truyền toàn bộ Order Aggregate để lấy địa chỉ giao | Dùng input/output contract vừa đủ |
| Data coupling | Thành phần trao đổi dữ liệu cần thiết qua tham số rõ ràng | Gửi OrderId và Quantity | Thường là dạng dễ quản lý nếu contract ổn định |
| Temporal coupling | Các thành phần phải được gọi theo thứ tự hoặc đúng thời điểm | Gọi create trước initialize, nếu không sẽ lỗi | Mô hình hóa trạng thái, transaction hoặc workflow |
| Deployment coupling | Một thay đổi buộc nhiều module phải build/deploy cùng lúc | Chia sẻ thư viện nội bộ không tương thích | Contract versioning và ranh giới triển khai rõ |
| Semantic coupling | Hai bên phụ thuộc vào cùng một cách hiểu ngầm | Một số 100 có lúc là VND, có lúc là phần trăm | Dùng kiểu domain và thuật ngữ cụ thể |

### Coupling qua dữ liệu thường bị đánh giá thấp

Hai module có thể không import class của nhau nhưng vẫn phụ thuộc chặt nếu cùng đọc và ghi một bảng. Ví dụ, Sales và Inventory cùng sửa bảng Stock để cập nhật số lượng. Khi schema hoặc quy tắc giữ hàng thay đổi, cả hai phải phối hợp.

Đây là coupling qua quyền sở hữu dữ liệu. Một ranh giới tốt xác định module nào sở hữu dữ liệu và invariant; các module khác trao đổi qua API hoặc event contract.

### Temporal coupling cũng là coupling

Nếu Payment chỉ hoạt động sau khi một job khác khởi tạo cache, hoặc một consumer phải nhận event A trước event B nhưng contract không bảo đảm thứ tự, hệ thống có phụ thuộc về thời gian. Hãy làm trạng thái và điều kiện sẵn sàng trở nên tường minh, thay vì dựa vào giả định ngầm.

## 4. Tổ chức trách nhiệm để cohesion cao

Một thành phần nên gom các hành vi và dữ liệu thay đổi cùng nhau. DDD cung cấp một số ranh giới để tổ chức điều đó.

### Aggregate sở hữu invariant

Aggregate Root là điểm truy cập chính để thay đổi trạng thái bên trong Aggregate. Nếu OrderLine thuộc Order Aggregate, caller nên yêu cầu Order thay đổi số lượng dòng hàng, thay vì cập nhật OrderLine trực tiếp từ module khác.

~~~java
public class Order {
    private final List<OrderLine> lines;
    private OrderStatus status;

    public void changeLineQuantity(OrderLineId lineId, Quantity quantity) {
        ensureEditable();

        OrderLine line = findLine(lineId);
        line.changeQuantity(quantity);
        recalculateTotals();
    }

    private void ensureEditable() {
        if (status != OrderStatus.DRAFT) {
            throw new OrderCannotBeEditedException();
        }
    }
}
~~~

Order giữ các quy tắc cần thiết để thay đổi dòng hàng và tổng tiền. Caller không cần biết cách Order tìm dòng hàng hoặc tính lại tổng.

### Bounded Context sở hữu mô hình

Sales có thể gọi khái niệm Order là đơn hàng đã chấp nhận. Fulfillment có thể gọi dữ liệu nhận được là yêu cầu chuẩn bị giao. Hai context có thể dùng chung OrderId nhưng không cần dùng chung một class Order.

Mỗi context giữ mô hình phù hợp với ngôn ngữ và invariant của mình. Việc chia sẻ một class lớn qua nhiều context thường làm mọi bên bị buộc vào cùng một mô hình và cùng nhịp thay đổi.

### Module sở hữu một năng lực nghiệp vụ

Trong một modular monolith, package/module có thể được tổ chức theo năng lực như Sales, Inventory, Payment và Fulfillment. Một module chứa domain model, application use case và adapter riêng của nó. Các module khác chỉ dùng API công khai đã định nghĩa.

## 5. Hướng phụ thuộc quan trọng hơn số lượng phụ thuộc

Một kiến trúc có thể có nhiều dependency nhưng vẫn dễ thay đổi nếu hướng phụ thuộc được kiểm soát. Quy tắc phổ biến là phần chứa chính sách nghiệp vụ không nên phụ thuộc trực tiếp vào chi tiết hạ tầng dễ thay đổi.

Ví dụ, Order Application Service cần gửi yêu cầu thanh toán. Nếu nó phụ thuộc trực tiếp vào class của nhà cung cấp cụ thể, việc thay nhà cung cấp có thể buộc sửa application logic.

~~~text
Order Application Service
        |
        v
StripePaymentClient
        |
        v
Stripe SDK / HTTP
~~~

Thiết kế này hướng dependency từ application logic vào chi tiết bên ngoài.

Có thể đảo hướng bằng một abstraction do application/domain boundary sở hữu:

~~~text
Order Application Service
        |
        v
PaymentGateway (port)
        ^
        |
StripePaymentAdapter
        |
        v
Stripe SDK / HTTP
~~~

Application Service phụ thuộc vào contract PaymentGateway. Adapter của Stripe triển khai contract đó. Nếu đổi nhà cung cấp, có thể viết adapter mới mà không cần đưa SDK mới vào application logic.

## 6. Dependency Inversion Principle

Dependency Inversion Principle (DIP) là một trong các nguyên tắc SOLID. Có thể diễn đạt ngắn gọn:

- Chính sách cấp cao không nên phụ thuộc vào chi tiết cấp thấp.
- Cả hai nên phụ thuộc vào abstraction.
- Abstraction không nên phụ thuộc vào chi tiết; chi tiết nên triển khai abstraction.

Trong ví dụ thanh toán:

- Chính sách cấp cao: xác nhận Order và yêu cầu thanh toán.
- Chi tiết cấp thấp: gọi REST API của nhà cung cấp.
- Abstraction: contract PaymentGateway diễn đạt hành vi mà use case cần.

Ví dụ Java:

~~~java
public interface PaymentGateway {
    PaymentResult authorize(PaymentRequest request);
}
~~~

Application Service:

~~~java
public class ConfirmOrderService {
    private final OrderRepository orders;
    private final PaymentGateway paymentGateway;

    public ConfirmOrderService(
            OrderRepository orders,
            PaymentGateway paymentGateway) {
        this.orders = orders;
        this.paymentGateway = paymentGateway;
    }

    public ConfirmOrderResult execute(ConfirmOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        order.ensureCanBeConfirmed();

        PaymentResult payment = paymentGateway.authorize(
            PaymentRequest.forOrder(order)
        );

        if (!payment.isAuthorized()) {
            return ConfirmOrderResult.paymentRejected();
        }

        order.confirm(payment.reference());
        orders.save(order);
        return ConfirmOrderResult.confirmed(order.id());
    }
}
~~~

Adapter:

~~~java
public class AcquirerPaymentAdapter implements PaymentGateway {
    private final AcquirerHttpClient client;

    public AcquirerPaymentAdapter(AcquirerHttpClient client) {
        this.client = client;
    }

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        AcquirerResponse response = client.authorize(
            request.reference(),
            request.amount(),
            request.currency()
        );

        return PaymentResult.from(response);
    }
}
~~~

Đây là ví dụ rút gọn để minh họa hướng dependency. Một tích hợp thanh toán thực tế còn cần idempotency key, xử lý timeout/unknown outcome, transaction boundary và quy trình đối soát. Không nên giữ database transaction mở trong lúc gọi provider nếu có thể tránh.

### Abstraction phải thuộc về phía cần nó

Không nên tạo interface chỉ để mọi class đều có interface. PaymentGateway hữu ích vì nó mô tả đúng khả năng mà use case cần và bảo vệ application logic khỏi SDK cụ thể.

Nếu interface chỉ phản chiếu từng method của SDK, ví dụ authorizeV1, authorizeV2, createProviderSession, mapProviderStatus, abstraction vẫn bị ràng buộc với nhà cung cấp. Hãy thiết kế contract theo ngôn ngữ của ứng dụng.

## 7. Ports and Adapters

Ports and Adapters (còn gọi là Hexagonal Architecture) tổ chức ứng dụng quanh lõi nghiệp vụ và các port biểu diễn cách lõi giao tiếp với bên ngoài.

- **Port vào (driving port):** mô tả hành động mà bên ngoài có thể yêu cầu ứng dụng thực hiện, ví dụ PlaceOrderUseCase.
- **Adapter vào:** chuyển giao thức bên ngoài thành lời gọi port, ví dụ REST controller, message consumer hoặc CLI.
- **Port ra (driven port):** mô tả khả năng ứng dụng cần từ bên ngoài, ví dụ OrderRepository hoặc PaymentGateway.
- **Adapter ra:** triển khai port bằng database, HTTP client, broker hoặc filesystem.

~~~text
       REST Controller       Message Consumer
              |                    |
              +---------+----------+
                        v
              +-------------------+
              | Application Core  |
              |                   |
              | PlaceOrderUseCase |
              | Domain Model      |
              +-------------------+
                 |             |
          output port      output port
                 |             |
                 v             v
          OrderRepository  PaymentGateway
                 ^             ^
                 |             |
          JPA Adapter    HTTP Adapter
                 |             |
                 v             v
              Database     Payment Provider
~~~

Hình này thể hiện hướng phụ thuộc ở mức thiết kế: core định nghĩa port cần thiết; adapter triển khai port. Runtime call có thể đi từ core ra adapter, nhưng source-code dependency vẫn hướng vào abstraction do core sở hữu.

## 8. Tách domain khỏi framework và hạ tầng

Domain model nên biểu diễn khái niệm và quy tắc nghiệp vụ. Nếu Entity domain trực tiếp kế thừa framework base class, chứa annotation persistence, gọi HTTP client hoặc đọc environment variable, nó sẽ khó kiểm thử và khó di chuyển.

Một cách tổ chức có thể dùng:

~~~text
sales/
  domain/
    model/
    policy/
    event/
    port/
  application/
    command/
    query/
    service/
  adapter/
    in/
      web/
      messaging/
    out/
      persistence/
      payment/
~~~

Domain có thể định nghĩa các interface cần thiết nếu đó là abstraction thuộc ngôn ngữ domain. Application layer điều phối use case. Adapter chịu trách nhiệm chuyển đổi giữa contract nội bộ và công nghệ cụ thể.

Không phải dự án nào cũng cần nhiều package con. Điều quan trọng là ranh giới dependency rõ: domain không import controller, ORM repository implementation hoặc SDK nhà cung cấp.

### Mapping giữa domain object và persistence object

Có thể dùng cùng một class cho domain và persistence nếu framework không làm mô hình bị ràng buộc quá mức. Với domain phức tạp, có thể tách persistence record/entity và domain Aggregate, rồi mapping trong adapter.

| Dùng chung class | Tách domain và persistence model |
|---|---|
| Ít mapping, ít code | Ranh giới rõ và domain ít phụ thuộc framework |
| Phù hợp domain đơn giản | Phù hợp khi persistence schema khác mô hình domain |
| Annotation có thể lan vào domain | Cần mapping và đồng bộ hai biểu diễn |
| Dễ triển khai ban đầu | Dễ thay đổi độc lập hơn nếu mapping được quản lý tốt |

Không nên tách model chỉ theo giáo điều. Hãy dựa vào độ phức tạp domain, rủi ro coupling và lợi ích của sự độc lập.

## 9. Tổ chức package theo năng lực nghiệp vụ

Một cấu trúc theo technical layer thường đặt tất cả controller vào một nơi, tất cả service vào nơi khác, tất cả repository vào nơi khác:

~~~text
com.example.app
  controller/
  service/
  repository/
  entity/
  dto/
~~~

Khi dự án lớn, một thay đổi trong năng lực Sales có thể chạm vào nhiều thư mục chung. Tên package không cho biết module nào sở hữu quy tắc.

Một cách tổ chức theo feature hoặc Bounded Context:

~~~text
com.example.app
  sales/
    api/
    application/
    domain/
    infrastructure/
  inventory/
    api/
    application/
    domain/
    infrastructure/
  payment/
    api/
    application/
    domain/
    infrastructure/
~~~

Lợi ích:

- Các thay đổi cùng năng lực nghiệp vụ nằm gần nhau.
- Dễ tìm owner của quy tắc và dữ liệu.
- Có thể đặt public API rõ cho từng module.
- Dễ kiểm tra module nào phụ thuộc module nào.
- Có thể tách module thành service riêng nếu nhu cầu triển khai xuất hiện.

Tuy nhiên, package theo context không tự tạo ra ranh giới. Nếu class trong Sales vẫn import implementation nội bộ của Inventory, hoặc hai module sửa cùng bảng, coupling vẫn tồn tại.

## 10. Thiết kế public contract nhỏ và ổn định

Một module nên công bố những gì caller thực sự cần. Không nên mở toàn bộ class, repository và entity nội bộ cho module khác.

Ví dụ contract cho Inventory:

~~~java
public interface StockReservation {
    ReservationResult reserve(
        ReservationRequest request
    );
}
~~~

Request:

~~~java
public record ReservationRequest(
    String reservationReference,
    List<ReservationLine> lines
) {}

public record ReservationLine(
    String sku,
    int quantity
) {}
~~~

Kết quả:

~~~java
public sealed interface ReservationResult
        permits ReservationAccepted, ReservationRejected {
}

public record ReservationAccepted(
    String reservationReference
) implements ReservationResult {}

public record ReservationRejected(
    String reasonCode
) implements ReservationResult {}
~~~

Caller chỉ cần biết cách yêu cầu giữ hàng và nhận kết quả. Nó không cần biết Inventory dùng bảng nào, Aggregate có field nào hoặc repository được triển khai bằng ORM nào.

### Contract không nên trở thành bản sao của implementation

Một contract quá rộng, trả về toàn bộ object graph nội bộ, khiến consumer phụ thuộc vào nhiều chi tiết. Hãy:

- Chỉ nhận dữ liệu cần cho hành động.
- Trả kết quả đủ để caller quyết định bước tiếp theo.
- Dùng identifier và thuật ngữ ổn định.
- Không trả ORM entity hoặc Aggregate nội bộ qua module boundary.
- Không dùng exception của framework làm contract công khai.
- Có quy tắc tương thích khi contract thay đổi.

## 11. Data ownership và tránh shared database coupling

Một trong những dạng coupling khó gỡ nhất là nhiều module cùng sở hữu và sửa dữ liệu trong một schema.

Ví dụ:

~~~text
Sales Module --------+
                     |
Inventory Module ---+----> stock table
                     |
Reporting Module ---+
~~~

Sales có thể trừ stock khi đặt đơn; Inventory cũng cập nhật stock khi nhập hàng; Reporting đọc bảng trực tiếp. Không rõ ai có quyền bảo vệ invariant số lượng và ai chịu trách nhiệm khi dữ liệu sai.

Thiết kế rõ hơn:

~~~text
Sales
  | request reservation
  v
Inventory API / Event Contract
  |
  v
Inventory owns Stock and Reservation
  |
  +--> Inventory database
  +--> StockReserved / StockUnavailable
~~~

Inventory sở hữu stock và quy tắc giữ hàng. Sales không cập nhật trực tiếp bảng Inventory. Reporting có thể dùng read model được cung cấp hoặc một pipeline dữ liệu được quản lý.

### Shared database không luôn sai

Trong modular monolith, nhiều module có thể dùng cùng một database vật lý để giảm chi phí vận hành. Điều cần giữ là quyền sở hữu logic và dữ liệu ở mức module:

- Module khác không ghi trực tiếp vào bảng nội bộ.
- Schema hoặc bảng được coi là private nếu không có contract.
- Truy cập xuyên module qua API hoặc query contract đã định nghĩa.
- Migration do owner của module chịu trách nhiệm.
- Test kiến trúc ngăn truy cập trái phép.

Database vật lý chung có thể chấp nhận; shared ownership và shared assumptions mới là nguồn coupling nguy hiểm.

## 12. Giao tiếp đồng bộ và bất đồng bộ

Giảm coupling không có nghĩa lúc nào cũng phải dùng message broker. Chọn cơ chế giao tiếp theo yêu cầu nghiệp vụ.

### Lời gọi đồng bộ

Phù hợp khi caller cần kết quả ngay để tiếp tục quyết định, ví dụ kiểm tra một chính sách hoặc yêu cầu một thao tác ngắn trong cùng ứng dụng.

Ưu điểm:

- Flow dễ theo dõi.
- Caller nhận kết quả trực tiếp.
- Dễ ánh xạ lỗi và kiểm soát transaction trong một process.

Rủi ro:

- Caller phụ thuộc thời gian sẵn sàng của callee.
- Latency của callee ảnh hưởng caller.
- Có thể tạo chuỗi gọi sâu.
- Nếu gọi qua network, timeout có thể tạo unknown outcome.

### Event hoặc message bất đồng bộ

Phù hợp khi consumer có thể xử lý sau và domain chấp nhận trạng thái trung gian. Ví dụ Sales công bố OrderAccepted để Fulfillment tiếp tục xử lý.

Ưu điểm:

- Producer không cần biết consumer cụ thể.
- Consumer có thể mở rộng hoặc triển khai độc lập.
- Có thể hấp thụ tải bằng queue.

Rủi ro:

- Eventual consistency.
- Duplicate, retry và ordering.
- Contract/schema evolution.
- Khó truy vết nếu thiếu correlation.
- Cần outbox hoặc cơ chế giao message bền vững.

### Bảng lựa chọn

| Câu hỏi | Gọi đồng bộ | Event/message |
|---|---|---|
| Cần kết quả ngay để quyết định? | Thường phù hợp | Có thể cần chờ response event, tăng độ phức tạp |
| Có thể chấp nhận xử lý trễ? | Không tận dụng được lợi thế chính | Phù hợp |
| Consumer cần biết producer? | Có dependency trực tiếp qua contract | Có thể giảm coupling producer-consumer |
| Có cần transaction tức thời? | Dễ phối hợp trong cùng resource | Thường phải mô hình hóa trạng thái trung gian |
| Cần retry/duplicate handling? | Có nếu network call không chắc chắn | Luôn cần thiết kế rõ |

Không nên dùng event chỉ để tránh một dependency đơn giản trong cùng module. Ngược lại, không nên gọi trực tiếp một service khác qua network nếu nghiệp vụ cho phép xử lý bất đồng bộ và cần độc lập vận hành.

## 13. Tránh dependency cycle

Dependency cycle xuất hiện khi module A phụ thuộc B, B phụ thuộc C và C lại phụ thuộc A:

~~~text
Sales ---> Inventory
  ^           |
  |           v
  +-------- Billing
~~~

Cycle khiến khó xác định thứ tự build, ownership và nơi đặt logic. Một thay đổi nhỏ có thể lan qua cả cụm module. Nó cũng làm việc tách module hoặc deploy độc lập khó hơn.

### Cách phá cycle

- Đưa contract ổn định về phía module sở hữu khả năng được yêu cầu.
- Đảo dependency bằng port do caller định nghĩa khi phù hợp.
- Dùng event nếu phản ứng có thể bất đồng bộ.
- Tách một khái niệm chung thực sự thành module riêng nếu nó có ownership và lifecycle rõ.
- Tránh tạo Common module chứa mọi class được dùng chung.

Ví dụ, nếu Sales cần yêu cầu Inventory giữ hàng, Sales gọi public API của Inventory hoặc gửi command qua contract. Inventory không cần import Order Aggregate; nó chỉ cần reservation request chứa SKU, quantity và reference.

Không nên phá cycle bằng cách chuyển mọi class vào package shared. Cách đó thường che giấu coupling thay vì loại bỏ nó.

## 14. Shared Kernel và Common Module cần giới hạn

DDD có khái niệm Shared Kernel: hai team hoặc context thống nhất chia sẻ một phần mô hình nhỏ và chấp nhận cùng chịu trách nhiệm thay đổi. Shared Kernel có thể hữu ích, nhưng cần quản trị chặt:

- Phạm vi rất nhỏ và có lý do nghiệp vụ rõ.
- Có owner và quy trình thay đổi chung.
- Hai bên hiểu tác động khi schema hoặc semantics thay đổi.
- Có versioning và kiểm thử tương thích.
- Không dùng làm nơi chứa mọi DTO, helper và enum dùng chung.

Các kiểu primitive hoặc khái niệm phổ biến như UUID, Instant có thể dùng chung mà không cần tạo một domain model dùng chung. Nhưng một enum như OrderStatus không nên chia sẻ giữa Sales và Fulfillment nếu hai context có vòng đời đơn hàng khác nhau.

Common module phình to thường trở thành nơi chứa dependency của cả hệ thống, khiến mọi module phải build và nâng version cùng nhau.

## 15. Dependency Injection và Composition Root

Dependency Injection (DI) cung cấp dependency cho thành phần thay vì để thành phần tự tạo implementation cụ thể.

Ví dụ constructor injection:

~~~java
public class PlaceOrderService {
    private final OrderRepository orders;
    private final StockReservation stockReservation;

    public PlaceOrderService(
            OrderRepository orders,
            StockReservation stockReservation) {
        this.orders = orders;
        this.stockReservation = stockReservation;
    }
}
~~~

Application Service không tự tạo JpaOrderRepository hoặc HttpInventoryClient. Một nơi ở rìa ứng dụng, thường gọi là Composition Root, cấu hình implementation:

~~~java
@Configuration
public class SalesConfiguration {
    @Bean
    PlaceOrderService placeOrderService(
            OrderRepository orders,
            StockReservation stockReservation) {
        return new PlaceOrderService(orders, stockReservation);
    }
}
~~~

Framework DI có thể tự phát hiện bean và wiring. Điều quan trọng là application/domain không tự tìm dependency từ global container hoặc service locator trong mỗi method.

### Vì sao constructor injection hữu ích?

- Dependency được nhìn thấy ngay trong constructor.
- Object không thể được tạo ở trạng thái thiếu dependency bắt buộc.
- Unit test có thể truyền fake hoặc stub.
- Có thể thay adapter mà không sửa business logic.
- Dependency graph dễ phân tích và phát hiện cycle.

DI không tự làm thiết kế tốt. Nếu một service có 18 dependency, constructor injection chỉ làm vấn đề lộ ra. Đó có thể là dấu hiệu service có quá nhiều trách nhiệm hoặc use case cần được chia nhỏ.

## 16. Không lạm dụng abstraction

Abstraction hữu ích khi nó bảo vệ một ranh giới có khả năng thay đổi hoặc làm rõ contract. Tạo interface cho mọi class có thể làm code khó điều hướng mà không giảm coupling thực tế.

Ví dụ, một lớp chỉ có một implementation, không có boundary và không có lý do thay thế, có thể không cần interface riêng. Ngược lại, một cổng thanh toán, repository, clock hoặc message publisher thường có boundary rõ và cần abstraction.

Trước khi tạo interface, hãy hỏi:

- Có consumer nào cần contract này không?
- Implementation có thể thay đổi độc lập không?
- Interface có diễn đạt ngôn ngữ của caller không?
- Nó có che giấu chi tiết thực sự hay chỉ đổi tên method?
- Ai sở hữu contract và ai chịu trách nhiệm tương thích?

Tránh abstraction kiểu GenericManager, BaseService hoặc UniversalRepository nếu chúng không thể hiện một capability nghiệp vụ hoặc kỹ thuật có ý nghĩa rõ.

## 17. Coupling qua contract và cách tiến hóa contract

Ngay cả khi hai module chỉ giao tiếp qua interface, chúng vẫn có thể coupling nếu contract thay đổi thường xuyên hoặc mang semantics không rõ.

Một contract tốt cần:

- Tên và field diễn đạt rõ ý nghĩa.
- Đơn vị đo và currency rõ ràng.
- Nullability và default được xác định.
- Error/result semantics được công bố.
- Quy tắc retry/idempotency được mô tả nếu có side effect.
- Quy tắc tương thích và versioning khi cần.

Ví dụ, field amount không rõ là tiền trước thuế hay sau thuế. Một contract rõ hơn có thể dùng subtotal, taxAmount, totalAmount và currency.

### Thay đổi tương thích

Thường có thể tương thích ngược nếu thêm field tùy chọn với default an toàn mà consumer cũ bỏ qua được. Xóa field, đổi kiểu, đổi đơn vị hoặc thay ý nghĩa thường là breaking change.

Khi contract breaking:

1. Xác định consumer hiện có.
2. Tạo version mới hoặc cơ chế chuyển tiếp.
3. Cho producer công bố cả contract cũ và mới trong thời gian chuyển đổi nếu cần.
4. Nâng consumer theo kế hoạch.
5. Theo dõi usage trước khi ngừng contract cũ.

Không nên dùng versioning để hợp thức hóa mọi thay đổi nhỏ. Version chỉ cần khi semantics hoặc schema không thể tiến hóa tương thích.

## 18. Dùng Value Object để giảm coupling ngữ nghĩa

Primitive obsession khiến nhiều module cùng dùng String, int hoặc BigDecimal nhưng hiểu chúng theo cách khác nhau.

Ví dụ:

- Một int là quantity.
- Một int khác là percentage.
- Một BigDecimal là VND.
- Một BigDecimal khác là USD.
- Một String là SKU, một String khác là customer identifier.

Compiler không thể phát hiện việc truyền nhầm các giá trị cùng kiểu primitive.

Value Object đặt tên cho ý nghĩa:

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
    }
}

public record Sku(String value) {
    public Sku {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
    }
}
~~~

Value Object giúp contract thể hiện ý nghĩa rõ hơn và gom validation tại một nơi. Nhưng không nên tạo kiểu mới cho mọi primitive nếu nó không mang semantics hoặc quy tắc riêng.

### Không chia sẻ Value Object chỉ vì tên giống nhau

Money ở Sales và Money ở Accounting có thể có precision, rounding, currency conversion và policy khác nhau. Có thể chia sẻ một kiểu giá trị rất ổn định nếu hai context thực sự thống nhất semantics. Nếu không, hãy chuyển đổi qua contract rõ ràng thay vì ép dùng một class chung.

## 19. Giảm coupling trong kiểm thử

Một thành phần dễ kiểm thử độc lập khi dependency của nó được khai báo rõ và có contract nhỏ.

Ví dụ test Application Service bằng fake:

~~~java
class InMemoryOrderRepository implements OrderRepository {
    private final Map<OrderId, Order> data = new HashMap<>();

    @Override
    public Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(data.get(id));
    }

    @Override
    public void save(Order order) {
        data.put(order.id(), order);
    }
}
~~~

Test có thể dùng FakePaymentGateway để mô phỏng kết quả:

~~~java
class FakePaymentGateway implements PaymentGateway {
    private PaymentResult nextResult;

    public void returnNext(PaymentResult result) {
        this.nextResult = result;
    }

    @Override
    public PaymentResult authorize(PaymentRequest request) {
        return nextResult;
    }
}
~~~

Nếu test một quy tắc domain cần khởi động database, broker và HTTP server, domain có thể đang phụ thuộc quá nhiều vào hạ tầng. Nếu test chỉ kiểm tra wiring, mock mọi thứ đến mức không còn kiểm tra contract thật, test cũng có thể tạo cảm giác an toàn giả.

### Các cấp kiểm thử

| Loại test | Mục tiêu | Phụ thuộc nên dùng |
|---|---|---|
| Domain unit test | Invariant và hành vi Aggregate | Object domain thuần |
| Application unit test | Điều phối use case | Fake/mock các port |
| Adapter integration test | Mapping và giao tiếp với công nghệ | Database, broker hoặc HTTP test server |
| Contract test | Producer/consumer hiểu cùng contract | Schema hoặc provider contract |
| Architecture test | Quy tắc module và dependency | Bytecode/package graph |
| End-to-end test | Một luồng nghiệp vụ hoàn chỉnh | Hệ thống tích hợp gần thực tế |

Mỗi loại test kiểm tra một ranh giới khác nhau. Không cần dùng end-to-end test để thay thế mọi unit và integration test.

## 20. Kiểm soát dependency bằng module boundary

Trong Java, package chỉ là một cách tổ chức mã nguồn. Nếu mọi package đều public và module nào cũng import được package của module khác, ranh giới chủ yếu tồn tại trong tài liệu.

Có thể tăng cường boundary bằng:

- Java Platform Module System (JPMS) với exports/requires khi phù hợp.
- Module riêng trong Gradle/Maven.
- Package-private để giới hạn truy cập nội bộ.
- Architecture test kiểm tra package dependency.
- Quy ước chỉ public API được import từ module khác.
- Code review và ownership rõ ràng.

Ví dụ JPMS:

~~~java
module com.example.sales {
    requires com.example.shared.contracts;

    exports com.example.sales.api;
}
~~~

Package domain và infrastructure không được export sẽ khó bị module khác truy cập trực tiếp qua module system. JPMS có các giới hạn và cấu hình riêng; không cần áp dụng cho mọi dự án, nhưng nó minh họa cách biến ranh giới kiến trúc thành ràng buộc kỹ thuật.

### Dependency rule có thể được kiểm tra tự động

Một số quy tắc hữu ích:

- Domain không phụ thuộc web, persistence adapter hoặc messaging framework.
- Sales không import package internal của Inventory.
- Module chỉ truy cập public API của module khác.
- Adapter không được trở thành dependency của domain.
- Không có dependency cycle giữa các module nghiệp vụ.

Architecture test nên kiểm tra quy tắc có giá trị lâu dài, không biến mọi chi tiết package thành luật cứng khiến refactor vô hại trở nên khó khăn.

## 21. Thay đổi một adapter mà không thay domain

Giả sử ứng dụng ban đầu dùng PostgreSQL. Sau này đội cần chuyển một phần lưu trữ sang document database. Nếu Application Service phụ thuộc interface repository và domain model không chứa annotation/SQL đặc thù, có thể triển khai adapter mới:

~~~text
Before:
OrderRepository port
       ^
       |
PostgresOrderRepository

After:
OrderRepository port
       ^
       +---------------------+
       |                     |
PostgresOrderRepository  DocumentOrderRepository
~~~

Application Service vẫn dùng cùng contract. Tuy nhiên, thay database không phải lúc nào cũng chỉ là thay adapter: transaction, query semantics, consistency, locking và mapping có thể khác. Nếu use case dựa vào tính năng riêng của PostgreSQL, contract có thể đang để lộ giả định storage.

Mục tiêu là để domain/application phụ thuộc vào semantics cần thiết, đồng thời làm rõ các trade-off khi adapter mới không hỗ trợ cùng semantics.

## 22. Những dấu hiệu cho thấy coupling đang quá cao

Hãy xem xét thiết kế khi xuất hiện các dấu hiệu:

- Một thay đổi nhỏ buộc sửa nhiều module không liên quan.
- Module phải import nhiều class internal của module khác.
- Một module không thể build hoặc test nếu không khởi động cả ứng dụng.
- Nhiều module cùng ghi một bảng hoặc cùng sở hữu một enum trạng thái.
- DTO API và domain entity được dùng lẫn cho mọi tầng.
- Một service có quá nhiều dependency hoặc nhiều cờ điều khiển hành vi.
- Dependency cycle giữa package hoặc module.
- Thay nhà cung cấp bên ngoài làm thay đổi business logic.
- Test phải mock một object graph lớn chỉ để gọi một method.
- Một lỗi ở hệ thống phụ làm hỏng use case không cần phụ thuộc đó.
- Các team phải release cùng nhau vì contract nội bộ không được quản lý.

Một dấu hiệu đơn lẻ chưa đủ chứng minh thiết kế sai. Hãy tìm nguyên nhân và chi phí thực tế: thay đổi lan rộng, lỗi lan truyền, khó test hoặc tốc độ phát triển giảm.

## 23. Quy trình giảm coupling cho một luồng nghiệp vụ

Khi cần cải thiện một luồng đang phụ thuộc chặt, có thể làm theo quy trình:

**Bước 1: Chọn một use case cụ thể.** Ví dụ PlaceOrder hoặc ReserveStock. Tránh refactor toàn bộ hệ thống cùng lúc.

**Bước 2: Vẽ dependency hiện tại.** Ghi các module, class, bảng và dịch vụ ngoài mà use case đang gọi.

**Bước 3: Xác định owner.** Aggregate nào sở hữu invariant? Bounded Context nào sở hữu dữ liệu và quy tắc?

**Bước 4: Tách contract.** Xác định dữ liệu và hành vi caller thực sự cần. Không trả toàn bộ implementation object.

**Bước 5: Đặt abstraction ở đúng phía.** Port thuộc phía cần capability; adapter triển khai port bằng công nghệ cụ thể.

**Bước 6: Chọn cơ chế giao tiếp.** Gọi đồng bộ khi cần kết quả ngay; event/message khi chấp nhận xử lý bất đồng bộ.

**Bước 7: Xác định consistency và failure behavior.** Transaction, timeout, retry, idempotency, event ordering và compensation.

**Bước 8: Di chuyển từng bước.** Giữ contract cũ trong giai đoạn chuyển đổi nếu có consumer; chuyển caller sang API mới và xóa đường phụ thuộc cũ khi an toàn.

**Bước 9: Thêm kiểm tra kiến trúc.** Ngăn dependency cycle, import nội bộ và truy cập dữ liệu ngoài ownership.

**Bước 10: Đo kết quả.** Kiểm tra phạm vi file phải sửa cho một thay đổi, thời gian test, khả năng build module độc lập và số lỗi lan truyền.

## 24. Ví dụ tổng hợp: Sales phụ thuộc Inventory

Thiết kế ban đầu cho phép Sales cập nhật bảng stock trực tiếp:

~~~java
public class PlaceOrderService {
    private final JdbcTemplate jdbc;

    public void place(Order order) {
        jdbc.update(
            "UPDATE stock SET quantity = quantity - ? WHERE sku = ?",
            order.quantity(),
            order.sku()
        );
        // Lưu Order...
    }
}
~~~

Vấn đề:

- Sales biết schema nội bộ của Inventory.
- Sales tự quyết định cách trừ stock.
- Không có một nơi duy nhất bảo vệ invariant về số lượng khả dụng.
- Thay schema hoặc quy tắc giữ hàng buộc sửa Sales.
- Hai luồng cập nhật đồng thời có thể không được kiểm soát đúng.

Thiết kế lại bằng contract:

~~~java
public interface StockReservation {
    ReservationResult reserve(ReservationRequest request);
}
~~~

Sales Application Service:

~~~java
public class PlaceOrderService {
    private final OrderRepository orders;
    private final StockReservation stockReservation;

    public PlaceOrderService(
            OrderRepository orders,
            StockReservation stockReservation) {
        this.orders = orders;
        this.stockReservation = stockReservation;
    }

    public PlaceOrderResult place(PlaceOrderCommand command) {
        Order order = Order.create(command);

        ReservationResult result = stockReservation.reserve(
            ReservationRequest.from(order)
        );

        if (result instanceof ReservationRejected rejected) {
            return PlaceOrderResult.stockUnavailable(
                rejected.reasonCode()
            );
        }

        order.markStockRequested();
        orders.add(order);
        return PlaceOrderResult.accepted(order.id());
    }
}
~~~

Nếu StockReservation là lời gọi đồng bộ, Sales vẫn phụ thuộc vào khả năng Inventory sẵn sàng và phải xử lý timeout/unknown outcome. Nếu nghiệp vụ cho phép xử lý bất đồng bộ, Sales có thể lưu Order ở trạng thái PendingStock và gửi yêu cầu qua outbox; Inventory phát StockReserved hoặc StockUnavailable. Process Manager theo dõi kết quả.

Điểm quan trọng là Inventory sở hữu quyết định giữ hàng. Sales không còn tự sửa dữ liệu nội bộ của Inventory. Contract diễn đạt đúng capability mà Sales cần, và hai context có thể tiến hóa độc lập trong phạm vi contract.

## 25. Checklist đánh giá thiết kế

- [ ] Mỗi module có mục tiêu và owner rõ ràng.
- [ ] Các quy tắc thay đổi cùng nhau được đặt gần nhau.
- [ ] Aggregate bảo vệ invariant của chính nó.
- [ ] Bounded Context sở hữu mô hình và dữ liệu của mình.
- [ ] Module khác chỉ truy cập public contract.
- [ ] Không có truy cập trực tiếp vào field, bảng hoặc package internal của module khác.
- [ ] Dependency cấp cao không phụ thuộc implementation cụ thể.
- [ ] Port mô tả capability theo ngôn ngữ caller.
- [ ] Adapter chứa chi tiết framework và nhà cung cấp.
- [ ] Không có dependency cycle không cần thiết.
- [ ] Shared Kernel/Common module nhỏ và có ownership.
- [ ] Contract có semantics, đơn vị, nullability và error behavior rõ.
- [ ] Giao tiếp đồng bộ/bất đồng bộ được chọn theo consistency requirement.
- [ ] Timeout, retry, idempotency và duplicate được thiết kế.
- [ ] Query/reporting không truy cập trái phép dữ liệu nội bộ.
- [ ] Có unit, integration, contract và architecture test phù hợp.
- [ ] Có thể thay adapter mà không viết lại domain policy.
- [ ] Thay đổi thông thường không lan qua nhiều module không liên quan.

## 26. Bài tập tự kiểm tra

Một hệ thống thương mại điện tử có các module Sales, Inventory, Payment và Notification. Hiện tại:

- Sales đọc bảng stock để kiểm tra số lượng.
- Sales gọi trực tiếp class PaymentProviderClient.
- Notification import Order Entity để lấy toàn bộ thông tin đơn.
- Payment và Sales cùng sửa field paymentStatus trong bảng Order.
- Reporting đọc bảng nội bộ của cả bốn module.

Hãy trả lời:

1. Những dạng coupling nào đang xuất hiện?
2. Module nào nên sở hữu số lượng hàng và quy tắc reserve?
3. Sales cần contract nào để yêu cầu giữ hàng?
4. PaymentGateway port nên do phía nào định nghĩa và adapter nằm ở đâu?
5. Notification cần toàn bộ Order Aggregate hay một message/DTO nhỏ?
6. Ai sở hữu trạng thái thanh toán? Sales nên biết kết quả thanh toán qua cách nào?
7. Reporting có thể dùng projection/read model nào để tránh truy cập trực tiếp mọi bảng?
8. Trường hợp nào nên gọi đồng bộ, trường hợp nào nên dùng event?
9. Làm sao phát hiện dependency cycle và ngăn truy cập package internal?
10. Những test nào chứng minh ranh giới mới thực sự hoạt động?

Gợi ý:

| Vấn đề | Hướng thiết kế |
|---|---|
| Sales đọc bảng stock | Inventory sở hữu Stock; công bố reserve API/command |
| Sales phụ thuộc PaymentProviderClient | Định nghĩa PaymentGateway port theo nhu cầu use case; adapter gọi provider |
| Notification import Order Entity | Dùng notification contract hoặc Integration Event với dữ liệu cần thiết |
| Sales và Payment cùng sửa paymentStatus | Payment sở hữu trạng thái thanh toán; Sales nhận PaymentAuthorized/PaymentFailed hoặc query contract |
| Reporting đọc mọi bảng | Dùng projection/data pipeline được quản lý với ownership rõ |
| Giao tiếp | Đồng bộ nếu cần kết quả ngay; event nếu chấp nhận trạng thái trung gian |
| Architecture guard | Module boundary, package visibility, JPMS hoặc architecture tests |
| Kiểm thử | Domain unit test, application test với fake port, adapter integration test, contract test và architecture test |

## Kết luận

Thiết kế dễ thay đổi cần cohesion cao bên trong thành phần và coupling có chủ đích giữa các thành phần. DDD giúp xác định ai sở hữu mô hình, dữ liệu và invariant; Dependency Inversion cùng Ports and Adapters giúp phần nghiệp vụ phụ thuộc vào contract ổn định thay vì chi tiết hạ tầng. Public API nhỏ, Value Object có semantics rõ, dependency injection và module boundary giúp các thành phần được hiểu và kiểm thử độc lập.

Không có một kỹ thuật duy nhất loại bỏ mọi phụ thuộc. Gọi đồng bộ, event, shared kernel hoặc database chung đều có thể phù hợp trong một số điều kiện. Hãy chọn theo consistency requirement, ownership, khả năng phục hồi và chi phí vận hành. Khi một thay đổi có thể được thực hiện bên trong một module mà không buộc các module không liên quan sửa theo, hệ thống đang có một ranh giới tiến hóa tốt hơn.
