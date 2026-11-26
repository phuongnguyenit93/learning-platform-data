# Xây dựng CRUD khách hàng bằng Repository và Template trong Spring Data Couchbase

> **Chương:** Bài thực hành  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng Spring Data với document mapping, Repository, `CouchbaseTemplate` và SQL++; tổ chức bucket/scope/collection, sử dụng CAS, độ bền ghi, TTL và API reactive nhằm đảm bảo tính đúng đắn và khả năng vận hành.

## 1. Mục tiêu và sản phẩm đầu ra

Bài thực hành hướng dẫn xây dựng **một REST API quản lý khách hàng** với **hai cách triển khai tầng lưu trữ có thể hoán đổi**:

- **Repository**: dùng `CouchbaseRepository` để CRUD theo ID và derived query theo `status`.
- **Template**: dùng `CouchbaseTemplate` fluent operations `insertById`, `findById`, `replaceById`, `removeById` và `findByQuery`.

Sau khi hoàn thành, bạn có thể:

1. Kết nối Spring Boot với Couchbase bằng cấu hình và quyền tối thiểu.
2. Thiết kế key `customer::<customerCode>` và document JSON.
3. Mapping Java entity bằng `@Document`, `@Id`, `@Version`, `@Scope`, `@Collection`.
4. Viết các thao tác **Create / Read / Update / Delete** bằng Repository và Template.
5. Tìm khách hàng theo trạng thái qua SQL++/GSI thay vì quét toàn bucket tùy tiện.
6. Chống ghi đè đồng thời bằng **CAS/optimistic locking** khi cập nhật.
7. Phân biệt `insert`, `upsert`, `replace`, `save` và `delete` về semantics.
8. Kiểm tra CRUD bằng HTTP, JUnit/Spring Boot Test và các ca lỗi.
9. Giải thích khác biệt giữa **KV read theo ID**, **SQL++ query theo thuộc tính**, durability và query scan consistency.
10. Biết những phần cần gia cố trước production: authentication, tenant isolation, idempotency, indexes, observability, recovery.

### 1.1. Hợp đồng HTTP của bài lab

| Chức năng | HTTP | Đường xử lý |
|---|---|---|
| Tạo khách hàng | `POST /customers` | Create-only; trùng mã trả conflict |
| Đọc theo mã | `GET /customers/{code}` | KV theo document ID |
| Cập nhật | `PUT /customers/{code}` | Read–validate–replace với CAS |
| Xóa | `DELETE /customers/{code}` | KV delete theo ID |
| Lọc theo trạng thái | `GET /customers?status=ACTIVE` | SQL++ / GSI |

**Điểm học trọng tâm:** cùng một API và cùng entity, chuyển `app.customer.backend=repository` sang `template` để so sánh đường triển khai. Hai backend được chọn **lúc khởi động**, không cho một request tùy ý đổi backend.

## 2. Bối cảnh nghiệp vụ và giới hạn thiết kế

Một khách hàng gồm:

~~~json
{
  "customerCode": "CUS-001",
  "fullName": "Nguyen Thi Lan",
  "email": "lan@example.test",
  "status": "ACTIVE",
  "createdAt": "2026-11-25T02:00:00Z",
  "updatedAt": "2026-11-25T02:00:00Z"
}
~~~

Trong Couchbase, document ID được chọn:

~~~text
customer::CUS-001
~~~

`customerCode` là **mã nghiệp vụ do caller cung cấp**, có ràng buộc ký tự và được dùng để tạo ID ổn định. Nhờ vậy:

- Tạo hai khách hàng có cùng mã sẽ va chạm trên **cùng một document ID**.
- Không đưa email/số điện thoại/PII vào document key.
- Có thể đọc, cập nhật, xóa bằng KV mà không cần chỉ mục phụ.
- Query theo `status` vẫn cần chỉ mục SQL++ phù hợp.

**Giới hạn:** ID chỉ bảo đảm không có hai documents **cùng ID** trong collection; nó **không** tự bảo đảm email là duy nhất hay một khách hàng không bị đăng ký bằng hai mã khác nhau. Nếu email cần unique, phải thiết kế ràng buộc nghiệp vụ/dedup riêng; một GSI thông thường không phải unique constraint như một RDBMS.

### 2.1. Ranh giới của lab

- Chạy ở **bucket thử nghiệm**, dùng dữ liệu giả và tài khoản RBAC riêng.
- Một backend xử lý sync MVC. Phần reactive là bài nâng cao, không trộn hai kiểu execution vô ý.
- `createdAt`/`updatedAt` là chuỗi ISO-8601 UTC để ví dụ dễ đọc và tránh phụ thuộc converter thời gian nâng cao.
- Không đưa tenant đa khách hàng, payment, external side effects hay email thật vào phiên bản đầu.
- Không giả định môi trường một Data node bảo vệ dữ liệu khi node đó mất hoàn toàn.
- Không thao tác production hay tự tạo bucket/index qua mỗi lần ứng dụng khởi động.

## 3. Luồng dữ liệu và phân chia trách nhiệm

~~~mermaid
flowchart LR
    HTTP["HTTP Client"]
    Controller["CustomerController"]
    Service["CustomerService<br/>validation / CAS"]
    Port["CustomerStore interface"]
    Repo["RepositoryCustomerStore<br/>CouchbaseRepository"]
    Template["TemplateCustomerStore<br/>CouchbaseTemplate"]
    KV["Couchbase Data Service<br/>KV by ID"]
    Query["Query + Index Service<br/>SQL++ / GSI"]
    HTTP --> Controller --> Service --> Port
    Port --> Repo
    Port --> Template
    Repo -->|"CRUD ID"| KV
    Template -->|"CRUD ID"| KV
    Repo -->|"findByStatus"| Query
    Template -->|"findByQuery"| Query
~~~

| Tầng | Trách nhiệm | Không nên làm |
|---|---|---|
| Controller | HTTP path, status, validation đầu vào | Tạo query trực tiếp từ body tùy ý |
| Service | Key nghiệp vụ, chuẩn hóa, rule cập nhật, lỗi domain | Giả định `existsById` trước `insert` là chống race |
| `CustomerStore` | Contract lưu trữ chung | Lộ Couchbase SDK types ra controller |
| Repository adapter | Spring Data CRUD, query derivation | Dùng `findAll` trên bucket lớn mà chưa có index/pagination |
| Template adapter | Fluent operations, tùy biến query/durability | Dùng `upsert` thay `insert` chỉ để “đỡ lỗi trùng” |
| Couchbase | KV theo ID, SQL++/GSI, CAS, replication | Tự hiểu ràng buộc email unique hoặc HTTP idempotency |

## 4. Chuẩn bị môi trường

### 4.1. Công cụ

- JDK tương thích với phiên bản Spring Boot đã chọn (ví dụ Java 21).
- Maven hoặc Gradle; IDE Java.
- Couchbase Server 7.x/phiên bản hiện hành hoặc Capella deployment có hỗ trợ scope/collection.
- Công cụ chạy HTTP: `curl`, HTTP client của IDE hoặc Postman.
- Quyền tạo **bucket/scope/collection/index trên lab** do DBA/SRE cấp cho người thực hiện setup.
- Tài khoản runtime chỉ có quyền cần thiết để thao tác keyspace và thực thi query.

Không cố ghép các major version Spring Boot/Spring Data/Java SDK không tương thích. Hãy chọn **một BOM Spring Boot tương thích từ Spring Initializr**, rồi để Spring Boot quản lý dependency versions.

### 4.2. Khởi tạo project bằng Spring Initializr

Tên gợi ý: `customer-couchbase-lab`; package Java `com.example.customer`. Chọn dependencies:

- **Spring Web**
- **Spring Data Couchbase**
- **Validation**
- **Spring Boot Test**

Phần `pom.xml` dưới đây là **đoạn dependencies** để đối chiếu trong project đã được Initializr tạo; parent/BOM và metadata project do Initializr cung cấp:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-couchbase</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Để giữ ví dụ độc lập với một số release patch cụ thể, bài không hardcode Spring Boot version vào fragment này. Khi triển khai, khóa phiên bản và lưu kết quả kiểm thử tương thích trong build thực tế.

### 4.3. Cấu trúc mã nguồn

~~~text
src/main/java/com/example/customer/
  CustomerCrudApplication.java
  CustomerDocument.java
  CustomerStatus.java
  CustomerRepository.java
  CustomerStore.java
  RepositoryCustomerStore.java
  TemplateCustomerStore.java
  CustomerRequests.java (hoặc các record tách file)
  CustomerService.java
  CustomerController.java
  CustomerExceptionHandler.java
src/main/resources/
  application.yml
src/test/java/com/example/customer/
  CustomerCrudIntegrationTest.java
~~~

**Quy ước mã:** mọi snippet Java bên dưới thuộc package `com.example.customer`. Khi tạo tệp thực, thêm `package com.example.customer;` và các imports được hiển thị; các record public phải tách file theo quy tắc Java nếu không đặt là nested type.

## 5. Tạo bucket, scope và collection trong lab

Ví dụ keyspace:

~~~text
Bucket: customer_lab
Scope:  crm
Collection: customers

customer_lab.crm.customers
~~~

Thực hiện qua Couchbase Web Console hoặc công cụ quản trị được tổ chức phê duyệt:

1. Tạo bucket `customer_lab` loại Couchbase, cấu hình memory/disk phù hợp quota lab.
2. Chọn replica count phù hợp **số Data nodes**: một Data node để học KV có thể dùng 0 replica; hai Data nodes có thể dùng 1 replica.
3. Tạo scope `crm` và collection `customers`.
4. Cấp quyền cho tài khoản ứng dụng trên đúng bucket/keyspace, và quyền SQL++/Index cần thiết cho thao tác đọc theo thuộc tính.
5. Kiểm tra status các Data/Query/Index Services.
6. Đảm bảo ứng dụng có thể kết nối qua TLS và certificate trust chain nếu dùng Capella.

### 5.1. Tránh trộn quyền setup và quyền runtime

Tài khoản tạo bucket/index là tài khoản **quản trị lab**; tài khoản `customer-api` chạy ứng dụng chỉ nên có quyền cần thiết. Không ghi admin username/password trong `application.yml` của mã nguồn hoặc log.

### 5.2. Chỉ mục cho tìm kiếm theo trạng thái

Repo `findById` và Template `findById` dùng **KV**, không cần GSI. Nhưng `findByStatus`/`findByQuery` là SQL++ và cần secondary index thích hợp:

~~~sql
CREATE INDEX ix_customers_status
ON `customer_lab`.`crm`.`customers`(status, customerCode);
~~~

Vì đây là lab về một entity, bạn có thể dùng một index như trên để bắt đầu. Spring Data Couchbase thường thêm discriminator `_class` vào document và query; nếu planner không chọn index, xem `EXPLAIN` và predicate thực tế trước khi điều chỉnh DDL.

Ví dụ SQL++ để đối chiếu:

~~~sql
SELECT META(c).id AS id, c.customerCode, c.fullName,
       c.email, c.status
FROM `customer_lab`.`crm`.`customers` AS c
WHERE c.status = "ACTIVE"
LIMIT 20;
~~~

Không tạo **primary index trên production** chỉ để xử lý mọi query thiếu index. Một primary index trong lab có thể hữu ích để debug `findAll`, nhưng không thay bước thiết kế index theo predicate.

## 6. Cấu hình Spring Boot

Ví dụ `src/main/resources/application.yml`:

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_CONNECTION_STRING}"
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"
  data:
    couchbase:
      bucket-name: customer_lab

app:
  customer:
    backend: repository   # Đổi thành template để chạy cùng HTTP API
server:
  port: 8080
~~~

Các biến môi trường cần có:

~~~text
CB_CONNECTION_STRING=couchbase://127.0.0.1
CB_USERNAME=customer-api
CB_PASSWORD=<đặt bằng secret manager hoặc biến môi trường>
~~~

Trong container/Capella, `CB_CONNECTION_STRING` có thể là `couchbases://...` với TLS; không tắt xác minh certificate để xử lý lỗi kết nối. Trong lab có thể dùng quyền tối thiểu theo bucket/scope/collection.

### 6.1. Application class

~~~java
package com.example.customer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomerCrudApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomerCrudApplication.class, args);
    }
}
~~~

**Không cần** tự tạo `Cluster.connect(...)` mỗi khi nhận HTTP request. Spring Boot tự cấu hình các bean Spring Data/Template khi dependencies, kết nối và bucket name hợp lệ.

## 7. Entity: Document ID, CAS và trạng thái

### 7.1. Enum trạng thái

~~~java
package com.example.customer;

public enum CustomerStatus {
    ACTIVE,
    INACTIVE
}
~~~

### 7.2. Entity mapping

~~~java
package com.example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("crm")
@Collection("customers")
public class CustomerDocument {
    @Id
    private String id;

    @Version
    private Long version;

    private String customerCode;
    private String fullName;
    private String email;
    private CustomerStatus status;
    private String createdAt;
    private String updatedAt;

    public CustomerDocument() {}

    public CustomerDocument(
            String id, String customerCode, String fullName,
            String email, CustomerStatus status,
            String createdAt, String updatedAt) {
        this.id = id;
        this.customerCode = customerCode;
        this.fullName = fullName;
        this.email = email;
        this.status = status;
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }

    public String getCustomerCode() { return customerCode; }
    public void setCustomerCode(String customerCode) {
        this.customerCode = customerCode;
    }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public CustomerStatus getStatus() { return status; }
    public void setStatus(CustomerStatus status) { this.status = status; }

    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }

    public String getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(String updatedAt) {
        this.updatedAt = updatedAt;
    }
}
~~~

### 7.3. Vì sao dùng `Long version`?

`@Version` lưu **CAS token** của Couchbase theo Spring Data mapping. Nó là **opaque value**, không phải số lần cập nhật tăng một đơn vị. Khi một writer khác thay document, CAS thay đổi; replace dựa trên CAS cũ có thể bị từ chối.

- Entity mới có `version == null`. Với Spring Data Couchbase, `save` có thể chọn **insert** nếu entity version chưa có giá trị; entity đã có version thì dùng **replace**.
- Không tự tăng hoặc tự tạo `version` trong service.
- Đưa version ra REST dạng **chuỗi** để không mất độ chính xác ở các client JavaScript chỉ hỗ trợ integer 53-bit.
- `@Version` không thay độ bền ghi. CAS và durability là hai lựa chọn khác nhau.

### 7.4. JSON thực tế và metadata

Couchbase KV key `customer::CUS-001` không nhất thiết là một field JSON `id`; Spring Data mapping dùng `@Id` để gắn key. `@Version` đọc CAS từ metadata; không nên tự coi nó là một trường version tăng tuần tự trong body JSON. Spring Data còn có thể lưu type discriminator `_class`.

## 8. DTO và validation: không cho client sửa CAS, ID trực tiếp

Một API public không nên nhận trực tiếp `CustomerDocument` làm body. Tách record yêu cầu và response để tránh cho client gán `id`, `version`, thời gian và field nội bộ.

### 8.1. Create request

~~~java
package com.example.customer;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9_-]{3,40}")
    String customerCode,

    @NotBlank
    @Size(max = 120)
    String fullName,

    @NotBlank
    @Email
    @Size(max = 254)
    String email
) {}
~~~

### 8.2. Update request

~~~java
package com.example.customer;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record UpdateCustomerRequest(
    @NotBlank String expectedVersion,

    @NotBlank @Size(max = 120) String fullName,

    @NotBlank @Email @Size(max = 254) String email,

    @NotNull CustomerStatus status
) {}
~~~

### 8.3. Response

~~~java
package com.example.customer;

public record CustomerResponse(
    String customerCode,
    String fullName,
    String email,
    CustomerStatus status,
    String version,
    String createdAt,
    String updatedAt
) {}
~~~

`expectedVersion` do client giữ từ response trước đó. So sánh nó với **version của document mới đọc** trước khi update; sau đó **CAS của bản vừa đọc** bảo vệ khoảng race giữa read và replace. Không cho client trực tiếp chỉnh version trên entity.

## 9. Repository: bắt đầu từ API đơn giản nhất

~~~java
package com.example.customer;

import java.util.List;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.ScanConsistency;

public interface CustomerRepository
        extends CouchbaseRepository<CustomerDocument, String> {

    @ScanConsistency(query = QueryScanConsistency.REQUEST_PLUS)
    List<CustomerDocument> findByStatus(CustomerStatus status);
}
~~~

Các method có sẵn:

~~~text
save(customer)
findById(id)
existsById(id)
deleteById(id)
delete(customer)
findAll()
count()
~~~

**Đường thực thi không đồng nhất:**

- `findById(id)`, `deleteById(id)`, `save(entity)` (single-document) sử dụng đường KV tương ứng.
- `findByStatus(status)` là derived query SQL++ và phụ thuộc Index Service/GSI.
- `findAll()` hoặc `count()` thường cần SQL++/index; không dùng vô điều kiện trên collection lớn.
- `REQUEST_PLUS` trên method tìm kiếm yêu cầu Index Service chờ index bắt kịp mốc query; có thể tăng latency.

### 9.1. Tại sao không dùng `existsById` rồi `save` để bảo đảm unique?

~~~java
// Phản ví dụ: hai requests đồng thời có thể cùng thấy false.
if (!repository.existsById(id)) {
    repository.save(customer);
}
~~~

Kiểm tra-đầu-tiên-rồi-ghi **không atomic**. Hãy dùng **create-only insert**: Repository `save` trên entity có `@Version == null` theo semantics hiện hành chọn insert; Template `insertById` luôn thể hiện create-only rõ ràng.

**Quan trọng:** Behavior của `save` chịu state detection; test case trùng ID phải là một phần acceptance suite khi đổi version/dependency.

## 10. Tạo một contract chung cho hai backend

~~~java
package com.example.customer;

import java.util.List;
import java.util.Optional;

public interface CustomerStore {
    CustomerDocument insert(CustomerDocument customer);
    Optional<CustomerDocument> findById(String id);
    CustomerDocument replace(CustomerDocument customer);
    void removeById(String id);
    List<CustomerDocument> findByStatus(CustomerStatus status);
}
~~~

Nhờ interface này, Controller và Service không cần biết request sẽ dùng Repository hay Template. Tránh lặp business validation ở từng backend.

## 11. Adapter dùng Repository

~~~java
package com.example.customer;

import java.util.List;
import java.util.Optional;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    name = "app.customer.backend",
    havingValue = "repository",
    matchIfMissing = true
)
public class RepositoryCustomerStore implements CustomerStore {

    private final CustomerRepository repository;

    public RepositoryCustomerStore(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public CustomerDocument insert(CustomerDocument customer) {
        // @Version null => new entity => insert, không upsert.
        return repository.save(customer);
    }

    @Override
    public Optional<CustomerDocument> findById(String id) {
        return repository.findById(id);
    }

    @Override
    public CustomerDocument replace(CustomerDocument customer) {
        // Entity đọc từ DB có @Version => replace dùng CAS.
        return repository.save(customer);
    }

    @Override
    public void removeById(String id) {
        repository.deleteById(id);
    }

    @Override
    public List<CustomerDocument> findByStatus(CustomerStatus status) {
        return repository.findByStatus(status);
    }
}
~~~

### 11.1. Trade-off của adapter Repository

Ưu điểm: ít boilerplate, dễ đọc, thuận lợi với CRUD phổ biến và derived queries. Nhược điểm: không diễn đạt rõ tùy chọn per-operation như durability, expiry hoặc policy query đặc biệt ngay tại từng method nếu không bổ sung annotation/template.

### 11.2. Chú ý về xóa

`deleteById` xóa theo key; **bản demo chưa yêu cầu CAS khi xóa**. Nếu API cần bảo vệ trường hợp khách hàng bị sửa giữa lần đọc và lệnh DELETE, hãy yêu cầu version từ caller và xóa có CAS bằng Template/SDK hoặc adapter chuyên biệt; không coi pre-read `existsById` là atomic guard.

## 12. Adapter dùng CouchbaseTemplate

~~~java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.data.couchbase.core.query.Query;
import org.springframework.data.couchbase.core.query.QueryCriteria;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    name = "app.customer.backend",
    havingValue = "template"
)
public class TemplateCustomerStore implements CustomerStore {

    private final CouchbaseTemplate template;

    public TemplateCustomerStore(CouchbaseTemplate template) {
        this.template = template;
    }

    @Override
    public CustomerDocument insert(CustomerDocument customer) {
        return template
                .insertById(CustomerDocument.class)
                .one(customer);
    }

    @Override
    public Optional<CustomerDocument> findById(String id) {
        return Optional.ofNullable(
                template.findById(CustomerDocument.class).one(id)
        );
    }

    @Override
    public CustomerDocument replace(CustomerDocument customer) {
        return template
                .replaceById(CustomerDocument.class)
                .one(customer);
    }

    @Override
    public void removeById(String id) {
        template.removeById(CustomerDocument.class).one(id);
    }

    @Override
    public List<CustomerDocument> findByStatus(CustomerStatus status) {
        Query query = Query.query(
            QueryCriteria.where("status").is(status.name())
        );
        return template
                .findByQuery(CustomerDocument.class)
                .matching(query)
                .withConsistency(QueryScanConsistency.REQUEST_PLUS)
                .all();
    }
}
~~~

### 12.1. Một lựa chọn Template có chủ đích

- `insertById`: không tạo trùng ID.
- `findById`: KV theo ID; không cần GSI.
- `replaceById`: thay document đã tồn tại; với entity có CAS, test optimistic locking.
- `removeById`: xóa một key; có thể bổ sung `withCas(...)` khi hợp đồng xóa yêu cầu.
- `findByQuery`: sử dụng SQL++, Index Service và predicate rõ ràng.

### 12.2. Vì sao không dùng `upsertById` cho Create?

`upsertById` có thể **ghi đè** document cùng ID. Dùng nó cho chức năng “tạo khách hàng mới, không được ghi đè” sẽ làm hỏng semantics nếu mã đã tồn tại. `upsert` phù hợp các nghiệp vụ mà tạo-hoặc-thay là lựa chọn có chủ đích.

### 12.3. Tại sao phải chỉ rõ entity type?

Template cần `CustomerDocument.class` để sử dụng mapping, scope/collection và converter. Khác với repository đã biết type từ generic parameters, Template API fluent thường yêu cầu domain class ở mỗi thao tác.

## 13. Chọn backend bằng một property

Hai implementation `CustomerStore` đều có `@ConditionalOnProperty`. Chỉ một bean được tạo theo `app.customer.backend`:

~~~yaml
# Repository (mặc định khi không truyền property)
app:
  customer:
    backend: repository
~~~

~~~yaml
# Template
app:
  customer:
    backend: template
~~~

Đừng để Controller tự chọn backend theo tham số HTTP; điều đó khiến quyền truy cập, latency và chính sách ghi có thể thay đổi tùy caller. Trong lab, mỗi lần đổi backend hãy **khởi động lại** ứng dụng và chạy cùng bộ contract tests.

| Khía cạnh | Repository | Template |
|---|---|---|
| Create | `save` với `@Version == null` → insert | `insertById` thể hiện create-only rõ |
| Read ID | `findById` | `findById` |
| Update | `save` với CAS entity đã có | `replaceById` với CAS entity |
| Delete | `deleteById` | `removeById` |
| Query | Derived `findByStatus` | `findByQuery` và `QueryCriteria` |
| Tùy chọn operation | Metadata/annotation | Fluent `withDurability`, `withConsistency`, v.v. |

## 14. CustomerService: gom quy tắc nghiệp vụ một nơi

Lớp Service nhận `CustomerStore` và không cần biết adapter được chọn.

~~~java
package com.example.customer;

import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

import org.springframework.stereotype.Service;

@Service
public class CustomerService {
    private static final Pattern CODE =
        Pattern.compile("[A-Z0-9_-]{3,40}");

    private final CustomerStore store;

    public CustomerService(CustomerStore store) {
        this.store = store;
    }

    public CustomerResponse create(CreateCustomerRequest request) {
        String code = normalizeCode(request.customerCode());
        String now = Instant.now().toString();

        CustomerDocument customer = new CustomerDocument(
            keyFor(code), code, request.fullName().trim(),
            normalizeEmail(request.email()), CustomerStatus.ACTIVE,
            now, now
        );

        // Không làm check-then-insert: thao tác create-only
        // ở repository/template quyết định atomic về trùng ID.
        return toResponse(store.insert(customer));
    }

    public CustomerResponse get(String customerCode) {
        return toResponse(loadByCode(customerCode));
    }

    public CustomerResponse update(
            String customerCode, UpdateCustomerRequest request) {
        CustomerDocument current = loadByCode(customerCode);

        String actualVersion = String.valueOf(current.getVersion());
        if (!actualVersion.equals(request.expectedVersion())) {
            throw new Stale("Khách hàng đã được cập nhật.");
        }

        current.setFullName(request.fullName().trim());
        current.setEmail(normalizeEmail(request.email()));
        current.setStatus(request.status());
        current.setUpdatedAt(Instant.now().toString());

        // CAS vẫn bảo vệ race từ lần đọc tới lúc replace.
        return toResponse(store.replace(current));
    }

    public void delete(String customerCode) {
        CustomerDocument current = loadByCode(customerCode);
        store.removeById(current.getId());
    }

    public List<CustomerResponse> list(CustomerStatus status) {
        return store.findByStatus(status).stream()
                .map(CustomerService::toResponse)
                .toList();
    }

    private CustomerDocument loadByCode(String rawCode) {
        String id = keyFor(normalizeCode(rawCode));
        return store.findById(id)
                .orElseThrow(() -> new NotFound(
                    "Không tìm thấy khách hàng"
                ));
    }

    private static String keyFor(String code) {
        return "customer::" + code;
    }

    private static String normalizeCode(String raw) {
        if (raw == null) {
            throw new InvalidCode("Mã khách hàng không hợp lệ.");
        }
        String code = raw.trim().toUpperCase(Locale.ROOT);
        if (!CODE.matcher(code).matches()) {
            throw new InvalidCode("Mã khách hàng không hợp lệ.");
        }
        return code;
    }

    private static String normalizeEmail(String raw) {
        return raw.trim().toLowerCase(Locale.ROOT);
    }

    private static CustomerResponse toResponse(CustomerDocument doc) {
        return new CustomerResponse(
            doc.getCustomerCode(), doc.getFullName(),
            doc.getEmail(), doc.getStatus(),
            String.valueOf(doc.getVersion()),
            doc.getCreatedAt(), doc.getUpdatedAt()
        );
    }

    public static class NotFound extends RuntimeException {
        public NotFound(String message) { super(message); }
    }

    public static class Stale extends RuntimeException {
        public Stale(String message) { super(message); }
    }

    public static class InvalidCode extends RuntimeException {
        public InvalidCode(String message) { super(message); }
    }
}
~~~

### 14.1. Vì sao tạo mới không gọi `existsById` trước?

Hai request đồng thời có thể cùng thấy `existsById=false` rồi cùng cố tạo. Kiểm tra-đầu-tiên-rồi-ghi không atomic. `insert` là operation create-only ở server; khi trùng ID, một attempt phải bị từ chối. Test contract ở cả hai backend để xác nhận behavior của Spring Data phiên bản đang dùng.

### 14.2. Vì sao update kiểm tra version hai lần theo hai cơ chế?

- `expectedVersion` là version caller đã thấy trước khi gửi PUT. So với document mới đọc giúp phát hiện **client stale**.
- `@Version`/CAS ở mutation thực tế phát hiện **writer khác thay đổi giữa read và replace**.

Ngay cả hai service requests cùng qua được precheck, CAS chỉ cho một replace dùng CAS cũ thành công (trong điều kiện không có update khác). Không bỏ version đi khi gặp conflict; tải lại trạng thái rồi thực hiện business merge.

### 14.3. Giới hạn giản lược cần biết

Chuyển email về lowercase toàn bộ là **quy ước trong bài lab**, không phải chính sách canonical email áp dụng cho mọi hệ thống. Xóa hiện tại không gửi CAS; một writer khác có thể cập nhật giữa bước read và delete. Production muốn conditional delete phải bổ sung expected version và thao tác xóa có CAS.

## 15. Controller: HTTP contract không phụ thuộc Repository/Template

~~~java
package com.example.customer;

import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CustomerResponse> create(
            @Valid @RequestBody CreateCustomerRequest request) {
        CustomerResponse created = service.create(request);
        return ResponseEntity
                .created(URI.create(
                    "/customers/" + created.customerCode()
                ))
                .body(created);
    }

    @GetMapping("/{code}")
    public CustomerResponse get(@PathVariable String code) {
        return service.get(code);
    }

    @PutMapping("/{code}")
    public CustomerResponse update(
            @PathVariable String code,
            @Valid @RequestBody UpdateCustomerRequest request) {
        return service.update(code, request);
    }

    @DeleteMapping("/{code}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String code) {
        service.delete(code);
    }

    @GetMapping
    public List<CustomerResponse> list(
            @RequestParam(defaultValue = "ACTIVE")
            CustomerStatus status) {
        return service.list(status);
    }
}
~~~

### 15.1. Phân biệt đường Read

- `GET /customers/{code}` dùng KV theo ID (Repository/Template `findById`).
- `GET /customers?status=ACTIVE` dùng SQL++/Index Service; cần GSI phù hợp và scan consistency.

Không dùng một query theo email/trạng thái chỉ để biết một document theo ID có tồn tại; điều đó tăng độ trễ và rủi ro index lag.

### 15.2. HTTP status dự kiến

| Kịch bản | HTTP | Ghi chú |
|---|---:|---|
| Create thành công | 201 | Kèm `Location` |
| Read/List thành công | 200 | Body entity DTO/list |
| Update thành công | 200 | Kèm version mới |
| Delete thành công | 204 | Không có body |
| Input sai | 400 | Jakarta Validation + domain validation |
| ID không tồn tại | 404 | KV not found |
| Create trùng ID | 409 | Không ghi đè |
| Update CAS cũ | 409 | Client cần load lại |
| Index/cluster lỗi | 5xx phù hợp | Không biến thành danh sách rỗng |

## 16. ExceptionHandler: lỗi conflict/validation/404

Spring Data có exception translation; Java SDK cũng có những exception riêng. Ví dụ sau ánh xạ các loại phổ biến, **không bắt mọi RuntimeException rồi trả 409**.

~~~java
package com.example.customer;

import com.couchbase.client.core.error.DocumentExistsException;
import com.couchbase.client.core.error.DocumentNotFoundException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class CustomerExceptionHandler {
    private ResponseEntity<ProblemDetail> fail(
            HttpStatus status, String message) {
        return ResponseEntity.status(status).body(
            ProblemDetail.forStatusAndDetail(status, message)
        );
    }

    @ExceptionHandler({
        CustomerService.NotFound.class,
        DocumentNotFoundException.class
    })
    public ResponseEntity<ProblemDetail> notFound(Exception ex) {
        return fail(HttpStatus.NOT_FOUND, "Khách hàng không tồn tại.");
    }

    @ExceptionHandler(CustomerService.InvalidCode.class)
    public ResponseEntity<ProblemDetail> badCode(Exception ex) {
        return fail(HttpStatus.BAD_REQUEST, "Mã khách hàng không hợp lệ.");
    }

    @ExceptionHandler({
        DocumentExistsException.class,
        DuplicateKeyException.class
    })
    public ResponseEntity<ProblemDetail> duplicate(Exception ex) {
        return fail(HttpStatus.CONFLICT, "Mã khách hàng đã tồn tại.");
    }

    @ExceptionHandler({
        CustomerService.Stale.class,
        OptimisticLockingFailureException.class
    })
    public ResponseEntity<ProblemDetail> stale(Exception ex) {
        return fail(HttpStatus.CONFLICT, "Phiên bản đã cũ, cần tải lại.");
    }
}
~~~

### 16.1. Kiểm tra exception translation thực tế

Trong integration test hãy xác nhận:

1. Backend Repository tạo trùng ID phát exception loại nào.
2. Backend Template tạo trùng ID phát exception loại nào.
3. CAS mismatch trong mỗi backend được bọc như thế nào.
4. Delete missing/Query no index được phân loại khác duplicate ra sao.

Nếu lỗi thực tế được bọc trong một `DataAccessException` khác, sửa handler **theo loại đã quan sát**, không bắt catch-all trả 200 hay 409. Lỗi timeout ambiguous không được coi như chắc chắn chưa insert.

### 16.2. Không trả stack trace chứa dữ liệu nhạy cảm

Báo cáo HTTP nên chứa mã lỗi, message an toàn và correlation ID; credentials, email khách hàng, raw query parameters hoặc stacktrace có PII không được lộ cho caller.

## 17. Thao tác bằng HTTP client theo thứ tự

Khởi động với `app.customer.backend=repository` và keyspace lab đã tạo. Thực hiện chuỗi dưới đây; sau đó đổi sang `template`, khởi động lại và sử dụng mã khác như `TPL-001`.

### 17.1. POST tạo khách hàng

~~~http
POST /customers HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{
  "customerCode": "CUS-001",
  "fullName": "Nguyen Thi Lan",
  "email": "lan@example.test"
}
~~~

Kỳ vọng status 201:

~~~http
HTTP/1.1 201 Created
Location: /customers/CUS-001
Content-Type: application/json
~~~

Body minh họa:

~~~json
{
  "customerCode": "CUS-001",
  "fullName": "Nguyen Thi Lan",
  "email": "lan@example.test",
  "status": "ACTIVE",
  "version": "<CAS_TOKEN_TU_SERVER>",
  "createdAt": "2026-11-25T02:00:00Z",
  "updatedAt": "2026-11-25T02:00:00Z"
}
~~~

`version` là **opaque CAS token**. Không nhập literal `<CAS_TOKEN_TU_SERVER>` vào lệnh PUT; phải dùng chính chuỗi version thật từ response.

### 17.2. GET theo mã

~~~http
GET /customers/CUS-001 HTTP/1.1
Host: localhost:8080
~~~

Kỳ vọng 200. Đây là KV read theo key `customer::CUS-001`, không cần GSI.

### 17.3. PUT cập nhật dùng version của GET

~~~http
PUT /customers/CUS-001 HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{
  "expectedVersion": "<VERSION_THAT_SU_TU_GET>",
  "fullName": "Nguyen Thi Lan Anh",
  "email": "lan.anh@example.test",
  "status": "INACTIVE"
}
~~~

Kỳ vọng 200 và version khác bản cũ. Thử gửi lại **cùng expectedVersion cũ** sau khi update đã commit: kỳ vọng 409, không overwrite lần cập nhật trước.

### 17.4. GET danh sách trạng thái

~~~http
GET /customers?status=ACTIVE HTTP/1.1
Host: localhost:8080
~~~

Kỳ vọng 200 với danh sách các khách hàng ACTIVE. Nếu khách hàng vừa được đổi sang INACTIVE sẽ không thuộc danh sách này; query phụ thuộc GSI và consistency đã cấu hình.

### 17.5. DELETE và kiểm tra sau xóa

~~~http
DELETE /customers/CUS-001 HTTP/1.1
Host: localhost:8080
~~~

Kỳ vọng 204. Sau đó GET cùng mã phải trả 404.

### 17.6. Các trường hợp âm phải chạy

- POST hai lần với cùng code → conflict, không thay body có trước.
- POST code không hợp lệ → 400.
- POST email rỗng/format sai → 400.
- GET code chưa tồn tại → 404.
- PUT với version stale → 409.
- List khi Query/Index service lỗi → không giả danh 200 với array rỗng.
- DELETE code chưa tồn tại → phân loại theo hợp đồng 404 đã chọn ở lab.

## 18. So sánh cùng một luồng trên hai backend

| Bước | Repository | Template |
|---|---|---|
| Create | `repository.save(newEntity)` | `template.insertById(...).one` |
| Read | `repository.findById` | `template.findById(...).one` |
| Update | `repository.save(existing)` | `template.replaceById(...).one` |
| Delete | `repository.deleteById` | `template.removeById(...).one` |
| Search | `findByStatus` | `findByQuery` |
| Query consistency | `@ScanConsistency(REQUEST_PLUS)` | `withConsistency(REQUEST_PLUS)` |

**Không sửa Service hay Controller khi đổi backend.** Mỗi backend dùng chung domain key/value và collection; do đó dữ liệu của backend Repository vẫn nhìn thấy bằng Template và ngược lại. Dùng mã riêng cho từng vòng test hoặc dọn dữ liệu trước khi chạy lại.

Trong các hệ thống lớn, không nên cho caller tự chọn backend theo query parameter vì có thể vô tình bỏ qua chính sách vận hành. Ở đây đổi backend chỉ là phương pháp học hai API của Spring Data Couchbase.

## 19. Kiểm thử tích hợp Repository với Couchbase lab

Unit test dùng mock `CustomerStore` có thể kiểm tra validation, nhưng không chứng minh Repository/Template mapping đúng scope/collection, CAS, SQL++ index hoặc exception translation. Các ca quan trọng nên được thử với **cluster lab có thật**.

### 19.1. Điều kiện trước test

- `customer_lab.crm.customers` đã tồn tại.
- Tài khoản ứng dụng có quyền KV và SQL++ cần thiết.
- Index `ix_customers_status` đã online.
- Biến môi trường `CB_CONNECTION_STRING`, `CB_USERNAME` và `CB_PASSWORD` trỏ tới đúng **lab**, không phải production.
- Chỉ chạy test khi bật `RUN_CB_IT=true`.

Ví dụ test Spring Boot:

~~~java
package com.example.customer;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = "app.customer.backend=repository")
@EnabledIfEnvironmentVariable(named = "RUN_CB_IT", matches = "true")
class CustomerRepositoryIT {
    @Autowired
    CustomerService service;

    @Test
    void crudAndVersionGuard() {
        String code = "IT-" + UUID.randomUUID()
                .toString().substring(0, 8).toUpperCase();

        var created = service.create(new CreateCustomerRequest(
                code, "Nguyen Van A", "a@example.test"));
        assertEquals(code, created.customerCode());
        assertNotNull(created.version());

        var loaded = service.get(code);
        assertEquals(created.version(), loaded.version());

        var updated = service.update(code, new UpdateCustomerRequest(
                loaded.version(),
                "Nguyen Van B", "b@example.test",
                CustomerStatus.INACTIVE));

        assertEquals(CustomerStatus.INACTIVE, updated.status());
        assertNotEquals(loaded.version(), updated.version());

        assertThrows(CustomerService.Stale.class, () ->
            service.update(code, new UpdateCustomerRequest(
                loaded.version(),
                "Stale", "a@example.test",
                CustomerStatus.ACTIVE)));

        service.delete(code);
        assertThrows(CustomerService.NotFound.class,
                () -> service.get(code));
    }
}
~~~

`@EnabledIfEnvironmentVariable` giúp không chạy nhầm test khi thiếu cờ, nhưng **không tự tạo cluster** hay cấp quyền. Bài không thực thi test; mã này là nguồn tham khảo để người học đưa vào project đã tạo và vận hành trên lab.

### 19.2. Contract test tương đương cho Template

Dùng cùng assertions với một test class khác khai báo:

~~~java
@SpringBootTest(properties = "app.customer.backend=template")
@EnabledIfEnvironmentVariable(named = "RUN_CB_IT", matches = "true")
class CustomerTemplateIT {
    // Inject CustomerService và chạy lại bộ contract tests.
    // Mỗi test dùng customerCode mới để tránh trùng key.
}
~~~

Trong project thực tế, nên trích contract test reusable rồi chạy một lần theo mỗi backend. Khung lớp trên **chưa** là một test hoàn chỉnh; không copy rồi kỳ vọng nó tự kiểm thử tính đúng.

### 19.3. Test trùng ID

Tạo lần đầu mã `DUP-001`. Tạo lần hai cùng code nhưng `email` khác: kỳ vọng HTTP 409 hoặc exception duplicate đã được xác định. Sau đó KV `GET` phải vẫn thấy **dữ liệu lần đầu**, không bị upsert ghi đè. Đây là assertion quan trọng vì `repository.save` phụ thuộc new-entity detection của `@Version`.

### 19.4. Test query và GSI

Sau khi tạo customer ACTIVE, gọi `service.list(CustomerStatus.ACTIVE)` và assert danh sách chứa code đó. Nếu query không có index hoặc Query Service chưa online, phải sửa DDL/quyền/trạng thái index; không biến lỗi thành danh sách rỗng.

## 20. Hai clients cập nhật cùng lúc: CAS chặn lost update

Giả sử A và B vừa đọc `CUS-001`, cùng được cấp `version=V1`.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant API as Customer REST
    participant KV as Couchbase KV
    A->>API: GET CUS-001
    B->>API: GET CUS-001
    API-->>A: version V1
    API-->>B: version V1
    A->>API: PUT expectedVersion V1
    API->>KV: replace với CAS V1
    KV-->>API: success CAS V2
    API-->>A: 200 V2
    B->>API: PUT expectedVersion V1
    API-->>B: 409 conflict
~~~

**Hai lớp bảo vệ** cùng cần thiết:

1. Service so `expectedVersion` của caller với version mà request vừa đọc.
2. `@Version`/CAS được truyền tới mutation để xử lý cả tình huống hai service instances cùng đọc V1 và cùng đi tới bước ghi.

Không tự tính `V2=V1+1` vì CAS là opaque token. Không dùng `upsert` với body stale chỉ để né 409; điều đó có thể ghi đè thay đổi hợp lệ.

### 20.1. Conditional delete bằng CAS

Bản lab xóa theo ID, có pre-read nhưng không bắt buộc CAS. Khi business đòi chỉ xóa nếu record chưa thay đổi, mở rộng hợp đồng HTTP dùng expected version và thực hiện conditional remove. Template có API:

~~~java
template.removeById(CustomerDocument.class)
        .withCas(currentCas)
        .one("customer::CUS-001");
~~~

`currentCas` là `Long` CAS nhận từ lần đọc đúng document và đã được xác minh với version của caller. Repository delete theo entity có thể có semantics khác tùy version; phải kiểm thử trước khi hứa cùng mức bảo vệ.

## 21. Tìm kiếm theo `status`: khác biệt KV và SQL++

Đường CRUD theo ID định tuyến trực tiếp tới Data Service. Đường tìm theo `status` thông qua SQL++/Global Secondary Index (GSI):

~~~mermaid
flowchart LR
    HTTP["GET /customers?status=ACTIVE"]
    Repo["Repository findByStatus<br/>hoặc Template findByQuery"]
    Query["SQL++ Query Service"]
    GSI["Index Service"]
    Data["Data Service"]
    HTTP --> Repo --> Query --> GSI
    Query -.->|"Fetch nếu cần"| Data
~~~

**Điểm cần hiểu:** Spring Data Couchbase không tạo một bảng quan hệ cùng indexes tự động chỉ vì bạn viết `findByStatus`. Cần index phù hợp, kế hoạch `EXPLAIN` hợp lý và quyền SQL++/Index Service.

### 21.1. Index freshness và `REQUEST_PLUS`

GSI cập nhật bất đồng bộ qua DCP. Ngay sau create/update, `GET /customers/{id}` theo KV có thể đã thấy body mới, trong khi `NOT_BOUNDED` SQL++ chưa thấy. Bài đã chọn:

- Repository `@ScanConsistency(query = REQUEST_PLUS)`.
- Template `withConsistency(REQUEST_PLUS)`.

Hai lựa chọn yêu cầu Query Service chờ index theo mốc query và có thể tăng p95/p99 hoặc timeout khi Index Service chậm. Không đổi write durability để khắc phục một query stale.

### 21.2. Đừng dùng `findAll` trên collection lớn

Bài lab chỉ lấy danh sách nhỏ theo trạng thái. Ở production, thêm giới hạn số lượng, pagination và index phục vụ sort; không trả toàn bộ khách hàng vào memory. Chú ý data isolation nếu collection có nhiều tenants: `findByStatus` không có tenant predicate có thể rò dữ liệu.

## 22. Durability, CAS, TTL và idempotency giải quyết các vấn đề khác nhau

| Cơ chế | Mục đích chính | Không giải quyết |
|---|---|---|
| `@Version`/CAS | Tránh lost update cùng document | Replica/persistence |
| `DurabilityLevel.MAJORITY` | Chờ xác nhận majority trước success khi topology hỗ trợ | GSI freshness, email unique |
| TTL/expiry | Quy định vòng đời document | Exactly-once API |
| `REQUEST_PLUS` | Chờ chỉ mục mới hơn ở thời điểm query | Mutation durability |
| Stable document ID | Tránh tạo hai document cùng ID | Các side effect ngoài database |
| Idempotency key/fingerprint | Nhận biết retry cùng business command | Khôi phục cluster khi mất tất cả copies |

### 22.1. Dùng Template để đổi level theo operation

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;

CustomerDocument saved = template
    .insertById(CustomerDocument.class)
    .withDurability(DurabilityLevel.MAJORITY)
    .one(customer);
~~~

Tùy chọn trên cần bucket/topology thực sự đáp ứng majority; không biến lab một node thành HA. Có thể đặt default bằng `@Document(durabilityLevel = MAJORITY)` trên entity khi môi trường đã được thiết kế phù hợp.

### 22.2. Không đặt TTL ngắn cho hồ sơ khách hàng bền vững

Một document khách hàng thường không phải cache. TTL thích hợp với session, verification token hay dữ liệu thử nghiệm có retention ngắn, không phải cứ bật TTL mới là production-ready. Khi dùng TTL cho idempotency record, phải bảo đảm không hết hạn trước khả năng retry muộn.

### 22.3. HTTP timeout ambiguous

Nếu POST đã commit nhưng response thất lạc, lần POST sau cùng code sẽ gặp duplicate. Bộ lab ban đầu trả 409; muốn **idempotent create**, bổ sung fingerprint của yêu cầu và đối soát record cùng ID trước khi quyết định trả lại kết quả cũ. Không tạo mã khác hoặc dùng `upsert` để “chữa lỗi” timeout.

## 23. Bốn tình huống thực tế và cách sửa

### 23.1. Case A — Repository tạo lại cùng mã ghi đè khách hàng

**Biểu hiện:** chạy lại `POST` với `CUS-001` nhưng email khác, dữ liệu cũ bị thay. **Gốc lỗi có thể là:** dùng `upsertById` hoặc một entity không có new-state detection phù hợp, không phải insert-only.

**Cách xử lý:** dùng `@Version Long` trên entity mới và kiểm thử `repository.save` chọn insert, hoặc tạo bằng Template `insertById` rõ ràng. Assert duplicate trả conflict, record cũ không đổi.

### 23.2. Case B — `findById` hoạt động, `findByStatus` lỗi

**Biểu hiện:** GET theo code 200, còn list theo status báo lỗi Query Service. **Nguyên nhân thường gặp:** thiếu GSI, index offline, sai collection, thiếu query permissions hoặc query plan chưa dùng index.

**Cách xử lý:** xác nhận `customer_lab.crm.customers`, DDL, `EXPLAIN` và RBAC; không thêm primary index vô tội vạ trên production.

### 23.3. Case C — Hai nhân viên sửa cùng khách hàng

**Biểu hiện:** người B lưu màn hình stale và ghi đè thay đổi của A. **Cách sửa:** trả version dạng chuỗi, yêu cầu expectedVersion ở PUT; service load latest, compare version, update bằng CAS. Khi conflict, trả 409 và yêu cầu refresh/merge.

### 23.4. Case D — API báo timeout, nhưng record đã được tạo

**Biểu hiện:** người dùng gửi lại POST, nhận duplicate. **Lý do:** response có thể mất sau khi Couchbase đã commit. **Cách xử lý:** cùng business key, giữ ID cố định, đọc/đối soát fingerprint; không kết luận timeout nghĩa là chưa ghi hoặc tự sinh code mới.

## 24. Bảng chẩn đoán lỗi trong buổi thực hành

| Triệu chứng | Kiểm tra đầu tiên | Không nên làm |
|---|---|---|
| Kết nối thất bại | Connection string, TLS, credential, network | Tắt TLS để thử production |
| Bucket/scope/collection not found | Tên keyspace và quyền | Tự sửa nhầm keyspace |
| POST trùng mã | ID và cách insert; version của entity | Chuyển sang upsert để che lỗi |
| PUT 409 | Expected version, CAS và concurrent writers | Bỏ CAS để ép ghi |
| GET ID 404 | Key normalization, collection, document lifecycle | Dùng SQL++ query rồi đoán dữ liệu mất |
| List query lỗi | Index state, `EXPLAIN`, Query/Index permissions | Bắt exception rồi trả `[]` |
| List chưa thấy record vừa ghi | Query consistency và GSI lag | Tăng durability vô điều kiện |
| Mutation timeout | Data node health, requested level, retry reasons | Retry bằng customerCode khác |
| Xóa thất bại | Document tồn tại, CAS nếu có, RBAC | Coi mọi lỗi là 404 |
| App chạy nhưng không có `CustomerStore` | `app.customer.backend` | Tạo adapter thứ ba vô tình active |

## 25. Bài tập mở rộng

1. **Unique email:** thiết kế record khóa email → customer ID, giải thích race condition và dùng transaction/CAS khi cần; đừng gọi GSI thường là unique constraint.
2. **Pagination:** thêm `GET /customers?status=ACTIVE&page=0&size=20` với giới hạn max page size, sort và index phù hợp.
3. **Conditional DELETE:** yêu cầu `If-Match` và dùng CAS ở lệnh xóa; test xóa với version cũ trả conflict.
4. **Auditing:** thêm createdBy/updatedBy hoặc Spring Data Couchbase auditing theo dependency version; thử bản ghi của hai users.
5. **Search by email:** chuẩn hóa business email, index thích hợp, query theo tenant và kiểm thử quyền.
6. **Expiry:** thêm collection `customer-verification-codes` có TTL phù hợp; không cho customer chính hết hạn.
7. **Durability:** kiểm thử `MAJORITY` với topology lab có đủ Data nodes, so p99 với default.
8. **Reactive:** thay adapter bằng `ReactiveCouchbaseRepository` và `ReactiveCouchbaseTemplate`; trả `Mono`/`Flux` đến WebFlux, không dùng `block()` trên event loop.
9. **Idempotency:** thêm `Idempotency-Key`/fingerprint và reconciliation cho POST timeout ambiguous.
10. **Multi-tenant:** thêm tenant trong key và bắt buộc predicate tenant ở tất cả SQL++ query.
11. **Error contract:** chuẩn hóa mã lỗi `CUSTOMER_EXISTS`, `CUSTOMER_STALE` và correlation ID mà không lộ PII.
12. **Performance:** so throughput, allocation và p99 theo loại operation Repository vs Template trên cùng lab, cùng tải và cùng consistency.

## 26. Checklist nghiệm thu

- [ ] Có project Spring Boot tương thích JDK, Spring Data Couchbase và Java SDK.
- [ ] Bucket `customer_lab`, scope `crm`, collection `customers` tồn tại trong lab.
- [ ] Cấu hình kết nối/credential không được commit vào source.
- [ ] Tài khoản runtime có RBAC tối thiểu, kết nối TLS phù hợp.
- [ ] `CustomerDocument` có `@Id`, `@Version`, `@Scope` và `@Collection`.
- [ ] ID có prefix `customer::`, mã khách hàng được validate/normalize.
- [ ] Client không thể ghi đè trực tiếp ID/CAS qua body JSON.
- [ ] POST create-only; duplicate không thay record cũ.
- [ ] GET theo ID qua KV; không lệ thuộc secondary index.
- [ ] PUT dùng expectedVersion và CAS; stale update bị từ chối.
- [ ] DELETE theo ID có behavior được kiểm thử; biết giới hạn thiếu CAS.
- [ ] Derived query `findByStatus` có GSI online.
- [ ] Template query có scan consistency phù hợp.
- [ ] Cùng API chạy được với `repository` hoặc `template` backend.
- [ ] Các HTTP status 201/200/204/400/404/409 được phân loại đúng.
- [ ] Không bắt mọi lỗi Couchbase thành conflict/empty list.
- [ ] Có integration tests được cô lập, không chạy nhầm production.
- [ ] Biết phân biệt CAS, durability, TTL, SQL++ freshness, idempotency.
- [ ] Không tự retry mutation ambiguous bằng ID mới.
- [ ] Có roadmap pagination, auth, tenant isolation, metrics và backup/DR.

## 27. Tổng kết

Qua một bài CRUD khách hàng, **Repository** và **CouchbaseTemplate** cùng cung cấp tầng truy cập Couchbase nhưng nhấn mạnh những cách làm khác nhau. Repository tối giản mã CRUD và hỗ trợ derived query; Template cho phép chọn trực tiếp `insertById`, `replaceById`, `findById`, `removeById` và query/durability options theo từng operation.

Nền tảng đúng không chỉ là “có đủ bốn endpoint”: **document ID ổn định, create-only semantics, optimistic locking qua CAS, validation tách khỏi entity, SQL++ index cho truy vấn theo field, exception mapping và integration test ở lab** mới làm cho API có thể kiểm chứng.

Bài thực hành chủ ý sử dụng một project nhỏ để người học nhìn rõ ranh giới: CRUD theo ID chạy qua KV; tìm kiếm theo field phụ thuộc Query/Index Service; `@Version` không thay thế durability; `REQUEST_PLUS` không sửa được retry lỗi; và một mutation timeout không chứng minh nó chắc chắn chưa commit.

## Tài liệu tham khảo chính thức

1. [Spring Data Couchbase — Repository](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): KV khi biết ID, SQL++/index cho queries khác, repository customization.
2. [Spring Data Couchbase — Template & Direct Operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): fluent insert/upsert/find/replace/remove và durability overrides.
3. [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): `@Scope`, `@Collection`, precedence khi override keyspace.
4. [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Id`, `@Version`, CAS và mapping fields.
5. [Spring Boot — Couchbase Auto-Configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html): starters, `spring.couchbase.*` và bucket name.
6. [Spring Data Couchbase — CouchbaseTemplate API](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/core/CouchbaseTemplate.html): các operations có sẵn.
7. [Spring Data Couchbase — QueryCriteria API](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/core/query/QueryCriteria.html): fluent predicates với `QueryCriteria.where`.
8. [Spring Data Couchbase — @ScanConsistency](https://docs.spring.io/spring-data/couchbase/docs/current/api/org/springframework/data/couchbase/repository/ScanConsistency.html): `REQUEST_PLUS` cho SQL++ methods.
9. [Couchbase Java SDK — KV Data Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): create-only insert, CAS, durability và KV APIs.
10. [Couchbase Server — SQL++ Indexes](https://docs.couchbase.com/server/current/learn/services-and-indexes/indexes/indexes.html): index design và truy vấn theo field.

**Phạm vi hoàn thành:** bài hướng dẫn đã cung cấp mã khung và bộ tiêu chí để người học xây ứng dụng thực tế trên môi trường thử nghiệm. Việc build, chạy Java integration tests, kiểm tra phiên bản và Content QA chuyên môn là những hoạt động riêng; không suy từ ví dụ mã rằng project đã được build hoặc deploy.



