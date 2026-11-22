# Kiểm tra đối tượng lồng, collection và validation group

## 1. Vì sao @Valid ở request body có thể bỏ sót lỗi?

API tạo đơn nhận:

```json
{
  "customerId":"c-42",
  "shipping":{"receiver":"","city":"Hà Nội","postalCode":"abc"},
  "items":[{"sku":"SKU-A","quantity":2},{"sku":"","quantity":0}],
  "tags":["gift",""]
}
```

Chỉ gắn `@NotNull` lên `shipping` và `@NotEmpty` lên `items` **không kiểm tra các field bên trong**. Cần đúng ràng buộc cho **container, phần tử và nested object**, kết hợp `@Valid` để cascade.

Bài thuộc chương **Dữ liệu và lỗi Spring** của module **INTEGRATION_API_REST**: thực hành REST với Java/Spring, HTTP status, hợp đồng dữ liệu, validation, bảo mật và kiểm thử. Bạn sẽ biết cách validate `List`/`Map` nhiều tầng, chọn `@Validated` groups, trả lỗi có field path và test hành vi thực, không lặp toàn bộ lý thuyết REST.


## 2. Root, container và nested value là ba cấp khác nhau

| Cấp | Ràng buộc ví dụ |
|---|---|
| Request root | `@Valid @RequestBody` kích hoạt kiểm tra DTO |
| Container | `@NotEmpty @Size(max=50) List<...>` |
| Phần tử | `List<@NotNull …>` cấm phần tử null |
| Nested object | `@Valid` để xuống `sku`/`quantity` |
| Scalar element | `List<@NotBlank String>` cấm tag trắng |

`@Valid` **không tự cấm null**: cascade bỏ qua tham chiếu null; thêm `@NotNull` nếu object bắt buộc. `@NotEmpty` kiểm tra list có phần tử, **không bảo đảm item hợp lệ**.

Spring Boot 3+/Spring 6+ dùng `jakarta.validation.*` và provider như Hibernate Validator; dự án cũ có thể dùng `javax.validation.*`. Chọn dependency/provider tương thích phiên bản.


## 3. DTO hoàn chỉnh cho đối tượng lồng và collection

Ví dụ với Java record (Java 17+) và Jakarta Validation:

```java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;

record OrderLineInput(
    @NotBlank String sku,
    @Positive int quantity
) {}

record ShippingInput(
    @NotBlank String receiver,
    @NotBlank String city,
    @NotBlank
    @Pattern(regexp = "[0-9]{5,6}")
    String postalCode
) {}

record CreateOrderInput(
    @NotBlank String customerId,

    @NotEmpty
    @Size(max = 50)
    List<@NotNull @Valid OrderLineInput> items,

    @NotNull @Valid ShippingInput shipping,

    @Size(max = 10)
    List<@NotBlank String> tags
) {}
```

Các lớp này minh họa Java record: Spring/Jackson phù hợp có thể deserialize từ JSON đến các record components; Bean Validation đánh giá constraints trên chúng khi được kích hoạt.

Điểm đáng chú ý:

- `@NotEmpty` áp lên **List**: null hoặc danh sách rỗng không hợp lệ.
- `@Size(max=50)` giới hạn số phần tử; nó **không** kiểm tra số lượng từng dòng.
- `List<@NotNull @Valid OrderLineInput>`: cấm phần tử null và cascade xuống `sku`/`quantity` cho từng phần tử.
- `@NotNull @Valid ShippingInput`: shipping phải có, đồng thời các field bên trong được kiểm tra.
- `List<@NotBlank String> tags`: mọi tag, nếu list được gửi, phải là chuỗi có nội dung không trắng. Vì `tags` không có `@NotNull`, **toàn bộ list có thể null** theo DTO này.
- `@Positive int quantity` buộc lớn hơn 0; dùng `Integer` cùng `@NotNull` nếu phải phân biệt field thiếu với giá trị 0 khi deserialize.

**Thông điệp:** cần đọc kiểu Java và ràng buộc cùng nhau. Không có một annotation duy nhất thay thế được việc kiểm tra root, list, item và field bên trong.

## 4. Kích hoạt @Valid ở request và nested relationships

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @PostMapping
    ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderInput input) {
        OrderView saved = orders.create(input);
        return ResponseEntity.created(
            java.net.URI.create("/api/orders/" + saved.id())
        ).body(saved);
    }
}
```

`@Valid` ở `@RequestBody` kích hoạt kiểm tra root; `@Valid` trên `shipping` và phần tử `items` cascade vào field con. Nếu thiếu tại một cạnh, các constraint nằm sâu có thể không chạy theo luồng MVC đó.

`OrderService`/`OrderView` là kiểu ứng dụng. Trong triển khai thật, service phải kiểm tra authentication, tenant, tồn kho và idempotency; **validation pass không đồng nghĩa được phép tạo đơn**. HTTP thành công tạo resource thường trả `201 Created` với `Location`; body JSON và security policy phải được kiểm thử.


## 5. Các annotation không thay thế lẫn nhau

| Constraint | Áp dụng | Ý nghĩa |
|---|---|---|
| `@NotNull` | Reference type | Không null |
| `@NotEmpty` | String/Collection/Map/Array | Không null/rỗng |
| `@NotBlank` | Chuỗi | Có ký tự không phải khoảng trắng |
| `@Size(min,max)` | String/collection/map/array | Kích thước hợp lệ; **null vẫn pass** |
| `@Positive`/`@Min(1)` | Số | Số dương hoặc ≥ 1 |
| `@Email`/`@Pattern` | Chuỗi | Kiểm tra định dạng; **null có thể pass** |

```java
record SignupInput(
    @NotBlank @Email String email,
    @NotEmpty List<@NotBlank String> interests
) {}
```

`@Size(min=1)` hoặc `@Email` một mình không đủ để buộc field tồn tại. `@NotEmpty List<String>` không cấm `[""]`; cần constraint trên phần tử. JSON gửi sai kiểu số có thể bị Jackson từ chối **trước** Bean Validation.


## 6. Collection element constraints và nhiều tầng lồng

```java
record BatchInput(
    @NotEmpty List<@NotBlank String> orderIds,
    @Size(max=10) Set<@NotBlank String> labels,
    Map<@NotBlank String, @NotNull @Valid ShippingInput> addresses,
    List<@NotEmpty List<@NotBlank String>> lineGroups
) {}
```

- `orderIds` không được rỗng, từng ID không trắng; `labels` có thể null vì chỉ `@Size`.
- `addresses` có thể null nếu không có constraint trên field; khi có map, key phải có nội dung và value không null/cascade.
- `lineGroups` bắt list con không rỗng và từng chuỗi không trắng; toàn bộ container null cần `@NotNull` nếu muốn cấm.
- `Set` có thể gộp phần tử trùng lúc deserialize; muốn báo duplicate từ JSON phải dùng DTO/kiểm tra phù hợp.

Với `List<@NotNull @Valid Item>`, violation có thể có path `items[1].sku`. Spring `BindingResult` thường cung cấp path dạng này; nếu đưa ra public contract, hãy chuẩn hóa format thay vì phụ thuộc byte-for-byte vào một provider.

Các generic container tự viết có thể cần `ValueExtractor` khi provider không biết cách duyệt.


## 7. Field vắng khác explicit null, nhất là PATCH

JSON `{}` và `{"shipping":null}` thường cùng deserialize thành `shipping == null` nếu DTO không giữ thông tin present/absent. Bean Validation **không tự phân biệt** hai trường hợp.

- **POST:** trường bắt buộc dùng `@NotNull`/`@NotBlank`.
- **PATCH:** vắng có thể nghĩa “giữ nguyên”, còn null có thể là “xóa” tùy contract/media type.
- Một field có `@NotBlank` nhưng null vẫn có thể pass nếu không kèm constraint bắt buộc.

Với patch nhiều field hoặc JSON Merge Patch/JSON Patch, **ưu tiên DTO riêng** và test rõ null/missing. Validation groups không thay thế merge semantics, `If-Match` hay kiểm soát ghi đè đồng thời.


## 8. Validation groups: khi cùng kiểu dữ liệu có nhiều ngữ cảnh

Jakarta Validation mặc định kiểm tra **nhóm `Default`**. Có thể định nghĩa nhóm cho từng operation:

```java
import jakarta.validation.groups.Default;

interface OnCreate extends Default {}
interface OnPatch extends Default {}
```

Hai interface **kế thừa Default** có chủ đích: khi validate `OnCreate` hay `OnPatch`, các constraint thuộc `Default` cũng được xem xét theo quy tắc kế thừa group. Nếu nhóm chỉ là `interface OnCreate {}`, gọi validate mỗi `OnCreate` **không mặc nhiên chạy mọi constraint Default**.

Ví dụ DTO dùng chung để minh họa:

```java
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;

record OrderDraft(
    @NotBlank(groups = OnCreate.class)
    String customerId,

    @NotEmpty(groups = OnCreate.class)
    List<@NotNull @Valid OrderLineInput> items,

    @NotNull(groups = OnCreate.class)
    @Valid ShippingInput shipping,

    @Size(max = 200) String note
) {}
```

| Thuộc tính | Validate OnCreate | Validate OnPatch |
|---|---|---|
| `customerId` thiếu/trắng | Fail | Không bị `@NotBlank(OnCreate)` bắt |
| `items` thiếu | Fail | Có thể qua constraint của container ở nhóm Patch |
| `items` hiện diện, có phần tử sai | Fail do cascade/Default | Vẫn có thể fail do cascade/Default |
| `shipping` thiếu | Fail | Có thể bỏ qua nếu patch không đổi shipping |
| `shipping` hiện diện, city rỗng | Fail | Fail do constraints nested ở Default |
| `note` quá 200 ký tự | Fail | Fail vì `@Size` thuộc Default |

**Điểm cần để ý:** `OnPatch extends Default` không có nghĩa PATCH “luôn hợp lệ khi mọi field đều vắng”. Nếu không cho phép empty patch, cần constraint cấp class hoặc rule nghiệp vụ riêng. Nếu field vừa có constraint default vừa có constraint theo group, phải suy ngữ nghĩa toàn bộ thay vì chỉ đọc một annotation.

### Ưu/nhược điểm tái dùng DTO

Groups hữu ích khi phần lớn schema chung, khác một vài ràng buộc. Nhưng nếu create và patch có **nghĩa khác nhau**, nhiều nhóm chồng chéo, null/missing phức tạp hoặc an toàn dữ liệu cao, DTO riêng thường rõ và ít lỗi hơn. Không phải lúc nào “giảm số class” cũng là mục tiêu quan trọng hơn một API contract có thể hiểu được.

## 9. @Validated chọn group trong Spring MVC

`@Valid` ở parameter kích hoạt nhóm mặc định trong trường hợp thông thường; `@Validated` của Spring cho phép chỉ định validation groups tại vị trí hỗ trợ:

```java
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/order-drafts")
class OrderDraftController {
    private final OrderDraftService drafts;

    OrderDraftController(OrderDraftService drafts) {
        this.drafts = drafts;
    }

    @PostMapping
    DraftView create(
            @Validated(OnCreate.class) @RequestBody OrderDraft input) {
        return drafts.create(input);
    }

    @PatchMapping("/{id}")
    DraftView patch(
            @PathVariable String id,
            @Validated(OnPatch.class) @RequestBody OrderDraft input) {
        return drafts.patch(id, input);
    }
}
```

`OrderDraftService` và `DraftView` do ứng dụng cung cấp. Đây là ví dụ **chọn nhóm kiểm tra ở request body**, không phải mẫu hoàn chỉnh cho PATCH production. Tên group không thể thay thế xử lý quyền, atomic update, version precondition hoặc phân biệt null/field vắng.

**Không đặt `@Validated` lên toàn bộ controller chỉ vì quen tay.** Trong một số phiên bản Spring, annotation cấp class kích hoạt proxy-based method validation và thay đổi cơ chế/exception của validation cho tham số method. Với Spring MVC 6.1+, built-in method validation có hành vi riêng; lựa chọn cấu hình nên được xác minh bằng integration tests và documentation của phiên bản đang dùng.

## 10. Group inheritance và group sequence

Nếu `OnCreate extends Default`, kiểm tra group OnCreate cũng xét constraint Default theo quy tắc kế thừa. Nếu chỉ `interface OnCreate {}`, không tự hiểu các constraints ở Default được kiểm tra cùng.

`@GroupSequence` cho phép thứ tự kiểm tra:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface ExpensiveChecks {}

@GroupSequence({Default.class, ExpensiveChecks.class})
interface OrderedChecks {}
```

`validator.validate(input, OrderedChecks.class)` chạy Default trước và bỏ qua group sau nếu Default có violation. **Không được dựa vào thứ tự violations trong cùng group**; test nên so tập lỗi.

Group sequence dùng khi thực sự có pha kiểm tra phụ thuộc, không phải mặc định mọi DTO. DB uniqueness/authorization vẫn cần kiểm tra tại transaction/service, không giải quyết race chỉ bằng validator.


## 11. @ConvertGroup dùng cho cascade, không phải “chọn nhóm cho cả request”

Với đối tượng nested, đôi lúc cần validate group khác với root. `@ConvertGroup` áp dụng **tại cạnh cascade**:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;
import jakarta.validation.constraints.NotBlank;

interface CompleteAddress extends Default {}

record AddressInput(
    @NotBlank String city,
    @NotBlank(groups = CompleteAddress.class) String district
) {}

record CheckoutInput(
    @Valid
    @ConvertGroup(from = Default.class, to = CompleteAddress.class)
    AddressInput shipping
) {}
```

Khi root `CheckoutInput` được validate trong `Default`, cascade qua `shipping` chuyển sang `CompleteAddress`, nên kiểm tra cả city ở Default (nhờ group kế thừa) và district ở CompleteAddress.

Các ràng buộc:

1. **`@ConvertGroup` cần gắn cùng điểm với `@Valid`** hoặc vị trí cascade tương ứng.
2. Nó chỉ đổi group **khi đi qua quan hệ được cascade**, không thay group của mọi field root.
3. Chọn group chuyển đổi rõ và tránh vòng chuyển đổi khó hiểu; conversion không phải cơ chế chạy kiểm tra theo mọi nhóm.
4. Với `List`/`Map` nested, cần đặt conversion tại phần tử/cạnh tương ứng theo cú pháp và khả năng provider hỗ trợ.
5. Khi group còn có kế thừa, kiểm tra bằng `Validator` và request HTTP thật để chắc constraints mong muốn chạy.

**Phần lớn controller không cần `@ConvertGroup`.** Dùng khi đối tượng lồng có ngữ cảnh kiểm tra khác rõ ràng, có test cụ thể; không dùng để “vá” DTO quá nhiều nhóm.

## 12. Bean Validation không thay business rules và authorization

Một request hợp lệ về `sku`, `quantity` và `postalCode` vẫn có thể vi phạm:

- `customerId` thuộc tenant khác.
- SKU không tồn tại hoặc đã ngừng bán.
- Tồn kho đã đổi sau khi validate.
- Idempotency key đã dùng với body khác.

| Tầng | Trách nhiệm |
|---|---|
| Jackson/binding | Đọc body và kiểu dữ liệu |
| Bean Validation | Constraints cấu trúc, nested/collection/group |
| Service/security | Quyền resource, quy tắc domain, tenant |
| Transaction/database | Unique/FK, race, optimistic locking |
| Gateway | Auth transport, quotas và body size |

**Không tin tenant/owner do caller khai.** Lấy principal từ identity đã xác thực, giới hạn truy vấn và side effects ở service. Custom validator gọi DB trước insert **không đảm bảo uniqueness** dưới concurrency.


## 13. HTTP status và error contract

| Trường hợp | Status thường dùng |
|---|---|
| JSON sai cú pháp/kiểu, `@Valid` nested/list fail | `400 Bad Request` |
| Lỗi semantic với body parse được, nếu hợp đồng chọn | `422 Unprocessable Content` |
| Business state hoặc uniqueness conflict | `409 Conflict` |
| `If-Match` sai | `412 Precondition Failed` |
| Thiếu token | `401 Unauthorized` |
| Không có quyền | `403` hoặc `404` theo chính sách che tài nguyên |
| Lỗi server không dự kiến | `500 Internal Server Error` |

Trong Spring MVC, `400` là response phổ biến cho `@Valid @RequestBody` fail; **422 không bắt buộc**. API có thể chọn 422 cho nhóm lỗi semantic nhưng phải nhất quán.

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type":"https://api.example.test/problems/invalid-request",
  "title":"Invalid request",
  "status":400,
  "code":"VALIDATION_FAILED",
  "violations":[
    {"field":"shipping.receiver","code":"NotBlank"},
    {"field":"items[1].sku","code":"NotBlank"}
  ]
}
```

`code`/`violations` là extensions của **Problem Details (RFC 9457)**. Thứ tự violations không phải cam kết; **không đưa rejected values/PII/token** vào response.


## 14. Spring @RestControllerAdvice: chuẩn hóa lỗi lồng nhau

Ví dụ Spring Framework 6+/Boot 3.x dùng `ResponseEntityExceptionHandler` để mapping lỗi `MethodArgumentNotValidException`:

```java
import java.util.List;
import java.util.Map;
import org.springframework.http.*;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@ControllerAdvice
class ValidationErrorHandler extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<Map<String, String>> violations = ex.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> Map.of(
                "field", error.getField(),
                "code", error.getCode() == null ? "INVALID" : error.getCode()
            ))
            .toList();

        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        problem.setTitle("Invalid request");
        problem.setType(java.net.URI.create(
            "https://api.example.test/problems/invalid-request"));
        problem.setProperty("code", "VALIDATION_FAILED");
        problem.setProperty("violations", violations);

        return handleExceptionInternal(
            ex, problem, headers, HttpStatus.BAD_REQUEST, request);
    }
}
```

Đoạn này tập trung lỗi ở `@Valid/@Validated @RequestBody`, nơi Spring thường ném `MethodArgumentNotValidException`. Cần bổ sung xử lý global/object-level errors nếu có class-level constraints, vì `getFieldErrors()` **không bao gồm mọi `ObjectError`**.

Trong Spring MVC phiên bản hỗ trợ **built-in method validation**, ràng buộc trực tiếp trên path/query/method arguments có thể dẫn đến `HandlerMethodValidationException`, khác với lỗi request-body. Cách áp `@Validated` cấp controller có thể ảnh hưởng cơ chế AOP/proxy và loại exception. Test từng đường, không cố map **mọi** `ConstraintViolationException` thành 400 vì validation của return value/server invariant có thể là lỗi 500.

**Mã lỗi ổn định:** provider có thể trả `NotBlank`/`Positive` làm constraint code; với API public, cân nhắc ánh xạ sang taxonomy ổn định (`REQUIRED`, `INVALID_FORMAT`, `OUT_OF_RANGE`) để giảm phụ thuộc vào nội bộ framework.

### Không đưa mọi thông tin validation vào client

`error.getRejectedValue()` có thể chứa địa chỉ, email, token hoặc dữ liệu riêng. Chỉ trả field path và error code cần thiết; chi tiết log nội bộ phải được lọc/mask. Giới hạn số lượng violations công bố nếu input có hàng nghìn phần tử.

## 15. Kiểm thử đơn vị với Jakarta Validator

Test thuần Bean Validation kiểm tra cách cascade và groups hoạt động **trước khi** đưa vào HTTP:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import java.util.Set;
import jakarta.validation.*;
import org.junit.jupiter.api.Test;

class OrderValidationTest {
    @Test
    void nestedItemsAndShippingAreValidated() {
        try (ValidatorFactory factory =
                 Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            CreateOrderInput input = new CreateOrderInput(
                "c-42",
                List.of(new OrderLineInput("", 0)),
                new ShippingInput("", "Hà Nội", "abc"),
                List.of("gift", "")
            );

            Set<ConstraintViolation<CreateOrderInput>> errors =
                validator.validate(input);

            assertTrue(errors.stream().anyMatch(v ->
                v.getPropertyPath().toString().contains("sku")));
            assertTrue(errors.stream().anyMatch(v ->
                v.getPropertyPath().toString().contains("quantity")));
            assertTrue(errors.stream().anyMatch(v ->
                v.getPropertyPath().toString().contains("receiver")));
            assertTrue(errors.stream().anyMatch(v ->
                v.getPropertyPath().toString().contains("postalCode")));
        }
    }
}
```

Test này không giả định thứ tự errors. Với `List.of`, **không thể tạo phần tử null** vì `List.of` từ chối null ngay từ Java; để test `List<@NotNull …>` có phần tử null, dùng mutable list hoặc `Arrays.asList(...)` trong fixture.

### Kiểm thử group

```java
OrderDraft input = new OrderDraft(
    null, null, null, "Ghi chú"
);

Set<ConstraintViolation<OrderDraft>> createErrors =
    validator.validate(input, OnCreate.class);

Set<ConstraintViolation<OrderDraft>> patchErrors =
    validator.validate(input, OnPatch.class);

assertFalse(createErrors.isEmpty());
assertTrue(patchErrors.isEmpty());
```

Trích đoạn này giả định `validator` đã được khởi tạo trong test. Nó chứng minh những constraint `OnCreate` bắt buộc không tự áp cho `OnPatch`; nếu DTO có thêm rule Patch hoặc Default khác, kết quả kỳ vọng cần thay theo hợp đồng thực tế.

## 16. MockMvc: kiểm tra JSON lồng và HTTP error

Unit test Validator không phát hiện lỗi từ Jackson, binding, filter, controller advice hay serialization. Cần kiểm thử HTTP.

Ví dụ phần assertions trong test đã cấu hình `mockMvc`, authentication và `OrderService` mock:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.hamcrest.Matchers.hasItem;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.*;

mockMvc.perform(post("/api/orders")
        .with(user("alice"))
        .with(csrf())
        .contentType("application/json")
        .content("""
          {
            "customerId":"c-42",
            "shipping":{
              "receiver":"","city":"Hà Nội","postalCode":"abc"
            },
            "items":[
              {"sku":"SKU-A","quantity":2},
              {"sku":"","quantity":0}
            ],
            "tags":["gift",""]
          }
          """))
    .andExpect(status().isBadRequest())
    .andExpect(content().contentTypeCompatibleWith(
        "application/problem+json"))
    .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
    .andExpect(jsonPath("$.violations[*].field",
        hasItem("items[1].sku")))
    .andExpect(jsonPath("$.violations[*].field",
        hasItem("shipping.receiver")));
```

Đây là trích đoạn, không phải class test độc lập. `.with(csrf())` áp dụng khi app có CSRF policy phù hợp với cơ chế xác thực; REST API stateless bearer có thể dùng fixture JWT và policy khác. Tài khoản giả `user("alice")` không tự chứng minh endpoint thật xác minh JWT hoặc quyền tenant.

### Ma trận tình huống HTTP

| Input | Kết quả mong đợi |
|---|---|
| Thiếu `shipping` | 400, field `shipping` (do `@NotNull`) |
| `shipping.receiver=""` | 400, field nested |
| `items=[]` | 400, `items` (do `@NotEmpty`) |
| `items=[null]` | 400, lỗi phần tử null |
| `items[1].quantity=0` | 400, lỗi phần tử thứ hai |
| `tags=[""]` | 400, lỗi phần tử string |
| `items` dài hơn 50 | 400, lỗi kích thước collection |
| JSON quantity là object/string không hợp kiểu | 400 ở bước conversion, không nhất thiết có cùng danh sách constraint violations |
| `Content-Type: text/plain` với handler chỉ nhận JSON | 415 |
| Request hợp lệ, user khác tenant | 403 hoặc 404 theo policy; **không tạo đơn** |
| POST hợp lệ | 201 + Location, service được gọi đúng một logical operation |

Thử **body sai dữ liệu và body sai kiểu** riêng: một lỗi xảy ra trong Bean Validation, lỗi kia có thể xảy ra ở Jackson trước khi validator nhận DTO. Cần bảo đảm cả hai cùng có error contract an toàn, dù mã lỗi chi tiết có thể khác.

## 17. Test groups và cascade từ HTTP

Kết hợp unit Validator, MockMvc và integration tests:

1. POST `@Validated(OnCreate.class)` thiếu customerId/items/shipping → 400.
2. PATCH `@Validated(OnPatch.class)` chỉ có note → pass validation nếu hợp đồng cho phép.
3. PATCH có shipping với receiver rỗng hoặc item có sku trống → lỗi nested.
4. `OnPatch` có kế thừa `Default`; test chứng minh constraint chung vẫn chạy.
5. DTO có `@ConvertGroup`: field thuộc target group fail đúng chỗ.
6. `@GroupSequence`: vi phạm nhóm trước khiến nhóm sau không chạy.
7. HTTP error chứa **field path và code** ổn định, không dựa vào thứ tự.

Đừng dùng group tests để thay thế kiểm thử phân quyền/transaction. Nếu method parameter validation tạo exception khác request body, kiểm thử đường đó riêng.


## 18. Bảo mật và kiểm soát chi phí validation

- `@Size(max=50)` **chỉ chạy sau parse**: gateway/container phải giới hạn body size trước khi nhận JSON quá lớn.
- Dùng input DTO có **whitelist fields**, không bind JPA entity có `ownerId`/`role`/`isAdmin`.
- Validator không thay tenant/ownership check; luôn lấy identity từ auth.
- Không echo rejectedValue, raw body, SQL, token hoặc PII vào error/logs.
- Regex/custom validators cần giới hạn chi phí; tránh gọi network/DB cho mỗi item.
- Rate limit/timeout theo principal/tenant vì payload nhỏ nhưng request dồn dập vẫn gây DoS.
- **Không cho client chọn validation group qua query/header** để bỏ qua constraint.

Đảm bảo validation fail không tạo side effect và security fail không tiết lộ tài nguyên người khác.


## 19. Phản mẫu và cách sửa

| Sai lầm | Cách sửa |
|---|---|
| Root `@Valid` nhưng thiếu cascade nested | `@Valid` ở đúng cạnh object/element |
| `@NotEmpty List<Line>` rồi nghĩ item hợp lệ | `List<@NotNull @Valid Line>` |
| Chỉ `@Valid` mà object null vẫn qua | Thêm `@NotNull` ở field bắt buộc |
| `@NotEmpty List<String>` để cấm `[""]` | `List<@NotBlank String>` |
| `@Email` hoặc `@Size(min=1)` để buộc có field | Thêm `@NotBlank`/`@NotNull` thích hợp |
| `@Validated(SomeGroup)` làm bỏ qua Default | Group inheritance/sequence và test |
| Dùng DTO tạo mới cho PATCH phức tạp | Patch DTO có missing/null semantics rõ |
| Validator kiểm tra quyền hoặc uniqueness race | Service authorization + DB constraint |
| Trả rejected values hoặc stack trace | Field path và stable error code |
| So thứ tự violations trong test | So tập lỗi |
| Map mọi ConstraintViolationException thành 400 | Phân biệt request vs server validation |
| Dùng Bean Validation thay body/rate limits | Giới hạn từ gateway và security layer |


## 20. Bài thực hành: endpoint tạo đơn có nested data

### Đề bài

Ứng dụng có controller đang nhận trực tiếp entity:

```java
@PostMapping("/api/orders")
OrderEntity create(@RequestBody OrderEntity input) {
    return repository.save(input);
}
```

Yêu cầu mới: khách hàng bắt buộc, ít nhất một item, mỗi item có `sku` không trắng và `quantity > 0`; địa chỉ giao hàng có receiver/city/postalCode hợp lệ; tags tối đa 10 và không có phần tử trắng. POST tạo đơn khác PATCH cập nhật ghi chú. API cần phản hồi validation có path cụ thể, không lộ dữ liệu riêng, có quyền tenant và trả `201 + Location`.

**Nhiệm vụ:**

1. Thiết kế `CreateOrderInput`, `OrderLineInput` và `ShippingInput` với constraints đúng cấp. Nêu vì sao `@NotEmpty List<@Valid Line>` chưa chắc loại bỏ phần tử null.
2. Tạo controller `@Valid @RequestBody` và `ResponseEntity.created(…)`, tách DTO khỏi entity.
3. Thêm demo `OnCreate`/`OnPatch` với common Default constraints; kiểm thử việc chọn group qua `@Validated`. Nói khi nào nên có Patch DTO riêng.
4. Tạo error handler Problem Details có `violations` chứa tối thiểu `shipping.receiver` và `items[1].sku`.
5. Viết ít nhất sáu test cases: body đúng; items rỗng; phần tử null; nested field sai; tags chứa chuỗi trắng; user khác tenant.
6. Phân tích quy tắc nghiệp vụ “SKU còn hàng” và “khách hàng thuộc tenant hiện tại” nên được kiểm tra ở đâu, vì sao `@NotBlank` không đủ.
7. Thử payload rất lớn và chứng minh request size/rate limits có hiệu lực **trước khi** tạo đơn.

### Gợi ý lời giải

Một dạng DTO phù hợp:

```java
record CreateOrderInput(
    @NotBlank String customerId,
    @NotEmpty @Size(max=50)
    List<@NotNull @Valid OrderLineInput> items,
    @NotNull @Valid ShippingInput shipping,
    @Size(max=10) List<@NotBlank String> tags
) {}
```

POST dùng `@Valid @RequestBody CreateOrderInput`; nếu không hợp lệ, trả 400 với path, nếu hợp lệ thì service **vẫn** kiểm tra quyền tenant, tồn kho/idempotency và giao dịch. Với PATCH, ưu tiên một DTO chỉ có trường được phép thay đổi, tránh vô tình cập nhật `ownerId`, `status` hoặc null hóa toàn bộ object.

## 21. Checklist phát hành

- [ ] Entry point `@Valid`/`@Validated` đúng group; cascade nested/element đầy đủ.
- [ ] Object required có `@NotNull`; list required có `@NotEmpty`/`@Size`.
- [ ] Type-use constraint kiểm tra null element, blank tag và Map key/value.
- [ ] Groups, Default inheritance, `@ConvertGroup`/`@GroupSequence` có tests.
- [ ] PATCH tách missing/null theo contract; không lạm dụng groups.
- [ ] Jackson errors, nested Bean Validation và method validation có HTTP tests riêng.
- [ ] Problem Details có field path/code, không lộ rejected values, PII/token.
- [ ] Service xác thực quyền tenant; DB chống race/uniqueness.
- [ ] MockMvc/Validator/integration tests kiểm tra âm/dương; không assert thứ tự lỗi.
- [ ] Có body size, rate limits, validation cost safeguards và OpenAPI phù hợp.


## 22. Kết luận

**Validate REST request lồng nhau phải đúng từng cấp:** `@NotEmpty`/`@Size` cho container, `List<@NotNull @Valid Item>` cho phần tử và cascade, `@NotBlank`/`@Positive` cho field. `@Validated` chọn group, nhưng cần hiểu `Default`, conversion/sequence và giới hạn khi dùng chung DTO cho PATCH.

Spring MVC nên trả **HTTP lỗi thực + Problem Details an toàn** với field path, đồng thời vẫn thực thi **tenant authorization, transaction invariants và request limits**. Kiểm thử cả Validator, MockMvc và đường nghiệp vụ để lỗi `items[1].sku` được phát hiện mà không che giấu lỗi bảo mật hay hệ thống.


