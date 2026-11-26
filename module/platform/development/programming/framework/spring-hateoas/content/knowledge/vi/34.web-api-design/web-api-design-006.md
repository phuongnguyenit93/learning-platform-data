# Action bằng link

Trong REST API dùng hypermedia, client nên khám phá những hành động có thể thực hiện từ representation mà server trả về. Một đơn hàng đang chờ thanh toán có thể cung cấp link để thanh toán hoặc hủy; sau khi đã thanh toán, link thanh toán biến mất và có thể xuất hiện link tạo lệnh giao hàng. Client dựa vào các link và metadata đi kèm để biết bước tiếp theo, thay vì tự suy luận từ trạng thái hoặc ghép URL theo quy ước nội bộ.

Spring HATEOAS hỗ trợ cách thiết kế này bằng `Link`, link relation và `Affordance`. Link chỉ ra đích điều hướng và ý nghĩa quan hệ; affordance mô tả thao tác có thể thực hiện trên đích, chẳng hạn HTTP method, kiểu dữ liệu đầu vào và đầu ra. Khi serialize bằng media type phù hợp như HAL-FORMS, API có thể công bố các thao tác đó cho client.

## 1. Hypermedia control là gì?

Hypermedia control là thông tin trong representation cho phép client khám phá và thực hiện một bước tiếp theo. Nó thường bao gồm:

- URI đích (`href`) để client điều hướng hoặc gửi request.
- Relation (`rel`) mô tả ý nghĩa của link đối với resource hiện tại.
- Affordance mô tả thao tác được hỗ trợ, ví dụ `GET`, `POST`, `PUT`, `PATCH` hoặc `DELETE`.
- Metadata về input/output khi thao tác cần dữ liệu hoặc trả về một representation cụ thể.

Ví dụ, một đơn hàng đang chờ xử lý có thể công bố:

```json
{
  "id": "ORD-1042",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/ORD-1042"
    },
    "cancel": {
      "href": "https://api.example.test/orders/ORD-1042/cancellations"
    },
    "payment": {
      "href": "https://api.example.test/orders/ORD-1042/payments"
    }
  }
}
```

Các link gợi ý rằng client có thể xem đơn hàng, bắt đầu quy trình hủy hoặc thanh toán. Tuy nhiên, chỉ có `href` và `rel` chưa đủ để mô tả một request `POST` có body. Nếu client cần biết method và input, server phải công bố affordance bằng media type có hỗ trợ metadata đó.

## 2. Phân biệt link relation và affordance

Hai khái niệm này bổ sung cho nhau:

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| `href` | Gửi request hoặc điều hướng đến đâu? | `/orders/ORD-1042/cancellations` |
| `rel` | Link này có ý nghĩa gì trong ngữ cảnh hiện tại? | `cancel` |
| Affordance | Có thể thực hiện thao tác nào trên link? | `POST` |
| Input metadata | Cần gửi dữ liệu gì? | `CancelOrderRequest` |
| Output metadata | Kết quả có dạng gì? | `OrderRepresentation` |

Relation không phải HTTP method. Relation `cancel` không tự nói rằng client phải gửi `POST`, `DELETE` hay `PATCH`. Tương tự, một link `self` không có nghĩa rằng resource chỉ hỗ trợ đọc; cùng URI có thể hỗ trợ nhiều method khác nhau. Affordance mô tả những thao tác được công bố trên link.

Nếu client chỉ cần điều hướng đến một trang hoặc resource có thể đọc, link thông thường có thể đủ. Nếu client cần thực hiện một thao tác thay đổi trạng thái, hãy mô tả method và dữ liệu đầu vào bằng affordance.

## 3. Thiết kế endpoint cho hành động nghiệp vụ

Giả sử hệ thống quản lý đơn hàng có các thao tác:

| Hành động | Điều kiện ví dụ | HTTP method | Endpoint ví dụ |
| --- | --- | --- | --- |
| Xem đơn hàng | Đơn hàng tồn tại và caller có quyền đọc | GET | `/orders/{id}` |
| Hủy đơn hàng | Đơn hàng còn ở trạng thái PENDING | POST | `/orders/{id}/cancellations` |
| Thanh toán | Đơn hàng chưa thanh toán | POST | `/orders/{id}/payments` |
| Xác nhận giao hàng | Đơn hàng đã thanh toán và chưa giao | POST | `/orders/{id}/shipments` |

Các endpoint hành động có thể được thiết kế như resource con đại diện cho quy trình hoặc kết quả nghiệp vụ. Ví dụ `POST /orders/{id}/cancellations` yêu cầu server bắt đầu quy trình hủy đơn. Cách đặt URI cụ thể phụ thuộc domain; điều quan trọng là method và semantics phải rõ ràng, nhất quán.

Không biến mọi hành động thành endpoint kiểu RPC như `/doCancelOrder` hoặc `/executePayment` nếu một resource/action URI có ngữ nghĩa HTTP rõ hơn. Tên route không thay thế semantics của HTTP method và hợp đồng hypermedia.

## 4. Khai báo request và controller

Request hủy đơn có thể chứa lý do:

```java
import java.util.UUID;

public record CancelOrderRequest(String reason) {
}

enum OrderStatus {
    PENDING, PAID, SHIPPED, CANCELLED
}

record Order(UUID id, OrderStatus status, UUID customerId) {
}

record OrderRepresentation(UUID id, String status, UUID customerId) {

    static OrderRepresentation from(Order order) {
        return new OrderRepresentation(
                order.id(), order.status().name(), order.customerId());
    }
}

interface OrderService {
    Order getRequired(UUID id);
    Order cancel(UUID id, CancelOrderRequest request);
}
```

Các kiểu trên là domain và DTO rút gọn để minh họa. Trong ứng dụng thực tế, dùng model và request validation của domain đang có.

Controller công bố endpoint hủy đơn bằng `POST`:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderCommandController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;

    OrderCommandController(
            OrderService orderService,
            OrderModelAssembler orderAssembler) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
    }

    @PostMapping(value = "/{id}/cancellations",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = {"application/hal+json", "application/prs.hal-forms+json"})
    EntityModel<OrderRepresentation> cancel(
            @PathVariable("id") UUID id,
            @RequestBody CancelOrderRequest request) {

        Order cancelled = orderService.cancel(id, request);
        return orderAssembler.toModel(cancelled);
    }
}
```

`OrderService` chịu trách nhiệm kiểm tra trạng thái và thực hiện quy tắc nghiệp vụ. Controller chỉ chuyển request đến service rồi tạo representation kết quả. Việc công bố link hủy trong response không thay thế bước kiểm tra điều kiện ở service.

## 5. Tạo action link bằng WebMvcLinkBuilder

Spring HATEOAS có thể tạo URI từ mapping controller bằng `linkTo(...)` và `methodOn(...)`. Khi link trỏ đến một handler có method khác GET, thêm affordance để mô tả thao tác đó:

```java
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link cancelLink(UUID orderId) {
    return linkTo(methodOn(OrderCommandController.class)
            .cancel(orderId, null))
            .withRel("cancel")
            .andAffordance(afford(methodOn(OrderCommandController.class)
                    .cancel(orderId, null)));
}
```

`methodOn(...)` tham chiếu đúng handler để Spring HATEOAS suy ra URI từ mapping. `withRel("cancel")` gắn relation nghiệp vụ; `afford(...)` mô tả thao tác được ánh xạ bởi method `cancel(...)`. Tham số body `null` chỉ là placeholder để link builder đọc chữ ký handler; client sẽ gửi request body thực tế khi thực hiện affordance.

Trong API lớn, hãy tập trung tên relation thành vocabulary được tài liệu hóa. Nếu `cancel` là custom relation công khai, cần giữ ngữ nghĩa ổn định và có thể dùng CURIE namespace trong HAL để tránh xung đột.

Trong ví dụ, `cancel` là tên relation rút gọn cho dễ đọc. Với extension relation công khai, nên định danh bằng URI ổn định theo quy ước Web Linking và dùng CURIE để biểu diễn gọn trong HAL khi cần.

## 6. Chỉ công bố hành động hợp lệ theo trạng thái

Một điểm mạnh của hypermedia là representation có thể thay đổi tập hành động theo trạng thái domain. Assembler có thể thêm hoặc bỏ link tùy điều kiện:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler {

    EntityModel<OrderRepresentation> toModel(Order order) {
        EntityModel<OrderRepresentation> model = EntityModel.of(
                OrderRepresentation.from(order),
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel());

        if (order.status() == OrderStatus.PENDING) {
            model.add(linkTo(methodOn(OrderCommandController.class)
                    .cancel(order.id(), null))
                    .withRel("cancel")
                    .andAffordance(afford(methodOn(OrderCommandController.class)
                            .cancel(order.id(), null))));
        }

        if (order.status() == OrderStatus.PENDING) {
            model.add(linkTo(methodOn(PaymentController.class)
                    .pay(order.id(), null))
                    .withRel("payment")
                    .andAffordance(afford(methodOn(PaymentController.class)
                            .pay(order.id(), null))));
        }

        if (order.status() == OrderStatus.PAID) {
            model.add(linkTo(methodOn(ShipmentController.class)
                    .create(order.id(), null))
                    .withRel("create-shipment")
                    .andAffordance(afford(methodOn(ShipmentController.class)
                            .create(order.id(), null))));
        }

        return model;
    }
}
```

Ví dụ minh họa ba trạng thái và các controller command tương ứng. `OrderController.one(UUID)`, `OrderCommandController`, `PaymentController.pay(...)` và `ShipmentController.create(...)` là các handler giả định; `Order`, `OrderStatus` và `OrderRepresentation.from(...)` là kiểu domain/DTO rút gọn đã khai báo ở phần trước. Trong dự án thực tế, thay bằng enum, DTO và handler thật.

Client nhận representation của đơn hàng `PENDING` sẽ thấy link `cancel` và `payment`. Khi đơn hàng chuyển sang `PAID`, response mới không còn hai link đó và công bố `create-shipment`. Client không cần tự mã hóa toàn bộ state machine trong ứng dụng để biết thao tác nào server đang công bố.

Việc ẩn link không phải cơ chế phân quyền. Server vẫn phải xác thực caller, kiểm tra quyền và trạng thái ở mỗi request, vì client có thể giữ URL cũ hoặc tự gửi request trực tiếp.

## 7. Công bố method và input bằng affordance

Affordance có thể được tạo trực tiếp từ method controller như ví dụ trên. Cách này giúp Spring HATEOAS đọc metadata từ mapping và chữ ký handler, bao gồm method HTTP, request body và kiểu response.

Khi cần xây dựng affordance thủ công, có thể bắt đầu từ một link rồi mô tả method, input và output:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.http.HttpMethod;

Link cancelLinkWithAffordance(Link cancelLink) {
    return Affordances.of(cancelLink)
            .afford(HttpMethod.POST)
            .withInput(CancelOrderRequest.class)
            .withOutput(OrderRepresentation.class)
            .withName("cancel")
            .toLink();
}
```

Tên và cách serialize affordance phụ thuộc media type. Dùng cách tạo affordance từ controller method khi có thể để metadata nhất quán với mapping thực tế; cách thủ công hữu ích khi endpoint hoặc contract được mô tả ở một abstraction khác.

## 8. HAL và HAL-FORMS khi mô tả hành động

HAL cơ bản biểu diễn link bằng `href` và `rel`. Nó không cung cấp đầy đủ metadata để diễn tả một thao tác `POST` cần body, vì vậy client không thể suy ra method và input chỉ từ một HAL link thông thường.

HAL-FORMS bổ sung `_templates` để công bố thao tác, method, content type và các property đầu vào. Một representation có thể chứa link điều hướng cùng template cho hành động:

```json
{
  "id": "ORD-1042",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/ORD-1042"
    },
    "cancel": {
      "href": "https://api.example.test/orders/ORD-1042/cancellations"
    }
  },
  "_templates": {
    "cancel": {
      "method": "POST",
      "contentType": "application/json",
      "properties": [
        {
          "name": "reason",
          "required": true
        }
      ]
    }
  }
}
```

Đây là representation minh họa để giải thích cấu trúc template; các property thực tế được tạo từ affordance và cấu hình của ứng dụng. Client hiểu HAL-FORMS có thể dùng metadata để tạo form hoặc request phù hợp. Client chỉ hiểu HAL cơ bản vẫn có thể theo các link điều hướng, nhưng không nên đoán method/body cho hành động thay đổi trạng thái.

Trong Spring HATEOAS, hãy yêu cầu media type phù hợp khi test hoặc phục vụ client cần affordance:

```java
import java.util.UUID;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

// Method fragment trong OrderController.
@GetMapping(value = "/{id}", produces = {
        MediaTypes.HAL_JSON_VALUE,
        MediaTypes.HAL_FORMS_JSON_VALUE
})
EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
    return orderAssembler.toModel(orderService.getRequired(id));
}
```

Client gửi `Accept: application/prs.hal-forms+json` để nhận representation có template affordance. Nếu chỉ gửi `Accept: application/hal+json`, server trả định dạng HAL cơ bản theo content negotiation.

## 9. Chọn HTTP method đúng semantics

Action link không làm thay đổi quy tắc của HTTP. Chọn method dựa trên bản chất thao tác:

| Method | Dùng khi | Tính chất quan trọng |
| --- | --- | --- |
| GET | Đọc trạng thái hoặc lấy dữ liệu | Safe, không yêu cầu thay đổi trạng thái server |
| POST | Tạo resource con hoặc khởi chạy command không idempotent | Retry có thể tạo hiệu ứng lặp nếu không có cơ chế bảo vệ |
| PUT | Thay thế trạng thái của resource theo URI xác định | Idempotent theo semantics HTTP |
| PATCH | Áp dụng thay đổi một phần | Semantics phụ thuộc patch format và contract |
| DELETE | Xóa resource | Idempotent theo semantics HTTP, dù response có thể khác nhau |

Không dùng GET để hủy đơn, thanh toán hoặc thực hiện hành động có side effect. Crawler, prefetcher hoặc cache có thể gọi GET ngoài ý muốn; GET phải giữ semantics đọc an toàn.

Với POST có khả năng được retry như thanh toán hoặc tạo shipment, cân nhắc idempotency key hoặc một resource command có định danh để tránh thực hiện lặp. Với thao tác cập nhật dựa trên phiên bản resource, có thể dùng ETag và `If-Match` để phát hiện dữ liệu đã thay đổi.

## 10. Client thực hiện action bằng hypermedia

Một client hypermedia nên làm theo trình tự:

1. Gọi API root hoặc resource collection.
2. Đọc link dẫn đến resource cần thao tác.
3. Đọc relation và affordance để xác định thao tác có sẵn.
4. Lấy method, input metadata và content type từ affordance.
5. Thu thập dữ liệu cần thiết và gửi request đến `href`.
6. Đọc representation mới để khám phá các hành động tiếp theo.

Ví dụ, client thấy link `cancel` và template yêu cầu `reason`. Client điền lý do rồi gửi `POST` đến URI trong link với body JSON. Sau khi nhận response, client đọc lại trạng thái đơn hàng và các link mới.

Client không nên tự tạo `/orders/{id}/cancellations` từ một quy tắc URL được hard-code. Nó phải dùng `href` do server cung cấp. Nhờ vậy server có thể đổi route, chuyển action sang service khác hoặc thay cấu trúc URI mà client vẫn theo được hợp đồng hypermedia.

## 11. Hành động phụ thuộc quyền truy cập

Tập affordance có thể phụ thuộc vào cả trạng thái domain và quyền của caller. Ví dụ, nhân viên hỗ trợ có quyền hủy đơn nhưng khách hàng chỉ được xem đơn của mình. Server có thể công bố link `cancel` cho caller có quyền và bỏ link đó trong representation của caller không có quyền.

Tuy nhiên, không được xem việc ẩn link là biện pháp bảo mật. Quyền có thể thay đổi sau khi representation được tải; URL có thể bị chia sẻ hoặc gọi trực tiếp. Mỗi command endpoint phải kiểm tra:

- Danh tính caller và quyền trên resource cụ thể.
- Trạng thái hiện tại có cho phép hành động không.
- Dữ liệu đầu vào có hợp lệ và thuộc phạm vi caller được thao tác không.
- Các điều kiện đồng thời như phiên bản resource hoặc ETag.

Khi request không được phép, server trả status code phù hợp, thường là `403 Forbidden` hoặc `404 Not Found` tùy chính sách không tiết lộ sự tồn tại của resource. Khi trạng thái đã thay đổi và hành động không còn hợp lệ, trả lỗi nghiệp vụ rõ ràng, ví dụ `409 Conflict`.

## 12. Kiểm thử action link bằng MockMvc

Test cần xác nhận link xuất hiện khi điều kiện nghiệp vụ đúng và không xuất hiện khi hành động không còn hợp lệ. Ví dụ với đơn hàng `PENDING`:

```java
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
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderActionLinkTest {

    private static final UUID ORDER_ID =
            UUID.fromString("a6a1f2b4-1f0d-4a7c-8e12-123456789abc");

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void publishesCancelLinkForPendingOrder() throws Exception {
        given(orderService.getRequired(ORDER_ID))
                .willReturn(OrderFixtures.pending(ORDER_ID));

        mockMvc.perform(get("/orders/{id}", ORDER_ID)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.cancel.href").exists());
    }

    @Test
    void omitsCancelLinkForCancelledOrder() throws Exception {
        given(orderService.getRequired(ORDER_ID))
                .willReturn(OrderFixtures.cancelled(ORDER_ID));

        mockMvc.perform(get("/orders/{id}", ORDER_ID)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.cancel").doesNotExist());
    }
}
```

`OrderFixtures` là fixture test giả định. Hai test dùng cùng endpoint nhưng trạng thái domain khác nhau để kiểm tra quyết định của assembler. Nếu link có relation custom được serialize qua CURIE, điều chỉnh JSONPath theo tên relation đã công bố.

Ví dụ dùng `@MockitoBean` của Spring Framework 6.2 trở lên. Với phiên bản cũ hơn, thay bằng `@MockBean` theo Spring Boot đang dùng.

## 13. Kiểm tra affordance bằng HAL-FORMS

Khi endpoint công bố affordance, yêu cầu HAL-FORMS và kiểm tra template xuất hiện:

```java
import org.springframework.hateoas.MediaTypes;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

// Method fragment trong OrderActionLinkTest; mockMvc và ORDER_ID đã được khai báo.
mockMvc.perform(get("/orders/{id}", ORDER_ID)
        .accept(MediaTypes.HAL_FORMS_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_FORMS_JSON))
        .andExpect(jsonPath("$._links.cancel.href").exists())
        .andExpect(jsonPath("$._templates").exists());
```

Nếu ứng dụng đặt tên template là `cancel`, có thể kiểm tra cụ thể `$._templates.cancel.method` bằng giá trị `POST` và property `reason`. Tên template phụ thuộc cấu hình affordance; trước khi cố định assertion, hãy xác nhận tên thực tế trong contract của ứng dụng.

Test HAL cơ bản có thể xác nhận `href` và relation, nhưng không nên kỳ vọng nó chứa metadata method và input body của thao tác POST. Để kiểm tra affordance, dùng media type hỗ trợ chúng.

## 14. Kiểm thử thực thi hành động và lỗi nghiệp vụ

Ngoài việc kiểm tra link, cần kiểm thử command endpoint thực hiện đúng thao tác:

```java
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(post("/orders/{id}/cancellations", ORDER_ID)
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {"reason":"Khách hàng yêu cầu hủy"}
                """))
        .andExpect(status().isOk());
```

Kiểm thử thêm các trường hợp:

- Đơn hàng đã giao không thể hủy và trả lỗi nghiệp vụ phù hợp.
- Caller không có quyền nhận `403` hoặc kết quả theo chính sách bảo mật.
- Request thiếu `reason` bị validation từ chối nếu field này bắt buộc.
- Request lặp lại không gây side effect ngoài mong muốn theo semantics/idempotency policy.
- Sau khi hủy thành công, representation mới không còn affordance `cancel`.

Các test này xác nhận cả phần công bố hành động và việc server thực thi đúng quy tắc domain.

## 15. Lỗi thường gặp

**Chỉ trả URL mà không mô tả thao tác:** client không biết cần gửi method hoặc body nào. Thêm affordance và dùng media type hỗ trợ khi cần metadata chi tiết.

**Nhầm relation với HTTP method:** `cancel` mô tả ý nghĩa link, còn affordance mô tả method. Không suy ra POST chỉ từ tên relation.

**Dùng GET để thay đổi trạng thái:** prefetch hoặc crawler có thể kích hoạt side effect. Dùng POST, PUT, PATCH hoặc DELETE theo semantics.

**Luôn công bố mọi action:** client nhìn thấy thao tác không hợp lệ với trạng thái hiện tại. Tạo link theo điều kiện domain và quyền caller.

**Tin rằng ẩn link là đủ bảo mật:** caller có thể gọi URL cũ trực tiếp. Luôn xác thực và kiểm tra quyền/trạng thái trong command handler.

**Không kiểm tra retry cho POST:** request bị gửi lại có thể tạo thanh toán hoặc lệnh giao hàng trùng. Thiết kế idempotency khi nghiệp vụ cần.

**Dùng HAL cơ bản nhưng kỳ vọng form metadata:** HAL link không mô tả đầy đủ method và body. Dùng HAL-FORMS hoặc media type phù hợp.

**Không cập nhật representation sau action:** client tiếp tục hiển thị link đã hết hiệu lực. Trả representation mới và để client khám phá lại affordance.

## 16. Checklist thiết kế action bằng link

- Mỗi link có `href` và relation mang ý nghĩa rõ ràng.
- Relation được tài liệu hóa và không bị dùng như tên HTTP method.
- Affordance mô tả method, input và output cần thiết.
- Endpoint hành động dùng HTTP method đúng semantics.
- Link chỉ xuất hiện khi hành động phù hợp với trạng thái domain.
- Quyền truy cập được kiểm tra lại trong handler/service.
- Dùng HAL-FORMS hoặc media type hỗ trợ affordance nếu client cần form metadata.
- Có chính sách idempotency cho command có thể được retry.
- Xử lý xung đột phiên bản hoặc trạng thái bằng ETag/If-Match khi phù hợp.
- Test link xuất hiện/biến mất theo trạng thái và quyền.
- Test cả affordance lẫn việc thực thi command.
- Sau action, trả representation mới để client khám phá bước tiếp theo.

Action bằng link biến trạng thái domain thành các khả năng mà client có thể khám phá qua hypermedia. Khi Spring HATEOAS kết hợp link relation với affordance và representation phản ánh đúng trạng thái hiện tại, client có thể điều hướng quy trình nghiệp vụ mà không phải hard-code toàn bộ state machine hoặc cấu trúc URL của server.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [Spring HATEOAS Reference – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
- [Spring HATEOAS Reference – Building links in Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.mvc)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
