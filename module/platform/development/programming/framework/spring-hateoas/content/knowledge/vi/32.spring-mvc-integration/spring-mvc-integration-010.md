# Cấu hình MVC liên quan

Spring HATEOAS tạo representation model và link, còn Spring MVC tiếp nhận HTTP request, chọn controller, xử lý request context và serialize response. Vì vậy, một API có link đúng trong Java object vẫn có thể trả JSON sai định dạng hoặc URI sai host nếu lớp MVC chưa được cấu hình phù hợp.

Khi tích hợp Spring HATEOAS với Spring MVC, cần hiểu bốn nhóm cấu hình: bật hỗ trợ hypermedia, cấu hình message converter và content negotiation, tạo link dựa trên request hiện tại, và xử lý thông tin proxy khi ứng dụng chạy sau load balancer hoặc reverse proxy. Cấu hình đúng giúp `EntityModel`, `CollectionModel` và `PagedModel` được serialize theo media type đã chọn, đồng thời tạo link có host, scheme và context path mà client bên ngoài thực sự truy cập.

## Vai trò của Spring MVC trong một API HATEOAS

Một request đi qua các thành phần chính sau:

```text
HTTP request
    |
    v
Servlet filters
    |
    v
DispatcherServlet
    |
    v
Controller mapping + argument binding
    |
    v
Controller / service / assembler
    |
    v
RepresentationModel (EntityModel, CollectionModel, ...)
    |
    v
HttpMessageConverter + Jackson hypermedia module
    |
    v
HAL / HAL-FORMS response
```

Các thành phần MVC liên quan có trách nhiệm khác nhau:

| Thành phần | Vai trò trong tích hợp HATEOAS |
| --- | --- |
| `DispatcherServlet` | Điều phối request đến controller và xử lý response. |
| `@RequestMapping`, `@GetMapping`, `@PathVariable`, `@RequestParam` | Khai báo URI, method và cách bind dữ liệu request. |
| `WebMvcLinkBuilder` | Đọc mapping controller và request context để xây URI cho link. |
| `HttpMessageConverter` | Chọn cách đọc/ghi body theo media type. |
| Jackson hypermedia module | Serialize representation model thành cấu trúc HAL hoặc định dạng hypermedia được bật. |
| Servlet filter | Xử lý thông tin request trước khi controller và link builder sử dụng. |

Hãy kiểm tra toàn bộ đường đi từ request đến JSON cuối cùng. Việc assembler tạo đúng `Link` chưa chứng minh message converter sẽ serialize link và embedded resource theo HAL.

## Cấu hình với Spring Boot

Trong ứng dụng Spring Boot dùng Spring MVC, cách phổ biến là thêm starter HATEOAS tương thích với phiên bản Boot đang sử dụng. Boot cung cấp auto-configuration cho Spring HATEOAS, đăng ký các bean cần thiết như link discoverer và mapper được cấu hình để serialize representation model.

Với cấu hình Boot thông thường, không cần tự thêm `@EnableHypermediaSupport`. Boot cũng cấu hình mặc định để request chấp nhận `application/json` có thể nhận HAL JSON. Nếu muốn yêu cầu client gửi rõ `Accept: application/hal+json`, có thể tắt hành vi mặc định này:

```yaml
spring:
  hateoas:
    use-hal-as-default-json-media-type: false
```

Sau khi tắt, ứng dụng cần cấu hình hypermedia media type phù hợp để endpoint trả đúng định dạng mà client yêu cầu. Hãy kiểm thử cả trường hợp `Accept: application/hal+json` và `Accept: application/json` vì hành vi content negotiation ảnh hưởng trực tiếp đến hợp đồng API.

### Không bật lại cấu hình thủ công một cách không cần thiết

Spring Boot auto-configuration đã chuẩn bị mapper và các thành phần hỗ trợ hypermedia. Nếu thêm `@EnableHypermediaSupport` để tự điều khiển cấu hình, Boot chuyển quyền cấu hình cho annotation này và một số tùy biến `JsonMapper` mà Boot cung cấp sẽ không còn được áp dụng như trước.

Vì vậy, trước khi thêm annotation, hãy xác định rõ lý do cần tự cấu hình, ví dụ ứng dụng không dùng Boot auto-configuration hoặc cần chọn web stack/media type cụ thể. Không bật đồng thời nhiều cấu hình chỉ để “chắc chắn HAL hoạt động”, vì có thể tạo converter hoặc mapper trùng lặp.

## Cấu hình thủ công với Spring MVC

Trong ứng dụng Spring Framework không dùng Boot auto-configuration, có thể bật Spring MVC và hypermedia support bằng Java configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;
import org.springframework.hateoas.support.WebStack;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
@EnableHypermediaSupport(
    type = HypermediaType.HAL,
    stacks = WebStack.WEBMVC
)
class WebConfiguration {
}
```

`@EnableWebMvc` bật hạ tầng Spring MVC trong ứng dụng Java configuration thuần. `@EnableHypermediaSupport` đăng ký hạ tầng cần thiết để các representation model được serialize theo HAL. `stacks = WebStack.WEBMVC` giới hạn cấu hình cho Servlet MVC.

Nếu dùng nhiều định dạng hypermedia, chọn các `HypermediaType` mà phiên bản Spring HATEOAS hỗ trợ. Không giả định tên enum hoặc danh sách media type giống nhau giữa mọi phiên bản; hãy kiểm tra API tương ứng với dependency của dự án.

### Khi classpath có cả Spring MVC và WebFlux

Một ứng dụng MVC có thể dùng `WebClient` của WebFlux để gọi dịch vụ khác. Khi đó, việc có WebFlux trên classpath không có nghĩa controller server đang chạy bằng WebFlux. Nếu bật `@EnableHypermediaSupport`, chỉ rõ `WebStack.WEBMVC` khi muốn cấu hình hypermedia cho Servlet MVC.

`spring-boot-starter-hateoas` dành cho Spring MVC. Ứng dụng server chạy WebFlux cần cấu hình dependency và link builder tương ứng với WebFlux; không ghép hai stack một cách tùy tiện. `WebMvcLinkBuilder` dành cho MVC, còn WebFlux có `WebFluxLinkBuilder`.

## Content negotiation và media type

Spring MVC chọn representation dựa trên request, đặc biệt là header `Accept`, và các media type mà endpoint/converter hỗ trợ.

Ví dụ client yêu cầu HAL:

```http
GET /api/orders/ord-1042 HTTP/1.1
Accept: application/hal+json
```

Response có thể chứa `_links` và `_embedded`:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "id": "ord-1042",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/ord-1042"
    }
  }
}
```

Nếu endpoint cần giới hạn rõ định dạng, có thể khai báo `produces`:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping(
        path = "/api/orders/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
    )
    EntityModel<OrderView> one(@PathVariable UUID id) {
        return orderAssembler.toModel(orderService.getRequired(id));
    }
}
```

Ví dụ giả định controller đã inject `orderAssembler` và `orderService`. Khi khai báo `produces`, client cần gửi `Accept` tương thích; nếu API muốn hỗ trợ nhiều representation, hãy cấu hình và kiểm thử danh sách media type tương ứng.

### Phân biệt application/json và application/hal+json

`application/json` chỉ xác định JSON nói chung. `application/hal+json` xác định cấu trúc HAL với quy ước cho link và embedded resource. Một JSON object có trường tên `_links` chưa tự động trở thành HAL hợp lệ nếu cấu trúc và media type không khớp.

Trong cấu hình Spring Boot mặc định, `application/json` có thể được ánh xạ đến HAL JSON. Nếu tắt hành vi đó, hãy bảo đảm client yêu cầu media type HAL rõ ràng. Tránh để một endpoint trả HAL cho client yêu cầu JSON thuần mà không có quy ước tương thích được công bố.

## Message converter và Jackson

Spring MVC dùng `HttpMessageConverter` để chuyển Java object thành response body. Với HAL, converter phải sử dụng Jackson module và cấu hình hypermedia phù hợp để serialize `EntityModel`, `CollectionModel`, `PagedModel` và các link.

Trong cấu hình Boot, hãy để auto-configuration quản lý mapper khi có thể. Nếu cần tùy biến Jackson, dùng cơ chế builder/customizer mà phiên bản Boot hỗ trợ để giữ các module Spring HATEOAS đã đăng ký.

Không nên tạo một `new ObjectMapper()` độc lập rồi dùng nó để serialize `EntityModel` trong controller hoặc service:

```java
// Không nên dùng mapper độc lập như thế này cho HAL:
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(entityModel);
```

Mapper mới không tự có các module và cấu hình hypermedia mà Spring MVC đã chuẩn bị. Kết quả có thể khác response do `HttpMessageConverter` tạo ra hoặc làm mất cấu trúc HAL mong đợi.

Nếu phải đăng ký converter tùy chỉnh, hãy bảo đảm converter đó vẫn dùng mapper có đầy đủ module Spring HATEOAS và không chiếm ưu tiên trước converter HAL theo cách làm hỏng content negotiation. Chỉ thêm converter sau khi đã xác định converter mặc định không đáp ứng một yêu cầu cụ thể.

## Mapping controller ảnh hưởng đến link

`WebMvcLinkBuilder` dựa vào mapping Spring MVC để tạo URI. Hãy khai báo mapping rõ ràng và dùng annotation tường minh cho path/query parameter:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable("id") UUID id) {
        return orderAssembler.toModel(orderService.getRequired(id));
    }
}
```

Assembler có thể tạo self link từ mapping method:

```java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(methodOn(OrderController.class).one(order.getId()))
    .withSelfRel();
```

`methodOn(...)` tạo proxy để ghi nhận lời gọi method và tham số cần cho mapping. Nó không thực thi controller method hoặc service. `@PathVariable` cung cấp giá trị để tạo path segment; các query parameter được xử lý theo metadata của mapping và quy tắc URI template.

Đặt tên path variable tường minh giúp mapping ổn định khi refactor tên tham số Java. Tương tự, dùng `@RequestParam(name = "status")` cho query parameter công khai. Không hard-code cùng một route trong controller, assembler và service vì một lần đổi mapping có thể làm link bị lệch.

## Base URI và request context

`WebMvcLinkBuilder` sử dụng `ServletUriComponentsBuilder` để lấy thông tin URI cơ sở từ request hiện tại, sau đó ghép mapping controller. Base URI có thể bao gồm:

- Scheme: `http` hoặc `https`.
- Host: tên miền mà request đang sử dụng.
- Port: cổng công khai.
- Context path hoặc prefix của ứng dụng.
- Servlet path và mapping controller.

Ví dụ ứng dụng chạy nội bộ tại `http://localhost:8080` nhưng client bên ngoài truy cập qua `https://api.example.com/shop`. Nếu MVC chỉ nhìn thấy request nội bộ, link được tạo có thể trỏ nhầm về `http://localhost:8080/api/orders/...`. Khi xử lý forwarded headers đúng cách, link có thể dùng địa chỉ công khai `https://api.example.com/shop/api/orders/...`.

Trong code controller đang xử lý request, ưu tiên `WebMvcLinkBuilder` thay vì tự ghép scheme, host, port hoặc context path. Nếu tạo link ngoài request context, chẳng hạn trong batch job hoặc message consumer, không nên giả định `ServletUriComponentsBuilder` có request hiện tại; hãy dùng public base URI được cấu hình rõ ràng và tạo `Link` từ URI đó.

## Xử lý forwarded headers khi chạy sau proxy

Reverse proxy hoặc load balancer có thể kết thúc TLS, đổi host, port hoặc loại bỏ path prefix trước khi chuyển request đến ứng dụng. Proxy có thể gửi các header như:

```http
Forwarded: proto=https;host=api.example.com
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /shop
```

Spring HATEOAS dựa trên request URI của Spring Framework để xây link. Nếu ứng dụng không xử lý forwarded headers, link có thể chứa host nội bộ, scheme `http` hoặc thiếu prefix công khai.

### Cấu hình Spring Boot 4.x

Với Spring Boot 4.x hiện hành, có thể bật xử lý forwarded headers qua cấu hình server:

```yaml
server:
  request:
    header:
      forwarded:
        strategy: framework
        use-prefix: true
```

`strategy: framework` dùng hỗ trợ forwarded header của Spring Framework. `use-prefix: true` bật xử lý `X-Forwarded-Prefix` khi proxy dùng header này để thông báo path prefix đã bị loại bỏ trước khi request đến ứng dụng.

### Cấu hình Spring Boot 3.x

Ở các phiên bản Spring Boot 3.x, thuộc tính thường dùng là:

```yaml
server:
  forward-headers-strategy: framework
```

Tên thuộc tính forwarded-header đã thay đổi giữa các thế hệ Boot. Hãy dùng cấu hình thuộc phiên bản thực tế trong dự án; không sao chép đồng thời cả hai cấu hình vào một ứng dụng.

### Cấu hình Spring Framework MVC không dùng Boot

Trong ứng dụng Servlet MVC không có Boot auto-configuration, cần đăng ký `ForwardedHeaderFilter` với Servlet container. Nếu dự án dùng `AbstractAnnotationConfigDispatcherServletInitializer`, có thể thêm filter vào danh sách filter của initializer:

```java
import jakarta.servlet.Filter;
import org.springframework.web.filter.ForwardedHeaderFilter;

@Override
protected Filter[] getServletFilters() {
    return new Filter[] { new ForwardedHeaderFilter() };
}
```

Đây là phần override trong lớp kế thừa `AbstractAnnotationConfigDispatcherServletInitializer`; lớp initializer vẫn cần triển khai các phương thức cấu hình root context, servlet context và servlet mapping của ứng dụng. Có thể đăng ký filter tương đương trong `web.xml`. Filter cần được áp dụng trước các thành phần downstream đọc request, để controller và link builder nhìn thấy scheme/host/prefix đã được điều chỉnh. Nếu dùng Spring Boot và đã cấu hình forwarded strategy, không đăng ký thêm filter thứ hai một cách tùy tiện.

## Bảo mật forwarded headers

Forwarded headers có thể làm thay đổi host, scheme, port và prefix mà ứng dụng dùng để tạo link. Nếu ứng dụng tin mọi giá trị do client gửi, kẻ tấn công có thể giả mạo host hoặc scheme để tạo link độc hại trong response.

Chỉ xử lý forwarded headers khi request đi qua proxy đáng tin cậy. Proxy ở ranh giới tin cậy cần xóa hoặc ghi đè cả `Forwarded` và các header `X-Forwarded-*` do client bên ngoài tự gửi, sau đó tự thêm giá trị đúng. Cấu hình ứng dụng chỉ nhận thông tin từ các proxy được kiểm soát.

Không bật forwarded-header handling một cách máy móc trong môi trường mà ứng dụng nhận request trực tiếp từ Internet. Nếu không có proxy đáng tin cậy, hãy giữ chế độ xử lý phù hợp với môi trường và không tin các header này.

## Context path, servlet path và prefix

Ứng dụng có thể được triển khai dưới context path, ví dụ `/orders-app`, hoặc nằm sau proxy công bố prefix `/shop`. Hai giá trị này có nguồn gốc khác nhau:

| Giá trị | Nguồn | Ví dụ |
| --- | --- | --- |
| Context path | Cấu hình servlet container/ứng dụng | `/orders-app` |
| Servlet path | Mapping của DispatcherServlet | `/mvc` |
| Forwarded prefix | Proxy thông báo prefix công khai đã strip | `/shop` |
| Controller mapping | `@RequestMapping` trong code | `/api/orders` |

Link cuối cùng cần phản ánh đúng đường đi mà client có thể gọi từ bên ngoài. Không tự thêm prefix vào controller mapping nếu proxy hoặc servlet container đã thêm prefix vào request; làm vậy có thể tạo đường dẫn lặp như `/shop/shop/api/orders`.

## CORS và hypermedia links

CORS quyết định trình duyệt có được phép đọc response hoặc gửi một số loại request cross-origin hay không. CORS không tạo link và không sửa `href` trong HAL.

Nếu browser client chạy ở origin khác, có thể cấu hình CORS bằng `WebMvcConfigurer`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class CorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://client.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders("Accept", "Content-Type", "Authorization");
    }
}
```

Thay origin và method theo client thực tế. Nếu API dùng HTTP `Link` hoặc `Location` header và browser cần đọc chúng, cấu hình `exposedHeaders` tương ứng. Link nằm trong JSON body không cần expose header CORS riêng, nhưng request theo link vẫn phải tuân thủ CORS của endpoint đích.

## Kiểm thử cấu hình MVC và HAL

Kiểm thử cần xác nhận media type, cấu trúc HAL và URI được tạo theo request. Đừng chỉ kiểm tra assembler trả về một object có link; hãy kiểm tra response đã qua Spring MVC message converter.

### Kiểm tra content negotiation

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists());
```

Test xác nhận MVC chọn converter hypermedia và trả cấu trúc HAL có self link.

### Kiểm tra URI sau reverse proxy

Khi test có đăng ký `ForwardedHeaderFilter`, có thể gửi forwarded headers:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .header("X-Forwarded-Proto", "https")
        .header("X-Forwarded-Host", "api.example.com")
        .header("X-Forwarded-Port", "443")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value(org.hamcrest.Matchers.startsWith(
            "https://api.example.com/")));
```

Nếu proxy dùng `X-Forwarded-Prefix`, hãy kiểm tra link có prefix đúng một lần. Test này chỉ có ý nghĩa khi filter/strategy forwarded headers thật sự được bật trong test context.

### Các trường hợp nên có trong bộ test

- `Accept: application/hal+json` trả HAL với `Content-Type` tương thích.
- `Accept: application/json` tuân theo chính sách default HAL hoặc JSON thuần đã cấu hình.
- Link `self` phản ánh context path và mapping controller.
- Link không chứa host nội bộ khi chạy sau proxy.
- Scheme HTTPS, host, port và forwarded prefix được xử lý đúng.
- Query parameter và path variable được encode đúng trong link.
- Endpoint không hỗ trợ media type yêu cầu trả lỗi content negotiation phù hợp.
- Không có forwarded header từ nguồn không tin cậy nào được dùng để tạo host tùy ý.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Thêm `@EnableHypermediaSupport` dù Boot đã auto-configure | Có thể thay đổi cách Boot tùy biến mapper hoặc tạo cấu hình trùng. | Dùng auto-configuration mặc định; chỉ bật thủ công khi cần kiểm soát rõ ràng. |
| Dùng `@EnableWebMvc` trong ứng dụng Boot mà không chủ đích | Làm mất một phần MVC auto-configuration của Boot. | Chỉ dùng trong cấu hình Spring MVC thuần hoặc khi chủ động thay thế auto-config. |
| Tự tạo `ObjectMapper` không có module HATEOAS | `EntityModel` có thể serialize sai cấu trúc HAL. | Dùng mapper/converter do Boot hoặc Spring HATEOAS cấu hình. |
| Converter Jackson tùy chỉnh đứng trước converter HAL | Content negotiation có thể trả JSON không có `_links` đúng chuẩn. | Giữ hypermedia modules và kiểm tra thứ tự converter. |
| Không xử lý forwarded headers sau proxy | Link chứa `http`, host nội bộ hoặc thiếu prefix. | Cấu hình forwarded strategy/filter phù hợp với Boot và proxy. |
| Tin forwarded headers từ mọi client | Có thể tạo link với host/scheme do attacker giả mạo. | Chỉ tin proxy kiểm soát; proxy phải strip/overwrite header từ bên ngoài. |
| Ghép host hoặc context path bằng chuỗi | Link sai khi đổi domain, port, context path hoặc proxy. | Dùng `WebMvcLinkBuilder` trong request context. |
| Dùng WebMvcLinkBuilder trong tác vụ nền không có request | Không có request context để suy ra base URI. | Dùng public base URI được cấu hình rõ ràng. |
| Nhầm CORS với link generation | CORS được bật nhưng `href` vẫn sai hoặc không truy cập được. | Kiểm tra CORS và URI generation như hai cấu hình riêng. |

## Ghi nhớ

- Spring MVC chịu trách nhiệm mapping, request context, content negotiation và serialize representation model.
- Spring Boot thường tự cấu hình Spring HATEOAS; không thêm `@EnableHypermediaSupport` nếu chưa cần kiểm soát thủ công.
- Trong Spring MVC thuần, bật `@EnableHypermediaSupport(type = HypermediaType.HAL, stacks = WebStack.WEBMVC)` cùng cấu hình MVC phù hợp.
- `HttpMessageConverter` và Jackson hypermedia module quyết định `EntityModel`/`CollectionModel` được serialize thành HAL như thế nào.
- Dùng `Accept: application/hal+json` để yêu cầu HAL rõ ràng; hiểu chính sách ánh xạ `application/json` của ứng dụng.
- `WebMvcLinkBuilder` lấy base URI từ request hiện tại và mapping controller; dùng `methodOn(...)` để tham chiếu method.
- Xử lý forwarded headers để link phản ánh scheme, host, port và prefix công khai khi chạy sau proxy.
- Chỉ tin forwarded headers do proxy đáng tin cậy tạo; chặn header giả mạo từ client bên ngoài.
- Không tự ghép host/path hoặc tạo mapper/converter mới thiếu module HATEOAS.
- Kiểm thử response HAL sau MVC serialization, content negotiation, context path và forwarded headers bằng MockMvc.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Configuration](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#configuration)
- [Spring HATEOAS Reference Documentation – Building links in Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.mvc.link-builder)
- [Spring HATEOAS Reference Documentation – Forwarded header handling](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.forwarded-headers)
- [Spring HATEOAS API – EnableHypermediaSupport](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/EnableHypermediaSupport.html)
- [Spring Boot Reference – Spring HATEOAS](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
- [Spring Boot Reference – Forwarded headers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework Reference – ForwardedHeaderFilter](https://docs.spring.io/spring/reference/web/webmvc/filters.html)
