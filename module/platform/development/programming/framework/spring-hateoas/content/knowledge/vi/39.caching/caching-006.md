# Link và freshness

Một API trả về collection đơn hàng có thể chứa link đến từng item, trang kế tiếp và các thao tác như hủy hoặc xác nhận đơn. Khi client cache response này, nó cache cả dữ liệu lẫn các link trong representation. Nếu trạng thái đơn hàng thay đổi hoặc endpoint được chuyển sang route mới, response cũ có thể vẫn chứa link không còn phù hợp.

Vì vậy, cần phân biệt **freshness của representation chứa link** với **freshness và khả năng truy cập của resource đích**. HTTP cache kiểm soát thời gian một representation có thể được tái sử dụng. Link trong representation không tự có thời hạn riêng và việc link còn xuất hiện không bảo đảm target vẫn tồn tại, còn hiệu lực hoặc được phép truy cập. Spring HATEOAS tạo các link trong representation; Spring MVC và HTTP caching headers quyết định client, browser hoặc proxy có thể tái sử dụng representation đó trong bao lâu.

## Freshness trong hypermedia API

Một response HAL có thể chứa:

- Dữ liệu của resource hiện tại.
- Link `self` đến resource hiện tại.
- Link đến collection, item liên quan hoặc tài liệu.
- Link hành động phụ thuộc trạng thái như `approve`, `cancel` hoặc `pay`.
- Embedded representation trong `_embedded`.

Tất cả những thành phần này thuộc cùng representation HTTP. Khi cache response, cache giữ nguyên body đã nhận, bao gồm các link và affordance. Nếu representation còn fresh, cache có thể trả lại body đó mà không hỏi origin server.

Ví dụ, client lấy đơn hàng khi trạng thái là `PENDING` và response có link `cancel`. Sau đó đơn hàng được thanh toán. Nếu response cũ vẫn còn fresh, client có thể nhìn thấy link `cancel` dù thao tác không còn hợp lệ. Server vẫn phải kiểm tra trạng thái khi nhận request, nhưng freshness ngắn hoặc revalidation giúp client sớm nhận representation và tập link mới.

```text
GET /api/orders/ord-1042
        |
        v
Representation tại thời điểm T1
status = PENDING
_links: self, cancel
        |
        v
HTTP cache lưu response
        |
        +---- đơn hàng chuyển sang PAID tại T2
        |
        v
Cache vẫn có thể trả representation T1 nếu còn fresh
        |
        v
Client thấy link cancel cũ
```

Freshness không phải thuộc tính của riêng `href`. Nó là chính sách tái sử dụng representation chứa `href` đó.

## Freshness của representation khác với freshness của target

Một collection response có thể chứa link đến item. Collection và item là hai URI khác nhau, thường có cache entry và validator riêng.

| Thành phần | Cache identity | Điều cần kiểm soát |
| --- | --- | --- |
| API root | URI root | Link đến các collection/capability có còn đúng không? |
| Collection | URI collection cùng query/filter/page | Danh sách item, item links và pagination links có còn mới không? |
| Item | URI `self` của item | Dữ liệu và action links có phản ánh trạng thái hiện tại không? |
| Action target | URI của thao tác | Target còn tồn tại và thao tác còn được phép không? |
| Profile/documentation | URI tài liệu | Nội dung giải thích relation hoặc schema có được cập nhật không? |

Nếu cache collection trong năm phút, điều đó không có nghĩa item link bên trong cũng có freshness năm phút theo cache policy của item. Cache entry của collection chứa một URI target; client có thể cần GET target, và response target sẽ có chính sách caching riêng.

Tương tự, việc item representation còn fresh không đảm bảo action target vẫn hợp lệ. Endpoint đích phải xác thực, phân quyền và kiểm tra trạng thái mới nhất khi nhận request.

## HTTP freshness lifetime

HTTP caching dùng response directives để chỉ định khoảng thời gian response có thể được xem là fresh. Các chỉ thị phổ biến:

| Directive/header | Ý nghĩa |
| --- | --- |
| `Cache-Control: max-age=60` | Response có freshness lifetime 60 giây tính theo HTTP age calculation. |
| `Cache-Control: s-maxage=30` | Freshness lifetime 30 giây dành cho shared cache; ưu tiên hơn `max-age` trong shared cache. |
| `Cache-Control: public` | Cho phép shared cache lưu response trong những điều kiện phù hợp. |
| `Cache-Control: private` | Response chỉ dành cho private cache, không được shared cache lưu. |
| `Cache-Control: no-cache` | Có thể lưu response nhưng phải revalidate trước khi tái sử dụng. |
| `Cache-Control: no-store` | Cache không được lưu response. |
| `Cache-Control: must-revalidate` | Khi response đã stale, cache phải revalidate trước khi dùng lại. |
| `Expires` | Ngày/giờ tuyệt đối mà response hết freshness theo HTTP semantics. |
| `Date` | Thời điểm tạo response được dùng trong tính toán age. |
| `Age` | Tuổi hiện tại của response khi được gửi từ cache trung gian. |

Ví dụ một API root công khai, ít thay đổi:

```http
HTTP/1.1 200 OK
Date: Thu, 26 Nov 2026 05:00:00 GMT
Cache-Control: public, max-age=300, s-maxage=60, must-revalidate
Vary: Accept
ETag: "api-root-r17"
Content-Type: application/hal+json
```

Browser/private cache có thể dùng response trong tối đa 300 giây; shared cache dùng `s-maxage=60`. Khi stale, cache phải xác minh lại với origin trước khi trả response theo directive `must-revalidate`.

`Age` và `Date` có ý nghĩa khi response đi qua nhiều cache. Client không nên hiểu `max-age=300` đơn giản là “bắt đầu đếm 300 giây từ lúc tôi vừa nhận response”; HTTP age calculation còn tính tuổi response đã trải qua cache trung gian.

Khi cùng một URI có thể trả nhiều biến thể, freshness được áp dụng cho từng cache variant. `max-age` thường được ưu tiên hơn `Expires` khi cả hai cùng có mặt; shared cache dùng `s-maxage` nếu được cung cấp.

## Phân biệt no-cache và no-store

Hai directive này thường bị nhầm:

- `no-cache`: cache được phép lưu representation nhưng phải xác minh với origin trước khi tái sử dụng.
- `no-store`: cache không được lưu representation.

Nếu response có link thay đổi theo trạng thái đơn hàng, `no-cache` có thể phù hợp: cache giữ body để dùng khi revalidation trả `304 Not Modified`, nhưng không được tự ý phục vụ body cũ khi chưa hỏi origin.

Nếu response chứa dữ liệu nhạy cảm, capability URL hoặc link phụ thuộc danh tính người dùng và không nên lưu ở bất kỳ cache nào, dùng `no-store`.

`no-cache` không có nghĩa “không cache”. `no-store` cũng không xóa các bản sao đã được lưu trước đó trong mọi hệ thống; khi phát hiện dữ liệu nhạy cảm từng bị cache, cần xử lý purge và retention theo chính sách vận hành.

## Validators: ETag và Last-Modified

Khi response stale, cache có thể hỏi origin xem representation đã thay đổi chưa. Validators giúp thực hiện revalidation mà không cần truyền lại toàn bộ body nếu không thay đổi.

### ETag

`ETag` là validator gắn với một representation. Ví dụ:

```http
HTTP/1.1 200 OK
ETag: "order-1042-repr-17"
Cache-Control: private, no-cache
Content-Type: application/hal+json
```

Khi cache có bản sao cũ, nó gửi validator:

```http
GET /api/orders/ord-1042 HTTP/1.1
If-None-Match: "order-1042-repr-17"
Accept: application/hal+json
```

Nếu representation không thay đổi, server có thể trả:

```http
HTTP/1.1 304 Not Modified
ETag: "order-1042-repr-17"
Cache-Control: private, no-cache
```

Cache giữ body đã lưu và cập nhật metadata theo response `304`. Nếu dữ liệu, embedded resource hoặc link đã thay đổi, server trả `200 OK` với representation và ETag mới.

### ETag phải phản ánh cả link

Với hypermedia, ETag không nên chỉ dựa trên version của entity nếu representation còn chứa dữ liệu khác. Các thay đổi sau có thể làm representation thay đổi dù row đơn hàng không đổi:

- Route collection được chuyển sang URI mới.
- Một link `cancel` được thêm hoặc gỡ do trạng thái thay đổi.
- Quyền của người dùng thay đổi làm tập action links khác đi.
- Link đến tài liệu/profile được cập nhật.
- Embedded projection hoặc page metadata thay đổi.
- CURIE hoặc cấu hình relation được thay đổi.

Nếu ETag chỉ dựa trên `order.version`, server có thể trả `304` trong khi body cache vẫn chứa link cũ. Validator cần nhận diện toàn bộ representation có thể quan sát được, bao gồm link và metadata. Với representation cá nhân hóa, ETag cũng cần được tính trong đúng phạm vi người dùng/tenant và response phải có cache policy phù hợp.

### Last-Modified

`Last-Modified` cung cấp timestamp cho lần thay đổi cuối cùng của representation:

```http
Last-Modified: Thu, 26 Nov 2026 04:58:00 GMT
```

Cache có thể gửi `If-Modified-Since` để hỏi origin. Cách này dễ dùng khi có một timestamp đáng tin cậy, nhưng HTTP date có độ phân giải theo giây và có thể bỏ sót nhiều thay đổi xảy ra trong cùng một giây. Với hypermedia, timestamp cũng phải phản ánh thay đổi của link map, policy và embedded data, không chỉ `updated_at` của entity.

Nếu có thể, ETag thường là validator linh hoạt hơn. Có thể gửi cả ETag và Last-Modified; khi nhận cả `If-None-Match` và `If-Modified-Since`, server/caching implementation áp dụng precedence theo HTTP semantics, trong đó `If-None-Match` được ưu tiên.

## Link thay đổi thì cache cần nhận biết thế nào?

Giả sử API root có relation `orders` trỏ đến `/api/v1/orders`. Sau khi chuyển route sang `/commerce/orders`, representation root đã thay đổi dù tên relation không đổi.

Để client nhận link mới, server cần ít nhất một trong các cơ chế:

1. Freshness lifetime ngắn để cache sớm hết hạn.
2. `no-cache` để cache revalidate mỗi lần trước khi tái sử dụng.
3. ETag/Last-Modified thay đổi khi link target thay đổi.
4. Invalidation/purge cache khi triển khai thay đổi link.
5. Giữ endpoint cũ hoạt động hoặc redirect trong giai đoạn migration để client dùng link cũ không bị lỗi đột ngột.

Không nên dựa vào việc client tự đoán route mới. Khi client đang dùng hypermedia, server cần cập nhật representation dẫn nhập hoặc link nguồn để công bố target hiện hành.

## Cache policy theo mức độ thay đổi của link

Không phải mọi representation đều cần cùng freshness lifetime. Chọn policy dựa trên tốc độ thay đổi, tác động khi link cũ được dùng và mức độ cá nhân hóa.

| Loại representation | Đặc điểm link | Policy gợi ý |
| --- | --- | --- |
| API root công khai | Link collection ít đổi, route có migration theo kế hoạch | `public` với `max-age` ngắn/vừa và ETag; purge khi đổi route. |
| Tài liệu/profile tĩnh | Link và nội dung ít thay đổi | `public` với freshness dài, ETag hoặc immutable URL khi version hóa nội dung. |
| Collection có filter/pagination | Link phụ thuộc query, page và dữ liệu hiện tại | Freshness ngắn, validator; cache key phải giữ query đầy đủ. |
| Item có action links | Link thay đổi theo trạng thái | `private, no-cache` hoặc private TTL rất ngắn kèm validator. |
| Representation theo quyền/tenant | Tập link khác nhau theo principal | `private` hoặc `no-store`; không dùng shared cache nếu chưa có thiết kế cách ly rõ ràng. |
| Link cấp capability/secret | `href` tự mang quyền truy cập | `no-store`, TTL của capability ngắn, redact log và có thể thu hồi. |

Đây là hướng dẫn thiết kế, không phải TTL cố định cho mọi API. Hãy đo độ trễ, tần suất thay đổi và hậu quả khi client sử dụng link cũ.

## HTTP cache khác với Spring Cache

HTTP cache và Spring Cache giải quyết hai lớp khác nhau:

| Cơ chế | Lưu gì? | Điều khiển bằng gì? |
| --- | --- | --- |
| HTTP cache ở browser/proxy/CDN | HTTP response representation, status và metadata như link HAL | `Cache-Control`, `ETag`, `Last-Modified`, `Vary`, conditional request. |
| Spring Cache (`@Cacheable`, `@CacheEvict`) | Kết quả method trong tiến trình hoặc cache provider ứng dụng | Cache name, key, TTL/eviction do cache provider và cấu hình ứng dụng. |

Đặt `Cache-Control: no-store` không tự xóa object đang nằm trong Redis hoặc cache được Spring Cache quản lý. Ngược lại, `@CacheEvict` không tự purge response đã lưu trong browser hoặc CDN.

Nếu cache domain object ở service layer rồi tạo `EntityModel` trong mỗi request, ứng dụng có thể xây link theo request context và quyền hiện tại. Nếu cache nguyên `EntityModel` hoặc HAL representation, hãy cẩn thận: `href` có thể chứa host/context path của request trước, action links có thể thuộc principal trước, và metadata có thể đã stale. Chỉ cache assembled representation khi cache key và invalidation bao phủ mọi yếu tố làm thay đổi representation, bao gồm origin, media type, locale, tenant và authorization context khi có liên quan.

## Spring MVC: đặt Cache-Control cho representation HATEOAS

Spring MVC cho phép đặt cache headers trên `ResponseEntity`. `CacheControl` giúp xây dựng directive mà không phải nối chuỗi header thủ công.

Ví dụ item đơn hàng có action links phụ thuộc trạng thái và quyền người dùng:

```java
import java.time.Duration;
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(
        path = "/api/orders/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
    )
    ResponseEntity<EntityModel<OrderView>> one(@PathVariable("id") UUID id) {
        EntityModel<OrderView> model = assembler.toModel(
            orderService.getRequired(id));

        return ResponseEntity.ok()
            .varyBy("Accept")
            .cacheControl(CacheControl.maxAge(Duration.ofSeconds(15))
                .cachePrivate()
                .mustRevalidate())
            .body(model);
    }
}
```

Ví dụ dùng TTL riêng tư 15 giây. Cache riêng của user có thể tái sử dụng representation trong khoảng fresh; shared cache không được lưu response `private`. Khi stale, `must-revalidate` yêu cầu xác minh lại trước khi sử dụng. Nếu action links thay đổi rất nhanh hoặc không muốn cache lưu representation, dùng `CacheControl.noStore()`.

Với root resource công khai và ít thay đổi, có thể chọn policy public:

```java
return ResponseEntity.ok()
    .varyBy("Accept")
    .cacheControl(CacheControl.maxAge(Duration.ofMinutes(2))
        .cachePublic())
    .body(rootModel);
```

Chỉ dùng `public` khi representation thực sự giống nhau và được phép chia sẻ giữa mọi người dùng. Nếu root có link phụ thuộc role hoặc tenant, không dùng shared public cache.

## Dùng ETag cho representation chứa link

Controller có thể trả ETag cùng response. Giá trị phải là validator của representation, không chỉ là ID hoặc version của entity:

```java
String representationTag = representationFingerprint.create(
    orderView,
    model.getLinks(),
    currentAuthorizationContext,
    representationProfile);

String etag = "\"" + representationTag + "\"";

return ResponseEntity.ok()
    .eTag(etag)
    .cacheControl(CacheControl.noCache().cachePrivate())
    .body(model);
```

`representationFingerprint` là thành phần ứng dụng cần triển khai. Nó phải tạo cùng một tag khi representation có thể quan sát không đổi và tag mới khi bất kỳ phần nào trong representation thay đổi, bao gồm link, embedded data, profile và các affordance. Ví dụ trên minh họa nơi gắn ETag; không nên dùng `model.getLinks().toString()` hoặc `entity.getVersion()` một cách máy móc làm fingerprint.

Nếu muốn tạo ETag từ body đã serialize, `ShallowEtagHeaderFilter` của Spring Framework có thể tính validator dựa trên response content. Cách này giúp kiểm tra thay đổi ở link và body, nhưng response vẫn phải được tạo trước khi filter tính ETag; nó chủ yếu tiết kiệm băng thông, không tránh chi phí truy vấn và render. Cần cân nhắc buffering, streaming và response lớn trước khi áp dụng.

## `Vary` và content negotiation

Một URI có thể trả HAL hoặc JSON khác tùy `Accept`. Nếu cache không phân biệt các request này, nó có thể trả HAL body cho client mong JSON hoặc ngược lại. Dùng `Vary` để chỉ ra request header ảnh hưởng đến representation:

```http
Vary: Accept
```

Nếu link title hoặc nội dung được dịch theo `Accept-Language`, response có thể cần:

```http
Vary: Accept, Accept-Language
```

Chỉ thêm header vào `Vary` khi nó thực sự ảnh hưởng đến response. `Vary` tạo các cache variants; thêm quá nhiều header làm giảm cache hit rate.

Đối với response cá nhân hóa theo người dùng, `Vary: Authorization` không phải biện pháp duy nhất để bảo vệ dữ liệu. Dùng `private` hoặc `no-store` phù hợp và không cho shared cache lưu response có action links hoặc dữ liệu riêng tư.

## Shared cache và response phụ thuộc quyền

Một response HATEOAS có thể khác nhau theo principal:

- Người quản trị thấy link `approve`.
- Người chỉ đọc không thấy link `approve`.
- User của tenant A chỉ thấy collection và target thuộc tenant A.
- User tenant B nhận tập link khác.

Nếu shared cache lưu response của user A rồi trả cho user B, nó có thể lộ link hoặc metadata ngoài quyền. Nguy cơ không biến mất chỉ vì endpoint đích có authorization; chính sự hiện diện của relation, URI hoặc title cũng có thể là thông tin nhạy cảm.

Với response phụ thuộc quyền, mặc định nên dùng `private` hoặc `no-store`. Nếu thực sự cần shared caching, phải thiết kế cache key theo danh tính/tenant và policy authorization, bảo đảm purge đúng phạm vi, đồng thời đánh giá rủi ro side channel. Không giả định cache proxy sẽ tự hiểu Spring Security principal.

## Invalidation khi mutation làm thay đổi link

Một thao tác `POST`, `PUT`, `PATCH` hoặc `DELETE` có thể làm thay đổi:

- Representation item.
- Collection chứa item.
- Pagination metadata và `next`/`prev` links.
- API root hoặc dashboard link tùy trạng thái.
- Action links như `approve`, `cancel` hoặc `refund`.

HTTP cache có quy tắc invalidation đối với URI của request method không an toàn, nhưng không tự biết mọi URI liên quan trong domain. Ví dụ cập nhật một đơn hàng không có nghĩa mọi cache của collection `/api/orders`, dashboard hoặc search result đều được invalidated tự động.

Các lựa chọn:

1. TTL ngắn cho collection và representation có link biến động.
2. Conditional GET với ETag để phát hiện representation đã đổi.
3. Purge cache/CDN cho các URI liên quan sau mutation.
4. Dùng event-driven invalidation khi hệ thống có cache infrastructure hỗ trợ.
5. Giữ các URI cũ hoạt động trong thời gian chuyển đổi nếu link đã được cache ở client.

Phải xác định rõ cache nào chịu trách nhiệm invalidation: browser, reverse proxy, CDN hay application cache. Xóa entry trong Spring Cache không tự động purge browser cache hoặc CDN.

## Stale links và khả năng chịu lỗi

Cache có thể giữ response stale khi origin không truy cập được nếu policy cho phép. Các extension như `stale-while-revalidate` cho phép cache tạm trả response cũ trong lúc revalidate; `stale-if-error` cho phép dùng response stale khi origin gặp lỗi trong khoảng thời gian được chỉ định.

Điều này hữu ích với nội dung công khai ít nhạy cảm, nhưng cần thận trọng với action links:

- Link `self` hoặc tài liệu có thể vẫn hữu ích dù hơi cũ.
- Link collection/search có thể dẫn đến kết quả không mới nhất.
- Link `approve`, `cancel`, `pay` có thể đã không còn hợp lệ.
- Link capability có thể hết hạn hoặc bị thu hồi.

Không dùng stale serving rộng rãi cho representation chứa capability hoặc action links nhạy cảm. Nếu cho phép stale cho dữ liệu đọc, endpoint target vẫn phải kiểm tra trạng thái và quyền; client cần xử lý `404`, `403`, `409` hoặc lỗi nghiệp vụ khi follow link cũ.

## Link cũ trong giai đoạn thay đổi route

Nếu API đổi target từ `/api/v1/orders` sang `/api/v2/orders`, cache có thể tiếp tục trả representation chứa URI v1 cho đến khi hết freshness hoặc được purge. Có thể giảm tác động bằng cách:

- Dùng freshness ngắn cho API root và collection link map.
- Revalidate root bằng ETag khi stale.
- Duy trì endpoint v1 trong giai đoạn deprecation.
- Trả redirect có kiểm soát từ URI cũ sang URI mới nếu semantics và method cho phép.
- Công bố relation mới hoặc link successor khi semantics thật sự thay đổi.

Không redirect mù quáng các request có body hoặc action semantics khác nhau. Chuyển route không được làm thay đổi ý nghĩa thao tác mà client đang gọi.

## Kiểm thử freshness và link validators

Kiểm thử caching cần xác minh header và hành vi revalidation, không chỉ body HAL.

### Kiểm tra Cache-Control và Vary

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(header().string("Cache-Control",
        org.hamcrest.Matchers.containsString("private")))
    .andExpect(header().string("Vary",
        org.hamcrest.Matchers.containsString("Accept")));
```

Nếu response được thiết kế `no-store`, kiểm tra directive đó thay cho `private`. Nếu Spring MVC hoặc proxy gộp nhiều giá trị `Vary`, kiểm tra theo cách header thực tế được serialize.

### Kiểm tra ETag

```java
MvcResult first = mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(header().exists("ETag"))
    .andReturn();

String etag = first.getResponse().getHeader("ETag");

mockMvc.perform(get("/api/orders/{id}", orderId)
        .header("If-None-Match", etag)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isNotModified());
```

Test giả định representation không thay đổi giữa hai request và controller/filter hỗ trợ conditional GET. Nếu link hoặc body thay đổi giữa hai request, response phải là `200 OK` với ETag mới, không phải `304`.

### Kiểm tra ETag thay đổi khi link thay đổi

Tạo hai trạng thái test có cùng entity data nhưng khác tập link, chẳng hạn quyền user khác nhau hoặc link action được bật/tắt. Xác nhận representation body và ETag thay đổi. Test này bắt lỗi dùng entity version làm ETag trong khi link map đã đổi.

### Kiểm tra revalidation sau mutation

1. GET item và lưu ETag cùng `cancel` link.
2. Thực hiện mutation làm trạng thái item chuyển sang `CANCELLED` hoặc `PAID`.
3. GET lại với `If-None-Match` cũ.
4. Xác nhận server trả `200 OK`, ETag mới và action link không còn khả dụng.

Nếu mutation làm thay đổi collection, hãy kiểm tra collection cache/validator riêng. Không giả định validator item tự invalidates collection.

### Kiểm tra cache variants

Gửi hai request cùng URI nhưng `Accept` khác nhau. Xác nhận response có media type đúng và `Vary: Accept` khi representation phụ thuộc header đó. Nếu title/link được localization, lặp lại với `Accept-Language`.

### Kiểm tra stale link và authorization

Giữ một link action từ response cũ, thay đổi quyền hoặc trạng thái resource, rồi gọi target trực tiếp. Server phải từ chối hoặc trả lỗi nghiệp vụ phù hợp. Test này chứng minh endpoint không tin link đã được client cache.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ cache payload và quên link cũng nằm trong representation | Client có thể dùng link cũ dù data đã stale. | Chọn freshness/validator cho toàn bộ representation. |
| Cho rằng target có cùng TTL với source representation | Cache source và target có vòng đời độc lập. | Revalidate từng URI theo cache policy riêng. |
| ETag chỉ dựa trên entity version | Link hoặc affordance đổi nhưng server trả `304`. | Tính validator từ representation hoàn chỉnh, gồm links. |
| Dùng `no-cache` với nghĩa không lưu | Cache vẫn được lưu và phải revalidate trước khi dùng. | Dùng `no-store` nếu thực sự không cho lưu. |
| Cache public response có action links cá nhân hóa | Lộ capability hoặc link giữa user/tenant. | Dùng `private`/`no-store` và tách cache theo phạm vi an toàn. |
| Không gửi `Vary: Accept` khi media type khác nhau | Cache có thể trả sai representation cho client. | Khai báo các request header ảnh hưởng đến response. |
| Tin rằng mutation tự invalidates mọi collection liên quan | Cache collection/search/root có thể giữ link hoặc data cũ. | TTL, validator và purge các URI liên quan. |
| Cho phép stale action links quá lâu | Client nhìn thấy thao tác đã hết hiệu lực. | Revalidate nhanh; endpoint luôn kiểm tra trạng thái và quyền. |
| Chỉ xóa Spring Cache khi cần purge CDN | Browser/proxy/CDN vẫn giữ bản sao. | Xác định và purge đúng từng cache layer. |
| Đổi route rồi tắt endpoint cũ ngay | Client đang dùng link đã cache bị lỗi. | Có deprecation window, redirect phù hợp và hỗ trợ URI cũ có thời hạn. |

## Ghi nhớ

- Freshness áp dụng cho toàn bộ HTTP representation, bao gồm `_links`, `_embedded`, metadata và affordances.
- Freshness của source representation độc lập với cache policy của target URI.
- `max-age`, `s-maxage`, `Expires`, `Date` và `Age` quyết định freshness theo HTTP age calculation.
- `no-cache` cho phép lưu nhưng bắt buộc revalidate; `no-store` cấm lưu response.
- Dùng ETag/Last-Modified để revalidate; validator phải thay đổi khi link hoặc embedded data thay đổi.
- ETag chỉ dựa trên entity version có thể sai nếu route, permission hoặc action links thay đổi.
- Chọn TTL theo mức biến động và hậu quả khi client dùng link stale.
- Dùng `private`/`no-store` cho response cá nhân hóa hoặc chứa capability; `Vary` cho content negotiation.
- Mutation không tự invalidates mọi URI liên quan; cần TTL, validator hoặc purge cache đúng layer.
- Endpoint đích luôn kiểm tra authorization và trạng thái mới nhất, kể cả khi client follow link cũ.
- Kiểm thử Cache-Control, Vary, ETag, 304/200, link changes và stale-link authorization.

## Tài liệu tham khảo

- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 5861 – HTTP Cache-Control Extensions for Stale Content](https://www.rfc-editor.org/rfc/rfc5861.html)
- [Spring Framework – CacheControl API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/CacheControl.html)
- [Spring Framework – ShallowEtagHeaderFilter API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ShallowEtagHeaderFilter.html)
- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
