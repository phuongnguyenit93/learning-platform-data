# Kiểm thử cache response

## Mục tiêu

Sau bài này, bạn có thể kiểm thử chính sách HTTP cache cho representation Spring HATEOAS, chọn `Cache-Control` phù hợp với dữ liệu công khai hoặc cá nhân hóa, xác nhận `ETag` và conditional GET trả `304 Not Modified`, kiểm tra `Vary` khi content negotiation thay đổi representation, đồng thời phân biệt HTTP response caching với cache dữ liệu phía server bằng Spring Cache.

## 1. Vì sao phải kiểm thử cache response?

Một response Spring HATEOAS có thể chứa dữ liệu, embedded resources, links và affordances. Khi response được cache, client hoặc proxy có thể tái sử dụng toàn bộ representation trong một khoảng thời gian. Điều này giảm số request và tải xử lý, nhưng cũng có thể khiến client nhận dữ liệu hoặc links đã cũ.

Ví dụ một đơn hàng có trạng thái `PENDING` và link `cancel`:

```json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/order-42"
    },
    "https://api.example.com/rels/cancel": {
      "href": "/orders/order-42/cancel"
    }
  }
}
```

Sau khi đơn hàng được thanh toán, link `cancel` có thể không còn hợp lệ. Nếu client tiếp tục dùng representation cũ từ cache, nó vẫn nhìn thấy link đó. Endpoint đích vẫn phải kiểm tra trạng thái và quyền, nhưng cache policy hợp lý sẽ giảm thời gian client nhìn thấy khả năng đã hết hiệu lực.

Kiểm thử cache response giúp xác nhận:

- Response có chính sách lưu trữ phù hợp với độ nhạy của dữ liệu.
- Cache không dùng nhầm representation giữa các media type hoặc phiên bản.
- Validator phản ánh đúng nội dung representation, bao gồm links.
- Client có thể revalidate bằng `ETag` thay vì tải lại body.
- Response sau thao tác ghi không bị cache cũ làm sai lệch luồng điều hướng.

Trong API hypermedia, cache cần được đánh giá trên toàn bộ representation. Link `self`, `next`, `cancel`, `approve` hoặc link đến tài nguyên nhạy cảm cũng là một phần nội dung được cache.

## 2. Phân biệt HTTP response cache và Spring Cache

Hai cơ chế thường bị nhầm:

| Cơ chế | Cache cái gì? | Cách cấu hình thường gặp |
|---|---|---|
| HTTP response caching | HTTP representation và metadata như freshness, validator | `Cache-Control`, `ETag`, `Last-Modified`, `Vary` |
| Spring Cache abstraction | Kết quả gọi method phía server | `@Cacheable`, `@CachePut`, `@CacheEvict` |

`@Cacheable` có thể tránh truy vấn repository hoặc tính toán lại DTO, nhưng nó không tự động tạo header `Cache-Control`, `ETag` hay `Vary` cho HTTP response. Ngược lại, HTTP cache có thể tái sử dụng response mà không gọi lại controller khi response còn fresh.

Một ứng dụng có thể dùng cả hai cơ chế, nhưng cần thiết kế chúng độc lập:

- Spring Cache kiểm soát việc tái sử dụng dữ liệu hoặc kết quả method phía server.
- HTTP cache kiểm soát việc client, browser, reverse proxy hoặc CDN lưu và revalidate response.
- Khi dữ liệu thay đổi, cần cân nhắc cả việc evict server-side cache và cách làm mới HTTP representation.

Bài này tập trung vào HTTP response caching vì đó là cơ chế trực tiếp ảnh hưởng representation hypermedia mà client nhận được.

## 3. Chọn Cache-Control theo loại representation

`Cache-Control` xác định response có thể được lưu ở đâu và trong bao lâu.

| Directive | Ý nghĩa | Trường hợp thường dùng |
|---|---|---|
| `max-age=60` | Response fresh trong 60 giây kể từ lúc tạo | Dữ liệu thay đổi chậm |
| `private` | Chỉ private cache như browser được lưu; shared cache không được dùng response | Representation phụ thuộc người dùng |
| `public` | Cho phép shared cache lưu response nếu các điều kiện khác đáp ứng | Representation thực sự giống nhau giữa người dùng |
| `no-cache` | Có thể lưu nhưng phải revalidate trước khi tái sử dụng | Muốn cache body nhưng luôn xác nhận với server |
| `no-store` | Không lưu response vào cache | Dữ liệu nhạy cảm hoặc link ngắn hạn |
| `must-revalidate` | Khi response stale, cache phải revalidate trước khi dùng lại | Không được tái sử dụng dữ liệu hết freshness |
| `s-maxage=...` | Freshness lifetime dành cho shared cache | Chính sách riêng cho proxy/CDN |

Một số lựa chọn điển hình:

**Tài nguyên công khai, ít thay đổi**

```http
Cache-Control: public, max-age=300
```

Chỉ dùng `public` nếu body và links không phụ thuộc principal, tenant, quyền hoặc thông tin xác thực.

**Tài nguyên cá nhân hóa**

```http
Cache-Control: private, max-age=30
```

Browser có thể lưu response trong thời gian ngắn; shared cache không được tái sử dụng response này cho người khác.

**Representation nhạy cảm hoặc chứa link tạm thời**

```http
Cache-Control: no-store
```

Không lưu response vào cache. Đây là lựa chọn phù hợp khi representation chứa dữ liệu nhạy cảm hoặc URI ký số có thời hạn.

**Muốn lưu body nhưng luôn hỏi server trước khi dùng lại**

```http
Cache-Control: private, no-cache
```

`no-cache` không có nghĩa là “không lưu”. Cache có thể giữ response, nhưng phải revalidate trước khi sử dụng lại. `no-store` mới là chỉ thị không lưu response.

Không chọn `public` chỉ để tăng hiệu năng. Nếu links thay đổi theo quyền, chủ sở hữu, tenant hoặc trạng thái người dùng, response không phải representation công khai dùng chung.

## 4. Caching ảnh hưởng đến hypermedia links như thế nào?

Representation HATEOAS công bố các khả năng tại thời điểm server tạo response. Cache có thể tiếp tục cung cấp representation đó sau khi trạng thái nghiệp vụ thay đổi.

Ví dụ:

1. Đơn hàng đang `PENDING`; response có link `cancel`.
2. Người dùng hủy đơn hàng hoặc đơn hàng được thanh toán.
3. Representation mới không còn link `cancel`.
4. Client vẫn giữ representation cũ trong cache và nhìn thấy link cũ.

Đây không phải lý do để bỏ kiểm tra quyền hoặc trạng thái ở endpoint đích. Link chỉ mô tả khả năng tại thời điểm representation được tạo. Endpoint phải xác thực và kiểm tra điều kiện nghiệp vụ lại tại thời điểm request thực sự đến.

Để hạn chế link stale:

- Dùng `max-age` ngắn cho tài nguyên có trạng thái thay đổi thường xuyên.
- Dùng `no-cache` nếu cần revalidate trước mỗi lần tái sử dụng.
- Dùng `no-store` cho representation có dữ liệu nhạy cảm hoặc link tạm thời.
- Dùng ETag để client revalidate với chi phí truyền tải thấp.
- Làm mới hoặc purge cache collection khi thao tác ghi ảnh hưởng đến các item hoặc link điều hướng.
- Không xem sự hiện diện của link là bằng chứng quyền vẫn còn hiệu lực.

Đặc biệt chú ý collection response. Sau khi tạo hoặc xóa item, response collection có thể đã cũ dù URI của collection không thay đổi. Chính sách cache cần tính đến tác động của thao tác ghi lên cả item lẫn collection.

## 5. Dùng CacheControl trong ResponseEntity

Spring Framework cung cấp `CacheControl` để tạo header cache mà không phải tự ghép chuỗi.

Ví dụ endpoint trả representation công khai, có thể cache trong một phút:

```java
import java.time.Duration;
import java.util.UUID;

import org.springframework.hateoas.MediaTypes;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@GetMapping(
        value = "/public/orders/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
)
public ResponseEntity<OrderModel> getPublicOrder(
        @PathVariable UUID id) {

    Order order = orderService.getPublicOrder(id);
    OrderModel model = assembler.toPublicModel(order);

    return ResponseEntity.ok()
            .cacheControl(CacheControl.maxAge(Duration.ofMinutes(1))
                    .cachePublic())
            .varyBy("Accept")
            .body(model);
}
```

Ví dụ giả định representation công khai giống nhau cho mọi client và assembler chỉ công bố dữ liệu, links được phép chia sẻ. `varyBy("Accept")` cần thiết nếu cùng URI có thể trả representation khác nhau theo media type được yêu cầu.

Với response phụ thuộc người dùng:

```java
@GetMapping(
        value = "/orders/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
)
public ResponseEntity<OrderModel> getOrder(
        @PathVariable UUID id) {

    Order order = orderService.getRequired(id);
    OrderModel model = assembler.toModelForCurrentUser(order);

    return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .varyBy("Accept")
            .body(model);
}
```

Ví dụ dùng `no-store` vì representation có thể chứa links theo quyền của người dùng hiện tại. Nếu ứng dụng cho phép private browser cache và có cơ chế revalidation phù hợp, có thể chọn `private` cùng freshness lifetime hoặc `private, no-cache`. Hãy xác định rõ yêu cầu bảo mật và hành vi mong muốn trước khi nới chính sách.

`CacheControl` chỉ tạo chính sách HTTP. Nó không tự evict Spring Cache, không làm mới dữ liệu trong repository và không bảo đảm links đã được tạo đúng theo quyền.

## 6. Dùng ETag làm validator cho representation

`ETag` là validator định danh một phiên bản representation. Client lưu ETag cùng response; khi muốn kiểm tra response có thay đổi không, client gửi `If-None-Match`.

Ví dụ response lần đầu:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
ETag: "order-42-v17"
Cache-Control: private, max-age=0, must-revalidate
```

Khi client revalidate:

```http
GET /orders/42 HTTP/1.1
Accept: application/hal+json
If-None-Match: "order-42-v17"
```

Nếu representation chưa thay đổi, server trả:

```http
HTTP/1.1 304 Not Modified
ETag: "order-42-v17"
Cache-Control: private, max-age=0, must-revalidate
```

`304 Not Modified` không mang representation body mới. Cache client sử dụng body đã lưu và cập nhật metadata theo response revalidation.

Nếu representation đã thay đổi, server trả `200 OK`, ETag mới và representation mới.

ETag có thể là strong validator hoặc weak validator:

- Strong ETag, ví dụ `"order-42-v17"`, biểu thị representation được xác định chính xác theo validator.
- Weak ETag, ví dụ `W/"order-42-v17"`, cho phép một số khác biệt không ảnh hưởng ý nghĩa representation theo quy tắc HTTP.

Với response HAL, validator phải tính đến các phần có thể làm body thay đổi: dữ liệu item, embedded resources, links, affordances và media type variant. Chỉ dùng `@Version` của entity làm ETag khi mọi thay đổi ảnh hưởng representation đều làm version đó thay đổi và representation không phụ thuộc vào principal hoặc ngữ cảnh khác.

## 7. Xử lý conditional GET bằng WebRequest

Spring MVC cung cấp `WebRequest.checkNotModified(...)` để xử lý validator của request. Khi ETag khớp với `If-None-Match`, Spring đánh dấu response là `304 Not Modified`.

Ví dụ endpoint có representation ổn định, dùng phiên bản resource làm validator:

```java
import java.time.Duration;
import java.util.UUID;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.context.request.WebRequest;

@GetMapping(
        value = "/public/orders/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
)
public ResponseEntity<OrderModel> getOrder(
        @PathVariable UUID id,
        WebRequest request,
        HttpServletResponse response) {

    Order order = orderService.getPublicOrder(id);

    String etag = "\"order-" + id + "-v" + order.getVersion() + "\"";
    String cachePolicy = "public, max-age=0, must-revalidate";

    // checkNotModified có thể kết thúc request bằng 304 trước khi
    // ResponseEntity được tạo, nên đặt các header cần có trên 304 trước.
    response.setHeader(HttpHeaders.CACHE_CONTROL, cachePolicy);
    response.setHeader(HttpHeaders.VARY, HttpHeaders.ACCEPT);

    if (request.checkNotModified(etag)) {
        return null;
    }

    OrderModel model = assembler.toPublicModel(order);

    return ResponseEntity.ok()
            .eTag(etag)
            .cacheControl(CacheControl.maxAge(Duration.ZERO)
                    .cachePublic()
                    .mustRevalidate())
            .varyBy(HttpHeaders.ACCEPT)
            .body(model);
}
```

Spring xử lý response 304 khi validator khớp; controller không cần serialize representation trong nhánh đó. Khi validator không khớp hoặc không được gửi, controller tạo model và trả body cùng ETag.

Ví dụ này giả định ETag dựa trên version của resource đủ để xác định toàn bộ representation công khai. Nếu assembler thêm link dựa trên quyền, tenant, feature flag hoặc trạng thái ngoài resource version, validator phải tính đến những yếu tố làm thay đổi representation đó. Nếu không thể tạo validator đúng, không nên phát ETag gây hiểu nhầm.

`CacheControl.maxAge(Duration.ZERO).mustRevalidate()` yêu cầu response stale ngay và phải revalidate trước khi tái sử dụng. Đây là lựa chọn hữu ích khi muốn client giữ body nhưng server luôn có cơ hội xác nhận validator.

## 8. ETag phải phản ánh link và affordance

Với JSON thông thường, một số hệ thống chỉ tính validator dựa trên version của bản ghi. Với HATEOAS, cách đó có thể sai nếu link thay đổi mà entity không đổi.

Ví dụ dữ liệu đơn hàng vẫn như cũ, nhưng quyền của người dùng bị thu hồi:

- Trước đó representation có link `approve`.
- Sau khi quyền bị thu hồi, assembler bỏ link `approve`.
- Entity `Order` không thay đổi nên `order.getVersion()` vẫn giữ nguyên.
- Nếu ETag chỉ dựa vào version entity, server có thể trả 304 và client tiếp tục dùng body cũ có link `approve`.

Có ba hướng xử lý:

1. **Không cache response cá nhân hóa:** dùng `Cache-Control: no-store` nếu representation phụ thuộc quyền và không có validator an toàn.
2. **Tính validator theo representation:** tạo ETag từ nội dung representation cuối cùng hoặc một phiên bản tổng hợp bao gồm dữ liệu và các yếu tố làm thay đổi links.
3. **Gắn version của policy/visibility:** chỉ phù hợp nếu hệ thống có version rõ ràng cho mọi yếu tố quyền và link tham gia response.

Không dùng ETag của entity như validator của representation nếu nó không phản ánh đầy đủ các thay đổi đó. Đây là lỗi có thể làm client giữ khả năng đã bị thu hồi.

## 9. Vary khi response phụ thuộc request header

`Vary` liệt kê các request header ảnh hưởng đến cách chọn representation. Cache dùng các giá trị header đó để phân biệt biến thể response.

Ví dụ cùng URI hỗ trợ HAL và HAL-FORMS:

```http
Vary: Accept
```

Nếu cùng URI chọn API version bằng header:

```http
Vary: Accept, X-API-Version
```

Nếu representation thay đổi theo ngôn ngữ:

```http
Vary: Accept, Accept-Language
```

Trong Spring MVC:

```java
import org.springframework.http.HttpHeaders;

return ResponseEntity.ok()
        .varyBy(
                HttpHeaders.ACCEPT,
                HttpHeaders.ACCEPT_LANGUAGE
        )
        .body(model);
```

Chỉ đưa header thực sự ảnh hưởng representation vào `Vary`. Không dùng `Vary` thay cho chính sách bảo vệ response cá nhân hóa. Với dữ liệu phụ thuộc principal, dùng `private` hoặc `no-store` theo yêu cầu; không dựa vào cache key để cách ly người dùng.

Nếu version nằm trong URI path như `/v1/orders` và `/v2/orders`, URI đã khác nhau nên không cần `Vary: X-API-Version` chỉ vì path versioning. Nếu version nằm trong request header, phải đưa header đó vào `Vary`.

## 10. Last-Modified và If-Modified-Since

Ngoài ETag, HTTP hỗ trợ validator theo thời điểm sửa đổi:

- Server trả `Last-Modified`.
- Client gửi `If-Modified-Since` trong request tiếp theo.
- Server trả 304 nếu representation không thay đổi kể từ thời điểm đó.

Ví dụ:

```http
HTTP/1.1 200 OK
Last-Modified: Thu, 26 Nov 2026 04:00:00 GMT
```

Request revalidation:

```http
GET /orders/42 HTTP/1.1
If-Modified-Since: Thu, 26 Nov 2026 04:00:00 GMT
```

Last-Modified dễ triển khai nếu dữ liệu có timestamp cập nhật đáng tin cậy. Tuy nhiên, độ chính xác thời gian HTTP chỉ đến giây và timestamp của entity có thể không phản ánh thay đổi trong link visibility hoặc affordance. ETag thường phù hợp hơn khi representation được tổng hợp từ nhiều nguồn.

Spring MVC có thể dùng `WebRequest.checkNotModified(lastModified)` hoặc overload kết hợp ETag và thời gian sửa đổi. Nếu dùng cả ETag và Last-Modified, cần kiểm thử ưu tiên validator theo semantics HTTP; không tự viết logic so sánh header rời rạc nếu framework đã hỗ trợ.

## 11. Cache collection, pagination và search links

Collection representation thường thay đổi theo query parameter:

```http
GET /orders?page=0&size=20&sort=createdAt,desc
```

Các URI khác nhau tạo cache key khác nhau theo URI và query string. Tuy nhiên, cần chú ý:

- Trang đầu có thể stale sau khi tạo hoặc xóa item.
- Link `next` và `prev` có thể thay đổi khi số lượng item thay đổi.
- Search response có thể phụ thuộc query parameter và quyền truy cập.
- Link `self` có thể là URI template với các biến pagination.
- Một số proxy có cấu hình bỏ qua query string hoặc chuẩn hóa query parameter; cần kiểm tra cấu hình cache thực tế.

Với collection thay đổi thường xuyên, có thể đặt `max-age` ngắn hoặc yêu cầu revalidation. Sau thao tác ghi, ứng dụng có thể purge cache key của collection bị ảnh hưởng nếu dùng CDN hoặc reverse proxy có hỗ trợ invalidation.

Không nên chỉ evict cache của item vừa cập nhật rồi cho rằng collection tự mới. Hypermedia collection có thể chứa embedded item data, tổng số phần tử và navigation links; tất cả đều có thể đã thay đổi.

## 12. Kiểm thử Cache-Control và Vary bằng MockMvc

MockMvc có thể xác nhận response phát đúng cache header:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderCacheHeadersTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesCachePolicyAndVaryHeader() throws Exception {
        mockMvc.perform(get("/public/orders/{id}", "42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL,
                        containsString("public")
                ))
                .andExpect(header().string(
                        HttpHeaders.VARY,
                        containsString("Accept")
                ));
    }
}
```

Test slice thực tế cần mock service và import assembler/configuration mà controller sử dụng. Assertion chỉ kiểm tra những directive thuộc hợp đồng; không nên so sánh nguyên chuỗi `Cache-Control` nếu thứ tự directive không phải điều API cam kết.

Kiểm tra response cá nhân hóa không được lưu:

```java
@Test
void preventsStorageOfSensitiveRepresentation() throws Exception {
    mockMvc.perform(get("/orders/{id}", "42")
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL,
                    containsString("no-store")
            ));
}
```

Nếu chính sách chọn `private, no-cache`, hãy assert đúng các directive đó thay vì `no-store`. Test phải phản ánh quyết định bảo mật của API.

## 13. Kiểm thử ETag và conditional GET

Test đầu tiên lấy ETag từ response 200, sau đó gửi lại ETag trong `If-None-Match`:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

import org.springframework.test.web.servlet.MvcResult;

@Test
void returnsNotModifiedWhenEtagMatches() throws Exception {
    MvcResult firstResponse = mockMvc.perform(
                    get("/public/orders/{id}", "42")
                            .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(header().exists(HttpHeaders.ETAG))
            .andReturn();

    String etag = firstResponse.getResponse()
            .getHeader(HttpHeaders.ETAG);

    mockMvc.perform(get("/public/orders/{id}", "42")
                    .accept(MediaTypes.HAL_JSON)
                    .header(HttpHeaders.IF_NONE_MATCH, etag))
            .andExpect(status().isNotModified())
            .andExpect(header().string(HttpHeaders.ETAG, etag))
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL,
                    containsString("must-revalidate")
            ))
            .andExpect(header().string(
                    HttpHeaders.VARY,
                    containsString("Accept")
            ))
            .andExpect(content().string(""));
}
```

Kiểm tra validator cũ không khớp thì server trả representation mới:

```java
@Test
void returnsRepresentationWhenEtagDoesNotMatch() throws Exception {
    mockMvc.perform(get("/public/orders/{id}", "42")
                    .accept(MediaTypes.HAL_JSON)
                    .header(HttpHeaders.IF_NONE_MATCH, "\"old-version\""))
            .andExpect(status().isOk())
            .andExpect(header().exists(HttpHeaders.ETAG))
            .andExpect(jsonPath("$._links.self.href").exists());
}
```

Các test giả định controller dùng `WebRequest.checkNotModified(etag)` như ví dụ trước. Nếu dùng `ShallowEtagHeaderFilter`, hành vi ETag được tạo ở filter và test cần cấu hình filter trong test context.

Khi test 304, không chỉ kiểm tra status. Hãy xác nhận response không gửi body mới và validator vẫn được trả để cache đối chiếu.

## 14. Kiểm thử cache sau thay đổi trạng thái hoặc quyền

Một bài test quan trọng của API hypermedia là bảo đảm representation mới không giữ link đã hết hiệu lực.

Ví dụ:

1. Request đầu tiên với principal có quyền nhận link `approve`.
2. Thay đổi quyền hoặc trạng thái đơn hàng.
3. Gửi request mới với validator cũ.
4. Server phải trả representation mới hoặc yêu cầu revalidation, không trả 304 dựa trên validator không phản ánh link visibility.
5. Representation mới không còn link `approve`.

Có thể kiểm tra ở mức integration test:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .with(user("reviewer").authorities(
                new SimpleGrantedAuthority("ORDER_APPROVE")))
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.approve.href").exists());

revokeApprovalPermission("reviewer");

mockMvc.perform(get("/orders/{id}", orderId)
        .with(user("reviewer"))
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.approve").doesNotExist());
```

Đây là pseudocode kiểm thử; `revokeApprovalPermission(...)`, fixture user và security configuration phụ thuộc ứng dụng. Nếu representation cá nhân hóa dùng `no-store`, test không cần gửi validator để kiểm tra cache; vẫn cần xác nhận link bị ẩn sau khi quyền thay đổi.

Nếu ứng dụng dùng ETag cho response theo quyền, test phải chứng minh ETag thay đổi khi tập links thay đổi, kể cả khi entity version không đổi.

## 15. ShallowEtagHeaderFilter và giới hạn

Spring Framework cung cấp `ShallowEtagHeaderFilter` để tính ETag dựa trên nội dung response đã render. Filter có thể giúp thêm validator mà không cần tự tính hash trong controller.

Cách này có lợi khi representation nhỏ và có thể buffer trong bộ nhớ. Tuy nhiên:

- Filter phải đọc nội dung response để tính ETag, nên không tránh được chi phí tạo body ở server.
- Với response lớn, việc buffer có thể làm tăng bộ nhớ.
- Không phù hợp với response streaming hoặc nội dung được ghi theo luồng mà không buffer.
- Cần kiểm tra cách filter được đăng ký và thứ tự filter trong ứng dụng.
- ETag vẫn chỉ hữu ích nếu cache policy cho phép lưu và revalidate response.

Với representation lớn hoặc cần validator theo phiên bản domain, có thể tự tạo ETag từ version tổng hợp đã được thiết kế đúng. Dù chọn cách nào, test phải bảo đảm validator thay đổi khi nội dung hypermedia thay đổi.

## 16. Những lỗi thường gặp

**Dùng `no-cache` với ý nghĩa không lưu response.** `no-cache` cho phép lưu nhưng bắt buộc revalidate; dùng `no-store` khi không được lưu.

**Dùng `public` cho representation có link theo quyền.** Shared cache có thể làm lộ links hoặc dữ liệu của người dùng khác. Dùng `private` hoặc `no-store`.

**ETag chỉ dựa trên entity version.** Links hoặc affordances có thể đổi mà entity không đổi. Validator phải phản ánh toàn bộ representation variant.

**Quên `Vary: Accept`.** HAL và HAL-FORMS có thể bị cache nhầm cùng URI. Khai báo `Vary` khi media type response phụ thuộc `Accept`.

**Quên `Vary` cho header chọn version.** Cache có thể trả sai phiên bản. Thêm header version vào `Vary` khi cùng URI trả representation khác nhau.

**Cho rằng 304 có body mới.** 304 chỉ xác nhận representation đã lưu còn hợp lệ. Client tái sử dụng body cache.

**Chỉ evict item cache sau thao tác ghi.** Collection, search và pagination links có thể stale. Xác định các representation phụ thuộc cần revalidate hoặc purge.

**Dựa vào link đã cache để quyết định quyền.** Quyền có thể thay đổi sau khi response được tạo. Endpoint phải authorization lại mỗi request.

**Nhầm `@Cacheable` với HTTP cache.** Cache method không tự tạo cache header cho response. Kiểm thử riêng cả hai nếu ứng dụng dùng cả hai.

**Dùng ETag nhưng không kiểm thử If-None-Match.** Header validator có thể xuất hiện nhưng conditional request không được xử lý. Kiểm tra 200, 304 và body.

## 17. Nguyên tắc thiết kế

- Chọn `Cache-Control` theo độ nhạy và mức thay đổi của representation.
- Chỉ dùng `public` khi dữ liệu và links giống nhau cho mọi người dùng.
- Dùng `private` cho response chỉ dành cho private cache; dùng `no-store` khi không được lưu.
- Phân biệt `no-cache` (revalidate) và `no-store` (không lưu).
- Dùng ETag khi có thể tạo validator phản ánh toàn bộ representation, gồm links và affordances.
- Dùng `WebRequest.checkNotModified(...)` hoặc cơ chế phù hợp để xử lý conditional GET.
- Dùng `Vary` cho các request header thực sự làm thay đổi representation.
- Cập nhật hoặc revalidate collection và item sau thao tác ghi.
- Không dựa vào link đã cache để thực thi authorization.
- Phân biệt HTTP response caching với Spring Cache abstraction.
- Kiểm thử cache header, ETag, 304, stale validator và link visibility bằng MockMvc/integration test.

## Kết luận

Kiểm thử cache response bảo đảm representation hypermedia được lưu và tái sử dụng đúng chính sách. `Cache-Control` quyết định nơi lưu và freshness; ETag hỗ trợ revalidation; `Vary` phân biệt các representation được chọn theo request header. Với Spring HATEOAS, validator phải tính đến cả dữ liệu, embedded resources, links và affordances. Representation phụ thuộc quyền cần chính sách private hoặc no-store phù hợp, còn endpoint đích luôn phải kiểm tra authorization lại. Dùng MockMvc để xác nhận header cache, conditional GET, 304 và hành vi khi link thay đổi; đồng thời phân biệt rõ HTTP caching với `@Cacheable` phía server.

## Tài liệu tham khảo

- [Spring Framework Reference – HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html)
- [Spring Framework API – CacheControl](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/CacheControl.html)
- [Spring Framework API – WebRequest](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/context/request/WebRequest.html)
- [Spring Framework API – ShallowEtagHeaderFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ShallowEtagHeaderFilter.html)
- [Spring HATEOAS Reference – Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [RFC 9110 – HTTP Semantics, Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110.html#section-13)

