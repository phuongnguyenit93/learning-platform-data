# PUT để thiết lập hoặc thay thế quan hệ

Trong Spring Data REST, một entity có thể liên kết với entity khác thông qua các association như **@ManyToOne**, **@OneToOne**, **@OneToMany** hoặc **@ManyToMany**. Các quan hệ này được công bố thành association resource để client có thể đọc, gắn hoặc gỡ liên kết qua HTTP.

**PUT trên association resource** dùng để gắn resource được chỉ định bằng URI vào quan hệ. Với quan hệ một-một hoặc nhiều-một, PUT thiết lập target mới và thay thế target đang được liên kết. Với quan hệ collection, PUT gửi danh sách URI của các resource cần gắn vào collection; nếu chỉ muốn thêm một phần tử mới vào collection, dùng POST.

Điểm quan trọng là request PUT tới association resource dùng **Content-Type: text/uri-list** và body chứa URI của resource liên quan. Đây là thao tác cập nhật liên kết, không phải gửi toàn bộ JSON của entity.

## 1. Association resource là gì?

Spring Data REST tạo một association resource cho từng quan hệ được xuất trên item resource. Path mặc định của association resource dựa trên tên thuộc tính quan hệ trong entity. Có thể tùy chỉnh tên và path bằng **@RestResource** đặt trên thuộc tính đó.

Ví dụ entity **Person** có một phòng ban và nhiều vai trò:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne
    private Department department;

    @ManyToMany
    private Set<Role> roles = new HashSet<>();

    // getters and setters
}
~~~

Giả sử repository của các entity đều được Spring Data REST xuất. Khi client đọc một person:

~~~http
GET /people/1
Accept: application/hal+json
~~~

Representation HAL có thể chứa các liên kết quan hệ:

~~~json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/1"
    },
    "department": {
      "href": "http://localhost:8080/people/1/department"
    },
    "roles": {
      "href": "http://localhost:8080/people/1/roles"
    }
  }
}
~~~

Trong ví dụ:

- **`/people/1/department`** là association resource cho quan hệ một phòng ban.
- **`/people/1/roles`** là association resource cho collection các vai trò.
- Các URI như **`/departments/3`** hoặc **`/roles/2`** là item resource của entity được liên kết.

Client nên lấy các URL từ liên kết HAL trong response thay vì tự ghép path. Tên liên kết mặc định lấy từ tên thuộc tính quan hệ; **@RestResource** trên thuộc tính có thể tùy chỉnh tên/path đó.

## 2. Dùng PUT để thiết lập quan hệ một-một hoặc nhiều-một

Với quan hệ đơn trị, chẳng hạn **@OneToOne** hoặc **@ManyToOne**, association resource chỉ liên kết tới một resource tại một thời điểm.

Ví dụ person có quan hệ **department**. Để gắn person số 1 với department số 3, gửi:

~~~http
PUT /people/1/department
Content-Type: text/uri-list
~~~

Body là URI của department:

~~~text
http://localhost:8080/departments/3
~~~

Có thể gọi bằng curl:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/departments/3" \
  http://localhost:8080/people/1/department
~~~

Nếu person đang liên kết với department khác, PUT thiết lập liên kết tới department số 3. Không gửi JSON object của department vào body association resource; endpoint này nhận URI dưới dạng **text/uri-list**.

Để thay department bằng một department khác, gửi PUT tới cùng association resource với URI mới:

~~~http
PUT /people/1/department
Content-Type: text/uri-list
~~~

~~~text
http://localhost:8080/departments/5
~~~

Với association một-một hoặc nhiều-một, chỉ gửi một URI. Nếu gửi nhiều URI cho quan hệ to-one, Spring Data REST trả về **400 Bad Request**.

## 3. Dùng PUT với quan hệ collection

Với quan hệ nhiều phần tử như **@OneToMany** hoặc **@ManyToMany**, association resource đại diện cho một collection. PUT có thể nhận nhiều URI, mỗi URI trỏ tới một resource cần gắn vào association.

Ví dụ person số 1 có các role. Gửi danh sách URI:

~~~http
PUT /people/1/roles
Content-Type: text/uri-list
~~~

~~~text
http://localhost:8080/roles/2
http://localhost:8080/roles/4
~~~

Mỗi URI nằm trên một dòng. Danh sách URI mô tả những resource được gửi để gắn vào association. Hãy đọc lại association sau request để xác nhận trạng thái quan hệ thực tế của ứng dụng.

Ví dụ curl:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data-binary $'http://localhost:8080/roles/2\nhttp://localhost:8080/roles/4' \
  http://localhost:8080/people/1/roles
~~~

Nếu muốn thêm một role vào collection hiện có, POST là thao tác phù hợp hơn. Phần tiếp theo phân biệt rõ hai cách này.

## 4. Phân biệt PUT, POST và DELETE trên association resource

Spring Data REST hỗ trợ GET, PUT, POST và DELETE cho association resource. Mỗi method có mục đích riêng:

| HTTP method | Phạm vi | Tác dụng |
|---|---|---|
| **GET** | Association resource | Đọc trạng thái quan hệ hiện tại |
| **PUT** | Quan hệ đơn trị hoặc collection | Gắn resource được chỉ định bằng URI vào quan hệ |
| **POST** | Chỉ collection association | Thêm một phần tử mới vào collection |
| **DELETE** | Association resource | Gỡ liên kết của association |

### POST để thêm một phần tử vào collection

Ví dụ person số 1 đã có role số 2 và muốn thêm role số 5 mà không thay đổi cách gửi danh sách bằng PUT:

~~~http
POST /people/1/roles
Content-Type: text/uri-list
~~~

~~~text
http://localhost:8080/roles/5
~~~

POST chỉ được hỗ trợ cho collection association. Nó thêm phần tử mới được chỉ định vào collection.

### DELETE để gỡ association

Ví dụ gỡ liên kết department khỏi person:

~~~http
DELETE /people/1/department
~~~

DELETE trên association resource yêu cầu Spring Data REST unbind association. Với association không cho phép null hoặc không optional, thao tác này có thể bị từ chối bằng **405 Method Not Allowed**.

Hãy kiểm tra trạng thái quan hệ sau khi gọi DELETE. Nếu mục tiêu chỉ là thay một department bằng department khác, PUT với URI mới thường thể hiện ý định rõ ràng hơn.

## 5. Phân biệt PUT entity resource và PUT association resource

Hai endpoint đều dùng HTTP PUT nhưng có body và ý nghĩa khác nhau.

| Endpoint | Content-Type | Body | Ý nghĩa |
|---|---|---|---|
| **PUT /people/1** | **application/json** hoặc **application/hal+json** | Representation của Person | Thay thế trạng thái entity |
| **PUT /people/1/department** | **text/uri-list** | URI của Department | Thiết lập hoặc thay target của quan hệ department |
| **PUT /people/1/roles** | **text/uri-list** | Một hoặc nhiều URI Role | Gắn các resource được chỉ định vào collection association |

Ví dụ, không gửi payload này tới **`/people/1/department`**:

~~~json
{
  "id": 3,
  "name": "Engineering"
}
~~~

Association resource cần URI của entity liên quan:

~~~text
http://localhost:8080/departments/3
~~~

Phân biệt đúng endpoint giúp tránh lỗi media type hoặc lỗi binding khi client muốn cập nhật một quan hệ.

## 6. Đọc và xác nhận quan hệ

Trước khi cập nhật, nên đọc item resource để khám phá liên kết:

~~~http
GET /people/1
Accept: application/hal+json
~~~

Theo liên kết **department** hoặc **roles** trong **_links** để truy cập association resource.

Đọc trạng thái quan hệ đơn trị:

~~~http
GET /people/1/department
Accept: application/hal+json
~~~

Đọc trạng thái collection association:

~~~http
GET /people/1/roles
Accept: application/hal+json
~~~

Sau khi PUT, GET lại association resource để kiểm tra liên kết đã trỏ tới entity mong muốn. Có thể GET item resource liên quan để xác nhận URI đích tồn tại.

Khi kiểm tra collection, đối chiếu toàn bộ các liên kết được trả về với các URI đã gửi. Không chỉ dựa vào HTTP status code để kết luận quan hệ đã được lưu đúng.

## 7. Tùy chỉnh association resource

Tên và path mặc định của association resource dựa trên tên thuộc tính quan hệ. Có thể dùng **@RestResource** trên thuộc tính để tùy chỉnh rel và path.

Ví dụ:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne
    @RestResource(path = "team", rel = "team")
    private Department department;
}
~~~

Trong ví dụ, association resource có thể được công bố với liên kết **team** và path **`/people/1/team`** thay cho tên thuộc tính mặc định **department**.

Client nên theo href được trả về trong HAL. Khi thay đổi tên/path association, các client đang gọi trực tiếp URL cũ cần được cập nhật.

## 8. Những điều kiện cần kiểm tra

Để thao tác PUT association hoạt động, hãy kiểm tra:

1. Repository của entity nguồn và entity đích được Spring Data REST xuất.
2. Quan hệ được khai báo đúng trên entity và có thể được truy cập qua association resource.
3. URI trong body trỏ tới item resource tồn tại và có thể truy cập.
4. Request dùng đúng **Content-Type: text/uri-list**.
5. Với quan hệ to-one, body chỉ chứa một URI.
6. Với collection association, mỗi URI được đặt trên một dòng riêng.
7. Mapping JPA cập nhật đúng phía sở hữu quan hệ (owning side), đặc biệt với quan hệ hai chiều có **mappedBy**.
8. Quyền truy cập và validation của ứng dụng cho phép thay đổi quan hệ đó.

Spring Data REST không thể gắn một resource không tồn tại. URI sai, resource đích không được xuất hoặc lỗi quyền truy cập có thể làm request thất bại.

Với JPA, cần hiểu phía sở hữu quan hệ. Ở quan hệ hai chiều, chỉ cập nhật collection ở phía inverse có thể không tạo ra thay đổi trong database nếu owning side không được đồng bộ. Hãy thiết kế setter hoặc logic nghiệp vụ để giữ hai phía quan hệ nhất quán khi ứng dụng cần điều đó.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| PUT association trả về 415 Unsupported Media Type | Dùng **application/json** thay vì **text/uri-list** | Đổi Content-Type và gửi URI thuần |
| PUT to-one trả về 400 Bad Request | Body chứa nhiều URI cho quan hệ đơn trị | Chỉ gửi một URI đích |
| Quan hệ không thay đổi | URI không trỏ tới item resource hợp lệ hoặc property không được xuất | Kiểm tra href từ HAL và cấu hình repository |
| POST collection bị từ chối | Association không phải collection | Dùng PUT cho quan hệ đơn trị |
| DELETE trả về 405 Method Not Allowed | Quan hệ được khai báo non-optional | Kiểm tra nullable/optional và contract nghiệp vụ |
| Request thành công nhưng database không phản ánh quan hệ mong muốn | Mapping hai chiều chưa đồng bộ owning side | Kiểm tra mappedBy và logic cập nhật hai phía |
| Client gọi sai URL association | Tự ghép path thay vì theo HAL link | Đọc item resource và dùng href trong _links |

## 10. Quy trình thực hành

Có thể thực hành với **Person**, **Department** và **Role**:

1. Tạo một person có ID đã biết và đọc **GET /people/{id}**.
2. Từ **_links**, lấy href của association **department** và **roles**.
3. Gửi PUT tới association **department** với một URI Department để thiết lập hoặc thay department.
4. Gửi PUT tới association **roles** với danh sách URI Role cần gắn.
5. Gửi POST tới **roles** với một URI khác để thêm một role.
6. GET lại từng association resource để xác nhận trạng thái.
7. Thử DELETE trên một association optional trong môi trường development và kiểm tra liên kết đã được gỡ.

Ví dụ các request cốt lõi:

~~~http
PUT /people/1/department
Content-Type: text/uri-list

http://localhost:8080/departments/3
~~~

~~~http
PUT /people/1/roles
Content-Type: text/uri-list

http://localhost:8080/roles/2
http://localhost:8080/roles/4
~~~

~~~http
POST /people/1/roles
Content-Type: text/uri-list

http://localhost:8080/roles/5
~~~

Tóm lại, dùng PUT trên association resource để thiết lập hoặc thay target của quan hệ bằng URI, dùng POST để thêm phần tử vào collection association và dùng DELETE để gỡ liên kết khi association cho phép. Luôn theo các liên kết HAL, gửi đúng media type và GET lại quan hệ sau cập nhật để xác nhận kết quả.

Tài liệu tham khảo chính thức:

- [Spring Data REST — Repository resources, Association Resource](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
