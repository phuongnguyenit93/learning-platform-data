# Cache link

Một representation hypermedia không chỉ chứa dữ liệu. Nó còn có các link trong `_links`, resource nhúng trong `_embedded`, metadata phân trang và đôi khi affordance mô tả thao tác tiếp theo. Khi cache một response Spring HATEOAS, toàn bộ representation này được cache cùng nhau. Vì vậy, cache link cần xem xét cả độ mới của dữ liệu lẫn độ mới của khả năng điều hướng mà server công bố.

Ví dụ, response đơn hàng có thể chứa link `cancel` khi đơn còn ở trạng thái PENDING. Sau khi đơn chuyển sang SHIPPED, link đó không còn phù hợp. Nếu browser hoặc proxy tiếp tục dùng response cũ, client có thể vẫn hiển thị nút Hủy. Endpoint vẫn phải kiểm tra quyền và trạng thái khi request đến, nhưng cache hợp lý sẽ giúp client sớm nhận được representation mới.

Spring Framework hỗ trợ HTTP caching bằng `Cache-Control`, `ETag` và `Last-Modified`. Spring HATEOAS tạo representation có link; chính sách cache của HTTP áp dụng cho toàn bộ response chứa representation đó.

## Cache link có nghĩa là gì?

Giả sử server trả HAL:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "customer": {
      "href": "https://api.example.com/customers/7"
    },
    "cancel": {
      "href": "https://api.example.com/orders/42/cancellation"
    }
  },
  "id": "42",
  "status": "PENDING"
}
~~~

Khi response được cache, cache giữ cả:

- Dữ liệu đơn hàng như `id` và `status`.
- Relation và href trong `_links`.
- Resource nhúng trong `_embedded`, nếu có.
- Metadata phân trang hoặc URI template, nếu response có chúng.
- Các thuộc tính affordance được serialize bởi media type, nếu có.

Cache không lưu riêng từng relation theo một chính sách độc lập. `Cache-Control` là chính sách của HTTP response; các link bên trong body đi cùng vòng đời của representation. Khi client theo một href để tải resource đích, response của resource đích có chính sách cache riêng.

## Phân biệt HTTP response cache và Spring Cache

Hai cơ chế thường được gọi chung là cache nhưng giải quyết các tầng khác nhau:

| Cơ chế | Cache cái gì? | Công cụ Spring thường dùng |
| --- | --- | --- |
| HTTP response cache | Response đã serialize, gồm body HAL và các HTTP header | `Cache-Control`, `ETag`, `Last-Modified`, `ResponseEntity` |
| Application cache | Kết quả xử lý trong JVM hoặc cache backend như Redis/Caffeine | `@Cacheable`, `@CachePut`, `@CacheEvict`, `CacheManager` |

HTTP cache giúp browser, client HTTP hoặc proxy tái sử dụng response. Application cache giúp server tránh truy vấn hoặc tính toán lại dữ liệu khi xử lý request.

Không nên nhầm `@Cacheable` với `Cache-Control`. Đặt `@Cacheable` trên service không tự thêm HTTP header; thêm `Cache-Control` vào `ResponseEntity` cũng không tự cache kết quả service trong Redis.

## Cache-Control điều khiển vòng đời response

Header `Cache-Control` cho browser và intermediary biết response được lưu ở đâu và có thể được dùng lại trong bao lâu. Các directive thường gặp:

| Directive | Ý nghĩa |
| --- | --- |
| `max-age=60` | Response còn fresh trong 60 giây kể từ thời điểm được tạo theo quy tắc HTTP |
| `private` | Shared cache không được lưu response; private cache như browser có thể lưu |
| `public` | Cho phép shared cache lưu response ngay cả trong một số trường hợp thường không cache được |
| `no-cache` | Có thể lưu response nhưng phải revalidate trước khi dùng lại |
| `no-store` | Cache không được lưu response |
| `must-revalidate` | Khi response đã stale, cache phải xác thực lại trước khi dùng |
| `s-maxage=30` | Đặt freshness lifetime riêng cho shared cache |
| `no-transform` | Intermediary không được biến đổi representation |

Hai directive dễ bị nhầm:

- `no-cache` không có nghĩa là không lưu. Cache có thể giữ response, nhưng phải hỏi lại server trước khi sử dụng.
- `no-store` yêu cầu cache không lưu response vào cache.

Nếu representation có link phụ thuộc người dùng hoặc quyền truy cập, hãy chọn chính sách cẩn thận. `private` ngăn shared cache lưu response nhưng vẫn cho phép browser cache. Nó không phải cơ chế phân vùng cache theo tài khoản đăng nhập trong cùng browser.

Với representation chứa thông tin nhạy cảm hoặc link thể hiện quyền động, `no-store` thường là lựa chọn an toàn. Nếu muốn browser lưu nhưng phải xác thực lại mỗi lần dùng, có thể dùng `private, no-cache` cùng validator phù hợp.

## Chọn chính sách theo loại representation

Không phải mọi response HATEOAS đều có cùng yêu cầu cache:

| Loại representation | Chính sách thường phù hợp | Lý do |
| --- | --- | --- |
| Catalog công khai, link giống nhau với mọi client | `public, max-age=...` | Có thể dùng lại ở browser và CDN |
| Metadata API ít thay đổi, không chứa dữ liệu theo người dùng | `public` hoặc `max-age` ngắn | Giảm request lặp |
| Đơn hàng có dữ liệu riêng theo người dùng | `private, no-cache` hoặc `no-store` | Tránh shared cache và xác thực lại dữ liệu |
| Link action thay đổi theo scope hoặc trạng thái | `no-store`, hoặc `private, no-cache` với validator bao phủ toàn representation | Không dùng lại link đã cũ |
| Dữ liệu rất nhạy cảm | `no-store` | Không lưu response trong HTTP cache |
| Trang collection biến động thường xuyên | `max-age` ngắn và/hoặc `ETag` | Giảm tải nhưng vẫn cập nhật được link phân trang |

Không đặt `public` chỉ vì endpoint là GET hoặc response dùng HAL. `public` cho phép shared cache lưu response, kể cả một số response được yêu cầu kèm Authorization mà nếu không có directive rõ ràng thì shared cache không được tái sử dụng.

## Thêm Cache-Control vào ResponseEntity

Spring Framework cung cấp `CacheControl` builder. Có thể đặt chính sách cache trực tiếp khi trả representation:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogController {

    private final CatalogService catalogService;
    private final ProductModelAssembler assembler;

    CatalogController(
            CatalogService catalogService,
            ProductModelAssembler assembler) {
        this.catalogService = catalogService;
        this.assembler = assembler;
    }

    @GetMapping(
        value = "/catalog/products/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
    )
    ResponseEntity<EntityModel<ProductRepresentation>> product(
            @PathVariable UUID id) {

        Product product = catalogService.findPublicProduct(id);
        EntityModel<ProductRepresentation> model = assembler.toModel(product);

        return ResponseEntity.ok()
            .cacheControl(
                CacheControl.maxAge(Duration.ofMinutes(2)).cachePublic())
            .varyBy(HttpHeaders.ACCEPT)
            .body(model);
    }
}
~~~

Ví dụ giả định representation sản phẩm và các link của nó giống nhau với mọi người dùng trong suốt hai phút. `varyBy(HttpHeaders.ACCEPT)` giúp cache phân biệt response theo media type client yêu cầu nếu endpoint có thể trả nhiều định dạng.

Chỉ dùng `cachePublic()` khi representation không chứa dữ liệu riêng, link theo quyền hoặc URL được tạo theo danh tính người gọi. Nếu response có nội dung khác nhau theo người dùng, hãy chọn chính sách private hoặc no-store.

## Cache private cho representation theo người dùng

Đơn hàng thường có link phụ thuộc người dùng hiện tại. Ví dụ nhân viên hỗ trợ có quyền hủy đơn, trong khi khách hàng chỉ được đọc đơn. Có thể đặt:

~~~java
return ResponseEntity.ok()
    .cacheControl(
        CacheControl.noCache().cachePrivate())
    .varyBy(HttpHeaders.ACCEPT)
    .body(model);
~~~

`private` ngăn shared cache lưu response. `noCache()` cho phép private cache giữ response nhưng bắt buộc revalidate trước khi dùng lại. Khi người dùng đăng nhập bằng tài khoản khác trong cùng browser, server cần tạo lại representation và xác nhận ETag tương ứng với tập link hiện tại.

Nếu không muốn response nhạy cảm được lưu trong browser cache, dùng:

~~~java
return ResponseEntity.ok()
    .cacheControl(CacheControl.noStore())
    .varyBy(HttpHeaders.ACCEPT)
    .body(model);
~~~

`noStore()` áp dụng cho cả private và shared cache. Directive này giảm việc lưu response trong cache, nhưng không thay thế mã hóa đường truyền, kiểm soát truy cập, bảo vệ thiết bị hoặc chính sách lưu trữ của ứng dụng.

## Vì sao ETag của representation phải bao gồm cả link?

`ETag` là validator nhận diện một phiên bản representation. Client gửi `If-None-Match` với ETag đã nhận; server có thể trả `304 Not Modified` nếu representation vẫn tương đương và client được phép dùng bản đã lưu.

Với response hypermedia, ETag cần thay đổi khi bất kỳ phần nào thuộc representation thay đổi, bao gồm:

- Trường dữ liệu của entity.
- Relation hoặc href.
- Link next/prev khi trang collection thay đổi.
- Resource nhúng.
- Metadata hoặc affordance được serialize.
- Link hiển thị theo scope, role, tenant hoặc trạng thái nghiệp vụ.

Nếu chỉ dùng `order.version` làm ETag trong khi link `cancel` thay đổi theo quyền người dùng, validator có thể nói response chưa đổi dù body HAL đã đổi. Khi đó client nhận `304` và tiếp tục dùng link cũ.

Một ETag dựa trên version entity chỉ an toàn khi version đó thay đổi mỗi lần mọi thành phần của representation thay đổi. Nếu link phụ thuộc policy động, hãy đưa phiên bản policy hoặc biến thể representation vào validator, hoặc tính ETag từ nội dung representation đã serialize.

## Dùng ETag theo version của resource

Với representation công khai có link ổn định, version của resource hoặc catalog có thể làm validator hiệu quả. Spring MVC hỗ trợ `ETag` trên `ResponseEntity` và xử lý conditional GET:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PublicProductController {

    private final ProductService productService;
    private final ProductModelAssembler assembler;

    PublicProductController(
            ProductService productService,
            ProductModelAssembler assembler) {
        this.productService = productService;
        this.assembler = assembler;
    }

    @GetMapping(
        value = "/public/products/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
    )
    ResponseEntity<EntityModel<ProductRepresentation>> one(
            @PathVariable UUID id) {

        Product product = productService.findPublicProduct(id);
        EntityModel<ProductRepresentation> model = assembler.toModel(product);

        String etag = "\"" + product.getRepresentationVersion() + "\"";

        return ResponseEntity.ok()
            .cacheControl(
                CacheControl.maxAge(Duration.ofMinutes(2)).cachePublic())
            .eTag(etag)
            .varyBy(HttpHeaders.ACCEPT)
            .body(model);
    }
}
~~~

Ví dụ giả định `representationVersion` tăng mỗi khi dữ liệu sản phẩm hoặc bất kỳ link công khai nào của nó thay đổi. Khi client gửi lại ETag hiện tại trong `If-None-Match`, Spring MVC có thể trả `304 Not Modified` mà không gửi body. Nếu version không bao phủ thay đổi link, hãy dùng một validator khác.

ETag ở đây được đặt trong dấu nháy kép theo cú pháp HTTP. Với representation có thể thay đổi theo ngôn ngữ, media type hoặc người dùng, ETag phải nhận diện đúng biến thể đang trả về.

## Dùng ShallowEtagHeaderFilter cho body HAL đã serialize

Nếu representation có nhiều link được tính toán theo request, việc tự tạo ETag từ version entity dễ bỏ sót thành phần. Với Spring MVC, `ShallowEtagHeaderFilter` có thể tạo ETag từ nội dung response sau khi converter đã serialize HAL.

Ví dụ đăng ký filter trong Spring Boot:

~~~java
import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.filter.ShallowEtagHeaderFilter;

@Configuration
class EtagFilterConfiguration {

    @Bean
    FilterRegistrationBean<ShallowEtagHeaderFilter> orderEtagFilter() {
        FilterRegistrationBean<ShallowEtagHeaderFilter> registration =
            new FilterRegistrationBean<>(new ShallowEtagHeaderFilter());

        registration.addUrlPatterns("/orders/*");
        registration.setDispatcherTypes(
            DispatcherType.REQUEST,
            DispatcherType.ASYNC
        );

        return registration;
    }
}
~~~

Filter đọc body đã serialize và tạo ETag từ nội dung đó. Vì body bao gồm `_links`, hai người dùng nhận các link khác nhau sẽ có ETag khác nhau. Kết hợp với `Cache-Control: private, no-cache`, browser có thể lưu response nhưng phải revalidate trước khi sử dụng lại.

Shallow ETag tiết kiệm băng thông, không tiết kiệm chi phí tạo representation hoặc serialize JSON vì server vẫn phải dựng toàn bộ body để tính hash. Nếu có thể tạo validator từ version dữ liệu và policy một cách chính xác trước khi serialize, kiểm tra ở controller thường tiết kiệm CPU hơn.

Không dùng filter này cho response streaming hoặc response rất lớn cần gửi từng phần mà không buffer toàn bộ nội dung. Filter cần giữ nội dung response để tính ETag.

## Conditional GET và response 304

Luồng conditional GET điển hình:

1. Client gửi GET tới URI resource.
2. Server trả `200 OK`, body HAL, `ETag` và `Cache-Control`.
3. Client lưu representation cùng ETag.
4. Khi cần tải lại, client gửi `If-None-Match` với ETag đã lưu.
5. Server so sánh validator với representation hiện tại.
6. Nếu không đổi, server trả `304 Not Modified` không có body; client tiếp tục dùng body đã cache.
7. Nếu thay đổi, server trả `200 OK` với representation mới và ETag mới.

Ví dụ request:

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
Accept: application/hal+json
If-None-Match: "order-42-v7"
~~~

Response khi representation chưa đổi:

~~~http
HTTP/1.1 304 Not Modified
ETag: "order-42-v7"
Cache-Control: private, no-cache
Vary: Accept
~~~

Response `304` không chứa body. Client dùng representation đã lưu trước đó. Nếu server quên đổi ETag khi relation `cancel` biến mất hoặc href thay đổi, client có thể tiếp tục dùng link cũ.

## Last-Modified và If-Modified-Since

Spring MVC cũng hỗ trợ validator theo thời điểm sửa đổi:

~~~java
return ResponseEntity.ok()
    .lastModified(product.getUpdatedAt().toEpochMilli())
    .cacheControl(CacheControl.maxAge(Duration.ofMinutes(1)))
    .body(model);
~~~

Client có thể gửi `If-Modified-Since` ở request kế tiếp. Validator thời gian phù hợp khi thời điểm cập nhật đại diện chính xác cho mọi thay đổi trong representation.

Với hypermedia, cần cập nhật `updatedAt` hoặc timestamp tương ứng khi link thay đổi. Nếu quyền hoặc link được tính theo người dùng nhưng entity không đổi, `Last-Modified` của entity không đủ để xác định representation. ETag thường phù hợp hơn cho trường hợp này.

Timestamp HTTP có độ chính xác theo giây. Nhiều thay đổi xảy ra trong cùng một giây có thể khó phân biệt bằng Last-Modified; ETag tránh phụ thuộc vào độ phân giải thời gian.

## Vary khi response có nhiều biến thể

Cache thường dùng URI và method để xác định response có thể tái sử dụng. Header `Vary` bổ sung các request header cần được xét khi chọn biến thể.

Với API HATEOAS, các header có thể làm representation thay đổi:

| Request header | Khi nào cần đưa vào Vary? |
| --- | --- |
| `Accept` | Server trả HAL, HAL-FORMS hoặc media type khác tùy content negotiation |
| `Accept-Language` | `title`, nhãn affordance hoặc nội dung được bản địa hóa |
| `Accept-Encoding` | Hạ tầng trả các biến thể mã hóa nội dung và cần cache phân biệt |
| `Origin` | Response CORS thay đổi theo origin được cho phép |

Ví dụ:

~~~java
return ResponseEntity.ok()
    .cacheControl(CacheControl.maxAge(Duration.ofMinutes(1)).cachePublic())
    .varyBy(
        HttpHeaders.ACCEPT,
        HttpHeaders.ACCEPT_LANGUAGE
    )
    .body(model);
~~~

Nếu server tạo title link bằng ngôn ngữ người dùng, thiếu `Vary: Accept-Language` có thể khiến cache trả title tiếng Việt cho request tiếng Anh hoặc ngược lại.

Không thêm mọi header vào `Vary` theo thói quen. Mỗi header tạo thêm biến thể cache và có thể làm giảm tỷ lệ cache hit. Chỉ đưa vào những header thực sự ảnh hưởng representation.

## Vary không thay thế authorization

Nếu body thay đổi theo token, tenant hoặc cookie đăng nhập, không thể chỉ thêm `Vary` rồi cho phép shared cache lưu tùy ý.

- `Vary: Authorization` giúp phân biệt request theo giá trị header Authorization khi cache hỗ trợ và sử dụng Vary.
- Nhưng Vary không cấp quyền truy cập và không tự cho phép shared cache lưu response chứa Authorization.
- `private` ngăn shared cache lưu response.
- `no-store` yêu cầu cả private và shared cache không lưu response.

Với response có dữ liệu riêng theo người dùng hoặc link thể hiện quyền, hãy ưu tiên `private` hoặc `no-store` theo mức nhạy cảm. Chỉ dùng `public` hay `s-maxage` khi đã chứng minh representation an toàn để chia sẻ giữa các người dùng.

## Link stale và trạng thái resource thay đổi

Link trong representation là thông tin điều hướng tại thời điểm server tạo response. Nó không phải giấy phép bất biến để thực hiện hành động trong tương lai.

Ví dụ:

- Response lúc 10:00 có link `cancel` vì đơn đang PENDING.
- Một tác vụ khác chuyển đơn sang SHIPPED lúc 10:01.
- Browser vẫn giữ response đến 10:02.
- Người dùng bấm link `cancel` lúc 10:01:30.

Endpoint cancellation phải kiểm tra lại trạng thái và quyền. Nó có thể trả `409 Conflict` hoặc lỗi nghiệp vụ phù hợp. Client sau đó nên tải lại resource để nhận representation và links mới.

Cache policy chỉ giảm khoảng thời gian client nhìn thấy link cũ; nó không thể loại bỏ hoàn toàn race condition giữa lúc hiển thị link và lúc gửi request.

Với action nhạy cảm hoặc thay đổi trạng thái nhanh, dùng `no-store` hoặc `private, no-cache` và validator phản ánh link. Endpoint vẫn phải xác thực quyền tại thời điểm thực thi.

## Link phân trang cũng có thể stale

Một collection response có thể chứa:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders?page=1&size=20"
    },
    "prev": {
      "href": "/orders?page=0&size=20"
    },
    "next": {
      "href": "/orders?page=2&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 95,
    "totalPages": 5,
    "number": 1
  }
}
~~~

Nếu có đơn hàng mới được chèn hoặc dữ liệu bị xóa, link next và metadata có thể thay đổi. Cache một trang quá lâu có thể khiến client điều hướng theo phân trang cũ.

Đối với collection biến động:

- Dùng freshness lifetime ngắn.
- Dùng ETag bao gồm dữ liệu trang, page metadata và navigation links.
- Cân nhắc cursor pagination nếu offset dễ bị dịch chuyển khi dữ liệu thay đổi.
- Xử lý cursor hoặc page không còn hợp lệ bằng response lỗi có thể hiểu được.
- Sau khi nhận lỗi từ link cũ, client có thể quay lại collection entry point và khám phá lại.

Cache response của trang đầu không tự cache các trang tiếp theo. Mỗi href được gọi là một request riêng và response tương ứng có cache policy riêng.

## Thay đổi resource và invalidation

HTTP cache có quy tắc invalidation khi nhận một số request thay đổi trạng thái như POST, PUT hoặc DELETE. Tuy nhiên, việc cập nhật một resource không tự động xóa mọi response khác có chứa link hoặc dữ liệu liên quan tới resource đó.

Theo RFC 9111, khi cache nhận response không phải lỗi cho một unsafe method, nó phải invalidate URI đích của request. Cache có thể invalidate thêm URI trong header Location hoặc Content-Location nếu cùng origin. Quy tắc này không tự khám phá tất cả href nằm trong HAL body, không xóa mọi collection/search response liên quan và không tác động tới cache khác không đi qua request đó.

Ví dụ cập nhật `/orders/42` có thể làm thay đổi:

- Representation item `/orders/42`.
- Collection `/orders`.
- Kết quả search `/orders/search/by-status`.
- Dashboard chứa số lượng đơn hàng.
- Resource khách hàng có embedded orders.

Cache HTTP không nhất thiết biết tất cả URI liên quan. Có thể cần:

- TTL ngắn cho collection và search result.
- ETag để client revalidate.
- CDN purge hoặc surrogate key theo nhóm resource.
- Event-driven invalidation trong application cache.
- Cache key có version hoặc namespace để thay thế nhanh một nhóm dữ liệu.

Không giả định `Cache-Control: no-cache` tự xóa bản cũ ngay khi dữ liệu thay đổi. Nó yêu cầu revalidate trước khi tái sử dụng; server vẫn cần trả validator và representation mới đúng.

## Application cache: cache dữ liệu, tạo link theo request

Spring Cache có thể cache dữ liệu truy vấn để giảm tải database. Với representation HATEOAS có link theo quyền, cách an toàn thường là cache DTO/domain snapshot và tạo link trong mỗi request:

Để kích hoạt annotation cache, đăng ký @EnableCaching trong cấu hình ứng dụng:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
class ApplicationCacheConfiguration {
}
~~~

`@EnableCaching` bật cơ chế intercept các annotation cache; ứng dụng vẫn cần một `CacheManager` và cache provider phù hợp, ví dụ Caffeine hoặc Redis. Spring Boot có thể auto-configure khi dependency cache tương ứng được thêm vào, hoặc ứng dụng có thể khai báo `CacheManager` bean riêng.

~~~java
import java.util.UUID;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    private final OrderRepository orderRepository;

    OrderQueryService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Cacheable(
        cacheNames = "order-snapshots",
        key = "#p0.toString() + ':' + #p1.toString()"
    )
    OrderSnapshot findSnapshot(UUID tenantId, UUID orderId) {
        return orderRepository.findSnapshotByTenantIdAndId(
            tenantId, orderId);
    }
}
~~~

Cache key chứa tenant ID để không dùng chung dữ liệu giữa các tenant. Biểu thức #p0 và #p1 tham chiếu hai tham số đầu tiên, nên không phụ thuộc việc compiler giữ tên tham số Java. Trong request, assembler vẫn nhận Authentication hiện tại và tạo link phù hợp với quyền:

~~~java
OrderSnapshot snapshot =
    orderQueryService.findSnapshot(currentTenantId, orderId);

EntityModel<OrderRepresentation> model =
    orderModelAssembler.toModel(snapshot, authentication);
~~~

`OrderSnapshot` là DTO chỉ chứa dữ liệu cần đọc; nó không giữ link được tạo từ request trước. Cách này tránh việc một representation có link `cancel` của người dùng A bị trả cho người dùng B.

Nếu quyết định cache trực tiếp representation, cache key phải bao gồm mọi yếu tố làm representation khác nhau, chẳng hạn tenant, locale, phiên bản policy và nhóm quyền. Đây là thiết kế phức tạp; cache dữ liệu thuần rồi tạo link theo request thường dễ kiểm soát hơn.

## Evict application cache khi cập nhật

Khi đơn hàng thay đổi, cần cập nhật hoặc loại bỏ snapshot trong application cache:

~~~java
import java.util.UUID;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderCommandService {

    private final OrderRepository orderRepository;

    OrderCommandService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    @CacheEvict(
        cacheNames = "order-snapshots",
        key = "#p0.toString() + ':' + #p1.toString()"
    )
    void updateStatus(UUID tenantId, UUID orderId, OrderStatus status) {
        Order order = orderRepository.findByIdAndTenantId(orderId, tenantId)
            .orElseThrow();

        order.changeStatus(status);
    }
}
~~~

`@CacheEvict` loại bỏ entry trong Spring Cache sau khi method được gọi theo cấu hình cache advice. Với hệ thống transaction và cache phân tán, cần chọn thứ tự commit/evict phù hợp để tránh cache bị làm mới từ dữ liệu chưa commit. Có thể dùng event sau commit hoặc cơ chế outbox khi cần đồng bộ invalidation đáng tin cậy.

Evict application cache không tự purge browser cache hoặc CDN. Hai tầng cache cần chiến lược invalidation riêng.

## Không cache link action như dữ liệu bất biến

Relation có thể ổn định trong thời gian dài, nhưng việc một relation có xuất hiện trong representation hay không có thể thay đổi theo:

- Trạng thái domain.
- Scope hoặc role của principal.
- Tenant và quyền sở hữu resource.
- Thời gian hiệu lực của nghiệp vụ.
- Tính sẵn sàng của dịch vụ phụ thuộc.
- Feature flag hoặc phiên bản API.

Ví dụ relation `approve` có thể tồn tại trong representation khi đơn chờ duyệt và biến mất sau khi duyệt. Href có thể vẫn trỏ tới cùng URI, nhưng khả năng thực hiện đã thay đổi.

Đừng đặt TTL dài cho response chứa affordance động nếu server không có validator bao phủ các điều kiện đó. Với quyền động, hãy tạo link theo Authentication hiện tại và chọn cache policy phù hợp với mức độ nhạy cảm.

## Cache và HAL-FORMS affordance

HAL-FORMS có thể mô tả template cho thao tác, method, content type và các property đầu vào. Những metadata này cũng nằm trong representation và chịu cùng chính sách cache HTTP.

Nếu form `cancel` chỉ xuất hiện khi đơn đang PENDING, cache response cũ có thể tiếp tục hiển thị template đó sau khi đơn chuyển trạng thái. Server vẫn phải kiểm tra lại điều kiện khi nhận POST.

Nếu affordance chứa field phụ thuộc quyền hoặc trạng thái, validator phải phản ánh thay đổi đó. Với form chứa dữ liệu nhạy cảm hoặc token tạm thời, tránh cache response lâu hoặc dùng `no-store`.

## Kiểm thử Cache-Control và ETag bằng MockMvc

Một test cho endpoint công khai có thể xác nhận header và conditional GET:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MvcResult;

@Test
void returnsCacheHeadersAndSupportsConditionalGet() throws Exception {
    MvcResult firstResponse = mockMvc.perform(
            get("/public/products/{id}", PRODUCT_ID)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(header().string(
            HttpHeaders.CACHE_CONTROL,
            containsString("public")))
        .andExpect(header().string(
            HttpHeaders.VARY,
            containsString(HttpHeaders.ACCEPT)))
        .andExpect(header().exists(HttpHeaders.ETAG))
        .andReturn();

    String etag = firstResponse.getResponse()
        .getHeader(HttpHeaders.ETAG);

    mockMvc.perform(
            get("/public/products/{id}", PRODUCT_ID)
                .accept(MediaTypes.HAL_JSON)
                .header(HttpHeaders.IF_NONE_MATCH, etag))
        .andExpect(status().isNotModified());
}
~~~

Test giả định ETag được tạo từ version representation và Spring MVC xử lý conditional GET. Nếu dùng `ShallowEtagHeaderFilter`, hãy bảo đảm filter được đăng ký trong test context và response không mang `no-store`, vì filter không tính ETag cho response bị cấm lưu.

## Kiểm thử link và ETag thay đổi cùng representation

Với link phụ thuộc trạng thái, cần xác nhận ETag thay đổi khi link biến mất. Nếu dùng `ShallowEtagHeaderFilter`, hash được tính trên body HAL đã serialize:

~~~java
@Test
void changesEtagWhenAvailableActionsChange() throws Exception {
    MvcResult pending = mockMvc.perform(
            get("/orders/{id}", ORDER_ID)
                .with(readAndCancelScopes())
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.cancel").exists())
        .andReturn();

    String pendingEtag = pending.getResponse()
        .getHeader(HttpHeaders.ETAG);

    orderTestFixture.markAsShipped(ORDER_ID);

    MvcResult shipped = mockMvc.perform(
            get("/orders/{id}", ORDER_ID)
                .with(readAndCancelScopes())
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.cancel").doesNotExist())
        .andReturn();

    String shippedEtag = shipped.getResponse()
        .getHeader(HttpHeaders.ETAG);

    assertThat(shippedEtag).isNotEqualTo(pendingEtag);
}
~~~

`readAndCancelScopes()` và `orderTestFixture` là helper của test suite. Test phải thực hiện request thứ hai sau khi dữ liệu được cập nhật và transaction đã commit. Nếu ETag không đổi dù body link đã thay đổi, cache có thể trả representation cũ khi client gửi `If-None-Match`.

Nếu response dùng `no-store`, Shallow ETag filter mặc định không tạo ETag. Trong trường hợp đó, test tập trung xác nhận `Cache-Control: no-store` và link thay đổi theo trạng thái.

## Kiểm thử response cá nhân hóa không bị cache dùng chung

Với response theo người dùng, test cần xác nhận chính sách cache và link:

~~~java
@Test
void marksPersonalizedOrderRepresentationAsPrivateAndNoCache()
        throws Exception {

    mockMvc.perform(
            get("/orders/{id}", ORDER_ID)
                .with(readOnlyPrincipal())
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(header().string(
            HttpHeaders.CACHE_CONTROL,
            allOf(
                containsString("private"),
                containsString("no-cache"))))
        .andExpect(jsonPath("$._links.cancel").doesNotExist());
}
~~~

Test cần xác nhận người dùng có quyền hủy nhận representation có link, còn người dùng chỉ có quyền đọc thì không có. Không chỉ kiểm tra header; cần kiểm tra body để phát hiện link bị lộ do application cache dùng sai key.

## Những lỗi thường gặp

- **Cache representation có link theo user bằng key chung:** một người có thể nhận link được tạo theo quyền của người khác.
- **Dùng `public` cho response có Authorization:** shared cache có thể lưu nội dung cá nhân nếu directive cho phép.
- **Cho rằng `private` là phân vùng theo tài khoản:** private chỉ ngăn shared cache, không bảo đảm browser cache tách các lần đăng nhập.
- **Nhầm `no-cache` với `no-store`:** no-cache vẫn cho phép lưu và yêu cầu revalidation.
- **ETag chỉ dựa vào entity version:** relation hoặc href thay đổi nhưng ETag không đổi.
- **Cache link action quá lâu:** client nhìn thấy affordance đã hết hiệu lực.
- **Thiếu Vary:** cache trả HAL thay cho HAL-FORMS hoặc nhãn ngôn ngữ sai.
- **Cho rằng Vary là authorization:** Vary không kiểm tra quyền và không tự cho phép shared caching.
- **Quên collection/search cache:** update item có thể làm representation liên quan trở nên stale.
- **Dùng ShallowEtagHeaderFilter cho streaming:** filter cần buffer body và chỉ tiết kiệm băng thông.
- **Chỉ evict Spring Cache:** browser/CDN vẫn có thể giữ response cũ.
- **Dùng link để quyết định quyền cuối cùng:** endpoint phải kiểm tra lại scope, tenant và trạng thái khi nhận request.

## Checklist thiết kế cache link

| Câu hỏi | Quyết định cần có |
| --- | --- |
| Representation có giống nhau với mọi người dùng? | Nếu không, tránh shared cache và xem xét `private` hoặc `no-store` |
| Link có phụ thuộc quyền hoặc trạng thái không? | TTL ngắn, revalidation hoặc no-store |
| ETag có bao gồm link và embedded resource không? | Đảm bảo validator đổi khi bất kỳ phần body nào thay đổi |
| Có nhiều media type hoặc ngôn ngữ không? | Đặt `Vary` cho request header ảnh hưởng representation |
| Collection có biến động thường xuyên không? | TTL ngắn, ETag và chiến lược pagination phù hợp |
| Update resource ảnh hưởng những URI nào? | Lập kế hoạch invalidation cho item, collection, search và dashboard |
| Có dùng `@Cacheable` không? | Cache DTO/data theo tenant; tạo link theo request |
| Action có thể hết hiệu lực sau khi link được phát không? | Kiểm tra lại authorization và business state tại endpoint |

Cache link trong Spring HATEOAS là cache của representation chứa hypermedia. Hãy chọn `Cache-Control` theo mức độ công khai và độ biến động của representation, dùng `ETag` hoặc `Last-Modified` để revalidate, và bảo đảm validator phản ánh cả link chứ không chỉ dữ liệu entity. Với link cá nhân hóa, cache dữ liệu thuần ở application layer rồi tạo link theo request thường dễ kiểm soát hơn. Dù response còn fresh hay đã stale, endpoint vẫn phải kiểm tra quyền và trạng thái nghiệp vụ khi client thực hiện hành động.

## Tài liệu tham khảo

- [Spring Framework – HTTP Caching in Spring MVC](https://docs.spring.io/spring/reference/web/webmvc/mvc-caching.html)
- [Spring Framework API – CacheControl](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/CacheControl.html)
- [Spring Framework – Shallow ETag Filter](https://docs.spring.io/spring/reference/7.1/web/webmvc/filters.html)
- [Spring Framework – Declarative Annotation-based Caching](https://docs.spring.io/spring/reference/integration/cache/annotations.html)
- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
