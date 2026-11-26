# Phạm vi quét entity và kích hoạt repository

## 1. Vì sao cấu hình kết nối đúng vẫn chưa đủ?

Một ứng dụng Spring Boot có thể kết nối được Couchbase nhưng vẫn không tạo ra bean `ProductRepository`, không nhận diện entity `ProductDocument` hoặc truy cập nhầm collection. Nguyên nhân không nhất thiết ở connection string hay bucket: **Spring cần biết nên tìm class nào, ở package nào và đăng ký chúng theo cơ chế nào**.

Trong module **SPRING_DATA_COUCHBASE**, các API như `CouchbaseRepository`, `ReactiveCouchbaseRepository` và `CouchbaseTemplate` dựa trên mapping document và cấu hình hạ tầng. Phạm vi quét (*scanning*) vì thế là cầu nối giữa cách tổ chức mã Java với việc đọc/ghi vào bucket, scope và collection trên server.

Bài học thuộc chương **Cấu hình kết nối**, tập trung vào hai nhiệm vụ:

1. **Quét entity:** xác định các class đại diện document và metadata mapping.
2. **Kích hoạt repository:** phát hiện các interface repository, tạo proxy/bean và gắn chúng với hạ tầng Spring Data Couchbase.

Sau bài học, bạn có thể phân biệt ba cơ chế quét thường bị nhầm, dùng cấu trúc package mặc định hoặc cấu hình quét tường minh, chọn repository đồng bộ hay reactive, xử lý lỗi bean không xuất hiện và kiểm chứng khả năng truy cập collection thật.

Các ví dụ dựa trên **Spring Boot 3.x** và Spring Data Couchbase tương thích do Boot quản lý. Với phiên bản khác, hãy xác minh API và điều kiện auto-configuration của phiên bản dự án.

## 2. Ba phạm vi quét là ba vấn đề khác nhau

Trong một ứng dụng Spring có ít nhất ba cơ chế dễ bị coi là một:

| Cơ chế | Tìm gì? | Class/annotation thường liên quan | Kết quả |
| --- | --- | --- | --- |
| Component scan | Các bean ứng dụng như service, controller, configuration | `@SpringBootApplication`, `@ComponentScan`, `@Service` | Bean thông thường trong `ApplicationContext` |
| Entity scan / mapping context | Các class document cùng metadata mapping | `@Document`, `@Id`, `@Scope`, `@Collection`, `@EntityScan` hoặc hook cấu hình mapping | Metadata phục vụ chuyển đổi Java object và Couchbase document |
| Repository scan | Các interface Spring Data repository | `CouchbaseRepository`, `@EnableCouchbaseRepositories`, `@EnableReactiveCouchbaseRepositories` | Repository proxy/bean cho DI |

**Ví dụ:** một class `@Document` không cần `@Service` mới trở thành entity, và một interface `CouchbaseRepository` không cần `@Repository` chỉ để Spring Data nhận diện theo cơ chế repository scanning. Ngược lại, component scan tìm thấy một `@Service` không bảo đảm repository interface mà service inject đã được đăng ký.

~~~mermaid
flowchart TD
    A["@SpringBootApplication"] --> B["Component scan"]
    A --> C["Auto-configuration packages"]
    B --> D["@Service / @Controller / @Configuration"]
    C --> E["Repository discovery"]
    C --> F["Entity mapping"]
    E --> G["ProductRepository bean"]
    F --> H["ProductDocument metadata"]
    D --> I["ProductService bean"]
    G --> I
    H --> J["CouchbaseTemplate + Converter"]
    G --> J
    J --> K["Cluster / Bucket / Scope / Collection"]
~~~

Sơ đồ trình bày trường hợp Boot auto-configuration mặc định; nếu chủ động khai báo annotation scan hoặc cấu hình Java, các package nguồn có thể được thay đổi. `@ComponentScan(scanBasePackages = ...)` **không phải** cách tương đương để thay mọi phạm vi entity/repository scan.

## 3. Cấu trúc package được Spring Boot tự nhận diện

Trường hợp đơn giản nhất là đặt main class ở **package cha** của entity, repository và service.

~~~text
src/main/java/
└── com/example/catalog/
    ├── CatalogApplication.java
    ├── domain/
    │   └── ProductDocument.java
    ├── repository/
    │   └── ProductRepository.java
    └── service/
        └── ProductService.java
~~~

Main class:

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

Với starter và cấu hình kết nối phù hợp, Spring Boot thường dùng package của main class làm điểm gốc auto-configuration. Các package con `domain`, `repository`, `service` vì thế nằm trong vùng tìm kiếm tự nhiên.

### 3.1. Document entity

~~~java
package com.example.catalog.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("commerce")
@Collection("products")
public class ProductDocument {

    @Id
    private String id;

    private String sku;
    private String name;

    protected ProductDocument() {
    }

    public ProductDocument(String id, String sku, String name) {
        this.id = id;
        this.sku = sku;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }
}
~~~

Các annotation phục vụ những vai trò riêng:

- `@Document`: xác định class là document được Spring Data Couchbase mapping.
- `@Id`: đánh dấu document key; không phải một cột khóa chính SQL.
- `@Scope("commerce")` và `@Collection("products")`: chỉ định scope/collection mà entity sử dụng **bên trong bucket mặc định**.

Các annotation không tự tạo bucket, scope hay collection trên Couchbase. Những tài nguyên đó phải tồn tại trước khi ứng dụng thực hiện I/O.

### 3.2. Repository interface

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.ProductDocument;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<ProductDocument, String> {
}
~~~

Từ interface, Spring Data tạo repository proxy theo hạ tầng Couchbase khi interface nằm trong phạm vi repository scan. Không phải tự viết lớp `ProductRepositoryImpl` cho các phương thức CRUD cơ bản.

### 3.3. Service tiêu thụ repository

~~~java
package com.example.catalog.service;

import com.example.catalog.domain.ProductDocument;
import com.example.catalog.repository.ProductRepository;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    public Optional<ProductDocument> findById(String id) {
        return products.findById(id);
    }
}
~~~

`ProductService` được đăng ký nhờ component scan. `ProductRepository` là repository proxy. `ProductDocument` là metadata mapping; **không phải bean singleton ứng dụng** được inject như service.

## 4. Điều kiện để Spring Boot kích hoạt Couchbase repository

Khi dùng Spring Boot, cần có starter Spring Data Couchbase cùng các điều kiện auto-configuration thích hợp:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-couchbase</artifactId>
</dependency>
~~~

Cấu hình kết nối ví dụ:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET:inventory}"
~~~

Ứng dụng sử dụng các thuộc tính `spring.couchbase.*` để cấu hình kết nối SDK và `spring.data.couchbase.bucket-name` để chọn bucket mặc định cho Spring Data.

**Trong trường hợp thông thường, bạn không bắt buộc phải thêm `@EnableCouchbaseRepositories`**. Boot có thể kích hoạt quét repository tự động theo những package được auto-configuration nhận diện, miễn đáp ứng các điều kiện classpath và bean liên quan.

Tuy nhiên, không nên suy ra “có starter” là chắc chắn proxy được tạo. Repository vẫn có thể bị bỏ sót nếu nằm ngoài vùng quét, bị vô hiệu hóa theo cấu hình, thuộc loại repository không phù hợp hoặc bị can thiệp bởi Java configuration khác.

## 5. Phân biệt phạm vi quét với phạm vi dữ liệu Couchbase

Giả sử:

~~~text
Couchbase Cluster
└── Bucket: inventory
    ├── Scope: commerce
    │   ├── Collection: products
    │   └── Collection: orders
    └── Scope: _default
        └── Collection: _default
~~~

Có hai quyết định hoàn toàn khác nhau:

- **Package scan:** có tìm thấy `com.example.catalog.domain.ProductDocument` và `com.example.catalog.repository.ProductRepository` hay không?
- **Data keyspace:** entity `ProductDocument` dùng bucket `inventory`, scope `commerce`, collection `products` hay một keyspace khác?

Bảng đối chiếu:

| Cấu hình | Giải quyết vấn đề | Không giải quyết |
| --- | --- | --- |
| `@EnableCouchbaseRepositories(basePackageClasses = ...)` | Interface repository nào được đăng ký | Bucket hoặc collection nào chứa dữ liệu |
| `@EntityScan(basePackageClasses = ...)` trong Boot | Package nào là nguồn tìm entity cho mapping | Repository interface nào được tạo |
| `getMappingBasePackage()` ở Java config | Package tìm document entity | Phạm vi repository scan |
| `spring.data.couchbase.bucket-name` | Bucket mặc định | Java package của entity/repository |
| `@Scope` / `@Collection` | Scope/collection của entity | Tạo Spring bean hoặc mở rộng package scan |

Đừng cố sửa lỗi `NoSuchBeanDefinitionException` của repository bằng cách đổi tên collection hoặc tạo index. Ngược lại, khi repository bean đã tồn tại nhưng ghi nhầm keyspace, cần kiểm tra bucket/mapping chứ không mở rộng scan tùy tiện.

## 6. Khi repository nằm ngoài package của main application

Giả sử một dự án lớn dùng các module Java riêng:

~~~text
com.example.app
└── InventoryApplication.java

com.acme.shared.catalog
├── model/
│   └── ProductDocument.java
└── persistence/
    └── ProductRepository.java
~~~

Vì `com.acme.shared.catalog` không phải package con của `com.example.app`, cách quét mặc định của Boot **có thể không tìm thấy** repository/entity. Một cách xử lý là cấu hình tường minh.

### 6.1. Quét repository đồng bộ bằng marker class

~~~java
package com.example.app.config;

import com.acme.shared.catalog.persistence.ProductRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.couchbase.repository.config.EnableCouchbaseRepositories;

@Configuration
@EnableCouchbaseRepositories(
        basePackageClasses = ProductRepository.class
)
public class CouchbaseRepositoryScanConfiguration {
}
~~~

`basePackageClasses` lấy package chứa `ProductRepository` để làm điểm bắt đầu quét. Cách viết này giúp compiler phát hiện một số lỗi khi đổi tên package, tốt hơn việc dùng một string viết tay.

Cùng một annotation cũng hỗ trợ xác định package qua tên chuỗi, ví dụ:

~~~java
@EnableCouchbaseRepositories(
        basePackages = "com.acme.shared.catalog.persistence"
)
~~~

Chỉ cần chọn **một cách khai báo phù hợp**. Marker class thường dễ refactor hơn; string hữu ích khi package chưa có interface/class dùng làm marker.

### 6.2. Tách riêng việc quét entity

Với Spring Boot auto-configuration, có thể chỉ rõ package chứa document class:

~~~java
package com.example.app.config;

import com.acme.shared.catalog.model.ProductDocument;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@EntityScan(basePackageClasses = ProductDocument.class)
public class CouchbaseEntityScanConfiguration {
}
~~~

`@EntityScan` cung cấp các package entity cho cơ chế auto-configuration của Spring Boot và những Spring Data store được Boot hỗ trợ. **Nó không tạo repository proxy**; vẫn cần repository scan đúng. Trong dự án dùng nhiều Spring Data store (chẳng hạn JPA và Couchbase), lựa chọn vùng quét entity cần được đánh giá tổng thể thay vì tùy tiện quét mọi package.

Với Spring Data Couchbase cấu hình thủ công bằng `AbstractCouchbaseConfiguration`, có thể chủ động điều khiển phạm vi mapping bằng hook `getMappingBasePackage()` như phần tiếp theo.

### 6.3. Không thay tất cả bằng component scan

Ví dụ:

~~~java
@SpringBootApplication(
        scanBasePackages = {
                "com.example.app",
                "com.acme.shared.catalog"
        }
)
~~~

Nó có thể mở rộng **component scan**, nhưng không nên dựa vào nó như một lời cam kết sẽ thay cả repository scan và entity scan. Auto-configuration packages, mapping context và annotation enable repository có hợp đồng riêng. Khi cố tình đặt repository/entity ngoài root, khai báo trực tiếp các phạm vi liên quan sẽ dễ hiểu và dễ kiểm chứng hơn.

## 7. Java config qua `AbstractCouchbaseConfiguration`

Một số ứng dụng không dùng cấu hình tự động hoàn toàn mà kế thừa `AbstractCouchbaseConfiguration` để khai báo hạ tầng Spring Data Couchbase. Khi đó phạm vi entity và repository cần được quyết định rõ.

Ví dụ rút gọn:

~~~java
package com.example.app.config;

import com.acme.shared.catalog.persistence.ProductRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.couchbase.config.AbstractCouchbaseConfiguration;
import org.springframework.data.couchbase.repository.config.EnableCouchbaseRepositories;

@Configuration
@EnableCouchbaseRepositories(
        basePackageClasses = ProductRepository.class
)
public class ManualCouchbaseConfiguration
        extends AbstractCouchbaseConfiguration {

    @Override
    public String getConnectionString() {
        return System.getenv("COUCHBASE_CONNECTION_STRING");
    }

    @Override
    public String getUserName() {
        return System.getenv("COUCHBASE_USERNAME");
    }

    @Override
    public String getPassword() {
        return System.getenv("COUCHBASE_PASSWORD");
    }

    @Override
    public String getBucketName() {
        return "inventory";
    }

    @Override
    protected String getMappingBasePackage() {
        return "com.acme.shared.catalog.model";
    }
}
~~~

Ý nghĩa:

1. Bốn phương thức `getConnectionString()`, `getUserName()`, `getPassword()`, `getBucketName()` cung cấp cluster, user và bucket mặc định cho Spring Data.
2. `getMappingBasePackage()` cho biết nơi tìm metadata mapping của document class.
3. `@EnableCouchbaseRepositories` cho biết nơi quét các interface repository.

Đoạn trên minh họa API kết nối của lớp cơ sở và đường đi scanning. Trong ứng dụng thật, nên bind thông tin kết nối bằng `@ConfigurationProperties` hoặc một bean settings thay vì gọi trực tiếp `System.getenv()` ở từng getter; quản lý secret theo môi trường và kiểm tra thiếu biến một cách chủ động.

**Không đồng thời tạo nhiều lớp cấu hình đầy đủ chỉ vì muốn mở rộng phạm vi quét.** Các bean hạ tầng có thể trùng hoặc làm Spring Boot auto-configuration lùi bước theo điều kiện bean. Tốt hơn là khai báo phạm vi quét nhất quán trong chiến lược cấu hình đang dùng.

## 8. Repository đồng bộ và reactive phải được nhận diện đúng kiểu

Spring Data Couchbase hỗ trợ API đồng bộ và reactive. Hai loại repository có interface và cơ chế scan khác nhau.

### 8.1. Repository đồng bộ (imperative)

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<ProductDocument, String> {
}
~~~

Kích hoạt quét tường minh khi cần:

~~~java
import org.springframework.data.couchbase.repository.config.EnableCouchbaseRepositories;

@EnableCouchbaseRepositories(
        basePackageClasses = ProductRepository.class
)
~~~

Kết quả của `findById` theo kiểu `Optional<ProductDocument>`; `save` trả về entity. Thao tác này phù hợp với mô hình ứng dụng đồng bộ.

### 8.2. Repository reactive

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Mono;

public interface ReactiveProductRepository
        extends ReactiveCouchbaseRepository<ProductDocument, String> {

    Mono<ProductDocument> findBySku(String sku);
}
~~~

Kích hoạt quét reactive tường minh khi cần:

~~~java
import org.springframework.data.couchbase.repository.config.EnableReactiveCouchbaseRepositories;

@EnableReactiveCouchbaseRepositories(
        basePackageClasses = ReactiveProductRepository.class
)
~~~

Sử dụng starter `spring-boot-starter-data-couchbase-reactive` và cấu hình API theo thiết kế ứng dụng. Một `Mono` hoặc `Flux` là pipeline reactive, khác với việc gọi repository đồng bộ rồi bọc kết quả bằng `Mono.just(...)`.

### 8.3. Không dùng annotation sai loại repository

| Bạn muốn | Interface thường dùng | Annotation enable tường minh |
| --- | --- | --- |
| Đồng bộ | `CouchbaseRepository` | `@EnableCouchbaseRepositories` |
| Reactive | `ReactiveCouchbaseRepository` | `@EnableReactiveCouchbaseRepositories` |

Khi cả hai loại có mặt, tránh đưa mọi interface vào chung một vùng quét mà không kiểm soát loại repository. Phân chia package theo chế độ truy cập là một chiến lược rõ ràng:

~~~text
com.example.catalog
├── repository/
│   └── blocking/
│       └── ProductRepository.java
└── reactive/
    └── ReactiveProductRepository.java
~~~

Ví dụ một cấu hình scan có chủ đích:

~~~java
@Configuration
@EnableCouchbaseRepositories(
        basePackageClasses = ProductRepository.class
)
@EnableReactiveCouchbaseRepositories(
        basePackageClasses = ReactiveProductRepository.class
)
class CouchbaseRepositoryModesConfiguration {
}
~~~

Ví dụ giả định hai interface thuộc các package khác nhau và dự án thật sự cần cả hai loại. **Không bật cả hai chỉ vì starter cho phép**; nếu chọn WebFlux end-to-end, cân nhắc chỉ dùng reactive. Cũng không được tự ý tạo hai `Cluster` cho cùng một cluster chỉ để tách kiểu repository.

## 9. Interface cơ sở dùng chung và `@NoRepositoryBean`

Các dự án có thể tạo một interface cơ sở chứa quy ước chung cho mọi repository. Nếu interface đó xuất hiện trong vùng scan mà không gắn với một entity cụ thể, Spring Data có thể cố tạo bean cho chính nó.

Ví dụ:

~~~java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

@NoRepositoryBean
public interface BaseCouchbaseRepository<T, ID>
        extends CouchbaseRepository<T, ID> {
}
~~~

Repository thực tế:

~~~java
public interface ProductRepository
        extends BaseCouchbaseRepository<ProductDocument, String> {
}
~~~

`@NoRepositoryBean` báo Spring Data **không tạo bean cho interface cơ sở**. Đây không phải annotation để vô hiệu hóa mọi repository con, cũng không liên quan trực tiếp đến bucket name hay SQL++ index.

Nếu bạn chủ động triển khai base repository tùy chỉnh, cần cấu hình repository factory/base class theo API Spring Data phù hợp; chỉ dùng `@NoRepositoryBean` không tự động gắn một implementation do bạn viết.

## 10. Phạm vi quét không phải cơ chế định tuyến nhiều bucket

Một tình huống hay gặp: entity `ProductDocument` và `OrderDocument` đặt ở hai package khác nhau, nhưng cùng một `CouchbaseClientFactory` mặc định trỏ tới bucket `inventory`.

Mở rộng `@EnableCouchbaseRepositories` sang package chứa `OrderRepository` **không làm repository đó tự dùng bucket `orders`**. Phạm vi quét quyết định **có bean repository nào**, trong khi factory/template và mapping quyết định **đích dữ liệu**.

~~~mermaid
flowchart LR
    A["Package repository.products"] --> C["Repository proxy"]
    B["Package repository.orders"] --> C
    C --> D["CouchbaseClientFactory mặc định"]
    D --> E["Bucket: inventory"]
    E --> F["Scope + Collection theo mapping"]
~~~

Nếu cần nhiều bucket thật sự, phải thiết kế factory/template/repository gắn đúng bucket và phân biệt các bean thích hợp theo API của phiên bản Spring Data. Không đổi `@Collection("orders")` để kỳ vọng chuyển từ bucket `inventory` sang bucket `orders`.

Tương tự, đưa hai repository vào cùng package không đảm bảo chúng dùng cùng entity class hoặc cùng collection; mỗi repository khai báo generic entity riêng và entity có metadata mapping riêng.

## 11. Kết nối mapping với truy vấn SQL++ và chỉ mục

Khi quét đúng entity/repository, bạn vẫn phải xác minh truy cập dữ liệu.

Các thao tác theo document ID như:

~~~java
repository.findById("product::SKU-001");
~~~

thường dùng Key-Value API của Couchbase và không đòi hỏi secondary index SQL++. Trái lại, phương thức truy vấn theo thuộc tính:

~~~java
// Đặt trong ProductRepository:
java.util.List<ProductDocument> findBySku(String sku);
~~~

thường được Spring Data chuyển thành truy vấn SQL++ theo keyspace đã mapping. Query service và index tương ứng phải tồn tại, ví dụ minh họa:

~~~sql
CREATE INDEX ix_products_sku
ON `inventory`.`commerce`.`products`(`sku`);
~~~

Một repository được tạo thành công **không có nghĩa** index này đã tồn tại hoặc query đã sẵn sàng. Để tránh nhầm lỗi scanning với lỗi SQL++, hãy xác nhận lần lượt:

1. Bean repository có được tạo trong Spring context?
2. Entity có ánh xạ đúng bucket/scope/collection?
3. KV theo ID có chạy được không?
4. Truy vấn SQL++ có index và quyền thích hợp không?

Đọc theo ID, truy vấn theo thuộc tính, TTL, CAS, giao dịch và lựa chọn API reactive là những vấn đề độc lập với việc Spring phát hiện package nào. Tuy nhiên, cấu hình scanning đúng là điều kiện để các API Spring Data tham gia luồng dữ liệu.

## 12. Tìm lỗi khi Spring không tạo repository bean

Dấu hiệu phổ biến khi inject repository là một lỗi dạng:

~~~text
No qualifying bean of type
'com.example.catalog.repository.ProductRepository'
available
~~~

Bảng chẩn đoán:

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Spring không có bean `ProductRepository` | Repository nằm ngoài vùng quét | Kiểm tra vị trí main class, `@EnableCouchbaseRepositories` và package marker |
| Service không được tạo | Component scan thiếu package `@Service` | Kiểm tra component scan, `@SpringBootApplication` |
| Repository bean có nhưng ánh xạ entity sai | Entity chưa có metadata phù hợp hoặc mapping scan thiếu | Kiểm tra `@Document`, `@Id`, `@EntityScan`/`getMappingBasePackage()` |
| Reactive repository không xuất hiện | Sai starter/annotation enable hoặc sai interface | Kiểm tra `ReactiveCouchbaseRepository` và `@EnableReactiveCouchbaseRepositories` |
| Tạo hai bean trùng repository | Nhiều vùng scan chồng lấn hoặc cấu hình enable lặp | Thu hẹp scan và dùng một cấu hình chịu trách nhiệm |
| Boot tự cấu hình bị thay đổi | Custom `AbstractCouchbaseConfiguration`/bean khác can thiệp | Kiểm tra hạ tầng Spring Data và bean definitions |
| Repo có bean nhưng `findById` lỗi | Sai cluster/bucket/collection hoặc RBAC | Kiểm tra connection, mapping và quyền |
| `findById` chạy, `findBySku` lỗi | Query service/index hoặc quyền SQL++ | Kiểm tra index đúng collection |
| Test chạy, app chính lỗi | Test slice và app có package/auto-config khác nhau | So sánh cấu hình test với app thực tế |
| Repo truy cập sai bucket | Factory/bucket config sai, không phải scan | Kiểm tra factory/template, property bucket |

### Thứ tự xử lý hiệu quả

~~~mermaid
flowchart TD
    A["Lỗi sử dụng repository"] --> B{"Có bean repository trong context?"}
    B -- "Không" --> C["Classpath, package scan, annotation enable,<br/>imperative/reactive"]
    B -- "Có" --> D{"Có metadata entity hợp lệ?"}
    D -- "Không" --> E["@Document, @Id, entity mapping scan"]
    D -- "Có" --> F{"KV theo ID truy cập được?"}
    F -- "Không" --> G["Cluster, bucket, scope, collection, RBAC"]
    F -- "Có" --> H{"Query theo thuộc tính được?"}
    H -- "Không" --> I["Query service, index, quyền SQL++"]
    H -- "Có" --> J["Kiểm chứng hoàn tất"]
~~~

Không tăng timeout hoặc sửa query index khi nguyên nhân là repository interface không được scan. Cũng không mở rộng scan ra toàn classpath chỉ để thử, vì có thể kích hoạt những interface không mong muốn và làm tăng nguy cơ xung đột bean.

## 13. Kiểm thử phạm vi quét và hành vi truy cập

### 13.1. Xác nhận proxy có trong context

Một kiểm tra nhẹ để xác nhận repository bean đã được tạo (chưa cần thực hiện I/O Couchbase) có thể viết bằng `ApplicationRunner` dành cho local:

~~~java
import com.example.catalog.repository.ProductRepository;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("local")
class RepositoryScanProbe {

    @Bean
    ApplicationRunner verifyRepositoryBean(ProductRepository repository) {
        return args -> {
            if (repository == null) {
                throw new IllegalStateException("Repository bean missing");
            }
            System.out.println("ProductRepository bean registered");
        };
    }
}
~~~

Phương thức trên nhận repository qua constructor injection của bean factory method. Nếu repository bị thiếu, Spring sẽ không tạo được runner/khởi động context. Kiểm tra này chỉ cho biết proxy có mặt, **chưa chứng minh** cluster có thể đọc bucket hay entity được ánh xạ đúng ở thao tác I/O.

### 13.2. Kiểm tra KV thật sau khi bean đã có

Tiếp theo, trên môi trường local kiểm tra truy cập entity:

~~~java
@Bean
@Profile("local")
ApplicationRunner verifyMappedKv(ProductRepository repository) {
    return args -> {
        // Không cần tạo document; Optional.empty() là hợp lệ.
        var result = repository.findById("probe::missing");
        System.out.println("KV read completed; present=" + result.isPresent());
    };
}
~~~

Ví dụ giả định bucket `inventory`, scope `commerce` và collection `products` đã tồn tại và user có quyền KV. Nếu đọc ID không tồn tại trả về `Optional.empty()` mà không exception, đường đọc KV tương ứng có thể hoạt động. Sau bước này mới kiểm tra query SQL++ theo thuộc tính với index đúng.

Tùy hệ thống, có thể dùng một kiểm thử tích hợp thay vì `ApplicationRunner`. Tránh chạy các probe như trên trong production không kiểm soát, và không in credentials vào log để gỡ lỗi.

### 13.3. Đối chiếu cả package và hạ tầng

Trước khi báo bài toán scanning đã được giải quyết, xác nhận cả hai loại điều kiện:

- **Phía Java:** main class có vị trí phù hợp; repository interface có đúng kiểu; entity có `@Document` và `@Id`; cấu hình quét không chồng lấn; không có custom bean vô tình thay hạ tầng.
- **Phía Couchbase:** cluster reachable; bucket tồn tại; scope/collection đúng; tài khoản có RBAC phù hợp; Query service và index có mặt cho truy vấn theo thuộc tính.

Một ứng dụng có thể thỏa mãn vế Java và thất bại hoàn toàn ở vế Couchbase, hoặc ngược lại. Tách hai vế giúp chẩn đoán chính xác.

## 14. Tình huống thực hành: tách domain sang shared module

Một đội chuyển `ProductDocument` và `ProductRepository` từ `com.example.catalog` sang thư viện `com.acme.shared.catalog` để nhiều service dùng chung. Sau đó `CatalogApplication` vẫn khởi động nhưng service không inject được `ProductRepository`.

Hướng thực hiện:

1. Đối chiếu vị trí main class với package của repository và entity sau khi di chuyển.
2. Khai báo `@EnableCouchbaseRepositories(basePackageClasses = ProductRepository.class)` trong lớp `@Configuration` thuộc vùng component scan.
3. Bổ sung phạm vi entity phù hợp, ví dụ `@EntityScan(basePackageClasses = ProductDocument.class)` ở cấu hình Boot hoặc `getMappingBasePackage()` nếu sử dụng `AbstractCouchbaseConfiguration`.
4. Xác nhận starter Couchbase hiện diện và không có repository scan trùng lặp.
5. Khởi động context để thấy bean `ProductRepository` được tạo.
6. Dùng `findById` trên môi trường local để kiểm tra ánh xạ tới `inventory.commerce.products`.
7. Chỉ sau đó kiểm chứng `findBySku` và index SQL++ thích hợp.

**Không nên** giải quyết bằng cách chuyển toàn bộ code dùng chung thành `@Service`, khai báo `@ComponentScan("com")` hoặc thêm tràn lan những bean `CouchbaseTemplate` mới. Những thay đổi đó không giải quyết đúng ranh giới repository/entity scanning và có thể gây vấn đề khác.

**Câu hỏi tự kiểm tra:**

1. `@SpringBootApplication(scanBasePackages = ...)` ảnh hưởng trực tiếp đến cơ chế scan nào?
2. Vì sao `@EntityScan` không thay thế `@EnableCouchbaseRepositories`?
3. Khi chỉ đổi tên collection trên entity, repository có phải được quét lại theo package mới không?
4. Khác nhau thế nào giữa lỗi “không có bean `ProductRepository`” và lỗi “`ProductRepository.findById` truy cập sai bucket”?
5. Tại sao `@NoRepositoryBean` phù hợp cho interface repository generic nhưng không dùng trên interface `ProductRepository` thực tế?

**Đáp án định hướng:** component scan, mapping scan và repository scan có mục đích riêng. Entity metadata không tự tạo proxy repository; địa chỉ collection nằm ở mapping/hạ tầng data chứ không nằm ở package scan. `@NoRepositoryBean` ngăn tạo instance cho interface cơ sở không đủ thông tin entity cụ thể.

## 15. Tổng kết

**Phạm vi quét entity** xác định lớp Java nào được Spring Data Couchbase xem là document để mapping; **kích hoạt repository** xác định interface nào trở thành bean proxy truy cập dữ liệu. Chúng khác với component scan của Spring và khác với thiết kế bucket/scope/collection phía Couchbase Server.

Trong ứng dụng Spring Boot đơn giản, cấu trúc package dưới main class cùng starter phù hợp thường đủ để auto-configuration kích hoạt repository. Khi mã nằm ngoài package gốc hoặc có Java config đặc biệt, dùng `@EntityScan`/`getMappingBasePackage()` và `@EnableCouchbaseRepositories` hoặc `@EnableReactiveCouchbaseRepositories` để diễn đạt chính xác phạm vi cần quét.

Chỉ khi cả bean repository, entity mapping và data path đã được xác minh, bạn mới có nền tảng vững để triển khai `CouchbaseTemplate`, truy vấn SQL++, index, TTL, CAS, giao dịch hoặc API reactive mà không nhầm lỗi phát hiện class với lỗi kết nối hay tính nhất quán dữ liệu.

