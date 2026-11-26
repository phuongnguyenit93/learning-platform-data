# Projection trong Data REST

Spring Data REST xuất bản các repository thành REST resource và tạo representation mặc định từ domain model. Trong nhiều tình huống, client chỉ cần một phần thuộc tính: màn hình danh sách chỉ cần tên và email, trang chi tiết cần thêm địa chỉ, còn màn hình quản trị có thể cần thông tin tổng hợp. Nếu mọi client đều nhận cùng một representation lớn, response có thể chứa dữ liệu không cần thiết và hợp đồng trở nên khó điều chỉnh.

Projection cho phép định nghĩa những góc nhìn khác nhau trên cùng một domain type. Với Spring Data REST, projection thường là một Java interface được đánh dấu bằng `@Projection`. Các getter trong interface xác định thuộc tính được đưa vào representation. Client chọn projection theo tên đã khai báo bằng query parameter `projection`. Một projection khác có thể được cấu hình làm excerpt để tự động áp dụng khi resource xuất hiện trong collection.

Projection giúp kiểm soát cấu trúc dữ liệu được xuất bản, nhưng không thay thế phân quyền, không thay đổi entity được lưu trong database và không bảo đảm truy vấn chỉ đọc đúng các cột được chiếu. Bài học này hướng dẫn cách khai báo, đăng ký, chọn và kiểm thử projection trong Spring Data REST; cách dùng excerpt và computed property; cùng các rủi ro về dữ liệu nhạy cảm, quan hệ lazy và tương thích API.

Sau bài học, bạn có thể:

- Giải thích projection trong Spring Data REST và lý do cần nhiều representation cho cùng một entity.
- Tạo interface projection bằng `@Projection`.
- Hiểu vai trò của `name` và `types`.
- Đăng ký projection theo package scan hoặc cấu hình tường minh.
- Chọn projection bằng query parameter `projection`.
- Phân biệt projection được chọn theo request với excerpt projection.
- Cấu hình excerpt bằng `@RepositoryRestResource(excerptProjection = ...)`.
- Tạo nested projection và computed property bằng `@Value`.
- Khám phá projection qua ALPS profile.
- Nhận diện rủi ro khi projection truy cập dữ liệu bị `@JsonIgnore`.
- Kiểm thử representation bằng MockMvc và quản lý thay đổi hợp đồng.

## 1. Projection giải quyết vấn đề gì?

Giả sử hệ thống quản lý khách hàng có entity:

~~~java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phone;

    @OneToOne
    private Address address;

    // constructors, getters and setters
}
~~~

Các import JPA cho entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.OneToOne;
~~~

Repository được Spring Data REST xuất bản:

~~~java
@RepositoryRestResource(path = "customers")
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Import:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
~~~

Một client hiển thị danh sách khách hàng có thể chỉ cần tên và email. Một client khác ở trang chi tiết cần số điện thoại và địa chỉ. Nếu dùng representation mặc định cho tất cả, client danh sách phải nhận thêm dữ liệu mà nó không sử dụng.

Có thể định nghĩa hai projection:

- `customerSummary`: tên hiển thị và email.
- `customerDetails`: tên, email, số điện thoại và địa chỉ.

Cả hai cùng áp dụng cho `Customer`. Domain model và repository vẫn là một; projection chỉ tạo các view khác nhau khi Spring Data REST dựng representation.

### 1.1. Projection là view của representation

Projection xác định những thuộc tính mà một representation được phép trình bày. Nó không tạo một entity mới, không thay đổi dữ liệu lưu trữ và không tạo một repository mới.

| Thành phần | Vai trò |
|---|---|
| Entity | Mô hình domain và trạng thái được lưu |
| Repository | Truy cập aggregate/domain object |
| Projection interface | Khai báo view được xuất bản |
| Projection name | Tên client dùng để chọn view |
| Representation | JSON/HAL được trả về cho client |

Ví dụ, cùng một khách hàng có thể được biểu diễn:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an@example.com"
}
~~~

Hoặc:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an@example.com",
  "phone": "+84-900-123-456",
  "address": {
    "city": "Ho Chi Minh City",
    "country": "Vietnam"
  }
}
~~~

Các thuộc tính xuất hiện phụ thuộc projection được chọn và cấu hình quan hệ. Link hypermedia của resource vẫn được Spring Data REST công bố theo cấu hình repository.

### 1.2. Projection không đồng nghĩa với database query projection

Spring Data có các khả năng projection ở tầng repository query, ví dụ query method trả về interface hoặc DTO để chỉ lấy một phần dữ liệu. Đó là một cơ chế liên quan nhưng khác với projection được Spring Data REST dùng để định hình representation HTTP.

Projection của Spring Data REST được áp dụng khi tạo representation từ domain object. Không nên mặc định rằng việc khai báo một projection REST sẽ khiến ORM chỉ truy vấn các cột có getter trong interface. Nếu mục tiêu là tối ưu truy vấn hoặc giảm lượng dữ liệu database đọc, cần xem xét query projection, fetch plan và cách tải quan hệ riêng.

## 2. Khai báo projection bằng @Projection

Một projection thường là interface có các getter tương ứng với thuộc tính cần xuất bản.

Ví dụ:

~~~java
@Projection(
    name = "customerSummary",
    types = Customer.class
)
public interface CustomerSummary {

    String getFirstName();

    String getLastName();

    String getEmail();
}
~~~

Import:

~~~java
import org.springframework.data.rest.core.config.Projection;
~~~

Giải thích:

- `@Projection` đánh dấu interface là projection dành cho Spring Data REST.
- `name` là tên client dùng trong query parameter `projection`.
- `types` chỉ định domain type mà projection áp dụng.
- Các getter khai báo thuộc tính được đưa vào representation.

Trong ví dụ, projection có tên `customerSummary`. Tên này không phụ thuộc tên interface `CustomerSummary`. Client phải dùng đúng giá trị `name`.

### 2.1. Chọn projection bằng query parameter

Sau khi projection được đăng ký, client có thể yêu cầu:

~~~http
GET /customers/42?projection=customerSummary
Accept: application/hal+json
~~~

Spring Data REST trả representation theo projection đã chọn. Ví dụ:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an@example.com",
  "_links": {
    "self": {
      "href": "http://localhost:8080/customers/42?projection=customerSummary"
    }
  }
}
~~~

Nếu resource hỗ trợ projection, link self có thể được biểu diễn dưới dạng URI template với biến `projection`:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/customers/42{?projection}",
      "templated": true
    }
  }
}
~~~

Client có thể khám phá lựa chọn representation từ metadata hypermedia và thêm query parameter tương ứng.

### 2.2. Tên projection phải khớp với annotation

Ví dụ:

~~~java
@Projection(name = "summary", types = Customer.class)
public interface CustomerNameAndEmail {
    String getFirstName();
    String getEmail();
}
~~~

Request đúng:

~~~http
GET /customers/42?projection=summary
~~~

Giá trị query parameter phải là `summary` vì đó là giá trị của thuộc tính `name`, không phải tên interface `CustomerSummary`.

### 2.3. Có thể định nghĩa nhiều projection cho cùng một type

Ví dụ:

~~~java
@Projection(name = "summary", types = Customer.class)
public interface CustomerSummary {
    String getFirstName();
    String getLastName();
    String getEmail();
}
~~~

~~~java
@Projection(name = "contact", types = Customer.class)
public interface CustomerContact {
    String getFirstName();
    String getLastName();
    String getEmail();
    String getPhone();
}
~~~

~~~java
@Projection(name = "details", types = Customer.class)
public interface CustomerDetails {
    String getFirstName();
    String getLastName();
    String getEmail();
    String getPhone();
    Address getAddress();
}
~~~

Client có thể chọn view phù hợp với tác vụ:

| Request | Mục đích |
|---|---|
| `?projection=summary` | Danh sách hoặc kết quả tìm kiếm |
| `?projection=contact` | Màn hình thông tin liên hệ |
| `?projection=details` | Màn hình chi tiết |

Nên đặt tên theo mục đích sử dụng của representation, giữ tên ngắn, ổn định và có ý nghĩa đối với client.

## 3. Spring Data REST tìm projection ở đâu?

Spring Data REST tự động phát hiện các interface có `@Projection` nếu chúng nằm trong cùng package với domain type hoặc một subpackage của package đó.

Ví dụ cấu trúc:

~~~text
com.example.store
├── customer
│   ├── Customer.java
│   ├── CustomerSummary.java
│   ├── CustomerDetails.java
│   └── CustomerRepository.java
└── address
    ├── Address.java
    └── AddressRepository.java
~~~

Vì các projection nằm trong package `com.example.store.customer` cùng package với `Customer`, chúng được phát hiện theo quy tắc package scan.

Nếu đặt projection ở một package không thuộc phạm vi đó, Spring Data REST sẽ không tự động tìm thấy chỉ vì interface có annotation. Khi ấy cần đăng ký projection tường minh.

### 3.1. Đăng ký thủ công bằng RepositoryRestConfiguration

Có thể đăng ký projection thông qua `RepositoryRestConfiguration`:

~~~java
@Configuration
public class DataRestConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getProjectionConfiguration()
            .addProjection(CustomerSummary.class);
    }
}
~~~

Các import:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
~~~

Projection vẫn cần được đánh dấu bằng `@Projection`. Cấu hình thủ công chỉ bổ sung cách đăng ký khi package scan mặc định không phù hợp.

### 3.2. Chọn một chiến lược đăng ký nhất quán

Với module nhỏ, đặt projection gần domain type thường đơn giản và dễ tìm. Với ứng dụng chia nhiều module hoặc tổ chức package theo lớp API, có thể dùng đăng ký tường minh.

Dù chọn cách nào, hãy bảo đảm projection thuộc đúng domain type và tên projection không bị nhầm giữa các tài nguyên.

## 4. Excerpt projection là gì?

Excerpt là một projection được áp dụng tự động khi resource xuất hiện trong collection hoặc được nhúng trong một resource liên quan. Nó tạo representation xem trước cho collection mà không buộc client gửi query parameter `projection` ở từng phần tử.

Ví dụ, danh sách khách hàng thường chỉ cần tên và email. Có thể dùng `CustomerSummary` làm excerpt:

~~~java
@RepositoryRestResource(
    path = "customers",
    excerptProjection = CustomerSummary.class
)
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Khi client yêu cầu collection:

~~~http
GET /customers
Accept: application/hal+json
~~~

các customer được nhúng trong collection sẽ dùng excerpt projection. Representation có thể tương tự:

~~~json
{
  "_embedded": {
    "customers": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "email": "an@example.com",
        "_links": {
          "self": {
            "href": "http://localhost:8080/customers/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/customers"
    }
  }
}
~~~

### 4.1. Excerpt không tự động áp dụng cho item resource

Đây là điểm cần nhớ khi thiết kế API:

- `GET /customers` trả collection; excerpt projection được dùng cho các phần tử trong collection.
- `GET /customers/42` trả item resource; excerpt không tự động áp dụng chỉ vì repository đã khai báo `excerptProjection`.
- Client có thể chọn projection cho item resource bằng `?projection=...` nếu projection đó được đăng ký.

Excerpt được thiết kế để cung cấp preview mặc định trong collection. Khi cấu hình excerpt, cần kiểm tra riêng response collection và response item.

### 4.2. Excerpt có thể nhúng dữ liệu quan hệ

Giả sử customer có quan hệ đến address. Nếu muốn collection hiển thị thêm thành phố mà không cần client gọi thêm endpoint address cho từng customer, có thể tạo projection lồng:

~~~java
@Projection(name = "summaryWithCity", types = Customer.class)
public interface CustomerSummaryWithCity {

    String getFirstName();

    String getLastName();

    String getEmail();

    AddressSummary getAddress();

    interface AddressSummary {
        String getCity();
        String getCountry();
    }
}
~~~

Sau đó cấu hình:

~~~java
@RepositoryRestResource(
    path = "customers",
    excerptProjection = CustomerSummaryWithCity.class
)
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Phần address được biểu diễn inline theo các getter trong nested projection. Link quan hệ có thể vẫn được công bố để client điều hướng đến resource address riêng.

### 4.3. Cân nhắc tác động tương thích của excerpt

Cấu hình `excerptProjection` thay đổi representation mặc định của collection. Nếu API đã được client sử dụng, việc thêm hoặc thay excerpt có thể làm response khác trước.

Trước khi thay đổi excerpt trong API đã phát hành, hãy kiểm tra:

- Client có phụ thuộc vào các thuộc tính hiện tại hay không.
- Các trường bị bỏ khỏi collection representation có còn cần cho client cũ không.
- Dữ liệu quan hệ được nhúng có làm tăng kích thước response không.
- Có cần version hoặc một giai đoạn chuyển đổi hay không.

## 5. Projection lồng cho quan hệ

Projection có thể trả về một interface khác để giới hạn dữ liệu của quan hệ. Điều này hữu ích khi entity có association lớn nhưng client chỉ cần một vài thuộc tính.

Ví dụ:

~~~java
@Projection(name = "customerDetails", types = Customer.class)
public interface CustomerDetails {

    String getFirstName();

    String getLastName();

    AddressView getAddress();

    interface AddressView {
        String getCity();
        String getCountry();
    }
}
~~~

Projection không yêu cầu client phải nhận toàn bộ object graph của address. Chỉ các thuộc tính được khai báo trong nested interface được đưa vào view.

Nếu quan hệ là collection, có thể khai báo collection của projection interface:

~~~java
@Projection(name = "orderSummary", types = Order.class)
public interface OrderSummary {

    String getOrderNumber();

    List<LineItemView> getItems();

    interface LineItemView {
        String getProductName();
        Integer getQuantity();
    }
}
~~~

Import:

~~~java
import java.util.List;
~~~

Cần kiểm tra cách serializer xử lý association theo cấu hình repository và loại quan hệ. Một association được quản lý bởi repository riêng có thể đồng thời có link điều hướng; projection lồng có thể cung cấp dữ liệu inline theo view được chọn.

## 6. Computed property bằng @Value

Projection không chỉ chọn thuộc tính có sẵn. Nó còn có thể tạo thuộc tính chỉ đọc từ dữ liệu của entity bằng Spring Expression Language (SpEL).

Ví dụ, entity có `firstName` và `lastName`. Projection có thể tạo `fullName`:

~~~java
@Projection(name = "withFullName", types = Customer.class)
public interface CustomerWithFullName {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();

    String getEmail();
}
~~~

Import:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.rest.core.config.Projection;
~~~

Representation có thể chứa:

~~~json
{
  "fullName": "An Nguyen",
  "email": "an@example.com"
}
~~~

`target` tham chiếu đối tượng domain đang được chiếu. Biểu thức kết hợp hai thuộc tính và trả về một giá trị chỉ đọc. Không cần thêm trường `fullName` vào entity hoặc lưu nó trong database.

### 6.1. Dùng computed property có kiểm soát

SpEL giúp tạo trường tiện dụng cho client, nhưng biểu thức phức tạp có thể làm projection khó kiểm thử và khó bảo trì.

Nên dùng cho phép biến đổi đơn giản, dễ hiểu như:

- Ghép họ và tên.
- Tạo nhãn hiển thị từ các trường.
- Tính giá trị mô tả chỉ đọc đơn giản.

Với logic nghiệp vụ phức tạp, hãy cân nhắc service hoặc representation model được xây dựng tường minh.

## 7. Projection và dữ liệu bị @JsonIgnore

Projection có thể làm xuất hiện dữ liệu mà Jackson thông thường bỏ qua bằng `@JsonIgnore`. Đây là một rủi ro bảo mật quan trọng.

Ví dụ entity:

~~~java
@Entity
public class Account {

    @Id
    @GeneratedValue
    private Long id;

    private String username;

    @JsonIgnore
    private String passwordHash;

    // getters and setters
}
~~~

Import:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
~~~

`@JsonIgnore` ngăn trường `passwordHash` xuất hiện trong serialization thông thường. Tuy nhiên, nếu projection khai báo getter tương ứng:

~~~java
@Projection(name = "accountInternal", types = Account.class)
public interface AccountInternal {

    String getUsername();

    String getPasswordHash();
}
~~~

projection có thể đưa trường đó vào representation. Spring Data REST không thể tự biết thuộc tính nào nhạy cảm trong nghiệp vụ của ứng dụng.

Vì vậy:

- Không dùng projection để xuất password, password hash, token, secret hoặc dữ liệu nội bộ.
- Không xem `@JsonIgnore` là ranh giới phân quyền.
- Không công bố projection nhạy cảm chỉ với kỳ vọng client sẽ không biết tên projection.
- Kiểm tra quyền truy cập và dữ liệu trả về ở server.
- Viết test xác nhận các trường nhạy cảm không xuất hiện trong bất kỳ representation nào.

Projection là hợp đồng trình bày dữ liệu, không phải cơ chế bảo mật.

## 8. Khám phá projection qua ALPS

Spring Data REST công bố metadata ALPS (Application-Level Profile Semantics) để mô tả các descriptor và transition của API. Client có thể theo link `profile` ở root resource để khám phá profile.

Với repository `customers`, tài liệu ALPS tương ứng có thể được tìm tại đường dẫn dạng:

~~~http
GET /alps/customers
Accept: application/alps+json
~~~

Trong ALPS, projection được liệt kê dưới descriptor `projection` của transition GET. Mỗi projection có descriptor mang tên khai báo trong `@Projection(name = "...")` và các descriptor con mô tả thuộc tính được xuất bản.

Ví dụ rút gọn:

~~~json
{
  "id": "get-customer",
  "name": "customer",
  "type": "SAFE",
  "descriptors": [
    {
      "name": "projection",
      "type": "SEMANTIC",
      "descriptors": [
        {
          "name": "customerSummary",
          "type": "SEMANTIC",
          "descriptors": [
            {
              "name": "firstName",
              "type": "SEMANTIC"
            },
            {
              "name": "lastName",
              "type": "SEMANTIC"
            },
            {
              "name": "email",
              "type": "SEMANTIC"
            }
          ]
        }
      ]
    }
  ]
}
~~~

ALPS giúp client hoặc công cụ khám phá các lựa chọn projection mà API công bố. Client vẫn cần hiểu quy ước query parameter và cách representation được trả về.

## 9. Kiểm thử projection với MockMvc

Kiểm thử cần xác nhận đúng projection được áp dụng và các thuộc tính ngoài projection không xuất hiện.

Với Spring Boot, có thể dùng `@SpringBootTest` kết hợp `@AutoConfigureMockMvc` để kiểm tra toàn bộ Spring Data REST configuration.

Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerProjectionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsCustomerSummaryProjection() throws Exception {

        mvc.perform(get("/customers/42")
                .param("projection", "customerSummary")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.firstName").value("An"))
            .andExpect(jsonPath("$.lastName").value("Nguyen"))
            .andExpect(jsonPath("$.email").value("an@example.com"))
            .andExpect(jsonPath("$.phone").doesNotExist())
            .andExpect(jsonPath("$.address").doesNotExist());
    }
}
~~~

Ví dụ giả định dữ liệu customer có ID 42 đã được seed trước test. Trong suite thực tế, nên tạo dữ liệu bằng repository trong setup hoặc dùng fixture rõ ràng.

Các import chính:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

### 9.1. Kiểm thử excerpt trên collection

Excerpt projection được áp dụng tự động cho collection, vì vậy cần test riêng:

~~~java
mvc.perform(get("/customers")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.customers[0].firstName").exists())
    .andExpect(jsonPath("$._embedded.customers[0].email").exists())
    .andExpect(jsonPath("$._embedded.customers[0].phone").doesNotExist());
~~~

Tên relation trong `_embedded` phụ thuộc cấu hình repository và resource rel. Hãy dùng đúng rel được ứng dụng công bố.

### 9.2. Kiểm thử item resource không tự nhận excerpt

Nếu repository khai báo excerpt, vẫn cần xác nhận item resource có representation mặc định theo hợp đồng hoặc projection được yêu cầu:

~~~java
mvc.perform(get("/customers/42")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.firstName").exists());
~~~

Sau đó kiểm thử request có query parameter projection để xác nhận view cụ thể. Điều này giúp tránh nhầm lẫn giữa excerpt mặc định của collection và projection được client chọn.

### 9.3. Kiểm thử dữ liệu nhạy cảm

Nếu entity có thuộc tính bí mật, hãy xác nhận nó không xuất hiện trong representation được phép:

~~~java
mvc.perform(get("/accounts/42")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.passwordHash").doesNotExist());
~~~

Cũng cần rà soát mọi projection đã đăng ký để bảo đảm không projection nào vô tình đưa trường nhạy cảm vào response.

## 10. Projection ảnh hưởng đến hiệu năng như thế nào?

Projection thường làm response gọn hơn vì chỉ đưa các getter được khai báo vào representation. Điều đó có thể giảm kích thước JSON và lượng dữ liệu truyền qua mạng.

Tuy nhiên, không được đồng nhất response nhỏ hơn với database query luôn nhẹ hơn.

Các tình huống cần xem xét:

- Entity đã được tải đầy đủ trước khi projection được áp dụng.
- Getter của association lazy có thể kích hoạt truy vấn bổ sung.
- Nested projection có thể truy cập nhiều quan hệ.
- Collection excerpt có thể gây N+1 nếu từng phần tử tải quan hệ riêng.
- Computed property có thể truy cập thuộc tính ngoài dự kiến.

Hãy dùng SQL logging, query metrics và integration test để xác định fetch behavior thực tế. Nếu cần tối ưu database, hãy dùng entity graph, fetch join, batch fetching hoặc query projection thích hợp trong Spring Data JPA.

## 11. Projection khác DTO và custom controller như thế nào?

Projection, DTO và custom controller đều có thể tạo representation khác entity, nhưng giải quyết những nhu cầu khác nhau.

| Cơ chế | Phù hợp khi | Đặc điểm |
|---|---|---|
| Spring Data REST projection | Muốn nhiều view khai báo trên repository resource | Interface, getter và query parameter |
| Excerpt projection | Muốn collection có preview mặc định | Tự áp dụng khi resource nằm trong collection |
| DTO projection trong repository query | Muốn kiểm soát kiểu trả về và có thể tối ưu query | Có thể dùng interface hoặc class-based query projection |
| Custom controller + DTO | Cần logic API hoặc cấu trúc response đặc thù | Kiểm soát toàn bộ endpoint và representation |

Nếu nhu cầu chỉ là một số view đọc khác nhau của repository resource, projection giữ API gọn và phù hợp với cơ chế hypermedia của Spring Data REST.

Nếu endpoint cần tổng hợp dữ liệu từ nhiều aggregate, áp dụng logic nghiệp vụ riêng hoặc có hợp đồng response phức tạp, custom controller và DTO có thể rõ ràng hơn.

## 12. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng tên interface thay cho `@Projection.name` | Query parameter không chọn đúng view | Dùng đúng giá trị `name` |
| Đặt projection ngoài package được scan | Spring Data REST không phát hiện projection | Đặt gần domain type hoặc đăng ký thủ công |
| Quên `@Projection` | Interface không được nhận diện là projection | Thêm annotation và `types` |
| Nghĩ excerpt áp dụng cho item resource | Item response khác kỳ vọng | Kiểm thử collection và item riêng |
| Dùng projection như cơ chế phân quyền | Có thể lộ dữ liệu nhạy cảm | Kiểm tra quyền và trường xuất bản ở server |
| Cho rằng `@JsonIgnore` luôn chặn projection | Projection có thể đưa field bị ignore vào response | Không khai báo field nhạy cảm trong projection |
| Dùng nested projection quá sâu | Response lớn hoặc phát sinh truy vấn phụ | Giới hạn graph và đo query thực tế |
| Coi projection là tối ưu SQL tự động | Kỳ vọng sai về fetch plan | Dùng query projection/fetch plan khi cần |
| Thay excerpt sau khi API đã phát hành | Client cũ có thể bị ảnh hưởng | Đánh giá tương thích và kiểm thử hợp đồng |
| Không kiểm thử tên property | Response thay đổi âm thầm | Viết JSONPath contract test |

## 13. Quy trình thiết kế projection

Khi thêm projection vào Spring Data REST, hãy đi theo trình tự:

1. Xác định client và tác vụ cần một view khác của domain resource.
2. Liệt kê chính xác các thuộc tính cần xuất bản.
3. Loại bỏ dữ liệu nhạy cảm và trường nội bộ khỏi projection.
4. Tạo interface có `@Projection`, `name` và `types`.
5. Đặt interface trong package của domain type hoặc subpackage; nếu không, đăng ký thủ công.
6. Chọn projection bằng `?projection=...` khi client cần view tường minh.
7. Dùng `excerptProjection` khi collection cần preview mặc định.
8. Tạo nested projection hoặc computed property chỉ khi có nhu cầu rõ ràng.
9. Kiểm tra ALPS profile để xác nhận projection được công bố.
10. Kiểm thử item, collection, nested data và trường nhạy cảm.
11. Đo query behavior nếu projection truy cập association.
12. Đánh giá khả năng tương thích trước khi thay đổi excerpt hoặc projection đã phát hành.

## 14. Kết luận

Projection trong Spring Data REST cung cấp các view khác nhau trên cùng một domain type thông qua interface được đánh dấu `@Projection`. Client chọn projection bằng giá trị `name` trong query parameter `projection`. Với collection resource, `excerptProjection` cho phép áp dụng một projection mặc định để tạo preview cho các phần tử được nhúng; excerpt không tự động áp dụng cho item resource.

Nested projection và `@Value` có thể tạo representation phù hợp hơn với nhu cầu client, nhưng mọi getter đều cần được xem xét về dữ liệu nhạy cảm và chi phí tải quan hệ. Projection không thay thế phân quyền và không bảo đảm database chỉ đọc các trường được khai báo. Khi đặt projection đúng package, công bố tên rõ ràng, kiểm thử HAL representation và theo dõi query behavior, Spring Data REST có thể phục vụ nhiều nhu cầu đọc mà vẫn giữ domain model và repository thống nhất.

## Tài liệu tham khảo

- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): khai báo projection, chọn qua query parameter, đăng ký, ALPS và excerpt projection.
- [Spring Data Commons Reference — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html): interface projection, nested projection và các dạng projection ở tầng repository.
- [Spring Data REST API — Projection](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/Projection.html): annotation đánh dấu projection và thuộc tính `name`, `types`.
- [Spring Data REST API — RepositoryRestConfiguration](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html): cấu hình projection trong Spring Data REST.

