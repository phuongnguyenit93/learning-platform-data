# Vị trí của Spring Data Couchbase giữa Spring Data, Spring Boot và Java SDK

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Phân biệt trách nhiệm của **Spring Data**, **Spring Data Couchbase**, **Spring Boot** và **Couchbase Java SDK**.
- Mô tả đường đi của một lệnh từ controller/service, qua repository hoặc template, đến Couchbase Server.
- Hiểu Spring Boot giúp thiết lập dependency, cấu hình và vòng đời bean như thế nào, cũng như những việc nó không tự thực hiện.
- Nhận biết khác biệt giữa **API Spring Data theo entity** và **API SDK theo document/key**, từ đó chọn tầng phù hợp cho mỗi tác vụ.
- Giải thích vì sao truy cập KV, truy vấn SQL++, chỉ mục, mức nhất quán, CAS, TTL, transaction và reactive vẫn phải được thiết kế dù đang dùng Spring Data.

> Phạm vi: Bài này giải thích **ranh giới giữa các lớp công nghệ** và cách chúng phối hợp trong ứng dụng Java/Spring. Các ví dụ tập trung vào Spring Boot và Spring Data Couchbase hiện đại; tên phương thức hoặc thuộc tính cấu hình cụ thể có thể khác giữa các phiên bản và cần được đối chiếu với bộ phiên bản của dự án.

## 2. Nhìn nhanh: bốn tên gọi, bốn vai trò

Giả sử ứng dụng có lớp `CustomerService` cần lấy hồ sơ theo ID `customer::c123`. Một phương án là gọi `customerRepository.findById(id)`. Lệnh đơn giản này thực chất đi qua nhiều lớp:

~~~mermaid
flowchart TB
    A["Ứng dụng Spring: Controller / Service"] --> B["Spring Data Couchbase: Repository / Template / Mapping"]
    B --> C["Couchbase Java SDK: Cluster, KV, Query, timeout, retry"]
    C --> D["Couchbase Server: bucket / scope / collection"]
    D --> E["Data Service: đọc ghi theo document ID"]
    D --> F["Query Service: thực thi SQL++"]
    F --> G["Index Service: hỗ trợ tìm kiếm theo thuộc tính"]
    H["Spring Data Commons: interface, metadata, mapping conventions"] -.-> B
    I["Spring Boot: starter, auto-configuration, bean lifecycle"] -.-> A
    I -.-> B
    I -.-> C
~~~

Các nét liền biểu thị đường gọi dữ liệu ở mức khái quát; các nét đứt biểu thị **năng lực được kế thừa/cấu hình**, không phải một network hop. Trong thực tế một số bước chạy trong cùng tiến trình JVM; chỉ việc giao tiếp tới Couchbase Server mới đi qua mạng.

| Thành phần | Vai trò cốt lõi | Thứ lập trình viên thường thấy |
| --- | --- | --- |
| **Spring Data** (hệ sinh thái, gồm Spring Data Commons) | Định nghĩa mô hình repository, abstraction và các quy ước dùng chung giữa nhiều loại database | `CrudRepository`, `Pageable`, `@Id`, `@Version` |
| **Spring Data Couchbase** | Hiện thực hóa những quy ước đó cho Couchbase: mapping JSON, repository, truy vấn, template, API reactive | `CouchbaseRepository`, `CouchbaseTemplate`, `@Document` |
| **Spring Boot** | Tập hợp dependency phù hợp và tự cấu hình bean từ thuộc tính ứng dụng khi điều kiện được thỏa mãn | Starter, `application.yml`, auto-configuration |
| **Couchbase Java SDK** | Client gốc dùng để nói chuyện trực tiếp với Couchbase: KV, SQL++, service API và tùy chọn thấp hơn | `Cluster`, `Bucket`, `Scope`, `Collection`, `get()`, `query()` |

Couchbase Server nằm ngoài cả bốn lớp trên. **Không có server và dữ liệu hợp lệ thì một repository được inject thành công vẫn chưa đủ để ứng dụng hoạt động.**

## 3. Spring Data: quy ước chung cho tầng truy cập dữ liệu

**Spring Data** là một họ dự án tích hợp dữ liệu với Spring. Thay vì mỗi ứng dụng tự thiết kế lại interface CRUD, mapping và cơ chế mở rộng truy vấn, Spring Data cung cấp các nguyên tắc nhất quán.

### 3.1. Spring Data Commons định nghĩa những gì?

Các khái niệm thường gặp gồm:

- **Repository abstraction:** interface biểu diễn tập thao tác với một loại aggregate/entity, ví dụ `CrudRepository<T, ID>`. Mỗi module dành cho một database cung cấp hiện thực phù hợp.
- **Entity metadata:** khái niệm ID, version, trạng thái entity và thông tin ánh xạ; annotation như `@Id`, `@Version` thuộc nhóm dùng chung.
- **Query methods:** quy ước suy diễn truy vấn từ tên phương thức như `findByEmail(...)`. Việc chuyển tên này thành cú pháp database cụ thể do module tương ứng thực hiện.
- **Pagination/sorting và các tiện ích repository:** những mẫu API quen thuộc để giảm mã lặp, dù cách triển khai và giới hạn thực tế phụ thuộc database.

Spring Data **không đồng nghĩa Spring Data JPA**. JPA dành cho mô hình persistence quan hệ. Spring Data Couchbase là một module khác, áp dụng tinh thần repository tương tự nhưng làm việc với **document JSON** và các khả năng của Couchbase.

Ví dụ cùng một lời gọi `findById(id)` có thể tồn tại ở repository của nhiều database. **Ý nghĩa nghiệp vụ** khá giống nhau, nhưng SQL, JSON, network protocol, transaction, consistency và index bên dưới **không giống nhau**.

### 3.2. Điều gì không được Spring Data Commons quyết định?

Spring Data Commons không biết bucket Couchbase của bạn tên gì, document được đặt vào collection nào, có index SQL++ hay không, hoặc server có phục vụ được query không. Nó cũng không quy định rằng `save()` sẽ có cùng ngữ nghĩa giao dịch và khóa giữa Couchbase, JPA, MongoDB hoặc Redis.

**Nguyên tắc:** giữ lại lợi ích API thống nhất, nhưng khi phân tích tính đúng đắn hoặc hiệu năng phải quay về **ngữ nghĩa của Couchbase**.

## 4. Spring Data Couchbase: phần triển khai chuyên cho Couchbase

Module **Spring Data Couchbase** kết nối abstraction nói trên với Couchbase Java SDK và đặc điểm document database.

Những nhóm năng lực tiêu biểu:

1. **Object–document mapping:** ánh xạ Java object sang nội dung document JSON, xử lý trường, loại entity, converter và document ID.
2. **Repository implementation:** tự tạo implementation cho interface kế thừa `CouchbaseRepository` hoặc `ReactiveCouchbaseRepository`.
3. **Derived/declared queries:** biến tiêu chí trên repository thành truy vấn phù hợp (thường SQL++ cho điều kiện ngoài ID).
4. **Template API:** `CouchbaseTemplate` và `ReactiveCouchbaseTemplate` cho các thao tác theo lối lập trình hơn khi repository method không phù hợp.
5. **Tích hợp Spring:** bean, exception translation, mapping context, callback/event và cơ chế quản lý phiên bản tùy khả năng được hỗ trợ.

Điểm quan trọng là Spring Data Couchbase **không tự tạo một database mới**. Nó dùng SDK để gửi yêu cầu tới Couchbase. Tài khoản, quyền truy cập, cấu hình server, index, bucket/scope/collection và chiến lược vận hành vẫn cần được quản lý riêng.

### 4.1. Entity mapping khác với JSON thuần

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Customer {

    @Id
    private String id;

    @Field
    private String fullName;

    @Field
    private String email;

    @Version
    private Long version;

    public Customer() {}

    public Customer(String id, String fullName, String email) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }
}
~~~

Các annotation trong ví dụ đến từ **hai lớp khác nhau**:

| Annotation | Thuộc thành phần | Vai trò |
| --- | --- | --- |
| `@Id` | Spring Data Commons | Chỉ định property Java chứa document key |
| `@Version` | Spring Data Commons | Khai báo version property; Spring Data Couchbase dùng nó để hỗ trợ optimistic locking/CAS |
| `@Document` | Spring Data Couchbase | Đánh dấu class được lưu dưới dạng Couchbase document |
| `@Field` | Spring Data Couchbase | Tùy biến/khai báo ánh xạ property sang JSON |

Với Couchbase, **document key nằm trong metadata**, độc lập với phần JSON body. Spring Data liên kết `@Id` với key đó; không cần giả định body sẽ lưu lại property `id`. Ngược lại, `email` và `fullName` là các field dữ liệu trong body. Framework còn có thể thêm metadata phân biệt kiểu khi ghi entity, nên nội dung JSON do framework tạo không nhất thiết giống JSON ghi thủ công từ SDK.

`@Version` giúp phát hiện tình huống hai bên cùng sửa một document; không có nghĩa cả ứng dụng tự động được bảo vệ khỏi mọi xung đột hay có transaction đa document.

### 4.2. Repository giải quyết công việc nào?

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    List<Customer> findByEmail(String email);
}
~~~

Ở tầng service:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    public Optional<Customer> get(String documentId) {
        return customers.findById(documentId);
    }

    public List<Customer> searchByEmail(String email) {
        return customers.findByEmail(email);
    }
}
~~~

Phần lớn người viết service chỉ thấy các phương thức Java:

- `findById("customer::c123")` thường truy cập trực tiếp **KV theo document key**, không cần secondary index.
- `findByEmail("an@example.com")` không biết key; Spring Data thường tạo **SQL++ query** dựa trên tên method và mapping. Truy vấn cần index phù hợp.
- `save(customer)` kết hợp xử lý lifecycle của entity và thao tác ghi thông qua SDK. Cần hiểu thêm insert/update/CAS nếu có yêu cầu tránh ghi đè.

Một interface repository rất ngắn **không có nghĩa Couchbase không phải làm việc**. Hiệu năng và tính nhất quán vẫn phụ thuộc access pattern, index, topology và tùy chọn query.

### 4.3. Template đứng ở đâu?

`CouchbaseTemplate` vẫn thuộc **Spring Data Couchbase**. Nó cho phép code chủ động lựa chọn thao tác, mapping, query và một số tùy chọn theo fluent API của module.

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.stereotype.Service;

@Service
public class CustomerTemplateReader {

    private final CouchbaseTemplate template;

    public CustomerTemplateReader(CouchbaseTemplate template) {
        this.template = template;
    }

    public Customer get(String documentId) {
        return template.findById(Customer.class).one(documentId);
    }
}
~~~

Đây là cách gọi **qua Spring Data mapping**, không phải gọi thẳng SDK. Repository giúp định nghĩa contract ngắn gọn theo domain; template giúp code service tự lắp thao tác khi cần thêm sự linh hoạt. Các overload/fluent method cụ thể cần khớp phiên bản Spring Data Couchbase sử dụng.

## 5. Spring Boot: người lắp ghép và quản lý cấu hình

**Spring Boot** giúp việc khởi tạo ứng dụng trở nên thuận tiện. Với các dependency và điều kiện phù hợp, auto-configuration có thể tạo bean cho kết nối Couchbase, mapping, template và repository để lớp ứng dụng dùng dependency injection.

### 5.1. Starter mang gì vào ứng dụng?

Trong một dự án Spring Boot có quản lý dependency tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
}
~~~

Starter giúp kéo vào các dependency liên quan, trong đó có Spring Data Couchbase và Couchbase Java SDK. **Starter không phải driver riêng**, cũng không phải module chứa toàn bộ logic repository. Nó là một cách gom dependency và kích hoạt đường auto-configuration tương ứng.

Với ứng dụng chủ yếu truy cập reactive, Spring Boot có starter reactive tương ứng trong các dòng phiên bản hỗ trợ. Việc chọn starter và API cần nhất quán với phiên bản Spring Boot/Spring Data và framework web của ứng dụng.

**Quản lý phiên bản:** Khi dùng Spring Boot dependency management/BOM, hãy ưu tiên bộ Spring Data, Couchbase SDK và thư viện Reactor mà Boot đã kiểm thử tương thích. Ghi đè ngẫu nhiên phiên bản riêng lẻ có thể gây lỗi class/method ở runtime, kể cả khi mã nghiệp vụ biên dịch thành công.

### 5.2. Cấu hình kết nối trong `application.yml`

Ví dụ phổ biến với Spring Boot 3.x:

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: ${COUCHBASE_USERNAME}
    password: ${COUCHBASE_PASSWORD}
  data:
    couchbase:
      bucket-name: shop
~~~

Giải thích:

- `spring.couchbase.*`: thông tin kết nối cluster và xác thực cho client.
- `spring.data.couchbase.bucket-name`: bucket mặc định được Spring Data Couchbase sử dụng theo cấu hình.
- Biến môi trường tránh nhúng tài khoản/mật khẩu thật trong repository Git.
- Cần tạo bucket `shop`, cấp quyền đúng cho tài khoản và bảo đảm dịch vụ Couchbase có thể được truy cập từ ứng dụng.

Ví dụ này giả định dùng scope/collection mặc định. Nếu cần phân tách `crm.customers` và `sales.orders`, hãy thiết kế ánh xạ theo scope/collection và quyền truy cập tương ứng; **không tự suy luận** rằng mọi entity có class riêng sẽ nằm ở collection riêng.

### 5.3. Spring Boot auto-configuration vận hành theo nguyên tắc nào?

Ở mức khái niệm, quá trình có dạng:

1. Spring Boot thấy các thư viện Couchbase/Spring Data Couchbase trên classpath và các điều kiện cấu hình liên quan.
2. Boot bind property kết nối từ `application.yml`/environment.
3. Framework chuẩn bị các bean để SDK kết nối và Spring Data thực hiện mapping, template, repository.
4. Spring tạo implementation cho `CustomerRepository` và inject vào `CustomerService`.
5. Khi service thực thi lời gọi, Spring Data sử dụng client SDK tương ứng để làm việc với Couchbase Server.

Thứ tự bean cụ thể phụ thuộc cấu hình và phiên bản; sơ đồ trên diễn tả **quan hệ trách nhiệm**, không phải lịch thực thi chính xác.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot startup
    participant Config as Auto-configuration
    participant SD as Spring Data Couchbase
    participant SDK as Couchbase Java SDK
    participant DB as Couchbase Server
    App->>Config: Đọc dependency và application.yml
    Config->>SDK: Khởi tạo/quản lý client cần thiết
    Config->>SD: Khởi tạo mapping, template, repository
    App->>SD: CustomerRepository.findById(key)
    SD->>SDK: Thao tác KV theo ID
    SDK->>DB: Request qua mạng
    DB-->>SDK: JSON + metadata
    SDK-->>SD: Kết quả SDK
    SD-->>App: Customer entity
~~~

Spring Boot **không** tự tạo dữ liệu, tất cả secondary index cần thiết, mô hình document tối ưu hoặc chiến lược xử lý xung đột. Khởi tạo được `ApplicationContext` không chứng minh truy vấn SQL++ sẽ chạy nhanh hay transaction đáp ứng đủ bất biến nghiệp vụ.

Khi repository không được phát hiện do nằm ngoài package scan mặc định hoặc ứng dụng có nhiều nguồn dữ liệu, có thể cần cấu hình quét repository/bean tường minh. Không nên thêm annotation cấu hình tùy ý trước khi xác định vấn đề thực sự nằm ở auto-configuration hay package scan.

## 6. Couchbase Java SDK: lớp giao tiếp trực tiếp với server

**Couchbase Java SDK** là client gốc do Couchbase cung cấp cho ứng dụng Java. Khi không đi qua Spring Data mapping, code có thể tương tác trực tiếp với cluster, bucket, collection, document hoặc Query Service.

Khái niệm điển hình:

| Java SDK API | Mục đích |
| --- | --- |
| `Cluster` | Điểm truy cập tới các dịch vụ của Couchbase cluster |
| `Bucket` | Không gian bucket và cấu hình truy cập liên quan |
| `Scope` | Nhóm collection trong bucket |
| `Collection` | Thao tác KV trên một tập document |
| `collection.get(id)` | Đọc document theo ID |
| `collection.upsert(id, content)` | Ghi nội dung vào ID; cần cân nhắc ngữ nghĩa ghi đè |
| `cluster.query(sql, options)` | Thực thi SQL++ và truyền tùy chọn query |

Ví dụ **đọc JSON trực tiếp qua SDK**, tận dụng `Cluster` do Spring Boot quản lý:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import org.springframework.stereotype.Service;

@Service
public class RawCustomerReader {

    private final Cluster cluster;

    public RawCustomerReader(Cluster cluster) {
        this.cluster = cluster;
    }

    public JsonObject getRaw(String documentId) {
        return cluster
                .bucket("shop")
                .defaultCollection()
                .get(documentId)
                .contentAsObject();
    }
}
~~~

Ví dụ giả định document nằm trong collection mặc định của bucket `shop`; nếu nằm trong scope/collection khác, hãy dùng `bucket.scope("crm").collection("customers")`. Việc inject `Cluster` giúp dùng chung cấu hình kết nối/lifecycle do Boot quản lý trong một ứng dụng cấu hình tiêu chuẩn. Không tạo `Cluster.connect(...)` mới cho từng request vì kết nối và tài nguyên SDK cần được tái sử dụng.

**Sự khác nhau của kết quả:** API SDK trả `JsonObject` chứa nội dung JSON. Nó không tự áp dụng những quy ước `@Document`, `@Id`, `@Field` và converter của Spring Data. Nếu muốn đưa JSON vào `Customer`, code dùng SDK trực tiếp phải tự xử lý mapping hoặc gọi lại lớp mapping thích hợp.

### 6.1. Khi nào cần đi xuống SDK?

Cân nhắc SDK khi:

- Cần thao tác KV chuyên biệt hoặc option chi tiết mà abstraction Spring Data đang sử dụng chưa phơi bày thuận tiện.
- Cần thao tác trên JSON/metadata thô, công cụ quản trị hay chức năng dịch vụ chuyên biệt.
- Cần tự xây một gateway dùng cho tài liệu không thuộc model entity hiện tại.
- Cần kiểm soát rõ các cơ chế SDK như mutation options, request consistency hoặc service API đặc biệt, sau khi đã đánh giá API template/repository.

Khi dùng SDK trực tiếp, phải tự chịu thêm trách nhiệm về mapping, exception, timeout, tài nguyên, tính lặp an toàn (idempotency) và quan sát hoạt động. Có thể kết hợp repository với SDK trong một ứng dụng, nhưng cần bảo đảm **cùng collection, cùng quy tắc ID, cùng chính sách version và cùng kỳ vọng consistency** để tránh sai lệch dữ liệu.

## 7. So sánh ba cách đọc cùng một document

Giả sử document có key `customer::c123` trong bucket `shop`, collection mặc định.

~~~mermaid
flowchart LR
    A["Service"] --> B["Repository: findById"]
    A --> C["Template: findById(...).one(...)"]
    A --> D["SDK: collection.get"]
    B --> E["Spring Data mapping"]
    C --> E
    E --> F["SDK KV client"]
    D --> F
    F --> G["Couchbase Data Service"]
~~~

| Tiêu chí | Repository | CouchbaseTemplate | Java SDK trực tiếp |
| --- | --- | --- | --- |
| Dữ liệu trả về điển hình | Java entity | Java entity qua mapping | Kết quả SDK, JSON và metadata |
| Mức độ code nghiệp vụ | Ngắn nhất cho CRUD/derived query | Chủ động hơn với thao tác/query | Chủ động thấp nhất về abstraction, nhiều chi tiết nhất |
| Ánh xạ `@Document`, `@Id` | Có | Có | Không tự động |
| Khả năng tùy chỉnh tùy chọn chuyên biệt | Theo method/annotation/API được hỗ trợ | Theo API template được hỗ trợ | Theo khả năng trực tiếp của SDK |
| Phù hợp nhất | CRUD và truy vấn domain rõ ràng | Truy vấn linh hoạt hoặc xử lý cần điều khiển hơn | Chức năng thấp cấp, truy cập JSON thô hay tối ưu đặc thù |

**Cả ba có thể cùng dùng đường KV để đọc theo ID**; đừng kết luận rằng “dùng SDK luôn nhanh hơn repository” chỉ vì ít abstraction hơn. Thường các yếu tố như số lần gọi mạng, kích thước document, index, consistency, retry và bố trí cluster mới quyết định độ trễ đáng kể. Hãy đo bằng benchmark phù hợp trước khi thay API.

## 8. Tại sao SQL++ và chỉ mục vẫn là việc của người thiết kế?

Lệnh `findById` đã biết document ID nên có thể thực hiện KV trực tiếp. Nhưng `findByEmail` phải tìm theo giá trị của field JSON; Spring Data Couchbase thường biến nó thành SQL++ query.

Ví dụ SQL++ minh họa:

~~~sql
SELECT META(c).id AS documentId, c.email, c.fullName
FROM `shop`.`_default`.`_default` AS c
WHERE c.email = "an@example.com";
~~~

Một index ví dụ:

~~~sql
CREATE INDEX ix_customer_email
ON `shop`.`_default`.`_default`(email);
~~~

Đây là SQL++ dùng để **minh họa keyspace và index**, không phải cam kết về câu query chính xác mà Spring Data sinh ra. Query thật có thể gồm điều kiện metadata phân biệt loại entity, các trường projection và tiêu chí khác; cần xem statement/plan thực tế để thiết kế chỉ mục.

Cần phân biệt hai câu hỏi:

- **“Ai xây câu lệnh?”** Spring Data Couchbase có thể xây SQL++ từ repository method/template.
- **“Ai thực thi nhanh và nhất quán?”** Query/Index Service của Couchbase, phụ thuộc index, điều kiện query, dữ liệu, scan consistency và tài nguyên cluster.

Spring Boot không tự biến một truy vấn lọc 10 triệu document thành truy vấn tối ưu chỉ bằng cách thêm starter. Spring Data không làm secondary index trở nên không cần thiết.

## 9. Reactive nằm ở lớp nào?

Reactive xuất hiện ở **cả Spring Data Couchbase và SDK** nhưng có ý nghĩa khác nhau.

| Lớp | API liên quan | Vai trò |
| --- | --- | --- |
| Spring Data Couchbase | `ReactiveCouchbaseRepository`, `ReactiveCouchbaseTemplate` | API entity/repository dùng `Mono` và `Flux` |
| Couchbase Java SDK | Reactive client API | Thực hiện thao tác I/O không chặn ở lớp SDK |
| Spring Boot | Cấu hình dependency, bean và tích hợp khi dùng stack reactive | Giảm boilerplate khởi tạo, không tự chuyển code blocking thành non-blocking |

Ví dụ repository reactive:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {
}
~~~

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCustomerService {

    private final ReactiveCustomerRepository customers;

    public ReactiveCustomerService(ReactiveCustomerRepository customers) {
        this.customers = customers;
    }

    public Mono<Customer> get(String documentId) {
        return customers.findById(documentId);
    }
}
~~~

Một `Mono<Customer>` biểu diễn kết quả có thể đến sau, tối đa một entity. Điều quan trọng là duy trì pipeline I/O không chặn ở các lớp có liên quan. Gọi `block()` trong event loop làm mất lợi ích của reactive và có thể gây tắc nghẽn.

**Reactive không phải lời hứa tăng tốc từng truy vấn.** Nếu SQL++ thiếu index, cluster đã quá tải hoặc truy vấn đòi hỏi scan consistency tốn kém, reactive repository không sửa được vấn đề đó. Chọn reactive khi ứng dụng và toàn bộ đường I/O có nhu cầu phù hợp, có khả năng vận hành, quan sát và xử lý lỗi đúng cách.

## 10. Những năng lực quan trọng thuộc lớp nào?

Đây là điểm thường gây hiểu lầm khi chuyển từ repository abstraction sang xử lý vận hành.

| Vấn đề | Trọng tâm trách nhiệm | Phần Spring Data/Boot giúp được |
| --- | --- | --- |
| **Document ID, bucket, scope, collection** | Thiết kế model và tổ chức dữ liệu trong Couchbase | Mapping và cấu hình mặc định |
| **SQL++/secondary index** | Query và Index Service, thiết kế access pattern | Repository method/query API gọi được SQL++ |
| **CAS/optimistic locking** | CAS được server/SDK hỗ trợ; ứng dụng xử lý xung đột | `@Version` và exception/logic mapping phù hợp |
| **TTL/expiry** | Expiry metadata, chính sách lưu trữ document | Annotation/API cấu hình tương ứng với phiên bản |
| **Scan consistency** | Tùy chọn truy vấn và cập nhật index | Một số API cung cấp tùy chọn; cần cấu hình rõ theo use case |
| **Transaction đa document** | Cơ chế transaction của Couchbase và bất biến nghiệp vụ | API tích hợp nếu phiên bản hỗ trợ, nhưng phải dùng đúng |
| **TLS, quyền truy cập, timeout** | Hạ tầng, client SDK, chính sách an toàn và độ tin cậy | Boot cấu hình bean/properties, Spring Data truyền thao tác |
| **Logging/metrics/tracing** | Toàn đường ứng dụng–SDK–server | Boot/Actuator và tích hợp monitoring hỗ trợ quan sát |

### Ví dụ 1: Vừa ghi xong nhưng tìm qua email chưa thấy

Luồng sau có thể xảy ra:

~~~text
service.save(customer)
    -> Spring Data Couchbase
    -> SDK KV ghi thành công vào Couchbase
service.findByEmail(customer.email)
    -> SQL++ truy vấn qua index
    -> index chưa bắt kịp mutation mới
    -> kết quả tìm kiếm tạm thời chưa thấy document
~~~

Đây là câu hỏi về **consistency giữa KV và query qua index**. Giải pháp có thể là thay đổi cách đọc (theo ID khi đã biết key) hoặc cấu hình scan consistency phù hợp, chẳng hạn các mức chờ index cập nhật theo nhu cầu. Chọn giải pháp phải cân bằng đúng đắn và độ trễ, không chỉ thay đổi từ repository sang template.

### Ví dụ 2: Hai request cùng ghi một document

~~~text
A đọc document với CAS=v1
B đọc document với CAS=v1
A sửa và ghi thành công -> CAS=v2
B cố ghi với CAS=v1 -> phát hiện xung đột
~~~

CAS là cơ chế của Couchbase. Spring Data Couchbase có thể dùng `@Version` để lộ optimistic locking cho entity; ứng dụng vẫn cần quyết định trả lỗi, yêu cầu thao tác lại hay thử lại có giới hạn sau khi đọc dữ liệu mới. Ghi đè vô điều kiện ở SDK có thể phá hỏng chính sách này nếu các luồng khác đang trông cậy vào version.

### Ví dụ 3: Cập nhật hai document có bảo đảm nguyên tử

Một lệnh repository `save(order)` và một lệnh `save(stock)` trong hai lời gọi riêng biệt **không mặc nhiên** tạo transaction nguyên tử. Nếu nghiệp vụ yêu cầu cả hai cùng thành công hoặc cùng không được áp dụng, cần thiết kế theo cơ chế transaction nhiều document được Couchbase và bộ API/phiên bản đang dùng hỗ trợ, đồng thời xử lý retry, lỗi và idempotency. Không nên suy diễn ngữ nghĩa transaction từ kinh nghiệm với Spring Data JPA.

## 11. Chẩn đoán lỗi theo đúng tầng

Khi một chương trình không hoạt động, xác định **lỗi xuất hiện ở ranh giới nào** giúp rút ngắn thời gian điều tra.

| Triệu chứng | Tầng cần kiểm tra trước | Câu hỏi cụ thể |
| --- | --- | --- |
| Không inject được `CustomerRepository` khi startup | Spring Boot / Spring Data | Starter có đúng không? Repository có nằm trong package scan? Bean/config có xung đột? |
| Không kết nối được cluster | Boot config / Java SDK / Network | Connection string, TLS, quyền, DNS/route, service, timeout có đúng? |
| `findById` báo document không tồn tại | Mapping / KV / model | Key có đúng không? Đúng bucket/scope/collection chưa? |
| `findByEmail` lỗi hoặc quá chậm | SQL++ / Index Service | Index có ở đúng collection? `EXPLAIN` chọn index nào? |
| Đọc ID được, tìm qua field chưa thấy ngay | Query consistency | Mức scan consistency có đáp ứng read-your-writes? |
| Đôi khi mất thay đổi khi cập nhật | Entity version / CAS / nghiệp vụ | Có optimistic locking hay ghi đè vô điều kiện? |
| SDK đọc được JSON nhưng entity Spring Data lỗi | Mapping layer | Kiểu field, metadata loại entity, converter và schema có tương thích không? |
| Reactive bị nghẽn | Reactor pipeline / SDK / Server | Có đoạn `block()` hoặc xử lý blocking? Query/index có đang chậm? |

**Cách điều tra có hệ thống:** lấy thông tin từ request/log, xác định bước thất bại, kiểm tra cấu hình thực tế và chỉ số SDK/Couchbase, sau đó quan sát statement/plan khi lỗi liên quan SQL++. Tránh quy tất cả timeout cho repository vì timeout có thể phát sinh ở nhiều lớp.

## 12. Quy tắc lựa chọn API trong một dự án

Không cần chọn độc quyền một API cho cả hệ thống. Có thể chọn theo nhu cầu cụ thể, đặt sau interface service/gateway để phần còn lại của ứng dụng ít phụ thuộc công nghệ hơn.

~~~mermaid
flowchart TD
    A{"Cần thao tác dữ liệu kiểu gì?"} -->|CRUD entity, query domain phổ biến| B["CouchbaseRepository"]
    A -->|Query/mapping linh hoạt hơn| C["CouchbaseTemplate"]
    A -->|I/O non-blocking xuyên suốt| D["Reactive repository/template"]
    A -->|API SDK chuyên biệt/JSON thô| E["Couchbase Java SDK"]
    B --> F["Couchbase Java SDK"]
    C --> F
    D --> F
    E --> F
    F --> G["Couchbase Server"]
~~~

Một số quy tắc thực hành:

1. **Bắt đầu từ access pattern:** có biết document ID hay phải tìm qua thuộc tính? Từ đó chọn đường KV hoặc SQL++, xác định index trước khi lựa chọn kiểu API.
2. **Ưu tiên repository** khi service chủ yếu CRUD entity và các truy vấn rõ ràng; việc có entity cụ thể làm code dễ đọc và dễ bảo trì.
3. **Dùng template** khi cần biểu đạt thao tác phức tạp hơn mà vẫn muốn bảo toàn mapping của Spring Data.
4. **Dùng SDK trực tiếp** cho tính năng đặc biệt hoặc JSON thô, nhưng đặt trong lớp gateway rõ ràng, quản lý mapping/timeout/exception nhất quán.
5. **Chọn reactive theo toàn luồng**: từ HTTP/API qua service đến I/O. Không chuyển riêng một repository sang reactive rồi gọi `block()` hàng loạt.
6. **Để Boot quản lý dependency và client lifecycle** khi có thể; tùy chỉnh bean khi có yêu cầu thực tế, kiểm thử cẩn thận nếu ghi đè auto-configuration.
7. **Không bỏ qua server semantics:** thiết kế bucket/scope/collection, index, TTL, CAS, consistency và transaction dựa trên bất biến dữ liệu.

### Một tình huống thiết kế tổng hợp

Một ứng dụng quản lý khách hàng cần:

- **Đọc chi tiết khách hàng:** dùng `CustomerRepository.findById`, đường KV phù hợp vì đã biết key.
- **Tìm theo email:** dùng derived query hoặc template; bảo đảm SQL++ có index phù hợp.
- **Đọc raw document để điều tra một bản ghi lỗi mapping:** dùng Java SDK `Collection.get` để xem JSON thực tế trong công cụ nội bộ có phân quyền.
- **Cập nhật thông tin đồng thời từ nhiều màn hình:** gắn `@Version`, xử lý xung đột ở tầng service.
- **Hỗ trợ nhiều kết nối I/O trong web reactive:** dùng repository/template reactive và tránh blocking trên event loop.
- **Vận hành:** cấu hình và quản lý client qua Boot; theo dõi cả error ở application, SDK và cluster.

Các tình huống này có thể cùng tồn tại trong một hệ thống. Ranh giới nên dựa trên yêu cầu dữ liệu và khả năng quan sát, không chỉ dựa vào cú pháp API nào ngắn hơn.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Spring Boot có phải nơi hiện thực `findByEmail` thành câu SQL++ không?

**Gợi ý:** Boot giúp thiết lập các bean và dependency; Spring Data Couchbase mới là module diễn giải repository method thành thao tác Couchbase.

**Câu 2.** Khi chuyển từ `CouchbaseRepository.findById` sang `Collection.get`, điều gì thay đổi?

**Gợi ý:** Cả hai thường có thể dùng KV để đọc cùng ID. SDK cấp thấp cho nội dung JSON/metadata; repository còn có mapping, converter, lifecycle và các abstraction Spring Data.

**Câu 3.** Vì sao vừa thêm starter Spring Boot vẫn phải tạo index cho truy vấn tìm khách hàng theo email?

**Gợi ý:** Starter không thực thi hoặc tối ưu query trên cluster; SQL++ cần khả năng truy cập bằng index thích hợp với điều kiện lọc.

**Câu 4.** Một request dùng repository có `@Version`, request khác dùng SDK với thao tác ghi đè vô điều kiện. Có rủi ro gì?

**Gợi ý:** Hai đường ghi đang áp dụng quy tắc cập nhật khác nhau. Ghi đè có thể vi phạm bất biến nghiệp vụ nếu không kiểm tra CAS hoặc không thống nhất chính sách cập nhật.

**Câu 5.** Khi query SQL++ chậm, chuyển từ blocking sang reactive có xử lý nguyên nhân không?

**Gợi ý:** Reactive giảm chi phí chờ trên thread của ứng dụng; cần vẫn kiểm tra query plan, index, consistency và tài nguyên server.

## 14. Tổng kết

Bốn thành phần nằm ở các tầng khác nhau nhưng bổ trợ cho nhau: **Spring Data** đưa ra quy ước repository; **Spring Data Couchbase** hiện thực repository, document mapping và template cho Couchbase; **Spring Boot** ghép dependency, cấu hình và vòng đời bean; **Couchbase Java SDK** thực hiện lời gọi trực tiếp tới **Couchbase Server**.

Hiểu đúng ranh giới giúp đặt câu hỏi đúng khi thiết kế và xử lý lỗi. Với một thao tác đọc theo key, hãy nhìn vào mapping và KV; với truy vấn thuộc tính, hãy nhìn vào SQL++ và index; với cập nhật đồng thời, hãy nhìn vào CAS/transaction; với throughput, hãy nhìn cả pipeline ứng dụng và tài nguyên cluster. Framework giúp viết code rõ ràng và nhất quán hơn, còn hiệu năng và tính đúng đắn vẫn cần được kiểm chứng trên dữ liệu và workload thực tế.
