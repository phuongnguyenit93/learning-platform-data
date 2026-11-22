# Nhiều DataSource: tách repository, template và transaction manager

Một ứng dụng dùng **Spring Data Relational JDBC** có thể làm việc với nhiều database hoặc nhiều nguồn dữ liệu. Ví dụ, đơn hàng nằm trong database orders, tồn kho nằm trong database inventory, còn dữ liệu báo cáo được đọc từ một nguồn riêng. Khi đó, mỗi nhóm repository phải sử dụng đúng `DataSource`, JDBC operations và transaction manager tương ứng.

Điểm quan trọng là **một repository không tự chọn database chỉ dựa vào kiểu aggregate**. Cấu hình repository cần được gắn với nhóm bean persistence phù hợp. Khi ứng dụng inject `JdbcAggregateTemplate` trực tiếp, template cũng phải được tạo từ hạ tầng của đúng nguồn dữ liệu. Khi có nhiều transaction manager, service cần chỉ rõ manager mà transaction của nó sử dụng.

Bài học này trình bày cách tách package repository, cấu hình nhiều `DataSource`, `NamedParameterJdbcOperations`, transaction manager và aggregate template, cách chọn manager trong `@Transactional`, cùng giới hạn khi một use case ghi vào nhiều database.

## 1. Khi nào một ứng dụng cần nhiều DataSource?

Một ứng dụng có thể kết nối nhiều nguồn dữ liệu vì các lý do như:

- Các bounded context dùng database riêng, chẳng hạn đơn hàng và kho.
- Một database phục vụ giao dịch, database khác phục vụ báo cáo.
- Ứng dụng cần đọc dữ liệu từ hệ thống cũ trong khi ghi dữ liệu mới vào database mới.
- Các tenant được phân vùng vào những database khác nhau.
- Một số bảng được quản lý bởi một database hoặc schema riêng.

Ví dụ kiến trúc:

~~~text
OrderApplicationService
    |
    +--> PurchaseOrderRepository
    |       |
    |       +--> ordersDataSource
    |               |
    |               +--> ordersTransactionManager
    |
    +--> InventoryRepository
            |
            +--> inventoryDataSource
                    |
                    +--> inventoryTransactionManager
~~~

Mỗi repository được cấu hình để sử dụng đúng JDBC operations và transaction manager. Nếu cấu hình không rõ ràng, Spring có thể không biết bean nào cần inject hoặc repository có thể truy cập nhầm database.

### 1.1. Phân biệt nhiều DataSource với nhiều schema

Hai schema trong cùng database không nhất thiết cần hai `DataSource`. Nếu cả hai nhóm repository có thể dùng cùng connection pool, cùng transaction manager và cùng cơ chế định tuyến schema, một DataSource có thể đủ.

Ngược lại, hai `DataSource` riêng thường đại diện cho hai resource kết nối riêng. Ngay cả khi hai bean có URL trỏ đến cùng một database server, hai connection pool khác nhau vẫn tạo ra hai resource transaction khác nhau.

Hãy bắt đầu từ ranh giới transaction và vận hành thực tế để quyết định có cần tách DataSource hay chỉ cần tách schema.

## 2. Những thành phần cần gắn với từng DataSource

Với Spring Data JDBC, một cấu hình nguồn dữ liệu thường có các thành phần:

| Thành phần | Vai trò |
|---|---|
| `DataSource` | Cung cấp JDBC connections tới database |
| `NamedParameterJdbcOperations` | Thực thi SQL với named parameter |
| `PlatformTransactionManager` | Quản lý transaction trên resource tương ứng |
| `JdbcMappingContext` | Chứa metadata mapping relational |
| `JdbcConverter` | Chuyển đổi giá trị giữa domain và JDBC |
| `DataAccessStrategy` | Thực hiện thao tác đọc/ghi aggregate |
| `JdbcAggregateTemplate` | API thao tác aggregate trực tiếp |
| Repository | API persistence theo aggregate root |

Ba bean đầu tiên cần được phân biệt rõ khi có nhiều nguồn dữ liệu. Các thành phần mapping và aggregate operations cũng phải tương thích với DataSource, dialect và cấu hình mapping mà chúng sử dụng.

Trong trường hợp hai database dùng cùng schema, cùng dialect và cùng domain mapping, một số metadata có thể dùng chung tùy cách cấu hình. Nếu dialect, naming strategy, custom conversions hoặc mapping khác nhau, cần tách infrastructure tương ứng. Không nên dùng một `DataAccessStrategy` được tạo cho database A để thao tác trên database B.

## 3. Tách package repository theo nguồn dữ liệu

Một cách tổ chức dễ hiểu là đặt repository của từng database trong package riêng:

~~~text
com.example
├── orders
│   ├── domain
│   └── repository
│       └── PurchaseOrderRepository.java
├── inventory
│   ├── domain
│   └── repository
│       └── InventoryRepository.java
└── config
    ├── OrdersJdbcConfiguration.java
    └── InventoryJdbcConfiguration.java
~~~

Package riêng giúp mỗi cấu hình `@EnableJdbcRepositories` quét đúng nhóm repository. Không để hai cấu hình cùng quét một package repository, vì một repository interface có thể bị đăng ký nhiều lần với các infrastructure khác nhau.

Ví dụ repository:

~~~java
package com.example.orders.repository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

~~~java
package com.example.inventory.repository;

public interface InventoryRepository
        extends CrudRepository<InventoryItem, Long> {
}
~~~

Hai repository có thể cùng kế thừa `CrudRepository`, nhưng sẽ được gắn vào các cấu hình nguồn dữ liệu khác nhau.

## 4. Khai báo hai DataSource

Ví dụ dùng Spring Boot và `DataSourceBuilder` để tạo hai bean riêng:

~~~java
import javax.sql.DataSource;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.jdbc.DataSourceBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DataSourceConfiguration {

    @Bean
    @ConfigurationProperties("app.datasource.orders")
    DataSource ordersDataSource() {
        return DataSourceBuilder.create().build();
    }

    @Bean
    @ConfigurationProperties("app.datasource.inventory")
    DataSource inventoryDataSource() {
        return DataSourceBuilder.create().build();
    }
}
~~~

Ví dụ cấu hình properties:

~~~yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders_db
      username: orders_app
      password: ORDERS_DB_PASSWORD_FROM_SECRET_STORE
      driver-class-name: org.postgresql.Driver
    inventory:
      url: jdbc:postgresql://localhost:5432/inventory_db
      username: inventory_app
      password: INVENTORY_DB_PASSWORD_FROM_SECRET_STORE
      driver-class-name: org.postgresql.Driver
~~~

Tên prefix và cách bind phụ thuộc cấu hình ứng dụng. Nếu dùng HikariCP hoặc một pool cụ thể, có thể khai báo bean theo kiểu pool đó để cấu hình pool size, timeout và các thuộc tính kết nối.

Không đặt credential thật trực tiếp trong file cấu hình được commit. Dùng environment variables hoặc secret management của môi trường triển khai.

## 5. Tạo JDBC operations và transaction manager riêng

Mỗi DataSource cần một `NamedParameterJdbcOperations` và một transaction manager gắn với chính DataSource đó:

~~~java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class JdbcResourceConfiguration {

    @Bean
    NamedParameterJdbcOperations ordersJdbcOperations(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new NamedParameterJdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    NamedParameterJdbcOperations inventoryJdbcOperations(
            @Qualifier("inventoryDataSource") DataSource dataSource) {
        return new NamedParameterJdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager inventoryTransactionManager(
            @Qualifier("inventoryDataSource") DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

`JdbcTransactionManager` có trong Spring Framework từ dòng phiên bản hỗ trợ class này; với phiên bản cũ hơn, có thể dùng `DataSourceTransactionManager`. Cả hai đều là JDBC transaction manager, nhưng hãy dùng API có trong dependency của dự án.

Điều quan trọng là cặp bean phải cùng trỏ đến một DataSource:

- `ordersJdbcOperations` dùng `ordersDataSource`.
- `ordersTransactionManager` dùng `ordersDataSource`.
- `inventoryJdbcOperations` dùng `inventoryDataSource`.
- `inventoryTransactionManager` dùng `inventoryDataSource`.

Không gắn transaction manager của orders với JDBC operations của inventory. Khi đó transaction có thể không bao phủ câu SQL mà ứng dụng nghĩ rằng nó đang quản lý.

## 6. Gắn repository với đúng JDBC operations và transaction manager

`@EnableJdbcRepositories` cho phép chỉ định package repository, bean JDBC operations và transaction manager:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration
@EnableJdbcRepositories(
    basePackages = "com.example.orders.repository",
    jdbcOperationsRef = "ordersJdbcOperations",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersRepositoryConfiguration {
}
~~~

~~~java
@Configuration
@EnableJdbcRepositories(
    basePackages = "com.example.inventory.repository",
    jdbcOperationsRef = "inventoryJdbcOperations",
    transactionManagerRef = "inventoryTransactionManager"
)
public class InventoryRepositoryConfiguration {
}
~~~

Hai cấu hình tách repository scan và chỉ rõ hai bean cần dùng. Tên attribute và các tùy chọn infrastructure khác cần được kiểm tra theo phiên bản Spring Data JDBC của dự án; mẫu trên thể hiện cách gắn repository group vào JDBC operations và transaction manager tương ứng.

Nếu ứng dụng có cấu hình `AbstractJdbcConfiguration`, cần bảo đảm mapping context, converter, dialect và data access strategy được tạo nhất quán với từng nguồn dữ liệu. Không tạo nhiều cấu hình nền có cùng tên bean mặc định mà không kiểm soát bean naming và dependency injection.

## 7. Inject repository và transaction manager trong service

Sau khi repository được đăng ký theo package, service có thể inject chúng như các dependency thông thường:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;

    public OrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Long createOrder(CreateOrderCommand command) {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create(command)
        );
        return saved.getId();
    }
}
~~~

Service của inventory chọn transaction manager riêng:

~~~java
@Service
public class InventoryService {

    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    @Transactional(transactionManager = "inventoryTransactionManager")
    public void reserve(Long productId, int quantity) {
        InventoryItem item = inventory.findById(productId)
            .orElseThrow();

        item.reserve(quantity);
        inventory.save(item);
    }
}
~~~

Khi có nhiều transaction manager, nên chỉ rõ `transactionManager` trong `@Transactional`. Nếu bỏ qua thuộc tính này, Spring phải chọn manager mặc định, thường dựa trên bean primary hoặc tên mặc định. Dựa vào lựa chọn ngầm có thể khiến service chạy transaction trên sai DataSource.

### 7.1. Có thể dùng @Primary không?

Có thể đánh dấu một DataSource hoặc transaction manager là `@Primary` để làm lựa chọn mặc định khi có nhiều bean cùng kiểu. Điều đó hữu ích nếu phần lớn ứng dụng dùng một database chính.

Tuy nhiên, `@Primary` không thay thế việc chỉ rõ manager cho service thuộc nguồn dữ liệu còn lại. Các use case quan trọng nên nêu rõ resource mà transaction cần quản lý.

## 8. Sử dụng JdbcAggregateTemplate cho từng DataSource

`JdbcAggregateTemplate` là API persistence ở cấp aggregate. Khi ứng dụng có nhiều database và cần inject template trực tiếp, mỗi template phải gắn với infrastructure của database tương ứng.

Ví dụ service có thể nhận hai template được đặt tên rõ ràng:

~~~java
@Service
public class AggregateMaintenanceService {

    private final JdbcAggregateOperations ordersOperations;
    private final JdbcAggregateOperations inventoryOperations;

    public AggregateMaintenanceService(
            @Qualifier("ordersJdbcAggregateTemplate")
            JdbcAggregateOperations ordersOperations,
            @Qualifier("inventoryJdbcAggregateTemplate")
            JdbcAggregateOperations inventoryOperations) {
        this.ordersOperations = ordersOperations;
        this.inventoryOperations = inventoryOperations;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public PurchaseOrder insertOrder(PurchaseOrder order) {
        return ordersOperations.insert(order);
    }

    @Transactional(transactionManager = "inventoryTransactionManager")
    public InventoryItem insertInventoryItem(InventoryItem item) {
        return inventoryOperations.insert(item);
    }
}
~~~

Trong ví dụ, `JdbcAggregateOperations` là abstraction thao tác aggregate; bean implementation có thể là `JdbcAggregateTemplate`. Tên bean trong `@Qualifier` là tên do cấu hình ứng dụng đăng ký.

### 8.1. Template phải dùng đúng DataAccessStrategy

Không chỉ đặt tên hai bean template khác nhau. Mỗi template cần được tạo từ các thành phần persistence của đúng database:

~~~text
ordersJdbcAggregateTemplate
    ├── orders mapping/conversion configuration
    ├── orders DataAccessStrategy
    └── orders JDBC operations

inventoryJdbcAggregateTemplate
    ├── inventory mapping/conversion configuration
    ├── inventory DataAccessStrategy
    └── inventory JDBC operations
~~~

Nếu template của orders được tạo từ `DataAccessStrategy` của inventory, template có thể đọc hoặc ghi nhầm database dù service đã chọn `ordersTransactionManager`.

Constructor và cách tạo `JdbcAggregateTemplate` phụ thuộc phiên bản Spring Data JDBC cùng cách cấu hình infrastructure. Khi cần khai báo template tường minh, hãy dùng các bean `JdbcMappingContext`, `JdbcConverter` và `DataAccessStrategy` được cấu hình cho đúng DataSource; không lấy một template mặc định rồi gắn thêm transaction manager khác.

Một factory bean có thể thể hiện rõ các dependency được ghép cho database orders:

~~~java
@Bean("ordersJdbcAggregateTemplate")
JdbcAggregateOperations ordersJdbcAggregateTemplate(
        ApplicationContext applicationContext,
        @Qualifier("ordersJdbcMappingContext")
        JdbcMappingContext mappingContext,
        @Qualifier("ordersJdbcConverter")
        JdbcConverter converter,
        @Qualifier("ordersDataAccessStrategy")
        DataAccessStrategy dataAccessStrategy) {

    return new JdbcAggregateTemplate(
        applicationContext,
        mappingContext,
        converter,
        dataAccessStrategy
    );
}
~~~

Database inventory cần một factory tương tự nhưng nhận `inventoryJdbcMappingContext`, `inventoryJdbcConverter` và `inventoryDataAccessStrategy`. Các bean mapping context, converter và strategy đó phải được cấu hình riêng hoặc được chia sẻ có chủ đích khi metadata thực sự tương thích. Phần tạo `DataAccessStrategy` phụ thuộc dialect và API của phiên bản Spring Data JDBC đang dùng; đoạn code trên minh họa cách ghép template với đúng các bean đã được cấu hình, không thay thế toàn bộ cấu hình nền của framework.

### 8.2. Khi nào nên dùng repository thay vì inject template?

Nếu use case chỉ cần CRUD thông thường, repository đã được cấu hình theo database là đủ:

~~~java
orders.save(order);
inventory.save(item);
~~~

Chỉ inject `JdbcAggregateTemplate` khi cần thao tác aggregate trực tiếp như `insert`, `update`, `findById` theo kiểu domain hoặc khi xây dựng adapter hạ tầng tổng quát. Template không tự giải quyết việc chọn transaction manager; service vẫn cần chọn manager phù hợp.

## 9. Mapping context, converter và dialect

Khi có nhiều database, cần xem xét liệu chúng có dùng cùng mô hình relational hay không.

| Thành phần | Có thể dùng chung khi | Nên tách khi |
|---|---|---|
| `JdbcMappingContext` | Domain mapping, naming strategy và metadata giống nhau | Mapping hoặc naming strategy khác nhau |
| `JdbcConverter` | Conversion rules và JDBC mapping tương thích | Có custom conversions hoặc mapping khác nhau |
| `JdbcCustomConversions` | Hai nguồn cần cùng tập converter | Kiểu lưu trữ hoặc quy tắc chuyển đổi khác nhau |
| `JdbcDialect` | Database dùng cùng dialect | Database khác hệ quản trị hoặc khác dialect |
| `DataAccessStrategy` | Cùng resource và cùng mapping infrastructure | Mỗi DataSource cần thao tác riêng |
| `JdbcAggregateTemplate` | Cùng data access strategy và resource | Mỗi database có strategy riêng |

Ví dụ, orders dùng PostgreSQL còn inventory dùng một hệ quản trị khác. Hai database có thể khác cách tạo ID, quoting identifier, hỗ trợ array hoặc cú pháp SQL. Khi đó không nên giả định một dialect duy nhất hoạt động đúng cho cả hai.

Nếu cả hai nguồn đều là PostgreSQL và dùng cùng domain mapping, có thể chia sẻ một số cấu hình metadata. Tuy nhiên, mỗi `DataAccessStrategy` vẫn cần gắn với JDBC operations của DataSource tương ứng.

## 10. Transaction khi một use case ghi vào hai DataSource

Đây là giới hạn quan trọng nhất của cấu hình nhiều database.

Giả sử một use case cần:

1. Tạo đơn hàng trong database orders.
2. Giảm tồn kho trong database inventory.

Code:

~~~java
@Service
public class CheckoutService {

    private final OrderService orders;
    private final InventoryService inventory;

    public CheckoutService(
            OrderService orders,
            InventoryService inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    public Long checkout(CreateOrderCommand command) {
        Long orderId = orders.createOrder(command);
        inventory.reserve(
            command.productId(),
            command.quantity()
        );
        return orderId;
    }
}
~~~

`orders.createOrder()` dùng `ordersTransactionManager`; `inventory.reserve()` dùng `inventoryTransactionManager`. Hai transaction manager quản lý hai transaction riêng.

Nếu ghi đơn commit thành công nhưng cập nhật kho thất bại, database orders không tự rollback theo transaction inventory. Việc gọi hai service tuần tự không biến hai transaction thành một transaction nguyên tử.

### 10.1. @Transactional trên caller không tự gộp hai transaction manager

Không thể đạt atomicity cho hai DataSource chỉ bằng cách thêm:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void checkout(...) {
    orders.createOrder(...);
    inventory.reserve(...);
}
~~~

Annotation trên caller chỉ quản lý transaction của `ordersTransactionManager`. Transaction của inventory phải được quản lý riêng nếu service inventory mở transaction bằng manager khác.

Tương tự, `REQUIRED` chỉ tham gia transaction hiện có do cùng transaction manager/resource quản lý. `REQUIRED` trên một transaction manager khác không tự tham gia transaction JDBC của database thứ nhất.

### 10.2. Các lựa chọn khi cần nhất quán giữa hai database

**Chấp nhận transaction riêng và xử lý bù:** mỗi database commit độc lập. Nếu bước thứ hai thất bại, ứng dụng chạy hành động bù, chẳng hạn hủy đơn đã tạo hoặc hoàn lại trạng thái giữ hàng.

**Saga hoặc workflow:** biểu diễn quy trình nhiều bước thành trạng thái rõ ràng. Mỗi bước commit cục bộ và có hành động bù khi bước sau thất bại. Cách này phù hợp với quy trình kéo dài và nhiều service.

**Outbox và message:** ghi thay đổi aggregate cùng một outbox event trong transaction của database sở hữu aggregate. Một worker phát event và service khác cập nhật database riêng. Cần thiết kế retry, idempotency và trạng thái xử lý.

**Distributed transaction/XA:** nếu hệ thống và database hỗ trợ XA/JTA, có thể dùng transaction coordinator để quản lý nhiều resource trong một global transaction. Cách này tăng độ phức tạp vận hành, yêu cầu driver/resource phù hợp và có thể ảnh hưởng hiệu năng/availability. Không phải mọi DataSource đều hỗ trợ XA.

Không dùng một transaction manager JDBC thông thường như thể nó tự quản lý nhiều DataSource. Chọn cơ chế nhất quán dựa trên yêu cầu nghiệp vụ và khả năng vận hành.

## 11. Transaction manager, propagation và lời gọi giữa service

Trong cùng một database, các service dùng cùng transaction manager và propagation `REQUIRED` có thể tham gia một transaction vật lý:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void createOrder(...) {
    orderRepository.save(...);
    orderLineService.addLines(...);
}
~~~

Nếu `orderLineService` cũng dùng `ordersTransactionManager` với `REQUIRED`, nó tham gia transaction đang có.

Nếu service được gọi dùng `inventoryTransactionManager`, nó đang làm việc với transaction resource khác. `REQUIRED` ở service đó không biến thành transaction con của orders.

Đối với service cần transaction độc lập trên cùng database, có thể dùng `REQUIRES_NEW` với đúng transaction manager. Nhưng cần cân nhắc connection pool, lock và consistency như bài học về propagation.

## 12. Đọc từ database khác

Nhiều ứng dụng dùng database giao dịch để ghi và database read replica hoặc reporting database để đọc. Khi đó có thể tổ chức repository theo hai package:

~~~text
orders.repository.write
orders.repository.read
~~~

hoặc tách module rõ hơn theo trách nhiệm. Repository đọc cần gắn với DataSource read tương ứng. Nếu read replica có độ trễ replication, dữ liệu vừa ghi có thể chưa xuất hiện ngay khi đọc từ replica.

Không giả định rằng transaction commit trên primary khiến read replica nhìn thấy dữ liệu tức thì. Nếu use case cần read-your-writes, có thể đọc từ primary trong một khoảng thời gian hoặc dùng cơ chế định tuyến phù hợp.

Với reporting database có schema tổng hợp, DTO/projection và `NamedParameterJdbcTemplate` có thể phù hợp hơn việc tải aggregate giao dịch.

## 13. DataSource định tuyến động cho tenant

Nếu nhiều tenant dùng cùng schema và cùng kiểu mapping nhưng mỗi tenant có database riêng, có thể cân nhắc `AbstractRoutingDataSource` thay vì khai báo một nhóm repository cho từng tenant.

Mô hình:

~~~text
Repository
    |
    v
Routing DataSource
    |
    +--> tenant A DataSource
    +--> tenant B DataSource
    +--> tenant C DataSource
~~~

Routing DataSource chọn DataSource đích dựa trên context, thường là tenant ID được thiết lập trước khi lấy connection.

Một số lưu ý:

- Tenant context phải được xác định trước khi transaction lấy connection.
- Không đổi tenant giữa transaction đang chạy.
- Context cần được xóa sau request/task để tránh rò rỉ tenant sang thread hoặc request kế tiếp.
- Mọi tenant phải có schema tương thích với mapping đang dùng.
- Cần kiểm soát pool connection và số lượng DataSource khi số tenant lớn.

Nếu các tenant có schema, dialect hoặc lifecycle khác nhau, routing một DataSource có thể không đủ; cần cấu hình persistence riêng hoặc một kiến trúc khác.

## 14. Migration và vận hành nhiều database

Khi có nhiều DataSource, migration schema cũng cần gắn đúng database.

Ví dụ:

| Database | Migration chịu trách nhiệm |
|---|---|
| orders | Bảng purchase_orders, order_lines, order_audit |
| inventory | Bảng inventory_items, stock_reservations |
| reporting | View hoặc bảng tổng hợp phục vụ báo cáo |

Mỗi migration tool cần được cấu hình với đúng DataSource và schema. Không để migration của orders vô tình chạy trên inventory vì dùng nhầm bean mặc định.

Vận hành cũng cần theo dõi riêng:

- Connection pool từng DataSource.
- Transaction timeout và lock timeout.
- Health check và trạng thái kết nối.
- Credentials và quyền truy cập từng database.
- Backup/restore và retention.
- Migration version của từng database.
- Metrics lỗi và thời gian truy vấn theo nguồn.

Một database bị lỗi không nhất thiết làm database khác ngừng hoạt động, nhưng ứng dụng cần định nghĩa cách xử lý khi một phần use case không thể hoàn tất.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không inject được DataSource | Có nhiều bean cùng kiểu mà không có qualifier/primary | Dùng `@Qualifier` hoặc `@Primary` có chủ đích |
| Repository kết nối nhầm database | Package scan hoặc `jdbcOperationsRef` cấu hình sai | Tách package và chỉ rõ JDBC operations |
| Transaction không rollback câu SQL | Transaction manager dùng DataSource khác với JDBC operations | Ghép đúng DataSource và manager |
| `@Transactional` chọn sai manager | Dựa vào default khi có nhiều manager | Chỉ rõ `transactionManager` |
| Repository bị đăng ký hai lần | Hai cấu hình cùng scan một package | Phân vùng `basePackages` không chồng lấn |
| Template thao tác sai database | Dùng `DataAccessStrategy`/JDBC operations của nguồn khác | Tạo template từ infrastructure tương ứng |
| Bean mapping context bị trùng tên | Nhiều cấu hình nền tạo bean mặc định giống nhau | Kiểm soát bean naming và cấu hình mapping |
| Custom converter chỉ hoạt động ở một database | Converter được đăng ký trong infrastructure khác | Đăng ký converter vào đúng `JdbcCustomConversions` |
| Dialect tạo SQL không phù hợp | Dùng chung dialect cho database khác hệ quản trị | Cấu hình dialect theo nguồn dữ liệu |
| Một transaction không rollback được cả hai database | Hai transaction manager JDBC độc lập | Dùng Saga/outbox hoặc XA/JTA nếu thật sự cần |
| Đọc replica không thấy dữ liệu vừa ghi | Replication lag | Dùng primary cho read-your-writes hoặc chấp nhận eventual consistency |
| Tenant bị định tuyến nhầm | Tenant context đổi sau khi connection đã lấy hoặc không được dọn | Thiết lập và dọn context đúng vòng đời |
| Migration chạy sai database | Migration tool dùng DataSource mặc định | Cấu hình migration riêng cho từng nguồn |

## 16. Quy trình cấu hình nhiều DataSource

Khi tách persistence cho nhiều database, có thể làm theo trình tự:

1. **Xác định ranh giới dữ liệu:** nhóm aggregate nào thuộc database nào.
2. **Tách package repository:** mỗi cấu hình scan một package riêng.
3. **Khai báo DataSource:** đặt bean name và property prefix rõ ràng.
4. **Tạo JDBC operations:** mỗi bean dùng đúng DataSource.
5. **Tạo transaction manager:** mỗi manager quản lý đúng DataSource.
6. **Cấu hình repository:** chỉ rõ `basePackages`, `jdbcOperationsRef` và `transactionManagerRef`.
7. **Cấu hình mapping:** kiểm tra converter, mapping context, dialect và data access strategy.
8. **Cấu hình template:** nếu dùng trực tiếp, tạo template từ infrastructure của đúng nguồn.
9. **Chọn transaction manager:** ghi rõ manager trong `@Transactional`.
10. **Xác định tính nguyên tử:** quyết định cách xử lý use case ghi nhiều database.
11. **Kiểm tra migration và vận hành:** bảo đảm schema, pool và health check tách đúng nguồn.
12. **Integration test:** xác nhận từng repository ghi đúng database và rollback đúng transaction manager.

## 17. Bài tập thực hành

### Bài 1 — Hai DataSource và hai repository group

1. Tạo hai database `orders_db` và `inventory_db`.
2. Tạo hai bean DataSource với tên riêng.
3. Tạo `ordersJdbcOperations` và `inventoryJdbcOperations`.
4. Tạo hai transaction manager tương ứng.
5. Tách package repository.
6. Dùng hai cấu hình `@EnableJdbcRepositories` để gắn repository vào đúng nguồn.
7. Lưu dữ liệu và kiểm tra từng database.

### Bài 2 — Chọn transaction manager

1. Tạo `OrderService` dùng `ordersTransactionManager`.
2. Tạo `InventoryService` dùng `inventoryTransactionManager`.
3. Gây lỗi sau thao tác ghi.
4. Xác nhận transaction rollback trên đúng database.
5. Thử bỏ qualifier manager và quan sát lựa chọn mặc định của Spring.

### Bài 3 — Hai JdbcAggregateTemplate

1. Tạo infrastructure riêng cho hai database.
2. Đăng ký hai template với bean name khác nhau.
3. Inject bằng `@Qualifier`.
4. Gọi `insert` trên từng template.
5. Xác nhận mỗi aggregate được lưu vào đúng database.

### Bài 4 — Một use case ghi hai database

1. Tạo đơn trong orders.
2. Cập nhật tồn kho trong inventory.
3. Làm thao tác inventory thất bại sau khi orders đã commit.
4. Quan sát vì sao transaction orders không tự rollback.
5. Thiết kế hành động bù hoặc outbox/Saga cho quy trình.

### Bài 5 — Nguồn đọc riêng

1. Cấu hình một DataSource read-only hoặc reporting.
2. Tạo repository/DAO đọc báo cáo.
3. Thực hiện một lần ghi vào primary.
4. Quan sát độ trễ nếu đọc qua replica.
5. Thiết kế read-your-writes cho use case cần dữ liệu mới ngay.

## 18. Kết luận

Với nhiều DataSource, hãy tách repository theo package và gắn mỗi nhóm với `NamedParameterJdbcOperations` cùng transaction manager của nguồn dữ liệu tương ứng. Khi dùng `JdbcAggregateTemplate` trực tiếp, template phải được tạo từ `DataAccessStrategy`, converter, mapping context và JDBC operations phù hợp với database đó. Trong service, chỉ rõ `transactionManager` để Spring mở transaction trên đúng resource.

Mỗi JDBC transaction manager thông thường quản lý một DataSource. Hai service dùng hai manager khác nhau không tự tạo thành một transaction nguyên tử, kể cả khi được gọi trong cùng một method. Nếu một use case cần phối hợp nhiều database, hãy thiết kế transaction cục bộ cùng hành động bù, Saga hoặc outbox; chỉ dùng XA/JTA khi hạ tầng thực sự hỗ trợ và yêu cầu cần distributed transaction.

Tách rõ resource, repository scan, template và transaction manager giúp ứng dụng tránh truy cập nhầm database, rollback nhầm phạm vi hoặc giả định sai về tính nguyên tử. Hãy kiểm chứng bằng integration test trên từng database thực tế và quản lý migration, connection pool cùng health check riêng cho mỗi nguồn.
