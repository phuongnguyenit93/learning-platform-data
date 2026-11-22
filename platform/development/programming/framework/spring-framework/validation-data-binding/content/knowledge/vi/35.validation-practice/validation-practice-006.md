# Tổ chức Bean Validation cho tạo mới và cập nhật trong Spring Framework

Cùng một tài nguyên nhưng **tạo mới (create)**, **thay thế/cập nhật đầy đủ (update/PUT)** và **cập nhật một phần (PATCH)** thường có các quy tắc input khác nhau. Nếu dùng một DTO với `@NotNull`, `@NotBlank` và `@Size` cho tất cả endpoint mà không xác định rõ hành vi, hệ thống dễ gặp hai lỗi đối lập:

- **Validation quá nghiêm:** endpoint PATCH chỉ muốn sửa `name` nhưng lại bị từ chối vì `sku` hoặc `price` không được gửi.
- **Validation quá lỏng:** developer bỏ `@NotNull` để PATCH hoạt động, khiến POST tạo mới cũng nhận thiếu các trường bắt buộc.

Spring Framework hỗ trợ Jakarta Bean Validation cùng `@Valid`, `@Validated`, validation groups, cascaded validation và custom constraints. Tuy nhiên, **chọn đúng quy tắc cho từng thao tác là quyết định thiết kế API**, không thể phó mặc cho annotations.

Bài thực hành thuộc nhóm **Thực hành** của module **Spring Framework — validation-data-binding**. Nội dung bao gồm hai chiến lược tổ chức: **request DTO riêng cho từng thao tác (mặc định nên ưu tiên)** và **Bean Validation groups khi thực sự cần tái sử dụng một model**; phân biệt POST, PUT, PATCH; nested DTO, group inheritance/conversion, error handling, quyền sửa field, service invariants và kiểm thử.

Ví dụ hoàn chỉnh dùng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Jakarta Bean Validation 3.x, Spring MVC Servlet và JUnit 5/MockMvc**. Các phiên bản mang tính tái hiện bài học, không phải một tuyên bố rằng chúng luôn mới nhất.

## 1. Xác định hợp đồng API trước khi viết annotation

Giả sử hệ thống quản lý sản phẩm có dữ liệu:

~~~json
{
  "id": 42,
  "sku": "PEN-001",
  "name": "Bút xanh",
  "price": 19.90,
  "description": "Bút bi màu xanh"
}
~~~

Các quy tắc:

- `id` do server cấp; client không được thay đổi.
- `sku` bắt buộc khi tạo mới, sau đó **bất biến** (không được sửa bởi PUT/PATCH).
- `name` bắt buộc, không được để trống, tối đa 100 ký tự.
- `price` bắt buộc, là số thập phân không âm.
- `description` tùy chọn, tối đa 500 ký tự.
- Khi PUT cập nhật, client phải cung cấp **đầy đủ tập fields có thể cập nhật** (`name`, `price`; `description` có thể null nếu muốn bỏ).
- Khi PATCH, **trường vắng mặt** có nghĩa là giữ nguyên, còn **trường có mặt với giá trị null** phải có ngữ nghĩa được xác định rõ.

### Ma trận thao tác

| Field | POST /products | PUT /products/{id} | PATCH /products/{id} |
|---|---|---|---|
| `id` | Server tạo, không nhận từ client | Path ID, không bind từ body | Path ID, không bind từ body |
| `sku` | Bắt buộc và đúng format | Không được cập nhật | Không được cập nhật |
| `name` | Bắt buộc, không blank | Bắt buộc, không blank | Nếu xuất hiện phải không blank |
| `price` | Bắt buộc, không âm | Bắt buộc, không âm | Nếu xuất hiện phải là số không âm |
| `description` | Có thể null | Có thể null để bỏ mô tả | Vắng = giữ nguyên; null = xóa mô tả |
| Trường không biết | Chọn reject hoặc ignore có chủ đích | Chọn reject hoặc ignore có chủ đích | Nên reject các keys ngoài allowlist |
| Quyền sửa field | Server kiểm soát | Chỉ tập mutable fields | Chỉ tập mutable fields |

Một tập quy tắc **khác nhau theo hành động** không chỉ là chuyện annotation. Nó còn liên quan đến **field ownership, HTTP semantics, authorization, concurrent updates, transactions và cách merge dữ liệu**.

## 2. Ba chiến lược tổ chức validation

### Cách A — DTO riêng cho create và update (khuyến nghị mặc định)

~~~java
public record CreateProductRequest(
    @NotBlank String sku,
    @NotBlank String name,
    @NotNull @DecimalMin("0.00") BigDecimal price,
    @Size(max = 500) String description
) {
}

public record ReplaceProductRequest(
    @NotBlank String name,
    @NotNull @DecimalMin("0.00") BigDecimal price,
    @Size(max = 500) String description
) {
}
~~~

Đây là snippets; các class runnable với imports/constraints đầy đủ ở phần 9.

Ưu điểm:

- Contract của từng endpoint **hiện rõ trên DTO**.
- `sku` không xuất hiện trong DTO cập nhật; giảm nguy cơ mass assignment.
- API docs/OpenAPI rõ hơn về required fields của POST và PUT.
- Test dễ đọc, không cần nhớ group nào đang chạy.
- Dễ tiến hóa khi hai API diverge theo thời gian.

Nhược điểm: có thể lặp lại annotations ở những field chung. Với các API nhỏ và vừa, **một chút duplication trong request contract thường tốt hơn abstraction che giấu khác biệt nghiệp vụ**.

### Cách B — Một model và Bean Validation groups

~~~java
public record GroupedProductInput(
    @NotBlank String name,
    @NotNull @DecimalMin("0.00") BigDecimal price,
    @NotBlank(groups = OnCreate.class) String sku
) {
}
~~~

Sau đó chọn groups theo endpoint với Spring `@Validated(...)`. Cách này phù hợp khi model có nhiều constraints chung và vài rule khác theo thao tác, nhưng **không làm cho field nguy hiểm tự biến mất khỏi object**. Bạn vẫn phải kiểm soát mapping/allowlist.

### Cách C — Kết hợp DTO riêng + groups ở bên trong

Có thể tổ chức **DTO tách biệt ở API boundary** nhưng dùng **custom reusable constraints**, composed constraints, shared validators hoặc groups ở những nested objects có logic thực sự thay đổi. Đây là cách giảm duplication mà vẫn giữ contract bên ngoài rõ ràng.

**Lựa chọn cho bài thực hành:** code POST/PUT chạy được sử dụng **DTO riêng**; phần 12 trình bày groups với unit tests độc lập. PATCH được giải thích riêng vì có ngữ nghĩa vắng mặt/null mà groups không tự giải quyết.

## 3. Vì sao một DTO với mọi field nullable dễ gây lỗi?

Ví dụ dễ mắc:

~~~java
public record ProductRequest(
    String sku,
    String name,
    BigDecimal price,
    String description
) {
}
~~~

Nếu không có validation hoặc conditional checks, POST có thể tạo sản phẩm thiếu SKU, PUT có thể lưu name null và service có thể quên kiểm tra một field. Thêm `@NotNull` cho tất cả lại làm PATCH không thể chỉ cập nhật một field.

Một phản ví dụ thứ hai:

~~~java
public record ProductRequest(
    @NotBlank String sku,
    @NotBlank String name,
    @NotNull BigDecimal price
) {
}
~~~

Nếu dùng chính DTO này cho PUT, client phải gửi lại `sku`. Nếu mapper vô tình gán SKU từ body vào entity, client có thể sửa trường đáng lẽ bất biến.

**Nguyên tắc thiết kế:** cần phân biệt **trường bắt buộc**, **trường được phép sửa** và **trường có mặt trong request**. `@NotNull` chỉ giải quyết một phần đầu tiên; nó không giải quyết hai phần sau.

### Entity khác request DTO

Một entity thường có thêm `id`, `ownerId`, `role`, `status`, `createdAt`, `version` và quan hệ nội bộ. Không nên bind `@RequestBody`/`@ModelAttribute` trực tiếp vào JPA managed entity rồi để client quyết định những fields nào đổi.

Flow nên là:

~~~text
HTTP body -> Request DTO -> Validation -> Authorization
                                |
                                v
                     Service / domain invariants
                                |
                                v
                    Explicit allowed-field mapping
                                |
                                v
                   Transaction + repository/entity
~~~

Từng thao tác POST/PUT/PATCH có thể dùng DTO/command và mapping riêng.

## 4. Ý nghĩa của các annotations thường dùng

| Annotation | Điều kiện | Null có hợp lệ không? | Ghi chú |
|---|---|---|---|
| `@NotNull` | Giá trị khác null | Không | Không kiểm tra chuỗi blank |
| `@NotBlank` | CharSequence có nội dung không trắng | Không | Hợp cho tên/SKU bắt buộc |
| `@NotEmpty` | Collection/String/array/map khác rỗng | Không | Chuỗi chỉ spaces vẫn có độ dài |
| `@Size(min,max)` | Độ dài/số phần tử trong khoảng | Thường có | Kết hợp NotNull/NotBlank nếu bắt buộc |
| `@DecimalMin("0.00")` | Numeric ≥ 0.00 | Thường có | Hợp cho BigDecimal |
| `@Positive` | Số > 0 | Thường có | Giá bằng 0 không hợp lệ nếu dùng Positive |
| `@Pattern` | Chuỗi khớp regex | Thường có | Không thay `@NotBlank` |
| `@Email` | Định dạng email theo provider | Thường có | Không xác minh sở hữu email |
| `@Valid` | Cascaded validation | Bỏ qua nested null | Không phải constraint bản thân nó |
| `@Validated(...)` | Spring activation/groups | Không có nghĩa “null-safe” | Dùng đúng vị trí Spring MVC |

Ví dụ tạo mới SKU:

~~~java
@NotBlank
@Size(min = 3, max = 32)
@Pattern(regexp = "[A-Z0-9-]+")
String sku
~~~

`@Pattern` kiểm tra định dạng; `@Size` kiểm tra độ dài; `@NotBlank` từ chối null/blank. Với các constraints này, **không dựa vào thứ tự khai báo annotation để suy ra thứ tự chạy**.

### Giá là BigDecimal, không nên dùng double cho tiền

Trong Java, `BigDecimal` diễn tả giá trị thập phân một cách phù hợp hơn `double` khi làm số tiền. `@DecimalMin("0.00")` là kiểm tra giá không âm; vẫn cần kiểm tra precision/scale, đơn vị tiền tệ, quy tắc làm tròn và giới hạn tối đa ở domain layer/DB schema.

Nếu hệ thống cho giá bằng 0, không dùng `@Positive`. Nếu giá phải strictly positive, có thể dùng `@DecimalMin(value="0.00",inclusive=false)` hoặc `@Positive` theo kiểu dữ liệu phù hợp.

## 5. POST create: ranh giới validation

Endpoint POST nhận `CreateProductRequest`:

~~~java
@PostMapping
public ResponseEntity<Product> create(
        @Valid @RequestBody CreateProductRequest request) {
    Product result = service.create(request);
    return ResponseEntity.created(
        URI.create("/api/products/" + result.id()))
        .body(result);
}
~~~

Khi có provider, `@Valid` ở argument khiến Spring MVC validate DTO sau bước JSON deserialization. Nếu một constraint sai, đối với một command object thông thường, Spring MVC có thể ném **`MethodArgumentNotValidException`** và mặc định trả HTTP **400** trước khi body method chạy.

Nhưng có các ngoại lệ về cơ chế:

- Nếu method có **direct constraint annotations trên parameter/return value**, Spring MVC 6.1+ có thể dùng method validation và exception `HandlerMethodValidationException` thay vì argument validation riêng.
- Nếu handler đặt `Errors`/`BindingResult` **ngay sau** argument, có thể xử lý lỗi cục bộ.
- Nếu provider không có trên classpath, annotation có thể không chạy như mong đợi.
- `@Valid` không validate một DTO đã được tạo ngoài controller khi code gọi service Java trực tiếp; service cần có boundary riêng nếu đó là requirement.

Để giảm nhập nhằng trong ví dụ, controller **không đặt `@Validated` cấp class**, không có direct constraints trên `@PathVariable` và không nhận `BindingResult`. Vì vậy các test có thể kiểm tra `MethodArgumentNotValidException` ở DTO input khi phù hợp.

### POST không phải PUT với ID bằng null

Đừng gộp hai thao tác bằng cách chấp nhận request `id=null` rồi gọi create, còn `id!=null` thì update. Điều này làm API khó bảo vệ quyền, khó kiểm tra idempotency và khó mô tả required fields. Path/method nên thể hiện ý định nghiệp vụ.

## 6. PUT update: full update của phần tài nguyên được phép sửa

Endpoint:

~~~http
PUT /api/products/42
Content-Type: application/json

{
  "name": "Bút xanh cao cấp",
  "price": 25.00,
  "description": "Nét mực đều"
}
~~~

Trong contract của ví dụ:

- `id=42` lấy từ **path**.
- `sku` không được sửa, không nằm trong `ReplaceProductRequest`.
- `name` và `price` bắt buộc như một **đại diện đầy đủ của các mutable fields**.
- `description` vắng/null được hiểu là bỏ mô tả, vì đây là full replacement theo contract này.
- Service lấy resource hiện có, kiểm tra quyền và thay **chỉ các fields được phép**.
- Nếu resource không tồn tại, trả HTTP **404**.
- Nếu có optimistic locking, cần `ETag/If-Match` hoặc field version và xử lý HTTP 409/412 tùy contract.

Không đánh đồng PUT với PATCH: một PUT chỉ gửi `{"name":"Bút mới"}` sẽ bị HTTP 400 vì thiếu `price` trong ví dụ. Đây là behavior **có chủ đích**, không phải Spring mặc định quyết định như vậy.

### PUT và idempotency

Một request PUT hoàn chỉnh gọi nhiều lần với **cùng resource state** nên dẫn tới cùng kết quả tài nguyên cuối cùng, dù response metadata có thể khác tùy hệ thống. Nếu muốn idempotent update, tránh tạo record/event không có deduplication chỉ vì cùng request được retry.

Đối với POST create, idempotency không được bảo đảm chỉ vì request giống nhau. Hệ thống có thể cần idempotency key/unique SKU policy trong service.

## 7. PATCH: ba trạng thái — absent, null, có giá trị

PATCH khác PUT vì **chỉ gửi những fields muốn sửa**.

Ví dụ tài nguyên hiện tại:

~~~json
{
  "name": "Bút xanh",
  "price": 19.90,
  "description": "Loại thường"
}
~~~

Ba body có ý nghĩa khác nhau:

~~~json
{"name":"Bút xanh mới"}
~~~

- `name` có mặt và mới → cập nhật name.
- `price` vắng → giữ nguyên price.
- `description` vắng → giữ nguyên description.

~~~json
{"description":null}
~~~

- `description` có mặt với null → xóa mô tả theo contract JSON Merge Patch nếu được dùng.
- Các fields khác vắng → giữ nguyên.

~~~json
{"price":null}
~~~

- `price` có mặt với null → theo chính sách demo **không hợp lệ**, vì price bắt buộc của resource sau merge.

### Vì sao `record PatchRequest(String name, BigDecimal price)` không đủ?

Khi Jackson deserialize Java record thông thường, **property vắng mặt** và **property có mặt với JSON null** thường đều dẫn đến Java `null`, nếu không dùng cơ chế lưu presence riêng. Không thể chỉ viết:

~~~java
if (patch.price() != null) {
    current.setPrice(patch.price());
}
~~~

rồi khẳng định đã hỗ trợ đầy đủ PATCH: câu lệnh này xem **explicit null** như “không sửa”, nên không thể diễn đạt clear field, và còn che giấu lỗi client muốn set required field thành null.

### Các lựa chọn cho PATCH

1. **JSON Merge Patch (RFC 7396):** định nghĩa null như xóa member trong merge; áp dụng với quy tắc nghiệp vụ cần được kiểm tra trên kết quả.
2. **JSON Patch (RFC 6902):** tập operations add/remove/replace theo path và content type riêng; phải validate paths và authorization.
3. **Presence wrapper:** loại biểu diễn như `PatchField<T>` với `present: boolean`, `value: T` cùng Jackson deserializer hoặc library phù hợp.
4. **`JsonNode/ObjectNode` cho tập fields nhỏ:** phân biệt `node.has("field")` và `node.get("field").isNull()` rồi map có kiểm soát.
5. **Endpoint riêng theo hành động** nếu tài nguyên có logic cập nhật phức tạp, tránh mọi trường hợp PATCH chung chung.

Dù dùng cách nào, quy trình an toàn là:

~~~text
Read current resource + authorization
        |
        v
Parse PATCH with presence information
        |
        v
Reject unsupported paths/fields
        |
        v
Apply patch to a COPY / immutable candidate
        |
        v
Validate final candidate + cross-field invariants
        |
        v
Check version/concurrency
        |
        v
Persist atomically and publish effects safely
~~~

**Chỉ validate fragment nhận vào là không đủ:** quan hệ giữa field mới và giá trị cũ có thể vi phạm domain rule. Sau merge phải validate **trạng thái cuối cùng**.

## 8. Một vài cách PATCH dễ sai

### Sai: dùng chung validation của POST

~~~java
public void patch(
    @Valid @RequestBody CreateProductRequest request) {
    // ...
}
~~~

Client chỉ muốn sửa description nhưng bị `@NotBlank` trên SKU/name từ chối. Bỏ `@NotBlank` để sửa PATCH sẽ khiến POST mất yêu cầu bắt buộc.

### Sai: để nhóm update chỉ kiểm tra field có giá trị khác null

Một group như `@NotBlank(groups=Create.class)` và bỏ constraint khi Update có thể làm **PUT nhận thiếu name**. Với PUT full-replacement, name vẫn phải bắt buộc.

### Sai: validate mỗi field trước khi merge

Một update price có thể làm vi phạm rule giá/giảm giá phụ thuộc category của entity. Đôi khi cần validation cả input fragment lẫn candidate hoàn chỉnh.

### Sai: bind PATCH trực tiếp vào JPA managed entity

Nếu một field convert/validate thất bại sau khi những field khác đã gắn, entity có thể đã mutate một phần; tránh dirty checking side effects. Bind vào một DTO/copy, validate rồi mới chuyển những field được phép vào entity.

### Sai: cho PATCH cập nhật mọi field mà entity có setter

Client gửi `id`, `sku`, `ownerId`, `stock` hoặc `status` mà mapper blind-copy, gây mass assignment. Field allowlist là quyết định quyền, **validation groups không cung cấp property-level authorization**.

## 9. Dự án thực hành chạy được: DTO riêng cho POST và PUT

Tạo project Spring Boot 3.5.x, Java 17 với starters **Spring Web**, **Validation** và **Spring Boot Starter Test**. Ứng dụng lưu dữ liệu **in-memory** để tập trung vào validation, không cần database.

Cấu trúc:

~~~text
product-validation/
  build.gradle
  src/main/resources/application.properties
  src/main/java/com/example/productvalidation/
    ProductValidationApplication.java
    CreateProductRequest.java
    ReplaceProductRequest.java
    ProductService.java
    ProductController.java
    ProductGroups.java
    GroupedProductInput.java
  src/test/java/com/example/productvalidation/
    ProductControllerTest.java
    ProductServiceTest.java
    GroupedProductValidationTest.java
~~~

File `build.gradle` ở project đã cấu hình Spring Boot plugin và dependency management tương ứng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Không dùng `javax.validation.*` trong Boot 3; sử dụng `jakarta.validation.*`.

### 9.1. `application.properties`

`src/main/resources/application.properties`:

~~~properties
# Chọn chính sách reject thuộc tính JSON ngoài request DTO.
spring.jackson.deserialization.fail-on-unknown-properties=true
~~~

Đây là feature Jackson trên `ObjectMapper` do Spring Boot quản lý, không thay thế authorization. Việc bật toàn ứng dụng có thể ảnh hưởng backward compatibility với clients đã gửi extra fields; trong production cân nhắc scope riêng hoặc versioning trước khi áp dụng.

**Tại sao chủ động reject unknown fields?** Nếu client gửi `sku` trong PUT dù DTO không có `sku`, nhiều cấu hình Jackson mặc định có thể **ignore** thay vì reject. Cả hai là lựa chọn contract; bài này dùng **strict rejection** để minh họa bảo vệ field bất biến.

### 9.2. `ProductValidationApplication.java`

`src/main/java/com/example/productvalidation/ProductValidationApplication.java`:

~~~java
package com.example.productvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProductValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ProductValidationApplication.class, args);
    }
}
~~~

### 9.3. `CreateProductRequest.java`

`src/main/java/com/example/productvalidation/CreateProductRequest.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
    @NotBlank
    @Size(min = 3, max = 32)
    @Pattern(regexp = "[A-Z0-9-]+")
    String sku,

    @NotBlank
    @Size(max = 100)
    String name,

    @NotNull
    @DecimalMin("0.00")
    BigDecimal price,

    @Size(max = 500)
    String description
) {
}
~~~

Khi POST, `sku` là bắt buộc vì `@NotBlank`. `@Pattern` kiểm tra uppercase ASCII digits/hyphen, không chạy chuẩn hóa thay cho caller. Với `price`, dùng `@NotNull` cùng `@DecimalMin` vì một `@DecimalMin` đơn lẻ không tự reject null.

### 9.4. `ReplaceProductRequest.java`

`src/main/java/com/example/productvalidation/ReplaceProductRequest.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record ReplaceProductRequest(
    @NotBlank
    @Size(max = 100)
    String name,

    @NotNull
    @DecimalMin("0.00")
    BigDecimal price,

    @Size(max = 500)
    String description
) {
}
~~~

So với Create DTO:

- Không có `sku`; không thể truyền SKU vào immutable command của replace.
- `name` và `price` vẫn bắt buộc, vì đây là **PUT**, không phải PATCH.
- `description` có thể null.
- `id` không có trong cả hai DTO; service tạo hoặc xác định từ path.

### 9.5. `ProductService.java`

`src/main/java/com/example/productvalidation/ProductService.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProductService {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentHashMap<Long, Product> products =
        new ConcurrentHashMap<>();

    public Product create(CreateProductRequest request) {
        long id = nextId.incrementAndGet();

        Product created = new Product(
            id,
            request.sku(),
            request.name(),
            request.price(),
            request.description());

        products.put(id, created);
        return created;
    }

    public Product replace(
            long id, ReplaceProductRequest request) {

        Product updated = products.computeIfPresent(
            id, (key, previous) -> new Product(
                previous.id(),
                previous.sku(), // SKU cũ, không lấy từ body.
                request.name(),
                request.price(),
                request.description()));

        if (updated == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Product not found");
        }
        return updated;
    }

    public Product find(long id) {
        Product found = products.get(id);
        if (found == null) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Product not found");
        }
        return found;
    }

    public record Product(
        long id,
        String sku,
        String name,
        BigDecimal price,
        String description
    ) {
    }
}
~~~

**Quan trọng:** đây là **service minh họa in-memory**, không phải một bản triển khai production có đầy đủ uniqueness, idempotency, database transaction, optimistic locking hoặc authorization.

`ConcurrentHashMap.computeIfPresent(...)` chỉ thay record khi key có mặt; giữ SKU cũ. Với database thật, bảo vệ SKU immutable và các invariants này **ở domain/service layer** kể cả khi controller đã validate DTO.

### 9.6. `ProductController.java`

`src/main/java/com/example/productvalidation/ProductController.java`:

~~~java
package com.example.productvalidation;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService products;

    public ProductController(ProductService products) {
        this.products = products;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ProductService.Product> create(
            @Valid @RequestBody CreateProductRequest request) {

        ProductService.Product created =
            products.create(request);

        return ResponseEntity.created(
            URI.create("/api/products/" + created.id()))
            .body(created);
    }

    @PutMapping(
        value = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<ProductService.Product> replace(
            @PathVariable long id,
            @Valid @RequestBody ReplaceProductRequest request) {

        ProductService.Product result =
            products.replace(id, request);

        return ResponseEntity.ok(result);
    }

    @GetMapping("/{id}")
    public ProductService.Product get(@PathVariable long id) {
        return products.find(id);
    }
}
~~~

Cả POST và PUT đều dùng `@Valid`, nhưng **khác DTO class** nên validation rules tự nhiên khác nhau. Controller không nhận entity và không map trực tiếp `id`, `sku` từ update body.

### 9.7. Chạy bằng Gradle

Từ thư mục project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu máy chỉ có Gradle và chưa có wrapper, dùng `gradle wrapper` từ project đã được cấu hình phù hợp, rồi chạy wrapper.

### 9.8. Gọi API

Tạo sản phẩm:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/products" \
  -H "Content-Type: application/json" \
  -d '{"sku":"PEN-001","name":"But xanh","price":19.90,"description":"But bi"}'
~~~

Trên app mới chỉ có một request tạo, kỳ vọng HTTP **201 Created**, header `Location: /api/products/1` và body:

~~~json
{
  "id": 1,
  "sku": "PEN-001",
  "name": "But xanh",
  "price": 19.90,
  "description": "But bi"
}
~~~

ID có thể khác nếu app đã nhận các requests khác; đừng hard-code ID trong test dữ liệu dùng chung.

PUT thay thế các mutable fields:

~~~bash
curl -i -X PUT \
  "http://localhost:8080/api/products/1" \
  -H "Content-Type: application/json" \
  -d '{"name":"But xanh moi","price":25.00,"description":null}'
~~~

Kỳ vọng HTTP **200 OK**, `sku` vẫn `"PEN-001"`, `name` mới, `price` mới và `description` null. Với production, cần xác thực user có quyền update ID=1 trước khi thay đổi.

POST thiếu SKU:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/products" \
  -H "Content-Type: application/json" \
  -d '{"name":"But xanh","price":19.90}'
~~~

Kỳ vọng HTTP **400 Bad Request** vì SKU cần cho create.

PUT thiếu giá:

~~~bash
curl -i -X PUT \
  "http://localhost:8080/api/products/1" \
  -H "Content-Type: application/json" \
  -d '{"name":"But xanh moi"}'
~~~

Kỳ vọng HTTP **400** vì `price=null` vi phạm `@NotNull` trong Replace DTO.

PUT cố sửa SKU:

~~~bash
curl -i -X PUT \
  "http://localhost:8080/api/products/1" \
  -H "Content-Type: application/json" \
  -d '{"sku":"HACKED","name":"But moi","price":25.00}'
~~~

Do cấu hình strict Jackson unknown-field ở trên, kỳ vọng HTTP **400** từ **JSON deserialization**, không phải từ `@NotBlank`. Nếu bỏ strict setting, Jackson có thể bỏ qua SKU; dù vậy service vẫn không bao giờ lấy SKU từ Replace DTO.

## 10. MockMvc tests cho POST và PUT

`src/test/java/com/example/productvalidation/ProductControllerTest.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private ProductService service;

    @Test
    void createValidReturns201AndLocation() throws Exception {
        var product = new ProductService.Product(
            42L, "PEN-001", "Pen",
            new BigDecimal("19.90"), "Blue");

        when(service.create(any(CreateProductRequest.class)))
            .thenReturn(product);

        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"PEN-001\",\"name\":\"Pen\","
                    + "\"price\":19.90,\"description\":\"Blue\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                "Location", "/api/products/42"))
            .andExpect(jsonPath("$.sku").value("PEN-001"))
            .andExpect(jsonPath("$.price").value(19.90));

        verify(service).create(
            new CreateProductRequest(
                "PEN-001", "Pen",
                new BigDecimal("19.90"), "Blue"));
    }

    @Test
    void createBlankSkuReturns400BeforeService()
            throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"\",\"name\":\"Pen\","
                    + "\"price\":19.90}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("sku"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void createBlankNameReturns400BeforeService()
            throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"PEN-001\",\"name\":\" \","
                    + "\"price\":19.90}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("name"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void createNegativePriceIsRejected() throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"PEN-001\",\"name\":\"Pen\","
                    + "\"price\":-0.01}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("price"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void createMissingPriceIsRejected() throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"PEN-001\",\"name\":\"Pen\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("price"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void putValidUpdatesMutableFields() throws Exception {
        var product = new ProductService.Product(
            42L, "PEN-001", "New Pen",
            new BigDecimal("25.00"), null);

        when(service.replace(
                eq(42L),
                any(ReplaceProductRequest.class)))
            .thenReturn(product);

        mvc.perform(put("/api/products/42")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"New Pen\","
                    + "\"price\":25.00,"
                    + "\"description\":null}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sku").value("PEN-001"))
            .andExpect(jsonPath("$.name").value("New Pen"));

        verify(service).replace(
            42L,
            new ReplaceProductRequest(
                "New Pen", new BigDecimal("25.00"), null));
    }

    @Test
    void putMissingNameIsRejected() throws Exception {
        mvc.perform(put("/api/products/42")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"price\":25.00}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("name"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void putNegativePriceIsRejected() throws Exception {
        mvc.perform(put("/api/products/42")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"New Pen\",\"price\":-2.00}"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException());
                assertTrue(ex.getBindingResult()
                    .hasFieldErrors("price"));
            });

        verifyNoInteractions(service);
    }

    @Test
    void putUnknownSkuFieldIsRejected() throws Exception {
        mvc.perform(put("/api/products/42")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"sku\":\"HACKED\","
                    + "\"name\":\"New Pen\",\"price\":25.00}"))
            .andExpect(status().isBadRequest());

        // Bị từ chối trước khi service cập nhật SKU.
        verifyNoInteractions(service);
    }

    @Test
    void putMissingResourceReturns404() throws Exception {
        when(service.replace(
                eq(404L),
                any(ReplaceProductRequest.class)))
            .thenThrow(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Product not found"));

        mvc.perform(put("/api/products/404")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"New Pen\",\"price\":25.00}"))
            .andExpect(status().isNotFound());
    }
}
~~~

**Mười MockMvc tests** kiểm tra: POST hợp lệ 201/Location, POST thiếu SKU/name/price hoặc giá âm, PUT hợp lệ với SKU giữ nguyên, PUT thiếu name/giá âm, không chấp nhận SKU không thuộc update DTO và PUT tài nguyên không tồn tại trả 404.

Những test có input sai dùng `verifyNoInteractions(service)`, nên không chỉ assert HTTP 400 mà còn bảo đảm **không gọi service trước khi validation hoàn tất**.

**Lưu ý:** `@WebMvcTest` kiểm tra slice MVC và đọc properties trong test context, nhưng không đi qua reverse proxy/API gateway. Nếu ứng dụng có Spring Security filters, cần thêm test authentication/CSRF hợp lệ. Nếu cấu hình ObjectMapper custom, phải xác minh strict unknown-field vẫn có hiệu lực.

## 11. Unit tests cho service: SKU bất biến sau PUT

`src/test/java/com/example/productvalidation/ProductServiceTest.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ProductServiceTest {

    @Test
    void replaceKeepsSkuAssignedOnCreate() {
        ProductService service = new ProductService();

        var first = service.create(
            new CreateProductRequest(
                "PEN-001", "Pen",
                new BigDecimal("19.90"), "Blue"));

        var result = service.replace(
            first.id(),
            new ReplaceProductRequest(
                "Updated Pen",
                new BigDecimal("25.00"), null));

        assertEquals(first.id(), result.id());
        assertEquals("PEN-001", result.sku());
        assertEquals("Updated Pen", result.name());
        assertEquals(new BigDecimal("25.00"), result.price());
        assertEquals(null, result.description());
    }

    @Test
    void replacingUnknownIdDoesNotCreateRecord() {
        ProductService service = new ProductService();

        ResponseStatusException ex = assertThrows(
            ResponseStatusException.class,
            () -> service.replace(
                999L,
                new ReplaceProductRequest(
                    "Pen", new BigDecimal("10.00"), null)));

        assertEquals(HttpStatus.NOT_FOUND, ex.getStatusCode());
    }
}
~~~

**Hai tests** xác minh invariant không phụ thuộc Controller: SKU không đổi sau PUT và update ID không tồn tại không biến thành create. Đây là minh họa vì service trong demo chưa có authorization; trong production invariants phải kiểm tra trong transaction và có kiểm thử race conditions.

### Chạy

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Các tests nêu ở phần này được thiết kế phù hợp Boot 3.5/Spring 6.2 và được soát tĩnh; **bài viết không tuyên bố đã thực thi Gradle**.

## 12. Thay thế: dùng Bean Validation groups cho create/update

Khi DTO có nhiều fields chung và sự khác biệt thực sự chỉ là một vài constraints, Bean Validation groups cho phép chọn **tập constraint** theo thao tác.

### 12.1. Marker interfaces

`src/main/java/com/example/productvalidation/ProductGroups.java`:

~~~java
package com.example.productvalidation;

public final class ProductGroups {

    private ProductGroups() {
    }

    public interface OnCreate {
    }

    public interface OnUpdate {
    }
}
~~~

Đây là những **marker interfaces**, không chứa method. Jakarta Validation dùng `Class<?>` của chúng để gán constraints vào groups. Chúng không tự kích hoạt bất kỳ validation nào.

### 12.2. Shared DTO có group-specific rules

`src/main/java/com/example/productvalidation/GroupedProductInput.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record GroupedProductInput(
    @NotBlank
    String name,

    @NotNull
    @DecimalMin("0.00")
    BigDecimal price,

    @NotBlank(groups = ProductGroups.OnCreate.class)
    String sku,

    @Size(max = 10, groups = ProductGroups.OnUpdate.class)
    String updateReason
) {
}
~~~

Ở đây:

- `name`, `price` thuộc **Default group** vì không nêu `groups`.
- `sku` chỉ được kiểm tra khi `OnCreate` được chọn.
- `updateReason` chỉ được kiểm tra khi `OnUpdate` được chọn.
- **Không có field-level authorization:** dù `sku` không được kiểm tra trong group Update, property vẫn nằm trên DTO. Service **không được dùng** giá trị này để thay SKU.

**Nhấn mạnh:** `@NotBlank(groups=OnCreate.class)` không có nghĩa “cấm gửi SKU trong update”. Nó chỉ nói constraint `NotBlank` thuộc một group. Nếu client gửi SKU mới, property vẫn có thể được deserialize — trừ khi API/mapper/DTO rules chặn riêng.

### 12.3. Chọn group trong Spring MVC

Với grouped DTO:

~~~java
@PostMapping("/grouped")
public ResponseEntity<?> createGrouped(
    @Validated({
        Default.class,
        ProductGroups.OnCreate.class
    })
    @RequestBody GroupedProductInput input
) {
    // ...
}
~~~

và:

~~~java
@PutMapping("/grouped/{id}")
public ResponseEntity<?> replaceGrouped(
    @PathVariable long id,
    @Validated({
        Default.class,
        ProductGroups.OnUpdate.class
    })
    @RequestBody GroupedProductInput input
) {
    // ...
}
~~~

Đây là **snippets** ngoài controller chạy được ở phần 9; cần các imports Spring/Jakarta tương ứng. Không tự thêm routes như trên vào project chính nếu không muốn dùng group-based API.

Vì sao chọn **`Default.class` tường minh**?

Constraint không khai báo groups thuộc `Default`. Khi bạn viết:

~~~java
@Validated(ProductGroups.OnCreate.class)
~~~

mà `OnCreate` không extends `Default`, những constraints chỉ thuộc Default như `name`/`price` **không tự động được thực thi**. Để tránh bỏ sót, ví dụ này yêu cầu cả hai groups:

~~~java
@Validated({Default.class, ProductGroups.OnCreate.class})
~~~

Một lựa chọn khác là tạo interface `OnCreate extends Default` để áp dụng inheritance rõ ràng, nhưng cần thống nhất toàn codebase và test. Đừng suy ra Spring tự thêm Default khi chọn một custom group bất kỳ.

### 12.4. Test groups trực tiếp với Jakarta Validator

`src/test/java/com/example/productvalidation/GroupedProductValidationTest.java`:

~~~java
package com.example.productvalidation;

import java.math.BigDecimal;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import jakarta.validation.groups.Default;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class GroupedProductValidationTest {

    @Autowired
    private Validator validator;

    private static GroupedProductInput badAll() {
        return new GroupedProductInput(
            "",
            new BigDecimal("-1.00"),
            "",
            "reason-exceeds-ten-characters");
    }

    private Set<String> fields(Class<?>... groups) {
        Set<ConstraintViolation<GroupedProductInput>> results =
            validator.validate(badAll(), groups);

        return results.stream()
            .map(v -> v.getPropertyPath().toString())
            .collect(Collectors.toSet());
    }

    @Test
    void createRunsDefaultPlusCreateRules() {
        Set<String> errors = fields(
            Default.class, ProductGroups.OnCreate.class);

        assertEquals(3, errors.size());
        assertTrue(errors.contains("name"));
        assertTrue(errors.contains("price"));
        assertTrue(errors.contains("sku"));
        assertFalse(errors.contains("updateReason"));
    }

    @Test
    void updateRunsDefaultPlusUpdateRules() {
        Set<String> errors = fields(
            Default.class, ProductGroups.OnUpdate.class);

        assertEquals(3, errors.size());
        assertTrue(errors.contains("name"));
        assertTrue(errors.contains("price"));
        assertTrue(errors.contains("updateReason"));
        assertFalse(errors.contains("sku"));
    }

    @Test
    void updateGroupAloneDoesNotImplicitlyRunDefault() {
        Set<String> errors = fields(
            ProductGroups.OnUpdate.class);

        assertEquals(Set.of("updateReason"), errors);
    }
}
~~~

**Ba tests** chứng minh:

- Create áp dụng Default + OnCreate, nên lỗi ở `name`, `price`, `sku`.
- Update áp dụng Default + OnUpdate, nên lỗi ở `name`, `price`, `updateReason`.
- Chỉ chọn OnUpdate sẽ **bỏ qua Default** trong ví dụ này, là regression phổ biến nhất khi dùng groups.

**Tổng cộng project có 15 `@Test` methods**: 10 MockMvc + 2 service + 3 grouped-provider tests. Cả nhóm DTO riêng và groups có ví dụ và tests riêng, nhưng routes sản phẩm chính chỉ dùng DTO riêng.

## 13. Validation groups không phải field permissions

Đây là bẫy bảo mật quan trọng:

~~~java
public record SharedAccount(
    @NotBlank(groups = Create.class)
    String email,

    String role
) {
}
~~~

Kể cả khi Update không chạy `NotBlank` trên email, field `role` vẫn có thể được deserialize. Nếu service blind-copy:

~~~java
entity.setRole(input.role());
~~~

thì validation groups không bảo vệ quyền sửa vai trò. Đó là **mass assignment**.

**Giải pháp:** DTO riêng cho từng action, allowlist, mapping tường minh và authorization service. Không dùng Jakarta constraint selection để quyết định field nào client được phép thay đổi.

### Validation groups cũng không điều khiển schema JSON

Jackson vẫn deserialize property theo JSON mapping rules. Nhóm Bean Validation không tự ẩn field trong OpenAPI, không từ chối unknown properties và không chọn các setter được phép chạy.

Nếu cần một field chỉ hợp lệ trong POST mà hoàn toàn bị cấm trong PUT, **không chỉ “bỏ constraint khỏi Update group”**. Hãy loại field khỏi Replace DTO hoặc dùng cơ chế mapping/validation input rõ ràng.

## 14. Group inheritance, sequence và group conversion

### Group inheritance

Jakarta Validation cho phép groups kế thừa nhau:

~~~java
public interface BaseChecks {
}

public interface CreateChecks extends BaseChecks {
}
~~~

Nếu validate `CreateChecks`, những constraints thuộc `BaseChecks` cũng được xem xét theo inheritance. Nếu muốn chạy Default group khi chọn Create, có thể tổ chức `CreateChecks extends Default`; nhưng các ràng buộc nhóm cần có convention, không trộn lẫn nhiều style không kiểm soát.

### `@GroupSequence`

Thông thường, các constraints trong nhiều groups **không có thứ tự thực thi bảo đảm**. Khi muốn chạy constraints rẻ/đơn giản trước rồi mới đến nhóm đắt hơn, có thể dùng:

~~~java
@GroupSequence({
    Default.class,
    ProductGroups.OnCreate.class
})
public interface OrderedCreateChecks {
}
~~~

Đây là snippet cần interface `OrderedCreateChecks` và imports. Khi một group sớm trong sequence có violations, các groups về sau **không được chạy** trong sequence đó.

Không dùng `@GroupSequence` như một API quyền sửa trường. Nó giải quyết **validation ordering**, và phải kiểm tra rule khi dùng group sequence redefining Default trên class (khác với sequence interface).

### `@ConvertGroup` khi cascade nested objects

Nếu root và nested DTO dùng group names khác, bạn có thể chuyển group khi `@Valid` đi sâu:

~~~java
public record OrderInput(
    @Valid
    @ConvertGroup(
        from = ProductGroups.OnCreate.class,
        to = AddressChecks.class
    )
    AddressInput address
) {
}
~~~

Đây là snippet cần định nghĩa `AddressInput`/`AddressChecks` và import `jakarta.validation.groups.ConvertGroup`. `@ConvertGroup` **phải đi cùng `@Valid`**; chỉ áp dụng tại điểm cascade. Nó không thay group của root object, không phải chuyển đổi JSON field và cũng không chạy recursively qua một chuỗi mapping groups tùy ý.

Nếu rule ở `AddressInput` vẫn thuộc Default nhưng bạn chọn `OnCreate` tại root, nested validation có thể không đánh giá Default như bạn kỳ vọng. Khi đó cần thiết kế group inheritance/conversion rõ, rồi test `ConstraintViolation.getPropertyPath()` cho nested path.

## 15. Mẫu thiết kế PATCH có kiểm tra kết quả sau merge

Với ứng dụng cần PATCH, đừng chỉ đánh dấu mọi field nullable rồi dùng `@Valid`. Ví dụ thao tác thủ công có kiểm soát với Jackson `JsonNode`:

~~~java
// Snippet trong service/controller, không phải file độc lập.
// current: Product có name(), price(), description().
// patch: ObjectNode/JsonNode đã được parse.
// validator: jakarta.validation.Validator.

if (!patch.isObject()) {
    throw new ResponseStatusException(
        HttpStatus.BAD_REQUEST, "Patch must be an object");
}

Set<String> allowed =
    Set.of("name", "price", "description");

Iterator<String> keys = patch.fieldNames();
while (keys.hasNext()) {
    if (!allowed.contains(keys.next())) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Unknown patch field");
    }
}

String name = current.name();
BigDecimal price = current.price();
String description = current.description();

if (patch.has("name")) {
    JsonNode value = patch.get("name");
    if (!value.isTextual()) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Invalid name type");
    }
    name = value.asText();
}

if (patch.has("price")) {
    JsonNode value = patch.get("price");
    if (!value.isNumber()) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Invalid price type");
    }
    price = value.decimalValue();
}

if (patch.has("description")) {
    JsonNode value = patch.get("description");
    if (value.isNull()) {
        description = null;
    }
    else if (value.isTextual()) {
        description = value.asText();
    }
    else {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "Invalid description type");
    }
}

ReplaceProductRequest candidate =
    new ReplaceProductRequest(name, price, description);

Set<ConstraintViolation<ReplaceProductRequest>> errors =
    validator.validate(candidate);

if (!errors.isEmpty()) {
    throw new ResponseStatusException(
        HttpStatus.BAD_REQUEST, "Invalid patch result");
}

// Sau authorization + concurrency check:
// service.applyValidatedCandidate(id, candidate);
~~~

Các imports cần thiết gồm `java.util.Set`, `java.util.Iterator`, `java.math.BigDecimal`, `com.fasterxml.jackson.databind.JsonNode`, `org.springframework.http.HttpStatus`, `org.springframework.web.server.ResponseStatusException` và `jakarta.validation.ConstraintViolation`. Snippet cố ý không thuộc project chạy được, vì muốn nhấn mạnh **merge + validate** chứ không giả vờ một PATCH endpoint đầy đủ đã xử lý transaction, ETag, JSON Merge Patch chuẩn RFC hoặc authorization.

Một điểm quan trọng: trong snippet, **`price:null` bị từ chối vì `!value.isNumber()`**; `name:null` bị từ chối; `description:null` được phép xóa. Các key vắng mặt giữ giá trị cũ.

**Đừng gọi đoạn này là một implementation RFC 7396 đầy đủ:** nó chỉ xử lý ba fields cấp 1 với semantics đã chọn. RFC 7396 còn có quy tắc đệ quy với objects; nếu công bố content type `application/merge-patch+json`, phải triển khai đúng RFC và test đầy đủ.

### Race condition của đọc–merge–ghi

Giả sử hai PATCH requests đọc cùng phiên bản tài nguyên:

~~~text
T1 đọc {name=A, price=10}
T2 đọc {name=A, price=10}
T1 đổi name -> B, ghi {name=B, price=10}
T2 đổi price -> 20, ghi {name=A, price=20}
~~~

Nếu không có version/locking, T2 có thể ghi đè thay đổi name của T1. Với DB thật, dùng optimistic locking (`@Version`), ETag/If-Match, row version hoặc transaction isolation phù hợp.

**Bean Validation không giải quyết concurrency.** Một candidate hợp lệ vẫn có thể bị stale; service phải re-check trong transaction.

## 16. Cross-field constraints: validate trạng thái cuối

Giả sử sản phẩm có `discountPrice` và yêu cầu `discountPrice <= price`. Nếu PATCH chỉ thay price xuống thấp hơn discountPrice đã lưu, kiểm tra riêng input field price là không đủ.

Cách đúng:

1. Load current resource theo ID và kiểm tra authorization.
2. Merge những fields được phép từ PATCH vào bản sao.
3. Validate candidate đã merge bằng `jakarta.validation.Validator` hoặc domain rule.
4. Chỉ khi hợp lệ mới ghi thay đổi.

Một class-level constraint:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = PriceRangeValidator.class)
public @interface ValidPriceRange {
    String message() default "Invalid price range";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Đây là snippet cần imports `java.lang.annotation.*`, `jakarta.validation.*` và implementation `PriceRangeValidator`. Không gắn nó vào object nhận PATCH fragment nếu chưa merge, vì constraints cross-field cần nhìn toàn trạng thái.

### Validation ở controller không thay thế domain invariant

Ngay cả khi controller đã `@Valid`, service có thể được gọi từ scheduled job, message listener, CLI, test khác hoặc một service khác. Những invariants cốt lõi (SKU immutable, quyền sửa, giá hợp lệ, trạng thái đơn hàng, uniqueness) vẫn cần được bảo vệ trong domain/service layer.

Một DTO đạt Bean Validation nhưng vi phạm business state vẫn phải bị từ chối. Có thể tạo domain exception riêng để map thành HTTP 409/422 khi phù hợp contract, không nhồi mọi tình huống vào `@NotNull`.

## 17. Service method validation: có cần `@Validated` ở service?

Nếu muốn validate method parameters **khi service được gọi từ nơi không đi qua MVC**, có thể dùng:

~~~java
@Service
@Validated
public class ProductCommandService {

    public void create(
            @Valid CreateProductRequest request) {
        // ...
    }
}
~~~

Đây là snippet minh họa: service class `@Validated` và lời gọi qua Spring-managed proxy có thể kích hoạt method-validation AOP. Nhưng:

- Chỉ gắn `@Valid` trên parameter rồi gọi `new ProductCommandService()` không tự kiểm tra.
- Self-invocation trong cùng bean thường bypass AOP proxy.
- Dùng service AOP cho validation là **lớp bổ sung**, không thay các domain checks.
- Có thể phát `ConstraintViolationException` hoặc adapted method-validation exception theo cấu hình thay vì `MethodArgumentNotValidException` của MVC.

Đừng thêm `@Validated` cấp class trên controller chỉ để “bật validation”; Spring MVC 6.1+ có built-in method validation và tài liệu khuyến nghị bỏ class-level `@Validated` trên controller nếu muốn dùng cơ chế đó.

## 18. Error handling theo thao tác

| Input | POST | PUT | PATCH |
|---|---|---|---|
| Thiếu `sku` | 400: SKU required | Không tồn tại trong DTO | Không được phép sửa |
| Name blank | 400 | 400 | 400 nếu name xuất hiện blank |
| Thiếu name | 400 | 400 | Hợp lệ: giữ nguyên name |
| Price âm | 400 | 400 | 400 nếu price xuất hiện âm |
| Thiếu price | 400 | 400 | Hợp lệ: giữ nguyên |
| Price null | 400 | 400 | 400 (required field của candidate) |
| Description null | Hợp lệ | Hợp lệ: clear | Hợp lệ: clear |
| Unknown field `role` | 400 nếu strict JSON | 400 nếu strict JSON | Reject theo allowlist |
| ID không tồn tại | Không áp dụng | 404 | 404 |
| Version stale | Không áp dụng | 409/412 theo contract | 409/412 theo contract |
| Không có quyền | 401/403 | 401/403 | 401/403 |

**Đây là chính sách của API mẫu**, không phải một bảng mã lỗi tự động áp dụng cho mọi ứng dụng Spring. Error status/ProblemDetail schema nên được định nghĩa nhất quán ở `@RestControllerAdvice` hoặc `ResponseEntityExceptionHandler`.

### Phân biệt lỗi parse, binding và validation

- JSON malformed/unknown property khi strict Jackson → thường `HttpMessageNotReadableException`.
- DTO vi phạm `@NotBlank`/`@DecimalMin` → thường `MethodArgumentNotValidException` khi MVC argument validation chạy.
- Direct method constraints → có thể `HandlerMethodValidationException`.
- Domain/business conflict → exception do service quyết định.
- Missing resource → `ResponseStatusException(HttpStatus.NOT_FOUND)` hoặc domain exception mapped 404.

Không dùng duy nhất status 400 để “chứng minh Bean Validation đã chạy”. Test nên kiểm tra đúng exception/field path ở những ca liên quan.

## 19. Chất lượng thông báo lỗi và i18n

Một `MethodArgumentNotValidException` chứa `BindingResult`, cho phép lấy:

~~~java
List<FieldError> fields =
    ex.getBindingResult().getFieldErrors();
~~~

Đây là snippet trong exception handler. Với API công khai, nên map thành error DTO ổn định như:

~~~json
{
  "code": "INVALID_INPUT",
  "issues": [
    {
      "field": "price",
      "code": "PRICE_BELOW_ZERO"
    }
  ]
}
~~~

Không đưa nguyên `BindingResult` hoặc `getRejectedValue()` vào response vì có thể lộ secrets, data riêng tư hoặc object graph nội bộ.

`MessageSource` giúp resolve các message codes của Spring/Bean Validation theo locale, nhưng không quyết định constraint được kích hoạt. Nếu muốn dùng messages cho create/update khác nhau, định nghĩa keys rõ ràng và test locale. Đừng gắn text message trực tiếp vào logic phân nhánh ở frontend; dùng machine-readable codes ổn định.

### Global error và nested path

Với class-level constraints, `BindingResult.getGlobalErrors()` có thể chứa lỗi không gắn với một field cụ thể. Với nested DTO, đường dẫn như `shippingAddress.postalCode` có thể xuất hiện; test không chỉ nhìn `getFieldError("postalCode")`.

Nếu API cần một lỗi cho nhiều fields, có thể trả `path="$object"` theo schema riêng, nhưng phải document rõ thay vì giả làm một property thật.

## 20. Test ma trận create/update quan trọng

| Tình huống | Assertion quan trọng |
|---|---|
| POST đầy đủ hợp lệ | 201, Location, service.create được gọi |
| POST thiếu SKU | 400, field `sku`, service không gọi |
| POST SKU format sai | 400, field `sku` |
| POST name blank | 400, field `name` |
| POST price âm | 400, field `price` |
| POST price null/missing | 400, field `price` |
| PUT name+price hợp lệ | 200, service.replace được gọi |
| PUT thiếu name | 400, field `name` |
| PUT thiếu price | 400, field `price` |
| PUT có sku ngoài DTO | 400 nếu strict, hoặc ignore theo policy |
| PUT ID không tồn tại | 404 |
| PUT sửa name/price | SKU ở entity vẫn không đổi |
| Group create | Default + OnCreate constraints đều chạy |
| Group update | Default + OnUpdate constraints đều chạy |
| Chỉ chọn custom group | Không tự động có Default nếu không kế thừa/chọn |
| PATCH name only | Price/description cũ giữ nguyên |
| PATCH description null | Description được clear |
| PATCH price null | 400 |
| PATCH sku | 400/403 tùy API policy |
| PATCH stale version | 409/412 theo ETag/locking policy |

Các tests ở phần 10–12 hiện thực những trường hợp cốt lõi POST/PUT/groups. PATCH matrix là **kế hoạch test cho triển khai PATCH tương lai**, không phải những tests đã có trong project này.

### Không khẳng định “test PASS” nếu chưa chạy

Các ví dụ được viết theo API Spring Boot 3.5/Spring Framework 6.2/Java 17 và đã được soát tính nhất quán về source files/imports; tuy vậy, **không có Gradle build thực tế được thực thi trong bài này**. Khi áp dụng vào repository thật, chạy `./gradlew test` với phiên bản dự án và sửa theo báo cáo compiler/test runner.

## 21. Lỗi phổ biến khi tổ chức validation theo thao tác

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| PATCH một field bị reject vì các field khác null | Reuse DTO POST/PUT có required constraints | Patch DTO có presence hoặc merge trước validate |
| POST cho phép thiếu name sau khi sửa PATCH | Bỏ `@NotBlank` khỏi shared DTO | Tách DTO hoặc chọn groups đúng |
| PUT thiếu price vẫn chấp nhận | Update group thiếu Default/required rule | Chạy Default + Update hoặc DTO riêng |
| Update tự đổi SKU dù không có constraint Update | Groups không chặn mapping | Loại SKU khỏi update DTO/service mapper |
| `@Validated(OnCreate.class)` bỏ qua rule `@NotBlank` Default | Custom group không tự chạy Default | Chọn cả `Default.class` hoặc group inheritance |
| Nested child constraints không chạy | Quên `@Valid` trên association | Thêm cascade, test nested field path |
| Child group sai | Groups pass-through không phù hợp child | Dùng `@ConvertGroup` có test |
| `@GroupSequence` dùng sai và group khác bị skip | Violation ở group đầu dừng sequence | Thiết kế/test ordering rõ |
| Annotation tồn tại nhưng provider thiếu | Chỉ có `jakarta.validation-api` | Thêm starter-validation/provider |
| Code Boot 3 import `javax.validation.*` | Sai namespace | Migrate sang Jakarta |
| PUT gửi JSON field lạ vẫn 200 | Jackson ignore unknown by default/config | Chọn strict mapping nếu contract yêu cầu |
| PUT 404 bị xử lý thành 500 | Không map missing resource | ResponseStatusException/domain handler |
| Trùng constraints ở DTO riêng | Chưa tách reusable custom constraint | Tạo composed constraint/value object khi có ích |
| DTO group trở nên khó hiểu | Quá nhiều action-specific groups | Tách command DTO rõ theo use case |
| PATCH null không xóa description | Code dùng `if(value!=null)` | Phân biệt absent/present/null |
| PATCH ghi đè thay đổi request khác | Read-modify-write không có version | Optimistic locking/ETag |
| Validation ở controller đúng nhưng service từ job bỏ qua | Chỉ tin web boundary | Domain/service invariants hoặc method validation |
| Client sửa ownerId/status qua DTO | Mass assignment | DTO riêng, allowlist, authorization |
| Test chỉ assert 400 nhưng service được gọi | Check errors sau service | Early validation gate + verifyNoInteractions |
| Numeric price thành double | Floating-point representation | Dùng BigDecimal + scale/domain rules |
| Validation group dùng để che field khỏi JSON | Lẫn validation và serialization | DTO mapping/authorization riêng |
| PUT chỉ gửi một field nhưng app xóa các field khác | Client dùng PUT như PATCH | Thiết kế contract/method rõ, test |
| API docs cho mọi field optional | Shared DTO/group không được schema generator hiểu | DTO riêng hoặc OpenAPI customization |
| Constraint không chạy khi service tạo bằng `new` | Bypass AOP | Dùng Spring-managed bean hoặc explicit validation |

## 22. Checklist thiết kế cho dự án thật

- [ ] Phân biệt rõ POST, PUT và PATCH ở API contract.
- [ ] Tài liệu hóa từng field: required, mutable, nullable, immutable.
- [ ] Dùng DTO riêng khi create/update khác nhau đáng kể.
- [ ] Không bind trực tiếp request vào JPA entity.
- [ ] Không để id/ownerId/SKU immutable có writable path từ client update.
- [ ] `@NotNull` đi cùng constraint cho field bắt buộc.
- [ ] Với BigDecimal price, kiểm tra giá không âm và các giới hạn domain.
- [ ] Có Jakarta provider trên runtime classpath.
- [ ] Gắn `@Valid`/`@Validated` đúng vị trí handler.
- [ ] Nếu dùng groups, xác định rõ Default và group inheritance.
- [ ] Không xem `@Validated(OnUpdate)` là cách cấm sửa property.
- [ ] Cascaded `@Valid` cho nested objects, `@ConvertGroup` khi thực sự cần.
- [ ] Phân biệt missing/null/value trong PATCH.
- [ ] Validate **candidate sau merge** trước khi ghi.
- [ ] Dùng optimistic locking/ETag nếu cập nhật đồng thời là rủi ro.
- [ ] Kiểm tra quyền sửa resource/field ở service.
- [ ] Chọn chính sách JSON unknown properties rõ ràng.
- [ ] Không gọi service khi request input invalid.
- [ ] Khi có domain conflict, map lỗi đúng status thay vì ẩn đi.
- [ ] Không serialize rejected values hoặc object graph nội bộ.
- [ ] Test cả positive và negative path cho POST/PUT.
- [ ] Test group-specific rules độc lập và Default fallback.
- [ ] Test rằng SKU/ID bất biến sau update.
- [ ] Nếu có PATCH, test absent/null/value/unknown field/concurrency.
- [ ] Kiểm tra OpenAPI schemas phản ánh contract từng thao tác.
- [ ] Chạy compile/tests thật trên repository trước khi deploy.

**Kết luận:** Bean Validation cho tạo mới và cập nhật nên bắt đầu từ **hợp đồng của từng thao tác**. **Tách Create DTO và Replace DTO** là cách rõ ràng, dễ bảo vệ nhất trong nhiều API. **Validation groups** hữu ích khi thật sự có nhiều constraint chung, nhưng phải hiểu `Default`, group selection và cascade; chúng không thay field authorization. Đối với **PATCH**, bắt buộc phân biệt **absent / explicit null / value**, merge vào candidate rồi validate trạng thái cuối trước khi lưu. Dù controller đã validate, những bất biến quan trọng vẫn cần được bảo vệ ở service/domain layer.

## Tài liệu tham khảo chính thức

- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — MVC Validator Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html)
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Hibernate Validator Reference Guide — Grouping Constraints](https://docs.hibernate.org/stable/validator/reference/en-US/html_single/#chapter-groups)
- [Jackson Databind — DeserializationFeature](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/DeserializationFeature.html)
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396)
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902)
