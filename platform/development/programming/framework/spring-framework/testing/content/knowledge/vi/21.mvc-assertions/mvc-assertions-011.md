# ResultHandler, print và thông tin chẩn đoán khi thất bại

**Ngữ cảnh:** Spring Framework Testing → Xác nhận kết quả MVC.

Một bài kiểm thử MockMvc thường kết thúc bằng các assertion về HTTP status, header, response body hoặc model. Khi một assertion thất bại, chỉ biết rằng kết quả thực tế khác mong đợi thường chưa đủ để tìm nguyên nhân. Cần quan sát request đã gửi, handler được chọn, exception được xử lý, response thực tế và các trạng thái phụ như redirect, flash attribute hoặc xử lý bất đồng bộ.

Spring Test cung cấp ba cơ chế bổ sung cho nhau:

- **ResultMatcher:** xác nhận một điều kiện trên kết quả xử lý request.
- **ResultHandler:** quan sát hoặc xử lý kết quả sau khi request đã được thực thi, ví dụ in thông tin chẩn đoán.
- **MvcResult:** cung cấp quyền truy cập trực tiếp vào request, response, handler, exception, model và các dữ liệu liên quan.

Hiểu rõ thời điểm mỗi cơ chế chạy giúp đặt lệnh in đúng vị trí, lưu được dữ liệu cần điều tra và tránh mất thông tin khi assertion đầu tiên ném lỗi.

## 1. Kết quả của một request MockMvc gồm những gì?

MockMvc mô phỏng request đi qua Spring MVC trong môi trường kiểm thử. Khi gọi **perform**, Spring xử lý request và trả về một đối tượng **ResultActions** để test tiếp tục kiểm tra hoặc xử lý kết quả.

Luồng cơ bản:

~~~text
MockMvc.perform(request)
        |
        v
Spring MVC xử lý request
        |
        v
MvcResult được tạo
        |
        +---- ResultMatcher: kiểm tra điều kiện
        |
        +---- ResultHandler: quan sát / in / lưu kết quả
        |
        +---- andReturn(): lấy MvcResult để kiểm tra sâu hơn
~~~

Các thành phần có vai trò khác nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| ResultActions | Chuỗi thao tác trên kết quả request | andExpect, andDo, andReturn |
| ResultMatcher | Kiểm tra kết quả có đúng kỳ vọng | status().isOk(), jsonPath(...) |
| ResultHandler | Thực hiện hành động với kết quả | print(), ghi log, thu thập dữ liệu |
| MvcResult | Dữ liệu request và response sau xử lý | getRequest(), getResponse(), getResolvedException() |

Không nên nhầm ResultHandler với ResultMatcher. Matcher trả lời câu hỏi “kết quả có đúng không?”, còn handler trả lời câu hỏi “cần làm gì với kết quả này?”. Một handler có thể in dữ liệu, lưu lại hoặc chuyển dữ liệu đến công cụ quan sát. Assertion nên được thể hiện rõ bằng matcher để khi test thất bại, thông báo cho biết điều kiện nào không đạt.

## 2. ResultActions và thứ tự thực thi

### 2.1. Ba phương thức quan trọng

Sau khi gọi perform, ResultActions cung cấp ba phương thức chính:

~~~java
ResultActions actions = mockMvc.perform(get("/orders/42"));

actions.andExpect(status().isOk());
actions.andDo(print());

MvcResult result = actions.andReturn();
~~~

- **andExpect(matcher):** chạy một ResultMatcher trên MvcResult. Nếu điều kiện không đạt, matcher thường ném AssertionError và test thất bại.
- **andDo(handler):** chạy ResultHandler trên MvcResult. Handler thường dùng để in hoặc thu thập thông tin.
- **andReturn():** trả về MvcResult để test đọc thêm request, response, handler hoặc exception.

Các thao tác có thể nối thành chuỗi:

~~~java
mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42))
        .andDo(print());
~~~

Chuỗi này dễ đọc: gửi request, kiểm tra status, kiểm tra content type, kiểm tra dữ liệu JSON rồi in kết quả.

### 2.2. Vì sao print đặt sau assertion có thể không chạy?

Các phương thức trên được thực hiện khi chuỗi được gọi. Nếu một **andExpect** thất bại, nó ném AssertionError ngay tại vị trí đó. Những thao tác phía sau trong chuỗi không được chạy.

Ví dụ:

~~~java
mockMvc.perform(get("/orders/404"))
        .andExpect(status().isOk())
        .andDo(print());
~~~

Nếu response thực tế là 404, test dừng tại **status().isOk()**. Lệnh **andDo(print())** ở phía sau không có cơ hội chạy. Đây là nguyên nhân phổ biến khiến test thất bại nhưng không có phần output chẩn đoán mà người viết mong đợi.

Nếu muốn in trước khi thực hiện assertion, đặt handler ngay sau perform:

~~~java
mockMvc.perform(get("/orders/404"))
        .andDo(print())
        .andExpect(status().isOk());
~~~

Khi request đã được thực thi và ResultActions được trả về, print chạy trước matcher tiếp theo. Nếu assertion sau đó thất bại, output đã được tạo.

Khi cần in cho mọi request được thực hiện qua một MockMvc instance, có thể cấu hình **alwaysDo** trong builder. Cách này hữu ích khi điều tra một nhóm test có nhiều request.

## 3. In kết quả bằng MockMvcResultHandlers.print()

### 3.1. Cách dùng cơ bản

Spring Test cung cấp **MockMvcResultHandlers.print()**, thường được import tĩnh:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
~~~

Sử dụng với MockMvc:

~~~java
mockMvc.perform(get("/orders/42"))
        .andDo(print())
        .andExpect(status().isOk());
~~~

Output của print có thể hiển thị các thông tin như:

- HTTP method và URI.
- Request parameters, headers và body.
- Handler được chọn để xử lý request.
- Exception được Spring giải quyết nếu có.
- Model và flash attributes nếu có.
- HTTP status, response headers và response body.
- Thông tin liên quan đến async khi request sử dụng xử lý bất đồng bộ.

Thông tin cụ thể xuất hiện tùy vào loại request và những dữ liệu thực sự có trong MvcResult. Ví dụ, request không có body thì phần request content có thể trống; endpoint REST không sử dụng model view thì phần model/view không có dữ liệu đáng kể.

### 3.2. In mọi request bằng alwaysDo

Nếu muốn mọi request qua MockMvc đều được in, đăng ký handler ở builder:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .alwaysDo(print())
        .build();
~~~

Với standalone setup:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .alwaysDo(print())
        .build();
~~~

**alwaysDo** áp dụng ResultHandler cho mỗi request được thực hiện qua MockMvc được tạo từ builder đó. Handler được gọi trong quá trình tạo kết quả, trước khi test tiếp tục gọi các matcher trên ResultActions. Vì vậy, thông tin vẫn được in nếu một assertion phía sau thất bại.

Đây là lựa chọn phù hợp khi đang điều tra lỗi và muốn có output nhất quán. Khi bộ test lớn, in mọi request có thể tạo rất nhiều log và làm CI output khó đọc. Sau khi tìm được nguyên nhân, có thể bỏ alwaysDo hoặc chỉ giữ print ở các test cần chẩn đoán.

### 3.3. In theo từng test hoặc từng request

Không nhất thiết phải bật print cho toàn bộ MockMvc. Có thể chỉ thêm handler vào request nghi ngờ:

~~~java
@Test
void showsDiagnosticOutputForMissingOrder() throws Exception {
    mockMvc.perform(get("/orders/404"))
            .andDo(print())
            .andExpect(status().isNotFound());
}
~~~

Cách này giúp output tập trung vào tình huống cần điều tra. Nếu assertion cần kiểm tra chính status đó, đặt print trước assertion như ví dụ trên.

Nếu test có nhiều request, mỗi request có thể gắn một handler riêng để biết output tương ứng với bước nào.

## 4. Tự viết ResultHandler

**ResultHandler** là một functional interface nhận **MvcResult**. Có thể dùng lambda để ghi lại thông tin cụ thể thay vì in toàn bộ kết quả.

Ví dụ:

~~~java
ResultHandler diagnosticHandler = result -> {
    MockHttpServletRequest request = result.getRequest();
    MockHttpServletResponse response = result.getResponse();

    System.out.println("Request: "
            + request.getMethod() + " " + request.getRequestURI());

    System.out.println("Handler: " + result.getHandler());
    System.out.println("Status: " + response.getStatus());
    System.out.println("Content-Type: " + response.getContentType());
    System.out.println("Response body: " + response.getContentAsString());

    Exception resolvedException = result.getResolvedException();
    if (resolvedException != null) {
        System.out.println("Resolved exception: "
                + resolvedException.getClass().getName()
                + ": " + resolvedException.getMessage());
    }
};
~~~

Gắn handler vào request:

~~~java
mockMvc.perform(get("/orders/404"))
        .andDo(diagnosticHandler)
        .andExpect(status().isNotFound());
~~~

Ví dụ này sử dụng các API của mock request và mock response. Trong một handler thực tế, có thể dùng logger thay cho System.out để kiểm soát mức log và định dạng output. Phương thức đọc body có thể ném exception về encoding; giao diện ResultHandler cho phép xử lý ngoại lệ trong quá trình đọc dữ liệu.

### 4.1. Chỉ in các trường cần thiết

Không phải lúc nào cũng cần in toàn bộ request và response. Có thể tạo handler nhỏ:

~~~java
ResultHandler statusAndException = result -> {
    int status = result.getResponse().getStatus();
    Exception exception = result.getResolvedException();

    System.out.println("HTTP status = " + status);

    if (exception != null) {
        exception.printStackTrace();
    }
};
~~~

Handler nhỏ hữu ích khi test chạy thường xuyên và chỉ cần vài trường để nhận diện lỗi. Một handler dùng chung có thể nhận tên kịch bản hoặc correlation id từ test, sau đó ghi chúng cùng status và URI.

### 4.2. Handler quan sát và matcher xác nhận

Có thể viết lambda trực tiếp cho ResultHandler:

~~~java
mockMvc.perform(get("/orders/42"))
        .andDo(result -> {
            System.out.println(
                    result.getResponse().getStatus()
            );
        })
        .andExpect(status().isOk());
~~~

Nếu muốn kiểm tra status, dùng ResultMatcher:

~~~java
mockMvc.perform(get("/orders/42"))
        .andExpect(result ->
                assertThat(result.getResponse().getStatus())
                        .isEqualTo(200));
~~~

Hai lambda trông tương tự nhưng mục đích khác nhau. Handler thực hiện hành động quan sát; matcher xác nhận điều kiện và phải làm test thất bại khi điều kiện không đạt.

Không nên giấu các assertion quan trọng trong một handler chỉ để tận dụng lambda. Tách chúng thành matcher giúp test thể hiện rõ hợp đồng cần xác nhận và báo lỗi đúng tại điều kiện không đạt.

## 5. Đọc MvcResult để chẩn đoán sâu hơn

### 5.1. Lấy MvcResult

Dùng **andReturn()** để lấy kết quả sau khi request đã được thực thi:

~~~java
MvcResult result = mockMvc.perform(get("/orders/42"))
        .andDo(print())
        .andReturn();
~~~

Từ đây có thể đọc request và response trực tiếp:

~~~java
MockHttpServletRequest request = result.getRequest();
MockHttpServletResponse response = result.getResponse();

assertThat(request.getMethod()).isEqualTo("GET");
assertThat(request.getRequestURI()).isEqualTo("/orders/42");
assertThat(response.getStatus()).isEqualTo(200);
~~~

Có thể kết hợp andReturn với các matcher trước đó:

~~~java
MvcResult result = mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andReturn();

String body = result.getResponse().getContentAsString();
assertThat(body).contains("\"id\":42");
~~~

Lưu ý rằng nếu matcher thất bại trước andReturn, dòng lấy result sẽ không được thực hiện. Khi cần đọc kết quả ngay cả lúc một assertion có thể thất bại, hãy dùng handler trước assertion hoặc cấu hình alwaysDo.

### 5.2. Những thông tin quan trọng trong MvcResult

| Phương thức | Thông tin |
|---|---|
| getRequest() | MockHttpServletRequest đã gửi |
| getResponse() | MockHttpServletResponse nhận được |
| getHandler() | Handler được chọn, thường là HandlerMethod trong Spring MVC |
| getInterceptors() | Các interceptor liên quan đến handler |
| getResolvedException() | Exception đã được HandlerExceptionResolver xử lý |
| getModelAndView() | ModelAndView nếu request tạo kết quả view |
| getFlashMap() | Flash attributes được lưu trong quá trình redirect |
| getAsyncResult() | Kết quả của request bất đồng bộ khi đã sẵn sàng |
| getAsyncResult(timeout) | Chờ kết quả async trong khoảng thời gian được chỉ định |

Không phải mọi phương thức đều có dữ liệu trong mọi request. Ví dụ, endpoint REST thường không tạo ModelAndView; request không redirect thường không có flash attributes.

### 5.3. Xác định controller method đã được chọn

Có thể xem handler:

~~~java
MvcResult result = mockMvc.perform(get("/orders/42"))
        .andDo(print())
        .andReturn();

Object handler = result.getHandler();
System.out.println("Selected handler: " + handler);
~~~

Nếu handler là **HandlerMethod**, có thể đọc bean và method:

~~~java
if (result.getHandler() instanceof HandlerMethod handlerMethod) {
    System.out.println("Controller bean: "
            + handlerMethod.getBeanType().getName());
    System.out.println("Controller method: "
            + handlerMethod.getMethod().toGenericString());
}
~~~

Thông tin này hữu ích khi có nhiều mapping gần giống nhau, nhiều controller cùng xử lý một nhóm URL hoặc một test đang gọi nhầm endpoint. Nếu handler là null, request có thể chưa được ánh xạ đến controller, ví dụ lỗi xảy ra ở bước handler mapping hoặc một thành phần phía trước.

### 5.4. Xem exception đã được giải quyết

Nếu exception được một **HandlerExceptionResolver** xử lý, MvcResult có thể cung cấp nó qua getResolvedException():

~~~java
MvcResult result = mockMvc.perform(get("/orders/404"))
        .andDo(print())
        .andReturn();

Exception exception = result.getResolvedException();

assertThat(exception)
        .isInstanceOf(OrderNotFoundException.class);
~~~

Điều này giúp xác nhận controller thực sự phát sinh loại exception dự kiến, đồng thời kiểm tra advice hoặc resolver đã biến exception đó thành response.

Cần phân biệt exception đã được giải quyết với exception chưa được xử lý. Nếu exception không được MVC resolver xử lý, perform có thể ném ServletException hoặc ngoại lệ liên quan ngay trong quá trình thực thi. Khi đó test không nhận được một MvcResult bình thường để đọc getResolvedException(); cần xem exception được ném ra và stack trace của nó.

### 5.5. Kiểm tra model và flash attributes

Với controller trả view:

~~~java
MvcResult result = mockMvc.perform(get("/orders"))
        .andExpect(status().isOk())
        .andReturn();

ModelAndView modelAndView = result.getModelAndView();

assertThat(modelAndView).isNotNull();
assertThat(modelAndView.getViewName()).isEqualTo("orders/list");
assertThat(modelAndView.getModel()).containsKey("orders");
~~~

Với redirect có flash attribute:

~~~java
MvcResult result = mockMvc.perform(post("/orders")
                .param("customerName", "An"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/orders"))
        .andReturn();

assertThat(result.getFlashMap())
        .containsEntry("message", "Order created");
~~~

Flash attributes được dùng để chuyển dữ liệu qua một lần redirect. Đọc chúng từ MvcResult giúp xác nhận dữ liệu thông báo hoặc trạng thái tạm thời đã được thiết lập.

## 6. Chẩn đoán theo từng phần của request và response

Khi test thất bại, nên đọc thông tin theo trình tự từ đầu request đến response. Cách này giúp xác định lỗi nằm ở mapping, binding, controller, exception handling hay serialization.

### 6.1. Request

Kiểm tra:

- HTTP method có đúng không?
- URI và path variable có đúng không?
- Query parameters có đủ và đúng tên không?
- Content-Type có phù hợp với request body không?
- Accept có phù hợp với kiểu response mong muốn không?
- Header xác thực, locale hoặc header nghiệp vụ có được gửi không?
- Request body có đúng JSON/XML và đúng cấu trúc DTO không?

Ví dụ một endpoint nhận JSON có thể thất bại nếu test quên contentType:

~~~java
mockMvc.perform(post("/orders")
                .content("""
                        {
                          "customerName": "An"
                        }
                        """))
        .andExpect(status().isCreated());
~~~

Nếu endpoint yêu cầu application/json, request không khai báo Content-Type có thể khiến Spring không tìm được converter phù hợp. Sửa test:

~~~java
mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "customerName": "An"
                        }
                        """))
        .andExpect(status().isCreated());
~~~

### 6.2. Handler mapping

Nếu response là 404 hoặc handler null, kiểm tra:

- URL có khớp @RequestMapping, @GetMapping, @PostMapping không?
- HTTP method có khớp không?
- Path variable có đúng mẫu không?
- Controller có được đăng ký trong application context không?
- Component scan có bao phủ package controller không?
- Test standalone có truyền đúng controller vào builder không?
- Có context path hoặc servlet path làm thay đổi URL không?

Một request có thể trả 404 vì không tìm thấy handler, hoặc vì controller/advice chủ động trả 404 cho tài nguyên không tồn tại. Xem handler và exception giúp phân biệt hai trường hợp này.

### 6.3. Binding và message conversion

Nếu status là 400 hoặc 415, xem request content type, body, tham số và exception liên quan.

Một số dấu hiệu:

| Hiện tượng | Khu vực cần xem |
|---|---|
| 415 Unsupported Media Type | Content-Type và HttpMessageConverter có hỗ trợ media type không |
| 406 Not Acceptable | Accept header và khả năng ghi response của converter |
| 400 Bad Request | Deserialize, type conversion, data binding hoặc validation |
| MethodArgumentTypeMismatchException | Chuyển đổi query/path parameter |
| HttpMessageNotReadableException | Đọc request body, JSON không hợp lệ hoặc kiểu dữ liệu không khớp |
| MethodArgumentNotValidException | Bean Validation của đối tượng request |

Không nên mặc định mọi HTTP 400 đều là lỗi validation. JSON sai cú pháp có thể bị từ chối trước khi DTO được tạo; một query parameter không chuyển được thành enum cũng có thể tạo lỗi 400.

### 6.4. Controller và exception handling

Nếu handler đúng nhưng response không như mong đợi, kiểm tra:

- Controller có được gọi không?
- Dependency của controller trả dữ liệu gì?
- Có exception nào phát sinh không?
- Exception có được resolver xử lý không?
- ControllerAdvice nào được chọn?
- Có nhiều advice hoặc handler cùng match không?
- Response status và body có được tạo theo đúng hợp đồng không?

Có thể dùng getResolvedException để xem exception đã được giải quyết. Nếu không có resolved exception nhưng response là lỗi, lỗi có thể do controller chủ động trả ResponseEntity hoặc do một thành phần khác xử lý.

### 6.5. Response

Đọc các thuộc tính sau:

~~~java
MockHttpServletResponse response = result.getResponse();

int status = response.getStatus();
String contentType = response.getContentType();
String location = response.getHeader(HttpHeaders.LOCATION);
String body = response.getContentAsString();
~~~

Kiểm tra status, content type, header, body và encoding. Với redirect, xem Location. Với response JSON, kiểm tra trường và giá trị quan trọng bằng jsonPath. Với response file hoặc binary, không nên ép nội dung thành chuỗi để in như JSON.

## 7. Viết ResultMatcher có thông báo lỗi rõ ràng

Spring cung cấp nhiều matcher có sẵn:

~~~java
mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andExpect(header().exists(HttpHeaders.ETAG))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("PAID"));
~~~

Những matcher này thường tạo thông báo lỗi cụ thể hơn so với việc lấy response body rồi so sánh chuỗi bằng một assertion tổng quát.

Có thể tạo matcher riêng khi một điều kiện nghiệp vụ được kiểm tra lặp lại:

~~~java
ResultMatcher hasOrderId(long expectedId) {
    return result -> {
        String body = result.getResponse().getContentAsString();
        JsonNode json = new ObjectMapper().readTree(body);

        assertThat(json.path("id").asLong())
                .as("order id in response body")
                .isEqualTo(expectedId);
    };
}
~~~

Sử dụng:

~~~java
mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andExpect(hasOrderId(42));
~~~

Matcher riêng nên kiểm tra một quy tắc có ý nghĩa và đặt tên theo điều kiện cần xác nhận. Nếu matcher chỉ gom nhiều assertion không liên quan vào một hàm lớn, khi lỗi xảy ra sẽ khó biết điều kiện nào thất bại.

Trong ví dụ trên, ObjectMapper được tạo trong matcher để minh họa. Với bộ test lớn, nên tái sử dụng mapper đã cấu hình theo ứng dụng và xử lý lỗi parse phù hợp. Nếu chỉ cần kiểm tra JSON đơn giản, jsonPath thường gọn hơn.

## 8. Chẩn đoán request bất đồng bộ

Spring MVC hỗ trợ handler trả về các kiểu bất đồng bộ như Callable, DeferredResult hoặc WebAsyncTask. Khi request bắt đầu xử lý async, lần perform đầu tiên có thể trả về trước khi kết quả cuối cùng sẵn sàng.

Kiểm tra trạng thái async:

~~~java
MvcResult asyncResult = mockMvc.perform(get("/reports/42"))
        .andExpect(request().asyncStarted())
        .andDo(print())
        .andReturn();
~~~

Sau đó dispatch kết quả async để kiểm tra response cuối cùng:

~~~java
mockMvc.perform(asyncDispatch(asyncResult))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON));
~~~

Không nên chỉ kiểm tra status của request đầu tiên rồi kết luận endpoint async đã trả response cuối cùng. Cần dispatch kết quả async và xác nhận status/body ở lượt xử lý tiếp theo.

Nếu cần đọc kết quả async trực tiếp, MvcResult cung cấp getAsyncResult() và getAsyncResult(timeout). Chỉ đọc khi request đã bắt đầu async và kết quả đã sẵn sàng; nếu không, test có thể chờ hoặc thất bại do timeout.

Khi chẩn đoán async, cần phân biệt:

- Request có thật sự chuyển sang async không?
- Callable/DeferredResult có hoàn tất không?
- Có exception trong luồng async không?
- asyncDispatch có được gọi không?
- Response cuối cùng có đúng status và body không?

## 9. Kết hợp print và assertion trong một helper

Nếu nhiều test cần in trước khi assertion chạy, có thể tạo helper:

~~~java
ResultActions performWithDiagnostics(
        MockHttpServletRequestBuilder request) throws Exception {

    return mockMvc.perform(request)
            .andDo(print());
}
~~~

Sử dụng:

~~~java
performWithDiagnostics(get("/orders/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42));
~~~

Helper này giúp thống nhất cách in kết quả cho nhóm test. Chỉ nên dùng khi nó làm test dễ đọc hơn; nếu helper che giấu request builder hoặc cấu hình quan trọng, gọi MockMvc trực tiếp sẽ rõ ràng hơn.

Nếu muốn luôn in trong một class test, cấu hình MockMvc với alwaysDo:

~~~java
@BeforeEach
void setUp() {
    mockMvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .alwaysDo(print())
            .build();
}
~~~

Có thể dùng helper riêng cho test cần điều tra và giữ các test khác không in để giảm nhiễu.

## 10. Tổ chức thông tin chẩn đoán trong CI

Khi chạy test ở máy cá nhân, output có thể xuất hiện ngay trên console. Trong CI, output thường được lưu trong log của test task hoặc test report. Cần bảo đảm output của ResultHandler nằm trong log mà nhóm phát triển có thể truy cập.

Một số nguyên tắc hữu ích:

- In request và response của test đang điều tra.
- Đặt print trước matcher có khả năng thất bại, hoặc dùng alwaysDo trong phạm vi MockMvc phù hợp.
- Giữ lại stack trace và exception gốc.
- Ghi nhận handler method để phân biệt lỗi mapping với lỗi nghiệp vụ.
- Không in quá nhiều request không liên quan trong bộ test lớn.
- Dùng logger có mức phù hợp nếu muốn điều khiển output theo môi trường.
- Không đưa token, cookie xác thực, mật khẩu hoặc dữ liệu cá nhân vào log chia sẻ.

Output chẩn đoán cần đủ để tái hiện nguyên nhân nhưng không nên chứa thông tin nhạy cảm. Nếu request có header Authorization hoặc cookie, cân nhắc không in toàn bộ header trong log CI dùng chung. Có thể dùng custom ResultHandler chỉ ghi URI, status và handler thay vì dump toàn bộ request.

### 10.1. Phân biệt lỗi assertion với lỗi thực thi request

Hai loại lỗi có dấu hiệu khác nhau:

**Lỗi assertion:** request đã chạy và có MvcResult, nhưng một matcher không đạt. Ví dụ mong đợi 200 nhưng thực tế 404. Print hoặc handler trước matcher có thể cho thấy response thực tế.

**Lỗi thực thi request:** exception chưa được xử lý làm perform ném exception trước khi trả ResultActions. Ví dụ controller ném một exception không có resolver phù hợp. Trong trường hợp này, andDo(print()) phía sau perform không chạy vì perform chưa trả về; cần xem stack trace của exception và cấu hình exception resolver.

Sự phân biệt này giúp tránh mất thời gian tìm MvcResult trong tình huống request chưa tạo được kết quả bình thường.

## 11. Ví dụ đầy đủ: điều tra response 404 không mong đợi

Giả sử test kỳ vọng endpoint trả HTTP 200:

~~~java
@Test
void returnsOrderDetails() throws Exception {
    MvcResult result = mockMvc.perform(get("/orders/42")
                    .accept(MediaType.APPLICATION_JSON))
            .andDo(print())
            .andReturn();

    assertThat(result.getResponse().getStatus()).isEqualTo(200);
}
~~~

Nếu test thất bại với status 404, có thể dùng dữ liệu trong MvcResult để tìm nguyên nhân:

~~~java
@Test
void diagnosesUnexpectedNotFound() throws Exception {
    MvcResult result = mockMvc.perform(get("/orders/42")
                    .accept(MediaType.APPLICATION_JSON))
            .andDo(print())
            .andReturn();

    System.out.println("Handler: " + result.getHandler());
    System.out.println("Status: "
            + result.getResponse().getStatus());
    System.out.println("Body: "
            + result.getResponse().getContentAsString());

    Exception exception = result.getResolvedException();
    if (exception != null) {
        System.out.println("Resolved exception: "
                + exception.getClass().getName());
    }

    assertThat(result.getResponse().getStatus()).isEqualTo(200);
}
~~~

Kết quả có thể dẫn đến một số hướng điều tra:

1. **Handler null:** request không được ánh xạ đến controller. Kiểm tra URL, HTTP method, component scan và cấu hình servlet.
2. **Handler đúng nhưng có resolved exception:** controller được gọi và exception đã được resolver xử lý. Xem loại exception, advice và dữ liệu đầu vào.
3. **Handler đúng, không có exception, response 404:** controller có thể chủ động trả 404 hoặc một thành phần khác tạo response đó. Kiểm tra logic trả ResponseEntity và interceptor/filter liên quan.
4. **Response body cho biết tài nguyên không tồn tại:** xác nhận dữ liệu test hoặc mock service có trả bản ghi mà endpoint cần không.

Trong quá trình điều tra, không nên thay assertion 200 thành 404 chỉ để test xanh nếu hợp đồng endpoint vẫn yêu cầu 200. Hãy xác định vì sao kết quả khác mong đợi rồi sửa cấu hình, dữ liệu hoặc hành vi phù hợp.

## 12. Những lỗi thường gặp khi dùng ResultHandler và print

### Print không xuất hiện khi test thất bại

Kiểm tra vị trí andDo(print()). Nếu nó đứng sau matcher thất bại, handler không chạy. Đưa print lên trước matcher hoặc dùng alwaysDo ở builder.

### Output có nhưng không cho biết nguyên nhân

Print cung cấp ảnh chụp request/response, không tự phân tích nguyên nhân. Đọc thêm handler, resolved exception, status, headers và body qua MvcResult. Khi cần, tạo ResultHandler riêng để ghi đúng trường dữ liệu có ý nghĩa.

### Test thất bại trước khi andDo được gọi

Nếu perform ném exception chưa được xử lý, ResultActions không được trả về và handler gắn sau perform không chạy. Xem stack trace và kiểm tra HandlerExceptionResolver hoặc exception phát sinh trong quá trình xử lý.

### Log quá nhiều làm khó tìm lỗi

Nếu alwaysDo(print()) được bật cho toàn bộ MockMvc, mọi request đều tạo output. Chỉ bật ở phạm vi cần thiết, hoặc viết handler ghi các trường ngắn gọn. Sau khi điều tra xong, có thể bỏ cấu hình chẩn đoán tạm thời.

### Không đọc được response body

Một số response là binary, streaming hoặc có encoding đặc thù. Không nên luôn gọi getContentAsString() cho mọi response. Với file download, hãy kiểm tra content type, header, độ dài hoặc bytes theo hợp đồng của endpoint.

### Nhầm resolved exception với exception gốc chưa xử lý

getResolvedException() chỉ phản ánh exception đã được resolver xử lý trong MvcResult. Exception chưa được xử lý có thể khiến perform ném lỗi trực tiếp. Hãy kiểm tra stack trace thay vì giả định mọi lỗi đều nằm trong getResolvedException().

### Chẩn đoán làm lộ dữ liệu nhạy cảm

print() có thể hiển thị header, cookie và body. Không dùng output đầy đủ ở môi trường chứa dữ liệu thật hoặc log chia sẻ nếu chưa kiểm soát dữ liệu được ghi. Với test có thông tin nhạy cảm, dùng handler chọn lọc và dữ liệu giả.

## 13. Nguyên tắc thực hành

1. Dùng ResultMatcher để xác nhận hợp đồng HTTP; dùng ResultHandler để quan sát kết quả.
2. Đặt andDo(print()) trước các matcher có khả năng thất bại nếu cần output khi assertion không đạt.
3. Dùng alwaysDo(print()) khi cần in mọi request qua một MockMvc instance trong giai đoạn điều tra.
4. Dùng andReturn() để đọc MvcResult và kiểm tra sâu hơn request, response, handler, exception, model hoặc flash attributes.
5. Dùng getResolvedException() khi exception đã được Spring MVC resolver xử lý.
6. Khi perform ném exception trước khi trả ResultActions, điều tra stack trace và cấu hình resolver.
7. Với request async, xác nhận asyncStarted và kiểm tra response cuối cùng qua asyncDispatch.
8. Ưu tiên matcher có thông báo rõ ràng và đặt tên cho matcher tùy chỉnh theo điều kiện cần kiểm tra.
9. Giữ log tập trung, dễ đọc và không chứa thông tin xác thực hoặc dữ liệu nhạy cảm.
10. Sau khi tìm được nguyên nhân, giữ lại những assertion có giá trị và loại bỏ cấu hình in tạm thời không cần thiết.

ResultHandler và print giúp nhìn thấy những gì Spring MVC đã xử lý; MvcResult cung cấp dữ liệu để điều tra sâu hơn; ResultMatcher biến kỳ vọng thành điều kiện kiểm thử rõ ràng. Kết hợp đúng ba cơ chế này giúp một lỗi MockMvc không chỉ báo rằng test thất bại mà còn cung cấp đủ dấu vết để xác định request đã đi đến đâu, thành phần nào xử lý nó và response thực tế được tạo ra như thế nào.

