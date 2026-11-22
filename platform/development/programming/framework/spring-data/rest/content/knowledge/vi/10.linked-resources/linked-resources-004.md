# Gửi tham chiếu tài nguyên bằng URI trong JSON khi tạo hoặc cập nhật Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể liên kết một entity mới hoặc entity đang tồn tại với resource khác bằng URI trong JSON; phân biệt tham chiếu URI với object lồng nhau; xử lý quan hệ đơn và quan hệ collection; và biết khi nào nên dùng association endpoint với `text/uri-list`.

## 1. Vì sao dùng URI để tham chiếu resource liên quan?

Trong Spring Data REST, một repository resource có thể có association đến resource khác. Ví dụ:

- Một `Order` thuộc về một `Customer`.
- Một `Book` có một `Publisher`.
- Một `Article` có nhiều `Tag`.

Khi client tạo hoặc cập nhật `Order`, client thường chỉ cần chỉ ra Customer đã tồn tại bằng URI của resource đó. Server dùng URI để xác định entity liên quan và gán association vào entity đang được ghi.

Cách này phù hợp với hypermedia: client lấy URI từ link `self` của resource đã biết, sau đó gửi URI đó khi tạo hoặc cập nhật quan hệ. Client không cần gửi lại toàn bộ dữ liệu của Customer và tránh tạo bản sao không chủ ý.

Ví dụ, API có:

- Customer item resource: `http://localhost:8080/customers/42`
- Order collection resource: `http://localhost:8080/orders`

Khi tạo Order cho Customer số 42, body có thể chứa URI của Customer:

```json
{
  "description": "Laptop order",
  "customer": "http://localhost:8080/customers/42"
}
```

Tên thuộc tính `customer` trong JSON tương ứng với association property mà domain object và Jackson expose. Dùng đúng tên property được API công bố; không tự suy ra tên từ class name nếu entity đã tùy chỉnh mapping.

## 2. Tạo resource mới với tham chiếu URI

Giả sử domain model có quan hệ nhiều Order đến một Customer:

```java
@Entity
public class Order {

    @Id
    @GeneratedValue
    private Long id;

    private String description;

    @ManyToOne
    private Customer customer;

    // Constructor, getters và setters
}
```

Repository được Spring Data REST công bố dưới `/orders`. Client tạo Order bằng cách gửi URI của Customer đã tồn tại:

```http
POST /orders HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/hal+json

{
  "description": "Laptop order",
  "customer": "http://localhost:8080/customers/42"
}
```

Spring Data REST đọc body, phân giải URI thành resource liên quan và gán vào association `customer` trước khi lưu Order. Response thành công thường là `201 Created`, kèm header `Location` trỏ đến Order vừa tạo.

Ví dụ response rút gọn:

```http
HTTP/1.1 201 Created
Location: http://localhost:8080/orders/100
Content-Type: application/hal+json
```

```json
{
  "description": "Laptop order",
  "_links": {
    "self": { "href": "http://localhost:8080/orders/100" },
    "customer": { "href": "http://localhost:8080/orders/100/customer" }
  }
}
```

Trong response HAL, association thường được biểu diễn bằng link. Client có thể đọc link đó để xem hoặc thay đổi quan hệ theo các thao tác mà endpoint hỗ trợ.

## 3. Cập nhật association bằng URI trong JSON

Khi cập nhật một Order đã tồn tại, client có thể gửi URI mới trong payload JSON. Ví dụ chuyển Order số 100 sang Customer số 43:

```http
PATCH /orders/100 HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "customer": "http://localhost:8080/customers/43"
}
```

Spring Data REST phân giải URI và gán Customer số 43 vào association. `PATCH` phù hợp khi chỉ muốn thay đổi một phần resource. Với `PUT`, client thường gửi representation đầy đủ theo semantics thay thế của endpoint; hãy bảo đảm các thuộc tính bắt buộc và các association cần giữ được thể hiện đúng.

Nếu muốn bỏ association, không gửi một URI giả hoặc chuỗi rỗng để mong server tự hiểu ý định. Hãy dùng thao tác association phù hợp hoặc semantics cập nhật được endpoint hỗ trợ; kiểm tra link HAL và mapping của domain model trước khi chọn cách gỡ liên kết.

## 4. Tham chiếu collection association

Một entity có thể liên kết với nhiều resource, ví dụ `Article` có nhiều `Tag`:

```java
@Entity
public class Article {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @ManyToMany
    private Set<Tag> tags = new HashSet<>();

    // Constructor, getters và setters
}
```

Khi endpoint nhận association collection trong JSON, client gửi một mảng URI tương ứng với các resource đã tồn tại:

```http
POST /articles HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "title": "Spring Data REST",
  "tags": [
    "http://localhost:8080/tags/3",
    "http://localhost:8080/tags/8"
  ]
}
```

Mỗi URI xác định một Tag được liên kết với Article mới. Kiểu JSON cần phù hợp với kiểu association trong domain model, ví dụ mảng URI cho collection. Hãy xác nhận tên property và representation mà endpoint thực tế hỗ trợ; không gửi một object lồng nhau chứa toàn bộ Tag nếu mục tiêu chỉ là liên kết đến Tag đã tồn tại.

Với collection association, cần hiểu semantics của thao tác cập nhật. Một payload `PATCH` hoặc `PUT` có thể được áp dụng theo cơ chế binding của endpoint và kiểu collection; nếu mục tiêu là thêm hoặc xóa riêng một liên kết, association endpoint thường thể hiện ý định rõ hơn.

## 5. URI tham chiếu khác với object lồng nhau

Giả sử Customer số 42 đã tồn tại. Đây là cách gửi tham chiếu:

```json
{
  "description": "Laptop order",
  "customer": "http://localhost:8080/customers/42"
}
```

Đây là object lồng nhau:

```json
{
  "description": "Laptop order",
  "customer": {
    "id": 42,
    "name": "Ada Lovelace"
  }
}
```

Hai payload không có cùng ý nghĩa. URI nói rõ client muốn liên kết đến một resource đã được quản lý bởi repository. Object lồng nhau có thể được Jackson xem như dữ liệu cần deserialize thành object mới hoặc không được chuyển đổi theo cách mong muốn cho association; không nên dựa vào nó để tìm và cập nhật entity đã tồn tại.

Nếu cần tạo Customer mới, hãy tạo Customer qua collection resource của Customer trước, nhận URI từ header `Location` hoặc link `self`, rồi dùng URI đó khi tạo Order. Nếu cần cập nhật thông tin Customer, gọi endpoint của Customer bằng thao tác cập nhật riêng.

## 6. Lấy URI đúng từ HAL response

Không nên tự ghép URI từ ID nếu API có thể thay đổi base path, context path, resource path hoặc chạy sau reverse proxy. Hãy dùng các link mà server trả về.

Ví dụ response của Customer:

```json
{
  "id": 42,
  "name": "Ada Lovelace",
  "_links": {
    "self": {
      "href": "https://api.example.com/shop/customers/42"
    }
  }
}
```

Client lấy giá trị `_links.self.href` rồi đưa vào thuộc tính association trong JSON của request tạo hoặc cập nhật Order. Cách này giữ đúng host và path do server công bố.

Nếu association được tùy chỉnh bằng `@RestResource`, tên relation hiển thị trong HAL có thể khác tên property trong domain model. Hãy dùng link HAL để tìm endpoint association; khi gửi JSON entity body, dùng đúng property name mà Jackson và Spring Data REST expose.

## 7. Association endpoint và media type text/uri-list

Ngoài việc gửi URI trong JSON body của entity, Spring Data REST còn công bố association resource riêng. Link này thường xuất hiện trên item resource, ví dụ:

```json
{
  "_links": {
    "self": { "href": "http://localhost:8080/orders/100" },
    "customer": { "href": "http://localhost:8080/orders/100/customer" },
    "tags": { "href": "http://localhost:8080/orders/100/tags" }
  }
}
```

Để thay đổi association qua endpoint riêng, client có thể dùng URI trong body với media type `text/uri-list`. Ví dụ gán Customer số 43 cho Order số 100:

```http
PUT /orders/100/customer HTTP/1.1
Content-Type: text/uri-list

http://localhost:8080/customers/43
```

Với collection association, `text/uri-list` có thể chứa một URI trên mỗi dòng:

```http
PUT /articles/10/tags HTTP/1.1
Content-Type: text/uri-list

http://localhost:8080/tags/3
http://localhost:8080/tags/8
```

Hãy kiểm tra semantics của association endpoint trước khi dùng `PUT`: với collection, thao tác này thường đặt tập liên kết theo danh sách URI được gửi. Nếu chỉ muốn thêm hoặc gỡ một liên kết, chọn HTTP method mà association resource hỗ trợ và đọc tài liệu Spring Data REST của phiên bản đang dùng.

Hai cách gửi dữ liệu cần được phân biệt:

| Cách gửi | Endpoint | Content-Type | Mục đích |
| --- | --- | --- | --- |
| URI trong JSON | Collection hoặc item resource | `application/json` | Tạo hoặc cập nhật entity cùng association |
| URI list | Association resource lấy từ HAL link | `text/uri-list` | Thay đổi association qua endpoint riêng |

Không gửi `text/uri-list` đến collection endpoint tạo entity nếu endpoint đó đang mong đợi JSON representation.

## 8. Quy tắc phân giải URI và các lỗi thường gặp

Khi server phân giải URI association, một số điều kiện cần được đáp ứng:

1. URI phải trỏ đến đúng item resource, không phải collection endpoint.
2. Resource đích phải tồn tại và có thể được phân giải trong ứng dụng.
3. URI phải thuộc đúng association type. Ví dụ, thuộc tính `customer` cần trỏ đến Customer, không phải Address.
4. Người dùng hiện tại phải được phép đọc hoặc liên kết resource đích theo chính sách bảo mật của ứng dụng.
5. Domain mapping phải cho phép thay đổi association; với JPA bidirectional relationship, cần cập nhật đúng owning side để thay đổi được lưu.

Các lỗi thường gặp:

**Gửi ID thay vì URI**

Payload `"customer": 42` chỉ là một số JSON, không phải URI tham chiếu resource. Hãy gửi URI của item resource, ví dụ `"customer": "http://localhost:8080/customers/42"`.

**Gửi object lồng nhau**

Payload `"customer": {"id": 42}` không thể hiện rõ ý định liên kết đến entity hiện có. Dùng URI từ link `self`.

**Dùng collection URI thay cho item URI**

`http://localhost:8080/customers` trỏ đến collection. Muốn liên kết một Customer cụ thể, dùng item URI như `http://localhost:8080/customers/42`.

**URI không tồn tại hoặc không đúng loại**

Server không thể phân giải resource đích; request sẽ thất bại theo cơ chế exception mapping của ứng dụng. Kiểm tra URI, repository path, base path và loại association.

**Bị từ chối bởi bảo mật**

Một URI hợp lệ về mặt cú pháp vẫn có thể không được phép liên kết. Kiểm tra authorization cho cả thao tác trên entity nguồn và resource đích; không tin URI do client cung cấp chỉ vì nó có dạng hợp lệ.

**Thay đổi association nhưng dữ liệu không được lưu**

Với JPA relationship hai chiều, kiểm tra owning side, cascade và helper method đồng bộ hai phía. Spring Data REST có thể bind association nhưng persistence vẫn phụ thuộc mapping ORM.

## 9. Ví dụ hoàn chỉnh: tạo Order và liên kết Customer

Giả sử Customer đã được tạo trước đó và HAL response trả về:

```json
{
  "name": "Ada Lovelace",
  "_links": {
    "self": {
      "href": "http://localhost:8080/customers/42"
    }
  }
}
```

Dùng URI `self` đó để tạo Order:

```bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{
    "description": "Laptop order",
    "customer": "http://localhost:8080/customers/42"
  }'
```

Sau khi tạo thành công, đọc response để lấy URI của Order mới trong header `Location`. Gọi item resource đó và xem link `customer` để xác nhận association. Nếu muốn chuyển Order sang Customer khác, gửi `PATCH` đến item resource với URI Customer mới hoặc sử dụng association endpoint được công bố trong HAL.

## Tóm tắt

- Khi tạo hoặc cập nhật entity, gửi URI item resource trong thuộc tính association của JSON body để tham chiếu entity đã tồn tại.
- Với quan hệ đơn, giá trị thường là một URI string; với collection association, representation có thể là mảng URI.
- Lấy URI từ link `self` của HAL response thay vì tự ghép URL.
- Object lồng nhau và ID đơn lẻ không thay thế cho URI tham chiếu resource.
- Association endpoint là cách riêng để thay đổi quan hệ; endpoint này thường nhận `text/uri-list`.
- Xác minh resource đích, kiểu quan hệ, quyền truy cập và mapping ORM trước khi lưu.

## Tài liệu tham khảo

- [Spring Data REST — Handling associations](https://docs.spring.io/spring-data/rest/reference/handling-associations.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing association resource exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
