# Chọn một phong cách assertion nhất quán trong bộ kiểm thử

**Ngữ cảnh:** Spring Framework Testing → MockMvcTester.

Khi kiểm thử Spring MVC, một request có thể được xác nhận bằng nhiều cách. Spring MVC Test truyền thống dùng **MockMvc**, **ResultActions** và **ResultMatcher** để kiểm tra kết quả. Từ Spring Framework 6.2, **MockMvcTester** cung cấp một API assertion dựa trên AssertJ với cách viết fluent hơn.

Cả hai phong cách đều có thể kiểm tra cùng một hợp đồng HTTP. Khác biệt chính nằm ở cách diễn đạt kỳ vọng, khả năng kết hợp assertion và cách tổ chức bộ test. Một dự án nên chọn phong cách chính phù hợp với phiên bản Spring, thư viện đang dùng và nhu cầu của nhóm, sau đó áp dụng nhất quán trong từng phạm vi kiểm thử.

Chọn nhất quán không có nghĩa mọi test trong toàn bộ repository bắt buộc phải dùng cùng một API. Một module cũ có thể tiếp tục dùng ResultMatcher; module mới có thể chọn MockMvcTester. Điều cần tránh là mỗi test tự trộn nhiều cách assertion mà không có lý do rõ ràng, khiến người đọc phải liên tục đổi cách hiểu và khó duy trì helper dùng chung.

## 1. Hai phong cách assertion trong Spring MVC Test

### 1.1. MockMvc với ResultMatcher

MockMvc là API nền tảng để thực thi request giả lập qua Spring MVC. Phương thức **perform** nhận một request builder và trả về **ResultActions**.

Test truyền thống thường nối các matcher bằng **andExpect**:

~~~java
mockMvc.perform(get("/orders/42")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("PAID"));
~~~

Các matcher được cung cấp theo nhóm:

- **status()**: kiểm tra HTTP status.
- **header()**: kiểm tra response header.
- **content()**: kiểm tra content type, encoding hoặc nội dung.
- **jsonPath()**: truy cập dữ liệu JSON theo biểu thức JSONPath.
- **xpath()**: truy cập XML.
- **view()** và **model()**: kiểm tra tên view và model của MVC controller.
- **flash()** và **redirectedUrl()**: kiểm tra redirect và flash attributes.
- **request()**: kiểm tra các trạng thái request, ví dụ async.

Cách viết này mô tả rõ request được thực thi rồi từng điều kiện được xác nhận. Các matcher của Spring có thông báo lỗi theo từng điều kiện, phù hợp với bộ test đã sử dụng MockMvc lâu năm.

### 1.2. MockMvcTester với AssertJ

**MockMvcTester** được giới thiệu trong Spring Framework 6.2. API này cung cấp cách gửi request và xác nhận kết quả theo phong cách AssertJ.

Ví dụ tương đương:

~~~java
MockMvcTester mvcTester = MockMvcTester.create(mockMvc);

assertThat(mvcTester.get().uri("/orders/42")
                .accept(MediaType.APPLICATION_JSON))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.id")
        .isEqualTo(42);
~~~

Trong ví dụ này:

- **mvcTester.get()** tạo request GET.
- **uri(...)** chỉ định đường dẫn.
- **accept(...)** chỉ định media type mà client chấp nhận.
- **assertThat(...)** bắt đầu chuỗi assertion AssertJ trên kết quả MVC.
- **hasStatusOk()** xác nhận HTTP 200.
- **bodyJson()** truy cập response body dưới dạng JSON.
- **extractingPath(...)** lấy một giá trị theo JSONPath để tiếp tục assertion.

Phong cách này phù hợp khi nhóm đã quen với AssertJ và muốn các assertion HTTP có cách diễn đạt tương tự assertion trên object, collection hoặc exception trong các test Java khác.

### 1.3. So sánh nhanh

| Tiêu chí | MockMvc + ResultMatcher | MockMvcTester + AssertJ |
|---|---|---|
| API thực thi request | MockMvc.perform(...) | MockMvcTester.get()/post()/... |
| Cách kiểm tra | andExpect(matcher) | assertThat(...).hasStatus... |
| Thư viện assertion | Spring ResultMatcher | AssertJ |
| Kiểu tổ chức | Chuỗi matcher theo nhóm của Spring | Chuỗi assertion fluent |
| Phiên bản Spring | Có từ các phiên bản Spring MVC Test trước đây | Spring Framework 6.2 trở lên |
| Phù hợp với | Bộ test hiện hữu, matcher chuyên biệt, codebase cũ | Bộ test mới, nhóm dùng AssertJ, assertion fluent |
| Tái sử dụng | Custom ResultMatcher và helper | AssertJ assertion/helper và cấu trúc fluent |

Hai cách đều dùng hạ tầng Spring MVC Test. MockMvcTester không thay thế DispatcherServlet, controller, converter, validator hoặc cấu hình MVC; nó thay đổi giao diện viết request và assertion.

## 2. Điều kiện để sử dụng MockMvcTester

MockMvcTester thuộc Spring Test và được bổ sung từ Spring Framework 6.2. Để sử dụng, cần có phiên bản Spring tương thích và AssertJ trên test classpath.

Ví dụ Gradle:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.assertj:assertj-core")
}
~~~

Phiên bản thực tế cần được quản lý đồng bộ với Spring Framework mà dự án đang sử dụng. Nếu dùng Spring Boot dependency management, nên để BOM hoặc plugin quản lý phiên bản tương thích thay vì tự khai báo một phiên bản spring-test khác với các module Spring còn lại.

Nếu dự án đang dùng Spring Framework thấp hơn 6.2, MockMvcTester chưa có sẵn. Khi đó có thể tiếp tục dùng MockMvc với ResultMatcher hoặc lên kế hoạch nâng cấp framework trước khi áp dụng API mới. Không nên thêm một lớp tự viết mô phỏng MockMvcTester chỉ để làm cú pháp ngắn hơn.

### 2.1. Tạo MockMvcTester từ MockMvc hiện có

Khi đã có MockMvc được cấu hình bằng standalone setup hoặc web application context, có thể tạo MockMvcTester từ instance đó:

~~~java
MockMvcTester mvcTester = MockMvcTester.create(mockMvc);
~~~

Điều này cho phép giữ nguyên cách thiết lập controller, filter, ControllerAdvice, converter, Validator và các thành phần MVC khác. Chỉ lớp biểu đạt request/assertion thay đổi.

Ví dụ với Spring TestContext:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = MvcTestConfig.class)
class OrderControllerTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    MockMvcTester mvcTester;

    @BeforeEach
    void setUp() {
        MockMvc mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();

        mvcTester = MockMvcTester.create(mockMvc);
    }
}
~~~

Cách này hữu ích khi muốn áp dụng MockMvcTester mà không phải thay đổi cấu hình MVC hiện có. Các bean trong WebApplicationContext vẫn là nguồn cấu hình cho request.

## 3. Viết cùng một kiểm thử theo hai phong cách

Giả sử API có endpoint GET trả về đơn hàng:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse findById(@PathVariable long id) {
        return new OrderResponse(id, "PAID");
    }
}

record OrderResponse(long id, String status) {}
~~~

### 3.1. Phiên bản dùng ResultMatcher

~~~java
@Test
void returnsOrderDetails() throws Exception {
    mockMvc.perform(get("/orders/42")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.status").value("PAID"));
}
~~~

Mỗi điều kiện được thể hiện bằng một matcher. Khi một điều kiện không đạt, thông báo lỗi chỉ ra matcher thất bại và giá trị thực tế nếu matcher hỗ trợ hiển thị.

### 3.2. Phiên bản dùng MockMvcTester

~~~java
@Test
void returnsOrderDetails() {
    assertThat(mvcTester.get().uri("/orders/42")
                    .accept(MediaType.APPLICATION_JSON))
            .hasStatusOk()
            .bodyJson()
            .extractingPath("$.id")
            .isEqualTo(42);
}
~~~

Có thể kiểm tra trường khác trong một assertion riêng nếu cần:

~~~java
@Test
void returnsPaidOrder() {
    assertThat(mvcTester.get().uri("/orders/42"))
            .hasStatusOk()
            .bodyJson()
            .extractingPath("$.status")
            .isEqualTo("PAID");
}
~~~

Các đoạn trên minh họa cách diễn đạt. Một test thực tế nên chọn tập điều kiện đủ để xác nhận hợp đồng endpoint. Không cần lặp lại cùng một request chỉ để xác nhận từng field nếu có thể kiểm tra các điều kiện quan trọng trong cùng một chuỗi hoặc helper dễ đọc.

### 3.3. Kiểm tra request có body

Với MockMvc truyền thống:

~~~java
@Test
void createsOrder() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": "An"
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.customerName").value("An"));
}
~~~

Với MockMvcTester:

~~~java
@Test
void createsOrder() {
    assertThat(mvcTester.post().uri("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": "An"
                            }
                            """))
            .hasStatus(HttpStatus.CREATED)
            .bodyJson()
            .extractingPath("$.customerName")
            .isEqualTo("An");
}
~~~

Request builder của MockMvcTester cung cấp cách khai báo method, URI, header, parameter, content type và body tương ứng với request cần gửi. Điều quan trọng là dữ liệu test và kỳ vọng HTTP phải giữ nguyên khi chuyển từ phong cách này sang phong cách kia.

## 4. Chọn phong cách theo đặc điểm của bộ kiểm thử

Không có một phong cách assertion tốt nhất cho mọi repository. Nên lựa chọn dựa trên các yếu tố cụ thể.

### 4.1. Giữ ResultMatcher khi bộ test đã ổn định

Nếu dự án có nhiều test sử dụng:

- Custom ResultMatcher.
- Matcher của Spring cho model, view, flash attributes và redirect.
- Request async với các assertion đặc thù.
- Các helper đã được nhóm phát triển sử dụng rộng rãi.

Thì tiếp tục dùng ResultMatcher là lựa chọn hợp lý. Việc đổi cú pháp không tự làm tăng độ tin cậy của test. Nếu bộ test đang rõ ràng, dễ bảo trì và đã có thông báo lỗi tốt, chỉ nên đổi khi có lợi ích cụ thể.

### 4.2. Chọn MockMvcTester cho test mới khi phù hợp

MockMvcTester phù hợp khi:

- Dự án dùng Spring Framework 6.2 trở lên.
- AssertJ đã là thư viện assertion chính.
- Test chủ yếu xác nhận status, header, content và JSON response.
- Nhóm muốn một phong cách fluent thống nhất giữa MVC test và các test Java khác.
- Các thành viên đã quen với cách tổ chức assertion của AssertJ.

Với test mới, có thể tạo một quy ước trong test support để khởi tạo MockMvcTester từ MockMvc đã cấu hình. Điều này giữ cấu hình request tập trung và tránh mỗi test tự tạo một instance khác nhau.

### 4.3. Không chọn chỉ vì số dòng code ngắn hơn

Một assertion ngắn không tự động dễ hiểu hơn. Ví dụ:

~~~java
assertThat(mvcTester.get().uri("/orders/42"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.id")
        .isEqualTo(42);
~~~

Ngắn gọn, nhưng nếu người đọc chưa quen MockMvcTester thì có thể khó hiểu bodyJson và extractingPath làm gì.

Ngược lại, chuỗi ResultMatcher dài hơn nhưng các tên matcher như status, contentTypeCompatibleWith và jsonPath mô tả trực tiếp mục tiêu.

Nên chọn API mà phần lớn thành viên có thể đọc, sửa và chẩn đoán khi test thất bại. Nếu một phong cách được chọn, hãy thống nhất import, helper và cách đặt tên trong phạm vi module.

## 5. Quy ước nhất quán ở cấp class, package và module

Có thể đặt quy ước theo phạm vi:

| Phạm vi | Quy ước gợi ý |
|---|---|
| Test class mới | Chọn một phong cách assertion chính |
| Package test hiện hữu | Giữ phong cách đang được sử dụng nếu không có lý do thay đổi |
| Module mới | Chọn phong cách theo phiên bản Spring và chuẩn của nhóm |
| Toàn repository | Cho phép module cũ và mới khác nhau khi có lý do rõ ràng |
| Helper dùng chung | Không buộc test phải chuyển sang một phong cách nếu helper không phục vụ cả hai |

Không cần ép toàn bộ repository đổi cùng một lúc. Repository có thể có nhiều module với phiên bản Spring hoặc mức trưởng thành khác nhau. Quy ước ở cấp module giúp giảm chi phí chuyển đổi và tránh tạo một đợt sửa lớn chỉ để thống nhất cú pháp.

### 5.1. Một test nên có một phong cách chính

Ví dụ nên tránh:

~~~java
@Test
void returnsOrder() throws Exception {
    MvcResult result = mockMvc.perform(get("/orders/42"))
            .andExpect(status().isOk())
            .andReturn();

    assertThat(result.getResponse().getStatus()).isEqualTo(200);
    assertThat(result.getResponse().getContentAsString())
            .contains("\"id\":42");
}
~~~

Test này kiểm tra status bằng ResultMatcher rồi lại kiểm tra status bằng AssertJ trên response. Hai assertion trùng lặp, làm tăng dòng code nhưng không tăng bằng chứng.

Nếu chọn ResultMatcher:

~~~java
@Test
void returnsOrder() throws Exception {
    mockMvc.perform(get("/orders/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42));
}
~~~

Nếu chọn MockMvcTester:

~~~java
@Test
void returnsOrder() {
    assertThat(mvcTester.get().uri("/orders/42"))
            .hasStatusOk()
            .bodyJson()
            .extractingPath("$.id")
            .isEqualTo(42);
}
~~~

Trong một số trường hợp, cần lấy MvcResult để kiểm tra dữ liệu không có assertion fluent tương ứng. Khi đó có thể dùng API cấp thấp một cách có chủ đích. Điều quan trọng là không lặp lại cùng điều kiện ở cả hai phong cách và ghi rõ lý do nếu phải kết hợp.

### 5.2. Thống nhất cách kiểm tra JSON

Với ResultMatcher, nhóm thường dùng JSONPath:

~~~java
.andExpect(jsonPath("$.customer.name").value("An"))
.andExpect(jsonPath("$.items").isArray())
.andExpect(jsonPath("$.items.length()").value(2))
~~~

Với MockMvcTester, có thể dùng bodyJson và extractingPath:

~~~java
assertThat(mvcTester.get().uri("/orders/42"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.customer.name")
        .isEqualTo("An");
~~~

Nên thống nhất cách kiểm tra field, array, null, số lượng và kiểu dữ liệu trong phạm vi test. Tránh một class dùng JSONPath, class khác parse toàn bộ body thành chuỗi, class khác nữa dùng ObjectMapper nếu không có lý do về độ phức tạp hoặc yêu cầu kiểm tra.

### 5.3. Thống nhất cách kiểm tra lỗi

Với ResultMatcher:

~~~java
mockMvc.perform(get("/orders/404"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
~~~

Với MockMvcTester:

~~~java
assertThat(mvcTester.get().uri("/orders/404"))
        .hasStatusNotFound()
        .bodyJson()
        .extractingPath("$.code")
        .isEqualTo("ORDER_NOT_FOUND");
~~~

Dù dùng API nào, test nên xác nhận cả status và error contract quan trọng. Chỉ kiểm tra status 404 có thể bỏ sót trường hợp một endpoint trả sai mã lỗi hoặc body không theo cấu trúc mà client mong đợi.

## 6. Kết hợp với các thành phần assertion khác

### 6.1. AssertJ cho kết quả domain

MockMvcTester dùng AssertJ cho kết quả MVC. AssertJ cũng phù hợp để kiểm tra các object domain, DTO hoặc collection được tạo trong test.

Ví dụ một test service:

~~~java
assertThat(order.getStatus()).isEqualTo(OrderStatus.PAID);
assertThat(order.getItems())
        .extracting(OrderItem::getProductCode)
        .containsExactly("P-01", "P-02");
~~~

Nếu MVC test chọn MockMvcTester, cách viết assertion có thể đồng nhất với những test khác dùng AssertJ. Nếu MVC test chọn ResultMatcher, vẫn có thể dùng AssertJ cho kết quả domain ở những phần kiểm tra riêng, nhưng nên phân biệt rõ assertion trên HTTP result và assertion trên object Java.

### 6.2. AssertJ không thay thế mọi matcher của Spring

Spring MVC Test có các matcher chuyên biệt cho những phần của MVC như:

- Model và view.
- Flash attribute.
- Redirect và forward.
- Async request.
- Session và request attributes.
- Content và JSON/XML.

MockMvcTester cung cấp nhiều assertion fluent cho kết quả MVC, nhưng không nên giả định mọi matcher hoặc extension hiện có trong dự án đều có bản tương đương trực tiếp. Khi cần một khả năng chuyên biệt, hãy xem API của phiên bản Spring đang dùng và chọn cách kiểm tra rõ ràng nhất.

Nếu một test cần kiểm tra sâu một đặc tính chỉ có ở ResultMatcher hoặc ResultHandler, có thể giữ test đó dùng MockMvc truyền thống. Không nên chuyển đổi chỉ để đồng nhất hình thức rồi phải viết thêm lớp adapter khó hiểu.

### 6.3. Chẩn đoán bằng print và MvcResult

Với MockMvc truyền thống, có thể gắn ResultHandler:

~~~java
mockMvc.perform(get("/orders/42"))
        .andDo(print())
        .andExpect(status().isOk());
~~~

Hoặc lấy MvcResult:

~~~java
MvcResult result = mockMvc.perform(get("/orders/42"))
        .andReturn();

assertThat(result.getResponse().getStatus()).isEqualTo(200);
~~~

MockMvcTester tập trung vào assertion fluent trên kết quả request. Khi cần một handler hoặc API quan sát chi tiết mà cách viết hiện tại không biểu đạt thuận tiện, có thể dùng MockMvc ở một test chẩn đoán chuyên biệt hoặc truy cập kết quả theo API được cung cấp bởi phiên bản đang dùng.

Không nên tạo một helper vừa thực hiện request bằng MockMvcTester, vừa thực hiện lại request bằng MockMvc chỉ để in output. Hai request có thể đi qua hai trạng thái test khác nhau, làm dữ liệu chẩn đoán không còn tương ứng với assertion.

## 7. Tổ chức cấu hình dùng chung

Một nhóm test có thể dùng chung factory để tạo MockMvc và MockMvcTester.

Ví dụ với Spring Framework TestContext:

~~~java
abstract class AbstractMvcTest {

    @Autowired
    protected WebApplicationContext webApplicationContext;

    protected MockMvc mockMvc;
    protected MockMvcTester mvcTester;

    @BeforeEach
    void configureMvc() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();

        mvcTester = MockMvcTester.create(mockMvc);
    }
}
~~~

Test con chọn một phong cách chính. Nếu package quy ước dùng MockMvcTester:

~~~java
class OrderControllerTest extends AbstractMvcTest {

    @Test
    void returnsOrder() {
        assertThat(mvcTester.get().uri("/orders/42"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.id")
                .isEqualTo(42);
    }
}
~~~

Nếu package vẫn dùng ResultMatcher:

~~~java
class LegacyOrderControllerTest extends AbstractMvcTest {

    @Test
    void returnsOrder() throws Exception {
        mockMvc.perform(get("/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42));
    }
}
~~~

Đây là một cách tổ chức minh họa. Có thể dùng composition hoặc test support theo cấu trúc dự án. Không nên tạo một base class quá lớn chứa mọi kiểu assertion, mọi converter và mọi mock dependency của toàn ứng dụng; cấu hình dùng chung nên phản ánh những thành phần MVC thật sự chung.

Nếu dùng standalone setup, có thể tạo factory trả về MockMvc đã đăng ký controller, advice, converter và validator cần thiết. Sau đó tạo MockMvcTester từ instance đó. Như vậy hai lớp vẫn tách bạch: factory chịu trách nhiệm cấu hình MVC, còn test class chịu trách nhiệm chọn phong cách assertion.

## 8. Chuyển dần từ ResultMatcher sang MockMvcTester

Một dự án đang có nhiều test ResultMatcher có thể chuyển đổi theo từng phần. Không cần sửa toàn bộ test chỉ để dùng API mới.

### Bước 1: Xác định điều kiện nền tảng

Kiểm tra phiên bản Spring Framework đang dùng. MockMvcTester yêu cầu Spring Framework 6.2 trở lên và AssertJ trên test classpath.

Nếu dự án chưa đạt điều kiện này, tiếp tục dùng MockMvc truyền thống hoặc lập kế hoạch nâng cấp framework riêng. Không trộn một spring-test mới vào ứng dụng đang dùng các module Spring phiên bản cũ mà không quản lý dependency alignment.

### Bước 2: Chọn một test đại diện

Chọn một test có request đơn giản, ví dụ GET JSON trả HTTP 200. Chuyển test đó sang MockMvcTester và giữ nguyên:

- Request method và URI.
- Query parameter, header và body.
- HTTP status kỳ vọng.
- Content type và các trường response quan trọng.

So sánh mục tiêu kiểm tra, không chỉ so sánh số dòng code.

### Bước 3: Chuyển theo nhóm có cùng đặc điểm

Có thể chuyển lần lượt:

- GET endpoint trả JSON.
- POST endpoint nhận JSON và trả JSON.
- Validation error.
- Exception handler.
- Redirect/model/view nếu API fluent hỗ trợ đầy đủ nhu cầu.
- Async hoặc trường hợp MVC chuyên biệt.

Những test có matcher đặc thù hoặc helper phức tạp có thể tiếp tục dùng ResultMatcher. Không nên ép chuyển đổi nếu kết quả là một lớp wrapper khó đọc hơn API hiện tại.

### Bước 4: Cập nhật test support khi cần

Nếu có helper tạo MockMvc, có thể bổ sung factory tạo MockMvcTester từ cùng MockMvc. Giữ cấu hình MVC tại một nơi để hai phong cách không vô tình dùng hai cấu hình khác nhau.

Không tạo hai bộ cấu hình riêng chỉ vì có hai phong cách assertion. Điều cần thay đổi là cách test diễn đạt kỳ vọng, không phải cách controller được đăng ký hoặc cách request được xử lý.

### Bước 5: Đặt quy ước cho test mới

Sau khi nhóm thống nhất phong cách chính, ghi rõ trong test support hoặc hướng dẫn module:

- Test MVC mới dùng phong cách nào.
- Khi nào được giữ ResultMatcher cho matcher chuyên biệt.
- Cách tạo MockMvcTester.
- Cách in/chẩn đoán khi test thất bại.
- Quy tắc tránh assertion trùng lặp.

Quy ước rõ ràng giúp test mới không phát sinh thêm nhiều cách viết khác nhau.

## 9. Các trường hợp nên giữ MockMvc truyền thống

MockMvcTester không làm MockMvc cũ trở nên lỗi thời. Một số tình huống tiếp tục dùng ResultMatcher hoặc ResultHandler có thể rõ ràng hơn.

### 9.1. Test dùng nhiều matcher chuyên biệt

Nếu test kiểm tra đồng thời model, view, flash attribute, forward và session, ResultMatcher của Spring có thể thể hiện ý định trực tiếp. Chỉ chuyển sang MockMvcTester khi API của phiên bản đang dùng hỗ trợ đầy đủ và cú pháp mới dễ đọc hơn.

### 9.2. Test cần ResultHandler

Nếu test cần print, lưu MvcResult, thu thập thông tin handler hoặc chụp request/response theo một quy trình tùy chỉnh, MockMvc truyền thống cung cấp andDo và andReturn trực tiếp.

### 9.3. Test đã có helper ổn định

Một bộ test có custom ResultMatcher và helper tốt không cần chuyển đổi chỉ để theo xu hướng. Chi phí chuyển đổi gồm sửa test, cập nhật tài liệu, hướng dẫn thành viên và xử lý khác biệt thông báo lỗi. Chỉ nên thực hiện khi lợi ích bảo trì hoặc khả năng đọc đủ lớn.

### 9.4. Phiên bản framework chưa hỗ trợ

Nếu module vẫn dùng Spring Framework trước 6.2, ResultMatcher là lựa chọn tự nhiên. Hãy tránh tạo một quy ước yêu cầu API chưa có trong dependency của module.

## 10. Những lỗi thường gặp khi chọn phong cách assertion

### Dùng MockMvcTester nhưng thiếu AssertJ

Nếu class MockMvcTester không được tìm thấy hoặc API không khả dụng, kiểm tra phiên bản Spring Test và dependency AssertJ. Cũng cần kiểm tra dependency resolution để chắc chắn spring-test thực tế được nạp đúng phiên bản.

### API MockMvcTester không tồn tại ở phiên bản Spring đang dùng

MockMvcTester được thêm từ Spring Framework 6.2. Kiểm tra phiên bản resolved của spring-test thay vì chỉ xem version được khai báo ở một file build. Dependency management hoặc module khác có thể quyết định phiên bản cuối cùng.

### Test có hai assertion cho cùng một điều kiện

Ví dụ vừa gọi status().isOk() vừa assertThat(response.getStatus()).isEqualTo(200). Giữ một assertion là đủ. Chỉ giữ hai cách nếu chúng xác nhận hai đặc tính khác nhau và có lý do rõ ràng.

### Dùng AssertJ trên raw response body cho mọi trường hợp

Việc lấy body thành String rồi contains có thể bỏ qua cấu trúc JSON, kiểu dữ liệu hoặc trường trùng tên. Dùng JSONPath hoặc bodyJson/extractingPath để kiểm tra đúng cấu trúc cần xác nhận.

### Chuyển đổi làm mất matcher quan trọng

Trước khi thay ResultMatcher bằng MockMvcTester, liệt kê các điều kiện hiện tại của test. Đảm bảo phiên bản mới vẫn xác nhận status, header, content type, body, model, redirect hoặc async theo yêu cầu. Không bỏ assertion chỉ vì chưa quen API tương đương.

### Dùng một helper che giấu phong cách

Một helper chung có thể trả về kiểu quá tổng quát hoặc bọc cả MockMvc lẫn MockMvcTester, khiến test không còn rõ nó đang dùng API nào. Helper nên giảm lặp lại cấu hình, không che mất cách assertion.

### Trộn phong cách tùy tiện giữa các test gần nhau

Nếu hai test trong cùng class dùng hai phong cách mà không có lý do, người đọc phải chuyển ngữ cảnh liên tục. Chọn phong cách chính cho class hoặc package; trường hợp đặc biệt cần được thể hiện rõ.

## 11. Ví dụ một bộ test có quy ước rõ ràng

Giả sử module chọn MockMvcTester cho các test MVC mới. Một test class có thể như sau:

~~~java
class OrderControllerTest {

    private final MockMvcTester mvcTester;

    OrderControllerTest(MockMvcTester mvcTester) {
        this.mvcTester = mvcTester;
    }

    @Test
    void returnsOrderDetails() {
        assertThat(mvcTester.get().uri("/orders/42"))
                .hasStatusOk()
                .bodyJson()
                .extractingPath("$.id")
                .isEqualTo(42);
    }

    @Test
    void returnsNotFoundForMissingOrder() {
        assertThat(mvcTester.get().uri("/orders/404"))
                .hasStatusNotFound()
                .bodyJson()
                .extractingPath("$.code")
                .isEqualTo("ORDER_NOT_FOUND");
    }

    @Test
    void createsOrder() {
        assertThat(mvcTester.post().uri("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerName": "An"
                                }
                                """))
                .hasStatus(HttpStatus.CREATED)
                .bodyJson()
                .extractingPath("$.customerName")
                .isEqualTo("An");
    }
}
~~~

Đoạn code trên minh họa quy ước dùng MockMvcTester; cách cung cấp instance qua constructor phụ thuộc vào cấu hình test hoặc test framework mà dự án chọn. Trong Spring TestContext, có thể inject bean nếu cấu hình đã đăng ký; hoặc tạo MockMvcTester trong setup từ MockMvc. Không nên coi constructor trên là cấu hình tự động có sẵn trong mọi project Spring.

Nếu module chọn ResultMatcher, các test có thể giữ cấu trúc:

~~~java
class OrderControllerTest {

    @Test
    void returnsOrderDetails() throws Exception {
        mockMvc.perform(get("/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42));
    }

    @Test
    void returnsNotFoundForMissingOrder() throws Exception {
        mockMvc.perform(get("/orders/404"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("ORDER_NOT_FOUND"));
    }

    @Test
    void createsOrder() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerName": "An"
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.customerName").value("An"));
    }
}
~~~

Hai cách đều tạo được bằng chứng tương đương cho API. Chọn một cách làm chuẩn trong phạm vi test sẽ giúp code review dễ dàng nhận ra khi một endpoint bị thiếu assertion.

## 12. Nguyên tắc thực hành

1. Kiểm tra phiên bản Spring trước khi chọn MockMvcTester; API này yêu cầu Spring Framework 6.2 trở lên.
2. Dùng MockMvc + ResultMatcher nếu bộ test hiện hữu đã ổn định hoặc cần các matcher chuyên biệt.
3. Chọn MockMvcTester khi dự án dùng Spring tương thích, AssertJ đã có và nhóm muốn assertion fluent.
4. Chọn một phong cách chính cho mỗi test class hoặc package; không trộn hai cách chỉ vì sở thích cá nhân.
5. Giữ nguyên request và hợp đồng cần xác nhận khi chuyển đổi test.
6. Không lặp lại cùng một assertion bằng ResultMatcher và AssertJ.
7. Dùng JSONPath hoặc bodyJson/extractingPath để kiểm tra cấu trúc JSON thay vì so sánh chuỗi tùy tiện.
8. Giữ MockMvc truyền thống cho trường hợp cần ResultHandler, MvcResult hoặc matcher chuyên biệt khi cách fluent chưa đáp ứng tốt.
9. Tái sử dụng cùng cấu hình MVC khi tạo MockMvc và MockMvcTester; không tạo hai cấu hình khác nhau chỉ vì hai API assertion.
10. Chuyển đổi theo nhóm nhỏ, giữ lại test có giá trị và cập nhật quy ước cho test mới.

Một bộ kiểm thử MVC nhất quán giúp người đọc tập trung vào hành vi của endpoint thay vì phải học lại cách diễn đạt assertion trong từng test. ResultMatcher phù hợp với cách kiểm tra chuyên biệt của Spring MVC Test; MockMvcTester mang phong cách AssertJ đến kết quả MVC trong Spring Framework 6.2 trở lên. Chọn dựa trên phiên bản, nhu cầu và thói quen của nhóm, rồi giữ cách viết ổn định trong phạm vi đã thống nhất.

