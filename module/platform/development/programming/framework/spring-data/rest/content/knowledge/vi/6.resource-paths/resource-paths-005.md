# Tùy chỉnh đường dẫn và rel của phương thức tìm kiếm trong Spring Data REST

Spring Data REST có thể tự động công bố các query method của repository dưới tài nguyên tìm kiếm \`/search\`. Mỗi phương thức được công bố sẽ xuất hiện dưới dạng một liên kết để client khám phá và gọi API. Khi tên URL hoặc tên quan hệ liên kết mặc định chưa phù hợp với thiết kế API, có thể dùng annotation **\`@RestResource\`** để tùy chỉnh riêng từng query method.

Hai thuộc tính cần phân biệt:

- **\`path\`** quyết định đoạn đường dẫn URL mà client gọi.
- **\`rel\`** quyết định tên quan hệ liên kết (link relation) được công bố trong tài liệu HAL để client nhận diện liên kết đó.

Việc thay đổi \`path\` và \`rel\` không thay đổi điều kiện truy vấn do tên phương thức hoặc \`@Query\` xác định. Chúng điều khiển cách Spring Data REST công bố và định danh endpoint.

## 1. Vị trí của query method trong Spring Data REST

Giả sử ứng dụng có repository:

~~~java
public interface PersonRepository extends CrudRepository<Person, Long> {

    List<Person> findByLastName(String lastName);
}
~~~

Khi query method được export, Spring Data REST đặt các phương thức tìm kiếm dưới tài nguyên \`search\` của collection resource. Nếu collection resource có đường dẫn \`/people\`, client khám phá các phương thức tìm kiếm tại:

~~~http
GET /people/search
~~~

Tài nguyên này trả về các liên kết đến những query method đã được export. Client theo liên kết tương ứng để gọi phương thức tìm kiếm. Ví dụ, phương thức \`findByLastName\` nhận một tham số có thể được gọi bằng query parameter:

~~~http
GET /people/search/findByLastName?lastName=Nguyen
~~~

Tên đường dẫn mặc định được tạo từ metadata của query method. Nếu muốn URL ổn định, ngắn gọn và có ý nghĩa rõ với client, hãy khai báo \`path\` tường minh bằng \`@RestResource\`.

## 2. Tùy chỉnh path và rel bằng @RestResource

Đặt \`@RestResource\` trực tiếp trên query method:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RestResource;

import java.util.List;

public interface PersonRepository extends CrudRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findByLastName(@Param("lastName") String lastName);
}
~~~

Với repository được công bố tại \`/people\`, endpoint tìm kiếm có đường dẫn:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
~~~

Trong ví dụ:

- \`path = "by-last-name"\` tạo đoạn URL \`by-last-name\` phía sau \`/people/search\`.
- \`rel = "byLastName"\` đặt tên quan hệ liên kết mà client nhìn thấy trong HAL.
- \`@Param("lastName")\` xác định tên query parameter trong URL. Tên này phải tương ứng với tham số mà query method nhận.
- \`findByLastName\` vẫn là derived query của Spring Data. Annotation chỉ thay đổi metadata công bố REST, không đổi ý nghĩa truy vấn.

### Path và rel có nhiệm vụ khác nhau

| Thuộc tính | Tác dụng | Ví dụ |
|---|---|---|
| \`path\` | Đoạn URL của endpoint | \`by-last-name\` |
| \`rel\` | Tên liên kết trong HAL | \`byLastName\` |
| \`@Param\` | Tên query parameter | \`lastName\` |

Vì vậy, client gọi URL bằng \`path\`, còn client đọc tài liệu HAL dựa vào \`rel\`. Hai giá trị có thể giống nhau, nhưng không bắt buộc phải giống.

## 3. Client khám phá liên kết tìm kiếm

Khi client yêu cầu:

~~~http
GET /people/search
Accept: application/hal+json
~~~

Spring Data REST trả về tài nguyên tìm kiếm với các liên kết tới query method được công bố. Sau khi cấu hình annotation ở ví dụ trên, một phần HAL minh họa có thể có dạng:

~~~json
{
  "_links": {
    "byLastName": {
      "href": "http://localhost:8080/people/search/by-last-name{?lastName}",
      "templated": true
    }
  }
}
~~~

Đây là ví dụ rút gọn để minh họa cách dùng \`rel\` và \`path\`; phản hồi thực tế có thể chứa thêm liên kết và metadata.

Client thực hiện theo hai bước:

1. Đọc liên kết có relation \`byLastName\` từ tài nguyên \`/people/search\`.
2. Điền giá trị cho biến URI template \`lastName\`, rồi gọi endpoint tìm kiếm.

Ví dụ request sau khi điền tham số:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
Accept: application/hal+json
~~~

Cách khám phá qua liên kết giúp client không phải tự ghép URL từ tên repository hoặc tên phương thức Java. Nếu sau này đường dẫn thay đổi nhưng relation được giữ ổn định, client có thể tiếp tục tìm liên kết qua cùng relation.

## 4. Chỉ tùy chỉnh một trong hai thuộc tính

Có thể dùng \`path\` và \`rel\` độc lập tùy nhu cầu. Ví dụ:

~~~java
@RestResource(path = "by-city")
List<Person> findByCity(@Param("city") String city);
~~~

Ví dụ này chỉ đặt đường dẫn tường minh; relation được framework xác định theo metadata mặc định của query method.

Hoặc:

~~~java
@RestResource(rel = "peopleInCity")
List<Person> findByCity(@Param("city") String city);
~~~

Ví dụ này tùy chỉnh tên relation trong HAL; đường dẫn vẫn theo mapping mặc định của query method.

Trong API được sử dụng bởi nhiều client, nên cân nhắc đặt cả hai giá trị rõ ràng để kiểm soát URL và hợp đồng liên kết. Dùng chữ thường và dấu gạch nối cho path thường giúp URL dễ đọc; dùng relation ngắn, có ý nghĩa và ổn định để client dễ khám phá.

## 5. Kết hợp với @RepositoryRestResource

\`@RestResource\` tùy chỉnh một phương thức repository. Ở cấp repository, \`@RepositoryRestResource\` cho phép tùy chỉnh đường dẫn và các relation của collection resource, item resource.

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

import java.util.List;

@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people",
    itemResourceRel = "person"
)
public interface PersonRepository extends CrudRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findByLastName(@Param("lastName") String lastName);
}
~~~

Trong ví dụ này:

- \`path = "people"\` tùy chỉnh đường dẫn collection resource.
- \`collectionResourceRel = "people"\` đặt relation cho collection.
- \`itemResourceRel = "person"\` đặt relation cho tài nguyên item.
- \`@RestResource\` trên \`findByLastName\` tùy chỉnh endpoint tìm kiếm cụ thể.

Endpoint tìm kiếm vẫn nằm dưới search resource của repository:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
~~~

Không nhầm \`collectionResourceRel\` với \`rel\` của query method: thuộc tính thứ nhất đặt relation cho collection resource, còn thuộc tính thứ hai đặt relation cho liên kết tìm kiếm.

## 6. Ẩn một query method khỏi REST API

Nếu một query method chỉ phục vụ nội bộ và không nên được client gọi qua Spring Data REST, có thể tắt export ngay trên phương thức:

~~~java
@RestResource(exported = false)
List<Person> findByInternalCode(String code);
~~~

Khi đó phương thức này không được công bố như một search endpoint. Ứng dụng vẫn có thể sử dụng phương thức qua repository trong mã Java nếu nó được triển khai và gọi theo cách phù hợp.

Ở cấp repository, \`@RepositoryRestResource(exported = false)\` có thể được dùng để không công bố repository đó qua Spring Data REST. Cần chọn đúng phạm vi: ẩn một query method hay ẩn cả repository.

## 7. Tham số tìm kiếm và kiểu kết quả

\`@RestResource\` không thay thế khai báo tham số hoặc kiểu trả về của query method.

Ví dụ với nhiều tham số:

~~~java
@RestResource(path = "by-name-and-city", rel = "byNameAndCity")
List<Person> findByFirstNameAndCity(
    @Param("firstName") String firstName,
    @Param("city") String city
);
~~~

Client gọi:

~~~http
GET /people/search/by-name-and-city?firstName=An&city=Hanoi
~~~

Với mỗi tham số, dùng \`@Param\` để đặt tên rõ ràng trong URL template. Điều này đặc biệt hữu ích khi tên tham số Java được đổi hoặc khi muốn giữ hợp đồng API nhất quán.

Query method cũng có thể dùng kiểu kết quả phù hợp với nhu cầu, chẳng hạn \`List<Person>\`, \`Collection<Person>\` hoặc kiểu hỗ trợ phân trang như \`Page<Person>\` khi module và cấu hình tương ứng hỗ trợ. Nếu phương thức nhận \`Pageable\` hoặc \`Sort\`, client có thể truyền thông tin phân trang/sắp xếp theo quy ước của Spring Data REST.

## 8. Lưu ý khi thiết kế path và rel

- **Giữ path duy nhất trong cùng search resource.** Hai query method không nên cùng công bố một đường dẫn vì client sẽ không thể phân biệt endpoint một cách rõ ràng và mapping có thể xung đột.
- **Giữ rel có ý nghĩa và ổn định.** Client HAL thường dùng relation để tìm chức năng, do đó tránh đổi rel tùy tiện khi chỉ đổi tên method Java.
- **Không trộn tên tham số với path.** Path xác định endpoint; \`@Param\` xác định query parameter được truyền vào endpoint.
- **Kiểm tra cả search resource lẫn endpoint.** Mở \`/people/search\` để xác nhận relation được công bố, sau đó gọi URL của endpoint với các query parameter thực tế.
- **Kiểm tra export.** Query method phải được export và repository phải được Spring Data REST công bố thì client mới khám phá được liên kết.
- **Chú ý thay đổi hợp đồng API.** Đổi path có thể làm hỏng client đang gọi URL cũ; đổi rel có thể làm client dựa vào relation cũ không còn tìm thấy liên kết.

## 9. Quy trình kiểm tra sau khi tùy chỉnh

1. Khởi động ứng dụng và xác nhận repository được Spring Data REST nhận diện.
2. Gửi request đến collection resource, ví dụ \`GET /people\`, để xác định đường dẫn gốc.
3. Gửi \`GET /people/search\` và kiểm tra liên kết có relation mong muốn.
4. Mở URI template trong liên kết, truyền đầy đủ các tham số được khai báo bằng \`@Param\`, rồi gọi endpoint.
5. Kiểm tra kết quả truy vấn, mã HTTP và nội dung phản hồi.
6. Nếu endpoint không xuất hiện, kiểm tra \`exported\`, cấu hình repository REST, tên path và việc query method có được nhận diện hay không.

## 10. Những điểm cần ghi nhớ

- Query method của Spring Data REST được khám phá qua search resource \`/search\` của repository.
- Dùng \`@RestResource(path = "...", rel = "...")\` trên phương thức để điều khiển URL và relation của liên kết tìm kiếm.
- \`path\` là đoạn đường dẫn endpoint; \`rel\` là tên liên kết trong HAL; \`@Param\` là tên query parameter.
- Dùng \`@RepositoryRestResource\` để tùy chỉnh path và relation ở cấp collection/item resource.
- Dùng \`exported = false\` để ẩn phương thức hoặc repository khỏi REST API tùy vị trí đặt annotation.
- Sau khi thay đổi, kiểm tra cả liên kết được công bố ở \`/search\` và request thực tế tới endpoint.
