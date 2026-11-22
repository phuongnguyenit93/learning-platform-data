# Hợp đồng request, response, schema và khả năng tương thích trong Spring Boot Test

## 1. Vì sao API chạy được vẫn có thể phá vỡ khách hàng?

Một ứng dụng Spring Boot cung cấp API đơn hàng. Các unit test của service đều xanh, endpoint trả HTTP 200, database đọc ghi đúng. Nhưng sau một lần deploy, ứng dụng khách cũ lại không hoạt động vì đội backend đã đổi `customerId` thành `customer`, đổi `quantity` từ JSON number sang string, xóa một trường bắt buộc hoặc thay HTTP 404 bằng 200 với body rỗng. Đây là **vi phạm hợp đồng API**, không nhất thiết là lỗi của một hàm Java riêng lẻ.

Một **hợp đồng (contract)** là tập kỳ vọng mà bên gọi (*consumer*) và bên cung cấp (*provider*) cùng dựa vào:

- **Request**: URL/path variable, HTTP method, query parameters, headers, `Content-Type`, `Accept`, authentication, body và các ràng buộc như required/minimum/enum.
- **Response**: HTTP status, headers (`Location`, ETag, content type...), JSON field names/types/required/nullable, body và ý nghĩa của từng mã lỗi.
- **Schema**: biểu diễn có thể máy đọc và kiểm tra được, ví dụ **JSON Schema Draft 2020-12** cho payload, **OpenAPI** cho toàn bộ HTTP interface, Avro/Protobuf schema cho messaging.
- **Khả năng tương thích**: liệu producer phiên bản mới vẫn đáp ứng những consumers đã được hỗ trợ hay không, cả ở mức cấu trúc **và ngữ nghĩa**.
- **Resilience**: khi request timeout, mất mạng, retry hay downstream lỗi, **hợp đồng lỗi và idempotency** vẫn phải nhất quán; test contract không thay thế fault-injection.

**Mục tiêu bài học (ngữ cảnh cha: “Hợp đồng và khả năng phục hồi”):**

1. Chuyển đặc tả HTTP request/response thành những assertions độc lập với implementation.
2. Phân biệt **provider contract test**, **consumer-driven contract (CDC)**, **schema test**, **integration test**, **end-to-end test**.
3. Kiểm method/path, headers, media type, status, response body và schema bằng **MockMvc**.
4. Kiểm body request theo **JSON Schema**, đồng thời chứng minh Spring MVC `@Valid` và Jackson đã enforce các trường hợp quan trọng.
5. Hiểu **required/optional/nullable**, `additionalProperties`, JSON type, enum và tác động khi đổi tên field.
6. Phân biệt **backward compatibility** (consumer cũ đọc được output producer mới) và **forward compatibility** (consumer mới chấp nhận output producer cũ khi dự kiến).
7. Kiểm một **field response tùy chọn được thêm** không làm hỏng consumer V1, nhưng việc xóa `id`, đổi `quantity` sang string hoặc xuất hiện enum value lạ có thể phá contract.
8. Thấy rõ vì sao **thêm request field** có thể gây lỗi nếu server cũ dùng strict deserialization, và vì sao **đổi requiredness** là thay đổi nguy hiểm.
9. Viết một project **Java 17 + Spring Boot 3.3.5 + Gradle** có controller/service/fixture và các JSON Schema versioned.
10. Dùng **JSON Schema validator thực** để test schema, không nhầm vài `jsonPath` assertions với kiểm đầy đủ Schema Draft.
11. Kiểm **ProblemDetail/RFC 9457** của lỗi 400/404 và việc không rò stack trace/dữ liệu nhạy cảm.
12. Thiết kế CI publish/verifier cho contract, Pact hoặc Spring Cloud Contract, OpenAPI diff, versioning và deprecation policy.
13. Tách rõ điều đã chứng minh trong MockMvc và điều cần HTTP transport/database/consumer tests bổ sung.

**Phiên bản cố định:** Java 17; **Spring Boot 3.3.5** (Spring Framework 6.1/Spring MVC); Jackson 2; JUnit Jupiter; JSON Schema Draft 2020-12; `com.networknt:json-schema-validator:1.5.9` dùng trong **test scope**. Đây là mã dùng **Boot 3.3**; Spring Boot 4 có package/module và Jackson default khác, phải đối chiếu lại khi nâng cấp.

## 2. Hợp đồng cụ thể của API ví dụ

API quản lý một tập đơn hàng giả lập, không kết nối database hoặc gửi HTTP ra ngoài:

| Thao tác | Request | Response hợp lệ | Lỗi chủ đạo |
|---|---|---|---|
| Đọc một đơn | `GET /api/v1/orders/{id}`; `Accept: application/json` | `200 OK`, `Content-Type: application/json`, `X-Contract-Version: 1`, JSON order | `404`, `application/problem+json` khi không có ID |
| Tạo đơn | `POST /api/v1/orders`; `Content-Type: application/json` | `201 Created`, `Location: /api/v1/orders/{id}`, `X-Contract-Version: 1`, JSON order | `400` validation/malformed, `415` media type sai |
| JSON request | `customerId` string không rỗng/không toàn whitespace; `quantity` integer >= 1 | Các trường không khai báo bị từ chối theo chính sách **strict input** của ví dụ | `400`, ProblemDetail |
| JSON response | `id`, `customerId`, `quantity`, `status` **bắt buộc** | Trạng thái `NEW` hoặc `SHIPPED`; `deliveryNote` **tùy chọn** | Không tự ý đổi field/type/status |
| `deliveryNote` | **Không bắt buộc** | Có thể bổ sung string khi đơn có ghi chú, hoặc **vắng mặt** | Không được biến thành required cho consumer cũ |

**Request mẫu:**

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json
Accept: application/json

{"customerId":"cust-a","quantity":2}
~~~

**Response mẫu:**

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/v1/orders/ord-201
X-Contract-Version: 1

{"id":"ord-201","customerId":"cust-a","quantity":2,"status":"NEW"}
~~~

**Lỗi không tồn tại:**

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Order not found",
  "errorCode": "ORDER_NOT_FOUND"
}
~~~

Đoạn lỗi trên minh họa các trường tối thiểu của contract. Spring có thể thêm `instance` trong trường hợp cụ thể; schema lỗi của project cho phép trường đó hoặc metadata được duyệt. Không assert nguyên chuỗi raw JSON theo thứ tự thuộc tính, khoảng trắng hoặc tên boundary.

**Tại sao status 201 quan trọng?** Một consumer có thể chỉ retry/đọc `Location` khi nhận 201. Thay 201 thành 200 dù body vẫn đúng là một thay đổi hành vi quan sát được. **Tại sao header quan trọng?** Content-Type quyết định parser, Location là đường dẫn tài nguyên vừa tạo, còn X-Contract-Version là metadata riêng của ví dụ; header này không thay thế chính sách versioning.

## 3. Bốn tầng kiểm thử khác nhau

| Tầng | Ai định nghĩa kỳ vọng? | Bằng chứng | Giới hạn |
|---|---|---|---|
| Unit test service | Lập trình viên của provider | Xử lý nghiệp vụ/validation thuần Java | Không biết HTTP serialization/status |
| **Provider HTTP test (MockMvc)** | Hợp đồng HTTP được kiểm trong provider repo | Spring MVC mapping, Jackson, validation, status, header, body | Không có TCP, TLS, proxy, DNS |
| **Schema validation** | JSON Schema/OpenAPI được quản lý | Payload tuân kiểu/required/enum/range | Không tự kiểm nghĩa nghiệp vụ hay HTTP headers |
| **Consumer-driven contract** | Consumer yêu cầu provider đáp ứng một số interactions | Provider verify contract trên các provider states, stub cho consumer | Không tự chứng minh mọi integration/network edge case |
| Integration với HTTP server thật | API chạy qua socket và HTTP client thật | Transport, filters, URL, serializer, đôi khi DB | Tốn chi phí môi trường hơn |
| End-to-end với consumer thật | Hai hệ thống phối hợp | Compatibility thực tại runtime | Flaky, chậm, phụ thuộc dữ liệu/infra |

**MockMvc là mock servlet request/response ở JVM**, không tự chạy embedded Tomcat qua một TCP port. Nó rất phù hợp để giữ hợp đồng controller ổn định trong CI. Nếu cần test connection pooling/TLS/redirect/cookie proxy/client SDK, bổ sung `@SpringBootTest(webEnvironment = RANDOM_PORT)` + client thực.

**“API documentation” không bằng “contract enforcement”.** Có một OpenAPI YAML đẹp nhưng tests vẫn mock toàn bộ controller có thể không phát hiện provider trả field sai. Để hữu ích, hợp đồng phải được **gắn vào automated verification**. Đừng chỉ tạo một snapshot output rồi cập nhật snapshot mỗi khi thay code mà không hỏi có consumer nào bị phá vỡ hay không.

## 4. Backward/forward compatibility: định nghĩa bằng người đọc dữ liệu

**Backward compatibility (hướng provider):** Provider mới P2 vẫn phục vụ những consumer P1 được cam kết hỗ trợ. Ví dụ response mới có thêm `deliveryNote` *tùy chọn*, nhưng vẫn giữ `id`, `customerId`, `quantity`, `status` đúng kiểu và nghĩa. Một consumer được thiết kế để **bỏ qua response fields không biết** có thể tiếp tục hoạt động.

**Forward compatibility (hướng reader/consumer):** Một consumer mới C2 có thể đọc dữ liệu do provider cũ P1 tạo ra khi chính sách yêu cầu. Muốn vậy, C2 không được bắt buộc một response field chỉ có ở P2, trừ khi có default/fallback được mô tả.

**Lưu ý không đối xứng:** Đối với **response**, thêm một optional field thường an toàn nếu consumers bỏ qua unknown properties; đối với **request**, thêm một unknown field vào payload mà **server cũ strict** có thể khiến server trả 400. “Additive = luôn tương thích” là kết luận sai.

| Thay đổi | Consumer cũ có thể gặp gì? | Chính sách/khuyến nghị |
|---|---|---|
| Thêm optional response field | Thường an toàn nếu reader tolerant | Kiểm bằng contract consumer thực |
| Thêm response field bắt buộc từ phía consumer mới | Provider cũ không có field đó | Dùng fallback hoặc version mới |
| Xóa/đổi tên field response bắt buộc | Consumer cũ không tìm thấy key | **Breaking** |
| Đổi `quantity: 2` thành `"2"` | JSON number → string | **Breaking**, dù UI cùng hiển thị “2” |
| Đổi `status: NEW` thành `READY` | Enum unknown | Có thể breaking, tùy consumer tolerance |
| `null` thay vì field vắng mặt | Parser/validation có thể khác | Cần contract về nullable/optional |
| Thay 201 bằng 200 | Consumer có thể branch theo status | Có thể **breaking** |
| Đổi `Location` hoặc media type | Consumer parsing/follow-up request sai | Có thể **breaking** |
| Thêm optional request field | Server cũ strict có thể trả 400 | Kiểm policy của provider |
| Thêm required request field ở server mới | Client cũ không gửi | **Breaking** |
| Đổi query param optional thành required | Client cũ thiếu param | **Breaking** |
| Thu hẹp error codes/status | Consumer error handling bị khác | Review compatibility |
| Tăng/giảm timeout hoặc rate limits | Ảnh hưởng runtime/retry | Kiểm resilience contract ngoài schema |

**Open-world và closed-world:** Với response schema phục vụ consumer V1, bài dùng `additionalProperties: true` để consumer có thể bỏ qua future optional fields. Với **request schema strict**, bài dùng `additionalProperties: false` để không vô tình chấp nhận các trường chưa có trong contract (chính sách này có thể đánh đổi forward compatibility). Với schema provider V2, bài dùng `additionalProperties: false` để kiểm output của implementation không vô tình leak field; không nên tự động áp chính sách strict đó cho mọi consumer.

**Mức tương thích là hợp đồng, không phải “hợp lệ về cú pháp JSON”.** Ví dụ `status` vẫn là string nhưng đổi từ NEW thành READY thì JSON hợp lệ, song consumer có `switch` chỉ xử lý NEW/SHIPPED có thể lỗi. Enum schema và test nghĩa nghiệp vụ giúp bắt thay đổi này.

## 5. JSON Schema Draft 2020-12: những keyword thiết yếu

Ví dụ JSON Schema cho response V1:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "customerId", "quantity", "status"],
  "properties": {
    "id": {"type": "string", "minLength": 1},
    "customerId": {"type": "string", "minLength": 1},
    "quantity": {"type": "integer", "minimum": 1},
    "status": {"type": "string", "enum": ["NEW", "SHIPPED"]}
  },
  "additionalProperties": true
}
~~~

- **`required`**: key phải tồn tại. Không nói key được phép null hay không; muốn cấm null, `type` phải không bao gồm `"null"`.
- **`type`**: kiểm JSON string/integer/number/boolean/object/array/null; `2` và `"2"` **khác kiểu**.
- **`enum`**: đóng tập giá trị hỗ trợ; thêm value mới có thể phá consumer dựa vào enum kín.
- **`minimum`**, **`minLength`**, **`pattern`**, **`format`**: ràng buộc tương ứng. `format` trong JSON Schema Draft 2020-12 có semantics annotation/assertion theo vocabulary/cấu hình validator; không suy rằng mọi email/URI luôn được kiểm sâu chỉ vì có `"format": "email"`.
- **`additionalProperties`**: kiểm các keys không liệt kê. Với output consumer tolerant có thể `true`; với API response provider cần tránh leak fields có thể dùng `false` ở schema dành cho phiên bản chính xác.
- **`oneOf`**, **`anyOf`**, **`allOf`**, **`$ref`**, **`$defs`**: hữu ích khi schema có variants/union/discriminator. Test phải phân biệt biến thể để consumer không hiểu nhầm.
- **`deprecated`**, **`default`**, **`readOnly`**, **`writeOnly`**: các annotation/vocabulary hữu ích, nhưng **`default` của JSON Schema không tự điền giá trị vào payload** trong mọi validator. Không phụ thuộc vào default nếu không có layer transformation rõ ràng.

**Nullable vs optional:**

~~~json
{
  "type": "object",
  "properties": {
    "deliveryNote": {
      "type": ["string", "null"]
    }
  }
}
~~~

Trong schema này `deliveryNote` **có thể vắng**, hoặc xuất hiện với string **hoặc null**, vì key không nằm trong `required`. Nếu schema là `"type": "string"` nhưng Java trả `null`, validator phải reject khi key xuất hiện. Ví dụ runnable chủ động bỏ `deliveryNote` khi null bằng Jackson `@JsonInclude(NON_NULL)`, và **không cho xuất hiện với null** trong response V2 schema.

### 5.1. Mốc phiên bản và thư viện validator

Bài kiểm JSON Schema bằng **networknt json-schema-validator 1.5.9**, dùng `JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012)`, `getSchema(InputStream)` và `validate(JsonNode)`. Đây là nhánh **Jackson 2** phù hợp Spring Boot 3.3.x. Khi dùng Spring Boot 4 với Jackson 3, phải chọn nhánh validator tương thích; không trộn package `com.fasterxml.jackson` và `tools.jackson`.

**Vì sao cần validator riêng?** `MockMvcResultMatchers.jsonPath("$.id").exists()` không kiểm được toàn bộ `required`, `enum`, `additionalProperties` hay nested arrays. `content().json(expected)` kiểm một JSON mẫu, nhưng không tự biến mẫu thành **một schema có các ràng buộc**. Hai loại assertions có thể bổ trợ nhau.

## 6. Project runnable: Spring Boot 3.3.5, Jackson, MockMvc, JSON Schema

Project sử dụng một in-memory repository để kiểm toàn bộ đường HTTP mà không cần database/Docker. Nó chứa:
- Endpoint GET/POST với version path `/api/v1`.
- DTO Java 17 records, `@Valid` Bean Validation và strict Jackson request settings.
- `ProblemDetail` có errorCode ổn định cho 400/404.
- JSON Schema cho **response V1**, **response V2 additive**, **request strict** và **ProblemDetail**.
- Tests MVC và tests tương thích schema; không dùng snapshot kiểu “update expected JSON cho khớp code mới”.

**Cây thư mục:**

~~~text
settings.gradle
build.gradle
src/main/resources/application.properties
src/main/java/demo/contract/ContractDemoApplication.java
src/main/java/demo/contract/CreateOrderRequest.java
src/main/java/demo/contract/OrderView.java
src/main/java/demo/contract/OrderRepository.java
src/main/java/demo/contract/OrderService.java
src/main/java/demo/contract/OrdersController.java
src/main/java/demo/contract/ContractErrorAdvice.java
src/test/resources/contracts/order-v1.json
src/test/resources/contracts/order-v2.json
src/test/resources/contracts/create-order.json
src/test/resources/contracts/problem.json
src/test/java/demo/contract/ContractSchemas.java
src/test/java/demo/contract/OrdersHttpContractTest.java
src/test/java/demo/contract/SchemaCompatibilityTest.java
~~~

### 6.1. Gradle và settings

**settings.gradle**

~~~groovy
rootProject.name = 'spring-api-contract-check'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.networknt:json-schema-validator:1.5.9'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Giải thích dependencies:**
- `starter-web`: Spring MVC, HTTP converters, Jackson 2 và servlet tests.
- `starter-validation`: Jakarta Bean Validation/Hibernate Validator để `@Valid` trên request DTO phát hiện thiếu hoặc sai constraints.
- `starter-test`: JUnit Jupiter, Spring Test và MockMvc.
- `json-schema-validator:1.5.9`: **test-only** JSON Schema Draft 2020-12 validator. Nó không tự động chặn HTTP request production; `@Valid` và Jackson vẫn phải xử lý request thật.
- Spring Boot dependency management cung cấp Spring Framework/Jackson versions tương thích. Thư viện schema 1.5.9 là version cố định cho ví dụ; khi chạy security scans CI cần áp dụng chính sách dependency updates.

### 6.2. Jackson strict request policy

**src/main/resources/application.properties**

~~~properties
spring.jackson.deserialization.fail-on-unknown-properties=true
spring.jackson.mapper.allow-coercion-of-scalars=false
~~~

Hai dòng tạo một **policy có chủ đích**:
1. Unknown fields trong request object không được âm thầm bỏ qua.
2. Jackson không tự chuyển `"2"` thành số nguyên `2` ở trường Integer bằng scalar coercion.

Với Spring Boot 3.3, các `spring.jackson.deserialization.*` và `spring.jackson.mapper.*` properties ánh xạ vào các Jackson enums tương ứng. Cần kiểm lại binding khi đổi major version.

**Đánh đổi:** strict request giúp phát hiện client gửi key sai/typo và giữ schema input chặt, nhưng có thể **làm giảm forward compatibility** với client mới gửi field tùy chọn mà server cũ không biết. Đây là quyết định contract, không phải một “best practice vô điều kiện”. Nếu API có policy tolerant request, phải thay cấu hình và tests đồng bộ, không chỉ sửa kỳ vọng 400 thành 201 cho test xanh.

**Không áp dụng strict unknown field lên response consumer** một cách máy móc. Trong test consumer cũ, ta dùng `@JsonIgnoreProperties(ignoreUnknown=true)` rõ ràng, vì reader của response được kỳ vọng bỏ qua trường bổ sung.

### 6.3. Main class

**src/main/java/demo/contract/ContractDemoApplication.java**

~~~java
package demo.contract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContractDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ContractDemoApplication.class, args);
    }
}
~~~

### 6.4. Request DTO và response DTO

**src/main/java/demo/contract/CreateOrderRequest.java**

~~~java
package demo.contract;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @NotNull @Positive Integer quantity) {
}
~~~

**src/main/java/demo/contract/OrderView.java**

~~~java
package demo.contract;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record OrderView(
        String id,
        String customerId,
        int quantity,
        String status,
        String deliveryNote) {
}
~~~

`CreateOrderRequest` không có `id` hay `status` để client tự ghi; server tạo các trường đó. `@NotBlank` chặn `null`, chuỗi rỗng và chuỗi toàn whitespace; `@NotNull @Positive` yêu cầu quantity có và lớn hơn 0. Nếu JSON quantity là string, strict Jackson setting sẽ chặn trước Bean Validation.

`OrderView` là **response DTO**, không phải JPA entity. `@JsonInclude(NON_NULL)` làm `deliveryNote` **vắng mặt** khi null — phân biệt với xuất hiện `deliveryNote:null`. Field `status` là String để bài học có thể minh họa thay đổi enum; thực tế có thể dùng Java enum, nhưng hợp đồng JSON vẫn phải mô tả các giá trị công bố.

### 6.5. In-memory repository có dữ liệu cố định

**src/main/java/demo/contract/OrderRepository.java**

~~~java
package demo.contract;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Repository;

@Repository
public class OrderRepository {

    private final ConcurrentMap<String, OrderView> rows =
            new ConcurrentHashMap<>();

    private final AtomicLong sequence = new AtomicLong(200);

    public OrderRepository() {
        reset();
    }

    public void reset() {
        rows.clear();
        rows.put(
                "ord-100",
                new OrderView(
                        "ord-100", "cust-a", 2, "NEW", null));

        rows.put(
                "ord-101",
                new OrderView(
                        "ord-101",
                        "cust-b",
                        3,
                        "SHIPPED",
                        "Giao sau 17 giờ"));

        sequence.set(200);
    }

    public Optional<OrderView> findById(String id) {
        return Optional.ofNullable(rows.get(id));
    }

    public OrderView create(CreateOrderRequest request) {
        String id = "ord-" + sequence.incrementAndGet();

        OrderView result = new OrderView(
                id,
                request.customerId(),
                request.quantity(),
                "NEW",
                null);

        rows.put(id, result);
        return result;
    }
}
~~~

Repository giữ hai fixtures: `ord-100` là response V1 chỉ có bốn fields bắt buộc; `ord-101` có thêm `deliveryNote` string. Việc bổ sung optional field **không đổi path `/api/v1`** vì ví dụ muốn kiểm **backward-compatible additive change** trong cùng major contract.

`reset()` được test gọi `@BeforeEach` để mỗi test khởi đầu với hai orders và sequence=200. Đây là singleton in-memory test fixture, **không thay thế database transaction test**. Lớp JUnit không chạy methods song song; nếu project thực dùng DB cần `@Sql`, transaction rollback hoặc disposable Testcontainers database.

### 6.6. Service và lỗi domain

**src/main/java/demo/contract/OrderService.java**

~~~java
package demo.contract;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderView read(String id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new OrderNotFoundException(id));
    }

    public OrderView create(CreateOrderRequest request) {
        return repository.create(request);
    }
}

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(String id) {
        super("Order not found");
    }
}
~~~

Class `OrderNotFoundException` ở cuối **cùng file Java** là package-private, hợp lệ với Java. Exception message không in ID nhằm giữ error body ổn định và không rò dữ liệu tùy ý; observability production có thể ghi correlation ID/trace ID an toàn ở log nội bộ. Không bọc exception thành `200 OK` với dữ liệu rỗng nếu contract đã công bố `404`.

### 6.7. Controller: status/header/path đều là contract

**src/main/java/demo/contract/OrdersController.java**

~~~java
package demo.contract;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(
        path = "/api/v1/orders",
        produces = MediaType.APPLICATION_JSON_VALUE)
public class OrdersController {

    private final OrderService service;

    public OrdersController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderView> get(
            @PathVariable String id) {

        return ResponseEntity.ok()
                .header("X-Contract-Version", "1")
                .body(service.read(id));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderRequest request) {

        OrderView created = service.create(request);

        return ResponseEntity
                .created(URI.create(
                        "/api/v1/orders/" + created.id()))
                .header("X-Contract-Version", "1")
                .body(created);
    }
}
~~~

**Những điểm đáng test:**
- `GET` trả 200 và `X-Contract-Version=1`, không trả 201.
- `POST` trả **201 Created** và `Location` trỏ đúng ID mới.
- `@RequestBody @Valid` bảo vệ các constraints của DTO.
- `consumes=application/json` từ chối media type không được công bố.
- `produces=application/json` giúp Content Negotiation cho GET/POST; `Accept: application/xml` sẽ không phù hợp.
- Không viết query/headers vào những trường mà hợp đồng không định nghĩa; nếu thêm chúng sau này, phải làm rõ required/optional.
- URI trả từ `Location` là **relative path** trong ví dụ. Trong production API có thể công bố absolute URL; nếu vậy phải test scheme/host/proxy forwarding đúng theo contract.

Không tạo hoặc mock HTTP client bên ngoài: các tests chạy **controller + service + repository thật trong JVM**, giúp bắt serialization mismatch giữa Java record và JSON Schema.

### 6.8. ProblemDetail: hợp đồng lỗi ổn định

**src/main/java/demo/contract/ContractErrorAdvice.java**

~~~java
package demo.contract;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ContractErrorAdvice {

    private ProblemDetail problem(
            HttpStatus status,
            String title,
            String detail,
            String errorCode) {

        ProblemDetail value = ProblemDetail
                .forStatusAndDetail(status, detail);

        value.setTitle(title);
        value.setProperty("errorCode", errorCode);
        return value;
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ProblemDetail missing() {
        return problem(
                HttpStatus.NOT_FOUND,
                "Not Found",
                "Order not found",
                "ORDER_NOT_FOUND");
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ProblemDetail invalidRequest() {
        return problem(
                HttpStatus.BAD_REQUEST,
                "Bad Request",
                "Request validation failed",
                "VALIDATION_FAILED");
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ProblemDetail unreadableRequest() {
        return problem(
                HttpStatus.BAD_REQUEST,
                "Bad Request",
                "Request body is invalid",
                "MALFORMED_JSON");
    }
}
~~~

Trong Spring Framework 6.1, `ProblemDetail` hỗ trợ standardized error body (RFC 9457), còn custom `errorCode` được Jackson serialize thành top-level property qua Spring integration. Vì mỗi exception có **status + title + errorCode**, consumers không cần đoán lỗi dựa vào text message vốn có thể được địa phương hóa.

**Không trả raw exception message/stack trace cho consumer.** Đặc biệt với lỗi deserialize, original JSON có thể chứa PII/token; body “Request body is invalid” giữ contract và giới hạn lộ dữ liệu. Lỗi `415 Unsupported Media Type`/`406 Not Acceptable` do Spring MVC xử lý mặc định trong demo; bài chỉ assert status cho những tình huống đó, **không khẳng định cùng errorCode schema** nếu chưa viết handler tương ứng.

## 7. Các JSON Schema được lưu và versioned như mã nguồn

### 7.1. Response V1: consumer chấp nhận field bổ sung

**src/test/resources/contracts/order-v1.json**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Order response contract V1 - tolerant reader",
  "type": "object",
  "required": ["id", "customerId", "quantity", "status"],
  "properties": {
    "id": {"type": "string", "minLength": 1},
    "customerId": {"type": "string", "minLength": 1},
    "quantity": {"type": "integer", "minimum": 1},
    "status": {"type": "string", "enum": ["NEW", "SHIPPED"]}
  },
  "additionalProperties": true
}
~~~

V1 schema chủ động không liệt kê `deliveryNote` nhưng **cho phép** additional fields để consumer cũ có thể bỏ qua optional additions. Đây là **một consumer-tolerant contract**, không phải lệnh cho provider tự do gửi secret fields; provider vẫn phải kiểm những thông tin được phép công bố.

### 7.2. Response V2: optional field, output provider nghiêm ngặt

**src/test/resources/contracts/order-v2.json**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Order response contract V2",
  "type": "object",
  "required": ["id", "customerId", "quantity", "status"],
  "properties": {
    "id": {"type": "string", "minLength": 1},
    "customerId": {"type": "string", "minLength": 1},
    "quantity": {"type": "integer", "minimum": 1},
    "status": {"type": "string", "enum": ["NEW", "SHIPPED"]},
    "deliveryNote": {"type": "string", "maxLength": 120}
  },
  "additionalProperties": false
}
~~~

**V2 không bắt `deliveryNote` phải có**, nên response V1 chỉ có bốn fields vẫn hợp lệ theo V2 schema. Ngược lại, khi `deliveryNote` có mặt, nó **phải là string**, không phải null hay number. `additionalProperties:false` giúp test output provider V2 phát hiện việc thêm field ngoài contract như `debugToken`, nhưng consumer V1 vẫn có thể chấp nhận extras.

**Tên V1/V2 trong hai file schema là những mốc contract để test**, không hàm ý project có hai endpoints `/api/v1` và `/api/v2`. Ví dụ muốn chứng minh **một thay đổi additive trong cùng đường API**, không triển khai version routing riêng.

### 7.3. Strict JSON request

**src/test/resources/contracts/create-order.json**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Create order request contract",
  "type": "object",
  "required": ["customerId", "quantity"],
  "properties": {
    "customerId": {
      "type": "string",
      "minLength": 1,
      "pattern": "\\S"
    },
    "quantity": {
      "type": "integer",
      "minimum": 1
    }
  },
  "additionalProperties": false
}
~~~

`pattern:"\\S"` trong JSON biểu diễn regex `\S` — yêu cầu ít nhất một ký tự không phải whitespace. Trong demo, `@NotBlank` là **validation thực của server**, còn JSON Schema là **test contract**; chúng không được tự động đồng bộ bởi Spring Boot. Khi thay DTO validation, tests schema và HTTP validation cần phát hiện sự không đồng bộ.

### 7.4. ProblemDetail JSON

**src/test/resources/contracts/problem.json**

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Application ProblemDetail contract",
  "type": "object",
  "required": ["type", "title", "status", "detail", "errorCode"],
  "properties": {
    "type": {"type": "string"},
    "title": {"type": "string", "minLength": 1},
    "status": {"type": "integer", "minimum": 400, "maximum": 599},
    "detail": {"type": "string"},
    "instance": {"type": "string"},
    "errorCode": {
      "type": "string",
      "enum": [
        "ORDER_NOT_FOUND",
        "VALIDATION_FAILED",
        "MALFORMED_JSON"
      ]
    }
  },
  "additionalProperties": true
}
~~~

Schema này giữ required fields/errorCode, cho phép optional `instance` và những extensions được kiểm soát. Nếu error response của provider bỏ `errorCode`, status từ 404 thành 200 hoặc `status` thành string, test fail. **Không nhất thiết mọi 4xx của Spring Boot phải theo schema này**: chỉ những lỗi có handler được mô tả mới được công bố trong ví dụ.

### 7.5. Schema file là artifact của hợp đồng, không chỉ là fixture

Đặt schema cạnh tests là bước đầu; trong dự án nhiều đội, nên quản lý:
- Ownership/approvals khi đổi contract.
- Versioning và changelog.
- Publication vào artifact registry, OpenAPI portal hoặc Pact broker.
- Dải consumer versions cần hỗ trợ (N, N−1...).
- CI verify provider implementation với **tất cả contracts còn đang sử dụng**, không chỉ contract vừa update.
- Quy định deprecation và sunset khi một breaking change là bắt buộc.

Nếu chỉ giữ schema trên một nhánh mới, consumer đang chạy production có thể chưa từng thấy thay đổi. Contract tests cần hoạt động như **compatibility gate**, không chỉ là tài liệu.

## 8. Helper thật để kiểm JSON Schema

**src/test/java/demo/contract/ContractSchemas.java**

~~~java
package demo.contract;

import java.io.IOException;
import java.io.InputStream;
import java.util.Set;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;

import org.springframework.core.io.ClassPathResource;

import static org.junit.jupiter.api.Assertions.*;

final class ContractSchemas {

    private static final JsonSchemaFactory FACTORY =
            JsonSchemaFactory.getInstance(
                    SpecVersion.VersionFlag.V202012);

    private static final ObjectMapper MAPPER =
            new ObjectMapper();

    private ContractSchemas() {
    }

    static JsonSchema schema(String filename) throws IOException {
        var resource = new ClassPathResource(
                "contracts/" + filename);

        try (InputStream stream = resource.getInputStream()) {
            return FACTORY.getSchema(stream);
        }
    }

    static Set<ValidationMessage> errors(
            JsonSchema schema, String json) throws Exception {

        JsonNode node = MAPPER.readTree(json);
        return schema.validate(node);
    }

    static void assertValid(
            JsonSchema schema, String json) throws Exception {

        Set<ValidationMessage> errors = errors(schema, json);

        assertTrue(
                errors.isEmpty(),
                () -> "Schema mismatches: " + errors);
    }

    static void assertInvalid(
            JsonSchema schema, String json) throws Exception {

        Set<ValidationMessage> errors = errors(schema, json);

        assertFalse(
                errors.isEmpty(),
                "An incompatible payload unexpectedly matches schema");
    }
}
~~~

Helper này **không viết lại một validator thủ công**. Nó dùng thư viện `com.networknt` để đọc schema JSON từ classpath và validate một Jackson `JsonNode`. `assertValid` yêu cầu **0 mismatches**; `assertInvalid` được dùng trong negative compatibility tests để kiểm thay đổi phá schema.

Một điều cần phân biệt: **JSON Schema validate dữ liệu JSON**, không kiểm HTTP method/status/header. Do đó tests HTTP ở mục 9 luôn kết hợp `MockMvcResultMatchers.status/header/content` với `ContractSchemas.assertValid(...)`. Không dùng `assertInvalid` để biến lỗi của provider production thành “PASS” ngoài ý đồ: negative test chỉ kiểm một fixture cố ý sai **đúng là bị schema từ chối**.

## 9. Lớp integration test HTTP: request, response, lỗi và compatibility

**src/test/java/demo/contract/OrdersHttpContractTest.java**

~~~java
package demo.contract;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.JsonSchema;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Execution(ExecutionMode.SAME_THREAD)
class OrdersHttpContractTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    OrderRepository repository;

    @BeforeEach
    void freshState() {
        repository.reset();
    }

    private String json(MvcResult result) {
        return result.getResponse()
                .getContentAsString(StandardCharsets.UTF_8);
    }

    private MvcResult create(String payload) throws Exception {
        return mvc.perform(post("/api/v1/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andReturn();
    }

    private JsonSchema v1() throws Exception {
        return ContractSchemas.schema("order-v1.json");
    }

    @Test
    void getChecksMethodPathStatusMediaTypeHeaderAndV1Schema()
            throws Exception {

        MvcResult result = mvc.perform(
                        get("/api/v1/orders/ord-100")
                                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        "X-Contract-Version", "1"))
                .andExpect(jsonPath("$.id").value("ord-100"))
                .andExpect(jsonPath("$.customerId").value("cust-a"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(jsonPath("$.status").value("NEW"))
                .andReturn();

        ContractSchemas.assertValid(v1(), json(result));

        // Chưa có optional note: field phải vắng, không phải null.
        assertFalse(
                mapper.readTree(json(result)).has("deliveryNote"));
    }

    @Test
    void additiveOptionalResponseFieldStillMatchesV1()
            throws Exception {

        MvcResult result = mvc.perform(
                        get("/api/v1/orders/ord-101")
                                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SHIPPED"))
                .andExpect(jsonPath("$.deliveryNote")
                        .value("Giao sau 17 giờ"))
                .andReturn();

        ContractSchemas.assertValid(v1(), json(result));
        ContractSchemas.assertValid(
                ContractSchemas.schema("order-v2.json"),
                json(result));
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    private record LegacyOrderReader(
            String id,
            String customerId,
            int quantity,
            String status) {
    }

    @Test
    void legacyConsumerCanDeserializeNewOptionalField()
            throws Exception {

        MvcResult result = mvc.perform(
                        get("/api/v1/orders/ord-101"))
                .andExpect(status().isOk())
                .andReturn();

        LegacyOrderReader legacy = mapper.readValue(
                json(result), LegacyOrderReader.class);

        assertEquals("ord-101", legacy.id());
        assertEquals("cust-b", legacy.customerId());
        assertEquals(3, legacy.quantity());
        assertEquals("SHIPPED", legacy.status());
    }

    @Test
    void missingOrderHas404AndStableProblemContract()
            throws Exception {

        MvcResult result = mvc.perform(
                        get("/api/v1/orders/not-here"))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.valueOf("application/problem+json")))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.errorCode")
                        .value("ORDER_NOT_FOUND"))
                .andReturn();

        ContractSchemas.assertValid(
                ContractSchemas.schema("problem.json"),
                json(result));

        assertFalse(json(result).contains("Exception"));
    }

    @Test
    void postValidRequestHas201LocationHeaderAndResponseSchema()
            throws Exception {

        String request =
                "{\"customerId\":\"cust-a\",\"quantity\":2}";

        ContractSchemas.assertValid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = mvc.perform(
                        post("/api/v1/orders")
                                .contentType(MediaType.APPLICATION_JSON)
                                .accept(MediaType.APPLICATION_JSON)
                                .content(request))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "Location", "/api/v1/orders/ord-201"))
                .andExpect(header().string(
                        "X-Contract-Version", "1"))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value("ord-201"))
                .andExpect(jsonPath("$.status").value("NEW"))
                .andReturn();

        ContractSchemas.assertValid(v1(), json(result));

        mvc.perform(get("/api/v1/orders/ord-201"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void postMissingCustomerIdReturnsValidationProblem()
            throws Exception {

        String request = "{\"quantity\":2}";

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());

        ContractSchemas.assertValid(
                ContractSchemas.schema("problem.json"),
                json(result));

        assertEquals(
                "VALIDATION_FAILED",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void postBlankCustomerIdReturns400()
            throws Exception {

        String request =
                "{\"customerId\":\"   \",\"quantity\":2}";

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "VALIDATION_FAILED",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void postQuantityZeroReturns400()
            throws Exception {

        String request =
                "{\"customerId\":\"cust-a\",\"quantity\":0}";

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "VALIDATION_FAILED",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void postNullQuantityReturns400()
            throws Exception {

        String request =
                "{\"customerId\":\"cust-a\",\"quantity\":null}";

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "VALIDATION_FAILED",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void postStringQuantityIsRejectedBySchemaAndJackson()
            throws Exception {

        String request =
                "{\"customerId\":\"cust-a\",\"quantity\":\"2\"}";

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "MALFORMED_JSON",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void postUnknownFieldIsRejectedByStrictInputPolicy()
            throws Exception {

        String request = """
                {
                  "customerId":"cust-a",
                  "quantity":2,
                  "adminOverride":true
                }
                """;

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                request);

        MvcResult result = create(request);

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "MALFORMED_JSON",
                mapper.readTree(json(result))
                        .path("errorCode").asText());
    }

    @Test
    void malformedJsonDoesNotProduceSuccess()
            throws Exception {

        MvcResult result = create(
                "{\"customerId\":\"cust-a\",\"quantity\":");

        assertEquals(400, result.getResponse().getStatus());
        assertEquals(
                "MALFORMED_JSON",
                mapper.readTree(json(result))
                        .path("errorCode").asText());

        mvc.perform(get("/api/v1/orders/ord-201"))
                .andExpect(status().isNotFound());
    }

    @Test
    void postWrongMediaTypeReturns415()
            throws Exception {

        mvc.perform(post("/api/v1/orders")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("customerId=cust-a&quantity=2"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void getUnacceptableAcceptMediaTypeReturns406()
            throws Exception {

        mvc.perform(get("/api/v1/orders/ord-100")
                        .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }

    @Test
    void wrongPathDoesNotMatchPublishedEndpoint()
            throws Exception {

        mvc.perform(get("/api/v1/order/ord-100"))
                .andExpect(status().isNotFound());
    }

    @Test
    void repeatedValidPostsCreateDistinctLocations()
            throws Exception {

        MvcResult first = create(
                "{\"customerId\":\"cust-a\",\"quantity\":1}");

        MvcResult second = create(
                "{\"customerId\":\"cust-b\",\"quantity\":3}");

        assertEquals(201, first.getResponse().getStatus());
        assertEquals(201, second.getResponse().getStatus());

        assertEquals(
                "/api/v1/orders/ord-201",
                first.getResponse().getHeader("Location"));
        assertEquals(
                "/api/v1/orders/ord-202",
                second.getResponse().getHeader("Location"));

        ContractSchemas.assertValid(v1(), json(first));
        ContractSchemas.assertValid(v1(), json(second));

        mvc.perform(get("/api/v1/orders/ord-202"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customerId")
                        .value("cust-b"));
    }
}
~~~

**Đếm chính xác: 16 phương thức `@Test` trong lớp này.** `@BeforeEach` reset repository, helper `create`, `v1`, `json` và nested record `LegacyOrderReader` không phải JUnit tests. Tests chỉ thao tác trong application context sandbox; không cần DB hoặc server HTTP TCP.

**Vì sao có cả `status`, `header`, `jsonPath` và JSON Schema?**
- `status().isCreated()` bắt việc đổi 201 thành 200.
- `header().string("Location",...)` bắt sai đường tài nguyên sau POST.
- `contentTypeCompatibleWith` bảo vệ `application/json`/`application/problem+json`.
- `jsonPath` nêu các **business examples** quan trọng.
- `ContractSchemas.assertValid` kiểm mọi required/type/enum/range/additionalProperties theo schema.
- `legacyConsumerCanDeserializeNewOptionalField` chứng minh một **consumer reader cụ thể** thật sự bỏ qua field mới, thay vì chỉ giả định dựa trên schema.

**Negative tests không kiểm chỉ status:** các trường hợp validation kiểm schema của request lẫn errorCode, và test malformed body kiểm không tạo `ord-201`. Cần mở rộng tương tự với authentication/authorization, ETag, query params, pagination, idempotency nếu chúng là contract của API thật.

**Một điểm quan trọng:** Strict Jackson settings là phần của project. Nếu gỡ `allow-coercion-of-scalars=false`, chuỗi `"2"` có thể được Jackson chuyển thành số 2 trước validation, làm test `postStringQuantityIsRejectedBySchemaAndJackson` fail. Đó là dấu hiệu **schema contract và runtime parsing đã lệch nhau**; không nên sửa test để che sự khác biệt.

## 10. Lớp compatibility test: cố ý tạo payload không tương thích

**src/test/java/demo/contract/SchemaCompatibilityTest.java**

~~~java
package demo.contract;

import com.networknt.schema.JsonSchema;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SchemaCompatibilityTest {

    private static final String OLD_RESPONSE = """
            {
              "id":"ord-100",
              "customerId":"cust-a",
              "quantity":2,
              "status":"NEW"
            }
            """;

    private static final String ADDITIVE_RESPONSE = """
            {
              "id":"ord-101",
              "customerId":"cust-b",
              "quantity":3,
              "status":"SHIPPED",
              "deliveryNote":"Giao sau 17 giờ"
            }
            """;

    private JsonSchema v1() throws Exception {
        return ContractSchemas.schema("order-v1.json");
    }

    private JsonSchema v2() throws Exception {
        return ContractSchemas.schema("order-v2.json");
    }

    @Test
    void additiveOptionalFieldIsAcceptedByOldAndNewSchema()
            throws Exception {

        ContractSchemas.assertValid(v1(), ADDITIVE_RESPONSE);
        ContractSchemas.assertValid(v2(), ADDITIVE_RESPONSE);
    }

    @Test
    void oldResponseIsStillValidForNewOptionalSchema()
            throws Exception {

        ContractSchemas.assertValid(v1(), OLD_RESPONSE);
        ContractSchemas.assertValid(v2(), OLD_RESPONSE);
    }

    @Test
    void missingRequiredIdWouldBreakOldConsumer()
            throws Exception {

        String withoutId = """
                {
                  "customerId":"cust-a",
                  "quantity":2,
                  "status":"NEW"
                }
                """;

        ContractSchemas.assertInvalid(v1(), withoutId);
    }

    @Test
    void renamingCustomerIdWouldBreakOldConsumer()
            throws Exception {

        String renamed = """
                {
                  "id":"ord-100",
                  "customer":"cust-a",
                  "quantity":2,
                  "status":"NEW"
                }
                """;

        ContractSchemas.assertInvalid(v1(), renamed);
    }

    @Test
    void changingIntegerQuantityToStringBreaksContract()
            throws Exception {

        String changedType = """
                {
                  "id":"ord-100",
                  "customerId":"cust-a",
                  "quantity":"2",
                  "status":"NEW"
                }
                """;

        ContractSchemas.assertInvalid(v1(), changedType);
    }

    @Test
    void introducingUnknownStatusBreaksClosedEnum()
            throws Exception {

        String newEnumValue = """
                {
                  "id":"ord-100",
                  "customerId":"cust-a",
                  "quantity":2,
                  "status":"READY"
                }
                """;

        ContractSchemas.assertInvalid(v1(), newEnumValue);
    }

    @Test
    void nullOptionalNoteIsNotEquivalentToAbsentNote()
            throws Exception {

        String noteIsNull = """
                {
                  "id":"ord-100",
                  "customerId":"cust-a",
                  "quantity":2,
                  "status":"NEW",
                  "deliveryNote":null
                }
                """;

        // V1 cho unknown additional properties, V2
        // biết field này và yêu cầu string khi xuất hiện.
        ContractSchemas.assertValid(v1(), noteIsNull);
        ContractSchemas.assertInvalid(v2(), noteIsNull);
    }

    @Test
    void unknownRequestFieldViolatesStrictInputSchema()
            throws Exception {

        String futureRequest = """
                {
                  "customerId":"cust-a",
                  "quantity":1,
                  "promotionCode":"SAVE10"
                }
                """;

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                futureRequest);
    }

    @Test
    void missingRequiredRequestQuantityBreaksProducer()
            throws Exception {

        ContractSchemas.assertInvalid(
                ContractSchemas.schema("create-order.json"),
                "{\"customerId\":\"cust-a\"}");
    }

    @Test
    void newUnreviewedResponseFieldFailsStrictV2Schema()
            throws Exception {

        String leakedField = """
                {
                  "id":"ord-100",
                  "customerId":"cust-a",
                  "quantity":2,
                  "status":"NEW",
                  "debugToken":"secret"
                }
                """;

        ContractSchemas.assertValid(v1(), leakedField);
        ContractSchemas.assertInvalid(v2(), leakedField);
    }
}
~~~

**Đếm chính xác: 10 phương thức `@Test` trong lớp schema compatibility.** Các fixture **không tương thích** được đặt cố ý và phải bị `assertInvalid` từ chối. Vì thế chúng PASS khi validator phát hiện vi phạm, không có test cố tình đỏ để đưa vào CI.

**Tổng project: 16 HTTP integration tests + 10 schema compatibility tests = 26 JUnit Jupiter `@Test` methods.**

**Hai tầng kiểm tương thích khác nhau:**
- Trong `OrdersHttpContractTest`, HTTP response **thực** từ Spring MVC được validate với schema, và một legacy reader thực sự parse response có field mới.
- Trong `SchemaCompatibilityTest`, các payload cố tình bị biến đổi được validate để chứng minh chính **các schema có khả năng phát hiện breaking changes**. Lớp này không chạy server, không được coi là bằng chứng runtime compatibility toàn hệ thống.

### 10.1. Những mutation nào sẽ bị phát hiện?

| Thay đổi trong provider hoặc fixture | Test cần fail |
|---|---|
| Bỏ `customerId` khỏi response | `getChecks...` JSONPath + V1 schema |
| Đổi `quantity` sang JSON string | V1 response schema |
| Trả status `READY` chưa công bố | V1 enum schema |
| Đổi POST 201 thành 200 | `postValidRequestHas201...` |
| Bỏ hoặc đổi `Location` | Location header assertion |
| Đổi HTTP 404 thành 200 | `missingOrderHas404...` |
| Bỏ `errorCode` khỏi ProblemDetail | ProblemDetail schema |
| Quên `@Valid` | Required/blank/quantity negative HTTP tests |
| Bật Jackson scalar coercion cho request | `postStringQuantityIsRejectedBySchemaAndJackson` |
| Bật ignore unknown request fields | `postUnknownFieldIsRejected...` |
| Bỏ `deliveryNote` dù business fixture có | `additiveOptionalResponseField...` |
| Đổi field tùy chọn thành `null` | V2 schema test |
| Leak `debugToken` vào provider response | Strict V2 schema |
| Legacy DTO không bỏ qua unknown fields | `legacyConsumerCanDeserialize...` |

**Đừng cập nhật ngay toàn bộ schema expected khi một test đỏ.** Hỏi trước xem đó là thay đổi **có chủ đích**, có consumer đang sử dụng hay không, đã có migration/deprecation plan hay chưa. Đổi một số expected JSON mà không thông báo consumer có thể biến regression test thành một sự hợp thức hóa breaking change.

## 11. Chạy project và kết quả kỳ vọng

**Điều kiện:** JDK 17; Gradle tương thích với Spring Boot 3.3.5; có thể tải dependencies từ Maven Central lần đầu; không cần Docker, database, external HTTP server hoặc token/secret thật.

Nếu có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu bạn chỉ tạo các file trong bài mà **chưa có `gradlew`, `gradlew.bat` và wrapper JAR**, `./gradlew` chưa tồn tại. Dùng Gradle đã cài để tạo wrapper hoặc chạy:

~~~bash
gradle test
~~~

Chạy riêng từng lớp:

~~~bash
./gradlew test --tests demo.contract.OrdersHttpContractTest
./gradlew test --tests demo.contract.SchemaCompatibilityTest
~~~

Báo cáo JUnit thường nằm tại `build/reports/tests/test/index.html`.

| Lớp | Số `@Test` | Trọng tâm |
|---|---:|---|
| `OrdersHttpContractTest` | **16** | HTTP method/path/status, Content-Type, headers, POST/GET, ProblemDetail, request validation và legacy reader |
| `SchemaCompatibilityTest` | **10** | Optional additive, backward/forward schema, missing required, rename, number↔string, enum, nullable, extra request fields |
| **Tổng** | **26** | Tests trong JVM, không cần network thật |

**Kết quả dự kiến:** Các tests được thiết kế để PASS khi mã nguồn được tạo đúng với Boot 3.3.5, Jackson/Spring dependencies và JSON Schema validator 1.5.9. Đây là **expected behavior theo API, source và assertions**, **không phải khẳng định Gradle đã được chạy trong môi trường người đọc**. Khi dự án có phụ thuộc/profiles khác, cần chạy thực tế để xác minh.

**Không dùng `@Transactional` trong lớp test này** vì repository là in-memory singleton; mỗi test reset bằng `@BeforeEach`. Với DB thật, cần transaction/cleanup riêng và kiểm concurrency. `@SpringBootTest` mặc định dùng mock web environment, còn MockMvc được bật bởi `@AutoConfigureMockMvc` — không mở port HTTP.

## 12. OpenAPI, Pact và Spring Cloud Contract: khi nào cần?

### 12.1. OpenAPI là hợp đồng HTTP ở mức interface

**OpenAPI** mô tả endpoints (`paths`), methods, parameters, requestBody, responses theo status, headers, security schemes và schemas. JSON Schema của bài chỉ là **một phần**: nó không thể tự diễn tả HTTP status/Location/Content-Type. Với API thật, lưu đặc tả `openapi.yaml` hoặc JSON ở source control và dùng CI:

1. Validate syntax/specification.
2. Kiểm code-generated OpenAPI có phù hợp đặc tả (hoặc dùng spec-first generation).
3. Dùng OpenAPI diff so sánh bản đã phát hành với bản hiện tại: deleted paths, required fields, changed response types/status.
4. Chạy HTTP contract tests trên implementation như mục 9.
5. Chạy consumer contract verification nếu đã có consumers cụ thể.
6. Gắn approval/migration policy cho breaking changes.

**Mẫu rút gọn OpenAPI 3.1 (minh họa, không là file runnable của project):**

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths:
  /api/v1/orders/{id}:
    get:
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Order exists
          headers:
            X-Contract-Version:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '404':
          description: Order not found
          content:
            application/problem+json:
              schema:
                type: object
  /api/v1/orders:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrder'
      responses:
        '201':
          description: Created
          headers:
            Location:
              schema:
                type: string
components:
  schemas:
    CreateOrder:
      type: object
      required: [customerId, quantity]
      properties:
        customerId:
          type: string
        quantity:
          type: integer
          minimum: 1
    Order:
      type: object
      required: [id, customerId, quantity, status]
      properties:
        id:
          type: string
        customerId:
          type: string
        quantity:
          type: integer
        status:
          type: string
          enum: [NEW, SHIPPED]
        deliveryNote:
          type: string
~~~

Đây là **ví dụ sơ lược** cho hình thức OpenAPI 3.1, không phải spec hoàn chỉnh của tất cả error cases/status/headers; dùng bản chính thức có security, examples, error codes và schema constraints đầy đủ. Springdoc/OpenAPI generators có thể trợ giúp, nhưng **không xem tài liệu sinh tự động từ implementation là bằng chứng compatibility** nếu expected contract cũ cũng bị sinh lại cùng lúc.

### 12.2. Consumer-driven contract testing

Ở mô hình CDC, consumer xác định interaction mà nó thực sự cần:

~~~text
Consumer "billing-ui"
  Given order ord-100 exists
  When GET /api/v1/orders/ord-100, Accept application/json
  Then status 200
       content-type application/json
       body has id:string, quantity:integer, status:NEW|SHIPPED

Publish contract artifact (version + consumer identity)
     |
     v
Provider CI verifies it against service implementation
     |
     v
Provider deploy is gated by active supported consumers
~~~

**Spring Cloud Contract** cho phép định nghĩa các contracts và generate tests/stubs trong hệ Spring (ví dụ Groovy DSL/YAML theo phiên bản); **Pact** dùng consumer-driven pact files và provider verification, có thể dùng broker để quản lý ma trận consumer/provider versions. Hai công cụ có cơ chế version/plugin/dependency riêng: không thêm một DSL/Pact snippet chưa khai báo dependency vào project runnable và nói nó tự hoạt động.

**Provider state** rất quan trọng: Một contract nói “order ord-100 exists” phải có seed/test data phù hợp trước verify, không phụ thuộc database development. Với state “order absent”, provider phải thực sự trả 404, không mock implementation sai. Nếu consumer dùng Kafka, CDC còn có message contract (key/schema/headers/event compatibility) chứ không chỉ HTTP.

### 12.3. Provider-first vs consumer-first

- **Provider-first:** đội provider công bố OpenAPI/schema và verify implementation; tốt khi API public/spec ownership rõ. Rủi ro: team provider thay schema mà không biết consumer thực sự phụ thuộc gì.
- **Consumer-first:** consumer viết những interactions cần thiết, publish cho provider verify; tốt cho hệ nhiều services/teams. Rủi ro: quá nhiều constraints không cần thiết có thể khiến provider khó đổi.
- **Kết hợp:** OpenAPI là baseline chính thức; consumer-specific contracts là **compatibility gate**; full-stack tests kiểm một vài luồng quan trọng. Mục tiêu không phải “chọn một công cụ duy nhất” mà là kiểm đủ các cam kết ở tầng phù hợp.

## 13. Khả năng phục hồi cũng là hợp đồng quan sát được

Một API có JSON Schema hoàn hảo vẫn có thể phá consumer khi có lỗi mạng hoặc retry. Contract reliability bao gồm:

- **Timeout**: consumer biết connect/read timeout, max latency và fallback; schema không kiểm timeout.
- **Retries**: POST không phải lúc nào idempotent. Nếu client retry do mất HTTP response sau khi server đã tạo order, có thể tạo hai orders. Cần **idempotency key**, business dedup hoặc policy retry thích hợp.
- **429/503**: status codes, `Retry-After`, response errorCode và rate limit policy; không tự biến mọi lỗi thành 200.
- **Circuit breaker/fallback**: khi backend lỗi, định nghĩa response nào là degraded, có phân biệt stale data hay không.
- **Correlation ID**: request/response headers và logs có thể dùng trace ID, nhưng không tiết lộ token/PII.
- **Pagination/ordering**: cursor, stable sort, consistency semantics ảnh hưởng consumer nhiều hơn việc JSON parse thành công.
- **Version skew**: provider mới và consumer cũ cùng tồn tại khi deploy rolling/canary, cần kiểm dải versions.
- **Security**: auth scopes/roles, 401/403, field redaction cũng là phần contract, không chỉ controller path.

**Ví dụ retry nguy hiểm:**

~~~text
T0: Consumer POST /orders, body order A
T1: Server tạo ord-201, commit thành công
T2: Mạng đứt trước khi client đọc 201
T3: Client retry cùng POST
T4: Server tạo ord-202 lần nữa
=> Hai orders dù mỗi response hoàn toàn đúng JSON Schema.
~~~

Nếu API cần retry-safe creation, thiết kế `Idempotency-Key` được server lưu đủ bền trong cùng transaction business và test **hai POST cùng key trả cùng kết quả**, bao gồm race/concurrency. Demo runnable ở mục 6 cố tình chưa hỗ trợ idempotency; test `repeatedValidPostsCreateDistinctLocations` thể hiện thực trạng đó. **Không nhầm một request contract test với chứng minh exactly-once semantics.**

### 13.1. Fault injection bổ sung

| Failure | Contract cần kiểm | Công cụ phù hợp |
|---|---|---|
| Server trả 503 | Client retry/fallback/timeout | WireMock/MockWebServer, resilience test |
| HTTP status vẫn 200 nhưng body sai schema | Consumer parser fail | MockMvc + JSON Schema/provider verification |
| Đổi 404 thành 200 body null | Error policy bị phá | MockMvc HTTP contract |
| Connection reset sau server commit | Duplicate create nguy cơ | Real HTTP mock server + DB integration |
| Consumer version cũ dùng response mới | Backward compatibility | Pact/Spring Cloud Contract/provider states |
| Provider cũ gặp request từ consumer mới | Strict unknown field có thể 400 | Consumer/provider version matrix |
| Event schema mới có field required | Consumer message deserialization fail | Schema registry compatibility + messaging tests |
| ETag/If-Match bị bỏ | Lost update/precondition behavior | HTTP integration + concurrent DB tests |

**Contract test không thay performance/chaos/security testing.** Nó là một lớp guardrail rõ: quan sát từ bên ngoài ổn định theo thỏa thuận. Khi cần chứng minh ứng dụng phục hồi sau outage/restart, phải có fault-injection, timeout, broker/storage state và metrics phù hợp.

## 14. Phân tích compatibility cho JSON Schema, Avro và Protobuf

Bài runnable dùng JSON/JSON Schema, nhưng thuật ngữ **schema compatibility** còn xuất hiện ở messaging:

**JSON/REST**
- Field required/optional, nullability, enum, type, format, HTTP status/headers.
- `additionalProperties` và Jackson unknown fields quyết định mức tolerant reader.
- Không có registry bắt buộc theo giao thức; quản lý schemas/OpenAPI/Pact artifacts bằng CI hoặc registry theo kiến trúc.

**Avro**
- Schema writer/reader resolution, default cho fields mới, union types, enum symbols và field aliases có semantics riêng.
- Registry thường có BACKWARD/FORWARD/FULL compatibility modes; tên mode và phạm vi (transitive hay chỉ latest) tùy registry.
- Không áp thẳng quy tắc JSON `additionalProperties:true` vào Avro.

**Protobuf**
- Field numbers là wire identity. Thêm field number mới thường tương thích hơn việc **tái sử dụng field number cũ với nghĩa khác**.
- Xóa field cần reserve number/name khi phù hợp; đổi wire type hoặc oneof semantics có thể breaking.
- Unknown fields handling thay đổi theo runtime/language/version; kiểm bằng serializer/consumer thực, không đoán.
- Schema registry có thể bổ sung policy nhưng không tự đảm bảo semantic compatibility của business event.

**GraphQL** cũng có cơ chế riêng: thêm optional field vào schema thường không phá query cũ, xóa field/đổi nullability hoặc enum có thể breaking. Cần introspection/schema diff và consumer operation checks.

**Thông điệp chính:** “Compatible” là một quan hệ giữa **producer writer, consumer reader, giao thức, serialization library và hợp đồng hành vi**; không phải một thuộc tính tuyệt đối của một file schema đứng riêng.

## 15. Chọn mức strictness và tránh contract test quá giòn

**Nên assert chặt ở đâu?**
- Method, route, status, required headers, content type: khi consumer dựa vào chúng.
- Required JSON fields, type, non-null, enum semantics: khi có trong public contract.
- Error code/shape, `Location`, API version semantics.
- Không xuất hiện field bí mật, extra properties ở provider output nếu disclosure là rủi ro.

**Nên tránh quá chặt ở đâu?**
- JSON object key order hoặc whitespace; JSON parser không cần thứ tự keys.
- Raw `Date`, request ID, trace ID hoặc dynamic timestamps nếu không có quy tắc định dạng xác định.
- Server header ordering hoặc casing không có ý nghĩa HTTP.
- Trường response tùy chọn mà consumer không dùng.
- Internal database IDs/stack traces/implementation class names.
- Absolute host trong tests nếu API contract chỉ hứa relative path (và ngược lại).

**Consumer tolerance phải được thiết kế có giới hạn.** Nếu consumer “bỏ qua mọi unknown fields”, việc provider vô tình gửi `debugToken` vẫn nguy hiểm. Vì thế bài dùng **schema V1 tolerant để test đọc**, nhưng **schema V2 strict để test output của provider**. Một API thực nên còn có kiểm field redaction, security classification và schema publication approvals.

**Không tắt validation để tương thích bằng mọi giá.** Nếu một v2 provider bỏ `quantity` hoặc đổi JSON type mà client parser silently defaults to 0, request có thể “parse được” nhưng tính tiền sai. **Tương thích về cú pháp không bảo đảm đúng semantics**. Đặc biệt với tiền tệ, đơn vị đo, timezone, enum, decimal precision, cần assertions riêng về business meaning.

### 15.1. Khi nào nên version endpoint?

Một breaking change có thể đáng tạo `/api/v2`, đổi media type có version, hoặc dùng một versioning strategy khác. Chọn theo public API policy:

- **Additive, compatible:** bổ sung optional fields, documentation và provider contract tests; không bắt buộc đổi major version nếu consumers đã tolerant.
- **Breaking:** xóa required field, đổi semantics hoặc status quan trọng; dùng version mới hoặc coordinated deploy với tất cả consumers nếu môi trường nội bộ cho phép.
- **Deprecation:** công bố lịch, đo traffic của version cũ, hỗ trợ overlap, gửi warning/headers theo chính sách đã định.
- **Retirement:** chỉ bỏ v1 khi dữ liệu sử dụng và hợp đồng consumer chứng minh không còn phụ thuộc, hoặc policy sunset đã được thực thi đúng.

**Đừng chỉ đổi path `/v1` thành `/v2` rồi tuyên bố an toàn.** Consumer cũ vẫn cần v1 được phục vụ cho tới khi migration hoàn tất, và dữ liệu/migrations phải hỗ trợ version skew nếu provider dùng chung database.

## 16. Những lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Bằng chứng/cách sửa |
|---|---|---|
| MockMvc trả 200 nhưng app khách lỗi | Chỉ assert status, bỏ body schema | Validate JSON Schema + consumer parse |
| Test xanh sau đổi `quantity` từ number sang string | `jsonPath` chỉ so `.asText` hoặc Jackson coercion | JSON Schema strict type; disable coercion nếu policy |
| Xóa field `id` mà test không nhận ra | Không có `required` trong schema | Thêm `required`, negative fixture |
| New `status=READY` làm UI crash | Closed enum chưa có compatibility review | Enum test + consumer capabilities |
| Thêm optional response field làm legacy parser fail | Consumer reject unknown fields | Test tolerant reader, phiên bản hoặc rollout |
| Thêm request property mới bị server cũ 400 | `additionalProperties:false`/strict Jackson | Kiểm forward compatibility và release ordering |
| Thêm required request property | Client cũ không cung cấp | Breaking; version/migration/default policy |
| `deliveryNote` null thay vì absent | `null` khác optional | JSON Schema type + @JsonInclude |
| `@Valid` không chạy | Thiếu starter-validation, annotation | Negative HTTP validation tests |
| JSON Schema pass nhưng HTTP status sai | Schema không biết status | MockMvc status assertion |
| 400 response có stack trace | Error handler rò exception | ProblemDetail stable code + security tests |
| Problem JSON có field custom rơi vào `properties` nested | Jackson ProblemDetail integration không giống kỳ vọng | Test JSON HTTP thực/flattened property |
| Provider schema và code cùng bị sửa để test xanh | Không có baseline contract artifact độc lập | Publish/verify versioned contracts |
| MockMvc pass, client vẫn không kết nối qua mạng | Mock servlet không mở socket | RANDOM_PORT/WebTestClient/MockWebServer |
| Nhiều tests phụ thuộc thứ tự do repository state | Singleton fixtures không reset | @BeforeEach, DB rollback/cleanup |
| Pact provider verify fail do thiếu fixture | Provider state chưa setup | Provider-state arrangement |
| OpenAPI diff cho false positives | Schemas generated không ổn định | Review semantically, normalize |
| Schema validator dùng sai Draft | Mặc định V4 thay vì V202012 | Factory V202012, `$schema` explicit |
| Jackson 3 bị trộn Jackson 2 ở Boot 4 | Package/module thay đổi | Chọn version validator tương thích Boot |
| Response body chứa secret mới nhưng V1 tolerant pass | `additionalProperties:true` | Provider strict schema/redaction tests |
| POST retry tạo hai tài nguyên | Không có idempotency contract | Idempotency-Key + DB dedup + failure tests |
| Timeout HTTP không được test | MockMvc chỉ kiểm response bình thường | MockWebServer/network fault-injection |
| Không biết consumer nào đang dùng field bị xóa | Thiếu registry/consumer telemetry | CDC/Pact broker/deprecation logs |

### 16.1. Checklist trước khi merge thay đổi API

1. Có baseline **OpenAPI/JSON Schema/CDC** được quản lý ngoài chính implementation mới chưa?
2. Đã liệt kê các active consumer versions và dải được hỗ trợ chưa?
3. Với **request**: method/path/query/headers/Content-Type và required/optional JSON có được kiểm?
4. Với **response**: status, Location, media type, headers, required fields/types/enum có được kiểm?
5. Có test **missing field, renamed field, wrong type, new enum, null vs absent**?
6. Có test **optional additive field** cho consumer cũ và provider mới?
7. Có test consumer reader thật hoặc CDC provider verification, không chỉ schema validity?
8. Strictness của unknown fields ở request và response có được xác nhận?
9. Bean Validation/Jackson behavior có khớp JSON Schema không?
10. Error body dùng mã ổn định và không lộ stack trace/PII?
11. Có thử HTTP 400/404/415/406 theo contract, không tự đổi sang 200?
12. Có migration plan nếu breaking, deprecation timeline và rollout order?
13. Có kiểm retry/idempotency/timeout/error status ở resilience test riêng?
14. Nếu deploy rolling/canary, provider mới có phục vụ consumer cũ trong overlap window không?
15. Nếu schema dùng trong Kafka/Avro/Protobuf, đã dùng đúng registry compatibility mode và runtime-specific rules chưa?
16. CI có fail khi contract cũ bị phá, không tự cập nhật golden file để bỏ qua?
17. Secrets/auth/test data có bị dùng trong snapshot hoặc logs không?
18. Bằng chứng test nêu rõ MockMvc/JSON Schema hay HTTP real network, không thổi phồng phạm vi?

## 17. Bài tập tự luyện

**Bài 1.** Bỏ `customerId` khỏi OrderView. Test nào fail trước? Hãy giải thích `required` có phát hiện trường vắng dù JSON vẫn parse được.

**Bài 2.** Đổi `quantity` của response thành string. Chứng minh JSON Schema reject, và đánh giá hệ thống có consumer tự coerce có an toàn hay không.

**Bài 3.** Thêm `deliveryNote` string tùy chọn. Tại sao v1 consumer vẫn parse được? Thử thay `@JsonIgnoreProperties(ignoreUnknown=true)` bằng strict reader.

**Bài 4.** Thêm `deliveryNote` vào danh sách `required` của V2. Old response còn hợp lệ không? Chọn default/fallback hay API version mới.

**Bài 5.** Thay `deliveryNote` vắng thành `null`. Đọc schema và chứng minh khác nhau giữa optional và nullable.

**Bài 6.** Đổi 201 thành 200 cho POST. Vì sao một response schema test vẫn pass nhưng HTTP contract test fail?

**Bài 7.** Bỏ `Location` sau 201. Viết test consumer follow-up GET và giải thích lợi ích của header contract.

**Bài 8.** Đổi `status=NEW` thành `status=READY` và không cập nhật schema. Vì sao enum compatibility review quan trọng ngay khi type vẫn string?

**Bài 9.** Gửi `{"customerId":"cust-a","quantity":"2"}`. Chứng minh schema fail và giải thích vì sao Jackson scalar coercion làm server behavior có thể khác schema.

**Bài 10.** Gửi request có thêm `promotionCode`. Server strict phải trả gì? Nếu muốn forward-compatible requests, đổi policy/tests ra sao?

**Bài 11.** Thay required `customerId` bằng một field tên `customer`. Phác thảo API v2 và migration path cho khách cũ.

**Bài 12.** Viết OpenAPI đầy đủ cho GET/POST gồm responses 200/201/400/404/415/406, location header và error schema.

**Bài 13.** Viết một consumer-driven interaction của `billing-ui` với provider state `"order ord-100 exists"`, verify trên API build hiện tại.

**Bài 14.** Bật Spring Security trên API. Thêm contract 401/403 và scopes phù hợp, phân biệt schema test với authorization policy test.

**Bài 15.** Thêm `Idempotency-Key` cho POST. Giả lập network timeout sau DB commit, retry cùng key và chứng minh chỉ một order được tạo.

**Bài 16.** Chuyển message OrderCreated sang Avro hoặc Protobuf; tìm thay đổi schema nào breaking theo writer/reader và field-number semantics.

**Bài 17.** Tạo canary provider P2 với consumer C1/C2; lập ma trận deploy order và contract verification trước khi dừng P1.

**Bài 18.** Review một API thực: liệt kê request, response, headers, errors, optional/required/enum và đưa chúng thành test contracts được chạy trong CI.

## 18. Tài liệu chính thức

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, `@WebMvcTest`.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): MVC request/response assertions không cần server TCP.
- [Spring Boot 3.3 — JSON/Jackson](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): Jackson mapping và customization.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.jackson.*`.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ResponseEntityExceptionHandler` và RFC 9457.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid` request bodies và method argument validation.
- [JSON Schema — Specification](https://json-schema.org/specification): Draft 2020-12 keywords/vocabulary và schema semantics.
- [NetworkNT json-schema-validator 1.5.9 API](https://www.javadoc.io/static/com.networknt/json-schema-validator/1.5.9/index.html): Java validator, SpecVersion, JsonSchemaFactory, validate.
- [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.1.html): paths, parameters, requestBody, responses/headers/schema.
- [Spring Cloud Contract](https://docs.spring.io/spring-cloud-contract/reference/): consumer-driven contracts, generated tests và stubs.
- [Pact](https://docs.pact.io/): consumer contracts, provider verification, broker/version workflows.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standardized error responses.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP method/status/media type/headers.
- [Confluent — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): Avro/Protobuf/JSON Schema registry policies.

**Ghi nhớ:** Hợp đồng API bao gồm **cả request, response, schema và hành vi HTTP**, không chỉ “JSON có parse được”. Khi thay đổi, phải hỏi **consumer nào còn đang hoạt động và sẽ đọc dữ liệu này ra sao**. Dùng JSON Schema với `required`, `type`, `enum`, `additionalProperties` để kiểm payload; dùng MockMvc để kiểm method/path/status/header/media type/error; dùng CDC/consumer tests để bảo vệ tích hợp thật. **Thêm response field tùy chọn có thể tương thích; xóa field required, đổi number→string, thay enum/status hoặc thêm required request field thường phá vỡ hợp đồng.** Với khả năng phục hồi, phải kiểm thêm timeout, retry, idempotency và version skew — một schema test đơn lẻ không chứng minh toàn hệ thống an toàn.
