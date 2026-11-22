# Phân biệt excerpt mặc định và projection do máy khách yêu cầu

Spring Data REST có thể trả về nhiều cách biểu diễn cho cùng một entity. Một collection thường cần representation gọn để hiển thị danh sách; khi mở một item, client có thể cần thêm thuộc tính; một màn hình khác lại chỉ cần một nhóm field riêng. **Excerpt projection** cho phép repository chọn trước representation mặc định cho các entity được nhúng trong collection. **Projection được client yêu cầu** cho phép client chọn một projection đã được ứng dụng công bố bằng tham số `projection`.

Hai cơ chế cùng dựa trên projection interface, nhưng khác nhau ở nơi chọn và thời điểm áp dụng.

## 1. Projection là gì?

Projection là một góc nhìn của entity, chỉ công bố những thuộc tính mà một use case cần. Trong Spring Data REST, projection thường được khai báo bằng interface có annotation `@Projection`.

Ví dụ entity:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phone;
    private String internalNote;

    // getters and setters
}
```

Projection chỉ hiển thị thông tin tóm tắt:

```java
@Projection(name = "summary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();

    String getEmail();
}
```

Khi representation dùng projection này, các thuộc tính `phone` và `internalNote` không nằm trong view được định nghĩa bởi interface. Projection thay đổi hình dạng dữ liệu trả về; nó không tạo entity mới, không cập nhật database và không thay đổi mapping của domain object.

Spring Data REST phát hiện projection theo quy tắc package scanning của ứng dụng. Đặt interface ở package phù hợp với domain type và kiểm tra nó được export trước khi sử dụng trong URL. Tên trong `@Projection(name = "summary", ...)` là tên client dùng trong query parameter, không nhất thiết giống tên interface Java.

## 2. Projection do client yêu cầu

Khi ứng dụng công bố một projection, client có thể chọn nó bằng query parameter `projection`. Ví dụ:

```http
GET /people/42?projection=summary HTTP/1.1
Host: api.example.test
Accept: application/hal+json
```

Client đang yêu cầu representation của Person 42 theo projection có tên `summary`. Nếu repository và endpoint hỗ trợ projection đó, Spring Data REST trả về view tương ứng.

Projection cũng có thể được yêu cầu trên collection:

```http
GET /people?projection=summary&page=0&size=20 HTTP/1.1
Accept: application/hal+json
```

Trong trường hợp này, client yêu cầu các phần tử của collection được biểu diễn bằng projection `summary`. Tham số phân trang và sắp xếp vẫn có thể kết hợp với projection; chúng điều khiển tập kết quả và cách lấy trang, còn projection điều khiển các thuộc tính được biểu diễn.

Điểm quan trọng là client chỉ có thể chọn projection mà server đã định nghĩa và công bố. Query parameter `projection` không cho phép client tùy ý yêu cầu bất kỳ field nào trong entity.

## 3. Excerpt projection là gì?

Excerpt projection là projection được repository cấu hình làm representation mặc định cho các entity được nhúng trong collection response. Client không cần thêm `?projection=...` để kích hoạt excerpt đó.

Ví dụ:

```java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();
}
```

Repository cấu hình excerpt:

```java
@RepositoryRestResource(
    collectionResourceRel = "people",
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

Khi client đọc collection `GET /people`, các Person được nhúng trong collection sử dụng excerpt projection đã cấu hình. Client không cần biết hoặc gửi tên excerpt trong query string để nhận view mặc định đó.

Excerpt đặc biệt hữu ích khi collection có nhiều entity hoặc entity có association phức tạp. Một representation danh sách gọn giúp tránh trả lặp dữ liệu liên quan và giảm payload. Khi người dùng mở một item, client có thể gọi item resource và yêu cầu một projection chi tiết hơn nếu API công bố projection đó.

Excerpt projection được cấu hình ở repository resource. Nếu nhiều repository export cùng domain type, mỗi repository có thể cần lựa chọn excerpt phù hợp với collection resource của nó.

## 4. Khác nhau ở đâu?

| Khía cạnh | Excerpt projection | Projection do client yêu cầu |
|---|---|---|
| Ai chọn view? | Nhà phát triển cấu hình ở repository | Client chọn tên projection đã được công bố |
| Cách kích hoạt | Tự động theo cấu hình excerpt của repository | Query parameter `?projection=name` |
| Mục đích thường gặp | View mặc định gọn cho item nhúng trong collection | View cụ thể cho màn hình hoặc use case |
| Client cần biết tên? | Không cần gửi tên để dùng excerpt mặc định | Có, client gửi tên projection |
| Phạm vi cấu hình | Repository resource | Projection được định nghĩa và export cho domain type |
| Có đổi dữ liệu lưu trữ? | Không | Không |

Cả hai đều là cách tạo representation. Chúng không thay đổi entity trong database và không thay thế quy tắc phân quyền.

## 5. Excerpt thường áp dụng cho collection representation

Một điểm dễ nhầm là excerpt projection được cấu hình cho collection resource, nơi các entity được nhúng trong `_embedded`. Nó không nên được hiểu là một quy tắc tự động rút gọn mọi lần truy cập item.

Ví dụ client gọi collection:

```http
GET /people HTTP/1.1
Accept: application/hal+json
```

Response minh họa:

```json
{
  "_embedded": {
    "people": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "_links": {
          "self": {
            "href": "https://api.example.test/people/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/people"
    }
  }
}
```

Các field trong embedded Person phản ánh excerpt projection đã cấu hình. Link `self` vẫn cho phép client điều hướng đến item resource.

Khi client gọi item trực tiếp:

```http
GET /people/42 HTTP/1.1
Accept: application/hal+json
```

Representation mặc định của item có thể chứa tập thuộc tính khác với excerpt của collection. Nếu cần một view được xác định rõ, client có thể yêu cầu projection đã công bố:

```http
GET /people/42?projection=summary HTTP/1.1
Accept: application/hal+json
```

Như vậy, excerpt giải quyết cách collection trình bày các phần tử nhúng; projection query parameter cho phép client yêu cầu một view cụ thể tại endpoint hỗ trợ projection.

## 6. Nhiều projection cho nhiều use case

Một domain type có thể có nhiều projection. Ví dụ:

```java
@Projection(name = "summary", types = Person.class)
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}

@Projection(name = "contact", types = Person.class)
public interface PersonContact {
    String getFirstName();
    String getLastName();
    String getEmail();
    String getPhone();
}
```

Client có thể chọn:

```http
GET /people/42?projection=summary
GET /people/42?projection=contact
```

View `summary` phù hợp với danh sách ngắn; `contact` phù hợp với màn hình cần thông tin liên hệ. Tên và field chỉ là ví dụ; ứng dụng cần chọn dữ liệu phù hợp với hợp đồng API.

Có thể định nghĩa thuộc tính dẫn xuất trong projection bằng Spring Expression Language khi phù hợp:

```java
@Projection(name = "display", types = Person.class)
public interface PersonDisplay {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
```

Thuộc tính `displayName` được tính từ entity khi tạo representation. Nó không phải cột mới trong database và không được ghi ngược vào entity thông qua projection.

## 7. Projection và association

Projection có thể khai báo getter cho association. Khi làm vậy, representation có thể thể hiện thêm dữ liệu liên quan theo cách mà projection định nghĩa.

Ví dụ:

```java
@Projection(name = "orderSummary", types = Order.class)
public interface OrderSummary {

    String getOrderNumber();

    OrderStatus getStatus();

    Customer getCustomer();
}
```

Việc đưa association vào projection có thể làm response lớn hơn hoặc tạo cấu trúc lồng sâu. Cần xem xét số lượng quan hệ, cách serialize và khả năng truy vấn dữ liệu liên quan. Không nên đưa toàn bộ graph entity vào một projection chỉ vì có thể khai báo getter.

Excerpt projection thường hữu ích để kiểm soát độ sâu và kích thước dữ liệu trong collection. Projection do client yêu cầu hữu ích khi một use case cụ thể cần thêm association hoặc thuộc tính. Dù dùng cách nào, cần quan sát response thực tế và tránh tạo payload quá lớn.

## 8. Projection không phải cơ chế bảo mật

Nếu một field không xuất hiện trong projection, điều đó chỉ nói rằng field không được đưa vào representation đang dùng. Nó không có nghĩa caller bị cấm đọc field đó ở mọi endpoint hoặc qua mọi projection khác.

Ví dụ, không đưa `internalNote` vào `PersonSummary` không đảm bảo dữ liệu này được bảo vệ. Nếu server công bố một projection khác có field đó hoặc có endpoint khác trả field, caller vẫn có thể truy cập nếu không có authorization phù hợp.

Vì vậy:

- Dùng projection để định hình response cho từng use case.
- Dùng Spring Security để xác thực và phân quyền.
- Không công bố projection chứa dữ liệu nhạy cảm cho những caller không được phép.
- Nếu dữ liệu nhạy cảm phụ thuộc vào từng người dùng hoặc từng record, cần kiểm tra quyền ở server trên request thực tế.
- Không coi việc ẩn link hoặc bỏ field khỏi excerpt là kiểm soát truy cập.

Projection cũng không phải DTO ghi dữ liệu. Nó chủ yếu định nghĩa cách đọc/biểu diễn entity. Nếu cần một contract ghi riêng, hãy thiết kế input model hoặc endpoint phù hợp thay vì dùng projection như một cơ chế cập nhật entity.

## 9. Cách chọn giữa excerpt và projection được yêu cầu

Có thể dùng các câu hỏi sau để quyết định:

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Mọi collection của repository cần một view mặc định gọn | Cấu hình excerpt projection |
| Các màn hình khác nhau cần field khác nhau | Định nghĩa nhiều projection và để client chọn |
| Item detail cần một view cụ thể | Client yêu cầu projection trên item URI |
| Collection cần một view khác theo use case | Client yêu cầu projection trên collection nếu endpoint hỗ trợ |
| Cần bảo vệ field nhạy cảm | Authorization và thiết kế representation theo quyền; không chỉ dựa vào projection |

Một cấu hình thường dùng là đặt excerpt projection gọn cho collection, sau đó công bố thêm projection chi tiết cho những màn hình cần nhiều dữ liệu hơn. Client dùng link item để mở chi tiết và gửi `?projection=...` khi muốn một view đã được server hỗ trợ.

## 10. Quy trình client khám phá và yêu cầu projection

1. Bắt đầu từ collection link do Spring Data REST công bố.
2. Đọc representation collection và các item được nhúng; đây có thể là excerpt mặc định.
3. Theo `self` link của item để mở tài nguyên chi tiết.
4. Nếu cần một view cụ thể, dùng tên projection mà API đã công bố và thêm `projection=name`.
5. Đọc response HAL và kiểm tra các field thực tế; không giả định projection chứa mọi thuộc tính entity.
6. Giữ các kiểm tra authorization ở server cho mọi request, kể cả request chọn projection.

Khi cấu hình excerpt projection ở repository, ứng dụng quyết định trước cách collection hiển thị các item nhúng. Khi công bố projection có tên, client có thể chọn một view phù hợp với use case. Phân biệt rõ hai cơ chế giúp collection gọn, item có thể mở rộng theo nhu cầu và hợp đồng HAL dễ khám phá hơn.
