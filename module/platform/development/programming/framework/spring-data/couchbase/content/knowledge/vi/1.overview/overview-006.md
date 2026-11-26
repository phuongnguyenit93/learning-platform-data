# Ánh xạ đối tượng khác gì ORM và persistence context của JPA?

## 1. Mục tiêu và câu hỏi trọng tâm

Khi chuyển từ **Spring Data JPA** sang **Spring Data Couchbase**, lập trình viên dễ nhận ra các khái niệm quen thuộc: entity Java, `@Id`, `@Version`, Repository, `save` và `findById`. Tuy nhiên, **cú pháp giống nhau không có nghĩa vòng đời đối tượng và cách lưu thay đổi giống nhau**.

Trong JPA, ORM ánh xạ Java object với bảng/hàng và hoạt động cùng **persistence context**: một vùng quản lý các entity đang được theo dõi, hỗ trợ identity map, dirty checking và đồng bộ thay đổi thông qua flush. Spring Data Couchbase ánh xạ Java object với **JSON document** và dựa trên Couchbase Java SDK; một entity vừa đọc bằng Repository thường là đối tượng Java bình thường, **không tự động được theo dõi để ghi lại mọi thay đổi**.

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa **Object–Relational Mapping (ORM)** và **Object–Document Mapping (ODM)** trong Couchbase.
- Phân biệt vòng đời entity JPA `managed` / `detached` với vòng đời entity ở Spring Data Couchbase.
- Hiểu vì sao ở JPA có dirty checking/flush, còn khi sửa document qua Spring Data Couchbase thường phải **gọi thao tác lưu rõ ràng**.
- So sánh quan hệ bảng và JSON lồng nhau; truy cập theo key và SQL++ so với SQL quan hệ.
- Chọn chiến lược CAS, TTL, chỉ mục, transaction và API reactive mà không mang các giả định của JPA sang Couchbase.

Bài học thuộc chương **Tổng quan** của module **SPRING_DATA_COUCHBASE**, đặt nền cho việc xây tầng truy cập Couchbase bằng document mapping, Repository, CouchbaseTemplate và SQL++.

## 2. ORM và object–document mapping: cùng ánh xạ, khác mô hình dữ liệu

**ORM** thường ánh xạ một đồ thị đối tượng Java sang mô hình quan hệ gồm bảng, hàng, khóa chính, khóa ngoại và quan hệ. Với JPA, `@Entity` có thể ánh xạ tới một bảng; `@ManyToOne` hoặc `@OneToMany` mô tả association giữa các entity. ORM xử lý nhiều chi tiết chuyển đổi giữa object và relational model.

**Object–Document Mapping** của Spring Data Couchbase ánh xạ object Java sang document JSON được truy cập bằng **document ID** trong một collection thuộc bucket/scope. Document có thể chứa object hoặc array lồng nhau ngay trong cùng body JSON.

| Góc nhìn | Spring Data JPA / ORM | Spring Data Couchbase / document mapping |
| --- | --- | --- |
| Đơn vị lưu dữ liệu phổ biến | Hàng của bảng | JSON document có khóa riêng |
| Nhận diện | Khóa chính (primary key) | Document ID metadata trong collection |
| Mô hình liên kết | Khóa ngoại, JOIN, association mapping | Embed dữ liệu hoặc tham chiếu ID do ứng dụng thiết kế; SQL++ cũng hỗ trợ JOIN theo điều kiện phù hợp |
| Mapping Java | `@Entity`, `@Table`, `@Column`… | `@Document`, `@Id`, `@Field`… |
| API đặc trưng | `EntityManager`, JPA Repository | Couchbase Repository, `CouchbaseTemplate` |
| Cơ chế truy cập phổ biến | SQL qua JDBC/JPA provider | KV theo ID, SQL++ qua Query/Index Service |
| Theo dõi thay đổi của object đã đọc | Có với entity đang `managed` trong persistence context | Không có persistence context JPA và dirty checking tương ứng |
| Concurrency | JPA `@Version` thường dùng version column | Spring Data Couchbase `@Version` gắn với CAS metadata |
| Giao dịch | JPA flush/persistence context gắn với transaction manager | Couchbase có khả năng transaction riêng; không có dirty checking JPA nhờ transaction |
| Tính linh hoạt schema | Schema quan hệ và migrations | Document JSON có thể có field khác nhau; vẫn cần quản lý schema evolution |

Điểm không nên kết luận quá mức: **Couchbase có SQL++ và hỗ trợ JOIN**, nên “document database thì không có truy vấn” là sai. Khác biệt quan trọng là cách thiết kế dữ liệu, đường truy cập và vòng đời của các Java object được framework quản lý.

## 3. Một nghiệp vụ: hai cách biểu diễn dữ liệu

Giả sử hệ thống lưu hồ sơ khách hàng cùng một vài tùy chọn hiển thị và danh sách địa chỉ.

### 3.1. Trong cơ sở dữ liệu quan hệ

Có thể thiết kế ba bảng:

~~~text
customers
  id (PK)
  full_name
  email
  locale

customer_addresses
  id (PK)
  customer_id (FK -> customers.id)
  label
  city

customer_preferences
  customer_id (PK/FK -> customers.id)
  receive_email
  theme
~~~

Một đối tượng `Customer` có thể liên kết `addresses` và `preferences` bằng các association JPA. Khi cần hiển thị trang hồ sơ, ORM phải tổ chức việc đọc các bảng phù hợp qua JOIN hoặc các truy vấn phụ tùy fetch strategy.

### 3.2. Trong Couchbase

Một lựa chọn là lưu toàn bộ dữ liệu có vòng đời gần nhau vào JSON document trong `shop.crm.customers`, metadata ID `customer::c-1001`:

~~~json
{
  "fullName": "Nguyen An",
  "email": "an@example.com",
  "preferences": {
    "locale": "vi-VN",
    "receiveEmail": true,
    "theme": "dark"
  },
  "addresses": [
    { "label": "home", "city": "Da Nang" },
    { "label": "work", "city": "Ha Noi" }
  ]
}
~~~

Trong ví dụ này, document key nằm **ngoài JSON body**. Spring Data Couchbase ánh xạ trường Java có `@Id` thành metadata ID; không nên nhầm với một field `"id"` tình cờ có trong JSON.

~~~mermaid
flowchart TB
    A["Java Customer object"] --> B{"Mapping?"}
    B -->|JPA ORM| C["customers row"]
    C --> D["customer_addresses rows qua FK"]
    C --> E["customer_preferences row qua FK"]
    B -->|Spring Data Couchbase| F["Một JSON document"]
    F --> G["preferences object"]
    F --> H["addresses array"]
    F --> I["Document ID metadata"]
~~~

Embed giúp đọc cùng lúc các phần thường dùng chung, nhưng không phù hợp với mọi dữ liệu. Ví dụ, **tất cả đơn hàng lịch sử** của một khách hàng có thể tăng không giới hạn; không nên nhồi toàn bộ vào một document hồ sơ. Khi quan hệ có vòng đời độc lập hoặc khối lượng lớn, tách thành document riêng và tham chiếu bằng ID thường dễ vận hành hơn.

## 4. Persistence context của JPA thực sự làm gì?

**Persistence context** là môi trường quản lý một tập entity instance theo định danh trong phạm vi quản lý của JPA `EntityManager`. Nó có các đặc tính thường gặp:

1. **Identity map:** trong cùng persistence context, khi lấy cùng một entity theo primary key qua các thao tác phù hợp, JPA bảo đảm identity của managed entity.
2. **Managed state:** entity được đưa vào context có trạng thái được JPA theo dõi.
3. **Dirty checking:** khi thuộc tính của managed entity thay đổi, provider phát hiện khác biệt để phát lệnh cập nhật khi flush.
4. **Flush:** đồng bộ thay đổi pending từ persistence context xuống database vào những thời điểm theo quy tắc flush mode/transaction.
5. **Lifecycle transitions:** entity có thể `new`, `managed`, `detached`, `removed`. `persist`, `merge`, `detach`, `remove` tương tác với trạng thái này.
6. **Association handling:** JPA có thể xử lý cascading, fetch strategy và lazy proxies theo mapping và phạm vi persistence context.

Ví dụ đơn giản với Spring Data JPA:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class CustomerJpa {
    @Id
    private String id;

    private String email;

    @Version
    private Long version;

    protected CustomerJpa() {}

    public String getId() { return id; }

    public String getEmail() { return email; }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerJpaRepository
        extends JpaRepository<CustomerJpa, String> {
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JpaCustomerService {
    private final CustomerJpaRepository repository;

    public JpaCustomerService(CustomerJpaRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changeEmail(String id, String newEmail) {
        CustomerJpa customer = repository.findById(id)
                .orElseThrow();

        customer.setEmail(newEmail);

        // Không nhất thiết gọi repository.save(customer):
        // customer đang managed trong persistence context.
        // JPA provider dirty-check và flush thay đổi.
    }
}
~~~

Trong đoạn code, `@Transactional` thiết lập một phạm vi transaction có hỗ trợ JPA persistence context phù hợp. Sau `findById`, `customer` là managed entity trong context đó. Việc gọi setter thay đổi trạng thái managed; khi flush (thường trước khi transaction hoàn tất), JPA provider có thể phát lệnh `UPDATE`.

**Giới hạn cần hiểu:** Không phải mọi Java object kiểu `@Entity` luôn được tự động lưu. Nếu entity đã `detached` hoặc bạn sửa một object được tạo ngoài persistence context, thay đổi không được dirty checking theo cách trên. `save` của Spring Data JPA vẫn có vai trò với entity mới/đã detach tùy trường hợp.

### 4.1. Dirty checking khác với một lần gọi update

~~~mermaid
sequenceDiagram
    participant S as JpaCustomerService
    participant PC as JPA Persistence Context
    participant DB as RDBMS
    S->>PC: findById(id)
    PC->>DB: SELECT nếu cần
    DB-->>PC: Row
    PC-->>S: Managed entity
    S->>S: customer.setEmail(...)
    Note over PC: Theo dõi trạng thái / dirty checking
    S->>PC: Hoàn tất transaction / flush
    PC->>DB: UPDATE khi có thay đổi cần ghi
~~~

Không nên suy rằng Java setter gọi SQL ngay. Thường JPA gom hoặc trì hoãn thao tác đến flush; hành vi cụ thể tùy provider và cấu hình flush mode. Việc dùng transaction và persistence context cũng không đồng nghĩa mọi bài toán cập nhật đồng thời tự động an toàn: cần isolation, locking và ràng buộc dữ liệu phù hợp.

## 5. Spring Data Couchbase không có persistence context kiểu JPA

Với Spring Data Couchbase, thao tác đọc document chuyển JSON thành Java object; object nhận được **không được JPA EntityManager theo dõi**. Do đó:

- Đổi một field của object đã đọc **không tự ghi trở lại Couchbase**.
- Không có vòng đời `managed/detached` của JPA cho object Couchbase thông thường.
- Không có identity map cấp persistence context bảo đảm hai lần đọc cùng key trả đúng một Java instance.
- Không có `flush()` kiểu JPA để tự gom các object đã sửa rồi đồng bộ toàn bộ lúc transaction kết thúc.
- Annotation `@Transactional` **không tự đem dirty checking của JPA sang Couchbase**, kể cả khi một transaction Couchbase đã được cấu hình.

Ví dụ entity cho Spring Data Couchbase:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class CustomerDocument {
    @Id
    private String id;

    @Field
    private String email;

    @Field
    private String fullName;

    @Version
    private Long version;

    public CustomerDocument() {}

    public CustomerDocument(String id, String email, String fullName) {
        this.id = id;
        this.email = email;
        this.fullName = fullName;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }
}
~~~

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerDocumentRepository
        extends CouchbaseRepository<CustomerDocument, String> {
}
~~~

~~~java
import org.springframework.stereotype.Service;

@Service
public class CouchbaseCustomerService {
    private final CustomerDocumentRepository repository;

    public CouchbaseCustomerService(CustomerDocumentRepository repository) {
        this.repository = repository;
    }

    public CustomerDocument changeEmail(
            String customerId, String newEmail) {

        CustomerDocument customer = repository.findById(
                "customer::" + customerId
        ).orElseThrow();

        customer.setEmail(newEmail);

        // Thao tác ghi explicit: cần gọi save.
        return repository.save(customer);
    }
}
~~~

**Điểm quyết định là `repository.save(customer)`**. Nếu service chỉ gọi `customer.setEmail(newEmail)` rồi trả về mà không lưu, bộ nhớ Java đã đổi nhưng Couchbase không tự nhận biết thay đổi để ghi. Khi muốn update có điều kiện, sử dụng CAS/optimistic locking hoặc operation cụ thể phù hợp.

Sơ đồ vòng đời tối giản:

~~~mermaid
sequenceDiagram
    participant S as CouchbaseCustomerService
    participant R as Spring Data Couchbase
    participant DB as Couchbase Data Service
    S->>R: findById(key)
    R->>DB: KV get(key)
    DB-->>R: JSON + metadata (CAS)
    R-->>S: CustomerDocument POJO
    S->>S: setEmail(newEmail)
    Note over S: Chưa có ghi dữ liệu
    S->>R: save(customer)
    R->>DB: KV write theo mapping/version
    DB-->>R: Kết quả ghi
    R-->>S: Entity kết quả
~~~

Khi Spring Data ánh xạ entity, có thể xuất hiện metadata phân biệt loại object (ví dụ field `_class` tùy cấu hình). Đây không phải tính năng dirty checking. Cả Repository và `CouchbaseTemplate` sử dụng cơ chế mapping trên các thao tác tương ứng.

## 6. Năm khác biệt dễ gây lỗi khi chuyển từ JPA sang Couchbase

| Giả định mang từ JPA | Điều xảy ra với Couchbase | Cách viết đúng hơn |
| --- | --- | --- |
| “Đã sửa entity trong transaction thì tự lưu” | Không có JPA persistence context/dirty checking | Gọi `save` hoặc operation update cụ thể |
| “Đọc cùng ID hai lần luôn là cùng object trong Unit of Work” | Không có identity map JPA mặc định | Đừng dựa vào tham chiếu Java trùng nhau; thiết kế cache riêng nếu cần |
| “`@OneToMany` sẽ tự JOIN/lazy load” | Không có association handling giống JPA | Embed hoặc tham chiếu ID; thiết kế truy cập bằng KV/SQL++ |
| “`@Version` là một cột version tăng số” | Trong Couchbase version liên quan tới CAS metadata | Hiểu rõ CAS và xử lý optimistic locking |
| “`@Transactional` đương nhiên bao mọi `save` trong một đơn vị JPA” | Transaction semantics khác; không có JPA flush | Kiểm tra khả năng transaction của stack và thiết kế ranh giới rõ |
| “Đã query được bằng ID thì lọc theo field cũng không cần index” | KV và SQL++ là hai đường truy cập khác nhau | Thiết kế secondary index cho query theo field |
| “Vừa save xong, query index chắc chắn thấy ngay” | Secondary index có thể cập nhật trễ | Cấu hình query consistency theo yêu cầu |

Những nhầm lẫn này thường gây ra **mất cập nhật**, truy vấn chậm, dữ liệu không phản ánh thay đổi hoặc một hành vi transaction khác mong đợi.

## 7. Quan hệ và aggregate: không nên sao chép nguyên mapping JPA

Trong JPA, một quan hệ có thể được biểu diễn bằng annotation, ví dụ:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private CustomerJpa customer;
~~~

Một association như vậy có thể được JPA provider giải quyết khi cần trong persistence context, tùy cách tải và trạng thái kết nối. Nếu code chạm thuộc tính lazy sau khi context đã đóng, có thể gặp lỗi hoặc cần fetch strategy khác. Đây là phần cốt lõi của ORM quan hệ.

Với Couchbase, bạn phải quyết định ranh giới document: dữ liệu nào **nên nằm chung** để đọc/cập nhật cùng nhau, dữ liệu nào **nên tách riêng** và tham chiếu bằng document ID.

### 7.1. Embed khi các phần thường được đọc và thay đổi cùng nhau

Ví dụ giỏ hàng theo ID `cart::customer-42`:

~~~json
{
  "customerId": "customer-42",
  "currency": "VND",
  "items": [
    { "sku": "sku-100", "quantity": 2, "unitPrice": 85000 },
    { "sku": "sku-200", "quantity": 1, "unitPrice": 120000 }
  ]
}
~~~

Màn hình giỏ hàng có thể lấy toàn bộ dữ liệu bằng một KV get. Các dòng `items` thường thuộc một aggregate cập nhật cùng giỏ; embed thường tự nhiên nếu số phần tử có giới hạn.

**Đổi lại:** khi nhiều tab cùng cập nhật một document, cần giải quyết contention. Document phình to khi danh sách không giới hạn có thể làm tăng chi phí đọc/ghi.

### 7.2. Tham chiếu ID khi vòng đời độc lập

Ví dụ tài khoản khách hàng có hàng chục nghìn đơn hàng theo thời gian. Thay vì embed lịch sử đơn hàng vào document khách hàng, mỗi đơn hàng có ID riêng:

~~~json
{
  "orderId": "ord-2049",
  "customerId": "customer-42",
  "createdAt": "2026-11-25T03:00:00Z",
  "status": "PAID"
}
~~~

Metadata key của document đơn hàng có thể là `order::ord-2049`. Trường `customerId` giúp query các đơn của khách hàng, nhưng bản thân nó **không phải một ràng buộc khóa ngoại do Couchbase tự thực thi**. Nếu cần list đơn theo khách hàng, thường dùng SQL++ với index phù hợp.

~~~sql
SELECT META(o).id AS documentId, o.customerId, o.createdAt, o.status
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Index khởi đầu minh họa:

~~~sql
CREATE INDEX ix_orders_customer_date
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Cú pháp và query plan cuối cùng cần xác nhận theo phiên bản Couchbase, dữ liệu và workload. Query sinh bởi Spring Data có thể bổ sung điều kiện phân biệt loại entity và projection riêng.

### 7.3. Vì sao nên thiết kế từ access pattern?

| Nhu cầu | Quan hệ/ORM thường nghĩ đến | Document modeling thường cân nhắc |
| --- | --- | --- |
| Xem chi tiết đơn cùng dòng hàng | JOIN/fetch hàng và order items | Embed item snapshot có giới hạn |
| Liệt kê đơn theo khách hàng và ngày | SQL filter, join/index | SQL++ + index theo `customerId`/`createdAt` |
| Thay địa chỉ hiện tại của người dùng | UPDATE bảng địa chỉ | Update document hồ sơ |
| Giữ địa chỉ giao hàng lịch sử | Tham chiếu/snapshot theo model | Embed snapshot vào document đơn |
| Dữ liệu tăng liên tục | Bảng con riêng | Document riêng, tham chiếu và phân trang |

Document modeling không nhất thiết “đơn giản hơn ORM” trong mọi trường hợp. Nó chuyển trọng tâm sang **đường đọc/ghi, kích thước document, cập nhật đồng thời và tính nhất quán** thay vì chỉ lập sơ đồ quan hệ.

## 8. @Id và @Version: giống tên, khác ý nghĩa lưu trữ

### 8.1. `@Id`

Trong JPA, `@Id` thường ánh xạ thuộc tính Java đến cột khóa chính trong bảng. Trong Spring Data Couchbase, `@Id` biểu diễn **document ID metadata**, thuộc một collection cụ thể.

Ví dụ:

~~~text
JPA:
  customers.id = "c-1001"

Couchbase:
  bucket: shop
  scope: crm
  collection: customers
  document ID: customer::c-1001
  JSON body: { "email": "an@example.com", ... }
~~~

Cùng chuỗi key ở hai collection Couchbase khác nhau vẫn có thể là hai document khác nhau. Tiền tố `customer::` chỉ là quy ước ứng dụng, không phải yêu cầu của Couchbase.

### 8.2. `@Version` và optimistic locking

Trong JPA, `@Version` thường là một trường được ánh xạ thành cột version. Provider dùng nó để phát hiện concurrent update: lệnh `UPDATE` có điều kiện theo version cũ và tăng version theo cơ chế optimistic locking.

Trong Spring Data Couchbase, `@Version` được dùng để hỗ trợ optimistic locking dựa trên **Compare-And-Swap (CAS)** của document. CAS là metadata do Couchbase quản lý; không nên coi nó là một trường phiên bản số tăng tuần tự do ứng dụng tự duy trì trong JSON.

~~~text
T0: A đọc customer::c-1001, CAS=C1
T1: B đọc customer::c-1001, CAS=C1
T2: A đổi email, save -> thành công, document nhận CAS=C2
T3: B đổi tier trên bản cũ, save với CAS=C1 -> conflict
~~~

Spring Data có thể chuyển xung đột version thành ngoại lệ tương ứng. Ứng dụng phải quyết định cách xử lý: báo conflict, yêu cầu tải lại hoặc đọc mới rồi thử lại **có giới hạn**. Không retry mù quáng nếu thao tác có tác dụng phụ, đặc biệt với thanh toán, cấp quyền hoặc thông báo.

CAS phù hợp để phát hiện cập nhật đua nhau trên một document. Nó **không tạo nguyên tử đa document** và cũng không thay thế cơ chế transaction cho nhiều document.

## 9. Transaction JPA khác transaction Couchbase ở đâu?

Một ranh giới `@Transactional` thường gắn với JPA transaction và persistence context, nơi managed entities có thể được flush cùng transaction. Nhưng Couchbase không dùng JPA EntityManager và không tự gom những sửa đổi vào Java object chưa `save`.

Điều đó không có nghĩa Couchbase “không có giao dịch”: Couchbase có khả năng transaction đa document, và hệ sinh thái SDK/Spring Data có cơ chế tích hợp tùy **phiên bản, cấu hình và API**. Tuy nhiên, cú pháp annotation hoặc tên phương thức tương tự không bảo đảm semantics và phạm vi hỗ trợ giống JPA.

| Câu hỏi | JPA | Spring Data Couchbase / SDK |
| --- | --- | --- |
| Sửa managed entity rồi thoát transaction có phát sinh ghi? | Có thể, qua dirty checking và flush | Không, nếu chỉ sửa POJO mà không gọi ghi |
| Một `save` đại diện cho cả transaction? | Không | Không |
| Một thao tác cập nhật một document có ranh giới nguyên tử? | Theo database transaction và lệnh SQL | KV mutation trên một document có tính nguyên tử theo semantics thao tác |
| Cập nhật nhiều entity/document phải cùng thành công? | Cần transaction phù hợp | Cần transaction Couchbase phù hợp hoặc workflow bù trừ |
| Giao dịch có tự bảo đảm query index thấy dữ liệu mới tức thì? | Phụ thuộc isolation, flush và query semantics | Không được suy ra từ commit; phải hiểu consistency của SQL++/Search index |

Ví dụ nghiệp vụ tạo đơn hàng và giảm tồn kho trên hai document: đọc tồn kho, kiểm tra còn đủ, ghi đơn, cập nhật tồn kho. Đây là bài toán nhiều đối tượng, có race condition và yêu cầu commit/rollback. Không nên chỉ dùng `repository.save(order)` rồi `repository.save(stock)` và gọi đó là một giao dịch mà không xác minh transaction manager/API đã được cấu hình đúng.

Với hệ thống phân tán nhiều service, còn cần xem xét idempotency, retry và cơ chế bù trừ; chúng không được giải quyết chỉ bằng việc chọn JPA hay Couchbase.

## 10. Query SQL++ và index cũng không giống JPA query mặc định

Ở JPA, developer có thể dùng JPQL/Criteria; provider tạo SQL truy cập các bảng theo mapping. Ở Spring Data Couchbase, derived query hoặc `@Query` có thể sinh **SQL++** truy cập JSON fields và secondary indexes.

Ví dụ Repository:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerDocumentRepository
        extends CouchbaseRepository<CustomerDocument, String> {

    List<CustomerDocument> findByEmail(String email);
}
~~~

- `findById(id)` thường dùng KV, không cần secondary index.
- `findByEmail(email)` tìm theo thuộc tính JSON, thường chạy SQL++ với index.
- `@Query` hoặc `CouchbaseTemplate` có thể diễn đạt query phức tạp hơn.
- SDK trực tiếp có thể thực thi SQL++/Search khi cần các tùy chọn đặc thù.

Ví dụ index theo email trong `shop.crm.customers`:

~~~sql
CREATE INDEX ix_customers_email
ON `shop`.`crm`.`customers`(email);
~~~

**Lưu ý về generated query:** Spring Data có thể thêm điều kiện phân biệt kiểu entity và metadata cần cho mapping. Query/index phải được kiểm tra dựa trên truy vấn **thực tế** bằng `EXPLAIN` và số liệu chạy, không chỉ dựa vào tên method. Nếu bộ lọc email phải là duy nhất theo nghiệp vụ, một secondary index thông thường **không mặc nhiên áp đặt ràng buộc unique email**.

### 10.1. Vấn đề vừa ghi vừa query

~~~text
repository.save(customer)      -> ghi document
repository.findById(id)        -> đọc qua KV
repository.findByEmail(email)  -> đọc qua SQL++/index
~~~

Secondary index có thể cập nhật trễ so với mutation. Vì thế ngay sau khi lưu, `findById` có thể cho dữ liệu mới nhưng `findByEmail` với chính sách consistency mặc định có thể tạm thời không thấy kết quả. Khi cần read-your-writes ở query, phải xét scan consistency như `request_plus` hoặc mức nhất quán theo mutation token nếu stack hỗ trợ, và đo chi phí chờ index.

Đây là vấn đề **index/query consistency**, không liên quan đến JPA persistence context hay việc entity Java có được dirty checking hay không.

## 11. CouchbaseTemplate và Java SDK nằm ở đâu khi không có EntityManager?

Khi dự án JPA cần can thiệp sâu, lập trình viên thường nghĩ đến `EntityManager`. Trong Spring Data Couchbase, lớp thao tác linh hoạt tương ứng về **vai trò sử dụng** thường là `CouchbaseTemplate`. Tuy nhiên, **Template không phải phiên bản đổi tên của EntityManager**.

Ví dụ đọc document với Template:

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerLookup {
    private final CouchbaseTemplate template;

    public CustomerLookup(CouchbaseTemplate template) {
        this.template = template;
    }

    public CustomerDocument findOne(String id) {
        return template.findById(CustomerDocument.class)
                .one("customer::" + id);
    }
}
~~~

Template giữ các lợi ích như mapper, converter và operations trên entity, nhưng không có context theo dõi entity và flush dirty changes như JPA. Sau `findOne`, nếu đổi thuộc tính và muốn lưu, vẫn phải gọi một thao tác ghi thích hợp.

### 11.1. Khi nào cần Java SDK trực tiếp?

Couchbase Java SDK có API KV, SQL++, Search và các thao tác chuyên biệt như sub-document, CAS options, expiry options hoặc durability options. Có thể sử dụng SDK trong một gateway mà Spring quản lý, ví dụ:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import org.springframework.stereotype.Component;

@Component
public class CustomerRawGateway {
    private final Collection collection;

    public CustomerRawGateway(Cluster cluster) {
        this.collection = cluster.bucket("shop")
                .scope("crm")
                .collection("customers");
    }

    public JsonObject getBody(String documentId) {
        return collection.get(documentId).contentAsObject();
    }
}
~~~

SDK trả JSON body thực tế; nó **không tự dùng mọi annotation mapping và converter Spring Data**. Nếu Repository lưu metadata loại entity như `_class`, một SDK `upsert` chỉ với vài field có thể làm mất metadata và các field còn lại.

Tránh tạo `Cluster.connect` cho từng request. Trong ứng dụng Spring, tái sử dụng client/cluster được cấu hình và quản lý vòng đời tập trung. Cả Repository lẫn Template sử dụng SDK bên dưới; việc đổi API không thay thế tối ưu query/index.

## 12. TTL, CAS và schema evolution khi không có dirty checking

Document mapping không tự giải quyết tất cả hành vi dữ liệu. Hãy phân biệt:

| Cơ chế | Cần để làm gì | Có tự xuất hiện khi gắn `@Document`? |
| --- | --- | --- |
| `@Id` | Xác định document key | Cần khai báo/chiến lược tạo ID |
| `@Version` / CAS | Tránh lost update giữa request cạnh tranh | Phải chọn cơ chế và xử lý conflict |
| TTL/expiry | Document tự hết hạn | Không; cần cấu hình expiry phù hợp |
| Durability | Quy định mức xác nhận ghi bền | Phải chọn mức phù hợp cho mutation |
| Secondary index | Tìm theo field JSON bằng SQL++ | Không tự có index tối ưu |
| Transaction | Nhiều document cần atomicity/rollback | Không suy từ việc dùng Repository |
| Schema evolution | Đọc được document của phiên bản cũ | Cần quy ước, validation và migration |

### 12.1. TTL không phải một trường JSON `expiresAt`

Ví dụ lưu session có field `"expiresAt"` trong body không có nghĩa Couchbase sẽ tự xóa document. **Expiry là metadata/cấu hình vòng đời document**, được thiết lập qua API hỗ trợ. Khi nhiều code path dùng Repository, Template hoặc SDK cập nhật cùng session, cần xác định cách giữ hoặc làm mới TTL; tránh vô tình khiến session hết hạn sai.

### 12.2. Schema linh hoạt vẫn cần hợp đồng

Hai document cùng collection có thể khác field. Một phiên bản cũ có `phoneNumber`, phiên bản mới đổi thành `phone`; nếu code Java chỉ đọc `phone`, document cũ có thể không chứa giá trị mong đợi. Khác với một migration DDL quan hệ, với document database có thể cần migration theo lô hoặc cơ chế đọc tương thích nhiều phiên bản.

Không nên dựa vào việc không có persistence context để bỏ qua kiểm thử mapping. Các thay đổi về tên trường, kiểu dữ liệu, enum, nested object và metadata discriminator có thể ảnh hưởng Repository, Template, query và SDK gateway.

## 13. Reactive không bổ sung persistence context

Spring Data Couchbase còn có `ReactiveCouchbaseRepository` và `ReactiveCouchbaseTemplate`. Các API này trả Publisher dạng Reactor `Mono` và `Flux`, hữu ích khi xây dựng pipeline I/O không chặn.

Ví dụ:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Mono;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<CustomerDocument, String> {

    Mono<CustomerDocument> findByEmail(String email);
}
~~~

Nếu email **không duy nhất**, phương thức trên có thể không phải hợp đồng kết quả phù hợp; hãy dùng `Flux<CustomerDocument>` khi có thể có nhiều document và xử lý số lượng kết quả rõ ràng.

Reactive không thay đổi các nguyên tắc:

- Sau khi nhận object qua `Mono<CustomerDocument>`, setter **không tự lưu**; cần compose thao tác `save` khi muốn ghi.
- Một query SQL++ thiếu index vẫn chậm dù kết quả là `Flux`.
- CAS/TTL/transaction vẫn theo Couchbase API và quy tắc nghiệp vụ.
- Không gọi `block()` trong pipeline WebFlux; thiết kế reactive xuyên suốt khi muốn tối ưu hiệu quả chờ I/O.

Ví dụ minh họa cách ghi tường minh:

~~~java
import reactor.core.publisher.Mono;

public Mono<CustomerDocument> changeEmail(
        ReactiveCustomerRepository repository,
        String id, String newEmail) {

    return repository.findById("customer::" + id)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Customer not found")))
            .flatMap(customer -> {
                customer.setEmail(newEmail);
                return repository.save(customer);
            });
}
~~~

`flatMap` nối tiếp thao tác ghi bất đồng bộ; không có persistence context JPA đứng sau để tự động flush thay đổi của object.

## 14. Thực hành: chuyển một service JPA sang Couchbase

Ứng dụng có một đoạn service JPA:

~~~java
@Transactional
public void updateProfile(String id, String email) {
    CustomerJpa customer = jpaRepository.findById(id).orElseThrow();
    customer.setEmail(email);
    // JPA dirty checking trong persistence context.
}
~~~

Khi chuyển sang Couchbase, các bước không chỉ là đổi `JpaRepository` thành `CouchbaseRepository`:

1. **Thiết kế aggregate:** hồ sơ nên là document nào, preferences/addresses embed hay tham chiếu?
2. **Thiết kế keyspace:** bucket/scope/collection nào lưu customer, ID có thể suy từ business key không?
3. **Đổi model mapping:** dùng `@Document`, `@Id`, `@Field`, `@Version` phù hợp.
4. **Đổi semantics ghi:** gọi `save` hoặc operation update rõ ràng; không chờ JPA flush.
5. **Đổi concurrency:** chọn `@Version`/CAS và chính sách giải quyết xung đột.
6. **Thiết kế query:** `findByEmail` cần SQL++/secondary index; phân biệt với `findById` dùng KV.
7. **Xem xét transaction:** nếu có nhiều document phải cùng thành công, thiết kế transaction Couchbase phù hợp với stack thực tế.
8. **Kiểm soát vận hành:** TTL, durability, timeout, retry, metric, query plan và quyền truy cập.

Ví dụ service Couchbase sau khi đổi:

~~~java
public CustomerDocument updateProfile(String id, String email) {
    CustomerDocument customer = couchbaseRepository
            .findById("customer::" + id)
            .orElseThrow();

    customer.setEmail(email);
    return couchbaseRepository.save(customer);
}
~~~

Đoạn này giả định `couchbaseRepository` có kiểu `CustomerDocumentRepository` và đã được inject trong service. Với `@Version`, nếu có xung đột khi lưu, service nên xử lý lỗi optimistic locking hoặc retry có kiểm soát tùy nghiệp vụ. Việc lưu thành công không tự nghĩa rằng mọi query SQL++ qua index sẽ thấy thay đổi ngay ở chính sách consistency mặc định.

### 14.1. Những lỗi điển hình

| Lỗi | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Cập nhật Java object nhưng database không đổi | Tưởng Couchbase có JPA dirty checking | Gọi save/update operation |
| Hai request ghi đè dữ liệu nhau | Không dùng CAS/optimistic locking | `@Version` hoặc SDK CAS với xử lý conflict |
| Đọc qua Repository thiếu field sau khi SDK ghi | SDK upsert body không đầy đủ hoặc mất metadata mapping | Thống nhất converter/schema và cách ghi |
| Truy vấn theo email chậm | Thiếu secondary index hoặc query plan không phù hợp | Xem SQL++ sinh ra, `EXPLAIN` và index |
| Mới ghi xong query chưa thấy | Secondary index chưa cập nhật tới mutation | Chọn query consistency phù hợp |
| Lỗi khi tách association từ JPA | Mong JPA fetch/cascade vẫn tồn tại | Thiết kế embed/tham chiếu và luồng đọc rõ |
| Session không hết hạn | Chỉ có JSON field `expiresAt` | Thiết lập expiry metadata bằng API tương ứng |
| Thay API thành reactive vẫn chậm | Query/index hoặc blocking I/O vẫn là nút thắt | Phân tích query plan và pipeline end-to-end |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Ở JPA, vì sao setter trên managed entity có thể khiến database được cập nhật mà không cần gọi `save`?

*Gợi ý:* Persistence context theo dõi managed state, dirty checking và flush.

**Câu 2.** Trong Spring Data Couchbase, nếu lấy entity bằng `findById`, đổi email và không gọi `save` thì chuyện gì xảy ra?

*Gợi ý:* Chỉ object trong bộ nhớ đổi; không có JPA dirty checking để tự ghi document.

**Câu 3.** `@Version` của hai hệ thống có hoàn toàn cùng định dạng lưu trữ không?

*Gợi ý:* JPA thường dùng version column; Couchbase dùng CAS metadata qua cơ chế mapping phù hợp.

**Câu 4.** Vì sao không nên embed hàng trăm nghìn đơn hàng vào document khách hàng?

*Gợi ý:* Kích thước tăng không giới hạn, cập nhật nóng và vòng đời độc lập. Nên tách document và dùng ID/query.

**Câu 5.** Dùng `@Transactional` có khiến Couchbase thay đổi mọi POJO đã đọc rồi bị sửa setter trở nên tự ghi được không?

*Gợi ý:* Không. Transaction Couchbase và JPA persistence context là hai khái niệm khác nhau.

**Câu 6.** `findById` và `findByEmail` có sử dụng cùng index không?

*Gợi ý:* Lookup theo key thường dùng KV, còn query field JSON thường dùng SQL++/secondary index.

## 16. Kết luận

**Spring Data Couchbase thực hiện object–document mapping; nó không phải JPA ORM với persistence context.** Repository và `CouchbaseTemplate` giúp ứng dụng thao tác với Java entity, converter và JSON document, nhưng object được đọc không có dirty checking/flush kiểu JPA. Khi muốn ghi thay đổi, phải gọi thao tác lưu/cập nhật rõ ràng và kiểm soát CAS, TTL cùng quy tắc transaction tương ứng.

Khi thiết kế tầng dữ liệu, hãy bắt đầu từ **bucket/scope/collection, document ID, cấu trúc JSON và mẫu truy cập**: biết ID thì dùng KV; lọc theo field thì dùng SQL++ với index; cập nhật đồng thời thì cần CAS; nhiều document đòi hỏi giao dịch hoặc workflow thích hợp; ứng dụng nhiều I/O có thể chọn reactive API. Hiểu đúng ranh giới giữa mapping và persistence context giúp tránh mang các giả định JPA sang Couchbase và xây được tầng truy cập có hiệu năng, tính nhất quán và khả năng vận hành tốt.
