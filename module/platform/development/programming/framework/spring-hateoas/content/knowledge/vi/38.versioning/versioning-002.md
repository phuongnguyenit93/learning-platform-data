# Version trong URI

Version trong URI (URI path versioning) là cách đưa phiên bản hợp đồng API vào đường dẫn tài nguyên, thường bằng một segment như /api/v1 hoặc /api/v2. Client chọn phiên bản bằng URI mà nó gọi; server định tuyến request đến controller và representation tương ứng. Cách này dễ quan sát trong log, browser, gateway, tài liệu và cache vì phiên bản xuất hiện trực tiếp trong request target.

Trong REST API dùng Spring HATEOAS, version trong URI cần được áp dụng nhất quán cho toàn bộ link mà server công bố. Nếu client đang dùng phiên bản v1, self link, collection link, pagination link và action link của representation đó cần tiếp tục trỏ vào namespace v1. Spring HATEOAS hỗ trợ việc này qua link builder dựa trên mapping của controller, giúp link được tạo theo đúng phiên bản endpoint.

## Vì sao đưa version vào URI?

Giả sử API đơn hàng đang có hợp đồng v1:

~~~http
GET /api/v1/orders/o-42 HTTP/1.1
Host: shop.example
Accept: application/hal+json
~~~

Sau một thời gian, API cần thay đổi cấu trúc representation theo cách không tương thích. Server có thể cung cấp v2 song song:

~~~http
GET /api/v2/orders/o-42 HTTP/1.1
Host: shop.example
Accept: application/hal+json
~~~

Hai URI cùng đại diện cho một đơn hàng nghiệp vụ nhưng công bố hai hợp đồng representation khác nhau. Client cũ tiếp tục dùng /api/v1; client đã nâng cấp chuyển sang /api/v2.

Một response v1 có thể là:

~~~json
{
  "id": "o-42",
  "status": "PAID",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://shop.example/api/v1/orders/o-42"
    },
    "collection": {
      "href": "https://shop.example/api/v1/orders"
    }
  }
}
~~~

Representation v2 có thể thay đổi cấu trúc theo hợp đồng mới:

~~~json
{
  "id": "o-42",
  "state": "PAID",
  "amount": {
    "value": 125000,
    "currency": "VND"
  },
  "_links": {
    "self": {
      "href": "https://shop.example/api/v2/orders/o-42"
    },
    "collection": {
      "href": "https://shop.example/api/v2/orders"
    }
  }
}
~~~

Trong ví dụ, v2 đổi tên status thành state và nhóm giá trị tiền vào amount. Client phụ thuộc cấu trúc v1 không bị buộc phải hiểu representation mới ngay lập tức.

## URI versioning phù hợp khi nào?

Đưa major version vào URI thường phù hợp khi:

- Có thay đổi breaking về request hoặc response.
- Nhiều nhóm client cần được nâng cấp theo lịch khác nhau.
- Gateway, proxy hoặc routing cần phân biệt rõ các hợp đồng.
- Muốn quan sát traffic theo phiên bản qua access log và metrics.
- Cần giữ hai hợp đồng công khai cùng tồn tại trong giai đoạn migration.

Không cần tăng version chỉ vì thêm một field tùy chọn, thêm link relation mới hoặc thêm affordance mà client cũ có thể bỏ qua. Những thay đổi additive nên được cân nhắc trước để tránh tạo quá nhiều phiên bản cần bảo trì.

Version trong URI là một lựa chọn thiết kế, không phải yêu cầu bắt buộc của REST. Nó đặc biệt thực dụng khi tổ chức muốn chọn phiên bản rõ ràng ở tầng routing và vận hành.

## Phân biệt API version với version của dữ liệu

Từ version có thể chỉ nhiều khái niệm khác nhau:

| Loại version | Ví dụ | Mục đích |
| --- | --- | --- |
| API version | /api/v2/orders/o-42 | Chọn hợp đồng HTTP và representation. |
| Resource revision | ETag "order-o-42-r17" | Nhận diện một revision cụ thể của resource để cache hoặc kiểm tra cập nhật. |
| Database optimistic-lock version | Trường @Version trong entity | Phát hiện cập nhật đồng thời ở persistence layer. |
| Application release | shop-service 3.8.1 | Phiên bản triển khai phần mềm server. |

Các khái niệm này không thay thế nhau. /api/v2 không có nghĩa database entity phải có version bằng 2. Một API v1 và v2 có thể cùng đọc một domain model và cùng truy cập dữ liệu nghiệp vụ. Ngược lại, một order có thể thay đổi revision nhiều lần trong khi vẫn được truy cập qua /api/v2/orders/o-42.

## Lựa chọn phạm vi version

Thông thường nên version hóa hợp đồng lớn ở cấp API, chẳng hạn /api/v1 và /api/v2, rồi đặt các resource bên dưới namespace đó:

~~~text
/api/v1
  /orders
  /orders/{id}
  /customers
  /customers/{id}

/api/v2
  /orders
  /orders/{id}
  /customers
  /customers/{id}
~~~

Cách tổ chức này giúp các resource có cùng một chính sách version và link traversal không vô tình trộn lẫn hợp đồng. Nếu chỉ một nhóm tài nguyên cần thay đổi độc lập, tổ chức có thể chọn phạm vi version hẹp hơn, nhưng phải tài liệu hóa cách các resource liên kết qua ranh giới đó.

Tránh tạo URI như /api/v1/orders-v2/{id} hoặc version riêng lẻ cho từng field. Cấu trúc như vậy làm client khó hiểu một representation thuộc hợp đồng nào.

## Version trong URI và các cách versioning khác

Có nhiều cách để client chọn hợp đồng:

| Cách | Ví dụ | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| URI path | /api/v2/orders | Dễ quan sát, routing và cache key rõ ràng. | Version trở thành một phần URI resource; phải duy trì các route cũ. |
| Media type | Accept: application/vnd.shop.order-v2+json | URI có thể giữ nguyên, version chọn qua content negotiation. | Cần cấu hình converter, tài liệu và tooling rõ ràng. |
| Custom header | API-Version: 2 | Version tách khỏi URI. | Khó nhìn thấy khi debug URL; cache cần xét header qua Vary. |
| Query parameter | /orders?version=2 | Dễ thử nghiệm. | Dễ bị bỏ sót khi tạo link và không phải lựa chọn tốt cho hợp đồng dài hạn. |

Bài này tập trung vào URI path versioning. Không nên đồng thời mã hóa cùng một major version trong path, media type và custom header nếu không có lý do rõ ràng; nhiều nguồn version có thể mâu thuẫn. Khi version nằm trong path, Accept: application/hal+json vẫn dùng để chọn định dạng hypermedia, không cần biến media type thành một nguồn version thứ hai.

## Ánh xạ version bằng Spring MVC

Spring MVC có thể định tuyến phiên bản qua class-level @RequestMapping. Mỗi version có controller riêng và một base path rõ ràng:

| Controller | Mapping ở cấp lớp | Ví dụ item URI |
| --- | --- | --- |
| OrderV1Controller | /api/v1/orders | /api/v1/orders/o-42 |
| OrderV2Controller | /api/v2/orders | /api/v2/orders/o-42 |

Ví dụ controller v1 hoàn chỉnh ở phần sau dùng mapping /api/v1/orders. Controller v2 áp dụng cùng cấu trúc với base path /api/v2/orders và trả DTO/representation v2. Hai controller có thể gọi cùng application service nhưng chuyển domain object sang DTO khác nhau.

Spring MVC chọn controller dựa trên path. Request đến /api/v1/orders/o-42 không tự chuyển sang v2 chỉ vì server đã triển khai v2. Client chọn phiên bản bằng URI mà nó sử dụng.

## Giữ domain service dùng chung, tách representation theo version

Không nên nhân đôi toàn bộ nghiệp vụ chỉ vì có hai API version. Có thể dùng chung query/command service và giữ DTO, assembler, controller riêng cho từng hợp đồng:

~~~text
                 HTTP request
                      |
             +--------+--------+
             |                 |
        /api/v1/...        /api/v2/...
             |                 |
       OrderV1Controller  OrderV2Controller
             |                 |
       OrderV1Assembler  OrderV2Assembler
             |                 |
             +--------+--------+
                      |
              OrderQueryService
              OrderCommandService
                      |
                 Domain model
~~~

Ví dụ DTO của hai version:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderV1Dto(
        UUID id,
        String status,
        BigDecimal total) {
}

public record MoneyDto(
        BigDecimal value,
        String currency) {
}

public record OrderV2Dto(
        UUID id,
        String state,
        MoneyDto amount,
        Instant createdAt) {
}
~~~

V1 và v2 có thể cùng nhận một domain Order, nhưng mapping representation khác nhau. Việc tách DTO ngăn thay đổi field v2 vô tình làm thay đổi JSON của v1. Không nên serialize trực tiếp JPA entity làm hợp đồng công khai cho nhiều version vì thay đổi persistence model có thể ảnh hưởng mọi consumer.

## Tạo link đúng version bằng Spring HATEOAS

Link trong representation phải trỏ đến controller thuộc cùng version. Dùng WebMvcLinkBuilder để tạo URI theo mapping thay vì nối chuỗi /api/v1 thủ công.

Assembler v1:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.stereotype.Component;

@Component
class OrderV1Assembler {

    EntityModel<OrderV1Dto> toModel(Order order) {
        OrderV1Dto dto = new OrderV1Dto(
                order.getId(),
                order.getStatus().name(),
                order.getTotal());

        return EntityModel.of(
                dto,
                linkTo(methodOn(OrderV1Controller.class)
                        .one(order.getId())).withSelfRel(),
                linkTo(methodOn(OrderV1Controller.class)
                        .all()).withRel(IanaLinkRelations.COLLECTION));
    }
}
~~~

Controller v1 dùng assembler và trả collection:

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
@RequestMapping(
        path = "/api/v1/orders",
        produces = MediaTypes.HAL_JSON_VALUE)
class OrderV1Controller {

    private final OrderQueryService orderQueryService;
    private final OrderV1Assembler assembler;

    OrderV1Controller(
            OrderQueryService orderQueryService,
            OrderV1Assembler assembler) {
        this.orderQueryService = orderQueryService;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderV1Dto>> all() {
        List<EntityModel<OrderV1Dto>> items = orderQueryService.findAll()
                .stream()
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(
                items,
                linkTo(methodOn(OrderV1Controller.class).all()).withSelfRel());
    }

    @GetMapping("/{id}")
    EntityModel<OrderV1Dto> one(@PathVariable UUID id) {
        Order order = orderQueryService.findById(id);
        return assembler.toModel(order);
    }
}
~~~

Order và OrderQueryService là các kiểu domain/application do dự án định nghĩa; ví dụ giả định findAll() trả danh sách order và findById() trả order hoặc ném exception không tìm thấy. Controller v2 có thể dùng cùng query service nhưng cần OrderV2Assembler và DTO v2.

Vì assembler gọi methodOn(OrderV1Controller.class), self link của item và collection link được tạo từ mapping /api/v1/orders. Khi tạo assembler v2, hãy tham chiếu OrderV2Controller; các link v2 sẽ được tạo trong namespace /api/v2. Ví dụ dùng IanaLinkRelations.COLLECTION cho relation chuẩn. Nếu cần một relation nghiệp vụ như orders, hãy tài liệu hóa semantics hoặc dùng extension relation URI theo chính sách của API.

## API root có thể công bố các version

Một API có thể cung cấp entry point ổn định /api, từ đó công bố link đến các version root:

~~~json
{
  "_links": {
    "curies": [
      {
        "name": "api",
        "href": "https://shop.example/rels/{rel}",
        "templated": true
      }
    ],
    "api:v1": {
      "href": "https://shop.example/api/v1"
    },
    "api:v2": {
      "href": "https://shop.example/api/v2"
    }
  }
}
~~~

Mỗi version root có thể công bố relation orders trỏ đến collection tương ứng:

~~~json
{
  "_links": {
    "curies": [
      {
        "name": "api",
        "href": "https://shop.example/rels/{rel}",
        "templated": true
      }
    ],
    "api:orders": {
      "href": "https://shop.example/api/v1/orders"
    }
  }
}
~~~

Client biết entry point /api, chọn version root theo chính sách tương thích của nó rồi theo relation api:orders. Prefix api là CURIE khai báo trong response; URI đầy đủ của extension relation được mở rộng từ template https://shop.example/rels/{rel}. Hãy tài liệu hóa semantics của từng relation. Không nên tự động chọn version cao nhất chỉ vì nó tồn tại: client chỉ nên dùng version mà nó hiểu.

Nếu hệ thống đã công bố URI root riêng cho từng version, client có thể bắt đầu trực tiếp tại /api/v1 hoặc /api/v2. API root chung là một lựa chọn khám phá, không phải điều kiện bắt buộc của URI versioning.

## Giữ toàn bộ link traversal trong cùng version

Khi client đã chọn v1, link được trả về trong representation v1 nên tiếp tục dẫn đến tài nguyên và hành động v1:

- self của order trỏ đến /api/v1/orders/{id}.
- collection trỏ đến /api/v1/orders.
- next và prev giữ prefix /api/v1.
- Link approve, cancel hoặc invoice trỏ đến endpoint có hợp đồng v1.

Không nên để trang v1 trả next sang /api/v2/orders?page=1 chỉ vì code tái sử dụng một link builder chung có base path v2. Điều đó khiến client đang chạy v1 vô tình nhận representation v2 ở bước tiếp theo.

Tách controller/assembler theo version là một cách làm rõ ranh giới. Nếu dùng một helper tạo link dùng chung, helper cần nhận đúng controller type hoặc version-specific link factory; tránh truyền version string tùy tiện khắp code.

## Pagination và search trong URI versioned

Pagination link phải giữ namespace version và toàn bộ filter/sort đang áp dụng. Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "https://shop.example/api/v1/orders?page=0&size=20&sort=createdAt,desc"
    },
    "next": {
      "href": "https://shop.example/api/v1/orders?page=1&size=20&sort=createdAt,desc"
    }
  }
}
~~~

Finder hoặc search resource cũng thuộc version tương ứng:

~~~text
/api/v1/orders/search/by-status?status=PAID
/api/v2/orders/search/by-status?state=PAID
~~~

V2 có thể đổi tên query parameter từ status sang state nếu đây là thay đổi breaking đã được đưa vào hợp đồng mới. Client v1 tiếp tục dùng tên cũ. Không đổi default sort, page index hoặc filter semantics của v1 khi triển khai v2.

Khi server tạo link, hãy dùng URI builder gắn với controller version đó và bảo toàn query parameter. Client nên theo next/prev thay vì tự ghép path và query string.

## Error response cũng thuộc hợp đồng version

Version không chỉ áp dụng cho response thành công. Request đến /api/v1 cần tiếp tục nhận error contract mà client v1 hiểu. Request đến /api/v2 có thể dùng cấu trúc mới nếu hợp đồng v2 quy định.

Các phần cần xem xét:

- HTTP status và semantics của lỗi.
- Problem Details type, title, detail và extension code.
- Media type như application/problem+json.
- Validation error field names.
- Link hỗ trợ hoặc link khôi phục nếu API công bố.

Không nên đổi 404 thành 200 hoặc đổi mã lỗi mà client v1 đang dùng chỉ vì controller v2 đã có cách xử lý mới. Có thể dùng exception mapper/advice riêng theo version hoặc giữ error contract chung nếu nó vẫn phù hợp cả hai version.

## URI versioning và Spring Security

Mỗi version là một route namespace, nhưng không phải ranh giới phân quyền. Cấu hình Spring Security cần bảo vệ cả /api/v1/** và /api/v2/** theo chính sách thích hợp. Nếu v2 thêm chức năng mới, không được mặc định endpoint v2 an toàn chỉ vì client phải biết URI mới.

Authorization nên tiếp tục dựa trên principal, authority, tenant và resource policy. Khi client theo link hành động trong v1 hoặc v2, server phải kiểm tra quyền lại ở request thực thi. Không công bố link nhạy cảm cho người dùng không đủ quyền và cũng không dựa vào việc ẩn link để bảo vệ endpoint.

## Deprecation và sunset cho version cũ

Khi v2 thay thế v1, không nên xóa v1 ngay sau khi v2 phát hành. Các client có lịch nâng cấp khác nhau; mobile app hoặc tích hợp đối tác có thể còn dùng v1 trong nhiều tháng.

Một lộ trình thường gồm:

1. Phát hành v2 và tài liệu migration.
2. Duy trì v1 song song trong thời gian chuyển đổi.
3. Thông báo v1 deprecated và cung cấp ngày sunset dự kiến.
4. Theo dõi traffic theo version và client để tìm consumer còn sử dụng.
5. Hỗ trợ chuyển đổi, gửi nhắc trước ngày ngừng hỗ trợ.
6. Chỉ gỡ v1 khi đáp ứng chính sách vòng đời đã công bố.

Có thể dùng HTTP Deprecation header theo RFC 9745 và Sunset header theo RFC 8594. Link relation deprecation có thể trỏ đến tài liệu giải thích thay đổi và hướng dẫn migration. Các header này thông báo vòng đời; chúng không tự động chuyển request v1 sang v2.

Ví dụ response v1 trong giai đoạn chuyển tiếp:

~~~http
HTTP/1.1 200 OK
Deprecation: @1798761599
Sunset: Thu, 31 Dec 2026 23:59:59 GMT
Link: <https://api.example.com/deprecations/v1>; rel="deprecation"
Content-Type: application/hal+json
~~~

Giá trị Deprecation dùng cú pháp Structured Fields Date; Sunset dùng HTTP-date. Chỉ công bố ngày sunset khi tổ chức đã có kế hoạch vận hành tương ứng.

## Kiểm thử URI versioning bằng MockMvc

Kiểm thử nên xác nhận route của từng version, representation tương ứng và link được tạo trong đúng namespace.

Ví dụ kiểm tra self link của v1:

~~~java
import static org.hamcrest.Matchers.endsWith;
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
class OrderApiVersioningTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void v1KeepsV1RepresentationAndLinks() throws Exception {
        mockMvc.perform(get("/api/v1/orders/o-42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.status").exists())
                .andExpect(jsonPath("$.total").exists())
                .andExpect(jsonPath("$._links.self.href")
                        .value(endsWith("/api/v1/orders/o-42")));
    }
}
~~~

Với v2, test kiểm tra field state và amount theo schema mới, đồng thời xác nhận self link kết thúc bằng /api/v2/orders/o-42. Không nên chỉ kiểm tra status 200; route có thể trả nhầm representation hoặc link của version khác mà request vẫn thành công.

Nên có thêm test:

- V1 và v2 cùng hoạt động với một domain fixture.
- Collection link và pagination link không đi chéo version.
- Finder/search parameter đúng với từng hợp đồng.
- Error response giữ đúng status, media type và error code.
- Version deprecated phát ra header thông báo.
- Security policy được áp dụng nhất quán trên cả hai namespace.
- Unknown version trả lỗi phù hợp, thường là 404 nếu không có route tương ứng.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đưa version vào controller nhưng link vẫn trỏ route cũ | Client bắt đầu ở v2 nhưng traversal quay về v1. | Dùng methodOn với controller cùng version. |
| Dùng chung DTO cho v1 và v2 | Thay đổi field v2 vô tình làm thay đổi response v1. | Tách DTO và assembler theo version. |
| Nhân đôi domain service cho từng version | Logic nghiệp vụ bị lệch theo thời gian. | Dùng chung domain/application service, tách adapter HTTP. |
| Version hóa mọi thay đổi nhỏ | Số phiên bản tăng và chi phí bảo trì lớn. | Chỉ tạo major version cho thay đổi breaking. |
| Để pagination link sang version khác | Client nhận hợp đồng không mong đợi ở trang tiếp theo. | Giữ mọi link của representation trong namespace version đó. |
| Xem API version là database version | Gắn sai vòng đời API với persistence model. | Quản lý API contract độc lập với entity revision và release server. |
| Xóa v1 ngay khi v2 phát hành | Client cũ bị gián đoạn. | Dùng deprecation, sunset và theo dõi consumer. |
| Chỉ kiểm thử route, không kiểm thử href | Link sai version vẫn lọt qua. | Assert self, collection, action và pagination href. |

## Nguyên tắc thiết kế

- Dùng segment major như /api/v1 và /api/v2 cho hợp đồng có thay đổi không tương thích.
- Giữ một version ổn định sau khi công bố; không tái sử dụng version number cho semantics mới.
- Không tăng version cho thay đổi additive mà client cũ có thể bỏ qua.
- Tách controller, DTO và assembler theo version; dùng chung domain/application service khi semantics nghiệp vụ không đổi.
- Tạo link bằng WebMvcLinkBuilder tham chiếu controller đúng version.
- Giữ self, collection, action, search và pagination links trong cùng namespace version.
- Dùng API root để khám phá version nếu client cần một entry point chung.
- Duy trì error contract và security policy phù hợp cho từng version.
- Công bố deprecation/sunset và có lộ trình migration cho version cũ.
- Kiểm thử representation cùng toàn bộ link traversal, không chỉ status code của route.

Version trong URI giúp client chọn rõ hợp đồng REST mà nó hiểu và cho phép nhiều major version cùng tồn tại trong giai đoạn chuyển đổi. Spring MVC định tuyến theo path, còn Spring HATEOAS tạo link dựa trên controller mapping để representation v1 tiếp tục dẫn đến tài nguyên v1 và representation v2 dẫn đến tài nguyên v2. Khi tách DTO/assembler theo version, dùng chung nghiệp vụ phù hợp và quản lý deprecation có kế hoạch, API có thể tiến hóa mà không buộc mọi consumer nâng cấp cùng lúc.
