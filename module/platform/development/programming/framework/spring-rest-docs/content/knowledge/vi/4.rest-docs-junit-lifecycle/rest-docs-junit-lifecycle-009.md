# Đặt tên test và operation để dễ truy tìm snippet

## 1. Vì sao tên test và tên operation cần nhất quán?

Trong module **SPRING_REST_DOCS**, các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured vừa kiểm chứng hành vi API vừa sinh generated snippets. Những snippet này được ghép vào tài liệu Asciidoctor/Markdown và thường được tạo lại trong build/CI.

Khi một API có nhiều operation và mỗi operation có nhiều kết quả, tên không rõ ràng sẽ khiến việc tìm nguồn snippet khó khăn. Ví dụ, thư mục `get-1` không cho biết đó là lấy tài khoản thành công, tài khoản không tồn tại hay lấy danh sách. Nếu một test method có tên chung `testApi()`, người review cũng khó xác định mục tiêu của test từ báo cáo CI.

Cần phân biệt hai loại tên:

- **Tên test:** định danh method/scenario trong JUnit, ví dụ `getExistingOrder_returns200` hoặc display name.
- **Tên operation/snippet:** chuỗi truyền vào `document("...")`, quyết định thư mục generated snippets, ví dụ `orders-get-success`.

JUnit không tự động đổi `@DisplayName` thành REST Docs snippet identifier. Hai tên có thể giống nhau về ý nghĩa, nhưng phải được nối với nhau bằng quy ước và code rõ ràng.

Bài này hướng dẫn:

1. Đặt tên test theo operation, scenario và outcome.
2. Đặt snippet identifier ổn định, có ý nghĩa và không trùng.
3. Liên kết test method, HTTP operation, snippet và đoạn include Asciidoctor.
4. Xử lý parameterized/dynamic tests và nhiều status của cùng endpoint.
5. Thiết kế tên dễ tìm trong báo cáo CI, generated snippets và code review.

## 2. Phân biệt test name, display name và snippet identifier

| Khái niệm | Ví dụ | Nơi xuất hiện | Mục đích |
| --- | --- | --- | --- |
| Test method name | `getOrder_whenExists_returns200` | Mã Java, báo cáo test | Nhận diện scenario kỹ thuật |
| JUnit display name | `GET order - existing - 200 OK` | IDE/test report | Giúp người đọc hiểu test |
| REST Docs identifier | `orders-get-success` | Đường dẫn generated snippets | Tên operation/scenario trong tài liệu |
| API path | `GET /api/orders/{id}` | HTTP request và tài liệu | Endpoint thực tế |
| Asciidoctor section | `Xem đơn hàng đã tồn tại` | Tài liệu được xuất bản | Điều hướng nội dung cho người đọc |

Một test có thể gửi HTTP request tới `GET /api/orders/42`, được JUnit hiển thị là `GET order - existing - 200 OK` và ghi snippet vào `orders-get-success`. Không có cơ chế tự động nào buộc ba chuỗi này phải giống hệt nhau.

**Quy tắc:** mỗi tên phục vụ một mục đích, nhưng cần đủ thông tin để người đọc lần ngược giữa chúng.

## 3. Đặt tên test method có cấu trúc

Một mẫu dễ đọc:

```text
<operation>_<condition>_<expectedOutcome>
```

Ví dụ:

| Operation | Test method | Ý nghĩa |
| --- | --- | --- |
| GET order | `getOrder_whenExists_returns200` | Đơn hàng tồn tại |
| GET order | `getOrder_whenMissing_returns404` | Không tìm thấy |
| POST order | `createOrder_withValidRequest_returns201` | Tạo đơn thành công |
| POST order | `createOrder_whenInvalid_returns400` | Dữ liệu không hợp lệ |
| DELETE order | `deleteOrder_whenExists_returns204` | Xóa thành công, không body |

Tên nên nói rõ điều kiện và kết quả được kiểm tra. Tránh tên chung như `testGet()`, `testSuccess()`, `testError()` hoặc tên quá dài lặp cả nội dung nghiệp vụ.

Không nhất thiết phải nhét toàn bộ endpoint vào method name. Class hoặc nested class đã thể hiện resource thì method có thể ngắn hơn.

### 3.1. Dùng @DisplayName để báo cáo dễ đọc

JUnit Jupiter cho phép đặt display name riêng:

```java
@Test
@DisplayName("GET order: đơn hàng tồn tại trả 200")
void getOrder_whenExists_returns200() throws Exception {
    // Arrange fixture, perform request, assert và document(...)
}
```

Display name giúp người đọc báo cáo hiểu scenario mà không phải giải mã naming convention. Nó không thay thế method name; method name vẫn hữu ích cho stack trace, tìm kiếm trong repository và quy ước nhóm.

Không dùng display name làm dữ liệu sinh identifier bằng cách đọc reflection nếu không có lý do mạnh. Display name có thể chứa dấu, khoảng trắng hoặc nội dung thay đổi vì mục tiêu trình bày; snippet identifier nên là chuỗi ổn định, an toàn với path và được kiểm soát tại source.

### 3.2. Dùng @Nested để gom theo resource

```java
@Nested
@DisplayName("Orders API")
class OrdersApi {

    @Nested
    @DisplayName("GET /api/orders/{id}")
    class GetOrder {

        @Test
        @DisplayName("Đơn hàng tồn tại trả 200")
        void whenExists_returns200() throws Exception {
            // ...
        }

        @Test
        @DisplayName("Đơn hàng không tồn tại trả 404")
        void whenMissing_returns404() throws Exception {
            // ...
        }
    }
}
```

Cấu trúc nested giúp test report có phân cấp resource/operation/scenario. Method con không cần lặp lại toàn bộ tên endpoint nếu tên class cha đã cung cấp ngữ cảnh.

Dù tổ chức class thế nào, snippet identifier vẫn cần được truyền rõ vào `document(...)`.

## 4. Quy ước đặt REST Docs identifier

Một format dễ mở rộng:

```text
<resource>-<operation>-<scenario>
```

Ví dụ:

```text
orders-get-success
orders-get-not-found
orders-create-success
orders-create-validation-error
orders-cancel-no-content
accounts-get-success
accounts-update-conflict
```

Nếu cần phân biệt version API hoặc representation, thêm segment có quy ước:

```text
v1-orders-get-success
v2-orders-get-success
orders-get-success-json
orders-get-success-xml
```

Chỉ thêm segment khi nó giải quyết một khác biệt thực sự. Tên quá dài, lặp path và mọi tham số request làm identifier khó bảo trì.

Một identifier tốt có các đặc điểm:

- Viết thường, dùng dấu gạch ngang và ký tự path an toàn.
- Ổn định giữa các lần chạy, không chứa timestamp hoặc random UUID.
- Mô tả resource, operation và scenario/outcome đủ phân biệt.
- Không trùng với test khác nếu output khác nhau.
- Được đặt ngay cạnh lời gọi `document(...)` để reviewer dễ kiểm tra.
- Được dùng nhất quán trong file Asciidoctor include.

### 4.1. Không dùng một identifier cho nhiều nội dung khác nhau

Sai:

```java
@Test
void getOrderSuccess() throws Exception {
    // ...
    mockMvc.perform(get("/api/orders/42"))
            .andDo(document("orders-get"));
}

@Test
void getOrderNotFound() throws Exception {
    // ...
    mockMvc.perform(get("/api/orders/404"))
            .andDo(document("orders-get"));
}
```

Hai test ghi vào cùng một thư mục `orders-get`. Nội dung snippet có thể bị ghi đè hoặc kết quả phụ thuộc thứ tự chạy. Điều này đặc biệt khó phát hiện khi suite chạy song song hoặc build giữ lại output cũ.

Đúng:

```java
.andDo(document("orders-get-success"))
```

```java
.andDo(document("orders-get-not-found"))
```

Mỗi kịch bản có output riêng, và Asciidoctor có thể include chính xác scenario tương ứng.

### 4.2. Tránh identifier được tạo từ giá trị ngẫu nhiên

Không nên:

```java
.andDo(document("orders-" + UUID.randomUUID()))
```

Tên thư mục sẽ thay đổi ở mỗi lần chạy, làm diff khó review và khiến tài liệu include không ổn định. Chỉ dùng tham số có tập giá trị được kiểm soát nếu thực sự cần tách output. Với scenario đại diện, tốt hơn là dùng identifier cố định.

## 5. Liên kết test method với snippet identifier

Một test tài liệu hóa đầy đủ có thể nhìn thấy cả ba thành phần:

```java
@Test
@DisplayName("GET order: đơn hàng tồn tại trả 200")
void getOrder_whenExists_returns200() throws Exception {
    given(orderService.findById("42"))
            .willReturn(new OrderResponse("ORD-42", "CONFIRMED"));

    mockMvc.perform(get("/api/orders/{id}", "42")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value("ORD-42"))
            .andDo(document("orders-get-success",
                    responseFields(
                            fieldWithPath("orderId")
                                    .description("Mã đơn hàng"),
                            fieldWithPath("status")
                                    .description("Trạng thái đơn hàng")
                    )));
}
```

Tên method mô tả điều kiện và status; display name thân thiện với báo cáo; snippet identifier được dùng làm đường dẫn output. Người review có thể tìm method theo identifier hoặc tìm identifier ngay trong lệnh `document(...)`.

Nếu một test có nhiều lần gọi `document(...)` cho nhiều HTTP exchange, hãy đặt identifier riêng và đặt tên biến/đoạn code thể hiện operation tương ứng. Tốt nhất tách thành test riêng nếu các exchange là các outcome độc lập cần tài liệu hóa riêng.

## 6. Tổ chức theo resource và operation trong JUnit

Với API nhiều resource, có thể dùng một class cho mỗi resource hoặc nested classes:

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTests {

    @Nested
    class GetOrder {

        @Test
        void whenExists_returns200() throws Exception {
            // document("orders-get-success")
        }

        @Test
        void whenMissing_returns404() throws Exception {
            // document("orders-get-not-found")
        }
    }

    @Nested
    class CreateOrder {

        @Test
        void withValidRequest_returns201() throws Exception {
            // document("orders-create-success")
        }

        @Test
        void withInvalidRequest_returns400() throws Exception {
            // document("orders-create-validation-error")
        }
    }
}
```

Tên class, nested class và method tạo ra một cây điều hướng cho test suite. Identifier snippet theo quy ước resource-operation-outcome tạo ra cây output tương ứng:

```text
OrderDocumentationTests
├── GetOrder
│   ├── whenExists_returns200
│   └── whenMissing_returns404
└── CreateOrder
    ├── withValidRequest_returns201
    └── withInvalidRequest_returns400

generated-snippets/
├── orders-get-success/
├── orders-get-not-found/
├── orders-create-success/
└── orders-create-validation-error/
```

Không bắt buộc cấu trúc thư mục test và snippet phải giống nhau từng chữ. Điều cần giữ là quan hệ rõ ràng, dễ truy tìm và không có identifier trùng.

## 7. Parameterized tests và tên snippet

Parameterized test có nhiều invocation của một method. Nếu mỗi invocation đều gọi `document(...)` với cùng identifier, chúng sẽ ghi vào cùng thư mục snippet.

Ví dụ có nguy cơ ghi đè:

```java
@ParameterizedTest
@ValueSource(strings = {"42", "43"})
void getOrder(String id) throws Exception {
    mockMvc.perform(get("/api/orders/{id}", id))
            .andExpect(status().isOk())
            .andDo(document("orders-get-success"));
}
```

Cần quyết định mục đích test:

**Trường hợp A — chỉ cần một snippet đại diện:** giữ parameterized test để kiểm tra nhiều ID nhưng không sinh snippet từ mọi invocation. Tạo một test documentation riêng với fixture ổn định và identifier cố định.

**Trường hợp B — từng invocation là một kịch bản tài liệu riêng:** cung cấp scenario key tĩnh, không dùng giá trị tùy ý làm tên directory.

```java
@ParameterizedTest
@CsvSource({
    "42, ORD-42, order-42",
    "43, ORD-43, order-43"
})
void getOrder(String id, String expectedId, String scenario)
        throws Exception {

    mockMvc.perform(get("/api/orders/{id}", id))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orderId").value(expectedId))
            .andDo(document("orders-get-" + scenario));
}
```

Các scenario key ở đây do test author kiểm soát và mỗi key duy nhất. Nếu dữ liệu input có dấu, slash, khoảng trắng hoặc giá trị không ổn định, không ghép trực tiếp vào identifier.

## 8. Dynamic tests và tên ổn định

Dynamic tests tạo test node trong runtime. Có thể đặt display name dễ đọc và dùng scenario key ổn định:

```java
@TestFactory
Stream<DynamicTest> orderScenarios() {
    return Stream.of(
            new OrderScenario(
                    "existing-order", "42", 200),
            new OrderScenario(
                    "missing-order", "404", 404))
        .map(scenario -> dynamicTest(
                "GET order - " + scenario.name(),
                () -> {
                    // Arrange, request, assertions
                    // document("orders-get-" + scenario.name())
                }));
}

record OrderScenario(String name, String id, int status) {}
```

Display name giúp báo cáo; scenario name được dùng làm suffix identifier. Vì dynamic tests không tự động có cùng lifecycle callback riêng biệt như test method thông thường, nếu mỗi node cần documentation context độc lập, phải tổ chức lifecycle trong executable hoặc ưu tiên parameterized test với extension Jupiter.

Không xây tên bằng nội dung exception hoặc response động. Những chuỗi đó thay đổi theo môi trường và làm output khó truy tìm.

## 9. Đồng bộ identifier với Asciidoctor

Sau khi biết identifier, include snippet đúng đường dẫn:

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

Nếu test đổi identifier từ `orders-get-success` sang `orders-read-success` nhưng Asciidoctor vẫn include đường dẫn cũ, bước biên soạn tài liệu sẽ báo thiếu snippet. Khi đổi identifier, cập nhật tham chiếu và kiểm tra tất cả include liên quan trong chính tài liệu được giao.

Nên giữ quy tắc:

- Identifier xuất hiện trong đúng một nơi khai báo `document(...)` cho một scenario.
- Asciidoctor include tham chiếu cùng identifier.
- Phần heading tài liệu diễn đạt outcome bằng ngôn ngữ người dùng API.
- CI chạy test sinh snippet trước task Asciidoctor.
- Snippet không được chỉnh tay để “khớp” include.

## 10. Truy tìm ngược từ file snippet về test

Khi reviewer nhìn thấy file:

```text
build/generated-snippets/orders-create-validation-error/http-response.adoc
```

Có thể lần theo quy trình:

1. Tìm chuỗi `orders-create-validation-error` trong source bằng IDE hoặc code search.
2. Xác định class và method chứa `document("orders-create-validation-error")`.
3. Đọc phần arrange/fixture để biết request nào tạo ra response.
4. Đọc assertion để xác minh status/body/header.
5. Tìm include trong Asciidoctor để biết snippet được trình bày ở section nào.
6. So sánh output snippet với thay đổi code và contract API trong pull request.

Điều này hữu ích khi CI phát hiện snippet diff: người review biết test nào tạo ra output, input nào được gửi và lý do tài liệu thay đổi.

Có thể tìm trong repository bằng công cụ tìm kiếm source:

```text
rg -n 'document\("orders-create-validation-error"\)' src/test
rg -n 'orders-create-validation-error' src/docs
```

Đường dẫn cụ thể phụ thuộc cấu trúc module. Lệnh đầu tìm nơi khai báo identifier; lệnh sau tìm nơi include hoặc tham chiếu trong tài liệu.

## 11. Quy ước đặt tên ở quy mô nhóm

Một convention có thể ghi trong test support/documentation guide của dự án:

| Thành phần | Quy ước | Ví dụ |
| --- | --- | --- |
| Test class | Resource + DocumentationTests | `OrderDocumentationTests` |
| Nested class | HTTP operation | `GetOrder` |
| Test method | condition + expected outcome | `whenMissing_returns404` |
| Display name | HTTP verb/resource + scenario + status | `GET order - missing - 404` |
| Snippet identifier | resource-operation-outcome | `orders-get-not-found` |
| Asciidoctor heading | Câu mô tả cho client | `Không tìm thấy đơn hàng` |

Các nhóm có thể chọn quy ước khác, miễn áp dụng thống nhất. Tránh đặt một bộ quy tắc quá phức tạp buộc developer phải đoán nhiều segment. Với resource lồng hoặc operation dài, dùng tên ngắn nhưng vẫn phân biệt được.

### 11.1. Khi nào nên đổi tên?

Đổi tên method khi nó không còn mô tả scenario sau khi contract thay đổi. Đổi snippet identifier khi resource, operation hoặc outcome được phân loại lại, hoặc tên cũ gây hiểu nhầm. Đổi heading tài liệu khi nội dung người đọc nhìn thấy không còn chính xác.

Không đổi identifier chỉ để đồng bộ từng ký tự với method name nếu không có lợi ích. Identifier là API nội bộ giữa test và tài liệu: mọi include tham chiếu phải được cập nhật cùng lúc.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm được test tạo snippet | Identifier chung chung như `get-1` | Tìm theo identifier; đổi thành resource-operation-outcome |
| Hai test ghi cùng thư mục | Dùng một document identifier cho output khác nhau | Tách identifier theo scenario |
| JUnit report dễ đọc nhưng snippet khó hiểu | Chỉ đặt `@DisplayName`, identifier vẫn chung chung | Đặt tên `document(...)` riêng |
| Nghĩ @DisplayName tự tạo snippet name | Nhầm hai hệ định danh | Truyền identifier rõ ràng cho document |
| Parameterized invocations ghi đè output | Cùng identifier trong mọi invocation | Một snippet đại diện hoặc scenario key duy nhất |
| Dynamic test có tên thay đổi mỗi lần | Dùng dữ liệu runtime/random làm display/identifier | Dùng scenario key ổn định |
| Asciidoctor báo thiếu snippet | Đổi identifier nhưng chưa cập nhật include | Đồng bộ test identifier và include path |
| Test method quá dài | Nhét cả path và toàn bộ payload vào tên | Dùng class/nested context và tên condition/outcome |
| Snippet diff khó review | Identifier/fixture chứa timestamp hoặc random data | Chuẩn hóa naming và fixture |
| Nhiều operation cùng resource khó phân biệt | Chỉ dùng tên resource | Thêm operation và outcome segment |

## 13. Checklist trước khi hoàn tất test tài liệu

- [ ] Test class/nested class cho biết resource hoặc operation.
- [ ] Test method diễn đạt condition và outcome.
- [ ] Display name dễ đọc trong IDE/CI.
- [ ] REST Docs identifier được truyền tường minh.
- [ ] Identifier phản ánh resource, operation và scenario.
- [ ] Không có hai test khác nội dung ghi chung identifier.
- [ ] Parameterized/dynamic tests dùng scenario key ổn định.
- [ ] Identifier không chứa timestamp, random UUID hoặc dữ liệu tự do.
- [ ] Asciidoctor include đúng identifier đang được khai báo.
- [ ] HTTP request và assertion đủ để hiểu lý do snippet được sinh.
- [ ] CI sinh snippets trước khi biên soạn tài liệu.
- [ ] Khi đổi identifier, test và tài liệu được cập nhật cùng nhau.

## 14. Bài thực hành

Dùng các operation của Order API:

1. Tạo nested test class `OrdersApi` và `GetOrder`.
2. Viết hai method `whenExists_returns200` và `whenMissing_returns404`; thêm `@DisplayName` dễ đọc.
3. Gắn snippet identifier `orders-get-success` và `orders-get-not-found` tương ứng.
4. Cố ý cho hai test dùng chung `orders-get`; quan sát nguy cơ ghi đè rồi sửa thành identifier riêng.
5. Viết parameterized test cho ID 42 và 43. Chọn một snippet đại diện hoặc tạo scenario key cố định.
6. Tạo dynamic tests với display name dễ đọc và identifier không phụ thuộc dữ liệu ngẫu nhiên.
7. Include hai snippet GET vào Asciidoctor và xác nhận mỗi heading trỏ đúng outcome.
8. Tìm identifier trong source và docs để lần ngược từ generated snippet về test method.
9. Đổi tên một identifier rồi kiểm tra build phát hiện include cũ; cập nhật toàn bộ tham chiếu.
10. Xem CI test report và generated snippet diff, đánh giá liệu người review có tìm được source của thay đổi hay không.

**Tiêu chí hoàn thành:** bạn phân biệt test method name, JUnit display name và REST Docs identifier; có convention ngắn gọn cho resource/operation/scenario; tránh snippet collision; tổ chức parameterized/dynamic scenarios ổn định; và lần ngược được từ generated snippet đến test và section Asciidoctor.

## Tài liệu tham khảo

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/index.html): sử dụng `document(...)` và sinh các snippet theo identifier.
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started/index.html): cấu hình output directory và tích hợp với test framework.
- [JUnit 5 User Guide — Display Names](https://junit.org/junit5/docs/current/user-guide/#writing-tests-display-names): cách đặt tên hiển thị cho test.
- [JUnit 5 User Guide — Nested Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-nested): tổ chức test theo nhóm/nested class.
- [JUnit 5 User Guide — Parameterized Tests](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests): nhiều invocation với dữ liệu tham số.
