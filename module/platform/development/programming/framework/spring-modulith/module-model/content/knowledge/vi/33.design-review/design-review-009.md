# Đánh giá refactor mà không phá hợp đồng

Một refactor tốt cải thiện cấu trúc bên trong nhưng giữ nguyên những cam kết mà caller đang dựa vào. Trong một modular monolith, cam kết đó có thể là Java API giữa hai application module, Named Interface, event contract, transaction behavior, cấu hình vận hành hoặc cấu trúc dữ liệu được nhiều thành phần sử dụng. Vì vậy, review refactor không thể chỉ nhìn diff và xác nhận code mới gọn hơn.

Design review cần xác định ai đang dùng hợp đồng, hợp đồng gồm những gì, thay đổi nào có thể quan sát từ phía consumer và cách chuyển đổi mà không làm consumer cũ ngừng hoạt động. Với Spring Modulith, module boundary giúp chỉ ra nơi hợp đồng được công bố và nơi implementation phải được giữ kín. Tuy nhiên, annotation hoặc package structure không tự bảo đảm tương thích hành vi; nhóm vẫn phải đánh giá API, event, dữ liệu, cấu hình và rollout.

Trong SPRING_MODULITH_MODULE_MODEL, bài học này đưa ra quy trình review một refactor có thay đổi module boundary: lập bản đồ consumer, phân loại compatibility, xem xét public API/Named Interface, đánh giá migration và kiểm thử, rồi đưa ra quyết định approve hoặc yêu cầu chỉnh sửa dựa trên bằng chứng.

## 1. Mục tiêu của design review

Một design review đạt yêu cầu cần trả lời được:

1. Refactor giải quyết vấn đề kiến trúc nào?
2. Những consumer nào đang phụ thuộc vào phần được thay đổi?
3. Hợp đồng nào đang được công bố hoặc được sử dụng trên thực tế?
4. Thay đổi có tương thích với consumer đang chạy không?
5. Nếu không tương thích, kế hoạch migration có hỗ trợ giai đoạn chuyển tiếp không?
6. Test nào chứng minh contract cũ vẫn hoạt động hoặc contract mới đã được áp dụng?
7. Có thể triển khai và rollback từng bước không?
8. Điều kiện nào cho phép loại bỏ adapter hoặc API cũ?

Review không chỉ đánh giá chất lượng code sau refactor. Nó đánh giá toàn bộ quá trình chuyển từ trạng thái hiện tại sang trạng thái đích.

## 2. Xác định phạm vi refactor trước khi đọc diff

Đầu tiên, mô tả thay đổi bằng một câu cụ thể:

> Chuyển quyền sở hữu việc kiểm tra tồn kho từ service dùng chung sang application module inventory, giữ các caller hiện tại hoạt động qua API tương thích trong thời gian migration.

Sau đó, xác định phạm vi:

| Câu hỏi | Ví dụ cần ghi nhận |
|---|---|
| Module thay đổi | inventory |
| Consumer bị ảnh hưởng | order, checkout, fulfillment, reporting |
| API thay đổi | StockService, InventoryAvailability |
| Package thay đổi | inventory.internal, inventory |
| Event liên quan | StockReserved, StockReleased |
| Dữ liệu liên quan | INVENTORY_STOCK, STOCK_RESERVATION |
| Cấu hình liên quan | inventory.reservation.enabled |
| Cách triển khai | Adapter tương thích, chuyển caller theo đợt |

Không nên review một diff lớn mà chưa hiểu mục tiêu. Nếu refactor đồng thời đổi package, API, schema và event payload, hãy tách các quyết định đó để có thể đánh giá rủi ro riêng.

## 3. Lập bản đồ consumer và dependency trước khi thay đổi

Hợp đồng chỉ có ý nghĩa khi biết ai đang sử dụng nó. Consumer có thể nằm trong application module khác, trong cùng module, trong batch job, scheduler, integration adapter hoặc một ứng dụng bên ngoài.

Lập danh sách consumer từ nhiều nguồn:

- Java imports và constructor injection.
- allowedDependencies trong @ApplicationModule.
- Named Interface references.
- Event listener và publisher.
- REST client, message consumer và integration adapter.
- Scheduled job, batch job và command-line task.
- SQL query hoặc view truy cập bảng dùng chung.
- Configuration, deployment manifest và script vận hành.
- Test fixture, contract test và tài liệu hướng dẫn.

Ví dụ:

~~~text
inventory.StockService
├── order.PlaceOrderService
├── checkout.CheckoutFacade
├── fulfillment.AllocateShipment
├── reporting.StockReportJob
└── legacy.ReconciliationJob
~~~

Không dừng ở kết quả tìm kiếm source code. Consumer chạy theo lịch hoặc được kích hoạt từ broker có thể không xuất hiện trong luồng request chính. Hãy hỏi owner của các module và nhóm vận hành về các tích hợp đang hoạt động.

Một dependency không có trong sơ đồ Spring Modulith vẫn có thể là contract thật ở cấp database, HTTP hoặc messaging.

## 4. Phân loại hợp đồng trước khi đánh giá tương thích

Không có một loại compatibility duy nhất. Cùng một thay đổi có thể tương thích ở một lớp nhưng phá vỡ lớp khác.

| Loại hợp đồng | Ví dụ | Câu hỏi review |
|---|---|---|
| Source/API contract | Public class, interface, method, constructor | Consumer có còn biên dịch không? |
| Binary contract | Method descriptor, class/package, constructor | Artifact đã biên dịch trước có còn liên kết được không? |
| Behavioral contract | Kết quả, validation, exception, side effect | Consumer có nhận cùng hành vi không? |
| Module contract | Public package, Named Interface, allowed dependency | Consumer có truy cập đúng API đã công bố không? |
| Event/message contract | Event type, field, schema, routing key | Publisher và consumer khác version có hiểu payload không? |
| HTTP contract | Path, method, status, header, JSON shape | Client cũ có tiếp tục giao tiếp được không? |
| Data contract | Table, column, constraint, view, stored procedure | Code cũ và mới có đọc/ghi được dữ liệu trong giai đoạn chuyển tiếp không? |
| Configuration contract | Property, environment variable, secret name | Deployment cũ có còn cấu hình được ứng dụng không? |
| Operational contract | Latency, ordering, retry, availability | Luồng vận hành có giữ SLA và semantics không? |

Review cần chỉ ra loại hợp đồng nào bị tác động và bằng chứng tương ứng. API vẫn compile không chứng minh event schema, transaction hoặc dữ liệu vẫn tương thích.

## 5. Phân biệt implementation nội bộ với module API

Trong Spring Modulith, package gốc của application module là API package mặc định. Package con được giữ internal khi module đóng, trừ khi được công bố bằng Named Interface hoặc module được cấu hình theo cách khác.

Ví dụ:

~~~text
com.example.shop.inventory
├── InventoryAvailability.java
├── InventoryReservation.java
├── events
│   ├── StockReserved.java
│   └── package-info.java
└── internal
    ├── InventoryRepository.java
    └── DefaultInventoryAvailability.java
~~~

Consumer khác module nên phụ thuộc vào InventoryAvailability hoặc Named Interface đã được công bố. Nó không nên import InventoryRepository hay DefaultInventoryAvailability.

Khi review, kiểm tra:

- Consumer có chỉ dùng package gốc hoặc Named Interface được công bố không?
- Implementation có bị chuyển ra khỏi internal package chỉ để làm test pass không?
- Có class nội bộ nào đang bị nhiều module dùng trực tiếp không?
- Named Interface có chứa đúng hợp đồng ổn định cần công bố không?
- allowedDependencies có phản ánh đúng dependency mà thiết kế cho phép không?

Modifier public của Java không tự biến package thành API công khai của application module. Ngược lại, nếu nhiều consumer đã phụ thuộc vào một kiểu public ở package gốc, thay đổi kiểu đó có thể là một contract change dù nhóm nghĩ nó chỉ là refactor nội bộ.

## 6. Đánh giá thay đổi package và module identity

Đổi package có thể làm thay đổi import, module detection hoặc identifier mặc định. Đừng đánh giá package rename như thao tác đổi tên file đơn thuần.

Trước và sau refactor, so sánh:

| Thuộc tính | Trước | Sau | Cần review |
|---|---|---|---|
| Base package | com.example.shop.inventory | com.example.shop.stock | Java imports và module detection |
| Module identifier | inventory | inventory hoặc stock | Consumer dependency metadata |
| Display name | Inventory Management | Có thể giữ nguyên | Tài liệu và cách gọi nghiệp vụ |
| Named Interface | inventory::events | Identifier/interface mới? | Consumer tham chiếu |
| Public API package | inventory | stock | Source/binary compatibility |

Nếu cần giữ logical identity qua package rename, hãy xem xét id tường minh trên phiên bản Spring Modulith hỗ trợ. displayName chỉ là nhãn trình bày; nó không giữ module identifier và không thay thế package Java.

Ví dụ metadata:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management"
)
package com.example.shop.stock;
~~~

Consumer tiếp tục tham chiếu module identifier:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.order;
~~~

Nếu module identifier thay đổi, review mọi allowedDependencies, Named Interface reference, test và công cụ nội bộ tham chiếu tên cũ.

## 7. Đánh giá source và binary compatibility của Java API

Một thay đổi source-compatible chưa chắc binary-compatible, và ngược lại. Review cần xét cách consumer sử dụng API và cách artifact được triển khai.

Các thay đổi thường gây breaking change:

- Xóa hoặc đổi package của public type.
- Đổi tên public class/interface.
- Xóa method hoặc constructor được consumer gọi.
- Đổi parameter type, return type hoặc checked exception.
- Thu hẹp visibility.
- Đổi interface thành class hoặc ngược lại.
- Thêm abstract method vào interface mà consumer tự implement.
- Đổi generic contract theo cách làm consumer không biên dịch hoặc thay đổi semantics.

Ví dụ API cũ:

~~~java
public interface StockService {

    int getAvailableQuantity(String sku);
}
~~~

API mới:

~~~java
public interface InventoryAvailability {

    Availability availabilityOf(Sku sku);
}
~~~

API mới có thể thể hiện domain tốt hơn, nhưng việc xóa StockService ngay lập tức sẽ phá consumer còn gọi getAvailableQuantity(String). Nếu consumer được biên dịch và triển khai độc lập, đây còn có thể là binary incompatibility.

Một refactor nội bộ chỉ nên được coi là không phá contract khi mọi public signature mà consumer dựa vào vẫn giữ nguyên hoặc có kế hoạch chuyển đổi tương thích.

## 8. Giữ API cũ bằng compatibility facade

Một cách chuyển đổi an toàn là giữ entry point cũ và delegate sang API module mới. Ví dụ:

~~~java
package com.example.shop.inventory;

public interface StockService {

    int getAvailableQuantity(String sku);
}
~~~

API mới:

~~~java
package com.example.shop.inventory;

public interface InventoryAvailability {

    Availability availabilityOf(Sku sku);
}
~~~

Facade tương thích:

~~~java
package com.example.shop.inventory.internal;

import com.example.shop.inventory.Availability;
import com.example.shop.inventory.InventoryAvailability;
import com.example.shop.inventory.StockService;
import com.example.shop.inventory.Sku;
import org.springframework.stereotype.Component;

@Component
class LegacyStockServiceAdapter implements StockService {

    private final InventoryAvailability inventory;

    LegacyStockServiceAdapter(InventoryAvailability inventory) {
        this.inventory = inventory;
    }

    @Override
    public int getAvailableQuantity(String sku) {
        Availability result = inventory.availabilityOf(new Sku(sku));
        return result.availableQuantity();
    }
}
~~~

Đây là ví dụ minh họa; các kiểu Sku và Availability cần được định nghĩa trong API package. Trước khi dùng adapter, review mapping có giữ đúng contract cũ không:

- SKU null hoặc rỗng được xử lý như thế nào?
- SKU không tồn tại trả về 0, null hay ném exception?
- Số lượng âm có thể xuất hiện không?
- Có phân biệt hàng khả dụng, hàng giữ trước và hàng đang chờ nhập không?
- Có giữ nguyên authorization và tenant context không?
- Method cũ có bảo đảm transaction hoặc locking nào không?

Facade không chỉ chuyển lời gọi. Nó phải giữ đúng observable behavior mà caller đang dựa vào. Nếu không thể giữ một semantics cũ, hãy ghi rõ đây là behavior change và đưa vào kế hoạch migration.

## 9. Không để adapter trở thành API thứ hai vĩnh viễn

Compatibility facade hữu ích trong giai đoạn chuyển đổi nhưng làm tăng số đường truy cập. Nếu không có điều kiện kết thúc, consumer mới có thể tiếp tục dùng API cũ.

Kế hoạch adapter cần có:

| Nội dung | Yêu cầu |
|---|---|
| Lý do tồn tại | Caller nào chưa thể chuyển? |
| Consumer owner | Nhóm nào chịu trách nhiệm migration? |
| Deprecation | Khi nào đánh dấu API cũ deprecated? |
| Telemetry | Có thể quan sát số caller còn dùng không? |
| Deadline | Khi nào review lại ngoại lệ? |
| Exit criteria | Điều kiện nào cho phép xóa facade? |

Nếu API cũ được gọi từ nhiều module, chuyển caller theo từng đợt và xác nhận bằng source search, test, log hoặc metric phù hợp. Chỉ xóa adapter khi không còn consumer cần nó và rollback window đã kết thúc.

## 10. Đánh giá Named Interface như một contract

Named Interface cho phép công bố một nhóm package con có chủ đích. Khi consumer phụ thuộc vào nhóm API này, tên interface trở thành một phần của module contract.

Ví dụ provider công bố event API:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.inventory.events;
~~~

Consumer khai báo dependency:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::events"
)
package com.example.shop.order;
~~~

Trong review, kiểm tra:

- Tên Named Interface có ổn định và phản ánh nhóm hợp đồng không?
- Package được công bố có chứa implementation nội bộ không cần thiết không?
- Có consumer nào phụ thuộc vào package con khác ngoài Named Interface không?
- Đổi tên interface có yêu cầu cập nhật tất cả consumer cùng lúc không?
- Có thể giữ tên cũ và tạo interface mới trong giai đoạn chuyển tiếp không?

Đừng expose toàn bộ package chỉ để tránh violation. Công bố phần contract tối thiểu cần cho consumer.

## 11. Đánh giá event contract và consumer cũ

Event giữa module là contract nếu consumer khác module lắng nghe event đó. Review event như một API: tên, payload, semantics, thời điểm publish, thứ tự và khả năng xử lý lặp đều quan trọng.

Ví dụ event hiện tại:

~~~java
public record StockReserved(
        UUID orderId,
        String sku,
        int quantity) {
}
~~~

Refactor muốn thêm reservationId:

~~~java
public record StockReserved(
        UUID orderId,
        String sku,
        int quantity,
        UUID reservationId) {
}
~~~

Việc thêm component vào record có thể làm consumer source cũ không biên dịch vì canonical constructor đã đổi. Với serializer hoặc schema ngoài process, field mới bắt buộc cũng có thể khiến consumer cũ không đọc được payload.

Review các lựa chọn:

- Giữ event cũ và tạo event version mới nếu contract đã được nhiều consumer sử dụng.
- Thêm field tùy chọn có default phù hợp nếu serializer và consumer hỗ trợ additive evolution.
- Dùng constructor overload tương thích cho Java caller khi phù hợp, nhưng không coi đó là giải pháp tự động cho mọi serializer.
- Duy trì consumer có thể đọc cả payload cũ và mới trong giai đoạn chuyển tiếp.
- Chỉ ngừng publish event cũ sau khi đã xác nhận consumer cũ không còn hoạt động.

Ngoài payload, xác nhận semantics:

- Event biểu diễn sự thật đã xảy ra hay command yêu cầu hành động?
- Event được publish trước hay sau commit?
- Consumer có thể nhận duplicate không?
- Có yêu cầu ordering theo orderId hoặc reservationId không?
- Consumer có idempotency key không?
- Việc đổi event có làm thay đổi retry hoặc failure handling không?

Thay đổi tên field nhưng giữ Java type có thể vẫn phá contract JSON. Thay đổi thời điểm publish có thể phá hành vi ngay cả khi payload không đổi.

## 12. Đánh giá HTTP và integration contract

Nếu module cung cấp REST endpoint hoặc adapter tích hợp, contract có thể được sử dụng bởi client ngoài ứng dụng.

Kiểm tra:

- HTTP method và path.
- Request/response field, type, nullability và default.
- Status code và error body.
- Authentication, authorization và tenant context.
- Header, pagination, sorting và filtering.
- Idempotency key và retry semantics.
- Timeout, rate limit và version negotiation.
- OpenAPI hoặc schema được công bố.

Ví dụ, đổi availableQuantity từ integer sang object { "value": 10, "unit": "ITEM" } có thể hợp lý hơn về domain nhưng client cũ không còn đọc được. Hãy version endpoint hoặc giữ response cũ qua adapter trong giai đoạn chuyển tiếp.

Không giả định API HTTP nội bộ không phải contract. Nếu một consumer hoặc script khác đang gọi nó, nó đã trở thành một dependency thực tế cần được review.

## 13. Đánh giá data contract và schema migration

Trong modular monolith, nhiều module có thể cùng truy cập một database. Đổi quyền sở hữu dữ liệu hoặc schema có thể phá code cũ ngay cả khi Java API giữ nguyên.

Ví dụ:

~~~sql
-- Trước refactor
CREATE TABLE INVENTORY_STOCK (
    SKU VARCHAR(80) PRIMARY KEY,
    AVAILABLE_QUANTITY INTEGER NOT NULL
);
~~~

Refactor muốn đổi AVAILABLE_QUANTITY thành ON_HAND và thêm RESERVED:

~~~sql
ALTER TABLE INVENTORY_STOCK ADD COLUMN ON_HAND INTEGER;
ALTER TABLE INVENTORY_STOCK ADD COLUMN RESERVED INTEGER;
~~~

Không nên xóa cột cũ ngay khi code mới được triển khai. Một rollout có thể tạm thời có instance cũ và mới cùng hoạt động.

Dùng expand-and-contract:

1. Expand: thêm cột hoặc bảng mới theo cách không làm code cũ lỗi.
2. Backfill: sao chép và kiểm tra dữ liệu cũ sang cấu trúc mới.
3. Compatibility: triển khai code có thể đọc dữ liệu trong giai đoạn chuyển.
4. Switch: chuyển writer/reader theo một kế hoạch rõ, bảo đảm một nguồn ghi có thẩm quyền.
5. Reconcile: đối soát dữ liệu và theo dõi sai lệch.
6. Contract: chỉ xóa cấu trúc cũ khi không còn code cũ hoặc consumer cần nó.

Review phải xác định:

- Có hai writer cùng cập nhật một nghiệp vụ không?
- Transaction và locking có thay đổi không?
- Backfill có chạy lại an toàn không?
- Có thể rollback application mà vẫn đọc được schema không?
- Dữ liệu đã chuyển có thể đảo ngược hay cần forward-fix?
- Có consumer đọc trực tiếp bảng mà nhóm chưa biết không?

## 14. Đánh giá configuration contract

Configuration cũng là contract giữa ứng dụng với deployment platform và operator. Refactor đổi tên property có thể làm ứng dụng dùng default value mà không báo lỗi rõ ràng.

Ví dụ property cũ:

~~~yaml
inventory:
  reservation:
    enabled: true
~~~

Property mới:

~~~yaml
spring:
  modulith:
    inventory:
      reservation-enabled: true
~~~

Nếu deployment manifest vẫn cung cấp key cũ, ứng dụng mới có thể không nhận giá trị. Review cần xác nhận:

- Property cũ còn được bind trong thời gian chuyển tiếp không?
- Có alias hoặc migration warning không?
- Default value có thay đổi không?
- Profile, environment variable và command-line override có được cập nhật không?
- Secret/config map và deployment automation có được cập nhật đồng bộ không?
- Có log hoặc health indicator giúp phát hiện cấu hình không được nhận diện không?

Không nên xóa property cũ trong cùng release mà operator chưa thể cập nhật cấu hình. Nếu giữ alias, hãy có thời hạn và thông báo deprecation rõ.

## 15. Đánh giá behavioral compatibility

Nhiều breaking change không xuất hiện trong method signature. Một method có thể giữ nguyên tên và kiểu nhưng thay đổi kết quả hoặc side effect.

Review các yếu tố:

| Hành vi | Câu hỏi cần đặt ra |
|---|---|
| Validation | Input null, rỗng, sai định dạng được xử lý giống trước không? |
| Return value | Không tìm thấy dữ liệu trả về gì? |
| Exception | Loại exception, error code và thời điểm ném có đổi không? |
| Transaction | Có còn commit/rollback cùng phạm vi không? |
| Consistency | Kết quả có chuyển từ đồng bộ sang eventual consistency không? |
| Ordering | Event hoặc side effect có đổi thứ tự không? |
| Idempotency | Retry có tạo duplicate không? |
| Authorization | Quyền truy cập và tenant isolation có được giữ không? |
| Side effect | Email, payment, reservation có bị gọi thêm hoặc bỏ sót không? |
| Performance | Latency, query count, lock contention có thay đổi đáng kể không? |

Ví dụ, trước refactor getAvailableQuantity() trả về số lượng sau khi trừ reservation đang hoạt động. Sau refactor, implementation mới chỉ trả về số lượng vật lý trong kho. Chữ ký vẫn là int, nhưng semantics đã thay đổi và có thể khiến order nhận nhiều đơn hơn khả năng đáp ứng.

Đây là behavioral breaking change và cần được review như thay đổi nghiệp vụ.

## 16. Phân tích transaction và consistency

Khi chuyển logic giữa module, nhóm có thể vô tình thay đổi ranh giới transaction.

Trước refactor:

~~~text
PlaceOrder transaction
  ├── save order
  ├── reserve stock
  └── commit both
~~~

Sau refactor:

~~~text
PlaceOrder transaction
  ├── save order
  └── publish OrderSubmitted

Inventory listener
  └── reserve stock later
~~~

Hai luồng không tương đương. Nếu reserve stock thất bại sau khi order đã được commit, hệ thống cần trạng thái nghiệp vụ và quy trình bù trừ rõ ràng.

Review:

- Invariant nào cần được bảo vệ đồng bộ?
- Có thể gọi module API trực tiếp trong cùng process để giữ kết quả đồng bộ không?
- Nếu dùng event, trạng thái trung gian nào được công bố cho caller?
- Consumer retry và duplicate được xử lý thế nào?
- Có cần Event Publication Registry hoặc cơ chế phục hồi tương ứng không?
- Có compensating action khi bước sau thất bại không?

Không chuyển synchronous command thành asynchronous event chỉ để giảm coupling trên sơ đồ. Hãy chứng minh semantics mới phù hợp với nghiệp vụ và được consumer chấp nhận.

## 17. Kiểm tra migration và deprecation plan

Nếu refactor phá contract hiện tại, cần một migration plan rõ thay vì chỉ ghi cập nhật consumer.

Một kế hoạch thường có các giai đoạn:

| Giai đoạn | Provider | Consumer | Tiêu chí |
|---|---|---|---|
| 1. Compatibility | Cung cấp API mới và giữ API cũ | Vẫn dùng API cũ | Cả hai API chạy đúng |
| 2. Migration | Giữ adapter và theo dõi usage | Chuyển từng consumer | Test/telemetry xác nhận consumer mới |
| 3. Deprecation | Cảnh báo API cũ | Không tạo consumer mới | Có owner và deadline |
| 4. Removal | Xóa API cũ sau thời gian tương thích | Tất cả consumer đã chuyển | Không còn usage và rollback window kết thúc |

Deprecation cần chỉ ra:

- API/event/property nào bị deprecated.
- API thay thế là gì.
- Consumer cần thay đổi ra sao.
- Phiên bản hoặc mốc triển khai dự kiến loại bỏ.
- Ai chịu trách nhiệm migration.

Không đánh dấu deprecated mà không có hướng thay thế. Cũng không loại bỏ API cũ chỉ vì source search không còn reference nếu vẫn có client ngoài process hoặc artifact cũ đang chạy.

## 18. Chọn test phù hợp để chứng minh contract

Mỗi loại contract cần một loại bằng chứng khác nhau.

| Test/bằng chứng | Điều chứng minh |
|---|---|
| Compile test của consumer | Source API vẫn sử dụng được |
| Binary compatibility check | Consumer đã biên dịch có thể liên kết với artifact mới |
| Contract test | Request/response hoặc message schema vẫn tương thích |
| Characterization test | Hành vi cũ được bảo toàn |
| Unit test | Quy tắc trong module mới đúng |
| Integration test | Persistence, transaction và event hoạt động đúng |
| Architecture test | Module boundary và dependency hợp lệ |
| Spring context test | Bean và auto-configuration khởi tạo được |
| Migration test | Schema/backfill tương thích với code cũ và mới |
| End-to-end test | Luồng nghiệp vụ hoàn chỉnh vẫn hoạt động |

Với Spring Modulith, architecture test có thể dùng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test này bảo vệ cấu trúc module, nhưng không chứng minh API trả về cùng kết quả, event schema tương thích hoặc database migration an toàn. Cần ghép với test contract và behavioral test tương ứng.

## 19. Đọc diff theo hướng consumer

Khi review pull request, đừng chỉ đọc file đã đổi. Đi từ consumer vào provider:

1. Chọn một consumer đang sử dụng API.
2. Theo dõi import, injection hoặc event subscription của consumer.
3. Xác định kiểu và semantics mà consumer kỳ vọng.
4. Đối chiếu API cũ và API mới.
5. Xem adapter hoặc mapping có giữ contract không.
6. Kiểm tra test của consumer và provider.
7. Kiểm tra migration, config và rollout.

Ví dụ:

~~~text
PlaceOrderService
  -> StockService.getAvailableQuantity(sku)
  -> InventoryAvailability.availabilityOf(Sku)
  -> InventoryRepository
~~~

Review cần xác nhận consumer chỉ nhìn thấy hợp đồng được công bố, adapter giữ semantics cũ và repository vẫn là chi tiết nội bộ của inventory.

Một refactor có thể làm provider đẹp hơn nhưng tăng coupling cho consumer. Hãy đánh giá cả hai phía của dependency.

## 20. Đánh giá khả năng triển khai từng bước

Một thiết kế có thể đúng khi toàn bộ hệ thống được nâng cấp đồng thời nhưng không an toàn trong rolling deployment. Trong thời gian rollout, version cũ và mới có thể cùng tồn tại.

Review các trạng thái:

| Trạng thái triển khai | Câu hỏi |
|---|---|
| Chỉ version cũ | Hợp đồng và schema cũ vẫn hoạt động? |
| Version mới được triển khai một phần | Version cũ và mới có thể giao tiếp với nhau? |
| Toàn bộ version mới | Có thể tắt adapter cũ chưa? |
| Rollback về version cũ | Version cũ có đọc được dữ liệu đã ghi bởi version mới? |
| Sau khi contract schema | Có còn artifact cũ hoặc job cũ cần cấu trúc đã xóa? |

Nếu các version không tương thích trong giai đoạn rollout, cần dùng expand-and-contract, versioned endpoint/event, adapter hoặc chiến lược deploy khác. Không giả định toàn bộ instance đổi version cùng một thời điểm.

## 21. Chuẩn bị rollback và recovery

Rollback code không đồng nghĩa rollback được dữ liệu hoặc side effect.

Review cần phân biệt:

- Code rollback: Có thể triển khai lại artifact trước không?
- Configuration rollback: Property và secret cũ còn hợp lệ không?
- Schema rollback: Cấu trúc dữ liệu cũ có còn tồn tại không?
- Data rollback: Giá trị đã chuyển đổi có thể khôi phục chính xác không?
- Event recovery: Event đã publish có thể được xử lý lại hoặc bù trừ không?
- External side effect: Payment, email hoặc shipment đã gửi có thể đảo ngược không?

Nếu một hành động không thể đảo ngược, cần forward-fix hoặc compensating action. Không viết rollback bằng cách deploy bản cũ nếu bản cũ không đọc được schema mới.

## 22. Dùng bảng compatibility để review thay đổi

Với mỗi hợp đồng bị ảnh hưởng, lập bảng trước/sau:

| Contract | Trước refactor | Sau refactor | Tương thích? | Hành động |
|---|---|---|---|---|
| Java API | StockService.getAvailableQuantity(String) | Giữ facade, delegate API mới | Có nếu behavior giữ nguyên | Giữ trong giai đoạn migration |
| Module API | inventory package gốc | inventory package gốc | Có | Không đổi consumer |
| Event | StockReserved với 3 field | Thêm field mới | Cần xác minh | Additive schema/version strategy |
| Database | AVAILABLE_QUANTITY | ON_HAND, RESERVED | Không tự động | Expand/backfill/switch/contract |
| Config | inventory.reservation.enabled | Property mới | Không nếu bỏ key cũ ngay | Alias và deprecation |
| Behavior | Số lượng đã trừ reservation | Số lượng vật lý | Không | Khôi phục semantics hoặc phê duyệt business change |

Không đánh dấu compatible nếu chưa có bằng chứng. Dùng trạng thái như PASS, CONDITIONAL, BREAKING hoặc UNKNOWN, kèm owner và hành động.

## 23. Ví dụ review một refactor inventory

### Đề xuất thay đổi

Nhóm muốn chuyển StockService dùng chung thành InventoryAvailability, đưa repository vào internal package, đổi event StockReserved và đổi schema để quản lý số lượng on-hand/reserved riêng.

### Nhận định ban đầu

Đề xuất có lợi về ownership: inventory sở hữu logic và repository, order phụ thuộc vào API nghiệp vụ. Tuy nhiên, đề xuất đồng thời tác động Java API, event contract và database schema.

### Nhận xét review

| Hạng mục | Nhận xét | Quyết định |
|---|---|---|
| InventoryAvailability | Hợp đồng mới rõ trách nhiệm | Approve có điều kiện về mapping semantics |
| StockService | Nhiều consumer đang dùng | Giữ facade và deprecate theo kế hoạch |
| InventoryRepository | Đưa vào internal đúng hướng | Kiểm tra consumer không import trực tiếp |
| StockReserved | Thêm field có thể ảnh hưởng record constructor và serializer | Cần compatibility test hoặc versioning |
| Schema inventory | Đổi cột cùng lúc có thể phá instance cũ | Yêu cầu expand-and-contract |
| Reservation behavior | Có thể đổi cách tính available quantity | Cần characterization và business approval |
| allowedDependencies | Consumer phải phụ thuộc module API | Kiểm tra architecture test |

### Điều kiện trước khi approve

1. Có danh sách consumer của StockService và StockReserved.
2. Facade giữ method cũ và semantics cũ.
3. Event consumer cũ đọc được payload trong giai đoạn chuyển.
4. Schema cũ vẫn tồn tại cho tới khi version cũ không còn chạy.
5. Có test cho available quantity, reservation và rollback.
6. ApplicationModules.verify() xác nhận dependency mới tuân thủ module boundary.
7. Có telemetry hoặc bằng chứng khác để xác nhận không còn caller dùng facade.

Review có thể approve phần tạo module API và yêu cầu chỉnh sửa phần event/schema trước khi triển khai. Không nhất thiết phải approve hoặc reject toàn bộ refactor như một khối không thể tách.

## 24. Các dấu hiệu cần yêu cầu chỉnh sửa

| Dấu hiệu trong đề xuất | Vì sao cần dừng review |
|---|---|
| Xóa public API mà không liệt kê consumer | Không biết ai sẽ bị ảnh hưởng |
| Chuyển class sang internal nhưng consumer vẫn import | Module boundary chưa được chuyển thật |
| Đổi record/event field mà không kiểm tra consumer | Có thể phá source hoặc wire contract |
| Đổi transaction sang async mà không mô tả trạng thái trung gian | Business behavior có thể thay đổi |
| Drop column trước khi mọi version cũ ngừng chạy | Rolling deployment có thể fail |
| Đổi property nhưng không cập nhật deployment config | Ứng dụng có thể chạy với default ngoài ý muốn |
| Adapter không có exit criteria | API cũ có thể tồn tại vĩnh viễn |
| Chỉ có unit test, không có contract/integration test | Chưa đủ bằng chứng cho compatibility |
| Rollback chỉ nói deploy bản trước | Không chứng minh schema và dữ liệu tương thích |
| Mở module thành OPEN để bỏ violation | Có thể che giấu việc expose implementation không cần thiết |

## 25. Mẫu nhận xét trong design review

Một nhận xét tốt nêu rõ vị trí, tác động, bằng chứng cần bổ sung và điều kiện chấp nhận.

Ví dụ:

~~~text
Finding: Breaking change trong event contract

Hiện trạng:
StockReserved đang được order và reporting consume.
Refactor thêm reservationId vào record và thay canonical constructor.

Tác động:
Consumer được compile từ source cũ có thể không compile lại.
Consumer chạy với serializer/schema cũ có thể không đọc payload mới.

Yêu cầu:
Giữ contract cũ trong giai đoạn chuyển tiếp hoặc phát hành event
version mới. Bổ sung contract test chứng minh consumer cũ và mới
đọc được payload trong rollout.

Điều kiện đóng:
Tất cả consumer đã chuyển, không còn subscriber dùng event cũ,
và có kế hoạch dừng publish event cũ.
~~~

Ví dụ khác:

~~~text
Finding: Package internal chưa được encapsulate

Hiện trạng:
order.internal.PlaceOrderService import inventory.internal.InventoryRepository.

Tác động:
order phụ thuộc trực tiếp persistence implementation của inventory.

Yêu cầu:
Consumer gọi InventoryAvailability ở API package hoặc Named Interface
đã công bố. Repository được giữ trong inventory.internal.

Điều kiện đóng:
Architecture test pass và không còn import tới inventory.internal
từ module order.
~~~

Tránh nhận xét chung như cần đảm bảo backward compatibility. Hãy nói rõ contract nào, consumer nào, loại incompatibility nào và test nào sẽ chứng minh đã khắc phục.

## 26. Đưa ra quyết định review

Có thể dùng bốn trạng thái:

| Quyết định | Khi nào dùng |
|---|---|
| Approve | Không có breaking change ngoài phạm vi đã chấp nhận; bằng chứng đủ |
| Approve with conditions | Thiết kế đúng nhưng còn điều kiện rõ trước rollout hoặc removal |
| Request changes | Có rủi ro chưa được giải quyết hoặc thiếu bằng chứng quan trọng |
| Reject | Hướng thay đổi phá contract/invariant và không có migration path khả thi |

Nếu approve có điều kiện, ghi rõ điều kiện nào phải hoàn tất trước merge, trước deploy hoặc trước khi xóa API cũ. Không để một điều kiện vận hành quan trọng chỉ nằm trong phần comment không có owner.

## 27. Checklist design review

### Phạm vi và consumer

- [ ] Mục tiêu refactor được mô tả cụ thể.
- [ ] Consumer trực tiếp và gián tiếp đã được liệt kê.
- [ ] Batch, scheduler, integration và external client đã được xem xét.
- [ ] Contract hiện tại được ghi lại trước khi thay đổi.

### Module boundary và API

- [ ] Public API và internal implementation được phân biệt.
- [ ] Consumer chỉ truy cập API package hoặc Named Interface được công bố.
- [ ] allowedDependencies phản ánh đúng dependency.
- [ ] Module identifier và package rename được đánh giá riêng.
- [ ] Không mở module hoặc expose package rộng chỉ để làm test pass.

### Compatibility

- [ ] Source và binary compatibility đã được đánh giá.
- [ ] Behavioral contract được so sánh trước/sau.
- [ ] Event, HTTP và message schema được kiểm tra.
- [ ] Database và configuration contract được kiểm tra.
- [ ] Transaction, consistency, ordering và idempotency không bị đổi ngoài chủ đích.

### Migration và vận hành

- [ ] Có adapter/facade khi cần giữ consumer cũ.
- [ ] Có deprecation, owner, deadline và exit criteria.
- [ ] Schema migration hỗ trợ version cũ/mới cùng tồn tại.
- [ ] Có rollout và rollback plan cho code, config và data.
- [ ] Có metric/log để xác nhận consumer đã chuyển.

### Bằng chứng

- [ ] Compile/consumer compatibility test phù hợp.
- [ ] Contract và characterization test phù hợp.
- [ ] Integration/context test phù hợp.
- [ ] ApplicationModules.verify() bảo vệ module structure.
- [ ] Generated docs và dependency graph phản ánh thiết kế mới.

## 28. Mẫu báo cáo review có thể tái sử dụng

~~~markdown
# Design Review: <Tên refactor>

## Mục tiêu
<Vấn đề kiến trúc và kết quả mong muốn>

## Phạm vi
- Provider/module:
- Consumer:
- API/package/event/data/config bị ảnh hưởng:

## Contract trước và sau
| Contract | Before | After | Compatibility | Evidence |
|---|---|---|---|---|

## Findings
| Severity | Finding | Impact | Required action | Owner |
|---|---|---|---|---|

## Migration plan
1. Compatibility phase:
2. Consumer migration:
3. Deprecation:
4. Removal:

## Verification
- Compile/consumer tests:
- Contract/behavior tests:
- Architecture tests:
- Integration/data tests:
- Rollout/rollback:

## Decision
<Approve / Approve with conditions / Request changes / Reject>

## Conditions and exit criteria
<Điều kiện, owner, deadline và bằng chứng đóng>
~~~

## 29. Kết luận

Đánh giá refactor mà không phá hợp đồng bắt đầu từ consumer và những cam kết mà consumer đang sử dụng. Hãy phân loại source/binary API, behavior, module boundary, event, HTTP, data, configuration và operational contracts; sau đó đánh giá từng thay đổi theo tác động thực tế thay vì chỉ dựa vào việc code có biên dịch.

Spring Modulith giúp làm rõ API package, Named Interface và dependency giữa module, nhưng architecture verification chỉ chứng minh các quy tắc cấu trúc. Muốn bảo vệ contract, cần thêm characterization, consumer/contract, integration và migration tests. Khi có breaking change, giữ adapter hoặc versioned contract trong giai đoạn chuyển tiếp, chuyển consumer theo đợt và chỉ xóa API cũ khi có bằng chứng không còn sử dụng. Một design review tốt kết thúc bằng quyết định rõ, findings có thể hành động, owner, điều kiện rollout và tiêu chí đóng.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Martin Fowler — Branch By Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html)
- [Martin Fowler — Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html)
- [Martin Fowler — Parallel Change](https://martinfowler.com/bliki/ParallelChange.html)
