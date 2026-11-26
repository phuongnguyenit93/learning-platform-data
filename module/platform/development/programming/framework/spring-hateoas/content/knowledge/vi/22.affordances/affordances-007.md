# Affordance cho DELETE

Một representation REST không chỉ cho client biết tài nguyên nằm ở đâu. Nó còn có thể mô tả các thao tác mà client được phép thực hiện trên tài nguyên đó. Ví dụ, khi client đọc một đơn hàng, API có thể công bố thao tác cập nhật, thanh toán hoặc xóa đơn hàng. Những mô tả hành động này được gọi là affordance.

Spring HATEOAS cho phép gắn nhiều affordance vào cùng một link. Với thao tác xóa, cách thường dùng là gắn affordance của phương thức controller có @DeleteMapping vào link self của tài nguyên. Spring HATEOAS đọc mapping, HTTP method và chữ ký phương thức để tạo metadata. Khi client yêu cầu media type hỗ trợ affordance như HAL-FORMS, metadata có thể được biểu diễn thành template DELETE không có trường nhập liệu.

Bài học này tập trung vào affordance cho DELETE: ý nghĩa của thao tác HTTP, cách định nghĩa endpoint xóa, cách gắn affordance vào self link, cách đọc HAL-FORMS template, cách công bố thao tác có điều kiện và cách kiểm thử hợp đồng hypermedia.

## 1. Affordance cho DELETE là gì?

Giả sử client đọc đơn hàng số 42:

~~~http
GET /api/orders/42
Accept: application/prs.hal-forms+json
~~~

Representation có thể chứa dữ liệu đơn hàng, link self và một affordance mô tả rằng client có thể gửi DELETE đến URI của đơn hàng.

Affordance cho DELETE mô tả ít nhất:

- HTTP method: DELETE.
- Target URI: URI của tài nguyên cần xóa.
- Input: thường không có request body hoặc form property.
- Tên thao tác: ví dụ deleteOrder, để client có thể phân biệt template.

Điểm quan trọng là affordance mô tả khả năng tương tác mà server công bố trong representation. Nó không tự thực hiện việc xóa, không thay thế endpoint và cũng không cấp quyền truy cập cho client.

## 2. DELETE trong HTTP

DELETE yêu cầu server xóa liên kết giữa URI đích và chức năng hiện tại của tài nguyên. Cách triển khai có thể là xóa vật lý, đánh dấu đã xóa, lưu trữ hoặc áp dụng quy trình nghiệp vụ tương ứng. Hợp đồng API cần nói rõ kết quả mà client có thể kỳ vọng.

Một số status code thường gặp:

| Status | Ý nghĩa thường dùng |
| --- | --- |
| 204 No Content | Xóa thành công và không trả response body |
| 200 OK | Xóa thành công và có trả representation mô tả kết quả |
| 202 Accepted | Đã nhận yêu cầu; việc xóa sẽ được xử lý bất đồng bộ |
| 404 Not Found | Không tìm thấy tài nguyên tại URI |
| 409 Conflict | Không thể xóa do trạng thái hoặc ràng buộc nghiệp vụ |
| 403 Forbidden | Người dùng đã xác thực nhưng không có quyền xóa |

DELETE được định nghĩa là một phương thức idempotent: gửi cùng một yêu cầu nhiều lần phải đưa server về cùng trạng thái cuối như gửi một lần. Điều này không bắt buộc mọi lần gửi đều trả cùng status code. Ví dụ, lần đầu có thể trả 204, lần sau có thể trả 404 nếu tài nguyên đã không còn.

DELETE thường không cần request body vì URI đã xác định tài nguyên cần xóa. Nếu nghiệp vụ cần dữ liệu xác nhận hoặc lý do xóa, hãy thiết kế hợp đồng riêng có chủ đích. Không nên mặc định rằng mọi client hoặc proxy đều xử lý request body của DELETE giống nhau.

## 3. Khai báo endpoint DELETE trong Spring MVC

Giả sử API quản lý đơn hàng tại /api/orders/{id}. Endpoint đọc và endpoint xóa có thể dùng cùng URI nhưng khác HTTP method:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public OrderDto one(@PathVariable Long id) {
        return orderService.getRequiredDto(id);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deleteOrder(@PathVariable Long id) {
        orderService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Trong ví dụ:

- GET /api/orders/42 đọc đơn hàng số 42.
- DELETE /api/orders/42 yêu cầu xóa đơn hàng số 42.
- @PathVariable đưa cùng định danh vào cả hai phương thức.
- ResponseEntity.noContent() trả 204 No Content khi service hoàn tất thao tác.

OrderService chịu trách nhiệm kiểm tra tài nguyên tồn tại, quyền sở hữu, trạng thái đơn hàng và các quy tắc nghiệp vụ. Controller chỉ chuyển yêu cầu HTTP vào service và chuyển kết quả thành response.

## 4. Gắn affordance DELETE vào self link

Spring HATEOAS cung cấp afford(...) trong WebMvcLinkBuilder. Hàm này nhận lời gọi giả lập đến phương thức controller để trích xuất mapping và metadata của thao tác.

Ví dụ representation đơn hàng:

~~~java
import java.math.BigDecimal;

public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}

public record OrderDto(
        Long id,
        OrderStatus status,
        BigDecimal total
) {
}
~~~

Hai kiểu public trên được đặt trong hai file Java riêng. Service và policy được dùng trong controller:

~~~java
public interface OrderService {
    OrderDto getRequiredDto(Long id);
    void delete(Long id);
}
~~~

~~~java
public interface OrderActionPolicy {
    boolean canDelete(OrderDto order);
}
~~~

Controller có thể gắn affordance vào self link:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderActionPolicy orderActionPolicy;

    public OrderController(
            OrderService orderService,
            OrderActionPolicy orderActionPolicy
    ) {
        this.orderService = orderService;
        this.orderActionPolicy = orderActionPolicy;
    }

    @GetMapping(
            value = "/{id}",
            produces = {
                    MediaTypes.HAL_JSON_VALUE,
                    MediaTypes.HAL_FORMS_JSON_VALUE
            }
    )
    public EntityModel<OrderDto> one(@PathVariable Long id) {
        OrderDto order = orderService.getRequiredDto(id);

        Link self = linkTo(methodOn(OrderController.class)
                .one(id))
                .withSelfRel();

        if (orderActionPolicy.canDelete(order)) {
            self = self.andAffordance(afford(methodOn(OrderController.class)
                    .deleteOrder(id)));
        }

        return EntityModel.of(order, self);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deleteOrder(@PathVariable Long id) {
        orderService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Đoạn mã dùng ba bước:

1. methodOn(OrderController.class).one(id) tham chiếu đến mapping GET của resource.
2. withSelfRel() tạo link self trỏ đến URI đơn hàng.
3. andAffordance(afford(methodOn(...).deleteOrder(id))) gắn metadata của phương thức DELETE vào link self đó.

methodOn tạo lời gọi giả lập trên proxy controller để Spring HATEOAS đọc mapping. Nó không thực thi phương thức deleteOrder và không gọi service. afford lấy thông tin của handler method được tham chiếu, bao gồm HTTP method và metadata đầu vào/đầu ra.

Vì thao tác xóa nhắm đến chính tài nguyên đang đọc, affordance được gắn vào link self đó. Không cần tạo một URI khác chỉ để biểu diễn hành động DELETE nếu endpoint dùng cùng target URI.

Trong ví dụ, OrderActionPolicy quyết định đơn hàng hiện tại có thể bị xóa hay không. Nếu không thể xóa, representation chỉ có link self và không gắn affordance DELETE.

## 5. Vì sao DELETE affordance không cần input model?

Một thao tác cập nhật bằng PUT thường cần request body mô tả trạng thái mới. POST có thể cần payload tạo tài nguyên. DELETE thông thường chỉ cần URI xác định tài nguyên.

Do phương thức deleteOrder không có tham số @RequestBody, Spring HATEOAS không cần tạo các trường form cho request body. HAL-FORMS có thể biểu diễn thao tác này bằng một template có:

- method là delete.
- properties là mảng rỗng.
- Target mặc định là URI của link mà affordance được gắn vào.

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    }
  },
  "_templates": {
    "deleteOrder": {
      "method": "delete",
      "properties": []
    }
  }
}
~~~

Tên deleteOrder được suy ra từ tên phương thức controller được tham chiếu. Nếu một resource có nhiều affordance, mỗi template cần tên đủ rõ để client phân biệt thao tác.

## 6. HAL và HAL-FORMS thể hiện affordance khác nhau

HAL cơ bản tập trung vào link và relation trong _links. HAL không định nghĩa cấu trúc chuẩn để mô tả form hoặc đầy đủ metadata của thao tác HTTP gắn với link.

HAL-FORMS là một media type mở rộng HAL để mô tả các thao tác qua _templates. Vì vậy, cùng một model có thể cho ra representation khác nhau tùy Accept header:

| Accept | Kết quả |
| --- | --- |
| application/hal+json | HAL với dữ liệu và link; metadata affordance không được biểu diễn thành form template |
| application/prs.hal-forms+json | HAL-FORMS với dữ liệu, link và _templates mô tả thao tác |

Ví dụ, với HAL thông thường, client có thể nhận:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    }
  }
}
~~~

Với HAL-FORMS, cùng representation có thể bổ sung template:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    }
  },
  "_templates": {
    "deleteOrder": {
      "method": "delete",
      "properties": []
    }
  }
}
~~~

Nếu client cần khám phá phương thức DELETE và cách gửi thao tác qua hypermedia, nó cần yêu cầu media type có khả năng biểu diễn affordance như HAL-FORMS. Chỉ nhìn thấy link self trong HAL không đủ để kết luận rằng resource hỗ trợ DELETE.

## 7. Bật hỗ trợ HAL-FORMS

Có thể bật HAL-FORMS bằng @EnableHypermediaSupport:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;

@Configuration
@EnableHypermediaSupport(
        type = {
                EnableHypermediaSupport.HypermediaType.HAL,
                EnableHypermediaSupport.HypermediaType.HAL_FORMS
        }
)
public class HypermediaConfiguration {
}
~~~

Khi cấu hình đã được đăng ký, client có thể yêu cầu:

~~~http
GET /api/orders/42
Accept: application/prs.hal-forms+json
~~~

Controller trong ví dụ khai báo cả MediaTypes.HAL_JSON_VALUE và MediaTypes.HAL_FORMS_JSON_VALUE trong produces, vì vậy Spring có thể chọn representation theo Accept header. Nếu ứng dụng chỉ hỗ trợ một media type, hãy khai báo rõ media type đó trong mapping và tài liệu API.

Không nhầm application/prs.hal-forms+json với application/hal+json. Hai media type có cấu trúc liên quan nhưng không thể thay thế cho nhau.

## 8. Công bố DELETE affordance có điều kiện

Không phải đơn hàng nào cũng có thể xóa. Ví dụ, đơn hàng đã giao hoặc đã thanh toán có thể bị khóa để bảo đảm lịch sử giao dịch. API nên chỉ công bố affordance khi thao tác có ý nghĩa trong trạng thái hiện tại và người dùng hiện tại có quyền thực hiện.

Ví dụ trong controller:

~~~java
OrderDto order = orderService.getRequiredDto(id);

Link self = linkTo(methodOn(OrderController.class)
        .one(id))
        .withSelfRel();

if (orderActionPolicy.canDelete(order)) {
    self = self.andAffordance(afford(methodOn(OrderController.class)
            .deleteOrder(id)));
}

return EntityModel.of(order, self);
~~~

OrderActionPolicy là thành phần nghiệp vụ hoặc authorization policy xác định người dùng hiện tại có thể xóa đơn hàng hay không. Điều kiện có thể phụ thuộc trạng thái, quyền, thời hạn hoặc quy trình phê duyệt.

Khi affordance không được công bố, client không nên hiển thị thao tác xóa. Tuy nhiên, việc ẩn affordance không phải cơ chế bảo mật. Client có thể lưu URI từ response cũ hoặc tự gửi DELETE. Endpoint vẫn phải kiểm tra quyền và trạng thái tại thời điểm nhận request.

Nếu trạng thái thay đổi sau khi GET được trả về, request DELETE tiếp theo có thể bị từ chối với 409 Conflict hoặc status phù hợp với hợp đồng API.

## 9. Phân biệt affordance với link relation

Một link relation như self, customer hoặc orders mô tả đích điều hướng. Affordance mô tả một thao tác có thể thực hiện trên đích đó, gồm HTTP method và metadata của input/output khi media type hỗ trợ.

| Thành phần | Câu hỏi nó trả lời |
| --- | --- |
| Link self | Tài nguyên hiện tại ở URI nào? |
| Affordance DELETE | Có thể gửi thao tác DELETE đến URI nào? |
| HAL-FORMS template | Client cần dùng HTTP method nào và cần gửi những trường nào? |
| Controller @DeleteMapping | Server xử lý request DELETE ra sao? |

Không nên tạo một relation delete trỏ đến cùng URI rồi cho rằng client đã biết đó là phương thức DELETE. Một link thông thường không tự mang ngữ nghĩa HTTP method. Dùng affordance để mô tả thao tác và dùng controller mapping để thực thi nó.

## 10. Xử lý kết quả và lỗi khi DELETE

Affordance được công bố trong GET response chỉ mô tả thao tác dự kiến. Khi client gửi DELETE, server vẫn cần xử lý các kết quả thực tế:

~~~java
@DeleteMapping("/{id}")
public ResponseEntity<Void> deleteOrder(@PathVariable Long id) {
    orderService.delete(id);
    return ResponseEntity.noContent().build();
}
~~~

Service có thể phát sinh các trường hợp:

- Không tìm thấy đơn hàng: trả 404 Not Found.
- Người dùng không có quyền: trả 403 Forbidden.
- Đơn hàng không ở trạng thái cho phép xóa: trả 409 Conflict.
- Xóa được xử lý bất đồng bộ: trả 202 Accepted và cung cấp link theo dõi trạng thái nếu cần.

Không nên giả định rằng việc client nhìn thấy affordance sẽ bảo đảm thao tác thành công. Giữa thời điểm GET và DELETE, dữ liệu, quyền hoặc trạng thái nghiệp vụ có thể thay đổi.

## 11. Đặt tên và mô tả DELETE template

Tên template nên mô tả hành động một cách ổn định. Nếu controller có phương thức deleteOrder, tên mặc định thường được suy ra từ tên phương thức. Nếu cần kiểm soát tên độc lập với tên Java method, có thể xây affordance thủ công bằng API Affordances:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.mediatype.Affordances;

Link deleteLink = Affordances.of(selfLink)
        .afford(HttpMethod.DELETE)
        .withName("deleteOrder")
        .toLink();
~~~

API thủ công hữu ích khi không thể tham chiếu trực tiếp đến controller method hoặc cần mô tả thao tác không được suy ra đầy đủ từ Spring MVC mapping. Khi dùng cách này, ứng dụng chịu trách nhiệm cung cấp đúng target, method, input metadata và output metadata.

Nếu chỉ có một affordance, HAL-FORMS có thể dùng tên default theo quy tắc của media type. Khi có nhiều template, tên riêng giúp client phân biệt các thao tác như updateOrder, cancelOrder và deleteOrder.

Có thể bổ sung tiêu đề thân thiện cho template thông qua resource bundle rest-messages.properties:

~~~properties
OrderDto._templates.deleteOrder.title=Delete order
~~~

Tiêu đề giúp giao diện hiển thị nội dung phù hợp với người dùng. Với ứng dụng đa ngôn ngữ, có thể cung cấp các resource bundle theo locale.

## 12. Kiểm thử DELETE affordance bằng MockMvc

Kiểm thử cần xác nhận hai việc riêng:

1. GET representation có công bố DELETE template khi trạng thái và quyền cho phép.
2. Endpoint DELETE thực sự thực hiện thao tác và trả status code đúng.

Ví dụ kiểm thử HAL-FORMS:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(HypermediaConfiguration.class)
class OrderAffordanceTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @MockBean
    OrderActionPolicy orderActionPolicy;

    @Test
    void exposesDeleteTemplateWhenOrderCanBeDeleted() throws Exception {
        OrderDto order = new OrderDto(
                42L,
                OrderStatus.PENDING,
                BigDecimal.valueOf(1250000)
        );
        when(orderService.getRequiredDto(42L)).thenReturn(order);
        when(orderActionPolicy.canDelete(order)).thenReturn(true);

        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaTypes.HAL_FORMS_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_FORMS_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._templates.deleteOrder.method")
                        .value("delete"))
                .andExpect(jsonPath(
                        "$._templates.deleteOrder.properties.length()"
                ).value(0));
    }
}
~~~

Đây là ví dụ test slice. Các kiểu OrderDto, OrderStatus, OrderService, OrderActionPolicy và OrderController cần được định nghĩa trong ứng dụng. @Import đăng ký cấu hình HAL-FORMS; các dependency được mock để kiểm soát trạng thái và quyền.

Kiểm thử endpoint DELETE:

~~~java
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void deletesOrderAndReturnsNoContent() throws Exception {
    mockMvc.perform(delete("/api/orders/42"))
            .andExpect(status().isNoContent());

    verify(orderService).delete(42L);
}
~~~

Nên bổ sung các trường hợp:

- Đơn hàng không thể xóa thì HAL-FORMS không có template deleteOrder.
- Người dùng không có quyền không nhận affordance và DELETE bị từ chối.
- Đơn hàng không tồn tại trả status phù hợp.
- Đơn hàng ở trạng thái bị khóa trả 409 Conflict.
- HAL-FORMS template dùng đúng HTTP method và không có properties.
- HAL thông thường vẫn trả link self nhưng không được giả định có _templates.
- Template chỉ được công bố khi controller có endpoint DELETE tương ứng.

## 13. Những lỗi thường gặp

**Chỉ thêm link self mà không khai báo affordance.** Link self cho biết URI của resource; nó không mô tả rằng URI hỗ trợ DELETE. Hãy gắn afford(methodOn(...).deleteOrder(id)).

**Tạo relation delete thay cho affordance.** Relation thông thường không mô tả HTTP method hoặc input/output metadata. Dùng affordance để công bố thao tác.

**Dùng sai controller mapping.** Nếu @DeleteMapping có URI khác với self link, affordance có thể trỏ đến target khác. Hãy để methodOn tham chiếu đúng phương thức và kiểm thử target.

**Mong HAL cơ bản hiển thị template.** HAL không biểu diễn đầy đủ metadata affordance. Yêu cầu application/prs.hal-forms+json khi client cần template.

**Tạo form property cho thao tác không có input.** DELETE thông thường chỉ cần URI. HAL-FORMS template có thể có properties: [].

**Coi affordance là quyền truy cập.** Client nhìn thấy thao tác không có nghĩa thao tác chắc chắn được phép ở thời điểm gửi request. Server phải kiểm tra quyền và trạng thái trong endpoint.

**Không xử lý trạng thái đã thay đổi.** Affordance có thể cũ khi tài nguyên thay đổi sau GET. Endpoint DELETE phải kiểm tra lại invariant và trả lỗi phù hợp.

**Nhầm idempotency với response luôn giống nhau.** DELETE là idempotent về hiệu ứng trạng thái, nhưng status code giữa lần đầu và lần lặp có thể khác theo chính sách API.

## 14. Ghi nhớ

Affordance cho DELETE mô tả rằng một resource có thể được xóa bằng HTTP DELETE tại target URI. Trong Spring HATEOAS, tạo self link bằng linkTo(methodOn(...)), sau đó gắn thao tác xóa bằng andAffordance(afford(methodOn(...).deleteOrder(id))). Controller cần có endpoint @DeleteMapping tương ứng.

DELETE thông thường không cần request body. Khi client yêu cầu HAL-FORMS, thao tác có thể được biểu diễn trong _templates với method: delete và properties: []. HAL cơ bản vẫn biểu diễn link nhưng không cung cấp form template để mô tả đầy đủ affordance.

Chỉ công bố affordance khi thao tác phù hợp với trạng thái tài nguyên và quyền hiện tại. Dù vậy, endpoint vẫn phải kiểm tra quyền, sự tồn tại và quy tắc nghiệp vụ tại thời điểm nhận DELETE. Kiểm thử cả template HAL-FORMS lẫn response thực tế của endpoint để bảo đảm client khám phá và thực hiện thao tác đúng.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [Spring HATEOAS Reference – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
- [WebMvcLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [Affordances API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/Affordances.html)
- [HTTP Semantics – DELETE](https://www.rfc-editor.org/rfc/rfc9110.html#name-delete)
