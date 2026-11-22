# Lựa chọn interface theo phiên bản và nhu cầu của ứng dụng trong Spring Data JPA

Spring Data JPA cung cấp nhiều interface repository có phần chức năng giao nhau. Chọn đúng interface giúp repository chỉ cung cấp những khả năng ứng dụng cần, đồng thời tránh lỗi tương thích khi nâng cấp Spring Data. Với ứng dụng JPA thông thường, `JpaRepository` là lựa chọn thuận tiện; khi cần giới hạn API, tối ưu truy vấn hoặc hỗ trợ truy vấn động, có thể kết hợp `Repository`, `CrudRepository`, `PagingAndSortingRepository`, `JpaSpecificationExecutor` và các interface liên quan.

Bài này tập trung vào repository đồng bộ của Spring Data JPA. JPA là công nghệ truy cập dữ liệu blocking; các interface reactive như `ReactiveCrudRepository` thường dành cho module reactive khác, chẳng hạn Spring Data MongoDB Reactive hoặc R2DBC.

## 1. Hiểu cấu trúc các interface repository

Các interface được xây dựng theo những lớp chức năng. Không phải interface nào cũng là một bản thay thế trực tiếp cho interface khác.

| Interface | Vai trò | Khi nào nên dùng |
|---|---|---|
| `Repository<T, ID>` | Interface gốc, đánh dấu domain type và kiểu ID; không cung cấp CRUD sẵn | Muốn tự khai báo chính xác các phương thức repository cần công khai |
| `CrudRepository<T, ID>` | Các thao tác CRUD cơ bản | Cần lưu, đọc, đếm và xóa dữ liệu |
| `ListCrudRepository<T, ID>` | Mở rộng CRUD với các phương thức trả về `List` | Dùng Spring Data 3.x+ và muốn làm việc với danh sách có kiểu cụ thể |
| `PagingAndSortingRepository<T, ID>` | Đọc dữ liệu theo trang hoặc thứ tự sắp xếp | Cần `Pageable` hoặc `Sort` |
| `ListPagingAndSortingRepository<T, ID>` | Biến thể trả về `List` cho truy vấn sắp xếp | Cần kết quả `List` khi sắp xếp, không cần metadata của `Page` |
| `JpaRepository<T, ID>` | Tập hợp CRUD, phân trang/sắp xếp, Query by Example và thao tác đặc thù JPA | Repository JPA thông thường cần bộ tính năng đầy đủ |
| `JpaSpecificationExecutor<T>` | Thực thi truy vấn dựa trên `Specification` | Bộ lọc động, nhiều điều kiện tùy chọn |
| `QueryByExampleExecutor<T>` | Truy vấn dựa trên một entity mẫu | Tìm kiếm đơn giản theo các thuộc tính được cung cấp |

`T` là kiểu entity, còn `ID` là kiểu khóa chính của entity. Ví dụ `JpaRepository<Product, Long>` nghĩa là repository quản lý entity `Product` có khóa chính kiểu `Long`.

### 1.1. Repository — interface gốc

`Repository<T, ID>` là marker interface. Nó cho Spring Data biết repository làm việc với entity nào và ID có kiểu gì. Nó không tự cung cấp các phương thức như `save`, `findAll` hay `deleteById`.

Có thể kế thừa trực tiếp `Repository` và chỉ khai báo những phương thức ứng dụng muốn công khai:

~~~java
package com.example.store;

import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface ProductLookupRepository
        extends Repository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

Spring Data có thể tạo implementation cho phương thức truy vấn dẫn xuất `findBySku`. Cách này hữu ích khi một thành phần chỉ cần tra cứu sản phẩm và không nên có quyền gọi các thao tác ghi/xóa thông qua repository đó.

Nếu cần định nghĩa repository bằng annotation thay vì kế thừa `Repository`, có thể dùng `@RepositoryDefinition(domainClass = ..., idClass = ...)`. Trong phần lớn dự án, kế thừa interface vẫn dễ đọc và dễ tổ chức hơn.

### 1.2. CrudRepository — CRUD cơ bản

`CrudRepository<T, ID>` cung cấp các thao tác thường dùng:

~~~java
public interface ProductCrudRepository
        extends CrudRepository<Product, Long> {
}
~~~

Các phương thức tiêu biểu gồm:

- `save(entity)` và `saveAll(entities)` để lưu entity.
- `findById(id)`, `findAll()` và `findAllById(ids)` để đọc dữ liệu.
- `existsById(id)` và `count()` để kiểm tra sự tồn tại, đếm bản ghi.
- `deleteById(id)`, `delete(entity)`, `deleteAllById(ids)` và `deleteAll()` để xóa dữ liệu.

Các phương thức đọc một ID thường trả về `Optional<T>` để biểu diễn trường hợp không tìm thấy bản ghi. Trong `CrudRepository`, các phương thức trả về nhiều entity thường dùng `Iterable<T>`; điều này cho phép implementation không phải cam kết một cấu trúc danh sách cụ thể.

### 1.3. ListCrudRepository — CRUD với List

`ListCrudRepository` được bổ sung từ Spring Data 3.0. Interface này mở rộng `CrudRepository` và ghi đè một số phương thức để trả về `List`, ví dụ:

~~~java
public interface ProductListRepository
        extends ListCrudRepository<Product, Long> {
}
~~~

Điểm khác biệt chính:

- `findAll()` trả về `List<T>`.
- `findAllById(ids)` trả về `List<T>`.
- `saveAll(entities)` trả về `List<S>`.

Chọn interface này khi muốn dùng API CRUD cơ bản nhưng cần kiểu trả về `List` để truy cập theo index, dùng các thao tác của Collection hoặc truyền vào thành phần nhận `List`.

Không cần chọn `ListCrudRepository` nếu ứng dụng không quan tâm kiểu trả về cụ thể. Với Spring Data JPA 3.x+, `JpaRepository` vốn đã cung cấp các phương thức trả về `List`.

### 1.4. PagingAndSortingRepository — phân trang và sắp xếp

`PagingAndSortingRepository<T, ID>` cung cấp các phương thức đọc có phân trang hoặc sắp xếp, tiêu biểu là:

~~~java
Page<Product> findAll(Pageable pageable);
Iterable<Product> findAll(Sort sort);
~~~

Interface này phù hợp khi cần giới hạn số bản ghi đọc trong mỗi lần truy vấn, hoặc sắp xếp theo thuộc tính entity. Tuy nhiên, cách kết hợp interface này với CRUD phụ thuộc phiên bản Spring Data; điểm thay đổi quan trọng được trình bày ở phần 2.

### 1.5. JpaRepository — lựa chọn mặc định cho repository JPA

Trong ứng dụng Spring Data JPA thông thường, có thể bắt đầu bằng:

~~~java
package com.example.store;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

`JpaRepository` kết hợp các khả năng cần thiết của repository JPA:

- CRUD với các phương thức trả về `List` ở những API phù hợp.
- Phân trang và sắp xếp.
- Query by Example.
- Các thao tác JPA như `flush()`, `saveAndFlush()`, `saveAllAndFlush()` và các phương thức xóa theo batch.
- `getReferenceById(id)` để lấy tham chiếu entity theo ID; việc truy cập dữ liệu có thể được trì hoãn cho đến khi cần.

Vì đã bao gồm nhiều chức năng, `JpaRepository` thường là lựa chọn ngắn gọn nhất cho một repository cần đọc, ghi, xóa và phân trang. Nếu chỉ cần một phần API, có thể tạo interface hẹp hơn để tránh công khai các thao tác không phù hợp với trách nhiệm của thành phần sử dụng.

Một số phương thức JPA đặc thù cần hiểu đúng:

- `flush()` đồng bộ các thay đổi đang chờ trong persistence context xuống database. Flush không đồng nghĩa với commit transaction.
- `saveAndFlush(entity)` lưu entity và yêu cầu flush ngay.
- `saveAllAndFlush(entities)` lưu một nhóm entity rồi flush.
- `getReferenceById(id)` có thể trả về proxy/tham chiếu mà chưa đọc bản ghi ngay. Nếu ID không tồn tại, lỗi có thể chỉ xuất hiện khi proxy được truy cập hoặc khi provider kiểm tra dữ liệu.
- `deleteAllInBatch()` và các phương thức xóa theo batch thực hiện thao tác xóa hàng loạt. Chúng có thể bỏ qua callback vòng đời entity và khiến persistence context đang mở không đồng bộ với database. Chỉ dùng khi hiểu rõ hệ quả.

`saveAll` cũng không bảo đảm rằng Hibernate sẽ phát đúng một câu SQL INSERT cho toàn bộ danh sách. Hiệu quả batching phụ thuộc cấu hình JPA provider, loại ID, database và transaction.

## 2. Khác biệt giữa Spring Data 2.x và 3.x

Khi nâng cấp Spring Data, cần chú ý thay đổi ở quan hệ kế thừa giữa các interface. Đây là nguyên nhân phổ biến khiến code repository cũ không biên dịch hoặc mất phương thức CRUD sau khi đổi dependency.

### 2.1. Spring Data 2.x

Trong dòng Spring Data 2.x, `PagingAndSortingRepository` kế thừa `CrudRepository`. Vì vậy, repository chỉ kế thừa `PagingAndSortingRepository` đã có cả CRUD và các phương thức phân trang/sắp xếp:

~~~java
// Mẫu phù hợp với Spring Data 2.x
public interface ProductRepository
        extends PagingAndSortingRepository<Product, Long> {
}
~~~

Repository trên có thể gọi cả `save`, `findById`, `deleteById` lẫn `findAll(Pageable)`.

### 2.2. Spring Data 3.x trở lên

Từ Spring Data 3.0, `PagingAndSortingRepository` không còn kế thừa `CrudRepository`. Interface này tập trung vào phân trang và sắp xếp. Nếu chỉ kế thừa nó, repository không tự có các phương thức CRUD như `save` hay `deleteById`.

Ví dụ:

~~~java
// Chỉ có khả năng phân trang/sắp xếp trong Spring Data 3.x+
public interface ProductPagingRepository
        extends PagingAndSortingRepository<Product, Long> {
}
~~~

Nếu muốn kết hợp CRUD và phân trang/sắp xếp, hãy kế thừa cả hai:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long>,
                PagingAndSortingRepository<Product, Long> {
}
~~~

Spring Data 3.0 cũng bổ sung `ListCrudRepository` và `ListPagingAndSortingRepository` để hỗ trợ các API trả về `List`. Với JPA, lựa chọn đơn giản hơn thường là `JpaRepository`, vì interface này đã kết hợp các khả năng tương ứng.

### 2.3. Bảng so sánh nhanh

| Nhu cầu | Spring Data 2.x | Spring Data 3.x+ |
|---|---|---|
| CRUD cơ bản | `CrudRepository` | `CrudRepository` hoặc `ListCrudRepository` |
| CRUD + paging/sorting qua một interface | `PagingAndSortingRepository` | `JpaRepository` cho JPA, hoặc kết hợp `CrudRepository` với `PagingAndSortingRepository` |
| Paging/sorting riêng | `PagingAndSortingRepository` | `PagingAndSortingRepository` |
| CRUD với kết quả List | `JpaRepository` trả về List ở các phương thức JPA tương ứng | `ListCrudRepository` hoặc `JpaRepository` |
| Paging/sorting với kết quả List cho Sort | Tùy API có trong phiên bản đang dùng | `ListPagingAndSortingRepository` hoặc `JpaRepository` |

Không nên sao chép một ví dụ repository từ tài liệu Spring Data 2.x vào dự án 3.x mà không kiểm tra quan hệ kế thừa. Hãy xem Javadoc đúng phiên bản dependency mà Spring Boot đang quản lý.

### 2.4. Spring Boot, Java và namespace JPA

Phiên bản Spring Boot quyết định bộ phiên bản Spring Framework và Spring Data tương thích được quản lý qua dependency management.

- Các dự án Spring Boot 2.x thường dùng Spring Data 2.x và namespace `javax.persistence`.
- Spring Boot 3.x chuyển sang Spring Data 3.x, yêu cầu Java 17 trở lên và dùng namespace `jakarta.persistence`.
- Khi dùng dòng Spring Boot mới hơn, hãy để BOM của Spring Boot quản lý phiên bản Spring Data tương ứng thay vì tự nâng riêng từng module.

Ví dụ import entity của dự án Spring Boot 3.x:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
~~~

Dự án Spring Boot 2.x cũ thường dùng:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.GeneratedValue;
~~~

Không trộn `javax.persistence` và `jakarta.persistence` trong cùng một mô hình entity. Khi nâng cấp, cần kiểm tra cả import trong mã nguồn, dependency, plugin, thư viện tích hợp và cấu hình kiểm thử.

Có thể xem dependency đang được resolve bằng Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data,org.springframework.boot
~~~

Hãy dùng phiên bản Spring Data do Spring Boot BOM quản lý, trừ khi dự án có lý do tương thích rõ ràng để ghi đè. Tự đặt phiên bản rời rạc cho `spring-data-jpa` và `spring-data-commons` có thể tạo ra các API không tương thích.

## 3. Chọn interface theo nhu cầu thực tế

Không có một interface duy nhất tối ưu cho mọi ứng dụng. Nên bắt đầu từ những thao tác mà thành phần sử dụng thực sự cần.

| Tình huống | Interface nên cân nhắc | Lý do |
|---|---|---|
| Repository JPA thông thường, cần CRUD và paging | `JpaRepository<T, ID>` | Đầy đủ chức năng và ít cấu hình |
| Chỉ cần CRUD cơ bản | `CrudRepository<T, ID>` | API nhỏ, không phụ thuộc JPA-specific methods |
| Dùng Spring Data 3.x+, cần CRUD trả về List | `ListCrudRepository<T, ID>` | Kiểu trả về thuận tiện cho Collection |
| Chỉ cần truy vấn, không muốn công khai ghi/xóa | `Repository<T, ID>` với các query method tự khai báo | Giới hạn bề mặt API |
| Chỉ cần paging/sorting và đã có CRUD ở một interface khác | `PagingAndSortingRepository<T, ID>` | Tách trách nhiệm truy vấn theo trang |
| Bộ lọc tìm kiếm thay đổi theo tham số người dùng | `JpaSpecificationExecutor<T>` kết hợp `JpaRepository` | Tạo điều kiện truy vấn động |
| Tìm kiếm theo một đối tượng mẫu đơn giản | `QueryByExampleExecutor<T>` hoặc `JpaRepository` | Không phải viết nhiều query method |
| Có truy vấn cố định phức tạp | `@Query` trên repository | Kiểm soát JPQL hoặc native SQL |
| Có logic truy cập dữ liệu tùy biến | Repository fragment | Tách phần cài đặt riêng khỏi CRUD chuẩn |

### 3.1. Dùng JpaRepository cho phần lớn CRUD JPA

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);

    Page<Customer> findByActiveTrue(Pageable pageable);
}
~~~

Ví dụ này có CRUD, paging, sorting, truy vấn theo email và truy vấn khách hàng đang hoạt động theo trang. Phương thức truy vấn dẫn xuất được tạo từ tên thuộc tính Java trong entity.

Chọn cách này khi repository là cổng truy cập dữ liệu chính cho một aggregate hoặc entity và ứng dụng cần phần lớn thao tác phổ biến.

### 3.2. Giới hạn API bằng Repository

Một thành phần chỉ được phép tra cứu có thể dùng repository hẹp:

~~~java
public interface CustomerReader
        extends Repository<Customer, Long> {

    Optional<Customer> findById(Long id);

    Optional<Customer> findByEmailIgnoreCase(String email);

    List<Customer> findByActiveTrue();
}
~~~

Repository này không công khai `save` hay `deleteById`. Nó hữu ích trong các module cần tách quyền đọc/ghi ở cấp API nội bộ, hoặc khi muốn giảm phụ thuộc của service vào các thao tác không sử dụng.

Đây không phải cơ chế bảo mật database. Quyền truy cập thật vẫn phải được kiểm soát ở tầng ứng dụng, transaction và database khi cần.

Nếu tạo một interface cơ sở generic dùng chung cho nhiều repository, đánh dấu nó bằng `@NoRepositoryBean` để Spring Data không cố tạo bean trực tiếp cho interface chưa có domain type cụ thể:

~~~java
@NoRepositoryBean
public interface ReadOnlyRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();
}

public interface ProductReader
        extends ReadOnlyRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

Các import cần thiết:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;
~~~

### 3.3. Kết hợp JpaSpecificationExecutor cho bộ lọc động

Khi màn hình tìm kiếm có nhiều bộ lọc tùy chọn, chẳng hạn tên, trạng thái, danh mục và khoảng giá, việc tạo một phương thức repository cho mọi tổ hợp điều kiện sẽ nhanh chóng trở nên khó bảo trì.

Có thể mở rộng repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

Một Specification đơn giản:

~~~java
public final class ProductSpecifications {

    private ProductSpecifications() {
    }

    public static Specification<Product> hasCategory(String category) {
        return (root, query, builder) ->
                builder.equal(root.get("category"), category);
    }

    public static Specification<Product> priceAtLeast(BigDecimal minPrice) {
        return (root, query, builder) ->
                builder.greaterThanOrEqualTo(root.get("price"), minPrice);
    }
}
~~~

Kết hợp các điều kiện trong service:

~~~java
Specification<Product> filter =
        Specification.where(ProductSpecifications.hasCategory("BOOK"))
                .and(ProductSpecifications.priceAtLeast(
                        new BigDecimal("100.00")));

Page<Product> result = products.findAll(
        filter,
        PageRequest.of(0, 20, Sort.by("name").ascending())
);
~~~

Ví dụ cần các import sau:

~~~java
import java.math.BigDecimal;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
~~~

Trong ứng dụng thực tế, chỉ thêm điều kiện khi tham số tương ứng có giá trị. Tránh gọi `equal` với giá trị null nếu nghiệp vụ yêu cầu bỏ qua bộ lọc. Cũng cần kiểm tra kiểu thuộc tính, tên thuộc tính entity và truy vấn SQL do Hibernate tạo ra.

### 3.4. Chọn Query by Example cho tìm kiếm đơn giản

Query by Example (QBE) cho phép tạo một entity mẫu rồi dùng các thuộc tính của nó làm tiêu chí tìm kiếm:

~~~java
Product probe = new Product();
probe.setName("keyboard");

ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnoreCase()
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING);

Example<Product> example = Example.of(probe, matcher);

List<Product> matches = products.findAll(example);
~~~

QBE thích hợp khi điều kiện tìm kiếm chủ yếu dựa trên giá trị thuộc tính của một entity mẫu và các tùy chọn so khớp. QBE không thay thế hoàn toàn Specification: các điều kiện OR phức tạp, biểu thức trên quan hệ, phép so sánh nâng cao hoặc logic nghiệp vụ nhiều nhánh thường phù hợp hơn với Specification hoặc JPQL.

### 3.5. Chọn Page, Slice hay List

Khi truy vấn danh sách lớn, kiểu kết quả cũng là một quyết định thiết kế:

- `Page<T>` chứa nội dung trang và thông tin tổng số phần tử/trang. Thông thường Spring Data cần thêm truy vấn đếm để tính tổng.
- `Slice<T>` cho biết có trang tiếp theo hay không mà không nhất thiết phải đếm toàn bộ kết quả.
- `List<T>` chỉ trả về dữ liệu; khi truyền `Pageable`, danh sách vẫn có thể bị giới hạn theo trang nhưng không có metadata trang.

Ví dụ:

~~~java
Page<Product> findByActiveTrue(Pageable pageable);

Slice<Product> findByCategory(String category, Pageable pageable);

List<Product> findByCategoryAndActiveTrue(
        String category,
        Pageable pageable
);
~~~

Dùng `Page` khi giao diện cần tổng số kết quả và số trang. Dùng `Slice` cho kiểu tải tiếp hoặc cuộn vô hạn khi chỉ cần biết còn dữ liệu hay không. Dùng `List` khi caller chỉ cần các bản ghi của một đoạn dữ liệu đã giới hạn.

## 4. Khi nào cần Query method, @Query hoặc repository fragment?

Các interface repository có thể kết hợp nhiều chiến lược truy vấn. Chọn cách đơn giản nhất đáp ứng rõ yêu cầu.

### 4.1. Derived query — tạo truy vấn từ tên phương thức

~~~java
Optional<Product> findBySku(String sku);

List<Product> findByNameContainingIgnoreCase(String keyword);

List<Product> findByPriceBetween(
        BigDecimal minPrice,
        BigDecimal maxPrice
);
~~~

Phù hợp với truy vấn có điều kiện dễ đọc từ tên phương thức. Khi tên phương thức trở nên quá dài hoặc biểu đạt logic phức tạp, hãy cân nhắc Specification hoặc `@Query`.

### 4.2. @Query — JPQL hoặc native SQL

~~~java
@Query("""
       select p
       from Product p
       where p.active = true
         and p.price >= :minPrice
       """)
List<Product> findAvailableProducts(
        @Param("minPrice") BigDecimal minPrice
);
~~~

JPQL tham chiếu entity và thuộc tính Java, không tham chiếu trực tiếp tên bảng/cột vật lý. Nếu dùng native SQL, truy vấn sẽ gắn chặt hơn với cú pháp và khả năng của database cụ thể.

Với câu lệnh cập nhật/xóa dùng `@Modifying`, cần thiết kế transaction rõ ràng và cân nhắc trạng thái persistence context sau bulk operation. Bulk update/delete không tự đồng bộ mọi entity đang được quản lý trong bộ nhớ.

### 4.3. Repository fragment — cài đặt phần tùy biến

Khi có logic truy vấn không phù hợp với derived query hoặc `@Query`, có thể tách thành fragment interface và implementation riêng. Repository chính kế thừa fragment để Spring Data ghép implementation vào repository.

Cách này giúp phần tùy biến được tổ chức rõ ràng, đồng thời giữ các thao tác CRUD chuẩn trong `JpaRepository`. Không nên tạo một repository implementation lớn chứa mọi logic truy cập dữ liệu nếu có thể chia thành các fragment theo trách nhiệm.

## 5. Một số nhầm lẫn cần tránh

1. **Chỉ kế thừa PagingAndSortingRepository trên Spring Data 3.x rồi gọi save:** interface này không còn cung cấp CRUD. Hãy thêm `CrudRepository` hoặc dùng `JpaRepository`.
2. **Cho rằng JpaRepository là bắt buộc:** repository có thể kế thừa `Repository` hoặc `CrudRepository` nếu chỉ cần một tập phương thức nhỏ.
3. **Cho rằng ListCrudRepository có từ mọi phiên bản:** interface này được bổ sung từ Spring Data 3.0. Không dùng nó trong dự án còn phụ thuộc Spring Data 2.x.
4. **Nhầm Page với List:** `Page` cung cấp metadata và thường kéo theo truy vấn count; `List` không có thông tin tổng số trang.
5. **Nhầm flush với commit:** flush gửi thay đổi đang chờ xuống database, còn commit kết thúc transaction.
6. **Dùng deleteAllInBatch như deleteAll:** thao tác batch có thể bỏ qua entity lifecycle callback và không đồng bộ persistence context.
7. **Nâng riêng Spring Data module:** cần giữ các module Spring Data tương thích với nhau; ưu tiên phiên bản do Spring Boot BOM quản lý.
8. **Dùng repository reactive với JPA:** JPA đồng bộ/blocking; chọn repository reactive chỉ khi dùng công nghệ lưu trữ và driver reactive tương ứng.
9. **Cho rằng saveAll luôn là một batch SQL:** batching cần cấu hình provider và còn phụ thuộc loại khóa, database, transaction.
10. **Đưa mọi thao tác vào repository:** transaction và quy tắc nghiệp vụ thường nên được tổ chức ở service; repository tập trung vào truy cập dữ liệu.

## 6. Quy trình lựa chọn interface

Có thể áp dụng quy trình sau khi tạo repository mới hoặc review repository hiện có:

1. Xác định module lưu trữ: nếu dùng JPA thì dùng các interface Spring Data JPA; không chọn interface reactive của module khác.
2. Kiểm tra phiên bản Spring Boot/Spring Data được quản lý trong dự án.
3. Liệt kê thao tác caller cần: đọc, ghi, xóa, phân trang, sắp xếp, truy vấn động hay thao tác JPA đặc thù.
4. Chọn interface nhỏ nhất đáp ứng nhu cầu. Với CRUD JPA thông thường, bắt đầu bằng `JpaRepository`.
5. Nếu cần truy vấn động, thêm `JpaSpecificationExecutor` hoặc dùng QBE tùy độ phức tạp.
6. Nếu chỉ cần một số phương thức, cân nhắc kế thừa `Repository` và khai báo API hẹp.
7. Viết kiểm thử repository và kiểm tra SQL phát sinh cho các truy vấn quan trọng.
8. Khi nâng cấp phiên bản, đọc release notes/Javadoc của đúng phiên bản và kiểm tra thay đổi namespace, method signature, quan hệ kế thừa.

## 7. Checklist tự kiểm tra

- [ ] Tôi biết entity type và kiểu ID của repository.
- [ ] Tôi đã xác định phiên bản Spring Data thực tế từ dependency tree hoặc BOM.
- [ ] Tôi không dựa vào quan hệ kế thừa PagingAndSortingRepository của Spring Data 2.x trong dự án 3.x.
- [ ] Tôi chọn JpaRepository khi cần bộ tính năng JPA đầy đủ.
- [ ] Tôi chọn Repository/CrudRepository khi muốn API hẹp hơn.
- [ ] Tôi hiểu khi nào dùng Page, Slice hoặc List.
- [ ] Tôi chỉ thêm JpaSpecificationExecutor khi có nhu cầu truy vấn động.
- [ ] Tôi hiểu flush, transaction và giới hạn của các thao tác batch.
- [ ] Tôi không trộn javax.persistence với jakarta.persistence.
- [ ] Repository có kiểm thử cho các phương thức truy vấn quan trọng.

## Kết luận

Với ứng dụng Spring Data JPA, `JpaRepository<T, ID>` là điểm bắt đầu hợp lý khi cần CRUD, phân trang, sắp xếp và các thao tác JPA thông dụng. Dùng `Repository` hoặc `CrudRepository` để giữ API nhỏ, bổ sung `JpaSpecificationExecutor` cho bộ lọc động và chọn `Page`/`Slice`/`List` theo dữ liệu mà caller cần. Khi nâng cấp từ Spring Data 2.x lên 3.x, phải kiểm tra thay đổi quan hệ kế thừa của `PagingAndSortingRepository` và các interface List mới để repository tiếp tục biên dịch và cung cấp đúng chức năng.
