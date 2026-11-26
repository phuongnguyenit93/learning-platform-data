# ResourceModel trong MVC

## Mục tiêu

Trong Spring MVC, controller thường trả DTO hoặc entity để Spring ghi thành JSON. Với REST API theo HATEOAS, response còn cần links và có thể có embedded resources để client khám phá những bước tiếp theo. Spring HATEOAS cung cấp các representation model để controller trả về dữ liệu cùng hypermedia trong luồng xử lý MVC.

Tên gọi “ResourceModel” trong bài này nói tới mô hình biểu diễn tài nguyên. Trong API Spring HATEOAS hiện đại, lớp nền là **RepresentationModel**; không có lớp chính thức tên ResourceModel. Các kiểu như EntityModel, CollectionModel và PagedModel mở rộng mô hình này cho từng loại response.

Nếu đọc tutorial cũ của Spring HATEOAS trước phiên bản 1.0, bạn có thể gặp các tên sau:

| API cũ | API hiện tại |
|---|---|
| ResourceSupport | RepresentationModel |
| Resource | EntityModel |
| Resources | CollectionModel |
| PagedResources | PagedModel |
| ResourceAssembler | RepresentationModelAssembler |

Vì vậy, khi gặp ví dụ dùng ResourceSupport hoặc Resource, hãy hiểu đó là API cũ và đối chiếu với kiểu hiện tại trước khi áp dụng vào dự án mới.

Sau bài học, bạn có thể:

- Hiểu vị trí của representation model trong luồng Spring MVC.
- Phân biệt RepresentationModel, EntityModel, CollectionModel và PagedModel.
- Trả representation model trực tiếp từ controller.
- Tạo links dựa trên mapping của controller bằng WebMvcLinkBuilder.
- Bật hypermedia support cho ứng dụng Spring MVC.
- Phân biệt cấu hình thủ công với auto-configuration của Spring Boot.
- Kiểm thử response HAL qua MockMvc.

## Representation model nằm ở đâu trong Spring MVC?

Trong Spring MVC, controller nhận request và trả về một giá trị. Nếu giá trị được trả như response body, Spring MVC chọn HttpMessageConverter phù hợp để ghi object thành HTTP response. Với JSON, converter thường dùng Jackson.

Spring HATEOAS tích hợp vào luồng này: controller trả về một RepresentationModel; hypermedia support cung cấp Jackson module để chuyển links và embedded resources sang cấu trúc của media type được thương lượng, chẳng hạn HAL JSON.

~~~mermaid
flowchart TD
    A[HTTP request] --> B[DispatcherServlet]
    B --> C[Controller method]
    C --> D[RepresentationModel]
    D --> E[HttpMessageConverter]
    E --> F[Jackson và Hypermedia module]
    F --> G[HAL JSON response]
    G --> H[HTTP client]
~~~

Controller không cần tự ghép chuỗi JSON hoặc tự chuyển links thành object map. Nó tập trung tạo representation; Spring MVC và Spring HATEOAS đảm nhiệm phần ghi response theo media type.

Ví dụ client yêu cầu:

~~~http
GET /api/orders/42
Accept: application/hal+json
~~~

Server có thể trả dữ liệu đơn hàng cùng relation self và collection:

~~~json
{
  "id": "42",
  "status": "PAID",
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "collection": {
      "href": "/api/orders"
    }
  }
}
~~~

Client đọc relation để tìm link cần dùng và theo href server cung cấp. Client không phải tự đoán cấu trúc URL từ ID hoặc tên controller.

## Các kiểu representation model

Spring HATEOAS cung cấp một hệ kiểu xoay quanh RepresentationModel:

| Kiểu | Dùng khi nào? | Nội dung chính |
|---|---|---|
| RepresentationModel<T> | Cần model riêng chứa thuộc tính của representation và links. | Dữ liệu do lớp con định nghĩa cùng links. |
| EntityModel<T> | Muốn bọc một object hoặc DTO thành representation của một item. | Một content object và links. |
| CollectionModel<T> | Muốn biểu diễn một collection resource. | Danh sách item và links cấp collection. |
| PagedModel<T> | Collection có metadata phân trang. | Item, links điều hướng và page metadata. |
| SlicedModel<T> | Kết quả dạng Slice, không cần tổng số phần tử. | Item và thông tin điều hướng theo slice. |

### RepresentationModel

RepresentationModel là lớp nền để tạo model riêng:

~~~java
import org.springframework.hateoas.RepresentationModel;

public class OrderModel extends RepresentationModel<OrderModel> {

    private final String id;
    private final String status;

    public OrderModel(String id, String status) {
        this.id = id;
        this.status = status;
    }

    public String getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Generic self-type cho phép các phương thức như add(link) trả lại chính kiểu model để có thể nối lời gọi. Lớp con chứa những thuộc tính mà API muốn công bố, còn RepresentationModel quản lý links.

### EntityModel, CollectionModel và PagedModel

Nếu không cần tạo lớp con riêng, có thể bọc DTO bằng EntityModel:

~~~java
import org.springframework.hateoas.EntityModel;

OrderResponse response = new OrderResponse("42", "PAID");
EntityModel<OrderResponse> model = EntityModel.of(response);
~~~

Links có thể được thêm sau khi tạo model hoặc truyền ngay vào factory method:

~~~java
EntityModel<OrderResponse> model =
        EntityModel.of(response, selfLink, collectionLink);
~~~

CollectionModel biểu diễn một collection resource:

~~~java
import java.util.List;
import org.springframework.hateoas.CollectionModel;

CollectionModel<OrderResponse> model =
        CollectionModel.of(orderResponses, collectionLink);
~~~

Các item có thể là DTO đơn giản hoặc representation model có links riêng. Link self của collection thuộc cấp collection; links self của từng item thuộc cấp item.

Khi collection có phân trang, thường dùng Page từ Spring Data và PagedResourcesAssembler để tạo PagedModel. PagedModel chứa page metadata và links như first, prev, self, next, last khi chúng có ý nghĩa. Controller không cần tự tính URI của từng trang.

## Trả representation model trực tiếp từ controller

Spring MVC có thể ghi một RepresentationModel làm response body như các object khác. Dùng @RestController để các giá trị trả về được xem là response body:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@ExposesResourceFor(Order.class)
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    EntityModel<OrderResponse> findById(@PathVariable UUID id) {
        Order order = orderService.findById(id);
        OrderResponse response = OrderResponse.from(order);

        Link self = linkTo(methodOn(OrderController.class)
                .findById(id))
                .withSelfRel();

        Link collection = linkTo(methodOn(OrderController.class)
                .findAll())
                .withRel(IanaLinkRelations.COLLECTION);

        return EntityModel.of(response, self, collection);
    }

    @GetMapping
    CollectionModel<EntityModel<OrderResponse>> findAll() {
        List<EntityModel<OrderResponse>> items =
                orderService.findAll().stream()
                        .map(this::toModel)
                        .toList();

        Link self = linkTo(methodOn(OrderController.class)
                .findAll())
                .withSelfRel();

        return CollectionModel.of(items, self);
    }

    private EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse response = OrderResponse.from(order);
        Link self = linkTo(methodOn(OrderController.class)
                .findById(order.getId()))
                .withSelfRel();

        return EntityModel.of(response, self);
    }
}
~~~

Ví dụ giả định OrderService trả domain object Order và OrderResponse.from(...) chuyển object đó thành DTO. Controller tạo một EntityModel cho từng item và một CollectionModel cho danh sách. Trong ứng dụng thực tế, có thể chuyển phần ánh xạ này sang RepresentationModelAssembler để tái sử dụng ở nhiều endpoint.

Nếu controller dùng @Controller thay vì @RestController, hãy đánh dấu method trả body bằng @ResponseBody hoặc trả ResponseEntity có body. Nếu không, Spring MVC có thể diễn giải giá trị trả về theo cơ chế xử lý view.

Có thể bọc representation bằng ResponseEntity khi cần điều khiển status hoặc header:

~~~java
import org.springframework.http.ResponseEntity;

ResponseEntity<EntityModel<OrderResponse>> response(
        EntityModel<OrderResponse> model) {
    return ResponseEntity.ok(model);
}
~~~

ResponseEntity không thay thế representation model. Nó điều khiển HTTP response; body vẫn là EntityModel được Spring HATEOAS serialize.

## Tạo links dựa trên Spring MVC mapping

Không nên rải chuỗi URL như /api/orders/42 ở nhiều nơi. Khi mapping thay đổi, các chuỗi tự ghép có thể bị bỏ sót. WebMvcLinkBuilder tạo link dựa trên mapping thực tế của controller:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(methodOn(OrderController.class)
        .findById(orderId))
        .withSelfRel();
~~~

methodOn(...) tạo proxy ghi nhận lời gọi method để Spring HATEOAS đọc mapping. Nó không gọi method controller thật, không truy vấn database và không gửi HTTP request. Giá trị @PathVariable được dùng để tạo URI tương ứng.

WebMvcLinkBuilder lấy thông tin request hiện tại để xây URI cơ sở và đọc mapping của controller. Vì vậy, link có thể bao gồm context path và host phù hợp với request đang xử lý.

Nếu ứng dụng chạy sau reverse proxy hoặc load balancer, URI công khai có thể khác host và scheme mà servlet container nhìn thấy. Spring Framework hỗ trợ forwarded headers; chỉ bật và tin các header này khi chúng đến từ proxy đáng tin cậy đã được cấu hình đúng. Không để client tùy ý điều khiển host của links qua forwarded headers.

## Cấu hình hypermedia support trong Spring MVC

Spring HATEOAS cần đăng ký các thành phần chuyển representation model thành media type hypermedia. Cách cấu hình phụ thuộc ứng dụng có dùng Spring Boot hay cấu hình Spring MVC thủ công.

### Ứng dụng Spring MVC không dùng Spring Boot auto-configuration

Có thể bật HAL support bằng @EnableHypermediaSupport:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
~~~

Annotation này đăng ký Jackson modules cần thiết để serialize EntityModel và CollectionModel theo định dạng hypermedia đã chọn. Nó cũng đăng ký hạ tầng liên quan như LinkDiscoverer và EntityLinks khi các điều kiện tương ứng được đáp ứng.

Mặc định Spring HATEOAS phát hiện web stack đang dùng. Nếu ứng dụng có cả Spring MVC và thành phần WebFlux cho outbound client nhưng chỉ muốn bật hỗ trợ hypermedia cho MVC, có thể giới hạn stack bằng thuộc tính stacks = WebStack.WEBMVC của @EnableHypermediaSupport.

Khi cần cấu hình tường minh, import WebStack từ org.springframework.hateoas.support:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;
import org.springframework.hateoas.support.WebStack;

@Configuration
@EnableHypermediaSupport(
        type = HypermediaType.HAL,
        stacks = WebStack.WEBMVC)
class MvcOnlyHypermediaConfiguration {
}
~~~

### Ứng dụng Spring Boot

Với Spring Boot, dependency thường dùng là spring-boot-starter-hateoas. Starter này dành cho Spring MVC; không kết hợp nó với spring-boot-starter-webflux trong cùng cấu hình ứng dụng WebFlux. Với WebFlux, dùng dependency spring-hateoas trực tiếp cùng starter WebFlux phù hợp.

Spring Boot cung cấp auto-configuration cho Spring HATEOAS, bao gồm JsonMapper được cấu hình để serialize representation. Vì vậy, ứng dụng Boot thông thường không cần thêm @EnableHypermediaSupport.

Chỉ dùng @EnableHypermediaSupport khi muốn tự kiểm soát cấu hình hypermedia. Việc bật annotation này làm thay đổi đường auto-configuration của Boot và tắt phần tùy biến JsonMapper được mô tả trong tài liệu Boot. Tránh đăng ký hai cơ chế cấu hình cạnh tranh mà không có lý do rõ ràng.

## Content negotiation và HAL JSON

Representation model có thể được serialize theo các hypermedia media type khác nhau. Client chỉ rõ định dạng mong muốn bằng header Accept:

~~~http
GET /api/orders/42
Accept: application/hal+json
~~~

Với HAL JSON, links được đặt trong _links và collection item liên quan có thể được đặt trong _embedded. Nếu endpoint khai báo produces, giá trị đó phải tương thích với media type mà client yêu cầu.

Trong test, Spring HATEOAS cung cấp MediaTypes.HAL_JSON:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists());
~~~

Với Spring Boot, cấu hình mặc định hiện hành có thể trả HAL JSON ngay cả khi client yêu cầu application/json. Có thể tắt hành vi đó bằng thuộc tính spring.hateoas.use-hal-as-default-json-media-type=false. Hành vi mặc định này thuộc cấu hình Boot; không nên suy rộng nó sang mọi ứng dụng Spring MVC cấu hình thủ công.

## EntityLinks và RepresentationModelProcessor

Khi nhiều controller cần tạo link tới collection hoặc item resource của cùng một loại domain, EntityLinks giúp tránh phụ thuộc trực tiếp vào class controller. Controller OrderController ở ví dụ trước đã khai báo @ExposesResourceFor(Order.class). Annotation cho Spring HATEOAS biết controller quản lý collection và item resources của kiểu Order. Mapping ở cấp class đại diện collection; mapping có path variable ở method đại diện item.

Khi hypermedia support được bật, Spring HATEOAS có thể phát hiện controller và tạo EntityLinks. Thành phần khác có thể inject EntityLinks để tạo link theo kiểu resource:

~~~java
import java.util.UUID;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.stereotype.Component;

@Component
class PaymentLinkFactory {

    private final EntityLinks entityLinks;

    PaymentLinkFactory(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    Link orderLink(UUID orderId) {
        return entityLinks.linkToItemResource(Order.class, orderId);
    }
}
~~~

EntityLinks hữu ích khi thành phần tạo link không cần biết OrderController cụ thể. Để cơ chế mặc định suy ra URI, controller cần tuân theo quy ước mapping collection ở cấp class và mapping item có path variable ID.

Spring HATEOAS cũng có thể gọi RepresentationModelProcessor cho các representation model được controller trả về. Processor phù hợp khi cần bổ sung links dùng chung sau khi controller hoặc assembler đã tạo model:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
class OrderHelpProcessor
        implements RepresentationModelProcessor<EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> process(
            EntityModel<OrderResponse> model) {

        if (!model.hasLink("help")) {
            model.add(Link.of("/docs/orders", "help"));
        }
        return model;
    }
}
~~~

Generic type giới hạn loại model mà processor nhận. Hãy dùng processor cho metadata hoặc links dùng chung; links phụ thuộc trạng thái của từng đơn hàng vẫn nên được tạo ở assembler hoặc logic tạo representation tương ứng.

## Kiểm thử tích hợp MVC

MockMvc kiểm thử toàn bộ đường đi từ mapping controller đến message converter và serializer hypermedia. Một test cơ bản:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$.id").value(orderId.toString()))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.collection.href").exists());
~~~

Với collection endpoint, kiểm tra _embedded và links cấp collection:

~~~java
mockMvc.perform(get("/api/orders")
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._embedded").exists());
~~~

Nên kiểm tra thêm:

- Client yêu cầu HAL JSON và nhận đúng Content-Type.
- Self link trỏ tới mapping tương ứng với path variable.
- Collection link thuộc cấp collection, còn self link item thuộc cấp item.
- Embedded relation đúng với @Relation hoặc LinkRelationProvider.
- Processor được gọi và bổ sung link dùng chung.
- Request media type không được hỗ trợ trả lỗi phù hợp.
- URI được tạo đúng khi ứng dụng có context path hoặc chạy sau proxy tin cậy.

Test trực tiếp một assembler không chứng minh Spring MVC đã serialize representation thành HAL. Ít nhất một test MockMvc nên bao phủ message converter và content negotiation.

## Những lỗi thường gặp

- **Tìm lớp tên ResourceModel:** API hiện đại dùng RepresentationModel; EntityModel, CollectionModel và PagedModel là các kiểu chuyên biệt.
- **Trả DTO thuần nhưng mong tự có _links:** DTO không tự trở thành hypermedia model. Hãy bọc bằng EntityModel hoặc tạo lớp kế thừa RepresentationModel.
- **Trả object từ @Controller mà thiếu @ResponseBody:** Spring MVC có thể xem kết quả là model cho view thay vì response body. Dùng @RestController hoặc @ResponseBody.
- **Tự ghép URL trong controller:** dùng WebMvcLinkBuilder để link theo mapping thực tế.
- **Tự serialize bằng ObjectMapper mới:** mapper riêng có thể thiếu module HATEOAS. Trả representation model để Spring MVC dùng converter đã cấu hình.
- **Thiếu hypermedia configuration:** ứng dụng MVC thủ công cần bật @EnableHypermediaSupport hoặc cấu hình media type tương đương.
- **Thêm @EnableHypermediaSupport không cần thiết trong Spring Boot:** Boot đã auto-configure; annotation có thể thay đổi cấu hình JsonMapper.
- **Nhầm HAL JSON với JSON thường:** kiểm tra Accept, produces và Content-Type.
- **Dùng starter MVC trong ứng dụng WebFlux:** chọn dependency theo web stack.
- **Tin forwarded headers từ mọi request:** chỉ chấp nhận header do proxy đáng tin cậy kiểm soát.

## Quy trình tích hợp representation model vào Spring MVC

1. Chọn representation type: RepresentationModel cho model riêng, EntityModel cho item, CollectionModel cho collection hoặc PagedModel cho trang.
2. Tạo DTO/model chỉ chứa dữ liệu được phép công khai.
3. Dùng WebMvcLinkBuilder hoặc EntityLinks để tạo links theo mapping MVC.
4. Trả representation model từ @RestController hoặc ResponseEntity body.
5. Bật hypermedia support thủ công nếu ứng dụng không dùng Spring Boot auto-configuration.
6. Thương lượng media type bằng Accept và xác minh Content-Type response.
7. Kiểm thử qua MockMvc để bao phủ controller, converter, serializer, links và embedded resources.

Spring MVC không cần một pipeline riêng để trả HATEOAS resource model. Controller trả representation model như response body thông thường; Spring HATEOAS bổ sung khả năng chuyển đổi hypermedia cho Spring MVC. Khi chọn đúng model type, tạo link từ mapping và cấu hình media type nhất quán, API có thể công bố dữ liệu cùng đường điều hướng trong một response dễ khám phá.

## Tài liệu tham khảo

- Spring HATEOAS Reference Documentation, Representation models: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models
- Spring HATEOAS Reference Documentation, Building links in Spring MVC: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder
- Spring HATEOAS Reference Documentation, Configuration: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#configuration
- Spring Boot Reference Documentation, Spring HATEOAS: https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html
