# Version API có hypermedia

API thay đổi theo thời gian: thêm trường dữ liệu, thay quy tắc nghiệp vụ, đổi cấu trúc representation hoặc ngừng một thao tác cũ. Nếu client và server triển khai độc lập, một thay đổi không tương thích có thể làm client đang chạy bị lỗi. Versioning giúp công bố những hợp đồng API khác nhau trong giai đoạn chuyển đổi; hypermedia giúp client khám phá URI và khả năng của từng hợp đồng qua link relation.

Với Spring HATEOAS, versioning không chỉ là thêm `/v2` vào controller. Cần quyết định phần nào của hợp đồng được version, client tìm phiên bản mới bằng cách nào, các link trong từng representation dẫn tới đâu và phiên bản cũ sẽ được duy trì trong bao lâu. Một API root ổn định cùng link tới các phiên bản có thể giúp client chọn hợp đồng phù hợp mà không phải tự ghép URI.

## Version API và version representation

Một API có nhiều loại thay đổi. Không phải thay đổi nào cũng cần tạo phiên bản mới:

- **Thay đổi implementation:** đổi database, framework hoặc cách truy vấn nhưng giữ nguyên HTTP contract. Client không cần biết.
- **Thay đổi representation:** thêm/bớt field, đổi kiểu dữ liệu hoặc cấu trúc JSON.
- **Thay đổi hypermedia:** thêm relation, đổi target, thay URI template hoặc ngữ nghĩa capability.
- **Thay đổi hành vi:** thay quy tắc nghiệp vụ, validation, status code hoặc ý nghĩa của thao tác.

Version API là cách công bố một hợp đồng có thể được nhận diện và lựa chọn. Phiên bản có thể áp dụng cho toàn bộ API, một nhóm tài nguyên hoặc một representation cụ thể. Nên định nghĩa rõ phạm vi version trước khi chọn cơ chế.

Ví dụ, phiên bản 1 trả `fullName`:

```json
{
  "id": "ORD-1001",
  "customer": {
    "fullName": "Nguyen An"
  }
}
```

Phiên bản 2 tách tên khách hàng thành hai trường:

```json
{
  "id": "ORD-1001",
  "customer": {
    "firstName": "An",
    "lastName": "Nguyen"
  }
}
```

Client phiên bản 1 có thể không hiểu representation mới nếu nó yêu cầu `fullName`. Hai representation cần được phân biệt hoặc thay đổi theo cách tương thích có chủ đích.

## Những chiến lược versioning phổ biến

Có bốn cách thường gặp để client yêu cầu một phiên bản:

| Chiến lược | Ví dụ | Ưu điểm | Hạn chế |
|---|---|---|---|
| URI path | `/api/v1/orders` | Dễ đọc, dễ route, dễ quan sát và cache | Version xuất hiện trong URI; có thể nhân đôi mapping |
| Media type | `Accept: application/vnd.acme.order-v2+json` | URI tài nguyên có thể ổn định; version gắn với representation | Cần cấu hình content negotiation và converter phù hợp |
| Header riêng | `API-Version: 2` | URI gọn, version tách khỏi body | Khó quan sát hơn; cache phải xét header; client phải biết header |
| Query parameter | `/api/orders?api-version=2` | Dễ thử nghiệm và tương thích với một số gateway | Version thành một phần query; dễ bị bỏ quên khi theo link |

Không có chiến lược duy nhất phù hợp mọi hệ thống. Với API công khai, URI versioning thường dễ vận hành và kiểm tra nhất. Media type versioning hữu ích khi cùng một resource URI có nhiều representation. Dù chọn cách nào, API nên công bố version qua entry point và link thay vì bắt client tự suy ra mọi endpoint.

### URI path versioning

Mỗi phiên bản có namespace URI riêng:

```text
/api/v1/orders
/api/v2/orders
```

Server có thể triển khai hai controller song song. Các link bên trong representation v1 tiếp tục dẫn tới resource v1; representation v2 dẫn tới resource v2. Điều này giúp client không vô tình chuyển từ hợp đồng cũ sang hợp đồng mới giữa một workflow.

### Media type versioning

Client yêu cầu representation bằng header `Accept`:

```http
GET /api/orders/ORD-1001 HTTP/1.1
Accept: application/vnd.acme.order-v2+json
```

Server trả `Content-Type` tương ứng:

```http
HTTP/1.1 200 OK
Content-Type: application/vnd.acme.order-v2+json
Vary: Accept
```

`Vary: Accept` quan trọng khi cùng URI có thể trả nhiều representation. Cache trung gian cần biết response phụ thuộc vào `Accept` để không dùng nhầm representation của client khác.

Với Spring HATEOAS, một vendor media type không tự động trở thành HAL chỉ vì tên có hậu tố `+json`. Nếu muốn serialize `EntityModel`, `_links` và `_embedded` theo một hypermedia format tùy chỉnh, cần đăng ký hỗ trợ media type và mapping tương ứng trong Spring HATEOAS. Chỉ khai báo `produces` không tự cung cấp một hypermedia converter mới. Có thể dùng HAL JSON chuẩn cho cả hai version trong khi phân biệt version bằng URI path, hoặc xây dựng `HypermediaMappingInformation` khi thực sự cần một media type hypermedia riêng.

### Header versioning

Client gửi một header đã được thống nhất:

```http
GET /api/orders/ORD-1001 HTTP/1.1
API-Version: 2
Accept: application/hal+json
```

Header riêng cần được đưa vào chính sách cache (`Vary: API-Version`) và tài liệu API. Không dùng một header tùy ý mà không định nghĩa rõ giá trị mặc định, phiên bản không hợp lệ và cách xử lý khi client bỏ header.

### Query parameter versioning

Client yêu cầu version bằng query parameter:

```http
GET /api/orders/ORD-1001?api-version=2
Accept: application/hal+json
```

Nếu link được server công bố chứa version parameter, client có thể theo link mà không tự thêm tham số. Tuy nhiên, query parameter có thể bị lược khi client tự tạo URL hoặc khi một link khác không giữ query context. Vì vậy, cần bảo đảm mọi link trong workflow đều duy trì version.

## Hypermedia giúp client khám phá phiên bản

Một API có thể giữ entry point ổn định và công bố link tới các phiên bản đang hỗ trợ. Ví dụ root HAL:

```json
{
  "_links": {
    "self": {
      "href": "https://api.acme.example/api"
    },
    "orders": {
      "href": "https://api.acme.example/api/v2/orders",
      "type": "application/hal+json"
    },
    "https://api.acme.example/rels/orders-v1": {
      "href": "https://api.acme.example/api/v1/orders",
      "type": "application/hal+json"
    },
    "version-history": {
      "href": "https://api.acme.example/api/version-history"
    },
    "profile": {
      "href": "https://api.acme.example/profiles/order-api"
    }
  }
}
```

Trong ví dụ, `orders` trỏ tới phiên bản mặc định hiện hành; URI relation `https://api.acme.example/rels/orders-v1` cho phép client còn cần hợp đồng cũ chọn collection v1. `version-history` dẫn tới tài liệu hoặc tài nguyên mô tả các phiên bản. Nếu rút gọn URI relation bằng CURIE, công bố mapping qua link `curies`.

Một lựa chọn khác là công bố nhiều link cùng relation `orders`, mỗi link có `type` hoặc profile khác nhau. Cần lưu ý HAL có thể serialize nhiều link cùng relation thành array. Client phải xử lý đúng cấu trúc đó và chọn link theo khả năng hỗ trợ. Tránh giả định relation luôn chỉ có một link.

### Dùng các relation versioning đã đăng ký

IANA Link Relation Registry có các relation phục vụ điều hướng phiên bản như:

- `version-history`: dẫn tới tài nguyên mô tả lịch sử phiên bản.
- `latest-version`: dẫn tới phiên bản mới nhất của tài nguyên.
- `predecessor-version`: dẫn tới phiên bản trước.
- `successor-version`: dẫn tới phiên bản kế tiếp.

Các relation này mô tả quan hệ giữa tài nguyên và phiên bản của nó. Chúng không tự quy định cách server triển khai versioning hoặc cách client chọn version. Hãy dùng đúng relation theo ngữ nghĩa; không dùng `latest-version` nếu link chỉ là phiên bản mặc định cho một nhóm client.

Ví dụ representation của tài nguyên v1 có thể công bố link tới phiên bản kế tiếp:

```json
{
  "id": "ORD-1001",
  "status": "OPEN",
  "_links": {
    "self": {
      "href": "/api/v1/orders/ORD-1001"
    },
    "successor-version": {
      "href": "/api/v2/orders/ORD-1001",
      "type": "application/hal+json"
    },
    "version-history": {
      "href": "/api/orders/ORD-1001/versions"
    }
  }
}
```

Client v1 có thể hiển thị khả năng nâng cấp khi phù hợp. Nó không bắt buộc phải theo link successor ngay lập tức; quyết định nâng cấp phụ thuộc khả năng hỗ trợ của client và chính sách triển khai.

## Tạo các versioned endpoint trong Spring MVC

Với URI versioning, có thể tạo controller riêng cho mỗi version. Ví dụ v1 và v2 có DTO khác nhau:

```java
import java.util.UUID;

public record OrderV1Response(
        UUID id,
        String status,
        String customerName
) {}

public record OrderV2Response(
        UUID id,
        String status,
        CustomerName customer
) {}

public record CustomerName(
        String firstName,
        String lastName
) {}
```

Controller v1:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(path = "/api/v1/orders", produces = MediaTypes.HAL_JSON_VALUE)
public class OrderV1Controller {

    private final OrderService service;
    private final OrderV1Assembler assembler;

    public OrderV1Controller(OrderService service, OrderV1Assembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderV1Response> one(@PathVariable UUID id) {
        return assembler.toModel(service.findRequired(id));
    }
}
```

Controller v2:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(path = "/api/v2/orders", produces = MediaTypes.HAL_JSON_VALUE)
public class OrderV2Controller {

    private final OrderService service;
    private final OrderV2Assembler assembler;

    public OrderV2Controller(OrderService service, OrderV2Assembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderV2Response> one(@PathVariable UUID id) {
        return assembler.toModel(service.findRequired(id));
    }
}
```

Hai controller dùng chung domain service nhưng có DTO và assembler riêng. Đây là cách tránh để persistence entity trở thành hợp đồng công khai. Khi thay đổi cấu trúc v2, không cần sửa DTO v1 nếu vẫn phải duy trì client cũ.

### Tạo link theo đúng version

Assembler v1 cần tạo `self` và link nghiệp vụ trong namespace v1:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderV1Assembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderV1Response>> {

    @Override
    public EntityModel<OrderV1Response> toModel(Order order) {
        var id = order.getId();
        Link self = linkTo(methodOn(OrderV1Controller.class).one(id))
                .withSelfRel();

        OrderV1Response body = new OrderV1Response(
                id, order.getStatus().name(), order.getCustomer().getFullName());

        return EntityModel.of(body, self);
    }
}
```

Assembler v2 tạo link trong namespace v2:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderV2Assembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderV2Response>> {

    @Override
    public EntityModel<OrderV2Response> toModel(Order order) {
        var id = order.getId();
        Link self = linkTo(methodOn(OrderV2Controller.class).one(id))
                .withSelfRel();

        CustomerName customer = new CustomerName(
                order.getCustomer().getFirstName(),
                order.getCustomer().getLastName());

        return EntityModel.of(
                new OrderV2Response(id, order.getStatus().name(), customer),
                self);
    }
}
```

Điểm quan trọng là các link trong representation v1 tiếp tục dẫn tới endpoint v1. Nếu assembler v1 tạo link tới controller v2, client có thể nhận representation v2 giữa workflow dù nó chỉ hiểu v1.

## Tạo API root cho các phiên bản

Root controller có thể công bố phiên bản mặc định và lịch sử version:

```java
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class VersionedApiRootController {

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public RepresentationModel<?> root() {
        RepresentationModel<?> model = new RepresentationModel<>();

        model.add(Link.of("/api", "self"));
        model.add(Link.of("/api/v2/orders", "orders"));
        model.add(Link.of(
                "/api/v1/orders",
                LinkRelation.of("https://api.acme.example/rels/orders-v1")
        ));
        model.add(Link.of("/api/version-history", "version-history"));

        return model;
    }
}
```

Ví dụ dùng extension relation URI cho collection v1 để tránh tạo nhiều link cùng relation `orders`. Nếu muốn dùng vocabulary chuẩn, có thể công bố `latest-version` hoặc `version-history` đúng ngữ nghĩa. Root cần được duy trì ổn định để client có thể bắt đầu từ một URI đã biết.

Với link tới tài nguyên cụ thể, `WebMvcLinkBuilder` tạo URI theo mapping controller. Root trên dùng path literal để minh họa hai version; trong ứng dụng thực tế, có thể dùng link builder để tránh lặp path và cấu hình base path.

## Media type versioning và content negotiation trong Spring MVC

Nếu một URI phải trả nhiều representation theo `Accept`, Spring MVC có thể chọn handler qua điều kiện `produces`. Ví dụ ở mức controller:

```java
@GetMapping(
        value = "/api/orders/{id}",
        produces = "application/vnd.acme.order-v1+json"
)
public OrderV1Response oneV1(@PathVariable UUID id) {
    return service.findRequired(id).toV1Response();
}

@GetMapping(
        value = "/api/orders/{id}",
        produces = "application/vnd.acme.order-v2+json"
)
public OrderV2Response oneV2(@PathVariable UUID id) {
    return service.findRequired(id).toV2Response();
}
```

Đây là ví dụ content negotiation cho DTO JSON. Để trả HAL representation với media type vendor riêng, cần thêm cấu hình hỗ trợ hypermedia media type tương ứng; không nên giả định `HalJacksonHttpMessageConverter` mặc định xử lý mọi `application/*+json` theo cấu trúc HAL.

Nếu hai version dùng cùng `application/hal+json` và chỉ khác payload, có thể dùng URI path versioning thay vì tự tạo vendor media type. Nếu version khác nhau chủ yếu ở profile ngữ nghĩa, có thể công bố profile link hoặc profile parameter theo hợp đồng được client hỗ trợ. `profile` giúp định danh semantics của representation nhưng không thay thế hoàn toàn chính sách versioning.

## Dùng Link type và profile để mô tả representation

Thuộc tính `type` trong link là gợi ý về media type của tài nguyên đích. Nó giúp client nhận biết dạng representation dự kiến:

```java
Link v2Orders = Link.of("/api/v2/orders", "orders")
        .withType(MediaTypes.HAL_JSON_VALUE);
```

`type` không phải cơ chế route hay kiểm soát quyền. Server vẫn phải xử lý `Accept` và trả `Content-Type` phù hợp. Nếu một URI có thể trả nhiều media type, giá trị `type` trong link chỉ là hint; client có thể yêu cầu media type bằng `Accept`.

Relation `profile` có thể dẫn tới tài liệu mô tả schema, semantics hoặc các quy tắc của representation:

```java
Link profile = Link.of(
        "https://api.acme.example/profiles/orders-v2",
        "profile");
```

Profile hữu ích để giải thích các field hoặc semantics của v2. Client không nên coi việc có profile link đồng nghĩa với việc tự động hiểu được mọi thay đổi; profile chỉ có giá trị khi tài liệu mô tả rõ contract.

## Giữ link relation ổn định qua các phiên bản

Link relation mô tả ý nghĩa của quan hệ, còn `href` xác định URI đích. Hai phần này nên được quản lý riêng:

| Thành phần | Có nên đổi khi tạo v2? | Lý do |
|---|---|---|
| `self` | URI đích thường đổi theo namespace version | Resource v2 có URI riêng |
| Relation `orders` | Giữ nếu vẫn là collection đơn hàng | Semantics không thay đổi |
| Relation `cancel` | Giữ nếu vẫn mô tả cùng capability | Client có thể tái sử dụng workflow |
| Relation tùy chỉnh | Chỉ đổi nếu semantics thực sự đổi | Không dùng version number chỉ để phân biệt payload |
| `href` | Có thể đổi theo route mới | Client phải theo link server công bố |
| `type` | Cập nhật khi media type representation đổi | Client cần biết định dạng đích |

Nếu hành động `approve` ở v2 mang ý nghĩa khác với v1, không nên giữ cùng relation chỉ vì tên giống nhau. Hãy định nghĩa relation mới hoặc profile mới để client không hiểu sai semantics. Ngược lại, nếu hành động vẫn cùng ý nghĩa, giữ relation ổn định giúp client ít phụ thuộc version hơn.

Một thiết kế tốt thường giữ các relation chung như `self`, `collection`, `next`, `prev`, `search` ổn định và chỉ thay đổi link target hoặc representation khi cần. Không nhúng version vào mọi relation một cách máy móc.

## Thay đổi tương thích và thay đổi phá vỡ tương thích

Version mới nên được tạo khi thay đổi có thể làm client hiện tại không hoạt động đúng. Bảng sau là hướng dẫn thực tế; mức độ tương thích còn phụ thuộc cách client parse và contract cụ thể:

| Thay đổi | Thường tương thích? | Ghi chú |
|---|---|---|
| Thêm field tùy chọn | Có, với tolerant reader | Client không được từ chối field lạ |
| Thêm link relation mới | Có | Client cũ có thể bỏ qua relation chưa biết |
| Thêm query parameter tùy chọn | Có | Server phải giữ default cũ |
| Đổi tên hoặc xóa field | Không | Client đang đọc field cũ có thể lỗi |
| Đổi kiểu field | Không | Ví dụ string thành object |
| Đổi semantics của relation | Không | Client có thể thực hiện sai hành động |
| Xóa link mà client đang cần | Có thể không | Phụ thuộc workflow và capability contract |
| Đổi default hoặc validation | Có thể không | Hành vi thay đổi dù schema không đổi |
| Đổi status code hoặc error body | Có thể không | Client có thể xử lý lỗi khác đi |

Tư duy tolerant reader giúp client bỏ qua field hoặc relation chưa biết. Tuy nhiên, tolerant reader không thể khắc phục việc server đổi semantics của field đã tồn tại hoặc xóa khả năng mà workflow yêu cầu.

## Deprecation và Sunset cho phiên bản cũ

Khi có v2, không nhất thiết phải ngừng v1 ngay. Một giai đoạn chuyển tiếp rõ ràng giúp client có thời gian nâng cấp:

1. Công bố v2 và tài liệu migration.
2. Giữ v1 hoạt động trong khoảng thời gian đã thông báo.
3. Đánh dấu v1 deprecated và công bố thời điểm dự kiến ngừng phục vụ.
4. Theo dõi traffic, client version và lỗi migration.
5. Ngừng v1 sau khi hết thời gian hỗ trợ và đã thông báo theo chính sách.

HTTP có các header liên quan:

- `Deprecation`: chỉ ra resource hoặc API đã bị đánh dấu deprecated.
- `Sunset`: cho biết thời điểm resource dự kiến không còn khả dụng.
- `Link` với relation `deprecation`: dẫn tới tài liệu giải thích lý do và hướng migration.

Ví dụ response cho endpoint v1:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Deprecation: @1796083200
Sunset: Thu, 31 Dec 2026 23:59:59 GMT
Link: <https://api.acme.example/migrations/orders-v1-to-v2>; rel="deprecation"
```

Giá trị `Deprecation` ở ví dụ là thời điểm dạng Structured Field date theo RFC 9745; khi triển khai, phải dùng thời điểm thật của chính sách phát hành. `Sunset` dùng HTTP-date theo RFC 8594. Header thông báo không thay thế tài liệu migration hoặc thông báo trực tiếp tới người vận hành client.

Trong Spring MVC, có thể gắn header vào response v1:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;

class OrderV1LifecycleHeaders {

    private static final String DEPRECATION_DATE = "@1796083200";
    private static final String SUNSET_DATE = "Thu, 31 Dec 2026 23:59:59 GMT";

    ResponseEntity<EntityModel<OrderV1Response>> addHeaders(
            EntityModel<OrderV1Response> body
    ) {
        return ResponseEntity.ok()
                .header("Deprecation", DEPRECATION_DATE)
                .header("Sunset", SUNSET_DATE)
                .header(HttpHeaders.LINK,
                        "<https://api.acme.example/migrations/orders-v1-to-v2>; rel=\"deprecation\"")
                .body(body);
    }
}
```

Đoạn code chỉ minh họa cách gắn header; trong ứng dụng thực tế, đọc ngày deprecation và sunset từ cấu hình triển khai để tránh hard-code thời điểm trong controller. Nếu v1 chưa có lịch ngừng phục vụ, không gửi `Sunset` giả.

## Kiểm thử versioning bằng MockMvc

Test cần xác nhận mỗi version trả đúng representation, link và media type đã công bố. Với URI versioning:

```java
import static org.hamcrest.Matchers.containsString;
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
class OrderVersioningTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void v1KeepsLegacyRepresentationAndLinks() throws Exception {
        mockMvc.perform(get("/api/v1/orders/ORD-1001")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.customerName").exists())
            .andExpect(jsonPath("$._links.self.href")
                    .value(containsString("/api/v1/orders/")));
    }

    @Test
    void v2ReturnsNewRepresentationAndVersionedSelfLink() throws Exception {
        mockMvc.perform(get("/api/v2/orders/ORD-1001")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.customer.firstName").exists())
            .andExpect(jsonPath("$.customer.lastName").exists())
            .andExpect(jsonPath("$._links.self.href")
                    .value(containsString("/api/v2/orders/")));
    }
}
```

Trong test class cần import `containsString` từ `org.hamcrest.Matchers`. Dữ liệu `ORD-1001` phải được tạo bởi fixture hoặc test database trước khi chạy.

Kiểm tra root công bố version links:

```java
mockMvc.perform(get("/api").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.orders.href")
            .value(containsString("/api/v2/orders")))
    .andExpect(jsonPath("$._links['https://api.acme.example/rels/orders-v1'].href")
            .value(containsString("/api/v1/orders")))
    .andExpect(jsonPath("$._links.version-history.href").exists());
```

Với media type versioning, test hai `Accept` khác nhau và xác nhận `Content-Type` cũng như body. Với header hoặc query parameter versioning, test cả trường hợp có version, không có version và version không được hỗ trợ. Nếu cùng URI trả nhiều representation theo header, kiểm tra `Vary` để cache không trộn response.

Kiểm thử deprecation:

```java
mockMvc.perform(get("/api/v1/orders/ORD-1001")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(header().exists("Deprecation"))
    .andExpect(header().exists("Sunset"))
    .andExpect(header().string("Link", containsString("rel=\"deprecation\"")));
```

Test này cần import `header` từ `MockMvcResultMatchers` và `containsString` từ Hamcrest. Chỉ assert `Sunset` nếu server đã công bố thời điểm ngừng phục vụ.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ đổi DTO nhưng không đổi version contract | Client không biết representation nào đang được trả | Công bố version qua URI, media type hoặc cơ chế đã chọn |
| Trộn link v1 với endpoint v2 | Client cũ bị chuyển sang contract không tương thích | Giữ link trong từng representation ở đúng version |
| Version hóa mọi relation | Client mất khả năng tái sử dụng relation chung | Giữ relation nếu semantics không đổi |
| Đổi semantics nhưng giữ relation cũ | Client có thể thực hiện sai hành động | Tạo relation/profile mới khi ý nghĩa thay đổi |
| Nghĩ `produces` tự đăng ký vendor HAL converter | Có thể gặp 406 hoặc JSON không theo HAL | Đăng ký hypermedia mapping/converter tương ứng |
| Media type versioning nhưng quên `Vary: Accept` | Cache có thể trả nhầm representation | Thêm `Vary: Accept` |
| Header versioning nhưng không xét cache | Cache có thể bỏ qua version header | Thêm header vào `Vary` và cấu hình cache |
| Thay đổi v1 trực tiếp khi v2 ra mắt | Client cũ bị phá vỡ bất ngờ | Duy trì song song và có thời gian chuyển tiếp |
| Công bố `Sunset` không có kế hoạch thực tế | Client mất niềm tin vào thông báo | Chỉ công bố lịch đã được phê duyệt và có thể thực hiện |
| Chỉ thêm link successor mà không có migration guide | Client không biết cách xử lý thay đổi payload | Cung cấp profile, tài liệu migration và ví dụ |

## Quy trình thiết kế version API có hypermedia

1. Xác định thay đổi có thực sự phá vỡ contract hiện tại hay có thể triển khai theo hướng tương thích.
2. Chọn phạm vi version: toàn API, nhóm resource hay representation.
3. Chọn cơ chế versioning và quy định giá trị mặc định.
4. Duy trì API root ổn định, công bố link tới version hiện hành và lịch sử phiên bản.
5. Tạo DTO, assembler và controller riêng khi representation khác nhau đáng kể.
6. Bảo đảm link trong representation v1 tiếp tục dẫn tới tài nguyên v1; link v2 dẫn tới tài nguyên v2.
7. Giữ relation ổn định khi semantics không đổi; định nghĩa relation mới khi semantics thay đổi.
8. Dùng `type`, profile và version-history links để mô tả representation khi hữu ích.
9. Công bố deprecation, migration guide và sunset date theo chính sách rõ ràng.
10. Kiểm thử representation, relation, href, media type, cache headers và vòng đời version bằng MockMvc.

## Kết luận

Versioning giúp nhiều thế hệ client cùng sử dụng API trong giai đoạn chuyển đổi. Spring HATEOAS bổ sung khả năng khám phá: API root công bố các version resource, representation chứa link đúng namespace và relation mô tả ngữ nghĩa ổn định. URI path là lựa chọn đơn giản để triển khai song song; media type, header và query parameter có thể phù hợp khi cần thương lượng representation hoặc tích hợp với gateway. Dù chọn cách nào, hãy giữ link và relation nhất quán, tách DTO theo contract, quản lý cache đúng và thông báo deprecation/sunset đủ sớm. Client khi đó có thể chọn version được hỗ trợ và tiếp tục điều hướng qua hypermedia thay vì phụ thuộc vào các URI tự ghép.

## Tài liệu tham khảo

- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html): mô hình link, relation type và target.
- [RFC 5829 – Link Relation Types for Simple Version Navigation between Web Resources](https://www.rfc-editor.org/rfc/rfc5829.html): `version-history`, `latest-version`, `predecessor-version`, `successor-version` và các relation liên quan.
- [RFC 6906 – The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906.html): mô tả profile của representation.
- [RFC 9745 – The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html): thông báo resource/API bị deprecated.
- [RFC 8594 – The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html): công bố thời điểm resource dự kiến ngừng phục vụ.
- [Spring Framework – Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): cấu hình mapping và điều kiện `produces`/`consumes`.
- [Spring HATEOAS Reference](https://docs.spring.io/spring-hateoas/docs/current/reference/html/): RepresentationModel, Link, hypermedia media type và cấu hình Spring HATEOAS.
