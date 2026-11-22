# Hợp đồng công bố, phiên bản và khả năng tương thích

Trong Domain-Driven Design, một Bounded Context không chỉ có mô hình và ngôn ngữ riêng; khi nó trao đổi dữ liệu với context khác, nó còn phải xác định **hợp đồng công bố** (Published Contract). Hợp đồng mô tả dữ liệu và ý nghĩa mà bên cung cấp cam kết cho bên tiêu thụ. Phiên bản của hợp đồng là cách thay đổi cam kết theo thời gian, còn khả năng tương thích xác định consumer cũ có tiếp tục hoạt động khi provider thay đổi hay không.

Ba khái niệm này liên kết chặt chẽ:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Hợp đồng công bố | Context khác được phép phụ thuộc vào điều gì? | OrderPlaced có orderId, customerId, total |
| Phiên bản | Thay đổi hợp đồng được quản lý như thế nào? | /v1/orders, /v2/orders hoặc schema version |
| Khả năng tương thích | Consumer hiện tại có tiếp tục hiểu hợp đồng không? | Thêm field tùy chọn thường tương thích với consumer cũ |

Mục tiêu không phải làm cho mọi context dùng chung một mô hình. Mỗi context vẫn bảo vệ mô hình riêng của mình; hợp đồng chỉ xác định phần trao đổi cần ổn định giữa các ranh giới.

## 1. Hợp đồng công bố nằm ở ranh giới giữa các Bounded Context

Giả sử hệ thống bán hàng có ba context:

- **Order Context** quản lý đơn hàng, trạng thái và tổng tiền.
- **Billing Context** quản lý hóa đơn và thanh toán.
- **Shipping Context** quản lý giao hàng.

Order Context có thể phát hành sự kiện:

~~~text
Order Context
    |
    | OrderPlaced
    v
+-----------+       +-------------+
| Billing   |       | Shipping    |
| Context   |       | Context     |
+-----------+       +-------------+
~~~

Billing không cần biết class Order của Order Context. Shipping cũng không nên đọc trực tiếp aggregate Order. Hợp đồng công bố nằm giữa chúng:

~~~json
{
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "orderId": "ORD-1001",
  "customerId": "CUS-42",
  "total": {
    "amount": 129.90,
    "currency": "USD"
  }
}
~~~

Trong DDD, đây là một phần của Context Map. Mối quan hệ giữa các context phải nói rõ ai cung cấp ngôn ngữ tích hợp và ai chịu trách nhiệm thích nghi khi ngôn ngữ đó khác với mô hình nội bộ.

Điểm quan trọng là **hợp đồng không đồng nhất với domain model**. Domain model có thể chứa hàng chục thuộc tính, invariant và association; published contract chỉ nên công bố phần mà context khác thực sự cần.

## 2. Contract phải mô tả ý nghĩa, không chỉ cấu trúc

Một JSON hợp lệ chưa chắc là một hợp đồng tốt. Consumer cần biết:

- orderId định danh đơn hàng trong context nào.
- total.amount dùng đơn vị tiền tệ nào và có bao gồm thuế hay chưa.
- eventType biểu thị một sự kiện đã xảy ra hay chỉ là một yêu cầu.
- eventVersion thay đổi theo schema hay theo business meaning.
- Consumer có thể giả định thứ tự sự kiện hay phải xử lý sự kiện đến muộn.
- Field nào bắt buộc, field nào có thể vắng mặt.

Ví dụ, câu mô tả sau có giá trị nghiệp vụ cao hơn việc chỉ ghi total: number:

> total là tổng tiền của đơn hàng tại thời điểm đơn hàng được đặt, đã bao gồm các khoản giảm giá nhưng chưa bao gồm phí vận chuyển.

Nếu Billing hiểu total theo nghĩa khác, hai bên có thể cùng tuân thủ JSON schema nhưng vẫn tích hợp sai nghiệp vụ.

Vì vậy, một contract nên có ít nhất bốn lớp thông tin:

~~~text
Contract
├── Shape       → field, type, required/optional
├── Semantics   → ý nghĩa nghiệp vụ
├── Rules       → invariant và điều kiện sử dụng
└── Evolution   → versioning và compatibility policy
~~~

## 3. Published Language giúp hai context giao tiếp mà không chia sẻ domain model

DDD thường dùng **Published Language** khi nhiều context cần một ngôn ngữ trao đổi được công bố rõ ràng. Ngôn ngữ này có thể là JSON event, REST resource, message schema hoặc một format khác.

Ví dụ Order Context có domain model:

~~~java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines;
    private OrderStatus status;

    public Money total() {
        // Quy tắc miền được thực thi trong Order.
        return calculateTotal(lines);
    }
}
~~~

Không nên biến class này thành contract chỉ vì Billing cần orderId, customerId và total. Thay vào đó, Order Context tạo DTO/event riêng:

~~~java
public record OrderPlaced(
        String eventType,
        int eventVersion,
        String orderId,
        String customerId,
        MoneyPayload total
) {
}

public record MoneyPayload(
        BigDecimal amount,
        String currency
) {
}
~~~

Cách này giữ cho thay đổi bên trong aggregate không tự động trở thành thay đổi tích hợp.

Nếu Order thêm fraudScore, đổi cách lưu OrderLine hoặc thay repository, contract không nhất thiết phải thay đổi.

## 4. Hợp đồng API và hợp đồng sự kiện có cách tiến hóa khác nhau

Có hai kiểu tích hợp phổ biến.

### API request/response

Consumer chủ động gọi provider:

~~~text
Billing → GET /orders/ORD-1001 → Order
~~~

Provider phải duy trì khả năng trả lời những request mà consumer hợp lệ gửi.

### Domain event hoặc integration event

Provider phát thông báo:

~~~text
Order → OrderPlaced → Message Broker → Billing
                                  └──────→ Shipping
~~~

Consumer không nên giả định provider sẽ chờ hoặc retry cho mình. Hợp đồng sự kiện cần quy định schema, version, identity và semantics của event.

Một event thường có envelope:

~~~json
{
  "eventId": "evt-8c1",
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "occurredAt": "2026-11-18T10:15:00Z",
  "producer": "order-context",
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-42",
    "total": {
      "amount": 129.90,
      "currency": "USD"
    }
  }
}
~~~

eventId giúp consumer nhận diện message; eventType xác định loại thông điệp; eventVersion xác định schema của phần data; occurredAt và producer giúp quan sát và xử lý vận hành.

## 5. Phân biệt domain event và integration contract

Domain event mô tả điều có ý nghĩa trong domain model. Integration event là hình thức được thiết kế để truyền thông tin đó qua ranh giới context.

Ví dụ domain event nội bộ:

~~~java
public record OrderPlaced(
        OrderId orderId,
        CustomerId customerId
) {}
~~~

Integration contract:

~~~json
{
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-42",
    "total": {
      "amount": 129.90,
      "currency": "USD"
    }
  }
}
~~~

Hai biểu diễn có thể giống nhau, nhưng không bắt buộc phải giống. Khi Billing cần thêm total trong khi domain event nội bộ chưa cần nó, application/integration layer có thể xây dựng integration event riêng.

Điều này giúp tránh việc mọi thay đổi của domain model trở thành breaking change cho toàn hệ thống.

## 6. Versioning bắt đầu từ chính sách thay đổi

Versioning không chỉ là thêm số v2. Trước khi tăng version, cần phân loại thay đổi.

| Thay đổi | Thường tương thích? | Ví dụ |
|---|---|---|
| Thêm field optional | Có | thêm discount |
| Thêm enum value | Có điều kiện | status = RETURNED có thể làm consumer cũ lỗi |
| Đổi tên field | Không | customerId → buyerId |
| Xóa field | Không | bỏ currency |
| Đổi kiểu field | Thường không | number → string |
| Đổi semantics | Không dù schema giữ nguyên | total từ trước thuế thành sau thuế |
| Thêm endpoint mới | Có | GET /orders/{id}/invoice |
| Thay đổi required field | Có nguy cơ phá consumer | thêm shippingAddress bắt buộc |

Quy tắc quan trọng là **semantic compatibility** quan trọng hơn compatibility của schema. Một field vẫn có kiểu number nhưng đổi từ “giá trước thuế” thành “giá sau thuế” vẫn là breaking change đối với consumer.

## 7. Consumer-driven contract và provider contract

Provider có thể công bố schema chính thức:

~~~text
OrderPlaced v1
  orderId: required string
  customerId: required string
  total: required object
    amount: required number
    currency: required string
~~~

Nhưng provider cũng cần biết consumer thực sự dùng phần nào. Consumer-driven contract test có thể biểu diễn:

~~~text
Billing expects:
  eventType == "OrderPlaced"
  data.orderId exists
  data.customerId exists
  data.total.amount exists
  data.total.currency exists
~~~

Mục tiêu là phát hiện thay đổi làm vỡ consumer trước khi provider triển khai.

Tuy nhiên, contract test không thay thế business contract. Test có thể xác nhận total.amount tồn tại nhưng không thể tự quyết định total có bao gồm phí vận chuyển hay không. Ý nghĩa đó phải được thống nhất trong ubiquitous language và tài liệu contract.

## 8. Quy tắc backward compatibility

Một consumer tương thích ngược có thể tiếp tục xử lý message mới trong giới hạn đã cam kết.

Ví dụ contract v1:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "CUS-42",
  "total": {
    "amount": 129.90,
    "currency": "USD"
  }
}
~~~

Contract v1.1 thêm field tùy chọn:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "CUS-42",
  "total": {
    "amount": 129.90,
    "currency": "USD"
  },
  "discount": {
    "amount": 10.00,
    "currency": "USD"
  }
}
~~~

Consumer cũ bỏ qua discount và vẫn xử lý được message. Đây là một thay đổi thường có tính backward compatible.

Ngược lại, nếu provider biến currency thành object:

~~~json
"currency": {
  "code": "USD",
  "numericCode": 840
}
~~~

consumer đang chờ string sẽ thất bại. Đây là breaking change dù tên field vẫn là currency.

## 9. Forward compatibility cũng cần được thiết kế

Forward compatibility hỏi câu ngược lại: consumer mới có thể đọc dữ liệu được tạo bởi producer cũ hay không?

Nếu consumer mới yêu cầu một field luôn tồn tại nhưng producer cũ chưa từng gửi field đó, consumer có thể không tương thích.

Một chiến lược đơn giản là:

- field mới có default hợp lý;
- consumer xử lý missing field;
- parser bỏ qua field chưa biết;
- enum có nhánh UNKNOWN hoặc chính sách fallback phù hợp;
- không suy luận business meaning từ việc field vắng mặt nếu contract không quy định điều đó.

Ví dụ Java:

~~~java
public record OrderPlacedPayload(
        String orderId,
        String customerId,
        MoneyPayload total,
        DiscountPayload discount
) {
    public DiscountPayload discountOrZero() {
        return discount == null
                ? DiscountPayload.zero(total.currency())
                : discount;
    }
}
~~~

Default chỉ hợp lệ nếu domain cho phép. Không được biến missing data thành giá trị mặc định một cách tùy tiện.

## 10. Enum là một nguồn breaking change dễ bị bỏ sót

Giả sử contract ban đầu:

~~~json
{
  "status": "PLACED"
}
~~~

Consumer có code:

~~~java
switch (status) {
    case PLACED -> processPlaced();
    case CANCELLED -> processCancelled();
}
~~~

Provider thêm RETURNED. Nếu consumer deserialize enum bằng cơ chế strict, message mới có thể bị từ chối.

Vì vậy, thêm enum value phải được xem là thay đổi có rủi ro. Với integration contract, có thể dùng string và fallback:

~~~java
public enum OrderStatus {
    PLACED,
    CANCELLED,
    UNKNOWN;

    public static OrderStatus parse(String value) {
        try {
            return value == null
                    ? UNKNOWN
                    : valueOf(value.toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            return UNKNOWN;
        }
    }
}
~~~

Fallback này chỉ giải quyết khả năng đọc. Consumer vẫn cần quyết định business behavior khi gặp trạng thái chưa biết.

## 11. Khi nào cần version mới?

Không nên tăng major version cho mọi thay đổi nhỏ. Một chính sách rõ ràng có thể dùng:

~~~text
Patch  → sửa tài liệu, metadata, lỗi không đổi contract
Minor  → thêm dữ liệu tương thích
Major  → thay đổi phá compatibility hoặc semantics
~~~

Ví dụ:

~~~text
OrderPlaced v1
       |
       +-- v1.1: thêm discount optional
       |
       +-- v1.2: thêm couponCode optional
       |
       +-- v2: đổi total semantics
               hoặc đổi customerId thành cấu trúc khác
~~~

Cách đánh số thực tế có thể khác tùy transport và platform. Điều cần giữ là quy tắc nhất quán và có thể kiểm tra được.

## 12. Có thể version ở nhiều lớp

Version có thể nằm trong URL:

~~~text
GET /api/v1/orders/ORD-1001
GET /api/v2/orders/ORD-1001
~~~

hoặc media type:

~~~text
Accept: application/vnd.shop.order+json;version=2
~~~

hoặc event schema:

~~~json
{
  "eventType": "OrderPlaced",
  "eventVersion": 2
}
~~~

Với message broker, version thường thuộc schema hoặc event type. Không nên chọn cơ chế version chỉ vì nó quen thuộc; hãy xét lifecycle của consumer, cách rollout và khả năng chạy song song.

Ví dụ migration event:

~~~text
                 ┌── Billing v1
Order Context ───┤
                 └── Billing v2
                       |
                       v
                 migrate consumers
                       |
                       v
                 retire v1
~~~

Trong giai đoạn chuyển tiếp, provider có thể phát cả hai contract hoặc cung cấp adapter. Thời gian duy trì version cũ phải có owner và tiêu chí kết thúc.

## 13. Anti-Corruption Layer bảo vệ mô hình bên nhận

Nếu Published Language của provider không khớp với mô hình của consumer, consumer có thể đặt một **Anti-Corruption Layer (ACL)** ở ranh giới.

Ví dụ provider gửi:

~~~json
{
  "customer": {
    "id": "CUS-42",
    "tier": "GOLD"
  }
}
~~~

Billing lại có model:

~~~java
public record BillingCustomerId(String value) {}
public record BillingCustomerSegment(Segment value) {}
~~~

ACL chuyển đổi:

~~~java
public final class CustomerContractTranslator {

    public BillingCustomer translate(CustomerPayload payload) {
        return new BillingCustomer(
                new BillingCustomerId(payload.id()),
                toSegment(payload.tier())
        );
    }

    private BillingCustomerSegment toSegment(String tier) {
        return switch (tier) {
            case "GOLD" -> new BillingCustomerSegment(Segment.PREMIUM);
            case "SILVER" -> new BillingCustomerSegment(Segment.STANDARD);
            default -> new BillingCustomerSegment(Segment.UNKNOWN);
        };
    }
}
~~~

ACL là nơi đặt mapping và quyết định thích nghi. Nhờ đó, mô hình Billing không phải mang các thuật ngữ đặc thù của Customer Context.

## 14. Hợp đồng nên có owner và lifecycle

Một contract không có owner dễ trở thành dependency không ai dám thay đổi.

Có thể ghi metadata:

| Field | Ví dụ |
|---|---|
| Contract | OrderPlaced |
| Version | 1 |
| Producer | Order Context |
| Consumers | Billing, Shipping |
| Owner | Order Integration Team |
| Compatibility | backward compatible |
| Deprecated at | 2026-06-01 |
| Sunset target | 2027-01-01 |

Khi một field cần bỏ, lifecycle nên có các bước:

~~~text
Introduce
   ↓
Adopt
   ↓
Deprecate
   ↓
Migrate consumers
   ↓
Verify no active consumers
   ↓
Remove
~~~

Deprecation chỉ có ý nghĩa khi consumer có thời gian di chuyển. Việc xóa một field ngay sau khi đánh dấu deprecated vẫn có thể phá hệ thống.

## 15. Một contract tốt nên chịu được thay đổi nội bộ

Giả sử Order Context chuyển từ:

~~~text
Order
 └── List<OrderLine>
~~~

sang:

~~~text
Order
 └── OrderItems
       └── PricingSnapshot
~~~

Nếu contract chỉ công bố:

~~~json
{
  "orderId": "ORD-1001",
  "total": {
    "amount": 129.90,
    "currency": "USD"
  }
}
~~~

thì consumer không cần biết cấu trúc aggregate đã thay đổi.

Đây là một tiêu chí thiết kế hữu ích:

> Thay đổi bên trong Bounded Context chỉ nên lan sang context khác khi ý nghĩa tích hợp thực sự thay đổi.

Nếu một refactor database hoặc entity làm vỡ integration contract, ranh giới contract có thể đang bám quá chặt vào mô hình nội bộ.

## 16. Ví dụ hoàn chỉnh: tiến hóa OrderPlaced

Version đầu:

~~~json
{
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-42",
    "total": {
      "amount": 129.90,
      "currency": "USD"
    }
  }
}
~~~

Version 1.1 thêm discount tùy chọn:

~~~json
{
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-42",
    "total": {
      "amount": 129.90,
      "currency": "USD"
    },
    "discount": {
      "amount": 10.00,
      "currency": "USD"
    }
  }
}
~~~

Sau đó business quyết định total phải biểu thị tổng trước phí vận chuyển thay vì sau phí vận chuyển. Đây là thay đổi semantics, nên không nên âm thầm giữ eventVersion = 1.

Một thiết kế rõ ràng có thể tạo v2:

~~~json
{
  "eventType": "OrderPlaced",
  "eventVersion": 2,
  "data": {
    "orderId": "ORD-1001",
    "customerId": "CUS-42",
    "pricing": {
      "merchandiseTotal": {
        "amount": 119.90,
        "currency": "USD"
      },
      "shippingFee": {
        "amount": 10.00,
        "currency": "USD"
      }
    }
  }
}
~~~

Tên field mới làm rõ semantics thay vì bắt consumer đoán ý nghĩa của total.

## 17. Checklist thiết kế contract

Trước khi công bố contract, hãy kiểm tra:

- Contract có một owner rõ ràng không?
- Mỗi field có business meaning rõ ràng không?
- Required và optional có được xác định không?
- Đơn vị, currency, timezone và precision có rõ ràng không?
- Contract có vô tình lộ domain model nội bộ không?
- Consumer cũ xử lý được thay đổi dự kiến không?
- Enum và unknown value có chính sách không?
- Missing field có semantics rõ ràng không?
- Versioning policy đã được thống nhất chưa?
- Có cách kiểm thử compatibility tự động không?
- Có thời gian deprecation và sunset không?
- Consumer có cần ACL để bảo vệ model riêng không?

Một contract đạt yêu cầu kỹ thuật nhưng thiếu semantics vẫn là contract yếu. Một contract có semantics rõ nhưng không có lifecycle cũng dễ trở thành gánh nặng tích hợp.

## 18. Kết nối với Strategic Design của DDD

Contract, versioning và compatibility là phần nối giữa **Bounded Context** và hệ thống thực tế. Context Map cho biết các context phụ thuộc nhau như thế nào; Published Language mô tả ngôn ngữ trao đổi; ACL bảo vệ mô hình của context nhận; versioning và compatibility cho phép mối quan hệ đó tiến hóa.

Có thể hình dung:

~~~text
                 Context Map
                     │
          ┌──────────┴──────────┐
          │                     │
   Bounded Context A      Bounded Context B
          │                     │
          └──── Published ─────┘
                Contract
                   │
          ┌────────┴────────┐
          │                 │
      Versioning       Compatibility
          │                 │
          └────────┬────────┘
                   │
              ACL / Adapter
                   │
             Consumer Model
~~~

Mục tiêu cuối cùng là giữ cho mỗi Bounded Context có thể tiến hóa theo domain của mình trong khi quan hệ tích hợp vẫn có quy tắc rõ ràng. Hợp đồng công bố xác định điều được cam kết, versioning quản lý sự thay đổi của cam kết, và compatibility giúp quyết định thay đổi nào có thể triển khai an toàn.

