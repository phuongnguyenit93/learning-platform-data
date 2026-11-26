# Tích hợp Jackson

Spring HATEOAS dùng Jackson để chuyển representation thành JSON. Khi response có hypermedia, việc serialize còn phải giữ đúng cấu trúc của định dạng được chọn: HAL đặt link trong `_links`, tài nguyên nhúng trong `_embedded`, và mỗi link được trình bày theo relation của nó. Vì vậy, tích hợp Jackson trong ứng dụng HATEOAS không chỉ là chuyển một DTO thành JSON; ứng dụng cần dùng cấu hình hypermedia và message converter tương ứng để client nhận được representation đúng hợp đồng.

Trong phạm vi Spring HATEOAS, Jackson đảm nhiệm hai phần liên quan nhưng khác nhau:

- Serialize dữ liệu nghiệp vụ như mã đơn hàng, trạng thái, số tiền và thời gian.
- Serialize cấu trúc hypermedia như `Link`, relation, URI template và các tài nguyên được nhúng.

Các annotation Jackson điều khiển phần dữ liệu của representation. Spring HATEOAS bổ sung module và cơ chế chuyển đổi để xử lý phần hypermedia. Giữ rõ hai trách nhiệm này giúp tránh tự tạo JSON link bằng tay hoặc vô tình làm mất metadata khi tùy biến `ObjectMapper`.

## Jackson và cấu trúc HAL

Một representation HAL thường có dữ liệu tài nguyên ở cấp ngoài cùng, link trong `_links`, và các tài nguyên liên quan được nhúng trong `_embedded`:

```json
{
  "id": "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042",
  "status": "PENDING",
  "total_amount": 125000,
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042"
    },
    "orders": {
      "href": "https://shop.example/api/orders"
    }
  }
}
```

Jackson thông thường biết cách serialize các thuộc tính `id`, `status` và `total_amount`. Spring HATEOAS cung cấp hỗ trợ Jackson dành cho hypermedia để biểu diễn `Link` thành cấu trúc HAL, đặt các quan hệ dưới `_links` và xử lý `_embedded`. Relation là tên khóa bên trong `_links`; nó không phải một thuộc tính tùy ý của DTO.

Với HAL, Spring HATEOAS cung cấp `Jackson2HalModule`; với HAL-FORMS, thư viện có module Jackson tương ứng `Jackson2HalFormsModule`. Các module này bổ sung cách xử lý cấu trúc hypermedia cho Jackson. Cấu hình hypermedia của Spring kết nối module với message converter và media type tương ứng, để controller không phải tự gọi serializer cho từng link.

Ví dụ, relation `self` có thể trỏ đến chính tài nguyên, `orders` đến collection đơn hàng và `customer` đến tài nguyên khách hàng liên quan. Khi có nhiều link cùng relation, serializer HAL biểu diễn chúng theo quy tắc của HAL. Client cần tìm link theo relation và đọc `href`, không phụ thuộc thứ tự các thuộc tính JSON.

## Cấu hình hỗ trợ hypermedia

Với ứng dụng Spring Boot, thêm starter HATEOAS để nhận các tích hợp cần thiết:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-hateoas")
}
```

Starter đưa Spring HATEOAS và tích hợp hypermedia vào ứng dụng Boot. Cấu hình tự động của Boot phối hợp Jackson với message converter phù hợp để trả về các representation HATEOAS. Trong ứng dụng thông thường, controller chỉ cần trả về `RepresentationModel`, `EntityModel` hoặc `CollectionModel`; không cần tự tạo `ObjectMapper` mới rồi tự serialize link.

Nếu ứng dụng dùng Spring Framework mà không dựa vào auto-configuration của Boot, có thể bật hỗ trợ HAL trong cấu hình MVC:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
```

`@EnableHypermediaSupport` đăng ký hạ tầng cần thiết cho định dạng hypermedia được chọn, bao gồm tích hợp với cơ chế chuyển đổi HTTP. Hãy chọn cách cấu hình phù hợp với kiểu ứng dụng. Trong ứng dụng Boot đã dùng starter HATEOAS, không cần thêm cấu hình thủ công trùng lặp chỉ để bật HAL.

Client có thể yêu cầu HAL bằng header:

```http
GET /api/orders/7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042 HTTP/1.1
Accept: application/hal+json
```

Server trả về representation với media type `application/hal+json`. Nếu endpoint công bố nhiều định dạng, Spring MVC và các message converter dùng content negotiation để chọn định dạng phù hợp với header `Accept`. Nếu endpoint chỉ hỗ trợ HAL, có thể khai báo `produces = MediaTypes.HAL_JSON_VALUE` trên mapping để hợp đồng media type được thể hiện rõ.

## Dùng model HATEOAS trong controller

Spring HATEOAS cung cấp các kiểu model để gắn link vào nội dung trước khi Jackson serialize:

| Kiểu | Cách dùng |
| --- | --- |
| `RepresentationModel<T>` | Lớp cơ sở cho model tự định nghĩa có thể chứa link. |
| `EntityModel<T>` | Bọc một DTO hoặc đối tượng nội dung cùng các link. |
| `CollectionModel<T>` | Bọc tập hợp model và các link của collection. |
| `PagedModel<T>` | Biểu diễn collection có thông tin phân trang. |

Ví dụ sau dùng model riêng cho đơn hàng. `@Relation` xác định tên relation khi model được nhúng vào collection; các link được thêm bằng API Spring HATEOAS.

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public class OrderRepresentation extends RepresentationModel<OrderRepresentation> {

    private final UUID id;
    private final String status;
    private final BigDecimal totalAmount;

    public OrderRepresentation(UUID id, String status, BigDecimal totalAmount) {
        this.id = id;
        this.status = status;
        this.totalAmount = totalAmount;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

Assembler chuyển đối tượng nghiệp vụ thành model có dữ liệu và link:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, OrderRepresentation> {

    @Override
    public OrderRepresentation toModel(Order order) {
        OrderRepresentation model = new OrderRepresentation(
                order.getId(), order.getStatus().name(), order.getTotalAmount());

        model.add(linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel());
        model.add(linkTo(methodOn(OrderController.class)
                .all()).withRel("orders"));

        return model;
    }
}
```

Controller trả về model thay vì tự dựng JSON:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    OrderRepresentation one(@PathVariable UUID id) {
        return assembler.toModel(service.findById(id));
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    CollectionModel<OrderRepresentation> all() {
        List<OrderRepresentation> orders = service.findAll().stream()
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(orders,
                linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }
}
```

Các lớp `Order`, `OrderService` và tầng lưu trữ là thành phần nghiệp vụ của ứng dụng. Khi controller trả về `OrderRepresentation` hoặc `CollectionModel<OrderRepresentation>`, message converter HAL dùng Jackson đã được tích hợp để tạo JSON hypermedia. Relation `orders` của collection được lấy từ `@Relation`; relation `self` của từng phần tử được tạo trong assembler.

## Tùy biến tên thuộc tính bằng Jackson

Các annotation Jackson vẫn có tác dụng với phần dữ liệu của model. Ví dụ, API có thể dùng tên trường `total_amount` trong JSON dù Java dùng tên `totalAmount`:

```java
import java.math.BigDecimal;
import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record OrderPayload(
        UUID id,
        String status,
        @JsonProperty("total_amount") BigDecimal totalAmount,
        String note
) {
}
```

`@JsonProperty` định nghĩa tên thuộc tính JSON; `@JsonInclude` điều khiển việc đưa giá trị null vào JSON. Có thể dùng thêm `@JsonIgnore` để loại một thuộc tính nội bộ khỏi representation, hoặc `@JsonFormat` để quy định định dạng ngày giờ khi hợp đồng yêu cầu. Những annotation này điều khiển dữ liệu của tài nguyên, không đổi relation của link.

Đối với relation của tài nguyên nhúng, dùng `@Relation` trên kiểu model. Ví dụ `itemRelation = "order"` và `collectionRelation = "orders"` giúp HAL có tên relation dễ hiểu cho từng phần tử và collection. Nhờ đó, tên trường JSON và tên relation hypermedia được cấu hình ở đúng lớp trách nhiệm.

Một response collection có thể có cấu trúc khái quát như sau:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042",
        "status": "PENDING",
        "total_amount": 125000,
        "_links": {
          "self": {
            "href": "https://shop.example/api/orders/7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders"
    }
  }
}
```

Tên `orders` dưới `_embedded` đến từ relation collection. Nếu relation này bị đổi, client đang tìm `_embedded.orders` có thể bị ảnh hưởng; vì vậy hãy xem tên relation là một phần hợp đồng và kiểm thử nó như các link khác.

## Tùy biến ObjectMapper mà không làm mất HAL

`ObjectMapper` quản lý cách Jackson đọc và ghi JSON. Ứng dụng thường cần tùy biến cách xử lý ngày giờ, số, enum hoặc serializer riêng cho kiểu dữ liệu nghiệp vụ. Tuy nhiên, một mapper được tạo thủ công bằng `new ObjectMapper()` không tự có mọi module và cấu hình mà Spring Boot hoặc Spring HATEOAS đã đăng ký. Nếu thay mapper của message converter bằng mapper mới, ứng dụng có thể mất hỗ trợ serialize `Link`, `_links` hoặc `_embedded` theo HAL.

Trong ứng dụng Boot, hãy ưu tiên tùy biến builder hoặc đăng ký Jackson `Module` theo cơ chế cấu hình của Boot. Ví dụ, một `Jackson2ObjectMapperBuilderCustomizer` có thể điều chỉnh cách ghi ngày giờ mà vẫn giữ cấu hình module do ứng dụng tự động đăng ký:

```java
import com.fasterxml.jackson.databind.SerializationFeature;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
        return builder -> builder.featuresToDisable(
                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }
}
```

Nếu cần serializer riêng, có thể đóng gói serializer trong một Jackson `Module` và đăng ký module theo cơ chế của framework. Hãy bảo đảm mapper được message converter hypermedia sử dụng cũng nhận được cấu hình đó. Tránh tự serialize `Link` thành chuỗi hoặc tự tạo thuộc tính `_links` trong DTO: cách làm này bỏ qua relation, metadata và quy tắc định dạng mà Spring HATEOAS cung cấp.

Với ứng dụng Spring MVC không dùng Boot, hãy giữ cấu hình Jackson và message converter HAL do `@EnableHypermediaSupport` thiết lập. Chỉ thay thế converter hoặc mapper khi có yêu cầu cụ thể và đã cấu hình đầy đủ module hypermedia tương ứng với phiên bản Spring HATEOAS đang dùng. Cách tích hợp thủ công phụ thuộc phiên bản thư viện; không nên sao chép cấu hình `ObjectMapper` từ một ví dụ khác mà chưa xác minh các module và handler cần thiết.

## Kiểm thử kết quả serialize

Kiểm thử qua HTTP giúp xác minh cả Jackson, message converter, content negotiation và cấu trúc HAL. Với MockMvc, có thể kiểm tra media type, dữ liệu tài nguyên và các relation:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderSerializationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void orderIsSerializedAsHal() throws Exception {
        mockMvc.perform(get("/api/orders/{id}",
                        "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").exists())
                .andExpect(jsonPath("$.total_amount").exists())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.orders.href").exists());
    }

    @Test
    void collectionUsesConfiguredEmbeddedRelation() throws Exception {
        mockMvc.perform(get("/api/orders").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._embedded.orders").isArray());
    }
}
```

Ví dụ giả định dữ liệu kiểm thử có đơn hàng với UUID đã nêu và collection có thể truy cập. Nếu ứng dụng có nhiều kiểu response, hãy bổ sung kiểm thử cho từng relation quan trọng, trường JSON được đổi tên, trường null và media type được công bố. Khi dùng custom serializer, cần kiểm tra rằng phần dữ liệu được chuyển đổi đúng mà `_links` và `_embedded` vẫn còn nguyên cấu trúc.

Một số lỗi thường gặp khi tích hợp Jackson với Spring HATEOAS:

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Response có dữ liệu nhưng không có `_links` | Controller trả DTO thuần hoặc message converter không được cấu hình cho hypermedia. | Trả về model HATEOAS và kiểm tra starter hoặc `@EnableHypermediaSupport`. |
| `Link` không được serialize theo HAL | Mapper/converter đang dùng thiếu cấu hình module hypermedia. | Dùng mapper và converter do tích hợp Spring HATEOAS thiết lập; rà soát cấu hình mapper tùy chỉnh. |
| Tên trong `_embedded` không như mong đợi | Relation của kiểu model chưa được xác định hoặc tên mặc định khác dự kiến. | Khai báo `@Relation` và kiểm tra JSON thực tế. |
| Trường dữ liệu bị đổi tên hoặc biến mất | Annotation Jackson, visibility hoặc custom serializer thay đổi schema. | Kiểm tra DTO và serializer; thêm assertion JSON path cho trường thuộc hợp đồng. |
| Client nhận sai định dạng | Header `Accept`, `produces` hoặc message converter không khớp. | Kiểm tra content negotiation và `Content-Type` trong response. |

## Giữ hợp đồng JSON và hypermedia ổn định

Khi thay đổi cấu hình Jackson, hãy đánh giá tác động lên cả dữ liệu và hypermedia. Đổi `totalAmount` thành `total_amount` là thay đổi tên thuộc tính JSON. Đổi relation `orders` thành `purchases` là thay đổi hợp đồng hypermedia. Đổi `application/hal+json` thành media type khác là thay đổi cách client diễn giải toàn bộ representation. Ba loại thay đổi này có phạm vi ảnh hưởng khác nhau và cần được kiểm thử riêng.

Các nguyên tắc thực hành:

- Dùng model HATEOAS và message converter hypermedia để Spring HATEOAS quản lý cấu trúc link.
- Dùng annotation Jackson cho thuộc tính dữ liệu, và `@Relation` cho tên relation của tài nguyên nhúng.
- Tạo link bằng API Spring HATEOAS; không ghép URL hay tự dựng `_links` trong DTO.
- Tùy biến mapper thông qua cơ chế cấu hình của Spring Boot hoặc Spring MVC để giữ các module hypermedia.
- Kiểm thử response qua HTTP với đúng `Accept` header, `Content-Type`, trường dữ liệu, `_links` và `_embedded`.

Khi Jackson và Spring HATEOAS được tích hợp đúng, ứng dụng vẫn tận dụng được khả năng serialize dữ liệu của Jackson, đồng thời công bố link và tài nguyên nhúng theo định dạng hypermedia. Client nhận được một representation nhất quán để vừa đọc dữ liệu, vừa khám phá các quan hệ mà server cung cấp.
