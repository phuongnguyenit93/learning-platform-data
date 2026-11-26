# Chọn template, factory và transaction manager đúng mô-đun

## Mục tiêu bài học

Trong ứng dụng nhiều store, nhận diện đúng repository mới giải quyết một phần cấu hình. Repository còn phải sử dụng đúng cơ chế thực thi, đúng nguồn dữ liệu và đúng transaction manager.

Một repository JPA có thể được nhận diện chính xác nhưng vẫn nối nhầm entity manager factory. Một MongoTemplate có thể truy cập đúng database nhưng không tham gia transaction mà service mong đợi nếu transaction manager dùng một database factory khác.

Bài học thuộc chương **Nhiều store** của module SPRING_DATA_COMMONS. Sau bài học, bạn có thể:

- Phân biệt factory tạo repository với factory cung cấp hạ tầng lưu trữ.
- Chọn API truy cập dữ liệu phù hợp với module.
- Liên kết repository JPA với entity manager factory và transaction manager cụ thể.
- Liên kết repository MongoDB với MongoTemplate cụ thể.
- Đảm bảo code tùy biến sử dụng cùng hạ tầng với repository.
- Nhận diện giới hạn của transaction cục bộ và sự khác nhau giữa imperative với reactive.

Commons cung cấp abstraction và hạ tầng chung. Các lựa chọn kết nối, mapping và transaction vẫn cần tuân theo cơ chế của từng module lưu trữ.

## 1. Theo dõi một chuỗi liên kết hoàn chỉnh

Có thể phân tích một repository theo chuỗi:

~~~text
Interface repository
    -> factory repository của module
    -> API thực thi hoặc template
    -> factory/kết nối của nguồn dữ liệu
    -> database thực tế

Method service có transaction
    -> transaction manager được chọn
    -> tài nguyên mà manager đó quản lý
~~~

Hai nhánh phải gặp nhau ở đúng tài nguyên nếu muốn các thao tác tham gia transaction mong đợi.

Ví dụ:

~~~mermaid
flowchart TD
    A["OrderRepository"] --> B["Factory repository JPA"]
    B --> C["EntityManager"]
    C --> D["ordersEntityManagerFactory"]
    D --> E["ordersDataSource"]
    F["ordersTransactionManager"] --> D
    G["AuditRecordRepository"] --> H["Factory repository MongoDB"]
    H --> I["auditMongoTemplate"]
    I --> J["auditMongoDatabaseFactory"]
    K["auditMongoTransactionManager"] --> J
~~~

Mũi tên thể hiện liên kết trách nhiệm. Nó không phải cam kết về thứ tự tạo bean hoặc toàn bộ các interceptor nội bộ.

Tên bean rõ ràng giúp người đọc theo dõi, nhưng chỉ tên không đủ. Phải kiểm tra đối tượng được tham chiếu và nguồn dữ liệu mà nó thực sự đại diện.

## 2. Có nhiều loại factory khác nhau

| Khái niệm | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| Factory/factory bean tạo repository | JpaRepositoryFactory, JpaRepositoryFactoryBean | Xây dựng repository JPA và cơ chế xử lý lời gọi. |
| Factory/factory bean tạo repository | MongoRepositoryFactory, MongoRepositoryFactoryBean | Xây dựng repository MongoDB. |
| Hạ tầng persistence JPA | EntityManagerFactory | Tạo hoặc cung cấp EntityManager cho một persistence unit. |
| Hạ tầng MongoDB | MongoDatabaseFactory | Cung cấp database và hỗ trợ tài nguyên/session theo cơ chế MongoDB. |
| FactoryBean của Spring tạo hạ tầng JPA | LocalContainerEntityManagerFactoryBean | Tích hợp quá trình xây dựng EntityManagerFactory vào container. |

Cùng có chữ “factory” nhưng các đối tượng này không thay thế nhau.

Trong JPA:

- `entityManagerFactoryRef` trỏ tới bean sản phẩm kiểu EntityManagerFactory.
- `repositoryFactoryBeanClass` là lựa chọn lớp factory bean để tạo repository.
- Hai cấu hình đó giải quyết hai nhu cầu khác nhau.

Thông thường, để chuyển một tập repository JPA sang một datasource khác, bạn cấu hình entity manager factory và transaction manager phù hợp. Không cần tự viết factory repository mới chỉ vì có nhiều cơ sở dữ liệu.

Trong MongoDB, chọn template khác cũng không có nghĩa phải thay MongoRepositoryFactoryBean bằng một implementation tùy biến.

## 3. Chọn đúng API truy cập dữ liệu của module

| Module/cơ chế | API hoặc template thường dùng | Tài nguyên và transaction liên quan |
| --- | --- | --- |
| JPA | EntityManager | EntityManagerFactory; thường dùng JpaTransactionManager cho transaction cục bộ JPA. |
| MongoDB imperative | MongoTemplate hoặc MongoOperations | MongoDatabaseFactory; MongoTransactionManager khi dùng transaction MongoDB phù hợp. |
| Spring Data JDBC | JdbcAggregateTemplate và hạ tầng JDBC tương ứng | DataSource; transaction manager JDBC phù hợp. |
| R2DBC | R2dbcEntityTemplate hoặc R2dbcEntityOperations | ConnectionFactory; R2dbcTransactionManager. |
| MongoDB reactive | ReactiveMongoTemplate hoặc ReactiveMongoOperations | ReactiveMongoDatabaseFactory; ReactiveMongoTransactionManager. |

Không có một template của Commons tự hiểu mọi mapping, query và transaction của tất cả các store.

JPA repository sử dụng EntityManager theo cơ chế JPA. Không cần tìm một template chung tên tương tự MongoTemplate để cấu hình JPA.

Các module có thể cùng sử dụng Pageable, Sort, projection hoặc metadata repository, nhưng đó là sự dùng chung hợp đồng, không phải khả năng hoán đổi những đối tượng thực thi bên dưới.

## 4. Chuẩn bị ví dụ JPA và MongoDB

Ví dụ có hai phần dữ liệu:

- Đơn hàng lưu ở cơ sở dữ liệu quan hệ.
- Bản ghi kiểm toán lưu ở MongoDB.

Bố cục package:

~~~text
com.example.multistore
    order
        domain
            PurchaseOrder
        repository
            OrderRepository
    audit
        document
            AuditRecord
        repository
            AuditRecordRepository
    config
        OrdersJpaConfiguration
        AuditMongoConfiguration
    service
        OrderService
        AuditService
~~~

Giả định dự án đã có bộ dependency tương thích và hai bean kết nối nền:

| Bean đã được chuẩn bị | Kiểu | Ý nghĩa |
| --- | --- | --- |
| ordersDataSource | DataSource | Kết nối tới cơ sở dữ liệu đơn hàng. |
| auditMongoDatabaseFactory | MongoDatabaseFactory | Kết nối và database dùng cho dữ liệu kiểm toán. |

Cấu hình kết nối được cung cấp theo môi trường. Các đoạn mã tiếp theo tập trung vào việc liên kết repository, tài nguyên và transaction.

Ví dụ JPA dùng Jakarta Persistence cùng Hibernate. Schema đơn hàng được chuẩn bị trước; cấu hình minh họa sẽ kiểm tra schema thay vì tự tạo dữ liệu hoặc bảng.

### 4.1. Entity đơn hàng

File `order/domain/PurchaseOrder.java`:

~~~java
package com.example.multistore.order.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }
}
~~~

Chiến lược sinh ID phải phù hợp với database thực tế. Mapping này không tự trở thành mapping MongoDB.

### 4.2. Document kiểm toán

File `audit/document/AuditRecord.java`:

~~~java
package com.example.multistore.audit.document;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "audit_records")
public class AuditRecord {

    @Id
    private String id;

    private String orderNumber;

    private String action;

    protected AuditRecord() {
    }

    public AuditRecord(String orderNumber, String action) {
        this.orderNumber = orderNumber;
        this.action = action;
    }

    public String getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getAction() {
        return action;
    }
}
~~~

OrderNumber là dữ liệu nghiệp vụ dùng để liên hệ hai phía. Việc hai model có cùng thuộc tính đó không tự tạo join hoặc giao dịch xuyên store.

### 4.3. Hai repository

File `order/repository/OrderRepository.java`:

~~~java
package com.example.multistore.order.repository;

import com.example.multistore.order.domain.PurchaseOrder;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

File `audit/repository/AuditRecordRepository.java`:

~~~java
package com.example.multistore.audit.repository;

import com.example.multistore.audit.document.AuditRecord;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AuditRecordRepository
        extends MongoRepository<AuditRecord, String> {
}
~~~

Interface và mapping đều thể hiện đúng module. Bước tiếp theo là gắn chúng với đúng hạ tầng cụ thể.

## 5. Liên kết repository JPA với persistence unit và transaction manager

File `config/OrdersJpaConfiguration.java`:

~~~java
package com.example.multistore.config;

import com.example.multistore.order.domain.PurchaseOrder;
import com.example.multistore.order.repository.OrderRepository;
import jakarta.persistence.EntityManagerFactory;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.orm.jpa.vendor.HibernateJpaVendorAdapter;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement
@EnableJpaRepositories(
    basePackageClasses = OrderRepository.class,
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfiguration {

    @Bean(name = "ordersEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean
            ordersEntityManagerFactory(
                    @Qualifier("ordersDataSource")
                    DataSource dataSource) {

        LocalContainerEntityManagerFactoryBean factory =
            new LocalContainerEntityManagerFactoryBean();

        factory.setDataSource(dataSource);
        factory.setPackagesToScan(
            PurchaseOrder.class.getPackageName()
        );
        factory.setPersistenceUnitName("ordersUnit");
        factory.setJpaVendorAdapter(
            new HibernateJpaVendorAdapter()
        );
        factory.setJpaPropertyMap(
            Map.of("hibernate.hbm2ddl.auto", "validate")
        );

        return factory;
    }

    @Bean(name = "ordersTransactionManager")
    JpaTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {

        return new JpaTransactionManager(entityManagerFactory);
    }
}
~~~

Những liên kết quan trọng:

1. Package của OrderRepository thuộc vùng repository JPA này.
2. Repository dùng EntityManagerFactory có tên ordersEntityManagerFactory.
3. Factory đó quản lý entity ở package của PurchaseOrder.
4. Factory đó dùng ordersDataSource.
5. ordersTransactionManager được xây trên chính EntityManagerFactory đó.

`@EnableTransactionManagement` kích hoạt hạ tầng proxy cho transaction annotation trong cấu hình ví dụ. Một ứng dụng Boot có thể đã tự cấu hình phần này; không phải mọi dự án đều cần thêm lại annotation.

Bean method trả LocalContainerEntityManagerFactoryBean nhưng container cung cấp sản phẩm EntityManagerFactory khi dependency yêu cầu kiểu đó. Tham chiếu entityManagerFactoryRef cần hướng đến sản phẩm persistence factory, không phải thay bằng tên repository factory.

Vì ví dụ tự xây EntityManagerFactory, các property provider cần được thiết lập có chủ đích. Không mặc định mọi cấu hình `spring.jpa.*` của Boot đều tự động được áp vào một factory tự tạo theo bất kỳ cách nào.

Nếu có thêm một datasource JPA, hãy tạo một nhóm liên kết tương ứng và một vùng repository riêng. Đổi tên transaction manager mà vẫn giữ nhầm EntityManagerFactory không tạo được sự tách biệt mong muốn.

## 6. Liên kết Mongo repository với template cụ thể

File `config/AuditMongoConfiguration.java`:

~~~java
package com.example.multistore.config;

import com.example.multistore.audit.repository.AuditRecordRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
    basePackageClasses = AuditRecordRepository.class,
    mongoTemplateRef = "auditMongoTemplate"
)
public class AuditMongoConfiguration {

    @Bean(name = "auditMongoTemplate")
    MongoTemplate auditMongoTemplate(
            @Qualifier("auditMongoDatabaseFactory")
            MongoDatabaseFactory databaseFactory) {

        return new MongoTemplate(databaseFactory);
    }

    @Bean(name = "auditMongoTransactionManager")
    MongoTransactionManager auditMongoTransactionManager(
            @Qualifier("auditMongoDatabaseFactory")
            MongoDatabaseFactory databaseFactory) {

        return new MongoTransactionManager(databaseFactory);
    }
}
~~~

Ở đây:

- Repository MongoDB được tạo với auditMongoTemplate.
- Template sử dụng auditMongoDatabaseFactory.
- Transaction manager MongoDB cũng dùng chính bean database factory đó.

Việc dùng cùng factory là điều quan trọng để template tham gia cơ chế session/transaction mà manager quản lý. Hai factory được tạo riêng dù có cấu hình URI giống nhau chưa phải cùng một tài nguyên được liên kết theo cách mà ứng dụng cần.

`mongoTemplateRef` là liên kết tới template, không phải tên transaction manager. Không suy từ các thuộc tính của @EnableJpaRepositories rồi gán một thuộc tính transactionManagerRef tương tự cho @EnableMongoRepositories trong API đang dùng.

Đăng ký MongoTransactionManager cũng chưa có nghĩa mọi lời gọi Mongo repository mặc nhiên chạy trong một transaction nhiều thao tác. Cần ranh giới transaction được mở theo cơ chế tương ứng.

MongoDB server và topology phải hỗ trợ transaction cần sử dụng; một standalone server thông thường không cung cấp cùng khả năng transaction nhiều document như cấu hình replica set hoặc sharded cluster phù hợp.

Nếu không có yêu cầu transaction MongoDB nhiều thao tác, ứng dụng vẫn có thể dùng template/repository với cơ chế bảo đảm riêng của các thao tác MongoDB. Đừng coi việc luôn tạo transaction manager là điều kiện bắt buộc cho mọi lần truy cập MongoDB.

## 7. Chọn transaction manager tại ranh giới service

Trong ứng dụng có nhiều manager, khai báo tên rõ giúp service thể hiện tài nguyên mà nghiệp vụ đang điều phối.

### 7.1. Service ghi đơn hàng

~~~java
package com.example.multistore.service;

import com.example.multistore.order.domain.PurchaseOrder;
import com.example.multistore.order.repository.OrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(
        transactionManager = "ordersTransactionManager"
    )
    public PurchaseOrder create(String orderNumber) {
        return repository.save(
            new PurchaseOrder(orderNumber)
        );
    }
}
~~~

Ranh giới service và cấu hình repository đều trỏ về hệ JPA đơn hàng.

### 7.2. Service ghi kiểm toán

~~~java
package com.example.multistore.service;

import com.example.multistore.audit.document.AuditRecord;
import com.example.multistore.audit.repository.AuditRecordRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {

    private final AuditRecordRepository repository;

    public AuditService(AuditRecordRepository repository) {
        this.repository = repository;
    }

    @Transactional(
        transactionManager = "auditMongoTransactionManager"
    )
    public AuditRecord record(
            String orderNumber,
            String action) {

        return repository.save(
            new AuditRecord(orderNumber, action)
        );
    }
}
~~~

Hai service dùng annotation `org.springframework.transaction.annotation.Transactional`. Nếu dùng một annotation cùng tên từ namespace khác, cần kiểm tra API của annotation đó; không mặc định nó có thuộc tính chọn manager tương tự.

Transaction annotation có hiệu lực theo cơ chế interception đã cấu hình. Với proxy thông thường, gọi một method có annotation từ một method khác ngay trong cùng instance không tự đi qua proxy để mở transaction mới.

Nên đánh giá transaction trên lời gọi thật sự đi qua bean Spring, không chỉ dựa vào việc source code có một annotation.

## 8. Code tùy biến phải dùng đúng tài nguyên như repository

Repository có thể được liên kết đúng nhưng một fragment hoặc adapter tùy biến lại inject template mặc định. Khi đó, các method trong cùng một API có thể truy cập nguồn khác nhau ngoài ý định.

### 8.1. Chọn EntityManager của đúng persistence unit

Một thành phần JPA tùy biến có thể dùng:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class OrderStatistics {

    @PersistenceContext(unitName = "ordersUnit")
    private EntityManager entityManager;

    @Transactional(
        transactionManager = "ordersTransactionManager",
        readOnly = true
    )
    public long countOrders() {
        return entityManager.createQuery(
            "select count(o) from PurchaseOrder o",
            Long.class
        ).getSingleResult();
    }
}
~~~

`ordersUnit` là tên persistence unit đã đặt trong cấu hình factory, không phải tên bean transaction manager.

Đừng hoán đổi tùy ý:

- ordersEntityManagerFactory: tên bean hạ tầng persistence.
- ordersUnit: tên persistence unit.
- ordersTransactionManager: tên manager điều phối transaction.

### 8.2. Chọn MongoTemplate bằng qualifier

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AuditQueries {

    private final MongoTemplate template;

    public AuditQueries(
            @Qualifier("auditMongoTemplate")
            MongoTemplate template) {
        this.template = template;
    }
}
~~~

Trong một fragment, nguyên tắc chọn template cũng như vậy. Fragment không tự thừa hưởng mọi lựa chọn injection chỉ vì được ghép vào repository đã có mongoTemplateRef.

Nếu đoạn code tùy biến cần tham gia transaction MongoDB, nó phải được gọi trong ranh giới phù hợp và dùng template nối với đúng database factory mà manager đó quản lý.

## 9. @Primary, @Qualifier và các thuộc tính Ref giải quyết việc khác nhau

| Cơ chế | Điều nó xác định |
| --- | --- |
| @Primary | Ứng viên ưu tiên trong những tình huống phân giải dependency mặc định có liên quan. |
| @Qualifier | Bean cụ thể được chọn tại điểm injection phù hợp. |
| entityManagerFactoryRef | Persistence factory dùng cho nhóm repository JPA. |
| transactionManagerRef trong cấu hình JPA | Manager được cấu hình cho nhóm repository JPA. |
| mongoTemplateRef | Template dùng để tạo nhóm Mongo repository. |
| @Transactional(transactionManager = ...) | Manager dùng để mở ranh giới transaction của lời gọi được xử lý. |

Đặt @Primary lên một template hoặc manager không tự viết lại tất cả những thuộc tính Ref đã cấu hình.

Ngược lại, một thuộc tính Ref đúng ở repository không tự sửa mọi injection trong code tùy biến hoặc mọi annotation transaction ở service.

Khi dự án có nhiều bean cùng kiểu, dùng tên và qualifier có chủ đích. Không coi “không còn lỗi nhiều bean” là bằng chứng chắc chắn rằng đã chọn đúng nguồn dữ liệu.

Một cấu hình có thể chọn được một bean hợp lệ về kiểu nhưng sai tài nguyên. Lỗi đó có thể không xuất hiện ngay lúc khởi động.

## 10. Khi nào cần thay repository factory?

Phần lớn cấu hình nhiều store chỉ cần:

- Chọn interface và mapping đúng module.
- Tách vùng repository.
- Liên kết đúng template hoặc persistence factory.
- Chọn transaction manager tương ứng.

`repositoryFactoryBeanClass` hữu ích khi thực sự mở rộng cơ chế tạo repository theo yêu cầu và hợp đồng của module. Nó không phải công tắc đổi JPA repository thành Mongo repository.

Dùng một factory bean của module khác có thể làm metadata, constructor, mapping và chiến lược query không tương thích. Commons cung cấp nền tảng chung không có nghĩa những factory cụ thể trở thành các thành phần thay thế tùy ý.

Cũng phân biệt thay repository factory với thay base implementation. Một yêu cầu thêm hành vi chung có thể dùng fragment hoặc base class phù hợp mà không cần tự xây toàn bộ factory.

Khi mở rộng, vẫn phải giữ đúng liên kết tài nguyên. Một factory tùy biến không tự giải quyết vấn đề transaction manager hoặc template bị chọn sai.

## 11. Một transaction manager không tạo giao dịch nguyên tử xuyên hai store

Xét một method được mở bởi ordersTransactionManager nhưng bên trong vừa lưu đơn hàng vừa gọi MongoTemplate ghi kiểm toán.

Annotation chỉ chọn manager JPA cho ranh giới đó. Nó không tự biến hai kho dữ liệu thành một transaction chung.

Những kết quả có thể xảy ra tùy đường thực thi và cấu hình:

| Tình huống | Hệ quả cần đánh giá |
| --- | --- |
| Mongo ghi thành công nhưng JPA rollback sau đó. | Có bản ghi kiểm toán cho một đơn hàng chưa được commit. |
| JPA đã hoàn tất ở một ranh giới trước, Mongo ghi thất bại. | Đơn hàng tồn tại nhưng thiếu dữ liệu kiểm toán. |
| Hai manager mở hai transaction cục bộ. | Có hai phạm vi commit/rollback; chưa có bảo đảm nguyên tử toàn cục. |

Chuyển lần ghi thứ hai sang REQUIRES_NEW cũng không tự tạo nguyên tử xuyên store. Nó thay đổi ranh giới của một transaction được hỗ trợ, không cung cấp một cơ chế commit chung cho mọi hệ thống.

Nếu nghiệp vụ yêu cầu phối hợp nhiều store, cần thiết kế nhất quán dữ liệu và xử lý thất bại. Tùy yêu cầu, ứng dụng có thể dùng một nguồn dữ liệu chuẩn rồi đồng bộ, outbox hoặc cơ chế điều phối thích hợp.

Lựa chọn cụ thể thuộc thiết kế hệ thống. Việc chọn manager đúng vẫn cần thiết, nhưng chỉ chứng minh transaction cục bộ đang quản lý đúng tài nguyên của nó.

## 12. Giữ nhất quán imperative và reactive

Trong bảng lựa chọn module, các manager reactive không phải tên khác của manager imperative.

- JPA thường sử dụng API đồng bộ, EntityManager và transaction theo mô hình thread-bound tương ứng.
- R2DBC dùng API reactive và transaction gắn với reactive context.
- MongoDB có các template và transaction manager riêng cho hai mô hình.

Không chọn R2dbcTransactionManager cho một luồng JPA chỉ vì cả hai cùng truy cập cơ sở dữ liệu quan hệ.

Tương tự, một reactive Mongo repository cần hạ tầng reactive phù hợp. Chọn MongoTemplate imperative rồi kỳ vọng reactive transaction tự bao bọc các thao tác đó là cấu hình không nhất quán.

Dùng `block()` để lấy giá trị từ publisher không tự làm tài nguyên reactive tham gia một transaction JPA. Những bước chuyển mô hình thực thi cần được thiết kế, không được suy ra từ abstraction repository chung.

## 13. Phân tích các lỗi thường gặp

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Repository JPA báo domain không được quản lý. | Repository đang dùng EntityManagerFactory nào; factory đó quét đúng entity không? |
| Không tìm thấy một bean hạ tầng mặc định. | Tên Ref có khớp tên bean đã khai báo không? |
| Mongo repository truy cập nhầm database. | mongoTemplateRef trỏ tới template nào; template dùng database factory nào? |
| Code tùy biến có dữ liệu khác method CRUD. | Fragment/adapter có inject nhầm template hoặc EntityManager không? |
| Có nhiều transaction manager và lời gọi không rõ manager. | Annotation transaction, cấu hình mặc định và transactionManagerRef của nhóm repository. |
| Một thao tác không rollback như mong đợi. | Đúng tài nguyên, manager, đường gọi proxy và ranh giới commit chưa? |
| Mongo transaction không hoạt động. | Template và manager có dùng cùng factory; server/topology và session có phù hợp không? |
| Không lỗi khi khởi động nhưng truy cập sai dữ liệu. | Bean được chọn đúng kiểu nhưng có thể sai nguồn; đối chiếu đích thực tế. |
| Thay factory rồi phát sinh lỗi metadata hoặc query. | Factory tùy biến có đúng module và tương thích bộ dependency không? |

Một lỗi manager có thể không xuất hiện dưới dạng “không tìm thấy transaction manager”. Nếu bean được chọn có tồn tại nhưng quản lý tài nguyên khác, lời gọi có thể không tham gia phạm vi transaction bạn tưởng, hoặc một phần thao tác mở phạm vi khác theo cơ chế của module.

Vì vậy, cần theo dõi liên kết tài nguyên đến cùng, không chỉ kiểm tra có bean cùng tên.

## 14. Bảng đối chiếu cấu hình cho ví dụ

| Thành phần | Đơn hàng JPA | Kiểm toán MongoDB |
| --- | --- | --- |
| Repository | OrderRepository | AuditRecordRepository |
| Domain | PurchaseOrder | AuditRecord |
| Factory repository | Cơ chế JPA mặc định. | Cơ chế MongoDB mặc định. |
| API thực thi | EntityManager. | auditMongoTemplate. |
| Factory tài nguyên | ordersEntityManagerFactory. | auditMongoDatabaseFactory. |
| Đích kết nối | ordersDataSource và database của nó. | Database mà factory MongoDB cung cấp. |
| Transaction manager | ordersTransactionManager. | auditMongoTransactionManager khi nghiệp vụ dùng transaction MongoDB. |
| Code tùy biến | EntityManager của ordersUnit. | Template được qualifier auditMongoTemplate. |

Khi kiểm chứng trong một ứng dụng thực hành, nên quan sát riêng:

1. Repository được đăng ký vào đúng module.
2. Những bean Ref tồn tại và trỏ đúng đối tượng.
3. Một thao tác dữ liệu đi tới đúng nguồn.
4. Một tình huống rollback tác động đúng tài nguyên cục bộ.
5. Yêu cầu liên quan hai store có chính sách xử lý thất bại riêng.

Một lời gọi thành công chưa tự kiểm chứng rollback. Một lần rollback ở JPA cũng chưa chứng minh MongoDB được rollback cùng nó.

## 15. Bài tập vận dụng

### Bài tập 1: Tìm liên kết sai

OrderRepository được cấu hình dùng ordersEntityManagerFactory nhưng ordersTransactionManager lại được tạo từ một EntityManagerFactory của kho báo cáo.

Hãy xác định chuỗi liên kết bị lệch và đề xuất cấu hình nhất quán. Giải thích vì sao chỉ đổi tên bean manager không giải quyết được vấn đề.

### Bài tập 2: Hai MongoTemplate

Ứng dụng có auditMongoTemplate và archiveMongoTemplate. Repository kiểm toán đã chọn đúng auditMongoTemplate nhưng một fragment inject MongoTemplate không có qualifier.

Hãy xác định thông tin cần bổ sung ở điểm injection và điều kiện để fragment tham gia cùng transaction MongoDB với phần còn lại.

### Bài tập 3: Phân biệt ba tên JPA

Giải thích vai trò khác nhau của:

- ordersEntityManagerFactory.
- ordersUnit.
- ordersTransactionManager.

Chỉ ra tên nào dùng trong entityManagerFactoryRef, tên nào dùng trong @PersistenceContext và tên nào dùng trong @Transactional.

### Bài tập 4: Đánh giá yêu cầu xuyên store

Một service phải lưu đơn hàng và ghi audit ở MongoDB. Người viết cho rằng chọn ordersTransactionManager trên method sẽ bảo đảm cả hai cùng rollback.

Hãy chỉ ra phạm vi thực tế của manager đó và những kết quả không nhất quán có thể xảy ra. Sau đó xác định loại chính sách phối hợp dữ liệu mà nghiệp vụ cần, trước khi chọn giải pháp triển khai.

Một cấu hình đúng không chỉ có đủ template, factory và transaction manager. Các thành phần đó phải được nối thành một chuỗi nhất quán cho từng module, và service phải thể hiện đúng phạm vi tài nguyên mà mỗi transaction thực sự quản lý.