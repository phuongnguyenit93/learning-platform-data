# Tiêm WebApplicationContext và các đối tượng web mock

Khi kiểm thử một ứng dụng Spring MVC, ta thường cần cả hai phần: Spring container để lấy controller, service và cấu hình web; các đối tượng Servlet để mô phỏng request, response, session và servlet context. Spring Test kết hợp hai phần này bằng `WebApplicationContext` và nhóm mock web objects trong `spring-test`.

`WebApplicationContext` cho phép test truy cập application context dành cho ứng dụng web. Các lớp như `MockHttpServletRequest`, `MockHttpServletResponse` và `MockHttpSession` cung cấp những đối tượng Servlet có thể điều khiển trực tiếp trong test. Với kiểm thử luồng MVC đầy đủ, `MockMvc` dùng chính các đối tượng mock đó để đưa request qua `DispatcherServlet` mà không cần khởi động máy chủ HTTP thật.

## 1. WebApplicationContext là gì?

`WebApplicationContext` là biến thể của `ApplicationContext` dành cho môi trường web Servlet. Ngoài khả năng quản lý bean như một Spring application context thông thường, nó còn liên kết với một `ServletContext`.

Từ `WebApplicationContext`, ứng dụng có thể truy cập:

- Các bean đã được đăng ký trong web application context, chẳng hạn controller, service, handler mapping và view resolver.
- `ServletContext` đại diện cho môi trường web của ứng dụng.
- Các khả năng phụ thuộc vào môi trường web như request scope, session scope và tài nguyên theo web context.

Trong ứng dụng Spring MVC, `DispatcherServlet` nhận request và điều phối đến controller. `WebApplicationContext` cung cấp cấu hình và các bean mà tầng web cần dùng. Một ứng dụng có thể có root context dùng chung và context con gắn với `DispatcherServlet`; cấu trúc cụ thể phụ thuộc cách ứng dụng cấu hình.

Trong test, việc tiêm `WebApplicationContext` giúp ta xây dựng `MockMvc` từ đúng cấu hình web của ứng dụng. Tiêm `ServletContext` cũng giúp kiểm tra những thành phần cần biết môi trường Servlet.

## 2. Tạo WebApplicationContext cho test

Với Spring TestContext Framework, hai annotation thường được dùng cùng nhau là:

- `@ContextConfiguration`: chỉ định cấu hình hoặc lớp cấu hình dùng để tạo context.
- `@WebAppConfiguration`: yêu cầu Spring tạo `WebApplicationContext` cho test thay vì application context thông thường.

Khi không truyền đường dẫn cho `@WebAppConfiguration`, resource base path mặc định là `src/main/webapp`. Có thể chỉ định một thư mục tài nguyên khác, ví dụ `@WebAppConfiguration("src/test/webapp")`. Spring Test dùng `MockServletContext` để cung cấp môi trường Servlet giả lập cho context này.

Với JUnit Jupiter, `@ExtendWith(SpringExtension.class)` kết nối JUnit 5 với Spring TestContext:

```java
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = WebTestConfig.class)
@WebAppConfiguration
class GreetingControllerTests {
    // Các dependency của test sẽ được Spring tiêm vào.
}
```

`WebTestConfig` là lớp cấu hình Spring MVC. Ví dụ:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = GreetingController.class)
class WebTestConfig {
}
```

`@EnableWebMvc` đăng ký hạ tầng Spring MVC cơ bản; `@ComponentScan` tìm controller và các component trong package chứa `GreetingController`. Trong dự án thực tế, test thường tham chiếu lớp cấu hình đã được ứng dụng sử dụng để bảo đảm kiểm thử đúng cấu hình đang chạy.

## 3. Tiêm WebApplicationContext và ServletContext

Khi Spring tạo web test context, test có thể tiêm `WebApplicationContext` và `ServletContext` bằng `@Autowired`:

```java
import jakarta.servlet.ServletContext;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.context.WebApplicationContext;

class GreetingControllerTests {

    @Autowired
    private WebApplicationContext webApplicationContext;

    @Autowired
    private ServletContext servletContext;
}
```

`WebApplicationContext` cũng cung cấp `getServletContext()`, vì vậy có thể kiểm tra hai tham chiếu cùng trỏ đến servlet context của web application:

```java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(webApplicationContext.getServletContext())
    .isSameAs(servletContext);
```

Trong các component cần truy cập Servlet API, Spring còn hỗ trợ các cơ chế như `ServletContextAware` để nhận `ServletContext`. Tuy nhiên, service nghiệp vụ thông thường nên nhận các dependency nghiệp vụ rõ ràng; không nên truyền `ServletContext` xuyên qua các tầng chỉ để đọc dữ liệu không liên quan đến môi trường web.

## 4. Các đối tượng web mock của Spring

Spring Test cung cấp nhiều lớp trong package `org.springframework.mock.web`. Chúng triển khai hoặc mô phỏng các API Servlet để test có thể thiết lập dữ liệu và kiểm tra kết quả mà không cần servlet container thật.

| Đối tượng mock | API được mô phỏng | Mục đích thường gặp |
|---|---|---|
| `MockServletContext` | `ServletContext` | Môi trường chung của ứng dụng web, context attributes và tài nguyên web |
| `MockServletConfig` | `ServletConfig` | Tên servlet, `ServletContext` và init parameters |
| `MockHttpServletRequest` | `HttpServletRequest` | HTTP method, URI, parameters, headers, attributes và session |
| `MockHttpServletResponse` | `HttpServletResponse` | Status, headers, cookies và response body |
| `MockHttpSession` | `HttpSession` | Session attributes và trạng thái session |

Các lớp mock này cho phép test thiết lập trạng thái theo ý muốn. Ví dụ, test có thể đặt parameter, header hoặc session attribute trước khi gọi thành phần đang kiểm thử, sau đó kiểm tra status hay dữ liệu được ghi vào response.

### MockServletContext và MockServletConfig

`MockServletContext` đại diện cho servlet context dùng chung. Nó hữu ích khi một component cần đọc context attribute hoặc truy cập tài nguyên web. `MockServletConfig` đại diện cho cấu hình của một servlet cụ thể và cung cấp tên servlet cùng các init parameter.

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.mock.web.MockServletConfig;
import org.springframework.mock.web.MockServletContext;

MockServletContext servletContext = new MockServletContext();

MockServletConfig servletConfig =
    new MockServletConfig(servletContext, "exampleServlet");
servletConfig.addInitParameter("mode", "test");

assertThat(servletConfig.getServletName()).isEqualTo("exampleServlet");
assertThat(servletConfig.getInitParameter("mode")).isEqualTo("test");
```

Trong test dùng `@WebAppConfiguration`, Spring Test thường tạo và quản lý `MockServletContext` cho `WebApplicationContext`. Không cần tự tạo một context khác nếu mục tiêu là kiểm tra bean đã được tiêm vào web test context.

### MockHttpServletRequest, MockHttpServletResponse và MockHttpSession

Các đối tượng HTTP mock có thể được tạo trực tiếp để kiểm tra một filter, adapter hoặc component Servlet ở mức thấp:

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockServletContext;

MockServletContext servletContext = new MockServletContext();

MockHttpServletRequest request =
    new MockHttpServletRequest(servletContext);
request.setMethod("POST");
request.setRequestURI("/orders");
request.setParameter("customerId", "C-208");
request.addHeader("X-Request-Source", "test");

MockHttpSession session = new MockHttpSession(servletContext);
session.setAttribute("userId", "U-17");
request.setSession(session);

MockHttpServletResponse response = new MockHttpServletResponse();
response.setStatus(HttpServletResponse.SC_CREATED);
response.addHeader("X-Result", "created");

assertThat(request.getParameter("customerId")).isEqualTo("C-208");
assertThat(request.getSession().getAttribute("userId")).isEqualTo("U-17");
assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_CREATED);
assertThat(response.getHeader("X-Result")).isEqualTo("created");
```

Ví dụ này chỉ tạo và kiểm tra trạng thái của các đối tượng Servlet mock. Nó chưa gọi `DispatcherServlet`, chưa chạy controller và cũng chưa chứng minh một request HTTP có thể đi qua toàn bộ ứng dụng.

## 5. Dùng WebApplicationContext để tạo MockMvc

Đối với kiểm thử controller và luồng Spring MVC, `MockMvc` thường là lựa chọn phù hợp hơn việc tự gọi controller hoặc tự ghép request và response. `MockMvc` gửi request qua `DispatcherServlet` được cấu hình bằng Spring MVC, sử dụng các servlet mock ở bên dưới và trả về kết quả để test assertion.

Tạo `MockMvc` từ `WebApplicationContext` bằng `MockMvcBuilders.webAppContextSetup(...)`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

class GreetingControllerTests {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .build();
    }
}
```

Giả sử ứng dụng có controller sau:

```java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
class GreetingController {

    @GetMapping("/greeting")
    @ResponseBody
    String greeting(
            @RequestParam(defaultValue = "friend") String name) {
        return "Hello " + name;
    }
}
```

Test có thể gửi request và kiểm tra response như sau:

```java
import org.junit.jupiter.api.Test;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void returnsGreetingForRequestedName() throws Exception {
    mockMvc.perform(get("/greeting").param("name", "Mai"))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello Mai"));
}
```

Request builder tạo request mock; `DispatcherServlet` xử lý request bằng các bean trong web application context; result matcher kiểm tra HTTP status và response body. Test không cần mở cổng mạng hoặc gửi request qua một server đang chạy.

`webAppContextSetup` dùng cấu hình web đã nạp trong context, nên thích hợp khi cần kiểm tra sự phối hợp của controller, handler mapping, converter, exception resolver và các thành phần MVC khác. Nếu filter cần được áp dụng trong MockMvc, hãy đăng ký filter theo cấu hình test phù hợp, chẳng hạn thông qua `addFilters(...)` của builder hoặc cấu hình kiểm thử đang dùng.

## 6. Chọn webAppContextSetup hay standaloneSetup

Hai cách tạo `MockMvc` phục vụ hai phạm vi kiểm thử khác nhau:

| Cách tạo | Cấu hình được sử dụng | Khi nào phù hợp |
|---|---|---|
| `webAppContextSetup(webApplicationContext)` | Web application context đã được Spring nạp | Kiểm thử tích hợp MVC với cấu hình và bean thật của ứng dụng |
| `standaloneSetup(controller)` | Đăng ký controller trực tiếp cùng cấu hình tối thiểu | Kiểm thử tập trung một hoặc vài controller mà không cần nạp toàn bộ web context |

Nếu mục tiêu của bài test là xác nhận Spring đã tạo `WebApplicationContext`, đã tiêm đúng bean và MVC hoạt động với cấu hình ứng dụng, hãy dùng `webAppContextSetup`. `standaloneSetup` không lấy cấu hình từ `WebApplicationContext`, vì vậy không thể dùng nó để xác nhận việc tiêm hoặc khởi tạo web context.

## 7. Dùng Spring Boot trong kiểm thử web

Với ứng dụng Spring Boot kiểu Servlet, có thể dùng cấu hình test tích hợp do Boot cung cấp:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

@SpringBootTest
@AutoConfigureMockMvc
class GreetingControllerBootTests {

    @Autowired
    private WebApplicationContext webApplicationContext;

    @Autowired
    private MockMvc mockMvc;

    @Test
    void webContextIsAvailable() {
        assertThat(webApplicationContext.getServletContext()).isNotNull();
    }
}
```

Với ứng dụng web Servlet, `@SpringBootTest` mặc định dùng web environment kiểu mock; `@AutoConfigureMockMvc` cấu hình và cung cấp `MockMvc` để tiêm vào test. Trong kiểu cấu hình này, Boot tạo web context và MockMvc theo cơ chế tự động của nó. Thông thường không cần thêm `@WebAppConfiguration` hoặc tự gọi `MockMvcBuilders.webAppContextSetup(...)` lần nữa.

Nếu ứng dụng không phải ứng dụng web Servlet, không thể mặc định giả định rằng `WebApplicationContext` sẽ tồn tại. Hãy xác nhận loại ứng dụng và web environment trước khi tiêm các Servlet API.

## 8. Những giới hạn cần hiểu khi dùng mock web objects

Các đối tượng mock rất hữu ích nhưng không phải servlet container hoàn chỉnh:

- Chúng không mở cổng HTTP và không kiểm tra giao tiếp qua mạng.
- Chúng không chứng minh cấu hình triển khai của Tomcat, Jetty hoặc container khác hoạt động đúng.
- Việc một mock request có parameter hoặc session attribute không tự động chứng minh browser, proxy hay container thật sẽ tạo request tương tự.
- Tạo `MockHttpServletRequest` trực tiếp không tự chạy filter chain, `DispatcherServlet`, interceptor hoặc controller.
- `MockMvc` kiểm thử pipeline Spring MVC trong môi trường mock; các khác biệt phụ thuộc container thật vẫn cần kiểm thử ở môi trường phù hợp.

Nếu cần kiểm tra request đi qua server thật, hãy dùng một kiểu kiểm thử khởi động server, chẳng hạn Spring Boot `@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)`, rồi gửi HTTP request đến server đó. Đây là phạm vi khác với kiểm thử bằng `MockMvc`.

## 9. Lỗi thường gặp và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Không tiêm được `WebApplicationContext` | Test context chưa được cấu hình như web context; kiểm tra `@WebAppConfiguration` hoặc cấu hình Spring Boot và loại ứng dụng |
| Không tìm thấy controller hoặc handler | Cấu hình component scan chưa bao gồm controller, hoặc cấu hình MVC chưa được nạp |
| `webAppContextSetup` không nhận được context | Chưa tiêm `WebApplicationContext` hoặc đang dùng application context không phải web context |
| Test dùng `standaloneSetup` nhưng mong cấu hình ứng dụng được áp dụng | `standaloneSetup` không sử dụng web application context; chuyển sang `webAppContextSetup` nếu cần cấu hình đầy đủ |
| Test trực tiếp component có request scope nhưng không có request hiện hành | Component đang được gọi ngoài request lifecycle; dùng `MockMvc` hoặc thiết lập request context phù hợp cho kiểu test đó |
| Test mock thành công nhưng triển khai thật gặp lỗi container | Mock không kiểm tra đầy đủ hành vi của servlet container; bổ sung kiểm thử với server thật khi yêu cầu cần điều đó |

Khi điều tra lỗi, hãy xác định test đang kiểm tra lớp nào: một Servlet API object, một filter, controller riêng lẻ, toàn bộ Spring MVC context hay server triển khai. Chọn đúng cấp kiểm thử sẽ giúp tránh kết luận sai từ một mock quá đơn giản.

## 10. Quy trình chọn công cụ kiểm thử

1. Nếu cần bean và cấu hình web của ứng dụng, tạo `WebApplicationContext` bằng `@WebAppConfiguration` kết hợp `@ContextConfiguration`, hoặc dùng cấu hình test web của Spring Boot.
2. Nếu cần truy cập môi trường web, tiêm `WebApplicationContext` hoặc `ServletContext`.
3. Nếu chỉ cần kiểm tra trạng thái của Servlet API object, tạo `MockHttpServletRequest`, `MockHttpServletResponse`, `MockHttpSession` hoặc mock tương ứng.
4. Nếu cần gửi request qua Spring MVC, tạo `MockMvc` bằng `webAppContextSetup` và kiểm tra kết quả bằng request/result matchers.
5. Nếu cần xác nhận hành vi của server hoặc servlet container thật, dùng kiểm thử khởi động server thay vì dựa vào mock.

`WebApplicationContext` cung cấp nền tảng Spring cho môi trường web; các web mock objects mô phỏng Servlet API; `MockMvc` kết nối hai phần để kiểm tra request qua Spring MVC. Hiểu đúng vai trò của từng phần giúp test kiểm tra đúng phạm vi và tránh nhầm kết quả mock với hành vi của một server thật.
