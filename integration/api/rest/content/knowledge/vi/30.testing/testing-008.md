# Kiểm thử ETag, 304, If-Match và xung đột đồng thời

> **Module:** `INTEGRATION_API_REST` — chương **Kiểm thử**. Bài học thực hành kiểm tra HTTP conditional requests trong REST API bằng Java 17, Spring Boot 3, Spring MVC, Spring Security, Spring Data JPA và database thật. Trọng tâm: **ETag, `If-None-Match`/`304 Not Modified`, `If-Match`/`412 Precondition Failed` và tình huống hai client cập nhật cùng tài nguyên**. Những kỹ thuật này bảo vệ hợp đồng resource/URI/status, cache và nhất quán nghiệp vụ thay vì chỉ kiểm HTTP 200.

## 1. Vì sao test CRUD thành công chưa đủ?

Một API quản lý đơn hàng có:

~~~http
GET /v1/orders/ord_42 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-ord_42-v7"
Cache-Control: private, no-cache

{"id":"ord_42","status":"DRAFT","deliveryNote":"Giao buổi tối"}
~~~

Frontend lưu representation và ETag. Lần GET tiếp theo hỏi nội dung có đổi không:

~~~http
GET /v1/orders/ord_42 HTTP/1.1
If-None-Match: "order-ord_42-v7"
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 304 Not Modified
ETag: "order-ord_42-v7"
Cache-Control: private, no-cache
~~~

Khi sửa ghi chú, frontend gửi:

~~~http
PATCH /v1/orders/ord_42 HTTP/1.1
If-Match: "order-ord_42-v7"
Content-Type: application/merge-patch+json
Authorization: Bearer <access-token>

{"deliveryNote":"Giao sau 19 giờ"}
~~~

Nếu client A đã cập nhật đơn lên v8, request của client B vẫn dùng v7 phải **thất bại mà không ghi đè thay đổi của A**. Kiểm thử chỉ gửi một PATCH hợp lệ rồi nhận 200 không thể phát hiện lỗi lost update này.

**Đích của bài:** thiết kế test chứng minh (1) ETag phản ánh representation; (2) GET/HEAD có điều kiện trả 304 **không có body**; (3) ghi với ETag sai trả 412 và không sửa DB; (4) cạnh tranh thật giữa hai transaction không để cả hai cùng thắng; (5) quyền đọc/ghi được kiểm trước khi tiết lộ trạng thái tài nguyên.

## 2. Mô hình HTTP: một ETag có nhiều vai trò

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant API as REST API
    participant DB as Database
    A->>API: GET /orders/42
    API->>DB: Read authorized order version=7
    API-->>A: 200 + ETag "order-ord_42-v7"
    B->>API: GET /orders/42
    API-->>B: 200 + cùng ETag v7
    A->>API: PATCH If-Match v7
    API->>DB: Update / commit v8
    API-->>A: 200 + ETag v8
    B->>API: PATCH If-Match v7
    API->>DB: Recheck current version=8
    API-->>B: 412 Precondition Failed
    B->>API: GET If-None-Match v7
    API-->>B: 200 + representation v8
~~~

### 2.1. Strong ETag và weak ETag

`ETag` là validator của **representation** theo HTTP Semantics (RFC 9110), không phải token đăng nhập, mã định danh secret hoặc bản sao cứng của DB primary key.

| Dạng | Ví dụ | GET `If-None-Match` | Ghi `If-Match` |
|---|---|---|---|
| Strong ETag | `"order-ord_42-v7"` | So khớp được | So khớp được |
| Weak ETag | `W/"order-ord_42-v7"` | **Weak comparison** có thể khớp strong cùng opaque tag | **Không** thỏa strong comparison |
| ETag khác | `"order-ord_42-v8"` | Không khớp v7 → gửi 200 mới | Không khớp v7 → 412 |

**Strong ETag** phải thay đổi khi nội dung representation thay đổi theo cách có ý nghĩa cho strong comparison; chỉ đưa `@Version` vào chuỗi ETag là đúng khi mỗi thay đổi tác động representation đã được quản lý đồng bộ. Nếu response biến đổi theo ngôn ngữ, tenant, quyền, encoding hoặc projection thì validator/caching cũng phải phản ánh sự khác nhau đó.

Giá trị ETag có **dấu nháy kép** là một phần cú pháp; không tùy tiện cắt dấu rồi gửi `If-Match`. `If-Match: *` nghĩa là điều kiện về sự tồn tại của representation hiện hành, không phải bảo vệ phiên bản cụ thể; API có thể yêu cầu ETag phiên bản thay vì chỉ dựa vào `*` nếu hợp đồng nghiệp vụ cần.

### 2.2. `304` chỉ dành cho trường hợp phù hợp

Đối với GET/HEAD, khi `If-None-Match` khớp validator hiện tại, server có thể trả `304 Not Modified`; **304 không chứa message body**. Nếu điều kiện không khớp, server trả `200 OK` và representation mới. `If-None-Match` ưu tiên hơn `If-Modified-Since` nếu client gửi cả hai.

304 vẫn mang metadata được chỉ định/phù hợp, đặc biệt `ETag` và chính sách cache hiện hành. Không trả JSON kiểu `{"notModified":true}` với 304; client có cache sẽ dùng bản đã lưu. Nếu muốn quan sát tiết kiệm băng thông, assert **body rỗng** và response `ETag` đúng, không chỉ assert status.

Nếu dùng `Cache-Control: no-store` cho dữ liệu nhạy cảm, browser không nên lưu representation để tái sử dụng 304 như cache. Nhưng `If-Match` vẫn dùng được cho kiểm soát ghi đồng thời. Ví dụ bài dùng `private, no-cache`: cache riêng tư **được phép lưu nhưng phải revalidate**; đây là lựa chọn chỉ khi chính sách dữ liệu/thiết bị cho phép.

### 2.3. `If-Match` và `If-None-Match` có ngữ nghĩa khác nhau

| Header / method | Kết quả khi validator khớp | Kết quả khi không khớp |
|---|---|---|
| GET `If-None-Match` | `304` không body | `200` và body mới |
| HEAD `If-None-Match` | `304` không body | `200` không body, metadata mới |
| PATCH/PUT `If-Match` | Có thể tiến hành mutation sau khi kiểm quyền và invariant | `412 Precondition Failed`, **không mutate** |
| PUT/POST `If-None-Match: *` để tránh ghi đè resource hiện hữu | Nếu resource hiện hữu: `412` | Khi chưa tồn tại: có thể tạo |
| Missing `If-Match` khi contract yêu cầu | Không áp dụng | `428 Precondition Required` |

`409 Conflict` khác `412`: 412 nói **HTTP precondition** không còn khớp; 409 thường báo **business state conflict**, ví dụ đơn đã giao không được sửa dù ETag hiện hành vẫn đúng. Một request có thể vi phạm nhiều điều kiện; server nên có thứ tự xử lý nhất quán, không tiết lộ existence/version của resource ngoài quyền.

## 3. Hợp đồng kiểm thử trước khi viết mã

Giả định resource `/v1/orders/{id}` cho phép GET và PATCH ghi chú khi `status=DRAFT`. Mọi thay đổi lưu DB có `@Version`:

- GET hợp lệ → `200`, body đúng, **strong ETag** với dấu nháy, cache header phù hợp.
- GET `If-None-Match` đúng (cả weak token cùng opaque value) → `304` **không body**, ETag không đổi.
- GET `If-None-Match` sai → `200` + body và ETag mới.
- PATCH với strong ETag đúng, body hợp lệ, đơn trong trạng thái cho phép → `200`, body sau cập nhật và ETag mới.
- PATCH với ETag cũ hoặc weak tag → `412`, DB không đổi.
- PATCH thiếu `If-Match` → `428` nếu API bắt buộc optimistic precondition.
- PATCH với ETag hiện hành nhưng `status=SHIPPED` → `409`, DB không đổi.
- Đơn không thuộc tenant/owner → `404` (theo chính sách che tồn tại), không được trả 304 chỉ vì client đoán trúng ETag.
- Hai PATCH xuất phát từ cùng phiên bản → tối đa **một mutation thắng**; request còn lại thất bại/được yêu cầu đối soát theo contract.

**Lưu ý:** API phải quyết định rõ có chấp nhận `If-Match: *` và danh sách nhiều tags hay không; chuẩn HTTP định nghĩa những cú pháp này. Test không nên “ép” server chỉ hỗ trợ một tag mà không công bố hạn chế, nhất là nếu hệ thống tuyên bố hỗ trợ toàn bộ HTTP conditional semantics.

### 3.1. Ma trận lỗi theo tầng

| Thao tác | Status | Chứng cứ test |
|---|---|---|
| JSON malformed | 400 | Không gọi mutation / DB không đổi |
| Thiếu/hết hạn token | 401 | Không tiết lộ order, challenge theo cơ chế auth |
| Thiếu scope | 403 | Không mutate |
| Object ngoài tenant | 404 hoặc 403 theo policy | Không tiết lộ ETag hoặc body |
| `If-Match` stale | 412 | Không ghi đè |
| Thiếu required precondition | 428 | Không ghi đè |
| Business rule không cho update | 409 | Không ghi đè |
| Hai transaction cùng ghi | Một thành công; còn lại conflict/stale | DB giữ một phiên bản nhất quán |
| Lỗi DB/serialization | 5xx hoặc mapped domain status | Không trả false 200; transaction rollback |

Đừng viết test chỉ dựa vào response JSON mà không đọc DB: một endpoint trả 412 sau khi **đã sửa dữ liệu** vẫn sai nghiêm trọng.

## 4. Chọn đúng tầng kiểm thử: unit, HTTP, database và concurrency

Không có một test nào chứng minh tất cả. Đặc biệt `MockMvc` có thể test HTTP layer rất tốt nhưng không tạo hai transaction thực để thử race nếu toàn bộ service bị mock.

| Tầng | Kiểm gì | Không chứng minh được điều gì? |
|---|---|---|
| Unit test validator/parser | Strong/weak comparison, `*`, nhiều tags, malformed header | Không chứng minh HTTP response/wiring |
| `@WebMvcTest` + `MockMvc` | Route, status, ETag/headers, exception mapping, security filter trong slice | Không chứng minh transaction/DB thật nếu service mock |
| `@SpringBootTest` + MockMvc + DB | HTTP → auth → service → DB, ETag sau commit, 412 không ghi | Race vẫn cần nhiều transaction độc lập |
| Testcontainers PostgreSQL + concurrent clients | `@Version`, lock/isolation, lost update, rollback | Không chứng minh browser caching/CORS |
| Browser E2E / reverse proxy | Cache revalidation, `fetch()`, CORS Expose-Headers, reverse proxy | Không thay DB invariant tests |

**Quy ước test quan trọng:** đừng đặt `@Transactional` lên test class nếu mục tiêu là xác nhận response chỉ trả thành công sau **transaction commit thực sự**. Transaction bao quanh test có thể che flush/commit hoặc làm fixture chưa commit bị vô hình với luồng concurrent.

Fixture nên có ID rõ, ví dụ `ord_42` thuộc `tenant_a/user_1` với `status=DRAFT` và phiên bản 7, thêm `ord_99` thuộc tenant khác. Nếu dùng DB sinh `@Version` từ 0, đừng hardcode v7 mà hãy đọc header `ETag` từ GET đầu tiên; như vậy test vẫn đúng sau khi thay đổi cách seed.

## 5. Java/Spring: resource có ETag và phiên bản JPA

Ví dụ thiết kế dưới đây dùng Spring Boot 3.x, Java 17, Spring MVC/Spring Security 6. Các lớp chia theo trách nhiệm để kiểm thử độc lập: **entity version**, **service kiểm quyền và transaction**, **conditional header parser**, **controller tạo HTTP response**. Đây là một lát cắt cần bổ sung entity mapping/DB schema/exception config trong dự án, không phải một ứng dụng Spring Boot đầy đủ.

### 5.1. Entity và DTO công khai

~~~java
import jakarta.persistence.*;

enum OrderStatus { DRAFT, SHIPPED }

@Entity
@Table(name = "orders")
class OrderEntity {
    @Id
    private String id;
    private String tenantId;
    private String ownerUserId;
    @Enumerated(EnumType.STRING)
    private OrderStatus status;
    private String deliveryNote;
    @Version
    private long version;

    protected OrderEntity() {} // JPA
    // Getter/setter và constructor cho fixture/command được lược bỏ.
}

record OrderView(String id, String status, String deliveryNote) {}
record OrderSnapshot(OrderView view, long version) {}
record ChangeNoteRequest(String deliveryNote) {}
~~~

DTO response không trả `tenantId`, `ownerUserId`, JPA entity hoặc field nội bộ. `@Version` giúp JPA so sánh phiên bản khi UPDATE; nếu hai transaction cập nhật từ cùng version, một bên sẽ gặp optimistic locking failure thay vì “last writer silently wins”.

### 5.2. Sinh strong ETag có thể kiểm thử

~~~java
final class OrderTags {
    private OrderTags() {}

    static String current(String id, long version) {
        // ID được cấp bởi server và thuộc bộ ký tự URI-safe có kiểm soát.
        return "\"order-" + id + "-v" + version + "\"";
    }
}
~~~

Hàm là **ví dụ minh họa** khi mọi thay đổi làm thay đổi representation đều làm version tăng. Nếu JSON representation khác nhau theo role, language hoặc projection, phải phát validator phù hợp **từng representation** (hoặc dùng weak ETag cho trường hợp chỉ tương đương ngữ nghĩa); không dùng cùng tag cho hai biểu diễn khác nhau nếu nó làm sai cache/strong comparison.

### 5.3. Parse `If-None-Match` / `If-Match` thay vì so chuỗi thủ công

HTTP cho phép danh sách entity tags hoặc `*`. Spring `HttpHeaders` hỗ trợ parse các header này:

~~~java
import java.util.List;
import org.springframework.http.HttpHeaders;

final class Conditions {
    private Conditions() {}

    static List<String> parse(String header, String raw) {
        if (raw == null || raw.isBlank()) {
            return List.of();
        }
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.add(header, raw);
            return HttpHeaders.IF_MATCH.equals(header)
                ? headers.getIfMatch()
                : headers.getIfNoneMatch();
        } catch (IllegalArgumentException ex) {
            throw new BadConditionalHeaderException();
        }
    }

    static boolean matchesGet(String ifNoneMatch, String current) {
        return parse(HttpHeaders.IF_NONE_MATCH, ifNoneMatch)
            .stream().anyMatch(candidate ->
                "*".equals(candidate) ||
                stripWeak(candidate).equals(stripWeak(current)));
    }

    static boolean matchesWrite(String ifMatch, String current) {
        return parse(HttpHeaders.IF_MATCH, ifMatch)
            .stream().anyMatch(candidate ->
                "*".equals(candidate) ||
                (!candidate.startsWith("W/")
                    && candidate.equals(current)));
    }

    private static String stripWeak(String tag) {
        return tag.startsWith("W/") ? tag.substring(2) : tag;
    }
}

class BadConditionalHeaderException extends RuntimeException {}
~~~

Giá trị `If-None-Match: W/"order-ord_42-v7"` có thể khớp GET với strong ETag `"order-ord_42-v7"` vì GET dùng **weak comparison**. `If-Match: W/"order-ord_42-v7"` không thể vượt qua strong comparison cho PATCH. `If-Match: *` chỉ nói resource hiện hữu; nó không bảo vệ chống cập nhật của client khác, vì vậy nếu yêu cầu nghiệp vụ bắt buộc tag phiên bản cụ thể, contract có thể từ chối wildcard ngay từ validation với lỗi được công bố.

Hàm trên là **testable helper** dựa vào parser của phiên bản Spring đang chạy, không cố viết một RFC parser bằng cách `split(",")` (dễ sai khi có dấu nháy và ký tự hợp lệ). Test malformed syntax và danh sách tags trên runtime mục tiêu. Khi `If-Match` rỗng không đồng nghĩa “cho phép”: service sẽ trả 428.

## 6. Service: kiểm quyền trước validator, transaction trước commit

Ví dụ dùng repository ràng buộc tenant ngay trong query, sau đó kiểm owner:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<OrderEntity, String> {
    Optional<OrderEntity> findByIdAndTenantId(
        String id, String tenantId);
}
~~~

~~~java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository repository;
    private final EntityManager entityManager;

    public OrderService(OrderRepository repository,
            EntityManager entityManager) {
        this.repository = repository;
        this.entityManager = entityManager;
    }

    @Transactional(readOnly = true)
    public OrderSnapshot visible(String tenant, String caller, String id) {
        OrderEntity order = authorized(tenant, caller, id);
        return snapshot(order);
    }

    @Transactional
    public OrderSnapshot changeNote(
            String tenant, String caller, String id,
            String ifMatch, ChangeNoteRequest input) {
        if (ifMatch == null || ifMatch.isBlank()) {
            throw new MissingPreconditionException();
        }
        OrderEntity order = authorized(tenant, caller, id);
        String current = OrderTags.current(
            order.getId(), order.getVersion());
        if (!Conditions.matchesWrite(ifMatch, current)) {
            throw new StalePreconditionException();
        }
        if (order.getStatus() != OrderStatus.DRAFT) {
            throw new OrderStateConflictException();
        }
        if (input.deliveryNote() != null
                && input.deliveryNote().length() > 500) {
            throw new InvalidNoteException();
        }
        order.setDeliveryNote(input.deliveryNote());
        entityManager.flush();
        return snapshot(order);
    }

    private OrderEntity authorized(String tenant,
            String caller, String id) {
        if (tenant == null || tenant.isBlank()) {
            throw new OrderForbiddenException();
        }
        OrderEntity order = repository
            .findByIdAndTenantId(id, tenant)
            .orElseThrow(OrderNotFoundException::new);
        if (!order.getOwnerUserId().equals(caller)) {
            throw new OrderNotFoundException();
        }
        return order;
    }

    private static OrderSnapshot snapshot(OrderEntity entity) {
        return new OrderSnapshot(
            new OrderView(entity.getId(),
                entity.getStatus().name(),
                entity.getDeliveryNote()),
            entity.getVersion());
    }
}
~~~

`OrderEntity` cần getters/setters trong code thật. Những exception domain sẽ được ánh xạ status ở mục 7. `entityManager.flush()` giúp phát hiện nhiều lỗi version/constraint trước khi tạo snapshot; **flush không phải commit**. Với Spring proxy, transaction commit lúc service method hoàn tất. Optimistic locking vẫn phải được bắt/xử lý cả trường hợp lỗi phát sinh lúc flush/commit, không chỉ khi kiểm `ifMatch` lần đầu.

Đừng lưu ETag từ JWT/header chưa kiểm và đừng trả `304` trước khi đã kiểm object-level authorization. Một caller biết ID và đoán được ETag **không** được phép dùng `If-None-Match` làm oracle xác nhận đơn của tenant khác tồn tại.

## 7. Controller và lỗi HTTP: kết nối ETag với response

### 7.1. GET có điều kiện và PATCH strict input

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.*;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/orders")
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping(path = "/{id}", produces = "application/json")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    ResponseEntity<OrderView> get(@PathVariable String id,
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(value = HttpHeaders.IF_NONE_MATCH,
                           required = false) String ifNoneMatch) {
        OrderSnapshot current = service.visible(
            tenant(jwt), jwt.getSubject(), id);
        String etag = OrderTags.current(id, current.version());
        if (Conditions.matchesGet(ifNoneMatch, etag)) {
            return ResponseEntity.status(HttpStatus.NOT_MODIFIED)
                .eTag(etag)
                .header(HttpHeaders.CACHE_CONTROL,
                    "private, no-cache")
                .build();
        }
        return ResponseEntity.ok()
            .eTag(etag)
            .header(HttpHeaders.CACHE_CONTROL, "private, no-cache")
            .body(current.view());
    }

    @PatchMapping(path = "/{id}",
                  consumes = "application/merge-patch+json",
                  produces = "application/json")
    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    ResponseEntity<OrderView> patch(@PathVariable String id,
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(value = HttpHeaders.IF_MATCH,
                           required = false) String ifMatch,
            @RequestBody JsonNode patch) {
        // Endpoint hỗ trợ subset của Merge Patch: chỉ deliveryNote.
        if (patch == null || !patch.isObject()
                || patch.size() != 1
                || !patch.has("deliveryNote")) {
            throw new InvalidNoteException();
        }
        JsonNode value = patch.get("deliveryNote");
        if (!value.isNull() && !value.isTextual()) {
            throw new InvalidNoteException();
        }
        ChangeNoteRequest input = new ChangeNoteRequest(
            value.isNull() ? null : value.textValue());
        try {
            OrderSnapshot changed = service.changeNote(
                tenant(jwt), jwt.getSubject(), id, ifMatch, input);
            String etag = OrderTags.current(id, changed.version());
            return ResponseEntity.ok()
                .eTag(etag)
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(changed.view());
        } catch (OptimisticLockingFailureException race) {
            // Service proxy đã hoàn tất hoặc rollback transaction.
            // Trong endpoint conditional write, xung đột phiên bản
            // đồng nghĩa request này không thể commit ở phiên bản cũ.
            throw new StalePreconditionException();
        }
    }

    private static String tenant(Jwt jwt) {
        String t = jwt.getClaimAsString("tenant_id");
        if (t == null || t.isBlank()) {
            throw new OrderForbiddenException();
        }
        return t;
    }
}
~~~

Endpoint cố ý nhận **chỉ property `deliveryNote`**: `application/merge-patch+json` nhưng không hỗ trợ mọi khả năng của RFC 7396; yêu cầu khác phải bị từ chối và hạn chế này cần tài liệu hóa. JSON null nghĩa là xóa ghi chú; JSON không có property sẽ bị 400, không được âm thầm xóa trường. `GET` kiểm quyền qua service **trước** khi kiểm `If-None-Match`, rồi trả 304 không entity.

Ở đây controller chỉ bắt `OptimisticLockingFailureException` trong một endpoint **đã dùng `If-Match`**, ánh xạ race thành 412. Ở endpoint ghi không có HTTP precondition hoặc xung đột rule nghiệp vụ khác, không được mặc định đổi mọi optimistic-lock error toàn ứng dụng thành 412; có thể cần trả 409 hoặc truy vấn lại state để phân loại. Nếu implementation trả exception khác tại commit, phải kiểm thử/định nghĩa mapping cho đúng runtime/JPA vendor, không nuốt lỗi thành 200.

### 7.2. `ProblemDetail` và status mapping

~~~java
import java.net.URI;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

class OrderNotFoundException extends RuntimeException {}
class OrderForbiddenException extends RuntimeException {}
class MissingPreconditionException extends RuntimeException {}
class StalePreconditionException extends RuntimeException {}
class OrderStateConflictException extends RuntimeException {}
class InvalidNoteException extends RuntimeException {}

@RestControllerAdvice
class OrderProblemAdvice {
    @ExceptionHandler(MissingPreconditionException.class)
    ResponseEntity<ProblemDetail> missingPrecondition() {
        return error(428, "PRECONDITION_REQUIRED");
    }
    @ExceptionHandler(StalePreconditionException.class)
    ResponseEntity<ProblemDetail> stale() {
        return error(412, "STALE_VERSION");
    }
    @ExceptionHandler(OrderStateConflictException.class)
    ResponseEntity<ProblemDetail> stateConflict() {
        return error(409, "ORDER_STATE_CONFLICT");
    }
    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ProblemDetail> notFound() {
        return error(404, "ORDER_NOT_FOUND");
    }
    @ExceptionHandler(OrderForbiddenException.class)
    ResponseEntity<ProblemDetail> forbidden() {
        return error(403, "FORBIDDEN");
    }
    @ExceptionHandler({
        InvalidNoteException.class,
        BadConditionalHeaderException.class
    })
    ResponseEntity<ProblemDetail> badRequest() {
        return error(400, "INVALID_REQUEST");
    }

    private static ResponseEntity<ProblemDetail> error(
            int status, String code) {
        ProblemDetail p = ProblemDetail.forStatus(status);
        p.setType(URI.create(
            "https://api.example.test/problems/"
                + code.toLowerCase().replace('_', '-')));
        p.setTitle("Request cannot be completed");
        p.setProperty("code", code);
        return ResponseEntity.status(status)
            .contentType(MediaType.parseMediaType(
                "application/problem+json"))
            .header(HttpHeaders.CACHE_CONTROL, "no-store")
            .body(p);
    }
}
~~~

Spring Security filter có thể phát **401/403 trước controller**; phải cấu hình `AuthenticationEntryPoint`/`AccessDeniedHandler` riêng nếu muốn Problem Details nhất quán. Advice trên không tự xử lý mọi lỗi của gateway, cache hoặc container. Không trả raw JPA exception, SQL hoặc ID tenant khác trong `detail`.

### 7.3. Bảo mật validator và cache

Một token hợp lệ không có quyền xem order phải nhận 403/404 theo policy **ngay cả khi đoán đúng ETag**. ETag không thay `Authorization`, tenant filtering hay owner check. Đặc biệt:

- Không lấy tenant từ query/body chưa xác thực; claim JWT phải được xác minh issuer, audience, signature, expiration và membership theo policy.
- Không dùng cache dùng chung để trả representation riêng tư cho caller khác; với dữ liệu nhạy cảm có thể dùng `no-store` và bỏ revalidation cache, chỉ giữ `If-Match` để cập nhật an toàn.
- Nếu API dùng CORS, frontend chỉ đọc `ETag` qua `fetch().headers.get("ETag")` khi response cross-origin có `Access-Control-Expose-Headers: ETag`. Preflight của PATCH phải cho phép **request header `If-Match`**; đây là hai cấu hình khác nhau.
- Không dùng ETag có token, email hay secret; correlation ID và logs không chứa raw bearer token hoặc body nhạy cảm.

## 8. Test MockMvc: `200` → `304` → `200` mới

Đặt fixture trong DB, khởi động security filter thật (`@SpringBootTest` + `@AutoConfigureMockMvc`, dependency `spring-security-test`). Giả định test có `MockMvc mockMvc` được inject và order thuộc `user_1`/`tenant_a`. Helper sau giúp giữ các test rõ:

~~~java
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

private RequestPostProcessor customer(String scope) {
    return jwt().jwt(token -> token
        .subject("user_1")
        .claim("tenant_id", "tenant_a"))
        .authorities(new SimpleGrantedAuthority(scope));
}
~~~

Đoạn code trên là phương thức đặt trong lớp kiểm thử; cấu hình JWT test principal chỉ thay identity trong môi trường test.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@Test
void unchangedOrderReturns304WithoutBody() throws Exception {
    var first = mockMvc.perform(get("/v1/orders/ord_42")
            .with(customer("SCOPE_orders.read")))
        .andExpect(status().isOk())
        .andExpect(header().exists("ETag"))
        .andReturn();

    String etag = first.getResponse().getHeader("ETag");
    assertNotNull(etag);
    assertTrue(etag.startsWith("\""));

    mockMvc.perform(get("/v1/orders/ord_42")
            .with(customer("SCOPE_orders.read"))
            .header("If-None-Match", etag))
        .andExpect(status().isNotModified())
        .andExpect(header().string("ETag", etag))
        .andExpect(content().string(""));

    // Weak comparison cho GET: W/ cùng opaque-tag vẫn 304.
    mockMvc.perform(get("/v1/orders/ord_42")
            .with(customer("SCOPE_orders.read"))
            .header("If-None-Match", "W/" + etag))
        .andExpect(status().isNotModified())
        .andExpect(content().string(""));

    mockMvc.perform(get("/v1/orders/ord_42")
            .with(customer("SCOPE_orders.read"))
            .header("If-None-Match", "\"old-version\""))
        .andExpect(status().isOk())
        .andExpect(header().string("ETag", etag))
        .andExpect(jsonPath("$.id").value("ord_42"));
}
~~~

Test này bắt được ba loại lỗi hay gặp: quên ETag trong 200, 304 có body, hoặc so sánh weak `If-None-Match` như strong `If-Match`. Sau đó test `HEAD` tương đương; không chỉ nhìn response status mà cần assert `Content-Length`/body theo HTTP contract và runtime. `If-None-Match: *` khi resource có tồn tại cũng phải được kiểm.

## 9. Test PATCH: strong If-Match, 412 và kiểm DB không đổi

Với cùng fixture, GET lấy validator ban đầu, PATCH cập nhật thành công, sau đó dùng **ETag cũ** để thử ghi đè:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@Test
void staleIfMatchMustNotOverwriteCommittedChange() throws Exception {
    String oldTag = mockMvc.perform(get("/v1/orders/ord_42")
            .with(customer("SCOPE_orders.read")))
        .andExpect(status().isOk())
        .andReturn().getResponse().getHeader("ETag");

    String newTag = mockMvc.perform(patch("/v1/orders/ord_42")
            .with(customer("SCOPE_orders.write"))
            .header("If-Match", oldTag)
            .contentType("application/merge-patch+json")
            .content("{\"deliveryNote\":\"Giao sau 19h\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.deliveryNote").value("Giao sau 19h"))
        .andReturn().getResponse().getHeader("ETag");

    assertNotNull(newTag);
    assertNotEquals(oldTag, newTag);

    mockMvc.perform(patch("/v1/orders/ord_42")
            .with(customer("SCOPE_orders.write"))
            .header("If-Match", oldTag)
            .contentType("application/merge-patch+json")
            .content("{\"deliveryNote\":\"Ghi đè trái phép\"}"))
        .andExpect(status().isPreconditionFailed())
        .andExpect(jsonPath("$.code").value("STALE_VERSION"));

    // Helper mở một transaction/connection kiểm dữ liệu đã commit.
    assertEquals("Giao sau 19h", readCommittedNote("ord_42"));
}
~~~

`readCommittedNote(...)` là helper test sử dụng JDBC/transaction riêng, không phải method có sẵn của Spring. Một số DB transaction chạy dưới isolation khác có thể không nhìn thấy commit mới nếu test bao ngoài bởi `@Transactional`; tách rõ setup, execution và assertion.

### 9.1. Những trường hợp boundary không được bỏ quên

~~~java
// Thiếu precondition bắt buộc → 428.
mockMvc.perform(patch("/v1/orders/ord_42")
        .with(customer("SCOPE_orders.write"))
        .contentType("application/merge-patch+json")
        .content("{\"deliveryNote\":\"Khác\"}"))
    .andExpect(status().isEqualTo(428));

// Weak tag không được chấp nhận như strong If-Match.
mockMvc.perform(patch("/v1/orders/ord_42")
        .with(customer("SCOPE_orders.write"))
        .header("If-Match", "W/" + newTag)
        .contentType("application/merge-patch+json")
        .content("{\"deliveryNote\":\"Khác\"}"))
    .andExpect(status().isPreconditionFailed());
~~~

Thêm test `If-Match` với danh sách hai strong tags, `If-Match: *` theo contract, malformed header, tag chứa dấu nháy sai, trường hợp header đúng nhưng JSON body không hợp lệ và state đã `SHIPPED`. Với mỗi lỗi, kiểm **version không tăng**, note không đổi và không tạo event/outbox sai.

### 9.2. Phân biệt 409 với 412 trong test

Hai request có thể cùng bị từ chối nhưng lý do khác:

- `If-Match` không khớp **representation hiện hành** → **412**.
- `If-Match` khớp, nhưng `status=SHIPPED` hoặc rule “không sửa sau thanh toán” → **409**.

Test nên seed trạng thái `SHIPPED` với **ETag hiện hành**, rồi gửi PATCH để chắc chắn `409` là do business rule, không phải do đã dùng tag cũ. Nếu lúc nào cũng dùng ETag stale, test `409` có thể chưa bao giờ chạm business validator.

### 9.3. Kiểm HTTP errors không làm rò thông tin

Với bearer token thiếu/hết hạn, scope sai hoặc ID ngoài tenant, kiểm 401/403/404 theo policy; response không chứa ETag, owner, row ID ngoài quyền, SQL hoặc stack trace. Lặp lại cùng test với `If-None-Match` đoán trúng và `If-Match` đoán trúng: precondition **không** mở khóa dữ liệu. Nếu quyền đã bị thu hồi kể từ GET đầu, request GET có điều kiện phải từ chối, **không trả 304** chỉ vì tag chưa đổi.

## 10. Test xung đột đồng thời: hai transaction phải thật sự overlap

Test tuần tự “PATCH v7, PATCH v7 lần hai” xác minh **stale read sau commit**. Nó **không** chứng minh code không bị *time-of-check/time-of-use* (TOCTOU) khi **cả hai** transaction đọc v7 và cùng pass precondition trước khi bất kỳ bên nào commit.

~~~mermaid
sequenceDiagram
    participant T1 as Transaction 1
    participant T2 as Transaction 2
    participant DB as DB row version=7
    T1->>DB: Read version 7
    T2->>DB: Read version 7
    T1->>T1: If-Match v7 passes
    T2->>T2: If-Match v7 passes
    T1->>DB: UPDATE ... WHERE version=7
    DB-->>T1: Commit version 8
    T2->>DB: UPDATE ... WHERE version=7
    DB-->>T2: Optimistic lock failure
    Note over T1,T2: Chỉ một ghi thành công
~~~

Nếu code chỉ kiểm tag bằng cách đọc rồi gọi `save` không có `@Version`, row lock hoặc conditional SQL update, cả hai request có thể trả 200 và một thay đổi sẽ bị mất. `@Version` đảm bảo một update thua trên DB hỗ trợ optimistic locking đúng cách.

### 10.1. Tạo race có kiểm soát thay vì `Thread.sleep`

Dùng hai thread, **hai transaction độc lập**, barrier đặt **sau khi đọc cùng version nhưng trước khi mutate/flush**. Ví dụ ý tưởng integration test (đã cấu hình `TransactionTemplate`, repository, `EntityManager`, fixture và PostgreSQL Testcontainers):

~~~java
import java.util.concurrent.*;
import org.springframework.dao.OptimisticLockingFailureException;

@Test
void concurrentWritesFromSameVersionCannotBothCommit()
        throws Exception {
    CountDownLatch bothRead = new CountDownLatch(2);
    ExecutorService pool = Executors.newFixedThreadPool(2);
    try {
        Callable<Boolean> writer = () -> {
            try {
                transactionTemplate.execute(tx -> {
                    OrderEntity order = repository
                        .findByIdAndTenantId("ord_42", "tenant_a")
                        .orElseThrow();
                    // Mỗi transaction đã đọc cùng version.
                    bothRead.countDown();
                    try {
                        if (!bothRead.await(10, TimeUnit.SECONDS)) {
                            throw new IllegalStateException(
                                "Test barrier timed out");
                        }
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(interrupted);
                    }
                    order.setDeliveryNote(
                        Thread.currentThread().getName());
                    entityManager.flush();
                    return null;
                });
                return true;
            } catch (OptimisticLockingFailureException conflict) {
                return false;
            }
        };

        Future<Boolean> a = pool.submit(writer);
        Future<Boolean> b = pool.submit(writer);
        int committed = (a.get(15, TimeUnit.SECONDS) ? 1 : 0)
            + (b.get(15, TimeUnit.SECONDS) ? 1 : 0);
        assertEquals(1, committed);
        assertEquals(initialVersion + 1,
            readCommittedVersion("ord_42"));
    } finally {
        pool.shutdownNow();
    }
}
~~~

Các biến `transactionTemplate`, `repository`, `entityManager`, `initialVersion` và helper query là fixture của integration test, không phải framework magic. **Không gắn `@Transactional` lên test method**. Đây là test kỹ thuật DB cho `@Version`; nó chủ động bypass HTTP/security để ép race đúng vị trí. Test HTTP riêng ở mục 9 chứng minh mapping của conditional requests. Muốn test *hai HTTP requests đồng thời*, tạo **test-only gate** sau service kiểm version và trước flush, gửi hai MockMvc/HTTP calls từ hai thread rồi kiểm một 200 và một 412 theo contract.

Với JPA/DB provider thực tế, exception có thể được dịch thành `ObjectOptimisticLockingFailureException`, `OptimisticLockException` hoặc lỗi commit tương đương; test phải nhận diện **đúng loại** dựa trên stack đang dùng, không viết `catch (Exception) { return false; }` vì như vậy lỗi cấu hình DB cũng bị coi là “đã khóa đúng”.

### 10.2. Test thêm ba tình huống race khác

1. **Delete vs update:** client B PATCH theo ETag cũ trong lúc client A xóa order. Kết quả có thể 404/412 tùy thứ tự xác thực/tồn tại và contract, nhưng **không được resurrect** resource đã xóa.
2. **Business state transition vs note update:** một transaction chuyển `DRAFT→SHIPPED`, transaction kia sửa ghi chú; kiểm `@Version` hoặc lock/invariant khiến chỉ kết quả hợp lệ được commit.
3. **Hai clients khác tenant:** cùng đoán một ID không khiến kết quả cross-tenant bị leak; truy vấn luôn scope tenant/owner, kể cả khi client gửi ETag của người khác.

Tránh test flaky bằng delay ngẫu nhiên và `Thread.sleep(100)`. Dùng latch/barrier với timeout, mỗi test seed fixture riêng, hai DB connections thực và assertion cuối trên dữ liệu **đã commit**.

## 11. Header/cache/proxy và browser: test những gì ngoài controller?

Client có thể lưu ETag ở browser, CDN, API gateway hoặc local cache. Phần lớn lỗi ở đây không nằm trong method `get()`:

- **304 không body:** xác nhận trên wire qua HTTP client/gateway, không chỉ ở một DTO. Không trả `Content-Type: application/problem+json` cùng 304.
- **`Cache-Control`:** `private, no-cache` cho phép private cache lưu rồi phải revalidate; `no-store` yêu cầu không lưu. Chọn theo mức nhạy cảm, không sử dụng `public` cho đơn hàng có thông tin cá nhân.
- **`Vary` và content negotiation:** nếu phản hồi thay theo `Accept-Language`/`Accept-Encoding`/quyền, cache key và ETag phải phản ánh biến thể. Gateway nén/biến đổi body nhưng giữ strong ETag sai có thể phá validator.
- **ETag trên 412:** không giả định response 412 luôn mang ETag mới. Client nên GET lại representation đã được phép để lấy validator mới; 412 không phải lý do tự động bỏ `If-Match`.
- **CORS:** frontend cross-origin chỉ đọc ETag qua `fetch().headers.get("ETag")` khi actual response có `Access-Control-Expose-Headers: ETag`. Để gửi `If-Match` trong PATCH, preflight cần `Access-Control-Allow-Headers: If-Match`.
- **Auth và private data:** GET conditional không được “tối ưu” bypass auth hoặc tenant ACL. Một cache dùng chung không được làm lộ representation/ETag giữa khách hàng.

Ví dụ browser:

~~~javascript
const uri = "https://api.example.test/v1/orders/ord_42";
const first = await fetch(uri, {
  headers: {"Authorization": "Bearer " + accessToken},
  cache: "no-cache"
});
if (!first.ok) throw new Error("Read failed");
const etag = first.headers.get("ETag");
if (!etag) throw new Error("ETag missing or not exposed");

const update = await fetch(uri, {
  method: "PATCH",
  headers: {
    "Authorization": "Bearer " + accessToken,
    "Content-Type": "application/merge-patch+json",
    "If-Match": etag
  },
  body: JSON.stringify({deliveryNote: "Giao sau 19h"})
});
if (update.status === 412) {
  // Đọc lại, hiển thị conflict để người dùng quyết định.
}
~~~

`cache:"no-cache"` ở Fetch không tự chứng minh server đã trả 304; browser có thể quản lý cache/revalidation phía dưới và hiển thị status đã ghép. Cần test E2E phù hợp và quan sát network/proxy, không kết luận chỉ bằng `Response.status` của JavaScript.

### 11.1. Kịch bản HTTP wire-level bằng curl

~~~bash
# Chỉ dùng token test; đừng lưu token thật trong shell history/log.
curl -i -H 'Authorization: Bearer TEST_TOKEN' \
  https://api.example.test/v1/orders/ord_42

curl -i -H 'Authorization: Bearer TEST_TOKEN' \
  -H 'If-None-Match: "order-ord_42-v7"' \
  https://api.example.test/v1/orders/ord_42

curl -i -X PATCH \
  -H 'Authorization: Bearer TEST_TOKEN' \
  -H 'If-Match: "order-ord_42-v7"' \
  -H 'Content-Type: application/merge-patch+json' \
  --data '{"deliveryNote":"Giao sau 19h"}' \
  https://api.example.test/v1/orders/ord_42
~~~

Các giá trị ETag trong lệnh là **minh họa**: trong test thực, lấy nguyên tag từ response GET đầu tiên. Curl đọc raw HTTP headers không chịu filtered response headers của Fetch/CORS; muốn chứng minh JavaScript đọc được ETag phải chạy browser test. Với endpoint được bảo vệ, test bearer token phải có quyền, không dùng token production.

## 12. OpenAPI 3.1: mô tả preconditions như một phần hợp đồng

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /v1/orders/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema: {type: string}
    get:
      security: [{bearerAuth: []}]
      parameters:
        - name: If-None-Match
          in: header
          required: false
          schema: {type: string}
          description: Cho phép GET có điều kiện bằng weak comparison.
      responses:
        '200':
          description: Representation hiện hành
          headers:
            ETag: {schema: {type: string}}
            Cache-Control: {schema: {type: string}}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Order'}
        '304':
          description: Not Modified, không có response body
          headers:
            ETag: {schema: {type: string}}
            Cache-Control: {schema: {type: string}}
        '401': {description: Chưa xác thực}
        '403': {description: Thiếu quyền thao tác}
        '404': {description: Không tìm thấy hoặc không được công bố}
    patch:
      summary: Cập nhật ghi chú chỉ khi strong ETag khớp
      security: [{bearerAuth: []}]
      parameters:
        - name: If-Match
          in: header
          required: true
          schema: {type: string}
          description: Strong entity tag của representation đang sửa.
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema:
              type: object
              required: [deliveryNote]
              additionalProperties: false
              properties:
                deliveryNote:
                  type: [string, 'null']
                  maxLength: 500
      responses:
        '200':
          description: Cập nhật thành công; trả ETag mới
          headers:
            ETag: {schema: {type: string}}
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Order'}
        '400': {$ref: '#/components/responses/Problem'}
        '409': {$ref: '#/components/responses/Problem'}
        '412': {$ref: '#/components/responses/Problem'}
        '428': {$ref: '#/components/responses/Problem'}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
  schemas:
    Order:
      type: object
      properties:
        id: {type: string}
        status: {type: string}
        deliveryNote: {type: [string, 'null']}
  responses:
    Problem:
      description: Lỗi theo RFC 9457
      content:
        application/problem+json:
          schema:
            type: object
            required: [type, title, status]
            properties:
              type: {type: string, format: uri-reference}
              title: {type: string}
              status: {type: integer}
              code: {type: string}
~~~

OpenAPI không tự làm validation/precondition atomic. Nếu implementation hỗ trợ `If-Match: *` hoặc danh sách ETag, tài liệu phải mô tả; nếu yêu cầu một strong tag cụ thể, cần công bố hạn chế và kiểm tra nhất quán. `304` không có content schema vì không có body. CI có thể có contract tests đối chiếu 200/304/412/428 với schema/header đã khai báo.

## 13. Bài thực hành: chống lost update trong API kho hàng

**Bối cảnh:** API `GET /v1/inventories/{sku}` trả tồn kho và `ETag`, `PATCH /v1/inventories/{sku}` điều chỉnh `reorderThreshold`. Hệ thống đa tenant; nhân viên quản lý chỉ được chỉnh SKU thuộc kho họ phụ trách. Có hai giao diện browser và một batch worker cùng có thể cập nhật ngưỡng.

**Nhiệm vụ thực hiện:**

1. Thiết kế representation/ETag và chính sách cache cho GET; quyết định dùng `private, no-cache` hay `no-store`.
2. Định nghĩa GET `If-None-Match` với strong/weak tag, `304` body rỗng và GET với validator sai.
3. Thiết kế PATCH bắt buộc `If-Match`, status `412`/`428`, rule `reorderThreshold >= 0` và status `409` cho kho bị khóa.
4. Viết entity `@Version`, scoped repository theo tenant/kho, service transaction, controller và Problem Details.
5. Viết MockMvc tests cho 200→304, HEAD, weak `If-None-Match`, weak `If-Match` bị từ chối, PATCH thành công và PATCH stale không thay DB.
6. Viết integration test hai transaction cùng đọc một version bằng latch/barrier; chứng minh không thể cả hai cùng commit. Làm tương tự với hai HTTP requests để kiểm status mapping.
7. Test BOLA: lấy ETag từ tenant A, thử GET/PATCH SKU của tenant B; không tiết lộ existence, số lượng, ETag hoặc trạng thái.
8. Thêm OpenAPI và browser CORS Expose-Headers/Allow-Headers; test `fetch` đọc ETag được và gửi If-Match an toàn.

**Tiêu chí đạt:** cùng một phiên bản chỉ có một mutation thắng trong bài test cạnh tranh, các request lỗi không sửa state, ETag không mở khóa dữ liệu trái quyền và 304 không có message body.

## 14. Checklist rà soát trước khi kết thúc STEP 4

| Rủi ro | Bằng chứng cần có |
|---|---|
| ETag có nhưng không phản ánh representation | Test thay đổi field → validator đổi khi cần |
| GET điều kiện bị trả 200 mọi lần | Test matched `If-None-Match` → 304 |
| 304 có body | Assert body rỗng cả raw HTTP/proxy |
| Weak tag vô tình chấp nhận khi ghi | Test `If-Match: W/"..."` → 412 |
| Thiếu precondition vẫn ghi được | Test 428 và DB không đổi |
| 412 trả rồi DB đã mutate | Đọc DB sau request |
| Race hai transaction đều pass check trước write | DB test với barrier + `@Version` |
| 409 và 412 bị trộn | Test ETag hiện hành nhưng state conflict |
| Bypass tenant/owner bằng đoán tag | HTTP/security tests cho ID ngoài quyền |
| Cache/CORS làm frontend không đọc được ETag | Browser E2E, response headers, origin |
| Exception ở commit bị trả false success | Test lỗi flush/commit + rollback |
| Outbox/event chạy dù ghi bị từ chối | Assert không có event thành công sau transaction lỗi |

## 15. Ghi nhớ

**ETag là validator của representation; `304` giảm truyền dữ liệu; `If-Match` tạo precondition để không ghi đè phiên bản cũ.** Một test đúng phải xem cả response status, headers, body, quyền người gọi **và trạng thái database sau commit/rollback**.

Kiểm tra tuần tự `200 → 304 → PATCH → 412` là cần thiết nhưng **chưa đủ**: hai transaction có thể cùng pass `If-Match` rồi đua nhau ghi. Kết hợp `@Version`/locking hoặc conditional SQL update với integration test concurrency có kiểm soát mới chứng minh không lost update. Chỉ sau khi đối chiếu **HTTP contract, security, DB và browser cache** mới có thể tin cậy hành vi conditional requests của REST API.
