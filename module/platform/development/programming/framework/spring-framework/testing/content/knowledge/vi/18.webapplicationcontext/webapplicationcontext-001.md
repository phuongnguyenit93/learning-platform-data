# `@WebAppConfiguration` và thư mục gốc tài nguyên web

Trong Spring Test, `@WebAppConfiguration` cho biết bài kiểm thử cần một `WebApplicationContext` gắn với môi trường Servlet. Annotation này giúp Spring tạo một `MockServletContext` để các bean web, bộ điều khiển, bộ phân giải tài nguyên và mã sử dụng `ServletContext` có thể hoạt động trong test. Giá trị của annotation xác định thư mục gốc tài nguyên web được dùng để tạo servlet context đó.

Thư mục gốc tài nguyên web là điểm bắt đầu để phân giải các đường dẫn như `/WEB-INF/views/home.html` hoặc `/static/css/site.css`. Nó độc lập với nơi lưu các file cấu hình Spring được khai báo trong `@ContextConfiguration`. Hiểu rõ sự khác biệt này giúp tránh lỗi không tìm thấy view, file tĩnh hoặc tài nguyên được đọc thông qua `ServletContext` trong các bài kiểm thử tích hợp.

## 1. Vì sao cần `@WebAppConfiguration`?

Một `ApplicationContext` thông thường quản lý bean của Spring nhưng không nhất thiết gắn với một môi trường ứng dụng web. Trong ứng dụng Spring MVC, nhiều thành phần cần một `WebApplicationContext`, là loại application context có liên kết với `ServletContext` và hỗ trợ các thành phần web như request scope, session scope và tài nguyên theo ngữ cảnh servlet.

Khi kiểm thử các thành phần đó, Spring Test cần cung cấp một môi trường web phù hợp. `@WebAppConfiguration` đánh dấu test class để TestContext Framework nạp web application context và tạo servlet context giả lập. Ví dụ:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebTestConfig.class)
class WebApplicationContextTest {
    @Autowired
    private WebApplicationContext webApplicationContext;
}
```

Trong ví dụ trên:

- `@ExtendWith(SpringExtension.class)` tích hợp Spring TestContext Framework với JUnit Jupiter.
- `@ContextConfiguration` chỉ ra cấu hình bean cần nạp cho test.
- `@WebAppConfiguration` yêu cầu môi trường web và một `MockServletContext`.
- `WebApplicationContext` được inject là context web được Spring Test tạo cho test class.

Với JUnit 4, có thể dùng `@RunWith(SpringRunner.class)` thay cho `@ExtendWith(SpringExtension.class)`. `@WebAppConfiguration` thường được sử dụng cùng `@ContextConfiguration` hoặc `@ContextHierarchy` để chỉ định cấu hình cho context.

## 2. Thư mục gốc tài nguyên web là gì?

Thư mục gốc tài nguyên web đại diện cho gốc của ứng dụng web trong `ServletContext`. Giả sử cấu trúc thư mục như sau:

```text
src/test/webapp/
├── index.html
├── static/
│   ├── css/
│   │   └── site.css
│   └── images/
│       └── logo.png
└── WEB-INF/
    └── views/
        └── home.html
```

Nếu `src/test/webapp` được chọn làm resource base path, các đường dẫn tài nguyên trong servlet context được tính từ thư mục đó:

| Đường dẫn trong servlet context | File tương ứng trong test fixture |
| --- | --- |
| `/index.html` | `src/test/webapp/index.html` |
| `/static/css/site.css` | `src/test/webapp/static/css/site.css` |
| `/static/images/logo.png` | `src/test/webapp/static/images/logo.png` |
| `/WEB-INF/views/home.html` | `src/test/webapp/WEB-INF/views/home.html` |

Đường dẫn bắt đầu bằng `/` trong các API của `ServletContext` được hiểu tương đối với gốc servlet context, không phải thư mục làm việc hiện tại của tiến trình và cũng không phải thư mục chứa file cấu hình Spring.

Thư mục `WEB-INF` có quy ước đặc biệt của Servlet: nội dung bên trong không được cung cấp trực tiếp như tài nguyên công khai qua URL thông thường. Tuy vậy, ứng dụng và Spring có thể đọc các file trong đó để phân giải view hoặc tải cấu hình. Vì vậy, test có thể kiểm tra sự tồn tại của `/WEB-INF/views/home.html` thông qua `ServletContext` hoặc `Resource`.

## 3. Giá trị mặc định và cách chọn resource base path

Nếu không truyền giá trị, `@WebAppConfiguration` dùng resource base path mặc định là `file:src/main/webapp`:

```java
@WebAppConfiguration
@ContextConfiguration(classes = WebTestConfig.class)
class DefaultWebRootTest {
}
```

Có thể chỉ định một thư mục khác bằng thuộc tính `value`:

```java
@WebAppConfiguration("file:src/test/webapp")
@ContextConfiguration(classes = WebTestConfig.class)
class TestWebRootTest {
}
```

Trong trường hợp này, Spring dùng `src/test/webapp` làm gốc tài nguyên của `MockServletContext`. Cách làm này hữu ích khi test cần một tập tài nguyên riêng, tránh phụ thuộc vào nội dung web được đóng gói cho môi trường chạy thật.

Spring cũng hỗ trợ resource base path trên classpath:

```java
@WebAppConfiguration("classpath:test-web-resources")
@ContextConfiguration(classes = WebTestConfig.class)
class ClasspathWebRootTest {
}
```

Với cấu hình trên, thư mục tài nguyên tương ứng có thể được đặt tại `src/test/resources/test-web-resources`:

```text
src/test/resources/
└── test-web-resources/
    ├── index.html
    └── WEB-INF/
        └── views/
            └── home.html
```

Hai dạng đường dẫn phổ biến có ý nghĩa khác nhau:

| Prefix | Nguồn tài nguyên | Khi nào nên dùng |
| --- | --- | --- |
| `file:` | Hệ thống file | Test cần dùng trực tiếp một thư mục web trong workspace |
| `classpath:` | Tài nguyên có trên classpath | Test cần fixture được quản lý cùng tài nguyên test và đóng gói theo classpath |

Đối với đường dẫn `file:` tương đối như `file:src/test/webapp`, vị trí được phân giải dựa trên thư mục làm việc của tiến trình chạy test. Vì vậy, cần bảo đảm test được chạy với working directory dự kiến hoặc cấu hình một đường dẫn phù hợp với cách build của dự án. Với `classpath:`, cần bảo đảm thư mục tài nguyên đã được đưa lên test classpath.

Giá trị `@WebAppConfiguration` là một resource location, không phải URL mà trình duyệt sẽ truy cập. Nó cũng không phải vị trí của file cấu hình bean. Không nên truyền đường dẫn đến `dispatcher-servlet.xml` làm resource base path; file cấu hình đó thuộc phạm vi `@ContextConfiguration`.

## 4. Phân biệt `@WebAppConfiguration` và `@ContextConfiguration`

Hai annotation này giải quyết hai việc riêng biệt và thường xuất hiện cùng nhau:

| Annotation | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `@WebAppConfiguration` | Chọn môi trường web và gốc tài nguyên của `ServletContext` giả lập | `file:src/test/webapp` |
| `@ContextConfiguration` | Chọn cấu hình Spring dùng để tạo bean và application context | `WebTestConfig.class` hoặc `classpath:application-context.xml` |

Ví dụ với cấu hình Java:

```java
@Configuration
@EnableWebMvc
@ComponentScan(basePackages = "com.example.web")
class WebTestConfig {
}
```

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration("file:src/test/webapp")
@ContextConfiguration(classes = WebTestConfig.class)
class ProductControllerWebTest {
    @Autowired
    private WebApplicationContext webApplicationContext;
}
```

Ví dụ với cấu hình XML:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration("file:src/test/webapp")
@ContextConfiguration(locations = "classpath:spring/web-test-context.xml")
class XmlConfiguredWebTest {
    @Autowired
    private WebApplicationContext webApplicationContext;
}
```

Trong ví dụ XML, file `web-test-context.xml` là cấu hình Spring được nạp từ classpath. Thư mục `src/test/webapp` vẫn là gốc tài nguyên của servlet context. Thay đổi một giá trị không tự động thay đổi giá trị còn lại.

## 5. `MockServletContext` được tạo và sử dụng như thế nào?

Khi Spring TestContext Framework xử lý test class có `@WebAppConfiguration`, framework tạo một `MockServletContext` dựa trên resource base path. Web application context được nạp với servlet context đó, nhờ vậy bean có thể truy cập môi trường web trong lúc test.

`MockServletContext` triển khai API `ServletContext` ở dạng giả lập. Nó hỗ trợ các thao tác thường dùng trong kiểm thử như lấy resource, lấy đường dẫn thực, truy cập context attribute và cung cấp thông tin môi trường servlet cơ bản. Nó không khởi động Tomcat, Jetty hay một servlet container thật.

Có thể kiểm tra servlet context và đọc tài nguyên như sau:

```java
import jakarta.servlet.ServletContext;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.Resource;
import org.springframework.mock.web.MockServletContext;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.web.context.WebApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration("file:src/test/webapp")
@ContextConfiguration(classes = WebTestConfig.class)
class WebRootResourceTest {
    @Autowired
    private WebApplicationContext webApplicationContext;

    @Test
    void createsMockServletContextWithConfiguredRoot() throws Exception {
        ServletContext servletContext = webApplicationContext.getServletContext();

        assertThat(servletContext).isInstanceOf(MockServletContext.class);
        assertThat(servletContext.getResource("/index.html")).isNotNull();
    }

    @Test
    void resolvesResourceRelativeToWebRoot() {
        Resource view = webApplicationContext.getResource(
                "/WEB-INF/views/home.html");

        assertThat(view.exists()).isTrue();
    }
}
```

Các file được kiểm tra trong ví dụ phải thực sự tồn tại dưới `src/test/webapp`. `getResource()` của `ServletContext` trả về URL hoặc `null` nếu không tìm thấy tài nguyên; `WebApplicationContext.getResource()` trả về đối tượng `Resource`, có thể kiểm tra bằng `exists()`. Đường dẫn có dấu `/` ở đầu được phân giải từ gốc servlet context.

Các import minh họa dùng `jakarta.servlet`, phù hợp với Spring Framework 6 và Spring Boot 3. Với dự án Spring Framework 5 hoặc Spring Boot 2, API Servlet thường thuộc namespace `javax.servlet`; cần dùng import tương ứng với phiên bản của dự án.

## 6. Kiểm tra tài nguyên thông qua `ResourceLoader`

`WebApplicationContext` cũng là một `ResourceLoader`. Vì vậy, test có thể dùng `getResource()` để kiểm tra file view, template hoặc tài nguyên khác trong web root mà không phải tự ghép đường dẫn hệ thống file.

```java
@Test
void canReadAViewTemplate() throws IOException {
    Resource template = webApplicationContext.getResource(
            "/WEB-INF/views/home.html");

    assertThat(template.exists()).isTrue();
    try (InputStream input = template.getInputStream()) {
        String content = new String(input.readAllBytes(), StandardCharsets.UTF_8);
        assertThat(content).contains("Home");
    }
}
```

Để kiểm tra nội dung file, test cần import `java.io.InputStream`, `java.io.IOException` và `java.nio.charset.StandardCharsets`. Với dự án dùng Java trước phiên bản 9, có thể đọc stream bằng cách khác thay cho `readAllBytes()`.

Khi dùng `ServletContextResource` trực tiếp, đường dẫn cũng được tính từ gốc servlet context:

```java
Resource css = new ServletContextResource(
        webApplicationContext.getServletContext(),
        "/static/css/site.css");

assertThat(css.exists()).isTrue();
```

`ServletContextResource` hữu ích khi mã cần thể hiện rõ rằng tài nguyên được lấy từ servlet context. Dùng `webApplicationContext.getResource()` thường gọn hơn và giúp test ít phụ thuộc vào lớp triển khai cụ thể.

## 7. Kết hợp với `MockMvc`

`@WebAppConfiguration` thường được dùng khi kiểm thử Spring MVC cùng `MockMvc`. `MockMvc` gửi request giả lập qua Spring MVC infrastructure đã được nạp trong `WebApplicationContext`, cho phép kiểm tra routing, controller, filter và kết quả HTTP mà không cần mở cổng mạng hoặc khởi động servlet container thật.

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration("file:src/test/webapp")
@ContextConfiguration(classes = WebTestConfig.class)
class HomeControllerTest {
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
    void returnsHomePage() throws Exception {
        mockMvc.perform(get("/home"))
                .andExpect(status().isOk());
    }
}
```

Test này giả định `WebTestConfig` đăng ký controller và các thành phần MVC cần thiết, đồng thời ứng dụng có endpoint `/home`. Các import thường dùng gồm `MockMvc`, `MockMvcBuilders`, `BeforeEach`, `get` và `status` từ những package tương ứng của Spring Test và MockMvc.

Resource base path và URL request là hai khái niệm khác nhau. Ví dụ, file `src/test/webapp/static/css/site.css` có đường dẫn servlet-context là `/static/css/site.css`. Để trình duyệt hoặc MockMvc truy cập file đó qua URL như `/assets/site.css`, ứng dụng còn cần cấu hình resource handler ánh xạ URL tới thư mục tài nguyên:

```java
@Configuration
@EnableWebMvc
class WebTestConfig implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("/static/");
    }
}
```

Với cấu hình trên, request `/assets/css/site.css` được ánh xạ tới tài nguyên `/static/css/site.css` trong servlet context. Chỉ đặt `@WebAppConfiguration("file:src/test/webapp")` không tự tạo URL mapping cho tài nguyên tĩnh; việc ánh xạ vẫn thuộc cấu hình Spring MVC.

## 8. Khi ứng dụng có root context và DispatcherServlet context

Một ứng dụng Spring MVC truyền thống có thể dùng hai tầng context: root context chứa các bean dùng chung như service và repository; context của `DispatcherServlet` chứa controller, handler mapping và view resolver. Khi cần mô phỏng cấu trúc này trong integration test, Spring Test hỗ trợ `@ContextHierarchy`.

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration("file:src/test/webapp")
@ContextHierarchy({
    @ContextConfiguration(name = "root", locations = "classpath:spring/root-context.xml"),
    @ContextConfiguration(name = "dispatcher", locations = "classpath:spring/dispatcher-context.xml")
})
class HierarchicalWebApplicationTest {
    @Autowired
    private WebApplicationContext webApplicationContext;
}
```

Hai cấu hình được đặt trong cùng một context hierarchy: context `dispatcher` là context con và có thể sử dụng bean từ context `root`. `@WebAppConfiguration` cung cấp môi trường servlet cho web context. Chỉ nên dùng hierarchy khi ứng dụng thực sự có ranh giới parent-child; một ứng dụng có một web context đơn giản không cần cấu hình phức tạp này.

Khi kiểm thử hierarchy, cần chú ý context nào chứa bean đang được kiểm tra. Controller thường nằm trong context của `DispatcherServlet`, còn service dùng chung thường nằm trong root context. Inject một bean từ context con có thể nhìn thấy bean ở context cha, nhưng context cha không nhìn thấy bean chỉ được khai báo ở context con.

## 9. Dùng `@WebAppConfiguration` trong dự án Spring Boot

Trong các test Spring Framework truyền thống, `@WebAppConfiguration` kết hợp với `@ContextConfiguration` là cách trực tiếp để tạo `WebApplicationContext` dùng `MockServletContext`.

Với Spring Boot, `@SpringBootTest` có thể tự tạo web application context và môi trường servlet giả lập khi ứng dụng là web application và `webEnvironment` được đặt ở chế độ `MOCK` (đây cũng là giá trị mặc định của `@SpringBootTest`). Khi cần kiểm tra MVC, có thể kết hợp `@AutoConfigureMockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class HomeControllerIntegrationTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void servesHomeEndpoint() throws Exception {
        mockMvc.perform(get("/home"))
                .andExpect(status().isOk());
    }
}
```

Trong cách tiếp cận Spring Boot này, không cần thêm `@WebAppConfiguration` chỉ để có `MockServletContext`; Boot đã cấu hình web context theo `webEnvironment`. Nếu mục tiêu là kiểm tra hành vi khi chạy trên servlet container thật, hãy dùng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` và gửi HTTP request đến server được khởi động cho test. Đây là phạm vi kiểm thử khác với `MockMvc` và `@WebAppConfiguration`.

## 10. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không inject được `WebApplicationContext` | Test chỉ nạp context thông thường hoặc thiếu cấu hình web | Dùng `@WebAppConfiguration` cùng cấu hình context phù hợp |
| `ServletContext.getResource()` trả về `null` | File không nằm dưới resource base path hoặc sai đường dẫn | Kiểm tra cấu trúc thư mục và đường dẫn tính từ web root |
| `Resource.exists()` trả về `false` | Prefix `file:` hoặc `classpath:` trỏ sai vị trí | Kiểm tra working directory hoặc test classpath |
| File cấu hình Spring được nạp nhưng view không tìm thấy | Nhầm `@ContextConfiguration` với resource base path | Đặt file cấu hình trong `@ContextConfiguration`, còn thư mục web trong `@WebAppConfiguration` |
| File tĩnh tồn tại nhưng request trả về 404 | Chưa cấu hình resource handler hoặc URL mapping không khớp | Kiểm tra `addResourceHandlers` và URL request |
| Test hoạt động trên máy cá nhân nhưng lỗi ở CI | Dựa vào đường dẫn file tương đối với working directory khác nhau | Dùng resource path ổn định hoặc tài nguyên classpath |
| Mong đợi JSP được render như trên server nhưng test không làm được | `MockServletContext` không biên dịch và thực thi JSP như servlet container thật | Dùng integration test với container thật cho kiểm thử JSP/deployment |
| Test cần servlet API nhưng context không có bean phù hợp | Cấu hình test chưa tạo web application context | Kiểm tra `@WebAppConfiguration`, context loader và cấu hình web |

Một lỗi phổ biến là chỉ định `@WebAppConfiguration("file:src/test/webapp/WEB-INF")` trong khi mã lại đọc `/WEB-INF/views/home.html`. Khi đó đường dẫn sẽ được tính từ thư mục `WEB-INF` đã chọn làm gốc, dẫn đến việc tìm kiếm sai vị trí. Nếu muốn đường dẫn trong servlet context bắt đầu bằng `/WEB-INF/...`, resource base path phải là thư mục cha chứa `WEB-INF`, ví dụ `file:src/test/webapp`.

Một lỗi khác là giả định rằng resource base path chính là thư mục public static resource. Thực tế, nó đại diện cho toàn bộ web root. Các thư mục `WEB-INF`, `META-INF` hoặc `static` chỉ là các thư mục con theo cấu trúc ứng dụng; cách truy cập từng tài nguyên phụ thuộc vào Servlet API và cấu hình Spring MVC.

## 11. Nguyên tắc tổ chức test web resources

1. Chọn resource base path phản ánh đúng cấu trúc tài nguyên mà test cần kiểm tra. Dùng `src/main/webapp` nếu muốn kiểm tra web root của ứng dụng; dùng `src/test/webapp` nếu cần fixture riêng cho test.
2. Dùng prefix `file:` cho thư mục trên hệ thống file và `classpath:` cho tài nguyên được đưa lên classpath. Bảo đảm đường dẫn tương ứng thực sự tồn tại.
3. Giữ `@WebAppConfiguration` và `@ContextConfiguration` đúng trách nhiệm: một annotation chọn web root, annotation còn lại nạp cấu hình Spring.
4. Dùng `WebApplicationContext.getResource()` hoặc `ServletContext.getResource()` để kiểm tra tài nguyên theo đúng ngữ nghĩa servlet context.
5. Khi kiểm tra URL của file tĩnh, cấu hình và kiểm tra resource handler riêng. Việc file tồn tại trong web root không tự động bảo đảm URL sẽ phục vụ file đó.
6. Dùng `MockMvc` cho kiểm thử Spring MVC không cần server thật; dùng test với server/container thật khi cần kiểm tra deployment, JSP hoặc hành vi phụ thuộc container.
7. Giữ test độc lập với đường dẫn tuyệt đối trên máy cá nhân để có thể chạy ổn định trong CI.

`@WebAppConfiguration` giúp Spring Test tái tạo phần môi trường Servlet cần thiết cho một bài kiểm thử tích hợp. Khi resource base path được chọn đúng và tách biệt với vị trí cấu hình bean, test có thể xác minh việc phân giải tài nguyên, hoạt động của `WebApplicationContext` và xử lý request MVC trong một môi trường giả lập có thể kiểm soát.
