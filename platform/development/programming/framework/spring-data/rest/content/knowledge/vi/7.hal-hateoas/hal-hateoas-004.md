# URI template, thuộc tính templated và cách điền tham số

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận biết URI template trong một HAL link.
- Giải thích ý nghĩa của thuộc tính **templated**.
- Phân biệt link có URL hoàn chỉnh với link còn biến cần điền.
- Đọc các biến path và query theo cú pháp URI Template.
- Điền giá trị, mã hóa tham số và gọi endpoint đúng cách.
- Áp dụng quy trình khám phá link cho collection phân trang và search resource của Spring Data REST.

## 1. Vì sao HAL link có thể chứa URI template?

HATEOAS hướng client khám phá API thông qua các liên kết mà server trả về. Trong HAL, mỗi liên kết thường có một relation name và một thuộc tính **href**. Client dùng relation name để tìm đúng liên kết theo mục đích, sau đó đi theo URL trong **href**.

Có hai tình huống:

**Link hoàn chỉnh** đã chứa đủ thông tin để gọi:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/members"
    }
  }
}
~~~

**URI template** mô tả một URL còn có biến cần được client cung cấp:

~~~json
{
  "_links": {
    "members": {
      "href": "http://localhost:8080/api/members{?page,size}",
      "templated": true
    }
  }
}
~~~

Trong ví dụ thứ hai, server cho biết client có thể chọn trang và kích thước trang. Giá trị cụ thể chưa được gắn vào URL. Client phải mở rộng template với các giá trị phù hợp trước khi gửi HTTP request.

URI template giúp một liên kết mô tả được nhiều request có cùng cấu trúc. Ví dụ, một relation **members** có thể dẫn tới trang đầu, trang tiếp theo hoặc một trang có cách sắp xếp khác mà không cần server phát ra một relation riêng cho từng tổ hợp tham số.

## 2. Ý nghĩa của thuộc tính templated

Trong HAL, **templated** là một thuộc tính boolean của link.

| Giá trị | Ý nghĩa |
|---|---|
| **true** | **href** là URI template; có biến cần được mở rộng trước khi gọi |
| **false** hoặc bị lược bỏ | **href** là URI hoàn chỉnh có thể dùng trực tiếp |

Ví dụ link có template:

~~~json
{
  "href": "http://localhost:8080/api/members{?page,size}",
  "templated": true
}
~~~

Ví dụ link thông thường:

~~~json
{
  "href": "http://localhost:8080/api/members?page=0&size=20"
}
~~~

**templated** không phải tên tham số, không cho biết server đã thực hiện truy vấn và cũng không phải cờ bật/tắt endpoint. Nó chỉ báo cho client biết cách diễn giải **href**.

Một client HAL nên kiểm tra thuộc tính này thay vì suy đoán từ việc URL có chứa dấu ngoặc nhọn. Khi link được đánh dấu **templated: true**, hãy dùng bộ xử lý URI template tương thích để mở rộng nó.

## 3. Cú pháp URI Template thường gặp

URI Template sử dụng dấu ngoặc nhọn để đánh dấu biến. Các biểu thức thường gặp trong Spring Data REST là:

| Cú pháp | Ý nghĩa | Kết quả minh họa |
|---|---|---|
| **{id}** | Thay biến trong path | **/members/42** |
| **{?page,size}** | Bắt đầu query string với các biến được cung cấp | **?page=0&size=10** |
| **{&sort}** | Bổ sung biến vào query string đã có | **&sort=name,asc** |

### Biến trong path

Template:

~~~text
/api/members/{id}
~~~

Nếu client cung cấp **id = 42**, URI được mở rộng thành:

~~~text
/api/members/42
~~~

Biến path thường xác định một tài nguyên cụ thể. Nếu thiếu giá trị cho biến bắt buộc, client chưa có một URL hợp lệ để gọi.

### Biến query

Template:

~~~text
/api/members{?page,size}
~~~

Nếu client cung cấp **page = 0** và **size = 10**, URI trở thành:

~~~text
/api/members?page=0&size=10
~~~

Biểu thức **{?page,size}** tự thêm dấu hỏi đầu query string. Client không cần tự nối dấu **?** hoặc tự tạo từng tham số.

### Bổ sung query parameter

Khi URL đã có query string, template có thể dùng biểu thức **{&sort}**:

~~~text
/api/members?active=true{&sort}
~~~

Với **sort = name,asc**, kết quả là:

~~~text
/api/members?active=true&sort=name,asc
~~~

Dấu **?** và **&** là toán tử của template. Không được coi toàn bộ biểu thức trong ngoặc nhọn là tên một query parameter.

## 4. Spring Data REST tạo template cho collection phân trang

Một repository Spring Data có hỗ trợ phân trang có thể cung cấp collection resource kèm liên kết cho các tham số phân trang và sắp xếp.

Ví dụ response HAL minh họa:

~~~json
{
  "_embedded": {
    "members": []
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/members"
    },
    "members": {
      "href": "http://localhost:8080/api/members{?page,size,sort}",
      "templated": true
    }
  },
  "page": {
    "size": 20,
    "totalElements": 0,
    "totalPages": 0,
    "number": 0
  }
}
~~~

Đây là ví dụ về cấu trúc và cách hoạt động; relation name, URL, dữ liệu và các link thực tế phụ thuộc cấu hình cùng phiên bản Spring Data REST của ứng dụng.

Các biến thường gặp:

- **page**: chỉ số trang; Spring Data pageable mặc định đánh số từ 0.
- **size**: số phần tử tối đa trong một trang.
- **sort**: thuộc tính sắp xếp, thường có dạng **property,asc** hoặc **property,desc**.

Ví dụ client muốn lấy trang thứ hai, mỗi trang 10 thành viên và sắp xếp theo tên tăng dần:

~~~text
/api/members?page=1&size=10&sort=name,asc
~~~

**page=1** là trang thứ hai theo cách đánh số bắt đầu từ 0. Server có thể giới hạn kích thước trang tối đa hoặc từ chối thuộc tính sort không hợp lệ; client phải xử lý response thực tế thay vì giả định mọi giá trị đều được chấp nhận.

## 5. Template của search resource

Spring Data REST cũng có thể công bố query method dưới search resource. Tên tham số trong template được hình thành từ tên parameter mà method công bố.

Ví dụ repository:

~~~java
public interface MemberRepository extends JpaRepository<Member, Long> {

    List<Member> findByEmailAddress(@Param("email") String email);
}
~~~

HAL có thể chứa một liên kết tìm kiếm tương tự:

~~~json
{
  "_links": {
    "findByEmailAddress": {
      "href": "http://localhost:8080/api/members/search/findByEmailAddress{?email}",
      "templated": true
    }
  }
}
~~~

Client cung cấp giá trị cho biến **email**. URI sau khi mở rộng có thể là:

~~~text
/api/members/search/findByEmailAddress?email=lan%40example.com
~~~

Tên biến phải khớp với tên query parameter được công bố. Trong ví dụ này, **@Param("email")** xác định tên đó. Nếu đổi tên parameter API, client cần dùng tên mới mà server công bố.

Không nên tự suy ra search URL chỉ từ tên Java method. Hãy tìm relation trong HAL response rồi sử dụng đúng **href** và tên biến mà template trả về.

## 6. Mở rộng URI template trong Java

Spring HATEOAS cung cấp **UriTemplate** để mở rộng URI template. Client lấy chuỗi **href** từ HAL response, truyền các giá trị theo đúng tên biến và nhận lại URI hoàn chỉnh.

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.hateoas.UriTemplate;

public class MemberLinkClient {

    public URI buildMembersUri(String href) {
        return UriTemplate.of(href).expand(Map.of(
            "page", 1,
            "size", 10,
            "sort", "name,asc"
        ));
    }

    public URI buildSearchUri(String href, String email) {
        return UriTemplate.of(href).expand(Map.of(
            "email", email
        ));
    }
}
~~~

Cách gọi:

~~~java
URI pageUri = buildMembersUri(
    "http://localhost:8080/api/members{?page,size,sort}"
);

URI searchUri = buildSearchUri(
    "http://localhost:8080/api/members/search/findByEmailAddress{?email}",
    "lan@example.com"
);
~~~

Kết quả tương ứng có dạng:

~~~text
http://localhost:8080/api/members?page=1&size=10&sort=name,asc
http://localhost:8080/api/members/search/findByEmailAddress?email=lan%40example.com
~~~

Ví dụ tập trung vào bước mở rộng URI. Phần đọc HAL JSON và gửi HTTP request được thực hiện bởi HTTP client mà ứng dụng đang dùng. Hãy dùng phiên bản Spring HATEOAS tương thích với Spring Boot của dự án.

## 7. Quy trình client nên thực hiện

Khi nhận HAL response, client có thể đi theo quy trình sau:

1. Chọn relation phù hợp với thao tác, chẳng hạn **members** hoặc **findByEmailAddress**.
2. Lấy đối tượng link và đọc **href**.
3. Kiểm tra **templated**.
4. Nếu là template, cung cấp các biến theo đúng tên và mở rộng bằng URI Template processor.
5. Nếu là link hoàn chỉnh, dùng trực tiếp **href**.
6. Gửi request đến URI kết quả và xử lý status code cùng response body.
7. Nếu response tiếp theo chứa link mới, tiếp tục khám phá từ response đó.

Điểm quan trọng là client điều hướng theo relation và link server cung cấp. Client không cần ghép base URL, tên endpoint và query parameter bằng nhiều chuỗi rời rạc.

## 8. Mã hóa giá trị và xử lý tham số

Giá trị tham số có thể chứa ký tự đặc biệt như dấu cách, dấu cộng, dấu **@**, dấu **&** hoặc dấu **/**. Khi mở rộng template, thư viện URI template sẽ áp dụng quy tắc encoding phù hợp với vị trí biến.

Ví dụ email:

~~~text
lan@example.com
~~~

Khi được đặt trong query string, ký tự **@** có thể được mã hóa thành **%40**:

~~~text
email=lan%40example.com
~~~

Một số nguyên tắc cần nhớ:

- Truyền giá trị gốc cho thư viện mở rộng template; tránh tự URL-encode trước rồi lại để thư viện encode lần nữa.
- Không nối trực tiếp giá trị người dùng vào URL bằng string concatenation.
- Không tự thêm **?** hoặc **&** nếu template đã có toán tử query tương ứng.
- Cung cấp đúng tên biến, đúng kiểu dữ liệu và giá trị hợp lệ với endpoint.
- Nếu biến tùy chọn không có giá trị, hãy để URI template processor xử lý theo cú pháp template; không thay placeholder bằng chuỗi rỗng một cách thủ công.
- Với biến path, bảo đảm giá trị đại diện cho đúng một path segment; không để dữ liệu đầu vào vô tình thay đổi cấu trúc đường dẫn.

Giá trị đã mở rộng vẫn phải tuân theo validation và giới hạn mà server áp dụng. Việc template cho phép một biến không có nghĩa mọi giá trị đều hợp lệ.

## 9. Những lỗi thường gặp

### Gửi nguyên dấu ngoặc nhọn lên server

Request chứa **/members{?page,size}** chưa phải URI đã mở rộng. Client cần điền biến trước khi gửi request.

### Bỏ qua thuộc tính templated

Nếu client coi mọi **href** là URL hoàn chỉnh, request có thể chứa placeholder chưa xử lý. Hãy kiểm tra **templated** trước khi sử dụng link.

### Dùng sai tên biến

Template yêu cầu **email** nhưng client lại cung cấp **emailAddress**. Biến không được mở rộng như mong muốn hoặc URI vẫn còn placeholder. Hãy lấy tên biến từ chính **href** và đối chiếu với parameter mà server công bố.

### Tự tạo URL thay vì dùng relation

Client ghép cứng **/api/members/search/findByEmailAddress** và tự đoán query parameter. Cách này phụ thuộc cấu trúc URL nội bộ và dễ hỏng khi server đổi path. Hãy khám phá search relation từ HAL response.

### Mã hóa hai lần

Client encode email thành **%40** trước, sau đó template processor lại encode dấu **%**. Kết quả có thể chứa **%2540** và server nhận sai giá trị. Hãy truyền giá trị chưa encode cho thư viện mở rộng.

### Nhầm templated với quyền truy cập

**templated: true** không xác nhận client được phép gọi endpoint. Server vẫn phải kiểm tra authentication, authorization, validation và các giới hạn dữ liệu như bình thường. URI template cũng không phải nơi để nhúng mật khẩu, access token hoặc dữ liệu bí mật.

## 10. Kiểm tra thực tế bằng HTTP

Giả sử API root trả về relation **members** với template:

~~~json
{
  "href": "http://localhost:8080/api/members{?page,size,sort}",
  "templated": true
}
~~~

Sau khi mở rộng với **page=0**, **size=5**, **sort=name,asc**, client gọi:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/api/members?page=0&size=5&sort=name,asc"
~~~

Với search relation có template:

~~~json
{
  "href": "http://localhost:8080/api/members/search/findByEmailAddress{?email}",
  "templated": true
}
~~~

Client gọi URL đã điền tham số:

~~~bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "email=lan@example.com" \
  "http://localhost:8080/api/members/search/findByEmailAddress"
~~~

Lệnh thứ hai minh họa cách gửi query parameter đã được công cụ HTTP mã hóa. Khi kiểm tra một API thực tế, hãy lấy URL và relation từ HAL response của chính server đó; các URL ở đây chỉ là ví dụ.

## 11. Ghi nhớ

- **href** chứa địa chỉ hoặc URI template của một HAL link.
- **templated: true** báo client cần mở rộng template trước khi gọi.
- **{id}** thường đại diện biến path; **{?page,size}** mở đầu query string; **{&sort}** nối thêm query parameter.
- Dùng relation name để tìm link, rồi lấy tên biến từ template.
- Dùng URI Template processor để điền giá trị và mã hóa đúng quy tắc.
- Spring Data REST thường dùng template cho tham số phân trang, sắp xếp và query method.
- Link template hỗ trợ khám phá API; nó không thay thế validation, authentication hoặc authorization.
