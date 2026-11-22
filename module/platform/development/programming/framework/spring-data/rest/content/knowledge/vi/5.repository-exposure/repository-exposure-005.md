# Ẩn phương thức CRUD hoặc truy vấn bằng @RestResource(exported = false)

Spring Data REST có thể tự động xuất các phương thức của repository thành tài nguyên REST. Trong thực tế, repository thường có những phương thức chỉ dành cho xử lý nội bộ hoặc không nên trở thành một phần của API công khai. Có thể dùng **@RestResource(exported = false)** trên từng phương thức để yêu cầu Spring Data REST không xuất phương thức đó.

Cách này giúp giữ nguyên repository cho tầng service và các thành phần Java khác, đồng thời giới hạn những thao tác mà client có thể gọi qua Spring Data REST.

## 1. Cơ chế hoạt động

**@RestResource** thuộc package **org.springframework.data.rest.core.annotation**. Thuộc tính **exported** quyết định một phương thức hoặc tài nguyên có được Spring Data REST xuất ra HTTP hay không:

- Giá trị mặc định là **true**: phương thức đủ điều kiện sẽ được xuất theo quy tắc của Spring Data REST.
- Đặt **exported = false**: phương thức không được xuất thành endpoint REST.
- Phương thức vẫn tồn tại trong interface repository và vẫn có thể được gọi từ service hoặc code Java khác.

Ví dụ import:

~~~java
import org.springframework.data.rest.core.annotation.RestResource;
~~~

Đặt annotation trực tiếp trên khai báo phương thức trong interface repository đang được Spring Data REST quản lý.

## 2. Ẩn một phương thức truy vấn

Các phương thức truy vấn được khai báo theo quy ước tên của Spring Data, chẳng hạn **findByEmail** hoặc **findByStatus**, có thể được xuất dưới tài nguyên **search** của repository.

Nếu một truy vấn chỉ phục vụ nghiệp vụ nội bộ, hãy đánh dấu phương thức đó:

~~~java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "customers")
public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @RestResource(exported = false)
    Optional<Customer> findByEmail(String email);
}
~~~

Khi không có annotation ẩn, phương thức truy vấn thường có thể được gọi qua đường dẫn tương tự:

~~~http
GET /customers/search/findByEmail?email=alice@example.com
~~~

Sau khi đặt **@RestResource(exported = false)**, Spring Data REST không xuất endpoint truy vấn này và không đưa phương thức đó vào các liên kết tìm kiếm được công bố. Phương thức **findByEmail** vẫn có thể được gọi trong Java:

~~~java
Optional<Customer> customer = customerRepository.findByEmail(email);
~~~

Như vậy, tầng service vẫn dùng được truy vấn trong khi client REST không thể gọi trực tiếp endpoint do Spring Data REST tạo ra.

## 3. Ẩn phương thức CRUD kế thừa

Repository thường kế thừa các phương thức CRUD từ **CrudRepository**, **ListCrudRepository** hoặc **JpaRepository**. Khi muốn ẩn một phương thức kế thừa, hãy khai báo lại phương thức đó trong repository cụ thể và gắn **@RestResource(exported = false)**.

Ví dụ, ẩn thao tác xóa theo ID và thao tác tìm một bản ghi theo ID:

~~~java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "customers")
public interface CustomerRepository extends JpaRepository<Customer, Long> {

    @Override
    @RestResource(exported = false)
    void deleteById(Long id);

    @Override
    @RestResource(exported = false)
    Optional<Customer> findById(Long id);
}
~~~

Điểm cần nhớ:

1. Phải khai báo lại phương thức trong interface repository đang được Spring Data REST quét.
2. Chữ ký khai báo lại phải tương thích với phương thức kế thừa: tên, tham số và kiểu trả về phải đúng theo hợp đồng của interface cha.
3. Annotation chỉ áp dụng cho phương thức được đánh dấu. Các phương thức CRUD khác vẫn có thể được xuất.
4. Nếu muốn ẩn nhiều thao tác, hãy đánh dấu từng phương thức tương ứng. Ví dụ, ẩn **deleteById** không tự động ẩn mọi phương thức xóa khác như **delete**, **deleteAll** hoặc các phương thức xóa tùy chỉnh.

Các phương thức có thể khác nhau giữa các interface repository và phiên bản Spring Data. Hãy chọn đúng phương thức mà repository đang kế thừa và muốn ẩn.

## 4. Phân biệt ẩn một phương thức và ẩn cả repository

Có hai phạm vi cấu hình khác nhau:

| Annotation | Phạm vi | Mục đích |
|---|---|---|
| **@RestResource(exported = false)** | Một phương thức repository | Ẩn riêng endpoint tương ứng với phương thức |
| **@RepositoryRestResource(exported = false)** | Toàn bộ repository | Không xuất repository đó thành tài nguyên REST |

Ví dụ ẩn toàn bộ repository:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalCustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Chỉ dùng cấu hình cấp repository khi không muốn Spring Data REST công bố bất kỳ tài nguyên nào của repository đó. Nếu vẫn cần công bố các thao tác khác, hãy dùng cấu hình cấp phương thức.

## 5. Kiểm tra kết quả

Sau khi khởi động ứng dụng, kiểm tra các tài nguyên do Spring Data REST công bố. Nếu ứng dụng cấu hình base path, hãy thêm base path đó vào các URL bên dưới.

**Với phương thức truy vấn:**

1. Gọi tài nguyên collection, ví dụ **GET /customers**.
2. Kiểm tra tài nguyên **GET /customers/search**.
3. Xác nhận phương thức **findByEmail** không còn xuất hiện trong các liên kết tìm kiếm.
4. Thử gọi **GET /customers/search/findByEmail?email=alice@example.com**. Endpoint do Spring Data REST quản lý phải không còn được cung cấp; thông thường request sẽ nhận phản hồi 404.

**Với phương thức CRUD:**

1. Kiểm tra tài nguyên item và các thao tác CRUD đang được công bố.
2. Thử gọi endpoint tương ứng với phương thức đã ẩn, chẳng hạn thao tác xóa theo ID.
3. Xác nhận phương thức đã đánh dấu không còn được Spring Data REST cung cấp.
4. Nếu cần, kiểm tra riêng trong một service hoặc bài kiểm thử Java để xác nhận phương thức repository vẫn hoạt động khi được gọi nội bộ.

Kết quả HTTP cụ thể có thể chịu ảnh hưởng của cấu hình ứng dụng và các controller khác. Mục tiêu của phép kiểm tra là xác nhận Spring Data REST không còn xuất endpoint của phương thức được đánh dấu.

## 6. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Endpoint truy vấn vẫn xuất hiện | Annotation chưa đặt trên đúng phương thức trong repository được quản lý | Kiểm tra package import và vị trí annotation |
| Phương thức CRUD kế thừa vẫn được xuất | Chưa khai báo lại phương thức trong repository con hoặc chữ ký không khớp | Override đúng phương thức rồi đặt annotation trên khai báo đó |
| Một số thao tác vẫn gọi được | Chỉ một phương thức được ẩn, còn phương thức CRUD khác vẫn được xuất | Xác định và ẩn riêng từng phương thức cần loại khỏi API |
| URL vẫn hoạt động dù repository method đã bị ẩn | Có controller hoặc endpoint tùy chỉnh cung cấp cùng chức năng | Kiểm tra cấu hình controller và các đường dẫn REST tùy chỉnh |

Cần dùng đúng annotation **org.springframework.data.rest.core.annotation.RestResource**. Annotation cùng tên hoặc annotation của package khác không thay thế cấu hình của Spring Data REST.

## 7. Giới hạn và lưu ý bảo mật

**exported = false** điều khiển việc Spring Data REST xuất phương thức thành endpoint. Nó không xóa phương thức khỏi repository, không ngăn code Java gọi phương thức và không tự tạo quy tắc phân quyền cho ứng dụng.

Nếu chức năng vẫn được cung cấp qua controller tùy chỉnh hoặc một API khác, cần cấu hình bảo mật cho đường dẫn đó. Với các thao tác nhạy cảm, hãy dùng Spring Security và kiểm tra quyền ở tầng phù hợp; không nên xem việc ẩn endpoint là cơ chế phân quyền duy nhất.

Khi thiết kế API, nên chỉ xuất những thao tác client thực sự cần. Dùng **@RestResource(exported = false)** cho từng phương thức nội bộ giúp giữ repository phục vụ nghiệp vụ mà không công bố các endpoint không cần thiết.
