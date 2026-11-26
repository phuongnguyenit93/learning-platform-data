# Link cho PATCH

Trong REST API, **PATCH** được dùng để áp dụng một thay đổi một phần lên tài nguyên. Với Spring HATEOAS, server có thể công bố liên kết đến tài nguyên và mô tả thao tác PATCH mà client được phép thực hiện. Việc tạo một link trỏ đến method có **@PatchMapping** mới chỉ cung cấp URI; để client biết method, kiểu nội dung và dữ liệu đầu vào, API cần công bố thêm affordance bằng một định dạng hypermedia có hỗ trợ mô tả thao tác, chẳng hạn HAL-FORMS.

Một response chi tiết đơn hàng có thể cung cấp self link cùng affordance PATCH khi đơn hàng còn ở trạng thái cho phép chỉnh sửa. Client đọc điều khiển này để biết có thể gửi bản cập nhật một phần đến đâu và cần gửi dữ liệu theo dạng nào. Khi trạng thái thay đổi, server có thể bỏ affordance PATCH khỏi response tiếp theo.

Trong module SPRING_HATEOAS, controller links được tạo từ mapping của controller để tránh hard-code URI. Bài học này tập trung vào cách tạo link cho PATCH, cách mô tả hành động bằng affordance, cách chọn media type cho patch document và cách kiểm thử hợp đồng.

Sau bài học, bạn có thể:

- Phân biệt PATCH với PUT và link URI thông thường.
- Tạo URI đến endpoint @PatchMapping bằng linkTo và methodOn.
- Gắn affordance PATCH vào link bằng afford(...) và andAffordance(...).
- Hiểu vì sao HAL link cơ bản không mô tả HTTP method và body schema.
- Công bố thao tác PATCH qua HAL-FORMS.
- Chọn patch document phù hợp và xử lý khác biệt giữa thuộc tính bị bỏ qua với thuộc tính có giá trị null.
- Chỉ công bố thao tác khi trạng thái và quyền cho phép, đồng thời kiểm thử response.

## PATCH dùng để làm gì?

PUT thường biểu diễn việc thay thế biểu diễn của tài nguyên tại URI đích. PATCH biểu diễn việc áp dụng một tập thay đổi lên tài nguyên hiện tại. PATCH phù hợp khi client chỉ cần thay đổi một vài thuộc tính mà không phải gửi lại toàn bộ tài nguyên.

Ví dụ, đơn hàng có các thuộc tính description, status, deliveryNote và total. Nếu client chỉ muốn cập nhật ghi chú giao hàng, request PATCH có thể chỉ chứa phần thay đổi:

~~~http
PATCH /orders/42 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json

{
  "deliveryNote": "Giao tại quầy lễ tân"
}
~~~

Server áp dụng thay đổi và trả biểu diễn mới hoặc status phù hợp. Các thuộc tính không xuất hiện trong patch document được xử lý theo semantics của media type.

### PATCH và PUT

| Khía cạnh | PUT | PATCH |
| --- | --- | --- |
| Mục đích thường gặp | Thay thế biểu diễn của tài nguyên | Áp dụng thay đổi một phần |
| Nội dung request | Thường gửi biểu diễn đầy đủ theo hợp đồng | Gửi patch document hoặc dữ liệu cập nhật một phần |
| Thuộc tính không gửi | Được xử lý theo quy tắc thay thế của API | Được xử lý theo semantics của patch format |
| Idempotent | Được định nghĩa là idempotent theo HTTP | Không mặc định idempotent; có thể thiết kế thao tác idempotent |
| Media type | Thường là media type của biểu diễn tài nguyên | Có thể là JSON Merge Patch, JSON Patch hoặc định dạng riêng |

Không nên dùng PATCH chỉ vì body ngắn hơn. Hãy xác định rõ ngữ nghĩa cập nhật, đặc biệt là cách xử lý thuộc tính bị bỏ qua, giá trị null, mảng và trường chỉ đọc.

## Tạo link đến endpoint PATCH

Giả sử controller cung cấp endpoint đọc và cập nhật một đơn hàng:

~~~java
@GetMapping("/{id}")
EntityModel<OrderResponse> one(@PathVariable Long id) {
    // ...
}

@PatchMapping("/{id}")
EntityModel<OrderResponse> patch(
        @PathVariable Long id,
        @RequestBody OrderPatchRequest request) {
    // ...
}
~~~

Hai method có cùng URI path nhưng khác HTTP method. linkTo(methodOn(...)) có thể lấy mapping và tham số từ method PATCH để tạo URI:

~~~java
Link patchTarget = linkTo(methodOn(OrderController.class)
    .patch(id, null))
    .withRel("edit");
~~~

Link trên trỏ đến URI của endpoint PATCH và có relation edit. Tuy nhiên, relation edit chỉ mô tả ý nghĩa liên kết; nó không tự nói rằng client phải gửi PATCH, cũng không mô tả body cần gửi. Khi serialize thành HAL JSON cơ bản, client thường chỉ thấy relation và href.

Ví dụ HAL link thông thường:

~~~json
{
  "_links": {
    "edit": {
      "href": "/orders/42"
    }
  }
}
~~~

Client không thể suy ra chắc chắn method từ tên relation edit. Cùng URI có thể hỗ trợ GET, PATCH hoặc DELETE. Nếu API muốn mô tả thao tác PATCH ngay trong response, hãy thêm affordance.

## Affordance mô tả thao tác PATCH

Affordance là mô tả về một khả năng tương tác gắn với link. Nó có thể cho biết method, media type và các thuộc tính đầu vào của thao tác. Spring HATEOAS cho phép tạo affordance từ method của controller.

Các thành phần thường dùng:

- afford(...) tạo mô tả affordance từ method controller.
- andAffordance(...) gắn affordance vào một Link hiện có.
- methodOn(...) mô tả method và tham số cần thiết để Spring HATEOAS suy ra mapping và thông tin đầu vào.

Ví dụ gắn affordance PATCH vào self link:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderResponse> toModel(OrderResponse order) {
    Link self = linkTo(methodOn(OrderController.class)
        .one(order.id()))
        .withSelfRel()
        .andAffordance(afford(methodOn(OrderController.class)
            .patch(order.id(), null)));

    return EntityModel.of(order, self);
}
~~~

Self link vẫn chỉ đến tài nguyên hiện tại. Affordance đính kèm mô tả thêm thao tác PATCH có thể thực hiện trên URI đó. null trong lời gọi mô phỏng là placeholder cho request body; methodOn không gọi endpoint và không gửi body thật.

Có thể gắn nhiều affordance lên cùng một link nếu tài nguyên hỗ trợ nhiều thao tác:

~~~java
Link self = linkTo(methodOn(OrderController.class).one(order.id()))
    .withSelfRel()
    .andAffordance(afford(methodOn(OrderController.class)
        .patch(order.id(), null)))
    .andAffordance(afford(methodOn(OrderController.class)
        .delete(order.id())));
~~~

Trong ví dụ, cùng một URI có thể có các affordance PATCH và DELETE. Mỗi affordance được suy ra từ mapping và chữ ký method tương ứng. Chỉ thêm các affordance thực sự khả dụng trong ngữ cảnh hiện tại.

## Khai báo endpoint PATCH trong controller

Một controller có thể dùng DTO riêng để định nghĩa patch document. Ví dụ sau minh họa hợp đồng cập nhật một phần theo quy tắc của ứng dụng:

~~~java
public record OrderPatchRequest(
    String description,
    String deliveryNote
) {}
~~~

Controller:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    EntityModel<OrderResponse> one(@PathVariable Long id) {
        OrderResponse order = orderService.findById(id)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return toModel(order);
    }

    @PatchMapping(path = "/{id}", consumes = MediaType.APPLICATION_JSON_VALUE)
    EntityModel<OrderResponse> patch(
            @PathVariable Long id,
            @RequestBody OrderPatchRequest request) {
        OrderResponse updated = orderService.patch(id, request);
        return toModel(updated);
    }
}
~~~

Ví dụ giả định OrderService.patch thực hiện kiểm tra nghiệp vụ và trả về DTO đã cập nhật. Ở đây API dùng application/json cho một patch document riêng của ứng dụng. Hợp đồng cần quy định rõ trường nào được phép thay đổi và cách diễn giải giá trị bị bỏ qua hoặc null.

Một DTO Java thông thường có thể không phân biệt được thuộc tính bị bỏ qua với thuộc tính được gửi rõ ràng bằng null: cả hai có thể được deserialize thành null. Nếu API cần phân biệt “không thay đổi” với “xóa giá trị”, hãy dùng kiểu dữ liệu có theo dõi sự hiện diện của thuộc tính hoặc chọn định dạng patch chuẩn có semantics rõ ràng.

### JSON Merge Patch

JSON Merge Patch được định nghĩa bởi RFC 7396 và dùng media type application/merge-patch+json. Các quy tắc quan trọng:

- Thuộc tính không xuất hiện trong patch document giữ nguyên giá trị hiện tại.
- Thuộc tính có giá trị null yêu cầu loại bỏ thuộc tính tương ứng theo semantics merge patch.
- Object lồng nhau được merge đệ quy.
- Mảng được thay thế như một giá trị; merge patch không cập nhật từng phần tử mảng theo chỉ số.

Khai báo endpoint:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

@PatchMapping(
    path = "/{id}",
    consumes = "application/merge-patch+json")
EntityModel<OrderResponse> mergePatch(
        @PathVariable Long id,
        @RequestBody JsonNode patchDocument) {
    OrderResponse updated = orderService.applyMergePatch(id, patchDocument);
    return toModel(updated);
}
~~~

JsonNode cho phép service kiểm tra thuộc tính nào có mặt trong patch document và áp dụng semantics phù hợp. Service cần validate các trường được phép thay đổi, kiểu dữ liệu, giới hạn và quy tắc nghiệp vụ. Không áp dụng patch JSON tùy ý trực tiếp lên JPA entity.

### JSON Patch

JSON Patch được định nghĩa bởi RFC 6902 và dùng media type application/json-patch+json. Body là một mảng các thao tác như add, remove, replace, move, copy và test.

Ví dụ:

~~~http
PATCH /orders/42
Content-Type: application/json-patch+json

[
  { "op": "replace", "path": "/deliveryNote", "value": "Giao tại quầy lễ tân" }
]
~~~

JSON Patch cho phép chỉ rõ đường dẫn và thao tác trên document. Server phải kiểm tra path được phép, kiểu dữ liệu và quyền sửa từng trường. Không cho client sửa các trường nhạy cảm như total, ownerId hoặc status nếu quy trình nghiệp vụ không cho phép.

## Công bố PATCH bằng HAL-FORMS

HAL JSON cơ bản mô tả link qua _links, nhưng không có cấu trúc chuẩn để mô tả đầy đủ method PATCH và các trường request. Nếu client cần khám phá thao tác và form đầu vào, có thể dùng HAL-FORMS (application/prs.hal-forms+json).

Khi controller gắn affordance PATCH vào link, Spring HATEOAS có thể biểu diễn thông tin thao tác thành template HAL-FORMS. Một response minh họa có thể có dạng:

~~~json
{
  "id": 42,
  "description": "Bàn phím cơ",
  "status": "DRAFT",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_templates": {
    "default": {
      "method": "PATCH",
      "contentType": "application/json",
      "properties": [
        {
          "name": "description",
          "required": false
        },
        {
          "name": "deliveryNote",
          "required": false
        }
      ]
    }
  }
}
~~~

Đây là cấu trúc minh họa để thể hiện ý nghĩa của affordance; tên template, tiêu đề và metadata thuộc tính thực tế phụ thuộc relation, chữ ký controller, cấu hình và phiên bản Spring HATEOAS. Hãy kiểm tra response được serialize từ ứng dụng thay vì giả định mọi thuộc tính của DTO đều tự động được mô tả giống nhau.

Client có thể đọc method PATCH, contentType và các property để tạo request. Sau khi nhận template, client gửi request đến URI được liên kết, dùng method và media type được mô tả.

Để nhận HAL-FORMS, client gửi:

~~~http
GET /orders/42 HTTP/1.1
Accept: application/prs.hal-forms+json
~~~

Nếu client chỉ yêu cầu application/hal+json, response HAL cơ bản có thể chỉ chứa link và không biểu diễn affordance dưới dạng form. Vì vậy, hai media type phục vụ hai mức hợp đồng khác nhau:

| Media type | Nội dung chính |
| --- | --- |
| application/hal+json | Tài nguyên, _links và _embedded |
| application/prs.hal-forms+json | HAL cùng các template mô tả thao tác và dữ liệu đầu vào |

## Công bố PATCH theo trạng thái nghiệp vụ

Không phải đơn hàng nào cũng có thể chỉnh sửa. Ví dụ, đơn hàng ở trạng thái DRAFT có thể cho phép thay đổi mô tả và ghi chú giao hàng; đơn hàng đã SHIPPED có thể không còn cho phép các thay đổi này.

Có thể thêm affordance có điều kiện:

~~~java
EntityModel<OrderResponse> toModel(OrderResponse order) {
    Link self = linkTo(methodOn(OrderController.class)
        .one(order.id()))
        .withSelfRel();

    if (order.status() == OrderStatus.DRAFT) {
        self = self.andAffordance(afford(methodOn(OrderController.class)
            .patch(order.id(), null)));
    }

    return EntityModel.of(order, self);
}
~~~

Điều kiện có thể dựa trên:

- Trạng thái hiện tại của tài nguyên.
- Quyền của người dùng đang xác thực.
- Quy tắc tenant hoặc phạm vi sở hữu.
- Thời hạn nghiệp vụ hoặc điều kiện phê duyệt.
- Khả năng của client nếu API có cơ chế thương lượng phù hợp.

Việc không công bố affordance giúp client tránh hiển thị thao tác không khả dụng. Tuy nhiên, affordance không phải cơ chế bảo mật. Client có thể giữ response cũ hoặc tự gửi request đến endpoint; server phải kiểm tra lại quyền và trạng thái trong service khi xử lý PATCH.

## Cập nhật response và các link sau PATCH

Sau khi PATCH thành công, server có thể trả:

- 200 OK cùng representation mới, bao gồm các link và affordance phù hợp với trạng thái mới.
- 204 No Content nếu hợp đồng không yêu cầu trả representation.

Nếu trả representation, nên tạo lại links từ dữ liệu sau cập nhật. Ví dụ, khi đơn hàng chuyển từ DRAFT sang trạng thái không cho chỉnh sửa, affordance PATCH có thể biến mất khỏi response mới.

Không nên trả lại affordance cũ chỉ vì nó có trong request trước đó. Link và affordance cần phản ánh trạng thái hiện tại tại thời điểm tạo response.

## Kiểm soát cập nhật đồng thời bằng ETag

Một client có thể đọc tài nguyên, chờ một thời gian rồi gửi PATCH trong khi người dùng khác đã cập nhật cùng tài nguyên. ETag và điều kiện If-Match giúp tránh ghi đè thay đổi mới hơn.

Ví dụ:

~~~http
GET /orders/42
~~~

Response:

~~~http
HTTP/1.1 200 OK
ETag: "order-42-v7"
Content-Type: application/hal+json
~~~

Client gửi PATCH kèm ETag đã đọc:

~~~http
PATCH /orders/42
If-Match: "order-42-v7"
Content-Type: application/merge-patch+json

{
  "deliveryNote": "Giao tại quầy lễ tân"
}
~~~

Nếu phiên bản tài nguyên đã thay đổi, server có thể trả 412 Precondition Failed. ETag không thay thế validation nghiệp vụ, nhưng giúp phát hiện cập nhật dựa trên phiên bản cũ.

## Kiểm thử link và affordance PATCH

Kiểm thử cần xác minh URI, method và media type được công bố. Với HAL JSON, có thể kiểm tra self link. Với HAL-FORMS, kiểm tra template có method PATCH và các thuộc tính đầu vào phù hợp.

Ví dụ kiểm tra response HAL-FORMS bằng Spring MVC Test:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderPatchAffordanceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void draftOrderAdvertisesPatchTemplate() throws Exception {
        mockMvc.perform(get("/orders/{id}", 42)
                .accept("application/prs.hal-forms+json"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                "application/prs.hal-forms+json"))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._templates.default.method").value("PATCH"));
    }
}
~~~

Test giả định đơn hàng 42 đang ở trạng thái DRAFT, controller công bố affordance trên self link và template được đặt tên default. Nếu cấu hình relation tạo template với tên khác, JSONPath phải khớp với response thực tế.

Kiểm thử request PATCH:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;

@Test
void patchUpdatesAllowedFields() throws Exception {
    mockMvc.perform(patch("/orders/{id}", 42)
            .contentType("application/json")
            .content("{\"deliveryNote\":\"Giao tại quầy lễ tân\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.deliveryNote")
            .value("Giao tại quầy lễ tân"));
}
~~~

Trong test đầy đủ, cần import patch từ MockMvcRequestBuilders và chuẩn bị dữ liệu đơn hàng. Nếu endpoint dùng JSON Merge Patch, đổi contentType thành application/merge-patch+json và kiểm tra semantics null, thuộc tính bị bỏ qua cùng mảng.

Các trường hợp nên kiểm thử:

1. Tài nguyên có thể chỉnh sửa công bố affordance PATCH.
2. Tài nguyên không thể chỉnh sửa không công bố affordance PATCH.
3. HAL-FORMS mô tả đúng method và content type.
4. URI trong link trỏ đến endpoint PATCH phù hợp.
5. PATCH hợp lệ cập nhật đúng các trường được phép.
6. PATCH sai kiểu dữ liệu hoặc vi phạm validation trả lỗi client phù hợp.
7. Người dùng không có quyền bị từ chối dù tự gọi endpoint.
8. ETag cũ với If-Match trả lỗi tiền điều kiện phù hợp.
9. Response sau PATCH phản ánh trạng thái và affordance mới.

## Những sai lầm thường gặp

**Nghĩ link đến @PatchMapping tự cho client biết method PATCH.** HAL link cơ bản chỉ cung cấp relation và URI. Cần affordance cùng media type hỗ trợ mô tả thao tác nếu client cần biết method và body.

**Dùng relation edit như thể đó là HTTP method.** Relation mô tả mục đích liên kết. Method PATCH phải được mô tả riêng trong affordance hoặc hợp đồng media type.

**Nhầm PATCH với PUT.** PATCH áp dụng thay đổi một phần theo patch format; PUT thường thay thế biểu diễn tài nguyên theo hợp đồng.

**Không định nghĩa semantics của null và thuộc tính bị bỏ qua.** Hai trạng thái này có thể bị deserialize thành cùng giá trị trong DTO đơn giản. Chọn patch format và kiểu dữ liệu thể hiện rõ ý nghĩa cần thiết.

**Cho client sửa mọi thuộc tính trong entity.** Chỉ công bố và chấp nhận trường được phép sửa. ID, chủ sở hữu, tổng tiền hoặc trạng thái có thể cần thao tác nghiệp vụ riêng.

**Coi affordance là quyền truy cập.** Affordance chỉ mô tả hành động được công bố tại thời điểm response. Server phải kiểm tra quyền và điều kiện lại khi nhận request.

**Không cập nhật links sau PATCH.** Representation mới phải phản ánh trạng thái mới, kể cả việc affordance không còn khả dụng.

**Bỏ qua cập nhật đồng thời.** Dùng ETag và If-Match khi client cần bảo vệ thay đổi khỏi phiên bản tài nguyên cũ.

## Kết luận

Link đến endpoint PATCH được tạo từ mapping controller bằng linkTo và methodOn, nhưng một HAL link thông thường chỉ cung cấp URI cùng relation. Để mô tả rõ thao tác một phần, Spring HATEOAS cho phép gắn affordance bằng afford(...) và andAffordance(...). HAL-FORMS có thể biểu diễn method PATCH, media type và các thuộc tính đầu vào để client khám phá cách thực hiện thao tác.

Hãy định nghĩa patch document rõ ràng, công bố affordance theo trạng thái và quyền hiện tại, kiểm tra lại điều kiện ở server và tạo response mới sau khi cập nhật. Kiểm thử cả URI, method, media type, validation và các link sau PATCH để hợp đồng hypermedia hỗ trợ client tương tác an toàn.
