# Truy vấn exists, count và lựa chọn phép toán phù hợp

## 1. Ba nhu cầu truy vấn khác nhau

Khi làm việc với dữ liệu bằng Spring Data R2DBC, không phải lúc nào ứng dụng cũng cần tải một entity. Nhiều use case chỉ cần biết một điều kiện có thỏa mãn hay không, hoặc cần một con số tổng hợp.

Ba nhu cầu phổ biến là:

- **Existence:** kiểm tra có ít nhất một bản ghi thỏa điều kiện hay không.
- **Count:** đếm số bản ghi thỏa điều kiện.
- **Read:** lấy entity hoặc projection khi ứng dụng thực sự cần dữ liệu của bản ghi.

Chọn đúng phép toán giúp database chỉ phải trả về thông tin cần thiết. Nếu chỉ cần biết email đã được dùng hay chưa, tải toàn bộ `Customer` là không cần thiết. Nếu cần hiển thị tổng số đơn hàng, lấy tất cả đơn hàng về Java rồi đếm sẽ tạo thêm lưu lượng mạng và bộ nhớ.

Trong Spring Data R2DBC, các phương thức repository reactive thường trả về `Mono<Boolean>`, `Mono<Long>` hoặc `Flux<T>`. Publisher mô tả kết quả bất đồng bộ; thao tác truy vấn được thực hiện khi publisher được subscribe.

## 2. Kiểm tra tồn tại bằng ReactiveCrudRepository

`ReactiveCrudRepository<T, ID>` cung cấp sẵn hai phương thức quan trọng:

```java
Mono<Boolean> existsById(ID id);
Mono<Long> count();
```

`existsById` phát ra `true` nếu có entity với ID tương ứng, hoặc `false` nếu không có. `count()` phát ra tổng số entity mà repository quản lý.

Ví dụ repository:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, UUID> {
}
```

Sử dụng:

```java
Mono<Boolean> customerExists = customerRepository.existsById(customerId);

Mono<Long> customerCount = customerRepository.count();
```

Kiểu trả về là `Mono` vì kết quả được cung cấp theo giao thức reactive. Với `existsById`, publisher hoàn tất bằng một giá trị boolean. Với `count`, publisher hoàn tất bằng một giá trị số đếm, kể cả khi không có bản ghi thì giá trị là `0`.

Không nên nhầm `Mono.empty()` với kết quả không tồn tại. `existsById` biểu diễn trường hợp không tìm thấy bằng `false`; `count()` biểu diễn bảng không có bản ghi bằng `0`. `Mono.empty()` thường là cách biểu diễn không có phần tử của một truy vấn tìm entity như `findById`.

## 3. Derived query: existsBy và countBy

Ngoài phương thức có sẵn, Spring Data R2DBC hỗ trợ tạo truy vấn từ tên phương thức repository. Các tiền tố `exists…By` và `count…By` biểu đạt rõ mục đích truy vấn.

Ví dụ:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, UUID> {

    Mono<Boolean> existsByEmail(String email);

    Mono<Boolean> existsByEmailAndStatus(String email, String status);

    Mono<Long> countByStatus(String status);

    Mono<Long> countByStatusAndCountryCode(String status, String countryCode);
}
```

Tên thuộc tính trong phương thức derived query phải tương ứng với thuộc tính Java của entity, không nhất thiết là tên cột vật lý trong database.

Ví dụ entity:

```java
@Table("customer")
public class Customer {

    @Id
    private UUID id;

    @Column("email_address")
    private String email;

    private String status;

    @Column("country_code")
    private String countryCode;
}
```

Vì entity có thuộc tính `email`, phương thức dùng `existsByEmail`. Spring Data dựa trên mapping metadata để ánh xạ thuộc tính đó tới cột `email_address`.

### 3.1. existsBy không tải entity về ứng dụng

Ví dụ:

```java
Mono<Boolean> exists = customerRepository.existsByEmail("lan@example.com");
```

Ý nghĩa của truy vấn là kiểm tra có bản ghi nào có email tương ứng hay không. Spring Data tạo truy vấn existence phù hợp với dialect và phiên bản đang dùng. Ứng dụng chỉ nhận kết quả boolean thay vì một `Customer` đầy đủ.

Đây là lựa chọn phù hợp cho các kiểm tra như:

- Email hoặc mã khách hàng đã được sử dụng chưa.
- Đơn hàng có tồn tại trước khi thực hiện một thao tác không.
- Có bản ghi nào đang ở trạng thái cần xử lý hay không.
- Người dùng có bản ghi liên quan đáp ứng một điều kiện hay không.

### 3.2. countBy đếm bản ghi theo điều kiện

Ví dụ:

```java
Mono<Long> activeCustomers = customerRepository.countByStatus("ACTIVE");
```

Phương thức này trả về số khách hàng có `status` bằng `ACTIVE`. Kiểu `Long` phù hợp với kiểu đếm SQL thường được trả về là số nguyên lớn; không nên dùng `Integer` nếu số bản ghi có thể vượt phạm vi của nó.

Các điều kiện có thể được kết hợp theo khả năng query derivation của Spring Data, ví dụ `countByStatusAndCountryCode`. Nếu điều kiện truy vấn phức tạp, có join, biểu thức đặc thù hoặc cần tối ưu SQL riêng, hãy dùng `@Query` hoặc `DatabaseClient`.

## 4. Phân biệt exists, count và find

| Nhu cầu nghiệp vụ | Phép toán nên cân nhắc | Kiểu trả về thường gặp |
| --- | --- | --- |
| Chỉ cần biết có bản ghi hay không | `existsBy...` | `Mono<Boolean>` |
| Cần biết tổng số bản ghi | `count()` hoặc `countBy...` | `Mono<Long>` |
| Cần lấy một entity theo ID | `findById(...)` | `Mono<Entity>` |
| Cần lấy nhiều entity | `findAll()` hoặc `findBy...` | `Flux<Entity>` |
| Cần một vài cột cho màn hình/báo cáo | Projection hoặc truy vấn SQL riêng | `Mono<DTO>` hoặc `Flux<DTO>` |

Ví dụ không nên tải entity chỉ để kiểm tra tồn tại:

```java
// Không cần thiết nếu chỉ cần true/false
Mono<Boolean> exists = customerRepository.findById(customerId)
        .map(customer -> true)
        .defaultIfEmpty(false);
```

Nên dùng:

```java
Mono<Boolean> exists = customerRepository.existsById(customerId);
```

Truy vấn `findById` có thể phải đọc và ánh xạ các cột của entity. Truy vấn existence chỉ cần trả lời điều kiện tồn tại. Nếu đã có publisher `Flux<T>` và muốn biết nó có phần tử hay không, Reactor cung cấp `hasElements()`, nhưng với một use case repository rõ ràng thì phương thức `existsBy...` thường thể hiện ý định tốt hơn.

## 5. EXISTS ở mức SQL

Trong SQL, `EXISTS` kiểm tra xem một subquery có trả về ít nhất một hàng hay không. Database chỉ cần xác định có hàng phù hợp; nội dung các cột trong hàng không phải là kết quả mà ứng dụng cần.

Ví dụ PostgreSQL:

```sql
SELECT EXISTS (
    SELECT 1
    FROM customer
    WHERE email_address = $1
) AS present;
```

Kết quả là một giá trị boolean. `SELECT 1` là quy ước thường dùng trong subquery EXISTS vì giá trị cụ thể không quan trọng; điều quan trọng là subquery có hàng hay không.

Database optimizer có thể dừng việc tìm kiếm khi tìm thấy một hàng phù hợp. Tuy nhiên, hiệu quả thực tế còn phụ thuộc execution plan, index, thống kê và điều kiện lọc. Không nên hiểu rằng mọi truy vấn `EXISTS` luôn chỉ đọc đúng một dòng vật lý hoặc luôn nhanh bất kể schema.

### 5.1. Dùng DatabaseClient cho truy vấn EXISTS

Khi cần SQL tường minh hoặc truy vấn đặc thù, có thể dùng `DatabaseClient`. Ví dụ dưới đây dành cho PostgreSQL:

```java
public Mono<Boolean> customerEmailExists(
        DatabaseClient databaseClient,
        String email) {

    return databaseClient.sql("""
            SELECT EXISTS (
                SELECT 1
                FROM customer
                WHERE email_address = :email
            ) AS present
            """)
            .bind("email", email)
            .map((row, metadata) -> row.get("present", Boolean.class))
            .one();
}
```

Giá trị `email` được bind như tham số, không nối trực tiếp vào SQL. Tên marker và cách biểu diễn boolean phụ thuộc driver/dialect; ví dụ này dùng cú pháp marker được `DatabaseClient` hỗ trợ và kiểu boolean của PostgreSQL.

Nếu không có yêu cầu SQL riêng, derived query `existsByEmail` thường ngắn gọn và giúp Spring Data quản lý việc tạo truy vấn.

### 5.2. EXISTS kết hợp nhiều điều kiện

Ví dụ kiểm tra có đơn hàng đang chờ xử lý của một khách hàng:

```sql
SELECT EXISTS (
    SELECT 1
    FROM purchase_order
    WHERE customer_id = $1
      AND status = 'PENDING'
) AS present;
```

Ở repository, có thể biểu diễn bằng phương thức derived tương ứng nếu điều kiện phù hợp:

```java
Mono<Boolean> existsByCustomerIdAndStatus(UUID customerId, String status);
```

Với điều kiện phức tạp hơn, SQL tường minh có thể dễ đọc và kiểm soát hơn tên phương thức quá dài.

## 6. COUNT ở mức SQL

`COUNT` là hàm tổng hợp trả về số lượng. Một truy vấn tổng số khách hàng:

```sql
SELECT COUNT(*) AS total
FROM customer;
```

Đếm khách hàng đang hoạt động:

```sql
SELECT COUNT(*) AS total
FROM customer
WHERE status = 'ACTIVE';
```

Trong PostgreSQL, kết quả `COUNT` là `bigint`. Vì vậy, ở Java nên nhận bằng `Long`:

```java
public Mono<Long> countActiveCustomers(DatabaseClient databaseClient) {
    return databaseClient.sql("""
            SELECT COUNT(*) AS total
            FROM customer
            WHERE status = :status
            """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> row.get("total", Long.class))
            .one();
}
```

### 6.1. COUNT(*) và COUNT(column)

Hai cách đếm sau có ý nghĩa khác nhau:

```sql
SELECT COUNT(*) FROM customer;
SELECT COUNT(phone_number) FROM customer;
```

- `COUNT(*)` đếm tất cả hàng trong tập kết quả, bao gồm hàng có cột nullable là `NULL`.
- `COUNT(phone_number)` chỉ đếm hàng mà `phone_number` không phải `NULL`.

Nếu câu hỏi là “có bao nhiêu khách hàng?”, thường dùng `COUNT(*)`. Nếu câu hỏi là “có bao nhiêu khách hàng đã cung cấp số điện thoại?”, `COUNT(phone_number)` có thể phù hợp.

### 6.2. COUNT(DISTINCT ...)

`COUNT(DISTINCT column)` đếm số giá trị khác nhau, bỏ qua NULL theo quy tắc SQL:

```sql
SELECT COUNT(DISTINCT country_code) AS country_count
FROM customer;
```

Đây là số quốc gia/mã vùng khác nhau có trong dữ liệu, không phải tổng số khách hàng.

### 6.3. Đếm sau JOIN

Khi JOIN một bảng cha với bảng con có quan hệ một-nhiều, một bản ghi cha có thể xuất hiện nhiều hàng trong tập kết quả. Khi đó `COUNT(*)` có thể đếm số cặp join thay vì số entity cha.

Ví dụ:

```sql
SELECT COUNT(*)
FROM customer c
JOIN purchase_order o ON o.customer_id = c.id;
```

Truy vấn trên đếm số hàng join, về thực tế là số đơn hàng có khách hàng tương ứng. Nếu cần đếm số khách hàng có ít nhất một đơn hàng, dùng:

```sql
SELECT COUNT(DISTINCT c.id)
FROM customer c
JOIN purchase_order o ON o.customer_id = c.id;
```

Hoặc biểu diễn trực tiếp bằng EXISTS:

```sql
SELECT COUNT(*)
FROM customer c
WHERE EXISTS (
    SELECT 1
    FROM purchase_order o
    WHERE o.customer_id = c.id
);
```

Chọn cách viết theo ý nghĩa cần đếm và execution plan thực tế. `COUNT(DISTINCT ...)` có thể cần thêm công việc loại trùng; EXISTS có thể phù hợp hơn khi chỉ cần biết có quan hệ hay không.

## 7. Vì sao không nên dùng count để thay exists?

Một cách viết có thể hoạt động nhưng không diễn đạt đúng nhu cầu:

```java
Mono<Boolean> exists = customerRepository.countByEmail(email)
        .map(count -> count > 0);
```

Nếu chỉ cần biết có bản ghi, đếm toàn bộ số hàng phù hợp là nhiều thông tin hơn cần thiết. Database có thể phải xác định tổng số hàng khớp, trong khi existence chỉ cần xác định có ít nhất một hàng.

Nên viết:

```java
Mono<Boolean> exists = customerRepository.existsByEmail(email);
```

Tương tự, không nên tải tất cả hàng về rồi mới đếm:

```java
// Đọc toàn bộ entity qua driver và đếm trong ứng dụng
Mono<Long> count = customerRepository.findAll().count();
```

Nếu cần tổng số bản ghi trong database, dùng:

```java
Mono<Long> count = customerRepository.count();
```

`findAll().count()` là toán tử Reactor trên một `Flux`: nó tiêu thụ các phần tử mà nguồn phát ra rồi đếm trong pipeline. Nó không tự biến thành câu SQL `COUNT(*)`. Cách này có thể truyền nhiều dữ liệu qua driver, thực hiện mapping entity không cần thiết và tăng thời gian xử lý.

## 8. Chọn phép toán theo câu hỏi nghiệp vụ

Một số ví dụ lựa chọn:

| Câu hỏi nghiệp vụ | Cách làm phù hợp | Lý do |
| --- | --- | --- |
| Email đã được đăng ký chưa? | `existsByEmail` | Chỉ cần boolean |
| Đơn hàng có tồn tại trước khi hủy không? | `existsById` hoặc `findById` nếu cần trạng thái | Nếu chỉ kiểm tra tồn tại thì không cần tải entity |
| Có bao nhiêu đơn hàng đang mở? | `countByStatus` | Cần số lượng chính xác |
| Cần hiển thị thông tin đơn hàng | `findById` | Cần dữ liệu entity |
| Cần danh sách 20 khách hàng mới nhất | Query có sort/limit hoặc truy vấn phù hợp | Cần một tập con bản ghi |
| Có khách hàng nào chưa xác minh không? | `existsByVerifiedFalse` nếu query derivation phù hợp | Chỉ cần biết có hay không |
| Có bao nhiêu mã quốc gia khác nhau? | `COUNT(DISTINCT country_code)` | Cần số lượng giá trị phân biệt |

Hãy bắt đầu bằng câu hỏi nghiệp vụ, sau đó chọn kiểu kết quả tối thiểu đáp ứng yêu cầu. Tránh chọn `findAll` theo thói quen rồi xử lý ở Java khi database có thể trả lời trực tiếp.

## 9. Kết hợp exists với luồng nghiệp vụ reactive

Ví dụ đăng ký khách hàng và kiểm tra email:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> register(String email, String name) {
        return repository.existsByEmail(email)
                .flatMap(exists -> {
                    if (exists) {
                        return Mono.error(
                                new EmailAlreadyRegisteredException(email));
                    }

                    Customer customer = new Customer();
                    customer.setEmail(email);
                    customer.setName(name);
                    return repository.save(customer);
                });
    }
}
```

Luồng trên thực hiện kiểm tra tồn tại rồi mới tạo entity. `flatMap` được dùng vì nhánh tạo mới trả về `Mono<Customer>`. Không cần `block()` để lấy boolean trước khi gọi `save`.

### 9.1. Kiểm tra tồn tại trước khi insert có race condition

Đoạn code trên hữu ích để đưa ra thông báo thân thiện, nhưng không đủ để bảo đảm email là duy nhất. Có thể xảy ra tình huống:

1. Request A kiểm tra email và nhận `false`.
2. Request B gần như đồng thời kiểm tra cùng email và cũng nhận `false`.
3. Cả hai request đều cố gắng insert.
4. Nếu schema không có unique constraint, hai hàng trùng email có thể được lưu.

Vì vậy, tính duy nhất phải được bảo vệ ở database:

```sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_email UNIQUE (email_address);
```

Database là nơi có thể bảo vệ invariant duy nhất trước các thao tác ghi đồng thời. Ứng dụng vẫn có thể gọi `existsByEmail` trước để phản hồi sớm, nhưng phải xử lý lỗi unique constraint khi insert vì một request khác có thể thắng cuộc đua.

Trong Spring, lỗi vi phạm unique constraint thường được chuyển thành một loại `DataIntegrityViolationException` hoặc exception cụ thể theo driver/translator. Cần xác định lỗi constraint nào đang xảy ra trước khi chuyển thành `EmailAlreadyRegisteredException`; không nên biến mọi lỗi database thành thông báo “email đã tồn tại”.

Với PostgreSQL, có thể cân nhắc `INSERT ... ON CONFLICT` để xử lý thao tác duy nhất một cách nguyên tử. Đây là cú pháp riêng của PostgreSQL; nếu sử dụng, hãy đặt nó trong repository/custom persistence adapter và xử lý kết quả theo hợp đồng rõ ràng.

### 9.2. Exists không thay thế authorization

Một truy vấn `existsById` chỉ trả lời bản ghi có tồn tại hay không. Nó không xác nhận người dùng hiện tại có quyền đọc hoặc sửa bản ghi đó. Khi kiểm tra quyền, cần kết hợp owner, tenant, trạng thái và chính sách truy cập trong truy vấn hoặc logic domain phù hợp.

Ví dụ, chỉ kiểm tra `existsById(orderId)` rồi cho phép sửa có thể tạo lỗ hổng nếu người dùng có thể đoán ID của đơn hàng người khác. Có thể cần truy vấn `existsByIdAndCustomerId` hoặc tải aggregate và kiểm tra quyền theo ngữ cảnh xác thực.

## 10. Count trong các quy tắc giới hạn

Một số use case cần đếm để kiểm tra giới hạn, ví dụ khách hàng chỉ được tạo tối đa 5 địa chỉ giao hàng:

```java
public Mono<Long> countAddresses(UUID customerId) {
    return addressRepository.countByCustomerId(customerId);
}
```

Application service có thể so sánh kết quả với giới hạn:

```java
return addressRepository.countByCustomerId(customerId)
        .flatMap(count -> {
            if (count >= 5) {
                return Mono.error(new AddressLimitExceededException());
            }

            return addressRepository.save(newAddress);
        });
```

Đây là cách minh họa logic nhưng vẫn có race condition. Hai request cùng đếm được 4 địa chỉ rồi cùng insert có thể làm tổng thành 6. Nếu giới hạn là invariant bắt buộc, cần cơ chế bảo vệ đồng thời ở database hoặc mô hình dữ liệu.

Các lựa chọn tùy nghiệp vụ và database:

- Dùng một hàng counter theo customer và cập nhật có điều kiện trong một câu lệnh nguyên tử.
- Khóa hàng cha trong transaction khi kiểm tra và thêm bản ghi, nếu database/isolation hỗ trợ đúng cách.
- Dùng constraint hoặc mô hình dữ liệu cho phép database tự bảo vệ giới hạn.
- Dùng mức isolation cao hơn với xử lý serialization failure/retry có kiểm soát nếu phù hợp.

Chỉ thêm `@Transactional` ở mức mặc định không tự động làm cho chuỗi “count rồi insert” trở thành nguyên tử trước mọi request đồng thời. Cần xem isolation level, locking và câu lệnh SQL thực tế.

## 11. Count chính xác có thể tốn kém

`COUNT(*)` trả số lượng chính xác theo snapshot truy vấn. Với bảng lớn hoặc điều kiện lọc rộng, database có thể phải đọc nhiều entry từ index hoặc nhiều hàng để xác định số lượng. Index có thể giảm lượng dữ liệu phải đọc, nhưng không có nghĩa mọi count đều miễn phí.

Một số gợi ý:

- Tạo index phù hợp cho điều kiện `WHERE` thường dùng.
- Xem execution plan thay vì đoán rằng truy vấn count luôn nhanh.
- Không gọi count liên tục cho mọi request nếu giao diện không thực sự cần số tổng chính xác.
- Với dashboard cần số liệu gần đúng hoặc cập nhật theo đợt, cân nhắc bảng tổng hợp, materialized view, cache hoặc bộ đếm được cập nhật theo event.
- Nếu bảng rất lớn và chỉ cần trang tiếp theo, cân nhắc keyset pagination thay vì đếm toàn bộ để hiển thị tổng trang.

Index không phải lúc nào cũng làm count nhanh hơn đáng kể. Nếu điều kiện chọn phần lớn bảng hoặc database cần kiểm tra visibility của nhiều hàng, chi phí vẫn có thể cao. Mỗi index cũng làm tăng chi phí ghi và dung lượng lưu trữ.

## 12. Count và phân trang

Một màn hình phân trang có thể cần hai loại thông tin:

1. Danh sách bản ghi của trang hiện tại.
2. Tổng số bản ghi phù hợp để tính tổng trang hoặc hiển thị “có N kết quả”.

Đây là hai truy vấn khác nhau: một truy vấn lấy dữ liệu với điều kiện sort/limit, truy vấn còn lại đếm tổng số bản ghi phù hợp. Với reactive repository, không nên gom tất cả bản ghi vào bộ nhớ rồi mới cắt trang hoặc đếm.

Nếu tổng số chính xác là yêu cầu của giao diện, hãy thực hiện count query riêng và cân nhắc chi phí. Nếu chỉ cần biết còn dữ liệu tiếp theo hay không, có thể truy vấn nhiều hơn số phần tử cần hiển thị một đơn vị, hoặc dùng cursor/keyset để xác định trang kế tiếp mà không phải đếm toàn bộ.

Ví dụ truy vấn PostgreSQL lấy một trang:

```sql
SELECT id, email_address, status
FROM customer
WHERE status = $1
ORDER BY id
LIMIT $2 OFFSET $3;
```

Và truy vấn tổng số:

```sql
SELECT COUNT(*)
FROM customer
WHERE status = $1;
```

Hai câu lệnh có thể quan sát hai snapshot khác nhau nếu dữ liệu thay đổi giữa chúng và không nằm trong cùng một transaction với isolation phù hợp. Vì vậy, tổng số và danh sách trang không nhất thiết phản ánh đúng cùng một thời điểm trong môi trường có cập nhật liên tục.

`OFFSET` lớn có thể làm database phải đi qua nhiều hàng trước khi trả trang cần thiết. Với bảng lớn, keyset pagination theo khóa sắp xếp thường có hiệu quả tốt hơn. Chi tiết hỗ trợ Pageable/Sort của repository reactive phụ thuộc phiên bản Spring Data R2DBC; nếu cần kiểm soát chắc chắn SQL và hành vi phân trang, có thể dùng truy vấn tùy chỉnh.

## 13. Truy vấn count và exists bằng @Query

Khi derived query không diễn đạt được truy vấn, có thể khai báo SQL bằng `@Query`. Ví dụ count theo trạng thái:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, UUID> {

    @Query("SELECT COUNT(*) FROM customer WHERE status = :status")
    Mono<Long> countForStatus(@Param("status") String status);
}
```

Tên cột và bảng trong `@Query` là tên SQL thực tế. `@Param` gắn tham số method với named marker trong câu SQL; cú pháp bind cụ thể được Spring Data R2DBC xử lý theo driver/dialect.

Với truy vấn existence tùy chỉnh, cần xem khả năng mapping scalar boolean của database và driver. Ví dụ PostgreSQL:

```java
@Query("""
    SELECT EXISTS (
        SELECT 1 FROM customer WHERE email_address = :email
    )
    """)
Mono<Boolean> emailExists(@Param("email") String email);
```

Nếu query phụ thuộc cú pháp riêng, hãy ghi rõ database mục tiêu và kiểm thử bằng đúng driver. Derived `existsBy...` thường dễ chuyển database hơn vì Spring Data tạo truy vấn dựa trên dialect.

## 14. Xử lý kết quả reactive

Vì repository trả publisher, hãy kết hợp kết quả bằng toán tử Reactor:

```java
customerRepository.existsById(customerId)
        .flatMap(exists -> exists
                ? Mono.just("Customer found")
                : Mono.just("Customer not found"));
```

Hoặc trả kết quả trực tiếp cho WebFlux:

```java
@GetMapping("/{id}/exists")
public Mono<Boolean> customerExists(@PathVariable UUID id) {
    return customerRepository.existsById(id);
}
```

WebFlux quản lý subscription cho publisher trả về từ controller. Trong service reactive, tránh gọi `block()` để chờ `Boolean` hoặc `Long`, vì việc đó chặn thread và phá vỡ chuỗi xử lý reactive.

Không gọi `subscribe()` bên trong service chỉ để lấy kết quả rồi tiếp tục xử lý. `subscribe()` tạo subscription riêng, khiến lỗi và vòng đời thao tác tách khỏi publisher của caller. Hãy dùng `map`, `flatMap`, `zip` hoặc các toán tử phù hợp rồi trả publisher cuối cùng.

Lỗi kết nối, timeout, lỗi SQL hoặc lỗi mapping được truyền dưới dạng tín hiệu lỗi của publisher. Có thể xử lý bằng `onErrorMap` hoặc `onErrorResume` khi có chính sách nghiệp vụ rõ ràng; không nên biến lỗi database thành `false` hoặc `0` một cách âm thầm vì như vậy kết quả “không có dữ liệu” bị lẫn với “không thể kiểm tra dữ liệu”.

## 15. Kiểm thử exists và count

Có thể dùng `StepVerifier` để kiểm thử publisher reactive:

```java
StepVerifier.create(customerRepository.existsByEmail("lan@example.com"))
        .expectNext(true)
        .verifyComplete();

StepVerifier.create(customerRepository.countByStatus("ACTIVE"))
        .expectNext(3L)
        .verifyComplete();
```

Các ví dụ giả định dữ liệu test đã được chuẩn bị và số lượng tương ứng là chính xác. Với kiểm thử repository, nên dùng database test phù hợp và làm sạch dữ liệu giữa các test để kết quả không phụ thuộc thứ tự chạy.

Những tình huống nên kiểm thử:

- `existsById` khi ID tồn tại và không tồn tại.
- `existsByEmail` với email có và không có trong bảng.
- `count()` trên bảng rỗng và bảng có dữ liệu.
- `countByStatus` với trạng thái có kết quả và không có kết quả.
- Giá trị null nếu thuộc tính và query cho phép null.
- Điều kiện kết hợp nhiều thuộc tính.
- Lỗi database được truyền về publisher thay vì bị chuyển thành false/zero.
- Unique constraint khi có hai request tạo dữ liệu trùng đồng thời.

Unit test có thể mock repository để kiểm thử cách application service xử lý true/false hoặc các giá trị count. Nhưng mock không chứng minh SQL được tạo đúng, index được dùng hoặc driver ánh xạ kiểu scalar đúng. Những hành vi đó cần integration test với R2DBC driver và database thực tế.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể có | Hướng xử lý |
| --- | --- | --- |
| Tải entity chỉ để kiểm tra tồn tại | Dùng `findById` hoặc `findAll` dù chỉ cần boolean | Dùng `existsById` hoặc `existsBy...` |
| Đếm bằng `findAll().count()` rất chậm | Ứng dụng đọc và tiêu thụ mọi entity rồi mới đếm | Dùng `count()` hoặc `countBy...` để database thực hiện aggregate |
| Dùng `count > 0` để kiểm tra tồn tại | Database phải xác định tổng số hàng khớp | Dùng truy vấn existence |
| `count()` trả `0` khi có lỗi kết nối bị che giấu | `onErrorResume` chuyển lỗi thành giá trị mặc định | Phân biệt lỗi với kết quả count bằng 0 |
| Email trùng dù đã gọi exists trước insert | Hai request cùng kiểm tra trước khi một request ghi dữ liệu | Thêm unique constraint và xử lý lỗi vi phạm constraint |
| Giới hạn số bản ghi bị vượt | Chuỗi count rồi insert không được bảo vệ đồng thời | Dùng constraint, khóa hoặc cập nhật nguyên tử phù hợp |
| Count sau JOIN lớn hơn số entity mong đợi | Một entity cha xuất hiện nhiều hàng do quan hệ một-nhiều | Dùng `COUNT(DISTINCT root_id)` hoặc EXISTS tùy ý nghĩa |
| Count trên bảng lớn chậm | Truy vấn cần đếm nhiều hàng; index hoặc kế hoạch chưa phù hợp | Xem execution plan, index và cân nhắc summary/counter |
| Derived query không tìm thấy property | Dùng tên cột SQL thay vì tên thuộc tính entity | Đặt tên method theo property Java và mapping metadata |

## 17. Cách lựa chọn phép toán trong một use case

Khi thiết kế truy vấn, hãy xác định rõ dữ liệu đầu ra tối thiểu cần có:

1. Nếu câu trả lời chỉ là có/không, dùng `existsBy...` hoặc `existsById`.
2. Nếu cần số lượng chính xác, dùng `count()` hoặc `countBy...`.
3. Nếu cần nội dung bản ghi, dùng `findBy...` và chỉ lấy các cột cần thiết nếu có thể.
4. Nếu cần tổng hợp theo nhóm, dùng truy vấn aggregate như `COUNT`, `GROUP BY` hoặc projection.
5. Nếu chỉ cần biết còn trang kế tiếp, tránh count toàn bộ khi có thể dùng limit/cursor.
6. Nếu kết quả count/exists dùng để bảo vệ invariant trước thao tác ghi, hãy xử lý race condition ở database bằng constraint, lock hoặc câu lệnh nguyên tử.
7. Giữ kết quả trong pipeline `Mono`/`Flux`; để tầng gọi quản lý subscribe và tránh block trong luồng reactive.

`exists` trả lời câu hỏi có hay không; `count` trả lời có bao nhiêu; `find` trả về dữ liệu cần sử dụng. Dùng đúng phép toán giúp giảm dữ liệu truyền về ứng dụng và thể hiện rõ mục đích của truy vấn. Với Spring Data R2DBC, các phương thức `existsBy...`, `countBy...` cùng `ReactiveCrudRepository.existsById()` và `count()` cung cấp API reactive trực tiếp; database vẫn cần index, constraint và transaction phù hợp để bảo đảm hiệu năng cũng như tính đúng đắn khi có nhiều thao tác đồng thời.
