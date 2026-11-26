# Tạo resource DTO

Trong dự án REST API có Spring HATEOAS, dữ liệu nghiệp vụ và representation gửi cho client cần được tổ chức rõ ràng. Một JPA entity thường chứa trạng thái persistence, quan hệ nội bộ và dữ liệu phục vụ xử lý nghiệp vụ. Nếu trả trực tiếp entity, API vô tình để lộ cấu trúc lưu trữ và khiến contract HTTP phụ thuộc vào mô hình bên trong ứng dụng.

Trong bài thực hành này, bạn sẽ tạo một DTO đại diện cho resource đơn hàng, chuyển dữ liệu từ domain object sang DTO, rồi bọc DTO bằng **EntityModel** để bổ sung link hypermedia. Bạn sẽ tiếp tục tạo collection representation bằng **CollectionModel**, công bố endpoint qua controller và kiểm tra JSON HAL mà client thực sự nhận được.

Kết quả là một resource có dữ liệu công khai được kiểm soát, relation **self** để truy cập chính nó và relation **collection** để quay lại danh sách đơn hàng. Phần tử trong collection được đặt dưới relation **orders**, giúp client nhận biết ngữ nghĩa của embedded resource.

## Mục tiêu thực hành

Sau khi hoàn thành, bạn có thể:

- Phân biệt domain entity, request DTO và resource DTO.
- Tạo resource DTO chỉ chứa dữ liệu cần công bố qua API.
- Chuyển domain object sang DTO mà không trả entity trực tiếp.
- Dùng EntityModel để kết hợp DTO với link.
- Dùng CollectionModel để biểu diễn danh sách resource.
- Dùng RepresentationModelAssembler để gom logic chuyển đổi và tạo link.
- Khai báo item relation và collection relation bằng @Relation.
- Tích hợp assembler vào Spring MVC controller.
- Kiểm tra response HAL bằng MockMvc.
- Đánh giá DTO và link theo tiêu chí của một public API contract.

## Bài toán

Bạn xây dựng một API quản lý đơn hàng. Domain model có thể chứa nhiều thuộc tính phục vụ nghiệp vụ và persistence, nhưng client chỉ cần một phần dữ liệu:

| Thuộc tính domain | Có công bố? | Lý do |
|---|---|---|
| ID đơn hàng | Có | Định danh đơn hàng |
| Mã đơn hàng | Có | Hiển thị và tra cứu |
| Trạng thái | Có | Cho biết tiến trình xử lý |
| Tổng tiền | Có | Thông tin nghiệp vụ cần thiết |
| Thời điểm tạo | Có | Hiển thị lịch sử |
| Ghi chú nội bộ | Không | Chỉ phục vụ vận hành |
| Cờ persistence hoặc version nội bộ | Không | Chi tiết lưu trữ |
| Thông tin credential hoặc dữ liệu bí mật | Không | Không thuộc public contract |

API cần cung cấp:

~~~text
GET /api/orders
GET /api/orders/{id}
~~~

Endpoint chi tiết trả về một order resource. Endpoint danh sách trả về collection có các order resource được nhúng. Cả hai đều dùng HAL để client có thể điều hướng bằng link.

## Chuẩn bị dự án

Tạo ứng dụng Spring Boot có Spring MVC và Spring HATEOAS. Với stack Spring Framework 7 và Spring HATEOAS 3.x, dùng Spring Boot 4 dependency management; các dependency chính thường là:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
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

Để Spring Boot dependency management hoặc parent POM quản lý version của các dependency, không tự nâng riêng Spring HATEOAS vượt khỏi dòng tương thích. Nếu dự án dùng Spring Boot 3 và Spring HATEOAS 2.x, Web MVC starter tương ứng là spring-boot-starter-web. Hãy giữ Spring Boot, Spring Framework và Spring HATEOAS trong cùng một bộ version tương thích.

Ví dụ dùng Java 17 trở lên để khai báo DTO bằng record. Nếu dự án dùng Java thấp hơn hoặc cần class DTO mutable, có thể thay record bằng class có constructor và getter.

Một cấu trúc package gợi ý:

~~~text
com.example.orders
├── domain
│   └── Order.java
├── application
│   └── OrderService.java
└── web
    ├── OrderController.java
    ├── OrderResourceDto.java
    └── OrderModelAssembler.java
~~~

DTO thuộc lớp web/API vì nó mô tả dữ liệu công bố cho client. Domain model và application service vẫn chịu trách nhiệm nghiệp vụ.

## Bước 1: Tạo domain model tối giản

Trong dự án thật, Order có thể là JPA entity hoặc aggregate root. Để tập trung vào resource DTO, ví dụ dưới đây dùng một record domain đơn giản:

~~~java
package com.example.orders.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record Order(
    UUID id,
    String orderNumber,
    String status,
    BigDecimal total,
    Instant createdAt,
    String internalNote
) {
}
~~~

internalNote là dữ liệu nội bộ, không cần xuất hiện trong API. Khi dùng JPA entity, các thuộc tính persistence như lazy relationship, audit field nội bộ hoặc optimistic lock version cũng không nên tự động trở thành JSON chỉ vì entity có getter.

Khai báo application service trả về domain object:

~~~java
package com.example.orders.application;

import java.util.List;
import java.util.UUID;

import com.example.orders.domain.Order;

public interface OrderService {

    Order findById(UUID id);

    List<Order> findAll();
}
~~~

Phần cài đặt service và repository có thể dùng database, in-memory store hoặc fixture. Trong bài này, giả sử service đã có thể tìm một đơn hàng và trả danh sách đơn hàng.

## Bước 2: Tạo resource DTO

Tạo OrderResourceDto trong package web:

~~~java
package com.example.orders.web;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

import com.example.orders.domain.Order;

@Relation(
    itemRelation = "order",
    collectionRelation = "orders"
)
public record OrderResourceDto(
    UUID id,
    String orderNumber,
    String status,
    BigDecimal total,
    Instant createdAt
) {

    public static OrderResourceDto from(Order order) {
        return new OrderResourceDto(
            order.id(),
            order.orderNumber(),
            order.status(),
            order.total(),
            order.createdAt()
        );
    }
}
~~~

Đây là DTO dành cho response. Phương thức from() chuyển dữ liệu từ domain model sang cấu trúc công khai. internalNote không được copy nên không thể vô tình bị serialize ra ngoài qua DTO này.

### Vì sao DTO không chứa link dưới dạng field?

Không thêm các field như selfUrl, customerUrl hoặc cancelUrl. Những field này trộn dữ liệu nghiệp vụ với metadata điều hướng. Spring HATEOAS đã có EntityModel và RepresentationModel để biểu diễn link riêng. Giữ DTO tập trung vào dữ liệu giúp:

- Tách contract dữ liệu khỏi cách điều hướng.
- Thay đổi URI mà không phải thay cấu trúc DTO.
- Tái sử dụng DTO ở nhiều representation hoặc media type.
- Dễ kiểm tra dữ liệu công khai và mapping.

### Vai trò của @Relation

@Relation định nghĩa tên relation cho item và collection khi Spring HATEOAS cần serialize resource. Trong ví dụ:

- itemRelation = "order" mô tả một order item.
- collectionRelation = "orders" mô tả collection các order.

Khi serialize CollectionModel<EntityModel<OrderResourceDto>> thành HAL, relation collection có thể được dùng làm key trong _embedded:

~~~json
{
  "_embedded": {
    "orders": []
  }
}
~~~

Tên relation là một phần contract mà client sử dụng. Nếu muốn đổi từ orders sang tên khác, cần xem đó là thay đổi contract và đánh giá tác động tới client.

## Bước 3: Tạo assembler cho resource

Assembler chịu trách nhiệm chuyển domain object thành resource representation. Tạo OrderModelAssembler:

~~~java
package com.example.orders.web;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import com.example.orders.domain.Order;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<
            Order,
            EntityModel<OrderResourceDto>
        > {

    @Override
    public EntityModel<OrderResourceDto> toModel(Order order) {
        OrderResourceDto dto = OrderResourceDto.from(order);

        return EntityModel.of(
            dto,
            linkTo(methodOn(OrderController.class).one(order.id()))
                .withSelfRel(),
            linkTo(methodOn(OrderController.class).all())
                .withRel(IanaLinkRelations.COLLECTION)
        );
    }
}
~~~

RepresentationModelAssembler nhận domain object Order và trả về EntityModel<OrderResourceDto>. Việc chuyển đổi và tạo link nằm cùng một nơi, giúp controller không phải tự map từng field hoặc lặp lại cách xây URI.

Hai link được công bố:

| Relation | Target | Ý nghĩa |
|---|---|---|
| self | Endpoint chi tiết của order hiện tại | Client truy cập lại resource |
| collection | Endpoint danh sách orders | Client quay về collection |

linkTo(methodOn(...)) tạo link dựa trên mapping controller. Nếu route được đổi nhưng method mapping và semantics vẫn giữ, assembler tự tạo href theo mapping mới.

Không tự nối chuỗi "/api/orders/" + order.id() trong assembler. Cách làm đó lại đưa route vào logic ứng dụng và làm mất lợi ích của link builder.

### toCollectionModel()

RepresentationModelAssembler còn cung cấp toCollectionModel(). Phương thức này gọi toModel() cho từng domain object và trả về CollectionModel:

~~~java
CollectionModel<EntityModel<OrderResourceDto>> collection =
    assembler.toCollectionModel(orders);
~~~

Nhờ vậy, mỗi order trong collection có DTO và link riêng. Controller chỉ cần thêm link self cho collection.

## Bước 4: Tạo controller

Tạo OrderController:

~~~java
package com.example.orders.web;

import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.mvc.WebMvcLinkBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.orders.application.OrderService;
import com.example.orders.domain.Order;

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

    @GetMapping("/{id}")
    public EntityModel<OrderResourceDto> one(
            @PathVariable("id") UUID id) {
        Order order = orders.findById(id);
        return assembler.toModel(order);
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderResourceDto>> all() {
        return assembler.toCollectionModel(orders.findAll())
            .add(
                WebMvcLinkBuilder.linkTo(
                    WebMvcLinkBuilder.methodOn(OrderController.class)
                        .all())
                    .withSelfRel()
            );
    }
}
~~~

Controller trả về model của Spring HATEOAS thay vì trả trực tiếp DTO hoặc entity:

- EntityModel<OrderResourceDto> cho một resource.
- CollectionModel<EntityModel<OrderResourceDto>> cho collection resource.

Spring MVC sử dụng message converter hypermedia để serialize các model theo media type mà client yêu cầu. Khi dùng Spring Boot với HATEOAS starter, auto-configuration thường cung cấp HAL support. Nếu cấu hình ứng dụng tùy chỉnh message converter hoặc không dùng Boot auto-configuration, hãy đăng ký hypermedia support phù hợp.

## Bước 5: Xem representation HAL

Gọi endpoint chi tiết:

~~~http
GET /api/orders/6d2d1d4d-ec8d-4ed7-b8f8-8f42f43d9b16
Accept: application/hal+json
~~~

Response có cấu trúc tương tự:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "id": "6d2d1d4d-ec8d-4ed7-b8f8-8f42f43d9b16",
  "orderNumber": "ORD-2026-0042",
  "status": "SUBMITTED",
  "total": 1250000.00,
  "createdAt": "2026-11-20T08:30:00Z",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/6d2d1d4d-ec8d-4ed7-b8f8-8f42f43d9b16"
    },
    "collection": {
      "href": "http://localhost:8080/api/orders"
    }
  }
}
~~~

Response collection có thể có dạng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": "6d2d1d4d-ec8d-4ed7-b8f8-8f42f43d9b16",
        "orderNumber": "ORD-2026-0042",
        "status": "SUBMITTED",
        "total": 1250000.00,
        "createdAt": "2026-11-20T08:30:00Z",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/orders/6d2d1d4d-ec8d-4ed7-b8f8-8f42f43d9b16"
          },
          "collection": {
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

Host trong ví dụ là host local minh họa. Khi chạy sau reverse proxy, scheme, host và prefix có thể khác theo cấu hình forwarded headers. Client nên đọc href từ response thay vì ghép URI từ ví dụ.

Hãy kiểm tra các điểm sau:

- Field internalNote không xuất hiện.
- Resource đơn có self và collection.
- Collection có _embedded.orders.
- Mỗi embedded order có link self.
- Collection có link self.
- Content-Type là application/hal+json.

## Bước 6: Kiểm thử resource DTO và HAL representation

Kiểm thử mapping DTO riêng giúp xác nhận dữ liệu công khai được chọn đúng. Ví dụ:

~~~java
package com.example.orders.web;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;

import com.example.orders.domain.Order;

class OrderResourceDtoTest {

    @Test
    void mapsOnlyPublicOrderFields() {
        Order order = new Order(
            UUID.fromString("6d2d1d4d-ec8d-4ed7-b8f8-8f42f43d9b16"),
            "ORD-2026-0042",
            "SUBMITTED",
            new BigDecimal("1250000.00"),
            Instant.parse("2026-11-20T08:30:00Z"),
            "Internal note"
        );

        OrderResourceDto dto = OrderResourceDto.from(order);

        assertThat(dto.orderNumber()).isEqualTo("ORD-2026-0042");
        assertThat(dto.status()).isEqualTo("SUBMITTED");
        assertThat(dto.total()).isEqualByComparingTo("1250000.00");
    }
}
~~~

Unit test này xác nhận mapping từ domain sang DTO. Nó chưa kiểm tra serializer, media type hoặc link, vì vậy cần thêm MVC test.

### MVC test cho endpoint chi tiết

Ví dụ dùng @WebMvcTest và @MockitoBean để mock service trong khi vẫn chạy controller và MVC message converter:

~~~java
package com.example.orders.web;

import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import com.example.orders.application.OrderService;
import com.example.orders.domain.Order;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerRepresentationTest {

    private static final UUID ORDER_ID =
        UUID.fromString("6d2d1d4d-ec8d-4ed7-b8f8-8f42f43d9b16");

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orders;

    @Test
    void returnsHalOrderResourceWithLinks() throws Exception {
        Order order = new Order(
            ORDER_ID,
            "ORD-2026-0042",
            "SUBMITTED",
            new BigDecimal("1250000.00"),
            Instant.parse("2026-11-20T08:30:00Z"),
            "Internal note"
        );

        given(orders.findById(ORDER_ID)).willReturn(order);

        mockMvc.perform(get("/api/orders/{id}", ORDER_ID)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.orderNumber")
                .value("ORD-2026-0042"))
            .andExpect(jsonPath("$.status").value("SUBMITTED"))
            .andExpect(jsonPath("$.internalNote").doesNotExist())
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/api/orders/" + ORDER_ID)))
            .andExpect(jsonPath("$._links.collection.href")
                .exists());
    }
}
~~~

@MockitoBean có trong Spring Test hiện đại. Nếu dự án đang dùng dòng Spring Framework cũ hơn, dùng cơ chế mock bean tương ứng của phiên bản Spring Boot đó. @WebMvcTest cần nạp cấu hình HATEOAS phù hợp; nếu test slice của dự án không tự cấu hình HAL converter, hãy import cấu hình hypermedia mà ứng dụng đang dùng.

### MVC test cho collection

Thêm test xác nhận embedded relation:

~~~java
@Test
void returnsOrdersInsideEmbeddedCollection() throws Exception {
    Order order = new Order(
        ORDER_ID,
        "ORD-2026-0042",
        "SUBMITTED",
        new BigDecimal("1250000.00"),
        Instant.parse("2026-11-20T08:30:00Z"),
        "Internal note"
    );

    given(orders.findAll()).willReturn(List.of(order));

    mockMvc.perform(get("/api/orders")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._embedded.orders[0].orderNumber")
            .value("ORD-2026-0042"))
        .andExpect(jsonPath("$._embedded.orders[0]._links.self.href")
            .exists());
}
~~~

Đây là method bổ sung cho test class OrderControllerRepresentationTest ở trên. Các import, mockMvc, orders và ORDER_ID đã được khai báo trong class đó; List cũng cần được import ở đầu test class. Nếu tách method thành test class khác, khai báo lại các fixture và mock bean cần thiết.

## Bước 7: Kiểm tra contract của DTO

Trước khi hoàn tất, xem DTO như một phần public contract. Hãy trả lời:

1. Mỗi field có thực sự cần thiết cho client không?
2. Có field nội bộ hoặc dữ liệu nhạy cảm nào bị đưa vào DTO không?
3. Tên field có ổn định và có ý nghĩa với client không?
4. Kiểu dữ liệu có thể được serialize nhất quán không?
5. Thời gian có timezone rõ ràng không?
6. Tiền tệ có được mô tả cùng giá trị hay API cần thêm currency code?
7. Link được tạo bằng mapping thay vì ghép chuỗi không?
8. Collection relation có tên rõ ràng không?
9. Client có thể điều hướng mà không cần đoán URI không?

Nếu API hỗ trợ nhiều loại tiền tệ, DTO nên có thêm trường currency thay vì để client đoán từ locale hoặc cấu hình. Nếu trạng thái là enum, cân nhắc serialize bằng mã ổn định dành cho API thay vì phụ thuộc tên enum nội bộ có thể đổi.

### Resource DTO và request DTO

Không dùng cùng một DTO cho mọi chiều dữ liệu. Ví dụ:

~~~java
import java.util.List;
import java.util.UUID;

public record CreateOrderRequest(
    String customerReference,
    List<CreateOrderLineRequest> lines
) {
}

public record CreateOrderLineRequest(
    UUID productId,
    int quantity
) {
}
~~~

CreateOrderRequest mô tả dữ liệu client gửi để tạo đơn hàng. OrderResourceDto mô tả dữ liệu server công bố sau khi đơn hàng được tạo. Hai contract có thể khác nhau:

- Request không cần có id, createdAt hoặc status do server quản lý.
- Response có thể công bố id, status, total và link điều hướng.
- Request không nên cho client tự gửi field nội bộ hoặc trạng thái tùy ý.
- Response không nên để client ghi đè dữ liệu chỉ đọc.

Tách request DTO và resource DTO giúp kiểm soát validation, mass assignment và tiến hóa API độc lập.

## Bước 8: Mở rộng resource theo trạng thái

Sau khi hoàn thành resource cơ bản, bạn có thể mở rộng assembler để công bố link chỉ khi action khả dụng. Ví dụ, chỉ thêm relation cancel khi đơn hàng đang ở trạng thái cho phép hủy:

~~~java
@Override
public EntityModel<OrderResourceDto> toModel(Order order) {
    EntityModel<OrderResourceDto> model = EntityModel.of(
        OrderResourceDto.from(order),
        linkTo(methodOn(OrderController.class).one(order.id()))
            .withSelfRel(),
        linkTo(methodOn(OrderController.class).all())
            .withRel(IanaLinkRelations.COLLECTION)
    );

    if ("SUBMITTED".equals(order.status())) {
        model.add(
            linkTo(methodOn(OrderController.class).cancel(order.id()))
                .withRel("cancel")
        );
    }

    return model;
}
~~~

Đây là phần mở rộng tùy chọn. Để dùng được, controller cần có method cancel(UUID id) với mapping phù hợp và service phải thực thi quy tắc nghiệp vụ. Không thêm link action chỉ vì UI muốn hiển thị nút; server phải quyết định khả năng dựa trên trạng thái và policy.

Link không thay thế authorization. Endpoint cancel vẫn phải xác thực quyền và kiểm tra trạng thái tại thời điểm nhận request, vì resource có thể thay đổi sau khi representation được tạo.

## Kết quả cần đạt

Khi hoàn thành phần bắt buộc, dự án có:

- Một domain model Order.
- Một OrderResourceDto chỉ chứa field công khai.
- Một assembler chuyển Order thành EntityModel<OrderResourceDto>.
- Một controller trả resource chi tiết và collection.
- HAL response có relation self, collection và embedded relation orders.
- Unit test cho DTO mapping.
- MVC test xác nhận media type, field và link.

Có thể tự đánh giá theo bảng:

| Tiêu chí | Đạt khi |
|---|---|
| Tách domain và DTO | Controller không trả trực tiếp entity |
| Chọn field | Không lộ internalNote hoặc persistence detail |
| Relation item | Một order có semantics item order |
| Relation collection | Danh sách được nhúng dưới orders |
| Link self | Mỗi order trỏ tới URI của chính nó |
| Link collection | Client có đường điều hướng về collection |
| Controller | Trả EntityModel/CollectionModel |
| Serialization | HAL media type và cấu trúc JSON đúng |
| Test | Kiểm tra cả DTO mapping và HTTP representation |

## Bài tập mở rộng

1. Thêm relation customer tới customer resource và kiểm tra href được tạo từ controller mapping.
2. Thêm currency vào DTO và cập nhật test.
3. Thay status string bằng enum API riêng, không phụ thuộc enum persistence.
4. Tạo endpoint POST nhận CreateOrderRequest và trả 201 Created cùng resource DTO và Location header lấy từ self link.
5. Thêm relation cancel có điều kiện theo trạng thái, sau đó kiểm thử cả trường hợp link xuất hiện và vắng mặt.
6. Thử đổi mapping từ /api/orders sang /commerce/orders; xác nhận assembler tạo link theo mapping mới và test không khóa cứng route cũ.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Trả trực tiếp JPA entity | Lộ persistence detail và quan hệ nội bộ | Map sang resource DTO |
| Dùng DTO làm nơi chứa selfUrl và cancelUrl | Trộn dữ liệu với metadata hypermedia | Bọc DTO bằng EntityModel |
| Dùng request DTO làm response DTO | Client có thể ghi vào field server quản lý hoặc thiếu field response | Tách request DTO và resource DTO |
| Map tất cả field entity sang DTO | Có thể lộ ghi chú nội bộ hoặc dữ liệu nhạy cảm | Chọn field công khai tường minh |
| Tạo link bằng nối chuỗi | Coupling với route và dễ tạo URI sai | Dùng linkTo(methodOn(...)) |
| Lặp mapping và link trong controller | Khó tái sử dụng và dễ không nhất quán | Đưa vào RepresentationModelAssembler |
| Quên @Relation cho collection | Embedded relation có thể mang tên suy ra ngoài ý muốn | Khai báo item và collection relation rõ ràng |
| Chỉ test DTO | Không phát hiện lỗi HAL serializer hoặc content negotiation | Bổ sung MockMvc test |
| Chỉ test status 200 | Link và payload có thể sai nhưng test vẫn xanh | Assert media type, field và relation |
| Xem link là quyền truy cập | Request trực tiếp vẫn có thể vượt policy nếu endpoint không bảo vệ | Enforce authorization tại endpoint |

## Ghi nhớ

Resource DTO là dữ liệu công khai mà API muốn biểu diễn; EntityModel kết hợp dữ liệu đó với link hypermedia. Hãy map domain object sang DTO bằng assembler, chọn field công khai tường minh và giữ metadata điều hướng ở EntityModel thay vì nhúng URL vào DTO. Dùng @Relation để đặt tên item và collection ổn định, dùng link builder để tạo href từ controller mapping, rồi kiểm tra response HAL bằng MockMvc. Khi đó, resource vừa có cấu trúc dữ liệu rõ ràng vừa cho phép client điều hướng theo relation mà không phải đoán route.

## Tài liệu tham khảo

- [Spring HATEOAS – Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
- [Spring HATEOAS – RepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [Spring HATEOAS – EntityModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [Spring HATEOAS – Relation annotation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html)
- [Spring HATEOAS – WebMvcLinkBuilder API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html)
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
