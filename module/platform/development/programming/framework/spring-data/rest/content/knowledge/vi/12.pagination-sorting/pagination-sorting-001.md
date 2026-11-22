# Điều kiện để tài nguyên tập hợp hỗ trợ phân trang và sắp xếp

## Mục tiêu

Khi Spring Data REST xuất bản một repository thành REST API, endpoint tập hợp (collection resource) có thể trả về toàn bộ bản ghi hoặc một phần kết quả theo trang. Phân trang giúp giới hạn lượng dữ liệu trong mỗi phản hồi; sắp xếp giúp client yêu cầu thứ tự kết quả mà không phải tạo endpoint riêng cho từng cách sắp xếp.

Hai khả năng này chỉ xuất hiện khi repository và phương thức được Spring Data REST sử dụng có hỗ trợ tương ứng. Việc một endpoint có dạng `GET /people` chưa tự động bảo đảm rằng nó nhận được `page`, `size` và `sort`.

## 1. Repository phải được Spring Data REST xuất bản

Spring Data REST chỉ tạo collection resource cho repository được phát hiện và cho phép export. Ví dụ, repository dưới đây được xuất bản tại đường dẫn `/people`:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Nếu không khai báo `path`, Spring Data REST tự suy ra đường dẫn từ tên miền hoặc cấu hình repository. Có thể dùng `@RepositoryRestResource(exported = false)` để tắt export cho toàn bộ repository.

Phương thức đọc danh sách cũng phải được export. Nếu các phương thức `findAll(...)` không tồn tại hoặc bị ẩn bằng `@RestResource(exported = false)`, yêu cầu GET tới collection resource có thể nhận `405 Method Not Allowed`.

## 2. Repository phải cung cấp phương thức phân trang hoặc sắp xếp

Spring Data REST chọn phương thức đọc collection theo thứ tự ưu tiên sau:

1. `findAll(Pageable)`: hỗ trợ phân trang và có thể kèm sắp xếp.
2. `findAll(Sort)`: hỗ trợ sắp xếp nhưng không cung cấp phân trang.
3. `findAll()`: trả về danh sách không có khả năng phân trang hoặc sắp xếp động.

Vì vậy, để collection resource hỗ trợ cả hai khả năng, repository cần có phương thức `findAll(Pageable)` và hạ tầng Spring Data tương ứng phải triển khai phương thức đó. Khi phương thức này có mặt và được export, Spring Data REST có thể chuyển các tham số HTTP thành một đối tượng `Pageable`; đối tượng này chứa số trang, kích thước trang và thông tin sắp xếp.

Ví dụ với Spring Data JPA:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

`JpaRepository` cung cấp các khả năng CRUD, phân trang và sắp xếp cho repository JPA. Với repository tổng quát, có thể kế thừa `PagingAndSortingRepository<T, ID>` để có `findAll(Pageable)` và `findAll(Sort)`.

**Lưu ý với Spring Data 3.x:** `PagingAndSortingRepository` không còn kế thừa `CrudRepository`. Nếu cần cả CRUD lẫn phân trang/sắp xếp khi dùng các interface tổng quát, hãy kết hợp hai interface hoặc dùng abstraction của store như `JpaRepository`.

Ví dụ kết hợp interface tổng quát:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, Long>,
                PagingAndSortingRepository<Person, Long> {
}
~~~

Khả năng thực thi còn phụ thuộc vào module lưu trữ đang dùng. Repository JPA cần được Spring Data JPA triển khai; repository của MongoDB, JDBC hoặc store khác cần dùng abstraction tương ứng có hỗ trợ `Pageable` và `Sort`. Chỉ thêm kiểu tham số vào một phương thức tự cài đặt không làm cho truy vấn bên dưới tự động phân trang hoặc sắp xếp.

## 3. Phương thức truy vấn riêng phải khai báo đúng chữ ký

Các query method được Spring Data REST export thành tài nguyên tìm kiếm dưới đường dẫn `/search`. Để một query method hỗ trợ phân trang, chữ ký phương thức phải:

- Nhận thêm tham số kiểu `Pageable`.
- Trả về `Page<T>` hoặc `Slice<T>`, thay vì chỉ trả về `List<T>`.
- Được export và có thể được gọi qua repository REST.

Ví dụ:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    Page<Person> findByLastNameStartingWithIgnoreCase(
            @Param("prefix") String prefix,
            Pageable pageable);
}
~~~

Spring Data REST có thể xuất phương thức trên thành endpoint tìm kiếm tương tự:

~~~http
GET /people/search/by-last-name?prefix=Ng&page=0&size=5
~~~

Client có thể thêm tham số `sort` vào cùng URL. Nếu phương thức nhận `Pageable` nhưng trả về `List<T>`, Spring Data có thể giới hạn dữ liệu theo Pageable trong một số cách gọi nội bộ, nhưng Spring Data REST không có kiểu `Page` hoặc `Slice` để biểu diễn đầy đủ kết quả phân trang và các liên kết điều hướng. Vì vậy, với query method được xuất bản qua Spring Data REST, hãy dùng `Page<T>` hoặc `Slice<T>` khi cần phân trang.

Nếu chỉ cần sắp xếp cho một query method, có thể nhận tham số `Sort`:

~~~java
List<Person> findByActiveTrue(Sort sort);
~~~

Phương thức này hỗ trợ sắp xếp động; nó không tự cung cấp thông tin tổng số trang. Khi cần cả phân trang và sắp xếp, dùng `Pageable`.

## 4. Tham số HTTP mà collection resource nhận

Khi repository có khả năng phân trang, Spring Data REST mặc định nhận các tham số:

| Tham số | Ý nghĩa | Giá trị mặc định |
|---|---|---|
| `page` | Số thứ tự trang, bắt đầu từ 0 | `0` |
| `size` | Số bản ghi tối đa trong một trang | `20` |
| `sort` | Thuộc tính và chiều sắp xếp | Không sắp xếp động |

Ví dụ lấy trang đầu, tối đa 10 người và sắp xếp theo họ tăng dần:

~~~http
GET /people?page=0&size=10&sort=lastName,asc
~~~

Sắp xếp theo nhiều thuộc tính bằng cách lặp lại tham số `sort`. Thứ tự các chỉ thị trong query string được giữ trong đối tượng sắp xếp:

~~~http
GET /people?page=0&size=10&sort=lastName,asc&sort=firstName,desc
~~~

Trong ví dụ trên, hệ thống sắp xếp theo `lastName` tăng dần; nếu nhiều bản ghi có cùng họ, tiếp tục sắp xếp theo `firstName` giảm dần.

Tên thuộc tính phải khớp với thuộc tính của mô hình miền mà Spring Data có thể truy vấn, không phải tên cột SQL tùy ý. Có thể dùng property path cho thuộc tính lồng nhau. Spring Data REST không hỗ trợ sắp xếp trực tiếp theo association được xuất bản thành liên kết tới tài nguyên cấp cao nhất.

Để kết quả giữa các trang ổn định khi nhiều bản ghi có cùng giá trị sắp xếp, nên thêm một thuộc tính phân biệt làm tiêu chí cuối, chẳng hạn:

~~~http
GET /people?page=0&size=10&sort=lastName,asc&sort=id,asc
~~~

## 5. Cấu hình kích thước trang và tên tham số

Giá trị mặc định là 20 bản ghi mỗi trang. Có thể thay đổi kích thước mặc định và giới hạn tối đa để tránh client yêu cầu một trang quá lớn. Có thể cấu hình bằng Spring Boot properties:

~~~properties
spring.data.rest.default-page-size=25
spring.data.rest.max-page-size=100
~~~

Nếu API cần tên tham số khác, có thể cấu hình thông qua `RepositoryRestConfigurer`:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);
        config.setPageParamName("p");
        config.setLimitParamName("limit");
        config.setSortParamName("order");
    }
}
~~~

Sau cấu hình này, client dùng `p`, `limit` và `order` thay cho `page`, `size` và `sort`. Tên tham số phải thống nhất giữa server và client.

## 6. Dấu hiệu trong phản hồi HAL

Một phản hồi phân trang thường chứa:

- `_embedded`: các phần tử thuộc trang hiện tại.
- `_links.self`: liên kết của trang hiện tại, thường là URI template cho các tham số tùy chọn.
- `_links.next` và `_links.prev`: liên kết tới trang kế tiếp hoặc trước đó khi tồn tại.
- `page`: thông tin kích thước trang, tổng số phần tử, tổng số trang và số trang hiện tại.

Ví dụ rút gọn:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people{&sort,page,size}",
      "templated": true
    },
    "next": {
      "href": "http://localhost:8080/people?page=1&size=10{&sort}",
      "templated": true
    }
  },
  "_embedded": {
    "people": []
  },
  "page": {
    "size": 10,
    "totalElements": 52,
    "totalPages": 6,
    "number": 0
  }
}
~~~

Số trang trong phản hồi cũng bắt đầu từ 0. Ở trang đầu không có liên kết `prev`; ở trang cuối không có liên kết `next`. Với `Page<T>`, phản hồi có thể cung cấp tổng số phần tử và tổng số trang. `Slice<T>` hữu ích khi chỉ cần biết còn trang tiếp theo hay không và không cần tính tổng số bản ghi.

## 7. Cách kiểm tra khi endpoint không nhận phân trang hoặc sắp xếp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Collection GET trả về toàn bộ dữ liệu, không có liên kết trang | Repository không có hoặc không export `findAll(Pageable)`; repository chỉ có `findAll()` hoặc chỉ có CRUD cơ bản. |
| Collection GET trả về `405 Method Not Allowed` | Không có phương thức `findAll(...)` phù hợp hoặc các phương thức đó bị tắt export. |
| Query method bỏ qua `page` và `size` | Phương thức chưa nhận `Pageable`, hoặc không trả về `Page<T>`/`Slice<T>`. |
| Query method không nhận tham số `sort` | Chữ ký phương thức không có `Pageable` hoặc `Sort`, hoặc phương thức không được export. |
| Sort báo lỗi thuộc tính | Tên thuộc tính không tồn tại trong mô hình miền, sai property path hoặc đang sắp xếp theo association được liên kết tới tài nguyên khác. |
| Client yêu cầu trang lớn nhưng server trả ít bản ghi hơn | Kiểm tra giới hạn `maxPageSize` và cấu hình kích thước trang. |

Khi chẩn đoán, hãy kiểm tra đúng repository interface và chữ ký phương thức mà Spring Data REST thực sự gọi. Đừng chỉ kiểm tra URL của client: tham số `page`, `size`, `sort` chỉ có tác dụng khi phương thức phía server có khả năng tiếp nhận và xử lý chúng.

## Ghi nhớ

Một collection resource hỗ trợ **phân trang** khi phương thức được export có khả năng nhận `Pageable`, điển hình là `findAll(Pageable)`. Nó hỗ trợ **sắp xếp** khi phương thức được gọi có khả năng nhận `Sort`, hoặc nhận `Pageable` chứa thông tin sắp xếp. Với query method riêng, cần khai báo `Pageable` và trả về `Page<T>` hoặc `Slice<T>` để Spring Data REST biểu diễn đúng kết quả phân trang. Repository phải được export và store implementation phải thực thi được các abstraction đó.

## Tài liệu tham khảo

- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/4.5/repository-resources.html)
- [Spring Data — Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
