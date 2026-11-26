# Affordance là gì

## Mục tiêu

Một REST resource không chỉ cung cấp dữ liệu và các URI. Resource còn có thể mô tả những thao tác client có thể thực hiện trên nó, ví dụ xem chi tiết, cập nhật, hủy hoặc tìm kiếm. Trong hypermedia, mô tả về một thao tác khả dụng như vậy được gọi là affordance.

Spring HATEOAS gắn affordance với một Link. Link cho biết đích và quan hệ của đích với representation hiện tại; affordance bổ sung thông tin về cách tương tác với đích, chẳng hạn HTTP method, kiểu dữ liệu đầu vào, kiểu dữ liệu đầu ra và query parameters. Các media type hypermedia có thể chuyển metadata này thành cấu trúc phù hợp cho client.

Sau bài học, bạn có thể:

- Giải thích affordance và phân biệt affordance với Link thông thường.
- Hiểu các thông tin mà affordance mô tả cho một thao tác.
- Tạo affordance từ controller method bằng afford(methodOn(...)).
- Gắn nhiều affordance vào cùng một link.
- Dựng affordance thủ công bằng Affordances.
- Nhận biết cách HAL-FORMS biểu diễn affordance và kiểm thử metadata.
- Hiểu giới hạn của affordance về bảo mật và tính hợp lệ của request.

## Affordance là gì?

Affordance mô tả một khả năng tương tác mà server công bố cho client. Ví dụ, một đơn hàng có thể cho phép:

- Đọc thông tin đơn hàng bằng GET.
- Thay thế toàn bộ thông tin được phép cập nhật bằng PUT.
- Cập nhật một phần thuộc tính bằng PATCH.
- Hủy đơn hàng bằng POST tới một endpoint hành động.

Một link thông thường có thể công bố:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    }
  }
}
~~~

Client biết URI của đơn hàng. Tuy nhiên, chỉ từ href và relation self, client chưa biết hợp đồng cập nhật: có hỗ trợ PUT hay PATCH không, cần gửi payload nào, payload có trường gì và media type nào được chấp nhận.

Khi link có thêm affordances, server có thể mô tả các thao tác gắn với chính URI đó. Ví dụ, cùng URI /api/orders/42 có thể hỗ trợ GET để đọc, PUT để thay thế và PATCH để cập nhật một phần. Affordance cho client biết cách sử dụng URI theo hợp đồng mà server công bố.

Affordance không nhất thiết tạo ra một URI mới. Nhiều thao tác có thể cùng trỏ tới một URI nhưng dùng HTTP method hoặc payload khác nhau. Đây là lý do Spring HATEOAS cho phép gắn nhiều affordances vào một Link.

## Link và affordance bổ sung cho nhau

| Thành phần | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| href | Gửi request tới đâu? | /api/orders/42 |
| rel | URI này có quan hệ gì với resource hiện tại? | self, orders, cancel |
| HTTP method trong affordance | Client có thể dùng thao tác HTTP nào? | GET, PUT, PATCH |
| Input model | Client cần gửi dữ liệu đầu vào nào? | ReplaceOrderRequest |
| Output model | Thao tác dự kiến trả về kiểu representation nào? | OrderRepresentation |
| Query parameters | Có tham số truy vấn nào được hỗ trợ? | status, page, size |
| Tên affordance | Client hoặc giao diện có thể nhận diện thao tác ra sao? | replaceOrder, searchOrders |

Relation và affordance không thay thế nhau. Relation mô tả ngữ nghĩa của link; affordance mô tả thao tác gắn với link. Ví dụ, relation self nói link trỏ tới chính resource, còn affordance trên link đó có thể mô tả PUT và PATCH.

Affordance cũng không phải một biểu mẫu HTML. Nó là metadata có cấu trúc về thao tác và payload. Một hypermedia media type như HAL-FORMS có thể chuyển metadata đó thành template để client hoặc công cụ như HAL Explorer hiển thị biểu mẫu tương tác.

## Các thông tin một affordance có thể mô tả

Spring HATEOAS xây dựng affordance tổng quát từ các thông tin như:

- **Target link:** link mà thao tác hướng tới.
- **HTTP method:** GET, POST, PUT, PATCH, DELETE hoặc method khác.
- **Input payload:** kiểu dữ liệu client gửi trong request body.
- **Output payload:** kiểu dữ liệu mà thao tác dự kiến trả về.
- **Query parameters:** tham số truy vấn được endpoint hỗ trợ.
- **Input media type:** media type mà server chấp nhận cho payload.
- **Name:** tên nhận diện affordance, có thể được chỉ định hoặc suy ra.

Không phải media type nào cũng biểu diễn được toàn bộ metadata này. Spring HATEOAS giữ mô tả affordance ở dạng tổng quát, sau đó media type cụ thể quyết định cách serialize. HAL-FORMS có thể biểu diễn HTTP method và các thuộc tính của form; một định dạng chỉ biểu diễn link có thể không hiển thị toàn bộ mô tả đầu vào.

## Tạo affordance từ controller method

Đây là cách phổ biến khi ứng dụng dùng Spring MVC. Spring HATEOAS có thể phân tích mapping và chữ ký method để suy ra thông tin thao tác. Dùng methodOn(...) để tham chiếu method, afford(...) để tạo affordance từ method đó, rồi gắn nó vào Link bằng andAffordance(...).

Giả sử controller cung cấp endpoint đọc, thay thế và cập nhật một phần đơn hàng:

~~~java
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderRepresentation findOne(@PathVariable UUID id) {
        // Đọc đơn hàng.
        return null;
    }

    @PutMapping(path = "/{id}", consumes = MediaType.APPLICATION_JSON_VALUE)
    OrderRepresentation replaceOrder(
            @PathVariable UUID id,
            @RequestBody ReplaceOrderRequest request) {
        // Thay thế các trường được phép cập nhật.
        return null;
    }

    @PatchMapping(path = "/{id}", consumes = MediaType.APPLICATION_JSON_VALUE)
    OrderRepresentation patchOrder(
            @PathVariable UUID id,
            @RequestBody PatchOrderRequest request) {
        // Cập nhật một phần đơn hàng.
        return null;
    }
}
~~~

Request representation có thể khai báo các ràng buộc mà HAL-FORMS dùng để mô tả input properties:

~~~java
import jakarta.validation.constraints.NotNull;

record ReplaceOrderRequest(
        @NotNull String shippingAddress,
        String note) {
}

record PatchOrderRequest(String note) {
}
~~~

Khi tạo representation cho một đơn hàng, gắn affordances của hai method cập nhật vào link self:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

EntityModel<OrderRepresentation> toModel(Order order) {
    UUID id = order.getId();

    Link self = linkTo(methodOn(OrderController.class)
            .findOne(id))
            .withSelfRel()
            .andAffordance(afford(methodOn(OrderController.class)
                    .replaceOrder(id, null)))
            .andAffordance(afford(methodOn(OrderController.class)
                    .patchOrder(id, null)));

    return EntityModel.of(OrderRepresentation.from(order), self);
}
~~~

Trong ví dụ:

1. linkTo(methodOn(...).findOne(id)) tạo link self từ mapping GET.
2. afford(methodOn(...).replaceOrder(id, null)) mô tả thao tác PUT.
3. afford(methodOn(...).patchOrder(id, null)) mô tả thao tác PATCH.
4. andAffordance(...) gắn từng thao tác vào cùng link self.

methodOn(...) tạo proxy để ghi nhận method và tham số; nó không thực thi controller, không gọi service và không gửi request. null ở vị trí request body chỉ là giá trị placeholder khi tham chiếu method. Spring HATEOAS phân tích chữ ký và annotation như @PutMapping, @PatchMapping, @RequestBody để suy ra metadata cho affordance.

Kiểu trả về của method được tham chiếu qua methodOn cần hỗ trợ proxy theo cơ chế của Spring HATEOAS. Nếu method trả về kiểu không thể proxy, hãy dùng cách tạo link hoặc affordance khác được API hỗ trợ thay vì giả định mọi chữ ký đều dùng được với methodOn.

Đối với path variable, giá trị ID được dùng để tạo URI đích. Các tham số khác không nhất thiết được đưa vào href; query parameters và payload được mô tả theo mapping cùng metadata của method. Không truyền dữ liệu nghiệp vụ thật vào vị trí body chỉ để tạo affordance.

## Một link có thể có nhiều affordances

Một resource detail thường có link self duy nhất, nhưng có thể hỗ trợ nhiều thao tác trên cùng URI:

| Link | Affordance | Input | Ý nghĩa |
|---|---|---|---|
| self | GET | Không có body | Đọc resource. |
| self | PUT | ReplaceOrderRequest | Thay thế dữ liệu được phép cập nhật. |
| self | PATCH | PatchOrderRequest | Cập nhật một phần dữ liệu. |

Điều này khác với việc tạo ba link có cùng href nhưng relation tùy ý. Affordances cho phép gắn các cách tương tác khác nhau vào link có ý nghĩa ngữ nghĩa đã được công bố.

Nếu hành động có URI riêng, ví dụ /api/orders/42/cancellation, hãy tạo link relation cancel tới endpoint đó và có thể gắn affordance POST tương ứng. Chọn cách biểu diễn dựa trên thiết kế resource và hợp đồng HTTP của API.

## Dựng affordance thủ công bằng Affordances

Không phải lúc nào thao tác cũng tương ứng trực tiếp với một controller method. Có thể cần mô tả affordance từ HTTP method, kiểu payload và query parameters. Spring HATEOAS cung cấp API Affordances cho trường hợp này:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.hateoas.mediatype.QueryParameter;
import org.springframework.http.HttpMethod;

Link employeeCollection = Link.of("/api/employees", "employees");

Link collectionWithActions = Affordances.of(employeeCollection)
        .afford(HttpMethod.POST)
        .withInputAndOutput(Employee.class)
        .withName("createEmployee")
        .andAfford(HttpMethod.GET)
        .withOutput(Employee.class)
        .addParameters(
                QueryParameter.optional("name"),
                QueryParameter.optional("role"))
        .withName("searchEmployees")
        .toLink();
~~~

Đoạn code mô tả hai affordances trên cùng link collection:

- POST nhận và trả về model Employee, được đặt tên createEmployee.
- GET trả về Employee, đồng thời công bố hai query parameters tùy chọn name và role, được đặt tên searchEmployees.

Affordances.of(link) tạo ngữ cảnh từ link hiện có. afford(HttpMethod) bắt đầu mô tả thao tác. Các phương thức withInput(...), withOutput(...) hoặc withInputAndOutput(...) khai báo kiểu payload. addParameters(...) bổ sung query parameters. andAfford(...) kết thúc affordance hiện tại và bắt đầu mô tả thao tác tiếp theo. toLink() trả về link đã gắn metadata affordance.

Sử dụng cách dựng thủ công khi metadata không thể suy ra từ controller method hoặc khi cần mô tả một giao diện truy vấn đặc biệt. Nếu thao tác đã được khai báo rõ trong Spring MVC, cách tham chiếu method thường giúp tránh lặp lại HTTP method, payload type và query parameter.

## HAL-FORMS biểu diễn affordance như thế nào?

HAL cơ bản tập trung vào links và embedded resources. HAL-FORMS mở rộng HAL để mô tả các thao tác tương tác bằng _templates. Mỗi template có thể khai báo HTTP method, target, content type, title và danh sách properties mà client gửi.

Để bật HAL-FORMS trong cấu hình Spring HATEOAS:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
class HypermediaConfiguration {
}
~~~

Client yêu cầu media type application/prs.hal-forms+json qua header Accept. Khi response có affordances, serializer HAL-FORMS có thể chuyển chúng thành các template:

~~~http
GET /api/orders/42
Accept: application/prs.hal-forms+json
~~~

Ví dụ response rút gọn:

~~~json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/api/orders/42"
    }
  },
  "_templates": {
    "replaceOrder": {
      "method": "put",
      "contentType": "application/json",
      "properties": [
        {
          "name": "shippingAddress",
          "required": true
        },
        {
          "name": "note"
        }
      ]
    },
    "patchOrder": {
      "method": "patch",
      "contentType": "application/json",
      "properties": [
        {
          "name": "note"
        }
      ]
    }
  }
}
~~~

Tên template thường được suy ra từ tên controller method mà affordance tham chiếu, trừ khi tên được cấu hình tường minh. Nếu chỉ có một template, HAL-FORMS dùng tên default; khi có nhiều template, chúng có thể được nhận diện bằng tên affordance. Ví dụ trên minh họa cách client có thể khám phá hai thao tác cập nhật; hình dạng và thuộc tính thực tế phụ thuộc input model, annotation, cấu hình và phiên bản thư viện.

HAL-FORMS có thể suy ra một phần metadata thuộc tính từ kiểu input và các annotation validation. Ví dụ:

- @NotNull có thể làm property được mô tả là bắt buộc.
- @Pattern có thể cung cấp biểu thức kiểm tra định dạng.
- @Size, @Min, @Max có thể cung cấp giới hạn độ dài hoặc giá trị.
- @Email có thể giúp suy ra kiểu input phù hợp.

Trong ví dụ controller, consumes = application/json cho phép HAL-FORMS công bố contentType của template. Thuộc tính required mặc định là false nên serializer hiện hành có thể lược bỏ required=false; @NotNull làm trường shippingAddress được mô tả là bắt buộc.

Vì vậy, nên dùng request representation riêng làm input model. Kiểu này mô tả chính xác dữ liệu client được phép gửi, các trường bắt buộc và ràng buộc đầu vào. Không dùng entity persistence trực tiếp làm form payload nếu nó chứa trường nội bộ hoặc trường client không được quyền sửa.

HAL-FORMS là một media type riêng, không đồng nghĩa với HAL JSON. Client cần thương lượng đúng media type và xử lý _templates theo đặc tả HAL-FORMS. Một client chỉ hiểu HAL cơ bản có thể bỏ qua metadata affordance đặc thù của HAL-FORMS.

## Affordance giúp client khám phá hành động

Khi response công bố affordance, client có thể:

1. Đọc link để biết target URI.
2. Đọc affordance để biết HTTP method và payload cần chuẩn bị.
3. Dựa vào input metadata để tạo form hoặc request body.
4. Gửi request tới target với method và media type phù hợp.
5. Đọc response tiếp theo để khám phá các links và affordances mới.

Client không cần mã hóa cứng mọi URL và thao tác theo từng trạng thái của resource. Server có thể công bố thao tác phù hợp với resource hiện tại; khi trạng thái thay đổi, representation mới có thể công bố tập affordances khác.

Ví dụ, đơn hàng PENDING có thể công bố affordance cancel, còn đơn hàng SHIPPED không công bố affordance đó. Đây là cách server diễn đạt khả năng tương tác dựa trên trạng thái hiện tại. Client vẫn cần xử lý lỗi nếu trạng thái thay đổi giữa lúc đọc representation và lúc gửi request.

## Affordance không thay thế bảo mật hoặc validation

Affordance là metadata mô tả thao tác, không phải cơ chế cấp quyền. Việc response chứa affordance cancel không chứng minh client chắc chắn được phép hủy tại thời điểm request đến. Endpoint vẫn phải:

- Xác thực danh tính request.
- Kiểm tra quyền truy cập và quyền thực hiện thao tác.
- Kiểm tra trạng thái resource mới nhất.
- Validate payload theo quy tắc nghiệp vụ.
- Trả status HTTP thích hợp nếu thao tác không còn hợp lệ.

Tương tự, việc HAL-FORMS mô tả property là required hoặc cung cấp regex không thay thế validation phía server. Client có thể bỏ qua metadata hoặc gửi payload sai; server luôn là nơi thực thi quy tắc.

Chỉ công bố các thao tác mà client trong ngữ cảnh hiện tại nên khám phá. Nếu khả năng thao tác phụ thuộc người dùng, tenant hoặc trạng thái nghiệp vụ, hãy tạo representation dựa trên ngữ cảnh phù hợp và vẫn kiểm tra quyền ở endpoint.

## Kiểm thử affordance

Kiểm thử nên xác minh cả link đích lẫn metadata thao tác. Với HAL-FORMS, MockMvc có thể kiểm tra template và method:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_FORMS_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_FORMS_JSON))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._templates.replaceOrder.method")
                .value("put"))
        .andExpect(jsonPath("$._templates.patchOrder.method")
                .value("patch"));
~~~

Tên template trong assertion phải khớp tên affordance thực tế mà ứng dụng phát ra. Nếu dùng tên mặc định từ controller method, kiểm tra đúng tên method; nếu đặt tên tường minh qua API dựng thủ công, kiểm tra tên đã cấu hình.

Nên kiểm tra thêm:

- Input properties, required, type và contentType đúng với request model.
- Link target của affordance trỏ tới endpoint mong đợi.
- Resource ở trạng thái không cho phép thao tác thì không công bố affordance tương ứng.
- Client gửi request hợp lệ tới endpoint và nhận response đúng.
- Request thiếu quyền, sai payload hoặc trạng thái không hợp lệ vẫn bị server từ chối.

Nếu ứng dụng hỗ trợ cả HAL và HAL-FORMS, kiểm thử từng media type riêng. Không suy luận rằng metadata được hiển thị giống nhau ở mọi hypermedia format.

## Những lỗi thường gặp

- **Nhầm affordance với link:** link cung cấp đích và relation; affordance mô tả cách tương tác với đích.
- **Cho rằng relation edit đã mô tả đủ thao tác:** relation không tự cho biết PUT hay PATCH, payload hoặc media type.
- **Tạo một URI cho mỗi HTTP method dù không cần:** nhiều thao tác có thể cùng gắn vào một link khi target URI giống nhau.
- **Nghĩ methodOn(...) thực thi controller:** methodOn chỉ ghi nhận method invocation để phân tích mapping và metadata.
- **Truyền payload thật khi tạo affordance:** dùng null làm placeholder ở vị trí @RequestBody; không gửi request body trong lúc xây link.
- **Mặc định mọi media type đều hiển thị affordance:** metadata được chuyển đổi theo khả năng của từng media type. HAL-FORMS cung cấp _templates.
- **Dùng entity persistence làm input model:** request representation riêng giúp kiểm soát trường và validation mà client được phép gửi.
- **Coi affordance là quyền truy cập:** server vẫn phải xác thực, phân quyền và kiểm tra trạng thái khi request đến.
- **Không kiểm thử hợp đồng template:** đổi tên method hoặc input model có thể làm tên template và properties thay đổi, ảnh hưởng client.

## Quy trình thiết kế affordance

1. Xác định resource và link mà client cần điều hướng tới.
2. Liệt kê các thao tác hợp lệ trên target, cùng HTTP method của từng thao tác.
3. Khai báo controller method với input/output model và mapping phù hợp.
4. Dùng afford(methodOn(...)) để suy ra metadata từ method, hoặc dùng Affordances khi cần mô tả thủ công.
5. Gắn một hoặc nhiều affordances vào Link bằng andAffordance(...).
6. Chọn media type có khả năng biểu diễn metadata cần công bố, ví dụ HAL-FORMS cho form templates.
7. Kiểm thử link, method, payload properties, template name và hành vi endpoint thực tế.

Affordance giúp REST API công bố không chỉ nơi client có thể đi tới mà còn cách client có thể tương tác với resource. Khi Spring HATEOAS gắn affordance vào Link và media type chuyển metadata thành định dạng phù hợp, client có thể khám phá thao tác, chuẩn bị payload và tiếp tục điều hướng theo hợp đồng hypermedia do server cung cấp.
