# Thiết kế URL nhất quán với context path và đường dẫn công khai

Khi một ứng dụng Spring Boot được chạy trực tiếp ở máy phát triển, URL có thể đơn giản là `http://localhost:8080/api/products/42`. Nhưng khi triển khai sau reverse proxy, API gateway, load balancer hoặc dưới một prefix chung của tổ chức, cùng một endpoint có thể được truy cập công khai qua `https://api.example.test/catalog/v1/products/42` trong khi backend chỉ lắng nghe `http://catalog-service:8080/catalog/v1/products/42`.

Nếu không phân biệt **đường dẫn của ứng dụng trong Servlet container** với **đường dẫn công khai do gateway cung cấp**, lỗi thường gặp là 404, prefix bị lặp hoặc mất, redirect về `localhost:8080`, URL trong JSON sai scheme HTTP/HTTPS, cookie không dùng được, OpenAPI mô tả sai server hoặc đường dẫn frontend không tương ứng backend.

Bài học thuộc nhóm **Định tuyến web**, tập trung vào cách tổ chức URL nhất quán giữa **`server.servlet.context-path`**, **đường dẫn `@RequestMapping`**, **prefix của reverse proxy/API gateway**, **đường dẫn công khai** và **URL mà ứng dụng tự sinh**. Ví dụ chạy với **Spring Boot 3.3.x, Spring MVC/Servlet, Java 21 và Gradle**. Spring WebFlux có cấu hình base path và runtime khác; không áp nguyên xi mọi thuộc tính Servlet cho reactive stack.

## 1. Một URL có nhiều lớp cấu thành

Xem địa chỉ công khai:

~~~text
https://api.example.test/catalog/v1/products/42?lang=vi#details
|---|  |--------------| |---------------------| |-------| |------|
scheme       host                  path              query    fragment
~~~

Phân biệt:

- **Scheme**: `https` hay `http`; client bên ngoài có thể dùng HTTPS dù backend nhận HTTP từ reverse proxy.
- **Host**: `api.example.test`; hostname bên ngoài khác tên container nội bộ như `catalog-service`.
- **Port**: 443 mặc định của HTTPS hoặc 8080 nội bộ; proxy có thể giấu port của backend.
- **Path**: `/catalog/v1/products/42`, gồm prefix triển khai và route tới tài nguyên.
- **Query**: `lang=vi`, thường dùng bộ lọc, pagination hoặc tùy chọn; không đồng nghĩa URL path.
- **Fragment**: `#details` thuộc phần điều hướng phía client, thông thường **không được gửi trong HTTP request-target** đến server.

Đường dẫn công khai cần có hợp đồng rõ ràng. Ví dụ, API dùng host `api.example.test` và prefix `/catalog`. Các phiên bản API có thể đặt tiếp `/v1` hoặc `/v2`. Một request từ browser có thể đi qua nhiều lớp thay đổi URL trước khi tới controller.

Khung phân tích hữu ích:

~~~text
Browser/mobile client
    |
    | PUBLIC URL
    | https://api.example.test/catalog/v1/products/42
    v
CDN / API gateway / reverse proxy
    |
    | UPSTREAM URL (có thể giữ nguyên hoặc rewrite path)
    | http://catalog-service:8080/catalog/v1/products/42
    v
Embedded Tomcat + Servlet application context
    |
    | Spring MVC lookup path
    | /v1/products/42
    v
@RequestMapping("/v1/products") + @GetMapping("/{id}")
~~~

**Public URL không nhất thiết bằng upstream URL.** Cần xác định cụ thể proxy đang **giữ nguyên, thêm, bỏ hoặc thay thế** prefix; đây là điều kiện tiên quyết trước khi cấu hình context path.

## 2. Ba lớp đường dẫn cần phân biệt

Trong Spring Boot 3.3 + Spring MVC/Servlet, thường có ba lớp:

| Lớp | Ví dụ | Nơi cấu hình | Trách nhiệm |
| --- | --- | --- | --- |
| **Servlet context path** | `/catalog` | `server.servlet.context-path` | Prefix của toàn bộ Servlet web application |
| **DispatcherServlet servlet path** | Thông thường `/` | `spring.mvc.servlet.path` khi cần tùy biến | Mapping URL mà DispatcherServlet phụ trách |
| **Controller mapping** | `/v1/products/{id}` | `@RequestMapping`, `@GetMapping` | Route nghiệp vụ mà Spring MVC chọn |

Nếu dùng cấu hình đơn giản:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /catalog
~~~

và controller:

~~~java
@RestController
@RequestMapping("/v1/products")
class ProductController {
    @GetMapping("/{id}")
    public ProductView get(@PathVariable long id) {
        // ...
    }
}
~~~

thì đường dẫn mà Tomcat phục vụ từ ứng dụng này là:

~~~text
http://localhost:8080/catalog/v1/products/42
                       |------| |-------------|
                       context   controller mappings
~~~

Đây là **mã controller minh họa**, giả định `ProductView` và body method được định nghĩa. Dự án runnable đầy đủ ở phần sau.

**Không chèn lại context path vào `@RequestMapping`.** Nếu trong ví dụ trên viết `@RequestMapping("/catalog/v1/products")`, URL ứng dụng có thể thành `/catalog/catalog/v1/products/42`. Cũng không tự cộng `/catalog` vào mọi link khi đã dùng helper hiểu context path.

### 2.1. server.servlet.context-path tác động toàn ứng dụng Servlet

`server.servlet.context-path` là cấu hình ở tầng Servlet web application, không phải annotation route. Khi thay giá trị này, URL của những Servlet endpoints trong cùng application context thay đổi, kể cả nhiều endpoint REST và tùy trường hợp static resources hoặc các thành phần web cùng context.

Không nên thay context path riêng cho từng controller để “định tuyến nhóm”: khi cần namespace nghiệp vụ như `/v1/orders`, `/admin` hay `/internal`, dùng class-level `@RequestMapping` và policy phù hợp.

Giá trị mặc định là context path rỗng (root). Khi chạy ở root, `@GetMapping("/health")` thông thường được gọi qua `/health`; khi đặt context `/catalog`, URL là `/catalog/health`, trừ các endpoint thuộc web server/management context khác.

### 2.2. spring.mvc.servlet.path không phải một context path thứ hai tùy ý

`spring.mvc.servlet.path` cấu hình đường dẫn của `DispatcherServlet`, khác với `server.servlet.context-path`. Trong **Spring Boot 3.3**, chiến lược path matching `PathPatternParser` phổ biến theo mặc định **không tương thích với việc cấu hình DispatcherServlet bằng một path prefix qua `spring.mvc.servlet.path`**. Nếu bắt buộc dùng servlet path prefix, phải đánh giá chiến lược matching phù hợp, ví dụ `spring.mvc.pathmatch.matching-strategy=ant-path-matcher` theo tài liệu phiên bản đang dùng.

Vì vậy, **đừng tạo cấu hình demo có cả `spring.mvc.servlet.path=/api` và matching mặc định rồi khẳng định chắc chắn chạy được**. Với nhiều REST applications chỉ cần `server.servlet.context-path` và `@RequestMapping`; cách này dễ hiểu, ít bị phụ thuộc hạ tầng hơn.

### 2.3. Controller prefix là hợp đồng route

Một cách phổ biến:

~~~java
@RestController
@RequestMapping("/v1/products")
class ProductController {
    @GetMapping("/{id}")
    public ProductView getById(@PathVariable long id) {
        // ...
    }

    @GetMapping("/search")
    public List<ProductView> search(@RequestParam String q) {
        // ...
    }
}
~~~

Trong ví dụ, `/v1/products` thuộc API route. Nếu có nhiều nhóm controller khác nhau, mỗi nhóm có thể dùng class-level prefix khác nhau, còn context path của ứng dụng vẫn là `/catalog`.

Lưu ý: URL path matching, trailing slash và encoded path variables chịu quy tắc Spring Framework 6; đừng trông chờ `/v1/products/42/` luôn khớp với `/v1/products/42` nếu không có chủ đích cấu hình.

## 3. Công thức URL nội bộ và ví dụ không qua proxy

Trong trường hợp Servlet mapping mặc định `/` và không có reverse proxy rewrite:

~~~text
Application URL path =
    servlet context path
    + class-level @RequestMapping path
    + method-level mapping path
~~~

Ví dụ:

| Cấu hình | Giá trị |
| --- | --- |
| `server.port` | `8080` |
| `server.servlet.context-path` | `/catalog` |
| Controller class-level mapping | `/v1/products` |
| Method mapping | `/{id}` |
| Method input | `id=42` |
| Request URL tại backend | `http://localhost:8080/catalog/v1/products/42` |

Công thức là mô hình tư duy cho trường hợp đơn giản. Nếu có custom DispatcherServlet mapping, thêm Servlet, gateway rewrite hoặc forwarding rules đặc biệt, cần phân tích thêm tầng tương ứng.

### 3.1. Ba đường dẫn dễ bị nhìn nhầm

Trong một `HttpServletRequest` của ứng dụng Servlet:

- `getContextPath()`: context path của ứng dụng, ví dụ `/catalog`.
- `getRequestURI()`: request URI path mà request wrapper đang trình bày, ví dụ `/catalog/v1/products/42`; không bao gồm query string.
- `getServletPath()`: path portion dùng để xác định Servlet trong mapping hiện hành; phải xem actual Servlet mapping, không giả định luôn bằng nguyên controller route.
- `getPathInfo()`: phần path bổ sung trong một số kiểu Servlet mapping; có thể `null`.
- `getQueryString()`: query string thô, ví dụ `lang=vi`, không bao gồm dấu `?`.

Nếu có forwarded header processing, kết quả hiển thị qua các getter có thể được **wrapper** điều chỉnh theo public request. Vì vậy, log cần ghi rõ đang nhìn request tại proxy hay trong ứng dụng, và header forwarding đã được tin cậy/áp dụng hay chưa.

## 4. Ba kiểu triển khai public prefix qua gateway

Giả sử API đã có controller route `/v1/products/42`.

### 4.1. Kiểu A: Giữ nguyên prefix từ public đến backend

~~~text
Client:
  GET https://api.example.test/catalog/v1/products/42

Proxy forwards:
  GET http://catalog-service:8080/catalog/v1/products/42

Application:
  server.servlet.context-path=/catalog
  @RequestMapping("/v1/products")
  @GetMapping("/{id}")
~~~

Ưu điểm: path giữa client và backend giống nhau, dễ quan sát, dễ test và URL tự sinh thường cần ít translation hơn. Đối với nhiều hệ thống, **đây là cấu hình đơn giản nhất** nếu bạn kiểm soát cả gateway lẫn ứng dụng.

Proxy vẫn cần truyền đúng scheme/host/port bên ngoài khi ứng dụng tạo absolute links, redirect hoặc `Location`. Nếu không, ứng dụng có thể sinh `http://catalog-service:8080/catalog/...` dù client truy cập qua HTTPS.

### 4.2. Kiểu B: Proxy bỏ prefix công khai, backend chạy ở root

~~~text
Client:
  GET https://api.example.test/catalog/v1/products/42

Proxy strips /catalog and forwards:
  GET http://catalog-service:8080/v1/products/42

Application:
  server.servlet.context-path= (root)
  @RequestMapping("/v1/products")
  @GetMapping("/{id}")
~~~

Ở kiểu này, controller không biết `/catalog` từ URL backend nếu proxy không truyền thêm thông tin. **Inbound routing vẫn có thể hoạt động**, nhưng các URL do ứng dụng tự sinh, redirect hoặc link trong response có nguy cơ thiếu `/catalog`.

Nếu muốn ứng dụng hiểu public prefix, gateway có thể truyền `X-Forwarded-Prefix: /catalog` và ứng dụng cần có cấu hình forwarded-header processing phù hợp. Đây không phải yêu cầu bắt buộc nếu toàn bộ absolute public URLs được tạo bằng canonical base URL riêng và không cần introspect prefix, nhưng chính sách phải thống nhất.

### 4.3. Kiểu C: Proxy thay thế prefix khác trên backend

~~~text
Client:
  GET https://api.example.test/shop/v1/products/42

Proxy replaces /shop with /internal:
  GET http://catalog-service:8080/internal/v1/products/42

Application:
  server.servlet.context-path=/internal
  @RequestMapping("/v1/products")
  @GetMapping("/{id}")
~~~

Trong trường hợp này, client cần nhìn thấy đường dẫn `/shop/v1/products/42`, không phải `/internal/v1/products/42`. Theo cơ chế Spring Framework, proxy có thể gửi `X-Forwarded-Prefix: /shop` để mô tả public prefix, sau đó Spring xử lý forwarded headers để tạo external links đúng.

**Không kết hợp bừa hai chiến lược:** nếu proxy đã giữ nguyên `/shop` và ứng dụng cũng đặt context path `/shop`, không cần thêm một rewrite rule khiến backend nhận `/shop/shop/...`. Đặt ownership rõ cho từng prefix: gateway hay ứng dụng thêm/bỏ/thay thế nó?

## 5. Public URL và upstream URL có vai trò khác nhau

Định nghĩa rõ trong tài liệu triển khai:

| Thông tin | Ví dụ | Ai sở hữu? |
| --- | --- | --- |
| Public scheme | `https` | Ingress/TLS termination |
| Public host | `api.example.test` | DNS, gateway, public API contract |
| Public path prefix | `/catalog` | API gateway/ingress hoặc một quy ước dùng chung |
| Internal service address | `catalog-service:8080` | Service discovery/Kubernetes/network nội bộ |
| Internal context path | `/catalog` hoặc root | Spring Boot application/server config |
| Controller route | `/v1/products/{id}` | Application API code |
| Version segment | `/v1` | API contract/versioning policy |
| Public base URL for generated links | `https://api.example.test/catalog` | Gateway trust policy hoặc canonical config |

Một vấn đề hay gặp là viết code tạo URL bằng internal host/port thay vì external host/scheme. Cụ thể, `localhost` trong container thường chỉ chính container đó, không phải máy của người dùng. Public clients không thể dùng `http://catalog-service:8080/...` trừ khi có truy cập trực tiếp vào mạng nội bộ.

**Public API contract không nên phụ thuộc vào tên service nội bộ.** Backend có thể đổi service name/port/pod mà URL công khai vẫn ổn định nhờ gateway mapping.

## 6. Forwarded headers phục hồi thông tin public request

Khi proxy kết thúc TLS hoặc rewrite path, các thông tin mà Tomcat nhìn thấy có thể khác góc nhìn của client.

Các header phổ biến:

| Header | Ý nghĩa |
| --- | --- |
| `Forwarded` | Header chuẩn RFC 7239 cho thông tin `for`, `host`, `proto` qua proxy |
| `X-Forwarded-Host` | Host gốc mà client truy cập |
| `X-Forwarded-Proto` | Scheme gốc, ví dụ `https` |
| `X-Forwarded-Port` | Port bên ngoài, ví dụ `443` |
| `X-Forwarded-Prefix` | Public path prefix do proxy áp dụng |
| `X-Forwarded-For` | Chuỗi địa chỉ client/proxy theo các hop |

Ví dụ:

~~~text
Public:
  https://api.example.test/catalog/v1/products/42

Backend:
  http://catalog-service:8080/catalog/v1/products/42

Headers from trusted proxy:
  X-Forwarded-Host: api.example.test
  X-Forwarded-Proto: https
  X-Forwarded-Port: 443
~~~

Khi Spring dùng các forwarded headers đáng tin, một URI builder request-aware có thể tạo `https://api.example.test/catalog/...` thay vì `http://catalog-service:8080/catalog/...`.

### 6.1. server.forward-headers-strategy

Spring Boot 3.3 hỗ trợ các cách xử lý:

| Giá trị | Ý nghĩa thực tế |
| --- | --- |
| `none` | Không kích hoạt xử lý forwarded headers tự động từ Boot |
| `native` | Dùng cơ chế native của web server, ví dụ Tomcat RemoteIpValve; phạm vi và header hỗ trợ tùy runtime |
| `framework` | Dùng cơ chế Spring Framework: `ForwardedHeaderFilter` cho Servlet hoặc `ForwardedHeaderTransformer` cho WebFlux |

Khi chỉ cần host/proto/port trên một runtime có hỗ trợ native đầy đủ, `native` có thể đủ. Với kịch bản cần `X-Forwarded-Prefix` và URI reconstruction phức tạp, `framework` thường phù hợp hơn; vẫn cần kiểm thử behavior theo phiên bản Boot/Framework và proxy thực tế.

Ví dụ **application-prod.yml** chỉ dùng khi đã có trusted edge proxy:

~~~yaml
server:
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
~~~

Giá trị `redirect-context-root: false` được Spring Boot khuyến nghị khi **Tomcat nhận HTTPS đã termination ở proxy**, để scheme forwarded có thể được xét trước redirect đến context root của Tomcat. Thuộc tính này không thay thế việc cấu hình prefix và URL sinh ra trong controller.

**Không bật tin tưởng forwarded headers cho endpoint public nhận trực tiếp traffic tùy ý** nếu chưa kiểm soát trust boundary. Cấu hình production phải được xác định từ topology và chính sách của đơn vị vận hành.

### 6.2. Cảnh báo bảo mật: forwarded headers có thể bị giả mạo

Một client tùy ý có thể gửi:

~~~http
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
X-Forwarded-Prefix: /fake
~~~

Nếu server tin ngay vào chúng, absolute URLs, redirects, cookie settings hoặc link tạo trong email có thể bị ảnh hưởng. Vì vậy, **reverse proxy ở biên vùng tin cậy phải loại bỏ/ghi đè mọi `Forwarded` và `X-Forwarded-*` từ nguồn không đáng tin**, sau đó chỉ thêm giá trị do proxy tự xác nhận.

Cũng cần hạn chế khả năng client kết nối trực tiếp vào backend bỏ qua gateway. Header rewriting phải nhất quán qua các hop; không dùng một header từ client làm thẩm quyền xác định public origin nếu chưa kiểm tra.

Forwarded headers dùng cho **URL reconstruction và network metadata**, không tự chứng minh danh tính người dùng. Authentication/authorization là trách nhiệm riêng.

## 7. X-Forwarded-Prefix: thêm, bỏ hoặc thay thế phần đầu path

Spring Framework mô tả các tình huống khác nhau:

~~~text
Trường hợp override:
  public /api/{path}        -> internal /app1/{path}
  X-Forwarded-Prefix: /api

Trường hợp remove:
  public /{path}            -> internal /app1/{path}
  X-Forwarded-Prefix: (empty value)

Trường hợp insert:
  public /api/app1/{path}   -> internal /app1/{path}
  X-Forwarded-Prefix: /api/app1
~~~

`X-Forwarded-Prefix` không chỉ là một chuỗi bất biến “thêm vào URL”. Nó diễn đạt **prefix bên ngoài** mà Spring có thể dùng để điều chỉnh thông tin request đã được wrapper. Khi đã bật `ForwardedHeaderFilter`/framework strategy, cách một URL builder lấy context path có thể khác so với request nội bộ trước khi qua filter.

Hãy kiểm chứng cả **đường đi vào** (controller có được gọi không?) và **đường đi ra** (JSON self link, `Location`/redirect có chính xác public URL không?). Tình trạng request trả 200 chưa chứng minh URI sinh ra đã đúng.

### 7.1. Lỗi prefix bị lặp

Ví dụ:

~~~text
Expected: https://api.example.test/catalog/v1/products/42
Actual:   https://api.example.test/catalog/catalog/v1/products/42
~~~

Các nguồn lỗi:

- Ứng dụng đặt `server.servlet.context-path=/catalog` nhưng controller cũng map `/catalog/v1/...`.
- Gateway thêm `/catalog` dù upstream application đã có prefix này.
- Code nhận URI builder đã có context prefix rồi lại nối thủ công `/catalog`.
- Cấu hình forwarded prefix không khớp kiểu proxy rewrite.

Cách sửa là **xác định nơi sở hữu prefix**, không đổi ngẫu nhiên controller mappings. Viết bảng public → upstream → controller route và kiểm tra từng giá trị.

### 7.2. Lỗi mất prefix

~~~text
Expected: https://api.example.test/catalog/v1/products/42
Actual:   https://api.example.test/v1/products/42
~~~

Có thể proxy đã strip `/catalog`, backend chạy root và URI builder không nhận `X-Forwarded-Prefix`. Nếu app phát redirect, browser sẽ đi tới đường dẫn sai và nhận 404. Có thể sửa bằng forwarded-header processing có trust boundary rõ hoặc bằng public base URL được quản lý tập trung.

## 8. Tạo URL trong code: không hard-code localhost hay prefix

Không nên làm:

~~~java
// Ví dụ phản diện: đừng dùng trong backend triển khai nhiều môi trường.
String self = "http://localhost:8080/catalog/v1/products/" + id;
~~~

Trên máy phát triển, chuỗi có vẻ đúng, nhưng production thường dùng domain và HTTPS khác. Tương tự, nếu ghép tay `request.getContextPath()` vào URL builder vốn đã hiểu context path, bạn có thể nhận prefix gấp đôi.

### 8.1. ServletUriComponentsBuilder

Trong **Spring MVC Servlet** có utility `ServletUriComponentsBuilder`:

~~~java
URI self = ServletUriComponentsBuilder
    .fromCurrentContextPath()
    .path("/v1/products/{id}")
    .buildAndExpand(id)
    .toUri();
~~~

Đây là fragment minh họa chạy **bên trong một Servlet request**; cần import `java.net.URI` và `org.springframework.web.servlet.support.ServletUriComponentsBuilder`. `fromCurrentContextPath()` lấy scheme, host, port và context path từ request hiện hành (tính cả forwarded headers nếu đã được xử lý đúng), rồi nối route của ứng dụng.

Ví dụ:

~~~text
Trong local:
  http://localhost:8080/catalog/v1/products/42

Qua trusted HTTPS gateway cùng path:
  https://api.example.test/catalog/v1/products/42
~~~

**Tại sao dùng fromCurrentContextPath?** Vì phần context path được framework truy xuất, không phải một string hard-code. Nên chọn builder method phù hợp với scope: `fromCurrentRequestUri()` có thể hữu ích khi muốn giữ URI path của request đang xử lý; `fromCurrentContextPath()` hữu ích khi cần tạo URI cho route khác trong cùng application context.

### 8.2. Path segment và encoding

Nếu path chứa text do user cung cấp, đừng nối raw text như:

~~~java
String unsafe = "/products/" + userInput;
~~~

Một ký tự `/`, `?` hoặc `#` trong input có thể thay đổi cấu trúc URL; còn percent-encoding có các quy tắc riêng. Hãy truyền dữ liệu vào URI builder và áp dụng phương pháp encoding phù hợp:

~~~java
URI uri = UriComponentsBuilder
    .fromPath("/products")
    .pathSegment("{sku}")
    .encode()
    .buildAndExpand(sku)
    .toUri();
~~~

Đây là fragment minh họa (giả định `sku` được cung cấp, import `UriComponentsBuilder` và `URI`). Với dữ liệu đã encoded hoặc các route có wildcard, cần kiểm tra tránh **double encoding** và đảm bảo normalizing ở gateway/controller thống nhất. Không coi URL encoding là cơ chế authorization.

### 8.3. Absolute và relative links

Một API có thể trả:

~~~json
{"self":"/catalog/v1/products/42"}
~~~

hoặc:

~~~json
{"self":"https://api.example.test/catalog/v1/products/42"}
~~~

**Relative link** ít phụ thuộc host/scheme, phù hợp khi client giải quyết nó dựa trên public origin đúng. **Absolute link** hữu ích cho HATEOAS, Location hoặc integration bên ngoài, nhưng cần xác định public origin đáng tin.

Nếu tạo email links, webhook callbacks hoặc background jobs **không có HTTP request**, `ServletUriComponentsBuilder.fromCurrentContextPath()` không phải giải pháp chung vì không có current request. Khi đó nên dùng **canonical public base URL** trong config đã được kiểm soát cho từng môi trường.

## 9. Redirect và Location phải dùng URL public

HTTP redirect và Location header là nơi lỗi routing dễ lộ nhất. Giả sử người dùng đang ở:

~~~text
https://api.example.test/catalog/v1/products/go
~~~

Nếu server trả:

~~~http
HTTP/1.1 302 Found
Location: http://catalog-service:8080/catalog/v1/products/42
~~~

thì backend đã để lộ/internalize địa chỉ và browser có thể không truy cập được. Nếu đúng public origin và prefix, Location phải là:

~~~http
HTTP/1.1 302 Found
Location: https://api.example.test/catalog/v1/products/42
~~~

Có thể dùng `ResponseEntity.status(HttpStatus.FOUND).location(uri).build()` để kiểm soát rõ URL. Với POST tạo resource thật sự, response `201 Created` và `Location` chỉ ra tài nguyên mới là thông lệ phù hợp, nhưng phải đảm bảo resource đã thực sự được tạo; demo phía dưới dùng **GET redirect 302** để không giả vờ lưu dữ liệu.

### 9.1. Các status redirect thường dùng

| Status | Ý nghĩa ngắn |
| --- | --- |
| 301 Moved Permanently | Tài nguyên được chuyển vĩnh viễn, client có thể cache theo chính sách |
| 302 Found | Redirect tạm thời; client thực tế có thể đổi method POST thành GET tùy cơ chế |
| 303 See Other | Sau hành động, chuyển client sang GET ở URI khác |
| 307 Temporary Redirect | Redirect tạm thời và giữ nguyên HTTP method theo chuẩn |
| 308 Permanent Redirect | Redirect vĩnh viễn và giữ nguyên HTTP method theo chuẩn |

Không tự suy rằng redirect luôn giữ method hoặc luôn chuyển sang GET. Chọn status theo hành vi API/client mong muốn và kiểm thử với client thực tế.

### 9.2. Tránh open redirect

Không nhận `?next=https://attacker.example` rồi trả `Location` trực tiếp mà không kiểm tra. Nếu redirect nhận URL từ client, nên giới hạn đích thuộc cùng ứng dụng hoặc allowlist cụ thể, kiểm tra scheme/host/path đúng cách. Forwarded host không được kiểm soát cũng có thể trở thành đầu vào gây **host-header poisoning** cho absolute redirects.

## 10. Thiết kế route nhất quán theo API resource

Nên phân biệt phần do **triển khai sở hữu** và phần do **hợp đồng API sở hữu**:

~~~text
Public prefix:         /catalog
API version:           /v1
Resource collection:   /products
Resource identifier:   /{id}
--------------------------------
Public route:          /catalog/v1/products/{id}
~~~

Một chiến lược rõ ràng:

- `/catalog` do gateway/context path sở hữu.
- `/v1` do API version policy sở hữu.
- `/products` do controller/resource design sở hữu.
- `/{id}` là resource identifier, nên được validate và encode.
- Query như `?page=1&size=20` dành cho filter/pagination, không thay route gốc.

Nên sử dụng danh từ cho collections và item resources khi thiết kế REST, tránh nhét environment name (dev/staging) vào route công khai nếu host đã phân biệt môi trường. Một số hệ thống cần version qua hostname hoặc media type; hãy chọn một quy ước thống nhất và tài liệu hóa.

### 10.1. Không gắn hostname nội bộ vào route nghiệp vụ

Controller không nên chứa `http://catalog-service:8080` hoặc `api.example.test` trong `@RequestMapping`. Annotation này nhận **path pattern**, không phải cấu hình public origin. Host/domain routing thuộc gateway, reverse proxy hoặc điều kiện routing chuyên biệt được thiết kế riêng.

### 10.2. Tránh path tùy tiện theo môi trường

Nếu local chạy `/api/products`, staging `/staging/api/products` và production `/catalog/api/products`, test có nguy cơ bỏ sót lỗi do prefix. Hãy có ma trận môi trường nêu public URL, upstream path, context path và forwarded header policy, thay vì để các team tự suy đoán.

## 11. Cấu hình Spring Boot theo môi trường

### 11.1. Cấu hình mặc định cho local

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /catalog
~~~

Trên local không có proxy, endpoint:

~~~text
http://localhost:8080/catalog/v1/products/42
~~~

Không cần cấu hình forwarded headers chỉ để chạy `localhost`.

### 11.2. Cấu hình cho production có trusted proxy

**src/main/resources/application-prod.yml**

~~~yaml
server:
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
~~~

Đây là cấu hình bổ sung theo profile `prod`, không thay đổi context path trong `application.yml`. Proxy phải chuyển request tới upstream path chính xác và chuẩn hóa forwarding headers; backend nên chỉ nhận traffic từ hạ tầng tin cậy.

Kích hoạt profile bằng biến môi trường `SPRING_PROFILES_ACTIVE=prod` hoặc tham số cấu hình tương ứng; đừng gắn profile prod vào toàn bộ môi trường phát triển để rồi mặc nhiên tin header do client tự gửi.

### 11.3. Cấu hình canonical base URL nếu không có request

Trong các tác vụ email/async/batch, có thể định nghĩa property riêng cho ứng dụng:

~~~yaml
app:
  public-base-url: "https://api.example.test/catalog"
~~~

Đây là **property tự định nghĩa** `app.public-base-url`; Spring Boot không tự dùng nó để sửa routing, response hoặc redirects. Ứng dụng có thể inject bằng `@ConfigurationProperties` và dùng nó làm nguồn tạo URL từ background jobs.

Tránh hard-code một public URL production trong code Java. Nguồn cấu hình nên được quản lý, kiểm thử và giới hạn quyền thay đổi.

## 12. Ví dụ đầy đủ Spring Boot MVC: public self link và redirect

Dự án sau triển khai một ứng dụng đọc product demo, có:

1. Servlet context path `/catalog`.
2. Controller `/v1/products` và item route `/{id}`.
3. Trả JSON với **self URL** được tạo từ current request context.
4. Endpoint chuyển hướng tới product 42 với **Location** dựng bằng URL builder.
5. MockMvc tests cho URL nội bộ và URL công khai thông qua forwarded headers đáng tin.

Ví dụ không giả vờ tạo/sửa dữ liệu thật: chỉ có product `id=42` để tập trung vào đường dẫn.

Cấu trúc:

~~~text
public-url-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/publicurl/
    │   │   ├── PublicUrlApplication.java
    │   │   └── ProductController.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-prod.yml
    └── test/java/com/example/publicurl/
        └── ProductControllerTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'public-url-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/com/example/publicurl/PublicUrlApplication.java**

~~~java
package com.example.publicurl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PublicUrlApplication {
    public static void main(String[] args) {
        SpringApplication.run(PublicUrlApplication.class, args);
    }
}
~~~

**src/main/java/com/example/publicurl/ProductController.java**

~~~java
package com.example.publicurl;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/v1/products")
public class ProductController {

    public record ProductView(long id, String name, URI self) {
    }

    @GetMapping(path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ProductView> show(@PathVariable long id) {
        if (id != 42L) {
            return ResponseEntity.notFound().build();
        }

        URI self = productUri(42L);
        return ResponseEntity.ok(
            new ProductView(42L, "Notebook", self));
    }

    @GetMapping("/go")
    public ResponseEntity<Void> redirectToProduct() {
        return ResponseEntity.status(HttpStatus.FOUND)
            .location(productUri(42L))
            .build();
    }

    private URI productUri(long id) {
        return ServletUriComponentsBuilder
            .fromCurrentContextPath()
            .path("/v1/products/{id}")
            .buildAndExpand(id)
            .toUri();
    }
}
~~~

Giải thích:

- `@RequestMapping("/v1/products")` không lặp lại `/catalog`.
- `ProductView.self` là `URI`; Jackson thường ghi nó thành chuỗi URL trong JSON.
- `productUri(...)` lấy context path + public scheme/host khi request được xử lý đúng theo forwarded-header strategy.
- `GET /v1/products/go` là route cụ thể hơn `/{id}`, vì vậy MVC có thể chọn chính xác route `/go` thay vì ép `go` thành long.
- `show(42)` trả 200 với self link; id khác trả 404 theo dữ liệu demo.
- `redirectToProduct()` trả 302 và `Location`, không tạo resource hoặc đổi state.

**application.yml**:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /catalog
~~~

**application-prod.yml**:

~~~yaml
server:
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
~~~

Đối với hạ tầng thật, trước khi bật profile prod hãy xác nhận proxy lọc incoming `Forwarded` và `X-Forwarded-*` headers, chỉ chuyển các giá trị đáng tin.

### 12.1. Chạy local

Với JDK 21 và Gradle tương thích (ví dụ Gradle 8.5), nếu có wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell dùng `.\gradlew.bat bootRun`. Nếu project chưa có wrapper nhưng đã cài Gradle:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Thử product 42:

~~~bash
curl -i http://localhost:8080/catalog/v1/products/42
~~~

Kỳ vọng HTTP **200 OK** và JSON có ý nghĩa:

~~~json
{
  "id": 42,
  "name": "Notebook",
  "self": "http://localhost:8080/catalog/v1/products/42"
}
~~~

Thứ tự JSON fields, header và log có thể khác tùy runtime; nội dung `self` là điều cần quan sát. Với ID không tồn tại:

~~~bash
curl -i http://localhost:8080/catalog/v1/products/99
~~~

Kỳ vọng HTTP **404 Not Found** do controller từ chối ID 99.

Thử redirect:

~~~bash
curl -i http://localhost:8080/catalog/v1/products/go
~~~

Kết quả dự kiến có status **302 Found** và header:

~~~http
Location: http://localhost:8080/catalog/v1/products/42
~~~

Trong local không có forwarded header processing, đây là URL đúng của ứng dụng. Không mở server từ Internet để thử tin forwarded headers tùy ý.

### 12.2. Chạy sau trusted HTTPS gateway

Giả sử proxy giữ nguyên path:

~~~text
Client URL:
  https://api.example.test/catalog/v1/products/42

Backend URL:
  http://catalog-service:8080/catalog/v1/products/42

Trusted proxy forwards:
  X-Forwarded-Host: api.example.test
  X-Forwarded-Proto: https
  X-Forwarded-Port: 443
~~~

Với `server.forward-headers-strategy=framework`, expected `self` được dựng là:

~~~text
https://api.example.test/catalog/v1/products/42
~~~

Không dùng `X-Forwarded-Prefix` khi public và internal prefix đã giống nhau trừ khi topology và proxy policy yêu cầu rõ. Nếu proxy thay thế prefix, áp dụng `X-Forwarded-Prefix` theo đúng kịch bản và kiểm thử self link/Location đầu ra.

## 13. Kiểm thử URL và Location với MockMvc

Không chỉ test controller nhận đúng URL; cần test response dùng đúng public origin. Với Spring Boot, có thể chạy MockMvc dưới ứng dụng Servlet và bật forwarded-header framework strategy **riêng trong test context** để giả lập request từ trusted proxy.

**src/test/java/com/example/publicurl/ProductControllerTest.java**

~~~java
package com.example.publicurl;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "server.forward-headers-strategy=framework")
@AutoConfigureMockMvc
class ProductControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void localContextPathIsIncludedOnce() throws Exception {
        mvc.perform(get("/catalog/v1/products/42")
                .contextPath("/catalog"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.self")
                .value("http://localhost/catalog/v1/products/42"));
    }

    @Test
    void forwardedPublicOriginProducesPublicSelfLink() throws Exception {
        mvc.perform(get("/catalog/v1/products/42")
                .contextPath("/catalog")
                .header("X-Forwarded-Host", "api.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.self")
                .value("https://api.example.test/catalog/v1/products/42"));
    }

    @Test
    void redirectLocationIncludesContextPath() throws Exception {
        mvc.perform(get("/catalog/v1/products/go")
                .contextPath("/catalog"))
            .andExpect(status().isFound())
            .andExpect(header().string(
                "Location",
                "http://localhost/catalog/v1/products/42"));
    }

    @Test
    void missingProductReturns404() throws Exception {
        mvc.perform(get("/catalog/v1/products/99")
                .contextPath("/catalog"))
            .andExpect(status().isNotFound());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

**Vì sao trong MockMvc URL là `http://localhost` không có `:8080`?** MockHttpServletRequest mặc định mô phỏng request tại host localhost, port mặc định tương ứng HTTP 80; nó không phải một TCP request thực tới embedded Tomcat port 8080. Khi chạy `bootRun` và dùng `curl` tới port 8080 thật, URI builder sẽ nhìn thấy port của request thực.

Các tests trên kiểm tra controller routing, context path và forwarded origin theo Spring test setup. Chúng **không thay thế** integration test ở gateway thật: ingress có thể strip prefix sai, thêm header lặp hoặc thay host khác so với mock.

### 13.1. Kiểm thử gateway từ bên ngoài

Trong môi trường staging do bạn quản lý, tạo ma trận tối thiểu:

| Request public | Điều mong đợi |
| --- | --- |
| GET product tồn tại | 200, JSON self link có đúng public scheme/host/prefix |
| GET product không tồn tại | 404 theo API contract |
| GET redirect | 302, `Location` trỏ tới URL public hợp lệ |
| GET qua HTTP nếu có redirect HTTPS | Không redirect loop; Location trỏ HTTPS theo policy |
| GET có query | Query được truyền đúng khi route có dùng |
| URL có trailing slash sai | 404 hoặc redirect có chủ đích, thống nhất |
| Request có path encoded | Không decode hai lần; không vượt ranh giới authorization |
| Client thử giả mạo forwarded headers | Proxy loại bỏ/ghi đè, URL response không bị poisoning |
| Public request qua subdomain phụ | CORS/cookies/callbacks hợp lệ nếu chính sách cho phép |

Không cần thử các tình huống giả mạo trên môi trường người khác hoặc internet public mà không được phép; kiểm thử trong hạ tầng của mình.

## 14. Lỗi 404 do context path, prefix và route

Đừng sửa `@GetMapping` trước khi biết request thực tế đến backend với path nào.

Một quy trình điều tra:

1. Xác nhận **public request URL** chính xác (scheme, host, path, query).
2. Xác nhận proxy/ingress đã match route và có forward tới đúng service chưa.
3. Đọc **upstream request path** sau rewrite.
4. Xác nhận `server.servlet.context-path` có hiệu lực của profile đang chạy.
5. Xác nhận class-level và method-level `@RequestMapping` đã ghép đúng.
6. Nếu có `spring.mvc.servlet.path`, xác minh actual mapping và chiến lược path matching.
7. Kiểm tra `DispatcherServlet` và `RequestMappingHandlerMapping` thực sự đã đăng ký route chưa.
8. Kiểm tra controller bean có nằm trong phạm vi component scan của `@SpringBootApplication` không.
9. Phân biệt 404 do **không có handler** với 404 do **nghiệp vụ không tìm thấy resource**.
10. So sánh local direct request với staging request qua gateway.

Nếu Spring Boot không tìm được endpoint vì route, lỗi có thể xuất hiện ở Spring MVC hoặc static resource handler tùy cấu hình. Không kết luận rằng 404 luôn do nginx/gateway hay do thiếu controller.

### 14.1. Các mẫu sai thường gặp

| Triệu chứng | Nguyên nhân hay gặp |
| --- | --- |
| `/catalog/catalog/...` | Prefix được thêm hai lần |
| `/v1/products/...` công khai thiếu `/catalog` | Proxy strip prefix, app không khôi phục public prefix khi tạo link |
| App chỉ chạy ở `/catalog/...` nhưng client gọi `/api/...` | Public contract và proxy rewrite chưa thống nhất |
| Link trỏ `http://catalog-service:8080` | Thiếu forwarded host/proto hoặc code hard-code internal URL |
| Redirect từ HTTPS về HTTP | Proxy TLS termination nhưng app không hiểu forwarded proto hoặc redirect context root quá sớm |
| Gateway trả 502/503 | Không nhất thiết do controller mapping; có thể upstream unavailable/connection error |
| Redirect loop | Gateway và app cùng ép scheme/prefix theo quy tắc mâu thuẫn |
| Local 200, staging 404 | Khác context path, proxy rewrite, component scanning, route hoặc ingress host |

## 15. URL, CORS, cookies và security có quan hệ gì?

Khi đổi public host/path, không chỉ controller route bị ảnh hưởng. Browser và security framework còn áp dụng những quy tắc riêng.

### 15.1. Same-origin và CORS

Origin được xác định bởi **scheme + host + port**, không phải path prefix. Hai URL cùng domain/scheme/port nhưng khác `/catalog` và `/admin` thường vẫn cùng origin; còn `https://app.example.test` gọi `https://api.example.test` là cross-origin dù có chung prefix.

CORS policy cần liệt kê origin đáng tin theo contract, không suy diễn từ `server.servlet.context-path`. CORS preflight `OPTIONS` có thể bị chặn trước khi handler chạy nếu gateway/Spring Security chưa cấu hình phù hợp.

### 15.2. Cookies và session path

Cookie có thuộc tính `Path` quyết định những request nào từ browser sẽ gửi cookie. Một app chạy dưới `/catalog` có thể cần cookie path phù hợp; sau khi gateway chuyển public prefix hoặc thay root, hãy kiểm tra `Set-Cookie` và behavior của browser.

Cookie cũng bị chi phối bởi `Domain`, `Secure`, `HttpOnly`, `SameSite` và HTTPS; không thể chỉ sửa context path để mọi cookie/session hoạt động. Tuyệt đối không dùng cookie path như cơ chế phân quyền.

### 15.3. CSRF và authorization matcher

Nếu Spring Security rules dựa trên đường dẫn, phải hiểu matcher đang hoạt động theo **request path trong ứng dụng**, không nhất thiết là URL public chưa rewrite. Khi gateway thay prefix, security rule phải bảo vệ đúng controller routes mà backend nhận.

Một lỗi nghiêm trọng là gateway cho phép `/catalog/admin` nhưng authorization rule chỉ xét `/admin` với giả định sai về context path. Hãy test trực tiếp boundary và route thực tế, không suy đoán từ chuỗi URL.

### 15.4. Host header và forwarded header spoofing

Nếu ứng dụng tạo absolute URL dựa trên `Host` hoặc `X-Forwarded-Host` do client điều khiển, link trong reset password/email, redirect hoặc JSON response có thể bị đổi sang host lạ. Public base URL cho các liên kết có tác động bảo mật cao nên đến từ cấu hình trusted/canonical thay vì một header chưa kiểm chứng.

## 16. Frontend, static assets, SPA và API docs

### 16.1. Frontend đặt ở cùng hoặc khác origin

Một SPA được phục vụ ở `https://web.example.test/app/` có thể gọi API ở `https://api.example.test/catalog/v1/...`. Trong trường hợp này, không dùng relative path `/v1/products` nếu nó làm browser gửi request về domain frontend không đúng. Phải cấu hình API base URL của frontend theo environment, hoặc có gateway route chung phục vụ cùng origin.

Nếu frontend được phục vụ dưới `/catalog`, absolute paths bắt đầu bằng `/` có thể bỏ mất prefix. Hãy thống nhất build-time base path của frontend, router base path và server public prefix.

### 16.2. Static assets và redirect

HTML có `<script src="/main.js">` sẽ yêu cầu file tại root domain, không tự thêm `/catalog`. Nếu app thật sự được phục vụ dưới prefix, cần dùng đường dẫn asset phù hợp hoặc cấu hình frontend bundler/base path; không trông chờ Spring MVC sửa mọi link bên trong HTML.

### 16.3. OpenAPI/Swagger servers và Try it out

Nếu API docs sinh `servers: [http://localhost:8080]` trong môi trường staging/production, client “Try it out” có thể gọi sai domain/protocol. Hãy cấu hình public server URL hoặc forwarded headers đúng theo tool OpenAPI đang dùng. Swagger UI path cũng phải được tính cùng proxy/context path; đây là cấu hình của thư viện docs, không phải `@RequestMapping` của controller.

### 16.4. Actuator có thể có base path/port riêng

`/actuator/health` không nhất thiết có URL giống tất cả business endpoints. Khi Actuator chạy cùng port/context, base path management có quan hệ với application context path; khi cấu hình `management.server.port` riêng, nó có thể dùng management context/base path riêng.

Hãy xác định rõ đâu là **public API endpoint** và đâu là **internal monitoring endpoint**. Không mở mọi Actuator endpoints ra public internet chỉ để dashboard hoặc liveness probe hoạt động.

## 17. Spring MVC/Servlet và Spring WebFlux: đừng dùng nhầm thuộc tính

| Chủ đề | Spring MVC/Servlet | Spring WebFlux |
| --- | --- | --- |
| Web dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Prefix ứng dụng thông dụng | `server.servlet.context-path` | `spring.webflux.base-path` theo cấu hình Boot |
| Servlet mapping | `spring.mvc.servlet.path` (có giới hạn matching strategy) | Không phải cơ chế Servlet path của MVC |
| Request/response API | `HttpServletRequest`/`HttpServletResponse` | `ServerWebExchange`/reactive HTTP APIs |
| Forwarded-header support | `ForwardedHeaderFilter` khi dùng framework strategy | `ForwardedHeaderTransformer` khi dùng framework strategy |
| Server mặc định | Tomcat với `spring-boot-starter-web` | Reactor Netty với `spring-boot-starter-webflux` |

Đừng đặt `server.servlet.context-path=/catalog` trong reactive app rồi khẳng định mọi WebFlux routes đã có prefix đó. Ngược lại, `spring.webflux.base-path` không phải cách cấu hình Servlet context path của Spring MVC.

Khi cả hai starters cùng nằm trong classpath, Boot thường chọn Servlet/MVC theo mặc định; xác nhận runtime thực tế trước khi debug prefix.

## 18. Checklist thiết kế URL nhất quán

Trước khi release một API đi qua proxy/gateway:

1. **Công khai:** public scheme/host/port và URL prefix chính thức là gì?
2. **Nội bộ:** backend lắng nghe port nào, context path nào, controller route nào?
3. **Proxy:** request path được pass-through, strip, prepend hay replace prefix?
4. **Forwarding:** proxy gửi những header `Forwarded`/`X-Forwarded-*` nào, thứ tự hop ra sao?
5. **Tin cậy:** edge proxy đã xóa/ghi đè headers do client tùy ý gửi chưa?
6. **Spring Boot:** `server.forward-headers-strategy` là `none`, `native` hay `framework`, vì sao?
7. **Tomcat TLS:** có cần `server.tomcat.redirect-context-root=false` trong topology TLS termination không?
8. **Mapping:** `server.servlet.context-path` có bị lặp trong `@RequestMapping` không?
9. **Dispatcher:** có cấu hình `spring.mvc.servlet.path` và kiểm tra tính tương thích path matcher chưa?
10. **URL sinh ra:** JSON self links, `Location`, redirects có dùng public origin/prefix đúng không?
11. **Không có request:** emails, webhooks, async jobs có canonical public base URL không?
12. **Encoding:** path variables/query được encode đúng, không bị double decode hay rewrite nguy hiểm?
13. **Security:** authorization matcher, CORS, CSRF và cookie Path/Secure có phù hợp với public route không?
14. **Frontend:** SPA router base, asset URLs và API base URL có dùng prefix đúng không?
15. **Docs:** OpenAPI servers, Swagger UI và API examples có trỏ domain/path public không?
16. **Monitoring:** health probes và Actuator có đặt đúng port/base path, giới hạn public exposure không?
17. **Tests:** đã test local direct URL, staging gateway URL, 404, redirect và Location chưa?
18. **Observability:** log có thể phân biệt public path, upstream path và controller mapping để điều tra không?
19. **Triển khai:** có ma trận environment → public URL → upstream URL → context path được review không?
20. **Rollback:** thay proxy/context path có thể rollback nhanh và không làm hỏng bookmarks/callbacks lâu dài không?

**Kết luận:** Thiết kế URL nhất quán đòi hỏi phân định rõ **public prefix do gateway trình bày**, **Servlet context path do ứng dụng triển khai** và **controller mapping do API định nghĩa**. Khi proxy giữ nguyên đường dẫn, cấu hình thường đơn giản; khi proxy strip/replace prefix, cần có chiến lược khôi phục public URL qua forwarded headers đáng tin hoặc canonical base URL. Đừng nhân đôi prefix trong `@RequestMapping`, đừng hard-code `localhost` vào links/redirects và đừng chấp nhận forwarded headers không được kiểm soát. Kiểm thử đồng thời **request đi vào** và **URL đi ra** là cách xác nhận cấu hình thật sự đúng qua mọi môi trường.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Embedded Web Servers / Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): `server.forward-headers-strategy`, TLS termination và Tomcat redirect context root.
- [Spring Framework — Servlet Filters / Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): `ForwardedHeaderFilter`, `X-Forwarded-Prefix`, security/trust considerations.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): MVC mapping, servlet path và `PathPatternParser` compatibility.
- [Spring Framework — Spring MVC Annotated Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): class/method mappings.
- [Spring Framework — UriComponentsBuilder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html): tạo URI và encoding.
