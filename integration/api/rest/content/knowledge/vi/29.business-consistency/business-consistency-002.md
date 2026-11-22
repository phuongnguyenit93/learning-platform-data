# Đồng bộ hợp đồng phản hồi với thời điểm commit dữ liệu

Khách hàng gọi **POST /v1/orders**, API trả **201 Created**, kèm **Location: /v1/orders/o-918**. Ngay lập tức ứng dụng di động gọi GET vào Location và nhận **404**; sau vài giây đơn mới xuất hiện. Ở trường hợp khác, một giao dịch đã được ghi thành công nhưng kết nối đứt trước khi API gửi response: client thấy timeout, gửi lại POST và tạo thêm đơn. Cả hai đều xuất phát từ việc không xác định rõ **thời điểm thay đổi trở nên bền vững** so với **lời hứa trong HTTP response**.

Bài thuộc chương **Nhất quán nghiệp vụ** của module **INTEGRATION_API_REST**: thiết kế REST API theo resource/URI, method, HTTP status và hợp đồng dữ liệu, kết hợp idempotency, xử lý lỗi, phân quyền và kiểm thử bằng **Java/Spring**. Trọng tâm: phản hồi phải thể hiện đúng điều hệ thống **đã commit**, **chỉ mới tiếp nhận**, hay **chưa thể xác định kết quả**, chứ không phản ánh một thao tác vừa được gọi trong bộ nhớ.

## 1. Mục tiêu và ba khái niệm cần tách biệt

Sau bài này, bạn có thể:

1. Phân biệt **ghi vào bộ nhớ**, **JPA flush**, **database commit**, **publish sự kiện**, **serialize response** và **client nhận đủ response**.
2. Chọn **200/201/202/204**, **409/412**, **5xx** theo kết quả đã được bảo đảm; không hứa hoàn tất quá sớm.
3. Đặt ranh giới **@Transactional** đúng cách trong Spring và hiểu transaction interceptor commit lúc nào.
4. Xử lý hai cửa sổ lỗi: **chưa commit đã lỗi** và **đã commit nhưng HTTP response mất**.
5. Thiết kế **idempotency key, operation record, outbox, version/ETag** để hỗ trợ retry, tác động ngoài DB và cập nhật cạnh tranh.
6. Kiểm tra **read-after-write** với read replica, cache, event projection và phân quyền theo tenant.
7. Kiểm thử xung đột tại commit, mất response, request đồng thời và retry với database thật.

**Transaction commit** là điểm mà hệ quản trị dữ liệu xác nhận các thay đổi của giao dịch theo cấu hình durability/isolation. Nó không có nghĩa **mọi replica, cache, search index hoặc dịch vụ ngoài** đã nhìn thấy thay đổi. **HTTP response** là một thông điệp chạy trên mạng khác với transaction database; không có một giao dịch ACID tự động bao trùm cả việc ghi DB và nhận response ở client.

## 2. Dòng thời gian: điều gì đã xảy ra trước khi trả 201?

~~~mermaid
sequenceDiagram
    autonumber
    participant C as HTTP client
    participant A as Spring Controller
    participant S as Transactional Service
    participant DB as Primary database
    C->>A: POST /v1/orders
    A->>S: create(input, actor)
    S->>DB: BEGIN; validate; INSERT order/outbox
    S->>DB: COMMIT
    DB-->>S: Commit acknowledged
    S-->>A: CreatedOrder(id, version)
    A-->>C: 201 Created + Location + body
    Note over C,DB: Response có thể thất lạc sau commit
~~~

Đây là **đường đi đồng bộ thành công mong muốn**. Với Spring AOP proxy gọi method service có **@Transactional**, transaction interceptor mở giao dịch trước method, chạy logic, rồi **commit trước khi lời gọi qua proxy trả kết quả cho controller**. Nếu commit thất bại theo cách được báo rõ, controller không được tiếp tục tạo 201 từ kết quả service; exception phải đi theo nhánh lỗi.

Các mốc dễ nhầm:

| Mốc | Ý nghĩa thật | Có được tuyên bố đã tạo resource bền vững? |
|---|---|---|
| DTO qua @Valid | Dữ liệu request hợp lệ về cấu trúc | **Chưa** |
| Entity mới được tạo trong Java | Object tồn tại trong RAM | **Chưa** |
| **repository.save** | Entity được quản lý/lên lịch ghi, tùy JPA mapping | **Chưa** |
| **flush** / SQL INSERT gửi tới DB | DML có thể đã chạy, transaction vẫn chưa commit | **Chưa** |
| **COMMIT acknowledged** | Transaction thành công theo bảo đảm database | **Có**, với resource đã được transaction ghi |
| Outbox event còn trong DB | Event đã bền vững cùng transaction | Chỉ bảo đảm **sẽ có dữ liệu để dispatch**, không bảo đảm consumer đã xử lý |
| Kafka/PSP/search index đã cập nhật | Hệ ngoài quan sát được thay đổi | **Chỉ** khi có bằng chứng từ workflow riêng |
| HTTP body đã được serialize | Byte được tạo để gửi | Không bảo đảm client đã nhận hoặc đọc |
| HTTP client nhận 201 | Client quan sát phản hồi thành công | Vẫn cần kiểm tra GET qua đường đọc nhất quán |

**Flush không phải commit.** Constraint, trigger, transaction conflict hoặc kết nối DB có thể khiến commit thất bại sau flush. Trả 201 ngay khi gọi saveAndFlush(), tạo side effect ở hệ ngoài trước commit hoặc trả dữ liệu “đã hoàn tất” từ một callback chạy bất đồng bộ đều là rủi ro.

### 2.1. Hợp đồng HTTP phải theo đúng mức bảo đảm

| Kết quả nghiệp vụ | HTTP thường phù hợp | Cam kết đối với client |
|---|---|---|
| Tạo resource **đã commit** | **201 Created + Location** | Resource mới tồn tại ở URI đã công bố, theo access policy |
| Xử lý thành công, trả representation hiện tại | **200 OK** | Kết quả mô tả operation đã hoàn thành theo contract |
| PUT/PATCH/DELETE đã commit, không trả entity | **204 No Content** | Thay đổi đã được áp dụng, không có response body |
| Đã **nhận bền vững** yêu cầu xử lý sau | **202 Accepted** + job link theo contract | Công việc đang chờ/chưa hoàn tất; không được hứa outcome |
| Trạng thái resource không cho phép thay đổi | **409 Conflict** | Không commit thay đổi xung đột |
| Precondition **If-Match** không thỏa | **412 Precondition Failed** | Không được ghi đè version client không biết |
| Lỗi hạ tầng trước khi commit xác định | **500/503** tùy bản chất | Không khẳng định đã thành công |
| Response mất sau khi commit | Client có thể thấy timeout/502/504 | **Kết quả không xác định ở phía client**; cần tra cứu |

**201 không bắt buộc trả toàn bộ resource**, nhưng **Location** nên trỏ tới tài nguyên chính đã tạo; body nếu có phải khớp danh tính/phiên bản đã commit. URI-reference tương đối là hợp lệ. **202 không bảo đảm job sẽ hoàn tất** và chỉ nên dùng khi hệ thống đã tiếp nhận công việc theo một cơ chế **có thể theo dõi/khôi phục**. **204 không được có response body**.

Không có quy tắc “mọi POST thành công đều 201”: một POST tính toán tức thì có thể trả **200**; một POST kích hoạt job lưu bền vững có thể trả **202**; một lệnh tạo resource hoàn tất giao dịch trả **201**. Cần định nghĩa rõ resource nào tồn tại tại thời điểm response.

## 3. Ranh giới transaction trong Spring MVC

Thiết kế đơn giản và dễ kiểm chứng: **Controller xử lý HTTP/actor/DTO; service quản lý transaction và business invariant; database commit trước khi service trả về controller; controller mới dựng response**.

### 3.1. Request, service, response

Ví dụ Spring Boot 3 / Java 17 / Spring Data JPA. **Các interface và domain class là hợp đồng minh họa**, không phải một project build độc lập; production cần entity/schema, authentication, repository, migration, cấu hình transaction và exception handler phù hợp.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

record CreateOrderRequest(@NotNull UUID cartId) {}
record CreatedOrder(UUID id, String status, long version) {}

interface AuthenticatedActorResolver {
    Actor fromValidatedJwt(Jwt jwt);
}
record Actor(UUID tenantId, UUID userId) {}

@RestController
@RequestMapping("/v1/orders")
class OrderController {
    private final OrderService service;
    private final AuthenticatedActorResolver actors;

    OrderController(OrderService service, AuthenticatedActorResolver actors) {
        this.service = service;
        this.actors = actors;
    }

    @PostMapping
    ResponseEntity<CreatedOrder> create(
            @Valid @RequestBody CreateOrderRequest request,
            @AuthenticationPrincipal Jwt jwt) {
        Actor actor = actors.fromValidatedJwt(jwt);
        // Lời gọi qua Spring proxy: service transaction commit trước khi trả về.
        CreatedOrder created = service.create(actor, request);
        URI location = URI.create("/v1/orders/" + created.id());
        return ResponseEntity.created(location)
                .cacheControl(CacheControl.noStore())
                .body(created);
    }
}
~~~

Ở đây ID là **UUID server sinh** nên segment URI an toàn; đừng ghép chuỗi với path do client tự nhập. **Location tương đối** tránh lấy host từ header không đáng tin khi app đứng sau reverse proxy. Nếu contract bắt absolute URL, dùng **public origin từ cấu hình/forwarded header được trust**. Actor phải suy từ JWT đã xác thực **issuer/audience/lifetime/scopes**, không lấy tenantId từ JSON.

Service transaction và outbox:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

interface OrderStore {
    // Implementation phải ghi order trong transaction hiện tại.
    void insert(UUID id, UUID tenant, UUID user, UUID cart, String status);
}
interface CartStore {
    // 404 nếu cart không tồn tại hoặc không thuộc scope actor.
    void requireVisible(UUID tenant, UUID user, UUID cart);
    // Trả 1 khi claim cart thành công, 0 khi state/scope không còn khớp.
    int markCheckoutIfOpen(UUID tenant, UUID user, UUID cart);
}
interface OutboxStore {
    void insertOrderCreated(UUID eventId, UUID orderId, UUID tenantId);
}
class CartNotAvailable extends RuntimeException {}

@Service
class OrderService {
    private final CartStore carts;
    private final OrderStore orders;
    private final OutboxStore outbox;

    OrderService(CartStore carts, OrderStore orders, OutboxStore outbox) {
        this.carts = carts;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public CreatedOrder create(Actor actor, CreateOrderRequest request) {
        carts.requireVisible(
                actor.tenantId(), actor.userId(), request.cartId());
        int claimed = carts.markCheckoutIfOpen(
                actor.tenantId(), actor.userId(), request.cartId());
        if (claimed != 1) {
            throw new CartNotAvailable();
        }
        UUID id = UUID.randomUUID();
        orders.insert(id, actor.tenantId(), actor.userId(),
                request.cartId(), "PENDING");
        outbox.insertOrderCreated(UUID.randomUUID(), id, actor.tenantId());
        return new CreatedOrder(id, "PENDING", 0L);
    }
}
~~~

**Điều kiện bắt buộc:** ba Store phải dùng **cùng database/transaction manager** và không tự mở transaction riêng. requireVisible tra cart theo **tenant/owner**, trả 404 nếu không được công bố; markCheckoutIfOpen dùng conditional update chống trạng thái đổi sau lookup, trả 0 thì conflict 409. Order cần unique constraint chống trùng cart. **@Transactional** mặc định cần lời gọi qua Spring proxy; **self-invocation** có thể bỏ qua interceptor. **CreatedOrder không tới controller cho tới khi proxy xử lý xong commit**.

Đối với order với version do DB cấp, phải lấy/thiết kế version đúng trước khi dựng ETag/body: trường version=0 trong ví dụ chỉ minh họa trạng thái ban đầu. Trigger hoặc column được DB tự thay đổi có thể đòi một readback trong transaction, và **đọc giá trị không biến flush thành commit**. Đừng trả ETag từ object trong RAM nếu representation sau commit có dữ liệu khác.

### 3.2. SQL để bảo vệ state trước khi commit

~~~sql
-- Cùng transaction với INSERT orders/outbox.
UPDATE carts
   SET status = 'CHECKING_OUT'
 WHERE id = :cart_id
   AND tenant_id = :tenant_id
   AND owner_id = :user_id
   AND status = 'OPEN';
-- affected_rows phải = 1; nếu 0 thì rollback, không phát 201.

-- DDL: chạy một lần qua schema migration, KHÔNG chạy trong request:
CREATE UNIQUE INDEX uq_order_cart_per_tenant
    ON orders(tenant_id, cart_id);
~~~

Nếu hai request cùng checkout một cart, chỉ một request được claim trạng thái hoặc ghi unique record thành công. **DB constraint là lớp bảo vệ cuối cùng**, còn check-then-act không có atomic update vẫn có race. Khi database từ chối ghi **tại flush hoặc commit**, transaction phải rollback và API ánh xạ lỗi theo ngữ cảnh (thường **409**, hoặc trả kết quả cũ nếu đúng idempotency key), không trả 201 trước khi kiểm chứng.

### 3.3. Những chỗ đặt transaction sai

~~~java
// SAI: phát 201 khi công việc mới chỉ được xếp trên executor RAM.
@PostMapping("/bad/orders")
ResponseEntity<Void> createBad(@RequestBody CreateOrderRequest input) {
    executor.execute(() -> orderService.createLater(input));
    return ResponseEntity.created(URI.create("/v1/orders/unknown")).build();
}

// SAI: flush chỉ đẩy SQL tới DB, không có nghĩa transaction đã commit.
@Transactional
void createBadly() {
    repository.saveAndFlush(order);
    externalPaymentClient.charge(card); // DB rollback không rollback PSP.
}
~~~

Nếu API thật sự nhận job bất đồng bộ, phải **persist job/operation đủ bền vững** trước khi trả **202 + Location**, có worker và trạng thái theo dõi. Khi gọi PSP/queue từ transaction, có thể tạo **dual-write**: DB rollback nhưng PSP đã nhận; hoặc DB commit nhưng publish event thất bại. Dùng transactional outbox và cơ chế idempotent downstream ở phần sau.

## 4. Hai cửa sổ lỗi và giới hạn của HTTP response

Một client chỉ nhìn thấy **response hoặc sự thiếu vắng response**; nó không thấy thời điểm COMMIT trực tiếp. Vì vậy cần phân biệt hai câu hỏi: **server thực tế đã làm gì?** và **client có bằng chứng gì?**

### 4.1. Lỗi trước khi commit hoàn tất

Ví dụ constraint được kiểm tra ở commit, database hết connection hoặc transaction bị rollback do xung đột. Nếu DB báo chắc chắn transaction **không commit**, API có thể trả lỗi đúng nguyên nhân: 409 cho business conflict, 412 cho điều kiện If-Match không thỏa, 503/500 cho dependency hoặc lỗi server. **Không được trả Location tới resource mà transaction đã rollback**.

Nhưng ở một số lỗi kết nối ngay trong lúc commit, server **không chắc** DB đã commit hay chưa vì mất phản hồi từ DB. Trong trường hợp đó, không tuyên bố “rollback chắc chắn”. Hệ thống phải dùng **operation identity, transaction record và query đối soát** để phân biệt kết quả sau khi kết nối phục hồi.

### 4.2. Commit thành công, response không tới client

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A as API
    participant DB as Database
    C->>A: POST /v1/orders (Idempotency-Key: k-31)
    A->>DB: COMMIT order o-918 + operation k-31
    DB-->>A: COMMIT OK
    A--xC: 201 Lost / connection closed
    Note over C: Timeout: outcome UNKNOWN
    C->>A: Retry same key + same payload
    A->>DB: Read committed operation k-31
    DB-->>A: Result for o-918
    A-->>C: Replayed result, no new order
~~~

**DB commit và HTTP delivery không thể gộp thành một transaction atomic chỉ bằng Spring @Transactional.** Việc client gửi ACK HTTP hoặc dùng TCP thành công cũng không tương đương commit giữa các hệ thống. Nếu server cố chờ client xác nhận trước khi commit, client có thể nhận “thành công dự kiến” rồi server rollback; nếu commit trước khi gửi, client vẫn có thể mất response. Bài toán phải được giải bằng **idempotency + khả năng tra kết quả**, không bằng thay đổi thứ tự hai thao tác để giả lập exactly-once.

### 4.3. Sau commit vẫn có thể phát 500

Spring MVC thường serialize JSON sau khi controller đã trả object và transaction service hoàn thành. Nếu **Jackson serialization** lỗi sau khi commit, hoặc proxy đóng kết nối khi đã có byte response, client có thể thấy lỗi/response dở dang dù order đã tồn tại. **Không thể rollback DB chỉ vì serialize thất bại sau commit.**

Hãy trả DTO nhỏ, được kiểm tra serialization, không expose lazy JPA entity để serializer vô tình truy vấn sau transaction. Nếu response streaming/SSE hoặc trả file lớn, đừng giữ transaction DB mở suốt thời gian truyền dữ liệu; tách snapshot/trạng thái bền vững với lifecycle của HTTP stream.

### 4.4. Ma trận diễn giải kết quả

| Quan sát ở API/client | Điều được biết | Hành động đúng |
|---|---|---|
| Service trả thành công **sau commit** | Local DB commit đã được xác nhận | Tạo 200/201/204 đúng contract |
| Validation/authorization lỗi trước ghi | Chưa thực hiện side effect | 400/401/403/404 theo policy |
| Unique constraint tại commit từ chối | Operation này không commit như dự định | 409 hoặc tra operation đã tồn tại |
| Mất kết nối DB khi commit | Có thể **không xác định** outcome | Đối soát bằng operation ID |
| HTTP client timeout | Client không biết commit hay chưa | **Không retry POST với key mới** |
| HTTP 201 đã nhận, GET đọc replica nhận 404 | Read path chưa bắt kịp, hoặc access-policy lỗi | Khắc phục read consistency, không cho rằng 201 không có hiệu lực |
| Đã commit local order nhưng chưa gửi event | Outbox còn chờ | Giữ trạng thái domain PENDING/ASYNC, theo dõi delivery |

**HTTP status 5xx hoặc gateway 504 không phải bằng chứng chắc chắn “server chưa làm gì”**. Đối với operation không idempotent, client phải đọc trạng thái hoặc retry **cùng key**. Đây là điểm phải ghi rõ trong OpenAPI và tài liệu SDK.

## 5. Idempotency: ràng buộc response với một logical operation

**Idempotency-Key** không phải magic header do HTTP tự cấp semantics. API và client cần thống nhất **scope, TTL, fingerprint, trạng thái xử lý và cách replay**. Ví dụ:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: 5f0ed1ca-481e-4aaf-94f6-409fe4ec3ec8
Content-Type: application/json

{"cartId":"e72e0410-b765-4c55-a031-2ec29101b31a"}
~~~

Một record operation tối thiểu:

| Trường | Vai trò |
|---|---|
| **tenant_id, actor_id, operation_type, idem_key** | Namespace tránh rò kết quả giữa tenant/principal |
| **request_fingerprint** | Phân biệt retry đúng payload với key trùng payload khác |
| **state** | IN_PROGRESS, COMPLETED, FAILED_FINAL hoặc trạng thái domain rõ ràng |
| **resource_id, http_status/headers/body** | Tra và phát lại kết quả đã được quyết định |
| **created_at, expires_at** | TTL và chính sách dọn sau khi không còn cần replay |

**Một transaction** cần ghi order và kết quả idempotency tương ứng, hoặc thiết kế claim/complete có thể phục hồi không để lại kết quả sai sau crash. **Unique constraint** trên scope key ngăn hai request đồng thời cùng chiếm một operation; cần xử lý trạng thái **IN_PROGRESS** (chờ có deadline, trả status/409 theo contract, hoặc 202 khi có resource operation thật) mà không phát hai side effect.

~~~sql
CREATE UNIQUE INDEX uq_order_operation
    ON idempotent_operations
       (tenant_id, actor_id, operation_type, idem_key);

-- Trong cùng transaction tạo order:
-- 1. Claim operation key hoặc kiểm tra record đã commit.
-- 2. Kiểm tra fingerprint và bất biến cart/owner.
-- 3. INSERT orders, INSERT outbox, UPDATE operation COMPLETED
--    với resource_id/status/response metadata.
-- 4. COMMIT trước khi controller nhận CreatedOrder.
~~~

**Cùng key + cùng payload:** trả lại kết quả/định danh **đã commit**, không trừ quota hoặc tạo đơn lần hai. **Cùng key + payload khác:** trả **409 Conflict** (hoặc lỗi riêng được tài liệu hóa), không âm thầm dùng key đó để tạo resource mới. **Key khác nhưng cùng cart đã checkout:** phải có unique business constraint; Idempotency-Key không thay bất biến “mỗi cart được checkout một lần”.

Nếu DB phát **DataIntegrityViolationException** ở commit, đừng catch rồi tiếp tục đọc trong transaction có thể đã bị đánh dấu rollback-only; hãy để transaction kết thúc, sau đó kiểm tra operation record bằng một transaction đọc riêng. Nếu record vừa được tạo ở request cạnh tranh còn đang in-flight, cần chính sách chờ có giới hạn hoặc trả trạng thái đang xử lý, không đoán lỗi đó chắc là retry hợp lệ.

**TTL hết không được phá bất biến domain**. Sau khi operation key hết hạn, request mới có thể được xem là operation mới; constraint theo cart/payment/beneficiary vẫn phải chặn tạo trùng không hợp lệ. Khi thao tác có side effect tài chính, TTL/khả năng đối soát phải đáp ứng thời gian retry của client và downstream, không chỉ 30 giây tùy ý.

### 5.1. Response replay và cache khác nhau

Replay idempotent có thể trả lại **201 + cùng Location và body**, hoặc HTTP status phù hợp khác nếu contract công bố rõ. Đừng tự tạo ETag/Location mới từ đồng hồ request hiện tại trong khi response cũ cần ổn định. **HTTP cache** là vấn đề riêng: một POST response được lưu cho idempotency nội bộ **không đồng nghĩa** proxy/CDN được phép cache công khai. Với đơn hàng có dữ liệu cá nhân, dùng **Cache-Control: no-store** và kiểm tra identity cho mọi replay.

### 5.2. Bảng lỗi client cần biết

| Thao tác | Retry sau timeout | Điều kiện an toàn |
|---|---|---|
| **GET** | Thường được phép | Giới hạn attempt/backoff; dữ liệu có thể đã đổi |
| **PUT** | Idempotent theo semantics method, nhưng vẫn có race | ETag/If-Match hoặc version khi cần ngăn lost update |
| **DELETE** | Idempotent theo intended effect | Response lặp có thể 204 hoặc 404 theo contract |
| **POST tạo order** | Không tự động nếu chưa có dedupe | **Cùng Idempotency-Key**, fingerprint và tra kết quả |
| **POST charge/refund** | Chỉ khi PSP hỗ trợ idempotency hoặc query status | Cùng operation ID trên tất cả các hop |

Client không được xem timeout là kết quả âm tính rồi tạo key mới. Retry của SDK, gateway và service cần **chung budget**, có jitter và deadline, tránh tạo retry storm. Số lần gửi HTTP có thể nhiều hơn một, nhưng **logical operation phải có nhận dạng ổn định**.

## 6. Transactional outbox và ranh giới hệ thống ngoài DB

Ngay cả khi **orders** đã commit, thao tác “đã thanh toán”, “đã gửi email”, “đã index search” hay “đã trừ tồn kho ở ERP” là câu hỏi **khác** nếu chúng nằm ở service ngoài. Tổ hợp **DB transaction + Kafka publish + HTTP response** không tự tạo atomicity xuyên hệ thống.

~~~mermaid
flowchart LR
    A["POST /v1/orders"] --> T["Local DB transaction"]
    T --> O["orders: PENDING"]
    T --> E["outbox: OrderCreated"]
    T --> C["COMMIT"]
    C --> R["201 Created: order PENDING"]
    C --> P["Outbox dispatcher"]
    P --> B["Broker / consumer"]
    B --> S["Downstream processing"]
    S --> U["Order status updated later"]
~~~

Thực tế, **orders + outbox** được ghi trong **cùng transaction**. Dispatcher sau commit đọc những event chưa gửi, publish có retry và đánh dấu kết quả. Dùng **unique event_id, idempotent consumer hoặc inbox dedupe** vì event có thể được gửi hơn một lần. Nếu dùng callback **@TransactionalEventListener(AFTER_COMMIT)** để gọi broker trực tiếp, callback **không phải durable queue**: process có thể chết giữa commit và publish. Dùng outbox khi mất event là không chấp nhận được.

**Hợp đồng quan trọng:** có thể trả **201** cho resource order **PENDING đã commit**, nhưng **không** trả 200 với “paymentSucceeded=true” trước khi PSP xác nhận. Nếu bản chất resource chưa tạo và hệ thống chỉ nhận một lệnh sẽ xử lý sau, trả **202** với URI của job/operation đã được lưu bền vững là lựa chọn rõ hơn.

### 6.1. 202 và operation status

~~~http
HTTP/1.1 202 Accepted
Location: /v1/operations/op-918
Retry-After: 3
Cache-Control: no-store
Content-Type: application/json

{"operationId":"op-918","state":"QUEUED"}
~~~

Client có thể GET operation để xem **QUEUED, RUNNING, SUCCEEDED, FAILED**, kết quả hoặc link đến resource mới. **Retry-After** hướng dẫn polling, không bảo đảm job hoàn thành sau 3 giây. Không trả 202 nếu lệnh chỉ nằm trên queue RAM hoặc publish broker thất bại và không có record để khôi phục. Khi sử dụng outbox, nên ghi operation/job và outbox trong cùng transaction trước khi xác nhận 202.

### 6.2. Saga và bù trừ

Nếu workflow dài gồm đặt chỗ → thanh toán → xuất kho, mỗi service có transaction riêng. **Saga** điều phối bước và **compensation** như hủy giữ chỗ/hoàn tiền khi một bước sau thất bại. Compensation là một **nghiệp vụ mới**, không phải rollback ACID của các side effect trước đó: có thể mất thời gian, thất bại tạm thời hoặc cần xử lý thủ công. API phải có trạng thái trung gian **PENDING/PROCESSING/COMPENSATING/FAILED** phản ánh đúng mức nhất quán, không chỉ boolean “success”.

## 7. Read-after-write: 201 xong GET lại phải thấy gì?

Một tình huống phổ biến: POST ghi vào **primary**, GET được load balancer đưa tới **read replica** đang lag. Client nhận 201 nhưng GET từ Location nhận 404. Về mặt local DB, đơn đã commit; về trải nghiệm/hợp đồng, client thấy API tự mâu thuẫn.

Biện pháp theo yêu cầu nhất quán:

| Phương án | Lợi ích | Đánh đổi |
|---|---|---|
| Đọc resource vừa tạo từ **primary** | Read-your-writes rõ ràng cho GET sau POST | Tăng tải primary |
| Session stickiness hoặc **consistency token** | Định tuyến tới replica đã bắt kịp vị trí commit | Cần hạ tầng theo dõi LSN/version |
| Chờ replica đạt watermark | Client thấy dữ liệu nhất quán khi đã bắt kịp | Tăng độ trễ và cần timeout |
| **202 + job status** | Trung thực khi resource chưa sẵn sàng theo contract | Client phải polling |
| Trả **201 + representation đã commit** | Client có dữ liệu ngay mà không GET | Những GET sau vẫn cần consistency policy |

Không dùng **sleep(500ms)** như bằng chứng replica đã đồng bộ; replica lag thay đổi theo tải. Không hứa mọi edge/CDN đã invalidated ngay khi primary commit; nếu cần read-after-write, cần cấu hình cache invalidation/ETag hoặc bỏ qua cache theo contract.

**Bảo mật:** GET có thể trả 404 vì tenant/owner không có quyền, hoàn toàn khác 404 do replica lag. Không “sửa” bằng cách chuyển mọi GET sau 201 thành truy vấn không kiểm tra quyền. **Location phải trỏ resource có scope hợp lệ**, và request GET phải xác thực/ủy quyền lại. URI lộ ra không phải bearer credential.

### 7.1. ETag, If-Match và version đúng thời điểm

Một client sửa order đã đọc ETag:

~~~http
PUT /v1/orders/o-918 HTTP/1.1
If-Match: "order-v4"
Content-Type: application/json
Authorization: Bearer <access-token>

{"shippingAddressId":"addr-13"}
~~~

Server phải thực hiện kiểm tra version **trong cùng thao tác ghi nguyên tử**, chẳng hạn:

~~~sql
UPDATE orders
   SET shipping_address_id = :address_id,
       version = version + 1
 WHERE id = :order_id
   AND tenant_id = :tenant_id
   AND owner_id = :user_id
   AND version = :expected_version;
-- Nếu affected_rows = 0: phân biệt 404 theo scope hoặc 412 do If-Match.
~~~

**If-Match dùng strong comparison** theo RFC 9110; ETag trong ví dụ là identifier của representation/version được thiết kế phù hợp, không tự động là raw DB version trong mọi API. Nếu row bị thay đổi sau client đọc, cập nhật phải bị từ chối bằng **412** trước khi commit. Với yêu cầu **If-Match bắt buộc** nhưng thiếu, contract có thể dùng **428 Precondition Required**.

Sau **commit thành công**, server có thể trả **204 + ETag mới** hoặc **200 + body mới**, theo hợp đồng. **Không trả version mới từ một update dự kiến chưa commit**. Nếu client lặp lại cùng conditional PUT sau response mất, lần thứ hai có thể nhận 412 vì version đã tăng ở lần đầu; điều đó **không chứng minh lần đầu thất bại**. Client nên GET lại trạng thái và đối soát.

## 8. Xử lý lỗi, transaction propagation và bảo mật

### 8.1. Exception handler phải phân biệt lỗi nghiệp vụ và hạ tầng

Spring MVC có thể dùng **@RestControllerAdvice** để chuẩn hóa **Problem Details (RFC 9457)**. Ví dụ một cart đã đóng:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/cart-not-available",
  "title": "Cart cannot be checked out",
  "status": 409,
  "code": "CART_NOT_AVAILABLE"
}
~~~

~~~java
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class OrderProblemAdvice {
    @ExceptionHandler(CartNotAvailable.class)
    ResponseEntity<ProblemDetail> conflict(CartNotAvailable error) {
        ProblemDetail body = ProblemDetail.forStatus(
                HttpStatus.CONFLICT);
        body.setType(URI.create(
                "https://api.example.test/problems/cart-not-available"));
        body.setTitle("Cart cannot be checked out");
        body.setProperty("code", "CART_NOT_AVAILABLE");
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .contentType(MediaType.valueOf("application/problem+json"))
                .cacheControl(CacheControl.noStore())
                .body(body);
    }
}
~~~

**Không catch mọi DataIntegrityViolationException rồi trả 409**: một lỗi constraint có thể đến từ bug/schema sai, chứ không phải business conflict đã xác định. Map qua tên invariant/operation cụ thể; lỗi dependency có thể là **500/503**, và nếu mất phản hồi DB ngay ở COMMIT thì outcome có thể không chắc chắn. **Không tự động retry transaction ghi** khi chưa có operation identity. Lỗi do authorization phải là **401/403/404 theo policy**, không phải 500 hay 409 để che việc thiếu quyền.

### 8.2. Cấu hình @Transactional phải khớp cách gọi thật

Các bẫy cần kiểm chứng:

- **AOP proxy/self-invocation:** method gọi từ cùng instance vào method @Transactional có thể không đi qua proxy; dùng bean service riêng hoặc cách quản lý transaction được Spring hỗ trợ.
- **Rollback rule:** Spring mặc định rollback trên **RuntimeException/Error**, không mặc định mọi checked exception; khai báo rollbackFor khi thật sự cần, hoặc dùng exception domain nhất quán. Không nuốt exception rồi trả kết quả “thành công”.
- **Propagation REQUIRES_NEW:** một phần việc có thể commit độc lập dù outer transaction sau đó rollback. Đừng dùng cho ghi business chính nếu cần tính nguyên tử chung.
- **Async thread:** transaction imperative thường gắn với thread hiện tại; **@Async/CompletableFuture** ở thread khác không tự chia sẻ transaction; với R2DBC/reactive dùng **reactive transaction context** tương ứng.
- **afterCommit hook:** callback chạy **sau commit** vẫn có thể lỗi và ảnh hưởng request, nhưng không thể rollback thay đổi đã commit. Không thay durable outbox bằng callback gửi broker thuần túy.
- **Thời điểm trả entity:** tránh cho Jackson serialize lazy JPA association sau transaction. Dùng DTO kiểm soát rõ fields, cache và masking.

Nếu transaction kết thúc nhưng controller tiếp tục gọi API ngoài để lấy dữ liệu trang trí response, lỗi ở bước đó có thể khiến client thấy 5xx **sau local commit**. Quyết định một trong hai: tách downstream khỏi đường thành công đồng bộ, trả dữ liệu chỉ từ commit đã bảo đảm, hoặc khai báo rõ trạng thái **partial/pending** theo contract.

### 8.3. Quyền, cache và dữ liệu phản hồi

Một **Idempotency-Key đoán được** không được phép mở kết quả của actor khác. Khi tra operation, scope bằng **tenant, principal và operation type**, so fingerprint an toàn và kiểm tra lại quyền theo yêu cầu. Đừng đưa raw token, key, account number, SQL error, internal transaction ID vào URL/Problem Details/log.

Sau commit, response và **Location/ETag** phải cùng resource được phép công bố; tránh dùng **Host/X-Forwarded-Host** do client điều khiển để dựng absolute URL (Host header poisoning). Với dữ liệu cá nhân, thường dùng **Cache-Control: no-store** để tránh shared cache hoặc browser giữ thông tin không mong muốn. **BOLA/IDOR** không thể sửa bằng việc dùng UUID khó đoán.

## 9. Kiểm thử hợp đồng đúng tại điểm commit

Unit test trả về **CreatedOrder** có thể chứng minh mapping DTO, **không** chứng minh database đã commit. Để kiểm tra transaction, dùng database thật hoặc môi trường gần production; test in-memory khác DB production có thể không phát hiện **deferred constraints, isolation, trigger và serialization behavior**.

| Tình huống | Thiết lập/fault injection | Bằng chứng cần có |
|---|---|---|
| POST tạo đơn thông thường | HTTP integration test + DB thật | 201 + Location, row và outbox đã commit, GET trả dữ liệu |
| Validation sai trước transaction | Request thiếu cartId | 400, không tạo order/outbox |
| Khác tenant/owner | JWT tenant A, cart tenant B | 403/404 theo contract, không đổi cart |
| Hai request cùng cart | Barrier đồng thời trên primary DB | Tối đa một order; cart không checkout hai lần |
| Unique/constraint lỗi ở COMMIT | Deferred constraint hoặc fault point phù hợp DB | **Không có 201**; toàn transaction rollback khi xác định |
| Thất bại giữa order và outbox | Throw exception trước commit | Không có order “mồ côi” hoặc event “mồ côi” |
| Commit rồi client mất response | Proxy ngắt kết nối sau commit | Retry cùng key không tạo đơn/trừ quota lần hai |
| Cùng key + payload khác | Gửi hai POST khác body | 409/contract error, không lộ kết quả khác |
| GET ngay sau 201 | Route qua replica/cache thật | Đúng read-after-write policy, không 404 giả do lag |
| If-Match cũ | Hai client cùng sửa version | Một commit, request kia 412; version/ETag nhất quán |
| Worker outbox retry event | Consumer nhận event lặp | Consumer dedupe, business effect tối đa một lần |
| Lỗi serialize sau commit | Inject MessageConverter failure | Server log/metric phát hiện, client đối soát bằng operation ID |

Ví dụ test HTTP hợp đồng với **MockMvc**, giả định project có endpoint GET order, Spring Security JWT fixture và database isolation theo tenant:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderCommitContractIT {
    @Autowired MockMvc mvc;

    @Test
    void createdOrderCanBeReadImmediately() throws Exception {
        UUID cart = fixtureOpenCartForCurrentActor();
        var result = mvc.perform(post("/v1/orders")
                .with(jwt().jwt(t -> t.subject("user-1")
                        .claim("tenant_id", "tenant-1"))
                        .authorities(
                                new SimpleGrantedAuthority("SCOPE_orders:write"),
                                new SimpleGrantedAuthority("SCOPE_orders:read")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"cartId\":\"" + cart + "\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andReturn();

        String location = result.getResponse().getHeader("Location");
        mvc.perform(get(location)
                .with(jwt().jwt(t -> t.subject("user-1")
                        .claim("tenant_id", "tenant-1"))
                        .authorities(
                                new SimpleGrantedAuthority("SCOPE_orders:read"))))
            .andExpect(status().isOk());
    }
}
~~~

Đây là **test skeleton**, chưa chạy độc lập: cần helper **fixtureOpenCartForCurrentActor**, GET endpoint, claims/scope khớp issuer/audience và test database setup. Mock JWT chỉ giúp test route, **không chứng minh chữ ký và token validation production**. Mẫu này kiểm tra request **sau khi nhận 201**; để kiểm chứng commit real, đọc row từ **connection khác sau HTTP request**, không bọc toàn bộ test trong **@Transactional** rồi vô tình dựa trên dữ liệu chưa commit của chính test.

### 9.1. Test race và commit uncertainty

Hai request nên được kích hoạt bằng **barrier** (không chỉ hai lời gọi tuần tự) trên hai transaction độc lập, kiểm tra số order, version và event outbox cuối cùng. Với deferred constraint, dùng DB engine/constraint thực tế: lỗi có thể chỉ xuất hiện ở commit, **không** phải saveAndFlush. Với lỗi giữa **COMMIT được DB xử lý** và HTTP response được client nhận, đặt fault ở proxy/network sau commit rồi cho client retry cùng key và query operation.

Đừng dùng một mock repository trả “success” để kết luận hệ thống giải quyết mất response. Test ngoài gateway/proxy/replica cần bao phủ **502/504, load balancer routing, cache staleness, header Location** và retry của SDK. Đồng thời đo tỉ lệ **committed-but-unacknowledged, idempotency replay, outbox lag, rollback, commit latency, 409/412/503**; tránh log PII.

## 10. Bài tập: đúng thời điểm nào được trả 201?

Một API **POST /v1/tickets** nhận request giữ vé. Server ghi booking ở PostgreSQL, gửi sự kiện qua Kafka để hệ thanh toán xử lý; client có thể gửi lại POST sau timeout. Hệ thống chạy ba replica, GET vé đi qua một read replica thường lag khoảng vài trăm ms. Mỗi ghế chỉ được giữ bởi một booking đang hiệu lực.

Hãy:

1. Quyết định **201 hay 202** khi booking đã commit nhưng chưa thanh toán; mô tả trạng thái và URI tương ứng.
2. Chỉ ra điểm **commit** trước khi tạo Location; tại sao saveAndFlush chưa đủ?
3. Thiết kế SQL/unique constraint hoặc conditional update chống hai request giữ cùng ghế.
4. Bố trí **operation ID, Idempotency-Key, fingerprint** và record kết quả để POST replay không tạo booking thứ hai.
5. Thiết kế **outbox** để Kafka publish lỗi không làm mất thông điệp; nêu cách consumer dedupe.
6. Giải quyết GET **404 sau 201** do replica lag mà không làm lộ booking tenant khác.
7. Lập tối thiểu sáu ca test gồm commit failure, concurrent booking, response-lost-after-commit và conditional update stale.

**Gợi ý:** có thể trả **201** cho booking **PENDING_PAYMENT đã commit** vì booking resource thực sự tồn tại, còn thanh toán là trạng thái về sau; hoặc **202 + /v1/operations/{id}** nếu mới chỉ nhận tác vụ chưa tạo booking. Hai lựa chọn đều hợp lý khi **hợp đồng nói đúng điều đã bền vững**. Ghi booking + outbox + idempotency result trong cùng transaction; không chỉ gửi Kafka rồi trả 201. GET nhất quán qua primary hoặc consistency token, vẫn kiểm tra owner/tenant. Timeout không chứng minh booking thất bại.

## 11. Checklist và tham khảo

- [ ] Response **200/201/204** chỉ tuyên bố kết quả đã được xác nhận theo contract; **202** chỉ tiếp nhận bền vững.
- [ ] Service transaction **commit trước khi** controller dựng response; biết rõ ranh giới Spring proxy, rollback và serialization.
- [ ] Không nhầm **save/flush với commit**, không publish tác động ngoài DB như thể cùng một transaction ACID.
- [ ] Có ranh giới rõ cho **commit uncertain** và **response lost after commit**; retry không tạo logical operation mới.
- [ ] Idempotency key có scope/fingerprint/TTL và kết quả đã commit; DB có business unique constraint.
- [ ] Outbox và consumer dedupe bảo vệ sự kiện; trạng thái domain không hứa downstream đã hoàn tất quá sớm.
- [ ] **Location/ETag/If-Match** khớp resource/version và quyền; GET sau 201 có consistency policy.
- [ ] Kiểm thử DB thật, deferred commit failure, race, replica lag, proxy/network loss và cross-tenant.

Tham khảo: **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html; **Spring Transaction Management**, https://docs.spring.io/spring-framework/reference/data-access/transaction.html; **Spring Declarative Transaction Rollback**, https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html; **Spring MVC**, https://docs.spring.io/spring-framework/reference/web/webmvc.html; **Transactional Outbox Pattern**, https://microservices.io/patterns/data/transactional-outbox.html.

**Kết luận:** Hợp đồng HTTP phải phản ánh **mốc commit và phạm vi nhất quán mà server thực sự bảo đảm**. Local DB commit không đồng nghĩa hệ ngoài đã hoàn tất, còn HTTP timeout không chứng minh transaction thất bại. Đặt transaction đúng, lưu operation identity, dùng outbox và bảo vệ read-after-write sẽ giúp API trả kết quả trung thực, chống trùng và có thể đối soát sau sự cố.
