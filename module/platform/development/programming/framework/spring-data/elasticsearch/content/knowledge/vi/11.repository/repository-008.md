# Phân vùng Repository khi nhiều mô-đun Spring Data cùng tồn tại

Một ứng dụng Spring Boot có thể dùng đồng thời nhiều công nghệ lưu trữ, chẳng hạn Spring Data Elasticsearch để tìm kiếm, Spring Data JPA để làm việc với cơ sở dữ liệu quan hệ và Spring Data MongoDB để lưu document. Mỗi mô-đun Spring Data cung cấp repository abstraction và cách tạo repository bean riêng.

Khi nhiều mô-đun Spring Data cùng có mặt trên classpath, Spring Data cần xác định repository interface thuộc store nào. Nếu repository chỉ kế thừa một abstraction chung như `CrudRepository`, hoặc domain class không thể hiện rõ store đích, việc phân loại có thể trở nên mơ hồ. Cách tổ chức an toàn là dùng repository interface đặc thù cho từng store và giới hạn package scanning bằng cấu hình tương ứng.

## 1. Vì sao cần phân vùng Repository?

Giả sử ứng dụng quản lý sản phẩm bằng PostgreSQL và đồng thời xây dựng chức năng tìm kiếm bằng Elasticsearch:

- PostgreSQL lưu dữ liệu nghiệp vụ chuẩn như sản phẩm, tồn kho và đơn hàng.
- Elasticsearch giữ bản sao dữ liệu đã được tối ưu cho tìm kiếm toàn văn, lọc và aggregation.
- Một repository JPA thao tác với entity quan hệ.
- Một repository Elasticsearch thao tác với document tìm kiếm.

Trong ứng dụng chỉ dùng một Spring Data module, một interface đơn giản có thể kế thừa `CrudRepository<T, ID>` và module đó sẽ tạo repository tương ứng. Khi có nhiều module, `CrudRepository` không cho biết repository thuộc JPA, Elasticsearch hay MongoDB.

Spring Data Commons sử dụng chế độ **strict repository configuration** khi phát hiện nhiều store module. Trong chế độ này, Spring Data cần bằng chứng rõ hơn để gán repository cho đúng module.

## 2. Cách Spring Data nhận diện repository thuộc store nào

Có hai tín hiệu chính giúp Spring Data xác định store:

1. Repository kế thừa một interface đặc thù của module, ví dụ `JpaRepository` hoặc `ElasticsearchRepository`.
2. Domain type được repository quản lý mang annotation đặc thù của store, ví dụ `@Entity` của JPA hoặc `@Document` của Elasticsearch.

Ví dụ:

~~~java
public interface ProductJpaRepository
        extends JpaRepository<ProductEntity, Long> {
}
~~~

`JpaRepository` thể hiện rõ repository thuộc Spring Data JPA.

~~~java
public interface ProductSearchRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

`ElasticsearchRepository` thể hiện rõ repository thuộc Spring Data Elasticsearch.

Domain type cũng nên phản ánh store tương ứng:

~~~java
@Entity
@Table(name = "products")
public class ProductEntity {
    // Trường và quan hệ JPA
}

@Document(indexName = "products")
public class ProductDocument {
    // Trường phục vụ tìm kiếm
}
~~~

Khi repository kế thừa abstraction đúng module và domain type mang annotation đúng store, ý định được thể hiện rõ trong code.

## 3. Tổ chức package theo store

Một cấu trúc package dễ hiểu là tách domain model, repository và cấu hình theo từng công nghệ lưu trữ:

~~~text
com.example.catalog
├── CatalogApplication.java
├── jpa
│   ├── entity
│   │   └── ProductEntity.java
│   ├── repository
│   │   └── ProductJpaRepository.java
│   └── config
│       └── JpaRepositoryConfig.java
├── elasticsearch
│   ├── document
│   │   └── ProductDocument.java
│   ├── repository
│   │   └── ProductSearchRepository.java
│   └── config
│       └── ElasticsearchRepositoryConfig.java
└── application
    └── ProductSearchService.java
~~~

Phân vùng như vậy có một số lợi ích:

- Repository nằm trong package của store mà nó sử dụng.
- Cấu hình scanning có thể trỏ tới đúng package.
- Domain model quan hệ và document tìm kiếm có thể có field, mapping và vòng đời riêng.
- Người đọc code dễ nhận ra repository nào truy cập PostgreSQL và repository nào truy cập Elasticsearch.

Package không tự quyết định store nếu interface và domain type không rõ ràng, nhưng nó tạo ranh giới để cấu hình scanning chính xác và tránh quét nhầm repository.

## 4. Dùng repository interface đặc thù của từng module

### 4.1. Repository JPA

Ví dụ entity quan hệ:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class ProductEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;
    private String name;

    // Constructor, getters và setters
}
~~~

Repository JPA kế thừa `JpaRepository`:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductJpaRepository
        extends JpaRepository<ProductEntity, Long> {

    Optional<ProductEntity> findBySku(String sku);
}
~~~

Spring Data JPA tạo implementation cho interface này và sử dụng JPA `EntityManager` cùng persistence unit đã cấu hình.

### 4.2. Repository Elasticsearch

Document tìm kiếm có thể dùng cùng một số dữ liệu nghiệp vụ nhưng được thiết kế theo mapping Elasticsearch:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    // Constructor, getters và setters
}
~~~

Repository Elasticsearch kế thừa `ElasticsearchRepository`:

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductSearchRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findBySku(String sku);
}
~~~

Spring Data Elasticsearch tạo repository sử dụng Elasticsearch operations/client đã cấu hình. `@Id` trong document ánh xạ tới Elasticsearch `_id`; kiểu ID ở generic repository là `String` trong ví dụ này.

JPA và Elasticsearch có hai kiểu ID và hai mapping context khác nhau. Không nên dùng một repository interface kế thừa cả `JpaRepository` và `ElasticsearchRepository`, vì hai module có store operations, query semantics và lifecycle khác nhau.

## 5. Giới hạn package scanning bằng `@Enable...Repositories`

Khi cần kiểm soát rõ repository nào được đăng ký, có thể dùng annotation cấu hình riêng của từng module.

### 5.1. Cấu hình Elasticsearch

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchRepositories;

@Configuration
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.elasticsearch.repository"
)
public class ElasticsearchRepositoryConfig {
}
~~~

`@EnableElasticsearchRepositories` yêu cầu Spring Data Elasticsearch quét package được chỉ định để tìm repository interface của Elasticsearch.

### 5.2. Cấu hình JPA

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.catalog.jpa.repository"
)
public class JpaRepositoryConfig {
}
~~~

`@EnableJpaRepositories` giới hạn việc phát hiện repository JPA trong package của JPA.

Có thể đặt hai annotation trong cùng một class cấu hình nếu muốn gom cấu hình repository lại:

~~~java
@Configuration
@EnableJpaRepositories(
        basePackages = "com.example.catalog.jpa.repository"
)
@EnableElasticsearchRepositories(
        basePackages = "com.example.catalog.elasticsearch.repository"
)
public class RepositoryConfiguration {
}
~~~

Các cấu hình trên chỉ điều khiển repository scanning. Kết nối JPA datasource, entity manager factory và Elasticsearch client/template vẫn cần được Spring Boot auto-configuration hoặc cấu hình ứng dụng cung cấp.

## 6. Dùng `basePackageClasses` để tránh hard-code package

Thay vì viết package dưới dạng chuỗi, có thể tạo một marker class trong package repository rồi dùng `basePackageClasses`. Cách này giúp IDE hỗ trợ refactor package và giảm lỗi chính tả.

Ví dụ marker trong package JPA:

~~~java
package com.example.catalog.jpa.repository;

public interface JpaRepositoryMarker {
}
~~~

Marker trong package Elasticsearch:

~~~java
package com.example.catalog.elasticsearch.repository;

public interface ElasticsearchRepositoryMarker {
}
~~~

Cấu hình:

~~~java
@Configuration
@EnableJpaRepositories(basePackageClasses = JpaRepositoryMarker.class)
@EnableElasticsearchRepositories(
        basePackageClasses = ElasticsearchRepositoryMarker.class
)
public class RepositoryConfiguration {
}
~~~

Spring Data sử dụng package chứa marker class làm điểm bắt đầu scanning. Marker không phải repository và không cần được triển khai.

## 7. Strict repository configuration mode và repository mơ hồ

Khi có nhiều Spring Data module, một repository chỉ kế thừa interface chung có thể không cho biết nó thuộc store nào:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {
}
~~~

Nếu domain class `Product` cũng không có annotation store-specific, Spring Data không có đủ thông tin rõ ràng để gán repository cho một module. Kết quả có thể là repository không được đăng ký, cảnh báo cấu hình mơ hồ hoặc hành vi phụ thuộc vào cấu hình scanning.

Giải pháp đơn giản là kế thừa interface đặc thù:

~~~java
public interface ProductSearchRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Hoặc nếu cần một base repository dùng chung, hãy làm cho base interface mang store-specific parent và đánh dấu nó không được tạo bean trực tiếp.

## 8. Dùng `@NoRepositoryBean` cho base repository

Ứng dụng có thể muốn chia sẻ các method chung giữa nhiều repository Elasticsearch. Có thể tạo base interface như sau:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

@NoRepositoryBean
public interface BaseSearchRepository<T, ID>
        extends ElasticsearchRepository<T, ID> {

    // Khai báo các method tìm kiếm dùng chung
}
~~~

Repository cụ thể kế thừa base interface:

~~~java
public interface ProductSearchRepository
        extends BaseSearchRepository<ProductDocument, String> {
}
~~~

`@NoRepositoryBean` báo cho Spring Data rằng interface generic này chỉ là nền tảng để repository khác kế thừa, không phải một repository độc lập cần tạo implementation. Vì base interface vẫn kế thừa `ElasticsearchRepository`, module Elasticsearch có thể nhận diện store của repository con.

Nếu có base repository JPA, hãy tạo base interface riêng kế thừa `JpaRepository` và cũng đánh dấu `@NoRepositoryBean`. Không tạo một base interface duy nhất kế thừa abstraction của nhiều store.

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.jpa.repository.JpaRepository;

@NoRepositoryBean
public interface BaseJpaRepository<T, ID>
        extends JpaRepository<T, ID> {

    // Các method dùng chung cho JPA
}
~~~

`@NoRepositoryBean` không tự xác định store. Nó chỉ ngăn Spring Data tạo bean cho interface nền. Store vẫn được thể hiện qua interface cha đặc thù và domain type.

## 9. Annotation domain type và việc phân biệt store

Các annotation của domain model là tín hiệu bổ sung để Spring Data nhận diện module:

| Store | Annotation thường gặp | Repository interface |
| --- | --- | --- |
| JPA | `jakarta.persistence.Entity` | `JpaRepository<T, ID>` |
| Elasticsearch | `org.springframework.data.elasticsearch.annotations.Document` | `ElasticsearchRepository<T, ID>` |
| MongoDB | `org.springframework.data.mongodb.core.mapping.Document` | `MongoRepository<T, ID>` |

Lưu ý JPA và Elasticsearch đều có annotation tên `Document` trong hệ sinh thái Spring Data, nhưng chúng thuộc package khác nhau và có ý nghĩa khác nhau. Khi import, hãy kiểm tra đúng package.

Không nên gắn nhiều annotation lưu trữ lên cùng một domain class chỉ để tái sử dụng một model cho tất cả database. Một class vừa mang `@Entity`, vừa mang annotation `@Document` của Elasticsearch có thể khiến nhiều module cùng nhận nó là domain type của mình và tạo cấu hình mapping không rõ ràng.

Trong mô hình có nhiều store, thường nên tách `ProductEntity` cho JPA và `ProductDocument` cho Elasticsearch. Service hoặc mapper chuyển đổi dữ liệu giữa hai model theo nhu cầu đồng bộ.

## 10. Repository scanning khác với entity scanning

Repository scanning tìm các interface repository để tạo bean. Entity scanning tìm các domain type mà persistence provider hoặc mapping context cần quản lý. Hai quá trình có liên quan nhưng không đồng nhất.

Với JPA, `@EntityScan` của Spring Boot có thể điều chỉnh package tìm entity, còn `@EnableJpaRepositories` điều chỉnh package tìm repository.

Với Elasticsearch, `@EnableElasticsearchRepositories` điều chỉnh việc tìm repository. Mapping metadata của Elasticsearch được xây dựng từ domain types mà repository hoặc cấu hình mapping context sử dụng. Đặt repository vào đúng package không tự sửa mapping của entity hoặc tạo index đã tồn tại.

Vì vậy, nếu repository được phát hiện nhưng entity không được ánh xạ như mong muốn, hãy kiểm tra domain annotations, mapping metadata và cấu hình store tương ứng; đừng chỉ mở rộng package repository scanning.

## 11. Kết hợp với Spring Boot auto-configuration

Spring Boot có thể tự cấu hình các Spring Data module khi dependency tương ứng có mặt và điều kiện ứng dụng đáp ứng. Trong cấu trúc ứng dụng đơn giản, package gốc của `@SpringBootApplication` có thể là điểm quét mặc định cho repository.

Khi có nhiều store, hãy đảm bảo các repository có kiểu cha đặc thù và package được tổ chức rõ. Nếu cần giới hạn phạm vi quét chính xác, cấu hình `@EnableJpaRepositories` và `@EnableElasticsearchRepositories` với package riêng.

Không nên đồng thời khai báo nhiều cấu hình scanning chồng lấn mà không kiểm tra tác động. Nếu vừa dùng cấu hình tự động của Spring Boot, vừa thêm `@Enable...Repositories` thủ công, hãy đảm bảo mỗi repository chỉ được đăng ký theo cấu hình mong muốn và không phát sinh bean trùng tên hoặc scan sai module.

Ví dụ ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Các cấu hình repository riêng có thể nằm trong package được component scan của ứng dụng nhận diện. Cấu hình kết nối JPA và Elasticsearch được khai báo trong `application.yml` hoặc qua bean cấu hình tương ứng.

## 12. Dùng hai repository trong cùng service

Service có thể phối hợp JPA và Elasticsearch mà không trộn hai repository abstraction:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductCatalogService {

    private final ProductJpaRepository jpaRepository;
    private final ProductSearchRepository searchRepository;

    public ProductCatalogService(
            ProductJpaRepository jpaRepository,
            ProductSearchRepository searchRepository) {
        this.jpaRepository = jpaRepository;
        this.searchRepository = searchRepository;
    }

    public ProductDocument indexProduct(Long productId) {
        ProductEntity entity = jpaRepository.findById(productId)
                .orElseThrow();

        ProductDocument document = new ProductDocument(
                entity.getId().toString(),
                entity.getSku(),
                entity.getName());

        return searchRepository.save(document);
    }
}
~~~

Trong ví dụ, JPA là nguồn dữ liệu nghiệp vụ và Elasticsearch là nơi phục vụ tìm kiếm. Service đọc entity từ PostgreSQL, chuyển thành document rồi ghi vào Elasticsearch.

Đây là ví dụ đơn giản cho luồng đồng bộ. Trong hệ thống thực tế, nếu transaction JPA đã commit nhưng ghi Elasticsearch thất bại, hai store có thể lệch dữ liệu. Có thể dùng transactional outbox, event-driven projection hoặc cơ chế retry để đồng bộ đáng tin cậy. Việc phân vùng repository giúp tách trách nhiệm store; nó không tự tạo transaction phân tán giữa JPA và Elasticsearch.

## 13. Các thuộc tính cấu hình scanning hữu ích

Các annotation `@EnableJpaRepositories` và `@EnableElasticsearchRepositories` cung cấp một số thuộc tính thường dùng:

| Thuộc tính | Công dụng |
| --- | --- |
| `basePackages` | Danh sách package được quét để tìm repository. |
| `basePackageClasses` | Chọn package thông qua class marker, tránh hard-code tên package. |
| `includeFilters` | Chỉ định thêm điều kiện để chọn interface cần quét. |
| `excludeFilters` | Loại bỏ interface khỏi phạm vi quét. |
| `considerNestedRepositories` | Cho phép phát hiện repository interface lồng trong class khi được bật. |
| `repositoryImplementationPostfix` | Hậu tố dùng khi tìm implementation tùy chỉnh của repository. |

Thông thường, `basePackageClasses` hoặc `basePackages` đã đủ để phân vùng repository. Chỉ dùng include/exclude filters khi package chứa nhiều loại interface và cần điều kiện chọn chi tiết hơn.

## 14. Lỗi thường gặp khi có nhiều Spring Data module

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Repository không được tạo bean | Interface chỉ kế thừa `CrudRepository` và domain type không có annotation store-specific. | Kế thừa repository interface của module hoặc gắn domain annotation phù hợp. |
| Repository bị nhận nhầm store | Package scanning chồng lấn hoặc domain type mang annotation của nhiều store. | Tách package/model và cấu hình scan theo module. |
| Có bean repository trùng tên | Nhiều interface ở package khác nhau có cùng tên bean mặc định. | Đổi tên repository interface hoặc cấu hình bean naming phù hợp. |
| JPA repository dùng sai entity | `@EnableJpaRepositories` quét cả package Elasticsearch hoặc generic repository không rõ store. | Giới hạn package JPA và dùng `JpaRepository`. |
| Elasticsearch repository không dùng đúng template/client | Repository scanning hoặc cấu hình module tham chiếu sai store. | Kiểm tra `@EnableElasticsearchRepositories` và cấu hình client/template. |
| Base repository generic bị tạo bean | Thiếu `@NoRepositoryBean`. | Đánh dấu interface nền bằng `@NoRepositoryBean`. |
| Cùng domain class được nhiều module nhận diện | Một model dùng chung nhiều annotation store. | Tách entity/document và ánh xạ giữa chúng ở tầng service. |
| Service ghi JPA thành công nhưng search chưa thấy dữ liệu | Projection Elasticsearch chưa được đồng bộ hoặc refresh chưa hoàn tất. | Kiểm tra luồng đồng bộ, lỗi ghi và refresh/search visibility. |

## 15. Quy trình cấu hình ứng dụng nhiều store

Khi một ứng dụng cần nhiều Spring Data module, có thể thực hiện theo thứ tự:

1. Liệt kê các store thực sự sử dụng, ví dụ JPA và Elasticsearch.
2. Tạo domain model riêng phù hợp với mapping của từng store.
3. Tạo repository interface kế thừa abstraction đặc thù như `JpaRepository` và `ElasticsearchRepository`.
4. Đặt repository trong package riêng theo store.
5. Dùng `@EnableJpaRepositories` và `@EnableElasticsearchRepositories` với package tương ứng khi cần kiểm soát scanning.
6. Đánh dấu generic base repository bằng `@NoRepositoryBean` và bảo đảm base interface kế thừa đúng module.
7. Kiểm tra cấu hình entity/mapping, datasource, Elasticsearch client và template riêng cho từng store.
8. Khởi động ứng dụng và xác nhận các repository bean được tạo đúng module.
9. Kiểm tra service phối hợp hai repository và xử lý tính nhất quán dữ liệu giữa các store.

Khi nhiều Spring Data module cùng tồn tại, repository cần thể hiện rõ store mà nó phục vụ. Dùng interface đặc thù, domain annotation đúng package và package scanning tách biệt giúp Spring Data phân loại repository ổn định. `@NoRepositoryBean` dành cho base interface, còn service là nơi phối hợp các repository khác store và xử lý đồng bộ dữ liệu giữa chúng.
