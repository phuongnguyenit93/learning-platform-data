# Kiểm thử bean phạm vi session với MockHttpSession

## 1. Mục tiêu của bài kiểm thử

Một bean có scope **@SessionScope** có một target instance riêng cho mỗi HTTP session. Các request thuộc cùng một session dùng chung target đó; hai session khác nhau nhận hai target khác nhau. Vì vậy, một bài kiểm thử có ý nghĩa cần chứng minh được cả hai hành vi:

- Trạng thái được giữ lại khi cùng một session gửi nhiều request.
- Trạng thái của session này không xuất hiện trong session khác.

**MockHttpSession** thuộc Spring Test, mô phỏng **HttpSession** trong bộ nhớ. Có thể truyền cùng một đối tượng **MockHttpSession** vào nhiều request MockMvc để kiểm tra vòng đời của bean theo session mà không cần khởi chạy servlet container thật.

## 2. Cách hoạt động của session scope

Có thể khai báo bean bằng **@SessionScope** trên component:

~~~java
@Component
@SessionScope
public class UserPreferences {
    // Trạng thái riêng của một HTTP session
}
~~~

Hoặc khai báo trên phương thức **@Bean**:

~~~java
@Bean
@SessionScope
Cart cart() {
    return new Cart();
}
~~~

**@SessionScope** là cách viết gọn cho scope **WebApplicationContext.SCOPE_SESSION** và mặc định dùng scoped proxy kiểu class. Proxy có thể được inject vào một singleton bean như controller. Khi một request đang hoạt động gọi phương thức trên proxy, Spring tìm target tương ứng trong HTTP session hiện tại; nếu session chưa có target thì Spring tạo target và lưu nó vào session.

Điều này tạo ra ba đặc điểm cần kiểm thử:

1. Controller có thể giữ proxy trong suốt vòng đời của application context.
2. Hai request có cùng **HttpSession** sẽ truy cập cùng target bean.
3. Hai request có **HttpSession** khác nhau sẽ truy cập target bean khác nhau.

Target của session-scoped bean chỉ có thể được phân giải khi có request context đang hoạt động. Nếu gọi proxy từ một đoạn test thông thường bên ngoài request, Spring không biết session hiện tại là session nào và có thể báo scope chưa hoạt động. Dùng MockMvc sẽ tạo request context trong quá trình dispatch.

**@SessionScope** mặc định tạo class proxy, vì vậy class được proxy không nên là **final**. Nếu muốn dùng JDK interface proxy, có thể khai báo **@SessionScope(proxyMode = ScopedProxyMode.INTERFACES)** và inject qua interface tương ứng.

### Phân biệt với @SessionAttributes

**@SessionScope** quản lý vòng đời của một Spring bean theo HTTP session. **@SessionAttributes** là cơ chế của Spring MVC để giữ các model attribute của controller qua nhiều request trong một luồng xử lý.

Hai cơ chế đều sử dụng HTTP session nhưng có mục đích khác nhau. Bài này kiểm tra bean được khai báo với **@SessionScope**; nếu mục tiêu là kiểm tra model attribute do **@SessionAttributes** lưu, cần kiểm tra luồng controller và các model attribute đó.

## 3. MockHttpSession và MockMvc

**MockHttpSession** là một implementation mô phỏng **HttpSession**. Nó cho phép đặt, đọc và xóa session attribute, đồng thời có thể được tái sử dụng qua nhiều request.

Điểm quan trọng nhất khi kiểm tra session scope bằng MockMvc là truyền **cùng một đối tượng session** vào từng request:

~~~java
MockHttpSession session = new MockHttpSession();

mockMvc.perform(post("/cart/items/book").session(session));
mockMvc.perform(get("/cart/items").session(session));
~~~

MockMvc tạo một mock request mới cho mỗi lần **perform**. Lời gọi **.session(session)** gắn cùng đối tượng **HttpSession** vào request mới đó. Vì Spring lưu target của session-scoped bean trong session, request thứ hai sẽ truy cập lại target đã được tạo ở request đầu tiên.

Không nên tạo một **new MockHttpSession()** cho từng request nếu mục tiêu là kiểm tra trạng thái được giữ lại. Mỗi session mới đại diện cho một người dùng hoặc một phiên làm việc khác.

Cũng cần phân biệt hai cách thiết lập dữ liệu:

- **.session(session)** truyền một session cụ thể để có thể tái sử dụng qua nhiều request.
- **.sessionAttr("key", value)** thiết lập một session attribute cho request. Cách này tiện khi cần chuẩn bị dữ liệu đầu vào, nhưng tự nó không chứng minh rằng nhiều request đang dùng cùng một session object.

**MockHttpSession** mô phỏng phần session phía server trong bộ nhớ. Nó không mô phỏng đầy đủ cookie của trình duyệt, trao đổi mạng, timeout thực tế hoặc hành vi lưu session của một servlet container thật.

## 4. Ví dụ ứng dụng cần kiểm thử

Ví dụ dưới đây xây dựng một giỏ hàng đơn giản. Mỗi HTTP session có một **Cart** riêng. Controller là singleton nhưng nhận scoped proxy của **Cart**.

### Bean Cart

~~~java
import java.util.ArrayList;
import java.util.List;

public class Cart {

    private final List<String> items = new ArrayList<>();

    public void add(String itemId) {
        items.add(itemId);
    }

    public List<String> items() {
        return List.copyOf(items);
    }
}
~~~

### Controller

~~~java
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/cart")
public class CartController {

    private final Cart cart;

    public CartController(Cart cart) {
        this.cart = cart;
    }

    @PostMapping("/items/{id}")
    public ResponseEntity<Void> add(@PathVariable String id) {
        cart.add(id);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/items")
    public List<String> items() {
        return cart.items();
    }
}
~~~

### Cấu hình WebApplicationContext

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.context.annotation.SessionScope;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class WebConfig {

    @Bean
    @SessionScope
    Cart cart() {
        return new Cart();
    }

    @Bean
    CartController cartController(Cart cart) {
        return new CartController(cart);
    }
}
~~~

Phương thức **cart()** tạo bean theo session scope. Khi Spring tạo **CartController**, dependency được inject là scoped proxy. Target **Cart** thật sẽ được lấy theo session của request đang xử lý.

Trong ví dụ trả JSON, ứng dụng cần có JSON message converter, thường được cung cấp bởi Jackson. Với Spring Boot, dependency **spring-boot-starter-web** thường đã cung cấp cấu hình cần thiết.

## 5. Kiểm thử bằng MockMvc và MockHttpSession

Đây là cách phù hợp khi muốn kiểm tra cả wiring của **WebApplicationContext**, controller mapping và hành vi session scope trong một request flow.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebConfig.class)
class CartSessionScopeTest {

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
    void shouldKeepCartStateAcrossRequestsInTheSameSession() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mockMvc.perform(post("/cart/items/{id}", "book")
                        .session(session))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/cart/items")
                        .session(session))
                .andExpect(status().isOk())
                .andExpect(content().json("[\"book\"]"));
    }

    @Test
    void shouldIsolateCartStateBetweenDifferentSessions() throws Exception {
        MockHttpSession firstSession = new MockHttpSession();
        MockHttpSession secondSession = new MockHttpSession();

        mockMvc.perform(post("/cart/items/{id}", "book")
                        .session(firstSession))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/cart/items")
                        .session(firstSession))
                .andExpect(status().isOk())
                .andExpect(content().json("[\"book\"]"));

        mockMvc.perform(get("/cart/items")
                        .session(secondSession))
                .andExpect(status().isOk())
                .andExpect(content().json("[]"));
    }
}
~~~

Test thứ nhất gửi request thêm sản phẩm rồi gửi request đọc giỏ hàng với cùng **MockHttpSession**. Kết quả phải chứa sản phẩm đã thêm. Điều này chứng minh target bean được giữ lại qua các request trong cùng session.

Test thứ hai tạo hai session độc lập. Request thêm sản phẩm chỉ dùng **firstSession**. Khi đọc bằng **secondSession**, giỏ hàng phải rỗng; khi đọc lại bằng **firstSession**, sản phẩm vẫn còn. Hai assertion này kiểm tra cả tính cô lập lẫn khả năng duy trì trạng thái.

**@WebAppConfiguration** yêu cầu Spring Test tạo một **WebApplicationContext**. Đây là môi trường phù hợp cho web scope. **MockMvcBuilders.webAppContextSetup(...)** dùng context đó để cấu hình các thành phần MVC và dispatch request. Nếu chỉ dùng một **ApplicationContext** thông thường, web scope có thể chưa được đăng ký đúng.

### Nếu session được ứng dụng tạo trong request đầu tiên

Không nhất thiết phải tạo session trước test. Nếu request đầu tiên tự tạo session, có thể lấy session từ request sau khi thực hiện:

~~~java
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

MvcResult result = mockMvc.perform(post("/cart/items/{id}", "book"))
        .andExpect(status().isNoContent())
        .andReturn();

MockHttpSession session =
        (MockHttpSession) result.getRequest().getSession(false);
~~~

Sau đó truyền **session** vào các request tiếp theo bằng **.session(session)**. Cần kiểm tra session khác **null** trước khi dùng nếu ứng dụng không đảm bảo tạo session ở request đầu tiên.

## 6. Kiểm tra bean trực tiếp mà không dispatch controller

Trong một số trường hợp, chỉ cần kiểm tra việc phân giải target của session-scoped bean. Khi đó có thể kết hợp **MockHttpSession**, **MockHttpServletRequest** và **RequestContextHolder**.

Ví dụ sau giả định test đã nạp một **WebApplicationContext** có khai báo bean **Cart** với **@SessionScope** như cấu hình ở trên:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import static org.assertj.core.api.Assertions.assertThat;

class CartScopeUnitTest {

    @Autowired
    private Cart cart; // Đây là scoped proxy được Spring inject.

    @Test
    void shouldResolveTheSameTargetForRequestsInOneSession() {
        MockHttpSession session = new MockHttpSession();

        try {
            ServletRequestAttributes firstRequest = bind(session);
            try {
                cart.add("book");
            } finally {
                firstRequest.requestCompleted();
            }

            ServletRequestAttributes secondRequest = bind(session);
            try {
                assertThat(cart.items()).containsExactly("book");
            } finally {
                secondRequest.requestCompleted();
            }
        } finally {
            RequestContextHolder.resetRequestAttributes();
        }
    }

    private ServletRequestAttributes bind(MockHttpSession session) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setSession(session);

        ServletRequestAttributes attributes =
                new ServletRequestAttributes(request);
        RequestContextHolder.setRequestAttributes(attributes);
        return attributes;
    }
}
~~~

Ở đây, mỗi lần gọi **bind(session)** tạo một mock request mới nhưng gắn cùng **MockHttpSession**. **RequestContextHolder** đưa request attributes vào thread hiện tại để scoped proxy biết session nào đang được sử dụng. Khối **finally** gọi **requestCompleted()** và **resetRequestAttributes()** để dọn request context kể cả khi assertion thất bại.

Cách này kiểm tra trực tiếp scope resolution và hữu ích cho một test hẹp ở tầng bean. Nó không kiểm tra controller mapping, argument resolver, message converter hoặc toàn bộ quá trình dispatch của MVC. Khi cần xác nhận luồng web hoạt động như ứng dụng thực tế, nên ưu tiên bài kiểm thử MockMvc ở phần trước.

## 7. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Gọi session-scoped bean báo scope chưa hoạt động | Truy cập scoped proxy khi không có request context | Thực hiện qua MockMvc hoặc bind **ServletRequestAttributes** trong test trực tiếp |
| Trạng thái biến mất giữa hai request | Mỗi request dùng một **MockHttpSession** mới | Tạo một session và truyền lại bằng **.session(session)** |
| Bean không được phân giải đúng trong test | Context không phải **WebApplicationContext** | Dùng **@WebAppConfiguration** cùng **@ContextConfiguration** |
| Controller không nhận đúng session-scoped target | Bean thiếu scoped proxy khi được inject vào singleton | Dùng **@SessionScope**, hoặc khai báo **@Scope** với **proxyMode** phù hợp |
| Test kiểm tra được session attribute nhưng không chứng minh scope của bean | Chỉ dùng **.sessionAttr(...)** hoặc kiểm tra trực tiếp một key trong session | Gửi nhiều request bằng cùng session và kiểm tra hành vi công khai của bean |
| Test pass nhưng người dùng khác vẫn dùng chung dữ liệu | Ứng dụng vô tình lưu trạng thái vào singleton bean khác hoặc static field | Kiểm tra nguồn lưu trạng thái và thêm assertion với hai session riêng biệt |

Không nên phụ thuộc vào tên attribute nội bộ mà Spring dùng để lưu scoped target trong **HttpSession**. Tên đó là chi tiết triển khai của scoped proxy. Hãy kiểm tra hành vi qua controller hoặc API công khai của bean.

Cũng không nên gọi một phương thức trên session-scoped proxy trong **@BeforeEach** trước khi có request context. Có thể inject proxy vào test mà không lỗi, nhưng target chỉ được phân giải khi gọi phương thức. Hãy thực hiện lời gọi đó bên trong request MockMvc hoặc trong vùng đã bind **RequestContextHolder**.

Một session có thể được nhiều request đồng thời sử dụng. Session scope đảm bảo target gắn với session, nhưng không tự làm cho trạng thái mutable bên trong bean trở nên thread-safe. Nếu nhiều request đồng thời có thể cập nhật cùng một **Cart** hoặc **UserPreferences**, thiết kế bean vẫn cần xử lý đồng thời phù hợp.

## 8. Chọn cách kiểm thử phù hợp

| Mục tiêu | Cách làm |
|---|---|
| Kiểm tra trạng thái tồn tại qua nhiều request cùng session | MockMvc và tái sử dụng **.session(session)** |
| Kiểm tra dữ liệu của hai session được cô lập | Tạo hai **MockHttpSession** khác nhau |
| Chuẩn bị một session attribute cho request | **.sessionAttr("key", value)** hoặc **session.setAttribute(...)** |
| Kiểm tra riêng việc phân giải target bean | **MockHttpServletRequest** + **ServletRequestAttributes** + **RequestContextHolder** |
| Kiểm tra cookie, timeout và hành vi của servlet container thật | Integration test chạy với embedded hoặc deployed servlet container |

Với Spring Boot, có thể dùng **@SpringBootTest** kết hợp **@AutoConfigureMockMvc**, inject **MockMvc** trực tiếp rồi áp dụng cùng nguyên tắc: tạo một **MockHttpSession** và truyền lại session đó cho mọi request cần thuộc cùng phiên.

Một bài kiểm thử session scope tốt luôn xác định rõ session nào đang được dùng ở từng request. Khi cùng session giữ được trạng thái và session khác không nhìn thấy trạng thái đó, test đã xác nhận được hai thuộc tính quan trọng nhất của **@SessionScope**.

