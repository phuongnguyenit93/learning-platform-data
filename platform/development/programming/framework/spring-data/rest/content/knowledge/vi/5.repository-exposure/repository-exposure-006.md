# Chọn phương thức công bố với Repository, CrudRepository và JpaRepository

Spring Data REST tạo REST API từ các repository của Spring Data. Interface mà repository kế thừa quyết định những thao tác dữ liệu có sẵn trong tầng repository; Spring Data REST dùng các thao tác đó để phục vụ tài nguyên collection, item và các truy vấn tìm kiếm. Vì vậy, chọn đúng interface giúp kiểm soát bề mặt API ngay từ đầu.

## 1. Ba interface khác nhau ở đâu?

| Interface | Phương thức được cung cấp | Khi nên chọn |
|---|---|---|
| Repository<T, ID> | Interface đánh dấu tối thiểu. Nó không tự cung cấp bộ CRUD; bạn khai báo các phương thức mà ứng dụng cần. | Khi muốn giới hạn API, chẳng hạn chỉ cho phép đọc hoặc chỉ công bố một vài truy vấn. |
| CrudRepository<T, ID> | Bộ thao tác CRUD tổng quát như save, saveAll, findById, findAll, existsById, count, deleteById, delete và deleteAll. | Khi tài nguyên cần các thao tác tạo, đọc, cập nhật và xóa thông dụng. |
| JpaRepository<T, ID> | Các thao tác CRUD cùng khả năng phân trang/sắp xếp và tiện ích riêng cho JPA, ví dụ flush, saveAndFlush, getReferenceById hoặc các thao tác xóa theo lô. Danh sách và kiểu trả về cụ thể phụ thuộc phiên bản Spring Data. | Khi dùng JPA và tầng nghiệp vụ cần các tiện ích bổ sung của JPA. |

Repository<T, ID> là lựa chọn tối giản. Nó cho phép bạn khai báo đúng những chữ ký phương thức mà repository cần. Ví dụ, một repository chỉ khai báo findById và findAll có thể phục vụ việc đọc mà không đưa save hoặc delete vào hợp đồng repository.

CrudRepository bổ sung hợp đồng CRUD tiêu chuẩn. Khi repository kế thừa interface này, Spring Data REST có đủ thao tác phổ biến để phục vụ các tài nguyên đọc và ghi.

JpaRepository thường phù hợp với ứng dụng dùng Spring Data JPA. Nó kế thừa các khả năng CRUD và phân trang/sắp xếp, đồng thời bổ sung các thao tác phục vụ EntityManager và cơ chế lưu trữ JPA. Chọn JpaRepository vì tầng nghiệp vụ cần các tiện ích này; việc dùng interface này không có nghĩa mỗi phương thức JPA sẽ trở thành một URL REST riêng.

## 2. Spring Data REST công bố tài nguyên như thế nào?

Spring Data REST tổ chức API quanh tài nguyên:

- **Collection resource** đại diện cho tập hợp entity, ví dụ /api/products.
- **Item resource** đại diện cho một entity, ví dụ /api/products/42.
- **Search resource** đại diện cho một phương thức truy vấn được công bố, ví dụ /api/products/search/by-category.

Với repository hỗ trợ CRUD, các thao tác HTTP thường có dạng:

| HTTP | Tài nguyên | Ý nghĩa |
|---|---|---|
| GET | /api/products | Lấy danh sách sản phẩm; phản hồi có thể chứa thông tin phân trang và liên kết điều hướng. |
| GET | /api/products/42 | Lấy sản phẩm có ID 42. |
| POST | /api/products | Tạo sản phẩm mới trong collection. |
| PUT | /api/products/42 | Thay thế dữ liệu của sản phẩm tại item resource. |
| PATCH | /api/products/42 | Cập nhật một phần dữ liệu của sản phẩm. |
| DELETE | /api/products/42 | Xóa sản phẩm tại item resource. |

Đây là cách nhìn theo tài nguyên và HTTP. Không nên hiểu rằng mỗi phương thức Java như save, findAll hoặc deleteById sẽ tạo một endpoint mang đúng tên phương thức đó. Spring Data REST ánh xạ thao tác repository vào collection và item resource theo quy ước REST.

Phương thức truy vấn tùy chỉnh được công bố dưới search resource. Ví dụ, phương thức findByCategory có thể được gọi qua một URL dạng /api/products/search/by-category?category=books. Tên đường dẫn và tên tham số có thể được tùy chỉnh bằng annotation.

## 3. Chỉ khai báo những phương thức cần thiết với Repository

Dùng Repository<T, ID> khi muốn tự xác định hợp đồng của repository thay vì kế thừa toàn bộ CRUD:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.Repository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.repository.query.Param;

@RepositoryRestResource(path = "products", collectionResourceRel = "products")
public interface ProductRepository extends Repository<Product, Long> {

    Optional<Product> findById(Long id);

    List<Product> findAll();

    @RestResource(path = "by-category", rel = "by-category")
    List<Product> findByCategoryIgnoreCase(@Param("category") String category);
}
~~~

Trong ví dụ này, repository khai báo hai phương thức đọc cơ bản và một truy vấn theo category. Nó không kế thừa save hoặc delete từ CrudRepository, vì vậy hợp đồng repository không cung cấp các thao tác ghi đó.

Truy vấn tùy chỉnh được công bố ở search resource với đường dẫn by-category. Tham số category xuất hiện trong query string. Dùng @Param tường minh giúp tên tham số API ổn định và dễ đọc.

Nếu tạo một interface cha tổng quát để nhiều repository cùng kế thừa, đánh dấu interface cha bằng @NoRepositoryBean để Spring Data không cố tạo repository độc lập cho kiểu tổng quát đó:

~~~java
@NoRepositoryBean
public interface ReadOnlyRepository<T, ID> extends Repository<T, ID> {
    Optional<T> findById(ID id);
    List<T> findAll();
}
~~~

Sau đó, repository cụ thể có thể kế thừa ReadOnlyRepository<Product, Long> và khai báo thêm các truy vấn riêng.

## 4. Dùng CrudRepository cho CRUD thông dụng

Khi tài nguyên cần các thao tác tạo, đọc, cập nhật và xóa thông thường, CrudRepository là lựa chọn rõ ràng:

~~~java
import java.util.List;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.repository.query.Param;

@RepositoryRestResource(path = "products", collectionResourceRel = "products")
public interface ProductRepository extends CrudRepository<Product, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    List<Product> findByNameContainingIgnoreCase(@Param("name") String name);

    @Override
    @RestResource(exported = false)
    void deleteById(Long id);
}
~~~

Repository kế thừa bộ CRUD chuẩn. Truy vấn theo tên được công bố dưới search resource; thao tác deleteById được ẩn khỏi REST API bằng exported = false. Phương thức Java vẫn thuộc hợp đồng repository và có thể được tầng ứng dụng sử dụng.

Ví dụ, search resource có thể được gọi như sau:

~~~http
GET /api/products/search/by-name?name=keyboard
~~~

Nếu muốn ẩn toàn bộ repository khỏi Spring Data REST, đặt exported = false ở cấp repository:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalProductRepository extends CrudRepository<Product, Long> {
}
~~~

Khi đó repository vẫn có thể được inject và sử dụng trong ứng dụng, nhưng Spring Data REST không công bố tài nguyên của nó.

## 5. Dùng JpaRepository trong ứng dụng JPA

Với ứng dụng dùng JPA, JpaRepository cung cấp bộ thao tác repository phong phú hơn:

~~~java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.repository.query.Param;

@RepositoryRestResource(path = "products", collectionResourceRel = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {

    @RestResource(path = "active", rel = "active")
    List<Product> findByActiveTrue();

    @RestResource(path = "by-category", rel = "by-category")
    List<Product> findByCategoryIgnoreCase(@Param("category") String category);
}
~~~

Spring Data REST có thể công bố các truy vấn tùy chỉnh như active và by-category dưới search resource. Các thao tác JPA như flush, saveAndFlush hoặc deleteAllInBatch phục vụ tầng persistence; đừng mặc định rằng chúng tạo endpoint REST riêng. API REST vẫn được tổ chức theo tài nguyên và các quy ước HTTP.

Nếu ứng dụng chỉ cần CRUD cơ bản, CrudRepository thường diễn đạt đúng nhu cầu hơn. Nếu ứng dụng thực sự dùng các tiện ích của JPA, JpaRepository là lựa chọn phù hợp. Với phiên bản Spring Data mới, một số interface phân trang và CRUD đã được tách hoặc bổ sung kiểu trả về List; hãy đối chiếu API với phiên bản dependency đang dùng khi khai báo kiểu repository.

## 6. Kiểm soát tên và phạm vi công bố

Có hai cấp kiểm soát chính:

**Cấp repository — @RepositoryRestResource**

- path đặt đường dẫn collection resource.
- collectionResourceRel đặt tên quan hệ trong HAL response.
- exported = false ẩn toàn bộ repository khỏi Spring Data REST.

**Cấp phương thức — @RestResource**

- path đặt đường dẫn cho search resource.
- rel đặt tên quan hệ trong response.
- exported = false ẩn phương thức khỏi REST API.

Ví dụ đổi đường dẫn truy vấn:

~~~java
@RestResource(path = "recent", rel = "recent")
List<Product> findTop10ByOrderByCreatedAtDesc();
~~~

Search resource tương ứng có đường dẫn dạng /api/products/search/recent.

Để ẩn một phương thức kế thừa, có thể override phương thức đó trong repository cụ thể và gắn @RestResource(exported = false), như ví dụ deleteById ở trên. Cách này điều khiển việc công bố qua Spring Data REST; nó không thay thế phân quyền truy cập của ứng dụng.

## 7. Chọn interface theo nhu cầu

- **Chỉ muốn công bố một tập phương thức nhỏ:** kế thừa Repository<T, ID>, sau đó khai báo rõ các phương thức đọc hoặc truy vấn cần dùng.
- **Muốn API CRUD tiêu chuẩn:** kế thừa CrudRepository<T, ID>.
- **Dùng JPA và cần tiện ích persistence bổ sung:** kế thừa JpaRepository<T, ID>.
- **Muốn giữ repository cho nội bộ:** dùng @RepositoryRestResource(exported = false).
- **Muốn ẩn một thao tác cụ thể:** dùng @RestResource(exported = false) trên phương thức.

Đừng chọn JpaRepository chỉ vì nó có nhiều phương thức hơn. Mỗi repository được công bố là một phần hợp đồng API mà client có thể khám phá và gọi. Hãy bắt đầu từ các thao tác nghiệp vụ mà client thực sự cần, sau đó chọn interface và annotation phù hợp.

## 8. Các lỗi dễ gặp

1. **Cho rằng tên phương thức CRUD là URL.** Spring Data REST công bố collection/item resource theo quy ước; chỉ các truy vấn phù hợp mới xuất hiện dưới search resource.
2. **Kế thừa interface quá rộng.** Một repository kế thừa CrudRepository hoặc JpaRepository sẽ có hợp đồng thao tác rộng hơn một repository chỉ kế thừa Repository.
3. **Quên ẩn phương thức nhạy cảm.** Dùng exported = false ở cấp repository hoặc phương thức nếu không muốn công bố thao tác đó.
4. **Không đặt tên đường dẫn truy vấn rõ ràng.** Dùng path, rel và @Param để API dễ đọc, ổn định.
5. **Coi việc ẩn endpoint là phân quyền.** exported = false điều khiển việc Spring Data REST công bố tài nguyên; quyền truy cập vẫn cần được cấu hình bằng cơ chế bảo mật của ứng dụng.
6. **Nhầm tiện ích JPA với endpoint REST.** Các phương thức như flush hoặc thao tác xóa theo lô phục vụ tầng persistence, không mặc nhiên tạo URL riêng.

## 9. Cách kiểm tra API sau khi cấu hình

1. Khởi động ứng dụng có Spring Data REST và repository được cấu hình.
2. Mở endpoint gốc, ví dụ /api, để xem các liên kết tài nguyên mà Spring Data REST công bố.
3. Mở collection resource, ví dụ /api/products, rồi thử GET và các thao tác ghi mà repository được phép hỗ trợ.
4. Mở /api/products/search để xem các truy vấn được công bố.
5. Gọi thử một truy vấn tùy chỉnh, ví dụ /api/products/search/by-category?category=books.
6. Kiểm tra repository hoặc phương thức có exported = false không xuất hiện trong API.

Khi API có nhiều client, nên ghi lại rõ repository nào được công bố, các thao tác HTTP được hỗ trợ và các truy vấn tìm kiếm đang cung cấp. Điều này giúp thay đổi interface repository có chủ đích, vì thay đổi interface có thể làm thay đổi hợp đồng REST mà client đang sử dụng.

