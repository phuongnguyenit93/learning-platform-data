# ReactiveCouchbaseRepository và ReactiveCouchbaseTemplate

Trong **SPRING_DATA_COUCHBASE**, ứng dụng có thể truy cập Couchbase theo mô hình đồng bộ hoặc theo mô hình **reactive**. Với reactive, thao tác truy cập dữ liệu được biểu diễn bằng các publisher của Project Reactor, chủ yếu là `Mono<T>` và `Flux<T>`. Hai điểm vào quan trọng trong Spring Data Couchbase là **`ReactiveCouchbaseRepository`**, phù hợp với truy vấn có hợp đồng tương đối ổn định, và **`ReactiveCouchbaseTemplate`**, phù hợp khi muốn điều khiển thao tác truy cập Couchbase linh hoạt hơn.

Bài thuộc chương **Truy cập phản ứng**, tập trung vào cách sử dụng, lựa chọn và phối hợp hai API này. Mục tiêu không chỉ là đổi `Customer` thành `Mono<Customer>` hoặc `List<Customer>` thành `Flux<Customer>`: cần hiểu **lúc nào câu truy vấn được chạy**, phân biệt truy cập theo document ID với truy vấn SQL++, xử lý kết quả rỗng/lỗi, giới hạn dữ liệu, index, TTL, CAS, giao dịch và consistency. Bucket/scope/collection và document mapping vẫn là những phần nền tảng quyết định truy vấn đọc đúng dữ liệu hay không.

> **Ý chính:** Reactive là một mô hình tổ chức và tiêu thụ thao tác I/O, **không phải cam kết** rằng mọi truy vấn đều nhanh hơn, mọi yêu cầu đều chạy song song hoặc mọi lỗi consistency được tự động giải quyết.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `Mono` và `Flux`, và mô tả các tín hiệu `onNext`, `onComplete`, `onError` theo Reactive Streams.
2. Khai báo `ReactiveCouchbaseRepository<Customer, String>` với các thao tác CRUD và truy vấn dẫn xuất đơn giản.
3. Nhận diện những tình huống nên sử dụng `ReactiveCouchbaseTemplate` hoặc interface `ReactiveCouchbaseOperations` thay vì mở rộng tên phương thức repository.
4. Viết pipeline không chặn với `map`, `flatMap`, `switchIfEmpty`, `then` và xử lý lỗi có chủ đích.
5. Hiểu vì sao gọi `subscribe()` tùy tiện hoặc `block()` trong xử lý WebFlux là sai mô hình.
6. Phân biệt truy cập key-value theo ID với truy vấn SQL++ theo field, cùng nhu cầu secondary index.
7. Xử lý đúng khi `findById` không có document, khi query trả nhiều document hoặc khi giá trị JSON là `NULL`/`MISSING`.
8. Kiểm soát số lượng kết quả, concurrency, backpressure và thời gian thực thi mà không giả định `Flux.take(n)` chính là SQL++ `LIMIT n`.
9. Đánh giá ảnh hưởng của scan consistency, TTL, CAS/optimistic locking và transaction trong luồng reactive.
10. Kiểm thử các luồng bằng `StepVerifier` và integration test trên một collection Couchbase dành riêng cho test.

## 2. Reactive trong tầng truy cập Couchbase nghĩa là gì?

Thay vì gọi một hàm và chờ đến khi có kết quả `Customer`, thao tác reactive thường trả về một **mô tả công việc bất đồng bộ**:

```java
Mono<Customer> customerMono = repository.findById(customerId);
```

Lúc này, `customerMono` là một publisher. Việc lấy dữ liệu và phát kết quả diễn ra theo quy tắc subscription của publisher và thư viện triển khai. Trong các pipeline reactive điển hình, truy cập Couchbase bắt đầu khi có một subscriber; không nên coi việc tạo biến `Mono` là bằng chứng document đã được đọc xong.

### 2.1. Hai kiểu publisher thường gặp

| Kiểu | Số phần tử tối đa | Ví dụ |
| --- | --- | --- |
| `Mono<Customer>` | 0 hoặc 1 phần tử | Lấy customer theo ID, lưu một document. |
| `Flux<Customer>` | 0 đến nhiều phần tử | Tìm tất cả khách hàng trong một trạng thái. |
| `Mono<Long>` | 0 hoặc 1 giá trị số | Đếm document qua một API phù hợp. |
| `Mono<Boolean>` | 0 hoặc 1 giá trị Boolean | Kiểm tra tồn tại. |
| `Mono<Void>` | Không phát payload; dùng tín hiệu hoàn tất/lỗi | Hoàn tất lệnh xóa hoặc một bước không cần kết quả trả về. |

`Mono.empty()` không phát phần tử và kết thúc bình thường; `Mono.error(error)` kết thúc bằng lỗi; `Mono.just(customer)` phát đúng một phần tử rồi hoàn tất. Theo Reactive Streams, **`null` không phải một phần tử hợp lệ để phát qua `onNext`**. Vì vậy không được diễn giải `Mono.empty()` thành “document tồn tại nhưng một field JSON là null”; nó thường biểu thị **không có entity kết quả** của thao tác đọc.

### 2.2. Ba nhóm tín hiệu

```text
Subscriber                     Publisher
   |-- subscribe ----------------->|
   |<--------- onNext(customer) ---|   (0..N phần tử)
   |<--------- onComplete ---------|   (thành công)
      hoặc
   |<--------- onError(error) -----|   (thất bại)
```

Một publisher kết thúc bằng **`onComplete` hoặc `onError`**, không phải cả hai. Việc huỷ subscription cũng khác với thành công; nó có thể ngừng tiêu thụ kết quả, nhưng không bảo đảm một tác vụ phía server đã được hoàn tác.

### 2.3. Reactive khác đồng bộ ở điểm nào?

| Đồng bộ/imperative | Reactive |
| --- | --- |
| `Customer findById(...)` hoặc `Optional<Customer>` | `Mono<Customer> findById(...)` |
| `List<Customer> findByStatus(...)` | `Flux<Customer> findByStatus(...)` |
| Kết quả được chờ trên luồng gọi theo API blocking | Pipeline biểu diễn công việc bất đồng bộ, phát tín hiệu tới subscriber |
| `try/catch` quanh thao tác đồng bộ | `onErrorResume`, `onErrorMap` hoặc xử lý tại subscriber/controller |
| Có thể dùng `for` trên `List` sau khi tải | Dùng toán tử Reactor để biến đổi, giới hạn và kết hợp các publisher |

Reactive giúp ứng dụng quản lý nhiều thao tác I/O đang chờ mà không giữ một thread chặn cho mỗi thao tác theo mô hình quen thuộc. Tuy nhiên, Couchbase Server vẫn phải đọc document, chạy SQL++, dùng index và truyền dữ liệu; reactive **không xóa chi phí database**.

## 3. Chuẩn bị dependency và cấu hình

Trong ứng dụng Spring Boot sử dụng stack reactive, dự án thường có dependency Spring Data Couchbase reactive và WebFlux khi cần HTTP reactive. Tên starter và phiên bản phải được kiểm tra theo **Spring Boot release/BOM** của chính ứng dụng.

Ví dụ khai báo Gradle **minh họa**:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-couchbase-reactive")
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    testImplementation("io.projectreactor:reactor-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Không nên thêm song song nhiều bộ starter chỉ để “có đủ class”. Nếu dự án dùng Spring MVC/Servlet hoặc có cả reactive và blocking repository, cần xác định kiến trúc thực tế, cách tự động cấu hình, dependency được resolve và cách tránh chặn luồng xử lý reactive.

Thông tin cấu hình cần kiểm tra:

- Endpoint và quyền truy cập cluster; bucket mặc định ứng dụng sử dụng.
- Scope và collection được annotation hoặc template/query options chọn.
- Các converter, type discriminator và cách lưu JSON field.
- Couchbase Java SDK version, cấu hình timeout và resource lifecycle.
- Các secondary index cần cho truy vấn theo field.
- Quy tắc query scan consistency khi vừa ghi rồi tìm theo field.
- Quy tắc ghi TTL/CAS và transaction nếu nghiệp vụ yêu cầu.

**Lưu ý API theo phiên bản:** Các fluent method của `ReactiveCouchbaseTemplate` và cách cấu hình query options có thể khác nhau theo Spring Data Couchbase release. Những ví dụ template bên dưới chỉ rõ ý định và mẫu API phổ biến; trước khi copy vào dự án, cần đối chiếu interface thực tế của phiên bản đang sử dụng.

## 4. Mô hình document dùng trong bài

Giả sử ứng dụng quản lý khách hàng đa tenant trong bucket `app`, scope `crm`, collection `customers`. Một document:

```json
{
  "tenant_id": "tenant-a",
  "customer_code": "C001",
  "display_name": "Lan Anh",
  "status": "ACTIVE",
  "city": "HANOI",
  "loyalty_points": 50
}
```

Couchbase có document ID riêng, chẳng hạn `customer::tenant-a::C001`. ID này không cần là một field `id` trong nội dung JSON.

Entity Java:

```java
package example.crm;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("crm")
@Collection("customers")
public class Customer {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("customer_code")
    private String customerCode;

    @Field("display_name")
    private String displayName;

    @Field
    private String status;

    @Field
    private String city;

    @Field("loyalty_points")
    private Integer loyaltyPoints;

    @Version
    private Long version;

    protected Customer() {
        // Dành cho document mapping.
    }

    // Constructor nghiệp vụ, getters/setters được lược bỏ.
}
```

Ở đây:

| Property Java | JSON/metadata |
| --- | --- |
| `id` | Document ID của Couchbase. |
| `tenantId` | JSON `tenant_id`. |
| `customerCode` | JSON `customer_code`. |
| `displayName` | JSON `display_name`. |
| `status` | JSON `status`. |
| `loyaltyPoints` | JSON `loyalty_points`. |
| `version` với `@Version` | Metadata dùng cho optimistic locking/CAS theo Spring Data Couchbase và phiên bản cấu hình. |

Với `@Version`, cần kiểm thử cách framework ánh xạ phiên bản/CAS và xử lý xung đột thực tế. **Không tự coi field version trong Java là một số thứ tự ghi nghiệp vụ** hoặc giả định nó được lưu thành trường JSON thông thường.

## 5. ReactiveCouchbaseRepository: API theo kiểu repository

Giao diện phổ biến để làm việc với document là:

```java
package example.crm;

import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    Flux<Customer> findByStatus(String status);

    Flux<Customer> findByTenantIdAndStatus(
        String tenantId,
        String status
    );

    Flux<Customer> findByTenantIdAndCity(
        String tenantId,
        String city
    );
}
```

`ReactiveCouchbaseRepository<Customer, String>` thể hiện entity type `Customer` và ID type `String`. Nó cung cấp các thao tác reactive kế thừa cho CRUD và cho phép khai báo một số truy vấn dẫn xuất.

Các API sử dụng thông thường:

```java
Mono<Customer> byId = repository.findById("customer::tenant-a::C001");

Flux<Customer> active = repository.findByTenantIdAndStatus(
    "tenant-a",
    "ACTIVE"
);

Mono<Long> total = repository.count();

Mono<Boolean> exists =
    repository.existsById("customer::tenant-a::C001");

Mono<Customer> saved = repository.save(customer);

Mono<Void> deleted =
    repository.deleteById("customer::tenant-a::C001");
```

Đoạn mã minh họa cách sử dụng **một đối tượng `repository` đã được inject**, không phải Java file độc lập. Các thao tác do repository kế thừa cần được kiểm tra chính xác theo API của phiên bản đang dùng.

### 5.1. Reactive CRUD và derived query khác đường truy cập

`findById(id)` thường đọc qua **key-value** theo document ID; `findByTenantIdAndStatus(...)` thường được Spring Data Couchbase chuyển thành **SQL++** trên các field JSON. Vì vậy chúng có đặc điểm khác nhau về index và consistency:

```text
findById(id)                      -> đọc theo key-value document ID
findByTenantIdAndStatus(...)      -> SQL++ truy vấn field qua Query Service
```

`findAll()` cũng cần được đánh giá theo cách backend thực hiện; với collection lớn không nên gọi chỉ để tạo một danh sách UI, dù kết quả là `Flux`.

### 5.2. Derived query vẫn phụ thuộc phiên bản

Tên `findByTenantIdAndStatus` là dạng đơn giản và dễ hiểu. Với keyword nâng cao như `ContainingIgnoreCase`, `Between`, `TopN`, `IsNull`, `deleteBy` hoặc nested array, cần xác minh Spring Data Couchbase phiên bản đang sử dụng hỗ trợ đúng cú pháp và ngữ nghĩa.

**Đặc biệt:** parser tên phương thức của Spring Data Commons có thể hiểu một keyword trong khi Couchbase query creator không triển khai đầy đủ. Reactive không tự bổ sung hỗ trợ cho keyword chỉ vì publisher trả `Flux`.

### 5.3. Không lấy `findById` làm kiểm tra tenant

Document ID của khách hàng có thể chứa mã tenant, nhưng chỉ dựa vào cấu trúc chuỗi ID từ request không đủ để áp dụng phân quyền. Khi có yêu cầu đa tenant, service phải kiểm tra quyền và đối chiếu tenant của document sau đọc hoặc chọn một API có ràng buộc tenant tường minh. Không để một endpoint `findById(id)` trở thành đường truy cập chéo tenant.

## 6. Tạo pipeline reactive đúng cách

Một service nhận repository qua constructor injection:

```java
package example.crm;

import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CustomerService {

    private final ReactiveCustomerRepository repository;

    public CustomerService(ReactiveCustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> getRequired(String id) {
        return repository.findById(id)
            .switchIfEmpty(Mono.error(
                new NoSuchElementException("Customer not found: " + id)
            ));
    }

    public Flux<Customer> activeForTenant(String tenantId) {
        return repository.findByTenantIdAndStatus(
            tenantId,
            "ACTIVE"
        );
    }

    public Mono<Customer> save(Customer customer) {
        return repository.save(customer);
    }
}
```

Đây là mô hình **compose rồi return**, không tự subscribe. Tầng nhận publisher (ví dụ Spring WebFlux controller hoặc một tác vụ có subscription được quản lý) chịu trách nhiệm tiêu thụ nó.

### 6.1. `map`, `flatMap` và `then`

Dùng `map` khi biến đổi đồng bộ một giá trị đã phát:

```java
Mono<String> label = repository.findById(id)
    .map(customer -> customer.toString());
```

Trong ví dụ, `toString()` chỉ minh họa phép biến đổi; với hệ thống thực tế nên ánh xạ sang DTO hiển thị, tránh vô tình làm lộ toàn bộ field.

Dùng `flatMap` khi bước tiếp theo trả một `Mono` khác:

```java
Mono<Customer> updated = repository.findById(id)
    .switchIfEmpty(Mono.error(
        new NoSuchElementException("Customer not found")
    ))
    .flatMap(customer -> repository.save(customer));
```

Đoạn `save` trên cố tình lược bỏ thay đổi nghiệp vụ; khi triển khai, cần chỉnh property mong muốn và kiểm soát CAS trước khi ghi.

Dùng `then` khi quan tâm thao tác hoàn tất chứ không cần payload trước đó:

```java
Mono<Void> done = repository.deleteById(id)
    .then();
```

`then()` không biến lỗi thành thành công; lỗi vẫn đi xuống pipeline nếu không bị một operator khác nuốt mất.

### 6.2. Không gọi `subscribe()` bên trong service

Anti-pattern:

```java
public void saveAndForget(Customer customer) {
    repository.save(customer).subscribe();
}
```

Vấn đề:

- Service trả `void` trước khi biết thao tác ghi thành công hay thất bại.
- Lỗi có thể bị bỏ qua hoặc khó liên hệ với request.
- Không còn kiểm soát luồng huỷ, timeout và transaction context từ tầng gọi.
- Khó kiểm thử outcome và thực hiện retry có chủ đích.

Cách thích hợp:

```java
public Mono<Customer> saveCustomer(Customer customer) {
    return repository.save(customer);
}
```

Để framework hoặc một thành phần điều phối job có lifecycle rõ ràng quản lý subscription.

### 6.3. Tránh `block()` trong WebFlux

Anti-pattern:

```java
Customer c = repository.findById(id).block();
```

`block()` chặn luồng hiện tại cho tới khi publisher kết thúc; trong đường xử lý request WebFlux, nó có thể làm mất lợi ích non-blocking và gây lỗi nếu chạy trên event-loop thread không cho phép blocking.

Trong **test hoặc bước tích hợp biên** được kiểm soát, blocking có thể được sử dụng có cân nhắc, nhưng trong request reactive end-to-end nên truyền `Mono`/`Flux` đến controller hoặc tầng gọi tiếp theo.

## 7. ReactiveCouchbaseTemplate: API linh hoạt hơn repository

`ReactiveCouchbaseTemplate` là công cụ Spring Data Couchbase cho các thao tác reactive theo mô hình template. Interface `ReactiveCouchbaseOperations` (khi được phiên bản sử dụng cung cấp) có thể được dùng để giảm phụ thuộc trực tiếp vào implementation.

Template hữu ích khi:

- Không muốn tạo một repository method riêng cho nhiều tổ hợp điều kiện.
- Muốn sử dụng **fluent API** cho thao tác theo ID, truy vấn theo criteria hoặc thay đổi dạng dữ liệu trả về.
- Cần phối hợp query options, mapping và biểu thức truy vấn linh hoạt hơn một tên derived query.
- Cần định nghĩa ranh giới cụ thể giữa truy vấn theo field và thao tác key-value.
- Muốn giữ các truy vấn SQL++ phức tạp trong một lớp truy cập dữ liệu có thể kiểm thử.

### 7.1. Hai ví dụ thao tác theo ID với template

Mẫu fluent API của các phiên bản Spring Data Couchbase hỗ trợ những cách gọi gần dạng sau:

```java
import org.springframework.data.couchbase.core.ReactiveCouchbaseTemplate;
import reactor.core.publisher.Mono;

public class CustomerTemplateReader {

    private final ReactiveCouchbaseTemplate template;

    public CustomerTemplateReader(ReactiveCouchbaseTemplate template) {
        this.template = template;
    }

    public Mono<Customer> getById(String id) {
        return template.findById(Customer.class).one(id);
    }
}
```

API chính xác và signature của `findById(...).one(...)` phải được đối chiếu với **Spring Data Couchbase phiên bản dự án**. Mục tiêu của ví dụ là cho thấy template vẫn trả một publisher chứ không tự tải dữ liệu đồng bộ.

Các thao tác ghi theo ID có thể được trình bày trong cùng phong cách fluent:

```java
// Mẫu API minh họa; kiểm tra release đang chạy.
Mono<Customer> inserted =
    template.insertById(Customer.class).one(newCustomer);

Mono<Customer> upserted =
    template.upsertById(Customer.class).one(existingCustomer);
```

Hai lời gọi trên **không đồng nghĩa** về chính sách dữ liệu:

- **Insert** có ý định chỉ tạo document mới; khi ID đã tồn tại, API phù hợp phải báo xung đột.
- **Upsert** có ý định tạo nếu chưa có hoặc cập nhật nếu có; không phù hợp làm cơ chế uniqueness khi nghiệp vụ cần chặn ghi đè.

Khi thao tác với document nhạy cảm, cần xác định rõ insert-only, replace/update có CAS và các điều kiện nghiệp vụ. Không dùng upsert tùy tiện chỉ vì code ngắn.

### 7.2. Truy vấn qua template

Một mẫu truy vấn theo property dùng criteria trong những phiên bản hỗ trợ fluent query:

```java
import org.springframework.data.couchbase.core.ReactiveCouchbaseTemplate;
import org.springframework.data.couchbase.core.query.Criteria;
import org.springframework.data.couchbase.core.query.Query;
import reactor.core.publisher.Flux;

public class CustomerTemplateSearch {

    private final ReactiveCouchbaseTemplate template;

    public CustomerTemplateSearch(ReactiveCouchbaseTemplate template) {
        this.template = template;
    }

    public Flux<Customer> byStatus(String status) {
        Query query = Query.query(
            Criteria.where("status").is(status)
        );

        return template.findByQuery(Customer.class)
            .matching(query)
            .all();
    }
}
```

Ví dụ trên thể hiện một mẫu API thông dụng; **kiểm tra import, fluent method và cách mapping tên property theo bản Spring Data Couchbase thực tế** trước khi biên dịch. Một số release có biến thể cấu hình hoặc đặt query options khác nhau.

Cách sử dụng template và repository có thể tạo cùng ý định `status = ?`, nhưng không được giả định **SQL++ sinh ra giống hệt** về projection, discriminator, index hints hoặc consistency. Hãy kiểm tra query thực tế và kết quả integration test.

## 8. Repository hay template: chọn theo bài toán

| Tình huống | Ưu tiên xem xét | Lý do |
| --- | --- | --- |
| CRUD theo document ID | `ReactiveCouchbaseRepository` | API ngắn, hợp đồng rõ. |
| Truy vấn đơn giản theo vài field cố định | Repository derived query | Giảm SQL++/boilerplate. |
| Một vài truy vấn ổn định cần `@Query` | Repository với method tường minh | Tập trung contract của use case. |
| Nhiều bộ lọc tùy chọn theo request | `ReactiveCouchbaseTemplate`/query builder | Dễ kiểm soát cấu trúc predicate động. |
| Thao tác by-ID với lựa chọn insert/upsert/replace rõ | Template hoặc SDK KV API | Phân biệt semantics mutation và CAS. |
| Truy vấn SQL++ có `ANY`, `UNNEST`, projection, aggregate | Template/query API hoặc `@Query` phù hợp | Tránh tên method quá dài và sai nhóm. |
| FTS, truy vấn SDK đặc thù hoặc diagnostics chuyên sâu | API phù hợp của Couchbase SDK | Dùng đúng engine và options cần thiết. |
| Nghiệp vụ nhiều document cần transaction | Transaction API tương thích với SDK/Spring Data | Reactive API đơn thuần không tự cấp atomicity. |

Không nhất thiết phải chọn **chỉ một**. Repository có thể xử lý CRUD chuẩn, còn một thành phần đọc chuyên biệt dùng template cho truy vấn nghiệp vụ phức tạp. Tuy nhiên, tránh tạo hai cách truy vấn trùng nghĩa nhưng trả kết quả khác nhau do mapping, consistency hoặc tenant scope.

### 8.1. Không dùng template để bỏ qua chính sách tenant

Nếu repository đã có `findByTenantIdAndStatus`, khi viết lại bằng template phải **giữ điều kiện tenant từ context xác thực**. Một câu query chỉ lọc `status` có thể trả document của mọi tenant. Bảo mật không được dựa vào việc người gọi “thường sẽ tự nhớ thêm điều kiện”.

## 9. SQL++ của Couchbase trong luồng reactive

Giả sử repository có:

```java
Flux<Customer> findByTenantIdAndStatus(
    String tenantId,
    String status
);
```

Logic SQL++ minh họa:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`tenant_id` = $tenantId
  AND c.`status` = $status;
```

Đây là **ý định** chứ không phải nguyên văn query được Spring Data Couchbase gửi. Thư viện có thể thêm metadata ID/CAS, discriminator và placeholders theo phiên bản.

Cần phân biệt:

| Thao tác | Đường backend điển hình | Yêu cầu thường gặp |
| --- | --- | --- |
| `findById(id)` | Key-value theo ID | ID đúng, quyền đọc, consistency của KV. |
| `findByTenantIdAndStatus(...)` | SQL++ Query Service | Secondary index, binding, query scan consistency. |
| Template query theo `Criteria` | SQL++ theo fluent API | Index, projection/mapping, tập điều kiện đúng. |
| Lấy theo mảng và điều kiện tổng hợp | SQL++/FTS/API thích hợp | Index phù hợp và ngữ nghĩa dữ liệu phức tạp. |

Truy cập reactive **không có nghĩa mọi phép đọc đều qua cùng một API Couchbase**. Lỗi `findById` thấy document nhưng truy vấn theo status không thấy ngay có thể đến từ **độ trễ cập nhật index**, không phải vì Reactor đã bỏ một phần tử.

### 9.1. Index minh họa

Giả sử ứng dụng có điều kiện type discriminator qua `_class`, một index có thể cân nhắc:

```sql
CREATE INDEX ix_customer_type_tenant_status
ON `app`.`crm`.`customers` (
    `_class`,
    `tenant_id`,
    `status`
);
```

Index này chỉ minh họa: Spring Data có thể dùng discriminator khác hoặc cấu hình không giống `_class`. Phải lấy SQL++ thực tế, kiểm tra index, phân bố dữ liệu và `EXPLAIN` trước khi áp dụng.

```sql
EXPLAIN
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`tenant_id` = "tenant-a"
  AND c.`status` = "ACTIVE";
```

Ngay cả khi backend trả `Flux`, server vẫn phải scan/fetch các document. Hãy kiểm tra index được chọn, số phần tử quét và lượng dữ liệu truyền, không chỉ đo thời gian subscription ở Java.

## 10. Kết quả rỗng và lỗi: thiết kế hợp đồng rõ ràng

### 10.1. Không có document là hoàn tất rỗng

Với thao tác:

```java
Mono<Customer> result = repository.findById(id);
```

Nếu ID không tồn tại, hành vi phổ biến là `Mono.empty()` chứ không phải phát ra `null`. Ở tầng API có thể chuyển tình huống này thành một lỗi nghiệp vụ hoặc HTTP 404.

```java
import java.util.NoSuchElementException;
import reactor.core.publisher.Mono;

Mono<Customer> required = repository.findById(id)
    .switchIfEmpty(Mono.error(
        new NoSuchElementException("Không tìm thấy customer")
    ));
```

Không sử dụng `defaultIfEmpty(null)`: Reactive Streams không cho phép phát giá trị `null`.

### 10.2. Lỗi database không phải “không có dữ liệu”

Anti-pattern:

```java
// Nguy hiểm: che cả lỗi query/index/network thành danh sách rỗng.
Flux<Customer> customers = repository
    .findByTenantIdAndStatus(tenantId, "ACTIVE")
    .onErrorResume(error -> Flux.empty());
```

Nó khiến UI thấy “không có khách hàng” dù Couchbase có thể bị timeout hoặc lỗi index.

Thay vào đó, phân loại lỗi dựa trên khả năng phục hồi thực tế, log/metric có kiểm soát và trả lỗi phù hợp:

```java
Flux<Customer> customers = repository
    .findByTenantIdAndStatus(tenantId, "ACTIVE")
    .doOnError(error -> metricsRecorder.recordQueryFailure(error));
```

`metricsRecorder` là **đối tượng minh họa cần được ứng dụng triển khai**, không phải API có sẵn của Spring Data Couchbase. `doOnError` chỉ quan sát lỗi, không “nuốt” lỗi hoặc thay thế chính sách phục hồi.

### 10.3. Retry không phải lúc nào cũng an toàn

Với truy vấn đọc idempotent, retry có thể chấp nhận được nếu giới hạn số lần, thời gian và phân loại lỗi tạm thời. Với **ghi/xóa**, retry mù quáng có thể dẫn tới ghi lặp, xung đột CAS hoặc xử lý nghiệp vụ hai lần nếu thao tác trước đã hoàn tất ở server nhưng phản hồi bị mất.

Một quy tắc an toàn: chỉ retry theo cơ chế mà operation/SDK phiên bản cho phép, có **idempotency** hoặc điều kiện xác nhận trạng thái cuối cùng. Không gắn `retry()` vô hạn vào mọi publisher.

## 11. Kết hợp thao tác và xử lý đồng thời

### 11.1. `map` không dùng cho lời gọi reactive bên trong

Không nên viết:

```java
Mono<Mono<Customer>> nested = repository.findById(id)
    .map(customer -> repository.save(customer));
```

Mã trên tạo **publisher lồng publisher**, không phải một luồng trả `Mono<Customer>` của save được phối hợp tự động.

Dùng `flatMap` khi callback trả publisher:

```java
Mono<Customer> saved = repository.findById(id)
    .flatMap(customer -> repository.save(customer));
```

Ví dụ bỏ qua bước thay đổi nghiệp vụ, nhằm minh họa hình dạng kiểu. Khi sửa thông tin thật, cần xử lý optimistic locking/version.

### 11.2. `flatMap` có thể chạy nhiều công việc đồng thời

Giả sử một luồng ID cần đọc nhiều document:

```java
Flux<String> ids = Flux.just(
    "customer::tenant-a::C001",
    "customer::tenant-a::C002",
    "customer::tenant-a::C003"
);

Flux<Customer> customers = ids.flatMap(
    repository::findById,
    4 // Giới hạn số inner publisher đang xử lý đồng thời.
);
```

`flatMap` có thể **thay đổi thứ tự phát kết quả** so với thứ tự ID đầu vào. Nếu cần giữ thứ tự, cân nhắc `concatMap` hoặc `flatMapSequential` và kiểm tra trade-off hiệu năng.

Giới hạn concurrency phải xuất phát từ tải Couchbase, giới hạn kết nối, tài nguyên ứng dụng và mục tiêu độ trễ. Không tự đặt concurrency vài trăm cho một job ghi hàng loạt rồi cho rằng reactive sẽ làm server chịu tải tốt hơn.

### 11.3. Không viết quy trình read-modify-save thiếu xử lý cạnh tranh

```java
Mono<Customer> changed = repository.findById(id)
    .flatMap(customer -> {
        // Cập nhật property nghiệp vụ ở đây.
        return repository.save(customer);
    });
```

Hai request có thể cùng đọc một document, cùng thay đổi rồi cùng save. Nếu cần bảo vệ khỏi lost update, sử dụng `@Version`/CAS và xử lý xung đột phù hợp với Spring Data Couchbase/SDK. Một pipeline reactive liên tiếp chỉ xác định **thứ tự trong pipeline của chính request**, không tự khóa document trước request khác.

## 12. Backpressure và giới hạn kết quả

**Backpressure** cho phép subscriber điều tiết nhu cầu nhận phần tử, nhưng phải hiểu rằng các tầng bên dưới có thể có buffering, network và kế hoạch thực thi riêng. `Flux` không đảm bảo Query Service chỉ đọc đúng số document mà subscriber vừa yêu cầu.

Ví dụ:

```java
Flux<Customer> preview = repository
    .findByTenantIdAndStatus("tenant-a", "ACTIVE")
    .take(10);
```

`take(10)` giới hạn số phần tử **phát tới subscriber** trong pipeline. Nó **không chứng minh** SQL++ có `LIMIT 10` hoặc index chỉ scan đúng 10 document. Nếu backend đã chạy truy vấn trả nhiều bản ghi, ứng dụng vẫn có thể chịu chi phí đáng kể trước khi huỷ.

Để tối ưu cả database, nên:

1. Định nghĩa **điều kiện lọc đủ chọn lọc**.
2. Yêu cầu **giới hạn ở phía query** bằng API được phiên bản hỗ trợ.
3. Dùng `ORDER BY` có khóa phụ xác định nếu chọn “10 bản ghi đầu”.
4. Kiểm tra index và `EXPLAIN`.
5. Chỉ sau đó dùng `Flux` để tiêu thụ kết quả phù hợp.

### 12.1. `TopN` và `Pageable` trên repository reactive

Có thể thử một chữ ký derived query mang ý định giới hạn:

```java
// Kiểm tra hỗ trợ keyword TopN ở bản Spring Data Couchbase thực tế.
Flux<Customer> findTop10ByTenantIdAndStatusOrderByCustomerCodeAsc(
    String tenantId,
    String status
);
```

Dạng nhận `Pageable` cũng có thể được xem xét theo API được phiên bản cung cấp:

```java
// Kiểm tra hỗ trợ tham số Pageable trong repository reactive.
Flux<Customer> findByTenantIdAndStatus(
    String tenantId,
    String status,
    org.springframework.data.domain.Pageable pageable
);
```

Không mặc định `Mono<Page<Customer>>` là một kiểu trả về derived query reactive được hỗ trợ giống repository imperative. Trong nhiều mô hình reactive, tổng số kết quả được lấy bằng một publisher đếm **riêng** nếu ứng dụng cần tổng số.

### 12.2. Tránh phân trang không có thứ tự

SQL++ không cam kết thứ tự document nếu không có `ORDER BY`. Với phân trang offset, nên dùng sort có khóa phụ xác định; với tập dữ liệu rất lớn, cân nhắc keyset/cursor theo khả năng API.

Reactive không tạo snapshot bất biến giữa hai request. Document có thể được thêm, xóa, cập nhật hoặc hết TTL giữa các lần lấy trang.

## 13. SQL++ scan consistency và dữ liệu vừa ghi

Trường hợp dễ gây nhầm:

```text
repository.save(customer)       -> complete thành công
repository.findById(id)         -> có thể thấy document theo key-value
repository.findByStatus(...)    -> SQL++/index có thể chưa thấy ngay
```

Couchbase cập nhật index phục vụ truy vấn theo field qua một đường xử lý khác với KV. Với query scan consistency không đợi các mutation mới nhất, kết quả SQL++ có thể chưa phản ánh thay đổi vừa ghi.

Một pipeline:

```java
Mono<Customer> savedThenRead = repository.save(customer)
    .flatMap(saved -> repository.findById(saved.getId()));
```

có thứ tự **save hoàn tất rồi mới đọc bằng ID**. Nhưng nếu thay `findById` bằng `findByStatus`, việc nối bằng `flatMap` **không tự buộc index chờ cập nhật**.

Khi nghiệp vụ cần read-your-own-write qua query, đánh giá scan consistency phù hợp, ví dụ mức tương đương `REQUEST_PLUS` nếu phiên bản SDK/Spring Data hỗ trợ. Mức nhất quán mạnh hơn có thể làm tăng thời gian chờ; lựa chọn phải dựa trên yêu cầu thực tế, không chỉ để test “dễ pass”.

### 13.1. Cần phân biệt ba nguồn kết quả thay đổi

- **Index lag:** document đã ghi nhưng SQL++ chưa thấy ở mức consistency đang dùng.
- **TTL:** document đã hết hạn, nên có thể không còn tồn tại.
- **Đồng thời:** document bị update/delete trong lúc pipeline chạy.

Không có một toán tử Reactor nào tự sửa cả ba vấn đề này. Cần kiểm tra JSON, query options, mutation outcome và thời điểm thực thi.

## 14. TTL, CAS và transaction trong reactive

### 14.1. TTL/expiration

TTL là thuộc tính vòng đời document ở Couchbase. Một customer hết hạn có thể khiến `findById` hoặc query theo field hoàn tất rỗng ngay cả khi logic Java không đổi.

Khi create/update document bằng template hoặc repository, phải kiểm tra cách cấu hình expiration của entity, bucket/collection và SDK theo phiên bản. Không giả định `save` sẽ tự giữ nguyên TTL trong mọi loại ghi; chính sách expiration cần được kiểm thử riêng trong đường mutation đang dùng.

### 14.2. CAS và optimistic locking

Couchbase dùng **CAS** để phát hiện document đã bị sửa giữa hai thời điểm. Spring Data Couchbase có thể ánh xạ optimistic locking qua `@Version` như trong entity ví dụ.

Nếu hai subscriber đọc cùng một `Customer` và cùng thực hiện update:

```text
A: read version V1
B: read version V1
A: save -> thành công, version thay đổi
B: save với version cũ -> có thể bị từ chối do xung đột
```

Cần xác minh cơ chế optimistic locking và exception chính xác trên phiên bản ứng dụng. Không retry xung đột bằng cách gửi lại object cũ vô hạn; hãy quyết định nghiệp vụ có cho phép đọc lại và áp dụng thay đổi một lần nữa hay không.

### 14.3. Transaction reactive

Một pipeline `repository.findById(id).flatMap(repository::save)` **không tự tạo transaction**. Tương tự, `zip`, `then` hoặc `concatMap` là toán tử phối hợp publisher, không tự bảo đảm tính nguyên tử của các mutation trên Couchbase.

Nếu nghiệp vụ cần thay đổi nguyên tử nhiều document, phải dùng transaction API mà **Couchbase SDK và Spring Data Couchbase đúng phiên bản** hỗ trợ trong ngữ cảnh reactive, với giới hạn về thời gian, kích thước và thao tác được phép. Không tự gắn `@Transactional` rồi giả định mọi publisher và DML đều tham gia cùng một transaction.

## 15. Thiết kế WebFlux controller không chặn

Nếu dùng Spring WebFlux, controller có thể trả thẳng publisher:

```java
package example.crm;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final ReactiveCustomerRepository repository;

    public CustomerController(ReactiveCustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Customer>> getById(
            @PathVariable String id) {

        return repository.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

Ví dụ chỉ minh họa chuỗi publisher và HTTP 404. Trong hệ thống thật:

- Phải áp dụng xác thực/phân quyền tenant, không cho ID bất kỳ truy cập chéo tenant.
- Không trả nguyên entity chứa trường nội bộ hoặc CAS/version nếu API chỉ cần một số field.
- Chuyển lỗi Couchbase thành HTTP response theo chính sách, không che lỗi hệ thống thành 404.
- Thêm timeout và giới hạn tải phù hợp, có quan sát request ID/trace.

Controller không cần `subscribe()` hay `block()` để “kích hoạt query”; WebFlux quản lý subscription khi trả response.

## 16. Kiểm thử với StepVerifier

Project Reactor cung cấp `StepVerifier` để kiểm tra các tín hiệu mà publisher phát. Với reactive repository, test không chỉ cần kiểm tra một Java object, mà còn phải xác minh **publisher hoàn tất hay báo lỗi**.

Ví dụ giả định một customer đã được seed với ID xác định:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveCustomerRepositoryIT {

    @Autowired
    ReactiveCustomerRepository repository;

    @Test
    void findExistingCustomerEmitsOneAndCompletes() {
        StepVerifier.create(
                repository.findById("customer::tenant-a::C001")
            )
            .assertNext(customer -> assertThat(customer.getId())
                .isEqualTo("customer::tenant-a::C001"))
            .verifyComplete();
    }

    @Test
    void findMissingCustomerCompletesEmpty() {
        StepVerifier.create(
                repository.findById("customer::tenant-a::MISSING")
            )
            .verifyComplete();
    }
}
```

Ví dụ này là **khung integration test**, không phải test tự chạy được nếu chưa có test cluster, index, seed/cleanup fixture và cấu hình Spring Boot phù hợp. Phải dùng collection test riêng, không ghi/xóa dữ liệu sản xuất.

### 16.1. Test lỗi và mutation outcome

Ví dụ kiểm tra publisher phát lỗi:

```java
StepVerifier.create(
        Mono.<Customer>error(
            new IllegalStateException("simulated failure")
        )
    )
    .expectError(IllegalStateException.class)
    .verify();
```

Đây là test Reactor **thuần** minh họa cách bắt lỗi, không chứng minh Couchbase sẽ trả `IllegalStateException` trong một tình huống cụ thể. Với lỗi database thật, assert loại exception đã quan sát được từ phiên bản SDK/mapper đang dùng.

Với save/delete, phải test document trước/sau thao tác, kiểm tra ID và CAS khi cần. Không kết luận “đã lưu” chỉ vì đã tạo `Mono<Customer>` mà chưa có subscription hoặc kết quả hoàn tất.

### 16.2. Test sau khi seed dữ liệu phải xét consistency

Nếu test seed qua key-value và ngay sau đó gọi derived query SQL++, có thể gặp tình huống index chưa cập nhật. Nên dùng scan consistency hoặc cơ chế chờ có điều kiện và timeout phù hợp, thay vì ngủ một khoảng thời gian cố định rồi hy vọng query nhìn thấy dữ liệu.

Bộ test tối thiểu nên bao phủ:

| Trường hợp | Assertion |
| --- | --- |
| ID tồn tại | `Mono` phát một entity đúng và hoàn tất. |
| ID không tồn tại | `Mono` hoàn tất rỗng theo hợp đồng. |
| Query không có kết quả | `Flux` hoàn tất mà không phát entity. |
| Query có nhiều kết quả | Đúng tập ID, không dựa vào thứ tự khi thiếu `Sort`. |
| Query có `Sort`/limit | Đúng thứ tự và giới hạn ở phía query theo bằng chứng SQL++. |
| Giá trị field `NULL`/`MISSING` | Không lẫn trạng thái JSON với publisher empty. |
| Lỗi index/timeout | Publisher phát lỗi, không bị biến thành danh sách rỗng. |
| Ghi đồng thời | Optimistic locking/CAS xử lý xung đột như hợp đồng. |
| Document TTL | Hành vi khi hết hạn được kiểm tra rõ. |
| Hủy subscription | Tài nguyên được giải phóng theo API/SDK, không suy ra xóa/giao dịch rollback. |

## 17. Quan sát và xử lý lỗi khi vận hành

Một hệ thống reactive cần quan sát **cả phía Java lẫn phía Couchbase**:

- Request/trace ID và tên use case.
- Thời gian từ subscription đến response; phân biệt thời gian chờ network, Query Service và mapping.
- Loại thao tác: KV read/write hay SQL++ query.
- Số document được phát, giới hạn kết quả, thời gian hoàn tất.
- Tỉ lệ timeout, lỗi index, xung đột CAS, retry và cancellation.
- Scan consistency và query options khi cần chẩn đoán.
- Tài nguyên ứng dụng: event-loop threads, bộ nhớ/buffering và concurrency.
- Query plan và secondary index trên dữ liệu đại diện.

**Tránh log dữ liệu nhạy cảm:** Không in toàn bộ customer document, token, password hoặc query bind values chứa thông tin cá nhân lên log mặc định. Dùng test fixtures và redaction.

### 17.1. Một số lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| `Mono` không “chạy” | Chưa có subscription, hoặc pipeline không được return/consume. |
| Endpoint treo hoặc throughput thấp | Có `block()`/thao tác blocking trên event loop; database/index chậm. |
| `Flux` trả ít hơn mong đợi | `take`/filter trong pipeline, query `LIMIT`, NULL/MISSING, index lag. |
| `findById` thấy document nhưng `findByStatus` không thấy | Khác đường KV và SQL++, scan consistency, discriminator hoặc index. |
| Lỗi `No index` hay query timeout | Thiếu/chọn sai secondary index, query scan lớn, timeout. |
| Lỗi lưu/xóa sau khi đọc | CAS conflict, document hết hạn hoặc bị request khác sửa/xóa. |
| Trả rỗng khi database lỗi | `onErrorResume(... -> Flux.empty())` che mất lỗi. |
| Trả dữ liệu của tenant khác | Filter/query template thiếu điều kiện tenant hoặc phân quyền. |
| Tốn RAM dù dùng `Flux` | Pipeline buffer/collect quá nhiều, downstream chậm hoặc backend đã trả lượng lớn. |
| Lệnh ghi chạy hai lần | Nhiều subscription, `retry` hoặc xử lý phụ thuộc lifecycle sai. |

### 17.2. `collectList()` làm mất lợi ích streaming nếu tập quá lớn

```java
Mono<java.util.List<Customer>> all = repository
    .findByTenantIdAndStatus("tenant-a", "ACTIVE")
    .collectList();
```

`collectList()` thu **toàn bộ phần tử** của publisher vào một danh sách trước khi phát ra `Mono<List<Customer>>`. Với dữ liệu lớn, điều này có thể tiêu tốn bộ nhớ tương tự việc nhận một danh sách không giới hạn trong API đồng bộ.

Chỉ dùng khi tập dữ liệu được giới hạn/chọn lọc rõ; với UI phân trang, nên đặt giới hạn ở Query Service. Reactive không mặc nhiên có nghĩa sử dụng bộ nhớ hằng số.

## 18. Tình huống thực hành: danh sách khách hàng ACTIVE

Yêu cầu:

> Endpoint trả tối đa 20 khách hàng ACTIVE của tenant đã xác thực, sắp mã khách hàng tăng dần, không chặn thread và không làm lộ dữ liệu tenant khác.

### Bước 1 — Chốt bộ lọc và thứ tự

```text
WHERE tenant_id = authenticatedTenant
  AND status = "ACTIVE"
ORDER BY customer_code ASC
LIMIT 20
```

Tenant phải lấy từ context xác thực phía server. `customer_code` cần có giá trị và quy tắc sắp xếp ổn định; nếu mã có thể trùng, bổ sung khóa phụ duy nhất.

### Bước 2 — Chọn API

Nếu phiên bản Spring Data Couchbase hỗ trợ derived query `Top20` và mapping đúng, có thể kiểm thử phương thức:

```java
Flux<Customer> findTop20ByTenantIdAndStatusOrderByCustomerCodeAsc(
    String tenantId,
    String status
);
```

Nếu bộ lọc/tính năng phân trang thay đổi động hoặc keyword không hỗ trợ theo ý định, dùng template/query API với SQL++/criteria và query limit có xác minh.

### Bước 3 — Kiểm tra index

Một index định hướng cho bộ lọc tenant/status và sort mã:

```sql
CREATE INDEX ix_customers_tenant_status_code
ON `app`.`crm`.`customers` (
    `tenant_id`,
    `status`,
    `customer_code`
);
```

Nếu query do Spring Data sinh thêm discriminator, index cần được đánh giá theo predicate thực tế. Chạy `EXPLAIN` để xác nhận index được chọn, scan/sort/limit phù hợp. Không sao chép index theo ví dụ mà chưa xem workload, loại dữ liệu và bản Server.

### Bước 4 — Viết service chỉ compose publisher

```java
public Flux<Customer> firstActiveCustomers(String tenantId) {
    return repository
        .findTop20ByTenantIdAndStatusOrderByCustomerCodeAsc(
            tenantId,
            "ACTIVE"
        );
}
```

Không gọi `block()`, `subscribe()` hoặc `collectList()` một cách mặc định trong service.

### Bước 5 — Kiểm thử

Tạo fixture có hai tenant và nhiều status:

| ID | Tenant | Status | Customer code | Có được trả? |
| --- | --- | --- | --- | :---: |
| `c01` | tenant-a | ACTIVE | C001 | ✓ |
| `c02` | tenant-a | SUSPENDED | C002 | ✗ |
| `c03` | tenant-b | ACTIVE | C003 | ✗ |
| `c04` | tenant-a | ACTIVE | C004 | ✓ |
| `c05` | tenant-a | ACTIVE | C005 | ✓ |

Kiểm tra `Flux` chỉ trả `c01, c04, c05` theo đúng thứ tự mã, rồi hoàn tất. Sau đó thêm hơn 20 document đủ điều kiện để chứng minh **giới hạn không vượt 20** và query thực sự có limit ở phía Couchbase. Tạo dữ liệu null/missing và timestamp/TTL nếu nghiệp vụ có thể gặp những trạng thái đó.

## 19. Bài tập tự kiểm tra

### Bài A — Repository hay template?

Một màn hình có hai bộ lọc cố định `tenantId` và `status`. Bạn chọn API nào trước?

**Gợi ý:** Bắt đầu từ `ReactiveCouchbaseRepository` với method đơn giản nếu keyword hỗ trợ và index phù hợp. Không cần template chỉ vì ứng dụng đang dùng reactive.

### Bài B — Nhiều điều kiện tùy chọn

Màn hình báo cáo có các bộ lọc thành phố, ngưỡng điểm, khoảng thời gian, danh sách status và sắp xếp do người dùng chọn. Tạo hàng chục method tên dài có tốt không?

**Gợi ý:** Cân nhắc `ReactiveCouchbaseTemplate`/query builder để dựng predicate rõ ràng. Bảo đảm ràng buộc tenant, bind tham số, whitelist sort và giới hạn size.

### Bài C — Publisher rỗng

`repository.findById(id)` hoàn tất mà không phát phần tử. Có thể khẳng định document tồn tại nhưng field `city` là JSON null không?

**Đáp án:** Không. Publisher rỗng thường biểu thị **không có entity kết quả**; trạng thái một field null/missing là vấn đề khác.

### Bài D — `take(10)`

Một `Flux` do SQL++ trả hàng nghìn document được nối `take(10)`. Có chắc Couchbase chỉ quét 10 document?

**Đáp án:** Không. `take` giới hạn phần tử tới subscriber; cần SQL++ `LIMIT` và index phù hợp để giảm tải phía server.

### Bài E — Ghi rồi tìm

`save(customer)` hoàn tất, `findById` thấy document, nhưng `findByStatus` chưa thấy. Có phải Reactor bị mất sự kiện không?

**Đáp án:** Chưa đủ bằng chứng. Kiểm tra namespace/discriminator và mức query scan consistency/index cập nhật. Hai thao tác thường dùng đường KV và SQL++ khác nhau.

### Bài F — Hai request cùng sửa

Hai subscriber cùng đọc một customer rồi cập nhật điểm. Vì sao `flatMap` không đủ ngăn lost update?

**Đáp án:** `flatMap` tổ chức thứ tự thao tác trong mỗi pipeline, không khóa document giữa các request. Cần CAS/optimistic locking, xử lý xung đột và quyết định retry theo nghiệp vụ.

### Bài G — Nuốt lỗi

Vì sao `onErrorResume(e -> Flux.empty())` có thể nguy hiểm trong API tìm khách hàng?

**Đáp án:** Nó biến lỗi database thành tập kết quả rỗng, khiến hệ thống báo sai “không có khách hàng” và che sự cố.

### Checklist thực hành

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Đã chọn API reactive đúng dependency/phiên bản chưa? | Repository/template và signature được hỗ trợ. |
| Entity đã mapping đúng namespace và field JSON chưa? | `@Document`, `@Scope`, `@Collection`, `@Field`. |
| Query theo ID hay theo field? | KV khác SQL++/index và consistency. |
| Publisher có được subscribe bởi tầng sở hữu lifecycle không? | Không bỏ quên thao tác, không subscribe tùy tiện. |
| Có `block()` trên request WebFlux không? | Tránh chặn event loop. |
| Có xử lý empty và error khác nhau không? | Không biến database outage thành 404/danh sách rỗng. |
| Query có điều kiện tenant ở mọi nhánh không? | Tránh đọc chéo tenant. |
| Có `LIMIT`/`ORDER BY` ở phía server không? | Không chỉ dựa `Flux.take`. |
| `collectList`/`buffer` có giới hạn không? | Kiểm soát bộ nhớ và backpressure. |
| Index và `EXPLAIN` đã đạt yêu cầu chưa? | Tránh scan/sort quá lớn. |
| Có ràng buộc uniqueness/CAS khi ghi không? | `save`/upsert không tự bảo đảm độc nhất. |
| Scan consistency/TTL có phù hợp read-after-write không? | Giải thích tình huống query chưa thấy ghi. |
| Có transaction thực sự nếu cần nguyên tử nhiều document không? | Reactor operators không tạo transaction. |
| Có StepVerifier và test Couchbase thật không? | Xác nhận kết quả, lỗi, subscription, concurrency. |

## 20. Ghi nhớ

**`ReactiveCouchbaseRepository`** phù hợp với CRUD và truy vấn tương đối ổn định bằng giao diện repository. **`ReactiveCouchbaseTemplate`** cho quyền kiểm soát linh hoạt hơn đối với truy vấn và mutation, đặc biệt khi bộ lọc động hoặc cần API fluent. Cả hai tích hợp với **Project Reactor** qua `Mono`/`Flux`, nhưng vẫn sử dụng Couchbase KV/Query Service, document mapping, namespace và index như các cơ chế dữ liệu nền tảng.

Thiết kế reactive đúng nghĩa là **trả publisher thay vì tự subscribe**, **không chặn event loop**, phân biệt **empty với error**, quản lý **concurrency/backpressure**, giới hạn kết quả ở **query phía server**, và kiểm chứng consistency/TTL/CAS/transaction trên phiên bản đang chạy. Lựa chọn repository hay template không phải mục tiêu cuối; mục tiêu là một tầng truy cập Couchbase **đúng nghiệp vụ, quan sát được, hiệu quả và vận hành an toàn**.
