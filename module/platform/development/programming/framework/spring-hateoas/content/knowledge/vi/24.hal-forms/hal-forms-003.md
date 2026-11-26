# `_templates`

Trong HAL-FORMS, `_templates` là vùng metadata mô tả các thao tác mà client có thể thực hiện trên tài nguyên. Mỗi template cung cấp tên thao tác, HTTP method, media type của request và danh sách property mà client cần gửi. Nhờ đó, client có thể dựng form hoặc giao diện tương tác dựa trên response hypermedia thay vì phải hard-code mọi endpoint và cấu trúc request.

Spring HATEOAS có thể tạo template từ affordance gắn với link. Khi controller công bố một affordance cho thao tác cập nhật hoặc hủy đơn hàng, HAL-FORMS serializer chuyển metadata đó thành các entry trong `_templates`. Client đọc template, thu thập giá trị input rồi gửi request đến target với method và content type đã công bố.

## `_templates` nằm ở đâu trong HAL-FORMS?

HAL-FORMS dùng media type `application/prs.hal-forms+json`. Một representation có thể chứa dữ liệu tài nguyên, `_links` để điều hướng và `_templates` để mô tả các thao tác có input:

```json
{
  "id": "o-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    }
  },
  "_templates": {
    "default": {
      "title": "Cập nhật đơn hàng",
      "method": "PUT",
      "contentType": "application/json",
      "target": "https://shop.example/api/orders/o-42",
      "properties": [
        {
          "name": "note",
          "prompt": "Ghi chú",
          "type": "text",
          "required": false
        },
        {
          "name": "deliveryDate",
          "prompt": "Ngày giao dự kiến",
          "type": "date",
          "required": true
        }
      ]
    },
    "cancel": {
      "title": "Hủy đơn hàng",
      "method": "POST",
      "contentType": "application/json",
      "target": "https://shop.example/api/orders/o-42/cancellation",
      "properties": [
        {
          "name": "reason",
          "prompt": "Lý do hủy",
          "type": "text",
          "required": true,
          "maxLength": 250
        }
      ]
    }
  }
}
```

`_templates` là một object ánh xạ tên template sang định nghĩa template. Trong ví dụ:

- `default` là tên template mặc định của tài nguyên, mô tả cách cập nhật đơn hàng.
- `cancel` là template có tên riêng cho thao tác hủy.
- `method` cho biết HTTP method mà client dùng khi submit.
- `contentType` cho biết media type của request body.
- `target` xác định URI nhận request; nếu không được công bố riêng, target mặc định gắn với URI của resource theo quy tắc HAL-FORMS.
- `properties` mô tả các trường input mà client có thể thu thập.

`_templates` không phải một HTML form đã render. Nó là metadata có cấu trúc để client tự dựng giao diện phù hợp với nền tảng của mình: web, mobile, desktop hoặc một HTTP client tự động.

## Phân biệt `_links` và `_templates`

Hai vùng này bổ sung cho nhau nhưng có vai trò khác nhau:

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| `_links` | Công bố URI và relation để client điều hướng đến resource. | `self`, `customer`, `items` |
| `_templates` | Công bố cách thực hiện một thao tác, gồm method, target, content type và input properties. | `default`, `cancel` |

Một link `self` cho client biết URI của đơn hàng. Một template `default` có thể cho biết client gửi `PUT` đến URI đó với body gồm `note` và `deliveryDate`. Link cho biết có thể điều hướng đến đâu; template cho biết có thể gửi thao tác theo hình thức nào.

Không phải mọi link đều cần template. Link đến một tài nguyên chỉ đọc có thể không có thao tác nhập liệu. Ngược lại, một template thường gắn với resource và target cụ thể để client biết thao tác đó áp dụng ở đâu. Một relation trong `_links` không tự động tạo ra template nếu server không công bố affordance tương ứng.

## Các trường chính của template

Một template có thể chứa các metadata sau:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `title` | Nhãn mô tả thao tác để giao diện hiển thị. | `Cập nhật đơn hàng` |
| `method` | HTTP method được dùng khi gửi request. | `PUT`, `POST`, `PATCH`, `DELETE` |
| `contentType` | Media type của request body. | `application/json` |
| `target` | URI đích của thao tác khi được công bố. | `/api/orders/o-42` |
| `properties` | Danh sách trường input và metadata của chúng. | `status`, `note` |

Tên template là khóa trong `_templates`, chẳng hạn `default`, `cancel` hoặc `approve`. `default` có ý nghĩa quy ước để client chọn template mặc định; tên khác cho phép một resource công bố nhiều thao tác. Tên cần ổn định và có ý nghĩa, vì client có thể dùng nó để chọn đúng luồng tương tác.

`method` và `contentType` giúp client tạo request đúng với endpoint. `target` cho phép template chỉ rõ URI nhận request; client không nên tự suy ra endpoint từ tên template. Nếu target vắng mặt, client áp dụng quy tắc mặc định của HAL-FORMS và ngữ cảnh resource thay vì tự nối URL.

## Property mô tả input

Mỗi phần tử trong `properties` mô tả một trường mà client có thể hiển thị hoặc gửi. Một property có thể có:

- `name`: tên thuộc tính trong request payload.
- `prompt`: nhãn gợi ý cho giao diện.
- `type`: kiểu input phù hợp như `text`, `number`, `date`, `email`, `checkbox` hoặc `select`.
- `required`: cho biết trường có bắt buộc theo metadata template hay không.
- `readOnly`: cho biết trường chỉ hiển thị và không nên cho người dùng sửa.
- `value`: giá trị mặc định hoặc giá trị hiện tại được công bố.
- `min`, `max`, `minLength`, `maxLength`, `regex`: ràng buộc gợi ý cho input.
- `options`: tập lựa chọn cho kiểu input như select hoặc radio.

Ví dụ property cho cập nhật trạng thái đơn hàng:

```json
{
  "name": "status",
  "prompt": "Trạng thái đơn hàng",
  "type": "select",
  "required": true,
  "value": "PENDING",
  "options": {
    "inline": false,
    "link": {
      "href": "https://shop.example/api/order-status-options"
    },
    "promptField": "label",
    "valueField": "code"
  }
}
```

Với kiểu lựa chọn, `options` có thể mô tả tập lựa chọn inline hoặc chỉ đến nguồn options để client tải thêm; các trường như `promptField` và `valueField` giúp ánh xạ nhãn hiển thị và giá trị gửi đi. Cấu trúc options cần khớp với quy ước HAL-FORMS mà client hỗ trợ. Property metadata giúp client dựng input phù hợp mà không phải biết trước toàn bộ schema. Tuy nhiên, nó chỉ mô tả giao diện và ràng buộc được công bố. Server vẫn phải validate request thực tế, kiểm tra quyền và áp dụng quy tắc nghiệp vụ khi nhận dữ liệu.

## Nhiều template trên cùng một resource

Một resource có thể công bố nhiều template cho các thao tác khác nhau. Ví dụ đơn hàng đang `PENDING` có thể cho phép cập nhật ghi chú và hủy đơn. Cả hai template được đặt trong `_templates` nhưng có tên, method, target và properties riêng.

```json
{
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    }
  },
  "_templates": {
    "default": {
      "title": "Cập nhật đơn hàng",
      "method": "PATCH",
      "contentType": "application/json",
      "properties": [
        { "name": "note", "prompt": "Ghi chú", "type": "text" }
      ]
    },
    "cancel": {
      "title": "Hủy đơn hàng",
      "method": "POST",
      "contentType": "application/json",
      "target": "https://shop.example/api/orders/o-42/cancellation",
      "properties": [
        {
          "name": "reason",
          "prompt": "Lý do",
          "type": "text",
          "required": true
        }
      ]
    }
  }
}
```

Client có thể hiển thị nút “Cập nhật đơn hàng” và “Hủy đơn hàng”. Khi người dùng chọn một thao tác, client đọc template tương ứng để biết request cần gửi. Server chỉ nên công bố template khi thao tác có ý nghĩa với trạng thái resource và người dùng hiện tại.

## Công bố template từ Spring HATEOAS affordance

Spring HATEOAS tạo HAL-FORMS template từ affordance gắn với link. Affordance mô tả một thao tác có thể thực hiện trên resource, gồm mapping controller và metadata input/output. HAL-FORMS converter chuyển affordance thành `_templates` khi controller trả representation với media type HAL-FORMS.

Ví dụ DTO đầu vào cho hai thao tác:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateOrderRequest(
        @Size(max = 250) String note
) {
}

public record CancelOrderRequest(
        @NotBlank @Size(max = 250) String reason
) {
}
```

Controller định nghĩa các endpoint tương ứng:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import jakarta.validation.Valid;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService service;
    private final OrderAssembler assembler;

    OrderController(OrderService service, OrderAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_FORMS_JSON_VALUE)
    EntityModel<OrderDto> one(@PathVariable UUID id) {
        return assembler.toModel(service.findById(id));
    }

    @PutMapping(value = "/{id}", consumes = "application/json")
    ResponseEntity<Void> update(
            @PathVariable UUID id,
            @Valid @RequestBody UpdateOrderRequest input) {
        service.update(id, input);
        return ResponseEntity.noContent().build();
    }

    @PostMapping(value = "/{id}/cancellation", consumes = "application/json")
    ResponseEntity<Void> cancel(
            @PathVariable UUID id,
            @Valid @RequestBody CancelOrderRequest input) {
        service.cancel(id, input.reason());
        return ResponseEntity.noContent().build();
    }
}
```

Assembler gắn affordance cho self link:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Affordances;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.stereotype.Component;

@Component
class OrderAssembler {

    EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(order.getId(), order.getStatus().name());

        Link self = linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel();

        Link affordanceLink = Affordances.of(self)
                .afford(afford(methodOn(OrderController.class)
                        .update(order.getId(), null))
                        .withInput(UpdateOrderRequest.class)
                        .withName("default"))
                .andAfford(afford(methodOn(OrderController.class)
                        .cancel(order.getId(), null))
                        .withInput(CancelOrderRequest.class)
                        .withName("cancel"))
                .toLink();

        return EntityModel.of(dto, affordanceLink);
    }
}
```

Trong ví dụ, `Affordances.of(self)` bắt đầu từ self link của đơn hàng. `afford(...)` mô tả endpoint cập nhật; `withInput(UpdateOrderRequest.class)` cung cấp kiểu dữ liệu đầu vào để Spring HATEOAS tạo property metadata; `withName("default")` đặt tên template. `andAfford(...)` thêm template hủy với input riêng. `toLink()` trả về link có các affordance gắn kèm.

`methodOn(...)` chỉ mô tả method mapping để tạo URI và metadata, không gọi endpoint cập nhật hoặc hủy. Khi serialize representation dưới HAL-FORMS, các affordance được chuyển thành `_templates`. Các kiểu `Order`, `OrderDto`, `OrderService` và `OrderAssembler` là thành phần ứng dụng; cần định nghĩa chúng theo domain thực tế.

## Tạo template mặc định và template có tên

`withName("default")` đặt tên template mặc định. Một template bổ sung có thể dùng tên như `cancel`, `approve` hoặc `ship`. Tên này trở thành key trong `_templates` và giúp client chọn đúng thao tác.

```java
Affordances.of(self)
        .afford(afford(methodOn(OrderController.class)
                .update(orderId, null))
                .withInput(UpdateOrderRequest.class)
                .withName("default"))
        .andAfford(afford(methodOn(OrderController.class)
                .cancel(orderId, null))
                .withInput(CancelOrderRequest.class)
                .withName("cancel"))
        .toLink();
```

Nếu chỉ có một affordance và không đặt tên riêng, Spring HATEOAS có thể sử dụng quy tắc mặc định của builder/serializer. Với hợp đồng mà client cần chọn template rõ ràng, hãy đặt tên tường minh và kiểm tra JSON thực tế để bảo đảm key mong đợi được công bố.

Không dùng cùng một tên cho nhiều thao tác có ý nghĩa khác nhau. Cũng không nên để client suy ra hành động từ tên method Java; tên template là một phần hợp đồng hypermedia và nên ổn định qua refactor.

## Metadata của template lấy từ đâu?

Spring HATEOAS có thể lấy thông tin input từ kiểu DTO được truyền vào `withInput(...)`. Các trường của DTO cùng metadata validation có thể được dùng để mô tả property trong HAL-FORMS. Ví dụ:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateDeliveryRequest(
        @NotBlank @Size(max = 100) String address,
        @Min(1) @Max(10) int deliveryWindow
) {
}
```

Các annotation validation có thể cung cấp ràng buộc để Spring HATEOAS hiển thị trong property metadata nếu cấu hình metadata tương ứng được bật. Tùy phiên bản và cấu hình, có thể cần `HalFormsConfiguration` hoặc custom property metadata để điều chỉnh prompt, type, options và cách diễn giải validation.

Đừng coi việc có annotation `@NotBlank` đồng nghĩa client chắc chắn nhận đúng mọi metadata mong muốn. Hãy kiểm tra response HAL-FORMS thực tế. Validation server vẫn phải chạy trên endpoint; client có thể bỏ qua metadata hoặc gửi request không hợp lệ.

## Template và trạng thái resource

Không phải mọi thao tác đều khả dụng trong mọi trạng thái. Ví dụ đơn hàng `PENDING` có thể cho phép `default` và `cancel`; đơn hàng `SHIPPED` có thể không còn template hủy. Assembler hoặc lớp ứng dụng cần quyết định affordance nào được gắn vào resource hiện tại.

```java
var affordances = Affordances.of(self)
        .afford(afford(methodOn(OrderController.class)
                .update(orderId, null))
                .withInput(UpdateOrderRequest.class)
                .withName("default"));

if (order.canBeCancelled()) {
    affordances = affordances.andAfford(
            afford(methodOn(OrderController.class)
                    .cancel(orderId, null))
                    .withInput(CancelOrderRequest.class)
                    .withName("cancel"));
}

Link link = affordances.toLink();
```

Ví dụ minh họa việc tạo template có điều kiện; kiểu builder cụ thể cần được giữ nhất quán với phiên bản Spring HATEOAS đang dùng. Điều kiện nghiệp vụ nên được tính từ domain/service hoặc một policy collaborator, tránh để assembler tự truy vấn database.

Ẩn template không thay thế bảo mật. Endpoint `cancel` vẫn phải xác thực, phân quyền và kiểm tra trạng thái tại thời điểm nhận request. Client có thể gửi request thủ công ngay cả khi template không xuất hiện trong response trước đó.

## Client sử dụng `_templates`

Client không cần biết trước endpoint hủy hoặc cấu trúc input. Quy trình tổng quát:

1. Gửi GET và yêu cầu `application/prs.hal-forms+json`.
2. Đọc `_templates` trong response.
3. Chọn template theo tên hoặc theo hành động hiển thị cho người dùng.
4. Dựng input từ `properties`, dùng `prompt`, `type`, `required`, `options` và các constraint để hỗ trợ nhập liệu.
5. Gửi request đến `target` với HTTP method và `contentType` của template.
6. Đọc response mới để cập nhật resource và các template/links hiện hành.

Ví dụ client chọn template `cancel` có thể gửi:

```http
POST /api/orders/o-42/cancellation HTTP/1.1
Content-Type: application/json
Accept: application/prs.hal-forms+json

{
  "reason": "Khách hàng yêu cầu hủy"
}
```

Client lấy target, method và content type từ template; body được tạo từ property có tên `reason`. Nếu server trả lỗi validation, client cần hiển thị lỗi tương ứng và cho phép người dùng sửa input. Sau khi thao tác thành công, client nên đọc representation mới để nhận template và link phù hợp với trạng thái đã thay đổi.

## Content negotiation cho HAL-FORMS

Spring HATEOAS cung cấp hằng `MediaTypes.HAL_FORMS_JSON` và `MediaTypes.HAL_FORMS_JSON_VALUE` cho media type `application/prs.hal-forms+json`:

```java
import org.springframework.hateoas.MediaTypes;

@GetMapping(value = "/{id}", produces = MediaTypes.HAL_FORMS_JSON_VALUE)
EntityModel<OrderDto> one(@PathVariable UUID id) {
    return assembler.toModel(service.findById(id));
}
```

Client cần gửi:

```http
Accept: application/prs.hal-forms+json
```

Server phải trả `Content-Type` tương thích với media type này để client biết response có `_templates`. Với Spring Boot, thêm starter HATEOAS và cấu hình hypermedia phù hợp. Nếu bật hỗ trợ thủ công, có thể chọn `HypermediaType.HAL_FORMS` trong `@EnableHypermediaSupport`; tránh đăng ký trùng khi auto-configuration đã đảm nhiệm việc đó.

HAL-FORMS khác HAL JSON thông thường ở media type và metadata template. Nếu client chỉ yêu cầu `application/hal+json`, server không nên âm thầm trả HAL-FORMS document như thể hai định dạng hoàn toàn giống nhau. Hãy khai báo `produces` và kiểm thử negotiation theo hợp đồng.

## Kiểm thử `_templates` bằng MockMvc

Kiểm thử response giúp bảo vệ tên template, method, target và property metadata mà client dựa vào:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderHalFormsTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesDefaultAndCancelTemplates() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "o-42")
                        .accept(MediaTypes.HAL_FORMS_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_FORMS_JSON))
                .andExpect(jsonPath("$._templates.default.method").value("PUT"))
                .andExpect(jsonPath("$._templates.default.contentType")
                        .value("application/json"))
                .andExpect(jsonPath("$._templates.default.properties[0].name")
                        .value("note"))
                .andExpect(jsonPath("$._templates.cancel.method").value("POST"))
                .andExpect(jsonPath("$._templates.cancel.properties[0].name")
                        .value("reason"));
    }
}
```

Fixture cần có đơn hàng `o-42` ở trạng thái cho phép cả hai thao tác. Nếu template được công bố có điều kiện, hãy thêm test cho trạng thái không cho phép hủy và xác nhận `_templates.cancel` không xuất hiện. Cũng nên kiểm thử request gửi theo template thực sự được endpoint chấp nhận, thay vì chỉ kiểm tra metadata.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm `_templates` với `_links` | Client tìm template như một link hoặc không dựng được form. | Đọc template trong `_templates`; dùng `_links` cho điều hướng. |
| Dùng sai media type | Client không nhận diện response là HAL-FORMS. | Dùng `application/prs.hal-forms+json` và hằng `MediaTypes.HAL_FORMS_JSON`. |
| Không đặt tên template rõ ràng | Client khó chọn đúng thao tác khi có nhiều template. | Dùng `default` và tên riêng như `cancel`, `approve`. |
| Metadata property không khớp DTO | Client gửi payload thiếu hoặc sai tên field. | Đồng bộ input type, controller request DTO và kiểm thử JSON. |
| Coi `required` hoặc `regex` là validation bảo mật | Request sai vẫn có thể đến server. | Validate lại ở endpoint bằng Bean Validation và quy tắc nghiệp vụ. |
| Công bố template cho thao tác không khả dụng | Giao diện đưa ra hành động thất bại theo trạng thái hiện tại. | Tạo affordance theo trạng thái và quyền; endpoint vẫn kiểm tra lại. |
| Client tự ghép target | URI sai khi route thay đổi. | Dùng `target` của template hoặc quy tắc target HAL-FORMS. |

## Nguyên tắc thiết kế

- Dùng `_templates` để công bố metadata thao tác có input trong HAL-FORMS.
- Phân biệt template với link điều hướng trong `_links`.
- Dùng tên `default` cho thao tác mặc định và tên riêng cho hành động bổ sung.
- Công bố rõ `method`, `contentType`, `target` và `properties`.
- Dùng `withInput(...)` để mô tả DTO request và kiểm tra property metadata được serialize.
- Chỉ công bố affordance phù hợp với trạng thái và quyền hiện tại.
- Xem property constraints là gợi ý giao diện; server luôn validate request.
- Dùng media type `application/prs.hal-forms+json` và kiểm thử content negotiation.
- Kiểm thử cả metadata template lẫn request thực tế theo template.

`_templates` giúp HAL-FORMS mô tả các thao tác ngay trong representation của resource. Client đọc metadata để dựng giao diện và gửi request đúng method, target, content type cùng input properties. Khi template được đặt tên ổn định và phản ánh đúng khả năng hiện tại, server có thể hướng dẫn client tương tác với API mà không buộc client phải hard-code mọi endpoint và form.
