# SpringBean dependency và component scan

Trong một ứng dụng Spring Modulith, package xác định ranh giới application module, còn Spring container quản lý các đối tượng được đăng ký thành bean. Hai cơ chế này phối hợp để tạo nên ứng dụng modular monolith: Spring tìm và khởi tạo bean, còn mô hình module giúp nhóm hiểu và kiểm soát dependency giữa các thành phần.

Khi một Spring bean trong module `order` inject một bean thuộc module `inventory`, quan hệ đó tạo ra dependency giữa hai module. Dependency cần đi qua API được công bố của `inventory` và phải tuân thủ quy tắc phụ thuộc đã khai báo. Component scan giúp Spring tìm thấy bean, nhưng bản thân việc scan không quyết định module nào được phép gọi module nào.

## 1. Hai lớp mô hình cần phân biệt

Một ứng dụng Spring Modulith có hai cơ chế liên quan:

| Cơ chế | Trách nhiệm |
| --- | --- |
| Spring component scanning và bean registration | Tìm component, tạo bean definition, khởi tạo bean và kết nối dependency |
| Spring Modulith application module model | Nhận diện module từ package, mô tả API và package nội bộ, phân tích dependency và kiểm chứng ranh giới |

Ví dụ ứng dụng bán hàng:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   └── internal
│       └── PlaceOrderService.java
└── inventory
    ├── InventoryManagement.java
    └── internal
        └── InventoryManagementImpl.java
~~~

Spring Boot có thể quét các package con của `com.acme.shop` để tìm bean. Spring Modulith nhận diện `order` và `inventory` là các application module theo cấu trúc package mặc định.

Nếu `PlaceOrderService` inject `InventoryManagement`, ứng dụng có dependency từ `order` đến API của `inventory`. Nếu nó inject thẳng `InventoryManagementImpl` nằm trong `inventory.internal`, dependency đi vào package nội bộ và có thể vi phạm quy tắc kiến trúc.

## 2. Component scan tìm Spring bean như thế nào?

`@SpringBootApplication` bao gồm cơ chế component scanning. Theo mặc định, Spring Boot bắt đầu quét từ package chứa lớp ứng dụng và đi xuống các package con.

Đặt lớp ứng dụng tại package gốc:

~~~java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Với vị trí này, component scan mặc định có thể tìm các component trong:

- `com.acme.shop.order`
- `com.acme.shop.order.internal`
- `com.acme.shop.inventory`
- `com.acme.shop.inventory.internal`

Các class được đánh dấu bằng stereotype phù hợp như `@Component`, `@Service`, `@Repository` hoặc `@Controller` có thể trở thành bean nếu chúng nằm trong phạm vi scan và thỏa các điều kiện đăng ký.

Ví dụ:

~~~java
package com.acme.shop.order.internal;

import org.springframework.stereotype.Service;

@Service
class PlaceOrderService {
    // Xử lý use case đặt hàng.
}
~~~

Spring tìm thấy `PlaceOrderService` và đăng ký bean trong application context. Class này vẫn thuộc package `order.internal`; việc được Spring quản lý không làm nó trở thành API công khai của module `order`.

## 3. Component scan không tạo ranh giới module

Component scan trả lời câu hỏi: **Spring có tìm thấy và đăng ký component này hay không?**

Mô hình module trả lời câu hỏi: **Component thuộc module nào và module khác được phép phụ thuộc vào phần nào của nó?**

Hai câu hỏi này độc lập:

| Tình huống | Kết quả |
| --- | --- |
| Bean nằm trong package được scan và ở base package của module | Bean được đăng ký; kiểu có thể thuộc API mặc định nếu được công khai phù hợp |
| Bean nằm trong package được scan nhưng ở package con `internal` | Bean vẫn có thể được đăng ký; package vẫn là nội bộ theo quy ước module |
| Class nằm trong module nhưng bị component scan loại trừ | Module vẫn có thể tồn tại trong mô hình; bean không được tạo bởi component scan |
| Bean được đăng ký bằng `@Bean` hoặc `@Import` | Bean có thể tồn tại dù không được tìm thấy qua component scan |

Vì vậy, không nên dùng `@ComponentScan` như một cách thay thế `allowedDependencies`, `@NamedInterface` hoặc `ApplicationModules.verify()`. Scan điều khiển bean discovery; quy tắc Modulith điều khiển cấu trúc và dependency kiến trúc.

## 4. Bean dependency hình thành qua constructor injection

Constructor injection thể hiện dependency của một Spring bean ngay trong chữ ký constructor. Đây là cách dễ đọc và dễ kiểm thử để khai báo các collaborator mà bean cần.

Module `inventory` công bố hợp đồng:

~~~java
package com.acme.shop.inventory;

public interface InventoryManagement {

    boolean reserve(String sku, int quantity);
}
~~~

Implementation được đặt trong package nội bộ:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.InventoryManagement;
import org.springframework.stereotype.Service;

@Service
class InventoryManagementImpl implements InventoryManagement {

    @Override
    public boolean reserve(String sku, int quantity) {
        // Kiểm tra và giữ hàng trong kho.
        return true;
    }
}
~~~

Module `order` inject API:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.InventoryManagement;
import org.springframework.stereotype.Service;

@Service
class PlaceOrderService {

    private final InventoryManagement inventory;

    PlaceOrderService(InventoryManagement inventory) {
        this.inventory = inventory;
    }

    void place(String sku, int quantity) {
        boolean reserved = inventory.reserve(sku, 1);

        if (!reserved) {
            throw new IllegalStateException("Không đủ hàng");
        }
    }
}
~~~

Spring container tìm bean phù hợp với kiểu `InventoryManagement` và inject vào constructor. Mã nguồn của `order` chỉ phụ thuộc vào interface ở base package của `inventory`. Implementation vẫn được giữ trong module sở hữu.

Đây là cách phối hợp tốt giữa dependency injection và module encapsulation: Spring lo việc kết nối object ở runtime, còn code của module tiêu thụ chỉ tham chiếu hợp đồng công khai.

## 5. Spring Modulith nhìn nhận bean dependency ra sao?

Mô hình module được xây dựng từ các kiểu và quan hệ dependency mà Spring Modulith phân tích trong codebase. Khi một bean khai báo kiểu thuộc module khác trong constructor hoặc injection point, mã nguồn có tham chiếu đến kiểu đó và mô hình có thể ghi nhận dependency giữa hai module. Việc phân tích dựa trên quan hệ kiểu trong codebase; nó không cần khởi chạy Spring context để tìm bean implementation thực tế được chọn lúc runtime.

Ví dụ:

~~~text
order.internal.PlaceOrderService
          |
          | constructor injection
          v
inventory.InventoryManagement
          ^
          | implements
inventory.internal.InventoryManagementImpl
~~~

Dependency kiến trúc của `order` hướng đến `InventoryManagement`, vì đó là kiểu mà mã nguồn của `PlaceOrderService` tham chiếu. Việc Spring chọn `InventoryManagementImpl` để tạo bean không yêu cầu `order` import implementation.

Khi một bean phụ thuộc vào kiểu thuộc module khác, hãy xem xét:

- Kiểu được inject có nằm trong base package hoặc named interface được công bố không?
- Module tiêu thụ có được phép phụ thuộc vào module cung cấp không?
- Dependency có tạo vòng phụ thuộc giữa các module không?
- Bean có được đăng ký trong application context theo cấu hình scan và bean registration hiện tại không?

Spring Modulith giúp kiểm tra các quy tắc kiến trúc từ mô hình module. Spring context test giúp xác nhận các bean thực sự có thể được tạo và kết nối. Hai loại kiểm tra bổ sung cho nhau.

## 6. Nếu inject implementation nội bộ thì điều gì xảy ra?

Giả sử `order` tham chiếu trực tiếp implementation:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.internal.InventoryManagementImpl;
import org.springframework.stereotype.Service;

@Service
class PlaceOrderService {

    private final InventoryManagementImpl inventory;

    PlaceOrderService(InventoryManagementImpl inventory) {
        this.inventory = inventory;
    }
}
~~~

Nếu implementation có khả năng truy cập từ module khác, Spring có thể tìm và inject bean đó. Tuy nhiên, dependency đã đi vào package `inventory.internal`, tức chi tiết triển khai của module cung cấp.

Điều này gây ra một số vấn đề:

- Module `order` bị gắn với class triển khai cụ thể.
- Module `inventory` khó thay đổi implementation mà không ảnh hưởng bên gọi.
- Dependency có thể vi phạm quy ước package API mặc định của Spring Modulith.
- Việc kiểm thử và thay thế implementation trở nên khó khăn hơn.

Hãy inject `InventoryManagement` từ base package. Spring vẫn có thể sử dụng implementation nội bộ để đáp ứng interface đó.

## 7. Component scan mặc định và vị trí lớp ứng dụng

Một lỗi phổ biến là đặt lớp `@SpringBootApplication` quá sâu trong cây package:

~~~text
com.acme.shop
├── order
├── inventory
└── bootstrap
    └── ShopApplication.java
~~~

Nếu lớp ứng dụng nằm tại `com.acme.shop.bootstrap`, component scan mặc định bắt đầu từ package này và các package con. Các package anh em `order` và `inventory` không nằm dưới `bootstrap`, nên có thể không được scan.

Giải pháp thường dùng là đặt lớp ứng dụng tại package gốc:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
├── inventory
└── bootstrap
~~~

Nếu không thể di chuyển lớp ứng dụng, có thể khai báo rõ phạm vi scan:

~~~java
package com.acme.shop.bootstrap;

@SpringBootApplication(scanBasePackages = "com.acme.shop")
public class ShopApplication {
}
~~~

Chỉ định package gốc có phạm vi rõ ràng giúp component scan bao phủ các module dự kiến. Tránh cấu hình scan quá rộng trên toàn bộ classpath vì có thể vô tình đăng ký component không thuộc ứng dụng.

## 8. Dùng @ComponentScan có chọn lọc

Spring cho phép dùng include filter và exclude filter để điều chỉnh component scan. Ví dụ, có thể loại một nhóm class khỏi quá trình scan:

~~~java
@Configuration(proxyBeanMethods = false)
@ComponentScan(
    basePackages = "com.acme.shop",
    excludeFilters = @ComponentScan.Filter(
        type = FilterType.REGEX,
        pattern = "com\\.acme\\.shop\\.legacy\\..*"
    )
)
class ApplicationComponentConfiguration {
}
~~~

Khi cấu hình scan có chọn lọc, hãy hiểu tác động đến bean registration:

- Component bị loại trừ sẽ không được đăng ký qua scan đó.
- Việc loại trừ bean không tự xóa application module khỏi mô hình package.
- Một bean bị loại trừ vẫn có thể được đăng ký qua `@Bean`, `@Import` hoặc một cơ chế khác.
- Nếu một bean bắt buộc bị loại khỏi context, bean phụ thuộc vào nó có thể không khởi tạo được.

Không nên loại trừ implementation chỉ để che một dependency kiến trúc. Nếu module khác cần hành vi, hãy thiết kế API công khai và cấu hình bean phù hợp.

## 9. Bean được khai báo bằng @Bean

Không phải mọi Spring bean đều được phát hiện bằng stereotype annotation. Một `@Configuration` class có thể khai báo bean thông qua phương thức `@Bean`:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.InventoryManagement;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class InventoryBeanConfiguration {

    @Bean
    InventoryManagement inventoryManagement(
            StockRepository repository) {
        return new InventoryManagementImpl(repository);
    }
}
~~~

Spring đăng ký giá trị trả về của phương thức `@Bean` thành bean. Các tham số phương thức cũng có thể là dependency được Spring inject khi tạo bean.

`@Bean` hữu ích khi:

- Cần tạo bean từ thư viện bên ngoài không có stereotype annotation.
- Muốn kiểm soát rõ cách khởi tạo hoặc cấu hình bean.
- Cần cung cấp implementation cho một interface công khai.

Hãy đặt configuration class gần module sở hữu bean. Nếu một module khác cần bean đó, module tiêu thụ nên phụ thuộc vào kiểu API được công bố thay vì import configuration nội bộ của module cung cấp.

## 10. @Import và đăng ký bean ngoài component scan

Spring cũng có thể đăng ký configuration hoặc component thông qua `@Import`:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(InventoryBeanConfiguration.class)
class ShopConfiguration {
}
~~~

`@Import` làm cho cấu hình được chỉ định tham gia vào quá trình xử lý configuration của Spring. Vì vậy, một bean có thể tồn tại trong context dù package chứa class không nằm trong component scan thông thường.

Điều này củng cố sự khác nhau giữa hai mô hình:

- Component scan là một cơ chế phát hiện và đăng ký component.
- Bean registration còn có các cơ chế khác như `@Bean`, `@Import`, auto-configuration và registrar.
- Spring Modulith kiểm tra ranh giới module dựa trên mô hình package và dependency; việc một bean được đăng ký ngoài scan không tự động mở package nội bộ thành API.

Khi gặp một bean không được tìm thấy, hãy kiểm tra cả component scan lẫn các cơ chế đăng ký bean tường minh.

## 11. Giữ component scan phù hợp với ranh giới module

Một cấu trúc package rõ ràng giúp việc scan và kiến trúc dễ hiểu:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   ├── internal
│   │   └── PlaceOrderService.java
│   └── web
│       └── OrderController.java
├── inventory
│   ├── InventoryManagement.java
│   ├── internal
│   │   ├── InventoryManagementImpl.java
│   │   └── StockRepository.java
│   └── persistence
│       └── JpaStockRepository.java
└── payment
    ├── PaymentManagement.java
    └── internal
        └── PaymentManagementImpl.java
~~~

Các module cùng nằm dưới package gốc nên component scan mặc định có thể tìm bean ở các package con. Trong từng module:

- API được đặt tại base package.
- Service triển khai, repository và adapter đặt trong package con.
- Bean nội bộ vẫn có thể được Spring quản lý.
- Module khác chỉ tham chiếu kiểu API được công bố.

Không cần tách mỗi module thành một Spring application context riêng để có ranh giới Modulith. Một modular monolith thường sử dụng cùng một application context, trong khi Spring Modulith giúp quản lý dependency logic giữa các module.

## 12. Kiểm chứng dependency và bean registration

Có thể dùng `ApplicationModules.verify()` để kiểm tra quy tắc dependency của các module:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Kiểm tra này tập trung vào cấu trúc và dependency module. Nó giúp phát hiện các tham chiếu đi vào package nội bộ hoặc dependency không được cho phép.

Để xác nhận Spring thực sự tạo được các bean, có thể viết một context test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.acme.shop.inventory.InventoryManagement;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class InventoryBeanRegistrationTests {

    @Autowired
    InventoryManagement inventoryManagement;

    @Test
    void registersInventoryManagementBean() {
        assertThat(inventoryManagement).isNotNull();
    }
}
~~~

Test thứ nhất kiểm tra kiến trúc. Test thứ hai kiểm tra context và bean registration. Một ứng dụng có thể vượt qua kiểm tra kiến trúc nhưng vẫn thiếu bean do component scan sai; ngược lại, context có thể khởi động thành công nhưng dependency giữa các module vẫn vi phạm quy ước.

## 13. Chẩn đoán khi Spring không inject được bean

Khi gặp lỗi `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException`, hãy kiểm tra theo trình tự:

1. **Kiểm tra package của lớp ứng dụng.** Component scan mặc định có bắt đầu từ package cha chung của các module không?
2. **Kiểm tra stereotype hoặc phương thức đăng ký.** Class có `@Component`, `@Service`, `@Repository` phù hợp không? Hoặc bean có được khai báo bằng `@Bean`/`@Import` không?
3. **Kiểm tra phạm vi scan.** `basePackages`, `scanBasePackages`, include filter và exclude filter có bao phủ component không?
4. **Kiểm tra kiểu inject.** Có bean nào cung cấp đúng kiểu hoặc một implementation tương thích không?
5. **Kiểm tra nhiều candidate.** Nếu có nhiều bean cùng kiểu, cần xác định candidate bằng `@Primary`, `@Qualifier` hoặc thiết kế lại cấu hình.
6. **Kiểm tra điều kiện đăng ký.** Bean có bị điều kiện profile, property hoặc conditional annotation loại khỏi context không?
7. **Kiểm tra ranh giới module.** Nếu bean đã tồn tại, dependency của module tiêu thụ có đi qua API được công bố và được phép không?

Lỗi bean registration và lỗi module verification là hai nhóm lỗi khác nhau. Hãy xác định nhóm lỗi trước để chọn công cụ kiểm tra phù hợp.

## 14. Những nhầm lẫn thường gặp

**Cho rằng component scan tạo application module.** Module được nhận diện từ cấu trúc package và metadata Modulith. Component scan chỉ tìm component để đăng ký bean.

**Cho rằng bean trong package `internal` không được Spring quản lý.** Package nội bộ vẫn có thể được scan và tạo bean. Quy ước internal giới hạn dependency kiến trúc từ module khác.

**Cho rằng bean đã được inject thì dependency chắc chắn hợp lệ.** Spring có thể kết nối bean thành công dù dependency đi vào package nội bộ. Cần chạy kiểm tra kiến trúc để phát hiện vi phạm.

**Cho rằng module khác cần scan package implementation để inject interface.** Spring container cần đăng ký implementation bean trong context; module tiêu thụ chỉ cần tham chiếu API interface. Component scan ở cấp ứng dụng có thể tìm implementation mà không yêu cầu module tiêu thụ import class đó.

**Đặt lớp `@SpringBootApplication` trong package con quá sâu.** Scan mặc định có thể bỏ sót các module anh em. Hãy đặt lớp ứng dụng ở package gốc hoặc khai báo rõ `scanBasePackages`.

**Cho rằng mọi bean đều đến từ component scan.** `@Bean`, `@Import`, auto-configuration và các cơ chế registrar cũng có thể đăng ký bean.

**Dùng `@ComponentScan` để cho phép dependency liên module.** Quyền phụ thuộc được quản lý bằng API module, named interface và cấu hình dependency; scan không thay thế các quy tắc này.

## 15. Checklist thiết kế Spring bean trong modular monolith

- [ ] Đặt lớp `@SpringBootApplication` ở package gốc chung của ứng dụng nếu có thể.
- [ ] Xác nhận component scan bao phủ các module cần chạy.
- [ ] Đặt stereotype annotation hoặc khai báo `@Bean` cho các component cần đăng ký.
- [ ] Giữ bean implementation và repository trong package nội bộ của module sở hữu.
- [ ] Công bố interface hoặc hợp đồng cần dùng tại base package hoặc named interface.
- [ ] Dùng constructor injection để thể hiện dependency rõ ràng.
- [ ] Tránh inject implementation nội bộ từ module khác.
- [ ] Rà soát `@ComponentScan`, `scanBasePackages`, filter và `@Import` khi bean không được tìm thấy.
- [ ] Chạy `ApplicationModules.verify()` để kiểm tra dependency kiến trúc.
- [ ] Dùng Spring context test để xác nhận bean được đăng ký và inject thành công.

## 16. Kết luận

Spring component scan và Spring Modulith application module model phối hợp nhưng có trách nhiệm riêng. Component scan cùng các cơ chế như `@Bean` và `@Import` quyết định bean nào được đăng ký trong Spring context. Mô hình Modulith nhận diện module từ package, phân tích dependency giữa các thành phần và kiểm tra việc truy cập API.

Hãy đặt lớp ứng dụng tại package gốc để component scan mặc định bao phủ các module. Dùng constructor injection để thể hiện dependency và cho module tiêu thụ tham chiếu interface công khai của module cung cấp. Bean implementation vẫn có thể nằm trong package nội bộ và được Spring quản lý. Cuối cùng, kết hợp `ApplicationModules.verify()` với Spring context test để kiểm tra cả ranh giới kiến trúc lẫn khả năng khởi tạo bean thực tế.

## Tài liệu tham khảo

- [Spring Boot — Using the `@SpringBootApplication` Annotation](https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html)
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
