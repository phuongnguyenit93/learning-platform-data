# Định nghĩa `CouchbaseRepository` và kiểu khóa của entity

Trong module **SPRING_DATA_COUCHBASE**, Spring Data Couchbase đóng vai trò tầng truy cập dữ liệu giữa ứng dụng Java và Couchbase. Để dùng repository đúng cách, cần phân biệt **kiểu ID trong Java**, **document key trong Couchbase** và **các thuộc tính nằm trong nội dung JSON**. Đây là nền tảng cho document mapping, truy vấn SQL++, lựa chọn bucket/scope/collection, kiểm soát nhất quán bằng CAS và các API đồng bộ hoặc reactive.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Khai báo một entity bằng `@Document`, đánh dấu khóa bằng `@Id` và định nghĩa repository bằng `CouchbaseRepository<Entity, ID>`.
- Giải thích vì sao `ID` trong repository phải tương ứng với kiểu của thuộc tính `@Id` và vì sao `String` thường là lựa chọn rõ ràng nhất cho Couchbase document key.
- Thiết kế khóa ổn định, duy nhất, có tiền tố theo loại tài liệu và ngữ cảnh nghiệp vụ.
- Phân biệt thao tác theo document key với truy vấn theo thuộc tính JSON; nhận biết các lỗi về trùng khóa, đổi khóa và nhầm ID với trường nghiệp vụ.

## 2. `CouchbaseRepository` là gì?

`CouchbaseRepository<T, ID>` là interface repository của Spring Data Couchbase. Ứng dụng tự định nghĩa một interface kế thừa nó; Spring Data tạo implementation tại thời điểm chạy và cung cấp những thao tác dữ liệu quen thuộc như:

| Phương thức | Ý nghĩa | Đối tượng được xác định bằng |
| --- | --- | --- |
| `save(entity)` | Lưu document từ entity, đồng thời xử lý trường hợp document có khóa đã tồn tại theo quy tắc ghi và version đang dùng. | Giá trị `@Id` của entity |
| `findById(id)` | Tìm một document theo khóa; trả về `Optional<T>`. | Document key |
| `existsById(id)` | Kiểm tra sự tồn tại của khóa. | Document key |
| `deleteById(id)` | Xóa document có khóa tương ứng. | Document key |
| `findAll()` | Lấy nhiều document thuộc repository; phải cân nhắc chi phí truy vấn và chỉ mục. | Truy vấn tập tài liệu |

Cú pháp tổng quát:

```java
public interface TenRepository
        extends CouchbaseRepository<LoaiEntity, KieuId> {
}
```

- `LoaiEntity` là kiểu Java được ánh xạ thành document.
- `KieuId` là kiểu Java của thuộc tính gắn `@Id`.
- Các phương thức tự khai báo như `findByTenantId(...)` được Spring Data phân tích tên để tạo truy vấn. Đây là kiểu truy cập khác với đọc trực tiếp bằng `findById(...)`.

**Điểm cốt lõi:** `findById("customer::tenant-a::C102")` truy cập theo **document key**. Nó không có nghĩa là tìm một trường JSON có tên `id` hoặc tìm mọi document có `customerCode = "C102"`.

## 3. Document key khác thuộc tính JSON như thế nào?

Trong Couchbase, mỗi document có một **key duy nhất trong collection** và một phần **value** chứa dữ liệu JSON. Key là định danh được Couchbase dùng cho các thao tác key-value (KV).

Ví dụ một document được lưu trong bucket `appdata`, scope `sales`, collection `customers`:

```text
Document key:
customer::tenant-a::C102
```

Nội dung JSON minh họa (lược bỏ các trường metadata do framework có thể thêm):

```json
{
  "tenantId": "tenant-a",
  "customerCode": "C102",
  "displayName": "Lan Anh"
}
```

Trong ví dụ này:

- `customer::tenant-a::C102` là **document key**, được ánh xạ từ thuộc tính `@Id`.
- `tenantId`, `customerCode` và `displayName` là **trường nội dung** để lọc, hiển thị hoặc xử lý nghiệp vụ.
- Key không mặc nhiên là một trường JSON thông thường. Nếu cần tìm theo `customerCode`, hãy lưu và đánh chỉ mục cho trường nghiệp vụ đó; không giả định Couchbase sẽ truy vấn được key qua một thuộc tính JSON `id`.
- Tính duy nhất của key nằm trong phạm vi **collection**. Cùng chuỗi key có thể tồn tại trong các collection khác nhau.

Một customer có thể đổi `displayName` mà vẫn giữ nguyên key. Trái lại, thay đổi giá trị `@Id` khiến đối tượng Java trỏ tới **một key khác**; lưu đối tượng đó không tự động đổi tên document cũ.

## 4. Khai báo entity với `@Id` kiểu `String`

Ví dụ dưới đây dùng Spring Data Couchbase theo mô hình Spring Boot hiện đại. Giả sử bucket `appdata` đã được cấu hình, còn scope `sales` và collection `customers` đã tồn tại trên Couchbase.

```java
package com.example.customer;

import org.springframework.data.annotation.Id;
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

    public Customer() {
    }

    public Customer(
            String id,
            String tenantId,
            String customerCode,
            String displayName) {
        this.id = id;
        this.tenantId = tenantId;
        this.customerCode = customerCode;
        this.displayName = displayName;
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
}
```

Vai trò của từng annotation:

| Annotation | Vai trò |
| --- | --- |
| `@Document` | Đánh dấu lớp được Spring Data Couchbase quản lý như một document. |
| `@Id` | Chỉ ra thuộc tính chứa document key. Dùng `org.springframework.data.annotation.Id`, không nhầm với `jakarta.persistence.Id` của JPA. |
| `@Field` | Đánh dấu các thuộc tính được ánh xạ vào phần dữ liệu document. |
| `@Scope("sales")` | Chỉ định scope đích của entity. |
| `@Collection("customers")` | Chỉ định collection đích của entity. |

Khi không khai báo scope/collection cụ thể, cấu hình mặc định của ứng dụng quyết định đích lưu. Annotation chỉ mô tả ánh xạ: nó **không thay thế** việc tạo bucket, scope, collection và cấp quyền truy cập trên máy chủ.

### Vì sao thường dùng `String` cho khóa?

Couchbase document key về bản chất là một chuỗi. Dùng `String` cho thuộc tính `@Id` giúp biểu diễn chính xác key được gửi qua API và tránh việc dựa vào chuyển đổi kiểu ngầm định.

| Nhu cầu | Cách thiết kế nên cân nhắc | Lý do |
| --- | --- | --- |
| Khóa có ngữ nghĩa nghiệp vụ và cần ổn định | `String id = "customer::tenant-a::C102"` | Dễ tạo, đọc và tra cứu bằng key |
| Mã khách hàng là số `102` | `String id = "customer::102"`; có thể giữ `Long customerNumber` riêng | Phân biệt định danh document với kiểu dữ liệu nghiệp vụ |
| Cần ID ngẫu nhiên | `String id = "customer::" + UUID.randomUUID()` | Có key duy nhất mà không phụ thuộc mã khách hàng |
| Muốn framework tự sinh ID | Cấu hình chiến lược sinh ID do Spring Data Couchbase hỗ trợ, thay vì chỉ để `id = null` rồi mặc định sẽ có key | Tránh giả định entity luôn được tự cấp key |

Có thể tồn tại cơ chế chuyển đổi ID khác tùy phiên bản và converter được cấu hình, nhưng một dự án nên chọn **một quy ước thống nhất**. Khi dùng `String` trong entity, hãy dùng `String` trong repository và ở mọi lời gọi `findById` / `deleteById`.

## 5. Định nghĩa `CustomerRepository`

```java
package com.example.customer;

import java.util.List;
import java.util.Optional;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    List<Customer> findByTenantId(String tenantId);

    Optional<Customer> findByTenantIdAndCustomerCode(
            String tenantId, String customerCode);
}
```

Cách đọc `CouchbaseRepository<Customer, String>`:

- `Customer`: entity mà repository thao tác.
- `String`: kiểu của `Customer.id` có `@Id`.
- `CustomerRepository`: interface do ứng dụng cung cấp, không cần tự viết implementation CRUD cơ bản.

Trong ứng dụng Spring Boot đã cài Spring Data Couchbase, cấu hình kết nối và đặt repository trong vùng package được Spring quét, một bean repository sẽ được tạo tự động. Với cấu hình đặc thù hoặc nhiều nguồn dữ liệu, có thể cần thiết lập repository scanning rõ ràng.

Hai phương thức `findByTenantId` và `findByTenantIdAndCustomerCode` đọc theo **thuộc tính nội dung**, vì thế thông thường cần truy vấn SQL++ cùng chỉ mục phù hợp cho collection. Chúng không có đặc tính đọc trực tiếp theo key như `findById`. Không nên mặc định rằng mọi phương thức repository đều dùng KV hoặc có cùng chi phí truy cập.

### Lỗi khai báo kiểu ID không khớp

```java
// KHÔNG đúng với Customer.id là String:
public interface WrongCustomerRepository
        extends CouchbaseRepository<Customer, Long> {
}
```

Ở đây phương thức kế thừa `findById` nhận `Long`, trong khi entity khai báo `@Id String id`. Sai lệch có thể bộc lộ khi chạy thông qua ánh xạ hoặc chuyển đổi ID; không nên trông đợi trình biên dịch luôn phát hiện.

Nguyên tắc:

```text
Entity:      @Id private String id;
Repository:  CouchbaseRepository<Customer, String>
Call site:   repository.findById("customer::tenant-a::C102");
```

## 6. Thiết kế document key dễ bảo trì

Một quy ước khóa hữu ích cho hệ thống nhiều tenant là:

```text
<entity-type>::<tenant-id>::<business-id>
customer::tenant-a::C102
customer::tenant-b::C102
```

Quy ước này giúp đọc tên khóa, giảm nguy cơ va chạm giữa loại tài liệu, và tách khách hàng cùng mã nghiệp vụ nhưng thuộc tenant khác nhau. Tuy nhiên, tiền tố trong key **không phải** cơ chế phân quyền: backend vẫn phải kiểm tra tenant của người gọi trước khi đọc hoặc ghi document.

Khi tạo key, cần bảo đảm:

1. **Duy nhất trong collection:** hai entity không được vô tình chia sẻ cùng key.
2. **Ổn định:** không sử dụng tên hiển thị, email hay thuộc tính thường thay đổi nếu thay đổi đó không có chủ đích tạo document mới.
3. **Có quy ước chuẩn hóa:** xác định rõ chữ hoa/chữ thường, khoảng trắng và ký tự phân cách. Nếu dùng `::` làm dấu phân cách, cần cấm hoặc mã hóa `::` trong từng thành phần để tránh key mơ hồ.
4. **Không chứa dữ liệu nhạy cảm không cần thiết:** key có thể xuất hiện trong log, chỉ số theo dõi hoặc công cụ vận hành.
5. **Đủ ngắn và hợp lệ:** kiểm tra ràng buộc document key của phiên bản Couchbase đang triển khai.

Nếu doanh nghiệp có mã khách hàng không ổn định, hãy dùng một ID bất biến (ví dụ UUID biểu diễn bằng chuỗi) làm document key, rồi lưu mã khách hàng như thuộc tính JSON được đánh chỉ mục.

## 7. Sử dụng repository trong service

Service dưới đây dùng **cùng một hàm tạo key** cho lưu, đọc và xóa để tránh mỗi nơi ghép khóa theo một kiểu.

```java
package com.example.customer;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    public Customer saveCustomer(
            String tenantId,
            String customerCode,
            String displayName) {

        String id = documentKey(tenantId, customerCode);
        Customer entity =
                new Customer(id, tenantId, customerCode, displayName);

        return customers.save(entity);
    }

    public Optional<Customer> getCustomer(
            String tenantId, String customerCode) {

        return customers.findById(documentKey(tenantId, customerCode));
    }

    public boolean customerExists(
            String tenantId, String customerCode) {

        return customers.existsById(documentKey(tenantId, customerCode));
    }

    public void deleteCustomer(
            String tenantId, String customerCode) {

        customers.deleteById(documentKey(tenantId, customerCode));
    }

    private String documentKey(String tenantId, String customerCode) {
        if (tenantId == null || tenantId.isBlank()
                || customerCode == null || customerCode.isBlank()) {
            throw new IllegalArgumentException(
                    "tenantId và customerCode không được rỗng");
        }

        if (tenantId.contains("::") || customerCode.contains("::")) {
            throw new IllegalArgumentException(
                    "Thành phần khóa không được chứa '::'");
        }

        return "customer::" + tenantId + "::" + customerCode;
    }
}
```

Giả sử gọi:

```java
service.saveCustomer("tenant-a", "C102", "Lan Anh");

Optional<Customer> result =
        service.getCustomer("tenant-a", "C102");
```

Giá trị truyền vào `findById` là `"customer::tenant-a::C102"`. Nếu document không tồn tại, `result` là `Optional.empty()`. Không cần viết SQL++ chỉ để đọc theo document key.

**Lưu ý về ghi dữ liệu:** `save(...)` là cách lưu tổng quát; với cùng key, nó có thể ghi lên document đã có theo cơ chế mapping và version. Nếu nghiệp vụ yêu cầu "tạo mới và báo lỗi khi key đã tồn tại", hãy dùng thao tác **insert-only có tính nguyên tử** phù hợp của Couchbase/Spring Data Couchbase. Mẫu `existsById(...)` rồi `save(...)` **không** bảo đảm duy nhất khi có nhiều request đồng thời, vì document có thể được tạo trong khoảng giữa hai lời gọi.

## 8. ID, CAS và tính nhất quán là các khái niệm riêng

Document key cho biết **document nào** đang được truy cập. CAS (Compare-And-Swap) giúp kiểm tra **phiên bản dữ liệu nào** đang được cập nhật. Không dùng CAS làm document key.

Trong Spring Data Couchbase có thể dùng `@Version` để tham gia cơ chế optimistic locking:

```java
import org.springframework.data.annotation.Version;

// Bổ sung vào Customer nếu cần optimistic locking:
@Version
private Long version;
```

Khi entity mang thông tin version phù hợp, Spring Data có thể phát hiện việc document đã bị luồng khác thay đổi trước lúc lưu và báo lỗi optimistic locking. Việc cấu hình/kiểm thử chính xác phụ thuộc vào phiên bản framework và đường ghi dữ liệu. Quy tắc thiết kế vẫn là:

- `@Id`: định danh ổn định của document.
- `@Version`: thông tin kiểm soát ghi đồng thời (gắn với CAS), không phải ID nghiệp vụ.
- TTL: quy tắc hết hạn document, độc lập với kiểu generic `ID` của repository.

Với thao tác read–modify–write quan trọng, cần chủ động chọn chiến lược CAS/optimistic locking hoặc giao dịch phù hợp, thay vì giả định `save` tự tránh mọi xung đột.

## 9. Phân biệt các thao tác và lỗi thường gặp

| Tình huống | Hiểu đúng / cách xử lý |
| --- | --- |
| `repository.findById("C102")` không tìm thấy khách hàng | Document key thực tế là `customer::tenant-a::C102`. Phải truyền **toàn bộ key**. |
| Đổi `customerCode` trong JSON nhưng giữ nguyên `id` | Document vẫn ở key cũ. Cần quy tắc đồng bộ key/thuộc tính nếu chúng cùng biểu diễn mã nghiệp vụ. |
| Đổi `id` từ `customer::tenant-a::C102` thành `customer::tenant-a::C103` rồi gọi `save` | Đây là key khác; document cũ không tự bị xóa hay đổi tên. Di chuyển document cần quy trình riêng. |
| Hai tenant dùng `customerCode = "C102"` | Dùng key bao gồm tenant hoặc ID toàn cục; kiểm tra phân quyền tenant độc lập với cách đặt key. |
| Khai báo `@Id String id` nhưng repository là `CouchbaseRepository<Customer, Long>` | Kiểu ID không khớp; sửa generic thành `String` hoặc thiết kế lại mapping có chủ đích. |
| `findByTenantId(...)` chạy chậm hoặc báo thiếu index | Đây thường là truy vấn SQL++ dựa trên trường JSON. Xem lại index, scope/collection và execution plan. |
| Gọi `findAll()` trên collection lớn để tìm một customer | Đọc theo key bằng `findById`, hoặc dùng truy vấn SQL++ có điều kiện/chỉ mục khi tìm theo trường khác. |
| Trùng key khi thêm khách hàng | Phân biệt upsert với insert-only; dùng thao tác ghi nguyên tử khi nghiệp vụ yêu cầu không ghi đè. |

## 10. Kiểm tra triển khai

Sau khi cấu hình kết nối, bucket và quyền truy cập, hãy xác minh theo thứ tự:

1. Tạo `Customer("customer::tenant-a::C102", "tenant-a", "C102", "Lan Anh")`, sau đó gọi `repository.save(customer)`.
2. Dùng `repository.findById("customer::tenant-a::C102")` và kiểm tra các trường nghiệp vụ nhận về.
3. Dùng `repository.findById("customer::tenant-a::C999")` để xác nhận không tồn tại được biểu diễn bằng `Optional.empty()`.
4. Dùng `repository.existsById(...)` và `deleteById(...)` để kiểm tra tác động của việc xóa đúng key trong môi trường thử nghiệm.
5. Nếu gọi `findByTenantId("tenant-a")`, tạo và kiểm tra chỉ mục phục vụ truy vấn SQL++ trên đúng collection; quan sát execution plan thay vì giả định đây là KV lookup.
6. Thử cùng `customerCode` ở hai tenant với **hai key khác nhau** và xác minh không bị ghi đè lẫn nhau.

Các kiểm tra này là hướng dẫn thực hành; kết quả chỉ có ý nghĩa khi chạy trên Couchbase thật hoặc môi trường tích hợp phù hợp.

## Ghi nhớ

Đối với `CouchbaseRepository<Customer, String>`, tham số `String` phải thống nhất với `@Id String id` trong `Customer`. `@Id` ánh xạ **document key**, còn các trường như `customerCode` hoặc `tenantId` thuộc phần JSON và có thể cần chỉ mục SQL++ để tìm kiếm. Chọn key ổn định và duy nhất ngay từ đầu giúp repository dễ sử dụng, hạn chế ghi đè ngoài ý muốn và chuẩn bị tốt cho những chủ đề tiếp theo về query, CAS, TTL và giao dịch trong Spring Data Couchbase.
