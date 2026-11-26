# Client cũ và link mới

Một REST API thường phải phục vụ nhiều thế hệ client cùng lúc. Client cũ có thể đang tìm relation acme:approve-order, trong khi client mới đã chuyển sang relation acme:approve; hoặc client vẫn gọi đường dẫn /api/v1/orders/42 trong khi server đã giới thiệu endpoint /api/v2/orders/42. Nếu thay đổi link thiếu kế hoạch, client cũ có thể không tìm thấy hành động, gọi nhầm endpoint hoặc không đọc được representation mới.

Hypermedia giúp giảm sự phụ thuộc vào cấu trúc URI vì client có thể khám phá target qua link relation. Khi server thay đổi href nhưng giữ nguyên ngữ nghĩa relation, client tuân theo link mới mà không cần biết đường dẫn đã đổi. Khi relation hoặc representation thay đổi không tương thích, server cần một giai đoạn chuyển tiếp: công bố link mới, giữ alias cũ cho client cũ, đánh dấu link cũ deprecated và chỉ loại bỏ sau khi có kế hoạch ngừng hỗ trợ.

Bài học này trình bày cách thiết kế thay đổi tương thích trong Spring HATEOAS, phân biệt thay đổi URI với thay đổi hợp đồng, duy trì relation cũ và mới, dùng metadata deprecation, lựa chọn chiến lược versioning, và kiểm thử nhiều thế hệ client.

## 1. Điều gì làm client cũ bị hỏng?

Một client hypermedia thường tìm link bằng relation rồi theo href:

~~~java
Link approve = order.getRequiredLink(OrderRelations.LEGACY_APPROVE_ORDER);
// Client gửi request đến approve.getHref().
~~~

Client có thể tiếp tục hoạt động khi server đổi target URI nhưng vẫn giữ relation acme:approve-order và giữ nguyên cách tương tác. Ví dụ:

| Thay đổi | Tác động tới client cũ |
| --- | --- |
| href đổi từ /api/orders/42/approve sang /api/v2/orders/42/approval | Thường tương thích nếu client theo link và method/payload vẫn được hỗ trợ |
| Thêm một link relation mới | Thường tương thích nếu client bỏ qua relation chưa biết |
| Thêm field JSON mới | Thường tương thích nếu client bỏ qua field chưa biết |
| Xóa hoặc đổi tên relation mà client đang dùng | Không tương thích |
| Đổi HTTP method hoặc request body của action | Có thể không tương thích |
| Đổi ý nghĩa nghiệp vụ của relation | Không tương thích về ngữ nghĩa |
| Xóa field bắt buộc hoặc đổi kiểu dữ liệu | Không tương thích với client phụ thuộc field đó |

Hypermedia không tự động làm mọi thay đổi trở nên tương thích. Nó tạo cơ chế để server điều khiển liên kết và giúp client khám phá hành động, nhưng hai phía vẫn phải thống nhất ngữ nghĩa relation, media type và cấu trúc dữ liệu.

## 2. Giữ relation ổn định khi chỉ thay đổi URI

Relation biểu diễn ý nghĩa của link; href biểu diễn địa chỉ hiện tại. Nếu hành động vẫn là duyệt đơn hàng, relation nên giữ nguyên dù endpoint thay đổi. Các ví dụ HAL bên dưới giả định ứng dụng đã cấu hình CurieProvider với prefix acme:

API cũ:

~~~json
{
    "_links": {
      "curies": {
        "name": "acme",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      },
    "acme:approve-order": {
      "href": "/api/orders/42/approve"
    }
  }
}
~~~

API mới:

~~~json
{
    "_links": {
      "curies": {
        "name": "acme",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      },
    "acme:approve-order": {
      "href": "/api/v2/orders/42/approval"
    }
  }
}
~~~

Client tìm acme:approve-order ở cả hai representation và theo target do server công bố. Client không cần tự nối /approve hoặc /approval vào URI đơn hàng.

Trong Spring HATEOAS, tạo link từ mapping controller giúp server giữ href đồng bộ với endpoint:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Link;

Link approve = linkTo(methodOn(OrderV2Controller.class)
        .approve(orderId))
        .withRel(OrderRelations.LEGACY_APPROVE_ORDER);
~~~

Ví dụ giả định OrderV2Controller.approve(...) ánh xạ tới endpoint mới. methodOn(...) đọc mapping để dựng URI; nó không gọi nghiệp vụ duyệt đơn.

Giữ relation ổn định là cách chuyển đổi đơn giản nhất khi chỉ thay đổi cấu trúc URL, gateway, host hoặc controller mapping. Nếu semantics của hành động thay đổi, cần relation mới thay vì tái sử dụng relation cũ cho một ý nghĩa khác.

## 3. Client cũ cần bỏ qua link và field chưa biết

Một client có khả năng tiến hóa nên:

- Tìm những relation mà nó hiểu, không yêu cầu danh sách link phải khớp chính xác.
- Bỏ qua relation mới mà nó chưa biết.
- Bỏ qua field JSON bổ sung nếu field đó không thuộc hợp đồng bắt buộc.
- Không suy luận endpoint từ tên entity hoặc cấu trúc URI.
- Không giả định một action luôn tồn tại trong mọi trạng thái.

Ví dụ client cũ chỉ cần relation self và acme:approve-order. Server có thể bổ sung acme:cancel-order, acme:refund-order hoặc acme:audit-history; client cũ không cần lỗi chỉ vì response có thêm link.

Tương tự, representation mới có thể thêm field priority hoặc lastModifiedAt. Client cũ dùng mapper linh hoạt và bỏ qua field không biết sẽ dễ tương thích hơn client yêu cầu JSON schema khớp tuyệt đối.

Điều này không có nghĩa server được tự do thay đổi mọi field. Nếu client cũ cần status là chuỗi với các giá trị đã biết, đổi field thành object hoặc đổi semantics của enum vẫn có thể làm client hỏng.

## 4. Khi nào cần relation mới?

Hãy tạo relation mới khi hành động mới có ngữ nghĩa khác hoặc cách tương tác không còn tương thích. Ví dụ:

| Relation cũ | Relation mới | Lý do |
| --- | --- | --- |
| acme:approve-order | acme:approve-order-with-review | Hành động mới yêu cầu bước xác nhận hoặc review |
| acme:refund-order | acme:request-refund | Client gửi yêu cầu hoàn tiền thay vì thực hiện hoàn tiền ngay |
| acme:publish | acme:schedule-publication | Hành động mới đặt lịch xuất bản, không xuất bản ngay |

Custom relation nên dùng URI tuyệt đối ổn định:

~~~java
import org.springframework.hateoas.LinkRelation;

public final class OrderRelations {

    public static final LinkRelation LEGACY_APPROVE_ORDER =
            LinkRelation.of("https://api.example.com/rels/approve-order");

    public static final LinkRelation APPROVE_ORDER =
            LinkRelation.of("https://api.example.com/rels/approve");

    public static final LinkRelation REQUEST_REFUND =
            LinkRelation.of("https://api.example.com/rels/request-refund");

    private OrderRelations() {
    }
}
~~~

Relation URI là định danh ngữ nghĩa công khai, không phải endpoint. URI target có thể thay đổi mà relation vẫn ổn định. Không gắn version của URL endpoint vào relation chỉ vì API đổi path từ v1 sang v2.

## 5. Duy trì relation cũ và mới trong giai đoạn chuyển tiếp

Nếu relation cũ được đổi tên nhưng ngữ nghĩa hành động vẫn tương đương, server có thể công bố cả hai relation trong một thời gian:

~~~json
{
  "_links": {
    "curies": {
      "name": "acme",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    },
    "acme:approve-order": {
      "href": "https://api.example.com/api/v2/orders/42/approval",
      "deprecation": "https://api.example.com/deprecations/approve-order"
    },
    "acme:approve": {
      "href": "https://api.example.com/api/v2/orders/42/approval"
    }
  }
}
~~~

Client cũ tiếp tục tìm acme:approve-order; client mới ưu tiên acme:approve. Cả hai link có thể trỏ đến cùng target nếu method, payload và kết quả vẫn tương thích.

Khi hai hành động khác nhau về semantics hoặc input, không nên trỏ cả hai relation đến cùng endpoint chỉ để giữ client cũ. Hãy duy trì endpoint adapter hoặc handler tương thích cho relation cũ, chuyển đổi request cũ sang mô hình nội bộ mới và trả response theo hợp đồng cũ.

Không xóa relation cũ ngay khi thêm relation mới. Giai đoạn chuyển tiếp cần đủ thời gian để client được cập nhật và triển khai. Lịch ngừng hỗ trợ cần được công bố qua tài liệu, header hoặc tài nguyên deprecation phù hợp.

## 6. Đánh dấu link cũ deprecated trong Spring HATEOAS

Spring HATEOAS Link hỗ trợ metadata deprecation. URI deprecation nên dẫn đến tài liệu giải thích link nào bị deprecated, lý do, phương án thay thế và mốc ngừng hỗ trợ:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Link;

Link legacyApprove = linkTo(methodOn(OrderV1Controller.class)
        .approve(orderId))
        .withRel(OrderRelations.LEGACY_APPROVE_ORDER)
        .withDeprecation(
                "https://api.example.com/deprecations/approve-order"
        );

Link currentApprove = linkTo(methodOn(OrderV2Controller.class)
        .approve(orderId))
        .withRel(OrderRelations.APPROVE_ORDER);
~~~

withDeprecation(...) gắn URI mô tả việc deprecated vào link. Với HAL, metadata này được serialize thành thuộc tính deprecation trong link object. Metadata cảnh báo client và công cụ developer; nó không tự chặn request hoặc tự xóa endpoint.

Trang deprecation nên mô tả:

- Relation cũ và target đang được hỗ trợ.
- Relation mới được khuyến nghị.
- Khác biệt về method, payload hoặc semantics nếu có.
- Phiên bản client cần nâng cấp.
- Ngày bắt đầu deprecation và ngày dự kiến ngừng hỗ trợ.
- Hướng dẫn chuyển đổi và cách nhận hỗ trợ.

## 7. Client mới ưu tiên relation mới, nhưng vẫn có fallback

Trong giai đoạn chuyển tiếp, client mới có thể tìm relation hiện hành trước rồi fallback về relation cũ:

~~~java
import java.util.Optional;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.RepresentationModel;

Optional<Link> approveLink = order.getLink(OrderRelations.APPROVE_ORDER)
        .or(() -> order.getLink(OrderRelations.LEGACY_APPROVE_ORDER));

Link selected = approveLink.orElseThrow(
        () -> new IllegalStateException("Order approval is unavailable")
);
~~~

Ví dụ trên giả định order là RepresentationModel đã deserialize và OrderRelations.APPROVE_ORDER là custom LinkRelation. Client ưu tiên relation mới, chỉ dùng relation cũ khi server chưa công bố relation mới.

Fallback cần có thời hạn. Nếu client giữ logic fallback vô thời hạn, server không thể kết thúc quá trình migration. Sau khi phiên bản client mới đã được triển khai rộng rãi, hãy loại bỏ fallback trong một phiên bản client sau và theo dõi việc sử dụng relation cũ trước khi server xóa alias.

Nếu client cũ không thể được nâng cấp, server cần duy trì relation cũ hoặc endpoint adapter trong thời gian hỗ trợ đã cam kết. Không thể buộc một client cũ tự hiểu relation mới mà nó chưa được lập trình để nhận diện.

## 8. Chọn chiến lược versioning cho API

Spring HATEOAS cung cấp mô hình link và serializer hypermedia; nó không áp đặt một chiến lược versioning duy nhất. Ứng dụng cần chọn cách phân biệt hợp đồng API dựa trên client, gateway, media type và yêu cầu vận hành.

| Chiến lược | Ví dụ | Ưu điểm | Chi phí |
| --- | --- | --- | --- |
| URI path | /api/v1/orders/42 và /api/v2/orders/42 | Dễ quan sát, định tuyến và vận hành song song | Có thể nhân đôi controller hoặc adapter |
| Media type | Accept: application/vnd.acme.order-v2+json | Version gắn với representation và content negotiation | Khó debug hơn; phải cấu hình negotiation và tài liệu |
| Profile | application/hal+json;profile="https://api.example.com/profiles/order-v2" | Mô tả semantics/constraints của representation | Client và server cần hiểu profile; profile không tự tạo endpoint version |
| Query parameter | ?api-version=2 | Dễ thêm vào một số gateway | Dễ bị bỏ quên trong cache key, link và log |

Không có lựa chọn nào tự động bảo đảm tương thích. Với URI versioning, link trong representation v1 nên trỏ tới resource/action thuộc hợp đồng v1; representation v2 có thể trỏ đến v2. Với media type versioning, cùng một URI có thể trả representation khác nhau theo Accept, vì vậy cache phải phân biệt biến thể theo Vary: Accept.

Profile mô tả một tập semantics hoặc quy ước của representation. Nó không phải công cụ thay thế hoàn toàn versioning khi cấu trúc payload hoặc hành vi HTTP thay đổi không tương thích.

## 9. Duy trì entry point riêng cho các phiên bản URI

Với URI versioning, có thể duy trì hai entry point trong thời gian chuyển đổi:

~~~text
https://api.example.com/api/v1
https://api.example.com/api/v2
~~~

Mỗi entry point công bố các relation phù hợp với hợp đồng phiên bản đó. Ví dụ:

~~~json
{
  "_links": {
    "orders": {
      "href": "https://api.example.com/api/v1/orders"
    }
  }
}
~~~

Entry point v2:

~~~json
{
  "_links": {
    "orders": {
      "href": "https://api.example.com/api/v2/orders"
    }
  }
}
~~~

Client v1 bắt đầu từ root v1 và chỉ nhận link thuộc hợp đồng v1. Client v2 bắt đầu từ root v2. Cách này tránh trường hợp client cũ gọi một root không versioned nhưng bất ngờ nhận link target v2 có payload hoặc method mới.

Nếu ứng dụng có một root không versioned, cần xác định rõ root đó đại diện cho phiên bản nào. Không âm thầm chuyển root mặc định sang phiên bản mới khi vẫn có client cũ phụ thuộc vào semantics cũ.

## 10. Dùng cùng relation cho các phiên bản nếu ngữ nghĩa không đổi

Relation orders có thể được dùng ở cả API v1 và v2 nếu trong cả hai phiên bản nó vẫn có nghĩa là collection đơn hàng. Target khác nhau theo phiên bản:

~~~java
Link ordersV1 = linkTo(methodOn(OrderV1Controller.class)
        .all())
        .withRel("orders");

Link ordersV2 = linkTo(methodOn(OrderV2Controller.class)
        .all())
        .withRel("orders");
~~~

Đây là hai representation được tạo trong hai context version khác nhau; mỗi context phát link phù hợp với phiên bản client đang sử dụng. Không nên trả đồng thời hai link có cùng relation orders trong cùng một representation nếu client không có quy tắc phân biệt rõ ràng.

Nếu relation cùng tên nhưng semantics đã thay đổi, cần relation mới. Ví dụ orders trong v1 trả tất cả đơn của tài khoản, nhưng orders trong v2 chỉ trả đơn đang hoạt động, thì client có thể hiểu sai kết quả. Hãy làm rõ semantics qua relation/profile mới hoặc giữ hành vi cũ cho phiên bản cũ.

## 11. Versioning representation bằng media type

Media type versioning cho phép client yêu cầu một representation cụ thể qua Accept:

~~~http
GET /api/orders/42
Accept: application/vnd.acme.order-v1+json
~~~

Client mới:

~~~http
GET /api/orders/42
Accept: application/vnd.acme.order-v2+json
~~~

Ứng dụng phải cấu hình content negotiation và chọn representation tương ứng. Chỉ khai báo chuỗi media type trong annotation không tự chuyển đổi domain model hoặc tạo adapter cho field khác nhau.

Nếu dùng HAL và profile để phân biệt semantics, request có thể dùng:

~~~http
GET /api/orders/42
Accept: application/hal+json;profile="https://api.example.com/profiles/order-v2"
~~~

Server phải công bố Content-Type phù hợp với representation đã chọn và xử lý trường hợp không hỗ trợ media type, thường bằng 406 Not Acceptable. Client nên gửi media type cụ thể thay vì giả định server luôn trả phiên bản mới nhất.

Với response có thể thay đổi theo Accept, thêm Vary: Accept để cache phân biệt representation. Không dùng cache key chỉ dựa vào URI khi cùng URI trả các hợp đồng khác nhau.

## 12. Tách domain model khỏi các phiên bản representation

Không nên để một entity persistence phải thay đổi theo mọi phiên bản API. Dùng DTO hoặc assembler riêng cho từng representation:

~~~java
public record OrderV1Dto(
        Long id,
        String status,
        String customerName
) {
}

public record OrderV2Dto(
        Long id,
        String state,
        CustomerSummary customer,
        boolean cancellable
) {
}
~~~

Assembler v1 và v2 chuyển cùng domain model sang representation phù hợp:

~~~java
public EntityModel<OrderV1Dto> toV1Model(Order order) {
    OrderV1Dto dto = new OrderV1Dto(
            order.getId(),
            order.getStatus().name(),
            order.getCustomer().getName()
    );

    return EntityModel.of(dto,
            linkTo(methodOn(OrderV1Controller.class)
                    .one(order.getId()))
                    .withSelfRel());
}
~~~

~~~java
public EntityModel<OrderV2Dto> toV2Model(Order order) {
    OrderV2Dto dto = new OrderV2Dto(
            order.getId(),
            order.getStatus().name(),
            new CustomerSummary(
                    order.getCustomer().getId(),
                    order.getCustomer().getName()
            ),
            order.canCancel()
    );

    return EntityModel.of(dto,
            linkTo(methodOn(OrderV2Controller.class)
                    .one(order.getId()))
                    .withSelfRel());
}
~~~

DTO/assembler riêng giúp giữ hợp đồng cũ ổn định trong khi representation mới có thể tổ chức field khác. Cả hai vẫn có thể dùng chung domain service và policy nghiệp vụ. Hãy bảo đảm action link trong từng representation trỏ tới endpoint tương ứng với phiên bản đó.

## 13. Dùng link relation deprecation và HTTP deprecation

Metadata deprecation trong link cho biết một quan hệ cụ thể không còn được khuyến nghị. Ngoài ra, server có thể dùng các header deprecation/sunset theo chính sách công bố vòng đời API:

~~~http
Deprecation: @1798761600
Sunset: Thu, 31 Dec 2026 23:59:59 GMT
Link: <https://api.example.com/deprecations/order-v1>; rel="deprecation"
~~~

Ví dụ header ở trên chỉ minh họa định dạng; timestamp và ngày cần được thay bằng lịch thực tế của API. Header Deprecation thông báo một tài nguyên/API đã hoặc sẽ bị deprecated theo RFC 9745; Sunset thông báo thời điểm dự kiến resource không còn khả dụng theo RFC 8594. Link relation deprecation có thể dẫn tới tài liệu giải thích.

Metadata deprecation ở link và header deprecation có phạm vi khác nhau:

- Link.withDeprecation: cảnh báo một link relation cụ thể.
- Deprecation header: thông báo trạng thái deprecated của resource/API.
- Sunset header: thông báo thời điểm dự kiến resource ngừng hoạt động.
- Tài liệu deprecation: giải thích thay đổi, tác động và hướng migration.

Không dùng header deprecation như một cách tự động thay thế endpoint. Server vẫn cần duy trì hành vi tương thích trong thời gian đã công bố.

## 14. Quy trình migration không làm hỏng client cũ

Một quy trình thực tế có thể gồm các giai đoạn:

1. Khảo sát hợp đồng hiện tại: liệt kê relation, target URI, method, payload, status code và media type mà client cũ đang sử dụng.
2. Xác định thay đổi tương thích: tách thay đổi chỉ ảnh hưởng href khỏi thay đổi relation, semantics, method hoặc representation.
3. Công bố link mới: giữ relation cũ nếu semantics không đổi; nếu relation đổi tên, công bố relation mới cùng alias cũ.
4. Đánh dấu deprecation: gắn metadata deprecation vào link cũ, cung cấp tài liệu và thời gian chuyển đổi.
5. Nâng cấp client: client mới ưu tiên relation mới và có fallback có thời hạn khi cần hỗ trợ server cũ.
6. Theo dõi và ngừng hỗ trợ: đo việc sử dụng endpoint/relation cũ, thông báo trước khi xóa và giữ khả năng rollback trong thời gian phù hợp.

Khi đo việc sử dụng link cũ, hãy dùng telemetry an toàn như route name, relation identifier và client version. Không ghi token, query nhạy cảm hoặc payload chứa dữ liệu cá nhân vào log.

## 15. Kiểm thử representation chứa link cũ và mới

MockMvc có thể xác nhận server giữ relation cũ trong thời gian chuyển tiếp, đồng thời công bố relation mới:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderV2Controller.class)
class OrderVersionCompatibilityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesCurrentAndLegacyApproveRelationsDuringMigration()
            throws Exception {
        mockMvc.perform(get("/api/v2/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links['acme:approve'].href").exists())
                .andExpect(jsonPath("$._links['acme:approve-order'].href").exists())
                .andExpect(jsonPath(
                        "$._links['acme:approve-order'].deprecation"
                ).value("https://api.example.com/deprecations/approve-order"));
    }
}
~~~

Test cần cấu hình fixture để đơn hàng 42 có thể duyệt, policy cho phép công bố cả hai link trong giai đoạn migration và mock các dependency của OrderV2Controller. Nếu endpoint chỉ công bố một relation theo phiên bản client, hãy kiểm thử riêng representation v1 và v2 thay vì mong đợi cả hai relation trong cùng response.

## 16. Kiểm thử client cũ vẫn theo được relation cũ

Một kiểm thử hợp đồng client có thể dùng Traverson để xác nhận entry point cũ vẫn dẫn tới link mà client cũ hiểu:

~~~java
import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

import static org.assertj.core.api.Assertions.assertThat;

class LegacyClientTraversalTest {

    @Test
    void legacyRelationStillResolvesToSupportedTarget() {
        Traverson traverson = new Traverson(
                URI.create("https://api.example.com/api/v1/orders/42"),
                MediaTypes.HAL_JSON
        );

        var legacyApprove = traverson
                .follow("acme:approve-order")
                .asLink();

        assertThat(legacyApprove.getHref())
                .contains("/approval");
    }
}
~~~

Đây là kiểm thử minh họa với API test server đang chạy tại entry point v1. Trong integration test thực tế, dùng RANDOM_PORT, MockWebServer hoặc HTTP stub để tránh gọi hệ thống bên ngoài. Assertion nên kiểm tra relation và semantics quan trọng; tránh khóa cứng toàn bộ hostname nếu môi trường test có port động.

## 17. Kiểm thử content negotiation và cache variation

Nếu API versioning bằng media type, hãy kiểm tra response tương ứng với từng Accept:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

mockMvc.perform(MockMvcRequestBuilders.get("/api/orders/42")
        .accept("application/vnd.acme.order-v1+json"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            "application/vnd.acme.order-v1+json"));

mockMvc.perform(get("/api/orders/42")
        .accept("application/vnd.acme.order-v2+json"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            "application/vnd.acme.order-v2+json"));
~~~

Các matcher content() cần được import từ MockMvcResultMatchers. Ví dụ giả định ứng dụng đã đăng ký converter và cấu hình negotiation cho hai media type. Bổ sung test 406 Not Acceptable khi client yêu cầu một phiên bản không được hỗ trợ.

Nếu cùng URI trả nhiều representation theo Accept, kiểm tra header Vary: Accept và cache policy. Với representation cá nhân hóa theo người dùng, còn phải áp dụng cache policy riêng như private hoặc no-store.

## 18. Những lỗi thường gặp

**Đổi href và relation cùng lúc dù semantics không đổi.** Giữ relation cũ, chỉ cập nhật target URI để client hypermedia tiếp tục hoạt động.

**Xóa relation cũ ngay khi phát hành relation mới.** Duy trì alias trong giai đoạn migration và đánh dấu deprecation.

**Tái sử dụng relation cũ cho hành động có semantics khác.** Tạo relation mới để client không thực hiện nhầm nghiệp vụ.

**Cho rằng client cũ tự hiểu relation mới.** Client chỉ biết vocabulary được lập trình hoặc cấu hình. Giữ alias hoặc nâng cấp client.

**Để client tự dựng URI từ phiên bản.** Theo link do server công bố; tránh nối /v2 hoặc tên endpoint ở phía client.

**Trả v2 representation từ entry point v1.** Giữ hợp đồng của entry point/version cũ hoặc có content negotiation rõ ràng.

**Coi profile là versioning tự động.** Profile mô tả semantics/constraints; ứng dụng vẫn phải cấu hình cách chọn và xử lý representation.

**Không phân biệt deprecation và sunset.** Deprecated nghĩa là không còn được khuyến nghị; sunset là thời điểm dự kiến resource ngừng hoạt động.

**Không kiểm thử client cũ.** Test server response mới thôi chưa đủ. Cần kiểm thử traversal và parser của client cũ với representation mới.

**Cache các phiên bản theo URI đơn thuần.** Khi response phụ thuộc Accept, cache phải phân biệt biến thể và xử lý Vary đúng.

## 19. Ghi nhớ

Client hypermedia có thể chịu được thay đổi URI khi server giữ nguyên relation và semantics của hành động. Khi cần đổi relation, server nên công bố relation mới cùng alias cũ trong giai đoạn chuyển tiếp, gắn metadata deprecation và duy trì endpoint tương thích đến mốc ngừng hỗ trợ đã công bố.

Spring HATEOAS hỗ trợ tạo link từ controller mapping và gắn deprecation metadata bằng Link.withDeprecation(...). Ứng dụng vẫn phải tự thiết kế versioning qua URI, media type hoặc profile, tách DTO/assembler theo hợp đồng và chọn representation tương ứng. Client mới nên ưu tiên relation mới, dùng fallback có thời hạn; client cũ tiếp tục dùng relation cũ cho đến khi được nâng cấp.

Kiểm thử nhiều thế hệ client, link cũ/mới, media type, deprecation và cache variation trước khi loại bỏ hợp đồng cũ. Hypermedia giúp server điều khiển quá trình khám phá API, còn tương thích thực tế vẫn phụ thuộc vào việc giữ ổn định ngữ nghĩa và giao thức đã công bố.

## Tài liệu tham khảo

- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [RFC 6906 – The profile Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906.html)
- [RFC 8594 – The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html)
- [RFC 9745 – The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html)
- [Spring HATEOAS Reference – Links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.links)
- [Spring HATEOAS Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [Spring Framework Reference – Content Negotiation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html)
