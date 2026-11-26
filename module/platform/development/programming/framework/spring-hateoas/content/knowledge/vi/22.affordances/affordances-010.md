# Hiển thị affordance cho client

Trong REST API có hypermedia, một link cho client biết có thể điều hướng đến URI nào. **Affordance** bổ sung thông tin về hành động mà resource có thể hỗ trợ, chẳng hạn cập nhật, hủy hoặc xóa; thông tin này có thể bao gồm HTTP method và mô tả dữ liệu đầu vào. Nhờ affordance, client có thể xây dựng giao diện theo khả năng mà server công bố thay vì phải mã hóa cứng mọi hành động theo từng endpoint.

Spring HATEOAS cho phép gắn affordance vào `Link` bằng `afford(...)` và `andAffordance(...)`. Để client nhận được mô tả thao tác có cấu trúc, ứng dụng cần dùng media type hỗ trợ affordance, ví dụ HAL-FORMS (`application/prs.hal-forms+json`). Client đọc link để biết resource, đọc affordance/template để biết thao tác và dữ liệu cần nhập, rồi gửi request theo hợp đồng được công bố.

## 1. Affordance là gì?

Một hypermedia link cơ bản thường có URI `href` và relation `rel`. Ví dụ, relation `self` trỏ đến chính đơn hàng:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/ORD-101"
    }
  }
}
```

Link cho biết địa chỉ của resource. Tuy nhiên, riêng link HAL cơ bản không mô tả đầy đủ client cần gửi HTTP method nào, body có những trường gì hoặc giá trị nào bắt buộc khi muốn cập nhật đơn hàng.

Affordance mô tả một thao tác gắn với resource hoặc link đó. Ví dụ, cùng resource đơn hàng có thể hỗ trợ:

- `PUT` để cập nhật ghi chú đơn hàng.
- `DELETE` để xóa đơn hàng nếu trạng thái cho phép.
- `POST` đến một action endpoint để hủy đơn hàng.

Một affordance có thể cung cấp thông tin về HTTP method, media type của request và các thuộc tính đầu vào. Tập metadata cụ thể phụ thuộc media type và affordance model factory được cấu hình. Client có thể dùng metadata đó để hiển thị form hoặc nút thao tác phù hợp.

## 2. Link và affordance có vai trò khác nhau

| Thành phần | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Link `self` | Resource này ở đâu? | `/orders/ORD-101` |
| Link `items` | Collection dòng hàng ở đâu? | `/orders/ORD-101/items` |
| Affordance `update` | Có thể cập nhật resource bằng cách nào? | `PUT` với payload cập nhật |
| Affordance `delete` | Có thể xóa resource bằng cách nào? | `DELETE` không cần body |

Link là cơ chế điều hướng đến một resource hoặc endpoint. Affordance mô tả một tương tác có thể thực hiện thông qua link. Một link có thể mang nhiều affordance, ví dụ self link của đơn hàng có thể gắn thao tác cập nhật và xóa.

Affordance không tự thực thi hành động, không gửi request thay client và không cấp quyền truy cập. Nó là metadata được server công bố để client hiểu khả năng tương tác tại thời điểm response được tạo.

## 3. Khai báo các thao tác trên controller

Giả sử API quản lý đơn hàng có endpoint đọc, cập nhật và xóa:

```java
import java.util.UUID;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    OrderRepresentation one(@PathVariable("id") UUID id) {
        return orderService.getRepresentation(id);
    }

    @PutMapping("/{id}")
    ResponseEntity<Void> update(
            @PathVariable("id") UUID id,
            @Valid @RequestBody UpdateOrderRequest request) {
        orderService.update(id, request);
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(@PathVariable("id") UUID id) {
        orderService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
```

`UpdateOrderRequest` là kiểu payload mà client gửi khi cập nhật:

```java
public record UpdateOrderRequest(String note) {
}
```

Representation trả về từ handler có thể là DTO riêng:

```java
import java.util.UUID;

public record OrderRepresentation(UUID id, String status) {

    static OrderRepresentation from(Order order) {
        return new OrderRepresentation(order.getId(), order.getStatus().name());
    }
}
```

Mapping của controller cho Spring HATEOAS biết URI, HTTP method và chữ ký handler. Khi tạo affordance, ứng dụng tham chiếu đúng handler để metadata được suy ra từ mapping thay vì tự mô tả lại endpoint bằng chuỗi.

## 4. Gắn affordance vào Link bằng Spring HATEOAS

Có thể gắn affordance của thao tác cập nhật và xóa vào self link của đơn hàng:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderRepresentation> toModel(Order order) {
    Link self = linkTo(methodOn(OrderController.class)
            .one(order.getId()))
            .withSelfRel()
            .andAffordance(afford(methodOn(OrderController.class)
                    .update(order.getId(), null)))
            .andAffordance(afford(methodOn(OrderController.class)
                    .delete(order.getId())));

    return EntityModel.of(OrderRepresentation.from(order), self);
}
```

`methodOn(...)` tạo proxy mô tả lời gọi handler để Spring HATEOAS đọc mapping. Nó không gọi service và không thực hiện thao tác cập nhật hoặc xóa. Đối số `null` ở lời gọi `update(...)` chỉ dùng để tham chiếu chữ ký handler và kiểu request body; không phải payload được gửi đi trong lúc tạo link.

`afford(...)` tạo mô tả thao tác từ handler được tham chiếu. `andAffordance(...)` gắn mô tả đó vào link hiện có. Kết quả là một self link có thể mang nhiều thao tác, trong ví dụ này là `PUT` và `DELETE`.

Nếu chỉ cần link điều hướng mà không cần metadata thao tác, có thể tạo link riêng với relation như `update` hoặc `delete`. Tuy nhiên, relation tùy chỉnh đơn thuần không tự mô tả method và schema đầu vào như affordance.

## 5. Chỉ công bố affordance khi hành động khả dụng

Khả năng thực hiện hành động thường phụ thuộc trạng thái resource và người dùng hiện tại. Ví dụ, đơn hàng ở trạng thái `DRAFT` có thể được cập nhật hoặc xóa, trong khi đơn hàng đã giao không còn hỗ trợ các thao tác đó.

Assembler có thể thêm affordance theo điều kiện:

```java
EntityModel<OrderRepresentation> toModel(Order order) {
    Link self = linkTo(methodOn(OrderController.class)
            .one(order.getId())).withSelfRel();

    if (order.canBeUpdated()) {
        self = self.andAffordance(afford(methodOn(OrderController.class)
                .update(order.getId(), null)));
    }

    if (order.canBeDeleted()) {
        self = self.andAffordance(afford(methodOn(OrderController.class)
                .delete(order.getId())));
    }

    return EntityModel.of(OrderRepresentation.from(order), self);
}
```

Client nhận response có thể hiển thị thao tác tương ứng với affordance được công bố. Nếu server không công bố affordance `delete`, giao diện có thể ẩn nút xóa hoặc đánh dấu thao tác không khả dụng.

Điều kiện trong assembler nên phản ánh trạng thái nghiệp vụ và quyền của người gọi nếu thông tin xác thực có sẵn trong request context. Tuy nhiên, việc không công bố affordance không thay thế authorization. Server phải kiểm tra lại quyền, trạng thái và các ràng buộc nghiệp vụ khi nhận request vì dữ liệu có thể thay đổi sau khi response được gửi.

## 6. Chọn media type có thể biểu diễn affordance

Affordance là mô hình thao tác trong Spring HATEOAS. Cách mô hình này được serialize phụ thuộc media type. HAL cơ bản (`application/hal+json`) tập trung vào link và embedded resource; client HAL thông thường không thể dựa vào cấu trúc HAL cơ bản để đọc đầy đủ HTTP method và form fields của affordance.

HAL-FORMS (`application/prs.hal-forms+json`) bổ sung cấu trúc template cho các thao tác. Một template có thể mô tả:

- Tên hoặc tiêu đề thao tác.
- HTTP method, chẳng hạn `PUT`, `POST` hoặc `DELETE`.
- Content type của payload nếu thao tác có body.
- Các property đầu vào, kiểu dữ liệu, nhãn và yêu cầu bắt buộc khi metadata có thể suy ra.

Client yêu cầu HAL-FORMS bằng content negotiation:

```http
GET /orders/ORD-101 HTTP/1.1
Host: api.example.test
Accept: application/prs.hal-forms+json
```

Server cần có cấu hình serializer/media type HAL-FORMS tương ứng. Trong Spring Boot, starter HATEOAS thường cung cấp cấu hình tự động cho các media type được hỗ trợ. Với cấu hình Spring thuần, có thể bật hỗ trợ HAL-FORMS:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
class HypermediaConfiguration {
}
```

Nếu client yêu cầu `application/hal+json`, response có thể chỉ chứa cấu trúc link HAL cơ bản tùy cấu hình. Client cần yêu cầu và hỗ trợ media type HAL-FORMS nếu muốn hiển thị affordance dưới dạng form template.

## 7. Cấu trúc HAL-FORMS mà client đọc

Một response HAL-FORMS minh họa có thể có dạng:

```json
{
  "id": "ORD-101",
  "status": "DRAFT",
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
          "prompt": "Ghi chú",
          "required": false
        }
      ]
    },
    "delete": {
      "title": "Xóa đơn hàng",
      "method": "DELETE"
    }
  }
}
```

Đây là ví dụ khái niệm để minh họa cách client đọc template; tên template và các trường thực tế được tạo theo affordance model factory và cấu hình của ứng dụng. Không nên hard-code tên `default` hoặc `delete` cho mọi API nếu hợp đồng thực tế sử dụng tên khác.

Client đọc `_links.self.href` để biết resource, sau đó đọc các template trong `_templates`. Với template cập nhật, client có thể dựng form cho property `note`, dùng HTTP method `PUT` và gửi payload theo `contentType`. Với template xóa, client có thể hiển thị hành động xác nhận và gửi `DELETE` đến đích mà template/link xác định theo quy ước HAL-FORMS.

Các template không phải HTML form được nhúng sẵn. Chúng là metadata có cấu trúc để client tự dựng giao diện theo khả năng của nó. Một ứng dụng web có thể tạo textbox, dropdown hoặc nút; một ứng dụng mobile có thể dùng cùng metadata để tạo giao diện native.

## 8. Client nên hiển thị affordance như thế nào?

Client nên xử lý response theo hai bước:

1. Đọc `_links` để nhận diện resource và các URI điều hướng.
2. Đọc affordance/template mà media type cung cấp để xác định thao tác, HTTP method, content type và input properties.

Một client có thể áp dụng quy tắc hiển thị như sau:

| Metadata | Cách hiển thị gợi ý |
| --- | --- |
| Template có `method: PUT` và property `note` | Hiển thị form chỉnh sửa ghi chú và nút lưu |
| Template có `method: DELETE` | Hiển thị nút xóa, thường kèm bước xác nhận |
| Property có `required: true` | Đánh dấu trường bắt buộc và kiểm tra trước khi gửi |
| Property có kiểu hoặc lựa chọn được mô tả | Chọn control phù hợp như input, checkbox hoặc select |
| Không có affordance cho một hành động | Không hiển thị thao tác đó như khả năng hiện tại |

Client không nên suy luận thao tác chỉ từ tên URI hoặc từ việc có link `self`. Nếu API chỉ phát HAL cơ bản mà không có affordance, client có thể cần dựa vào hợp đồng riêng đã biết. Để đạt mức client-driven, nên công bố affordance qua media type mà client hỗ trợ.

## 9. Gửi request từ affordance

Sau khi người dùng nhập dữ liệu, client gửi request với method và content type được template mô tả. Ví dụ minh họa cho thao tác cập nhật:

```http
PUT /orders/ORD-101 HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/prs.hal-forms+json

{
  "note": "Giao hàng sau 17 giờ"
}
```

Với thao tác xóa:

```http
DELETE /orders/ORD-101 HTTP/1.1
Host: api.example.test
Accept: application/prs.hal-forms+json
```

Client cần dùng đích và method theo template/affordance mà server công bố. Không nên tự tạo URL từ ID hoặc ghép path theo quy ước nội bộ nếu response đã cung cấp link đích.

Sau khi gửi request, client nên đọc response mới để cập nhật trạng thái giao diện và khám phá affordance tiếp theo. Ví dụ, sau khi cập nhật thành công, đơn hàng có thể chuyển từ `DRAFT` sang `SUBMITTED`; response mới có thể bỏ affordance cập nhật và công bố affordance theo dõi xử lý.

## 10. Validation và dữ liệu đầu vào

Affordance có thể giúp client hiểu các property đầu vào và một số metadata như kiểu dữ liệu hoặc trường bắt buộc, tùy khả năng mô tả của model factory và media type. Tuy nhiên, metadata hiển thị trên client chỉ hỗ trợ trải nghiệm người dùng.

Server vẫn phải xác thực request body bằng validation và quy tắc nghiệp vụ. Ví dụ:

```java
import jakarta.validation.constraints.Size;

public record UpdateOrderRequest(
        @Size(max = 500) String note) {
}
```

Handler có thể kích hoạt validation:

```java
@PutMapping("/{id}")
ResponseEntity<Void> update(
        @PathVariable UUID id,
        @Valid @RequestBody UpdateOrderRequest request) {
    orderService.update(id, request);
    return ResponseEntity.noContent().build();
}
```

Client có thể dùng metadata để giới hạn độ dài input trước khi gửi, nhưng server phải kiểm tra lại vì request có thể được gửi bởi client khác hoặc bị sửa thủ công. Affordance không thay thế Bean Validation, kiểm tra quyền hoặc quy tắc miền.

## 11. Affordance và bảo mật

Việc công bố affordance nên phù hợp với trạng thái resource và quyền của người gọi. Ví dụ, chỉ người dùng có quyền quản lý đơn hàng mới nhận affordance cập nhật hoặc xóa. Điều này giúp client hiển thị đúng hành động có thể thực hiện trong ngữ cảnh hiện tại.

Tuy nhiên, không được coi affordance là ranh giới bảo mật:

- Client có thể lưu response cũ và sử dụng affordance sau khi quyền đã thay đổi.
- Người dùng có thể tự gửi request đến URI mà họ biết.
- Trạng thái resource có thể đổi giữa thời điểm server tạo affordance và lúc request được gửi.
- Một client có thể bỏ qua giao diện và gọi trực tiếp endpoint.

Do đó, endpoint phải xác thực, phân quyền, kiểm tra trạng thái và xác thực dữ liệu trên mỗi request. Khi điều kiện không còn phù hợp, server trả status code theo hợp đồng, chẳng hạn `403 Forbidden`, `404 Not Found`, `409 Conflict` hoặc lỗi validation tương ứng.

## 12. Kiểm thử affordance trong response

Kiểm thử nên xác nhận controller gắn affordance đúng và response được serialize theo media type mà client yêu cầu. Với Spring MVC và `MockMvc`, có thể kiểm tra HAL-FORMS:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
import java.util.UUID;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderAffordanceTest {

    @Autowired
    MockMvc mockMvc;

    private final UUID draftOrderId = UUID.fromString(
            "a6a1f2b4-1f0d-4a7c-8e12-123456789abc");

    @Test
    void exposesUpdateTemplateForDraftOrder() throws Exception {
        mockMvc.perform(get("/orders/{id}", draftOrderId)
                        .accept(MediaTypes.HAL_FORMS_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._templates.default.method")
                        .value("PUT"));
    }
}
```

`draftOrderId` là fixture hoặc dữ liệu test cần chuẩn bị. Tên template thực tế phụ thuộc cấu hình; nếu ứng dụng đặt tên khác `default`, hãy điều chỉnh JSONPath theo response đã thống nhất. Có thể kiểm tra thêm `contentType` và các property trong template.

Nên có test đối chiếu trạng thái:

- Đơn hàng `DRAFT` có affordance cập nhật nếu nghiệp vụ cho phép.
- Đơn hàng đã giao không có affordance cập nhật hoặc xóa.
- Người dùng không đủ quyền không nhận affordance bị hạn chế, nếu API thiết kế theo quyền người gọi.
- Request thực tế vẫn bị từ chối nếu quyền hoặc trạng thái thay đổi sau khi response được tạo.
- Client yêu cầu HAL cơ bản nhận đúng representation HAL đã định nghĩa; client yêu cầu HAL-FORMS nhận template affordance.
- Template mô tả đúng HTTP method và input content type.

## 13. Lỗi thường gặp

**Nghĩ affordance là một link khác:** affordance mô tả thao tác gắn với link; nó có thể bổ sung method và dữ liệu đầu vào.

**Chỉ dùng HAL cơ bản nhưng mong client đọc được form:** HAL link cơ bản không nhất thiết serialize đầy đủ affordance. Hãy dùng media type hỗ trợ, chẳng hạn HAL-FORMS.

**Hard-code giao diện theo endpoint:** client mất khả năng thích ứng khi server thay đổi khả năng. Hãy đọc template và metadata mà server công bố.

**Cho rằng affordance tự gửi request:** affordance chỉ mô tả. Client vẫn phải tạo và gửi HTTP request.

**Coi affordance là quyền truy cập:** metadata không bảo vệ endpoint. Server phải kiểm tra quyền và trạng thái khi nhận request.

**Không làm mới representation sau thao tác:** affordance có thể thay đổi theo trạng thái. Client nên đọc response mới sau khi hành động thành công.

**Tin metadata validation từ client:** client có thể bỏ qua hoặc sửa form. Server phải xác thực payload bằng validation và quy tắc nghiệp vụ.

## 14. Checklist triển khai

- Xác định các hành động mà resource hỗ trợ trong từng trạng thái.
- Khai báo handler với mapping và request body rõ ràng.
- Tạo link đến resource bằng `linkTo(...)` và `methodOn(...)`.
- Gắn thao tác bằng `afford(...)` và `andAffordance(...)`.
- Chỉ công bố affordance khi phù hợp với trạng thái và quyền hiện tại.
- Chọn media type hỗ trợ affordance, ví dụ HAL-FORMS.
- Cấu hình content negotiation để client yêu cầu media type phù hợp.
- Client đọc `_links` để điều hướng và `_templates` để dựng thao tác.
- Dùng method, content type và input properties theo template khi gửi request.
- Làm mới representation sau khi thao tác hoàn tất.
- Kiểm thử affordance theo trạng thái, quyền, method và payload.
- Luôn xác thực, phân quyền và kiểm tra trạng thái ở server khi nhận request.

Affordance giúp API mô tả khả năng tương tác cùng với resource. Khi Spring HATEOAS gắn affordance vào link và serialize qua HAL-FORMS, client có thể khám phá thao tác, dựng giao diện phù hợp và gửi request theo metadata do server công bố. Server vẫn giữ quyền quyết định cuối cùng bằng cách xác thực dữ liệu, quyền truy cập và trạng thái nghiệp vụ tại thời điểm thực hiện.
