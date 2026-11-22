# Kích hoạt repository bằng @EnableJdbcRepositories và giới hạn vùng quét

Trong Spring Data JDBC, lập trình viên thường khai báo một interface như `OrderRepository extends CrudRepository<Order, Long>` rồi inject trực tiếp vào service. Đằng sau thao tác tưởng như đơn giản đó là bước **repository scanning**: Spring Data tìm các interface repository trong những package được phép quét, xác định kiểu aggregate và kiểu khóa chính, rồi đăng ký bean repository tương ứng.

Annotation **`@EnableJdbcRepositories`** cho phép khai báo tường minh **những package nào được tìm kiếm để tạo JDBC repository**. Cấu hình này quan trọng khi ứng dụng có nhiều module nghiệp vụ, sử dụng đồng thời nhiều công nghệ Spring Data, hoặc đặt file cấu hình khác package với repository.

Hai quy tắc nền tảng:

- Với Spring Boot và `spring-boot-starter-data-jdbc`, auto-configuration thường đã kích hoạt các Spring Data JDBC repository nằm trong vùng package mặc định. Không cần thêm `@EnableJdbcRepositories` chỉ để sử dụng CRUD.
- Khi cần kiểm soát rõ ranh giới của repository, dùng `@EnableJdbcRepositories(basePackages = ...)` hoặc `@EnableJdbcRepositories(basePackageClasses = ...)`. Giá trị thứ hai dùng marker type, giúp việc đổi tên package dễ quản lý hơn.

Bài học này tập trung vào **kích hoạt repository và giới hạn vùng quét**, đồng thời phân biệt repository scanning với component scanning, domain mapping và cấu hình kết nối database.

## 1. Repository scanning thực sự làm gì?

Xét một repository:

~~~java
package com.example.shop.sales.repository;

import com.example.shop.sales.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Ta không viết một class triển khai thủ công cho `findById(...)`, `save(...)` và `deleteById(...)`. Spring Data JDBC sử dụng cơ chế repository factory để tạo bean triển khai các phương thức cơ bản và xử lý các phương thức truy vấn được khai báo hợp lệ.

Luồng tổng quát:

~~~text
Application startup
       |
       v
Xác định package gốc của repository scan
       |
       v
Tìm các interface Spring Data repository
       |
       v
Đọc metadata: domain type, ID type, query methods
       |
       v
Đăng ký repository factory bean và repository proxy
       |
       v
Ứng dụng inject PurchaseOrderRepository vào service
       |
       v
Khi gọi repository: thực thi truy cập database qua Spring Data JDBC
~~~

**Repository scanning** chỉ quyết định interface nào được xem xét để đăng ký bean. Việc SQL có chạy được hay không còn phụ thuộc `DataSource`, mapping, bảng dữ liệu, connection và transaction. `@EnableJdbcRepositories` không tự tạo schema hoặc tự cung cấp thông tin đăng nhập database.

## 2. Spring Boot thường đã kích hoạt repository tự động

Đối với một ứng dụng Boot dùng Spring Data JDBC starter và datasource phù hợp, Boot thường tự đăng ký repository ở các *auto-configuration packages*. Những package này mặc định bắt nguồn từ package chứa `@SpringBootApplication`.

Ví dụ cấu trúc:

~~~text
src/main/java/
└── com/example/shop/
    ├── ShopApplication.java
    ├── sales/
    │   ├── domain/PurchaseOrder.java
    │   ├── repository/PurchaseOrderRepository.java
    │   └── service/PurchaseOrderService.java
    └── catalog/
        ├── domain/Product.java
        └── repository/ProductRepository.java
~~~

Class khởi động:

~~~java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Với cấu trúc trên, repository thuộc `com.example.shop.sales.repository` và `com.example.shop.catalog.repository` nằm dưới package gốc `com.example.shop`, nên thường được auto-configuration phát hiện mà không cần annotation enable riêng.

Ví dụ dependency Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Ví dụ cấu hình kết nối:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_user
    password: change-me-in-your-environment
~~~

Giá trị trên chỉ minh họa cấu trúc YAML, không phải thông tin truy cập có thể dùng trực tiếp. Trong dự án thật, mật khẩu nên lấy từ secret hoặc cấu hình môi trường.

### Khi package mặc định không bao phủ repository

Giả sử `@SpringBootApplication` nằm tại `com.example.shop.app`, còn repository ở `com.example.shop.sales.repository`:

~~~text
com.example.shop
├── app
│   └── ShopApplication.java
└── sales
    └── repository
        └── PurchaseOrderRepository.java
~~~

`sales.repository` không phải package con của `app`, vì vậy việc quét theo package mặc định có thể bỏ qua repository.

Có thể chuyển `ShopApplication` lên package cha chung `com.example.shop` nếu kiến trúc cho phép; hoặc cấu hình phạm vi repository JDBC tường minh.

## 3. Kích hoạt tường minh bằng @EnableJdbcRepositories

Import đúng annotation:

~~~java
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
~~~

Đây là `EnableJdbcRepositories` của **Spring Data JDBC**, khác với `EnableJpaRepositories` của JPA.

### 3.1. Chỉ định basePackages

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackages = "com.example.shop.sales.repository"
)
public class SalesJdbcRepositoryConfig {
}
~~~

Spring Data JDBC sẽ tìm repository trong `com.example.shop.sales.repository` và các package con, thay vì quét mọi package cùng thuộc `com.example.shop` theo khai báo này.

**Ưu điểm:** trực tiếp, dễ thấy package nào được đăng ký.

**Hạn chế:** tên package được đặt trong một chuỗi. Sau khi đổi tên package bằng IDE, chuỗi có thể không được cập nhật tự động.

Có thể chỉ định nhiều gốc quét:

~~~java
@EnableJdbcRepositories(basePackages = {
    "com.example.shop.sales.repository",
    "com.example.shop.reporting.repository"
})
~~~

Khi dùng nhiều package, mỗi gốc nên là phạm vi có chủ đích, tránh mở rộng quá mức chỉ để giải quyết một lỗi “không tìm thấy repository”.

### 3.2. Chỉ định basePackageClasses

Cách an toàn hơn khi refactor là tạo một **marker type** trong package repository cần quét:

~~~java
package com.example.shop.sales.repository;

/** Chỉ làm mốc xác định package của Sales repository. */
public interface SalesRepositoryPackage {
}
~~~

Sau đó cấu hình:

~~~java
package com.example.shop.config;

import com.example.shop.sales.repository.SalesRepositoryPackage;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackageClasses = SalesRepositoryPackage.class
)
public class SalesJdbcRepositoryConfig {
}
~~~

Spring lấy **package chứa `SalesRepositoryPackage`** làm package gốc. Marker không phải repository và không tự tạo bean; nó không kế thừa `CrudRepository`.

Cách này giảm rủi ro chuỗi package trở nên lỗi thời khi đổi tên thư mục hoặc di chuyển source. Nếu class/interface marker đổi tên, trình biên dịch cũng giúp phát hiện tham chiếu chưa được cập nhật.

Lưu ý: `basePackageClasses` **không có nghĩa chỉ quét class được truyền vào**. Nó quét các interface repository hợp lệ trong package chứa class đó và các package con.

Dùng nhiều marker khi cần nhiều vùng:

~~~java
@EnableJdbcRepositories(basePackageClasses = {
    SalesRepositoryPackage.class,
    ReportingRepositoryPackage.class
})
~~~

Mỗi marker nên nằm trong package repository tương ứng, không đặt tất cả ở package `com.example.shop` quá rộng.

## 4. Không khai báo basePackages thì quét ở đâu?

Nếu trực tiếp viết:

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories
public class JdbcRepositoryConfig {
}
~~~

Vùng quét mặc định của **khai báo này** là package chứa class mang annotation: `com.example.shop.config`.

~~~text
com.example.shop
├── config/
│   └── JdbcRepositoryConfig.java   <-- mặc định bắt đầu quét ở đây
├── sales/
│   └── repository/
│       └── PurchaseOrderRepository.java
└── catalog/
    └── repository/
        └── ProductRepository.java
~~~

Vì `sales.repository` không phải package con của `config`, khai báo `@EnableJdbcRepositories` ở trên có thể không tìm thấy repository nghiệp vụ.

Đây là điểm khác nhau cần nắm:

| Cách kích hoạt | Nơi lấy gốc quét |
|---|---|
| Spring Boot auto-configuration | Các auto-configuration packages của Boot, thường dựa vào package `@SpringBootApplication` |
| `@EnableJdbcRepositories` không có tham số vùng quét | Package của class khai báo annotation |
| `basePackages = "..."` | Package được viết rõ bằng chuỗi |
| `basePackageClasses = X.class` | Package chứa kiểu `X` |

Một số ứng dụng có nhiều cơ chế đăng ký cùng lúc. Vì vậy, bảng trên mô tả **phạm vi của từng cơ chế**, không nhất thiết là toàn bộ repository cuối cùng trong ApplicationContext.

## 5. Phân biệt component scanning và repository scanning

Một nguồn nhầm lẫn phổ biến là tưởng `@ComponentScan` và `@EnableJdbcRepositories` làm cùng một việc.

| Cơ chế | Chủ yếu tìm gì? | Cấu hình |
|---|---|---|
| **Component scanning** | Các Spring component như `@Service`, `@Component`, `@Controller` | `@ComponentScan`, `@SpringBootApplication(scanBasePackages = ...)` |
| **Repository scanning** | Interface Spring Data repository hợp lệ cần repository factory tạo proxy | `@EnableJdbcRepositories` hoặc auto-configuration |
| **Relational mapping** | Metadata ánh xạ aggregate Java với bảng/cột | `@Table`, `@Id`, `@MappedCollection` |

Ví dụ:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.shop.sales",
        "com.example.shop.catalog"
    }
)
public class ShopApplication {
}
~~~

Thuộc tính `scanBasePackages` chủ yếu điều khiển **component scan**. Nó không tự thay thế cấu hình repository base packages cho mọi Spring Data module.

Một interface `CrudRepository<PurchaseOrder, Long>` không cần `@Component` để trở thành repository bean. Spring Data xử lý interface này thông qua repository registration.

### Một aggregate và repository minh họa

~~~java
package com.example.shop.sales.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderCode;

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public void setOrderCode(String orderCode) {
        this.orderCode = orderCode;
    }
}
~~~

Repository:

~~~java
package com.example.shop.sales.repository;

import com.example.shop.sales.domain.PurchaseOrder;
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderCode(String orderCode);
}
~~~

`@Table` mô tả bảng tương ứng với aggregate. `@EnableJdbcRepositories` và auto-configuration chịu trách nhiệm tìm interface repository. Hai tầng này có nhiệm vụ khác nhau.

## 6. Thiết kế ranh giới package theo module

Khi mã nguồn lớn, nên đặt các repository vào package có tên biểu thị rõ chủ sở hữu:

~~~text
com.example.shop
├── config/
│   ├── SalesJdbcRepositoryConfig.java
│   └── CatalogJdbcRepositoryConfig.java
├── sales/
│   ├── domain/
│   │   └── PurchaseOrder.java
│   ├── repository/
│   │   ├── SalesRepositoryPackage.java
│   │   └── PurchaseOrderRepository.java
│   └── service/
│       └── OrderApplicationService.java
└── catalog/
    ├── domain/
    │   └── Product.java
    └── repository/
        ├── CatalogRepositoryPackage.java
        └── ProductRepository.java
~~~

Trong cấu hình giới hạn Sales:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackageClasses = SalesRepositoryPackage.class
)
public class SalesJdbcRepositoryConfig {
}
~~~

Chỉ các repository bên trong Sales package là ứng viên của **khai báo này**.

Khi cần đăng ký thêm Catalog, có thể:

- Thêm `CatalogRepositoryPackage.class` vào cùng `basePackageClasses` nếu các repository dùng chung hạ tầng JDBC.
- Tạo một cấu hình Catalog khác với package gốc không chồng lấn nếu kiến trúc cần tổ chức riêng.

Ví dụ hai cấu hình không giao nhau:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackageClasses = SalesRepositoryPackage.class
)
class SalesRepositoriesConfiguration {
}

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackageClasses = CatalogRepositoryPackage.class
)
class CatalogRepositoriesConfiguration {
}
~~~

Không nhất thiết có một class config cho mỗi repository. Nếu hệ thống chỉ có một database và cùng một kiểu cấu hình, một phạm vi gốc rõ ràng có thể đã đủ.

### Tránh chồng lấn vùng quét

Giả sử một cấu hình quét `com.example.shop`, cấu hình khác quét `com.example.shop.sales.repository`. Cả hai có thể cùng xem xét `PurchaseOrderRepository`. Nếu hai cơ chế cùng đăng ký một bean, ứng dụng có thể gặp lỗi bean trùng tên, bean definition override hoặc xung đột repository factory.

Giải pháp đúng là kiểm soát **tất cả các registrar đang chạy** và xác định chính xác bên nào sở hữu từng repository. Không nên mặc định bật cho phép override bean để che lỗi thiết kế phạm vi.

### includeFilters và excludeFilters

`@EnableJdbcRepositories` hỗ trợ các thuộc tính `includeFilters` và `excludeFilters` dùng bộ lọc type của Spring khi cần lọc ứng viên sâu hơn.

Ví dụ bỏ qua các interface ở package legacy:

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FilterType;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackages = "com.example.shop.sales.repository",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.REGEX,
        pattern = "com\\.example\\.shop\\.sales\\.repository\\.legacy\\..*"
    )
)
public class SalesJdbcRepositoryConfig {
}
~~~

Ở đây `\\.` trong Java string tạo thành dấu chấm literal trong regular expression, còn `.*` khớp các tên type trong package legacy và cấp con. Khi có thể, ưu tiên **tổ chức package đúng ngay từ đầu** thay vì dựa trên regex filter dài và dễ sai.

## 7. Những repository nào đủ điều kiện được đăng ký?

Spring Data nhận diện một interface repository khi nó kế thừa phù hợp từ các interface nền, ví dụ:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Không cần viết một class `PurchaseOrderRepositoryImpl` để triển khai các thao tác CRUD mặc định; cũng không nhất thiết thêm `@Repository` trên interface.

### Interface cơ sở generic và @NoRepositoryBean

Nếu dự án tạo một repository interface generic để các repository cụ thể kế thừa, nên đánh dấu nó không phải repository độc lập:

~~~java
package com.example.shop.shared.repository;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseCrudRepository<T, ID>
        extends CrudRepository<T, ID> {
}
~~~

Repository thực tế:

~~~java
package com.example.shop.sales.repository;

import com.example.shop.sales.domain.PurchaseOrder;
import com.example.shop.shared.repository.BaseCrudRepository;

public interface PurchaseOrderRepository
        extends BaseCrudRepository<PurchaseOrder, Long> {
}
~~~

`@NoRepositoryBean` giúp Spring Data không cố tạo repository bean cho interface generic chưa xác định domain type. Interface cụ thể có `PurchaseOrder` và `Long` vẫn được đăng ký khi nằm trong phạm vi quét.

### Lưu ý khi dùng đồng thời JDBC và JPA/MongoDB

Khi một ứng dụng có nhiều Spring Data module trên classpath, Spring Data có thể sử dụng cơ chế **strict repository configuration** để phân biệt repository thuộc store nào.

Trong bối cảnh Spring Data JDBC:

1. Đặt JDBC repository vào package được giới hạn phù hợp.
2. Sử dụng các mapping annotation của Spring Data Relational như `@Table` cho aggregate JDBC.
3. Phân biệt `@EnableJdbcRepositories` với `@EnableJpaRepositories` hoặc annotation enable của store khác.
4. Tránh để cùng một interface repository bị quét bởi nhiều store khi không có chủ đích rõ ràng.

Một interface chỉ kế thừa `CrudRepository` đôi khi không đủ thông tin để chọn đúng store trong một ứng dụng chứa nhiều Spring Data module. Domain mapping và cấu hình repository cần nhất quán.

## 8. Khi nào cần cấu hình rõ hơn hạ tầng JDBC?

`@EnableJdbcRepositories` **không tự tạo DataSource**. Với một database, Spring Boot thường chuẩn bị datasource và các bean JDBC liên quan khi dependency cùng thuộc tính kết nối đầy đủ.

Ví dụ service:

~~~java
package com.example.shop.sales.service;

import com.example.shop.sales.repository.PurchaseOrderRepository;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository repository;

    public OrderApplicationService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public boolean exists(Long orderId) {
        return repository.existsById(orderId);
    }
}
~~~

Service inject thành công nghĩa là repository bean đã được đăng ký. Khi gọi `existsById(...)`, việc SQL hoạt động hay không còn cần kết nối, schema và mapping hợp lệ.

### 8.1. Nhiều datasource không chỉ là nhiều basePackages

Xét hai nhóm repository:

~~~text
sales.repository       -> Sales database
analytics.repository   -> Analytics database
~~~

Cấu hình gốc quét riêng mới xác định repository nào thuộc từng nhóm. Để thực sự sử dụng hai database, ứng dụng còn phải thiết lập các bean JDBC operations, transaction manager và phần hạ tầng mapping/data access tương ứng.

Tùy phiên bản Spring Data JDBC, `@EnableJdbcRepositories` cung cấp các tham chiếu cấu hình như `jdbcOperationsRef` và `transactionManagerRef`. Chúng có vai trò liên kết repository tới các bean cụ thể, nhưng bản thân việc chỉ định hai tham số đó không bảo đảm mọi phần của thiết kế multi-datasource đã đúng. Cần đánh giá dialect, converter, data access strategy, transaction boundary và cấu hình bean trong phiên bản được sử dụng.

Ví dụ trên chỉ giải thích **ranh giới trách nhiệm**: chọn package là cấu hình đăng ký repository; chọn database là cấu hình hạ tầng sâu hơn.

## 9. Một số lỗi và cách xác định đúng tầng gây lỗi

### 9.1. “No qualifying bean of type PurchaseOrderRepository”

Ví dụ:

~~~text
No qualifying bean of type
'com.example.shop.sales.repository.PurchaseOrderRepository'
available
~~~

Nguyên nhân thường thuộc phần đăng ký bean:

- Repository nằm ngoài các base packages đang được quét.
- `@EnableJdbcRepositories` không có tham số, nhưng class cấu hình lại nằm ở package khác.
- Class chứa `@Configuration` không được Spring nạp.
- Repository bị lọc bởi `excludeFilters`.
- Repository không được xem là ứng viên hợp lệ.
- Auto-configuration tương ứng không kích hoạt theo điều kiện của ứng dụng.

Trong trường hợp class cấu hình nằm ngoài component scan, có thể import nó qua một class cấu hình đang được Spring nạp:

~~~java
package com.example.shop;

import com.example.shop.config.SalesJdbcRepositoryConfig;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(SalesJdbcRepositoryConfig.class)
public class ShopApplication {
}
~~~

`@Import` là một cách nạp config tường minh, không phải bước bắt buộc nếu config đã được component scanning tìm thấy.

### 9.2. “Relation/table does not exist” khi truy vấn

Ví dụ:

~~~text
BadSqlGrammarException:
relation "purchase_order" does not exist
~~~

Nếu repository đã được inject và câu SQL được gọi, scanning thường không còn là nguyên nhân chính. Cần kiểm tra schema, tên bảng trong `@Table`, migration, quyền database, datasource và dialect.

### 9.3. Bean repository đăng ký hai lần

Nếu có nhiều `@EnableJdbcRepositories` hoặc auto-configuration kết hợp với cấu hình explicit, hãy kiểm tra các vùng quét có giao nhau không. Tách package, thu hẹp gốc quét và bảo đảm mỗi repository được quản lý theo một cơ chế phù hợp.

### 9.4. Thay đổi package nhưng quên sửa string

~~~java
@EnableJdbcRepositories(
    basePackages = "com.example.shop.sales.repository"
)
~~~

Nếu các class đã chuyển sang `com.example.shop.orders.repository`, chuỗi trên trở nên lỗi thời. Marker class làm liên kết package rõ hơn trong refactoring.

### 9.5. Marker đặt quá cao

Nếu đặt marker ở `com.example.shop` rồi dùng `basePackageClasses`, Spring có thể quét nhiều module Sales, Catalog, Billing... không mong muốn. Marker thường nên nằm ở package repository riêng, ví dụ `com.example.shop.sales.repository`.

## 10. Quan sát tập repository thực tế trong ApplicationContext

Có thể dùng một integration test để xác nhận repository mong đợi đã được đăng ký:

~~~java
package com.example.shop;

import com.example.shop.sales.repository.PurchaseOrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class RepositoryRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void purchaseOrderRepositoryIsRegistered() {
        assertThat(context.getBeansOfType(
                PurchaseOrderRepository.class
        )).hasSize(1);
    }
}
~~~

Đây là integration test minh họa, cần ứng dụng có test datasource và các bean liên quan hợp lệ. Kết quả xác nhận số bean trong **toàn bộ ApplicationContext**; nó không chỉ kiểm tra riêng một annotation enable.

Nếu muốn giới hạn Sales mà loại Catalog, có thể kiểm tra `CatalogRepository` không xuất hiện trong context, nhưng chỉ sau khi bảo đảm không có registrar khác cố ý đăng ký Catalog.

Log khởi động của Spring Data thường cho biết quá trình bootstrap repositories và số interface được tìm thấy. Nếu cần xem kỹ, có thể bật log thích hợp cho `org.springframework.data.repository.config` để tìm hiểu repository scan của phiên bản đang dùng.

## 11. Thực hành từng bước: chỉ định vùng quét của module Sales

Bắt đầu từ cấu trúc:

~~~text
com.example.shop
├── ShopApplication.java
├── config/
│   └── SalesJdbcRepositoryConfig.java
└── sales/
    ├── domain/
    │   └── PurchaseOrder.java
    └── repository/
        ├── SalesRepositoryPackage.java
        └── PurchaseOrderRepository.java
~~~

**Bước 1 — Tạo marker:**

~~~java
package com.example.shop.sales.repository;

public interface SalesRepositoryPackage {
}
~~~

**Bước 2 — Đăng ký JDBC repository theo marker:**

~~~java
package com.example.shop.config;

import com.example.shop.sales.repository.SalesRepositoryPackage;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration(proxyBeanMethods = false)
@EnableJdbcRepositories(
    basePackageClasses = SalesRepositoryPackage.class
)
public class SalesJdbcRepositoryConfig {
}
~~~

**Bước 3 — Nạp config:** nếu package `config` nằm trong component scan của Boot, class `@Configuration` được nhận diện. Nếu không, dùng `@Import(SalesJdbcRepositoryConfig.class)` trên một class cấu hình đã được nạp.

**Bước 4 — Xem context:** xác nhận `PurchaseOrderRepository` xuất hiện đúng một bean. Nếu mục tiêu là giới hạn Sales, cần tính cả những cấu hình quét repository khác đang hoạt động, bao gồm auto-configuration của Boot nếu có.

**Bước 5 — Kiểm tra khả năng truy vấn:** khi repository được inject thành công, gọi thao tác đọc phù hợp và phân biệt lỗi kết nối/schema với lỗi tìm bean.

Đây là ví dụ tối thiểu để thiết kế ranh giới scan. Không cần viết repository implementation thủ công hoặc đặt `@Repository` trên marker.

## 12. Những câu hỏi giúp hiểu bản chất

**Nếu class `@EnableJdbcRepositories` nằm ở `com.example.shop.config` mà không có basePackages, nó có tự quét `sales.repository` không?**

Không theo cấu hình đó. Mặc định annotation quét package của chính class mang annotation. Repository nằm ở nơi khác phải được đưa vào phạm vi quét tường minh hoặc được một registrar khác đăng ký.

**`basePackageClasses = PurchaseOrderRepository.class` có phải chỉ quét đúng repository đó không?**

Không. Nó dùng package chứa `PurchaseOrderRepository` làm gốc quét, nên các repository hợp lệ khác trong cùng package và package con cũng có thể được đăng ký.

**Có cần `@EnableJdbcRepositories` cho mọi ứng dụng Boot sử dụng JDBC không?**

Không. Spring Boot thường tự cấu hình repository nếu có starter và điều kiện phù hợp. Chỉ thêm annotation tường minh khi có lý do kiểm soát vùng quét hoặc hạ tầng.

**Có thể sửa lỗi repository bằng `@SpringBootApplication(scanBasePackages = "...")` không?**

Đó là cấu hình component scanning. Repository scanning có quy tắc riêng; đừng coi nó là biện pháp chung thay thế `@EnableJdbcRepositories`.

**Repo đã inject được nhưng `findById(...)` lỗi SQL, có nghĩa scan sai không?**

Không nhất thiết. Bean đã được tạo; lúc này nên kiểm tra database, schema, mapping và cách truy vấn.

**Nếu khai báo hai datasource cùng hai `basePackages` thì đã chắc chắn map đúng từng database chưa?**

Chưa. Package scan chỉ xác định repository được đăng ký; cấu hình JDBC infrastructure và transaction phải được thiết kế tương ứng.

## 13. Ghi nhớ mô hình hoạt động

~~~text
@SpringBootApplication + Spring Boot auto-configuration
    └── Thường kích hoạt JDBC repository trong package mặc định

@EnableJdbcRepositories
    ├── basePackages       -> chỉ định package bằng String
    ├── basePackageClasses -> lấy package từ marker type
    ├── include/exclude    -> tinh chỉnh repository candidates
    └── không có tham số   -> package của class khai báo annotation

Repository scanning
    -> tìm interface -> tạo repository factory/proxy

Component scanning
    -> tìm @Service / @Component / @Controller ...

Relational mapping
    -> dùng @Table / @Id / @MappedCollection ...

DataSource + JDBC infrastructure
    -> thực thi kết nối, mapping và SQL thực tế
~~~

Khi dùng Spring Data JDBC, hãy xem `@EnableJdbcRepositories` như công cụ **tuyên bố ranh giới đăng ký repository**. Chọn package gốc đủ hẹp, ưu tiên marker khi cần refactor an toàn, tránh scan chồng lấn và kiểm tra tổng thể những cấu hình đang có hiệu lực. Nhờ vậy, ứng dụng dễ giải thích repository nào thuộc module nào và vì sao một repository bean được tạo ra.
