# Tránh ghi đè snippet giữa các test

## 1. Vì sao snippet có thể bị ghi đè?

Spring REST Docs ghi các snippet của một lần document vào thư mục được xác định bởi **output directory** kết hợp với **document identifier**. Nếu hai test dùng cùng output root và cùng identifier, chúng cùng ghi vào một vị trí. Các tệp có tên giống nhau như http-request.adoc, http-response.adoc hoặc request-fields.adoc có thể bị ghi đè bởi lần chạy sau.

Ví dụ hai test:

~~~java
@Test
void getOrderAsCustomer() throws Exception {
    mockMvc.perform(get("/orders/42"))
        .andDo(document("orders/get"));
}

@Test
void getOrderAsAdmin() throws Exception {
    mockMvc.perform(get("/admin/orders/42"))
        .andDo(document("orders/get"));
}
~~~

Cả hai cùng ghi vào:

~~~text
build/generated-snippets/orders/get/
~~~

Sau khi cả hai test chạy, thư mục chỉ còn một bộ snippet cho identifier đó. Nội dung cuối cùng phụ thuộc thứ tự ghi; tài liệu có thể mô tả nhầm request của customer thành request của admin hoặc ngược lại.

Trong module **SPRING_REST_DOCS**, test HTTP bằng MockMvc, WebTestClient hoặc REST Assured là nguồn tạo snippet để biên soạn Asciidoctor/Markdown và đưa vào build/CI. Để tài liệu đáng tin cậy, mỗi thao tác được document phải có identifier ổn định, duy nhất trong phạm vi output root mà nó dùng.

## 2. Hiểu phạm vi duy nhất của document identifier

Một đường dẫn snippet gồm hai phần:

~~~text
<output-directory>/<document-identifier>/<snippet-file>
~~~

Ví dụ:

~~~text
build/generated-snippets/
└── orders/
    └── get-customer/
        ├── http-request.adoc
        └── http-response.adoc
~~~

Để tránh ghi đè, cần bảo đảm cặp **output directory + document identifier** không trùng giữa các test tạo nội dung khác nhau.

| Cấu hình | Khả năng xung đột |
| --- | --- |
| Cùng output root, cùng identifier | Có; hai test ghi cùng thư mục |
| Cùng output root, identifier khác nhau | Không ghi đè trực tiếp |
| Output root khác nhau, identifier giống nhau | Không ghi đè nếu root thực sự khác |
| Cùng identifier, test chạy song song | Rủi ro cao; có thể ghi đồng thời vào cùng tệp |

Không chỉ tên method cần duy nhất. Một class khác có thể có method cùng tên; một test parameterized có thể chạy nhiều invocation với dữ liệu khác nhau; một test workflow có thể gọi document nhiều lần. Hãy chọn identifier dựa trên đơn vị tài liệu cần phân biệt.

## 3. Tách identifier theo class và method

Spring REST Docs hỗ trợ placeholder trong document identifier:

| Placeholder | Ý nghĩa |
| --- | --- |
| {class-name} | Tên test class theo kebab-case |
| {ClassName} | Tên class nguyên dạng |
| {class_name} | Tên class theo snake_case |
| {method-name} | Tên test method theo kebab-case |
| {methodName} | Tên method nguyên dạng |
| {method_name} | Tên method theo snake_case |
| {step} | Số thứ tự lần document trong test hiện tại |

Ví dụ:

~~~java
mockMvc.perform(get("/orders/42"))
    .andDo(document("{class-name}/{method-name}"));
~~~

Hai class có method cùng tên vẫn tạo thư mục khác nhau:

~~~text
build/generated-snippets/
├── customer-order-documentation-test/
│   └── get-order/
└── admin-order-documentation-test/
    └── get-order/
~~~

Đây là lựa chọn phù hợp khi test class đại diện cho nhóm quyền, nhóm API hoặc kịch bản nghiệp vụ khác nhau. Nếu chỉ dùng {method-name}, các class có cùng tên method sẽ va chạm.

### 3.1. Đặt tên identifier tường minh

Với test có ít thao tác, tên tường minh cũng dễ đọc:

~~~java
document("orders/customer/get-one");
document("orders/admin/get-one");
~~~

Với test suite lớn, placeholder giảm việc phải lặp tên class:

~~~java
document("{class-name}/{method-name}");
~~~

Hai cách có thể kết hợp. Điều quan trọng là tên phản ánh đúng ý nghĩa request và không trùng với test khác.

## 4. Dùng {step} khi một test tạo nhiều bộ snippet

Một test có thể thực hiện nhiều request và muốn lưu snippet cho từng request. Nếu mọi request dùng cùng identifier, lần gọi sau có thể ghi đè kết quả lần trước.

Ví dụ:

~~~java
@Test
void createThenReadOrder() throws Exception {
    mockMvc.perform(post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"product\":\"book\"}"))
        .andExpect(status().isCreated())
        .andDo(document("orders/create"));

    mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andDo(document("orders/get"));
}
~~~

Nếu cùng một handler tự động ghi snippet cho mọi request, có thể dùng:

~~~java
.alwaysDo(document("{class-name}/{method-name}/{step}"))
~~~

Khi đó các lần document trong test được phân tách theo step:

~~~text
order-documentation-test/
└── create-then-read-order/
    ├── 1/
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── 2/
        ├── http-request.adoc
        └── http-response.adoc
~~~

Không thêm {step} một cách máy móc nếu test chỉ tạo một request. Dùng class/method để tạo namespace; dùng step khi có nhiều request có ý nghĩa tài liệu trong cùng test.

## 5. Test parameterized và dữ liệu đầu vào khác nhau

JUnit parameterized test có thể chạy cùng một method nhiều lần với dữ liệu khác nhau:

~~~java
@ParameterizedTest
@ValueSource(strings = {"basic", "pro"})
void getOrdersByPlan(String plan) throws Exception {
    mockMvc.perform(get("/orders").param("plan", plan))
        .andExpect(status().isOk())
        .andDo(document("orders/by-plan"));
}
~~~

Các invocation dùng chung method name và identifier cố định orders/by-plan. Chúng ghi vào cùng thư mục; invocation sau có thể thay snippet của invocation trước. Kết quả cuối không thể hiện đầy đủ cả hai trường hợp.

Có ba hướng giải quyết:

1. **Tách test method** nếu các trường hợp có ý nghĩa tài liệu khác nhau và cần include độc lập.
2. **Tách identifier theo scenario** bằng một tên cố định có ý nghĩa như orders/by-plan-basic và orders/by-plan-pro.
3. **Dùng cơ chế phân biệt invocation** của test framework để tạo identifier duy nhất, nếu framework cung cấp giá trị ổn định và có thể kiểm soát.

Không nên lấy dữ liệu ngẫu nhiên như UUID hoặc timestamp làm identifier. Tên thư mục sẽ thay đổi ở mỗi lần chạy, khiến Asciidoctor khó include và build không tái lập. Nếu dữ liệu đầu vào là một tập hữu hạn, tên scenario ổn định dễ quản lý hơn.

Ví dụ tách scenario:

~~~java
@Test
void getBasicPlanOrders() throws Exception {
    documentOrdersForPlan("basic", "orders/by-plan-basic");
}

@Test
void getProPlanOrders() throws Exception {
    documentOrdersForPlan("pro", "orders/by-plan-pro");
}
~~~

## 6. Tránh xung đột khi test chạy song song

Tách identifier theo class/method là bước đầu. Nếu hai JVM, hai Gradle worker hoặc hai Maven module cùng ghi vào **một output directory vật lý** và cùng identifier, chúng vẫn có thể đụng nhau.

Ví dụ:

~~~text
Worker A ── document("orders/get") ──┐
                                    ├── build/generated-snippets/orders/get/
Worker B ── document("orders/get") ──┘
~~~

Các thao tác ghi file có thể xen kẽ. Ngay cả khi hai test có cùng nội dung, việc ghi đồng thời cũng có thể tạo kết quả không xác định tùy cách file được tạo và thay thế.

Các cách giảm rủi ro:

- Dùng identifier có class và method để tách test độc lập.
- Nếu cùng một test suite được chạy ở nhiều process hoặc module với cùng identifier, cấp output root riêng theo task/module/process rồi hợp nhất output sau khi test hoàn tất.
- Hoặc tuần tự hóa nhóm test cùng ghi một output root nếu không thể tách đường dẫn.
- Không để nhiều CI job dùng chung workspace/output directory mà không có cơ chế cô lập.

Ví dụ hai task Gradle dùng output root riêng:

~~~groovy
tasks.register('testAdmin', Test) {
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    systemProperty 'restdocs.outputDir', layout.buildDirectory.dir('snippets/admin').get().asFile
}

tasks.register('testCustomer', Test) {
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    systemProperty 'restdocs.outputDir', layout.buildDirectory.dir('snippets/customer').get().asFile
}
~~~

Ví dụ chỉ minh họa ý tưởng cô lập output. Test harness phải đọc system property restdocs.outputDir và chuyển nó thành output directory của REST Docs; không phải mọi cấu hình Spring Boot annotation tự động sử dụng property tùy ý này. Nếu dùng @AutoConfigureRestDocs(outputDir = "...") với đường dẫn cố định, cần điều chỉnh test configuration để mỗi task thực sự nhận root riêng.

Với Maven, có thể cấu hình Surefire system property theo profile/module và truyền cùng giá trị vào plugin Asciidoctor. Tránh cho các module ghi chung một thư mục nếu chúng có identifier trùng nhau.

## 7. Dùng alwaysDo(...) có chọn lọc

alwaysDo(document(...)) tiện lợi vì tự động ghi snippet cho mọi request đi qua một MockMvc instance:

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(documentationConfiguration(documentation))
    .alwaysDo(document("{class-name}/{method-name}/{step}"))
    .build();
~~~

Nhưng nếu một test gửi cả request phụ trợ như đăng nhập, khởi tạo dữ liệu hoặc gọi endpoint nội bộ, tất cả đều có thể sinh snippet. Điều này làm output phình to và có thể gây ghi đè nếu identifier không đủ phân biệt.

Chọn một trong các cách:

- Dùng alwaysDo khi mọi request trong test đều là một phần của tài liệu.
- Gắn andDo(document(...)) tại từng request cần công bố.
- Tách setup fixture khỏi request được document.
- Dùng test riêng cho mỗi API operation nếu cần snippet độc lập và tên rõ ràng.

Không ghi snippet cho request không thuộc hợp đồng API chỉ vì nó đi qua cùng MockMvc instance.

## 8. Tổ chức Asciidoctor include theo identifier

Khi identifier là {class-name}/{method-name}, Asciidoctor cần include đúng đường dẫn sau khi placeholder được REST Docs phân giải. Ví dụ:

~~~text
build/generated-snippets/
└── customer-order-documentation-test/
    └── get-order/
        ├── http-request.adoc
        └── http-response.adoc
~~~

Trang AsciiDoc:

~~~adoc
== Lấy đơn hàng của khách hàng

=== HTTP request
include::{snippets}/customer-order-documentation-test/get-order/http-request.adoc[]

=== HTTP response
include::{snippets}/customer-order-documentation-test/get-order/http-response.adoc[]
~~~

Nếu đổi tên class hoặc method, đường dẫn sinh ra cũng đổi. Cập nhật include cùng thay đổi đó. Để giảm phụ thuộc vào tên test Java, có thể dùng identifier tường minh ổn định cho các snippet được include ở nhiều trang.

Một chiến lược thực tế:

| Loại test | Identifier | Cách include |
| --- | --- | --- |
| Snippet nội bộ, nhiều test class | {class-name}/{method-name} | Dùng đường dẫn class/method |
| Snippet công bố trong tài liệu dài hạn | orders/get-customer | Include bằng tên nghiệp vụ ổn định |
| Workflow nhiều request | {class-name}/{method-name}/{step} hoặc tên scenario/step | Include từng bước theo thứ tự |

Tên identifier tường minh giúp tài liệu ít đổi khi refactor tên test; placeholder giúp giảm collision và tự động hóa. Chọn theo mức độ ổn định cần thiết của tài liệu.

## 9. Dọn snippet cũ sau khi đổi identifier

Parameterized identifier không tự xóa thư mục cũ. Ví dụ đổi:

~~~java
document("orders/get");
~~~

thành:

~~~java
document("{class-name}/{method-name}");
~~~

thì thư mục orders/get/ từ build trước có thể còn lại. Nếu Asciidoctor vẫn include đường dẫn cũ, tài liệu có thể tiếp tục hiển thị snippet lỗi thời.

Với Gradle:

~~~bash
./gradlew clean test asciidoctor
~~~

Với Maven:

~~~bash
mvn clean verify
~~~

Clean build xóa output cũ trước khi test tạo snippet mới. Trong pipeline incremental, hãy bảo đảm output directory được quản lý đúng như output của test task/plugin và không dùng chung với job khác.

## 10. Checklist rà soát trước khi merge

| Câu hỏi | Kết quả mong đợi |
| --- | --- |
| Hai test khác nhau có dùng cùng identifier không? | Không, trừ khi chủ đích tạo chung một bộ snippet |
| Identifier có class/method khi cần không? | Có |
| Một test có nhiều request cần tách không? | Có {step} hoặc tên scenario riêng |
| Parameterized invocation có dùng chung identifier không? | Đã tách theo scenario/invocation hoặc gom có chủ đích |
| Test chạy song song có dùng chung output root và identifier không? | Đã cô lập root hoặc tuần tự hóa |
| alwaysDo có ghi cả request phụ không? | Đã giới hạn đúng request cần document |
| Asciidoctor include có trỏ đúng identifier mới không? | Có |
| Clean build có loại bỏ snippet cũ không? | Có |

## 11. Bài tập thực hành

Tạo hai test class CustomerOrderDocumentationTest và AdminOrderDocumentationTest. Cả hai đều có method getOrder, nhưng gọi endpoint và dùng quyền khác nhau.

Thực hiện:

1. Dùng identifier cố định orders/get trong cả hai test, chạy test và quan sát hiện tượng ghi chung output.
2. Đổi thành {class-name}/{method-name} và xác nhận mỗi class có thư mục riêng.
3. Tạo test workflow gửi hai request; dùng {class-name}/{method-name}/{step} để tách hai bộ snippet.
4. Tạo parameterized test cho hai plan basic và pro; chọn identifier ổn định riêng cho mỗi scenario.
5. Bật chạy song song cho nhóm test, xác định các test có cùng output root/identifier hay không; cô lập output hoặc điều chỉnh lịch chạy.
6. Cấu hình Asciidoctor include đúng request/response của customer và admin.
7. Chạy clean test asciidoctor và xác nhận không còn snippet cũ được include.

**Tiêu chí hoàn thành:** Không có hai test độc lập ghi vào cùng cặp output root/identifier; các bước trong workflow được phân tách; test chạy song song không tranh chấp file; tài liệu include đúng snippet của đúng scenario.

## Tài liệu tham khảo

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Spring REST Docs — Using Parameterized Output Directories](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Gradle User Manual — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Apache Maven Surefire Plugin — Parallel Test Execution](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-parallel-execution.html)
