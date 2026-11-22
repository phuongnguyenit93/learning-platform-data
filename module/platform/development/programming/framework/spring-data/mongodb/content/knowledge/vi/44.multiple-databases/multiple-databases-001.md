# Nhiều MongoClient, MongoDatabaseFactory và MongoTemplate

Trong Spring Data MongoDB, một ứng dụng có thể truy cập nhiều database bằng cách cấu hình các bean kết nối và gắn từng luồng nghiệp vụ với đúng `MongoTemplate` hoặc repository. Bài học này thuộc chương **Nhiều database** của **SPRING_DATA_MONGODB**: sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác dữ liệu qua `MongoTemplate`/repository, đồng thời quản lý truy vấn, transaction, kiểm thử và hiệu năng.

## 1. Mục tiêu và tình huống thực tế

Giả sử một dịch vụ thương mại điện tử có:

- `orders_db`: đơn hàng cần giao dịch nhanh, quyền ghi chặt chẽ.
- `audit_db`: sự kiện kiểm toán có thời gian lưu trữ và chính sách truy cập khác.

Hai database có thể nằm trong **cùng một MongoDB deployment** hoặc trên **hai deployment độc lập**. Khi đó ứng dụng phải chọn đúng database cho từng thao tác, cấu hình repository rõ ràng, quản lý vòng đời kết nối và hiểu giới hạn transaction.

Sau bài này, người học có thể:

1. Phân biệt trách nhiệm của `MongoClient`, `MongoDatabaseFactory` và `MongoTemplate`.
2. Quyết định khi nào cần một hay nhiều `MongoClient`.
3. Cấu hình hai database với bean được đặt tên và `@Qualifier`.
4. Buộc từng nhóm `MongoRepository` dùng đúng `MongoTemplate` bằng `mongoTemplateRef`.
5. Nhận diện lỗi định tuyến dữ liệu, quản lý connection pool, transaction và kiểm thử cấu hình.

## 2. Ba lớp cấu hình phối hợp như thế nào?

| Thành phần | Vai trò | Phạm vi quan trọng |
| --- | --- | --- |
| `com.mongodb.client.MongoClient` | Driver client, quản lý kết nối, connection pool, cấu hình TLS/xác thực, chọn server và session | Trỏ đến một deployment/cluster; có thể truy cập nhiều database trong deployment đó |
| `org.springframework.data.mongodb.MongoDatabaseFactory` | Cung cấp đối tượng `MongoDatabase` mặc định từ client và tên database | Gắn một database mặc định với một client; có thể lấy database khác bằng `getMongoDatabase(String)` |
| `org.springframework.data.mongodb.core.MongoTemplate` | API Spring Data để CRUD, truy vấn, aggregation, mapping, exception translation | Mỗi template sử dụng một factory; thao tác thông thường đi vào database mặc định của factory |

Sơ đồ một cấu hình có hai deployment:

```text
Orders Service / Orders Repository        Audit Service / Audit Repository
                 |                                      |
        ordersMongoTemplate                      auditMongoTemplate
                 |                                      |
     ordersMongoDatabaseFactory               auditMongoDatabaseFactory
                 |                                      |
          ordersMongoClient                         auditMongoClient
                 |                                      |
      Cluster A / orders_db                    Cluster B / audit_db
```

**Lưu ý:** `MongoClient` không đại diện cho riêng một database. Một client có thể mở `getDatabase("orders_db")` và `getDatabase("audit_db")` trên cùng deployment. Nếu hai database cùng cluster, tạo nhiều client đến cùng máy chủ thường làm tăng connection pool và tài nguyên không cần thiết. `MongoTemplate` thường được đăng ký singleton và có thể tái sử dụng giữa các request.

### Chọn sơ đồ phù hợp

| Bối cảnh | Số client thường dùng | Số factory/template thường dùng |
| --- | --- | --- |
| Hai database trong cùng cluster, cùng cấu hình kết nối | 1 client dùng chung | 2 factory + 2 template |
| Hai cluster độc lập, URI/credentials khác nhau | 2 client | 2 factory + 2 template |
| Nhiều database với cấu hình mapping khác nhau | Tùy deployment | Factory và template riêng; cân nhắc converter/mapping context riêng |
| Rất nhiều tenant được tạo động | Tránh tự động tạo client riêng cho từng tenant | Cần chiến lược chọn database theo tenant, quản lý cache/vòng đời và kiểm soát quyền truy cập |

## 3. Cấu hình hai MongoClient cho hai deployment

Ví dụ dưới đây sử dụng Spring Boot với **driver đồng bộ** (`com.mongodb.client.MongoClient`) và Spring Data MongoDB. Cần có dependency `spring-boot-starter-data-mongodb` tương thích với phiên bản Spring Boot của dự án. Hai MongoDB server thử nghiệm được giả định chạy ở cổng 27017 và 27018; trong sản phẩm thực tế, dùng URI từ biến môi trường hoặc secret manager.

### 3.1. Khai báo thông số trong application.yml

```yaml
app:
  mongo:
    orders:
      uri: ${ORDERS_MONGODB_URI:mongodb://localhost:27017}
      database: orders_db
    audit:
      uri: ${AUDIT_MONGODB_URI:mongodb://localhost:27018}
      database: audit_db
```

`app.mongo.*` là **namespace tự đặt**; Spring Boot không tự sinh các template cho hai nhóm từ namespace này. Ta sẽ tự khai báo bean. Trong môi trường thật, URI nên chứa cơ chế xác thực/TLS thích hợp, không hard-code mật khẩu vào repository và không ghi URI có credential ra log.

### 3.2. Khai báo client, factory và template

```java
package com.example.multimongo.config;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;

@Configuration(proxyBeanMethods = false)
public class MultiMongoConfig {

    @Bean(name = "ordersMongoClient", destroyMethod = "close")
    MongoClient ordersMongoClient(
            @Value("${app.mongo.orders.uri}") String uri) {
        return MongoClients.create(uri);
    }

    @Bean(name = "auditMongoClient", destroyMethod = "close")
    MongoClient auditMongoClient(
            @Value("${app.mongo.audit.uri}") String uri) {
        return MongoClients.create(uri);
    }

    @Bean("ordersMongoDatabaseFactory")
    MongoDatabaseFactory ordersMongoDatabaseFactory(
            @Qualifier("ordersMongoClient") MongoClient client,
            @Value("${app.mongo.orders.database}") String dbName) {
        return new SimpleMongoClientDatabaseFactory(client, dbName);
    }

    @Bean("auditMongoDatabaseFactory")
    MongoDatabaseFactory auditMongoDatabaseFactory(
            @Qualifier("auditMongoClient") MongoClient client,
            @Value("${app.mongo.audit.database}") String dbName) {
        return new SimpleMongoClientDatabaseFactory(client, dbName);
    }

    @Bean("ordersMongoTemplate")
    MongoTemplate ordersMongoTemplate(
            @Qualifier("ordersMongoDatabaseFactory")
            MongoDatabaseFactory factory) {
        return new MongoTemplate(factory);
    }

    @Bean("auditMongoTemplate")
    MongoTemplate auditMongoTemplate(
            @Qualifier("auditMongoDatabaseFactory")
            MongoDatabaseFactory factory) {
        return new MongoTemplate(factory);
    }
}
```

Trong ví dụ:

- Hai bean `MongoClient` sở hữu hai connection pool và được Spring đóng khi application context dừng, nhờ `destroyMethod = "close"`.
- Hai `SimpleMongoClientDatabaseFactory` nhận **client đã được quản lý** và tên database. Factory không tự đóng client bên ngoài được truyền vào; vòng đời client thuộc về các bean `MongoClient`.
- Hai `MongoTemplate` dùng factory tương ứng. Tên bean là một phần của hợp đồng cấu hình: khi đổi tên phải sửa tất cả `@Qualifier` và `mongoTemplateRef` liên quan.
- `@Qualifier` loại bỏ sự mơ hồ khi context có từ hai bean cùng kiểu. Có thể thêm `@Primary` cho một nhóm mặc định nếu ứng dụng thật sự cần, nhưng repository vẫn nên trỏ bằng tên rõ ràng.

Ví dụ này cố ý không dùng `spring.data.mongodb.uri` để chỉ định cả hai kết nối. Nếu dự án đã có MongoDB auto-configuration mặc định, cần kiểm tra các bean có sẵn để tránh trùng client/template hoặc chọn nhầm đường kết nối.

## 4. Dùng một MongoClient cho nhiều database cùng cluster

Nếu `orders_db` và `audit_db` cùng nằm ở `mongodb://localhost:27017` và có thể dùng chung cơ chế xác thực, ta **không cần** `auditMongoClient` thứ hai. Thay vào đó, tạo hai factory trên cùng một client:

```java
MongoClient sharedClient = MongoClients.create("mongodb://localhost:27017");

MongoDatabaseFactory ordersFactory =
        new SimpleMongoClientDatabaseFactory(sharedClient, "orders_db");
MongoDatabaseFactory auditFactory =
        new SimpleMongoClientDatabaseFactory(sharedClient, "audit_db");

MongoTemplate ordersTemplate = new MongoTemplate(ordersFactory);
MongoTemplate auditTemplate = new MongoTemplate(auditFactory);

// Ví dụ minh họa quan hệ giữa các đối tượng.
// Trong Spring: tạo sharedClient thành @Bean singleton, rồi inject
// vào hai @Bean MongoDatabaseFactory; Spring chịu trách nhiệm close().
```

Đoạn trên minh họa cấu trúc, **không phải** một cấu hình `@Bean` hoàn chỉnh để chép thêm vào mục 3. Khi áp dụng, thay bean client/factory tương ứng trong cấu hình, bảo đảm chỉ có một chủ sở hữu đóng `sharedClient`. Không gọi `close()` sau mỗi truy vấn hoặc mỗi request.

Dùng chung client không có nghĩa hai database tự chia sẻ quyền truy cập. Database và quyền truy cập thực tế vẫn phụ thuộc vào tài khoản MongoDB trong connection string. Nếu hai database yêu cầu credentials hoặc network policy khác nhau, có thể phải dùng client riêng dù cùng cluster.

## 5. Định tuyến MongoRepository đúng database

Chỉ tạo hai template chưa đủ khi ứng dụng dùng `MongoRepository`. Cơ chế repository mặc định thường tìm bean tên `mongoTemplate` nếu không được chỉ định khác; vì vậy cần cấu hình `@EnableMongoRepositories` cho **từng package repository tách biệt**.

Giả sử cấu trúc package:

```text
com.example.multimongo
├── config
│   ├── MultiMongoConfig.java
│   ├── OrdersRepositoryConfig.java
│   └── AuditRepositoryConfig.java
├── orders
│   ├── model/OrderDoc.java
│   └── repository/OrderRepository.java
└── audit
    ├── model/AuditEventDoc.java
    └── repository/AuditEventRepository.java
```

Cấu hình repository cho database đơn hàng:

```java
package com.example.multimongo.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
        basePackages = "com.example.multimongo.orders.repository",
        mongoTemplateRef = "ordersMongoTemplate"
)
public class OrdersRepositoryConfig {
}
```

Cấu hình repository cho database kiểm toán:

```java
package com.example.multimongo.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
        basePackages = "com.example.multimongo.audit.repository",
        mongoTemplateRef = "auditMongoTemplate"
)
public class AuditRepositoryConfig {
}
```

Document và repository tối giản cho hai nhóm:

```java
// com.example.multimongo.orders.model.OrderDoc
@Document("orders")
public record OrderDoc(
        @Id String id,
        String customerId,
        long totalCents
) {}

// com.example.multimongo.orders.repository.OrderRepository
public interface OrderRepository
        extends MongoRepository<OrderDoc, String> {}

// com.example.multimongo.audit.model.AuditEventDoc
@Document("audit_events")
public record AuditEventDoc(
        @Id String id,
        String action,
        String entityId
) {}

// com.example.multimongo.audit.repository.AuditEventRepository
public interface AuditEventRepository
        extends MongoRepository<AuditEventDoc, String> {}
```

Các khai báo này là những file Java khác nhau; cần thêm import phù hợp như `org.springframework.data.annotation.Id`, `org.springframework.data.mongodb.core.mapping.Document` và `org.springframework.data.mongodb.repository.MongoRepository`.

Nhờ `mongoTemplateRef`, gọi `orderRepository.save(...)` sẽ dùng `ordersMongoTemplate`, còn `auditEventRepository.save(...)` sẽ dùng `auditMongoTemplate`. Không nên quét chung cùng một package repository trong cả hai cấu hình, vì có thể sinh bean trùng hoặc gắn nhầm template. Nếu Spring Boot đang tự quét repository, cần giới hạn hoặc tắt phần auto-scan chồng lấn theo cấu trúc ứng dụng.

## 6. Sử dụng MongoTemplate trực tiếp trong service

Không phải trường hợp nào cũng cần repository. Với truy vấn động, aggregation hoặc bulk operations, service có thể inject chính xác template:

```java
package com.example.multimongo.orders.service;

import com.example.multimongo.orders.model.OrderDoc;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {

    private final MongoTemplate orders;

    public OrderQueryService(
            @Qualifier("ordersMongoTemplate") MongoTemplate orders) {
        this.orders = orders;
    }

    public OrderDoc findById(String id) {
        return orders.findById(id, OrderDoc.class);
    }

    public OrderDoc save(OrderDoc order) {
        return orders.save(order);
    }
}
```

Để ghi audit, inject `@Qualifier("auditMongoTemplate")` vào service audit. Với hai template cùng kiểu, constructor chỉ nhận `MongoTemplate` mà không có qualifier thường gặp lỗi `NoUniqueBeanDefinitionException` (hoặc phụ thuộc `@Primary` không như mong đợi). Có thể inject interface `MongoOperations` thay vì lớp cụ thể khi chỉ cần các thao tác nghiệp vụ.

**Điểm an toàn dữ liệu:** `@Document("orders")` chỉ xác định collection, **không xác định database**. Chính template quyết định database đích. Hai database cùng có collection `orders` vẫn là hai tập dữ liệu độc lập.

## 7. Transaction và tính nhất quán

Khi một nghiệp vụ chỉ cập nhật dữ liệu trong `orders_db`, có thể khai báo `MongoTransactionManager` tương ứng với factory của đơn hàng:

```java
@Bean("ordersTransactionManager")
MongoTransactionManager ordersTransactionManager(
        @Qualifier("ordersMongoDatabaseFactory")
        MongoDatabaseFactory factory) {
    return new MongoTransactionManager(factory);
}
```

Import `org.springframework.data.mongodb.MongoTransactionManager`; đặt phương thức trên trong class `@Configuration`. Tại service:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void updateOrder(/* dữ liệu đầu vào */) {
    // Các thao tác qua ordersMongoTemplate / ordersRepository
    // tham gia transaction đã được cấu hình phù hợp.
}
```

Cần phân biệt rõ:

1. MongoDB multi-document transactions yêu cầu topology hỗ trợ transaction, chẳng hạn replica set hoặc sharded cluster; một MongoDB standalone đơn lẻ không đáp ứng yêu cầu này.
2. `MongoTransactionManager` quản lý session/transaction cho **factory tương ứng**. Nếu có cả `auditMongoDatabaseFactory`, việc tạo thêm `auditTransactionManager` không tự tạo transaction phân tán chung giữa hai manager.
3. Ghi đơn hàng ở cluster A và audit ở cluster B **không mặc nhiên atomic**. Chẳng hạn, lưu đơn hàng thành công rồi ghi audit thất bại có thể để lại hai trạng thái lệch nhau.
4. Nếu cần độ tin cậy qua nhiều cluster, cân nhắc outbox, hàng đợi, retry có idempotency, hoặc quy trình bù trừ. Khi cả hai database cùng deployment, transaction trải nhiều namespace chỉ khả thi nếu các thao tác thực sự dùng chung session/transaction được hỗ trợ; hai template/factory tách rời không tự đảm bảo điều đó.

Không đặt `@Transactional` chung chung khi ứng dụng có nhiều transaction manager và không có manager mặc định rõ ràng. Hãy khai báo bean manager theo tên, chỉ định `transactionManager` trong annotation và kiểm thử rollback thực tế với topology mong muốn.

## 8. Kiểm thử cấu hình và xác nhận kết nối

Một kiểm thử tích hợp nên xác nhận **đúng database đích** và **đúng server có thể truy cập**. Ví dụ JUnit 5 dưới đây chạy khi hai MongoDB instance trong mục 3 đã sẵn sàng:

```java
@SpringBootTest
class MultiMongoWiringTest {

    @Autowired
    @Qualifier("ordersMongoTemplate")
    MongoTemplate orders;

    @Autowired
    @Qualifier("auditMongoTemplate")
    MongoTemplate audit;

    @Test
    void templatesPointToExpectedDatabases() {
        assertEquals("orders_db", orders.getDb().getName());
        assertEquals("audit_db", audit.getDb().getName());
    }

    @Test
    void bothDeploymentsRespondToPing() {
        assertDoesNotThrow(() ->
                orders.getDb().runCommand(new org.bson.Document("ping", 1)));
        assertDoesNotThrow(() ->
                audit.getDb().runCommand(new org.bson.Document("ping", 1)));
    }
}
```

Cần import `@SpringBootTest`, `@Autowired`, `@Qualifier`, `@Test`, `MongoTemplate` và static assertions của JUnit 5. `getDb().getName()` chỉ kiểm tra cấu hình tên database, còn `runCommand(ping)` mới xác nhận kết nối đến deployment. Với môi trường CI, dùng hai MongoDB test instances hoặc Testcontainers và cấp URI động; tránh chạy smoke test phụ thuộc máy chủ production.

Kiểm thử thêm ở mức nghiệp vụ:

- Lưu một `OrderDoc` qua `ordersMongoTemplate` rồi đọc lại trong `orders_db`.
- Xác nhận dữ liệu đó không xuất hiện trong `audit_db`, ngay cả khi collection trùng tên.
- Lưu `AuditEventDoc` qua repository audit và kiểm tra bộ đếm document hoặc tra cứu trực tiếp ở `audit_db`.
- Thử quyền truy cập bị từ chối nếu credentials không có quyền ghi lên database còn lại.
- Khi dùng transaction, kiểm tra trường hợp lỗi dẫn đến rollback trong đúng phạm vi và trường hợp ghi xuyên cluster thất bại từng phần.

Kiểm tra database bằng `db.getName()` **không đủ** để chứng minh trỏ đến đúng cluster nếu hai cluster có database trùng tên. Khi cần bằng chứng đầy đủ, kiểm tra cấu hình URI trên môi trường triển khai và kết nối đến từng deployment qua ping hoặc dữ liệu đặc trưng của test.

## 9. Vận hành, hiệu năng và bảo mật

### Connection pool và vòng đời

`MongoClient` là đối tượng nặng và được thiết kế để tái sử dụng; tạo client mỗi request sẽ tăng số kết nối, số luồng giám sát và chi phí handshake. Dùng một client singleton cho mỗi cấu hình deployment/credential hợp lý, và chia sẻ client khi hai database dùng cùng cluster, cùng thông số xác thực. Theo dõi pool utilization, connection timeout, server selection timeout và lỗi kết nối theo từng client. Khi cần chỉnh pool, cấu hình nhất quán qua URI hoặc `MongoClientSettings`.

Khi factory được tạo từ `new SimpleMongoClientDatabaseFactory(existingClient, dbName)`, **client truyền vào** cần được đóng bởi chủ sở hữu của nó (trong ví dụ là Spring bean), không dựa vào factory để đóng hộ. Ngược lại, constructor nhận connection string có thể tự tạo client; khi factory sở hữu client đó, vòng đời đóng client đi theo factory. Tránh phối hợp cả hai kiểu ownership mà không có quy ước.

### Mapping, index và migration

Mỗi template mặc định có bộ thiết lập mapping riêng khi dựng trực tiếp từ factory. Nếu ứng dụng sử dụng custom converter, custom conversions, codec, naming strategy, auditing hoặc index setup, phải kiểm tra chúng có áp dụng cho từng template hay không. Không mặc định cho rằng cấu hình tùy biến của bean `mongoTemplate` chính sẽ được nhân bản sang các template tự tạo. Index, dữ liệu ban đầu và migration phải được kiểm tra trên **mỗi database đích**.

### Quyền truy cập và quan sát hệ thống

Dùng MongoDB user với quyền tối thiểu cho database cần thiết; đặt secrets ngoài source control. Khi cấu hình nhiều client, nên ghi log/metrics bằng nhãn logic như `orders` và `audit` nhưng tránh log URI có password. Kiểm soát read/write concern, timeout và retry theo SLA riêng của từng hệ thống. Khi báo lỗi, chỉ ra tên bean và database logic để khoanh vùng mà không tiết lộ credential.

### Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` khi inject MongoTemplate | Có nhiều bean cùng type | Dùng `@Qualifier`; `@Primary` chỉ khi có mặc định hợp lệ |
| Repository không khởi tạo, báo thiếu `mongoTemplate` | Không khai báo `mongoTemplateRef` khi bean mang tên khác | Chỉ định `mongoTemplateRef` cho từng nhóm repository |
| Ghi vào database không mong đợi | Package repository bị quét chồng hoặc inject sai template | Tách package, kiểm tra tên bean và tên db trong integration test |
| Số lượng socket/tài nguyên tăng | Nhiều client cùng trỏ một cluster | Tái sử dụng client chung nếu cấu hình kết nối tương thích |
| Không thể bắt đầu MongoDB transaction | MongoDB topology không hỗ trợ hoặc manager chọn sai | Dùng replica set/sharded cluster phù hợp, gắn manager đúng factory |
| Transaction thành công một phía | Hai cluster/factory độc lập | Thiết kế idempotency, outbox hoặc cơ chế phối hợp phù hợp |
| Lỗi xác thực chỉ trên database thứ hai | Sai `authSource`, credential hoặc quyền truy cập | Kiểm tra URI và role của tài khoản riêng |
| Mapping hoặc index khác kỳ vọng | Template thứ hai thiếu converter/index configuration | Áp dụng cấu hình mapping/index riêng và kiểm thử |

## 10. Checklist áp dụng vào dự án

1. Vẽ sơ đồ database → deployment → credential trước khi quyết định số lượng `MongoClient`.
2. Định danh rõ bean client, factory, template; giữ quan hệ một chiều client → factory → template.
3. Gắn từng package repository với `mongoTemplateRef`; ở service dùng `@Qualifier` khi inject template.
4. Quản lý vòng đời client bằng singleton và đóng đúng một lần lúc shutdown.
5. Gắn transaction manager với factory cụ thể và xác định ranh giới atomicity thật.
6. Kiểm thử tên database, kết nối, phân tách dữ liệu, quyền truy cập và các case lỗi xuyên database.

**Ghi nhớ:** Chọn đúng `MongoClient` quyết định deployment/credential; `MongoDatabaseFactory` quyết định database mặc định; `MongoTemplate` hoặc repository quyết định nơi thao tác của ứng dụng được thực thi. Ba mức này phải được liên kết tường minh để tránh ghi nhầm dữ liệu.

## Tài liệu tham khảo

- [Spring Data MongoDB — Connecting to MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/configuration.html)
- [MongoDatabaseFactory API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/MongoDatabaseFactory.html)
- [SimpleMongoClientDatabaseFactory API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/SimpleMongoClientDatabaseFactory.html)
- [MongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html)
- [EnableMongoRepositories API](https://docs.spring.io/spring-data/data-mongodb/reference/api/java/org/springframework/data/mongodb/repository/config/EnableMongoRepositories.html)
