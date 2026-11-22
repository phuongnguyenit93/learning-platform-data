# Tách credential, converter và transaction manager khi cần

Khi một ứng dụng **Spring Data MongoDB** làm việc với nhiều MongoDB database, thêm một tên database vào chuỗi kết nối mới chỉ giải quyết được phần định tuyến dữ liệu. Hệ thống còn phải quyết định **dùng chung hay tách thông tin đăng nhập**, **mapping converter** và **transaction manager** để dữ liệu không bị ghi nhầm, quyền truy cập không bị mở rộng ngoài ý muốn và giao dịch có phạm vi rõ ràng.

Bài học thuộc chương **Nhiều database** của `SPRING_DATA_MONGODB`. Các ví dụ sử dụng Spring Data MongoDB để ánh xạ document, truy vấn qua `MongoTemplate`/repository, quản lý index và transaction. Trọng tâm là cách cấu hình có chủ đích, kiểm chứng bằng những hành vi có thể quan sát được và nhận diện giới hạn khi hai database ở cùng hoặc khác cluster.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **MongoDB cluster**, **MongoClient**, **MongoDatabaseFactory**, **MongoTemplate**, **converter**, **repository** và **MongoTransactionManager**.
2. Chọn sử dụng chung `MongoClient` khi các database dùng cùng credential, hoặc tách client khi cần danh tính truy cập khác nhau.
3. Cấu hình hai bộ bean MongoDB với tên cụ thể và gắn repository đúng `mongoTemplateRef`.
4. Tạo `MongoCustomConversions` và `MappingMongoConverter` độc lập khi mỗi database có quy ước lưu BSON khác nhau.
5. Chọn transaction manager bằng tên trong `@Transactional`; giải thích vì sao hai manager không mặc nhiên tạo được một transaction nguyên tử.
6. Kiểm tra kết nối, quyền, serialization, database đích và rollback để tránh lỗi cấu hình âm thầm.

## 2. Hiểu đúng các lớp cách ly

Trong ứng dụng một database, Spring Boot thường tự cấu hình một `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate` và các repository tương ứng. Khi số database tăng lên, ta phải quyết định **mỗi thành phần thuộc phạm vi nào**.

```text
Ứng dụng
├── Catalog (database: catalog_db)
│   ├── catalogMongoClient       -> credential: catalog_app
│   ├── catalogDatabaseFactory    -> catalog_db
│   ├── catalogMongoConverter     -> BSON mapping riêng
│   ├── catalogMongoTemplate      -> CRUD và truy vấn catalog
│   ├── CatalogRepository         -> gắn với catalogMongoTemplate
│   └── catalogTransactionManager -> transaction của catalog
│
└── Audit (database: audit_db)
    ├── auditMongoClient          -> credential: audit_app
    ├── auditDatabaseFactory      -> audit_db
    ├── auditMongoConverter       -> BSON mapping riêng/default
    ├── auditMongoTemplate        -> CRUD và truy vấn audit
    ├── AuditRepository           -> gắn với auditMongoTemplate
    └── auditTransactionManager   -> transaction của audit
```

| Thành phần | Chịu trách nhiệm | Khi nào tách? |
| --- | --- | --- |
| `MongoClient` | Kết nối, authentication, connection pool, session | Khi URI, cụm, credential, TLS hoặc các đặc tính kết nối khác cần độc lập |
| `MongoDatabaseFactory` | Chọn database logic và tạo nguồn tương tác MongoDB cho template/transaction | Thông thường mỗi database đích có factory riêng |
| `MongoTemplate` | API CRUD, query, aggregation, index và mapping cho database | Mỗi tổ hợp database + converter cần template riêng |
| `MongoCustomConversions` | Bộ converter giữa kiểu Java và BSON | Khi hai database dùng quy tắc chuyển đổi khác nhau |
| `MappingMongoConverter` | Ánh xạ object/document, tên field, `_id`, DBRef | Khi mapping context hoặc custom conversions khác nhau |
| `MongoRepository` | Abstraction truy cập dữ liệu theo domain | Ràng buộc nhóm repository vào đúng template |
| `MongoTransactionManager` | Quản lý transaction và session thông qua MongoDB factory | Khi cần transaction theo từng phạm vi database/client |

**Phân biệt:** tên database không phải cơ chế bảo mật. `MongoDatabaseFactory(client, "catalog_db")` chỉ chọn database đích; quyền đọc/ghi do credential của kết nối và MongoDB RBAC quyết định.

## 3. Quyết định dùng chung hay tách client

Không phải hệ thống nhiều database nào cũng cần hai `MongoClient`.

| Bối cảnh | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Hai database cùng cluster, dùng cùng tài khoản và chính sách kết nối | Một `MongoClient`, hai factory/template | Tái sử dụng connection pool, tránh tăng kết nối |
| Cùng cluster nhưng mỗi database có tài khoản và quyền riêng | Hai `MongoClient`, hai factory/template | Mỗi client mang authentication riêng, thực thi least privilege |
| Hai MongoDB cluster độc lập | Hai `MongoClient`, hai factory/template | Topology, pool, credential và failure domain riêng |
| Hai database có quy ước chuyển đổi BSON giống nhau | Có thể dùng chung một số thành phần mapping được quản lý phù hợp | Giảm cấu hình, nhưng phải kiểm tra DBRef và mapping context |
| Hai database có converter, tên field hay kiểu dữ liệu khác nhau | Converter/mapping context riêng | Tránh một converter tác động tới entity thuộc database khác |
| Chỉ thao tác đơn document và không cần multi-document transaction | Không nhất thiết tạo transaction manager | Ghi một document đã có tính atomic trong phạm vi document |
| Hai luồng nghiệp vụ cần transaction độc lập | Hai manager đặt tên tường minh | Tránh chọn nhầm transaction manager |

Khi hai MongoClient dùng cùng cluster nhưng hai credential khác nhau, MongoDB không thể tự động chuyển tài khoản của một MongoClient từ request này sang request khác. Tách client là lựa chọn rõ ràng và dễ kiểm soát.

### 3.1. `authSource` khác database thao tác

Ví dụ URI có thể mang thông tin:

```text
mongodb://catalog_app:***@mongo-a:27017,mongo-b:27017/
  ?replicaSet=rs0&authSource=admin&tls=true
```

- `authSource=admin`: database MongoDB lưu thông tin xác thực của `catalog_app`, **không** phải database tự động được phép ghi.
- `catalog_db`: database nghiệp vụ được chọn khi tạo `MongoDatabaseFactory`.
- Roles như `readWrite` trên `catalog_db` là thứ cho phép thao tác. Tài khoản có `readWrite` trên một database không mặc nhiên có quyền trên database khác.

Đặt secrets trong biến môi trường hoặc secret manager. Không commit URI chứa username/password và không ghi URI nguyên văn vào log. Khi dùng URL encoding cho mật khẩu trong URI, cần đảm bảo ký tự đặc biệt được mã hóa đúng.

## 4. Cấu hình hai database bằng Spring Boot và Spring Data MongoDB

Xét một hệ thống quản lý đơn hàng:

- `catalog_db` lưu `orders`, phải đọc/ghi dữ liệu nghiệp vụ và sử dụng kiểu giá tiền `Amount`.
- `audit_db` lưu `audit_events`, chủ yếu append/audit, có cách ánh xạ entity đơn giản.
- Mỗi database có credential riêng. Ví dụ sử dụng **hai MongoClient singleton**.

Các đoạn Java bên dưới minh họa mô hình Spring Data MongoDB dùng **imperative driver**, Java 17+ và Spring Boot/Spring Data tương ứng. Với API khác phiên bản, đối chiếu chữ ký constructor và cấu hình auto-configuration của bản dự án.

### 4.1. Khai báo URI và tên database

```yaml
# application.yml
app:
  mongo:
    catalog:
      uri: ${CATALOG_MONGODB_URI}
      database: catalog_db
    audit:
      uri: ${AUDIT_MONGODB_URI}
      database: audit_db
```

Biến môi trường triển khai chứa URI thật, với credential có quyền phù hợp và TLS/replica-set options cần thiết. Không sử dụng một URI mặc định trỏ tới `admin` rồi suy luận nó có thể ghi vào mọi database.

Khi tự khai báo nhiều `MongoClient` và `MongoTemplate`, hãy kiểm tra Spring Boot có còn tự tạo bean MongoDB mặc định nào không. Những bean dư hoặc tên trùng có thể khiến `@Autowired` không xác định được nguồn, hoặc khiến repository trỏ nhầm database. Ví dụ bên dưới sử dụng `@Qualifier` và `mongoTemplateRef` có chủ đích.

### 4.2. Model và converter riêng cho catalog

Catalog lưu kiểu giá tiền `Amount` dưới BSON `Decimal128`. Thay vì để `Amount` được ánh xạ thành document con như `{value: ...}`, ta dùng hai custom converter.

```java
// com.example.catalog.model.Amount
package com.example.catalog.model;

import java.math.BigDecimal;

public record Amount(BigDecimal value) {}
```

Hai converter (đặt trong package cấu hình catalog):

```java
package com.example.catalog.config;

import com.example.catalog.model.Amount;
import java.math.BigDecimal;
import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class AmountWriteConverter
        implements Converter<Amount, Decimal128> {

    @Override
    public Decimal128 convert(Amount amount) {
        return new Decimal128(amount.value());
    }
}
```

```java
package com.example.catalog.config;

import com.example.catalog.model.Amount;
import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class AmountReadConverter
        implements Converter<Decimal128, Amount> {

    @Override
    public Amount convert(Decimal128 value) {
        return new Amount(value.bigDecimalValue());
    }
}
```

`@WritingConverter`/`@ReadingConverter` giúp Spring Data nhận diện chiều chuyển đổi, nhất là khi các kiểu nguồn/đích đều có thể xuất hiện trong MongoDB mapping. Vì chúng được đăng ký riêng cho catalog, các field kiểu tương tự trong audit sẽ không bất ngờ chịu cùng quy tắc lưu BSON.

### 4.3. Bộ bean catalog

```java
package com.example.catalog.config;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;
import org.springframework.data.mongodb.core.convert.DefaultDbRefResolver;
import org.springframework.data.mongodb.core.convert.MappingMongoConverter;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
    basePackages = "com.example.catalog.repository",
    mongoTemplateRef = "catalogMongoTemplate"
)
public class CatalogMongoConfig {

    @Bean(name = "catalogMongoClient", destroyMethod = "close")
    MongoClient catalogMongoClient(
            @Value("${app.mongo.catalog.uri}") String uri) {
        return MongoClients.create(uri);
    }

    @Bean("catalogDatabaseFactory")
    MongoDatabaseFactory catalogDatabaseFactory(
            @Qualifier("catalogMongoClient") MongoClient client,
            @Value("${app.mongo.catalog.database}") String database) {
        return new SimpleMongoClientDatabaseFactory(client, database);
    }

    @Bean("catalogConversions")
    MongoCustomConversions catalogConversions() {
        return new MongoCustomConversions(List.of(
            new AmountWriteConverter(),
            new AmountReadConverter()
        ));
    }

    @Bean("catalogMappingContext")
    MongoMappingContext catalogMappingContext(
            @Qualifier("catalogConversions")
            MongoCustomConversions conversions) {
        MongoMappingContext context = new MongoMappingContext();
        context.setSimpleTypeHolder(conversions.getSimpleTypeHolder());
        return context;
    }

    @Bean("catalogMongoConverter")
    MappingMongoConverter catalogMongoConverter(
            @Qualifier("catalogDatabaseFactory")
            MongoDatabaseFactory factory,
            @Qualifier("catalogMappingContext")
            MongoMappingContext context,
            @Qualifier("catalogConversions")
            MongoCustomConversions conversions) {

        MappingMongoConverter converter = new MappingMongoConverter(
            new DefaultDbRefResolver(factory), context
        );
        converter.setCustomConversions(conversions);
        return converter;
    }

    @Bean("catalogMongoTemplate")
    MongoTemplate catalogMongoTemplate(
            @Qualifier("catalogDatabaseFactory")
            MongoDatabaseFactory factory,
            @Qualifier("catalogMongoConverter")
            MappingMongoConverter converter) {
        return new MongoTemplate(factory, converter);
    }

    @Bean("catalogTransactionManager")
    MongoTransactionManager catalogTransactionManager(
            @Qualifier("catalogDatabaseFactory")
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

Những điểm quan trọng của wiring:

- `catalogMongoClient` sở hữu kết nối và credential. Đây là bean singleton, sẽ được đóng khi application context kết thúc.
- `catalogDatabaseFactory` được gắn chính xác với client và tên database `catalog_db`.
- `catalogMongoConverter` dùng **catalogConversions** và **catalogMappingContext**. Không tiêm nhầm converter mặc định của database khác.
- `catalogMongoTemplate` dùng cùng factory và converter vừa khai báo.
- `catalogTransactionManager` dùng **cùng factory** với template, giúp session được quản lý đúng phạm vi khi chạy transaction.
- `@EnableMongoRepositories` chỉ quét package repository của catalog, và `mongoTemplateRef` trỏ đúng template.

Việc tạo converter riêng mang lại tính chủ động nhưng cũng cần đồng bộ cấu hình mapping, custom conversions và xử lý index. Nếu ứng dụng có cấu hình mapping đặc thù (naming strategy, metadata, type mapper, DBRef, conversions), không copy converter cũ sang template mới mà bỏ qua sự khác biệt.

### 4.4. Bộ bean audit

Audit không cần converter `Amount` của catalog. Ở đây ta vẫn tạo converter độc lập, với bộ custom conversion rỗng; về sau audit có thể đăng ký những converter chuyên cho schema audit.

```java
package com.example.audit.config;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;
import org.springframework.data.mongodb.core.convert.DefaultDbRefResolver;
import org.springframework.data.mongodb.core.convert.MappingMongoConverter;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
    basePackages = "com.example.audit.repository",
    mongoTemplateRef = "auditMongoTemplate"
)
public class AuditMongoConfig {

    @Bean(name = "auditMongoClient", destroyMethod = "close")
    MongoClient auditMongoClient(
            @Value("${app.mongo.audit.uri}") String uri) {
        return MongoClients.create(uri);
    }

    @Bean("auditDatabaseFactory")
    MongoDatabaseFactory auditDatabaseFactory(
            @Qualifier("auditMongoClient") MongoClient client,
            @Value("${app.mongo.audit.database}") String database) {
        return new SimpleMongoClientDatabaseFactory(client, database);
    }

    @Bean("auditConversions")
    MongoCustomConversions auditConversions() {
        return new MongoCustomConversions(List.of());
    }

    @Bean("auditMappingContext")
    MongoMappingContext auditMappingContext(
            @Qualifier("auditConversions")
            MongoCustomConversions conversions) {
        MongoMappingContext context = new MongoMappingContext();
        context.setSimpleTypeHolder(conversions.getSimpleTypeHolder());
        return context;
    }

    @Bean("auditMongoConverter")
    MappingMongoConverter auditMongoConverter(
            @Qualifier("auditDatabaseFactory")
            MongoDatabaseFactory factory,
            @Qualifier("auditMappingContext")
            MongoMappingContext context,
            @Qualifier("auditConversions")
            MongoCustomConversions conversions) {

        MappingMongoConverter converter = new MappingMongoConverter(
            new DefaultDbRefResolver(factory), context
        );
        converter.setCustomConversions(conversions);
        return converter;
    }

    @Bean("auditMongoTemplate")
    MongoTemplate auditMongoTemplate(
            @Qualifier("auditDatabaseFactory")
            MongoDatabaseFactory factory,
            @Qualifier("auditMongoConverter")
            MappingMongoConverter converter) {
        return new MongoTemplate(factory, converter);
    }

    @Bean("auditTransactionManager")
    MongoTransactionManager auditTransactionManager(
            @Qualifier("auditDatabaseFactory")
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

**Không tạo hai MongoClient chỉ để dùng hai tên database**, nếu cùng cluster, cùng danh tính và cùng cấu hình kết nối. Khi đó, có thể giữ **một client** rồi khai báo hai `SimpleMongoClientDatabaseFactory(client, databaseName)`, hai template và chỉ những converter/transaction manager thực sự cần thiết.

### 4.5. Biến thể dùng chung một MongoClient

Nếu catalog và audit cùng cluster, cùng tài khoản được cấp quyền trên cả hai database và cùng tham số kết nối:

```java
@Bean(name = "sharedMongoClient", destroyMethod = "close")
MongoClient sharedMongoClient(
        @Value("${app.mongo.shared.uri}") String uri) {
    return MongoClients.create(uri);
}

@Bean("catalogDatabaseFactory")
MongoDatabaseFactory catalogDatabaseFactory(
        @Qualifier("sharedMongoClient") MongoClient client) {
    return new SimpleMongoClientDatabaseFactory(client, "catalog_db");
}

@Bean("auditDatabaseFactory")
MongoDatabaseFactory auditDatabaseFactory(
        @Qualifier("sharedMongoClient") MongoClient client) {
    return new SimpleMongoClientDatabaseFactory(client, "audit_db");
}
```

Đây là **biến thể thay thế** hai phương thức tạo MongoClient và hai factory ở trên; không khai báo đồng thời các bean trùng tên trong cùng ứng dụng. Hai factory vẫn tách biệt về database mặc định, trong khi client chung dùng cùng pool và cùng credential. Chia sẻ client **không đồng nghĩa** mọi transaction qua hai factory tự liên kết thành một transaction.

## 5. Định tuyến repository và MongoTemplate chính xác

### 5.1. Hai nhóm entity và repository

Ví dụ tối giản entity catalog:

```java
package com.example.catalog.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class CatalogOrder {

    @Id
    private String id;

    private Amount amount;
    private String status;

    // Constructors, getters, setters...
}
```

```java
package com.example.catalog.repository;

import com.example.catalog.model.CatalogOrder;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogOrderRepository
        extends MongoRepository<CatalogOrder, String> {
}
```

Entity và repository audit:

```java
package com.example.audit.model;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("audit_events")
public class AuditEvent {

    @Id
    private String id;

    private String action;
    private Instant createdAt;

    // Constructors, getters, setters...
}
```

```java
package com.example.audit.repository;

import com.example.audit.model.AuditEvent;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AuditEventRepository
        extends MongoRepository<AuditEvent, String> {
}
```

Vì hai cấu hình ở mục trước dùng hai `basePackages` **không giao nhau**, mỗi repository được liên kết đúng `MongoTemplate`. `@Document(collection = ...)` chỉ chỉ định **collection**, không tự chọn MongoDB database hoặc MongoClient.

### 5.2. Tiêm `MongoTemplate` bằng `@Qualifier`

```java
package com.example.reporting;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class DataDiagnosticsService {

    private final MongoTemplate catalog;
    private final MongoTemplate audit;

    public DataDiagnosticsService(
            @Qualifier("catalogMongoTemplate")
            MongoTemplate catalog,
            @Qualifier("auditMongoTemplate")
            MongoTemplate audit) {
        this.catalog = catalog;
        this.audit = audit;
    }

    public String describeTargets() {
        return "Catalog=" + catalog.getDb().getName()
             + ", Audit=" + audit.getDb().getName();
    }
}
```

Dòng kết quả mong đợi là `Catalog=catalog_db, Audit=audit_db`. Nếu thấy hai tên giống nhau, phải kiểm tra lại factory hoặc properties ngay.

Khi trong context có nhiều `MongoTemplate` hoặc `MongoDatabaseFactory`, không tiêm bằng type đơn thuần:

```java
// Không rõ bean nào được chọn khi có nhiều MongoTemplate:
// public SomeService(MongoTemplate template) { ... }
```

Có thể đặt `@Primary` cho một bean thật sự là mặc định. Tuy nhiên, **tên rõ ràng và `@Qualifier`** thường phù hợp hơn tại các lớp xử lý dữ liệu nhạy cảm hoặc hệ thống có nhiều database ngang hàng.

## 6. Converter: cách ly quy ước BSON theo database

### 6.1. Converter tác động lên biểu diễn dữ liệu

Một `MappingMongoConverter` quyết định cách Java object thành BSON `Document` và ngược lại. Ví dụ:

| Domain field | Catalog với custom conversion | Audit với mapping mặc định/riêng |
| --- | --- | --- |
| `Amount(BigDecimal)` | Lưu như BSON `Decimal128` | Không nhất thiết tồn tại kiểu này |
| `Instant` | Theo quy ước date/time đã chọn | Có thể dùng quy ước UTC khác hoặc định dạng legacy |
| `@Field("...")` | Theo annotation/entity catalog | Theo entity audit |
| `@Id` | Ánh xạ ID của entity catalog | Ánh xạ ID của entity audit |
| DBRef và target database | Cần resolver/factory tương ứng | Cần resolver/factory tương ứng |

Nếu vô tình dùng `catalogMongoConverter` cho `auditMongoTemplate`, các custom converter catalog có thể áp dụng cho audit. Nguy cơ rõ hơn khi một converter dành cho kiểu phổ biến như `String` hoặc `Date`: nó có thể làm thay đổi rất nhiều field không liên quan.

### 6.2. Đồng bộ conversions với mapping context

Điểm dễ bỏ sót trong cấu hình thủ công là `MongoMappingContext` cũng cần hiểu kiểu nào được coi là **simple type**. Trong ví dụ:

```java
MongoCustomConversions conversions = new MongoCustomConversions(
    List.of(new AmountWriteConverter(), new AmountReadConverter())
);

MongoMappingContext context = new MongoMappingContext();
context.setSimpleTypeHolder(conversions.getSimpleTypeHolder());

MappingMongoConverter converter =
    new MappingMongoConverter(new DefaultDbRefResolver(factory), context);
converter.setCustomConversions(conversions);
```

Nếu chỉ đăng ký custom conversions lên converter mà bỏ qua mapping context, việc khám phá/ánh xạ kiểu phức hợp có thể không nhất quán. Với cấu hình chính thức, hãy giữ context, custom conversions và converter tương thích.

### 6.3. Khi nào có thể dùng chung converter?

Chỉ cân nhắc chia sẻ converter khi:

- Cả hai database có cùng schema conventions, custom conversions, naming và type mapping.
- Những tham chiếu DBRef không phụ thuộc factory đích hoặc đã có cách giải quyết rõ ràng.
- Đã thử đọc/ghi đúng hai loại entity và xác nhận không có tác động chéo.
- Một thay đổi converter của database A sẽ được xem xét tác động tới database B.

Ngay cả khi giống nhau, cấu hình converter **riêng** thường dễ kiểm soát hơn đối với hai bounded context phát triển độc lập. Ngược lại, tách converter chỉ vì có hai tên database có thể làm tăng code cấu hình mà không đem lại lợi ích nghiệp vụ.

### 6.4. Tránh tự động tạo index chồng chéo

Hai template có thể quản lý hai collection cùng tên (chẳng hạn mỗi database đều có `orders`), nhưng đó là **hai namespace khác nhau**. `indexOps` cần được gọi trên template đích:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

catalogMongoTemplate.indexOps("orders")
    .ensureIndex(new Index().on("status", Sort.Direction.ASC));

auditMongoTemplate.indexOps("audit_events")
    .ensureIndex(new Index().on("createdAt", Sort.Direction.DESC));
```

Spring Data MongoDB không bảo đảm mọi cấu hình sẽ tự tạo index trong production. Khi yêu cầu index thuộc kiểm soát migration, hãy dùng script/step triển khai rõ ràng và kiểm tra index tại database tương ứng.

## 7. Transaction manager: tách đúng phạm vi giao dịch

### 7.1. Một MongoTransactionManager gắn với factory nào?

`MongoTransactionManager` quản lý transaction bằng MongoDB `ClientSession` thông qua `MongoDatabaseFactory`. `MongoTemplate` tham gia transaction do Spring quản lý khi factory/session của thao tác tương thích với tài nguyên được liên kết vào transaction context.

Trong ví dụ, ta có:

```java
@Bean("catalogTransactionManager")
MongoTransactionManager catalogTransactionManager(
        @Qualifier("catalogDatabaseFactory")
        MongoDatabaseFactory catalogFactory) {
    return new MongoTransactionManager(catalogFactory);
}

@Bean("auditTransactionManager")
MongoTransactionManager auditTransactionManager(
        @Qualifier("auditDatabaseFactory")
        MongoDatabaseFactory auditFactory) {
    return new MongoTransactionManager(auditFactory);
}
```

Hai manager trên làm rõ transaction nào thuộc catalog và transaction nào thuộc audit. Chúng **không** tự phối hợp commit/rollback thành một distributed transaction chung.

Nếu ứng dụng cần multi-document transactions, MongoDB deployment phải hỗ trợ (replica set hoặc sharded cluster phù hợp). Một standalone `mongod` không phải môi trường thay thế tương đương cho kiểm thử transaction.

### 7.2. Chọn manager bằng `@Transactional`

```java
package com.example.catalog.service;

import com.example.catalog.repository.CatalogOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogOrderService {

    private final CatalogOrderRepository orders;

    public CatalogOrderService(CatalogOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(transactionManager = "catalogTransactionManager")
    public void saveCatalogOrder(CatalogOrder order) {
        orders.save(order);

        // Có thể thêm các thao tác catalog khác trong cùng transaction.
    }
}
```

Ví dụ dịch vụ audit:

```java
package com.example.audit.service;

import com.example.audit.repository.AuditEventRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditEventService {

    private final AuditEventRepository events;

    public AuditEventService(AuditEventRepository events) {
        this.events = events;
    }

    @Transactional(transactionManager = "auditTransactionManager")
    public void appendEvent(AuditEvent event) {
        events.save(event);
    }
}
```

Trong code thực tế, thêm import `CatalogOrder` hoặc `AuditEvent` từ đúng package model. Nếu hai transaction manager cùng tồn tại và một method chỉ ghi `@Transactional` mà không nêu manager, Spring cần có cơ chế chọn manager mặc định; nếu không, việc resolve bean có thể thất bại hoặc chọn không đúng như dự kiến.

**Điều kiện hoạt động:** Spring transaction proxy không intercept lời gọi nội bộ kiểu `this.saveCatalogOrder(...)` trong cùng instance. Hãy gọi method transactional qua bean Spring, kiểm soát transaction manager được chọn và đặt xử lý exception hợp lý.

### 7.3. Transaction của catalog không bao trùm audit

Xét luồng:

```java
@Transactional(transactionManager = "catalogTransactionManager")
public void processOrder(CatalogOrder order, AuditEvent event) {
    catalogOrderRepository.save(order);
    auditEventRepository.save(event);
}
```

Với **hai MongoClient/factory/transaction manager riêng** như cấu hình ở trên, phần `catalogOrderRepository` có thể tham gia transaction catalog, còn lời gọi `auditEventRepository` **không mặc nhiên dùng cùng MongoDB session hoặc cùng transaction**.

Nếu lưu audit thành công rồi catalog bị rollback, có thể còn audit không tương ứng; hoặc ngược lại. Không thể kết luận cả hai là atomic chỉ vì cùng method mang `@Transactional`.

Ngay cả khi hai database nằm trên cùng MongoDB cluster, hai template được cấu hình với **hai factory khác nhau** cũng không tự động tham gia cùng transaction của một factory. MongoDB có hỗ trợ transaction chạm nhiều collection/database **trong cùng triển khai phù hợp** khi dùng **cùng session**; muốn làm vậy phải thiết kế rõ cách chia sẻ session/factory hoặc sử dụng API session/transaction thích hợp, và kiểm thử end-to-end. Với **hai cluster độc lập**, một MongoDB transaction không commit nguyên tử trên cả hai cluster.

### 7.4. Khi cần nhất quán giữa nhiều database

Nếu muốn ghi một đơn hàng và phát sinh audit/log ở database khác:

- **Hai bước độc lập:** chấp nhận nhất quán cuối cùng và retry/idempotency có kiểm soát, nếu nghiệp vụ cho phép.
- **Transactional outbox:** lưu đơn hàng và một bản ghi outbox vào **cùng transaction catalog**; tiến trình khác đọc outbox, ghi audit và đánh dấu trạng thái chuyển giao. Phần ghi audit cần xử lý idempotent vì một sự kiện có thể được gửi lại.
- **Cùng cluster, cùng session:** nếu bắt buộc atomic trên nhiều database, thiết kế/kiểm thử transaction MongoDB xuyên database với một session phù hợp, thay vì giả định hai transaction manager tự liên kết.
- **Hai cluster:** dùng thiết kế saga/compensating action hoặc outbox; đừng coi `ChainedTransactionManager` hay gọi hai commit liên tiếp là một distributed transaction atomic.

Một luồng outbox đơn giản:

```mermaid
flowchart LR
    A["HTTP Create Order"] --> B["Catalog Transaction"]
    B --> C["Lưu order"]
    B --> D["Lưu outbox event"]
    D --> E["Outbox publisher"]
    E --> F["Audit database"]
    F --> G["Ghi idempotent theo eventId"]
```

Bước lưu `order` và `outbox` phải đi cùng catalog transaction. Việc chuyển event sang audit là bước sau, có retry và xử lý trùng rõ ràng.

## 8. Quyền truy cập và vận hành nhiều MongoClient

### 8.1. Least privilege theo database

Thiết kế vai trò tối thiểu:

| Tài khoản | Database được truy cập | Ví dụ quyền |
| --- | --- | --- |
| `catalog_app` | `catalog_db` | `readWrite` nếu nghiệp vụ cần cả đọc/ghi |
| `audit_app` | `audit_db` | Quyền insert/read phù hợp chính sách audit |
| Migration/admin | Các namespace cần thay đổi schema/index | Quyền riêng cho quản trị, không dùng chung credential với ứng dụng |

`MongoTemplate` chỉ chọn database **theo logic ứng dụng**; nếu tài khoản có quyền quá rộng, lỗi tiêm nhầm template vẫn có thể ghi sai database mà không bị server chặn. Vì vậy **bean names đúng** và **RBAC đúng** bổ sung cho nhau.

Credential riêng cũng có nghĩa việc rotate secret của catalog không bắt buộc ảnh hưởng audit, nhưng hai connection pool riêng làm tăng số kết nối mà cluster phải duy trì. Theo dõi số connection, pool exhaustion, timeout và ảnh hưởng của lỗi một cluster đến các request sử dụng cluster còn lại.

### 8.2. Lifecycle và connection pool

- `MongoClient` là thành phần thread-safe, được thiết kế để **tái sử dụng**. Không tạo client mới mỗi request hoặc mỗi repository operation.
- Khai báo bean singleton và để Spring đóng khi dừng ứng dụng (`destroyMethod = "close"`).
- Khi dùng chung cluster/credential, chia sẻ client thường giảm số pool và sockets.
- Hai client riêng có pool, topology monitoring và connection limits riêng. Cấu hình max pool size, timeouts, TLS và retries theo workload, không sao chép giá trị tùy tiện.
- Khi một database không khả dụng, thiết kế timeout/circuit breaker phù hợp để tránh làm nghẽn toàn bộ ứng dụng.

### 8.3. Cấu hình tránh nhầm routing

Một checklist khi mở thêm database:

1. Đặt tên rõ `catalogMongoClient`, `catalogDatabaseFactory`, `catalogMongoConverter`, `catalogMongoTemplate`, `catalogTransactionManager`.
2. Làm tương tự cho audit, tránh trùng tên bean.
3. Dùng `@Qualifier` trên constructor và `mongoTemplateRef` trên `@EnableMongoRepositories`.
4. Không quét trùng repository giữa hai configuration classes.
5. Kiểm tra `@Document` trỏ đúng collection và converter của entity phù hợp.
6. Không dựa vào `spring.data.mongodb.database` mặc định nếu đã có hai factory riêng.
7. Kiểm tra RBAC bằng đúng credential triển khai.
8. Nếu có transaction, gắn transaction manager đúng factory và triển khai trên MongoDB hỗ trợ transactions.

## 9. Kiểm thử cấu hình và chẩn đoán lỗi

### 9.1. Smoke test đúng database và converter

Một bài kiểm tra tích hợp có thể nhận cả hai template bằng qualifier, sau đó so tên database:

```java
@SpringBootTest
class MongoWiringTest {

    @Autowired
    @Qualifier("catalogMongoTemplate")
    MongoTemplate catalog;

    @Autowired
    @Qualifier("auditMongoTemplate")
    MongoTemplate audit;

    @Test
    void templatesPointToDifferentDatabases() {
        assertThat(catalog.getDb().getName()).isEqualTo("catalog_db");
        assertThat(audit.getDb().getName()).isEqualTo("audit_db");
        assertThat(catalog.getConverter())
            .isNotSameAs(audit.getConverter());
    }
}
```

Đây là khung kiểm tra (cần bổ sung import JUnit/AssertJ và cấu hình URI của môi trường test). Nếu dùng biến thể một client, vẫn kiểm tra hai database khác nhau; không yêu cầu hai MongoClient khác nhau.

Tiếp theo, chạy một integration test trên hai MongoDB database thực nghiệm:

- Ghi `CatalogOrder` có `Amount(new BigDecimal("12.34"))` bằng catalog repository.
- Đọc bản ghi BSON và xác nhận field amount là `Decimal128`.
- Ghi và đọc `AuditEvent` trên `audit_db`, xác nhận không phụ thuộc converter catalog.
- Dùng credential catalog thử thao tác trực tiếp vào audit (trong môi trường test được phân quyền riêng), kỳ vọng bị từ chối nếu RBAC đúng.
- Tạo hai thao tác catalog trong một transaction, cố ý phát sinh lỗi và xác nhận rollback; lặp lại độc lập với transaction audit nếu tính năng được sử dụng.
- Không giả định một exception sau khi ghi audit sẽ rollback audit khi transaction manager chỉ dành cho catalog.

### 9.2. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` với `MongoTemplate` | Hai template cùng type, thiếu qualifier/default | Đặt tên bean và `@Qualifier` rõ ràng |
| Repository lưu nhầm database | Package scan overlap hoặc `mongoTemplateRef` sai | Tách package và kiểm tra mapping repository-template |
| `MongoSecurityException` / unauthorized | Credential/`authSource`/MongoDB role không phù hợp | Kiểm tra URI, role theo database, cơ chế secret |
| `ConverterNotFoundException` hoặc BSON không đúng schema | Dùng nhầm converter hoặc thiếu custom conversions | Kiểm tra converter bean, reading/writing converters, mapping context |
| Field tiền bị lưu dưới nested document | Converter `Amount → Decimal128` chưa được áp dụng | Kiểm tra đăng ký converter và dữ liệu BSON thật |
| `NoSuchBeanDefinitionException` cho transaction manager | Tên trong `@Transactional` sai hoặc chưa tạo bean | Tạo đúng `MongoTransactionManager`, kiểm tra context |
| Transaction bị từ chối | Standalone mongod, phiên bản/topology không hỗ trợ hoặc session cấu hình sai | Dùng replica set/sharded cluster hỗ trợ transactions và kết nối đúng |
| Một database rollback nhưng database khác vẫn ghi | Hai factory/transaction khác nhau, không có shared session | Thiết kế lại atomicity, dùng session chung khi phù hợp hoặc outbox |
| Số connection tăng mạnh | Mỗi request tạo MongoClient hoặc khai báo quá nhiều pool | Reuse singleton, chia sẻ client nếu cùng credential |
| Query chậm bất thường | Routing đúng database nhưng index không được tạo cho namespace đó | Kiểm tra `indexOps` và `explain("executionStats")` trên đúng database |

### 9.3. Quan sát trong `mongosh`

Đăng nhập bằng tài khoản đúng môi trường (không ghi secret vào câu lệnh được lưu trong lịch sử shell nếu có thể), rồi kiểm tra database/collection/index riêng:

```javascript
use catalog_db

db.getName();
db.orders.getIndexes();
db.orders.find({ status: "NEW" }).explain("executionStats");
```

Và tương tự:

```javascript
use audit_db

db.getName();
db.audit_events.getIndexes();
db.audit_events.find().sort({ createdAt: -1 }).limit(5);
```

Khi ứng dụng log tên database đích để chẩn đoán, chỉ log tên logical database, bean/operation và thời gian xử lý; không log URI có credential, token hay nội dung document nhạy cảm.

## 10. Reactive, repository và những khác biệt cần lưu ý

Các ví dụ trong bài dùng **imperative** `MongoTemplate` và `MongoTransactionManager`. Nếu ứng dụng dùng **Reactive Spring Data MongoDB** thì bộ loại bean khác:

- Driver reactive dùng `com.mongodb.reactivestreams.client.MongoClient`.
- Data access dùng `ReactiveMongoTemplate` và `ReactiveMongoDatabaseFactory`.
- Transaction dùng `ReactiveMongoTransactionManager`, gắn với **Reactor Context** thay vì thread-bound transaction của imperative stack.
- Repository dùng `@EnableReactiveMongoRepositories` và cấu hình reactive template tương ứng.

Không lấy `MongoTransactionManager` của imperative template dùng chung cho reactive pipeline. Nếu có cả hai stack, tách rõ scope và transaction context của mỗi stack.

Tương tự, với nhiều repository modules, đừng mở rộng `basePackages` quá rộng. Một package được scan bởi hai `@EnableMongoRepositories` có thể tạo bean trùng hoặc gắn nhầm MongoTemplate.

## 11. Bài tập tình huống

### Tình huống A: Cùng cluster, cùng tài khoản

Ứng dụng báo cáo đọc `sales_db` và `customer_db`, cùng một MongoDB user có quyền read. Dùng **một MongoClient**, tạo **hai MongoDatabaseFactory** và template trỏ đúng database, chỉ tạo converter riêng nếu quy ước ánh xạ khác nhau.

### Tình huống B: Hai credential riêng

Hệ thống đơn hàng lưu trong `orders_db`, audit log cần tài khoản ít quyền hơn ở `audit_db`. Dùng **hai MongoClient** với URI lấy từ secret manager, hai factory, hai template, hai tập repository. Kiểm tra rằng credential orders không thể tự ghi audit nếu chính sách yêu cầu tách quyền.

### Tình huống C: Audit yêu cầu BSON format khác

Database A lưu tiền dưới `Decimal128`, database B nhận tài liệu JSON từ hệ thống legacy với field date dạng chuỗi. Tạo **MongoCustomConversions/MappingMongoConverter riêng** cho hai domain, viết test đọc/ghi qua đúng template và kiểm tra giá trị BSON thực tế.

### Tình huống D: Muốn rollback order và audit cùng lúc

Hai service dùng hai transaction manager riêng, một service ghi đơn hàng rồi service khác ghi audit. `@Transactional("catalogTransactionManager")` **không bảo đảm** hai phần cùng rollback. Nếu cùng cluster và thực sự cần atomic xuyên database, thiết kế dùng cùng MongoDB session phù hợp; nếu khác cluster hoặc chấp nhận eventual consistency, dùng **transactional outbox** cùng idempotency.

### Tình huống E: Thêm một database thứ ba

Trước khi copy cấu hình, trả lời:

1. Database mới có credential/cluster khác không?
2. Schema conversion có khác không?
3. Repository package nào sở hữu?
4. Nghiệp vụ cần transaction nhiều document không?
5. Có thao tác nào đòi transaction xuyên database không?
6. Cần index, giám sát và giới hạn pool nào?

Trả lời những câu hỏi này sẽ quyết định phần nào của cấu hình cần nhân thêm và phần nào có thể dùng chung.

## 12. Checklist triển khai

| Hạng mục | Cần xác nhận |
| --- | --- |
| Connection | URI đúng môi trường, TLS/replica set options, secret không lộ |
| Authentication | `authSource` đúng, role đủ nhưng tối thiểu |
| Factory | DatabaseName đúng, client tương ứng đúng credential |
| Template | Đúng factory và converter |
| Repository | Package scan tách biệt, `mongoTemplateRef` chính xác |
| Conversion | Custom conversions và simple type holder đồng bộ, BSON round trip đúng |
| Transaction | Manager tương ứng factory, không nhầm atomicity giữa hai scope |
| Auto-configuration | Không có MongoClient/template/repository default gây nhiễu |
| Data correctness | Test ghi/đọc và rollback trên đúng database |
| Production | Quan sát connection pool, index, retry, timeout và lỗi từng database |

Quy tắc thực hành cốt lõi là **tách theo ranh giới thực sự khác nhau**: credential theo quyền, factory theo database đích, converter theo quy ước BSON và transaction manager theo phạm vi session/transaction. Mọi `MongoTemplate` và repository phải liên kết rõ ràng với tổ hợp đó.

## Tài liệu tham khảo

- Spring Data MongoDB Reference — [Connecting to MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/configuration.html)
- Spring Data MongoDB Reference — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- Spring Data MongoDB Reference — [Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html)
- Spring Data MongoDB Reference — [MongoDB Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html)
- Spring Data MongoDB Reference — [Client Session Support and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- MongoDB Manual — [Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- MongoDB Manual — [Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
