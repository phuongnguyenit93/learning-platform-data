# Tính nguyên tử cho một tài nguyên hoặc một thao tác batch

> **Module:** `INTEGRATION_API_REST` — chương **Nhất quán nghiệp vụ**. Bài học làm rõ *atomicity* (tính nguyên tử) trong REST API: cập nhật một tài nguyên có nhiều thuộc tính, cập nhật nhiều mục trong một batch, ranh giới transaction cơ sở dữ liệu, kiểm soát phiên bản và idempotency. Ví dụ dùng HTTP, Java 17, Spring Boot 3 / Spring MVC, Spring Data JPA, bảo mật, OpenAPI và kiểm thử.

## 1. Vấn đề: một request không nhất thiết là một giao dịch nguyên tử

Giả sử người dùng yêu cầu thay đổi đơn hàng `ord_42`: sửa địa chỉ nhận hàng và đổi số lượng. Nếu hệ thống cập nhật địa chỉ, sau đó phát hiện số lượng vượt tồn kho rồi trả lỗi nhưng **giữ địa chỉ mới**, trạng thái đơn trở nên nửa cũ nửa mới. Ở một tình huống khác, client giữ hàng cho ba SKU:

~~~http
POST /v1/inventory-reservations/batches HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 920bfec1-b36f-4d45-b00c-c92715f7f733
Accept: application/json

{
  "items": [
    {"sku": "SKU-A", "quantity": 2},
    {"sku": "SKU-B", "quantity": 1},
    {"sku": "SKU-C", "quantity": 5}
  ]
}
~~~

`SKU-C` chỉ còn ba sản phẩm. API có nên giữ `SKU-A`, `SKU-B` rồi báo lỗi `SKU-C`, hay từ chối **cả batch**? Câu trả lời là **quyết định hợp đồng nghiệp vụ**, không phải chuyện framework tự quyết.

Trong bài này, ta chọn hai hợp đồng minh họa:

- **Cập nhật một resource:** mọi field thay đổi cùng nhau; nếu một invariant/condition sai, không field nào được commit.
- **Batch nguyên tử:** tất cả items cùng được áp dụng trong **một database transaction** hoặc không item nào được áp dụng. Không trả thành công từng phần như thể batch đã commit.

**Mục tiêu:** phân biệt all-or-nothing với best-effort, thiết kế HTTP status và body, bảo vệ khỏi lost update, triển khai `@Transactional` đúng phạm vi, xử lý retry/side effects, kiểm thử rollback và quyền trên từng item.

## 2. Tính nguyên tử thực sự cam kết điều gì?

Tính nguyên tử (*atomicity*) là tính chất **all-or-nothing của những thay đổi nằm trong cùng một đơn vị commit**. Nó không có nghĩa request chỉ có một câu SQL, không có nghĩa toàn hệ thống nhìn thấy thay đổi tại cùng một thời điểm, và **không có nghĩa mọi service bên ngoài cũng rollback**.

~~~mermaid
flowchart TD
    A["HTTP PATCH hoặc POST batch"] --> B["Xác thực + phân quyền theo item"]
    B --> C["Parse, validate, kiểm invariant"]
    C --> D["DB transaction: đọc/khóa, ghi nhiều rows"]
    D --> E{"Tất cả điều kiện và commit thành công?"}
    E -- "Có" --> F["Commit + HTTP 2xx"]
    E -- "Không" --> G["Rollback + HTTP 4xx/5xx phù hợp"]
    F --> H["Outbox worker phát event sau commit"]
    G -. "Không phát event thành công" .-> H
~~~

### 2.1. Bốn khái niệm dễ bị đánh đồng

| Khái niệm | Câu hỏi | Điểm cần nhớ |
|---|---|---|
| **Atomicity** | Có thể chỉ commit một phần những write của transaction không? | Không: commit hết hoặc rollback hết |
| **Consistency** | Invariant nào phải luôn đúng sau commit? | Ví dụ tồn kho không âm, tenant đúng, tổng tiền hợp lệ |
| **Isolation** | Giao dịch chạy song song tương tác ra sao? | Cần locking/phiên bản để tránh lost update, write skew |
| **Durability** | Sau commit, thay đổi có được lưu bền? | Phụ thuộc DB/storage và cấu hình |

Một transaction atomic vẫn có thể tính sai nghiệp vụ nếu kiểm tra invariant không đầy đủ hoặc isolation không phù hợp. Ví dụ hai giao dịch cùng đọc stock=5, mỗi giao dịch giữ 4 rồi ghi stock=1; nếu không khóa/compare-and-swap, kết quả có thể ghi nhận hai reservations dù tồn kho thực chỉ đủ cho một.

### 2.2. Phạm vi commit phải được nêu chính xác

Trong một relational DB, Spring `@Transactional` có thể bao các thao tác dùng **cùng transaction manager / datasource**. Nhưng nếu trong transaction còn gọi payment gateway, gửi email, ghi S3, publish Kafka hoặc RPC sang dịch vụ khác, rollback DB **không tự hoàn tác** các tác động ngoài đó.

Không viết tài liệu “atomic across all microservices” chỉ vì endpoint dùng `@Transactional`. Khi nhiều resource thuộc **nhiều DB/service độc lập**, dùng workflow/compensation (Saga), idempotency, transactional outbox hoặc một giao thức phân tán có thỏa thuận rõ; đó là **eventual consistency**, không tương đương transaction DB đơn lẻ.

## 3. Nguyên tử khi cập nhật **một tài nguyên**

HTTP API cho một resource thường nhận `PUT` hoặc `PATCH`:

- `PUT /v1/orders/ord_42` có ngữ nghĩa thay thế representation theo hợp đồng. Nếu client chỉ gửi một số field, cần định nghĩa rõ đó có phải full replacement không; không gọi mọi “partial update” là PUT.
- `PATCH /v1/orders/ord_42` mô tả tập thay đổi; theo RFC 5789, server **MUST apply the entire set of changes atomically**. Nếu toàn bộ patch không áp dụng được, không để lộ representation đã patch một nửa.
- `POST` cho một business command (ví dụ `/v1/orders/ord_42/cancellations`) cũng cần invariant/transaction rõ ràng, dù POST không mặc nhiên idempotent.

### 3.1. Một PATCH có nhiều thay đổi, một trong số đó không hợp lệ

~~~http
PATCH /v1/orders/ord_42 HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
If-Match: "ord_42-v7"

{
  "deliveryNote": "Giao cổng phụ",
  "shippingAddressId": "addr_other_tenant"
}
~~~

Giả sử người gọi sở hữu đơn nhưng **không sở hữu địa chỉ mới**. Server phải:

1. Xác thực và kiểm người gọi được sửa đơn `ord_42`.
2. Kiểm tất cả field và quan hệ `shippingAddressId` theo tenant/owner, **trước hoặc trong transaction**.
3. Kiểm ETag `If-Match` và trạng thái hiện tại còn cho chỉnh.
4. Chỉ commit khi **mọi điều kiện** đạt; nếu địa chỉ không hợp lệ thì `deliveryNote` cũng **không đổi**.

Không dùng `BeanUtils.copyProperties(request, entity)` rồi mới validate địa chỉ, nhất là khi persistence session có thể flush tự động. Với JSON Patch `application/json-patch+json`, nhiều operation `add/remove/replace/test/move/copy` thuộc **cùng một patch document** và phải được xử lý nguyên tử; `test` thất bại thì không áp dụng các thay đổi trước đó.

### 3.2. Mất cập nhật và HTTP conditional requests

Hai client cùng đọc ETag `"ord_42-v7"`. Client A đổi địa chỉ và commit phiên bản v8. Client B vẫn dùng ETag v7 để đổi ghi chú:

~~~http
PATCH /v1/orders/ord_42 HTTP/1.1
If-Match: "ord_42-v7"
Content-Type: application/merge-patch+json

{"deliveryNote":"Sau 18 giờ"}
~~~

Nếu resource đã ở v8, trả:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/stale-order",
  "title": "Resource version changed",
  "status": 412,
  "code": "STALE_VERSION",
  "detail": "Tải lại đơn hàng trước khi cập nhật."
}
~~~

`If-Match` dùng **strong comparison**: weak ETag (`W/"..."`) không đáp ứng strong match cho write. Nếu API bắt buộc precondition nhưng thiếu header, có thể trả **428 Precondition Required**. Kiểm ETag phải đi kèm cơ chế concurrency ở DB (`@Version`/atomic compare-and-swap/row lock) để tránh race giữa “kiểm” và “ghi”. Không hiểu `ETag` là token phân quyền; mọi lần cập nhật vẫn phải kiểm owner/tenant/scope.

### 3.3. Transaction ≠ retry an toàn

Nếu server đã commit nhưng response bị mất, client thấy timeout dù DB đã cập nhật. Để replay POST an toàn cần **Idempotency-Key** được xử lý phía server hoặc URI/command có ngữ nghĩa idempotent; với PATCH, client có thể đọc lại resource/ETag để đối soát. Việc rollback khi exception **trước commit** không nói gì về timeout **sau commit**.

## 4. Batch: nguyên tử toàn bộ hay trả kết quả từng item?

Một batch gồm N thao tác có ít nhất hai mô hình hợp lệ, nhưng **không thể để client tự đoán**:

| Đặc tính | **Atomic batch** | **Best-effort / partial batch** |
|---|---|---|
| Lỗi ở item thứ N | **Không item nào được commit** | Các item khác có thể đã commit |
| Transaction DB | Thường **một transaction** chứa toàn bộ batch | Mỗi item hoặc nhóm nhỏ có transaction riêng |
| Response thành công | 200/201 tùy contract, toàn bộ items thành công | 200 với kết quả từng item; đôi khi 207 nếu được định nghĩa rõ |
| Response lỗi | Một lỗi toàn batch + mã item vi phạm đã lọc | Danh sách kết quả success/failure theo item |
| Thời gian và khóa | Tăng theo batch; cần limit và thứ tự khóa | Dễ scale hơn, phải xử lý partial success |
| Retry | Replay **cùng batch ID/key** khi có idempotency | Retry riêng các item thất bại theo ID/key |
| Phù hợp | Cập nhật cần all-or-nothing trong một DB | Import độc lập, gửi thông báo, job lớn |

**`207 Multi-Status` không phải tín hiệu “partial transaction” phổ quát.** Nó xuất phát từ WebDAV; API ngoài WebDAV chỉ dùng khi có contract rõ về cách diễn giải body, clients và tooling. Rất nhiều JSON batch API chọn **200** kèm mảng `results` có status riêng. Ngược lại, nếu hợp đồng là atomic, đừng trả `207` với vài 200/vài 409 và ngụ ý đã commit một phần.

### 4.1. URI và request cho một atomic batch

~~~http
POST /v1/inventory-reservations/batches HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: 920bfec1-b36f-4d45-b00c-c92715f7f733
Content-Type: application/json
Accept: application/json

{
  "items": [
    {"sku":"SKU-A","quantity":2},
    {"sku":"SKU-B","quantity":1},
    {"sku":"SKU-C","quantity":5}
  ]
}
~~~

Endpoint này **luôn atomic**, vì vậy request không có field `atomic`. Nếu cho phép cả `atomic=true` lẫn `atomic=false` trong một endpoint khác, phải xác định riêng hợp đồng status, body và retry cho **từng mode**, tránh dữ liệu thành công từng phần bị trình bày như all-or-nothing.

Batch thành công toàn bộ:

~~~http
HTTP/1.1 201 Created
Location: /v1/inventory-reservations/batches/batch_451
Content-Type: application/json

{
  "batchId": "batch_451",
  "status": "COMMITTED",
  "reservations": [
    {"sku":"SKU-A","reservationId":"res_1","quantity":2},
    {"sku":"SKU-B","reservationId":"res_2","quantity":1},
    {"sku":"SKU-C","reservationId":"res_3","quantity":5}
  ]
}
~~~

Nếu thiếu stock ở SKU-C, không commit SKU-A/B:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/insufficient-stock",
  "title": "Cannot reserve entire batch",
  "status": 409,
  "code": "BATCH_REJECTED",
  "detail": "Không thể giữ hàng cho toàn bộ yêu cầu.",
  "failedItems": [{"index":2,"code":"INSUFFICIENT_STOCK"}]
}
~~~

`failedItems` là extension do API định nghĩa, không phải member chuẩn bắt buộc của RFC 9457. `index` tính từ 0 theo thứ tự mảng input; không nhất thiết trả số tồn kho thật, ID tenant khác hoặc các lý do nhạy cảm. Client biết **không reservation nào** được tạo, không phải “2/3 thành công”.

### 4.2. Batch không nguyên tử cần hợp đồng khác

Nếu yêu cầu thật sự là “xử lý từng import row độc lập”, có thể công bố `POST /v1/import-jobs` trả **202 Accepted**, cho client theo dõi `GET /v1/import-jobs/{id}`; khi job hoàn thành, resource kết quả nêu success/failure từng item. Tính nguyên tử lúc đó có thể chỉ là **mỗi item**, không phải toàn job.

Ví dụ kết quả partial batch (một API có contract như vậy):

~~~json
{
  "mode": "BEST_EFFORT",
  "results": [
    {"index":0,"status":201,"id":"res_1"},
    {"index":1,"status":201,"id":"res_2"},
    {"index":2,"status":409,"code":"INSUFFICIENT_STOCK"}
  ]
}
~~~

Đừng dùng một `500` “mơ hồ” cho batch đã commit vài mục nếu client cần đối soát. Đặt **operation ID**, trạng thái rõ và idempotency ở cấp item/batch để tránh phát lại các item đã thành công khi response bị mất.

## 5. Giới hạn batch và kiểm tra **mọi item**

Atomic batch không phải giấy phép để nhận hàng chục nghìn thao tác trong một transaction. Khi batch lớn, transaction giữ locks lâu, tốn RAM, tăng khả năng deadlock và làm phức tạp retry.

**Đặt chính sách tối thiểu:**

1. Giới hạn **số item** (ví dụ 1–50 tùy workload), **byte size**, số SKU phân biệt, số reservations và tổng số lượng.
2. Xác thực và kiểm quyền **từng SKU/resource**, không chỉ `hasAuthority("inventory.reserve")` ở controller.
3. Từ chối duplicate item không được định nghĩa rõ; nếu gộp SKU trùng, phải công bố cách cộng và overflow.
4. Validate toàn bộ shape, kiểu dữ liệu, số lượng dương, định dạng SKU và invariant xuyên item trước khi mutate.
5. Khi transaction bắt đầu, đọc trạng thái hiện hành và giữ lock/compare-and-swap cần thiết; không dựa hoàn toàn vào dữ liệu preflight trước đó.
6. Có **timeout** và quota concurrency theo tenant để batch chậm không giữ DB connection mãi.

Ví dụ `items=[{"sku":"A","quantity":2},{"sku":"A","quantity":3}]`: nếu vòng lặp trừ stock hai lần nhưng response ghi một reservation, hệ thống rất dễ sai lệch. Chọn **reject duplicate** bằng `400` hoặc **normalize có hợp đồng** rồi validate tổng. Không được để tràn số khi cộng quantity hoặc bỏ qua giới hạn tổng.

### 5.1. Quyền trên từng mục và chống BOLA

Mỗi item phải nằm trong tenant mà access token đã xác thực có quyền. Không đọc `tenantId` từ body và tin ngay; dùng `tenant_id`/membership đã được xác minh hoặc identity được resolve từ server. Truy vấn phải ràng buộc tenant ngay ở repository, sau đó kiểm policy theo resource và action.

Nếu một item là của tenant khác, toàn bộ atomic batch phải bị **từ chối và rollback**. Có thể trả **404** cho resource không được công bố để không lộ tồn tại, hoặc **403** nếu policy công khai quyền rõ ràng. Không trả trong `failedItems` tên tenant hoặc số dư hàng tồn kho của người khác.

### 5.2. Bước validate ngoài transaction không đủ

Kiểm stock=5 ở thời điểm nhận request không bảo đảm stock vẫn là 5 khi ghi. Hai batch đồng thời có thể cùng vượt qua validation. Việc quyết định **đủ tồn kho** phải gắn với một thao tác đồng bộ hóa **ngay trong transaction**: row lock, optimistic version + retry toàn transaction có giới hạn, hoặc một câu SQL conditional update `WHERE available >= quantity` kiểm row count.

Tối ưu để giảm lock time: parse/schema, auth tổng quát, quota, số item và duplicate kiểm **trước transaction**; nhưng kiểm **resource ownership/current stock/invariant** phải được xác nhận lại khi thực hiện write.

## 6. Ranh giới transaction và những “nguyên tử giả”

Một số code có vẻ atomic nhưng thực tế không đảm bảo:

~~~java
for (ReservationItem item : request.items()) {
    try {
        reservationRepository.save(makeReservation(item));
    } catch (Exception ex) {
        // Ghi nhận lỗi rồi tiếp tục => không còn atomic batch.
    }
}
~~~

Nếu mỗi `save` được gọi qua một service có transaction độc lập, các item trước có thể đã commit trước khi item sau lỗi. Nếu đặt `@Transactional` ở method nhưng **bắt/nuốt exception** và vẫn trả thành công, transaction có thể commit thay đổi một phần (hoặc bị đánh dấu rollback-only và ném lỗi lúc commit), tùy loại exception và propagation.

Lỗi thiết kế khác:

- Gọi `@Transactional` method **từ chính object đó** (self-invocation) khi dùng Spring AOP proxy thông thường có thể không đi qua proxy; annotation không áp dụng như mong đợi.
- Lấy `@Transactional(readOnly=true)` làm bằng chứng không có side effect; đó chủ yếu là hint/tùy implementation, không phải authorization enforcement.
- Dùng `REQUIRES_NEW` cho mỗi item rồi gọi từ batch: mỗi item có commit riêng, phá vỡ all-or-nothing trừ khi contract yêu cầu partial.
- Ghi ra DB A và DB B với một local transaction manager rồi gọi đó là “atomic across DBs”.
- Gửi message/email **trước commit**: nếu transaction rollback, side effect đã đi ra ngoài.

Đặt transaction ở **application service boundary** gọi từ controller qua Spring-managed bean; tất cả thao tác DB phải dùng cùng transaction manager và connection context phù hợp. Mặc định Spring rollback cho `RuntimeException` và `Error`, không tự rollback mọi checked exception trừ khi được cấu hình (`rollbackFor`). Thất bại ở flush/commit phải được coi là thất bại transaction ngay cả khi code trước đó đã chạy xong.

## 7. Java/Spring: cập nhật một resource theo transaction và ETag

Ví dụ dùng Spring Boot 3.x, Java 17, Spring Security 6 và JPA. Endpoint `PUT /v1/orders/{id}/delivery-preferences` thay **toàn bộ** cặp thuộc tính giao hàng (note và address) của một order; không cho client gửi `tenantId`, `status`, `totalAmount`. Khác với PATCH, PUT ở đây có contract **replacement của subresource delivery-preferences**. Các lớp entity/repository và security configuration chỉ được minh họa phần liên quan; dự án thực cần ánh xạ DB và bật method security.

### 7.1. Request DTO, auth và HTTP boundary

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.*;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

record DeliveryPreferences(
    @Size(max = 500) String deliveryNote,
    @NotBlank String shippingAddressId
) {}

record OrderView(
    String id, String status, String deliveryNote,
    String shippingAddressId, long version
) {}

record UpdatedOrder(OrderView view, String etag) {}

@RestController
@RequestMapping("/v1/orders")
class OrderResource {
    private final OrderCommandService commands;

    OrderResource(OrderCommandService commands) {
        this.commands = commands;
    }

    @PutMapping(path = "/{id}/delivery-preferences",
                consumes = "application/json",
                produces = "application/json")
    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    ResponseEntity<OrderView> replaceDelivery(
            @PathVariable String id,
            @RequestHeader(value = HttpHeaders.IF_MATCH,
                           required = false) String ifMatch,
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody DeliveryPreferences body) {
        String tenant = jwt.getClaimAsString("tenant_id");
        UpdatedOrder updated = commands.replaceDelivery(
            tenant, jwt.getSubject(), id, ifMatch, body);
        return ResponseEntity.ok()
            .eTag(updated.etag())
            .cacheControl(CacheControl.noStore())
            .body(updated.view());
    }
}
~~~

Vì `If-Match` được khai `required=false`, service có thể trả **428** khi thiếu thay vì để Spring tự trả 400 trước khi vào nghiệp vụ. `jwt` chỉ đáng tin nếu Resource Server đã kiểm issuer/audience/signature/token expiry. `@PreAuthorize` là quyền thao tác, còn kiểm tenant, owner và quan hệ được đặt tại service.

### 7.2. Service áp dụng tất cả thay đổi hoặc rollback

~~~java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {
    private final OrderRepository orders;
    private final AddressRepository addresses;
    private final EntityManager em;

    public OrderCommandService(
            OrderRepository orders,
            AddressRepository addresses,
            EntityManager em) {
        this.orders = orders;
        this.addresses = addresses;
        this.em = em;
    }

    @Transactional
    public UpdatedOrder replaceDelivery(
            String tenant, String caller, String id,
            String ifMatch, DeliveryPreferences input) {
        if (tenant == null || tenant.isBlank()) {
            throw new ForbiddenOperationException();
        }
        if (ifMatch == null || ifMatch.isBlank()) {
            throw new PreconditionRequiredException();
        }

        OrderEntity order = orders.findByIdAndTenantId(id, tenant)
            .orElseThrow(OrderNotFoundException::new);
        if (!order.getOwnerUserId().equals(caller)) {
            throw new OrderNotFoundException(); // Che sự tồn tại.
        }
        String current = etag(order.getId(), order.getVersion());
        if (!current.equals(ifMatch)) {
            throw new StaleVersionException();
        }
        if (order.getStatus() != OrderStatus.DRAFT) {
            throw new OrderStateConflictException();
        }
        AddressEntity address = addresses
            .findByIdAndTenantId(input.shippingAddressId(), tenant)
            .orElseThrow(OrderNotFoundException::new);
        if (!address.getOwnerUserId().equals(caller)) {
            throw new OrderNotFoundException();
        }

        order.setDeliveryNote(input.deliveryNote());
        order.setShippingAddressId(address.getId());
        em.flush(); // Phát hiện lỗi constraint/version trước khi trả DTO.
        OrderView view = new OrderView(
            order.getId(), order.getStatus().name(),
            order.getDeliveryNote(), order.getShippingAddressId(),
            order.getVersion());
        return new UpdatedOrder(
            view, etag(order.getId(), order.getVersion()));
    }

    private static String etag(String id, long version) {
        return "\"order-" + id + "-v" + version + "\"";
    }
}
~~~

Các `OrderEntity`, `AddressEntity`, repository và exception classes được định nghĩa riêng trong project. `OrderEntity.version` cần ánh xạ `@Version`. Khi hai transaction cùng đọc v7 rồi cùng cập nhật, DB/JPA phải phát hiện conflict ở flush/commit hoặc sử dụng lock. `em.flush()` **không phải commit**; commit diễn ra khi proxy transaction hoàn tất. Controller nhận kết quả bình thường **sau khi method service hoàn thành transaction** nếu được gọi qua proxy Spring.

**Giới hạn ví dụ:** ETag từ version là một thiết kế đơn giản khi representation và version nhất quán; nếu một số field được trả nhưng thay đổi không làm version tăng, hoặc representation theo quyền thay đổi, validator có thể không phản ánh nội dung thực. Không dùng ETag vừa để giấu ownership vừa làm access token. Với replacement không thay giá trị, JPA có thể không tăng version; đó không phá idempotent effect, nhưng contract ETag vẫn cần kiểm chứng.

## 8. Java/Spring: một atomic batch giữ hàng

Batch chỉ hoạt động atomic khi **mọi write ở cùng transaction DB**. Ví dụ sau cố ý giới hạn 30 items, không cho SKU trùng, khóa row tồn kho theo thứ tự SKU và tạo reservation records trong một transaction.

### 8.1. DTO request và endpoint

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;
import java.net.URI;
import org.springframework.http.*;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

record ReserveLine(
    @NotBlank String sku,
    @Min(1) int quantity
) {}

record AtomicReserveRequest(
    @NotEmpty @Size(max = 30)
    List<@Valid ReserveLine> items
) {}

record ReservedLine(String sku, String reservationId, int quantity) {}
record ReservedBatch(
    String batchId, String status, List<ReservedLine> reservations
) {}

@RestController
@RequestMapping("/v1/inventory-reservations")
class ReservationResource {
    private final InventoryCommandService service;

    ReservationResource(InventoryCommandService service) {
        this.service = service;
    }

    @PostMapping(path = "/batches", consumes = "application/json")
    @PreAuthorize("hasAuthority('SCOPE_inventory.reserve')")
    ResponseEntity<ReservedBatch> reserve(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody AtomicReserveRequest request) {
        String tenant = jwt.getClaimAsString("tenant_id");
        ReservedBatch created = service.reserveAtomically(
            tenant, jwt.getSubject(), request);
        return ResponseEntity.created(URI.create(
            "/v1/inventory-reservations/batches/"
                + created.batchId())).body(created);
    }
}
~~~

Endpoint này minh họa **all-or-nothing**; sample chưa đọc `Idempotency-Key`, nên **chưa an toàn để retry POST sau timeout**. Để triển khai thực tế phải thêm dedup record + fingerprint vào cùng transaction, như mục 10.

### 8.2. Service và row lock

~~~java
import java.util.*;
import java.util.stream.Collectors;
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryCommandService {
    private final StockRepository stocks;
    private final ReservationRepository reservations;
    private final InventoryAuthorization policy;
    private final EntityManager em;

    public InventoryCommandService(
            StockRepository stocks,
            ReservationRepository reservations,
            InventoryAuthorization policy,
            EntityManager em) {
        this.stocks = stocks;
        this.reservations = reservations;
        this.policy = policy;
        this.em = em;
    }

    @Transactional
    public ReservedBatch reserveAtomically(
            String tenant, String caller,
            AtomicReserveRequest request) {
        if (tenant == null || tenant.isBlank()) {
            throw new ForbiddenOperationException();
        }
        List<ReserveLine> lines = request.items();
        if (lines == null || lines.isEmpty()
                || lines.size() > 30) {
            throw new InvalidBatchException();
        }

        Set<String> seen = new HashSet<>();
        for (ReserveLine line : lines) {
            if (line == null || line.sku() == null
                    || line.sku().isBlank()
                    || line.quantity() <= 0
                    || !seen.add(line.sku())) {
                throw new InvalidBatchException();
            }
        }
        List<ReserveLine> ordered = lines.stream()
            .sorted(Comparator.comparing(ReserveLine::sku))
            .toList();
        String batchId = UUID.randomUUID().toString();
        List<ReservedLine> results = new ArrayList<>();

        for (ReserveLine line : ordered) {
            // Method repository dùng PESSIMISTIC_WRITE trên đúng row.
            StockEntity stock = stocks
                .findLockedByTenantIdAndSku(tenant, line.sku())
                .orElseThrow(StockNotFoundException::new);
            policy.checkReserve(caller, tenant, stock);
            if (stock.getAvailable() < line.quantity()) {
                throw new InsufficientStockException(line.sku());
            }
            stock.setAvailable(
                stock.getAvailable() - line.quantity());
            String reservationId = UUID.randomUUID().toString();
            reservations.save(new ReservationEntity(
                reservationId, batchId, tenant,
                line.sku(), line.quantity()));
            results.add(new ReservedLine(
                line.sku(), reservationId, line.quantity()));
        }
        em.flush(); // Constraint failures sẽ rollback toàn transaction.
        return new ReservedBatch(
            batchId, "COMMITTED", List.copyOf(results));
    }
}
~~~

Repository dùng khóa ghi JPA, ví dụ một method có `@Lock(LockModeType.PESSIMISTIC_WRITE)` và query ràng buộc **tenant + SKU**:

~~~java
import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

interface StockRepository extends JpaRepository<StockEntity, String> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select s from StockEntity s
        where s.tenantId = :tenant and s.sku = :sku
        """)
    Optional<StockEntity> findLockedByTenantIdAndSku(
        @Param("tenant") String tenant,
        @Param("sku") String sku);
}
~~~

`InventoryAuthorization` kiểm quyền **trên từng stock resource**. `ReservationEntity` có constructor/schema được định nghĩa riêng. Các inventory rows phải tồn tại và có unique constraint thích hợp trên `(tenant_id, sku)` để một SKU không khớp nhiều rows. Tất cả repositories sử dụng **cùng DB transaction manager**; nếu `reservations.save` phát sinh lỗi constraint ở item cuối, toàn bộ stock updates cũng phải rollback.

Việc khóa theo thứ tự cố định giảm nguy cơ deadlock giữa batches có cùng SKU, nhưng **không loại bỏ mọi deadlock** khi còn những code path/foreign key khác. Nên có DB constraints/invariant (ví dụ available >= 0 khi DB hỗ trợ), transaction timeout, deadlock handling và metrics. Khi DB báo deadlock hoặc lock timeout, có thể retry **toàn transaction** trong lớp orchestration ngoài transaction, có ngân sách và idempotency; không chỉ chạy lại item cuối.

## 9. Atomicity, isolation và lỗi commit: các điểm cần kiểm soát

### 9.1. Transaction đã bắt đầu không bảo đảm điều kiện nghiệp vụ đúng

Ngay trong transaction vẫn phải kiểm tra:

- **Unique và foreign key constraints:** một item không được trỏ tới object của tenant khác hoặc một product đã bị xóa; không dựa vào validation phía frontend.
- **Balance/inventory invariant:** giá trị không âm sau phép trừ; thêm kiểm soát concurrency ở DB.
- **Lifecycle:** không sửa đơn đã giao, không giữ hàng từ kho bị khóa, không chuyển trạng thái trái phép.
- **Quyền thay đổi giữa chừng:** membership hoặc resource state được đọc/kiểm ngay trước khi ghi, theo isolation và chính sách thu hồi quyền.
- **Deadlock và timeout:** DB có thể abort transaction; lớp HTTP phải đưa lỗi phù hợp và không giả định đã lưu một phần.

Transaction isolation mặc định nhiều DB là `READ_COMMITTED`, nhưng hành vi tùy vendor/cấu hình. `@Transactional(isolation = Isolation.SERIALIZABLE)` có thể giải quyết một số bất thường nhưng tăng lock/conflict, không thay kiểm invariant; có thể cần retry **toàn giao dịch** khi serialization failure. Đừng tăng isolation toàn hệ thống mà chưa đo tải.

### 9.2. Response chỉ được coi thành công sau commit

Khi service dùng `@Transactional` qua Spring proxy, transaction thường commit khi method service trả về và interceptor hoàn tất. Nếu controller trả 201 sau khi service call hoàn tất thành công, commit đã được xử lý. Tuy vậy:

- `save`/`flush` **chưa phải commit**. DB có thể lỗi tại commit hoặc sau đó mạng trả response lỗi.
- Một method `@Async`/event subscriber nằm ngoài transaction có thể tiếp tục chạy sau response; phải mô tả đây là xử lý bất đồng bộ, không đưa nó vào lời hứa atomic DB.
- Nếu streaming response bắt đầu trước khi xử lý batch hoàn tất, không thể chắc chắn đổi status thành 409 khi item cuối thất bại.

Do đó atomic batch đồng bộ nên **tính toán và commit trước khi xuất response body**; batch quá dài nên dùng operation resource và contract `202 Accepted` riêng.

### 9.3. Phân biệt “không xảy ra”, “thất bại” và “không biết kết quả”

| Quan sát của client | Có biết DB đã commit không? | Hành vi đề xuất |
|---|---|---|
| Server trả `409 BATCH_REJECTED` theo contract | Có: batch đã rollback và không tạo reservation | Sửa request/stock |
| Server trả `201 COMMITTED` | Có: server cam kết kết quả đã lưu khi trả | Dùng Location/result |
| TCP reset/timeout sau khi gửi toàn body | **Không chắc** | Truy vấn operation, hoặc retry cùng idempotency key |
| `503` từ gateway khi upstream vẫn xử lý | **Không chắc** | Không phát lại POST bằng key mới |
| Client hủy request sau khi server nhận | **Không chắc** | Cancellation không mặc nhiên rollback transaction đã commit |

Không suy ra “timeout = rollback”. Trong hệ thống nhiều máy, client không thể biết kết quả chỉ bằng việc không nhận phản hồi; **idempotency và truy vấn trạng thái** mới giải quyết sự mơ hồ.

## 10. Idempotency và kết quả bền vững cho atomic batch

Ví dụ POST giữ hàng có side effect. Nếu client retry với một key mới sau timeout, batch có thể bị giữ hàng **hai lần** dù mỗi execution riêng lẻ đều atomic. Vì vậy yêu cầu thêm một **idempotency contract**:

~~~http
POST /v1/inventory-reservations/batches HTTP/1.1
Idempotency-Key: 920bfec1-b36f-4d45-b00c-c92715f7f733
Content-Type: application/json
Authorization: Bearer <access-token>

{"items":[{"sku":"SKU-A","quantity":2},{"sku":"SKU-B","quantity":1}]}
~~~

Server thiết kế bảng/trạng thái tương đương:

~~~text
batch_request
  (tenant_id, client_id, operation, idempotency_key) UNIQUE
  request_fingerprint
  batch_id
  state: IN_PROGRESS | COMMITTED | REJECTED
  response_status / response_body_location
  created_at / expires_at
~~~

Chính sách:

1. Khóa identity của key theo **tenant + client + operation** và fingerprint của normalized request. Không để một tenant dùng lại kết quả của tenant khác.
2. **Cùng key + cùng payload**: nếu đã COMMITTED, trả lại kết quả theo contract; nếu đang IN_PROGRESS, trả trạng thái poll/retry phù hợp; không chạy batch thứ hai.
3. **Cùng key + payload khác**: từ chối, thường `409 Conflict`, không sửa reservation nào.
4. Lưu reservation/batch result **cùng transaction** với bản ghi kết quả idempotency khi có thể. Nếu cần bản ghi IN_PROGRESS bền qua transaction đang chạy, thiết kế riêng cách lease/fencing và xử lý crash; không tạo hai đường commit không liên kết.
5. Công bố retention/TTL, hành vi key hết hạn, request size limit, kết quả lỗi có replay hay không; đừng cam kết “exactly once mãi mãi”.

Các request đồng thời dùng **cùng key** phải bị chặn nhờ unique constraint/serialization/admission control tại DB, không chỉ dùng `ConcurrentHashMap` trong một JVM (vì service có nhiều instance). Một key được phát lại không bao giờ được tính là bằng chứng caller còn quyền: request mới vẫn phải xác thực, kiểm scope/tenant và chính sách xem kết quả.

Trong ví dụ ở mục 8, `batchId` chỉ có ý nghĩa làm `Location` **nếu batch resource thực sự được lưu** và `GET /v1/inventory-reservations/batches/{id}` được định nghĩa có kiểm quyền. Cần lưu batch header/result trong DB hoặc một operation store bền, không trả link đến resource không thể truy cập.

## 11. Transactional outbox và giới hạn side effect bên ngoài DB

Nếu sau khi giữ hàng cần gửi `InventoryReserved` sang Kafka để kho vận xử lý, cách này **không an toàn**:

~~~java
@Transactional
public void reserveAndPublish(...) {
    saveAllReservations(...);
    kafkaTemplate.send("inventory", event); // Có thể gửi trước commit.
    // Commit có thể thất bại, nhưng event đã được phát.
}
~~~

Nếu DB rollback còn event đã phát, service kho vận có thể tin rằng hàng đã được giữ. Ngược lại, commit DB thành công nhưng publish thất bại cũng làm mất event. **Transactional outbox** giải bài toán này bằng cách ghi **business changes + event record vào cùng DB transaction**:

~~~mermaid
sequenceDiagram
    participant API as Inventory API
    participant DB as DB (reservation + outbox)
    participant W as Outbox worker
    participant MQ as Message broker
    API->>DB: BEGIN; stock updates; reservations; outbox event
    DB-->>API: COMMIT
    API-->>API: Trả 201 (commit DB đã thành công)
    W->>DB: Đọc event chưa phát
    W->>MQ: Publish InventoryReserved
    MQ-->>W: Ack
    W->>DB: Mark delivered
~~~

Outbox bảo đảm **không ghi business state mà thiếu event intent** trong cùng transaction DB. Nó **không bảo đảm broker nhận đúng một lần**: worker có thể publish rồi crash trước khi mark delivered, dẫn đến gửi lại. Consumer cần xử lý **idempotently** bằng event ID/dedup; thứ tự event và retry/backoff cũng cần contract riêng.

Không thể “rollback email đã gửi” bằng JPA. Với thanh toán, shipping hay service nhiều database, dùng workflow/Saga với hành động bù trừ và operation status; **compensation không biến toàn bộ hệ thành một ACID transaction**. Khi user đòi atomic tuyệt đối across DB + payment provider, phải xác định lại ranh giới khả thi và các trạng thái nghiệp vụ trung gian.

## 12. HTTP errors, quyền và quan sát

| Lỗi | Status thường phù hợp | Cam kết atomic của API |
|---|---|---|
| JSON malformed, batch rỗng, SKU trùng | `400 Bad Request` | Không tạo reservation |
| Token thiếu/hết hạn | `401 Unauthorized` | Chưa chạy business command |
| Không có scope/action privilege | `403 Forbidden` | Không sửa dữ liệu |
| SKU ngoài tenant/không được công bố | `404 Not Found` theo policy | Không item nào được commit |
| Tồn kho không đủ/trạng thái đã thay đổi | `409 Conflict` | Rollback toàn batch |
| Thao tác hợp cấu trúc nhưng vi phạm quy tắc được định nghĩa | `422 Unprocessable Content` nếu contract chọn | Không sửa |
| ETag `If-Match` stale | `412 Precondition Failed` | Không update resource |
| Thiếu precondition bắt buộc | `428 Precondition Required` | Không update resource |
| Request/batch vượt size, item limit | `413` cho body lớn; `400/422` cho số item | Từ chối trước commit |
| Rate limit/concurrency quota | `429 Too Many Requests` | Không chạy nếu bị chặn từ admission |
| DB timeout/resource unavailable | `503` hoặc `500` tùy loại | Phải xác định outcome, không trả false success |

Lỗi có thể dùng `application/problem+json` theo RFC 9457, với `type/title/status/detail` và extension `code/failedItems/traceId` đã lọc an toàn. Đừng đưa SQL, số dư stock của tenant khác, raw body hay stack trace vào lỗi. `409` không đồng nghĩa luôn retry: với stock không đủ, client cần thay yêu cầu; deadlock có thể retry ngắn **toàn batch** nếu operation có idempotency và ngân sách.

Chỉ gửi status 201 khi **toàn bộ batch đã commit** theo hợp đồng. Nếu dùng 202 thì body phải chỉ operation resource, không ghi `COMMITTED` trong khi xử lý nền còn chưa xong. Với dữ liệu riêng tư, cân nhắc `Cache-Control: no-store` cho status/result và xác thực từng lần đọc operation.

**Quan sát hệ thống** nên đo: batch size, tổng transaction duration, lock wait, deadlock/retry, rollback theo reason, idempotency replay/conflict, outbox lag, số lượng item commit/được từ chối. Log dùng `requestId/operationId` được kiểm soát, không log token, thông tin thanh toán hay dữ liệu người dùng.

## 13. OpenAPI 3.1: mô tả all-or-nothing thành contract

OpenAPI phải nêu rõ batch có được partial success không, giới hạn item và các mã lỗi, thay vì để frontend đoán từ một response 200.

~~~yaml
openapi: 3.1.0
info:
  title: Inventory API
  version: 1.0.0
paths:
  /v1/inventory-reservations/batches:
    post:
      summary: Giữ hàng cho toàn bộ batch trong một transaction
      description: |
        Atomic all-or-nothing: một item không hợp lệ hoặc thiếu tồn kho
        khiến tất cả reservations trong batch không được commit.
        Cùng idempotency key và cùng body trả lại cùng logical result.
      security: [{bearerAuth: []}]
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: {type: string, minLength: 1, maxLength: 128}
      requestBody:
        required: true
        content:
          application/json:
            schema: {$ref: '#/components/schemas/ReserveBatch'}
      responses:
        '201':
          description: Toàn bộ reservations đã commit
          headers:
            Location:
              schema: {type: string, format: uri-reference}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/ReservedBatch'}
        '400': {$ref: '#/components/responses/Problem'}
        '401': {description: Chưa xác thực}
        '403': {description: Thiếu quyền}
        '404': {description: Resource không được công bố}
        '409': {$ref: '#/components/responses/Problem'}
        '429': {description: Quá tải hoặc vượt quota}
        '503': {$ref: '#/components/responses/Problem'}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
  schemas:
    ReserveBatch:
      type: object
      additionalProperties: false
      required: [items]
      properties:
        items:
          type: array
          minItems: 1
          maxItems: 30
          items:
            type: object
            additionalProperties: false
            required: [sku, quantity]
            properties:
              sku: {type: string, minLength: 1}
              quantity: {type: integer, minimum: 1}
    ReservedBatch:
      type: object
      required: [batchId, status, reservations]
      properties:
        batchId: {type: string}
        status: {type: string, enum: [COMMITTED]}
        reservations:
          type: array
          items: {type: object}
  responses:
    Problem:
      description: Lỗi không làm commit một phần batch
      content:
        application/problem+json:
          schema:
            type: object
            required: [type, title, status]
            properties:
              type: {type: string, format: uri-reference}
              title: {type: string}
              status: {type: integer}
              detail: {type: string}
              code: {type: string}
              failedItems:
                type: array
                items:
                  type: object
                  properties:
                    index: {type: integer, minimum: 0}
                    code: {type: string}
~~~

Đây là bản trích hợp đồng, không phải hệ thống chạy được chỉ nhờ schema. Ví dụ code mục 8 **chưa triển khai dedup Idempotency-Key**, trong khi OpenAPI **yêu cầu** header đó — cần làm mục 10 trước khi công bố API theo OpenAPI này. Ngoài ra cần nêu rõ header `Idempotency-Key` không tự ngăn duplicate nếu server chưa lưu key bền, và cần test mapping từ mã lỗi domain sang `ProblemDetail`.

## 14. Kiểm thử rollback, tenant isolation và concurrency

**Test HTTP status chưa đủ.** Một endpoint trả 409 đúng nhưng vẫn trừ stock của SKU-A là lỗi nguyên tử nghiêm trọng. Kiểm thử phải đọc lại **database sau request**, với dữ liệu được commit/rollback thật, kể cả lỗi cuối transaction.

| Tình huống | Kỳ vọng cần chứng minh |
|---|---|
| PUT đổi note + address hợp lệ | 200, cả hai field đổi và ETag mới |
| PUT có address ngoài quyền | 404/403, **note cũng không đổi** |
| PUT `If-Match` stale | 412, không thay đổi DB |
| PUT thiếu `If-Match` bắt buộc | 428, không thay đổi DB |
| Patch JSON nhiều operation, `test` thất bại giữa chừng | Không operation nào đã commit |
| Atomic batch 3 SKU đủ hàng | 201, cả ba stock giảm đúng và tạo ba reservations |
| SKU cuối thiếu hàng | 409, **không giảm SKU đầu**, không có reservation mới |
| Một SKU ngoài tenant | 404/403, không item nào commit, không lộ dữ liệu tenant |
| Batch có SKU trùng hoặc số lượng 0 | 400, DB không đổi |
| Unique/FK constraint lỗi ở flush/commit | 5xx hoặc 409 theo domain, toàn transaction rollback |
| Hai batch giữ cùng SKU song song | Tổng reservation không vượt stock, không âm |
| Hai request cùng key/body | Một logical batch, cùng batch/result |
| Cùng key khác body | 409, không thêm reservation |
| Response bị mất sau commit | Retry cùng key không giữ hàng lần hai |
| Event publish thất bại sau commit DB | Outbox vẫn giữ event để retry, không mất intent |

### 14.1. MockMvc + database test cho batch lỗi

Giả định fixture DB có `tenant=t_1`, stock A=10, B=10, C=1; toàn bộ reservation count ban đầu bằng 0. Test chạy service/repository thật và đã cấu hình Spring Security Test:

~~~java
// @SpringBootTest + @AutoConfigureMockMvc; không đặt @Transactional
// trên test vì có thể che ranh giới commit của service.
// import static org.springframework.security.test.web.servlet
//     .request.SecurityMockMvcRequestPostProcessors.jwt;
// import static org.springframework.test.web.servlet.request
//     .MockMvcRequestBuilders.post;
// import static org.springframework.test.web.servlet.result
//     .MockMvcResultMatchers.*;

mockMvc.perform(post("/v1/inventory-reservations/batches")
        .with(jwt().jwt(token -> token
            .subject("user_1")
            .claim("tenant_id", "t_1"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_inventory.reserve")))
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "items": [
                {"sku":"SKU-A","quantity":2},
                {"sku":"SKU-B","quantity":1},
                {"sku":"SKU-C","quantity":5}
              ]
            }
            """))
    .andExpect(status().isConflict())
    .andExpect(jsonPath("$.code").value("BATCH_REJECTED"));

// Dùng cùng test DB đã seed, đọc qua JDBC sau request:
assertEquals(10, availableOf("t_1", "SKU-A"));
assertEquals(10, availableOf("t_1", "SKU-B"));
assertEquals(1, availableOf("t_1", "SKU-C"));
assertEquals(0L, reservationCount("t_1"));
~~~

`availableOf(...)` và `reservationCount(...)` là helpers đọc DB test cần tự triển khai; `BATCH_REJECTED` phải được mapper exception thiết lập. Không mock `InventoryCommandService` trong test rollback vì mock không thể chứng minh transaction thật. Dùng Testcontainers/DB tương ứng production để kiểm pessimistic lock, foreign key và deadlock. Hãy test **DB commit failure**, không chỉ exception ném trước khi gọi `save`.

### 14.2. Test đồng thời và kiểm vùng không xác định

Cho hai request cùng giữ 4 sản phẩm khi stock ban đầu là 5. Chạy đồng thời bằng hai transaction/connection độc lập, một request được commit, request còn lại phải thất bại hoặc có kết quả tương đương theo contract. Assert `available >= 0` và tổng quantity đã giữ không vượt 5. Đừng dùng `@Transactional` chung trên method test khiến cả hai tác vụ vô tình ở cùng transaction hoặc dữ liệu chưa commit.

Test idempotency với **server thực sự lưu key**, hai request cùng key được gửi đồng thời; đừng chỉ test tuần tự. Với mô phỏng timeout sau commit, gọi endpoint qua HTTP test server/proxy có thể **cắt response** sau khi DB commit, rồi gửi lại cùng key. Xác nhận không tạo batch/reservation thứ hai. Test có fake clock/lease nếu dùng IN_PROGRESS/expiry và cả case key hết hạn.

## 15. Bài tập: thiết kế batch chuyển điểm thưởng

**Bối cảnh:** hệ thống loyalty có API chuyển điểm từ tài khoản A sang B và một batch thực hiện ba chuyển khoản. Độ tin cậy yêu cầu:

- Tổng điểm không được tự sinh ra hoặc mất đi trong DB.
- Mỗi chuyển khoản phải kiểm quyền tài khoản nguồn và tenant của cả hai đầu.
- Atomic mode: **một chuyển khoản thất bại thì không chuyển khoản nào được ghi**.
- Client có thể timeout ngay sau khi server commit; request có `Idempotency-Key`.

**Yêu cầu thực hiện:**

1. Định nghĩa `POST /v1/point-transfers/batches` với body và success/error response, giới hạn số item, duplicate transfer ID và trường `atomic` nếu thực sự hỗ trợ nhiều mode.
2. Viết bảng invariant: tổng điểm, không âm, quyền tenant, trạng thái tài khoản và version.
3. Thiết kế service `@Transactional` đọc/khóa tất cả accounts theo thứ tự ổn định, validate toàn batch rồi cập nhật số dư và lưu transfer records.
4. Nêu cụ thể vị trí `@Version`/row lock/conditional update; xử lý hai batch đồng thời chuyển từ cùng tài khoản.
5. Thiết kế idempotency store với unique key, fingerprint, TTL và truy vấn trạng thái sau timeout.
6. Nếu gửi email thông báo cho người nhận, dùng outbox; giải thích vì sao email không nằm trong rollback DB.
7. Viết ít nhất 10 test gồm item cuối thất bại, cross-tenant, commit failure, concurrency, timeout sau commit, key payload mismatch và consumer event duplicate.

**Câu hỏi tự kiểm:** Nếu hai chuyển khoản đã thành công, chuyển khoản thứ ba thiếu điểm, bạn trả gì? Trong **atomic mode**, rollback cả ba và trả lỗi toàn batch (ví dụ 409). Trong **best-effort mode**, trả kết quả từng mục theo contract; không được dùng chung cùng một lời hứa “all-or-nothing” cho hai mode.

## 16. Tổng kết

**Tính nguyên tử gắn với ranh giới commit cụ thể.** Một PUT/PATCH có thể thay nhiều field nhưng không được để resource ở trạng thái cập nhật nửa vời; một atomic batch phải commit **tất cả item hoặc không item nào**. `@Transactional` giúp tổ chức thay đổi trong một DB, còn **locking/`@Version`, constraints và validation** mới bảo vệ invariant khi có cạnh tranh.

Phía HTTP cần công bố mode batch, status/Problem Details, conditional requests, idempotency và operation monitor. Phía bảo mật phải kiểm **từng resource/item**; phía vận hành phải kiểm rollback, race, commit failure và tác động ngoài DB. Với message/email/service khác, dùng outbox hoặc Saga phù hợp, không gọi chúng là một transaction ACID chỉ vì request bắt đầu từ cùng một endpoint.
