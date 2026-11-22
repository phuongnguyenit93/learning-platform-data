# `fieldWithPath` và cách viết mô tả ngắn gọn trong Spring REST Docs

## 1. Vai trò của đường dẫn và mô tả trong request fields

Khi tài liệu hóa JSON request bằng **Spring REST Docs**, mỗi field cần trả lời hai câu hỏi: field nằm ở đâu trong cấu trúc JSON và nó có ý nghĩa gì đối với người gọi API.

Spring REST Docs sử dụng hai thành phần kết hợp:

- `fieldWithPath("...")` tạo một `FieldDescriptor` trỏ tới đường dẫn trong JSON.
- `requestFields(...)` nhận các descriptor và tạo snippet mô tả request payload.

Tên `requestFieldWithPath(...)` đôi khi xuất hiện trong lời nói hoặc ví dụ tự đặt, nhưng **không phải API chuẩn của Spring REST Docs**. Cách gọi chính xác là `fieldWithPath(...)` bên trong `requestFields(...)`.

Ví dụ API `POST /api/orders` nhận:

```json
{
  "customerId": 42,
  "note": "Giao sau 17 giờ",
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2
    }
  ]
}
```

Ta có thể viết:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("customerId")
        .description("Mã khách hàng"),
    fieldWithPath("note")
        .description("Ghi chú giao hàng"),
    fieldWithPath("items")
        .description("Danh sách mặt hàng"),
    fieldWithPath("items[].sku")
        .description("Mã sản phẩm"),
    fieldWithPath("items[].quantity")
        .description("Số lượng đặt")
);
```

`fieldWithPath(...)` xác định đường dẫn; `.description(...)` bổ sung ý nghĩa; `requestFields(...)` gom các descriptor thành snippet `request-fields.adoc`. Mô tả ngắn nên giúp client hiểu được nội dung và vai trò của field mà không lặp lại tên field bằng một câu mơ hồ.

Sau bài này, bạn có thể:
- Phân biệt đúng `fieldWithPath` và `requestFields`.
- Viết mô tả súc tích, cụ thể, nhất quán về kiểu nghĩa và đơn vị.
- Đặt thông tin bắt buộc, tùy chọn, nullable và ràng buộc ở đúng nơi.
- Tổ chức descriptor để tránh lặp, dễ bảo trì và dễ đọc trong snippet.
- Tạo tài liệu từ bài kiểm thử MockMvc, WebTestClient hoặc REST Assured và include vào Asciidoctor/Markdown build.

## 2. Cấu trúc một `FieldDescriptor`

Một descriptor cơ bản có dạng:

```java
fieldWithPath("fieldPath")
    .description("Mô tả ý nghĩa của field");
```

Có thể thêm kiểu, trạng thái tùy chọn, ignore hoặc metadata tùy biến:

```java
fieldWithPath("quantity")
    .type(JsonFieldType.NUMBER)
    .description("Số lượng sản phẩm")
    .optional();
```

Các thành phần:

| Thành phần | Mục đích | Lưu ý |
| --- | --- | --- |
| `fieldWithPath("...")` | Xác định đường dẫn JSON | Phải khớp JSON thực tế |
| `.type(JsonFieldType.NUMBER)` | Chỉ định kiểu hiển thị | Không thay thế validation |
| `.description("...")` | Giải thích field | Viết ngắn, rõ, có ngữ cảnh |
| `.optional()` | Cho phép field vắng mặt trong payload mẫu | Không đồng nghĩa với nullable |
| `.ignored()` | Không đưa descriptor vào bảng snippet | Không phải cơ chế bảo mật |
| `.attributes(...)` | Thêm metadata để template tùy biến đọc | Không tự hiện thành cột nếu template không dùng |

Với `requestFields(...)`, descriptor không được đánh dấu `.optional()` được xem là bắt buộc khi đối chiếu payload mẫu. Field có thể vắng mặt trong một số request thì cần `.optional()` theo đúng contract.

### 2.1. Phân biệt tên API

| Tên | Có phải API Spring REST Docs chuẩn? | Vai trò |
| --- | --- | --- |
| `fieldWithPath("items[].sku")` | Có | Tạo descriptor cho một field |
| `requestFields(...)` | Có | Tạo snippet fields cho request payload |
| `requestFieldWithPath(...)` | Không | Không phải tên phương thức chuẩn |
| `responseFields(...)` | Có | Tạo snippet fields cho response payload |

Trong phần request body, không gọi `fieldWithPath(...)` một mình để tạo snippet. Cần truyền descriptor vào `requestFields(...)` hoặc một API phù hợp khác.

## 3. Nguyên tắc viết description ngắn gọn

Một mô tả tốt nên có đủ ý nghĩa để người đọc hiểu field mà không phải đoán. Có thể áp dụng các nguyên tắc sau.

### 3.1. Bắt đầu bằng danh từ hoặc vai trò của dữ liệu

Mô tả nên cho biết field đại diện cho dữ liệu gì:

| Mô tả yếu | Mô tả tốt hơn |
| --- | --- |
| `ID` | `Mã khách hàng` |
| `Name` | `Tên người nhận hàng` |
| `Status` | `Trạng thái đơn hàng` |
| `Date` | `Thời điểm tạo đơn hàng` |
| `Data` | `Danh sách mặt hàng trong đơn` |

Tránh lặp lại nguyên tên kỹ thuật mà không giải thích. Ví dụ `customerId` không nên chỉ được mô tả là “customerId”; người đọc cần biết đó là mã khách hàng nào trong ngữ cảnh API.

### 3.2. Không viết lại tên field bằng câu khác

Description có nhiệm vụ bổ sung ý nghĩa, không phải lặp lại cú pháp:

```java
// Yếu: chỉ diễn giải lại tên
fieldWithPath("customerId")
    .description("Customer ID");

// Tốt hơn: giải thích đối tượng được tham chiếu
fieldWithPath("customerId")
    .description("Mã khách hàng tạo đơn");
```

Tên code có thể là tiếng Anh, trong khi mô tả tài liệu có thể dùng tiếng Việt theo ngôn ngữ tài liệu của dự án. Quan trọng là giữ nhất quán thuật ngữ giữa các operation.

### 3.3. Một câu, một ý chính

Mô tả cơ bản thường chỉ cần một cụm danh từ hoặc một câu ngắn:

- `Mã khách hàng tạo đơn`
- `Địa chỉ email nhận xác nhận`
- `Số lượng sản phẩm đặt mua`
- `Thời điểm giao hàng mong muốn`

Tránh gom quá nhiều quy tắc vào một câu dài. Nếu field có nhiều ràng buộc, tách phần ý nghĩa và phần quy tắc rõ ràng:

```java
fieldWithPath("quantity")
    .description("Số lượng sản phẩm; số nguyên lớn hơn 0");
```

### 3.4. Thêm đơn vị khi con số có thể gây hiểu nhầm

Các field số thường cần đơn vị hoặc quy ước:

| Field | Description gợi ý |
| --- | --- |
| `amount` | `Giá trị đơn hàng, tính bằng VND` |
| `weight` | `Khối lượng kiện hàng, tính bằng gram` |
| `duration` | `Thời gian xử lý, tính bằng giây` |
| `pageSize` | `Số bản ghi tối đa trong một trang` |
| `latitude` | `Vĩ độ theo hệ tọa độ WGS 84` |

Không tự suy diễn đơn vị từ tên field. Phải lấy theo contract thực tế của API.

### 3.5. Dùng thuật ngữ nghiệp vụ nhất quán

Nếu dự án sử dụng “đơn hàng”, không đổi luân phiên sang “đơn”, “order”, “giao dịch” khi cùng chỉ một khái niệm. Tương tự, nếu `customer` được gọi là “khách hàng”, các field `customerId`, `customerName`, `customerAddress` nên duy trì cách gọi tương thích.

## 4. Mô tả field theo cấu trúc JSON

### 4.1. Field ở cấp gốc

```json
{
  "customerId": 42,
  "note": "Giao buổi chiều"
}
```

```java
fieldWithPath("customerId")
    .description("Mã khách hàng tạo đơn");

fieldWithPath("note")
    .description("Ghi chú giao hàng");
```

Mỗi mô tả tập trung vào vai trò của field trong operation đang tài liệu hóa.

### 4.2. Object lồng nhau

```json
{
  "shippingAddress": {
    "recipient": "Nguyễn An",
    "city": "TP. Hồ Chí Minh"
  }
}
```

```java
fieldWithPath("shippingAddress")
    .description("Thông tin địa chỉ giao hàng");

fieldWithPath("shippingAddress.recipient")
    .description("Tên người nhận");

fieldWithPath("shippingAddress.city")
    .description("Thành phố giao hàng");
```

Description của object cha nên giải thích mục đích cả nhóm. Description của field con nên tập trung vào dữ liệu cụ thể. Không nên dùng cùng một câu cho tất cả các cấp.

### 4.3. Mảng và object trong mảng

```json
{
  "items": [
    { "sku": "BOOK-001", "quantity": 2 }
  ]
}
```

```java
fieldWithPath("items")
    .description("Danh sách mặt hàng");

fieldWithPath("items[].sku")
    .description("Mã sản phẩm");

fieldWithPath("items[].quantity")
    .description("Số lượng đặt");
```

`items` mô tả cả danh sách; `items[].sku` mô tả mã sản phẩm ở mỗi phần tử. Dùng `[]` để tài liệu hóa cấu trúc không phụ thuộc chỉ số cụ thể.

### 4.4. Mảng giá trị nguyên thủy

```json
{
  "tags": ["gift", "priority"]
}
```

```java
fieldWithPath("tags")
    .description("Danh sách nhãn đơn hàng");

fieldWithPath("tags[]")
    .description("Một nhãn của đơn hàng");
```

Mô tả phần tử nên giải thích ý nghĩa từng giá trị, không chỉ ghi “phần tử mảng”.

### 4.5. Khóa đặc biệt

Nếu một khóa JSON chứa dấu chấm trong chính tên khóa, dùng cú pháp ngoặc:

```json
{
  "metadata": {
    "campaign.name": "summer"
  }
}
```

```java
fieldWithPath("metadata['campaign.name']")
    .description("Tên chiến dịch tiếp thị");
```

Không dùng `metadata.campaign.name` vì cú pháp đó diễn đạt các object lồng nhau khác với JSON mẫu.

## 5. Viết description cho required, optional và nullable

`.description(...)` nên tập trung vào ý nghĩa và các quy tắc mà người dùng API cần biết. `.optional()` mới là descriptor option đánh dấu field có thể vắng trong payload mẫu.

```java
fieldWithPath("couponCode")
    .description("Mã giảm giá; có thể bỏ qua")
    .optional();

fieldWithPath("externalReference")
    .description("Mã tham chiếu ngoài; bắt buộc có khóa, cho phép null");
```

Không viết description “Tùy chọn” rồi quên `.optional()` nếu trường thực sự có thể vắng. Ngược lại, không thêm `.optional()` chỉ để làm test qua khi API yêu cầu field phải có.

| Contract | Descriptor | Description nên nói gì? |
| --- | --- | --- |
| Required, non-null | Không `.optional()` | Ý nghĩa; thêm ràng buộc quan trọng nếu cần |
| Optional, non-null | Có `.optional()` | Nêu có thể bỏ qua; nếu gửi thì kiểu/giới hạn ra sao |
| Required, nullable | Không `.optional()` | Nêu luôn phải có khóa nhưng giá trị có thể `null` |
| Optional, nullable | Có `.optional()` | Nêu có thể bỏ qua; nếu gửi cho phép `null` |

Spring REST Docs không có cờ `.nullable()` chuẩn trên `FieldDescriptor`. Nếu tài liệu cần một cột nullable riêng, có thể dùng `.attributes(...)` và tùy biến template; metadata tự thêm không xuất hiện trong bảng nếu template không đọc nó.

## 6. Ví dụ đầy đủ: dùng description ngắn gọn trong MockMvc

Giả định endpoint `POST /api/orders` tồn tại và trả `201 Created` với request hợp lệ. Dự án đã có test dependencies `spring-boot-starter-test` và `spring-restdocs-mockmvc`.

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Bộ descriptor nên tách riêng khỏi method test để dễ tái sử dụng và rà soát:

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] ORDER_REQUEST_FIELDS = {
    fieldWithPath("customerId")
        .type(JsonFieldType.NUMBER)
        .description("Mã khách hàng tạo đơn"),
    fieldWithPath("note")
        .type(JsonFieldType.STRING)
        .description("Ghi chú giao hàng")
        .optional(),
    fieldWithPath("items")
        .type(JsonFieldType.ARRAY)
        .description("Danh sách mặt hàng"),
    fieldWithPath("items[].sku")
        .type(JsonFieldType.STRING)
        .description("Mã sản phẩm"),
    fieldWithPath("items[].quantity")
        .type(JsonFieldType.NUMBER)
        .description("Số lượng đặt")
};
```

Bài kiểm thử:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderRequestFieldsDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentCreateOrderRequest() throws Exception {
        String json = """
                {
                  "customerId": 42,
                  "note": "Giao sau 17 giờ",
                  "items": [
                    { "sku": "BOOK-001", "quantity": 2 }
                  ]
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(json))
                .andExpect(status().isCreated())
                .andDo(document("orders-create",
                        requestFields(ORDER_REQUEST_FIELDS)));
    }
}
```

Khi test và bước tạo snippet thành công, Spring REST Docs sinh `request-fields.adoc` trong `build/generated-snippets/orders-create/`, bên cạnh các snippet HTTP khác tùy cấu hình.

Ví dụ include vào Asciidoctor:

```adoc
== Tạo đơn hàng

=== Request fields
include::{snippets}/orders-create/request-fields.adoc[]
```

## 7. Mẹo giữ mô tả ngắn mà vẫn đủ thông tin

### 7.1. Mô tả ý nghĩa trước, quy tắc sau

Một cấu trúc dễ đọc:

`<Ý nghĩa>; <quy tắc quan trọng nếu có>`

Ví dụ:
- `Mã sản phẩm`
- `Số lượng đặt; số nguyên lớn hơn 0`
- `Giá đơn hàng, tính bằng VND`
- `Mã giảm giá; có thể bỏ qua`

### 7.2. Đưa quy tắc dài sang tài liệu schema hoặc phần giải thích riêng

Không nên nhồi mọi điều kiện vào description:

```java
// Không nên: quá nhiều quy tắc trong một dòng
fieldWithPath("password")
    .description("Mật khẩu có từ 12 đến 64 ký tự, phải có chữ hoa, chữ thường, số, ký tự đặc biệt, không chứa email, không trùng 5 mật khẩu gần nhất...");
```

Nên viết gọn:

```java
fieldWithPath("password")
    .description("Mật khẩu đăng nhập; tuân theo chính sách mật khẩu của hệ thống");
```

Sau đó tài liệu hóa chính sách mật khẩu ở một phần riêng, nơi dễ cập nhật và tra cứu.

### 7.3. Chỉ mô tả điều client cần biết

Không cần giải thích chi tiết nội bộ như tên bảng database, tên biến Java hoặc cách hệ thống lưu cache, trừ khi thông tin đó ảnh hưởng đến cách client sử dụng API.

### 7.4. Tránh từ mơ hồ

Các từ như “data”, “info”, “value”, “status” đứng riêng thường không đủ nghĩa. Cần xác định “dữ liệu gì”, “thông tin của ai”, “giá trị theo đơn vị nào” hoặc “trạng thái của đối tượng nào”.

### 7.5. Duy trì cùng một phong cách giữa các operation

Có thể thống nhất quy ước:
- Dùng cụm danh từ, tránh câu dài không cần thiết.
- Kết thúc mô tả theo một kiểu thống nhất.
- Viết đơn vị và định dạng theo cách giống nhau.
- Mô tả object cha ở mức tổng quan, field con ở mức dữ liệu cụ thể.
- Mọi trường optional phải có `.optional()` tương ứng.

## 8. Kiểm tra chất lượng description trong review

Trước khi chấp nhận một bộ descriptor, kiểm tra:

| Câu hỏi review | Dấu hiệu đạt |
| --- | --- |
| Path có khớp payload JSON? | Test sinh snippet thành công với đúng request mẫu |
| Description có nói field là gì? | Người đọc hiểu mà không phải đoán từ tên code |
| Có đơn vị cho dữ liệu số cần thiết? | Tiền, trọng lượng, thời gian có đơn vị rõ |
| Optional có khớp contract? | `.optional()` chỉ dùng cho field thật sự có thể vắng |
| Nullable có được phân biệt? | Description hoặc schema nói rõ null nếu được chấp nhận |
| Có lặp lại mô tả object cha ở mọi field con? | Mỗi descriptor có một ý nghĩa riêng |
| Có lộ thông tin nội bộ không cần thiết? | Description chỉ chứa thông tin phù hợp với client |
| Mô tả có quá dài? | Quy tắc phức tạp được chuyển sang phần riêng |

Một snippet có thể được tạo thành công dù description rất tệ hoặc mơ hồ. Vì vậy, việc review nội dung mô tả vẫn cần được thực hiện bên cạnh việc kiểm tra kỹ thuật của Spring REST Docs.

## 9. Đưa snippet vào build và CI

Spring REST Docs thường tạo snippet AsciiDoc. Khi dùng Gradle và plugin Asciidoctor đã được cấu hình, task tài liệu cần phụ thuộc vào task test tạo snippet:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
```

Luồng build:

```text
MockMvc / WebTestClient / REST Assured tests
                  |
                  v
        requestFields descriptors
                  |
                  v
          request-fields.adoc
                  |
                  v
          Asciidoctor / HTML
                  |
                  v
            CI validation
```

Nếu nhóm đổi `fieldWithPath`, description hoặc optional state, snippet được sinh lại khi test chạy. Build CI nên kiểm tra cả test tài liệu hóa lẫn kết xuất Asciidoctor để tránh include file cũ hoặc thiếu snippet.

Nếu dự án cần Markdown, cần cấu hình template Markdown hoặc bước chuyển đổi; không mặc định `request-fields.md` được tạo sẵn.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không biên dịch `requestFieldWithPath(...)` | Dùng nhầm tên API | Dùng `fieldWithPath(...)` bên trong `requestFields(...)` |
| Snippet thiếu trường | Path sai hoặc descriptor bắt buộc vắng mặt trong request mẫu | So sánh path với JSON; dùng `.optional()` nếu contract cho phép |
| Description lặp tên field | Mô tả không giải thích ý nghĩa nghiệp vụ | Viết theo vai trò field trong operation |
| Mô tả số thiếu đơn vị | Chỉ ghi “Giá trị” hoặc “Số lượng” | Bổ sung VND, gram, giây hoặc đơn vị đúng contract |
| Description quá dài | Nhồi validation và chính sách vào một câu | Giữ ý nghĩa chính; chuyển quy tắc dài sang tài liệu riêng |
| Bảng không có cột nullable | Template mặc định không hiển thị metadata này | Viết trong description hoặc tùy biến template |
| Test chạy nhưng tài liệu lỗi thời | Asciidoctor chạy trước test hoặc không phụ thuộc output | Cấu hình task dependency và input snippet |
| Tài liệu lộ chi tiết nội bộ | Dùng mô tả từ tên class, database hoặc biến nội bộ | Viết lại theo ngôn ngữ contract mà client cần |

## 11. Bài thực hành

Dựa vào API tạo đơn hàng:

1. Viết descriptor cho `customerId`, `items`, `items[].sku`, `items[].quantity` với mô tả tối đa một câu ngắn.
2. Thêm `amount` tính bằng VND. Viết description có đơn vị, ví dụ `Tổng tiền đơn hàng, tính bằng VND`.
3. Thêm `note` là field tùy chọn. Đánh dấu `.optional()` và nêu rõ client có thể bỏ qua.
4. Tạo một descriptor `deliveryAddress.city`. Mô tả thành phố giao hàng thay vì lặp lại tên kỹ thuật.
5. Cố tình dùng `requestFieldWithPath(...)`, quan sát lỗi biên dịch, sau đó sửa thành `fieldWithPath(...)`.
6. Chạy bài kiểm thử và mở `request-fields.adoc`; review xem mô tả có dễ hiểu với người không biết cấu trúc Java DTO hay không.
7. Include snippet vào Asciidoctor và kiểm tra HTML được sinh sau khi test hoàn tất.

### Câu hỏi tự đánh giá

- `fieldWithPath(...)` và `requestFields(...)` khác vai trò như thế nào?
- Vì sao `requestFieldWithPath(...)` không phải tên API chuẩn?
- Một description tốt cần giải thích điều gì ngoài tên field?
- Khi nào cần ghi đơn vị trong description?
- `.optional()` và nullability có giống nhau không?
- Vì sao test tạo snippet thành công vẫn chưa chứng minh description đủ tốt?

**Ghi nhớ:** `fieldWithPath(...)` xác định vị trí của field trong JSON; `requestFields(...)` dùng các descriptor đó để sinh bảng request payload. Description nên ngắn gọn nhưng trả lời được field là gì, dành cho ai hoặc dùng trong ngữ cảnh nào; thêm đơn vị và quy tắc quan trọng khi cần. Mô tả đúng giúp snippet trở thành tài liệu mà người dùng API có thể thực sự sử dụng.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): cách dùng `requestFields`, `fieldWithPath` và snippet payload.
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/FieldDescriptor.html): kiểu, description, optional và metadata của descriptor.
