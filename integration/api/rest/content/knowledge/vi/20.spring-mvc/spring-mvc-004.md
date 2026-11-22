# @PathVariable, @RequestParam, @RequestHeader và @CookieValue

## 1. Bốn nguồn dữ liệu trong một HTTP request

Trong Spring MVC, cùng một request có thể truyền nhiều loại dữ liệu đến controller. Điểm quan trọng không chỉ là biết cú pháp annotation mà là **lấy đúng thông tin từ đúng vị trí**, kiểm tra kiểu dữ liệu và không nhầm dữ liệu do client khai với thông tin đã được xác thực.

~~~http
GET /v1/orders/3b4c7a1e-659e-4cdb-a986-a0a54fae0b52?includeItems=true&limit=20 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept-Language: vi-VN
X-Request-Id: req-972
Cookie: ui_lang=vi; theme=dark
~~~

| Annotation | Đọc từ đâu? | Ví dụ trong request | Vai trò thường gặp |
|---|---|---|---|
| `@PathVariable` | Biến được khai báo trong **URI path pattern** | `3b4c...0b52` từ `/orders/{orderId}` | Định danh resource/parent |
| `@RequestParam` | Servlet **request parameters**: query string và, tùy content type, form fields | `includeItems=true`, `limit=20` | Lọc, phân trang, mở rộng response |
| `@RequestHeader` | **HTTP request header** | `Accept-Language: vi-VN`, `X-Request-Id` | Content negotiation, điều kiện HTTP, metadata |
| `@CookieValue` | **Cookie** được gửi trong `Cookie` header | `ui_lang=vi` | Tùy chọn giao diện, token cookie theo policy |

Các annotation này thuộc chương **Spring MVC** của module **INTEGRATION_API_REST**, nơi ta học thiết kế REST API theo resource, URI, method, status, hợp đồng dữ liệu, phân trang, cache, idempotency, xác thực/phân quyền và kiểm thử Java/Spring.

Sau bài học, bạn sẽ biết lựa chọn annotation đúng, sử dụng `required`/`defaultValue`/`Optional`, xử lý conversion và validation, tránh lỗi IDOR hoặc tin dữ liệu giả mạo, viết API minh họa và test hành vi HTTP bằng MockMvc.

**Không nên nhầm:** `@RequestBody` đọc body JSON/XML, `@RequestPart` đọc một phần multipart, còn `@RequestParam` có thể đọc field của form trong mô hình Servlet. Không dùng `@RequestParam` thay cho JSON body chỉ vì dữ liệu cũng là “tham số”.

## 2. @PathVariable: định danh tài nguyên theo URI

### 2.1. Khớp tên biến trong mapping

~~~java
@RestController
@RequestMapping("/v1/orders")
class OrderQueryController {
    private final OrderReadService service;

    OrderQueryController(OrderReadService service) {
        this.service = service;
    }

    @GetMapping("/{orderId}")
    OrderView get(@PathVariable("orderId") UUID id) {
        return service.findVisibleOrder(id);
    }
}
~~~

Request `GET /v1/orders/3b4c7a1e-659e-4cdb-a986-a0a54fae0b52` làm Spring MVC:

1. Chọn handler theo HTTP method và URI pattern `/v1/orders/{orderId}`.
2. Trích chuỗi segment của `{orderId}`.
3. Chuyển chuỗi thành `UUID` qua cơ chế conversion.
4. Gọi method; service quyết định resource có tồn tại và được phép xem không.

**Khai báo tên tường minh** `@PathVariable("orderId")` giúp dễ kiểm tra khi đổi tên biến Java và tránh phụ thuộc vào compiler parameter-name metadata. Đặt `@PathVariable UUID orderId` không ghi tên có thể hoạt động nếu dự án build với `-parameters`, nhưng tên trong Java, mapping và build phải phù hợp.

### 2.2. Nhiều biến path, đúng phạm vi nghiệp vụ

Ví dụ route `/v1/tenants/{tenantId}/orders/{orderId}` có hai tham số `@PathVariable("tenantId") UUID tenantId` và `@PathVariable("orderId") UUID orderId`.

`tenantId` là **dữ liệu client cung cấp trong path**, không phải bằng chứng user thuộc tenant ấy. Service phải đối chiếu tenant từ principal đã xác thực, ACL và chủ sở hữu resource. Nếu chỉ truy vấn `findById(orderId)` rồi trả kết quả, API có thể mắc **IDOR/BOLA**: người biết ID của tenant khác truy cập được dữ liệu.

Nếu một endpoint đại diện collection có biến động scope, chỉ dùng path phù hợp với resource model. Ví dụ `/v1/orders/{id}` và `/v1/tenants/{tenantId}/orders/{id}` đều khả thi, nhưng cần một quy ước URL rõ ràng, tránh nhân nhiều URI không có mục đích.

### 2.3. 400 hay 404 khi path sai?

| Request | Điều xảy ra thường gặp | HTTP status phù hợp |
|---|---|---|
| `GET /v1/orders/abc`, handler kỳ vọng `UUID` | Path khớp nhưng chuyển kiểu UUID thất bại | **400 Bad Request** |
| `GET /v1/unknown/123`, không có route | Không tìm thấy mapping | **404 Not Found** |
| `GET /v1/orders/{uuid}`, UUID hợp lệ nhưng bản ghi không tồn tại | Handler chạy, service không tìm thấy | **404 Not Found** |
| UUID hợp lệ của tenant khác | Service nhận diện resource ngoài scope | **404 trung tính** hoặc 403 tùy chính sách tiết lộ |

Nếu mapping có thêm regex hoặc điều kiện riêng, một giá trị path có thể **không match handler** ngay từ đầu và cho kết quả 404 thay vì 400. Không mặc định mọi lỗi trong URL đều cùng một status.

### 2.4. Không chuyển đường dẫn file thành quyền truy cập file

Với `@PathVariable String filename`, không ghép trực tiếp `baseDir + "/" + filename` để mở file. Tên file trong URI có thể chứa encoding và ký tự đặc biệt; slash đã encode có cách xử lý phụ thuộc container/proxy. Cách an toàn hơn là nhận **opaque file ID**, tra metadata và authorization, rồi mở object key do server quản lý. Tránh thiết kế nơi client điều khiển đường dẫn file hệ thống.

## 3. @RequestParam: query/filter/page và form fields

### 3.1. Required, optional và default

~~~java
@GetMapping("/v1/orders")
PageView<OrderView> list(
    @RequestParam(name = "status", required = false) String status,
    @RequestParam(name = "limit", defaultValue = "25") int limit,
    @RequestParam(name = "cursor", required = false) String cursor
) {
    return service.list(status, limit, cursor);
}
~~~

~~~http
GET /v1/orders?status=SUBMITTED&limit=50&cursor=opaque-next-token HTTP/1.1
~~~

Trong Spring MVC, `@RequestParam` mặc định là **`required=true`**. Không gửi tham số bắt buộc thường dẫn đến 400. Đặt `required=false` cho phép không truyền giá trị (đối với `String` thường nhận `null`); dùng `Optional<String>` khi muốn biểu đạt rõ optional. `defaultValue="25"` làm tham số không còn bắt buộc và thường cũng áp dụng khi giá trị rỗng; đừng dựa vào nó để phân biệt “không gửi” và “gửi chuỗi rỗng” nếu nghiệp vụ cần khác nhau.

**Quan trọng:** default không có nghĩa được bỏ qua validation. Query `limit=100000` có thể làm database kiệt tải nếu không áp giới hạn 1–100. Tương tự, `cursor` nên là token mờ được ký/xác minh theo tenant, filter, sort và hạn dùng, không chuyển trực tiếp thành mệnh đề SQL.

### 3.2. Chuyển kiểu và trường hợp lỗi

`@RequestParam("from") @DateTimeFormat(iso=DateTimeFormat.ISO.DATE) LocalDate from` đọc ngày từ `?from=2026-11-18`; `@RequestParam(defaultValue="false") boolean includeArchived` đọc boolean. Giá trị sai cú pháp như `from=not-a-date` thường gây **400**. Với thời điểm có múi giờ, công bố rõ định dạng/offset, không dùng `LocalDateTime` mơ hồ.

### 3.3. Tham số lặp lại và nhiều giá trị

~~~http
GET /v1/orders?status=SUBMITTED&status=APPROVED HTTP/1.1
~~~

~~~java
@GetMapping("/v1/orders/search")
List<OrderView> search(
    @RequestParam("status") List<String> statuses
) {
    return service.searchAllowedStatuses(statuses);
}
~~~

Spring có hỗ trợ binding collection từ request parameter; với repeated parameter như ví dụ, `statuses` chứa nhiều phần tử. Nếu cần giữ **toàn bộ các giá trị của từng key** thay vì một value trên mỗi key, dùng `MultiValueMap<String,String>` trong trường hợp phù hợp. Không coi thứ tự và cách gộp các giá trị như hợp đồng mặc định cho mọi client; hãy nêu quy ước `status=...&status=...` rõ trong OpenAPI.

`@RequestParam Map<String,String>` thuận tiện với query động, nhưng dễ đánh mất validation, cho client tùy ý truyền tên filter/sort. Với REST API có hợp đồng ổn định, ưu tiên **parameter có tên, kiểu và whitelist**.

### 3.4. Query parameter và form data không giống JSON body

Spring MVC trên Servlet dùng `@RequestParam` cho query string **và request parameters do form encoding tạo ra**, ví dụ `application/x-www-form-urlencoded`; với multipart cũng có thể bind form field. Nhưng:

~~~http
POST /v1/orders HTTP/1.1
Content-Type: application/json

{"productCode":"SKU-12","quantity":2}
~~~

Trường `productCode` nằm trong JSON body, nên thích hợp với `@RequestBody @Valid CreateOrderRequest`. Đừng dùng `@RequestParam("productCode")` và chờ nó tự đọc field JSON. Với file multipart, dùng `@RequestPart MultipartFile` (hoặc binding multipart tương ứng) và xử lý kích thước/loại file riêng.

## 4. @RequestHeader: thông tin giao thức, không phải định danh đáng tin

### 4.1. Đọc header có tên rõ ràng

~~~java
@GetMapping("/v1/catalog")
CatalogView catalog(
    @RequestHeader(name = "Accept-Language", required = false)
        String acceptLanguage,
    @RequestHeader(name = "X-Request-Id", required = false)
        String clientRequestId
) {
    return service.catalog(acceptLanguage, clientRequestId);
}
~~~

Header HTTP **không phân biệt chữ hoa/chữ thường ở tên**: `accept-language` và `Accept-Language` cùng chỉ một field. Nhưng giá trị header vẫn phải được parse/validate theo **ngữ nghĩa từng header**; ví dụ `Accept-Language` có thể chứa danh sách ngôn ngữ và quality weights, không phải luôn một mã `vi` đơn giản. Khi muốn locale đã được Spring resolve, có thể dùng tham số `Locale` do MVC hỗ trợ thay vì tự parse header.

Nếu header bắt buộc và bị thiếu, `@RequestHeader("X-Client-Version") String version` thường gây 400. Đặt `required=false` hoặc `Optional<String>` nếu thực sự không bắt buộc. Với default:

~~~java
@RequestHeader(name = "X-Channel", defaultValue = "web") String channel
~~~

Giá trị `web` chỉ là lựa chọn hợp đồng cho header không có/rỗng; không được dùng `X-Channel` để tự cấp vai trò như `ADMIN`.

### 4.2. Header kiểm soát điều kiện HTTP

Một API sửa đơn có thể yêu cầu client gửi `If-Match` để tránh ghi đè bản cập nhật đồng thời:

~~~http
PATCH /v1/orders/3b4c7a1e-659e-4cdb-a986-a0a54fae0b52 HTTP/1.1
Authorization: Bearer <access-token>
If-Match: "order-v7"
Content-Type: application/json

{"note":"Giao vào chiều thứ Sáu"}
~~~

~~~java
@PatchMapping("/v1/orders/{orderId}")
ResponseEntity<OrderView> changeNote(
    @PathVariable("orderId") UUID orderId,
    @RequestHeader(name = "If-Match", required = false)
        String ifMatch,
    @Valid @RequestBody ChangeNoteRequest body
) {
    if (ifMatch == null) {
        throw new PreconditionRequiredException(); // 428 theo policy
    }
    // Service xác thực quyền, parse/so ETag mạnh, cập nhật nguyên tử.
    OrderUpdate updated = service.changeNote(orderId, ifMatch, body.note());
    return ResponseEntity.ok()
        .eTag(updated.etag()) // giá trị cần đúng quy ước ETag của Spring
        .body(updated.value());
}
~~~

Ví dụ chỉ minh họa **cách lấy header**; `If-Match` cần so sánh **strong validator** theo RFC 9110, gồm danh sách tag/wildcard nếu hỗ trợ. Không so chuỗi thô, và không dùng một lần `SELECT` rồi `UPDATE` không điều kiện: cần lock/CAS hoặc `@Version` trong transaction. Thiếu precondition bắt buộc có thể trả **428**; gửi nhưng không khớp thường trả **412 Precondition Failed**. Những yêu cầu bị cấm vẫn phải bị chặn theo chính sách trước khi tiết lộ trạng thái resource.

### 4.3. Authorization phải do Spring Security xử lý

Mặc dù có thể viết `@RequestHeader("Authorization") String authorization`, **không nên tự giải mã bearer token trong controller** rồi tin payload JWT chưa kiểm chứng. Spring Security phải xác minh signature, issuer, audience, expiry và quyền trước; controller/service nhận identity từ `Authentication`, `@AuthenticationPrincipal` hoặc security context đã xác thực.

Tương tự, các header như `X-User-Id`, `X-Tenant-Id`, `X-Forwarded-For`, `X-Forwarded-Host` hoặc `X-Role` đều có thể bị client giả mạo khi không đi qua lớp proxy đáng tin. Chỉ tin header được gateway thiết lập khi ingress **xóa giá trị client gửi** và hệ thống có ranh giới trust rõ ràng.

### 4.4. Header lặp và map

Để đọc nhiều giá trị header của cùng tên, có thể sử dụng `@RequestHeader("X-Feature") List<String> features` hoặc `HttpHeaders` nếu cần giữ cấu trúc nhiều giá trị. `@RequestHeader Map<String,String>` thường chỉ biểu diễn một giá trị cho mỗi tên; `MultiValueMap<String,String>`/`HttpHeaders` phù hợp hơn khi cần toàn bộ. Đừng dùng một header tùy ý để quyết định logic bảo mật chỉ vì dễ lấy.

## 5. @CookieValue: nhận cookie, không phải xác nhận phiên

Cookie được trình duyệt gửi qua `Cookie` header:

~~~http
GET /v1/preferences HTTP/1.1
Cookie: ui_lang=vi; theme=dark
~~~

~~~java
@GetMapping("/v1/preferences")
PreferenceView preferences(
    @CookieValue(name = "ui_lang", defaultValue = "vi")
        String language,
    @CookieValue(name = "theme", required = false)
        String theme
) {
    return service.publicPreferences(language, theme);
}
~~~

`@CookieValue` mặc định `required=true`, có thể nhận `String` hoặc kiểu được converter hỗ trợ; dùng `required=false`, `Optional<T>` hoặc `defaultValue` khi phù hợp. Nếu thiếu cookie bắt buộc thường dẫn tới 400. Nếu cookie có giá trị không thể chuyển sang kiểu Java tương ứng, request cũng có thể bị từ chối theo cơ chế binding.

**Cookie là dữ liệu client gửi.** `ui_lang=admin` hay `session_id=123` không chứng minh người gọi được làm admin hoặc sở hữu session 123. Tùy chọn UI có thể cần whitelist `vi`/`en`; cookie phiên hoặc JWT phải được xác minh qua Spring Security/session manager, không chỉ đọc bằng `@CookieValue` rồi dùng như identity.

### 5.1. Cookie request khác Set-Cookie response

`@CookieValue` chỉ **đọc cookie đến**, không tự tạo cookie mới. Server cấp/đổi cookie bằng header `Set-Cookie`:

Ví dụ response: `Set-Cookie: ui_lang=vi; Path=/; Max-Age=2592000; Secure; SameSite=Lax`.

Với cookie xác thực/session, thường cần `HttpOnly`, `Secure`, `SameSite` và phạm vi Path/Domain hợp lý; thời hạn sống phải phù hợp chính sách đăng nhập. `HttpOnly` ngăn JavaScript đọc trực tiếp cookie, nhưng **không bảo vệ khỏi CSRF**: trình duyệt vẫn có thể tự gửi cookie theo quy tắc. Khi ứng dụng dùng cookie-based authentication, cần thiết kế kiểm soát CSRF phù hợp với các phương thức thay đổi trạng thái.

`SameSite` giảm một số nguy cơ gửi cookie cross-site nhưng không thay thế toàn bộ kiểm tra Origin/CSRF token. Không đưa session ID vào query parameter hoặc log nếu không cần. Nếu cookie có cấu trúc do client sửa được, dùng chữ ký/MAC khi cần bảo vệ tính toàn vẹn hoặc chỉ lưu một ID mờ để lookup server-side.

### 5.2. Khi không nên đọc cookie trực tiếp

Đối với principal hiện hành, dùng Spring Security thay vì `@CookieValue("JSESSIONID")`. Đối với locale, ưu tiên cơ chế `LocaleResolver`/`LocaleContextResolver` khi ứng dụng đã có chiến lược ngôn ngữ thống nhất. `@CookieValue` phù hợp với dữ liệu cookie cụ thể mà endpoint thực sự cần, không phải thay thế mọi cơ chế framework.

## 6. Mặc định, null và lỗi binding: so sánh nhanh

| Tình huống | Annotation | Hành vi thường gặp |
|---|---|---|
| Thiếu biến trong route pattern | `@PathVariable` | Không match route hoặc lỗi mapping; thường 404 |
| Path có trong route nhưng UUID sai | `@PathVariable UUID` | Conversion error, thường **400** |
| Query/header/cookie bắt buộc bị thiếu | `@RequestParam`/`@RequestHeader`/`@CookieValue` | **400 Bad Request** |
| Query/header/cookie có `required=false` | Như trên | Giá trị `null` hoặc kiểu optional tương ứng |
| Có `defaultValue` | RequestParam/Header/CookieValue | Dùng giá trị mặc định khi thiếu/rỗng theo Spring |
| `Optional<T>` | Các nguồn phù hợp | Vắng mặt được biểu diễn thành `Optional.empty()` |
| Query/header không chuyển được thành số/ngày/enum | Binding + conversion | Thường **400** |
| Constraint `@Min`/`@Pattern` không đạt | Validation đã được bật | Kết quả phụ thuộc handler; API nên map thành **400** |
| Principal không có quyền đọc resource | Service/security | **403** hoặc **404** để che giấu |

**Chi tiết phiên bản:** cơ chế method validation và exception cụ thể có thay đổi giữa các Spring Framework/Boot minor. Với Spring Framework 6.1+, MVC hỗ trợ method validation tích hợp cho constraint trên method parameters; dùng đúng `spring-boot-starter-validation`/Bean Validation dependency và kiểm thử response status/ProblemDetail thực tế. Đừng chỉ nhìn annotation rồi cho rằng hệ thống chắc chắn trả đúng status mong muốn.

## 7. Ví dụ xuyên suốt: API tra cứu đơn hàng trong Spring Boot

Giả sử dịch vụ REST có hai thao tác: tra cứu một đơn và liệt kê đơn. Bốn annotation phục vụ **bốn mục đích khác nhau**, trong khi quyền truy cập do service kiểm tra theo principal.

### 7.1. Controller minh họa (Java 17+, Spring Boot 3)

Request mẫu ở Mục 1 truyền `orderId`, `includeItems`, `X-Request-Id` và `ui_lang`. Server trả `200` cùng `OrderView` sau khi xác thực và kiểm quyền; cookie chỉ điều khiển hiển thị, header request ID chỉ giúp truy vết, không thay đổi ACL.

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.validation.annotation.Validated;
import java.util.UUID;

@RestController
@RequestMapping("/v1/orders")
@Validated
class OrderRestController {
    private final OrderService orders;
    private final ActorFactory actors;

    OrderRestController(OrderService orders, ActorFactory actors) {
        this.orders = orders;
        this.actors = actors;
    }

    @GetMapping("/{orderId}")
    ResponseEntity<OrderView> getOne(
        @PathVariable("orderId") UUID orderId,
        @RequestParam(name = "includeItems", defaultValue = "false")
            boolean includeItems,
        @RequestHeader(name = "X-Request-Id", required = false)
            String requestId,
        @CookieValue(name = "ui_lang", defaultValue = "vi")
            String uiLanguage,
        @AuthenticationPrincipal Jwt jwt
    ) {
        Actor actor = actors.fromVerifiedJwt(jwt);
        OrderView result = orders.findVisible(
            actor,
            orderId,
            includeItems,
            validateUiLanguage(uiLanguage),
            normalizeRequestId(requestId)
        );
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(result);
    }

    @GetMapping
    ResponseEntity<OrderPage> list(
        @RequestParam(name = "status", required = false)
            String status,
        @RequestParam(name = "limit", defaultValue = "25")
            @Min(1) @Max(100) int limit,
        @RequestParam(name = "cursor", required = false)
            String cursor,
        @AuthenticationPrincipal Jwt jwt
    ) {
        Actor actor = actors.fromVerifiedJwt(jwt);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(orders.findPage(actor, status, limit, cursor));
    }
}
~~~

`OrderService`, `ActorFactory`, `validateUiLanguage` và `normalizeRequestId` là thành phần minh họa cần hiện thực trong project; chúng **không phải method của Spring có sẵn**. DTO `OrderView`/`OrderPage` cũng phải được định nghĩa. Vì code này tập trung vào HTTP binding, nó không bao gồm SQL/JPA hoặc security config.

**Ranh giới trách nhiệm nên rõ:** controller nhận và convert đầu vào; validation từ chối cú pháp/kiểu/giới hạn không hợp lệ; service dùng principal đáng tin để lọc tenant/owner và áp dụng policy; repository chỉ truy vấn resource được phép. Đối với `status`, dùng enum/whitelist thay vì truyền string tùy ý vào SQL; đối với `cursor`, xác minh chữ ký/phạm vi nếu đó là token đã mã hóa.

**Về `@Validated`:** annotation ở cấp class có thể dùng validation qua AOP; Spring MVC 6.1+ còn có method validation tích hợp. Chọn cơ chế phù hợp phiên bản, tránh hai đường validation chồng chéo và test response 400 thực tế.

### 7.2. Tài liệu OpenAPI cho bốn nguồn

Một operation GET sẽ có bốn `parameters` phân biệt bởi `in`:

~~~yaml
paths:
  /v1/orders/{orderId}:
    get:
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
        - name: includeItems
          in: query
          required: false
          schema:
            type: boolean
            default: false
        - name: X-Request-Id
          in: header
          required: false
          schema:
            type: string
        - name: ui_lang
          in: cookie
          required: false
          schema:
            type: string
            default: vi
      responses:
        "200":
          description: Đơn hàng được phép xem
        "400":
          description: Input không hợp lệ
        "401":
          description: Thiếu hoặc sai xác thực
        "404":
          description: Không có đơn hoặc không được phép tiết lộ
~~~

Đây là **trích đoạn OpenAPI**, không phải file spec hoàn chỉnh. Springdoc có thể suy một phần từ controller, nhưng cần xác minh tên parameter, `required`, default và lỗi trong tài liệu thực tế. Không viết `Authorization` như một header parameter độc lập để thay thế **security scheme** `http bearer`; auth nên được mô tả bằng `securitySchemes` và `security`.

## 8. Validation và lỗi HTTP có cấu trúc

Binding thất bại và nghiệp vụ từ chối là **hai loại lỗi khác nhau**:

~~~text
HTTP request
   |
   +-- Không khớp path/method --> 404/405 theo routing
   |
   +-- Khớp handler
          |
          +-- Thiếu required / conversion lỗi --> 400
          +-- Bean Validation không đạt --> lỗi validation (map 400)
          +-- Identity không hợp lệ --> 401
          +-- Không có quyền --> 403 hoặc 404 trung tính
          +-- Không có resource --> 404
          +-- Nghiệp vụ xung đột --> 409
          +-- Thành công --> 200/201/204 tùy operation
~~~

Không nhất thiết mọi framework sẽ kiểm tra theo **đúng thứ tự dòng sơ đồ**: security filter có thể từ chối **trước MVC handler**; status cuối còn tùy exception handler, content negotiation và policy. Sơ đồ chỉ phân nhóm trách nhiệm giúp tránh trả 500 cho input sai.

### 8.1. Map lỗi có ý nghĩa cho client

Ví dụ `GET /v1/orders?limit=abc` dẫn tới 400:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/invalid-parameter",
  "title": "Bad Request",
  "status": 400,
  "detail": "Tham số 'limit' phải là số nguyên từ 1 đến 100.",
  "code": "INVALID_PARAMETER"
}
~~~

Trong Spring Boot 3, `ProblemDetail` giúp trình bày lỗi theo **RFC 9457**. Cần bổ sung handler cho các nhóm `MissingServletRequestParameterException`, `MethodArgumentTypeMismatchException`, lỗi validation và lỗi nghiệp vụ phù hợp. Không trả stack trace, SQL hay thông tin tenant khác; logger nội bộ có thể lưu exception chi tiết với request ID đã kiểm tra.

Với `@RestControllerAdvice`, map `MethodArgumentTypeMismatchException` sang `ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, ...)` và `code=INVALID_PARAMETER`; xử lý riêng lỗi thiếu parameter, Bean Validation, quyền và nghiệp vụ. **Không bắt `Exception.class` rồi trả 400 cho mọi lỗi**, vì sẽ che giấu sự cố vận hành.

## 9. Checklist bảo mật cho dữ liệu lấy từ request

| Nguồn | Điều phải kiểm tra |
|---|---|
| `@PathVariable` | Chỉ dùng ID để lookup trong **scope đã xác thực**, không dùng ID thay quyền; không ghép filename vào path hệ thống |
| `@RequestParam` | Whitelist filter/sort, giới hạn `limit`, validate cursor, không ghép chuỗi thành SQL |
| `@RequestHeader` | Không tin `X-User-Id`/`X-Role` hoặc forwarded headers ngoài trusted proxy; giới hạn header tự do |
| `@CookieValue` | Không coi cookie tự khai là principal; cookie auth qua Spring Security/session, chú ý CSRF/SameSite |

Ở mọi endpoint, **authentication** xác minh ai đang gọi, **authorization** xác định người ấy được xem/sửa resource nào, còn những annotation trên chỉ **bind dữ liệu do HTTP request cung cấp**. Các quyết định tenant/owner phải nằm ở service hoặc policy và được bảo vệ ở tầng truy vấn. Khi dùng cookie session, không bỏ kiểm soát CSRF cho POST/PUT/PATCH/DELETE chỉ vì GET đã hoạt động.

## 10. Kiểm thử MockMvc: đọc đúng nguồn và từ chối đầu vào sai

### 10.1. Ma trận kiểm thử

| Ca | Yêu cầu | Kỳ vọng |
|---|---|---|
| B01 | Path UUID hợp lệ, đơn trong tenant | 200 và đúng đơn |
| B02 | Path UUID sai cú pháp | 400 khi route khớp |
| B03 | Path ID hợp lệ nhưng resource không tồn tại | 404 |
| B04 | Không truyền `includeItems` | Dùng default `false` |
| B05 | `?includeItems=true` | Service nhận `true` |
| B06 | `?limit=abc` | 400 do conversion |
| B07 | `?limit=1000` | 400 nếu validation 1–100 được bật/map đúng |
| B08 | Thiếu `X-Request-Id` optional | Request vẫn hợp lệ |
| B09 | Có `Cookie: ui_lang=vi` | Đọc đúng cookie; không đổi quyền |
| B10 | Không có `ui_lang` | Dùng default `vi` |
| B11 | Token tenant B truy cập order tenant A | 404 trung tính theo policy |
| B12 | Người dùng gửi `X-Role: ADMIN` giả | Không được cấp quyền mới |
| B13 | PATCH thiếu `If-Match` trong API yêu cầu precondition | 428 theo hợp đồng |

### 10.2. MockMvc tích hợp

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderRequestBindingTest {
    @Autowired MockMvc mvc;
    UUID orderId = UUID.fromString(
        "3b4c7a1e-659e-4cdb-a986-a0a54fae0b52");

    @Test
    void bindsPathQueryHeaderAndCookie() throws Exception {
        mvc.perform(get("/v1/orders/{orderId}", orderId)
                .param("includeItems", "true")
                .header("X-Request-Id", "req-972")
                .cookie(new Cookie("ui_lang", "vi"))
                .with(jwt().jwt(j -> j
                    .subject("owner-7")
                    .claim("tenant_id", "tenant-a"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(orderId.toString()));
    }

    @Test
    void malformedUuidIsBadRequest() throws Exception {
        mvc.perform(get("/v1/orders/{orderId}", "not-a-uuid")
                .with(jwt()))
            .andExpect(status().isBadRequest());
    }

    @Test
    void badLimitIsBadRequest() throws Exception {
        mvc.perform(get("/v1/orders")
                .param("limit", "not-a-number")
                .with(jwt()))
            .andExpect(status().isBadRequest());
    }
}
~~~

Test là **khung minh họa**: cần import JUnit, Spring Security Test, `jakarta.servlet.http.Cookie`, fixtures, repository/service, JWT authority đúng policy. `jwt()` tạo principal cho test, **không kiểm chứng chữ ký/issuer/audience của token thật**; cần security integration test riêng. Với ca B11, dùng order fixture thuộc tenant A, gửi principal B và assert 404 cùng database không đổi.

Không chỉ assert status: có thể dùng spy/fake service để xác minh `includeItems=true`, `ui_lang=vi` và request ID được xử lý đúng; test header/cookie thiếu, lặp, input độc hại và `defaultValue`. Với API có session cookie thực, test CSRF khi gọi method ghi; MockMvc `.with(csrf())` chỉ mô phỏng token hợp lệ, không tự chứng minh mọi cấu hình production an toàn.

## 11. Bài tập thực hành và đáp án

**Bài tập:** thiết kế `GET /v1/tenants/{tenantId}/orders/{orderId}?includeItems=true&limit=20`, nhận `X-Request-Id` optional và cookie `ui_lang` mặc định `vi`. Yêu cầu: chọn bốn annotation, giải thích mã lỗi khi `limit=abc`, khi không có cookie, khi tenant trong path khác tenant của principal. Có nên lấy `Authorization` qua `@RequestHeader` và tự parse JWT?

**Gợi ý lời giải:** dùng `@PathVariable` cho `tenantId/orderId`; `@RequestParam` cho `includeItems/limit`; `@RequestHeader(required=false)` cho request ID; `@CookieValue(defaultValue="vi")` cho ngôn ngữ UI. `limit=abc` thông thường là **400** do conversion; thiếu cookie dùng `vi`; tenant không phù hợp phải bị **403/404 theo chính sách**, không phải vì UUID hợp lệ mà được truy cập. Token cần được Spring Security xác minh; controller lấy principal đáng tin, không tự parse bearer string chưa xác thực.

**Câu hỏi mở:** `limit` có ý nghĩa gì khi đang đọc **một đơn**? Nếu nó chỉ giới hạn số item của đơn, hãy đặt tên rõ như `itemsLimit` và mô tả pagination của subcollection; nếu không, **bỏ limit khỏi detail endpoint** và dùng nó trong `GET /v1/orders`. Thiết kế nguồn dữ liệu đúng còn phải đi cùng **hợp đồng API nhất quán**.

## 12. Checklist và nguồn tham khảo

- [ ] URI template và tên `@PathVariable` khớp; ID được chuyển kiểu và kiểm quyền theo tenant/owner.
- [ ] `@RequestParam` có kiểu, default, giới hạn, whitelist và quy ước nhiều giá trị rõ ràng.
- [ ] `@RequestHeader` chỉ đọc metadata phù hợp; auth dùng principal đã được framework xác thực.
- [ ] `@CookieValue` dùng cho cookie cần thiết; session/cookie auth bảo vệ CSRF và quyền truy cập.
- [ ] Phân biệt path/query/header/cookie với JSON `@RequestBody` và multipart `@RequestPart`.
- [ ] Thiếu input/conversion/validation được map thành 400; 401/403/404 phản ánh policy.
- [ ] OpenAPI khai báo `in: path/query/header/cookie` đúng, không biến bearer thành header param tùy tiện.
- [ ] MockMvc có cả happy path, missing/default, malformed value, cross-tenant và runtime security test.

**Đọc thêm:** [Spring Framework — Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html), [@PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/uri-templates.html), [@RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html), [@RequestHeader](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html), [@CookieValue](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html) và [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457).

**Kết luận:** `@PathVariable` xác định resource, `@RequestParam` điều khiển truy vấn, `@RequestHeader` lấy metadata HTTP, còn `@CookieValue` đọc cookie. Cả bốn đều bind **dữ liệu từ client**, không thay thế xác thực, phân quyền, validation hay kiểm thử; một REST API tốt phải xác định rõ nguồn, kiểu, default và lỗi cho từng tham số.
