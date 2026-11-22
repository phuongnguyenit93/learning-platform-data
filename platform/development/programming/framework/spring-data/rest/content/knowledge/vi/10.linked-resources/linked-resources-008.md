# DELETE để gỡ liên kết và phân biệt với xóa thực thể đích trong Spring Data REST

Spring Data REST có thể công bố cả tài nguyên entity và tài nguyên association (liên kết giữa các entity). Cả hai loại tài nguyên đều có thể liên quan đến HTTP DELETE, nhưng ý nghĩa nghiệp vụ khác nhau:

- **DELETE association resource** yêu cầu gỡ một quan hệ giữa hai tài nguyên. Ví dụ: bỏ địa chỉ khỏi hồ sơ của một người.
- **DELETE item resource** yêu cầu xóa chính entity được định danh bởi URI. Ví dụ: xóa bản ghi địa chỉ khỏi repository.

Gỡ một liên kết không đồng nghĩa với xóa entity ở đầu bên kia của liên kết. Khi thiết kế client, cần xác định chính xác URI mà HAL công bố và chọn đúng tài nguyên đích cho thao tác DELETE.

## 1. Entity resource và association resource

Giả sử ứng dụng quản lý người và địa chỉ. Một người có một địa chỉ:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne
    private Address address;

    // getters and setters
}
~~~

Địa chỉ là một entity độc lập:

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue
    private Long id;

    private String city;

    private String street;

    // getters and setters
}
~~~

Hai repository có thể được công bố qua Spring Data REST:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}

@RepositoryRestResource(path = "addresses")
public interface AddressRepository extends JpaRepository<Address, Long> {
}
~~~

Giả sử person có ID 42 và address có ID 7. Các URI minh họa:

- Entity resource của người: `/people/42`.
- Entity resource của địa chỉ: `/addresses/7`.
- Association resource của thuộc tính `address` trên người: `/people/42/address`.

Hai URI cuối cùng phục vụ hai đối tượng khác nhau. `/addresses/7` định danh entity Address; `/people/42/address` định danh quan hệ address của Person 42.

URI thực tế phụ thuộc repository path, base path, mapping association, cấu hình export và các liên kết được Spring Data REST công bố. Client nên khám phá liên kết từ response thay vì tự suy ra URL.

## 2. DELETE trên association resource: gỡ quan hệ

Giả sử response của `GET /people/42` công bố liên kết:

~~~json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    }
  }
}
~~~

Nếu client muốn người này không còn gắn với địa chỉ hiện tại, client gọi DELETE trên association resource:

~~~http
DELETE /people/42/address
~~~

Thao tác này yêu cầu Spring Data REST gỡ quan hệ giữa Person 42 và Address đang được liên kết. Với association to-one có thể biểu diễn sau khi gỡ là không còn giá trị, chẳng hạn thuộc tính address được đặt thành null nếu domain model và ràng buộc dữ liệu cho phép.

Request trên không phải là yêu cầu xóa entity Address. Entity đích vẫn có URI riêng là `/addresses/7` và có thể tiếp tục được truy cập nếu vẫn tồn tại và được export.

Ví dụ sau khi gỡ association, representation của người có thể không còn liên kết `address`:

~~~json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

Response thực tế còn phụ thuộc cấu hình representation và các association khác. Điểm cần hiểu là thao tác xóa relation thay đổi mối liên hệ của Person với Address; nó không tự động có nghĩa xóa Address khỏi kho dữ liệu.

## 3. DELETE một phần tử trong collection association

Một entity có thể liên kết với nhiều entity khác. Ví dụ, một người có nhiều nhóm hoặc vai trò:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany
    private Set<Role> roles = new HashSet<>();

    // getters and setters
}
~~~

Nếu collection association được công bố với relation `roles`, item resource có thể cung cấp liên kết tới association resource:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "roles": {
      "href": "http://localhost:8080/people/42/roles"
    }
  }
}
~~~

Để gỡ một role cụ thể khỏi người đó, Spring Data REST thường công bố URI association item có thêm định danh phần tử, ví dụ:

~~~http
DELETE /people/42/roles/7
~~~

Thao tác này gỡ liên kết giữa Person 42 và Role 7. Nếu Role 7 còn được dùng bởi người khác, entity Role vẫn tồn tại và các quan hệ khác vẫn được giữ.

Đối với collection association, cần phân biệt ba ý định:

- Xem các phần tử đang liên kết qua association resource.
- Gỡ một phần tử cụ thể khỏi collection association.
- Xóa entity phần tử khỏi repository của nó.

Client phải dùng đúng liên kết mà API công bố cho association và phần tử cần gỡ. Cấu trúc URI minh họa có thể thay đổi theo loại association và mapping của ứng dụng.

## 4. DELETE trên item resource: xóa chính entity

Nếu mục tiêu thực sự là xóa Address 7 khỏi hệ thống, client gửi DELETE tới entity resource của Address:

~~~http
DELETE /addresses/7
~~~

Đây là thao tác xóa entity Address có ID 7 thông qua repository của Address. Nó khác với:

~~~http
DELETE /people/42/address
~~~

Request thứ nhất nhắm tới bản ghi Address. Request thứ hai nhắm tới quan hệ address của Person 42.

Khi entity bị xóa, các association trỏ đến entity đó có thể bị ảnh hưởng bởi ràng buộc khóa ngoại, mapping ORM, cascade, xử lý tham chiếu và logic nghiệp vụ. Ứng dụng có thể cần gỡ liên kết trước, từ chối xóa vì còn tham chiếu, hoặc xử lý các quan hệ liên quan trong transaction.

Không nên dùng DELETE item resource chỉ vì muốn bỏ entity khỏi một collection của entity khác. Nếu entity vẫn cần tồn tại cho các quan hệ hoặc nghiệp vụ khác, hãy gỡ association tương ứng.

## 5. Bảng phân biệt hai loại thao tác

| Request | Tài nguyên bị tác động | Ý nghĩa |
|---|---|---|
| `DELETE /people/42/address` | Association resource | Gỡ địa chỉ khỏi Person 42 |
| `DELETE /people/42/roles/7` | Một association trong collection | Gỡ Role 7 khỏi Person 42 |
| `DELETE /addresses/7` | Address item resource | Xóa entity Address 7 |
| `DELETE /people/42` | Person item resource | Xóa entity Person 42 |

Hãy nhìn vào URI và relation mà client đang theo. Nếu URI nằm dưới item resource của owner và thể hiện association, thao tác hướng tới quan hệ. Nếu URI là item resource của repository đích, thao tác hướng tới entity.

## 6. Gỡ association không bảo đảm entity luôn được giữ lại

Về mặt API, DELETE association yêu cầu loại bỏ quan hệ. Tuy nhiên, trạng thái entity sau khi gỡ còn chịu ảnh hưởng của domain model và cấu hình persistence.

Một số trường hợp cần lưu ý:

- **Many-to-many:** thường gỡ hàng liên kết trong bảng join; entity ở hai phía vẫn tồn tại.
- **Many-to-one:** thường bỏ tham chiếu từ entity owner tới entity được tham chiếu; entity đích vẫn tồn tại nếu không có logic khác xóa nó.
- **One-to-many với orphanRemoval:** nếu phần tử con bị loại khỏi quan hệ và mapping bật `orphanRemoval = true`, JPA có thể xóa entity con khi transaction được flush/commit.
- **Cascade remove:** thao tác xóa entity owner có thể lan sang entity liên quan nếu cấu hình cascade phù hợp. Đây là hành vi persistence cần phân biệt với ý nghĩa HTTP của DELETE association.
- **Ràng buộc khóa ngoại và validation:** database hoặc domain có thể từ chối việc gỡ association nếu quan hệ bắt buộc hoặc còn ràng buộc không thỏa mãn.

Ví dụ, một quan hệ bắt buộc có thể không cho phép đặt foreign key thành null. Trong trường hợp đó, request gỡ association có thể thất bại do validation hoặc lỗi persistence. Nếu nghiệp vụ yêu cầu xóa liên kết nhưng vẫn giữ entity đích, hãy cấu hình mapping và quy tắc domain phù hợp.

Với association hai chiều trong JPA, cần cập nhật đúng phía sở hữu quan hệ (owning side). Nhiều domain model cung cấp phương thức helper để cập nhật cả hai phía, chẳng hạn xóa một role khỏi collection và đồng bộ tham chiếu ngược. Hãy kiểm tra cách repository và association handler của ứng dụng cập nhật object graph để dữ liệu sau khi lưu đúng như mong đợi.

## 7. Vì sao client cần khám phá association link?

Spring Data REST dùng hypermedia để công bố các association. Thay vì ghép URL bằng cách nối chuỗi, client nên đọc relation trong `_links` của item resource.

Ví dụ:

~~~http
GET /people/42
Accept: application/hal+json
~~~

Response có thể chứa:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    },
    "address": {
      "href": "http://localhost:8080/people/42/address"
    },
    "roles": {
      "href": "http://localhost:8080/people/42/roles"
    }
  }
}
~~~

Client có thể dùng relation `address` hoặc `roles` để xác định association resource. Đối với collection association, client tiếp tục khám phá representation của collection và liên kết đến phần tử cụ thể nếu API công bố.

Cách này giúp client theo hợp đồng hypermedia khi server thay đổi host, context path hoặc cấu trúc URL. Client vẫn cần hiểu ý nghĩa relation và chỉ gửi DELETE khi người dùng hoặc nghiệp vụ thực sự yêu cầu gỡ quan hệ.

Nếu association bị ẩn hoặc không được export, client không nên đoán endpoint. Hãy kiểm tra cấu hình export và representation được công bố.

## 8. DELETE association và các thao tác thêm/thay thế liên kết

Để hiểu rõ ý nghĩa của DELETE, có thể đặt nó cạnh các thao tác tạo hoặc thay thế association.

Với association to-one, client có thể gán một tài nguyên liên quan bằng URI của tài nguyên đích:

~~~http
PUT /people/42/address
Content-Type: text/uri-list

http://localhost:8080/addresses/7
~~~

PUT ở đây đặt association address của Person 42 trỏ tới Address 7 theo hợp đồng association resource.

Với collection association, client thường thêm một phần tử bằng POST lên collection association resource:

~~~http
POST /people/42/roles
Content-Type: text/uri-list

http://localhost:8080/roles/7
~~~

Sau khi liên kết đã được tạo, DELETE association item có thể được dùng để gỡ phần tử cụ thể:

~~~http
DELETE /people/42/roles/7
~~~

Các ví dụ là mapping phổ biến của Spring Data REST. Hãy dùng đúng method, URI và media type mà phiên bản ứng dụng thực tế công bố hoặc hỗ trợ; association có thể khác nhau theo cardinality, mapping và cấu hình.

## 9. Quyền truy cập, validation và phản hồi HTTP

DELETE association vẫn là một thao tác thay đổi dữ liệu. Ứng dụng cần kiểm tra quyền của client trên cả entity owner và quan hệ cần gỡ. Không nên chỉ kiểm tra quyền xóa entity đích rồi suy ra client có quyền gỡ mọi association.

Các tình huống cần xử lý:

- Người dùng không có quyền sửa entity owner.
- Association không tồn tại hoặc phần tử không thuộc collection của owner.
- Association bắt buộc không được phép gỡ.
- Entity đích đang được tham chiếu bởi dữ liệu khác.
- Transaction thất bại do ràng buộc database hoặc lỗi persistence.
- Entity đã bị xóa hoặc thay đổi bởi một request đồng thời.

Mã HTTP cụ thể phụ thuộc endpoint, phiên bản Spring Data REST và cấu hình xử lý lỗi. Client không nên giả định mọi DELETE đều trả cùng một status hoặc response body. Hãy xử lý các phản hồi thành công và lỗi theo hợp đồng API, sau đó GET lại resource khi cần xác nhận trạng thái.

## 10. Kiểm thử để bảo đảm không xóa nhầm entity

Một integration test nên xác nhận cả association lẫn sự tồn tại của entity đích.

Ví dụ với to-one association:

1. Tạo Address 7 và Person 42 có tham chiếu tới Address 7.
2. Gọi DELETE trên association resource của Person 42.
3. Đọc lại Person 42 và xác nhận association address đã được gỡ.
4. Đọc trực tiếp `/addresses/7` hoặc truy vấn repository để xác nhận Address 7 vẫn tồn tại nếu mapping không có orphan-removal hoặc logic xóa liên quan.
5. Gọi DELETE trên `/addresses/7` trong một test riêng để xác nhận hành vi xóa entity và các ràng buộc liên quan.

Ví dụ với collection association:

1. Tạo Person 42 có Role 7 và một Role khác.
2. Gọi DELETE trên association item của Role 7.
3. Đọc lại collection roles của Person 42 và xác nhận Role 7 không còn liên kết.
4. Xác nhận Role 7 vẫn tồn tại và quan hệ của nó với owner khác vẫn được giữ nếu nghiệp vụ yêu cầu.
5. Kiểm tra trường hợp gỡ một role không thuộc Person 42 và xác nhận response phù hợp.

Nếu JPA bật orphanRemoval, hãy viết test riêng để xác định entity con có bị xóa sau khi gỡ khỏi collection hay không. Kết quả này phụ thuộc mapping, không thể suy ra chỉ từ tên HTTP method.

## 11. Cách chọn endpoint trong ứng dụng

Dùng DELETE trên association resource khi mục tiêu là gỡ quan hệ giữa hai entity mà vẫn muốn giữ entity đích độc lập. Ví dụ: bỏ một địa chỉ khỏi hồ sơ người dùng hoặc gỡ một vai trò khỏi danh sách vai trò của người đó.

Dùng DELETE trên item resource khi mục tiêu là xóa chính entity khỏi repository và ứng dụng cho phép thao tác đó. Ví dụ: xóa hẳn một địa chỉ không còn được quản lý.

Trước khi gửi request, xác định:

- URI thuộc item resource hay association resource.
- Entity nào là owner và entity nào là target.
- Quan hệ là to-one hay collection.
- Mapping có orphanRemoval, cascade hoặc ràng buộc bắt buộc hay không.
- Client có quyền gỡ association hoặc xóa entity tương ứng hay không.

## 12. Những điểm cần ghi nhớ

- DELETE association resource gỡ quan hệ; DELETE item resource xóa entity được định danh bởi URI.
- `DELETE /people/42/address` minh họa việc gỡ địa chỉ khỏi Person 42; `DELETE /addresses/7` minh họa xóa Address 7.
- Với collection association, dùng association resource và định danh phần tử theo mapping được Spring Data REST công bố để gỡ đúng một liên kết.
- Gỡ association không tự động đồng nghĩa xóa entity đích, nhưng orphanRemoval, cascade, validation và persistence mapping có thể ảnh hưởng đến trạng thái dữ liệu.
- Client nên khám phá relation từ HAL thay vì tự ghép URL.
- Kiểm thử cần xác nhận cả việc liên kết đã bị gỡ và entity đích vẫn tồn tại khi nghiệp vụ yêu cầu giữ lại.
