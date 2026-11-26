# Tra cứu theo trường đơn và nhiều trường kết hợp

Trong **SPRING_DATA_COUCHBASE**, *derived query* cho phép khai báo điều kiện tìm document ngay trong tên phương thức repository. Bài học thuộc chương **Truy vấn dẫn xuất** và tập trung vào hai nhu cầu phổ biến: **tra cứu theo một trường** và **kết hợp nhiều trường** bằng `And`, `Or`, toán tử so sánh và tập giá trị.

Ở Couchbase, cú pháp Java chỉ là lớp biểu diễn yêu cầu. Khi thực thi, Spring Data Couchbase dựa trên **document mapping** để ánh xạ thuộc tính Java sang trường JSON, tạo truy vấn **SQL++** chạy trên bucket/scope/collection, và sử dụng **index** để tìm dữ liệu. Vì vậy hiệu năng và độ nhất quán của kết quả còn chịu ảnh hưởng từ mô hình lưu trữ, TTL và cập nhật index. Tầng truy cập cũng có thể cần CAS, giao dịch và API reactive trong các luồng nghiệp vụ liên quan.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Viết `findByEmail`, `findByStatus` và giải thích điều kiện lọc trên một trường.
2. Viết `findByStatusAndCity`, `findByStatusOrCity`, phân tích ý nghĩa logic và thứ tự tham số.
3. Kết hợp bằng nhau với `GreaterThan`, `Between`, `In`; tra cứu theo property lồng nhau.
4. Phân biệt truy vấn theo ID với truy vấn theo thuộc tính document.
5. Chọn kiểu trả về, sắp xếp và phân trang phù hợp với quy mô tập kết quả.
6. Kiểm tra index, dữ liệu `NULL`/`MISSING` và consistency khi truy vấn ngay sau khi ghi.
7. Chọn `@Query` hoặc `CouchbaseTemplate` khi tên phương thức không thể biểu đạt rõ điều kiện.

## 2. Ví dụ dữ liệu và entity dùng xuyên suốt

Giả sử ứng dụng CRM sử dụng bucket `app`, scope `crm` và collection `customers`. Mỗi document lưu thông tin cơ bản của khách hàng:

```json
{
  "email": "lan@example.test",
  "status": "ACTIVE",
  "city": "HANOI",
  "loyalty_points": 120,
  "created_at": "2026-09-01T10:00:00Z"
}
```

Một document có thể mang ID riêng, chẳng hạn `customer::1001`; ID là metadata khóa của document và không nhất thiết xuất hiện thành trường `id` trong nội dung JSON.

Khai báo Java:

```java
package example.crm;

import java.time.Instant;
import org.springframework.data.annotation.Id;
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

    @Field
    private String email;

    @Field
    private String status;

    @Field
    private String city;

    @Field("loyalty_points")
    private Integer loyaltyPoints;

    @Field("created_at")
    private Instant createdAt;

    protected Customer() {
        // Cho cơ chế document mapping.
    }

    // Constructor nghiệp vụ và getters/setters được lược bỏ.
}
```

Repository:

```java
package example.crm;

import java.util.List;
import java.util.Optional;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {

    Optional<Customer> findByEmail(String email);
    List<Customer> findByStatus(String status);
    List<Customer> findByCity(String city);

    List<Customer> findByStatusAndCity(String status, String city);
    List<Customer> findByStatusOrCity(String status, String city);

    List<Customer> findByStatusAndLoyaltyPointsGreaterThan(
        String status, Integer minPoints
    );

    List<Customer> findByStatusAndCityIn(
        String status, java.util.Collection<String> cities
    );

    Page<Customer> findByStatusAndCity(
        String status, String city, Pageable pageable
    );

    long countByStatusAndCity(String status, String city);
    boolean existsByEmail(String email);
}
```

Hai phiên bản `findByStatusAndCity` hợp lệ vì khác số lượng tham số: phương thức phân trang nhận thêm `Pageable`.

**Quy tắc mapping:** Tên phương thức dùng property Java `loyaltyPoints` và `createdAt`, dù trong JSON tên là `loyalty_points` và `created_at`. Spring Data xử lý ánh xạ này. Không chèn tên trường vật lý vào tên phương thức một cách máy móc.

## 3. Tra cứu theo một trường

### 3.1. Điều kiện bằng nhau

```java
List<Customer> findByStatus(String status);
```

Lời gọi:

```java
List<Customer> active = repository.findByStatus("ACTIVE");
```

được hiểu là lấy các khách hàng có `status` bằng `ACTIVE`. Có thể hình dung điều kiện SQL++:

```sql
-- Minh họa điều kiện, không phải bản sao SQL++ framework sinh ra.
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = $status;
```

Spring Data Couchbase có thể bổ sung projection metadata và điều kiện phân biệt kiểu entity, tùy cấu hình/phiên bản. Dữ liệu đầu vào được binding như tham số của truy vấn; không nên tự ghép trực tiếp chuỗi do người dùng cung cấp vào SQL++.

Các phương thức `findByEmail`, `findByCity` hoạt động theo cùng nguyên tắc lọc trường bằng giá trị tham số.

### 3.2. Tra cứu dự kiến duy nhất với `Optional`

```java
Optional<Customer> maybeCustomer =
    repository.findByEmail("lan@example.test");
```

Kết quả có thể là `Optional.empty()` (không có document) hoặc một `Customer`. Tuy nhiên, **email không mặc nhiên là khóa duy nhất**: secondary index trên `email` chỉ phục vụ tra cứu, không tự đảm bảo uniqueness. Nếu hai document cùng email, kiểu đơn trị có thể gây lỗi vì nhiều kết quả hơn kỳ vọng. Phải có quy tắc nghiệp vụ và thao tác ghi phù hợp để đảm bảo tính duy nhất nếu ứng dụng phụ thuộc vào giả định này.

### 3.3. Tìm theo ID khác với tìm theo trường

| Tác vụ | Phương thức | Đặc điểm |
| --- | --- | --- |
| Tìm theo document ID | `findById("customer::1001")` | Thường dùng truy cập **key-value** theo khóa. |
| Tìm theo email | `findByEmail("lan@example.test")` | Truy vấn theo nội dung document, thường dùng **SQL++ và index**. |
| Tìm mọi document có status | `findByStatus("ACTIVE")` | Truy vấn theo trường nội dung, có thể trả rất nhiều document. |

Biết document ID thì ưu tiên `findById` cho trường hợp lấy một document theo khóa. Một tên phương thức `findByEmail` vẫn là truy vấn trường ngay cả khi có document được đặt ID trùng với email.

## 4. Kết hợp hai hoặc nhiều trường bằng `And`

Phương thức:

```java
List<Customer> findByStatusAndCity(String status, String city);
```

Lời gọi:

```java
List<Customer> customers =
    repository.findByStatusAndCity("ACTIVE", "HANOI");
```

thể hiện điều kiện:

```sql
WHERE c.`status` = "ACTIVE"
  AND c.`city` = "HANOI"
```

Hai điều kiện phải **đồng thời đúng**. Thứ tự tham số Java tương ứng với thứ tự các property trong tên phương thức. Ví dụ truyền `("HANOI", "ACTIVE")` vẫn có thể hợp lệ về kiểu dữ liệu nhưng sẽ lọc nhầm `status = "HANOI"` và `city = "ACTIVE"`.

Một ví dụ kết hợp ba điều kiện:

```java
List<Customer> findByStatusAndCityAndLoyaltyPointsGreaterThan(
    String status, String city, Integer points
);
```

Đọc là: `status = ? AND city = ? AND loyalty_points > ?`.

### 4.1. Kết hợp điều kiện bằng với so sánh

| Yêu cầu | Dạng tên phương thức |
| --- | --- |
| Khách hàng ACTIVE có trên 100 điểm | `findByStatusAndLoyaltyPointsGreaterThan` |
| Khách hàng ACTIVE có điểm dưới ngưỡng | `findByStatusAndLoyaltyPointsLessThan` |
| Khách hàng tại HANOI có điểm trong khoảng | `findByCityAndLoyaltyPointsBetween` |
| Khách hàng có status thuộc tập giá trị | `findByStatusIn` |
| Khách hàng ACTIVE thuộc một trong nhiều thành phố | `findByStatusAndCityIn` |

Để minh họa cú pháp đầy đủ:

```java
List<Customer> findByCityAndLoyaltyPointsBetween(
    String city, Integer min, Integer max
);

List<Customer> findByStatusIn(
    java.util.Collection<String> statuses
);
```

`GreaterThan` **không bao gồm** giá trị đúng bằng ngưỡng. Nếu nghiệp vụ muốn `>=`, cần sử dụng từ khóa tương đương được Spring Data Couchbase hỗ trợ trong phiên bản ứng dụng (ví dụ `GreaterThanEqual`). Một số từ khóa của Spring Data nói chung có thể khác khả năng hỗ trợ hoặc cách diễn giải trong từng data module; phải thử những biến thể ít phổ biến trên đúng phiên bản đang chạy.

### 4.2. `In` không phải `Or` theo nhiều trường

```java
List<Customer> selected = repository.findByStatusAndCityIn(
    "ACTIVE",
    java.util.List.of("HANOI", "DANANG")
);
```

Ý nghĩa: `status = "ACTIVE" AND city IN ["HANOI", "DANANG"]`.

Phương thức trên chỉ dùng một điều kiện `status`, còn `city` nằm trong tập. Nếu **cả hai trường** đều phải thuộc hai tập thì tên phù hợp về ý định là `findByStatusInAndCityIn(...)`, với hai tham số kiểu collection.

Tại tầng service, cần xác định rõ cách xử lý tập rỗng:

- Danh sách rỗng nghĩa là **không có giá trị nào được chọn** → có thể trả kết quả rỗng mà không cần gọi repository.
- Danh sách rỗng nghĩa là **không áp dụng bộ lọc thành phố** → nên gọi biến thể chỉ lọc status.

Không nên mặc định `IN []` hoặc collection tham số `null` sẽ luôn có một hành vi thuận tiện và giống nhau ở mọi phiên bản.

## 5. Tra cứu bằng `Or` và nhóm điều kiện

```java
List<Customer> findByStatusOrCity(String status, String city);
```

```java
List<Customer> customers =
    repository.findByStatusOrCity("ACTIVE", "HANOI");
```

Ý nghĩa: lấy khách hàng ở trạng thái ACTIVE **hoặc** cư trú tại HANOI. Một document chỉ cần đáp ứng một trong hai điều kiện.

Dữ liệu ví dụ:

| ID | Status | City | Điểm thưởng |
| --- | --- | --- | ---: |
| `c1` | ACTIVE | HANOI | 120 |
| `c2` | ACTIVE | HCM | 40 |
| `c3` | SUSPENDED | HANOI | 230 |
| `c4` | SUSPENDED | DANANG | 80 |
| `c5` | ACTIVE | DANANG | 300 |

Đối chiếu:

| Lời gọi | Tập ID kỳ vọng |
| --- | --- |
| `findByCity("HANOI")` | `{c1, c3}` |
| `findByStatus("ACTIVE")` | `{c1, c2, c5}` |
| `findByStatusAndCity("ACTIVE", "HANOI")` | `{c1}` |
| `findByStatusOrCity("ACTIVE", "HANOI")` | `{c1, c2, c3, c5}` |
| `findByStatusAndLoyaltyPointsGreaterThan("ACTIVE", 100)` | `{c1, c5}` |

Các bảng mô tả **tập kết quả**. Không có `OrderBy` hoặc `Sort` thì không được giả định thứ tự trả về ổn định.

### 5.1. Kết hợp `And` với `Or`

Xét phương thức:

```java
List<Customer> findByStatusAndCityOrStatusAndCity(
    String firstStatus, String firstCity,
    String secondStatus, String secondCity
);
```

Spring Data phân tích mỗi nhóm `And` thành một nhánh của `Or`. Cách diễn giải:

```text
(status = firstStatus AND city = firstCity)
OR
(status = secondStatus AND city = secondCity)
```

Với lời gọi:

```java
repository.findByStatusAndCityOrStatusAndCity(
    "ACTIVE", "HANOI", "SUSPENDED", "DANANG"
);
```

kết quả theo bảng là `{c1, c4}`.

Cần phân biệt yêu cầu **status = ACTIVE AND (city = HANOI OR city = DANANG)**. Trong trường hợp này, dùng `findByStatusAndCityIn("ACTIVE", List.of("HANOI", "DANANG"))` rõ ràng hơn. Khi biểu thức có nhiều dấu ngoặc và các nhánh phức tạp, tên phương thức không còn là phương tiện tốt để mô tả chính xác nghiệp vụ; nên viết `@Query` với SQL++ tường minh.

## 6. Trường lồng nhau và mapping tên JSON

Giả sử document có object lồng nhau:

```json
{
  "status": "ACTIVE",
  "address": {
    "city": "HANOI",
    "district": "CAU_GIAY"
  }
}
```

Nếu entity chứa property `address` và object đó có property `city`, đường dẫn có thể được diễn đạt trong tên phương thức bằng cơ chế phân tích property lồng nhau của Spring Data:

```java
public class Address {
    private String city;
    private String district;
    // Constructor, getters/setters.
}

@Document
public class CustomerWithAddress {
    @Id
    private String id;

    @Field
    private String status;

    @Field
    private Address address;

    // Constructor, getters/setters.
}
```

Repository ví dụ:

```java
List<CustomerWithAddress> findByStatusAndAddress_City(
    String status, String city
);
```

Dấu gạch dưới `_` trong tên phương thức là **dấu tách đường dẫn property tường minh** (`address.city`), giúp tránh mơ hồ nếu entity cũng có property `addressCity`. Trong khi đó, dấu gạch dưới của `@Field("loyalty_points")` chỉ là ký tự trong tên trường JSON. Hai trường hợp không được nhầm với nhau.

Với truy vấn trên mảng, object sâu hoặc điều kiện SQL++ đặc thù, không nên mặc định tên phương thức luôn đủ biểu đạt. Kiểm thử mapping, SQL++ sinh ra và khả năng hỗ trợ của phiên bản Spring Data Couchbase đang dùng.

## 7. Chọn kiểu trả về và giới hạn tập kết quả

| Kiểu/trạng thái | Khi thích hợp | Điểm cần chú ý |
| --- | --- | --- |
| `Optional<Customer>` | Kỳ vọng tối đa một document. | Nhiều kết quả có thể gây lỗi. |
| `List<Customer>` | Trả một tập kết quả nhỏ hoặc đã được giới hạn. | Không tự an toàn với collection lớn. |
| `long countBy...` | Chỉ cần số lượng document. | Tránh tải entity về chỉ để đếm. |
| `boolean existsBy...` | Chỉ kiểm tra có ít nhất một kết quả. | Không bảo đảm uniqueness khi ghi. |
| `Page<Customer>` | Màn hình cần dữ liệu từng trang và tổng số. | Có thể phát sinh thêm truy vấn count. |

Sắp xếp cố định có thể viết:

```java
List<Customer> findByStatusAndCityOrderByCreatedAtDesc(
    String status, String city
);
```

Đọc là lọc `status` và `city` trước, sắp theo `createdAt` giảm dần. Dùng property Java `createdAt` dù JSON lưu `created_at`.

Với phân trang động:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<Customer> page = repository.findByStatusAndCity(
    "ACTIVE",
    "HANOI",
    PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.DESC, "createdAt")
    )
);

List<Customer> rows = page.getContent();
long total = page.getTotalElements();
```

`PageRequest` đếm từ trang **0**. Nếu nhiều document có cùng `createdAt`, các trang có thể không ổn định về thứ tự; nên có thêm khóa sắp xếp phụ phân biệt document khi yêu cầu kết quả ổn định. Offset rất sâu và truy vấn đếm trên tập lớn có chi phí đáng kể; cần đo trên dữ liệu thực tế.

## 8. Index cho tra cứu đơn và nhiều trường

Các truy vấn `findByEmail`, `findByStatusAndCity` thường chạy qua **Query Service**, đòi hỏi index SQL++ phù hợp để tối ưu hoặc thậm chí để lập kế hoạch truy vấn thành công.

Nếu Spring Data đang thêm điều kiện loại entity qua trường `_class`, một số index **minh họa**:

```sql
CREATE INDEX ix_customers_type_email
ON `app`.`crm`.`customers`(`_class`, `email`);

CREATE INDEX ix_customers_type_status_city
ON `app`.`crm`.`customers`(`_class`, `status`, `city`);

CREATE INDEX ix_customers_type_status_points
ON `app`.`crm`.`customers`(`_class`, `status`, `loyalty_points`);
```

Đây là những ví dụ có điều kiện, **không phải lệnh bắt buộc tạo đồng loạt**. Truy vấn Spring Data thực tế có thể thay đổi điều kiện type discriminator, cách lấy metadata và tên trường. Nếu ứng dụng không dùng `_class`, index phải được thiết kế lại tương ứng.

### 8.1. Index kết hợp và tiền tố

Một index theo `(_class, status, city)` có thể hiệu quả khi truy vấn lọc `_class` và `status`, có hoặc không có điều kiện `city`. Ngược lại, truy vấn **chỉ theo city** có thể không tận dụng hiệu quả index này nếu thiếu điều kiện theo `status`. Đường truy cập thường xuyên theo `city` đơn lẻ có thể cần index khác.

| Mẫu truy vấn | Hướng thiết kế index |
| --- | --- |
| Theo email | Ưu tiên đường tra cứu theo `email` (và discriminator nếu có). |
| Theo status và city | Composite index hỗ trợ các equality predicates tương ứng. |
| Theo status và điểm lớn hơn ngưỡng | Equality theo status, range theo `loyalty_points`. |
| Theo status/city và thứ tự tạo | Xem xét `created_at` cùng tiêu chí lọc/sắp xếp. |
| Điều kiện `status OR city` | Kiểm tra từng nhánh và khả năng chọn index trong kế hoạch thực thi. |

Index mới làm tăng chi phí ghi và vận hành. Tái sử dụng index khi phù hợp; tránh tạo một index riêng cho mọi phương thức repository.

### 8.2. Dùng `EXPLAIN`

```sql
EXPLAIN
SELECT c.*
FROM `app`.`crm`.`customers` AS c
WHERE c.`status` = "ACTIVE"
  AND c.`city` = "HANOI";
```

Đây là câu SQL++ minh họa. Khi đánh giá thật, cần lấy câu SQL++ Spring Data sinh ra, kể cả discriminator và projection, để phân tích index có được chọn không, có bước quét rộng hay sắp xếp tốn kém không. Một `PRIMARY INDEX` có thể giúp chạy truy vấn tổng quát nhưng không phải lựa chọn tối ưu mặc định cho các đường truy cập sản xuất.

## 9. Những trường hợp dễ sai khi lọc nhiều trường

### 9.1. `NULL` khác `MISSING`

Ba document sau có ý nghĩa khác nhau:

```json
{"city": null}
```

```json
{}
```

```json
{"city": ""}
```

Ở SQL++, trường có `NULL` khác với trường **không tồn tại** (`MISSING`), và chuỗi rỗng là một giá trị riêng. Một điều kiện `city = "HANOI"` sẽ không chọn các document trên.

Không nên mặc định từ khóa `IsNull` của derived query đồng thời tìm cả `MISSING`. Nếu nghiệp vụ cần tách biệt trạng thái thiếu trường, giá trị null và chuỗi rỗng, phải kiểm tra SQL++ sinh ra hoặc khai báo câu SQL++ có `IS NULL`/`IS MISSING` chính xác.

### 9.2. Kiểu dữ liệu phải đồng nhất

Nếu một document lưu `"loyalty_points": "120"` (chuỗi) thay vì số `120`, bộ lọc so sánh numeric có thể trả khác kỳ vọng. Mapper Java không thể tự sửa điều kiện mà Query Service đang thực thi trên JSON trước khi entity được ánh xạ. Chuẩn hóa dữ liệu khi ghi và kiểm thử các trường hợp sai kiểu.

### 9.3. Vừa ghi xong nhưng `findBy...` chưa thấy document

```text
save(customer)       -> hoàn tất ghi key-value
findById(id)         -> có thể thấy ngay theo document ID
findByEmail(email)   -> truy vấn SQL++ qua index có thể chưa thấy ngay
```

Chỉ mục có quá trình cập nhật riêng. Nếu nghiệp vụ cần **read-your-own-write** khi tìm bằng trường nội dung, hãy xem xét mức query scan consistency thích hợp (chẳng hạn dạng `REQUEST_PLUS` nếu phiên bản/API cho phép), hoặc đọc lại theo ID. Mức nhất quán mạnh hơn có thể làm tăng thời gian chờ; tránh áp dụng mặc định cho mọi truy vấn.

### 9.4. TTL, CAS, transaction

- **TTL:** Document hết hạn có thể biến mất khỏi lần truy vấn tiếp theo dù các điều kiện `And`/`Or` không đổi.
- **CAS/optimistic locking:** Tìm thấy document không đồng nghĩa có quyền ghi đè an toàn. Khi sửa theo kết quả tra cứu, cần cơ chế phát hiện xung đột cập nhật.
- **Giao dịch:** Chuỗi `findBy...` rồi `save(...)` không tự trở thành giao dịch nguyên tử; cần thiết kế giao dịch theo các API được hỗ trợ nếu nghiệp vụ yêu cầu.

Các yếu tố này thuộc tầng lưu trữ và nhất quán, không phải phần mở rộng ngầm của tên phương thức.

## 10. Truy vấn động và lúc nên dùng API khác

Derived query phù hợp với số ít bộ lọc ổn định. Khi nhiều bộ lọc tùy chọn được kết hợp theo request, số tổ hợp tăng nhanh và tên repository sẽ quá dài. Ví dụ yêu cầu:

```sql
WHERE c.`status` = "ACTIVE"
  AND (
      c.`city` = "HANOI"
      OR c.`loyalty_points` >= 500
  )
```

Đây là logic có nhóm ngoặc tường minh. Nếu không thể diễn đạt rõ bằng `In` hay một nhóm điều kiện nhỏ, ưu tiên `@Query` để kiểm soát SQL++, hoặc `CouchbaseTemplate` khi cần lắp ghép bộ lọc động. Những tình huống như `JOIN`, `UNNEST`, nhóm kết quả và projection phức tạp cũng phù hợp hơn với truy vấn tường minh.

Trong `@Query` cần dùng cú pháp SQL++ và binding của **Spring Data Couchbase**. Không thể sao chép trực tiếp truy vấn JPQL của Spring Data JPA sang Couchbase.

## 11. Dùng cùng điều kiện trong repository reactive

Tên phương thức vẫn biểu diễn bộ lọc như nhau, nhưng API reactive dùng các kiểu Reactor:

```java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatusAndCity(String status, String city);

    Flux<Customer> findByStatusAndLoyaltyPointsGreaterThan(
        String status, Integer points
    );
}
```

`Mono<Customer>` đại diện tối đa một khách hàng, `Flux<Customer>` đại diện nhiều khách hàng. API reactive không loại bỏ yêu cầu về index hoặc độ mới của chỉ mục SQL++. Tránh gọi `block()` ngay trên chuỗi xử lý web reactive nếu không có lý do kiến trúc phù hợp.

## 12. Bài thực hành: đọc tập kết quả trước khi viết code

Dùng dữ liệu `c1`–`c5` ở mục 5. Hãy viết phương thức cho các yêu cầu sau và đối chiếu kết quả:

**Bài A.** Tìm tất cả khách hàng tại HANOI.

```java
List<Customer> findByCity(String city);
```

Gọi `findByCity("HANOI")` → mong đợi `{c1, c3}`.

**Bài B.** Tìm khách hàng ACTIVE tại HANOI.

```java
List<Customer> findByStatusAndCity(String status, String city);
```

Gọi `findByStatusAndCity("ACTIVE", "HANOI")` → mong đợi `{c1}`.

**Bài C.** Tìm khách hàng ACTIVE có hơn 100 điểm tích lũy.

```java
List<Customer> findByStatusAndLoyaltyPointsGreaterThan(
    String status, Integer points
);
```

Gọi `findByStatusAndLoyaltyPointsGreaterThan("ACTIVE", 100)` → mong đợi `{c1, c5}`.

**Bài D.** Chỉ lấy khách hàng ACTIVE ở HANOI hoặc DANANG.

```java
List<Customer> findByStatusAndCityIn(
    String status, java.util.Collection<String> cities
);
```

Gọi `findByStatusAndCityIn("ACTIVE", List.of("HANOI", "DANANG"))` → mong đợi `{c1, c5}`. So sánh với `findByStatusOrCity("ACTIVE", "HANOI")` để thấy lý do `Or` giữa hai trường có thể trả về nhiều document hơn yêu cầu.

**Bài kiểm thử biên:** Thêm `c6` với `status = "ACTIVE"`, `city = "HANOI"`, `loyalty_points = 100`. Kết quả `findByStatusAndCity` phải có `c6`, còn `GreaterThan("ACTIVE", 100)` phải loại `c6`. Nếu truy vấn ngay sau khi ghi, đảm bảo chính sách consistency trước khi kết luận logic lọc sai.

### Checklist kiểm thử

| Kiểm tra | Câu hỏi cần trả lời |
| --- | --- |
| Mapping | Tên property Java đã đúng với entity và `@Field` chưa? |
| Logic | `And`, `Or`, `In` có phản ánh đúng nhóm điều kiện không? |
| Tham số | Thứ tự tham số đã đúng với tên phương thức chưa? |
| Kiểu trả về | Có đảm bảo 0..1 khi dùng `Optional` không? |
| Sắp xếp | Có `Sort`/`OrderBy` khi cần thứ tự ổn định không? |
| Index | Có index phục vụ đường truy cập, đã kiểm tra `EXPLAIN` chưa? |
| Dữ liệu đặc biệt | Đã thử `NULL`, `MISSING`, chuỗi rỗng, sai kiểu, tập rỗng chưa? |
| Tính nhất quán | Sau khi ghi, có chấp nhận độ trễ index không? |

## 13. Ghi nhớ

Tra cứu theo trường đơn giúp định nghĩa bộ lọc gọn bằng `findBy<Property>`; kết hợp nhiều trường bằng `And`, `Or` và các phép so sánh để biểu diễn nghiệp vụ thường gặp. Thiết kế đúng đòi hỏi **tên property Java**, **thứ tự tham số**, **cách nhóm điều kiện**, **kiểu trả về** và **index** phù hợp. Trong Spring Data Couchbase, mỗi truy vấn còn chịu ảnh hưởng của collection đích, cấu trúc document JSON và query consistency. Khi bộ lọc trở nên nhiều nhánh hoặc thay đổi động, viết SQL++ tường minh qua `@Query` hay `CouchbaseTemplate` để có logic dễ kiểm soát và kế hoạch index rõ ràng hơn.
