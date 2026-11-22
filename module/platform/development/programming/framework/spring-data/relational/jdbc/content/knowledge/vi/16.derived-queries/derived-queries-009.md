# find, count, exists và delete theo điều kiện trong Spring Data JDBC

## 1. Truy vấn suy diễn là gì?

Spring Data JDBC cho phép định nghĩa truy vấn bằng **tên phương thức repository**. Framework phân tích tên method, nhận diện property và toán tử điều kiện, rồi tạo câu SQL phù hợp với mapping của entity và database dialect.

Thay vì tự viết SQL cho mỗi điều kiện đơn giản:

~~~java
@Query("SELECT * FROM customers WHERE customer_code = :code")
Optional<Customer> findByCode(String code);
~~~

ta có thể khai báo:

~~~java
Optional<Customer> findByCustomerCode(String customerCode);
~~~

Spring Data nhận biết `findBy` là loại truy vấn đọc, còn `CustomerCode` là property cần so sánh. Đây là **derived query** (truy vấn suy diễn).

Bốn nhóm method được tập trung:

- **`find...By`**: tìm và trả về entity hoặc projection phù hợp.
- **`count...By`**: đếm số hàng thỏa điều kiện.
- **`exists...By`**: kiểm tra có hàng thỏa điều kiện hay không.
- **`delete...By` / `remove...By`**: xóa hàng thỏa điều kiện.

Truy vấn suy diễn hữu ích với điều kiện phổ biến, dễ đọc và ít SQL tùy biến. Khi truy vấn có join, projection phức tạp, biểu thức database riêng hoặc yêu cầu tối ưu đặc biệt, `@Query` và SQL tường minh thường phù hợp hơn.

## 2. Cấu trúc tên method

Một tên method derived query thường có dạng:

~~~text
<Subject><By><Predicate><OrderBy>
~~~

Ví dụ:

~~~java
List<Customer> findByStatusAndCityOrderByDisplayNameAsc(
        CustomerStatus status,
        String city
);
~~~

Có thể phân tích:

- `find`: loại truy vấn tìm dữ liệu.
- `By`: bắt đầu phần điều kiện.
- `StatusAndCity`: hai property được nối bằng `And`.
- `OrderByDisplayNameAsc`: sắp xếp theo property `displayName` tăng dần.

Các phần tên method phải khớp **property Java trong entity**, không nhất thiết khớp tên cột SQL. Ví dụ:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("customer_code")
    private String customerCode;

    @Column("display_name")
    private String displayName;

    private String city;

    private CustomerStatus status;
}
~~~

Method `findByCustomerCode(...)` tham chiếu property `customerCode`; metadata `@Column("customer_code")` giúp Spring Data JDBC ánh xạ tới cột vật lý `customer_code`.

Không viết `findByCustomer_code(...)` chỉ vì schema dùng snake_case. Parser làm việc với mô hình property Java.

## 3. findBy: tìm entity theo điều kiện

### 3.1. Tìm một entity theo business key

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Optional<Customer> findByCustomerCode(String customerCode);
}
~~~

Sử dụng:

~~~java
Customer customer = customerRepository
        .findByCustomerCode("CUST-001")
        .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy khách hàng"
        ));
~~~

`Optional<Customer>` thể hiện rõ hai trường hợp: có kết quả hoặc không có kết quả. Nếu property không được bảo đảm duy nhất, method trả về một entity đơn có thể gặp lỗi khi nhiều hàng phù hợp. Khi nghiệp vụ yêu cầu đúng một khách hàng theo mã, hãy đặt unique constraint trên cột business key trong database.

`Optional` không tự bảo đảm dữ liệu duy nhất; nó chỉ biểu diễn khả năng không có kết quả.

### 3.2. Tìm nhiều entity

~~~java
List<Customer> findByCity(String city);

List<Customer> findAllByStatus(CustomerStatus status);
~~~

`findBy...` và `findAllBy...` có thể được dùng để đọc tập kết quả. Với collection return type, không có hàng phù hợp thường trả collection rỗng, thuận tiện cho vòng lặp:

~~~java
List<Customer> customers = customerRepository.findByCity("Da Nang");

if (customers.isEmpty()) {
    // Không có khách hàng ở thành phố này.
}
~~~

Chọn return type dựa trên cardinality nghiệp vụ:

| Kiểu trả về | Cách biểu diễn |
|---|---|
| `Optional<Customer>` | Không có hoặc một kết quả |
| `Customer` | Một kết quả theo contract; cách xử lý không có kết quả phụ thuộc loại query/API |
| `List<Customer>` | Nhiều kết quả; rỗng nếu không tìm thấy |
| `Iterable<Customer>` | Tập kết quả tổng quát |

Với method dự kiến chỉ có một kết quả, nên dùng `Optional<T>` nếu không tìm thấy là tình huống bình thường. Không dùng `Optional<T>` thay cho unique constraint.

### 3.3. Giới hạn số kết quả với First và Top

Có thể giới hạn số hàng bằng các từ khóa `First` hoặc `Top`:

~~~java
Optional<Customer> findFirstByCityOrderByDisplayNameAsc(String city);

List<Customer> findTop5ByStatusOrderByCreatedAtDesc(
        CustomerStatus status
);
~~~

`First`/`Top` hữu ích khi chỉ cần một vài kết quả theo thứ tự xác định. Nếu chọn một bản ghi “mới nhất”, hãy chỉ rõ `OrderBy` để tránh phụ thuộc thứ tự database trả về.

`findFirstByCity(...)` không có `OrderBy` không diễn đạt rõ bản ghi nào phải được chọn khi có nhiều hàng. SQL quan hệ không bảo đảm thứ tự kết quả nếu không có `ORDER BY`.

## 4. Các toán tử điều kiện thường dùng

Tên method có thể dùng keyword để tạo điều kiện so sánh. Keyword khả dụng và chi tiết hỗ trợ phụ thuộc phiên bản Spring Data JDBC; các dạng dưới đây là những pattern phổ biến.

| Keyword | Ý nghĩa | Ví dụ |
|---|---|---|
| `And` | Kết hợp hai điều kiện bằng AND | `findByStatusAndCity(...)` |
| `Or` | Kết hợp bằng OR | `findByStatusOrCity(...)` |
| `Between` | Nằm trong khoảng | `findByPriceBetween(...)` |
| `LessThan` | Nhỏ hơn | `findByPriceLessThan(...)` |
| `LessThanEqual` | Nhỏ hơn hoặc bằng | `findByPriceLessThanEqual(...)` |
| `GreaterThan` | Lớn hơn | `findByQuantityGreaterThan(...)` |
| `GreaterThanEqual` | Lớn hơn hoặc bằng | `findByPriceGreaterThanEqual(...)` |
| `Before` / `After` | Trước/sau với kiểu ngày giờ phù hợp | `findByCreatedAtAfter(...)` |
| `IsNull` | Giá trị null | `findByEmailAddressIsNull()` |
| `IsNotNull` | Giá trị không null | `findByEmailAddressIsNotNull()` |
| `In` | Giá trị nằm trong tập | `findByStatusIn(...)` |
| `NotIn` | Giá trị không nằm trong tập | `findByStatusNotIn(...)` |
| `Like` | So khớp mẫu SQL LIKE | `findByDisplayNameLike(...)` |
| `Containing` | Chứa chuỗi con | `findByDisplayNameContaining(...)` |
| `StartingWith` | Bắt đầu bằng chuỗi | `findByCustomerCodeStartingWith(...)` |
| `EndingWith` | Kết thúc bằng chuỗi | `findByCustomerCodeEndingWith(...)` |
| `True` / `False` | Giá trị boolean | `findByActiveTrue()` |
| `Not` | Phủ định điều kiện | `findByStatusNot(...)` |
| `IgnoreCase` | So sánh chuỗi không phân biệt hoa thường nếu được hỗ trợ | `findByEmailAddressIgnoreCase(...)` |

### 4.1. Kết hợp điều kiện

~~~java
List<Customer> findByStatusAndCity(
        CustomerStatus status,
        String city
);

List<Customer> findByStatusOrCity(
        CustomerStatus status,
        String city
);
~~~

`And` yêu cầu cả hai điều kiện đúng. `Or` yêu cầu ít nhất một điều kiện đúng.

Với nhiều điều kiện có cả `And` và `Or`, tên method dài có thể khó hiểu về nhóm logic. Hãy kiểm tra quy tắc parser/SQL của phiên bản đang dùng và cân nhắc `@Query` nếu cần biểu thức có ngoặc rõ ràng.

### 4.2. Điều kiện khoảng

~~~java
List<Book> findByPriceBetween(
        BigDecimal minPrice,
        BigDecimal maxPrice
);
~~~

Điều kiện `Between` thường bao gồm hai biên, tương tự SQL `BETWEEN`. Nếu nghiệp vụ cần khoảng nửa mở (ví dụ từ ngày bắt đầu gồm cả ngày đó đến trước ngày kết thúc), có thể dùng hai điều kiện tường minh:

~~~java
List<AuditEvent> findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
        Instant from,
        Instant until
);
~~~

Cách này thường phù hợp với khoảng thời gian `[from, until)`, tránh trùng bản ghi ở ranh giới giữa hai khoảng liền kề.

### 4.3. Điều kiện chuỗi

~~~java
List<Customer> findByDisplayNameContaining(String fragment);

List<Customer> findByCustomerCodeStartingWith(String prefix);

List<Customer> findByEmailAddressEndingWith(String suffix);
~~~

`Containing`, `StartingWith` và `EndingWith` diễn đạt các mẫu tìm kiếm quen thuộc. Kết quả phụ thuộc cách database thực hiện `LIKE`, collation và quy tắc escape ký tự wildcard.

Nếu cần kiểm soát chính xác `%` hoặc `_` trong input, hãy tìm hiểu escaping của phiên bản và cách truy vấn được tạo. Không tự nối chuỗi người dùng vào SQL.

### 4.4. Điều kiện null

~~~java
List<Customer> findByEmailAddressIsNull();

List<Customer> findByEmailAddressIsNotNull();
~~~

SQL sử dụng `IS NULL`/`IS NOT NULL`, không phải phép so sánh `= NULL`. Dùng tên method tường minh giúp thể hiện ý nghĩa và tránh nhầm lẫn giữa giá trị null với chuỗi rỗng.

### 4.5. Điều kiện IN và NOT IN

~~~java
List<Book> findByStatusIn(Collection<BookStatus> statuses);

List<Book> findByStatusNotIn(Collection<BookStatus> statuses);
~~~

Đây là cách tiện lợi khi đầu vào là một tập giá trị. Hãy xử lý collection rỗng trước khi gọi method: SQL `IN ()` không có cú pháp/ý nghĩa nhất quán trên các database và hành vi xử lý có thể khác theo implementation.

Ví dụ:

~~~java
if (statuses.isEmpty()) {
    return List.of();
}
return bookRepository.findByStatusIn(statuses);
~~~

Quyết định với tập rỗng phải theo nghiệp vụ. Với `IN` có tập rỗng, thường không có bản ghi nào thỏa; với `NOT IN` rỗng, có thể có nghĩa là không loại trừ trạng thái nào. Xử lý ở service giúp semantics rõ ràng.

## 5. countBy: đếm số hàng thỏa điều kiện

`countBy...` trả về số lượng bản ghi khớp với predicate. Ví dụ:

~~~java
long countByStatus(CustomerStatus status);

long countByCityAndStatus(String city, CustomerStatus status);

long countByCreatedAtBetween(Instant from, Instant until);
~~~

Sử dụng:

~~~java
long activeCustomers =
        customerRepository.countByStatus(CustomerStatus.ACTIVE);

if (activeCustomers == 0) {
    // Chưa có khách hàng đang hoạt động.
}
~~~

Nên dùng `long` cho số lượng vì tổng số hàng có thể vượt giới hạn của `int`. `countBy` đếm các hàng thỏa điều kiện theo truy vấn; nếu dữ liệu có join hoặc projection tùy biến, cần xác định rõ một hàng được tính theo semantics nào.

### 5.1. countBy khác findBy(...).size()

So sánh:

~~~java
List<Customer> customers =
        customerRepository.findByStatus(CustomerStatus.ACTIVE);

long count = customers.size();
~~~

với:

~~~java
long count =
        customerRepository.countByStatus(CustomerStatus.ACTIVE);
~~~

Cách thứ nhất tải toàn bộ entity về application rồi mới đếm. Cách thứ hai yêu cầu database đếm kết quả, thường giảm lượng dữ liệu truyền và số object phải tạo.

Khi chỉ cần số lượng, ưu tiên `countBy` thay vì tải toàn bộ collection. Tuy nhiên, chi phí truy vấn count vẫn phụ thuộc index, predicate, database và query plan; không phải mọi `COUNT` đều có chi phí hằng số.

## 6. existsBy: kiểm tra có bản ghi hay không

`existsBy...` trả về boolean, phù hợp khi nghiệp vụ chỉ cần biết có ít nhất một bản ghi thỏa điều kiện:

~~~java
boolean existsByCustomerCode(String customerCode);

boolean existsByEmailAddressAndStatus(
        String emailAddress,
        CustomerStatus status
);
~~~

Ví dụ kiểm tra trước khi tạo:

~~~java
if (customerRepository.existsByCustomerCode(code)) {
    throw new CustomerCodeAlreadyUsedException(code);
}
~~~

`existsBy` diễn đạt đúng ý định hơn việc gọi `findBy...` rồi kiểm tra `Optional.isPresent()`, vì ứng dụng không cần toàn bộ entity.

Tuy nhiên, kiểm tra tồn tại trước khi insert **không thay thế unique constraint**. Hai request đồng thời có thể cùng nhận `false` rồi cùng cố insert. Database phải có constraint bảo vệ quy tắc duy nhất; ứng dụng vẫn cần xử lý lỗi duplicate khi ghi.

### 6.1. existsBy không phải khóa chống cạnh tranh

Luồng có thể xảy ra:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Database
    A->>DB: existsByCustomerCode("C001")
    B->>DB: existsByCustomerCode("C001")
    DB-->>A: false
    DB-->>B: false
    A->>DB: INSERT C001
    B->>DB: INSERT C001
    DB-->>A: Thành công
    DB-->>B: Unique constraint violation
~~~

Vì vậy, `existsBy` hữu ích để kiểm tra sớm và cải thiện thông báo. Nó không giữ chỗ cho giá trị đó, không khóa business key và không bảo đảm request tiếp theo sẽ insert thành công.

## 7. deleteBy và removeBy: xóa theo điều kiện

Spring Data hỗ trợ derived delete methods theo tên điều kiện:

~~~java
void deleteByStatus(CustomerStatus status);

void removeByCreatedAtBefore(Instant cutoff);
~~~

Ví dụ xóa các bản ghi đã hết hạn:

~~~java
customerRepository.deleteByStatus(CustomerStatus.EXPIRED);
~~~

`deleteBy` và `removeBy` biểu đạt thao tác xóa các hàng thỏa điều kiện. Chữ `By` bắt đầu predicate; các keyword như `And`, `Before`, `In` có thể được dùng để mô tả điều kiện.

### 7.1. Chọn kiểu trả về cho delete

Tùy loại repository method và phiên bản Spring Data, delete method có thể dùng kiểu trả về không có dữ liệu hoặc kiểu số lượng hàng bị tác động khi được hỗ trợ. Ví dụ dạng đếm:

~~~java
long deleteByStatus(CustomerStatus status);
~~~

Hãy xác nhận kiểu trả về mà phiên bản Spring Data JDBC và repository interface của dự án hỗ trợ. Nếu không cần số lượng, dùng `void` để thể hiện command. Nếu cần biết chính xác số hàng bị xóa, kiểm tra contract và kết quả trên database mục tiêu thay vì giả định mọi delete method đều trả count giống nhau.

Với dữ liệu quan trọng, không nên thực hiện xóa diện rộng chỉ dựa trên một predicate chưa được kiểm tra. Có thể chạy `countBy...` hoặc `find...` trước để xác nhận phạm vi, nhưng transaction và chính sách xóa vẫn phải được thiết kế rõ.

### 7.2. Xóa entity theo ID và xóa theo điều kiện

Hai thao tác có ý nghĩa khác nhau:

~~~java
customerRepository.deleteById(id);
customerRepository.deleteByCustomerCode(code);
~~~

`deleteById` nhắm tới identifier của entity. `deleteByCustomerCode` nhắm tới property nghiệp vụ. Nếu business key không unique, lệnh thứ hai có thể xóa nhiều hàng.

Nếu yêu cầu chỉ xóa đúng một khách hàng theo mã, hãy bảo vệ tính duy nhất bằng unique constraint. Đừng chỉ dựa vào giả định mã “thường không trùng”.

### 7.3. Delete theo điều kiện và aggregate

Trong Spring Data JDBC, aggregate root có thể sở hữu các hàng con ở bảng khác. Khi xóa aggregate, cần giữ toàn vẹn foreign key và quy tắc vòng đời child.

Không nên mặc định mọi derived delete method có semantics giống việc tải từng aggregate rồi gọi `repository.delete(entity)`. Nếu aggregate có child, callback, audit hoặc quy tắc xóa phụ thuộc, hãy kiểm tra hành vi của method trên phiên bản đang dùng và database thực tế. Với thao tác cần lifecycle rõ ràng, có thể tìm các aggregate phù hợp rồi xóa qua repository theo cách tường minh, hoặc thiết kế SQL/cascade trong schema có chủ đích.

Cần chú ý foreign key: nếu bảng con không được xóa theo chiến lược của aggregate hoặc không có cascade phù hợp, xóa root có thể bị database từ chối. Không bật cascade một cách máy móc; chọn chính sách theo ownership của dữ liệu.

## 8. Kết hợp find, count, exists và delete trong repository

Ví dụ repository:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Optional<Customer> findByCustomerCode(String customerCode);

    List<Customer> findByStatusAndCity(
            CustomerStatus status,
            String city
    );

    List<Customer> findTop10ByStatusOrderByCreatedAtDesc(
            CustomerStatus status
    );

    long countByStatus(CustomerStatus status);

    boolean existsByEmailAddress(String emailAddress);

    void deleteByStatusAndCreatedAtBefore(
            CustomerStatus status,
            Instant cutoff
    );
}
~~~

Service có thể kết hợp các thao tác:

~~~java
@Service
public class CustomerMaintenanceService {

    private final CustomerRepository customers;

    public CustomerMaintenanceService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public long removeExpiredCustomers(Instant cutoff) {
        long before = customers.countByStatusAndCreatedAtBefore(
                CustomerStatus.EXPIRED,
                cutoff
        );

        customers.deleteByStatusAndCreatedAtBefore(
                CustomerStatus.EXPIRED,
                cutoff
        );

        return before;
    }
}
~~~

Trong ví dụ này, số lượng được đếm trước khi xóa và trả về. Lưu ý `count` và `delete` là hai truy vấn riêng. Nếu dữ liệu thay đổi đồng thời, số đếm trước và số hàng thực sự xóa có thể khác nhau, trừ khi transaction isolation và khóa được thiết kế để đảm bảo snapshot phù hợp.

Nếu repository delete method có thể trả count theo contract của phiên bản đang dùng, dùng trực tiếp kết quả đó sẽ tránh một truy vấn count riêng. Cần xác nhận semantics và kiểu trả về cụ thể.

## 9. Derived query dùng property Java, không dùng tên cột

Entity:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("customer_code")
    private String customerCode;

    @Column("email_address")
    private String emailAddress;

    @Column("created_at")
    private Instant createdAt;
}
~~~

Repository method:

~~~java
Optional<Customer> findByCustomerCode(String code);

boolean existsByEmailAddress(String email);

long countByCreatedAtAfter(Instant timestamp);
~~~

Parser tham chiếu property `customerCode`, `emailAddress`, `createdAt`. Mapping metadata xử lý tên cột vật lý `customer_code`, `email_address`, `created_at`.

Nếu viết `findByEmail_Address`, method parser không hiểu đó là tên cột SQL; dấu gạch dưới trong tên method có thể được dùng để phân tách property path theo quy ước parser, không phải để viết tên cột vật lý.

Khi property lồng nhau hoặc embedded object, tên property path và khả năng hỗ trợ phụ thuộc mapping/query derivation của Spring Data JDBC. Hãy kiểm tra mapping cụ thể; không giả định có thể truy vấn tùy ý xuyên qua mọi quan hệ aggregate như khi dùng ORM.

## 10. Derived query và @Query: khi nào nên chuyển sang SQL tường minh?

Derived query phù hợp khi method name vẫn dễ đọc và điều kiện phản ánh trực tiếp property. Ví dụ:

~~~java
List<Book> findByPriceGreaterThanEqualAndStatus(
        BigDecimal minPrice,
        BookStatus status
);
~~~

Khi method trở nên dài hoặc cần tính năng SQL riêng, `@Query` có thể rõ ràng hơn:

~~~java
@Query("""
    SELECT id, title, price, status
    FROM books
    WHERE status = :status
      AND price >= :minPrice
    ORDER BY price DESC, id
    """)
List<Book> findAvailableBooks(
        BookStatus status,
        BigDecimal minPrice
);
~~~

Với truy vấn thay đổi dữ liệu bằng `@Query`, Spring Data JDBC thường yêu cầu `@Modifying` để đánh dấu đây là modifying query:

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET status = :newStatus
    WHERE status = :oldStatus
    """)
int updateCustomerStatus(
        CustomerStatus oldStatus,
        CustomerStatus newStatus
);
~~~

SQL tường minh phù hợp khi cần:

- Join hoặc biểu thức database đặc thù.
- CTE, window function hoặc phép tổng hợp phức tạp.
- Alias/projection tùy chỉnh.
- Điều kiện có nhóm ngoặc phức tạp.
- Update nhiều cột theo một lệnh.
- Kiểm soát chính xác câu SQL được gửi.

Đổi lại, người viết phải đảm bảo SQL khớp schema, dialect, kiểu tham số và kết quả mapping. Dùng named parameter để bind **giá trị dữ liệu**; không nối input trực tiếp vào chuỗi SQL.

## 11. Return type và cách xử lý không có kết quả

Chọn kiểu trả về phù hợp giúp caller xử lý rõ ràng:

| Ý định | Method ví dụ | Return type thường dùng |
|---|---|---|
| Tìm theo mã có thể không tồn tại | `findByCustomerCode(...)` | `Optional<Customer>` |
| Tìm nhiều hàng | `findByStatus(...)` | `List<Customer>` |
| Đếm hàng phù hợp | `countByStatus(...)` | `long` |
| Kiểm tra tồn tại | `existsByCustomerCode(...)` | `boolean` |
| Xóa theo điều kiện, không cần kết quả | `deleteByStatus(...)` | `void` |
| Xóa và cần số lượng khi được hỗ trợ | `deleteByStatus(...)` | Kiểu số phù hợp theo contract |

Đối với `Optional<T>`, nhiều hàng phù hợp không phải là “có nhiều lựa chọn thì lấy đại một hàng”; nó vi phạm giả định kết quả đơn và có thể dẫn tới exception về kích thước kết quả. Nếu nghiệp vụ yêu cầu duy nhất, database cần unique constraint.

Đối với collection return type, không có hàng thường biểu diễn collection rỗng. Với count, không có hàng phù hợp trả về zero. Với exists, kết quả là false.

## 12. An toàn tham số và SQL injection

Derived query bind giá trị thông qua cơ chế truy vấn của Spring Data. Với `@Query`, hãy dùng named parameter:

~~~java
@Query("""
    SELECT id, customer_code, display_name
    FROM customers
    WHERE customer_code = :code
    """)
Optional<Customer> findByCode(String code);
~~~

Không ghép input thành SQL:

~~~java
// Không an toàn:
String sql = "SELECT * FROM customers WHERE customer_code = '" + code + "'";
~~~

Prepared parameter bảo vệ **giá trị**, không thể thay thế tên bảng, tên cột hoặc keyword SQL. Nếu người dùng được chọn cột sắp xếp, hãy ánh xạ lựa chọn từ allowlist do ứng dụng kiểm soát.

Tên method derived query được xác định khi biên dịch và không nhận trực tiếp một mảnh SQL từ request, do đó không cần nối chuỗi input vào tên method.

## 13. Hiệu năng và index cho các điều kiện truy vấn

Derived query không tự bảo đảm truy vấn nhanh. Database vẫn phải thực hiện predicate, sort và count theo schema/index/query plan.

Ví dụ method:

~~~java
Optional<Customer> findByCustomerCode(String customerCode);
~~~

Nếu `customer_code` là business key duy nhất, nên có unique constraint:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uk_customers_customer_code UNIQUE (customer_code);
~~~

Constraint này vừa bảo vệ dữ liệu vừa thường tạo index hỗ trợ lookup. Với truy vấn:

~~~java
List<Customer> findByStatusAndCity(
        CustomerStatus status,
        String city
);
~~~

có thể cân nhắc index ghép `(status, city)` sau khi xem workload và query plan. Không nên tạo index cho mọi property; index làm tăng chi phí INSERT/UPDATE/DELETE và dung lượng.

Đối với `countBy`, database có thể phải quét nhiều index entry hoặc hàng tùy điều kiện. Đối với `existsBy`, database có thể dừng khi tìm được một kết quả phù hợp, nhưng câu SQL và query plan thực tế phụ thuộc implementation/database. Hãy đo thay vì giả định mọi exists query đều có cùng chi phí.

`deleteBy` cũng có thể tốn đáng kể nếu predicate không có index hoặc xóa lượng lớn hàng. Xóa hàng còn kéo theo cập nhật index, kiểm tra foreign key và ghi transaction log.

## 14. Những lưu ý về điều kiện và dữ liệu

### 14.1. Hoa thường và collation

`findByEmailAddressIgnoreCase(...)` có thể biểu đạt so sánh không phân biệt hoa thường nếu kiểu property và database hỗ trợ. Tuy nhiên, quy tắc chính xác phụ thuộc dialect/collation và cách Spring Data tạo SQL.

Nếu email hoặc username cần uniqueness không phân biệt hoa thường, hãy bảo đảm unique constraint cũng sử dụng cùng quy tắc chuẩn hóa. Derived query `IgnoreCase` không tự tạo unique constraint tương ứng.

### 14.2. Wildcard trong LIKE

`Containing`, `StartingWith`, `EndingWith` thường được chuyển thành pattern LIKE. Ký tự `%` và `_` có ý nghĩa wildcard trong SQL. Nếu input chứa các ký tự này, xác định cách escape mà framework/driver sử dụng hoặc chọn `@Query` với chiến lược escaping rõ ràng.

### 14.3. Thời gian và timezone

Với property thời gian, chọn kiểu Java/SQL phù hợp. Ví dụ `Instant` biểu diễn thời điểm trên timeline; `LocalDate` biểu diễn ngày không có thời gian. Khi dùng `Before`, `After`, `Between`, cần thống nhất timezone và cách lưu timestamp để tránh sai lệch ở biên ngày.

### 14.4. Delete diện rộng

Method `deleteByStatus(status)` có thể tác động nhiều hàng. Trước khi chạy trên dữ liệu quan trọng, hãy xác định predicate, transaction và chính sách xóa. Có thể dùng count hoặc truy vấn preview để ước lượng phạm vi; nhưng giữa preview và delete vẫn có thể có thay đổi đồng thời.

## 15. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Method name không được parse | Tên keyword hoặc property sai | Kiểm tra property Java và cú pháp derived query |
| `findByCustomer_code` không hoạt động | Dùng tên cột vật lý thay tên property | Dùng `findByCustomerCode` |
| `Optional` gặp nhiều hàng | Property không unique nhưng method giả định một kết quả | Dùng collection hoặc đặt unique constraint |
| `countBy` tải nhiều entity | Dùng `findBy(...).size()` thay vì count query | Dùng `countBy...` |
| `existsBy` bị coi là bảo đảm không trùng | Nhầm kiểm tra trước với constraint | Thêm unique constraint và xử lý duplicate |
| `IN` với collection rỗng gây SQL lỗi | SQL `IN ()` không portable | Xử lý collection rỗng ở service |
| `IgnoreCase` cho kết quả khác database khác | Collation/dialect khác nhau | Kiểm tra SQL và quy tắc so sánh |
| `deleteBy` xóa quá nhiều hàng | Predicate quá rộng hoặc thiếu điều kiện tenant | Bổ sung điều kiện phạm vi và kiểm tra trước |
| Delete root vi phạm foreign key | Child/reference chưa được xử lý theo aggregate/schema | Kiểm tra mapping, cascade và aggregate boundary |
| Derived query quá dài, khó đọc | Quá nhiều điều kiện và logic OR | Dùng `@Query` hoặc custom repository |
| Query trả về entity thiếu property | SELECT tùy biến không trả đủ cột cần mapping | Trả đủ cột hoặc dùng projection |
| Count trước và delete thực tế lệch nhau | Có ghi đồng thời giữa hai truy vấn | Xác định transaction isolation/lock hoặc dùng kết quả delete nếu hỗ trợ |

## 16. Bài tập thực hành

### Bài 1 — findBy

Tạo `CustomerRepository` với `findByCustomerCode`, `findByStatusAndCity` và `findTop5ByStatusOrderByCreatedAtDesc`. Tạo dữ liệu mẫu rồi kiểm tra collection rỗng, một kết quả và nhiều kết quả.

### Bài 2 — countBy

Viết `countByStatus` và `countByCreatedAtAfter`. So sánh với cách gọi `findByStatus(...).size()` về số object được tải và thời gian thực thi.

### Bài 3 — existsBy

Viết `existsByCustomerCode`. Gửi hai request đồng thời đăng ký cùng mã. Thêm unique constraint và quan sát vì sao một request phải xử lý duplicate dù cả hai lần kiểm tra trước đều có thể trả false.

### Bài 4 — deleteBy

Viết `deleteByStatusAndCreatedAtBefore`. Chuẩn bị dữ liệu có trạng thái khác nhau và kiểm tra predicate chỉ xóa đúng nhóm cần thiết. Nếu method trả count trong phiên bản đang dùng, đối chiếu count với dữ liệu thực tế.

### Bài 5 — Điều kiện IN

Viết `findByStatusIn`. Thử tập có nhiều phần tử, một phần tử và rỗng. Thiết kế xử lý tập rỗng ở service theo đúng ý nghĩa nghiệp vụ.

### Bài 6 — Chuyển derived query thành @Query

Lấy một method có nhiều điều kiện và chuyển sang `@Query`. So sánh độ dễ đọc, khả năng kiểm soát SQL và sự phụ thuộc vào schema.

### Bài 7 — Index và query plan

Tạo truy vấn `findByStatusAndCity`, đo query plan trước và sau khi thêm index phù hợp. Đo cả chi phí ghi khi index tồn tại để hiểu trade-off đọc/ghi.

## 17. Ghi nhớ

- Derived query được tạo từ **tên method repository**, predicate và property Java của entity.
- `find...By` tìm entity; dùng `Optional` cho không/có một kết quả và collection cho nhiều kết quả.
- `count...By` đếm bản ghi phù hợp; `exists...By` kiểm tra có bản ghi phù hợp; `delete...By`/`remove...By` xóa theo điều kiện.
- Tên property Java và tên cột vật lý có thể khác nhau; `@Column` và naming strategy xử lý ánh xạ.
- Các keyword như `And`, `Or`, `Between`, `In`, `IsNull`, `Containing`, `StartingWith` và `OrderBy` giúp mô tả điều kiện phổ biến.
- `existsBy` không thay thế unique constraint; kiểm tra trước khi insert vẫn có race condition.
- Delete theo điều kiện cần predicate chặt chẽ, transaction và hiểu rõ quan hệ aggregate/foreign key.
- Khi method quá dài hoặc cần SQL phức tạp, dùng `@Query` và `@Modifying` phù hợp.
- Hiệu năng phụ thuộc index, collation, query plan, số hàng và chi phí cập nhật index/constraint; hãy đo trên database mục tiêu.
