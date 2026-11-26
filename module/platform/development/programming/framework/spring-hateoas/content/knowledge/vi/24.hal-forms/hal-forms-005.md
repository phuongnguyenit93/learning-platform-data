# Template properties

Trong HAL-FORMS, một template mô tả thao tác mà client có thể thực hiện trên resource. Mỗi phần tử trong mảng `properties` mô tả một giá trị đầu vào mà client có thể cần gửi khi thực hiện thao tác đó. Các metadata như `name`, `prompt`, `required`, `type`, `value` và các ràng buộc độ dài hoặc giá trị giúp client dựng giao diện phù hợp mà không phải mã hóa cứng cấu trúc form cho từng endpoint.

Spring HATEOAS mô hình hóa thao tác bằng affordance rồi chuyển metadata thành template khi response được serialize theo media type HAL-FORMS (`application/prs.hal-forms+json`). Vì vậy, cần hiểu cả ý nghĩa của từng property trong hợp đồng và cách chúng liên hệ với kiểu request, validation và client tiêu thụ response.

## 1. Template properties là gì?

Một template HAL-FORMS thường nằm trong `_templates` của response. Template mô tả một thao tác, ví dụ cập nhật đơn hàng bằng `PUT`. Mảng `properties` bên trong template liệt kê các trường đầu vào:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/ORD-101"
    }
  },
  "_templates": {
    "default": {
      "title": "Cập nhật đơn hàng",
      "method": "PUT",
      "contentType": "application/json",
      "properties": [
        {
          "name": "note",
          "prompt": "Ghi chú giao hàng",
          "required": false,
          "type": "text",
          "maxLength": 300
        },
        {
          "name": "priority",
          "prompt": "Mức ưu tiên",
          "required": true,
          "type": "number",
          "min": 1,
          "max": 5,
          "value": 3
        }
      ]
    }
  }
}
```

Trong ví dụ, `default` là tên template, `method` là HTTP method, `contentType` là media type của request body. Hai phần tử trong `properties` mô tả `note` và `priority`. Client có thể dùng metadata để dựng textbox và numeric input, đặt nhãn hiển thị, đánh dấu trường bắt buộc và giới hạn giá trị đầu vào.

Property mô tả dữ liệu của thao tác, thường tương ứng với trường trong request body. Nó không nhất thiết là một trường được trả về trong representation hiện tại. Một response có thể chứa nhiều template cho các thao tác khác nhau, mỗi template có tập property riêng.

## 2. Các metadata thường gặp

HAL-FORMS định nghĩa các thuộc tính metadata để mô tả property. Một số trường phổ biến:

| Metadata | Ý nghĩa | Cách client có thể dùng |
| --- | --- | --- |
| `name` | Tên property trong dữ liệu gửi đi | Dùng làm key trong request payload |
| `prompt` | Nhãn hoặc lời nhắc hiển thị | Hiển thị label bên cạnh control |
| `required` | Property có bắt buộc hay không | Đánh dấu bắt buộc và kiểm tra trước khi gửi |
| `readOnly` | Property chỉ đọc | Hiển thị giá trị nhưng không cho chỉnh sửa |
| `type` | Kiểu input hoặc control gợi ý | Chọn textbox, number input, checkbox, select... |
| `value` | Giá trị được cung cấp sẵn | Điền giá trị hiện tại hoặc giá trị mặc định |
| `regex` | Biểu thức chính quy cho giá trị | Kiểm tra định dạng ở client |
| `min`, `max`, `step` | Giới hạn và bước của giá trị số/ngày tùy control | Cấu hình phạm vi và bước tăng giảm |
| `minLength`, `maxLength` | Giới hạn độ dài chuỗi | Giới hạn số ký tự nhập |
| `options` | Các lựa chọn cho property dạng chọn | Dựng select, radio hoặc lựa chọn nhiều giá trị |
| `multiple` | Property cho phép nhiều giá trị | Cho phép chọn nhiều mục nếu control hỗ trợ |
| `cols`, `rows` | Kích thước gợi ý cho vùng văn bản | Dựng textarea với kích thước phù hợp |
| `templated` | Giá trị property có dạng URI template | Cho phép client mở rộng template theo quy ước |

Không phải property nào cũng cần tất cả metadata. Ví dụ, `name` là thông tin cốt lõi để xác định trường; `prompt`, `type` hoặc `value` có thể được lược bỏ nếu không có dữ liệu tương ứng. Client cần có giá trị mặc định hợp lý khi một metadata tùy chọn không xuất hiện.

## 3. name và prompt

`name` xác định tên trường trong dữ liệu gửi đến server. Đây là tên có ý nghĩa máy đọc và cần khớp với cấu trúc request body theo hợp đồng API. `prompt` cung cấp văn bản thân thiện hơn để hiển thị cho người dùng.

Ví dụ:

```json
{
  "name": "deliveryNote",
  "prompt": "Ghi chú giao hàng"
}
```

Client có thể hiển thị nhãn “Ghi chú giao hàng” nhưng gửi key `deliveryNote` trong JSON:

```json
{
  "deliveryNote": "Gọi trước khi giao"
}
```

Không nên dùng `prompt` làm key trong payload. Nội dung prompt có thể được bản địa hóa hoặc thay đổi để cải thiện trải nghiệm người dùng; `name` cần ổn định để client gửi đúng dữ liệu.

## 4. required và readOnly

`required` cho biết property cần có giá trị khi gửi thao tác. `readOnly` cho biết client nên hiển thị giá trị nhưng không cho người dùng sửa property đó.

```json
{
  "name": "customerNumber",
  "prompt": "Mã khách hàng",
  "required": true,
  "readOnly": true,
  "type": "text",
  "value": "C-105"
}
```

Trong ví dụ, client có thể hiển thị mã khách hàng nhưng không cho thay đổi. Nếu property là bắt buộc, client cần bảo đảm payload có giá trị theo yêu cầu của template.

Metadata này hướng dẫn giao diện và việc tạo request. Server vẫn phải kiểm tra payload thực tế. Không tin rằng client sẽ tuân thủ `required` hoặc `readOnly`; một request thủ công vẫn có thể gửi thiếu trường hoặc thay đổi giá trị. Các quy tắc bảo mật và nghiệp vụ phải được thực thi ở server.

## 5. type và cách chọn control

`type` cung cấp gợi ý về kiểu control phù hợp. Ví dụ, `text` thường tương ứng với textbox, `number` với trường số, `checkbox` với lựa chọn đúng/sai, còn `date` với trường ngày.

| Type gợi ý | Control phía client |
| --- | --- |
| `text` | Text input |
| `number` | Numeric input |
| `date` | Date picker |
| `checkbox` | Checkbox |
| `textarea` | Vùng nhập nhiều dòng |
| `email` | Input email |
| `url` | Input URL |
| `password` | Input mật khẩu |
| `select` | Danh sách lựa chọn |

Danh sách type và cách render phụ thuộc HAL-FORMS specification, serializer và khả năng của client. Client nên có fallback khi gặp type không hỗ trợ, thay vì từ chối toàn bộ response. Không nên giả định `type` là tên class Java hoặc kiểu dữ liệu JSON; đây là metadata dành cho việc mô tả input.

## 6. value và giá trị được điền sẵn

`value` có thể cung cấp giá trị hiện tại hoặc giá trị mặc định cho property. Client có thể điền sẵn giá trị đó vào form để người dùng chỉnh sửa hoặc xác nhận.

```json
{
  "name": "priority",
  "prompt": "Mức ưu tiên",
  "type": "number",
  "required": true,
  "value": 3,
  "min": 1,
  "max": 5
}
```

Trong ví dụ, client có thể hiển thị giá trị ban đầu là `3`. Khi người dùng lưu, client gửi giá trị đã chọn trong payload. Server không được mặc định rằng client sẽ giữ nguyên `value`; hãy xác thực giá trị nhận được theo quy tắc nghiệp vụ.

Đối với dữ liệu nhạy cảm, không đưa giá trị bí mật vào metadata. Ví dụ, không công bố token, mật khẩu hoặc thông tin xác thực dưới dạng `value`. `readOnly` cũng không phải cơ chế che giấu dữ liệu; nếu client không nên biết một giá trị, server không được gửi giá trị đó.

## 7. regex và ràng buộc độ dài

`regex` mô tả một biểu thức chính quy có thể dùng để kiểm tra định dạng. `minLength` và `maxLength` mô tả độ dài tối thiểu/tối đa của giá trị chuỗi.

```json
{
  "name": "referenceCode",
  "prompt": "Mã tham chiếu",
  "type": "text",
  "required": true,
  "regex": "^[A-Z]{3}-[0-9]{4}$",
  "minLength": 8,
  "maxLength": 8
}
```

Client có thể kiểm tra đầu vào trước khi gửi để giảm lỗi tương tác. Tuy nhiên, regex phải được hiểu theo quy ước mà HAL-FORMS và client hỗ trợ; không nên dựa vào hành vi khác nhau giữa các engine regex. Server vẫn phải xác thực cùng quy tắc ở phía backend.

Trong Spring, các constraint như `@NotBlank`, `@Size` hoặc `@Pattern` có thể cung cấp thông tin validation cho các cơ chế tạo metadata khi cấu hình hỗ trợ tương ứng. Cách các constraint được chuyển thành metadata cụ thể phụ thuộc phiên bản Spring HATEOAS, Jackson và affordance model factory đang dùng. Hãy kiểm tra response HAL-FORMS thực tế thay vì giả định mọi annotation đều được serialize thành cùng một property.

## 8. min, max và step

`min`, `max` và `step` cung cấp giới hạn và bước hợp lệ cho giá trị có miền số hoặc control hỗ trợ phạm vi. Ví dụ:

```json
{
  "name": "quantity",
  "prompt": "Số lượng",
  "type": "number",
  "required": true,
  "min": 1,
  "max": 50,
  "step": 1
}
```

Client có thể tạo numeric input với giá trị từ 1 đến 50 và bước tăng 1. Với một số kiểu ngày hoặc thời gian, metadata phạm vi có thể được diễn giải theo quy tắc control tương ứng. Hãy xác nhận khả năng của client trước khi dùng metadata nâng cao.

Các giới hạn trên giao diện chỉ hỗ trợ trải nghiệm nhập liệu. Server cần kiểm tra lại giá trị trong request body và từ chối dữ liệu vượt ngoài miền hợp lệ.

## 9. options và các lựa chọn có sẵn

Với property dạng lựa chọn, `options` có thể mô tả tập giá trị mà client được phép chọn. Ví dụ options inline:

```json
{
  "name": "shippingMethod",
  "prompt": "Phương thức giao hàng",
  "type": "select",
  "required": true,
  "options": {
    "inline": [
      {
        "value": "STANDARD",
        "prompt": "Tiêu chuẩn"
      },
      {
        "value": "EXPRESS",
        "prompt": "Hỏa tốc"
      }
    ]
  }
}
```

`value` là giá trị client gửi trong request; `prompt` là nhãn hiển thị. Khi danh sách lựa chọn thay đổi thường xuyên hoặc quá lớn, API có thể cung cấp options qua một link thay vì nhúng toàn bộ danh sách. Client theo link options để tải các lựa chọn theo hợp đồng HAL-FORMS mà nó hỗ trợ.

Client không nên tự suy luận giá trị gửi đi từ nhãn hiển thị. Nhãn có thể được dịch hoặc thay đổi, còn giá trị cần giữ đúng định danh do server công bố. Server vẫn phải kiểm tra lựa chọn có còn hợp lệ tại thời điểm request hay không.

## 10. multiple, cols và rows

`multiple` cho biết property có thể nhận nhiều giá trị. Nó hữu ích cho danh sách tag, nhóm vai trò hoặc nhiều lựa chọn trong một trường. `cols` và `rows` có thể gợi ý kích thước vùng nhập văn bản.

```json
{
  "name": "tags",
  "prompt": "Nhãn đơn hàng",
  "type": "select",
  "multiple": true,
  "options": {
    "inline": [
      { "value": "FRAGILE", "prompt": "Dễ vỡ" },
      { "value": "GIFT", "prompt": "Quà tặng" },
      { "value": "PRIORITY", "prompt": "Ưu tiên" }
    ]
  }
}
```

Với nội dung dài, có thể dùng textarea:

```json
{
  "name": "internalNote",
  "prompt": "Ghi chú nội bộ",
  "type": "textarea",
  "cols": 60,
  "rows": 4,
  "maxLength": 1000
}
```

Client có thể bỏ qua gợi ý kích thước nếu nền tảng không hỗ trợ. Những metadata trình bày không làm thay đổi cấu trúc dữ liệu mà server nhận.

## 11. templated và giá trị có URI template

Metadata `templated` có thể chỉ ra rằng giá trị property là URI template thay vì một giá trị cố định. Client cần mở rộng template theo quy tắc URI template trước khi sử dụng. Trường hợp này thường hữu ích khi property chứa URI hoặc tham chiếu đến tài nguyên có biến.

Ví dụ khái niệm:

```json
{
  "name": "callbackUri",
  "prompt": "Địa chỉ callback",
  "type": "url",
  "templated": true,
  "value": "https://client.example.test/events/{eventId}"
}
```

Client cần phân biệt URI template với URL cụ thể. Khi nhận dữ liệu URI từ người dùng hoặc một hệ thống bên ngoài, server cần kiểm tra scheme, host và chính sách truy cập phù hợp; không nên tin một URI tùy ý chỉ vì nó xuất hiện trong template.

## 12. Tạo template properties từ kiểu request trong Spring HATEOAS

Spring HATEOAS tạo affordance từ handler controller. Khi handler nhận một request body có kiểu cụ thể, affordance model factory có thể phân tích kiểu đó và các metadata được hỗ trợ để mô tả properties trong HAL-FORMS.

Ví dụ request DTO:

```java
import com.fasterxml.jackson.annotation.JsonPropertyDescription;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;

public record UpdateOrderRequest(
        @JsonPropertyDescription("Ghi chú hiển thị cho nhân viên giao hàng")
        @Size(max = 300)
        String note,

        @Min(1) @Max(5)
        int priority) {
}
```

Controller khai báo handler nhận DTO:

```java
import java.util.UUID;

import jakarta.validation.Valid;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PutMapping("/{id}")
ResponseEntity<Void> update(
        @PathVariable("id") UUID id,
        @Valid @RequestBody UpdateOrderRequest request) {
    orderService.update(id, request);
    return ResponseEntity.noContent().build();
}
```

Assembler gắn affordance cập nhật vào self link:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(methodOn(OrderController.class)
        .one(order.getId()))
        .withSelfRel()
        .andAffordance(afford(methodOn(OrderController.class)
                .update(order.getId(), null)));

return EntityModel.of(OrderRepresentation.from(order), self);
```

Khi response được serialize theo HAL-FORMS, metadata của `UpdateOrderRequest` có thể được dùng để tạo các template properties tương ứng. `@JsonPropertyDescription` cung cấp mô tả cho property trong Jackson metadata; các validation annotation cung cấp ràng buộc cho cơ chế introspection nếu affordance model factory được cấu hình để đọc chúng. Tên property, prompt và constraint được serialize cụ thể thế nào cần được xác nhận theo phiên bản và cấu hình của ứng dụng. Chỉ thêm constraint phù hợp với quy tắc nghiệp vụ, không thêm annotation chỉ để làm form trông có vẻ bắt buộc.

## 13. Phân biệt template properties với query parameters

Template properties thường mô tả dữ liệu đầu vào của thao tác, đặc biệt là request body. Query parameter cũng có thể là một phần của URI hoặc mapping, nhưng không nên mặc định mọi tham số của handler đều trở thành một property trong `properties`.

Ví dụ handler có `@RequestParam` để lọc collection có thể tạo URI template hoặc link tìm kiếm với tham số query. Một handler có `@RequestBody UpdateOrderRequest` mô tả payload cập nhật; các trường của DTO là ứng viên tự nhiên cho template properties.

Khi thiết kế API, hãy phân biệt:

- Path variable xác định resource trong URI, ví dụ `id`.
- Query parameter thay đổi cách chọn hoặc lọc kết quả, ví dụ `status` hoặc `page`.
- Template property mô tả một giá trị đầu vào của affordance, ví dụ `note` hoặc `priority`.

Client phải gửi mỗi giá trị vào đúng vị trí mà template và hợp đồng HTTP mô tả. Không đưa path variable vào JSON body chỉ vì nó xuất hiện trong chữ ký handler.

## 14. Kiểm thử template properties

Kiểm thử nên xác nhận template xuất hiện với đúng HTTP method và các metadata quan trọng. Với Spring MVC và `MockMvc`, có thể yêu cầu HAL-FORMS:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderTemplatePropertiesTest {

    @Autowired
    MockMvc mockMvc;

    private final UUID draftOrderId = UUID.fromString(
            "a6a1f2b4-1f0d-4a7c-8e12-123456789abc");

    @Test
    void publishesUpdatePropertiesForDraftOrder() throws Exception {
        mockMvc.perform(get("/orders/{id}", draftOrderId)
                        .accept(MediaTypes.HAL_FORMS_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._templates.default.method")
                        .value("PUT"))
                .andExpect(jsonPath("$._templates.default.properties[?(@.name == 'note')]")
                        .isNotEmpty())
                .andExpect(jsonPath("$._templates.default.properties[?(@.name == 'priority')]")
                        .isNotEmpty());
    }
}
```

`draftOrderId` là fixture hoặc dữ liệu test cần chuẩn bị. Tên template và đường dẫn JSONPath cần khớp response thực tế của ứng dụng. Nếu affordance model factory không phát ra metadata constraint như mong đợi, hãy kiểm tra cấu hình Jackson, validation và media type trước khi kết luận serializer bị lỗi.

Nên kiểm tra thêm:

- `name` khớp tên trường trong request payload.
- `prompt` có nội dung phù hợp cho client hiển thị.
- `required` và `readOnly` phản ánh đúng quy tắc đầu vào.
- `type` phù hợp với dữ liệu và control dự kiến.
- `value` không làm lộ thông tin nhạy cảm.
- `min`, `max`, `step`, `minLength`, `maxLength` phản ánh đúng ràng buộc.
- `options` chứa đúng giá trị và nhãn, hoặc link options hợp lệ.
- HAL-FORMS chỉ được trả khi client yêu cầu media type tương ứng.
- Server vẫn từ chối payload vi phạm validation dù client bỏ qua metadata.

## 15. Lỗi thường gặp

**Nhầm `name` với `prompt`:** `name` là key dữ liệu, `prompt` là nhãn hiển thị. Client dùng `name` để tạo payload.

**Cho rằng mọi metadata đều bắt buộc:** nhiều trường là tùy chọn. Client cần fallback khi không có `prompt`, `type` hoặc `value`.

**Coi `required` và `readOnly` là bảo mật:** client có thể bỏ qua metadata. Server phải xác thực và phân quyền độc lập.

**Dùng nhãn option làm giá trị gửi đi:** nhãn có thể được dịch. Gửi `value` do server công bố.

**Đưa thông tin bí mật vào `value`:** response được gửi đến client. Không serialize token, password hoặc secret vào template.

**Giả định mọi annotation tự động thành property metadata:** việc introspection phụ thuộc phiên bản và affordance model factory. Hãy kiểm tra response HAL-FORMS thực tế.

**Nhầm request body property với query parameter:** mỗi loại dữ liệu thuộc vị trí khác nhau trong HTTP request. Theo metadata và hợp đồng của thao tác.

## 16. Checklist thiết kế template properties

- Mỗi property có `name` ổn định và khớp payload mà server nhận.
- Dùng `prompt` làm nhãn thân thiện, không dùng làm key JSON.
- Đặt `required` và `readOnly` theo quy tắc thực tế.
- Chọn `type` phù hợp với dữ liệu và khả năng của client.
- Chỉ cung cấp `value` khi đó là giá trị an toàn để công bố.
- Mô tả ràng buộc bằng `regex`, `min`, `max`, `step`, `minLength` hoặc `maxLength` khi phù hợp.
- Dùng `options` cho lựa chọn cố định hoặc liên kết options cho danh sách động.
- Kiểm tra cách Jackson và validation metadata được chuyển thành HAL-FORMS.
- Phân biệt property của request body với path variable và query parameter.
- Kiểm thử template theo media type, trạng thái resource và quyền người gọi.
- Luôn xác thực request ở server, kể cả khi client đã kiểm tra theo template.

Template properties biến cấu trúc đầu vào của một affordance thành metadata mà client có thể đọc và dùng để dựng giao diện. Khi `name`, `prompt`, kiểu dữ liệu, giá trị và ràng buộc được công bố rõ ràng, client có thể tạo request phù hợp với thao tác mà server hỗ trợ; Spring HATEOAS kết nối metadata đó với handler, còn server vẫn chịu trách nhiệm xác thực và thực thi quy tắc nghiệp vụ.
