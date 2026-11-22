# Lựa chọn mô hình miền phù hợp để công bố trực tiếp qua REST

Spring Data REST có thể xuất Spring Data Repository thành REST resource. Repository quản lý kiểu miền nào thì kiểu miền đó trở thành cơ sở cho collection resource, item resource và các thao tác HTTP được hỗ trợ. Vì vậy, lựa chọn mô hình miền để công bố trực tiếp qua REST cũng là lựa chọn ranh giới dữ liệu, quan hệ và thao tác mà client bên ngoài có thể nhìn thấy.

Không phải mọi entity trong database đều nên có repository REST riêng. Mô hình phù hợp thường là mô hình có ý nghĩa nghiệp vụ rõ ràng, có định danh và vòng đời ổn định, có ranh giới nhất quán dễ hiểu, và có dữ liệu có thể công khai mà không làm lộ cấu trúc nội bộ. Với những đối tượng chỉ có ý nghĩa bên trong một đối tượng lớn hơn, hãy cân nhắc giữ chúng như thành phần của aggregate thay vì biến từng đối tượng thành một resource độc lập.

## 1. Spring Data REST công bố mô hình miền như thế nào?

Spring Data REST lấy repository làm điểm xuất phát. Ví dụ:

~~~java
public interface OrderRepository extends CrudRepository<Order, UUID> {
}
~~~

Repository trên có thể tạo collection resource tại đường dẫn suy ra từ tên kiểu miền, chẳng hạn `/orders`, cùng item resource `/orders/{id}`. Tên và đường dẫn có thể được tùy chỉnh bằng `@RepositoryRestResource`.

Các HTTP method được cung cấp phụ thuộc vào những phương thức repository được export. Với repository kiểu CRUD, collection thường hỗ trợ GET và POST; item thường hỗ trợ GET, PUT, PATCH và DELETE. Có thể ẩn các thao tác bằng cách không khai báo hoặc dùng `@RestResource(exported = false)` cho method phù hợp.

Điều đó có nghĩa là việc chọn một repository không chỉ quyết định dữ liệu nào được đọc. Nó còn có thể công bố khả năng tạo, thay thế, cập nhật hoặc xóa đối tượng qua HTTP. Cần xem repository như một phần của API contract.

Spring Data REST mặc định biểu diễn resource bằng HAL JSON. Response chứa dữ liệu cùng các link để client khám phá collection, item, search và quan hệ. Client có thể đi theo link được công bố thay vì tự ghép URL theo quy ước nội bộ của server.

## 2. Bắt đầu từ khái niệm nghiệp vụ và vòng đời

Một kiểu miền phù hợp để công bố trực tiếp nên đại diện cho một khái niệm mà người dùng API hiểu được. Ví dụ:

- `Order`: đơn hàng có mã, trạng thái, thời điểm tạo và các dòng hàng.
- `Customer`: khách hàng có danh tính và thông tin hồ sơ được phép công bố.
- `Product`: sản phẩm trong catalog.
- `Shipment`: lô giao hàng có trạng thái và lịch sử giao nhận.

Một kiểu chỉ tồn tại để hỗ trợ lưu trữ thường không phải resource tốt. Ví dụ `OrderSequence`, `OrderAuditRow`, `InternalPricingCache` hoặc một bảng nối thuần kỹ thuật có thể không có ý nghĩa độc lập với người dùng API.

Hãy đặt các câu hỏi sau khi xem xét một kiểu miền:

1. Người dùng API có thể gọi tên và hiểu đối tượng này như một tài nguyên riêng không?
2. Đối tượng có định danh ổn định để truy cập trực tiếp không?
3. Nó có vòng đời riêng, hay chỉ được tạo/xóa cùng một đối tượng khác?
4. Có quy tắc nghiệp vụ nào yêu cầu mọi thay đổi phải đi qua một đối tượng điều phối không?
5. Những thuộc tính của nó có thể được công bố mà không tiết lộ dữ liệu nội bộ không?
6. Các thao tác CRUD có phản ánh đúng những hành động mà API nên cho phép không?

Ví dụ, `Order` có định danh, trạng thái và vòng đời từ lúc tạo đến khi hoàn tất. Nó thường là resource có ý nghĩa. `OrderLine` có thể chỉ là một phần của đơn hàng: người dùng không tạo một dòng hàng độc lập mà phải thêm dòng hàng vào một đơn hàng đang ở trạng thái cho phép chỉnh sửa. Trong trường hợp đó, `OrderLine` thường nên được quản lý thông qua `Order`.

## 3. Dùng aggregate root làm điểm bắt đầu

Trong Domain-Driven Design, aggregate là một nhóm đối tượng cần giữ nhất quán trong cùng một ranh giới thay đổi. Mỗi aggregate có một aggregate root. Những thay đổi thuộc aggregate được điều phối qua root; repository thường được định nghĩa cho aggregate root.

Ví dụ một đơn hàng:

~~~mermaid
flowchart TD
    O["Order<br/>Aggregate Root"] --> L1["OrderLine"]
    O --> L2["OrderLine"]
    O --> L3["OrderLine"]
    O -. "tham chiếu aggregate khác" .-> C["Customer"]
    O -. "tham chiếu aggregate khác" .-> P["Product"]
~~~

`Order` là root vì nó kiểm soát trạng thái đơn hàng và các dòng hàng. `OrderLine` là thành phần được thêm, sửa hoặc bỏ thông qua `Order`. `Customer` và `Product` có thể là aggregate riêng với vòng đời riêng.

Một cách tổ chức repository phù hợp có thể là:

~~~java
public interface OrderRepository extends CrudRepository<Order, UUID> {
}

public interface CustomerRepository extends CrudRepository<Customer, UUID> {
}

public interface ProductRepository extends CrudRepository<Product, UUID> {
}
~~~

Nếu `OrderLine` chỉ thuộc về `Order`, không cần tạo `OrderLineRepository` chỉ vì nó được lưu trong bảng riêng. Việc tạo repository riêng có thể cho phép client đọc hoặc thay đổi dòng hàng độc lập, đi vòng qua quy tắc mà `Order` cần bảo vệ.

Một repository cho aggregate root giúp client thao tác trên ranh giới nghiệp vụ rõ ràng. Tuy nhiên, chỉ tạo repository cho root chưa đủ để bảo đảm mọi invariant được giữ khi request REST ghi dữ liệu. Hãy thiết kế cách binding, validation, phương thức ghi và quyền truy cập để các thay đổi vẫn tuân theo quy tắc của aggregate.

## 4. Phân biệt entity độc lập, entity con và value object

Ba loại đối tượng thường có cách công bố khác nhau:

| Loại đối tượng | Đặc điểm | Cách cân nhắc công bố |
|---|---|---|
| Aggregate root | Có identity và vòng đời độc lập; điều phối invariant của aggregate | Thường là ứng viên cho repository REST |
| Entity con | Có identity trong phạm vi aggregate nhưng được quản lý qua root | Thường để root quản lý; chỉ xuất riêng khi thật sự có nhu cầu và vòng đời độc lập |
| Value object | Được xác định bởi giá trị, không có identity riêng; thường bất biến | Thường nhúng vào representation của root thay vì tạo repository riêng |

Ví dụ, `Money(amount, currency)` là value object. Một `Address` có thể là value object nếu nó chỉ mô tả địa chỉ của một khách hàng và thay đổi cùng khách hàng. Nhưng nếu địa chỉ có thể được quản lý, chia sẻ hoặc tham chiếu độc lập trong nghiệp vụ, nó có thể cần identity và resource riêng.

Không quyết định dựa trên số bảng trong database. Một bảng riêng không tự động có nghĩa là một resource REST riêng. Ranh giới API nên theo ý nghĩa và vòng đời nghiệp vụ, không theo cấu trúc vật lý của schema.

## 5. Thiết kế quan hệ giữa các resource

Khi một thuộc tính tham chiếu đến kiểu miền khác, cách Spring Data REST biểu diễn nó phụ thuộc vào việc kiểu được tham chiếu có repository riêng hay không.

Giả sử `Order` có thuộc tính `customer`:

- Nếu `Customer` có repository được export, resource `Order` thường biểu diễn quan hệ bằng link đến association resource. Client có thể đi theo link để truy cập quan hệ.
- Nếu `Customer` không có repository riêng, dữ liệu của `Customer` có thể được đưa trực tiếp vào representation của `Order`.
- Nếu không muốn hiển thị quan hệ đó, có thể dùng projection hoặc cấu hình ẩn association phù hợp.

Ví dụ HAL khi `Customer` được export:

~~~json
{
  "status": "CREATED",
  "_links": {
    "self": {
      "href": "/orders/8b2"
    },
    "customer": {
      "href": "/orders/8b2/customer"
    }
  }
}
~~~

Link `customer` cho biết nơi truy cập quan hệ. Nó không nhất thiết là URI trực tiếp của resource Customer; client nên theo link mà server trả về.

Với quan hệ thuộc cùng aggregate, representation lồng nhau có thể phù hợp hơn:

~~~json
{
  "status": "CREATED",
  "lines": [
    {
      "productCode": "BOOK-01",
      "quantity": 2,
      "unitPrice": {
        "amount": 15.00,
        "currency": "USD"
      }
    }
  ]
}
~~~

Cách biểu diễn thực tế phụ thuộc mapping, repository được export, projection và serializer.

### 5.1. Tránh tạo resource cho mọi quan hệ

Nếu một quan hệ chỉ có ý nghĩa bên trong aggregate, công bố nó thành endpoint riêng có thể cho phép client thay đổi trạng thái theo cách không mong muốn. Ví dụ, nếu `OrderLine` có thể được sửa riêng qua `/orderLines/{id}`, client có thể thay số lượng của một đơn đã xác nhận mà không đi qua quy tắc của `Order`.

Ngược lại, nếu `Customer` là aggregate riêng, có vòng đời và quyền truy cập độc lập, việc cung cấp resource Customer có thể hợp lý. `Order` có thể tham chiếu đến Customer qua association link thay vì sao chép toàn bộ hồ sơ khách hàng vào mỗi response.

### 5.2. Cẩn thận với quan hệ hai chiều

Các object graph có tham chiếu hai chiều dễ tạo representation quá sâu hoặc vòng lặp khi serialize. Ví dụ `Order` giữ danh sách `OrderLine`, trong khi mỗi `OrderLine` lại tham chiếu ngược đến `Order`.

Không nên để cấu trúc Java nội bộ quyết định ngẫu nhiên hình dạng JSON. Hãy chọn rõ quan hệ nào được biểu diễn thành link, quan hệ nào được nhúng, và quan hệ nào bị ẩn. Có thể dùng projection, annotation serialization hoặc mô hình response riêng khi cần kiểm soát chặt.

## 6. Chọn thuộc tính được phép công bố

Spring Data REST trình bày một default view của domain model được export. Theo mặc định, nhiều thuộc tính của đối tượng được đưa vào representation, ngoại trừ identifier theo quy tắc mapping của exporter. Vì vậy, một entity được thiết kế cho persistence chưa chắc đã an toàn để công bố nguyên trạng.

Không nên đưa trực tiếp các dữ liệu sau vào API resource:

- Password, password hash, reset token hoặc credential.
- Secret key, access token và thông tin xác thực tích hợp.
- Trường nội bộ phục vụ vận hành hoặc tính toán.
- Thông tin cá nhân mà client hiện tại không được phép xem.
- Giá trị có thể làm lộ quy tắc nội bộ hoặc dữ liệu của tenant khác.

Ví dụ, một `User` dùng để xác thực có thể chứa `passwordHash`, `rolesInternal` và `resetToken`. Nếu repository được export, các thuộc tính đó cần được loại khỏi representation và các thao tác ghi tương ứng phải được bảo vệ.

Không dựa vào tên trường khó đoán hoặc giao diện frontend để giữ dữ liệu bí mật. Authorization phải được thực hiện ở server cho cả collection, item, search và association resource.

## 7. Dùng projection và excerpt để điều chỉnh representation

Khi domain model phù hợp với resource nhưng client chỉ cần một phần dữ liệu, Spring Data REST hỗ trợ projection.

Ví dụ, resource `Order` có nhiều thuộc tính nhưng màn hình danh sách chỉ cần mã, trạng thái và tổng tiền:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.data.rest.core.config.Projection;

@Projection(name = "orderSummary", types = Order.class)
public interface OrderSummary {

    UUID getId();

    OrderStatus getStatus();

    BigDecimal getTotal();
}
~~~

Client có thể yêu cầu projection qua query parameter `projection` nếu projection đã được đăng ký và được export cho resource:

~~~http
GET /orders/8b2?projection=orderSummary
~~~

Một excerpt projection có thể được khai báo trên repository:

~~~java
@RepositoryRestResource(
    path = "orders",
    excerptProjection = OrderSummary.class
)
public interface OrderRepository extends CrudRepository<Order, UUID> {
}
~~~

Excerpt được dùng làm view mặc định khi resource xuất hiện trong collection hoặc trong một resource liên quan. Excerpt projection không tự động áp dụng cho item resource khi client GET trực tiếp một item; client cần yêu cầu projection tương ứng.

Projection giúp điều chỉnh dữ liệu được trình bày. Nó không thay đổi aggregate boundary, không thay thế authorization và không tự biến một mô hình miền không phù hợp thành API contract tốt.

### 7.1. Projection có thể làm lộ dữ liệu

Projection có thể bổ sung những thuộc tính vốn bị ẩn khỏi default JSON representation. Vì vậy, một trường bị đánh dấu `@JsonIgnore` vẫn có thể xuất hiện nếu một projection được thiết kế để đọc trường đó.

Khi tạo projection, hãy xem mỗi getter là một quyết định công bố dữ liệu. Không cho rằng `@JsonIgnore` là ranh giới bảo mật tuyệt đối nếu API còn hỗ trợ projection. Với dữ liệu nhạy cảm, kiểm tra cả các projection đã đăng ký và quyền của người gọi.

## 8. Đánh giá khả năng ghi và bảo vệ invariant

Công bố repository có thể làm xuất hiện POST, PUT, PATCH hoặc DELETE tương ứng với các phương thức repository. Điều này phù hợp khi CRUD trực tiếp là cách thao tác hợp lệ của nghiệp vụ.

Hãy cân nhắc lại nếu:

- Đơn hàng chỉ được tạo qua quy trình checkout nhiều bước.
- Trạng thái đơn hàng chỉ được chuyển theo một state machine.
- Giá sản phẩm phải lấy từ catalog và được chụp lại tại thời điểm đặt hàng.
- Số lượng tồn kho chỉ được thay đổi qua quy trình giữ chỗ hoặc hoàn kho.
- Một thay đổi cần kiểm tra nhiều aggregate hoặc gọi dịch vụ bên ngoài.
- Một thao tác cần phát sự kiện, ghi audit hoặc thực hiện side effect có thứ tự.

Trong những trường hợp đó, một endpoint CRUD trực tiếp có thể không thể hiện đúng hành động nghiệp vụ. Hãy dùng service/controller cho use case, chẳng hạn `POST /orders/{id}/confirm`, `POST /orders/{id}/cancel` hoặc `POST /checkout`. Service thực hiện quy tắc và transaction; repository vẫn có thể được giữ nội bộ.

Nếu chỉ cần ẩn một method repository khỏi REST API, dùng `@RestResource(exported = false)` trên method. Nếu cần ẩn toàn bộ repository, dùng `@RepositoryRestResource(exported = false)` hoặc cấu hình detection strategy phù hợp.

Ẩn method không đồng nghĩa đã bảo vệ toàn bộ nghiệp vụ. Một endpoint khác có thể vẫn gọi cùng repository, và quyền truy cập phải được kiểm tra ở server.

## 9. Cân nhắc hiệu năng và kích thước representation

Một mô hình miền phù hợp về nghiệp vụ vẫn có thể tạo API chậm nếu response kéo theo quá nhiều quan hệ.

Hãy xem xét:

- Collection có hỗ trợ phân trang hay không.
- Mỗi item có tải thêm nhiều association hay không.
- Quan hệ nào chỉ cần link, quan hệ nào cần dữ liệu nhúng.
- Projection nào phù hợp cho danh sách và chi tiết.
- Có truy vấn N+1 khi serialize collection không.
- Client có thực sự cần toàn bộ graph trong một response không.

Spring Data REST có thể cung cấp pagination và link điều hướng trang khi repository hỗ trợ `Pageable`. Đừng mặc định collection lớn nên được trả toàn bộ trong một response.

Một chiến lược phổ biến là collection dùng excerpt projection ngắn; item resource cung cấp chi tiết; các aggregate liên quan được truy cập qua link. Cách này giúp client lấy đúng lượng dữ liệu cần thiết và giữ representation dễ điều hướng.

## 10. Khi nào không nên công bố trực tiếp domain model?

Công bố trực tiếp phù hợp khi domain model và API resource có cùng ý nghĩa, cùng ranh giới và có thể phát triển tương đối đồng bộ. Nếu hai mô hình khác nhau, hãy tạo lớp API riêng.

| Tình huống | Hướng phù hợp |
|---|---|
| CRUD đơn giản trên aggregate root, dữ liệu có thể công khai | Spring Data REST trực tiếp |
| Domain model có nhiều trường nội bộ nhưng chỉ cần một số trường đọc | Projection, excerpt và cấu hình representation |
| API cần một hợp đồng JSON độc lập với entity và schema | DTO hoặc representation model riêng |
| Một request thực hiện quy trình nghiệp vụ nhiều bước | Service và custom controller |
| Quyền truy cập phụ thuộc tenant, trạng thái hoặc từng thuộc tính | Authorization rõ ràng; thường cần service/controller hoặc cơ chế bảo vệ chuyên biệt |
| Một resource tổng hợp dữ liệu từ nhiều aggregate hoặc hệ thống | Query service và DTO/custom endpoint |
| API cần versioning độc lập với mô hình persistence | API model riêng và controller |

DTO không phải là dấu hiệu thiết kế thừa. Nó hữu ích khi API có vòng đời, tên trường, quy tắc validation hoặc mức độ công khai khác domain model.

Có thể giữ Spring Data Repository để truy cập dữ liệu, nhưng không export repository đó. Service và controller sẽ gọi repository, chuyển dữ liệu sang DTO, áp dụng authorization và thực hiện use case. Như vậy, persistence model có thể thay đổi mà không buộc client thay đổi theo.

## 11. Ví dụ lựa chọn mô hình cho hệ thống bán hàng

Giả sử hệ thống có các kiểu miền:

~~~mermaid
flowchart TD
    O["Order"] --> L["OrderLine"]
    O --> C["Customer"]
    L --> P["Product"]
    O --> A["PaymentAttempt"]
    O --> H["OrderHistory"]
~~~

Có thể cân nhắc như sau:

| Kiểu miền | Quyết định ban đầu | Lý do |
|---|---|---|
| Order | Export repository | Có định danh, vòng đời và là aggregate root |
| OrderLine | Giữ trong Order | Thay đổi dòng hàng cần tuân theo trạng thái và quy tắc của Order |
| Customer | Có thể export repository riêng | Có vòng đời và quyền truy cập riêng; Order tham chiếu đến Customer |
| Product | Có thể export read-only hoặc qua API catalog | Product thuộc catalog; việc thay đổi giá/tồn kho có quy trình riêng |
| PaymentAttempt | Thường không export CRUD trực tiếp | Là chi tiết của quy trình thanh toán, cần kiểm soát side effect |
| OrderHistory | Thường chỉ đọc qua query resource | Lịch sử cần bảo toàn tính bất biến và audit |

Đây là quyết định phụ thuộc nghiệp vụ, không phải quy tắc cứng. Nếu hệ thống cho phép người dùng quản lý địa chỉ giao hàng độc lập, `Address` có thể trở thành resource riêng. Nếu địa chỉ chỉ là bản chụp tại thời điểm đặt hàng, nó nên là một phần dữ liệu của Order và không tự thay đổi khi hồ sơ Customer được cập nhật.

Ví dụ repository cho aggregate root:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends CrudRepository<Order, UUID> {
}
~~~

Nếu ứng dụng không muốn cho client xóa đơn hàng trực tiếp, có thể ẩn method xóa khỏi REST exposure và cung cấp hành động nghiệp vụ riêng:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends CrudRepository<Order, UUID> {

    @Override
    @RestResource(exported = false)
    void deleteById(UUID id);
}
~~~

API hành động hủy đơn hàng có thể được triển khai bằng service/controller để kiểm tra trạng thái, hoàn kho hoặc phối hợp thanh toán theo quy tắc của hệ thống.

## 12. Quy trình quyết định trước khi export

Với mỗi kiểu miền được cân nhắc công bố, hãy đi lần lượt qua các quyết định sau:

1. Xác định khái niệm nghiệp vụ và người tiêu dùng API.
2. Xác định identity, vòng đời và aggregate root.
3. Phân loại các quan hệ thành aggregate khác, entity con hoặc value object.
4. Quyết định repository nào được phép export.
5. Chọn thuộc tính và association được hiển thị.
6. Xác định HTTP method nào phản ánh đúng thao tác nghiệp vụ.
7. Đánh giá authorization, tenant boundary và dữ liệu nhạy cảm.
8. Xác định pagination, projection và mức độ tải quan hệ.
9. Quyết định liệu domain model có thể là API contract lâu dài hay cần DTO/controller riêng.

Hãy ghi rõ lý do cho mỗi repository được export hoặc không export. Điều này giúp tránh việc một repository nội bộ vô tình trở thành public API chỉ vì nó đã được tạo để phục vụ persistence.

## 13. Ghi nhớ

- Spring Data REST xuất repository thành collection và item resource; cấu trúc repository quyết định các HTTP method được cung cấp.
- Aggregate root thường là điểm bắt đầu tốt để chọn repository và resource boundary.
- Entity con nên được quản lý qua root nếu vòng đời và invariant của nó phụ thuộc vào aggregate.
- Value object thường được nhúng trong representation thay vì có repository riêng.
- Association có repository riêng thường được biểu diễn bằng link; kiểu không có repository có thể được nhúng thành dữ liệu.
- Projection và excerpt điều chỉnh representation, nhưng không thay thế authorization.
- CRUD trực tiếp phù hợp với thao tác dữ liệu tiêu chuẩn; quy trình nghiệp vụ nhiều bước nên đi qua service/controller.
- Không để cấu trúc bảng database quyết định cấu trúc API.

## 14. Tài liệu chính thức

- Spring Data REST — Repository resources: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST — Projections and excerpts: https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html
- Spring Data Commons — Repository abstraction: https://docs.spring.io/spring-data/commons/reference/repositories.html
- Spring Data Relational — Domain-driven design and aggregates: https://docs.spring.io/spring-data/relational/reference/jdbc/domain-driven-design.html
