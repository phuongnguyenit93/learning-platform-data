# Repository, Template và Java SDK: vai trò và quan hệ

## 1. Mục tiêu học tập

Trong hệ sinh thái **Spring Data Couchbase**, cùng một document JSON có thể được đọc hoặc ghi qua `CouchbaseRepository`, `CouchbaseTemplate` hoặc **Couchbase Java SDK**. Các API này bổ sung cho nhau vì chúng phục vụ những mức trừu tượng và quyền kiểm soát khác nhau, nhưng cùng làm việc với Couchbase cluster.

Bài học thuộc chương **Tổng quan**, giúp bạn:

- Giải thích luồng truy cập từ Spring Service qua Repository/Template/SDK tới Couchbase.
- Chọn API cho CRUD theo document ID, truy vấn SQL++, thao tác KV nâng cao và xử lý reactive.
- Viết entity, Repository, service, Template và SDK gateway cho một nghiệp vụ cụ thể.
- Hiểu ranh giới của document mapping, quản lý bucket/scope/collection, index, TTL, CAS, consistency và transaction.
- Biết cách phối hợp các API trong một hệ thống mà không làm hỏng quy tắc dữ liệu hoặc tăng độ phức tạp không cần thiết.

## 2. Tình huống: một service khách hàng có nhiều yêu cầu truy cập

Giả sử ứng dụng thương mại điện tử có một document hồ sơ người dùng với key metadata `customer::c-1001` và body:

~~~json
{
  "fullName": "Nguyen An",
  "email": "an@example.com",
  "status": "ACTIVE",
  "tier": "GOLD",
  "settings": {
    "language": "vi",
    "notifications": true
  }
}
~~~

Lớp dịch vụ cần thực hiện các yêu cầu:

1. Đọc hồ sơ theo mã khách hàng `c-1001`.
2. Tìm khách hàng có `status = ACTIVE` và `tier = GOLD`.
3. Cập nhật `tier` mà không làm mất thay đổi do request khác vừa ghi.
4. Cập nhật một phần JSON bằng khả năng KV chuyên biệt.
5. Thiết lập expiry cho session tạm, theo dõi thời gian chờ và lỗi từ database.
6. Hỗ trợ cả ứng dụng Spring MVC truyền thống và một API WebFlux reactive.

Nếu mỗi thao tác đều viết bằng một lớp API duy nhất, có thể xảy ra hai vấn đề: hoặc Repository phải mô tả những hoạt động quá đặc thù, hoặc service viết nhiều code mapping và xử lý thấp hơn cần thiết. Để thiết kế hợp lý, trước tiên cần hiểu các tầng.

## 3. Mối quan hệ giữa Repository, Template và Java SDK

~~~mermaid
flowchart TD
    C["Controller / Application Service"] --> R["CouchbaseRepository"]
    C --> T["CouchbaseTemplate"]
    C --> D["Java SDK trực tiếp"]
    R --> I["Spring Data Repository Infrastructure"]
    I --> M["Spring Data mapping / query operations"]
    T --> M
    M --> SDK["Couchbase Java SDK"]
    D --> SDK
    SDK --> CB[("Couchbase Cluster")]
    CB --> KV["Data Service / KV"]
    CB --> Q["Query Service / SQL++"]
    Q --> IX["Index Service"]
    CB --> S["Search Service"]
~~~

Đây là **sơ đồ quan hệ logic**, không phải lời khẳng định mọi lệnh có đúng cùng call stack. Spring Data cung cấp Repository và Template, sử dụng bộ ánh xạ object–document, converter và hạ tầng thực thi dữ liệu. Bên dưới, Couchbase Java SDK quản lý giao tiếp với cluster và thực thi các thao tác được hỗ trợ.

Trong đó:

- **Repository:** người lập trình khai báo interface, Spring Data tạo implementation tại runtime. Phù hợp với các thao tác entity thường gặp.
- **Template:** người lập trình chủ động gọi các operation/query ở mức Spring Data. Vẫn giữ mapping Java ↔ JSON và tích hợp framework.
- **SDK:** người lập trình giao tiếp gần hơn với Couchbase, chủ động chọn collection, thao tác KV, truy vấn SQL++, Search, tùy chọn CAS/expiry/durability và xử lý kết quả thô.
- **Server:** thực sự lưu document, vận hành Data/Query/Index/Search Service, xử lý quyền, tính nhất quán và độ bền.

Một cách hình dung: **Repository mô tả “muốn lấy dữ liệu nào”**, **Template giúp tổ chức “thao tác bằng Spring Data như thế nào”**, còn **SDK cho phép chỉ định “giao tiếp với Couchbase bằng operation và option nào”**.

### 3.1. Luồng đọc theo ID

~~~mermaid
sequenceDiagram
    participant S as CustomerService
    participant R as CustomerRepository
    participant M as Spring Data Mapping
    participant SDK as Couchbase Java SDK
    participant DB as Couchbase Data Service
    S->>R: findById("customer::c-1001")
    R->>M: Thực hiện thao tác entity
    M->>SDK: KV get(collection, key)
    SDK->>DB: Đọc document theo key
    DB-->>SDK: JSON body và metadata
    SDK-->>M: Kết quả KV
    M-->>R: Customer entity
    R-->>S: Optional<Customer>
~~~

Khi có sẵn document ID, `findById` thường đi qua **KV**. Nếu gọi `findByEmail`, Spring Data thường cần sinh SQL++ để lọc theo trường và cần index phù hợp. Việc đều nằm trong Repository **không** khiến hai đường truy cập có cùng cách thực thi.

## 4. So sánh nhanh và quy tắc lựa chọn

| Đặc điểm | Repository | CouchbaseTemplate | Couchbase Java SDK |
| --- | --- | --- | --- |
| Hình thức | Interface khai báo | API thao tác trong code | API trực tiếp của client |
| Mức trừu tượng | Cao | Trung bình, vẫn thuộc Spring Data | Thấp hơn, sát Couchbase |
| Mapping entity Java | Spring Data | Spring Data | Serializer/codec của SDK, không mặc nhiên áp dụng toàn bộ converter Spring Data |
| CRUD theo ID | Rất thuận tiện | Hỗ trợ thao tác entity | `get`, `insert`, `upsert`, `replace`, `remove` |
| Query theo field JSON | Derived query, `@Query` | Query/operation tùy chỉnh | `Cluster.query` / các API query tương ứng |
| Tùy chọn nâng cao | Tùy repository API | Tùy Template API | Phạm vi SDK hỗ trợ trực tiếp |
| Reactive | `ReactiveCouchbaseRepository` | `ReactiveCouchbaseTemplate` | Async/reactive APIs của SDK |
| Công sức viết code | Ít với CRUD đơn giản | Vừa phải | Thường nhiều hơn |
| Loại lỗi | Có lớp Spring Data translation/semantics | Có lớp Spring Data semantics | Exception và kết quả SDK trực tiếp |

Không có kết luận chung “SDK luôn nhanh nhất” hay “Template luôn nhanh hơn Repository”. Với cùng một document ID, Repository và SDK có thể cùng sử dụng KV; với cùng truy vấn theo trạng thái, cả ba có thể dẫn đến SQL++ và một query plan tương tự. Nút thắt thường ở **index, kích thước document, kết nối, round trip, contention và tải cluster**.

| Yêu cầu nghiệp vụ | Lựa chọn thường hợp lý |
| --- | --- |
| Lấy khách hàng theo ID, lưu entity | Repository |
| Tìm theo email/status/tier bằng vài điều kiện | Repository derived query hoặc `@Query` |
| Xây truy vấn linh hoạt theo nhiều bộ lọc | Template hoặc custom repository |
| Thao tác một phần JSON, dùng KV options đặc thù | SDK nếu Template/Repository chưa đáp ứng |
| Toàn văn, Search index, Search hit | SDK Search API hoặc lớp tích hợp Search phù hợp |
| Pipeline WebFlux nhiều I/O đồng thời | Reactive Repository/Template hoặc SDK reactive |

## 5. Document mapping là phần chung quan trọng

Giả sử ứng dụng dùng bucket `shop`, scope `crm` và collection `customers`. Document có key `customer::c-1001`, nhưng key là **metadata**; không bắt buộc lưu một bản sao `id` trong JSON body.

Entity mẫu:

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

    @Field
    private String status;

    @Field
    private String tier;

    @Version
    private Long version;

    public Customer() {}

    public Customer(String id, String fullName, String email,
                    String status, String tier) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
        this.status = status;
        this.tier = tier;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getTier() { return tier; }
    public void setTier(String tier) { this.tier = tier; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }
}
~~~

Ý nghĩa:

- `@Document`: entity được Spring Data Couchbase ánh xạ thành document.
- `@Id`: biểu diễn document key, ví dụ `customer::c-1001`.
- `@Field`: biểu diễn thuộc tính JSON trong body document.
- `@Version`: hỗ trợ optimistic locking theo CAS khi dùng các thao tác Spring Data phù hợp.

**CAS không phải một trường số nguyên `version` phải được application tự cộng lên trong JSON.** CAS là giá trị metadata do Couchbase Server quản lý. Spring Data có thể dùng thông tin đó qua `@Version`.

Spring Data có thể bổ sung metadata phân biệt Java type, thường là trường như `_class`, tùy cách cấu hình converter. Đây là chi tiết quan trọng khi SDK trực tiếp đọc/ghi document mà trước đó Repository quản lý.

### 5.1. Cùng document nghĩa là cùng bucket, scope, collection và ID

Đừng chỉ so sánh chuỗi `customer::c-1001`. Hai collection khác nhau có thể chứa cùng key nhưng là **hai document khác nhau**. Nếu Repository được cấu hình ở `shop._default._default` còn SDK gọi `shop.crm.customers`, kết quả khác nhau dù ID giống nhau.

Khi dùng collection riêng, cần cấu hình mapping theo annotation/configuration được phiên bản Spring Data sử dụng. Với SDK, chọn collection trực tiếp qua bucket → scope → collection. Trong ví dụ minh họa bên dưới, hãy hiểu các thành phần đã được cấu hình để cùng trỏ tới `shop.crm.customers`.

## 6. Repository: giải quyết CRUD và truy vấn phổ biến

### 6.1. Khai báo dependency và cấu hình kết nối

Với Spring Boot tương thích, có thể sử dụng starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
}
~~~

Cấu hình đơn giản cho bucket (cú pháp cụ thể phụ thuộc phiên bản Spring Boot):

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: PLACEHOLDER_USERNAME
    password: PLACEHOLDER_PASSWORD
  data:
    couchbase:
      bucket-name: shop
~~~

Các placeholder trên là tên biến cấu hình giả định; trong triển khai thật, thay bằng cơ chế environment/secret của ứng dụng. Cluster, bucket và tài khoản phải được thiết lập từ trước. Bucket-name không tự xác định scope/collection `crm.customers`; cần cấu hình mapping tương ứng. Không đặt thông tin đăng nhập thực trong mã nguồn.

### 6.2. Repository interface

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    List<Customer> findByStatusAndTier(
            String status, String tier);
}
~~~

Các phương thức `findById`, `save`, `deleteById` và `existsById` đã được kế thừa; người lập trình không cần tự viết implementation cho CRUD phổ biến.

Trong service:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Optional<Customer> get(String customerId) {
        return repository.findById("customer::" + customerId);
    }

    public List<Customer> activeGoldCustomers() {
        return repository.findByStatusAndTier("ACTIVE", "GOLD");
    }

    public Customer save(Customer customer) {
        return repository.save(customer);
    }
}
~~~

Luồng `get(...)` biết key trước nên thường truy cập **KV**; `findByStatusAndTier(...)` phải lọc theo thuộc tính JSON và thường dùng **SQL++**.

### 6.3. Repository không tự tạo chỉ mục phù hợp

Nếu entity nằm ở `shop.crm.customers`, truy vấn SQL++ tương đương về ý tưởng:

~~~sql
SELECT META(c).id AS documentId,
       c.fullName, c.email, c.status, c.tier
FROM `shop`.`crm`.`customers` AS c
WHERE c.status = "ACTIVE"
  AND c.tier = "GOLD";
~~~

Index minh họa:

~~~sql
CREATE INDEX ix_customer_status_tier
ON `shop`.`crm`.`customers`(status, tier);
~~~

Truy vấn này **không nhất thiết giống câu SQL++ Spring Data sinh ra**. Derived query có thể thêm điều kiện metadata/type để ánh xạ đúng entity. Index thực tế phải xem thêm độ chọn lọc, sắp xếp, projection, điều kiện `_class`, độ lớn dữ liệu và kết quả `EXPLAIN`.

Không tạo secondary index chỉ để `findById` chạy được: lookup theo ID đã có đường truy cập KV. Repository giúp code gọn nhưng không thay thế thiết kế index và kiểm tra query plan.

### 6.4. Khi nào Repository chưa đủ thuận tiện?

Repository vẫn có `@Query` và tùy biến query, nhưng interface có quá nhiều phương thức tên dài, lựa chọn bộ lọc động hoặc thao tác đặc thù có thể trở nên khó theo dõi. Thay vì ép mọi trường hợp vào derived query, bạn có thể đặt phần truy cập linh hoạt vào một DAO dùng Template hoặc SDK. Quyết định này phục vụ **khả năng đọc và bảo trì code**, không nhất thiết thay đổi engine của database.

## 7. CouchbaseTemplate: chủ động thao tác mà vẫn giữ Spring Data mapping

`CouchbaseTemplate` là API thao tác dữ liệu có lập trình trong Spring Data Couchbase. Nó cho phép bạn diễn đạt rõ operation tại điểm thực thi, tận dụng mapping/conversion và hạ tầng cấu hình Spring Data thay vì viết lại serializer theo từng use case.

Một ví dụ đọc theo ID bằng fluent operation (áp dụng cho các phiên bản có API tương ứng):

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerLookupDao {
    private final CouchbaseTemplate template;

    public CustomerLookupDao(CouchbaseTemplate template) {
        this.template = template;
    }

    public Customer findOne(String customerId) {
        return template.findById(Customer.class)
                .one("customer::" + customerId);
    }
}
~~~

Ở đây `Customer.class` chỉ kiểu entity để mapper chuyển JSON thành object. Lỗi/giá trị trả về khi không có document phụ thuộc operation và phiên bản Spring Data, nên code service cần xử lý trường hợp không tồn tại theo đúng API thực tế.

### 7.1. Template có thể giải quyết những trường hợp nào?

1. Xây dựng các query có điều kiện thay đổi linh hoạt.
2. Gom một chuỗi thao tác vào lớp persistence khi muốn kiểm soát rõ luồng thực thi.
3. Thao tác với entity mà vẫn cần hệ thống converter, field mapping hoặc metadata Spring Data.
4. Xây một custom repository implementation khi interface repository thông thường không đủ diễn đạt truy vấn.

Template **vẫn cần secondary index** khi truy vấn SQL++ theo trường JSON. Đổi một derived query sang Template không tự sửa kế hoạch truy vấn. Khi dùng query tùy biến cần chọn đúng projection và điều kiện mapping để reconstruct entity đầy đủ.

### 7.2. Phân biệt Template với SQL++ thô

Template không đồng nghĩa phải viết một chuỗi SQL++ ở mọi chỗ. Nó cung cấp operations ở mức Spring Data để chọn và thực thi truy cập, còn Query Service vẫn xử lý điều kiện SQL++ khi thao tác cần truy vấn. Một số trường hợp SDK `cluster.query` phù hợp nếu bạn cần tùy chọn query thấp hơn hoặc muốn xử lý kết quả không đi qua entity mapping; trường hợp đó phải chủ động quản lý kết quả và tham số.

Nếu chỉ có một method `findById` và vài derived query, việc tạo thêm DAO Template có thể chỉ làm tăng số lớp mà chưa mang lại giá trị rõ ràng.

## 8. Java SDK: kiểm soát trực tiếp Couchbase

SDK biết về **Cluster → Bucket → Scope → Collection**, và cung cấp các thao tác KV, SQL++, Search cũng như các options vận hành liên quan.

Ví dụ đọc JSON thô qua SDK:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetResult;
import org.springframework.stereotype.Component;

@Component
public class CustomerSdkGateway {
    private final Collection collection;

    public CustomerSdkGateway(Cluster cluster) {
        this.collection = cluster.bucket("shop")
                .scope("crm")
                .collection("customers");
    }

    public JsonObject load(String customerId) {
        String documentId = "customer::" + customerId;
        GetResult result = collection.get(documentId);
        return result.contentAsObject();
    }
}
~~~

Trong ví dụ này, `Cluster` được giả định là bean đã cấu hình và có vòng đời được Spring quản lý. **Không tạo và đóng cluster cho mỗi request**; thao tác đó làm tăng overhead mạng và rủi ro cạn tài nguyên.

SDK `contentAsObject()` đọc body JSON hiện tại; nó không tự vận hành mọi quy tắc ánh xạ `@Id`, `@Version`, custom converter, type discriminator của Spring Data. Khi trộn SDK với Repository, hai bên phải thống nhất cấu trúc JSON.

### 8.1. So sánh thao tác KV phổ biến

| KV operation của SDK | Hành vi | Điều cần chú ý |
| --- | --- | --- |
| `get` | Đọc theo key | Không có document thường dẫn tới lỗi cụ thể của SDK |
| `insert` | Tạo mới khi key chưa tồn tại | Xung đột nếu key đã có |
| `upsert` | Tạo hoặc thay thế document theo key | Có thể ghi đè field nếu body không đầy đủ |
| `replace` | Thay document đã tồn tại | Có thể dùng CAS để chống lost update |
| `remove` | Xóa document | Cần quyền và quy tắc nghiệp vụ |
| Sub-document operations | Đọc/sửa phần dữ liệu JSON | Cần kiểm soát đường dẫn, điều kiện và concurrency |

Ở mức entity, `repository.save` không nên bị xem là một bản sao một-một của `collection.upsert`: Spring Data quyết định thao tác liên quan tới mapping, trạng thái entity và cơ chế versioning được cấu hình.

### 8.2. Cập nhật với CAS ở SDK

Giả sử hai request cùng đọc hồ sơ và một request đã ghi thay đổi trước. Dùng CAS có thể ngăn request còn lại ghi đè document trên trạng thái cũ:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.ReplaceOptions;

public class CustomerTierUpdater {
    private final Collection collection;

    public CustomerTierUpdater(Collection collection) {
        this.collection = collection;
    }

    public void changeTier(String documentId, String newTier) {
        GetResult current = collection.get(documentId);
        JsonObject body = current.contentAsObject();

        body.put("tier", newTier);

        collection.replace(
                documentId,
                body,
                ReplaceOptions.replaceOptions().cas(current.cas())
        );
    }
}
~~~

`current.cas()` là CAS đọc được cùng document. Nếu document đã thay đổi, lệnh `replace` có điều kiện có thể bị từ chối. Khi xung đột, service phải quyết định **trả lỗi**, **đọc lại** hoặc **thử lại có giới hạn sau khi áp dụng lại thay đổi nghiệp vụ**. Không retry vô hạn hoặc lặp lại các tác dụng phụ ngoài database.

Ví dụ cố ý sửa object JSON đã đọc, tránh tạo một body mới chỉ chứa `tier`. Nếu SDK tạo lại document từ vài field, có thể làm mất dữ liệu còn lại hoặc metadata `_class` mà Spring Data dùng. Dù dùng kiểu body nào, cần kiểm tra chính sách expiry và versioning của thao tác khi cùng document được cập nhật bằng nhiều API.

### 8.3. SDK phù hợp khi nào?

- Cần option và operation cấp thấp chưa được lớp Spring Data đang dùng hỗ trợ thuận tiện.
- Cần sub-document mutation, thao tác KV nâng cao hoặc một cấu hình query/search đặc thù.
- Cần dữ liệu JSON thô hoặc một gateway chung không phụ thuộc entity mapping của Spring Data.
- Muốn đo/kiểm soát rõ từng round trip và phân tích lỗi ở cấp SDK.

Trước khi chọn SDK chỉ vì mục tiêu hiệu năng, kiểm tra xem phương thức Repository/Template đã dùng cùng đường KV hay SQL++ chưa. Nếu bottleneck là index thiếu, đổi API không giải quyết nguyên nhân.

## 9. Phối hợp ba API trong cùng ứng dụng: nên đặt ranh giới ở đâu?

Một kiến trúc hợp lý có thể là:

~~~mermaid
flowchart TB
    API["CustomerController"] --> S["CustomerService: nghiệp vụ, phân quyền"]
    S --> R["CustomerRepository: CRUD, query đơn giản"]
    S --> T["CustomerQueryDao: Template, bộ lọc động"]
    S --> G["CustomerMutationGateway: SDK, operation đặc thù"]
    R --> DB[("Couchbase")]
    T --> DB
    G --> DB
~~~

Tầng service giữ quy tắc domain; lớp persistence chỉ nhận trách nhiệm truy cập dữ liệu. **Không để controller gọi thẳng SDK ở một route và dùng service kiểm tra quyền ở route khác** nếu hai route đều thay đổi cùng dữ liệu nghiệp vụ.

Để phối hợp an toàn cần ít nhất bốn điều kiện:

1. **Cùng keyspace:** bucket, scope, collection và document ID đúng.
2. **Tương thích mapping:** tên field, kiểu dữ liệu, metadata type, custom converter và schema evolution thống nhất.
3. **Quy tắc ghi chung:** optimistic locking/CAS, retry, TTL và durability không mâu thuẫn giữa các đường ghi.
4. **Bất biến nghiệp vụ chung:** validation, tenant authorization, chính sách sửa/xóa, transaction đều do service hoặc domain layer kiểm soát.

### Ví dụ đối chiếu

**Cách nguy hiểm:**

~~~text
API A: repository.findById("customer::c-1001")
       -> sửa fullName -> repository.save(entity có @Version)

Tác vụ B: SDK upsert("customer::c-1001", {"tier": "GOLD"})

Hậu quả có thể:
  - Mất fullName, email, status và các field khác
  - Mất metadata phục vụ Spring Data mapping
  - Không còn bảo đảm hành vi ghi với CAS/expiry như mong đợi
~~~

**Cách có kiểm soát:** Đặt cập nhật `tier` trong một service có hợp đồng rõ; chọn save entity có `@Version` hoặc sub-document/CAS phù hợp; luôn kiểm tra schema và quyền trước khi ghi. Nếu một SDK gateway làm cùng một nghiệp vụ với Repository, viết rõ API nào là nơi xử lý cuối cùng thay đổi đó.

## 10. Reactive Repository, Reactive Template và SDK reactive

Spring Data Couchbase có API đồng bộ và reactive. Chọn theo mô hình thực thi ứng dụng, không chỉ theo sở thích cú pháp.

| Truy cập đồng bộ | Truy cập reactive | Kiểu kết quả tiêu biểu |
| --- | --- | --- |
| `CouchbaseRepository` | `ReactiveCouchbaseRepository` | `Optional<T>` / `List<T>` so với `Mono<T>` / `Flux<T>` |
| `CouchbaseTemplate` | `ReactiveCouchbaseTemplate` | Object/list so với Publisher |
| Java SDK sync | Java SDK async/reactive | Giá trị trực tiếp so với future/publisher theo API |

Ví dụ reactive repository:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    Flux<Customer> findByStatus(String status);
}
~~~

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCustomerReadService {
    private final ReactiveCustomerRepository repository;

    public ReactiveCustomerReadService(
            ReactiveCustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> get(String id) {
        return repository.findById("customer::" + id);
    }
}
~~~

`Mono` thể hiện 0..1 kết quả, `Flux` 0..n kết quả. Ở request tìm theo `status` có thể có nhiều khách hàng, `Flux<Customer>` là lựa chọn hợp lý.

Reactive thích hợp khi muốn duy trì chuỗi I/O không chặn, đặc biệt trong Spring WebFlux. Tuy nhiên:

- Không gọi `block()` trong pipeline WebFlux để lấy dữ liệu đồng bộ.
- Không giả định thay sang reactive sẽ làm một truy vấn SQL++ thiếu index nhanh hơn.
- Khi tìm nhiều document, kiểm soát số thao tác đồng thời, backpressure và timeout.
- Đừng bọc lệnh SDK blocking trong `Mono.just(...)` rồi coi đó là truy cập non-blocking.

SDK cũng có các API async/reactive riêng, nhưng cú pháp và mô hình tài nguyên phụ thuộc phiên bản. Chọn abstraction thống nhất, chỉ trộn khi có lý do rõ ràng.

## 11. Các yêu cầu dữ liệu không thuộc riêng một API

### 11.1. CAS và cập nhật đồng thời

CAS do server quản lý giúp phát hiện **document đã đổi kể từ lần đọc trước**. Ở Spring Data, `@Version` giúp optimistic locking trong các thao tác được hỗ trợ; ở SDK có thể dùng tùy chọn CAS trực tiếp.

~~~text
Request A đọc document (CAS = X)
Request B đọc document (CAS = X)
A ghi thành công -> CAS thay đổi
B ghi kèm CAS = X -> bị từ chối nếu CAS không còn khớp
~~~

CAS chủ yếu kiểm soát một document; không tự làm nhiều thao tác trên các document khác nhau thành một transaction.

### 11.2. TTL và expiry

TTL là metadata cho phép document tự hết hạn. Một field JSON `"expiresAt"` do ứng dụng thêm không khiến Couchbase tự xóa document nếu không cấu hình expiry thực tế.

Khi Repository, Template và SDK cùng ghi vào một document, cần thống nhất:
- Có đặt TTL không?
- Khi cập nhật, expiry được giữ hay thay?
- Giỏ hàng/session có cần thời hạn khác với hồ sơ khách hàng không?

Các annotation/tùy chọn expiry cụ thể và hành vi khi mutation phụ thuộc phiên bản SDK và Spring Data, nên phải đối chiếu trước khi triển khai.

### 11.3. SQL++ và độ mới của index

Đọc theo ID bằng KV khác với tìm theo field qua SQL++ và secondary index. Vừa ghi xong document bằng `save` có thể đọc được bằng key, nhưng query qua index với chính sách nhất quán mặc định có thể tạm thời chưa thấy mutation.

Khi bắt buộc read-your-writes ở query, có thể cân nhắc scan consistency như `request_plus` hoặc nhất quán theo mutation token khi API/phiên bản hỗ trợ, đồng thời chấp nhận chi phí độ trễ. Việc gọi query từ Template hay SDK không tự làm index được cập nhật đồng bộ hơn.

### 11.4. Transaction và durability

Một thao tác `save` và một thao tác `replace` không mặc định tạo giao dịch nguyên tử cho luồng nhiều document. Nếu cần cập nhật tồn kho đồng thời tạo đơn, phải xác định transaction semantics và chọn khả năng transaction được hỗ trợ bởi bộ phiên bản Spring Data/SDK/Server hiện tại.

Durability trả lời câu hỏi mức xác nhận ghi bền trước khi thao tác được xem là thành công; nó khác với CAS và khác với SQL++ index consistency. Các lựa chọn này cần xuất phát từ yêu cầu nghiệp vụ, chứ không phụ thuộc Repository “đơn giản” hay SDK “cao cấp”.

## 12. Khi nào nên thay Repository bằng Template hoặc SDK?

| Tình huống | Nên làm gì? | Không nên mặc định |
| --- | --- | --- |
| Repository có vài derived query dễ đọc | Giữ Repository | Thêm Template chỉ để giảm overhead chưa đo |
| Có nhiều điều kiện lọc động | Xây DAO bằng Template hoặc custom repository | Tạo hàng chục method tên quá dài |
| Cần cập nhật một trường sâu của JSON rất thường xuyên | Đánh giá SDK sub-document operation | Upsert một JSON chỉ chứa trường thay đổi |
| Cần CAS chi tiết ở một lệnh KV | Dùng chức năng Spring Data phù hợp hoặc SDK CAS | Ghi đè khi có conflict |
| Cần Search Service và relevance score | Dùng Search API/tích hợp chuyên biệt | Dùng `findById` hay `LIKE` để thay hẳn FTS |
| Query chậm vì thiếu index | Xem query plan, index và keyspace | Chuyển sang SDK và kỳ vọng hết chậm |
| Nhiều lệnh phải cùng thành công | Xác định transaction API hỗ trợ | Coi một loạt `save` là transaction |
| API WebFlux có tải I/O lớn | Ưu tiên pipeline reactive đồng nhất | Trộn truy cập blocking trong event-loop |

### 12.1. Anti-pattern: thử tồn tại rồi tạo mới

~~~text
if (!repository.existsById(id)) {
    repository.save(entity);
}
~~~

Hai request có thể cùng thấy “chưa tồn tại” trước khi một request ghi. Nếu nghiệp vụ yêu cầu không cho tạo trùng ID, phải dùng **thao tác tạo có điều kiện** hoặc cơ chế phù hợp, xử lý xung đột trực tiếp. SDK `insert` có ngữ nghĩa “chỉ tạo nếu key chưa tồn tại”; với Spring Data, hãy hiểu rõ cách một entity mới được nhận diện và chốt tại tầng ghi, không chỉ dựa vào kiểm tra tồn tại trước đó.

### 12.2. Anti-pattern: tự mở cluster trong mỗi request

~~~text
GET /customer/123
  -> Cluster.connect(...)
  -> bucket(...)
  -> collection(...)
  -> get(...)
  -> cluster.disconnect(...)
~~~

Làm vậy tăng chi phí thiết lập kết nối, khó kiểm soát retry/timeout, dễ gây tải không cần thiết. Trong ứng dụng Spring, nên để client/cluster được cấu hình và quản lý vòng đời tập trung, inject vào gateway và dùng lại.

## 13. Tình huống thực hành: giỏ hàng và lịch sử đơn

Ứng dụng bán hàng có các API:

- `GET /carts/{customerId}`: lấy giỏ hàng hiện tại.
- `POST /carts/{customerId}/items`: sửa items, có thể có nhiều tab đồng thời.
- `GET /orders?status=PAID&from=...`: lọc danh sách đơn đã thanh toán theo thời gian.
- `GET /orders/{orderId}`: lấy chi tiết đơn.
- Một hệ thống nền cần cập nhật một trường lồng trong JSON giỏ hàng.
- Session khách vãng lai phải tự hết hạn sau 30 phút.

### 13.1. Phân loại đường truy cập

| Chức năng | Đường truy cập | API gợi ý | Rủi ro cần giải quyết |
| --- | --- | --- | --- |
| Đọc giỏ theo ID suy từ customerId | KV | Repository `findById` | Không tìm thấy, phân quyền |
| Sửa items trong giỏ | KV + concurrency | Repository `@Version` hoặc SDK CAS | Lost update |
| Lọc đơn theo trạng thái/ngày | SQL++ + index | Repository `@Query` hoặc Template | Index, phân trang, consistency |
| Chi tiết đơn theo orderId | KV | Repository | Đúng collection và key |
| Cập nhật phần JSON lồng nhau | Sub-document KV | SDK nếu cần tính năng đặc thù | Mapping, CAS, tác dụng phụ |
| Session hết hạn | KV + expiry | API có hỗ trợ TTL phù hợp | Không vô tình reset TTL |

### 13.2. Thiết kế service

~~~mermaid
flowchart TD
    API["CartController"] --> S["CartService"]
    S --> R["CartRepository"]
    S --> M["CartMutationGateway (SDK khi cần)"]
    API2["OrderController"] --> OS["OrderService"]
    OS --> OR["OrderRepository"]
    OS --> OQ["OrderQueryDao (Template)"]
    R --> DB[("Couchbase")]
    M --> DB
    OR --> DB
    OQ --> DB
~~~

Một service chỉ nên sử dụng gateway phù hợp với hợp đồng nghiệp vụ. Ví dụ `CartService` quyết định cách giải quyết conflict; `CartMutationGateway` không tự ý ghi đè mọi dữ liệu của giỏ. `OrderQueryDao` cần index để lọc đơn; nó không có quyền thay đổi tính đúng đắn của số tiền đặt hàng dựa vào một Search hit cũ.

### 13.3. Câu hỏi tự kiểm tra

1. **Repository có sử dụng Couchbase Java SDK ở tầng dưới không?** Có, qua hạ tầng Spring Data.
2. **CouchbaseTemplate có biến thao tác theo field thành KV get không?** Không. Nếu không biết ID và phải lọc field, thường cần SQL++/index.
3. **SDK ghi JSON trực tiếp có tự chạy custom converter Spring Data không?** Không nên giả định như vậy.
4. **`@Version` có làm toàn bộ một luồng cập nhật nhiều document thành transaction không?** Không.
5. **Reactive Repository có sửa được vấn đề không có index cho query không?** Không.
6. **Lấy document bằng key có cần secondary index không?** Không, khi key chính xác.
7. **Nếu SDK upsert JSON chỉ có `tier`, điều gì có thể mất?** Các trường còn lại, metadata mapping và chính sách ghi trước đó.
8. **Khi đã biết ID và cần xem ngay document vừa lưu, nên ưu tiên đường nào?** KV theo ID, thay vì truy vấn lại theo thuộc tính nếu không cần thiết.

## 14. Checklist trước khi triển khai production

1. **Định danh dữ liệu:** bucket, scope, collection, document ID rõ ràng, không nhầm giữa các API.
2. **Mapping:** định dạng JSON, type discriminator, custom converter và phiên bản schema tương thích.
3. **Quy tắc API:** Repository cho CRUD/query phổ biến; Template cho truy cập lập trình linh hoạt; SDK cho tính năng đặc thù.
4. **Index:** mọi query SQL++ theo field có index được kiểm chứng bằng `EXPLAIN` và dữ liệu đại diện.
5. **Concurrency:** có phương án CAS/versioning và giải quyết xung đột; retry có giới hạn.
6. **Lưu trữ:** TTL, durability và transaction được chọn theo yêu cầu nghiệp vụ.
7. **Consistency:** xác định mức nhất quán query khi người dùng vừa ghi vừa tìm.
8. **Runtime:** client connection tái sử dụng, timeout, metric, log/tracing và exception mapping hợp lý.
9. **Reactive:** luồng xử lý không chặn, giới hạn mức đồng thời, không gọi `block()` trên event loop.
10. **Kiểm thử:** integration test với Couchbase thực/tương đương cho mapping, query, xung đột CAS và các thay đổi liên quan expiry.

## 15. Kết luận

**Repository**, **CouchbaseTemplate** và **Couchbase Java SDK** đều kết nối tới cùng nền tảng Couchbase nhưng ở mức trừu tượng khác nhau. Repository làm gọn thao tác entity, Template cho phép viết luồng truy cập linh hoạt mà vẫn dùng Spring Data mapping, còn SDK cung cấp quyền kiểm soát trực tiếp những operation và tùy chọn Couchbase.

Điểm cốt lõi khi xây tầng truy cập **Spring Data Couchbase** là chọn API theo **mẫu đọc/ghi và yêu cầu nghiệp vụ**: document ID dẫn đến KV; lọc theo field dẫn đến SQL++ và index; cập nhật đồng thời cần CAS; dữ liệu tạm cần TTL; luồng nhiều document có thể cần transaction; hệ thống reactive cần pipeline không chặn. Sự phối hợp hiệu quả giữa ba API phụ thuộc vào việc giữ thống nhất keyspace, metadata/mapping và cách xử lý tính nhất quán trong toàn hệ thống.
