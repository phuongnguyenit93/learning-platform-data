# Xử lý proxy, gateway và forwarded headers với Spring REST Docs

## 1. Vì sao URI phía ứng dụng khác URI client nhìn thấy?

Trong production, client thường kết nối qua CDN, load balancer, API gateway hoặc reverse proxy:

```text
Client
  |
  | https://api.example.com/public/v1/orders/42
  v
Edge proxy / API gateway
  |
  | http://orders-service:8080/orders/42
  v
Spring application
```

Proxy có thể kết thúc TLS, đổi hostname/port, thêm path prefix hoặc chuyển request đến service nội bộ. Ứng dụng có thể nhận kết nối HTTP từ `orders-service:8080` trong khi client dùng URI `https://api.example.com/public/v1/orders/42`.

Nếu ứng dụng dùng request URL để tạo link, redirect hoặc absolute URL trong response, nó cần biết thông tin gốc mà proxy quan sát được. Proxy thường truyền thông tin qua header chuẩn `Forwarded` (RFC 7239) hoặc nhóm `X-Forwarded-*` như `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Forwarded-Port`, `X-Forwarded-For` và `X-Forwarded-Prefix`.

Spring REST Docs ghi nhận HTTP operation từ MockMvc, WebTestClient hoặc REST Assured. Khi test và cấu hình proxy không khớp, snippet có thể lộ host nội bộ, dùng sai scheme hoặc thiếu public path prefix. Bài này thuộc chương **URI configuration** của module **SPRING_REST_DOCS**, giúp tạo tài liệu REST API có thể kiểm chứng từ HTTP tests, sinh snippet request/response/payload/headers và biên soạn Asciidoctor/Markdown trong build/CI.

Sau bài học, bạn có thể hiểu các forwarded headers, chọn strategy trong Spring Boot, cấu hình Framework filter/transformer, bảo vệ ứng dụng trước spoofing và kiểm thử URL/snippet khi chạy sau gateway.

## 2. Các forwarded headers thường gặp

### 2.1. Header chuẩn Forwarded

RFC 7239 định nghĩa header `Forwarded`. Proxy có thể thêm thông tin client-facing connection:

```http
Forwarded: for=203.0.113.10;proto=https;host=api.example.com
```

| Tham số | Ý nghĩa |
| --- | --- |
| `for` | Địa chỉ client được proxy quan sát |
| `by` | Địa chỉ proxy tạo header |
| `proto` | Scheme phía client, thường là http hoặc https |
| `host` | Authority phía client, có thể kèm port |

Header có thể có nhiều phần tử nếu request đi qua nhiều proxy. Không nên tự lấy phần tử đầu/cuối nếu chưa xác định proxy nào tạo ra từng giá trị.

### 2.2. Nhóm X-Forwarded-*

| Header | Mục đích |
| --- | --- |
| `X-Forwarded-For` | Địa chỉ client hoặc chuỗi địa chỉ qua proxy |
| `X-Forwarded-Host` | Host mà client sử dụng |
| `X-Forwarded-Proto` | Scheme phía client |
| `X-Forwarded-Port` | Port phía client |
| `X-Forwarded-Prefix` | Prefix public mà proxy thêm vào route |
| `X-Forwarded-Ssl` | Chỉ báo SSL được một số proxy sử dụng |

Ví dụ:

```http
X-Forwarded-For: 203.0.113.10
X-Forwarded-Host: api.example.com
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /public/v1
```

Không phải mọi proxy đều gửi đủ các header. Hãy xác minh cấu hình gateway thực tế và tài liệu web server, không mặc định mọi trường đều có mặt.

## 3. Chọn forwarded-header strategy trong Spring Boot

Spring Boot cung cấp thuộc tính `server.forward-headers-strategy`:

| Giá trị | Hành vi |
| --- | --- |
| `NONE` | Không chủ động diễn giải forwarded headers bằng strategy của Boot |
| `NATIVE` | Dùng khả năng xử lý proxy của web server đang chạy, nếu server hỗ trợ |
| `FRAMEWORK` | Dùng Spring Framework support: `ForwardedHeaderFilter` cho Servlet hoặc `ForwardedHeaderTransformer` cho Reactive |

Ví dụ:

```yaml
server:
  forward-headers-strategy: FRAMEWORK
```

Chọn theo kiến trúc:

- `NATIVE` khi web server được cấu hình đúng và hỗ trợ các header proxy đang gửi.
- `FRAMEWORK` khi cần hành vi của Spring Framework hoặc native support không đáp ứng.
- `NONE` khi ứng dụng không cần forwarded headers hoặc việc diễn giải được quản lý ở lớp khác.

Default strategy có thể phụ thuộc môi trường triển khai/nền tảng cloud được hỗ trợ. Hãy đặt giá trị rõ ràng theo profile deploy thay vì dựa vào default chưa xác minh. Xem [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html).

## 4. Spring Framework filter và transformer

### 4.1. Servlet stack

Với Spring MVC/Servlet, `ForwardedHeaderFilter` bọc request để API servlet nhìn thấy scheme, host và port đã được điều chỉnh từ forwarded headers. Filter cũng loại các header này khỏi request wrapper để tránh chúng tiếp tục ảnh hưởng đến thành phần phía sau.

Trong Spring Boot có thể chọn:

```properties
server.forward-headers-strategy=framework
```

Nếu tự đăng ký filter, đặt nó trước các filter cần đọc request đã chỉnh sửa, ví dụ `RequestContextFilter`. Với đăng ký thủ công, xem xét dispatcher types `REQUEST`, `ASYNC` và `ERROR` nếu ứng dụng dùng async/error dispatch.

### 4.2. Reactive stack

Với WebFlux, Spring Framework dùng `ForwardedHeaderTransformer` thay cho Servlet filter. Spring Boot cũng có thể cấu hình qua `server.forward-headers-strategy=framework`. Không đăng ký Servlet filter trong reactive stack; dùng cơ chế phù hợp với stack.

### 4.3. Chế độ remove-only

`ForwardedHeaderFilter` hỗ trợ chế độ `removeOnly`. Khi bật chế độ này, filter loại forwarded headers khỏi request thay vì dùng chúng để sửa request URL. Cách này hữu ích khi ứng dụng không nên diễn giải các giá trị forwarded không được tin cậy. Không kết hợp nhiều lớp cùng diễn giải forwarded headers một cách không chủ đích.

## 5. Ranh giới tin cậy và forwarded header spoofing

Forwarded headers là dữ liệu do proxy đáng tin cậy tạo ra. Client độc hại có thể tự gửi:

```http
GET /account HTTP/1.1
Host: internal-service:8080
Forwarded: proto=https;host=attacker.example
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
```

Nếu application tin các header này dù request không đi qua proxy đáng tin cậy, attacker có thể tác động absolute URL, redirect, link hoặc quyết định bảo mật dựa trên host/scheme.

### 5.1. Proxy tại edge phải xóa hoặc ghi đè header đầu vào

Proxy ở ranh giới tin cậy cần:

1. Xóa cả `Forwarded` và `X-Forwarded-*` do client gửi vào.
2. Tự tạo lại header dựa trên kết nối mà proxy thực sự quan sát.
3. Chỉ chuyển header do proxy tin cậy tạo đến application.
4. Giữ danh sách trusted proxies ở mức tối thiểu cần thiết.

Phải xử lý cả hai họ header. Nếu chỉ xóa `Forwarded` nhưng vẫn chuyển `X-Forwarded-Host`, hoặc ngược lại, application vẫn có thể nhận giá trị giả mạo. Spring Framework và Spring Security đều nhấn mạnh forwarded headers chỉ nên đến từ proxy được kiểm soát. Xem [Spring Framework — Forwarded headers and security considerations](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html) và [Spring Security — HTTP security considerations](https://docs.spring.io/spring-security/reference/features/exploits/http.html).

### 5.2. Tomcat native proxy handling

Với Tomcat, native support có thể dựa trên `RemoteIpValve`. Spring Boot cho phép cấu hình header và trusted proxy pattern:

```yaml
server:
  forward-headers-strategy: NATIVE
  tomcat:
    remoteip:
      remote-ip-header: x-forwarded-for
      protocol-header: x-forwarded-proto
      internal-proxies: "10\\.0\\.\\d{1,3}\\.\\d{1,3}"
```

Regex chỉ minh họa một dải IP; phải thay bằng địa chỉ/range proxy thực tế. Không cấu hình tin mọi proxy hoặc để internal-proxies rỗng trong production. Cách xử lý native khác nhau theo web server. Xem [Spring Boot — Customize Tomcat proxy configuration](https://docs.spring.io/spring-boot/how-to/webserver.html).

## 6. Gateway thêm public prefix

Ví dụ:

```text
Public URL:
https://api.example.com/store/v2/orders/42

Backend URL:
http://orders-service:8080/orders/42
```

Gateway gửi:

```http
Forwarded: proto=https;host=api.example.com
X-Forwarded-Prefix: /store/v2
```

Public prefix không nhất thiết giống context path backend. Khi Framework xử lý prefix, ứng dụng có thể tạo link theo external path. Hãy kiểm tra proxy gửi prefix nào và cấu hình filter/transformer thực sự hỗ trợ nó.

Không tự thêm `/store/v2` vào cả application context path và forwarded prefix nếu điều đó làm prefix xuất hiện hai lần. Cũng không chỉ sửa host/scheme trong Spring REST Docs rồi kết luận path đã đúng; snippet chỉ đúng khi path test ghi nhận phù hợp public contract.

## 7. Kiểm thử forwarded headers bằng MockMvc

Controller minh họa tạo URI tuyệt đối dựa trên request:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

record LinkResponse(String self) {}

@RestController
class OrderLinkController {
    @GetMapping("/orders/42")
    LinkResponse order() {
        String self = ServletUriComponentsBuilder.fromCurrentRequest()
                .build().toUriString();
        return new LinkResponse(self);
    }
}
```

Chỉ thêm header vào MockMvc không tự chứng minh chúng đã được xử lý. Test phải chạy qua đúng `ForwardedHeaderFilter` hoặc cấu hình proxy handling mà ứng dụng sử dụng. `standaloneSetup` cần đăng ký filter tường minh nếu muốn kiểm tra filter.

Ví dụ đăng ký filter trong test Servlet:

```java
import org.springframework.web.filter.ForwardedHeaderFilter;

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderLinkController())
        .addFilters(new ForwardedHeaderFilter())
        .build();
```

Request test:

```java
mockMvc.perform(get("/orders/42")
        .header("Forwarded", "proto=https;host=api.example.com")
        .header("X-Forwarded-Prefix", "/store/v2"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.self")
        .value("https://api.example.com/store/v2/orders/42"));
```

Giá trị mong đợi phụ thuộc cách filter được cấu hình để xử lý `X-Forwarded-Prefix`. Nếu prefix không được bật/hỗ trợ trong cấu hình thực tế, test cần điều chỉnh theo behavior đúng. Nếu chọn native strategy, hãy kiểm thử native container/configuration trong integration test thay vì thêm Framework filter song song.

## 8. Spring REST Docs ghi nhận URI nào?

Spring REST Docs ghi lại operation mà test client gửi. Nó không tự phát hiện cấu hình gateway production và không tự biết public authority nếu request test không mang thông tin đó.

### 8.1. Kiểm thử qua gateway test

Nếu pipeline có gateway/test ingress tương đương production:

- Gửi request qua hostname/path public của gateway.
- Gateway tạo forwarded headers theo quy tắc deploy.
- Application xử lý forwarded headers như production.
- REST Docs sinh snippet từ request thực tế qua gateway.

Đây là cách kiểm tra end-to-end route, prefix và TLS termination, nhưng cần môi trường test ổn định.

### 8.2. Test backend trực tiếp và cấu hình URI snippet

Nếu test gọi thẳng backend, có thể dùng URI defaults hoặc `modifyUris()` để hiển thị public scheme/host/port. Tuy nhiên, cách này chỉ sửa URI snippet. Nó không kiểm tra gateway có expose path đó không, proxy có tạo header đúng không, link/redirect có đúng không hoặc prefix có bị mất/lặp không.

Vì vậy, test backend trực tiếp phù hợp với kiểm thử service/contract; thêm integration test qua gateway nếu public routing là phần quan trọng của contract.

## 9. Document request/response và forwarded headers

Thông thường, `Forwarded`, `X-Forwarded-Host` và `X-Forwarded-Proto` là metadata giữa proxy và application. Không trình bày chúng như header mà client API thông thường phải tự đặt, trừ khi API thực sự yêu cầu.

Ví dụ Spring REST Docs chỉ document header public của operation:

```java
document("order-detail",
    requestHeaders(
        headerWithName("Accept")
            .description("Media type response client chấp nhận")
    ),
    responseFields(
        fieldWithPath("id").description("Mã đơn hàng"),
        fieldWithPath("self").description("URI public của đơn hàng")
    )
)
```

Nếu cần test forwarded headers, đưa chúng vào test setup hoặc fixture của integration test nhưng không nhất thiết đưa vào `requestHeaders(...)` trong tài liệu public. Tài liệu client nên mô tả những gì client phải gửi; forwarded headers thuộc trách nhiệm hạ tầng proxy.

## 10. WebTestClient và REST Assured

Header chỉ được xử lý nếu request đi qua application stack đã đăng ký forwarded-header support.

### 10.1. WebTestClient

Có thể thêm header vào request test:

```java
webTestClient.get()
        .uri("/orders/42")
        .header("Forwarded", "proto=https;host=api.example.com")
        .header("X-Forwarded-Prefix", "/store/v2")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.self")
        .isEqualTo("https://api.example.com/store/v2/orders/42");
```

Test chỉ kiểm tra forwarded behavior nếu WebTestClient đi qua WebFlux transformer/filter tương ứng. Cấu hình bind-to-controller riêng lẻ có thể không phản ánh toàn bộ production filter chain; chọn integration setup phù hợp khi cần xác minh pipeline thật.

### 10.2. REST Assured

REST Assured cũng có thể gửi forwarded headers:

```java
given()
        .header("Forwarded", "proto=https;host=api.example.com")
        .header("X-Forwarded-Prefix", "/store/v2")
        .when()
        .get("/orders/42")
        .then()
        .statusCode(200)
        .body("self", equalTo(
                "https://api.example.com/store/v2/orders/42"));
```

Không dùng header này trong request client public trừ khi contract yêu cầu. Ở test, chúng đại diện cho header mà proxy đáng tin cậy gửi đến backend; integration test qua proxy thật tốt hơn khi cần kiểm chứng cách proxy xóa/ghi đè giá trị đầu vào.

## 11. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Link/redirect dùng http dù client gọi HTTPS | Application không diễn giải X-Forwarded-Proto hoặc Forwarded | Cấu hình NATIVE/FRAMEWORK phù hợp và kiểm tra proxy |
| URL response lộ hostname service nội bộ | Host forwarded thiếu hoặc không được tin cậy/xử lý | Kiểm tra Forwarded/X-Forwarded-Host ở gateway |
| Public prefix bị mất | Gateway không gửi prefix hoặc application không áp dụng | Xác minh X-Forwarded-Prefix và cấu hình stack |
| Public prefix xuất hiện hai lần | Prefix đã nằm trong context path và lại được cộng từ proxy | Chọn một nguồn path và test external URI |
| Host response do client tự gửi quyết định | Proxy không xóa/ghi đè forwarded headers đầu vào | Sửa trust boundary; lọc cả hai họ header |
| MockMvc test nhận header nhưng URL không đổi | Test không đăng ký filter hoặc transformer | Dùng application context/filter chain đúng |
| Filter làm sai URL ở async/error dispatch | Filter mapping thiếu dispatcher type | Kiểm tra REQUEST, ASYNC, ERROR mapping |
| Docs ghi URI khác production | Chỉ dùng modifyUris() mà không test proxy behavior | Bổ sung integration test qua gateway |

## 12. Tích hợp vào Spring REST Docs và CI

Một pipeline đáng tin cậy nên có các lớp kiểm tra:

1. **Unit/integration validation:** test proxy header parsing và URL generation trong Spring stack.
2. **Gateway integration:** xác nhận proxy xóa header client gửi vào và tạo lại header đáng tin cậy.
3. **REST Docs tests:** sinh snippet request/response, bao gồm URI hoặc Location nếu có trong contract.
4. **Asciidoctor/Markdown build:** include snippet vừa sinh và render tài liệu.
5. **URL scan:** tìm localhost, hostname backend, port nội bộ và prefix sai trong tài liệu public.

Ví dụ build Gradle khi task đã được cấu hình:

```bash
./gradlew test asciidoctor
```

Ví dụ scan snippet:

```bash
grep -RniE 'localhost|127\\.0\\.0\\.1|orders-service:8080|http://.*internal' build/generated-snippets
```

Kết quả scan cần được review theo ngữ cảnh; test fixture/hướng dẫn local có thể chứa địa chỉ nội bộ có chủ đích. CI nên giới hạn scan vào artifact public docs thay vì cấm mọi occurrence trong toàn repository.

Nếu ứng dụng chạy phía sau proxy, strategy phải nhất quán giữa các profile deploy. Không để profile production tin mọi header trong khi gateway chưa lọc giá trị do client gửi.

## 13. Bài tập thực hành

Một gateway public route:

```text
https://shop.example.com/api/v2/orders/42
```

Backend route:

```text
http://order-service:8080/orders/42
```

Gateway thêm:

```http
Forwarded: proto=https;host=shop.example.com
X-Forwarded-Prefix: /api/v2
```

Hãy thực hiện:

1. Cấu hình Spring Boot với `server.forward-headers-strategy` phù hợp cho Servlet hoặc Reactive stack.
2. Viết endpoint trả absolute self link dựa trên request hiện tại.
3. Viết test gửi forwarded headers và xác nhận link có HTTPS, public host và prefix đúng.
4. Thêm test spoofing: client gửi `Forwarded` và `X-Forwarded-*` giả; xác minh proxy edge xóa/ghi đè các header đó trước khi request đến backend.
5. Chạy integration test qua gateway test để kiểm tra route và prefix thật.
6. Sinh snippet Spring REST Docs và kiểm tra URI/Location trong output.
7. Render Asciidoctor và thêm scan hostname nội bộ vào CI.

**Tiêu chí hoàn thành:** Application tạo public URI đúng trong cấu hình tin cậy; forwarded headers từ client không thể tự quyết định host/scheme; test bao phủ path prefix và response links; REST Docs snippet không làm người tích hợp gọi nhầm host backend.

## 14. Ghi nhớ

Proxy/gateway có thể thay đổi host, scheme, port và path trước khi request đến Spring application. `Forwarded` và `X-Forwarded-*` truyền thông tin gốc để ứng dụng tạo URL, redirect và link chính xác. Trong Spring Boot, chọn `NONE`, `NATIVE` hoặc `FRAMEWORK` theo web server/stack; Servlet dùng `ForwardedHeaderFilter`, Reactive dùng `ForwardedHeaderTransformer`. Chỉ tin header do proxy kiểm soát: edge proxy phải xóa hoặc ghi đè cả hai nhóm header từ client. Dùng test HTTP để xác minh URL sinh ra và Spring REST Docs để ghi lại contract; chỉ thay host trong snippet không thay thế kiểm thử routing và trust boundary của gateway.

### Tài liệu tham khảo

- [Spring Boot — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Spring Security — HTTP Security Considerations](https://docs.spring.io/spring-security/reference/features/exploits/http.html)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
