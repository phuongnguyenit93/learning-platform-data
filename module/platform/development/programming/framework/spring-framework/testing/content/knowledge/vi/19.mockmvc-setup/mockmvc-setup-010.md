# Giới hạn mô phỏng so với container Servlet đang chạy

`MockMvc` cho phép gửi request HTTP mô phỏng vào Spring MVC mà không cần khởi động một Servlet container thật. Nó rất hữu ích để kiểm tra controller, routing, binding tham số, validation, exception handler, filter và nội dung response trong một bài test nhanh. Tuy nhiên, request của `MockMvc` đi qua các đối tượng Servlet API mô phỏng trong bộ nhớ; request không đi qua socket, HTTP connector hay toàn bộ vòng đời xử lý của Tomcat, Jetty hoặc Undertow.

Vì vậy, một bài test `MockMvc` thành công chứng minh rằng phần lớn pipeline Spring MVC được cấu hình và xử lý đúng trong môi trường mô phỏng. Nó không chứng minh ứng dụng sẽ hoạt động giống hệt khi nhận request qua container Servlet đang chạy. Khi yêu cầu kiểm thử liên quan đến connector, giao thức HTTP, cookie thực tế, multipart parsing, async I/O hoặc cấu hình triển khai của container, cần chạy ứng dụng trên một server thật và gửi request qua HTTP client.

## 1. Request đi qua những thành phần nào?

Trong môi trường chạy thật, một request thường đi qua các lớp sau:

```text
HTTP client
    |
    v
Network socket / TLS
    |
    v
Servlet container connector
    |
    v
Servlet container request processing
    |
    v
Servlet Filters
    |
    v
DispatcherServlet
    |
    v
HandlerMapping -> Controller -> Application services
    |
    v
HttpMessageConverter / View rendering
    |
    v
Servlet container response processing
    |
    v
Network socket / HTTP response
```

Khi dùng `MockMvc`, Spring Test tạo `MockHttpServletRequest`, `MockHttpServletResponse` và các đối tượng Servlet mô phỏng liên quan. Request được chuyển đến `DispatcherServlet` để thực hiện phần xử lý Spring MVC:

```text
Test code
    |
    v
MockMvc.perform(...)
    |
    v
MockHttpServletRequest / MockHttpServletResponse
    |
    v
DispatcherServlet
    |
    v
HandlerMapping -> Controller -> Application services
    |
    v
HttpMessageConverter / View rendering
    |
    v
Mock response returned to the test
```

Điểm quan trọng là `MockMvc` không bỏ qua Spring MVC. Nó thực thi `DispatcherServlet`, handler mapping, argument resolver, data binding, validation, exception resolver, interceptor và message converter theo cấu hình được đưa vào test. Điều được mô phỏng là lớp Servlet API bao quanh Spring MVC và request/response; container thực cùng tầng mạng không được khởi chạy.

## 2. Những gì MockMvc kiểm tra tốt

### Mapping và xử lý controller

Ta có thể xác nhận URL, HTTP method, path variable, query parameter, header, content type và các điều kiện mapping khác có chọn đúng handler hay không.

```java
@RestController
@RequestMapping("/greetings")
class GreetingController {

    private final GreetingService greetingService;

    GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/{name}")
    Greeting greet(@PathVariable String name) {
        return greetingService.greet(name);
    }
}

record Greeting(String message) {
}
```

Bài test slice có thể mock service để tập trung vào hợp đồng HTTP của controller:

```java
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    GreetingService greetingService;

    @Test
    void returnsGreetingForTheRequestedName() throws Exception {
        given(greetingService.greet("Lan"))
                .willReturn(new Greeting("Hello, Lan"));

        mockMvc.perform(get("/greetings/{name}", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Lan"));
    }
}
```

`@WebMvcTest` nạp slice phục vụ web MVC và các thành phần liên quan đến controller được chọn. Service được thay bằng mock để test không phụ thuộc vào xử lý nghiệp vụ phía sau. Đây là cách phù hợp để kiểm tra request mapping, serialization và response contract của controller.

### Binding, validation và chuyển đổi dữ liệu

MockMvc có thể kiểm tra các tình huống như:

- Path variable hoặc query parameter được chuyển sang đúng kiểu Java.
- Request body JSON được deserialize thành DTO.
- Bean Validation phát hiện dữ liệu không hợp lệ.
- `@ControllerAdvice` chuyển exception thành status và response body mong đợi.
- `HttpMessageConverter` chọn định dạng phù hợp với `Content-Type` và `Accept`.
- Header, status code, cookie được đặt trên response mô phỏng.
- View được chọn và model được chuẩn bị trong luồng Spring MVC.

Các kiểm tra này có giá trị vì chúng chạy qua `DispatcherServlet` và các thành phần Spring MVC thật trong context của test. Tuy nhiên, chúng không kiểm tra việc container nhận và phân tích byte HTTP từ mạng như thế nào trước khi request đến `DispatcherServlet`.

### Filter và Spring Security

Filter là một phần của Servlet pipeline. MockMvc có thể chạy filter nếu filter được thêm vào MockMvc. Với Spring Boot, `@AutoConfigureMockMvc` mặc định thêm các bean `Filter` của ứng dụng vào chuỗi mô phỏng; thuộc tính `addFilters` có thể điều chỉnh hành vi này.

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class SecurityMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsAnUnauthenticatedRequest() throws Exception {
        mockMvc.perform(get("/api/private"))
                .andExpect(status().isUnauthorized());
    }
}
```

Ví dụ trên kiểm tra Spring Security filter chain nếu chain đã được cấu hình và được đưa vào MockMvc. Nó hữu ích để kiểm tra authorization, authentication entry point, CSRF và response do security filter tạo ra. Nếu cấu hình `addFilters = false`, hoặc dùng `standaloneSetup` mà quên thêm filter, test sẽ không đi qua filter cần kiểm tra.

Ngay cả khi filter đã chạy trong MockMvc, bài test vẫn chưa xác nhận container đăng ký filter với đúng URL pattern, dispatcher type, thứ tự và quy tắc mapping như môi trường triển khai. Cấu hình filter registration thực tế cần được kiểm tra ở tầng server khi đây là rủi ro của ứng dụng.

## 3. Những phần MockMvc không mô phỏng đầy đủ

### Network, connector và giao thức HTTP

MockMvc không mở cổng TCP và không xử lý kết nối từ client. Vì thế nó không kiểm tra được:

- TLS handshake, chứng chỉ, HTTPS redirect hoặc cấu hình cipher.
- HTTP/2, keep-alive, connection reuse và hành vi đóng kết nối.
- HTTP parser của container, request line, header thực tế và các trường hợp HTTP không hợp lệ.
- Giới hạn kích thước request line, header, body hoặc số lượng header do connector đặt ra.
- Timeout khi đọc request, timeout kết nối và giới hạn số kết nối.
- Nén response, chunked transfer encoding và cách response được flush ra mạng.

Ví dụ, một bài test MockMvc có thể gửi header dài tùy ý và vẫn nhận được response bình thường, trong khi connector của server thật có thể từ chối request vì vượt giới hạn header. Nếu cần xác nhận giới hạn này, hãy gửi request đến server đã khởi động với đúng cấu hình connector và kiểm tra status hoặc hành vi đóng kết nối.

### Cookie, session và vòng đời request thực

MockMvc có `MockHttpSession` và API hỗ trợ đặt session vào request. Điều này phù hợp để kiểm tra logic đọc/ghi session trong ứng dụng. Nhưng test không tự chứng minh container tạo và gửi `Set-Cookie`, client gửi lại cookie trong request kế tiếp, session timeout hoặc session persistence hoạt động như môi trường thật.

Khi cần xác nhận luồng cookie thực tế, dùng HTTP client giữ cookie jar hoặc lấy `Set-Cookie` từ response đầu tiên rồi gửi `Cookie` trong request kế tiếp đến server đang chạy. Nếu hệ thống dùng session replication hoặc distributed session store, cần kiểm tra với cấu hình store tương ứng.

### Multipart parsing và giới hạn upload

MockMvc hỗ trợ `multipart(...)` và `MockMultipartFile`, nhờ đó có thể kiểm tra controller nhận file, tên part, metadata và kết quả xử lý upload.

```java
mockMvc.perform(multipart("/documents")
                .file(new MockMultipartFile(
                        "file",
                        "notes.txt",
                        "text/plain",
                        "sample content".getBytes(StandardCharsets.UTF_8))))
        .andExpect(status().isCreated());
```

Request này được tạo trong bộ nhớ; nó không kiểm tra container hoặc multipart resolver thực tế phân tích boundary từ luồng byte trên mạng, ghi file tạm, áp dụng giới hạn kích thước, xử lý upload bị ngắt hoặc dọn file tạm. Các giới hạn multipart cấu hình trong Spring Boot và container cần được kiểm tra bằng request HTTP thật nếu chúng là yêu cầu quan trọng.

### Servlet mapping, dispatch và cấu hình container

Container quản lý Servlet registration, URL mapping, filter mapping, listener, dispatcher type và một số quy tắc triển khai. MockMvc khởi chạy phần Spring MVC cần thiết cho test nhưng không tái tạo toàn bộ quá trình deploy ứng dụng vào container.

Những khác biệt có thể xuất hiện ở:

- Context path và servlet path của ứng dụng khi deploy dưới một đường dẫn khác root.
- Filter được đăng ký bằng `FilterRegistrationBean`, `web.xml`, `ServletContextInitializer` hoặc cấu hình riêng của container.
- Thứ tự filter và việc filter áp dụng cho `REQUEST`, `ASYNC`, `ERROR`, `FORWARD` hay `INCLUDE` dispatch.
- Servlet listener, session listener và các callback vòng đời của container.
- Welcome page, default servlet, static resource mapping, forward/include và error page của container.
- JNDI resource, datasource hoặc thành phần do môi trường container cung cấp.

MockMvc vẫn có thể đặt `contextPath`, `servletPath` hoặc kiểm tra một số kiểu dispatch mô phỏng. Điều đó giúp kiểm tra logic Spring MVC trong những ngữ cảnh này, nhưng không thay thế việc xác nhận cấu hình deployment thực sự được container áp dụng.

### Async, streaming và response trên mạng

MockMvc hỗ trợ kiểm tra một phần asynchronous request của Spring MVC, ví dụ xác nhận request chuyển sang trạng thái async và thực hiện `asyncDispatch` để kiểm tra kết quả cuối cùng:

```java
MvcResult result = mockMvc.perform(get("/reports/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(result))
        .andExpect(status().isOk());
```

Đây là kiểm tra hữu ích cho luồng async của Spring MVC. Nó không xác nhận container quản lý async I/O, timeout, executor, client disconnect, backpressure, streaming hoặc việc flush từng phần response trên socket như thế nào.

Nếu endpoint dùng `StreamingResponseBody`, `SseEmitter`, streaming JSON hoặc dữ liệu lớn, nên có thêm bài test gửi HTTP request đến server thật. Bài test đó có thể đọc response theo từng phần, xác nhận event được nhận, kiểm tra timeout và quan sát hành vi khi client đóng kết nối.

## 4. Phân biệt các kiểu test Spring Boot

Tên annotation có thể khiến ta nhầm rằng mọi bài test Spring đều chạy server thật. Cần nhìn vào `webEnvironment` và cách request được gửi.

| Cách thiết lập | Application context | Có Servlet container thật? | Cách gửi request |
|---|---|---|---|
| `@WebMvcTest` | Web MVC slice | Không | Inject `MockMvc`. |
| `@SpringBootTest` mặc định | Full application context với web environment mô phỏng | Không | Có thể kết hợp `@AutoConfigureMockMvc`. |
| `@SpringBootTest(webEnvironment = MOCK)` + `@AutoConfigureMockMvc` | Full application context với mock web environment | Không | `MockMvc`. |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` | Full application context | Có, server nhúng được khởi động | HTTP client như `TestRestTemplate` hoặc `RestClient`. |
| `@SpringBootTest(webEnvironment = DEFINED_PORT)` | Full application context | Có, server nhúng lắng nghe cổng đã cấu hình | HTTP client gửi đến cổng đó. |

Ví dụ, `@SpringBootTest` kết hợp `@AutoConfigureMockMvc` vẫn gửi request qua MockMvc. Việc nạp toàn bộ bean của ứng dụng không biến MockMvc thành HTTP client và cũng không tự khởi động embedded server.

Để kiểm tra request qua container nhúng, dùng `RANDOM_PORT`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void servesGreetingThroughTheEmbeddedServletContainer() {
        ResponseEntity<String> response =
                http.getForEntity("/greetings/Lan", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("Hello, Lan");
    }
}
```

Spring Boot khởi động server nhúng trên một cổng ngẫu nhiên và cấu hình `TestRestTemplate` để gọi ứng dụng đó. Request đi qua HTTP stack và Servlet container đang chạy, do đó test có thể phát hiện nhiều vấn đề mà MockMvc không nhìn thấy. Cổng ngẫu nhiên cũng giúp nhiều test context chạy song song mà ít xung đột cổng cố định.

Nếu muốn dùng `RestClient`, có thể tạo client trỏ đến host và cổng được inject bằng `@LocalServerPort`. Với `TestRestTemplate`, Spring Boot đã xử lý base URL cho test server.

## 5. Chọn mức kiểm thử theo rủi ro

Không cần chuyển mọi bài test controller sang server thật. Khởi động container làm test chậm hơn và tăng chi phí tài nguyên. Nên chọn công cụ dựa trên hành vi cần chứng minh.

| Mục tiêu | Cách kiểm thử phù hợp |
|---|---|
| URL mapping, status, JSON, validation, exception advice | `@WebMvcTest` + MockMvc. |
| Tương tác controller với service, repository và cấu hình ứng dụng | `@SpringBootTest` + MockMvc, tùy phạm vi cần nạp. |
| Spring Security filter chain và response của filter | MockMvc có filter được cấu hình đầy đủ; bổ sung server test nếu cần xác nhận registration hoặc dispatch mapping. |
| Connector, HTTP parser, giới hạn header/body, TLS, HTTP/2 | HTTP client gọi server thật với cấu hình tương ứng. |
| Cookie qua nhiều request, session cookie và multipart upload thực | HTTP client gọi server thật. |
| Async I/O, streaming, SSE, client disconnect hoặc response flush | HTTP client gọi server thật; kiểm tra thời gian và dữ liệu theo từng phần khi cần. |
| Khác biệt giữa embedded container và môi trường deploy bên ngoài | Chạy kiểm thử trong container/môi trường deploy mục tiêu. |

Một chiến lược thực tế có thể gồm ba tầng:

1. **MVC slice tests:** số lượng lớn, chạy nhanh, kiểm tra contract của từng controller.
2. **Application integration tests:** số lượng vừa phải, nạp full context và dùng MockMvc để xác nhận wiring, security và tương tác giữa các bean.
3. **Real-server tests:** số lượng tập trung vào các hành vi phụ thuộc container hoặc HTTP transport, chạy với embedded server hoặc đúng container triển khai.

Các tầng này bổ sung bằng chứng cho nhau. MockMvc giúp khoanh vùng lỗi trong Spring MVC nhanh; server test xác nhận ứng dụng được khởi động và phục vụ request qua container thật.

## 6. Giới hạn của embedded server test

`RANDOM_PORT` kiểm tra container nhúng mà ứng dụng khởi động trong test. Nếu production dùng cùng loại container và cấu hình tương đương, đây là bằng chứng gần với môi trường chạy thật hơn MockMvc.

Tuy nhiên, embedded server test không tự chứng minh môi trường production hoàn toàn giống nhau. Một số khác biệt có thể nằm ngoài tiến trình ứng dụng:

- Reverse proxy, ingress controller, load balancer và TLS termination.
- DNS, firewall, network policy và giới hạn của nền tảng hosting.
- Cấu hình Tomcat/Jetty/Undertow bên ngoài nếu production deploy WAR vào một container được quản trị riêng.
- Secret, JNDI, volume, quyền file, biến môi trường và tài nguyên do nền tảng cấp.
- Cấu hình scale nhiều instance, session replication và cân bằng tải.

Nếu ứng dụng chạy trong một Tomcat bên ngoài, test với embedded Tomcat không xác nhận được mọi quy tắc của Tomcat bên ngoài. Khi một vấn đề chỉ xuất hiện sau deployment, hãy tạo test hoặc smoke test trong chính loại container và cấu hình gần với production, đồng thời kiểm tra cả proxy nếu request đi qua proxy.

## 7. Ví dụ: cùng một yêu cầu, hai tầng kiểm thử

Giả sử endpoint upload tài liệu cần:

- Trả về `201 Created` khi file hợp lệ.
- Từ chối file lớn hơn giới hạn cấu hình.
- Ghi nhận metadata và trả về JSON.

MockMvc phù hợp để kiểm tra controller nhận đúng part `file`, gọi service và trả về JSON theo contract. Có thể gửi `MockMultipartFile` cho các trường hợp file hợp lệ, thiếu part hoặc metadata sai.

Một bài test HTTP thật bổ sung việc gửi multipart request có boundary qua connector và xác nhận giới hạn upload thực sự được áp dụng. Test này nên dùng file có kích thước vượt ngưỡng và xác nhận status/response theo chính sách đã cấu hình. Nếu giới hạn được áp dụng ở reverse proxy trước khi request tới ứng dụng, cần test qua proxy tương ứng; gọi trực tiếp embedded server sẽ không xác nhận lớp proxy đó.

Tương tự, với endpoint yêu cầu đăng nhập, MockMvc có thể xác nhận authorization và CSRF filter logic. Bài test server thật có thể xác nhận cookie session được phát, gửi lại và duy trì trạng thái qua hai HTTP request. Nếu production dùng SSO hoặc proxy xác thực, cần thêm kiểm thử tại ranh giới tích hợp đó.

## 8. Những hiểu nhầm thường gặp

### “MockMvc trả response HTTP nên chắc chắn đã kiểm tra HTTP server”

Response của MockMvc là kết quả từ `MockHttpServletResponse`. Nó có status, header, cookie và body để test kiểm tra, nhưng không phải response đã được ghi qua socket bởi connector. Cấu trúc response trong bộ nhớ không chứng minh cách server mã hóa hoặc truyền response trên mạng.

### “Dùng `@SpringBootTest` nghĩa là đã khởi động web server”

Không đúng trong mọi trường hợp. `@SpringBootTest` mặc định dùng web environment mô phỏng. Khi kết hợp `@AutoConfigureMockMvc`, test vẫn gửi request qua MockMvc. Muốn server nhúng khởi động, hãy chọn `RANDOM_PORT` hoặc `DEFINED_PORT`.

### “MockMvc không kiểm tra được filter hoặc security”

MockMvc có thể chạy filter và Spring Security filter chain khi chúng được thêm vào cấu hình MockMvc. Điều cần phân biệt là việc thực thi filter logic trong chuỗi mô phỏng với việc kiểm tra container đăng ký filter, URL pattern, dispatcher type và thứ tự thực tế.

### “Test async bằng asyncDispatch tương đương test async trên server”

`asyncDispatch` xác nhận kết quả xử lý bất đồng bộ trong mô hình Spring MVC test. Nó không mô phỏng đầy đủ executor, socket, timeout, streaming và client disconnect của container đang phục vụ request.

### “Embedded server test là bằng chứng production tuyệt đối”

Embedded server chỉ đại diện cho server và cấu hình đã khởi động trong test. Nếu production có proxy, container bên ngoài, TLS termination hoặc tài nguyên nền tảng riêng, các thành phần đó cần được kiểm tra ở tầng triển khai phù hợp.

## 9. Cách đọc kết quả test

Khi một bài MockMvc thất bại, hãy xem request đã chọn đúng handler chưa, filter nào đã chạy, exception resolver nào xử lý lỗi và response mô phỏng được tạo ra như thế nào. Đây là phạm vi mà MockMvc cung cấp tín hiệu rất tốt.

Khi MockMvc thành công nhưng request thật thất bại, hãy kiểm tra các lớp nằm trước và sau `DispatcherServlet`: connector, TLS, HTTP parsing, filter registration, servlet mapping, multipart parsing, session cookie, async transport và proxy. Sự khác biệt giữa hai kết quả thường giúp xác định vấn đề nằm ở Spring MVC hay ở môi trường Servlet/HTTP.

Khi thiết kế test, hãy ghi rõ hành vi nào đang được chứng minh. Ví dụ, “controller trả `413 Payload Too Large` khi service từ chối file” khác với “container từ chối request vượt giới hạn multipart trước khi controller được gọi”. Hai hành vi có thể trả status giống nhau nhưng được tạo ra ở hai tầng khác nhau và cần hai loại test khác nhau.

## 10. Checklist lựa chọn MockMvc hay server thật

- [ ] Mục tiêu chỉ là kiểm tra Spring MVC mapping, binding, validation hoặc response contract? Dùng MockMvc.
- [ ] Cần nạp full application context nhưng không cần HTTP transport? Dùng `@SpringBootTest` với MockMvc.
- [ ] Cần chứng minh request đi qua connector và Servlet container? Dùng `RANDOM_PORT` hoặc `DEFINED_PORT` với HTTP client.
- [ ] Cần kiểm tra TLS, HTTP/2, giới hạn connector hoặc HTTP parser? Dùng server thật với cấu hình connector tương ứng.
- [ ] Cần kiểm tra cookie/session qua nhiều request hoặc multipart parsing thực? Dùng server thật.
- [ ] Cần kiểm tra async streaming, flush, timeout hoặc client disconnect? Dùng server thật.
- [ ] Production có reverse proxy hoặc container bên ngoài? Bổ sung test ở đúng môi trường đó khi hành vi liên quan.
- [ ] Test MockMvc có đưa các filter cần thiết vào chuỗi mô phỏng không?
- [ ] Test có mô tả đúng tầng mà nó đang xác nhận không?

`MockMvc` là công cụ kiểm thử Spring MVC rất hiệu quả vì nó chạy `DispatcherServlet` mà không cần mở server. Giới hạn của nó nằm ở những hành vi do Servlet container, connector và mạng đảm nhiệm. Kết hợp MockMvc cho phần MVC với một số bài test HTTP thật tập trung vào rủi ro của container sẽ tạo ra bộ kiểm thử nhanh, rõ phạm vi và có bằng chứng phù hợp cho môi trường chạy của ứng dụng.
