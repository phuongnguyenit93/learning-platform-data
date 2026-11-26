# Chuyển lỗi dữ liệu thành phản hồi API phù hợp trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **lỗi đầu vào**, **lỗi nghiệp vụ**, **lỗi dữ liệu không tồn tại**, **xung đột ghi**, **lỗi hạ tầng** và **kết quả ghi chưa xác định** khi ứng dụng sử dụng Spring Data Couchbase.
2. Thiết kế ranh giới dịch lỗi từ **Couchbase Java SDK → Spring Data repository / CouchbaseTemplate → application service → REST API**, tránh để HTTP controller biết trực tiếp tên exception nội bộ.
3. Ánh xạ chính xác các tình huống thường gặp sang HTTP `400`, `401`, `403`, `404`, `409`, `412`, `428`, `422` và các mã `5xx` khi thích hợp; biết khi nào **không** nên biến lỗi dữ liệu thành lỗi client.
4. Sử dụng `ProblemDetail` (RFC 9457) và `@RestControllerAdvice` của Spring Boot để cung cấp contract nhất quán gồm `type`, `title`, `status`, `detail`, `instance`, `code` và `traceId`.
5. Xử lý đúng `OptimisticLockingFailureException` / CAS conflict, duplicate key, TTL expiry, query index lag, document mapping lỗi, timeout, durability failure và các ngoại lệ transaction.
6. Phân biệt mutation **chắc chắn chưa áp dụng** với mutation **có thể đã áp dụng nhưng mất phản hồi**; thiết kế idempotency và API tra cứu trạng thái khi outcome ambiguous.
7. Biết cách áp dụng cùng policy cho synchronous và reactive repositories mà không làm mất error signal, tự động retry quá mức hoặc làm rò rỉ credentials.
8. Viết unit tests, controller tests, SDK integration tests và contract tests để chứng minh API trả **đúng status, problem code và trạng thái dữ liệu cuối**.
9. Tổ chức logging, tracing, metrics, rate limiting, SLO và runbook để xử lý lỗi đúng trong production.

Bài thuộc chương **Xử lý lỗi** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase bằng Spring Data document mapping, repository, `CouchbaseTemplate` và truy vấn SQL++; thiết kế bucket/scope/collection, index, TTL, CAS, transaction và API reactive với hiệu năng, nhất quán và khả năng vận hành.

> **Hợp đồng quan trọng:** HTTP status mô tả điều **client được phép hiểu và hành động**, không phải bản sao tên exception Couchbase. Cùng một `DocumentNotFoundException` có thể là `404` trong API GET, nhưng lại là `409` khi một bước xác nhận đơn hàng đòi document phải còn tồn tại. Cần có **ngữ cảnh nghiệp vụ** trước khi trả lời.

## 1. Vì sao một lỗi Couchbase không tương đương một HTTP status?

Giả sử ứng dụng bán hàng có các API:

~~~text
GET    /api/orders/{id}                 Đọc đơn hàng
POST   /api/orders                      Tạo đơn hàng với Idempotency-Key
PUT    /api/orders/{id}                 Cập nhật với If-Match
DELETE /api/orders/{id}                 Hủy/xóa theo policy
POST   /api/orders/{id}/confirm         Xác nhận và cập nhật tồn kho
GET    /api/orders?customerId=...       Tìm kiếm qua SQL++
GET    /api/operations/{requestId}      Tra cứu tiến độ hoặc kết quả thao tác
~~~

Các operation dùng API Couchbase khác nhau:

| API | Đường dữ liệu | Rủi ro |
| --- | --- | --- |
| GET by id | KV `findById` | Không tồn tại/hết TTL, lỗi mapping |
| POST | `insert` hoặc repository save | Trùng ID, dữ liệu sai, timeout ghi |
| PUT | Read-modify-write với `@Version` | CAS stale, xóa song song |
| DELETE | KV remove | Key không tồn tại, race |
| Confirm | Transaction Order + Inventory | Rollback, commit ambiguous, hết hàng |
| Search | SQL++/Index Service | Index lag, thiếu index, timeout, malformed query |
| Async submit | Reactive repository/service | Publisher error, cancellation, không subscribe |

Một document không có trong KV có thể xảy ra vì:

- Client truyền ID không tồn tại thật sự.
- Document đã hết TTL và không còn được đọc qua KV.
- Service đang chọn nhầm bucket/scope/collection.
- Thao tác delete đã hoàn tất bởi một request khác.
- Dữ liệu vừa được tạo ở cluster khác nhưng luồng replication chưa bắt kịp.
- Adapter dùng repository có type filter/alias khác kỳ vọng.

Trả cùng một `404` cho tất cả các tình huống này có thể **che một bug cấu hình nghiêm trọng**.

### 1.1. Bốn lớp trách nhiệm

~~~mermaid
flowchart TD
    HTTP["HTTP Controller"] --> APP["Application / Domain Service"]
    APP --> PORT["Persistence port / Repository adapter"]
    PORT --> SDK["Spring Data Couchbase / Java SDK"]
    SDK --> SERVER["Couchbase Server"]
    SERVER --> SDK
    SDK --> CLASS["Phân loại storage failure"]
    CLASS --> APP
    APP --> DECISION["Quyết định business meaning"]
    DECISION --> HTTP
    HTTP --> PROBLEM["HTTP Response / ProblemDetail"]
~~~

**SDK adapter** biết các loại lỗi kỹ thuật: CAS mismatch, not found, query failed, durability impossible, timeout. **Application service** biết operation đang thực hiện: tra cứu optional, tạo mới, xác nhận đơn, hoàn tiền. **Controller/advice** chuyển kết quả thành contract công khai và không phát tán stack trace, SQL++ hoặc thông tin cluster.

### 1.2. Điều không nên làm

~~~java
@RestController
class BadOrderController {

    @GetMapping("/api/orders/{id}")
    Object get(@PathVariable String id) {
        try {
            return repository.findById(id).orElseThrow();
        } catch (Exception ex) {
            // SAI: mọi lỗi đều là 404.
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, ex.getMessage());
        }
    }
}
~~~

Lỗi connection reset, lỗi mapping từ JSON cũ hoặc thiếu Query Index không được coi là “không có đơn hàng”. Đồng thời `ex.getMessage()` từ SDK có thể chứa keyspace, IDs, statements và chi tiết nội bộ không phù hợp đưa cho client.

### 1.3. Domain errors khác hẳn storage errors

Ví dụ `StockNotEnoughException` không phải lỗi từ Couchbase; nó là quyết định nghiệp vụ sau khi đọc stock mới nhất. Một transaction có thể thất bại do nó, nhưng client nên nhận vấn đề liên quan đến hết hàng, **không** nhận một thông báo chung “Couchbase transaction failed”.

Ngược lại, `AuthenticationFailureException` khi SDK đăng nhập Couchbase bằng secret sai là **sự cố cấu hình server-side**, không nên trả `401 Unauthorized` cho người mua hàng (họ không nhập credential Couchbase).

## 2. Thiết kế contract Problem Details ổn định

Spring Framework 6+/Spring Boot 3+ hỗ trợ `org.springframework.http.ProblemDetail`, phù hợp mô hình **Problem Details for HTTP APIs (RFC 9457)**.

Ví dụ API trả:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Request-Id: req-7e9b

{
  "type": "https://api.example.invalid/problems/order-version-conflict",
  "title": "Order version conflict",
  "status": 409,
  "detail": "Đơn hàng đã thay đổi. Hãy tải lại trước khi cập nhật.",
  "instance": "/api/orders/order-123",
  "code": "ORDER_VERSION_CONFLICT",
  "traceId": "01JTEST9H4V"
}
~~~

URL `example.invalid` là minh họa không truy cập được; production cần đăng ký namespace tài liệu lỗi ổn định của riêng mình. Trường `code` là extension field giúp client phân loại lỗi theo contract; `title/detail` cho người dùng, có thể được địa phương hóa.

### 2.1. Ý nghĩa các trường

| Trường | Nguồn | Khuyến nghị |
| --- | --- | --- |
| `type` | Định danh loại lỗi | URI cố định theo error code, không theo exception class |
| `title` | Tên ngắn gọn, chung cho một loại | Không chứa PII |
| `status` | Mã HTTP thực tế | Phải khớp response status |
| `detail` | Mô tả tình huống cụ thể | Sanitized, hữu ích nhưng không lộ hạ tầng |
| `instance` | Đường dẫn request | Không nhúng query token/secret nếu URL chứa thông tin nhạy cảm |
| `code` | Public business error code | Bền vững để client xử lý |
| `traceId` | Trace correlation | ID an toàn để support tra log |
| `requestId` | Business idempotency/operation | Chỉ khi user được phép thấy |
| `retryable` | Policy API, không từ một exception chung | Chỉ bật khi thật sự safe |
| `violations` | Lỗi validation field-level | Không echo giá trị nhạy cảm |

Không mặc định gửi `debugMessage`, `stackTrace`, `sqlpp`, `clusterHostname`, `bucketPassword` hoặc cause chain ra ngoài. Log nội bộ có thể giữ nguyên nhân đã redacted theo chính sách, response public chỉ cần contract chuẩn.

### 2.2. Nên thống nhất mã lỗi công khai

~~~text
VALIDATION_FAILED
ORDER_NOT_FOUND
ORDER_ALREADY_EXISTS
ORDER_VERSION_CONFLICT
ORDER_PRECONDITION_REQUIRED
ORDER_PRECONDITION_FAILED
ORDER_INVALID_TRANSITION
INVENTORY_INSUFFICIENT
REQUEST_ALREADY_PROCESSED
REQUEST_PAYLOAD_MISMATCH
DEPENDENCY_UNAVAILABLE
DEPENDENCY_TIMEOUT
WRITE_OUTCOME_UNKNOWN
QUERY_TEMPORARILY_UNAVAILABLE
INTERNAL_DATA_ERROR
INTERNAL_ERROR
~~~

Không nhất thiết tạo một `code` cho từng SDK exception: SDK versions khác nhau có thể đưa ra subtype khác nhau nhưng policy HTTP không đổi.

## 3. Bảng ánh xạ HTTP theo ý nghĩa của operation

| Ngữ cảnh | HTTP gợi ý | Public `code` | Vì sao |
| --- | --- | --- | --- |
| Body sai cú pháp JSON / sai type request | `400 Bad Request` | `INVALID_REQUEST` | Không parse được yêu cầu |
| Bean Validation thiếu/sai field | `400` hoặc `422` theo contract | `VALIDATION_FAILED` | Client cần sửa dữ liệu |
| Client chưa xác thực | `401 Unauthorized` | `AUTHENTICATION_REQUIRED` | Lỗi xác thực **API client** |
| Client không được phép thao tác Order | `403 Forbidden` | `ACCESS_DENIED` | Authorization của ứng dụng |
| GET Order ID hợp lệ nhưng không có | `404 Not Found` | `ORDER_NOT_FOUND` | Resource không tồn tại theo contract |
| POST create ID đã tồn tại | `409 Conflict` | `ORDER_ALREADY_EXISTS` | Xung đột với state |
| PUT cập nhật entity dựa CAS cũ | `409` | `ORDER_VERSION_CONFLICT` | Không dùng HTTP conditional header |
| PUT với `If-Match` không khớp ETag | `412 Precondition Failed` | `ORDER_PRECONDITION_FAILED` | HTTP conditional request failed |
| PUT bắt buộc `If-Match` nhưng thiếu | `428 Precondition Required` | `ORDER_PRECONDITION_REQUIRED` | Yêu cầu tiền điều kiện |
| Confirm Order bị hủy/đã hoàn tất | `409` | `ORDER_INVALID_TRANSITION` | Xung đột business state |
| Tồn kho không đủ | `409` hoặc `422` theo API | `INVENTORY_INSUFFICIENT` | Nghiệp vụ từ chối, không retry mù |
| Cùng idempotency key, payload khác | `409` | `REQUEST_PAYLOAD_MISMATCH` | Chống request replay sai |
| Service chủ động giới hạn request rate | `429 Too Many Requests` | `RATE_LIMITED` | Chính sách throttling của API |
| Couchbase tạm không khả dụng | `503 Service Unavailable` | `DEPENDENCY_UNAVAILABLE` | Server-side dependency lỗi |
| Backend dependency timeout | `503` hoặc `504` theo architecture | `DEPENDENCY_TIMEOUT` | Không được nói resource thiếu |
| Kết quả mutation không rõ | Theo status-lookup protocol | `WRITE_OUTCOME_UNKNOWN` | Có thể đã được áp dụng |
| JSON lưu trong DB không map được | `500 Internal Server Error` | `INTERNAL_DATA_ERROR` | Dữ liệu tồn tại nhưng schema/code sai |
| SQL++ thiếu index do triển khai | `500`/`503` theo root cause | `QUERY_UNAVAILABLE` | Không phải client không tìm thấy |
| Lỗi lập trình không biết trước | `500` | `INTERNAL_ERROR` | Lỗi nội bộ |

**HTTP status là một quyết định API contract.** Bảng trên là lựa chọn thiết kế phù hợp phổ biến, không phải Spring Data tự áp cho mọi ứng dụng. Chọn và tài liệu hóa một policy nhất quán; ví dụ dùng `422` cho validation domain có thể hợp lý, nhưng đừng để cùng lỗi lúc trả `400` lúc trả `422` tùy đường code.

### 3.1. Sự khác nhau giữa 409 và 412

- `409 Conflict`: application phát hiện trạng thái business/version đã thay đổi, không nhất thiết vì một HTTP conditional header.
- `412 Precondition Failed`: client gửi `If-Match` hoặc điều kiện HTTP khác và điều kiện đó không đúng tại thời điểm xử lý.
- `428 Precondition Required`: API yêu cầu conditional request, nhưng client bỏ qua `If-Match`.

Nếu API không hỗ trợ ETag/`If-Match`, đừng dùng `412` chỉ vì SDK có CAS. Ngược lại, nếu API công bố optimistic concurrency bằng HTTP ETag thì trả `409` cho mọi failed `If-Match` sẽ làm mất semantics chuẩn HTTP.

### 3.2. 404 so với 410 cho TTL và delete

`404` nói resource không khả dụng/không tìm thấy theo contract. `410 Gone` chỉ phù hợp nếu application **biết chắc resource đã từng tồn tại và đã bị loại bỏ vĩnh viễn** theo policy.

Một Couchbase `findById` trả empty sau expiry **không chứng minh** resource từng tồn tại; nếu không có audit/tombstone lịch sử tin cậy, trả `404`. Không dùng `410` cho mọi document expired chỉ vì TTL được đặt.

### 3.3. DELETE không tìm thấy: 204 hay 404?

Cả hai có thể hợp lý tùy contract:

- `DELETE` idempotent: trả `204 No Content` ngay cả khi key đã không còn, vì state mong muốn “không tồn tại” đã đạt.
- `DELETE` yêu cầu resource phải tồn tại: trả `404` khi missing.

Idempotent nghĩa là **thực hiện lại không tạo tác dụng phụ mới**, không bắt buộc tất cả lần gọi phải trả cùng HTTP status. Việc chọn `204`/`404` nên thống nhất trong OpenAPI/contract tests.

## 4. Ranh giới lỗi trong Spring Data và Couchbase SDK

Một operation có thể đi qua:

~~~text
HTTP request
  -> Spring MVC / WebFlux
  -> validation / security
  -> application service
  -> repository / CouchbaseTemplate
  -> Spring Data exception translation
  -> Couchbase Java SDK
  -> Couchbase Server
~~~

Couchbase Java SDK ném các lỗi cụ thể từ `com.couchbase.client.core.error` hoặc các module transactions; Spring Data có thể dịch một số lỗi sang hệ `org.springframework.dao.DataAccessException` như `OptimisticLockingFailureException`.

### 4.1. Bảng nguồn lỗi tiêu biểu

| Nguồn | Tên lỗi/mẫu lỗi | Mức nên phân loại |
| --- | --- | --- |
| Spring Data repository `findById` | `Optional.empty()` | Application decide missing |
| SDK `get`/`remove` | `DocumentNotFoundException` | Storage adapter |
| SDK `insert` | `DocumentExistsException` | Storage adapter |
| Repository `save` entity `@Version` stale | `OptimisticLockingFailureException` | Storage adapter/domain |
| SDK conditional replace CAS stale | `CasMismatchException` | Storage adapter/domain |
| SDK durability timeout/ambiguous | `AmbiguousTimeoutException` hoặc subtype theo SDK | Adapter → unknown outcome |
| SDK connection/operation timeout | `UnambiguousTimeoutException` hoặc subtype | Adapter → transient failure, theo semantics |
| SDK query | `CouchbaseException`, `QueryException` hoặc subtype/version | Adapter → query unavailable/syntax/index |
| SDK resource routing | Bucket/scope/collection not found | Deployment/adapter, thường 5xx |
| Converter/entity mapping | `MappingException` hoặc exception mapping cụ thể | Internal data quality |
| SDK authentication/RBAC | `AuthenticationFailureException`/authorization subtype | Dependency configuration/security |
| Couchbase Transactions | `TransactionFailedException`, `TransactionExpiredException` | Service phân loại cause |
| Couchbase Transactions | `TransactionCommitAmbiguousException` | Unknown outcome protocol |

Tên và inheritance của một số SDK exceptions thay đổi theo release. **Không dựa vào string match của exception message** như `contains("CAS")`/`contains("index")`; dùng type, cause chain, error context SDK và version đã được pin.

### 4.2. Một số lỗi không bao giờ nên trở thành 4xx của client

- Ứng dụng cấu hình nhầm scope/collection không tồn tại.
- Username/password Couchbase bị rotation làm SDK không thể login.
- Thiếu Query Index hoặc index chưa ONLINE khi API cần query.
- Lỗi mapping document cũ sau khi deploy schema mới.
- SDK connection timeout vì cluster quá tải.
- Transaction durability impossible do bucket replica count/topology.

Đó thường là lỗi **server/dependency/configuration**. Trả `404`/`401`/`400` cho client trong các trường hợp này vừa sai ý nghĩa vừa làm bộ phận vận hành bỏ lỡ sự cố.

## 5. Thiết kế storage port không rò rỉ exception SDK

Giữ ranh giới domain bằng interface:

~~~java
package com.example.shop.order;

import java.util.Optional;

public interface OrderStore {
    Optional<Order> findById(OrderId id);
    Order create(Order draft);
    Order updateWithVersion(Order updated);
    void delete(OrderId id);
}
~~~

Application service chỉ biết `OrderStore`, không phụ thuộc trực tiếp vào `DocumentNotFoundException` hoặc `CasMismatchException`. SDK adapter đảm nhiệm chuyển lỗi kỹ thuật thành nhóm lỗi ổn định.

### 5.1. Kiểu lỗi application

~~~java
package com.example.shop.order;

public sealed abstract class OrderFailure extends RuntimeException
    permits OrderMissing, OrderAlreadyExists,
            OrderVersionConflict, OrderInvalidState {

    protected OrderFailure(String message, Throwable cause) {
        super(message, cause);
    }
}

public final class OrderMissing extends OrderFailure {
    public OrderMissing() { super("Order not found", null); }
}

public final class OrderAlreadyExists extends OrderFailure {
    public OrderAlreadyExists(Throwable cause) {
        super("Order already exists", cause);
    }
}

public final class OrderVersionConflict extends OrderFailure {
    public OrderVersionConflict(Throwable cause) {
        super("Order was changed concurrently", cause);
    }
}

public final class OrderInvalidState extends OrderFailure {
    public OrderInvalidState(String reason) {
        super(reason, null);
    }
}
~~~

Đây là ví dụ type hierarchy có chủ đích, không bắt buộc mọi dự án phải dùng sealed classes. Cần thêm các lỗi chung `DependencyUnavailable`, `UnknownWriteOutcome` và validation/domain failures khác mà không làm các service business import trực tiếp SDK types.

### 5.2. Lỗi không tồn tại là một kết quả hợp lệ khi đọc

~~~java
public Order getRequired(OrderId id) {
    return store.findById(id)
        .orElseThrow(OrderMissing::new);
}
~~~

`OrderStore.findById` trả `Optional.empty` khi key không có; **service** quyết định API GET required nên ném `OrderMissing`. Ở workflow “nếu chưa có thì tạo”, empty có thể là nhánh bình thường, không phải 404 ngay lập tức.

### 5.3. Đừng trộn lỗi domain với HTTP framework quá sớm

Sai:

~~~java
public Order confirm(OrderId id) {
    if (stock <= 0) {
        throw new ResponseStatusException(
            HttpStatus.CONFLICT, "Out of stock");
    }
}
~~~


## 6. Adapter dịch lỗi cụ thể từ Couchbase SDK

Một adapter SDK cho `create` cần **insert-only** để phát hiện duplicate key. `upsert` mặc định có thể ghi đè document cũ nên không phù hợp nếu API POST hứa “tạo mới hoặc conflict”.

### 6.1. Ghi create với Collection.insert

~~~java
package com.example.shop.order.persistence;

import com.couchbase.client.core.error.DocumentExistsException;
import com.couchbase.client.core.error.AmbiguousTimeoutException;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.InsertOptions;

public final class CouchbaseOrderWriter {
    private final Collection orders;

    public CouchbaseOrderWriter(Collection orders) {
        this.orders = orders;
    }

    public void create(String key, JsonObject body) {
        try {
            orders.insert(key, body);
        } catch (DocumentExistsException collision) {
            throw new OrderAlreadyExists(collision);
        } catch (AmbiguousTimeoutException timeout) {
            throw new UnknownWriteOutcome(
                "order-create", key, timeout);
        }
    }
}
~~~

`UnknownWriteOutcome` là lỗi application riêng của dự án (ví dụ class extends `RuntimeException`, giữ operation ID cho reconciliation nội bộ). Mẫu này cố ý **không catch tất cả CouchbaseException rồi trả duplicate**. Nếu SDK không chắc server đã commit sau timeout, adapter không được nói “tạo đơn thất bại, cứ thử lại với ID mới”.

### 6.2. Không dựa vào exists trước insert để bảo đảm unique

Sai:

~~~java
if (!orders.exists(key).exists()) {
    orders.upsert(key, body);
}
~~~

Hai requests có thể cùng thấy key vắng rồi cả hai `upsert`. Không có conditional insert, client có thể nhận hai lần “đã tạo” nhưng record cuối đã bị ghi đè.

Đúng là dùng `insert` duy nhất theo key xác định, nhận `DocumentExistsException` cho collision thực. Khi create dùng Spring Data repository, cần kiểm tra đường `save`/newness detection; không **giả định** repository `save` luôn là insert-only.

### 6.3. SDK get not-found và repository findById khác nhau

SDK:

~~~java
try {
    return orders.get(key).contentAsObject();
} catch (DocumentNotFoundException notFound) {
    return null; // Adapter có thể đổi thành Optional.empty().
}
~~~

Spring Data repository:

~~~java
Optional<OrderDocument> found =
    repository.findById(key);
~~~

Nhiều Spring Data repository APIs thể hiện missing qua `Optional.empty()`, còn SDK `Collection.get` thông thường ném `DocumentNotFoundException`. Adapter nên thống nhất **một** contract `Optional<Order>` cho use case đọc tùy chọn; đừng để controller bắt hai cơ chế riêng.

### 6.4. SDK `replace` với CAS guard

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;
import com.couchbase.client.core.error.CasMismatchException;

public void replaceWhenUnchanged(
        String key, JsonObject body, long expectedCas) {
    try {
        orders.replace(
            key, body,
            replaceOptions().cas(expectedCas));
    } catch (CasMismatchException stale) {
        throw new OrderVersionConflict(stale);
    } catch (DocumentNotFoundException missing) {
        throw new OrderMissing();
    }
}
~~~

`CasMismatchException` chứng minh expected CAS **không còn khớp**. Không tạo CAS bằng `currentCas + 1`, vì CAS là token opaque của Server. Một `DocumentNotFoundException` khi replace có thể do document bị xóa/TTL hết hạn, và business service có thể chọn `404` hay `409` tùy operation.

### 6.5. Spring Data optimistic locking

Với entity:

~~~java
@Document
@Scope("commerce")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long cas;

    @Field("status")
    private String status;

    // Constructors, getters, business methods...
}
~~~

Repository:

~~~java
interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {}
~~~

Test CAS đúng:

~~~java
repository.save(new OrderDocument(key, "DRAFT"));

OrderDocument writerA = repository.findById(key).orElseThrow();
OrderDocument writerB = repository.findById(key).orElseThrow();

writerA.changeStatus("CONFIRMED");
repository.save(writerA);

writerB.changeStatus("CANCELLED");
assertThrows(OptimisticLockingFailureException.class,
    () -> repository.save(writerB));
~~~

Mỗi writer dùng **hai snapshots độc lập, cùng CAS cũ**. Nếu writer B đọc lại sau khi A save, nó có CAS mới và có thể ghi thành công. Service dịch optimistic conflict thành `OrderVersionConflict` hoặc `ConditionalWriteFailed`, còn HTTP advice quyết định `409`/`412` theo contract.

### 6.6. Không nuốt lỗi ở repository/template

Sai:

~~~java
try {
    repository.save(order);
} catch (DataAccessException ex) {
    return order; // SAI: trả entity như thể đã persist.
}
~~~

Sau lỗi I/O, transaction, CAS hoặc converter, **không thể nói thành công** chỉ vì object Java vẫn có giá trị. Với reactive `onErrorResume(ex -> Mono.just(order))` còn nguy hiểm hơn: API có thể báo success dù mutation không hoàn tất.

## 7. Mapping lỗi service: context business quyết định kết quả

Mô hình use case:

~~~java
@Service
public class OrderApplicationService {

    private final OrderStore store;

    public OrderApplicationService(OrderStore store) {
        this.store = store;
    }

    public Order getRequired(String rawId) {
        OrderId id = OrderId.parse(rawId); // Có validation.
        return store.findById(id).orElseThrow(OrderMissing::new);
    }

    public Order create(CreateOrderCommand command) {
        command.validate();
        Order draft = Order.newDraft(command);
        return store.create(draft);
    }

    public Order confirm(OrderId id) {
        Order current = store.findById(id)
            .orElseThrow(OrderMissing::new);

        if (!current.canConfirm()) {
            throw new OrderInvalidState(
                "Order is not confirmable");
        }
        current.confirm();
        return store.updateWithVersion(current);
    }
}
~~~

`OrderId.parse`, `CreateOrderCommand` và `Order.newDraft` là domain APIs minh họa, không phải lớp có sẵn trong Spring Data. Cấu trúc có lợi ở chỗ **validation và state machine không gắn HTTP**, còn persistence adapter chỉ dịch lỗi kỹ thuật.

### 7.1. Chọn policy cho delete và confirm

| Operation | Storage condition | Business interpretation |
| --- | --- | --- |
| `GET /orders/{id}` | `findById` empty | `OrderMissing` → 404 |
| `DELETE /orders/{id}` idempotent | key absent | Có thể 204, không cần ném lỗi |
| `DELETE /orders/{id}` strict | key absent | 404 theo contract |
| `POST /orders/{id}/confirm` | Order absent | 404 |
| Confirm | Order exists, state CANCELLED | `OrderInvalidState` → 409 |
| Confirm | Stock missing | Inventory inconsistency/conflict, không tự gọi Order missing |
| Confirm | CAS conflict | Reload/409 theo policy |
| Confirm | Transaction failed do business exception | Trả business code theo cause |
| Confirm | Commit ambiguous | Tra cứu operation ID, không báo “rolled back” |

Một exception không mang đủ ngữ cảnh để chọn HTTP status nếu service chưa phân biệt request semantic.

### 7.2. Mapping lỗi vào miền không làm mất nguyên nhân nội bộ

Một lớp exception application nên giữ `cause` để log/tracing:

~~~java
public final class UnknownWriteOutcome extends RuntimeException {
    private final String operation;
    private final String resourceKey;

    public UnknownWriteOutcome(
            String operation, String resourceKey,
            Throwable cause) {
        super("Write outcome is unknown", cause);
        this.operation = operation;
        this.resourceKey = resourceKey;
    }

    public String operation() { return operation; }
    public String resourceKey() { return resourceKey; }
}
~~~

`resourceKey` dùng cho nội bộ, **không tự đưa vào ProblemDetail** nếu key chứa tenant/user IDs. Với log, ưu tiên trace/operation ID và có thể hash resource key nếu cần.

## 8. @RestControllerAdvice trả ProblemDetail không lộ hạ tầng

Ví dụ Spring Boot 3.x / Spring Framework 6.x, Java 17+:

~~~java
package com.example.shop.api;

import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderProblemAdvice {

    @ExceptionHandler(OrderMissing.class)
    ResponseEntity<ProblemDetail> notFound(
            OrderMissing ex, HttpServletRequest request) {
        return problem(HttpStatus.NOT_FOUND,
            "ORDER_NOT_FOUND", "Order not found",
            "Không tìm thấy đơn hàng.", request);
    }

    @ExceptionHandler(OrderAlreadyExists.class)
    ResponseEntity<ProblemDetail> duplicate(
            OrderAlreadyExists ex, HttpServletRequest request) {
        return problem(HttpStatus.CONFLICT,
            "ORDER_ALREADY_EXISTS", "Order already exists",
            "Mã đơn hàng đã tồn tại.", request);
    }

    @ExceptionHandler(OrderVersionConflict.class)
    ResponseEntity<ProblemDetail> versionConflict(
            OrderVersionConflict ex, HttpServletRequest request) {
        return problem(HttpStatus.CONFLICT,
            "ORDER_VERSION_CONFLICT", "Order was changed",
            "Đơn hàng đã được cập nhật. Hãy tải lại.", request);
    }

    @ExceptionHandler(OrderInvalidState.class)
    ResponseEntity<ProblemDetail> invalidState(
            OrderInvalidState ex, HttpServletRequest request) {
        return problem(HttpStatus.CONFLICT,
            "ORDER_INVALID_STATE", "Invalid order transition",
            "Đơn hàng không ở trạng thái cho phép thao tác.",
            request);
    }

    static ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String code, String title,
            String detail, HttpServletRequest request) {

        ProblemDetail p =
            ProblemDetail.forStatusAndDetail(status, detail);
        p.setTitle(title);
        p.setType(URI.create(
            "https://api.example.invalid/problems/"
                + code.toLowerCase(java.util.Locale.ROOT)
                      .replace('_', '-')));

        // Chỉ dùng requestURI nếu API không đặt secrets/token trong path.
        p.setInstance(URI.create(request.getRequestURI()));
        p.setProperty("code", code);

        // API hiện tại lấy trace ID từ tracing context khi có.
        String traceId = org.slf4j.MDC.get("traceId");
        if (traceId != null && !traceId.isBlank()) {
            p.setProperty("traceId", traceId);
        }

        return ResponseEntity.status(status)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(p);
    }
}
~~~

Đây là skeleton minh họa; nếu dùng `@ControllerAdvice` có thứ tự ưu tiên khác hoặc mở rộng `ResponseEntityExceptionHandler`, cần kiểm tra handlers mặc định (validation, JSON parse, no-handler, security) **không bị một catch-all ghi đè**. Với WebFlux, thay `HttpServletRequest` bằng `ServerWebExchange`/API tương ứng.

### 8.1. Dùng properties trong ProblemDetail có chủ đích

Spring `ProblemDetail.setProperty("code", ...)` thêm extension field. Lúc JSON serialization qua Spring MVC, các properties có thể được phát ra ở root đúng hợp đồng Problem Details. Không tự bọc:

~~~json
{"error":{"problem":{"code":"..."}}}
~~~

nếu OpenAPI đã công bố `application/problem+json` chuẩn; hai response schema khác nhau sẽ làm client parser khó tái sử dụng.

### 8.2. Validation request và error handling của Spring MVC

Các lỗi request body invalid có thể gồm:

~~~java
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.http.converter.HttpMessageNotReadableException;

@ExceptionHandler(MethodArgumentNotValidException.class)
ResponseEntity<ProblemDetail> validation(
        MethodArgumentNotValidException ex,
        HttpServletRequest request) {
    return problem(HttpStatus.BAD_REQUEST,
        "VALIDATION_FAILED", "Invalid request",
        "Dữ liệu yêu cầu không hợp lệ.", request);
}

@ExceptionHandler(HttpMessageNotReadableException.class)
ResponseEntity<ProblemDetail> invalidJson(
        HttpMessageNotReadableException ex,
        HttpServletRequest request) {
    return problem(HttpStatus.BAD_REQUEST,
        "INVALID_REQUEST", "Unreadable JSON",
        "Không thể đọc JSON theo schema của API.", request);
}
~~~

Có thể thêm `violations` dạng whitelist tên field/code, nhưng không phản chiếu raw value/mật khẩu/token từ request body. Tách **request JSON parse error (4xx)** khỏi **JSON đã lưu trong Couchbase không map được (5xx)**.

### 8.3. API authentication không giống Couchbase authentication

Spring Security có filter chain cho 401/403 API client. Một `CouchbaseException` do credentials kết nối cluster sai **không** được dịch sang `401` dành cho người gọi. Với Spring Security, các lỗi `AuthenticationException`/`AccessDeniedException` thường được xử lý tại security filter/entrypoint; không tạo catch-all ControllerAdvice khiến chúng biến thành 500 hoặc rò thông tin.

### 8.4. Không lộ exception message

Sai:

~~~java
p.setDetail(ex.getMessage());
p.setProperty("exceptionClass", ex.getClass().getName());
p.setProperty("sql", statement);
p.setProperty("bucket", bucketName);
~~~

Một message có thể chứa tên cluster/collection, query statements, document keys, token hoặc nguyên nhân hạ tầng. Trả thông điệp được soạn theo `code`; log chi tiết sanitized riêng với correlation ID.

## 9. ETag và CAS: từ optimistic locking đến HTTP preconditions

Ứng dụng muốn client tránh lost update khi chỉnh Order:

~~~text
GET /api/orders/order-123
→ 200 OK
  ETag: "v1encodedtoken"

PUT /api/orders/order-123
If-Match: "v1encodedtoken"
→ 200 OK + ETag mới
hoặc → 412 Precondition Failed
~~~

### 9.1. CAS là token nội bộ, ETag là hợp đồng HTTP

`@Version Long` trong Spring Data Couchbase giữ CAS metadata, còn `ETag` là HTTP entity validator. Có thể xây strong ETag từ CAS qua encoding an toàn/ổn định, nhưng **không trả CAS như business version tăng một đơn vị** và không cho client tự đoán version.

Khuyến nghị: adapter/hàm ETag codec chịu trách nhiệm chuyển CAS opaque thành ETag; service so request ETag với snapshot server đọc rồi ghi bằng CAS guard. Nếu application dùng projection/snapshot không phản ánh toàn entity thì cần thiết kế validator tương ứng, không mặc định CAS của một document đã bao phủ mọi tài nguyên phụ thuộc.

### 9.2. Ba kết quả của PUT có If-Match

~~~mermaid
flowchart TD
    A["PUT /orders/123"] --> B{"If-Match có?"}
    B -->|Không| C["428 Precondition Required"]
    B -->|Có| D["Đọc Order từ KV"]
    D --> E{"Order có?"}
    E -->|Không| F["404 Not Found"]
    E -->|Có| G{"ETag hiện tại khớp?"}
    G -->|Không| H["412 Precondition Failed"]
    G -->|Có| I["Validate domain + save CAS"]
    I --> J{"CAS stale khi ghi?"}
    J -->|Có| H
    J -->|Không| K["200 OK với ETag mới"]
~~~

Nếu API yêu cầu `If-Match` và thiếu header, `428` diễn đạt đúng precondition policy. Khi precondition khác, `412`. Nếu operation không sử dụng HTTP conditional request nhưng service phát hiện optimistic conflict bằng `@Version`, `409` là hợp lý.

### 9.3. Check-then-save không loại bỏ race

Sai:

~~~java
if (current.getCas().equals(expectedCas)) {
    repository.save(entityWithoutVersionGuard);
}
~~~

Hai threads có thể đều kiểm tra CAS đúng trước khi một thread save. Phải **ghi có CAS condition**, thông qua `repository.save` với `@Version` hoặc SDK `replaceOptions().cas(expectedCas)`.

### 9.4. Delete với If-Match

Tương tự, nếu API hỗ trợ conditional DELETE, stale ETag là `412`, nhưng client cần biết contract “delete absent” là `404` hay `204`. Một CAS conflict trong DB cùng lúc delete không tự động chuyển thành 500; controller/service phải biểu thị precondition failed khi xác nhận từ state.

## 10. TTL, document missing và lỗi do sai keyspace

TTL của Couchbase làm **cả document** hết hạn; `@Document(expiry=...)`, bucket/collection maxTTL và SDK expiry options ảnh hưởng đến thời điểm KV không còn thấy document.

### 10.1. TTL hết hạn không phải connection error

~~~java
Optional<OrderDocument> order = repository.findById(key);

if (order.isEmpty()) {
    throw new OrderMissing(); // API GET required → thường 404.
}
~~~

`isEmpty()` **không chứng minh** document từng tồn tại rồi mới hết hạn. Khi không có audit/tombstone đáng tin, nên trả 404 thay vì 410. Chỉ dùng `410 Gone` nếu application biết chắc tài nguyên đã bị loại bỏ vĩnh viễn và hợp đồng công khai 410.

### 10.2. Không biến sai route thành 404 hợp lệ

Nếu repository cấu hình nhầm `shop_live.commerce.orders` sang `shop_stage.commerce.orders` và ở bucket kia không có key, một `findById` có thể trả empty, tạo false 404. Vì thế cần:

- Startup checks cho cluster/bucket/scope/collection và RBAC.
- Sentinel/canary data và integration contract tests cho routing.
- Không fallback về default bucket khi config đích thiếu.
- Tách test “đúng keyspace” khỏi “document missing”.
- Không lấy bucket/cluster từ request input chưa xác thực.

### 10.3. Missing vì delete race khi đang update

~~~text
T0: PUT đọc Order + CAS C0
T1: Request khác DELETE Order
T2: PUT replace với CAS C0
T3: Server trả DocumentNotFound
~~~

PUT yêu cầu resource đang tồn tại có thể trả `404`; PUT sử dụng `If-Match` và xử lý theo HTTP precondition contract có thể trả `412`; confirm order theo business rule có thể trả `409`. **Context service** mới xác định được ý nghĩa.

## 11. SQL++: thiếu index, query lỗi và visibility lag

Couchbase KV `findById` không cần secondary index, nhưng derived query/`@Query` thường dùng SQL++ qua Query/Index Services. Một API tìm kiếm có thể thất bại trong khi GET by key vẫn thành công.

### 11.1. SQL++ failure không phải “không tìm thấy dữ liệu”

| Tình huống | HTTP policy phù hợp |
| --- | --- |
| Query hợp lệ, zero rows | `200 OK` với mảng rỗng đối với search endpoint |
| Client gửi filter không hợp lệ | `400`/`422` tùy validation contract |
| SQL++ syntax lỗi do developer | `500`, sửa code/deployment |
| Thiếu index cần thiết | `500` hoặc `503` nếu tạm thời đang build/recover |
| Query/Index Service unavailable | `503 DEPENDENCY_UNAVAILABLE` |
| Query timeout do overload/scan wait | `503 DEPENDENCY_TIMEOUT` hoặc gateway-specific `504` |
| Query rỗng vì index lag | Không nên giả định resource không tồn tại |
| Permission denied bởi Couchbase RBAC | Server-side security/config issue, không phải 403 client tự động |

Một lỗi “No index available” không được che bằng `Collections.emptyList()` hay 404. Tên/cú pháp index là chi tiết nội bộ, không xuất vào public ProblemDetail.

### 11.2. Eventual index consistency gây “không thấy vừa tạo”

~~~text
T0: KV insert Order thành công
T1: KV get(OrderID) → có Order
T2: SQL++ NOT_BOUNDED → có thể chưa thấy Order
T3: Index Service bắt kịp → SQL++ trả Order
~~~

Nếu API hứa read-your-own-writes sau create:

- Dùng `REQUEST_PLUS` trong query cần đảm bảo scan consistency.
- Hoặc `consistentWith(MutationState)` nếu SDK có mutation token phù hợp.
- Hoặc dùng KV by key khi workflow cho phép.

Không đổi lỗi dữ liệu chưa được index thành 404 vĩnh viễn. `REQUEST_PLUS` **không tự tạo index** và **không thay durability**.

### 11.3. Không đưa SQL++/index details vào response

Một Query error có thể kèm bucket/scope/collection names, statement, query parameters và error context. Log sanitized, gắn trace ID, trả `QUERY_UNAVAILABLE`/`DEPENDENCY_TIMEOUT`. Không trả `ex.getMessage()` nguyên văn.

## 12. Durability, timeout và kết quả ghi chưa xác định

Couchbase Java SDK có các loại timeout khác nhau. Một lần timeout **không phải bằng chứng** Server chưa thực hiện mutation.

~~~mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant App as API
    participant DB as Couchbase
    Client->>App: POST Order, Idempotency-Key=req-123
    App->>DB: INSERT durable Order
    DB->>DB: Mutation có thể đã commit
    DB--xApp: Ack mất / timeout
    App-->>Client: Outcome unknown + operation ID
    Client->>App: GET /operations/req-123
    App->>DB: Reconcile marker/state
    DB-->>App: Applied, pending hoặc not applied
~~~

### 12.1. Bốn outcome khác nhau

| Kết quả | Điều đã biết | Ứng dụng nên làm |
| --- | --- | --- |
| Success acknowledged | Mutation được chấp nhận theo acknowledgement requirements | Trả success/body/ETag |
| `UnambiguousTimeoutException` hoặc loại lỗi SDK xác định chưa apply | Không có confirmed mutation cho operation đó | Retry theo budget + business policy khi an toàn |
| `AmbiguousTimeoutException`/durability ambiguous | **Chưa biết đã apply hay chưa** | Reconcile bằng stable request ID |
| `DurabilityImpossibleException` | Không đạt quorum/topology cần thiết | 5xx, sửa resource/replica config, không retry mù |

`503` hợp lý cho dependency tạm không khả dụng; `504` có nghĩa riêng ở gateway/proxy. Quan trọng hơn status là public code phân biệt **unavailable** với **write outcome unknown** và không nói sai rằng mutation đã rollback.

### 12.2. Khi nào có thể trả 202 Accepted?

`202 Accepted` phù hợp khi API **đã nhận việc để xử lý không đồng bộ** và có status endpoint dựa trên operation record đáng tin cậy.

~~~http
HTTP/1.1 202 Accepted
Location: /api/operations/req-123
Retry-After: 2
Content-Type: application/json

{"requestId":"req-123","state":"PENDING"}
~~~

Nếu SDK trả ambiguous mà hệ thống **không có durable operation record/status lookup**, không nên tự trả 202 như thể đã nhận và sẽ xử lý. Có thể trả `503 WRITE_OUTCOME_UNKNOWN` và yêu cầu tra cứu/retry theo **cùng idempotency key** sau reconciliation policy; không mời client tạo ID mới. Thiết kế API phải mô tả rõ khi nào 202/503 được trả.

### 12.3. Retry-After phải đúng policy

`Retry-After` hữu ích khi service biết thời gian rate-limit/recovery, nhưng không có nghĩa “POST lại với ID mới”. Với unknown outcome, hướng dẫn client giữ `Idempotency-Key`, tra cứu trạng thái operation, hoặc retry bằng stable command ID nếu protocol cho phép.

### 12.4. Durable write và topology

`DurabilityLevel.MAJORITY` phụ thuộc replicas; bucket một Data node với một replica thường không đạt quorum và có thể báo `DurabilityImpossibleException`. Đây là hạ tầng, không phải validation của người mua. Bucket zero replicas trên một node có thể đạt majority nhưng **không chứng minh failover nhiều node**.

### 12.5. Stable operation identity là điều kiện tiên quyết

~~~text
POST /orders
Idempotency-Key: req-123
Body: {customerId, items, ...}
~~~

Cùng key + payload canonical tương đương phải trả cùng business outcome, không tạo Order mới. Cùng key + payload khác phải trả `409 REQUEST_PAYLOAD_MISMATCH`. Key random mới cho mỗi HTTP retry **không phải idempotency**.

## 13. TransactionFailed khác CommitAmbiguous

Couchbase Transactions có thể retry các attempts khi gặp conflict transient; ứng dụng phải phân biệt exception đã biết **chưa commit** với exception **chưa rõ đã commit hay chưa**.

~~~java
import com.couchbase.client.java.transactions.error.TransactionFailedException;
import com.couchbase.client.java.transactions.error.TransactionExpiredException;
import com.couchbase.client.java.transactions.error.TransactionCommitAmbiguousException;
~~~

| Nhóm lỗi | Điều biết được | Hành động |
| --- | --- | --- |
| `TransactionFailedException` không phải ambiguous | Không đạt commit point | Xem cause và phân loại domain/infrastructure |
| `TransactionExpiredException` | Hết transaction timeout trước commit | Phân loại trước khi retry operation |
| `TransactionCommitAmbiguousException` | Có thể đã đạt commit point | Reconcile marker, không tự chạy lại command |
| Business exception (insufficient stock) trong lambda | Domain reject | 409/422 theo API |
| Conflict transient | SDK có thể retry attempt | Tránh double-retry ở HTTP |
| Durability/config failure | Hạ tầng không đáp ứng | 5xx, sửa deployment |

### 13.1. Catch ambiguous trước failure

~~~java
try {
    var result = cluster.transactions().run(ctx -> {
        // Stage Order, Stock và operation marker bằng ctx.
    });
    return handleCommitted(result);
} catch (TransactionCommitAmbiguousException ambiguous) {
    throw new UnknownWriteOutcome(
        "confirm-order", requestId, ambiguous);
} catch (TransactionFailedException failed) {
    throw translateFailedTransaction(failed);
}
~~~

`translateFailedTransaction` là hàm application. Phân loại dựa trên exception type/cause chain, không dùng `failed.getMessage().contains("stock")`. Khi cause là business exception, trả public domain code; khi là auth/quorum/timeout, trả server-side dependency code.

### 13.2. Lambda có thể thực thi nhiều attempts

~~~java
cluster.transactions().run(ctx -> {
    paymentGateway.charge(...); // SAI: external side effect không rollback.
    kafkaProducer.send(...);    // SAI: có thể duplicate khi retry.
});
~~~

Dùng transactional API của `ctx` cho DB operations; nếu cần phát event, stage outbox record cùng transaction rồi relay idempotent sau commit. `@Transactional` Spring Data cũng phải có đúng manager/proxy; một direct SDK call không tự tham gia transaction chỉ vì cùng Java method.

### 13.3. Commit thành công nhưng unstaging chưa xong

`TransactionResult.unstagingComplete() == false` có thể xảy ra **sau khi commit point đã đạt**. Không coi đó là rollback/503. Nếu đọc committed state bằng non-transactional KV ngay lập tức, có thể cần polling đến khi unstaging hoàn tất theo deadline.

## 14. Retry: ai retry, retry cái gì và trong bao lâu?

~~~text
HTTP client
  -> API gateway retry
    -> application retry
      -> SDK retry
        -> Couchbase Server
~~~

Nếu mọi tầng tự retry nhiều lần mà không có end-to-end deadline, cluster có thể bị quá tải và business command bị áp dụng lặp.

| Lỗi | Có thể retry? | Điều kiện |
| --- | --- | --- |
| GET transient timeout | Có | Backoff+jitter + deadline |
| Duplicate key | Không | 409/idempotency policy |
| CAS conflict | Có thể | **Reload** state, kiểm invariant, bounded |
| Invalid request / domain reject | Không | Client phải thay request/state |
| Missing resource | Thường không | Trừ workflow eventual/poll được thiết kế |
| Query index missing | Không | Sửa schema/index/permissions |
| Index lag | Query consistency đúng hơn | Không sửa bằng sleep cố định |
| DurabilityImpossible | Không mù | Sửa replicas/topology |
| Ambiguous mutation | Không tạo command mới | Reconcile bằng stable ID |
| Transaction transient conflict | SDK có retry | Đừng tăng retry vòng ngoài vô hạn |
| Rate limited API | Sau thời hạn | 429 và Retry-After theo policy |

### 14.1. Retry CAS đúng bằng reload + recompute

~~~java
public Order reserveWithCasRetry(OrderId id, String commandId) {
    int maxAttempts = 4;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        Order current = store.findById(id)
            .orElseThrow(OrderMissing::new);

        current.reserve(commandId); // Kiểm invariant trên state mới.

        try {
            return store.updateWithVersion(current);
        } catch (OrderVersionConflict conflict) {
            if (attempt == maxAttempts) throw conflict;
            // Vòng sau đọc lại, không save entity stale.
        }
    }
    throw new IllegalStateException("Unreachable");
}
~~~

Đây là skeleton cần bổ sung idempotency cho `commandId`, backoff/jitter/deadline trong production. **Không** retry cùng một object stale, không retry mọi `RuntimeException` và không làm `onErrorResume` trả success giả.

### 14.2. 429 của API khác overload SDK

`429 Too Many Requests` báo API admission/rate limit với client. Một Couchbase SDK queue full/server overload **không tự có nghĩa** client vượt quota public; theo contract có thể là `503` và một code khác. Đừng “đổ lỗi” cho client khi nguyên nhân ở dependency.

## 15. Reactive error signals: không biến lỗi thành Mono.empty

Spring Data Couchbase reactive trả `Mono`/`Flux`; với truy vấn theo ID không tồn tại, một `Mono.empty()` có thể là kết quả hợp lệ. Nhưng một exception về timeout, converter hoặc CAS không được nuốt rồi thay bằng empty.

### 15.1. Ánh xạ missing và optimistic locking bằng Reactor

~~~java
import org.springframework.dao.OptimisticLockingFailureException;
import reactor.core.publisher.Mono;

public Mono<OrderDocument> requiredReactive(String key) {
    return reactiveRepository.findById(key)
        .switchIfEmpty(Mono.error(new OrderMissing()));
}

public Mono<OrderDocument> saveReactive(OrderDocument entity) {
    return reactiveRepository.save(entity)
        .onErrorMap(OptimisticLockingFailureException.class,
            OrderVersionConflict::new);
}
~~~

`switchIfEmpty` chỉ xử lý publisher hoàn thành **không phát phần tử**; nó không phải nơi catch lỗi hạ tầng. `onErrorMap` đổi một error signal sang type application, giữ cause. Nếu cả phương thức reactive return publisher nhưng controller không subscribe qua WebFlux framework/StepVerifier, không thể chứng minh I/O đã diễn ra.

### 15.2. Thận trọng với onErrorResume

Sai:

~~~java
return reactiveRepository.findById(key)
    .onErrorResume(error -> Mono.empty());
// Timeout hoặc mapping lỗi bị đổi thành “không tồn tại”.
~~~

Đúng hơn:

~~~java
return reactiveRepository.findById(key)
    .onErrorResume(
        DocumentNotFoundException.class,
        error -> Mono.empty());
// Chỉ khi adapter dùng raw SDK và xác định đây là not-found.
~~~

Với `ReactiveCouchbaseRepository.findById`, missing thông thường đã thể hiện bằng `Mono.empty()`; không cần catch `DocumentNotFoundException` nếu API không ném. **Không xử lý mọi DataAccessException như missing**.

### 15.3. Reactive timeout không chứng minh write chưa xảy ra

~~~java
Mono<OrderDocument> submitted =
    reactiveRepository.save(order)
        .timeout(Duration.ofSeconds(3));
~~~

`timeout` trong Reactor có thể cancel subscription nhưng Server vẫn đã nhận mutation. Khi deadline ở client hết, kết quả write có thể cần reconcile, nhất là với SDK operation đã gửi. Không dùng:

~~~java
.onErrorResume(TimeoutException.class,
    timeout -> reactiveRepository.save(newOrderWithNewId()));
~~~

Một API reactive có thể dùng cùng idempotency protocol và `WRITE_OUTCOME_UNKNOWN` như blocking API.

### 15.4. ControllerAdvice với WebFlux

`@RestControllerAdvice` và `ProblemDetail` vẫn dùng được trong Spring WebFlux, nhưng các dependency như `jakarta.servlet.http.HttpServletRequest` không thuộc reactive stack. Dùng `ServerWebExchange` hoặc `ServerHttpRequest` theo handler signature. Không copy nguyên MVC skeleton mục 8 sang WebFlux mà giữ Servlet request object.

### 15.5. Test reactive error signal

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(requiredReactive("missing-id"))
    .expectError(OrderMissing.class)
    .verify();

StepVerifier.create(saveReactive(staleOrder))
    .expectError(OrderVersionConflict.class)
    .verify();
~~~

Với test optimistic conflict, `staleOrder` phải xuất phát từ hai snapshots độc lập đã đọc trước một write thành công; không chỉ tạo object với CAS giả rồi mong mapper tự ném conflict. Cần kiểm tra server state sau test và subscribe cleanup publisher.

## 16. Lớp phân loại lỗi hạ tầng và handler HTTP

Tầng service nên có nhóm lỗi chung cho dependency, thay vì để controller xử lý `com.couchbase.client.core.error.*`.

### 16.1. Các application failures tối thiểu

~~~java
public final class DependencyUnavailable
        extends RuntimeException {
    public DependencyUnavailable(Throwable cause) {
        super("Data dependency unavailable", cause);
    }
}

public final class DependencyTimeout
        extends RuntimeException {
    public DependencyTimeout(Throwable cause) {
        super("Data dependency timed out", cause);
    }
}

public final class InternalDataError
        extends RuntimeException {
    public InternalDataError(Throwable cause) {
        super("Persisted data could not be read", cause);
    }
}
~~~

`UnknownWriteOutcome` đã được định nghĩa ở mục 7.2. Adapter phân loại dựa trên **error type, operation, acknowledged state và SDK error context**, không chỉ cause message.

### 16.2. Mapping sang ProblemDetail cố định

~~~java
// Thêm vào OrderProblemAdvice của mục 8.

@ExceptionHandler(DependencyUnavailable.class)
ResponseEntity<ProblemDetail> unavailable(
        DependencyUnavailable ex, HttpServletRequest request) {
    return problem(HttpStatus.SERVICE_UNAVAILABLE,
        "DEPENDENCY_UNAVAILABLE", "Data service unavailable",
        "Hệ thống tạm thời chưa xử lý được yêu cầu.",
        request);
}

@ExceptionHandler(DependencyTimeout.class)
ResponseEntity<ProblemDetail> timeout(
        DependencyTimeout ex, HttpServletRequest request) {
    return problem(HttpStatus.SERVICE_UNAVAILABLE,
        "DEPENDENCY_TIMEOUT", "Data operation timed out",
        "Yêu cầu không hoàn tất trong giới hạn thời gian.",
        request);
}

@ExceptionHandler(UnknownWriteOutcome.class)
ResponseEntity<ProblemDetail> unknownOutcome(
        UnknownWriteOutcome ex, HttpServletRequest request) {
    return problem(HttpStatus.SERVICE_UNAVAILABLE,
        "WRITE_OUTCOME_UNKNOWN", "Write status is unknown",
        "Chưa xác định được kết quả. Hãy tra cứu trạng thái " +
        "bằng mã yêu cầu trước khi thử lại.",
        request);
}

@ExceptionHandler(InternalDataError.class)
ResponseEntity<ProblemDetail> internalData(
        InternalDataError ex, HttpServletRequest request) {
    return problem(HttpStatus.INTERNAL_SERVER_ERROR,
        "INTERNAL_DATA_ERROR", "Stored data error",
        "Hệ thống chưa thể đọc dữ liệu này.",
        request);
}
~~~

`WRITE_OUTCOME_UNKNOWN` với 503 ở đây là **một lựa chọn hợp đồng**, không phải Couchbase SDK tự bắt buộc status 503. Nếu API có durable operation record và async status tracking thì thiết kế 202/Location riêng, thay vì map mọi ambiguous thành 202.

### 16.3. Catch-all phải bảo vệ built-in HTTP errors

Nếu có `@ExceptionHandler(Exception.class)`, nó không được vô tình chuyển mọi lỗi parse/validation/security thành 500. Prefer các typed handlers + Spring defaults, hoặc kế thừa `ResponseEntityExceptionHandler` với override đã kiểm chứng. Khi thật sự bắt unexpected exceptions, log sanitized (trace correlation), trả `500 INTERNAL_ERROR`, không xuất exception class/stack/cause chain.

### 16.4. Một policy response status không thay thế monitoring

Ngay cả khi client nhận mã 503, service cần log lỗi nguồn thuộc `kv`, `query`, `index`, `transaction`, `auth` hoặc `converter`; phân loại theo logical store/cluster alias để vận hành biết phải xử lý ở đâu.

## 17. Kiểm thử API mapping với MockMvc và Testcontainers

Một bộ test tốt có nhiều tầng:

| Lớp test | Dùng gì? | Chứng minh |
| --- | --- | --- |
| Unit service | JUnit/Mockito | Lỗi domain theo business rule |
| Controller contract | `@WebMvcTest` + `MockMvc` | Status, content type, `code`/`detail` |
| Storage integration | Couchbase Testcontainers | SDK/Repository thực sự ném lỗi đúng |
| API integration | Application + Couchbase test | End-to-end status và database state |
| Fault injection | Toxiproxy/network harness/adapter stub | Timeout, ambiguous, recovery/reconciliation |
| Load/chaos | Multi-node topology | Durability, failover, retry storm, SLO |

**Một Mockito test không chứng minh CAS, query index hay transaction behavior thật.** Nó chỉ chứng minh mapping của một exception được giả lập.

### 17.1. @WebMvcTest kiểm tra 404 và problem body

Giả sử có controller:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderApplicationService service;

    OrderController(OrderApplicationService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    OrderResponse get(@PathVariable String id) {
        return OrderResponse.from(service.getRequired(id));
    }
}
~~~

`OrderResponse.from` là converter API DTO minh họa. Test MVC:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(OrderProblemAdvice.class)
class OrderControllerErrorContractTest {

    @Autowired MockMvc mvc;

    @MockitoBean OrderApplicationService service;

    @Test
    void missingOrderBecomes404Problem() throws Exception {
        when(service.getRequired("not-found"))
            .thenThrow(new OrderMissing());

        mvc.perform(get("/api/orders/not-found"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                "application/problem+json"))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code")
                .value("ORDER_NOT_FOUND"))
            .andExpect(jsonPath("$.title")
                .value("Order not found"));
    }
}
~~~

`@MockitoBean` được Spring Framework 6.2/Spring Boot 3.4+ hỗ trợ; nếu dự án dùng Boot 3.0–3.3, dùng `@MockBean` phù hợp phiên bản đó. Nếu Spring Security đang bật, test cần `@WithMockUser`/security test setup thích hợp; đừng disable auth hoàn toàn rồi gọi đó là security test.

### 17.2. Test CAS cần hai snapshots từ DB thật

~~~java
@Test
void staleSaveIsReportedAsConflict() throws Exception {
    // 1. Seed Order(key) qua repository thật.
    // 2. Read snapshotA và snapshotB trước bất kỳ save nào.
    // 3. Save A thành công, read back state.
    // 4. PUT từ B/If-Match stale → expected 412.
    // 5. Verify DB giữ A, không bị B ghi đè.
}
~~~

Nếu API không yêu cầu `If-Match`, expected có thể là `409`. Đây là **end-to-end contract test**: kiểm tra cả HTTP status, public error code, và state cuối. Không dùng `assertThrows(Exception.class)` rồi suy ra API conflict.

### 17.3. Test duplicate create thực

~~~java
@Test
void duplicateCreateCannotOverwriteExistingOrder() {
    String key = "it::" + UUID.randomUUID() + "::order::dupe";

    try {
        collection.insert(key,
            JsonObject.create().put("status", "DRAFT"));

        assertThrows(DocumentExistsException.class,
            () -> collection.insert(key,
                JsonObject.create().put("status", "CONFIRMED")));

        assertEquals("DRAFT",
            collection.get(key).contentAsObject()
                .getString("status"));
    } finally {
        if (collection.exists(key).exists()) collection.remove(key);
    }
}
~~~

Sau khi đã chứng minh SDK duplicate behavior, test API POST hai lần với cùng unique ID để xác nhận **409 ORDER_ALREADY_EXISTS** hoặc idempotent replay outcome theo contract. Không dùng `upsert` cho test duplicate vì nó che collision.

### 17.4. Test dữ liệu sai mapping không phải 400

Seed raw SDK JSON legacy có kiểu không tương thích hoặc type metadata sai, rồi đọc bằng Spring Data. Xác minh adapter ném `InternalDataError`/error code server-side, **không** trả 400 cho client chỉ vì JSON được lưu trong DB sai. Nếu converter đang có policy chấp nhận MISSING/NULL/legacy field, test phải phản ánh đúng policy, không mặc định dữ liệu cũ là lỗi.

### 17.5. Test SQL++ query index và consistency

- Với `findById`, KV không cần secondary index.
- Với derived query/`@Query`, tạo đúng Query/Index Services và index rồi chờ ONLINE.
- Test missing index trên môi trường riêng để thấy API trả `QUERY_UNAVAILABLE`, không trả danh sách rỗng giả.
- Sau create, dùng `REQUEST_PLUS` hoặc strategy read-after-write phù hợp để không kết luận do index lag.
- Với `NOT_BOUNDED`, không assert query đầu tiên **bắt buộc thiếu** dữ liệu; index có thể bắt kịp nhanh.

### 17.6. Test unknown outcome phải có fault-injection policy

Muốn gây `AmbiguousTimeoutException` đúng thời điểm mutation đã đi tới server không đơn giản trên CI bình thường. Có thể:

1. Unit test adapter bằng stub ném đúng exception sau khi gọi mutation.
2. Test API response `WRITE_OUTCOME_UNKNOWN` và hướng dẫn status/retry.
3. Test idempotency end-to-end với replay cùng request ID.
4. Dùng fault-injection suite riêng mô phỏng mất response, quan sát operation marker và reconciliation.

Không kill Couchbase container rồi assert “request chắc chắn không tạo Order”; ngắt mạng sau gửi mutation **có thể để lại outcome ambiguous**.

### 17.7. Test ma trận lỗi đầy đủ

| Input/setup | DB behavior | HTTP expected | State cần verify |
| --- | --- | --- | --- |
| GET ID không có | `Optional.empty` | 404 | Không tạo document |
| POST duplicate ID | `DocumentExists` | 409 | Body cũ còn |
| PUT stale CAS không If-Match | `OptimisticLockingFailure` | 409 | Winner còn |
| PUT If-Match sai | CAS/precondition | 412 | Không overwrite |
| PUT bắt buộc If-Match nhưng thiếu | Không gửi write | 428 | DB không đổi |
| POST body invalid | Controller validation | 400/422 | Không ghi |
| Stock không đủ | Business error | 409/422 | Không âm |
| SDK credential sai | Auth failure | 5xx | Không lộ secret |
| Named collection thiếu | Resource failure | 5xx | Không giả 404 |
| SQL++ index thiếu | Query error | 5xx | Không trả empty giả |
| Query hợp lệ zero rows | Success | 200 [] | Không thay DB |
| Query REQUEST_PLUS sau write | Success/index catches up | 200 đúng row | Index visibility |
| Expired Order GET | Missing sau TTL | 404 hoặc contract riêng | KV không còn |
| Durable write ambiguous | Unknown outcome | 503/lookup protocol | Reconcile |
| Transaction business rollback | Failed before commit | Domain code | Không partial commit |
| Transaction commit ambiguous | Unknown | Unknown code/protocol | Không báo rollback |
| Rate limited client | API rejection | 429 | Không gọi DB |
| Duplicate idempotency key/payload sai | Conflict | 409 | Không apply lần hai |
| Reactive timeout | Publisher error | Theo taxonomy | Không trả success giả |

### 17.8. Cleanup và isolation

Dùng keys dạng `it::<runId>::order::<logicalId>`, không dọn toàn collection bằng `deleteAll` trong shared cluster. Dọn sau khi worker threads/publishers kết thúc; không xóa document đang phục vụ transaction unresolved. Không có Docker thì báo integration chưa chạy, **không** coi test bị skip là chứng minh CRUD/error mapping đúng.

## 18. Logging, tracing, an toàn dữ liệu và hoạt động production

Một API trả ProblemDetail chuẩn cho client nhưng không có logs/metrics đủ phân loại vẫn khó vận hành. Với Couchbase, log phải giữ **ngữ nghĩa operation** và **nguồn lỗi** mà không tiết lộ dữ liệu nhạy cảm.

### 18.1. Cấu trúc log gợi ý

~~~json
{
  "trace_id": "01JTEST9H4V",
  "request_id": "req-123",
  "api_operation": "confirm_order",
  "storage_operation": "transaction.commit",
  "logical_store": "primary-orders",
  "category": "WRITE_OUTCOME_UNKNOWN",
  "exception_type": "TransactionCommitAmbiguousException",
  "http_status": 503,
  "retry_action": "RECONCILE",
  "duration_ms": 812
}
~~~

Dùng `logical_store` alias như `primary-orders` thay raw connection string; tránh đưa full document IDs có PII, SQL++ query parameter values, tenant secrets hoặc password vào logs. `exception_type` ở **log nội bộ** có thể hữu ích, nhưng **không cần** xuất public ProblemDetail.

### 18.2. Metrics theo failure taxonomy

| Metric gợi ý | Labels nên có | Mục tiêu |
| --- | --- | --- |
| `api_problem_total` | `code`, `status`, endpoint template | Tần suất lỗi công khai |
| `couchbase_request_errors_total` | logical store, op, error category | Lỗi theo adapter |
| `couchbase_cas_conflicts_total` | operation | Contention/optimistic lock |
| `couchbase_ambiguous_mutations_total` | operation | Số outcome cần reconcile |
| `couchbase_transaction_ambiguous_total` | capability | Xác định nguy cơ retry trùng |
| `couchbase_transaction_rollback_total` | business/infra category | Failed trước commit |
| `couchbase_query_index_errors_total` | query type | Thiếu index, build lỗi |
| `couchbase_query_timeouts_total` | query type | SLO/Index Service backlog |
| `idempotency_replay_total` | endpoint, outcome | Replay bảo vệ duplicate effects |
| `api_dependency_latency_seconds` | logical store, operation | p50/p95/p99 |
| `api_retry_attempts_total` | layer, reason | Detect retry amplification |
| `api_rate_limited_total` | endpoint | API admission behavior |

Đây là **metrics do ứng dụng có thể định nghĩa**, không phải danh sách metric mặc định của Couchbase/Spring. Không gắn raw order ID, customer ID hoặc requestId làm metric labels vì cardinality và privacy.

### 18.3. SLO và alert phân biệt lỗi client/server

- 4xx validation thường không phải dependency outage; đo riêng và xem trải nghiệm người dùng.
- 409 CAS conflict tăng cao có thể là hotspot/contended document; cần phân tích retry và business rejection.
- 503 dependency timeout tăng → đo Index/KV latency, service health, connection pool.
- `WRITE_OUTCOME_UNKNOWN` tăng → ưu tiên reconciliation queue và kiểm tra response loss/quorum.
- Lỗi `INTERNAL_DATA_ERROR` tăng sau deploy → schema compatibility/migration hoặc converter regression.
- 404 đột biến theo một bucket/scope → có thể là routing misconfiguration chứ không phải toàn bộ khách hàng xóa đơn hàng.

### 18.4. Phân biệt operational rollback với business reject

Một operation bị transaction rollback do `InsufficientInventory` là **business rejection đúng thiết kế**; không alert như cluster down. Một transaction thất bại do `DurabilityImpossibleException` là configuration/outage. Cả hai có thể đi qua `TransactionFailedException` nhưng phải mang category khác nhau sau classification.

### 18.5. Trả retry advice nhất quán

Nếu public ProblemDetail có `retryable`:

| Public code | retryable | Hướng dẫn |
| --- | :---: | --- |
| `VALIDATION_FAILED` | false | Sửa payload |
| `ORDER_NOT_FOUND` | false | Kiểm tra ID hoặc resource state |
| `ORDER_VERSION_CONFLICT` | Theo workflow | Reload và áp lại business intent |
| `ORDER_PRECONDITION_FAILED` | false cho cùng ETag | GET ETag mới |
| `DEPENDENCY_UNAVAILABLE` | Có thể | Retry with jitter/backoff nếu operation safe |
| `WRITE_OUTCOME_UNKNOWN` | **Không retry mù** | Tra cứu operation theo stable ID |
| `REQUEST_PAYLOAD_MISMATCH` | false | Không reuse idempotency key với payload khác |
| `RATE_LIMITED` | true theo policy | Chờ Retry-After |

Đừng dùng một boolean `retryable=true` cho mọi 503 mà bỏ qua phân biệt idempotent GET với non-idempotent POST. Có thể dùng `action` như `RELOAD`, `CHECK_OPERATION`, `CONTACT_SUPPORT` thay boolean khi protocol cần diễn đạt rõ.

## 19. Case study: API xác nhận đơn hàng với tồn kho và outbox

### 19.1. Bối cảnh

Hệ thống có ba collections trên cùng Couchbase cluster:

~~~text
shop_live.commerce.orders
shop_live.warehouse.stocks
shop_live.integration.outbox
~~~

Request:

~~~http
POST /api/orders/order-123/confirm
Idempotency-Key: confirm-req-456
Content-Type: application/json

{"confirmedBy":"customer-100"}
~~~

Yêu cầu: xác nhận Order, trừ tồn kho, tạo outbox event **cùng transaction**, không trừ hàng/emit event hai lần khi client retry.

### 19.2. Kết quả thành công

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "new-etag"

{
  "id": "order-123",
  "status": "CONFIRMED",
  "requestId": "confirm-req-456"
}
~~~

Khác endpoint, dự án có thể chọn 204 hoặc 202 theo synchronous/async workflow. Nhưng phải công bố rõ **confirmed commit** khác **accepted for processing**. Nếu SDK transaction return success nhưng unstaging chưa hoàn tất, không tự giả failed; response status theo commit contract.

### 19.3. Bảy tình huống lỗi cần khác nhau

| Case | Root cause | API response | Hành vi client |
| --- | --- | --- | --- |
| 1 | Body thiếu/invalid | 400 VALIDATION_FAILED | Sửa body |
| 2 | Order key không tồn tại | 404 ORDER_NOT_FOUND | Kiểm tra Order ID |
| 3 | Order CANCELLED | 409 ORDER_INVALID_STATE | Không retry cùng intent |
| 4 | Không đủ stock | 409 INVENTORY_INSUFFICIENT | Điều chỉnh cart/số lượng |
| 5 | Hai requests CAS conflict | 409 ORDER_VERSION_CONFLICT hoặc retry nội bộ bounded | Reload/resolve |
| 6 | Transaction failed vì SDK infrastructure | 503 DEPENDENCY_UNAVAILABLE | Retry theo safe policy |
| 7 | Transaction commit ambiguous | WRITE_OUTCOME_UNKNOWN/status endpoint | Reconcile, không tạo request mới |

Một API có thể cho client gửi thêm conditional `If-Match`; khi đó stale ETag phải được phân biệt bằng `412`. Không ép cùng operation trả 409 và 412 ngẫu nhiên.

### 19.4. Transactional command và idempotency marker

~~~java
// Skeleton: chuẩn bị operation ID trước lambda.
String requestId = command.idempotencyKey();
String outboxKey = "outbox::" + requestId;
String operationKey = "operation::" + requestId;

var result = cluster.transactions().run(ctx -> {
    // 1. Thử tạo operation marker dùng requestId ổn định.
    // 2. ctx.get Order/Stock, kiểm state và invariant.
    // 3. ctx.replace Order, ctx.replace Stock.
    // 4. ctx.insert OutboxEvent có stable eventId.
    // 5. Commit atomic trong cùng cluster.
});
~~~

Đây là một protocol skeleton, không phải implementation đầy đủ cho duplicate marker races. Cần phân biệt duplicate operation key **cùng payload** với **khác payload**, đọc lại committed operation state sau ambiguous, và xử lý request in-flight. Không gửi Kafka trong transaction lambda (lambda có thể retry).

### 19.5. Sơ đồ API quyết định kết quả

~~~mermaid
flowchart TD
    A["POST confirm + Idempotency-Key"] --> B{"Input/auth valid?"}
    B -->|No| C["400 / 401 / 403"]
    B -->|Yes| D["Lookup operation marker"]
    D --> E{"Already committed?"}
    E -->|Yes, same payload| F["Return prior result"]
    E -->|Yes, different payload| G["409 Payload mismatch"]
    E -->|No| H["Transaction Order + Stock + Outbox"]
    H --> I{"Outcome?"}
    I -->|Committed| J["200 Confirmed"]
    I -->|Business reject| K["404 / 409 / 422"]
    I -->|Failed before commit| L["503 / domain-specific"]
    I -->|Commit ambiguous| M["Status lookup / reconcile"]
~~~

### 19.6. Test assertions phải kiểm cả data state

- **Success:** Order CONFIRMED, stock trừ đúng một lần, một outbox event có request ID.
- **Business rollback:** cả ba documents vẫn ở state tương ứng trước operation.
- **CAS conflict:** không lost update; client nhận conflict hoặc service retry an toàn rồi success.
- **Replay cùng key:** không thêm stock decrement/outbox event mới.
- **Replay khác payload:** 409 và không có mutation.
- **Ambiguous:** public API không báo chắc chắn rollback; có operation lookup/repair path.
- **Index lag:** query tìm Order theo status phải có consistency phù hợp; không biến pending index update thành 404.
- **TTL:** không gắn expiry ngắn vô tình làm mất authoritative Order; operation marker retention đúng cửa sổ replay contract.

### 19.7. Khi hạ tầng hoàn toàn down

API có thể không đọc được marker lúc dependency unavailable. Không được đoán “request chưa xử lý” chỉ vì không đọc được; tùy thời điểm, một request trước đó có thể đã commit. Response sanitized 503, giữ original request ID và cho phép client tra sau khi khôi phục.

## 20. Bài thực hành và câu hỏi tự kiểm tra

### 20.1. Yêu cầu thực hành

Xây dựng API `POST /api/carts/{id}/checkout` dựa trên Spring Data Couchbase. Giỏ hàng có `@Version Long cas`, tồn kho nằm collection khác, và API nhận `Idempotency-Key`.

1. Định nghĩa error codes tối thiểu: `CART_NOT_FOUND`, `CART_VERSION_CONFLICT`, `INVENTORY_INSUFFICIENT`, `WRITE_OUTCOME_UNKNOWN`, `DEPENDENCY_UNAVAILABLE`.
2. Chọn `409` hay `412` dựa trên có hay không `If-Match`.
3. Tạo `CartStore` port không import SDK exceptions.
4. Viết adapter repository/SDK bảo đảm create insert-only và update CAS-guarded.
5. Viết `@RestControllerAdvice` dùng `ProblemDetail`.
6. Định nghĩa transaction Order/Stock/Outbox cùng cluster và idempotency marker.
7. Viết `MockMvc` tests cho 400/404/409/412/428/503 và structure ProblemDetail.
8. Viết Testcontainers CAS/duplicate/rollback thật; kiểm state sau lỗi.
9. Viết test SQL++ index failure/REQUEST_PLUS để không báo 404 sai.
10. Thiết kế adapter test mô phỏng ambiguous outcome mà không tạo double checkout.
11. Thêm `traceId`, metrics/logs phân loại lỗi nhưng không log PII/secrets.
12. Viết runbook phân biệt Index Service down với duplicate request.

### 20.2. Câu hỏi tự kiểm tra

1. **Vì sao không dùng `assertThrows(Exception.class)` cho CAS test?** Nó có thể PASS vì cluster down.
2. **SDK `DocumentNotFoundException` có luôn là 404?** Không, service context quyết định.
3. **Repository `findById` missing thường biểu diễn thế nào?** `Optional.empty()`.
4. **`DocumentExistsException` sau `insert` thường map gì?** 409 duplicate, trừ idempotency replay contract.
5. **`repository.save` có mặc định là insert-only không?** Không nên giả định.
6. **CAS stale không có If-Match thường là?** 409.
7. **If-Match không khớp theo HTTP semantics thường là?** 412.
8. **API bắt buộc If-Match nhưng thiếu?** 428.
9. **Couchbase SDK auth failed có trả 401 cho user?** Không; đó là cấu hình/identity backend.
10. **Query rỗng có bắt buộc trả 404?** Không; search endpoint thường 200 [].
11. **Index lag có nghĩa document không tồn tại?** Không.
12. **`REQUEST_PLUS` có tạo index hoặc tăng durability không?** Không.
13. **Expired document có luôn là 410?** Không; cần lịch sử xác nhận đã gone.
14. **Ambiguous timeout có chứng minh write rollback không?** Không.
15. **Khi nào dùng 202?** Khi đã accepted async work và có status tracking đáng tin.
16. **Cùng Idempotency-Key payload khác trả gì?** 409.
17. **TransactionCommitAmbiguous có được retry mù không?** Không.
18. **TransactionFailed do không đủ stock nên trả 503?** Không; phân loại cause domain.
19. **Reactive `onErrorResume(error -> Mono.empty())` có nguy hiểm không?** Có thể che lỗi IO thành missing.
20. **HTTP 429 có phải mọi SDK overload?** Không, 429 là API admission/rate limit contract.
21. **Cần assert gì ngoài status trong test rollback?** State cuối các documents.
22. **ProblemDetail có nên chứa SDK stack trace?** Không.
23. **Vì sao metrics cần logical store?** Định vị lỗi cluster/bucket/adapter.
24. **Có thể đưa requestId vào metric label không?** Không nên, cardinality/PII.
25. **Content QA học thuật có tương đương readback file?** Không; cần bước QA riêng.

## 21. Checklist trước khi đưa API vào production

### Hợp đồng HTTP

- [ ] Có bảng lỗi theo **business operation**, không map chỉ theo exception class.
- [ ] 400/422 cho input invalid, 401/403 chỉ cho API client auth/authz.
- [ ] 404 cho missing resource theo contract; không biến query/index errors thành 404.
- [ ] 409 cho duplicate/business conflict, 412/428 khi dùng HTTP If-Match semantics.
- [ ] 429 chỉ khi rate limiting công bố rõ; 5xx cho dependency/internal faults.
- [ ] Có `application/problem+json` với type/title/status/detail/instance/code/traceId.
- [ ] Public code ổn định, không chứa raw SDK exception/cause/SQL++/secrets.
- [ ] Có OpenAPI error schemas và examples cho từng endpoint.
- [ ] Có policy rõ khi DELETE absent, TTL missing và 410 Gone.

### Persistence và consistency

- [ ] `insert` dùng để bảo đảm create-only, không check-then-upsert.
- [ ] `@Version`/CAS được kiểm chứng bằng hai snapshots thực.
- [ ] Lỗi CAS stale khác SDK timeout/ambiguous mutation.
- [ ] Query/index build/routing failures không bị che thành result rỗng.
- [ ] Query read-after-write có consistency phù hợp.
- [ ] Converter failure từ stored JSON không bị coi là 400 input.
- [ ] Missing cluster/bucket/collection/RBAC fail fast và log đúng.
- [ ] Durability/quorum đúng với cluster topology thực tế.
- [ ] TransactionFailed/Expired phân biệt với CommitAmbiguous.
- [ ] Không đặt external side effects trong retryable transaction lambda.
- [ ] TTL/expiry được hiểu là document lifetime, không phải transient connection issue.

### Retry, idempotency và bảo mật

- [ ] Retry có owner, timeout budget, backoff/jitter và không amplification.
- [ ] Retry CAS phải reload/recompute; không retry stale entity.
- [ ] Retry write ambiguous không dùng business ID mới.
- [ ] Có stable idempotency/operation marker và status lookup nếu API yêu cầu.
- [ ] 202 chỉ khi có durable async acceptance và status tracking.
- [ ] Retry-After không khuyến khích duplicate side effects.
- [ ] Spring Security 401/403 được xử lý ở đúng filter/entrypoint.
- [ ] Logs được redacted và correlation IDs an toàn.
- [ ] Không phát ra stack trace, credentials, SQL++ hoặc raw PII trong ProblemDetail.
- [ ] Rate limiting không được dùng để che backend overload.

### Test và vận hành

- [ ] Unit tests kiểm tra domain error invariants.
- [ ] MockMvc/WebFlux contract tests kiểm status, content type, code, fields.
- [ ] Testcontainers chứng minh duplicate, CAS, query/index và rollback thật.
- [ ] Test sau lỗi kiểm database state, không chỉ exception.
- [ ] Fault injection ambiguity được tách khỏi regression suite bình thường.
- [ ] Reactive tests subscribe publisher và cleanup.
- [ ] CI có Docker/resources/timeouts; không coi skipped integration là PASS.
- [ ] Metrics phân biệt business reject, dependency unavailable, unknown write outcome.
- [ ] Alert theo logical cluster/bucket và SLO, có runbook reconciliation.
- [ ] Không xem STEP 4 technical write/readback là Content QA STEP 6.

## Tài liệu tham khảo chính thức

- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): `type`, `title`, `status`, `detail`, `instance` và extensions.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): `400`, `404`, `409`, `410`, `412`, `429`, `503`, `504` và conditional requests.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): `428 Precondition Required` và `429 Too Many Requests`.
- [Spring Framework — Error Responses / ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, `@ControllerAdvice`.
- [Spring Framework — WebFlux Exceptions](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html): reactive error responses.
- [Spring Boot — Error Handling](https://docs.spring.io/spring-boot/reference/web/servlet.html): MVC error support và auto-configuration.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD, derived query và exceptions.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Id`, `@Version`, `@Document(expiry)`.
- [Spring Data Couchbase — Transactions](https://docs.spring.io/spring-data/couchbase/reference/couchbase/transactions.html): transaction manager và exception semantics.
- [Couchbase Java SDK — Error Handling](https://docs.couchbase.com/java-sdk/current/howtos/error-handling.html): exceptions, timeouts, retry, context.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): `insert`, `replace`, CAS, expiry/durability.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): Query/Index Services, scan consistency.
- [Couchbase Java SDK — Distributed Transactions](https://docs.couchbase.com/java-sdk/current/howtos/distributed-acid-transactions-from-the-sdk.html): transaction lambda, retry, commit/error handling.
- [Couchbase Java SDK — Transaction Error Handling](https://docs.couchbase.com/java-sdk/current/concept-docs/transactions-error-handling.html): `TransactionFailedException`, `TransactionCommitAmbiguousException`, unstaging.
- [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): quorum, persistence và ambiguous outcomes.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/): `StepVerifier`, error signals và subscription.
- [Testcontainers Java — Couchbase Module](https://java.testcontainers.org/modules/databases/couchbase/): test server thực/cô lập.




