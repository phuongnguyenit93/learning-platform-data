# Invalidation khi state đổi

Cache giúp REST API giảm truy vấn database, giảm thời gian serialize representation và giảm tải cho service phía sau. Nhưng một representation chỉ còn đúng khi dữ liệu và trạng thái mà nó mô tả chưa thay đổi. Khi đơn hàng chuyển từ PENDING sang APPROVED, response HAL đã cache có thể vẫn chứa trạng thái cũ, link approve đã hết hiệu lực hoặc thiếu link ship vừa trở nên khả dụng. Vì vậy, thiết kế cache phải đi cùng chiến lược invalidation (vô hiệu hóa cache) khi state thay đổi.

Trong Spring HATEOAS, cần xem cả dữ liệu lẫn hypermedia metadata là một phần của representation. Một state transition có thể làm thay đổi field, link relation, affordance, collection membership, kết quả tìm kiếm và các resource tổng hợp. Xóa cache của một key đơn lẻ thường chưa đủ.

## Cache nào đang giữ representation?

Một request GET có thể đi qua nhiều lớp cache:

~~~text
Client / browser
      |
      v
CDN / reverse proxy / gateway cache
      |
      v
Spring MVC + Spring HATEOAS
      |
      +---- Spring Cache / application cache
      |
      v
Repository / database
~~~

Các lớp này có cơ chế và phạm vi invalidation khác nhau:

| Loại cache | Ví dụ | Cách invalidation thường dùng |
| --- | --- | --- |
| HTTP cache ở client | Browser cache response GET | Cache-Control, ETag, Last-Modified và revalidation. |
| Shared HTTP cache | CDN, reverse proxy, gateway | TTL, purge API, surrogate key/tag hoặc revalidation. |
| Application cache | Spring Cache với Caffeine, Redis hoặc provider khác | Evict key, evict toàn bộ region hoặc cập nhật value. |
| Data/query cache | Hibernate second-level cache, cache kết quả truy vấn | Cơ chế invalidation của persistence provider và transaction. |

Annotation @CacheEvict của Spring Cache chỉ tác động đến cache manager mà ứng dụng cấu hình. Nó không tự xóa response đã lưu ở browser, CDN hay reverse proxy. Tương tự, Cache-Control: no-cache không gọi Redis để xóa key application cache. Cần xác định mỗi representation được cache ở đâu và giao trách nhiệm invalidation cho đúng lớp.

## State transition làm thay đổi những representation nào?

Giả sử order o-42 chuyển từ PENDING sang APPROVED. Các response phụ thuộc vào state đó có thể gồm:

| Representation | Thay đổi có thể xảy ra |
| --- | --- |
| /api/orders/o-42 | Field status, updatedAt, ETag và các link hành động thay đổi. |
| /api/orders | Order có thể đổi vị trí, đổi nhóm hoặc không còn thuộc filter hiện tại. |
| /api/orders?status=PENDING | Order cần biến mất khỏi kết quả. |
| /api/orders?status=APPROVED | Order cần xuất hiện trong kết quả. |
| /api/customers/c-7/orders | Thống kê hoặc danh sách order của khách hàng thay đổi. |
| /api/dashboard | Tổng số order chờ duyệt và đã duyệt thay đổi. |

Đây là quan hệ phụ thuộc giữa dữ liệu domain và các representation. Trước khi chọn cache key, hãy lập danh sách URI hoặc cache tag bị ảnh hưởng bởi mỗi loại state transition.

Không phải mọi endpoint đều cần purge đồng bộ. Một danh sách ít quan trọng có thể chấp nhận stale trong vài giây; màn hình phê duyệt hoặc số dư tài chính có thể yêu cầu revalidation ngay. Chính sách phụ thuộc mức độ nhạy cảm và tác động của dữ liệu.

## Hypermedia cũng có thể stale

Giả sử order đang ở trạng thái PENDING. Server công bố:

~~~json
{
  "id": "o-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    },
    "approve": {
      "href": "https://shop.example/api/orders/o-42/approval"
    },
    "cancel": {
      "href": "https://shop.example/api/orders/o-42/cancellation"
    }
  }
}
~~~

Sau khi order được phê duyệt, representation mới có thể là:

~~~json
{
  "id": "o-42",
  "status": "APPROVED",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    },
    "ship": {
      "href": "https://shop.example/api/orders/o-42/shipment"
    }
  }
}
~~~

Nếu cache vẫn trả response cũ, client có thể hiển thị hành động approve đã hết hiệu lực và không biết hành động ship mới. Vì vậy, cache invalidation của Spring HATEOAS phải tính đến _links, _embedded, affordances và page metadata, không chỉ các field trong DTO.

Link cũ không được xem là quyền thực hiện hành động. Endpoint vẫn phải xác thực, kiểm tra authorization và kiểm tra state tại thời điểm command. Nếu client theo một link cũ, server có thể trả 409 Conflict khi state không còn cho phép transition đó.

## HTTP cache tự invalidation được đến đâu?

HTTP caching có một quy tắc quan trọng: khi cache nhận response thành công cho một request dùng method không an toàn (ví dụ POST, PUT, PATCH hoặc DELETE), cache phải invalidation URI mục tiêu của request đó theo RFC 9111. Cache có thể invalidation thêm URI trong Location hoặc Content-Location khi đáp ứng điều kiện cùng origin.

Quy tắc này hữu ích nhưng có phạm vi giới hạn. Nếu client gọi:

~~~http
POST /api/orders/o-42/approval HTTP/1.1
Host: shop.example
Content-Type: application/json

{"comment":"Đã kiểm tra"}
~~~

cache có thể invalidation URI /api/orders/o-42/approval. Nó không tự biết rằng các URI /api/orders/o-42, /api/orders, /api/orders?status=PENDING và /api/dashboard cũng đã thay đổi. HTTP cache không hiểu quan hệ domain giữa các resource.

Do đó, không nên kỳ vọng một POST tự động xóa mọi GET representation liên quan. Với các URI phụ thuộc state, cần dùng một hoặc kết hợp các cơ chế:

- Response không cache hoặc yêu cầu revalidation cho resource nhạy cảm.
- Purge URI/tag ở CDN hoặc reverse proxy sau khi transaction commit.
- Evict application cache keys liên quan.
- Dùng ETag/Last-Modified để client phát hiện representation đã đổi.
- Dùng TTL ngắn làm giới hạn thời gian stale khi purge bị trễ.

## Chọn chính sách Cache-Control

Cache-Control quyết định client và shared cache có thể lưu, dùng lại hay phải kiểm tra lại response:

| Directive | Ý nghĩa thực tế | Trường hợp thường dùng |
| --- | --- | --- |
| max-age=60 | Response còn fresh trong 60 giây theo cache freshness model. | Dữ liệu công khai ít thay đổi. |
| private | Chỉ private cache được lưu; shared cache không được dùng response này. | Representation phụ thuộc người dùng. |
| no-cache | Có thể lưu nhưng phải revalidate trước khi dùng lại. | Resource cần kiểm tra freshness mỗi lần tái sử dụng. |
| no-store | Cache không được lưu response. | Dữ liệu nhạy cảm hoặc không chấp nhận lưu trữ. |
| must-revalidate | Khi stale, cache phải revalidate trước khi dùng lại. | Dữ liệu cần tránh phục vụ stale response theo điều kiện directive. |
| s-maxage=30 | Freshness lifetime cho shared cache. | Điều khiển CDN/proxy riêng với private cache. |

no-cache không đồng nghĩa với no-store: response vẫn có thể được lưu nhưng phải revalidate. private cũng không có nghĩa response không stale; nó chỉ giới hạn shared cache. Chọn directive theo dữ liệu và mô hình cache thực tế.

Ví dụ Spring MVC đặt response private và bắt buộc revalidation:

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AccountController {

    private final AccountService accountService;

    AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @GetMapping("/api/account")
    ResponseEntity<AccountModel> account() {
        AccountModel model = accountService.currentAccountModel();

        return ResponseEntity.ok()
                .cacheControl(CacheControl.maxAge(0, TimeUnit.SECONDS)
                        .cachePrivate()
                        .mustRevalidate())
                .body(model);
    }
}
~~~

Trong ví dụ, AccountService và AccountModel là kiểu ứng dụng do dự án định nghĩa; service được inject qua constructor. Representation của tài khoản có thể khác theo principal, vì vậy response không được dùng trong shared cache. max-age=0 khiến response hết freshness ngay và cần revalidation khi private cache muốn dùng lại. Nếu dữ liệu không nên được lưu trên thiết bị, dùng CacheControl.noStore() thay vì chỉ đặt private.

## ETag và revalidation sau state change

ETag là validator định danh một phiên bản representation. Client lưu response cùng ETag, sau đó gửi If-None-Match trong request GET. Nếu representation chưa đổi, server có thể trả 304 Not Modified; nếu đã đổi, server trả representation mới và ETag mới.

Ví dụ response trước khi order đổi state:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Cache-Control: private, no-cache
ETag: "order-o-42-v7"

{
  "id": "o-42",
  "status": "PENDING"
}
~~~

Client revalidate:

~~~http
GET /api/orders/o-42 HTTP/1.1
Host: shop.example
If-None-Match: "order-o-42-v7"
Accept: application/hal+json
~~~

Sau khi order chuyển sang APPROVED, validator cần thay đổi. Server trả 200 OK với body và ETag mới thay vì 304:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "order-o-42-v8"

{
  "id": "o-42",
  "status": "APPROVED"
}
~~~

ETag phải thay đổi khi bất kỳ phần nào của representation thay đổi. Nếu ETag chỉ dựa trên version của order nhưng link còn phụ thuộc cấu hình route, quyền người dùng hoặc trạng thái liên quan khác, ETag có thể không còn đại diện đầy đủ cho representation. Với representation cá nhân hóa, hãy bảo đảm validator được tạo riêng cho biến thể tương ứng hoặc tắt shared caching.

Một cách đơn giản cho strong ETag là hash bytes representation sau serialize. Cách này chính xác với nội dung được serialize nhưng có thể tốn CPU và chỉ phát hiện thay đổi sau khi đã dựng body. Một ETag dựa trên aggregate version hiệu quả hơn nếu mọi thay đổi ảnh hưởng representation đều tăng version đó và các dependency bên ngoài được kiểm soát.

Ví dụ controller dùng revision của aggregate làm ETag:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
class OrderController {

    private final OrderService orderService;
    private final OrderAssembler assembler;

    OrderController(OrderService orderService, OrderAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/api/orders/{id}")
    ResponseEntity<OrderModel> one(@PathVariable UUID id) {
        Order order = orderService.findById(id);
        OrderModel model = assembler.toModel(order);
        String etag = "\"order-" + id + "-v" + order.getVersion() + "\"";

        return ResponseEntity.ok()
                .eTag(etag)
                .body(model);
    }
}
~~~

Ví dụ này chỉ đúng khi order.getVersion() tăng mỗi lần bất kỳ dữ liệu hoặc link/affordance nào trong representation phụ thuộc vào order thay đổi. Nếu representation chứa thông tin từ customer, shipment hoặc policy có version độc lập, cần kết hợp validator của các dependency hoặc hash representation hoàn chỉnh.

Spring MVC có thể xử lý conditional request với ETag/Last-Modified qua WebRequest.checkNotModified(...) hoặc các cơ chế tương ứng. Khi dùng, hãy kiểm tra validator trước khi thực hiện công việc dựng body tốn kém và bảo đảm validator phản ánh đúng representation mà client được nhận.

## Spring Cache và invalidation theo key

Application cache có thể lưu dữ liệu hoặc representation để tránh truy vấn và mapping lặp lại. Ví dụ cache một order theo ID:

~~~java
import java.util.UUID;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    private final OrderRepository orderRepository;

    OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Cacheable(cacheNames = "ordersById", key = "#orderId")
    public Order findById(UUID orderId) {
        return orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));
    }
}
~~~

Khi state thay đổi, evict key tương ứng:

~~~java
import java.util.UUID;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderCommandServiceWithCacheEvict {

    private final OrderRepository orderRepository;

    OrderCommandServiceWithCacheEvict(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    @CacheEvict(cacheNames = "ordersById", key = "#orderId")
    public void approve(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));
        order.approve();
    }
}
~~~

Đây là một cách minh họa riêng cho evict bằng annotation. Khi dùng cùng transaction, cần kiểm tra thứ tự advisor như phần trên; ví dụ transactional event ở phần tiếp theo là lựa chọn khác khi muốn ràng buộc invalidation vào AFTER_COMMIT. Không khai báo hai lớp cùng tên trong một package.

@CacheEvict mặc định evict sau khi method invocation thành công (beforeInvocation = false). Tuy nhiên, nếu method đang chạy trong transaction, thứ tự advisor của cache và transaction có thể khiến eviction xảy ra trước khi transaction commit. Với yêu cầu invalidation chỉ sau commit, không nên dựa vào thứ tự interceptor mặc định; hãy dùng event listener ở phase AFTER_COMMIT hoặc cơ chế đồng bộ transaction rõ ràng.

Nếu cache lưu collection/search result, một thay đổi order có thể ảnh hưởng nhiều key. Có thể evict cả cache region:

~~~java
@CacheEvict(cacheNames = "orderSearch", allEntries = true)
public void invalidateOrderSearchResults() {
}
~~~

Đoạn trên minh họa thao tác evict region; trong ứng dụng thực tế nên gọi nó từ một Spring bean riêng hoặc dùng CacheManager trong listener. allEntries = true đơn giản nhưng có thể xóa nhiều dữ liệu hơn cần thiết. Với hệ thống lớn, tag hoặc dependency index giúp invalidation có mục tiêu hơn.

Lưu ý: Spring Cache annotations hoạt động qua Spring proxy. Gọi một method @CacheEvict từ method khác trong cùng instance (self-invocation) thường không đi qua proxy, nên annotation không được áp dụng như mong đợi. Tách thao tác cache ra bean được inject hoặc dùng CacheManager trực tiếp.

## Chỉ invalidation sau khi transaction commit

Nếu evict cache trước khi transaction commit, request GET đồng thời có thể đọc database state cũ rồi nạp lại giá trị cũ vào cache ngay sau eviction. Kết quả là transaction commit xong nhưng cache vẫn chứa state cũ.

Luồng an toàn hơn:

1. Command tải aggregate và kiểm tra state hiện tại.
2. Command thay đổi state và lưu dữ liệu trong transaction.
3. Transaction commit thành công.
4. Event listener evict application cache và gửi yêu cầu purge HTTP cache.
5. Request đọc tiếp theo lấy state mới và tạo representation mới.

Spring hỗ trợ transactional event:

~~~java
import java.util.UUID;

public record OrderStateChanged(
        UUID orderId,
        UUID customerId) {
}
~~~

Command phát event trong transaction:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderCommandService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher events;

    OrderCommandService(
            OrderRepository orderRepository,
            ApplicationEventPublisher events) {
        this.orderRepository = orderRepository;
        this.events = events;
    }

    @Transactional
    public void approve(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.approve();
        events.publishEvent(
                new OrderStateChanged(order.getId(), order.getCustomerId()));
    }
}
~~~

Listener xử lý sau commit:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderCacheInvalidator {

    private final CacheManager cacheManager;

    OrderCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderStateChanged event) {
        cacheManager.getCache("ordersById").evict(event.orderId());
        cacheManager.getCache("ordersByCustomer").evict(event.customerId());
        cacheManager.getCache("orderSearch").clear();
        cacheManager.getCache("dashboard").clear();
    }
}
~~~

Listener chỉ chạy sau khi transaction commit. Nếu transaction rollback, listener không thực hiện invalidation. Trong production, kiểm tra cache region có tồn tại trước khi evict hoặc khai báo đầy đủ cache names trong cấu hình.

Transactional application event không phải message bền vững và chỉ được phát trong process hiện tại. Nếu ứng dụng chạy nhiều instance với local cache như Caffeine, listener trên một node không tự xóa cache của các node còn lại. Hãy dùng cache phân tán, publish invalidation tới mọi node hoặc phát sự kiện qua message broker.

Nếu tiến trình chết sau khi database commit nhưng trước khi listener hoàn thành, invalidation có thể bị mất. Với hệ thống cần bảo đảm event không bị thất lạc, hãy ghi một outbox record trong cùng transaction với thay đổi domain; worker đọc outbox, thực hiện evict/purge và đánh dấu event đã xử lý. Event cần idempotent để có thể retry an toàn.

## Invalidation CDN và reverse proxy

Spring Cache không điều khiển CDN. Nếu response được lưu ở CDN, ứng dụng cần cơ chế purge mà CDN hỗ trợ, ví dụ:

- Purge một URL cụ thể.
- Purge theo surrogate key hoặc cache tag.
- Gắn tag order-o-42, customer-c-7, orders vào response; sau transition purge các tag liên quan.
- Đặt TTL ngắn và dùng revalidation nếu provider không hỗ trợ purge chính xác.

Ví dụ về ý tưởng tag (header cụ thể phụ thuộc CDN):

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Cache-Control: public, max-age=30, s-maxage=120
Surrogate-Key: order-o-42 customer-c-7 orders
~~~

Khi order đổi state, publisher gửi purge cho order-o-42, customer-c-7 và các tag collection/search liên quan. Đây là extension riêng của CDN, không phải header HTTP chuẩn mà mọi cache đều hiểu.

Nếu API trả representation phụ thuộc quyền, không đưa nó vào shared cache công khai chỉ để dễ purge. Hãy dùng private/no-store hoặc cấu hình shared cache key và authorization rất cẩn thận. Purge không thay thế phân quyền.

## Invalidation bằng dependency tags

Khi một resource xuất hiện trong nhiều representation, có thể mô hình hóa dependency:

~~~text
Order o-42 changes
   |
   +--> /api/orders/o-42
   |
   +--> /api/orders
   |
   +--> /api/orders?status=PENDING
   |
   +--> /api/orders?status=APPROVED
   |
   +--> /api/customers/c-7/orders
   |
   +--> /api/dashboard
~~~

Nếu mỗi URI có cache key độc lập, application cần biết key nào bị ảnh hưởng. Hai cách phổ biến:

**Evict theo key cụ thể:** event mang order ID, customer ID và các aggregate liên quan. Listener evict cache key tương ứng. Cách này hiệu quả khi dependency rõ và số key nhỏ.

**Evict theo region/tag:** event mang tag, cache index tìm mọi key chứa tag đó rồi purge. Cách này linh hoạt cho nhiều query/filter nhưng cần quản lý index và dọn tag cũ.

Không nên tạo tag quá rộng cho mọi state change nếu cache có traffic lớn; purge toàn bộ collection có thể làm cache stampede khi nhiều client đồng thời tải lại. Có thể stagger refresh, dùng TTL ngắn, stale-while-revalidate ở nơi chấp nhận được hoặc chủ động warm các key phổ biến sau commit.

## Cache stampede và request đồng thời

Khi evict một key phổ biến, nhiều request có thể cùng truy vấn database và dựng representation mới. Đây là cache stampede. Một số biện pháp:

- Dùng single-flight/request coalescing để một request nạp cache, các request khác chờ kết quả.
- Dùng refresh-ahead hoặc stale-while-revalidate cho dữ liệu không nhạy cảm.
- Thêm jitter vào TTL để tránh nhiều key hết hạn cùng lúc.
- Warm cache sau commit cho một số representation có traffic cao.
- Giới hạn concurrency và bảo vệ database bằng timeout/bulkhead.

Không giữ stale hypermedia action quá lâu nếu hành động có thể gây tác động nghiệp vụ. Với representation có affordance quan trọng, revalidation hoặc TTL ngắn thường phù hợp hơn stale-while-revalidate kéo dài.

## Cache key phải tính đến biến thể representation

Cùng một resource URI có thể trả representation khác nhau theo:

- Accept (HAL, HAL-FORMS hoặc JSON khác).
- Ngôn ngữ qua Accept-Language.
- Principal/tenant nếu field hoặc link phụ thuộc quyền.
- Query parameter như filter, sort, page và projection.
- Host/proxy prefix nếu absolute link được tạo theo forwarded headers.

Cache key phải phân biệt những biến thể ảnh hưởng body. HTTP cache dùng Vary để chỉ ra request headers liên quan, ví dụ:

~~~http
Vary: Accept, Accept-Language
~~~

Không dùng Vary thay cho thiết kế cache key của Spring Cache; application cache phải tự bao gồm mọi input ảnh hưởng kết quả. Với representation cá nhân hóa, ưu tiên Cache-Control: private hoặc no-store trừ khi shared cache được cấu hình rõ để phân tách người dùng/tenant.

Nếu query result cache chỉ key theo status nhưng bỏ tenantId, dữ liệu tenant này có thể được trả cho tenant khác. Đây là lỗi phân tách dữ liệu nghiêm trọng, không chỉ là vấn đề stale data.

## Xử lý state transition và optimistic locking

Hai command đồng thời có thể cùng đọc order PENDING. Một request phê duyệt, request còn lại hủy. Nếu cả hai đều thành công dựa trên state cũ, cache invalidation sau đó không thể sửa được lỗi nghiệp vụ.

Domain command cần bảo vệ transition bằng transaction và concurrency control. Ví dụ entity dùng optimistic locking:

~~~java
import java.util.UUID;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
class Order {

    @Id
    private UUID id;

    @Version
    private long version;

    // Domain state và các phương thức transition.
}
~~~

@Version giúp persistence provider phát hiện cập nhật đồng thời. Khi conflict xảy ra, ứng dụng cần trả lỗi phù hợp, thường là 409 Conflict hoặc 412 Precondition Failed nếu client dùng If-Match. Chỉ publish event invalidation sau khi transaction commit thành công; transaction rollback không được phát event state change như thể đã cập nhật.

## Kiểm thử invalidation

Test cần chứng minh cache được nạp, state thay đổi, cache cũ bị evict sau commit và request tiếp theo thấy representation mới. Có thể dùng Spring Cache với cache manager test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.CacheManager;

@SpringBootTest
class OrderCacheInvalidationTest {

    @Autowired
    OrderQueryService queryService;

    @Autowired
    OrderCommandService commandService;

    @Autowired
    CacheManager cacheManager;

    @Test
    void evictsOrderCacheAfterApproval() {
        UUID orderId = UUID.fromString("00000000-0000-0000-0000-000000000042");

        Order before = queryService.findById(orderId);
        assertThat(before.getStatus()).isEqualTo(OrderStatus.PENDING);
        assertThat(cacheManager.getCache("ordersById").get(orderId)).isNotNull();

        commandService.approve(orderId);

        assertThat(cacheManager.getCache("ordersById").get(orderId)).isNull();

        Order after = queryService.findById(orderId);
        assertThat(after.getStatus()).isEqualTo(OrderStatus.APPROVED);
    }
}
~~~

Test giả định fixture orderId tồn tại ở trạng thái PENDING và transaction của command commit trước khi assertion chạy. Không đánh dấu test method @Transactional nếu muốn kiểm tra listener AFTER_COMMIT theo transaction thực của command; test transaction bao ngoài có thể trì hoãn commit đến cuối test và làm kết quả khác kỳ vọng.

Order, OrderStatus, OrderRepository, OrderNotFoundException, OrderModel, AccountService và các DTO trong ví dụ là kiểu domain/ứng dụng do dự án định nghĩa. Các đoạn code được tách theo từng tình huống; không ghép những lớp cùng tên thành nhiều khai báo trong một package.

Test cho HTTP cache cần kiểm tra validator và cache headers:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/orders/o-42")
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(header().exists("ETag"))
    .andExpect(header().string("Cache-Control", org.hamcrest.Matchers.containsString("no-cache")));
~~~

Sau state transition, test nên gửi If-None-Match với ETag cũ và xác nhận server không trả 304 cho representation mới. Nếu response là personalized, kiểm tra private hoặc no-store theo chính sách.

Với CDN purge hoặc outbox, kiểm tra event chứa đúng các tag/URI phụ thuộc, retry không purge sai tenant và event chỉ được phát sau commit. Không cần gọi CDN thật trong unit test; dùng adapter giả lập và kiểm tra command gửi đến provider.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ POST tự xóa mọi GET liên quan | Collection, search và dashboard vẫn stale. | Purge các URI/tag phụ thuộc sau commit. |
| Dùng @CacheEvict để xóa CDN | Browser/proxy cache không thay đổi. | Tách application cache invalidation và HTTP cache purge. |
| Evict trước khi transaction commit | GET đồng thời có thể nạp lại state cũ. | Xử lý event ở AFTER_COMMIT hoặc dùng outbox. |
| Chỉ cache DTO field, bỏ qua link | Affordance cũ vẫn xuất hiện sau state transition. | Invalidate toàn bộ representation có hypermedia metadata. |
| ETag chỉ dựa trên entity version trong khi link phụ thuộc dữ liệu khác | Client nhận 304 cho representation đã thay đổi. | Validator phải bao phủ mọi dependency ảnh hưởng body. |
| Dùng cache key thiếu tenant/filter/projection | Trả nhầm dữ liệu hoặc kết quả truy vấn. | Đưa mọi biến thể ảnh hưởng representation vào cache key. |
| Xóa toàn bộ cache cho mọi command | Cache miss tăng và có thể tạo stampede. | Evict key/tag có mục tiêu khi có thể. |
| Dựa vào TTL dài để giải quyết mọi invalidation | Client tiếp tục thấy link/action đã lỗi thời. | Chọn TTL theo rủi ro và kết hợp revalidation/purge. |
| Phát event trước commit | Transaction rollback nhưng cache đã bị xóa hoặc consumer nhận state chưa tồn tại. | Publish event trong transaction và xử lý sau commit. |

## Quy trình thiết kế invalidation

Với mỗi command làm thay đổi state, hãy thực hiện các bước:

1. Xác định aggregate và state transition có thể xảy ra.
2. Liệt kê detail, collection, search, projection và dashboard representation phụ thuộc.
3. Xác định lớp cache của từng representation: Spring Cache, browser, CDN hay proxy.
4. Chọn chính sách freshness: TTL, no-cache, private, no-store, ETag hoặc Last-Modified.
5. Sau commit, evict application keys và phát purge event cho shared HTTP cache khi cần.
6. Bảo đảm event bền vững bằng outbox nếu invalidation phân tán cần độ tin cậy cao.
7. Kiểm thử state mới, ETag mới, link/affordance mới và các URI collection/search bị ảnh hưởng.
8. Theo dõi cache hit/miss, purge latency, stale response và lỗi nạp lại sau eviction.

## Nguyên tắc thiết kế

- Xem link, affordance và embedded resources là một phần của representation cần invalidation.
- Lập dependency giữa domain state và mọi URI/representation phụ thuộc.
- Phân biệt Spring Cache với HTTP cache ở browser, proxy và CDN.
- Không kỳ vọng unsafe HTTP method tự invalidation mọi URI liên quan.
- Dùng ETag/Last-Modified để revalidate; validator phải phản ánh mọi thay đổi của representation.
- Evict application cache sau transaction commit, không trước khi dữ liệu được xác nhận.
- Dùng transactional outbox khi invalidation phân tán cần độ tin cậy cao.
- Dùng tag/purge có mục tiêu cho collection, search và aggregate response ở shared cache.
- Thiết kế cache key theo tenant, principal, media type, filter và projection khi chúng ảnh hưởng body.
- Giữ endpoint command kiểm tra lại quyền và state dù client đang dùng link đã cache.
- Đặt TTL làm giới hạn stale cuối cùng và theo dõi độ trễ invalidation.

Invalidation khi state đổi bảo đảm cache không tiếp tục đại diện cho một trạng thái nghiệp vụ đã lỗi thời. Với Spring HATEOAS, điều đó bao gồm cả dữ liệu, link và affordance được công bố cho client. Khi xác định đúng dependency, phân biệt các lớp cache, evict sau commit và dùng validator hoặc purge phù hợp, API có thể giữ hiệu năng mà vẫn phản ánh đúng khả năng hiện tại của resource.
