# Phạm vi context, test fixture và isolation giữa các operation

## 1. Vì sao scope và isolation quan trọng?

Trong module **SPRING_REST_DOCS**, Spring REST Docs tạo tài liệu REST API từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Mỗi test thực hiện một operation, xác minh response rồi ghi generated snippets như HTTP request, HTTP response, request fields, response fields, headers hoặc links. Các snippet được ghép vào Asciidoctor/Markdown và xuất bản cùng build.

Khi nhiều test cùng chạy trong một JVM, cùng dùng application context, fixture hoặc thư mục generated snippets, cần xác định dữ liệu nào thuộc test nào. Nếu scope không rõ, lỗi thường gặp là:

- Test ghi đè snippet của operation khác do dùng chung identifier.
- Test phụ thuộc thứ tự chạy vì cùng sửa fixture hoặc dữ liệu database.
- Documentation context được tạo một lần rồi dùng cho nhiều test invocation.
- Test song song ghi vào cùng file.
- Mock hoặc mutable state còn sót từ operation trước.
- Test riêng lẻ pass nhưng chạy toàn suite lại fail.
- Tài liệu được biên soạn từ snippet cũ hoặc fixture không khớp operation.

Bài học này phân biệt ba phạm vi: **documentation context**, **test fixture** và **snippet/output**. Nguyên tắc thực hành là một test tài liệu hóa một kịch bản HTTP có tên rõ ràng, dùng fixture có thể tái tạo, tạo snippet không xung đột và dọn dẹp state mà nó sở hữu.

## 2. Documentation context là gì?

REST Docs cần biết test nào đang tạo snippet, thông tin context và output directory. Với JUnit Jupiter, `RestDocumentationExtension` tích hợp vào extension lifecycle và cung cấp `RestDocumentationContextProvider`.

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }
}
```

Provider được inject vào callback cho test hiện tại. Cấu hình MockMvc sử dụng provider đó để lời gọi `document(...)` được liên kết với context tương ứng.

Không giữ provider hoặc documentation context của một test rồi tái sử dụng tùy tiện cho test khác. Hãy để extension quản lý lifecycle trong Jupiter. Với framework không có tích hợp extension tương ứng, `ManualRestDocumentation` yêu cầu gọi `beforeTest(...)` và `afterTest()` rõ ràng cho từng test.

### 2.1. Documentation context khác Spring ApplicationContext

Một dự án Spring có thể cache và tái sử dụng `ApplicationContext` giữa các test. Đó là context chứa bean và cấu hình ứng dụng. Documentation context là ngữ cảnh riêng phục vụ việc ghi snippet.

| Phạm vi | Chứa/điều phối | Vòng đời |
| --- | --- | --- |
| Spring `ApplicationContext` | Bean, controller, service, converter, filter, security config | Có thể cache và tái sử dụng |
| REST Docs documentation context | Ngữ cảnh ghi nhận test và sinh snippet | Theo lifecycle test |
| Test fixture | Input, dữ liệu test và state phụ trợ | Tạo/reset theo scenario |
| Snippet identifier | Tên thư mục operation output | Duy nhất cho nội dung khác nhau |

Có thể chia sẻ Spring application context nếu bean và môi trường được thiết kế phù hợp. Điều đó không có nghĩa một documentation context mutable hoặc fixture có state thay đổi cũng được chia sẻ an toàn.

## 3. Chọn phạm vi theo từng test invocation

Với JUnit Jupiter, `@BeforeEach` và `@AfterEach` chạy cho mỗi test method invocation. Với parameterized tests, setup/cleanup được áp dụng cho từng invocation. Đây là nơi phù hợp để chuẩn bị fixture và cấu hình test client gắn với documentation provider.

```java
@ExtendWith(RestDocumentationExtension.class)
class AccountDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new AccountController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @AfterEach
    void tearDown() {
        // Giải phóng tài nguyên mutable do test tự tạo nếu có.
    }
}
```

Không nhất thiết xây dựng mọi thành phần ứng dụng mới cho từng test. Có thể dùng Spring context được cache, fixture bất biến hoặc factory dùng chung. Điều quan trọng là state thay đổi được phải có owner và reset rõ ràng.

| Thành phần | Khuyến nghị |
| --- | --- |
| Documentation context | Cấp riêng theo test invocation |
| Snippet identifier | Riêng cho operation/scenario có nội dung khác nhau |
| Request body và expected response | Fixture rõ ràng của scenario |
| Mock expectation/history | Reset hoặc tạo mock độc lập |
| Database rows do test tạo | Dùng dữ liệu riêng hoặc reset |
| Test clock/random seed | Cố định để output tái lập |
| Immutable DTO/constants | Có thể chia sẻ |
| Application context bất biến | Có thể dùng Spring TestContext cache |
| Mutable singleton state | Tránh hoặc reset giữa test |
| Generated snippet file | Không để hai test ghi cùng đường dẫn |

`@BeforeAll` phù hợp với tài nguyên tốn kém nhưng bất biến. Không đặt fixture mutable của từng operation vào `@BeforeAll` rồi để các test cùng sửa chung.

## 4. Một operation, một fixture dễ hiểu

Giả sử API đơn hàng có các operation:

| Operation | Request | Kết quả mong đợi |
| --- | --- | --- |
| Lấy đơn hàng | `GET /api/orders/42` | `200` với order representation |
| Tạo đơn hàng | `POST /api/orders` | `201` với response/location phù hợp |
| Hủy đơn hàng | `POST /api/orders/42/cancel` | Status theo contract, ví dụ `204` |
| Không tìm thấy | `GET /api/orders/404` | `404` với error representation |

Mỗi scenario nên có fixture phản ánh chính xác trạng thái cần tài liệu hóa. Không dùng một object mutable rồi thay đổi status, items và payment theo thứ tự phụ thuộc giữa các test.

Ví dụ factory tạo fixture mới:

```java
final class OrderFixtures {

    private OrderFixtures() {}

    static OrderResponse confirmedOrder() {
        return new OrderResponse(
                "ORD-42", "CONFIRMED", 250000,
                List.of(new OrderItem("BK-01", 2)));
    }

    static OrderResponse cancelledOrder() {
        return new OrderResponse("ORD-43", "CANCELLED", 0, List.of());
    }
}
```

Mỗi lần gọi factory tạo object mới. Nếu fixture dùng collection mutable, hãy tạo collection riêng thay vì trả static list có thể bị sửa.

Một factory tốt làm rõ dữ liệu quan trọng của scenario. Tránh builder toàn cục có state ngầm như `currentOrder` hoặc `lastResponse` vì test có thể phụ thuộc test đã chạy trước.

### 4.1. Fixture bất biến

Record và collection immutable hữu ích để test không sửa nhầm fixture:

```java
record OrderItem(String sku, int quantity) {}

record OrderResponse(
        String orderId,
        String status,
        long totalAmount,
        List<OrderItem> items) {

    OrderResponse {
        items = List.copyOf(items);
    }
}
```

`List.copyOf` tạo snapshot không sửa được của danh sách. Nếu test cần thay đổi trạng thái, tạo fixture mới bằng factory/builder thay vì sửa fixture đang được chia sẻ.

## 5. Cô lập database, mock và external dependency

Generated snippets chỉ có giá trị khi response phản ánh đúng dữ liệu đã chuẩn bị. Khi endpoint gọi repository, message broker, payment gateway hoặc hệ thống khác, cần xác định test đang kiểm tra lớp nào:

- Với controller test cô lập, mock service/repository và định nghĩa kết quả rõ ràng.
- Với integration test, dùng database/test container phù hợp và chuẩn bị dữ liệu riêng.
- Với external API, dùng stub/server giả hoặc test double; không gọi hệ thống thật ngoài ý muốn.
- Xác định transaction rollback có thực sự áp dụng cho request hay không. Request chạy qua server/client khác thread hoặc process có thể không nằm trong transaction của test method.
- Dọn dữ liệu hoặc reset mock sau mỗi test nếu fixture có thể ảnh hưởng test khác.

Ví dụ stub service:

```java
private final OrderService orderService = mock(OrderService.class);

@BeforeEach
void prepareOrder() {
    reset(orderService);
    given(orderService.findById("42"))
            .willReturn(OrderFixtures.confirmedOrder());
}
```

Đoạn trên giả định Mockito và test setup tương ứng. Nếu mock được chia sẻ qua Spring context, cần reset interaction/behavior phù hợp hoặc thiết lập lại rõ ràng. Không mặc định mock bean trong context cache luôn độc lập giữa các method.

## 6. Mỗi operation cần snippet identifier riêng

`document("...")` chọn tên thư mục snippet. Nếu hai test khác nhau cùng ghi `orders-get`, chúng có thể dùng chung output path. Nội dung ghi sau có thể làm output không còn đại diện scenario mong muốn.

Đặt identifier theo resource + operation + outcome:

```java
.andDo(document("orders-get-success"))
```

```java
.andDo(document("orders-get-not-found"))
```

```java
.andDo(document("orders-create-validation-error"))
```

Identifier nên ổn định, mô tả operation/outcome, không phụ thuộc timestamp hoặc random UUID và không trùng giữa các test chạy song song.

Ví dụ cấu trúc:

```text
build/generated-snippets/
├── orders-get-success/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   └── response-fields.adoc
├── orders-get-not-found/
│   ├── http-request.adoc
│   └── http-response.adoc
└── orders-create-validation-error/
    ├── http-request.adoc
    └── http-response.adoc
```

Nếu nhiều test bổ sung snippet cho cùng operation, có thể gom vào một test rõ ràng hoặc đặt identifier riêng theo scenario. Không để hai test ghi cùng identifier với response khác nhau.

## 7. Ví dụ MockMvc với fixture riêng cho mỗi operation

Ví dụ dưới đây thể hiện hai operation độc lập: xem đơn thành công và xem đơn không tồn tại. Mỗi test có fixture, assertion và snippet identifier riêng.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.reset;
import static org.springframework.http.HttpStatus.NOT_FOUND;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderOperationDocumentationTest {

    private final OrderService orderService = mock(OrderService.class);
    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        reset(orderService);
        mockMvc = MockMvcBuilders.standaloneSetup(
                    new OrderController(orderService))
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void getExistingOrder() throws Exception {
        given(orderService.findById("42"))
                .willReturn(new OrderResponse("ORD-42", "CONFIRMED", 250000));

        mockMvc.perform(get("/api/orders/{id}", "42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-42"))
                .andExpect(jsonPath("$.status").value("CONFIRMED"))
                .andDo(document("orders-get-success",
                        responseFields(
                                fieldWithPath("orderId").description("Mã đơn hàng"),
                                fieldWithPath("status")
                                        .description("Trạng thái xử lý đơn"),
                                fieldWithPath("totalAmount")
                                        .description("Tổng tiền theo VND")
                        )));
    }

    @Test
    void getMissingOrder() throws Exception {
        given(orderService.findById("404")).willReturn(null);

        mockMvc.perform(get("/api/orders/{id}", "404")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andDo(document("orders-get-not-found"));
    }

    interface OrderService {
        OrderResponse findById(String id);
    }

    record OrderResponse(String orderId, String status, long totalAmount) {}

    @RestController
    static class OrderController {
        private final OrderService service;

        OrderController(OrderService service) {
            this.service = service;
        }

        @GetMapping("/api/orders/{id}")
        OrderResponse get(@PathVariable String id) {
            OrderResponse order = service.findById(id);
            if (order == null) {
                throw new ResponseStatusException(NOT_FOUND);
            }
            return order;
        }
    }
}
```

Đây là ví dụ minh họa cấu trúc. Trong dự án thực, controller/advice nên dùng implementation thật hoặc test configuration phù hợp. Điểm quan trọng là test not-found không phụ thuộc test success đã chạy trước để chuẩn bị dữ liệu.

## 8. Parameterized tests mà vẫn giữ isolation

Parameterized tests hữu ích khi cùng operation cần kiểm tra nhiều giá trị. Mỗi invocation là một lần chạy riêng, do đó snippet identifier phải dựa trên tham số có ý nghĩa và được chuẩn hóa.

```java
@ParameterizedTest
@CsvSource({
    "42, ORD-42",
    "43, ORD-43"
})
void getOrder(String id, String expectedOrderId) throws Exception {
    given(orderService.findById(id))
            .willReturn(OrderFixtures.order(expectedOrderId));

    mockMvc.perform(get("/api/orders/{id}", id))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value(expectedOrderId))
            .andDo(document("orders-get-" + id));
}
```

Nếu parameter là dữ liệu tự do, không dùng trực tiếp chuỗi có ký tự path không an toàn làm identifier. Có thể ánh xạ từng case sang tên tĩnh qua `Arguments` hoặc scenario key được kiểm soát.

Không dùng cùng identifier cho mọi invocation. Nếu các invocation chỉ kiểm tra assertion và chỉ một fixture đại diện cần đưa vào tài liệu, tách một test documentation riêng. Output sẽ tập trung vào kịch bản có giá trị cho người đọc.

## 9. Isolation khi chạy test song song

Chạy song song rút ngắn thời gian suite, nhưng cần kiểm tra tài nguyên dùng chung:

- Application context chứa bean singleton có state mutable.
- Mock dùng chung và interaction history.
- Database schema/table hoặc record cùng khóa.
- Port, file hoặc thư mục tạm dùng chung.
- Snippet identifier và generated output file.
- System properties, clock, locale hoặc environment variables.
- Static fixture/builder có trạng thái.

Hai test có documentation context riêng vẫn có thể xung đột nếu cùng ghi một snippet identifier. Documentation context riêng không tự tạo namespace output duy nhất cho mọi operation.

Nếu chưa bảo đảm isolation, có thể cấu hình nhóm documentation tests chạy tuần tự. Sau đó cải thiện bằng fixture độc lập, identifier riêng, resource riêng hoặc output directory được phân vùng có kiểm soát. Không bật parallel execution chỉ vì JUnit hỗ trợ tính năng đó.

### 9.1. Khi nào chia sẻ MockMvc?

MockMvc có thể được tái sử dụng nếu cấu hình và dependency ổn định. Tuy nhiên:

- Nếu MockMvc được tạo với documentation configuration gắn context của test, không mang instance đó sang test khác.
- Nếu MockMvc dùng application context ổn định, có thể chia sẻ theo Spring test setup; documentation configurer/filter phải phù hợp với test đang sinh snippet.
- Không mutate interceptor, filter hoặc result handler dùng chung trong khi test khác đang chạy.
- Không để mock/service/database state chia sẻ tạo phụ thuộc giữa request.

Ưu tiên một setup rõ ràng: Spring-managed MockMvc khi dùng application context thật; hoặc tạo MockMvc trong `@BeforeEach` cùng provider của test khi cần documentation context gắn theo invocation.

## 10. ManualRestDocumentation và cleanup thủ công

Với TestNG, Spock hoặc framework không có Jupiter extension, người viết phải giữ lifecycle rõ ràng:

```java
private final ManualRestDocumentation restDocumentation =
        new ManualRestDocumentation();

@BeforeMethod
public void before(Method method) {
    restDocumentation.beforeTest(getClass(), method.getName());
    // Tạo/configure HTTP client dùng provider này.
}

@AfterMethod(alwaysRun = true)
public void after() {
    restDocumentation.afterTest();
}
```

Không chia sẻ một `ManualRestDocumentation` đang hoạt động giữa các test đồng thời. Mỗi test invocation cần một context và một cặp before/after tương ứng. Cleanup phải chạy cả khi assertion thất bại; dùng hook cuối cùng của framework và đảm bảo teardown không bị bỏ qua.

Một test context có thể tạo nhiều snippet operation, nhưng mỗi `document("identifier")` cần tên riêng. Context scope và operation identifier là hai cấp khác nhau.

## 11. Tổ chức tài liệu và build theo operation

Asciidoctor include snippet theo identifier:

```adoc
= Order API
:snippets: build/generated-snippets

== Xem đơn hàng

=== Đơn hàng tồn tại
include::{snippets}/orders-get-success/http-request.adoc[]
include::{snippets}/orders-get-success/http-response.adoc[]
include::{snippets}/orders-get-success/response-fields.adoc[]

=== Không tìm thấy đơn hàng
include::{snippets}/orders-get-not-found/http-request.adoc[]
include::{snippets}/orders-get-not-found/http-response.adoc[]
```

Đường dẫn giả định Gradle output ở `build/generated-snippets`. Với Maven thường là `target/generated-snippets` hoặc vị trí cấu hình khác. Dùng một nguồn cấu hình nhất quán cho test và Asciidoctor.

Build nên chạy test sinh snippet trước task biên soạn tài liệu. CI cần phát hiện test thất bại do assertion/descriptor, identifier trùng, snippet cũ do task ordering, fixture không ổn định và race condition trên output.

Không chỉnh generated snippet bằng tay để sửa output. Sửa test, fixture hoặc descriptor rồi chạy lại task sinh snippet.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Hai operation ghi đè snippet | Dùng chung identifier | Tách identifier theo operation/outcome |
| Test phụ thuộc thứ tự | Fixture mutable hoặc state không reset | Tạo fixture mới/reset dependency mỗi test |
| Test riêng pass nhưng suite fail | Shared mock/database/static state | Cô lập mutable state |
| Snippet lấy response scenario trước | Stub không được thiết lập lại | Reset và stub trong test tương ứng |
| Documentation context dùng sai test | Giữ provider/context ngoài lifecycle | Để extension quản lý hoặc gọi manual lifecycle mỗi invocation |
| Parallel test ghi cùng file | Identifier/output location trùng | Phân vùng output hoặc chạy tuần tự |
| Parameterized test ghi đè snippet | Mọi invocation cùng identifier | Sinh identifier riêng hoặc có test đại diện |
| Cleanup chỉ chạy khi thành công | Teardown nằm trong thân test | Dùng `@AfterEach` hoặc hook always-run |
| Fixture thay đổi giữa lần chạy | Clock, random hoặc thứ tự dữ liệu không cố định | Cố định clock/seed và dữ liệu |
| Asciidoctor dùng snippet cũ | Task dependency sai | Chạy test sinh snippet trước Asciidoctor |

## 13. Checklist thiết kế một operation test

- [ ] Operation và outcome cần tài liệu hóa là gì?
- [ ] Test invocation nhận documentation context nào?
- [ ] HTTP client được cấu hình với context tương ứng chưa?
- [ ] Fixture request/response được tạo mới hoặc bất biến chưa?
- [ ] Mock và external dependency được stub/reset rõ ràng chưa?
- [ ] Database state và transaction cleanup đúng phạm vi request chưa?
- [ ] Identifier snippet riêng, ổn định và không trùng chưa?
- [ ] Test có assertion status/header/body cần thiết chưa?
- [ ] Descriptor phản ánh payload đúng operation chưa?
- [ ] Test an toàn khi chạy suite hoặc song song chưa?
- [ ] Asciidoctor include đúng identifier và task dependency chưa?

Không nhất thiết mỗi project phải tách một test class cho từng endpoint. Quan trọng là scope, state và identifier được phân định rõ.

## 14. Bài thực hành

Dùng API đơn hàng với operation GET, POST và cancel:

1. Tạo test Jupiter dùng `RestDocumentationExtension` và cấu hình MockMvc trong `@BeforeEach`.
2. Tạo fixture riêng cho đơn CONFIRMED và CANCELLED; xác nhận thay đổi fixture ở test này không ảnh hưởng test kia.
3. Tạo hai test GET success/not-found, dùng snippet identifier khác nhau và include cả hai vào Asciidoctor.
4. Cố ý dùng cùng identifier cho hai test, quan sát output xung đột rồi sửa tên theo operation/outcome.
5. Viết parameterized test cho nhiều order ID; bảo đảm invocation có identifier riêng hoặc tách test tài liệu đại diện.
6. Chạy hai test theo thứ tự ngược nhau để kiểm tra không có state phụ thuộc thứ tự.
7. Nếu dùng database, tạo dữ liệu khóa riêng và xác định transaction rollback có bao phủ request execution không.
8. Bật parallel execution cho nhóm test; kiểm tra mock, database và snippet output. Chỉ giữ parallel khi không có resource collision.
9. Thử `ManualRestDocumentation` với TestNG/Spock và đảm bảo teardown chạy khi test fail.
10. Chạy test sinh snippet trước Asciidoctor và kiểm tra trang tài liệu dùng output hiện tại.

**Tiêu chí hoàn thành:** bạn phân biệt application context và REST Docs documentation context; tạo fixture độc lập theo operation; quản lý mock/database/external state; dùng identifier riêng cho snippet; hiểu giới hạn chia sẻ tài nguyên khi chạy song song; và duy trì build sinh tài liệu tái lập.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started/index.html): cấu hình documentation context và HTTP test integrations.
- [Spring REST Docs — API Documentation](https://docs.spring.io/spring-restdocs/reference/index.html): sinh snippets từ MockMvc, WebTestClient và REST Assured.
- [JUnit 5 User Guide — Test Lifecycle](https://junit.org/junit5/docs/current/user-guide/#writing-tests-test-lifecycle): scope callback trước/sau test và test instance lifecycle.
- [JUnit 5 User Guide — Parallel Execution](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parallel-execution): bật và kiểm soát thực thi song song.
