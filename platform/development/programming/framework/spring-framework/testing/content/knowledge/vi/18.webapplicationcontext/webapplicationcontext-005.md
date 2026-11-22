# Chuẩn bị request attributes cho bean phạm vi request

## 1. Vì sao bean phạm vi request cần request attributes?

Trong ứng dụng web Spring, một bean có scope `request` được tạo riêng cho từng HTTP request. Các lần truy cập bean trong cùng request nhận cùng một instance; khi request kết thúc, Spring chạy các callback hủy được đăng ký cho bean đó và loại instance khỏi phạm vi request.

Ví dụ, một ứng dụng có thể lưu thông tin tương quan của request, dữ liệu tạm của biểu mẫu hoặc một đối tượng ngữ cảnh chỉ có ý nghĩa trong một lần gọi HTTP. Những dữ liệu này không nên dùng chung giữa các request đồng thời.

Để thực hiện scope này, Spring cần biết request hiện tại là request nào và nơi lưu các thuộc tính của request. Trong ứng dụng Servlet, thông tin đó được biểu diễn bởi `ServletRequestAttributes` và được cung cấp qua `RequestContextHolder`.

Khi chạy trong luồng xử lý HTTP thông thường, `DispatcherServlet` thiết lập request context cho quá trình xử lý. Một số cách tích hợp khác có thể dùng `RequestContextListener` hoặc `RequestContextFilter`. Trong kiểm thử gọi bean trực tiếp, không có Servlet request tự động đi qua các thành phần này. Vì vậy, bài kiểm thử phải tự tạo request giả và gắn request attributes vào luồng hiện tại.

## 2. Các thành phần liên quan

| Thành phần | Vai trò |
|---|---|
| `RequestAttributes` | Hợp đồng trừu tượng để đọc, ghi và xóa thuộc tính theo scope của request hoặc session. |
| `ServletRequestAttributes` | Adapter của Spring cho `HttpServletRequest` và `HttpServletResponse`; cung cấp request attributes trong môi trường Servlet. |
| `RequestContextHolder` | Giữ `RequestAttributes` hiện hành theo luồng xử lý, để các thành phần như request scope có thể tra cứu request đang hoạt động. |
| `MockHttpServletRequest` | Request Servlet giả của Spring Test, thích hợp để chuẩn bị request trong kiểm thử mà không cần mở cổng HTTP. |
| `@RequestScope` | Khai báo bean có vòng đời gắn với một HTTP request. |

`RequestContextHolder` dùng cơ chế lưu context theo thread. Do đó, việc thiết lập attributes trên một thread không tự động làm cho request context có mặt trên một thread khác. Cũng vì đặc điểm này, kiểm thử phải dọn context sau khi chạy để tránh rò rỉ trạng thái sang test tiếp theo.

## 3. Thiết lập request attributes trong kiểm thử

Quy trình cơ bản gồm bốn bước:

1. Tạo một `MockHttpServletRequest`.
2. Bọc request đó bằng `ServletRequestAttributes`.
3. Đăng ký attributes với `RequestContextHolder` trước khi truy cập request-scoped bean.
4. Kết thúc request và xóa context trong khối `finally`.

Ví dụ dưới đây minh họa một bean lưu mã tương quan trong phạm vi request. Khi được gọi nhiều lần trong cùng request, bean trả về cùng mã; request khác có instance và mã riêng.

```java
import java.util.UUID;

import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestCorrelation {

    private final String id = UUID.randomUUID().toString();

    public String id() {
        return id;
    }
}
```

Nếu bean được tiêm qua scoped proxy, proxy sẽ tra cứu instance thuộc request hiện hành khi phương thức được gọi. Điều này cho phép một singleton khác giữ tham chiếu đến proxy mà vẫn nhận đúng instance theo từng request.

Một kiểm thử tập trung có thể thiết lập request context trực tiếp như sau:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

@SpringJUnitConfig
@WebAppConfiguration
class RequestCorrelationTest {

    @Configuration
    @Import(RequestCorrelation.class)
    static class TestConfig {
    }

    @Autowired
    private RequestCorrelation correlation;

    @Test
    void usesOneInstanceWithinARequestAndANewInstanceForAnotherRequest() {
        String firstRequestId = invokeInRequest();
        String secondRequestId = invokeInRequest();

        assertNotEquals(firstRequestId, secondRequestId);
    }

    private String invokeInRequest() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        ServletRequestAttributes attributes = new ServletRequestAttributes(request);

        RequestContextHolder.setRequestAttributes(attributes);
        try {
            String firstCall = correlation.id();
            String secondCall = correlation.id();

            assertEquals(firstCall, secondCall);
            return firstCall;
        } finally {
            attributes.requestCompleted();
            RequestContextHolder.resetRequestAttributes();
        }
    }
}
```

Đoạn kiểm thử trên giả định `correlation` là bean được lấy từ một Spring web application context đã đăng ký request scope. Trong một dự án thực tế, có thể dùng `@SpringJUnitConfig` kết hợp cấu hình web context, hoặc dùng `@SpringBootTest` nếu cần kiểm thử cấu hình ứng dụng. Không thể chỉ tạo một đối tượng Java bằng `new RequestCorrelation()` rồi kỳ vọng `@RequestScope` tự hoạt động: scope được quản lý bởi Spring container.

Nếu muốn kiểm tra hai request một cách tường minh trong cùng một test, hãy gọi bean trong hai lần thiết lập context riêng như ví dụ. Mỗi lần tạo `ServletRequestAttributes` mới tương ứng với một request mới. Việc gọi bean hai lần khi cùng attributes đang được gắn sẽ kiểm tra tính ổn định của instance trong cùng request.

## 4. Đọc và ghi thuộc tính request trực tiếp

Đôi khi mục tiêu của kiểm thử là xác minh một thành phần đọc thuộc tính đã được đặt sẵn trên request. Có thể thiết lập thuộc tính trên mock request trước khi gắn attributes:

```java
MockHttpServletRequest request = new MockHttpServletRequest();
request.setAttribute("tenantId", "tenant-42");

ServletRequestAttributes attributes = new ServletRequestAttributes(request);
RequestContextHolder.setRequestAttributes(attributes);
try {
    Object tenantId = RequestContextHolder.currentRequestAttributes()
            .getAttribute("tenantId", RequestAttributes.SCOPE_REQUEST);

    // Thực hiện assertion với tenantId.
} finally {
    attributes.requestCompleted();
    RequestContextHolder.resetRequestAttributes();
}
```

Trong ví dụ này, `RequestAttributes.SCOPE_REQUEST` xác định phạm vi lưu trữ là request. `RequestContextHolder.currentRequestAttributes()` trả về context đã gắn với thread hiện tại. Nếu chưa thiết lập context, phương thức này ném `IllegalStateException` vì không có request attributes đang hoạt động.

Có thể dùng `RequestContextHolder.setRequestAttributes(attributes, true)` để bật chế độ `InheritableThreadLocal`. Tuy nhiên, không nên dùng tùy chọn này như cách khắc phục chung cho xử lý bất đồng bộ: thread pool tái sử dụng thread và vòng đời request có thể không trùng với vòng đời tác vụ. Với tác vụ chạy nền, hãy truyền dữ liệu cần thiết một cách tường minh hoặc dùng cơ chế truyền context được thiết kế riêng.

## 5. Dọn dẹp đúng vòng đời

Hai thao tác dọn dẹp trong ví dụ có mục đích khác nhau:

- `attributes.requestCompleted()` báo cho `ServletRequestAttributes` rằng quá trình xử lý request đã hoàn tất. Nó cho phép thực thi các callback hoàn tất request và callback hủy thuộc tính đã đăng ký.
- `RequestContextHolder.resetRequestAttributes()` xóa context khỏi thread hiện tại, tránh để request của test trước ảnh hưởng đến test sau.

Đặt cả hai thao tác trong `finally` để chúng vẫn chạy khi assertion hoặc code được kiểm thử ném exception. Nếu chỉ xóa context mà không báo hoàn tất request, các callback vòng đời có thể không được gọi như mong đợi. Nếu chỉ báo hoàn tất mà không reset holder, thread vẫn có thể giữ tham chiếu đến attributes cũ.

Không nên gọi `resetRequestAttributes()` trước khi code cần request context đã chạy xong. Khi cần kiểm thử nhiều request tuần tự, hãy hoàn tất và reset request hiện tại trước khi gắn attributes cho request tiếp theo.

## 6. Khi nào nên dùng MockMvc?

Thiết lập `RequestContextHolder` thủ công phù hợp khi kiểm thử một bean hoặc service cần request context mà không cần mô phỏng toàn bộ quá trình dispatch HTTP. Nếu cần kiểm tra controller, filter, interceptor, argument resolver hoặc luồng xử lý HTTP tích hợp, nên dùng `MockMvc`.

`MockMvc` gửi request qua chuỗi xử lý Spring MVC trong môi trường mock Servlet. `DispatcherServlet` thiết lập và quản lý request context trong quá trình dispatch, vì vậy bài kiểm thử thường không cần tự gọi `RequestContextHolder.setRequestAttributes()`.

Ví dụ kiểm thử controller bằng `MockMvc`:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RequestControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void handlesRequestWithRequestScopedDependencies() throws Exception {
        mockMvc.perform(get("/request-info"))
                .andExpect(status().isOk());
    }
}
```

Đường dẫn `/request-info` ở đây là ví dụ và cần tồn tại trong ứng dụng đang kiểm thử. Nếu bài kiểm thử chỉ cần xác nhận một bean lấy được request attribute đã chuẩn bị, cách thiết lập thủ công ngắn và tập trung hơn. Nếu cần xác nhận hành vi ở biên HTTP, `MockMvc` cung cấp độ bao phủ phù hợp hơn.

## 7. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `No thread-bound request found` hoặc `IllegalStateException` khi lấy request attributes | Code truy cập request scope ngoài request đang hoạt động hoặc test chưa gắn attributes. | Tạo `ServletRequestAttributes` và gọi `RequestContextHolder.setRequestAttributes()` trước khi truy cập bean; hoặc chạy qua `MockMvc`. |
| `Scope 'request' is not active` | Bean được gọi khi request scope chưa hoạt động, hoặc bean không được quản lý trong web application context phù hợp. | Kiểm tra context đã đăng ký web scope và request context đã được thiết lập đúng thời điểm. |
| Test chạy riêng thì qua nhưng chạy cả bộ thì lỗi hoặc phụ thuộc thứ tự | Request attributes cũ còn gắn trên thread do thiếu cleanup. | Dùng `try/finally`, gọi `requestCompleted()` và `resetRequestAttributes()`. |
| Hai request bất ngờ dùng chung dữ liệu | Dữ liệu được đặt trong singleton/static field, hoặc test tái sử dụng cùng request attributes. | Tạo request và attributes mới cho mỗi request; giữ dữ liệu riêng trong request-scoped bean hoặc request attributes. |
| Tác vụ chạy nền không thấy request context | Request context gắn với thread xử lý request và không tự động truyền an toàn sang thread pool. | Truyền dữ liệu cần thiết tường minh hoặc thiết kế cơ chế context propagation phù hợp với tác vụ. |

Một điểm cần phân biệt: `@RequestScope` và việc đọc một thuộc tính từ `HttpServletRequest` có liên quan nhưng không đồng nhất. `@RequestScope` điều khiển vòng đời instance bean trong Spring. `request.setAttribute(...)` chỉ đặt một giá trị vào request hiện tại. Một bean có thể dùng request attributes, nhưng việc đặt một thuộc tính không tự biến một bean thông thường thành request-scoped bean.

## 8. Checklist khi viết test

- [ ] Bean cần kiểm thử được tạo và quản lý bởi Spring container có hỗ trợ web scope.
- [ ] Mỗi request giả có một `MockHttpServletRequest` và `ServletRequestAttributes` tương ứng.
- [ ] Request context được gắn trước lần truy cập đầu tiên vào request-scoped bean hoặc proxy.
- [ ] Các lần truy cập trong cùng request được thực hiện khi cùng attributes còn hoạt động.
- [ ] Request được hoàn tất và `RequestContextHolder` được reset trong `finally`.
- [ ] Test tạo request mới khi cần xác minh dữ liệu hoặc instance không chia sẻ giữa các request.
- [ ] Dùng `MockMvc` nếu mục tiêu là kiểm tra chuỗi xử lý HTTP của Spring MVC.

## 9. Kết luận

Để kiểm thử bean phạm vi request độc lập với máy chủ web, hãy tạo `MockHttpServletRequest`, bọc nó bằng `ServletRequestAttributes` và gắn vào `RequestContextHolder` trước khi gọi bean. Sau khi kiểm thử, hoàn tất attributes và xóa context trong `finally`. Cách làm này tái hiện phần request context mà request scope cần, đồng thời giữ các test độc lập và có vòng đời rõ ràng.
