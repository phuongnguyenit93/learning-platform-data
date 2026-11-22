# Xử lý dấu gạch chéo cuối, ký tự mã hóa và đường dẫn không khớp trong Spring MVC

## 1. Mục tiêu và phạm vi

Trong ứng dụng Spring Boot dùng Spring MVC, hai URL nhìn có vẻ tương đương như **/api/items** và **/api/items/** có thể dẫn đến hai kết quả khác nhau. Dữ liệu chứa dấu cách, dấu gạch chéo, phần trăm, dấu tiếng Việt hoặc ký tự đặc biệt khi đưa vào URL cũng có thể thay đổi cấu trúc đường dẫn nếu mã hóa/giải mã không đúng. Ngoài ra, lỗi HTTP 404 không luôn đến từ việc thiếu controller: static resource handler, servlet container, proxy và các điều kiện @RequestMapping đều ảnh hưởng đến kết quả.

Bài học này tập trung vào **tùy chỉnh luồng khớp đường dẫn Spring MVC trên Servlet stack**, với embedded Tomcat phổ biến. Ví dụ sử dụng **Java 17+**, **Spring Boot 3.5.x**, Spring Framework 6.2 và Maven.

Sau khi học, bạn có thể:

1. Phân biệt **trailing slash**, URI path, path segment, query parameter và percent-encoding.
2. Giải thích cách **DispatcherServlet**, **HandlerMapping** và **PathPatternParser** xác định controller cho request.
3. Chọn chính sách nhất quán đối với **/resource** và **/resource/**: route tường minh, redirect URL chuẩn hoặc rewrite có kiểm soát.
4. Xử lý URL chứa **%20**, **%2B**, **%26**, Unicode và đặc biệt **%2F** một cách đúng đắn và an toàn.
5. Phân biệt HTTP **400**, **404**, **405**, **406**, **415** và lỗi do Spring Security/proxy.
6. Chẩn đoán **NoHandlerFoundException**, **NoResourceFoundException**, static resources, context path và reverse proxy.
7. Viết ứng dụng Spring Boot có test cho trailing slash, percent-encoded input và đường dẫn không khớp.

**Phân biệt phiên bản:** Spring MVC từ Spring Framework 6.0 mặc định không coi trailing slash là khớp ngầm; API cũ bật optional trailing slash đã bị deprecated trong 6.0 và bị loại bỏ trong Spring Framework 7.0. Spring Framework 6.2 bổ sung **UrlHandlerFilter** để chuẩn hóa hoặc redirect URL có dấu gạch chéo cuối. Nếu đang dùng Spring Boot 2.x, hãy đối chiếu hành vi và tài liệu tương ứng, không sao chép mặc định của Boot 3.x/4.x.

## 2. Request đi qua những bước nào trước khi khớp route?

~~~mermaid
flowchart TD
    A[HTTP client] --> B[CDN / Gateway / Reverse Proxy nếu có]
    B --> C[Tomcat connector: parse, validate, normalize URI]
    C --> D[Servlet Filter chain: Security, canonical URL...]
    D --> E[DispatcherServlet]
    E --> F[HandlerMapping: PathPatternParser + conditions]
    F --> G{Có handler phù hợp?}
    G -->|Có| H[HandlerAdapter gọi controller]
    G -->|Không| I[404 / static resource / error handling]
    H --> J[HTTP response]
    I --> J
~~~

Các tầng có trách nhiệm khác nhau:

| Tầng | Quyết định chính | Ví dụ |
|---|---|---|
| Client | Xây dựng URL, percent-encode từng thành phần | Giá trị **Cà phê** thành **C%C3%A0%20ph%C3%AA** |
| Proxy/gateway | Có thể rewrite đường dẫn, chuẩn hóa slash, từ chối URI hoặc kiểm tra WAF | **/public/api** được chuyển thành **/api** |
| Servlet container | Kiểm tra request-target, giải mã URI, quản lý encoded slash và ký tự không hợp lệ | Tomcat từ chối **%2F** trong path theo chính sách mặc định |
| Servlet Filter | Redirect/rewrite URL, xác thực, phân quyền | **UrlHandlerFilter**, Spring Security |
| Spring MVC HandlerMapping | So khớp path và các điều kiện HTTP method, params, headers, consumes, produces | **@GetMapping("/api/items/{id}")** |
| Controller | Nhận **@PathVariable** hoặc **@RequestParam** đã binding | id, query, body |
| Error handling | Tạo status và error response phù hợp | **404** cho endpoint không tìm thấy |

**Lưu ý quan trọng:** nếu Tomcat hoặc proxy trả **400** trước khi DispatcherServlet được gọi thì thay **@ControllerAdvice** hoặc **@GetMapping** không giải quyết được lỗi đó. Ngược lại, nếu URL hợp lệ nhưng HandlerMapping không tìm thấy mapping, thay đổi charset của request body cũng không giúp route khớp.

## 3. Spring MVC dùng PathPatternParser để khớp đường dẫn

Spring MVC hiện đại ưu tiên **PathPatternParser**. Spring Boot 3.5 sử dụng chiến lược này theo mặc định.

Với ví dụ:

~~~java
@GetMapping("/api/orders/{orderId}")
public String findOrder(@PathVariable String orderId) {
    return orderId;
}
~~~

- **/api/orders/42** khớp và binding **orderId=42**.
- **/api/orders/42/** không nhất thiết khớp vì có trailing slash thừa.
- **/api/orders/42/items** không khớp một biến **{orderId}** đơn lẻ.
- **/api/orders/C%C3%A0-ph%C3%AA** có thể được giải mã UTF-8 và binding thành giá trị có dấu, nếu connector/proxy cho phép.

### 3.1. PathPatternParser và AntPathMatcher

**PathPatternParser** tách request path thành các segment rồi so khớp với mẫu đã parse sẵn, tránh phải giải mã toàn bộ đường dẫn thành một String trước khi so khớp. Điều này quan trọng vì giải mã sớm những ký tự như **%2F** (dấu /) có thể làm thay đổi số lượng segment và ngữ nghĩa bảo mật.

**AntPathMatcher** là cách khớp mẫu dựa trên String lịch sử. Trong các phiên bản Boot 3.x tương ứng, có thể cấu hình:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: path-pattern-parser
~~~

Đây là mặc định; thông thường **không cần khai báo**. Nếu ứng dụng cũ phụ thuộc pattern không tương thích, Boot 3.5 còn có lựa chọn **ant-path-matcher** cho trường hợp đặc biệt:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

Tuy nhiên, **không đổi sang AntPathMatcher chỉ để “chữa” 404**. Điều đó có thể làm đổi quy tắc khớp, ảnh hưởng đến encoding, pattern specificity và bảo mật. Hãy tìm nguyên nhân sai URL/mapping trước, rồi dùng fallback chỉ khi có kiểm thử và yêu cầu tương thích cụ thể.

**Mẫu đường dẫn cần hiểu:**

| Mẫu | Phạm vi | Ghi chú |
|---|---|---|
| **/api/items/{id}** | Một path segment động | **{id}** không tự biểu diễn nhiều segment |
| **/api/items/{id:[0-9]+}** | Segment chỉ gồm chữ số | Input không đúng regex không khớp mapping |
| **/assets/*.png** | Tên file PNG trong một segment | Không bao trùm thư mục con |
| **/assets/** | Không hoặc nhiều segment cuối | ** trong PathPattern đặt ở cuối pattern |
| **/assets/{*path}** | Bắt nhiều segment cuối vào một biến | Chỉ hợp lệ ở vị trí cuối |
| **/api/items** | Đường dẫn chính xác | Không tự động trùng **/api/items/** trong mặc định MVC 6.x |

Trong **PathPatternParser**, ** không được đặt tùy tiện giữa một mẫu, ví dụ **/resources/**/file.png** là không hợp lệ. Dùng pattern cụ thể hoặc thiết kế đường dẫn khác.

### 3.2. Không còn tự match suffix một cách ngầm định

Từ Spring MVC 5.3, suffix pattern matching kiểu **/person** tự động match **/person.json** đã không còn được bật mặc định. Hãy sử dụng **Accept** để thương lượng media type, hoặc mapping rõ ràng nếu đường dẫn có phần mở rộng thực sự.

Không tự động giả định các route **/api/report**, **/api/report.json**, **/api/report/** và **/api/report//** là tương đương.

## 4. Dấu gạch chéo cuối: /resource và /resource/

Một trailing slash là dấu **/** cuối URL path; nó không giống dấu **/** phân chia segment ở giữa.

Ví dụ:

~~~text
GET /api/products
GET /api/products/
~~~

Với Spring MVC 6.x và một controller chỉ khai báo:

~~~java
@GetMapping("/api/products")
public List<Product> list() {
    // ...
}
~~~

thì URL đầu tiên có handler, còn URL thứ hai **không mặc nhiên** khớp. Tùy cấu hình static resources và error handling, client có thể nhận HTTP 404.

Không có một cách xử lý đúng cho mọi API. Hãy chọn một **canonical URL policy**: URL công khai chính thức là có slash hay không, và ứng dụng phản ứng thế nào khi gặp biến thể còn lại.

### 4.1. Cách A: Khai báo hai route một cách tường minh

Thích hợp khi chỉ có một vài endpoint legacy phải chấp nhận cả hai dạng:

~~~java
@GetMapping({"/api/products", "/api/products/"})
public List<Product> list() {
    // ...
}
~~~

Ưu điểm: rõ ràng, không tạo redirect, hữu ích khi giữ tương thích với một số client cũ.

Hạn chế: khó đồng bộ chính sách nếu có hàng trăm endpoint; cả hai URL vẫn được xử lý trực tiếp, nên cache key, metrics và URL canonization có thể tách đôi. Nếu ứng dụng có Spring Security, hãy đánh giá chính sách phân quyền cho **cả hai URL** thay vì giả định chúng tương đương.

**Không** nên áp dụng hàng loạt bằng cách đặt mỗi phương thức hai mapping mà không có lý do và kiểm thử. Với API mới, ưu tiên một canonical URL nhất quán.

### 4.2. Cách B: Redirect về URL chuẩn

Nếu chọn URL không có slash làm chuẩn, request:

~~~text
GET /api/hello/
~~~

có thể được redirect sang:

~~~text
GET /api/hello
~~~

Một lựa chọn là **HTTP 308 Permanent Redirect**, giúp client giữ nguyên HTTP method và body khi follow redirect. Nó thích hợp khi muốn chuẩn hóa URL lâu dài. Tuy nhiên cần kiểm tra cache, proxy, client HTTP, SDK và behavior khi retry POST/PUT hoặc các thao tác không idempotent. Không được giả định mọi client sẽ tự follow redirect.

Với Spring Framework 6.2, **UrlHandlerFilter** cho phép cấu hình redirect trailing slash. Ví dụ:

~~~java
UrlHandlerFilter filter = UrlHandlerFilter
        .trailingSlashHandler("/api/hello/**")
        .redirect(HttpStatus.PERMANENT_REDIRECT)
        .build();
~~~

Đoạn này dùng các import **org.springframework.web.filter.UrlHandlerFilter** và **org.springframework.http.HttpStatus**; bạn phải đăng ký filter vào Servlet container, không chỉ tạo một biến cục bộ. Phần ví dụ hoàn chỉnh ở mục 8 sẽ làm việc đó.

**Ưu điểm:** có một URL chuẩn cho routing, cache, documentation và chính sách quyền truy cập; client có thể cập nhật URL đang dùng.

**Hạn chế:** redirect tạo thêm một round-trip; cache hoặc proxy có thể giữ redirect lâu; các client không follow redirect cần được điều chỉnh. Không dùng redirect mù quáng nếu HTTP method/body hoặc yêu cầu backward compatibility chưa được xác minh.

### 4.3. Cách C: Rewrite request trước khi HandlerMapping

**UrlHandlerFilter** cũng có chế độ **wrapRequest()** để trình bày URL không có slash cho Spring MVC mà không gửi redirect ra client.

~~~java
UrlHandlerFilter filter = UrlHandlerFilter
        .trailingSlashHandler("/api/hello/**")
        .wrapRequest()
        .build();
~~~

Đây là đoạn minh họa cần được đăng ký như Servlet Filter. Client vẫn gọi URL có slash, nhưng phần xử lý tiếp theo nhìn thấy dạng đã được chuẩn hóa. Do không trả redirect, cách này có thể phù hợp trong một số hệ thống legacy, nhưng cần đặc biệt chú ý **thứ tự Filter và URL-based authorization**.

Khi có **ForwardedHeaderFilter** và Spring Security, filter chuẩn hóa URL nên chạy **sau** khi xử lý forwarded headers đáng tin cậy và **trước** filter bảo mật để Security và MVC cùng nhìn thấy một path. Đây là điều kiện cần kiểm thử, không chỉ là lựa chọn thẩm mỹ.

### 4.4. Vì sao không bật lại implicit trailing slash match?

Spring Framework đã deprecated cách cho nhiều path tự khớp cùng một handler vì có thể gây sai lệch giữa rule phân quyền và mapping MVC. Chẳng hạn Security bảo vệ **/admin** nhưng xử lý **/admin/** theo rule khác trong khi MVC lại coi chúng như nhau. Mô hình an toàn hơn là **URL canonization thống nhất** ở filter/gateway hoặc khai báo mapping cụ thể.

Trên Spring Framework 7.0, tùy chọn trailing slash match cũ đã bị loại bỏ; do đó code mới nên dùng giải pháp có tương lai dài hạn thay vì API deprecated.

## 5. URI encoding không giống character encoding của HTTP body

Một URI có những thành phần riêng:

~~~text
https://example.com/api/items/C%C3%A0%20ph%C3%AA?lang=vi#section
                     |---- path ------------|-- query --| fragment
~~~

**Fragment** sau dấu # thông thường không được gửi tới server. Trong URI path, **/** có ý nghĩa phân chia segment; trong query, **&** và **=** có ý nghĩa đối với dạng key-value.

**Percent-encoding** biến byte thành ký hiệu **%HH**. Với Unicode, thông thường chuyển ký tự thành byte UTF-8 rồi percent-encode các byte cần thiết.

| Đầu vào | Khi dùng làm một path segment | Khi dùng làm query/form value |
|---|---|---|
| **Cà phê** | **C%C3%A0%20ph%C3%AA** | **C%C3%A0+ph%C3%AA** theo form-style |
| **A+B** | **A+B** có thể là ký tự hợp lệ trong path | **A%2BB** để giữ dấu cộng thật |
| **A&B** | **A&B** có thể là dữ liệu segment hợp lệ nhưng nên encode khi cần | **A%26B** để tránh tách parameter |
| **100%** | **100%25** khi mã hóa percent literal | **100%25** |
| **x/y** | Hai segment nếu giữ dấu / thật | Nếu là một giá trị dữ liệu đơn lẻ, xem lưu ý encoded slash |
| **foo#bar** | **foo%23bar** khi # là dữ liệu | **foo%23bar** |

**Không** dùng **URLEncoder.encode** để mã hóa toàn bộ một URI hoặc path: API Java này mã hóa theo quy tắc **application/x-www-form-urlencoded**, trong đó dấu cách biến thành dấu cộng. Dấu cộng trong path không tương đương với dấu cách như khi decode form value.

### 5.1. Xây URI an toàn với UriComponentsBuilder

Khi giá trị là dữ liệu, hãy truyền như một URI template variable để Spring có thể encode theo ngữ cảnh:

~~~java
import org.springframework.web.util.UriComponentsBuilder;

String path = UriComponentsBuilder
        .fromPath("/api/items/{name}")
        .encode()
        .buildAndExpand("Cà phê & trà")
        .toUriString();

System.out.println(path);
~~~

Kết quả kỳ vọng:

~~~text
/api/items/C%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0
~~~

Đây là **đoạn mã minh họa** trong dự án có Spring Web, không phải một file Java độc lập nếu chưa thêm class, imports và dependencies. Trong URL, ký tự **&** được encode vì là **dữ liệu của biến path**, không phải dấu nối query.

Không tự **percent-encode trước** rồi truyền một lần nữa vào builder đang encode; nếu không, dấu % có thể trở thành **%25**, dẫn tới double-encoding. Tương tự, không tự URL-decode lần hai một giá trị **@PathVariable** mà Spring đã binding, vì double-decoding có thể tạo dấu slash hoặc ký tự điều khiển ngoài dự kiến.

### 5.2. Phân biệt @PathVariable và @RequestParam

Với một endpoint:

~~~java
@GetMapping("/api/items/{id}")
public String item(@PathVariable String id) {
    return id;
}
~~~

**@PathVariable** lấy dữ liệu từ một segment trong path. Query parameter dùng **@RequestParam**:

~~~java
@GetMapping("/api/search")
public String search(@RequestParam String q) {
    return q;
}
~~~

Với giá trị tự do có dấu slash, khoảng trắng và ký tự reserved, **query parameter** hoặc JSON request body thường dễ thiết kế hơn path segment vì không xung đột trực tiếp với cấu trúc tuyến đường.

Đặt **server.tomcat.uri-encoding: UTF-8** giúp Tomcat chọn UTF-8 để giải mã URI. Nó không sửa client đã encode URL sai, không ép proxy giữ nguyên path, và không thay thế cấu hình charset của request body.

## 6. Encoded slash %2F và các ký tự nhạy cảm

**%2F** là dấu **/** được percent-encode. Đây không chỉ là vấn đề chữ Việt hay charset: giải mã nó tại thời điểm khác nhau có thể làm thay đổi cấu trúc route.

Ví dụ một mã sản phẩm được nhập là:

~~~text
group/item
~~~

Nếu nhúng nguyên vào một segment URL:

~~~text
/api/items/group/item
~~~

Spring sẽ nhìn thấy **hai segment** sau **/api/items/**, nên mapping **/api/items/{id}** không khớp.

Nếu client gửi:

~~~text
/api/items/group%2Fitem
~~~

thì **Tomcat 10.1 mặc định từ chối encoded solidus trong request path bằng HTTP 400** khi thuộc tính **encodedSolidusHandling** dùng mặc định **reject**. Các connector hoặc proxy khác có thể có chính sách khác. Đừng ghi test giả định rằng %2F luôn được decode thành một ký tự slash trong @PathVariable.

Tomcat có những chế độ xử lý encoded solidus:

| Chế độ connector | Ý nghĩa cơ bản | Rủi ro cần cân nhắc |
|---|---|---|
| **reject** (mặc định Tomcat 10.1) | Từ chối path chứa **%2F** | Tránh sự nhập nhằng path |
| **decode** | Giải mã thành slash | Có thể thay đổi số lượng path segment hoặc cách route |
| **passthrough** | Giữ chuỗi encoded cho tầng sau xử lý | Phải kiểm soát decode ở các tầng tiếp theo và sự thống nhất với proxy |

Đây là **thuộc tính của Tomcat connector**, không phải property MVC chung cho mọi server. Không nên thay đổi chính sách chỉ để một request có URL sai trở nên hợp lệ. Nếu business identifier có slash, giải pháp đơn giản và an toàn hơn là truyền nó trong **query**, **request body**, hoặc ánh xạ sang một ID không có slash.

Những ký tự và mẫu cần chú ý thêm:

- **%5C**: encoded backslash, dễ gây khác biệt giữa hệ điều hành, proxy và backend.
- **%2E** hoặc các segment **.** và **..**: có thể liên quan đến path normalization/traversal.
- **%25**: percent literal đã encode; double-decoding có thể làm phát sinh một escape sequence mới.
- **;**: path parameter/matrix variable; parser và container có quy tắc riêng, không tùy ý loại bỏ hoặc chấp nhận toàn bộ.
- **%00**: NUL hoặc ký tự điều khiển không nên được chấp nhận một cách rộng rãi.
- **//**: dấu slash lặp có thể bị proxy/container chuẩn hóa khác nhau; không dựa vào behavior ngầm định.

**Spring PathPatternParser so khớp theo segment** giúp tránh một số vấn đề của kiểu giải mã toàn bộ path sớm, nhưng nó **không vượt qua được chính sách từ chối của connector hoặc WAF**. Sự hiện diện của PathPatternParser cũng không làm cho mọi encoded slash trở nên an toàn.

### 6.1. Vì sao không mở rộng relaxed-path-chars bừa bãi?

Tomcat có những tùy chọn như **relaxedPathChars**, **relaxedQueryChars** cho một số ký tự trong request-target. Chúng không có chức năng chung là “giải mã lại mọi URL” và không thay thế **encodedSolidusHandling**. Mở rộng tập ký tự được chấp nhận có thể tạo khác biệt với gateway, Spring Security firewall hoặc cache.

Nếu bắt buộc phải hỗ trợ một dạng URI đặc biệt, hãy lập threat model, xác minh hành vi từng tầng, chỉ áp dụng phạm vi hẹp và có integration tests cho path traversal, double encoding, authorization và cache.

## 7. Đường dẫn không khớp không luôn có nghĩa là HTTP 404

**@RequestMapping** có nhiều điều kiện: URL path, HTTP method, request params, headers, **consumes** và **produces**. Một URL path đúng có thể vẫn không chọn được handler phù hợp vì các điều kiện khác.

| Request | Nguyên nhân có thể | HTTP status thường gặp |
|---|---|---|
| **GET /api/items/42** | Mapping GET + path phù hợp | **200**, hoặc response của controller |
| **GET /api/items/42/** | Mapping chỉ khai báo **/{id}**; slash cuối thừa | **404** |
| **GET /api/unknown** | Không có controller/static resource phù hợp | **404** |
| **POST /api/items/42** | Path có handler GET nhưng không cho POST | **405 Method Not Allowed** |
| **POST /api/items** với **Content-Type** sai | Mapping yêu cầu JSON nhưng gửi text/plain | **415 Unsupported Media Type** |
| **GET /api/items** với **Accept** không được hỗ trợ | Mapping/produces không có media type phù hợp | **406 Not Acceptable** |
| **GET /api/items/abc** tới **@PathVariable long id** | Convert sang số thất bại nếu mapping đã được chọn | **400 Bad Request** |
| Request có percent escape lỗi, encoded slash bị chặn | Container hoặc proxy từ chối URI | **400**, đôi khi bị chặn trước Spring |
| Request tới endpoint được bảo vệ | Chưa xác thực hoặc không đủ quyền | **401/403**, phụ thuộc Security |
| URL qua redirect canonical | Có chính sách chuyển hướng | **308** hoặc status redirect đã cấu hình |

Không phải toàn bộ các dòng đều xảy ra trong mọi ứng dụng; status cụ thể còn tùy controller, exception handler, static mappings và cấu hình máy chủ. Bảng dùng để hướng dẫn **chẩn đoán theo tầng**, không để giả lập một giá trị mặc định cho mọi dự án.

### 7.1. NoHandlerFoundException và NoResourceFoundException

Trong Spring Boot Servlet MVC, static content thường được ánh xạ vào **/*** theo nghĩa pattern **/** với wildcard (**/*** ở đây chỉ là cách trình bày văn bản, ký hiệu mapping thực tế là **/ + hai dấu sao**). Vì static resource handler có thể là một handler catch-all, request không khớp controller vẫn có thể được gửi đến **ResourceHttpRequestHandler**. Khi không có file phù hợp, Spring MVC có thể phát sinh **NoResourceFoundException** thay vì **NoHandlerFoundException**.

Để tránh nhầm lẫn về cú pháp, static resource pattern mặc định có thể viết trong code như sau:

~~~text
/**
~~~

Kết luận quan trọng: **không** dựa vào một **@ExceptionHandler(NoHandlerFoundException.class)** đơn lẻ rồi khẳng định nó sẽ xử lý mọi 404. Trong Spring Boot 3.5, nếu không tìm được handler và có static resource mapping mặc định, lỗi thường đi qua cơ chế resource handler.

Nếu ứng dụng là REST-only và chủ động **không phục vụ static resources**, có thể tắt static resource mappings:

~~~yaml
spring:
  web:
    resources:
      add-mappings: false
~~~

Khi đó **NoHandlerFoundException** có thể được dùng rõ ràng hơn cho unmatched routes. Tuy nhiên tắt mapping này cũng ảnh hưởng đến file tĩnh, welcome page hoặc tài nguyên UI nếu dự án đang dùng. Chỉ thay đổi sau khi đánh giá nhu cầu sản phẩm và test.

Một lựa chọn khác là giới hạn mapping tài nguyên tĩnh:

~~~yaml
spring:
  mvc:
    static-path-pattern: /assets/**
~~~

Điều này chỉ đưa static resources vào vùng URL **/assets/**, giảm khả năng static resource handler bắt các request API không tồn tại. Cấu hình lỗi sẽ thay đổi theo kiểu deployment.

### 7.2. 404 được xử lý ở đâu?

**Spring MVC** có resolver và handler cho các lỗi phát sinh trong DispatcherServlet. **Spring Boot** còn có cơ chế lỗi Servlet ở **/error**, nơi status/body có thể khác theo **Accept** và các property error handling. Nếu một container/gateway trả 400/404 trước khi request đến ứng dụng, controller advice sẽ không thấy exception đó.

Đối với API, dùng **ProblemDetail**, **@RestControllerAdvice** hoặc hợp đồng lỗi có cấu trúc và thông điệp an toàn nếu cần. Không trả HTTP 200 kèm JSON báo lỗi “route not found” cho mọi request.

### 7.3. Cấu hình server path và context path

Một URL không khớp cũng có thể do prefix bị thay đổi:

~~~yaml
server:
  servlet:
    context-path: /app
  port: 8081
~~~

Nếu controller ánh xạ **/api/items**, URL thực là:

~~~text
http://localhost:8081/app/api/items
~~~

Không cần đưa **/app** vào mọi **@RequestMapping**; container context path được xử lý ở tầng khác. Tương tự, khi reverse proxy thêm hoặc bỏ **/gateway** prefix, phải xác nhận rule routing trước khi sửa mapping.

**spring.mvc.servlet.path** và prefix mapping của DispatcherServlet có những giới hạn riêng với cơ chế path matching ở một số dòng Boot. Không đổi sang servlet path prefix khi chưa hiểu ảnh hưởng; với nhu cầu thêm tiền tố công khai, cân nhắc context path hoặc gateway routing được cấu hình đúng.

## 8. Ví dụ Spring Boot hoàn chỉnh: route có slash, redirect, query và encoded path

Ví dụ dưới đây dùng Spring Boot **3.5.0**, Java **17** và Maven. Nó minh họa **hai chính sách khác nhau ở các route khác nhau** để so sánh:

- **/api/catalog** và **/api/catalog/** đều khớp vì controller khai báo hai mapping.
- **/api/hello** là canonical URL; **/api/hello/** được một **UrlHandlerFilter** chuyển hướng về URL không có slash.
- **/api/items/{id}** là endpoint dùng path variable; **/api/search?q=...** dùng query parameter.
- **/api/unknown** không có controller; Spring Boot trả 404 theo error handling hiện hành.

### 8.1. Cấu trúc

~~~text
mvc-routing-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/routing/
    │   │   ├── RoutingApplication.java
    │   │   ├── RoutingController.java
    │   │   └── CanonicalUrlConfig.java
    │   └── resources/application.yml
    └── test/java/com/example/routing/
        └── RoutingTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mvc-routing-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Các dependency do Spring Boot quản lý phiên bản, không cần khai báo spring-webmvc hoặc Tomcat riêng. Trong dự án sản xuất, dùng bản vá Spring Boot thuộc nhánh đang được bảo trì và tổ chức phê duyệt.

### 8.3. RoutingApplication.java

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
~~~

### 8.4. RoutingController.java

~~~java
package com.example.routing;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class RoutingController {

    @GetMapping({"/catalog", "/catalog/"})
    public Map<String, String> catalog() {
        return Map.of("result", "catalog");
    }

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "xin chào");
    }

    @GetMapping("/items/{id}")
    public ItemResult item(@PathVariable String id) {
        return new ItemResult(id);
    }

    @GetMapping("/search")
    public QueryResult search(@RequestParam String q) {
        return new QueryResult(q);
    }

    public record ItemResult(String id) {}
    public record QueryResult(String q) {}
}
~~~

Các record là DTO được Jackson serialize thành JSON. Với **@GetMapping("/items/{id}")**, một ID có slash ở giữa không mặc nhiên là một segment hợp lệ. Nếu ID nghiệp vụ chứa slash, ví dụ **team/project**, nên thiết kế API dùng query/body thay vì tự thay đổi connector để chấp nhận encoded slash.

### 8.5. CanonicalUrlConfig.java

~~~java
package com.example.routing;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.web.filter.UrlHandlerFilter;

@Configuration
public class CanonicalUrlConfig {

    @Bean
    public FilterRegistrationBean<UrlHandlerFilter> canonicalSlashFilter() {
        UrlHandlerFilter filter = UrlHandlerFilter
                .trailingSlashHandler("/api/hello/**")
                .redirect(HttpStatus.PERMANENT_REDIRECT)
                .build();

        FilterRegistrationBean<UrlHandlerFilter> registration =
                new FilterRegistrationBean<>(filter);
        registration.addUrlPatterns("/*");
        return registration;
    }
}
~~~

Lưu ý:

- **FilterRegistrationBean** đăng ký UrlHandlerFilter cho Servlet container. Filter chỉ **thực hiện hành vi redirect** trên các path khớp quy tắc cấu hình.
- Pattern **/api/hello/** được dùng để minh họa phạm vi hẹp; route **/api/catalog/** có chính sách riêng, không bị filter này biến đổi.
- Với proxy và Spring Security, phải thiết kế **thứ tự filter** sao cho forwarded headers đáng tin cậy được xử lý trước, và các quyết định authorization nhìn thấy cùng dạng canonical path với MVC. Ví dụ đơn giản này không cài Spring Security hay reverse proxy.
- Nếu muốn chuẩn hóa nhiều endpoint, hãy xác định phạm vi rõ ràng và bổ sung test cho các ngoại lệ; không bật rewrite cho toàn bộ URL mà không đánh giá tác động.

### 8.6. application.yml

~~~yaml
server:
  port: 8080
  tomcat:
    uri-encoding: UTF-8

spring:
  mvc:
    pathmatch:
      matching-strategy: path-pattern-parser
~~~

Hai property này minh họa cấu hình liên quan. Chúng không tự bật optional trailing slash matching; route và filter đã thiết kế xử lý quy tắc đó.

### 8.7. Chạy và thử bằng curl

Trong thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Hoặc build JAR rồi chạy:

~~~bash
mvn clean package
java -jar target/mvc-routing-demo-1.0.0.jar
~~~

**Bài test A – Hai mapping tường minh**

~~~bash
curl -i "http://localhost:8080/api/catalog"
curl -i "http://localhost:8080/api/catalog/"
~~~

Cả hai request mong đợi **HTTP 200** với body:

~~~json
{"result":"catalog"}
~~~

**Bài test B – URL chuẩn và redirect**

~~~bash
curl -i "http://localhost:8080/api/hello"
curl -i "http://localhost:8080/api/hello/"
~~~

URL đầu mong đợi **HTTP 200** với:

~~~json
{"message":"xin chào"}
~~~

URL thứ hai mong đợi **HTTP 308** với header **Location** chỉ đến URL không có slash. Redirect không tự có nghĩa là controller đã được chạy cho request đầu tiên; một client cần gửi tiếp đến canonical URL.

Để kiểm tra client follow redirect:

~~~bash
curl -i -L "http://localhost:8080/api/hello/"
~~~

**Bài test C – Unicode trong path**

~~~bash
curl -i "http://localhost:8080/api/items/C%C3%A0%20ph%C3%AA"
~~~

Nếu connector chấp nhận URI UTF-8 hợp lệ, response mong đợi:

~~~json
{"id":"Cà phê"}
~~~

Không nên lấy test này làm bảo đảm rằng dấu **%2F** cũng được chấp nhận: encoded slash có chính sách riêng.

**Bài test D – Query parameter có ký tự đặc biệt**

~~~bash
curl -i --get \
  --data-urlencode "q=Cà phê & trà" \
  "http://localhost:8080/api/search"
~~~

Response body mong đợi:

~~~json
{"q":"Cà phê & trà"}
~~~

**Bài test E – Route không tồn tại**

~~~bash
curl -i "http://localhost:8080/api/unknown"
~~~

Mong đợi **HTTP 404**. Body phụ thuộc error handler và header Accept, nên không cố định một JSON body khi chưa cấu hình.

**Bài test F – Sai phương thức HTTP**

~~~bash
curl -i -X POST "http://localhost:8080/api/hello"
~~~

Mong đợi **HTTP 405 Method Not Allowed** vì controller chỉ khai báo GET.

**Bài test G – Encoded slash bị từ chối theo mặc định Tomcat**

~~~bash
curl -i "http://localhost:8080/api/items/team%2Fproject"
~~~

Với cấu hình Tomcat 10.1 mặc định, mong đợi request bị từ chối (thường **HTTP 400**) trước khi controller binding path variable. Không điều chỉnh Tomcat chỉ để làm test này trả 200; nó là bằng chứng chính sách an toàn đang hoạt động.

Các lệnh curl nhiều dòng dùng Bash. Trên PowerShell, dùng **curl.exe** trên một dòng với cách escape phù hợp.

## 9. Kiểm thử tự động bằng MockMvc

**MockMvc** kiểm tra mapping, filter được đăng ký trong test context và status của Spring MVC. Tuy nhiên nó **không mở socket Tomcat thật**, nên không thay thế test encoded slash ở mục 8, nơi connector có thể từ chối trước khi Spring được gọi.

Tạo file **src/test/java/com/example/routing/RoutingTest.java**:

~~~java
package com.example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class RoutingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsBothExplicitCatalogRoutes() throws Exception {
        mvc.perform(get("/api/catalog"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("catalog"));

        mvc.perform(get("/api/catalog/"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("catalog"));
    }

    @Test
    void redirectsTrailingSlashOnCanonicalHello() throws Exception {
        mvc.perform(get("/api/hello/"))
                .andExpect(status().isPermanentRedirect());
    }

    @Test
    void respondsOnCanonicalHello() throws Exception {
        mvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("xin chào"));
    }

    @Test
    void retainsUnicodeQueryValue() throws Exception {
        mvc.perform(get("/api/search").param("q", "Cà phê & trà"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.q").value("Cà phê & trà"));
    }

    @Test
    void unknownPathIsNotFound() throws Exception {
        mvc.perform(get("/api/unknown"))
                .andExpect(status().isNotFound());
    }

    @Test
    void wrongMethodIsNotAllowed() throws Exception {
        mvc.perform(post("/api/hello"))
                .andExpect(status().isMethodNotAllowed());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test thành công khi Maven kết thúc với exit code 0. Tổng kết stdout của plugin test có thể thay đổi theo phiên bản; không nên dựa vào một chuỗi log cố định.

**Phân biệt phạm vi test:** MockMvc phù hợp cho route và exception resolver của Spring MVC, nhưng phải có integration test với **embedded Tomcat thật** hoặc môi trường gateway để đánh giá encoded slash, request-target không hợp lệ, reverse proxy rewrite và chính sách firewall. Thứ tự filter trong môi trường có Spring Security cũng cần được xác nhận thực tế.

## 10. Chẩn đoán 404, 400 và các lỗi path matching theo quy trình

Khi một URL không trả về controller mong đợi, hãy theo thứ tự sau:

1. **Ghi lại HTTP request thực:** method, URL chính xác (bao gồm trailing slash, percent escapes), Host, query, Content-Type, Accept và status. Dùng **curl -i** hoặc **curl -v** và kiểm tra log proxy.
2. **Xác nhận request đến backend chưa:** nếu bị chặn tại ingress/WAF/Tomcat, Spring MVC mapping không có cơ hội xử lý.
3. **Kiểm tra context path và proxy prefix:** URL ngoài gateway có thể khác URL mà DispatcherServlet nhìn thấy.
4. **Kiểm tra dạng canonical:** **/resource** và **/resource/** có được khai báo riêng hoặc có redirect filter không?
5. **Kiểm tra encoded characters:** **%2F**, **%25**, dấu +, Unicode và escaped reserved characters có được client tạo đúng không?
6. **Kiểm tra mapping annotation:** class-level + method-level path, HTTP method, params, headers, consumes, produces, regex path variable và các đường dẫn wildcard.
7. **Kiểm tra chiến lược matching:** PathPatternParser mặc định, pattern có hợp lệ và specificity có gây trúng handler khác không?
8. **Kiểm tra static resources:** có handler **/** wildcard bao phủ đường dẫn và tạo NoResourceFoundException không?
9. **Kiểm tra security/filter:** có rule phân quyền khác nhau cho URL canonical và URL có slash không?
10. **Viết test tái hiện:** một test MVC mapping, một test HTTP thật với Tomcat và một test qua proxy nếu production có gateway.

### 10.1. Dùng Actuator để nhìn mapping thực tế

Trong môi trường cho phép quan sát, có thể thêm **spring-boot-starter-actuator** và kiểm tra endpoint **mappings** để biết các handler đã đăng ký. Endpoint này **không nên được công khai ra Internet**; chỉ expose qua mạng quản trị/điểm kiểm soát truy cập phù hợp.

Ví dụ bật trong môi trường phát triển nội bộ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,mappings
~~~

Kiểm tra đường dẫn actuator theo cấu hình ứng dụng và bảo vệ endpoint mapping. Nó cho biết route đăng ký, nhưng không thay thế kiểm tra URL sau proxy hoặc chính sách container.

### 10.2. Logging chẩn đoán có kiểm soát

Có thể tạm bật log ở môi trường dev:

~~~yaml
logging:
  level:
    org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping: TRACE
    org.springframework.web.servlet.DispatcherServlet: DEBUG
~~~

Các logger này hữu ích để điều tra handler mapping; không bật TRACE kéo dài trong production hoặc ghi lại URL chứa token, thông tin nhạy cảm nếu chưa có chính sách ẩn dữ liệu.

### 10.3. Không thể dùng @ExceptionHandler để sửa mọi URL

**@RestControllerAdvice** có thể chuẩn hóa body của các lỗi Spring MVC sau khi request được giao cho framework. Nhưng URL chưa đến backend, Tomcat trả 400, WAF chặn hoặc Spring Security filter từ chối request thì ControllerAdvice không tự động can thiệp.

Nếu cần thống nhất error JSON cho tất cả các tầng, phải có thiết kế error contract tại proxy, security filter và backend, chứ không đặt mọi trách nhiệm vào một advice.

## 11. Bảo mật: canonical path phải nhất quán với authorization

Đường dẫn có thể được diễn giải khác nhau giữa:

- CDN/gateway và backend.
- Spring Security matcher và Spring MVC HandlerMapping.
- Servlet container và filter tùy chỉnh.
- Request đầu tiên và đường dẫn sau redirect/rewrite.

Ví dụ, nếu rule bảo vệ **/admin** nhưng không bảo vệ **/admin/**, một thiết lập MVC cho phép hai đường dẫn vào cùng controller có thể gây sai lệch quyền truy cập. Đó là lý do Spring khuyến khích chuẩn hóa đường dẫn một cách rõ ràng.

Các nguyên tắc:

1. Chọn URL canonical cho endpoint, cập nhật tài liệu API và link generation.
2. Nếu hỗ trợ trailing slash, định nghĩa chính sách redirect/rewrite ở đúng vị trí so với Spring Security.
3. Không đổi thuộc tính connector cho encoded slash/backslash nếu chưa đánh giá path traversal và bypass authorization.
4. Không double URL-decode; một chuỗi percent đã decode lại có thể tạo cấu trúc path mới.
5. Không tin mù quáng **X-Forwarded-\*** từ Internet; chỉ nhận header do trusted proxy đặt lại.
6. Kiểm thử đối chiếu **/admin**, **/admin/**, **/admin%2F**, dấu slash lặp và các biến thể chữ hoa/thường khi rule security phụ thuộc path.
7. Không tự động chuyển mọi request lạ về một endpoint hợp lệ; lỗi 404 có giá trị để phát hiện sai route và giúp phân tách namespace API.
8. Chỉ mở rộng route patterns đúng nhu cầu nghiệp vụ, không dùng wildcard quá rộng để “bắt tất cả” nhằm né lỗi không khớp.

Đối với API public, chuyển hướng **308** thường rõ ràng hơn về canonical URL so với rewrite âm thầm, nhưng việc lựa chọn phải dựa vào khả năng follow redirect của client và hợp đồng API đang được hỗ trợ.

## 12. Bảng lỗi và hướng khắc phục nhanh

| Triệu chứng | Nguyên nhân điển hình | Biện pháp ưu tiên |
|---|---|---|
| **/api/items** trả 200, **/api/items/** trả 404 | Trailing slash không auto-match | Chọn canonical URL; khai báo hai route hoặc UrlHandlerFilter |
| Trailing slash trả 308 nhưng client báo lỗi | Client không follow redirect, gateway/cache giữ redirect | Cập nhật URL client và chính sách redirect |
| Có dấu tiếng Việt trong path bị sai | Client/proxy encode không đúng UTF-8 | Kiểm tra URI percent-encoding, **server.tomcat.uri-encoding** |
| **%2F** trả 400 | Tomcat/WAF từ chối encoded slash | Dùng query/body cho ID có slash; không nới lỏng connector tùy tiện |
| **A+B** trong query thành **A B** | Dấu + chưa encode thành %2B theo form-style | Dùng URI builder hoặc data-urlencode |
| Path đúng nhưng trả 405 | HTTP method không phù hợp | Sửa method client hoặc mapping rõ ràng |
| POST JSON trả 415 | Content-Type không khớp consumes | Đặt Content-Type, kiểm tra mapping |
| GET trả 406 | Accept không tương thích produces | Điều chỉnh Accept/media type |
| **/api/123** không vào @GetMapping có regex ID | Input không khớp regex của PathPattern | Kiểm tra constraint và mẫu |
| 404 không vào NoHandlerFoundException | Static resource /** bắt request trước | Kiểm tra **NoResourceFoundException** hoặc đổi static path pattern |
| Test MockMvc thành công, production lỗi | Proxy/Tomcat normalization hoặc Security filter khác biệt | Test HTTP thật và qua gateway |
| 404 chỉ xảy ra sau đổi context path | URL client thiếu prefix | Kiểm tra **server.servlet.context-path** và route proxy |
| Handler bắt nhầm endpoint khác | Wildcard quá rộng hoặc mapping specificity | Dùng pattern chính xác hơn, xem Actuator mappings |
| 403 chỉ xuất hiện với URL có slash | Authorization matcher và MVC diễn giải khác nhau | Chuẩn hóa trước Security, kiểm thử toàn bộ variant |

## 13. Checklist trước khi đưa lên production

- [ ] Xác định phiên bản Spring Boot/Spring Framework/Tomcat và chiến lược path matching thực tế.
- [ ] Công bố một canonical URL policy cho trailing slash, kèm trạng thái redirect nếu có.
- [ ] Đảm bảo client HTTP/SDK tạo URI từng thành phần bằng URI builder đúng quy tắc.
- [ ] Đặt UTF-8 cho URI encoding, test non-ASCII và dấu cộng trong query/form.
- [ ] Không giải mã URL hai lần, không bật encoded slash mặc định để chữa lỗi routing.
- [ ] Kiểm tra path matching cho HTTP method, params, headers, consumes, produces và wildcard.
- [ ] Kiểm tra đường dẫn static resources và phân biệt NoHandlerFoundException với NoResourceFoundException.
- [ ] Kiểm tra Filter order và Security matchers với URL có/không có slash.
- [ ] Có test MockMvc **và** test qua Tomcat/gateway cho encoded slash, percent và path normalization.
- [ ] Log và metrics phân biệt 400/404/405/308 mà không làm lộ URL nhạy cảm.
- [ ] Chỉ expose Actuator mappings ở phạm vi bảo vệ thích hợp.
- [ ] Duy trì tài liệu API và kế hoạch migration khi thay đổi canonical URL.

## 14. Tài liệu tham khảo chính thức

1. Spring Framework 6.2 – Path Matching: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-path.html
2. Spring Framework 6.2 – Mapping Requests và PathPattern: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html
3. Spring Framework 6.2 – Filters và UrlHandlerFilter: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
4. Spring Framework 6.2 – URI Links / Encoding: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-uri-building.html
5. Spring Boot 3.5 – Servlet Web Applications, Path Matching và NoHandlerFoundException: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
6. Spring Boot 3.5 – Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
7. Apache Tomcat 10.1 – HTTP Connector, encodedSolidusHandling/URIEncoding: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
8. RFC 3986 – URI Generic Syntax: https://www.rfc-editor.org/rfc/rfc3986
9. Spring Security – HTTP Firewall: https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html

**Kết luận:** xử lý đúng trailing slash, encoded characters và unmatched paths đòi hỏi phân định ranh giới của **client → proxy → Servlet container → Filter/Security → Spring MVC HandlerMapping**. Spring MVC 6.x không tự coi **/resource/** tương đương **/resource**. Dùng canonical URL và UrlHandlerFilter hoặc khai báo hai mapping có chủ đích; để URI builder mã hóa dữ liệu theo đúng thành phần; giữ chính sách connector an toàn; và chẩn đoán 400/404/405 theo đúng tầng phát sinh. Luôn kiểm thử cả Spring MVC và đường đi HTTP thực tế.
