# Tuần tự hóa đối tượng được quản lý và đối tượng lồng thông thường trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể phân biệt một persistent entity được Spring Data quản lý với một object lồng thông thường; dự đoán cách từng loại xuất hiện trong JSON/HAL; hiểu vì sao association thường được biểu diễn bằng link; và chọn cách phù hợp khi cần nhúng dữ liệu, xử lý vòng tham chiếu hoặc nhận JSON đầu vào.

## 1. Hai loại object có vai trò khác nhau

Một domain model thường chứa cả entity độc lập và các object chỉ có ý nghĩa bên trong entity khác.

- **Persistent entity được quản lý** là kiểu dữ liệu mà Spring Data nhận diện qua mapping context. Entity thường có identity riêng, vòng đời lưu trữ riêng và có thể được truy cập qua repository resource nếu repository được export.
- **Object lồng thông thường** là object/value object nằm bên trong một entity, không có repository resource độc lập. Nó thường mô tả một phần giá trị của entity cha, ví dụ thông tin liên hệ, tọa độ, khoảng thời gian hoặc cấu hình hiển thị.

Hai loại object không nhất thiết được tuần tự hóa theo cùng một cách. Spring Data REST tích hợp với Jackson để hiểu metadata của persistent entity và association. Jackson cũng tuần tự hóa các bean/value object thông thường theo quy tắc property của nó.

Ví dụ một Customer có Department độc lập và ContactInfo là value object:

```java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne
    private Department department;

    @Embedded
    private ContactInfo contactInfo;

    // Constructor, getters và setters
}

@Entity
public class Department {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    // Constructor, getters và setters
}

@Embeddable
public class ContactInfo {

    private String phone;
    private String timezone;

    // Constructor, getters và setters
}
```

Trong ví dụ này, `Department` là entity có identity riêng; `ContactInfo` là giá trị được lưu cùng Customer và không có repository item resource riêng.

## 2. Persistent entity được biểu diễn thành resource và link

Khi Spring Data REST trả về một persistent entity theo HAL, response là một resource representation. Resource có dữ liệu của entity và các link hypermedia mô tả cách truy cập chính nó hoặc các quan hệ liên quan.

Ví dụ response rút gọn cho Customer:

```json
{
  "name": "Ada Lovelace",
  "contactInfo": {
    "phone": "+84-28-5555-0101",
    "timezone": "Asia/Ho_Chi_Minh"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/customers/42"
    },
    "department": {
      "href": "http://localhost:8080/customers/42/department"
    }
  }
}
```

Ở đây:

- `name` là property của Customer nên được đưa vào representation.
- `contactInfo` là object giá trị lồng bên trong nên xuất hiện như một object JSON.
- `department` là association đến một persistent entity khác; Spring Data REST biểu diễn quan hệ bằng link trong `_links`, thay vì mặc định mở rộng toàn bộ Department thành object lồng trong body.
- `self` trỏ đến item resource của Customer.

Link association thường trỏ đến association resource, qua đó client có thể đọc hoặc thay đổi quan hệ theo các thao tác mà API hỗ trợ. Khi cần thông tin Department, client theo link được server cung cấp. Cách này giữ representation gọn và giúp tránh tuần tự hóa đệ quy toàn bộ object graph.

Link cụ thể phụ thuộc repository exposure, mapping, tên relation và cấu hình. Nếu repository hoặc association bị ẩn, client có thể không thấy link tương ứng. Hãy khám phá API root và HAL response thay vì tự giả định URL.

## 3. Object lồng thông thường được tuần tự hóa inline

Một POJO hoặc value object không được nhận diện như persistent association thường được Jackson tuần tự hóa ngay bên trong property của object cha. Các property có thể đến từ getter, field hoặc constructor mapping tùy cấu hình Jackson.

Ví dụ `ContactInfo` không có ID hoặc repository riêng. Khi Customer được serialize, object này được thể hiện trực tiếp:

```json
{
  "contactInfo": {
    "phone": "+84-28-5555-0101",
    "timezone": "Asia/Ho_Chi_Minh"
  }
}
```

Không có link `self` cho ContactInfo vì nó không phải một resource độc lập. Client đọc và cập nhật các giá trị này thông qua Customer hoặc API nghiệp vụ mà ứng dụng thiết kế.

Nếu property lồng là một collection object thông thường, Jackson thường tạo một mảng JSON:

```json
{
  "preferences": [
    {
      "channel": "email",
      "enabled": true
    },
    {
      "channel": "sms",
      "enabled": false
    }
  ]
}
```

Object/value object lồng thường phù hợp với dữ liệu có vòng đời gắn với entity cha. Nếu object cần identity, quyền truy cập riêng, truy vấn độc lập hoặc được nhiều entity dùng chung, hãy cân nhắc mô hình hóa nó thành persistent entity và repository resource.

## 4. So sánh hai cách biểu diễn

| Đặc điểm | Persistent entity association | Object lồng thông thường |
| --- | --- | --- |
| Identity riêng | Thường có ID riêng | Thường không có identity độc lập |
| Repository resource | Có thể có nếu repository được export | Không có mặc định |
| HAL representation | Thường là link trong `_links` | Object JSON inline trong property |
| Truy cập chi tiết | Theo link đến resource/association | Đọc cùng representation của entity cha |
| Cập nhật quan hệ/giá trị | Dùng association resource hoặc thao tác entity phù hợp | Cập nhật property lồng qua entity cha hoặc API tùy chỉnh |
| Vòng đời | Có thể tồn tại độc lập | Thường gắn với entity cha |

Bảng này mô tả hành vi phổ biến của Spring Data REST với persistent association và value object. Kết quả thực tế còn phụ thuộc mapping context, repository exposure, projection, Jackson annotations và custom serializer.

## 5. HAL links và embedded resources không giống object lồng thông thường

Trong HAL, `_links` chứa URI để khám phá hoặc thao tác với resource. `_embedded` chứa representation của resource khác được nhúng vào response. Một object lồng thông thường lại xuất hiện như property domain bình thường, chẳng hạn `contactInfo`.

Ví dụ có thể thấy cả ba dạng trong một response:

```json
{
  "name": "Ada Lovelace",
  "contactInfo": {
    "phone": "+84-28-5555-0101"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/customers/42"
    },
    "department": {
      "href": "http://localhost:8080/customers/42/department"
    }
  },
  "_embedded": {
    "recentOrders": [
      {
        "description": "Laptop order",
        "_links": {
          "self": {
            "href": "http://localhost:8080/orders/100"
          }
        }
      }
    ]
  }
}
```

Trong ví dụ:

- `contactInfo` là value object được serialize inline.
- `_links.department` là liên kết đến association resource.
- `_embedded.recentOrders` là representation của các resource Order được nhúng theo một cơ chế representation như projection/excerpt hoặc cấu hình phù hợp.

Không nên xem mọi object lồng trong JSON là một persistent entity được embed. Hãy xem property đó là value object, association link hay embedded resource dựa trên mapping và cấu trúc HAL.

## 6. Dùng projection khi cần hiển thị dữ liệu liên quan

Mặc định, association của persistent entity thường được thể hiện bằng link. Nếu client cần một phần dữ liệu của entity liên quan ngay trong response, có thể dùng projection phù hợp thay vì mặc định tuần tự hóa toàn bộ object graph.

Ví dụ projection cho Department:

```java
@Projection(name = "departmentSummary", types = Department.class)
public interface DepartmentSummary {

    String getName();
}
```

Projection cho Customer:

```java
@Projection(name = "customerWithDepartment", types = Customer.class)
public interface CustomerWithDepartment {

    String getName();

    DepartmentSummary getDepartment();

    ContactInfo getContactInfo();
}
```

Client có thể yêu cầu projection đã được đăng ký:

```http
GET /customers/42?projection=customerWithDepartment
Accept: application/hal+json
```

Projection định nghĩa góc nhìn của representation. Việc association được thể hiện inline hoặc dưới dạng embedded/link còn phụ thuộc cách Spring Data REST áp dụng projection và loại media type. Hãy kiểm tra response thực tế và dùng đúng link/structure mà server công bố.

Với collection resource, excerpt projection có thể định nghĩa representation tóm tắt cho các phần tử được nhúng. Điều này giúp collection gọn hơn trong khi item resource vẫn có thể cung cấp representation chi tiết hơn.

## 7. Gửi JSON đầu vào: association URI và nested value object

Cách gửi request cũng phản ánh sự khác nhau giữa hai loại property.

Nếu `department` là association đến persistent entity đã tồn tại, client thường gửi URI của resource liên quan:

```http
POST /customers
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Ada Lovelace",
  "department": "http://localhost:8080/departments/7",
  "contactInfo": {
    "phone": "+84-28-5555-0101",
    "timezone": "Asia/Ho_Chi_Minh"
  }
}
```

Trong payload này:

- `department` là URI tham chiếu đến entity Department đã tồn tại.
- `contactInfo` là object JSON thông thường; Jackson deserialize nó thành ContactInfo lồng trong Customer.

Không gửi một object lồng chứa `id` của Department với giả định Spring Data REST sẽ tự tìm entity tương ứng. URI thể hiện rõ ý định tham chiếu resource đã được quản lý. Nếu muốn tạo Department mới, tạo resource đó qua collection endpoint trước, lấy URI từ `Location` hoặc link `self`, rồi sử dụng URI trong request Customer.

Với value object, gửi object JSON theo property shape mà domain class và Jackson expose. Không cần tạo repository hoặc URI cho một value object chỉ được lưu như một phần của entity cha.

## 8. Vòng tham chiếu và object graph quá sâu

Object graph có thể chứa quan hệ hai chiều:

```java
class Parent {
    private List<Child> children;
}

class Child {
    private Parent parent;
}
```

Nếu Jackson serialize trực tiếp hai phía mà không có cơ chế kiểm soát, nó có thể lặp Parent → Child → Parent cho đến khi gặp lỗi hoặc giới hạn tài nguyên. Với persistent entities, Spring Data REST thường dùng association links để tránh mở rộng vô hạn các quan hệ. Với POJO/value object thông thường, Jackson vẫn cần cấu trúc object graph có thể serialize.

Một số cách xử lý:

- Thiết kế value object theo hướng không có vòng tham chiếu; giữ object lồng là cấu trúc một chiều.
- Dùng DTO hoặc projection để xác định rõ chiều sâu dữ liệu cần trả.
- Với object graph Jackson thông thường, cân nhắc `@JsonManagedReference` và `@JsonBackReference` hoặc `@JsonIdentityInfo` khi semantics của ứng dụng phù hợp.
- Dùng `@JsonIgnore` trên property không nên xuất hiện trong JSON, sau khi xác định rõ ảnh hưởng đến cả input và output.
- Với association của Spring Data REST, ưu tiên hypermedia links hoặc projection/excerpt thay vì buộc serializer mở rộng toàn bộ entity graph.

Không thêm các Jackson annotations này một cách máy móc vào persistent association. Chúng có thể thay đổi property serialization hoặc làm mất thông tin mà Spring Data REST cần để tạo link. Kiểm tra representation sau khi cấu hình.

## 9. Ảnh hưởng của Jackson annotations và custom serializer

Jackson quyết định cách serialize POJO/value object thông qua property visibility, naming strategy, mix-in, annotations, custom serializers và modules đã đăng ký.

Một số annotation thường gặp:

- `@JsonProperty` đổi tên property hoặc điều khiển access khi đọc/ghi JSON.
- `@JsonIgnore` bỏ qua property trong quá trình JSON mapping.
- `@JsonInclude` điều khiển điều kiện đưa property vào output, ví dụ bỏ giá trị null.
- `@JsonFormat` định dạng ngày giờ hoặc kiểu dữ liệu được hỗ trợ.
- `@JsonUnwrapped` đưa property của object lồng ra cùng cấp với parent; cần cân nhắc xung đột tên và khả năng đọc ngược.

Spring Data REST cấu hình Jackson với các module riêng để xử lý persistent entity và hypermedia. Khi cần thêm serializer hoặc module tùy chỉnh, hãy mở rộng ObjectMapper theo điểm cấu hình được hỗ trợ, chẳng hạn `RepositoryRestConfigurer.configureJacksonObjectMapper(...)`. Tránh thay thế ObjectMapper mặc định bằng một instance tự tạo mà bỏ mất các module Spring Data REST/HATEOAS đã đăng ký.

Ví dụ cấu hình nên bổ sung module qua configurer:

```java
@Configuration
class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureJacksonObjectMapper(ObjectMapper objectMapper) {
        // Đăng ký custom module hoặc mix-in cần thiết.
        // Giữ lại các module mà Spring Data REST đã cấu hình.
    }
}
```

Nếu serializer tùy chỉnh thay đổi cách một persistent association được ghi ra JSON, hãy kiểm tra xem HAL links và khả năng phân giải association còn hoạt động như mong muốn hay không.

## 10. Hiệu năng, lazy loading và kích thước response

Inline nested object thuận tiện vì client nhận dữ liệu trong một response, nhưng object graph quá sâu hoặc collection lồng lớn có thể làm payload phình to. Với ORM như JPA, serialize property lazy-loaded có thể kích hoạt truy vấn bổ sung; nhiều association có thể dẫn đến N+1 queries hoặc lỗi lazy initialization nếu session đã đóng.

Association links giữ response gọn và cho phép client chỉ tải resource cần dùng, nhưng đổi lại có thể phát sinh nhiều HTTP requests. Projection và excerpt projection giúp chọn dữ liệu cần thiết; fetch plan/query tối ưu vẫn phải được thiết kế ở tầng persistence.

Khi quyết định inline hay link, cân nhắc:

- Object có identity và cần truy cập độc lập không?
- Client có thường xuyên cần toàn bộ dữ liệu lồng không?
- Collection có thể tăng kích thước lớn không?
- Quan hệ có lazy-loaded hoặc tạo nhiều truy vấn không?
- Dữ liệu có nhạy cảm hoặc cần authorization riêng không?

## 11. Cách kiểm tra representation thực tế

Sau khi triển khai, hãy kiểm tra response bằng cách:

1. Gọi API root để tìm collection link của repository.
2. Gọi item resource và xem property thông thường, `_links` và `_embedded`.
3. Xác nhận association đến persistent entity xuất hiện theo link mà server công bố.
4. Xác nhận value object/POJO được serialize inline với các property dự kiến.
5. Thử projection nếu client cần một phần dữ liệu của entity liên quan.
6. Kiểm tra các object lồng có vòng tham chiếu hoặc collection lớn.
7. Kiểm tra log SQL và số lượng query nếu serialization truy cập association JPA.
8. Thử request POST/PATCH để xác nhận association URI và nested value object được deserialize đúng.

Ví dụ đọc Customer:

```bash
curl -i http://localhost:8080/customers/42 \
  -H "Accept: application/hal+json"
```

Đọc Department qua association link được trả về:

```bash
curl -i http://localhost:8080/customers/42/department \
  -H "Accept: application/hal+json"
```

Đường dẫn association trong ví dụ chỉ minh họa; trong ứng dụng thật, hãy dùng chính URI trong `_links` của response.

## Tóm tắt

- Spring Data REST nhận diện persistent entity qua mapping metadata và biểu diễn resource/association theo quy ước hypermedia.
- Association đến entity được quản lý thường xuất hiện dưới dạng link trong `_links`, thay vì tự động nhúng toàn bộ entity.
- POJO/value object không có resource identity riêng thường được Jackson serialize inline như object hoặc array JSON bên trong entity cha.
- `_links`, `_embedded` và property object lồng thông thường là ba cấu trúc khác nhau.
- Projection/excerpt projection có thể cung cấp góc nhìn dữ liệu liên quan mà không cần serialize toàn bộ object graph.
- Với request JSON, association đến entity đã tồn tại thường dùng URI; value object lồng được gửi như object JSON.
- Kiểm soát vòng tham chiếu, lazy loading, kích thước payload và authorization khi lựa chọn cách biểu diễn.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources and representations](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing the Jackson ObjectMapper](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Projections and excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data Commons — Mapping metadata](https://docs.spring.io/spring-data/commons/reference/object-mapping.html)
- [Jackson annotations](https://github.com/FasterXML/jackson-annotations)
