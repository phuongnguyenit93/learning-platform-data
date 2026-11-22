# Đường dẫn, PathPattern và biến @PathVariable trong Spring WebFlux

## 1. Ba khái niệm cần tách biệt

Khi xây dựng REST API, một endpoint thường có dạng:

~~~text
GET /api/tenants/acme/orders/42
~~~

Spring cần giải quyết ba việc:

1. **Request mapping**: chọn controller method phù hợp với HTTP method, URL path và các điều kiện như header, query parameter, Content-Type hoặc Accept.
2. **PathPattern**: phân tích và so khớp cấu trúc đường dẫn, gồm literal, wildcard và URI template variable.
3. **@PathVariable**: lấy giá trị đã được capture từ URI template để đưa vào tham số method, đồng thời chuyển đổi sang kiểu Java được khai báo.

Ví dụ:

~~~java
@RestController
@RequestMapping("/api/tenants/{tenantId}/orders")
class OrderController {

    @GetMapping("/{orderId}")
    Mono<String> get(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("orderId") Long orderId) {

        return Mono.just("tenant=" + tenantId + ", order=" + orderId);
    }
}
~~~

Với request:

~~~text
GET /api/tenants/acme/orders/42
~~~

Spring ghép đường dẫn cấp class và cấp method thành:

~~~text
/api/tenants/{tenantId}/orders/{orderId}
~~~

Sau khi match, method nhận:

- `tenantId = "acme"`
- `orderId = 42L`

`@PathVariable` không tự truy vấn database và không xác nhận đơn hàng có tồn tại. Nó chỉ lấy một giá trị từ URL và chuyển đổi giá trị đó sang kiểu tham số Java. Việc kiểm tra tồn tại, quyền truy cập và quy tắc nghiệp vụ thuộc các tầng tiếp theo.

## 2. Request mapping trong controller

Spring WebFlux hỗ trợ controller dựa trên annotation thông qua `@Controller` và `@RestController`. `@RestController` là cách kết hợp controller với response body, phù hợp khi method trả dữ liệu HTTP trực tiếp.

Các annotation mapping thường dùng:

| Annotation | HTTP method | Tình huống |
| --- | --- | --- |
| `@GetMapping` | GET | Đọc tài nguyên |
| `@PostMapping` | POST | Tạo tài nguyên hoặc thực hiện lệnh |
| `@PutMapping` | PUT | Thay thế toàn bộ tài nguyên theo hợp đồng |
| `@PatchMapping` | PATCH | Cập nhật một phần |
| `@DeleteMapping` | DELETE | Xóa tài nguyên |
| `@RequestMapping` | Có thể khai báo nhiều điều kiện; nếu không chỉ định method thì mặc định không giới hạn HTTP method | Mapping tổng quát, thường dùng ở cấp class |

Có thể kết hợp điều kiện ở cấp class và method:

~~~java
@RestController
@RequestMapping("/api/v1/products")
class ProductController {

    @GetMapping
    Mono<String> list() {
        return Mono.just("product-list");
    }

    @GetMapping("/{productId}")
    Mono<String> detail(@PathVariable("productId") Long productId) {
        return Mono.just("product-" + productId);
    }

    @PostMapping
    Mono<String> create() {
        return Mono.just("created");
    }
}
~~~

Các URL tương ứng:

| Request | Method được chọn |
| --- | --- |
| GET `/api/v1/products` | `list()` |
| GET `/api/v1/products/12` | `detail(12L)` |
| POST `/api/v1/products` | `create()` |

Đường dẫn ở cấp class tạo **prefix chung**; đường dẫn ở cấp method mô tả phần còn lại. Nếu không có mapping ở cấp class, method có thể khai báo đường dẫn đầy đủ.

**Lưu ý:** không đặt nhiều annotation thuộc họ `@RequestMapping` trên cùng một element rồi kỳ vọng Spring cộng dồn chúng. Nếu phát hiện nhiều mapping annotation trên cùng class hoặc method, Spring ghi cảnh báo và chỉ dùng mapping đầu tiên. Hãy dùng một mapping annotation với các thuộc tính cần thiết.

Ngoài path và HTTP method, mapping còn có thể xét:

- `params`: điều kiện theo query parameter.
- `headers`: điều kiện theo request header.
- `consumes`: Content-Type mà endpoint chấp nhận.
- `produces`: media type endpoint có thể trả về, được đối chiếu với Accept.

Chủ đề của bài này là path và URI variables; các điều kiện khác giúp tránh nhiều handler cùng nhận một loại request ngoài ý muốn.

## 3. PathPattern là gì?

**`PathPattern`** là mô hình pattern đã được phân tích trước (pre-parsed), được thiết kế riêng cho việc match HTTP URL path. Spring WebFlux sử dụng `PathPattern` và `PathPatternParser` để xử lý URI path pattern.

Thay vì xem URL là một chuỗi ký tự tùy ý, WebFlux sử dụng cấu trúc path đã phân đoạn thành các segment. Điều này hỗ trợ việc so khớp hiệu quả, đồng thời xử lý encoding và path parameter phù hợp hơn.

Một pattern có thể gồm:

- Literal segment: tên cố định như `/orders`.
- Wildcard trong segment: `?` hoặc `*`.
- URI variable: `{id}`.
- URI variable có regex: `{id:[0-9]+}`.
- Catch-all: `**` hoặc `{*path}` trong vị trí được phép.

### 3.1. Bảng cú pháp PathPattern

| Cú pháp | Ý nghĩa | Ví dụ match |
| --- | --- | --- |
| `orders` | Segment literal | `/orders` |
| `?` | Khớp đúng một ký tự trong segment | `/pages/t?st` khớp `/pages/test` |
| `*` | Khớp không hoặc nhiều ký tự trong một segment | `/files/*.pdf` khớp `/files/report.pdf` |
| `**` | Khớp không hoặc nhiều path segment | `/resources/**` khớp `/resources/a/b.txt` |
| `{id}` | Capture một segment và đặt tên `id` | `/orders/{id}` khớp `/orders/42` |
| `{id:[0-9]+}` | Capture một segment nếu giá trị thỏa regex | `/orders/{id:[0-9]+}` khớp `/orders/42` |
| `{*path}` | Capture không hoặc nhiều segment còn lại thành một URI variable | `/files/{*path}` khớp `/files/docs/a.pdf` |

### 3.2. Phân biệt wildcard và URI variable

`*` chỉ giúp pattern match, không cung cấp tên biến để lấy trong method.

~~~java
@GetMapping("/files/*.pdf")
Mono<String> pdf() {
    return Mono.just("pdf");
}
~~~

Trong ví dụ trên, handler có thể match một tên file kết thúc bằng `.pdf`, nhưng không có biến để lấy tên file.

Ngược lại:

~~~java
@GetMapping("/files/{fileName}")
Mono<String> file(@PathVariable("fileName") String fileName) {
    return Mono.just(fileName);
}
~~~

`{fileName}` vừa match một segment vừa capture giá trị để đưa vào tham số method.

### 3.3. Một URI variable thông thường chỉ capture một segment

Pattern:

~~~text
/projects/{project}/versions
~~~

Match:

~~~text
/projects/spring/versions
~~~

Capture:

~~~text
project = spring
~~~

Không match:

~~~text
/projects/spring/framework/versions
~~~

Vì `{project}` chỉ đại diện cho **một segment**, không bao gồm dấu phân cách `/` để lấy nhiều segment.

Nếu cần capture nhiều segment, dùng catch-all phù hợp như `{*path}` thay vì cố ép một URI variable thông thường thành đường dẫn đệ quy.

### 3.4. Catch-all và vị trí hợp lệ

Ví dụ hợp lệ:

~~~text
/resources/**
/resources/{*path}
/**/info
/{*path}/resources
~~~

Một pattern chỉ được có **một catch-all instance** thuộc nhóm `**` hoặc `{*path}`. Catch-all không được đặt tùy ý ở giữa pattern.

Ví dụ không hợp lệ:

~~~text
/resources/**/file.png
/resources/{*path}/file.png
/**/spring/**
~~~

Nếu muốn bắt đầu từ một prefix rồi lấy toàn bộ phần đường dẫn còn lại, cách rõ ràng là:

~~~java
@GetMapping("/resources/{*path}")
Mono<String> resource(@PathVariable("path") String path) {
    return Mono.just(path);
}
~~~

Với request:

~~~text
GET /resources/images/logo.png
~~~

Giá trị capture theo PathPattern là:

~~~text
/images/logo.png
~~~

Giá trị catch-all có thể bao gồm dấu slash ở đầu phần đường dẫn được capture. Nếu API cần một định dạng riêng, hãy chuẩn hóa và kiểm thử rõ ràng thay vì tự giả định nó giống một segment đơn.

## 4. Regex trong URI variable

Cú pháp:

~~~text
/{variableName:regular-expression}
~~~

Regex ràng buộc giá trị được chấp nhận ngay tại bước match route. Ví dụ:

~~~java
@GetMapping("/orders/{orderNumber:[0-9]+}")
Mono<String> byNumber(
        @PathVariable("orderNumber") Long orderNumber) {
    return Mono.just("order=" + orderNumber);
}
~~~

Kết quả:

| URL | Kết quả match |
| --- | --- |
| `/orders/42` | Match; capture `orderNumber=42` |
| `/orders/0007` | Match; capture `orderNumber=0007`, sau conversion thành số 7 |
| `/orders/abc` | Không match pattern này |
| `/orders/42-extra` | Không match pattern này |

**Regex là điều kiện chọn route, không phải thay thế toàn bộ validation nghiệp vụ.** Nó hữu ích để phân biệt format của endpoint và tránh một handler nhận dữ liệu sai hình dạng.

Ví dụ regex cho slug:

~~~java
@GetMapping("/categories/{slug:[a-z0-9-]+}")
Mono<String> category(@PathVariable("slug") String slug) {
    return Mono.just("category=" + slug);
}
~~~

Regex chỉ cho phép chữ thường ASCII, chữ số và dấu gạch nối theo quy tắc đã khai báo. Nếu domain cho phép Unicode hoặc ký tự khác, hãy thiết kế pattern theo đúng contract thay vì dùng một regex quá hẹp.

Có thể dùng nhiều URI variable trong một pattern. Ví dụ:

~~~java
@GetMapping("/artifacts/{name:[a-z-]+}/{version:[0-9]+}")
Mono<String> artifact(
        @PathVariable("name") String name,
        @PathVariable("version") int version) {
    return Mono.just(name + ":" + version);
}
~~~

Trong Java annotation string, regex cần escape theo cú pháp Java nếu chứa backslash. Ví dụ `\\d+` trong regex phải được viết `"\\\\d+"` trong source Java. Với pattern số đơn giản, `[0-9]+` thường dễ đọc hơn.

## 5. Spring chọn pattern nào khi nhiều pattern cùng match?

Một URL có thể phù hợp với nhiều mapping. Ví dụ:

~~~text
GET /orders/new
~~~

Có thể match cả:

~~~text
/orders/new
/orders/{orderId}
/orders/**
~~~

Spring dùng cơ chế so sánh độ cụ thể của `PathPattern` để chọn mapping tốt nhất. Nguyên tắc thực hành:

1. Pattern literal cố định thường cụ thể hơn URI variable.
2. URI variable thường cụ thể hơn wildcard cùng phạm vi.
3. Catch-all được xếp cuối.
4. Nếu điểm so sánh bằng nhau, pattern dài hơn được ưu tiên theo comparator.
5. Khi có nhiều catch-all, pattern dài hơn được chọn theo quy tắc comparator.

Ví dụ:

~~~java
@RestController
@RequestMapping("/orders")
class OrderLookupController {

    @GetMapping("/new")
    Mono<String> createForm() {
        return Mono.just("new-order");
    }

    @GetMapping("/{orderId}")
    Mono<String> find(@PathVariable("orderId") String orderId) {
        return Mono.just("order=" + orderId);
    }

    @GetMapping("/**")
    Mono<String> fallback() {
        return Mono.just("fallback");
    }
}
~~~

Với `GET /orders/new`, pattern literal `/orders/new` cụ thể hơn `/orders/{orderId}`. Handler `createForm()` được chọn. Pattern `/orders/**` là catch-all nên có độ ưu tiên thấp hơn.

**Không dựa vào thứ tự khai báo method trong class để quyết định handler.** Hãy thiết kế các pattern rõ ràng, tránh những route có độ mơ hồ cao và test các URL biên.

## 6. @PathVariable làm nhiệm vụ gì?

`@PathVariable` liên kết một URI template variable trong mapping với một tham số method.

~~~java
@GetMapping("/owners/{ownerId}/pets/{petId}")
Mono<String> pet(
        @PathVariable("ownerId") Long ownerId,
        @PathVariable("petId") Long petId) {
    return Mono.just("owner=" + ownerId + ",pet=" + petId);
}
~~~

Request:

~~~text
GET /owners/12/pets/88
~~~

Giá trị method nhận:

~~~text
ownerId = 12L
petId   = 88L
~~~

Một method có thể có nhiều `@PathVariable`. Mỗi biến phải tương ứng với tên được capture trong pattern sau khi ghép mapping cấp class và method.

### 6.1. Đặt tên rõ ràng

Khuyến nghị:

~~~java
@GetMapping("/{productId}")
Mono<String> get(@PathVariable("productId") UUID productId) {
    return Mono.just(productId.toString());
}
~~~

Có thể bỏ tên trong annotation khi tên biến URI trùng với tên tham số Java và code được compile với thông tin parameter name (ví dụ Maven compiler bật `-parameters`):

~~~java
@GetMapping("/{productId}")
Mono<String> get(@PathVariable UUID productId) {
    return Mono.just(productId.toString());
}
~~~

Với API quan trọng, khai báo tên tường minh giúp tránh phụ thuộc compiler configuration hoặc việc refactor đổi tên biến Java.

### 6.2. Biến cấp class và cấp method

~~~java
@RestController
@RequestMapping("/tenants/{tenantId}/orders")
class TenantOrderController {

    @GetMapping("/{orderId}")
    Mono<String> get(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("orderId") UUID orderId) {
        return Mono.just(tenantId + "/" + orderId);
    }
}
~~~

`tenantId` nằm trong mapping cấp class nhưng vẫn có thể được inject vào method. `orderId` nằm trong mapping cấp method.

Không cần lặp lại `tenantId` trong `@GetMapping`; Spring ghép URI template của hai cấp thành một mapping hoàn chỉnh.

## 7. Tự động chuyển đổi kiểu của @PathVariable

Giá trị URL ban đầu là text. Spring sử dụng hệ thống conversion để chuyển sang kiểu Java của tham số.

Ví dụ:

~~~java
@GetMapping("/orders/{id}")
Mono<String> get(
        @PathVariable("id") UUID id) {
    return Mono.just(id.toString());
}
~~~

Một số kiểu phổ biến:

| Kiểu tham số | Giá trị path ví dụ | Kết quả |
| --- | --- | --- |
| `String` | `abc` | `"abc"` |
| `int` / `Integer` | `42` | 42 |
| `long` / `Long` | `9000` | 9000L |
| `UUID` | `550e8400-e29b-41d4-a716-446655440000` | UUID tương ứng |
| `enum` | `PAID` | Enum constant nếu tên hợp lệ |
| `LocalDate` | `2026-11-08` | Phụ thuộc converter/formatter đã đăng ký |

Các kiểu đơn giản như int, long và Date được hỗ trợ mặc định; có thể đăng ký converter/formatter cho kiểu khác. Với kiểu Java thời gian hoặc kiểu domain riêng, hãy kiểm tra converter hiện có trong cấu hình và test format thực tế.

### 7.1. Khi conversion thất bại

Ví dụ:

~~~java
@GetMapping("/orders/{id}")
Mono<String> get(@PathVariable("id") Long id) {
    return Mono.just("id=" + id);
}
~~~

Request:

~~~text
GET /orders/not-a-number
~~~

Pattern match vì `{id}` nhận một segment. Nhưng Spring không thể chuyển `not-a-number` thành `Long`, nên quá trình bind tham số thất bại với lỗi type mismatch. Ứng dụng thường ánh xạ lỗi này thành HTTP 400 theo cơ chế exception handling đang cấu hình.

Phân biệt với regex route:

~~~java
@GetMapping("/orders/{id:[0-9]+}")
Mono<String> get(@PathVariable("id") Long id) {
    return Mono.just("id=" + id);
}
~~~

Với URL `/orders/not-a-number`, regex không match. Request có thể kết thúc ở **404 route not found** thay vì vào handler rồi lỗi conversion. Hai cách thể hiện hai contract khác nhau:

- Không match route: URL không có endpoint phù hợp.
- Match route nhưng conversion thất bại: endpoint có nhưng input path không chuyển được sang kiểu yêu cầu.

Không nên dùng regex chỉ để đổi 400 thành 404 nếu điều đó làm hợp đồng API khó hiểu.

### 7.2. Converter cho kiểu domain riêng

Giả sử domain dùng `OrderId` thay vì UUID trực tiếp:

~~~java
public record OrderId(UUID value) {
    public OrderId {
        if (value == null) {
            throw new IllegalArgumentException("value is required");
        }
    }
}
~~~

Có thể đăng ký converter:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
            String.class,
            OrderId.class,
            value -> new OrderId(UUID.fromString(value))
        );
    }
}
~~~

Controller:

~~~java
@GetMapping("/orders/{id}")
Mono<String> get(@PathVariable("id") OrderId id) {
    return Mono.just("order=" + id.value());
}
~~~

Các đoạn trên là **mã minh họa theo nhiều file**; cần import `UUID`, `Configuration`, `WebFluxConfigurer`, `FormatterRegistry` và các annotation liên quan. Khi đăng ký converter, test cả giá trị hợp lệ lẫn không hợp lệ. Đừng biến lỗi parse thành một ID giả hoặc giá trị mặc định âm thầm.

## 8. @PathVariable với Map

Khi method cần toàn bộ URI template variables thay vì khai báo từng tham số, có thể dùng:

~~~java
@GetMapping("/tenants/{tenantId}/orders/{orderId}")
Mono<String> allVariables(@PathVariable Map<String, String> variables) {
    return Mono.just(variables.toString());
}
~~~

Map được populate từ các URI template variables của mapping. Ví dụ request:

~~~text
GET /tenants/acme/orders/42
~~~

Map chứa:

~~~text
tenantId -> acme
orderId  -> 42
~~~

Dùng `Map` hữu ích khi endpoint có nhiều biến mang tính cấu trúc hoặc một handler dùng chung. Tuy nhiên, nếu method chỉ cần một hoặc hai giá trị, khai báo từng `@PathVariable("...")` thường dễ đọc và có type safety tốt hơn.

Lưu ý:

- `Map<String, String>` giữ giá trị dạng chuỗi; nếu cần UUID/Long, tự chuyển đổi hoặc khai báo tham số có kiểu cụ thể.
- Đừng dựa vào thứ tự entry trong Map; nếu cần output xác định, sắp xếp key trước khi hiển thị.
- Khi mapping cấp class cũng có biến, map có thể bao gồm cả biến từ prefix cấp class và cấp method.
- Không dùng Map để né validation hoặc authorization cho các biến đường dẫn.

## 9. @PathVariable required và trường hợp optional

Theo mặc định, `@PathVariable` là **required**. Khi mapping có `{id}`, Spring mong đợi biến này tồn tại trong path được chọn.

Có thể dùng `required=false` hoặc kiểu `Optional` khi handler được map với nhiều pattern, trong đó có pattern không chứa biến đó:

~~~java
@GetMapping(path = {"", "/{id}"})
Mono<String> get(
        @PathVariable(name = "id", required = false)
        Optional<String> id) {

    return Mono.just(id.orElse("all"));
}
~~~

Đây là ví dụ minh họa; cần import `Optional` và Mono. Mapping có cả đường dẫn rỗng và đường dẫn có ID, vì vậy tham số có thể không hiện diện ở nhánh đầu.

**Chỉ đặt `required=false` không làm cho một path segment bắt buộc biến thành optional.** Nếu pattern duy nhất là `/{id}` thì request không có segment vẫn không match pattern đó. Hãy định nghĩa rõ các biến thể route trước khi dùng Optional.

Trong thiết kế REST, nếu hai thao tác khác nhau đáng kể, hai mapping riêng thường rõ hơn một method chứa quá nhiều nhánh optional.

## 10. Path variable khác query parameter và request body

| Nơi truyền dữ liệu | Ví dụ | Annotation | Dùng cho |
| --- | --- | --- | --- |
| Path segment | `/orders/42` | `@PathVariable("id")` | Định danh tài nguyên hoặc cấu trúc route |
| Query string | `/orders?status=PAID` | `@RequestParam("status")` | Bộ lọc, phân trang, tùy chọn tìm kiếm |
| HTTP header | `X-Request-Id: abc` | `@RequestHeader` | Metadata của request |
| Request body | JSON `{"status":"PAID"}` | `@RequestBody` | Dữ liệu payload của thao tác |

Ví dụ một endpoint tìm kiếm:

~~~java
@GetMapping("/orders/{customerId}")
Mono<String> orders(
        @PathVariable("customerId") UUID customerId,
        @RequestParam(name = "status", required = false) String status,
        @RequestParam(name = "page", defaultValue = "0") int page) {
    return Mono.just(
        "customer=" + customerId +
        ",status=" + status +
        ",page=" + page);
}
~~~

Với request:

~~~text
GET /orders/550e8400-e29b-41d4-a716-446655440000?status=PAID&page=2
~~~

`customerId` xác định phạm vi tài nguyên; `status` và `page` là điều kiện truy vấn. Không đưa mọi bộ lọc vào path chỉ vì `@PathVariable` tiện sử dụng.

## 11. Encoding, dấu slash và dấu chấm phẩy

Đường dẫn HTTP có quy tắc encoding riêng. Spring WebFlux dùng `RequestPath`/`PathContainer` để làm việc với path đã được phân đoạn; các segment có giá trị đã giải mã phục vụ truy cập. Semicolon content được tách khỏi phần dùng để match path và có thể được truy cập qua cơ chế `@MatrixVariable`.

Một số lưu ý thực tế:

1. **Không tự decode giá trị @PathVariable lần thứ hai** nếu framework đã cung cấp giá trị đã giải mã. Double decoding có thể biến dữ liệu thành nội dung khác dự kiến.
2. Dấu `/` phân cách segment. Một `{id}` bình thường không đại diện cho nhiều segment.
3. Nếu ID có thể chứa dấu slash, không dựa vào `%2F` sẽ đi qua mọi proxy, gateway và server theo cùng một cách. Hãy thiết kế endpoint dùng catch-all `{*path}` hoặc truyền dữ liệu như query parameter khi phù hợp.
4. Dữ liệu chứa ký tự reserved cần được encode đúng theo URI component; khi xây URL từ client, dùng URI builder thay vì nối chuỗi thủ công.
5. Semicolon path parameter không giống query string; nếu API cần matrix variable, khai báo và test rõ ràng.

Ví dụ matrix variable (đoạn minh họa):

~~~java
@GetMapping("/cars/{carId}")
Mono<String> car(
        @PathVariable("carId") String carId,
        @MatrixVariable(name = "color", required = false)
        String color) {
    return Mono.just("car=" + carId + ",color=" + color);
}
~~~

Một URL có thể có dạng `/cars/42;color=red`. Matrix variable là cơ chế riêng; đừng nhầm `color` với URI variable `{carId}`.

### 11.1. Dùng URI builder ở phía client

Khi WebClient gọi endpoint có path variable, dùng template và giá trị riêng:

~~~java
webClient.get()
    .uri("/api/orders/{id}", orderId)
    .retrieve()
    .bodyToMono(Order.class);
~~~

Giá trị `orderId` được đưa vào URI template qua builder của client. Cách này rõ ràng và tránh nối chuỗi thủ công khiến ký tự reserved hoặc khoảng trắng không được encode đúng.

## 12. WebFlux không tự động suffix-match như một số cấu hình MVC cũ

Trong Spring WebFlux, `PathPattern` được dùng cho path matching và **không hỗ trợ suffix pattern matching** kiểu `/person` tự động match `/person.json`.

Nếu cần phân biệt định dạng response, ưu tiên:

- HTTP `Accept` và thuộc tính `produces` trong mapping.
- Query parameter nếu API cần một format selector tường minh.
- Endpoint riêng khi hai representation có contract thực sự khác nhau.

Ví dụ:

~~~java
@GetMapping(path = "/products/{id}", produces = "application/json")
Mono<Product> json(@PathVariable("id") UUID id) {
    return service.find(id);
}
~~~

Đây là ví dụ cấu trúc, cần khai báo Product và service. Không dựa vào hậu tố file trong URL như một cơ chế content negotiation mặc định.

## 13. Mã nguồn Spring Boot WebFlux hoàn chỉnh

Ví dụ sau có thể chạy độc lập, minh họa:

- URI variable ở cấp class và method.
- Chuyển đổi UUID và long.
- Regex constraint.
- Catch-all path variable.
- Lấy toàn bộ URI variables qua Map.
- Route literal cụ thể hơn route variable.

Yêu cầu: **Java 17+**, **Maven 3.9+** và Spring Boot 4.1.2. Khi tạo dự án thực tế, dùng patch release được tổ chức hỗ trợ và để Boot BOM quản lý dependency.

Cấu trúc:

~~~text
path-variable-demo/
  pom.xml
  src/main/java/example/pathdemo/PathVariableDemoApplication.java
  src/main/java/example/pathdemo/OrderPathController.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>path-variable-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/pathdemo/PathVariableDemoApplication.java**

~~~java
package example.pathdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathVariableDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathVariableDemoApplication.class, args);
    }
}
~~~

**src/main/java/example/pathdemo/OrderPathController.java**

~~~java
package example.pathdemo;

import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/tenants/{tenantId}/orders")
public class OrderPathController {

    @GetMapping("/latest")
    public Mono<String> latest(
            @PathVariable("tenantId") String tenantId) {
        return Mono.just("tenant=" + tenantId + ";latest");
    }

    @GetMapping("/{orderId}")
    public Mono<String> byId(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("orderId") UUID orderId) {
        return Mono.just(
                "tenant=" + tenantId + ";orderId=" + orderId);
    }

    @GetMapping("/by-number/{number:\\d+}")
    public Mono<String> byNumber(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("number") long number) {
        return Mono.just(
                "tenant=" + tenantId + ";number=" + number);
    }

    @GetMapping("/files/{*path}")
    public Mono<String> filePath(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("path") String path) {
        return Mono.just(
                "tenant=" + tenantId + ";path=" + path);
    }

    @GetMapping("/variables/{category}/{item}")
    public Mono<String> allVariables(
            @PathVariable Map<String, String> variables) {
        return Mono.just(new TreeMap<>(variables).toString());
    }
}
~~~

### 13.1. Chạy ứng dụng

Tại thư mục chứa `pom.xml`:

~~~bash
mvn clean package
mvn spring-boot:run
~~~

Ở terminal khác, gọi từng endpoint:

~~~bash
curl -s http://localhost:8080/api/tenants/acme/orders/latest
curl -s http://localhost:8080/api/tenants/acme/orders/550e8400-e29b-41d4-a716-446655440000
curl -s http://localhost:8080/api/tenants/acme/orders/by-number/42
curl -s http://localhost:8080/api/tenants/acme/orders/files/manuals/install.pdf
curl -s http://localhost:8080/api/tenants/acme/orders/variables/books/42
~~~

**Body response dự kiến**, theo đúng thứ tự các lệnh:

~~~text
tenant=acme;latest
tenant=acme;orderId=550e8400-e29b-41d4-a716-446655440000
tenant=acme;number=42
tenant=acme;path=/manuals/install.pdf
{category=books, item=42, tenantId=acme}
~~~

Giải thích:

- `/latest` chọn mapping literal thay vì `/{orderId}`.
- UUID được chuyển đổi từ segment URL sang `java.util.UUID`.
- `by-number/{number:\\d+}` chỉ match segment dạng chữ số, sau đó được chuyển thành `long`.
- `files/{*path}` capture nhiều segment và trả phần path có slash đầu.
- Map nhận các biến URI từ mapping cấp class và method; `TreeMap` giúp output có thứ tự ổn định.

### 13.2. Một số request biên

| Request | Kết quả mong đợi theo mapping demo | Lý do |
| --- | --- | --- |
| `GET /api/tenants/acme/orders/latest` | Handler latest | Literal cụ thể hơn variable |
| `GET /api/tenants/acme/orders/42` | Handler byId nhưng UUID conversion thất bại | Route variable match, giá trị không phải UUID |
| `GET /api/tenants/acme/orders/by-number/42` | Handler byNumber | Regex và conversion đều hợp lệ |
| `GET /api/tenants/acme/orders/by-number/abc` | Không match byNumber | Regex `[0-9]+` không thỏa |
| `GET /api/tenants/acme/orders/files/a/b.pdf` | Handler filePath | Catch-all capture nhiều segment |
| `POST /api/tenants/acme/orders/latest` | Không có POST mapping tương ứng | HTTP method không phù hợp |

Status thực tế còn phụ thuộc exception handler, server và cấu hình ứng dụng. Thông thường route không tồn tại trả 404, HTTP method không được hỗ trợ trả 405, và type conversion lỗi được xử lý như lỗi request 400. Hãy kiểm thử contract status của ứng dụng, không chỉ dựa vào output của controller.

## 14. Thiết kế URL dễ hiểu và ổn định

Một API có đường dẫn rõ ràng thường có các đặc điểm:

- Dùng danh từ cho resource: `/orders`, `/customers`, `/products`.
- Dùng URI variable để định danh resource: `/orders/{orderId}`.
- Dùng path lồng nhau khi quan hệ cha–con thực sự quan trọng: `/customers/{customerId}/orders/{orderId}`.
- Dùng query parameter cho filter, sort, pagination: `/orders?status=PAID&page=0`.
- Dùng HTTP method để thể hiện thao tác; tránh tạo nhiều route khác nhau chỉ để biểu diễn CRUD cơ bản.
- Tránh catch-all quá rộng nếu không cần thiết; route catch-all có thể làm việc phân tích endpoint và bảo vệ dữ liệu khó hơn.
- Không đưa token, password, secret hoặc dữ liệu nhạy cảm vào path vì URL thường xuất hiện trong access log, browser history, tracing và monitoring.
- Giữ naming nhất quán: `orderId` thay vì nơi thì `id`, nơi thì `order_id` cho cùng một ý nghĩa.

Ví dụ:

~~~text
GET    /api/orders/{orderId}
POST   /api/orders
PATCH  /api/orders/{orderId}
DELETE /api/orders/{orderId}
GET    /api/customers/{customerId}/orders
~~~

Không cần lồng URL theo mọi quan hệ database. Nếu order có thể được truy cập độc lập bằng orderId, `/orders/{orderId}` có thể đủ; server vẫn phải kiểm tra quyền truy cập theo customer/tenant.

## 15. Bảo mật: PathVariable không thay thế authorization

Một URI variable do client gửi lên là **input không đáng tin cậy**. Ví dụ:

~~~text
GET /api/tenants/acme/orders/42
~~~

Việc controller nhận `tenantId="acme"` và `orderId=42` không có nghĩa user hiện tại được phép xem đơn hàng đó.

Các rủi ro thường gặp:

1. **IDOR/BOLA**: client đổi ID từ 42 sang 43 và truy cập tài nguyên của người khác.
2. **Tenant confusion**: client tự thay tenant trong URL để cố đọc dữ liệu tenant khác.
3. **Path traversal**: catch-all path được dùng để đọc file ngoài thư mục cho phép bằng các chuỗi như `../` hoặc dạng encoded tương đương.
4. **Input confusion**: nhiều dạng encoding/normalization có thể tạo cách hiểu khác nhau giữa proxy, gateway và application.
5. **Log leakage**: ID nhạy cảm hoặc dữ liệu bí mật được đặt trong URL và xuất hiện trong access log.

Biện pháp:

- Xác thực user ở security boundary.
- Lấy tenant được phép từ identity/authorization context đáng tin cậy; nếu URL có tenantId, phải xác minh nó khớp quyền của user.
- Kiểm tra quyền ở từng resource/service, không chỉ kiểm tra route có match.
- Với catch-all file path, normalize đường dẫn, giới hạn vào root được phép, chặn traversal và symlink escape theo thiết kế lưu trữ.
- Không dùng regex như cơ chế authorization; regex chỉ kiểm tra hình dạng của route variable.
- Không trả chi tiết nội bộ hoặc đường dẫn filesystem trong lỗi HTTP.

**PathPattern chỉ giúp chọn handler và capture dữ liệu. Nó không cấp quyền cho người gọi.**

## 16. Các lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@PathVariable` không tìm thấy giá trị | Tên annotation khác tên URI variable | Dùng `@PathVariable("orderId")` tường minh |
| Tham số không lấy được tên khi bỏ annotation value | Compiler không giữ parameter name | Bật `-parameters` hoặc khai báo tên rõ |
| `Long`/`UUID` conversion lỗi | URL không đúng định dạng | Kiểm tra contract, xử lý type mismatch phù hợp |
| Muốn một `{id}` bắt nhiều segment | URI variable thường chỉ bắt một segment | Dùng `{*path}` hoặc thiết kế query parameter |
| Catch-all đặt ở giữa pattern | PathPattern không cho phép cấu trúc đó | Đặt catch-all ở vị trí đầu/cuối hợp lệ và chỉ dùng một |
| Route static bị handler variable nhận | Pattern thiết kế không rõ hoặc mapping không đúng | Định nghĩa literal route cụ thể và test specificity |
| URL `/person.json` không match `/person` | WebFlux không dùng suffix pattern matching | Dùng Accept/produces hoặc route rõ ràng |
| Dùng @RequestParam để lấy path segment | Nhầm query string với URI template | Dùng @PathVariable |
| Dùng @PathVariable để lấy query string | Sai vị trí dữ liệu | Dùng @RequestParam |
| Gọi service với tenantId từ URL mà không kiểm tra quyền | Có thể truy cập chéo tenant | Authorize tenant/resource tại service/security layer |
| Dùng `%2F` để nhét slash vào một variable | Proxy/server có thể xử lý encoded slash khác nhau | Thiết kế catch-all hoặc query theo contract |
| Ghép URL client bằng chuỗi thủ công | Dễ sai encoding | Dùng URI template/UriBuilder/WebClient |
| Dùng regex để thay thế validation nghiệp vụ | Regex chỉ kiểm tra match path | Validate dữ liệu và quyền ở service |
| Catch-all file path chấp nhận `..` | Nguy cơ path traversal | Normalize, allowlist root, kiểm tra canonical path |
| Cho rằng path variable chứng minh tài nguyên tồn tại | Binding chỉ chuyển giá trị URL | Truy vấn service/repository và xử lý NotFound riêng |

## 17. Cách kiểm thử route và PathVariable

Một controller nên có test cho cả **match đúng**, **không match**, **conversion**, **độ ưu tiên** và **quyền truy cập**.

Danh sách tình huống:

1. Literal route được chọn thay cho variable route khi cả hai cùng match.
2. URI variable nhận đúng giá trị ở cấp class và cấp method.
3. UUID/Long chuyển đổi thành công.
4. Giá trị không chuyển đổi được trả lỗi theo HTTP contract.
5. Regex chỉ nhận định dạng đã khai báo.
6. Catch-all capture đúng nhiều segment.
7. Map chứa các URI variables cần thiết.
8. HTTP method sai không gọi handler.
9. ID hợp lệ nhưng không tồn tại được xử lý riêng với ID sai định dạng.
10. User không có quyền không thể đổi tenantId/orderId để truy cập tài nguyên khác.

Có thể dùng **WebTestClient** để kiểm thử endpoint reactive bằng HTTP, không cần viết test phụ thuộc vào cách controller tự gọi method. Ví dụ đoạn test minh họa:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderPathControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void resolvesPathVariables() {
        client.get()
            .uri("/api/tenants/acme/orders/by-number/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("tenant=acme;number=42");
    }

    @Test
    void capturesCatchAllPath() {
        client.get()
            .uri("/api/tenants/acme/orders/files/manuals/install.pdf")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("tenant=acme;path=/manuals/install.pdf");
    }
}
~~~

Đây là **đoạn test minh họa** cần import JUnit, Spring Boot test và WebTestClient; cần thêm dependency test tương ứng. Nó giả định controller ở ví dụ trước đã có trong application context. Khi chạy trên server thật, test xác nhận cả quá trình HTTP parsing, route matching, argument conversion và response encoding.

## 18. Checklist khi debug lỗi mapping

Khi một URL không vào đúng controller method, kiểm tra theo thứ tự:

1. **HTTP method**: client gửi GET hay POST? Mapping có khai báo method đó không?
2. **Prefix cấp class**: controller có `@RequestMapping` chung nào không?
3. **Method path**: ghép prefix với path của method có đúng URL thực tế không?
4. **PathPattern syntax**: wildcard/catch-all có đặt đúng vị trí và số lượng không?
5. **Specificity**: có mapping literal/variable/catch-all nào khác cùng match không?
6. **URI variable name**: tên trong `{...}` có trùng với tên được khai báo trong `@PathVariable` không?
7. **Conversion**: UUID, Long, enum hoặc custom type có parse được không?
8. **Encoding**: proxy/gateway có decode hoặc normalize path trước khi tới WebFlux không?
9. **Context path/base path**: URL gọi có thêm prefix do deployment/proxy không?
10. **Security**: request có bị chặn trước khi tới controller không?

Phân biệt lỗi theo giai đoạn:

~~~text
Không có mapping phù hợp
    -> thường là 404

Mapping có path nhưng HTTP method không phù hợp
    -> thường là 405

Mapping được chọn, nhưng @PathVariable không chuyển đổi được
    -> thường là 400

Mapping và binding thành công, nhưng service không tìm thấy tài nguyên
    -> domain NotFound, thường ánh xạ 404

Tài nguyên tồn tại nhưng user không có quyền
    -> 403 hoặc chính sách 404 để tránh tiết lộ tài nguyên
~~~

Status cuối cùng phải theo exception handling và security policy của ứng dụng; sơ đồ trên giúp khoanh vùng nguyên nhân.

## 19. Tự kiểm tra

**Câu 1.** Pattern `/orders/{id}` có match `/orders/42/history` không?

**Không.** `{id}` chỉ capture một segment; URL có thêm segment `history`.

**Câu 2.** Muốn capture toàn bộ phần còn lại sau `/files`, dùng pattern nào?

`/files/{*path}`. Biến path có thể chứa nhiều segment và phần capture có slash đầu.

**Câu 3.** `@PathVariable("orderId") UUID orderId` có tự truy vấn order trong database không?

**Không.** Spring chỉ chuyển giá trị URI variable sang UUID; service/repository mới kiểm tra tài nguyên.

**Câu 4.** Nếu cả `/orders/new` và `/orders/{id}` match, route nào cụ thể hơn?

`/orders/new` vì literal segment cụ thể hơn URI variable.

**Câu 5.** `limit` hoặc `page` trong `/orders?page=2` nên dùng PathVariable hay RequestParam?

`@RequestParam` vì dữ liệu nằm trong query string.

**Câu 6.** Nếu route có regex `{id:[0-9]+}` và URL gửi `abc`, handler có vào rồi bị lỗi Long conversion không?

Thông thường **không**. Regex khiến pattern không match ngay từ đầu; request không được chọn vào handler đó.

**Câu 7.** Có thể bỏ tên trong `@PathVariable` không?

Có, nếu tên tham số Java trùng với tên URI variable và compiler giữ parameter names; khai báo tên tường minh vẫn dễ bảo trì hơn.

**Câu 8.** `@PathVariable(required=false)` có khiến `/{id}` tự match URL không có id không?

**Không.** Pattern phải cho phép URL đó match; optional chỉ tác động cách bind argument khi mapping hợp lệ có thể không cung cấp biến.

**Câu 9.** Path variable tenantId có đủ để chứng minh người dùng thuộc tenant đó không?

**Không.** Phải xác thực và authorize tenant/resource bằng identity đáng tin cậy.

**Câu 10.** WebFlux có tự match `/person` với `/person.json` không?

**Không.** WebFlux không hỗ trợ suffix pattern matching; dùng media type/Accept hoặc route rõ ràng.

## 20. Tài liệu tham khảo chính thức

- [Spring Framework — Mapping Requests trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): RequestMapping, URI pattern, PathPattern, regex, specificity và @PathVariable.
- [Spring Framework — Annotated Controllers trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): controller annotation và method mapping.
- [Spring Framework — WebFlux Config](https://docs.spring.io/spring-framework/reference/web/webflux/config.html): PathMatchConfigurer, RequestPath và cấu hình path matching.
- [Spring Framework — Method Arguments trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html): các argument resolver được hỗ trợ.
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html): converter và formatter cho giá trị request dạng String.
- [Spring Framework — URI Building](https://docs.spring.io/spring-framework/reference/web/webflux/uri-building.html): UriComponentsBuilder, URI template và encoding.
- [Spring Framework — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): validation cho controller method.
- [Spring Framework — WebFlux Security](https://docs.spring.io/spring-framework/reference/web/webflux/security.html): bảo vệ endpoint và tài nguyên.

**Ghi nhớ:** **PathPattern** quyết định URL nào match với controller; **@PathVariable** lấy các URI template variables đã capture và chuyển chúng sang kiểu Java. Biến thông thường chỉ chiếm một segment; regex giới hạn format; catch-all `{*path}` lấy nhiều segment. Mapping cấp class và method được ghép với nhau, pattern cụ thể được ưu tiên, còn việc xác thực dữ liệu, tìm tài nguyên và authorization vẫn thuộc trách nhiệm của ứng dụng.