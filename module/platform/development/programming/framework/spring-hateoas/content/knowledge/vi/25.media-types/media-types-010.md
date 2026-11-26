# Kiểm thử negotiation

Content negotiation cho phép client và server thống nhất định dạng representation được trao đổi qua HTTP. Trong Spring HATEOAS, cùng một tài nguyên có thể được trả về dưới HAL hoặc HAL-FORMS tùy media type client yêu cầu. Khi endpoint nhận dữ liệu, server còn phải kiểm tra media type của request body. Vì vậy, một bài kiểm thử API cần xác nhận cả định dạng đầu vào, định dạng đầu ra và cấu trúc hypermedia thực tế.

Spring MVC cung cấp các thuộc tính produces và consumes trên mapping; HTTP dùng Accept để client nêu định dạng response mong muốn và Content-Type để mô tả định dạng request body. Spring HATEOAS bổ sung các media type như application/hal+json và application/prs.hal-forms+json. Kiểm thử negotiation cần chứng minh server chọn đúng converter, trả đúng status code khi không thể thỏa thuận và giữ nguyên hợp đồng link hoặc affordance.

Bài học này tập trung vào kiểm thử content negotiation trong Spring HATEOAS bằng MockMvc và WebTestClient, bao gồm HAL, HAL-FORMS, wildcard, quality factor, lỗi 406/415 và media type tùy chỉnh.

## 1. Content negotiation hoạt động như thế nào?

Client và server trao đổi hai thông tin khác nhau:

- Accept mô tả media type client muốn nhận trong response.
- Content-Type mô tả media type của request body mà client gửi lên.

Ví dụ client muốn nhận HAL:

~~~http
GET /api/orders/42
Accept: application/hal+json
~~~

Ví dụ client gửi JSON để tạo đơn hàng và muốn nhận HAL:

~~~http
POST /api/orders
Content-Type: application/json
Accept: application/hal+json

{
  "customerId": 7,
  "total": 1250000
}
~~~

Hai header này không thay thế cho nhau. Accept: application/hal+json không nói rằng request body là HAL. Tương tự, Content-Type: application/json không yêu cầu server phải trả JSON thuần.

Trong Spring MVC, produces giới hạn media type mà endpoint có thể trả về; consumes giới hạn media type của request body mà endpoint chấp nhận. Spring sử dụng các thông tin đó cùng message converter để chọn cách đọc request và ghi response.

## 2. Các media type thường gặp trong Spring HATEOAS

| Media type | Mục đích |
| --- | --- |
| application/hal+json | Biểu diễn tài nguyên và link theo HAL |
| application/prs.hal-forms+json | Biểu diễn HAL kèm template mô tả thao tác và input |
| application/json | JSON thông thường, không tự mang cấu trúc HAL |
| application/vnd.example.order+json | Ví dụ media type riêng của API, thường dùng để phân biệt representation theo vendor hoặc version |

HAL dùng _links để công bố liên kết và _embedded để chứa tài nguyên nhúng. HAL-FORMS giữ cấu trúc hypermedia của HAL và bổ sung _templates để mô tả các thao tác có thể thực hiện.

Ví dụ HAL:

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

Ví dụ HAL-FORMS:

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
    "default": {
      "method": "delete",
      "properties": []
    }
  }
}
~~~

Không nên xem application/json và application/hal+json là hai tên khác nhau cho cùng một hợp đồng. JSON là cú pháp dữ liệu; HAL còn quy định cách biểu diễn link và resource nhúng.

## 3. Cấu hình endpoint với produces và consumes

Ví dụ controller có endpoint đọc đơn hàng và tạo đơn hàng:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping(
            value = "/{id}",
            produces = {
                    MediaTypes.HAL_JSON_VALUE,
                    MediaTypes.HAL_FORMS_JSON_VALUE
            }
    )
    public EntityModel<OrderDto> one(@PathVariable Long id) {
        OrderDto order = orderService.getRequired(id);

        Link self = linkTo(methodOn(OrderController.class)
                .one(id))
                .withSelfRel()
                .andAffordance(afford(methodOn(OrderController.class)
                        .delete(id)));

        return EntityModel.of(order, self);
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = {
                    MediaTypes.HAL_JSON_VALUE,
                    MediaTypes.HAL_FORMS_JSON_VALUE
            }
    )
    public EntityModel<OrderDto> create(
            @RequestBody CreateOrderRequest request
    ) {
        OrderDto order = orderService.create(request);

        return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel()
        );
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        orderService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Trong ví dụ:

- GET chỉ công bố HAL và HAL-FORMS trong produces.
- POST chỉ nhận application/json trong consumes.
- POST có thể trả HAL hoặc HAL-FORMS theo Accept.
- DELETE không có request body và trả 204 No Content.
- Affordance DELETE được gắn vào self link để HAL-FORMS có thể mô tả thao tác.

Các kiểu OrderDto, CreateOrderRequest và OrderService được giả định đã khai báo trong ứng dụng. Mỗi kiểu public được đặt trong file Java riêng.

Kiểu dữ liệu và service rút gọn dùng trong ví dụ:

~~~java
import java.math.BigDecimal;

public record OrderDto(Long id, String status) {
}

public record CreateOrderRequest(Long customerId, BigDecimal total) {
}

public interface OrderService {
    OrderDto getRequired(Long id);
    OrderDto create(CreateOrderRequest request);
    void delete(Long id);
}
~~~

Nếu bỏ produces, Spring có thể chọn converter dựa trên các converter khả dụng và Accept. Với API hypermedia, khai báo media type công khai trên mapping giúp hợp đồng rõ ràng và làm cho kiểm thử negotiation có kết quả xác định.

## 4. Bật hỗ trợ HAL và HAL-FORMS

Trong Spring Boot, cấu hình Spring HATEOAS phù hợp có thể được tự động thiết lập qua auto-configuration. Nếu muốn khai báo tường minh các định dạng cần hỗ trợ:

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

Chỉ thêm cấu hình khi ứng dụng chưa được auto-configure đúng. Tránh đăng ký lặp các thành phần hypermedia converter hoặc cấu hình không tương thích với phiên bản Spring Boot đang dùng.

Trong test slice WebMvcTest, cấu hình hypermedia cần được import nếu không nằm trong phạm vi component scan của test:

~~~java
@WebMvcTest(OrderController.class)
@Import(HypermediaConfiguration.class)
~~~

Đặt hai annotation này trên test class kiểm tra controller.

## 5. Kiểm thử response HAL với MockMvc

MockMvc cho phép gửi request với Accept cụ thể và kiểm tra Content-Type cùng cấu trúc JSON trả về.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(HypermediaConfiguration.class)
class OrderControllerNegotiationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void returnsHalWhenClientAcceptsHalJson() throws Exception {
        when(orderService.getRequired(42L))
                .thenReturn(new OrderDto(42L, "PENDING"));

        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Kiểm thử này xác nhận ba điều:

1. Server chọn response thành công.
2. Content-Type tương thích với application/hal+json.
3. Payload có cấu trúc HAL với _links.self.

Chỉ kiểm tra status 200 là chưa đủ. Nếu endpoint vô tình trả JSON thuần, test status vẫn có thể qua trong khi hợp đồng hypermedia đã sai.

## 6. Kiểm thử response HAL-FORMS

Khi client yêu cầu HAL-FORMS, response phải có media type tương ứng và có thể chứa _templates nếu representation có affordance:

~~~java
@Test
void returnsHalFormsWhenClientAcceptsHalForms() throws Exception {
    when(orderService.getRequired(42L))
            .thenReturn(new OrderDto(42L, "PENDING"));

    mockMvc.perform(get("/api/orders/42")
                    .accept(MediaTypes.HAL_FORMS_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_FORMS_JSON))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._templates").exists());
}
~~~

Nếu controller không gắn affordance hoặc không có thao tác tương ứng, _templates có thể không xuất hiện. Trong trường hợp đó, test nên kiểm tra đúng hợp đồng đã thiết kế thay vì giả định mọi HAL-FORMS response đều bắt buộc có template.

HAL-FORMS không chỉ là HAL JSON đổi tên media type. Nó cần converter và cấu hình phù hợp để tuần tự hóa metadata affordance thành template.

## 7. Kiểm thử 406 Not Acceptable

Nếu endpoint chỉ khai báo produces là HAL và HAL-FORMS, client yêu cầu application/json thuần thì server không có representation phù hợp. Spring MVC thường trả 406 Not Acceptable.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

@Test
void returns406WhenAcceptHeaderIsUnsupported() throws Exception {
    mockMvc.perform(get("/api/orders/42")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotAcceptable());
}
~~~

Lỗi 406 liên quan đến định dạng response mà client chấp nhận. Nó khác với 415 Unsupported Media Type, vốn liên quan đến định dạng request body mà endpoint không nhận.

Nếu endpoint không khai báo produces, converter có thể hỗ trợ application/json; khi đó test này không còn đúng. Hãy kiểm tra mapping thực tế trước khi kỳ vọng 406.

## 8. Kiểm thử 415 Unsupported Media Type

Với POST khai báo:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public EntityModel<OrderDto> create(
        @RequestBody CreateOrderRequest request
) {
    // ...
}
~~~

request body có Content-Type: text/plain không phù hợp với consumes. Spring MVC trả 415 Unsupported Media Type.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import org.springframework.http.MediaType;

@Test
void returns415WhenRequestContentTypeIsUnsupported() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaTypes.HAL_JSON)
                    .content("not-json"))
            .andExpect(status().isUnsupportedMediaType());
}
~~~

Để kiểm thử thành công, dùng đúng Content-Type và JSON body:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import org.springframework.http.MediaType;

@Test
void acceptsJsonRequestAndReturnsHal() throws Exception {
    when(orderService.create(any(CreateOrderRequest.class)))
            .thenReturn(new OrderDto(42L, "PENDING"));

    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaTypes.HAL_JSON)
                    .content("""
                            {
                              "customerId": 7,
                              "total": 1250000
                            }
                            """))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists());
}
~~~

Ví dụ dùng text block của Java 15 trở lên. Nếu dự án dùng Java thấp hơn, có thể thay bằng chuỗi JSON thông thường. Cần import post và any khi đặt các đoạn test vào test class.

## 9. Kiểm thử Accept có nhiều media type và quality factor

Client có thể gửi nhiều lựa chọn trong Accept, kèm quality factor q để biểu thị mức ưu tiên:

~~~http
Accept: application/hal+json;q=1.0, application/prs.hal-forms+json;q=0.7
~~~

Server cần chọn representation phù hợp nhất trong số media type mà endpoint hỗ trợ. Có thể kiểm thử bằng:

~~~java
import org.springframework.http.MediaType;

@Test
void prefersHalWhenItHasHigherQualityValue() throws Exception {
    MediaType hal = MediaType.parseMediaType(
            "application/hal+json;q=1.0"
    );
    MediaType halForms = MediaType.parseMediaType(
            "application/prs.hal-forms+json;q=0.7"
    );

    when(orderService.getRequired(42L))
            .thenReturn(new OrderDto(42L, "PENDING"));

    mockMvc.perform(get("/api/orders/42")
                    .accept(hal, halForms))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON));
}
~~~

Quality factor cao hơn thể hiện ưu tiên cao hơn. Khi các lựa chọn có cùng q, độ cụ thể của media range và quy tắc lựa chọn của framework cũng ảnh hưởng kết quả. Không nên dựa vào thứ tự chuỗi header nếu test có thể khai báo q tường minh.

## 10. Kiểm thử wildcard Accept

Client có thể gửi:

~~~http
Accept: */*
~~~

Wildcard có nghĩa client không giới hạn media type. Spring chọn một representation mà endpoint và converter hỗ trợ. Nếu endpoint công bố nhiều produces, kết quả mặc định có thể phụ thuộc danh sách mapping và converter đã đăng ký.

Có thể kiểm tra request wildcard không bị từ chối:

~~~java
import org.springframework.http.MediaType;

mockMvc.perform(get("/api/orders/42")
        .accept(MediaType.ALL))
    .andExpect(status().isOk());
~~~

Nếu ứng dụng yêu cầu một media type mặc định cụ thể khi client không gửi Accept hoặc gửi wildcard, hãy cấu hình và kiểm thử chính sách mặc định đó. Không nên viết test giả định một định dạng mặc định nếu ứng dụng chưa quy định.

## 11. Kiểm thử Content-Type và Accept độc lập

Một request POST có thể gửi JSON nhưng yêu cầu response HAL-FORMS:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import org.springframework.http.MediaType;

@Test
void acceptsJsonInputAndNegotiatesHalFormsOutput() throws Exception {
    when(orderService.create(any(CreateOrderRequest.class)))
            .thenReturn(new OrderDto(42L, "PENDING"));

    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaTypes.HAL_FORMS_JSON)
                    .content("""
                            {
                              "customerId": 7,
                              "total": 1250000
                            }
                            """))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_FORMS_JSON));
}
~~~

Test này thể hiện rõ hai chiều negotiation:

- Content-Type: application/json được kiểm tra bởi consumes.
- Accept: application/prs.hal-forms+json được kiểm tra bởi produces và message converter đầu ra.

Một request có thể vượt qua kiểm tra consumes nhưng vẫn nhận 406 nếu Accept không phù hợp. Ngược lại, Accept hợp lệ nhưng request body có Content-Type không được hỗ trợ có thể nhận 415.

## 12. Kiểm thử cấu trúc hypermedia, không chỉ media type

Sau khi kiểm tra Content-Type, hãy kiểm tra các thành phần mà client thực sự phụ thuộc:

| Media type | Các assertion nên có |
| --- | --- |
| HAL | _links.self, relation quan trọng, _embedded nếu có |
| HAL-FORMS | _links, _templates, method, properties |
| Vendor media type | Cấu trúc version hoặc profile được công bố |

Ví dụ với collection HAL:

~~~java
mockMvc.perform(get("/api/orders")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._embedded.orders").exists())
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Ví dụ với affordance HAL-FORMS:

~~~java
mockMvc.perform(get("/api/orders/42")
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._templates").exists());
~~~

Không nên chỉ kiểm tra response là JSON. JSON parser chấp nhận cả JSON thuần lẫn HAL, nhưng điều đó không chứng minh client có thể điều hướng bằng link relation hoặc gửi thao tác dựa trên affordance.

## 13. Kiểm thử bằng WebTestClient cho WebFlux

Với ứng dụng Spring WebFlux, dùng WebTestClient để kiểm tra negotiation tương tự:

~~~java
import org.springframework.hateoas.MediaTypes;
import org.springframework.beans.factory.annotation.Autowired;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderWebFluxNegotiationTest {

    @Autowired
    private WebTestClient client;

    @Test
    void returnsHal() {
        client.get()
                .uri("/api/orders/42")
                .accept(MediaTypes.HAL_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaTypes.HAL_JSON)
                .expectBody()
                    .jsonPath("$._links.self.href").exists();
    }

    @Test
    void rejectsUnsupportedAccept() {
        client.get()
                .uri("/api/orders/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isEqualTo(406);
    }
}
~~~

Đây là ví dụ minh họa; test class cần được cấu hình bằng WebFluxTest hoặc bind với application context phù hợp. Nguyên tắc negotiation vẫn giống MVC: Accept chọn response, Content-Type mô tả request body. Khác biệt là test client và stack xử lý request.

## 14. Media type tùy chỉnh và versioning

Một API có thể công bố vendor media type:

~~~text
application/vnd.example.order-v1+json
~~~

Vendor media type có thể giúp phân biệt representation theo version hoặc profile. Tuy nhiên, hậu tố +json chỉ cho biết cú pháp dựa trên JSON; nó không tự động biến payload thành HAL hoặc HAL-FORMS.

Nếu media type tùy chỉnh cần giữ cấu trúc hypermedia, ứng dụng phải đăng ký cấu hình mapping/converter tương ứng theo extension point của Spring HATEOAS, thay vì chỉ thêm chuỗi media type vào produces và giả định converter HAL sẽ tự xử lý.

Nếu chỉ dùng vendor type cho DTO JSON thông thường, có thể khai báo nó trong produces và kiểm thử response Content-Type. Nếu dùng để phân biệt version, cần kiểm thử:

- Client v1 nhận đúng representation v1.
- Client v2 nhận đúng representation v2.
- Client gửi media type không được hỗ trợ nhận status phù hợp.
- Các link và relation vẫn nhất quán trong từng representation version.

Không nên thay đổi cấu trúc representation dưới cùng một media type mà không có chiến lược tương thích rõ ràng.

## 15. Những lỗi thường gặp

**Nhầm Accept với Content-Type.** Accept chọn định dạng response; Content-Type mô tả request body. Kiểm thử hai header độc lập.

**Chỉ kiểm tra status 200.** Response có thể thành công nhưng trả sai media type hoặc thiếu _links. Kiểm tra Content-Type và cấu trúc hypermedia.

**Dùng application/json để kiểm tra HAL.** JSON thuần không chứng minh converter HAL đã được dùng. Gửi Accept application/hal+json.

**Kỳ vọng HAL có _templates.** HAL cơ bản không biểu diễn affordance thành form template như HAL-FORMS. Dùng Accept application/prs.hal-forms+json.

**Nhầm 406 và 415.** 406 liên quan đến response không thỏa Accept; 415 liên quan đến request body không thỏa Content-Type/consumes.

**Không khai báo produces khi muốn giới hạn hợp đồng.** Nếu endpoint không giới hạn media type, converter khác có thể khiến request Accept: application/json vẫn thành công. Xác định rõ chính sách đầu ra.

**Giả định wildcard luôn chọn một media type cố định.** */* cho phép nhiều định dạng. Nếu cần mặc định xác định, cấu hình và kiểm thử rõ.

**Cho rằng hậu tố +json đồng nghĩa HAL.** Vendor media type có hậu tố +json vẫn cần mapping/converter phù hợp nếu muốn serialize theo một hypermedia format.

**Không kiểm thử request thành công với Content-Type hợp lệ.** Bài test 415 cần đi kèm test chấp nhận request đúng định dạng để xác nhận endpoint hoạt động.

## 16. Ghi nhớ

Content negotiation trong Spring HATEOAS cần kiểm tra hai hướng: Accept quyết định media type response, còn Content-Type mô tả request body. Spring MVC dùng produces để giới hạn đầu ra và consumes để giới hạn đầu vào. HAL thường dùng application/hal+json; HAL-FORMS dùng application/prs.hal-forms+json.

Với MockMvc, gửi Accept cụ thể rồi kiểm tra status, Content-Type, _links, _embedded và _templates theo hợp đồng. Dùng 406 Not Acceptable cho trường hợp không có response phù hợp và 415 Unsupported Media Type cho request body không được chấp nhận. Kiểm thử thêm quality factor và wildcard khi API hỗ trợ nhiều lựa chọn.

Với WebFlux, dùng WebTestClient để kiểm tra cùng các quy tắc negotiation. Nếu API công bố vendor media type, hãy cấu hình converter hoặc hypermedia mapping phù hợp; hậu tố +json không tự động tạo cấu trúc HAL. Kiểm thử cả media type lẫn nội dung hypermedia để bảo đảm client nhận đúng hợp đồng mà server công bố.

## Tài liệu tham khảo

- [Spring Framework – Mapping Requests: consumes and produces](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework – HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring HATEOAS Reference – Media Types](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes)
- [Spring HATEOAS MediaTypes API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html)
- [Spring Boot – Spring HATEOAS](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
