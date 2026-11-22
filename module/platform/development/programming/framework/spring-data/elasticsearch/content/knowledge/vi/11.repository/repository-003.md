# Quét Repository với @EnableElasticsearchRepositories

Spring Data Elasticsearch tạo repository bean bằng cách tìm các interface repository trong những package được cấu hình, sau đó tạo proxy để thực hiện các thao tác đọc, ghi và truy vấn Elasticsearch. Annotation @EnableElasticsearchRepositories bật cơ chế quét này trong một application context và cho biết Spring cần tìm repository ở đâu.

Đây là bước cấu hình quan trọng khi ứng dụng dùng ElasticsearchRepository hoặc một interface kế thừa các abstraction repository của Spring Data. Nếu package scan sai, ứng dụng có thể khởi động nhưng không có bean repository để inject, hoặc một số repository không được đăng ký như mong muốn.

Bài này giải thích cách hoạt động của repository scanning, cách chọn package bằng basePackages và basePackageClasses, cách xử lý repository lồng nhau, mối quan hệ với Spring Boot auto-configuration, cách cấu hình nhiều Elasticsearch template và cách chẩn đoán lỗi quét repository.

## 1. Repository scanning là gì?

Một repository của Spring Data Elasticsearch thường được khai báo dưới dạng interface:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Interface này mô tả thao tác dữ liệu ở mức ứng dụng. Spring Data tạo một implementation proxy khi application context khởi tạo. Bạn có thể inject interface đó vào service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Product findById(String id) {
        return productRepository.findById(id).orElse(null);
    }
}
~~~

Không cần tự viết class ProductRepositoryImpl chỉ để triển khai các method cơ bản của ElasticsearchRepository. Spring Data cung cấp repository factory để tạo proxy và kết nối nó với ElasticsearchOperations tương ứng.

Để tạo proxy, Spring phải tìm thấy interface repository. Quá trình này được gọi là **repository scanning**. Annotation @EnableElasticsearchRepositories đăng ký cấu hình cần thiết để:

1. Xác định các package cần quét.
2. Tìm interface phù hợp với repository abstraction.
3. Đọc domain type và ID type của repository.
4. Tạo repository factory bean và proxy tương ứng.
5. Kết nối repository với Elasticsearch template/operations đã cấu hình.

Luồng khái quát:

~~~text
@Configuration
    |
    v
@EnableElasticsearchRepositories
    |
    v
Chọn package cần quét
    |
    v
Tìm interface repository
    |
    v
RepositoryFactoryBean
    |
    v
Tạo repository proxy
    |
    v
Inject vào service/controller
    |
    v
ElasticsearchOperations / ElasticsearchTemplate
    |
    v
Elasticsearch cluster
~~~

Repository scanning chỉ là bước đăng ký bean. Nó không tự bảo đảm Elasticsearch đang chạy, index đã tồn tại hay mapping của document đúng. Những phần đó thuộc cấu hình client, mapping và lifecycle của index.

## 2. Khai báo @EnableElasticsearchRepositories

Annotation thuộc package:

~~~java
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;
~~~

Có thể đặt trên một class cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories
public class ElasticsearchRepositoryConfig {
}
~~~

Khi không chỉ định package rõ ràng, Spring Data sử dụng package của class cấu hình làm điểm bắt đầu quét. Các package con cũng được xem xét theo cơ chế scan của repository infrastructure.

Ví dụ cấu trúc:

~~~text
com.example.catalog
    |
    +-- CatalogApplication.java
    |
    +-- config
    |     +-- ElasticsearchRepositoryConfig.java
    |
    +-- repository
    |     +-- ProductRepository.java
    |     +-- CategoryRepository.java
    |
    +-- service
          +-- ProductService.java
~~~

Nếu class cấu hình nằm trong com.example.catalog.config nhưng repository ở com.example.catalog.repository, package mặc định của class cấu hình có thể không bao phủ package repository nằm bên cạnh. Vì vậy, trong ứng dụng có cấu trúc package rõ ràng, nên khai báo phạm vi quét tường minh.

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository"
)
public class ElasticsearchRepositoryConfig {
}
~~~

Khi đó Spring tìm repository trong package được chỉ định và các package con của nó.

## 3. Chọn package bằng basePackages

Thuộc tính basePackages nhận một hoặc nhiều tên package dạng String.

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = {
        "com.example.catalog.repository",
        "com.example.inventory.repository"
    }
)
public class ElasticsearchRepositoryConfig {
}
~~~

Cách này phù hợp khi repository được chia thành nhiều module hoặc package theo domain.

Có thể dùng thuộc tính value như một alias của basePackages:

~~~java
@EnableElasticsearchRepositories(
    value = "com.example.catalog.repository"
)
~~~

Nên chọn một cách khai báo thống nhất trong project để người đọc dễ nhận ra phạm vi quét.

### 3.1. Package cha và package con

Nếu chỉ định package cha:

~~~java
@EnableElasticsearchRepositories(
    basePackages = "com.example"
)
~~~

Spring có thể tìm repository trong nhiều package con thuộc vùng đó. Điều này tiện khi ứng dụng nhỏ, nhưng có thể vô tình quét repository của module không liên quan khi hệ thống phát triển.

Ví dụ:

~~~text
com.example
    +-- catalog
    |     +-- repository
    +-- inventory
    |     +-- repository
    +-- billing
          +-- repository
~~~

Quét toàn bộ com.example có thể đăng ký cả repository catalog, inventory và billing. Nếu mỗi module dùng Elasticsearch template hoặc cluster khác nhau, phạm vi quét quá rộng có thể khiến repository được gắn nhầm cấu hình hoặc tạo bean trùng lặp.

Với ứng dụng lớn, nên chỉ định các package repository cụ thể cho từng cấu hình.

### 3.2. Lưu ý về tên package

Giá trị basePackages là tên package Java, không phải đường dẫn thư mục hay tên class.

Đúng:

~~~java
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository"
)
~~~

Sai:

~~~java
@EnableElasticsearchRepositories(
    basePackages = "src/main/java/com/example/catalog/repository"
)
~~~

Không thêm đuôi .java và không dùng dấu gạch chéo thư mục.

## 4. Chọn package bằng basePackageClasses

Dùng chuỗi package có thể gặp lỗi khi refactor hoặc đổi tên package. Thuộc tính basePackageClasses cho phép chọn package thông qua một class marker.

Ví dụ tạo class rỗng trong package repository:

~~~java
package com.example.catalog.repository;

public final class CatalogRepositoryMarker {
    private CatalogRepositoryMarker() {
    }
}
~~~

Sau đó cấu hình:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackageClasses = CatalogRepositoryMarker.class
)
public class ElasticsearchRepositoryConfig {
}
~~~

Spring lấy package chứa CatalogRepositoryMarker làm package gốc để quét. Class marker không phải repository và không được tạo bean repository; nó chỉ giúp chỉ định package bằng kiểu Java.

Có thể chỉ định nhiều marker:

~~~java
@EnableElasticsearchRepositories(
    basePackageClasses = {
        CatalogRepositoryMarker.class,
        InventoryRepositoryMarker.class
    }
)
~~~

Cách này có các lợi ích:

- IDE hỗ trợ điều hướng tới class marker.
- Refactor package có thể được công cụ Java cập nhật tham chiếu.
- Không phải duy trì tên package dưới dạng chuỗi.
- Tránh lỗi đánh máy trong cấu hình.

Nếu project không muốn tạo class marker riêng, có thể dùng một repository interface hoặc class đã tồn tại trong package làm marker. Tuy nhiên, class marker chuyên dụng thường làm ý định cấu hình rõ hơn.

## 5. Repository scanning khác component scanning như thế nào?

Đây là hai cơ chế khác nhau và thường bị nhầm lẫn.

| Cơ chế | Mục tiêu | Ví dụ |
|---|---|---|
| @ComponentScan | Tìm component, service, controller và configuration bean | @Service, @Component, @Controller |
| @EnableElasticsearchRepositories | Tìm interface repository của Spring Data Elasticsearch | ElasticsearchRepository |
| Mapping metadata | Mô tả cách entity Java ánh xạ thành document và field | @Document, @Id, @Field |

Ví dụ:

~~~java
@Configuration
@ComponentScan(basePackages = "com.example.catalog.service")
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository"
)
public class CatalogConfig {
}
~~~

Trong cấu hình trên:

- ComponentScan tìm các service/component trong package service.
- EnableElasticsearchRepositories tìm các repository interface trong package repository.
- Entity Product được dùng làm domain type của repository và được Spring Data mapping context xử lý khi cần.

Đưa package entity vào basePackages của EnableElasticsearchRepositories không làm entity trở thành repository. Tương tự, ComponentScan không thay thế việc đăng ký repository infrastructure.

Trong ứng dụng Spring Boot, @SpringBootApplication đã bao gồm component scanning cho package gốc và các package con. Repository scanning được xử lý bởi auto-configuration của Spring Data khi điều kiện phù hợp. Nếu ứng dụng dùng cấu hình repository riêng, cần xác định rõ vùng package và tránh đăng ký cùng repository hai lần.

## 6. Spring Boot và khi nào cần khai báo annotation tường minh?

Với một ứng dụng Spring Boot thông thường, class chính thường nằm ở package gốc:

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

Các repository trong package con thường được Spring Boot và Spring Data auto-configuration phát hiện mà không cần tự thêm @EnableElasticsearchRepositories.

Ví dụ:

~~~text
com.example.catalog
    +-- CatalogApplication.java
    +-- repository
    |     +-- ProductRepository.java
    +-- service
    |     +-- ProductService.java
    +-- document
          +-- Product.java
~~~

Nếu repository nằm ngoài package gốc, hoặc cần chia repository theo các Elasticsearch template khác nhau, cấu hình tường minh có thể cần thiết.

Ví dụ:

~~~java
@SpringBootApplication
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.search.repository"
)
public class CatalogApplication {
}
~~~

Không nên thêm annotation chỉ vì muốn "chắc chắn" nếu Boot đã cấu hình repository phù hợp. Một cấu hình explicit không cần thiết có thể tạo ra vùng quét chồng lấn với auto-configuration hoặc một cấu hình khác.

Khi gặp lỗi không tìm thấy repository bean, hãy kiểm tra package gốc của @SpringBootApplication, package repository, điều kiện auto-configuration và cấu hình EnableElasticsearchRepositories đang có trước khi thêm cấu hình mới.

## 7. Repository nào được tìm thấy?

Spring Data tìm các interface repository phù hợp với repository infrastructure. Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Ở đây:

- Product là domain type.
- String là kiểu ID.
- ElasticsearchRepository cung cấp các thao tác CRUD và tìm kiếm cơ bản.
- Spring tạo proxy khi repository được phát hiện trong package scan.

Một interface chỉ khai báo method Java tùy ý mà không kế thừa repository abstraction phù hợp sẽ không tự động trở thành Spring Data repository.

Có thể tạo base repository dùng chung cho nhiều domain:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

@NoRepositoryBean
public interface BaseSearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {

    // Shared method declarations
}
~~~

Sau đó:

~~~java
public interface ProductRepository
        extends BaseSearchRepository<Product, String> {
}
~~~

@NoRepositoryBean báo cho Spring Data rằng BaseSearchRepository là interface cơ sở, không được tạo repository proxy trực tiếp. Các interface cụ thể như ProductRepository vẫn được phát hiện và đăng ký.

Nếu quên @NoRepositoryBean trên một generic base interface, Spring có thể cố tạo repository cho interface chưa có domain type cụ thể và dẫn tới lỗi khởi tạo.

## 8. Repository lồng nhau và considerNestedRepositories

Thông thường repository interface được đặt trực tiếp trong package hoặc package con. Một số project có thể khai báo repository bên trong class khác:

~~~java
public class SearchRepositories {

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {
    }
}
~~~

Repository lồng nhau không được xem xét theo mặc định trong một số cấu hình scanning. Nếu muốn phát hiện chúng, có thể bật:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog",
    considerNestedRepositories = true
)
public class ElasticsearchRepositoryConfig {
}
~~~

Thuộc tính considerNestedRepositories mặc định là false. Chỉ bật khi project thực sự tổ chức repository theo kiểu nested interface và phiên bản Spring Data đang dùng hỗ trợ cách khai báo này.

Trong đa số ứng dụng, đặt repository thành top-level interface trong package repository giúp cấu trúc dễ hiểu và thuận tiện hơn khi tìm kiếm, kiểm thử và refactor.

## 9. Lọc repository bằng includeFilters và excludeFilters

Trong trường hợp package chứa nhiều interface và chỉ một nhóm cần được đăng ký, annotation cung cấp cơ chế include/exclude filter theo component scan filter.

Ví dụ lọc theo annotation tùy chỉnh:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface CatalogSearchRepository {
}
~~~

Đánh dấu repository:

~~~java
@CatalogSearchRepository
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Cấu hình filter:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = CatalogSearchRepository.class
    )
)
public class ElasticsearchRepositoryConfig {
}
~~~

Ví dụ trên cần các import Spring tương ứng cho ComponentScan và FilterType. Filter chỉ có ý nghĩa trong phạm vi scan repository này. Khi dùng includeFilters, hãy hiểu rõ cách filter tương tác với quy tắc nhận diện repository của phiên bản Spring Data đang dùng; không nên dùng filter để thay thế việc kế thừa repository abstraction.

Trong nhiều dự án, package riêng cho repository đã đủ rõ ràng và không cần filter. Chỉ dùng filter khi cấu trúc package thực sự cần phân loại repository.

## 10. Kết nối repository với ElasticsearchOperations

Repository proxy cần một đối tượng thao tác Elasticsearch để gửi request tới cluster. Spring Data Elasticsearch cung cấp abstraction ElasticsearchOperations và các implementation template tương ứng.

Trong cấu hình đơn giản, Spring Boot có thể tự tạo client và template dựa trên cấu hình ứng dụng. Repository được scan sẽ sử dụng template mặc định mà repository infrastructure chọn.

Nếu có nhiều template, cần chỉ rõ repository nào dùng template nào.

Ví dụ:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    elasticsearchTemplateRef = "catalogElasticsearchTemplate"
)
public class CatalogRepositoryConfig {
}
~~~

Trong cấu hình này, bean tên catalogElasticsearchTemplate phải tồn tại và là template/operations phù hợp với API mà phiên bản Spring Data Elasticsearch yêu cầu.

Nếu có hai cluster:

~~~text
catalog repository
      |
      v
catalogElasticsearchTemplate
      |
      v
Catalog Elasticsearch cluster

audit repository
      |
      v
auditElasticsearchTemplate
      |
      v
Audit Elasticsearch cluster
~~~

Có thể tách package và cấu hình:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    elasticsearchTemplateRef = "catalogElasticsearchTemplate"
)
public class CatalogRepositoryConfig {
}

@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.audit.repository",
    elasticsearchTemplateRef = "auditElasticsearchTemplate"
)
public class AuditRepositoryConfig {
}
~~~

Điều kiện quan trọng:

- Hai package repository phải được phân tách rõ.
- Hai bean template phải được khai báo và khởi tạo thành công.
- Mỗi template phải được cấu hình đúng Elasticsearch client/cluster.
- Không để hai cấu hình scan chồng lấn cùng repository interface.
- Mapping của từng domain phải tương thích với index ở cluster tương ứng.

Tên thuộc tính tham chiếu template và các kiểu bean được chấp nhận cần được đối chiếu với phiên bản Spring Data Elasticsearch trong project. Một số thế hệ client có cách cấu hình template khác nhau; không sao chép cấu hình từ phiên bản khác mà chưa kiểm tra dependency.

## 11. Repository implementation tùy chỉnh

Repository scanning không chỉ tạo proxy cho method có sẵn. Spring Data cũng có cơ chế ghép custom repository fragment hoặc implementation theo quy ước tên.

Ví dụ interface:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchExtension {
}
~~~

Fragment interface:

~~~java
public interface ProductSearchExtension {
    List<Product> findFeaturedProducts();
}
~~~

Implementation:

~~~java
public class ProductSearchExtensionImpl
        implements ProductSearchExtension {

    private final ElasticsearchOperations operations;

    public ProductSearchExtensionImpl(
            ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> findFeaturedProducts() {
        // Build query and call ElasticsearchOperations
        return List.of();
    }
}
~~~

Spring Data kết hợp fragment implementation với repository proxy theo quy ước đặt tên và cơ chế fragment discovery. Hãy đặt implementation trong package mà repository infrastructure có thể tìm thấy và dùng hậu tố đúng theo cấu hình repositoryImplementationPostfix nếu đã thay đổi hậu tố mặc định.

Nếu repository được scan nhưng gọi custom method báo lỗi không có implementation, hãy kiểm tra tên interface fragment, tên class implementation, package, constructor dependency và hậu tố implementation.

Không nên tự tạo một bean ProductRepositoryImpl rồi mong Spring tự thay thế toàn bộ repository proxy. Với custom behavior, dùng repository fragment theo cơ chế Spring Data để phần CRUD chuẩn vẫn hoạt động.

## 12. Query method và repository scanning

Sau khi interface được phát hiện, Spring Data đọc các method khai báo để tạo query hoặc gắn query đã khai báo.

Ví dụ:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findBySku(String sku);

    List<Product> findByActiveTrue();

    List<Product> findByPriceInCentsGreaterThan(Long minPrice);
}
~~~

Các method query được phân tích trong quá trình tạo repository. Vì vậy repository có thể được phát hiện nhưng application context vẫn lỗi nếu tên property trong method không hợp lệ, kiểu domain không ánh xạ được hoặc query khai báo sai.

Có thể chọn query lookup strategy trong cấu hình repository nếu cần kiểm soát cách Spring Data tìm query cho method. Các chế độ phổ biến của Spring Data gồm:

- CREATE: tạo query từ tên method.
- USE_DECLARED_QUERY: yêu cầu query được khai báo rõ.
- CREATE_IF_NOT_FOUND: ưu tiên query khai báo, nếu không có thì suy ra từ tên method.

Hỗ trợ cụ thể và hành vi cho từng loại query phụ thuộc Spring Data Elasticsearch version. Nếu startup fail tại repository method, hãy đọc phần root cause thay vì chỉ kết luận package scan sai.

## 13. Tổ chức package cho ứng dụng lớn

Với ứng dụng chia module, nên tổ chức package theo trách nhiệm và cluster đích:

~~~text
com.example
    |
    +-- CatalogApplication.java
    |
    +-- catalog
    |     +-- document
    |     |     +-- Product.java
    |     +-- repository
    |     |     +-- ProductRepository.java
    |     +-- service
    |
    +-- audit
          +-- document
          +-- repository
          |     +-- AuditEventRepository.java
          +-- service
~~~

Cấu hình có thể tách theo từng vùng:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository"
)
public class CatalogElasticsearchRepositories {
}

@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.audit.repository"
)
public class AuditElasticsearchRepositories {
}
~~~

Nếu hai nhóm dùng cùng template mặc định, có thể không cần khai báo template reference riêng. Nếu chúng dùng cluster khác nhau, cần chỉ rõ template reference cho từng nhóm.

Không nên đặt mọi repository trong một package toàn cục rồi dùng nhiều cấu hình scan rộng. Điều này làm khó xác định repository thuộc cluster nào và dễ gây đăng ký trùng.

## 14. Các lỗi thường gặp khi quét Repository

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| No qualifying bean of type ProductRepository | Repository chưa được scan hoặc không được đăng ký | Kiểm tra package cấu hình, basePackages và repository interface |
| Repository bean không xuất hiện | Interface không kế thừa repository abstraction phù hợp | Kiểm tra extends ElasticsearchRepository hoặc Repository tương ứng |
| Chỉ một số repository được phát hiện | Package scan quá hẹp hoặc nested repository bị bỏ qua | Kiểm tra package, package con và considerNestedRepositories |
| No bean named catalogElasticsearchTemplate | Template reference sai hoặc bean chưa khai báo | Kiểm tra tên bean và cấu hình ElasticsearchOperations |
| Bean definition override/conflict | Hai cấu hình scan chồng lấn cùng repository | Tách package và kiểm tra các annotation EnableElasticsearchRepositories |
| Startup lỗi khi tạo repository proxy | Domain type, ID type hoặc query method không hợp lệ | Đọc root cause của repository factory |
| Custom method báo thiếu implementation | Fragment implementation không được phát hiện | Kiểm tra tên, package và hậu tố Impl |
| Repository kết nối nhầm cluster | Template reference hoặc bean mặc định không đúng | Xem cấu hình repository và template được inject |
| Entity mapping lỗi | Annotation hoặc metadata của domain không hợp lệ | Kiểm tra @Document, @Id, @Field và mapping context |

### 14.1. Chẩn đoán NoSuchBeanDefinitionException

Nếu service báo:

~~~text
NoSuchBeanDefinitionException:
No qualifying bean of type 'ProductRepository' available
~~~

Hãy kiểm tra theo thứ tự:

1. ProductRepository có phải interface không?
2. Interface có kế thừa ElasticsearchRepository hoặc repository abstraction phù hợp không?
3. Package chứa interface có nằm trong vùng quét không?
4. Class cấu hình EnableElasticsearchRepositories có được nạp vào application context không?
5. Spring Boot auto-configuration có bị loại trừ hoặc tắt không?
6. Có lỗi startup trước đó khiến repository factory không tạo được bean không?

Đừng chỉ nhìn exception cuối cùng. Nếu repository factory gặp lỗi khi khởi tạo, nguyên nhân thực tế có thể nằm trong nested cause như mapping, query method, template hoặc client.

### 14.2. Chẩn đoán repository được scan hai lần

Nếu hai cấu hình cùng quét package com.example.catalog.repository, Spring có thể cố đăng ký cùng repository từ hai repository configuration source. Kết quả có thể là bean trùng tên hoặc một cấu hình bị xung đột.

Cách xử lý là phân chia package không chồng lấn hoặc chỉ giữ một cấu hình chịu trách nhiệm cho repository đó. Nếu mục tiêu là chọn template khác nhau, hãy gán mỗi package repository cho đúng cấu hình tương ứng.

## 15. Kiểm tra repository scanning bằng integration test

Một kiểm thử Spring context có thể xác nhận repository bean được đăng ký:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ProductRepositoryConfigurationTest {

    @Autowired
    ProductRepository productRepository;

    @Test
    void shouldRegisterProductRepository() {
        assertThat(productRepository).isNotNull();
    }
}
~~~

Test này xác nhận repository có thể được inject trong context. Nó chưa chứng minh Elasticsearch có thể nhận request hoặc mapping đúng.

Để xác nhận repository hoạt động, cần một integration test với Elasticsearch test instance và thực hiện ít nhất một thao tác ghi/đọc:

~~~java
@Test
void shouldSaveAndFindProduct() {
    Product product = new Product("P-1001", "Wireless Mouse");

    productRepository.save(product);

    Product actual = productRepository.findById("P-1001")
        .orElseThrow();

    assertThat(actual.getName()).isEqualTo("Wireless Mouse");
}
~~~

Dùng index riêng cho test và mapping được tạo rõ ràng. Nếu test dùng Search API để kiểm tra query, cần chú ý refresh behavior của Elasticsearch. Get theo ID và Search không có cùng thời điểm hiển thị dữ liệu.

## 16. Lưu ý khi dùng nhiều application context hoặc module

Một số ứng dụng có nhiều configuration class, test slice hoặc module Spring riêng. Khi đó repository scan có thể khác nhau giữa runtime và test.

Ví dụ:

- Application chính có @EnableElasticsearchRepositories.
- Test dùng @DataElasticsearchTest hoặc một context rút gọn.
- Module con khai báo configuration riêng.
- Một test chỉ import một số configuration class.

Nếu repository hoạt động khi chạy ứng dụng nhưng không xuất hiện trong test, hãy kiểm tra context test có import repository configuration tương ứng hay không. Ngược lại, nếu test pass nhưng app không khởi động, kiểm tra package scan và auto-configuration thực tế của application.

Không nên khắc phục bằng cách thêm @Import tràn lan mà chưa xác định configuration class nào chịu trách nhiệm. Một cấu trúc rõ ràng giúp mỗi repository được đăng ký đúng một lần trong đúng application context.

## 17. Bảng tra cứu nhanh

| Nhu cầu | Cấu hình |
|---|---|
| Bật repository scanning cơ bản | @EnableElasticsearchRepositories |
| Chỉ định package bằng tên | basePackages |
| Chỉ định package bằng class marker | basePackageClasses |
| Quét repository lồng nhau | considerNestedRepositories = true |
| Chọn template cho một nhóm repository | elasticsearchTemplateRef |
| Dùng repository base interface chung | @NoRepositoryBean trên base interface |
| Tìm service/component | @ComponentScan hoặc @SpringBootApplication |
| Kiểm tra repository đã được tạo | Inject repository trong Spring context test |
| Kiểm tra repository thực sự truy cập Elasticsearch | Integration test ghi và đọc document |

@EnableElasticsearchRepositories chịu trách nhiệm phát hiện và đăng ký các interface repository trong package được chọn. Hãy dùng basePackages khi cần khai báo package rõ ràng, basePackageClasses khi muốn cấu hình an toàn khi refactor, và tách vùng scan khi có nhiều template hoặc nhiều cluster. Trong Spring Boot, kiểm tra auto-configuration hiện có trước khi thêm annotation tường minh. Khi repository không xuất hiện hoặc khởi tạo lỗi, xác định xem vấn đề nằm ở package scan, repository abstraction, template, domain mapping hay query method rồi xử lý đúng tầng.

