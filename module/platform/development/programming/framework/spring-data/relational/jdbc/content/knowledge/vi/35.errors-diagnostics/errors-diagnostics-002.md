# Không tìm thấy repository, quét sai package hoặc trùng bean

Spring Data JDBC tạo repository bean từ các interface kế thừa CrudRepository, ListCrudRepository hoặc Repository. Nếu ứng dụng không tìm thấy repository, báo NoSuchBeanDefinitionException, hoặc khởi động với lỗi trùng bean, nguyên nhân thường nằm ở cấu hình quét package, việc đăng ký repository nhiều lần hoặc tên bean bị xung đột.

Cần phân biệt hai cơ chế thường bị nhầm:

- **Component scanning** tìm các bean thông thường như @Component, @Service, @Controller và @Configuration.
- **Repository scanning** tìm interface repository và tạo proxy bean thông qua Spring Data repository infrastructure.

Một repository interface không trở thành bean chỉ vì package của nó nằm dưới @SpringBootApplication hoặc vì interface được đánh dấu @Repository. Spring Data phải quét interface đó bằng repository registrar.

Bài này hướng dẫn cách xác định repository nào chưa được đăng ký, cấu hình đúng package scan, xử lý nhiều DataSource và tránh trùng tên bean.

## 1. Spring Data JDBC đăng ký repository như thế nào?

Ví dụ repository:

~~~java
package com.example.orders.persistence;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Spring Data không tạo implementation class do lập trình viên viết. Khi repository scanning tìm thấy interface, infrastructure tạo proxy bean để xử lý các phương thức CRUD, derived query và query method đã khai báo.

Với Spring Boot, auto-configuration thường tìm repository trong package gốc của application configuration và các package con. Nếu cần chỉ định rõ phạm vi, có thể dùng @EnableJdbcRepositories.

Luồng khởi tạo khái quát:

~~~mermaid
flowchart TD
    A[Spring Boot khởi động] --> B[Repository auto-configuration]
    B --> C[Xác định base package]
    C --> D[Quét repository interfaces]
    D --> E[Đăng ký RepositoryFactoryBean]
    E --> F[Tạo repository proxy]
    F --> G[Inject vào service]
~~~

Nếu interface không nằm trong phạm vi quét, proxy bean không được tạo. Service inject repository sau đó sẽ thất bại với lỗi không tìm thấy bean.

## 2. Component scan và repository scan là hai việc riêng

Ví dụ cấu trúc package:

~~~text
com.example
  Application.java
  orders
    application/
      OrderService.java
    domain/
      PurchaseOrder.java
    persistence/
      PurchaseOrderRepository.java
  customers
    application/
      CustomerService.java
    persistence/
      CustomerRepository.java
~~~

Nếu Application.java nằm ở package com.example, Spring Boot thường quét component và repository trong các package con. Đây là cách tổ chức dễ dự đoán.

Cấu hình application:

~~~java
package com.example;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.SpringApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Nếu main class đặt quá sâu:

~~~text
com.example.bootstrap
  Application.java
com.example.orders.persistence
  PurchaseOrderRepository.java
~~~

package com.example.orders.persistence không phải package con của com.example.bootstrap. Repository có thể nằm ngoài phạm vi auto-configuration package mặc định.

Việc thêm @ComponentScan hoặc scanBasePackages có thể làm các @Service và @Configuration được tìm thấy, nhưng không nên mặc định rằng nó đã cấu hình repository scanning. Repository scan có base package và registrar riêng. Hãy cấu hình @EnableJdbcRepositories hoặc đặt application configuration tại package gốc phù hợp.

## 3. Cấu hình repository scan tường minh

Có thể dùng @EnableJdbcRepositories để chỉ rõ package chứa repository:

~~~java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration
@EnableJdbcRepositories(
        basePackages = "com.example.orders.persistence"
)
public class OrdersJdbcRepositoryConfiguration {
}
~~~

Hoặc dùng basePackageClasses để tránh hard-code tên package dạng String:

~~~java
@Configuration
@EnableJdbcRepositories(
        basePackageClasses = PurchaseOrderRepository.class
)
public class OrdersJdbcRepositoryConfiguration {
}
~~~

basePackageClasses lấy package của class được chỉ định làm điểm bắt đầu quét. Đây thường là lựa chọn an toàn khi refactor package vì compiler có thể phát hiện class marker bị đổi.

Khi có nhiều package repository, khai báo nhiều base package:

~~~java
@EnableJdbcRepositories(
        basePackages = {
                "com.example.orders.persistence",
                "com.example.customers.persistence"
        }
)
~~~

Chỉ cấu hình repository scan ở nơi cần thiết. Nếu Spring Boot auto-configuration đã quét đúng package, thêm một @EnableJdbcRepositories khác có thể làm repository được đăng ký lặp hoặc khiến phạm vi quét khó hiểu.

## 4. Vì sao @Repository trên interface không sửa được lỗi scan?

Spring Data repository interface thường không cần gắn @Repository:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Annotation @Repository là stereotype cho component scanning và exception translation đối với các bean repository được khai báo theo cách thông thường. Nhưng một interface thuần không có implementation không thể được tạo thành bean chỉ bằng component scan.

Spring Data repository registrar phải phát hiện interface và tạo proxy. Vì vậy, khi repository không được tìm thấy, hãy kiểm tra @EnableJdbcRepositories hoặc auto-configuration package trước khi thêm @Repository.

Cũng cần phân biệt:

- @Repository trên một class DAO do ứng dụng tự viết có thể đăng ký class đó qua component scan.
- Interface Spring Data kế thừa CrudRepository cần Spring Data repository scanning để tạo implementation proxy.
- @Repository không thay thế @EnableJdbcRepositories và không sửa một base package sai.

## 5. Các lỗi thường gặp và ý nghĩa

| Lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| NoSuchBeanDefinitionException cho PurchaseOrderRepository | Không có bean với kiểu/tên được yêu cầu | Repository scan, package, profile và test slice |
| No qualifying bean of type PurchaseOrderRepository | Không tìm thấy bean phù hợp để inject | Kiểm tra repository proxy đã được đăng ký chưa |
| UnsatisfiedDependencyException ở service | Bean service không thể được tạo do dependency repository thiếu hoặc lỗi khởi tạo | Đọc nguyên nhân sâu nhất trong stack trace |
| BeanDefinitionOverrideException | Hai bean dùng cùng tên trong khi bean overriding bị tắt | Tìm cấu hình scan trùng hoặc repository cùng tên |
| ConflictingBeanDefinitionException | Hai bean definition xung đột khi đăng ký | Kiểm tra component/repository cùng tên |
| Ambiguous dependency / NoUniqueBeanDefinitionException | Có nhiều bean phù hợp với một injection point | Dùng qualifier hoặc phân định cấu hình |
| Failed to configure a DataSource | Lỗi DataSource/configuration xảy ra trước repository | Kiểm tra JDBC URL, driver, credentials và profile |

Đừng dừng ở dòng UnsatisfiedDependencyException đầu tiên. Đọc chuỗi caused by đến exception gốc; lỗi repository scan và lỗi kết nối database có thể xuất hiện ở các tầng khác nhau.

## 6. Kiểm tra package của application class

Spring Boot thường dùng package của class có @SpringBootApplication làm package gốc cho auto-configuration. Cấu trúc khuyến nghị:

~~~text
com.example
  Application.java
  config/
  orders/
    domain/
    application/
    persistence/
  customers/
    domain/
    application/
    persistence/
~~~

Đặt Application ở package cha chung giúp component scan và repository auto-configuration có phạm vi nhất quán.

Tránh đặt main class trong package quá sâu như:

~~~text
com.example.orders.application
  Application.java
~~~

nếu repository hoặc service nằm ở package ngang hàng khác như com.example.customers. Package ngang hàng không phải package con của application package.

Nếu không thể thay đổi package main class, dùng cấu hình rõ ràng:

~~~java
@SpringBootApplication
public class Application {
    // ...
}

@Configuration
@EnableJdbcRepositories(
        basePackageClasses = {
                PurchaseOrderRepository.class,
                CustomerRepository.class
        }
)
class JdbcRepositoriesConfiguration {
}
~~~

Nếu component/service cũng nằm ngoài phạm vi component scan, cấu hình component scan riêng. Không gộp hai cơ chế thành một giả định.

## 7. Phát hiện repository scan bị cấu hình hai lần

Một nguyên nhân phổ biến của lỗi trùng bean là ứng dụng vừa dùng auto-configuration của Spring Boot, vừa khai báo nhiều @EnableJdbcRepositories có phạm vi chồng lấn.

Ví dụ:

~~~java
@SpringBootApplication
public class Application {
}
~~~

và:

~~~java
@Configuration
@EnableJdbcRepositories(
        basePackages = "com.example"
)
public class JdbcRepositoryConfiguration {
}
~~~

Nếu auto-configuration đã quét com.example, cấu hình tường minh trên có thể quét lại cùng các repository.

Cách xử lý:

1. Xác định repository scanning đang đến từ auto-configuration hay @EnableJdbcRepositories.
2. Kiểm tra tất cả configuration class có annotation @EnableJdbcRepositories.
3. Xác định phạm vi basePackages/basePackageClasses của từng cấu hình.
4. Giữ một cấu hình rõ ràng cho mỗi nhóm repository và mỗi DataSource.
5. Tránh cấu hình phạm vi rộng hơn cần thiết.
6. Không bật bean overriding chỉ để che lỗi đăng ký trùng.

Nếu cần nhiều repository configuration vì nhiều database, hãy chia package riêng và gắn mỗi cấu hình với đúng JDBC operations và transaction manager.

## 8. Trùng tên repository bean ở các package khác nhau

Tên bean mặc định của repository thường được suy ra từ tên interface. Hai interface cùng simple name ở package khác nhau có thể tạo bean name giống nhau.

Ví dụ:

~~~text
com.example.billing.persistence.CustomerRepository
com.example.support.persistence.CustomerRepository
~~~

Cả hai có thể muốn đăng ký bean tên customerRepository. Khi cùng nằm trong một application context, tên bean có thể xung đột.

Giải pháp dễ bảo trì nhất là đặt tên interface thể hiện domain:

~~~java
public interface BillingCustomerRepository
        extends CrudRepository<BillingCustomer, Long> {
}

public interface SupportCustomerRepository
        extends CrudRepository<SupportCustomer, Long> {
}
~~~

Tên rõ ràng giúp bean name dễ phân biệt và code gọi repository cũng thể hiện đúng bounded context.

Nếu hai repository có domain type khác nhau nhưng cùng tên interface do lịch sử codebase, cân nhắc đổi tên interface. Đừng dựa vào bean overriding để một repository âm thầm thay thế repository kia.

## 9. Trùng bean giữa repository và DAO tự viết

Ứng dụng có thể vô tình khai báo một DAO class có tên bean trùng repository:

~~~java
@Repository
public class PurchaseOrderRepository {
    // DAO implementation do ứng dụng tự viết.
}
~~~

và đồng thời có Spring Data interface:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Ngoài việc không thể cùng tồn tại hai class/interface có cùng fully qualified name trong một package, các kiểu cùng simple name ở package khác nhau vẫn có thể tạo bean name xung đột.

Đặt tên DAO theo vai trò cụ thể:

- PurchaseOrderJdbcDao.
- PurchaseOrderReadDao.
- PurchaseOrderSearchMapper.
- PurchaseOrderLegacyGateway.

Dành hậu tố Repository cho abstraction repository có contract rõ ràng. Đừng đặt mọi class truy cập database tên Repository vì làm giảm khả năng phân biệt ownership.

## 10. Bean tồn tại nhưng injection bị mơ hồ

Có thể repository đã được đăng ký, nhưng injection vẫn thất bại vì có nhiều bean cùng phù hợp với kiểu được yêu cầu.

Ví dụ một service phụ thuộc vào abstraction rộng:

~~~java
public class ExportService {
    private final CrudRepository<?, ?> repository;
}
~~~

Nếu context có nhiều repository bean phù hợp, Spring không biết chọn bean nào.

Hãy inject interface cụ thể:

~~~java
@Service
public class OrderExportService {
    private final PurchaseOrderRepository orders;

    public OrderExportService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }
}
~~~

Nếu có nhiều bean cùng kiểu do cấu hình riêng, dùng @Qualifier:

~~~java
@Service
public class ReportingService {
    private final NamedParameterJdbcOperations reportingJdbc;

    public ReportingService(
            @Qualifier("reportingJdbcOperations")
            NamedParameterJdbcOperations reportingJdbc
    ) {
        this.reportingJdbc = reportingJdbc;
    }
}
~~~

@Primary có thể đánh dấu một bean mặc định khi nhiều bean cùng kiểu, nhưng chỉ dùng nếu có lựa chọn mặc định hợp lý. Với nhiều repository/domain hoặc nhiều database, @Qualifier thường diễn đạt ý định rõ hơn.

## 11. Ứng dụng có nhiều DataSource

Khi một ứng dụng dùng nhiều database, mỗi nhóm repository phải gắn với đúng JDBC operations và transaction manager.

Ví dụ package:

~~~text
com.example
  Application.java
  orders/
    persistence/
      OrderRepository.java
  reporting/
    persistence/
      ReportRepository.java
  config/
    OrdersDatabaseConfiguration.java
    ReportingDatabaseConfiguration.java
~~~

Cấu hình repository cho database đơn hàng:

~~~java
@Configuration
@EnableJdbcRepositories(
        basePackageClasses = OrderRepository.class,
        jdbcOperationsRef = "ordersJdbcOperations",
        transactionManagerRef = "ordersTransactionManager"
)
public class OrdersDatabaseConfiguration {
}
~~~

Cấu hình cho database báo cáo:

~~~java
@Configuration
@EnableJdbcRepositories(
        basePackageClasses = ReportRepository.class,
        jdbcOperationsRef = "reportingJdbcOperations",
        transactionManagerRef = "reportingTransactionManager"
)
public class ReportingDatabaseConfiguration {
}
~~~

Các bean được tham chiếu phải tồn tại và được cấu hình nhất quán:

- DataSource cho từng database.
- NamedParameterJdbcOperations tương ứng.
- TransactionManager tương ứng.
- MappingContext/DataAccessStrategy phù hợp khi cấu hình nhiều JDBC repository context.
- Migration/schema cho từng database.

Tên bean trong ví dụ là tên minh họa; phải khớp tên bean thực tế. Không trỏ repository của database A tới JDBC operations hoặc transaction manager của database B.

Khi có nhiều DataSource, cần đặc biệt cẩn thận với auto-configuration mặc định. Hãy xác định rõ bean nào là primary nếu ứng dụng cần một default, và cấu hình repository group tường minh cho từng nguồn dữ liệu.

## 12. Test slice không quét repository như application đầy đủ

Một test dùng @DataJdbcTest có thể chỉ nạp một phần ApplicationContext. Nếu test class nằm trong package không liên quan tới package gốc của ứng dụng, hoặc cấu hình repository nằm ngoài phạm vi được phát hiện, repository bean có thể không xuất hiện.

Ví dụ:

~~~java
@DataJdbcTest
class PurchaseOrderRepositoryTest {
    @Autowired
    PurchaseOrderRepository repository;
}
~~~

Nếu repository không được tìm thấy, kiểm tra:

- Test class có nằm trong package phù hợp với application configuration không?
- Có @EnableJdbcRepositories tùy chỉnh cần import không?
- Cấu hình DataSource và mapping có được đưa vào test slice không?
- Có dùng @Import cho configuration bean/converter tùy chỉnh không?
- Có vô tình exclude repository auto-configuration không?

Có thể import cấu hình cần thiết:

~~~java
@DataJdbcTest
@Import(JdbcRepositoriesConfiguration.class)
class PurchaseOrderRepositoryTest {
}
~~~

Chỉ import cấu hình thực sự cần thiết. Không biến slice test thành full application context bằng cách thêm hàng loạt @ComponentScan nếu mục tiêu là kiểm tra repository isolation.

## 13. Phân biệt lỗi scan với lỗi khởi tạo repository

Repository có thể được tìm thấy nhưng không khởi tạo được do lỗi khác:

- Domain entity không ánh xạ được.
- Derived query method không phân tích được property path.
- Query annotation sai cú pháp hoặc tham số không khớp.
- MappingContext thiếu converter.
- DataSource không kết nối được.
- JDBC operations hoặc transaction manager không phù hợp.
- Hai repository configuration cùng dùng một bean name.

Vì vậy, thông báo lỗi “repository bean không tạo được” không luôn có nghĩa package scan sai. Hãy xác định exception gốc:

| Exception gốc | Hướng điều tra |
|---|---|
| NoSuchBeanDefinitionException | Scan phạm vi hoặc bean reference |
| BeanDefinitionOverrideException | Bean name trùng |
| NoUniqueBeanDefinitionException | Nhiều bean cùng kiểu |
| PropertyReferenceException | Derived query dùng property không tồn tại |
| QueryCreationException | Repository query không hợp lệ |
| DataAccessResourceFailureException | Database/connection |
| MappingException hoặc ConversionFailedException | Entity metadata/converter |

Đọc toàn bộ stack trace và xem bean nào đang được tạo tại thời điểm lỗi.

## 14. Kiểm tra repository bean ở runtime

Trong môi trường phát triển, có thể kiểm tra bean definitions của ApplicationContext:

~~~java
@Component
public class RepositoryBeanDiagnostics implements ApplicationRunner {

    private final ApplicationContext context;

    public RepositoryBeanDiagnostics(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        String[] names = context.getBeanNamesForType(
                PurchaseOrderRepository.class
        );

        System.out.println(
                "PurchaseOrderRepository beans: "
                        + Arrays.toString(names)
        );
    }
}
~~~

Đây là công cụ chẩn đoán tạm thời; không cần giữ class này trong production nếu không có nhu cầu vận hành.

Có thể dùng Actuator beans endpoint trong môi trường được bảo vệ để xem bean name và dependency. Endpoint này có thể chứa thông tin cấu hình nội bộ, vì vậy không mở công khai.

Bật log ở mức DEBUG cho package repository configuration của Spring Data có thể giúp thấy repository scanner đang quét package nào và đăng ký interface nào. Tên logger cụ thể có thể thay đổi theo phiên bản; bắt đầu với org.springframework.data.repository.config và org.springframework.data.jdbc.repository.config.

## 15. Quy trình chẩn đoán theo thứ tự

Khi service không inject được repository, làm theo trình tự:

1. Đọc exception gốc ở cuối stack trace.
2. Xác nhận repository interface kế thừa Repository/CrudRepository đúng kiểu.
3. Tìm package của Application class và package repository.
4. Xác định auto-configuration package mà Spring Boot đang dùng.
5. Tìm mọi @EnableJdbcRepositories trong project.
6. Kiểm tra basePackages và basePackageClasses.
7. Kiểm tra có cấu hình nhiều DataSource hay không.
8. Xem log repository scanner để biết interface có được phát hiện.
9. Nếu interface đã được phát hiện, kiểm tra lỗi query parsing, mapping, DataSource và converter.
10. Nếu bean đã tồn tại nhưng injection mơ hồ, kiểm tra bean type/name và dùng @Qualifier hoặc đổi tên repository.
11. Chạy context test nhỏ để tái hiện lỗi.
12. Xóa cấu hình scan trùng hoặc package scan quá rộng sau khi xác định nguyên nhân.

Không nên thêm @ComponentScan rộng toàn bộ root package trước khi biết repository registrar đang quét ở đâu. Cấu hình quá rộng có thể làm phát sinh bean trùng và khiến lỗi ban đầu khó xác định hơn.

## 16. Các lỗi cấu hình thường gặp

| Cấu hình/vấn đề | Hậu quả | Cách xử lý |
|---|---|---|
| Main class đặt trong package quá sâu | Repository ở package ngang hàng không được quét | Đặt main class ở package gốc hoặc cấu hình basePackageClasses |
| Chỉ thêm @Repository lên interface | Repository proxy vẫn không được tạo | Cấu hình Spring Data repository scan |
| Component scan đúng nhưng repository scan sai | Service có mặt nhưng repository thiếu | Kiểm tra @EnableJdbcRepositories/auto-configuration package |
| @EnableJdbcRepositories chồng phạm vi auto-config | Repository có thể đăng ký lặp | Chọn một cơ chế scan rõ ràng |
| Hai interface cùng simple name | Bean name có thể trùng | Đổi tên interface theo domain |
| Repository của hai database dùng chung config | Repository kết nối sai DataSource hoặc transaction manager | Tách package và cấu hình repository group |
| Inject abstraction quá rộng | Nhiều repository phù hợp | Inject interface cụ thể hoặc qualifier |
| Test slice không import config | Repository/converter tùy chỉnh không có trong context | Import cấu hình tối thiểu cần thiết |
| Dùng bean overriding để xử lý trùng | Một bean có thể che bean còn lại | Sửa nguồn đăng ký và bean naming |
| Query method sai property | Repository được scan nhưng khởi tạo thất bại | Sửa derived query hoặc @Query |

## 17. Checklist cấu hình package và bean

Trước khi hoàn tất cấu hình, xác nhận:

- Application class nằm ở package cha chung hoặc có cấu hình scan rõ.
- Repository interface kế thừa đúng Spring Data Repository abstraction.
- Repository package nằm trong base package được quét.
- Component scan và repository scan được hiểu là hai cơ chế riêng.
- Không có nhiều @EnableJdbcRepositories cấu hình chồng lấn ngoài chủ đích.
- Tên repository interface không trùng simple name trong các domain package khác nhau.
- Không có DAO @Repository class trùng bean name với repository proxy.
- Injection dùng kiểu cụ thể, không dùng CrudRepository quá rộng nếu context có nhiều repository.
- Mỗi repository group dùng đúng DataSource, JDBC operations và transaction manager.
- Test slice import các cấu hình cần thiết mà không quét toàn ứng dụng không cần thiết.
- Log và Actuator diagnostics được dùng có kiểm soát.

## 18. Ví dụ cấu hình hoàn chỉnh cho một database

Một cấu trúc đơn giản có thể dùng auto-configuration mặc định:

~~~text
com.example
  Application.java
  orders/
    domain/
      PurchaseOrder.java
    application/
      PurchaseOrderService.java
    persistence/
      PurchaseOrderRepository.java
  customers/
    domain/
      Customer.java
    application/
      CustomerService.java
    persistence/
      CustomerRepository.java
~~~

Application:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Repository:

~~~java
package com.example.orders.persistence;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Service:

~~~java
package com.example.orders.application;

import com.example.orders.domain.PurchaseOrder;
import com.example.orders.persistence.PurchaseOrderRepository;
import org.springframework.stereotype.Service;

@Service
public class PurchaseOrderService {
    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }
}
~~~

Với package root com.example, Spring Boot có thể tự cấu hình component và repository scanning cho các package con. Không cần thêm @EnableJdbcRepositories nếu auto-configuration đã đáp ứng đúng phạm vi.

Nếu repository nằm ngoài com.example, hãy thêm cấu hình repository scan tường minh thay vì giả định Spring sẽ tự tìm toàn bộ classpath.

## 19. Nguyên tắc ghi nhớ

- Spring Data JDBC tạo proxy bean từ repository interface qua repository scanning.
- Component scanning và repository scanning là hai cơ chế riêng.
- @Repository trên interface không thay thế @EnableJdbcRepositories.
- Package của @SpringBootApplication ảnh hưởng package mặc định mà Spring Boot dùng cho auto-configuration.
- Dùng @EnableJdbcRepositories với basePackageClasses hoặc basePackages khi cần chỉ định phạm vi rõ ràng.
- Tránh cấu hình repository scanning chồng lấn với auto-configuration nếu không có lý do.
- Hai repository interface cùng simple name có thể tạo bean name xung đột; đặt tên theo domain.
- Dùng @Qualifier khi có nhiều bean phù hợp và @Primary chỉ khi có default hợp lý.
- Với nhiều DataSource, gắn từng repository group với đúng jdbcOperationsRef và transactionManagerRef.
- Test slice có thể cần import cấu hình repository hoặc converter tùy chỉnh.
- Đọc exception gốc để phân biệt lỗi scan, trùng bean, query parsing, mapping và kết nối database.
- Không bật bean overriding để che xung đột; sửa nguồn đăng ký và ownership của bean.

Khi repository không được tìm thấy hoặc bean bị trùng, hãy xác định cơ chế nào chịu trách nhiệm đăng ký nó. Đặt application class ở package gốc hợp lý, cấu hình repository scan tường minh khi cần và phân chia rõ từng repository group nếu có nhiều database. Tên bean và injection point nên thể hiện domain cụ thể để Spring tạo đúng proxy và ứng dụng không phải dựa vào bean overriding hoặc cấu hình scan quá rộng.

