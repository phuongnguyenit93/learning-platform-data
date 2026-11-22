# Kích hoạt @EnableMongoRepositories và giới hạn package quét

> **Chương:** Cấu hình và kiến trúc  
> **Module:** `SPRING_DATA_MONGODB`

Khi sử dụng Spring Data MongoDB, ứng dụng thường khai báo các interface như `MongoRepository<Order, String>`. Spring Data sẽ tạo bean triển khai các interface này tại thời điểm khởi động, nhờ đó service có thể inject repository để truy vấn, ghi và cập nhật document. **`@EnableMongoRepositories` xác định những package nào được quét để tìm và đăng ký các MongoDB repository.** Chọn phạm vi quét chính xác giúp ứng dụng đăng ký đúng repository, tránh bỏ sót bean hoặc đăng ký nhầm repository của module khác.

Bài học tập trung vào cách dùng annotation trong cấu hình Java, cơ chế mặc định của Spring Boot, ranh giới giữa quét repository và các cơ chế quét khác, cùng cách gắn repository vào `MongoTemplate` phù hợp. Đây là nền tảng cho module `SPRING_DATA_MONGODB`, nơi ứng dụng kết nối MongoDB, ánh xạ document, thao tác qua `MongoTemplate` hoặc repository, rồi tiến đến truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chức năng của `@EnableMongoRepositories` và phân biệt nó với `@ComponentScan`, `@Document` và cấu hình kết nối MongoDB.
2. Biết khi nào Spring Boot tự cấu hình repository và khi nào cần khai báo annotation tường minh.
3. Giới hạn quét bằng `basePackages` hoặc `basePackageClasses` và hiểu tác động của vị trí đặt class cấu hình.
4. Tránh đăng ký trùng, quét nhầm interface, hoặc kết nối repository với sai `MongoTemplate` khi có nhiều database.
5. Kiểm tra bean repository đã được đăng ký đúng và xử lý các lỗi thường gặp trong ứng dụng thực tế.

## 2. Ba việc khác nhau trong một ứng dụng MongoDB

Hãy phân biệt rõ các trách nhiệm sau:

| Cơ chế | Tìm hoặc cấu hình cái gì? | Ví dụ | Có được `@EnableMongoRepositories` thay thế không? |
| --- | --- | --- | --- |
| **Component scan** | Các lớp cấu hình và component Spring như `@Service`, `@Configuration` | `OrderService`, `MongoRepositoryConfig` | Không |
| **Repository scan** | Interface repository để Spring Data tạo proxy/implementation bean | `OrderRepository extends MongoRepository<...>` | Có, đây là nhiệm vụ chính |
| **Document mapping** | Kiểu Java và metadata ánh xạ sang BSON/collection | `@Document(collection = "orders")`, `@Id`, `@Field` | Không |
| **MongoDB connection/template** | Client, database, converter và công cụ truy cập dữ liệu | `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate` | Không |

Luồng tạo repository thường có thể hình dung như sau:

```text
Ứng dụng Spring khởi động
   │
   ├── Khởi tạo MongoClient, MongoTemplate / mapping infrastructure
   │
   ├── Nạp @Configuration có @EnableMongoRepositories
   │      └── Quét interface repository trong các package đã chọn
   │             └── Đăng ký bean proxy cho OrderRepository, ...
   │
   └── Tạo OrderService
          └── Inject bean OrderRepository
                 └── Truy vấn document qua MongoTemplate/driver
```

Một repository là interface nhưng thường vẫn inject được vì Spring Data tạo bean triển khai động. Không nhất thiết tự viết lớp `OrderRepositoryImpl` cho các thao tác CRUD hoặc derived query thông thường.

**Điểm quan trọng:** `@EnableMongoRepositories` không mở kết nối, không tạo collection, không tự chọn database theo package và không quét mọi class có `@Document`. Repository được đăng ký theo package, còn việc lưu vào database nào phụ thuộc vào `MongoTemplate` mà repository sử dụng.

## 3. Có cần khai báo @EnableMongoRepositories trong Spring Boot?

### 3.1. Trường hợp dùng Spring Boot thông thường

Với Spring Boot đã cài dependency Spring Data MongoDB và có cấu hình kết nối hợp lệ, Boot thường tự kích hoạt repository infrastructure. Nếu không có cấu hình repository tùy chỉnh, Boot lấy phạm vi package mặc định từ package đăng ký tự cấu hình của ứng dụng, thường được thiết lập bởi `@SpringBootApplication`.

Ví dụ:

```text
com.example.shop
├── ShopApplication.java                 (@SpringBootApplication)
├── orders
│   ├── model/Order.java                 (@Document)
│   ├── repository/OrderRepository.java  (MongoRepository)
│   └── service/OrderService.java        (@Service)
└── catalog
    └── repository/ProductRepository.java
```

Nếu `ShopApplication` nằm ở `com.example.shop` và cơ chế auto-configuration repository của Boot đang hoạt động, cả hai repository trong các package con thường được phát hiện. Trong bố cục này, có thể **không cần** viết `@EnableMongoRepositories`.

Ví dụ cấu hình kết nối **cho môi trường phát triển local**:

```yaml
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/shop
```

Đây là URI ví dụ; môi trường triển khai thật cần cấu hình bảo mật, quyền truy cập và secret theo hạ tầng. Có URI không đồng nghĩa mọi repository đã được quét đúng; đây là hai cấu hình độc lập.

### 3.2. Khi nên dùng annotation tường minh

Cân nhắc `@EnableMongoRepositories` khi:

- Chỉ muốn đăng ký repository của một phạm vi module, ví dụ riêng `orders.repository`.
- Repository nằm ngoài package quét mặc định của ứng dụng.
- Có nhiều `MongoTemplate` hoặc nhiều MongoDB database cần liên kết từng nhóm repository đến đúng template.
- Xây dựng ứng dụng Spring không dựa vào cơ chế tự cấu hình repository của Boot.
- Cần tùy chỉnh repository scan bằng các thuộc tính dành riêng cho Spring Data.

Nếu đã chọn cách khai báo tường minh, hãy rà soát các cấu hình `@EnableMongoRepositories` khác và auto-configuration liên quan để không đăng ký chồng lấn cùng interface. Việc cấu hình thủ công và tự động có tương tác phụ thuộc phiên bản Spring Boot, bean hiện diện và điều kiện auto-configuration; nên kiểm tra **ApplicationContext thực tế** thay vì đoán từ sơ đồ package.

## 4. Ví dụ hoàn chỉnh: chỉ đăng ký repository của đơn hàng

Giả sử dự án có cấu trúc:

```text
src/main/java/com/example/shop/
├── ShopApplication.java
├── config/
│   └── OrdersRepositoryConfig.java
├── orders/
│   ├── model/Order.java
│   ├── repository/
│   │   ├── OrdersRepositoryPackage.java
│   │   └── OrderRepository.java
│   └── service/OrderService.java
└── catalog/
    └── repository/ProductRepository.java
```

Mục tiêu là cho cấu hình `OrdersRepositoryConfig` chỉ quét `com.example.shop.orders.repository`. Các class bên ngoài package này không nằm trong phạm vi **lệnh quét của cấu hình đó**.

### 4.1. Document

File `orders/model/Order.java`:

```java
package com.example.shop.orders.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
    @Id String id,
    String customerId,
    long totalMinor,
    String status
) {}
```

`@Document` cho biết domain object ánh xạ với collection `orders`. Tên trường `id` được ánh xạ sang `_id` trong document BSON.

### 4.2. Repository interface

File `orders/repository/OrderRepository.java`:

```java
package com.example.shop.orders.repository;

import com.example.shop.orders.model.Order;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
    List<Order> findByCustomerId(String customerId);
}
```

Khi interface được phát hiện, Spring Data tạo repository bean và chuyển phương thức `findByCustomerId` thành truy vấn theo property `customerId` của domain object. Việc tổ chức repository trong package không làm đổi tên collection hoặc tên field.

### 4.3. Marker để chọn package an toàn khi refactor

File `orders/repository/OrdersRepositoryPackage.java`:

```java
package com.example.shop.orders.repository;

/** Marker dùng để chọn package chứa repository. */
public interface OrdersRepositoryPackage {}
```

Marker này không phải repository và không phải bean. Mục đích của nó là cung cấp **địa chỉ package thông qua kiểu Java**, tránh viết trực tiếp tên package dưới dạng chuỗi.

### 4.4. Kích hoạt và giới hạn quét

File `config/OrdersRepositoryConfig.java`:

```java
package com.example.shop.config;

import com.example.shop.orders.repository.OrdersRepositoryPackage;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
    basePackageClasses = OrdersRepositoryPackage.class
)
public class OrdersRepositoryConfig {}
```

Vì marker nằm trong `com.example.shop.orders.repository`, annotation sẽ quét package đó **và các package con phù hợp**, thay vì lấy package của `OrdersRepositoryConfig`. Nếu đặt marker ở `com.example.shop`, phạm vi có thể rộng hơn dự kiến.

File `ShopApplication.java`:

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Do `OrdersRepositoryConfig` nằm trong package con của `com.example.shop`, component scan mặc định của `@SpringBootApplication` có thể nạp cấu hình này. Nếu chuyển class cấu hình ra ngoài phạm vi component scan, cần import nó hoặc thay đổi cấu hình quét component để Spring thực sự xử lý annotation.

### 4.5. Service sử dụng bean đã đăng ký

File `orders/service/OrderService.java`:

```java
package com.example.shop.orders.service;

import com.example.shop.orders.model.Order;
import com.example.shop.orders.repository.OrderRepository;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public List<Order> ordersOf(String customerId) {
        return orders.findByCustomerId(customerId);
    }
}
```

Nếu ứng dụng khởi động thành công và bean `OrderRepository` tồn tại, Spring có thể inject nó vào service qua constructor. Cần có kết nối MongoDB thích hợp để **thực thi truy vấn**; việc tạo bean thành công chưa chứng minh database đang hoạt động hoặc query đúng dữ liệu.

## 5. basePackages và basePackageClasses khác nhau thế nào?

`@EnableMongoRepositories` có hai cách chỉ định package được quét phổ biến:

### 5.1. basePackages: khai báo bằng chuỗi

```java
package com.example.shop.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
    basePackages = "com.example.shop.orders.repository"
)
public class OrdersRepositoryConfig {}
```

Cấu hình này ngắn và dễ nhìn, nhưng khi đổi tên package bằng công cụ refactor, chuỗi có thể không được cập nhật theo. Nếu gõ sai đường dẫn, ứng dụng có thể không tìm thấy repository nào trong phạm vi đó.

### 5.2. basePackageClasses: khai báo bằng class

```java
@EnableMongoRepositories(
    basePackageClasses = OrdersRepositoryPackage.class
)
```

Spring lấy **package chứa class/interface được chỉ định**, không chỉ đăng ký chính class/interface đó. Marker giúp thể hiện chủ đích rõ ràng; cũng có thể truyền `OrderRepository.class` nếu muốn quét toàn bộ package chứa repository ấy.

| Tiêu chí | `basePackages` | `basePackageClasses` |
| --- | --- | --- |
| Cách chọn phạm vi | Tên package dạng chuỗi | Package của kiểu Java |
| Hỗ trợ refactor | Dễ sai nếu chuỗi không đổi theo | Công cụ Java thường cập nhật import/type |
| Có thể dùng nhiều phạm vi | Có, truyền nhiều tên package | Có, truyền nhiều class/marker |
| Độ chính xác | Đúng package và các package con | Cũng là package và các package con |
| Lựa chọn gợi ý | Khi cần phạm vi từ chuỗi cấu hình rõ ràng | Khi codebase có thể sử dụng marker riêng cho module |

Hai thuộc tính đều nhận **nhiều** giá trị:

```java
// Ví dụ độc lập: dùng khi chủ đích cần quét cả hai package.
@EnableMongoRepositories(
    basePackages = {
        "com.example.shop.orders.repository",
        "com.example.shop.billing.repository"
    }
)
```

Hoặc:

```java
@EnableMongoRepositories(
    basePackageClasses = {
        OrdersRepositoryPackage.class,
        BillingRepositoryPackage.class
    }
)
```

Trong ví dụ thứ hai, `BillingRepositoryPackage` là marker đặt trong package repository của billing. Các đoạn annotation ngắn này minh họa các **lựa chọn thay thế**; không nên áp dụng nhiều cấu hình quét trùng nhau chỉ để sử dụng cả hai cú pháp.

### 5.3. Nếu không chỉ định basePackages?

`@EnableMongoRepositories` mặc định lấy package của **class cấu hình mang annotation** làm package gốc để quét.

Giả sử:

```text
com.example.shop
├── config/OrdersRepositoryConfig.java  <-- @EnableMongoRepositories không có basePackages
└── orders/repository/OrderRepository.java
```

Khi đó cấu hình thường chỉ tìm trong `com.example.shop.config` và các package con, **không** tự tìm sibling package `com.example.shop.orders.repository`. Đây là nguyên nhân phổ biến của lỗi service không inject được repository khi chuyển annotation từ class ứng dụng gốc vào một class `config`.

**Quy tắc:** nếu tạo class cấu hình trong package riêng như `config`, nên chỉ định `basePackageClasses` hoặc `basePackages` tường minh.

## 6. Repository scan không phải component scan

Spring cần **nạp class cấu hình** trước, sau đó annotation trên class ấy mới có hiệu lực. Hai phạm vi quét có thể khác nhau:

```text
@SpringBootApplication / @ComponentScan
    └── tìm @Configuration OrdersRepositoryConfig
           └── @EnableMongoRepositories
                 └── tìm MongoRepository interface trong orders.repository
```

Ví dụ `OrdersRepositoryConfig` đặt ở `com.example.infrastructure.mongo` bên ngoài package ứng dụng `com.example.shop`: dù annotation có `basePackageClasses` đúng, nếu Spring không nạp cấu hình thì **không xảy ra lần quét repository đó**.

Có thể import cấu hình từ class ứng dụng:

```java
package com.example.shop;

import com.example.infrastructure.mongo.OrdersRepositoryConfig;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(OrdersRepositoryConfig.class)
public class ShopApplication {}
```

Đây là ví dụ lựa chọn; class `OrdersRepositoryConfig` phải thực sự có trong dependency/module liên quan. Không cần dùng `@Import` nếu class đã nằm trong phạm vi component scan và được Spring nạp đúng.

**Quét repository cũng không quét document entity theo kiểu JPA.** Spring Data MongoDB nhận metadata ánh xạ của domain class khi làm việc với nó và thông qua mapping infrastructure. Đặt `Order` trong package khác `OrderRepository` không khiến repository bị bỏ qua, miễn class domain có trong classpath và mapping hợp lệ.

## 7. Giới hạn quét để tránh đăng ký nhầm

Một cấu trúc dự án lớn có thể gồm:

```text
com.example.platform
├── sales
│   └── repository/OrderRepository.java
├── audit
│   └── repository/AuditRepository.java
├── experiments
│   └── repository/DraftRepository.java
└── bootstrap
    └── MongoConfig.java
```

Nếu đặt `basePackages = "com.example.platform"`, mọi MongoDB repository interface phù hợp trong các package con có thể được quét. Khi các repository cùng trỏ đến một template, điều này dễ khiến module không dự kiến được đăng ký vào cùng ApplicationContext.

Cách kiểm soát:

1. **Đặt repository theo ranh giới module:** ví dụ `sales.repository`, `audit.repository`.
2. **Chỉ định marker ở package hẹp nhất cần dùng:** ví dụ `SalesRepositoryPackage.class`.
3. **Tách cấu hình theo nhóm repository và template** khi nhiều nguồn MongoDB.
4. **Tránh các cấu hình @EnableMongoRepositories có vùng quét chồng lấn** nếu đều đăng ký cùng repository.
5. Nếu có base repository interface dùng chung mà **không muốn tạo bean trực tiếp**, đánh dấu `@NoRepositoryBean`.

Ví dụ base interface:

```java
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseMongoRepository<T, ID>
        extends MongoRepository<T, ID> {
}
```

`@NoRepositoryBean` hướng Spring Data không tạo repository bean cho interface cơ sở chưa có domain cụ thể. Các interface con với domain cụ thể vẫn có thể được đăng ký. Điều này hữu ích khi tạo phương thức dùng chung cho nhiều repository nhưng không muốn interface generic bị coi như một repository độc lập.

Annotation `@EnableMongoRepositories` cũng có các bộ lọc `includeFilters`/`excludeFilters`. Chúng có thể hữu ích trong tình huống đặc thù, nhưng package tách rõ ràng thường dễ bảo trì và ít gây bất ngờ hơn filter dựa vào tên hoặc annotation.

## 8. Nhiều MongoTemplate: chọn đúng database cho mỗi nhóm repository

Trong hệ thống đa module, repository dành cho nghiệp vụ vận hành có thể dùng database `shop`, còn dữ liệu tổng hợp dùng `analytics`. **Chỉ giới hạn package quét chưa quyết định database đích.** Cần gắn từng nhóm repository với bean `MongoTemplate` tương ứng bằng `mongoTemplateRef`.

Ví dụ ý tưởng:

```text
orders.repository  -- @EnableMongoRepositories -->
                       mongoTemplateRef="ordersMongoTemplate"
                       MongoTemplate(database="shop")

analytics.repository -- @EnableMongoRepositories -->
                       mongoTemplateRef="analyticsMongoTemplate"
                       MongoTemplate(database="analytics")
```

### 8.1. Cấu hình repository cho orders

Ví dụ dưới đây sử dụng `MongoClient` đã được ứng dụng cung cấp (chẳng hạn từ auto-configuration của Spring Boot):

```java
package com.example.shop.config;

import com.example.shop.orders.repository.OrdersRepositoryPackage;
import com.mongodb.client.MongoClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
    basePackageClasses = OrdersRepositoryPackage.class,
    mongoTemplateRef = "ordersMongoTemplate"
)
public class OrdersMongoConfig {

    @Bean("ordersMongoTemplate")
    public MongoTemplate ordersMongoTemplate(MongoClient client) {
        return new MongoTemplate(client, "shop");
    }
}
```

- `basePackageClasses` xác định **nhóm interface repository**.
- `mongoTemplateRef` xác định **tên bean MongoTemplate** mà nhóm đó sử dụng.
- `new MongoTemplate(client, "shop")` chọn database `shop` trên client đã cung cấp.

Đây là cấu hình **thay thế** `OrdersRepositoryConfig` trong phần 4. Nếu sử dụng `OrdersMongoConfig`, hãy bỏ cấu hình quét chồng lấn cũ trong ứng dụng thực, tránh đăng ký hai lần cùng repository. Khi có nhiều template, các injection `MongoTemplate` trực tiếp vào service cần chỉ rõ bean phù hợp (ví dụ bằng `@Qualifier`).

### 8.2. Cấu hình nhóm analytics

Một class cấu hình khác có thể dùng:

```java
@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
    basePackageClasses = AnalyticsRepositoryPackage.class,
    mongoTemplateRef = "analyticsMongoTemplate"
)
public class AnalyticsMongoConfig {
    @Bean("analyticsMongoTemplate")
    MongoTemplate analyticsMongoTemplate(MongoClient client) {
        return new MongoTemplate(client, "analytics");
    }
}
```

Đoạn này giả định `AnalyticsRepositoryPackage` tồn tại trong package chứa các repository phân tích và ứng dụng dùng chung `MongoClient` cho hai database trên một triển khai. Nếu các database dùng hai cụm hoặc thông tin xác thực khác nhau, cần khai báo **hai client/factory tương ứng** thay vì dùng chung client.

`mongoTemplateRef` phải khớp **tên bean thực tế**. Nếu ghi nhầm, Spring có thể thất bại khi tạo repository do không tìm thấy template. Khi hai nhóm repository quét chồng lên nhau, việc chọn template khác nhau không tự làm cho trùng bean trở nên hợp lệ.

### 8.3. Sự khác nhau giữa phân nhóm package và phân quyền

Chia repository theo package là cách tổ chức bean của **ứng dụng**. Nó không thay thế xác thực và phân quyền MongoDB. Nếu nhiều repository dùng cùng client có quyền truy cập nhiều database, package quét không tự giới hạn quyền trên máy chủ. Việc cấu hình principal, role, TLS và credentials cần thực hiện độc lập.

## 9. Imperative và reactive phải cấu hình đúng loại repository

Module Spring Data MongoDB có hai phong cách truy cập:

| | Imperative (đồng bộ/blocking) | Reactive |
| --- | --- | --- |
| Repository điển hình | `MongoRepository<T, ID>` | `ReactiveMongoRepository<T, ID>` |
| Annotation quét tường minh | `@EnableMongoRepositories` | `@EnableReactiveMongoRepositories` |
| Template | `MongoTemplate` | `ReactiveMongoTemplate` |
| Kết quả phương thức | `Optional`, `List`, `Page`, ... | `Mono`, `Flux`, ... |

Ví dụ interface reactive:

```java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<Order, String> {

    Flux<Order> findByCustomerId(String customerId);
}
```

Nếu cần kích hoạt reactive repository tường minh, dùng annotation tương ứng:

```java
@Configuration(proxyBeanMethods = false)
@EnableReactiveMongoRepositories(
    basePackageClasses = ReactiveOrderRepository.class,
    reactiveMongoTemplateRef = "reactiveMongoTemplate"
)
public class ReactiveOrderRepositoryConfig {}
```

Ví dụ giả định ứng dụng đã có bean `reactiveMongoTemplate` đúng kiểu `ReactiveMongoTemplate` và đã import `@EnableReactiveMongoRepositories`/`@Configuration`. Trong dự án có cả hai phong cách, nên tách package repository đồng bộ và reactive, tránh để một cấu hình quét quá rộng hoặc khiến Spring Data suy luận sai loại repository.

Reactive repository cần reactive MongoDB driver và cấu hình kết nối tương ứng; chỉ chuyển `@EnableMongoRepositories` thành một annotation khác không biến các service blocking thành non-blocking. Tương tự, tính nguyên tử, transaction và lựa chọn index vẫn tuân theo khả năng của MongoDB và cách nghiệp vụ thực hiện thao tác.

## 10. Kiểm tra cấu hình khi ứng dụng khởi động

### 10.1. Kiểm tra bean repository trong ApplicationContext

Ví dụ kiểm thử tích hợp dùng JUnit 5 và Spring Boot Test:

```java
package com.example.shop;

import com.example.shop.orders.repository.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class MongoRepositoryRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void orderRepositoryIsRegistered() {
        assertThat(context.getBeansOfType(OrderRepository.class))
            .hasSize(1);
    }
}
```

Kiểm thử này chứng minh một `OrderRepository` bean đã được đăng ký. Nếu mục tiêu là **không có repository ngoài phạm vi**, có thể bổ sung assertion với kiểu repository đó, nhưng cần bảo đảm không có cấu hình khác đang cố ý đăng ký nó.

Test context có thể vẫn khởi tạo MongoDB infrastructure; để kiểm thử cả thao tác truy vấn, nên sử dụng MongoDB test instance cô lập (ví dụ Testcontainers) và dữ liệu thử có chủ đích. Cần tách hai kết luận:

- **Bean tồn tại:** repository scan và wiring cơ bản đúng.
- **Truy vấn hoạt động:** kết nối, mapping, tên collection, quyền và dữ liệu thực tế đúng.

Với ứng dụng Spring Boot, có thể dùng `@DataMongoTest` để kiểm tra slice dữ liệu. Nếu repository nằm ngoài package mà slice test tìm kiếm, cần import cấu hình cần thiết hoặc điều chỉnh phạm vi test; đừng giả định mọi configuration ở runtime được tự động nạp vào slice.

### 10.2. Kiểm tra log và điều kiện auto-configuration

Khi khởi động, Spring Data thường ghi log về quá trình tìm repository và số interface được phát hiện. Nếu số lượng không như mong đợi, hãy kiểm tra cấu hình đang được nạp trước, sau đó xem lại package và loại repository. Có thể bật log debug cho khu vực cấu hình repository:

```yaml
logging:
  level:
    org.springframework.data.repository.config: DEBUG
```

Spring Boot cũng hỗ trợ xem báo cáo điều kiện auto-configuration ở chế độ debug để hiểu cấu hình tự động nào được kích hoạt hoặc bỏ qua. Chỉ nên bật logging chi tiết khi chẩn đoán, tránh để log mức debug quá lớn trong vận hành bình thường.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và sửa |
| --- | --- | --- |
| `No qualifying bean of type 'OrderRepository'` | Package của repository nằm ngoài phạm vi quét; class config không được nạp | Kiểm tra nơi đặt `@Configuration`, `basePackageClasses` và component scan/`@Import` |
| Repository scan báo tìm thấy 0 interface | Đặt `@EnableMongoRepositories` trong package `config` nhưng không đặt base package | Chỉ định package chứa repository bằng marker hoặc chuỗi rõ ràng |
| Repository được tạo hai lần, lỗi trùng bean | Hai cấu hình quét trùng cùng interface | Chia package không chồng lấn; bỏ annotation/config dư |
| Repository chạy vào database không mong đợi | Tất cả repository đang dùng template mặc định hoặc gắn sai bean | Kiểm tra `mongoTemplateRef`, bean `MongoTemplate` và database của template |
| Không tìm được bean `mongoTemplate` hoặc tên template tùy chỉnh | Chưa có bean tương ứng hoặc ghi sai `mongoTemplateRef` | Khai báo template/connection và đối chiếu chính xác tên bean |
| Có nhiều `MongoTemplate`, inject theo kiểu bị mơ hồ | Nhiều bean cùng type và không có bean ưu tiên hoặc qualifier | Đánh dấu `@Primary` phù hợp hoặc inject bằng `@Qualifier` |
| Interface generic bị xem xét như repository cụ thể | Chưa đánh dấu interface base là `@NoRepositoryBean` | Thêm `@NoRepositoryBean` vào generic base repository |
| Reactive repository không được đăng ký như mong muốn | Dùng annotation/template cho imperative hoặc trộn package | Dùng `@EnableReactiveMongoRepositories` và reactive infrastructure, tách phạm vi quét |
| Repository tồn tại nhưng query lỗi | Sai tên field, converter, kết nối, quyền hoặc mapping | Thử truy vấn thật và kiểm tra metadata của `@Document`/`@Field` cùng database đích |

### Ví dụ chẩn đoán theo thứ tự

Giả sử `OrderService` báo không inject được `OrderRepository`:

1. Xác nhận `OrderRepository` thật sự là interface được Spring Data nhận diện (ví dụ extends `MongoRepository<Order, String>`).
2. Xác nhận `OrdersRepositoryConfig` đã được nạp vào ApplicationContext.
3. Kiểm tra package của marker `OrdersRepositoryPackage`, rồi đối chiếu vị trí repository.
4. Kiểm tra các annotation enable repository khác hoặc cấu hình auto-configuration đang hoạt động.
5. Xem log bootstrap repository và test `getBeansOfType(OrderRepository.class)`.
6. Khi bean đã hiện diện, mới tiếp tục xác minh kết nối MongoDB và truy vấn thực tế.

Đừng sửa bằng cách đưa `@ComponentScan("com.example")` rộng khắp một cách tùy tiện: mở rộng component scan không thay thế việc xác định đúng repository base package, và có thể nạp thêm cấu hình không mong muốn.

## 12. Checklist thiết kế trước khi đưa vào hệ thống

Trước khi chốt cấu hình, tự trả lời:

- **Nguồn kích hoạt là gì?** Spring Boot auto-configuration, `@EnableMongoRepositories`, hay cả hai theo cấu hình có chủ đích?
- **Repository nằm ở đâu?** Package chứa interface có nằm trong phạm vi quét hay không?
- **Class cấu hình có được Spring nạp?** Qua component scan hoặc `@Import`?
- **Có package nào bị quét dư?** Các package con, repository thí nghiệm, interface generic hoặc package của module khác?
- **Template nào được dùng?** `mongoTemplateRef` mặc định hay tên bean tường minh; template trỏ database nào?
- **Phong cách truy cập đúng chưa?** `MongoRepository`/`MongoTemplate` hay `ReactiveMongoRepository`/`ReactiveMongoTemplate`?
- **Đã xác minh được kết quả?** Có test đăng ký bean và kiểm thử truy vấn với MongoDB phù hợp?

### Bài tập tình huống

Ứng dụng có hai module:

```text
com.example.app
├── App.java
├── config
│   └── MongoConfig.java
├── customer.repository
│   └── CustomerRepository.java
└── report.repository
    └── DailyReportRepository.java
```

Yêu cầu: chỉ đăng ký `CustomerRepository` vào `customerMongoTemplate` trỏ database `crm`, còn `DailyReportRepository` vào `reportMongoTemplate` trỏ database `reporting`.

**Gợi ý giải:**

1. Tạo marker riêng trong hai package repository.
2. Tạo hai class cấu hình có `@EnableMongoRepositories`, mỗi class dùng `basePackageClasses` và `mongoTemplateRef` khác nhau.
3. Đăng ký hai `MongoTemplate` với database phù hợp, thiết lập client/factory và quyền kết nối cần thiết.
4. Đảm bảo các lớp cấu hình được Spring nạp, vùng quét không chồng lấn.
5. Kiểm tra mỗi repository được tạo đúng một bean; thực hiện truy vấn thử và xác nhận dữ liệu ở đúng database.

## Ghi nhớ

`@EnableMongoRepositories` là công cụ **chọn và đăng ký repository interface**. Trong Spring Boot thông thường, việc kích hoạt này có thể đã được auto-configuration đảm nhận; khi cần kiểm soát phạm vi hoặc nhiều nguồn dữ liệu, hãy khai báo tường minh với `basePackageClasses` hoặc `basePackages`. Vị trí của class `@Configuration` quyết định phạm vi mặc định nếu không chỉ rõ, còn `mongoTemplateRef` quyết định repository sử dụng bean `MongoTemplate` nào. Tách bạch repository scan, component scan, document mapping và cấu hình kết nối giúp phát hiện lỗi sớm và giữ kiến trúc Spring Data MongoDB dễ bảo trì.
