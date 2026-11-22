# Cơ chế tự cấu hình Spring Boot và điều kiện để repository được phát hiện trong Spring Data REST

Spring Data REST không tự tìm mọi interface trong dự án rồi biến chúng thành endpoint. Một API hoạt động cần đi qua nhiều lớp cấu hình: dependency phải có trên classpath, Spring Boot phải nhận diện loại web application và công nghệ lưu trữ, Spring Data phải quét được repository interface và tạo repository bean, sau đó Spring Data REST mới quyết định repository nào được export thành tài nguyên HTTP.

Điểm quan trọng nhất là phân biệt **repository discovery** với **repository exposure**:

- **Discovery (phát hiện repository):** Spring Data tìm interface trong các package được cấu hình, xác định store tương ứng và đăng ký proxy bean trong ApplicationContext.
- **Exposure (công bố repository):** Spring Data REST chọn những repository bean đã được phát hiện để tạo collection resource, item resource, search resource và các HTTP endpoint.

Một repository có thể được Spring Data tạo bean nhưng không được Spring Data REST công bố. Ngược lại, nếu repository bean chưa tồn tại, thay đổi detection strategy của Spring Data REST cũng không thể làm endpoint xuất hiện.

## 1. Các dependency cần có

Spring Data REST cần tích hợp MVC của Spring Data REST và một loại Spring Data repository cụ thể. Với ứng dụng JPA, thường thêm cả starter Data REST và starter Data JPA:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")

    runtimeOnly("org.postgresql:postgresql")
}
~~~

Ví dụ dùng Gradle Kotlin DSL và PostgreSQL. Có thể thay JPA bằng store khác, chẳng hạn:

| Loại dữ liệu | Starter Spring Data thường dùng |
|---|---|
| JPA / relational database | spring-boot-starter-data-jpa |
| MongoDB | spring-boot-starter-data-mongodb |
| JDBC | spring-boot-starter-data-jdbc |
| Redis | spring-boot-starter-data-redis |
| Elasticsearch | spring-boot-starter-data-elasticsearch |

Tên starter và phiên bản cụ thể phụ thuộc Spring Boot release đang dùng. Nên để Spring Boot dependency management quản lý các phiên bản tương thích thay vì tự ghép các phiên bản Spring Data khác nhau.

Mỗi dependency có một vai trò riêng:

- Store starter cung cấp Spring Data module và hạ tầng để tạo repository cho store đó.
- JDBC driver hoặc client tương ứng cho phép ứng dụng kết nối tới hệ thống lưu trữ.
- Data REST starter cung cấp lớp REST integration để công bố repository qua Spring MVC.
- Spring Boot auto-configuration kết nối các thành phần khi điều kiện tương ứng được thỏa mãn.

Chỉ có spring-boot-starter-data-jpa thì repository JPA vẫn có thể hoạt động như bean trong ứng dụng, nhưng điều đó không tự động có nghĩa các repository được công bố thành REST endpoint. Chỉ có spring-boot-starter-data-rest cũng chưa đủ nếu ứng dụng chưa có store repository nào được đăng ký.

## 2. Spring Boot auto-configuration hoạt động theo điều kiện

@SpringBootApplication bao gồm @EnableAutoConfiguration. Spring Boot dùng classpath, loại ứng dụng, bean đã tồn tại và các property để quyết định auto-configuration nào phù hợp. Auto-configuration không phải một cấu hình cố định được bật vô điều kiện; mỗi cấu hình có thể dùng các điều kiện như:

- @ConditionalOnClass: chỉ áp dụng khi class cần thiết có mặt trên classpath.
- @ConditionalOnMissingBean: chỉ áp dụng khi bean tùy chỉnh tương ứng chưa tồn tại.
- @ConditionalOnBean: chỉ áp dụng khi bean phụ thuộc đã có.
- @ConditionalOnProperty: chỉ áp dụng khi property có giá trị phù hợp.
- @ConditionalOnWebApplication: chỉ áp dụng cho loại web application phù hợp, ví dụ Servlet hoặc Reactive.

Khi một điều kiện không thỏa mãn, Spring Boot bỏ qua auto-configuration đó. Đây thường là lý do một tính năng không được bật dù dependency đã xuất hiện trong file build.

### 2.1. Auto-configuration của store repository

Với JPA, Spring Boot nhận diện Spring Data JPA trên classpath và cấu hình hạ tầng repository phù hợp. Quá trình này cần các thành phần liên quan như JPA API, EntityManager, EntityManagerFactory và DataSource được cấu hình hợp lệ.

Với MongoDB, Boot dùng module MongoDB và các thành phần kết nối Mongo tương ứng. Redis, JDBC, Elasticsearch và các store khác cũng có auto-configuration riêng.

Store auto-configuration chịu trách nhiệm cho việc tìm repository interface và đăng ký repository proxy bean. Vị trí quét mặc định thường lấy từ các auto-configuration package đã đăng ký, thông thường là package chứa class chính có @SpringBootApplication hoặc các package con của nó.

### 2.2. Auto-configuration của Spring Data REST

Spring Data REST có auto-configuration riêng cho lớp tích hợp MVC. Ở Spring Boot 3.5.x, class này là:

~~~java
org.springframework.boot.autoconfigure.data.rest.RepositoryRestMvcAutoConfiguration
~~~

Javadoc của Boot 3.5 mô tả các điều kiện chính:

~~~java
@ConditionalOnWebApplication(type = SERVLET)
@ConditionalOnMissingBean(RepositoryRestMvcConfiguration.class)
@ConditionalOnClass(RepositoryRestMvcConfiguration.class)
@EnableConfigurationProperties(RepositoryRestProperties.class)
@Import(RepositoryRestMvcConfiguration.class)
~~~

Ý nghĩa:

1. Ứng dụng phải là Servlet web application. Đây là tích hợp Spring MVC; chỉ chạy một ứng dụng WebFlux thuần không thỏa mãn điều kiện Servlet này.
2. Class RepositoryRestMvcConfiguration của Spring Data REST phải có trên classpath.
3. Nếu ứng dụng đã cung cấp RepositoryRestMvcConfiguration, auto-configuration mặc định sẽ lùi lại để tránh cấu hình trùng.
4. Các property dưới prefix spring.data.rest được bind vào cấu hình Spring Data REST.
5. Cấu hình MVC của Spring Data REST được import để đăng ký hạ tầng REST.

Từ Spring Boot 4, tên class và package auto-configuration đã thay đổi. Class tương ứng là:

~~~java
org.springframework.boot.data.rest.autoconfigure.DataRestAutoConfiguration
~~~

Boot 4 tiếp tục kiểm tra loại ứng dụng Servlet, class Spring Data REST trên classpath và sự hiện diện của RepositoryRestMvcConfiguration; nó bind DataRestProperties rồi import cấu hình MVC của Spring Data REST. Vì vậy, khi đọc Condition Evaluation Report hoặc Javadoc, phải đối chiếu với đúng major version đang chạy. Không nên sao chép tên class auto-configuration từ Boot 3 sang Boot 4.

Điều cần nhớ: auto-configuration REST chuẩn bị lớp HTTP và cấu hình REST. Nó không thay thế quá trình quét repository của JPA, MongoDB hoặc store module khác.

## 3. Chuỗi xử lý từ dependency đến endpoint

Có thể hình dung quá trình khởi tạo theo chuỗi sau:

~~~mermaid
flowchart TD
    A["Dependencies trên classpath"] --> B["Spring Boot nhận diện store"]
    B --> C["Store repository auto-configuration"]
    C --> D["Quét package repository"]
    D --> E["Tạo repository proxy bean"]
    F["Data REST starter và Servlet MVC"] --> G["Data REST auto-configuration"]
    G --> H["RepositoryRestMvcConfiguration"]
    E --> I["Repository detection và export rules"]
    H --> I
    I --> J["REST resources và HTTP endpoints"]
~~~

Diễn giải theo từng bước:

1. Dependency đưa các class Spring Data, store implementation và Spring Data REST vào runtime classpath.
2. Spring Boot kiểm tra các điều kiện để bật auto-configuration tương ứng.
3. Store module tìm repository interface trong package đã cấu hình.
4. Spring Data tạo proxy bean cho repository. Proxy này thực thi các thao tác CRUD hoặc query thông qua store implementation.
5. Spring Data REST đăng ký hạ tầng MVC và nhận biết repository metadata từ Spring Data.
6. Repository detection strategy quyết định repository nào được công bố.
7. Các repository được export trở thành tài nguyên HTTP; tên đường dẫn và relation có thể dùng quy ước mặc định hoặc annotation tùy chỉnh.

Bước 3–4 và bước 5–6 là hai cổng độc lập. Khi debug, hãy xác định lỗi nằm ở việc chưa tạo repository bean hay ở việc repository đã tồn tại nhưng không được export.

## 4. Điều kiện để Spring Data phát hiện repository interface

Spring Data repository thường là một interface kế thừa org.springframework.data.repository.Repository trực tiếp hoặc thông qua một interface chuyên biệt. Ví dụ:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

JpaRepository kế thừa các hợp đồng repository tổng quát của Spring Data và bổ sung các thao tác dành cho JPA. Spring Data nhận biết interface này, tạo một proxy bean và cung cấp implementation phù hợp với store.

Không bắt buộc phải viết class implementation cho từng repository. Spring Data tạo proxy trong lúc khởi tạo ApplicationContext và chuyển lời gọi phương thức sang cơ chế thực thi tương ứng.

### 4.1. Interface phải nằm trong package được quét

Giả sử cấu trúc package:

~~~text
com.example.catalog
├── CatalogApplication.java
├── product
│   ├── Product.java
│   └── ProductRepository.java
└── category
    ├── Category.java
    └── CategoryRepository.java
~~~

Class chính:

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

Vì class chính ở package com.example.catalog, các package con như com.example.catalog.product và com.example.catalog.category nằm trong phạm vi auto-configuration package mặc định. Spring Boot có thể dùng phạm vi này để tìm repository và entity.

Nếu class chính đặt ở com.example.bootstrap còn repository nằm trong com.example.catalog.product, repository có thể nằm ngoài package mặc định. Khi đó cần cấu hình phạm vi quét rõ ràng.

### 4.2. Dùng @EnableJpaRepositories để chỉ định phạm vi quét

Khi cần kiểm soát chính xác package repository, dùng annotation của store tương ứng:

~~~java
package com.example.bootstrap;

import com.example.catalog.product.ProductRepository;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@SpringBootApplication
@EnableJpaRepositories(
    basePackageClasses = ProductRepository.class
)
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

basePackageClasses lấy package của class được chỉ định và an toàn hơn việc ghi tên package dưới dạng chuỗi. Có thể dùng basePackages khi cần nhiều package.

Các annotation tương ứng theo store gồm:

- @EnableJpaRepositories
- @EnableMongoRepositories
- @EnableJdbcRepositories
- @EnableRedisRepositories

Trong ứng dụng Spring Boot đơn giản, thường không cần tự thêm annotation này vì store auto-configuration đã quét auto-configuration package. Chỉ dùng khi cần thay đổi phạm vi hoặc cấu trúc cấu hình mặc định.

### 4.3. Repository scan và entity scan là hai việc riêng

Đối với JPA, việc phát hiện repository interface không đồng nghĩa với việc entity đã được quản lý.

- @EnableJpaRepositories xác định nơi tìm repository interface.
- @EntityScan xác định nơi tìm các entity cần đưa vào persistence unit.
- @ComponentScan tìm các component như @Service, @Controller, @Configuration.

Nếu repository được tìm thấy nhưng entity nằm ngoài phạm vi entity scan, ứng dụng có thể lỗi khi tạo EntityManagerFactory hoặc báo domain type không được quản lý. Sửa repository scan không thay thế cho việc cấu hình entity scan.

Trong cấu trúc package mặc định của Spring Boot, repository và entity cùng nằm dưới package chính thường được tự động nhận diện. Khi tách module hoặc package, hãy cấu hình cả hai phạm vi khi cần.

## 5. Domain type và loại repository

Một repository phải xác định được domain type và kiểu ID. Có hai cách phổ biến.

### 5.1. Kế thừa interface Spring Data

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Product là domain type; Long là kiểu ID. Các phương thức được thừa kế từ JpaRepository cung cấp CRUD, phân trang, sắp xếp và các thao tác JPA phổ biến.

Một số interface thường dùng:

| Interface | Mục đích |
|---|---|
| Repository<T, ID> | Marker và điểm gốc của hợp đồng Spring Data |
| CrudRepository<T, ID> | Các thao tác CRUD cơ bản |
| ListCrudRepository<T, ID> | CRUD trả về List cho các phương thức lấy nhiều phần tử |
| PagingAndSortingRepository<T, ID> | Phân trang và sắp xếp |
| JpaRepository<T, ID> | Hợp đồng repository chuyên cho JPA |
| MongoRepository<T, ID> | Hợp đồng repository chuyên cho MongoDB |

Không phải repository nào cũng cần kế thừa JpaRepository. Có thể chọn interface hẹp hơn để giới hạn thao tác mà ứng dụng muốn sử dụng.

### 5.2. Dùng @RepositoryDefinition

Nếu không muốn kế thừa một interface repository chuẩn, có thể khai báo domain type và ID type bằng annotation:

~~~java
import org.springframework.data.repository.RepositoryDefinition;

@RepositoryDefinition(domainClass = Product.class, idClass = Long.class)
public interface ProductRepository {
    Optional<Product> findById(Long id);
    List<Product> findByNameContaining(String name);
}
~~~

Interface vẫn phải nằm trong phạm vi repository scan và tuân theo quy tắc của store tương ứng. @RepositoryDefinition không tự bật Spring Data REST; nó chỉ khai báo hợp đồng repository để Spring Data nhận diện.

### 5.3. Không đăng ký interface nền như repository nghiệp vụ

Khi xây dựng interface dùng chung, có thể đánh dấu bằng @NoRepositoryBean:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);
}
~~~

Interface con có domain type cụ thể:

~~~java
public interface ProductRepository
        extends BaseRepository<Product, Long> {
}
~~~

@NoRepositoryBean nói với Spring Data rằng không tạo repository proxy trực tiếp cho interface nền. Nếu bỏ annotation này trên interface tổng quát chưa có domain type cụ thể, Spring Data có thể cố tạo bean không hợp lệ hoặc báo lỗi khởi tạo.

## 6. Chọn đúng store khi có nhiều Spring Data module

Nếu chỉ có một store module, Spring Data có thể xác định repository dựa trên module hiện có. Khi nhiều module cùng xuất hiện trên classpath, Spring Data chuyển sang strict repository configuration mode để xác định repository nào thuộc store nào.

Ví dụ ứng dụng có cả Spring Data JPA và Spring Data MongoDB:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {
}

public interface AuditRepository
        extends MongoRepository<AuditDocument, String> {
}
~~~

Interface chuyên biệt như JpaRepository và MongoRepository cung cấp tín hiệu rõ ràng về store. Domain type cũng có thể được nhận diện bằng annotation phù hợp, ví dụ @Entity cho JPA và @Document cho MongoDB.

Một interface chỉ kế thừa CrudRepository có thể không đủ thông tin để Spring Data xác định store khi nhiều module cùng hoạt động. Khi gặp trường hợp này:

- Ưu tiên repository interface chuyên biệt theo store.
- Dùng annotation domain type đúng với công nghệ lưu trữ.
- Dùng @EnableJpaRepositories và @EnableMongoRepositories để tách rõ package.
- Tránh để một repository interface mơ hồ được nhiều store cùng nhận diện.

Ví dụ cấu hình package riêng:

~~~java
@Configuration
@EnableJpaRepositories(
    basePackageClasses = JpaOrderRepository.class
)
@EnableMongoRepositories(
    basePackageClasses = MongoAuditRepository.class
)
public class RepositoryConfiguration {
}
~~~

Có thể bật hoặc tắt auto-configured repositories của từng module bằng property tương ứng dưới spring.data.*.repositories.enabled khi module hỗ trợ property đó. Nếu dùng nhiều store, cần đọc property metadata của đúng Spring Boot version đang chạy.

## 7. Repository được tạo bean chưa có nghĩa là đã được REST export

Sau khi Spring Data đăng ký repository bean, Spring Data REST dùng RepositoryDetectionStrategy để quyết định repository nào được công bố dưới dạng HTTP resource.

Mặc định, Spring Data REST dùng chiến lược DEFAULT. Chiến lược này công bố repository interface public hoặc repository được đánh dấu bằng @RepositoryRestResource, đồng thời xét cờ exported của annotation.

Bốn chiến lược thường gặp:

| Strategy | Quy tắc công bố |
|---|---|
| DEFAULT | Công bố repository public hoặc được đánh dấu bằng @RepositoryRestResource, có xét exported=false |
| ALL | Xem xét tất cả repository, không phụ thuộc visibility hoặc annotation |
| VISIBILITY | Chỉ công bố repository interface public |
| ANNOTATED | Chỉ công bố repository được đánh dấu bằng annotation phù hợp và không bị exported=false |

Sự khác biệt giữa DEFAULT và VISIBILITY đáng chú ý: một repository package-private có thể được công bố khi nó được đánh dấu rõ ràng dưới DEFAULT; VISIBILITY chỉ xét interface public.

Có thể cấu hình chiến lược trong application.yml:

~~~yaml
spring:
  data:
    rest:
      detection-strategy: annotated
      base-path: /api
~~~

Với chiến lược annotated, repository cần được đánh dấu rõ ràng:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "products")
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Nếu repository chỉ phục vụ nội bộ, có thể tắt export:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<InternalAudit, Long> {
}
~~~

Có thể ẩn riêng query method hoặc association bằng @RestResource(exported = false) ở phần tử tương ứng. Đây là quy tắc exposure ở lớp Spring Data REST; nó không ngăn Spring Data tạo repository bean để code nội bộ sử dụng.

Không nên chọn ALL một cách tùy tiện trong ứng dụng có repository nội bộ, bởi chiến lược này mở rộng bề mặt repository được xem xét để công bố. Hãy chọn chiến lược phù hợp với hợp đồng API và kiểm tra các cờ export trong phiên bản đang dùng.

## 8. Tùy chỉnh Spring Data REST bằng property và configurer

Các property thuộc prefix spring.data.rest điều chỉnh cấu hình REST. Ví dụ:

~~~yaml
spring:
  data:
    rest:
      base-path: /api
      detection-strategy: annotated
      default-page-size: 20
      max-page-size: 100
~~~

Trong ví dụ:

- base-path đặt prefix cho các endpoint.
- detection-strategy chọn quy tắc công bố repository.
- default-page-size đặt số phần tử mặc định mỗi trang.
- max-page-size giới hạn số phần tử tối đa một trang.

Property chính xác có thể thay đổi giữa các release. Hãy dùng configuration metadata và tài liệu của đúng Spring Boot version, đặc biệt khi nâng cấp major version.

Khi cần logic tùy chỉnh ngoài property, có thể đăng ký một bean RepositoryRestConfigurer:

~~~java
@Configuration
public class RestRepositoryConfiguration {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return new RepositoryRestConfigurer() {
            @Override
            public void configureRepositoryRestConfiguration(
                    RepositoryRestConfiguration config,
                    CorsRegistry cors) {

                config.setBasePath("/api");
            }
        };
    }
}
~~~

Đây là điểm mở rộng dành cho cấu hình Spring Data REST. Spring Boot có thể tiếp tục cung cấp auto-configuration và áp dụng configurer tùy chỉnh. Nếu cần thay đổi cách cấu hình REST, ưu tiên RepositoryRestConfigurer và property thay vì tự import toàn bộ RepositoryRestMvcConfiguration.

Nếu tự khai báo RepositoryRestMvcConfiguration, điều kiện @ConditionalOnMissingBean khiến auto-configuration REST mặc định lùi lại. Khi đó ứng dụng chịu trách nhiệm đảm bảo các thành phần cấu hình cần thiết đã được đăng ký.

## 9. Kiểm tra repository có được phát hiện và export hay không

Một cách kiểm tra hiệu quả là tách chẩn đoán thành hai câu hỏi.

### 9.1. Repository bean có tồn tại không?

Kiểm tra:

- Dependency store có trong runtime classpath không?
- Store auto-configuration có được bật không?
- Interface có kế thừa Repository hoặc dùng @RepositoryDefinition không?
- Package repository có nằm trong phạm vi scan không?
- Domain type có thuộc store tương ứng và được quản lý không?
- Repository có bị đánh dấu @NoRepositoryBean không?
- Có nhiều store module khiến repository bị mơ hồ không?

Nếu ứng dụng không tạo được repository bean, lỗi thuộc discovery hoặc store infrastructure. Thay đổi spring.data.rest.detection-strategy sẽ không giải quyết được lỗi này.

### 9.2. Repository bean có được REST export không?

Nếu repository bean đã tồn tại nhưng endpoint không xuất hiện, kiểm tra:

- Data REST starter và RepositoryRestMvcConfiguration có trong runtime classpath không?
- Ứng dụng có phải Servlet web application không?
- RepositoryRestMvcConfiguration có bị thay thế bằng cấu hình thủ công khiến Boot auto-configuration lùi lại không?
- spring.data.rest.detection-strategy có loại repository này ra không?
- Repository có @RepositoryRestResource(exported = false) không?
- Auto-configuration có bị loại khỏi @EnableAutoConfiguration hoặc spring.autoconfigure.exclude không?
- Base path có được đổi sang /api hoặc một prefix khác không?

### 9.3. Bật điều kiện auto-configuration

Có thể chạy ứng dụng với --debug:

~~~bash
./gradlew bootRun --args="--debug"
~~~

Hoặc chạy JAR:

~~~bash
java -jar build/libs/catalog.jar --debug
~~~

Spring Boot in Condition Evaluation Report, cho biết auto-configuration nào được áp dụng và cấu hình nào bị bỏ qua cùng lý do. Khi đọc báo cáo, tìm các cấu hình liên quan tới store đang dùng và Spring Data REST.

Có thể tăng log cho repository configuration:

~~~yaml
logging:
  level:
    org.springframework.data.repository.config: DEBUG
    org.springframework.data.rest: DEBUG
~~~

Log giúp quan sát package được quét, repository được đăng ký và các thông tin liên quan tới REST mapping. Tên logger và mức log hữu ích có thể thay đổi theo phiên bản.

### 9.4. Gọi root resource để kiểm tra API

Nếu base path là /api, gửi request:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api/
~~~

Root resource thường trả các relation dẫn tới repository đã export. Nếu repository không xuất hiện ở đây, hãy quay lại kiểm tra discovery và exposure. Nếu repository xuất hiện nhưng request tới collection lỗi, tiếp tục kiểm tra route, security, kết nối store và trạng thái dữ liệu.

## 10. Các tình huống thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Ứng dụng chạy nhưng không có REST repository endpoint | Thiếu Data REST starter hoặc REST auto-configuration không thỏa điều kiện | Kiểm tra runtime classpath, Servlet MVC và Condition Evaluation Report |
| Repository interface không tạo bean | Interface nằm ngoài package scan hoặc thiếu store infrastructure | Kiểm tra package, store starter và @Enable…Repositories |
| Repository JPA được tìm thấy nhưng lỗi entity | Entity nằm ngoài entity scan hoặc mapping không hợp lệ | Kiểm tra @EntityScan, entity annotation và persistence unit |
| Bean tồn tại nhưng không có link ở root | Repository bị loại bởi detection strategy hoặc exported=false | Kiểm tra spring.data.rest.detection-strategy và annotation |
| Repository public vẫn không xuất hiện | REST auto-configuration bị loại hoặc ứng dụng không chạy Servlet MVC | Kiểm tra classpath, điều kiện web và custom MVC configuration |
| Chỉ một số repository được export | Khác biệt visibility, annotation hoặc package | So sánh repository interface và detection strategy |
| JPA và Mongo cùng nhận repository | Repository generic hoặc domain metadata không đủ rõ | Dùng store-specific interface và package riêng |
| Endpoint đúng nhưng URL khác dự kiến | Có base-path hoặc @RepositoryRestResource(path=...) | Đọc spring.data.rest.base-path và annotation |
| Query method không có link search | Method không được export hoặc không đáp ứng quy tắc query | Kiểm tra method signature và @RestResource |
| Ứng dụng lỗi khi khởi động sau khi thêm starter | Thiếu cấu hình DataSource, driver hoặc store bean | Đọc root cause và failure analysis trong startup log |

## 11. Checklist khi tạo một repository mới

Trước khi kỳ vọng endpoint xuất hiện, kiểm tra theo thứ tự:

1. Đã thêm Data REST starter và store starter phù hợp chưa?
2. Runtime classpath có driver hoặc client cần thiết không?
3. Class chính có @SpringBootApplication và package gốc hợp lý không?
4. Repository interface có kế thừa đúng Spring Data interface hoặc dùng @RepositoryDefinition không?
5. Package repository có nằm trong phạm vi scan không?
6. Domain type đã được store quản lý và entity scan đúng chưa?
7. Nếu nhiều store cùng có mặt, repository có chỉ rõ store không?
8. Repository có bị đánh dấu @NoRepositoryBean không?
9. Detection strategy có cho phép export repository không?
10. Annotation có exported=false hoặc auto-configuration có bị loại không?
11. Base path có đúng với URL đang gọi không?
12. Root resource có công bố relation tới collection không?

Khi đi đúng thứ tự này, có thể xác định nhanh endpoint bị thiếu ở giai đoạn tạo repository bean hay ở giai đoạn Spring Data REST công bố tài nguyên.

## Tài liệu tham khảo

- [Spring Boot Reference — Use Spring Data Repositories](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot How-to — Data Access](https://docs.spring.io/spring-boot/how-to/data-access.html)
- [Spring Boot 3.5 API — RepositoryRestMvcAutoConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/data/rest/RepositoryRestMvcAutoConfiguration.html)
- [Spring Boot 4 API — DataRestAutoConfiguration](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/data/rest/autoconfigure/DataRestAutoConfiguration.html)
- [Spring Boot 4 API — DataRestProperties](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/data/rest/autoconfigure/DataRestProperties.html)
- [Spring Data REST Reference — Getting Started and Detection Strategy](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Spring Data REST Reference — Customizing Repository Exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
