# Ánh xạ lỗi tranh chấp dữ liệu sang 409 hoặc 412 theo ngữ cảnh

## 1. Cùng là “xung đột”, tại sao có lúc trả 409 và lúc trả 412?

Một REST API quản lý sản phẩm cho phép tạo sản phẩm bằng **POST /products** và sửa tên bằng **PATCH /products/{id}**. Hai tình huống thường gặp:

**Tình huống A — trùng SKU:** Người dùng tạo sản phẩm có mã **SKU-100**, nhưng trong cùng tenant đã tồn tại một sản phẩm với SKU đó. Database từ chối vì unique constraint. Đây là **xung đột với trạng thái hiện tại của tập tài nguyên**, có thể biểu diễn bằng **409 Conflict**.

**Tình huống B — phiên bản đã thay đổi:** Client đọc sản phẩm P-100 và nhận **ETag: "product-P-100-v7"**. Sau đó người khác sửa sản phẩm thành phiên bản v8. Client gửi PATCH với **If-Match: "product-P-100-v7"**. Điều kiện HTTP mà client yêu cầu không còn đúng; câu trả lời phù hợp là **412 Precondition Failed**.

Trong cả hai tình huống, Spring Data JPA có thể ném exception liên quan đến database hoặc transaction. Tuy nhiên, **loại exception không đủ quyết định mã HTTP**. Phải xét **phương thức, header điều kiện, resource đang thao tác, invariant nghiệp vụ và ngữ cảnh transaction**.

Trong module **INTEGRATION_API_REST**, bài học này tập trung thiết kế hợp đồng REST đúng resource/URI, mã HTTP và dữ liệu lỗi, cách ánh xạ exception Spring/JPA an toàn, phân quyền theo tenant và kiểm thử tranh chấp. Không cần học lại toàn bộ cơ chế HTTP methods hay mọi loại lỗi Spring; trọng tâm là **chọn 409 hoặc 412 có căn cứ**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **409, 412, 428, 400, 404, 422** trong các tình huống tranh chấp.
2. Thiết kế **If-Match + strong ETag** và bảo vệ tính nguyên tử tại database.
3. Phân loại **optimistic locking, unique/FK constraints, deadlock và lỗi hạ tầng** trước khi ánh xạ.
4. Tổ chức Spring MVC controller, service có transaction và **@RestControllerAdvice + ProblemDetail**.
5. Không làm lộ tài nguyên tenant khác hay chi tiết SQL qua thông báo lỗi.
6. Kiểm thử cả **HTTP status** lẫn **bất biến dữ liệu sau hai yêu cầu đồng thời**.

## 2. Quy tắc chọn 409, 412 và các mã liên quan

**409 Conflict** (RFC 9110) biểu thị request không thể hoàn tất do **xung đột với trạng thái hiện tại của tài nguyên**: SKU đã được chiếm, ghế đã có reservation hoặc product ARCHIVED không cho sửa.

**412 Precondition Failed** cho biết một **HTTP precondition client đã gửi** không được thỏa. Ví dụ client đọc ETag v7 nhưng resource đã đổi v8:

~~~http
PATCH /products/P-100 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "product-P-100-v7"

{"name":"Bút gel xanh"}

HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"https://api.example.test/problems/stale-product",
 "title":"Precondition Failed","status":412,
 "code":"STALE_PRODUCT",
 "detail":"Sản phẩm đã thay đổi. Hãy tải lại trước khi cập nhật."}
~~~

| Ngữ cảnh | Status phù hợp | Ý nghĩa |
|---|---|---|
| POST trùng SKU trong tenant | **409** | Unique invariant xung đột trạng thái |
| PATCH ETag cũ trong If-Match | **412** | Precondition sai |
| PATCH thiếu If-Match bắt buộc | **428 Precondition Required** | Không cung cấp điều kiện được yêu cầu |
| PATCH ETag đúng, product ARCHIVED | **409** | Trạng thái nghiệp vụ cấm cập nhật |
| If-Match sai cú pháp | **400** | Request/header không hợp lệ |
| Product không tồn tại hoặc bị che theo quyền | **404** | Không lộ resource trái phạm vi |
| Body hợp cú pháp nhưng sai quy tắc nội dung | **422** hoặc mã đã công bố | Không nhất thiết có tranh chấp |
| Chưa xác thực/không có quyền | **401/403**, có thể 404 che giấu | Xử lý quyền trước khi lộ version |
| DB timeout/down | **5xx/503** | Không mặc định là lỗi do caller |

**Không đồng nhất 409 với 422**: 409 gắn với trạng thái hiện tại; 422 gắn với nội dung không thể xử lý theo ngữ nghĩa. **428 khác 412**: thiếu precondition so với precondition không thỏa. Spring exception chỉ là tín hiệu kỹ thuật; mã HTTP phải dựa trên **use case và request cụ thể**.

## 3. If-Match, ETag và điểm cập nhật nguyên tử

GET trả **strong ETag** của selected representation:

~~~http
GET /products/P-100 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
ETag: "product-P-100-v7"
Cache-Control: private, no-cache
Content-Type: application/json

{"id":"P-100","sku":"SKU-100","name":"Bút xanh","version":7}
~~~

Client giữ nguyên ETag opaque rồi gửi **If-Match** khi ghi. **If-Match dùng strong comparison**: ETag **W/"product-P-100-v7"** không khớp strong validator v7; header có thể chứa danh sách entity-tag. **If-Match: \*** chỉ yêu cầu target representation hiện tồn tại, **không thay thế kiểm soát phiên bản**. Parser production phải xử lý cú pháp RFC, không so raw string đơn giản. ETag phải thực sự đổi khi representation cần bảo vệ thay đổi; một cột @Version không luôn bao quát response tổng hợp hoặc biến thể theo người dùng.

**Đọc rồi so version, sau đó UPDATE không điều kiện** có race: hai transaction cùng thấy v7 và đều ghi đè nhau. Với conditional SQL, phép so và ghi là **một thao tác nguyên tử**:

~~~sql
UPDATE products
SET name = :name, version = version + 1
WHERE id = :id AND tenant_id = :tenant_id
  AND version = :expected_version;
~~~

Một row được cập nhật nghĩa là thao tác thắng; **0 row** phải được phân loại tiếp (không tồn tại, đổi quyền hoặc stale). JPA **@Version** tạo optimistic locking tương đương cho managed entity. Không chỉ dựa vào phép kiểm If-Match tại controller.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant DB as Database
    Note over A,B: Cả hai PATCH với ETag v7
    par Transaction A
      A->>DB: UPDATE WHERE version=7
    and Transaction B
      B->>DB: UPDATE WHERE version=7
    end
    DB-->>A: Thắng hoặc conflict
    DB-->>B: Conflict hoặc thắng
    Note over A,B: Một commit, phiên bản trở thành v8
~~~

Với **hai PATCH khác tên, cùng ETag v7, có quyền và không gặp lỗi hạ tầng**, kỳ vọng hợp đồng mẫu là **một 200 và một 412**, trạng thái cuối đúng yêu cầu thắng; không cố định client A thắng. Sau 412, client **GET lại, so thay đổi rồi chọn merge/retry có điều kiện mới**. Nếu response lần trước mất, retry bị 412 không chứng minh thao tác trước đã thành công: người khác cũng có thể đã sửa.

## 4. Phân loại exception Spring/JPA theo ngữ cảnh

| Exception hoặc lỗi | Có thể báo điều gì? | Cách xử lý |
|---|---|---|
| **ObjectOptimisticLockingFailureException / OptimisticLockingFailureException**, JPA **OptimisticLockException** | Phiên bản entity đổi trong lúc ghi | Xác minh precondition đang xử lý: **412** khi If-Match thực sự stale; không mặc định cho mọi endpoint |
| **DataIntegrityViolationException** | Unique/FK/NOT NULL/check constraint | Chỉ **409** khi xác định đúng conflict nghiệp vụ, ví dụ unique SKU |
| **PessimisticLockingFailureException / CannotAcquireLockException** | Tranh chấp lock | Không tự chứng minh client đã gửi ETag sai |
| **QueryTimeoutException / transaction timeout** | DB vượt deadline | Điều tra/retry an toàn hoặc lỗi hạ tầng |
| **DataAccessResourceFailureException** | Database không sẵn sàng | **5xx/503**, không phải 409 do người dùng |

**Đừng viết handler toàn cục** chuyển *mọi* DataIntegrityViolationException thành 409 hoặc *mọi* OptimisticLockingFailureException thành 412. Một lỗi NOT NULL do bug mapping không phải “SKU đã tồn tại”; optimistic lock trên một job nội bộ không có If-Match cũng không tự là 412.

**Ranh giới flush/commit:** repository.save() chưa chắc phát SQL hoặc commit. @Version và unique constraint có thể thất bại tại **flush hoặc commit**. Spring proxy thường commit transaction **sau khi phương thức @Transactional chạy xong nhưng trước khi controller nhận kết quả**. Nếu cần bắt lỗi commit để ánh xạ, dùng **façade không giao dịch gọi bean giao dịch riêng qua Spring proxy**; tránh self-invocation làm mất @Transactional. Không nuốt exception trong transaction đã rollback-only rồi trả thành công.

Khi phân loại lỗi constraint, sử dụng metadata/constraint name đáng tin từ driver hoặc xác minh **sau rollback trong transaction mới**. Không so chuỗi SQL exception message theo ngôn ngữ/phiên bản, không trả SQLState hoặc tên bảng ra API. **SELECT trước INSERT không chống race**: unique index tại DB mới bảo vệ invariant.

## 5. Contract mẫu: POST tạo SKU và PATCH đổi tên theo ETag

Giả định API cho một catalog đa tenant:

~~~text
POST  /products
GET   /products/{productId}
PATCH /products/{productId}
~~~

**Quy tắc sản phẩm:**

- Mỗi tenant có **SKU duy nhất**; tenant khác có thể dùng SKU giống nhau.
- Khi POST thành công, tạo product và trả **201 Created** với **Location**.
- GET trả representation và strong ETag; không tiết lộ sản phẩm tenant khác.
- PATCH chỉ cho đổi **name** bằng **application/merge-patch+json**, bắt buộc **If-Match** có validator cụ thể theo contract.
- PATCH thành công trả **200** với body và ETag mới.
- Product có trạng thái **ARCHIVED** không được đổi tên; nếu If-Match vẫn đúng, trả **409 PRODUCT_ARCHIVED**.

| Use case | Status | Mã lỗi ứng dụng |
|---|---|---|
| POST SKU đã tồn tại trong tenant | **409 Conflict** | SKU_ALREADY_EXISTS |
| PATCH If-Match cũ | **412 Precondition Failed** | STALE_PRODUCT |
| PATCH không gửi If-Match | **428 Precondition Required** | IF_MATCH_REQUIRED |
| PATCH có header không thể parse | **400 Bad Request** | INVALID_IF_MATCH |
| PATCH ETag đúng nhưng product ARCHIVED | **409 Conflict** | PRODUCT_ARCHIVED |
| GET/PATCH product không thuộc phạm vi quyền | **403/404** theo chính sách | FORBIDDEN/PRODUCT_NOT_FOUND |

Mọi tên ID/tenant ví dụ đều là giả. Hợp đồng phải rõ status được quyết định theo **lỗi thực tế nào đã xảy ra**; khi cùng tồn tại nhiều điều kiện lỗi, việc trả lỗi còn phụ thuộc thứ tự **xác thực, tìm resource, precondition evaluation, validation và domain rules** theo HTTP semantics. Đừng phát 412 kèm dữ liệu version của resource mà caller không có quyền.

## 6. Java/Spring: entity, repository và lớp giao dịch

Mô hình tối giản cho **Spring Boot 3 + Spring Data JPA**:

~~~java
import jakarta.persistence.*;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

@Entity
@Table(
    name = "products",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_products_tenant_sku",
        columnNames = {"tenant_id", "sku"}
    )
)
class ProductEntity {
    @Id
    private String id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(nullable = false)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Version
    private Long version;

    @Enumerated(EnumType.STRING)
    private ProductState state;

    protected ProductEntity() {}

    void ensureRenamable() {
        if (state == ProductState.ARCHIVED) {
            throw new ProductArchivedException();
        }
    }

    void rename(String next) {
        ensureRenamable();
        name = next;
    }

    // Constructor nghiệp vụ, getters/snapshot được lược bỏ.
}

enum ProductState { ACTIVE, ARCHIVED }

interface ProductRepository
        extends JpaRepository<ProductEntity, String> {
    Optional<ProductEntity> findByIdAndTenantId(
        String id, String tenantId);
}
~~~

**@Version** giúp ORM kiểm tra phiên bản khi ghi entity. **@UniqueConstraint** mô tả invariant SKU theo tenant; trên production phải xác minh migration/schema thật đã tạo unique index tương ứng (không tin annotation luôn tự sửa database). Service không được tin tenantId từ JSON/client header tự khai; phải lấy **tenant đã xác thực**.

### 6.1. Service giao dịch: không gắn status vào repository

Đây là **skeleton use case** để thấy rõ ranh giới; những lớp như **ProductEtag, IfMatchCondition, AuthorizedTenant, ProductSnapshot** là thành phần ứng dụng phải triển khai.

~~~java
@Service
class ProductWriteTx {
    private final ProductRepository products;
    private final ProductAccessPolicy access;

    ProductWriteTx(ProductRepository products,
                   ProductAccessPolicy access) {
        this.products = products;
        this.access = access;
    }

    @Transactional
    ProductSnapshot rename(
            String id, String requestedName,
            IfMatchCondition condition, AuthorizedTenant caller) {

        access.requireCanEdit(caller);
        ProductEntity product = products
            .findByIdAndTenantId(id, caller.tenantId())
            .orElseThrow(ProductNotFoundException::new);

        // Conflict nghiệp vụ 409 tồn tại độc lập với If-Match:
        // không biến thành 412 chỉ vì client gửi ETag cũ.
        product.ensureRenamable();

        String etag = ProductEtag.from(product);
        if (!condition.matchesStrong(etag)) {
            throw new StaleProductException();
        }

        product.rename(requestedName);
        products.flush(); // Buộc ORM phát UPDATE trước return.
        return ProductSnapshot.from(product);
    }
}
~~~

**Chú ý về thứ tự:** trong ứng dụng thực, kiểm tra **quyền trên sản phẩm đích**, không chỉ requireCanEdit trên tenant. Tìm theo tenant để giới hạn dữ liệu; nếu quyền phụ thuộc workspace, owner hoặc role của product, policy phải xét đủ resource đó. Phương thức **matchesStrong** cần parse đúng If-Match theo RFC, không dùng so sánh chuỗi tùy tiện.

Đoạn code trên không chứa một catch cho mọi optimistic exception. Nếu một request cạnh tranh vượt qua kiểm tra ETag ban đầu nhưng bị **@Version** chặn tại flush/commit, lỗi có thể thoát khỏi transactional proxy. Một lớp **façade bên ngoài transaction** sẽ quyết định có đủ bằng chứng rằng precondition của thao tác này đã stale hay không rồi chuyển thành domain error phù hợp.

### 6.2. Façade xử lý lỗi xảy ra sau khi transaction kết thúc

~~~java
@Service
class ProductCommandFacade {
    private final ProductWriteTx tx;
    private final ProductConflictClassifier classifier;

    ProductCommandFacade(ProductWriteTx tx,
                         ProductConflictClassifier classifier) {
        this.tx = tx;
        this.classifier = classifier;
    }

    ProductSnapshot rename(
            String id, String name,
            IfMatchCondition condition, AuthorizedTenant caller) {
        try {
            // @Transactional nằm trên bean khác: proxy commit
            // trước khi lời gọi tx.rename trả về façade.
            return tx.rename(id, name, condition, caller);
        } catch (OptimisticLockingFailureException e) {
            // Chỉ ánh xạ 412 nếu xác minh được optimistic
            // conflict thuộc product/precondition đang xử lý.
            throw classifier.classifyConditionalWrite(
                id, condition, caller, e);
        }
    }
}
~~~

**ProductConflictClassifier** là abstraction phải triển khai. Nó có thể kiểm tra **resource/version trong transaction đọc mới sau rollback**, phân biệt resource mất/quyền đổi với precondition stale. Không đọc resource bên trong transaction đã thất bại rồi tiếp tục sử dụng entity lỗi. Nếu không thể xác nhận precondition đã sai, **không tự gán 412 cho mọi lỗi locking**.

Façade cũng là chỗ thích hợp để phân loại **known unique constraint** của thao tác POST tạo SKU sau khi transaction tạo kết thúc/rollback. Khi bắt **DataIntegrityViolationException**, chỉ chuyển thành **SkuAlreadyExistsException** nếu đúng unique invariant đó; lỗi database khác phải được xử lý riêng. Đặc biệt, **không retry tự động PATCH bằng ETag cũ trên phiên bản mới** để biến yêu cầu thất bại thành thành công trái ý client.

## 7. Spring MVC: controller mỏng và Problem Details

Controller chuyển **HTTP If-Match + DTO** sang use case; service chịu trách nhiệm quyền, transaction và phân loại xung đột ở tầng nghiệp vụ:

~~~java
record RenameProductRequest(@NotBlank String name) {}

@RestController
@RequestMapping("/products")
class ProductController {
    private final ProductCommandFacade commands;
    private final CallerResolver callers;

    ProductController(ProductCommandFacade commands,
                      CallerResolver callers) {
        this.commands = commands;
        this.callers = callers;
    }

    @PatchMapping(
        path = "/{id}", consumes = "application/merge-patch+json")
    ResponseEntity<ProductView> rename(
            @PathVariable String id,
            @RequestHeader(name = "If-Match", required = false)
                String ifMatch,
            @Valid @RequestBody RenameProductRequest request) {

        if (ifMatch == null || ifMatch.isBlank()) {
            throw new MissingIfMatchException();
        }
        IfMatchCondition condition =
            IfMatchCondition.parseRequiredVersion(ifMatch);
        ProductSnapshot changed = commands.rename(
            id, request.name(), condition,
            callers.fromSecurityContext());

        return ResponseEntity.ok()
            .eTag(ProductEtag.from(changed))
            .body(ProductView.from(changed));
    }
}
~~~

Ví dụ dùng Spring MVC, cần thêm imports và implementation **ProductView, CallerResolver, IfMatchCondition** và exception types. DTO chỉ cho phép client sửa **name**; không bind trực tiếp entity có **tenantId, SKU, version**. Với **JSON Merge Patch** đầy đủ, phải định nghĩa rõ trường vắng mặt/null và field không cho phép sửa. If-Match parser phải hỗ trợ cú pháp HTTP đúng; nếu contract đòi **version validator cụ thể**, xử lý **If-Match: \*** minh bạch thay vì ngầm coi là một ETag phiên bản.

**@RestControllerAdvice** ánh xạ exception domain đã phân loại sang status HTTP và Problem Details:

~~~java
@RestControllerAdvice
class ProductErrorAdvice {
    @ExceptionHandler(StaleProductException.class)
    ResponseEntity<ProblemDetail> stale(RuntimeException ex) {
        return problem(412, "STALE_PRODUCT",
            "Sản phẩm đã đổi, hãy tải lại");
    }

    @ExceptionHandler(SkuAlreadyExistsException.class)
    ResponseEntity<ProblemDetail> duplicate(RuntimeException ex) {
        return problem(409, "SKU_ALREADY_EXISTS",
            "Mã SKU đã được sử dụng trong phạm vi được phép");
    }

    @ExceptionHandler(ProductArchivedException.class)
    ResponseEntity<ProblemDetail> archived(RuntimeException ex) {
        return problem(409, "PRODUCT_ARCHIVED",
            "Sản phẩm đã lưu trữ");
    }

    @ExceptionHandler(MissingIfMatchException.class)
    ResponseEntity<ProblemDetail> missing(RuntimeException ex) {
        return problem(428, "IF_MATCH_REQUIRED",
            "Hãy cung cấp If-Match");
    }

    private ResponseEntity<ProblemDetail> problem(
            int status, String code, String detail) {
        ProblemDetail p = ProblemDetail.forStatus(status);
        p.setTitle(HttpStatus.valueOf(status).getReasonPhrase());
        p.setDetail(detail);
        p.setProperty("code", code);
        return ResponseEntity.status(status)
            .contentType(MediaType.parseMediaType(
                "application/problem+json"))
            .cacheControl(CacheControl.noStore()).body(p);
    }
}
~~~

**Các domain exception đều là kiểu ứng dụng tự khai báo.** Cần xử lý riêng **ProductNotFoundException (404)**, If-Match sai cú pháp **400**, validation **400/422**, lỗi unknown **5xx**. **401/403** thường xảy ra trong Spring Security filter trước controller/advice; cấu hình entry point/denied handler nếu yêu cầu schema thống nhất.

**Thứ tự quan trọng:** server phải bỏ qua HTTP preconditions khi request không có chúng vốn đã cần trả lỗi ngoài **2xx hoặc 412** (quy tắc RFC 9110). Vì vậy kiểm tra xác thực, quyền, resource, những conflict nghiệp vụ độc lập (product ARCHIVED) trước khi kết luận stale. Sau đó dùng **@Version/atomic update** để tránh TOCTOU race. Không trả ETag hiện tại hoặc chi tiết DB của resource caller không được xem.

## 8. Unique constraint, delete conflict và lỗi hạ tầng

**Hai POST cùng SKU trong một tenant:** hai request có thể cùng SELECT thấy “chưa có SKU”, nhưng **unique index (tenant_id, sku)** chỉ cho một transaction commit. Nếu lỗi là **đúng constraint nghiệp vụ đã xác định**, request còn lại nhận **409 SKU_ALREADY_EXISTS**, không tạo thêm row. Không được áp dụng quy tắc đó cho SKU giống nhau ở hai tenant khác nhau nếu contract cho phép.

Nếu API có **Idempotency-Key**, retry cùng key/payload có thể được trả lại kết quả cũ theo hợp đồng thay vì tạo lần nữa; **retry cùng thao tác** khác **tạo hai thao tác độc lập với SKU trùng**. Việc dedup phải nguyên tử, không dựa vào biến RAM của một API instance.

**FK violation khi xóa** category còn products có thể là **409 CATEGORY_IN_USE** nếu chính sách không cho xóa. Nhưng lỗi FK bất ngờ do bug dữ liệu/transaction không được che thành conflict hợp lệ. Khi resource không tồn tại, xét **404**; khi không có quyền, xét **403/404** theo chính sách.

**Deadlock, serialization failure hoặc lock timeout** không chứng minh precondition sai. Có thể retry transaction với giới hạn/backoff nếu semantics và side effects cho phép; nếu vẫn lỗi, trả **5xx/503** thích hợp. Không tự retry PATCH với ETag cũ bằng version mới. Khi có email/payment/webhook, cần idempotency hoặc **transactional outbox** để tránh tạo tác dụng phụ trùng trong quá trình retry.

## 9. Bảo mật và vận hành khi báo lỗi tranh chấp

**Tránh rò rỉ thông tin qua thông báo lỗi:** Nếu người thuộc tenant B đoán ID/SKU của tenant A, response không được cho biết **version hiện tại, tên owner, mã constraint hoặc tài nguyên nội bộ**. Cần kiểm tra quyền trước khi phân biệt stale với conflict, bảo vệ lookup bằng tenant/role scope đã xác thực và áp dụng chính sách **403 hoặc 404 che giấu** nhất quán.

Những thông tin hữu ích cho **log nội bộ**: route template, HTTP status, domain error code, correlation/trace ID, loại constraint đã phân loại, transaction outcome, phiên bản kỳ vọng/hiện tại **chỉ khi không vi phạm chính sách dữ liệu**. Không log Authorization, Cookie, SQL có PII hay toàn bộ payload. Metric chỉ nên có nhãn giới hạn như **route, errorCode, result**; không dùng raw SKU, tenant ID hoặc correlation ID làm metric tags.

Tỷ lệ 412 tăng có thể là dấu hiệu **nhiều người sửa cùng resource**, không nhất thiết server lỗi. Tỷ lệ 409 SKU_ALREADY_EXISTS tăng có thể phản ánh retry thiếu idempotency hoặc trải nghiệm chọn mã SKU kém. Ngược lại, **deadlock/5xx tăng** là dấu hiệu cần điều tra cấu hình transaction và database, không được trộn vào cùng dashboard “business conflicts”.

## 10. Kiểm thử: phải đối chiếu status với dữ liệu sau transaction

### 10.1. Ma trận test trọng tâm

| Kịch bản | HTTP dự kiến | Điều cần xác minh sau request |
|---|---|---|
| POST SKU mới trong tenant A | **201** | Một product, Location hợp lệ |
| POST cùng SKU trong tenant A | **409** | Không tạo product thứ hai |
| POST cùng SKU trong tenant B | **201** nếu caller có quyền | Unique index đúng scope tenant |
| PATCH If-Match đúng, product ACTIVE | **200** | Name đổi và ETag/version mới |
| PATCH thiếu If-Match | **428** | Không có update |
| PATCH If-Match cũ | **412** | Không ghi đè thay đổi trước |
| PATCH weak validator không strong-match | **412** khi precondition được đánh giá | Không ghi |
| PATCH header sai cú pháp | **400** | Không ghi |
| PATCH sản phẩm ARCHIVED dù header đang khớp | **409** | Không ghi |
| Product của tenant khác | **403/404** theo policy | Không lộ existence/version |
| Hai PATCH cùng v7, hai tên khác | **Một 200, một 412** trong ví dụ | Một commit; version +1 |
| Hai POST cùng SKU, hai transaction | **Một 201, một 409** | Một row theo (tenant, sku) |
| Lỗi DB không xác định/deadlock | **5xx/retry** theo policy | Không tự trả 409/412 sai ngữ nghĩa |

### 10.2. MockMvc: kiểm tra HTTP semantics

Giả định test class đã có **MockMvc mockMvc**, fixture sản phẩm P-100 thuộc caller và Spring Security Test. Những đoạn sau kiểm tra mapping; cần bổ sung imports và authentication fixture phù hợp ứng dụng:

~~~java
// Không có If-Match: 428, không được thực hiện rename.
mockMvc.perform(patch("/products/P-100")
        .with(user("editor"))
        .with(csrf())
        .contentType("application/merge-patch+json")
        .content("{\"name\":\"Tên mới\"}"))
    .andExpect(status().is(428))
    .andExpect(jsonPath("$.code").value("IF_MATCH_REQUIRED"));

// Có If-Match cũ: 412, response Problem Details.
mockMvc.perform(patch("/products/P-100")
        .with(user("editor"))
        .with(csrf())
        .header("If-Match", "\"product-P-100-v6\"")
        .contentType("application/merge-patch+json")
        .content("{\"name\":\"Tên mới\"}"))
    .andExpect(status().isPreconditionFailed())
    .andExpect(header().string(
        "Content-Type", containsString("application/problem+json")))
    .andExpect(jsonPath("$.status").value(412))
    .andExpect(jsonPath("$.code").value("STALE_PRODUCT"));
~~~

**MockMvc có thể không chạy qua toàn bộ gateway/filter chain thực tế** nếu test cấu hình tối giản. Các test phải xác nhận service/fixture không ghi dữ liệu sau 412/428; mock service chỉ chứng minh controller và advice, **không chứng minh optimistic locking**.

### 10.3. Concurrency test với database thực

Dùng PostgreSQL/MySQL tương đương production, hai transaction độc lập. Test phải **commit fixture trước khi các worker chạy**; tránh dùng một transaction của thread JUnit rồi nghĩ nó được chia sẻ qua HTTP.

~~~text
Arrange:
    tenant A có product P-100, name="Cũ", version=7
    client A và B cùng nhận strong ETag v7
    hai request đều được phép sửa P-100

Act:
    hai request PATCH khác name gửi gần như đồng thời
    cả hai dùng If-Match v7

Assert:
    kết quả là (200, 412) hoặc (412, 200)
    product cuối trùng giá trị của request thắng
    version tăng đúng 1 theo contract test
    không có hai event/update thành công
    response thua là 412 Problem Details, không phải 500
~~~

Đồng bộ bằng **CountDownLatch/CyclicBarrier** ở client giúp gửi gần nhau, nhưng **không bảo đảm hai transaction cùng đọc v7**; với race khó tái hiện có thể dùng hook test-only sau điểm đọc, có timeout và không bật production. Test POST unique cũng cần hai request đồng thời với **cùng tenant/SKU** rồi xác minh **chỉ một row**, constraint DB hoạt động và request thua được phân loại thành 409.

Tăng coverage bằng **multi-instance test** qua cùng DB, thử rollback/commit failure, và xác minh hệ thống không gọi payment/email hai lần nếu use case có side effect. Không lấy “1000 request đều không trả 500” làm bằng chứng rằng business invariant đúng.

## 11. Bài thực hành: chọn 409 hay 412

Một API **/reservations/{id}** cho phép đổi thời gian giữ chỗ bằng PATCH có **If-Match**, còn **POST /reservations** tạo reservation mới. Mỗi phòng tại một khung giờ chỉ có một reservation được xác nhận.

Hãy chọn status, error code và nơi cần bảo vệ invariant cho từng trường hợp:

1. PATCH gửi **If-Match phiên bản 3**, nhưng resource hiện tại ở phiên bản 4.
2. PATCH không gửi If-Match dù hợp đồng bắt buộc.
3. PATCH có ETag đúng nhưng reservation đang **CANCELLED**, không thể đổi giờ.
4. POST tạo reservation có cùng phòng/khung giờ với reservation đã xác nhận.
5. Hai POST cùng thời điểm cùng phòng/khung giờ, cả hai kiểm tra thấy “chưa có”.
6. Database phát sinh deadlock tạm thời; không có bằng chứng precondition sai.
7. Caller ở tenant B đoán đúng reservation ID của tenant A.

**Hướng giải:** (1) **412 STALE_RESERVATION**; (2) **428 IF_MATCH_REQUIRED**; (3) **409 INVALID_RESERVATION_STATE**; (4) **409 SLOT_UNAVAILABLE**; (5) **unique constraint/lock/transaction** ngăn hai commit, lỗi được phân loại sang **409**; (6) retry transaction có giới hạn nếu an toàn, sau đó lỗi **5xx/503** theo chính sách, **không** tự là 412; (7) **403 hoặc 404 che giấu**, không lộ trạng thái hoặc ETag. Giải thích vì sao **SELECT trước INSERT** không đủ để xử lý câu 5.

## 12. Checklist và nguồn tham khảo

- [ ] Phân biệt **409 là xung đột trạng thái** và **412 là điều kiện HTTP không thỏa**; 428 dành cho precondition bắt buộc bị thiếu.
- [ ] Xác thực/ủy quyền trước khi để lộ conflict, tồn tại resource hoặc ETag; query có tenant scope.
- [ ] Strong ETag phản ánh đúng representation; If-Match được parse/đánh giá theo HTTP semantics.
- [ ] Precondition và ghi dữ liệu được bảo vệ **nguyên tử** bằng @Version, CAS hoặc locking phù hợp.
- [ ] Unique/FK constraint được phân loại đúng business rule; không trả 409 cho mọi DataIntegrityViolationException.
- [ ] Lỗi **flush/commit** được bắt ở ranh giới transaction thích hợp; không nuốt rollback-only.
- [ ] Lỗi hạ tầng/deadlock không bị che thành 409/412; retry có giới hạn và không lặp side effect.
- [ ] @RestControllerAdvice dùng Problem Details, code ổn định, không lộ SQL/stack trace/tenant data.
- [ ] MockMvc/HTTP tests kiểm header/status/schema; database concurrency tests kiểm **dữ liệu cuối và bất biến**.
- [ ] OpenAPI mô tả **409/412/428**, request If-Match và các mã lỗi liên quan.

Tài liệu: [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) (409, 412, preconditions và If-Match); [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585) (428); [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457); [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html); [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html); [OpenAPI Specification](https://spec.openapis.org/oas/latest.html).

**Ghi nhớ:** Spring Data exception là dấu hiệu **lỗi dữ liệu/transaction**, không phải mã HTTP. **409** dành cho conflict với trạng thái nghiệp vụ, **412** dành cho HTTP precondition thất bại; ánh xạ đúng đòi hỏi biết **hợp đồng, quyền truy cập, nguồn tranh chấp và trạng thái commit thực tế**.
