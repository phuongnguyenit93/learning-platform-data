# Deprecation link

API thường phải duy trì nhiều resource và endpoint qua nhiều năm. Khi một URI hoặc một đường dẫn điều hướng không còn được khuyến nghị, server cần báo cho client biết điều đó và cung cấp hướng dẫn chuyển đổi. Nếu chỉ xóa link hoặc thay URI ngay lập tức, client đang sử dụng API có thể gặp lỗi mà không có thời gian chuẩn bị.

Spring HATEOAS hỗ trợ metadata deprecation trên đối tượng Link. Với HAL, metadata này được serialize thành thuộc tính deprecation của link object. Client có thể đọc URL tài liệu tại đó để biết link sẽ bị loại bỏ và cách chuyển sang lựa chọn mới. Bên cạnh cơ chế của HAL, RFC 9745 định nghĩa HTTP response header Deprecation và link relation deprecation; RFC 8594 định nghĩa Sunset và link relation sunset để thông báo thời điểm resource dự kiến ngừng phản hồi.

Bài học này tập trung vào cách công bố deprecation link bằng Spring HATEOAS, phân biệt metadata của một link với trạng thái vòng đời của resource, và xây dựng lộ trình chuyển đổi có thể khám phá bằng hypermedia.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích deprecation và lý do cần thông báo trước khi loại bỏ API.
- Dùng Link.withDeprecation() để gắn URL hướng dẫn deprecation vào HAL link.
- Phân biệt thuộc tính deprecation của HAL link object với link relation deprecation.
- Công bố link tài liệu deprecation bằng LinkRelation.of("deprecation").
- Sử dụng HTTP response header Deprecation theo RFC 9745.
- Phân biệt thời điểm deprecation với thời điểm sunset theo RFC 8594.
- Công bố link thay thế và hướng dẫn migration.
- Kiểm thử metadata và header trong response.
- Lập kế hoạch loại bỏ API mà vẫn hỗ trợ client đang hoạt động.

## Deprecation là gì?

Deprecation là thông báo rằng một resource, endpoint, phiên bản hoặc khả năng API sẽ không còn được khuyến nghị sử dụng. Server khuyến khích client chuyển sang phương án thay thế, nhưng việc đánh dấu deprecated tự nó không làm thay đổi cách resource hoạt động.

Ví dụ, hệ thống có endpoint:

~~~text
GET /api/v1/orders
~~~

Sau khi phát hành API v2, endpoint v1 vẫn có thể hoạt động trong một giai đoạn chuyển tiếp. Server có thể:

- Giữ endpoint v1 hoạt động để client hiện tại tiếp tục sử dụng.
- Công bố thông tin rằng đường dẫn v1 đã hoặc sẽ deprecated.
- Cung cấp link tới tài liệu giải thích thay đổi.
- Công bố link tới resource hoặc phiên bản thay thế.
- Đưa ra ngày dự kiến ngừng phục vụ nếu đã có kế hoạch sunset.

Deprecation giúp client developer biết rằng họ cần lập kế hoạch migration. Nó không có nghĩa resource đã bị xóa, không còn hợp lệ hoặc chắc chắn sẽ ngừng hoạt động ngay tại ngày được thông báo.

## Ba khái niệm cần phân biệt

Trong API hypermedia, có ba cơ chế liên quan nhưng không thay thế lẫn nhau:

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| Thuộc tính deprecation trên HAL link | Một link object | Cho biết link đó dự kiến bị loại bỏ và chỉ tới tài liệu giải thích |
| Header Deprecation và relation deprecation | Resource trong response | Thông báo resource đã hoặc sẽ deprecated, đồng thời cung cấp tài liệu về chính sách |
| Header Sunset và relation sunset | Resource hoặc phạm vi service được tài liệu hóa | Cho biết thời điểm resource dự kiến trở nên không phản hồi và nơi tìm chính sách sunset |

Một response có thể dùng nhiều cơ chế cùng lúc. Ví dụ, representation HAL có thể đánh dấu một link v1 bằng thuộc tính deprecation, thêm link relation deprecation tới migration guide, trong khi HTTP response mang header Deprecation và Sunset.

## Thuộc tính deprecation trên HAL link

HAL định nghĩa thuộc tính tùy chọn deprecation trong link object. Khi thuộc tính xuất hiện, nó cho biết link sẽ bị loại bỏ trong tương lai. Giá trị là một URL nên cung cấp thêm thông tin về việc deprecation. Client nên thông báo cho người vận hành hoặc developer khi đi theo link đó, chẳng hạn ghi log cảnh báo kèm URL hướng dẫn.

Spring HATEOAS cung cấp Link.withDeprecation(String) để tạo một link mới với thuộc tính này:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link legacyOrders = Link.of(
        "/api/v1/orders",
        IanaLinkRelations.COLLECTION)
    .withDeprecation(
        "https://developer.example.com/migrations/orders-v1");
~~~

Link là value object bất biến. withDeprecation() trả về một đối tượng Link mới; vì vậy cần giữ giá trị trả về như ví dụ trên. Phương thức getDeprecation() có thể đọc lại URL đã gắn.

HAL representation có thể được serialize như sau:

~~~json
{
  "_links": {
    "collection": {
      "href": "/api/v1/orders",
      "deprecation": "https://developer.example.com/migrations/orders-v1"
    }
  }
}
~~~

Thuộc tính deprecation không phải ngày hết hạn. Nó là URL để client tìm hiểu việc deprecation, bao gồm lý do, phạm vi, mốc thời gian và phương án thay thế. Nếu không có tài liệu đáng tin cậy tại URL đó, metadata sẽ không giúp client lên kế hoạch migration.

### Khi nào nên gắn thuộc tính deprecation?

Gắn thuộc tính này vào một link khi chính link đó sẽ bị loại bỏ hoặc thay thế. Ví dụ:

- Link tới endpoint API v1 sẽ bị loại bỏ sau giai đoạn chuyển tiếp.
- Link tới một collection cũ sẽ được thay bằng URI collection mới.
- Link tới một thao tác cũ sẽ được thay bằng affordance hoặc action resource mới.

Không gắn thuộc tính này vào tất cả link chỉ vì một endpoint trong hệ thống bị deprecated. Chỉ đánh dấu những link mà client cần biết sẽ bị loại bỏ. Nếu toàn bộ resource hiện tại đã deprecated, cân nhắc công bố thêm header Deprecation theo RFC 9745.

## Thuộc tính deprecation khác link relation deprecation

Hai cách dùng từ deprecation dễ bị nhầm:

1. Link.withDeprecation(uri) gắn thuộc tính deprecation vào một link object. Relation của link vẫn giữ nguyên, ví dụ collection.
2. Link.of(uri, LinkRelation.of("deprecation")) tạo một link có relation deprecation, tức link đó dẫn tới tài liệu về việc deprecated của resource hiện tại.

Ví dụ:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link deprecationGuide = Link.of(
    "https://developer.example.com/migrations/orders-v1",
    LinkRelation.of("deprecation"));
~~~

Trong response HAL, link có thể được biểu diễn:

~~~json
{
  "_links": {
    "deprecation": {
      "href": "https://developer.example.com/migrations/orders-v1",
      "type": "text/html",
      "title": "Hướng dẫn chuyển đổi Orders API v1"
    }
  }
}
~~~

Relation deprecation được RFC 9745 đăng ký trong IANA Link Relation Types Registry. Spring HATEOAS 3.1.2 cung cấp LinkRelation.of() để tạo relation theo tên; IanaLinkRelations hiện không có hằng DEPRECATION hoặc SUNSET, vì vậy hãy dùng LinkRelation.of("deprecation") và LinkRelation.of("sunset") cho hai relation này.

Có thể công bố cả hai cơ chế:

~~~java
Link legacyOrders = Link.of(
        "/api/v1/orders",
        IanaLinkRelations.COLLECTION)
    .withDeprecation(
        "https://developer.example.com/migrations/orders-v1");

Link deprecationGuide = Link.of(
    "https://developer.example.com/migrations/orders-v1",
    LinkRelation.of("deprecation"));
~~~

Link đầu cho client biết collection cũ sẽ bị loại bỏ và URL đọc thêm. Link thứ hai cung cấp một quan hệ điều hướng rõ ràng tới tài liệu deprecation của resource hiện tại.

## Công bố link deprecation trong representation Spring HATEOAS

Một API root hoặc resource có thể công bố collection cũ, collection thay thế và tài liệu migration:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ApiRootController {

    @GetMapping("/")
    EntityModel<ApiRoot> root() {
        Link legacyOrders = Link.of(
                "/api/v1/orders",
                IanaLinkRelations.COLLECTION)
            .withDeprecation(
                "https://developer.example.com/migrations/orders-v1");

        Link currentOrders = Link.of(
            "/api/v2/orders",
            IanaLinkRelations.SUCCESSOR_VERSION);

        Link migrationGuide = Link.of(
            "https://developer.example.com/migrations/orders-v1",
            LinkRelation.of("deprecation"))
            .withType("text/html")
            .withTitle("Hướng dẫn chuyển đổi Orders API v1");

        return EntityModel.of(
            new ApiRoot("Orders API"),
            legacyOrders,
            currentOrders,
            migrationGuide
        );
    }
}

record ApiRoot(String name) {
}
~~~

Trong ví dụ, relation collection chỉ tới collection v1; thuộc tính deprecation của link chỉ tới tài liệu giải thích việc loại bỏ link đó. Relation successor-version chỉ tới phiên bản kế tiếp. Relation deprecation chỉ tới tài liệu về việc deprecated resource hiện tại.

HAL response rút gọn có thể như sau:

~~~json
{
  "name": "Orders API",
  "_links": {
    "collection": {
      "href": "/api/v1/orders",
      "deprecation": "https://developer.example.com/migrations/orders-v1"
    },
    "successor-version": {
      "href": "/api/v2/orders"
    },
    "deprecation": {
      "href": "https://developer.example.com/migrations/orders-v1",
      "type": "text/html",
      "title": "Hướng dẫn chuyển đổi Orders API v1"
    }
  }
}
~~~

Khi một relation chỉ có một link, Spring HATEOAS thường serialize link object trực tiếp. Nếu cùng relation có nhiều link, HAL có thể serialize thành mảng link object. Client cần tuân theo quy tắc của media type thay vì giả định mọi relation luôn là object đơn.

### Công bố link thay thế

Khi có endpoint mới, hãy cung cấp link thay thế trong cùng representation hoặc trong tài liệu migration. Với các phiên bản resource, có thể dùng relation chuẩn:

- successor-version: resource chứa phiên bản kế tiếp.
- predecessor-version: resource chứa phiên bản trước.
- version-history: resource chứa lịch sử các phiên bản.

Spring HATEOAS cung cấp các hằng tương ứng trong IanaLinkRelations. Chúng giúp client hiểu quan hệ phiên bản mà không phải phân tích tên path như /v1/ hoặc /v2/.

Ví dụ:

~~~java
Link successor = Link.of(
    "/api/v2/orders",
    IanaLinkRelations.SUCCESSOR_VERSION);
~~~

Link thay thế không tự động chuyển đổi payload hoặc request. Client vẫn cần đọc migration guide để hiểu thay đổi về field, semantics, validation, quyền và cách gọi action.

## Deprecation HTTP response header theo RFC 9745

RFC 9745 định nghĩa header Deprecation để server thông báo rằng resource trong ngữ cảnh của response đã hoặc sẽ deprecated. Giá trị header là một Structured Field Date, biểu diễn bằng dấu @ theo sau là số giây Unix.

Ví dụ:

~~~http
Deprecation: @1782863999
~~~

Giá trị có thể chỉ một ngày trong tương lai hoặc trong quá khứ:

- Ngày trong tương lai: resource sẽ deprecated tại thời điểm đó.
- Ngày trong quá khứ: resource đã deprecated tại thời điểm đó.

Header này áp dụng cho resource được định danh bởi URI của response. Nó không phải header để mô tả một link bất kỳ trong body.

### Thêm header bằng Spring MVC

Spring HATEOAS xây dựng body hypermedia; Spring MVC ResponseEntity có thể thêm các HTTP response header. Ví dụ:

~~~java
import java.time.Instant;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class LegacyOrdersController {

    private static final Instant DEPRECATION_DATE =
        Instant.parse("2026-06-30T23:59:59Z");

    @GetMapping("/api/v1/orders")
    ResponseEntity<String> all() {
        HttpHeaders headers = new HttpHeaders();
        headers.set(
            "Deprecation",
            "@" + DEPRECATION_DATE.getEpochSecond());
        headers.add(
            "Link",
            "<https://developer.example.com/migrations/orders-v1>; rel=\"deprecation\"; type=\"text/html\"");

        return ResponseEntity.ok()
            .headers(headers)
            .body("Legacy orders response");
    }
}
~~~

Ví dụ dùng body dạng String để tập trung vào header. Trong ứng dụng HATEOAS, có thể trả EntityModel, CollectionModel hoặc PagedModel thay cho chuỗi; cách thêm header vẫn tương tự.

Header Link ở đây dùng relation deprecation theo RFC 9745. Có thể thêm title hoặc type để client biết loại tài liệu ở URI đích.

### Relation deprecation có thể xuất hiện trước header

RFC 9745 cho phép công bố link relation deprecation trước khi resource chính thức deprecated. Ví dụ, API có thể công bố chính sách rằng các resource sẽ được báo trước ít nhất 90 ngày. Khi tới ngày bắt đầu deprecation, server mới thêm header Deprecation.

Điều này giúp client khám phá chính sách vòng đời API và lên kế hoạch từ sớm. Sự có mặt của relation deprecation không tự khẳng định resource đã deprecated.

## Sunset: thời điểm resource dự kiến ngừng phản hồi

Deprecation và sunset là hai mốc khác nhau:

- Deprecation: resource không còn được khuyến nghị sử dụng.
- Sunset: resource dự kiến trở nên không phản hồi tại một thời điểm trong tương lai.

RFC 8594 định nghĩa header Sunset, có giá trị theo định dạng HTTP-date:

~~~http
Sunset: Wed, 30 Jun 2027 23:59:59 GMT
~~~

Sunset là tín hiệu dự kiến, không phải cam kết tuyệt đối rằng resource chắc chắn sẽ ngừng hoạt động đúng thời điểm đó. Sau thời điểm sunset, server có thể trả 410 Gone, 404 Not Found, redirect hoặc hành vi khác đã được công bố trong chính sách migration.

RFC 8594 cũng đăng ký relation sunset. Relation này trỏ tới tài liệu về chính sách retirement, thông tin sunset sắp tới hoặc phương án giảm thiểu tác động:

~~~java
Link sunsetPolicy = Link.of(
    "https://developer.example.com/policies/api-retirement",
    LinkRelation.of("sunset"));
~~~

Trong HAL:

~~~json
{
  "_links": {
    "sunset": {
      "href": "https://developer.example.com/policies/api-retirement",
      "type": "text/html",
      "title": "Chính sách ngừng phục vụ API"
    }
  }
}
~~~

Relation sunset có thể được công bố trước cả header Sunset, tương tự cách relation deprecation công bố trước header Deprecation.

### Kết hợp Deprecation và Sunset

RFC 9745 cho phép dùng cả hai header. Thời điểm Sunset không được sớm hơn thời điểm Deprecation.

Ví dụ:

~~~http
Deprecation: @1782863999
Sunset: Wed, 30 Jun 2027 23:59:59 GMT
Link: <https://developer.example.com/migrations/orders-v1>; rel="deprecation"; type="text/html"
Link: <https://developer.example.com/policies/api-retirement>; rel="sunset"; type="text/html"
~~~

Client có thể dùng thông tin này để:

- Cảnh báo đội phát triển về API đã deprecated.
- Ưu tiên migration trước ngày sunset.
- Theo dõi tài liệu hướng dẫn và phiên bản thay thế.
- Tránh tạo dependency mới lên resource sắp bị loại bỏ.

Không dùng Sunset chỉ để nói rằng một API không còn được khuyến nghị. Nếu API vẫn hoạt động vô thời hạn và chưa có kế hoạch ngừng phản hồi, chỉ công bố deprecation khi phù hợp.

## Kết hợp metadata trong một response

Một controller có thể công bố metadata ở cả HTTP layer và representation layer. Ví dụ sau minh họa cách thêm Deprecation, Sunset, hai HTTP Link header và các link HAL:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class LegacyOrderCatalogController {

    private static final Instant DEPRECATION_DATE =
        Instant.parse("2026-06-30T23:59:59Z");

    private static final Instant SUNSET_DATE =
        Instant.parse("2027-06-30T23:59:59Z");

    @GetMapping("/api/v1/order-catalog")
    ResponseEntity<EntityModel<OrderCatalog>> catalog() {
        String migrationUri =
            "https://developer.example.com/migrations/orders-v1";
        String sunsetPolicyUri =
            "https://developer.example.com/policies/api-retirement";

        Link legacy = Link.of(
                "/api/v1/order-catalog",
                IanaLinkRelations.SELF)
            .withDeprecation(migrationUri);

        Link successor = Link.of(
            "/api/v2/order-catalog",
            IanaLinkRelations.SUCCESSOR_VERSION);

        Link deprecation = Link.of(
                migrationUri,
                LinkRelation.of("deprecation"))
            .withType(MediaType.TEXT_HTML_VALUE);

        Link sunset = Link.of(
                sunsetPolicyUri,
                LinkRelation.of("sunset"))
            .withType(MediaType.TEXT_HTML_VALUE);

        EntityModel<OrderCatalog> body = EntityModel.of(
            new OrderCatalog("Legacy order catalog"),
            legacy,
            successor,
            deprecation,
            sunset
        );

        HttpHeaders headers = new HttpHeaders();
        headers.set(
            "Deprecation",
            "@" + DEPRECATION_DATE.getEpochSecond());
        headers.set(
            "Sunset",
            DateTimeFormatter.RFC_1123_DATE_TIME.format(
                SUNSET_DATE.atZone(ZoneOffset.UTC)));
        headers.add(
            "Link",
            "<" + migrationUri + ">; rel=\"deprecation\"; type=\"text/html\"");
        headers.add(
            "Link",
            "<" + sunsetPolicyUri + ">; rel=\"sunset\"; type=\"text/html\"");

        return ResponseEntity.ok()
            .headers(headers)
            .body(body);
    }
}

record OrderCatalog(String name) {
}
~~~

Đây là ví dụ minh họa cách kết hợp các lớp metadata. Trong ứng dụng thật, nên lấy ngày deprecation, ngày sunset và URI tài liệu từ cấu hình quản lý vòng đời API thay vì hard-code trong controller. Nếu ngày sunset thay đổi, tất cả header và tài liệu liên quan cần được cập nhật đồng bộ.

Lưu ý: ví dụ gắn thuộc tính deprecation vào self link vì chính resource API v1 sẽ bị loại bỏ. Nếu chỉ một link khác trong representation deprecated, hãy gắn metadata vào đúng link đó. Header Deprecation thông báo vòng đời của resource trong response.

## Lập kế hoạch migration

Một kế hoạch deprecation có thể chia thành các giai đoạn:

| Giai đoạn | Hành vi server | Điều client cần làm |
|---|---|---|
| Công bố kế hoạch | Có link tài liệu deprecation hoặc sunset, chưa nhất thiết có header ngày | Khám phá chính sách và chuẩn bị thay đổi |
| Bắt đầu deprecation | Gửi header Deprecation, giữ resource hoạt động | Dừng tạo dependency mới, bắt đầu migration |
| Giai đoạn chuyển tiếp | Duy trì API cũ, công bố link successor và hướng dẫn | Chuyển dần traffic sang API mới |
| Trước sunset | Gửi thêm header Sunset, nhắc rõ thời điểm ngừng phục vụ | Hoàn tất migration và kiểm tra production |
| Sau sunset | Thực hiện chính sách đã công bố, ví dụ 410 Gone hoặc redirect | Không tiếp tục phụ thuộc endpoint cũ |

Nên công bố:

- Nguyên nhân deprecation và phạm vi resource bị ảnh hưởng.
- Ngày bắt đầu deprecation.
- Ngày sunset nếu đã xác định.
- URI hoặc relation tới phiên bản thay thế.
- Thay đổi về schema, semantics, authentication, authorization và affordance.
- Hướng dẫn xử lý các khác biệt không thể tự động chuyển đổi.
- Kênh liên hệ cho client developer nếu có câu hỏi.

Nếu ngày sunset chưa được quyết định, không nên tự tạo một ngày giả định. Có thể công bố tài liệu chính sách và header Deprecation mà chưa gửi Sunset.

## Kiểm thử deprecation metadata

Kiểm thử HAL representation cần xác nhận link deprecated có thuộc tính deprecation và link thay thế được công bố:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
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
class LegacyOrderCatalogTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesDeprecationAndSuccessorLinks() throws Exception {
        mockMvc.perform(get("/api/v1/order-catalog")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.deprecation")
                .value("https://developer.example.com/migrations/orders-v1"))
            .andExpect(jsonPath("$._links.successor-version.href")
                .value("/api/v2/order-catalog"))
            .andExpect(jsonPath("$._links.deprecation.href")
                .value("https://developer.example.com/migrations/orders-v1"))
            .andExpect(jsonPath("$._links.sunset.href")
                .value("https://developer.example.com/policies/api-retirement"));
    }
}
~~~

Kiểm thử header HTTP:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/v1/order-catalog")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(header().string("Deprecation", "@1782863999"))
    .andExpect(header().string(
        "Sunset",
        "Wed, 30 Jun 2027 23:59:59 GMT"))
    .andExpect(header().string(
        "Link",
        containsString("rel=\"deprecation\"")));
~~~

Các ngày trong assertion cần khớp với cấu hình của ứng dụng. Nếu dùng đồng hồ hoặc cấu hình động, inject một Clock hoặc một properties bean để test có thể xác định thời điểm và tránh phụ thuộc ngày chạy test.

Nên bổ sung kiểm thử:

- Response API v1 có header Deprecation với giá trị Structured Field Date hợp lệ.
- Response API v1 có relation deprecation tới migration guide.
- Response API v1 có relation successor-version tới API thay thế.
- Header Sunset không sớm hơn ngày deprecation.
- API v2 không bị gắn metadata deprecated nếu chưa có kế hoạch.
- Endpoint cũ vẫn hoạt động trong giai đoạn chuyển tiếp đã công bố.
- Hành vi sau sunset phù hợp với chính sách đã mô tả.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm Link.withDeprecation() với relation deprecation | Client không tìm được tài liệu theo relation hoặc không nhận ra link cũ sẽ bị loại bỏ | Dùng thuộc tính trên link và relation tới tài liệu theo đúng mục đích |
| Cho rằng deprecated đồng nghĩa đã ngừng hoạt động | Client có thể ngừng gọi resource quá sớm | Duy trì hành vi trong giai đoạn deprecation đã công bố |
| Dùng Sunset như ngày bắt đầu deprecation | Client hiểu sai thời điểm resource không còn được khuyến nghị | Dùng Deprecation cho ngày deprecated, Sunset cho ngày dự kiến không phản hồi |
| Dùng định dạng HTTP-date cho header Deprecation | Giá trị không đúng Structured Field Date của RFC 9745 | Dùng @ và Unix timestamp |
| Dùng Unix timestamp cho header Sunset | Giá trị không đúng HTTP-date của RFC 8594 | Dùng định dạng HTTP-date theo UTC |
| Đặt ngày sunset trước ngày deprecation | Vi phạm thứ tự thời gian được RFC 9745 yêu cầu | Đảm bảo sunset không sớm hơn deprecation |
| Chỉ công bố ngày mà không có hướng dẫn | Client biết endpoint cũ sắp bị loại nhưng không biết chuyển đi đâu | Cung cấp migration guide và successor link |
| Hard-code ngày ở nhiều controller | Header và tài liệu có thể lệch nhau khi lịch thay đổi | Quản lý metadata vòng đời tập trung qua cấu hình |
| Tin rằng link deprecation đảm bảo tính xác thực tài liệu | Client có thể theo URI tài liệu không đáng tin | Dùng HTTPS và xác minh nguồn tài liệu trước khi tự động áp dụng hướng dẫn |
| Xóa endpoint ngay khi gửi header | Client không có thời gian chuyển đổi | Duy trì giai đoạn chuyển tiếp theo chính sách đã công bố |

## Ghi nhớ

Link.withDeprecation(uri) đánh dấu một link HAL sẽ bị loại bỏ trong tương lai và cung cấp URL tài liệu. Relation deprecation theo RFC 9745 trỏ tới tài liệu về deprecation của resource trong ngữ cảnh hiện tại; header Deprecation thông báo ngày resource đã hoặc sẽ deprecated. Sunset theo RFC 8594 báo thời điểm resource dự kiến trở nên không phản hồi, còn relation sunset dẫn tới chính sách retirement. Deprecation không tự thay đổi hành vi resource. Hãy công bố link successor, migration guide và các mốc thời gian nhất quán; kiểm thử cả HAL metadata lẫn HTTP headers trước khi triển khai lộ trình loại bỏ.

## Tài liệu tham khảo

- [Spring HATEOAS – Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [Spring HATEOAS – HAL LinkMixin API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/LinkMixin.html)
- [RFC 9745 – The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html)
- [RFC 8594 – The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html)
- [JSON Hypertext Application Language – Link Objects](https://datatracker.ietf.org/doc/draft-kelly-json-hal/11/)
- [Spring Framework – StandardApiVersionDeprecationHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/accept/StandardApiVersionDeprecationHandler.html)
