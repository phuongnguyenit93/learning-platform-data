# Khai báo bằng @RepositoryDefinition

## Mục tiêu bài học

Trong Spring Data, một interface thường được nhận diện là repository thông qua việc kế thừa `Repository<T, ID>` hoặc một interface dẫn xuất. Spring Data Commons còn cung cấp một cách khai báo khác: đặt annotation `@RepositoryDefinition` lên interface và chỉ rõ kiểu domain cùng kiểu định danh.

Cách khai báo này phù hợp khi bạn muốn mô tả repository mà không đưa một interface Spring Data vào hệ kế thừa của chính interface đó. Bạn vẫn có thể chọn các method CRUD, khai báo derived queries và sử dụng những khả năng mà module lưu trữ hỗ trợ.

Bài học thuộc chương **Giao diện repository** của module SPRING_DATA_COMMONS. Sau bài học, bạn có thể:

- Khai báo đúng `domainClass` và `idClass`.
- Thiết kế một repository chỉ công khai những thao tác cần thiết.
- Phân biệt metadata repository với mapping và cơ chế thực thi truy vấn.
- Giải thích khác biệt giữa `@RepositoryDefinition`, `@Repository` và việc kế thừa `Repository`.
- Nhận diện các lỗi thường gặp khi kết hợp annotation với scanning, method tùy biến và nhiều module lưu trữ.

## 1. Hai cách cung cấp metadata cho repository

### 1.1. Cách dựa vào hệ kế thừa

Một interface có thể kế thừa marker interface của Spring Data:

~~~java
import org.springframework.data.repository.Repository;

public interface ProductLookupRepository
        extends Repository<Product, Long> {
}
~~~

Hai tham số kiểu cho hạ tầng biết repository quản lý `Product` với ID kiểu `Long`.

Bản thân `Repository` không tự khai báo toàn bộ method CRUD. Nếu muốn những method đó xuất hiện trong API, bạn cần khai báo chúng hoặc kế thừa một interface cung cấp chúng, chẳng hạn `CrudRepository`.

### 1.2. Cách dựa vào RepositoryDefinition

Thay vì kế thừa `Repository`, bạn có thể khai báo:

~~~java
import org.springframework.data.repository.RepositoryDefinition;

@RepositoryDefinition(
    domainClass = Product.class,
    idClass = Long.class
)
public interface ProductLookupRepository {
}
~~~

Annotation cung cấp metadata cần thiết về domain và ID. Interface ở đây không có mệnh đề `extends Repository<...>`.

Hai đoạn trên là hai phương án thay thế cho cùng một interface, không phải hai file có cùng tên cần đặt cạnh nhau trong dự án.

**Điểm cốt lõi:** `@RepositoryDefinition` thay thế cách xác định metadata domain/ID qua marker interface. Annotation không tự thêm những method mà bạn chưa khai báo và không tự cung cấp một engine truy cập dữ liệu.

## 2. Ý nghĩa của domainClass và idClass

| Thuộc tính | Giá trị trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| `domainClass` | `Product.class` | Kiểu domain mà repository quản lý. |
| `idClass` | `Long.class` | Kiểu định danh của domain đó. |

Hai thuộc tính cần được khai báo rõ ràng. Chúng mô tả kiểu Java, không phải tên bảng, tên collection hay tên bean.

Ví dụ:

~~~java
@RepositoryDefinition(
    domainClass = Product.class,
    idClass = Long.class
)
public interface ProductLookupRepository {
    Optional<Product> findById(Long id);
}
~~~

Để khai báo nhất quán, cần đối chiếu cả ba phần:

1. Domain được chỉ định là `Product`.
2. Mapping của `Product` xác định ID kiểu `Long`.
3. Method tìm theo ID nhận tham số `Long` và trả dữ liệu phù hợp với `Product`.

Annotation không tạo ràng buộc generic ở mức trình biên dịch giữa tất cả những phần này. Nếu đổi `idClass` thành `String.class` nhưng vẫn để ID entity và method là `Long`, mã có thể vẫn vượt qua kiểm tra cú pháp Java trong khi metadata repository đã mâu thuẫn.

Không nên trông chờ một loại lỗi duy nhất sẽ luôn xuất hiện ngay lúc khởi động khi khai báo sai kiểu. Thời điểm phát hiện còn phụ thuộc module, method được sử dụng và cấu hình khởi tạo.

### idClass không phải cấu hình sinh ID

`idClass = Long.class` không có nghĩa ID được tự tăng, cũng không có nghĩa Commons tự tạo ID cho đối tượng.

Với JPA, cơ chế sinh ID được quyết định qua mapping như `@GeneratedValue`. Với một module khác, kiểu và cơ chế ID có thể khác.

Thuộc tính `idClass` của `@RepositoryDefinition` cũng không thay thế annotation JPA `@IdClass` cho định danh tổng hợp. Nếu domain có ID tổng hợp, phải cấu hình mapping tương ứng và khai báo đúng kiểu ID mà repository thực sự sử dụng.

## 3. Ví dụ domain dùng với JPA

Để làm rõ cách metadata và mapping phối hợp, phần thực hành chọn Spring Data JPA. Giả định dự án đã có dependency JPA, datasource và bộ phiên bản tương thích. Mỗi lớp public bên dưới được đặt trong file cùng tên.

File `domain/Product.java`:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
    }

    public Product(String name, boolean active) {
        this.name = name;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Các annotation import từ `jakarta.persistence` thuộc JPA. Chúng mô tả entity, bảng, cột và định danh trong ví dụ này.

`@RepositoryDefinition` sẽ được đặt lên interface repository, không thay thế `@Entity` trên domain. Nếu chỉ khai báo repository metadata mà thiếu mapping hợp lệ cho công nghệ đang dùng, repository vẫn có thể không hoạt động.

Trong ví dụ JPA/H2 thông thường, có thể dùng chiến lược IDENTITY như trên. Khi chọn cơ sở dữ liệu hoặc module khác, cần chọn mapping và chiến lược ID phù hợp; không suy ra chúng từ annotation repository.

## 4. Công khai một API chỉ có các thao tác đọc

File `repository/ProductLookupRepository.java`:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Product;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.RepositoryDefinition;

@RepositoryDefinition(
    domainClass = Product.class,
    idClass = Long.class
)
public interface ProductLookupRepository {

    Optional<Product> findById(Long id);

    boolean existsById(Long id);

    Page<Product> findByActiveTrue(Pageable pageable);
}
~~~

Interface này có ba method và không kế thừa toàn bộ API CRUD:

| Method | Cách hiểu |
| --- | --- |
| `findById(Long)` | Tìm một sản phẩm theo định danh; dùng hợp đồng method CRUD phù hợp. |
| `existsById(Long)` | Kiểm tra sự tồn tại theo định danh; dùng hợp đồng method CRUD phù hợp. |
| `findByActiveTrue(Pageable)` | Truy vấn suy ra từ tên method, có yêu cầu phân trang. |

Bên gọi có thể tìm sản phẩm và lấy trang sản phẩm đang hoạt động. Bên gọi không thể gọi `save`, `deleteById` hay `deleteAll` thông qua kiểu `ProductLookupRepository` vì chúng không xuất hiện trong API đã khai báo.

Đây là **sự giới hạn API ở mức kiểu Java**. Nó không tự tạo một chính sách cấm ghi trên toàn bộ hệ thống. Một thành phần khác vẫn có thể ghi dữ liệu qua repository khác, EntityManager, template hoặc kết nối cơ sở dữ liệu mà nó được phép sử dụng.

Cũng không nên suy ra rằng entity trả về trở thành bất biến chỉ vì repository chỉ công khai thao tác đọc. Trạng thái quản lý entity và tác động của việc thay đổi nó vẫn phụ thuộc công nghệ cùng ranh giới transaction.

## 5. Những method này được thực thi bằng cách nào?

Annotation không yêu cầu lập trình viên tự tạo implementation cho mọi method. Hạ tầng repository của module sẽ xem method thuộc nhóm xử lý nào.

~~~mermaid
flowchart TD
    A["Interface có RepositoryDefinition"] --> B["Metadata domain và ID"]
    B --> C["Factory repository của module lưu trữ"]
    C --> D["Method CRUD khớp hợp đồng"]
    C --> E["Query method"]
    C --> F["Hành vi tùy biến có implementation"]
    D --> G["Triển khai cơ sở của module"]
    E --> H["Tạo hoặc lấy truy vấn theo cơ chế của module"]
    F --> I["Phần triển khai tùy biến đã đăng ký"]
~~~

Sơ đồ thể hiện những nhóm trách nhiệm chính, không phải mọi interceptor hoặc bước xử lý nội bộ.

### 5.1. Method CRUD được khai báo chọn lọc

Khi một method được khai báo phù hợp với hợp đồng CRUD mà module cung cấp, hạ tầng có thể chuyển lời gọi đến triển khai cơ sở của module.

Ví dụ, khai báo:

~~~java
Optional<Product> findById(Long id);
~~~

không cần một lớp `ProductLookupRepositoryImpl` chỉ để triển khai lại thao tác tìm theo ID.

Khi sao chép method CRUD, cách dễ kiểm soát là giữ chữ ký phù hợp với hợp đồng Spring Data đang dùng. Không tự đổi tên method hoặc tạo kiểu trả về bất kỳ rồi mặc định rằng factory sẽ nhận ra cùng một thao tác.

Một số kiểu trả về tương thích được hỗ trợ theo cơ chế repository, nhưng cần xét đúng method và module. Việc Java cho phép bạn khai báo một method không đồng nghĩa hạ tầng có thể thực thi nó theo ý định.

### 5.2. Derived query vẫn là derived query

Method:

~~~java
Page<Product> findByActiveTrue(Pageable pageable);
~~~

diễn đạt điều kiện thuộc tính `active` bằng `true`. Trong ví dụ, `active` tồn tại trên entity, còn `Pageable` là tham số điều khiển phân trang.

Commons cung cấp hạ tầng chung như phân tích method và các kiểu phân trang. Module JPA chịu trách nhiệm tạo truy vấn theo mapping JPA. Khi chuyển sang kho dữ liệu khác, cần xác nhận module đó hỗ trợ dạng truy vấn và phân trang tương ứng.

`@RepositoryDefinition` không mở rộng tập toán tử truy vấn của một module và không làm một method sai tên thuộc tính trở nên hợp lệ.

### 5.3. Một method nghiệp vụ bất kỳ chưa có implementation

Giả sử thêm:

~~~java
void rebuildCatalogIndex();
~~~

Việc đặt `@RepositoryDefinition` không tự tạo thuật toán xây dựng lại chỉ mục danh mục.

Nếu method không được nhận diện là thao tác cơ sở, không có truy vấn khai báo phù hợp và không có phần triển khai tùy biến, repository có thể thất bại khi tạo hoặc khi phân giải method. Thời điểm báo lỗi có thể bị trì hoãn theo cấu hình khởi tạo.

Với hành vi tùy biến, dùng cơ chế như repository fragment và cung cấp implementation tương ứng. Với truy vấn khai báo, sử dụng annotation hoặc cơ chế query của đúng module; chẳng hạn `@Query` của JPA không phải một annotation truy vấn chung cho mọi kho dữ liệu.

## 6. Inject repository vào service

File `ProductCatalogService.java`:

~~~java
package com.example.catalog;

import com.example.catalog.domain.Product;
import com.example.catalog.repository.ProductLookupRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class ProductCatalogService {

    private final ProductLookupRepository repository;

    public ProductCatalogService(ProductLookupRepository repository) {
        this.repository = repository;
    }

    public Product requireProduct(Long id) {
        return repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy sản phẩm: " + id
            ));
    }

    public Page<Product> findActiveProducts(int page, int size) {
        Pageable request = PageRequest.of(
            page,
            size,
            Sort.by("name").ascending()
                .and(Sort.by("id").ascending())
        );

        return repository.findByActiveTrue(request);
    }
}
~~~

Cách inject và gọi repository không khác về bản chất so với repository khai báo qua hệ kế thừa. Bên gọi phụ thuộc vào interface ứng dụng; Spring Data cung cấp bean repository nếu cấu hình và metadata hợp lệ.

`PageRequest` dùng chỉ số trang bắt đầu từ 0 và yêu cầu kích thước trang dương. Thứ tự theo tên rồi ID giúp phân biệt các sản phẩm có cùng tên; việc duy trì kết quả ổn định khi dữ liệu thay đổi còn phụ thuộc đặc tính truy vấn và kho dữ liệu.

Không cần thêm annotation `@Repository` lên interface chỉ để constructor injection hoạt động. Điều kiện quan trọng là interface đã được hạ tầng repository đúng module phát hiện và đăng ký.

## 7. Điều kiện để interface được đăng ký thành bean

### 7.1. Phải có module lưu trữ cụ thể

Chỉ có dependency `spring-data-commons` để import `@RepositoryDefinition` chưa tạo ra một repository truy cập JPA, MongoDB hoặc cơ sở dữ liệu bất kỳ.

Để ví dụ hoạt động bằng JPA, cần:

- Module Spring Data JPA và các thành phần JPA liên quan.
- Datasource cùng cấu hình persistence phù hợp.
- Entity mapping hợp lệ.
- Cấu hình phát hiện repository bao gồm interface đã khai báo.

Spring Boot starter phù hợp thường giúp cung cấp dependency và cấu hình tự động. Annotation repository không thay thế những điều kiện đó.

### 7.2. Repository phải nằm trong phạm vi scanning

Một cấu trúc package phù hợp với cấu hình Boot thông thường:

~~~text
com.example.catalog
    CatalogApplication
    ProductCatalogService
    domain
        Product
    repository
        ProductLookupRepository
~~~

Lớp ứng dụng có thể khai báo:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Khi repository nằm ở ngoài phạm vi mặc định hoặc ứng dụng cần cấu hình rõ ràng, có thể cấu hình quét repository JPA, ví dụ:

~~~java
package com.example.catalog;

import com.example.catalog.repository.ProductLookupRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
    basePackageClasses = ProductLookupRepository.class
)
public class JpaRepositoryConfiguration {
}
~~~

Đây là ví dụ cấu hình repository tường minh khi cần; không bắt buộc thêm vào mọi ứng dụng Boot đã được tự cấu hình đúng.

`basePackageClasses` xác định package dùng làm mốc quét repository. Nó không tự thay thế cấu hình entity scanning hoặc tạo datasource. Nếu entity cũng nằm ngoài phạm vi mặc định, phải cấu hình phần entity tương ứng.

### 7.3. Không dùng stereotype thay cho repository definition

Một interface chỉ có `@Repository` không tự nhận được implementation repository Spring Data. Component scanning thông thường không tự hiện thực những method abstract của một interface tùy ý.

Điều này khác với việc Spring Data nhận diện một repository candidate, đọc domain/ID metadata và tạo proxy thông qua factory của module.

## 8. Nếu cần thêm thao tác ghi

Bạn có thể chủ động thêm method ghi vào interface, hoặc tạo một interface riêng phục vụ nhu cầu ghi.

Ví dụ một repository ghi:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Product;
import org.springframework.data.repository.RepositoryDefinition;

@RepositoryDefinition(
    domainClass = Product.class,
    idClass = Long.class
)
public interface ProductCommandRepository {

    <S extends Product> S save(S entity);

    void deleteById(Long id);
}
~~~

Chữ ký generic của `save` giữ cách diễn đạt quen thuộc của hợp đồng CRUD: nhận một kiểu con phù hợp và trả lại kiểu đó.

Repository này chỉ công khai những method đã khai báo. Annotation không tự bổ sung `findAll`, `count` hay `saveAll`.

Hai repository đọc và ghi có thể cùng quản lý một domain nếu cấu hình của ứng dụng cho phép, nhưng cách tách đó là quyết định thiết kế API. Không cần tách chúng chỉ vì chọn `@RepositoryDefinition`.

Với `save`, vẫn nên sử dụng đối tượng trả về khi cần trạng thái sau lưu. Với JPA, ranh giới transaction và cơ chế persist/merge vẫn có vai trò như khi dùng repository kế thừa `CrudRepository`. Đổi cách khai báo repository không thay đổi bản chất thao tác lưu.

## 9. So sánh các lựa chọn khai báo

| Lựa chọn | Cách cung cấp domain/ID | Method xuất hiện trong API | Điểm cần cân nhắc |
| --- | --- | --- | --- |
| `extends Repository<Product, Long>` | Qua tham số generic của interface cha. | Những method do bạn hoặc interface cha khác khai báo. | Phù hợp nếu chấp nhận marker interface Spring Data trong hệ kế thừa. |
| `@RepositoryDefinition` | Qua `domainClass` và `idClass`. | Những method do bạn hoặc interface cha ứng dụng khai báo. | Không cần kế thừa marker nhưng vẫn dùng annotation Spring Data. |
| `extends CrudRepository<Product, Long>` | Qua tham số generic. | Có sẵn tập method CRUD của interface này. | Tiện khi muốn công khai tập CRUD tương ứng. |
| `extends JpaRepository<Product, Long>` | Qua hệ interface của Spring Data JPA. | Có API do hệ interface JPA cung cấp. | Gắn với module JPA và các khả năng của nó. |
| Chỉ đặt `@Repository` trên interface tùy ý | Không cung cấp metadata repository Spring Data theo cách này. | Không tự tạo implementation cho method abstract. | Không thay thế marker interface hoặc `@RepositoryDefinition`. |

Hai điểm dễ bỏ sót:

- Chọn `@RepositoryDefinition` không làm interface hoàn toàn độc lập với Spring Data, vì annotation vẫn đến từ Commons.
- Selective API không phải đặc quyền của annotation. Bạn cũng có thể chỉ kế thừa `Repository` rồi khai báo chọn lọc những method cần thiết.

### Khác biệt khi sử dụng generic bound trong mã ứng dụng

Nếu một utility của ứng dụng yêu cầu kiểu tham số phải kế thừa `Repository<?, ?>`, interface chỉ dùng `@RepositoryDefinition` không thỏa generic bound đó ở mức khai báo Java.

Annotation không làm thay đổi quan hệ kế thừa của kiểu. Vì vậy, cần cân nhắc các utility, interface nền hoặc quy ước kiến trúc của dự án trước khi chọn cách khai báo.

Đánh giá theo kiểu interface mà mã ứng dụng sử dụng, không dựa vào chi tiết implementation hoặc tập interface phụ mà một proxy runtime có thể mang theo.

## 10. Tái sử dụng hợp đồng giữa nhiều domain

Hai thuộc tính `domainClass` và `idClass` nhận class literal. Không thể khai báo một annotation tổng quát bằng `T.class` hoặc `ID.class` để nó tự thay đổi theo từng domain.

Một lựa chọn là để interface dùng chung chỉ chứa các chữ ký generic:

~~~java
package com.example.catalog.repository;

import java.util.Optional;

public interface LookupOperations<T, ID> {

    Optional<T> findById(ID id);

    boolean existsById(ID id);
}
~~~

Sau đó interface cụ thể khai báo metadata và kế thừa hợp đồng đó:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Product;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.RepositoryDefinition;

@RepositoryDefinition(
    domainClass = Product.class,
    idClass = Long.class
)
public interface ProductLookupRepository
        extends LookupOperations<Product, Long> {

    Page<Product> findByActiveTrue(Pageable pageable);
}
~~~

Đây là biến thể thay thế cho `ProductLookupRepository` đã khai báo trước đó. Method kế thừa từ `LookupOperations` vẫn là một phần API của repository; annotation không che giấu chúng.

Interface `LookupOperations` ở đây không kế thừa `Repository` và không có `@RepositoryDefinition`, nên không được thiết kế như một repository candidate độc lập theo cơ chế phát hiện thông thường.

Nếu thay sang cách xây dựng base repository có kế thừa `Repository<T, ID>`, annotation `@NoRepositoryBean` thường được dùng để ngăn hạ tầng tạo bean cho interface nền chưa gắn domain cụ thể. `@NoRepositoryBean` có mục đích khác với `@RepositoryDefinition`: một bên loại interface nền khỏi việc tạo repository bean, một bên cung cấp metadata cho một repository.

## 11. Ứng dụng dùng nhiều module lưu trữ

`@RepositoryDefinition` có domain và ID nhưng không có thuộc tính chọn “JPA”, “MongoDB” hay tên datasource. Annotation không tự quyết định kho dữ liệu cho repository.

Khi nhiều module Spring Data cùng được cấu hình, cần đảm bảo interface được module đúng quản lý. Những yếu tố liên quan gồm:

- Phạm vi scanning của từng cấu hình repository.
- Dấu hiệu mapping của domain theo công nghệ lưu trữ.
- Các interface chuyên biệt của module nếu dùng cách kế thừa.
- Cấu hình persistence và transaction manager tương ứng khi ứng dụng có nhiều nguồn dữ liệu.

Interface chỉ dùng `@RepositoryDefinition` không cung cấp dấu hiệu module thông qua hệ kế thừa như một interface trực tiếp mở rộng `JpaRepository`. Hạ tầng có thể cần dựa thêm vào mapping và cấu hình quét.

Ví dụ domain mang `@Entity` là một dấu hiệu liên quan tới JPA, nhưng không nên coi một annotation domain là lời giải cho mọi cấu hình nhiều module. Khi một domain mang dấu hiệu mapping của nhiều công nghệ hoặc nhiều vùng quét chồng nhau, cần làm rõ cấu hình thay vì mong Commons tự đoán ý định.

Khả năng truy vấn, projection, Query by Example hay auditing cũng tiếp tục phụ thuộc mức hỗ trợ và cách tích hợp của từng module. `@RepositoryDefinition` không tự kích hoạt những tính năng đó.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không import được `RepositoryDefinition`. | Dependency chưa đưa Commons vào compile classpath hoặc bộ dependency chưa phù hợp. | Kiểm tra dependency của module ứng dụng và cách quản lý phiên bản. |
| Không inject được repository. | Thiếu module lưu trữ, ngoài vùng quét hoặc metadata không hợp lệ. | Kiểm tra cấu hình tạo repository và package cụ thể. |
| Repository không có method `save` khi viết service. | Interface không khai báo hoặc kế thừa method đó. | Bổ sung đúng hợp đồng nếu API cần ghi, hoặc dùng repository ghi phù hợp. |
| Lỗi tạo query cho một method nghiệp vụ. | Method không phải CRUD phù hợp và chưa có query hay implementation tùy biến. | Thiết kế derived query đúng hoặc cung cấp cơ chế triển khai tương ứng. |
| Method tìm theo ID gặp lỗi kiểu dữ liệu. | `idClass`, mapping ID và chữ ký method không nhất quán. | Đối chiếu cả ba thay vì chỉ sửa tham số method. |
| Nhiều module tranh chấp một repository. | Phạm vi quét chồng nhau hoặc dấu hiệu nhận diện module mơ hồ. | Tách vùng repository và cấu hình module rõ ràng. |
| Đã bỏ method ghi nhưng dữ liệu vẫn bị sửa ở nơi khác. | Việc giới hạn interface không phải giới hạn ghi của toàn hệ thống. | Xem thành phần thực hiện ghi và ranh giới transaction thực tế. |

Thông báo lỗi cụ thể có thể khác giữa module và phiên bản. Đọc nguyên nhân gốc và đối chiếu trách nhiệm của từng thành phần, không mặc định annotation là nguyên nhân của mọi lỗi repository.

## 13. Bài tập vận dụng

Hãy thiết kế repository tra cứu đơn hàng, với domain `Order` có ID `Long`, yêu cầu:

1. Có thể tìm một đơn theo ID.
2. Có thể kiểm tra một đơn có tồn tại hay không.
3. Không công khai API xóa.
4. Không kế thừa một interface Spring Data.

Một khai báo đáp ứng yêu cầu có dạng:

~~~java
import java.util.Optional;
import org.springframework.data.repository.RepositoryDefinition;

@RepositoryDefinition(
    domainClass = Order.class,
    idClass = Long.class
)
public interface OrderLookupRepository {

    Optional<Order> findById(Long id);

    boolean existsById(Long id);
}
~~~

`Order` là domain của bài tập và cần có mapping tương ứng với module lưu trữ mà bạn chọn.

Tự phân tích các thay đổi sau:

| Thay đổi | Hệ quả cần nhận diện |
| --- | --- |
| Thêm `void deleteById(Long id)`. | API Java bắt đầu công khai thao tác xóa; annotation không tự ngăn điều đó. |
| Chỉ đổi `idClass` thành `String.class`. | Metadata mâu thuẫn nếu ID domain vẫn là `Long`. |
| Thêm `void exportReport()` mà không có implementation. | Annotation không tự tạo hành vi xuất báo cáo. |
| Chuyển interface ra ngoài vùng quét. | Repository có thể không còn được đăng ký thành bean. |
| Chuyển từ JPA sang kho dữ liệu khác. | Có thể giữ ý định API, nhưng phải đánh giá mapping, module, ID và khả năng thực thi. |

Tiêu chí của một khai báo đúng là metadata domain/ID nhất quán, API phản ánh đúng nhu cầu, module lưu trữ nhận diện được repository và mỗi method có cơ chế thực thi phù hợp. Khi những điều này rõ ràng, `@RepositoryDefinition` trở thành một lựa chọn khai báo repository có chủ đích trong hệ abstraction chung của Spring Data.