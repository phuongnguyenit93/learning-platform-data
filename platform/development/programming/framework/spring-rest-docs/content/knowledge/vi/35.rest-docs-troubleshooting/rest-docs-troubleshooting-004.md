# Operation name sai và ghi đè thư mục trong Spring REST Docs

## 1. Vì sao operation name quan trọng?

Trong Spring REST Docs, chuỗi truyền vào `document(...)` là **document identifier** của operation. Identifier quyết định thư mục con mà snippet được ghi vào bên dưới output directory.

Ví dụ:

```java
mockMvc.perform(get("/api/orders/42"))
        .andDo(document("orders/get-by-id"));
```

Với output directory `build/generated-snippets`, snippet được ghi vào:

```text
build/generated-snippets/
  orders/
    get-by-id/
      http-request.adoc
      http-response.adoc
      curl-request.adoc
```

Nếu hai operation dùng cùng identifier, chúng cùng ghi vào một thư mục và cùng tên file snippet. Request/response của operation chạy sau có thể thay thế nội dung đã được tạo trước. Tài liệu có thể hiển thị request của endpoint này nhưng response của endpoint khác, hoặc include một bộ snippet không còn khớp với operation.

Module **SPRING_REST_DOCS** tạo tài liệu REST API có thể kiểm chứng từ HTTP tests với MockMvc, WebTestClient hoặc REST Assured. Các test sinh snippet request, response, payload, parameter và header, rồi biên soạn thành Asciidoctor/Markdown trong build/CI. Bài thuộc chương **Chẩn đoán lỗi**, hướng dẫn phát hiện operation name sai, identifier trùng và hiện tượng ghi đè thư mục snippet.

Sau bài học, bạn có thể:

1. Hiểu document identifier ảnh hưởng trực tiếp đến output path.
2. Nhận diện identifier sai, thiếu, trùng hoặc không ổn định.
3. Tách snippet theo operation, test class, test method và step.
4. Kiểm tra output và Asciidoctor include khi refactor tên operation.
5. Tránh race condition khi nhiều test cùng ghi một identifier.

## 2. Document identifier không phải endpoint path

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| HTTP endpoint | GET /api/orders/42 | Route thực tế được test gọi |
| Document identifier | orders/get-by-id | Tên thư mục snippet |
| Output directory | build/generated-snippets | Root chứa các thư mục identifier |

Identifier không tự suy ra từ URL, HTTP method hoặc controller method. Người viết test truyền nó vào `document(...)`. Vì vậy, đổi endpoint path không tự đổi identifier; đổi identifier cũng không làm thay đổi URL mà test gọi.

Đường dẫn đầy đủ:

```text
<output-directory>/<document-identifier>/<snippet-file>
```

Ví dụ, `document("orders/get-by-id")` và `document("orders/create")` là hai operation độc lập dù cùng thuộc OrderController.

## 3. Dấu hiệu operation name sai

Triệu chứng thường gặp:

- Trang tài liệu lấy nhầm request hoặc response của operation khác.
- Snippet được sinh nhưng Asciidoctor include báo không tìm thấy file.
- Output có thư mục tên cũ sau khi test đã đổi tên.
- Hai test có identifier giống nhau dù URL khác nhau.
- Chạy test riêng thì đúng, chạy cả suite lại ra nội dung khác.
- Snippet thay đổi theo thứ tự chạy hoặc khi bật parallel execution.

Ví dụ hai test vô tình dùng cùng identifier:

```java
@Test
void getOrder() throws Exception {
    mockMvc.perform(get("/api/orders/42"))
            .andDo(document("order"));
}

@Test
void createOrder() throws Exception {
    mockMvc.perform(post("/api/orders"))
            .andDo(document("order"));
}
```

Cả hai ghi file http-request.adoc và http-response.adoc vào build/generated-snippets/order. Test tạo order có thể ghi đè snippet của test lấy order hoặc ngược lại.

## 4. Chẩn đoán từ output directory

Khi nghi ngờ ghi đè, kiểm tra output sau khi chạy test:

```text
build/generated-snippets/
  order/
    http-request.adoc
    http-response.adoc
```

Nếu có nhiều test nhưng chỉ có một identifier directory, xem lại các lời gọi document(...):

```java
document("order")
document("orders")
document("order-detail")
```

Tìm trong test source:

```bash
rg -n 'document\\(' src/test
```

Với PowerShell:

```powershell
Get-ChildItem -Path src/test -Recurse -File |
    Select-String -Pattern 'document\\('
```

Đối chiếu từng identifier với operation mà test thực hiện. Không kết luận chỉ dựa vào tên thư mục; mở http-request.adoc và http-response.adoc để xác nhận method, URL, status và payload đúng.

## 5. Đặt tên operation nhất quán

Một quy ước dễ đọc là nhóm theo resource rồi đặt tên theo hành động:

```text
orders/get-by-id
orders/create
orders/cancel
customers/get-by-id
customers/update-address
```

Khuyến nghị:

- Dùng tên mô tả operation, không dùng tên chung chung như test1, sample hoặc request.
- Dùng kebab-case để dễ đọc trong đường dẫn.
- Giữ identifier ổn định để Asciidoctor include không phải đổi liên tục.
- Không dùng cùng identifier cho hai operation có contract khác nhau.
- Tránh ghép dữ liệu random, timestamp hoặc ID của test run vào identifier.
- Nếu nhiều test cùng chứng minh một operation, cân nhắc một test sở hữu snippet chuẩn hoặc phân vùng theo test class/method.

Tên identifier không bắt buộc giống endpoint. Nó nên mô tả operation theo ngôn ngữ tài liệu, trong khi URL và HTTP method được thể hiện trong snippet.

## 6. Phân vùng theo test class và method

Nếu một test class chứa nhiều method document, dùng placeholder:

```java
document("{class-name}/{method-name}")
```

Ví dụ:

```text
build/generated-snippets/
  order-documentation-tests/
    get-order/
    create-order/
    cancel-order/
```

MockMvc có thể đặt identifier mặc định bằng alwaysDo(...):

```java
MockMvc mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(documentationConfiguration(restDocumentation))
        .alwaysDo(document("{class-name}/{method-name}"))
        .build();
```

Cách này hữu ích khi mọi request trong test class đều cần snippet. Nếu một test cần identifier riêng hoặc có nhiều exchange, cấu hình andDo(document(...)) tường minh để kiểm soát đường dẫn.

Các placeholder phổ biến:

| Placeholder | Kết quả |
| --- | --- |
| {class-name} | Tên class dạng kebab-case |
| {method-name} | Tên method dạng kebab-case |
| {ClassName} | Tên class giữ nguyên |
| {methodName} | Tên method giữ nguyên |
| {class_name} | Tên class dạng snake_case |
| {method_name} | Tên method dạng snake_case |
| {step} | Số thứ tự operation trong test hiện tại |

Đổi tên class hoặc method có thể làm đổi thư mục snippet. Hãy cập nhật Asciidoctor include trong cùng thay đổi.

## 7. Nhiều HTTP exchange trong một test method

Một test method có thể tạo order rồi đọc lại order. Nếu cả hai exchange cùng dùng identifier {class-name}/{method-name}, chúng có thể cùng ghi http-request.adoc và http-response.adoc.

Dùng {step} để phân biệt:

```java
@Test
void createAndReadOrder() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"productId":"P-42","quantity":1}
                            """))
            .andExpect(status().isCreated())
            .andDo(document("{class-name}/{method-name}/{step}"));

    mockMvc.perform(get("/api/orders/ORD-100"))
            .andExpect(status().isOk())
            .andDo(document("{class-name}/{method-name}/{step}"));
}
```

Output:

```text
build/generated-snippets/
  order-documentation-tests/
    create-and-read-order/
      1/
      2/
```

{step} phân biệt các lần gọi service trong test hiện tại. Trong tài liệu, ghi rõ step 1 là tạo order và step 2 là đọc order.

## 8. Kiểm tra Asciidoctor include path

Nếu identifier là orders/get-by-id, include phải tham chiếu đúng đường dẫn:

```asciidoc
== Lấy đơn hàng theo ID

include::{snippets}/orders/get-by-id/http-request.adoc[]
include::{snippets}/orders/get-by-id/http-response.adoc[]
```

Biến {snippets} phải trỏ tới output root, ví dụ build/generated-snippets. Không đưa orders/get-by-id vào biến {snippets} lần nữa nếu include đã chứa identifier, vì có thể tạo đường dẫn lặp.

Nếu đổi identifier từ order-detail sang orders/get-by-id, cập nhật lời gọi document(...), include trong Asciidoctor, script kiểm tra file snippet bắt buộc và tên artifact/link tham chiếu nếu pipeline lưu đường dẫn snippet.

Clean output trước khi build giúp phát hiện include cũ. Nếu không clean, thư mục cũ có thể vẫn tồn tại và che giấu lỗi include.

## 9. Phân biệt overwrite có chủ ý và collision

Không phải mọi lần ghi lại cùng identifier đều là lỗi. Một test có thể chạy lại để tái tạo snippet mới cho cùng operation. Điều cần tránh là nhiều operation khác nhau cùng sở hữu một identifier.

| Trường hợp | Đánh giá |
| --- | --- |
| Một test chạy lại và sinh cùng identifier | Bình thường |
| Hai test khác nhau cùng ghi một identifier | Collision, cần phân vùng |
| Cùng operation có nhiều exchange nhưng không dùng step | Có thể ghi đè, cần identifier riêng |
| Test đổi identifier nhưng output cũ chưa clean | Stale directory |
| Nhiều CI job ghi chung output directory | Race và cross-job overwrite |
| Hai test cố tình đóng góp vào cùng bộ snippet | Chỉ hợp lệ khi tổ chức tuần tự và có chủ đích |

Nếu nhiều test cần document cùng operation, hãy quyết định test nào là nguồn snippet chuẩn. Các test còn lại có thể kiểm tra behavior mà không sinh snippet, hoặc dùng identifier riêng cho từng góc kiểm thử.

## 10. Parallel execution và output isolation

Khi test chạy song song, hai operation trùng identifier có thể ghi cùng file đồng thời. Kết quả không xác định, nhất là khi request/response snippets được tạo ở các thời điểm khác nhau.

Giải pháp:

- Dùng identifier duy nhất theo class/method/step.
- Không chia sẻ output root giữa các CI job độc lập.
- Nếu nhiều test task cùng tạo snippet, phân vùng theo task hoặc tổ chức dependency tuần tự.
- Clean output một lần trước nhóm producer; không để từng task xóa thư mục chung của task khác.
- Không dùng random identifier để che collision vì đường dẫn include sẽ không ổn định.

Với REST Assured, WebTestClient và MockMvc, nguyên tắc giống nhau: identifier thuộc operation được document và phải duy nhất trong output root đang dùng.

## 11. Bài kiểm tra nhanh khi snippet bị ghi đè

1. Chạy clean để loại snippet stale.
2. Tìm mọi lời gọi document(...) trong test source.
3. Lập bảng test method → HTTP operation → identifier.
4. Kiểm tra identifier có trùng không.
5. Chạy từng test riêng và mở snippet request/response.
6. Chạy toàn bộ test suite, kể cả parallel mode nếu dự án bật.
7. Kiểm tra Asciidoctor include path và render lại tài liệu.

Ví dụ bảng kiểm:

| Test | HTTP operation | Identifier mong đợi |
| --- | --- | --- |
| getOrder | GET /api/orders/42 | orders/get-by-id |
| createOrder | POST /api/orders | orders/create |
| cancelOrder | DELETE /api/orders/42 | orders/cancel |

Nếu hai dòng cùng identifier nhưng nội dung snippet khác nhau, đó là dấu hiệu collision cần xử lý.

## 12. Bài tập thực hành

Tạo test class OrderDocumentationTests với ba method:

- getOrder
- createOrder
- cancelOrder

Thực hiện:

1. Cố ý cho cả ba test dùng document("order").
2. Chạy từng test và quan sát output bị dùng chung.
3. Đổi identifier thành orders/get-by-id, orders/create và orders/cancel.
4. Cập nhật Asciidoctor include tương ứng.
5. Thêm một test method thực hiện hai exchange và dùng {step}.
6. Chạy clean build và kiểm tra mỗi operation có request/response snippet đúng.
7. Chạy test song song và xác nhận không có identifier collision.

**Tiêu chí hoàn thành:** Mỗi operation có identifier rõ ràng và duy nhất; snippet phản ánh đúng HTTP method, URL, status và payload; Asciidoctor include đúng thư mục; clean build không còn thư mục cũ; parallel execution không làm thay đổi nội dung snippet.

## 13. Ghi nhớ

Document identifier là tên thư mục snippet do test chỉ định, không phải endpoint path. Hai operation khác nhau dùng cùng identifier sẽ ghi vào cùng các file snippet và có thể ghi đè nội dung. Dùng tên mô tả như orders/get-by-id, phân vùng theo {class-name}/{method-name} và thêm {step} khi một method document nhiều exchange. Khi đổi identifier, cập nhật Asciidoctor include và clean output cũ. Kiểm tra request/response snippet sau cả test riêng lẫn toàn suite để phát hiện collision, stale output và race condition.

### Tài liệu tham khảo

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
- [Spring REST Docs — MockMvc Integration](https://docs.spring.io/spring-restdocs/reference/getting-started/using-mock-mvc.html)
- [Spring REST Docs — REST Assured Integration](https://docs.spring.io/spring-restdocs/reference/getting-started/using-rest-assured.html)
- [Spring REST Docs — WebTestClient Integration](https://docs.spring.io/spring-restdocs/reference/getting-started/using-webtestclient.html)
