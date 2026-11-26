# IANA link relation

Trong REST API dùng hypermedia, một link không chỉ chứa URI đích. Client còn cần hiểu tài nguyên đích có quan hệ gì với tài nguyên hiện tại. Link relation cung cấp ý nghĩa đó. Ví dụ, self chỉ tài nguyên hiện tại, next chỉ tài nguyên tiếp theo trong một chuỗi, search chỉ điểm vào dùng để tìm kiếm, còn related chỉ một tài nguyên có liên quan.

IANA duy trì một registry các link relation chuẩn để nhiều API và client có thể dùng chung ngữ nghĩa. Spring HATEOAS cung cấp IanaLinkRelations để sử dụng các relation đã đăng ký dưới dạng hằng số có kiểu LinkRelation. Khi quan hệ của API không phù hợp với relation chuẩn, ứng dụng có thể định nghĩa extension relation bằng một URI ổn định.

Bài học này giải thích link relation theo RFC 8288, cách tra cứu và chọn relation từ IANA registry, cách dùng IanaLinkRelations và LinkRelation trong Spring HATEOAS, cách phân biệt relation chuẩn với relation riêng của ứng dụng, và cách kiểm thử relation được công bố trong representation.

## 1. Link relation mô tả điều gì?

Một link có hai thành phần cơ bản:

- Target URI: địa chỉ tài nguyên mà client có thể điều hướng đến.
- Relation: ý nghĩa của mối quan hệ giữa tài nguyên hiện tại và tài nguyên đích.

Ví dụ:

~~~text
Tài nguyên hiện tại: /api/orders/42
Target URI:          /api/customers/7
Relation:            related
~~~

Relation related cho biết khách hàng là một tài nguyên liên quan đến đơn hàng. Nó không nói client phải gửi GET hay POST, cũng không mô tả dữ liệu cần gửi trong request. Relation trả lời câu hỏi “đích này liên quan với tài nguyên hiện tại theo cách nào?”.

Trong HAL, link được biểu diễn trong thuộc tính _links:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "collection": {
      "href": "https://api.example.com/api/orders"
    },
    "related": {
      "href": "https://api.example.com/api/customers/7"
    }
  }
}
~~~

Các khóa self, collection và related chính là link relation. Client có thể dựa vào ý nghĩa của chúng để chọn link cần theo mà không phải phân tích cấu trúc URI.

## 2. IANA link relation registry

IANA (Internet Assigned Numbers Authority) duy trì registry các link relation đã đăng ký. Các relation chuẩn giúp những hệ thống độc lập hiểu cùng một loại liên kết theo một ngữ nghĩa thống nhất.

Registry có thể được tra cứu tại:

https://www.iana.org/assignments/link-relations/link-relations.xhtml

Một số relation thường gặp:

| Relation | Ý nghĩa |
| --- | --- |
| self | Link nhận diện tài nguyên hiện tại |
| collection | Target là collection chứa tài nguyên hiện tại |
| item | Target là một thành viên của collection hiện tại |
| related | Target là tài nguyên có liên quan |
| next | Target là tài nguyên tiếp theo trong một chuỗi |
| prev | Target là tài nguyên ngay trước trong một chuỗi |
| first | Target là tài nguyên đầu tiên trong chuỗi |
| last | Target là tài nguyên cuối cùng trong chuỗi |
| search | Target có thể được dùng để tìm kiếm trong ngữ cảnh hiện tại và tài nguyên liên quan |
| up | Target là tài liệu cha trong cấu trúc phân cấp |
| alternate | Target là một biểu diễn hoặc lựa chọn thay thế của tài nguyên hiện tại |
| describedby | Target cung cấp thông tin mô tả tài nguyên hiện tại |
| edit | Target có thể được dùng để chỉnh sửa tài nguyên hiện tại |
| help | Target cung cấp trợ giúp theo ngữ cảnh |

Đây là các ví dụ phổ biến, không phải toàn bộ registry. Danh sách relation có thể được IANA mở rộng theo thời gian; hãy tra registry khi cần chọn một relation cho trường hợp cụ thể.

## 3. Vì sao nên ưu tiên relation đã đăng ký?

Một API có thể tự đặt tên relation như order-details, customer-info hoặc next-page. Tuy nhiên, nếu một relation chuẩn đã diễn đạt đúng ý nghĩa cần công bố, dùng relation đó giúp client tái sử dụng hiểu biết có sẵn.

Ví dụ:

- Dùng self cho link trỏ về tài nguyên đang được biểu diễn.
- Dùng collection cho link từ một item về collection chứa nó.
- Dùng item cho link từ collection đến một phần tử.
- Dùng next và prev cho điều hướng trong một chuỗi có thứ tự.
- Dùng search cho điểm vào tìm kiếm.

Relation chuẩn giúp giảm số quy ước riêng mà client phải học. Điều này đặc biệt có ích khi một client tích hợp nhiều API do các nhóm hoặc tổ chức khác nhau phát triển.

Không nên chọn relation chỉ vì tên nghe có vẻ gần nghĩa. Hãy đọc mô tả trong registry và kiểm tra chiều quan hệ. Ví dụ, collection và item có ý nghĩa ngược chiều nhau: collection trỏ đến thành viên bằng item; item trỏ về collection bằng collection.

## 4. Dùng IanaLinkRelations trong Spring HATEOAS

Spring HATEOAS cung cấp lớp IanaLinkRelations trong package org.springframework.hateoas. Các trường như SELF, COLLECTION, ITEM, RELATED, NEXT, PREV và SEARCH là những giá trị LinkRelation tương ứng với relation chuẩn.

Tạo link:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of(
        "/api/orders/42",
        IanaLinkRelations.SELF
);

Link customer = Link.of(
        "/api/customers/7",
        IanaLinkRelations.RELATED
);
~~~

Sử dụng hằng số thay cho chuỗi giúp tránh lỗi chính tả và làm rõ rằng relation được chọn từ IANA registry. Giá trị của hằng số vẫn được serialize thành tên relation chuẩn, ví dụ SELF thành self.

Spring HATEOAS cũng hỗ trợ Link.of(href) không truyền relation. Trong trường hợp đó, relation mặc định là self. Cách viết này ngắn gọn khi link thực sự nhận diện tài nguyên hiện tại; với các link khác, hãy truyền relation tường minh để tránh vô tình gán sai ngữ nghĩa.

Có thể thêm nhiều link vào representation:

~~~java
import org.springframework.hateoas.EntityModel;

public record OrderDto(Long id, String status) {
}
~~~

Với DTO đã khai báo, có thể ghép nội dung và link vào EntityModel:

~~~java
import org.springframework.hateoas.EntityModel;

OrderDto order = new OrderDto(42L, "PAID");

EntityModel<OrderDto> model = EntityModel.of(
        order,
        self,
        customer
);
~~~

EntityModel lưu nội dung của tài nguyên cùng các link. Khi serialize bằng HAL, Spring HATEOAS đưa chúng vào _links.

## 5. Một số relation chuẩn và cách chọn đúng

### self

self nhận diện tài nguyên đang được biểu diễn. Hầu hết item resource nên có self link:

~~~java
Link self = Link.of(
        "/api/orders/42",
        IanaLinkRelations.SELF
);
~~~

Spring HATEOAS cũng có phương thức tiện ích withSelfRel() khi tạo link từ controller mapping:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link self = linkTo(methodOn(OrderController.class)
        .one(42L))
        .withSelfRel();
~~~

### collection và item

collection dùng khi link từ một item đến collection chứa item đó:

~~~java
Link collection = Link.of(
        "/api/orders",
        IanaLinkRelations.COLLECTION
);
~~~

item dùng khi collection trỏ đến một phần tử:

~~~java
Link item = Link.of(
        "/api/orders/42",
        IanaLinkRelations.ITEM
);
~~~

Không dùng collection để chỉ một tập hợp bất kỳ nếu target không phải collection của tài nguyên hiện tại theo ngữ nghĩa registry.

### next, prev, first và last

Các relation này biểu diễn điều hướng trong một chuỗi có thứ tự. Với kết quả phân trang, chúng có thể chỉ trang kế tiếp, trang trước, trang đầu và trang cuối:

~~~java
Link next = Link.of(
        "/api/orders?page=2",
        IanaLinkRelations.NEXT
);

Link previous = Link.of(
        "/api/orders?page=0",
        IanaLinkRelations.PREV
);
~~~

Client theo link để tiếp tục điều hướng. Relation next không có nghĩa là “một thao tác tiếp theo bất kỳ”; nó nói target là phần tử tiếp theo trong chuỗi.

### search

search chỉ tài nguyên có thể được dùng để tìm kiếm trong ngữ cảnh của link:

~~~java
Link search = Link.of(
        "/api/orders/search",
        IanaLinkRelations.SEARCH
);
~~~

Nếu endpoint nhận query parameter, có thể kết hợp relation search với URI template để công bố các biến tìm kiếm. Relation chỉ mô tả ý nghĩa link; template mô tả các biến URI.

## 6. LinkRelation là kiểu dữ liệu của relation

Trong Spring HATEOAS, LinkRelation là abstraction đại diện cho giá trị relation. Link sử dụng LinkRelation thay vì buộc ứng dụng làm việc trực tiếp với String ở mọi nơi.

Tạo relation từ chuỗi:

~~~java
import org.springframework.hateoas.LinkRelation;

LinkRelation relation = LinkRelation.of("https://api.example.com/rels/approve");
~~~

Có thể dùng relation đó khi tạo link:

~~~java
Link approval = Link.of(
        "/api/orders/42/approval",
        relation
);
~~~

LinkRelation.of(...) trả về một giá trị LinkRelation. Nó cho phép code truyền relation theo kiểu thống nhất với các hằng số IanaLinkRelations.

Để đọc giá trị relation:

~~~java
String value = approval.getRel().value();
~~~

Để kiểm tra quan hệ:

~~~java
boolean sameRelation =
        approval.getRel().isSameAs(relation);
~~~

isSameAs so sánh giá trị relation về mặt logic, không phụ thuộc implementation cụ thể của LinkRelation.

## 7. Phân biệt relation chuẩn và extension relation

RFC 8288 định nghĩa hai nhóm relation:

| Nhóm | Cách nhận diện | Ví dụ |
| --- | --- | --- |
| Registered relation type | Tên đã đăng ký trong IANA registry | self, next, search |
| Extension relation type | URI tuyệt đối dùng làm định danh relation riêng | https://api.example.com/rels/approve |

Nếu API cần một quan hệ riêng như approve, cancel hoặc assign-reviewer mà registry chưa có relation phù hợp, hãy dùng extension relation có URI tuyệt đối:

~~~java
LinkRelation approveRel = LinkRelation.of(
        "https://api.example.com/rels/approve"
);

Link approve = Link.of(
        "/api/orders/42/approval",
        approveRel
);
~~~

URI này là định danh ngữ nghĩa của relation. Tổ chức sở hữu API nên giữ nó ổn định và tài liệu hóa ý nghĩa, ngữ cảnh và cách client sử dụng. URI có thể trỏ đến trang mô tả để hỗ trợ con người và công cụ, nhưng điều quan trọng là định danh không bị thay đổi tùy tiện.

Không nên dùng một từ ngắn chưa đăng ký như approve làm extension relation. Theo RFC 8288, extension relation type được biểu diễn bằng URI tuyệt đối để tránh xung đột tên giữa các API.

## 8. Kiểm tra một relation có thuộc IANA hay không

IanaLinkRelations cung cấp isIanaRel để kiểm tra relation có phải relation chuẩn đã đăng ký mà Spring HATEOAS nhận diện hay không:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link self = Link.of("/api/orders/42", IanaLinkRelations.SELF);
LinkRelation approveRel = LinkRelation.of(
        "https://api.example.com/rels/approve"
);

boolean standard = IanaLinkRelations.isIanaRel(self.getRel());
boolean extension = IanaLinkRelations.isIanaRel(approveRel);
~~~

Trong ví dụ, standard là true và extension là false. Kiểm tra này hữu ích khi xử lý relation đến từ cấu hình hoặc dữ liệu ngoài. Nó không thay thế việc xác minh relation có đúng ngữ nghĩa trong ngữ cảnh API hay không.

Nếu nhận relation từ chuỗi bên ngoài, không nên tự động coi một giá trị bất kỳ là relation IANA chỉ vì nó có tên giống một từ thông dụng. Dùng registry hoặc API Spring HATEOAS để kiểm tra.

## 9. Relation không phải tên endpoint hay HTTP method

Một số khái niệm thường bị nhầm:

| Khái niệm | Câu hỏi được trả lời |
| --- | --- |
| URI | Tài nguyên đích nằm ở đâu? |
| Link relation | Tài nguyên đích liên quan thế nào với tài nguyên hiện tại? |
| HTTP method | Client gửi thao tác HTTP nào? |
| Affordance | Thao tác nào được công bố và cần metadata đầu vào/đầu ra nào? |
| Authorization | Người dùng hiện tại có được phép thực hiện thao tác không? |

Ví dụ, relation edit cho biết link đích liên quan đến việc chỉnh sửa tài nguyên. Nó không tự nói client phải dùng PUT hay PATCH. Nếu API cần công bố HTTP method và cấu trúc input, hãy dùng affordance hoặc một media type có khả năng mô tả thao tác.

Tương tự, có link relation delete không đồng nghĩa server đã cấp quyền xóa. Không nên tạo relation tùy ý chỉ để biểu diễn HTTP method. Hãy dùng affordance để mô tả thao tác và kiểm tra quyền ở server.

## 10. Relation chuẩn trong representation HAL

Ví dụ một order representation có self, collection và related:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

OrderDto order = new OrderDto(42L, "PAID");

EntityModel<OrderDto> model = EntityModel.of(
        order,
        Link.of("/api/orders/42", IanaLinkRelations.SELF),
        Link.of("/api/orders", IanaLinkRelations.COLLECTION),
        Link.of("/api/customers/7", IanaLinkRelations.RELATED)
);
~~~

HAL serialize model thành:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "collection": {
      "href": "https://api.example.com/api/orders"
    },
    "related": {
      "href": "https://api.example.com/api/customers/7"
    }
  }
}
~~~

Relation xuất hiện làm tên khóa trong _links. Client có thể tìm link theo relation thay vì phụ thuộc thứ tự link hoặc vị trí của chúng trong JSON.

## 11. Relation và @Relation trong Spring HATEOAS

Spring HATEOAS có annotation @Relation trong package org.springframework.hateoas.server.core. Annotation này thường dùng để cấu hình relation cho item và collection khi Spring HATEOAS tạo representation của một kiểu dữ liệu:

~~~java
import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(
        itemRelation = "order",
        collectionRelation = "orders"
)
public class OrderRepresentation
        extends RepresentationModel<OrderRepresentation> {

    private Long id;
    private String status;

    // Constructor, getter và setter.
}
~~~

@Relation cấu hình relation được dùng khi tham chiếu đến kiểu resource đơn lẻ hoặc collection của kiểu đó. Nó không đăng ký relation mới vào IANA registry và không thay thế IanaLinkRelations.

Spring HATEOAS dùng LinkRelationProvider để xác định relation cho item và collection. Provider có thể đọc cấu hình @Relation; nếu không có, framework áp dụng quy tắc mặc định dựa trên tên kiểu và cấu hình pluralization.

Phân biệt hai mục đích:

- IanaLinkRelations cung cấp relation chuẩn cho các liên kết như self, next, search.
- @Relation giúp định nghĩa tên relation của resource type trong representation, ví dụ order và orders.

Các giá trị ngắn order và orders trong ví dụ cần được ánh xạ bằng CURIE khi serialize HAL. Nếu không dùng CURIE, hãy khai báo relation bằng URI extension đầy đủ. Nếu dùng relation riêng trong HAL, hãy tài liệu hóa namespace để client có thể hiểu relation.

## 12. Curied relation cho relation riêng

HAL hỗ trợ CURIE (Compact URI) để biểu diễn relation URI dài dưới dạng tên ngắn có namespace. Ví dụ, relation URI:

~~~text
https://api.example.com/rels/approve
~~~

có thể được biểu diễn thành một tên rút gọn như ex:approve khi API khai báo CURIE tương ứng. CURIE giúp representation dễ đọc hơn nhưng vẫn giữ định danh relation đầy đủ.

Spring HATEOAS hỗ trợ cấu hình CURIE thông qua CurieProvider. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
@EnableHypermediaSupport(
        type = EnableHypermediaSupport.HypermediaType.HAL
)
public class HalConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
                "ex",
                UriTemplate.of("https://api.example.com/rels/{rel}")
        );
    }
}
~~~

Khi provider được dùng trong cấu hình HAL, Spring HATEOAS có thể công bố khai báo CURIE và serialize relation theo prefix. Client cần đọc khai báo CURIE để hiểu URI relation đầy đủ. Không tự rút ngắn relation URI bằng cách bỏ namespace nếu chưa công bố mapping tương ứng.

Một application scope chỉ nên có một bean CurieProvider vì provider chịu trách nhiệm ánh xạ namespace cho các relation extension trong representation.

## 13. Tìm relation trong RepresentationModel

RepresentationModel cung cấp các phương thức làm việc với link theo relation:

~~~java
boolean hasSelf = model.hasLink(IanaLinkRelations.SELF);

Link self = model.getRequiredLink(IanaLinkRelations.SELF);

model.getLink(IanaLinkRelations.RELATED)
        .ifPresent(link -> {
            // Dùng link liên quan nếu có.
        });
~~~

Một số phương thức thường dùng:

| Phương thức | Công dụng |
| --- | --- |
| hasLink(relation) | Kiểm tra model có link theo relation hay không |
| getLink(relation) | Lấy Optional<Link> theo relation |
| getRequiredLink(relation) | Lấy link bắt buộc; lỗi nếu không tồn tại |
| getLinks(relation) | Lấy tất cả link có cùng relation |
| add(link) | Thêm link vào model |

Không nên dùng getRequiredLink cho relation tùy chọn. Nếu link có thể không xuất hiện theo trạng thái hoặc quyền, dùng getLink hoặc hasLink để xử lý trường hợp thiếu.

## 14. Kiểm thử relation bằng unit test

Có thể kiểm tra relation của Link trước khi serialize:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

class IanaRelationTest {

    @Test
    void createsLinkWithRegisteredRelation() {
        Link link = Link.of(
                "/api/orders/42",
                IanaLinkRelations.SELF
        );

        assertThat(link.getRel()).isEqualTo(IanaLinkRelations.SELF);
        assertThat(IanaLinkRelations.isIanaRel(link.getRel())).isTrue();
    }

    @Test
    void representsApplicationRelationAsExtensionUri() {
        LinkRelation approve = LinkRelation.of(
                "https://api.example.com/rels/approve"
        );

        Link link = Link.of("/api/orders/42/approval", approve);

        assertThat(link.getRel().value())
                .isEqualTo("https://api.example.com/rels/approve");
        assertThat(IanaLinkRelations.isIanaRel(link.getRel())).isFalse();
    }
}
~~~

Unit test giúp phát hiện việc dùng nhầm relation hoặc tạo relation tùy chỉnh không đúng định danh đã thống nhất.

## 15. Kiểm thử relation trong HAL response bằng MockMvc

Kiểm thử ở mức HTTP xác nhận relation được serialize thành đúng tên trong _links:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderRelationMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesStandardRelationsInHal() throws Exception {
        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.collection.href").exists())
                .andExpect(jsonPath("$._links.related.href").exists());
    }
}
~~~

Đây là test slice minh họa. OrderController cần có các dependency tương ứng; hãy mock service và import assembler/configuration mà controller sử dụng. Kiểm tra relation theo tên ổn định, không phụ thuộc hostname hoặc thứ tự trường JSON.

Nếu API có extension relation, bổ sung assertion cho CURIE hoặc relation đã được serialize theo cấu hình HAL đang dùng. Test cần bảo đảm relation URI không bị mất namespace hoặc bị đổi ngoài ý muốn.

## 16. Những lỗi thường gặp

**Dùng relation tùy ý khi đã có relation chuẩn.** Điều này tạo thêm quy ước mà client phải học. Tra IANA registry trước khi định nghĩa relation mới.

**Nhầm chiều collection và item.** Từ item trỏ về collection dùng collection; từ collection trỏ đến thành viên dùng item.

**Dùng next cho mọi thao tác tiếp theo.** next mô tả phần tử tiếp theo trong chuỗi có thứ tự. Nó không thay thế affordance cho hành động nghiệp vụ.

**Dùng tên ngắn chưa đăng ký làm extension relation.** Relation riêng nên dùng URI tuyệt đối theo RFC 8288 để tránh xung đột tên.

**Coi relation là HTTP method.** Relation chỉ mô tả mối quan hệ ngữ nghĩa; dùng affordance hoặc metadata media type để mô tả thao tác HTTP.

**Coi relation là quyền truy cập.** Client nhìn thấy link không có nghĩa người dùng chắc chắn được phép thực hiện hành động. Server vẫn phải xác thực và phân quyền.

**Nhầm @Relation với IanaLinkRelations.** @Relation cấu hình relation cho kiểu resource và collection; IanaLinkRelations chứa các relation chuẩn của IANA.

**Thay đổi relation riêng mà không giữ tương thích.** Relation là một phần hợp đồng hypermedia. Hãy giữ URI định danh ổn định hoặc công bố thay đổi có chiến lược tương thích.

## 17. Ghi nhớ

Link relation mô tả mối quan hệ giữa tài nguyên hiện tại và tài nguyên đích. IANA registry cung cấp các relation chuẩn như self, collection, item, related, next, prev và search để client nhiều hệ thống có thể hiểu cùng một ngữ nghĩa.

Trong Spring HATEOAS, dùng IanaLinkRelations để tham chiếu relation chuẩn và LinkRelation để biểu diễn relation theo kiểu thống nhất. Dùng Link.of(href, relation) để tạo link có relation rõ ràng. Khi API cần quan hệ riêng, hãy dùng extension relation với URI tuyệt đối, giữ định danh ổn định và tài liệu hóa ngữ nghĩa. Có thể dùng CURIE để biểu diễn relation URI dài trong HAL.

Đừng nhầm relation với URI, HTTP method, affordance hoặc authorization. @Relation cũng có mục đích khác: nó cấu hình relation cho item và collection resource type, không đăng ký relation mới vào IANA. Kiểm thử cả giá trị relation trong model lẫn tên khóa được serialize trong HAL để giữ hợp đồng hypermedia ổn định.

## Tài liệu tham khảo

- [IANA Link Relations Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [Spring HATEOAS Reference – Link Relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.link-relations)
- [IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [LinkRelation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [Relation annotation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html)
