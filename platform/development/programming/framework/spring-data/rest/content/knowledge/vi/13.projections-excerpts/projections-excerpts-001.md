# Projection là gì và khi nào cần thay đổi góc nhìn dữ liệu trong Spring Data REST?

## Mục tiêu

Sau bài này, bạn có thể giải thích projection trong Spring Data REST; tạo projection interface để chọn các thuộc tính cần hiển thị; dùng nested projection cho quan hệ; phân biệt projection được client yêu cầu với excerpt projection tự động dùng trong collection; và nhận biết giới hạn của projection về hiệu năng, ghi dữ liệu và bảo mật.

## 1. Projection là gì?

Một domain entity thường có nhiều thuộc tính phục vụ lưu trữ và nghiệp vụ. Tuy nhiên, mỗi màn hình hoặc client chỉ cần một phần dữ liệu khác nhau. Ví dụ, entity `Customer` có thể chứa tên, email, số điện thoại, địa chỉ, ghi chú nội bộ và lịch sử giao dịch. Trang danh sách khách hàng chỉ cần tên và email; trang chi tiết cần thêm địa chỉ và số điện thoại.

**Projection** là một góc nhìn của entity, xác định tập thuộc tính được đưa vào representation trả về từ API. Trong Spring Data REST, projection thường được khai báo bằng một Java interface với các accessor tương ứng thuộc tính của domain type.

Projection giúp API trả dữ liệu phù hợp với nhu cầu từng client mà không phải tạo một endpoint hoặc DTO riêng cho mọi góc nhìn đơn giản. Entity và dữ liệu lưu trong database vẫn là nguồn dữ liệu; projection chỉ định cách biểu diễn resource trong response.

Ví dụ, entity:

```java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phone;
    private String internalNote;

    @ManyToOne
    private Address address;

    // Constructor, getters và setters
}
```

Một client danh sách có thể chỉ cần tên và email. Client khác có thể cần thêm số điện thoại và địa chỉ. Thay vì trả tất cả thuộc tính trong mọi trường hợp, ta định nghĩa các projection tương ứng.

## 2. Tạo projection interface bằng @Projection

Dùng annotation `@Projection` để đặt tên projection và chỉ rõ domain type mà projection áp dụng:

```java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "customerSummary", types = Customer.class)
public interface CustomerSummary {

    String getFirstName();

    String getLastName();

    String getEmail();
}
```

Các accessor như `getFirstName()`, `getLastName()` và `getEmail()` khớp với property của `Customer`. Khi projection được áp dụng, representation chứa các thuộc tính được khai báo trong interface cùng các link hypermedia do Spring Data REST tạo.

Để projection được Spring Data REST phát hiện tự động, đặt interface trong cùng package với domain type hoặc một subpackage của package đó. Nếu dự án dùng cách tổ chức package khác, có thể đăng ký projection rõ ràng thông qua cấu hình projection của `RepositoryRestConfiguration`.

Ví dụ repository:

```java
@RepositoryRestResource(path = "customers")
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Sau khi projection được nhận diện, client có thể yêu cầu nó bằng query parameter `projection`:

```http
GET /customers/42?projection=customerSummary
Accept: application/hal+json
```

Giá trị `customerSummary` là tên khai báo trong `@Projection(name = "customerSummary", ...)`. Tên query parameter và tên projection phải khớp với projection đã được đăng ký.

Nếu client gọi `GET /customers/42` mà không có `projection`, Spring Data REST dùng representation mặc định của resource hoặc excerpt/default projection theo ngữ cảnh. Projection được chọn qua query parameter cho phép client yêu cầu góc nhìn cụ thể khi endpoint hỗ trợ.

## 3. Closed projection: chỉ rõ các property cần lấy

Một projection có các accessor ánh xạ trực tiếp đến property của domain type thường được gọi là **closed projection**:

```java
@Projection(name = "customerContact", types = Customer.class)
public interface CustomerContact {

    String getFirstName();

    String getLastName();

    String getEmail();

    String getPhone();
}
```

Spring Data biết chính xác những property nào được projection yêu cầu vì các accessor đều tương ứng với property của entity. Đây là dạng projection đơn giản và dễ dự đoán nhất.

Dùng closed projection khi client cần một tập thuộc tính cố định, chẳng hạn:

- Danh sách ngắn gọn cho màn hình tìm kiếm.
- Thông tin liên hệ cho một quy trình chăm sóc khách hàng.
- Các thuộc tính hiển thị trong bảng hoặc thẻ tóm tắt.
- Một representation không cần các field nội bộ của domain object.

Một projection có thể bỏ qua các property mà client không cần. Tuy nhiên, việc một property không xuất hiện trong projection không có nghĩa property đó bị xóa, bị ẩn khỏi mọi endpoint hoặc không thể được truy cập bằng một API khác.

## 4. Open projection: tạo thuộc tính dẫn xuất

Projection cũng có thể định nghĩa giá trị được tính từ nhiều property của target object bằng `@Value` và SpEL. Dạng này thường được gọi là **open projection**:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "customerDisplay", types = Customer.class)
public interface CustomerDisplay {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();

    String getEmail();
}
```

Ở đây, `displayName` không nhất thiết là một cột trong database. Giá trị được tính từ `firstName` và `lastName` khi projection được tạo.

Open projection hữu ích khi response cần một thuộc tính dẫn xuất đơn giản, ví dụ tên hiển thị, nhãn hoặc giá trị tổng hợp. Tuy nhiên, biểu thức SpEL có thể truy cập nhiều property của target object nên Spring Data khó xác định chính xác tập property cần thiết trước khi tính kết quả. Điều này có thể làm giảm cơ hội tối ưu truy vấn so với closed projection.

Nếu logic tính toán phức tạp, phụ thuộc nhiều quy tắc nghiệp vụ hoặc cần gọi dịch vụ khác, hãy cân nhắc đặt logic trong service và tạo custom representation phù hợp thay vì nhồi toàn bộ logic vào SpEL.

## 5. Nested projection: thay đổi góc nhìn của quan hệ

Một entity có thể tham chiếu entity khác. Projection có thể khai báo một projection interface cho property quan hệ để kiểm soát dữ liệu hiển thị ở tầng lồng nhau.

Ví dụ, `Customer` có quan hệ đến `Address`. Tạo projection cho địa chỉ:

```java
@Projection(name = "addressSummary", types = Address.class)
public interface AddressSummary {

    String getCity();

    String getCountry();
}
```

Projection Customer có thể trả về `AddressSummary` thay vì toàn bộ Address:

```java
@Projection(name = "customerWithAddress", types = Customer.class)
public interface CustomerWithAddress {

    String getFirstName();

    String getLastName();

    AddressSummary getAddress();
}
```

Khi gọi:

```http
GET /customers/42?projection=customerWithAddress
Accept: application/hal+json
```

representation có thể chứa tên khách hàng và phần địa chỉ được giới hạn theo `AddressSummary`. Cách này giúp client nhận cấu trúc dữ liệu lồng nhau phù hợp với màn hình mà không cần yêu cầu toàn bộ property của Address.

Với quan hệ collection, có thể khai báo collection của projection interface tương ứng, ví dụ `List<OrderSummary> getOrders()`. Cần kiểm tra domain mapping, cách Jackson/Spring Data tạo projection và cấu hình serialization để bảo đảm cấu trúc response đúng như client cần.

Nested projection có thể làm phát sinh truy cập đến các association. Nếu association là lazy-loaded hoặc collection lớn, việc serialize representation có thể dẫn đến truy vấn bổ sung hoặc tải nhiều dữ liệu. Projection giúp điều khiển góc nhìn JSON, nhưng không tự động bảo đảm truy vấn database tối ưu.

## 6. Excerpt projection là gì?

**Excerpt projection** là projection được Spring Data REST dùng làm representation rút gọn cho các phần tử trong collection resource. Ví dụ, khi client gọi:

```http
GET /customers
Accept: application/hal+json
```

collection response có thể nhúng danh sách khách hàng trong `_embedded`. Nếu repository cấu hình excerpt projection, mỗi phần tử nhúng sẽ dùng góc nhìn tóm tắt đó thay vì representation đầy đủ của entity.

Khai báo excerpt projection trên repository bằng thuộc tính `excerptProjection` của `@RepositoryRestResource`:

```java
@Projection(name = "customerExcerpt", types = Customer.class)
public interface CustomerExcerpt {

    String getFirstName();

    String getLastName();

    String getEmail();
}
```

```java
@RepositoryRestResource(
    path = "customers",
    excerptProjection = CustomerExcerpt.class
)
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Trong ví dụ này, collection resource `/customers` dùng `CustomerExcerpt` cho các customer được nhúng. Client nhận danh sách tóm tắt và có thể theo link `self` để truy cập item resource.

Excerpt projection hữu ích khi collection có nhiều entity hoặc entity chứa nhiều property không cần thiết cho danh sách. Nó giúp representation collection gọn hơn và tạo một góc nhìn mặc định thống nhất cho danh sách.

## 7. Phân biệt projection được yêu cầu và excerpt projection

Hai cơ chế có liên quan nhưng mục đích sử dụng khác nhau:

| Cơ chế | Cách chọn | Nơi thường áp dụng | Mục đích |
| --- | --- | --- | --- |
| Projection thông thường | Client gửi `?projection=...` | Resource response mà endpoint hỗ trợ | Client chọn góc nhìn cụ thể |
| Excerpt projection | Repository khai báo `excerptProjection = ...` | Các phần tử được nhúng trong collection resource | Đặt góc nhìn tóm tắt mặc định cho collection |

Ví dụ, repository dùng excerpt projection cho collection:

```java
@RepositoryRestResource(
    path = "customers",
    excerptProjection = CustomerExcerpt.class
)
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Client gọi collection:

```http
GET /customers
```

Các phần tử trong `_embedded.customers` dùng excerpt projection. Khi client theo link `self` đến `/customers/42`, response item có thể sử dụng representation đầy đủ mặc định. Nếu client muốn một projection cụ thể và projection đó được công bố, client yêu cầu:

```http
GET /customers/42?projection=customerWithAddress
```

Vì vậy, excerpt projection không nên được hiểu là mọi request đến item resource đều bị khóa vào cùng một tập property. Nó định hình phần tóm tắt trong collection; projection query parameter cho phép chọn góc nhìn cụ thể trong các ngữ cảnh được hỗ trợ.

## 8. Projection ảnh hưởng thế nào đến API và dữ liệu?

Projection thay đổi representation mà client nhìn thấy. Nó không thay đổi entity được lưu trong database, không tự thay đổi query method, không tạo repository mới và không thay thế domain model.

Một số hệ quả cần nhớ:

- Các property không nằm trong projection không xuất hiện trong representation theo projection đó.
- Các link hypermedia vẫn được Spring Data REST tạo theo resource và cấu hình tương ứng.
- Một projection có thể bao gồm association hoặc nested projection, làm representation sâu hơn.
- Open projection có thể tính property bằng SpEL.
- Excerpt projection áp dụng cho phần tử collection được nhúng theo cấu hình repository.
- Projection không phải là request DTO hoặc allowlist cho các thuộc tính POST/PUT/PATCH được phép ghi.

Nếu client cần một schema đầu vào riêng, hãy thiết kế command/request DTO và custom controller hoặc application service phù hợp. Không dùng projection đọc để kiểm soát dữ liệu ghi.

## 9. Projection không phải cơ chế bảo mật

Không nên dùng projection làm ranh giới bảo mật cho dữ liệu nhạy cảm. Projection chỉ quyết định representation nào được trả trong một ngữ cảnh cụ thể. Client có thể thử request representation mặc định, yêu cầu một projection khác đã được đăng ký hoặc truy cập resource qua endpoint khác nếu endpoint đó cho phép.

Ví dụ, nếu `internalNote` là dữ liệu chỉ quản trị viên được xem, việc bỏ `getInternalNote()` khỏi `CustomerSummary` không đủ để bảo vệ dữ liệu đó. Cần áp dụng authorization ở server, dùng Spring Security và thiết kế endpoint/representation theo quyền người dùng. Với property không được phép xuất hiện trong bất kỳ JSON response nào, có thể cấu hình serialization phù hợp như `@JsonIgnore`, đồng thời kiểm tra các đường truy cập khác.

Tương tự, projection không thay thế kiểm soát quyền trên association. Nếu Customer liên kết với Order thuộc tenant khác, server vẫn phải xác minh quyền trước khi trả hoặc thay đổi quan hệ.

## 10. Lựa chọn projection theo nhu cầu

- Dùng **closed projection** khi cần một tập property cố định và rõ ràng.
- Dùng **open projection** khi cần một giá trị dẫn xuất đơn giản từ các property của entity.
- Dùng **nested projection** khi response cần hiển thị một phần của association.
- Dùng **excerpt projection** khi collection cần representation tóm tắt mặc định cho các phần tử nhúng.
- Dùng **custom DTO/controller** khi response cần hợp nhất nhiều nguồn dữ liệu, logic nghiệp vụ phức tạp hoặc schema đầu ra/đầu vào hoàn toàn riêng.

Không nên tạo quá nhiều projection gần như giống nhau mà không có nhu cầu client cụ thể. Mỗi projection là một phần hợp đồng API mà client có thể phụ thuộc; đổi tên projection hoặc property có thể ảnh hưởng các client đang gọi nó.

## 11. Cách kiểm tra projection

Sau khi khai báo projection, có thể kiểm tra theo trình tự:

1. Xác nhận projection interface có `@Projection`, tên projection và target type chính xác.
2. Kiểm tra package của projection để Spring Data REST phát hiện tự động, hoặc đăng ký rõ ràng qua cấu hình.
3. Gọi API root hoặc resource để lấy link và xác nhận repository đã được công bố.
4. Gọi item resource với `?projection=<name>`.
5. Kiểm tra response body có đúng các property được khai báo và có link hypermedia cần thiết.
6. Gọi collection resource để xác nhận excerpt projection được áp dụng cho các phần tử nhúng.
7. Kiểm tra nested association và số lượng truy vấn khi projection truy cập quan hệ lớn hoặc lazy-loaded.
8. Kiểm tra quyền truy cập riêng cho property nhạy cảm; không suy luận bảo mật từ việc property vắng mặt trong một projection.

Ví dụ:

```bash
curl -i "http://localhost:8080/customers/42?projection=customerSummary" \
  -H "Accept: application/hal+json"
```

Kiểm tra excerpt trong collection:

```bash
curl -i "http://localhost:8080/customers" \
  -H "Accept: application/hal+json"
```

Nếu query parameter `projection` không có tác dụng, kiểm tra tên projection, target type, package discovery và cấu hình projection. Nếu collection không dùng excerpt như mong muốn, kiểm tra `excerptProjection` trên đúng repository interface và response `_embedded`.

## Tóm tắt

- Projection là góc nhìn của domain object, thường khai báo bằng interface và `@Projection`.
- Client yêu cầu projection bằng query parameter `?projection=<name>`.
- Closed projection ánh xạ trực tiếp accessor đến property; open projection có thể tính giá trị bằng SpEL.
- Nested projection giới hạn dữ liệu của association trong representation lồng nhau.
- Excerpt projection được khai báo bằng `@RepositoryRestResource(excerptProjection = ...)` để định hình các phần tử nhúng trong collection resource.
- Projection thay đổi representation, không thay đổi dữ liệu lưu và không phải allowlist cho request ghi.
- Không dùng projection làm cơ chế bảo mật; hãy kiểm soát truy cập bằng authorization và cấu hình serialization phù hợp.

## Tài liệu tham khảo

- [Spring Data REST — Projections and excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Excerpt projection configuration](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
