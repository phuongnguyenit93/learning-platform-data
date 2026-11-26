# Thử client traversal

## Mục tiêu dự án

Trong dự án này, bạn sẽ xây một client Java dùng Spring HATEOAS Traverson để điều hướng một REST API theo các link mà server công bố. Client bắt đầu từ một URI entry point, tìm relation orders, tải collection và tiếp tục theo self link của item đầu tiên trong collection.

Mục tiêu là để client khám phá API qua hypermedia. Client chỉ cần biết URI entry point ban đầu và các relation thuộc hợp đồng API; nó không tự ghép đường dẫn như /api/orders/101 để gọi một đơn hàng cụ thể.

Sau khi hoàn thành, bạn có thể:

- Tạo API root công bố relation tới collection.
- Tạo collection HAL với relation được đặt tên rõ ràng.
- Dùng Traverson để theo một hoặc nhiều relation.
- Dùng JSONPath để chọn self link của item nhúng.
- Deserialize representation có generic bằng ParameterizedTypeReference.
- Kiểm thử client traversal qua HTTP thật với random port.
- Nhận biết những chỗ client vẫn phụ thuộc vào hợp đồng relation và media type.

## Bài toán

Một cửa hàng cung cấp API đơn hàng. Server có các endpoint đọc collection và item, nhưng client không nên biết trước route của từng endpoint.

Hãy xây luồng sau:

~~~text
API entry point
    |
    | relation: orders
    v
Orders collection
    |
    | self link của item đầu tiên trong _embedded.orders
    v
Order item
~~~

Client phải thực hiện các bước bằng links trong response:

1. Gọi URI entry point.
2. Tìm relation orders và theo href của nó.
3. Nhận collection representation.
4. Tìm self link của item đầu tiên trong embedded relation orders.
5. Theo self link đó và deserialize order item.

Nếu server đổi đường dẫn collection hoặc item nhưng giữ các relation và entry point, client vẫn có thể tiếp tục điều hướng.

## Chuẩn bị dự án

Tạo một ứng dụng Spring Boot dùng Java 17 trở lên và Spring MVC. Dùng Spring Boot dependency management để chọn các phiên bản tương thích:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-hateoas")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Tạo package ví dụ:

~~~text
com.example.orders
  OrderApiApplication.java
  ApiRoot.java
  ApiRootController.java
  Order.java
  OrderStatus.java
  OrderResponse.java
  OrderService.java
  OrderModelAssembler.java
  OrderController.java
  OrderTraversalClient.java
  OrderTraversalClientTest.java
~~~

Dự án dùng một ứng dụng để chạy API và một client component để gọi API qua HTTP. Integration test khởi động server trên cổng ngẫu nhiên rồi tạo Traverson với URI root tương ứng. Cách này kiểm tra cả việc tạo HAL ở server lẫn việc client thực sự khám phá và theo links.

## Bước 1: Tạo dữ liệu đơn hàng

Tạo enum trạng thái:

~~~java
package com.example.orders;

public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED
}
~~~

Tạo domain record:

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record Order(
        Long id,
        String customerName,
        BigDecimal total,
        OrderStatus status) {
}
~~~

Tạo DTO dùng trong representation:

~~~java
package com.example.orders;

import java.math.BigDecimal;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderResponse(
        Long id,
        String customerName,
        BigDecimal total,
        OrderStatus status) {
}
~~~

Annotation Relation khai báo relation dùng khi nhúng các item vào HAL collection. Trong bài này, collection relation là orders, vì vậy client có thể tìm item trong đường dẫn JSONPath $._embedded.orders.

Service dùng dữ liệu mẫu trong bộ nhớ:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final List<Order> orders = List.of(
            new Order(
                    101L,
                    "Nguyen An",
                    new BigDecimal("125000.00"),
                    OrderStatus.PAID),
            new Order(
                    102L,
                    "Tran Binh",
                    new BigDecimal("89000.00"),
                    OrderStatus.PENDING),
            new Order(
                    103L,
                    "Le Chi",
                    new BigDecimal("245000.00"),
                    OrderStatus.SHIPPED));

    public List<Order> findAll() {
        return orders;
    }

    public Optional<Order> findById(Long id) {
        return orders.stream()
                .filter(order -> order.id().equals(id))
                .findFirst();
    }
}
~~~

## Bước 2: Tạo assembler cho item resource

Assembler chuyển Order thành EntityModel và thêm self link dựa trên controller mapping:

~~~java
package com.example.orders;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse response = new OrderResponse(
                order.id(),
                order.customerName(),
                order.total(),
                order.status());

        return EntityModel.of(
                response,
                linkTo(methodOn(OrderController.class)
                        .findById(order.id()))
                        .withSelfRel());
    }
}
~~~

Client sẽ không gọi trực tiếp mapping này bằng một URI tự ghép. Nó sẽ lấy href của self link từ representation được server trả về.

## Bước 3: Tạo API root

API root là điểm bắt đầu mà client được cấu hình sẵn. Nó không cần liệt kê toàn bộ endpoint; chỉ cần công bố các quan hệ cấp cao mà client có thể khám phá.

Tạo representation model cho root:

~~~java
package com.example.orders;

import org.springframework.hateoas.RepresentationModel;

public class ApiRoot extends RepresentationModel<ApiRoot> {
}
~~~

Tạo controller:

~~~java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
public class ApiRootController {

    @GetMapping("/")
    public ApiRoot root() {
        ApiRoot model = new ApiRoot();
        model.add(linkTo(methodOn(OrderController.class)
                .findAll())
                .withRel("orders"));
        return model;
    }
}
~~~

Relation orders trỏ tới collection resource. Nếu sau này collection chuyển từ /api/orders sang /store/orders, chỉ cần mapping controller và link builder được cập nhật; client vẫn bắt đầu bằng relation orders.

## Bước 4: Tạo controller cho collection và item

Controller cung cấp hai endpoint:

~~~java
package com.example.orders;

import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orders;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService orders,
            OrderModelAssembler assembler) {
        this.orders = orders;
        this.assembler = assembler;
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderResponse>> findAll() {
        List<Order> result = orders.findAll();
        CollectionModel<EntityModel<OrderResponse>> collection =
                assembler.toCollectionModel(result);

        collection.add(linkTo(methodOn(OrderController.class)
                .findAll())
                .withSelfRel());

        return collection;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderResponse> findById(@PathVariable Long id) {
        Order order = orders.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Order not found"));

        return assembler.toModel(order);
    }
}
~~~

Collection có relation self của chính nó. Mỗi item được tạo qua assembler có self link riêng. Annotation Relation trên OrderResponse khiến embedded collection được công bố dưới key orders.

Tạo class khởi động:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApiApplication.class, args);
    }
}
~~~

## Bước 5: Quan sát các representation HAL

Khởi động server và gọi API root:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/
~~~

Response có dạng:

~~~http
HTTP/1.1 200
Content-Type: application/hal+json

{
  "_links": {
    "orders": {
      "href": "http://localhost:8080/api/orders"
    }
  }
}
~~~

Client chỉ biết URI root. Nó khám phá collection qua relation orders.

Gọi collection để quan sát embedded items:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/orders
~~~

Response rút gọn:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 101,
        "customerName": "Nguyen An",
        "total": 125000.00,
        "status": "PAID",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/101"
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

Trong response thực tế, collection chứa cả ba đơn hàng mẫu. Mỗi item có self link riêng. Client sẽ tìm self link này trong embedded relation orders rồi theo href được cung cấp.

## Bước 6: Viết client dùng Traverson

Traverson nhận URI entry point và media type mà client muốn sử dụng. Nó gửi request với Accept tương ứng, tìm relation trong representation hiện tại và theo href tới representation tiếp theo.

Tạo OrderTraversalClient:

~~~java
package com.example.orders;

import java.net.URI;
import java.util.Objects;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

public class OrderTraversalClient {

    private static final ParameterizedTypeReference<
            CollectionModel<EntityModel<OrderResponse>>> ORDERS_TYPE =
            new ParameterizedTypeReference<>() {
            };

    private static final ParameterizedTypeReference<
            EntityModel<OrderResponse>> ORDER_TYPE =
            new ParameterizedTypeReference<>() {
            };

    private final Traverson traverson;

    public OrderTraversalClient(URI apiRootUri) {
        this.traverson = new Traverson(apiRootUri, MediaTypes.HAL_JSON);
    }

    public CollectionModel<EntityModel<OrderResponse>> findOrders() {
        return Objects.requireNonNull(
                traverson.follow("orders").toObject(ORDERS_TYPE),
                "The orders relation did not return a collection");
    }

    public EntityModel<OrderResponse> findFirstOrder() {
        return Objects.requireNonNull(
                traverson
                        .follow("orders")
                        .follow("$._embedded.orders[0]._links.self.href")
                        .toObject(ORDER_TYPE),
                "The first embedded order could not be traversed");
    }
}
~~~

Phương thức findOrders() theo relation orders và deserialize collection thành CollectionModel<EntityModel<OrderResponse>>. ParameterizedTypeReference giữ lại generic type để message converter biết cấu trúc đích.

Phương thức findFirstOrder() thực hiện hai hop:

1. follow("orders") tải collection được API root công bố.
2. follow("$._embedded.orders[0]._links.self.href") đọc self href của item đầu tiên trong collection và tải item đó.

JSONPath ở hop thứ hai bắt đầu bằng ký tự $. Traverson dùng nó để tìm URI trong representation hiện tại. Nó không yêu cầu client biết item endpoint là /api/orders/{id}.

Client vẫn biết một số phần của hợp đồng: relation orders, embedded relation orders và media type HAL JSON. Hypermedia không loại bỏ mọi kiến thức về hợp đồng; nó loại bỏ sự phụ thuộc vào việc tự ghép các URI cụ thể.

## Bước 7: Kiểm thử traversal qua HTTP thật

Dùng Spring Boot test với random port để server khởi động trên cổng do test environment cấp. Traverson gọi server qua HTTP thật thay vì gọi controller trực tiếp:

~~~java
package com.example.orders;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderTraversalClientTest {

    @LocalServerPort
    private int port;

    @Test
    void discoversCollectionAndTraversesToFirstOrder() {
        URI rootUri = URI.create("http://localhost:" + port + "/");
        OrderTraversalClient client = new OrderTraversalClient(rootUri);

        var orders = client.findOrders();
        assertThat(orders.getContent()).hasSize(3);

        EntityModel<OrderResponse> firstOrder = client.findFirstOrder();

        assertThat(firstOrder.getContent()).isNotNull();
        assertThat(firstOrder.getContent().id()).isEqualTo(101L);
        assertThat(firstOrder.getRequiredLink(IanaLinkRelations.SELF)
                .getHref())
                .endsWith("/api/orders/101");
    }
}
~~~

Test chỉ tạo URI của entry point bằng cổng ngẫu nhiên. Client tìm collection và item qua links. Assertion cuối xác nhận item nhận được có self link trỏ tới đúng đơn hàng.

Traverson mặc định dùng RestTemplate cùng các message converter phù hợp với media type được truyền vào constructor. Nếu ứng dụng cần authentication header, timeout hoặc cấu hình HTTP client riêng, có thể truyền RestOperations tùy chỉnh bằng setRestOperations(...) và thêm request headers cho traversal bằng withHeaders(...).

## Bước 8: Chạy và quan sát

Khởi động ứng dụng:

~~~bash
./gradlew bootRun
~~~

Chạy integration test:

~~~bash
./gradlew test --tests "com.example.orders.OrderTraversalClientTest"
~~~

Khi test pass, client đã đi từ root tới collection rồi tới item bằng hai relation/href được server công bố. Không có đoạn code nào trong OrderTraversalClient ghép URI của collection hoặc item.

## Bước 9: Thử thay đổi route

Thay class-level mapping trong OrderController:

~~~java
@RequestMapping("/store/orders")
~~~

Không sửa ApiRootController, OrderTraversalClient hoặc JSONPath traversal. Chạy lại integration test.

Mong đợi:

- API root vẫn công bố relation orders.
- Href của relation orders tự đổi theo mapping mới.
- Self link của từng item cũng đổi theo mapping mới.
- Client vẫn tìm collection và item bằng cùng các relation.

Đây là lợi ích thực tế của client traversal: client dựa vào quan hệ mà server công bố, không phụ thuộc vào đường dẫn được mã hóa trong source code.

## Tiêu chí hoàn thành

- [ ] Ứng dụng khởi động với Spring MVC và Spring HATEOAS.
- [ ] GET / trả API root với relation orders.
- [ ] GET collection trả HAL JSON có embedded relation orders.
- [ ] Mỗi item trong collection có self link.
- [ ] OrderTraversalClient dùng Traverson với MediaTypes.HAL_JSON.
- [ ] Client tải collection bằng follow("orders").
- [ ] Client tải item bằng JSONPath tới embedded self href.
- [ ] Generic response được deserialize bằng ParameterizedTypeReference.
- [ ] Integration test chạy qua random HTTP port và pass.
- [ ] Đổi mapping collection không cần sửa client traversal.

## Thử thách mở rộng

Sau khi hoàn thành luồng cơ bản, hãy mở rộng:

1. Thêm relation customer vào mỗi order và dùng Traverson theo relation này để tải customer.
2. Thêm search relation có URI template, sau đó dùng Hop và withTemplateParameters(...) để truyền filter.
3. Thêm pagination và cho client theo next relation cho tới khi hết trang.
4. Truyền Authorization header bằng withHeaders(...) và xác minh traversal hoạt động với endpoint được bảo vệ.
5. Thay HAL bằng một media type hypermedia khác được server hỗ trợ, rồi cấu hình Traverson với media type tương ứng.
6. Thêm test khi collection rỗng để client xử lý trường hợp không có embedded item mà không giả định index 0 luôn tồn tại.

## Lỗi thường gặp

- **Traverson không tìm thấy relation:** kiểm tra API root có công bố đúng relation và client đang yêu cầu media type phù hợp.
- **Không thấy embedded key orders:** kiểm tra Relation annotation và tên collection relation trong JSON HAL.
- **JSONPath không tìm thấy self href:** kiểm tra response collection có item và mỗi item có self link.
- **Không deserialize được generic model:** dùng ParameterizedTypeReference thay cho Class thô.
- **Client vẫn ghép URI item:** dùng JSONPath hop để lấy self href từ embedded resource.
- **Test không kết nối được server:** dùng RANDOM_PORT và LocalServerPort; không dùng MockMvc cho Traverson vì Traverson thực hiện HTTP request thật.
- **Client nhận media type không mong muốn:** tạo Traverson với MediaTypes.HAL_JSON và kiểm tra server trả Content-Type tương thích.
- **Collection rỗng gây lỗi index:** kiểm tra collection có phần tử trước khi thực hiện hop JSONPath tới item đầu tiên.
- **Route thay đổi làm client hỏng:** tìm chỗ client đang tự ghép URL; chỉ giữ URI entry point làm cấu hình ban đầu.

## Kết quả cần nộp

Hoàn thành API root, collection và item endpoints; assembler tạo self links; client Traverson; và integration test dùng random port. Ghi lại response HAL của root và collection, kết quả test traversal tới item, cùng một lần đổi mapping mà không sửa client.

Trong phần mô tả ngắn, giải thích mỗi hop đã dùng relation hoặc JSONPath nào, client biết URI nào từ cấu hình ban đầu, và vì sao việc theo href giúp client ít phụ thuộc vào cấu trúc route của server.

Client traversal là cách hiện thực hóa HATEOAS ở phía tiêu thụ API. Khi bắt đầu từ entry point và theo relation đến từng tài nguyên, client để server dẫn đường bằng hypermedia links. Traverson hỗ trợ tự động hóa chuỗi request đó, còn integration test chứng minh luồng điều hướng hoạt động qua HTTP thật.

## Tài liệu tham khảo

- Spring HATEOAS Reference Documentation, Traverson: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client.traverson
- Spring HATEOAS API, Traverson: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.html
- Spring HATEOAS API, Traverson.TraversalBuilder: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.TraversalBuilder.html
- Spring HATEOAS API, Relation: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html
- Spring Boot Reference Documentation, Spring HATEOAS: https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html
