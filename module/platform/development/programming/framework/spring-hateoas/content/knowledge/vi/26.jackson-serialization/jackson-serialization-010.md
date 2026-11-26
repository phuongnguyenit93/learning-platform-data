# Kiểm tra JSON output

Khi dùng Spring HATEOAS, kiểm tra JSON output không chỉ là xác nhận các trường dữ liệu của DTO. Response còn có thể chứa `_links`, `_embedded`, relation của collection, metadata affordance và các giá trị được Jackson định dạng. API có thể trả HTTP `200 OK` nhưng vẫn phá vỡ hợp đồng client nếu relation đổi tên, link bị serialize sai cấu trúc, ngày tháng đổi định dạng hoặc trường quan trọng biến mất.

Cách kiểm tra đáng tin cậy là gọi endpoint qua `MockMvc` hoặc `WebTestClient`, yêu cầu đúng media type rồi xác nhận response thực tế. Với HAL, hãy kiểm tra `Content-Type`, dữ liệu, `_links`, `_embedded` và các trường hợp cấu hình serialization có ảnh hưởng tới cấu trúc JSON. Có thể dùng `JsonMapper` hoặc `ObjectMapper` do Spring Boot cấu hình để kiểm tra serialization trực tiếp, nhưng test qua HTTP vẫn cần thiết vì nó bao gồm cả content negotiation và HTTP message converter.

## JSON output là một phần của hợp đồng API

Giả sử endpoint trả một đơn hàng dưới dạng HAL. Client phụ thuộc vào cả dữ liệu và hypermedia:

```json
{
  "id": "ORD-2048",
  "status": "PENDING",
  "total": 1250000,
  "_links": {
    "self": { "href": "http://localhost:8080/api/orders/ORD-2048" },
    "customer": { "href": "http://localhost:8080/api/customers/C-100" }
  }
}
```

Khi kiểm tra output, cần xác nhận tên và kiểu của các trường dữ liệu; giá trị enum, số tiền, ngày giờ và giá trị nullable; media type; relation và `href`; tên collection trong `_embedded`; hình dạng link đơn/nhiều; và template affordance nếu endpoint công bố chúng.

Nên xem những thành phần này như hợp đồng mà client tiêu thụ. Nếu đổi tên field hoặc relation, cần đánh giá tác động tương tự khi đổi tên endpoint hoặc thay đổi HTTP status.

## Kiểm tra response qua MockMvc

`MockMvc` gửi request qua Spring MVC trong test context. Nhờ vậy, test kiểm tra cả controller, assembler, processor, content negotiation, Jackson module và HTTP message converter.

Ví dụ endpoint đọc đơn hàng trả `EntityModel<OrderResponse>`:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    public OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<OrderResponse> one(@PathVariable UUID id) {
        return assembler.toModel(service.findRequired(id));
    }
}
```

Test xác nhận status, media type, dữ liệu và link:

```java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderJsonOutputTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsOrderAsHalJson() throws Exception {
        UUID orderId = UUID.fromString("c4126a60-0d15-4df3-9d9d-5bb9b88a2a10");

        mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value(orderId.toString()))
            .andExpect(jsonPath("$.status").value("PENDING"))
            .andExpect(jsonPath("$.total").value(1250000))
            .andExpect(jsonPath("$._links.self.href")
                    .value(endsWith("/api/orders/" + orderId)))
            .andExpect(jsonPath("$._links.customer.href").exists());
    }
}
```

Matcher `endsWith(...)` xác nhận path cuối mà không khóa test vào scheme, hostname hoặc port. Đây thường là lựa chọn tốt khi các môi trường test có địa chỉ khác nhau. Nếu host công khai hoặc scheme HTTPS là một phần của cấu hình cần bảo vệ, hãy có test riêng cho các thuộc tính đó.

`contentTypeCompatibleWith(...)` kiểm tra media type tương thích, không buộc test phụ thuộc vào tham số charset. Với HAL JSON, dùng `MediaTypes.HAL_JSON` thay vì tự gõ chuỗi để tránh lỗi chính tả.

## Kiểm tra JSON bằng JsonPath

JsonPath cho phép truy cập trực tiếp vào một phần của JSON mà không cần so sánh toàn bộ chuỗi. Một số assertion thường dùng:

| Mục tiêu | Ví dụ JsonPath |
|---|---|
| Trường cấp cao nhất | `$.id` |
| Link self | `$._links.self.href` |
| Link liên quan | `$._links.customer.href` |
| Embedded object | `$._embedded.customer.id` |
| Embedded collection | `$._embedded.items` |
| Số phần tử | `$._embedded.items.length()` |
| Trường không được công bố | `$.internalSupplierCode` với `doesNotExist()` |

Ví dụ kiểm tra collection:

```java
mockMvc.perform(get("/api/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.orders.length()").value(2))
    .andExpect(jsonPath("$._embedded.orders[0].id").exists())
    .andExpect(jsonPath("$._embedded.orders[0]._links.self.href").exists());
```

Tên `orders` phụ thuộc relation collection mà ứng dụng cấu hình qua `@Relation` hoặc `LinkRelationProvider`. Nếu relation của API là `orderList`, test phải dùng đúng tên đã công bố. Không suy ra tên relation từ tên class nếu tên đó là một phần của hợp đồng client.

JsonPath cũng giúp xác nhận trường không bị lộ:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.internalSupplierCode").doesNotExist())
    .andExpect(jsonPath("$.databaseVersion").doesNotExist());
```

Đây là kiểm tra hữu ích khi response được tạo từ DTO hoặc representation model có nguy cơ vô tình thêm trường nội bộ sau một lần refactor.

## Kiểm tra collection rỗng

Collection rỗng cần được kiểm tra riêng vì Java type erasure có thể khiến serializer không suy ra được relation của phần tử. Nếu hợp đồng yêu cầu `_embedded.orders` luôn tồn tại dưới dạng mảng, hãy tạo `CollectionModel` có fallback type:

```java
CollectionModel<OrderResponse> emptyOrders =
        CollectionModel.<OrderResponse>empty()
                .withFallbackType(OrderResponse.class);
```

Test xác nhận mảng rỗng:

```java
mockMvc.perform(get("/api/orders").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.orders").isArray())
    .andExpect(jsonPath("$._embedded.orders.length()").value(0));
```

Nếu API chủ ý bỏ `_embedded` khi collection rỗng, hãy kiểm tra đúng hành vi đó. Điều quan trọng là output phải nhất quán với hợp đồng đã chọn, để client biết sự khác nhau giữa collection rỗng và relation không được công bố.

## Kiểm tra hình dạng của link trong HAL

Trong HAL, `_links` là object có các khóa là relation. Giá trị của một relation có thể là một link object hoặc một mảng link object.

Mặc định, Spring HATEOAS serialize một link duy nhất thành object:

```json
{
  "_links": {
    "self": { "href": "/api/orders/ORD-2048" }
  }
}
```

Khi một relation có nhiều link, giá trị là mảng:

```json
{
  "_links": {
    "item": [
      { "href": "/api/cart/items/1" },
      { "href": "/api/cart/items/2" }
    ]
  }
}
```

HAL cho phép cấu hình link đơn cũng được render thành mảng. Nếu ứng dụng bật `RenderSingleLinks.AS_ARRAY`, test phải đọc `$._links.self[0].href` thay vì `$._links.self.href`:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self").isArray())
    .andExpect(jsonPath("$._links.self[0].href").exists());
```

Ví dụ cấu hình toàn cục:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.mediatype.hal.HalConfiguration;
import org.springframework.hateoas.mediatype.hal.HalConfiguration.RenderSingleLinks;

@Configuration
class HalRenderingConfiguration {

    @Bean
    HalConfiguration halConfiguration() {
        return new HalConfiguration()
                .withRenderSingleLinks(RenderSingleLinks.AS_ARRAY);
    }
}
```

Không viết test theo hình dạng object hoặc array trước khi xác nhận `HalConfiguration` của ứng dụng. Thay đổi chính sách render link đơn có thể làm client cũ không còn đọc được JSON theo đường dẫn cũ, vì vậy cần coi đây là thay đổi hợp đồng.

## Kiểm tra content negotiation

JSON output phụ thuộc vào `Accept` mà client gửi và các media type endpoint hỗ trợ. Một test nên yêu cầu rõ HAL:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON));
```

Nếu endpoint chỉ hỗ trợ HAL mà client yêu cầu media type không được cấu hình, có thể kiểm tra phản hồi `406 Not Acceptable`:

```java
import org.springframework.http.MediaType;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaType.APPLICATION_XML))
    .andExpect(status().isNotAcceptable());
```

Chỉ dùng assertion `406` nếu ứng dụng thực sự không đăng ký converter hoặc media type XML cho endpoint đó. Nếu API hỗ trợ nhiều representation, hãy kiểm tra từng `Accept` tương ứng.

Spring Boot có thể mặc định trả HAL khi client gửi `Accept: application/json`. Hành vi này được điều khiển bởi cấu hình `spring.hateoas.use-hal-as-default-json-media-type`. Nếu ứng dụng đặt thuộc tính này thành `false`, response cho `application/json` có thể khác HAL. Test cần phản ánh cấu hình thật của ứng dụng thay vì giả định mọi request JSON đều là HAL.

## Kiểm tra dữ liệu Jackson serialize

Ngoài hypermedia, Jackson quyết định cách các trường dữ liệu được ghi ra JSON. Cần kiểm tra những phần có ý nghĩa với client:

| Dữ liệu | Điều cần xác nhận |
|---|---|
| Enum | Tên chuỗi hay giá trị khác theo cấu hình |
| Ngày giờ | ISO-8601, timezone và độ chính xác |
| Số tiền | Kiểu number, scale và đơn vị |
| Null | Trường được giữ với `null` hay bị bỏ qua |
| Tên property | `camelCase`, `snake_case` hoặc naming strategy tùy chỉnh |
| Collection | Mảng rỗng hay trường bị bỏ qua |
| Boolean | `true`/`false` và quy tắc bỏ qua giá trị mặc định |

Ví dụ response có thời điểm tạo đơn hàng:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderResponse(
        UUID id,
        OrderStatus status,
        BigDecimal total,
        Instant createdAt,
        String note
) {}
```

Test có thể xác nhận định dạng ngày giờ và chính sách null:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.createdAt").value("2026-11-26T04:30:00Z"))
    .andExpect(jsonPath("$.status").value("PENDING"))
    .andExpect(jsonPath("$.note").doesNotExist());
```

Assertion về `note` phụ thuộc cấu hình inclusion của Jackson và annotation trên DTO. Nếu hợp đồng yêu cầu `"note": null`, dùng `jsonPath("$.note").value(nullValue())` với matcher Hamcrest `nullValue()` thay cho `doesNotExist()`. Hai dạng JSON này khác nhau và có thể có ý nghĩa khác nhau với client.

Nếu ứng dụng dùng property naming strategy như `SNAKE_CASE`, hãy kiểm tra tên output thực tế, ví dụ `created_at`, thay vì tên Java `createdAt`. Với HAL, cần kiểm tra riêng cả relation `_embedded` và tên field content; không mặc định mọi tên trong JSON đều được xử lý giống nhau.

## Kiểm tra serialization trực tiếp bằng mapper của ứng dụng

Đôi khi cần test riêng việc serialize một representation model mà không gửi HTTP request. Khi đó, hãy inject mapper do Spring Boot cấu hình để giữ các module và customizer của ứng dụng.

Với Spring Boot 4.x mặc định Jackson 3, mapper là `tools.jackson.databind.json.JsonMapper`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

@SpringBootTest
class OrderMapperSerializationTest {

    @Autowired
    JsonMapper jsonMapper;

    @Test
    void serializesEntityModelWithHalLinks() throws Exception {
        UUID id = UUID.fromString("c4126a60-0d15-4df3-9d9d-5bb9b88a2a10");
        EntityModel<OrderResponse> model = EntityModel.of(
                new OrderResponse(
                        id,
                        OrderStatus.PENDING,
                        new BigDecimal("1250000"),
                        Instant.parse("2026-11-26T04:30:00Z"),
                        null
                ),
                Link.of("/api/orders/ORD-2048").withSelfRel()
        );

        String json = jsonMapper.writeValueAsString(model);
        JsonNode root = jsonMapper.readTree(json);

        assertEquals("PENDING", root.path("status").asText());
        assertEquals("/api/orders/ORD-2048",
                root.path("_links").path("self").path("href").asText());
        assertTrue(root.path("_links").path("self").isObject());
    }
}
```

Với Spring Boot 3.x sử dụng Jackson 2, inject `com.fasterxml.jackson.databind.ObjectMapper` thay cho `tools.jackson.databind.json.JsonMapper`; kiểu `JsonNode` cũng dùng package `com.fasterxml.jackson.databind.JsonNode`. Hãy dùng đúng mapper mà ứng dụng đang dùng cho HTTP serialization.

Test mapper trực tiếp hữu ích cho unit test serialization, nhưng không xác nhận endpoint đã chọn đúng converter, media type hoặc header. Nếu ứng dụng tự khai báo mapper mới mà không kế thừa cấu hình Spring HATEOAS, các module HAL có thể không được đăng ký. Đừng tự tạo mapper bằng `new ObjectMapper()` hoặc `JsonMapper.builder().build()` rồi dùng nó để kết luận response HTTP sẽ có cùng cấu trúc.

## Kiểm tra response JSON hoàn chỉnh

Trong một số trường hợp, hợp đồng yêu cầu xác nhận toàn bộ cấu trúc JSON. Có thể lấy body từ `MvcResult` và parse thành `JsonNode` để kiểm tra theo cấu trúc:

Đoạn test dưới đây giả định class đã inject `MockMvc` và `JsonMapper` như phần trước, đồng thời có một `orderId` hợp lệ.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MvcResult;

@Autowired
JsonMapper jsonMapper;

MvcResult result = mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andReturn();

JsonNode root = jsonMapper.readTree(result.getResponse().getContentAsString());

assertEquals(orderId.toString(), root.path("id").asText());
assertTrue(root.path("_links").has("self"));
assertTrue(root.path("_links").has("customer"));
```

Nếu cần so sánh với JSON mẫu, dùng công cụ so sánh JSON theo cấu trúc thay vì so sánh chuỗi thô. So sánh chuỗi thường bị ảnh hưởng bởi khoảng trắng, xuống dòng, thứ tự property và cách escape. Chỉ dùng strict comparison khi thứ tự mảng, property hoặc mọi trường đều là một phần của hợp đồng cần kiểm tra.

Ví dụ với JSONAssert (nếu dự án đã có dependency tương ứng):

```java
import org.skyscreamer.jsonassert.JSONAssert;
import org.skyscreamer.jsonassert.JSONCompareMode;

JSONAssert.assertEquals(
        expectedJson,
        result.getResponse().getContentAsString(),
        JSONCompareMode.LENIENT
);
```

`LENIENT` bỏ qua thứ tự property của object và cho phép một số khác biệt không quan trọng theo chế độ so sánh; nó vẫn kiểm tra nội dung JSON. Với các mảng như danh sách item, hãy quyết định rõ thứ tự có phải một phần của hợp đồng hay không.

## Kiểm tra affordance và HAL-FORMS output

Nếu controller gắn affordance và client yêu cầu HAL-FORMS, output có thể chứa `_templates`. Test cần yêu cầu media type HAL-FORMS và kiểm tra template, method cùng property:

```java
mockMvc.perform(get("/api/employees/{id}", employeeId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_FORMS_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates.default.method").value("put"))
    .andExpect(jsonPath("$._templates.default.properties[?(@.name == 'email')]")
            .isNotEmpty());
```

HAL-FORMS là media type riêng, không phải HAL JSON thông thường. Không kiểm tra `_templates` khi endpoint chỉ trả `application/hal+json`, trừ khi API có một định dạng tùy chỉnh công bố cấu trúc đó.

## Những lỗi thường gặp khi kiểm tra JSON output

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra status `200` | Không phát hiện JSON sai cấu trúc | Kiểm tra content type, field, link và embedded |
| So sánh toàn bộ chuỗi JSON | Test dễ hỏng do whitespace hoặc thứ tự object property | Dùng JsonPath hoặc parse thành `JsonNode` |
| Hard-code host/port | Test phụ thuộc môi trường | Kiểm tra path hoặc resolve base URI từ test config |
| Giả định link đơn luôn là object | Test hỏng khi `HalConfiguration` render array | Đồng bộ assertion với chính sách link rendering |
| Không kiểm tra relation collection | `_embedded` có thể đổi tên mà test vẫn pass | Kiểm tra đúng khóa relation trong hợp đồng |
| Bỏ qua collection rỗng | Relation có thể biến mất do type erasure | Dùng fallback type và test mảng rỗng nếu cần |
| Dùng mapper tự tạo | Thiếu HAL Jackson module hoặc customizer | Inject mapper của ứng dụng hoặc test qua MockMvc |
| Không kiểm tra `Accept`/`Content-Type` | Nhầm JSON thường với HAL hoặc HAL-FORMS | Gửi `Accept` rõ ràng và assert content type |
| Coi `null` và trường vắng mặt là giống nhau | Client có thể xử lý sai dữ liệu | Kiểm tra đúng chính sách null inclusion |
| Bỏ qua trường nội bộ | Có thể vô tình công bố dữ liệu không dành cho client | Assert trường nhạy cảm không xuất hiện |

## Checklist kiểm tra JSON output

1. Gửi request với `Accept` đúng media type mà client sử dụng.
2. Kiểm tra status và `Content-Type` của response.
3. Kiểm tra tên, kiểu và giá trị các trường dữ liệu quan trọng.
4. Kiểm tra enum, ngày giờ, số tiền và chính sách null.
5. Kiểm tra `_links`, relation, `href` và hình dạng object/array.
6. Kiểm tra `_embedded`, tên relation, số phần tử và collection rỗng.
7. Kiểm tra `_templates` nếu endpoint công bố HAL-FORMS affordance.
8. Kiểm tra trường nội bộ hoặc nhạy cảm không xuất hiện trong JSON.
9. Dùng mapper của ứng dụng cho test serialization trực tiếp; dùng MockMvc/WebTestClient để xác nhận response HTTP.
10. Tránh so sánh chuỗi JSON thô nếu whitespace và thứ tự object property không phải hợp đồng.

## Kết luận

Kiểm tra JSON output của Spring HATEOAS cần xác nhận cả dữ liệu Jackson serialize lẫn cấu trúc hypermedia mà client sử dụng. `MockMvc` kết hợp JsonPath giúp kiểm tra response HTTP, media type, `_links`, `_embedded` và affordance; mapper do Spring Boot cấu hình giúp kiểm tra serialization trực tiếp của representation model. Khi test tính đến chính sách render link đơn, relation collection, collection rỗng, định dạng ngày giờ và null inclusion, nhóm phát triển có thể phát hiện sớm thay đổi ngoài ý muốn trong hợp đồng JSON/HAL.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Representation Models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models): cách `RepresentationModel`, `EntityModel` và `CollectionModel` được render theo media type.
- [Spring HATEOAS Reference – Configuring HAL Link Rendering](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal.link-rendering): hình dạng link đơn, link nhiều phần tử và `HalConfiguration`.
- [Spring Boot – Spring HATEOAS](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html): auto-configuration và mapper được cấu hình cho hypermedia.
- [Spring Framework – Defining MockMvc Expectations](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/expectations.html): kiểm tra HTTP response và JSON hypermedia bằng JsonPath.
- [Spring Boot – JSON](https://docs.spring.io/spring-boot/reference/features/json.html): tích hợp Jackson 3 `JsonMapper` và Jackson 2 `ObjectMapper`.
