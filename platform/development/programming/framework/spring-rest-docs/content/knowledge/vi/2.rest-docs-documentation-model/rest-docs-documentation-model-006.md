# Phân biệt dữ liệu thực tế của response và mô tả hợp đồng

Một response JSON có thể chứa `"status": "CONFIRMED"`, nhưng chỉ từ một response đó, ta **không thể kết luận** rằng `CONFIRMED` là trạng thái duy nhất hợp lệ, mọi đơn hàng đều ở trạng thái này hay một client luôn được quyền xem đơn hàng. Response cho biết **điều đã xảy ra trong một lần gọi**; hợp đồng API cho biết **điều server cam kết với client trong những điều kiện xác định**.

Sự khác biệt này đặc biệt quan trọng trong **Spring REST Docs**. Thư viện ghi nhận request/response khi chạy bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**, đồng thời dùng các descriptor để tạo snippet cho payload, tham số, header, request và response. Sau đó Asciidoctor/Markdown kết hợp snippet với diễn giải nghiệp vụ và quy tắc hợp đồng thành tài liệu hoàn chỉnh. Nếu nhầm dữ liệu quan sát được với hợp đồng, tài liệu có thể chứa những lời hứa chưa được kiểm thử hoặc mô tả thiếu các trường hợp mà client thực sự phải xử lý.

Bài học nằm trong chương **Mô hình tài liệu** của module `SPRING_REST_DOCS`. Trọng tâm là hiểu ba lớp: **response thực tế**, **mô tả hợp đồng** và **bằng chứng kiểm thử liên kết hai lớp ấy**, từ đó viết tài liệu vừa chính xác vừa có thể kiểm chứng trong build và CI.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt một response cụ thể với hợp đồng HTTP/JSON của một operation.
2. Nhận biết những điều có thể suy ra từ status, header và payload quan sát được, cũng như những điều không thể suy ra.
3. Dùng assertion và các descriptor Spring REST Docs để kiểm tra những phần hợp đồng được khai báo.
4. Phân biệt **field vắng mặt**, **field có giá trị `null`**, **field có giá trị cố định trong ví dụ** và **field có miền giá trị hợp lệ**.
5. Viết test riêng cho response thành công và lỗi, kết hợp snippet với phần mô tả nghiệp vụ.
6. Hiểu tác động khi response thay đổi và những điểm cần rà soát trước khi xuất bản tài liệu qua CI.

## 2. Response thực tế là một quan sát; hợp đồng là tập quy tắc

Giả sử dịch vụ quản lý đơn hàng trả response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: demo-req-001

{
  "id": 91,
  "status": "CONFIRMED",
  "total": 189000,
  "currency": "VND",
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2
    }
  ]
}
```

Đây là **một quan sát cụ thể**: request nào đó đã chạy trong một môi trường, tại một thời điểm, và trả những giá trị trên. Nếu test ghi response này, Spring REST Docs có thể tạo snippet `http-response.adoc` chứa ví dụ tương ứng.

Nhưng **hợp đồng** còn có thể phải trả lời:

- Endpoint nào, method nào và điều kiện truy cập nào dẫn tới response `200`?
- `id` có định danh một đơn hàng hay một giao dịch thanh toán? Nó có thể thay đổi không?
- `status` chỉ được nhận những giá trị nào; khi nào được chuyển từ trạng thái này sang trạng thái khác?
- `total` đã bao gồm thuế, phí vận chuyển, giảm giá chưa? Đơn vị số là gì?
- `items` có được rỗng không? Mỗi `sku` có quy tắc định danh nào?
- API có khi nào trả `404`, `403` hay `409`? Body lỗi có cấu trúc nào?
- Header `X-Request-Id` có luôn xuất hiện không, client có cần gửi lại mã này khi liên hệ hỗ trợ không?
- Nếu response đổi theo thời gian, version hoặc quyền của người gọi thì phạm vi áp dụng của schema là gì?

Một lần chạy chỉ cho thấy **một điểm dữ liệu** trong số các trường hợp có thể xảy ra. Hợp đồng cần định nghĩa **tập các hành vi được chấp nhận** và cách client nên xử lý chúng.

### 2.1. Ba lớp cần liên kết nhưng không đồng nhất

| Lớp | Bản chất | Ví dụ | Trách nhiệm |
| --- | --- | --- | --- |
| **Response thực tế** | Dữ liệu server đã phát ra ở một lần thử nghiệm | `200` và JSON đơn hàng `91` | Chứng minh test đã quan sát được kết quả cụ thể |
| **Assertion và descriptor** | Điều kiện mà test kiểm tra và phần cấu trúc được mô tả | `status().isOk()`, `jsonPath("$.status").value("CONFIRMED")`, `responseFields(...)` | Làm test thất bại khi hành vi được kiểm tra lệch mong đợi |
| **Mô tả hợp đồng** | Cam kết về hành vi, ý nghĩa, giới hạn và trường hợp áp dụng | `total` được tính ra sao; khi nào trả `404` | Giúp client tích hợp đúng và giúp nhóm phát triển biết cần test thêm điều gì |

Không nên coi một response mẫu là **hợp đồng đầy đủ**. Cũng không nên coi một đoạn mô tả hợp đồng là **bằng chứng nó đã được triển khai**. Spring REST Docs kết nối chúng thông qua test, nhưng mức đảm bảo phụ thuộc vào **các assertion, descriptor và tình huống được test**.

### 2.2. HTTP status khác với field trạng thái nghiệp vụ

Trong ví dụ, có hai từ “status” với hai ý nghĩa khác nhau:

- `HTTP/1.1 200 OK` là **trạng thái HTTP** của lần gọi: server đã xử lý thành công yêu cầu theo nghĩa HTTP.
- `"status": "CONFIRMED"` là **trạng thái nghiệp vụ** của đơn hàng trong JSON.

Response `200` không có nghĩa đơn hàng đã được xác nhận; đơn hàng đang `DRAFT` cũng có thể được trả với `200` nếu API truy vấn thành công. Ngược lại, một operation xác nhận đơn hàng có thể trả `409 Conflict` khi trạng thái nghiệp vụ hiện tại không cho phép chuyển tiếp. Hợp đồng phải diễn giải cả hai lớp.

## 3. Điều gì được suy ra từ một response mẫu?

Một snapshot HTTP chứa nhiều chi tiết quan sát được nhưng không nói hết tính bắt buộc và miền giá trị.

| Chi tiết nhìn thấy trong response | Điều có thể nói chính xác | Điều chưa thể kết luận |
| --- | --- | --- |
| `200 OK` | Lần gọi này thành công | Mọi request cùng route đều được `200` |
| `Content-Type: application/json` | Response này được gửi với media type JSON | API không hỗ trợ media type/version nào khác |
| `X-Request-Id: demo-req-001` | Header có mặt trong lần gọi này | Header luôn có, cùng định dạng và không bao giờ trùng |
| `"id": 91` | Field `id` hiện diện và mang giá trị số `91` | ID luôn dương, duy nhất toàn hệ thống hoặc không đổi |
| `"status": "CONFIRMED"` | Response hiện tại chứa một chuỗi cụ thể | `CONFIRMED` là enum duy nhất hoặc trạng thái mặc định |
| `"total": 189000` | Trường `total` có giá trị số trong ví dụ | Đơn vị, thuế, cách làm tròn, giới hạn và công thức tính |
| `"items":[...]` | Lần này danh sách có một phần tử | Mảng luôn có phần tử, có thứ tự cố định hoặc không giới hạn số phần tử |
| Không thấy `discount` | Field không xuất hiện trong ví dụ | Field đó bị cấm trong mọi response hoặc sẽ không xuất hiện khi có khuyến mãi |

Lỗi thường gặp là viết “API luôn trả một phần tử trong `items`” chỉ vì ví dụ có một phần tử, hoặc đánh dấu `total` là bắt buộc chỉ vì mẫu hiện tại có nó. Tính bắt buộc phải đến từ **hợp đồng đã xác định**, sau đó được thể hiện và kiểm tra bằng test.

### 3.1. Một giá trị ví dụ không phải ràng buộc hợp đồng

Có thể công bố:

> Response ví dụ chứa `"id": 91`.

Nhưng nếu tài liệu ghi:

> Mọi lần gọi API trả `"id": 91`.

thì đó là một cam kết khác, gần như chắc chắn sai trong API quản lý nhiều đơn hàng. Tương tự, việc `total` xuất hiện dưới dạng JSON number không tự xác định số tiền tối đa, cách biểu diễn phần thập phân hoặc điều kiện tổng tiền bằng 0.

Cần phân biệt **giá trị minh họa** và **đặc điểm được bảo đảm** trong lời giải thích lẫn bài kiểm thử. Test nên cố định fixture để dễ tái tạo, còn tài liệu phải nêu rõ giá trị nào chỉ là ví dụ.

### 3.2. Schema không đủ để diễn đạt toàn bộ nghiệp vụ

Một JSON schema đơn giản có thể nói `status` là string và `total` là number. Nhưng quy tắc “chỉ đơn `CONFIRMED` mới được giao hàng”, “khách chỉ xem được đơn của mình” hoặc “`total` bằng tổng tiền các dòng hàng sau giảm giá” là những **bất biến nghiệp vụ**. Chúng cần diễn giải bằng lời, mô hình dữ liệu phù hợp và test hành vi tương ứng.

Ngay cả schema chi tiết hơn có thể diễn đạt enum, độ dài hay pattern, nhưng những ràng buộc phụ thuộc trạng thái, quyền truy cập và logic liên tài nguyên thường vẫn đòi hỏi kiểm thử và tài liệu nghiệp vụ.

## 4. Spring REST Docs ghi response và mô tả hợp đồng ở đâu?

Một HTTP test có thể gửi request bằng MockMvc, WebTestClient hoặc REST Assured rồi nhận response. Với Spring REST Docs, lời gọi `document("operation-id", ...)` gắn các snippet tạo tài liệu vào **operation vừa được thực thi**.

```text
                         Quy tắc hợp đồng đã thống nhất
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 ▼                                           ▼
             Assertions                                 Descriptors
       status/header/JSON values                  path/query/header/fields
                 │                                           │
                 └─────────────────────┬─────────────────────┘
                                       │
Request được test ──► Ứng dụng ──► Response thực tế
                                       │
                                       ▼
                            document("orders-get-200", …)
                                       │
                         ┌─────────────┴─────────────┐
                         ▼                           ▼
                 http-response.adoc          response-fields.adoc
                  (dữ liệu quan sát)          (bảng mô tả)
                         └─────────────┬─────────────┘
                                       ▼
                         Asciidoctor / Markdown
                        + giải thích nghiệp vụ
                                       │
                                       ▼
                               Trang API hoàn chỉnh
```

Các thành phần có chức năng khác nhau:

- `http-response.adoc` chứa **ví dụ response** được ghi nhận từ operation, có thể đã qua preprocessor hiển thị.
- `response-fields.adoc` được sinh từ `responseFields(...)`, mang **mô tả các field** do tác giả khai báo và được đối chiếu với payload.
- `response-headers.adoc` được sinh nếu tác giả khai báo `responseHeaders(...)`.
- Assertion như `jsonPath(...)` kiểm tra **giá trị và điều kiện** mà bộ mô tả đơn thuần không đủ bảo đảm.
- Đoạn văn nghiệp vụ trong trang Asciidoctor/Markdown giải thích **ý nghĩa, điều kiện áp dụng và hệ quả** mà snippet không thể tự suy ra.

Chẳng hạn, `fieldWithPath("total").type(JsonFieldType.NUMBER).description("Tổng tiền")` mô tả kiểu số và ý nghĩa sơ bộ của field; nó không tự xác nhận cách tính tiền hoặc mức thuế. Nếu cần chứng minh quy tắc tính, phải có assertion/test nghiệp vụ thích hợp.

## 5. Ví dụ MockMvc: dữ liệu response và mô tả trường là hai việc khác nhau

Ví dụ sử dụng Java 17+, JUnit 5, Spring MVC Test và Spring REST Docs theo phong cách API 3.x. Một controller nhỏ trả về đơn hàng `91` để tạo dữ liệu xác định; ID không tồn tại trả JSON lỗi. Việc cố định dữ liệu giúp dễ theo dõi nguồn của snippet, **không có nghĩa API thật phải dùng ID cố định**.

### 5.1. Controller dành cho bài học

```java
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    record OrderItem(String sku, int quantity) {}

    record OrderView(
        long id,
        String status,
        int total,
        String currency,
        List<OrderItem> items
    ) {}

    record ErrorView(String code, String message) {}

    @GetMapping(
        value = "/api/orders/{orderId}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<?> getOrder(@PathVariable long orderId) {
        if (orderId != 91L) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ErrorView(
                    "ORDER_NOT_FOUND",
                    "Order does not exist"
                ));
        }

        OrderView view = new OrderView(
            91L,
            "CONFIRMED",
            189000,
            "VND",
            List.of(new OrderItem("BOOK-01", 2))
        );

        return ResponseEntity.ok()
            .header("X-Request-Id", "demo-req-001")
            .body(view);
    }
}
```

Controller có hai **response thực tế khác nhau** theo fixture:

- `GET /api/orders/91` trả `200` và một `OrderView`.
- `GET /api/orders/999` trả `404` và một `ErrorView`.

Dù cùng route, hai payload có cấu trúc và ý nghĩa khác nhau. Cần tạo operation tài liệu riêng để người đọc không nhầm response thành công với response lỗi.

### 5.2. Test thành công kiểm tra giá trị và tài liệu hóa cấu trúc

Đoạn test sau yêu cầu một số giá trị cụ thể qua `andExpect(...)` rồi mô tả cấu trúc bằng `document(...)`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setup(RestDocumentationContextProvider provider) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new OrderController())
            .apply(documentationConfiguration(provider))
            .build();
    }

    @Test
    void getOrderSuccess() throws Exception {
        mockMvc.perform(
                get("/api/orders/{orderId}", 91L)
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(
                header().string("X-Request-Id", "demo-req-001")
            )
            .andExpect(jsonPath("$.id").value(91))
            .andExpect(
                jsonPath("$.status").value("CONFIRMED")
            )
            .andExpect(jsonPath("$.total").value(189000))
            .andExpect(
                jsonPath("$.items[0].sku").value("BOOK-01")
            )
            .andDo(document("orders-get-200",
                pathParameters(
                    parameterWithName("orderId")
                        .description("Mã định danh đơn hàng")
                ),
                responseHeaders(
                    headerWithName("X-Request-Id")
                        .description("Mã hỗ trợ truy vết request")
                ),
                responseFields(
                    fieldWithPath("id")
                        .type(JsonFieldType.NUMBER)
                        .description("Mã đơn hàng"),
                    fieldWithPath("status")
                        .type(JsonFieldType.STRING)
                        .description("Trạng thái nghiệp vụ"),
                    fieldWithPath("total")
                        .type(JsonFieldType.NUMBER)
                        .description("Số tiền của đơn hàng"),
                    fieldWithPath("currency")
                        .type(JsonFieldType.STRING)
                        .description("Mã tiền tệ"),
                    fieldWithPath("items")
                        .type(JsonFieldType.ARRAY)
                        .description("Danh sách dòng hàng"),
                    fieldWithPath("items[].sku")
                        .type(JsonFieldType.STRING)
                        .description("Mã sản phẩm"),
                    fieldWithPath("items[].quantity")
                        .type(JsonFieldType.NUMBER)
                        .description("Số lượng sản phẩm")
                )
            ));
    }
}
```

Các import ở đây bao phủ phần chính của test. `OrderController` từ đoạn trước cần đặt trong cùng package phù hợp với test hoặc được import từ mã ứng dụng. Dự án cần dependency Spring REST Docs, Spring MVC Test và JUnit Jupiter tương thích; đường dẫn output snippets được thiết lập trong build.

**Vì sao dùng `RestDocumentationRequestBuilders.get`?** Request builder của Spring REST Docs giữ URI template `/api/orders/{orderId}` để `pathParameters(...)` mô tả được biến `orderId`. Nếu dùng request builder không giữ template, snippet path parameter có thể không xác định được biến.

### 5.3. Test lỗi xác nhận một hợp đồng response khác

Bổ sung phương thức sau vào cùng `OrderDocumentationTest`:

```java
@Test
void getOrderNotFound() throws Exception {
    mockMvc.perform(
            get("/api/orders/{orderId}", 999L)
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isNotFound())
        .andExpect(
            jsonPath("$.code").value("ORDER_NOT_FOUND")
        )
        .andExpect(
            jsonPath("$.message").value("Order does not exist")
        )
        .andDo(document("orders-get-404",
            pathParameters(
                parameterWithName("orderId")
                    .description("Mã định danh đơn hàng")
            ),
            responseFields(
                fieldWithPath("code")
                    .type(JsonFieldType.STRING)
                    .description("Mã lỗi máy có thể xử lý"),
                fieldWithPath("message")
                    .type(JsonFieldType.STRING)
                    .description("Giải thích lỗi cho người đọc")
            )
        ));
}
```

Ở đây response `404` **có JSON body**, vì controller được thiết kế như vậy. Trong một ứng dụng khác, `404` có thể không có body hoặc dùng schema lỗi khác. Không suy ra schema lỗi từ mã HTTP; phải quan sát response và xác minh hợp đồng thực tế.

Hai operation sinh các nhóm snippet tách biệt:

```text
generated-snippets/
├── orders-get-200/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── path-parameters.adoc
│   ├── response-headers.adoc
│   └── response-fields.adoc
└── orders-get-404/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
```

Danh sách trên nêu các file liên quan trực tiếp; tùy cấu hình còn có các snippet mặc định như `curl-request.adoc`, `httpie-request.adoc`, `request-body.adoc` và `response-body.adoc`.

## 6. Assertion, descriptor và mô tả nghiệp vụ kiểm tra điều gì?

Trong test `getOrderSuccess`, ba câu lệnh sau nói về `status` nhưng ở ba mức khác nhau:

```java
.andExpect(status().isOk())

.andExpect(jsonPath("$.status").value("CONFIRMED"))

fieldWithPath("status")
    .type(JsonFieldType.STRING)
    .description("Trạng thái nghiệp vụ")
```

- `status().isOk()` xác nhận **HTTP status là 200** trong lần gọi kiểm thử.
- `jsonPath("$.status").value("CONFIRMED")` xác nhận **giá trị của field `status`** trong JSON của fixture.
- `fieldWithPath("status")...` tạo **mô tả cấu trúc của field** và tham gia kiểm tra tài liệu hóa response.

Ngay cả khi cả ba cùng pass, vẫn chưa chứng minh hợp đồng chỉ có duy nhất trạng thái `CONFIRMED` hoặc mọi đơn hàng `CONFIRMED` đều đáp ứng điều kiện xuất hóa đơn. Muốn công bố một enum hoặc quy tắc chuyển trạng thái, cần xác minh yêu cầu nghiệp vụ và viết các test phù hợp với ràng buộc đó.

### 6.1. Descriptor không tự kiểm tra công thức nghiệp vụ

Giả sử `total` phải bằng tổng giá trị dòng hàng sau khuyến mãi và cộng thuế. Descriptor:

```java
fieldWithPath("total")
    .type(JsonFieldType.NUMBER)
    .description("Tổng tiền của đơn hàng")
```

chỉ mô tả field số trong response. Nếu server sai công thức nhưng vẫn trả một số hợp lệ, mô tả có thể vẫn pass. `jsonPath("$.total").value(189000)` bảo vệ giá trị của một fixture; để bảo vệ công thức chung, cần test với các tình huống giảm giá, thuế, số lượng, làm tròn và giới hạn phù hợp.

Khi trình bày tài liệu chính thức, cần ghi rõ **đơn vị, phạm vi tiền được tính, thuế/phí, quy tắc làm tròn** theo hợp đồng. Không suy ra những điều này chỉ từ giá trị `189000` hay `VND`.

### 6.2. Mô tả nghiêm ngặt và mô tả một phần

Theo cách dùng phổ biến của Spring REST Docs:

- `responseFields(...)` áp dụng kiểm tra tài liệu hóa nghiêm ngặt đối với cấu trúc payload: một field chưa được mô tả có thể làm test thất bại; field được mô tả là bắt buộc nhưng thiếu cũng có thể gây lỗi.
- `relaxedResponseFields(...)` cho phép chỉ mô tả một phần các field quan tâm; những field còn lại không nhất thiết bị báo là chưa được tài liệu hóa.
- `optional()` dùng cho field có thể vắng mặt theo hợp đồng; đừng thêm vào chỉ để né lỗi test.
- `ignored()` được dùng khi muốn bỏ qua một thành phần trong output tài liệu theo ý đồ rõ ràng; không dùng nó để che các thay đổi hợp đồng đáng kể.

Ví dụ response đang có bảy đường dẫn field được test mô tả. Nếu controller trả thêm `discountAmount` mà `responseFields(...)` không khai báo, test tài liệu hóa nghiêm ngặt sẽ phát hiện sự thiếu mô tả đó. Điều này giúp buộc người viết quyết định: field mới có thuộc hợp đồng công khai không, kiểu và ý nghĩa là gì, cần thêm assertion hay cập nhật tài liệu nào?

**Kiểm tra nghiêm ngặt của Spring REST Docs không đồng nghĩa JSON Schema validator đầy đủ.** Nó không tự suy ra tất cả ràng buộc như enum, pattern, miền giá trị, quan hệ giữa các field hay quy tắc phân quyền.

## 7. Field vắng mặt, `null`, rỗng và tùy chọn: bốn ý nghĩa khác nhau

Các trường hợp dễ gây hiểu nhầm nhất thường không nằm ở giá trị `id` mà ở **sự có mặt** của một field.

### 7.1. Bốn response mẫu

Giả sử API có field `note`. Bốn JSON sau không tương đương:

**Trường hợp A — field không có trong payload:**

```json
{"id":91,"status":"CONFIRMED"}
```

**Trường hợp B — field có mặt với giá trị `null`:**

```json
{"id":91,"status":"CONFIRMED","note":null}
```

**Trường hợp C — field có mặt với chuỗi rỗng:**

```json
{"id":91,"status":"CONFIRMED","note":""}
```

**Trường hợp D — field có mặt với nội dung:**

```json
{"id":91,"status":"CONFIRMED","note":"Giao giờ hành chính"}
```

| Trạng thái field | Quan sát được | Câu hỏi hợp đồng cần trả lời |
| --- | --- | --- |
| Không xuất hiện | Client không nhận được key `note` | Có phải field tùy chọn theo loại đơn/phiên bản/quyền? |
| Xuất hiện và bằng `null` | Có key nhưng không có giá trị | `null` là trạng thái hợp lệ hay lỗi serialize? |
| Chuỗi rỗng | Giá trị tồn tại nhưng dài 0 ký tự | Có cho phép chuỗi rỗng hay cần bỏ field? |
| Chuỗi có nội dung | Có giá trị cụ thể | Có giới hạn độ dài, ký tự hoặc format? |

Nếu hợp đồng nói `note` có thể vắng mặt, descriptor có thể dùng `optional()`, nhưng **optional không tự giải thích ý nghĩa của `null`**. Phần diễn giải nghiệp vụ phải cho client biết liệu `null` và thiếu key có giống nghĩa nhau hay không. Nếu điều đó ảnh hưởng ứng dụng, hãy viết test cho cả hai dạng.

### 7.2. Quy tắc khai báo phải bắt nguồn từ hợp đồng

Mô tả minh họa cho một field tùy chọn:

```java
fieldWithPath("note")
    .type(JsonFieldType.STRING)
    .description(
        "Ghi chú giao hàng; có thể không được trả khi chưa có ghi chú"
    )
    .optional()
```

Cách khai báo này nói rằng field có thể **không xuất hiện** trong response mà test tài liệu hóa vẫn hợp lệ. Nó không tự cam kết field luôn khác `null` khi xuất hiện, không chứng minh chuỗi không rỗng và không đảm bảo mọi response của các role khác đều có cùng hành vi. Nếu hợp đồng có những ràng buộc đó, cần mô tả và kiểm thử tương ứng.

Tương tự, một danh sách `items: []` nghĩa là field `items` **có mặt với mảng rỗng**, khác với việc không có field `items`. Trong API có phân trang hoặc quyền che dữ liệu, sự khác biệt này có thể ảnh hưởng logic client.

## 8. Phân biệt trường hợp đơn lẻ với hợp đồng nhiều tình huống

Một API công khai hiếm khi chỉ có một response. Với cùng `GET /api/orders/{orderId}`, hợp đồng có thể phân biệt:

| Tình huống | HTTP status có thể dùng | Dạng payload | Phần cần giải thích |
| --- | --- | --- | --- |
| Đơn hàng tồn tại và người gọi có quyền | `200 OK` | JSON đơn hàng | Field, đơn vị, trạng thái và quyền truy cập |
| Không tìm thấy hoặc được che theo chính sách | `404 Not Found` | JSON lỗi hoặc không có body | Điều kiện không tìm thấy và cách xử lý |
| Không có thông tin xác thực hợp lệ | `401 Unauthorized` | Theo schema lỗi của API | Cơ chế xác thực cần có |
| Có danh tính nhưng thiếu quyền | `403 Forbidden` | Theo schema lỗi của API | Những vai trò hoặc phạm vi bị cấm |
| Xung đột trạng thái trong thao tác cập nhật | `409 Conflict` | JSON lỗi nghiệp vụ | Cần tải lại state hoặc chỉnh thao tác như thế nào |

Các dòng `401`, `403` và `409` là **tình huống cần xem xét nếu API hỗ trợ**, không phải hành vi đã được controller/test minh họa ở mục 5 chứng minh. Hợp đồng thực tế quyết định endpoint sử dụng status và payload nào.

Một test `200` không thể đại diện cho mọi response. Viết tài liệu đúng cần tạo các operation riêng cho những trường hợp có ý nghĩa với client, dùng identifier rõ ràng như `orders-get-200`, `orders-get-404`. Mỗi trường hợp có thể có bảng response field riêng.

### 8.1. Không trộn HTTP status với kết quả nghiệp vụ

Lỗi đặc biệt nguy hiểm là viết “`status=CONFIRMED` nghĩa là HTTP `200`”. Một đơn `CANCELLED` vẫn có thể truy vấn bằng `GET` và nhận `200`; ngược lại, một `POST` xác nhận đơn có thể thành công với status HTTP khác theo hợp đồng, chẳng hạn `200` hoặc `204`. Cần mô tả rõ **request nào** và **thao tác nào** thay đổi trạng thái nghiệp vụ.

### 8.2. Phạm vi test định nghĩa phạm vi bằng chứng

MockMvc `standaloneSetup` trong ví dụ chạy qua controller được dựng riêng; nó không tự kiểm chứng database, security filter hay cấu hình production. Nếu hợp đồng có quy tắc “chỉ chủ đơn được xem đơn”, cần test với cấu hình security và dữ liệu sở hữu thích hợp. WebTestClient hoặc REST Assured có thể giúp quan sát những lớp khác của ứng dụng tùy cách ràng buộc hay chạy server, nhưng cũng không tự chứng minh quy tắc nào mà test không kiểm tra.

## 9. Khi dữ liệu response thay đổi, tài liệu phải phản ứng ra sao?

Xét bốn thay đổi có khả năng xuất hiện trong một API:

| Thay đổi thực tế | Điều test mẫu có thể phát hiện | Điều cần cập nhật |
| --- | --- | --- |
| `status` đổi từ `CONFIRMED` thành `CANCELLED` với fixture `91` | Assertion `jsonPath("$.status")` thất bại | Xác minh nghiệp vụ, fixture và assertion; xem lại phần mô tả |
| Response thêm `discountAmount` | `responseFields(...)` nghiêm ngặt có thể thất bại | Quyết định field thuộc hợp đồng không, bổ sung descriptor/test |
| `total` từ JSON number chuyển sang string | Type descriptor `NUMBER` có thể không còn khớp | Thống nhất kiểu mới, kiểm tra tương thích và cập nhật client docs |
| Công thức `total` thay đổi nhưng response vẫn `189000` ở fixture | Test hiện tại có thể vẫn pass | Bổ sung test biên/tình huống đa dạng và sửa quy tắc nghiệp vụ trong tài liệu |
| Header `X-Request-Id` không còn xuất hiện | Assertion header và response header descriptor thất bại | Xác minh có thay đổi hợp đồng không và sửa mô tả |
| `items` trở thành mảng rỗng | Assertion `items[0].sku` thất bại | Xem lại đầu vào fixture, xử lý mảng rỗng theo hợp đồng |
| Có thêm response `403` cho role khác | Test `200` không tự phát hiện | Viết test role và bổ sung mục phân quyền/lỗi |

Trong thực hành, một số thay đổi tương thích với client, một số là breaking change. Đánh giá cần dựa trên **hợp đồng công khai** và cách client xử lý, không chỉ dựa vào việc test tài liệu hóa có pass hay không. Ví dụ thêm field vào JSON thường được nhiều client chấp nhận, nhưng có thể ảnh hưởng client kiểm tra schema nghiêm ngặt; thay kiểu trường hoặc xóa field bắt buộc thường có nguy cơ cao hơn.

### 9.1. Quy trình xử lý khi phát hiện chênh lệch

Khi snippet, test hoặc tài liệu có dấu hiệu không khớp:

1. **Quan sát lỗi cụ thể:** status, header, field nào đã đổi? Có phải fixture hoặc cấu hình test thay đổi?
2. **Xác minh hợp đồng mong muốn:** thay đổi là lỗi implementation hay yêu cầu API mới?
3. **Cập nhật đúng nơi:** nếu implementation sai, sửa code; nếu hợp đồng đổi có chủ đích, sửa assertion, descriptor, văn bản nghiệp vụ và ví dụ liên quan.
4. **Mở rộng kiểm thử nếu cần:** thêm case cho null, field vắng, role, trạng thái, biên số liệu hoặc lỗi.
5. **Sinh lại snippet và biên soạn:** chạy từ output sạch, xem lại trang tài liệu hoàn chỉnh.
6. **Đánh giá tương thích:** nếu client đã dựa vào hành vi cũ, cần chính sách version/migration phù hợp.

Đừng sửa mọi assertion để chạy xanh theo response mới trước khi kiểm tra đó có phải hành vi đúng. Ngược lại, cũng đừng giữ tài liệu cũ chỉ vì một phiên bản test trước đó từng pass.

## 10. Ghép snippet response và mô tả hợp đồng vào trang tài liệu

Một trang Asciidoctor cho API đơn hàng có thể kết hợp response được kiểm thử với giải thích do tác giả viết:

```asciidoc
[[orders-get]]
=== Tra cứu đơn hàng

GET /api/orders/{orderId} trả biểu diễn hiện tại
của một đơn hàng mà người gọi được phép truy cập.

==== Request mẫu

include::{snippets}/orders-get-200/http-request.adoc[]

==== Path parameter

include::{snippets}/orders-get-200/path-parameters.adoc[]

==== Response thành công (HTTP 200)

include::{snippets}/orders-get-200/http-response.adoc[]

==== Header của response

include::{snippets}/orders-get-200/response-headers.adoc[]

==== Trường JSON của response

include::{snippets}/orders-get-200/response-fields.adoc[]

status là trạng thái nghiệp vụ; tập giá trị và quy tắc
chuyển trạng thái cần được định nghĩa trong hợp đồng.

total cần được diễn giải rõ về tiền tệ, thuế, phí và làm tròn.
Giá trị trong ví dụ response không đại diện cho mọi đơn hàng.

==== Không tìm thấy (HTTP 404)

include::{snippets}/orders-get-404/http-request.adoc[]

include::{snippets}/orders-get-404/http-response.adoc[]

include::{snippets}/orders-get-404/response-fields.adoc[]
```

Trong ví dụ này, các đoạn `include::{snippets}/...[]` là cú pháp **Asciidoctor**; build cần đặt attribute `snippets` trỏ đến thư mục output. Với Markdown, phải có bước chèn/chuyển đổi snippet hoặc template phù hợp; không thể mặc định mọi Markdown renderer hiểu `include::...[]`.

Đoạn văn giải thích `status` và `total` là **chỗ đặt hợp đồng**. Khi dùng tài liệu thật, phải điền quy tắc đã được xác nhận, không để những lời hứa mơ hồ hoặc tự suy từ response mẫu.

### 10.1. Dữ liệu ví dụ có thể được chuẩn hóa, nhưng hợp đồng phải được giữ đúng

Spring REST Docs hỗ trợ preprocessors, chẳng hạn `preprocessResponse(prettyPrint())` để định dạng response, hoặc các cách thay/loại những giá trị không phù hợp với tài liệu công khai. Việc chuẩn hóa có ích khi có request ID ngẫu nhiên, timestamp, hostname môi trường test hoặc dữ liệu nhạy cảm.

Tuy nhiên, cần nhớ:

- Snippet sau tiền xử lý là **dạng hiển thị của tương tác được test**, không nhất thiết giống từng byte của response thô.
- Assertion nên kiểm tra hành vi cần bảo vệ trên response thực trong test, độc lập với việc làm đẹp output.
- Không được dùng bước tiền xử lý để che thay đổi kiểu dữ liệu, status hoặc field thuộc hợp đồng.
- Không đưa mật khẩu, token thật, cookie phiên hoặc dữ liệu cá nhân vào snippet công khai.

Nếu thay một request ID sinh ngẫu nhiên thành `demo-req-001` trong tài liệu, nên hiểu đó là **giá trị minh họa**. Hợp đồng vẫn phải mô tả định dạng/vòng đời của request ID nếu client cần dựa vào nó.

## 11. Build và CI kiểm chứng phần nào của tài liệu?

Một pipeline tài liệu điển hình:

```text
Source + hợp đồng đã thống nhất
            │
            ▼
     HTTP documentation tests
      ├── Assertions
      └── Descriptor validation
            │
        ┌───┴────┐
        │        │
      FAIL      PASS
        │        │
    Dừng build   ▼
          generated-snippets/
                 │
                 ▼
           Biên soạn trang
      Asciidoctor / Markdown
                 │
                 ▼
        Kiểm tra include, link,
       dữ liệu nhạy cảm, nội dung
                 │
                 ▼
             Công bố
```

Với Gradle, output snippet thường nằm ở `build/generated-snippets`; với Maven thường ở `target/generated-snippets`, tùy cấu hình. Bước biên soạn tài liệu cần phụ thuộc vào test tạo snippet, dùng đúng thư mục output và phát hiện lỗi include. Trên CI, nên bảo đảm các snippet được tái tạo từ source đang build, tránh dùng file cũ tồn dư khi test bị skip.

Bước này tăng độ tin cậy của **ví dụ HTTP và bảng mô tả cấu trúc**. Tuy nhiên, việc test pass và trang render được **không tự xác nhận** một quy tắc nghiệp vụ chưa được viết thành assertion hoặc chưa được chủ sở hữu hợp đồng rà soát.

### 11.1. Phân định rõ trách nhiệm khi review

| Vai trò/công việc | Câu hỏi nên kiểm tra |
| --- | --- |
| Người phát triển endpoint | Request/response, status và schema có đúng implementation dự kiến không? |
| Người viết test | Assertion bảo vệ những giá trị/ràng buộc nào, còn trường hợp nào chưa bao phủ? |
| Người viết descriptor | Field, kiểu, optional/ignored và header có mô tả đúng hợp đồng không? |
| Người hiểu nghiệp vụ | Enum, điều kiện truy cập, thuế/phí, vòng đời và mã lỗi có chính xác không? |
| Người xây dựng CI | Test có chạy trước render không, output có sạch và include có hợp lệ không? |
| Người duyệt tài liệu | Trang trình bày có dễ hiểu, không mâu thuẫn và không tiết lộ dữ liệu nhạy cảm không? |

Các vai trò có thể do cùng một người đảm nhiệm trong dự án nhỏ. Điều quan trọng là những câu hỏi cần được trả lời trước khi coi tài liệu là hợp đồng chính thức.

## 12. Những lỗi thường gặp

| Nhận định hoặc hiện tượng | Vấn đề | Cách giải quyết |
| --- | --- | --- |
| “Ví dụ có `200` nên endpoint luôn trả `200`” | Nhầm một observation với toàn bộ response space | Tài liệu hóa các điều kiện và case lỗi quan trọng |
| “`status` là string nên bất kỳ chuỗi nào cũng hợp lệ” | Kiểu dữ liệu không tương đương miền giá trị | Định nghĩa enum và test giá trị/quy tắc chuyển trạng thái |
| “Field có mặt ở test nên bắt buộc ở mọi trường hợp” | Không xét response theo role, state hoặc version | Xác minh hợp đồng, dùng `optional()` đúng lúc và test variant |
| “`null` và không có field là như nhau” | Client có thể xử lý khác nhau | Mô tả rõ nullability và sự có mặt của field |
| “`responseFields(...)` pass nên công thức tiền đúng” | Descriptor chủ yếu kiểm tra cấu trúc được tài liệu hóa | Viết test tính tiền, làm tròn và các ranh giới |
| Response mới có field lạ, test lỗi | Descriptor chưa cập nhật theo thay đổi | Xác định thay đổi hợp đồng và sửa mô tả nếu hợp lệ |
| Không có test nào thất bại khi ý nghĩa `total` đổi | Thay đổi ngữ nghĩa không làm đổi kiểu/schema | Rà soát nghiệp vụ và thêm assertion thích hợp |
| Trang chỉ nhúng `http-response.adoc` | Thiếu điều kiện áp dụng và diễn giải field | Viết thêm phần hợp đồng, trạng thái và mã lỗi |
| Snippet phản ánh build trước | Test không chạy hoặc output chưa dọn | Ràng buộc task và tái tạo output trong CI |
| Tài liệu công khai chứa trace/token nhạy cảm | Dữ liệu quan sát không được xử lý phù hợp | Dùng fixture giả, kiểm tra và chuẩn hóa snippet an toàn |

## 13. Bài thực hành: chứng minh đúng lời khẳng định về response

Giả sử nhóm muốn công bố hợp đồng cho `GET /api/orders/{orderId}`:

> Nếu đơn hàng tồn tại và người gọi có quyền, API trả `200` với các field `id`, `status`, `total`, `currency` và `items`. Nếu không tìm thấy, API trả `404` với field lỗi `code`, `message`. `status` là trạng thái nghiệp vụ; `total` là số tiền tính theo quy tắc tài chính của hệ thống.

**Bài tập thực hành:**

1. Viết hai test HTTP cho response `200` và `404`, chọn identifier khác nhau trong `document(...)`.
2. Với `200`, kiểm tra HTTP status, media type và các giá trị quan trọng; mô tả tất cả response field thuộc hợp đồng.
3. Với `404`, kiểm tra `code`/`message` đúng với lỗi thực và tạo snippet riêng.
4. Thêm trường hợp `items=[]` và xác minh client có nhận **mảng rỗng**, không phải field vắng mặt.
5. Nếu hợp đồng có field `note` tùy chọn, thiết kế hai case **có note** và **không có note**; quyết định `null` có hợp lệ hay không.
6. Thử thêm `discountAmount` vào response mà chưa cập nhật descriptor. Quan sát lỗi mô tả field ở chế độ nghiêm ngặt rồi cập nhật hợp đồng khi thay đổi là có chủ đích.
7. Thử sửa phép tính `total` nhưng vẫn giữ cùng JSON type. Chỉ ra vì sao descriptor không đủ để bảo vệ công thức và bổ sung test nghiệp vụ thích hợp.
8. Chèn snippet vào trang Asciidoctor, thêm mục ý nghĩa trạng thái, tiền tệ, lỗi và điều kiện truy cập; chạy build từ output sạch.

**Tiêu chí đạt:** mỗi lời khẳng định có thể xác định rõ thuộc **dữ liệu quan sát**, **điều kiện đã được assertion/descriptor kiểm tra** hay **quy tắc hợp đồng cần xác minh và bổ sung test**. Tài liệu không suy ra quy tắc chung từ một mẫu response đơn lẻ.

## 14. Ghi nhớ

- **Response thực tế** mô tả kết quả của một request trong tình huống kiểm thử cụ thể; **hợp đồng API** mô tả tập hành vi và dữ liệu mà client được phép dựa vào.
- `http-response.adoc` là ví dụ quan sát được; `response-fields.adoc` là bảng mô tả từ descriptor; **assertion** kiểm tra các giá trị và điều kiện mà tác giả lựa chọn.
- **Kiểu field, sự có mặt, `null`, giá trị cụ thể và ý nghĩa nghiệp vụ** là những thuộc tính khác nhau, cần được diễn giải đúng.
- Một test `200` không chứng minh các response lỗi, điều kiện phân quyền hoặc mọi trạng thái nghiệp vụ; cần những operation test phù hợp.
- Spring REST Docs cùng Asciidoctor/Markdown và CI giúp tái tạo tài liệu có cơ sở từ test, nhưng **khả năng kiểm chứng chỉ mạnh bằng phạm vi test, descriptor, assertion và sự chính xác của quy tắc nghiệp vụ được mô tả**.
