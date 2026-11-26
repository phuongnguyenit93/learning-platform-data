# Kiểm thử affordance

Affordance mô tả những thao tác mà client có thể thực hiện trong ngữ cảnh của một resource. Trong Spring HATEOAS, affordance được gắn với link và có thể mô tả HTTP method, URI đích, kiểu dữ liệu đầu vào, kiểu dữ liệu đầu ra và metadata của các trường. Khi representation được serialize bằng media type hỗ trợ affordance, chẳng hạn HAL-FORMS, client có thể khám phá thao tác và tạo request mà không phải tự đoán cấu trúc endpoint.

Kiểm thử affordance cần xác minh hai điều. Thứ nhất, representation có công bố đúng thao tác và đúng metadata mà client cần hay không. Thứ hai, endpoint thực sự có thực hiện thao tác đó theo cùng các quy tắc về validation, quyền truy cập và trạng thái nghiệp vụ hay không. Một template được serialize đúng vẫn không chứng minh server sẽ chấp nhận request; ngược lại, endpoint chạy đúng nhưng affordance sai có thể khiến client gửi request không hợp lệ.

Bài học này trình bày cách kiểm thử affordance ở các lớp: điều kiện nghiệp vụ tạo affordance, metadata của link, HAL-FORMS serialization, content negotiation, request thực tế và các trường hợp hành động không khả dụng. Ví dụ sử dụng API đơn hàng với thao tác yêu cầu hủy đơn, nhưng quy trình có thể áp dụng cho cập nhật, phê duyệt, thanh toán hoặc các thao tác khác.

Sau bài học, bạn có thể:

- Giải thích affordance và lý do cần kiểm thử nó như một phần của hợp đồng API.
- Phân biệt kiểm thử link thông thường với kiểm thử affordance.
- Tạo affordance từ Spring MVC controller method bằng afford(...) và andAffordance(...).
- Cấu hình HAL-FORMS và kiểm tra _templates.
- Xác minh method, target, content type và properties của template.
- Kiểm tra metadata được suy ra từ kiểu dữ liệu và Bean Validation.
- Kiểm thử affordance có điều kiện theo trạng thái resource.
- Kiểm tra nhánh không có affordance và media type được trả về.
- Gửi request theo affordance và xác minh kết quả thực tế.
- Phân biệt metadata gợi ý với validation và authorization phía server.
- Viết contract test ổn định bằng MockMvc và JSONPath.

## 1. Affordance là gì và kiểm thử điều gì?

Link thông thường cho biết client có thể điều hướng đến một resource. Affordance bổ sung mô tả về thao tác có thể thực hiện trong ngữ cảnh của link đó.

Ví dụ representation của một đơn hàng có link self. Tùy trạng thái đơn hàng, link này có thể mang thêm affordance:

- GET: đọc đơn hàng.
- PUT: thay thế thông tin được phép cập nhật.
- PATCH: cập nhật một phần.
- POST đến endpoint con: yêu cầu hủy đơn hàng.

Spring HATEOAS cho phép liên kết nhiều affordance với một link. Khi media type được serialize hỗ trợ affordance, metadata tổng quát sẽ được chuyển thành cấu trúc đặc thù của media type.

### 1.1. Link test và affordance test khác nhau

| Kiểm thử link | Kiểm thử affordance |
|---|---|
| Xác minh relation và href | Xác minh thao tác gắn với link |
| Kiểm tra URI có đúng resource đích | Kiểm tra HTTP method và target của thao tác |
| Có thể dùng HAL JSON | Cần media type có khả năng biểu diễn affordance để kiểm tra template |
| Không mô tả request body | Kiểm tra input properties và content type |
| Kiểm tra điều hướng | Kiểm tra khả năng thực hiện workflow |

Ví dụ, test sau chỉ chứng minh link self tồn tại:

~~~java
.andExpect(jsonPath("$._links.self.href").exists());
~~~

Nó không chứng minh affordance POST yêu cầu hủy đã được công bố, cũng không chứng minh client biết phải gửi trường reason nào.

### 1.2. Các lớp kiểm thử nên có

Một bộ test affordance nên có ít nhất các lớp sau:

1. Điều kiện nghiệp vụ: resource ở trạng thái nào thì thao tác được công bố?
2. Model/link: affordance có được gắn vào đúng link và đúng controller method không?
3. Serialization: media type có biểu diễn đúng method, target và input metadata không?
4. Content negotiation: HAL và HAL-FORMS có được trả đúng theo request không?
5. Workflow: request theo affordance có được server xử lý đúng không?
6. Từ chối: thao tác không hợp lệ hoặc không có quyền có bị server từ chối không?

Không nên chỉ kiểm tra JSON template. Client cuối cùng tương tác với endpoint, vì vậy test phải bao gồm cả metadata và hành vi.

## 2. Chuẩn bị ví dụ: affordance yêu cầu hủy đơn hàng

Giả sử API có resource đơn hàng:

~~~text
GET  /orders/{id}
POST /orders/{id}/cancellations
~~~

Một đơn hàng ở trạng thái PENDING có thể cho phép khách hàng yêu cầu hủy. Đơn đã SHIPPED không còn cho phép thao tác đó.

Request hủy nhận một lý do:

~~~java
public record CancellationRequest(

    @NotNull
    @NotBlank
    @Size(max = 300)
    String reason
) {}
~~~

Import:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
~~~

@NotNull giúp mô tả trường bắt buộc trong metadata HAL-FORMS. @NotBlank và @Size được dùng để kiểm tra payload thực tế ở server. Các annotation validation có thể được Spring HATEOAS dùng để tạo metadata phù hợp, nhưng client vẫn phải gửi dữ liệu hợp lệ và server vẫn phải chạy validation.

Ứng dụng cần có Bean Validation provider, thường được đưa vào qua dependency spring-boot-starter-validation, để các annotation validation được thực thi khi controller nhận request.

Representation đọc đơn hàng có thể là:

~~~java
public record OrderRepresentation(
    UUID id,
    String status
) {}
~~~

Import:

~~~java
import java.util.UUID;
~~~

Trong ví dụ, service và repository là thành phần của ứng dụng. Điều cần kiểm thử là quyết định công bố affordance, nội dung template và hành vi của endpoint hủy.

## 3. Gắn affordance vào link bằng Spring HATEOAS

Spring HATEOAS cho phép tạo link từ controller mapping bằng WebMvcLinkBuilder, sau đó gắn affordance trỏ đến method thực hiện thao tác.

Controller ví dụ:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final CancellationService cancellationService;

    OrderController(
            OrderService orderService,
            CancellationService cancellationService) {
        this.orderService = orderService;
        this.cancellationService = cancellationService;
    }

    @GetMapping("/{id}")
    EntityModel<OrderRepresentation> one(@PathVariable UUID id) {

        Order order = orderService.findById(id);

        Link self = linkTo(
            methodOn(OrderController.class).one(id)
        ).withSelfRel();

        if (order.canBeCancelled()) {
            self = self.andAffordance(
                afford(
                    methodOn(OrderController.class)
                        .requestCancellation(id, null)
                )
            );
        }

        OrderRepresentation representation =
            new OrderRepresentation(
                order.getId(),
                order.getStatus().name()
            );

        return EntityModel.of(representation, self);
    }

    @PostMapping(
        value = "/{id}/cancellations",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<?> requestCancellation(
            @PathVariable UUID id,
            @Valid @RequestBody CancellationRequest request) {

        if (!orderService.canBeCancelled(id)) {
            return ResponseEntity.status(HttpStatus.CONFLICT).build();
        }

        cancellationService.request(id, request.reason());
        return ResponseEntity.accepted().build();
    }
}
~~~

Các import liên quan:

~~~java
import jakarta.validation.Valid;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Các điểm quan trọng:

- linkTo(methodOn(...)) tạo link self từ mapping của controller.
- afford(methodOn(...)) mô tả method POST được ánh xạ từ requestCancellation(...).
- andAffordance(...) gắn thao tác đó vào link self.
- Điều kiện order.canBeCancelled() quyết định affordance có được công bố trong representation hiện tại hay không.
- Endpoint vẫn kiểm tra lại trạng thái khi nhận request.

Không dùng affordance thay cho logic nghiệp vụ. Trạng thái đơn hàng có thể thay đổi sau khi client đọc representation, vì vậy server luôn phải kiểm tra lại trước khi thực hiện thao tác.

## 4. Bật HAL-FORMS để kiểm tra template

HAL JSON mô tả link trong _links. HAL-FORMS mở rộng HAL bằng _templates để biểu diễn thao tác và các trường đầu vào.

Cấu hình Spring HATEOAS:

~~~java
@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
class HypermediaConfiguration {
}
~~~

Import:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;
~~~

Client yêu cầu HAL-FORMS bằng header:

~~~http
GET /orders/42
Accept: application/prs.hal-forms+json
~~~

Nếu affordance yêu cầu hủy được công bố, response có thể chứa:

~~~json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    }
  },
  "_templates": {
    "default": {
      "method": "post",
      "target": "http://localhost:8080/orders/42/cancellations",
      "contentType": "application/json",
      "properties": [
        {
          "name": "reason",
          "required": true,
          "type": "text"
        }
      ]
    }
  }
}
~~~

Các thuộc tính cần kiểm tra:

| Thuộc tính | Ý nghĩa | Bằng chứng cần kiểm tra |
|---|---|---|
| method | HTTP method khi submit | post |
| target | URI nhận request | Đường dẫn cancellation |
| contentType | Media type của request body | application/json |
| properties | Các trường client gửi | Có trường reason |
| required | Trường có bắt buộc không | true theo metadata |
| type | Gợi ý kiểu input | text |

target chỉ được render khi target của affordance khác link mà nó được gắn vào. Trong ví dụ này, link self trỏ đến order còn affordance trỏ đến cancellation endpoint, vì vậy target được công bố.

Nếu chỉ có một template, HAL-FORMS sử dụng tên default. Khi có nhiều affordance, tên template có thể được tạo từ tên method hoặc tên được cấu hình cho affordance. Test nên xác nhận đúng tên template mà API thực tế công bố.

## 5. Kiểm thử HAL-FORMS bằng MockMvc

MockMvc cho phép gửi request qua Spring MVC và kiểm tra status, header cùng JSON body mà không cần khởi chạy server HTTP bên ngoài.

Một test class có thể dùng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderAffordanceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    OrderTestFixture fixture;

    UUID pendingOrderId;
    UUID shippedOrderId;

    @BeforeEach
    void setUp() {
        pendingOrderId = fixture.createPendingOrder();
        shippedOrderId = fixture.createShippedOrder();
    }
}
~~~

Import:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

OrderTestFixture là helper của test suite: mỗi phương thức tạo và lưu một order ở trạng thái tương ứng rồi trả về ID. Tên helper và cách seed dữ liệu cần được thay bằng fixture thực tế của ứng dụng.

### 5.1. Kiểm tra affordance khi thao tác được phép

Với order đang PENDING:

~~~java
@Test
void publishesCancellationAffordanceForPendingOrder() throws Exception {

    mvc.perform(get("/orders/{id}", pendingOrderId)
            .accept(MediaTypes.HAL_FORMS_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_FORMS_JSON
        ))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._templates.default.method").value("post"))
        .andExpect(jsonPath("$._templates.default.target")
            .value(containsString("/orders/" + pendingOrderId + "/cancellations")))
        .andExpect(jsonPath("$._templates.default.contentType")
            .value("application/json"))
        .andExpect(jsonPath("$._templates.default.properties[0].name")
            .value("reason"))
        .andExpect(jsonPath("$._templates.default.properties[0].required")
            .value(true));
}
~~~

Import bổ sung:

~~~java
import static org.hamcrest.Matchers.containsString;
~~~

Test này bảo vệ các phần quan trọng của hợp đồng:

- Link self vẫn tồn tại.
- Template sử dụng POST.
- Target trỏ đúng cancellation endpoint của order hiện tại.
- Request body dùng media type JSON.
- Client biết trường reason cần gửi.
- Metadata cho biết trường này là bắt buộc.

Không nên chỉ kiểm tra _templates tồn tại. Một template có thể tồn tại nhưng trỏ sai endpoint, dùng sai method hoặc thiếu input property.

### 5.2. Kiểm tra affordance không xuất hiện khi thao tác không khả dụng

Với order đã SHIPPED:

~~~java
@Test
void doesNotPublishCancellationAffordanceForShippedOrder()
        throws Exception {

    mvc.perform(get("/orders/{id}", shippedOrderId)
            .accept(MediaTypes.HAL_FORMS_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._templates").doesNotExist());
}
~~~

Có một chi tiết của Spring HATEOAS cần lưu ý: HalFormsHttpMessageConverter kiểm tra representation có template hay không. Nếu không có template nào được đăng ký, converter có thể chuyển media type response về application/hal+json thay vì trả HAL-FORMS rỗng.

Do đó, nếu muốn kiểm tra nhánh không có affordance một cách đầy đủ, hãy xác minh cả Content-Type:

~~~java
mvc.perform(get("/orders/{id}", shippedOrderId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._templates").doesNotExist());
~~~

Hành vi fallback này thuộc converter HAL-FORMS của Spring HATEOAS. Nếu ứng dụng dùng custom message converter hoặc cấu hình media type riêng, hãy xác nhận lại response thực tế của ứng dụng.

### 5.3. Kiểm tra HAL JSON và HAL-FORMS riêng biệt

Một client có thể yêu cầu HAL JSON thay vì HAL-FORMS:

~~~java
@Test
void returnsRegularHalWhenClientRequestsHalJson() throws Exception {

    mvc.perform(get("/orders/{id}", pendingOrderId)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._templates").doesNotExist());
}
~~~

HAL JSON và HAL-FORMS là hai media type riêng. Không nên viết test giả định mọi affordance đều xuất hiện trong _templates bất kể header Accept.

### 5.4. Tránh test phụ thuộc vào host hoặc thứ tự property

URI được tạo từ request có thể là relative URI hoặc absolute URI tùy cấu hình. Khi không cần xác minh scheme/host, hãy kiểm tra phần path bằng containsString hoặc matcher phù hợp.

Tương tự, nếu input model có nhiều property, không nên mặc định thứ tự property luôn là một phần hợp đồng. Có thể dùng JSONPath filter theo tên property để tìm đúng phần tử thay vì phụ thuộc chỉ số mảng.

## 6. Kiểm thử metadata của input property

Spring HATEOAS có thể suy ra metadata HAL-FORMS từ kiểu dữ liệu và annotation trên input model. Một số metadata thường gặp:

| Annotation hoặc kiểu dữ liệu | Metadata có thể được suy ra |
|---|---|
| @NotNull | required: true |
| @Size(min, max) | min và max |
| @Email | type: email |
| @Pattern | regex |
| String | type: text |
| LocalDate | type: date |

Cần kiểm tra metadata mà phiên bản Spring HATEOAS và cấu hình thực tế serialize. Không phải mọi annotation validation của mọi thư viện đều được chuyển thành metadata HAL-FORMS.

Ví dụ test trường email:

~~~java
.andExpect(jsonPath(
    "$._templates.default.properties[?(@.name == 'email')].type[0]"
).value("email"));
~~~

Nếu property là trường bắt buộc:

~~~java
.andExpect(jsonPath(
    "$._templates.default.properties[?(@.name == 'email')].required[0]"
).value(true));
~~~

Test này giúp phát hiện thay đổi khi input model hoặc annotation bị chỉnh sửa nhưng template không còn mô tả đúng dữ liệu client phải gửi.

### 6.1. Kiểm tra contentType từ mapping consumes

Nếu controller khai báo:

~~~java
@PostMapping(
    value = "/{id}/cancellations",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
~~~

HAL-FORMS có thể đưa contentType tương ứng vào template. Nếu thay đổi mapping sang một media type khác, contract test cần phát hiện thay đổi đó.

Không nên chỉ kiểm tra method POST mà bỏ qua content type. Client có thể tạo body đúng nhưng gửi sai media type, dẫn đến 415 Unsupported Media Type.

### 6.2. Kiểm tra template target

Nếu affordance được gắn lên link self nhưng thao tác gửi đến endpoint khác, HAL-FORMS có thể biểu diễn target.

Test target giúp phát hiện lỗi như:

- ID bị thiếu hoặc sai.
- URI trỏ về resource self thay vì endpoint thao tác.
- Controller mapping thay đổi nhưng affordance chưa cập nhật.
- Link được tạo thủ công và lệch khỏi mapping thực tế.

Dùng controller method với methodOn(...) và afford(...) giúp giảm lặp URI trong code; test response vẫn cần xác minh target cuối cùng.

## 7. Kiểm thử request thực tế theo affordance

Metadata chỉ là mô tả cho client. Hãy gửi request đến endpoint và kiểm tra server thực hiện đúng quy tắc.

Ví dụ client gửi request theo template:

~~~http
POST /orders/42/cancellations
Content-Type: application/json

{
  "reason": "Customer requested cancellation"
}
~~~

MockMvc test:

~~~java
@Test
void acceptsCancellationForPendingOrder() throws Exception {

    mvc.perform(post("/orders/{id}/cancellations", pendingOrderId)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "reason": "Customer requested cancellation"
                }
                """))
        .andExpect(status().isAccepted());
}
~~~

Import bổ sung:

~~~java
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
~~~

Test này xác minh endpoint nhận đúng method và payload theo affordance đã công bố.

### 7.1. Kiểm thử server từ chối thao tác không còn hợp lệ

Giả sử order đã chuyển sang SHIPPED sau khi client nhận representation. Client vẫn có thể gửi POST bằng URI đã lưu trước đó.

Server cần kiểm tra trạng thái mới và từ chối:

~~~java
@Test
void rejectsCancellationWhenOrderIsAlreadyShipped() throws Exception {

    mvc.perform(post("/orders/{id}/cancellations", shippedOrderId)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "reason": "Customer requested cancellation"
                }
                """))
        .andExpect(status().isConflict());
}
~~~

Điều này xác nhận affordance không tạo ra quyền thực hiện vĩnh viễn. Nó chỉ mô tả khả năng ở thời điểm representation được tạo.

### 7.2. Kiểm thử validation của request body

HAL-FORMS có thể mô tả trường reason là bắt buộc, nhưng server vẫn phải kiểm tra payload:

~~~java
@Test
void rejectsCancellationWithoutReason() throws Exception {

    mvc.perform(post("/orders/{id}/cancellations", pendingOrderId)
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "reason": ""
                }
                """))
        .andExpect(status().isBadRequest());
}
~~~

Nếu API sử dụng Problem Details hoặc status code validation riêng, hãy điều chỉnh kỳ vọng theo hợp đồng lỗi đã công bố. Điều cần giữ là server không chấp nhận dữ liệu không hợp lệ chỉ vì client đã gửi theo một template.

### 7.3. Kiểm thử authorization độc lập

Affordance có thể không được công bố cho người dùng không có quyền. Tuy nhiên, endpoint vẫn phải bảo vệ request trực tiếp.

Nên có hai test:

- Người dùng không có quyền đọc resource không nhìn thấy affordance.
- Người dùng không có quyền thao tác gửi trực tiếp POST vẫn nhận lỗi authorization phù hợp.

Ví dụ, nếu hợp đồng dùng 403 Forbidden:

~~~java
mvc.perform(post("/orders/{id}/cancellations", pendingOrderId)
        .with(user("viewer").roles("READ_ONLY"))
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "reason": "Customer requested cancellation"
            }
            """))
    .andExpect(status().isForbidden());
~~~

Import:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
~~~

Cấu hình security và role trong ví dụ cần khớp với ứng dụng. Không dùng việc ẩn affordance như bằng chứng duy nhất rằng thao tác được bảo vệ.

## 8. Kiểm thử affordance có nhiều thao tác

Một resource có thể công bố nhiều affordance trên cùng link, ví dụ PUT và PATCH. Mỗi template cần được kiểm tra độc lập.

Spring HATEOAS cho phép:

~~~java
Link self = linkTo(
    methodOn(EmployeeController.class).findOne(id)
).withSelfRel()
 .andAffordance(
    afford(methodOn(EmployeeController.class).update(null, id))
 )
 .andAffordance(
    afford(methodOn(EmployeeController.class).partiallyUpdate(null, id))
 );
~~~

Khi HAL-FORMS serialize, representation có thể có nhiều template. Tên template được tạo từ method được tham chiếu nếu có nhiều thao tác; khi chỉ có một template, tên default được dùng.

Review test cần xác minh:

- Template PUT có method put.
- Template PATCH có method patch.
- Mỗi template có đúng target.
- Input property và quy tắc bắt buộc phù hợp với thao tác.
- PATCH không bị kiểm tra như PUT toàn phần.
- Template không bị trùng tên hoặc ghi đè ngoài ý muốn.

Ví dụ:

~~~java
.andExpect(jsonPath("$._templates.update.method").value("put"))
.andExpect(jsonPath("$._templates.partiallyUpdate.method").value("patch"));
~~~

Tên template trong ví dụ giả định controller method có tên update và partiallyUpdate. Hãy xác nhận tên được serialize thực tế trước khi cố định JSONPath trong test.

## 9. Kiểm thử affordance được tạo thủ công

Trong một số trường hợp, API không có controller method phù hợp để suy ra metadata. Spring HATEOAS hỗ trợ tạo affordance thủ công bằng Affordances.

Ví dụ:

~~~java
Link search = Affordances.of(
        Link.of("/orders", IanaLinkRelations.SEARCH))
    .afford(HttpMethod.GET)
    .withOutput(OrderSearchResult.class)
    .addParameters(
        QueryParameter.optional("status"),
        QueryParameter.optional("createdAfter")
    )
    .withName("searchOrders")
    .toLink();
~~~

Import:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.QueryParameter;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.http.HttpMethod;
~~~

Khi kiểm thử affordance thủ công, không có controller mapping để làm nguồn đối chiếu tự động. Vì vậy cần kiểm tra:

- Method được khai báo có đúng với endpoint thật không.
- Query parameter có được endpoint hỗ trợ không.
- Output type có khớp response không.
- Tên affordance có ổn định không.
- Target URI có được quản lý tập trung không.

Đặc biệt, hãy có integration test gửi request đến endpoint được mô tả. Nếu chỉ kiểm tra object affordance được tạo mà không kiểm tra HTTP response, test có thể bỏ sót sự sai lệch giữa metadata và endpoint.

## 10. Kiểm tra lỗi và thay đổi hợp đồng affordance

Affordance là một phần của hợp đồng mà client có thể phụ thuộc. Các thay đổi sau cần được review:

| Thay đổi | Tác động tiềm ẩn |
|---|---|
| Đổi method POST thành PUT | Client gửi request sai method |
| Đổi target URI | Client không gửi được thao tác |
| Xóa input property | Client cũ vẫn gửi trường đó |
| Đổi required từ false sang true | Request cũ có thể bị từ chối |
| Đổi content type | Client cần serialize body khác |
| Đổi tên template | Client hoặc test phụ thuộc tên có thể hỏng |
| Xóa affordance | Client không còn khám phá được workflow |
| Công bố affordance khi trạng thái không phù hợp | Client được hướng dẫn thực hiện thao tác sẽ bị từ chối |

Khi thay đổi affordance, cần cập nhật contract test để phản ánh hợp đồng mới. Nếu thay đổi phá vỡ client cũ, hãy có chiến lược versioning hoặc giai đoạn chuyển đổi.

### 10.1. Không kiểm tra quá nhiều chi tiết serialization không ổn định

Một test tốt nên tập trung vào điều client cần dựa vào:

- HTTP method.
- Target.
- Input property name và các ràng buộc quan trọng.
- Content type.
- Sự hiện diện hoặc vắng mặt của thao tác theo trạng thái.

Tránh kiểm tra thứ tự key trong JSON, khoảng trắng, thứ tự field nếu không thuộc hợp đồng, hoặc host cố định của môi trường test. Các chi tiết này dễ làm test lỗi khi cấu hình môi trường thay đổi mà API semantics không thay đổi.

### 10.2. Kiểm tra affordance theo trạng thái ở nhiều điểm thời gian

Nếu trạng thái có thể thay đổi đồng thời, test nên kiểm tra hai thời điểm:

1. GET representation khi thao tác đang khả dụng.
2. POST sau khi trạng thái đã thay đổi khiến thao tác không còn hợp lệ.

Điều này mô phỏng race condition phổ biến: client đã nhận form hợp lệ nhưng trạng thái server đổi trước khi submit. Server phải từ chối thao tác bằng status code phù hợp và không thực hiện side effect.

## 11. Lỗi thường gặp khi kiểm thử affordance

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra link self | Không xác minh thao tác | Kiểm tra _templates và metadata |
| Chỉ kiểm tra _templates tồn tại | Template có thể sai method hoặc target | Assert method, target và input |
| Chỉ kiểm tra HAL JSON | Không kiểm tra được HAL-FORMS template | Gửi Accept HAL-FORMS |
| Giả định response luôn là HAL-FORMS | Bỏ sót fallback khi không có template | Kiểm tra Content-Type thực tế |
| Kiểm tra template nhưng không gọi endpoint | Metadata đúng nhưng thao tác có thể hỏng | Gửi request integration test |
| Tin required là validation server | Payload sai vẫn có thể được gửi | Test Bean Validation ở endpoint |
| Coi affordance là authorization | Client gọi trực tiếp endpoint có thể vượt UI | Test quyền trên request thật |
| Chỉ test trạng thái hợp lệ | Không phát hiện affordance bị công bố sai | Test cả trạng thái không hợp lệ |
| Hard-code host trong JSONPath | Test lỗi ở môi trường khác | Kiểm tra path hoặc dùng matcher |
| Phụ thuộc thứ tự property | Test dễ vỡ khi model thay đổi | Tìm property theo tên |
| Dùng tên template mặc định cho mọi trường hợp | Test sai khi có nhiều affordance | Kiểm tra tên template thực tế |

## 12. Quy trình kiểm thử affordance trong dự án

Khi thêm hoặc thay đổi affordance, có thể đi theo quy trình:

1. Xác định workflow và trạng thái nghiệp vụ cho phép thao tác.
2. Xác định controller method, HTTP method, target và request model.
3. Gắn affordance vào link thích hợp bằng afford(...) và andAffordance(...).
4. Bật media type hỗ trợ affordance như HAL-FORMS.
5. Tạo fixture cho trạng thái thao tác được phép và không được phép.
6. Dùng MockMvc GET với Accept: application/prs.hal-forms+json.
7. Kiểm tra method, target, content type và input properties trong _templates.
8. Kiểm tra response khi không có affordance và xác minh Content-Type fallback.
9. Gửi request theo template để xác nhận endpoint thực thi đúng.
10. Kiểm tra validation, authorization và trạng thái thay đổi sau khi client đọc representation.
11. Thêm contract test cho các trường hợp thay đổi affordance trong tương lai.
12. Đánh giá tương thích nếu template hoặc semantics đã được client sử dụng.

## 13. Kết luận

Kiểm thử affordance cần xác minh cả metadata được công bố và hành vi HTTP thực tế. Với Spring HATEOAS, affordance có thể được tạo từ controller method hoặc khai báo thủ công, sau đó được media type hỗ trợ chuyển thành representation phù hợp. HAL-FORMS cung cấp _templates để client khám phá method, target, content type và input properties.

Một bộ test đầy đủ cần bao gồm trạng thái thao tác được phép, trạng thái không được phép, serialization HAL-FORMS, nhánh fallback về HAL khi không có template, request thực tế, validation và authorization. Affordance giúp client hiểu khả năng của resource tại thời điểm nhận representation; server vẫn phải kiểm tra lại mọi điều kiện khi request đến. Khi kiểm thử cả hai phía, nhóm bảo vệ được hợp đồng hypermedia và tránh tình trạng client nhìn thấy một thao tác nhưng không thể thực hiện đúng.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances): tạo affordance từ controller method và API xây dựng thủ công.
- [Spring HATEOAS Reference — HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms): cấu hình HAL-FORMS, template metadata và input properties.
- [Spring HATEOAS API — Affordances](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/Affordances.html): API tạo affordance thủ công.
- [Spring HATEOAS API — HalFormsHttpMessageConverter](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/forms/HalFormsHttpMessageConverter.html): cách converter kiểm tra template và media type fallback.
- [Spring Framework — MockMvc Expectations](https://docs.spring.io/spring/reference/testing/mockmvc/hamcrest/expectations.html): kiểm tra response và hypermedia links bằng JSONPath.



