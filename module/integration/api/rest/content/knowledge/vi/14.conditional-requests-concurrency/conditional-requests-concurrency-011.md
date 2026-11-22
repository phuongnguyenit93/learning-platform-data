# Kiểm thử cạnh tranh bằng nhiều yêu cầu đồng thời

## 1. Bài toán: hai client cùng sửa một tài nguyên

Trong một hệ thống quản lý kho, sản phẩm **P-100** có tên **“Bút xanh”** và phiên bản dữ liệu **7**. Hai nhân viên cùng mở màn hình chỉnh sửa. Người A đổi tên thành **“Bút xanh đậm”**; người B đổi thành **“Bút xanh nhạt”**. Cả hai bấm Lưu gần như cùng lúc.

Nếu server thực hiện đơn giản **đọc → sửa → ghi**, một request có thể ghi đè kết quả của request kia mà không hề báo lỗi. Đây là **lost update**. Nếu cả hai thao tác là “giữ chỗ còn lại cuối cùng”, kết quả sai còn có thể gây bán vượt số lượng hoặc đặt lịch trùng.

Một REST API có hợp đồng cập nhật có điều kiện có thể dùng **ETag** và **If-Match** để giải quyết phiên bản cũ. Tuy nhiên, **việc gửi một request thành công và một request thất bại theo thứ tự không chứng minh API xử lý đúng khi có cạnh tranh**. Cần kiểm thử nhiều yêu cầu xuất phát từ **cùng trạng thái ban đầu**, cùng lúc, với những tác vụ chạy qua các transaction riêng biệt.

Trong module **INTEGRATION_API_REST**, bài học này nối các chủ đề resource, URI, phương thức và mã HTTP, hợp đồng dữ liệu, idempotency, xác thực/phân quyền, xử lý lỗi, OpenAPI và kiểm thử Java/Spring. Trọng tâm là **thiết kế bài kiểm thử để chứng minh tính đúng đắn khi nhiều request cùng tác động đến dữ liệu**; không chỉ kiểm tra tốc độ dưới tải lớn.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **kiểm thử cạnh tranh (concurrency test)**, kiểm thử tải, thử tuần tự và thử khả năng retry.
2. Thiết kế invariant và kết quả mong đợi khi hai request cùng dùng **If-Match** trên một phiên bản.
3. Kiểm chứng **lost update, double booking, overselling, duplicate processing** và cập nhật một phần.
4. Tạo đồng thời thực sự trong kiểm thử Java/JUnit bằng **ExecutorService, CountDownLatch**, cùng HTTP client kết nối tới server đang chạy.
5. Hiểu tại sao **@Version**, kiểm tra phiên bản nguyên tử, ràng buộc DB và transaction quan trọng hơn một câu lệnh kiểm tra ở controller.
6. Phân biệt **412 Precondition Failed**, **428 Precondition Required**, **409 Conflict**, lỗi validation và **5xx** do sự cố nội bộ.
7. Kiểm thử retry/idempotency và các tác dụng phụ bất đồng bộ mà không chỉ đếm HTTP 2xx.
8. Xây dựng ma trận kiểm thử, cách tăng khả năng lặp lại, tiêu chí chấp nhận và hệ thống quan sát khi kiểm thử concurrent requests.

## 2. Kiểm thử cạnh tranh khác gì gửi nhiều request?

### 2.1. Request tuần tự không gây ra cùng một race

Giả sử test:

~~~text
GET /products/P-100   -> ETag "p-v7"
PATCH name="X", If-Match "p-v7" -> 200, ETag "p-v8"
PATCH name="Y", If-Match "p-v7" -> 412
~~~

Test này hữu ích để chứng minh **stale ETag bị từ chối**, nhưng request thứ hai diễn ra **sau khi request đầu hoàn tất**. Nó chưa kiểm tra thời điểm **cả hai transaction cùng đọc phiên bản v7**, rồi cố commit gần như đồng thời.

Trái lại, một concurrency test phải cho hai request có cơ hội thực sự **chồng lấn thời gian**:

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant API as REST API
    participant DB as Database
    Note over A,B: Cả hai đã nhận ETag "p-v7"
    par Client A
        A->>API: PATCH name=X, If-Match "p-v7"
    and Client B
        B->>API: PATCH name=Y, If-Match "p-v7"
    end
    API->>DB: Transaction A kiểm tra v7 và cập nhật
    API->>DB: Transaction B kiểm tra v7 và cập nhật
    Note over DB: Chỉ một transaction được commit cập nhật
    DB-->>API: Một cập nhật thành công, một cập nhật xung đột
    API-->>A: 200 hoặc 412 (tùy request thắng)
    API-->>B: 412 hoặc 200 (tùy request thắng)
    Note over A,B: Trạng thái cuối là X hoặc Y; không mất cập nhật âm thầm
~~~

**Không được giả định A luôn thắng.** Lịch thực thi thread, network và transaction có thể thay đổi qua mỗi lần chạy. Với cùng ETag ban đầu, hệ thống nên bảo đảm **đúng một cập nhật được chấp nhận**, chứ không bảo đảm cập nhật của client cụ thể nào hoàn tất trước.

### 2.2. Bốn kiểu kiểm thử cần tách bạch

| Loại | Mục tiêu chính | Ví dụ | Điều nó chưa tự chứng minh |
|---|---|---|---|
| **Functional/Sequential test** | Mã trạng thái và dữ liệu đúng với từng request có thứ tự | PATCH v7 thành công, PATCH v7 tiếp theo bị 412 | Hai request chồng lấn không gây lost update |
| **Concurrency/race test** | Bất biến đúng khi thao tác xen kẽ | Hai PATCH cùng phiên bản, hai đặt chỗ cùng ghế | Hệ thống đạt SLO dưới 10.000 RPS |
| **Load/stress test** | Throughput, latency, saturation và lỗi khi tải tăng | 500 client truy vấn, cập nhật đồng thời | Mỗi business invariant được kiểm tra kỹ nếu chỉ đo RPS |
| **Resilience/retry test** | Trạng thái đúng khi mất response, retry, timeout, crash | POST commit rồi client timeout và gửi lại cùng key | Không còn race trên mọi nhánh transaction |

Một dự án production nên kết hợp các loại test. **1000 request đồng thời chỉ assert “không có 500” vẫn có thể bỏ sót overselling hoặc ghi đè dữ liệu**.

## 3. Nhận diện race condition và invariant nghiệp vụ

### 3.1. Lost update

Hai client cùng đọc **stock=10**. A tính 10−3=7, B tính 10−2=8. Cả hai ghi lại giá trị tuyệt đối, kết quả cuối có thể là **7 hoặc 8**, thay vì **5**, dù cả hai request được báo thành công.

Nếu API cho phép hai thao tác giảm tồn độc lập, phải thiết kế **atomic decrement**/ràng buộc số lượng hoặc optimistic concurrency + retry ở tầng nghiệp vụ cho đúng yêu cầu. Nếu API biểu thị thay thế toàn bộ trạng thái, **If-Match** giúp từ chối cập nhật dựa trên biểu diễn cũ.

### 3.2. Check-then-act và double booking

Hai request cùng:

~~~text
SELECT seat WHERE seat_id = 'S-01' AND available = true
if available:
    INSERT booking for seat S-01
~~~

Nếu không có transaction hoặc ràng buộc unique thích hợp, hai request có thể cùng vượt qua bước kiểm tra rồi tạo **hai booking** cho một ghế.

**Invariant:** số booking đã xác nhận cho cùng một ghế của cùng sự kiện **không vượt quá 1**. Kiểm thử phải kiểm tra số hàng DB và nghiệp vụ sau các request, không chỉ HTTP status.

### 3.3. Duplicate processing do retry

Một client gửi POST tạo payment, server commit nhưng response bị mất. Client gửi lại; cùng một thao tác logic bị xử lý hai lần. Đây có thể xảy ra cả khi request thứ hai **không trùng thời gian** với request đầu. Cần **idempotency key**, uniqueness và lưu kết quả theo hợp đồng, không dùng correlation ID thay thế.

### 3.4. Write skew và invariant trải trên nhiều hàng

Hai bác sĩ trực, hệ thống yêu cầu **luôn có ít nhất một bác sĩ trực**. Mỗi transaction đọc thấy còn hai người trực, rồi mỗi người tự hủy lịch trực của chính mình. Nếu transaction được phép commit độc lập mà không bảo vệ ràng buộc liên hàng, cả hai có thể tắt trạng thái và **không còn ai trực**.

**Optimistic @Version trên từng hàng không tự ngăn mọi write skew**, vì hai transaction có thể cập nhật **hai hàng khác nhau**. Cần thiết kế ràng buộc nghiệp vụ bằng transaction isolation phù hợp, locking, constraint hoặc mô hình dữ liệu bảo vệ invariant. Concurrency test phải đưa vào tình huống hai hàng/tài nguyên nếu nghiệp vụ có invariant dạng này.

### 3.5. Các invariant cần ghi trước khi test

| Nghiệp vụ | Invariant | Quan sát sau test |
|---|---|---|
| Sửa product theo If-Match | Hai update từ cùng ETag cũ: nhiều nhất một update thực sự được chấp nhận | HTTP 200/204 và 412, version DB, giá trị cuối |
| Giữ một ghế còn lại | Không có hai booking đã xác nhận cho cùng ghế | Số booking, unique constraint, trạng thái ghế |
| Trừ kho | Stock không âm; tổng số được bán không vượt nguồn cung | Stock, số reservation, sự kiện xuất kho |
| Tạo đơn có idempotency key | Một key + cùng request logic tạo không quá một đơn | Bảng key, đơn hàng, response lưu, outbox |
| Hai lệnh cộng dồn riêng biệt | Mỗi lệnh hợp lệ tác động đúng một lần | Counter cuối, key khác nhau, audit event |
| Cập nhật nhiều phần của tài nguyên | Hoặc tất cả thay đổi được commit hoặc không có thay đổi | DB rows, event/outbox, không có partial write |

**Quy tắc:** status code là một bằng chứng, nhưng **invariant cuối cùng của dữ liệu mới quyết định test có đạt hay không**.

## 4. HTTP conditional requests khi có cạnh tranh

### 4.1. Đọc ETag trước khi sửa

Server trả một **strong ETag** cho representation tài nguyên:

~~~http
GET /products/P-100 HTTP/1.1
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "p-v7"

{
  "id": "P-100",
  "name": "Bút xanh",
  "version": 7
}
~~~

Client A và B cùng nhận **"p-v7"**, rồi gửi PATCH:

~~~http
PATCH /products/P-100 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "p-v7"

{"name":"Bút xanh đậm"}
~~~

**If-Match** yêu cầu điều kiện phiên bản của target representation còn đúng khi server thực hiện cập nhật. Với strong ETag và kiểm tra/ghi dữ liệu nguyên tử, một request có thể thắng; request còn lại phải thất bại khi trạng thái đã thay đổi.

### 4.2. Kết quả hợp lệ khi cùng phiên bản

Giả sử API chọn trả **200** với representation và ETag mới khi thành công. Với **hai PATCH hợp lệ, được ủy quyền và khác giá trị**, cùng If-Match **"p-v7"**:

| Điều kiện | Kết quả mong đợi |
|---|---|
| Request A thắng | A trả 200, B trả 412 |
| Request B thắng | B trả 200, A trả 412 |
| Trạng thái cuối | Tên bằng chính xác giá trị của request đã thắng |
| Phiên bản | Từ v7 chuyển sang v8 đúng một lần theo chính sách version của ví dụ |
| Sự kiện nghiệp vụ | Chỉ phát event cho cập nhật đã commit (nếu API có event) |
| Không được chấp nhận | **Cả A và B trả 200** và lần sửa sau âm thầm ghi đè lần trước |

Nếu server lỗi hạ tầng trong lúc test, có thể nhận 5xx; đó là **kết quả test thất bại cần điều tra**, không tự được xem là một nhánh hợp lệ của kịch bản có hai request hợp lệ.

### 4.3. 412, 428 và 409 khác nhau

| Mã HTTP | Ý nghĩa trong API ví dụ | Tình huống |
|---|---|---|
| **200 OK / 204 No Content** | Cập nhật thành công theo hợp đồng | Một request thắng, có thể trả body hoặc không |
| **412 Precondition Failed** | **If-Match** đã gửi nhưng không khớp hoặc transaction phát hiện phiên bản không còn thỏa | Hai request cùng v7, một thất bại |
| **428 Precondition Required** | Server yêu cầu conditional request mà client **không gửi** precondition cần thiết | PATCH không có If-Match |
| **409 Conflict** | Xung đột trạng thái nghiệp vụ, không phải điều kiện HTTP bị đánh giá false | Đặt ghế đã có người giữ hoặc trạng thái chuyển không hợp lệ |
| **400 Bad Request** | Cú pháp/header/payload sai theo hợp đồng | If-Match không thể parse hoặc JSON sai cú pháp |
| **401 / 403** | Không có xác thực / không được phép | Không được sửa tài nguyên |
| **404 Not Found** | Target resource không có representation hoặc được che giấu theo policy | Sản phẩm không tồn tại/không được công bố |
| **422 Unprocessable Content** | Payload hiểu được nhưng không hợp lệ về ngữ nghĩa | Giá âm hoặc quy tắc giá trị bị vi phạm |

**412 được dùng khi điều kiện If-Match thất bại.** Không nên thay thế tự động bằng 409 chỉ vì cả hai đều là “xung đột”. Đồng thời, không dùng 428 cho mọi lỗi phiên bản: 428 thường dành cho **thiếu điều kiện bắt buộc**, còn 412 cho **điều kiện không đúng**.

### 4.4. If-Match dùng so sánh strong validator

Lưu ý khi xây test:

- Strong ETag thường có dạng chuỗi đặt trong dấu ngoặc kép, như **"p-v7"**.
- Weak ETag **W/"p-v7"** không so khớp với If-Match theo quy tắc strong comparison.
- Header If-Match theo HTTP có thể chứa **danh sách ETag** hoặc **\***. Tránh viết parser production chỉ so sánh chuỗi thô trong trường hợp phải hỗ trợ toàn bộ cú pháp chuẩn.
- **\*** trong If-Match kiểm tra có representation hiện tại, không phải “bỏ qua concurrency”.
- ETag là **opaque validator**: client không tăng số phiên bản bằng cách tự sửa chuỗi.
- Strong ETag phải đổi chính xác khi representation được bảo vệ thay đổi; version của record không phải lúc nào cũng đủ nếu representation phụ thuộc quan hệ hoặc biến thể khác.
- Kiểm tra ETag trong controller rồi ghi database một cách **không nguyên tử** vẫn còn race condition.

### 4.5. If-None-Match và If-Unmodified-Since

**If-None-Match** thường dùng GET để revalidate bản sao, nhận **304 Not Modified** khi representation chưa đổi. Với phương thức thay đổi trạng thái, **If-None-Match: \*** còn được dùng trong một số hợp đồng để yêu cầu **chỉ tạo khi tài nguyên chưa tồn tại**, giúp tránh đè lên resource đã có.

**If-Unmodified-Since** là precondition theo thời điểm; nó có độ phân giải/giới hạn của HTTP-date và thường kém mạnh hơn strong ETag khi tài nguyên đổi nhiều lần trong thời gian ngắn. Khi cần tránh lost update chính xác, **If-Match với strong ETag** thường là lựa chọn phù hợp.

Nếu một request có nhiều conditional headers, server phải tuân thủ **thứ tự đánh giá precondition theo HTTP semantics**. Không tự thiết kế trình tự đánh giá tùy tiện nếu muốn tương thích chuẩn.

## 5. Điểm tuyến tính hóa: từ HTTP xuống database

### 5.1. Kiểm tra rồi ghi riêng biệt là chưa an toàn

Đoạn logic này có race:

~~~text
entity = repository.findById(id)
if entity.version != expectedVersion:
    return 412

entity.name = requestedName
repository.save(entity)
return 200
~~~

Nếu hai transaction cùng đọc version=7 trước khi transaction nào commit, cả hai có thể vượt kiểm tra. Nếu database chỉ ghi name không kiểm soát version, một thay đổi sẽ ghi đè thay đổi kia.

### 5.2. Optimistic concurrency với version và compare-and-swap

Ví dụ SQL thể hiện **điều kiện cập nhật nguyên tử**:

~~~sql
UPDATE products
SET name = :new_name,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
~~~

Nếu cả hai transaction gửi **expected_version = 7**, chỉ transaction cập nhật thành công trước mới đổi version thành 8. Transaction còn lại (sau khi phù hợp với cơ chế khóa/isolation của DB) thấy điều kiện version=7 không còn thỏa và **không cập nhật hàng**.

Service cần kiểm tra **affected rows**:

- **1 hàng:** cập nhật thành công.
- **0 hàng:** phiên bản đã thay đổi, resource đã mất hoặc quyền/ngữ cảnh khác không còn hợp lệ; phân loại status đúng hợp đồng, không mặc định mọi trường hợp là 412.

Giá trị phiên bản là **concurrency token nội bộ**; ETag HTTP phải gắn đúng representation và được tạo/parse theo hợp đồng, không cho client gửi trực tiếp SQL version tùy ý rồi xem là đã xác thực.

### 5.3. @Version trong JPA

JPA có cơ chế optimistic locking qua **@Version**:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
class Product {
    @Id
    private String id;

    private String name;

    @Version
    private long version;

    // Constructors, getters và domain methods được lược bỏ.
}
~~~

Trong một transaction, ORM thường sử dụng version khi UPDATE/flush. Nếu hai transaction cập nhật từ cùng version cũ, một transaction có thể nhận **OptimisticLockException** hoặc exception Spring tương ứng khi flush/commit. Cần để lỗi lan ra ngoài transaction và ánh xạ thành **412 khi đây là xung đột của If-Match trong hợp đồng endpoint**, sau khi đã phân loại lỗi.

**@Version không tự bảo đảm**:

- API bắt buộc client gửi If-Match.
- Authorization đúng theo tenant/resource.
- Tất cả cập nhật SQL bên ngoài ORM đều tăng/kiểm tra version.
- Invariant trải trên **nhiều hàng** hoặc **nhiều service** luôn được bảo vệ.
- Việc gửi event, email hoặc gọi payment bên ngoài transaction không bị lặp.

### 5.4. Isolation level, locking và ràng buộc

**READ COMMITTED**, **REPEATABLE READ**, **SERIALIZABLE**, pessimistic lock và unique constraint có semantics khác nhau theo database. Không thể kết luận “đã bọc @Transactional” nghĩa là không còn race.

| Bài toán | Cơ chế thường cân nhắc | Bằng chứng kiểm thử |
|---|---|---|
| Sửa một bản ghi theo version | Optimistic lock / compare-and-swap | Một request thắng, một request 412 |
| Trừ số lượng còn lại | Atomic conditional update hoặc lock thích hợp | Không âm, tổng reservation đúng |
| Giữ ghế duy nhất | Unique constraint, transaction và trạng thái booking | Không thể có hai booking được xác nhận cùng ghế |
| Invariant nhiều hàng | Lock phù hợp, serializable/constraint hoặc mô hình dữ liệu khác | Cạnh tranh trên các hàng khác nhau vẫn giữ invariant |
| Transaction có event | Transactional outbox | Số event tương ứng đúng số commit |
| Retry một thao tác logic | Idempotency key + uniqueness/transaction | Không tạo bản sao nghiệp vụ |

Chỉ dùng **sleep()** trong code production để “tránh đụng nhau” không phải giải pháp đồng thời. Độ trễ có thể thay đổi; cần một **điểm kiểm soát nguyên tử** đã xác định ở tầng lưu trữ hoặc hệ thống điều phối có semantics phù hợp.

## 6. Xây hợp đồng endpoint để kiểm thử có tiêu chí rõ

### 6.1. Hợp đồng của ví dụ Product API

Giả định hệ thống có:

~~~text
GET   /products/{id}
PATCH /products/{id}   Content-Type: application/merge-patch+json
~~~

Quy tắc:

1. GET trả **200**, representation và **strong ETag** hiện tại.
2. PATCH chỉ cho phép thay trường **name**, bắt buộc **If-Match**.
3. Khi name hợp lệ và If-Match khớp, cập nhật được commit nguyên tử, trả **200** với representation và ETag mới.
4. Nếu thiếu If-Match, trả **428** theo chính sách endpoint.
5. Nếu If-Match đã gửi nhưng không còn đúng, trả **412**, không thay dữ liệu.
6. Nếu chưa xác thực/không có quyền, xử lý **401/403/404 che giấu** theo chính sách; không để lộ ETag/version của tài nguyên không có quyền.
7. Một cập nhật thành công chỉ sinh **một** sự kiện thay đổi tên nếu nghiệp vụ có event.

Ví dụ phản hồi 412 theo **Problem Details (RFC 9457)**:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store
X-Correlation-ID: 6b76dafe-a0aa-478e-88ca-0b5e90e4f82d

{
  "type": "https://api.example.test/problems/stale-resource",
  "title": "Precondition Failed",
  "status": 412,
  "detail": "Tài nguyên đã thay đổi. Hãy tải lại trước khi cập nhật.",
  "code": "STALE_RESOURCE",
  "correlationId": "6b76dafe-a0aa-478e-88ca-0b5e90e4f82d"
}
~~~

**Correlation ID** chỉ giúp tìm dấu vết; nó không phải khóa idempotency và không chứng minh request đã commit. Error response không nên trả stack trace, SQL, secret hoặc representation chưa được ủy quyền.

### 6.2. Controller Spring MVC minh họa

~~~java
@RestController
@RequestMapping("/products")
class ProductController {
    private final ProductService service;

    ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    ResponseEntity<ProductView> get(@PathVariable String id) {
        VersionedProduct current = service.getAuthorized(id);
        return ResponseEntity.ok()
            .eTag(current.strongEtag())
            .body(current.view());
    }

    @PatchMapping(
        path = "/{id}",
        consumes = "application/merge-patch+json"
    )
    ResponseEntity<ProductView> rename(
            @PathVariable String id,
            @RequestHeader(
                name = "If-Match", required = false
            ) String ifMatch,
            @RequestBody RenameProductPatch patch) {

        if (ifMatch == null || ifMatch.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.PRECONDITION_REQUIRED,
                "If-Match is required"
            );
        }

        if (patch.name() == null || patch.name().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.UNPROCESSABLE_ENTITY,
                "name must not be blank"
            );
        }

        VersionedProduct updated =
            service.renameIfMatch(id, ifMatch, patch.name());

        return ResponseEntity.ok()
            .eTag(updated.strongEtag())
            .body(updated.view());
    }
}

record RenameProductPatch(String name) {}
// ProductService, ProductView, VersionedProduct là các kiểu
// minh họa của ứng dụng; imports được lược bỏ.
~~~

**Lưu ý giới hạn của đoạn code:** nó chỉ minh họa cách tổ chức controller. Để hỗ trợ **Merge Patch chuẩn**, API cần xử lý rõ trường **null**, field thiếu và field không được phép sửa; nếu chỉ hỗ trợ subset thay name, phải công bố trong OpenAPI và validate các field lạ, không bind thẳng JSON tùy ý vào JPA entity. Tại service cần kiểm tra **authorization, strong ETag** và **atomic optimistic concurrency**, không chỉ so sánh trong controller.

### 6.3. Giao dịch service phải bảo vệ đến lúc commit

Giả mã service:

~~~text
@Transactional
renameIfMatch(id, ifMatch, newName):
    product = lookup resource within caller's authorized scope
    if not found/visible: return 404 or appropriate auth error

    currentEtag = createStrongEtagForSelectedRepresentation(product)
    if not strongIfMatchSatisfied(ifMatch, currentEtag):
        return 412

    validate business rules for name
    change product.name
    flush / commit using @Version or conditional UPDATE
    if optimistic conflict:
        roll back and report 412 for this conditional write

    write domain/outbox event in same transaction if required
    return committed representation with correct new strong ETag
~~~

Giả mã là **hợp đồng thuật toán**, không phải cú pháp Java có thể chạy. Hàm **strongIfMatchSatisfied** cần tuân thủ phép so khớp strong ETag, danh sách validator và **\***. Nếu flush thành công nhưng event được gọi qua HTTP tới service khác **trước commit**, vẫn có nguy cơ phát event khi transaction sau đó rollback; cân nhắc transactional outbox.

### 6.4. Phần nào được phép gọi API khi chưa xác thực?

Trước khi chạy test concurrent, fixture cần xác định ai có quyền. Hai request cạnh tranh **cùng resource** từ hai principal có quyền hợp lệ thường là test business concurrency. Một request không có quyền thì phải kiểm thử riêng **authorization**, không nên kỳ vọng 412 của nó vì hệ thống có thể từ chối trước khi kiểm tra phiên bản. Khi test cross-tenant, không được suy rằng đối tượng “không có trong DB” chỉ vì repository đã áp dụng scope của principal.

## 7. Chọn cấp kiểm thử để bắt được race thật

### 7.1. Các lớp test nên có

| Cấp kiểm thử | Phát hiện tốt | Giới hạn cần nhớ |
|---|---|---|
| **Unit test** | Hàm tạo/so strong ETag, validate request, ánh xạ lỗi, tính toán invariant | Mock repository thường không mô phỏng khóa DB hoặc commit race |
| **Service/repository integration** | Transaction, @Version, compare-and-swap, unique constraint | Chưa kiểm chứng HTTP status, header, gateway và serialization |
| **HTTP integration (server đang chạy)** | Concurrency qua endpoint, transaction thật, response 200/412/428, phân quyền | Client xuất phát đồng thời chưa chắc các transaction đọc cùng lúc |
| **End-to-end multi-instance** | Nhiều API instance dùng chung DB/queue, cache, proxy, network | Tốn thời gian, khó tái hiện chính xác race nếu không có điều khiển |
| **Load/stress + invariant checks** | Hệ thống dưới tải và tranh chấp phổ biến | RPS cao không bảo đảm đã đi qua cửa sổ race cần kiểm tra |

Nên dùng **database engine và isolation/configuration sát production** để kiểm chứng cạnh tranh: một in-memory DB có thể thực hiện locking hoặc transaction khác PostgreSQL/MySQL. Có thể dùng môi trường kiểm thử chuyên dụng hoặc container database trong CI nếu dự án hỗ trợ.

### 7.2. Chuẩn bị fixture

Một test tốt cần:

- Resource test **riêng cho từng lần chạy** để không bị test khác hoặc worker khác can thiệp.
- Trạng thái khởi tạo được **commit** trước khi các HTTP request song song bắt đầu.
- Hai request lấy **cùng ETag ban đầu**, không lấy lại ETag giữa hai lệnh cạnh tranh.
- User/tenant/test token có **quyền rõ ràng**; không dùng token tùy ý chưa thiết lập.
- Không để một test method có **@Transactional rollback trên thread test** rồi tưởng dữ liệu đó xuất hiện ở các thread server: transaction của thread chạy test **không tự truyền** qua HTTP.
- Cleanup theo resource/tenant test sau khi test; không xóa dữ liệu test khác và không phụ thuộc thứ tự test.

Đặc biệt, test HTTP trên **RANDOM_PORT** với server thật chạy nhiều thread và kết nối database thật đáng tin cậy hơn một test chỉ gọi method controller tuần tự.

### 7.3. Đồng bộ điểm bắt đầu không bảo đảm đồng bộ điểm đọc DB

Sử dụng một barrier ở client để **phát hai request gần nhau** là kỹ thuật tốt nhưng chưa bảo đảm chúng cùng đến lệnh SELECT trong DB. Một thread có thể chạy nhanh và commit trước khi thread kia đi qua authentication.

Để kiểm thử cửa sổ race **có tính quyết định hơn**, có thể bổ sung một **test-only synchronization hook** ngay sau khi mỗi transaction đã đọc cùng version nhưng trước khi ghi, rồi thả cả hai. Điều kiện:

1. Hook chỉ được bật trong **môi trường test cô lập**, không cài chặn request production.
2. Có timeout để tránh deadlock nếu một transaction không tới barrier.
3. Không giữ transaction mở lâu ngoài nhu cầu kiểm thử; chú ý lock/isolation có thể khiến một bên chờ trước barrier.
4. Chỉ khẳng định “đã chạm cửa sổ race” nếu có bằng chứng từ hook hoặc log, không chỉ từ số thread.

Hai cách kiểm thử bổ sung cho nhau: **real HTTP + barrier đầu vào** chứng minh hợp đồng end-to-end, còn **điều khiển sau-read** giúp tái hiện xen kẽ DB khó xảy ra tự nhiên.

## 8. JUnit 5: gửi hai PATCH đồng thời qua HTTP

Ví dụ dưới đây minh họa bài test tích hợp **Spring Boot 3 + JUnit 5 + Java HttpClient**. Giả định đã có endpoint ở phần 6, dữ liệu sản phẩm do test fixture tạo, response 200 trả JSON có field **name**, và quyền của client được cấu hình cho môi trường test.

### 8.1. Tạo hai tác vụ có cùng ETag, mở barrier cùng lúc

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ProductConcurrentPatchIT {

    @LocalServerPort
    int port;

    @Autowired ProductTestFixture fixture;
    @Autowired ObjectMapper objectMapper;

    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

    @Test
    void onlyOnePatchWithSameEtagCanWin() throws Exception {
        // Fixture này phải tạo và COMMIT resource trước khi test gửi HTTP.
        String id = fixture.createCommittedProduct("Tên ban đầu");
        HttpResponse<String> firstGet = getProduct(id);
        assertEquals(200, firstGet.statusCode());

        String etag = firstGet.headers()
            .firstValue("ETag").orElseThrow();

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<HttpResponse<String>> requestA = () -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Barrier timeout A");
            }
            return patchName(id, etag, "Tên A");
        };

        Callable<HttpResponse<String>> requestB = () -> {
            ready.countDown();
            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Barrier timeout B");
            }
            return patchName(id, etag, "Tên B");
        };

        try {
            Future<HttpResponse<String>> futureA =
                pool.submit(requestA);
            Future<HttpResponse<String>> futureB =
                pool.submit(requestB);

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            HttpResponse<String> a =
                futureA.get(10, TimeUnit.SECONDS);
            HttpResponse<String> b =
                futureB.get(10, TimeUnit.SECONDS);

            // Không cố định A thắng hay B thắng.
            List<Integer> statuses = new ArrayList<>(
                List.of(a.statusCode(), b.statusCode())
            );
            statuses.sort(Integer::compareTo);
            assertEquals(List.of(200, 412), statuses);

            String winningName =
                a.statusCode() == 200 ? "Tên A" : "Tên B";

            HttpResponse<String> finalGet = getProduct(id);
            assertEquals(200, finalGet.statusCode());
            assertEquals(
                winningName,
                objectMapper.readTree(finalGet.body())
                    .path("name").asText()
            );

            String finalEtag = finalGet.headers()
                .firstValue("ETag").orElseThrow();
            assertNotEquals(etag, finalEtag);

            // Nếu fixture hỗ trợ, assert version + 1 và
            // đúng một bản ghi domain/outbox event.
            fixture.assertExactlyOneCommittedRename(id);
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }

    private HttpResponse<String> getProduct(String id)
            throws Exception {
        HttpRequest req = HttpRequest.newBuilder()
            .uri(URI.create(
                "http://localhost:" + port + "/products/" + id))
            .GET()
            .timeout(Duration.ofSeconds(5))
            .build();
        return client.send(req,
            HttpResponse.BodyHandlers.ofString());
    }

    private HttpResponse<String> patchName(
            String id, String etag, String newName)
            throws Exception {
        String json = objectMapper.writeValueAsString(
            java.util.Map.of("name", newName));

        HttpRequest req = HttpRequest.newBuilder()
            .uri(URI.create(
                "http://localhost:" + port + "/products/" + id))
            .header("Content-Type", "application/merge-patch+json")
            .header("If-Match", etag)
            .timeout(Duration.ofSeconds(5))
            .method("PATCH",
                HttpRequest.BodyPublishers.ofString(
                    json, StandardCharsets.UTF_8))
            .build();
        return client.send(req,
            HttpResponse.BodyHandlers.ofString());
    }
}

// ProductTestFixture là thành phần CHỈ DÀNH CHO TEST.
// Nó phải tạo dữ liệu đã commit, kiểm tra trạng thái và cleanup
// an toàn cho mỗi test. Authentication test được lược bỏ.
~~~

**Những điểm cần hiểu trong code:**

- **ready** bảo đảm hai task đã đến cửa chờ; **start** cho phép chúng gửi request gần như cùng thời điểm.
- Mỗi lời gọi HTTP chạy trên thread riêng. Server có thể dùng thread khác, connection khác và transaction DB khác.
- Cả hai request sử dụng **ETag từ cùng một GET**. Nếu mỗi task GET lại ETag ngay trước PATCH, một task có thể dùng v8 và cả hai cập nhật thành công **hợp lệ**, không còn kiểm thử trường hợp stale v7.
- Test **không gắn @Transactional ở method test** nhằm tránh fixture bị giữ chưa commit trên thread test.
- Client HTTP được cấu hình timeout; **Future.get** cũng có timeout để tránh CI treo nếu deadlock.
- **200/412** là status theo hợp đồng ví dụ. Nếu endpoint trả **204** khi thắng, hãy thay assert phù hợp; không thay đổi kỳ vọng **chỉ một cập nhật được commit**.
- Không chỉ kiểm tra status: test đọc lại resource, ETag và kiểm tra số domain/outbox events.

### 8.2. Vì sao không dùng sleep để tạo cạnh tranh?

Đoạn như:

~~~java
// Cách dễ flaky, không bảo đảm race:
executor.submit(() -> patchName(id, etag, "Tên A"));
Thread.sleep(10);
executor.submit(() -> patchName(id, etag, "Tên B"));
~~~

có thể khiến A luôn hoàn tất trước B trên một máy, nhưng B chạy trước A trên máy khác. **CountDownLatch/Phaser/CyclicBarrier** giúp đồng bộ tốt hơn. Tuy nhiên, như đã lưu ý, **barrier ở client chưa bảo đảm cả hai transaction đã đọc v7**; kiểm thử sâu hơn cần điều khiển cửa sổ cạnh tranh trong backend.

### 8.3. Những điểm mở rộng cho test thật

Trong dự án production, nên bổ sung:

- Xác thực giả lập hoặc bearer token thử nghiệm có quyền với resource, không dùng token thật.
- Kiểm tra 412 trả **Problem Details** có code cố định, không lộ exception.
- Kiểm tra body của request thành công khớp ETag/version mới.
- Kiểm tra **affected row count**, transaction commit, audit và outbox event sau test.
- Lặp lại test trên nhiều resource độc lập, có seed/log rõ ràng; không chạy nhiều test cùng sửa một fixture.
- Trường hợp phía client timeout **sau khi server commit** để kiểm thử recovery.

Nếu dùng **MockMvc**, có thể tạo nhiều task gọi MockMvc song song, nhưng nó **không tự mô phỏng mạng, proxy, gateway và transaction phân tách như một HTTP server thật**. MockMvc hữu ích cho controller behavior; bổ sung test chạy qua cổng HTTP để chứng minh contract end-to-end.

## 9. Kiểm thử deterministic race tại repository/service

### 9.1. Mục tiêu: chặn hai transaction ngay sau khi đọc v7

Giả sử bug chỉ xuất hiện khi hai transaction cùng đọc bản ghi trước khi có ai ghi. Một test đầu vào HTTP có thể không tái hiện được vì request B tới server sau khi A đã commit. Một **test-only hook** có thể làm rõ tiến trình:

~~~mermaid
sequenceDiagram
    participant T1 as Transaction 1
    participant T2 as Transaction 2
    participant H as Test Barrier
    participant DB as Database
    T1->>DB: READ product v7
    T1->>H: afterRead(v7), wait
    T2->>DB: READ product v7
    T2->>H: afterRead(v7), wait
    Note over H: Xác nhận cả hai đã đọc cùng phiên bản
    H-->>T1: Release
    H-->>T2: Release
    T1->>DB: UPDATE ... WHERE version=7
    T2->>DB: UPDATE ... WHERE version=7
    Note over DB: Chỉ một cập nhật được chấp nhận
~~~

Có thể dùng **CyclicBarrier(2)** hoặc **Phaser** cho hai transaction, với timeout và cơ chế dọn dẹp. Điểm hook cần nằm **sau khi đọc version nhưng trước cập nhật**, và chỉ tồn tại trong môi trường test có quyền kiểm soát.

Ví dụ giả mã của fixture:

~~~text
TestOnlyAfterReadHook.afterRead(productVersion):
    assert productVersion == 7
    barrier.await(timeout = 3 seconds)

Transaction A: read v7 -> barrier -> attempt update version=7
Transaction B: read v7 -> barrier -> attempt update version=7

assert:
    exactly one transaction commits the name change
    one transaction fails the stale-version condition
    committed product version == 8
    no duplicate outbox event
~~~

**Không nên chèn Thread.sleep() hoặc barrier trực tiếp vào code production** như một “giải pháp đồng thời”. Có thể dùng hook/interface trong test configuration, stub repository ở unit test, hoặc cơ chế fault injection ở test environment; test phải bảo đảm không ảnh hưởng traffic ngoài phạm vi.

### 9.2. Những hạn chế của barrier sau-read

- **Pessimistic lock** có thể khiến transaction thứ hai không đọc được bản ghi cho tới khi transaction thứ nhất thoát, nên test hook ở sau read có thể deadlock.
- Với một số mức **isolation**, mỗi transaction nhìn snapshot khác nhau; lịch đọc/ghi và lỗi có thể khác.
- Nếu barrier nằm **sau khi đã giữ exclusive lock**, một bên có thể không bao giờ đến barrier.
- Tài nguyên như connection pool phải đủ ít nhất hai connection cho hai transaction thử nghiệm, nếu không sẽ gặp timeout giả.
- Transaction timeout phải lớn hơn khoảng chờ test nhưng không quá lớn để gây treo CI; dùng giới hạn rõ ràng.

Không phải thiết kế nào cũng cần hai transaction đọc cùng lúc: **atomic SQL update** có thể kiểm chứng bằng hai lệnh tranh chấp mà không cần đồng bộ từng phép đọc. Mục tiêu test là **vi phạm không thể xảy ra**, không phải bắt buộc đi qua một schedule cụ thể nếu cơ chế đồng thời khác.

## 10. Kiểm tra kết quả cuối thay vì chỉ đếm HTTP status

### 10.1. Trạng thái dữ liệu sau race

Với hai PATCH theo ETag v7, hãy xác minh:

1. **HTTP:** đúng một 200/204 và một 412 theo contract.
2. **DB:** chỉ có một giá trị cuối, không bị ghi đè thêm sau khi kết quả đã được trả.
3. **Version:** tăng đúng một lần trong bài kiểm thử này.
4. **Audit/outbox:** đúng một event update thành công, không có event cho request 412.
5. **Response winner:** body và ETag phản ánh giá trị đã commit.
6. **Response loser:** mã lỗi đủ rõ, không chứa representation không có quyền hoặc stack trace.
7. **Không có update ngầm:** sau một khoảng chờ phù hợp và khi worker hoàn tất, trạng thái vẫn đúng.

**Không dùng version tăng đúng một lần như quy tắc toàn cục**: một hệ thống có trigger, timestamp hoặc logic versioning khác có thể có semantics riêng. Ở đây đó là bất biến **được quy định cho endpoint thử nghiệm**, cần dựa theo hợp đồng cụ thể.

### 10.2. Không được lấy “thành công của HTTP 2xx” làm chứng cứ duy nhất

Ví dụ hai request POST cùng đặt một ghế đều trả **201 Created** nhưng DB có **hai booking**: test phải thất bại. Ví dụ khác: một request trả **500** sau khi đã commit và tạo event, client retry thành 201 và tạo thêm booking: kiểm thử cần phát hiện **duplicate side effect**, không coi 500 ban đầu là bằng chứng chưa có thay đổi.

Kết quả cần so ở các nguồn phù hợp:

| Nguồn | Bằng chứng |
|---|---|
| HTTP status/body/header | Contract 200/201/204/409/412/428, ETag, Location, Problem Details |
| Database | Row count, version, uniqueness, constraint, trạng thái đã commit |
| Outbox / message broker | Số event hợp lệ, event ID, duplicate delivery và xử lý consumer |
| External side effect | Payment capture, email, SMS, booking đối tác, nếu thuộc luồng |
| Trace/log | Hai request riêng, correlation IDs, transaction outcomes, timeout/deadlock |

Test muốn chứng minh **không bị xử lý trùng** phải nhìn tác động cuối, không chỉ kiểm tra bảng idempotency keys có một row.

## 11. Kiểm thử đồng thời với Idempotency-Key

### 11.1. Vì sao If-Match không thay thế idempotency?

**If-Match** kiểm soát điều kiện cập nhật trên phiên bản tài nguyên. **Idempotency-Key** (nếu được API hỗ trợ) nhận diện **một thao tác nghiệp vụ logic** khi client gửi lại do timeout, mất kết nối hoặc thao tác lặp ngoài ý muốn.

Ví dụ:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 5dff9151-cb9c-4e4c-9215-43b4d6dbb498

{"cartId":"C-100","shippingMethod":"standard"}
~~~

Nếu client gửi request này hai lần **gần như đồng thời**, hợp đồng có thể yêu cầu **chỉ một đơn hàng** được tạo. Không được chỉ dựa vào hàng đợi hoặc một biến trong RAM của một instance để khẳng định chống trùng: nhiều API instance có thể nhận hai request cùng key.

### 11.2. Bốn kịch bản key quan trọng

| Kịch bản | Mục đích test | Invariant |
|---|---|---|
| **Hai request đồng thời, cùng key và payload** | Phát hiện check-then-insert race | Chỉ một thao tác nghiệp vụ được commit |
| **Retry sau khi request đầu hoàn thành** | Trả kết quả ổn định khi client mất response | Không sinh thêm đơn/event/phí, trả lại hoặc cho tra kết quả theo contract |
| **Cùng key, payload khác** | Ngăn key bị tái sử dụng sai | Không thực hiện thao tác khác dưới key cũ |
| **Hai key khác nhau, payload có thể giống nhau** | Phân biệt hai thao tác độc lập | Được xử lý như hai lệnh riêng nếu nghiệp vụ cho phép; ràng buộc khác vẫn áp dụng |

Trong lúc request cùng key đang chạy, API có thể:

- Chờ request đang xử lý và trả lại **response đã lưu**.
- Trả lỗi **409 Conflict** hoặc status đặc thù hợp đồng để client chờ và thử lại an toàn.
- Trả **202 Accepted** với resource/trạng thái để client kiểm tra khi xử lý bất đồng bộ.

**Không có một status bắt buộc cho mọi implementation Idempotency-Key.** Phải công bố và kiểm thử nhất quán trạng thái **in-progress, completed, conflicting fingerprint, expired key**.

### 11.3. Thiết kế dedup ở nơi có tính nguyên tử

Một bảng minh họa:

~~~sql
CREATE TABLE idempotency_requests (
    tenant_id        VARCHAR(80) NOT NULL,
    operation        VARCHAR(80) NOT NULL,
    idempotency_key  VARCHAR(120) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    state            VARCHAR(30) NOT NULL,
    resource_id      VARCHAR(80),
    response_body    TEXT,
    created_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation, idempotency_key)
);
~~~

Đây là **schema minh họa**; chọn kiểu dữ liệu, time zone, TTL, xử lý lỗi và bảo vệ dữ liệu tùy nền tảng thực. Đặt **UNIQUE/PRIMARY KEY** cho phạm vi key giúp DB phân xử hai request tranh chấp, thay vì:

~~~text
if key does not exist:
    insert key
    create order
~~~

vốn dễ tạo race khi hai request đều kiểm tra “chưa có key” trước khi insert.

Giải pháp cần đảm bảo **tính nguyên tử của bản ghi key và hành động nghiệp vụ** trong cùng transaction nếu có thể. Với side effect ngoài DB (thanh toán, gửi email), cần idempotency ở downstream, transactional outbox và đối soát; một transaction nội bộ không thể tự tạo bảo đảm **exactly-once end-to-end** trên toàn bộ hệ thống.

### 11.4. Phép thử 50 request cùng key

Chạy N=50 request với cùng key và cùng payload, đồng bộ barrier tại client:

~~~text
Arrange:
    tạo cart test hợp lệ
    tạo key "create-order-test-abc" chưa từng dùng
    chuẩn bị 50 clients/tasks có cùng key + request body

Act:
    thả barrier để gửi đồng thời
    thu mọi HTTP result hoặc timeout
    chờ mọi transaction/job có kết quả cuối theo timeout test

Assert:
    đúng một order được tạo cho key trong scope
    không có hai payment capture cho cùng logical operation
    event/outbox không phát sinh hiệu ứng nghiệp vụ trùng
    response của request trùng phù hợp hợp đồng
    cùng key + body khác bị từ chối
    key mới được xem là thao tác riêng khi nghiệp vụ cho phép
~~~

Không chỉ đếm **201**: 49 request còn lại có thể nhận replayed **201**, **200**, **202** hoặc **409** tùy contract. **Dữ liệu cuối và side effect** mới là căn cứ khẳng định duplicate processing được ngăn chặn.

### 11.5. Phạm vi key và bảo mật

Đừng lưu/tra key chỉ theo chuỗi do client gửi nếu có nhiều tenant. Phạm vi nên được ràng buộc với **principal/tenant đã xác thực, loại thao tác hoặc endpoint** và fingerprint các tham số quan trọng.

Đối với hai key giống nhau nhưng thuộc tenant khác nhau, hành vi phải **cô lập**; không để tenant A chặn hoặc đọc response của tenant B. Một key không phải credential; việc biết key không cấp quyền truy cập đơn hàng.

## 12. Giữ chỗ, trừ kho và ràng buộc nhiều request

### 12.1. Một đơn vị tồn kho còn lại

Giả sử còn **available=1** và hai người cùng đặt **1**:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE sku = :sku
  AND available >= 1;
~~~

Với một transaction/DB bảo đảm atomic statement phù hợp, **chỉ một UPDATE** có thể giảm từ 1 xuống 0; lệnh còn lại cập nhật 0 hàng sau khi điều kiện không còn đúng.

**Kết quả cần kiểm tra:**

- **available cuối = 0**, không bao giờ = -1.
- Chỉ **một reservation thành công**.
- Request thất bại được ánh xạ thành **409** hoặc lỗi domain phù hợp, không tạo reservation/event/charge phụ.
- Nếu request thành công nhưng response mất, retry phải **không giảm tồn lần thứ hai** khi cùng một thao tác logic (idempotency riêng).

Điều kiện **available >= 1** bảo vệ số lượng còn lại, nhưng không tự bảo vệ **duplicate request của một khách hàng**. Đây là hai invariant khác nhau.

### 12.2. Unique constraint để chống double booking

Một bảng booking có thể cần ràng buộc duy nhất theo **(event_id, seat_id)** cho các booking đã xác nhận; cách biểu diễn phụ thuộc lifecycle (hold, confirmed, cancelled, expired). Ví dụ database hỗ trợ partial unique index có thể dùng:

~~~sql
-- Ví dụ cú pháp PostgreSQL, không portable nguyên vẹn cho mọi DB.
CREATE UNIQUE INDEX uq_confirmed_seat
ON bookings (event_id, seat_id)
WHERE status = 'CONFIRMED';
~~~

Đừng tạo constraint theo (seat_id) nếu cùng số ghế **S-01** xuất hiện ở nhiều sự kiện. Đừng để booking bị cancel vẫn chặn vô thời hạn nếu lifecycle yêu cầu giải phóng ghế.

Test cần đưa hai transaction song song đến đúng cửa sổ **check available → confirm**. Ràng buộc database là hàng phòng thủ cuối; service phải phân loại **unique violation** thành xung đột nghiệp vụ, rollback transaction và bảo đảm không charge cả hai người.

### 12.3. Cạnh tranh trên nhiều bản ghi

Trong hệ thống chuyển tiền, tính đúng đắn có thể yêu cầu:

\[
\text{Tổng số dư trước} = \text{Tổng số dư sau}
\]

trừ các khoản phí/điều chỉnh được hạch toán minh bạch. Một transaction chỉ cập nhật một tài khoản trước khi request khác đọc có thể làm vi phạm invariant nếu chuyển khoản không được thực hiện nguyên tử.

Test không chỉ gửi hai PATCH lên **một** resource; cần kịch bản hai transfer ngược chiều, hai chuyển khoản từ cùng tài khoản, hoặc hai thao tác phụ thuộc cùng hạn mức. Cơ chế **@Version một entity** không phải đáp án cho mọi invariant nhiều hàng.

### 12.4. Khi có cache hoặc search index

Một database commit đúng nhưng **cache còn stale** có thể khiến request thứ hai đọc version cũ. Nếu API sử dụng ETag lấy từ cache còn stale và không kiểm tra tại điểm ghi nguyên tử, vẫn có lost update hoặc trả 412/200 không nhất quán.

Kiểm thử nên phân biệt:

1. GET lấy representation/ETag từ CDN hoặc app cache.
2. PATCH đi tới origin và kiểm tra version **ở DB/nguồn chân lý**.
3. GET lại trước/sau invalidation và conditional GET để xác minh dữ liệu không stale quá SLO.

Không bắt buộc mọi GET ngay lập tức phản ánh commit mới nếu contract cho phép eventual consistency; tuy nhiên, **phép ghi có điều kiện phải kiểm soát phiên bản tại nguồn có thẩm quyền**, không dựa vào cache stale như trọng tài duy nhất.

## 13. Mất phản hồi, retry và tính không chắc chắn sau commit

### 13.1. Khi timeout không đồng nghĩa thất bại

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as REST API
    participant DB as Database
    C->>API: PATCH /products/P-100 If-Match "p-v7"
    API->>DB: UPDATE WHERE version=7
    DB-->>API: Commit thành công, version=8
    Note over API,C: Response bị mất trong mạng
    C->>API: Retry PATCH cùng If-Match "p-v7"
    API-->>C: 412 Precondition Failed
~~~

Client nhận 412 ở lần retry **không thể kết luận**:

- “Request đầu của tôi đã chắc chắn thành công” — vì có thể **người khác** đã đổi resource.
- “Request đầu của tôi chắc chắn chưa chạy” — vì lần đầu có thể đã commit.

Client cần **GET lại tài nguyên**, so sánh kết quả mong muốn, và cân nhắc cách xác định request gốc đã được xử lý, đặc biệt nếu PATCH có side effect ngoài việc đặt trạng thái. Với thao tác không idempotent, API có thể cần **Idempotency-Key** để truy xuất kết quả logic.

### 13.2. Khi nào retry có thể an toàn?

| Loại request | Retry sau network timeout | Ghi chú |
|---|---|---|
| GET (safe) | Thường có thể retry có giới hạn | Vẫn cần timeout/backoff để tránh quá tải |
| PUT thay thế representation có điều kiện | Có thể retry **theo hợp đồng** nhưng cần xử lý 412 và đối chiếu trạng thái | PUT idempotent theo ngữ nghĩa, không có nghĩa response lần retry giống nhau |
| PATCH đặt field giá trị tuyệt đối | Có thể lũy đẳng theo trạng thái, nhưng xét If-Match và side effects | Không tự suy PATCH luôn an toàn |
| PATCH increment/append | **Không tự retry** nếu không có dedup | Mỗi lần áp dụng có thể cộng dồn |
| POST tạo đơn/thu phí | Cần idempotency contract để retry an toàn | Không lấy correlation ID thay idempotency key |
| Retry sau 409/412 | Xử lý trạng thái/xung đột trước | Không lặp vô hạn cùng precondition |
| Retry sau 429/503 | Backoff/Retry-After khi được cung cấp và **an toàn về ngữ nghĩa** | Backoff không ngăn double charge |

### 13.3. Kiểm thử commit rồi mất response

Trong một test riêng, có thể dùng **fault injection có kiểm soát** sau khi DB commit nhưng trước khi response tới client, hoặc dùng test proxy ngắt kết nối ở vị trí thích hợp. Không nên ném exception trong cùng transaction **trước commit** rồi coi đó là “response lost after commit”.

Kịch bản:

1. Client gửi request với key/precondition theo contract.
2. Server commit nghiệp vụ, nhưng client thấy connection reset hoặc timeout.
3. Client gửi lại cùng thao tác và key/precondition.
4. Kiểm tra status/response theo hợp đồng, DB và mọi side effect.

Mục tiêu là kiểm chứng rằng **mất response không làm mất tính đúng đắn**, không chỉ rằng API trả về một status cụ thể.

### 13.4. Deadlock và retry ở tầng database

Dưới concurrency cao, database có thể phát sinh **deadlock**, **serialization failure** hoặc timeout lock. Nếu service retry toàn bộ transaction, phải:

- Retry ở **ranh giới transaction** có kiểm soát, không retry một đoạn đã gây side effect bên ngoài.
- Dùng transaction mới khi cần, đọc lại trạng thái mới và đánh giá invariant/precondition phù hợp.
- Giới hạn retry count, backoff và deadline; không tự chuyển mọi conflict thành 200.
- Kiểm tra event/outbox và idempotency để không phát sinh tác dụng phụ trùng.

**Không phải mọi exception optimistic lock đều nên retry tự động.** Với If-Match do client gửi, tình trạng phiên bản đã thay đổi thường phải trả **412** để client quyết định dựa trên representation mới. Việc server âm thầm cập nhật theo phiên bản mới có thể đi ngược điều kiện của client.

## 14. Điều kiện GET song song với PATCH và khả năng quan sát

Concurrency không chỉ xảy ra giữa hai writer. Nhiều client có thể đọc/validate cache trong khi writer cập nhật.

### 14.1. Conditional GET trong lúc dữ liệu đổi

Giả sử client có ETag **"p-v7"** và gửi:

~~~http
GET /products/P-100 HTTP/1.1
If-None-Match: "p-v7"
~~~

Nếu selected representation chưa đổi theo điều kiện GET, server có thể trả **304 Not Modified**. Nếu writer đã commit phiên bản v8 và ETag phản ánh thay đổi, server nên trả **200** với representation mới.

**Kiểm thử:** chạy GET có điều kiện song song với PATCH, ghi nhận thời điểm server quyết định representation. Kết quả có thể là **304** nếu GET được đánh giá trước commit, hoặc **200** nếu sau commit, tùy thứ tự sự kiện. Test không nên cố định “GET luôn phải trả v8” nếu không có bảo đảm đọc nhất quán mạnh tại thời điểm được xác định.

Tuy nhiên, server không được trả **304 với ETag v7** khi nó đã chọn/đánh giá một representation v8 theo hợp đồng; ETag, body và validator phải nhất quán tại thời điểm quyết định.

### 14.2. GET không được thấy trạng thái cập nhật dở dang

Với PATCH thay nhiều trường hoặc transaction nhiều bảng, test có thể chạy reader liên tục trong lúc writer cập nhật. Nếu contract yêu cầu atomicity, không reader nào được nhận một representation pha trộn **trường mới và trường cũ** do commit một phần.

Ví dụ:

~~~text
Trước:  price=100, discount=10, total=90
Sau:    price=120, discount=20, total=100

Trạng thái không hợp lệ trong test:
        price=120, discount=10, total=90
~~~

Kết quả có thể phụ thuộc transaction isolation và cách đọc nhiều nguồn (DB, cache, search). Cần xác định invariant của representation mà API cam kết; không được thử một trạng thái nhất quán mạnh nếu kiến trúc công bố eventual consistency mà không có giải thích phạm vi/độ trễ.

### 14.3. 304 không phải đáp án thay thế 412

- **If-None-Match** trong GET có thể dẫn tới **304** khi representation không đổi.
- **If-Match** trong PATCH/PUT có thể dẫn tới **412** khi precondition sai.
- **304** không phải mã “bản ghi đã được cập nhật bởi client trước đó”.
- **412** không phải mã “không có nội dung cập nhật”.

Test cả hai loại điều kiện giúp tránh việc API dùng chung một handler cho mọi conditional header và trả status sai ngữ nghĩa.

## 15. Hợp đồng OpenAPI cho cập nhật có điều kiện

OpenAPI nên mô tả rõ **If-Match, kiểu patch, schema, status lỗi và semantics retry**. Ví dụ OpenAPI 3.0.3 rút gọn:

~~~yaml
openapi: 3.0.3
info:
  title: Concurrent Products API
  version: 1.0.0
paths:
  /products/{id}:
    get:
      summary: Đọc sản phẩm và phiên bản hiện tại
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        "200":
          description: Representation hiện tại
          headers:
            ETag:
              description: Strong ETag dùng với If-Match
              schema: {type: string}
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Product"
        "404":
          description: Không tìm thấy sản phẩm
    patch:
      summary: Đổi tên có điều kiện tránh lost update
      description: >
        Bắt buộc If-Match. Nếu precondition không còn
        đúng, không được ghi dữ liệu; trả 412.
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
        - name: If-Match
          in: header
          required: true
          description: Strong ETag của representation đã đọc
          schema: {type: string}
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema:
              type: object
              properties:
                name:
                  type: string
                  minLength: 1
              required: [name]
              additionalProperties: false
            example:
              name: Bút xanh đậm
      responses:
        "200":
          description: Cập nhật thành công
          headers:
            ETag:
              schema: {type: string}
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Product"
        "400":
          description: Request/header không hợp lệ
        "401":
          description: Thiếu hoặc sai xác thực
        "403":
          description: Không có quyền cập nhật
        "404":
          description: Không có resource nhìn thấy được
        "412":
          description: If-Match không khớp hoặc stale
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
        "422":
          description: Giá trị name vi phạm quy tắc
        "428":
          description: Thiếu precondition bắt buộc
components:
  schemas:
    Product:
      type: object
      properties:
        id: {type: string}
        name: {type: string}
        version: {type: integer, format: int64}
      required: [id, name, version]
    ApiProblem:
      type: object
      properties:
        type: {type: string}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        code: {type: string}
      required: [type, title, status, code]
~~~

Ví dụ này chỉ hỗ trợ một **subset đổi name** của Merge Patch và cần được thực thi/validate nhất quán. Với endpoint POST có Idempotency-Key, nên khai báo header, phạm vi key, TTL, trạng thái in-progress/completed, xử lý key trùng/khác payload và các status cụ thể riêng, thay vì gộp cơ chế đó vào If-Match.

**OpenAPI mô tả hợp đồng; nó không tự làm transaction, optimistic locking hay kiểm thử race.** Phải xác minh cả code, database và các service downstream.

## 16. Ma trận kiểm thử cạnh tranh theo mức độ ưu tiên

Một bộ test tốt cần bao phủ cả **đường thành công**, **đường bị từ chối có chủ đích**, **sự cố mạng** và **hành vi transaction**. Ma trận sau là điểm xuất phát:

| ID | Điều kiện / thao tác đồng thời | Kết quả HTTP mong đợi | Invariant cần kiểm tra |
|---|---|---|---|
| C01 | Một GET lấy strong ETag | 200 với ETag | ETag phản ánh representation hiện tại |
| C02 | Một PATCH hợp lệ, If-Match đúng | 200/204 theo contract | Cập nhật commit, version mới |
| C03 | Một PATCH thiếu If-Match | **428** | Không sửa tài nguyên |
| C04 | Một PATCH dùng ETag cũ | **412** | Không ghi đè giá trị mới |
| C05 | Hai PATCH tên khác nhau, cùng ETag và đồng thời | **Một 200, một 412** theo ví dụ | Đúng một thay đổi và một version increment |
| C06 | N request dùng cùng ETag ban đầu | Một thắng, còn lại 412 theo contract (nếu không có lỗi phụ) | Không có lost update, tối đa một commit |
| C07 | Hai request dùng **weak ETag** với If-Match | Không thỏa strong comparison | Không ghi sai vào tài nguyên |
| C08 | If-Match chứa danh sách validator hợp lệ | Theo strong match và trạng thái hiện tại | Không parse nhầm header/điều kiện |
| C09 | If-Match **\*** trên tài nguyên tồn tại và vắng mặt | Theo ngữ nghĩa có representation hiện tại | Không xem \* là phiên bản bất kỳ được quyền ghi vô điều kiện |
| C10 | Hai principal có quyền cùng sửa một resource | Một cập nhật theo concurrency contract | Không phụ thuộc thứ tự thread |
| C11 | Principal không có quyền gửi PATCH với ETag biết được | 401/403/404 theo policy | Không rò thông tin hoặc sửa dữ liệu trái quyền |
| C12 | Hai POST cùng key/payload | Status in-progress/replay theo contract | Một order logic, không duplicate side effects |
| C13 | Cùng key, payload khác | Lỗi key reuse theo contract | Không tạo thao tác mới |
| C14 | Hai thao tác hợp lệ có key khác nhau | Cả hai có thể thành công nếu nghiệp vụ cho phép | Mỗi thao tác được áp dụng đúng một lần |
| C15 | Hai người cùng mua ghế cuối | Một thành công, một conflict | Không double booking |
| C16 | Hai lệnh giảm kho vượt số lượng hiện có | Success/conflict theo hợp đồng | Stock không âm, reservation đúng |
| C17 | Hai transaction sửa **hai hàng** có invariant chung | Tùy semantics | Invariant liên hàng vẫn đúng |
| C18 | PATCH nhiều bước, bước sau lỗi | Status theo hợp đồng | Không commit từng phần |
| C19 | Commit thành công nhưng response mất | Timeout rồi kết quả retry theo contract | Không lặp nghiệp vụ |
| C20 | GET If-None-Match đua với PATCH | 304 hoặc 200 tùy thời điểm đánh giá | ETag/body nhất quán |
| C21 | Đọc qua cache stale sau PATCH | Status GET theo cache contract | Không vi phạm staleness budget/quyền |
| C22 | Hai API instances cùng xử lý key hoặc ETag | Phản hồi hợp đồng | DB uniqueness/version hoạt động xuyên instance |
| C23 | Lock timeout, deadlock hoặc serialization failure | Status và retry policy có tài liệu | Không partial commit/side effect trùng |
| C24 | Worker nhận trùng event sau transaction | HTTP có thể đã hoàn tất | Consumer không tạo hiệu ứng nghiệp vụ trùng |

### 16.1. Phân loại mức bắt buộc

Với endpoint **PATCH yêu cầu If-Match**, tối thiểu cần **C01–C05**, test malformed/weak ETag, thiếu auth và kiểm tra DB sau race. Với endpoint **POST tạo đơn có Idempotency-Key**, ưu tiên **C12–C14, C19, C22, C24**. Với hệ thống đặt vé/kho, thêm **C15–C17** cùng ràng buộc database.

Không chạy một danh sách test lớn chỉ để “đủ số lượng” mà không kiểm tra invariant. Mỗi test nên nói rõ **điểm đồng thời, điều kiện khởi tạo, trạng thái được phép và trạng thái bị cấm**.

### 16.2. Tham số hóa và randomization

Có thể chạy:

- 2 request tranh chấp trực tiếp cùng ETag.
- 10–100 request cùng resource, cùng precondition.
- Nhiều resource độc lập để so sánh với tranh chấp tập trung vào một resource.
- Các khoảng delay nhỏ được **randomize theo seed lưu lại được**, nhằm tìm nhiều cách xen kẽ.
- Một hoặc nhiều API instance với cùng database và message broker.

**Ngẫu nhiên hóa là bổ sung**, không thay cho test deterministic ở cửa sổ race quan trọng. Khi test fail, cần ghi lại seed, request ID, resource ID, phiên bản, môi trường và trace để tái hiện.

## 17. Quan sát khi test thất bại và chống test flaky

### 17.1. Log và trace cần thể hiện điều gì?

Một lỗi concurrency thường khó suy ra từ mỗi HTTP response. Nên có **structured logs** và trace theo request:

~~~json
{
  "event": "product.rename.conflict",
  "correlationId": "ceacf6b3-710e-4c98-97f8-c10ab13baf56",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "http.method": "PATCH",
  "http.route": "/products/{id}",
  "http.status_code": 412,
  "resource.type": "product",
  "expected.version": 7,
  "actual.version": 8,
  "transaction.outcome": "rolled_back",
  "duration_ms": 34
}
~~~

Các trường là ví dụ. Log production cần **ẩn hoặc hạn chế resource/user/tenant ID**, không ghi Authorization, giá trị nhạy cảm hoặc raw SQL chứa dữ liệu người dùng. **Correlation ID** dùng để điều tra; không dùng nó làm nhãn cho mọi time-series metric vì cardinality quá lớn.

### 17.2. Những metric đáng theo dõi

| Metric | Mục đích |
|---|---|
| Tỷ lệ **412** theo route | Có nhiều client sửa cùng version hay không |
| Tỷ lệ **428** | Client chưa áp dụng hợp đồng If-Match |
| Số optimistic-lock conflicts | Mức tranh chấp ở tầng DB |
| Deadlock/serialization failure | Nguy cơ transaction và locking |
| Số retry mỗi thao tác | Phát hiện retry storm và khuếch đại tải |
| Duplicate key/replay counts | Hiệu quả và tải của cơ chế idempotency |
| p95/p99 latency của write | Tác động lock và tranh chấp đến SLO |
| Outbox backlog / consumer duplicate rate | Tính nhất quán và tốc độ xử lý event |
| Số vi phạm invariant | Chỉ số bắt buộc bằng 0 đối với các bất biến nghiệp vụ nghiêm trọng |

**Không phải mọi 412 đều là incident.** Trong optimistic concurrency, một số xung đột là hành vi **đúng** để bảo vệ dữ liệu. Tuy nhiên tỷ lệ 412 quá cao có thể khiến UX tệ, cần xem lại granularity của tài nguyên, workflow và cơ chế merge.

### 17.3. Nguyên nhân phổ biến khiến test flaky

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều chỉnh |
|---|---|---|
| Lúc có race, lúc không | Hai request đến DB theo thứ tự khác nhau | Barrier client + test-only hook sau-read khi cần |
| Test pass local, fail CI | CPU, connection pool, scheduler, DB khác | Timeout hợp lý; DB tương đương; log schedule |
| Một request nhận 404 bất ngờ | Fixture chưa commit hoặc bị test khác xóa | Dữ liệu unique, commit trước start, cleanup cô lập |
| Một request treo tới timeout | Deadlock ở barrier/connection pool | Đặt timeout, đủ connection, không đặt barrier sau lock sai vị trí |
| Test đúng 200/412 nhưng DB sai | Handler trả response trước commit hoặc logic transaction sai | Kiểm tra state DB sau commit, outbox và request winner |
| Test kiểm event thấy 0/2 | Event xử lý async chậm, duplicate delivery | Đợi trạng thái cuối có deadline, assert nghiệp vụ và idempotency |
| MockMvc pass nhưng production sai | Mock không chạy gateway/DB lock thật | HTTP integration + multi-instance test |
| Nhiều thread cùng dùng EntityManager | Context JPA không thread-safe | Mỗi transaction/request dùng context riêng do framework quản lý |
| Assert theo “A luôn thắng” | Scheduler không xác định | Assert tập outcome và bất biến, không thứ tự thread |
| Test cần sleep cố định để “chờ consumer” | Công việc async có thời gian biến thiên | Poll trạng thái đến điều kiện với timeout, không chỉ sleep |

### 17.4. Test không được vô tình tạo điều kiện sản xuất sai

Trong kiểm thử concurrency:

- Không dùng dữ liệu thanh toán thật, token production hoặc tài khoản khách hàng thật.
- Không cố ý gây race trên hệ thống production ngoài kịch bản đã được phê duyệt và cô lập.
- Không bật debug logging chứa body nhạy cảm trên môi trường chung chỉ vì test thất bại.
- Nếu test tiêm lỗi mạng/DB, phải có giới hạn phạm vi, rollback/cleanup và người chịu trách nhiệm.

Một **invariant test chạy lặp với tài nguyên giả lập** thường an toàn hơn một stress test không kiểm soát tác động nghiệp vụ.

## 18. Case study: hai khách mua chiếc ghế cuối cùng

### 18.1. Mô hình nghiệp vụ

Một nền tảng đặt vé **TicketFlow** có đúng một ghế **S-01** còn trống trong sự kiện **E-2026**. Hai người A và B bấm mua gần như đồng thời.

REST API minh họa:

~~~text
GET  /events/E-2026/seats/S-01
POST /reservations
GET  /reservations/{reservationId}
~~~

GET seat cho biết trạng thái tham khảo. POST đặt chỗ cần kiểm soát tồn kho trong transaction, không chỉ tin dữ liệu GET từ cache. Mỗi logical reservation dùng Idempotency-Key nếu API hỗ trợ.

### 18.2. Một thiết kế dễ mắc lỗi

~~~text
POST /reservations:
    seat = repository.findById(S-01)
    if seat.available:
        paymentService.chargeCard(...)
        bookingRepository.save(confirmedBooking)
        seat.available = false
        return 201
    else:
        return 409
~~~

Hai thread cùng thấy **seat.available = true**; cả hai có thể gọi charge trước khi ai commit booking. Một transaction thất bại về sau **không tự đảo ngược** payment capture đã xảy ra ở hệ thống ngoài.

### 18.3. Thiết kế ứng viên an toàn hơn

1. Tạo **logical reservation** có idempotency key, chống trùng ở dữ liệu giao dịch.
2. Trong transaction, kiểm tra và giữ ghế nguyên tử bằng conditional update/unique constraint/locking phù hợp.
3. Chỉ có một reservation được xác nhận thành công; request còn lại trả **409** với mã **SEAT_NOT_AVAILABLE** theo hợp đồng.
4. Ghi outbox event hoặc trạng thái cần xử lý thanh toán trong cùng transaction, tránh gọi payment không kiểm soát trước commit.
5. Worker thanh toán xử lý có idempotency ở phía payment và cơ chế đối soát/compensation khi thất bại.
6. Trả **201 Created** với Location khi resource reservation được tạo theo contract; nếu xác nhận bất đồng bộ, có thể dùng **202 Accepted** và endpoint theo dõi trạng thái.

**Không có một thiết kế duy nhất** cho mọi hãng vé. Một hệ thống có thể cần giữ chỗ có TTL trước khi thu tiền; hệ thống khác chọn thanh toán trước rồi hoàn tiền nếu không giữ được ghế. Dù chọn cách nào, các invariant và hành vi thất bại phải được định nghĩa rõ.

### 18.4. Bộ test cạnh tranh cho TicketFlow

| Test | Hành động | Điều bắt buộc |
|---|---|---|
| Hai người, hai key, cùng ghế cuối | Gửi 2 POST đồng thời | Tối đa 1 reservation confirmed |
| Một người, một key, 20 retry | Gửi 20 POST đồng thời | Tối đa 1 logical reservation và 1 payment operation |
| Hai user có key trùng ngẫu nhiên | Gửi từ principal/tenant khác nhau | Scope idempotency không chặn hay lộ dữ liệu chéo |
| Response mất sau khi giữ ghế | Cắt kết nối, retry cùng key | Không giữ/thu phí lần hai; tìm được kết quả |
| Payment worker xử lý lại event | Delivery trùng | Không double capture |
| Request không có quyền | Caller không có quyền trên event | 401/403/404 phù hợp, không có reservation |
| 100 khách cùng tranh ghế cuối | Barrier 100 request | Không oversell, hệ thống không treo vô hạn |

### 18.5. Kết luận từ test

Nếu 100 người tranh một ghế mà **99 request trả 409**, đó có thể là kết quả **đúng**: chỉ một người được giữ ghế. Nếu chỉ có một 201 nhưng **hai payment capture**, test vẫn **thất bại nghiêm trọng**. Nếu mọi request trả 500 khi tranh chấp, database có thể bảo vệ dữ liệu nhưng API chưa ánh xạ xung đột thành hợp đồng khách hàng có thể xử lý.

## 19. Bài thực hành: thiết kế và diễn giải concurrency tests

### Bài 1: Cùng ETag cho hai PATCH

**Bối cảnh:** GET /documents/D-100 trả:

~~~http
HTTP/1.1 200 OK
ETag: "doc-v12"
Content-Type: application/json

{"id":"D-100","title":"Hướng dẫn","version":12}
~~~

Client A và B cùng PATCH **title** với **If-Match: "doc-v12"** và giá trị khác nhau. API quy định trả 200 khi commit, 412 khi precondition không còn đúng, mỗi lần cập nhật thực làm version tăng 1.

**Yêu cầu:**

1. Viết các cặp HTTP status hợp lệ cho hai request được thực thi cạnh tranh bình thường.
2. Nêu các trạng thái cuối được phép và trạng thái bị cấm.
3. Thiết kế CountDownLatch ở client để hai lệnh phát gần nhau.
4. Giải thích tại sao kiểm tra If-Match ở controller trước UPDATE **không đủ**.
5. Nêu bằng chứng cần lấy ở DB và event log để kết luận.

**Gợi ý đáp án:** Cặp status là **(200,412)** hoặc **(412,200)**; trạng thái cuối phải là title A hoặc title B tương ứng request thắng, version=13, không có hai event thành công. Cần **@Version/conditional update nguyên tử** hoặc cơ chế tương đương tại DB. Barrier client giúp tăng cơ hội race; hook sau-read giúp ép lịch thực thi nếu cần.

### Bài 2: Hai lần nhấn nút “Tăng tồn”

**Bối cảnh:** PATCH /products/P-100/stock với JSON:

~~~json
{"operation":"increment","amount":3}
~~~

Client mất mạng sau request đầu, không biết server đã commit hay chưa. Hệ thống định hỗ trợ header **Idempotency-Key**.

**Yêu cầu:**

1. Tính stock sau một và sau hai lần áp dụng thực sự nếu ban đầu stock=10.
2. Thiết kế test hai request **cùng key, cùng payload** và hai request **khác key**.
3. Nêu unique constraint và transaction cần có.
4. Nếu một request đã commit nhưng retry gặp 409 đang xử lý do trạng thái key bị kẹt, client/server phải làm gì?

**Gợi ý đáp án:** Một lần tăng là 13; hai lần thực sự tăng là 16. Cùng logical key không được cập nhật hai lần, còn hai key khác nhau có thể tăng thành 16 nếu đó là hai thao tác hợp lệ. Server cần state machine của idempotency record, cơ chế recovery cho in-progress/timeout và đối soát với hiệu ứng đã commit; **không xóa key đang kẹt rồi chạy lại mù quáng**.

### Bài 3: Trừ kho dưới tải

**Bối cảnh:** còn 5 sản phẩm; 20 khách cùng đặt một sản phẩm, mỗi request dùng key riêng.

**Yêu cầu:**

1. Viết invariant về tồn kho và số đơn được xác nhận.
2. Đề xuất lệnh SQL hoặc locking chống giảm tồn âm.
3. Thiết kế test 20 request đồng thời; kết quả status nào là bình thường?
4. Nếu API chuyển sang nhiều instance, test cần bổ sung điều gì?
5. Nếu một request đã đặt hàng nhưng phản hồi timeout, tại sao cần thêm idempotency?

**Gợi ý đáp án:** Cuối cùng có **5 reservation/đơn hợp lệ tối đa** theo giả định không có hủy, stock cuối 0, không âm, các request còn lại nhận conflict/không đủ hàng theo hợp đồng. Test chạy trên nhiều API instance cùng DB; DB unique/conditional update phải bảo vệ invariant xuyên instance. Idempotency ngăn cùng khách dùng retry tạo đơn thứ hai.

### Bài 4: Trả lời đúng/sai và giải thích

1. “Gửi 1000 request và tất cả trả 2xx chứng minh không có race condition”.
2. “@Transactional tự động ngăn mọi lost update, double booking và write skew”.
3. “Nếu hai PATCH dùng cùng ETag, luôn phải yêu cầu A thắng”.
4. “If-Match bảo vệ điều kiện phiên bản, không thay thế idempotency key”.
5. “Client nhận 412 sau timeout chứng minh request trước đã commit”.
6. “MockMvc là công cụ hữu ích, nhưng chưa thay thế mọi bài test HTTP qua server thật”.
7. “Một API trả 409 cho khách thứ hai trong cuộc đua ghế cuối có thể là hành vi đúng”.
8. “Chỉ kiểm tra số HTTP 201 là đủ chứng minh không double charge”.

**Đáp án:** 1 Sai (phải kiểm tra dữ liệu/invariant); 2 Sai (isolation, locking và ràng buộc còn quan trọng); 3 Sai (không cố định thứ tự thread); 4 Đúng; 5 Sai (có thể do client khác sửa); 6 Đúng; 7 Đúng; 8 Sai (phải xác minh side effect ở thanh toán).

## 20. Các phản mẫu khi kiểm thử cạnh tranh

| Phản mẫu | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Chạy hai request nối tiếp rồi gọi là concurrency test | Không có cửa sổ chồng lấn | Tạo task song song, barrier và test race sâu khi cần |
| Chỉ assert **status 200/412** | DB/event có thể đã sai | Kiểm tra version, giá trị cuối, outbox và downstream |
| Cố định “request A luôn thắng” | Phụ thuộc scheduler, flaky | Assert tập kết quả hợp lệ và invariant |
| Thêm **Thread.sleep** để “sửa race” | Không tạo bảo đảm nguyên tử | Dùng CAS, @Version, lock, constraint, transaction đúng |
| Dùng in-memory mock DB để chứng minh locking production | Semantics DB khác nhau | Tích hợp với engine/isolation sát production |
| Dùng @Transactional ở JUnit rồi gửi HTTP qua server thật | Fixture chưa commit trên thread test | Commit fixture trước khi gọi HTTP |
| Dùng một EntityManager trên nhiều thread | JPA context không thread-safe | Mỗi request/transaction có context riêng |
| Chỉ gửi cùng resource nhưng mỗi request dùng ETag mới | Không tạo tranh chấp trên một version | Dùng ETag ban đầu cho toàn bộ request trong kịch bản |
| Bỏ qua **affected row count** của conditional UPDATE | Request thua có thể bị báo thành công | Phân biệt 0 và 1 hàng cập nhật |
| Bắt mọi optimistic lock exception thành 500 | Client không biết cần đọc lại | Ánh xạ 412 theo hợp đồng conditional write phù hợp |
| Tự retry khi If-Match đã stale | Vi phạm ý định client hoặc retry storm | Trả 412, để client quyết định dựa trên trạng thái mới |
| Dùng correlation ID làm idempotency key | Không có bảo đảm nhận diện thao tác logic | Tách quan sát và chống thực thi trùng |
| Chỉ lưu key trong RAM một API instance | Các instance khác vẫn chạy trùng | Ràng buộc chung có tính nguyên tử ở persistence |
| Trả 201 một lần nên tin chắc không double charge | Side effect ngoài DB có thể thực hiện nhiều lần | Outbox, provider idempotency và đối soát |
| Test chịu tải mà không kiểm invariant | RPS cao che giấu overselling | Assert hậu điều kiện sau tải |
| Test không có timeout/cleanup | CI treo, lock/resource rò rỉ | Timeout, finally, fixture độc lập và dọn dữ liệu |
| Ghi token/payment data vào log để debug race | Rò dữ liệu nhạy cảm | Structured logs với mã lỗi, trace và redaction |

## 21. Checklist trước khi coi API an toàn dưới cạnh tranh

- [ ] Đã viết **invariant nghiệp vụ** cho từng thao tác có thể tranh chấp.
- [ ] Đã phân biệt test tuần tự, test race, load test và retry test.
- [ ] Với cập nhật có điều kiện, hợp đồng mô tả **strong ETag, If-Match, 412, 428** và phương thức HTTP đúng.
- [ ] Đã kiểm tra precondition và thay đổi dữ liệu **nguyên tử**, không chỉ so version ở controller.
- [ ] Đã kiểm tra @Version/conditional UPDATE/unique constraint hoạt động trên database engine production.
- [ ] Test có **ít nhất hai request song song dùng cùng ETag** và không phụ thuộc thứ tự ai thắng.
- [ ] Test kiểm tra **dữ liệu cuối, version và event**, không chỉ HTTP status.
- [ ] Khi cần tái hiện race khó, có barrier/test hook với timeout ở môi trường test cô lập.
- [ ] Transaction fixture được commit trước khi gửi HTTP; test không dùng chung EntityManager giữa thread.
- [ ] Các update nhiều hàng/tài nguyên có test invariant trải trên nhiều hàng.
- [ ] Các thao tác không idempotent có contract và test **Idempotency-Key**, xử lý duplicate in-flight/completed.
- [ ] Có test **mất response sau commit**, retry và không phát sinh side effect trùng.
- [ ] Có test nhiều API instance cùng DB/queue và worker xử lý trùng message khi kiến trúc cần.
- [ ] Authorization/tenant scope vẫn đúng khi hai principal cạnh tranh hoặc dùng key trùng.
- [ ] Lỗi 409/412/428, 4xx/5xx được phân loại đúng, Problem Details không lộ dữ liệu nội bộ.
- [ ] Test có timeout, cleanup, seed/trace và khả năng tái hiện khi fail.
- [ ] Quan sát được optimistic conflicts, deadlock, retries, p95/p99 và vi phạm invariant.
- [ ] Có test cho GET If-None-Match, cache/stale ETag và representation consistency khi writer cập nhật.
- [ ] Có runbook ứng phó khi phát hiện duplicate booking, lost update hoặc payment capture trùng.

## 22. Ghi nhớ và tài liệu tham khảo

**Kiểm thử cạnh tranh bằng nhiều yêu cầu đồng thời** phải chứng minh điều **không được phép xảy ra** đối với trạng thái và tác dụng phụ của API. Hai PATCH với cùng **If-Match** không được cùng ghi đè nhau khi contract yêu cầu optimistic concurrency; một request có thể thắng, request kia nhận **412**. Nhưng chỉ kiểm tra header và status chưa đủ: cơ chế bảo vệ phải được thực thi **nguyên tử tại database**, kết quả cuối phải giữ **invariant**, và mọi side effect bất đồng bộ phải được đối soát.

Hãy nhớ:

1. **If-Match + strong ETag** kiểm soát phiên bản của tài nguyên; **@Version/CAS/transaction** thực thi cạnh tranh tại persistence; **412/428** diễn đạt kết quả theo HTTP.
2. **Idempotency-Key** giúp nhận diện retry của **một thao tác logic**; nó không đồng nghĩa correlation ID hoặc ETag và phải được kiểm tra khi nhiều request cùng key tới đồng thời.
3. **CountDownLatch và nhiều thread** giúp gửi request gần nhau, nhưng muốn tái hiện race khó có thể cần barrier ngay tại cửa sổ transaction. **Test đúng** kiểm tra dữ liệu cuối, event, quyền và side effects, không chỉ 2xx hay throughput.

Tài liệu chuẩn và hướng dẫn:

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): If-Match, If-None-Match, conditional requests, ETag, mã **412** và các phương thức HTTP.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): mã **428 Precondition Required**.
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789): atomicity của PATCH và cách sử dụng conditional requests.
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902): tài liệu patch dạng thao tác và ngữ nghĩa.
- [RFC 7386 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7386): định dạng cập nhật từng phần dạng merge.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): định dạng lỗi có cấu trúc.
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html): cơ chế khóa khi truy cập repository.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction, propagation và giới hạn quản lý transaction.
- [JUnit 5 User Guide](https://docs.junit.org/current/user-guide/): tổ chức kiểm thử tự động.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): mô tả header, request/response và mã lỗi của REST API.
