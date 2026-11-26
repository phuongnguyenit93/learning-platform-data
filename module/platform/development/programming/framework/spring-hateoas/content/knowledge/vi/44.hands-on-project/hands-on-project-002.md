# Thiết kế API root

Trong dự án thực hành này, bạn sẽ xây dựng điểm vào cho một REST API quản lý đơn hàng bằng Spring HATEOAS. Client chỉ cần biết URI khởi đầu /api; từ API root, client khám phá collection đơn hàng, collection khách hàng, rồi theo các link của từng resource để tiếp tục điều hướng.

API root là một resource hypermedia đóng vai trò điểm bắt đầu của API. Nó mô tả những entry point mà client có thể truy cập và tạo nền tảng để server thay đổi URI nội bộ mà không buộc client phải hardcode toàn bộ đường dẫn. API root không phải trang liệt kê mọi endpoint hoặc bản sao của OpenAPI document. Nó nên nhỏ, ổn định và tập trung vào các quan hệ điều hướng cấp cao.

## Kết quả cần đạt

Sau khi hoàn thành, API phải đáp ứng các yêu cầu:

1. GET /api trả HAL JSON và có link self.
2. API root công bố link orders và customers.
3. Client theo link orders để tải collection đơn hàng.
4. Collection đơn hàng có link self, up và các item trong _embedded.orders.
5. Mỗi đơn hàng có link self và link customer.
6. Client có thể theo link customer để tải representation khách hàng.
7. Collection khách hàng cũng có link self và up.
8. Test chứng minh client điều hướng bằng href nhận được từ response.

Luồng điều hướng mục tiêu:

~~~mermaid
flowchart TD
    A[GET /api] --> B[API root]
    B -->|orders| C[Orders collection]
    B -->|customers| D[Customers collection]
    C --> E[Order item]
    E -->|customer| F[Customer resource]
    C -->|up| B
    D -->|up| B
~~~

Các relation orders, customers, customer và up là một phần hợp đồng hypermedia. Giữ tên relation ổn định và mô tả chúng trong tài liệu API. Với API công khai cần khả năng liên kết giữa nhiều tổ chức, cân nhắc relation URI hoặc CURIE thay vì dựa vào tên ngắn chỉ có ý nghĩa trong phạm vi một API.

## Bước 1: Tạo project và thêm Spring HATEOAS

Tạo ứng dụng Spring Boot với Spring Web và Spring HATEOAS. Nếu dùng Maven, thêm dependency sau; phiên bản được quản lý bởi Spring Boot dependency management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-hateoas</artifactId>
</dependency>
~~~

Nếu dùng Gradle:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-hateoas'
~~~

Spring Boot tự cấu hình các thành phần hypermedia cần thiết khi starter được thêm vào. Với ứng dụng Spring MVC không dùng Spring Boot auto-configuration, cần đăng ký hỗ trợ hypermedia phù hợp với media type được chọn.

Để chạy integration test ở bước sau, thêm test starter nếu project chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
~~~

Có thể tổ chức source theo cấu trúc:

~~~text
src/main/java/com/example/orders/
  OrdersApiApplication.java
  ApiRootController.java
  OrderController.java
  CustomerController.java
  OrderView.java
  CustomerView.java
  OrderRepresentation.java
  CustomerRepresentation.java
  OrderModelAssembler.java
  DemoCatalog.java
src/test/java/com/example/orders/
  ApiRootIntegrationTests.java
~~~

Đặt package `com.example.orders;` ở đầu mỗi file Java trong cấu trúc trên. Mỗi top-level type trong các đoạn code tiếp theo nằm trong file riêng tương ứng; vì các type cùng package nên không cần import class nội bộ của project. Lớp khởi động tối thiểu:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApiApplication.class, args);
    }
}
~~~

Trong dự án này, API trả HAL JSON với media type application/hal+json. Các endpoint khai báo produces = MediaTypes.HAL_JSON_VALUE, còn client gửi Accept: application/hal+json.

## Bước 2: Xác định hợp đồng API trước khi viết controller

Thiết kế URI và relation dự kiến:

| Resource | URI trong ví dụ | Relation từ resource cha | Nội dung chính |
| --- | --- | --- | --- |
| API root | /api | Điểm khởi đầu | Link tới các collection |
| Orders collection | /api/orders | orders | Các đơn hàng |
| Order item | /api/orders/{id} | self trong item | Trạng thái, tổng tiền |
| Customer collection | /api/customers | customers | Các khách hàng |
| Customer item | /api/customers/{id} | customer từ đơn hàng | Tên hiển thị |

URI trên là mapping ban đầu của ứng dụng. Client chỉ cần biết URI root đã được cấu hình; những URI còn lại được khám phá qua link. Nếu sau này collection đơn hàng chuyển sang /api/sales/orders, server có thể đổi mapping và link builder sẽ phát ra href mới mà client không phải sửa đường dẫn hardcode.

API root chỉ công bố collection entry point. Nó không nhúng toàn bộ đơn hàng hoặc khách hàng. Collection chịu trách nhiệm trả item và link tới resource liên quan.

## Bước 3: Tạo DTO cho representation

Không trả JPA entity hoặc domain aggregate trực tiếp. Định nghĩa DTO nhỏ cho nội dung API:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

public record OrderView(
    UUID id,
    String status,
    BigDecimal total,
    UUID customerId
) {}

public record CustomerView(
    UUID id,
    String displayName
) {}

@Relation(value = "order", collectionRelation = "orders")
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}

@Relation(value = "customer", collectionRelation = "customers")
public record CustomerRepresentation(
    UUID id,
    String displayName
) {}
~~~

OrderView và CustomerView là dữ liệu đầu vào cho tầng trình bày. OrderRepresentation và CustomerRepresentation là cấu trúc body được công bố ra HTTP. Annotation @Relation đặt tên relation cho item và collection, nhờ vậy HAL collection có _embedded.orders và _embedded.customers ổn định thay vì phụ thuộc tên class hoặc tên biến Java.

Nếu dùng Java phiên bản chưa hỗ trợ record, thay các record bằng class bất biến có constructor và accessor tương ứng. Annotation @Relation đặt trên class representation.

## Bước 4: Tạo dữ liệu mẫu và read service

Để tập trung vào API root, project dùng dữ liệu trong bộ nhớ. Trong ứng dụng thật, thay phần này bằng repository và query service; contract hypermedia vẫn giữ nguyên.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DemoCatalog {

    private static final UUID CUSTOMER_A =
        UUID.fromString("11111111-1111-4111-8111-111111111111");
    private static final UUID CUSTOMER_B =
        UUID.fromString("22222222-2222-4222-8222-222222222222");

    private final List<CustomerView> customers = List.of(
        new CustomerView(CUSTOMER_A, "Nguyễn An"),
        new CustomerView(CUSTOMER_B, "Trần Bình")
    );

    private final List<OrderView> orders = List.of(
        new OrderView(
            UUID.fromString("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            "PENDING",
            new BigDecimal("1250000.00"),
            CUSTOMER_A
        ),
        new OrderView(
            UUID.fromString("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            "SHIPPED",
            new BigDecimal("890000.00"),
            CUSTOMER_B
        )
    );

    List<OrderView> orders() {
        return orders;
    }

    List<CustomerView> customers() {
        return customers;
    }

    OrderView requireOrder(UUID id) {
        return orders.stream()
            .filter(order -> order.id().equals(id))
            .findFirst()
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND));
    }

    CustomerView requireCustomer(UUID id) {
        return customers.stream()
            .filter(customer -> customer.id().equals(id))
            .findFirst()
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND));
    }
}
~~~

Dữ liệu mẫu dùng UUID cố định để request và test có kết quả lặp lại. requireOrder và requireCustomer trả 404 nếu resource không tồn tại. Ở ứng dụng thật, query phải giới hạn tenant và quyền truy cập trước khi trả dữ liệu.

## Bước 5: Tạo assembler cho đơn hàng

Assembler chuyển OrderView thành EntityModel<OrderRepresentation> và thêm link tới chính đơn hàng cùng khách hàng:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler implements
        RepresentationModelAssembler<
            OrderView,
            EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(OrderView order) {
        OrderRepresentation body = new OrderRepresentation(
            order.id(),
            order.status(),
            order.total()
        );

        return EntityModel.of(
            body,
            linkTo(methodOn(OrderController.class).one(order.id()))
                .withSelfRel(),
            linkTo(methodOn(CustomerController.class).one(order.customerId()))
                .withRel("customer")
        );
    }
}
~~~

methodOn(...) tạo proxy để Spring HATEOAS đọc mapping của method controller và dựng URI tương ứng. Method được gọi trên proxy chỉ dùng để mô tả mapping; logic controller không được thực thi tại thời điểm tạo link.

Assembler không tự gọi repository. Nó nhận đủ dữ liệu qua OrderView, tạo body và link. Khi resource có nhiều trạng thái và hành động, có thể thêm action link theo điều kiện nghiệp vụ đã được tính trước; endpoint thực thi vẫn phải xác minh quyền và trạng thái lần nữa.

## Bước 6: Tạo controller cho API root

API root là một RepresentationModel không cần body nghiệp vụ. Nó chứa self và link tới hai collection:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.RepresentationModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiRootController {

    @GetMapping(value = "/api", produces = MediaTypes.HAL_JSON_VALUE)
    public RepresentationModel<?> root() {
        RepresentationModel<?> model = new RepresentationModel<>();

        model.add(linkTo(
            methodOn(ApiRootController.class).root()
        ).withSelfRel());

        model.add(linkTo(
            methodOn(OrderController.class).all()
        ).withRel("orders"));

        model.add(linkTo(
            methodOn(CustomerController.class).all()
        ).withRel("customers"));

        return model;
    }
}
~~~

Điểm quan trọng là link được dựng từ controller mapping. Tránh nối chuỗi /api/orders trong nhiều nơi vì khi URI thay đổi, các chuỗi hardcode dễ bị bỏ sót. API root chỉ cần biết method đại diện cho collection; nó không cần biết dữ liệu của collection.

Response dự kiến có hình dạng:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api"
    },
    "orders": {
      "href": "http://localhost:8080/api/orders"
    },
    "customers": {
      "href": "http://localhost:8080/api/customers"
    }
  }
}
~~~

Host và scheme trong href được tạo theo request và cấu hình forwarded headers của ứng dụng. Trong production sau reverse proxy, cấu hình proxy/header forwarding đúng để Spring dựng public URL chính xác.

## Bước 7: Tạo collection và item controller cho đơn hàng

Controller dùng base mapping /api/orders. Collection trả CollectionModel với link self và up; mỗi item được chuyển qua assembler:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final DemoCatalog catalog;
    private final OrderModelAssembler assembler;

    OrderController(DemoCatalog catalog, OrderModelAssembler assembler) {
        this.catalog = catalog;
        this.assembler = assembler;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        List<EntityModel<OrderRepresentation>> content =
            catalog.orders().stream()
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(
            content,
            linkTo(methodOn(OrderController.class).all()).withSelfRel(),
            linkTo(methodOn(ApiRootController.class).root()).withRel("up")
        );
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
    )
    public EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        return assembler.toModel(catalog.requireOrder(id));
    }
}
~~~

Collection relation được đặt tên là orders nhờ @Relation trên OrderRepresentation. Mỗi item có self và customer. up là link điều hướng ngược về API root, giúp client không cần tự suy ra parent URI.

## Bước 8: Tạo controller cho khách hàng

Customer collection và item hoàn tất đường điều hướng từ order tới customer:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final DemoCatalog catalog;

    CustomerController(DemoCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EntityModel<CustomerRepresentation>> all() {
        List<EntityModel<CustomerRepresentation>> content =
            catalog.customers().stream()
                .map(this::toModel)
                .toList();

        return CollectionModel.of(
            content,
            linkTo(methodOn(CustomerController.class).all()).withSelfRel(),
            linkTo(methodOn(ApiRootController.class).root()).withRel("up")
        );
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
    )
    public EntityModel<CustomerRepresentation> one(@PathVariable UUID id) {
        return toModel(catalog.requireCustomer(id));
    }

    private EntityModel<CustomerRepresentation> toModel(
            CustomerView customer) {
        CustomerRepresentation body = new CustomerRepresentation(
            customer.id(),
            customer.displayName()
        );

        return EntityModel.of(
            body,
            linkTo(methodOn(CustomerController.class).one(customer.id()))
                .withSelfRel()
        );
    }
}
~~~

Customer item có link self. Client đã đi theo relation customer từ order thì không cần biết customer URI được tạo theo quy tắc nào.

## Bước 9: Kiểm tra bằng trình duyệt hoặc curl

Khởi động ứng dụng rồi gọi API root:

~~~bash
curl -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Đọc href của relation orders, rồi gọi URI đó:

~~~bash
curl -H "Accept: application/hal+json" http://localhost:8080/api/orders
~~~

Response collection dự kiến có dạng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "status": "PENDING",
        "total": 1250000.00,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
          },
          "customer": {
            "href": "http://localhost:8080/api/customers/11111111-1111-4111-8111-111111111111"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders"
    },
    "up": {
      "href": "http://localhost:8080/api"
    }
  }
}
~~~

Các giá trị href thực tế được dựng theo request. Response minh họa chỉ thể hiện cấu trúc và relation cần có.

Tiếp theo, lấy href từ relation customer của item và gọi URI đó. Client nhận representation khách hàng cùng link self. Hãy thử thay đổi class-level mapping của OrderController rồi kiểm tra link orders ở API root và link self của item tự cập nhật theo mapping mới.

## Bước 10: Viết integration test cho luồng khám phá

Test không nên chỉ kiểm tra một href hardcode. Hãy lấy link từ response trước rồi theo link đó trong request tiếp theo:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.net.URI;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class ApiRootIntegrationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void clientCanDiscoverOrdersAndFollowCustomerLink() throws Exception {
        MvcResult rootResponse = mockMvc.perform(
                get("/api").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.orders.href").exists())
            .andExpect(jsonPath("$._links.customers.href").exists())
            .andExpect(jsonPath("$._embedded").doesNotExist())
            .andReturn();

        String ordersHref = JsonPath.read(
            rootResponse.getResponse().getContentAsString(),
            "$._links.orders.href");

        String customersHref = JsonPath.read(
            rootResponse.getResponse().getContentAsString(),
            "$._links.customers.href");

        mockMvc.perform(
                get(URI.create(customersHref)).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.up.href").exists())
            .andExpect(jsonPath("$._embedded.customers[0]._links.self.href")
                .exists());

        MvcResult ordersResponse = mockMvc.perform(
                get(URI.create(ordersHref)).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.up.href").exists())
            .andExpect(jsonPath("$._embedded.orders[0]._links.self.href")
                .exists())
            .andExpect(jsonPath("$._embedded.orders[0]._links.customer.href")
                .exists())
            .andReturn();

        String customerHref = JsonPath.read(
            ordersResponse.getResponse().getContentAsString(),
            "$._embedded.orders[0]._links.customer.href");

        mockMvc.perform(
                get(URI.create(customerHref)).accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").exists())
            .andExpect(jsonPath("$.displayName").exists())
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Test dùng @SpringBootTest để xác minh cả mapping, assembler, serialization HAL và link builder trong một luồng. Dependency spring-boot-starter-test cung cấp MockMvc và test framework; JsonPath được dùng để đọc href do server trả về.

Nếu ứng dụng bật Spring Security, cấu hình test principal hoặc CSRF phù hợp với endpoint; GET trong ví dụ không cần CSRF token. Với API có xác thực, test cần gửi credential và xác nhận root chỉ công bố những link phù hợp với principal.

## Bước 11: Tiêu chí nghiệm thu

| Tiêu chí | Cách xác minh |
| --- | --- |
| API root có thể truy cập | GET /api trả 200 |
| Đúng media type | Content-Type tương thích application/hal+json |
| Root có self | Có _links.self.href |
| Root có collection links | Có _links.orders.href và _links.customers.href |
| Root không phình thành object graph | Không có _embedded trong root |
| Orders collection có điều hướng | Có self, up và _embedded.orders |
| Order item có quan hệ | Có self và customer |
| Customer resource có thể theo link | GET href customer trả 200 và self |
| Client không phải hardcode URI con | Test đọc href rồi gọi chính href đó |
| Mapping có thể thay đổi | Link được dựng từ controller mapping, không nối chuỗi thủ công |

## Bài tập mở rộng

Sau khi hoàn thành luồng cơ bản, mở rộng project theo từng yêu cầu:

1. Thêm relation search ở API root, trỏ tới endpoint tìm đơn hàng theo trạng thái.
2. Thêm pagination cho orders collection và công bố link first, prev, self, next, last khi phù hợp.
3. Thêm link cancel cho đơn hàng PENDING; bỏ link khi trạng thái không cho phép hủy.
4. Thêm profile hoặc describedby link để client tìm tài liệu hợp đồng API.
5. Tách relation custom thành URI relation và thêm CURIE nếu cần nhóm nhiều relation.
6. Bảo vệ collection theo tenant và xác nhận root không công bố resource mà principal không được truy cập.
7. Viết test đổi URI mapping để chứng minh client vẫn hoạt động khi theo href.

Với action link, nhớ rằng việc link xuất hiện chỉ mô tả khả năng tại thời điểm representation được tạo. Endpoint thực thi vẫn phải kiểm tra authorization và trạng thái nghiệp vụ để xử lý request cạnh tranh hoặc link đã cũ.

## Những lỗi cần tránh trong project

- **API root chứa mọi item:** root nên công bố collection entry point, không thay thế collection.
- **Client hardcode URI con:** client chỉ cấu hình root URI rồi theo relation/href.
- **Nối chuỗi URL trong assembler:** dùng WebMvcLinkBuilder để bám theo mapping.
- **Dùng tên Java làm relation vô tình:** định nghĩa relation ổn định bằng @Relation hoặc relation URI.
- **Collection thiếu self/up:** client khó làm mới collection hoặc quay về root.
- **Link trỏ tới endpoint chưa tồn tại:** mọi relation công bố phải có đích hoạt động và được kiểm thử.
- **Dùng entity làm response:** DTO giúp kiểm soát trường và tránh lazy loading.
- **Coi link là cơ chế authorization:** endpoint đích luôn phải xác minh quyền.
- **Không kiểm tra Accept:** test cần xác nhận media type HAL và content negotiation.
- **Chỉ assert href tĩnh:** test khám phá phải lấy href từ response trước đó.

## Tổng kết dự án

API root là hợp đồng điều hướng cấp cao của REST API. Trong project này, /api cung cấp link orders và customers; collection orders cung cấp link tới từng order; order cung cấp link customer; client đi qua các href thay vì tự ghép URI. Spring HATEOAS hỗ trợ cách làm này bằng RepresentationModel, CollectionModel, EntityModel, RepresentationModelAssembler và WebMvcLinkBuilder.

Khi hoàn tất, bạn có một API nhỏ nhưng có luồng khám phá rõ ràng, relation ổn định và test chứng minh client có thể bắt đầu từ một URI duy nhất. Đây là nền tảng để bổ sung pagination, search, action links, bảo mật theo quyền và tài liệu API trong các bước tiếp theo.

## Tài liệu tham khảo

- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS – Building links with Spring MVC](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder)
- [Spring HATEOAS – Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
- [HAL – Hypertext Application Language](https://datatracker.ietf.org/doc/html/draft-kelly-json-hal)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
