# MockServletContext và ranh giới container Servlet mô phỏng

Trong một ứng dụng web Spring, `WebApplicationContext` cần một môi trường web để quản lý các bean liên quan đến Servlet. Trong ứng dụng đang chạy, Servlet container như Tomcat, Jetty hoặc Undertow cung cấp môi trường đó thông qua các API Servlet, trong đó có `ServletContext`.

Khi kiểm thử, ta thường không cần khởi động cả máy chủ web chỉ để xác nhận một bean đọc được application init parameter hoặc Spring MVC ánh xạ một URL đến controller. Spring cung cấp `MockServletContext` cùng nhiều đối tượng Servlet mô phỏng khác để tạo môi trường web ngay trong tiến trình test.

Điểm cần hiểu rõ là `MockServletContext` mô phỏng hợp đồng lập trình của `ServletContext`. Nó giúp kiểm tra cách ứng dụng tương tác với API Servlet, nhưng bản thân nó không phải Tomcat thu nhỏ và không thực hiện toàn bộ công việc của một Servlet container.

## 1. ServletContext trong một ứng dụng web

Theo Servlet API, mỗi web application có một `ServletContext`. Các servlet, filter và listener thuộc cùng web application có thể dùng context này để truy cập thông tin và tài nguyên ở phạm vi ứng dụng.

Một số trách nhiệm thường gặp của `ServletContext` gồm:

- Cung cấp context path của web application.
- Đọc application initialization parameters được khai báo trong cấu hình triển khai hoặc thiết lập lúc khởi tạo.
- Lưu và lấy application attributes để các thành phần trong cùng web application chia sẻ đối tượng.
- Truy cập tài nguyên thuộc web application thông qua các phương thức như `getResource`, `getResourceAsStream` và `getResourcePaths`.
- Cung cấp thông tin về Servlet container và phiên bản Servlet API.
- Hỗ trợ một số thao tác đăng ký servlet, filter, listener và các thành phần liên quan trong giai đoạn khởi tạo ứng dụng, tùy phiên bản Servlet API.

`ServletContext` có phạm vi ứng dụng. Nó khác với `HttpServletRequest`, vốn đại diện cho một request cụ thể; `HttpSession`, vốn đại diện cho phiên của một client; và `ServletConfig`, vốn chứa cấu hình khởi tạo của một servlet cụ thể.

Spring đưa `ServletContext` vào môi trường ứng dụng web thông qua `WebApplicationContext`. Vì vậy, bean triển khai `ServletContextAware` có thể nhận được context này, còn các thành phần Spring MVC có thể sử dụng hạ tầng web được khởi tạo trong cùng môi trường.

## 2. MockServletContext là gì?

`MockServletContext` là implementation phục vụ kiểm thử của Spring, nằm trong package `org.springframework.mock.web` thuộc module `spring-test`. Nó triển khai giao diện `jakarta.servlet.ServletContext` ở các phiên bản Spring Framework hiện đại; các phiên bản Spring cũ dùng namespace `javax.servlet` tương ứng.

Đây là một đối tượng có trạng thái và hành vi đơn giản, được thiết kế để dùng trong test. Chẳng hạn, test có thể thiết lập init parameter, thêm application attribute rồi gọi các phương thức đọc tương ứng. Vì vậy, dù tên lớp có chữ “Mock”, nó không phải một Mockito mock được tạo bằng `Mockito.mock(ServletContext.class)`. Nó là một implementation mô phỏng có sẵn của Spring.

Ví dụ sử dụng trực tiếp:

```java
import org.springframework.mock.web.MockServletContext;

class MockServletContextTest {

    @Test
    void storesApplicationParametersAndAttributes() {
        MockServletContext servletContext = new MockServletContext();
        servletContext.setInitParameter("app.mode", "test");
        servletContext.setAttribute("feature.enabled", Boolean.TRUE);

        assertThat(servletContext.getInitParameter("app.mode"))
                .isEqualTo("test");
        assertThat(servletContext.getAttribute("feature.enabled"))
                .isEqualTo(Boolean.TRUE);
    }
}
```

Ví dụ này kiểm tra code sử dụng API `ServletContext` có đọc được các giá trị đã thiết lập hay không. Không có web server, cổng HTTP hoặc kết nối mạng nào được mở. Test cũng không chứng minh một container thật sẽ nạp đúng file triển khai hay thực hiện đúng toàn bộ vòng đời ứng dụng.

### Những đối tượng mock web liên quan

Spring Test cung cấp một nhóm implementation mô phỏng Servlet API để các test có thể ghép thành môi trường web phù hợp:

| Đối tượng | Vai trò được mô phỏng |
| --- | --- |
| `MockServletContext` | Context ở phạm vi toàn web application |
| `MockServletConfig` | Cấu hình khởi tạo của một servlet và liên kết với `ServletContext` |
| `MockHttpServletRequest` | HTTP request, gồm method, URI, headers, parameters, attributes và session liên quan |
| `MockHttpServletResponse` | HTTP response, gồm status, headers, cookies và body |
| `MockHttpSession` | Trạng thái session trong test |
| `MockFilterConfig` | Cấu hình khởi tạo của filter |
| `MockFilterChain` | Chuỗi filter và servlet được gọi trong test |
| `MockRequestDispatcher` | Đối tượng mô phỏng thao tác forward hoặc include |

Không phải test nào cũng cần tạo tất cả các đối tượng này. Nên chọn đúng lớp mô phỏng theo API mà thành phần đang kiểm tra sử dụng. Khi kiểm thử Spring MVC ở cấp request, `MockMvc` thường là lớp tiện ích phù hợp hơn việc tự nối từng mock object.

## 3. MockServletContext trong WebApplicationContext

`WebApplicationContext` mở rộng `ApplicationContext` cho môi trường web. Ngoài khả năng quản lý bean, nó có liên kết với `ServletContext` của web application. Khi chạy trong container thật, `ServletContext` được container cung cấp. Khi dùng Spring TestContext Framework với `@WebAppConfiguration`, Spring tạo một `MockServletContext` cho bài kiểm thử.

Ví dụ kiểm tra context web:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mock.web.MockServletContext;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.web.context.WebApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = TestWebConfig.class)
class WebApplicationContextTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    @Test
    void createsWebApplicationContextWithMockServletContext() {
        assertThat(webApplicationContext.getServletContext())
                .isInstanceOf(MockServletContext.class);
    }
}
```

`TestWebConfig` là lớp cấu hình Spring của ứng dụng kiểm thử. `@WebAppConfiguration` đánh dấu rằng Spring Test cần tạo một `WebApplicationContext`, thay vì một context thông thường. Context này được liên kết với `MockServletContext` để các bean web có thể được khởi tạo trong test.

Mặc định, `@WebAppConfiguration` dùng thư mục `file:src/main/webapp` làm resource base path. Có thể chỉ định một đường dẫn khác khi test cần truy cập tài nguyên web ở vị trí riêng:

```java
@WebAppConfiguration("src/test/webapp")
@ContextConfiguration(classes = TestWebConfig.class)
class WebResourcesTest {
    // Các test cần đọc tài nguyên từ src/test/webapp.
}
```

Resource base path giúp `MockServletContext` tìm tài nguyên web trong phạm vi được cấu hình. Nó không tự biến thư mục đó thành một ứng dụng được deploy trong Tomcat. Nếu test cần xác nhận cách đóng gói WAR, cấu hình deployment descriptor hoặc cách container phục vụ tài nguyên, phải kiểm tra trong môi trường triển khai tương ứng.

### Bean nhận ServletContext qua ServletContextAware

Một bean có thể triển khai `ServletContextAware` để nhận context khi Spring tạo bean:

```java
import jakarta.servlet.ServletContext;
import org.springframework.web.context.ServletContextAware;

public class ApplicationMode implements ServletContextAware {

    private ServletContext servletContext;

    @Override
    public void setServletContext(ServletContext servletContext) {
        this.servletContext = servletContext;
    }

    public String getMode() {
        return servletContext.getInitParameter("app.mode");
    }
}
```

Trong một unit test thuần, có thể tạo bean và `MockServletContext` rồi gọi `setServletContext` trực tiếp. Trong một test tích hợp với `WebApplicationContext`, Spring sẽ thực hiện callback này trong quá trình khởi tạo bean. Cách thứ hai còn xác nhận việc tích hợp giữa bean, Spring context và Servlet context.

Lưu ý namespace import trong ví dụ. Nếu dự án sử dụng Spring Framework 5 hoặc nền tảng Servlet cũ, thay `jakarta.servlet.ServletContext` bằng `javax.servlet.ServletContext`. Không trộn hai namespace trong cùng một ứng dụng: chúng là hai kiểu Java khác nhau dù có tên lớp giống nhau.

## 4. Dùng MockServletContext khi kiểm thử Spring MVC

`MockServletContext` thường là một phần của môi trường mà Spring MVC test sử dụng. Với `MockMvc`, test có thể gửi request mô phỏng qua `DispatcherServlet`, chạy các thành phần Spring MVC đã cấu hình và kiểm tra response mà không cần mở HTTP server.

Có hai cách thiết lập `MockMvc` phổ biến:

- `standaloneSetup(...)`: tạo môi trường MVC tập trung quanh controller được chỉ định. Cách này phù hợp cho kiểm thử controller với cấu hình tối thiểu.
- `webAppContextSetup(webApplicationContext)`: dùng cấu hình Spring MVC từ `WebApplicationContext`, bao gồm các bean và thành phần web đã được nạp trong context.

Ví dụ dùng `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebMvcTestConfig.class)
class ProductControllerTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void returnsSuccessfulResponseForProductPage() throws Exception {
        mockMvc.perform(get("/products"))
                .andExpect(status().isOk());
    }
}
```

Ví dụ giả định `WebMvcTestConfig` đã cấu hình controller và các phụ thuộc cần thiết, còn endpoint `/products` trả về HTTP 200 khi được gọi với dữ liệu test phù hợp. `MockMvc` tạo request và response mô phỏng, sau đó gọi luồng xử lý Spring MVC trong cùng tiến trình. Nó không gửi request qua socket đến cổng của một server đang lắng nghe.

Với Spring Boot, `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)` kết hợp `@AutoConfigureMockMvc` cũng tạo môi trường web mô phỏng để kiểm thử qua `MockMvc`. Tên `MOCK` ở đây mô tả kiểu web environment của test: không khởi chạy embedded server để nhận HTTP request thực.

## 5. Ranh giới của Servlet container được mô phỏng

`MockServletContext` hữu ích vì nó cho phép code chạy với một đối tượng đáp ứng API Servlet mà không cần một container thật. Nhưng nó chỉ mô phỏng những hành vi mà Spring Test triển khai. Một số phần quan trọng của container nằm ngoài phạm vi đó.

### Những gì có thể kiểm tra bằng mock web environment

- Bean có nhận đúng `ServletContext` thông qua `ServletContextAware` hay không.
- Code có đọc đúng application init parameter và application attribute hay không.
- Code có truy cập tài nguyên thông qua các phương thức được `MockServletContext` hỗ trợ hay không.
- `WebApplicationContext` có được khởi tạo và liên kết với mock context hay không.
- Spring MVC có ánh xạ request mô phỏng đến controller, gọi interceptor, converter, argument resolver và exception handler đã cấu hình hay không.
- Controller hoặc filter được đưa vào chuỗi test có tạo status, header và response body mong đợi hay không.

Các kết quả này có giá trị để kiểm tra logic ứng dụng và tích hợp bên trong Spring. Chúng không chứng minh container thật triển khai toàn bộ hành vi giống hệt.

### Những gì cần container thật để xác nhận

| Hành vi cần xác nhận | Vì sao mock context chưa đủ |
| --- | --- |
| Khởi động Tomcat, Jetty hoặc Undertow | `MockServletContext` không khởi chạy container hay connector |
| Lắng nghe cổng và xử lý kết nối HTTP/TLS | Test mock không mở socket và không thực hiện giao tiếp mạng |
| Deploy WAR và đọc cấu hình triển khai thực tế | Mock context không thay thế quy trình deploy của container |
| Thứ tự khởi tạo servlet, filter, listener trong môi trường triển khai | Mock có thể hỗ trợ một số API đăng ký, nhưng không tái hiện đầy đủ startup lifecycle của container |
| Hành vi session cookie, URL rewriting và quản lý session ở cấp container | `MockHttpSession` chỉ mô phỏng trạng thái session trong test |
| Multipart parsing, giới hạn upload và xử lý request ở tầng connector | Request mock không đi qua bộ phân tích request của container |
| Error page, welcome file, security constraint và cấu hình triển khai | Đây là các hành vi phụ thuộc cấu hình và runtime của container |
| JSP compilation, WebSocket và tích hợp container cụ thể | Cần runtime hỗ trợ các tính năng đó |
| Async request và các chi tiết concurrency phụ thuộc container | Mock có thể mô phỏng một phần API async nhưng không tái hiện scheduling và runtime thực |

Danh sách này không có nghĩa mọi hành vi trong bảng đều luôn cần kiểm tra bằng một bộ test lớn. Chỉ cần chọn môi trường container thật khi ứng dụng phụ thuộc vào hành vi đó hoặc khi cần xác nhận khả năng triển khai và vận hành.

### Ví dụ về một test có thể xanh nhưng ứng dụng vẫn lỗi khi deploy

Giả sử controller test dùng `MockMvc` và nhận được status 200. Điều đó cho thấy Spring MVC đã xử lý request mô phỏng theo cấu hình test. Nhưng khi triển khai ứng dụng, WAR có thể thiếu một tài nguyên, filter có thể được khai báo sai trong deployment descriptor, context path có thể khác dự kiến, hoặc container có thể không khởi tạo được một listener. Các lỗi này không nhất thiết xuất hiện trong `MockMvc` test vì request chưa đi qua quá trình deploy và startup của container.

Tương tự, test dùng `MockServletContext` có thể đọc được một init parameter do test tự thiết lập. Điều đó chứng minh bean đọc giá trị từ API đúng cách; nó không chứng minh tham số đã được khai báo đúng trong cấu hình triển khai production.

## 6. Chọn đúng cấp độ kiểm thử

Nên chọn cách test dựa trên câu hỏi cần trả lời, thay vì chọn mock hoặc server theo thói quen.

| Mục tiêu | Cách tiếp cận phù hợp |
| --- | --- |
| Kiểm tra một lớp chỉ đọc init parameter từ `ServletContext` | Unit test với `MockServletContext` |
| Kiểm tra bean web được tạo trong môi trường Spring web | Spring TestContext với `@WebAppConfiguration` |
| Kiểm tra controller, mapping và các thành phần Spring MVC đã cấu hình | `MockMvc`, thường dùng `webAppContextSetup` khi cần toàn bộ web context |
| Kiểm tra controller độc lập với cấu hình toàn ứng dụng | `MockMvcBuilders.standaloneSetup(...)` |
| Kiểm tra ứng dụng nhận HTTP request qua embedded server | `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc `DEFINED_PORT` |
| Kiểm tra WAR triển khai trên Tomcat/Jetty bên ngoài | Deploy artifact vào container mục tiêu và chạy test qua HTTP |

Một chiến lược thường gặp là dùng nhiều cấp độ với số lượng phù hợp:

1. Unit test nhanh cho logic thuần Java và các bean chỉ cần một phần API Servlet.
2. Spring MVC test với `MockMvc` cho routing, binding, validation, interceptor, filter đã thêm vào test và response.
3. Một số integration test với embedded server để kiểm tra luồng HTTP thực qua runtime được đóng gói cùng ứng dụng.
4. Nếu production deploy lên container ngoài hoặc sử dụng tính năng đặc thù, chạy thêm kiểm thử trên đúng loại container và cấu hình triển khai.

Không cần nâng tất cả test lên mức server thật. Khởi động container làm test tốn thời gian và phụ thuộc môi trường hơn; chỉ nên dùng khi nó kiểm tra được một rủi ro mà mock environment không thể đại diện.

## 7. Các lưu ý khi dùng MockServletContext

### Thêm đúng dependency

Các lớp `MockServletContext`, `MockHttpServletRequest` và `MockMvc` thuộc hệ sinh thái Spring Test. Trong dự án Spring Boot, dependency `spring-boot-starter-test` thường đưa `spring-test` vào test classpath. Nếu dùng Spring Framework trực tiếp, cần khai báo module `spring-test` với scope test.

Ví dụ Gradle:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
}
```

Hãy dùng phiên bản `spring-test` tương thích với phiên bản Spring Framework chính của dự án. Với Spring Boot, nên để dependency management của Spring Boot quản lý phiên bản thay vì tự chọn một phiên bản khác.

### Không nhầm application attribute với init parameter

Init parameter là giá trị cấu hình dạng chuỗi được thiết lập cho web application. Application attribute là đối tượng được đặt vào context trong thời gian chạy. Hai loại dữ liệu có mục đích và vòng đời khác nhau:

```java
servletContext.setInitParameter("app.region", "test");
String region = servletContext.getInitParameter("app.region");

servletContext.setAttribute("current.config", configObject);
Object config = servletContext.getAttribute("current.config");
```

Không nên dùng application attribute để giả lập init parameter nếu code production gọi `getInitParameter`, hoặc ngược lại. Test phải thiết lập đúng loại dữ liệu mà ứng dụng thực sự sử dụng.

### Chú ý tài nguyên và đường dẫn

Nếu code dùng `ServletContext.getResource(...)` hoặc `getResourceAsStream(...)`, hãy cấu hình resource base path và đặt tài nguyên test ở vị trí phù hợp. Việc một đường dẫn đọc được từ `MockServletContext` chỉ xác nhận cách truy cập trong môi trường mock. Cần thêm test triển khai nếu đường dẫn đó phụ thuộc cấu trúc WAR hoặc cách container đóng gói tài nguyên.

### Tránh chia sẻ trạng thái giữa các test

Application attributes và các đối tượng trong mock context có thể giữ trạng thái. Nếu nhiều test dùng chung một `MockServletContext`, giá trị được đặt trong test trước có thể ảnh hưởng test sau. Tạo context mới cho mỗi test độc lập hoặc chủ động dọn trạng thái sau khi sử dụng. Khi dùng Spring TestContext, lưu ý context cache có thể tái sử dụng application context giữa các test có cấu hình tương đương; không nên thay đổi trạng thái dùng chung một cách tùy tiện.

### Đừng kiểm tra implementation nội bộ thay cho hành vi ứng dụng

Một test chỉ khẳng định đối tượng là `MockServletContext` giúp minh họa môi trường do Spring Test tạo ra, nhưng bản thân assertion đó không phải mục tiêu nghiệp vụ của mọi test. Trong phần lớn trường hợp, hãy kiểm tra điều ứng dụng cần làm: đọc đúng tham số, khởi tạo bean đúng, trả về response đúng hoặc xử lý request đúng. Kiểu lớp cụ thể chỉ nên được kiểm tra khi đó chính là điều bài test cần xác nhận.

## 8. Kết luận

`MockServletContext` cung cấp một implementation Servlet context dành cho kiểm thử, cho phép Spring tạo `WebApplicationContext` và chạy các bài test web mà không cần khởi động Servlet container. Kết hợp với các mock request/response và `MockMvc`, nó hỗ trợ kiểm tra nhiều hành vi bên trong Spring MVC ngay trong tiến trình test.

Ranh giới của nó nằm ở runtime của container. `MockServletContext` không mở cổng HTTP, không deploy ứng dụng, không thực hiện đầy đủ startup lifecycle, và không thay thế việc kiểm tra các tính năng phụ thuộc Tomcat, Jetty, Undertow hoặc cấu hình production. Hãy dùng mock environment để kiểm tra logic và tích hợp Spring; dùng embedded server hoặc container triển khai thật khi câu hỏi kiểm thử liên quan đến HTTP runtime và hành vi của container.
