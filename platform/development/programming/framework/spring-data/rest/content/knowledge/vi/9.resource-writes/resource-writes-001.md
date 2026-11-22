# POST tạo tài nguyên và xác định các thuộc tính được phép ghi trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể tạo một repository resource bằng HTTP POST; hiểu cách Spring Data REST chuyển JSON request thành domain object; xác định thuộc tính nào client được phép gửi; và bảo vệ các trường do server quản lý như ID, trạng thái, chủ sở hữu hoặc thông tin audit.

## 1. POST tạo resource ở collection endpoint

Với một repository được Spring Data REST công bố, collection resource thường hỗ trợ `POST` để tạo entity mới. Ví dụ, nếu repository `CustomerRepository` được export dưới path `/customers`, client gửi request đến collection endpoint:

```http
POST /customers HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Ada Lovelace",
  "email": "ada@example.com"
}
```

Spring Data REST đọc body, chuyển các thuộc tính được chấp nhận thành một `Customer`, rồi gọi cơ chế lưu của repository. Khi tạo thành công, response thường có status `201 Created`, header `Location` trỏ đến resource vừa tạo và representation của resource nếu request/cấu hình yêu cầu trả body.

Ví dụ response rút gọn:

```http
HTTP/1.1 201 Created
Location: http://localhost:8080/customers/42
Content-Type: application/hal+json
```

```json
{
  "name": "Ada Lovelace",
  "email": "ada@example.com",
  "_links": {
    "self": { "href": "http://localhost:8080/customers/42" }
  }
}
```

`POST` vào collection tạo một resource mới. Cần phân biệt với `PUT` hoặc `PATCH` trên item resource, vốn thường dùng để thay thế hoặc cập nhật resource đã tồn tại. Không nên gửi ID do client tự chọn nếu ID được database/server sinh ra.

## 2. Content-Type và Accept trong request tạo resource

Hai header có vai trò khác nhau:

- `Content-Type` mô tả định dạng body mà client gửi. Với JSON thông thường, dùng `application/json`.
- `Accept` mô tả representation mà client muốn nhận lại. Nếu cần response có HAL links, dùng `application/hal+json`.

Ví dụ:

```http
POST /customers
Content-Type: application/json
Accept: application/hal+json
```

Request body là JSON, nhưng response có thể là HAL JSON. Nếu client không cần hypermedia, có thể yêu cầu `Accept: application/json`, tùy theo cấu hình media type của Spring Data REST.

Khi request có `Content-Type` không được endpoint hỗ trợ, server có thể trả `415 Unsupported Media Type`. Khi giá trị `Accept` không khớp representation server có thể cung cấp, server có thể trả `406 Not Acceptable`.

## 3. JSON request được ánh xạ vào domain object như thế nào?

Spring Data REST sử dụng cơ chế HTTP message conversion của Spring và Jackson để deserialize request body thành đối tượng domain tương ứng với repository. Các thuộc tính JSON có thể được gán thông qua constructor/creator, setter hoặc field tùy theo cách domain class và Jackson được cấu hình.

Ví dụ entity đơn giản:

```java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private String email;

    protected Customer() {
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

Client có thể gửi:

```json
{
  "name": "Ada Lovelace",
  "email": "ada@example.com"
}
```

Jackson ánh xạ các thuộc tính phù hợp vào `Customer`; sau đó Spring Data REST lưu entity qua repository. Khả năng ghi thực tế còn phụ thuộc constructor, setter/field visibility, Jackson annotations, custom deserializers, message converters và cấu hình `ObjectMapper`.

Do đó, không nên suy luận rằng mọi field trong entity đều được phép ghi chỉ vì field đó tồn tại trong Java class. Cũng không nên cho rằng ẩn một field trên giao diện client là đủ để ngăn request giả mạo gửi field đó.

## 4. Xác định thuộc tính nào client được phép ghi

Hãy phân loại thuộc tính theo nguồn dữ liệu và trách nhiệm sở hữu trước khi thiết kế request contract:

| Nhóm thuộc tính | Ví dụ | Chính sách thường dùng |
| --- | --- | --- |
| Dữ liệu người dùng nhập | `name`, `email`, `description` | Cho phép client gửi, kèm validation |
| Dữ liệu do server/database sinh | `id`, `createdAt`, `version` | Server quản lý; không nhận giá trị ghi từ client |
| Dữ liệu audit | `createdBy`, `lastModifiedAt` | Lấy từ auditing/security context |
| Dữ liệu phân quyền hoặc sở hữu | `role`, `ownerId`, `tenantId` | Xác định từ danh tính đã xác thực hoặc business rule |
| Trạng thái nghiệp vụ | `approved`, `accountStatus`, `balance` | Chỉ thay đổi qua thao tác nghiệp vụ được cho phép |
| Bí mật đầu vào | `password`, `inviteCode` | Chỉ nhận khi cần; không trả lại trong response |

Một request tạo Customer có thể chỉ cho phép `name` và `email`. ID, thời điểm tạo, chủ sở hữu và trạng thái ban đầu được server gán. Việc phân loại này tạo ra allowlist rõ ràng cho từng thao tác tạo resource.

## 5. Kiểm soát serialization và deserialization bằng Jackson

Jackson cung cấp các annotation hữu ích để xác định một thuộc tính được đọc hoặc ghi qua JSON như thế nào.

### @JsonProperty(access = READ_ONLY)

Thuộc tính được đưa vào output JSON nhưng bị bỏ qua khi deserialize input JSON. Đây là lựa chọn phù hợp cho ID, trạng thái do server quản lý hoặc timestamp được sinh tự động:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class Customer {

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String accountStatus;

    // Các thuộc tính khác
}
```

Nếu client gửi `id` hoặc `accountStatus`, Jackson không dùng các giá trị đó để gán vào object qua thuộc tính read-only. Server vẫn có thể trả các giá trị này trong response.

### @JsonProperty(access = WRITE_ONLY)

Thuộc tính được nhận từ input JSON nhưng không được serialize ra output JSON. Dùng cho dữ liệu đầu vào nhạy cảm mà API cần nhận, ví dụ mã mời hoặc mật khẩu:

```java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private String inviteCode;
```

Server vẫn phải xác minh mã mời, xử lý an toàn và tránh lưu bí mật ở dạng không phù hợp. `WRITE_ONLY` chỉ điều khiển JSON output; nó không tự xác thực giá trị hay mã hóa dữ liệu.

### @JsonIgnore

`@JsonIgnore` loại thuộc tính khỏi quá trình JSON mapping theo cấu hình Jackson, thường có nghĩa thuộc tính không được đọc từ request và cũng không xuất hiện trong response:

```java
@JsonIgnore
private String internalNote;
```

Dùng khi thuộc tính hoàn toàn không thuộc API representation. Nếu cần đọc thuộc tính trong response nhưng cấm client ghi, hãy cân nhắc `READ_ONLY` thay vì `@JsonIgnore`.

Các annotation cần được đặt trên đúng logical property. Với class dùng getter/setter, constructor binding hoặc Lombok, hãy kiểm tra Jackson đang nhận diện property từ member nào để tránh cấu hình không có hiệu lực như dự kiến.

## 6. Ví dụ: chỉ cho phép gửi name và email

Giả sử server phải tự sinh ID, trạng thái tài khoản và thời điểm tạo. Có thể mô tả policy bằng entity như sau:

```java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    @NotBlank
    @Size(max = 120)
    private String name;

    @Email
    @NotBlank
    private String email;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String accountStatus;

    @CreatedDate
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Instant createdAt;

    protected Customer() {
    }

    // Constructor, getters và setters phù hợp
}
```

Request hợp lệ có thể là:

```http
POST /customers
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Ada Lovelace",
  "email": "ada@example.com"
}
```

Request cố gắng tự đặt ID và trạng thái:

```json
{
  "id": 999,
  "name": "Ada Lovelace",
  "email": "ada@example.com",
  "accountStatus": "ADMIN"
}
```

Với các property được đánh dấu `READ_ONLY`, Jackson bỏ qua giá trị đầu vào cho các property đó. Server cần tự gán `accountStatus` theo quy tắc tạo tài khoản và database/provider sinh ID.

Ví dụ trên minh họa hướng thiết kế. Để chạy được trong ứng dụng thực tế, cần bổ sung import, cấu hình JPA auditing nếu dùng `@CreatedDate`, constructor/setter và validation dependency phù hợp với phiên bản Spring Boot.

## 7. Validation và quy tắc nghiệp vụ trước khi lưu

Kiểm soát thuộc tính được ghi cần đi cùng validation. Các annotation Bean Validation như `@NotBlank`, `@Email`, `@Size`, `@Min` và `@Max` mô tả ràng buộc dữ liệu. Khi Bean Validation được tích hợp vào ứng dụng, request vi phạm ràng buộc có thể bị từ chối trước khi lưu.

Một số quy tắc cần logic nghiệp vụ, ví dụ:

- Email đã được sử dụng chưa?
- Người dùng hiện tại có quyền tạo customer thuộc tenant được chỉ định không?
- Mã mời có hợp lệ và còn hiệu lực không?
- Trạng thái khởi tạo có được phép chuyển sang trạng thái client yêu cầu không?

Không nên để client tự quyết định `ownerId`, `tenantId`, `role` hoặc trạng thái nhạy cảm chỉ bằng cách gửi thêm thuộc tính JSON. Hãy lấy thông tin người dùng từ security context và thực hiện kiểm tra quyền ở server.

Spring Data REST hỗ trợ repository event handlers để áp dụng logic quanh thời điểm lưu. Ví dụ dùng `@HandleBeforeCreate` để gán thông tin server quản lý hoặc kiểm tra điều kiện trước khi tạo:

```java
@Component
@RepositoryEventHandler(Customer.class)
public class CustomerEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Customer customer) {
        // Gán trạng thái ban đầu và kiểm tra quy tắc nghiệp vụ
    }
}
```

Handler cần được đăng ký như Spring bean. Với logic phức tạp hoặc nhiều bước, cân nhắc chuyển nghiệp vụ vào service chuyên trách và thiết kế custom controller/application service thay vì nhồi toàn bộ quy tắc vào entity event handler.

## 8. Thuộc tính quan hệ và association

Entity có thể chứa quan hệ đến resource khác, ví dụ Customer thuộc về một Address hoặc Order thuộc về một Customer. Spring Data REST công bố association thông qua các link và association resources.

Khi tạo hoặc cập nhật quan hệ, client thường tham chiếu URI của resource liên quan theo hợp đồng của association endpoint. Không nên mặc định rằng gửi một object lồng nhau bất kỳ sẽ tự tạo toàn bộ graph entity theo cách mong muốn.

Hãy xác định rõ:

- Quan hệ nào client được phép chọn?
- Resource liên quan có tồn tại và được phép truy cập không?
- Người dùng hiện tại có quyền liên kết hai resource đó không?
- Quan hệ có được thay đổi trong thao tác POST này hay phải qua association endpoint riêng?

Các association có thể có media type hoặc cách gọi riêng. Kiểm tra link trong HAL và tài liệu endpoint để biết cách gửi URI reference đúng định dạng. Đừng tin một URI chỉ vì client đã gửi nó; server vẫn phải xác minh quyền truy cập và tính hợp lệ của resource đích.

## 9. Phân biệt quyền ghi field với việc công bố endpoint

Một số annotation và cấu hình có tên gần nhau nhưng điều khiển các lớp khác nhau:

- `@RepositoryRestResource(exported = false)` ẩn toàn bộ repository khỏi REST export.
- `@RestResource(exported = false)` ẩn một method hoặc association resource.
- `@JsonProperty(access = READ_ONLY)` điều khiển JSON deserialization/serialization của một property.
- `@JsonIgnore` loại property khỏi JSON mapping.
- Spring Security quyết định ai được phép gọi endpoint và thực hiện thao tác.

Ẩn repository hoặc method không tạo ra field-level write policy. Ngược lại, đánh dấu property là read-only cũng không tự bảo vệ endpoint khỏi người dùng chưa được xác thực. Cần kết hợp JSON mapping, validation, authorization và quy tắc nghiệp vụ.

Các projection của Spring Data REST chủ yếu điều khiển representation đọc. Không dùng projection như một allowlist cho các thuộc tính mà POST được phép ghi. Hãy kiểm soát input bằng Jackson/domain binding và validation phù hợp.

## 10. Cách kiểm tra POST trong thực tế

Khi triển khai hoặc debug một endpoint tạo resource, thực hiện các kiểm tra sau:

1. Xác định collection path từ API root HAL hoặc cấu hình `@RepositoryRestResource(path = "...")`.
2. Gửi `POST` với `Content-Type: application/json` và các field được phép.
3. Kiểm tra status code, header `Location` và response `Content-Type`.
4. Đọc lại item resource theo URI trong `Location` để xác nhận dữ liệu được lưu.
5. Thử gửi thêm một field server-managed như `id` hoặc `accountStatus`; xác nhận server không nhận giá trị do client áp đặt.
6. Thử gửi dữ liệu không hợp lệ để xác nhận validation hoạt động.
7. Thử request không có quyền hoặc liên kết đến resource ngoài phạm vi được phép để xác nhận authorization được kiểm tra.

Ví dụ dùng curl:

```bash
curl -i -X POST http://localhost:8080/customers \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"name":"Ada Lovelace","email":"ada@example.com"}'
```

Nếu endpoint trả `400 Bad Request`, đọc response để xác định field hoặc validation nào không hợp lệ. Nếu trả `403 Forbidden`, kiểm tra authorization. Nếu trả `415 Unsupported Media Type`, kiểm tra `Content-Type`. Nếu trả `404 Not Found`, xác nhận collection path và base path.

## Tóm tắt

- `POST` vào collection resource tạo entity mới; response thành công thường trả `201 Created` và `Location`.
- `Content-Type` mô tả body gửi lên; `Accept` chọn representation response.
- JSON request được Jackson ánh xạ vào domain object; khả năng ghi phụ thuộc cấu hình binding và property annotations.
- `READ_ONLY` cho phép trả property nhưng bỏ qua giá trị client gửi; `WRITE_ONLY` nhận input nhưng không trả property; `@JsonIgnore` loại property khỏi JSON mapping.
- ID, owner, tenant, role, trạng thái và audit metadata nên do server quản lý khi đó là trách nhiệm của server.
- Kết hợp field policy với validation, authorization và kiểm tra association ở server.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Handling associations](https://docs.spring.io/spring-data/rest/reference/handling-associations.html)
- [Spring Data REST — Events and handlers](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Jackson — JsonProperty.Access API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html)
- [Jakarta Bean Validation](https://beanvalidation.org/)
