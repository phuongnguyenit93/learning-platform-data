# Dự án thực hành: Cấu hình HAL với Spring HATEOAS

Trong dự án này, bạn sẽ cấu hình một REST API Spring Boot để trả representation theo HAL JSON. API có entry point, collection đơn hàng và resource đơn; mỗi response công bố relation trong _links, collection dùng _embedded và client khám phá URL từ response thay vì tự ghép đường dẫn.

Mục tiêu không chỉ là thêm dependency để JSON xuất hiện trường _links. Bạn sẽ cấu hình đúng cơ chế hypermedia cho Spring MVC, chọn media type, đặt tên relation ổn định, tạo link bằng controller mapping, kiểm tra nội dung HAL qua MockMvc và xử lý các lỗi cấu hình thường gặp. Ví dụ dùng một service in-memory để tập trung vào cấu hình và representation; sau khi hoàn thành, có thể thay service bằng Spring Data mà không đổi nguyên tắc tạo HAL.

## 1. Kết quả cần đạt

Sau khi hoàn thành, API có thể:

- Trả entry point tại /api với relation orders.
- Trả collection đơn hàng dưới relation _embedded.orders.
- Trả resource đơn hàng với self link và link quay về collection.
- Dùng application/hal+json khi client yêu cầu HAL.
- Tạo href dựa trên Spring MVC mapping bằng WebMvcLinkBuilder.
- Giữ tên item relation và collection relation ổn định.
- Kiểm thử status, Content-Type, _links và _embedded.

Luồng khám phá dự kiến:

~~~mermaid
flowchart TD
    A[GET /api] -->|orders| B[GET /api/orders]
    B -->|item self| C[GET /api/orders/{id}]
    C -->|orders| B
~~~

Client chỉ cần biết entry point và relation names đã được tài liệu hóa. Href cụ thể được server công bố ở runtime.

## 2. Chuẩn bị project và dependency

Tạo một Spring Boot project dùng Java phù hợp với phiên bản Spring Boot mà dự án đang chọn. Thêm các dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-hateoas</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Để Spring Boot dependency management quản lý version cho các starter. Không khai báo một version Spring HATEOAS riêng lệch khỏi dependency set do Spring Boot quản lý, trừ khi dự án chủ động override và đã kiểm tra compatibility.

Starter hateoas ở ví dụ này dành cho Spring MVC. Nếu ứng dụng dùng WebFlux, không ghép spring-boot-starter-hateoas với spring-boot-starter-webflux; dùng dependency org.springframework.hateoas:spring-hateoas cùng starter WebFlux và cấu hình stack tương ứng.

## 3. Cấu trúc package của project

Có thể tổ chức mã nguồn như sau:

~~~text
src/main/java/com/example/orders/
  OrdersApplication.java
  api/
    ApiRootController.java
    OrderController.java
  application/
    OrderQueryService.java
  representation/
    OrderSummary.java
    OrderModelAssembler.java

src/main/resources/
  application.yml

src/test/java/com/example/orders/
  OrderHalIntegrationTest.java
~~~

Tách DTO representation và assembler khỏi service giúp phần truy vấn không phải biết về HTTP link. Controller chỉ điều phối request và trả hypermedia model; Spring HATEOAS cùng message converter chịu trách nhiệm serialize model thành HAL.

## 4. Cấu hình Spring Boot auto-configuration

Với Spring Boot, dependency spring-boot-starter-hateoas kích hoạt auto-configuration cho Spring HATEOAS. Boot đăng ký hạ tầng cần thiết để serialize RepresentationModel theo hypermedia format, cung cấp LinkDiscoverers và cấu hình JsonMapper phù hợp.

Vì vậy, ứng dụng Spring Boot thông thường không cần thêm @EnableHypermediaSupport. Hãy bắt đầu với application class đơn giản:

~~~java
@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Không tự tạo một ObjectMapper/JsonMapper bằng constructor mặc định để serialize EntityModel hoặc CollectionModel. Mapper tự tạo có thể thiếu module và cấu hình hypermedia mà Boot đã đăng ký. Nếu cần tùy chỉnh Jackson, ưu tiên các thuộc tính spring.jackson.* hoặc builder customizer phù hợp với dòng Spring Boot đang dùng (JsonMapperBuilderCustomizer ở Boot mới, Jackson2ObjectMapperBuilderCustomizer ở các dòng Boot cũ hơn) để giữ lại cấu hình auto-configuration.

## 5. Chọn chính sách media type cho HAL

HAL JSON dùng media type application/hal+json. Spring Boot mặc định cho phép request chấp nhận application/json nhận response HAL khi ứng dụng dùng Spring HATEOAS. Hành vi này tiện cho migration, nhưng có thể làm client không nhận ra rằng response chứa hypermedia controls.

Trong project thực hành này, controller khai báo produces = MediaTypes.HAL_JSON_VALUE và các ví dụ request gửi Accept: application/hal+json để thể hiện rõ contract. Cấu hình mặc định của Boot vẫn cho phép một client chỉ gửi Accept: application/json nhận HAL.

Nếu API muốn tắt hành vi mặc định đó, có thể đặt spring.hateoas.use-hal-as-default-json-media-type thành false. Khi chủ động tắt, cần cung cấp HypermediaMappingInformation hoặc HalConfiguration phù hợp để Spring HATEOAS biết mapping representation cần dùng. Không chỉ đặt property false rồi cho rằng mọi cấu hình HAL khác sẽ tự suy ra.

Nếu API hiện tại có client phụ thuộc vào hành vi application/json nhận HAL, hãy đánh giá compatibility trước khi đổi thuộc tính và kiểm thử consumer.

## 6. Tạo representation DTO và đặt tên relation

Tạo OrderSummary chỉ chứa dữ liệu đơn hàng được phép công bố:

~~~java
package com.example.orders.representation;

import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderSummary(
        UUID id,
        String orderNumber,
        String status,
        BigDecimal total
) {}
~~~

Annotation Relation chỉ rõ:

- itemRelation = order: relation của một item trong collection.
- collectionRelation = orders: tên relation được dùng cho collection embedded.

Đặt tên relation một cách có chủ đích để client không phụ thuộc vào pluralization ngẫu nhiên hoặc tên class Java. Nếu đổi relation name sau khi client đã sử dụng, đó là thay đổi contract cần đánh giá tương thích.

Không thêm các field như selfUrl hoặc cancelUrl vào DTO. Các URL sẽ được tạo thành Link trong assembler.

## 7. Tạo service cung cấp dữ liệu mẫu

Để project chạy độc lập, tạo service in-memory:

~~~java
package com.example.orders.application;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import com.example.orders.representation.OrderSummary;

@Service
public class OrderQueryService {

    private final List<OrderSummary> orders;

    public OrderQueryService() {
        UUID firstId = UUID.fromString(
                "11111111-1111-1111-1111-111111111111");
        UUID secondId = UUID.fromString(
                "22222222-2222-2222-2222-222222222222");

        orders = List.of(
                new OrderSummary(
                        firstId, "ORD-1001", "PENDING",
                        new BigDecimal("125000")),
                new OrderSummary(
                        secondId, "ORD-1002", "SHIPPED",
                        new BigDecimal("89000"))
        );
    }

    public List<OrderSummary> findAll() {
        return orders;
    }

    public OrderSummary findById(UUID id) {
        OrderSummary order = orders.stream()
                .filter(candidate -> candidate.id().equals(id))
                .findFirst()
                .orElse(null);

        if (order == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found");
        }

        return order;
    }
}
~~~

Service chỉ trả dữ liệu. Nó không biết endpoint nào tạo self link, không import Link và không phụ thuộc vào Servlet request.

## 8. Tạo RepresentationModelAssembler

Assembler chuyển OrderSummary thành EntityModel và thêm link:

~~~java
package com.example.orders.representation;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import com.example.orders.api.OrderController;

@Component
public class OrderModelAssembler implements
        RepresentationModelAssembler<OrderSummary,
                EntityModel<OrderSummary>> {

    @Override
    public EntityModel<OrderSummary> toModel(OrderSummary order) {
        return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                        .one(order.id()))
                        .withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .all())
                        .withRel("orders")
        );
    }
}
~~~

methodOn tạo một controller method invocation proxy để Spring HATEOAS đọc mapping và tham số. Nó không gửi HTTP request và không thực thi logic nghiệp vụ của controller. linkTo dùng mapping đó để tạo href.

Mỗi item có self relation trỏ tới chính đơn hàng và orders relation trỏ lại collection. Nếu muốn relation collection chỉ xuất hiện ở cấp collection, có thể bỏ link orders khỏi item; ví dụ này giữ nó để minh họa khả năng điều hướng hai chiều.

## 9. Tạo collection controller

Controller khai báo media type HAL và trả CollectionModel:

~~~java
package com.example.orders.api;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.orders.application.OrderQueryService;
import com.example.orders.representation.OrderModelAssembler;
import com.example.orders.representation.OrderSummary;

@RestController
@RequestMapping(
        path = "/api/orders",
        produces = MediaTypes.HAL_JSON_VALUE
)
public class OrderController {

    private final OrderQueryService queryService;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderQueryService queryService,
            OrderModelAssembler assembler) {
        this.queryService = queryService;
        this.assembler = assembler;
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderSummary>> all() {
        return assembler.toCollectionModel(queryService.findAll())
                .add(linkTo(methodOn(OrderController.class)
                        .all())
                        .withSelfRel());
    }

    @GetMapping("/{id}")
    public EntityModel<OrderSummary> one(
            @PathVariable UUID id) {
        return assembler.toModel(queryService.findById(id));
    }
}
~~~

CollectionModel giữ các item model trong collection và link self ở cấp collection. Tên embedded relation orders được lấy từ @Relation trên OrderSummary. Endpoint chỉ sản xuất HAL JSON; client gửi Accept không tương thích sẽ không được trả về representation HAL theo mapping này.

## 10. Tạo entry point API

Client nên có một URI gốc để bắt đầu traversal. Tạo model rỗng có links:

~~~java
package com.example.orders.api;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(path = "/api", produces = MediaTypes.HAL_JSON_VALUE)
public class ApiRootController {

    @GetMapping
    public RepresentationModel<?> root() {
        RepresentationModel<?> model = new RepresentationModel<>();
        model.add(linkTo(methodOn(OrderController.class)
                .all())
                .withRel("orders"));
        return model;
    }
}
~~~

Root response không cần chứa dữ liệu đơn hàng. Nó chỉ công bố entry relation orders. Client đọc href trong relation này rồi mới gọi collection.

## 11. Kiểm tra response HAL dự kiến

Gọi entry point:

~~~http
GET /api
Accept: application/hal+json
~~~

Response có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "_links": {
    "orders": {
      "href": "http://localhost:8080/api/orders"
    }
  }
}
~~~

Gọi collection:

~~~http
GET /api/orders
Accept: application/hal+json
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "_embedded": {
    "orders": [
      {
        "id": "11111111-1111-1111-1111-111111111111",
        "orderNumber": "ORD-1001",
        "status": "PENDING",
        "total": 125000,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/11111111-1111-1111-1111-111111111111"
          },
          "orders": {
            "href": "http://localhost:8080/api/orders"
          }
        }
      },
      {
        "id": "22222222-2222-2222-2222-222222222222",
        "orderNumber": "ORD-1002",
        "status": "SHIPPED",
        "total": 89000,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/22222222-2222-2222-2222-222222222222"
          },
          "orders": {
            "href": "http://localhost:8080/api/orders"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders"
    }
  }
}
~~~

Đây là ví dụ minh họa; host có thể khác theo môi trường, reverse proxy hoặc cấu hình forwarded headers. Client không nên so sánh chuỗi href với localhost mà nên theo relation và href nhận được.

Gọi một item bằng self href của item. Response đơn lẻ có payload order cùng _links.self và _links.orders. Như vậy client có thể đi từ root tới collection, từ collection tới item và từ item quay lại collection.

## 12. Xác nhận content negotiation

Request sau là cách rõ ràng nhất để client yêu cầu HAL:

~~~http
GET /api/orders
Accept: application/hal+json
~~~

Server trả 200 và Content-Type application/hal+json. Với cấu hình Spring Boot mặc định, client chỉ gửi Accept: application/json cũng có thể nhận application/hal+json. Nếu API muốn tắt hành vi này, hãy cấu hình property cùng HypermediaMappingInformation hoặc HalConfiguration và kiểm thử chính sách mới.

Nếu endpoint chỉ công bố HAL mà client gửi một media type không được hỗ trợ, ví dụ:

~~~http
GET /api/orders
Accept: application/xml
~~~

endpoint có thể trả 406 Not Acceptable. Nếu API muốn hỗ trợ thêm media type, cần cấu hình mapping/converter và contract cho từng representation; không chỉ đổi header để tuyên bố hỗ trợ mà không có serializer tương ứng.

## 13. Tùy chọn: cấu hình HAL không dùng Spring Boot

Nếu ứng dụng dùng Spring Framework MVC thuần và không có Spring Boot auto-configuration, hãy bật hypermedia support:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaWebConfiguration {
}
~~~

Annotation đăng ký các Jackson modules và hạ tầng cần thiết để render RepresentationModel theo HAL. Nó cũng có thể đăng ký LinkDiscoverer khi JSONPath có trên classpath và các relation providers liên quan.

Chọn cơ chế cấu hình phù hợp với kiểu ứng dụng. Trong Spring Boot thông thường, để auto-configuration xử lý là đủ. Khi chủ động dùng @EnableHypermediaSupport để kiểm soát cấu hình, lưu ý rằng điều này tắt một phần JsonMapper customization mà Boot cung cấp.

## 14. Tùy chọn: mở rộng relation bằng CURIE

Khi API có nhiều extension relation, CURIE giúp công bố tên ngắn cùng URI template để client tra cứu relation đầy đủ. Ví dụ API có relation ex:cancel và prefix ex trỏ tới URI template của tài liệu relation.

Spring HATEOAS hỗ trợ CurieProvider. Một ứng dụng chỉ nên đăng ký một CurieProvider cho mỗi application scope. Cấu hình này chỉ cần thiết khi API thật sự dùng CURIE; không thêm CURIE nếu relation set nhỏ và tên relation đã rõ.

Nếu bật CURIE, kiểm tra response có relation curies chứa prefix, href template và templated = true. Tài liệu API phải giải thích cách client mở rộng prefix thành URI relation đầy đủ.

## 15. Phân biệt HAL với HAL-FORMS

HAL cung cấp links để client khám phá resource. HAL-FORMS mở rộng mô hình đó bằng form templates mô tả input và method cho action. Hai media type không thể thay thế cho nhau.

| Định dạng | Media type | Thành phần chính |
| --- | --- | --- |
| HAL | application/hal+json | Payload, _links và _embedded. |
| HAL-FORMS | application/prs.hal-forms+json | HAL-like links cùng _templates mô tả form/action. |

Nếu project cần HAL-FORMS, phải bật support tương ứng và kiểm thử Accept header application/prs.hal-forms+json. Không chỉ thêm _templates thủ công vào JSON HAL rồi gọi response đó là HAL-FORMS.

## 16. Kiểm thử cấu hình HAL bằng MockMvc

Tạo integration test chạy toàn bộ Spring Boot context:

~~~java
package com.example.orders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderHalIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void rootPublishesOrdersRelation() throws Exception {
        mockMvc.perform(get("/api")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.orders.href").exists());
    }

    @Test
    void collectionUsesConfiguredHalRelations() throws Exception {
        mockMvc.perform(get("/api/orders")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._embedded.orders").isArray())
            .andExpect(jsonPath(
                    "$._embedded.orders[0]._links.self.href").exists());
    }
}
~~~

Test thứ nhất xác nhận entry point được serialize thành HAL và có relation orders. Test thứ hai khóa collection relation là orders, kiểm tra link self ở collection và item. Nếu relation name bị đổi ngoài ý muốn, test sẽ phát hiện.

## 17. Kiểm thử content negotiation và lỗi

Vì endpoint chỉ công bố HAL JSON, có thể xác nhận client yêu cầu XML bị từ chối:

~~~java
@Test
void rejectsUnsupportedAcceptHeader() throws Exception {
    mockMvc.perform(get("/api/orders")
            .accept(MediaType.APPLICATION_XML))
        .andExpect(status().isNotAcceptable());
}
~~~

Test này kiểm tra endpoint chỉ sản xuất HAL JSON. Nếu API có thêm representation XML, hãy cập nhật test theo content negotiation thực tế của endpoint.

Với resource không tồn tại, test status 404. Nếu API có @RestControllerAdvice và Problem Details, bổ sung assertion content type application/problem+json và type/code theo error contract.

## 18. Chạy project và kiểm tra bằng HTTP client

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Gọi entry point:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Gọi collection:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/orders
~~~

Gọi một resource theo href lấy từ response collection:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/orders/11111111-1111-1111-1111-111111111111
~~~

Trong thực tế, bước cuối nên lấy URL từ _links.self.href thay vì hard-code. URL viết trực tiếp ở đây chỉ để minh họa cách kiểm tra endpoint bằng terminal.

## 19. Checklist xác nhận HAL đã được cấu hình đúng

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Starter | Có spring-boot-starter-hateoas trong project MVC. |
| Auto-configuration | Spring Boot khởi tạo hypermedia infrastructure. |
| Media type | Request HAL nhận Content-Type application/hal+json. |
| Root | Có relation orders. |
| Item | Có _links.self.href. |
| Collection | Có _embedded.orders và _links.self. |
| Relation naming | Item relation và collection relation ổn định. |
| Link building | href được tạo từ controller mapping. |
| Serialization | Không tự tạo ObjectMapper làm mất HAL modules. |
| Tests | MockMvc xác nhận body, headers và content negotiation. |

## 20. Lỗi thường gặp và cách xử lý

**Response không có _links.** Kiểm tra controller có trả EntityModel/CollectionModel/PagedModel hay DTO thuần. Kiểm tra dependency và hypermedia auto-configuration đã được kích hoạt.

**Response có link nhưng Content-Type là application/json.** Kiểm tra Accept header, produces mapping và thuộc tính use-hal-as-default-json-media-type. Không dựa vào Content-Type đoán từ body.

**Request trả 406.** Client có thể gửi Accept không tương thích với produces. Gửi application/hal+json hoặc cấu hình thêm representation media type có serializer thực sự.

**Embedded relation có tên ngoài dự kiến.** Kiểm tra @Relation trên representation type và collectionRelation/itemRelation. Khóa tên bằng contract test.

**Href chứa host hoặc scheme sai.** Kiểm tra reverse proxy và forwarded headers. Không hard-code base URL trong assembler; dùng controller mapping để Spring HATEOAS xây link theo request context.

**Tự tạo ObjectMapper khiến _links serialize sai.** Không dùng new ObjectMapper() thay thế mapper do Boot cấu hình. Dùng spring.jackson.* hoặc JsonMapperBuilderCustomizer khi cần tùy chỉnh.

**Thêm @EnableHypermediaSupport vào ứng dụng Boot mà không hiểu tác động.** Annotation này cho phép kiểm soát cấu hình nhưng có thể tắt JsonMapper customization của Boot. Chỉ dùng khi có yêu cầu rõ ràng.

**Dùng starter HATEOAS với WebFlux.** Starter này dành cho Spring MVC. Với WebFlux, dùng spring-hateoas trực tiếp cùng starter WebFlux và cấu hình hypermedia cho stack đó.

**Nhầm HAL với HAL-FORMS.** Kiểm tra media type và cấu trúc tương ứng. HAL không tự mô tả form input; HAL-FORMS dùng media type và templates riêng.

## 21. Mở rộng dự án sau khi hoàn thành

Sau khi HAL cơ bản hoạt động, có thể mở rộng theo các hướng:

1. Thay in-memory service bằng Spring Data repository và DTO projection.
2. Dùng PagedModel cùng PagedResourcesAssembler để thêm pagination links.
3. Thêm search relation và URI template cho filter/sort.
4. Thêm relation customer hoặc items và quyết định link hay embedded.
5. Thêm affordance/HAL-FORMS cho cancel hoặc update action.
6. Thêm CURIE nếu API có nhiều extension relations.
7. Thêm Problem Details cho lỗi và link help/describedby.
8. Kiểm thử compatibility của relation names và media types trong CI.

Mỗi bước mở rộng cần giữ nguyên nguyên tắc: dữ liệu resource nằm trong payload, quan hệ và điều hướng nằm trong links, action metadata nằm trong affordance khi được hỗ trợ, còn HTTP metadata nằm trong status và headers.

## 22. Bài tập tự đánh giá

1. Vì sao ứng dụng Spring Boot có spring-boot-starter-hateoas thường không cần @EnableHypermediaSupport?
2. Media type nào được dùng cho HAL JSON?
3. Khác biệt giữa itemRelation và collectionRelation là gì?
4. Vì sao nên dùng methodOn thay vì tự nối URL trong assembler?
5. Điều gì có thể xảy ra nếu tự tạo ObjectMapper?
6. Vì sao không nên coi HAL và HAL-FORMS là cùng một media type?
7. Khi nào nên đặt use-hal-as-default-json-media-type thành false?
8. Những assertion nào chứng minh response collection là HAL thay vì JSON phẳng?

## Tiêu chí hoàn thành dự án

Dự án được xem là hoàn thành khi ứng dụng khởi động thành công; GET /api và GET /api/orders trả HAL JSON; collection relation là orders; item có self link; client có thể theo href để mở resource; content negotiation tuân thủ chính sách đã chọn; và MockMvc tests xác nhận media type cùng cấu trúc HAL.

Bạn đã cấu hình HAL khi có thể giải thích cả phần hạ tầng serialization lẫn contract mà client nhìn thấy. Một cấu hình đúng không chỉ làm xuất hiện _links; nó còn giữ relation ổn định, link được tạo từ mapping thật, media type được công bố rõ và các response có thể được kiểm chứng tự động.

## Tài liệu tham khảo chính thức

- [Spring Boot – Spring HATEOAS auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS – EnableHypermediaSupport API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/EnableHypermediaSupport.html)
- [HAL – Hypertext Application Language](https://stateless.group/hal_specification.html)
- [HAL-FORMS – Specification](https://rwcbook.github.io/hal-forms/)
