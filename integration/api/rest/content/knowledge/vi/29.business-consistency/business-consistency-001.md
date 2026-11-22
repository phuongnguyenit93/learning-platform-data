# Ranh giới giao dịch trong một yêu cầu API

Khi một REST API nhận `POST /api/v1/orders`, việc lưu đơn hàng có thể cần đồng thời giữ hàng trong kho, tạo dòng chi tiết và ghi lịch sử trạng thái. Nếu một bước lỗi nhưng các bước trước đã được ghi bền vững, hệ thống có thể tạo đơn hàng không có hàng hoặc trừ tồn kho mà không có đơn. **Ranh giới giao dịch (transaction boundary)** xác định những thay đổi nào phải thành công cùng nhau và khi nào chúng trở nên có hiệu lực.

Trong mô-đun **INTEGRATION_API_REST**, người học thiết kế API từ resource, URI, phương thức, mã trạng thái HTTP và hợp đồng dữ liệu. Ở chương **Nhất quán nghiệp vụ**, một hợp đồng API đúng còn phải trả lời câu hỏi: **khi client nhận kết quả, trạng thái nghiệp vụ đã được commit đến đâu, những bất biến nào được bảo vệ, và điều gì xảy ra nếu request bị lỗi hoặc bị gửi lại?** Bài này tập trung vào giao dịch **trong phạm vi một yêu cầu API** với Java/Spring và cơ sở dữ liệu quan hệ, đồng thời chỉ rõ giới hạn khi cần phối hợp với hệ thống khác.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt vòng đời HTTP request với vòng đời database transaction và xác định thời điểm commit/rollback.
2. Chọn ranh giới `@Transactional` ở tầng application service nhằm bảo vệ một **bất biến nghiệp vụ**.
3. Giải thích vì sao kiểm tra rồi cập nhật trong hai bước dễ gây race condition; dùng atomic update, khóa hoặc optimistic locking khi thích hợp.
4. Phân biệt giao dịch một database với gọi HTTP, broker, email hoặc thanh toán bên ngoài; hiểu khi nào cần transactional outbox hoặc quy trình nhiều bước.
5. Thiết kế HTTP status, idempotency và kiểm thử rollback, đồng thời xử lý trường hợp dữ liệu đã commit nhưng client chưa nhận response.

## 2. Một HTTP request không tự động là một giao dịch

HTTP là giao thức trao đổi request/response. Database transaction là đơn vị công việc mà hệ quản trị cơ sở dữ liệu xử lý theo các thuộc tính ACID: **atomicity**, **consistency**, **isolation** và **durability**. Hai phạm vi này liên quan nhưng **không đồng nhất**:

- Request có thể bị từ chối ở authentication, validation hoặc authorization **trước khi** bắt đầu transaction.
- Một request đọc dữ liệu có thể dùng một hoặc nhiều truy vấn; không nhất thiết mở một transaction ghi kéo dài cho toàn request.
- Một transaction ở tầng service có thể hoàn tất và **commit trước khi** controller dựng/serialize HTTP response.
- Request có thể gọi nhiều service, mỗi service dùng một transaction khác nhau. Không có đảm bảo toàn bộ request sẽ atomic nếu không thiết kế rõ.
- Một request có thể gửi job bất đồng bộ và trả `202 Accepted` trong khi nghiệp vụ chưa hoàn tất.
- Client mất kết nối hoặc gặp timeout **không chứng minh** database đã rollback; server có thể đã commit thành công.

### 2.1. Phạm vi thường dùng trong Spring MVC

~~~mermaid
sequenceDiagram
    participant C as Client
    participant H as Controller
    participant S as Transactional service
    participant D as Database
    C->>H: POST /api/v1/orders
    Note over H: Authenticate, validate HTTP contract
    H->>S: placeOrder(command)
    Note over S,D: Transaction manager bắt đầu transaction
    S->>D: UPDATE inventory có điều kiện
    D-->>S: Số dòng được cập nhật
    S->>D: INSERT purchase_order
    Note over S,D: Flush và COMMIT
    D-->>S: Commit thành công
    S-->>H: OrderReceipt
    H-->>C: 201 Created + Location
~~~

`@Transactional` đặt ở phương thức service được gọi **qua Spring proxy**. Proxy mở transaction trước khi chạy logic và commit sau khi method hoàn thành bình thường. Nếu commit thất bại, proxy ném exception thay vì trả kết quả thành công cho controller. Controller chỉ nên gửi `201 Created` khi service đã trả về bình thường và transaction đã commit.

Ví dụ trên mô tả thứ tự phổ biến, nhưng **việc HTTP response đến được client là sự kiện độc lập**. Response có thể mất trên mạng sau commit, việc serialize body cũng có thể lỗi sau commit, hoặc gateway timeout khi server vẫn đang xử lý. Do đó không được suy ra “client không nhận `201` thì database chưa ghi”.

### 2.2. Phân biệt tính chất ACID với nhất quán nghiệp vụ

| Khái niệm | Ý nghĩa trong một thao tác tạo đơn | Giới hạn cần nhớ |
| --- | --- | --- |
| Atomicity | Giữ tồn kho và tạo đơn cùng commit hoặc cùng rollback | Chỉ bao phủ các tài nguyên tham gia **cùng transaction** |
| Consistency | Mọi trạng thái đã commit thỏa mãn constraint và bất biến | Database không tự biết mọi quy tắc kinh doanh; phải thiết kế constraint và logic |
| Isolation | Request đồng thời không tạo kết quả sai do can thiệp lẫn nhau | Phụ thuộc isolation level, kiểu truy vấn, khóa và constraint |
| Durability | Sau khi commit thành công, dữ liệu vẫn được lưu theo cam kết của database | Không đồng nghĩa một email đã gửi hoặc một API đối tác đã phản hồi |

Ranh giới giao dịch nên đi theo **một hành động nghiệp vụ nhất quán**: chẳng hạn “giữ hàng và tạo đơn chờ xử lý”, “chuyển tiền giữa hai tài khoản trong cùng database”, hoặc “xác nhận phiếu nhập và tăng tồn kho”. Không nên chọn ranh giới đơn giản bằng số lượng dòng code, số repository hay toàn bộ vòng đời HTTP.

## 3. Xác định bất biến trước khi viết annotation

Giả sử nghiệp vụ đặt hàng quy định:

1. Số lượng yêu cầu phải dương và SKU tồn tại trong phạm vi bán hàng được phép.
2. `inventory.available` không âm.
3. Nếu một đơn ở trạng thái `PENDING` đã được tạo thì số lượng tương ứng đã được giữ; nếu không tạo đơn, số lượng không bị giữ.
4. Mỗi `clientReference` của một khách hàng xác định tối đa một đơn; ràng buộc này giúp giảm trùng lặp, nhưng chưa phải cơ chế idempotency hoàn chỉnh.
5. Đơn hàng của tenant này không được tác động đến tồn kho của tenant khác.

Ta có thể biểu diễn các dữ liệu liên quan:

| Bảng | Các trường tiêu biểu | Ràng buộc cần có |
| --- | --- | --- |
| `inventory` | `tenant_id`, `sku_id`, `available` | Khóa duy nhất theo tenant/SKU; `CHECK (available >= 0)` nếu DB hỗ trợ |
| `purchase_order` | `id`, `tenant_id`, `customer_id`, `client_reference`, `status` | PK; `UNIQUE (tenant_id, customer_id, client_reference)`; FK liên quan |
| `order_item` | `order_id`, `sku_id`, `quantity` | FK, `CHECK (quantity > 0)` |
| `outbox_event` (nếu cần) | `id`, `aggregate_id`, `event_type`, `payload`, `created_at` | Lưu event cùng transaction với đơn |

Không nhất thiết mọi hệ thống phải có cấu trúc bảng y hệt. Điều quan trọng là xác định **trạng thái nào không được phép tồn tại sau commit** và bổ sung constraint thực thi được tại database. Constraint là lớp bảo vệ cuối cùng trước các request đồng thời, thao tác từ batch job hoặc code path khác.

### 3.1. Chọn điểm bắt đầu và kết thúc

Một giao dịch tạo đơn phù hợp thường là:

~~~text
HTTP: validate JSON, authenticate user, check rate limits
      |
      v
application service: BEGIN TRANSACTION
    - kiểm tra quyền và phạm vi tenant liên quan đến dữ liệu
    - giữ số lượng tồn kho bằng thao tác atomic
    - tạo đơn hàng và dòng chi tiết
    - (tùy chọn) ghi outbox event
application service: COMMIT
      |
      v
HTTP: 201 Created, Location: /api/v1/orders/{id}
~~~

Không giữ database transaction trong khi tải file lớn, chờ người dùng, gọi một dịch vụ chậm qua HTTP, gửi email hoặc chờ message broker xác nhận. Transaction dài làm chiếm connection/lock, tăng nguy cơ deadlock và giảm throughput. Quy tắc này cần được cân bằng với yêu cầu nghiệp vụ, chứ không có một thời hạn transaction tuyệt đối phù hợp cho tất cả.

## 4. Ví dụ Java/Spring: đặt đơn và giữ tồn kho trong cùng transaction

Giả sử dùng Spring Boot 3, Spring Data JPA và một relational database. Các lớp entity, repository và `CurrentTenant` dưới đây là thành phần ứng dụng minh họa, chưa phải project hoàn chỉnh. Trong ứng dụng thật cần mapping entity, migration SQL, validation và authentication tương ứng.

### 4.1. HTTP controller chỉ chuyển yêu cầu vào service

~~~java
public record PlaceOrderRequest(
    @NotNull UUID skuId,
    @Min(1) int quantity,
    @NotBlank String clientReference
) {}

public record OrderReceipt(UUID id, String status) {}

@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final OrderApplicationService orders;

    public OrderController(OrderApplicationService orders) {
        this.orders = orders;
    }

    @PostMapping
    public ResponseEntity<OrderReceipt> create(
            @Valid @RequestBody PlaceOrderRequest request,
            Authentication authentication) {
        // Danh tính khách hàng do cơ chế authentication đã xác minh.
        OrderReceipt result =
            orders.placeOrder(authentication.getName(), request);

        URI location = URI.create("/api/v1/orders/" + result.id());
        return ResponseEntity.created(location).body(result);
    }
}
~~~

Controller xử lý binding/validation và xây HTTP response. `authentication.getName()` là principal đã được Spring Security xác thực, không lấy `customerId` hoặc `tenantId` do client tự khai để tăng quyền. Service phải kiểm tra thêm người gọi có quyền mua trong tenant và SKU có thể bán trong phạm vi đó; phân quyền không được mặc định chỉ vì có principal.

### 4.2. Service bảo vệ tính atomic

~~~java
@Service
public class OrderApplicationService {
    private final InventoryRepository inventory;
    private final OrderRepository orders;
    private final CurrentTenant currentTenant;

    public OrderApplicationService(
            InventoryRepository inventory,
            OrderRepository orders,
            CurrentTenant currentTenant) {
        this.inventory = inventory;
        this.orders = orders;
        this.currentTenant = currentTenant;
    }

    @Transactional
    public OrderReceipt placeOrder(
            String customerId, PlaceOrderRequest request) {
        String tenantId = currentTenant.requiredTenantId();
        // Chính sách nghiệp vụ xác nhận customer có quyền trong tenant.

        int updated = inventory.reserveIfEnough(
            tenantId, request.skuId(), request.quantity());
        if (updated != 1) {
            throw new InsufficientInventoryException();
        }

        PurchaseOrder order = PurchaseOrder.pending(
            tenantId,
            customerId,
            request.skuId(),
            request.quantity(),
            request.clientReference());
        orders.save(order);

        return new OrderReceipt(order.getId(), "PENDING");
    }
}

public class InsufficientInventoryException extends RuntimeException {
    public InsufficientInventoryException() {
        super("Không đủ hàng để giữ theo số lượng yêu cầu");
    }
}
~~~

Phương thức service được gọi qua bean Spring nên `@Transactional` bao phủ việc cập nhật `inventory` và thêm `purchase_order`. Nếu insert thất bại vì constraint, hoặc một exception khiến transaction rollback, lượng hàng giữ trong cùng database transaction cũng bị hủy. Mọi repository trong ví dụ phải tham gia **cùng transaction manager / cùng database**. Nếu ghi sang hai database độc lập thì `@Transactional` thông thường không tạo ra giao dịch atomic xuyên cả hai.

Chú ý thứ tự: trong demo, lỗi thiếu hàng được phát hiện **trước** khi ghi đơn, nhưng việc rollback vẫn cần thiết cho các lỗi xảy ra sau khi đã trừ hàng (ví dụ insert đơn vi phạm unique key). Với nghiệp vụ phức tạp hơn, có thể cần tạo đơn, các dòng chi tiết, giá tại thời điểm mua và outbox event trong cùng transaction.

### 4.3. Cập nhật tồn kho bằng một câu SQL có điều kiện

Một cách tránh race condition là thực hiện check và decrement ngay trong **một** câu `UPDATE`:

~~~java
public interface InventoryRepository
        extends JpaRepository<Inventory, InventoryId> {

    @Modifying
    @Query(value = """
        UPDATE inventory
           SET available = available - :quantity
         WHERE tenant_id = :tenantId
           AND sku_id = :skuId
           AND available >= :quantity
        """, nativeQuery = true)
    int reserveIfEnough(
        @Param("tenantId") String tenantId,
        @Param("skuId") UUID skuId,
        @Param("quantity") int quantity);
}
~~~

Nếu `quantity > 0`, hàng đã được phép bán và mỗi SKU trong tenant có đúng một row, thì `updated == 1` biểu thị yêu cầu giữ hàng thành công. `updated == 0` có thể nghĩa là SKU không tồn tại, không thuộc tenant hoặc không đủ tồn kho; hãy định nghĩa cách trả lỗi để tránh lộ tài nguyên xuyên tenant. Database khóa/cạnh tranh trên row khi cập nhật, và điều kiện `available >= :quantity` được xét như một phần của thao tác ghi atomic theo ngữ nghĩa database. Với PostgreSQL ở `READ COMMITTED`, các `UPDATE` đồng thời trên cùng row sẽ tuần tự hóa cập nhật và kiểm tra điều kiện trên phiên bản row phù hợp; hãy kiểm chứng hành vi trên DB và isolation level thực tế.

Đừng đọc `available` ra Java, kiểm tra `available >= requested` rồi gọi `save(entity)` mà không dùng cơ chế kiểm soát cạnh tranh. Hai request có thể cùng thấy `available=1` và đều quyết định nhận đơn. Với native/bulk update trong JPA, persistence context có thể chứa entity `Inventory` cũ; đừng tiếp tục dùng trạng thái entity cached sau bulk update mà không refresh/clear phù hợp. Có thể bổ sung constraint `available >= 0` để database chặn dữ liệu bất hợp lệ.

### 4.4. Lỗi HTTP được ánh xạ ngoài transaction

~~~java
@RestControllerAdvice
public class OrderErrorHandler {

    @ExceptionHandler(InsufficientInventoryException.class)
    public ProblemDetail insufficientInventory(
            InsufficientInventoryException exception) {
        ProblemDetail detail =
            ProblemDetail.forStatus(HttpStatus.CONFLICT);
        detail.setTitle("Không thể tạo đơn ở trạng thái tồn kho hiện tại");
        detail.setDetail("Số lượng hàng không đủ để tạo đơn.");
        return detail;
    }
}
~~~

Nếu API sử dụng Problem Details (RFC 9457), response có thể là:

~~~http
POST /api/v1/orders HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{"skuId":"11111111-1111-4111-8111-111111111111",
 "quantity":2,
 "clientReference":"checkout-abc-001"}

HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Không thể tạo đơn ở trạng thái tồn kho hiện tại",
  "status": 409,
  "detail": "Số lượng hàng không đủ để tạo đơn."
}
~~~

Đây là ví dụ request/response minh họa. `409 Conflict` phù hợp khi thao tác xung đột với **trạng thái hiện tại** của resource; nếu hệ thống dùng một mã khác cho thiếu hàng, hãy định nghĩa nhất quán trong OpenAPI và hợp đồng lỗi. `@ControllerAdvice` phải ánh xạ lỗi sau khi transaction đã rollback; tuyệt đối không nuốt lỗi rồi trả `201` như thể giao dịch thành công.

## 5. Vấn đề cạnh tranh khi nhiều request cùng cập nhật

Đúng ranh giới transaction **chưa đủ** để bảo vệ mọi bất biến trong điều kiện đồng thời. Isolation level, cách đọc/cập nhật và constraint quyết định kết quả. Xét tồn kho chỉ còn một sản phẩm:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant D as Database
    participant B as Request B
    A->>D: SELECT available = 1
    B->>D: SELECT available = 1
    A->>D: Quyết định giữ 1
    B->>D: Quyết định giữ 1
    Note over A,B: Nếu chỉ check ở Java, cả hai có thể chấp nhận đơn
~~~

Thao tác `UPDATE ... WHERE available >= :quantity` giúp tránh việc cả hai cùng giữ một đơn vị tồn kho. Các kỹ thuật khác:

| Kỹ thuật | Thích hợp khi | Cần chú ý |
| --- | --- | --- |
| Atomic conditional `UPDATE` | Tăng/giảm bộ đếm, giữ hàng, chuyển trạng thái có điều kiện | Kiểm tra số row cập nhật; đặt predicate gồm tenant và điều kiện phiên bản/trạng thái |
| Optimistic locking (`@Version`) | Nhiều lượt đọc, ít xung đột, không muốn giữ lock lâu | Phát hiện version mismatch; rollback và retry có giới hạn hoặc trả conflict |
| Pessimistic row lock (`SELECT ... FOR UPDATE`) | Phải đọc rồi ra quyết định liên quan trạng thái hiện tại | Giữ transaction ngắn; khóa theo thứ tự ổn định, xử lý deadlock/timeout |
| Unique constraint / FK / check | Bất biến có thể diễn đạt ở database | Luôn cần cho đường code cạnh tranh; map vi phạm constraint sang lỗi thích hợp |
| Isolation cao hơn (`SERIALIZABLE`) | Nhiều điều kiện đọc/ghi có thể gây anomaly khó tránh | Có thể phải retry transaction bị abort; giảm concurrency, chi phí khác nhau theo DB |

### 5.1. Optimistic concurrency qua version

Ví dụ resource `PUT /api/v1/orders/{id}` dùng ETag:

~~~http
GET /api/v1/orders/42 HTTP/1.1
Authorization: Bearer <token>

HTTP/1.1 200 OK
ETag: "order-v7"
Content-Type: application/json

{"id":"42","status":"PENDING"}
~~~

Client sửa dựa trên đúng phiên bản đã đọc:

~~~http
PATCH /api/v1/orders/42 HTTP/1.1
Authorization: Bearer <token>
If-Match: "order-v7"
Content-Type: application/json

{"status":"CANCELLED"}
~~~

Server cần so `If-Match` với version thực sự của tài nguyên và cập nhật có điều kiện **trong transaction**, không chỉ so trong memory trước khi ghi. Nếu precondition không đúng, trả `412 Precondition Failed`; nếu endpoint yêu cầu bắt buộc có `If-Match`, có thể trả `428 Precondition Required` khi thiếu. `@Version` ở JPA giúp phát hiện update dựa trên version cũ, nhưng việc ánh xạ ETag HTTP sang version JPA phải được thiết kế rõ và bảo đảm kiểm tra đúng khi ghi. Nếu không dùng HTTP precondition, lỗi cạnh tranh nghiệp vụ thường được ánh xạ `409 Conflict`.

### 5.2. Bảo vệ nhiều bản ghi và nhiều bất biến

Nếu thao tác chuyển tiền từ tài khoản A sang B trong cùng database, kiểm soát số dư và ghi cả hai thay đổi vào **một transaction**. Tuy nhiên, hai request chuyển tiền đồng thời vẫn cần khóa hoặc điều kiện cập nhật để không chi vượt số dư. Nếu nhiều bản ghi được khóa, chọn thứ tự khóa nhất quán để giảm deadlock. Nếu định nghĩa bất biến như “chỉ một đơn đang hoạt động cho mỗi ghế”, một **unique constraint có điều kiện** hoặc cơ chế khóa phù hợp thường cần hơn kiểm tra `SELECT COUNT(*)` rồi `INSERT`.

Đừng tùy tiện nâng mọi transaction lên `SERIALIZABLE`. Trước hết xác định anomaly cần ngăn, đo độ tranh chấp, dùng predicate/constraint/locking phù hợp, sau đó cấu hình isolation cao hơn khi cần. Mặc định Spring `Isolation.DEFAULT` theo database: PostgreSQL thường mặc định `READ COMMITTED`, MySQL InnoDB thường `REPEATABLE READ`; không giả định mọi DB có cùng hành vi.

## 6. Những điểm dễ hiểu sai về @Transactional

### 6.1. Proxy, self-invocation và lớp đặt transaction

Trong Spring với transaction dựa trên proxy, lời gọi đến phương thức `@Transactional` phải đi **qua proxy Spring**. Ví dụ có nguy cơ:

~~~java
@Service
class UnsafeOrderService {
    public void process() {
        saveOrder(); // Gọi nội bộ trên this, có thể bypass proxy.
    }

    @Transactional
    public void saveOrder() {
        // Ghi nhiều bảng nhưng không có transaction như mong đợi.
    }
}
~~~

Giải pháp là đặt ranh giới ở phương thức application service được controller/bean khác gọi qua Spring, hoặc tách service thành bean phù hợp. Hạn chế đặt `@Transactional` trên private method hay class tạo bằng `new`; proxy không có cơ hội can thiệp. Với Spring AOP, đặc biệt chú ý self-invocation, phương thức final và cách tạo bean. Nếu dùng AspectJ weaving hoặc reactive stack thì cơ chế thực thi có khác biệt.

Thông thường nên đặt transaction tại **application service**, nơi mô tả một use case như `placeOrder()` hoặc `transferFunds()`. Gắn `@Transactional` trên mọi repository/controller một cách máy móc dễ gây transaction phân mảnh, kéo dài transaction qua nhiều bước xử lý HTTP hoặc vô tình phụ thuộc chi tiết bên dưới.

### 6.2. Checked exception, bắt lỗi và rollback

Theo mặc định phổ biến của Spring, unchecked exception (`RuntimeException`) và `Error` làm transaction rollback; checked exception không mặc nhiên làm vậy. Nếu nghiệp vụ dùng checked exception để biểu thị thất bại phải rollback, cấu hình rõ:

~~~java
@Transactional(rollbackFor = BusinessRuleException.class)
public OrderReceipt execute(PlaceOrderRequest request)
        throws BusinessRuleException {
    // Ghi dữ liệu và có thể ném BusinessRuleException.
}
~~~

Đây là minh họa; `BusinessRuleException` là checked exception do ứng dụng định nghĩa. Nếu code bắt exception **bên trong** phương thức transactional và chỉ log rồi trả kết quả bình thường, transaction có thể commit những thay đổi đã ghi. Hãy chỉ bắt lỗi khi biết rõ cách phục hồi an toàn, hoặc ném tiếp lỗi; nếu buộc xử lý ở trong transaction, có thể đánh dấu rollback-only qua API transaction thích hợp. Cần phân biệt lỗi domain (như thiếu tồn kho) và lỗi hạ tầng (deadlock, mất kết nối); đừng biến mọi lỗi DB thành HTTP 409.

### 6.3. Flush, commit và thời điểm đọc được dữ liệu

JPA `save()` không bảo đảm mọi câu SQL đã được gửi ngay; `flush()` đẩy những thay đổi trong persistence context xuống database nhưng **không đồng nghĩa commit**. Constraint có thể phát nổ tại flush hoặc commit, tùy loại constraint và DB. Transaction được commit sau khi method transactional trả về qua proxy; nếu commit thất bại, controller không được coi method đã hoàn thành thành công.

`@Transactional(readOnly = true)` chủ yếu là hint/thiết lập tối ưu được framework và driver áp dụng ở mức hỗ trợ; không nên coi nó là chính sách phân quyền hoặc cam kết mọi database sẽ chặn ghi. `timeout` trên `@Transactional` giới hạn thời gian theo khả năng của transaction manager/driver, không tự hủy mọi network call hoặc thay thế timeout ở HTTP/gateway.

### 6.4. Propagation và transaction độc lập

| Propagation | Hành vi thường gặp | Rủi ro nếu hiểu sai |
| --- | --- | --- |
| `REQUIRED` (mặc định) | Tham gia transaction hiện có hoặc tạo mới | Service được gọi từ nơi khác có thể nhập vào transaction lớn hơn |
| `REQUIRES_NEW` | Tạm dừng transaction hiện tại và mở transaction riêng | Transaction con có thể commit dù transaction ngoài rollback |
| `MANDATORY` | Bắt buộc có transaction hiện tại | Gọi riêng không có transaction sẽ lỗi; hữu ích khi muốn ép use case boundary |
| `NOT_SUPPORTED` | Chạy ngoài transaction hiện tại | Không bảo vệ atomic cho các thay đổi ghi bên trong |
| `NESTED` | Có thể dùng savepoint khi transaction manager hỗ trợ | Không phải “transaction độc lập” và không được hỗ trợ đồng nhất mọi DB/JPA |

Ví dụ, một helper ghi log dùng `REQUIRES_NEW` có thể commit log “đã thành công” dù đơn hàng ngoài bị rollback. Chỉ dùng transaction độc lập khi chấp nhận có trạng thái riêng biệt và đã thiết kế tính nhất quán. Giao dịch lồng nhau cũng tiêu tốn connection/lock; cần cân nhắc pool size và deadlock.

### 6.5. Tác vụ async và thread context

Transaction kiểu imperative thường gắn với thread hiện tại. Lệnh `@Async`, `CompletableFuture` chạy thread khác hoặc callback sau response **không tự động kế thừa transaction** đang mở. Với Reactor/WebFlux phải dùng cơ chế reactive transaction tương ứng, không giả định `ThreadLocal` hoạt động như Spring MVC. Dữ liệu cần xử lý sau request nên được commit dưới dạng trạng thái/job/outbox, rồi worker thực hiện trong transaction riêng với idempotency và quyền phù hợp.

## 7. Không gộp HTTP call và message broker vào một database transaction

Một bước thanh toán từ provider, gửi email xác nhận hay publish Kafka/RabbitMQ không trở thành atomic chỉ vì phương thức Java có `@Transactional`. Xem ví dụ sai:

~~~java
@Transactional
public void createAndNotify(PlaceOrderRequest request) {
    orderRepository.save(/* ... */);
    paymentClient.charge(/* ... */); // Gọi dịch vụ bên ngoài.
    emailClient.send(/* ... */);     // Tác dụng phụ không rollback được.
}
~~~

Giả sử email gửi thành công rồi database rollback: email đã ra ngoài. Hoặc database giữ lock trong khi provider chậm; nếu client mất kết nối rồi retry, có thể thu tiền hai lần. `@Transactional` của local database không thể thu hồi email hay tự đảo giao dịch của provider. Khi hệ thống cần phối hợp nhiều dịch vụ, hãy thiết kế quy trình nghiệp vụ rõ ràng, có trạng thái trung gian, idempotency và thao tác bù khi cần.

### 7.1. Transactional outbox cho thông báo sau commit

Một cách phổ biến để tránh “đã tạo đơn nhưng không có event” là ghi bản ghi outbox **trong cùng transaction** với thay đổi domain:

~~~mermaid
flowchart LR
    A["POST /orders"] --> B["DB transaction"]
    B --> C["UPDATE inventory"]
    B --> D["INSERT purchase_order"]
    B --> E["INSERT outbox_event"]
    C --> F["COMMIT cùng nhau"]
    D --> F
    E --> F
    F --> G["Outbox worker"]
    G --> H["Broker / service khác"]
    H --> I["Consumer xử lý idempotent"]
~~~

Ở thời điểm commit, **đơn hàng và outbox event cùng tồn tại**. Worker ngoài transaction request đọc event, gửi đến broker, rồi cập nhật trạng thái đã gửi. Worker có thể crash sau khi broker nhận message nhưng trước khi đánh dấu đã gửi, dẫn đến publish lại; vì vậy consumer cần xử lý trùng theo event ID hoặc business key. Outbox giúp tránh mất thông báo khi chuyển từ DB sang broker, **không bảo đảm exactly-once effect trên toàn hệ thống** nếu không bổ sung cơ chế idempotency.

`@TransactionalEventListener(phase = AFTER_COMMIT)` có thể phù hợp cho các xử lý sau commit có thể mất mà hệ thống chấp nhận, nhưng **không thay thế durable outbox** khi event phải được gửi chắc chắn: process có thể chết giữa commit và callback.

Với thanh toán hoặc chuỗi công việc qua nhiều hệ thống, một transaction tại request thường chỉ ghi `PENDING`/`ACCEPTED` và ý định xử lý; worker/saga sau đó chuyển `CONFIRMED` hoặc `FAILED`. Hãy dùng `202 Accepted` nếu API mới **nhận xử lý**, và trả resource job/status hoặc `Location` nếu có. Không trả `201 Created` cho tài nguyên đã hoàn thành một bước nghiệp vụ mà thực tế còn đang phụ thuộc vào provider.

## 8. Khi client retry: commit rồi nhưng response mất

Tình huống quan trọng nhất với API có ghi dữ liệu:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant D as Database
    C->>A: POST /orders + Idempotency-Key: abc
    A->>D: BEGIN, ghi order
    D-->>A: COMMIT thành công
    A--xC: 201 bị mất do lỗi mạng
    C->>A: Retry POST /orders + cùng key
    Note over A,D: Tìm kết quả đã commit trước đó
    A-->>C: Trả kết quả tương ứng, không tạo đơn thứ hai
~~~

Để client có thể retry an toàn, API có thể dùng **Idempotency-Key** cho thao tác tạo đơn hoặc thanh toán. Khi thiết kế, cần xác định:

1. Phạm vi khóa: ví dụ `tenantId + customerId + HTTP method + route + Idempotency-Key`, không dùng khóa toàn cục do client tự chọn mà không có namespace.
2. Liên kết khóa với **fingerprint của request** (payload, action); cùng khóa nhưng payload khác phải bị từ chối theo hợp đồng, không âm thầm ghi đè kết quả.
3. Lưu kết quả/định danh resource và trạng thái xử lý theo cách atomic với thay đổi nghiệp vụ. Một row chứa idempotency record có unique constraint; xử lý các request đồng thời tranh khóa đúng quy tắc.
4. Nếu request đầu chưa hoàn thành, định nghĩa phản hồi cho bản gửi lại: có thể `409 Conflict`/`202 Accepted` hoặc trạng thái retry riêng theo hợp đồng; **không** cho cả hai chạy nghiệp vụ song song.
5. Có chính sách lưu trữ/TTL và bảo mật; đừng xóa record quá sớm so với khoảng thời gian client có thể retry.

Ví dụ:

~~~http
POST /api/v1/orders HTTP/1.1
Authorization: Bearer <token>
Idempotency-Key: "order-req-7e9d"
Content-Type: application/json

{"skuId":"11111111-1111-4111-8111-111111111111",
 "quantity":1,
 "clientReference":"checkout-abc-001"}

HTTP/1.1 201 Created
Location: /api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f
Content-Type: application/json

{"id":"8c9b4ca4-2211-4cd0-a949-d176bcb8e35f","status":"PENDING"}
~~~

`Idempotency-Key` là một hợp đồng tùy chọn do API áp dụng; đừng dựa vào việc client dùng `POST` để tự suy ra yêu cầu idempotent. `PUT` có ngữ nghĩa idempotent theo HTTP, nhưng backend vẫn phải triển khai đúng và xử lý cạnh tranh, side effect ngoài DB và response bị mất. Unique constraint `clientReference` trong ví dụ trước giúp phát hiện trùng, nhưng **không tự trả lại cùng kết quả, không xử lý request cùng key/payload khác**. Idempotency hoàn chỉnh cần một protocol riêng.

### 8.1. Timeout không cho biết kết quả commit

Nếu client/gateway timeout ở 5 giây, transaction có thể đã commit ở giây thứ 4 rồi response đến trễ; cũng có thể transaction đang giữ lock và sau đó rollback. Không nên tự động retry một operation có side effect **với khóa mới**. Client cần đọc trạng thái bằng một định danh ổn định hoặc retry bằng cùng Idempotency-Key trong khoảng thời gian hỗ trợ. Với những lỗi giao dịch tạm thời như deadlock hoặc serialization failure, server có thể retry **cả transaction từ đầu** có giới hạn và backoff; chỉ retry khi thao tác bên trong không có side effect ngoài DB chưa được kiểm soát.

## 9. Hợp đồng HTTP phản ánh trạng thái giao dịch

| Trường hợp | Status thường dùng | Quan hệ với transaction |
| --- | --- | --- |
| Input sai schema/kiểu/validation | `400 Bad Request` (hoặc `422 Unprocessable Content` theo hợp đồng) | Từ chối trước khi ghi; không cần mở transaction ghi |
| Chưa xác thực / không đủ quyền | `401 Unauthorized` / `403 Forbidden` | Kiểm tra sớm và tại tầng nghiệp vụ; không tạo side effect |
| Resource không tồn tại/không thuộc phạm vi được phép thấy | `404 Not Found` theo chính sách | Không cho phép thao tác lên resource ngoài tenant |
| Thiếu hàng hoặc trạng thái xung đột | `409 Conflict` | Transaction rollback; trạng thái hiện tại không cho phép thao tác |
| `If-Match` không còn đúng | `412 Precondition Failed` | Không ghi thay đổi không dựa trên phiên bản mong đợi |
| Thiếu `If-Match` bắt buộc | `428 Precondition Required` | Không bắt đầu thao tác ghi khi thiếu điều kiện |
| Đã tạo đơn và commit xong | `201 Created` + `Location` | Tài nguyên đã được ghi bền vững trong DB |
| Đã cập nhật thành công và không trả body | `204 No Content` | Thay đổi đã commit |
| Đã nhận job, chưa hoàn thành xử lý | `202 Accepted` | Đã ghi nhận ý định/job; tác dụng cuối sẽ đến sau |
| DB/broker tạm thời không sẵn sàng | `503 Service Unavailable` nếu phù hợp | Trạng thái commit có thể cần được kiểm tra lại sau timeout |

Các status là **thiết kế hợp đồng**, không tự chứng minh việc commit. Lỗi `5xx` cũng không bảo đảm transaction rollback: server có thể commit rồi thất bại khi tạo response. Đối với `201`, nên gửi một `Location` trỏ đến resource có thể truy cập hoặc trạng thái đại diện; URI không cần tuyệt đối nếu hợp đồng cho phép relative URI. Với việc tạo đơn không đồng bộ, cần tránh hứa “hoàn tất” khi chỉ mới ghi job.

Không để exception handler biến mọi `DataIntegrityViolationException` thành `409` mà không phân loại constraint; một lỗi FK do dữ liệu server hỏng, unique do idempotency, và lỗi connection không cùng ngữ nghĩa. Log nội bộ phải đủ thông tin để điều tra nhưng response không tiết lộ SQL, stack trace, connection string hoặc tenant khác.

## 10. Kiểm thử ranh giới giao dịch và cạnh tranh

Kiểm thử đúng nên chứng minh **bất biến còn đúng sau thất bại**, không chỉ xác nhận HTTP status. Với transaction, cần kiểm tra dữ liệu thực sự được commit/rollback từ một transaction quan sát **độc lập**.

### 10.1. Ma trận kiểm thử cốt lõi

| Kịch bản | Trạng thái mong đợi | Kiểm tra database sau request |
| --- | --- | --- |
| Tạo đơn hợp lệ, còn hàng | `201` | Đơn tồn tại và tồn kho giảm chính xác một lần |
| Không đủ hàng | `409` | Không tạo đơn; tồn kho giữ nguyên |
| Insert đơn vi phạm unique sau khi giữ hàng | Lỗi được ánh xạ theo hợp đồng | Cả số lượng tồn và đơn thứ hai đều không commit |
| Hai request cùng mua SKU chỉ còn một sản phẩm | Một thành công, một thất bại phù hợp | Tồn kho không âm; chỉ có một đơn hợp lệ |
| Hai request cùng Idempotency-Key | Trả kết quả tương ứng theo chính sách | Một hành động nghiệp vụ, một lần giảm tồn kho |
| Cùng key nhưng payload khác | Từ chối theo hợp đồng | Không tạo đơn/giữ hàng khác |
| Client mất kết nối sau commit rồi retry | Replay/đọc trạng thái | Không tạo đơn thứ hai |
| Khách hàng tenant A yêu cầu SKU tenant B | `404`/`403` theo chính sách | Không cập nhật bất kỳ row tenant B |
| Publication worker crash sau khi gửi event | Gửi lại có thể xảy ra | Consumer xử lý idempotent; không nhân đôi side effect |

### 10.2. Kiểm thử rollback thực bằng Spring Boot

Minh họa kiểm thử tích hợp với database đã được seed đúng constraint, không bọc chính phương thức test trong một transaction:

~~~java
@SpringBootTest
class OrderTransactionIT {
    @Autowired OrderApplicationService service;
    @Autowired InventoryRepository inventory;
    @Autowired OrderRepository orders;

    @Test
    void duplicateReferenceRollsBackInventoryReservation() {
        // Fixture đã có đơn (tenant-a, alice, ref-01);
        // SKU đang có 5 đơn vị sẵn sàng bán.
        UUID skuId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        int before = inventory.available("tenant-a", skuId);
        long orderCountBefore = orders.count();

        assertThrows(DataIntegrityViolationException.class, () ->
            service.placeOrder("alice",
                new PlaceOrderRequest(skuId, 1, "ref-01")));

        assertThat(inventory.available("tenant-a", skuId))
            .isEqualTo(before);
        assertThat(orders.count()).isEqualTo(orderCountBefore);
    }
}
~~~

Đây là mã khung giả định có helper `inventory.available(tenantId, skuId)` và fixture tạo bằng migration/test data. Để đúng ngữ cảnh, `CurrentTenant` của test phải xác định `tenant-a`; `purchase_order` có unique constraint thực trên `(tenant_id, customer_id, client_reference)`. Cần import JUnit, AssertJ và Spring tương ứng. Tùy JPA/provider và thời điểm flush, exception có thể phát sinh lúc commit; test phải quan sát dữ liệu **sau khi method proxied kết thúc**.

Đừng chỉ dùng `@Transactional` trên test và sau đó trông vào rollback cuối test: nó có thể làm test pass vì **chính test tự rollback**, trong khi implementation thực tế có transaction boundary sai. Với test rollback và concurrency, nên chạy PostgreSQL/MySQL phiên bản tương đương môi trường sản xuất (ví dụ Testcontainers), tạo dữ liệu độc lập, quản lý cleanup có kiểm soát và quan sát từ transaction khác.

### 10.3. Kiểm thử request đồng thời

Với SKU còn một đơn vị, tạo **hai request song song** có customer/reference khác nhau và cùng SKU. Đồng bộ điểm bắt đầu (barrier/latch), để cả hai gọi service qua Spring bean thật, sau đó xác nhận chính xác một request nhận đơn và tồn kho bằng 0; request còn lại bị từ chối theo policy. Lặp lại đủ lần để phát hiện lỗi tranh chấp nhưng không lấy kết quả stress test làm bảo đảm toán học; bằng chứng mạnh hơn đến từ **atomic SQL, isolation behavior và database constraint**.

Khi test ETag/optimistic lock, cho hai client cùng đọc version `v7` rồi cùng cập nhật. Một update phải thành công, update còn lại trả `412` hoặc `409` tùy hợp đồng, và dữ liệu không bị lost update. Khi test outbox, mô phỏng worker crash sau publish để kiểm tra consumer dedup, không chỉ happy path.

## 11. Bài tập thực hành

**Bài tập 1 — Vẽ ranh giới.** API `POST /api/v1/transfers` cần trừ tiền tài khoản A, cộng tiền tài khoản B (cùng database) và gửi email. Hãy vẽ trình tự từ HTTP controller tới transaction, chỉ ra thao tác nào phải chung một transaction, thao tác nào nên được phát sau commit, và điều gì xảy ra nếu email gửi thành công nhưng database rollback.

**Bài tập 2 — Sửa race condition.** Hai request cùng đặt đơn với SKU còn một sản phẩm. Code hiện tại:

~~~java
Inventory item = inventory.findById(skuId).orElseThrow();
if (item.getAvailable() > 0) {
    item.setAvailable(item.getAvailable() - 1);
    inventory.save(item);
    orders.save(PurchaseOrder.pending(...));
}
~~~

Hãy sửa bằng atomic conditional `UPDATE` hoặc optimistic locking và đặt toàn bộ cập nhật trong application service `@Transactional`. Viết kiểm thử cạnh tranh và chứng minh không có tồn kho âm hoặc hai đơn cùng giữ một đơn vị.

**Bài tập 3 — Rollback và exception.** Một service bắt `BusinessRuleException` (checked) sau khi cập nhật tồn kho rồi trả `OrderReceipt`. Phân tích khi nào transaction commit nhầm, sửa bằng `rollbackFor` hoặc exception policy phù hợp và thêm test chứng minh tồn kho không thay đổi sau lỗi.

**Bài tập 4 — Response bị mất.** Server commit một đơn rồi gateway timeout trước khi client nhận `201`. Client gửi lại `POST`. Thiết kế contract `Idempotency-Key`: phạm vi khóa, unique constraint, request fingerprint, xử lý đang chạy, replay kết quả và TTL. Cho hai request đồng thời cùng key, giải thích vì sao chỉ được tạo một đơn.

**Bài tập 5 — Tách side effect ngoài DB.** Service lưu đơn rồi gọi HTTP payment provider và publish message trong cùng `@Transactional`. Hãy chuyển sang mô hình ghi state/outbox atomic, worker thực hiện bên ngoài request transaction, consumer idempotent và xử lý trạng thái `PENDING`/`CONFIRMED`/`FAILED`. Xác định khi nào trả `201`, khi nào trả `202` và endpoint nào dùng để hỏi tiến độ.

### Tiêu chí đánh giá

Lời giải đạt yêu cầu khi: (1) chỉ rõ database transaction bắt đầu/kết thúc tại application service; (2) bất biến được bảo vệ bằng atomic write hoặc locking/constraint có căn cứ; (3) lỗi sau ghi bước đầu rollback toàn bộ thay đổi liên quan; (4) không xem side effect ngoài database là một phần rollback tự động; (5) hợp đồng HTTP phân biệt created/accepted/conflict/precondition; và (6) kiểm thử concurrent request, duplicate request, commit rồi mất response và cross-tenant có bằng chứng trạng thái database sau cùng.

## 12. Checklist khi review API có ghi dữ liệu

- [ ] Một hành động nghiệp vụ có transaction boundary rõ ở service; controller không giữ transaction trong lúc trả response hoặc chờ I/O ngoài.
- [ ] Các bảng/bản ghi cần atomic cùng dùng một datasource/transaction manager; constraint bảo vệ các bất biến thực thi được tại DB.
- [ ] Tranh chấp đồng thời được xử lý bằng atomic conditional update, `@Version`, row lock hoặc isolation phù hợp; không chỉ `SELECT` rồi `save`.
- [ ] Exception, rollback rule, propagation và self-invocation đã được xem xét; không nuốt lỗi rồi commit dở dang.
- [ ] Tenant, quyền người dùng và điều kiện đối tượng lấy từ nguồn đã xác thực; mọi update giới hạn đúng phạm vi.
- [ ] `save`, `flush` và `commit` được phân biệt; commit failure không bị chuyển thành response thành công.
- [ ] HTTP client/broker/email/payment không được mặc định nằm trong local DB transaction; có outbox/workflow khi cần.
- [ ] API ghi có chiến lược idempotency và quy trình retry cho trường hợp client timeout sau commit.
- [ ] HTTP status và Problem Details khớp trạng thái resource, tính đồng bộ/bất đồng bộ và lỗi cạnh tranh.
- [ ] Integration test quan sát database từ transaction độc lập, có test rollback sau partial write, test đồng thời và kiểm tra dữ liệu sau lỗi.

**Điểm cốt lõi:** ranh giới giao dịch nên bao trùm **những thay đổi trong một database cần cùng thỏa mãn bất biến nghiệp vụ**. Một request HTTP chỉ là bề mặt giao tiếp: dữ liệu được commit trước khi kết quả đến client, những hệ thống bên ngoài không tự rollback theo transaction local, và request gửi lại phải được xử lý bằng hợp đồng idempotency cùng kiểm soát cạnh tranh có chủ đích.
