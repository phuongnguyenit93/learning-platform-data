# Đánh đổi giữa nhúng dữ liệu, lần theo liên kết và số lượt HTTP

## 1. Hai cách biểu diễn quan hệ trong REST

Một resource thường liên quan đến resource khác. Ví dụ Person có Address, Order có Customer, Product có Category. Khi client đọc một Person, API có thể cung cấp dữ liệu Address ngay trong response hoặc cung cấp một link để client lấy Address riêng.

Hai lựa chọn chính:

- **Nhúng dữ liệu (embedding):** response của resource cha chứa thêm dữ liệu của resource liên quan, thường trong HAL dưới _embedded hoặc như một object property trong representation.
- **Lần theo liên kết (link traversal):** response cha chỉ cung cấp link trong _links; client gửi request tiếp theo đến URI đó để lấy resource liên quan.

Ví dụ nhúng:

~~~~json
{
  "id": 42,
  "name": "Alice",
  "address": {
    "city": "Hanoi",
    "country": "Vietnam"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~~

Ví dụ dùng link:

~~~~json
{
  "id": 42,
  "name": "Alice",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~~

Với cách thứ hai, client gọi thêm GET tới link address khi thực sự cần dữ liệu đó.

Không có cách nào tốt nhất cho mọi quan hệ. Quyết định phụ thuộc tần suất client cần dữ liệu liên quan, kích thước dữ liệu, độ ổn định, cache, quyền truy cập và chi phí của một round trip HTTP.

## 2. HAL và cách Spring Data REST biểu diễn association

Spring Data REST mặc định dùng HAL để render response. HAL đặt link trong thuộc tính _links, với key là relation name. Collection resource có thể chứa item representation trong _embedded.

Ví dụ collection:

~~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    },
    "next": {
      "href": "http://localhost:8080/people?page=1"
    }
  },
  "_embedded": {
    "people": [
      {
        "name": "Alice",
        "_links": {
          "self": {
            "href": "http://localhost:8080/people/42"
          }
        }
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 100,
    "totalPages": 5,
    "number": 0
  }
}
~~~~

Trong Spring Data REST, một association trỏ đến domain type có repository riêng thường được biểu diễn bằng link tới association resource. Client có thể theo link để lấy resource liên quan.

Nếu object liên quan không có repository riêng, Spring Data REST có thể render các field của object đó inline trong representation của parent. Hành vi cụ thể phụ thuộc domain mapping, repository exposure và projection đang dùng.

Do đó, nhúng hay link không chỉ là lựa chọn của frontend. Cấu trúc repository và projection của Spring Data REST cũng ảnh hưởng đến representation được tạo.

## 3. Ưu điểm của nhúng dữ liệu

Nhúng dữ liệu giúp client nhận được một nhóm thông tin trong một response.

Phù hợp khi:

- Dữ liệu liên quan nhỏ và hầu như luôn được hiển thị cùng resource cha.
- Client cần dữ liệu ngay trên màn hình danh sách.
- Quan hệ có ý nghĩa như một phần của representation cha.
- Giảm số request là yêu cầu quan trọng, đặc biệt trên mạng có latency cao.
- Dữ liệu liên quan không cần được cache hoặc refresh độc lập.

Ví dụ danh sách đơn hàng thường hiển thị tên khách hàng và tổng tiền. Nếu mỗi item embed một CustomerSummary nhỏ, frontend không phải gửi thêm GET cho từng khách hàng chỉ để hiển thị tên.

Một response có thể chứa:

~~~~json
{
  "id": 9001,
  "total": 125.50,
  "customer": {
    "id": 42,
    "displayName": "Alice"
  }
}
~~~~

Client có thể render đơn hàng ngay mà không cần gọi customer resource riêng.

Nhúng dữ liệu cũng giúp giảm độ phức tạp ở client nếu các field cần thiết luôn xuất hiện cùng nhau và không có nhu cầu điều hướng sâu.

## 4. Nhược điểm của nhúng dữ liệu

Nhúng quá nhiều dữ liệu làm response lớn và gắn chặt representation của resource cha với cấu trúc của resource con.

Các chi phí thường gặp:

- **Payload lớn:** dữ liệu con có thể chiếm phần lớn response dù màn hình chỉ cần một vài field.
- **Overfetching:** client nhận dữ liệu không sử dụng.
- **Lặp dữ liệu:** cùng một Customer xuất hiện trong nhiều Order và bị truyền lặp lại.
- **Cache khó hơn:** thay đổi ở resource con có thể làm representation của nhiều resource cha trở nên cũ.
- **Coupling:** thay đổi cấu trúc object con có thể ảnh hưởng mọi client dùng representation cha.
- **Phân quyền phức tạp:** dữ liệu được embed phải được kiểm tra quyền ngay trong response của parent.
- **Response khó phân trang:** một page gồm nhiều parent, mỗi parent lại embed collection lớn có thể tạo payload rất lớn.

Ví dụ một Order embed toàn bộ Customer, Address, PaymentHistory và hàng trăm OrderLine có thể khiến request lấy chi tiết đơn hàng trở nên nặng dù frontend chỉ cần thông tin tổng quan.

Không nên embed toàn bộ object graph chỉ vì ORM có thể truy cập các association đó.

## 5. Ưu điểm của link traversal

Link traversal cho phép client chỉ tải resource liên quan khi cần.

Phù hợp khi:

- Resource con lớn hoặc có nhiều field.
- Không phải client nào cũng cần dữ liệu con.
- Dữ liệu con được dùng ở nhiều màn hình hoặc nhiều workflow.
- Resource con có vòng đời và cache riêng.
- Client cần quyền truy cập khác nhau cho từng resource.
- Quan hệ có thể được điều hướng theo nhiều hướng hoặc thay đổi độc lập.

Ví dụ Person chỉ trả link address:

~~~~json
{
  "id": 42,
  "name": "Alice",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~~

Màn hình chỉ cần tên Person sẽ dừng sau request đầu tiên. Màn hình chi tiết địa chỉ sẽ theo link address và tải resource đó.

Link cũng giúp client khám phá API từ relation name thay vì tự ghép URL theo quy ước nội bộ. Đây là một lợi ích của hypermedia: server công bố nơi client có thể đi tiếp.

## 6. Nhược điểm của link traversal

Mỗi lần theo link thường cần một HTTP request riêng. Điều này làm tăng round trip và có thể khiến UI chậm khi client phải gọi tuần tự nhiều resource.

Ví dụ:

1. GET /orders/9001.
2. GET link customer.
3. GET link address của customer.
4. GET link payment.
5. GET link items.

Nếu mỗi request phải chờ response trước để biết link tiếp theo, tổng latency có thể gần bằng tổng thời gian của các request cộng lại. Trên mạng di động hoặc qua nhiều gateway, chi phí round trip có thể lớn hơn chi phí xử lý JSON.

Link traversal cũng làm client phức tạp hơn:

- Phải đọc relation và theo URI được trả về.
- Phải xử lý request lỗi ở từng bước.
- Phải quản lý loading state cho từng phần dữ liệu.
- Có thể cần cache và deduplicate các request tới cùng resource.
- Cần xử lý authorization riêng cho từng resource được theo link.

HTTP/2 hoặc HTTP/3 có thể giảm một số chi phí kết nối và cho phép multiplexing, nhưng không xóa latency mạng, chi phí xử lý server hoặc số lần client phải chờ dữ liệu.

## 7. Đếm round trip thay vì chỉ đếm số resource

Số resource trong response không bằng số round trip HTTP. Một response embed nhiều object có thể chỉ cần một request, trong khi cùng dữ liệu đó biểu diễn bằng link có thể cần nhiều request.

Ví dụ một trang có 20 Order và mỗi Order cần Customer:

**Embed Customer summary**

- 1 GET lấy collection Order.
- Mỗi Order chứa CustomerSummary.
- Tổng cộng 1 round trip cho phần dữ liệu này.

**Link Customer riêng**

- 1 GET lấy collection Order.
- Tối đa 20 GET lấy Customer nếu client tải tuần tự hoặc không deduplicate.
- Có thể ít hơn nếu nhiều Order cùng tham chiếu một Customer và client dùng cache.

Không nên giả định client sẽ gọi đúng N request. Nếu nhiều parent dùng chung một resource con, client có thể tải một lần và tái sử dụng kết quả. Nếu server cung cấp batch endpoint hoặc projection phù hợp, số request cũng có thể giảm.

Khi thiết kế API, hãy mô hình hóa workflow thật: màn hình cần bao nhiêu loại dữ liệu, bao nhiêu item trên một page và bao nhiêu resource con được dùng chung.

## 8. Projection và excerpt trong Spring Data REST

Spring Data REST cung cấp projection để thay đổi view của domain object mà API trả về. Projection có thể chỉ chọn một số field, bỏ field không cần thiết hoặc thêm dữ liệu dẫn xuất.

Ví dụ:

~~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~~

Client có thể yêu cầu projection bằng query parameter:

~~~~http
GET /people/42?projection=personSummary
~~~~

Projection giúp giảm payload và tránh trả toàn bộ domain object. Nó cũng có thể expose association nếu projection khai báo getter tương ứng.

Excerpt là projection tự động áp dụng cho item resources được nhúng trong collection hoặc related resources. Ví dụ:

~~~~java
@RepositoryRestResource(excerptProjection = PersonSummary.class)
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~~

Excerpt projection được dùng làm preview mặc định trong collection. Nó không tự động áp dụng cho single item resource; client cần yêu cầu projection phù hợp khi lấy item.

Cần nhớ projection không tự bảo đảm hiệu năng. Nếu getter trong projection truy cập association lazy, server vẫn có thể phải chạy query để lấy dữ liệu đó. Projection giảm field được serialize nhưng fetch plan và số query vẫn cần được thiết kế riêng.

## 9. Kết hợp embed và link

Không cần chọn một kiểu cho toàn bộ API. Một representation có thể embed summary nhỏ và vẫn cung cấp link tới resource đầy đủ.

Ví dụ Person embed AddressSummary nhưng giữ link address:

~~~~json
{
  "id": 42,
  "name": "Alice",
  "address": {
    "city": "Hanoi",
    "country": "Vietnam"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~~

Client có dữ liệu đủ để hiển thị summary. Khi người dùng mở trang địa chỉ, client theo link để lấy representation đầy đủ.

Đây là cách cân bằng tốt khi một số field được dùng thường xuyên nhưng resource con vẫn cần khả năng điều hướng và quản lý độc lập.

Spring Data REST có thể tạo kiểu representation này bằng projection/excerpt có getter cho association và vẫn cung cấp association link. Cần kiểm tra HAL response thực tế sau khi cấu hình.

## 10. Excerpt projection cho collection resource

Một excerpt projection phù hợp khi collection cần một preview nhỏ của từng item.

Ví dụ:

~~~~java
@Projection(name = "orderListItem", types = Order.class)
public interface OrderListItem {

    String getOrderNumber();

    BigDecimal getTotal();

    CustomerSummary getCustomer();
}

@Projection(name = "customerSummary", types = Customer.class)
public interface CustomerSummary {

    String getDisplayName();
}

@RepositoryRestResource(excerptProjection = OrderListItem.class)
public interface OrderRepository
        extends CrudRepository<Order, Long> {
}
~~~~

Collection có thể hiển thị order number, total và customer display name mà không embed toàn bộ Customer resource.

Khi client mở một Order cụ thể, có thể yêu cầu projection chi tiết riêng hoặc theo link customer. Nhờ vậy, collection response giữ kích thước ổn định hơn khi domain model phát triển.

Hãy xem excerpt là hợp đồng preview của collection. Thay đổi excerpt sau khi API đã phát hành có thể ảnh hưởng client đang dựa vào cấu trúc embedded hiện tại.

## 11. Pagination và collection lớn

Với collection lớn, nên phân trang parent resource trước. Spring Data REST cung cấp các link như self, next và prev cùng metadata page.

Ví dụ:

~~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders?page=0&size=20"
    },
    "next": {
      "href": "http://localhost:8080/orders?page=1&size=20"
    }
  },
  "_embedded": {
    "orders": [
      {
        "orderNumber": "A-1001",
        "total": 125.50
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 1000,
    "totalPages": 50,
    "number": 0
  }
}
~~~~

Nếu mỗi Order embed toàn bộ OrderLine, Customer, Address và Payment, kích thước một page có thể tăng rất nhanh.

Nên dùng excerpt nhỏ cho collection, rồi cung cấp link để client lấy chi tiết khi cần. Với collection con lớn như order lines, hãy cân nhắc resource riêng có pagination thay vì embed toàn bộ.

## 12. Cache và tính mới của dữ liệu

Link và embed có ảnh hưởng khác nhau đến cache.

**Khi embed:**

- Representation cha chứa bản sao dữ liệu con tại thời điểm response được tạo.
- Cache của cha có thể trở nên cũ khi resource con thay đổi.
- Nếu server dùng ETag cho cha, thay đổi dữ liệu embed cần được phản ánh vào validator của representation cha.
- Một resource con được embed ở nhiều parent có thể làm nhiều cache entry bị cũ cùng lúc.

**Khi dùng link:**

- Parent và child có thể có ETag, Last-Modified và cache policy riêng.
- Client có thể revalidate resource con độc lập.
- Một thay đổi ở child không nhất thiết làm representation parent thay đổi nếu parent chỉ chứa link.
- Client cần thực hiện thêm request để lấy dữ liệu mới.

Nếu màn hình cần snapshot nhất quán của parent và child, embedding hoặc một endpoint read model có thể phù hợp hơn. Nếu dữ liệu con thay đổi độc lập và cần cache riêng, link traversal thường thuận tiện hơn.

## 13. Bảo mật và quyền truy cập

Nhúng dữ liệu làm dữ liệu con xuất hiện trong response của parent. Vì vậy, quyền đọc parent không tự động có nghĩa caller được phép xem mọi thuộc tính của child.

Cần kiểm tra:

- Người dùng có quyền xem resource con không?
- Có field nhạy cảm nào bị embed ngoài ý muốn không?
- Projection có vô tình đưa field bị ẩn bởi JsonIgnore trở lại không?
- Link association có cho phép truy cập resource mà caller không được phép đọc không?
- Response collection có làm lộ thông tin tenant khác qua embedded object không?

Link cũng không phải cơ chế authorization. Client biết URI không có nghĩa request GET sẽ được phép. Server vẫn phải kiểm tra quyền ở mỗi resource và mỗi thao tác association.

Không dùng projection hoặc excerpt làm ranh giới bảo mật duy nhất. Authorization phải được áp dụng ở server cho resource và field phù hợp.

## 14. Tác động đến consistency và coupling

Embedding tạo một representation tổng hợp. Dữ liệu con được chụp cùng response của parent, giúp client render một màn hình với ít request hơn. Tuy nhiên, cấu trúc parent phụ thuộc nhiều hơn vào schema con.

Link traversal giữ resource độc lập hơn. Client lấy child tại thời điểm gọi link; dữ liệu có thể mới hơn hoặc khác snapshot đã đọc trước đó ở parent.

Ví dụ client GET Order lúc 10:00, sau đó GET Customer lúc 10:01. Customer có thể đã thay đổi giữa hai request. Nếu Order embed CustomerSummary trong response đầu tiên, client thấy snapshot summary được tạo lúc 10:00.

Không có lựa chọn nào luôn nhất quán hơn. Nếu cần tính nhất quán nghiệp vụ, hãy cung cấp read model/snapshot phù hợp hoặc version metadata; không dựa vào việc số request ít hay nhiều để suy ra consistency.

## 15. Chọn chiến lược theo use case

| Use case | Cách thường phù hợp | Lý do |
|---|---|---|
| Danh sách đơn hàng chỉ cần tên khách hàng | Embed CustomerSummary | Tránh một GET cho mỗi khách hàng |
| Trang chi tiết khách hàng có lịch sử đơn lớn | Link tới orders collection | Dữ liệu lớn và cần pagination |
| Danh sách sản phẩm chỉ cần tên category | Embed category name hoặc summary | Field nhỏ, thường được dùng |
| Trang category cần toàn bộ sản phẩm | Link tới products collection | Collection có thể lớn |
| Dữ liệu audit hoặc payment nhạy cảm | Link có authorization riêng | Quyền truy cập cần tách biệt |
| Address nhỏ và luôn hiển thị cùng Person | Embed Address | Quan hệ nhỏ, thường xuyên cần |
| Customer có profile, orders, payments, contacts | Link và projection theo màn hình | Tránh object graph lớn |
| Collection nhiều parent và child | Excerpt nhỏ + link | Giữ payload và query có kiểm soát |

Đây là nguyên tắc lựa chọn. Hãy đo số request, payload, query count và latency của workflow thực tế trước khi chốt representation.

## 16. Ví dụ so sánh hai workflow

Giả sử trang danh sách Order hiển thị order number, total và tên khách hàng.

### Phương án A — Embed summary

Server trả collection với CustomerSummary trong từng Order. Client gọi một GET cho page và render ngay.

Ưu điểm:

- Ít round trip.
- Không cần logic tải Customer riêng.
- Dễ hiển thị danh sách.

Chi phí:

- Payload lớn hơn một chút.
- Thay đổi CustomerSummary có thể ảnh hưởng representation Order.
- Server cần fetch summary hiệu quả, tránh N+1 database query.

### Phương án B — Link customer

Server trả link customer cho mỗi Order. Client theo link để lấy Customer.

Ưu điểm:

- Customer resource độc lập và có thể cache riêng.
- Client chỉ tải Customer khi thực sự cần.
- Nhiều Order cùng tham chiếu một Customer có thể dùng chung cache.

Chi phí:

- Có thể phát sinh nhiều GET.
- Client cần deduplicate và quản lý loading state.
- Nếu tải tuần tự, latency tổng có thể tăng đáng kể.

### Phương án C — Kết hợp

Server embed displayName và giữ link customer. Danh sách render ngay; khi người dùng mở chi tiết khách hàng, client theo link.

Đây thường là lựa chọn cân bằng khi summary nhỏ được dùng thường xuyên nhưng resource con vẫn cần khả năng truy cập độc lập.

## 17. Đo hiệu năng trước khi quyết định

Nên đo ở cả client và server:

**Phía client**

- Số HTTP request cho một màn hình.
- Tổng round trip và thời gian chờ.
- Tổng byte tải về.
- Số request trùng tới cùng URI.
- Cache hit rate và thời gian revalidation.

**Phía server**

- Số SQL query cho một request.
- Thời gian query và serialize response.
- Kích thước response body.
- CPU và memory khi tạo representation.
- Tác động của page size và số association được embed.

Một response chỉ có một HTTP request vẫn có thể chạy hàng trăm SQL query do lazy loading. Ngược lại, nhiều HTTP request nhỏ có thể dùng cache tốt và chỉ tải phần dữ liệu thực sự cần. Hãy đo cả hai tầng thay vì chỉ đếm request HTTP.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mỗi item tạo thêm một GET association | Client theo link tuần tự cho mọi item | Embed summary hoặc dùng batch/read endpoint phù hợp |
| Response collection quá lớn | Excerpt embed nhiều field hoặc collection lồng nhau | Thu nhỏ excerpt và chuyển collection lớn thành link |
| SQL query tăng theo số item | Projection truy cập association lazy gây N+1 | Tối ưu EntityGraph, query hoặc batch fetching |
| Client phải ghép URL thủ công | Không dùng relation link từ HAL | Theo href trong _links |
| Excerpt không áp dụng cho item resource | Excerpt chủ yếu dành cho collection/related resource | Dùng projection query tường minh cho item |
| Dữ liệu con bị lặp trong nhiều parent | Embed cùng resource nhiều lần | Link traversal hoặc embed summary nhỏ |
| Cache parent cũ sau khi child đổi | Child được embed trong representation parent | Revalidate parent hoặc tách child thành resource riêng |
| Client thấy dữ liệu con không được phép | Projection/excerpt expose field nhạy cảm | Kiểm tra authorization và field exposure |
| Pagination chậm khi embed collection lớn | Mỗi parent kéo theo nhiều child | Page child riêng hoặc dùng excerpt |
| Tăng số request nhưng UI vẫn chậm | Round trip tuần tự và latency mạng | Kết hợp dữ liệu thường dùng, cache và tải song song có giới hạn |

## 19. Kết luận

Nhúng dữ liệu giảm số round trip và giúp client render nhanh khi dữ liệu liên quan nhỏ, ổn định và thường xuyên được dùng cùng resource cha. Lần theo link giữ resource độc lập, hỗ trợ cache và tải theo nhu cầu, nhưng có thể tăng số HTTP request và độ phức tạp phía client.

Spring Data REST mặc định dùng HAL với _links để điều hướng. Projection và excerpt có thể tạo representation rút gọn hoặc embed dữ liệu liên quan; excerpt được áp dụng tự động cho collection/related resources, không tự động cho single item. Khi chọn cách biểu diễn, hãy cân nhắc payload, pagination, cache, authorization, consistency và SQL query count. Một response ít request HTTP vẫn có thể gây N+1 query; một response có link không nhất thiết chậm nếu client cache và tái sử dụng resource hiệu quả. Thực tế thường phù hợp với cách kết hợp: embed summary nhỏ, giữ link tới resource đầy đủ và dùng projection cho từng màn hình.

## Tài liệu tham khảo

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Repository Resources and HAL](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [HAL Specification](https://stateless.group/hal_specification.html)
- [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
