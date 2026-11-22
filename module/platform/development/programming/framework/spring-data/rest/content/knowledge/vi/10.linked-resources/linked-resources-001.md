# Phân biệt liên kết HAL và tài nguyên thao tác quan hệ

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận diện một HAL link trong JSON do Spring Data REST trả về.
- Phân biệt đường dẫn điều hướng với endpoint biểu diễn một quan hệ giữa hai entity.
- Theo HAL link để tìm association resource mà không tự đoán URL.
- Chọn đúng HTTP method và Content-Type khi đọc hoặc thay đổi quan hệ.
- Tránh nhầm thao tác trên association resource với thao tác tạo, sửa hoặc xóa entity.

## 1. Bối cảnh: Spring Data REST và HAL

Spring Data REST xuất bản các Spring Data repository thành REST resource. Ví dụ, repository quản lý entity Order có thể tạo collection resource tại /orders và item resource cho từng đơn hàng tại /orders/{id}.

Mặc định, Spring Data REST dùng HAL (Hypertext Application Language) để biểu diễn các liên kết trong JSON. Response thường có Content-Type là application/hal+json. HAL đặt các liên kết trong thuộc tính _links; mỗi khóa là một relation name, còn giá trị chứa thông tin về link, tối thiểu thường có href.

Ví dụ response ở API root:

~~~json
{
  "_links": {
    "orders": {
      "href": "http://localhost:8080/orders"
    },
    "profile": {
      "href": "http://localhost:8080/profile"
    }
  }
}
~~~

Trong ví dụ này:

- orders là relation name cho biết link dẫn tới collection đơn hàng.
- href là URI mà client có thể gọi tiếp.
- profile là một link khác, không phải quan hệ giữa hai entity nghiệp vụ.

Một HAL link là thông tin điều hướng nằm trong representation. Bản thân link không chứa dữ liệu quan hệ và cũng không thực thi thao tác. Nó cho client biết một URI có ý nghĩa gì trong ngữ cảnh response hiện tại.

HAL không chỉ dùng cho quan hệ entity. Link có thể dẫn tới API root, collection, item, search resource, profile, trang kế tiếp hoặc association resource. Vì vậy, không được kết luận rằng mọi phần tử trong _links đều là quan hệ dữ liệu.

## 2. Association resource là gì?

Khi một entity có association tới entity khác, Spring Data REST có thể xuất bản một sub-resource dành riêng cho association đó. Tài liệu Spring Data REST gọi đây là association resource.

Giả sử một Order tham chiếu tới một Customer:

~~~java
@Entity
public class Customer {
    @Id
    @GeneratedValue
    private Long id;

    private String name;

    // constructors, getters and setters
}
~~~

~~~java
@Entity
public class Order {
    @Id
    @GeneratedValue
    private Long id;

    private String orderNumber;

    @ManyToOne
    private Customer customer;

    // constructors, getters and setters
}
~~~

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}

public interface OrderRepository
        extends JpaRepository<Order, Long> {
}
~~~

Với repository được Spring Data REST xuất bản, item resource của đơn hàng có thể trả về:

~~~json
{
  "orderNumber": "ORD-042",
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    },
    "customer": {
      "href": "http://localhost:8080/orders/42/customer"
    }
  }
}
~~~

Ở đây cần phân biệt hai URI:

- /orders/42 là item resource của chính đơn hàng.
- /orders/42/customer là association resource đại diện cho quan hệ customer của đơn hàng đó.

Link có relation name customer nằm trong _links chỉ đường tới association resource. Association resource mới là endpoint mà client gọi để đọc hoặc thay đổi liên kết giữa Order 42 và một Customer.

Mặc định, tên và path của association resource dựa trên tên property trong entity. Có thể tùy chỉnh relation name và path bằng @RestResource trên property association. Vì vậy, client nên đọc href được server cung cấp thay vì tự ghép URL từ tên class hoặc tên field.

## 3. Phân biệt hai khái niệm

| Tiêu chí | HAL link | Association resource |
|---|---|---|
| Bản chất | Thông tin liên kết trong representation | REST endpoint biểu diễn một association |
| Vị trí | Thường nằm trong _links | Được truy cập qua URI trong href |
| Thành phần chính | Relation name và href | Trạng thái quan hệ và các thao tác HTTP được hỗ trợ |
| Vai trò | Giúp client khám phá và điều hướng | Cho phép đọc hoặc thay đổi quan hệ |
| Có tự chứa dữ liệu quan hệ không? | Không; chủ yếu chỉ mô tả đích liên kết | Có thể trả về trạng thái hoặc các resource đang được liên kết |
| Ví dụ | _links.customer.href | /orders/42/customer |

Hãy nhớ: HAL link là “địa chỉ được công bố trong response”; association resource là “đích REST có thể được gọi để thao tác quan hệ”. Hai khái niệm liên quan chặt chẽ nhưng không đồng nghĩa.

## 4. Đọc và thao tác association resource

### 4.1. Đọc quan hệ

Bước đầu tiên là đọc item resource và lấy URI từ relation tương ứng:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

Sau khi thấy link customer, client gọi URI của link đó:

~~~http
GET /orders/42/customer
Accept: application/hal+json
~~~

Association resource trả về trạng thái hiện tại của quan hệ. Với quan hệ to-one, response có thể là representation của Customer đang được liên kết. Với quan hệ collection, response có thể là collection representation chứa các resource liên quan.

Không cần đoán URI của Customer từ ID hoặc cấu trúc database. Hãy đi theo href được server công bố.

### 4.2. Gán một quan hệ to-one bằng PUT

Với association to-one, chẳng hạn Order có một Customer, Spring Data REST dùng PUT tới association resource. Body chứa URI của resource cần liên kết và Content-Type là text/uri-list.

Ví dụ gán Customer 7 cho Order 42:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/customers/7" \
  "http://localhost:8080/orders/42/customer"
~~~

Điểm cần nhớ:

- Request gửi tới association resource /orders/42/customer.
- Body là URI của Customer, không phải JSON object chứa các field của Customer.
- Content-Type phải là text/uri-list.
- Với association to-one, chỉ gửi một URI. Gửi nhiều URI cho quan hệ to-one có thể nhận 400 Bad Request.

Sau khi cập nhật, đọc lại association resource bằng GET để xác nhận quan hệ đã trỏ tới Customer 7. Tùy cấu hình trả response body, thao tác cập nhật có thể trả 204 No Content; response không có body không đồng nghĩa thao tác thất bại.

### 4.3. Thêm phần tử vào quan hệ collection bằng POST

Giả sử Article có quan hệ collection tới nhiều Tag:

~~~java
@ManyToMany
private Set<Tag> tags = new HashSet<>();
~~~

Item resource của Article có thể công bố link tags dẫn tới association resource của collection đó, ví dụ /articles/1/tags.

Để thêm Tag 5 vào collection, dùng POST và gửi URI của Tag:

~~~bash
curl -i -X POST \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/tags/5" \
  "http://localhost:8080/articles/1/tags"
~~~

POST trên association resource chỉ được hỗ trợ cho association dạng collection và có ý nghĩa thêm phần tử vào collection. Body vẫn là URI của resource cần liên kết, với Content-Type text/uri-list.

### 4.4. Gỡ quan hệ bằng DELETE

DELETE trên association resource có ý nghĩa hủy liên kết. Nó không đồng nghĩa với việc xóa entity ở đầu bên kia.

Ví dụ, nếu customer là association tùy chọn của Order, có thể gọi:

~~~http
DELETE /orders/42/customer
~~~

Thao tác này gỡ quan hệ customer khỏi Order 42; nó không tự xóa Customer 7 khỏi /customers/7.

Nếu association là bắt buộc hoặc không cho phép giá trị rỗng, Spring Data REST có thể trả 405 Method Not Allowed. Hãy kiểm tra mapping, cấu hình và trạng thái HTTP thực tế trước khi kết luận endpoint bị lỗi.

Không suy luận rằng DELETE trên association collection luôn có cùng ý nghĩa với xóa một phần tử riêng lẻ. Hãy đọc API được công bố và kiểm tra endpoint cụ thể mà server hỗ trợ.

## 5. Cùng là PUT nhưng hai loại resource khác nhau

Một nhầm lẫn phổ biến là dùng PUT lên item resource và PUT lên association resource như thể chúng có cùng body.

| Request | Ý nghĩa | Body điển hình |
|---|---|---|
| PUT /orders/42 | Thay thế trạng thái của Order 42 | JSON representation của Order |
| PATCH /orders/42 | Cập nhật một phần trạng thái của Order 42 | JSON hoặc patch document được hỗ trợ |
| PUT /orders/42/customer | Gán resource Customer vào association customer | URI, Content-Type text/uri-list |
| POST /articles/1/tags | Thêm resource Tag vào association collection tags | URI, Content-Type text/uri-list |

URI đích quyết định resource đang được thao tác. Content-Type và cấu trúc body phải phù hợp với loại resource đó.

Association resource có bộ HTTP method riêng: GET để đọc, PUT để bind resource theo URI, POST để thêm phần tử vào association collection, và DELETE để unbind association. Không áp dụng máy móc quy tắc PUT/PATCH của item resource cho endpoint association.

## 6. Quy trình làm việc đúng cho client

Khi cần thao tác một quan hệ trong Spring Data REST, hãy thực hiện theo trình tự:

1. Gọi GET tới collection hoặc item resource mà client đã biết.
2. Đọc relation name trong _links, ví dụ customer hoặc tags.
3. Lấy nguyên URI từ thuộc tính href. Nếu link là URI template, điền các tham số theo template được công bố.
4. Gọi GET tới association resource để xem trạng thái hiện tại nếu cần.
5. Chọn HTTP method theo loại association: PUT cho liên kết to-one; POST để thêm phần tử vào collection; DELETE để hủy association khi mapping cho phép.
6. Với PUT/POST tới association resource, gửi URI của resource liên quan bằng Content-Type text/uri-list.
7. Kiểm tra status code và đọc lại association resource để xác nhận kết quả.

Nếu server tùy chỉnh relation name hoặc path bằng @RestResource, client vẫn có thể làm việc theo cùng quy trình vì URI thực tế được cung cấp trong HAL response.

## 7. Các lỗi dễ gặp

- **Nhầm link với endpoint:** thấy _links.customer rồi cho rằng JSON link object là dữ liệu Customer. Hãy gọi href để đọc association resource hoặc resource đích.
- **Tự dựng URL:** ghép /orders/{id}/customer từ tên field dù path có thể đã được tùy chỉnh. Luôn ưu tiên href.
- **Gửi JSON thay cho URI:** association resource yêu cầu text/uri-list cho PUT/POST; JSON object của entity không phải payload tương đương.
- **Dùng POST cho quan hệ to-one:** POST được hỗ trợ cho collection association. Với quan hệ to-one, dùng PUT.
- **Gửi nhiều URI cho to-one:** Spring Data REST có thể trả 400 Bad Request vì quan hệ chỉ nhận một resource.
- **Hiểu DELETE là xóa entity:** DELETE association chỉ gỡ liên kết theo semantics của association resource; entity được tham chiếu có thể vẫn tồn tại.
- **Cho rằng mọi HAL link đều là association:** links như self, profile, search hoặc pagination phục vụ điều hướng và khám phá API.
- **Kết luận thất bại từ response rỗng:** 204 No Content là kết quả thành công hợp lệ cho nhiều thao tác cập nhật. Hãy đọc status code.
- **Bỏ qua cấu hình domain:** association bắt buộc, repository method bị ẩn hoặc cấu hình xuất bản có thể ảnh hưởng method được hỗ trợ.

## 8. Bài tập tự kiểm tra

Một response của GET /orders/42 chứa:

~~~json
{
  "orderNumber": "ORD-042",
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    },
    "customer": {
      "href": "http://localhost:8080/orders/42/customer"
    }
  }
}
~~~

**Câu 1.** URI nào là item resource của Order 42?

**Câu 2.** URI nào là association resource của property customer?

**Câu 3.** Muốn gán Customer 7 vào Order 42, cần gọi method nào, tới URI nào và gửi Content-Type gì?

**Câu 4.** Nếu DELETE /orders/42/customer thành công, Customer 7 có bị xóa khỏi repository không?

**Đáp án:**

1. /orders/42 là item resource.
2. /orders/42/customer là association resource.
3. Gọi PUT tới /orders/42/customer, gửi URI http://localhost:8080/customers/7 với Content-Type text/uri-list.
4. Không. DELETE gỡ association; nó không phải lệnh xóa Customer resource.

## 9. Ghi nhớ

- HAL link là metadata điều hướng nằm trong representation, thường ở _links.
- Association resource là endpoint đại diện cho quan hệ giữa một item resource và resource được liên kết.
- HAL link có thể trỏ tới association resource; link và resource là hai khái niệm khác nhau.
- Với association resource, GET đọc quan hệ, PUT bind theo URI, POST thêm phần tử vào collection, DELETE unbind khi mapping cho phép.
- Dùng href do server công bố, đúng HTTP method và đúng Content-Type text/uri-list cho thao tác liên kết.

## Tài liệu tham khảo

- Spring Data REST Reference — Repository resources: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST Reference — phần The Association Resource mô tả GET, PUT, POST, DELETE và media type text/uri-list.
