# Version trong media type với Spring HATEOAS

Một tài nguyên có thể giữ nguyên URI nhưng được biểu diễn theo nhiều phiên bản contract. Ví dụ, client truy cập cùng một đơn hàng tại `/orders/42` nhưng nhận cấu trúc V1 hoặc V2 tùy theo media type mà nó yêu cầu. Đây là cách versioning thông qua media type: client mô tả representation mình hiểu bằng header HTTP, còn server chọn representation phù hợp.

Với Spring MVC, content negotiation dựa trên `Accept` và `Content-Type` có thể kết hợp với thuộc tính `produces` và `consumes` của mapping. Spring HATEOAS tiếp tục chịu trách nhiệm serialize representation có links theo định dạng HAL hoặc media type hypermedia đã đăng ký.

## 1. Version trong media type là gì?

Media type xác định định dạng representation và cách recipient cần xử lý dữ liệu. HTTP dùng `Accept` để client nêu những loại representation có thể nhận, và `Content-Type` để server mô tả representation thực tế được gửi trong response.

Versioning trong media type đặt thông tin phiên bản vào subtype hoặc parameter của media type. Ví dụ:

~~~http
Accept: application/hal+json;v=1
~~~

Client yêu cầu HAL JSON theo contract phiên bản 1. Server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json;v=1
~~~

Cùng URI có thể hỗ trợ nhiều phiên bản:

~~~http
GET /orders/42
Accept: application/hal+json;v=1
~~~

hoặc:

~~~http
GET /orders/42
Accept: application/hal+json;v=2
~~~

Server chọn representation V1 hoặc V2 dựa trên media type được chấp nhận. URI tài nguyên vẫn là `/orders/42`.

Điểm quan trọng là phiên bản được gắn với representation mà client muốn trao đổi, thay vì gắn trực tiếp vào path của resource.

## 2. Phân biệt Accept và Content-Type

Hai header này có vai trò khác nhau:

| Header | Hướng thông tin | Ý nghĩa |
|---|---|---|
| `Accept` | Client gửi lên | Các media type client muốn nhận trong response |
| `Content-Type` | Server trả về | Media type thực tế của response body |
| `Content-Type` | Client gửi lên | Media type của request body |

Với GET không có request body, `Accept` là tín hiệu chính để chọn phiên bản response.

Với POST hoặc PUT có body, client còn phải khai báo phiên bản của request representation bằng `Content-Type`. Server dùng `consumes` để quyết định handler nào có thể đọc body đó.

Ví dụ client gửi dữ liệu theo V1 nhưng muốn nhận response theo V2:

~~~http
POST /orders
Content-Type: application/hal+json;v=1
Accept: application/hal+json;v=2

{
  "customerId": 7,
  "total": 1250000
}
~~~

Request body và response body có thể dùng hai phiên bản khác nhau nếu API định nghĩa rõ phép chuyển đổi giữa chúng.

## 3. Hai cách biểu diễn version trong media type

Có hai cách thường gặp.

**Version parameter trên media type ổn định**

~~~text
application/hal+json;v=1
application/hal+json;v=2
~~~

Cả hai vẫn sử dụng định dạng HAL JSON. Parameter `v` do API định nghĩa để chỉ phiên bản contract.

Ưu điểm là giữ nguyên media type hypermedia quen thuộc và chỉ phân biệt phiên bản bằng parameter. Đây là lựa chọn phù hợp khi các phiên bản vẫn dùng cùng một format như HAL.

**Vendor-specific media type cho từng phiên bản**

~~~text
application/vnd.acme.order-v1+json
application/vnd.acme.order-v2+json
~~~

Mỗi phiên bản có một media type subtype riêng. Prefix `vnd.` thuộc vendor tree theo quy tắc đăng ký media type.

Cách này thể hiện rõ định danh riêng của representation. Tuy nhiên, hậu tố `+json` chỉ cho biết dữ liệu dùng cú pháp JSON. Nó không tự nói representation tuân theo HAL, HAL-FORMS hay một hypermedia format cụ thể.

Nếu muốn media type vendor-specific mang semantics HAL, ứng dụng cần cung cấp cấu hình serializer, deserializer và khả năng khám phá link phù hợp. Spring HATEOAS có SPI dành cho việc tích hợp media type hypermedia tùy chỉnh.

## 4. Khi nào nên dùng media type versioning?

Media type versioning phù hợp khi cùng một resource cần cung cấp nhiều representation contract cho các nhóm client khác nhau.

Ví dụ:

- Ứng dụng mobile cũ tiếp tục đọc representation V1.
- Ứng dụng web mới dùng representation V2.
- Một integration partner cần schema cũ trong giai đoạn chuyển đổi.
- API giữ nguyên URI nhưng thay đổi cấu trúc hoặc semantics của representation.

Ví dụ cùng resource:

| URI | Accept | Representation |
|---|---|---|
| `/orders/42` | `application/hal+json;v=1` | Order V1 |
| `/orders/42` | `application/hal+json;v=2` | Order V2 |

Không phải mọi thay đổi đều cần tăng version. Việc bổ sung một field tùy chọn mà client cũ có thể bỏ qua thường có thể tương thích ngược. Thay đổi kiểu dữ liệu, ý nghĩa field, quan hệ hypermedia hoặc cách client thực hiện workflow có thể là thay đổi phá vỡ contract.

Hãy định nghĩa chính sách tương thích của API trước khi quyết định lúc nào tạo version mới.

## 5. So sánh media type versioning với URI versioning

| Tiêu chí | Media type versioning | URI versioning |
|---|---|---|
| Ví dụ | `Accept: application/hal+json;v=2` | `/api/v2/orders/42` |
| URI resource | Có thể giữ nguyên | Thường có path version |
| Cách chọn version | Content negotiation | Đường dẫn |
| Khả năng cung cấp nhiều representation | Tự nhiên qua media type | Thường tách theo URI |
| Độ phức tạp client | Cần gửi đúng Accept | Cần biết URI phiên bản |
| Cache | Cần phân biệt theo Accept | Cache phân biệt theo URI |

Media type versioning giữ URI ổn định và biểu đạt rõ client muốn nhận representation nào. URI versioning dễ quan sát và dễ gọi từ công cụ đơn giản, nhưng làm version trở thành một phần của cấu trúc địa chỉ.

Không có lựa chọn phù hợp cho mọi API. Điều quan trọng là giữ chính sách nhất quán và công bố rõ trong contract.

## 6. Đặt version parameter trên HAL JSON

Ví dụ dưới đây định nghĩa hai media type parameter:

~~~java
import org.springframework.http.MediaType;

public final class OrderMediaTypes {

    public static final MediaType HAL_V1 =
        MediaType.parseMediaType("application/hal+json;v=1");

    public static final MediaType HAL_V2 =
        MediaType.parseMediaType("application/hal+json;v=2");

    private OrderMediaTypes() {
    }
}
~~~

Spring HATEOAS cung cấp sẵn các media type như `MediaTypes.HAL_JSON`, `MediaTypes.HAL_FORMS_JSON` và `MediaTypes.VND_HAL_JSON`. Các hằng số này xác định format hypermedia. Parameter phiên bản của ứng dụng được bổ sung vào media type phù hợp.

Dùng hằng số chung giúp controller, test và client configuration không tự khai báo chuỗi media type ở nhiều nơi.

## 7. Chọn phiên bản bằng produces trong Spring MVC

Thuộc tính `produces` giới hạn media type mà một handler có thể trả về. Spring MVC so khớp nó với media type trong `Accept`.

Có thể khai báo hai method cùng path nhưng phục vụ hai phiên bản:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;
    private final OrderV1Assembler v1Assembler;
    private final OrderV2Assembler v2Assembler;

    OrderController(
            OrderService orderService,
            OrderV1Assembler v1Assembler,
            OrderV2Assembler v2Assembler) {
        this.orderService = orderService;
        this.v1Assembler = v1Assembler;
        this.v2Assembler = v2Assembler;
    }

    @GetMapping(
        path = "/orders/{id}",
        produces = "application/hal+json;v=1"
    )
    EntityModel<OrderV1> getV1(@PathVariable Long id) {
        return v1Assembler.toModel(orderService.getById(id));
    }

    @GetMapping(
        path = "/orders/{id}",
        produces = "application/hal+json;v=2"
    )
    EntityModel<OrderV2> getV2(@PathVariable Long id) {
        return v2Assembler.toModel(orderService.getById(id));
    }
}
~~~

Hai handler dùng cùng URI và HTTP method. Giá trị parameter trong `Accept` giúp Spring chọn method tương ứng.

Assembler riêng giữ mapping từng version rõ ràng. Domain object có thể dùng chung, trong khi DTO và representation model thay đổi theo contract V1 hoặc V2.

### Chú ý khi client không gửi version parameter

Spring MVC có quy tắc matching parameter của media type: nếu mapping khai báo parameter nhưng request media type không có parameter đó, request có thể được xem là chấp nhận mọi giá trị của parameter. Vì vậy, không nên giả định `Accept: application/hal+json` tự động bị từ chối hoặc luôn chọn một version cụ thể.

API cần định nghĩa chính sách rõ ràng cho request không có version:

- Chọn một version mặc định và công bố điều đó.
- Yêu cầu client gửi version parameter và kiểm tra ở boundary.
- Dùng một endpoint bootstrap để client khám phá phiên bản hỗ trợ.

Nếu có nhiều handler cùng path chỉ khác parameter, hãy kiểm thử trường hợp thiếu parameter để tránh mapping mơ hồ hoặc chọn nhầm representation.

## 8. Chọn phiên bản request body bằng consumes

Với endpoint ghi dữ liệu, `consumes` có thể chọn handler dựa trên `Content-Type`.

~~~java
@PostMapping(
    path = "/orders",
    consumes = "application/hal+json;v=1",
    produces = "application/hal+json;v=1"
)
ResponseEntity<EntityModel<OrderV1>> createV1(
        @RequestBody CreateOrderV1 request) {

    Order created = orderService.create(
        request.customerId(),
        request.total()
    );

    EntityModel<OrderV1> model = v1Assembler.toModel(created);

    return ResponseEntity
        .created(model.getRequiredLink(IanaLinkRelations.SELF).toUri())
        .body(model);
}
~~~

Một handler khác có thể nhận request V2:

~~~java
@PostMapping(
    path = "/orders",
    consumes = "application/hal+json;v=2",
    produces = "application/hal+json;v=2"
)
void createV2(
        @RequestBody CreateOrderV2 request) {
    // Chuyển request V2 sang command nghiệp vụ.
}
~~~

Trong ví dụ, body V1 và V2 được bind vào hai kiểu request riêng. Service vẫn có thể dùng command/domain model chung nếu semantics nghiệp vụ tương đương.

Tương tự `produces`, hãy kiểm tra chính sách khi `Content-Type` thiếu version parameter. Nếu endpoint yêu cầu version tường minh, cần validation ở boundary và test cho request thiếu hoặc sai parameter.

## 9. Khác biệt giữa DTO version và domain model

Không nên biến version HTTP thành version của entity persistence.

Ví dụ:

~~~java
public record OrderV1(
    Long id,
    String status,
    long total
) {}
~~~

V2 có thể biểu diễn tiền tệ rõ hơn:

~~~java
public record OrderV2(
    Long id,
    OrderStatusView status,
    MoneyView amount
) {}

public record OrderStatusView(
    String code,
    String label
) {}

public record MoneyView(
    BigDecimal value,
    String currency
) {}
~~~

Domain model có thể vẫn lưu trạng thái đơn hàng và số tiền theo cùng một cấu trúc. Assembler chuyển domain model thành V1 hoặc V2.

Tách DTO theo version giúp:

- Không làm domain model phụ thuộc contract HTTP.
- Duy trì response cũ trong thời gian client chuyển đổi.
- Kiểm soát field và kiểu dữ liệu từng version.
- Viết test rõ ràng cho mỗi representation.

Không nên tạo hai domain entity riêng chỉ vì API có hai media type version.

## 10. Link hypermedia trong response theo version

Media type versioning thay đổi representation contract, nhưng link vẫn là thành phần quan trọng của response.

Ví dụ V1:

~~~json
{
  "id": 42,
  "status": "PAID",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/customers/7"
    }
  }
}
~~~

Ví dụ V2:

~~~json
{
  "id": 42,
  "status": {
    "code": "PAID",
    "label": "Đã thanh toán"
  },
  "amount": {
    "value": 1250000,
    "currency": "VND"
  },
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/customers/7"
    }
  }
}
~~~

Relation `self` và `customer` có thể giữ nguyên nếu semantics của chúng không thay đổi. Nếu một relation thay đổi ý nghĩa hoặc đích, cần đánh giá đó có phải breaking change và có cần relation mới hay version mới hay không.

Client phải tiếp tục gửi Accept version phù hợp khi theo link. Href không tự mang theo header Accept của request trước đó. Một hypermedia client nên lưu media type đã chọn và sử dụng nó nhất quán trong các request tiếp theo của workflow.

## 11. Công bố media type trong link

Link có thể mang thuộc tính `type` để gợi ý media type của tài nguyên đích. Ví dụ response có thể công bố:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/42",
      "type": "application/hal+json;v=2"
    }
  }
}
~~~

Thuộc tính `type` là metadata gợi ý về media type của đích. Client vẫn nên dùng `Accept` để thương lượng representation. Không nên xem thuộc tính `type` là cơ chế thay thế content negotiation hoặc bảo đảm server luôn trả đúng version mà client muốn.

Với Spring HATEOAS, có thể đặt metadata media type trên Link khi xây dựng representation:

~~~java
Link self = Link.of("/orders/42")
    .withSelfRel()
    .withType(OrderMediaTypes.HAL_V2.toString());

model.add(self);
~~~

## 12. Vendor-specific media type cho từng version

Nếu tổ chức muốn định danh mỗi contract bằng subtype riêng, có thể dùng:

~~~text
application/vnd.acme.order-v1+json
application/vnd.acme.order-v2+json
~~~

Client gửi:

~~~http
GET /orders/42
Accept: application/vnd.acme.order-v2+json
~~~

Server trả:

~~~http
Content-Type: application/vnd.acme.order-v2+json
~~~

Cách này tạo tên media type riêng cho mỗi contract. Nhưng có một khác biệt quan trọng: `application/vnd.acme.order-v2+json` không tự động là HAL JSON.

Nếu vendor media type chỉ là alias của HAL JSON, Spring HATEOAS cho phép đăng ký alias bằng `HalConfiguration.withMediaType`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.mediatype.hal.HalConfiguration;
import org.springframework.http.MediaType;

@Configuration
class OrderHalConfiguration {

    @Bean
    HalConfiguration halConfiguration() {
        return new HalConfiguration().withMediaType(
            MediaType.parseMediaType(
                "application/vnd.acme.order-v2+json"
            )
        );
    }
}
~~~

Cấu hình này khai báo media type bổ sung sẽ được serialize như HAL JSON. Nó phù hợp khi representation vẫn giữ đúng cấu trúc HAL.

Nếu vendor media type có cấu trúc hypermedia riêng, cần tích hợp SPI `HypermediaMappingInformation`. SPI cho phép khai báo media type, Jackson module/mapper customization và LinkDiscoverer để client tìm link relation.

Khung cấu hình cho một format riêng:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.HypermediaMappingInformation;
import org.springframework.http.MediaType;
import tools.jackson.databind.JacksonModule;

@Configuration
class AcmeOrderMediaTypeConfiguration
        implements HypermediaMappingInformation {

    @Override
    public List<MediaType> getMediaTypes() {
        return List.of(
            MediaType.parseMediaType(
                "application/vnd.acme.order-v2+json"
            )
        );
    }

    @Override
    public JacksonModule getJacksonModule() {
        return new AcmeOrderJacksonModule();
    }
}
~~~

`AcmeOrderJacksonModule` là module của ứng dụng, cần triển khai serializer/deserializer phù hợp với format mà API công bố. Ứng dụng cũng cần một LinkDiscoverer tương ứng nếu muốn dùng Spring HATEOAS client support để khám phá link trong format riêng.

Với Spring HATEOAS 3.1.x, `HypermediaMappingInformation` dùng Jackson 3 API. Nếu dự án dùng dòng Spring HATEOAS cũ hơn, chữ ký module/mapper có thể khác; hãy theo Javadoc đúng phiên bản dependency đang chạy.

Nếu chỉ cần cùng cấu trúc HAL và thêm version parameter, không cần tạo một hypermedia format vendor-specific mới chỉ để đổi số version.

## 13. Phân biệt version parameter với profile

Version và profile có thể xuất hiện cùng media type nhưng giải quyết vấn đề khác nhau.

- Version chỉ định phiên bản contract mà client và server đã thống nhất.
- Profile mô tả semantics hoặc quy ước bổ sung của representation.

Ví dụ media type version:

~~~http
Accept: application/hal+json;v=2
~~~

Một link profile có thể dẫn tới tài liệu semantics:

~~~json
{
  "_links": {
    "profile": {
      "href": "https://api.example.com/profiles/order"
    }
  }
}
~~~

Profile có thể giải thích ý nghĩa của status, amount hoặc relation customer. Nó không tự thay thế version negotiation nếu V1 và V2 có schema không tương thích.

Đừng dùng profile chỉ như một cách viết khác của version. Hãy định nghĩa vai trò từng metadata để client biết khi nào cần chọn representation khác và khi nào chỉ cần đọc thêm semantics.

## 14. Content negotiation với nhiều lựa chọn Accept

Client có thể gửi nhiều media type cùng chất lượng ưu tiên:

~~~http
Accept: application/hal+json;v=2;q=1.0,
        application/hal+json;v=1;q=0.7
~~~

Header này thể hiện client ưu tiên V2 nhưng vẫn có thể nhận V1 nếu V2 không có sẵn và server có chính sách chọn fallback phù hợp.

Quality value `q` là trọng số ưu tiên trong content negotiation. Server không nên tự suy đoán rằng mọi client có thể xử lý mọi version chỉ vì client gửi wildcard như `application/*` hoặc `*/*`.

Nếu version có ý nghĩa bắt buộc đối với contract, hãy yêu cầu client gửi version parameter tường minh và xác định rõ fallback. Không dùng wildcard làm cơ chế tự chọn version cho client cũ.

## 15. Xử lý version không được hỗ trợ

Nếu client yêu cầu media type version mà server không hỗ trợ, server nên trả lỗi content negotiation rõ ràng.

Ví dụ:

~~~http
GET /orders/42
Accept: application/hal+json;v=99
~~~

Nếu không có handler hoặc converter hỗ trợ version đó, Spring MVC thường trả:

~~~http
HTTP/1.1 406 Not Acceptable
~~~

Với request body:

~~~http
POST /orders
Content-Type: application/hal+json;v=99
~~~

Nếu server không nhận media type này, response thường là:

~~~http
HTTP/1.1 415 Unsupported Media Type
~~~

Hai status này khác nhau:

| Status | Ý nghĩa |
|---|---|
| `406 Not Acceptable` | Server không thể tạo representation phù hợp với Accept |
| `415 Unsupported Media Type` | Server không hỗ trợ định dạng request body được gửi lên |

Response lỗi nên chỉ rõ cách client có thể tiếp tục, ví dụ link tới tài liệu phiên bản được hỗ trợ hoặc thông tin về media type hiện hành.

## 16. Cache khi version được chọn bằng Accept

Nếu cùng URI trả V1 hoặc V2 tùy theo Accept, cache phải phân biệt các representation đó.

Ví dụ:

~~~http
GET /orders/42
Accept: application/hal+json;v=1
~~~

và:

~~~http
GET /orders/42
Accept: application/hal+json;v=2
~~~

Nếu shared cache chỉ dùng URI làm cache key mà không xét Accept, response V2 có thể được trả nhầm cho client V1.

Response cần chính sách cache phù hợp, thường bao gồm:

~~~http
Vary: Accept
~~~

`Vary: Accept` thông báo cache rằng representation có thể thay đổi theo header Accept. Nếu có thêm header khác ảnh hưởng response như tenant hoặc ngôn ngữ, cần thiết kế cache key và Vary policy tương ứng.

Với response cá nhân hóa theo quyền truy cập, hãy dùng cache policy private hoặc no-store tùy mức độ nhạy cảm. Không để cache chia sẻ representation của principal này cho principal khác.

## 17. Deprecation và chuyển client sang version mới

Khi V2 thay thế V1, không nên tắt V1 ngay nếu vẫn có client đang sử dụng.

Một lộ trình chuyển đổi thường gồm:

1. Công bố V2 và tài liệu migration.
2. Hỗ trợ V1 và V2 song song.
3. Đo lường số lượng request theo media type version.
4. Thông báo thời điểm ngừng hỗ trợ V1.
5. Gửi metadata deprecation phù hợp và cập nhật tài liệu.
6. Theo dõi client đã chuyển đổi.
7. Ngừng V1 theo chính sách đã công bố.

Có thể dùng header `Deprecation` để thông báo resource đã hoặc sẽ bị deprecate, và `Sunset` để thông báo thời điểm resource dự kiến ngừng phản hồi. Hai header này có semantics riêng trong RFC 9745 và RFC 8594; chúng hỗ trợ kế hoạch chuyển đổi nhưng không tự thay thế tài liệu migration. Đồng thời, API root hoặc tài liệu profile có thể công bố thông tin phiên bản được hỗ trợ.

Lưu ý RFC 9745 định nghĩa `Deprecation` theo resource được nhận diện bởi URI. Nếu V1 và V2 dùng cùng URI, header này không tự xác định phiên bản media type nào đang bị deprecate. Hãy công bố rõ quy ước áp dụng cho version trong tài liệu hoặc link deprecation chuyên biệt, tránh để client hiểu rằng toàn bộ resource đã ngừng hỗ trợ.

Không nên âm thầm đổi response V1 thành cấu trúc V2 chỉ vì server đã triển khai V2. Client gửi V1 cần tiếp tục nhận contract V1 trong thời gian hỗ trợ đã cam kết.

## 18. Kiểm thử media type versioning bằng MockMvc

Test cần xác nhận đúng handler được chọn và response khai báo đúng media type.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderVersionNegotiationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsV1WhenClientRequestsV1() throws Exception {
        MediaType v1 = MediaType.parseMediaType(
            "application/hal+json;v=1"
        );

        mockMvc.perform(
                get("/orders/42").accept(v1)
            )
            .andExpect(status().isOk())
            .andExpect(content().contentType(v1))
            .andExpect(jsonPath("$.total").value(1250000))
            .andExpect(jsonPath("$.amount").doesNotExist());
    }

    @Test
    void returnsV2WhenClientRequestsV2() throws Exception {
        MediaType v2 = MediaType.parseMediaType(
            "application/hal+json;v=2"
        );

        mockMvc.perform(
                get("/orders/42").accept(v2)
            )
            .andExpect(status().isOk())
            .andExpect(content().contentType(v2))
            .andExpect(jsonPath("$.amount.value").value(1250000))
            .andExpect(jsonPath("$.amount.currency").value("VND"));
    }
}
~~~

Trong test thực tế, cần mock service và import assembler tương ứng như các test MVC slice khác. Test phải xác nhận cả body và Content-Type, vì chỉ kiểm tra field không chứng minh content negotiation đã chọn đúng version.

Các test bổ sung nên có:

- Accept version không tồn tại trả 406.
- Request Content-Type không được hỗ trợ trả 415.
- Request thiếu version parameter tuân theo fallback policy đã công bố.
- Client V1 theo link vẫn gửi Accept V1 ở các hop tiếp theo.
- Cache response có Vary: Accept.
- POST V1 và POST V2 bind vào đúng request DTO.
- HAL-FORMS hoặc media type tùy chỉnh được serialize đúng nếu API hỗ trợ.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng Content-Type của response để yêu cầu version | Client gửi sai header | Dùng Accept để chọn response |
| Dùng Accept để mô tả request body | Server không biết body có format nào | Dùng Content-Type và consumes |
| Cho rằng +json đồng nghĩa HAL | Client không biết cấu trúc hypermedia | Đăng ký media type hypermedia và serializer phù hợp |
| Thay đổi DTO dùng chung cho V1 và V2 | Response cũ có thể đổi ngoài ý muốn | Dùng DTO/assembler theo version |
| Không định nghĩa hành vi khi thiếu version | Handler có thể chọn nhầm hoặc mapping mơ hồ | Quy định default hoặc bắt buộc parameter |
| Client chỉ gửi version ở request đầu | Các link tiếp theo có thể trả version khác | Gửi Accept nhất quán trong toàn workflow |
| Cache không xét Accept | V1 có thể nhận response V2 | Dùng Vary: Accept |
| Tạo version mới cho mọi thay đổi nhỏ | Tăng chi phí hỗ trợ | Chỉ tăng version khi thay đổi contract phá vỡ tương thích |
| Ẩn version trong tài liệu | Client khó biết cách yêu cầu representation | Công bố media type, schema và migration guide |
| Tắt version cũ đột ngột | Client hiện tại bị lỗi | Có deprecation window và theo dõi usage |

## 20. Quy trình thiết kế version trong media type

Khi triển khai versioning qua media type với Spring HATEOAS, hãy làm theo trình tự:

1. Xác định thay đổi nào thực sự phá vỡ contract.
2. Chọn cách biểu diễn version: media type parameter hay vendor-specific subtype.
3. Định nghĩa chính xác media type cho từng version.
4. Dùng `produces` để chọn response và `consumes` để chọn request body.
5. Tạo DTO và assembler riêng cho các representation không tương thích.
6. Giữ URI và link relation ổn định nếu semantics của chúng không đổi.
7. Yêu cầu client gửi Accept nhất quán khi đi theo link.
8. Định nghĩa fallback khi thiếu version và hành vi cho version không hỗ trợ.
9. Cấu hình cache phân biệt representation theo Accept.
10. Kiểm thử status, Content-Type, body, links, cache và migration.
11. Theo dõi client sử dụng từng version trước khi ngừng hỗ trợ version cũ.

Version trong media type giúp API cung cấp nhiều representation contract trên cùng URI. Spring MVC chọn handler thông qua content negotiation; Spring HATEOAS đảm nhiệm representation và hypermedia links. Khi version, media type, DTO và chính sách cache được định nghĩa rõ, server có thể duy trì client cũ trong khi giới thiệu representation mới một cách có kiểm soát.

## Tài liệu tham khảo

- [Spring Framework — Mapping Requests with produces and consumes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring HATEOAS Reference — Media types](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes)
- [Spring HATEOAS Reference — Registering a custom media type](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.registering-custom-media-type)
- [Spring HATEOAS API — HypermediaMappingInformation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/HypermediaMappingInformation.html)
- [Spring HATEOAS API — MediaTypes](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html)
- [Spring HATEOAS API — HalConfiguration](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/HalConfiguration.html)
- [Spring HATEOAS API — Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [RFC 9110 — HTTP Semantics, Content-Type and Accept](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 6838 — Media Type Specifications and Registration Procedures](https://www.rfc-editor.org/rfc/rfc6838.html)
- [RFC 9745 — The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html)
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html)
