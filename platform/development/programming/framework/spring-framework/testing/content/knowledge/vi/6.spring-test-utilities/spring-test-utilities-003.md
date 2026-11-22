# MockServletContext và đối tượng Servlet mô phỏng

Spring Test cung cấp một nhóm lớp mô phỏng Servlet API để kiểm thử những thành phần cần môi trường web mà không phải khởi chạy một servlet container thật. Thành phần trung tâm là **MockServletContext**: một triển khai nhẹ của ServletContext, có thể lưu init parameter, application attribute và cung cấp quyền truy cập tài nguyên theo cấu hình của test. Đi cùng nó là các đối tượng như **MockHttpServletRequest**, **MockHttpServletResponse**, **MockHttpSession**, **MockServletConfig** và **MockFilterConfig**.

Các lớp này hữu ích khi kiểm thử servlet, filter, listener hoặc một thành phần Spring nhận ServletContext. Chúng cũng là nền tảng mà Spring MVC Test sử dụng để mô phỏng request và response. Tuy nhiên, cần chọn đúng mức kiểm thử: tạo MockServletContext trực tiếp giúp kiểm tra một thành phần Servlet riêng lẻ; dùng MockMvc giúp gửi request qua chuỗi xử lý Spring MVC; kiểm thử với embedded server mới xác nhận hành vi qua một servlet container thực tế.

## 1. ServletContext trong ứng dụng web

Theo Servlet API, mỗi web application có một ServletContext đại diện cho môi trường ứng dụng được triển khai. ServletContext cung cấp các khả năng ở phạm vi toàn ứng dụng:

- Đọc các tham số khởi tạo được cấu hình cho web application.
- Lưu và chia sẻ application attribute giữa các thành phần trong cùng ứng dụng.
- Truy cập tài nguyên của web application.
- Lấy thông tin về context và môi trường Servlet.
- Hỗ trợ các API đăng ký thành phần động trong giai đoạn khởi tạo, tùy phiên bản Servlet.

ServletContext có phạm vi rộng hơn HttpServletRequest hoặc HttpSession. Request đại diện cho một lần trao đổi HTTP; session đại diện cho trạng thái gắn với một phiên người dùng; ServletContext đại diện cho môi trường chung của web application.

| Đối tượng | Phạm vi | Ví dụ dữ liệu |
|---|---|---|
| ServletContext | Toàn web application | Tên ứng dụng, cấu hình chung, application attribute |
| ServletConfig | Một servlet | Tên servlet, init parameter riêng của servlet |
| FilterConfig | Một filter | Init parameter riêng của filter |
| HttpServletRequest | Một HTTP request | Method, URI, header, parameter, body |
| HttpServletResponse | Một HTTP response | Status, header, body |
| HttpSession | Một phiên người dùng | User id, dữ liệu phiên, trạng thái đăng nhập |

Việc phân biệt phạm vi rất quan trọng khi chuẩn bị test. Nếu dữ liệu thuộc về một request, không nên lưu nó vào ServletContext chỉ để các method khác đọc được. Nếu cấu hình áp dụng cho một servlet riêng, ServletConfig thường là nơi phù hợp hơn.

## 2. MockServletContext là gì?

**MockServletContext** nằm trong package org.springframework.mock.web của module spring-test. Đây là một đối tượng Java thực thi ServletContext với hành vi mô phỏng phù hợp cho test. Nó không phải một Mockito mock chỉ có các lời gọi được lập trình sẵn; nó có trạng thái và hành vi cơ bản để thành phần được kiểm thử có thể sử dụng như một ServletContext.

Có thể tạo một context tối giản:

~~~java
import org.springframework.mock.web.MockServletContext;

class ServletContextComponentTest {

    void example() {
        MockServletContext servletContext = new MockServletContext();

        servletContext.setAttribute("application.name", "test-app");
        servletContext.setInitParameter("feature.upload.enabled", "true");

        assertEquals("test-app",
            servletContext.getAttribute("application.name"));
        assertEquals("true",
            servletContext.getInitParameter("feature.upload.enabled"));
    }
}
~~~

Đoạn mã minh họa việc thiết lập application attribute và init parameter. Trong test thực tế, các giá trị này nên được chuẩn bị trước khi gọi thành phần cần kiểm tra.

### 2.1. Init parameter và application attribute

Init parameter là cấu hình được đọc thông qua ServletContext. Chúng thường đại diện cho giá trị cấu hình của web application. Application attribute là trạng thái runtime có thể được lưu và chia sẻ giữa các thành phần sử dụng cùng context.

~~~java
MockServletContext context = new MockServletContext();

context.setInitParameter("asset.version", "v2");
context.setAttribute("maintenance.enabled", Boolean.FALSE);

assertEquals("v2", context.getInitParameter("asset.version"));
assertEquals(Boolean.FALSE, context.getAttribute("maintenance.enabled"));
~~~

Hai loại dữ liệu này có ý nghĩa khác nhau:

- Init parameter được dùng để đọc cấu hình. Với Servlet API thật, việc thiết lập init parameter bị giới hạn theo giai đoạn khởi tạo ứng dụng. Trong test, hãy thiết lập chúng ngay khi tạo mock context, trước khi chạy component.
- Attribute là trạng thái runtime; component có thể thêm, đọc hoặc xóa attribute trong quá trình hoạt động.

Nếu component gọi setAttribute, removeAttribute hoặc getAttributeNames, MockServletContext cho phép quan sát các thao tác đó trong test. Tuy nhiên, test nên xác nhận hành vi có ý nghĩa với hợp đồng của component, không kiểm tra chi tiết nội bộ không cần thiết.

### 2.2. Resource của web application

ServletContext có các API như getResource, getResourceAsStream và getResourcePaths để truy cập tài nguyên trong web application. MockServletContext cung cấp cơ chế mô phỏng những API này dựa trên resource base path và ResourceLoader được cấu hình.

Khi cần kiểm thử một thành phần đọc file từ web application, hãy xác định rõ resource root của test. Không nên giả định đường dẫn làm việc của IDE, Gradle hoặc CI giống nhau. Có thể dùng constructor nhận resource base path và ResourceLoader để chỉ định cách phân giải tài nguyên.

Ví dụ cấu trúc khởi tạo:

~~~java
MockServletContext context = new MockServletContext(
    "src/main/webapp",
    new FileSystemResourceLoader()
);
~~~

Đường dẫn ở đây là ví dụ và cần phù hợp với thư mục tài nguyên của dự án cũng như working directory khi chạy test. Nếu mục tiêu là kiểm tra tài nguyên nằm trên classpath, hãy chọn ResourceLoader tương ứng thay vì phụ thuộc vào một đường dẫn file của máy phát triển.

Khi test resource lookup, nên xác nhận các tình huống cần thiết:

- Tài nguyên tồn tại và có thể đọc.
- Tài nguyên không tồn tại được xử lý đúng.
- Đường dẫn được truyền vào tuân theo quy ước của ServletContext, thường là đường dẫn bắt đầu bằng dấu slash.
- Component không giả định mọi tài nguyên đều có real file-system path.

MockServletContext có thể mô phỏng việc tìm tài nguyên nhưng không tái tạo mọi khác biệt của cách đóng gói và triển khai WAR trên container. Nếu hành vi phụ thuộc cách container publish resource hoặc filesystem production, cần thêm kiểm thử triển khai phù hợp.

## 3. Kiểm thử component nhận ServletContext

Một số thành phần Spring triển khai ServletContextAware để nhận ServletContext trong quá trình được khởi tạo. Với component nhỏ, có thể truyền MockServletContext trực tiếp để kiểm tra cách nó sử dụng context.

~~~java
import jakarta.servlet.ServletContext;
import org.springframework.web.context.ServletContextAware;

class UploadSettings implements ServletContextAware {

    private String uploadDirectory;

    @Override
    public void setServletContext(ServletContext servletContext) {
        this.uploadDirectory =
            servletContext.getInitParameter("upload.directory");
    }

    String uploadDirectory() {
        return uploadDirectory;
    }
}
~~~

Test tương ứng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockServletContext;

class UploadSettingsTest {

    @Test
    void readsUploadDirectoryFromServletContext() {
        // Arrange
        MockServletContext servletContext = new MockServletContext();
        servletContext.setInitParameter(
            "upload.directory",
            "/var/app/uploads"
        );
        UploadSettings settings = new UploadSettings();

        // Act
        settings.setServletContext(servletContext);

        // Assert
        assertEquals("/var/app/uploads", settings.uploadDirectory());
    }
}
~~~

Ví dụ dùng API Jakarta Servlet. Với Spring Framework 6 trở lên, Servlet API thuộc namespace jakarta.servlet. Với Spring Framework 5.x, các import tương ứng thường thuộc javax.servlet. Không được trộn hai namespace trong cùng một ứng dụng vì chúng là hai kiểu class khác nhau.

Test trên kiểm tra component đọc đúng cấu hình từ ServletContext. Nó không kiểm tra quá trình Spring tự động phát hiện ServletContextAware và gọi callback. Nếu mục tiêu là kiểm tra cơ chế wiring của Spring WebApplicationContext, hãy khởi tạo một context web trong test và lấy bean từ context đó.

## 4. Các Servlet mock thường dùng

Spring Test cung cấp nhiều đối tượng mô phỏng cho từng phần của Servlet API. Mỗi loại có phạm vi riêng:

| Lớp mock | Đối tượng mô phỏng | Trường hợp thường dùng |
|---|---|---|
| MockServletContext | ServletContext | Cấu hình và trạng thái cấp ứng dụng |
| MockServletConfig | ServletConfig | Init parameter và tên servlet |
| MockFilterConfig | FilterConfig | Init parameter của filter |
| MockHttpServletRequest | HttpServletRequest | Method, URI, header, parameter, body, session |
| MockHttpServletResponse | HttpServletResponse | Status, header, cookie và response body |
| MockHttpSession | HttpSession | Attribute và trạng thái phiên |
| MockPart | Part | Dữ liệu multipart upload |
| MockRequestDispatcher | RequestDispatcher | Kiểm tra forward/include trong test phù hợp |
| MockServletInputStream | ServletInputStream | Luồng nội dung request |
| MockServletOutputStream | ServletOutputStream | Luồng nội dung response |

Các lớp này được thiết kế để phối hợp với nhau. Ví dụ, MockHttpServletRequest có thể được tạo với MockServletContext và gắn MockHttpSession; MockServletConfig cũng nhận ServletContext để biểu diễn môi trường của một servlet.

## 5. MockServletConfig và MockFilterConfig

ServletConfig chứa cấu hình dành riêng cho một servlet. FilterConfig chứa cấu hình dành riêng cho một filter. Cả hai đều tham chiếu đến ServletContext chung.

~~~java
import org.springframework.mock.web.MockServletConfig;
import org.springframework.mock.web.MockServletContext;
import org.springframework.mock.web.MockFilterConfig;

MockServletContext context = new MockServletContext();

MockServletConfig servletConfig =
    new MockServletConfig(context, "reportServlet");
servletConfig.addInitParameter("format", "csv");

MockFilterConfig filterConfig =
    new MockFilterConfig(context, "auditFilter");
filterConfig.addInitParameter("header-name", "X-Request-Id");

assertEquals("reportServlet", servletConfig.getServletName());
assertEquals("csv", servletConfig.getInitParameter("format"));
assertEquals("auditFilter", filterConfig.getFilterName());
assertEquals("X-Request-Id", filterConfig.getInitParameter("header-name"));
~~~

Đây là ví dụ chuẩn bị hai loại cấu hình. Khi kiểm thử servlet hoặc filter, hãy truyền đúng config vào lifecycle init tương ứng. Servlet nhận ServletConfig; filter nhận FilterConfig. Cả hai có thể truy cập ServletContext thông qua config.

Một test filter có thể dùng MockFilterConfig để xác nhận filter đọc đúng tên header hoặc chế độ hoạt động. Nếu filter được cấu hình bởi Spring bean, hãy kiểm thử cấu hình Spring ở test phù hợp thay vì tạo config thủ công rồi kết luận toàn bộ quá trình khởi tạo filter đã đúng.

## 6. MockHttpServletRequest và MockHttpServletResponse

MockHttpServletRequest và MockHttpServletResponse là hai lớp quan trọng khi kiểm thử thành phần làm việc trực tiếp với HTTP Servlet API.

Request mock cho phép chuẩn bị:

- HTTP method và request URI.
- Context path, servlet path, query string.
- Header và parameter.
- Request body và content type.
- Principal, role và session.

Response mock cho phép quan sát:

- HTTP status.
- Header và cookie.
- Content type và encoding.
- Response body dạng byte hoặc text.
- Redirect hoặc error status được thiết lập.

Ví dụ kiểm thử một filter gắn correlation id vào response:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockServletContext;

class CorrelationIdFilterTest {

    @Test
    void copiesCorrelationIdToResponseHeader() throws Exception {
        // Arrange
        MockServletContext context = new MockServletContext();
        MockHttpServletRequest request =
            new MockHttpServletRequest(context);
        MockHttpServletResponse response =
            new MockHttpServletResponse();

        request.setMethod("GET");
        request.setRequestURI("/orders");
        request.addHeader("X-Correlation-Id", "trace-123");

        Filter filter = (ServletRequest servletRequest,
                         ServletResponse servletResponse,
                         FilterChain chain) -> {
            HttpServletRequest httpRequest =
                (HttpServletRequest) servletRequest;
            HttpServletResponse httpResponse =
                (HttpServletResponse) servletResponse;

            httpResponse.setHeader(
                "X-Correlation-Id",
                httpRequest.getHeader("X-Correlation-Id")
            );
            chain.doFilter(servletRequest, servletResponse);
        };

        // Act
        filter.doFilter(request, response, (req, res) -> {
            ((HttpServletResponse) res).setStatus(
                HttpServletResponse.SC_NO_CONTENT
            );
        });

        // Assert
        assertEquals("trace-123", response.getHeader("X-Correlation-Id"));
        assertEquals(HttpServletResponse.SC_NO_CONTENT, response.getStatus());
    }
}
~~~

Filter trong ví dụ là lambda minh họa hợp đồng Servlet Filter. Request và response được truyền trực tiếp vào filter; FilterChain giả lập bước xử lý tiếp theo và đặt status để test xác nhận filter đã gọi chain.

Trong test thực tế, có thể khởi tạo class filter của ứng dụng và truyền request, response mock vào. Nếu cần kiểm tra việc filter được đăng ký đúng thứ tự trong Spring Security hoặc servlet container, test filter riêng chưa đủ; cần kiểm tra cấu hình chuỗi filter hoặc gửi request qua MockMvc/embedded server tương ứng.

### 6.1. Kiểm thử request body và response body

Request mock cho phép gắn body byte:

~~~java
byte[] requestBody = """
    {"name":"Ada"}
    """.getBytes(StandardCharsets.UTF_8);
request.setContent(requestBody);
request.setContentType("application/json");
~~~

Response mock cho phép component ghi nội dung bằng writer hoặc output stream. Sau khi gọi component, test có thể đọc nội dung bằng getContentAsString hoặc getContentAsByteArray:

~~~java
assertEquals("created", response.getContentAsString());
~~~

Khi kiểm thử body, cần thống nhất charset. Nếu nội dung là JSON hoặc văn bản Unicode, hãy cấu hình encoding phù hợp và so sánh nội dung đã giải mã đúng charset. Với binary response, hãy so sánh byte array hoặc kiểm tra metadata như content type và content length.

Không nên chỉ kiểm tra rằng response body không rỗng. Hãy xác nhận cấu trúc hoặc giá trị có ý nghĩa đối với hợp đồng HTTP mà component cung cấp.

## 7. MockHttpSession và trạng thái phiên

HttpSession lưu trạng thái gắn với một phiên người dùng. MockHttpSession cho phép kiểm thử việc đọc, ghi và xóa session attribute mà không cần trình duyệt hoặc container.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockServletContext;

class SessionStateTest {

    @Test
    void readsUserIdFromSession() {
        // Arrange
        MockServletContext context = new MockServletContext();
        MockHttpSession session = new MockHttpSession(context);
        session.setAttribute("userId", "user-42");

        MockHttpServletRequest request =
            new MockHttpServletRequest(context);
        request.setSession(session);

        // Act
        Object userId = request.getSession().getAttribute("userId");

        // Assert
        assertEquals("user-42", userId);
    }
}
~~~

MockHttpSession cũng hữu ích để kiểm tra hành vi invalidate, session attribute và trạng thái mới/cũ của session. Khi test logic đăng nhập hoặc phân quyền, cần nhớ rằng việc gắn attribute vào session mock chỉ kiểm tra code đang đọc trạng thái đó. Nó không chứng minh cơ chế cookie, session id, session fixation protection hoặc lưu session phía container đã được cấu hình đúng.

Nếu cần kiểm tra tích hợp Spring Security, hãy gửi request qua MockMvc với cơ chế xác thực phù hợp. Khi cần kiểm tra session persistence hoặc cấu hình session thật, dùng embedded server và môi trường lưu session tương ứng.

## 8. MockServletContext trong Spring WebApplicationContext

WebApplicationContext là ApplicationContext có nhận thức về môi trường web. Một số bean trong web context cần ServletContext. Trong test cấp thấp, có thể tạo web application context và gắn MockServletContext trước khi refresh.

Ví dụ khái niệm với AnnotationConfigWebApplicationContext:

~~~java
import org.springframework.mock.web.MockServletContext;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;

class WebContextConfigurationTest {

    @Test
    void createsWebContextWithMockServletContext() {
        MockServletContext servletContext = new MockServletContext();

        try (AnnotationConfigWebApplicationContext context =
                 new AnnotationConfigWebApplicationContext()) {

            context.setServletContext(servletContext);
            context.register(WebTestConfiguration.class);
            context.refresh();

            assertNotNull(context.getServletContext());
            assertNotNull(context.getBean(WebComponent.class));
        }
    }
}
~~~

Ví dụ giả định WebTestConfiguration đăng ký WebComponent. Thứ tự quan trọng là gắn ServletContext và đăng ký cấu hình trước khi refresh context. Sau refresh, Spring tạo bean và thực hiện các callback liên quan theo lifecycle của context.

Trong ứng dụng Spring Boot, phần lớn test không cần tự tạo AnnotationConfigWebApplicationContext. Có thể dùng @SpringBootTest hoặc @WebMvcTest để Spring Boot và Spring Test chuẩn bị context phù hợp. Cách tạo context thủ công thích hợp hơn khi cần kiểm tra một cấu hình web nhỏ hoặc một thành phần Spring Web độc lập.

## 9. Quan hệ giữa Servlet mock và MockMvc

MockServletContext, MockHttpServletRequest và MockHttpServletResponse là các khối nền tảng. MockMvc xây dựng trên các đối tượng mock này và cung cấp API cấp cao để gửi request qua Spring MVC DispatcherServlet.

| Cách kiểm thử | Điểm vào | Phạm vi được kiểm tra |
|---|---|---|
| Gọi component với MockServletContext | ServletContext hoặc component nhận context | Cách component sử dụng context |
| Gọi filter/servlet với request và response mock | Servlet Filter hoặc Servlet | Hành vi của thành phần Servlet cụ thể |
| MockMvc | HTTP request mô phỏng gửi qua DispatcherServlet | Mapping, argument resolver, converter, validation, controller, exception handling và response |
| Embedded servlet container | HTTP client gửi qua cổng thật | Tích hợp với container, server connector và pipeline triển khai thực tế |

Ví dụ MockMvc:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsNotFoundForUnknownOrder() throws Exception {
        mockMvc.perform(get("/orders/{id}", "missing"))
            .andExpect(status().isNotFound());
    }
}
~~~

MockMvc phù hợp khi mục tiêu là kiểm tra hành vi HTTP của Spring MVC. Không cần tự tạo MockHttpServletRequest và gọi DispatcherServlet thủ công cho các tình huống controller thông thường.

Ngược lại, nếu đang kiểm thử một filter độc lập hoặc một component chỉ cần đọc ServletContext attribute, việc tạo trực tiếp mock Servlet có thể làm test ngắn và tập trung hơn.

## 10. Những giới hạn cần hiểu khi dùng Servlet mock

MockServletContext và các lớp mock khác cung cấp mô hình nhẹ của Servlet API. Chúng không thay thế một servlet container đầy đủ. Một số hành vi phụ thuộc môi trường thật có thể không được mô phỏng hoặc không có cùng đặc tính.

Không nên dùng Servlet mock để kết luận về:

- Socket, TLS, HTTP connector và giao tiếp mạng thật.
- Cấu hình reverse proxy hoặc load balancer.
- Cách container triển khai và khởi tạo WAR.
- Toàn bộ lifecycle của container, listener, filter và servlet registration trong môi trường production.
- JSP engine, session persistence của container hoặc đặc tính riêng của Tomcat/Jetty/Undertow.
- Khả năng tương thích giữa ứng dụng và phiên bản container cụ thể.

MockServletContext có thể giữ attribute và cung cấp resource lookup cơ bản, nhưng không mô phỏng đầy đủ quá trình deploy ứng dụng. MockHttpSession có thể giữ session attribute, nhưng không chứng minh cookie và session store thật hoạt động. MockHttpServletResponse có thể lưu status/header/body, nhưng không chứng minh response đã được truyền qua mạng.

Khi một yêu cầu phụ thuộc container, hãy bổ sung kiểm thử bằng embedded server. Ví dụ, Spring Boot có thể khởi chạy ứng dụng trên cổng ngẫu nhiên với @SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT). Khi đó, HTTP client gửi request qua server đang chạy và kiểm tra được nhiều hành vi tích hợp hơn.

## 11. Chọn đúng mức kiểm thử

Có thể dùng các câu hỏi sau để chọn công cụ:

| Mục tiêu | Cách tiếp cận phù hợp |
|---|---|
| Component đọc init parameter hoặc application attribute | MockServletContext trực tiếp |
| Servlet đọc init parameter riêng | MockServletConfig |
| Filter đọc init parameter riêng | MockFilterConfig |
| Filter xử lý header, request hoặc response | MockHttpServletRequest và MockHttpServletResponse |
| Logic phụ thuộc session attribute | MockHttpSession |
| Controller, validation và HTTP mapping của Spring MVC | MockMvc hoặc @WebMvcTest |
| Bean wiring trong web application context | WebApplicationContext cùng MockServletContext hoặc test slice phù hợp |
| Hành vi phụ thuộc servlet container hoặc network | Embedded server/integration test |

Một test tốt chỉ dựng phần môi trường cần thiết cho câu hỏi đang kiểm tra. Nếu mục tiêu là đọc một init parameter, MockServletContext đủ dùng. Nếu mục tiêu là xác nhận controller nhận JSON, áp dụng validation và trả status chính xác, MockMvc thể hiện đầy đủ pipeline MVC hơn. Nếu mục tiêu là kiểm tra cách ứng dụng hoạt động sau khi deploy lên container, cần chạy ứng dụng trên server thật.

## 12. Lỗi thường gặp khi sử dụng

### 12.1. Nhầm ServletContext với HttpSession

ServletContext có phạm vi toàn ứng dụng; HttpSession có phạm vi một phiên người dùng. Đưa thông tin riêng của người dùng vào ServletContext có thể làm rò rỉ trạng thái giữa các phiên trong ứng dụng thật. Hãy chọn đúng đối tượng theo phạm vi dữ liệu.

### 12.2. Dùng mock context nhưng kỳ vọng container tự khởi tạo

Tạo MockServletContext không tự động đăng ký filter, servlet, listener hoặc chạy toàn bộ lifecycle của container. Test phải gọi component hoặc khởi tạo Spring web context theo đúng mục tiêu.

### 12.3. Thiết lập init parameter quá muộn

Hãy thiết lập init parameter trước khi khởi tạo servlet, filter hoặc Spring context phụ thuộc vào giá trị đó. Nếu thay đổi sau khi component đã đọc cấu hình, component có thể vẫn giữ giá trị cũ trong field của nó.

### 12.4. Dùng đường dẫn tài nguyên phụ thuộc máy

Đường dẫn tuyệt đối trên máy phát triển có thể không tồn tại trong CI. Hãy dùng ResourceLoader và resource base path có chủ đích, ưu tiên tài nguyên thuộc test fixture hoặc classpath khi phù hợp.

### 12.5. Kiểm tra response trước khi component hoàn tất

Nếu component ghi body qua writer hoặc output stream, hãy thực thi xong hành động rồi mới đọc response. Với code có flush hoặc đóng stream, cần bảo đảm test theo đúng vòng đời mà component sử dụng.

### 12.6. Mock quá nhiều hành vi của Servlet API

Khi dùng MockServletContext, nên sử dụng hành vi mặc định của lớp mock và chỉ thiết lập các giá trị cần thiết. Nếu cần mô phỏng một hành vi đặc biệt mà mock không hỗ trợ, có thể dùng một test double riêng hoặc Mockito cho interface cụ thể, nhưng cần hiểu rằng test đó đang kiểm tra hợp đồng hẹp hơn.

### 12.7. Dùng Servlet mock để kết luận tích hợp production

Một test với MockHttpServletRequest không chứng minh ứng dụng nhận request thật qua connector. Hãy đặt giới hạn kết luận theo đúng phạm vi test và bổ sung embedded-container test cho các yêu cầu triển khai.

## 13. Mẫu cấu trúc test với MockServletContext

Với một component đọc cấu hình cấp ứng dụng, có thể bắt đầu bằng mẫu:

~~~java
class WebFeatureTest {

    @Test
    void usesApplicationConfiguration() {
        // Arrange
        MockServletContext servletContext = new MockServletContext();
        servletContext.setInitParameter("feature.enabled", "true");
        servletContext.setAttribute("feature.mode", "test");

        WebFeature feature = new WebFeature();

        // Act
        feature.setServletContext(servletContext);
        boolean enabled = feature.isEnabled();

        // Assert
        assertTrue(enabled);
        assertEquals("test", feature.mode());
    }
}
~~~

Tên class và method trong ví dụ là minh họa cho component của ứng dụng. Khi áp dụng, hãy giữ cấu trúc ba phần:

1. Tạo MockServletContext và cấu hình đúng init parameter, attribute hoặc resource.
2. Truyền context vào component qua constructor, setter hoặc Spring WebApplicationContext tùy cơ chế thực tế.
3. Gọi hành vi cần kiểm tra và xác nhận kết quả quan sát được.

Với request/response mock, cấu trúc tương tự nhưng chuẩn bị method, URI, header, parameter, body và session; sau đó gọi servlet hoặc filter; cuối cùng kiểm tra status, header và body.

## Kết luận

MockServletContext và các đối tượng Servlet mô phỏng của Spring Test giúp kiểm thử thành phần web ở mức nhẹ, nhanh và có thể kiểm soát. Hãy dùng MockServletContext cho cấu hình và trạng thái cấp ứng dụng, MockServletConfig hoặc MockFilterConfig cho cấu hình riêng của servlet/filter, request/response/session mock cho tương tác HTTP, và MockMvc cho pipeline Spring MVC. Khi hành vi phụ thuộc vào container hoặc mạng thật, cần kiểm thử tích hợp với embedded server để có bằng chứng phù hợp.
