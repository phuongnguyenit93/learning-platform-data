# Tài liệu link relation

Một API hypermedia không chỉ cần trả về URI để client gọi tiếp. Client còn cần hiểu link đó biểu thị quan hệ gì với resource hiện tại. Relation như `self`, `next`, `collection` hoặc `help` mang ý nghĩa điều hướng; nếu API tự định nghĩa relation như `approval` hoặc `shipment-events`, ý nghĩa của chúng phải được mô tả ổn định để client có thể tích hợp mà không phải đoán từ tên path.

Spring HATEOAS cung cấp `LinkRelation`, các relation chuẩn IANA qua `IanaLinkRelations`, và cơ chế cấu hình relation cho domain type bằng `@Relation` cùng `LinkRelationProvider`. Với HAL, `CurieProvider` cho phép biểu diễn extension relation URI dưới dạng CURIE ngắn gọn. Các thành phần này giúp giữ tên relation nhất quán trong representation; phần tài liệu công khai cần mô tả rõ quan hệ giữa resource nguồn và resource đích, điều kiện xuất hiện, semantics và cách client sử dụng.

Bài học này tập trung vào cách tài liệu hóa relation chuẩn và relation mở rộng, chọn relation đúng, định nghĩa URI relation ổn định, và cấu hình Spring HATEOAS để công bố các relation đó trong HAL.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích relation mô tả mối quan hệ giữa link context và link target.
- Phân biệt relation type với URI đích, media type và HTTP method.
- Tra cứu và sử dụng relation chuẩn từ IANA.
- Định nghĩa extension relation bằng URI do ứng dụng kiểm soát.
- Viết tài liệu semantics cho relation để client có thể tích hợp.
- Dùng `LinkRelation` và `IanaLinkRelations` trong Spring HATEOAS.
- Cấu hình tên item và collection relation bằng `@Relation`.
- Dùng `LinkRelationProvider` để lấy relation theo domain type.
- Dùng CURIE trong HAL để rút gọn extension relation URI.
- Kiểm thử relation được serialize đúng trong representation.

## Link relation là gì?

Một link là kết nối có kiểu giữa hai resource. Nó có:

- **Link context:** resource mà representation hiện tại mô tả.
- **Link relation type:** ý nghĩa của quan hệ từ context tới target.
- **Link target:** URI hoặc URI template của resource được liên kết.
- **Target attributes:** metadata tùy chọn như media type, title hoặc chỉ báo template.

Ví dụ, representation của đơn hàng có link:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/customers/7"
    },
    "next": {
      "href": "/orders?page=1"
    }
  }
}
```

Ở đây, context là representation của đơn hàng. Relation `self` chỉ tới chính resource đó; relation `customer` chỉ tới resource khách hàng có quan hệ với đơn hàng; relation `next` chỉ tới trang tiếp theo trong một luồng điều hướng.

Relation trả lời câu hỏi: *resource đích có quan hệ gì với resource nguồn?* URI đích trả lời câu hỏi: *client đi tới đâu?*

### Relation không phải URI, media type hay HTTP method

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Relation | Ngữ nghĩa của kết nối | `customer`, `next`, `approval` |
| Href | Địa chỉ của resource đích | `/customers/7` |
| Media type | Định dạng representation tại đích | `application/hal+json` |
| HTTP method | Phương thức dùng trong request | `GET`, `POST`, `PATCH` |
| Affordance | Mô tả thao tác có thể thực hiện trên link | `POST` với input schema |

Relation `approval` không tự nói rằng client phải gửi `POST`, cũng không mô tả body cần gửi. Nếu cần mô tả method, payload hoặc form, hãy dùng affordance và một media type hỗ trợ biểu diễn affordance như HAL-FORMS. Tài liệu relation nên giải thích ngữ nghĩa của liên kết; tài liệu affordance hoặc hợp đồng thao tác mô tả cách gọi.

Relation cũng không phải media type của response. Ví dụ, `customer` có thể trỏ tới một representation HAL hoặc JSON khác mà vẫn giữ cùng ngữ nghĩa relation.

## Vì sao phải tài liệu hóa relation?

Nếu server trả một link tên `approval`, client cần biết:

- Link này chỉ tới quy trình phê duyệt, trạng thái phê duyệt hay tài nguyên đại diện cho người phê duyệt?
- Quan hệ được nhìn từ đơn hàng sang yêu cầu phê duyệt hay ngược lại?
- Link xuất hiện khi nào và có thể vắng mặt trong trường hợp nào?
- Một đơn hàng có thể có một hay nhiều link `approval`?
- Client được phép làm gì với resource đích?
- Có yêu cầu quyền, trạng thái hoặc điều kiện nghiệp vụ nào không?
- Nếu semantics thay đổi, client có thể tìm tài liệu phiên bản mới ở đâu?

Nếu chỉ dựa vào tên relation hoặc URI, các client có thể diễn giải khác nhau. Một tài liệu relation tốt tạo ra vocabulary chung giữa server, client, đội tích hợp và đội vận hành.

Tài liệu relation cũng hỗ trợ tiến hóa API. Server có thể đổi URI đích, chuyển resource sang controller khác hoặc thay đổi cấu trúc representation mà client vẫn dựa trên relation để tìm đúng khả năng. Khi semantics của relation thực sự thay đổi, đó là thay đổi hợp đồng cần được quản lý và thông báo.

## Hai loại relation theo RFC 8288

RFC 8288 chia relation type thành hai nhóm:

| Nhóm | Cách định danh | Khi nào dùng |
|---|---|---|
| Registered relation | Token đã đăng ký trong IANA Link Relations Registry | Khi ngữ nghĩa phù hợp với một relation chuẩn đã tồn tại |
| Extension relation | URI duy nhất do bên định nghĩa kiểm soát | Khi API cần một quan hệ đặc thù chưa có relation chuẩn phù hợp |

Relation type chỉ định nghĩa ngữ nghĩa của chính quan hệ đó. Theo RFC 8288, client không nên suy ra thêm ngữ nghĩa nghiệp vụ chỉ từ việc một relation khác có hoặc không xuất hiện, hoặc chỉ từ số lượng link cùng relation. Ví dụ, việc có hai link `item` không tự nói rằng hai item có thứ tự ưu tiên; nếu thứ tự quan trọng, API phải mô tả điều đó bằng một hợp đồng riêng.

### Registered relation

Các relation chuẩn được đăng ký trong IANA Link Relations Registry. Ví dụ:

| Relation | Ý nghĩa khái quát |
|---|---|
| `self` | Resource hiện tại |
| `item` | Một item thuộc collection |
| `collection` | Collection resource của context |
| `next` | Resource tiếp theo trong chuỗi |
| `prev` | Resource trước đó |
| `first`, `last` | Phần tử đầu hoặc cuối của một chuỗi/collection |
| `describedby` | Tài nguyên cung cấp mô tả cho context |
| `help` | Tài nguyên cung cấp trợ giúp cho context |
| `profile` | Profile mô tả semantics hoặc cấu trúc của resource |
| `successor-version` | Phiên bản kế tiếp của resource |

Danh sách trên chỉ là ví dụ, không phải toàn bộ registry. Trước khi định nghĩa relation mới, hãy tra cứu registry để tránh tạo một relation trùng ngữ nghĩa với relation đã được chuẩn hóa.

Trong Spring HATEOAS, dùng `IanaLinkRelations` thay vì tự gõ chuỗi:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("/orders/42", IanaLinkRelations.SELF);
Link collection = Link.of(
    "/orders",
    IanaLinkRelations.COLLECTION
);
Link documentation = Link.of(
    "https://api.example.com/docs/orders",
    IanaLinkRelations.DESCRIBED_BY
);
```

Có thể kiểm tra một relation có thuộc nhóm IANA hay không:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.LinkRelation;

LinkRelation relation = IanaLinkRelations.HELP;
boolean registered = IanaLinkRelations.isIanaRel(relation);
```

Registered relation name được so sánh không phân biệt chữ hoa/chữ thường theo RFC 8288, nhưng khi phát ra representation nên dùng dạng chuẩn chữ thường như trong IANA registry.

Không tạo URI tự chế cho relation IANA. Ví dụ, `https://api.example.com/rels/self` không tương đương với registered relation `self`. Nếu ngữ nghĩa đã có trong registry, hãy dùng token chuẩn để client có thể nhận diện liên thông giữa các API.

Nếu một relation có ngữ nghĩa tổng quát, hữu ích cho nhiều hệ thống và cần được dùng liên thông rộng rãi, tổ chức có thể đề xuất đăng ký relation mới với IANA. Yêu cầu đăng ký cần có tên relation, mô tả ngắn bằng tiếng Anh nêu quan hệ giữa context và target, cùng tài liệu tham chiếu ổn định, công khai. Thủ tục đăng ký theo RFC 8288 yêu cầu xem xét chuyên gia. Với relation chỉ phục vụ một API hoặc một domain cụ thể, extension relation URI thường phù hợp hơn.

### Extension relation

Khi không có relation chuẩn phù hợp, ứng dụng có thể định nghĩa extension relation. RFC 8288 yêu cầu extension relation là URI duy nhất. URI nên thuộc quyền kiểm soát của tổ chức định nghĩa relation hoặc được tổ chức đó ủy quyền.

Ví dụ, một API quản lý đơn hàng định nghĩa relation phê duyệt:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link approval = Link.of(
    "/orders/42/approval",
    LinkRelation.of("https://api.example.com/rels/approval")
);
```

Trong ví dụ, URI relation là:

```text
https://api.example.com/rels/approval
```

URI này định danh semantics của relation. Href `/orders/42/approval` là đích của một link cụ thể. Hai URI có vai trò khác nhau và có thể thay đổi theo những quy tắc khác nhau.

Extension relation URI có thể trỏ tới một trang tài liệu giải thích semantics. RFC 8288 khuyến nghị client không tự động truy cập URI relation chỉ để đọc tài liệu, nhằm tránh tạo tải không cần thiết lên server. Client nên biết relation qua hợp đồng đã được công bố hoặc tài liệu API; con người có thể mở URI đó để tìm hiểu semantics.

Nên dùng URI relation ổn định, chữ thường và thuộc domain do tổ chức kiểm soát. Tránh:

- Dùng URL của môi trường development hoặc staging.
- Dùng URL chứa phiên bản triển khai tạm thời hoặc ID cụ thể của một resource.
- Dùng tên class Java hoặc tên method controller làm định danh relation.
- Dùng chuỗi ngắn như `approve` trong serialization không hỗ trợ cơ chế namespace/compact URI.
- Thay đổi URI relation chỉ vì URI đích của resource thay đổi.

## Cấu trúc một tài liệu relation

Một tài liệu relation cần mô tả quan hệ giữa context và target, không chỉ lặp lại tên relation. Có thể chuẩn hóa nội dung tài liệu theo mẫu:

| Trường | Nội dung cần ghi |
|---|---|
| Relation name | Token IANA hoặc tên CURIE/extension relation |
| Relation URI | URI đầy đủ định danh relation nếu là extension relation |
| Summary | Một câu mô tả ngắn quan hệ |
| Context | Resource nào có thể phát ra link này |
| Target | Resource đích đại diện cho điều gì |
| Direction | Ý nghĩa được diễn đạt từ context tới target |
| Availability | Điều kiện link xuất hiện hoặc bị lược bỏ |
| Cardinality | Có thể có một hay nhiều link cùng relation |
| Target representation | Media type hoặc profile liên quan nếu có |
| Operations | HTTP method, affordance hoặc thao tác được hỗ trợ nếu thuộc hợp đồng |
| Authorization | Điều kiện quyền cần biết ở mức contract |
| Failure behavior | Các trạng thái lỗi quan trọng khi truy cập target |
| Evolution | Chính sách tương thích và cách thông báo thay đổi |
| Examples | Ví dụ representation thực tế có link relation |

### Ví dụ tài liệu cho relation approval

```markdown
# approval

**URI:** https://api.example.com/rels/approval

**Summary:** Liên kết tới quy trình phê duyệt của đơn hàng.

**Context:** Representation của một đơn hàng.

**Target:** Resource mô tả yêu cầu phê duyệt và trạng thái xử lý.

**Availability:** Link xuất hiện khi đơn hàng đang chờ phê duyệt.
Link có thể vắng mặt khi đơn hàng đã bị hủy hoặc không cần phê duyệt.

**Cardinality:** Tối đa một link approval trên một đơn hàng.

**Authorization:** Client phải có quyền đọc quy trình phê duyệt.

**Operations:** Representation đích công bố các affordance được phép
để gửi quyết định. Client không suy ra HTTP method từ tên relation.

**Evolution:** URI relation giữ ổn định khi URI resource đích thay đổi.
Thay đổi semantics cần được công bố trong tài liệu phiên bản API.
```

Ví dụ trên mô tả cả điều kiện xuất hiện và semantics của target. Tài liệu không nên cam kết rằng mọi client đều có quyền thực hiện phê duyệt chỉ vì link xuất hiện; quyền thực tế vẫn do server kiểm tra ở request thực thi.

## Dùng LinkRelation trong Spring HATEOAS

`LinkRelation` là abstraction để làm việc với relation dưới dạng giá trị chuỗi. Nó có thể đại diện cho relation IANA hoặc custom relation:

```java
import org.springframework.hateoas.LinkRelation;

LinkRelation standard = LinkRelation.of("self");
LinkRelation custom = LinkRelation.of(
    "https://api.example.com/rels/approval");
```

Các phương thức hữu ích:

| API | Mục đích |
|---|---|
| `LinkRelation.of(String)` | Tạo một relation từ chuỗi |
| `LinkRelation.manyOf(String...)` | Tạo tập relation từ nhiều chuỗi |
| `value()` | Lấy giá trị chuỗi của relation |
| `isSameAs(LinkRelation)` | So sánh giá trị relation giữa các implementation |

Ví dụ tạo link và kiểm tra relation:

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

Link approval = Link.of(
    "/orders/42/approval",
    LinkRelation.of("https://api.example.com/rels/approval"));

boolean isApproval = approval.hasRel(
    LinkRelation.of("https://api.example.com/rels/approval"));
```

Không nên để client phụ thuộc vào cách viết hoa của extension relation. RFC 8288 quy định cách so sánh relation URI theo quy tắc của URI; dùng một cách viết chuẩn, nhất quán và chữ thường để tránh sai khác giữa các thành phần.

## Đặt tên relation cho item và collection bằng @Relation

Spring HATEOAS thường cần xác định relation khi tạo link hoặc khi serialize các phần tử trong HAL `_embedded`. `LinkRelationProvider` cung cấp relation cho item resource và collection resource dựa trên domain type.

Theo cấu hình mặc định, relation item được suy ra từ tên class đã chuyển về dạng chữ thường ở đầu. Relation collection mặc định có thể dùng tên item cộng `List`; nếu thư viện Evo Inflector có trong classpath, collection relation có thể được tạo bằng thuật toán số nhiều tiếng Anh.

Đối với API công khai, nên khai báo relation rõ ràng bằng `@Relation` thay vì để tên class Java vô tình trở thành contract:

```java
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;
import org.springframework.hateoas.server.core.Relation;

@Relation(
    itemRelation = "order",
    collectionRelation = "orders"
)
class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;

    OrderModel(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
```

Hai giá trị trong annotation có vai trò riêng:

- `itemRelation`: relation dùng khi trỏ tới một đơn hàng.
- `collectionRelation`: relation dùng khi trỏ tới collection đơn hàng hoặc đặt các phần tử đơn hàng trong `_embedded`.

`value` là alias của `itemRelation`. Khi cần mô tả cả item và collection, nên khai báo tường minh hai thuộc tính để người đọc hiểu rõ contract.

### Tra cứu relation bằng LinkRelationProvider

Khi cần dùng relation được cấu hình cho một kiểu, inject `LinkRelationProvider`:

```java
import org.springframework.hateoas.LinkRelation;
import org.springframework.hateoas.server.LinkRelationProvider;
import org.springframework.stereotype.Component;

@Component
class OrderRelationCatalog {

    private final LinkRelationProvider relations;

    OrderRelationCatalog(LinkRelationProvider relations) {
        this.relations = relations;
    }

    LinkRelation itemRelation() {
        return relations.getItemResourceRelFor(OrderModel.class);
    }

    LinkRelation collectionRelation() {
        return relations.getCollectionResourceRelFor(OrderModel.class);
    }
}
```

`LinkRelationProvider` là SPI của Spring HATEOAS. Khi dùng `@EnableHypermediaSupport`, Spring HATEOAS tự expose một provider làm Spring bean. Provider mặc định hỗ trợ quy ước tên; provider annotation đọc `@Relation`; provider delegating chọn implementation phù hợp. Ứng dụng có thể đăng ký provider tùy chỉnh nếu quy tắc relation của domain phức tạp hơn.

Không cần tự triển khai provider chỉ để đặt tên một vài relation. `@Relation` thường đủ cho item và collection rel. Chỉ viết custom provider khi có quy tắc ánh xạ type sang relation dùng chung và cần được tái sử dụng trên nhiều representation.

### @Relation không thay thế tài liệu semantics

`@Relation` điều khiển tên relation được dùng trong representation. Annotation không tự định nghĩa:

- Quan hệ nghiệp vụ giữa context và target.
- Điều kiện link được thêm vào representation.
- Quyền truy cập target.
- HTTP method hoặc input schema.
- Tài liệu giải thích semantics của relation.

Những thông tin đó vẫn phải được ghi trong tài liệu relation và được triển khai nhất quán trong controller, assembler hoặc `RepresentationModelProcessor`.

## Dùng CURIE để rút gọn extension relation trong HAL

Extension relation dùng URI đầy đủ. Khi API có nhiều relation riêng, lặp lại URI dài trong các key của HAL có thể làm representation khó đọc. HAL hỗ trợ CURIE (Compact URI) để rút gọn extension relation.

Ví dụ, relation URI:

```text
https://api.example.com/rels/orders
```

có thể được biểu diễn ngắn là:

```text
ex:orders
```

nếu response khai báo prefix `ex` với URI template:

```text
https://api.example.com/rels/{rel}
```

Client có thể đọc link `curies` trong response để giải mã prefix. CURIE chỉ là cách biểu diễn rút gọn relation URI trong HAL; nó không thay đổi semantics của relation.

### Cấu hình DefaultCurieProvider

Spring HATEOAS cung cấp `CurieProvider` và `DefaultCurieProvider`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
            "ex",
            new UriTemplate("https://api.example.com/rels/{rel}")
        );
    }
}
```

Khi cấu hình này hoạt động, các extension relation phù hợp được serialize bằng prefix `ex:`. Ví dụ, relation collection `orders` lấy từ `LinkRelationProvider` có thể được dùng để tạo link:

Đoạn code dưới đây là phần tiếp nối của component đã inject bean `LinkRelationProvider` ở mục trước; biến `relations` tham chiếu tới bean đó.

```java
LinkRelation collectionRel =
    relations.getCollectionResourceRelFor(OrderModel.class);

// relations là LinkRelationProvider được inject từ Spring.
Link orders = Link.of("/orders", collectionRel);
```

HAL document sẽ có một link `curies` mô tả cách mở rộng prefix:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "curies": {
      "name": "ex",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    },
    "ex:orders": {
      "href": "/orders"
    }
  }
}
```

Client thay phần sau dấu hai chấm vào URI template để nhận relation URI đầy đủ. Trong ví dụ, `ex:orders` tương ứng với `https://api.example.com/rels/orders`. Nếu có nhiều CURIE link, serializer có thể biểu diễn chúng theo dạng phù hợp với số lượng link; ví dụ trên dùng một CURIE duy nhất.

Một application scope chỉ nên khai báo một `CurieProvider`. Nếu có nhiều nhóm relation, có thể dùng một provider có quy ước namespace rõ ràng thay vì khai báo các prefix xung đột.

### CURIE không phải relation IANA

Không thêm prefix CURIE vào registered relation như `self`, `next` hoặc `help`. CURIE được dùng để rút gọn extension relation. Các registered relation vẫn giữ tên chuẩn IANA để client nhận diện đúng semantics.

CURIE cũng là tính năng serialization của HAL. Nếu API phát relation qua HTTP Link header hoặc một media type khác, không được giả định client sẽ hiểu cú pháp CURIE của HAL. Khi cần truyền extension relation URI ở nơi khác, dùng URI đầy đủ theo quy tắc của media type hoặc giao thức tương ứng.

## Dùng describedby để trỏ tới tài liệu của resource

Nếu cần công bố một trang mô tả resource hiện tại, relation chuẩn `describedby` thường phù hợp:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link documentation = Link.of(
    "https://api.example.com/docs/orders",
    IanaLinkRelations.DESCRIBED_BY
);
```

Relation `describedby` nói rằng target cung cấp thông tin mô tả context. Đây là cách trỏ tới tài liệu về resource hoặc cấu trúc của nó. Nó không tự động thay thế tài liệu cho từng extension relation.

Phân biệt:

- `describedby`: link từ resource tới tài liệu mô tả resource đó.
- Extension relation URI: định danh một loại quan hệ riêng, ví dụ `https://api.example.com/rels/approval`.
- `help`: tài nguyên cung cấp trợ giúp theo ngữ cảnh.
- `profile`: profile mô tả semantics hoặc constraints của resource representation.

Một API có thể công bố cả link `describedby` cho tài liệu API tổng quát và CURIE để định danh extension relation. Tài liệu API tổng quát cần liên kết tới từng trang relation để developer tra cứu.

## Title và tài liệu relation

HAL cho phép thêm thuộc tính `title` vào link object. Spring HATEOAS hỗ trợ cấu hình title qua resource bundle `rest-messages` với key:

```properties
_links.approval.title=Open approval workflow
_links.customer.title=View customer
```

Khi serialize HAL, title có thể giúp giao diện hiển thị nhãn thân thiện:

```json
{
  "_links": {
    "approval": {
      "href": "/orders/42/approval",
      "title": "Open approval workflow"
    }
  }
}
```

Title là nhãn hiển thị cho người dùng, không phải định nghĩa đầy đủ semantics. Không nên nhồi điều kiện nghiệp vụ, HTTP method hoặc hướng dẫn dài vào title. Hãy giữ title ngắn, có thể quốc tế hóa và cung cấp tài liệu relation riêng cho hợp đồng tích hợp.

## Quy trình thiết kế và công bố relation

Khi thêm một link relation mới, có thể thực hiện theo thứ tự:

1. Xác định rõ context và target. Viết câu mô tả theo dạng “context có target với quan hệ ...”.
2. Tra cứu IANA registry để tìm relation chuẩn có cùng semantics.
3. Nếu không có relation phù hợp, tạo extension relation URI dưới domain do tổ chức kiểm soát.
4. Viết tài liệu relation theo mẫu: ngữ nghĩa, context, target, availability, cardinality, operations và evolution.
5. Khai báo tên item/collection bằng `@Relation` nếu relation được suy ra từ domain type.
6. Cấu hình CURIE nếu API dùng HAL và có nhiều extension relation.
7. Công bố relation trong representation cùng tài liệu tổng quan hoặc `describedby` link.
8. Kiểm thử serialization và kiểm tra tài liệu có khớp với hành vi thực tế.
9. Giữ URI relation ổn định khi URI target hoặc cấu trúc controller thay đổi.

Không tạo relation mới chỉ để phản ánh từng endpoint hoặc từng method. Relation nên mô tả một ngữ nghĩa có giá trị cho client, không phải tên nội bộ của route.

## Kiểm thử relation trong HAL

Kiểm thử cần xác nhận relation name đúng, href đúng và CURIE được công bố khi dùng extension relation. Ví dụ với MockMvc:

```java
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
class OrderRelationDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesNamespacedCollectionRelation() throws Exception {
        mockMvc.perform(get("/orders/42")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href")
                .value("/orders/42"))
            .andExpect(jsonPath("$._links['ex:orders'].href")
                .value("/orders"))
            .andExpect(jsonPath("$._links.curies.name")
                .value("ex"))
            .andExpect(jsonPath("$._links.curies.href")
                .value("https://api.example.com/rels/{rel}"));
    }
}
```

Nếu API không dùng CURIE và serialize extension relation dưới dạng URI đầy đủ, assertion cần kiểm tra key relation URI đầy đủ tương ứng. Không viết test phụ thuộc vào thứ tự link vì thứ tự link không phải semantics của relation.

Mẫu kiểm thử giả định endpoint và cấu hình ứng dụng trả về representation có link collection được tạo từ `OrderModel`. Nếu đặt test ở package khác với model, hãy import kiểu `OrderModel`.

Có thể kiểm thử riêng relation provider:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.server.LinkRelationProvider;

@SpringBootTest
class OrderLinkRelationProviderTest {

    @Autowired
    LinkRelationProvider relations;

    @Test
    void exposesExplicitItemAndCollectionRelations() {
        assertThat(relations.getItemResourceRelFor(OrderModel.class).value())
            .isEqualTo("order");

        assertThat(relations.getCollectionResourceRelFor(OrderModel.class).value())
            .isEqualTo("orders");
    }
}
```

Ngoài serialization, cần review tài liệu relation:

- URI relation có ổn định và thuộc quyền kiểm soát của tổ chức không?
- Tài liệu có mô tả context và target theo đúng hướng không?
- Điều kiện xuất hiện của link có khớp code không?
- Tài liệu có hứa về cardinality hoặc thao tác mà server không bảo đảm không?
- Nếu client dùng relation để điều hướng, target có thực sự hỗ trợ semantics đã mô tả không?
- Có vô tình thay relation chuẩn bằng custom relation không cần thiết không?

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng tên relation như tên endpoint | Client phụ thuộc vào cấu trúc route | Đặt tên theo quan hệ ngữ nghĩa giữa context và target |
| Tự tạo relation đã có trong IANA | Client phải xử lý hai tên cho cùng một ý nghĩa | Tra cứu registry và dùng `IanaLinkRelations` |
| Dùng chuỗi ngắn cho extension rel trong giao thức không hỗ trợ namespace | Relation không có định danh duy nhất | Dùng URI extension relation đầy đủ |
| Dùng URI relation từ domain tạm thời | Contract bị phá khi đổi môi trường hoặc domain | Dùng URI ổn định do tổ chức kiểm soát |
| Nghĩ relation mô tả HTTP method | Client gọi sai thao tác hoặc payload | Dùng affordance và tài liệu thao tác để mô tả method/input |
| Nghĩ media type là relation | Client nhầm định dạng với ngữ nghĩa kết nối | Tài liệu riêng relation, href và media type |
| Chỉ khai báo `@Relation` rồi cho rằng đã có tài liệu | Client biết tên rel nhưng không biết semantics | Viết tài liệu relation và công bố URI tài liệu |
| Dựa vào tên class mặc định làm contract lâu dài | Đổi class có thể đổi rel | Khai báo `itemRelation` và `collectionRelation` tường minh |
| Thêm CURIE cho relation IANA | Client không nhận diện token chuẩn | Chỉ dùng CURIE cho extension relation |
| Dùng CURIE ngoài HAL mà không định nghĩa serialization | Client không giải được prefix | Dùng URI đầy đủ ngoài HAL |
| Đổi URI target rồi đổi luôn URI relation | Client cũ mất vocabulary đã biết | Giữ relation URI ổn định; chỉ thay href khi semantics không đổi |
| Dùng title thay tài liệu semantics | Client không thể tích hợp đáng tin cậy | Giữ title ngắn và cung cấp tài liệu relation đầy đủ |

## Ghi nhớ

Link relation mô tả mối quan hệ giữa resource context và resource target; nó không phải URI đích, media type hay HTTP method. Ưu tiên relation chuẩn từ IANA và dùng `IanaLinkRelations` trong Spring HATEOAS. Khi cần relation riêng, định danh nó bằng URI ổn định do tổ chức kiểm soát và viết tài liệu mô tả semantics, điều kiện xuất hiện, cardinality và cách client sử dụng. `@Relation` cùng `LinkRelationProvider` giúp quản lý tên item/collection; `CurieProvider` giúp rút gọn extension relation trong HAL. Hãy kiểm thử representation và giữ relation URI ổn định khi API thay đổi.

## Tài liệu tham khảo

- [Spring HATEOAS – Link relations](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.link-relations)
- [Spring HATEOAS – LinkRelation API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [Spring HATEOAS – IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Spring HATEOAS – LinkRelationProvider API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/LinkRelationProvider.html)
- [Spring HATEOAS – Relation annotation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/Relation.html)
- [Spring HATEOAS – CurieProvider API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/CurieProvider.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [IANA – Link Relation Types Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
