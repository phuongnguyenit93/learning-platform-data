# @JsonIgnore, thuộc tính chỉ đọc và thuộc tính chỉ ghi trong Spring Data REST

Spring Data REST dùng Jackson để ánh xạ dữ liệu JSON với các thuộc tính của domain object khi đọc và ghi tài nguyên. Annotation của Jackson cho phép kiểm soát thuộc tính nào xuất hiện trong response và thuộc tính nào được nhận từ request.

Ba cách thường gặp có mục đích khác nhau:

- **@JsonIgnore** loại một thuộc tính khỏi quá trình ánh xạ JSON, thường là cả khi serialize response lẫn deserialize request.
- **@JsonProperty(access = READ_ONLY)** cho phép trả thuộc tính trong response nhưng không nhận giá trị của nó từ JSON request.
- **@JsonProperty(access = WRITE_ONLY)** nhận thuộc tính từ JSON request nhưng không đưa nó vào JSON response.

Những quy tắc này hữu ích khi công bố repository qua Spring Data REST, nhưng chúng điều khiển ánh xạ JSON chứ không phải cơ chế phân quyền hoặc ràng buộc bất biến ở database.

## 1. Jackson tham gia vào luồng JSON của Spring Data REST

Khi client đọc một item resource, Spring Data REST lấy domain object từ repository rồi dùng Jackson để tạo representation JSON hoặc HAL. Khi client gửi POST, PUT hoặc PATCH với JSON body, Jackson tham gia chuyển dữ liệu request thành các giá trị trên domain object trước khi Spring Data REST xử lý và lưu.

Ví dụ một response HAL đơn giản:

~~~json
{
  "id": 42,
  "name": "An Nguyen",
  "email": "an@example.com",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

Các annotation Jackson trên field, getter hoặc setter ảnh hưởng đến thuộc tính dữ liệu được serialize hoặc deserialize. Các liên kết hypermedia như _links được Spring Data REST bổ sung theo cấu hình resource; chúng không phải field nghiệp vụ thông thường của entity.

Vì Spring Data REST thường công bố trực tiếp domain type của repository, annotation JSON trên domain type có thể ảnh hưởng đến nhiều endpoint sử dụng cùng representation. Hãy xác định rõ thuộc tính cần ẩn, chỉ đọc hay chỉ ghi trước khi áp dụng annotation.

## 2. @JsonIgnore: bỏ qua thuộc tính khi ánh xạ JSON

@JsonIgnore đánh dấu một thuộc tính để Jackson bỏ qua. Trường hợp thông dụng là không đưa thuộc tính vào JSON response và cũng không lấy giá trị từ JSON request để gán cho thuộc tính đó.

Ví dụ entity Person có một ghi chú nội bộ:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Person {

    @Id
    private Long id;

    private String name;

    @JsonIgnore
    private String internalNote;

    // getters and setters
}
~~~

Khi client gọi:

~~~http
GET /people/42
Accept: application/hal+json
~~~

representation có thể chứa id và name nhưng không chứa internalNote:

~~~json
{
  "id": 42,
  "name": "An Nguyen"
}
~~~

Nếu client gửi:

~~~http
PATCH /people/42
Content-Type: application/json

{
  "name": "An",
  "internalNote": "new value"
}
~~~

Jackson không dùng internalNote từ JSON để cập nhật thuộc tính được đánh dấu @JsonIgnore. Tùy cấu hình Jackson, thuộc tính bị bỏ qua có thể bị âm thầm bỏ qua hoặc request có thể bị từ chối nếu ứng dụng bật xử lý lỗi đối với ignored properties.

### Khi nào nên dùng @JsonIgnore?

Dùng khi thuộc tính không nên tham gia representation JSON của API theo cả hai chiều. Ví dụ:

- Trường nội bộ chỉ phục vụ xử lý trong domain.
- Thuộc tính kỹ thuật không cần công bố cho client.
- Một association hoặc thuộc tính không nên được đọc/ghi qua JSON endpoint đang dùng.
- Giá trị dẫn xuất mà API không muốn công bố hoặc nhận từ client.

Không dùng @JsonIgnore cho một thuộc tính cần nhận dữ liệu khi tạo/cập nhật nhưng chỉ cần ẩn khỏi response. Trường hợp đó phù hợp hơn với WRITE_ONLY.

## 3. @JsonProperty(access = READ_ONLY): chỉ đọc từ phía API

READ_ONLY có nghĩa Jackson cho phép serialize thuộc tính vào response nhưng bỏ qua giá trị tương ứng khi deserialize JSON request.

Ví dụ, ID và thời điểm tạo được server quản lý:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonProperty.Access;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.time.Instant;

@Entity
public class Person {

    @Id
    @JsonProperty(access = Access.READ_ONLY)
    private Long id;

    private String name;

    @JsonProperty(access = Access.READ_ONLY)
    private Instant createdAt;

    // getters and setters
}
~~~

Khi GET tài nguyên, client vẫn nhìn thấy id và createdAt:

~~~json
{
  "id": 42,
  "name": "An Nguyen",
  "createdAt": "2026-11-11T02:30:00Z"
}
~~~

Nếu client gửi request có các giá trị này:

~~~http
PATCH /people/42
Content-Type: application/json

{
  "name": "An",
  "id": 999,
  "createdAt": "2000-01-01T00:00:00Z"
}
~~~

Jackson không bind id và createdAt từ JSON request vào các thuộc tính READ_ONLY. Request có thể cập nhật name theo cấu hình và logic ứng dụng, còn các giá trị do server quản lý không được lấy từ body.

### Các trường hợp phù hợp với READ_ONLY

- ID do database hoặc hệ thống sinh.
- createdAt và createdBy do server ghi nhận.
- Trạng thái tính toán mà client chỉ được xem.
- Số liệu tổng hợp hoặc giá trị dẫn xuất mà client không được gửi để ghi đè.

READ_ONLY không tự tạo ra giá trị cho thuộc tính. Ứng dụng vẫn cần thiết lập ID, timestamp hoặc audit field thông qua persistence, entity listener, auditing hoặc service phù hợp.

## 4. @JsonProperty(access = WRITE_ONLY): chỉ ghi từ phía API

WRITE_ONLY cho phép Jackson đọc giá trị từ JSON request nhưng không serialize thuộc tính đó vào response.

Ví dụ, API nhận mật khẩu khi tạo hoặc đổi thông tin đăng nhập:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonProperty.Access;

public class AccountInput {

    private String username;

    @JsonProperty(access = Access.WRITE_ONLY)
    private String password;

    // getters and setters
}
~~~

Khi client gửi request:

~~~http
POST /accounts
Content-Type: application/json

{
  "username": "an",
  "password": "temporary-secret"
}
~~~

Jackson có thể bind password vào đối tượng nhận dữ liệu. Khi representation được serialize, thuộc tính password không xuất hiện:

~~~json
{
  "username": "an"
}
~~~

Nếu dùng trực tiếp entity làm request/response type trong Spring Data REST, cần bảo đảm thuộc tính WRITE_ONLY được xử lý đúng ở cả luồng tạo và cập nhật theo thiết kế ứng dụng.

### Các trường hợp phù hợp với WRITE_ONLY

- Mật khẩu hoặc mật khẩu mới.
- Mã xác minh chỉ được gửi vào.
- Secret đầu vào mà API không bao giờ trả lại.
- Dữ liệu đầu vào chỉ phục vụ một thao tác, không nên xuất hiện trong response.

WRITE_ONLY chỉ ngăn Jackson serialize thuộc tính. Nó không tự mã hóa, băm hoặc bảo vệ giá trị được lưu. Với password, ứng dụng phải hash bằng thuật toán phù hợp trước khi lưu và không bao giờ ghi password thô vào log hoặc trả lại qua endpoint khác.

## 5. So sánh ba cách cấu hình

| Cấu hình | JSON response | JSON request | Mục đích |
|---|---|---|---|
| Mặc định | Có thể serialize | Có thể deserialize | Đọc và ghi thông thường |
| @JsonIgnore | Bỏ qua | Bỏ qua | Không tham gia ánh xạ JSON |
| @JsonProperty(access = READ_ONLY) | Có | Bỏ qua khi đọc request | Server cung cấp, client chỉ xem |
| @JsonProperty(access = WRITE_ONLY) | Bỏ qua | Có | Client gửi vào, server không trả lại |

Jackson định nghĩa thêm các chế độ truy cập như READ_WRITE và AUTO. AUTO là chế độ mặc định theo quy tắc phát hiện property của Jackson; READ_WRITE cho phép cả serialize và deserialize. Khi cần thể hiện rõ hợp đồng API, READ_ONLY và WRITE_ONLY thường dễ hiểu hơn.

## 6. Dùng annotation trên field, getter hoặc setter

Jackson có thể phát hiện một property từ field, getter, setter hoặc constructor parameter tùy visibility và cấu hình ObjectMapper.

Ví dụ đặt annotation trên getter:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
public Instant getCreatedAt() {
    return createdAt;
}
~~~

Hoặc đặt trên field:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private Instant createdAt;
~~~

Nên khai báo annotation nhất quán cho cùng một property. Nếu field, getter và setter có annotation xung đột, Jackson có thể hợp nhất metadata theo quy tắc property introspection; kết quả dễ gây nhầm lẫn khi model có nhiều accessor.

Nếu một property có getter và setter riêng nhưng yêu cầu đọc/ghi khác nhau, dùng @JsonProperty(access = ...) ở cấp property giúp diễn đạt ý định rõ ràng hơn so với việc gắn @JsonIgnore tùy tiện lên một accessor.

## 7. Ví dụ kết hợp các loại property trong một entity

Một entity có thể kết hợp thuộc tính thông thường, read-only, write-only và ignored:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonProperty.Access;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.time.Instant;

@Entity
public class Account {

    @Id
    @JsonProperty(access = Access.READ_ONLY)
    private Long id;

    private String username;

    @JsonProperty(access = Access.WRITE_ONLY)
    private String password;

    @JsonProperty(access = Access.READ_ONLY)
    private Instant createdAt;

    @JsonIgnore
    private String internalRiskFlag;

    // getters and setters
}
~~~

Hợp đồng JSON dự kiến:

- id: server trả về, client không thể gán qua JSON request.
- username: có thể đọc và ghi theo các quy tắc khác của ứng dụng.
- password: client gửi vào, response không trả lại.
- createdAt: server trả về, client không thể ghi qua JSON request.
- internalRiskFlag: không được ánh xạ qua JSON theo cả hai chiều.

Các annotation không thay thế validation hoặc authorization. Ví dụ, việc username có được thay đổi hay không vẫn cần được kiểm soát bởi quy tắc nghiệp vụ và quyền của người gọi.

## 8. Tác động đến POST, PUT và PATCH

Spring Data REST sử dụng Jackson khi nhận JSON body cho các thao tác ghi. Vì vậy, quy tắc READ_ONLY, WRITE_ONLY và JsonIgnore có thể ảnh hưởng đến các request khác nhau.

### POST tạo tài nguyên

- Thuộc tính thông thường có thể được bind từ body.
- READ_ONLY không nhận giá trị client gửi.
- WRITE_ONLY nhận giá trị từ body nhưng không xuất hiện khi response được serialize.
- JsonIgnore bị bỏ qua trong quá trình ánh xạ JSON.

Ví dụ, client có thể gửi username và password khi tạo account; id và createdAt do server quản lý.

### PUT thay thế representation

PUT thể hiện ý định thay thế trạng thái tài nguyên theo representation request. Các thuộc tính READ_ONLY vẫn không được bind từ JSON. Những thuộc tính bị bỏ qua hoặc không có trong body có thể chịu ảnh hưởng từ cách Spring Data REST bind domain object và logic của ứng dụng.

Không nên coi READ_ONLY là một cơ chế bảo toàn dữ liệu tự động trong mọi quy trình PUT. Hãy kiểm thử trạng thái entity sau request, đặc biệt khi domain model dùng constructor, setter, factory method hoặc custom deserializer.

### PATCH cập nhật một phần

PATCH thường chỉ gửi các thuộc tính cần thay đổi. Thuộc tính READ_ONLY và JsonIgnore không được cập nhật từ body theo cấu hình Jackson tương ứng; thuộc tính WRITE_ONLY có thể nhận giá trị đầu vào mà không xuất hiện trong response.

Cần kiểm thử trường hợp thuộc tính không có key, có key với null và có giá trị cụ thể. Cách xử lý null, nested object và association còn phụ thuộc binding, validation và cấu hình của ứng dụng.

## 9. Annotation JSON không phải cơ chế bảo mật

Không nên dựa vào annotation serialization để bảo vệ dữ liệu nhạy cảm.

- READ_ONLY không ngăn thay đổi thuộc tính qua service nội bộ, database, custom controller hoặc endpoint khác.
- WRITE_ONLY không băm password và không ngăn ứng dụng ghi secret vào log.
- JsonIgnore không thay thế authorization; dữ liệu vẫn có thể được truy cập qua một endpoint hoặc serializer khác.
- Một projection, custom serializer hoặc ObjectMapper khác có thể tạo representation khác với endpoint đang xét.

Hãy kiểm soát quyền truy cập ở tầng security/service, xác thực dữ liệu đầu vào, bảo vệ secret khi lưu trữ và kiểm tra tất cả endpoint có thể công bố cùng domain type.

Nếu mỗi nhóm người dùng cần nhìn thấy các tập thuộc tính khác nhau, annotation tĩnh trên entity có thể không đủ. Khi đó cân nhắc DTO, projection phù hợp cho đọc, custom controller hoặc các representation tách biệt theo use case và quyền truy cập.

## 10. Liên hệ với association và HAL

Spring Data REST thường biểu diễn association bằng các liên kết HAL trong _links. Một property association có thể được trình bày dưới dạng link thay vì object JSON lồng nhau, tùy representation và projection.

Ví dụ:

~~~json
{
  "name": "An",
  "_links": {
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~

Nếu đặt @JsonIgnore trên property association, phần JSON property tương ứng có thể bị loại khỏi serialization/deserialization. Tuy nhiên, cách Spring Data REST phát hiện và công bố association còn liên quan tới metadata repository và cấu hình REST. Hãy kiểm tra response HAL thực tế thay vì giả định annotation trên field luôn loại bỏ mọi link liên quan.

Nếu mục tiêu là không công bố một association qua Spring Data REST, hãy xem xét cấu hình export của association/repository theo đúng khả năng của phiên bản đang dùng. JsonIgnore điều khiển Jackson property; export configuration điều khiển việc Spring Data REST công bố resource và association.

## 11. Kiểm thử serialization và deserialization

Nên kiểm tra cả hai chiều JSON. Một test chỉ gọi GET và xác nhận field bị ẩn chưa chứng minh server bỏ qua field đó khi nhận request.

Các trường hợp cần kiểm tra:

1. GET item resource và xác nhận READ_ONLY vẫn xuất hiện.
2. GET item resource và xác nhận WRITE_ONLY cùng JsonIgnore không xuất hiện.
3. Gửi POST với giá trị id hoặc createdAt giả và xác nhận server không lấy giá trị đó từ body.
4. Gửi POST với password và xác nhận giá trị được nhận, xử lý và lưu an toàn nhưng không xuất hiện trong response.
5. Gửi PATCH với thuộc tính READ_ONLY và xác nhận giá trị server quản lý không bị ghi đè.
6. Gửi request chứa property JsonIgnore và xác nhận hành vi theo cấu hình Jackson.
7. Kiểm tra phản hồi khi bật/tắt xử lý lỗi đối với ignored properties nếu ứng dụng có cấu hình này.
8. Kiểm tra association links trong HAL sau khi áp dụng annotation.
9. Kiểm tra custom serializer, projection và endpoint khác nếu chúng dùng chung entity.

Ví dụ test Jackson độc lập có thể dùng ObjectMapper:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = mapper.writeValueAsString(account);

// Assert password và internalRiskFlag không xuất hiện.
// Assert id và createdAt vẫn xuất hiện.
~~~

Đối với Spring Data REST, cần bổ sung integration test qua HTTP vì ObjectMapper riêng trong unit test có thể không giống cấu hình mà ứng dụng đăng ký cho REST layer.

## 12. Lựa chọn annotation theo yêu cầu

| Yêu cầu API | Cách phù hợp |
|---|---|
| Không nhận và không trả thuộc tính | @JsonIgnore |
| Trả thuộc tính nhưng không cho client ghi qua JSON | @JsonProperty(access = READ_ONLY) |
| Nhận thuộc tính nhưng không trả trong JSON | @JsonProperty(access = WRITE_ONLY) |
| Đọc và ghi thông thường | Không cần access override |
| Khác biệt field theo vai trò hoặc use case | Security + DTO/projection/custom representation phù hợp |

Trước khi chọn annotation, hãy xác định rõ hai câu hỏi cho từng thuộc tính:

1. Server có cần đưa giá trị này vào JSON response không?
2. Server có chấp nhận giá trị này từ JSON request không?

Nếu câu trả lời lần lượt là không/không, dùng JsonIgnore; có/không, dùng READ_ONLY; không/có, dùng WRITE_ONLY; có/có, giữ hành vi mặc định nếu không có yêu cầu khác.

## 13. Những điểm cần ghi nhớ

- Spring Data REST dùng Jackson để ánh xạ JSON request và response với domain object.
- @JsonIgnore bỏ qua property trong ánh xạ JSON; @JsonProperty READ_ONLY chỉ trả dữ liệu; WRITE_ONLY chỉ nhận dữ liệu.
- READ_ONLY phù hợp với ID, timestamp và giá trị server quản lý.
- WRITE_ONLY phù hợp với password hoặc secret đầu vào, nhưng ứng dụng vẫn phải hash/bảo vệ giá trị trước khi lưu.
- Annotation có thể đặt trên field hoặc accessor; nên tránh metadata xung đột trên cùng property.
- Các annotation ảnh hưởng đến JSON mapping, không thay thế authorization, validation hoặc ràng buộc database.
- Với association HAL, kiểm tra cả property JSON lẫn liên kết mà Spring Data REST công bố.
- Kiểm thử cả serialize response và deserialize request qua endpoint Spring Data REST thực tế.

## Nguồn tham khảo

- [Jackson — JsonIgnore API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html)
- [Jackson — JsonProperty.Access API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html)
- [Spring Data REST — Reference documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Jackson — Annotations documentation](https://github.com/FasterXML/jackson-annotations)
