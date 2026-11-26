# Truy vấn dẫn xuất và @Query với kiểu trả về phản ứng

Trong **SPRING_DATA_COUCHBASE**, một repository reactive có thể truy vấn Couchbase theo hai hướng chính: **suy diễn truy vấn từ tên phương thức** (*derived query*) và **khai báo SQL++ tường minh bằng `@Query`**. Cả hai đều có thể trả `Mono<T>` hoặc `Flux<T>` của Project Reactor, nhưng chúng khác nhau về cách biểu đạt điều kiện, khả năng kiểm soát truy vấn, quản lý metadata document và rủi ro khi câu hỏi nghiệp vụ trở nên phức tạp.

Ví dụ, “tìm mọi khách hàng ACTIVE của một tenant” là bài toán phù hợp với `findByTenantIdAndStatus`. Nhưng yêu cầu “tìm khách hàng ACTIVE thuộc tenant này, và (ở một trong các thành phố chỉ định **hoặc** có điểm từ ngưỡng cho trước), sắp mã và giới hạn kết quả” cần các dấu ngoặc logic rõ ràng; `@Query` có thể dễ đọc và dễ kiểm thử hơn một tên phương thức dài.

Bài thuộc chương **Truy cập phản ứng** và tập trung vào hợp đồng của `Mono`/`Flux`, hai cách tạo SQL++, binding tham số, projection/metadata, giới hạn kết quả, sắp xếp và consistency. Đây là phần của mục tiêu xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate`/`ReactiveCouchbaseTemplate` và SQL++ trên bucket/scope/collection; index, TTL, CAS, giao dịch và backpressure ảnh hưởng trực tiếp đến tính đúng đắn và khả năng vận hành.

> **Nguyên tắc:** Reactor quyết định **cách tiêu thụ** truy vấn; derived query hoặc `@Query` quyết định **truy vấn nào** được gửi tới Couchbase. `Flux` không tự thay thế `WHERE`, `ORDER BY` hay `LIMIT`, và `Mono` không tự bảo đảm giá trị truy vấn là duy nhất.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Khai báo `ReactiveCouchbaseRepository` với phương thức derived query trả `Flux<Customer>` hoặc `Mono<Customer>`.
2. Đọc tên phương thức dựa trên **property Java**, `@Field`, từ khóa so sánh và logic `And`/`Or`.
3. Nhận biết khi nào derived query quá dài hoặc không thể biểu đạt dấu ngoặc logic, JSON `MISSING`, biểu thức mảng và các phép tổng hợp.
4. Viết một `@Query` biểu đạt SQL++ có tham số binding và điều kiện tenant bắt buộc.
5. Hiểu vai trò của mẫu SpEL dành cho N1QL/SQL++ như `#{#n1ql.selectEntity}` và `#{#n1ql.filter}` trong những phiên bản hỗ trợ.
6. Phân biệt truy vấn trả **entity**, **scalar**, **DTO/projection** và metadata document ID/CAS.
7. Chọn `Flux<T>`, `Mono<T>`, `Mono<Long>` hoặc `Mono<Boolean>` theo ngữ nghĩa 0, 1 hay nhiều kết quả.
8. Kết hợp sort/limit và phân trang mà không nhầm `Flux.take(n)` với `LIMIT n` ở Query Service.
9. Dùng `EXPLAIN` để xem index và kiểm tra query consistency khi dữ liệu vừa được ghi.
10. Viết integration test với `StepVerifier` trên bộ dữ liệu có tenant chéo, giá trị biên, null/missing và thứ tự sắp xếp.

## 2. Chuẩn bị entity và namespace

Giả sử ứng dụng CRM dùng bucket `app`, scope `crm`, collection `customers`. Một document mẫu:

```json
{
  "tenant_id": "tenant-a",
  "customer_code": "C002",
  "display_name": "Lan Anh",
  "email": "lan@example.test",
  "status": "ACTIVE",
  "city": "HANOI",
  "loyalty_points": 120,
  "address_info": {
    "district_name": "CAU_GIAY"
  }
}
```

Couchbase lưu document ID riêng, ví dụ `customer::tenant-a::C002`. Mã `customer_code` ở đây là trường nghiệp vụ được giả định duy nhất trong tenant. Một entity tham khảo:

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
    private String email;

    @Field
    private String status;

    @Field
    private String city;

    @Field("loyalty_points")
    private Integer loyaltyPoints;

    @Field("address_info")
    private Address address;

    @Version
    private Long version;

    protected Customer() {
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getCustomerCode() { return customerCode; }
    public String getStatus() { return status; }
    public Integer getLoyaltyPoints() { return loyaltyPoints; }

    // Constructor nghiệp vụ và các getters/setters khác được lược bỏ.
}

class Address {

    @Field("district_name")
    private String district;

    protected Address() {
    }
}
```

`@Field` ánh xạ property Java sang field JSON. Vì vậy:

| Property Java | Field JSON trong SQL++ |
| --- | --- |
| `tenantId` | `tenant_id` |
| `customerCode` | `customer_code` |
| `displayName` | `display_name` |
| `email` | `email` |
| `loyaltyPoints` | `loyalty_points` |
| `address.district` | `address_info.district_name` |

`@Id` biểu diễn **document ID**, không nhất thiết là field JSON `id`. `@Version` hỗ trợ optimistic locking/CAS theo phiên bản Spring Data Couchbase; không giả định entity version được lưu như một số nguyên JSON bình thường.

Mẫu entity minh họa yêu cầu Spring Boot/Couchbase đã được cấu hình đúng bucket, scope, collection, converters và credentials. Những mẫu `@Query` trong bài phải được đối chiếu với Spring Data Couchbase **đúng phiên bản đang chạy**, vì template SpEL, cách binding, projection và hỗ trợ các keyword không nhất thiết bất biến giữa các release.

## 3. Repository reactive và hợp đồng trả về

Khai báo:

```java
package example.crm;

import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    Flux<Customer> findByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
```

Một lời gọi:

```java
Flux<Customer> active = repository.findByTenantIdAndStatus(
    "tenant-a", "ACTIVE"
);
```

trả publisher để tầng gọi tiêu thụ. Với thao tác reactive repository điển hình, công việc I/O thực tế được kích hoạt khi publisher có subscription. Lúc tạo publisher, code Java vẫn có thể validate tham số hoặc xây biểu thức query tùy implementation, nên không có nghĩa *mọi thứ đều chưa chạy*.

### 3.1. Chọn đúng kiểu publisher

| Kiểu trả về | Ý nghĩa mong đợi | Ví dụ |
| --- | --- | --- |
| `Flux<Customer>` | 0 đến nhiều customer | Tìm theo status/tenant. |
| `Mono<Customer>` | Tối đa một customer | `findById` hoặc truy vấn được bảo đảm đơn trị. |
| `Mono<Long>` | Một số đếm (theo API hỗ trợ) | `countByTenantIdAndStatus`. |
| `Mono<Boolean>` | Có hay không có kết quả | `existsByTenantIdAndEmail`. |
| `Mono<CustomerView>` | Một DTO/projection | Query projection một dòng, khi mapping được hỗ trợ. |
| `Mono<Void>` | Không có item; quan tâm hoàn tất | Mutation xóa hoặc bước chỉ phát completion. |

**Không được tự suy ra tính duy nhất từ `Mono<Customer>`**. Nếu SQL++ khớp nhiều dòng nhưng method chỉ khai báo một phần tử, cần xác minh framework xử lý như thế nào: báo lỗi, lấy một kết quả hay áp dụng giới hạn. Khi nghiệp vụ yêu cầu “khách hàng mới nhất”, phải có thứ tự và giới hạn rõ ràng, không chỉ khai báo `Mono`.

### 3.2. `Mono.empty()` không phải lỗi

`findById` có thể hoàn tất rỗng nếu document ID không tồn tại; lỗi kết nối, quyền hoặc query phải đi theo tín hiệu `onError`. JSON `NULL` của một field không đồng nghĩa publisher phát `null`; Reactive Streams không cho phép `onNext(null)`.

```java
import java.util.NoSuchElementException;

Mono<Customer> required = repository.findById(documentId)
    .switchIfEmpty(Mono.error(
        new NoSuchElementException("Customer not found")
    ));
```

`switchIfEmpty` không biến lỗi Couchbase thành not-found. Tránh `onErrorResume(e -> Mono.empty())` đại trà vì nó che sự cố hệ thống thành trạng thái “không có dữ liệu”.

## 4. Truy vấn dẫn xuất: đọc tên method để hiểu điều kiện

Một số chữ ký ứng viên:

```java
import java.util.Collection;
import reactor.core.publisher.Flux;

Flux<Customer> findByTenantIdAndStatus(
    String tenantId,
    String status
);

Flux<Customer> findByTenantIdAndLoyaltyPointsGreaterThanEqual(
    String tenantId,
    Integer minPoints
);

Flux<Customer> findByTenantIdAndCityIn(
    String tenantId,
    Collection<String> cities
);

Flux<Customer> findByTenantIdAndAddress_District(
    String tenantId,
    String district
);
```

Spring Data phân tích tên method dựa trên **property Java** (`tenantId`, `loyaltyPoints`, `address.district`). Query creator của Spring Data Couchbase dùng thông tin mapping để xây SQL++ tham chiếu field JSON.

Ví dụ logic của `findByTenantIdAndLoyaltyPointsGreaterThanEqual`:

```sql
-- Minh họa ý định, không phải statement framework sinh nguyên văn.
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`tenant_id` = $tenantId
  AND c.`loyalty_points` >= $minPoints;
```

**Tầng parser và tầng backend khác nhau.** Một từ khóa được Spring Data Commons hiểu trong `PartTree` hoặc được Spring Data JPA hỗ trợ **không chứng minh** Spring Data Couchbase phiên bản này tạo được SQL++ tương ứng. Những từ như `IgnoreCase`, `IsNull`, `TopN`, `Between`, `In`, `NotIn`, nested array và `deleteBy` đều cần kiểm thử nếu ứng dụng định dùng.

### 4.1. Có thể suy diễn một chuỗi điều kiện đơn giản

Với phương thức:

```java
Flux<Customer> findByTenantIdAndStatusAndCity(
    String tenantId,
    String status,
    String city
);
```

người đọc thường hiểu là:

```text
tenantId = ?
AND status = ?
AND city = ?
```

Nó phù hợp khi điều kiện luôn cố định và không cần dấu ngoặc phức tạp. Nếu ứng dụng có nhiều biến thể status/city/time range/sort, việc tiếp tục kéo dài tên method sẽ giảm khả năng review.

### 4.2. Nested path khác field JSON

Method:

```java
Flux<Customer> findByTenantIdAndAddress_District(
    String tenantId,
    String district
);
```

dùng dấu `_` để chỉ ranh giới property path `address.district`, **không** phải để mô tả tên JSON `address_info.district_name`. Parser có thể mơ hồ nếu entity có cả property `addressDistrict` và `address.district`; hãy kiểm tra JSON path thực sự trong SQL++.

## 5. `@Query`: khi muốn mô tả SQL++ tường minh

`@Query` của Spring Data Couchbase giúp khai báo query text ngay cạnh method repository thay vì suy diễn toàn bộ predicate từ tên. Nó đặc biệt hữu ích khi cần:

- Ngoặc `AND`/`OR` chính xác, nhất là chính sách tenant.
- Biểu thức `IS MISSING`, `IS NOT VALUED` hoặc xử lý dữ liệu JSON không đồng nhất.
- Truy vấn trên mảng object bằng `ANY ... SATISFIES ... END`.
- Projection đặc thù, `GROUP BY`, aggregate hoặc biểu thức `CASE`.
- `ORDER BY` nhiều khóa và giới hạn rõ khi điều kiện phức tạp.
- Logic cố định nhưng tên phương thức sẽ quá dài và khó kiểm chứng.

Với các release hỗ trợ các biểu thức hỗ trợ N1QL/SQL++, một mẫu thông dụng dùng `@Query` cùng SpEL:

```java
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface CustomerQueryRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    @Query("""
        #{#n1ql.selectEntity}
        WHERE #{#n1ql.filter}
          AND tenant_id = $1
          AND status = $2
        """)
    Flux<Customer> findActiveForTenant(
        String tenantId,
        String status
    );
}
```

Đây là **mẫu ứng viên để kiểm chứng trên release sử dụng**. Các bản Spring Data Couchbase có thể khác về cú pháp `@Query`, macro SpEL, Java text block, default query context và quy ước tham số. Trong ví dụ, `$1` và `$2` là **positional bind placeholders** của kiểu query hỗ trợ, không phải nối chuỗi input vào SQL++.

### 5.1. Đọc ba phần của mẫu `@Query`

| Phần | Vai trò |
| --- | --- |
| `#{#n1ql.selectEntity}` | Mẫu select/projection entity của Spring Data Couchbase ở các phiên bản hỗ trợ; có thể bao gồm keyspace và metadata cần cho mapping. |
| `#{#n1ql.filter}` | Bộ lọc entity/type discriminator mà Spring Data cung cấp trong ngữ cảnh tương ứng. |
| `tenant_id = $1 AND status = $2` | Điều kiện nghiệp vụ do tác giả query viết; giá trị được bind theo phương thức. |

Đừng chép SQL++ `SELECT c.*` giản lược rồi kết luận mapping entity chắc chắn đủ. Spring Data Couchbase có thể cần document ID, CAS và type metadata trong projection khi ánh xạ kết quả thành entity, nhất là entity có `@Id`/`@Version`. Macro giúp tránh viết sai projection trong **những phiên bản thực sự hỗ trợ**, nhưng không thay thế integration test.

### 5.2. Macro và cú pháp thật cần được đối chiếu

Cú pháp `#{#n1ql.selectEntity}`/`#{#n1ql.filter}` xuất hiện trong hệ sinh thái Spring Data Couchbase ở một số release. Không được giả định rằng:

- Tất cả release đều dùng cùng biểu thức và cùng cách chọn scope/collection.
- Mọi DTO/projection có thể sử dụng cùng một macro như entity.
- `@Query` tự thêm mọi điều kiện bảo mật tenant.
- Một câu `@Query` đang trả `Flux<Customer>` có thể đổi thành `Mono<Page<Customer>>` và framework sẽ tự tạo count query.
- Mọi phương thức repository reactive đều hỗ trợ chính xác cùng ngữ nghĩa với repository imperative.

Nếu query không chạy hoặc mapping sai, bước đầu tiên là kiểm tra **phiên bản được resolve**, reference docs đúng release, SQL++ đã tạo, thông báo lỗi và JSON thực tế.

## 6. Tại sao cần `@Query` cho ngoặc `AND`/`OR`?

Giả sử nghiệp vụ yêu cầu:

> Chỉ khách hàng của **tenant-a**, có status ACTIVE, và (**ở HANOI/HCM** hoặc **có từ 100 điểm trở lên**).

Predicate đúng:

```text
tenant = "tenant-a"
AND status = "ACTIVE"
AND (
    city IN ["HANOI", "HCM"]
    OR loyaltyPoints >= 100
)
```

Một tên method dễ gây hiểu nhầm:

```java
Flux<Customer>
findByTenantIdAndStatusAndCityInOrLoyaltyPointsGreaterThanEqual(
    String tenantId,
    String status,
    java.util.Collection<String> cities,
    Integer minPoints
);
```

Ngữ pháp phân tích `And`/`Or` thông thường có thể tạo logic:

```text
(tenantId = ? AND status = ? AND city IN ?)
OR loyaltyPoints >= ?
```

Nhánh `OR` thứ hai **không còn bị tenant/status giới hạn**. Đối với collection dùng chung nhiều tenant, lỗi này có nguy cơ rò rỉ dữ liệu nếu tầng phân quyền cũng dựa vào predicate đó.

### 6.1. SQL++ có ngoặc rõ ràng

Một mẫu `@Query` tham khảo:

```java
@Query("""
    #{#n1ql.selectEntity}
    WHERE #{#n1ql.filter}
      AND tenant_id = $1
      AND status = $2
      AND (
           city IN $3
           OR loyalty_points >= $4
      )
    ORDER BY customer_code ASC
    """)
Flux<Customer> findEligibleForTenant(
    String tenantId,
    String status,
    java.util.Collection<String> cities,
    Integer minPoints
);
```

Ví dụ nhấn mạnh **logic có ngoặc và binding**. Phải kiểm tra rằng kiểu `Collection<String>` được bind đúng thành giá trị mảng SQL++ theo phiên bản và câu query thật; nếu không, dùng query parameter type/options được SDK hỗ trợ. Không nối danh sách city vào query text bằng string interpolation từ client.

### 6.2. Fixture cho thấy khác biệt

| ID | Tenant | Status | City | Points | Được phép trả? |
| --- | --- | --- | --- | ---: | :---: |
| `c01` | tenant-a | ACTIVE | HANOI | 20 | ✓ |
| `c02` | tenant-a | ACTIVE | DANANG | 130 | ✓ |
| `c03` | tenant-a | SUSPENDED | HANOI | 200 | ✗ |
| `c04` | tenant-b | ACTIVE | HCM | 170 | ✗ |
| `c05` | tenant-b | SUSPENDED | DANANG | 0 | ✗ |
| `c06` | tenant-a | ACTIVE | HCM | 10 | ✓ |
| `c07` | tenant-a | ACTIVE | DANANG | 90 | ✗ |

Với `cities=["HANOI","HCM"]` và `minPoints=100`, kết quả đúng là **`{c01, c02, c06}`**. Tên derived query nhóm `OR` không đúng có thể chọn thêm `c03` và `c04` vì chúng đạt ngưỡng điểm nhưng không thỏa tenant/status.

**Quy tắc an toàn:** Điều kiện tenant và phân quyền phải bao phủ mọi nhánh `OR`; `@Query` chỉ làm ngoặc rõ ràng, còn chính sách xác thực/phân quyền phải được bảo đảm bởi ứng dụng.

## 7. `@Query` và tham số: bind thay vì nối chuỗi

Khi viết SQL++ tường minh, dùng placeholders cho **giá trị**.

```sql
WHERE tenant_id = $1
  AND status = $2
  AND loyalty_points >= $3
```

Ý nghĩa là:

1. `$1` nhận tenant được xác thực.
2. `$2` nhận status đã được validate.
3. `$3` nhận điểm dạng số theo đúng kiểu JSON.

Không dùng:

```java
// Anti-pattern: minh họa lỗi, không đưa vào ứng dụng.
String query = "SELECT * FROM customers WHERE status = '"
    + userProvidedStatus + "'";
```

Việc nối input vào SQL++ có nguy cơ injection và làm khó xử lý dấu nháy, Unicode, kiểu dữ liệu và cache kế hoạch truy vấn.

### 7.1. Tên field và keyspace không phải tham số dữ liệu thông thường

Bind placeholders phù hợp cho **giá trị** như email, status, ngưỡng điểm hoặc kích thước giới hạn mà backend cho phép. Không tự động truyền tên field, tên collection hoặc hướng `ASC/DESC` từ input client vào cú pháp SQL++ như một giá trị bình thường.

Với UI có lựa chọn sắp xếp, nên dùng **whitelist** ánh xạ sang các profile query/sort đã được xác nhận:

| Lựa chọn client | Sort profile được server cho phép |
| --- | --- |
| `code_asc` | `customer_code ASC` |
| `points_desc` | `loyalty_points DESC, customer_code ASC` |
| `name_asc` | `display_name ASC, customer_code ASC` |

Nếu dùng dynamic query builder, chỉ dựng tên trường và hướng từ danh sách đã kiểm soát; các giá trị lọc vẫn dùng binding.

### 7.2. Không nhầm `null` đầu vào với JSON `NULL`

Giả sử UI bỏ qua bộ lọc city bằng cách truyền Java `null`. Điều đó **không có nghĩa** một derived query `findByCity(null)` hoặc `WHERE city = $city` sẽ tự hiểu “không lọc city”.

Cần thiết kế hợp đồng cụ thể:

- Nếu city không được gửi → bỏ predicate.
- Nếu city được gửi hợp lệ → thêm `city = $city`.
- Nếu nghiệp vụ tìm document có JSON null → dùng `IS NULL`.
- Nếu nghiệp vụ tìm document không có field → dùng `IS MISSING`.
- Nếu muốn null **hoặc** missing → dùng `IS NOT VALUED`.

Đây thường là lý do chuyển sang `ReactiveCouchbaseTemplate`/query builder thay vì tạo nhiều method `@Query` cho mọi tổ hợp filter tùy chọn.

## 8. SQL++ trên JSON: `NULL`, `MISSING` và mảng

Couchbase phân biệt nhiều trạng thái JSON:

```json
{"city": "HANOI"}
```

```json
{"city": null}
```

```json
{}
```

```json
{"city": 123}
```

Chúng không giống nhau: giá trị chuỗi, null, missing và sai kiểu. Khi đọc query tự sinh hoặc query tường minh, phải xác nhận tập document mong đợi.

### 8.1. Trường `NULL` khác trường `MISSING`

```sql
-- Chỉ field có JSON null.
WHERE c.city IS NULL
```

```sql
-- Field không tồn tại.
WHERE c.city IS MISSING
```

```sql
-- Field không có giá trị: null hoặc missing.
WHERE c.city IS NOT VALUED
```

Một ứng viên derived query như `findByCityIsNull` không nên được hiểu mặc nhiên là lấy cả hai trạng thái. Kiểm tra SQL++ được sinh và phiên bản cụ thể. Với yêu cầu chính xác về missing, `@Query` tường minh thường dễ review hơn.

### 8.2. Mảng object: một phần tử phải thỏa cùng lúc hai điều kiện

Giả sử document có:

```json
{
  "contacts": [
    {"type": "PHONE", "value": "0900000001"},
    {"type": "EMAIL", "value": "lan@example.test"}
  ]
}
```

Ý định “một contact có type PHONE và value 0900000001” cần kiểm tra **cùng một phần tử**. SQL++ có thể biểu đạt:

```sql
WHERE ANY contact IN c.contacts
      SATISFIES contact.type = "PHONE"
            AND contact.value = $phone
      END
```

Không suy luận rằng tên `findByContacts_TypeAndContacts_Value` sẽ tự sinh biểu thức `ANY` chính xác. Với array, `@Query`/template và array index có thể là lựa chọn đúng; phải kiểm tra hỗ trợ của bản Couchbase Server và plan.

### 8.3. Nested property dùng tên Java ở derived, JSON ở SQL++

Một method `findByAddress_District` tham chiếu property Java `address.district`. Với entity ví dụ, SQL++ phải truy cập `address_info.district_name`. Trong `@Query` viết SQL++ trực tiếp, vì vậy tên trường trong statement phải dựa trên **JSON thực tế**, không mặc định tên property Java được tự đổi.

## 9. Kết quả entity, projection và metadata

Một truy vấn SQL++ trả ra object JSON, còn Spring Data cần ánh xạ nó thành entity Java. Truy vấn `@Query` sai projection có thể trả đúng giá trị nghiệp vụ nhưng **mất document ID, CAS hoặc type metadata**, ảnh hưởng thao tác `save` sau này.

### 9.1. Entity hoàn chỉnh

Với `Flux<Customer>`, ưu tiên một query shape phù hợp mapper của Spring Data Couchbase. Các mẫu SpEL như `#{#n1ql.selectEntity}` được dùng ở những release hỗ trợ để tạo projection entity và phần `FROM` phù hợp.

```java
@Query("""
    #{#n1ql.selectEntity}
    WHERE #{#n1ql.filter}
      AND tenant_id = $1
    """)
Flux<Customer> allForTenant(String tenantId);
```

**Không** thay `#{#n1ql.selectEntity}` bằng `SELECT c.*` rồi bảo đảm ID/CAS vẫn có đủ mà không kiểm thử. Đặc biệt khi entity có `@Version`, metadata CAS là một phần quan trọng của optimistic locking.

### 9.2. DTO và projection

Một UI danh sách có thể chỉ cần mã, tên và thành phố, không cần mọi trường trong document. SQL++ minh họa:

```sql
SELECT c.customer_code AS customerCode,
       c.display_name AS displayName,
       c.city AS city
FROM `app`.`crm`.`customers` AS c
WHERE c.tenant_id = $tenantId
ORDER BY c.customer_code ASC
LIMIT 20;
```

Có thể thiết kế một DTO đọc:

```java
public record CustomerSummary(
    String customerCode,
    String displayName,
    String city
) {
}
```

Nhưng **không được tự khẳng định** một `@Query` trả `Flux<CustomerSummary>` luôn tự map record này trên mọi phiên bản Spring Data Couchbase. Cần kiểm tra cơ chế projection/constructor mapping, aliases, nested fields, metadata và DTO support của bản thư viện. Một số API SDK trả hàng dạng JSON để map tường minh, khác với repository entity mapping.

### 9.3. Không lưu projection như entity đầy đủ

Nếu projection không có đầy đủ field hoặc CAS, không lấy nó rồi gọi `save` như thể đó là trạng thái mới nhất của document. Dạng đọc chỉ vài field dùng cho UI không phải dữ liệu đầy đủ để replace/upsert.

Nếu cần cập nhật, ưu tiên đọc entity đầy đủ với version/CAS, mutation có điều kiện hoặc sub-document update theo API được hỗ trợ.

## 10. `Mono` cho một hàng, `Flux` cho nhiều hàng

Khi viết `@Query` hoặc derived query, kiểu publisher cần phản ánh cardinality.

### 10.1. Zero-or-one và uniqueness

Ví dụ tìm theo email:

```java
// Chỉ hợp lý nếu nghiệp vụ bảo đảm email duy nhất trong tenant.
Mono<Customer> findByTenantIdAndEmail(
    String tenantId,
    String email
);
```

Nếu email có thể trùng, phương thức trên không phải một cơ chế kiểm tra uniqueness. Cần quy tắc insert-if-absent/khóa xác định hoặc transaction trên đường ghi, không dựa vào chữ ký `Mono`.

### 10.2. “Lấy người mới nhất” phải có sort và limit

Một truy vấn ý định:

```sql
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.tenant_id = $tenantId
  AND c.status = "ACTIVE"
ORDER BY c.customer_code DESC
LIMIT 1;
```

Nếu muốn “mới nhất” theo thời gian, cần trường thời gian được chuẩn hóa và sort theo nó, không phải customer code trừ khi mã encode thứ tự thời gian theo hợp đồng. Với nhiều document cùng timestamp, bổ sung tie-breaker duy nhất.

Các từ khóa `First`/`Top` có thể biểu đạt intent này ở derived query khi phiên bản hỗ trợ. Nhưng **kiểu trả về đơn** không tự phát sinh `LIMIT 1` theo mọi API; cần kiểm tra SQL++ thực thi.

### 10.3. Đừng dùng `Flux.next()` làm bằng chứng query đã tối ưu

```java
Mono<Customer> firstSeen = repository
    .findByTenantIdAndStatus(tenantId, "ACTIVE")
    .next();
```

`next()` lấy item đầu tiên mà `Flux` phát rồi có thể hủy subscription upstream. Nó **không chứng minh** backend đã áp dụng `ORDER BY` hoặc `LIMIT 1`. Nếu nghiệp vụ cần một document cụ thể theo tiêu chí, đặt thứ tự/giới hạn trong query và xem index.

## 11. Count, exists và kết quả scalar

Nhóm derived query có thể diễn đạt:

```java
Mono<Long> countByTenantIdAndStatus(
    String tenantId,
    String status
);

Mono<Boolean> existsByTenantIdAndCustomerCode(
    String tenantId,
    String customerCode
);
```

Đây là **chữ ký ứng viên** phải kiểm chứng ở Spring Data Couchbase reactive version thực tế. Mục tiêu là hỏi số lượng hoặc sự tồn tại mà không tải mọi entity.

### 11.1. Count theo điều kiện

SQL++ minh họa:

```sql
SELECT COUNT(1) AS total
FROM `app`.`crm`.`customers` AS c
WHERE c.tenant_id = $tenantId
  AND c.status = $status;
```

`COUNT(1)` đếm dòng/document thỏa điều kiện; `COUNT(field)` có thể khác khi field null/missing. Query scalar cần mapping đúng kết quả và aliases; đừng mặc định `@Query` trả `Mono<Long>` sẽ tự đọc đúng `total` từ mọi SQL++ result shape.

### 11.2. Exists khác count và khác uniqueness

SQL++ diễn đạt sự tồn tại có thể lấy tối đa một ID:

```sql
SELECT META(c).id
FROM `app`.`crm`.`customers` AS c
WHERE c.tenant_id = $tenantId
  AND c.customer_code = $code
LIMIT 1;
```

Nhưng `existsBy...` của Spring Data Couchbase có thể dùng cơ chế khác theo phiên bản. Nó trả `true` khi **có ít nhất một** document, không bảo đảm **chính xác một** document. Chuỗi `exists → save` vẫn có race condition.

Không thay `countByStatus` bằng `findByStatus(...).collectList().map(List::size)` khi tập dữ liệu lớn: cách đó có thể tải toàn bộ entity về Java để đếm.

## 12. Sắp xếp và giới hạn trong hai cách truy vấn

### 12.1. Derived query và `Sort`

Một phương thức đơn giản có thể nhận `Sort` như một tham số đặc biệt ở những phiên bản hỗ trợ:

```java
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Flux;

Flux<Customer> findByTenantIdAndStatus(
    String tenantId,
    String status,
    Sort sort
);
```

Lời gọi:

```java
Sort sort = Sort.by(
    Sort.Order.desc("loyaltyPoints"),
    Sort.Order.asc("customerCode")
);

Flux<Customer> ranked =
    repository.findByTenantIdAndStatus(
        tenantId, "ACTIVE", sort
    );
```

`Sort` dùng **property Java** (`loyaltyPoints`), còn SQL++/index dùng field JSON (`loyalty_points`). Hãy xác minh query creator chuyển đúng tên, hướng, thứ tự và xử lý null/missing.

### 12.2. `Pageable` reactive

Một repository reactive có thể hỗ trợ các dạng nhận `Pageable` tùy release:

```java
// Chữ ký ứng viên: kiểm tra support theo phiên bản.
Flux<Customer> findByTenantIdAndStatus(
    String tenantId,
    String status,
    org.springframework.data.domain.Pageable pageable
);
```

Không giả định trả `Mono<Page<Customer>>` được xử lý giống repository imperative ở mọi Spring Data Couchbase release. Với reactive, nếu UI cần tổng số, có thể phải phối hợp **query trang** và **query đếm riêng**.

```java
// Minh họa shape của hai publisher, không có snapshot chung.
Flux<Customer> pageRows = findPageForTenant(tenantId, pageable);
Mono<Long> totalCount = countActiveForTenant(tenantId);
```

`findPageForTenant` và `countActiveForTenant` là helper nghiệp vụ minh họa, cần được triển khai với query giới hạn và API tương thích. Kết quả trang và count có thể quan sát trạng thái dữ liệu khác nhau nếu có ghi/xóa/TTL giữa các lần truy vấn.

### 12.3. `@Query` với `ORDER BY` và `LIMIT` rõ

Ví dụ mẫu:

```java
@Query("""
    #{#n1ql.selectEntity}
    WHERE #{#n1ql.filter}
      AND tenant_id = $1
      AND status = $2
    ORDER BY loyalty_points DESC,
             customer_code ASC
    LIMIT $3
    """)
Flux<Customer> findTopRankedForTenant(
    String tenantId,
    String status,
    int maxResults
);
```

Mẫu này minh họa binding giới hạn, nhưng phải **kiểm tra SQL++ và query binding của version**; bảo đảm `maxResults` được validate, ví dụ từ 1 đến 100, để client không yêu cầu hàng triệu document.

Khi cần sort động từ UI, không tự chèn chuỗi `ORDER BY` do client gửi vào annotation. Chọn một số query profile hoặc query builder/template có whitelist.

### 12.4. Thứ tự ổn định và phân trang

Nếu `loyalty_points` trùng giữa hai document, `ORDER BY loyalty_points DESC` chưa tạo thứ tự xác định. Thêm `customer_code ASC`, với điều kiện mã duy nhất trong tập đang truy vấn. Khi thực hiện `LIMIT`/`OFFSET`, luôn dùng thứ tự ổn định.

Nhưng dữ liệu vẫn có thể bị thêm, sửa hoặc hết hạn giữa các trang. Sort có tie-breaker không tự tạo snapshot; với offset rất lớn có thể dùng keyset pagination theo bộ khóa, được định nghĩa bằng SQL++ có điều kiện tiếp nối rõ.

## 13. Reactive pipeline tiêu thụ query

Một service có thể trả thẳng kết quả query:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public Flux<Customer> eligibleForTenant(
        String authenticatedTenant,
        java.util.Collection<String> cities,
        int minPoints) {

    return repository.findEligibleForTenant(
        authenticatedTenant,
        "ACTIVE",
        cities,
        minPoints
    );
}
```

`repository` ở đây là repository chứa phương thức `@Query` tại mục 6.1. Tầng gọi (WebFlux hoặc job) sẽ subscribe; service không cần `block()` hay `subscribe()`.

### 13.1. Biến đổi kết quả

```java
Flux<String> customerCodes = repository
    .findEligibleForTenant(
        tenantId, "ACTIVE", cities, minPoints
    )
    .map(Customer::getCustomerCode);
```

`map` biến đổi mỗi entity được phát, không làm SQL++ tự chỉ SELECT field `customer_code`. Nếu muốn giảm băng thông bằng projection ở server, cần thiết kế query trả DTO/projection và kiểm tra mapper.

### 13.2. Lấy một giá trị tổng hợp từ nhiều publisher

```java
Mono<java.util.List<String>> allCodes = repository
    .findEligibleForTenant(
        tenantId, "ACTIVE", cities, minPoints
    )
    .map(Customer::getCustomerCode)
    .collectList();
```

`collectList` tích lũy tất cả item trong bộ nhớ; chỉ nên dùng khi kết quả được giới hạn/chọn lọc rõ. `Flux` không tự có giới hạn an toàn.

### 13.3. Không biến query thành `Mono` bằng cách chặn

```java
// Anti-pattern trong WebFlux.
java.util.List<Customer> customers = repository
    .findByTenantIdAndStatus(tenantId, "ACTIVE")
    .collectList()
    .block();
```

`block()` chặn thread gọi, làm mất lợi ích non-blocking và có thể không được phép trên event loop. Trả publisher tới controller WebFlux, hoặc quản lý subscription trong một job có lifecycle rõ ràng.

### 13.4. Không tự subscribe hai lần

```java
// Anti-pattern: hai subscription có thể kích hoạt hai lần query.
Flux<Customer> query = repository
    .findByTenantIdAndStatus(tenantId, "ACTIVE");

query.subscribe(c -> logCustomer(c));
return query;
```

Ngoài chạy lặp, lệnh `subscribe` tự phát làm việc theo dõi lỗi, cancellation và trace khó kiểm soát. `logCustomer` là helper minh họa; khi cần logging, dùng `doOnNext` trong cùng pipeline với redaction, không tự tạo subscriber bổ sung.

## 14. Backpressure và quan hệ với SQL++ Query Service

Reactor cho phép downstream điều tiết demand, nhưng Couchbase Query Service và SDK có buffering, network và quy trình scan riêng. Do đó:

```java
Flux<Customer> preview = repository
    .findByTenantIdAndStatus(tenantId, "ACTIVE")
    .take(10);
```

`take(10)` chỉ bảo đảm downstream nhận tối đa 10 item theo semantics operator. Nó **không chứng minh SQL++ có `LIMIT 10`**, càng không bảo đảm index chỉ scan đúng 10 document.

Muốn giảm tải phía server:

1. Chỉ truy vấn đúng tenant và điều kiện nghiệp vụ.
2. Đặt `ORDER BY`/`LIMIT` trong query hoặc API được phiên bản hỗ trợ.
3. Xác định index hỗ trợ `WHERE` và thứ tự sort.
4. Dùng `EXPLAIN` và đo số lượng scan/fetch trên dữ liệu đại diện.
5. Sau đó mới chọn pipeline `Flux` để tiêu thụ với concurrency và buffer hợp lý.

### 14.1. `flatMap` có thể làm mất thứ tự

Nếu một danh sách ID được truy vấn song song:

```java
Flux<Customer> customers = Flux.fromIterable(ids)
    .flatMap(repository::findById, 8);
```

kết quả có thể phát theo thứ tự hoàn tất I/O, **không phải** thứ tự ID đầu vào. Nếu cần giữ thứ tự, cân nhắc `concatMap` hoặc `flatMapSequential`, cùng trade-off độ trễ/buffering. Không dùng Reactor để “bù” cho một SQL++ thiếu `ORDER BY` khi API yêu cầu thứ tự ổn định và phân trang server-side.

## 15. Index và `EXPLAIN` cho derived query và `@Query`

Một query có kết quả đúng với 10 fixture có thể rất chậm với hàng triệu document. Với Couchbase, secondary index quyết định hiệu quả truy vấn theo field.

### 15.1. Composite index cho tenant, status, sort

Ví dụ index minh họa:

```sql
CREATE INDEX ix_customer_tenant_status_points_code
ON `app`.`crm`.`customers` (
    `tenant_id`,
    `status`,
    `loyalty_points` DESC,
    `customer_code` ASC
);
```

Nó có thể hỗ trợ một số truy vấn lọc theo tenant/status và sắp theo điểm/mã. Nhưng **không cam kết** mọi query `@Query`/derived query sẽ chọn index này: type discriminator, thống kê, biểu thức `OR`, projection và cách planner sử dụng key có thể thay đổi.

Nếu repository thêm điều kiện `_class`, cần đối chiếu discriminator thật. Nếu query có nhánh `OR` giữa `city IN ...` và `loyalty_points >= ...`, có thể cần chiến lược index khác; một index duy nhất không chắc tối ưu cho mọi nhánh.

### 15.2. `EXPLAIN` truy vấn thực tế

```sql
EXPLAIN
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`tenant_id` = "tenant-a"
  AND c.`status` = "ACTIVE"
  AND (
       c.`city` IN ["HANOI", "HCM"]
       OR c.`loyalty_points` >= 100
  )
ORDER BY c.`customer_code` ASC
LIMIT 20;
```

Khi đánh giá thật, lấy statement do `@Query`/repository **đang thực thi** (gồm type filter, projection, alias và bind parameters tương ứng). Xem index được chọn, scan, fetch, sort, `LIMIT` và độ trễ ở dữ liệu đại diện.

Không tuyên bố query tối ưu chỉ vì kết quả là `Flux`. Tính bất đồng bộ ở Java không xóa chi phí CPU/memory/index của Couchbase Server.

### 15.3. Index và `MISSING`

Cần kiểm tra cách secondary index bao phủ document thiếu field key theo cấu hình/phiên bản. Nếu nghiệp vụ yêu cầu `IS MISSING`, một index vốn chỉ đưa vào document có field có thể khiến kế hoạch hoặc tập kết quả khác mong đợi. Kết hợp test dữ liệu biên và `EXPLAIN`, không chỉ benchmark query trên document đầy đủ.

## 16. Query consistency và read-after-write

Một pipeline:

```java
Mono<Customer> roundTrip = repository.save(customer)
    .flatMap(saved -> repository.findById(saved.getId()));
```

đảm bảo theo thứ tự của pipeline: nếu save phát thành công, lời gọi đọc theo ID được thực hiện tiếp. `findById` thường dùng key-value, còn truy vấn theo status/tenant thường dùng SQL++ qua index.

```java
Flux<Customer> visibleByQuery = repository.save(customer)
    .flatMapMany(saved ->
        repository.findByTenantIdAndStatus(
            saved.getTenantId(),
            saved.getStatus()
        )
    );
```

`flatMapMany` nối `Mono` sang `Flux` nhưng **không** ép secondary index cập nhật tức thì. Query qua field có thể chưa thấy mutation mới ở mức scan consistency mặc định. Nếu nghiệp vụ cần read-your-own-write qua SQL++, hãy cân nhắc scan consistency phù hợp (như mức tương đương `REQUEST_PLUS` khi Spring Data/SDK release hỗ trợ) hoặc query mutation-state options; đánh giá tác động đến latency.

Một truy vấn `@Query` không tự có consistency khác derived query chỉ vì SQL++ được viết tay. Kiểm tra query options và dữ liệu vừa ghi với integration test.

### 16.1. TTL và dữ liệu thay đổi

Document có TTL có thể hết hạn giữa hai subscription. `Flux` có thể trả ít item hơn dù query text không đổi. Tương tự, count và trang dữ liệu có thể khác nhau khi document bị thêm, sửa, xóa hoặc hết hạn.

`Sort`, `@Query` và `Pageable` không tự cung cấp snapshot bất biến qua nhiều HTTP request; nếu cần báo cáo lịch sử phải có chiến lược dữ liệu và transaction/snapshot thích hợp.

## 17. CAS, mutation và lý do query đọc không phải transaction

Một truy vấn `@Query` trả entity có thể được dùng làm đầu vào cho thao tác sửa:

```java
Mono<Customer> updated = repository.findById(id)
    .flatMap(customer -> {
        // Thay đổi field nghiệp vụ ở đây.
        return repository.save(customer);
    });
```

Nhưng **đọc → sửa → save** không tự khóa document giữa các request. Khi có `@Version`/CAS được cấu hình đúng, Spring Data Couchbase có thể phát hiện lost update; phải kiểm tra loại lỗi và cách retry trên phiên bản thực tế.

**Cảnh báo:** Nếu `@Query` trả entity nhưng projection bỏ metadata CAS, việc đọc entity rồi save có thể làm mất bảo đảm optimistic locking như ý định. Đây là một trong những lý do cần ưu tiên query shape/macro thích hợp và kiểm chứng end-to-end.

### 17.1. Hạn chế của reactive operators

`Mono.when(saveA, saveB)`, `then`, `zip` hoặc `flatMap` phối hợp publisher và thứ tự tín hiệu, **không tự tạo atomicity nhiều document**.

Nếu cần transaction Couchbase, phải dùng transaction API tương thích với Spring Data/Couchbase SDK và đường reactive đang dùng; kiểm tra transaction context, retry, giới hạn và mutation outcome. Không mặc định `@Transactional` bất kỳ hoặc một vòng `flatMap` bảo đảm all-or-nothing.

### 17.2. `@Query` cho delete/update không tương đương repository CRUD

Một `@Query` chứa SQL++ DML có đặc tính khác với `repository.delete(entity)`: metadata, CAS, callback, mutation metrics và transaction có thể không giống nhau. Nếu cần thao tác ghi theo predicate, xác minh rõ API Spring Data Couchbase release có hỗ trợ `@Query` DML hay không; không dùng annotation trên query xóa chỉ vì cú pháp SQL++ hợp lệ trong Workbench.

## 18. Xử lý lỗi và cancellation trong truy vấn reactive

### 18.1. Query lỗi phát `onError`

Một method `@Query` có thể lỗi vì:

- SQL++ sai cú pháp hoặc macro không được release hỗ trợ.
- Positional binding không đúng kiểu/thứ tự.
- Thiếu index hoặc quyền ở collection.
- Timeout, kết nối, query service quá tải.
- Mapping trả entity/DTO không tương thích với projection.

Không biến mọi lỗi thành `Flux.empty()`:

```java
// Anti-pattern: che lỗi hệ thống thành "không có customer".
Flux<Customer> result = repository
    .findByTenantIdAndStatus(tenantId, "ACTIVE")
    .onErrorResume(error -> Flux.empty());
```

Thay vào đó, để lỗi được lan truyền tới tầng có khả năng phân loại, ghi metric/trace có redaction và retry **chỉ** khi lỗi tạm thời và operation idempotent.

### 18.2. Timeout và cancel

```java
import java.time.Duration;

Flux<Customer> bounded = repository
    .findByTenantIdAndStatus(tenantId, "ACTIVE")
    .timeout(Duration.ofSeconds(5));
```

`timeout` giúp subscriber không đợi vô hạn, nhưng không bảo đảm server chưa chạy query hoặc tài nguyên đã được giải phóng tức thì. Với truy vấn chỉ đọc, retry có thể phù hợp nếu giới hạn và phân loại lỗi. Với mutation, timeout không chứng minh thao tác chưa commit.

### 18.3. Không tự subscribe trong service

```java
// Anti-pattern: subscription không được owner HTTP quản lý.
public Flux<Customer> search(String tenantId) {
    Flux<Customer> query = repository.findByTenantIdAndStatus(
        tenantId, "ACTIVE"
    );

    query.subscribe();
    return query;
}
```

Đoạn trên có thể kích hoạt hai lần truy vấn, làm khó theo dõi lỗi và tải. Service nên return publisher; WebFlux hoặc job có lifecycle rõ quản lý subscription.

## 19. Integration test với `StepVerifier`

Một test tốt phải xác minh **method query chạy trên Couchbase thật**, không chỉ chứng minh Java parse tên method. Cần test cluster/collection riêng, index, mapping/discriminator phù hợp và fixture có ID được kiểm soát.

### 19.1. Test query theo tenant và status

Giả sử các fixture ở mục 6.2 đã được seed vào test collection, đầy đủ metadata mà Spring Data cần.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveCustomerQueryIT {

    @Autowired
    CustomerQueryRepository repository;

    @Test
    void eligibleQueryNeverLeaksOtherTenant() {
        StepVerifier.create(
                repository.findEligibleForTenant(
                    "tenant-a",
                    "ACTIVE",
                    Set.of("HANOI", "HCM"),
                    100
                )
                .map(Customer::getId)
                .collectList()
            )
            .assertNext(ids -> assertThat(ids)
                .containsExactlyInAnyOrder("c01", "c02", "c06"))
            .verifyComplete();
    }
}
```

Test này là **khung tích hợp minh họa**, cần cấu hình repository bean, dependency, test cluster, index và fixtures thực tế. Trong ví dụ, ID trong bảng `c01`–`c07` được dùng làm document ID; nếu ứng dụng lưu ID có prefix, chỉnh expectation tương ứng.

Không chỉ assert `Flux` có ba item: tập ID mới chứng minh điều kiện tenant/status và dấu ngoặc `OR` hoạt động đúng.

### 19.2. Test derived query giá trị biên

Ví dụ với điểm của fixture:

| ID | Tenant | Status | Điểm |
| --- | --- | --- | ---: |
| `c01` | tenant-a | ACTIVE | 20 |
| `c02` | tenant-a | ACTIVE | 130 |
| `c03` | tenant-a | SUSPENDED | 200 |
| `c04` | tenant-b | ACTIVE | 170 |
| `c05` | tenant-b | SUSPENDED | 0 |
| `c06` | tenant-a | ACTIVE | 10 |
| `c07` | tenant-a | ACTIVE | 90 |

Với `findByTenantIdAndLoyaltyPointsGreaterThanEqual("tenant-a", 100)`, kết quả **không lọc status**, do đó là `{c02, c03}`, không phải chỉ `c02`. Đây là một ví dụ vì sao người viết cần đọc chính xác điều kiện method, không tự thêm logic status trong đầu.

Để kiểm tra ngưỡng biên, thêm một fixture có đúng 100 điểm và khẳng định `GreaterThanEqual` bao gồm nó, trong khi `GreaterThan` loại nó.

### 19.3. Test empty và error của publisher

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(Flux.<Customer>empty())
    .verifyComplete();

StepVerifier.create(
        Flux.<Customer>error(
            new IllegalStateException("simulated failure")
        )
    )
    .expectError(IllegalStateException.class)
    .verify();
```

Đây chỉ là unit test **tín hiệu Reactor**, không xác nhận Spring Data Couchbase sẽ phát `IllegalStateException` khi timeout hoặc không có index. Cần integration test riêng cho lỗi Couchbase thật và cách ánh xạ exception của release đang chạy.

### 19.4. Test subscription và consistency

Nếu test seed qua KV rồi gọi `@Query` ngay, kết quả có thể chưa thấy do index lag. Cần query scan consistency hoặc cơ chế chờ có điều kiện/timeout phù hợp; không thêm `Thread.sleep(1000)` rồi xem test đã đáng tin cậy.

Khi có reactive repository, test cần **subscribe và chờ hoàn tất** bằng `StepVerifier`. Tạo một biến `Flux` rồi assert biến không null chưa hề chứng minh query được thực thi.

### 19.5. Test SQL++ và plan

Bên cạnh `StepVerifier`, lưu chứng cứ:

- SQL++ thực sự đã gửi (redact giá trị nhạy cảm).
- Kiểu tham số và query options.
- Tên index và kết quả `EXPLAIN`.
- Số ID trả về và thứ tự nếu query có `ORDER BY`.
- Phiên bản Spring Data Couchbase/Commons, SDK và Couchbase Server.

Test chỉ chạy PASS trên một phiên bản không tự bảo đảm behavior tương tự khi nâng cấp dependencies.

## 20. Khi nào giữ derived, chọn `@Query` hay dùng template?

| Tình huống | Ưu tiên xem xét | Giải thích |
| --- | --- | --- |
| Tìm theo tenant + status cố định | Derived query | Tên ngắn, điều kiện rõ. |
| So sánh điểm hoặc khoảng đơn giản | Derived query nếu keyword hỗ trợ | Ít code hơn, cần test ngưỡng. |
| Ngoặc `AND`/`OR` phức tạp | `@Query` | Logic/điều kiện tenant nhìn thấy trực tiếp. |
| JSON `NULL`/`MISSING` đặc thù | `@Query` | Dùng các toán tử SQL++ rõ nghĩa. |
| Mảng object cần `ANY` | `@Query`/template | Đảm bảo các predicate trên cùng phần tử. |
| Bộ lọc tùy chọn động theo request | `ReactiveCouchbaseTemplate`/query builder | Tránh nhiều annotation gần giống nhau. |
| Chỉ cần count/exists đơn giản | Derived `countBy`/`existsBy` nếu hỗ trợ | Không lấy entity chỉ để đếm. |
| Projection chuyên biệt | `@Query` hoặc template | Kiểm soát select/aliases; kiểm tra mapping DTO. |
| Truy vấn FTS và ranking văn bản | FTS/API phù hợp | Không lạm dụng `Containing` substring. |
| Mutation theo ID và CAS | Repository/template/KV API | `@Query` đọc không thay mutation có điều kiện. |
| Cần query options, diagnostics đặc thù | Template/SDK API | Kiểm soát operation và options. |

**Không có lựa chọn nào luôn “reactive hơn” lựa chọn khác.** Cả derived repository và `@Query` có thể phát `Flux`/`Mono`; khả năng non-blocking của pipeline phải đi cùng query đúng logic, index tốt, giới hạn dữ liệu và xử lý lỗi.

## 21. Những sai lầm thường gặp

| Sai lầm | Vì sao sai? | Cách cải thiện |
| --- | --- | --- |
| “`Mono` = đúng một document.” | `Mono` phát **tối đa** một item; truy vấn có thể rỗng hoặc trùng dữ liệu. | Xác định cardinality và ràng buộc uniqueness. |
| “`Flux` tự tối ưu query.” | Query Service vẫn quét index/fetch/sort. | `WHERE`, `LIMIT`, `ORDER BY`, `EXPLAIN`. |
| “Parser hiểu keyword là Couchbase hỗ trợ.” | Parser chung khác query creator/backend. | Test đúng release. |
| “`And`/`Or` trong tên method tự hiểu ngoặc.” | Nhóm logic có thể sai và lộ tenant. | `@Query` với dấu ngoặc tường minh. |
| “`@Query SELECT c.*` luôn map entity đầy đủ.” | ID/CAS/type metadata có thể cần projection riêng. | Mẫu entity select được release hỗ trợ và test. |
| “Field trong `@Query` dùng tên Java.” | SQL++ truy cập JSON field vật lý. | Đối chiếu `@Field` và document thật. |
| “Dùng `@Query` thì không cần index.” | SQL++ vẫn cần index thích hợp. | Thiết kế index, `EXPLAIN`. |
| “`Flux.take(10)` = `LIMIT 10`.” | Giới hạn downstream không bảo đảm giới hạn phía server. | Đặt limit ở query. |
| “`Mono<Page<T>>` luôn được hỗ trợ.” | Reactive paging khác giữa module/release. | Chọn API được chứng minh, count riêng nếu cần. |
| “`save` rồi query luôn thấy document.” | SQL++ secondary index có thể cập nhật trễ. | Scan consistency hoặc KV lookup. |
| “`@Query` tự kiểm tra tenant.” | SQL++ chỉ chạy predicate đã được cấu hình. | Tenant từ security context và test chéo tenant. |
| “Cancel/timeout làm rollback query hoặc mutation.” | Lệnh có thể đã chạy ở server. | Kiểm tra outcome, idempotency và API phù hợp. |

## 22. Bài tập vận dụng

**Bài A — Chọn kiểu truy vấn.** Yêu cầu tìm mọi khách hàng ACTIVE thuộc tenant có quyền, không có điều kiện đặc thù. Chọn `findByTenantIdAndStatus` hay SQL++ viết tay?

**Gợi ý:** Bắt đầu từ derived query đơn giản nếu phiên bản hỗ trợ, với index và test tenant. Không cần `@Query` chỉ để lặp lại equality cơ bản.

**Bài B — Lỗi logic.** Với method `findByTenantIdAndStatusAndCityInOrLoyaltyPointsGreaterThanEqual`, phân tích vì sao một document tenant-b có điểm cao có thể lọt vào kết quả.

**Đáp án:** Nhánh `OR loyaltyPoints >= ...` có thể đứng ngoài điều kiện tenant/status theo cách nhóm predicate; chuyển sang SQL++ có ngoặc bao toàn bộ nhánh `OR` dưới điều kiện tenant.

**Bài C — Kiểu trả về.** Tại sao `Mono<Customer> findByTenantIdAndEmail(...)` không bảo đảm email duy nhất?

**Đáp án:** `Mono` chỉ là hợp đồng publisher tối đa một item; uniqueness là quy tắc dữ liệu được bảo đảm ở đường ghi/khóa/transaction phù hợp, không phải ở kiểu return.

**Bài D — Mapping.** Entity dùng `@Field("loyalty_points") private Integer loyaltyPoints;`. Trong SQL++ của `@Query` nên tham chiếu `loyaltyPoints` hay `loyalty_points`?

**Đáp án:** SQL++ truy cập JSON vật lý `loyalty_points` theo mapping ví dụ; tên Java `loyaltyPoints` dùng khi khai báo derived query hoặc `Sort`.

**Bài E — Projection.** Vì sao không nên trả `Flux<Customer>` từ một `@Query` chỉ SELECT tên và thành phố rồi dùng ngay entity để `save`?

**Đáp án:** Có thể thiếu nhiều field và metadata ID/CAS, dẫn đến overwrite sai hoặc optimistic locking không còn đúng. Dùng DTO/projection chỉ đọc hoặc query entity đầy đủ.

**Bài F — `take`.** Một `Flux` từ query 50.000 document được nối `take(5)`. Có chắc Couchbase chỉ phải quét năm document không?

**Đáp án:** Không. Reactor giới hạn item phát xuống downstream; muốn tối ưu server phải có limit/order/filter/index trong query thực thi.

**Bài G — Read-after-write.** Sau khi `save` hoàn tất, `findById` thấy document còn `@Query` theo status chưa thấy. Có thể kết luận `@Query` sai không?

**Đáp án:** Chưa. Kiểm tra type discriminator, mapping, namespace và secondary-index scan consistency trước. `flatMap` không buộc index cập nhật.

**Bài H — Test tenant.** Với fixture `c01`–`c07` ở mục 6, expected IDs của query ACTIVE thuộc tenant-a và (city HANOI/HCM hoặc points >= 100) là gì?

**Đáp án:** `{c01, c02, c06}`. Không được có `c03` vì status SUSPENDED hay `c04` vì tenant-b, dù điểm cao.

### Bảng kiểm trước khi sử dụng `@Query` reactive

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Đã chốt đúng phiên bản thư viện/Server? | Dependency tree và release docs liên quan. |
| Keyword derived query đã được hỗ trợ? | Repository khởi tạo và integration test PASS. |
| Query có đúng bucket/scope/collection? | SQL++/query context thực tế. |
| `@Field` có ánh xạ đúng đường JSON? | Document JSON và statement đã chạy. |
| Macro `selectEntity`/`filter` có tương thích release? | Query thực tế, entity ID/CAS mapping. |
| Tất cả nhánh `OR` bị tenant/status bao phủ? | Predicate có ngoặc và test chéo tenant. |
| Binding có đúng kiểu/thứ tự? | Statement/options và test dữ liệu biên. |
| Có xử lý `NULL`/`MISSING` đúng? | Fixture phân biệt hai trạng thái. |
| `Mono`/`Flux` đúng cardinality? | Test 0/1/nhiều kết quả và lỗi. |
| `Top`/`Pageable`/`LIMIT` có đẩy xuống server? | SQL++ và `EXPLAIN`, không chỉ `take`. |
| Sort có tie-breaker ổn định? | Test thứ tự và dữ liệu trùng khóa. |
| Có index phù hợp và query plan tốt? | `EXPLAIN`, độ trễ thực tế. |
| Scan consistency đáp ứng yêu cầu sau ghi? | Integration test read-after-write. |
| Không `block()` hoặc tự `subscribe()` trong service? | Review pipeline/WebFlux lifecycle. |
| CAS/TTL/transaction có được xem xét? | Kiểm tra mutation, expiration và consistency. |
| Error/cancel/timeout không bị nuốt? | Publisher assertions, tracing và metrics. |

## 23. Ghi nhớ

**Truy vấn dẫn xuất** thích hợp cho lọc đơn giản, ổn định và đã được kiểm chứng keyword ở bản Spring Data Couchbase sử dụng. **`@Query`** thích hợp khi SQL++ cần ngoặc điều kiện chính xác, xử lý `NULL`/`MISSING`, mảng, projection hoặc biểu thức mà tên method không diễn đạt an toàn. Cả hai có thể trả `Mono`/`Flux` nhưng **không tự thay thế** việc chọn đúng cardinality, giới hạn, sort và index.

Muốn một truy vấn reactive đáng tin cậy, hãy kiểm tra: **property Java và field JSON**, **metadata entity ID/CAS**, **cú pháp SpEL/binding đúng release**, **điều kiện tenant trong mọi nhánh**, **`ORDER BY`/`LIMIT` phía Query Service**, **`EXPLAIN`**, **scan consistency** và **kết quả của `StepVerifier` trên fixtures đại diện**. Reactive mang lại cách phối hợp I/O không chặn; tính chính xác nghiệp vụ, bảo mật dữ liệu và nhất quán giữa các thao tác vẫn do thiết kế Couchbase và ứng dụng quyết định.
