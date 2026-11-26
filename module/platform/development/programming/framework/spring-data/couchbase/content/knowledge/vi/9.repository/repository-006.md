# Kiểu trả về Optional, danh sách và kết quả không tồn tại

Trong chương **Repository** của **SPRING_DATA_COUCHBASE**, sau khi định nghĩa entity và các phương thức truy cập Couchbase, một câu hỏi quan trọng là: **phương thức sẽ trả về gì nếu không tìm thấy document nào?** Tầng repository cần biểu diễn đúng trường hợp này để service, API và giao diện người dùng xử lý nhất quán.

Spring Data Couchbase có thể đọc một document bằng khóa thông qua **KV API**, hoặc tìm nhiều document dựa trên trường JSON thông qua **SQL++**. Vì vậy, kiểu trả về không chỉ ảnh hưởng cú pháp Java, mà còn thể hiện **số lượng kết quả mong đợi**, ngữ nghĩa “không tồn tại”, cách xử lý lỗi và khả năng phân trang.

Bài này tập trung vào `Optional<T>`, các kiểu kết quả tập hợp như `List<T>`, `Iterable<T>`, `Page<T>` và trường hợp không tìm thấy; đồng thời liên hệ với thiết kế document key, bucket/scope/collection, chỉ mục SQL++, TTL, CAS và API reactive trong tầng truy cập dữ liệu.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Dùng `Optional<Customer>` để biểu diễn **có hoặc không có một document** được tìm theo ID.
- Dùng `List<Customer>` để biểu diễn **0 đến nhiều kết quả** của một truy vấn.
- Phân biệt `Optional.empty()`, `List.of()` và **lỗi thực thi** như timeout, thiếu index hoặc xung đột ánh xạ.
- Nhận biết khi nào phương thức query khai báo `Optional<T>` có thể gặp **nhiều hơn một kết quả**, và vì sao `Optional` không tạo ràng buộc duy nhất trong dữ liệu.
- Thiết kế service/API xử lý không tìm thấy, danh sách rỗng và lỗi kết nối khác nhau.
- Hiểu phiên bản tương đương trong reactive repository: `Mono<T>`, `Flux<T>`, `Mono.empty()` và `Flux.empty()`.

## 2. Trước tiên, xác định truy vấn mong đợi bao nhiêu kết quả

Kiểu trả về nên được lựa chọn theo **ngữ nghĩa dữ liệu** chứ không chỉ theo cách muốn hiển thị màn hình.

| Câu hỏi của ứng dụng | Phương thức ví dụ | Kiểu trả về phù hợp | Nếu không có kết quả |
| --- | --- | --- | --- |
| Document có key chính xác `customer::tenant-a::C102` là gì? | `findById(id)` | `Optional<Customer>` | `Optional.empty()` |
| Có đúng một customer cho cặp tenant và mã khách hàng? | `findByTenantIdAndCustomerCode(...)` | `Optional<Customer>` khi dữ liệu bảo đảm tối đa một hàng | `Optional.empty()` |
| Tenant A có những customer ACTIVE nào? | `findByTenantIdAndStatus(...)` | `List<Customer>` | Danh sách rỗng |
| Lấy tập document theo các ID được chọn | `findAllById(ids)` | `Iterable<Customer>` theo giao diện CRUD | Iterable không có phần tử |
| Duyệt danh sách lớn theo trang | `findByTenantId(..., Pageable)` | `Page<Customer>` hoặc kiểu phân trang được hỗ trợ | Trang không có phần tử |
| Kiểm tra có document mang key không | `existsById(id)` | `boolean` | `false` |
| Đếm những document phù hợp điều kiện | `countByTenantId(...)` | `long` | `0` |

Cần nhớ **ba trường hợp khác nhau**:

1. **Không tìm thấy nhưng thao tác hợp lệ:** là kết quả bình thường; trả `Optional.empty()`, tập hợp rỗng, `false` hoặc `0`.
2. **Có nhiều kết quả ngoài dự kiến:** nếu ứng dụng yêu cầu tối đa một document mà query khớp nhiều document, đây là vấn đề về **cardinality** hoặc dữ liệu không nhất quán, không nên âm thầm chọn hàng đầu tiên.
3. **Không thể thực thi thao tác:** kết nối bị lỗi, timeout, thiếu index, không đủ quyền hoặc mapping sai. Đây là **lỗi**, không phải kết quả rỗng.

Không nên bắt mọi exception rồi trả `Optional.empty()` vì hành vi đó biến sự cố hệ thống thành thông báo sai rằng document không tồn tại.

## 3. Mô hình ví dụ: document key và trường JSON

Giả sử ứng dụng dùng:

```text
Bucket:      appdata
Scope:       sales
Collection:  customers
```

Document khách hàng thứ nhất:

```text
Document key: customer::tenant-a::C102
```

```json
{
  "tenantId": "tenant-a",
  "customerCode": "C102",
  "displayName": "Lan Anh",
  "status": "ACTIVE"
}
```

Document thứ hai:

```text
Document key: customer::tenant-a::C103
```

```json
{
  "tenantId": "tenant-a",
  "customerCode": "C103",
  "displayName": "Minh",
  "status": "INACTIVE"
}
```

Couchbase có **document key** riêng với phần JSON. Spring Data dùng `@Id` để ánh xạ key. Trường `customerCode` chỉ là dữ liệu nghiệp vụ; không mặc nhiên trở thành khóa tra cứu của `findById`.

Ví dụ `repository.findById("C102")` **không** truy cập document có key `customer::tenant-a::C102`. Cần cung cấp key chính xác hoặc dùng truy vấn theo thuộc tính `customerCode`.

## 4. Khai báo entity và repository

### 4.1. Entity `Customer`

```java
package com.example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("customers")
public class Customer {

    @Id
    private String id;

    @Field
    private String tenantId;

    @Field
    private String customerCode;

    @Field
    private String displayName;

    @Field
    private String status;

    @Version
    private Long version;

    public Customer() {
    }

    public Customer(
            String id,
            String tenantId,
            String customerCode,
            String displayName,
            String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.customerCode = customerCode;
        this.displayName = displayName;
        this.status = status;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public void setCustomerCode(String customerCode) {
        this.customerCode = customerCode;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Long getVersion() {
        return version;
    }

    public void setVersion(Long version) {
        this.version = version;
    }
}
```

- `@Document` cho biết đây là entity Couchbase.
- `@Id String id` chứa **document key**, độc lập với giá trị `customerCode` bên trong JSON.
- `@Scope` và `@Collection` chọn nơi ánh xạ document; bucket lấy từ cấu hình kết nối.
- `@Version` hỗ trợ optimistic locking bằng CAS trong các thao tác ghi, **không quyết định** `findById` trả `Optional` hay danh sách.

Giả định bucket, scope, collection và quyền truy cập đã được cấu hình. Việc thêm annotation không tự tạo keyspace trên server.

### 4.2. Repository khai báo theo số kết quả mong đợi

```java
package com.example.customer;

import java.util.List;
import java.util.Optional;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    // Tìm tối đa một customer theo định danh nghiệp vụ:
    Optional<Customer> findByTenantIdAndCustomerCode(
            String tenantId, String customerCode);

    // Trả 0..n customer thuộc tenant và trạng thái:
    List<Customer> findByTenantIdAndStatus(
            String tenantId, String status);

    // Trả 0..n customer thuộc tenant:
    List<Customer> findByTenantId(String tenantId);

    // Đếm customer thuộc một tenant:
    long countByTenantId(String tenantId);
}
```

Các phương thức kế thừa như `findById`, `existsById` và `findAllById` hoạt động theo document key. Các phương thức `findByTenantId...` là **derived queries**, thường thực thi bằng SQL++ và cần index phù hợp.

Khai báo `Optional<Customer> findByTenantIdAndCustomerCode(...)` thể hiện **kỳ vọng tối đa một kết quả ở tầng Java**, nhưng không tự tạo unique index/ràng buộc duy nhất cho bộ hai trường JSON. Độ duy nhất phải được bảo vệ bằng quy ước document key và thiết kế nghiệp vụ phù hợp.

## 5. `Optional<T>`: một document có thể không tồn tại

### 5.1. `findById` trả về `Optional<Customer>`

```java
String key = "customer::tenant-a::C102";
Optional<Customer> found = repository.findById(key);
```

Hai trường hợp hợp lệ:

- Key tồn tại và document ánh xạ được: `found.isPresent() == true`.
- Key không tồn tại trong collection được repository chọn: `found.isEmpty() == true`.

`Optional<Customer>` là **đối tượng bao**; chính kết quả Optional không nên là `null`. `Optional.empty()` biểu thị không có đối tượng `Customer`, không phải một `Customer` có mọi trường bằng `null`.

Đọc an toàn:

```java
Optional<Customer> found =
        repository.findById("customer::tenant-a::C102");

found.ifPresent(customer ->
        System.out.println(customer.getDisplayName()));
```

Hoặc chuyển thành kết quả nghiệp vụ bắt buộc phải tồn tại:

```java
Customer customer = repository.findById(
        "customer::tenant-a::C102")
    .orElseThrow(() ->
        new CustomerNotFoundException(
            "Không tìm thấy customer"));
```

Trong ví dụ trên, `CustomerNotFoundException` là exception do ứng dụng tự định nghĩa; mã triển khai sẽ có trong phần service.

### 5.2. Không gọi `get()` khi chưa kiểm tra

Cách viết dễ lỗi:

```java
// Có thể ném NoSuchElementException khi key không tồn tại:
Customer customer = repository.findById(key).get();
```

Thay bằng một trong các lựa chọn:

```java
// Trường hợp không tìm thấy là bình thường:
repository.findById(key)
        .ifPresent(this::processCustomer);

// Trường hợp bắt buộc phải tồn tại:
Customer customer = repository.findById(key)
        .orElseThrow(() -> new CustomerNotFoundException(key));

// Trường hợp cần chuyển đổi dữ liệu nếu có:
Optional<String> displayName = repository.findById(key)
        .map(Customer::getDisplayName);
```

Đoạn `this::processCustomer` chỉ minh họa trong một lớp có phương thức `processCustomer(Customer)`. Nếu không có phương thức đó, dùng lambda trực tiếp như ví dụ trước.

### 5.3. `orElse` khác `orElseGet`

```java
Customer fallback = new Customer(
        key, "tenant-a", "C102", "Chưa xác định", "UNKNOWN");

// fallback được tạo trước khi orElse chạy:
Customer first = repository.findById(key)
        .orElse(fallback);

// Supplier chỉ được gọi khi Optional rỗng:
Customer second = repository.findById(key)
        .orElseGet(() -> new Customer(
                key, "tenant-a", "C102",
                "Chưa xác định", "UNKNOWN"));
```

`orElse(...)` đánh giá đối số trước khi quyết định dùng hay không; `orElseGet(...)` chỉ gọi supplier khi không có giá trị. Tuy nhiên, trong tầng truy cập dữ liệu, **không nên tự tạo một customer giả** nếu nghiệp vụ thực sự cần biết rằng document không tồn tại. Dữ liệu fallback có thể phù hợp cho hiển thị, nhưng cần phân biệt với entity thực sự lưu trong Couchbase.

### 5.4. `Optional.empty()` không chứng minh customer không tồn tại ở mọi nơi

Một `findById(key)` trả Optional rỗng cho biết không tìm được document theo **key và collection hiện tại** tại thời điểm thao tác. Cần kiểm tra thêm khi kết quả bất ngờ:

- Key có đúng tiền tố và quy tắc chữ hoa/chữ thường không?
- Repository có đang ánh xạ đúng bucket, scope và collection không?
- Document có bị xóa hoặc hết hạn TTL không?
- Dữ liệu có nằm ở collection khác không?

Kết quả rỗng là thông tin đúng trong phạm vi truy cập cụ thể, không phải kết luận toàn cục rằng mã khách hàng chưa từng được lưu.

## 6. `List<T>`: truy vấn có thể trả 0 đến nhiều document

Một danh sách trả về cho phép biểu diễn cả không kết quả, một kết quả và nhiều kết quả mà không cần phân biệt kiểu.

```java
List<Customer> active = repository
        .findByTenantIdAndStatus("tenant-a", "ACTIVE");

if (active.isEmpty()) {
    System.out.println("Không có customer ACTIVE");
} else {
    for (Customer customer : active) {
        System.out.println(customer.getCustomerCode());
    }
}
```

Trong giao diện repository Spring Data, phương thức khai báo trả collection thường trả về **collection rỗng** khi không có phần tử, thay vì trả `null`. Vì vậy, cách xử lý tự nhiên là `isEmpty()` và `size()`.

| Kết quả thực tế | Giá trị của `List<Customer>` | Hành vi phù hợp |
| --- | --- | --- |
| Không có customer khớp điều kiện | `[]` | Hiển thị “Chưa có kết quả”, API trả `[]` |
| Có đúng một customer | `[customerA]` | Duyệt một phần tử |
| Có ba customer | `[customerA, customerB, customerC]` | Duyệt ba phần tử, phân trang nếu cần |
| SQL++ timeout/thiếu index | Exception | Xử lý lỗi hệ thống, **không** trả `[]` giả |

### Không biến danh sách rỗng thành “không có tenant”

Ví dụ `findByTenantIdAndStatus("tenant-a", "INACTIVE")` trả danh sách rỗng không chứng minh tenant A không tồn tại. Nó chỉ có nghĩa không tìm được customer thỏa cả **hai điều kiện** trong phạm vi và consistency của truy vấn.

Nếu API cần trả `404` khi **tenant** không tồn tại, đó là một quyết định nghiệp vụ cần có nguồn xác minh tenant riêng, không suy từ danh sách khách hàng.

### Danh sách không có thứ tự mặc định

`List` giữ thứ tự **của kết quả nhận được**, nhưng kết quả SQL++ không có `ORDER BY` không được bảo đảm ổn định. Nếu người dùng mong danh sách theo tên hoặc ngày tạo, phải sắp xếp rõ ràng trong truy vấn/repository; không dựa vào thứ tự tình cờ của index.

## 7. `Optional<T>` trong derived query: đừng bỏ qua ràng buộc số lượng

Khác với `findById` vốn nhắm đến **một key duy nhất**, derived query tìm theo trường JSON có thể khớp nhiều document.

Giả sử có hai document:

```text
customer::tenant-a::C102
imported-customer::tenant-a::C102
```

Cả hai đều chứa:

```json
{
  "tenantId": "tenant-a",
  "customerCode": "C102"
}
```

Khi gọi:

```java
Optional<Customer> result =
        repository.findByTenantIdAndCustomerCode(
                "tenant-a", "C102");
```

một phương thức được khai báo trả **tối đa một entity** có thể gặp lỗi do thực tế có **nhiều hàng khớp** (ví dụ nhóm lỗi `IncorrectResultSizeDataAccessException` tùy phiên bản/đường thực thi). Nó không nên tự động chọn document bất kỳ rồi xem là duy nhất.

**Không dùng `Optional` để tạo ràng buộc duy nhất.** Cách bảo đảm phù hợp thường là:

1. Xác định document key dựa trên cặp `tenantId` và `customerCode`, ví dụ `customer::tenant-a::C102`.
2. Khi yêu cầu chỉ tạo mới, dùng thao tác insert-only nguyên tử để từ chối key trùng.
3. Nếu chỉ cần một document đã biết key, truy cập bằng `findById(key)`.
4. Nếu phải tìm theo trường JSON, xây dựng quy tắc kiểm soát uniqueness và xử lý dữ liệu vi phạm; có thể dùng `List` khi nhiều kết quả là hợp lệ.

Trong một số API truy vấn, việc giới hạn `LIMIT 1` có thể làm kết quả chỉ còn một hàng. Nhưng điều đó **không chứng minh tính duy nhất** và không phù hợp khi nghiệp vụ yêu cầu phát hiện dữ liệu trùng.

## 8. `Iterable<T>` và truy cập nhiều ID

Các phương thức CRUD như `findAllById(Iterable<ID>)` có thể trả `Iterable<Customer>` theo hợp đồng giao diện:

```java
List<String> keys = List.of(
        "customer::tenant-a::C101",
        "customer::tenant-a::C102",
        "customer::tenant-a::C999");

Iterable<Customer> found = repository.findAllById(keys);

for (Customer item : found) {
    System.out.println(item.getId());
}
```

Nếu key `C999` không tồn tại, không có nghĩa toàn bộ lời gọi phải thất bại: tập kết quả thường chỉ chứa những document tìm thấy. Không nên mặc định thứ tự đầu ra khớp thứ tự các key đầu vào, cũng không giả định trả về một phần tử `null` tại vị trí key thiếu.

Nếu cần hiển thị đúng thứ tự yêu cầu hoặc báo ID nào không tìm thấy, hãy tạo ánh xạ từ kết quả theo `getId()` rồi đối chiếu với danh sách key đã nhập. Đối với số lượng lớn, đánh giá giới hạn batch và tài nguyên; `findAllById` không đồng nghĩa với một truy vấn SQL++ phân trang.

Ví dụ đối chiếu:

```java
import java.util.HashSet;
import java.util.Set;

Set<String> returnedIds = new HashSet<>();

for (Customer item : repository.findAllById(keys)) {
    returnedIds.add(item.getId());
}

List<String> missingKeys = keys.stream()
        .filter(key -> !returnedIds.contains(key))
        .toList();
```

`missingKeys` cho biết những key trong yêu cầu **không có trong kết quả trả về**. Nếu cần đảm bảo mọi key phải tồn tại tại một mốc nhất quán, ứng dụng phải xem xét thao tác đồng thời, TTL và chính sách truy cập dữ liệu; danh sách đối chiếu đơn thuần không tạo snapshot giao dịch.

## 9. `Page<T>`: trả về danh sách có metadata phân trang

Một repository tìm theo JSON có thể trả trang dữ liệu:

```java
package com.example.customer;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerPageRepository
        extends CouchbaseRepository<Customer, String> {

    Page<Customer> findByTenantIdAndStatus(
            String tenantId, String status, Pageable pageable);
}
```

Sử dụng:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<Customer> page = pageRepository
        .findByTenantIdAndStatus(
                "tenant-a",
                "ACTIVE",
                PageRequest.of(
                        0, 20, Sort.by("displayName").ascending()));

List<Customer> content = page.getContent();
boolean empty = page.isEmpty();
long total = page.getTotalElements();
int totalPages = page.getTotalPages();
```

`Page<Customer>` biểu diễn **một phần của tập kết quả**, đồng thời cung cấp thông tin như số phần tử trong trang và tổng số phần tử theo hợp đồng `Page`. Việc lấy tổng số bản ghi có thể yêu cầu thao tác đếm bổ sung, tùy query và implementation; cần cân nhắc chi phí với collection lớn.

**Trang rỗng** không nhất thiết có nghĩa toàn bộ tập dữ liệu rỗng: trang được yêu cầu có thể vượt quá trang cuối. Kiểm tra `page.getNumber()`, `page.getTotalElements()` và bộ lọc. Với dữ liệu biến động liên tục, tổng số và nội dung trang có thể được tính qua các bước không cùng một snapshot nếu không có cơ chế nhất quán phù hợp.

Với nhu cầu chỉ biết còn trang sau hay không, có thể cân nhắc `Slice<T>` ở những phương thức và phiên bản Spring Data Couchbase hỗ trợ; `Slice` thường tránh đòi hỏi tổng số kết quả. Đừng khai báo kiểu phân trang tùy ý trước khi xác minh implementation hỗ trợ.

### Chỉ mục phục vụ kết quả danh sách

Một index phục vụ lọc theo tenant, trạng thái và sắp xếp theo tên có thể được thiết kế như sau:

```sql
CREATE INDEX ix_customers_tenant_status_name
ON `appdata`.`sales`.`customers`(
    tenantId,
    status,
    displayName
);
```

Đây là chỉ mục minh họa cho workload cụ thể. Cần kiểm tra SQL++ query được sinh, điều kiện phân biệt kiểu entity và `EXPLAIN` để xác nhận index được optimizer sử dụng. `findById` theo key không cần secondary index này.

## 10. Không tìm thấy khác lỗi query hoặc lỗi hạ tầng

Các thao tác repository có thể gặp nhiều tình huống:

| Tình huống | Ví dụ | Cách hiểu và xử lý |
| --- | --- | --- |
| Key không tồn tại | `findById("customer::tenant-a::C999")` | `Optional.empty()` là kết quả hợp lệ |
| Không có bản ghi thỏa bộ lọc | `findByTenantIdAndStatus("tenant-a", "PAUSED")` | `List` rỗng là kết quả hợp lệ |
| Có nhiều bản ghi trong query chỉ mong một | `findByTenantIdAndCustomerCode(...)` khớp 2 document | Xử lý vi phạm cardinality; không che bằng `Optional.empty()` |
| SQL++ thiếu index | Derived query trên collection chưa có index thích hợp | Exception; kiểm tra index, query plan và quyền |
| Query timeout hoặc kết nối bị gián đoạn | Query Service/KV không trả lời kịp | Exception; xem timeout, tải, retry phù hợp |
| Không đủ quyền collection | Tài khoản không có quyền đọc | Exception phân quyền; không xem là không tồn tại |
| Mapping không đọc được JSON | Giá trị hoặc cấu trúc không ánh xạ được vào entity | Exception dữ liệu/mapping; cần sửa schema hoặc converter |
| Document hết hạn TTL | Document đã tồn tại nhưng tự hết hạn | Sau khi hết hạn, truy cập theo key có thể trả rỗng |
| Query chưa thấy document vừa ghi | Index SQL++ chưa bắt kịp | Xem scan consistency; chưa thể kết luận key không tồn tại |

### SQL++ scan consistency ảnh hưởng trường hợp “không có hàng”

Truy vấn theo thuộc tính thường dùng SQL++ và index. Couchbase có thể cập nhật index bất đồng bộ với thao tác KV ghi document. Với chế độ query **`NOT_BOUNDED`**, kết quả có thể chưa bao gồm mutation mới nhất.

Khi cần kết quả query phản ánh các thay đổi trước yêu cầu, có thể cân nhắc **`REQUEST_PLUS`** hoặc mức nhất quán theo mutation state phù hợp phiên bản SDK/Spring Data. Đổi consistency có thể làm query chậm hơn, nên cân nhắc theo nhu cầu nghiệp vụ.

Ví dụ sau có thể cho hai kết quả quan sát khác nhau ngay sau khi ghi:

```java
Customer stored = repository.save(customer);

// Truy cập KV theo key:
Optional<Customer> direct =
        repository.findById(stored.getId());

// Truy vấn SQL++ theo trường JSON:
List<Customer> byTenant =
        repository.findByTenantId(stored.getTenantId());
```

Nếu `direct` có giá trị nhưng `byTenant` chưa có phần tử tương ứng, hãy kiểm tra index/consistency trước khi khẳng định thao tác lưu không thành công.

## 11. Ánh xạ kết quả repository sang service và HTTP API

Tầng repository thể hiện sự tồn tại của **dữ liệu**; tầng service/controller quyết định cách trả lời **nghiệp vụ và HTTP**.

### 11.1. Service trả `Optional` và `List` đúng ngữ nghĩa

```java
package com.example.customer;

import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Optional<Customer> findOne(
            String tenantId, String customerCode) {
        return repository.findById(keyOf(tenantId, customerCode));
    }

    public Customer requireOne(
            String tenantId, String customerCode) {
        String id = keyOf(tenantId, customerCode);
        return repository.findById(id)
                .orElseThrow(() -> new CustomerNotFoundException(id));
    }

    public List<Customer> findActive(String tenantId) {
        requireToken(tenantId, "tenantId");
        return repository.findByTenantIdAndStatus(
                tenantId, "ACTIVE");
    }

    private static String keyOf(
            String tenantId, String customerCode) {
        requireToken(tenantId, "tenantId");
        requireToken(customerCode, "customerCode");

        return "customer::" + tenantId + "::" + customerCode;
    }

    private static void requireToken(String value, String name) {
        if (value == null || value.isBlank()
                || value.contains("::")) {
            throw new IllegalArgumentException(
                    name + " không hợp lệ");
        }
    }
}
```

Exception nghiệp vụ:

```java
package com.example.customer;

public class CustomerNotFoundException extends RuntimeException {
    public CustomerNotFoundException(String id) {
        super("Không tìm thấy customer theo key: " + id);
    }
}
```

Ở môi trường thật, cân nhắc không đưa key có dữ liệu nhạy cảm vào phản hồi public hoặc log. Với nhiều tenant, phải kiểm tra quyền truy cập của người dùng vào tenant được yêu cầu trước khi gọi repository; prefix tenant trong key không tự cung cấp phân quyền.

### 11.2. HTTP: một tài nguyên và một danh sách có ý nghĩa khác nhau

Một API REST thường có thể chọn:

| Endpoint minh họa | Trường hợp | Phản hồi phù hợp |
| --- | --- | --- |
| `GET /customers/C102` (tenant lấy từ ngữ cảnh đã xác thực) | Tìm được | `200 OK` với JSON của customer |
| `GET /customers/C999` | Không tồn tại | `404 Not Found` |
| `GET /customers?status=ACTIVE` | Có kết quả | `200 OK` với mảng các customer |
| `GET /customers?status=ACTIVE` | Không có kết quả | `200 OK` với `[]` |
| Bất kỳ endpoint nào | Lỗi truy cập dữ liệu | Mã lỗi phù hợp, thường nhóm `5xx`, không trá hình thành `404` hay `[]` |

Đây là **chính sách thiết kế API thường gặp**, không phải hành vi tự động của Spring Data Couchbase. Repository trả kiểu Java; controller quyết định HTTP status, cấu trúc phản hồi và cách ghi log. Không nhất thiết trả `404` cho một truy vấn danh sách rỗng.

### 11.3. Tránh che giấu exception

Không nên:

```java
public Optional<Customer> unsafeFind(String id) {
    try {
        return repository.findById(id);
    } catch (Exception error) {
        return Optional.empty(); // Che giấu mọi lỗi thành "không có"!
    }
}
```

Với cách này, timeout, lỗi xác thực hoặc lỗi ánh xạ đều được báo như “customer chưa tồn tại”, gây khó điều tra và có thể khiến nghiệp vụ tạo trùng dữ liệu khi thử lại.

Hãy để exception được xử lý ở tầng error handler có phân loại, ghi nhận ngữ cảnh vận hành phù hợp và quyết định retry chỉ với lỗi có thể retry an toàn.

## 12. Reactive: `Mono<T>` và `Flux<T>` biểu diễn sự vắng mặt

Khi chọn API reactive để tránh chặn thread trong ứng dụng WebFlux, Spring Data Couchbase có `ReactiveCouchbaseRepository`. Cách biểu diễn số kết quả thay đổi:

| Đồng bộ | Reactive | Không có phần tử |
| --- | --- | --- |
| `Optional<Customer>` | `Mono<Customer>` | `Mono.empty()` — hoàn tất không phát giá trị |
| `List<Customer>` | `Flux<Customer>` | `Flux.empty()` — không phát phần tử |
| `List<Customer>` sau khi gom dữ liệu | `Mono<List<Customer>>` từ `collectList()` | Phát **một danh sách rỗng** |
| Lỗi truy vấn | Publisher phát tín hiệu `onError` | Không phải `empty()` |

Repository minh họa:

```java
package com.example.customer;

import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    Flux<Customer> findByTenantIdAndStatus(
            String tenantId, String status);

    Mono<Customer> findByTenantIdAndCustomerCode(
            String tenantId, String customerCode);
}
```

Sử dụng:

```java
Mono<Customer> one = reactiveRepository.findById(
        "customer::tenant-a::C102");

Flux<Customer> active = reactiveRepository
        .findByTenantIdAndStatus("tenant-a", "ACTIVE");

// Khi không có kết quả, Mono<List<Customer>>
// vẫn phát ra một danh sách rỗng:
Mono<List<Customer>> activeAsList = active.collectList();

// Chuyển Mono.empty thành một lỗi nghiệp vụ:
Mono<Customer> required = one.switchIfEmpty(
        Mono.error(new CustomerNotFoundException(
                "customer::tenant-a::C102")));
```

**Phân biệt tín hiệu:**

```text
Mono<Customer> có dữ liệu:
    onNext(customer) → onComplete

Mono<Customer> không có dữ liệu:
    onComplete

Mono<Customer> lỗi:
    onError(exception)

Flux<Customer> không có dữ liệu:
    onComplete

Flux<Customer>.collectList() khi rỗng:
    onNext([]) → onComplete
```

Trong Reactor, `Mono.empty()` và `Flux.empty()` là publisher hoàn thành hợp lệ; không tương đương với lỗi `onError`. Cần xử lý lỗi qua toán tử thích hợp như `onErrorResume` khi có chính sách nghiệp vụ rõ ràng, tránh `onErrorReturn` một giá trị giả cho mọi lỗi.

Tránh gọi `block()` bên trong request pipeline reactive. Đặc tính KV, SQL++, index, consistency, CAS và TTL vẫn áp dụng; reactive thay đổi cách phối hợp bất đồng bộ, không làm query tự nhanh hay tự nhất quán.

## 13. Các lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Cách khắc phục |
| --- | --- | --- |
| `repository.findById(id).get()` ngay lập tức | `NoSuchElementException` khi không có dữ liệu | Dùng `map`, `ifPresent`, `orElseThrow` phù hợp |
| Tìm danh sách rồi trả `null` khi rỗng | Client luôn phải kiểm tra thêm null | Trả tập hợp rỗng theo hợp đồng |
| Bắt tất cả exception rồi trả `Optional.empty()` | Che lỗi hạ tầng thành "không tồn tại" | Phân loại exception riêng |
| Dùng `Optional<Customer>` cho query có thể khớp nhiều bản ghi | Không rõ cardinality và dữ liệu trùng | Dùng `List` hoặc bảo đảm uniqueness |
| Dùng `findById("C102")` khi key thực tế có prefix | Không tìm đúng document | Tạo document key thống nhất |
| Giả định `List` có thứ tự mặc định | Kết quả không ổn định | Khai báo ORDER BY hoặc Sort |
| `findAll()` rồi lọc hàng triệu document trong Java | Tốn tải dữ liệu và bộ nhớ | SQL++ WHERE + index + phân trang |
| SQL++ trả rỗng ngay sau ghi, kết luận dữ liệu đã mất | Chưa xét độ trễ cập nhật index | Kiểm tra KV và scan consistency |
| Xem `404` là kết quả bắt buộc cho mọi danh sách rỗng | Nhầm giữa truy vấn tập hợp và tài nguyên đơn | Thiết kế API phản hồi `[]` rõ ràng |
| Reactive `switchIfEmpty` trên `Mono<List<T>>` mà list rỗng | `Mono` vẫn có giá trị là `[]` | Kiểm tra `list.isEmpty()` sau `collectList()` |
| Thấy `Optional.empty()` sau một thời gian và kết luận chưa từng tồn tại | Document có thể đã bị xóa hoặc hết hạn TTL | Kiểm tra lịch sử và expiration |
| Xử lý `Optional` đúng nhưng cập nhật bằng bản cũ | Không tránh được lost update | Dùng `@Version`/CAS trong thao tác ghi |

## 14. Bài thực hành

Trong Couchbase thử nghiệm, chuẩn bị bucket `appdata`, scope `sales` và collection `customers` với các document sau:

| Document key | tenantId | customerCode | status |
| --- | --- | --- | --- |
| `customer::tenant-a::C101` | tenant-a | C101 | ACTIVE |
| `customer::tenant-a::C102` | tenant-a | C102 | ACTIVE |
| `customer::tenant-a::C103` | tenant-a | C103 | INACTIVE |
| `customer::tenant-b::C102` | tenant-b | C102 | ACTIVE |

Thực hiện:

1. Gọi `findById("customer::tenant-a::C102")` và kiểm tra `Optional.isPresent()`.
2. Gọi `findById("customer::tenant-a::C999")`; xác nhận `Optional.empty()`, rồi thử `orElseThrow` với exception nghiệp vụ.
3. Gọi `findByTenantIdAndStatus("tenant-a", "ACTIVE")`; xác nhận trả hai customer. Sau đó gọi với `"PAUSED"` và kiểm tra danh sách rỗng.
4. Kiểm tra `findAllById` với ba key, trong đó có một key chưa tồn tại; đối chiếu các ID trả về và key bị thiếu.
5. Thử `Page<Customer>` khi trang số 0 có dữ liệu và một trang vượt quá giới hạn; phân biệt `page.isEmpty()` với tổng số kết quả.
6. Quan sát derived query khi index SQL++ chưa có hoặc không phù hợp, và xác nhận lỗi không bị chuyển thành danh sách rỗng.
7. Trong reactive repository, so sánh `Mono.empty()` với `Flux.empty().collectList()` và sự khác biệt giữa `onComplete` và `onError`.

Mở rộng: tạo hai document có key khác nhau nhưng cùng `tenantId` và `customerCode`, gọi phương thức mong đợi một kết quả. Quan sát hành vi khi query khớp nhiều hàng, sau đó thiết kế lại quy tắc định danh/uniqueness để tránh dữ liệu mơ hồ. Thực hành này chỉ nên dùng dữ liệu thử nghiệm.

## 15. Câu hỏi tự kiểm tra

1. `Optional.empty()` khác `null` và khác exception như thế nào?
2. Vì sao `findById` với document key thường phù hợp với `Optional<Customer>`?
3. Vì sao `Optional<Customer> findByTenantIdAndCustomerCode(...)` không đảm bảo cặp trường JSON duy nhất?
4. `List<Customer>` rỗng có nghĩa là tenant không tồn tại hay chỉ không có bản ghi thỏa điều kiện?
5. Vì sao query SQL++ có thể trả rỗng ngay sau khi document vừa được lưu thành công?
6. Khi dùng `Page<Customer>`, một trang rỗng có nhất thiết đồng nghĩa tổng số customer là 0 không?
7. Trong Reactor, khác biệt giữa `Mono.empty()` và `Mono.just(List.of())` là gì?
8. Với API REST, khi nào nên dùng `404` và khi nào nên trả `200` cùng mảng rỗng?
9. Vì sao không nên bắt mọi exception từ Couchbase và thay bằng `Optional.empty()`?

## 16. Ghi nhớ

**`Optional<T>` phù hợp khi mong tối đa một kết quả; `List<T>` và các kiểu tập hợp phù hợp khi có thể có nhiều kết quả; `Page<T>` dùng khi cần phân trang và metadata.** Khi không có document, trả kiểu rỗng tương ứng với hợp đồng phương thức, không đánh đồng với lỗi hạ tầng hoặc vi phạm cardinality.

Trong Spring Data Couchbase, `findById` theo **document key** có ngữ nghĩa khác derived query theo **trường JSON** qua SQL++. Vì vậy, kết quả rỗng còn cần được hiểu trong bối cảnh bucket/scope/collection, TTL, chỉ mục và scan consistency. Khi mở rộng sang reactive, `Mono.empty()`/`Flux.empty()` tiếp tục biểu diễn **không có phần tử**, còn lỗi phải đi theo luồng `onError`. Những nguyên tắc này giúp tầng repository, service và API giao tiếp rõ ràng, nhất quán và dễ vận hành.
