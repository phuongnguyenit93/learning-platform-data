# Ánh xạ lời gọi HTTP đến phương thức repository

## Mục tiêu

Khi một ứng dụng dùng Spring Data REST, một repository được export có thể trở thành REST API mà không cần viết controller CRUD riêng. Spring Data REST đọc metadata của repository và domain type, tạo các resource tương ứng, rồi ánh xạ từng cặp **đường dẫn + HTTP method** sang thao tác repository phù hợp.

Điểm cần nhớ: endpoint CRUD không được tạo bằng cách đổi tên tùy ý một method Java thành URL. Với resource chuẩn, Spring Data REST quyết định thao tác dựa trên loại resource, HTTP method và các method repository đang được export. Các query method được công bố riêng dưới resource `search`.

## 1. Luồng xử lý từ HTTP đến repository

Một request đi qua các bước khái quát sau:

1. **Nhận diện repository được export.** Spring MVC nhận request. RepositoryRestHandlerMapping kiểm tra segment đầu của URL có khớp với resource mapping của một repository được export hay không. Nếu không, handler mapping khác của ứng dụng có thể xử lý request.
2. **Xác định loại resource.** Phần đường dẫn cho biết request nhắm tới collection, một item theo ID, association của item, search resource hay một query method.
3. **Kiểm tra HTTP method có được hỗ trợ.** Spring Data REST đối chiếu method cần dùng với các method mà repository khai báo và cho phép export. Nếu thao tác tương ứng không tồn tại hoặc bị tắt bằng exported = false, verb đó không được cung cấp và thường trả về 405 Method Not Allowed.
4. **Chuyển đổi dữ liệu đầu vào.** ID trên URL được chuyển sang kiểu ID của repository; query string được chuyển thành tham số method, Pageable hoặc Sort; request body được deserialize thành domain object hoặc dữ liệu cập nhật.
5. **Gọi repository.** Với CRUD chuẩn, Spring Data REST dùng metadata và RepositoryInvoker để gọi method phù hợp như findAll, findById, save hoặc delete. Với query resource, framework gọi query method đã được export.
6. **Tạo HTTP response.** Kết quả được chuyển thành representation JSON/HAL, kèm các link liên quan, metadata phân trang và header phù hợp như Location khi tạo resource.

Có thể hình dung luồng như sau:

~~~text
HTTP request
    |
    v
RepositoryRestHandlerMapping
    |
    v
Resource mapping + HTTP method
    |
    v
Collection / Item / Association / Search
    |
    v
Bind ID, query parameters, Pageable, request body
    |
    v
RepositoryInvoker hoặc query method đã export
    |
    v
Spring Data repository proxy -> store implementation
    |
    v
HAL/JSON representation + HTTP status/headers
~~~

Repository proxy của Spring Data mới là nơi thực thi truy vấn hoặc thao tác trên datastore. Spring Data REST đảm nhiệm việc nhận diện resource, chuyển request thành lời gọi repository và chuyển kết quả thành HTTP response.

## 2. Bản đồ HTTP method và repository method

Giả sử repository quản lý entity Person và được export tại đường dẫn `/people`.

| Resource | HTTP request | Method repository được dùng |
|---|---|---|
| Collection `/people` | GET | Ưu tiên `findAll(Pageable)`, sau đó `findAll(Sort)`, rồi `findAll()` nếu các method đó có sẵn và được export |
| Collection `/people` | POST | `save(entity)` để tạo entity từ request body |
| Collection `/people` | HEAD | Kiểm tra resource bằng các biến thể `findAll` có sẵn; không trả response body |
| Item `/people/{id}` | GET | `findById(id)` |
| Item `/people/{id}` | HEAD | Dùng khả năng tra cứu theo ID như GET, nhưng không trả response body |
| Item `/people/{id}` | PUT | `save(entity)` sau khi thay thế trạng thái resource bằng dữ liệu request |
| Item `/people/{id}` | PATCH | `save(entity)` sau khi áp dụng phần thay đổi được gửi lên |
| Item `/people/{id}` | DELETE | Dùng overload delete phù hợp đang được export, chẳng hạn `delete(entity)`, `delete(id)` hoặc `delete(entities)` |
| Search `/people/search` | GET | Trả danh sách link tới các query method đã export; chưa chạy một query cụ thể |
| Query `/people/search/...` | GET | Gọi chính query method tương ứng trên repository |

Thứ tự lựa chọn của collection GET có ý nghĩa. Nếu repository hỗ trợ `findAll(Pageable)`, Spring Data REST có thể nhận `page`, `size`, `sort` và trả dữ liệu kèm metadata/link phân trang. Nếu không có biến thể Pageable, framework xét các biến thể khác theo thứ tự trong bảng.

### Ý nghĩa của từng nhóm thao tác

- **GET collection** đọc danh sách. Với repository có hỗ trợ paging, `page` bắt đầu từ 0, `size` là số phần tử mỗi trang và `sort` mô tả thuộc tính cùng chiều sắp xếp.
- **POST collection** nhận một representation của entity, gọi `save` và tạo item resource. Response thường có status 201 Created cùng header Location trỏ tới item mới. Response body phụ thuộc Accept header và cấu hình trả body khi tạo.
- **GET item** chuyển ID trong URL sang đúng kiểu ID, gọi `findById` và biểu diễn entity tìm được. Không tìm thấy item thường dẫn tới 404 Not Found.
- **PUT item** thay thế trạng thái resource bằng representation được gửi lên. **PATCH item** chỉ áp dụng các trường/phần thay đổi có trong request. Cả hai dùng `save` để lưu trạng thái cuối cùng; việc datastore thực hiện insert hay update phụ thuộc repository và store.
- **DELETE item** xóa item bằng overload delete mà repository hỗ trợ. DELETE trên association là thao tác gỡ liên kết, khác với xóa entity.
- **Search** là điểm khám phá query method. GET `/people/search` trả các link; GET link của một query method mới thực thi truy vấn.

Không nên suy luận rằng mọi repository method đều có endpoint tương ứng. Các method CRUD chuẩn và query method đủ điều kiện export được xử lý theo quy tắc riêng. Một method nghiệp vụ tùy ý không tự động trở thành endpoint POST chỉ vì nó nằm trong repository interface.

## 3. Query method được ánh xạ dưới /search

Các query method được export xuất hiện dưới resource `search`. Tên resource mặc định thường dựa trên tên method, còn đường dẫn và relation có thể đổi bằng `@RestResource`.

Ví dụ repository tổng quát:

~~~java
@RepositoryRestResource(path = "people", collectionResourceRel = "people")
public interface PersonRepository
        extends CrudRepository<Person, Long>,
                PagingAndSortingRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    Page<Person> findByLastname(
            @Param("lastname") String lastname,
            Pageable pageable);
}
~~~

Ví dụ trên dùng cả CrudRepository và PagingAndSortingRepository để thể hiện rõ hai nhóm khả năng CRUD và paging. Với repository chuyên biệt của một store, chẳng hạn JpaRepository, các interface đó thường đã được kết hợp sẵn.

Nếu cấu hình base path:

~~~properties
spring.data.rest.base-path=/api
~~~

thì các request tiêu biểu là:

~~~http
GET    /api/people
POST   /api/people
GET    /api/people/42
PUT    /api/people/42
PATCH  /api/people/42
DELETE /api/people/42

GET    /api/people/search
GET    /api/people/search/by-last-name?lastname=Nguyen&page=0&size=10
~~~

Trong ví dụ query method:

- `by-last-name` là path được đặt bởi `@RestResource(path = "by-last-name")`.
- `lastname=Nguyen` được bind vào tham số `@Param("lastname")`.
- `page`, `size` và `sort` được bind cho Pageable nếu method hỗ trợ phân trang.
- Kết quả trả về là resource collection có metadata và link phân trang; query được thực thi bởi `findByLastname(...)`.

GET `/api/people/search` giúp client khám phá link query method thay vì phải tự đoán URL. Client nên đọc các link HAL do server trả về, đặc biệt khi path hoặc relation đã được tùy chỉnh.

## 4. Association resource không phải CRUD item thông thường

Với association được Spring Data REST nhận diện trong domain model, item có thể cung cấp link tới association resource, thường đặt theo tên property. Ví dụ:

~~~text
GET /api/people/42
    -> _links.address.href = /api/people/42/address
~~~

Association resource hỗ trợ các thao tác theo quan hệ:

| HTTP method | Ý nghĩa |
|---|---|
| GET | Đọc resource đang được liên kết |
| PUT | Gán resource được chỉ định vào association; thường gửi URI bằng media type text/uri-list |
| POST | Chỉ dùng cho association dạng collection; thêm một resource vào collection bằng URI |
| DELETE | Gỡ liên kết; không đồng nghĩa xóa entity được liên kết |

Ví dụ body cho thao tác gán liên kết:

~~~http
PUT /api/people/42/address
Content-Type: text/uri-list

http://localhost:8080/api/addresses/8
~~~

Vì association được thao tác qua URI của resource liên quan, client cần dùng đúng URI mà API công bố. Đối với association một-một/một-nhiều, khả năng PUT/POST/DELETE còn phụ thuộc kiểu quan hệ và metadata của domain model. Association không nên được hiểu như một lời gọi tùy ý tới method `saveAddress` trên repository.

## 5. Điều gì quyết định một HTTP method có được mở hay không?

Việc export endpoint phụ thuộc vào cấu trúc repository và cấu hình Spring Data REST:

- Repository phải được phát hiện và export. Đường dẫn collection mặc định được suy ra từ domain type; có thể đổi bằng `@RepositoryRestResource`.
- HTTP operation chỉ được cung cấp khi repository có method cần thiết. Ví dụ, thiếu `save` thì không thể tạo/cập nhật theo các route chuẩn.
- Method có thể bị ẩn bằng `@RestResource(exported = false)`. Ví dụ:

~~~java
@RestResource(exported = false)
@Override
void deleteById(Long id);
~~~

- Có thể tắt export cả repository bằng `@RepositoryRestResource(exported = false)`.
- Có thể đổi path và relation của repository hoặc query method bằng `@RepositoryRestResource` và `@RestResource`.
- Các cấu hình exposure của Spring Data REST có thể giới hạn HTTP method theo resource type hoặc repository.

Nếu một method không tồn tại hoặc không được export, request dùng verb tương ứng thường nhận 405 Method Not Allowed. Đây là khác biệt với 404: 404 thường cho biết đường dẫn/resource hoặc item không được tìm thấy, còn 405 cho biết resource có route nhưng verb đó không được hỗ trợ.

Export endpoint và phân quyền là hai việc riêng. `exported = false` điều khiển việc công bố method/resource; Spring Security vẫn cần được cấu hình để giới hạn người dùng được phép đọc, tạo, sửa hoặc xóa dữ liệu.

Nếu cần một thao tác nghiệp vụ riêng, ví dụ xác nhận đơn hàng hoặc tính phí, hãy thiết kế custom controller phù hợp thay vì kỳ vọng Spring Data REST tự ánh xạ method tùy ý thành HTTP endpoint. Query method dưới `search` chủ yếu dành cho thao tác truy vấn GET.

## 6. Đọc request và response khi debug

Khi một request không gọi đúng repository method như dự kiến, kiểm tra theo thứ tự sau:

1. **Kiểm tra root resource.** Gửi GET tới base path và xem các link HAL. Nếu collection link không xuất hiện, repository có thể chưa được phát hiện/export hoặc path đang được tùy chỉnh.
2. **Kiểm tra collection link.** GET collection để xác nhận resource và xem có link `search` hay không.
3. **Kiểm tra search link.** GET `/search` để xem query method nào thực sự được export. Đừng suy đoán path chỉ từ tên method Java nếu có `@RestResource`.
4. **Đối chiếu HTTP verb với method repository.** GET item cần khả năng findById; POST collection cần save; PUT/PATCH cần save; DELETE cần delete method phù hợp.
5. **Kiểm tra annotation export.** Tìm `@RepositoryRestResource(exported = false)` hoặc `@RestResource(exported = false)`, kể cả annotation đặt trên method được override.
6. **Kiểm tra binding.** Xác nhận ID đúng kiểu, tên query parameter khớp `@Param`, Pageable/Sort được khai báo, JSON có đúng cấu trúc và Content-Type phù hợp.
7. **Đọc status và header.** Location cho biết URI item được tạo; 405 gợi ý verb không được export; 404 gợi ý resource/item không tồn tại; 400 thường liên quan dữ liệu hoặc tham số không hợp lệ; 415 cho biết media type không được hỗ trợ.

Các response phổ biến:

| Status | Cách hiểu trong luồng này |
|---|---|
| 200 OK | GET thành công; update/delete cũng có thể trả body tùy cấu hình |
| 201 Created | Resource mới được tạo, thường kèm Location |
| 204 No Content | Thao tác thành công nhưng không trả body |
| 400 Bad Request | ID, tham số hoặc request body không hợp lệ |
| 404 Not Found | Không có resource/item được yêu cầu |
| 405 Method Not Allowed | Resource không hỗ trợ HTTP method đó hoặc method repository đã bị ẩn |
| 415 Unsupported Media Type | Content-Type không nằm trong nhóm media type được endpoint hỗ trợ |

## 7. Những nhầm lẫn thường gặp

- **GET collection không tự gọi một method findBy... tùy ý.** GET collection dùng các biến thể findAll; truy vấn lọc riêng được gọi qua query resource dưới `/search`.
- **Tên repository method không quyết định toàn bộ URL.** Collection path, query path và relation có thể được tùy chỉnh bằng annotation.
- **save không đồng nghĩa luôn luôn INSERT.** Spring Data REST gọi save; repository/store quyết định cách lưu entity dựa trên ID và trạng thái.
- **PUT và PATCH có ý nghĩa khác nhau.** PUT thay thế trạng thái resource; PATCH áp dụng thay đổi một phần. Cả hai vẫn có thể đi tới save sau khi dữ liệu đã được bind.
- **DELETE association không xóa entity liên quan.** Nó gỡ quan hệ giữa hai resource.
- **Không phải mọi method trong interface đều được export.** Chỉ những resource/method đáp ứng quy tắc export và cấu hình mới có endpoint.
- **405 không phải lỗi repository query.** Trước tiên hãy kiểm tra method có được export và verb có hợp lệ cho loại resource đó hay không.

## 8. Tóm tắt cách lần theo một request

Khi nhìn thấy một HTTP request, hãy đọc theo chuỗi:

**URL → loại resource → HTTP method → repository method cần có → binding tham số/body → kết quả repository → HAL/JSON response.**

Ví dụ với `GET /api/people/42`:

1. `people` khớp repository được export.
2. `42` cho biết đây là item resource, không phải collection.
3. GET chọn thao tác đọc item.
4. ID được chuyển sang kiểu ID của Person.
5. Spring Data REST gọi `findById(42L)`.
6. Entity được chuyển thành representation và trả về; nếu không có entity, response là 404.

Ví dụ với `GET /api/people/search/by-last-name?lastname=Nguyen`:

1. `people/search` xác định search resource của repository.
2. `by-last-name` chọn query method đã export.
3. `lastname` được bind vào tham số method.
4. Pageable/Sort được bind nếu method hỗ trợ.
5. Spring Data gọi query method và Spring Data REST biểu diễn kết quả.

## Tài liệu tham khảo

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Project overview](https://spring.io/projects/spring-data-rest/)
