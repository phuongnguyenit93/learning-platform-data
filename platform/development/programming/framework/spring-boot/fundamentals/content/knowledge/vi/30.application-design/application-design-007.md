# Cấu hình theo chức năng và hạn chế component scan quá rộng

Khi ứng dụng Spring Boot lớn dần, số lượng controller, service, repository, configuration class và integration adapter tăng lên nhanh chóng. Nếu tất cả được đặt trong một vài package lớn rồi để Spring quét từ một package gốc quá rộng, ứng dụng có thể vẫn khởi động nhưng ranh giới giữa các chức năng trở nên khó hiểu: một module vô tình đăng ký bean của module khác, hai class cùng tên tạo bean trùng, một cấu hình chỉ dành cho test/dev xuất hiện ở runtime không mong muốn, hoặc một module thư viện bị quét như một phần của ứng dụng.

Một cách tổ chức dễ kiểm soát là **đặt cấu hình và component theo chức năng (feature/module)**, đồng thời giới hạn phạm vi component scan vào package mà ứng dụng thực sự sở hữu. Mỗi chức năng có thể gom controller, service, repository, domain logic và configuration liên quan; những thành phần dùng chung được tách thành module/shared package có ranh giới rõ ràng.

Mục tiêu không phải tạo càng nhiều package càng tốt. Mục tiêu là làm cho quan hệ giữa chức năng và bean registration trở nên dễ dự đoán:

- Nhìn package có thể nhận ra thành phần thuộc chức năng nào.
- Một application module biết rõ những module nào được đưa vào context.
- Configuration của một feature không tự động ảnh hưởng toàn bộ ứng dụng khi không cần thiết.
- Test có thể khởi tạo một slice hoặc module phù hợp mà không phải scan toàn bộ hệ thống.
- Việc thêm module mới không vô tình kéo theo hàng loạt bean không liên quan.

Bài học này dùng Spring Boot 3.x, Java và Spring Framework annotation-based configuration. Nội dung tập trung vào cách chọn package boundary, component scan, cấu hình theo chức năng, tích hợp module tường minh, các giới hạn cần lưu ý và cách kiểm tra ứng dụng khi context khởi tạo sai.

## 1. Vì sao component scan quá rộng gây khó kiểm soát?

Spring quản lý các object được đăng ký thành bean trong ApplicationContext. Một cách phổ biến để đăng ký bean là component scanning: Spring tìm các class mang stereotype như `@Component`, `@Service`, `@Repository`, `@Controller` hoặc `@Configuration` trong phạm vi được chỉ định.

Ví dụ:

~~~java
@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bao gồm component scanning từ package chứa class này trở xuống theo mặc định. Nếu class nằm ở package gốc phù hợp, Spring có thể tìm được các component của ứng dụng mà không cần khai báo từng package.

Nhưng nếu main class được đặt trong package quá rộng, chẳng hạn package gốc dùng chung cho nhiều ứng dụng, thư viện hoặc module không thuộc service hiện tại, phạm vi scan có thể kéo vào các component ngoài ý muốn.

Ví dụ:

~~~text
com.company
├── platform
│   ├── audit
│   │   └── AuditConfiguration.java
│   ├── identity
│   │   └── IdentityAdminController.java
│   └── shared
│       └── SharedCacheConfiguration.java
├── shop
│   ├── ShopApplication.java
│   └── order
│       └── OrderService.java
└── analytics
    └── AnalyticsBatchApplication.java
~~~

Nếu `ShopApplication` nằm ở `com.company`, component scan mặc định có thể tìm cả `platform`, `shop` và `analytics`. Trong khi ứng dụng Shop có thể chỉ cần một phần của platform, nó lại vô tình đăng ký controller hoặc batch configuration thuộc ứng dụng khác.

### 1.1. Các hậu quả thường gặp

| Vấn đề | Biểu hiện |
| --- | --- |
| Bean ngoài ý muốn | Controller, scheduler hoặc integration client của module khác xuất hiện trong context |
| Bean trùng tên | Hai component cùng tên mặc định hoặc cùng bean name gây conflict |
| Dependency bị kéo ngoài phạm vi | Một service yêu cầu bean mà ứng dụng hiện tại không cấu hình |
| Auto-configuration tương tác bất ngờ | Bean do ứng dụng/module khác đăng ký làm Boot auto-configuration back off |
| Khởi động chậm | Spring phải xử lý nhiều candidate, configuration và bean definitions hơn |
| Test khó cô lập | Một test module phải khởi tạo nhiều bean không liên quan |
| Boundary mờ | Không rõ module nào chịu trách nhiệm cho bean/configuration |
| Security surface rộng | Route hoặc management component không dự kiến được đăng ký |

Không phải mọi component scan rộng đều lập tức làm ứng dụng lỗi. Nhiều lỗi chỉ xuất hiện khi thêm một module mới hoặc khi môi trường/profile thay đổi. Đây là lý do package boundary cần được thiết kế sớm.

## 2. Component scan bắt đầu từ đâu?

Annotation `@SpringBootApplication` thường được đặt trên main application class:

~~~java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Theo mặc định, component scan lấy package của `ShopApplication` làm base package và quét package đó cùng các subpackage.

Nếu class ở `com.example.shop`, phạm vi mặc định bao gồm:

~~~text
com.example.shop
com.example.shop.order
com.example.shop.payment
com.example.shop.inventory
com.example.shop.configuration
~~~

Nhưng không bao gồm sibling package:

~~~text
com.example.identity
com.example.analytics
~~~

Sơ đồ:

~~~text
com.example
├── shop                 <-- base package nếu ShopApplication ở đây
│   ├── ShopApplication
│   ├── order
│   └── payment
├── identity             <-- không nằm dưới com.example.shop
└── analytics            <-- không nằm dưới com.example.shop
~~~

### 2.1. Đặt main class ở package gốc của ứng dụng

Một convention phổ biến:

~~~text
com.example.shop
├── ShopApplication.java
├── order
├── payment
├── inventory
└── shared
~~~

Main class ở package gốc giúp component scan bao phủ các feature packages của chính ứng dụng. Bạn thường không cần chỉ định `scanBasePackages`.

### 2.2. Không đặt main class trong default package

Không nên để class ứng dụng ở default package, tức không có dòng `package`:

~~~java
@SpringBootApplication
public class ShopApplication {
}
~~~

Khi không có package rõ ràng, phạm vi quét có thể rộng đến mức bao phủ rất nhiều class trên classpath và gây khó kiểm soát. Hãy luôn đặt main class trong một package có tên, thường là root package của application module.

### 2.3. Main class nằm quá sâu

Nếu đặt main class tại:

~~~text
com.example.shop.order.bootstrap.ShopApplication
~~~

thì scan mặc định bắt đầu từ `com.example.shop.order.bootstrap` và các subpackage. Các package anh em như `com.example.shop.payment` hoặc `com.example.shop.inventory` không được quét.

Ứng dụng có thể khởi động nhưng thiếu bean của các feature khác. Đặt main class ở root package hoặc cấu hình scan boundary có chủ đích.

## 3. Tổ chức package theo layer và theo feature

Hai cách tổ chức phổ biến:

**Package theo layer:**

~~~text
com.example.shop
├── controller
│   ├── OrderController.java
│   └── PaymentController.java
├── service
│   ├── OrderService.java
│   └── PaymentService.java
├── repository
│   ├── OrderRepository.java
│   └── PaymentRepository.java
└── config
    └── SecurityConfiguration.java
~~~

**Package theo feature:**

~~~text
com.example.shop
├── ShopApplication.java
├── order
│   ├── OrderController.java
│   ├── OrderService.java
│   ├── OrderRepository.java
│   └── OrderConfiguration.java
├── payment
│   ├── PaymentController.java
│   ├── PaymentService.java
│   ├── PaymentGateway.java
│   └── PaymentConfiguration.java
└── inventory
    ├── InventoryController.java
    ├── InventoryService.java
    └── InventoryRepository.java
~~~

Package theo layer giúp nhận diện loại kỹ thuật của class. Package theo feature giúp nhận diện **chức năng nghiệp vụ mà class phục vụ**.

### 3.1. Vì sao package theo feature thường phù hợp khi hệ thống lớn?

Khi thêm một yêu cầu “hủy đơn hàng”, phần lớn thay đổi nằm trong feature order. Developer có thể tìm controller/service/repository/configuration liên quan trong cùng namespace.

Với package theo layer, các file của một feature nằm rải rác:

- Controller trong `controller`.
- Service trong `service`.
- Repository trong `repository`.
- Configuration trong `config`.

Khi feature lớn, việc hiểu toàn bộ chức năng đòi hỏi nhảy qua nhiều package.

Package theo feature giúp:

- Giữ thay đổi gần nhau theo nghiệp vụ.
- Giảm sự phụ thuộc vào package dùng chung quá rộng.
- Dễ chia ownership giữa các team.
- Dễ kiểm soát component scan theo module.
- Dễ tách module thành artifact riêng khi cần.

### 3.2. Package theo feature không bắt buộc nhồi mọi thứ vào một package

Feature có thể có subpackage:

~~~text
com.example.shop.order
├── api
│   ├── OrderController.java
│   └── OrderRequest.java
├── application
│   ├── CreateOrderService.java
│   └── CancelOrderService.java
├── domain
│   ├── Order.java
│   └── OrderPolicy.java
├── persistence
│   └── JpaOrderRepository.java
└── configuration
    └── OrderConfiguration.java
~~~

Cấu trúc này vẫn tổ chức theo feature, nhưng phân loại nội bộ theo trách nhiệm. Độ sâu package nên phục vụ khả năng tìm kiếm và boundary, không phải mục tiêu thẩm mỹ.

### 3.3. Shared package cần có giới hạn

Một package `shared` dễ trở thành nơi chứa mọi thứ không biết đặt đâu. Sau thời gian dài nó có thể chứa:

- Helper dùng cho một feature duy nhất.
- Configuration của nhiều module.
- DTO gắn với một API cụ thể.
- Repository hoặc client không có owner rõ.
- Component có dependency đến nhiều feature.

Hãy chỉ đưa vào shared những abstraction thực sự được dùng chung và có contract ổn định. Logic nghiệp vụ riêng nên ở trong feature sở hữu nó.

## 4. Đặt cấu hình gần feature sở hữu

Một configuration class nên nằm gần các component mà nó cấu hình, nếu phạm vi sử dụng chủ yếu là một feature.

Ví dụ:

~~~text
com.example.shop
├── ShopApplication.java
├── payment
│   ├── PaymentService.java
│   ├── PaymentGatewayClient.java
│   └── configuration
│       ├── PaymentConfiguration.java
│       └── PaymentProperties.java
└── order
    ├── OrderService.java
    └── configuration
        └── OrderProperties.java
~~~

`PaymentConfiguration` có thể đăng ký client, timeout, retry policy hoặc converter chỉ phục vụ payment.

~~~java
package com.example.shop.payment.configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway(
            PaymentProperties properties,
            RestClient.Builder builder) {

        RestClient client = builder
                .baseUrl(properties.baseUrl())
                .build();

        return new HttpPaymentGateway(client);
    }
}
~~~

Properties type-safe:

~~~java
package com.example.shop.payment.configuration;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration connectTimeout,
        boolean enabled
) {
}
~~~

Cấu hình trong application YAML:

~~~yaml
app:
  payment:
    base-url: https://payments.example.internal
    connect-timeout: 3s
    enabled: true
~~~

Ở đây configuration và properties nằm trong namespace payment, giúp người đọc biết cấu hình này thuộc feature nào.

### 4.1. Configuration class cũng là component

`@Configuration` là một stereotype được component scanning nhận diện. Nếu class nằm ngoài scan boundary, Spring không tự đăng ký nó chỉ vì file tồn tại trên classpath.

Bạn có thể:

- Đặt class trong package được scan.
- Import class bằng `@Import`.
- Đăng ký bean qua configuration của application module.
- Dùng auto-configuration/module configuration theo convention phù hợp.

Không nên mở rộng component scan toàn bộ project chỉ để một configuration class được tìm thấy.

### 4.2. Dùng proxyBeanMethods=false khi phù hợp

Với configuration class chỉ đăng ký bean và không cần gọi chéo `@Bean` methods như các lời gọi Java thông thường, có thể dùng:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {
}
~~~

Điều này tránh CGLIB method interception của configuration class. Khi đó nếu một `@Bean` method gọi trực tiếp method `@Bean` khác, nó có thể tạo một object mới thay vì lấy singleton bean từ container. Vì vậy hãy inject dependency qua tham số method:

~~~java
@Bean
PaymentFacade paymentFacade(PaymentGateway paymentGateway) {
    return new PaymentFacade(paymentGateway);
}
~~~

Đây là cách rõ ràng và tương thích với lite configuration semantics.

## 5. @SpringBootApplication và scanBasePackages

`@SpringBootApplication` kết hợp nhiều annotation, trong đó có `@ComponentScan`. Có thể tùy chỉnh base packages:

~~~java
@SpringBootApplication(
        scanBasePackages = {
                "com.example.shop",
                "com.example.platform.audit"
        }
)
public class ShopApplication {
}
~~~

Ứng dụng scan package shop và một phần audit platform.

### 5.1. scanBasePackages là alias của component scan base packages

Trong `@SpringBootApplication`, `scanBasePackages` được dùng như một alias để cấu hình package scan. Nó không tự thay đổi mọi cơ chế scan khác như JPA entity scanning hoặc repository scanning.

Đây là điểm quan trọng: **component scan, entity scan và repository scan là những cơ chế riêng**.

### 5.2. Không dùng scanBasePackages quá rộng

Một cấu hình:

~~~java
@SpringBootApplication(scanBasePackages = "com.example")
~~~

có thể hợp lý nếu `com.example` chỉ chứa một application và các module được phép đăng ký vào context. Nhưng nếu namespace này chứa nhiều service độc lập, batch app hoặc thư viện khác, phạm vi có thể quá rộng.

Đừng chọn package chỉ vì nó là prefix chung của mọi module. Chọn base package dựa trên **ownership và ranh giới runtime**.

### 5.3. Dùng type-safe marker class thay cho string khi cần

`@ComponentScan` hỗ trợ `basePackageClasses`:

~~~java
@SpringBootApplication
@ComponentScan(basePackageClasses = {
        ShopApplication.class,
        AuditModuleMarker.class
})
public class ShopApplication {
}
~~~

Một marker type có thể là class/interface rỗng nằm trong package module. Cách này tránh typo string và giúp refactor package an toàn hơn.

Lưu ý: `@SpringBootApplication` đã bao gồm `@ComponentScan`. Khi thêm một `@ComponentScan` riêng, hãy kiểm tra rõ cấu hình có được hợp nhất như mong muốn hay tạo phạm vi scan không chủ đích. Thông thường, có thể đặt cấu hình scan trực tiếp trên `@SpringBootApplication` bằng thuộc tính tương ứng thay vì chồng nhiều annotation.

### 5.4. Base package không phải danh sách class bean

Component scan nhận package làm vùng tìm kiếm, không phải danh sách class cần đăng ký. Nếu muốn tích hợp một module cụ thể mà không quét toàn package, `@Import` hoặc configuration module tường minh có thể phù hợp hơn.

## 6. @Import để kết nối module có chủ đích

Một module có thể cung cấp một configuration entry point:

~~~java
package com.example.shop.payment.configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentModuleConfiguration {

    @Bean
    PaymentGateway paymentGateway(PaymentProperties properties) {
        return new HttpPaymentGateway(properties);
    }

    @Bean
    PaymentService paymentService(PaymentGateway paymentGateway) {
        return new PaymentService(paymentGateway);
    }
}
~~~

Application import module:

~~~java
@SpringBootApplication
@Import(PaymentModuleConfiguration.class)
public class ShopApplication {
}
~~~

Lợi ích:

- Application thể hiện rõ module nào được tích hợp.
- Module có một entry point ổn định.
- Không cần scan mọi package trong library.
- Dễ kiểm tra module configuration độc lập.
- Thay đổi nội bộ package ít ảnh hưởng consumer hơn.

### 6.1. Import một configuration không nhất thiết scan tất cả component trong package

`@Import` đăng ký configuration class được chỉ định và các thành phần mà configuration khai báo/import. Nó không tự biến package chứa class đó thành một vùng component scan tổng quát.

Nếu configuration cần component khác, có thể khai báo `@Bean` hoặc import configuration tương ứng một cách rõ ràng.

### 6.2. Module configuration có thể import configuration con

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
        PaymentClientConfiguration.class,
        PaymentMappingConfiguration.class
})
public class PaymentModuleConfiguration {
}
~~~

Đây là cách tạo module entry point. Consumer chỉ import module configuration chính; các implementation details được module tự quản lý.

### 6.3. Tránh tạo vòng phụ thuộc giữa configuration

Nếu `PaymentConfiguration` import `OrderConfiguration` và ngược lại, module boundary không còn rõ. Hãy xem xét chuyển abstraction dùng chung sang module nhỏ hơn hoặc để application composition root kết nối hai module.

## 7. Application composition root

Trong một ứng dụng modular, main application class thường đóng vai trò **composition root**: nơi quyết định module nào được kết hợp để tạo thành runtime application.

Ví dụ:

~~~java
@SpringBootApplication
@Import({
        OrderModuleConfiguration.class,
        PaymentModuleConfiguration.class,
        InventoryModuleConfiguration.class
})
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Sơ đồ:

~~~mermaid
flowchart TD
    A["ShopApplication / Composition root"] --> O["OrderModuleConfiguration"]
    A --> P["PaymentModuleConfiguration"]
    A --> I["InventoryModuleConfiguration"]
    O --> OS["Order beans"]
    P --> PS["Payment beans"]
    I --> IS["Inventory beans"]
~~~

Điều này làm runtime composition dễ nhìn thấy. Một batch application khác có thể import chỉ những module cần thiết:

~~~java
@SpringBootApplication
@Import({
        InventoryModuleConfiguration.class,
        ImportJobConfiguration.class
})
public class InventoryImportApplication {
}
~~~

Cùng một codebase có thể có nhiều executable applications với tập bean khác nhau, miễn module boundaries và dependencies được thiết kế rõ.

## 8. Điều kiện đăng ký bean: @Conditional

Một configuration có thể chỉ được kích hoạt khi feature được bật hoặc dependency phù hợp có mặt.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentModuleConfiguration {

    @Bean
    PaymentGateway paymentGateway(PaymentProperties properties) {
        return new HttpPaymentGateway(properties);
    }
}
~~~

Khi:

~~~yaml
app:
  payment:
    enabled: false
~~~

configuration này không được áp dụng theo điều kiện đã đặt. Nếu property thiếu, mặc định `havingValue` không tự coi nó là true; hãy quyết định rõ `matchIfMissing` khi cần.

### 8.1. ConditionalOnClass

Một module integration có thể chỉ được kích hoạt nếu library tồn tại:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.sdk.Client")
public class VendorIntegrationConfiguration {
}
~~~

Dùng tên class dạng string có thể tránh resolve type khi dependency không có mặt. Trong auto-configuration library, cần chú ý class loading và cấu trúc nested configuration để điều kiện thực sự được áp dụng đúng trước khi bean method tham chiếu tới type tùy chọn.

### 8.2. ConditionalOnMissingBean

Có thể cung cấp default implementation nếu consumer chưa tự khai báo:

~~~@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway defaultPaymentGateway() {
    return new DisabledPaymentGateway();
}
~~~

Điều này phù hợp với module extensible, nhưng cần định nghĩa rõ contract và điều kiện fallback. Đừng dùng conditional để che giấu việc scan thiếu bean bắt buộc: nếu module không được import, cả service và default gateway có thể đều không tồn tại.

### 8.3. Conditional không thay thế module boundary

Một package scan quá rộng vẫn có thể tìm component không mong muốn dù một số configuration được conditional. Hãy giới hạn scan trước; dùng condition để xử lý các lựa chọn cấu hình/optional integrations đúng mục đích.

## 9. Exclude component khỏi scan

Có trường hợp một package được scan chung nhưng một component cụ thể không nên đăng ký. `@ComponentScan` hỗ trợ include/exclude filters.

Ví dụ loại một class:

~~~java
@SpringBootApplication
@ComponentScan(
        basePackageClasses = ShopApplication.class,
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = LegacyPaymentController.class
        )
)
public class ShopApplication {
}
~~~

Hoặc loại theo annotation:

~~~java
@ComponentScan.Filter(
        type = FilterType.ANNOTATION,
        classes = InternalOnlyComponent.class
)
~~~

Có thể dùng các filter type khác như regex hoặc AspectJ pattern, tùy nhu cầu.

### 9.1. Exclude filter không phải công cụ thay thế cấu trúc package

Nếu phải thêm nhiều exclusions để loại các component không thuộc ứng dụng, có thể base package đã quá rộng. Tách package/module rõ hơn thường giúp giảm danh sách ngoại lệ và tránh quên exclude khi có component mới.

### 9.2. Không loại nhầm infrastructure component

Một filter theo annotation chung có thể vô tình loại component cần thiết. Sau khi thêm exclusion, hãy kiểm tra context startup và các feature thực sự cần bean đó.

## 10. Component scan khác entity scan và repository scan

Đây là một trong những nguồn lỗi thường gặp trong ứng dụng modular.

- **Component scan** tìm các Spring components như service, controller, configuration.
- **Entity scan** tìm JPA entity classes.
- **Repository scan** tìm Spring Data repository interfaces.

Đặt `scanBasePackages` không tự đảm bảo entity và repository ở module khác được phát hiện.

### 10.1. EntityScan

Giả sử:

~~~text
com.example.shop
└── ShopApplication.java

com.example.platform.persistence
└── customer
    └── CustomerEntity.java
~~~

Nếu entity nằm ngoài package scan mặc định của application, có thể cấu hình:

~~~java
@SpringBootApplication
@EntityScan(basePackageClasses = CustomerEntity.class)
public class ShopApplication {
}
~~~

`@EntityScan` thiết lập package dùng để tìm entity classes cho các auto-configuration data technologies liên quan. Nó không đăng ký mọi service trong package đó thành Spring bean.

### 10.2. EnableJpaRepositories

Repository interface:

~~~java
package com.example.platform.persistence.customer;

public interface CustomerRepository
        extends JpaRepository<CustomerEntity, Long> {
}
~~~

Có thể chỉ định package repository:

~~~java
@SpringBootApplication
@EnableJpaRepositories(
        basePackageClasses = CustomerRepository.class
)
@EntityScan(basePackageClasses = CustomerEntity.class)
public class ShopApplication {
}
~~~

`@EnableJpaRepositories` điều khiển việc tìm Spring Data JPA repository interfaces. Đây là cơ chế riêng với component scan.

### 10.3. Chỉ định marker classes

Dùng `basePackageClasses` giúp package refactor an toàn hơn so với chuỗi:

~~~java
@EntityScan(basePackageClasses = {
        CustomerEntity.class,
        OrderEntity.class
})
~~~

Tuy nhiên, nếu danh sách entity/repository ngày càng dài, hãy xem xét một persistence module configuration để gom trách nhiệm và cung cấp entry point rõ ràng.

## 11. Cấu hình theo chức năng với @ConfigurationProperties

Configuration values cũng nên được nhóm theo chức năng thay vì gom tất cả vào một class lớn chứa hàng trăm field.

Ví dụ:

~~~text
com.example.shop
├── order
│   └── configuration
│       └── OrderProperties.java
├── payment
│   └── configuration
│       └── PaymentProperties.java
└── inventory
    └── configuration
        └── InventoryProperties.java
~~~

Payment properties:

~~~java
@ConfigurationProperties(prefix = "app.payment")
@Validated
public record PaymentProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout,
        @Min(1) @Max(5) int maxAttempts
) {
}
~~~

Đăng ký:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {
}
~~~

YAML:

~~~yaml
app:
  payment:
    base-url: https://payments.example.internal
    timeout: 2s
    max-attempts: 3
~~~

### 11.1. Lợi ích của type-safe configuration

- Property có kiểu cụ thể, không phải đọc string thủ công ở nhiều nơi.
- Validation tập trung tại boundary bind.
- Prefix cho biết feature sở hữu cấu hình.
- Test có thể cung cấp property riêng cho module.
- Tài liệu cấu hình dễ chia theo feature.

Không nên tạo một `ApplicationProperties` khổng lồ chỉ vì mọi property đều thuộc cùng một ứng dụng. Các nhóm cấu hình nên phản ánh chức năng và ownership.

### 11.2. Không đặt secret trong source-controlled defaults

Ví dụ URI nội bộ có thể để trong config, nhưng password/API key nên đến từ secret manager hoặc environment/config source được bảo vệ. Tổ chức theo feature không làm dữ liệu tự an toàn; vẫn cần chính sách secret handling riêng.

## 12. @ConfigurationPropertiesScan có phạm vi riêng

Có thể dùng:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ShopApplication {
}
~~~

Khi không chỉ định package, `@ConfigurationPropertiesScan` dùng package của class được annotate làm điểm bắt đầu scan theo quy tắc của nó.

Có thể giới hạn rõ:

~~~java
@ConfigurationPropertiesScan(basePackageClasses = {
        PaymentProperties.class,
        OrderProperties.class
})
~~~

Điểm cần phân biệt:

- `@ComponentScan` tìm component stereotype.
- `@ConfigurationPropertiesScan` tìm các type được đánh dấu `@ConfigurationProperties`.
- `@EntityScan` tìm JPA entities.
- `@EnableJpaRepositories` tìm repository interfaces.

Đừng dùng một annotation scan để kỳ vọng nó tự thực hiện các scan khác.

## 13. Modular monolith: mỗi feature có module configuration

Một modular monolith là một ứng dụng triển khai cùng nhau nhưng có các module chức năng với trách nhiệm và API nội bộ rõ ràng.

Ví dụ:

~~~text
com.example.shop
├── ShopApplication.java
├── order
│   ├── api
│   ├── application
│   ├── domain
│   └── configuration
├── payment
│   ├── api
│   ├── application
│   ├── domain
│   └── configuration
└── inventory
    ├── api
    ├── application
    ├── domain
    └── configuration
~~~

Mỗi feature có thể cung cấp:

~~~java
@Configuration(proxyBeanMethods = false)
public class OrderModuleConfiguration {
    // Khai báo bean của module order nếu cần.
}
~~~

Application composition root import các module được phép chạy.

### 13.1. API module khác implementation package

Nếu feature khác cần gọi order, nên phụ thuộc vào một API/application contract ổn định, ví dụ `OrderQueryService` hoặc một interface. Tránh để feature payment truy cập trực tiếp repository nội bộ của order.

Component scan rộng có thể khiến mọi class kỹ thuật đều trở nên injectable, nhưng **được đăng ký làm bean không có nghĩa được phép dùng như public module API**.

### 13.2. Package-private để giới hạn implementation

Java package visibility có thể giúp giới hạn một số implementation details:

~~~java
class JpaOrderRepositoryAdapter {
}
~~~

Nếu không có modifier public, class chỉ truy cập được trong package (và các trường hợp Java visibility tương ứng). Tuy nhiên, component scanning và proxying có những yêu cầu riêng về visibility; hãy thiết kế bean boundary sao cho Spring có thể tạo/invoke bean đúng cách.

Không dùng package-private một cách máy móc cho mọi bean. Chọn visibility theo API module và cách framework cần truy cập.

## 14. Multi-module Gradle/Maven không tự quyết định component scan

Một project multi-module có thể có:

~~~text
shop/
├── shop-app/
├── order-module/
├── payment-module/
└── platform-contracts/
~~~

Việc các module được khai báo dependency trong Gradle/Maven chỉ làm artifact/class có mặt trên classpath. **Component scan vẫn tuân theo package boundaries và scan configuration**.

Ví dụ app phụ thuộc module payment nhưng package payment nằm ngoài root package:

~~~text
com.example.shop.app
com.example.shop.payment
~~~

Main class ở `com.example.shop.app` sẽ không mặc định scan sibling `com.example.shop.payment`. Bạn cần import module configuration hoặc chỉ định base package có chủ đích.

### 14.1. Dùng module entry point thay vì quét toàn bộ group

Trong library module:

~~~java
package com.example.shop.payment.configuration;

@Configuration(proxyBeanMethods = false)
public class PaymentModuleConfiguration {
    // Module beans.
}
~~~

Trong app:

~~~java
@SpringBootApplication
@Import(PaymentModuleConfiguration.class)
public class ShopApplication {
}
~~~

Cách này làm contract tích hợp rõ hơn. Library có thể thay đổi package nội bộ mà không yêu cầu application scan toàn bộ namespace.

### 14.2. Dependency graph và bean graph là hai đồ thị

- Dependency graph của Gradle/Maven quyết định artifact/class nào có trên classpath.
- Bean graph của Spring quyết định object nào được đăng ký và inject vào nhau.

Có dependency trên classpath không tự động làm mọi class trở thành bean. Ngược lại, scan được component nhưng dependency cần thiết không có trên runtime classpath thì bean creation vẫn thất bại.

## 15. Auto-configuration và component scan là hai cơ chế khác nhau

Spring Boot auto-configuration dựa trên conditions, classpath và cấu hình để cung cấp beans/infrastructure theo convention. Component scan tìm các component do ứng dụng/library khai báo.

Ví dụ, `spring-boot-starter-web` có thể khiến Boot cấu hình MVC và embedded server. Nhưng controller của ứng dụng vẫn phải được phát hiện bởi component scan hoặc được đăng ký bằng cơ chế phù hợp.

### 15.1. @SpringBootApplication có @EnableAutoConfiguration

`@SpringBootApplication` bao gồm `@EnableAutoConfiguration`. Auto-configuration không đơn giản là “scan tất cả package dependency”. Nó dùng metadata/import selectors và conditions để quyết định configuration nào áp dụng.

Vì vậy:

- Component scan rộng có thể tìm các component trong package không mong muốn.
- Auto-configuration có thể được kích hoạt do classpath và conditions.
- Hai nguồn bean có thể tương tác, ví dụ custom bean khiến auto-configuration back off.

### 15.2. Không dùng component scan để bật mọi tính năng Boot

Nếu một feature cần auto-configuration, hãy đảm bảo dependency và configuration đúng. Việc thêm package vào scan không thay thế dependency hoặc điều kiện classpath cần thiết.

### 15.3. Kiểm tra condition report

Trong môi trường phát triển:

~~~bash
java -jar app.jar --debug
~~~

Condition evaluation report giúp hiểu vì sao một auto-configuration được match hoặc không match. Nó bổ sung cho việc xem component scan, không phải cùng một báo cáo.

## 16. Bean name conflict khi scan quá rộng

Mặc định, Spring thường suy ra bean name từ tên class với quy tắc đặt tên bean. Hai component ở package khác nhau nhưng cùng tên đơn giản có thể xung đột:

~~~java
package com.example.shop.order;

@Service
public class DefaultValidator {
}
~~~

~~~java
package com.example.shop.payment;

@Service
public class DefaultValidator {
}
~~~

Nếu cả hai được scan, bean name mặc định có thể cùng là `defaultValidator`. Tùy bean registration settings và version/configuration, context có thể báo bean definition conflict hoặc một registration không được cho phép ghi đè.

### 16.1. Không giải quyết mọi conflict bằng tên bean dài

Có thể đặt tên tường minh:

~~~java
@Service("orderValidator")
public class DefaultValidator {
}
~~~

Nhưng nếu application không cần bean của một feature, cách đúng có thể là giới hạn module scan hoặc chỉ import module cần thiết. Đặt tên riêng chỉ giải quyết va chạm tên; nó không sửa việc đăng ký thừa component.

### 16.2. @Primary và @Qualifier giải quyết injection ambiguity

Nếu có nhiều implementation cùng interface và đều cần tồn tại:

~~~java
public interface PaymentGateway {
    void charge();
}
~~~

~~~java
@Component
@Qualifier("card")
class CardPaymentGateway implements PaymentGateway {
    public void charge() {}
}
~~~

~~~java
@Component
@Qualifier("bank")
class BankPaymentGateway implements PaymentGateway {
    public void charge() {}
}
~~~

Consumer có thể chỉ định qualifier:

~~~java
@Service
class CheckoutService {

    private final PaymentGateway gateway;

    CheckoutService(@Qualifier("card") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

`@Primary` có thể chọn implementation mặc định khi injection theo type có nhiều candidate. Nhưng đừng dùng `@Primary` để che giấu module boundaries không rõ ràng; nếu một implementation chỉ dành cho batch application, có thể nó không nên được đăng ký trong web application đó.

## 17. Profile và conditional bean không nên thay thế package ownership

Ví dụ:

~~~java
@Configuration
@Profile("dev")
public class LocalPaymentConfiguration {
    // Fake gateway dành cho development.
}
~~~

Component này chỉ được áp dụng khi profile tương ứng active, nhưng nó vẫn cần được phát hiện/đăng ký qua scan hoặc import.

Một package scan rộng có thể tìm cả production adapter và dev adapter; profile/condition quyết định bean nào được tạo. Nếu conditions sai hoặc profile không như mong muốn, ứng dụng có thể dùng nhầm implementation.

### 17.1. Profile là lựa chọn runtime, module boundary là cấu trúc

- Package/module boundary nói chức năng nào thuộc application.
- Profile nói cấu hình/implementation nào được dùng trong môi trường cụ thể.
- Condition nói bean có được tạo khi điều kiện thỏa mãn hay không.

Đừng dùng profile để giải quyết mọi vấn đề về cấu trúc package. Đừng dùng package scan để biểu diễn môi trường dev/test/prod.

## 18. Tổ chức configuration class theo trách nhiệm

Một application có thể có các lớp cấu hình:

~~~text
com.example.shop
├── ShopApplication.java
├── configuration
│   ├── WebConfiguration.java
│   ├── SecurityConfiguration.java
│   └── JacksonConfiguration.java
├── order
│   └── configuration
│       └── OrderConfiguration.java
├── payment
│   └── configuration
│       ├── PaymentConfiguration.java
│       └── PaymentProperties.java
└── inventory
    └── configuration
        └── InventoryConfiguration.java
~~~

Phân biệt:

- **Application-wide configuration**: ảnh hưởng nhiều feature hoặc toàn ứng dụng, ví dụ MVC converter, security filter chain, serialization defaults.
- **Feature configuration**: chỉ phục vụ module, ví dụ payment client, order policy hoặc inventory integration.
- **Infrastructure configuration**: kết nối database, messaging, cache hoặc external platform; nên có owner và API rõ.

### 18.1. Tránh một AppConfig khổng lồ

Một class chứa hàng chục `@Bean` methods cho mọi module khiến configuration coupling tăng. Khi sửa payment, bạn có thể vô tình ảnh hưởng order hoặc test setup.

Chia configuration theo chức năng và trách nhiệm, nhưng không nhất thiết mỗi bean một file. Nhóm các bean có vòng đời và dependency cùng thuộc một concern.

### 18.2. Tránh cấu hình nằm ngoài ownership

Nếu `PaymentConfiguration` tạo bean cho order và inventory, tên class không còn phản ánh trách nhiệm. Chuyển phần dùng chung sang infrastructure/module riêng hoặc để composition root kết nối các module.

## 19. Kiểm thử package và component scan

Test cần phản ánh cách ứng dụng thực sự được lắp ghép.

### 19.1. @SpringBootTest tìm application configuration

Một test:

~~~java
@SpringBootTest
class ShopApplicationTest {
}
~~~

thường tìm `@SpringBootConfiguration` hoặc cấu hình application phù hợp từ package của test đi lên theo quy tắc test bootstrap. Nếu test đặt ngoài package tree hoặc có nhiều application configuration, có thể cần chỉ rõ class:

~~~java
@SpringBootTest(classes = ShopApplication.class)
class ShopApplicationTest {
}
~~~

Chỉ rõ application class giúp test dùng đúng composition root.

### 19.2. Slice test giới hạn component cần tải

Ví dụ:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    // Chỉ khởi tạo phần MVC phù hợp với test.
}
~~~

Slice test không phải full component scan của toàn ứng dụng. Các service dependency có thể cần mock hoặc import cấu hình nhỏ phù hợp.

### 19.3. Test module configuration độc lập

Có thể kiểm tra module bằng context nhỏ:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PaymentModuleConfiguration.class)
class PaymentModuleConfigurationTest {
    // Assert các bean/module contract cần có.
}
~~~

Nếu module configuration phụ thuộc auto-configuration hoặc properties, bổ sung cấu hình test tương ứng. Mục tiêu là xác nhận entry point của module đăng ký đúng beans mà không cần scan mọi package của application.

### 19.4. Kiểm tra bean không mong muốn

Một integration test có thể xác nhận component thuộc ứng dụng khác không xuất hiện:

~~~java
@SpringBootTest(classes = ShopApplication.class)
class ShopBeanBoundaryTest {

    @Autowired
    ApplicationContext context;

    @Test
    void doesNotRegisterAnalyticsController() {
        assertThat(context.containsBean("analyticsController")).isFalse();
    }
}
~~~

Tên bean trong ví dụ cần khớp component thực tế. Nếu component có tên được suy ra khác hoặc bean không được đăng ký, điều chỉnh assertion theo contract mong muốn.

Test boundary nên ưu tiên kiểm tra **module behavior/API** thay vì khóa quá nhiều tên bean nội bộ dễ refactor.

## 20. Troubleshooting khi thiếu hoặc thừa bean

### 20.1. NoSuchBeanDefinitionException

Ví dụ:

~~~text
No qualifying bean of type 'com.example.shop.payment.PaymentGateway' available
~~~

Nguyên nhân có thể:

- Package payment nằm ngoài component scan.
- Module configuration chưa được import.
- Bean bị condition/profile loại.
- Implementation không có stereotype hoặc `@Bean` declaration.
- Dependency/runtime classpath thiếu module.
- Test dùng application configuration khác production.

Cách xử lý: xác định module entry point, điều kiện đăng ký bean và scan/import boundary. Không mở scan lên package root lớn nhất chỉ để lỗi biến mất.

### 20.2. BeanDefinitionOverrideException hoặc ConflictingBeanDefinitionException

Nguyên nhân có thể là hai component cùng bean name hoặc configuration được import/scan nhiều lần theo cách gây conflict.

Kiểm tra:

- Hai class có cùng tên component không?
- Có cấu hình component scan chồng lấn không?
- Có vừa import configuration vừa scan cùng package không?
- Có custom bean name trùng không?
- Có module nào không nên nằm trong application context không?

Đặt bean name rõ ràng nếu cả hai thực sự cần tồn tại. Nếu không, thu hẹp phạm vi đăng ký.

### 20.3. Bean được tạo hai lần

Có thể do cấu hình đăng ký cùng class theo nhiều con đường hoặc tạo bean thủ công đồng thời scan component. Kiểm tra context bean definitions và configuration import graph.

Đừng mặc định mọi trường hợp có hai object là do component scan; một số bean có thể có scope/prototype hoặc được tạo thủ công ngoài container.

### 20.4. App khởi động nhưng route ngoài ý muốn xuất hiện

Một controller của module khác có thể bị scan vào context. Kiểm tra component scan base package và module ownership. Với API nhạy cảm, kiểm tra cả security authorization; xóa route ngoài ý muốn khỏi context là cách giảm surface tốt hơn dựa hoàn toàn vào route protection.

## 21. Quan sát bean registration

Trong môi trường phát triển, có thể xem bean definitions qua ApplicationContext:

~~~java
String[] names = context.getBeanDefinitionNames();

Arrays.stream(names)
        .sorted()
        .forEach(System.out::println);
~~~

Cách này có thể tạo output lớn. Hãy lọc theo prefix/package hoặc loại bean đang điều tra.

Spring Boot Actuator `beans` endpoint cũng có thể hiển thị bean graph khi được thêm/expose phù hợp. Đây là thông tin nội bộ, không nên công bố rộng rãi trên production.

### 21.1. Condition report và bean list trả lời câu hỏi khác nhau

- Bean list cho biết bean nào được đăng ký.
- Condition report cho biết các auto-configuration conditions nào match/back off.
- Component scan debug logs có thể giúp biết candidate nào được tìm thấy hoặc bị loại.
- Dependency tree cho biết class/library nào có trên classpath.

Không có một nguồn duy nhất trả lời tất cả. Chọn công cụ dựa trên câu hỏi đang điều tra.

## 22. Component scan rộng và startup performance

Component scan quá rộng có thể làm tăng số candidate cần xét, số bean definitions và công việc khởi tạo context. Nhưng đừng kết luận mọi startup chậm đều do component scan.

Những nguyên nhân khác có thể gồm:

- Bean khởi tạo kết nối mạng/database đồng bộ.
- Migration hoặc schema initialization.
- Classpath rất lớn và auto-configuration nhiều.
- Bean factory post-processors.
- Configuration property validation.
- External service calls trong initialization.
- Classpath scanning của ORM hoặc framework khác.

Giới hạn scan giúp context dễ kiểm soát và có thể giảm công việc thừa, nhưng phải đo startup thực tế trước khi coi đó là tối ưu hiệu năng chính.

### 22.1. Đừng chuyển toàn bộ component thành lazy để che startup

`spring.main.lazy-initialization=true` có thể trì hoãn bean creation, nhưng lỗi thiếu dependency hoặc cấu hình có thể chỉ xuất hiện khi bean được dùng lần đầu. Nó không sửa module boundary và có thể khiến failure xuất hiện muộn hơn.

## 23. Một ví dụ thiết kế theo feature hoàn chỉnh

Cấu trúc:

~~~text
com.example.shop
├── ShopApplication.java
├── order
│   ├── api
│   │   └── OrderController.java
│   ├── application
│   │   └── OrderService.java
│   ├── domain
│   │   └── Order.java
│   └── configuration
│       └── OrderModuleConfiguration.java
├── payment
│   ├── application
│   │   └── PaymentService.java
│   ├── infrastructure
│   │   └── HttpPaymentGateway.java
│   └── configuration
│       ├── PaymentProperties.java
│       └── PaymentModuleConfiguration.java
└── inventory
    ├── application
    │   └── InventoryService.java
    └── configuration
        └── InventoryModuleConfiguration.java
~~~

Main application:

~~~java
@SpringBootApplication
@Import({
        OrderModuleConfiguration.class,
        PaymentModuleConfiguration.class,
        InventoryModuleConfiguration.class
})
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Payment module:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentModuleConfiguration {

    @Bean
    PaymentGateway paymentGateway(
            PaymentProperties properties,
            RestClient.Builder builder) {

        RestClient client = builder
                .baseUrl(properties.baseUrl())
                .build();

        return new HttpPaymentGateway(client);
    }

    @Bean
    PaymentService paymentService(PaymentGateway gateway) {
        return new PaymentService(gateway);
    }
}
~~~

Properties:

~~~java
@ConfigurationProperties("app.payment")
public record PaymentProperties(URI baseUrl) {
}
~~~

Cách thiết kế này cho thấy application root kết hợp các feature, còn mỗi module tự đăng ký implementation và configuration của mình. Nếu module nhỏ và tất cả component đã nằm trong root scan hợp lý, không cần tạo module configuration chỉ để bọc một component. Hãy dùng mức tường minh phù hợp với độ phức tạp và ranh giới thực tế.

## 24. Những lựa chọn thiết kế nên tránh

### 24.1. Đặt main class ở package của toàn công ty

~~~text
com.company
├── service-a
├── service-b
├── batch
└── shared-platform
~~~

Nếu mỗi service là một ứng dụng độc lập, đặt main class ở `com.company` có thể quét tất cả. Đặt application class trong package riêng của từng service và import shared module một cách tường minh.

### 24.2. Scan toàn bộ namespace vì “cứ để Spring tìm”

Một cấu hình:

~~~java
@ComponentScan("com")
~~~

thường quá rộng cho ứng dụng thực tế. Nó có thể tìm component của dependency, ứng dụng khác hoặc package không thuộc service hiện tại.

### 24.3. Mỗi module tự scan mọi thứ bên dưới namespace chung

Nếu tất cả module cùng dùng `@ComponentScan("com.example")`, ranh giới module gần như mất tác dụng. Module entry point tường minh hoặc base package riêng giúp composition rõ ràng hơn.

### 24.4. Một configuration class chứa mọi feature

Một `ApplicationConfig` khổng lồ làm các feature phụ thuộc vào nhau và khó kiểm thử riêng. Chia theo concern/feature, để application composition root lắp ghép.

### 24.5. Dùng @Primary để xử lý mọi bean conflict

`@Primary` chọn candidate mặc định khi inject theo type. Nó không xử lý bean name conflict và không loại bean ngoài ý muốn khỏi context.

### 24.6. Dùng exclude filter ngày càng dài

Nếu phải loại hàng chục component khỏi scan, hãy xem lại base package. Một allowlist/import list hoặc package structure phù hợp có thể dễ duy trì hơn.

### 24.7. Coi package-private là security boundary

Java package visibility hỗ trợ encapsulation trong code, nhưng không phải security mechanism để bảo vệ HTTP route, database hay secret. Hãy dùng security controls tương ứng với tài nguyên.

## 25. Checklist thiết kế cho một ứng dụng mới

Trước khi thêm nhiều component:

1. Main application class nằm trong package root của đúng application module.
2. Không đặt main class trong default package hoặc package chung của nhiều ứng dụng.
3. Feature packages phản ánh ownership nghiệp vụ.
4. Shared package chỉ chứa abstraction thực sự dùng chung.
5. Feature-specific configuration nằm gần feature.
6. `@ConfigurationProperties` có prefix theo chức năng và validation phù hợp.
7. Component scan có base package rõ ràng, không mở rộng tùy tiện.
8. Module bên ngoài scan boundary được import qua entry point rõ ràng.
9. Entity scan và repository scan được cấu hình riêng khi cần.
10. Profile/conditional beans không vô tình chọn implementation sai môi trường.
11. Test application context xác nhận module cần thiết có mặt.
12. Negative tests xác nhận component của ứng dụng khác không xuất hiện.
13. Bean conflicts được xử lý bằng ownership/name/qualifier đúng nguyên nhân.
14. Actuator bean diagnostics không được expose rộng trong production.

Checklist là cách xem xét kiến trúc; không cần thêm cấu hình phức tạp cho một ứng dụng nhỏ chỉ có vài component trong một root package hợp lý.

## 26. Bài tập thực hành

### Bài tập 1 — Quan sát component scan mặc định

Tạo main class ở `com.example.shop` và hai component ở `com.example.shop.order`, `com.example.shop.payment`. Khởi động context và xác nhận cả hai bean được tìm thấy.

### Bài tập 2 — Đặt main class quá sâu

Chuyển main class xuống `com.example.shop.order.bootstrap`. Quan sát bean payment không còn được tìm thấy theo scan mặc định. Khôi phục bằng cách đặt main class ở root package hoặc cấu hình scan phù hợp.

### Bài tập 3 — Scan quá rộng

Tạo một package `com.example.analytics` với một controller. Đặt application class ở `com.example` rồi quan sát route ngoài ý muốn xuất hiện. Thu hẹp scan để analytics không còn thuộc context của shop.

### Bài tập 4 — Package theo layer và feature

Tổ chức cùng một chức năng order theo hai cấu trúc. So sánh việc tìm controller/service/repository và xác định package nào giúp team ownership rõ hơn trong dự án giả lập.

### Bài tập 5 — Import module configuration

Tạo `PaymentModuleConfiguration` đăng ký một gateway và service. Để package payment nằm ngoài scan boundary. Dùng `@Import` để tích hợp module và viết test kiểm tra bean được tạo.

### Bài tập 6 — ConfigurationProperties theo feature

Tạo `OrderProperties` và `PaymentProperties` với prefix riêng. Thử thiếu giá trị bắt buộc và quan sát validation lúc bind. Xác định module nào sở hữu từng property.

### Bài tập 7 — Conditional module

Dùng `@ConditionalOnProperty` để bật/tắt payment integration. Kiểm tra trường hợp property true, false và bị thiếu. Giải thích giá trị `matchIfMissing` nếu được cấu hình.

### Bài tập 8 — Component scan filter

Tạo một component legacy và loại nó bằng `ASSIGNABLE_TYPE` filter. Sau đó thu hẹp base package để xem liệu exclusion còn cần thiết hay không.

### Bài tập 9 — Entity và repository scan

Đặt JPA entity/repository trong package ngoài application root. Dùng `@EntityScan` và `@EnableJpaRepositories` riêng. Xác nhận vì sao `scanBasePackages` không tự giải quyết hai loại scan này.

### Bài tập 10 — Bean name conflict

Tạo hai `@Service` class cùng tên ở hai feature packages và scan cả hai. Quan sát conflict. Thử đặt bean name riêng, sau đó cân nhắc liệu cả hai bean có thực sự nên ở cùng application context không.

### Bài tập 11 — Application composition root

Tạo một web app và một batch app dùng chung module contracts. Mỗi main application import đúng các module cần thiết. Xác nhận batch app không đăng ký controller không liên quan.

### Bài tập 12 — Test boundary

Viết một integration test xác nhận application context có các feature bắt buộc và không có bean từ module ngoài phạm vi. Dùng explicit application class trong `@SpringBootTest` để test bootstrap không phụ thuộc package vị trí test.

## 27. Ghi nhớ

Component scanning của Spring Boot tìm component từ package của main application class trở xuống theo mặc định. Đặt main class ở package root của đúng ứng dụng giúp các feature packages được phát hiện mà không cần scan toàn bộ namespace chung. Package quá rộng có thể kéo nhầm controller, service, configuration hoặc module khác vào ApplicationContext.

Tổ chức **theo feature** giúp gom controller, application service, domain, repository adapter và configuration gần chức năng sở hữu. Mỗi module có thể cung cấp một configuration entry point, còn application class đóng vai trò composition root dùng `@Import` để kết hợp đúng module. Dùng `@Conditional` cho optional integrations và `@ConfigurationProperties` với prefix theo chức năng để cấu hình rõ ràng.

Cần phân biệt component scan với entity scan, repository scan và configuration-properties scan. `scanBasePackages` chỉ điều khiển component scanning; JPA entities và Spring Data repositories có cơ chế riêng. Nếu có bean thiếu hoặc bean thừa, kiểm tra base package, import graph, condition/profile và dependency runtime trước khi mở rộng scan hoặc thêm `@Primary`.

**Một ApplicationContext dễ kiểm soát bắt đầu từ ranh giới module rõ ràng.** Hãy để mỗi application biết những feature nào nó sở hữu, cấu hình nào nó cần và những bean nào được phép tham gia runtime.
