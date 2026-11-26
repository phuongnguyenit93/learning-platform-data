# Cache representation

## Mục tiêu

Một representation HATEOAS chứa dữ liệu, links và có thể cả embedded resources hoặc affordances. Khi client tải lại cùng một tài nguyên nhiều lần, HTTP caching giúp tránh truyền toàn bộ response nếu representation chưa thay đổi. Với Spring MVC và Spring HATEOAS, controller có thể công bố Cache-Control, ETag hoặc Last-Modified để browser và proxy lưu response, sau đó gửi conditional request khi cần kiểm tra dữ liệu mới.

Cache representation cần chú ý thêm đến hypermedia. Hai response có cùng dữ liệu đơn hàng nhưng khác links vẫn có thể là hai representation khác nhau. Links có thể phụ thuộc quyền, trạng thái nghiệp vụ, media type hoặc phiên bản API. Vì vậy, validator và cache policy phải phản ánh toàn bộ nội dung mà client thực sự nhận.

Sau bài học, bạn có thể:

- Phân biệt HTTP response caching với server-side method caching.
- Chọn Cache-Control phù hợp cho representation công khai và cá nhân hóa.
- Dùng ETag hoặc Last-Modified cho conditional GET.
- Hiểu phản hồi 304 Not Modified và vai trò của If-None-Match.
- Tạo validator bao quát cả dữ liệu lẫn hypermedia links.
- Dùng ShallowEtagHeaderFilter và hiểu chi phí của nó.
- Kiểm thử cache headers, ETag và conditional request bằng MockMvc.

## HTTP cache hoạt động thế nào?

HTTP cache lưu response để có thể tái sử dụng khi client gửi request tới cùng tài nguyên. Response header Cache-Control hướng dẫn cache có thể lưu, dùng lại trong bao lâu và khi nào phải xác thực lại với server.

Một luồng thường gặp:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring MVC API
    C->>S: GET /api/orders/42
    S-->>C: 200 + HAL JSON + ETag + Cache-Control
    Note over C: Lưu representation và ETag
    C->>S: GET /api/orders/42 + If-None-Match
    S->>S: So sánh validator hiện tại
    alt Representation không đổi
        S-->>C: 304 Not Modified
        Note over C: Dùng body đã lưu
    else Representation đã đổi
        S-->>C: 200 + HAL JSON mới + ETag mới
        Note over C: Thay representation đã lưu
    end
~~~

Response 304 không gửi lại body. Client dùng representation đã lưu và cập nhật metadata cache theo response mới. Nếu representation đã thay đổi, server trả 200 cùng body và validator mới.

HTTP caching thường có hai lợi ích:

- **Freshness:** client có thể dùng response còn trong thời gian max-age mà chưa cần gọi server.
- **Revalidation:** khi response hết freshness, client gửi validator để server xác nhận response có còn giống bản đã lưu hay không.

Một request không có body không đồng nghĩa server không phải làm việc. Với ETag tính từ dữ liệu domain, server có thể chỉ cần đọc version hoặc timestamp. Với ETag tính từ toàn bộ response, server có thể phải dựng representation trước khi so sánh.

## Cache-Control và phạm vi lưu trữ

Spring cung cấp lớp CacheControl để tạo Cache-Control header:

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.http.CacheControl;

CacheControl publicCache = CacheControl
        .maxAge(5, TimeUnit.MINUTES)
        .cachePublic();

CacheControl privateCache = CacheControl
        .maxAge(1, TimeUnit.MINUTES)
        .cachePrivate()
        .mustRevalidate();

CacheControl noStore = CacheControl.noStore();
CacheControl revalidateEveryTime = CacheControl.noCache();
~~~

Các directive thường dùng:

| Directive | Ý nghĩa |
|---|---|
| max-age=60 | Response còn fresh trong 60 giây; cache có thể dùng lại mà chưa cần revalidate. |
| public | Cho phép shared cache lưu response nếu các điều kiện HTTP khác cho phép. |
| private | Chỉ cache riêng của client được lưu response; shared cache không được lưu response đó. |
| no-store | Không lưu response trong cache. Dùng cho dữ liệu nhạy cảm hoặc response cá nhân hóa cần tránh lưu trữ. |
| no-cache | Có thể lưu response, nhưng phải revalidate trước khi dùng lại. Không có nghĩa là cấm lưu. |
| must-revalidate | Khi response đã stale, cache phải xác thực lại trước khi dùng. |

private không thay thế authorization và cũng không ngăn browser của người dùng hiện tại lưu response. Nếu response chứa dữ liệu nhạy cảm không nên tồn tại trên thiết bị sau request, dùng no-store.

Trong thời gian max-age còn hiệu lực, browser có thể dùng response đã lưu mà không hỏi server. Nếu cần áp dụng ngay việc thu hồi quyền hoặc thay đổi links theo principal, không dùng freshness lifetime dài; chọn TTL ngắn, no-cache để revalidate hoặc no-store theo mức độ nhạy cảm.

Không đặt public cho representation phụ thuộc người dùng, tenant hoặc quyền truy cập. Shared cache có thể trả nhầm representation của người này cho người khác nếu cache key và chính sách lưu trữ không phản ánh đúng biến thể response.

## Cache representation HATEOAS

Một HAL representation có thể chứa:

~~~json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/api/orders/order-42"
    },
    "cancel": {
      "href": "/api/orders/order-42/cancel"
    }
  }
}
~~~

Khi trạng thái đơn hàng đổi từ PENDING sang PAID, dữ liệu status thay đổi và link cancel có thể biến mất. Representation đã thay đổi dù URI self vẫn giữ nguyên.

Các yếu tố có thể làm representation thay đổi:

- Thuộc tính của tài nguyên và các embedded resources.
- Links được thêm hoặc bỏ theo trạng thái nghiệp vụ.
- Links hoặc affordances được thêm hoặc bỏ theo quyền của principal.
- Relation và URI thay đổi khi API được version hoặc route được triển khai lại.
- Media type hoặc profile khác nhau theo header Accept.
- Ngôn ngữ hoặc locale khác nhau theo header Accept-Language.
- Tenant hoặc feature flag làm thay đổi khả năng mà API công bố.

Do đó, không nên mặc định ETag của representation bằng version của một entity duy nhất. Validator phải thay đổi khi bất kỳ phần nào của representation được cache thay đổi.

Nếu mọi người dùng nhận cùng một representation và entity version được tăng mỗi khi dữ liệu hoặc links thay đổi, entity version có thể dùng làm ETag. Nếu links cá nhân hóa theo quyền, cần validator phản ánh cả biến thể quyền hoặc không cache response đó trong shared cache. Với dữ liệu nhạy cảm, lựa chọn đơn giản và an toàn thường là Cache-Control: no-store.

## Dùng ETag trong controller

ETag là validator định danh một phiên bản representation. Client gửi giá trị đã nhận trong header If-None-Match ở request sau.

Ví dụ controller trả EntityModel và dùng version của đơn hàng để tạo ETag:

~~~java
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.springframework.hateoas.EntityModel;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(
            OrderService orderService,
            OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/api/orders/{id}")
    ResponseEntity<EntityModel<OrderResponse>> findById(
            @PathVariable UUID id) {

        Order order = orderService.findById(id);
        EntityModel<OrderResponse> model = assembler.toModel(order);
        String etag = "order-" + order.id() + "-v" + order.version();

        return ResponseEntity.ok()
                .cacheControl(CacheControl.maxAge(1, TimeUnit.MINUTES)
                        .cachePrivate()
                        .mustRevalidate())
                .eTag(etag)
                .body(model);
    }
}
~~~

Spring MVC có thể so sánh ETag với If-None-Match và trả 304 Not Modified khi representation chưa thay đổi. Khi có thay đổi, response trả 200 cùng body và ETag mới. ResponseEntity.eTag(...) xử lý định dạng dấu ngoặc kép cho entity tag.

Ví dụ này chỉ đúng khi version của order thay đổi mỗi khi bất kỳ dữ liệu hoặc link nào trong representation thay đổi và mọi người nhận cùng một representation. Nếu assembler thêm link cancel theo quyền hoặc thêm link theo feature flag, chỉ version của order chưa đủ để đại diện toàn bộ response.

Trong trường hợp đó, hãy tính validator từ snapshot representation đầy đủ hoặc kết hợp các version đầu vào ảnh hưởng đến response. Không dùng ETag cũ nếu quyền hoặc links có thể thay đổi mà validator không đổi.

## ETag và Last-Modified

ETag và Last-Modified đều hỗ trợ conditional request:

| Validator | Request header | Ưu điểm | Giới hạn |
|---|---|---|---|
| ETag | If-None-Match | Có thể dựa trên version hoặc hash nội dung; phân biệt tốt hơn thay đổi nhỏ. | Cần tính validator nhất quán với representation. |
| Last-Modified | If-Modified-Since | Dễ dùng khi tài nguyên có thời điểm cập nhật đáng tin cậy. | Độ phân giải thời gian thường là giây; thay đổi nhiều lần trong một giây có thể khó phân biệt. |

Có thể dùng cả hai validator. Khi request có cả If-None-Match và If-Modified-Since, quy tắc HTTP ưu tiên xử lý ETag. Nếu chỉ dùng Last-Modified, đảm bảo timestamp phản ánh mọi thay đổi của representation, bao gồm links và embedded data.

Spring MVC cho phép đặt Last-Modified trên ResponseEntity:

~~~java
return ResponseEntity.ok()
        .lastModified(order.lastModifiedAt())
        .cacheControl(CacheControl.maxAge(30, TimeUnit.SECONDS))
        .body(model);
~~~

Giá trị lastModified cần là thời điểm representation được cập nhật, không nhất thiết là thời điểm một bảng database cụ thể được ghi. Nếu links thay đổi do quyền hoặc cấu hình ngoài entity, timestamp cần tính đến những thay đổi đó hoặc response phải dùng chính sách cache phù hợp hơn.

## Xử lý conditional request tường minh

Nếu muốn tự kiểm tra validator trước khi tạo representation, controller có thể dùng WebRequest.checkNotModified(...):

~~~java
import java.util.concurrent.TimeUnit;
import java.util.UUID;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.context.request.WebRequest;

@GetMapping("/api/orders/{id}")
ResponseEntity<EntityModel<OrderResponse>> findById(
        @PathVariable UUID id,
        WebRequest request) {

    OrderSnapshot snapshot = orderService.loadSnapshot(id);
    String etag = "\"order-" + id + "-v" + snapshot.version() + "\"";
    CacheControl cacheControl = CacheControl
            .maxAge(1, TimeUnit.MINUTES)
            .cachePrivate()
            .mustRevalidate();

    if (request.checkNotModified(etag)) {
        return null;
    }

    EntityModel<OrderResponse> model = assembler.toModel(snapshot);
    return ResponseEntity.ok()
            .eTag(etag)
            .cacheControl(cacheControl)
            .body(model);
}
~~~

Ví dụ giả định snapshot.version() đã phản ánh mọi yếu tố ảnh hưởng đến representation. checkNotModified so sánh validator với conditional request header và đánh dấu response 304 khi phù hợp. Khi đã trả 304, response không có body; client dùng representation đã lưu.

Khi method trả null trong nhánh này, WebRequest đã đánh dấu response là 304; Spring MVC không cần ghi thêm body. Có thể dùng cách tương tự cho controller trả view hoặc response body tùy cách xử lý return value của endpoint.

Kiểm tra validator trước khi dựng links có thể tiết kiệm công tạo model, nhưng chỉ an toàn khi có thể biết chắc representation không đổi từ snapshot/version đã đọc. Nếu link phụ thuộc quyền hoặc trạng thái chưa được tính trong validator, không được trả 304 chỉ dựa trên version của dữ liệu chính.

Với request thay đổi trạng thái, If-Match và checkNotModified có thể được dùng cho precondition. Nếu ETag không còn khớp, server có thể trả 412 Precondition Failed để ngăn ghi đè dữ liệu mới. Đây là cơ chế bảo vệ cập nhật đồng thời, khác với 304 của conditional GET.

## ShallowEtagHeaderFilter

Spring MVC có ShallowEtagHeaderFilter để tạo ETag từ nội dung response đã serialize. Filter giữ lại response body, tính hash rồi so sánh với If-None-Match ở request tiếp theo.

Filter hữu ích khi:

- Muốn thêm ETag cho nhiều endpoint mà không tự tính version từng entity.
- Validator cần phản ánh nội dung HAL sau khi Jackson đã serialize links và embedded resources.
- Response có cấu trúc phức tạp và khó tạo version tổng hợp ở controller.

Tuy nhiên, đây là shallow ETag: server vẫn phải chạy controller, lấy dữ liệu, dựng representation và serialize toàn bộ body trước khi so sánh hash. Filter tiết kiệm băng thông khi trả 304, nhưng không tiết kiệm chi phí xử lý và serialize response. Nó cũng không thay thế Cache-Control, không xử lý đầy đủ các precondition cho request ghi và cần chú ý bộ nhớ vì response body được giữ lại để tính hash.

Nếu ứng dụng có thể lấy version từ database hoặc snapshot một cách rẻ hơn, ETag ở controller thường hiệu quả hơn. Không bật filter toàn cục chỉ vì muốn có ETag; chọn phạm vi URL và loại response phù hợp.

## HTTP caching khác với @Cacheable

Spring Cache và HTTP caching giải quyết hai lớp khác nhau:

| Cơ chế | Cache cái gì? | Ai sử dụng? | Tác động tới HTTP response |
|---|---|---|---|
| @Cacheable | Kết quả method hoặc dữ liệu ứng dụng. | Server. | Không tự tạo Cache-Control, ETag hay 304. |
| HTTP Cache-Control | Response representation. | Browser, proxy, CDN hoặc HTTP client cache. | Quyết định response có thể được lưu và dùng lại. |
| ETag/Last-Modified | Validator của representation. | Client gửi conditional request; server xác nhận. | Có thể trả 304 thay vì body. |

Ví dụ server-side cache một snapshot theo tenant và order ID:

~~~java
import java.util.UUID;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    @Cacheable(
            cacheNames = "order-snapshots",
            key = "#tenantId + ':' + #orderId")
    OrderSnapshot loadSnapshot(UUID tenantId, UUID orderId) {
        return repository.findSnapshotByTenantIdAndOrderId(
                        tenantId,
                        orderId)
                .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

Key cần bao gồm tenant khi cùng một order ID có thể tồn tại trong các tenant khác nhau. Nếu kết quả method còn phụ thuộc người dùng, locale hoặc phạm vi quyền, cache key phải phản ánh các biến thể đó hoặc cache dữ liệu dùng chung ở tầng thấp hơn.

Với representation HATEOAS cá nhân hóa, thường nên cache dữ liệu/snapshot đã được phân quyền ở server rồi dựng links theo principal của request. Tránh cache nguyên EntityModel có cancel link của quản trị viên và trả lại cho người dùng chỉ có quyền đọc.

Khi dữ liệu thay đổi, dùng @CacheEvict hoặc cơ chế invalidation tương ứng để loại snapshot cũ. HTTP cache vẫn cần ETag/Cache-Control riêng; xóa server-side cache không tự xóa body đã lưu trong browser hoặc proxy.

## Vary và content negotiation

Nếu cùng URI có thể trả HAL JSON hoặc một media type khác tùy header Accept, cache phải phân biệt các biến thể đó. Response nên có Vary: Accept để cache biết representation phụ thuộc header này.

Tương tự, nếu response thay đổi theo Accept-Language hoặc Origin, cần khai báo header tương ứng trong Vary khi phù hợp với content negotiation và CORS của ứng dụng.

Với representation cá nhân hóa theo principal, tenant hoặc quyền, Vary đơn lẻ không phải giải pháp an toàn cho shared cache. Hãy dùng private hoặc no-store theo mức độ nhạy cảm và cấu hình cache. Không dùng public cho response khác nhau theo Authorization hoặc session.

Server vẫn phải xác thực và phân quyền request trước khi trả 304. Nếu quyền đã bị thu hồi, không được dùng một validator khớp để xác nhận response cũ cho người gọi hiện không còn quyền. Với dữ liệu nhạy cảm hoặc cần thu hồi quyền tức thì, no-store là lựa chọn an toàn hơn; private không phân vùng cache theo principal ứng dụng.

Ví dụ ResponseEntity công bố media type variant:

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;

return ResponseEntity.ok()
        .varyBy(HttpHeaders.ACCEPT)
        .cacheControl(CacheControl.maxAge(30, TimeUnit.SECONDS)
                .cachePrivate())
        .body(model);
~~~

Không thêm Vary một cách máy móc cho mọi header. Chỉ đưa vào những request header thực sự làm thay đổi representation. Nếu hệ thống có CORS, framework hoặc gateway đã thêm Vary: Origin, cần giữ lại các giá trị Vary hiện có thay vì ghi đè.

## Links có thể cũ dù dữ liệu chưa đổi

Giả sử dữ liệu đơn hàng không đổi trong 10 phút, nhưng trong thời gian đó API triển khai route mới hoặc quyền của người dùng bị thu hồi. Representation có thể đã cũ dù version của order vẫn giữ nguyên:

- Link cancel có thể cần biến mất khi quyền bị thu hồi.
- Link tới collection có thể đổi khi API chuyển phiên bản.
- Affordance có thể thay đổi khi trạng thái nghiệp vụ đổi.
- Profile hoặc relation có thể đổi khi hợp đồng API được cập nhật.

Vì vậy, TTL dài không phù hợp với mọi representation HATEOAS. Với links ít thay đổi và công khai, có thể dùng max-age dài hơn. Với links phụ thuộc quyền hoặc trạng thái, dùng TTL ngắn, no-cache để revalidate, hoặc no-store nếu response nhạy cảm.

Cache invalidation phải tính đến cả các thay đổi gián tiếp ảnh hưởng tới links. Nếu một đơn hàng có link tới khách hàng, việc khách hàng bị xóa hoặc quyền truy cập khách hàng thay đổi có thể làm representation của đơn hàng cần được tạo lại.

## Kiểm thử HTTP caching bằng MockMvc

Test đầu tiên xác nhận response HAL có Cache-Control và ETag:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(header().exists(HttpHeaders.ETAG))
        .andExpect(header().string(
                HttpHeaders.CACHE_CONTROL,
                containsString("private")));
~~~

Kiểm thử conditional GET bằng ETag đã nhận:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.HttpHeaders;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MvcResult;

MvcResult firstResponse = mockMvc.perform(
                get("/api/orders/{id}", orderId)
                        .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andReturn();

String etag = firstResponse.getResponse()
        .getHeader(HttpHeaders.ETAG);

mockMvc.perform(get("/api/orders/{id}", orderId)
                .header(HttpHeaders.IF_NONE_MATCH, etag)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isNotModified())
        .andExpect(content().string(""));
~~~

Ví dụ giả định endpoint đã tạo ETag ổn định và dữ liệu không thay đổi giữa hai request. Trong test đầy đủ, cần xác nhận service hoặc repository không bị gọi lại nếu controller có thể kiểm tra version trước khi dựng representation. Với ETag từ ShallowEtagHeaderFilter, controller vẫn có thể chạy và serialize body ở request thứ hai trước khi filter trả 304.

Nên có test khi dữ liệu thay đổi:

1. Gửi GET và lấy ETag thứ nhất.
2. Cập nhật order hoặc một yếu tố ảnh hưởng tới links.
3. Gửi GET với If-None-Match cũ.
4. Xác nhận server trả 200, body mới và ETag khác.

Kiểm thử thêm:

- Response cá nhân hóa có private hoặc no-store theo chính sách.
- Representation không bị shared cache dùng lại giữa hai principal.
- Vary có Accept khi content negotiation làm thay đổi body.
- ETag thay đổi khi link/affordance thay đổi, không chỉ khi field domain đổi.
- Response 304 không chứa body và vẫn giữ các cache headers cần thiết.
- no-cache cho phép lưu nhưng yêu cầu revalidation; no-store cấm lưu.

## Những lỗi thường gặp

- **Đồng nhất @Cacheable với HTTP cache:** @Cacheable chỉ cache kết quả method ở server; nó không tự tạo Cache-Control hoặc 304.
- **Chỉ tính ETag từ entity version:** links hoặc embedded resources có thể thay đổi độc lập; validator phải bao quát representation.
- **Dùng public cho response cá nhân hóa:** shared cache có thể làm lộ links hoặc dữ liệu theo quyền của người khác.
- **Hiểu no-cache là không lưu:** no-cache yêu cầu revalidate; no-store mới chỉ thị không lưu response.
- **Dùng TTL dài cho links phụ thuộc quyền:** quyền và trạng thái có thể đổi trước khi cache hết hạn.
- **Coi 304 là response rỗng hoàn toàn:** client cần body đã lưu; server vẫn phải xác nhận validator và trả metadata phù hợp.
- **Dùng ShallowEtagHeaderFilter để giảm CPU:** filter vẫn tạo toàn bộ response trước khi tính hash.
- **Quên Vary khi Accept thay đổi media type:** cache có thể dùng nhầm representation của media type khác.
- **Cho rằng Vary thay thế authorization:** response riêng tư cần private/no-store và endpoint vẫn phải kiểm tra quyền.
- **Không invalidation server-side cache sau update:** @Cacheable có thể tiếp tục trả snapshot cũ dù HTTP cache đã revalidate.
- **Bỏ qua links thay đổi do deploy hoặc feature flag:** ETag và TTL cần phản ánh các yếu tố làm thay đổi representation.

## Quy trình cache representation HATEOAS

1. Xác định representation có công khai, dùng chung hay cá nhân hóa theo principal/tenant.
2. Chọn Cache-Control: public/private cho response có thể lưu hoặc no-store cho dữ liệu nhạy cảm.
3. Chọn TTL phù hợp với tốc độ thay đổi của dữ liệu, links và affordances.
4. Tạo ETag hoặc Last-Modified phản ánh mọi yếu tố ảnh hưởng đến representation.
5. Dùng conditional GET để client revalidate bằng If-None-Match hoặc If-Modified-Since.
6. Dùng Vary khi Accept hoặc request headers khác làm thay đổi representation.
7. Tách server-side data cache khỏi HTTP response cache và bảo đảm cache key có tenant/security scope cần thiết.
8. Kiểm thử 200, 304, ETag mới sau update, cache headers và các biến thể theo quyền/media type.

Cache representation HATEOAS hiệu quả khi server có thể xác định chính xác response nào còn hợp lệ để tái sử dụng. Hãy coi links, embedded resources và affordances là một phần của representation được cache. Khi validator và cache policy phản ánh đầy đủ các yếu tố đó, client giảm được băng thông mà vẫn nhận đúng khả năng điều hướng hiện tại.

## Tài liệu tham khảo

- Spring Framework Reference Documentation, HTTP Caching: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html
- Spring Framework Reference Documentation, Shallow ETag Filter: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html#filters-shallow-etag
- Spring Framework API, CacheControl: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/CacheControl.html
- Spring Framework API, ResponseEntity: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html
- Spring Framework API, WebRequest: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/context/request/WebRequest.html
