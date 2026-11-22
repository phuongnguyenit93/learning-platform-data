# defaultRequest, alwaysExpect và tùy chỉnh chung

Khi một test suite sử dụng `MockMvc`, nhiều request thường có cùng một số đặc điểm: cùng `Accept` header, locale, context path, thông tin người dùng hoặc các header phục vụ kiểm thử. Nhiều test cũng cần kiểm tra một số điều kiện chung trên mọi response, chẳng hạn status thành công hoặc header bảo mật luôn phải tồn tại. Nếu lặp lại các thiết lập đó trong từng lời gọi `perform(...)`, test sẽ dài và dễ thiếu nhất quán.

Spring MVC Test cho phép cấu hình các quy tắc dùng chung ngay trên `MockMvcBuilder`. Ba phương thức quan trọng là:

- `defaultRequest(...)`: thiết lập request mặc định được kế thừa bởi mỗi request gửi qua `MockMvc`.
- `alwaysExpect(...)`: đăng ký một `ResultMatcher` phải được áp dụng sau mỗi request.
- `alwaysDo(...)`: đăng ký một `ResultHandler` được thực thi sau mỗi request, thường dùng để in request/response hoặc ghi nhận thông tin phục vụ chẩn đoán.

Ngoài ra, builder có thể đăng ký filter, `MockMvcConfigurer` và các tùy chỉnh cho `DispatcherServlet`. Các cấu hình này giúp mọi request trong cùng một `MockMvc` có môi trường kiểm thử nhất quán.

## 1. Cấu hình MockMvcBuilder một lần

`MockMvc` được tạo từ builder. Ta có thể kết hợp nhiều phương thức cấu hình trước khi gọi `build()`:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.Locale;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

class ApiControllerTests {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .defaultRequest(get("/")
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Test-Client", "mock-mvc")
                .locale(Locale.US))
            .alwaysExpect(status().isOk())
            .alwaysDo(print())
            .build();
    }
}
```

Trong ví dụ, mỗi request được gửi qua `mockMvc` nhận các giá trị mặc định đã khai báo. Sau khi request hoàn tất, Spring áp dụng matcher kiểm tra status và gọi handler để in chi tiết kết quả. Test không cần viết lại các thiết lập chung này trong từng phương thức kiểm thử.

Đoạn mã minh họa cách ghép builder; trong một test class hoàn chỉnh cần thêm các import JUnit tương ứng, chẳng hạn `@BeforeEach`, `@Test` và các static assertion cần dùng.

## 2. Thiết lập request mặc định bằng defaultRequest

`defaultRequest(RequestBuilder)` nhận một request builder làm mẫu. Các thuộc tính của request mặc định được áp dụng vào từng request được thực hiện bởi `MockMvc` đó. Request cụ thể vẫn cung cấp URI và có thể khai báo các giá trị riêng cho trường hợp đang kiểm tra.

Các thiết lập thường dùng gồm:

- `accept(...)` để đặt loại nội dung client chấp nhận.
- `contentType(...)` để đặt loại nội dung của request có body.
- `header(...)` để thêm header chung.
- `locale(...)` để đặt locale của request.
- `contextPath(...)`, `servletPath(...)` hoặc thông tin session/principal khi test cần mô phỏng môi trường tương ứng.

Ví dụ, một API nội bộ luôn nhận JSON và các request trong test đều có header đánh dấu nguồn gửi:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .defaultRequest(get("/")
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Test-Client", "mock-mvc"))
    .build();
```

Sau đó, test chỉ cần mô tả phần riêng của request:

```java
mockMvc.perform(get("/api/profile"))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/orders"))
    .andExpect(status().isOk());
```

Cả hai request đều kế thừa `Accept: application/json` và `X-Test-Client: mock-mvc`. URI của từng request vẫn đến từ `get("/api/profile")` hoặc `get("/api/orders")`.

### Request cụ thể có thể ghi đè giá trị mặc định

Khi một test cần khác biệt so với mặc định, hãy khai báo giá trị đó trên request cụ thể. Ví dụ sau dùng header và locale làm dữ liệu đầu vào của controller:

```java
import java.util.Locale;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

record RequestContext(String client, String language) {
}

@RestController
class RequestContextController {

    @GetMapping("/api/request-context")
    RequestContext requestContext(
            @RequestHeader("X-Test-Client") String client,
            Locale locale) {
        return new RequestContext(client, locale.toLanguageTag());
    }
}
```

Với cấu hình mặc định ở phần trước, test có thể xác nhận giá trị mặc định được sử dụng:

```java
mockMvc.perform(get("/api/request-context"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.client").value("mock-mvc"))
    .andExpect(jsonPath("$.language").value("en-US"));
```

Một request riêng có thể thay header và locale:

```java
mockMvc.perform(get("/api/request-context")
        .header("X-Test-Client", "mobile-test")
        .locale(Locale.CANADA))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.client").value("mobile-test"))
    .andExpect(jsonPath("$.language").value("en-CA"));
```

Kết quả cho thấy request builder cụ thể có thể cung cấp thiết lập riêng khi cần. Vì vậy, `defaultRequest` phù hợp cho những giá trị thực sự chung; các dữ liệu thay đổi theo kịch bản nên được đặt ngay trong `perform(...)` để ý định của test rõ ràng.

### Lưu ý khi chọn giá trị mặc định

Không nên đưa mọi thuộc tính vào request mặc định. Chỉ đặt những giá trị mà hầu hết request trong phạm vi `MockMvc` đó thực sự cần. Một số điểm cần cân nhắc:

- Không đặt `contentType` mặc định nếu cùng một `MockMvc` kiểm thử cả request JSON, form và request không có body.
- Không đặt session hoặc principal dùng chung nếu các test cần người dùng hay trạng thái xác thực khác nhau.
- Tránh dùng giá trị mặc định khiến test trông như đã kiểm tra một điều kiện mà thực tế test không chủ động thiết lập.
- Nếu nhiều nhóm endpoint có quy tắc mặc định khác nhau, tạo builder hoặc cấu hình `MockMvc` riêng cho từng nhóm thay vì làm một cấu hình chung quá rộng.

## 3. Áp dụng matcher cho mọi request bằng alwaysExpect

`alwaysExpect(ResultMatcher)` đăng ký một matcher được thực hiện cho mỗi request. Đây là nơi phù hợp để kiểm tra các điều kiện bất biến trong phạm vi của một `MockMvc`.

Ví dụ, nếu toàn bộ test trong một nhóm chỉ gọi các endpoint thành công, có thể áp dụng status `200 OK` một lần:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .alwaysExpect(status().isOk())
    .build();
```

Các test vẫn có thể bổ sung assertion riêng:

```java
mockMvc.perform(get("/api/profile"))
    .andExpect(jsonPath("$.active").value(true));

mockMvc.perform(get("/api/settings"))
    .andExpect(jsonPath("$.theme").value("dark"));
```

Mỗi request đều phải thỏa `status().isOk()` trước khi các assertion riêng hoàn tất. Nếu một response trả về status khác, matcher chung sẽ làm test thất bại ngay cả khi test không gọi `andExpect(status()...)` trực tiếp.

Các điều kiện chung khác có thể là header luôn được thêm bởi filter, kiểu nội dung của một API JSON hoặc một điều kiện bảo mật áp dụng cho toàn bộ endpoint trong nhóm test. Ví dụ:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .alwaysExpect(header().exists("X-Content-Type-Options"))
    .build();
```

Matcher trên chỉ hợp lý nếu ứng dụng thực sự cam kết header đó xuất hiện trong mọi response thuộc phạm vi test. Hãy chọn điều kiện có ý nghĩa nghiệp vụ hoặc cấu hình rõ ràng, tránh biến giả định của test thành quy tắc chung không đúng với mọi endpoint.

### Không dùng matcher chung cho các response có chủ đích khác nhau

Một test suite có thể kiểm tra cả `200`, `400`, `401`, `404` hoặc `500`. Nếu gắn `alwaysExpect(status().isOk())` vào một `MockMvc` dùng cho tất cả các trường hợp, các test kiểm tra lỗi sẽ thất bại vì matcher chung.

Có ba cách xử lý:

1. Chỉ đăng ký matcher chung cho một nhóm request mà điều kiện đó luôn đúng.
2. Tạo các cấu hình `MockMvc` riêng cho nhóm endpoint hoặc nhóm kịch bản khác nhau.
3. Giữ assertion status ở từng test nếu status thay đổi theo kịch bản.

`alwaysExpect` nên mô tả hợp đồng chung thật sự, không phải kết quả mong đợi của một test đơn lẻ.

## 4. Chạy ResultHandler chung bằng alwaysDo

`alwaysDo(ResultHandler)` đăng ký hành động được gọi sau mỗi request. Một cách dùng phổ biến là `print()` để in request, handler, model, exception và response trong quá trình debug:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .alwaysDo(print())
    .build();
```

Khác với `alwaysExpect`, `alwaysDo` dùng để thực hiện thao tác trên kết quả. Nó không thay thế assertion và bản thân việc in response không làm test thất bại khi dữ liệu sai.

Có thể kết hợp hai phương thức:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .alwaysExpect(status().isOk())
    .alwaysDo(print())
    .build();
```

Khi đó, mỗi request vừa được kiểm tra status, vừa được in chi tiết. Trong test suite lớn, in mọi request có thể tạo rất nhiều log. Chỉ bật `alwaysDo(print())` khi cần điều tra hoặc khi lượng log vẫn có thể đọc được; nếu không, hãy dùng `andDo(print())` ở đúng test cần xem.

## 5. Đăng ký filter và cấu hình dùng chung

`MockMvcBuilder` còn cho phép đăng ký filter để filter được áp dụng trong quá trình xử lý request. Điều này hữu ích khi kiểm tra filter xử lý encoding, correlation id, CORS hoặc xác thực.

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .addFilters(requestIdFilter, characterEncodingFilter)
    .defaultRequest(get("/").accept(MediaType.APPLICATION_JSON))
    .build();
```

Các filter được đăng ký trên builder thuộc pipeline của `MockMvc` đó. Hãy chú ý thứ tự filter nếu hành vi phụ thuộc thứ tự thực thi. Nếu ứng dụng dùng Spring Security, có thể áp dụng cấu hình tích hợp của Spring Security Test:

```java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
```

Ví dụ này yêu cầu dự án có Spring Security và dependency kiểm thử tương ứng. `springSecurity()` đăng ký tích hợp filter chain và các hỗ trợ kiểm thử bảo mật của Spring Security. Chỉ thêm cấu hình này khi ứng dụng thực sự dùng Spring Security.

Builder cũng cung cấp `addDispatcherServletCustomizer(...)` khi cần điều chỉnh cấu hình của `DispatcherServlet` được tạo cho `MockMvc`. Đây là mức tùy chỉnh thấp hơn; chỉ sử dụng khi một thiết lập của servlet là một phần của hành vi cần kiểm tra. Các cấu hình MVC thông thường nên được đặt trong application context để test phản ánh cấu hình ứng dụng.

## 6. Kết hợp các tùy chỉnh thành một cấu hình có chủ đích

Một cấu hình dùng chung thường kết hợp request mặc định, matcher chung và filter:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .addFilters(requestIdFilter)
    .defaultRequest(get("/")
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Test-Client", "mock-mvc"))
    .alwaysExpect(status().isOk())
    .build();
```

Khi đọc cấu hình này, có thể phân biệt rõ ba phạm vi:

| Cấu hình | Tác động | Câu hỏi nó trả lời |
|---|---|---|
| `addFilters(...)` | Request đi qua filter đã đăng ký | Filter có tham gia xử lý request không? |
| `defaultRequest(...)` | Request kế thừa các thuộc tính mặc định | Mọi request bắt đầu với header, locale hoặc thuộc tính nào? |
| `alwaysExpect(...)` | Mọi response đều được kiểm tra bằng matcher chung | Điều kiện nào phải đúng với tất cả request trong nhóm? |
| `alwaysDo(...)` | Mọi kết quả đều được xử lý bởi result handler | Cần ghi nhận hoặc hiển thị thông tin nào sau mỗi request? |
| `apply(...)` | Áp dụng một `MockMvcConfigurer` | Cần tích hợp cơ chế kiểm thử nào với builder? |

Đặt cấu hình gần test class hoặc một factory dùng chung để người đọc biết rõ `MockMvc` đang áp dụng những quy tắc nào. Nếu cấu hình được chia sẻ cho nhiều test class, hãy đặt nó trong một lớp cấu hình test hoặc phương thức tạo `MockMvc` có tên mô tả phạm vi sử dụng.

## 7. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| Một request nhận header hoặc locale ngoài dự kiến | `defaultRequest` đang đặt giá trị dùng chung | Kiểm tra builder và các thiết lập ghi đè trong `perform(...)` |
| Test kiểm tra `400` hoặc `404` nhưng vẫn thất bại | `alwaysExpect(status().isOk())` áp dụng cho cả request lỗi | Dùng builder riêng hoặc bỏ matcher status chung |
| Log test quá dài | `alwaysDo(print())` in mọi request | Chuyển sang `andDo(print())` ở test cần debug |
| Filter không chạy trong MockMvc | Filter chưa được đăng ký vào builder hoặc chưa được cấu hình trong test context | Dùng `addFilters(...)` hoặc cấu hình tích hợp phù hợp |
| Giá trị mặc định làm test phụ thuộc lẫn nhau | Một builder chứa quá nhiều thiết lập cho nhiều kịch bản khác nhau | Chia cấu hình theo nhóm test có cùng hợp đồng |
| Test tưởng rằng response đã được xác minh vì có log | `alwaysDo` chỉ xử lý kết quả, không tự kiểm tra tính đúng đắn | Bổ sung `alwaysExpect` hoặc `andExpect` |

Khi test thất bại, hãy xác định matcher chung hay assertion riêng đã làm test thất bại. Việc tách cấu hình dùng chung khỏi assertion của từng kịch bản giúp lỗi chỉ ra đúng điều kiện đang bị vi phạm.

## 8. Quy trình chọn cấu hình

1. Xác định các thuộc tính request thực sự giống nhau giữa mọi test trong một nhóm. Đặt các thuộc tính đó vào `defaultRequest`.
2. Xác định điều kiện response phải đúng trong mọi request thuộc nhóm. Đăng ký chúng bằng `alwaysExpect`.
3. Chỉ đăng ký `alwaysDo` khi cần một thao tác sau mỗi request, ví dụ in chi tiết để debug.
4. Thêm filter hoặc `MockMvcConfigurer` khi pipeline kiểm thử cần chúng; chú ý thứ tự và dependency tương ứng.
5. Tách builder khi các nhóm test có status, xác thực, content type hoặc môi trường request khác nhau.

`defaultRequest` chuẩn hóa đầu vào, `alwaysExpect` kiểm tra hợp đồng chung của đầu ra, còn `alwaysDo` thực hiện thao tác sau mỗi lần request. Các tùy chỉnh filter và configurer bổ sung hành vi cho pipeline MockMvc. Dùng từng cơ chế đúng phạm vi sẽ giúp test ngắn gọn mà vẫn thể hiện rõ những điều kiện đang được áp dụng cho toàn bộ nhóm request.
