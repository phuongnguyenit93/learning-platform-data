# Đăng ký MongoTransactionManager và bật quản lý giao dịch

## 1. Tại sao phải đăng ký transaction manager?

Trong chương **Session và giao dịch** của **Spring Data MongoDB**, ứng dụng có thể thao tác MongoDB bằng `MongoTemplate` hoặc repository. MongoDB bảo đảm một thao tác ghi lên **một document** là nguyên tử; tuy nhiên nghiệp vụ đôi khi bắt buộc nhiều document phải **cùng commit hoặc cùng rollback**.

Ví dụ hệ thống chuyển một số tiền từ tài khoản A sang B, hai tài khoản được lưu trong hai document:

~~~text
Trước chuyển:
  Account A = 100.000 VND
  Account B =  20.000 VND

Thao tác:
  1. Trừ A 30.000 VND
  2. Cộng B 30.000 VND

Sau chuyển:
  Account A =  70.000 VND
  Account B =  50.000 VND
  Tổng vẫn = 120.000 VND
~~~

Nếu gọi hai `updateFirst` riêng lẻ, chương trình có thể bị kill sau bước trừ A nhưng trước bước cộng B. **Mỗi update nguyên tử riêng không có nghĩa cả hai update nguyên tử cùng nhau**. Để yêu cầu cả hai document tham gia một transaction MongoDB, ứng dụng Spring cần:

1. **MongoDB topology hỗ trợ transaction**.
2. Một `MongoDatabaseFactory` kết nối đúng MongoDB/database.
3. Một bean `MongoTransactionManager` gắn với database factory đó.
4. Hạ tầng transaction interception của Spring, ví dụ `@EnableTransactionManagement` và lời gọi `@Transactional` đi qua Spring proxy.
5. Các thao tác MongoDB thực sự sử dụng session/transaction do manager quản lý.
6. Cơ chế xử lý commit, rollback, lỗi transient và idempotency phù hợp.

Trọng tâm bài này là **đăng ký `MongoTransactionManager` và bật quản lý giao dịch cho luồng đồng bộ (imperative)**, sau đó chứng minh transaction hoạt động bằng kiểm thử tích hợp. Phần cuối phân biệt với reactive access, multiple transaction managers và các lỗi triển khai.

> Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x và MongoDB server hỗ trợ multi-document transactions. Kiểm tra version và cấu hình thực tế của dự án: một số API/convention khác nhau giữa các dòng Spring Boot/Spring Data. Transaction không tự làm các tác vụ bên ngoài MongoDB (email, HTTP, Kafka) trở nên nguyên tử.

## 2. Phân biệt session, transaction và transaction manager

Ba khái niệm thường bị sử dụng lẫn lộn:

| Khái niệm | Vai trò | Có tự tạo transaction không? |
|---|---|---|
| **ClientSession** của MongoDB Driver | Lưu ngữ cảnh một session, causal consistency hoặc transaction khi được mở | Không, nếu chưa `startTransaction` |
| **MongoDB transaction** | Nhiều read/write operations trong một giao dịch được commit/abort theo quy tắc server | Phải được start và quản lý vòng đời |
| **MongoTransactionManager** | Bridge giữa Spring transaction abstraction và MongoDB client session/transaction | Tạo và quản lý khi có transaction boundary từ Spring |
| **@Transactional** | Khai báo transaction boundary ở service method | Chỉ hoạt động khi có manager/interceptor và lời gọi đi đúng proxy |
| **@EnableTransactionManagement** | Kích hoạt Spring annotation-driven transaction handling theo cấu hình | Không tạo MongoTransactionManager bean hay thay server topology |
| **MongoTemplate** | Gửi truy vấn/ghi tới MongoDB theo mapping Spring Data | Tham gia transaction khi được quản lý đúng |

Luồng chuẩn:

~~~mermaid
flowchart TD
    A["HTTP / Worker gọi Spring service proxy"] --> B["@Transactional interceptor"]
    B --> C["MongoTransactionManager"]
    C --> D["MongoDatabaseFactory"]
    D --> E["MongoDB ClientSession + start transaction"]
    E --> F["MongoTemplate / repositories dùng session"]
    F --> G["Cập nhật account A"]
    G --> H["Cập nhật account B"]
    H --> I{"Method kết thúc?"}
    I -->|"Bình thường"| J["Commit"]
    I -->|"Rollback rule hoặc lỗi"| K["Abort"]
~~~

**Không có bean `MongoTransactionManager`**, annotation `@Transactional` không mặc nhiên biết phải sử dụng MongoDB transaction. Nếu có transaction manager khác, Spring còn có thể chọn **nhầm** manager cho JDBC/JPA. Cần cấu hình có chủ đích.

### 2.1. Session đơn thuần khác transaction

Một `ClientSession` có thể được dùng cho các operation thuộc cùng session mà **không mở transaction**. Có session không chứng minh các lệnh được commit cùng nhau.

Trong Spring, các thao tác `MongoTemplate` có thể tham gia session gắn với thread hiện tại khi `MongoTransactionManager` đang quản lý transaction. Đừng tự tạo driver session khác bên trong method rồi nghĩ rằng nó tự nhập vào transaction Spring đang chạy.

### 2.2. Single-document atomicity vẫn hữu ích

Khi invariant chỉ nằm ở **một document**, có thể viết một lệnh:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    stock_qty: { $gte: 3 }
  },
  { $inc: { stock_qty: -3 } }
);
~~~

Filter và update được kiểm tra/áp dụng nguyên tử trên document đó. **Không nhất thiết mở transaction** chỉ để bảo vệ trường hợp một document như trên. Transaction nhiều document có chi phí cao hơn và phải được dùng khi cần ranh giới nhất quán rộng hơn.

## 3. Yêu cầu của MongoDB server và topology

Multi-document transactions yêu cầu server MongoDB hỗ trợ và môi trường triển khai phù hợp. Trong thực tế, topology thường là **replica set** hoặc **sharded cluster** hỗ trợ transactions; một MongoDB **standalone** thông thường không đáp ứng yêu cầu này.

Để tránh nhầm lẫn:

- Một MongoDB container chạy đơn lẻ bằng `mongod` **không tự biến thành replica set**.
- Một **single-node replica set** có thể dùng trong môi trường phát triển/test khi được cấu hình đúng.
- Production thường dùng replica set có số node phù hợp để đáp ứng yêu cầu availability/durability.
- Sharded cluster hỗ trợ transaction theo phiên bản/quy tắc server nhưng có chi phí, giới hạn và thao tác triển khai riêng.
- Driver URI, authentication, replica set discovery và session support phải hoạt động; không chỉ thêm `@Transactional` ở Java.

### 3.1. Kiểm tra topology bằng mongosh

Trong môi trường được phép truy cập:

~~~javascript
db.hello();
~~~

Với replica set, phản hồi có thể chứa metadata như `setName` và thông tin primary/member. Có thể kiểm tra thêm:

~~~javascript
rs.status();
~~~

`rs.status()` phù hợp trong phiên làm việc mongosh kết nối replica set và có quyền tương ứng; trên standalone hoặc user bị giới hạn quyền, lệnh có thể thất bại. **Không dùng việc lệnh thành công/thất bại như cách kiểm tra duy nhất**: còn cần kiểm tra URI/connection options và thử transaction thật.

### 3.2. URI Spring Boot

Ví dụ dành cho **môi trường local/test có replica set tên `rs0`**:

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://localhost:27017/shopdb?replicaSet=rs0"
~~~

`localhost` chỉ phù hợp khi ứng dụng thực sự kết nối tới MongoDB qua địa chỉ đó. Trong Docker/Kubernetes, host/port, DNS member của replica set và network topology phải được cấu hình đúng, không copy URI local sang production.

Trong hệ thống có tài khoản/password, secret nên được cấp từ cơ chế quản lý bí mật; không hard-code credentials trong bài học, Git repository hay logging.

### 3.3. Chuẩn bị collection/index trước transaction

Đối với ví dụ chuyển tiền, nên tạo collection và index cần thiết **trước** khi bắt đầu transaction nghiệp vụ. Một số thao tác DDL, create collection/index trong transaction có giới hạn tùy version/topology. Đừng làm index migration ngầm trong service `@Transactional`.

## 4. Dependencies: cần Spring Data MongoDB và Spring transaction abstraction

Với Spring Boot 3.x, một cách khai báo Gradle thông dụng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Data MongoDB và Spring transaction abstraction được quản lý theo BOM của Spring Boot khi dùng dependency management phù hợp. Tránh ép một `spring-data-mongodb` hoặc MongoDB Driver version riêng không tương thích với Boot BOM chỉ vì thấy API transaction trong tài liệu một phiên bản khác.

Nếu dự án đã dùng Spring Boot Starter từ trước, không cần thêm dependencies trùng lặp. Với dự án không dùng Boot, cần cấu hình MongoDB client/database factory/template và transaction infrastructure tương ứng thủ công.

### 4.1. Cấu hình connection và registration là hai việc khác nhau

Spring Boot thường có thể tạo `MongoClient`, `MongoDatabaseFactory` và `MongoTemplate` dựa trên starter/cấu hình. Nhưng **không đồng nghĩa ứng dụng đã có một bean `MongoTransactionManager` được đăng ký theo đúng ý định**. Ta sẽ khai báo bean này tường minh.

Kiểm tra trong application context:

~~~java
Map<String, MongoTransactionManager> managers =
        applicationContext.getBeansOfType(
                MongoTransactionManager.class);
~~~

Đoạn này minh họa logic chẩn đoán bên trong một bean có `applicationContext` được inject; không phải class Java độc lập. Đừng chỉ dựa vào `@Transactional` xuất hiện trong source code.

## 5. Đăng ký MongoTransactionManager bằng @Configuration

Đây là cấu hình cốt lõi của bài học.

**MongoTransactionConfig.java**

~~~java
package com.example.finance;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class MongoTransactionConfig {

    @Bean("mongoTransactionManager")
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory mongoDatabaseFactory) {
        return new MongoTransactionManager(mongoDatabaseFactory);
    }
}
~~~

Trong cấu hình này:

1. `@Configuration` cho Spring biết đây là class đăng ký bean.
2. `@Bean("mongoTransactionManager")` đăng ký một manager có tên xác định.
3. `MongoDatabaseFactory` do Spring quản lý cung cấp MongoDB connection/database scope.
4. `new MongoTransactionManager(factory)` tạo Spring `PlatformTransactionManager` dành cho MongoDB imperative operations.
5. `@EnableTransactionManagement` kích hoạt xử lý annotation `@Transactional` theo cơ chế proxy mặc định của Spring.

**Điểm mấu chốt:** chỉ đăng ký manager không khiến mọi truy vấn tự khởi động transaction. Transaction chỉ được mở khi ứng dụng đi vào một transaction boundary được Spring nhận diện, chẳng hạn method `@Transactional` hoặc `TransactionTemplate`.

### 5.1. Có nhất thiết ghi @EnableTransactionManagement?

Trong nhiều ứng dụng Spring Boot, transaction infrastructure có thể đã được tự cấu hình khi phát hiện transaction manager và các điều kiện cần thiết. Bài này dùng **`@EnableTransactionManagement` tường minh** để giải thích cơ chế và tránh phụ thuộc vào suy đoán cấu hình.

Nếu dự án đã bật transaction management qua auto-configuration hoặc một config khác, đừng copy nhiều cấu hình lặp lại mà chưa kiểm tra. Mục tiêu không phải “thêm annotation càng nhiều càng an toàn” mà là **một hạ tầng transaction hoạt động đúng, rõ manager và scope**.

### 5.2. Không tự tạo MongoClient mới chỉ cho manager

Sai về mặt thiết kế:

~~~java
// Không nên dùng một MongoClient/database factory khác
// bên trong transaction manager trong khi MongoTemplate
// của service kết nối vào factory khác.
~~~

Nếu `MongoTemplate` và `MongoTransactionManager` được nối tới **hai factory/client khác nhau**, việc manager mở transaction không đủ để chứng minh các operation của template được enlist vào transaction đó. Ưu tiên inject **cùng `MongoDatabaseFactory`** do application context quản lý.

### 5.3. Manager phục vụ imperative, không phải reactive

`MongoTransactionManager` là manager cho luồng **đồng bộ/thread-bound** (imperative). Spring Data MongoDB reactive dùng `ReactiveMongoTransactionManager` và Reactor context; không lấy một manager imperative gắn vào repository reactive rồi kỳ vọng có transaction.

## 6. @Transactional hoạt động qua Spring proxy

Sau khi đăng ký manager, tạo một Spring bean có method transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ExampleService {
    @Transactional(transactionManager = "mongoTransactionManager")
    public void performBusinessOperation() {
        // Gọi MongoTemplate / MongoRepository ở đây.
    }
}
~~~

Với cấu hình proxy mặc định, khi một bean khác gọi `performBusinessOperation()` **qua Spring proxy**, interceptor sẽ dùng manager đã chọn để mở transaction, gọi body rồi commit hoặc rollback theo kết quả.

### 6.1. @Transactional không phải keyword của Java

Không có phép biến đổi Java compiler nào biến mọi lệnh MongoDB trong một method có annotation thành một đơn vị giao dịch. Transaction thực sự tồn tại vì **runtime infrastructure** của Spring và session driver đang hoạt động.

### 6.2. Self-invocation bỏ qua proxy mặc định

~~~java
@Service
public class UnsafeExample {
    public void outer() {
        // Lời gọi nội bộ trên "this" không đi qua Spring proxy.
        inner();
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void inner() {
        // Không mặc định được mở transaction
        // khi gọi từ outer() như trên.
    }
}
~~~

Sửa bằng cách đưa method transaction vào bean khác và gọi qua bean Spring được inject, hoặc thiết kế một **public transactional entrypoint** được caller gọi qua proxy. Đừng dùng self-injection/circular dependency như một mẹo mặc định khi chưa cân nhắc kiến trúc.

### 6.3. Thread-bound scope

Imperative Spring transaction dựa trên context gắn với thread đang thực thi. `@Async`, tự spawn thread, `CompletableFuture.supplyAsync(...)` hay Reactor scheduler khác không tự được kế thừa transaction thread-bound:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void riskyMethod() {
    // Nếu ném công việc sang một thread khác,
    // không mặc định có transaction context tương tự.
}
~~~

Nếu nghiệp vụ thực sự cần các thao tác cùng transaction, giữ chúng trong transaction-bound flow, hoặc thiết kế một boundary phù hợp ở mỗi worker. Không kéo transaction đi qua mạng hoặc chạy quá lâu chỉ để bao phủ công việc nền.

## 7. Entity mẫu: hai document tài khoản

Ta dùng collection `money_accounts`. Hai tài khoản được lưu **hai document riêng**, nên chuyển tiền không thể dựa vào single-document atomicity.

**MoneyAccount.java**

~~~java
package com.example.finance;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "money_accounts")
public class MoneyAccount {

    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;

    @Field("balance_vnd")
    private long balanceVnd;

    protected MoneyAccount() {
        // Spring Data object mapping.
    }

    public MoneyAccount(
            String id, String tenantId, long balanceVnd) {
        this.id = id;
        this.tenantId = tenantId;
        this.balanceVnd = balanceVnd;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public long getBalanceVnd() {
        return balanceVnd;
    }
}
~~~

**MoneyAccountRepository.java**

~~~java
package com.example.finance;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface MoneyAccountRepository
        extends MongoRepository<MoneyAccount, String> {
}
~~~

Metadata cần nhớ:

- Java `id` được lưu thành BSON `_id` dạng String.
- Java `balanceVnd` được ánh xạ vào BSON `balance_vnd` nhờ `@Field`.
- `tenantId` phải lấy từ ngữ cảnh xác thực đáng tin khi update; MongoDB không tự thêm filter tenant cho ta.
- Đơn vị tiền là VND nguyên, biểu diễn bằng `long`; hệ thống đa tiền tệ/phần lẻ cần mô hình chính xác hơn. Với tính toán cộng/trừ phải xét overflow và invariant nghiệp vụ.

Tạo dữ liệu kiểm thử:

~~~javascript
db.money_accounts.insertMany([
  {
    _id: "A",
    tenantId: "tenant-a",
    balance_vnd: NumberLong(100000)
  },
  {
    _id: "B",
    tenantId: "tenant-a",
    balance_vnd: NumberLong(20000)
  }
]);
~~~

Không chạy seed lặp trên collection production. Trong integration test, chỉ seed trong database được cô lập.

## 8. Service chuyển tiền dùng MongoTemplate và @Transactional

**MoneyTransferService.java**

~~~java
package com.example.finance;

import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MoneyTransferService {

    private final MongoTemplate mongo;

    public MoneyTransferService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void transfer(
            String authenticatedTenantId,
            String fromAccountId,
            String toAccountId,
            long amountVnd) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || fromAccountId == null || fromAccountId.isBlank()
                || toAccountId == null || toAccountId.isBlank()
                || fromAccountId.equals(toAccountId)
                || amountVnd <= 0) {
            throw new IllegalArgumentException("Thông tin chuyển tiền sai");
        }

        Query debitFilter = Query.query(
                Criteria.where("id").is(fromAccountId)
                        .and("tenantId").is(authenticatedTenantId)
                        .and("balanceVnd").gte(amountVnd));

        UpdateResult debit = mongo.updateFirst(
                debitFilter,
                new Update().inc("balanceVnd", -amountVnd),
                MoneyAccount.class);

        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Tài khoản nguồn không hợp lệ hoặc không đủ số dư");
        }

        Query creditFilter = Query.query(
                Criteria.where("id").is(toAccountId)
                        .and("tenantId").is(authenticatedTenantId));

        UpdateResult credit = mongo.updateFirst(
                creditFilter,
                new Update().inc("balanceVnd", amountVnd),
                MoneyAccount.class);

        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Tài khoản đích không tồn tại hoặc không thuộc tenant");
        }

        // Khi method return thành công, interceptor sẽ commit.
    }
}
~~~

Trong code:

1. `@Transactional(transactionManager = "mongoTransactionManager")` chọn rõ manager MongoDB.
2. `MongoTemplate` inject từ Spring sử dụng session được transaction manager bind đúng cách.
3. Debit có **điều kiện đủ số dư** để không âm.
4. Credit giới hạn cùng `tenantId` để không ghi vào tài khoản thuộc tenant khác.
5. Nếu debit/credit không khớp, method ném unchecked exception. Theo rollback rule mặc định, transaction sẽ được abort.
6. **Không dùng hai read–modify–save** cho số dư: `$inc` trong database tránh stale overwrite của một field.

### 8.1. Tại sao dùng matchedCount chứ không chỉ tin không có exception?

`updateFirst` có thể hợp lệ và không ném lỗi nhưng `matchedCount = 0` khi điều kiện không khớp. Với chuyển tiền, đó là thất bại nghiệp vụ: nếu debit không match không được credit; nếu credit không match phải rollback debit.

Không nên hiểu `matchedCount = 0` chỉ là tài khoản không tồn tại; có thể còn là sai tenant, số dư thiếu hoặc filter bổ sung không đạt. Quy tắc trả HTTP status phải được định nghĩa riêng.

### 8.2. Vì sao một update trên một tài khoản chưa đủ?

Trừ tiền ở A và cộng tiền ở B đều là **atomic single-document updates**. Nhưng invariant “tổng tiền của hai account không thay đổi” yêu cầu cả hai document cùng commit, vì thế transaction có ý nghĩa.

### 8.3. Tại sao không gọi email/HTTP bên trong transaction?

Một lệnh gọi sang hệ thống thanh toán ngoài hoặc gửi email **không tham gia MongoDB transaction**. Nếu server MongoDB abort sau khi email đã gửi, email không tự được thu hồi. Mô hình outbox và consumer idempotent thường phù hợp hơn.

### 8.4. Điều kiện dữ liệu phải được kiểm tra trước production

Đây là ví dụ *giao dịch dữ liệu*, **chưa phải hệ thống chuyển tiền production**. Cần bổ sung ledger bất biến, idempotency theo transfer ID, kiểm soát currency, overflow, limit/permission, audit, chống double spending ở các đường ghi khác, handling transient errors và unknown commit outcome.

## 9. Dòng thời gian commit và rollback thực tế

Hai lệnh `updateFirst` bên trong service `@Transactional` đều được thực thi trong transaction session. Sau đó kết quả phụ thuộc việc method kết thúc bình thường hay có lỗi.

### 9.1. Trường hợp thành công

~~~text
Caller -> Spring proxy
  -> MongoTransactionManager: open session + startTransaction
     -> debit(A, 30000), matched=1
     -> credit(B, 30000), matched=1
     -> service return normally
  -> transaction manager: commit
Caller nhận kết quả

Sau commit:
A = 70000
B = 50000
~~~

### 9.2. Trường hợp debit không hợp lệ

~~~text
Caller -> Spring proxy
  -> transaction begin
     -> debit(A, 30000), matched=0
     -> ném IllegalStateException
     -> KHÔNG chạy credit(B)
  -> abort transaction
Caller nhận exception
~~~

### 9.3. Trường hợp credit thất bại sau debit

~~~text
Caller -> Spring proxy
  -> transaction begin
     -> debit(A, 30000), matched=1
     -> credit(B, 30000), matched=0
     -> ném IllegalStateException
  -> abort transaction
Caller nhận exception

Sau abort:
A vẫn = 100000
B vẫn = 20000 (nếu B tồn tại nhưng không match)
~~~

**Điều cần chứng minh bằng integration test** là A đã được sửa trong transaction nhưng **thay đổi không được commit** sau khi method ném lỗi. Đừng chỉ assert có exception; một service không transaction cũng có thể ném exception sau debit nhưng để A bị trừ vĩnh viễn.

### 9.4. Sau service return vẫn có thể lỗi commit

Nội dung method kết thúc thành công **chưa đồng nghĩa client chắc chắn nhận một commit thành công**. Transaction manager phải gửi lệnh commit; commit có thể gặp timeout, lỗi transient hoặc kết quả chưa xác định. Cần phân biệt:

- Lỗi xảy ra **trong body** → framework xử lý rollback theo rule.
- Lỗi **khi commit** → trạng thái giao dịch cần được phân loại/đối soát theo MongoDB semantics.
- Client mất response **sau commit thành công** → retry toàn bộ transfer có thể nhân đôi hiệu ứng nếu thiếu idempotency.

Một trang web hiển thị “thành công” chỉ khi method chạy hết nhưng chưa quan tâm kết quả commit là thiết kế dễ sai.

## 10. Rollback rules: unchecked, checked và catch exception

Spring transaction proxy có rollback rules. Theo mặc định thường gặp trong Spring Framework:

- `RuntimeException` và `Error` dẫn đến rollback.
- Checked exception thông thường **không mặc định** yêu cầu rollback, trừ khi cấu hình rollback rule.
- Các phiên bản Spring mới hơn có thể hỗ trợ tùy biến default rollback rules; hãy xác minh cấu hình của dự án.

Ví dụ:

~~~java
@Transactional(
        transactionManager = "mongoTransactionManager",
        rollbackFor = java.io.IOException.class)
public void processWithCheckedFailure() throws java.io.IOException {
    // MongoDB writes ...
    throw new java.io.IOException("Lỗi quy trình");
}
~~~

Khi nghiệp vụ có checked exception phải rollback, **định nghĩa `rollbackFor` rõ ràng**. Đừng mặc định mọi exception đều rollback.

### 10.1. Nuốt exception khiến transaction có thể commit

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void unsafe() {
    try {
        debit();
        credit();
    } catch (RuntimeException ex) {
        logger.warn("Chuyển tiền lỗi", ex);
        // Method vẫn return normally.
        // Transaction interceptor có thể coi là thành công.
    }
}
~~~

`logger` và hai method trên là ví dụ minh họa trong một service có biến/method tương ứng. **Nếu exception bị bắt và không ném lại**, transaction interceptor thông thường không nhận được tín hiệu rollback từ lời gọi. Một số lỗi ở driver/transaction state có thể tự đánh dấu transaction thất bại, nhưng **không được dựa vào điều đó**.

Cách tốt hơn:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void transferOrFail() {
    debit();
    credit(); // Nếu lỗi nghiệp vụ cần rollback, ném exception.
}
~~~

Nếu có lý do cần catch và vẫn rollback, có thể đánh dấu rollback-only thông qua Spring transaction API trong transaction đang hoạt động; nhưng ưu tiên một exception rõ và xử lý ở tầng ngoài transaction.

### 10.2. Nơi xử lý lỗi

~~~text
Controller / Job boundary
    try:
        gọi service @Transactional qua Spring proxy
    catch:
        chuyển lỗi thành response / retry policy

Service @Transactional
    validate
    MongoDB writes
    throw khi invariant không đạt
~~~

Với cấu trúc này, exception được truyền **qua transaction interceptor** trước khi controller nhận và xử lý, nên framework có cơ hội abort transaction đúng rule.

## 11. Propagation và phạm vi transaction

`@Transactional` hỗ trợ propagation. Tác dụng cụ thể phải được hiểu trong transaction manager đang dùng.

| Propagation | Ý nghĩa tổng quát | Lưu ý với MongoDB |
|---|---|---|
`REQUIRED` | Tham gia transaction hiện tại hoặc tạo mới | Mặc định thường phù hợp service boundary |
`SUPPORTS` | Tham gia nếu có; không có thì chạy không transaction | Dễ vô tình ghi ngoài transaction nếu caller không tạo |
`MANDATORY` | Bắt buộc phải có transaction hiện tại | Hữu ích cho helper chỉ được chạy trong transaction |
`REQUIRES_NEW` | Đề nghị transaction độc lập mới, suspend scope cũ nếu hỗ trợ | Cần hiểu resource/session và tránh giữ nhiều giao dịch lâu |
`NOT_SUPPORTED` | Chạy ngoài transaction, suspend scope hiện tại nếu hỗ trợ | Không dùng cho bước bắt buộc all-or-nothing |
`NEVER` | Báo lỗi khi đang ở transaction | Phù hợp những operation không được phép trong transaction |
`NESTED` | Dựa trên savepoint/nested transaction nếu manager hỗ trợ | **Không coi MongoTransactionManager có savepoint/nested transaction như JDBC** |

Ví dụ một helper chỉ được gọi khi có transaction:

~~~java
import org.springframework.transaction.annotation.Propagation;

@Transactional(
        transactionManager = "mongoTransactionManager",
        propagation = Propagation.MANDATORY)
public void writeLedgerEntry(...) {
    // Cần transaction của caller.
}
~~~

Fragment trên nằm trong Spring bean có implementation thực. `Propagation.MANDATORY` giúp phát hiện một số trường hợp gọi helper ngoài transaction, nhưng vẫn phải kiểm tra rằng transaction **đúng là MongoDB transaction** và MongoTemplate dùng cùng factory.

### 11.1. Đừng gắn @Transactional ở mọi method rồi đoán hiệu ứng

Nếu method ngoài đã mở transaction và gọi helper `REQUIRED` qua Spring proxy, chúng có thể chia sẻ cùng transaction. Nhưng self-invocation, sai manager, thread mới hoặc một annotation propagation khác có thể khiến boundary không như mong muốn.

Xác định **một entrypoint transaction chính**, giữ scope ngắn, mô tả invariant và kiểm thử rollback thực tế.

### 11.2. Không dùng NESTED như savepoint của MongoDB

MongoDB multi-document transaction không mặc định hỗ trợ nested transaction/savepoint theo nghĩa JDBC. Không thiết kế “rollback phần B nhưng giữ phần A trong cùng transaction” bằng cách thêm `Propagation.NESTED` mà chưa xác minh khả năng manager và server.

Nếu một nhánh có thể thất bại nhưng không làm hỏng cả nghiệp vụ, cân nhắc thay mô hình transaction hoặc lưu state/compensation có chủ đích.

## 12. Quản lý transaction theo chương trình bằng TransactionTemplate

Không phải ứng dụng nào cũng muốn dùng annotation trên mọi luồng. Spring có `TransactionTemplate` để tạo transaction boundary tường minh:

**MongoTransactionTemplateConfig.java**

~~~java
package com.example.finance;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class MongoTransactionTemplateConfig {

    @Bean("mongoTransactionTemplate")
    public TransactionTemplate mongoTransactionTemplate(
            @Qualifier("mongoTransactionManager")
            PlatformTransactionManager manager) {
        return new TransactionTemplate(manager);
    }
}
~~~

Sử dụng từ một Spring service:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ProgrammaticTransferService {
    private final TransactionTemplate transactions;
    private final MongoTemplate mongo;

    public ProgrammaticTransferService(
            @Qualifier("mongoTransactionTemplate")
            TransactionTemplate transactions,
            MongoTemplate mongo) {
        this.transactions = transactions;
        this.mongo = mongo;
    }

    public void doWork() {
        transactions.execute(status -> {
            // MongoTemplate operations trong callback này.
            // Ném RuntimeException nếu nghiệp vụ thất bại.
            return null;
        });
    }
}
~~~

Đây là ví dụ **scope transaction programmatic**, chưa phải implementation chuyển tiền. Nó làm rõ ranh giới “bắt đầu → callback → commit/rollback” mà không phụ thuộc một method `@Transactional` được caller gọi qua proxy.

### 12.1. Khi nào dùng TransactionTemplate?

- Một khối code nhỏ cần transaction rõ ràng trong một service phức tạp.
- Cần điều khiển chặt callback boundaries và cách chuyển result.
- Cần tránh vấn đề self-invocation của `@Transactional` khi thiết kế code có thể dùng template.
- Có nhiều managers, muốn inject rõ template MongoDB.

Không dùng `TransactionTemplate` chỉ để biến một workflow chạy hàng phút trở thành transaction kéo dài. Nó vẫn sử dụng `MongoTransactionManager` và các giới hạn của MongoDB session/transaction.

### 12.2. Template và annotation không nên lồng tùy tiện

Một callback `TransactionTemplate` bên trong method đã `@Transactional` có thể tham gia transaction hiện có hoặc tạo scope khác tùy propagation. Không tự suy rằng có hai annotation/template layers thì sẽ có “gấp đôi atomicity”. Phải xác định transaction boundary từ góc nhìn manager/server.

## 13. Session được liên kết với MongoTemplate như thế nào?

Trong một imperative transaction được `MongoTransactionManager` quản lý, Spring Data có thể bind `ClientSession` vào thread-bound resource để `MongoTemplate` và repository cùng factory sử dụng.

~~~text
Thread xử lý request
  Spring transaction context
      -> MongoTransactionManager
          -> ClientSession + transaction
              -> MongoTemplate.updateFirst(A)
              -> Repository.save(B)
              -> MongoTemplate.findOne(C)
  commit/rollback
~~~

Điều kiện: các template/repository dùng **MongoDatabaseFactory tương thích** và Spring transaction infrastructure đang hoạt động.

### 13.1. Không lấy native collection tùy tiện để bypass session

~~~java
// Đặt trong method @Transactional.
mongo.updateFirst(query, update, MoneyAccount.class);

// Thao tác driver trực tiếp qua MongoCollection có thể cần
// truyền ClientSession tường minh để tham gia transaction.
mongo.getCollection("money_accounts")
        .updateOne(rawFilter, rawUpdate);
~~~

Đoạn này minh họa **rủi ro** khi trộn đường Spring Data và đường Java Driver; `rawFilter`/`rawUpdate` là BSON documents đã tạo ở scope khác. Đừng giả định một lệnh driver viết trực tiếp lên collection sẽ tự dùng thread-bound Spring transaction như template. Nếu buộc dùng native driver, phải xác minh API session và cách enlist nó vào transaction cụ thể.

### 13.2. Một MongoTemplate khác có thể dùng sai factory

Nếu ứng dụng cấu hình nhiều MongoDB databases:

~~~text
mongoTemplateA -> databaseFactoryA
mongoTemplateB -> databaseFactoryB
mongoTransactionManager -> databaseFactoryA
~~~

Thì transaction manager cho A không tự quản lý mọi write trên B. Muốn transaction đảm bảo toàn bộ nghiệp vụ, cần xác định cùng MongoDB deployment/session và các operation được enlist đúng; **không có “transaction chéo hai MongoDB servers” chỉ nhờ hai template cùng dùng Spring**.

### 13.3. Session synchronization khi dùng manager khác

Spring Data MongoDB có cấu hình `SessionSynchronization` cho những kịch bản tích hợp session/transaction. Tuy nhiên không nên chỉnh `mongoTemplate.setSessionSynchronization(...)` theo một snippet rời rạc khi hệ thống đã dùng `MongoTransactionManager` đúng cách. Hãy hiểu manager nào sở hữu transaction, scope nào bind session và kiểm thử BSON command/rollback sau khi thay đổi.

## 14. Trường hợp có nhiều transaction managers

Ứng dụng có thể đồng thời có:

- `MongoTransactionManager` cho MongoDB.
- `DataSourceTransactionManager` hoặc `JpaTransactionManager` cho database quan hệ.
- Transaction manager của một MongoDB database/deployment khác.

Khi đó `@Transactional` không chỉ rõ manager dễ gây nhầm:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void updateMongoData() {
    // MongoTemplate operations
}
~~~

Việc đặt `@Bean("mongoTransactionManager")` như mục 5 giúp tên manager rõ ràng. Nếu muốn một manager là mặc định, có thể cấu hình `@Primary` hoặc `TransactionManagementConfigurer` theo nhu cầu, nhưng phải đánh giá toàn ứng dụng trước khi thay đổi lựa chọn mặc định.

### 14.1. Chọn nhầm manager không tạo MongoDB transaction

Ví dụ method sửa MongoDB nhưng được `JpaTransactionManager` bao quanh. Khi đó một JDBC/JPA transaction có thể hoạt động, nhưng **MongoDB writes không tự được enlist trong JDBC transaction**. Đặt đúng annotation manager và test rollback MongoDB để tránh ngộ nhận.

### 14.2. Hai transaction managers không tạo distributed transaction

~~~text
@Transactional("mongoTransactionManager")
  update MongoDB
  update PostgreSQL
~~~

Không đồng nghĩa MongoDB và PostgreSQL cùng commit/rollback. Một transaction manager đơn không thể tự điều phối ACID xuyên hai hệ thống độc lập. `ChainedTransactionManager`/hai transaction managers lồng nhau cũng không tự cấp bảo đảm distributed atomicity như XA.

Nếu business workflow trải qua nhiều hệ thống, cân nhắc **outbox, saga, compensation, idempotency và reconciliation**, hoặc một giải pháp điều phối được thiết kế đặc biệt với các giới hạn đã phân tích.

## 15. Transaction options: read/write concern, read preference và timeout

Khi dùng MongoDB transaction, cấu hình và semantics của:

- **Read concern**: mức nhất quán của dữ liệu đọc trong transaction.
- **Write concern**: mức xác nhận commit/write của server.
- **Read preference**: cách chọn replica phục vụ read; transaction có ràng buộc riêng về primary và read operations.
- **maxCommitTime**, lifetime/timeout và giới hạn khác tùy server/driver.

Ví dụ xây `TransactionOptions` ở phía MongoDB Java Driver:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;

TransactionOptions options = TransactionOptions.builder()
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();
~~~

Khi cấu hình manager ở dòng Spring Data hỗ trợ constructor nhận options, có thể truyền các options này vào `MongoTransactionManager`. **Không cần gắn options tuỳ tiện trên mọi transaction**; trước hết phải định nghĩa consistency/durability contract. Chi phí read concern snapshot/majority và write concern majority phải được benchmark.

### 15.1. @Transactional(readOnly = true) không đồng nghĩa “không có transaction”

`readOnly = true` trong Spring thường là một **hint/semantic** cho transaction infrastructure, không phải cơ chế bảo mật ngăn mọi MongoDB write. Với `MongoTransactionManager`, read-only scope có thể vẫn khởi động một session/transaction để phục vụ các read tùy version/config.

Đừng dựa vào annotation readOnly để bảo vệ một endpoint khỏi ghi dữ liệu; quyền database, code review và policy vẫn cần được thực thi.

### 15.2. IsolationLevel của Spring không tự tương đương isolation tùy ý ở MongoDB

MongoDB transaction có semantics read concern/snapshot và hạn chế riêng. Không kỳ vọng `@Transactional(isolation = Isolation.SERIALIZABLE)` sẽ làm MongoDB bỗng hỗ trợ một isolation level giống RDBMS nếu manager/server không cung cấp. Phải đọc tài liệu phiên bản và test invariant cụ thể.

### 15.3. Giữ transaction ngắn

Mở transaction rồi đợi người dùng xác nhận, gọi dịch vụ mạng chậm, upload file hoặc sleep lâu không phải cách sử dụng hiệu quả. Transaction kéo dài có thể tăng contention, memory/working set pressure và nguy cơ transient errors.

Thiết kế service ngắn: validate input → thực hiện các database writes cần cùng commit → return. Việc nặng ngoài DB nên đặt ngoài transaction hoặc đi qua outbox/worker.

## 16. Imperative và reactive transaction manager không thay thế nhau

**`MongoTransactionManager`** dành cho `MongoTemplate`/imperative MongoDB repositories. Nếu dự án sử dụng **`ReactiveMongoTemplate`** và reactive repositories, cần một manager riêng:

~~~java
package com.example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTxConfig {

    @Bean("reactiveMongoTransactionManager")
    public ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

Trong reactive pipeline, transaction context được truyền qua **Reactor Context**, không dựa trên cùng thread-local context như imperative flow. Một `Mono` hoặc `Flux` được tạo ra nhưng **chưa subscribe** chưa chạy database operations; transaction boundary phải bao đúng chuỗi reactive thực sự được thực thi.

### 16.1. TransactionalOperator cho reactive flow

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

TransactionalOperator operator =
        TransactionalOperator.create(reactiveMongoTransactionManager);

Mono<Void> work = debitReactive()
        .then(creditReactive())
        .as(operator::transactional);
~~~

Fragment này nằm trong một bean có `reactiveMongoTransactionManager`, `debitReactive()`, `creditReactive()` đã khai báo. Cần import Reactor `Mono`; đây là minh họa cơ chế bao transaction, không phải một service production đầy đủ.

Không gọi `block()` trong reactive chain rồi suy rằng mọi imperative write cũng được enlist vào cùng reactive MongoDB session. Nếu phải kết hợp imperative và reactive trong một workflow, cần phân tích ranh giới giao dịch rõ thay vì trộn hai managers.

### 16.2. Chọn @Transactional đúng loại return

Trong Spring, reactive transaction interception hoạt động với reactive return types và reactive transaction manager thích hợp. Một method trả `Mono` nhưng bị cấu hình manager imperative, hoặc một method `void` được mong đợi tham gia reactive manager, dễ gây lỗi/kết quả ngoài ý muốn.

Khi codebase có cả hai loại, đặt **tên bean riêng** và chọn manager tường minh:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void imperativeOperation() {
    // MongoTemplate operations
}

@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> reactiveOperation() {
    // ReactiveMongoTemplate operations
    return Mono.empty();
}
~~~

Đoạn trên chỉ minh họa annotation và signature, không thực hiện database write. Chỉ áp dụng khi các method nằm trên Spring-managed bean và dependencies/reactive infrastructure tương ứng đã được cấu hình.

## 17. Retry transaction và commit outcome chưa xác định

MongoDB transaction có thể gặp **write conflict** hoặc lỗi transient trong lúc nhiều request thay đổi các document nóng. Driver/server có cơ chế gắn error labels như `TransientTransactionError` hoặc `UnknownTransactionCommitResult` ở các lỗi tương ứng.

Không xử lý mọi exception bằng:

~~~java
while (true) {
    transferService.transfer(...);
}
~~~

Đây là một anti-pattern: retry vô hạn có thể tạo tải lớn, và nếu transaction **đã commit nhưng response bị mất**, chạy lại toàn bộ nghiệp vụ như một transfer mới có thể chuyển tiền **hai lần**.

### 17.1. Phân biệt ba tình huống

| Tình huống | Hướng xử lý |
|---|---|
Transaction abort chắc chắn, có lỗi transient được xác định | Retry **toàn transaction** với backoff/giới hạn và logic idempotent |
Kết quả `commitTransaction` không rõ | Theo quy tắc driver/server, retry commit hoặc **đối soát trạng thái**, không tự coi là abort |
Business exception do không đủ tiền/sai tenant | **Không** retry mù quáng; trả lỗi nghiệp vụ |

Một số đường API/driver có helper xử lý retry transaction theo đặc tả của MongoDB. Khi dùng Spring `@Transactional`, cần hiểu phần retry nào được driver/framework xử lý và phần nào ứng dụng phải xử lý. Không gắn một `@Retryable` chung cho mọi exception rồi cho rằng đã đúng.

### 17.2. Idempotency của toàn transfer

Để người dùng retry transfer sau timeout mà không làm mất tiền hai lần, nên có **transfer ID** ổn định được ghi nhận bền vững cùng các thay đổi tài khoản trong transaction:

~~~text
Transaction:
  validate transferId chưa xử lý
  debit A
  credit B
  insert transfer record với unique(tenantId, transferId)
Commit
~~~

Unique constraint và cách diễn giải duplicate key phải được thiết kế cẩn thận theo contention. Sau timeout, một request cùng `transferId` nên nhận được trạng thái **đã xử lý/đang xử lý/chưa xác định** theo contract, không đơn giản là chuyển tiếp lần hai.

### 17.3. Transactional outbox khi cần phát sự kiện

Nếu transfer thành công còn cần publish event:

~~~text
MongoDB transaction:
  update A
  update B
  insert outbox event (unique eventId)

Outbox worker (ngoài transaction):
  đọc event chưa publish
  publish
  đánh dấu tiến độ
~~~

Worker có thể publish rồi crash trước khi mark completed, nên consumer cần xử lý message duplicate. Outbox giúp ngăn trường hợp commit account nhưng **không có dữ liệu sự kiện để phát**, không tự cung cấp “exactly once” trên mạng.

## 18. Cấu hình MongoDB thực cho integration test

Một unit test chỉ mock `MongoTemplate` không thể chứng minh rollback. Integration test phải chạy trên **MongoDB topology hỗ trợ transaction**, có manager đăng ký thật và các thao tác thực sự enlist vào cùng transaction.

Hai lựa chọn thường gặp:

1. **Testcontainers MongoDB** phiên bản tương thích với Spring Boot/Testcontainers đang dùng, cấu hình **single-node replica set** được hỗ trợ.
2. Một **replica set MongoDB test riêng**, với kết nối có `replicaSet` và credentials/ports dành cho test.

Trong Spring Boot 3.x, `@DataMongoTest` tạo cấu hình test slice cho Spring Data MongoDB nhưng **không tự khởi động server**. Nếu dùng Testcontainers, cấu hình container/`@DynamicPropertySource` hoặc `@ServiceConnection` cần tuân thủ đúng version thư viện và phải cung cấp connection string có session/replica set hợp lệ.

### 18.1. Mẫu properties test với replica set đang chạy

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://localhost:27017/transaction_test?replicaSet=rs0"
~~~

Chỉ dùng địa chỉ này nếu một MongoDB replica set test `rs0` đang hoạt động ở đó. **Không trỏ integration test có lệnh xóa/seed vào database dùng chung hoặc production.**

### 18.2. Preflight kết nối test

Trước khi coi bài test transaction có ý nghĩa:

- Replica set đã elect primary và driver discover được topology.
- Collection `money_accounts` tồn tại hoặc đã được chuẩn bị ở bước setup **ngoài transaction**.
- Test có quyền read/write cần thiết.
- `MongoTransactionConfig` được import/scan vào application context.
- Không có một transaction manager khác bị chọn thay manager MongoDB.
- Test method không vô tình được bọc trong một transaction lớn của framework test khiến mọi assertion “rollback” trở thành khó diễn giải.

Trong test dưới đây, method test **không có `@Transactional`**; transaction boundary nằm ở `MoneyTransferService.transfer` và được tạo từ service proxy.

## 19. Integration test: chứng minh commit và rollback

**MoneyTransferIntegrationTest.java**

~~~java
package com.example.finance;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import({
        MongoTransactionConfig.class,
        MoneyTransferService.class
})
class MoneyTransferIntegrationTest {

    @Autowired
    MongoTemplate mongo;

    @Autowired
    MoneyTransferService transfers;

    @BeforeEach
    void seed() {
        // Dữ liệu riêng cho database test cô lập.
        // Không chạy trên production/shared database.
        mongo.remove(new Query(), MoneyAccount.class);
        mongo.insert(
                new MoneyAccount("A", "tenant-a", 100000L));
        mongo.insert(
                new MoneyAccount("B", "tenant-a", 20000L));
    }

    private long balance(String id) {
        MoneyAccount account =
                mongo.findById(id, MoneyAccount.class);
        assertThat(account).isNotNull();
        return account.getBalanceVnd();
    }

    @Test
    void transferCommitsBothDocuments() {
        transfers.transfer("tenant-a", "A", "B", 30000L);

        assertThat(balance("A")).isEqualTo(70000L);
        assertThat(balance("B")).isEqualTo(50000L);
        assertThat(balance("A") + balance("B"))
                .isEqualTo(120000L);
    }

    @Test
    void missingDestinationRollsBackSourceDebit() {
        assertThatThrownBy(() ->
                transfers.transfer(
                        "tenant-a", "A", "MISSING", 30000L))
                .isInstanceOf(IllegalStateException.class);

        // Debit được thực hiện trong transaction,
        // nhưng phải bị rollback khi credit không match.
        assertThat(balance("A")).isEqualTo(100000L);
        assertThat(balance("B")).isEqualTo(20000L);
    }

    @Test
    void insufficientBalanceDoesNotCreditDestination() {
        assertThatThrownBy(() ->
                transfers.transfer("tenant-a", "A", "B", 200000L))
                .isInstanceOf(IllegalStateException.class);

        assertThat(balance("A")).isEqualTo(100000L);
        assertThat(balance("B")).isEqualTo(20000L);
    }

    @Test
    void crossTenantDestinationIsNotCredited() {
        mongo.insert(
                new MoneyAccount("C", "tenant-b", 50000L));

        assertThatThrownBy(() ->
                transfers.transfer("tenant-a", "A", "C", 30000L))
                .isInstanceOf(IllegalStateException.class);

        assertThat(balance("A")).isEqualTo(100000L);
        assertThat(balance("C")).isEqualTo(50000L);
    }

    @Test
    void invalidAmountIsRejectedWithoutWrites() {
        assertThatThrownBy(() ->
                transfers.transfer("tenant-a", "A", "B", 0L))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(balance("A")).isEqualTo(100000L);
        assertThat(balance("B")).isEqualTo(20000L);
    }
}
~~~

### 19.1. Test quan trọng nhất là rollback sau debit

Test `missingDestinationRollsBackSourceDebit` đảm bảo:

1. Account A có đủ 30.000 nên debit update **match 1**.
2. Account `MISSING` không tồn tại nên credit **match 0**.
3. Service ném unchecked exception.
4. Khi method kết thúc lỗi và manager abort transaction, A phải trở lại 100.000.

Nếu bỏ `@Transactional` hoặc manager không thực sự có tác dụng, cùng test có thể để A còn 70.000. Đây là bằng chứng mạnh hơn việc chỉ kiểm tra có exception.

### 19.2. Test phải độc lập

`@BeforeEach` xóa dữ liệu tài khoản để seed lại A/B. Khi test chạy song song trên cùng database, bước xóa có thể làm test khác thất bại. Cần:

- Database/collection tách biệt theo test class hoặc suite.
- Thiết lập không chạy song song nếu dùng chung collection.
- Không dùng `dropCollection`/`remove(new Query())` trên database có dữ liệu thật.
- Seed và cleanup **ngoài transaction** của code đang được kiểm thử để tránh vô tình che lỗi.

### 19.3. Test BSON mapping

Trong class test, có thể xác minh Java property `balanceVnd` thực sự được lưu dưới BSON `balance_vnd`:

~~~java
org.bson.Document raw = mongo.getCollection("money_accounts")
        .find(new org.bson.Document("_id", "A"))
        .first();

assertThat(raw).isNotNull();
assertThat(raw.get("balance_vnd")).isInstanceOf(Number.class);
assertThat(raw.containsKey("balanceVnd")).isFalse();
~~~

Đoạn này cần được đặt trong scope có `mongo` và import AssertJ static như test trên. Kiểm tra mapping là quan trọng vì `MongoTemplate.updateFirst` dùng Java property names nhưng server nhận BSON field names.

### 19.4. Điều test chưa chứng minh

Bộ test trên chứng minh **commit/rollback trên MongoDB test topology**. Nó chưa chứng minh:

- Service chống retry transfer hai lần sau unknown commit result.
- Hiệu năng dưới hàng nghìn transaction cạnh tranh.
- Không có double spend qua các service khác.
- Transaction logic còn đúng khi dùng nhiều MongoDB factory hoặc cả PostgreSQL.
- Tác động của failover, replication lag hoặc các write concerns khác.

Đây là các chủ đề cần bài test/thiết kế riêng. Không tuyên bố một test pass đã đủ cho giao dịch tài chính production.

## 20. Chẩn đoán manager và session trong ứng dụng

Khi `@Transactional` có vẻ không hoạt động, kiểm tra theo thứ tự từ application context tới MongoDB server:

### 20.1. Bean có tồn tại không?

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.data.mongodb.MongoTransactionManager;

Map<String, MongoTransactionManager> managers =
        context.getBeansOfType(MongoTransactionManager.class);
~~~

`context` là `ApplicationContext` được inject; cần import `java.util.Map`. Kết quả nên có bean tên `mongoTransactionManager` đã đăng ký trong mục 5.

### 20.2. Service có được proxy không?

Nếu caller tự `new MoneyTransferService(mongoTemplate)` hoặc gọi method nội bộ bằng `this.transfer(...)`, transaction interceptor có thể không được kích hoạt. Service phải là bean Spring được inject và method được gọi qua proxy phù hợp.

Có thể bật logging của Spring transaction ở mức cần thiết trong **môi trường test** để quan sát begin/commit/rollback. Không bật DEBUG toàn hệ thống trên production mà chưa đánh giá dữ liệu nhạy cảm, overhead và chính sách logging.

### 20.3. Transaction có được start ở MongoDB không?

MongoDB Java Driver `CommandListener` trong test có thể quan sát các MongoDB commands và thông tin như `lsid`, `startTransaction`, `autocommit` hoặc `commitTransaction`/`abortTransaction` theo cấu trúc command thực tế. Hãy xác minh thay đổi bằng integration test rollback thay vì chỉ tìm một field command ở mọi phiên bản.

Không log toàn bộ command bao gồm số tài khoản, tenant hoặc dữ liệu tài chính nhạy cảm. Cần che thông tin, giới hạn phạm vi và cleanup listener sau test.

### 20.4. Server có thực sự hỗ trợ transaction không?

Khi chạy standalone không hỗ trợ, có thể gặp lỗi server kiểu “transaction numbers are only allowed on a replica set member or mongos” hoặc tương tự, tùy phiên bản. Đó là **lỗi topology**, không phải lý do để xóa annotation rồi coi hai update đã được bảo vệ.

### 20.5. Nếu nhiều managers?

Xem danh sách `PlatformTransactionManager` beans, tên và qualifier. Dùng `@Transactional(transactionManager = "mongoTransactionManager")`, đặc biệt nếu app còn có JDBC/JPA transaction manager.

## 21. Bảng lỗi thường gặp và cách xử lý

| Biểu hiện/sai lầm | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
Chỉ thêm `@Transactional` nhưng không khai báo manager | Không có MongoDB manager hoặc chọn sai manager | Đăng ký `MongoTransactionManager` bằng đúng `MongoDatabaseFactory` |
MongoDB báo không hỗ trợ transaction | Standalone/topology/version chưa đáp ứng | Dùng replica set/sharded cluster tương thích |
Rollback test thất bại, debit vẫn tồn tại | Transaction không active hoặc write ngoài session | Kiểm tra proxy, manager, factory, path API |
Method tự gọi method `@Transactional` | Self-invocation bỏ qua proxy | Gọi qua Spring bean/proxy hoặc dùng `TransactionTemplate` |
Catch và nuốt RuntimeException | Interceptor thấy method kết thúc bình thường | Ném lại hoặc đánh dấu rollback-only đúng cách |
Checked exception không rollback | Default rollback rule không bao phủ | Cấu hình `rollbackFor` phù hợp |
`MongoTemplate` và manager dùng factory khác | Mongo operations không enlist đúng | Inject cùng factory/config rõ ràng |
Native driver update không có session | Write có thể nằm ngoài transaction | Sử dụng template/session API đúng |
Có manager JPA và Mongo, annotation không chỉ rõ | Chọn nhầm manager | Chọn theo tên/qualifier |
Tưởng transaction Mongo bao gồm JDBC | Không có distributed transaction | Outbox/saga/reconciliation |
Tưởng `@EnableTransactionManagement` tự tạo manager | Annotation chỉ bật hạ tầng proxy | Đăng ký bean manager |
Tưởng `@Bean` manager tự bọc mọi query | Chưa có transaction boundary | Dùng `@Transactional` hoặc `TransactionTemplate` |
Đặt transaction vào `@Async` không rõ scope | Thread-bound context không tự theo thread mới | Tạo transaction boundary ở worker |
Trộn reactive và imperative managers | Session context khác | Dùng `ReactiveMongoTransactionManager`/operator cho reactive |
`Propagation.NESTED` được kỳ vọng như savepoint JDBC | Không có nested savepoint như mong muốn | Thiết kế boundary khác |
Tạo collection/index ngầm trong transaction | Server có thể hạn chế DDL | Provision schema/index trước |
Credit không match nhưng method vẫn return | Transaction có thể commit debit | Ném exception và test rollback |
Retry sau unknown commit mà không transfer ID | Có thể chuyển tiền hai lần | Idempotency và đối soát |
Transaction giữ mở khi gọi HTTP/email | Lock/contention, không rollback external side effects | Giữ transaction ngắn, dùng outbox |
Test dùng MongoDB standalone | Không chứng minh transaction | Chạy replica set test |
Chỉ assert exception mà không kiểm tra số dư | Không phát hiện debit đã commit | Assert rollback dữ liệu thực |
Read secondary thấy cũ sau commit | Replication lag/read preference | Định nghĩa consistency/read concern contract |
Mở quá nhiều transaction lâu | Tăng contention, thời gian, lỗi transient | Thu hẹp transaction boundary |

## 22. Quy trình triển khai được khuyến nghị

Một checklist kỹ thuật có thể áp dụng cho ứng dụng Spring Data MongoDB:

1. **Xác định invariant.** Nghiệp vụ cần atomicity của một document hay nhiều document? Nếu chỉ một document, cân nhắc conditional update thay transaction.
2. **Kiểm tra MongoDB topology.** Server và driver hỗ trợ transaction, ứng dụng kết nối đúng replica set/sharded cluster.
3. **Thiết lập dependencies/config.** Spring Boot starter MongoDB, URI và database factory đúng.
4. **Đăng ký `MongoTransactionManager`.** Đặt bean có tên rõ và dùng cùng `MongoDatabaseFactory` với template/repository nghiệp vụ.
5. **Kích hoạt transaction interception.** `@EnableTransactionManagement` khi cần hoặc xác minh auto-configuration đã bật.
6. **Đặt transaction tại service boundary.** Một public method `@Transactional(transactionManager = "mongoTransactionManager")` được caller gọi qua Spring proxy.
7. **Đưa mọi MongoDB operation cần commit chung vào scope.** Không trộn raw driver session ngoài transaction hoặc thread mới.
8. **Kiểm tra kết quả write.** `matchedCount=0` của debit/credit phải được xử lý như một lỗi nghiệp vụ phù hợp.
9. **Không nuốt rollback exception.** Chỉ rõ `rollbackFor` với checked exception khi cần.
10. **Giữ scope ngắn.** Không giữ transaction qua HTTP, email, user input hoặc công việc nền lâu.
11. **Bổ sung idempotency.** Transfer ID và unique business key để bảo vệ trước retry/unknown commit outcome.
12. **Viết integration test trên replica set.** Assert cả happy path và lỗi sau debit nhưng trước credit phải rollback.
13. **Đo contention và latency.** Test với dữ liệu, concurrency, failover và write concerns đại diện.
14. **Triển khai và giám sát.** Theo dõi tỷ lệ abort/retry, latency, operational errors và kết quả đối soát.

~~~mermaid
flowchart TD
    A["Nghiệp vụ đa document"] --> B["MongoDB replica set / sharded cluster"]
    B --> C["MongoDatabaseFactory"]
    C --> D["Bean MongoTransactionManager"]
    D --> E["@EnableTransactionManagement + @Transactional"]
    E --> F["MongoTemplate / repository trong session"]
    F --> G{"Mọi bước và invariant đều đạt?"}
    G -->|"Có"| H["Commit"]
    G -->|"Không"| I["Rollback"]
    H --> J["Outbox/idempotency/observability"]
    I --> J
    J --> K["Integration test + production metrics"]
~~~

## 23. Bài tập thực hành

**Bài 1 — Đăng ký bean.** Tạo `MongoTransactionConfig` có `@Bean("mongoTransactionManager")` nhận `MongoDatabaseFactory`. Kiểm tra application context có đúng một MongoDB manager dự kiến.

**Bài 2 — Bật quản lý giao dịch.** Thêm `@EnableTransactionManagement` rồi tạo service method `@Transactional`. Gọi qua bean được inject; đối chiếu với self-invocation để giải thích khác biệt.

**Bài 3 — Topology test.** So sánh MongoDB standalone với single-node replica set dùng cho test. Ghi lỗi cụ thể khi transaction không được server hỗ trợ, không “sửa” bằng cách bỏ transaction.

**Bài 4 — Two-document transfer.** Seed A=100000, B=20000. Chuyển 30000 với service transaction; assert số dư mới và tổng tiền không đổi.

**Bài 5 — Rollback sau debit.** Gọi chuyển từ A đến account không tồn tại. Assert A trở lại 100000 sau exception. Thử tạm bỏ annotation trong môi trường test để thấy sự khác biệt.

**Bài 6 — Rollback rules.** Viết method ném checked exception sau update. So sánh không có và có `rollbackFor`; giải thích vì sao unchecked và checked có hành vi mặc định khác nhau.

**Bài 7 — Exception swallowing.** Bắt exception bên trong service và return bình thường; quan sát nguy cơ commit. Sửa để interceptor nhận được rollback signal và test lại.

**Bài 8 — TransactionTemplate.** Tạo `TransactionTemplate` từ `mongoTransactionManager`, chuyển một đoạn work nhiều update vào callback và xác minh rollback khi ném exception.

**Bài 9 — Hai managers.** Cấu hình MongoDB và JDBC/JPA transaction managers trong test demo. Chỉ rõ bean name bằng `@Transactional(transactionManager=...)`; kiểm tra việc chọn nhầm manager không bảo vệ MongoDB.

**Bài 10 — Session propagation.** Dùng một method transaction cập nhật account bằng `MongoTemplate` và repository. Xác minh cùng commit/rollback; sau đó đánh giá rủi ro một native driver call không truyền session.

**Bài 11 — Imperative vs reactive.** Mô tả khi nào dùng `MongoTransactionManager` và `ReactiveMongoTransactionManager`. Tạo reactive flow đơn giản với `TransactionalOperator` trên một replica set test.

**Bài 12 — Propagation.** Tạo helper `Propagation.MANDATORY` để ghi ledger, gọi từ ngoài/đang ở transaction. Đối chiếu với `REQUIRED`, tránh mặc định `NESTED` có savepoint.

**Bài 13 — Idempotency.** Mô phỏng transaction đã commit nhưng response mất. Thiết kế transfer ID có unique index để replay không chuyển tiền lần hai.

**Bài 14 — Outbox.** Ghi document chuyển trạng thái và outbox message trong cùng transaction; để worker riêng publish với retry và deduplication.

**Bài 15 — Concurrency benchmark.** Gửi nhiều transfer cạnh tranh cùng tài khoản nguồn trên replica set test; thống kê write conflicts, retries và độ trễ. Kiểm tra invariant, không chỉ throughput.

**Bài 16 — Consistency và concerns.** Dùng một workload có secondary reads, thay đổi read/write concerns theo policy, quan sát lag và giải thích tại sao transaction commit không tự đồng nghĩa mọi secondary đọc được dữ liệu mới ngay.

## 24. Ghi nhớ

**Đăng ký `MongoTransactionManager`** là bước nối Spring transaction abstraction với MongoDB `ClientSession` và transaction trên server. Với Spring Data MongoDB imperative, cấu hình nền tảng là **`@Bean("mongoTransactionManager")` nhận cùng `MongoDatabaseFactory`** mà `MongoTemplate`/repository sử dụng, kết hợp **`@EnableTransactionManagement`** hoặc xác minh Spring transaction interception đã được bật.

**`@Transactional` phải được gọi qua đúng Spring proxy, chọn đúng transaction manager và chạy trên MongoDB topology hỗ trợ**. Một method với hai update không tự all-or-nothing nếu thiếu manager/session; khi có transaction hoạt động, exception phù hợp có thể abort toàn bộ thao tác MongoDB trong scope. Muốn chứng minh điều đó, **test rollback sau khi debit đã khớp nhưng credit thất bại** trên replica set thật, chứ không chỉ assert method ném exception.

Cuối cùng, **transaction không thay idempotency, authorization, unique constraints, write concerns hoặc xử lý kết quả commit chưa rõ**. Giữ transaction ngắn, tránh external side effects trong scope, dùng outbox khi cần publish, và phân biệt imperative `MongoTransactionManager` với reactive `ReactiveMongoTransactionManager`. Mục tiêu không phải “bật transaction ở khắp nơi”, mà là đặt **đúng ranh giới nhất quán cho đúng nghiệp vụ và xác minh bằng MongoDB thực**.
