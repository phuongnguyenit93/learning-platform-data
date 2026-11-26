# Tài liệu affordance

Affordance mô tả một thao tác mà client có thể thực hiện trên một resource: gửi HTTP method nào, đến URI nào, cần dữ liệu đầu vào gì và kết quả có dạng gì. Khi dùng Spring HATEOAS, tài liệu affordance giúp client hiểu các hành động mà server công bố ngay trong hypermedia representation, thay vì phải suy luận từ tên endpoint hoặc đọc một danh sách route tách rời.

Một link thông thường cho biết nơi điều hướng và ý nghĩa quan hệ (href, rel). Affordance bổ sung mô tả thao tác trên link. Ví dụ, link cancel có thể trỏ đến /orders/42/cancellations; affordance cho biết client gửi POST, body có trường reason và server trả về representation đơn hàng sau khi hủy.

Tài liệu affordance cần mô tả cả ý nghĩa nghiệp vụ, điều kiện xuất hiện, input/output, quyền truy cập và lỗi có thể xảy ra. Spring HATEOAS có thể biểu diễn metadata thao tác bằng HAL-FORMS; tài liệu tĩnh như OpenAPI vẫn hữu ích để mô tả schema, xác thực và quy tắc vận hành rộng hơn.

## 1. Phân biệt link, relation và affordance

Các thành phần này trả lời những câu hỏi khác nhau:

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| href | Client đi đến đâu? | /orders/42/cancellations |
| rel | Link có ý nghĩa gì trong resource hiện tại? | cancel |
| HTTP method | Client thực hiện thao tác bằng cách nào? | POST |
| Input | Client cần gửi dữ liệu nào? | CancelOrderRequest |
| Output | Server có thể trả representation nào? | OrderRepresentation |
| Điều kiện | Khi nào thao tác được công bố hoặc chấp nhận? | Đơn hàng còn PENDING |

Relation cancel là tên quan hệ hypermedia, không phải HTTP method. Chỉ nhìn relation không đủ để kết luận client phải gửi POST, DELETE hay PATCH. Affordance mô tả method và metadata cần thiết cho thao tác.

Một API có thể có link điều hướng mà không có affordance, ví dụ link self hoặc link đến trang trợ giúp. Ngược lại, một link có thể mang nhiều affordance nếu cùng một URI hỗ trợ nhiều thao tác HTTP.

## 2. Những gì cần ghi trong tài liệu affordance

Với mỗi hành động nghiệp vụ được công bố, tài liệu nên trả lời:

- **Tên relation:** tên chuẩn mà client dùng để tìm link.
- **Ý nghĩa:** thao tác làm gì trong ngôn ngữ nghiệp vụ.
- **Đích:** link href do server cung cấp; không yêu cầu client tự ghép URL.
- **Method và media type:** POST, PUT, PATCH hoặc method khác; kiểu dữ liệu request được chấp nhận.
- **Input:** field, kiểu dữ liệu, field bắt buộc/tùy chọn, giới hạn và quy tắc validation.
- **Output:** status code, response media type và representation có thể nhận.
- **Điều kiện khả dụng:** trạng thái resource, quyền caller hoặc điều kiện nghiệp vụ.
- **Lỗi:** các status code và tình huống nghiệp vụ có thể xảy ra.
- **Tính lặp an toàn:** request có idempotent không; client có thể retry trong trường hợp nào.
- **Phiên bản:** cách thay đổi contract mà không làm client cũ hỏng.

Ví dụ bảng mô tả action cancel:

| Thuộc tính | Contract |
| --- | --- |
| Relation | acme:cancel |
| Ý nghĩa | Hủy đơn hàng chưa được xử lý |
| Method | POST |
| Request media type | application/json |
| Input | reason: string, bắt buộc |
| Success | 200 OK với đơn hàng đã cập nhật hoặc 204 No Content theo contract |
| Điều kiện | Caller có quyền hủy; đơn hàng ở trạng thái PENDING |
| Lỗi | 400, 401, 403, 404, 409, 412 tùy điều kiện |
| Retry | Cần chính sách idempotency nếu client có thể gửi lại command |

Tài liệu phải phản ánh đúng contract thực tế. Nếu endpoint trả 202 Accepted và xử lý bất đồng bộ, không mô tả như thể response luôn chứa đơn hàng đã hủy hoàn tất.

## 3. Khai báo command và request DTO

Giả sử API có hành động hủy đơn hàng:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CancelOrderRequest(
        @NotBlank
        @Size(max = 250)
        String reason) {
}
~~~

DTO thể hiện các ràng buộc mà server thực sự kiểm tra. Nếu dùng Bean Validation, controller cần kích hoạt validation bằng @Valid:

~~~java
import java.util.UUID;

import jakarta.validation.Valid;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderCommandController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderCommandController(
            OrderService orderService,
            OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @PostMapping(
            value = "/orders/{id}/cancellations",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = "application/hal+json")
    EntityModel<OrderRepresentation> cancel(
            @PathVariable UUID id,
            @Valid @RequestBody CancelOrderRequest request) {

        Order updated = orderService.cancel(id, request);
        return assembler.toModel(updated);
    }
}
~~~

Các kiểu OrderService, Order, OrderRepresentation và OrderModelAssembler là contract domain minh họa. Trong dự án thực tế, dùng service và DTO của ứng dụng. Điều quan trọng là request DTO, validation annotation và mapping controller phải thống nhất với nội dung tài liệu.

## 4. Gắn affordance vào link bằng Spring HATEOAS

Spring HATEOAS cho phép tạo affordance từ method controller. Cách này giúp metadata thao tác gắn với handler thực tế:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler {

    EntityModel<OrderRepresentation> toModel(Order order) {
        var self = linkTo(methodOn(OrderController.class)
                .one(order.id()))
                .withSelfRel();

        var cancel = linkTo(methodOn(OrderCommandController.class)
                .cancel(order.id(), null))
                .withRel(OrderRelations.CANCEL)
                .andAffordance(afford(methodOn(OrderCommandController.class)
                        .cancel(order.id(), null)));

        return EntityModel.of(
                OrderRepresentation.from(order),
                self,
                cancel);
    }
}
~~~

methodOn(...) mô tả method controller mà link builder cần tham chiếu; proxy không thực thi body handler. afford(...) tạo metadata cho thao tác cancel(...), còn andAffordance(...) gắn thao tác đó với link relation cancel. Tham số null cho request body là placeholder để xác định chữ ký method, không phải body client sẽ gửi.

Nếu action có relation riêng và URI riêng, tạo link cho relation đó rồi gắn affordance:

~~~java
var cancel = linkTo(methodOn(OrderCommandController.class)
        .cancel(order.id(), null))
        .withRel(OrderRelations.CANCEL)
        .andAffordance(afford(methodOn(OrderCommandController.class)
                .cancel(order.id(), null)));

// model là EntityModel đã được tạo trong assembler.
model.add(cancel);
~~~

Không tạo affordance cho một handler chỉ vì handler tồn tại. Chỉ công bố thao tác khi resource hiện tại và caller thực sự có thể thực hiện nó. Server vẫn phải kiểm tra quyền và trạng thái trong command endpoint.

## 5. HAL và giới hạn của link thông thường

HAL biểu diễn link bằng href và relation:

~~~json
{
  "_links": {
    "curies": [
      {
        "name": "acme",
        "href": "https://api.example.test/rels/{rel}",
        "templated": true
      }
    ],
    "self": {
      "href": "/orders/42"
    },
    "acme:cancel": {
      "href": "/orders/42/cancellations"
    }
  }
}
~~~

HAL cơ bản không mô tả đầy đủ method, request body và field của một form. Client có thể biết nơi cancel trỏ đến, nhưng không thể suy ra chắc chắn request cần POST với JSON body chỉ từ link.

Vì vậy, nếu client cần khám phá thao tác và input một cách máy đọc được, hãy dùng media type hỗ trợ affordance như HAL-FORMS. Nếu API chỉ cần cung cấp khả năng điều hướng, link HAL thông thường có thể đủ; phần method/input có thể được mô tả thêm trong tài liệu API tĩnh.

## 6. HAL-FORMS mô tả thao tác như thế nào?

HAL-FORMS bổ sung _templates vào representation. Template mô tả method, content type và danh sách property client có thể gửi:

~~~json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "curies": [
      {
        "name": "acme",
        "href": "https://api.example.test/rels/{rel}",
        "templated": true
      }
    ],
    "self": {
      "href": "/orders/42"
    },
    "acme:cancel": {
      "href": "/orders/42/cancellations"
    }
  },
  "_templates": {
    "cancel": {
      "title": "Cancel order",
      "method": "POST",
      "contentType": "application/json",
      "properties": [
        {
          "name": "reason",
          "prompt": "Reason for cancellation",
          "required": true,
          "type": "text"
        }
      ]
    }
  }
}
~~~

Đây là ví dụ minh họa contract HAL-FORMS. Tên template, property và metadata thực tế được tạo từ affordance model cùng cấu hình serializer. Hãy kiểm tra JSON thực tế của ứng dụng trước khi ghi cố định JSONPath hoặc tên template trong tài liệu client.

Các thuộc tính template thường có thể mô tả:

- method: HTTP method client gửi.
- contentType: media type của request body.
- properties: các field đầu vào.
- name: tên field trong request.
- prompt: nhãn gợi ý cho giao diện client.
- required: field có bắt buộc hay không.
- readOnly: field chỉ để hiển thị, không nhập.
- type: kiểu điều khiển hoặc dữ liệu mà client có thể dùng.
- value, min, max, regex: giá trị hoặc ràng buộc nếu serializer và contract cung cấp.

Không phải mọi quy tắc nghiệp vụ đều có thể biểu diễn bằng metadata form. Ví dụ, việc một đơn hàng chỉ hủy được trước khi đóng gói vẫn cần mô tả trong tài liệu nghiệp vụ và được server xác minh ở thời điểm nhận request.

## 7. Yêu cầu HAL-FORMS từ Spring MVC

Controller có thể công bố HAL và HAL-FORMS như các response media type được hỗ trợ:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/orders/{id}", produces = {
            MediaTypes.HAL_JSON_VALUE,
            MediaTypes.HAL_FORMS_JSON_VALUE
    })
    EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }
}
~~~

Client yêu cầu:

~~~http
GET /orders/42 HTTP/1.1
Accept: application/prs.hal-forms+json
~~~

Server trả HAL-FORMS representation nếu converter và cấu hình media type đã được đăng ký. Nếu client yêu cầu HAL JSON, server có thể trả representation HAL cơ bản theo content negotiation.

Khi viết tài liệu, ghi rõ media type mà client cần gửi. Đừng mô tả _templates như một phần luôn tồn tại trong mọi HAL response.

## 8. Document relation và CURIE

Relation là vocabulary mà client dùng để tìm hành động. Relation chuẩn đã có semantics được định nghĩa rộng rãi; relation riêng của domain nên có URI ổn định và tài liệu giải thích ý nghĩa.

Ví dụ khai báo custom relation:

~~~java
import org.springframework.hateoas.LinkRelation;

final class OrderRelations {

    static final LinkRelation CANCEL =
            LinkRelation.of("https://api.example.test/rels/cancel");

    private OrderRelations() {
    }
}
~~~

Trong HAL, CURIE có thể rút gọn extension relation:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
class HalConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
                "acme",
                UriTemplate.of("https://api.example.test/rels/{rel}"));
    }
}
~~~

Với cấu hình trên, client có thể thấy relation acme:cancel, đồng thời dùng CURIE link để mở rộng prefix thành URI relation đầy đủ. Tài liệu nên ghi cả tên rút gọn mà client thấy và URI relation chuẩn, kèm semantics của relation. Không đổi nghĩa một relation đã công bố chỉ vì implementation route thay đổi.

## 9. Điều kiện xuất hiện và vòng đời affordance

Affordance có thể xuất hiện hoặc biến mất theo trạng thái resource và quyền caller. Ví dụ:

| Trạng thái đơn hàng | Link/affordance được công bố |
| --- | --- |
| PENDING và caller có quyền | cancel |
| PENDING nhưng caller không có quyền | Không có cancel |
| PAID | Có thể có create-shipment |
| SHIPPED | Không còn cancel; có thể có track |
| CANCELLED | Không có cancel hoặc create-shipment |

Tài liệu phải giải thích điều kiện xuất hiện của từng affordance. Client cần hiểu rằng absence của link có thể là một trạng thái hợp lệ, không nhất thiết là lỗi server.

Việc link biến mất không thay thế authorization. Client có thể giữ URL cũ hoặc tự tạo request; server phải xác minh quyền và điều kiện domain ở mọi command endpoint. Nếu trạng thái thay đổi giữa lúc client đọc representation và gửi command, server có thể trả 409 Conflict hoặc 412 Precondition Failed theo contract.

## 10. Mô tả input và output chính xác

Đối với từng affordance, tài liệu cần chỉ ra request schema:

~~~json
{
  "reason": "Customer requested cancellation"
}
~~~

Và response có thể có:

~~~json
{
  "id": "42",
  "status": "CANCELLED",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  }
}
~~~

Tài liệu nên nêu rõ:

- Field nào bắt buộc và field nào tùy chọn.
- Kiểu dữ liệu, độ dài, miền giá trị và format.
- Quy tắc validation và lỗi tương ứng.
- Response status code cho thành công và lỗi.
- Response media type.
- Link/affordance nào có thể xuất hiện trong representation tiếp theo.

Đừng sao chép một JSON mẫu mà không nói rõ field nào là ví dụ, field nào bắt buộc. Với enum hoặc giá trị có tập lựa chọn, mô tả tập giá trị và ý nghĩa từng giá trị.

## 11. OpenAPI và tài liệu hypermedia bổ sung cho nhau

OpenAPI phù hợp để công bố tài liệu tĩnh cho endpoint, request/response schema, security scheme, status code và ví dụ. Hypermedia affordance là contract runtime: server gửi khả năng hiện tại cùng representation của resource.

| Tài liệu tĩnh (OpenAPI) | Affordance runtime |
| --- | --- |
| Liệt kê operation và schema tổng quát | Cho biết thao tác hiện khả dụng trên resource cụ thể |
| Mô tả authentication scheme và response code | Client khám phá link theo trạng thái hiện tại |
| Hữu ích cho code generation, lint và contract review | Hữu ích cho client điều hướng theo hypermedia |
| Thường được xuất bản ngoài response nghiệp vụ | Đi cùng HAL/HAL-FORMS representation |

Không nên coi một trong hai là bản thay thế hoàn toàn cho bên còn lại. OpenAPI có thể mô tả tổng thể API; affordance cho biết action nào server đang công bố trong ngữ cảnh resource hiện tại. Nếu duy trì cả hai, cần quy trình kiểm tra để tránh schema tĩnh khác với request DTO hoặc controller mapping thực tế.

Đặc biệt, không tuyên bố rằng mọi affordance tự động sinh ra một OpenAPI document đầy đủ. Affordance metadata và OpenAPI có mục đích, cấu trúc và mức chi tiết khác nhau; việc đồng bộ chúng cần tooling hoặc quy trình riêng.

## 12. Ví dụ tài liệu action cho client

Một đoạn tài liệu ngắn có thể mô tả cách client thực hiện action:

~~~text
Relation: acme:cancel
Ý nghĩa: Hủy đơn hàng đang chờ xử lý.
Khả dụng khi: Caller có quyền ORDER_CANCEL và status = PENDING.
Đích: Dùng href trong link acme:cancel của representation hiện tại.
Method: POST
Content-Type: application/json
Input:
  reason: string, bắt buộc, tối đa 250 ký tự.
Thành công:
  200 OK, trả OrderRepresentation mới.
Lỗi:
  400: request không hợp lệ.
  401: caller chưa xác thực.
  403: caller không có quyền.
  404: đơn hàng không tồn tại hoặc không hiển thị.
  409: trạng thái hiện tại không cho phép hủy.
~~~

Client không lấy path /orders/{id}/cancellations từ tài liệu rồi tự ghép ID. Nó tìm relation acme:cancel, đọc href, method và input metadata trong affordance, sau đó gửi request đến đúng đích. Điều này cho phép server đổi route mà không bắt client phụ thuộc vào cấu trúc URI cũ.

## 13. Kiểm thử tài liệu affordance bằng MockMvc

Tài liệu phải khớp representation thực tế. Test có thể kiểm tra response HAL-FORMS chứa link và template:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderAffordanceDocumentationTest {

    private static final UUID ORDER_ID =
            UUID.fromString("a6a1f2b4-1f0d-4a7c-8e12-123456789abc");

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void publishesCancelAffordanceForPendingOrder() throws Exception {
        given(orderService.getRequired(ORDER_ID))
                .willReturn(OrderFixtures.pending(ORDER_ID));

        mockMvc.perform(get("/orders/{id}", ORDER_ID)
                        .accept(MediaTypes.HAL_FORMS_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_FORMS_JSON))
                .andExpect(jsonPath("$._links['acme:cancel'].href").exists())
                .andExpect(jsonPath("$._templates").exists());
    }
}
~~~

OrderFixtures, OrderService và OrderModelAssembler là thành phần test minh họa. Cần cấu hình CurieProvider nếu test dùng relation acme:cancel. Tên template và cấu trúc property nên được xác nhận từ JSON thực tế của ứng dụng trước khi viết assertion chi tiết.

Ví dụ dùng MockitoBean của Spring Framework 6.2 trở lên. Với Spring Boot/Spring Framework cũ hơn, thay bằng MockBean theo phiên bản dự án. Các import của OrderService và OrderFixtures thuộc package ứng dụng nên được bổ sung theo source thực tế.

Có thể kiểm tra sâu hơn method và input property khi contract serializer đã ổn định:

~~~java
.andExpect(jsonPath("$._templates.cancel.method").value("POST"))
.andExpect(jsonPath("$._templates.cancel.contentType")
        .value("application/json"))
.andExpect(jsonPath("$._templates.cancel.properties[?(@.name == 'reason')]")
        .exists());
~~~

Đường dẫn _templates.cancel ở trên chỉ là ví dụ. Nếu HAL-FORMS serializer đặt template dưới default hoặc tên khác, cập nhật assertion theo contract thực tế thay vì giả định mọi phiên bản đều sinh cùng một key.

Test cần có thêm trường hợp affordance không xuất hiện khi đơn hàng không còn PENDING hoặc caller không đủ quyền. Ngoài ra, gửi request trực tiếp đến command endpoint với caller không có quyền để xác nhận server vẫn từ chối request.

## 14. Kiểm tra contract giữa DTO, controller và tài liệu

Một thay đổi ở request DTO có thể làm tài liệu cũ sai dù route không đổi. Ví dụ đổi reason thành cancellationReason, giảm giới hạn độ dài hoặc biến field tùy chọn thành bắt buộc sẽ ảnh hưởng client.

Trong review, đối chiếu:

| Nguồn | Điều cần kiểm tra |
| --- | --- |
| Controller mapping | HTTP method, path, consumes, produces |
| Request DTO | Field, type, validation và nullability |
| Response DTO | Field và representation được trả |
| Affordance | Link relation, method và metadata input/output |
| OpenAPI/tài liệu | Schema, status code, security và ví dụ |
| Tests | JSON HAL/HAL-FORMS thực tế và các trạng thái khả dụng |

Nên có contract test cho các relation quan trọng và review thay đổi DTO/controller cùng với tài liệu. Nếu một relation bị đổi tên hoặc xóa, xem đó là thay đổi contract cần kế hoạch tương thích, không phải refactor nội bộ đơn thuần.

## 15. Versioning và deprecation

Relation URI nên ổn định theo thời gian. Nếu semantics của action thay đổi đáng kể, hãy tạo relation mới hoặc version semantics rõ ràng thay vì âm thầm đổi nghĩa relation cũ.

Khi ngừng hỗ trợ affordance:

1. Ngừng công bố affordance mới trong các trạng thái phù hợp.
2. Tài liệu hóa thời điểm và điều kiện deprecation.
3. Nếu cần, giữ endpoint cũ trong giai đoạn chuyển tiếp.
4. Trả lỗi có cấu trúc và hướng dẫn chuyển đổi khi client gọi action đã ngừng.
5. Xóa relation cũ sau khi thời hạn tương thích kết thúc.

Không để client phụ thuộc vào vị trí hoặc thứ tự link trong JSON. Client phải tìm bằng relation và xử lý trường hợp affordance không xuất hiện.

## 16. Lỗi thường gặp

**Chỉ ghi tên relation mà không ghi semantics:** client không hiểu hành động làm gì. Tài liệu hóa ý nghĩa nghiệp vụ và điều kiện khả dụng.

**Nhầm relation với HTTP method:** relation cancel không tự nói rằng request dùng POST. Mô tả method trong affordance.

**Dùng HAL cơ bản nhưng kỳ vọng form metadata:** HAL link không chứa đầy đủ method/input. Dùng HAL-FORMS khi client cần khám phá form.

**Tài liệu input khác request DTO:** client gửi field không được server nhận. Đồng bộ DTO, validation, affordance và tài liệu.

**Giả định template key cố định:** serializer có thể đặt tên template khác theo affordance model. Kiểm tra response thực tế.

**Coi affordance là quyền truy cập:** client vẫn có thể gọi URL cũ. Authorization phải được kiểm tra ở server.

**Bỏ qua trạng thái resource:** tài liệu khiến client nghĩ action luôn khả dụng. Mô tả rõ điều kiện xuất hiện và trạng thái chuyển tiếp.

**Cho rằng affordance tự sinh OpenAPI hoàn chỉnh:** hai contract có mục tiêu khác nhau. Duy trì và kiểm thử tính nhất quán giữa chúng.

## 17. Checklist tài liệu affordance

- Relation có semantics ổn định và được tài liệu hóa.
- Link cung cấp href để client dùng trực tiếp.
- Affordance công bố đúng HTTP method.
- Request media type và input property khớp DTO/controller.
- Output media type, response schema và status code được mô tả.
- Điều kiện theo trạng thái và quyền caller được nêu rõ.
- Các lỗi nghiệp vụ và chính sách retry được ghi lại.
- HAL-FORMS được dùng khi client cần method/input metadata.
- Custom relation có URI ổn định và CURIE khi phù hợp.
- OpenAPI bổ sung schema và contract tĩnh; không bị nhầm với runtime affordance.
- MockMvc test xác nhận link/template thực tế.
- Test xác nhận affordance biến mất khi action không còn khả dụng.
- Thay đổi relation, DTO hoặc method có quy trình versioning/deprecation.

Tài liệu affordance là phần giải thích có cấu trúc cho những hành động mà API công bố qua hypermedia. Khi relation, method, input, output và điều kiện khả dụng được mô tả nhất quán với controller cùng HAL-FORMS response, client có thể khám phá và thực hiện quy trình nghiệp vụ mà không phụ thuộc vào route hard-code. OpenAPI và tài liệu nghiệp vụ tiếp tục bổ sung những thông tin tổng quát mà runtime affordance không nhằm thay thế.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [Spring HATEOAS Reference – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
- [HAL-FORMS Specification](https://rwcbook.github.io/hal-forms/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
