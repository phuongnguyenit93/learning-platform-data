# Lựa chọn interface theo phiên bản và nhu cầu của ứng dụng trong Spring Data JPA

Việc chọn interface repository ảnh hưởng đến tập phương thức mà tầng service có thể gọi, kiểu dữ liệu trả về và khả năng nâng cấp Spring Data. Một repository cần ghi/xóa dữ liệu có yêu cầu khác với một repository chỉ phục vụ tìm kiếm; ứng dụng cần phân trang cũng có yêu cầu khác với tác vụ chỉ tải một danh sách nhỏ.

Trong Spring Data JPA, `JpaRepository<T, ID>` thường là lựa chọn thuận tiện cho CRUD JPA thông dụng. Tuy nhiên, không phải repository nào cũng cần toàn bộ API đó. Khi thiết kế, hãy xác định phiên bản Spring Data đang dùng, các thao tác caller thực sự cần và ranh giới trách nhiệm của repository.

Bài này tập trung vào cách ra quyết định, các khác biệt tương thích giữa Spring Data 2.x và 3.x, cách thu hẹp API và cách kiểm tra lựa chọn đó trong một dự án thực tế.

## 1. Bắt đầu từ nhu cầu của caller

Đừng chọn interface chỉ vì nó quen thuộc. Trước tiên, liệt kê các khả năng mà thành phần gọi repository cần:

- Chỉ tra cứu theo ID hoặc theo một vài thuộc tính?
- Có cần tạo, cập nhật và xóa dữ liệu?
- Có cần sắp xếp hoặc phân trang?
- Có bộ lọc tùy chọn được kết hợp động?
- Có cần API đặc thù JPA như flush, tham chiếu entity hoặc thao tác xóa theo batch?
- Có cần trả về `List`, `Page` hay `Slice`?
- Repository có được dùng ở nhiều module hoặc nhiều tầng với mức quyền thao tác khác nhau không?

Các câu trả lời này quyết định interface phù hợp. Ví dụ, một service chỉ tìm sản phẩm theo SKU không cần nhận một repository công khai `deleteAll()`; một trang quản trị có phân trang thường cần `Pageable`; một quy trình nhập dữ liệu có thể cần API ghi theo lô và transaction rõ ràng.

Hãy coi repository là hợp đồng giữa tầng nghiệp vụ và tầng lưu trữ. Hợp đồng càng rộng thì caller càng có nhiều khả năng phụ thuộc vào các thao tác mà nó không thực sự cần.

## 2. Xác định phiên bản Spring Data trước khi chọn

Phiên bản interface có thể khác nhau giữa các dòng Spring Data. Trong dự án Spring Boot, phiên bản Spring Data thường được quản lý thông qua BOM của Spring Boot. Vì vậy, hãy kiểm tra dependency đã resolve thay vì đoán từ tên dependency hoặc một bài hướng dẫn trên mạng.

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-commons,org.springframework.data:spring-data-jpa
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
~~~

Nếu lệnh Gradle được chạy trên Windows PowerShell, có thể dùng `gradlew.bat` thay cho `./gradlew`.

### 2.1. Khác biệt quan trọng giữa Spring Data 2.x và 3.x

Trong Spring Data 2.x, `PagingAndSortingRepository<T, ID>` kế thừa `CrudRepository<T, ID>`. Vì thế, chỉ cần kế thừa `PagingAndSortingRepository` là repository có cả CRUD và paging/sorting.

~~~java
// Spring Data 2.x: PagingAndSortingRepository có cả CRUD.
public interface ProductRepository
        extends PagingAndSortingRepository<Product, Long> {
}
~~~

Từ Spring Data 3.0, quan hệ kế thừa này thay đổi: `PagingAndSortingRepository` tập trung vào paging/sorting và không còn kế thừa `CrudRepository`. Nếu chỉ kế thừa nó, các phương thức như `save` hoặc `deleteById` không tự xuất hiện.

~~~java
// Spring Data 3.x+: chỉ có paging/sorting.
public interface ProductPagingRepository
        extends PagingAndSortingRepository<Product, Long> {
}
~~~

Nếu dự án 3.x cần cả CRUD lẫn paging/sorting mà không dùng `JpaRepository`, hãy kết hợp hai interface:

~~~java
// Spring Data 3.x+: kết hợp rõ hai nhóm chức năng.
public interface ProductRepository
        extends CrudRepository<Product, Long>,
                PagingAndSortingRepository<Product, Long> {
}
~~~

Spring Data 3.0 cũng bổ sung `ListCrudRepository` và `ListPagingAndSortingRepository`. Chúng cung cấp các phương thức trả về `List` ở những trường hợp tương ứng, giúp caller không phải xử lý kiểu `Iterable` khi muốn một danh sách cụ thể.

| Phiên bản | CRUD | Paging/sorting | API trả về List |
|---|---|---|---|
| Spring Data 2.x | `CrudRepository` | `PagingAndSortingRepository` cũng bao gồm CRUD | `JpaRepository` có các API List phổ biến |
| Spring Data 3.x+ | `CrudRepository` hoặc `ListCrudRepository` | `PagingAndSortingRepository` là nhóm riêng | `ListCrudRepository`, `ListPagingAndSortingRepository` và `JpaRepository` |

Trong ứng dụng JPA, `JpaRepository` thường che đi phần lớn khác biệt này vì nó cung cấp tập chức năng JPA cần thiết. Khác biệt kế thừa vẫn quan trọng khi dự án dùng trực tiếp `PagingAndSortingRepository` hoặc có interface cơ sở tự định nghĩa.

### 2.2. Spring Boot 2.x và 3.x

Các dự án Spring Boot 2.x thường đi cùng Spring Data 2.x và namespace persistence `javax.persistence`. Spring Boot 3.x chuyển sang Spring Data 3.x, yêu cầu Java 17 trở lên và dùng namespace `jakarta.persistence`.

Ví dụ import trong dự án Boot 3.x:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
~~~

Dự án Boot 2.x cũ thường có:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.GeneratedValue;
~~~

Không trộn hai namespace trong cùng một entity model. Khi nâng cấp, cần kiểm tra entity, converter, annotation, thư viện tích hợp và cấu hình kiểm thử. Hãy để BOM của Spring Boot quản lý các module Spring Data tương thích; không tự nâng riêng `spring-data-commons` và `spring-data-jpa` lên những phiên bản không cùng dòng.

## 3. Chọn theo bề mặt API cần công khai

### 3.1. Repository — chỉ khai báo hợp đồng cần thiết

`Repository<T, ID>` là interface gốc để Spring Data nhận diện một repository. Nó không tự cung cấp CRUD. Ta có thể khai báo một số phương thức cần dùng:

~~~java
package com.example.catalog;

import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface ProductReader extends Repository<Product, Long> {

    Optional<Product> findBySku(String sku);

    Optional<Product> findById(Long id);
}
~~~

Spring Data có thể tạo implementation cho các query method trên. Caller chỉ nhìn thấy hai thao tác tra cứu đã khai báo. Cách này phù hợp với thành phần chỉ cần đọc, hoặc module muốn giữ hợp đồng hẹp.

Một interface hẹp không tự tạo ra cơ chế bảo mật ở database. Nếu người dùng cuối không được phép xem hoặc sửa dữ liệu, vẫn cần kiểm tra quyền trong service/API và áp dụng phân quyền database khi kiến trúc yêu cầu.

### 3.2. CrudRepository — CRUD cơ bản

Khi caller cần thao tác thêm, đọc, cập nhật và xóa nhưng không cần API đặc thù JPA, `CrudRepository<T, ID>` là một lựa chọn nhỏ gọn:

~~~java
public interface ProductCrudRepository
        extends CrudRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

Các phương thức CRUD cơ bản có thể dùng cho nhiều Spring Data module. Điều này hữu ích khi muốn giữ service phụ thuộc vào hợp đồng repository chung, dù implementation cụ thể có thể là JPA.

Trong Spring Data 2.x, các phương thức trả về nhiều entity của `CrudRepository` thường trả về `Iterable`. Nếu caller cần `List`, có thể chuyển đổi tại service hoặc chọn một interface có API trả về List phù hợp với phiên bản.

### 3.3. ListCrudRepository — khi caller cần List

Từ Spring Data 3.0:

~~~java
public interface ProductListRepository
        extends ListCrudRepository<Product, Long> {
}
~~~

Chọn interface này nếu ứng dụng chỉ cần CRUD nhưng muốn `findAll`, `findAllById` và `saveAll` trả về `List` theo hợp đồng. Nó phù hợp với caller cần Collection API đầy đủ, xử lý theo thứ tự hoặc truyền kết quả cho thành phần nhận `List`.

Không cần đổi sang `ListCrudRepository` chỉ để làm cho code ngắn hơn nếu dự án đã dùng `JpaRepository`; `JpaRepository` đã cung cấp kiểu trả về List cho các thao tác tương ứng.

### 3.4. PagingAndSortingRepository — khi cần phân trang hoặc sắp xếp

Interface này cung cấp các phương thức đọc theo `Pageable` hoặc `Sort`. Trên Spring Data 3.x, nó không bao gồm CRUD.

~~~java
public interface ProductPagingRepository
        extends PagingAndSortingRepository<Product, Long> {
}
~~~

Nếu repository cần thêm CRUD trên 3.x, hãy kết hợp với `CrudRepository` hoặc dùng `JpaRepository` cho JPA. Nếu chỉ cần truy vấn theo trang, việc giữ interface paging riêng giúp thể hiện rõ trách nhiệm đọc.

### 3.5. JpaRepository — khi cần bộ chức năng JPA đầy đủ

Đây là lựa chọn phổ biến cho repository của ứng dụng JPA:

~~~java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

`JpaRepository` kết hợp các khả năng CRUD, paging/sorting và Query by Example, đồng thời cung cấp các thao tác JPA như flush và tham chiếu entity. Trong Spring Data 3.x, nó cũng cung cấp các API List phù hợp với cấu trúc interface mới.

Chọn nó khi caller thực sự cần phần lớn chức năng của repository JPA. Nếu một service chỉ cần tra cứu, có thể truyền vào một interface đọc hẹp hơn thay vì để service phụ thuộc vào toàn bộ `JpaRepository`.

## 4. Chọn kiểu kết quả theo cách caller sử dụng dữ liệu

Chọn interface mới chỉ giải quyết tập phương thức. Kiểu kết quả của truy vấn cũng ảnh hưởng đến hiệu năng và hợp đồng API.

### 4.1. List — danh sách đơn giản

Dùng `List<T>` khi tập kết quả nhỏ hoặc truy vấn đã được giới hạn rõ ràng:

~~~java
List<Product> findByCategory(String category);
~~~

Phương thức trên có thể tải toàn bộ sản phẩm thuộc một danh mục. Nếu danh mục có hàng trăm nghìn bản ghi, trả về toàn bộ danh sách có thể tốn bộ nhớ và thời gian.

### 4.2. Page — cần tổng số kết quả

~~~java
Page<Product> findByCategory(
        String category,
        Pageable pageable
);
~~~

`Page<T>` cung cấp nội dung trang, tổng số phần tử, tổng số trang và thông tin trang hiện tại. Để tính tổng, Spring Data thường cần thêm truy vấn count. Vì vậy, `Page` phù hợp với giao diện cần hiển thị kiểu “trang 2 trên 18” hoặc tổng số kết quả.

### 4.3. Slice — chỉ cần biết còn dữ liệu hay không

~~~java
Slice<Product> findByCategory(
        String category,
        Pageable pageable
);
~~~

`Slice<T>` cung cấp dữ liệu của lát hiện tại và thông tin có trang tiếp theo hay không. Nó phù hợp với nút “Tải thêm” hoặc cuộn vô hạn khi giao diện không cần tổng số bản ghi. Tùy query và database, Spring Data có thể lấy thêm một bản ghi để xác định còn kết quả tiếp theo.

### 4.4. List có Pageable — chỉ lấy dữ liệu đã giới hạn

~~~java
List<Product> findByActiveTrue(Pageable pageable);
~~~

Cách này giới hạn kết quả theo trang nhưng không trả về metadata tổng số phần tử như `Page`. Dùng khi caller chỉ cần một đoạn danh sách.

Không nên dùng `Page` cho mọi endpoint. Nếu không dùng tổng số kết quả, `Slice` hoặc `List` có thể giảm chi phí truy vấn.

## 5. Bổ sung executor theo kiểu tìm kiếm

Một repository có thể kết hợp nhiều interface để thêm năng lực tìm kiếm. Các executor không thay thế CRUD; chúng bổ sung cách xây dựng truy vấn.

### 5.1. JpaSpecificationExecutor — điều kiện động

Khi người dùng có thể bật/tắt nhiều bộ lọc, `JpaSpecificationExecutor<T>` giúp kết hợp các predicate:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

Ví dụ Specification:

~~~java
public final class ProductSpecs {

    private ProductSpecs() {
    }

    public static Specification<Product> active() {
        return (root, query, cb) ->
                cb.isTrue(root.get("active"));
    }

    public static Specification<Product> categoryIs(String category) {
        return (root, query, cb) ->
                cb.equal(root.get("category"), category);
    }

    public static Specification<Product> priceAtLeast(BigDecimal price) {
        return (root, query, cb) ->
                cb.greaterThanOrEqualTo(root.get("price"), price);
    }
}
~~~

Kết hợp:

~~~java
Specification<Product> spec =
        Specification.where(ProductSpecs.active())
                .and(ProductSpecs.categoryIs("BOOK"))
                .and(ProductSpecs.priceAtLeast(new BigDecimal("50.00")));

Page<Product> result = products.findAll(
        spec,
        PageRequest.of(0, 20, Sort.by("name").ascending())
);
~~~

Trong ứng dụng thực tế, chỉ thêm predicate khi bộ lọc tương ứng được truyền vào. Hãy xác thực dữ liệu đầu vào và kiểm tra query plan nếu bộ lọc có thể truy cập bảng lớn.

### 5.2. QueryByExampleExecutor — tìm theo entity mẫu

Query by Example phù hợp với tìm kiếm đơn giản dựa trên giá trị của một đối tượng mẫu:

~~~java
Product probe = new Product();
probe.setName("mouse");

ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnoreCase()
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING);

List<Product> matches =
        products.findAll(Example.of(probe, matcher));
~~~

QBE dễ dùng khi các điều kiện là so khớp thuộc tính thông thường. Nó không biểu đạt tốt mọi phép OR phức tạp, phép so sánh nâng cao hoặc điều kiện trên quan hệ; khi đó Specification hoặc JPQL thường rõ ràng hơn.

## 6. Tổ chức interface theo ranh giới module

Một ứng dụng lớn có thể có nhiều service dùng chung một entity nhưng với nhu cầu khác nhau. Không nhất thiết mọi service đều phải phụ thuộc cùng một repository rộng.

Ví dụ:

~~~java
public interface ProductReader extends Repository<Product, Long> {
    Optional<Product> findById(Long id);
    Optional<Product> findBySku(String sku);
}

public interface ProductWriter extends Repository<Product, Long> {
    <S extends Product> S save(S product);
}
~~~

Một adapter hoặc service có thể nhận đúng hợp đồng cần thiết. Cách tổ chức này giúp dependency thể hiện mục đích của caller và giảm khả năng gọi nhầm thao tác.

Nếu tạo interface generic dùng chung, đánh dấu nó bằng `@NoRepositoryBean` để Spring Data không cố tạo bean cho interface chưa có domain type cụ thể:

~~~java
@NoRepositoryBean
public interface ReadRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();
}

public interface ProductReadRepository
        extends ReadRepository<Product, Long> {

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

Không tạo nhiều interface chỉ để đổi tên các phương thức giống hệt nhau. Việc tách chỉ có giá trị khi nó thể hiện một ranh giới trách nhiệm thực tế, được caller sử dụng rõ ràng và có thể kiểm thử.

### 6.1. Ứng dụng có nhiều Spring Data module

Nếu cùng một ứng dụng dùng JPA và MongoDB, cần cấu hình repository scanning rõ ràng. Khi một domain type có annotation của nhiều store hoặc repository base interface không đủ để xác định store, Spring Data có thể không phân biệt được repository thuộc module nào.

Có thể tách package:

~~~java
@Configuration
@EnableJpaRepositories(basePackages = "com.example.persistence.jpa")
class JpaRepositoryConfig {
}

@Configuration
@EnableMongoRepositories(basePackages = "com.example.persistence.mongo")
class MongoRepositoryConfig {
}
~~~

Đây là ví dụ cấu hình khi ứng dụng thực sự có nhiều module tương ứng; không thêm cấu hình này vào dự án chỉ dùng JPA. Đảm bảo các package không bị quét chồng lấn ngoài ý muốn.

## 7. Kiểm tra lựa chọn bằng compile-time và test

Một repository interface có thể biên dịch ở phiên bản này nhưng không biên dịch ở phiên bản khác do thay đổi quan hệ kế thừa. Vì vậy, kiểm tra lựa chọn bằng một bài compile nhỏ là cách hữu ích khi nâng cấp.

Ví dụ repository cho Spring Data 3.x:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long>,
                PagingAndSortingRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

Một test tích hợp có thể xác nhận bean được tạo và query method hoạt động:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository products;

    @Test
    void findsProductBySku() {
        Product product = products.save(
                new Product("Keyboard", "KB-01")
        );

        Optional<Product> found = products.findBySku("KB-01");

        assertThat(found).isPresent();
        assertThat(found.orElseThrow().getId()).isEqualTo(product.getId());
    }
}
~~~

Đây là đoạn minh họa; constructor và thuộc tính của `Product` phải khớp với entity thực tế trong dự án. Kiểm thử repository nên dùng database test phù hợp, chẳng hạn H2 cho kiểm thử cơ bản hoặc Testcontainers khi cần xác minh hành vi đặc thù của database triển khai.

Các bước kiểm tra khi nâng cấp:

1. Xác nhận phiên bản Spring Boot và Spring Data đã resolve.
2. Kiểm tra import `javax.persistence` hay `jakarta.persistence`.
3. Tìm các interface kế thừa `PagingAndSortingRepository`.
4. Kiểm tra nơi gọi `save`, `deleteById` hoặc các phương thức CRUD khác trên repository đó.
5. Nếu dự án 3.x cần cả CRUD và paging, kết hợp `CrudRepository` với `PagingAndSortingRepository` hoặc chuyển sang `JpaRepository`.
6. Biên dịch toàn dự án và chạy test repository.
7. Kiểm tra SQL phát sinh cho các truy vấn có tác động hiệu năng.

## 8. Các quyết định mẫu

| Nhu cầu | Lựa chọn đề xuất | Lý do |
|---|---|---|
| Một repository JPA cần CRUD, paging và thao tác JPA | `JpaRepository` | Tập chức năng đầy đủ, ít phải kết hợp |
| Chỉ đọc theo ID và SKU | `Repository` với query method | Hợp đồng hẹp, không công khai ghi/xóa |
| CRUD chung, không cần API JPA riêng | `CrudRepository` | Tập phương thức cơ bản |
| CRUD trả về List trên Spring Data 3.x | `ListCrudRepository` | Kiểu trả về phù hợp caller |
| Paging/sorting độc lập trên Spring Data 3.x | `PagingAndSortingRepository` | Chỉ cung cấp nhóm đọc theo trang/sắp xếp |
| Bộ lọc nhiều điều kiện tùy chọn | `JpaSpecificationExecutor` | Ghép predicate động |
| Tìm kiếm đơn giản theo entity mẫu | `QueryByExampleExecutor` | Ít mã truy vấn |
| Có truy vấn JPQL/native SQL cố định | Query method với `@Query` | Chủ động định nghĩa câu truy vấn |

## 9. Lỗi thường gặp khi chọn interface

- **Chỉ kế thừa PagingAndSortingRepository trong Spring Data 3.x nhưng gọi save:** thêm `CrudRepository` hoặc dùng `JpaRepository`.
- **Dùng ListCrudRepository trong dự án Spring Data 2.x:** interface chưa có ở dòng này; kiểm tra phiên bản dependency trước khi áp dụng.
- **Chọn JpaRepository cho mọi module dù caller chỉ đọc:** hợp đồng quá rộng khiến caller phụ thuộc vào thao tác không cần thiết.
- **Dùng Page cho màn hình không cần tổng số kết quả:** có thể tạo truy vấn count không cần thiết; cân nhắc Slice hoặc List có giới hạn.
- **Dùng Specification cho một truy vấn rất đơn giản:** derived query hoặc `@Query` có thể dễ đọc hơn.
- **Tự nâng riêng một module Spring Data:** có thể làm lệch phiên bản giữa Commons và JPA; ưu tiên BOM của Spring Boot.
- **Coi repository hẹp là ranh giới bảo mật:** quyền truy cập cần được kiểm soát trong service/API và database theo yêu cầu.
- **Dùng repository JPA reactive:** JPA là blocking; chọn công nghệ lưu trữ reactive nếu cần luồng reactive đầu-cuối.

## 10. Checklist trước khi tạo hoặc thay đổi repository

- [ ] Đã biết phiên bản Spring Data thực tế.
- [ ] Đã xác định caller cần đọc, ghi, xóa, phân trang hay truy vấn động.
- [ ] Đã chọn interface có bề mặt API vừa đủ.
- [ ] Nếu dùng Spring Data 3.x, đã kiểm tra quan hệ kế thừa của PagingAndSortingRepository.
- [ ] Đã cân nhắc ListCrudRepository nếu cần API List trên Spring Data 3.x.
- [ ] Đã chọn Page, Slice hoặc List theo nhu cầu hiển thị.
- [ ] Chỉ thêm JpaSpecificationExecutor khi thật sự cần điều kiện động.
- [ ] Đã kiểm tra package scanning nếu ứng dụng dùng nhiều Spring Data module.
- [ ] Đã chạy compile và test repository sau khi thay đổi.

Một lựa chọn tốt không nhất thiết là interface ngắn nhất hoặc rộng nhất. Hãy để nhu cầu của caller quyết định hợp đồng, để phiên bản dependency quyết định API khả dụng, và để service quản lý transaction cùng quy tắc nghiệp vụ. Với phần lớn repository JPA thông thường, bắt đầu bằng `JpaRepository<T, ID>` là hợp lý; thu hẹp xuống `Repository`/`CrudRepository` khi muốn kiểm soát API, hoặc bổ sung executor khi có nhu cầu tìm kiếm cụ thể.
