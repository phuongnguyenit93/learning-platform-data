# Sunset thông báo

Khi một phiên bản API sắp ngừng được hỗ trợ, client cần đủ thời gian để phát hiện thay đổi, đánh giá ảnh hưởng và chuyển sang tài nguyên hoặc phiên bản thay thế. Nếu server chỉ tắt endpoint vào một ngày đã định mà không thông báo theo hợp đồng HTTP, client có thể đột ngột nhận lỗi và các workflow đang chạy bị gián đoạn.

HTTP có hai header quan trọng cho vòng đời tài nguyên: `Deprecation` và `Sunset`. `Deprecation` thông báo tài nguyên đã hoặc sẽ bị đánh dấu deprecated. `Sunset` thông báo thời điểm tài nguyên được dự kiến sẽ không còn phản hồi. Hai thông tin này có ý nghĩa khác nhau và không tự động thay đổi hành vi endpoint. RFC 9745 định nghĩa header `Deprecation` và relation `deprecation`; RFC 8594 định nghĩa header `Sunset` và relation `sunset`.

Trong Spring HATEOAS, có thể công bố thêm link tới tài liệu migration hoặc chính sách retirement trong representation. Bài học này trình bày cách thiết kế mốc deprecation và sunset, tạo header đúng định dạng, công bố link relation, tích hợp với Spring MVC và kiểm thử response bằng MockMvc. Bạn cũng sẽ học cách tránh các lỗi như dùng chung một ngày cho hai khái niệm, phát sai định dạng ngày, tuyên bố sunset như một cam kết chắc chắn hoặc tắt endpoint mà không có kế hoạch chuyển đổi.

Sau bài học, bạn có thể:

- Phân biệt deprecation và sunset trong vòng đời API.
- Giải thích vai trò của RFC 9745 và RFC 8594.
- Tạo header `Deprecation` theo Structured Field Date.
- Tạo header `Sunset` theo định dạng HTTP-date.
- Kết hợp `Deprecation`, `Sunset` và các link relation tương ứng.
- Phân biệt link tới tài liệu deprecation, chính sách sunset và phiên bản thay thế.
- Công bố thông báo qua Spring MVC và Spring HATEOAS.
- Kiểm thử header, relation, ngày và content negotiation bằng MockMvc.
- Thiết kế lịch migration và chính sách phản hồi sau sunset.
- Phát hiện lỗi về phạm vi thông báo, CORS, cache và proxy.

## 1. Deprecation và Sunset giải quyết hai thời điểm khác nhau

Một API có thể tiếp tục hoạt động sau khi nhà cung cấp tuyên bố nó deprecated. Deprecation là tín hiệu cho biết client nên ngừng tạo phụ thuộc mới và bắt đầu chuyển đổi. Sunset là thời điểm tài nguyên được dự kiến sẽ trở nên không phản hồi.

Ví dụ một API đơn hàng có hai phiên bản:

~~~text
GET /v1/orders/42
GET /v2/orders/42
~~~

Nhà cung cấp quyết định không khuyến khích client mới sử dụng `/v1/orders/42` từ ngày 1 tháng 1 năm 2027 và dự kiến ngừng phục vụ tài nguyên này từ ngày 30 tháng 6 năm 2027.

Hai mốc này cần được thông báo riêng:

- Ngày deprecation: từ thời điểm đó tài nguyên được đánh dấu deprecated.
- Ngày sunset: thời điểm tài nguyên dự kiến không còn phản hồi.

Trong khoảng thời gian giữa hai mốc, endpoint cũ vẫn có thể xử lý request như trước. Client có thể dùng khoảng thời gian này để chuyển sang `/v2/orders/42`.

### 1.1. So sánh hai header

| Thuộc tính | `Deprecation` | `Sunset` |
|---|---|---|
| Tiêu chuẩn | RFC 9745 (Standards Track) | RFC 8594 (Informational) |
| Ý nghĩa | Tài nguyên đã hoặc sẽ bị deprecated | Tài nguyên dự kiến trở nên không phản hồi |
| Giá trị ngày | Structured Field Date | HTTP-date |
| Ví dụ | `@1798761600` | `Wed, 30 Jun 2027 23:59:59 GMT` |
| Có thay đổi hành vi endpoint không? | Không | Không trực tiếp |
| Tính chất | Tín hiệu vòng đời tài nguyên | Dự báo thời điểm retirement |
| Có thể công bố tài liệu bổ sung? | Có, relation `deprecation` | Có, relation `sunset` |

`Deprecation` không phải ngày endpoint chắc chắn bị tắt. `Sunset` cũng không phải cam kết tuyệt đối rằng endpoint sẽ hoạt động đến đúng thời điểm đó hoặc chắc chắn bị xóa ngay sau đó. RFC 8594 yêu cầu client xem thời điểm sunset như một tín hiệu để lập kế hoạch.

### 1.2. Deprecation không đồng nghĩa với ngừng hoạt động

RFC 9745 nêu rõ việc đánh dấu một resource deprecated không tự thay đổi ý nghĩa hoặc chức năng của resource. Server có thể tiếp tục phục vụ request trong giai đoạn deprecated.

Khi ngày deprecation đã qua, client không nên tiếp tục giả định hành vi sẽ luôn giống như trước mốc đó. Hãy đọc tài liệu migration được công bố cùng thông báo để biết thay đổi nào có thể xảy ra và resource thay thế nào được khuyến nghị.

Ví dụ:

~~~http
GET /v1/orders/42
~~~

Response vẫn có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Deprecation: @1798761600
Sunset: Wed, 30 Jun 2027 23:59:59 GMT
~~~

Client nhận được dữ liệu bình thường cùng thông tin về vòng đời của resource. Nó có thể lên kế hoạch migration trước ngày sunset.

### 1.3. Sunset không quy định status code sau khi ngừng phục vụ

RFC 8594 không bắt buộc server phải trả một status code cụ thể sau thời điểm sunset. Tùy chính sách và trạng thái thực tế, server có thể:

- Trả `410 Gone` nếu resource đã bị loại bỏ và server biết URI đó từng tồn tại.
- Trả redirect nếu có resource thay thế và việc chuyển hướng phù hợp.
- Trả `404 Not Found` nếu resource không còn được cung cấp.
- Ngừng phục vụ theo cách khác được mô tả trong chính sách của dịch vụ.

Không nên suy luận rằng có header `Sunset` thì sau ngày đó chắc chắn sẽ nhận `410 Gone`. Hãy công bố rõ hành vi sau sunset trong tài liệu migration.

## 2. Định dạng chính xác của Deprecation header

RFC 9745 định nghĩa `Deprecation` là một Item Structured Header Field có giá trị kiểu Date theo RFC 9651. Cú pháp dùng dấu `@` theo sau là số giây Unix.

Ví dụ:

~~~http
Deprecation: @1798761600
~~~

Giá trị này biểu thị thời điểm 1 tháng 1 năm 2027 lúc 00:00:00 UTC.

Không dùng định dạng HTTP-date cho header này:

~~~http
Deprecation: Fri, 01 Jan 2027 00:00:00 GMT
~~~

Đây không phải cú pháp Structured Field Date của RFC 9745.

### 2.1. Ngày deprecation có thể ở tương lai hoặc quá khứ

Header `Deprecation` có thể biểu thị một ngày trong tương lai hoặc quá khứ:

- Ngày tương lai: resource sẽ được đánh dấu deprecated tại mốc đó.
- Ngày quá khứ: resource đã được đánh dấu deprecated tại mốc đó.

Nếu resource đã deprecated, server tiếp tục gửi ngày deprecation ban đầu. Không thay ngày này bằng ngày hiện tại trong mỗi response, vì client cần một mốc vòng đời ổn định.

### 2.2. Chuyển Instant thành Structured Field Date

Trong Java, `Instant.getEpochSecond()` cung cấp số giây Unix. Có thể tạo giá trị header:

~~~java
static String toDeprecationHeader(Instant deprecationDate) {
    return "@" + deprecationDate.getEpochSecond();
}
~~~

Ví dụ:

~~~java
Instant deprecationDate =
    Instant.parse("2027-01-01T00:00:00Z");

String value = toDeprecationHeader(deprecationDate);

// @1798761600
~~~

Import:

~~~java
import java.time.Instant;
~~~

Không nối thêm hậu tố `Z`, `UTC` hoặc chuỗi ngày giờ sau số giây. Structured Field Date sử dụng dạng `@epoch-seconds`.

## 3. Định dạng chính xác của Sunset header

RFC 8594 định nghĩa `Sunset` là một HTTP response header field có giá trị `HTTP-date`. Định dạng ngày cần tuân theo cú pháp HTTP-date và dùng UTC với hậu tố `GMT`.

Ví dụ:

~~~http
Sunset: Wed, 30 Jun 2027 23:59:59 GMT
~~~

Không dùng định dạng ISO-8601 sau đây:

~~~http
Sunset: 2027-06-30T23:59:59Z
~~~

ISO-8601 phù hợp với nhiều API payload, nhưng không phải cú pháp HTTP-date của header `Sunset`.

### 3.1. Format Instant thành HTTP-date trong Java

Có thể dùng `DateTimeFormatter` với locale tiếng Anh và múi giờ UTC:

~~~java
private static final DateTimeFormatter HTTP_DATE =
    DateTimeFormatter
        .ofPattern("EEE, dd MMM yyyy HH:mm:ss 'GMT'", Locale.US)
        .withZone(ZoneOffset.UTC);

static String toSunsetHeader(Instant sunsetDate) {
    return HTTP_DATE.format(sunsetDate);
}
~~~

Import:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
~~~

Ví dụ:

~~~java
Instant sunsetDate =
    Instant.parse("2027-06-30T23:59:59Z");

String value = toSunsetHeader(sunsetDate);

// Wed, 30 Jun 2027 23:59:59 GMT
~~~

Dùng UTC để tránh việc cùng một mốc thời gian được phát ra dưới các múi giờ khác nhau. Không dùng thời gian local của máy chủ nếu chưa chuyển đổi về UTC.

### 3.2. Sunset là tín hiệu dự kiến, không phải bảo đảm

RFC 8594 mô tả thời điểm resource được kỳ vọng trở nên không phản hồi. Client nên xem đây là thông tin để điều chỉnh việc sử dụng resource, nhưng không thể dựa vào đó như một cam kết tuyệt đối.

Khi phát header mới, ngày Sunset SHOULD nằm trong tương lai. Nếu giá trị đã ở quá khứ, client nên hiểu resource có thể trở nên không khả dụng bất cứ lúc nào.

Ngày sunset có thể được điều chỉnh hoặc rút lại khi kế hoạch vận hành thay đổi. Tài liệu chính sách cần nêu cách thông báo khi ngày này thay đổi.

Sunset cũng không thay thế cache header. `Cache-Control`, `ETag` và `Last-Modified` liên quan đến việc tái sử dụng representation và phát hiện thay đổi dữ liệu; `Sunset` liên quan đến vòng đời khả dụng của resource.

## 4. Kết hợp Deprecation và Sunset đúng quy tắc

RFC 8594 cho phép công bố `Sunset` như một tín hiệu retirement độc lập. RFC 9745 mô tả cách kết hợp `Sunset` cùng `Deprecation` để thông báo cả thời điểm deprecated và thời điểm dự kiến ngừng phản hồi.

Một quy tắc quan trọng: ngày `Sunset` không được sớm hơn ngày `Deprecation`. Nếu Sunset sớm hơn, thông tin vòng đời mâu thuẫn và client nên yêu cầu nhà cung cấp làm rõ.

Ví dụ hợp lệ:

~~~http
Deprecation: @1798761600
Sunset: Wed, 30 Jun 2027 23:59:59 GMT
~~~

Ví dụ không hợp lệ về thứ tự thời gian:

~~~http
Deprecation: @1814399999
Sunset: Fri, 01 Jan 2027 00:00:00 GMT
~~~

Ngày sunset trong ví dụ thứ hai nằm trước ngày deprecation. Không phát ra cấu hình như vậy.

### 4.1. Kiểm tra thứ tự ngày trước khi tạo response

Có thể kiểm tra bằng Java:

~~~java
static void validateLifecycleDates(
        Instant deprecationDate,
        Instant sunsetDate) {

    if (sunsetDate.isBefore(deprecationDate)) {
        throw new IllegalArgumentException(
            "Sunset must not be earlier than Deprecation"
        );
    }
}
~~~

Nếu chưa xác định được ngày sunset, không cần tạo một ngày giả định. Có thể gửi `Deprecation` cùng tài liệu migration trước, rồi bổ sung `Sunset` khi lịch retirement đã được phê duyệt.

### 4.2. Không gửi Sunset như ngày hết hạn cache

Không nên đồng nhất:

- `Sunset`: dự kiến resource trở nên không phản hồi.
- `Expires`: thời điểm response trở nên stale theo cơ chế HTTP caching.
- `Cache-Control: max-age`: khoảng thời gian response có thể được cache fresh.

Một representation có thể cần cache trong thời gian ngắn dù resource còn nhiều tháng mới sunset. Ngược lại, resource sắp sunset vẫn có thể trả response với cache policy phù hợp.

## 5. Link relation cung cấp tài liệu deprecation và sunset

Header ngày chỉ cho client biết mốc thời gian. Để nhà phát triển hiểu lý do, tác động và cách chuyển đổi, server nên cung cấp link đến tài liệu liên quan.

RFC 9745 định nghĩa relation `deprecation` cho tài liệu về việc deprecate resource. RFC 8594 định nghĩa relation `sunset` cho tài nguyên chứa chính sách retirement, thông tin về sunset sắp tới hoặc cách giảm thiểu tác động.

Ví dụ HTTP Link header:

~~~http
Link: <https://developer.example.com/deprecation/orders-v1>; rel="deprecation"; type="text/html"
Link: <https://developer.example.com/sunset-policy>; rel="sunset"; type="text/html"
~~~

Hai link này có mục đích khác nhau:

| Relation | Tài liệu đích nên giải thích |
|---|---|
| `deprecation` | Vì sao resource deprecated, phạm vi ảnh hưởng và hướng dẫn migration |
| `sunset` | Chính sách retirement, mốc ngừng phục vụ và cách giảm thiểu tác động |
| `successor-version` | Phiên bản kế nhiệm hoặc resource thay thế |

Không dùng relation `deprecation` để trỏ trực tiếp đến endpoint thay thế nếu target thực chất là phiên bản mới. Relation đó được định nghĩa cho tài liệu về deprecation. Hãy công bố link phiên bản thay thế bằng relation phù hợp như `successor-version`.

### 5.1. Có thể công bố chính sách trước khi resource deprecated

Một dịch vụ có thể công bố link `deprecation` hoặc `sunset` từ sớm để client biết chính sách vòng đời, ngay cả khi chưa có header `Deprecation` hoặc `Sunset`.

Ví dụ:

~~~http
Link: <https://developer.example.com/api-lifecycle>; rel="deprecation"; type="text/html"
Link: <https://developer.example.com/sunset-policy>; rel="sunset"; type="text/html"
~~~

Các link này giúp client tìm hiểu chính sách deprecation và sunset của dịch vụ. Chúng không có nghĩa mọi resource đã deprecated hoặc sắp bị tắt.

### 5.2. Phân biệt link trong HTTP header và link trong HAL body

Spring HATEOAS có thể đưa link vào HAL representation:

~~~json
{
  "_links": {
    "self": {
      "href": "/v1/orders/42"
    },
    "deprecation": {
      "href": "/docs/deprecations/orders-v1"
    },
    "sunset": {
      "href": "/docs/sunset-policy"
    },
    "successor-version": {
      "href": "/v2/orders/42"
    }
  }
}
~~~

Đây là link trong body representation. RFC 9745 và RFC 8594 cũng cho phép công bố tài liệu qua HTTP `Link` response header. Hai cách có thể bổ sung cho nhau; hãy giữ URI và ý nghĩa relation nhất quán.

## 6. Tạo link relation bằng Spring HATEOAS

Spring HATEOAS cung cấp `LinkRelation.of(String)` để tạo relation và `Link.of(...)` để tạo link.

Ví dụ:

~~~java
Link deprecation = Link.of(
    "/docs/deprecations/orders-v1",
    LinkRelation.of("deprecation")
);

Link sunset = Link.of(
    "/docs/sunset-policy",
    LinkRelation.of("sunset")
);

Link successor = Link.of(
    "/v2/orders/42",
    IanaLinkRelations.SUCCESSOR_VERSION
);
~~~

Import:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
~~~

Có thể thêm vào representation:

~~~java
EntityModel<OrderRepresentation> model =
    EntityModel.of(orderRepresentation);

model.add(deprecation, sunset, successor);
~~~

Import bổ sung:

~~~java
import org.springframework.hateoas.EntityModel;
~~~

Trong Javadoc Spring HATEOAS hiện tại, `IanaLinkRelations` không cung cấp hằng số riêng cho `deprecation` và `sunset`. Có thể tạo các relation chuẩn đã đăng ký này bằng `LinkRelation.of(...)`. Không tạo extension relation URI cho các tên đã có định nghĩa trong IANA registry.

### 6.1. Link replacement phải trỏ đến tài nguyên có cùng ngữ nghĩa

Nếu endpoint cũ là:

~~~text
GET /v1/orders/42
~~~

và endpoint mới là:

~~~text
GET /v2/orders/42
~~~

link `successor-version` nên trỏ đến resource mới tương ứng với cùng order. Không chỉ trỏ đến trang chủ API hoặc collection nếu client cần một item resource cụ thể để tiếp tục workflow.

Nếu phiên bản mới thay đổi mô hình dữ liệu hoặc yêu cầu thao tác khác, tài liệu migration cần mô tả các bước chuyển đổi thay vì giả định client có thể thay URI trực tiếp.

### 6.2. Thuộc tính deprecation trên một HAL Link

Spring HATEOAS còn cung cấp `Link.withDeprecation(String)` để gắn URI tài liệu deprecation trực tiếp lên một link. Khi serialize thành HAL, thuộc tính `deprecation` nằm bên trong Link Object:

~~~java
Link legacySelf = Link.of("/v1/orders/42")
    .withSelfRel()
    .withDeprecation(
        "https://developer.example.com/deprecation/orders-v1"
    );
~~~

HAL representation có thể chứa:

~~~json
{
  "_links": {
    "self": {
      "href": "/v1/orders/42",
      "deprecation": "https://developer.example.com/deprecation/orders-v1"
    }
  }
}
~~~

Thuộc tính này là URI dẫn tới thông tin deprecation của chính link. Nó không chứa ngày deprecation và không thay thế response header `Deprecation`. Client HAL có thể phát cảnh báo khi đi theo link mang thuộc tính này và cung cấp URI tài liệu cho người duy trì client.

Phân biệt ba cấu trúc:

| Cấu trúc | Vị trí | Vai trò |
|---|---|---|
| `Deprecation` | HTTP response header | Công bố ngày resource được hoặc sẽ được đánh dấu deprecated |
| Relation `deprecation` | HTTP `Link` header hoặc HAL `_links` | Liên kết đến tài liệu về deprecation của context |
| Property `deprecation` | Bên trong một HAL Link Object | Cho biết link đó sẽ bị loại bỏ và cung cấp URI tài liệu |

Ví dụ kiểm thử thuộc tính trên link:

~~~java
.andExpect(jsonPath(
    "$._links.self.deprecation"
).value("https://developer.example.com/deprecation/orders-v1"));
~~~

Chỉ gắn thuộc tính này lên link thực sự sẽ bị loại bỏ. Nếu toàn bộ resource được đánh dấu deprecated, hãy công bố header và tài liệu ở cấp resource theo chính sách API.

## 7. Gắn thông báo Sunset vào response Spring MVC

Trong Spring MVC, `ResponseEntity` cho phép trả body, status và header trong cùng response. Có thể tạo header `Deprecation` và `Sunset` từ các mốc thời gian đã cấu hình.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/v1/orders")
class LegacyOrderController {

    private static final DateTimeFormatter HTTP_DATE =
        DateTimeFormatter
            .ofPattern("EEE, dd MMM yyyy HH:mm:ss 'GMT'", Locale.US)
            .withZone(ZoneOffset.UTC);

    private final OrderService orderService;

    LegacyOrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    ResponseEntity<EntityModel<OrderRepresentation>> getOrder(
            @PathVariable UUID id) {

        Instant deprecationDate =
            Instant.parse("2027-01-01T00:00:00Z");

        Instant sunsetDate =
            Instant.parse("2027-06-30T23:59:59Z");

        validateLifecycleDates(deprecationDate, sunsetDate);

        OrderRepresentation representation =
            orderService.getRepresentation(id);

        EntityModel<OrderRepresentation> model =
            EntityModel.of(
                representation,
                Link.of("/v1/orders/" + id, IanaLinkRelations.SELF),
                Link.of(
                    "/v2/orders/" + id,
                    IanaLinkRelations.SUCCESSOR_VERSION
                ),
                Link.of(
                    "/docs/deprecations/orders-v1",
                    LinkRelation.of("deprecation")
                ),
                Link.of(
                    "/docs/sunset-policy",
                    LinkRelation.of("sunset")
                )
            );

        return ResponseEntity.ok()
            .header(
                "Deprecation",
                "@" + deprecationDate.getEpochSecond()
            )
            .header(
                "Sunset",
                HTTP_DATE.format(sunsetDate)
            )
            .header(
                "Link",
                "<https://developer.example.com/deprecation/orders-v1>; rel=\"deprecation\"; type=\"text/html\", " +
                "<https://developer.example.com/sunset-policy>; rel=\"sunset\"; type=\"text/html\""
            )
            .body(model);
    }

    static void validateLifecycleDates(
            Instant deprecationDate,
            Instant sunsetDate) {

        if (sunsetDate.isBefore(deprecationDate)) {
            throw new IllegalArgumentException(
                "Sunset must not be earlier than Deprecation"
            );
        }
    }
}
~~~

Các import chính:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
~~~

Ví dụ này minh họa một endpoint cũ trả representation và thông báo vòng đời. Trong ứng dụng thực tế, ngày deprecation và sunset nên được lấy từ cấu hình quản lý phiên bản hoặc metadata tập trung, thay vì lặp lại trong từng controller.

### 7.1. Không hard-code ngày ở nhiều endpoint

Nếu một phiên bản API có nhiều resource, việc hard-code ngày trong từng controller dễ dẫn đến thông báo không nhất quán. Có thể tạo một cấu hình vòng đời dùng chung:

~~~java
public record ApiLifecycle(
    Instant deprecationDate,
    Instant sunsetDate,
    URI deprecationDocumentation,
    URI sunsetPolicy,
    URI successor
) {}
~~~

Import:

~~~java
import java.net.URI;
~~~

Một service hoặc component có thể đọc cấu hình này và cung cấp header/link cho controller. Cần bảo đảm cấu hình được kiểm tra khi ứng dụng khởi động, đặc biệt là quy tắc Sunset không sớm hơn Deprecation.

### 7.2. Dùng ResponseBodyAdvice hoặc interceptor khi cần áp dụng diện rộng

Nếu nhiều endpoint cùng thuộc một phiên bản deprecated, có thể cân nhắc cơ chế dùng chung như:

- Một helper tạo header và link lifecycle.
- Một controller advice hoặc response advice phù hợp với kiểu response.
- Một interceptor hoặc filter áp dụng header theo route policy.

Không gắn header deprecation/sunset cho toàn bộ ứng dụng nếu chỉ một phiên bản hoặc một nhóm resource bị ảnh hưởng. Phạm vi cần được xác định rõ theo route hoặc resource.

## 8. Kiểm thử thông báo bằng MockMvc

Kiểm thử cần xác minh header có đúng cú pháp, mốc thời gian, link relation và representation hay không.

Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class LegacyOrderLifecycleTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    OrderTestFixture fixture;

    UUID orderId;

    @BeforeEach
    void setUp() {
        orderId = fixture.createOrder();
    }

    @Test
    void publishesDeprecationAndSunsetInformation() throws Exception {

        mvc.perform(get("/v1/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Deprecation",
                "@1798761600"
            ))
            .andExpect(header().string(
                "Sunset",
                "Wed, 30 Jun 2027 23:59:59 GMT"
            ))
            .andExpect(header().string(
                "Link",
                allOf(
                    containsString("rel=\"deprecation\""),
                    containsString("rel=\"sunset\"")
                )
            ))
            .andExpect(jsonPath(
                "$._links.deprecation.href"
            ).value("/docs/deprecations/orders-v1"))
            .andExpect(jsonPath(
                "$._links.sunset.href"
            ).value("/docs/sunset-policy"))
            .andExpect(jsonPath(
                "$._links['successor-version'].href"
            ).value("/v2/orders/" + orderId));
    }
}
~~~

Import:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

`OrderTestFixture` là helper của test suite: `createOrder()` tạo và lưu một order để endpoint có dữ liệu trả về, sau đó trả lại ID. Tên helper và cách seed dữ liệu cần được thay bằng fixture thực tế của ứng dụng.

### 8.1. Kiểm tra header Deprecation có đúng cú pháp Structured Field Date

Không chỉ kiểm tra header tồn tại. Hãy kiểm tra giá trị có dạng `@epoch-seconds` và khớp ngày đã cấu hình.

Ví dụ:

~~~java
.andExpect(header().string("Deprecation", "@1798761600"));
~~~

Nếu server trả `Fri, 01 Jan 2027 00:00:00 GMT` hoặc `2027-01-01T00:00:00Z`, test cần thất bại vì đây không phải cú pháp của RFC 9745.

### 8.2. Kiểm tra Sunset là HTTP-date

Ví dụ:

~~~java
.andExpect(header().string(
    "Sunset",
    "Wed, 30 Jun 2027 23:59:59 GMT"
));
~~~

Test này giúp phát hiện lỗi múi giờ, locale, thiếu hậu tố GMT hoặc dùng ISO-8601 thay vì HTTP-date.

### 8.3. Kiểm tra ngày Sunset không sớm hơn Deprecation

Có thể kiểm tra quy tắc này ở unit test của cấu hình lifecycle:

~~~java
@Test
void rejectsSunsetBeforeDeprecation() {

    Instant deprecation =
        Instant.parse("2027-06-01T00:00:00Z");

    Instant sunset =
        Instant.parse("2027-05-01T00:00:00Z");

    assertThatThrownBy(() ->
        LegacyOrderController.validateLifecycleDates(deprecation, sunset)
    ).isInstanceOf(IllegalArgumentException.class);
}
~~~

Import:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
~~~

Đây là kiểm thử cấu hình, không phải kiểm thử response HTTP. Nên có cả hai: unit test bảo vệ quy tắc ngày và integration test bảo vệ header thực tế.

### 8.4. Kiểm tra link relation trong HAL body

Với Spring HATEOAS, có thể xác minh các relation:

~~~java
.andExpect(jsonPath("$._links.deprecation.href").exists())
.andExpect(jsonPath("$._links.sunset.href").exists())
.andExpect(jsonPath("$._links['successor-version'].href").exists());
~~~

Không giả định client chỉ đọc HTTP Link header hoặc chỉ đọc HAL body. Nếu API công bố cả hai, cần giữ URI và ngữ nghĩa thống nhất.

## 9. Chính sách migration và lịch thông báo

Thông báo deprecation có ích khi đi cùng một kế hoạch migration có thể hành động. Chỉ gửi header mà không có tài liệu thay thế sẽ khiến client biết endpoint sắp nghỉ nhưng không biết phải làm gì.

Một quy trình thực tế có thể gồm các giai đoạn:

| Giai đoạn | Thông tin công bố | Việc cần làm |
|---|---|---|
| Chuẩn bị | Chính sách deprecation và sunset | Hoàn thiện phiên bản thay thế, tài liệu và kiểm thử |
| Thông báo trước | Link relation tới tài liệu | Cho client biết chính sách và cách migration |
| Đánh dấu deprecated | Header Deprecation | Ngừng khuyến khích tích hợp mới, theo dõi client |
| Giai đoạn chuyển đổi | Deprecation, Sunset và link successor | Hỗ trợ migration, đo lưu lượng còn dùng API cũ |
| Trước sunset | Nhắc lại mốc retirement và hỗ trợ | Xác nhận client đã chuyển đổi |
| Sau sunset | Hành vi endpoint theo chính sách | Trả status/redirect phù hợp và duy trì tài liệu lịch sử |

Khoảng thời gian giữa deprecation và sunset phụ thuộc vào mức độ ảnh hưởng, số lượng client, chu kỳ phát hành của người tiêu thụ và khả năng hỗ trợ song song.

### 9.1. Tài liệu deprecation cần có gì?

Một trang tài liệu được liên kết bằng relation `deprecation` nên giải thích:

- Resource hoặc nhóm resource nào bị deprecated.
- Ngày deprecation và phạm vi áp dụng.
- Lý do thay đổi.
- API hoặc resource thay thế.
- Những khác biệt về URI, method, media type và payload.
- Các bước migration và ví dụ request/response.
- Những thay đổi cần thực hiện ở authentication, pagination hoặc error handling.
- Kênh hỗ trợ và lịch ngừng phục vụ.

### 9.2. Tài liệu sunset policy cần có gì?

Tài liệu được liên kết bằng relation `sunset` nên giải thích:

- Chính sách xác định resource nào sẽ sunset.
- Cách công bố hoặc cập nhật ngày sunset.
- Hành vi dự kiến sau ngày sunset.
- Có redirect, `410 Gone` hay một cách xử lý khác không.
- Quy trình yêu cầu gia hạn hoặc ngoại lệ nếu có.
- Cách client xác nhận migration đã thành công.

Không nên đưa thông tin nhạy cảm hoặc chi tiết vận hành nội bộ vào tài liệu công khai nếu client không cần biết.

### 9.3. Theo dõi mức sử dụng của client

Trong giai đoạn deprecated, nhà cung cấp nên theo dõi:

- Request còn đến từ phiên bản API cũ.
- Client hoặc API key nào còn sử dụng.
- Endpoint cũ nào có lưu lượng cao.
- Tỷ lệ lỗi khi client thử phiên bản mới.
- Các dependency hoặc webhook còn trỏ tới URI cũ.

Có thể dùng metrics và log đã loại bỏ dữ liệu nhạy cảm để hỗ trợ quyết định sunset. Không nên dựa vào header thông báo mà giả định mọi client đã nhận hoặc xử lý nó.

## 10. Phạm vi áp dụng của thông báo

Theo mặc định, header `Deprecation` và `Sunset` áp dụng cho resource được xác định bởi response đang mang header đó. Không được mặc định rằng một header trên một endpoint tự động áp dụng cho toàn bộ API.

Ví dụ:

~~~http
GET /v1/orders/42
Deprecation: @1798761600
~~~

Thông báo này theo nghĩa chuẩn áp dụng cho resource trong ngữ cảnh response. Nếu nhà cung cấp muốn nó đại diện cho toàn bộ phiên bản `v1`, chính sách phải mô tả rõ phạm vi mở rộng đó và công bố ở nơi client có thể khám phá.

Một entry point hoặc trang profile của API có thể liên kết tới tài liệu chính sách:

~~~http
Link: <https://developer.example.com/api-lifecycle/v1>; rel="deprecation"; type="text/html"
~~~

Những client không biết quy tắc mở rộng phạm vi vẫn chỉ diễn giải header theo nghĩa chuẩn: resource đang trả response đã được đánh dấu deprecated.

### 10.1. Phải giữ thông báo nhất quán qua proxy và gateway

Nếu API chạy sau API gateway, reverse proxy hoặc CDN, hãy kiểm tra các thành phần này có giữ nguyên header `Deprecation`, `Sunset` và `Link` hay không.

Một số cấu hình gateway có thể loại bỏ header không nằm trong allowlist. Khi đó client gọi trực tiếp backend thấy thông báo nhưng client gọi qua public gateway lại không thấy.

Cần kiểm thử ở đường đi thực tế mà client sử dụng, không chỉ kiểm tra controller unit test.

### 10.2. CORS và JavaScript client

Đối với client chạy trong browser và gọi API khác origin, JavaScript không mặc nhiên đọc được mọi response header. Nếu client cần đọc `Deprecation` hoặc `Sunset`, CORS policy cần expose các header đó:

~~~http
Access-Control-Expose-Headers: Deprecation, Sunset, Link
~~~

Ví dụ cấu hình Spring MVC:

~~~java
@Configuration
class CorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .exposedHeaders("Deprecation", "Sunset", "Link");
    }
}
~~~

Import:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
~~~

Chỉ expose header không thay thế cấu hình CORS cho origin, method và credential. Hãy giữ danh sách origin phù hợp với ứng dụng.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Coi deprecation là thời điểm tắt endpoint | Client hiểu sai vòng đời | Tách ngày deprecation và sunset |
| Dùng HTTP-date cho Deprecation | Header sai cú pháp RFC 9745 | Dùng Structured Field Date dạng `@epoch-seconds` |
| Dùng ISO-8601 cho Sunset | Header sai cú pháp HTTP-date | Dùng ngày HTTP với GMT |
| Sunset sớm hơn Deprecation | Hai mốc vòng đời mâu thuẫn | Validate thứ tự thời gian |
| Coi Sunset là cam kết tuyệt đối | Client có thể lên kế hoạch sai | Mô tả đây là tín hiệu dự kiến |
| Cho rằng Sunset bắt buộc trả 410 Gone | Client dựa vào status chưa được cam kết | Công bố hành vi sau sunset trong policy |
| Dùng relation deprecation để trỏ endpoint mới | Client hiểu sai target | Dùng successor-version cho phiên bản kế nhiệm |
| Không có tài liệu migration | Client biết API cũ sắp nghỉ nhưng không biết cách chuyển | Công bố deprecation documentation |
| Gắn header cho toàn ứng dụng | Resource không liên quan bị đánh dấu sai | Xác định phạm vi theo resource hoặc version |
| Hard-code ngày ở từng controller | Các endpoint phát ngày không nhất quán | Quản lý lifecycle metadata tập trung |
| Gateway loại bỏ header | Client không nhận được thông báo | Kiểm thử response qua gateway |
| Browser không đọc được header | Client JavaScript không phát hiện deprecation | Expose header qua CORS |
| Dùng Sunset như cache expiration | Sai chính sách cache | Quản lý cache và lifecycle riêng |

## 12. Checklist review trước khi phát hành thông báo

### Ngữ nghĩa và ngày tháng

- [ ] Đã xác định resource hoặc nhóm resource bị deprecated.
- [ ] Ngày Deprecation phản ánh đúng mốc đánh dấu deprecated.
- [ ] Header Deprecation dùng Structured Field Date dạng `@epoch-seconds`.
- [ ] Header Sunset dùng HTTP-date với GMT.
- [ ] Ngày Sunset không sớm hơn ngày Deprecation.
- [ ] Không công bố ngày sunset giả định khi lịch retirement chưa được xác định.
- [ ] Tài liệu nói rõ Sunset là thời điểm dự kiến, không phải bảo đảm.

### Hypermedia và tài liệu

- [ ] Relation `deprecation` trỏ tới tài liệu deprecation.
- [ ] Relation `sunset` trỏ tới chính sách sunset.
- [ ] Relation `successor-version` trỏ tới resource thay thế phù hợp.
- [ ] URI trong HTTP Link header và HAL body nhất quán.
- [ ] Tài liệu migration có ví dụ request/response và khác biệt cần xử lý.

### Triển khai và kiểm thử

- [ ] Controller hoặc lifecycle component phát đúng header.
- [ ] Có test kiểm tra cú pháp và giá trị ngày.
- [ ] Có test kiểm tra thứ tự Deprecation/Sunset.
- [ ] Có test cho link relation và response body.
- [ ] Gateway và CDN giữ các header cần thiết.
- [ ] CORS expose header nếu browser client cần đọc.
- [ ] Metrics có thể nhận diện client còn sử dụng API cũ.
- [ ] Hành vi sau sunset đã được công bố.

## 13. Kết luận

Thông báo deprecation và sunset giúp client có thời gian chuyển đổi trước khi một API cũ ngừng phục vụ. `Deprecation` theo RFC 9745 cho biết thời điểm resource được đánh dấu deprecated và dùng Structured Field Date dạng `@epoch-seconds`. `Sunset` theo RFC 8594 thông báo thời điểm resource dự kiến trở nên không phản hồi và dùng HTTP-date. Khi sử dụng cả hai, Sunset không được sớm hơn Deprecation.

Trong Spring HATEOAS, có thể công bố tài liệu deprecation, chính sách sunset và phiên bản kế nhiệm bằng các link relation tương ứng. Spring MVC có thể trả các header qua `ResponseEntity`, còn MockMvc giúp kiểm tra cú pháp, ngày, link và hành vi response. Một thông báo hữu ích cần đi cùng tài liệu migration, phạm vi áp dụng rõ ràng, chính sách sau sunset và khả năng quan sát client còn sử dụng phiên bản cũ. Nhờ đó, việc retirement trở thành một phần có thể dự đoán của hợp đồng API thay vì một lần tắt endpoint bất ngờ.

## Tài liệu tham khảo

- [RFC 9745 — The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html): cú pháp Structured Field Date, relation `deprecation`, mối quan hệ giữa Deprecation và Sunset.
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html): header Sunset, định dạng HTTP-date, relation `sunset`, phạm vi và các lưu ý về tính dự kiến.
- [RFC 9651 — Structured Field Values for HTTP](https://www.rfc-editor.org/rfc/rfc9651.html): kiểu Date được sử dụng bởi header Deprecation.
- [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html): cú pháp HTTP Link header và link relation.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): tạo response có status, headers và body.
- [Spring HATEOAS API — Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html): `withDeprecation(String)`, `getDeprecation()` và cách tạo link.
- [Spring HATEOAS API — LinkRelation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html): tạo relation bằng `LinkRelation.of(String)`.
- [Spring HATEOAS — IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html): các relation chuẩn được Spring HATEOAS cung cấp dưới dạng hằng số.
- [JSON Hypertext Application Language (HAL), Internet-Draft](https://datatracker.ietf.org/doc/html/draft-kelly-json-hal): thuộc tính `deprecation` tùy chọn trong HAL Link Object (tài liệu Internet-Draft, không phải RFC).

