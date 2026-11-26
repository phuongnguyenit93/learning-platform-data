# So sánh relation

Trong Spring HATEOAS, relation (quan hệ liên kết) cho biết link đang mô tả mối quan hệ nào giữa tài nguyên hiện tại và tài nguyên đích. Cùng một URI đích có thể được gắn các relation khác nhau tùy ngữ nghĩa; ngược lại, cùng một relation có thể trỏ đến các URI khác nhau trong từng response hoặc môi trường triển khai.

Khi thiết kế REST API có hypermedia, việc chọn relation ảnh hưởng trực tiếp đến khả năng khám phá và mức độ phụ thuộc của client vào server. Spring HATEOAS cung cấp LinkRelation để biểu diễn relation, IanaLinkRelations để dùng các relation chuẩn đã đăng ký và cơ chế relation tùy chỉnh cho nghiệp vụ riêng.

Bài học này so sánh relation chuẩn với relation tùy chỉnh, phân biệt các relation có ý nghĩa gần nhau, trình bày cách Spring HATEOAS biểu diễn và so sánh LinkRelation, đồng thời hướng dẫn cách chọn relation ổn định cho hợp đồng API.

## 1. Relation mô tả điều gì?

Một Link thường có href và rel:

- href xác định URI đích.
- rel mô tả ý nghĩa của mối quan hệ giữa tài nguyên hiện tại và đích đó.

Ví dụ, một đơn hàng có thể công bố:

~~~json
{
  "id": "ORD-42",
  "status": "PROCESSING",
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    },
    "collection": {
      "href": "/orders"
    },
    "customer": {
      "href": "/customers/CUS-7"
    },
    "cancel": {
      "href": "/orders/ORD-42/cancellation"
    }
  }
}
~~~

Các relation có vai trò khác nhau:

- self nhận diện chính tài nguyên đơn hàng đang được biểu diễn.
- collection dẫn đến tập hợp mà đơn hàng thuộc về.
- customer dẫn đến tài nguyên khách hàng liên quan.
- cancel công bố một đường dẫn nghiệp vụ cho thao tác hủy.

Relation không phải là URL, tên controller, tên method hoặc tên bảng dữ liệu. Client nên tìm link theo relation rồi sử dụng href được server công bố. Nếu server thay đổi đường dẫn của đơn hàng, relation self vẫn giữ ý nghĩa và client không cần tự xây URI từ mã đơn.

## 2. Hai nhóm relation: chuẩn IANA và tùy chỉnh

Có thể chia relation thành hai nhóm lớn dựa trên nguồn định nghĩa.

| Tiêu chí | Relation chuẩn IANA | Relation tùy chỉnh |
|---|---|---|
| Nguồn định nghĩa | Được đăng ký trong IANA Link Relation Types | Do API hoặc miền nghiệp vụ định nghĩa |
| Ngữ nghĩa | Có ý nghĩa chung được công bố trong registry | Có ý nghĩa theo hợp đồng của API |
| Khả năng tái sử dụng | Cao giữa các API khác nhau | Phụ thuộc client hiểu hợp đồng riêng |
| Ví dụ | self, collection, item, next, describedby, profile | customer, cancel, invoice, shipment |
| Cách dùng trong Spring HATEOAS | Hằng số trong IanaLinkRelations | LinkRelation.of("...") |
| Khi nên chọn | Khi relation chuẩn diễn đạt đúng ý định | Khi không có relation chuẩn phù hợp hoặc cần thuật ngữ nghiệp vụ rõ hơn |

Relation chuẩn giúp client tổng quát hiểu một số mối quan hệ phổ biến mà không cần biết riêng API. Ví dụ, next có ý nghĩa điều hướng đến phần tiếp theo trong một chuỗi; self nhận diện tài nguyên hiện tại.

Relation tùy chỉnh phù hợp với những khái niệm như customer, invoice hoặc cancel. Các relation này có thể rất rõ với client của hệ thống, nhưng cần được tài liệu hóa để client biết chúng có nghĩa gì.

Không nên dùng relation chuẩn chỉ vì tên của nó có vẻ gần giống nhu cầu. Ngữ nghĩa phải khớp với định nghĩa của relation. Nếu không có relation chuẩn đúng nghĩa, một relation tùy chỉnh được định nghĩa rõ ràng sẽ dễ hiểu và an toàn hơn.

## 3. Dùng IanaLinkRelations cho relation chuẩn

Spring HATEOAS cung cấp lớp IanaLinkRelations chứa các hằng số LinkRelation cho registry IANA. Ví dụ:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of(
    "/orders/ORD-42",
    IanaLinkRelations.SELF
);

Link collection = Link.of(
    "/orders",
    IanaLinkRelations.COLLECTION
);

Link next = Link.of(
    "/orders?page=2",
    IanaLinkRelations.NEXT
);
~~~

Một số relation thường gặp:

| Hằng số Spring HATEOAS | Giá trị relation | Ý nghĩa |
|---|---|---|
| SELF | self | Nhận diện tài nguyên hiện tại |
| COLLECTION | collection | Tập hợp chứa hoặc đại diện cho ngữ cảnh hiện tại |
| ITEM | item | Tài nguyên đích là phần tử của tập hợp |
| NEXT | next | Tài nguyên tiếp theo trong chuỗi |
| PREV | prev | Tài nguyên trước đó trong chuỗi |
| FIRST | first | Tài nguyên đầu tiên trong chuỗi |
| LAST | last | Tài nguyên cuối cùng trong chuỗi |
| SEARCH | search | Tài nguyên có thể dùng để tìm kiếm |
| PROFILE | profile | Profile mô tả ngữ nghĩa của biểu diễn |
| DESCRIBED_BY | describedby | Tài nguyên cung cấp thông tin mô tả ngữ cảnh của link |

Dùng hằng số giúp tránh gõ sai tên relation và làm rõ đây là relation chuẩn. IanaLinkRelations là một lớp chứa hằng số, không phải enum mà ứng dụng phải tự định nghĩa lại.

Nếu chỉ có chuỗi relation từ một nguồn bên ngoài, Spring HATEOAS còn cung cấp IanaLinkRelations.isIanaRel(...) để kiểm tra relation có thuộc registry IANA hay không, và IanaLinkRelations.parse(...) để chuyển chuỗi thành LinkRelation chuẩn tương ứng. Việc phân tích relation theo registry IANA tuân theo quy tắc không phân biệt chữ hoa/chữ thường của RFC 8288.

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.LinkRelation;

String suppliedRel = "NEXT";

boolean standard = IanaLinkRelations.isIanaRel(suppliedRel);

LinkRelation parsed = IanaLinkRelations.parse(suppliedRel);
~~~

Trong code ứng dụng, nên ưu tiên các hằng số IanaLinkRelations khi đã biết relation từ lúc biên dịch. isIanaRel và parse hữu ích hơn khi cần xử lý relation đến từ cấu hình hoặc dữ liệu bên ngoài.

## 4. Dùng LinkRelation cho relation tùy chỉnh

Khi cần một relation theo miền nghiệp vụ, có thể tạo bằng LinkRelation.of(...):

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link customer = Link.of(
    "/customers/CUS-7",
    LinkRelation.of("customer")
);

Link cancel = Link.of(
    "/orders/ORD-42/cancellation",
    LinkRelation.of("cancel")
);
~~~

LinkRelation là abstraction để biểu diễn giá trị relation. Nó có thể đại diện relation chuẩn hoặc relation tùy chỉnh; IanaLinkRelations cung cấp các giá trị chuẩn thường dùng, còn LinkRelation.of(...) tạo một relation từ chuỗi.

Nên định nghĩa relation tùy chỉnh ở một nơi dùng chung thay vì rải chuỗi trong nhiều controller:

~~~java
import org.springframework.hateoas.LinkRelation;

public final class ApiRelations {

    private ApiRelations() {
    }

    public static final LinkRelation CUSTOMER =
        LinkRelation.of("customer");

    public static final LinkRelation CANCEL =
        LinkRelation.of("cancel");

    public static final LinkRelation INVOICE =
        LinkRelation.of("invoice");
}
~~~

Sử dụng:

~~~java
model.add(customerLink.withRel(ApiRelations.CUSTOMER));
model.add(cancelLink.withRel(ApiRelations.CANCEL));
~~~

Việc tập trung relation giúp giảm lỗi chính tả và tạo một điểm để rà soát hợp đồng. Tên relation nên ổn định, viết theo một quy ước nhất quán và có tài liệu mô tả ngữ nghĩa.

Nếu relation cần được định danh toàn cầu hoặc được nhiều tổ chức sử dụng độc lập, có thể dùng URI relation theo quy tắc Web Linking. Trong HAL, CURIE có thể rút gọn URI relation dài thành dạng compact relation. Relation URI có ích khi API cần tránh xung đột tên giữa các miền hoặc tổ chức.

## 5. So sánh những relation có ý nghĩa gần nhau

Một số relation có tên gần nhau nhưng ngữ nghĩa khác nhau. Chọn đúng relation giúp client hiểu cấu trúc API chính xác.

### 5.1. self và related

- self trỏ đến chính tài nguyên đang được biểu diễn.
- related chỉ ra một tài nguyên có liên quan đến tài nguyên hiện tại, nhưng không mang ý nghĩa tự nhận diện.

Ví dụ, response đơn hàng nên có self đến /orders/ORD-42. Link đến khách hàng có thể dùng relation nghiệp vụ customer hoặc relation related nếu API chỉ muốn diễn tả một mối liên quan chung.

Không dùng related khi API có thể công bố quan hệ cụ thể như customer, invoice hoặc shipment. Relation cụ thể giúp client hiểu được tài nguyên đích mà không phải suy luận từ URL.

### 5.2. collection và item

- collection mô tả link đến tài nguyên tập hợp liên quan đến ngữ cảnh hiện tại.
- item mô tả link đến một tài nguyên là phần tử của tập hợp.

Ví dụ response tập hợp:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders"
    }
  },
  "_embedded": {
    "orders": [
      {
        "id": "ORD-42",
        "_links": {
          "self": {
            "href": "/orders/ORD-42"
          }
        }
      }
    ]
  }
}
~~~

Trong HAL, tên relation orders ở _embedded thường là relation tập hợp do relation provider xác định. Còn item là relation chuẩn trong Web Linking để mô tả đích là một thành viên của tập hợp. Không nên nhầm tên relation của phần tử nhúng trong HAL với mọi trường hợp sử dụng IanaLinkRelations.ITEM.

### 5.3. next, prev, first và last

Các relation này mô tả vị trí trong chuỗi tài nguyên hoặc kết quả phân trang:

- next dẫn đến phần tiếp theo.
- prev dẫn đến phần trước.
- first dẫn đến phần đầu tiên.
- last dẫn đến phần cuối cùng.

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders?page=2"
    },
    "first": {
      "href": "/orders?page=0"
    },
    "prev": {
      "href": "/orders?page=1"
    },
    "next": {
      "href": "/orders?page=3"
    },
    "last": {
      "href": "/orders?page=8"
    }
  }
}
~~~

Client nên theo link được cung cấp thay vì tự tăng hoặc giảm page parameter. Với cursor pagination, href có thể chứa cursor thay vì số trang; ý nghĩa của relation vẫn là điều hướng theo thứ tự.

### 5.4. describedby và profile

Hai relation này đều có thể dẫn đến tài liệu mô tả, nhưng ý nghĩa không giống nhau:

- describedby dẫn đến tài nguyên cung cấp thông tin về ngữ cảnh của link.
- profile nhận diện profile mà biểu diễn tuân theo, bổ sung ngữ nghĩa mà không thay đổi semantics cơ bản của media type.

Ví dụ, describedby có thể dẫn đến tài liệu hướng dẫn hoặc mô tả tài nguyên. profile thường tham chiếu một profile mô tả quy ước hoặc ngữ nghĩa bổ sung mà representation tuân thủ.

Không dùng profile như một từ đồng nghĩa chung cho tài liệu hướng dẫn. Chọn relation theo mục đích thực tế của tài liệu được liên kết.

### 5.5. create-form và create

create-form là relation IANA chỉ đến tài nguyên nơi client có thể lấy biểu mẫu để gửi yêu cầu tạo. Một relation tùy chỉnh như create có thể được API dùng để chỉ đường dẫn hoặc thao tác tạo theo hợp đồng riêng.

Nếu API chỉ muốn công bố endpoint tạo tài nguyên, cần định nghĩa rõ semantics của relation tùy chỉnh. Nếu API muốn chỉ đến một submission form, hãy xem xét create-form và media type phù hợp.

## 6. So sánh LinkRelation trong Spring HATEOAS

LinkRelation là interface có thể biểu diễn nhiều cách triển khai relation. Không nên phụ thuộc vào class triển khai cụ thể khi chỉ cần so sánh giá trị relation.

Phương thức isSameAs(...) kiểm tra hai LinkRelation có cùng giá trị chuỗi hay không, độc lập với implementation:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.LinkRelation;

LinkRelation fromIana = IanaLinkRelations.NEXT;
LinkRelation fromString = LinkRelation.of("next");

boolean same = fromIana.isSameAs(fromString);
~~~

Đây là cách phù hợp khi một relation đến từ hằng số IANA còn relation kia được tạo từ chuỗi. isSameAs(...) tập trung so sánh giá trị relation thay vì yêu cầu hai đối tượng phải có cùng class triển khai.

Có thể đọc giá trị chuỗi bằng value():

~~~java
String relValue = IanaLinkRelations.NEXT.value();
~~~

Nếu cần kiểm tra relation có phải relation chuẩn IANA:

~~~java
boolean isStandard =
    IanaLinkRelations.isIanaRel(LinkRelation.of("next"));

boolean isCustom =
    !IanaLinkRelations.isIanaRel(LinkRelation.of("customer"));
~~~

Hãy phân biệt hai câu hỏi:

- isSameAs(...) trả lời hai LinkRelation có cùng giá trị relation hay không.
- isIanaRel(...) trả lời relation có thuộc registry IANA hay không.

Một relation tùy chỉnh có thể được so sánh bằng isSameAs(...) giống như relation chuẩn. Việc so sánh thành công không biến relation tùy chỉnh thành relation IANA.

### 6.1. Chuyển đổi giá trị relation

LinkRelation có phương thức map(...) để tạo relation từ một phép biến đổi chuỗi. Với relation IANA, phương thức này giữ nguyên relation chuẩn thay vì thay đổi tên đã đăng ký.

~~~java
LinkRelation custom = LinkRelation.of("customer");

LinkRelation namespaced = custom.map(value -> "shop-" + value);

LinkRelation standard = IanaLinkRelations.SELF
    .map(value -> "my-" + value);
~~~

namespaced là relation tùy chỉnh được biến đổi theo hàm. standard vẫn giữ relation self vì map(...) không biến đổi relation IANA. Hành vi này giúp tránh vô tình làm thay đổi tên relation chuẩn khi áp dụng một phép ánh xạ chung.

Không nên dùng map(...) để đổi tên relation công khai tùy tiện ở từng response. Nếu cần thay relation, hãy xem đó là thay đổi hợp đồng API và có kế hoạch chuyển tiếp cho client.

## 7. LinkRelation và LinkRelationProvider là hai khái niệm khác nhau

Hai tên này gần nhau nhưng phục vụ hai nhiệm vụ:

| Thành phần | Vai trò |
|---|---|
| LinkRelation | Biểu diễn một giá trị relation cụ thể, ví dụ self hoặc customer |
| IanaLinkRelations | Cung cấp các relation chuẩn IANA dưới dạng hằng số |
| LinkRelationProvider | Xác định relation phù hợp cho một kiểu tài nguyên hoặc tập hợp tài nguyên |
| @Relation | Cho phép chỉ định tên relation item và collection cho một representation type |

Ví dụ DTO:

~~~java
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderRepresentation(
    UUID id,
    String status
) {}
~~~

@Relation cho Spring HATEOAS biết tên relation dùng khi biểu diễn một phần tử và một tập hợp. LinkRelationProvider là abstraction thực hiện việc xác định các relation đó. Đây là cơ chế đặt tên relation cho loại tài nguyên; nó không phải cơ chế so sánh hai LinkRelation.

Nếu không cấu hình @Relation, Spring HATEOAS dùng relation provider mặc định và quy tắc đặt tên dựa trên kiểu tài nguyên. Nếu API cần relation ổn định, rõ nghĩa và không phụ thuộc tên class Java, hãy khai báo tường minh bằng @Relation hoặc cung cấp LinkRelationProvider phù hợp.

## 8. Chọn relation nào cho một use case?

Có thể dùng bảng quyết định sau khi thiết kế link:

| Câu hỏi | Relation nên cân nhắc |
|---|---|
| Link trỏ đến chính tài nguyên này? | self |
| Link dẫn đến tập hợp liên quan? | collection |
| Link dẫn đến một phần tử của tập hợp? | item |
| Link dẫn đến phần tiếp theo của chuỗi? | next |
| Link dẫn đến phần trước? | prev |
| Link dẫn đến profile mô tả ngữ nghĩa representation? | profile |
| Link dẫn đến tài liệu mô tả ngữ cảnh? | describedby |
| Link dẫn đến một tài nguyên nghiệp vụ cụ thể? | Relation tùy chỉnh như customer, invoice |
| Link công bố hành động nghiệp vụ chưa có relation chuẩn phù hợp? | Relation tùy chỉnh như cancel hoặc approve |
| Link dẫn đến form tạo tài nguyên? | create-form |

Ví dụ một đơn hàng có thể dùng:

~~~java
Link self = Link.of(
    "/orders/ORD-42",
    IanaLinkRelations.SELF
);

Link customer = Link.of(
    "/customers/CUS-7",
    LinkRelation.of("customer")
);

Link invoice = Link.of(
    "/invoices/INV-9",
    LinkRelation.of("invoice")
);
~~~

self dùng relation chuẩn vì ý nghĩa phổ quát. customer và invoice là quan hệ nghiệp vụ của API nên được định nghĩa rõ như relation tùy chỉnh.

## 9. Kiểm thử relation và so sánh relation

Kiểm thử nên xác nhận cả giá trị relation trong model và JSON mà client nhận được.

Kiểm tra LinkRelation:

~~~java
LinkRelation customCustomer = LinkRelation.of("customer");

assertThat(customCustomer.isSameAs(LinkRelation.of("customer"))).isTrue();
assertThat(IanaLinkRelations.isIanaRel(IanaLinkRelations.SELF)).isTrue();
assertThat(IanaLinkRelations.isIanaRel(customCustomer)).isFalse();
~~~

Kiểm tra Link được tạo đúng relation:

~~~java
Link customer = Link.of(
    "/customers/CUS-7",
    LinkRelation.of("customer")
);

assertThat(customer.getRel().isSameAs(LinkRelation.of("customer"))).isTrue();
assertThat(customer.getHref()).isEqualTo("/customers/CUS-7");
~~~

Kiểm tra HAL JSON qua MockMvc:

~~~java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.customer.href").exists())
    .andExpect(jsonPath("$._links.invoice.href").exists());
~~~

Một test khác nên xác nhận link cancel chỉ xuất hiện khi trạng thái đơn hàng cho phép. Ngoài việc kiểm tra href, hãy xác nhận relation có tên đúng, bởi client thường tìm link theo relation thay vì theo vị trí của link trong JSON.

## 10. Những lỗi thường gặp khi chọn relation

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng relation chuẩn gần giống nhưng sai ngữ nghĩa | Client hiểu sai mối quan hệ | Đọc định nghĩa registry IANA trước khi chọn |
| Dùng custom relation cho ý nghĩa đã có relation chuẩn phù hợp | Các client tổng quát khó nhận biết relation | Ưu tiên relation chuẩn khi semantics trùng khớp |
| Dùng related cho mọi quan hệ | Mất thông tin nghiệp vụ cụ thể | Dùng relation như customer hoặc invoice khi phù hợp |
| Dùng self cho link đến tài nguyên khác | Client hiểu nhầm đích là tài nguyên hiện tại | Chọn relation đúng với quan hệ |
| Nhầm LinkRelation với LinkRelationProvider | Đặt logic tìm relation sai lớp | Phân biệt giá trị relation và cơ chế tra cứu relation theo type |
| So sánh bằng class triển khai cụ thể | Code phụ thuộc implementation | Dùng LinkRelation.isSameAs(...) |
| Nghĩ custom relation là IANA vì isSameAs trả true | Nhầm lẫn giữa so sánh giá trị và registry | Dùng IanaLinkRelations.isIanaRel(...) để kiểm tra chuẩn |
| Đổi relation đã công bố mà không có chuyển tiếp | Client cũ không tìm thấy link | Quản lý relation như hợp đồng API và có kế hoạch deprecation |

## 11. Quy trình thiết kế và so sánh relation

Khi thêm link vào API Spring HATEOAS, hãy thực hiện theo trình tự:

1. Xác định chính xác quan hệ giữa tài nguyên hiện tại và tài nguyên đích.
2. Tìm relation chuẩn IANA có ngữ nghĩa phù hợp.
3. Nếu không có relation chuẩn thích hợp, định nghĩa custom relation theo ngôn ngữ nghiệp vụ.
4. Dùng IanaLinkRelations cho giá trị chuẩn và LinkRelation.of(...) cho giá trị tùy chỉnh.
5. Dùng isSameAs(...) khi cần so sánh các LinkRelation độc lập implementation.
6. Dùng IanaLinkRelations.isIanaRel(...) khi cần xác định relation có thuộc registry IANA hay không.
7. Đặt tên relation ổn định, tài liệu hóa và kiểm thử trong response HAL.
8. Nếu relation thay đổi, xử lý như một thay đổi hợp đồng API và có lộ trình chuyển tiếp.

Relation là phần ngữ nghĩa của hypermedia. Chọn đúng relation giúp client hiểu mối quan hệ mà server công bố, trong khi href giữ vai trò cung cấp đích điều hướng. Spring HATEOAS hỗ trợ cả relation chuẩn và tùy chỉnh, đồng thời cung cấp abstraction LinkRelation để so sánh và thao tác nhất quán. Khi relation được thiết kế rõ ràng và ổn định, API có thể thay đổi cấu trúc URI mà vẫn duy trì khả năng khám phá cho client.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [LinkRelation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [LinkRelationProvider API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/LinkRelationProvider.html)
- [IANA Link Relation Types Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [Web Linking – RFC 8288](https://www.rfc-editor.org/rfc/rfc8288)

