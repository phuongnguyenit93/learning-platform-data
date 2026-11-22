# Chọn static import cho builder, matcher và handler

Khi viết kiểm thử với Spring MockMvc, một test thường có nhiều lời gọi ngắn như `get(...)`, `status()`, `jsonPath(...)` và `print()`. Các lời gọi này là static method thuộc những lớp khác nhau trong Spring Test. Java cho phép dùng **static import** để gọi chúng trực tiếp mà không cần viết tên lớp ở phía trước.

Static import giúp phần kiểm thử tập trung vào request và kết quả mong đợi. Tuy nhiên, nếu import nhầm lớp hoặc gom quá nhiều static method từ nhiều thư viện, mã test sẽ khó đọc và dễ gặp tên phương thức trùng nhau. Cách chọn tốt nhất là xác định vai trò của lời gọi trước, sau đó import đúng lớp khai báo phương thức đó.

## 1. Static import trong Java

Static import đưa một static method hoặc static field của một kiểu vào phạm vi tên đơn giản của file Java. Cú pháp:

~~~java
import static ten.package.TenLop.tenPhuongThuc;
~~~

Có thể import tất cả static member có thể truy cập của một lớp bằng dấu `*`:

~~~java
import static ten.package.TenLop.*;
~~~

Ví dụ, thay vì viết:

~~~java
mockMvc.perform(
        MockMvcRequestBuilders.get("/api/books/42")
).andExpect(
        MockMvcResultMatchers.status().isOk()
);
~~~

có thể viết:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/books/42"))
        .andExpect(status().isOk());
~~~

Static import chỉ thay đổi cách gọi tên trong mã nguồn. Nó không tạo thêm object, không thay đổi vòng đời bean, không cấu hình MockMvc và không làm cho request chạy khác đi.

## 2. Nhận diện bốn nhóm API thường dùng

Trong MockMvc, nên phân biệt các nhóm sau:

| Vai trò | Lớp khai báo static method | Ví dụ |
|---|---|---|
| Tạo MockMvc builder | `MockMvcBuilders` | `standaloneSetup(...)`, `webAppContextSetup(...)` |
| Tạo HTTP request | `MockMvcRequestBuilders` | `get(...)`, `post(...)`, `multipart(...)`, `asyncDispatch(...)` |
| Kiểm tra kết quả request | `MockMvcResultMatchers` | `status()`, `content()`, `jsonPath(...)`, `handler()` |
| Thực hiện thao tác với kết quả | `MockMvcResultHandlers` | `print()`, `log()` |

Các lớp trên thuộc những package khác nhau. Nhìn vào vai trò của lời gọi sẽ giúp chọn đúng package:

~~~text
MockMvcBuilders
    └── standaloneSetup / webAppContextSetup
            └── build() → MockMvc

MockMvcRequestBuilders
    └── get / post / put / delete / multipart
            └── tạo request cho mockMvc.perform(...)

MockMvcResultMatchers
    └── status / content / jsonPath / view / handler
            └── ResultMatcher cho andExpect(...)

MockMvcResultHandlers
    └── print / log
            └── ResultHandler cho andDo(...)
~~~

Điểm quan trọng: `handler()` và `print()` không cùng loại. `handler()` là matcher để xác nhận Spring chọn handler nào; `print()` là result handler để in thông tin của lần thực thi.

## 3. Static import cho builder

Builder tạo một đối tượng `MockMvc` với cấu hình kiểm thử phù hợp.

Hai factory method thường gặp nằm trong:

~~~java
org.springframework.test.web.servlet.setup.MockMvcBuilders
~~~

- `standaloneSetup(...)`: dựng MockMvc từ controller được truyền trực tiếp. Phù hợp khi muốn kiểm thử controller trong cấu hình tối giản và tự khai báo các thành phần hỗ trợ cần thiết.
- `webAppContextSetup(...)`: dựng MockMvc từ `WebApplicationContext`. Phù hợp khi muốn dùng cấu hình MVC và các bean đã được nạp trong web application context.

Có thể gọi bằng tên lớp:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new GreetingController())
        .build();
~~~

Hoặc static import factory method:

~~~java
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup;

MockMvc mockMvc = standaloneSetup(new GreetingController()).build();
~~~

Với web application context:

~~~java
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

MockMvc mockMvc = webAppContextSetup(webApplicationContext).build();
~~~

Chỉ import factory method mà test sử dụng. Nếu một test class có nhiều cách dựng MockMvc hoặc tên method gây khó hiểu, gọi qua tên lớp `MockMvcBuilders` vẫn là lựa chọn rõ ràng.

Trong Spring Boot, các test dùng `@WebMvcTest` hoặc `@SpringBootTest` kết hợp `@AutoConfigureMockMvc` thường nhận `MockMvc` qua injection. Khi đó, test không cần gọi builder:

~~~java
@WebMvcTest(BookController.class)
class BookControllerTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

Không thêm static import `standaloneSetup` hoặc `webAppContextSetup` nếu test không trực tiếp gọi chúng.

## 4. Static import cho request builder

Các factory method tạo request nằm trong:

~~~java
org.springframework.test.web.servlet.request.MockMvcRequestBuilders
~~~

Những method phổ biến:

| Method | Mục đích |
|---|---|
| `get(url, ...)` | Tạo HTTP GET |
| `post(url, ...)` | Tạo HTTP POST |
| `put(url, ...)` | Tạo HTTP PUT |
| `patch(url, ...)` | Tạo HTTP PATCH |
| `delete(url, ...)` | Tạo HTTP DELETE |
| `options(url, ...)` | Tạo HTTP OPTIONS |
| `head(url, ...)` | Tạo HTTP HEAD |
| `request(method, url, ...)` | Tạo request với HTTP method được chỉ định |
| `multipart(url, ...)` | Tạo multipart request |
| `asyncDispatch(mvcResult)` | Tạo lần dispatch tiếp theo cho kết quả xử lý bất đồng bộ |

Ví dụ request GET:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

mockMvc.perform(
        get("/api/books/{id}", 42L)
                .accept(MediaType.APPLICATION_JSON)
);
~~~

Ví dụ request POST:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

mockMvc.perform(
        post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "title": "Spring Testing"
                        }
                        """)
);
~~~

Các method trả về request builder, vì vậy có thể nối thêm thông tin như:

- `accept(...)`: kiểu nội dung client chấp nhận.
- `contentType(...)`: kiểu dữ liệu trong request body.
- `content(...)`: nội dung body.
- `param(...)`: query parameter hoặc request parameter.
- `header(...)`: HTTP header.
- `cookie(...)`: cookie.
- `with(...)`: áp dụng request post-processor, ví dụ cấu hình user trong Spring Security Test.

Ví dụ:

~~~java
mockMvc.perform(
        get("/api/books")
                .param("page", "0")
                .param("size", "20")
                .header("X-Request-Source", "test")
                .accept(MediaType.APPLICATION_JSON)
);
~~~

Các method như `get(...)` và `post(...)` được static import vì chúng tạo request. Không import chúng từ `MockMvcBuilders`; lớp builder chỉ chịu trách nhiệm dựng `MockMvc`.

## 5. Static import cho result matcher

Các matcher kiểm tra kết quả request thường được lấy từ:

~~~java
org.springframework.test.web.servlet.result.MockMvcResultMatchers
~~~

Nhóm này cung cấp các factory method trả về matcher phù hợp với `andExpect(...)`.

| Static method | Kiểm tra |
|---|---|
| `status()` | HTTP status |
| `content()` | Response body và content type |
| `jsonPath(expression)` | Giá trị trong JSON theo JSONPath |
| `header()` | HTTP response header |
| `cookie()` | Cookie trong response |
| `view()` | Tên view được chọn |
| `model()` | Model được đưa vào view |
| `redirectedUrl(...)` | URL redirect |
| `forwardedUrl(...)` | URL forward |
| `flash()` | Flash attribute |
| `handler()` | Handler method hoặc handler type được chọn |
| `request()` | Một số thuộc tính của request trong quá trình xử lý, gồm trạng thái async |
| `xpath(...)` | Nội dung XML theo XPath |

Ví dụ kiểm tra HTTP status và JSON:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/books/{id}", 42L)
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
        ))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.title").value("Spring Testing"));
~~~

Mỗi matcher có thể kiểm tra một khía cạnh riêng. Nối nhiều `andExpect(...)` giúp test mô tả rõ hợp đồng HTTP mà endpoint phải đáp ứng.

Một số matcher khác:

~~~java
mockMvc.perform(get("/books/42"))
        .andExpect(status().isOk())
        .andExpect(header().exists("ETag"))
        .andExpect(cookie().exists("SESSION"));
~~~

Với controller trả về view:

~~~java
mockMvc.perform(get("/books"))
        .andExpect(status().isOk())
        .andExpect(view().name("books/list"))
        .andExpect(model().attributeExists("books"));
~~~

Với redirect hoặc flash attribute:

~~~java
mockMvc.perform(post("/books")
                .param("title", "Spring Testing"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/books"))
        .andExpect(flash().attributeExists("message"));
~~~

### 5.1. Phân biệt MockMvcResultMatchers.handler() và MockMvcResultHandlers

Tên `handler` dễ gây nhầm với result handler. Hai API sau có nhiệm vụ khác nhau:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/books/42"))
        .andExpect(handler().handlerType(BookController.class))
        .andExpect(handler().methodName("findById"))
        .andDo(print());
~~~

- `handler()` thuộc `MockMvcResultMatchers`, trả về `ResultMatcher`. Nó kiểm tra handler mà Spring MVC đã chọn để xử lý request, chẳng hạn controller type hoặc tên method.
- `print()` thuộc `MockMvcResultHandlers`, trả về `ResultHandler`. Nó in thông tin request, response và kết quả thực thi để hỗ trợ chẩn đoán.

Một cách nhớ đơn giản:

- `andExpect(...)` nhận một điều kiện cần xác minh.
- `andDo(...)` nhận một thao tác cần thực hiện trên kết quả.

Không dùng `handler()` như đối số của `andDo(...)`, và không dùng `print()` như đối số của `andExpect(...)`.

## 6. Static import cho result handler

Các result handler thường dùng nằm trong:

~~~java
org.springframework.test.web.servlet.result.MockMvcResultHandlers
~~~

Các method phổ biến:

- `print()`: in thông tin của lần thực thi MockMvc ra output mặc định.
- `print(outputStream)` hoặc `print(writer)`: in kết quả ra output stream hoặc writer được chỉ định.
- `log()`: ghi thông tin kết quả qua logger của Spring Test.

Ví dụ:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/books"))
        .andDo(print())
        .andExpect(status().isOk());
~~~

`andDo(print())` hữu ích khi cần xem request, response, header, body hoặc exception trong lúc phát triển test. Khi test ổn định, chỉ giữ lại nếu log đầu ra thực sự hữu ích cho nhóm; in toàn bộ response ở mọi test có thể làm log CI dài và khó tìm lỗi.

Result handler không thay thế assertion. Một test gọi `andDo(print())` nhưng không có `andExpect(...)` vẫn chưa xác minh rằng endpoint trả về kết quả đúng.

## 7. Ví dụ hoàn chỉnh với static import tường minh

Ví dụ sau dùng MockMvc được Spring Boot cấu hình qua `@WebMvcTest`. Test kiểm tra status, content type, dữ liệu JSON và handler method.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsBookById() throws Exception {
        mockMvc.perform(
                        get("/api/books/{id}", 42L)
                                .accept(MediaType.APPLICATION_JSON)
                )
                .andDo(print())
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(handler().handlerType(BookController.class))
                .andExpect(handler().methodName("findById"))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.title").value("Spring Testing"));
    }
}
~~~

Các import được chia thành hai nhóm:

- Import thông thường dành cho annotation, class và kiểu dữ liệu như `Test`, `WebMvcTest`, `MediaType`, `MockMvc`.
- Static import dành cho các factory method như `get`, `print`, `content`, `handler`, `jsonPath`, `status`.

Tên lớp chứa static method không cần được import thông thường khi chỉ dùng static import. Ví dụ, import static `MockMvcRequestBuilders.get` không yêu cầu thêm `import MockMvcRequestBuilders`.

## 8. Kiểm thử async: kết hợp request builder, matcher và dispatch builder

MockMvc có thể kiểm tra request xử lý bất đồng bộ. Trong lần gọi đầu, kiểm tra request đã bắt đầu async và lấy `MvcResult`. Sau đó dùng `asyncDispatch(...)` để mô phỏng lần dispatch tiếp theo, rồi kiểm tra response cuối cùng.

~~~java
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

MvcResult pendingResult = mockMvc.perform(get("/api/reports"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(pendingResult))
        .andExpect(status().isOk());
~~~

Ở đây:

- `get(...)` và `asyncDispatch(...)` là request builder, được import từ `MockMvcRequestBuilders`.
- `request()` và `status()` là result matcher, được import từ `MockMvcResultMatchers`.
- `andReturn()` trả về `MvcResult`; đây là method của `ResultActions`, không phải static method cần import.

Phân biệt đúng nguồn khai báo giúp tránh cố tìm một static import cho method vốn là method instance trên đối tượng kết quả.

## 9. Import tường minh hay wildcard?

Có hai phong cách thường gặp.

### 9.1. Import từng method

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Ưu điểm:

- Nhìn import biết test đang sử dụng API nào.
- Dễ phát hiện method đến từ Spring Test hay thư viện khác.
- Giảm nguy cơ tên đơn giản bị trùng giữa các static import.
- IDE và code review dễ theo dõi thay đổi import.

Nhược điểm là danh sách import có thể dài khi test sử dụng nhiều matcher.

### 9.2. Import tất cả static member của một lớp

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.*;
~~~

Ưu điểm là ngắn và thuận tiện khi test dùng nhiều method từ cùng một lớp. Một số ví dụ Spring cũng sử dụng cách này.

Nhược điểm là người đọc phải tra cứu để biết method đang gọi thuộc lớp nào; khi thêm static import từ Hamcrest, Mockito, AssertJ hoặc JUnit, các tên trùng nhau có thể làm lời gọi mơ hồ hoặc khó đọc.

Wildcard static import chỉ lấy static member của đúng lớp được chỉ định. Nó không import static member của các lớp khác trong package, cũng không import tất cả class trong package.

### 9.3. Quy tắc chọn trong dự án

Một quy tắc thực tế:

1. Ưu tiên import tường minh trong test có ít method hoặc có nhiều thư viện assertion.
2. Có thể dùng wildcard cho một lớp MockMvc nếu test dùng nhiều method từ lớp đó và quy ước dự án cho phép.
3. Không trộn tùy tiện nhiều wildcard static import từ các thư viện khác nhau.
4. Giữ một phong cách nhất quán trong cùng module để người đọc dự đoán được nguồn của các method.
5. Để IDE tổ chức import, nhưng xem lại kết quả nếu IDE tự chuyển nhiều import thành wildcard theo ngưỡng cấu hình.

Không có quy tắc Java bắt buộc mọi dự án phải dùng import tường minh. Điều quan trọng là import rõ nguồn và tránh xung đột tên.

## 10. Xử lý trùng tên và lỗi import thường gặp

### 10.1. Hai lớp cùng khai báo method trùng tên

Các thư viện kiểm thử có nhiều static method ngắn như `is(...)`, `not(...)`, `any(...)` hoặc `assertThat(...)`. Nếu import cùng tên từ nhiều lớp, compiler có thể báo lời gọi mơ hồ khi không thể chọn một method phù hợp.

Ví dụ, khi cần dùng một method trùng tên từ hai thư viện, có thể gọi một phía bằng tên lớp đầy đủ:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/books"))
        .andExpect(status().isOk());

org.hamcrest.MatcherAssert.assertThat(
        actualValue,
        org.hamcrest.Matchers.is(expectedValue)
);
~~~

Trong ví dụ này, `status()` là matcher của Spring MockMvc; `assertThat(...)` và `is(...)` được gọi qua lớp Hamcrest để nguồn của chúng rõ ràng. Với test thực tế, có thể chọn một phong cách assertion nhất quán thay vì trộn nhiều thư viện.

### 10.2. Import nhầm package

Các lỗi dễ gặp:

| Muốn gọi | Static import đúng |
|---|---|
| `standaloneSetup(...)` | `org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup` |
| `get(...)` | `org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get` |
| `status()` | `org.springframework.test.web.servlet.result.MockMvcResultMatchers.status` |
| `handler()` | `org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler` |
| `print()` | `org.springframework.test.web.servlet.result.MockMvcResultHandlers.print` |

Đừng nhầm `MockMvcBuilders` với `MockMvcRequestBuilders`: một lớp tạo MockMvc, lớp còn lại tạo HTTP request cho MockMvc.

### 10.3. Dùng static import cho method không phải static

Không phải method nào xuất hiện trong chuỗi MockMvc cũng cần static import. Những method sau được gọi trên object:

- `mockMvc.perform(...)`: method của `MockMvc`.
- `andExpect(...)`, `andDo(...)`, `andReturn()`: method của `ResultActions`.
- `build()`: method của builder được trả về từ `standaloneSetup(...)` hoặc `webAppContextSetup(...)`.
- `accept(...)`, `contentType(...)`, `content(...)`, `param(...)`: method trên request builder.
- `isOk()`, `isCreated()`, `isBadRequest()`: method trên đối tượng matcher được trả về từ `status()`.

Ví dụ:

~~~java
mockMvc.perform(get("/api/books"))
        .andExpect(status().isOk());
~~~

Trong chuỗi này chỉ `get` và `status` là các static factory method thường được import. Những lời gọi còn lại là method instance.

### 10.4. Thiếu dependency

Nếu IDE không tìm thấy package `org.springframework.test.web.servlet`, nguyên nhân có thể là module chưa có dependency Spring Test hoặc dependency test của Spring Boot. Static import không thể bổ sung thư viện còn thiếu. Hãy kiểm tra dependency của module và scope test theo cấu hình build đang dùng.

## 11. Cách tự xác định import khi gặp method mới

Khi gặp một method chưa biết nguồn, có thể đi theo trình tự:

1. Xác định method đang tạo thứ gì: builder, request, matcher hay handler.
2. Dùng IDE `Go to Declaration` hoặc `Quick Documentation` để xem class khai báo method.
3. Kiểm tra package của class đó.
4. Chọn import tường minh cho method cần dùng.
5. Nếu method là method instance, không tạo static import; xem kiểu object đứng trước dấu chấm.

Ví dụ:

| Lời gọi | Câu hỏi cần đặt | Kết luận |
|---|---|---|
| `get("/books")` | Ai tạo HTTP request? | `MockMvcRequestBuilders.get` |
| `status().isOk()` | Ai tạo điều kiện kiểm tra status? | `MockMvcResultMatchers.status` |
| `print()` | Ai thao tác trên kết quả? | `MockMvcResultHandlers.print` |
| `standaloneSetup(controller)` | Ai dựng MockMvc? | `MockMvcBuilders.standaloneSetup` |
| `andExpect(...)` | Method được gọi trên object nào? | `ResultActions`, không static import |

## 12. Ghi nhớ

- Builder dựng `MockMvc`: `MockMvcBuilders`.
- Request builder tạo HTTP request: `MockMvcRequestBuilders`.
- Result matcher xác minh kết quả: `MockMvcResultMatchers`.
- Result handler thực hiện thao tác trên kết quả: `MockMvcResultHandlers`.
- `handler()` là một matcher; `print()` là một handler.
- `andExpect(...)` nhận `ResultMatcher`; `andDo(...)` nhận `ResultHandler`.
- Static import chỉ rút gọn tên gọi, không thay đổi hành vi của MockMvc.
- Import tường minh dễ truy vết nguồn; wildcard giảm số dòng nhưng cần được dùng nhất quán.

Khi đọc hoặc viết một test MockMvc, hãy bắt đầu từ vai trò của method rồi xác định lớp khai báo. Nếu tên method không đủ rõ hoặc có xung đột, gọi qua tên lớp đầy đủ để giữ ý nghĩa của test dễ hiểu.
