# Input field metadata

Một ứng dụng quản lý đơn hàng cho phép người dùng cập nhật địa chỉ giao hàng, ghi chú và mức ưu tiên. Khi API chỉ trả một link đến endpoint cập nhật, client biết URI đích nhưng chưa biết cần gửi những trường nào, trường nào bắt buộc, trường nào chỉ đọc hoặc giá trị nào được chọn. HAL-FORMS giải quyết phần khám phá này bằng metadata cho từng input field trong template.

Trong HAL-FORMS, một affordance được serialize thành template dưới `_templates`. Template mô tả HTTP method và content type của request; mảng `properties` mô tả các field mà client có thể gửi. Mỗi property có thể mang tên, prompt, kiểu dữ liệu, giá trị gợi ý, ràng buộc và danh sách lựa chọn. Client dùng metadata để dựng form hoặc giao diện tương tác phù hợp với thao tác mà server công bố.

## Input field metadata là gì?

Input field metadata là tập thông tin mô tả một trường đầu vào trong HAL-FORMS template. Metadata giúp client hiểu:

- Trường được gửi với tên nào trong request.
- Nhãn hiển thị thân thiện cho người dùng là gì.
- Trường có bắt buộc hay chỉ đọc không.
- Client nên dùng loại control nào, ví dụ text, number, date hoặc select.
- Giá trị gợi ý ban đầu là gì.
- Độ dài, miền giá trị hoặc pattern nào được công bố.
- Trường có tập lựa chọn cố định hoặc nguồn options riêng hay không.

Metadata nằm trong từng object của `properties`:

```json
{
  "_templates": {
    "default": {
      "title": "Cập nhật đơn hàng",
      "method": "PATCH",
      "contentType": "application/merge-patch+json",
      "properties": [
        {
          "name": "shippingAddress",
          "prompt": "Địa chỉ giao hàng",
          "type": "text",
          "required": true,
          "minLength": 5,
          "maxLength": 200
        }
      ]
    }
  }
}
```

Trong ví dụ, template `default` mô tả thao tác PATCH. Property `shippingAddress` cho client biết tên field, nhãn hiển thị, loại input và giới hạn độ dài. Đây là metadata của request template, không phải dữ liệu response của resource.

## Cấu trúc một HAL-FORMS template

Template được đặt trong `_templates` của HAL representation. Một template thường có các thuộc tính cấp template:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `title` | Tên thân thiện của thao tác hoặc form. |
| `method` | HTTP method dùng khi gửi request, ví dụ `GET`, `POST`, `PUT`, `PATCH` hoặc `DELETE` tùy thao tác. |
| `contentType` | Media type của request body mà template gửi, ví dụ `application/json` hoặc `application/merge-patch+json`. |
| `properties` | Danh sách metadata của các input field. |

Ví dụ template hoàn chỉnh hơn:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/ord-1042"
    }
  },
  "_templates": {
    "default": {
      "title": "Cập nhật đơn hàng",
      "method": "PATCH",
      "contentType": "application/merge-patch+json",
      "properties": [
        {
          "name": "shippingAddress",
          "prompt": "Địa chỉ giao hàng",
          "type": "text",
          "required": true,
          "minLength": 5,
          "maxLength": 200
        },
        {
          "name": "deliveryNote",
          "prompt": "Ghi chú giao hàng",
          "type": "text",
          "required": false,
          "maxLength": 500
        }
      ]
    }
  }
}
```

Client dùng link để biết resource đích và template để biết cách tương tác. `method` và `contentType` áp dụng cho request được tạo từ template; các thuộc tính trong `properties` áp dụng cho từng field.

## Các thuộc tính của property

HAL-FORMS định nghĩa nhiều metadata có thể dùng để mô tả input field. Không phải property nào cũng cần mọi thuộc tính; chỉ khai báo những thông tin có ý nghĩa cho field đó.

| Thuộc tính | Kiểu dữ liệu thường dùng | Ý nghĩa |
| --- | --- | --- |
| `name` | string | Tên field trong dữ liệu request. |
| `prompt` | string | Nhãn thân thiện hiển thị cho người dùng. |
| `type` | string | Gợi ý kiểu input/control cho client. |
| `required` | boolean | Field có bắt buộc được cung cấp trong thao tác hay không. |
| `readOnly` | boolean | Field được hiển thị nhưng không cho người dùng chỉnh sửa. |
| `value` | giá trị JSON | Giá trị gợi ý hoặc giá trị hiện tại cho field. |
| `regex` | string | Pattern mà giá trị nhập cần thỏa mãn. |
| `min` | number hoặc giá trị phù hợp với type | Giá trị tối thiểu. |
| `max` | number hoặc giá trị phù hợp với type | Giá trị tối đa. |
| `minLength` | number | Độ dài tối thiểu của chuỗi. |
| `maxLength` | number | Độ dài tối đa của chuỗi. |
| `step` | number | Bước tăng/giảm hợp lệ cho kiểu giá trị số hoặc range. |
| `options` | object | Danh sách lựa chọn nhúng hoặc link đến nguồn lựa chọn. |

Các metadata này là gợi ý cho client xây dựng giao diện và kiểm tra dữ liệu sớm. Server vẫn phải kiểm tra request thực tế bằng validation và quy tắc nghiệp vụ.

## name và prompt

`name` là tên kỹ thuật của property. Nó cần khớp với cấu trúc request mà endpoint chấp nhận, sau khi áp dụng quy tắc serialize/deserialize của ứng dụng.

`prompt` là nhãn thân thiện mà client có thể hiển thị. Ví dụ:

```json
{
  "name": "shippingAddress",
  "prompt": "Địa chỉ giao hàng"
}
```

Client có thể dùng `shippingAddress` làm key trong request JSON và hiển thị “Địa chỉ giao hàng” trên form. Không nên dùng prompt làm key vì prompt có thể thay đổi theo ngôn ngữ hoặc thiết kế giao diện.

Nếu API phục vụ nhiều locale, prompt có thể được bản địa hóa theo ngôn ngữ response. Cần giữ `name` ổn định giữa các ngôn ngữ để request body không thay đổi theo locale.

## type: gợi ý control cho client

`type` giúp client chọn loại input phù hợp. Một số giá trị thường gặp có ngữ nghĩa gần với các control HTML:

| Type | Cách client có thể hiển thị | Ví dụ |
| --- | --- | --- |
| `text` | Ô nhập văn bản một dòng | Tên người nhận, địa chỉ. |
| `textarea` | Ô nhập văn bản nhiều dòng | Ghi chú giao hàng. |
| `number` | Ô nhập số | Số lượng, trọng lượng. |
| `range` | Thanh chọn khoảng giá trị | Mức ưu tiên dạng thang số. |
| `date` | Bộ chọn ngày | Ngày giao dự kiến. |
| `time` | Bộ chọn giờ | Khung giờ giao hàng. |
| `datetime-local` | Ngày và giờ | Thời điểm hẹn giao. |
| `email` | Ô nhập email | Email liên hệ. |
| `url` | Ô nhập URL | Địa chỉ website. |
| `tel` | Ô nhập số điện thoại | Số liên hệ. |
| `checkbox` | Hộp chọn bật/tắt | Yêu cầu giao không tiếp xúc. |
| `radio` | Nhóm lựa chọn một giá trị | Chọn phương thức giao. |
| `select` | Danh sách lựa chọn | Chọn mức ưu tiên. |

Ví dụ:

```json
{
  "name": "deliveryDate",
  "prompt": "Ngày giao dự kiến",
  "type": "date",
  "required": true
}
```

`type` là gợi ý trình bày. Client có thể không hỗ trợ một số loại control hoặc có cách hiển thị riêng. Server không được dựa vào việc client đã tạo đúng control để bỏ qua validation.

## required và readOnly

Hai thuộc tính này giải quyết hai câu hỏi khác nhau:

- `required: true`: thao tác yêu cầu client cung cấp giá trị cho field theo hợp đồng template.
- `readOnly: true`: field được mô tả nhưng client không nên cho người dùng chỉnh sửa giá trị.

Ví dụ:

```json
{
  "name": "orderNumber",
  "prompt": "Mã đơn hàng",
  "type": "text",
  "readOnly": true,
  "value": "ORD-1042"
}
```

Client có thể hiển thị mã đơn hàng nhưng không cho sửa. Trường này có thể hữu ích để cung cấp ngữ cảnh trong form cập nhật.

`required` không đồng nghĩa với “không được null” trong mọi định dạng request. Ý nghĩa chính xác còn phụ thuộc content type và hợp đồng của endpoint. Với JSON Merge Patch, việc bỏ field và gửi `null` có semantics khác nhau; HAL-FORMS metadata không thay thế quy tắc patch document.

`readOnly` cũng không phải biện pháp bảo mật. Client có thể tự gửi field read-only bằng HTTP request. Server cần bỏ qua hoặc từ chối field đó theo hợp đồng, đồng thời kiểm tra quyền và invariant ở tầng xử lý request.

## value: giá trị gợi ý ban đầu

`value` cung cấp giá trị hiện tại hoặc giá trị gợi ý cho field. Client có thể dùng nó để điền sẵn form:

```json
{
  "name": "deliveryNote",
  "prompt": "Ghi chú giao hàng",
  "type": "textarea",
  "required": false,
  "value": "Gọi trước khi giao hàng"
}
```

Không phải mọi thao tác đều cần `value`. Với thao tác tạo mới, có thể dùng giá trị mặc định nếu API muốn gợi ý; với thao tác cập nhật, có thể dùng giá trị hiện tại nếu representation và chính sách bảo mật cho phép.

Không đưa dữ liệu nhạy cảm vào `value` chỉ để tiện điền form. Mọi giá trị trong response đều có thể được client đọc và lưu lại. Nếu field không được phép xem, hãy bỏ nó khỏi representation/template thay vì chỉ đánh dấu read-only.

## Ràng buộc regex, min, max, minLength, maxLength và step

HAL-FORMS có thể công bố các ràng buộc để client kiểm tra dữ liệu trước khi gửi request.

### regex

`regex` mô tả pattern mà chuỗi cần thỏa mãn:

```json
{
  "name": "postalCode",
  "prompt": "Mã bưu chính",
  "type": "text",
  "regex": "^[0-9]{5,6}$"
}
```

Pattern là gợi ý validation phía client. Cần chọn cú pháp tương thích với client và không dựa vào regex client như lớp bảo vệ duy nhất. Server phải kiểm tra bằng validator phù hợp với ngôn ngữ và quy tắc nghiệp vụ.

### min và max

Với kiểu số, `min` và `max` giới hạn miền giá trị:

```json
{
  "name": "quantity",
  "prompt": "Số lượng",
  "type": "number",
  "min": 1,
  "max": 50,
  "step": 1
}
```

Với kiểu ngày hoặc thời gian, metadata giới hạn có thể được dùng theo quy ước type và khả năng của client. Hãy kiểm tra định dạng giá trị và hỗ trợ của client trước khi công bố.

### minLength và maxLength

Hai thuộc tính này giới hạn độ dài chuỗi:

```json
{
  "name": "shippingAddress",
  "prompt": "Địa chỉ giao hàng",
  "type": "text",
  "minLength": 5,
  "maxLength": 200
}
```

Client có thể dùng chúng để cảnh báo người dùng trước khi submit. Server vẫn phải validate độ dài sau khi nhận request vì client có thể bỏ qua hoặc thay đổi metadata.

### step

`step` mô tả khoảng tăng hợp lệ cho input dạng số/range:

```json
{
  "name": "weight",
  "prompt": "Khối lượng (kg)",
  "type": "number",
  "min": 0.5,
  "max": 30,
  "step": 0.5
}
```

Giá trị step cần phù hợp với miền nghiệp vụ và độ chính xác lưu trữ. Ví dụ cân nặng cho phép bước `0.5` kg; server cần áp dụng cùng quy tắc khi validate.

## options: lựa chọn cho select, radio và các field có tập giá trị

Khi field chỉ chấp nhận một số giá trị, `options` có thể cung cấp lựa chọn cho client. HAL-FORMS hỗ trợ options nhúng trực tiếp hoặc link đến nguồn options.

### Inline options

Ví dụ field chọn mức ưu tiên:

```json
{
  "name": "priority",
  "prompt": "Mức ưu tiên",
  "type": "select",
  "required": true,
  "options": {
    "inline": [
      { "value": "NORMAL", "prompt": "Bình thường" },
      { "value": "EXPRESS", "prompt": "Hỏa tốc" },
      { "value": "SCHEDULED", "prompt": "Theo lịch" }
    ]
  }
}
```

Client hiển thị prompt cho người dùng nhưng gửi giá trị `value` trong request. Không dùng prompt làm giá trị nghiệp vụ vì prompt có thể được dịch hoặc thay đổi câu chữ.

Inline options phù hợp khi tập lựa chọn nhỏ và ít thay đổi. Nếu tập giá trị lớn hoặc được quản lý độc lập, nên dùng link options.

### Linked options

Khi options được lấy từ resource khác, template có thể tham chiếu một URI cung cấp danh sách lựa chọn:

```json
{
  "name": "customerId",
  "prompt": "Khách hàng",
  "type": "select",
  "required": true,
  "options": {
    "link": {
      "href": "https://api.example.com/api/customers/options"
    }
  }
}
```

Client theo link để lấy options. Điều này tránh nhúng một danh sách lớn vào mọi response. Resource options có thể được phân trang, cache hoặc bảo vệ theo quyền truy cập riêng.

Hãy bảo đảm endpoint options trả cấu trúc mà client HAL-FORMS hiểu được. Không giả định mọi JSON array thông thường đều tự động là options hợp lệ. Cần kiểm tra response theo quy ước HAL-FORMS mà ứng dụng công bố.

## Liên hệ input metadata với affordance

Input metadata được gắn với thao tác mà affordance mô tả. Ví dụ, đơn hàng có endpoint PATCH:

```java
import java.util.UUID;

import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;

@PatchMapping(
    path = "/{id}",
    consumes = "application/json")
OrderView patch(
        @PathVariable UUID id,
        @RequestBody OrderPatchRequest request) {
    return orderService.patch(id, request);
}
```

Representation có thể gắn affordance của method PATCH vào link:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Link;

Link self = linkTo(methodOn(OrderController.class).one(order.getId()))
    .withSelfRel()
    .andAffordance(afford(
        methodOn(OrderController.class).patch(order.getId(), null)));
```

Khi client yêu cầu HAL-FORMS, Spring HATEOAS có thể serialize affordance thành template và mô tả các input property dựa trên metadata của phương thức/kiểu đầu vào mà framework nhận diện. `methodOn(...)` chỉ ghi nhận method mapping và tham số; nó không gọi controller và không gửi request.

Mức metadata được tự suy ra phụ thuộc kiểu request, Jackson mapping, cấu hình HAL-FORMS và phiên bản framework. Không giả định mọi annotation validation hoặc mọi quy tắc nghiệp vụ đều được chuyển thành property metadata. Nếu hợp đồng cần `options`, prompt, default value hoặc ràng buộc cụ thể, hãy cấu hình và kiểm thử HAL-FORMS output tương ứng.

## Request DTO và validation phía server

Một request DTO có thể dùng Bean Validation để bảo vệ endpoint:

```java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

enum OrderPriority {
    NORMAL, EXPRESS, SCHEDULED
}

public record OrderPatchRequest(
    @NotBlank
    @Size(min = 5, max = 200)
    String shippingAddress,

    @Size(max = 500) String deliveryNote,

    @NotNull OrderPriority priority
) {
}
```

Controller cần kích hoạt validation:

```java
@PatchMapping(
    path = "/{id}",
    consumes = "application/json")
OrderView patch(
        @PathVariable UUID id,
        @Valid @RequestBody OrderPatchRequest request) {
    return orderService.patch(id, request);
}
```

Các annotation `@NotBlank` và `@Size` là quy tắc kiểm tra ở server. HAL-FORMS metadata có thể giúp client hiển thị required/length constraints nếu framework và cấu hình ánh xạ chúng, nhưng endpoint vẫn phải validate độc lập.

Với PATCH, DTO record đơn giản không tự phân biệt property vắng mặt và property được gửi rõ ràng với `null`. Nếu API dùng JSON Merge Patch, `null` có semantics xóa property. Nếu API dùng patch DTO riêng, hãy thiết kế kiểu dữ liệu có thể giữ presence của field hoặc tài liệu hóa rõ quy tắc. Không suy ra rằng `required: false` đồng nghĩa `null` luôn được chấp nhận.

## Tùy biến metadata trong Spring HATEOAS

Spring HATEOAS xây dựng HAL-FORMS template từ affordance model và thông tin request mà framework nhận diện. Với những metadata đơn giản, kiểu dữ liệu và chữ ký controller có thể cung cấp một phần thông tin cho template.

Khi cần điều khiển options, relation, hoặc cách một kiểu dữ liệu được biểu diễn trong HAL-FORMS, có thể dùng cấu hình HAL-FORMS của Spring HATEOAS, chẳng hạn `HalFormsConfiguration` và các kiểu options tương ứng trong phiên bản đang sử dụng. Cấu hình nên tập trung vào metadata mà client cần, không đưa logic nghiệp vụ hoặc dữ liệu nhạy cảm vào template.

Trước khi phụ thuộc vào một annotation hoặc quy tắc tự suy diễn, hãy kiểm tra API của phiên bản Spring HATEOAS trong dự án. Các phiên bản có thể khác nhau về khả năng ánh xạ validation metadata, enum options và custom property metadata. Response HAL-FORMS đã serialize mới là hợp đồng mà client thực sự nhận.

## Bản địa hóa prompt

Prompt thường được hiển thị trực tiếp cho người dùng, vì vậy có thể được bản địa hóa theo locale của request. Ví dụ:

| Locale | Prompt |
| --- | --- |
| `vi` | `Địa chỉ giao hàng` |
| `en` | `Shipping address` |

Trong cả hai trường hợp, `name` vẫn là `shippingAddress`. Client gửi cùng key request; chỉ nhãn hiển thị thay đổi.

Nếu response thay đổi theo `Accept-Language`, cache cần tính đến locale để tránh trả prompt ngôn ngữ này cho người dùng ngôn ngữ khác. Không dùng chuỗi prompt làm identifier trong client hoặc logic server.

## Bảo mật và quyền truy cập của input field

Input metadata có thể tiết lộ những field mà server chấp nhận hoặc những lựa chọn nghiệp vụ có sẵn. Trước khi công bố template, cần xem xét:

- Người dùng có quyền thực hiện affordance hay không.
- Field có được phép chỉnh sửa trong trạng thái resource hiện tại không.
- Options có chứa dữ liệu hoặc định danh mà người dùng không được xem không.
- `value` có chứa thông tin cá nhân hoặc dữ liệu nhạy cảm không.
- Field read-only có thực sự cần xuất hiện trong form không.
- Template có bị cache dùng chung giữa các vai trò hoặc tenant khác nhau không.

`readOnly` và việc bỏ field khỏi template chỉ là hướng dẫn cho client. Server phải từ chối hoặc bỏ qua mọi field không được phép thay đổi, kể cả khi client tự tạo request ngoài template.

## Kiểm thử input field metadata

Kiểm thử cần xác nhận template chứa đúng metadata mà client dựa vào. Với MockMvc, yêu cầu media type HAL-FORMS:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/prs.hal-forms+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._templates.default.method").value("PATCH"))
    .andExpect(jsonPath("$._templates.default.contentType")
        .value("application/json"))
    .andExpect(jsonPath("$._templates.default.properties[0].name")
        .value("shippingAddress"))
    .andExpect(jsonPath("$._templates.default.properties[0].prompt")
        .value("Địa chỉ giao hàng"))
    .andExpect(jsonPath("$._templates.default.properties[0].required")
        .value(true));
```

`default` là tên template minh họa; relation hoặc cấu hình affordance có thể tạo tên template khác. Trong test thực tế, hãy kiểm tra đúng key và cấu trúc response được công bố.

Với options, kiểm tra cả value và prompt:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.parseMediaType("application/prs.hal-forms+json")))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$._templates.default.properties[2].options.inline[0].value")
        .value("NORMAL"));
```

Ví dụ giả định `priority` là property thứ ba trong template. Nếu thứ tự property thay đổi, hãy tìm phần tử theo `name` bằng `JsonPath`/`ObjectMapper` thay vì phụ thuộc vào index cố định.

Ngoài metadata, cần kiểm thử endpoint thực tế:

- Gửi field hợp lệ và xác nhận cập nhật thành công.
- Bỏ field tùy chọn và xác nhận semantics đúng.
- Gửi giá trị vi phạm `min`, `max`, `regex` hoặc độ dài và xác nhận server từ chối.
- Gửi field read-only hoặc field không được phép và xác nhận server không thay đổi dữ liệu trái phép.
- Gửi option value không nằm trong tập cho phép và xác nhận validation thất bại.
- Kiểm thử prompt theo locale nếu API hỗ trợ bản địa hóa.
- Kiểm tra template không tiết lộ options hoặc giá trị thuộc tenant/người dùng khác.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `prompt` làm key request | Đổi ngôn ngữ làm request body thay đổi. | Dùng `name` làm key ổn định; prompt chỉ là nhãn hiển thị. |
| Nghĩ `required: false` nghĩa là `null` luôn hợp lệ | Client gửi null có thể gây xóa hoặc lỗi ngoài dự kiến. | Định nghĩa semantics absent/null theo content type và endpoint. |
| Coi `readOnly` là bảo mật | Client vẫn có thể tự gửi field đó. | Kiểm tra field được phép thay đổi ở server. |
| Dựa hoàn toàn vào `type` để validate | Client khác nhau có thể hỗ trợ control khác nhau. | Validate giá trị trong controller/service. |
| Công bố options quá rộng | Client thấy hoặc gửi lựa chọn không có quyền sử dụng. | Lọc options theo quyền và tenant ở server. |
| Nhúng options lớn vào mọi template | Response nặng và options khó cache độc lập. | Dùng linked options khi danh sách lớn hoặc thay đổi thường xuyên. |
| Giả định Bean Validation luôn được ánh xạ đầy đủ | Template có thể thiếu constraint mà client kỳ vọng. | Kiểm thử HAL-FORMS output và tùy biến cấu hình khi cần. |
| Chỉ test JSON response thông thường | Không phát hiện sai metadata trong HAL-FORMS. | Gửi `Accept: application/prs.hal-forms+json` và kiểm tra `_templates`. |

## Ghi nhớ

- Input field metadata nằm trong `properties` của HAL-FORMS template dưới `_templates`.
- `name` là key kỹ thuật; `prompt` là nhãn hiển thị và có thể bản địa hóa.
- `type` gợi ý control; `required` và `readOnly` hướng dẫn client về khả năng nhập liệu.
- `value` cung cấp giá trị gợi ý; không đưa dữ liệu nhạy cảm vào template.
- `regex`, `min`, `max`, `minLength`, `maxLength` và `step` mô tả ràng buộc để client hỗ trợ validation sớm.
- `options.inline` nhúng tập lựa chọn nhỏ; `options.link` tham chiếu nguồn options độc lập.
- Metadata được gắn với affordance và request type; mức tự suy diễn phụ thuộc cấu hình/phiên bản Spring HATEOAS.
- HAL-FORMS metadata không thay thế validation, authorization hoặc semantics của PATCH ở server.
- Kiểm thử response HAL-FORMS đã serialize cùng endpoint thực tế, options, locale và các trường hợp dữ liệu không hợp lệ.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
- [Spring HATEOAS API – HalFormsConfiguration](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/forms/HalFormsConfiguration.html)
- [HAL-FORMS specification](https://rwcbook.github.io/hal-forms/)
- [RFC 5789 – PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789)
- [RFC 7396 – JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396)
