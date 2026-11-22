# Phối hợp nhiều Spring Data module mà không quét nhầm repository

> **Chương:** Cấu hình và kiến trúc  
> **Bối cảnh:** Ứng dụng dùng **Spring Data MongoDB** để thao tác document qua `MongoTemplate` hoặc repository, đồng thời dùng một Spring Data module khác, chẳng hạn **Spring Data JPA** để truy cập cơ sở dữ liệu quan hệ.  
> **Mục tiêu:** Hiểu cách Spring Data xác định repository thuộc data store nào; bố trí package, interface và entity rõ ràng; giới hạn vùng quét repository; kiểm tra wiring; tránh lỗi khi dùng đồng thời MongoDB imperative/reactive và nhiều data store.

## 1. Vì sao nhiều Spring Data module dễ phát sinh nhầm lẫn?

Một ứng dụng có thể sử dụng PostgreSQL làm nguồn dữ liệu giao dịch qua Spring Data JPA và MongoDB làm kho document phục vụ tra cứu qua Spring Data MongoDB:

~~~mermaid
flowchart LR
    A["Service / Use case"] --> B["ProductJpaRepository"]
    A --> C["ProductViewMongoRepository"]
    B --> D["Spring Data JPA"]
    C --> E["Spring Data MongoDB"]
    D --> F[("PostgreSQL")]
    E --> G[("MongoDB")]
~~~

Cả hai module đều được xây trên **Spring Data Commons** nên dùng các khái niệm tương tự: repository interface, `findById()`, `save()`, `deleteById()`, truy vấn suy diễn từ tên phương thức. Tuy nhiên:

- `JpaRepository` phải được triển khai bởi hạ tầng JPA và dùng `EntityManager`.
- `MongoRepository` phải được triển khai bởi hạ tầng MongoDB và dùng MongoDB driver/`MongoTemplate`.
- `ReactiveMongoRepository` cần hạ tầng **reactive**, khác với MongoDB repository đồng bộ.

Nếu quét một package quá rộng hoặc định nghĩa repository quá chung chung, Spring có thể không xác định được repository thuộc store nào, tạo trùng bean, bỏ qua repository, hoặc nhận một entity sai loại. Lỗi có thể xuất hiện **khi khởi động**, hoặc muộn hơn khi ứng dụng truy cập database.

Mục tiêu kiến trúc là làm rõ **ai sở hữu repository**, **store nào xử lý repository** và **template/transaction manager nào được dùng**.

## 2. Cơ chế strict repository configuration

Khi phát hiện **nhiều Spring Data module hỗ trợ repository** trên classpath, Spring Data vào chế độ thường được gọi là **strict repository configuration mode**. Cơ chế này cố xác định một ứng viên repository phù hợp với từng module dựa trên những dấu hiệu như:

1. **Repository kế thừa interface chuyên biệt của store**: `JpaRepository`, `MongoRepository`, `ReactiveMongoRepository`…
2. **Domain type có annotation nhận dạng store**: ví dụ `@Entity` của JPA hoặc `@Document` của MongoDB.
3. **Phạm vi package được cấu hình cho từng bộ quét**: chỉ các interface nằm trong vùng quét mới được xem xét.

Hai loại dấu hiệu đầu giúp xác định **store assignment**; phạm vi package quyết định **repository nào được phát hiện**. Chỉ đặt interface vào package tên `mongo` hoặc `jpa` **không tự làm cho nó trở thành repository đúng store** nếu không có cấu hình quét hoặc dấu hiệu nhận dạng phù hợp.

### 2.1. Trường hợp nhận dạng rõ ràng

~~~java
// Spring Data JPA nhận dạng bằng interface chuyên biệt.
public interface ProductJpaRepository
        extends JpaRepository<ProductJpaEntity, Long> {
}

// Spring Data MongoDB nhận dạng bằng interface chuyên biệt.
public interface ProductViewMongoRepository
        extends MongoRepository<ProductViewDocument, String> {
}
~~~

Với hai interface trên, cách gán store rõ ràng ngay cả khi ứng dụng dùng nhiều Spring Data module. Ở mức domain, nên bổ sung đúng annotation cho cơ chế mapping:

~~~java
@jakarta.persistence.Entity
public class ProductJpaEntity {
    // Các field và cấu hình ánh xạ JPA.
}

@org.springframework.data.mongodb.core.mapping.Document("product_views")
public class ProductViewDocument {
    // Các field và cấu hình ánh xạ MongoDB.
}
~~~

Ví dụ dùng hai kiểu domain khác nhau vì bản ghi quan hệ và document tra cứu thường có cấu trúc, khóa định danh và vòng đời không giống nhau.

### 2.2. Trường hợp mơ hồ

~~~java
// Chỉ kế thừa interface chung của Spring Data Commons.
public interface ProductRepository
        extends CrudRepository<Product, String> {
}
~~~

`CrudRepository` thuộc **Spring Data Commons**, không chỉ định JPA hay MongoDB. Khi có nhiều module, Spring phải dựa vào dấu hiệu khác, chẳng hạn annotation trên `Product`. Nếu `Product` không có annotation đặc trưng, store assignment có thể **không xác định được**.

Một ví dụ khác cần tránh:

~~~java
@jakarta.persistence.Entity
@org.springframework.data.mongodb.core.mapping.Document("products")
public class Product {
    // Dùng cùng một domain type cho hai data store.
}
~~~

Khi domain vừa có `@Entity` vừa có `@Document`, hai module có dấu hiệu để nhận dạng cùng một kiểu. Hành vi gắn repository với module trong trường hợp này có thể trở nên không xác định. Không nên giải quyết bằng cách dựa vào thứ tự khởi động của các module.

**Quy tắc thực hành:** Dùng repository interface chuyên biệt và domain riêng cho từng store; đặt package tách biệt; giới hạn vùng quét bằng cấu hình rõ ràng.

## 3. Thiết kế package để các repository không bị lẫn

Giả sử service quản lý sản phẩm ghi dữ liệu giao dịch vào PostgreSQL và xây dựng document tra cứu trong MongoDB:

~~~text
com.example.catalog
├── CatalogApplication.java
├── application
│   └── ProductService.java
├── persistence
│   ├── jpa
│   │   ├── model
│   │   │   └── ProductJpaEntity.java
│   │   └── repository
│   │       ├── JpaRepositoriesPackage.java
│   │       └── ProductJpaRepository.java
│   └── mongodb
│       ├── model
│       │   └── ProductViewDocument.java
│       └── repository
│           ├── MongoRepositoriesPackage.java
│           └── ProductViewMongoRepository.java
└── configuration
    └── PersistenceRepositoryConfiguration.java
~~~

Trong cấu trúc này:

| Phần | Vai trò | Không nên chứa |
| --- | --- | --- |
| `persistence.jpa.model` | Entity JPA, mapping bảng và khóa quan hệ | `@Document` chỉ để tái sử dụng chung entity |
| `persistence.jpa.repository` | Interface `JpaRepository`, marker cấu hình quét | `MongoRepository` |
| `persistence.mongodb.model` | Document MongoDB, mapping BSON | `@Entity` chỉ để gộp hai mô hình |
| `persistence.mongodb.repository` | Interface `MongoRepository`, marker cấu hình quét | `JpaRepository` |
| `application` | Quy tắc nghiệp vụ và phối hợp hai cổng dữ liệu | Giả định hai database nằm trong cùng một transaction |

Tên package là một **quy ước bảo vệ cấu trúc**; chính các annotation `@Enable...Repositories` ở phần sau mới quy định package nào được mỗi module quét.

### 3.1. Một JPA entity và một MongoDB document

~~~java
// File: persistence/jpa/model/ProductJpaEntity.java
package com.example.catalog.persistence.jpa.model;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class ProductJpaEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;
    private long priceVnd;

    protected ProductJpaEntity() { }

    public ProductJpaEntity(String sku, long priceVnd) {
        this.sku = sku;
        this.priceVnd = priceVnd;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public long getPriceVnd() { return priceVnd; }
}
~~~

~~~java
// File: persistence/mongodb/model/ProductViewDocument.java
package com.example.catalog.persistence.mongodb.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "product_views")
public class ProductViewDocument {
    @Id
    private String id;

    private String sku;
    private String displayName;
    private long priceVnd;

    protected ProductViewDocument() { }

    public ProductViewDocument(
            String id, String sku, String displayName, long priceVnd) {
        this.id = id;
        this.sku = sku;
        this.displayName = displayName;
        this.priceVnd = priceVnd;
    }

    public String getId() { return id; }
    public String getSku() { return sku; }
    public String getDisplayName() { return displayName; }
    public long getPriceVnd() { return priceVnd; }
}
~~~

Chú ý hai `@Id` khác nhau:

- JPA: `jakarta.persistence.Id`; thường đi cùng `@GeneratedValue` nếu database cấp khóa.
- MongoDB: `org.springframework.data.annotation.Id`; ánh xạ sang trường `_id` của document.

Hai kiểu dữ liệu không nhất thiết dùng cùng loại ID. Khi cần liên kết thông tin, hãy dùng khóa nghiệp vụ như `sku` hoặc một trường tham chiếu được định nghĩa rõ, thay vì ép một entity phải có cả hai cơ chế mapping.

### 3.2. Repository chuyên biệt theo store

~~~java
// File: persistence/jpa/repository/ProductJpaRepository.java
package com.example.catalog.persistence.jpa.repository;

import com.example.catalog.persistence.jpa.model.ProductJpaEntity;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductJpaRepository
        extends JpaRepository<ProductJpaEntity, Long> {

    Optional<ProductJpaEntity> findBySku(String sku);
}
~~~

~~~java
// File: persistence/mongodb/repository/ProductViewMongoRepository.java
package com.example.catalog.persistence.mongodb.repository;

import com.example.catalog.persistence.mongodb.model.ProductViewDocument;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductViewMongoRepository
        extends MongoRepository<ProductViewDocument, String> {

    Optional<ProductViewDocument> findBySku(String sku);
}
~~~

Hai phương thức `findBySku()` có vẻ giống nhau, nhưng Spring Data JPA tạo truy vấn qua JPA; Spring Data MongoDB tạo truy vấn theo MongoDB. Repository chính là điểm gắn với công nghệ lưu trữ.

Vì bean repository thường được đặt tên từ **tên interface**, nên dùng tên rõ ràng như `productJpaRepository` và `productViewMongoRepository`. Hai interface có cùng tên đơn giản `ProductRepository` trong hai package khác nhau có nguy cơ bị trùng bean name khi cùng đăng ký vào một ApplicationContext.

## 4. Giới hạn quét bằng `@EnableJpaRepositories` và `@EnableMongoRepositories`

Với ví dụ trên, ta tạo marker type trong **đúng package repository** của từng store. Marker là lớp bình thường, không phải repository:

~~~java
// File: persistence/jpa/repository/JpaRepositoriesPackage.java
package com.example.catalog.persistence.jpa.repository;

public final class JpaRepositoriesPackage {
    private JpaRepositoriesPackage() { }
}
~~~

~~~java
// File: persistence/mongodb/repository/MongoRepositoriesPackage.java
package com.example.catalog.persistence.mongodb.repository;

public final class MongoRepositoriesPackage {
    private MongoRepositoriesPackage() { }
}
~~~

Sau đó dùng một cấu hình tường minh:

~~~java
// File: configuration/PersistenceRepositoryConfiguration.java
package com.example.catalog.configuration;

import com.example.catalog.persistence.jpa.repository.JpaRepositoriesPackage;
import com.example.catalog.persistence.mongodb.repository.MongoRepositoriesPackage;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackageClasses = JpaRepositoriesPackage.class
)
@EnableMongoRepositories(
    basePackageClasses = MongoRepositoriesPackage.class,
    mongoTemplateRef = "mongoTemplate"
)
public class PersistenceRepositoryConfiguration {
}
~~~

Ý nghĩa:

- `basePackageClasses = JpaRepositoriesPackage.class`: chỉ quét các repository trong package chứa marker JPA và các package con.
- `basePackageClasses = MongoRepositoriesPackage.class`: chỉ quét repository MongoDB trong package chứa marker MongoDB và các package con.
- `mongoTemplateRef = "mongoTemplate"`: MongoDB repositories dùng bean `MongoTemplate` mang tên `mongoTemplate`; Spring Boot thường tự tạo bean này khi cấu hình một MongoDB connection thông thường.

Trong dự án nhỏ, auto-configuration của Spring Boot có thể nhận dạng chính xác repository nếu interface và domain đã tách rõ. **Không bắt buộc** tự thêm hai annotation `@Enable...Repositories` chỉ vì có hai module. Khi cần chủ động kiểm soát đường quét, hãy cấu hình cả hai với phạm vi hẹp như ví dụ; tránh vừa quét thủ công một package rộng vừa giả định auto-configuration sẽ tự loại tất cả trường hợp mơ hồ.

**Tại sao dùng `basePackageClasses`?** Tên package lấy theo vị trí của một class thật, nên việc đổi package bằng IDE thường được cập nhật cùng source code. Có thể dùng `basePackages = "com.example.catalog.persistence.mongodb.repository"` nếu cần, nhưng chuỗi đường dẫn dễ bị bỏ quên khi refactor.

### 4.1. Trường hợp chỉ dùng một data store repository, data store khác dùng template

Nếu ứng dụng cần `JpaRepository` để làm CRUD và chỉ dùng `MongoTemplate` để thực thi aggregation hoặc cập nhật document theo cách thủ công, thì **không nhất thiết tạo `MongoRepository`**:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchWriter {
    private final MongoTemplate mongoTemplate;

    public ProductSearchWriter(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void writeView(ProductViewDocument document) {
        mongoTemplate.save(document);
    }
}
~~~

Đoạn code minh họa dùng `ProductViewDocument` đã định nghĩa ở phần 3; trong file thực tế phải import class đó. Sự hiện diện của `MongoTemplate` **không tự tạo repository** nếu không có interface phù hợp được quét. Đây là lựa chọn hợp lý khi cần truy vấn MongoDB chuyên biệt hoặc không muốn thêm một tầng repository.

### 4.2. Cấu hình nhiều kết nối MongoDB

Nếu ứng dụng có hai MongoDB databases hoặc hai cluster với hai `MongoTemplate` riêng:

~~~java
@EnableMongoRepositories(
    basePackages = "com.example.catalog.persistence.mongodb.reporting",
    mongoTemplateRef = "reportingMongoTemplate"
)
~~~

Phải có bean thực sự mang tên `reportingMongoTemplate`, được cấu hình với đúng `MongoDatabaseFactory`/`MongoClient`. Nếu có thêm repository MongoDB cho database khác, khai báo một nhóm package khác và dùng đúng template của nhóm đó.

`mongoTemplateRef` chỉ định **MongoDB template**, không chọn JPA `EntityManagerFactory`. Ngược lại, khi có nhiều JPA data sources, `@EnableJpaRepositories` hỗ trợ `entityManagerFactoryRef` và `transactionManagerRef` để gắn đúng tài nguyên JPA; đó là hai vấn đề cấu hình khác nhau.

## 5. Những nguyên nhân quét nhầm thường gặp

### 5.1. Cấu hình package quá rộng

Ví dụ cần tránh khi ứng dụng có cả JPA và MongoDB:

~~~java
// Ví dụ cấu hình rủi ro: quét cả gốc ứng dụng bằng cả hai module.
@EnableJpaRepositories(basePackages = "com.example.catalog")
@EnableMongoRepositories(basePackages = "com.example.catalog")
~~~

Hai bộ quét đều nhìn thấy các interface trong toàn ứng dụng. Chế độ strict có thể phân loại được một số interface, nhưng thiết kế này dễ làm phát sinh cảnh báo hoặc khó chẩn đoán khi sau này có repository chung mới. Hãy giới hạn riêng từng package như phần 4.

### 5.2. Dùng `CrudRepository` làm repository cuối cùng mà không có dấu hiệu store

~~~java
// Mơ hồ nếu Product không mang annotation nhận dạng store.
public interface ProductRepository extends CrudRepository<Product, String> {
}
~~~

Khắc phục: repository JPA nên mở rộng `JpaRepository`; repository MongoDB mở rộng `MongoRepository`. Nếu cần abstraction dùng chung, dùng domain service hoặc cổng nghiệp vụ riêng; đừng ép cả hai store dùng cùng một Spring Data repository interface.

### 5.3. Quên `@NoRepositoryBean` trên interface cơ sở

Khi tạo interface generic dùng làm lớp cha cho nhiều repository, đánh dấu `@NoRepositoryBean` để Spring Data không thử tạo bean trực tiếp từ interface thiếu domain cụ thể:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.mongodb.repository.MongoRepository;

@NoRepositoryBean
public interface BaseMongoRepository<T, ID> extends MongoRepository<T, ID> {
    // Các phương thức chung cho repository MongoDB.
}
~~~

Repository cuối cùng có thể kế thừa `BaseMongoRepository<ProductViewDocument, String>`. Do lớp cơ sở đã kế thừa `MongoRepository`, dấu hiệu gắn với MongoDB được giữ rõ ràng. Với JPA, nếu cần một base tương tự, hãy mở rộng `JpaRepository` và đánh dấu `@NoRepositoryBean`.

### 5.4. Dùng cùng một class vừa `@Entity` vừa `@Document`

Ngoài vấn đề strict mode, cách này khiến mapping quan hệ và BSON cùng chi phối một class: kiểu ID, tên trường, quan hệ JPA, constructor, lazy loading và yêu cầu serialize có thể xung đột.

Giải pháp bền vững:

1. Tạo `ProductJpaEntity` làm mô hình ghi dữ liệu quan hệ.
2. Tạo `ProductViewDocument` làm mô hình đọc hoặc tìm kiếm trong MongoDB.
3. Chuyển đổi dữ liệu một cách tường minh ở application service hoặc một mapper có kiểm thử.

Hai model có thể dùng một số trường trùng tên, nhưng không phải có cùng toàn bộ cấu trúc.

### 5.5. Nhầm repository scanning với component scanning và entity scanning

| Cơ chế | Đối tượng quét | Ví dụ |
| --- | --- | --- |
| Spring component scan | Bean ứng dụng như `@Service`, `@Configuration`, `@Component` | `@SpringBootApplication` / `@ComponentScan` |
| Spring Data repository scan | Các repository interface để Spring Data tạo proxy | `@EnableMongoRepositories` / `@EnableJpaRepositories` |
| JPA entity scan | Các class entity cần JPA quản lý | `@Entity`, `@EntityScan` hoặc cơ chế auto-configuration |
| MongoDB mapping context | Các kiểu document và metadata mapping MongoDB | `@Document`, mapping context/`MongoTemplate` |

Đổi `@ComponentScan` không bảo đảm sửa được một repository được gán sai store. Ngược lại, `@EnableMongoRepositories` không có nghĩa mọi class `@Document` đều trở thành repository. Trong Spring Boot, một số tùy chỉnh vùng quét entity còn ảnh hưởng nhiều Spring Data stores; kiểm tra riêng phần entity mapping nếu model nằm ngoài cấu trúc package mặc định.

## 6. Trường hợp có cả MongoDB đồng bộ và reactive

Spring Data MongoDB có hai dòng API:

| Đồng bộ (imperative) | Reactive |
| --- | --- |
| `MongoRepository<T, ID>` | `ReactiveMongoRepository<T, ID>` |
| `MongoTemplate` | `ReactiveMongoTemplate` |
| Thường trả về entity, `List`, `Optional` | Trả về `Mono`, `Flux` |
| `@EnableMongoRepositories` | `@EnableReactiveMongoRepositories` |
| `mongoTemplateRef` | `reactiveMongoTemplateRef` |

Ví dụ repository reactive riêng:

~~~java
package com.example.catalog.persistence.mongodb.reactive;

import com.example.catalog.persistence.mongodb.model.ProductViewDocument;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ProductViewReactiveRepository
        extends ReactiveMongoRepository<ProductViewDocument, String> {

    Flux<ProductViewDocument> findBySkuStartingWith(String prefix);
}
~~~

Nếu dùng cả imperative và reactive repositories trong cùng ứng dụng, đặt interface reactive vào package **riêng** rồi giới hạn quét:

~~~java
@EnableReactiveMongoRepositories(
    basePackages = "com.example.catalog.persistence.mongodb.reactive",
    reactiveMongoTemplateRef = "reactiveMongoTemplate"
)
~~~

Bean `reactiveMongoTemplate` phải tồn tại (thường do Boot tạo khi khai báo starter reactive và cấu hình phù hợp). Nếu cần đồng thời hai dòng API, xác nhận hai template đang trỏ đến đúng MongoDB database. Không dùng `MongoRepository` bên trong reactive event loop rồi giả định thao tác trở thành non-blocking; gọi API chặn trên event loop có thể làm giảm khả năng xử lý yêu cầu.

**Spring Data JPA không tự trở thành reactive khi được dùng cạnh Reactive MongoDB.** Nếu cần dữ liệu quan hệ với API reactive, cân nhắc Spring Data R2DBC theo đúng ràng buộc của hệ thống; khi đó repository R2DBC cũng cần phạm vi quét riêng và interface tương ứng.

## 7. Kiểm tra wiring tại thời điểm khởi động

Repository compile được chưa chứng minh ứng dụng đã tạo đúng bean cho đúng store. Khi xác minh, nên có đủ **database thử nghiệm** để ApplicationContext khởi động thực sự: có thể dùng Testcontainers cho PostgreSQL và MongoDB hoặc hai instance thử nghiệm được quản lý theo môi trường.

### 7.1. Đọc log cấu hình repository

Trong profile kiểm thử, có thể bật log:

~~~yaml
logging:
  level:
    org.springframework.data.repository.config: DEBUG
~~~

Khi nhiều Spring Data module xuất hiện, log có thể ghi nhận việc vào strict mode và số lượng repository interface được tìm thấy theo từng module. Một thông điệp về strict mode **tự nó không phải lỗi**: cần xem Spring phát hiện đúng interface của JPA/MongoDB hay chưa.

Các dấu hiệu cần điều tra gồm:

- `Could not safely identify store assignment for repository candidate ...`: repository ứng viên không đủ thông tin để quyết định module nào phụ trách.
- `Found 0 ... repository interfaces` khi bạn kỳ vọng có repository: package quét sai, repository nằm ngoài package, hoặc interface không đáp ứng tiêu chí.
- `BeanDefinitionOverrideException` hoặc thông báo trùng bean name: hai repository/bean cấu hình bị đăng ký dưới cùng tên.
- `Not a managed type`: entity JPA không được quản lý đúng, dù repository JPA đã được phát hiện.
- Thiếu `mongoTemplate`, `entityManagerFactory` hoặc `transactionManager`: hạ tầng tương ứng chưa có hoặc bean reference trong cấu hình sai.

Đừng dựa riêng vào nội dung log để kết luận toàn bộ cấu hình đúng. Tiếp tục kiểm tra bean đã đăng ký và thực hiện thao tác đọc/ghi có kiểm soát.

### 7.2. Kiểm tra repository factory thực tế

Một test toàn ứng dụng có thể xác nhận hai repository cùng tồn tại và `FactoryBean` của chúng thuộc đúng module:

~~~java
package com.example.catalog;

import com.example.catalog.persistence.jpa.repository.ProductJpaRepository;
import com.example.catalog.persistence.mongodb.repository.ProductViewMongoRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.data.jpa.repository.support.JpaRepositoryFactoryBean;
import org.springframework.data.mongodb.repository.support.MongoRepositoryFactoryBean;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class RepositoryWiringTest {
    @Autowired
    ApplicationContext context;

    @Test
    void repositoriesBelongToExpectedModules() {
        assertThat(context.getBean(ProductJpaRepository.class)).isNotNull();
        assertThat(context.getBean(ProductViewMongoRepository.class)).isNotNull();

        // Dấu & lấy chính FactoryBean, không lấy repository proxy.
        assertThat(context.getBean("&productJpaRepository"))
            .isInstanceOf(JpaRepositoryFactoryBean.class);

        assertThat(context.getBean("&productViewMongoRepository"))
            .isInstanceOf(MongoRepositoryFactoryBean.class);
    }
}
~~~

Ví dụ giả định bean repository sử dụng **tên mặc định** từ interface. Nếu dự án đặt tên bean tùy biến, cần đổi chuỗi truyền vào `getBean()` cho đúng. `@SpringBootTest` tải context thật nên phải cấp datasource, MongoDB endpoint và schema cần thiết cho profile test. Test này kiểm tra factory/wiring; để kiểm chứng truy vấn và mapping, cần thêm **integration test thực sự** trên database thử nghiệm.

Các slice như `@DataJpaTest` và `@DataMongoTest` hữu ích khi kiểm tra riêng từng store, nhưng kiểm thử slice không thay thế việc khởi động context kết hợp để phát hiện lỗi cấu hình giữa hai module.

### 7.3. Kiểm tra thao tác của từng repository

Với database test được cô lập:

1. Lưu một `ProductJpaEntity` bằng `ProductJpaRepository.save()`; đọc lại bằng `findById()` và xác nhận bản ghi nằm trong PostgreSQL.
2. Lưu một `ProductViewDocument` bằng `ProductViewMongoRepository.save()`; đọc lại bằng `findById()` và xác nhận document nằm trong collection `product_views`.
3. Gọi `findBySku()` ở hai repository, so sánh kết quả mong đợi và dọn dữ liệu test.

Nếu test kết nối MongoDB qua `MongoTemplate` nhưng repository của MongoDB không được tạo, hãy quay lại phần repository scan; `MongoTemplate` sẵn sàng là điều kiện cần cho thao tác MongoDB, **không chứng minh** repository interface đã được Spring đăng ký.

## 8. Lưu ý về transaction và đồng bộ dữ liệu giữa hai store

Việc mỗi repository được quét đúng **không mang lại một transaction phân tán tự động**. Ví dụ:

~~~java
// Đây là thứ tự nghiệp vụ minh họa:
ProductJpaEntity savedOrder = productJpaRepository.save(jpaEntity);
productViewMongoRepository.save(mongoDocument);
~~~

Nếu lệnh ghi JPA thành công nhưng MongoDB thất bại, hệ thống có thể đang lưu hai trạng thái khác nhau. `@Transactional` thông thường áp dụng theo transaction manager được chọn, ví dụ `JpaTransactionManager` cho JPA; nó không tự biến hai data store thành một transaction nguyên tử.

Các lựa chọn kiến trúc khi cần đồng bộ:

- **Synchronous best effort:** ghi hai bên và xử lý lỗi/đền bù ở tầng nghiệp vụ, phù hợp khi chấp nhận hạn chế về tính nguyên tử.
- **Transactional outbox:** lưu thay đổi nghiệp vụ và event trong cùng giao dịch JPA, rồi worker đọc outbox để cập nhật MongoDB, có retry và idempotency.
- **Event-driven projection:** cập nhật MongoDB như read model bất đồng bộ; thiết kế trạng thái cuối cùng nhất quán và theo dõi độ trễ.

MongoDB transaction riêng yêu cầu cấu hình và topology MongoDB phù hợp, và cũng **không tự bao trùm transaction JPA**. Hãy quyết định chiến lược nhất quán dữ liệu ở cấp use case, không đặt kỳ vọng đó vào annotation quét repository.

## 9. Bảng xử lý lỗi theo triệu chứng

| Triệu chứng | Hướng nguyên nhân | Việc cần kiểm tra |
| --- | --- | --- |
| Cảnh báo `Could not safely identify store assignment` | `CrudRepository` chung, domain thiếu annotation, hoặc domain dùng nhiều annotation store | Kiểu base repository, `@Entity`/`@Document`, cấu hình package |
| Mongo repository không được tạo | Repository ở ngoài `basePackageClasses`, hoặc auto-configuration bị vô hiệu hóa | Package thực tế, `@EnableMongoRepositories`, phụ thuộc Spring Data MongoDB |
| JPA repository báo `Not a managed type` | Entity không thuộc entity scan của JPA hoặc dùng nhầm document MongoDB | `@Entity`, vị trí model, cấu hình JPA entity scanning |
| Bean repository trùng tên | Hai interface cùng simple name hoặc đăng ký lặp | Tên interface, bean naming và hai phạm vi quét |
| `No bean named 'mongoTemplate'` | `mongoTemplateRef` sai hoặc Boot không tạo MongoTemplate | Bean MongoTemplate, URI/connection và cấu hình custom |
| Repository hoạt động nhưng truy vấn nhầm database | Template/factory trỏ sai database hoặc config môi trường sai | `mongoTemplateRef`, `MongoDatabaseFactory`, URI và profile |
| Reactive repository không tìm thấy | Dùng bộ quét imperative cho interface reactive | `@EnableReactiveMongoRepositories` và package riêng |
| JPA commit rồi Mongo thất bại | Hai store không nằm trong cùng transaction | Thiết kế retry, outbox, idempotent projection |

Một số lỗi dễ bị hiểu sai: cảnh báo strict mode không đồng nghĩa ứng dụng bị lỗi, và không tìm thấy repository không nhất thiết do sai database URI. **Repository scanning diễn ra ở mức cấu hình Spring**, còn lỗi kết nối/xác thực đến từ hạ tầng data store; nên phân biệt hai tầng trong quá trình chẩn đoán.

## 10. Quy trình áp dụng trong dự án thật

Trước khi đưa nhiều Spring Data module vào cùng ứng dụng:

1. Liệt kê **store nào thực sự cần repository**, store nào chỉ dùng template hoặc client.
2. Tách package theo mỗi store và dùng tên repository có hậu tố rõ ràng: `JpaRepository`, `MongoRepository`, `ReactiveMongoRepository`.
3. Tách class domain theo cơ chế mapping; tránh gắn `@Entity` và `@Document` lên cùng class chỉ để tái sử dụng dữ liệu.
4. Đánh dấu `@NoRepositoryBean` cho các interface repository cơ sở generic.
5. Nếu cần bật repository scan thủ công, giới hạn `basePackageClasses` hoặc `basePackages` cho từng module. Chỉ định đúng template/factory khi có nhiều kết nối.
6. Dùng log cấu hình để xem repository được phát hiện; khởi động toàn bộ context trên môi trường test và xác minh đúng `FactoryBean`.
7. Kiểm thử CRUD trên **từng database thử nghiệm** và xác nhận dữ liệu đi đến đúng collection/bảng.
8. Xác định rõ transaction manager, chính sách lỗi và cơ chế đồng bộ khi một use case ghi qua cả hai store.

## 11. Bài thực hành

**Tình huống:** Ứng dụng catalog có `spring-boot-starter-data-jpa` và `spring-boot-starter-data-mongodb`. Nhà phát triển thêm:

~~~java
public interface InventoryRepository extends CrudRepository<Inventory, String> {
}
~~~

`Inventory` chưa có `@Entity` hoặc `@Document`. Khi chạy ứng dụng, Spring Data thông báo không thể xác định repository thuộc store nào.

**Yêu cầu A:** Nếu Inventory là document MongoDB, hãy sửa thiết kế tối thiểu để repository thuộc đúng module.

**Đáp án tham khảo:**

~~~java
@Document(collection = "inventory")
public class Inventory {
    @org.springframework.data.annotation.Id
    private String id;
    // Các trường nghiệp vụ và constructor/getter.
}

public interface InventoryMongoRepository
        extends MongoRepository<Inventory, String> {
}
~~~

Đặt interface vào package MongoDB repository và đảm bảo package đó được quét bởi `@EnableMongoRepositories` hoặc auto-configuration phù hợp. `@Document` giúp mapping, còn `MongoRepository` thể hiện store rõ ràng.

**Yêu cầu B:** Nếu một service cần cùng lúc `InventoryJpaRepository` và `InventoryMongoRepository`, có nên dùng một class Inventory mang cả `@Entity` và `@Document`?

**Đáp án:** Không nên. Tạo entity JPA và document MongoDB tách biệt, ánh xạ dữ liệu ở service/mapper; chỉ định repository scan theo từng package. Nếu dữ liệu cần đồng bộ qua hai store, thiết kế transaction/outbox hoặc cơ chế khắc phục phù hợp.

**Yêu cầu C:** Bạn nhận log `Found 0 MongoDB repository interfaces`, nhưng code `MongoTemplate.find(...)` vẫn trả dữ liệu. Điều này có mâu thuẫn không?

**Đáp án:** Không. MongoTemplate dùng trực tiếp hạ tầng MongoDB, không phụ thuộc có repository interface hay không. Cần kiểm tra package scan nếu kỳ vọng MongoDB repository được tạo; nếu cố ý dùng template thuần, số repository bằng 0 là hợp lệ.

## Tài liệu tham khảo

- [Spring Data Commons — Repository abstraction](https://docs.spring.io/spring-data/commons/reference/repositories.html): repository, strict matching và nhiều Spring Data module.
- [Spring Data MongoDB — Repositories](https://docs.spring.io/spring-data/mongodb/reference/repositories.html): repository MongoDB, mapping và các biến thể API.
- [Spring Data MongoDB — Template API](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): `MongoTemplate` và các cách truy cập MongoDB không qua repository.
- [Spring Data JPA — Repositories](https://docs.spring.io/spring-data/jpa/reference/repositories.html): JPA repository configuration và `JpaRepository`.
- [Spring Boot — Data Access](https://docs.spring.io/spring-boot/reference/data/index.html): auto-configuration, cấu hình database và kiểm thử với Spring Boot.
