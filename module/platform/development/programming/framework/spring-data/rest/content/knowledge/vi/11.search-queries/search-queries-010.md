# Giới hạn của lọc tự động từ query parameter và lựa chọn truy vấn tường minh

Spring Data REST cung cấp hai cách phổ biến để lọc dữ liệu khi đọc collection resource:

1. **Lọc động theo thuộc tính bằng Querydsl**: client truyền tên thuộc tính và giá trị trong query string; Spring Data REST chuyển các tham số đó thành predicate nếu repository hỗ trợ Querydsl.
2. **Chọn truy vấn tường minh qua search resource**: repository khai báo từng query method; client gọi đúng method đã được công bố và truyền các tham số mà method nhận.

Hai cách này giải quyết những nhu cầu khác nhau. Lọc động phù hợp với các điều kiện đơn giản trên thuộc tính được cho phép. Query method tường minh phù hợp khi nghiệp vụ cần một truy vấn có tên, điều kiện và contract ổn định. Không nên giả định rằng mọi query parameter bất kỳ đều tự động trở thành điều kiện lọc.

## 1. Query parameter mặc định của collection resource

Một collection resource Spring Data REST thường được truy cập bằng:

~~~http
GET /products
Accept: application/hal+json
~~~

Nếu repository hỗ trợ phân trang, collection resource nhận các tham số chuẩn:

| Tham số | Ý nghĩa |
|---|---|
| **`page`** | Số trang, bắt đầu từ 0 |
| **`size`** | Số phần tử trong một trang |
| **`sort`** | Thuộc tính và chiều sắp xếp, ví dụ **`name,asc`** |

Ví dụ:

~~~http
GET /products?page=0&size=10&sort=name,asc
~~~

Các tham số trên điều khiển phân trang và sắp xếp. Chúng không tự động lọc theo mọi thuộc tính của entity. Nếu gửi **`?status=ACTIVE`** tới collection resource nhưng repository không bật cơ chế lọc tương ứng, không nên mong Spring Data REST tự suy ra điều kiện **`status = ACTIVE`**.

Để lọc collection bằng các thuộc tính trong query string, repository có thể tích hợp Querydsl.

## 2. Lọc động theo thuộc tính với Querydsl

Querydsl cho phép Spring Data REST tạo predicate từ các query parameter và dùng predicate đó khi đọc collection resource.

Repository cần triển khai **`QuerydslPredicateExecutor<T>`**. Ví dụ:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface ProductRepository
        extends JpaRepository<Product, Long>,
                QuerydslPredicateExecutor<Product> {
}
~~~

Cần thêm dependency Querydsl tương thích với phiên bản Spring Data đang dùng và cấu hình annotation processing để sinh các lớp Q, ví dụ **`QProduct`**. Tên và cấu hình dependency có thể khác theo phiên bản Querydsl và persistence module.

Sau khi tích hợp, client có thể lọc trực tiếp trên collection:

~~~http
GET /products?name=Keyboard&status=ACTIVE
~~~

Các điều kiện thuộc tính được kết hợp thành predicate. Ví dụ trên tương đương ý tưởng:

~~~text
name = "Keyboard" AND status = "ACTIVE"
~~~

Có thể kết hợp lọc với phân trang và sắp xếp:

~~~http
GET /products?status=ACTIVE&category=OFFICE&page=0&size=10&sort=name,asc
~~~

Với các thuộc tính lồng nhau, có thể dùng property path theo cú pháp được binder hỗ trợ, ví dụ:

~~~http
GET /stores?address.city=York
~~~

Querydsl là cơ chế xây dựng predicate có kiểu dữ liệu, không phải bộ phân tích một ngôn ngữ truy vấn SQL tùy ý do client gửi lên.

## 3. Quy tắc binding mặc định và giới hạn

Querydsl binder có các quy tắc mặc định thường gặp:

| Loại thuộc tính | Cách binding mặc định |
|---|---|
| Thuộc tính đơn giản | So sánh bằng (**`eq`**) |
| Thuộc tính dạng collection | Kiểm tra phần tử chứa giá trị (**`contains`**) |
| Nhiều giá trị cho thuộc tính đơn giản | So sánh thuộc tập giá trị (**`in`**) |

Ví dụ query string có hai thuộc tính đơn giản:

~~~http
GET /users?firstname=Dave&lastname=Matthews
~~~

Predicate được tạo theo dạng:

~~~text
firstname = "Dave" AND lastname = "Matthews"
~~~

Một số giới hạn cần hiểu:

- Giá trị phải chuyển đổi được sang kiểu Java tương ứng. Giá trị ngày, số, enum hoặc ID sai định dạng có thể khiến request bị từ chối.
- Tên tham số gắn với property path mà binder cho phép; đây không phải tên tham số tùy ý cho một câu SQL.
- Các điều kiện query parameter mặc định không cung cấp đầy đủ cú pháp cho mọi phép so sánh, biểu thức OR lồng nhau, nhóm điều kiện, phép tổng hợp hoặc truy vấn nghiệp vụ phức tạp.
- Việc lọc theo association hoặc property lồng nhau phụ thuộc khả năng binding, model và persistence module.
- Không nên công khai mọi thuộc tính chỉ vì Querydsl có thể tạo predicate cho chúng. Thuộc tính nội bộ hoặc nhạy cảm cần được loại khỏi binding.
- Lọc động không thay thế phân quyền. Client không được phép tự quyết định phạm vi tenant, chủ sở hữu hoặc dữ liệu mà người dùng có quyền xem.

Nếu cần các phép so sánh đặc biệt hoặc quy tắc tìm kiếm khác mặc định, hãy tùy chỉnh binding hoặc chuyển sang truy vấn được khai báo rõ ràng.

## 4. Tùy chỉnh Querydsl binding

Có thể triển khai **`QuerydslBinderCustomizer`** trên repository để thay đổi cách query parameter được chuyển thành predicate.

Ví dụ, tìm tên sản phẩm theo kiểu chứa chuỗi, không phân biệt chữ hoa chữ thường, đồng thời không cho client lọc theo mã nội bộ:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;

public interface ProductRepository
        extends JpaRepository<Product, Long>,
                QuerydslPredicateExecutor<Product>,
                QuerydslBinderCustomizer<QProduct> {

    @Override
    default void customize(QuerydslBindings bindings, QProduct product) {
        bindings.bind(product.name)
                .first((path, value) -> path.containsIgnoreCase(value));

        bindings.excluding(product.internalCode);
    }
}
~~~

Trong ví dụ:

- **`name`** dùng phép tìm chuỗi chứa và không phân biệt hoa thường.
- **`internalCode`** không được dùng làm query parameter để tạo predicate.
- Các binding khác vẫn theo quy tắc mặc định nếu chưa được tùy chỉnh.

Có thể tùy chỉnh thêm binding theo từng thuộc tính hoặc theo kiểu dữ liệu. Nên ưu tiên allow-list những trường thực sự cần tìm kiếm khi API có yêu cầu bảo mật hoặc giới hạn truy vấn.

Việc loại một thuộc tính khỏi Querydsl binding chỉ ngăn client dùng thuộc tính đó làm điều kiện lọc qua cơ chế này. Nó không thay thế cấu hình bảo mật cho dữ liệu được trả về.

## 5. Chọn truy vấn tường minh qua search resource

Khi không muốn client tự chọn property path, repository có thể định nghĩa các query method cụ thể. Spring Data REST công bố các method đủ điều kiện dưới tài nguyên **`search`**.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends CrudRepository<Person, Long> {

    List<Person> findByLastname(@Param("name") String lastname);
}
~~~

Spring Data REST tạo search resource tại:

~~~http
GET /people/search
Accept: application/hal+json
~~~

Search resource trả về các liên kết tới query method đã được công bố. Method trên có thể được gọi bằng:

~~~http
GET /people/search/findByLastname?name=Baggins
~~~

Tên query parameter **`name`** lấy từ **`@Param("name")`**. Có thể tùy chỉnh path và rel của query method bằng **`@RestResource`**:

~~~java
@RestResource(path = "by-lastname", rel = "by-lastname")
List<Person> findByLastname(@Param("name") String lastname);
~~~

Khi đó client gọi:

~~~http
GET /people/search/by-lastname?name=Baggins
~~~

Dùng liên kết được trả về từ **`/people/search`** để khám phá endpoint thay vì bắt client tự đoán tên method hoặc URL.

## 6. Dùng @Query khi cần điều kiện nghiệp vụ rõ ràng

Tên method dẫn xuất phù hợp với các điều kiện đơn giản như **`findByStatus`**, **`findByLastnameAndActiveTrue`** hoặc **`findByPriceGreaterThan`**. Khi tên method quá dài hoặc điều kiện khó diễn đạt bằng quy ước tên, có thể khai báo JPQL bằng **`@Query`**.

Ví dụ, chỉ tìm người đang hoạt động tại một thành phố và có tuổi tối thiểu:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RestResource;

public interface PersonRepository extends JpaRepository<Person, Long> {

    @Query("select p from Person p " +
           "where p.active = true " +
           "and p.city = :city " +
           "and p.age >= :minAge")
    @RestResource(path = "active-by-city")
    Page<Person> findActiveByCityAndMinimumAge(
            @Param("city") String city,
            @Param("minAge") int minAge,
            Pageable pageable);
}
~~~

Client gọi query method đã chọn:

~~~http
GET /people/search/active-by-city?city=Da%20Nang&minAge=18&page=0&size=20
~~~

Điều kiện truy vấn do repository định nghĩa. Client chỉ truyền giá trị cho các tham số đã khai báo. Với kết quả **`Page`** và tham số **`Pageable`**, response có thể chứa metadata và các liên kết phân trang.

Các query method resource là tài nguyên chỉ đọc và được gọi bằng GET. Nếu một query method nội bộ không nên xuất thành API, có thể dùng **`@RestResource(exported = false)`** trên method đó.

## 7. Lựa chọn giữa lọc động và truy vấn tường minh

| Nhu cầu | Cách phù hợp |
|---|---|
| Lọc collection theo một vài thuộc tính đơn giản | Querydsl property binding |
| Cho phép kết hợp nhiều bộ lọc độc lập | Querydsl với binding được kiểm soát |
| Tìm theo một quy tắc nghiệp vụ có tên rõ ràng | Query method tường minh |
| Dùng phép join, điều kiện hoặc biểu thức phức tạp | **`@Query`** hoặc custom query |
| Muốn client chỉ được chọn trong một tập truy vấn đã định nghĩa | Search resource |
| Cần logic động vượt quá khả năng binder | Custom controller/service dùng Specification, Criteria hoặc Querydsl |

Lọc động giảm số lượng method phải khai báo, nhưng phạm vi truy vấn phụ thuộc các property path và binding được công khai. Query method tường minh cần khai báo nhiều method hơn, đổi lại mỗi endpoint có contract cụ thể, dễ mô tả và kiểm soát.

Hai cách có thể cùng tồn tại trên một repository. Ví dụ collection resource hỗ trợ lọc động cho các trường an toàn, trong khi **`/people/search`** công bố những truy vấn nghiệp vụ quan trọng.

## 8. Khi nào nên xây dựng endpoint tìm kiếm riêng?

Hãy cân nhắc custom controller hoặc service nếu truy vấn cần:

- Kết hợp nhiều nhóm điều kiện AND/OR có ngoặc và ưu tiên phức tạp.
- Điều kiện tùy chọn với quy tắc null, khoảng giá trị hoặc nhiều phép so sánh khác nhau.
- Join nhiều aggregate, truy vấn thống kê, tổng hợp hoặc kết quả không khớp trực tiếp với entity.
- Kiểm soát chặt chẽ các trường được phép lọc theo vai trò, tenant hoặc chính sách dữ liệu.
- Một contract tìm kiếm ổn định mà không muốn phụ thuộc cấu trúc entity và tên property.

Với Spring MVC controller riêng, có thể dùng **`@QuerydslPredicate`** để chuyển query parameter thành Querydsl Predicate và thực thi qua **`QuerydslPredicateExecutor`**. Đây là cách tích hợp web support cho controller; nó cần được khai báo trên tham số controller và không có nghĩa mọi controller hay mọi query parameter đều tự động được lọc.

## 9. Kiểm tra endpoint tìm kiếm

Sau khi cấu hình, kiểm tra từng cơ chế độc lập.

**Kiểm tra lọc động:**

~~~http
GET /products?name=key&status=ACTIVE&page=0&size=10
Accept: application/hal+json
~~~

Xác nhận chỉ các sản phẩm thỏa binding được cấu hình xuất hiện, đồng thời kiểm tra metadata phân trang.

**Kiểm tra search resource:**

~~~http
GET /people/search
Accept: application/hal+json
~~~

Xác nhận liên kết tới các query method được công bố.

**Kiểm tra query method cụ thể:**

~~~http
GET /people/search/active-by-city?city=Da%20Nang&minAge=18
Accept: application/hal+json
~~~

Đối chiếu kết quả với điều kiện JPQL đã khai báo. Thử giá trị không hợp lệ, tham số bị thiếu và trang tiếp theo để hiểu contract thực tế của endpoint.

## 10. Lưu ý bảo mật và vận hành

- Chỉ cho phép lọc theo những thuộc tính cần thiết; loại các trường nhạy cảm khỏi binding.
- Không xem query parameter là cơ chế phân quyền. Luôn áp dụng authorization và giới hạn dữ liệu ở phía server.
- Giới hạn kích thước trang và cân nhắc index database cho các trường thường xuyên lọc hoặc sắp xếp.
- Tránh công khai những phép lọc có thể tạo truy vấn quá tốn kém hoặc làm lộ thông tin qua kết quả.
- Kiểm tra khả năng chuyển đổi kiểu dữ liệu và cách binder xử lý giá trị lặp, property lồng nhau, null và chuỗi rỗng.
- Dùng HAL để khám phá search resource và các URI template do server công bố.
- Cấu hình Querydsl và annotation processing phải tương thích với phiên bản Spring Data, Querydsl và persistence provider của ứng dụng.

Tài liệu tham khảo chính thức:

- [Spring Data REST — Repository resources and search resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Project features, including dynamic filtering](https://spring.io/projects/spring-data-rest/)
- [Spring Data JPA — Querydsl extension and web support](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html)
- [Spring Guide — Accessing JPA Data with REST](https://spring.io/guides/gs/accessing-data-rest)
