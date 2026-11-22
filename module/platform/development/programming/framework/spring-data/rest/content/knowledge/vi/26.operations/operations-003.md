# Forwarded header, HTTPS và tính đúng đắn của liên kết tuyệt đối trong Spring Data REST

## Mục tiêu

Khi Spring Data REST chạy sau reverse proxy hoặc load balancer, request đến ứng dụng thường không còn giữ nguyên thông tin mà client nhìn thấy. Client có thể gọi:

~~~text
https://api.example.com/api/products
~~~

nhưng proxy chuyển tiếp tới:

~~~text
http://10.0.0.12:8080/products
~~~

Nếu ứng dụng chỉ nhìn request nội bộ, các liên kết HAL như `_links.self.href`, `_links.profile.href`, hoặc header `Location` sau khi tạo tài nguyên có thể chứa `http`, hostname nội bộ, port `8080`, hoặc thiếu path prefix công khai. Client bên ngoài không thể dùng các URL đó một cách đáng tin cậy.

Spring Data REST tạo các liên kết dựa trên request hiện tại. Để tạo URL tuyệt đối đúng với góc nhìn bên ngoài, proxy cần truyền thông tin gốc qua forwarded headers và ứng dụng phải được cấu hình để tin cậy, xử lý các header đó.

## 1. Các forwarded header quan trọng

Có hai nhóm header phổ biến:

- Header chuẩn RFC 7239: `Forwarded`.
- Nhóm header phổ biến theo quy ước: `X-Forwarded-*`.

Ví dụ header chuẩn:

~~~http
Forwarded: for=203.0.113.10;proto=https;host=api.example.com
~~~

Ví dụ nhóm `X-Forwarded-*`:

~~~http
X-Forwarded-For: 203.0.113.10
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
X-Forwarded-Port: 443
X-Forwarded-Prefix: /api
~~~

Ý nghĩa thường gặp:

| Header | Thông tin được khôi phục |
| --- | --- |
| `Forwarded` | Các thuộc tính như `proto`, `host`, `for` trong một header chuẩn |
| `X-Forwarded-Proto` | Scheme công khai, ví dụ `https` |
| `X-Forwarded-Host` | Host công khai, ví dụ `api.example.com` |
| `X-Forwarded-Port` | Port công khai, ví dụ `443` |
| `X-Forwarded-Prefix` | Prefix URL công khai mà proxy đã thêm, bỏ hoặc thay thế |
| `X-Forwarded-For` | Địa chỉ client gốc; thường phục vụ log và kiểm soát truy cập, không quyết định scheme/host của link |

Spring Framework hỗ trợ cả `Forwarded` và `X-Forwarded-*`. Các header `X-Forwarded-Host`, `X-Forwarded-Port`, `X-Forwarded-Proto` và `X-Forwarded-Prefix` là quy ước phổ biến, không phải header chuẩn RFC 7239.

## 2. Vì sao link Spring Data REST bị sai sau proxy?

Spring Data REST là ứng dụng Spring MVC và thường trả representation HAL có các link tuyệt đối. Ví dụ một response khi chạy trực tiếp ở máy local có thể chứa:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/products"
    }
  }
}
~~~

Trong môi trường production, client cần URL công khai:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/products"
    }
  }
}
~~~

Proxy thay đổi scheme, host, port hoặc path trên đường chuyển tiếp. Spring Framework có thể khôi phục các thông tin ban đầu từ forwarded headers trước khi Spring Data REST/Spring HATEOAS tạo link. Với Servlet stack, thành phần chính là `ForwardedHeaderFilter`; với WebFlux, thành phần tương ứng là `ForwardedHeaderTransformer`.

Nếu không bật xử lý forwarded headers, request có thể được nhìn nhận như `http://10.0.0.12:8080`, dù client thực sự gọi HTTPS ở `api.example.com`.

## 3. Cấu hình Spring Boot

Với Spring Boot hiện hành, chọn `server.forward-headers-strategy` theo khả năng của môi trường:

| Giá trị | Ý nghĩa |
| --- | --- |
| `NATIVE` | Dùng hỗ trợ forwarded headers của web server/container đang chạy. Hành vi cụ thể phụ thuộc Tomcat, Jetty hoặc Undertow. |
| `FRAMEWORK` | Dùng hỗ trợ của Spring Framework; Servlet stack xử lý bằng `ForwardedHeaderFilter`. |
| `NONE` | Bỏ qua forwarded headers. |

Nếu cần Spring Framework xử lý đầy đủ host, port, scheme và prefix, có thể cấu hình:

~~~properties
server.forward-headers-strategy=FRAMEWORK
~~~

Hoặc YAML:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Spring Boot dùng cấu hình này để cài cơ chế forwarded-header phù hợp với web stack. Nếu proxy chỉ gửi các header thông dụng như `X-Forwarded-For` và `X-Forwarded-Proto`, `NATIVE` có thể đủ khi container hỗ trợ chúng. Khi cần thêm `X-Forwarded-Host`, `X-Forwarded-Port` hoặc `X-Forwarded-Prefix`, kiểm tra khả năng của container; chọn `FRAMEWORK` nếu cần xử lý của Spring.

Đừng dựa vào giá trị mặc định: Spring Boot có thể chọn `NATIVE` trên một số cloud platform được hỗ trợ và `NONE` trong các môi trường khác. Hãy cấu hình rõ ràng theo deployment.

Nếu dùng Tomcat và TLS kết thúc ở proxy, Spring Boot lưu ý có thể cần:

~~~properties
server.tomcat.redirect-context-root=false
~~~

Thiết lập này giúp `X-Forwarded-Proto` được tôn trọng trước khi Tomcat thực hiện redirect ở context root.

### 3.1. Không dùng Spring Boot

Trong ứng dụng Spring MVC tự cấu hình, đăng ký `ForwardedHeaderFilter` như một Servlet filter. Ví dụ khi cấu hình bằng Spring bean:

~~~java
@Bean
ForwardedHeaderFilter forwardedHeaderFilter() {
    return new ForwardedHeaderFilter();
}
~~~

Nếu đăng ký thủ công qua `FilterRegistrationBean`, `web.xml` hoặc Servlet initializer, đặt filter trước các filter cần đọc request đã được chỉnh sửa, chẳng hạn `RequestContextFilter`. Khi tự khai báo dispatcher types, cân nhắc cả `REQUEST`, `ASYNC` và `ERROR` để xử lý async request và error dispatch đúng cách.

Với WebFlux, dùng `ForwardedHeaderTransformer` thay cho Servlet filter:

~~~java
@Bean
ForwardedHeaderTransformer forwardedHeaderTransformer() {
    return new ForwardedHeaderTransformer();
}
~~~

Spring Data REST dùng Spring MVC, nên cấu hình Servlet filter là nhánh phù hợp cho các repository REST được export.

## 4. Cấu hình proxy và path prefix

Proxy cần gửi đúng thông tin mà client bên ngoài đã sử dụng. Ví dụ:

- Client gọi `https://api.example.com/api/products`.
- Proxy kết thúc TLS tại biên, sau đó chuyển request tới service qua HTTP.
- Proxy gửi `X-Forwarded-Proto: https`, `X-Forwarded-Host: api.example.com` và `X-Forwarded-Port: 443`.
- Nếu proxy bỏ prefix `/api` trước khi chuyển tiếp, proxy gửi thêm `X-Forwarded-Prefix: /api`.

Spring Data REST có cấu hình base path riêng. Ví dụ:

~~~properties
spring.data.rest.basePath=/api
~~~

Hoặc cấu hình qua `RepositoryRestConfigurer` và `RepositoryRestConfiguration.setBasePath("/api")`. Base path này xác định đường dẫn export của Spring Data REST; nó không thay thế thông tin scheme, host hoặc port do forwarded headers cung cấp.

Phân biệt ba khái niệm:

- `spring.data.rest.basePath`: prefix cho tài nguyên Spring Data REST.
- `server.servlet.context-path`: context path của toàn ứng dụng Servlet.
- `X-Forwarded-Prefix`: prefix công khai mà proxy cần khôi phục khi URL nội bộ và URL bên ngoài khác nhau.

Chọn cách cấu hình theo đúng phép biến đổi proxy đang thực hiện:

**Trường hợp A — proxy giữ nguyên prefix**

Nếu proxy chuyển `/api/products` thành `/api/products` và Spring Data REST cũng được cấu hình `basePath=/api`, không thêm lại `X-Forwarded-Prefix: /api` một cách máy móc. Kiểm tra link cuối cùng để tránh kết quả `/api/api/products`.

**Trường hợp B — proxy bỏ prefix trước khi forward**

Nếu public URL là `/api/products` nhưng service nhận `/products`, proxy cần cung cấp prefix gốc bằng `X-Forwarded-Prefix: /api`. Cấu hình filter và route nội bộ sao cho request vẫn được map đúng, còn link được tạo theo path công khai.

**Trường hợp C — proxy thay prefix**

Spring Framework hỗ trợ các tình huống prefix được thay thế, bỏ hoặc thêm vào. Ví dụ public path `/api/{path}` có thể được chuyển tới internal path `/app1/{path}`; proxy gửi `X-Forwarded-Prefix: /api` để link trả về dùng prefix công khai.

Không cộng dồn prefix ở proxy, context path, Spring Data REST base path và forwarded prefix mà không kiểm tra kết quả thực tế.

## 5. Ví dụ request và response

Giả sử ứng dụng Spring Data REST nhận request nội bộ tại `localhost:8080`, còn client truy cập qua `https://api.example.com`. Với cấu hình `FRAMEWORK`, thử gửi các header sau:

~~~bash
curl -i http://localhost:8080/products \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Host: api.example.com' \
  -H 'X-Forwarded-Port: 443'
~~~

Các link HAL được tạo từ request đã khôi phục có thể có dạng:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/products"
    }
  }
}
~~~

Nếu proxy còn bỏ prefix `/api` trước khi chuyển tiếp, gửi thêm:

~~~http
X-Forwarded-Prefix: /api
~~~

Khi cấu hình prefix đúng, link công khai phải chứa `/api` đúng một lần. Nếu port công khai là port mặc định của HTTPS (`443`), URI có thể lược bỏ phần `:443`; điều quan trọng là scheme và authority phải trỏ tới host công khai.

Hãy kiểm tra cả:

- `_links.self.href` ở collection và item resource.
- Các link điều hướng/search/profile do Spring Data REST tạo.
- Header `Location` sau POST tạo tài nguyên.
- Header `Location` hoặc URL đích của redirect nếu ứng dụng có redirect.

## 6. Kiểm thử

### 6.1. Kiểm tra HAL link với forwarded origin bằng MockMvc

Bật strategy trong cấu hình test:

~~~properties
server.forward-headers-strategy=FRAMEWORK
~~~

Sau đó gửi request có forwarded headers và xác nhận link dùng HTTPS cùng host công khai:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ForwardedLinksIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void halLinksUseThePublicOrigin() throws Exception {
        mvc.perform(get("/products")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Host", "api.example.test")
                .header("X-Forwarded-Port", "443"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href",
                    startsWith("https://api.example.test/")));
    }
}
~~~

Cần có repository và dữ liệu test để endpoint `/products` trả representation HAL. Đảm bảo MockMvc đang cài filter; nếu cấu hình test loại bỏ filter, test chỉ kiểm tra request nội bộ và không xác nhận forwarded-header behavior.

### 6.2. Kiểm tra prefix

Nếu deployment dùng proxy rewrite, thêm test với `X-Forwarded-Prefix`:

~~~java
mvc.perform(get("/products")
        .header("X-Forwarded-Proto", "https")
        .header("X-Forwarded-Host", "api.example.test")
        .header("X-Forwarded-Prefix", "/api"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href",
            containsString("/api/products")));
~~~

Điều chỉnh URL request và cấu hình base path theo đúng route nội bộ của dự án. Assert link có prefix đúng một lần, không chỉ assert rằng chuỗi `/api` xuất hiện.

### 6.3. Kiểm tra Location sau POST

Gửi POST tạo một entity qua MockMvc với cùng forwarded headers. Assert header `Location` bắt đầu bằng `https://api.example.test/` và chứa public path. Test này bắt được trường hợp HAL link đúng nhưng URL trong response header vẫn dùng host nội bộ.

### 6.4. Kiểm tra tại proxy thật

MockMvc xác nhận filter của ứng dụng, nhưng không xác nhận cấu hình reverse proxy. Trong staging hoặc môi trường tích hợp:

1. Gọi endpoint bằng public HTTPS URL.
2. Kiểm tra response HAL và `Location`.
3. Xác nhận không có hostname nội bộ, port nội bộ hoặc scheme `http`.
4. Kiểm tra prefix không thiếu hoặc lặp.
5. Thử gửi forged `Forwarded`/`X-Forwarded-*` từ client và xác nhận proxy biên ghi đè/xóa các header không đáng tin cậy.

Chạy test theo build của dự án, ví dụ `./mvnw test` hoặc `mvn test`.

## 7. Troubleshooting

**Link vẫn dùng `http://` dù client truy cập HTTPS**

- Xác nhận proxy gửi `X-Forwarded-Proto: https` hoặc `Forwarded: proto=https`.
- Kiểm tra `server.forward-headers-strategy` không phải `NONE`.
- Nếu dùng `NATIVE`, xác nhận container đang chạy có hỗ trợ đúng header; thử `FRAMEWORK` khi cần Spring xử lý.
- Với Tomcat kết thúc TLS ở proxy, kiểm tra `server.tomcat.redirect-context-root=false` nếu lỗi xuất hiện trong redirect context root.

**Link dùng host nội bộ hoặc `localhost`**

- Kiểm tra `X-Forwarded-Host` hoặc thuộc tính `host` trong `Forwarded`.
- Kiểm tra proxy có ghi đè header do client gửi lên hay không.
- Xác nhận forwarded filter/strategy được bật trước khi Spring Data REST tạo link.

**Link có port nội bộ như 8080 hoặc sai port**

- Kiểm tra `X-Forwarded-Port` và `X-Forwarded-Host`.
- Xác nhận container hoặc Spring Framework đang xử lý port gốc.
- Lưu ý port mặc định `443` có thể không xuất hiện trong URI HTTPS hợp lệ.

**Link thiếu prefix hoặc lặp `/api/api`**

- Ghi lại public path, path proxy forward tới service, `server.servlet.context-path`, `spring.data.rest.basePath` và `X-Forwarded-Prefix`.
- Xác định proxy giữ, bỏ hay thay prefix.
- Chỉ để một cấu hình đại diện cho mỗi bước rewrite; xác nhận bằng URL cuối trong HAL và `Location`.

**Một số link đúng, một số link vẫn sai**

- Kiểm tra link nào do Spring Data REST/Spring HATEOAS tạo từ request và link nào do code ứng dụng tự ghép chuỗi.
- Không hard-code `http://localhost`, hostname nội bộ hoặc port container trong custom link builder.
- Dùng URI/link builder dựa trên request đã được forwarded filter xử lý, hoặc cấu hình public base URI một cách có kiểm soát nếu link thực sự không gắn với request.

**Header có trong request log nhưng ứng dụng không dùng**

- Kiểm tra filter có được đăng ký và chạy trước `RequestContextFilter` hay không.
- Kiểm tra ứng dụng dùng Servlet hay WebFlux; chọn `ForwardedHeaderFilter` cho Servlet và `ForwardedHeaderTransformer` cho WebFlux.
- Nếu tự đăng ký filter, kiểm tra dispatcher types cho `ASYNC` và `ERROR` khi ứng dụng có async/error dispatch.
- Xác nhận định dạng header proxy gửi khớp định dạng Spring được cấu hình để xử lý.

**Kết quả thay đổi theo môi trường**

- Đừng dựa vào default của `server.forward-headers-strategy`; một số cloud platform có default khác môi trường tự quản lý.
- Đặt cấu hình rõ theo môi trường và kiểm tra sau mỗi thay đổi proxy/container.
- Kiểm tra cả request đi thẳng tới service và request đi qua proxy; hai đường có thể có scheme, host và prefix khác nhau.

## 8. An toàn khi tin cậy forwarded headers

Forwarded headers có thể làm thay đổi scheme, host, port và URL gốc mà ứng dụng dùng để tạo link. Nếu ứng dụng nhận trực tiếp các header này từ Internet mà không có proxy tin cậy kiểm soát, client có thể giả mạo host hoặc scheme và làm ứng dụng tạo URL độc hại hoặc sai lệch.

Thực hiện các nguyên tắc sau:

- Proxy ở ranh giới tin cậy phải xóa hoặc reset cả `Forwarded` và `X-Forwarded-*` do client gửi vào, sau đó tự ghi các giá trị đáng tin cậy.
- Không công khai đường truy cập trực tiếp tới backend nếu thiết kế yêu cầu mọi request phải đi qua proxy tin cậy.
- Chỉ bật xử lý forwarded headers khi deployment có proxy tin cậy và đã xác định rõ header nào được sử dụng.
- Không cấu hình tin cậy mọi proxy trong production.
- Nếu chỉ cần loại bỏ forwarded headers mà không dùng giá trị của chúng, Spring Framework có chế độ `removeOnly` cho filter.

Spring Framework lưu ý proxy ở biên tin cậy cần reset cả header chuẩn `Forwarded` và nhóm `X-Forwarded-` để bảo vệ ứng dụng có thể kiểm tra cả hai loại.

## 9. Tài liệu chính thức

- [Spring Boot 3.5 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): `server.forward-headers-strategy`, lựa chọn `NATIVE`/`FRAMEWORK`, proxy HTTPS và Tomcat.
- [Spring Framework — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring/reference/web/webmvc/filters.html): ý nghĩa `Forwarded`, các header `X-Forwarded-*`, xử lý host/port/scheme/prefix, thứ tự filter và security.
- [Spring Data REST — Configuring the REST URL Path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html): ví dụ HAL với absolute href, repository path và `rel`.
- [Spring Data REST — Getting Started / Changing the Base URI](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): `spring.data.rest.basePath` và `RepositoryRestConfigurer.setBasePath(...)`.
- [Spring HATEOAS — Forwarded header handling](https://docs.spring.io/spring-hateoas/docs/2.5.1/reference/html/): ví dụ đăng ký `ForwardedHeaderFilter`, gửi `X-Forwarded-Proto/Host/Port` và kết quả link HAL theo public origin.
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): định nghĩa header chuẩn `Forwarded`.

Tên property và default có thể khác giữa các phiên bản Spring Boot. Đối chiếu tài liệu đúng với version trong build, rồi xác nhận URL trả về qua proxy thật trước khi triển khai.
