# findById, findAll và findAllById

Trong Spring Data JDBC, repository cung cấp các phương thức CRUD cơ bản để đọc aggregate từ cơ sở dữ liệu. Ba phương thức thường dùng nhất khi truy xuất theo định danh là **`findById`**, **`findAll`** và **`findAllById`**. Chúng có vẻ đơn giản, nhưng khác nhau về kiểu kết quả, phạm vi dữ liệu được đọc, cách xử lý ID không tồn tại và khả năng mở rộng khi số lượng dữ liệu tăng.

Bài học này giải thích ba phương thức trong hợp đồng repository của Spring Data Commons và cách Spring Data JDBC thực hiện chúng trên aggregate quan hệ. Ví dụ sử dụng một `CustomerRepository` để minh họa truy xuất một khách hàng, toàn bộ khách hàng và một tập khách hàng theo danh sách ID.

## 1. Repository CRUD và vị trí của ba phương thức

Spring Data Commons định nghĩa các hợp đồng repository dùng chung. `CrudRepository<T, ID>` cung cấp những thao tác CRUD cơ bản với:

- `T`: kiểu domain object/aggregate root mà repository quản lý.
- `ID`: kiểu định danh của root.

Ba phương thức đọc cần nắm:

```java
Optional<T> findById(ID id);

Iterable<T> findAll();

Iterable<T> findAllById(Iterable<ID> ids);
```

Trong Spring Data JDBC, repository được khai báo theo aggregate root. Spring Data JDBC cung cấp implementation để đọc các aggregate đó từ database và ánh xạ thành domain object.

Ví dụ:

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Không cần tự viết implementation cho ba phương thức CRUD cơ bản. Khi ứng dụng có Spring Data JDBC và cấu hình datasource hợp lệ, Spring Data tạo repository proxy phù hợp.

### 1.1. CrudRepository và ListCrudRepository

Spring Data Commons có hai hợp đồng thường dùng:

| Interface | Kiểu kết quả của các phương thức đọc nhiều phần tử |
| --- | --- |
| `CrudRepository<T, ID>` | `Iterable<T>` |
| `ListCrudRepository<T, ID>` | `List<T>` |

Nếu muốn nhận `List` trực tiếp, có thể khai báo:

```java
import org.springframework.data.repository.ListCrudRepository;

public interface CustomerRepository
        extends ListCrudRepository<Customer, Long> {
}
```

`ListCrudRepository` kế thừa hợp đồng CRUD và cung cấp kiểu trả về `List` cho những phương thức trả về nhiều entity. `findById` vẫn trả về `Optional<T>` vì kết quả là tối đa một entity.

Việc chọn `CrudRepository` hay `ListCrudRepository` không làm thay đổi ý nghĩa nghiệp vụ của truy vấn; nó chủ yếu ảnh hưởng kiểu dữ liệu mà code gọi nhận được.

## 2. findById(ID id): tìm một aggregate theo định danh

`findById` truy xuất một entity theo ID:

```java
Optional<Customer> findById(Long id);
```

Kết quả là `Optional<Customer>` vì có thể có hoặc không có hàng tương ứng trong database.

Ví dụ:

```java
Optional<Customer> result = customerRepository.findById(42L);

if (result.isPresent()) {
    Customer customer = result.get();
    System.out.println(customer.name());
}
```

Hoặc dùng cách thường thấy trong service:

```java
Customer customer = customerRepository.findById(customerId)
    .orElseThrow(() ->
        new CustomerNotFoundException(customerId)
    );
```

### 2.1. Vì sao trả về Optional?

Có hai khả năng hợp lệ:

- ID tồn tại: Optional chứa entity.
- ID không tồn tại: Optional rỗng (`Optional.empty()`).

Phương thức không trả về `null` để biểu diễn không tìm thấy. Nhờ vậy, caller phải xử lý rõ trường hợp thiếu dữ liệu thay vì vô tình dereference một giá trị null.

Ví dụ:

```java
Optional<Customer> result = customerRepository.findById(999L);

assert result.isEmpty();
```

Nếu ứng dụng muốn trả HTTP 404, service có thể chuyển trường hợp Optional rỗng thành exception nghiệp vụ hoặc kết quả phù hợp. Repository không tự quyết định HTTP status.

### 2.2. ID không hợp lệ

Tham số ID không được là `null`. Truyền ID null vi phạm contract và dẫn tới `IllegalArgumentException`.

```java
customerRepository.findById(null); // Không hợp lệ
```

Hãy validate dữ liệu đầu vào ở boundary phù hợp. Nếu ID đến từ URL hoặc request, có thể chuyển đổi/kiểm tra trước khi gọi repository.

### 2.3. findById đọc aggregate root như thế nào?

Giả sử Customer là aggregate root có địa chỉ liên hệ thuộc cùng aggregate:

```java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;

    @MappedCollection(idColumn = "customer_id")
    private Set<ContactAddress> addresses = new HashSet<>();
}
```

Khi gọi `findById`, mục tiêu là khôi phục aggregate Customer theo mapping đã khai báo. Spring Data JDBC không phải JPA ORM với lazy-loading proxy; mô hình JDBC đọc dữ liệu thuộc aggregate theo cơ chế mapping của nó. Không nên giả định rằng collection con sẽ tự được tải muộn ở lần gọi getter như `FetchType.LAZY` của JPA.

Vì vậy, kích thước aggregate ảnh hưởng tới chi phí của một lần đọc. Nếu root sở hữu nhiều dữ liệu con, truy xuất một root có thể cần nhiều thao tác đọc hơn một câu SELECT đơn giản trên bảng root.

### 2.4. Ví dụ SQL khái niệm

Với bảng:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(160) NOT NULL
);
```

Một truy vấn theo ID có dạng khái niệm:

```sql
SELECT id, name
FROM customers
WHERE id = ?;
```

Đây là cách diễn đạt ý nghĩa truy vấn. SQL thực tế có thể khác theo dialect, mapping metadata, tên cột và cách Spring Data JDBC triển khai.

## 3. findAll(): đọc toàn bộ aggregate

`findAll` lấy tất cả entity mà repository quản lý:

```java
Iterable<Customer> findAll();
```

Nếu repository kế thừa `ListCrudRepository`, kiểu trả về là `List<Customer>`:

```java
List<Customer> customers = customerRepository.findAll();
```

Ví dụ:

```java
for (Customer customer : customerRepository.findAll()) {
    System.out.println(customer.name());
}
```

### 3.1. Khi không có dữ liệu

Nếu không có khách hàng nào, `findAll` trả về collection rỗng (Iterable/List rỗng), không trả `null`.

```java
List<Customer> customers = customerRepository.findAll();

if (customers.isEmpty()) {
    System.out.println("Chưa có khách hàng");
}
```

### 3.2. findAll không có điều kiện lọc

`findAll` không nhận tham số lọc và có ý nghĩa đọc tất cả entity của repository. Về mặt SQL, có thể hình dung:

```sql
SELECT id, name
FROM customers;
```

Không nên dùng phương thức này cho bảng có hàng triệu bản ghi chỉ để sau đó lọc bằng Java:

```java
List<Customer> all = customerRepository.findAll();

List<Customer> active = all.stream()
    .filter(Customer::active)
    .toList();
```

Cách làm này đưa toàn bộ dữ liệu về ứng dụng, tốn bộ nhớ và băng thông, trong khi database có thể lọc hiệu quả hơn.

Nếu chỉ cần các khách hàng đang hoạt động, hãy dùng query method hoặc truy vấn có điều kiện phù hợp:

```java
List<Customer> findByActiveTrue();
```

Đây là phương thức truy vấn được dẫn xuất từ tên method, khác với CRUD method `findAll`.

### 3.3. Không có bảo đảm thứ tự

`findAll` không có tham số sắp xếp nên caller không nên giả định kết quả theo thứ tự ID, tên hoặc thời điểm tạo. Database không bảo đảm thứ tự row nếu câu SQL không có `ORDER BY`.

Nếu nghiệp vụ cần sắp xếp, hãy dùng API sorting/query phù hợp hoặc truy vấn tường minh:

```sql
SELECT id, name
FROM customers
ORDER BY name ASC, id ASC;
```

Việc dùng một tiêu chí phụ như ID giúp kết quả ổn định khi nhiều bản ghi có cùng tên.

### 3.4. Rủi ro hiệu năng của findAll

Một lần `findAll` có thể tạo ra nhiều công việc:

- Đọc toàn bộ aggregate root.
- Ánh xạ từng row thành domain object.
- Đọc các thành phần con thuộc aggregate theo mapping.
- Giữ nhiều object trong bộ nhớ ứng dụng cùng lúc.

Nếu aggregate có collection lớn, tổng lượng dữ liệu được materialize có thể vượt xa kích thước bảng root. Hãy cân nhắc quy mô dữ liệu trước khi gọi `findAll` trong request web hoặc job định kỳ.

`findAll` phù hợp khi tập dữ liệu nhỏ hoặc use case thực sự cần toàn bộ dữ liệu. Với danh sách lớn, nên cân nhắc pagination, sorting, query theo điều kiện hoặc read model chuyên biệt.

## 4. findAllById(Iterable<ID> ids): đọc một tập aggregate theo ID

`findAllById` nhận một iterable các ID và trả về các entity tìm thấy:

```java
Iterable<Customer> findAllById(Iterable<Long> ids);
```

Với `ListCrudRepository`:

```java
List<Customer> findAllById(Iterable<Long> ids);
```

Ví dụ:

```java
List<Long> ids = List.of(10L, 20L, 30L);

List<Customer> customers =
    customerRepository.findAllById(ids);
```

Phương thức này hữu ích khi ứng dụng đã có danh sách định danh và muốn tải những aggregate tương ứng mà không phải gọi `findById` lặp lại cho từng ID.

### 4.1. ID không tìm thấy sẽ bị bỏ qua

Contract của `findAllById` quy định chỉ trả về các entity tìm thấy. Nếu một hoặc nhiều ID không tồn tại, các entity tương ứng không xuất hiện trong kết quả.

Ví dụ:

```java
List<Long> ids = List.of(10L, 20L, 999L);

List<Customer> found = customerRepository.findAllById(ids);
```

Giả sử database có ID 10 và 20 nhưng không có 999, kết quả chứa khách hàng 10 và 20. Phương thức không tạo placeholder hoặc Optional riêng cho từng ID bị thiếu.

Điều này khác với cách gọi lặp:

```java
Optional<Customer> first = repository.findById(10L);
Optional<Customer> second = repository.findById(20L);
Optional<Customer> missing = repository.findById(999L);
```

Nếu nghiệp vụ cần biết chính xác ID nào thiếu, ứng dụng phải so sánh tập ID yêu cầu với ID trả về hoặc thực hiện kiểm tra bổ sung.

### 4.2. Thứ tự kết quả không được bảo đảm

Đây là điểm rất quan trọng: `findAllById` **không bảo đảm thứ tự kết quả trùng với thứ tự các ID đầu vào**.

Ví dụ:

```java
List<Long> requestedIds = List.of(30L, 10L, 20L);
List<Customer> customers =
    repository.findAllById(requestedIds);
```

Không được giả định phần tử đầu tiên trong kết quả chắc chắn là Customer có ID 30. Database và implementation repository không cam kết thứ tự này.

Nếu cần giữ thứ tự đầu vào, hãy tái sắp xếp kết quả ở application layer theo ID:

```java
Map<Long, Customer> byId = customers.stream()
    .collect(Collectors.toMap(
        Customer::id,
        Function.identity()
    ));

List<Customer> ordered = requestedIds.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
```

Ví dụ này giữ thứ tự ID yêu cầu và bỏ qua ID không tìm thấy. Nếu cần phân biệt ID thiếu, hãy kiểm tra giá trị null hoặc tạo kết quả biểu diễn trạng thái rõ ràng thay vì lọc bỏ.

### 4.3. Đầu vào null

Iterable IDs không được là `null` và không được chứa ID null theo contract. Truyền đầu vào không hợp lệ dẫn tới `IllegalArgumentException`.

```java
repository.findAllById(null); // Không hợp lệ

repository.findAllById(
    Arrays.asList(10L, null, 20L)
); // Không hợp lệ
```

Một collection rỗng là đầu vào hợp lệ; kết quả là collection rỗng.

### 4.4. Trùng ID trong đầu vào

Không nên dựa vào `findAllById` để giữ số lần xuất hiện hoặc vị trí của ID trùng lặp trong iterable đầu vào. Contract không bảo đảm thứ tự và không phải một API ánh xạ từng phần tử đầu vào thành một kết quả tương ứng.

Nếu nghiệp vụ cần xử lý từng yêu cầu riêng biệt, hãy chuẩn hóa danh sách ID hoặc tự xây dựng logic ánh xạ kết quả theo danh sách ban đầu. Nếu chỉ cần tập aggregate duy nhất, có thể chuẩn hóa bằng `Set` trước khi gọi repository.

### 4.5. SQL khái niệm

Về mặt ý nghĩa, truy vấn có thể được diễn đạt bằng:

```sql
SELECT id, name
FROM customers
WHERE id IN (?, ?, ?);
```

Đây chỉ là minh họa logic lọc theo tập ID. Không nên phụ thuộc vào chính xác một câu SQL hoặc số lần round-trip cố định: cách thực thi phụ thuộc phiên bản Spring Data JDBC, dialect, kích thước tập ID và giới hạn của driver/database.

## 5. So sánh ba phương thức

| Tiêu chí | `findById` | `findAll` | `findAllById` |
| --- | --- | --- | --- |
| Đầu vào | Một ID | Không có | Iterable các ID |
| Phạm vi | Tối đa một aggregate | Tất cả aggregate của repository | Những aggregate có ID trong tập đầu vào |
| Kiểu trả về CrudRepository | `Optional<T>` | `Iterable<T>` | `Iterable<T>` |
| Kiểu trả về ListCrudRepository | `Optional<T>` | `List<T>` | `List<T>` |
| ID không tồn tại | Optional rỗng | Không áp dụng | Bỏ qua entity không tìm thấy |
| Thứ tự | Một phần tử | Không bảo đảm | Không bảo đảm theo input |
| Đầu vào null | ID null không hợp lệ | Không có tham số | Iterable null/ID null không hợp lệ |
| Quy mô dữ liệu | Một aggregate | Có thể rất lớn | Phụ thuộc số ID truyền vào |

### 5.1. Chọn phương thức theo use case

- Cần tải một đơn hàng theo ID: dùng `findById`.
- Cần lấy toàn bộ dữ liệu nhỏ cho tác vụ quản trị: có thể dùng `findAll`.
- Đã có danh sách ID và cần tải các aggregate tương ứng: dùng `findAllById`.
- Cần lọc, sắp xếp hoặc phân trang tập lớn: dùng query/sorting/paging API phù hợp thay vì đọc tất cả.

## 6. Ví dụ domain và repository hoàn chỉnh

Giả sử ứng dụng quản lý khách hàng có schema:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL
);
```

Domain object:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
    @Id Long id,
    String name,
    String email,
    boolean active
) {}
```

Repository:

```java
import org.springframework.data.repository.ListCrudRepository;

public interface CustomerRepository
        extends ListCrudRepository<Customer, Long> {
}
```

Service:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerQueryService {

    private final CustomerRepository customers;

    public CustomerQueryService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public Optional<Customer> findOne(Long id) {
        return customers.findById(id);
    }

    @Transactional(readOnly = true)
    public List<Customer> findEveryCustomer() {
        return customers.findAll();
    }

    @Transactional(readOnly = true)
    public List<Customer> findSelected(List<Long> ids) {
        return customers.findAllById(ids);
    }
}
```

Ở đây `@Transactional(readOnly = true)` thể hiện use case chỉ đọc. Các phương thức CRUD của repository có cấu hình transaction mặc định của Spring Data; transaction ở service hữu ích khi use case phối hợp nhiều thao tác cần chung một ranh giới transaction.

Service trả `Optional<Customer>` cho một ID, `List<Customer>` cho tập kết quả vì repository kế thừa `ListCrudRepository`. Nếu dùng `CrudRepository`, service sẽ nhận `Iterable<Customer>` và có thể chuyển sang List khi thật sự cần.

## 7. Xử lý ID thiếu và yêu cầu nghiệp vụ

`findAllById` bỏ qua ID không tồn tại. Điều này phù hợp khi caller chỉ cần những đối tượng có sẵn, nhưng không phù hợp nếu use case yêu cầu **mọi ID phải tồn tại**.

Ví dụ: một yêu cầu tạo nhóm khách hàng cần liên kết chính xác 3 khách hàng. Nếu chỉ tìm được 2, ứng dụng phải báo lỗi thay vì âm thầm tiếp tục với 2.

Có thể kiểm tra:

```java
public List<Customer> requireAllCustomers(List<Long> requestedIds) {
    List<Customer> found = customers.findAllById(requestedIds);

    Set<Long> foundIds = found.stream()
        .map(Customer::id)
        .collect(Collectors.toSet());

    List<Long> missingIds = requestedIds.stream()
        .filter(id -> !foundIds.contains(id))
        .distinct()
        .toList();

    if (!missingIds.isEmpty()) {
        throw new CustomerNotFoundException(missingIds);
    }

    return found;
}
```

Ví dụ này giả định ID đầu vào đã được validate không null. Nó không phụ thuộc thứ tự trả về của repository vì so sánh bằng tập ID.

Nếu đầu vào có ID trùng, `distinct()` làm danh sách lỗi không lặp lại. Nếu nghiệp vụ cần giữ số lần lặp để báo lỗi chi tiết, bỏ `distinct()`.

Cần nhớ rằng trạng thái tồn tại có thể thay đổi giữa lúc đọc và lúc thao tác tiếp theo nếu có transaction khác xóa dữ liệu. Foreign key, transaction isolation và xử lý concurrency vẫn cần được thiết kế phù hợp.

## 8. findAllById không phải query method findAllBy...

Tên `findAllById` là một phương thức CRUD có sẵn trong repository contract. Nó nhận iterable các ID và tìm aggregate theo định danh.

Trong khi đó, các method như:

```java
List<Customer> findAllByActiveTrue();

List<Customer> findAllByNameContainingIgnoreCase(String keyword);

List<Customer> findAllByEmailIn(Collection<String> emails);
```

là **query methods** được Spring Data phân tích tên để tạo truy vấn theo property của domain model.

Sự khác biệt:

| Phương thức | Nguồn gốc | Ý nghĩa |
| --- | --- | --- |
| `findAll()` | CRUD contract | Đọc tất cả aggregate. |
| `findAllById(ids)` | CRUD contract | Đọc aggregate theo tập ID. |
| `findAllByActiveTrue()` | Query method | Lọc theo property `active`. |
| `findAllByNameContainingIgnoreCase(name)` | Query method | Lọc theo quy tắc tên/property được hỗ trợ. |

Không cần đặt tên custom method là `findAllById` để tận dụng query derivation; method này đã có trong contract.

## 9. Khi dữ liệu lớn: pagination, sorting và query chuyên biệt

`findAll` không có tham số phân trang. Nếu bảng có nhiều dữ liệu, không nên tải tất cả chỉ để hiển thị một trang trên giao diện.

Một số hướng tiếp cận:

- Dùng repository contract/API phân trang và sắp xếp mà module hỗ trợ, với `Pageable`/`Sort` khi phù hợp.
- Dùng query có điều kiện để giảm tập dữ liệu ở database.
- Dùng projection/DTO cho read model chỉ cần một số cột.
- Dùng custom repository hoặc `NamedParameterJdbcOperations` khi truy vấn JOIN/tổng hợp cần kiểm soát SQL.
- Với batch processing, chia tập ID hoặc dữ liệu thành các lô có kích thước hợp lý.

Ví dụ một query method theo trạng thái:

```java
List<Customer> findByActiveTrue();
```

Nó tốt hơn việc `findAll()` rồi lọc `active` ở Java khi chỉ cần khách hàng đang hoạt động.

Nếu cần phân trang, cần chú ý phiên bản Spring Data và contract được sử dụng. Trong Spring Data 3.x, `PagingAndSortingRepository` là abstraction riêng; khi cần cả CRUD và paging, repository thường kế thừa cả hai interface tương ứng hoặc dùng kiểu repository chuyên biệt do module hỗ trợ.

### 9.1. findAllById với tập ID rất lớn

Nếu đầu vào chứa hàng chục nghìn hoặc hàng trăm nghìn ID, việc truyền tất cả vào một lời gọi có thể gặp giới hạn parameter của database/driver, tăng bộ nhớ và tạo truy vấn kém hiệu quả.

Có thể chia thành các batch:

```java
List<Customer> result = new ArrayList<>();

for (List<Long> batch : partition(ids, 500)) {
    result.addAll(repository.findAllById(batch));
}
```

`partition` là hàm chia danh sách thành các phần nhỏ; ví dụ chỉ minh họa cách tổ chức batch, không phải API Java tiêu chuẩn. Kích thước batch cần dựa trên database, driver, số cột và tải thực tế.

Nếu cần giữ thứ tự input, việc ghép kết quả từng batch vẫn không tự bảo đảm thứ tự bên trong từng batch. Cần sắp xếp lại theo ID sau khi tải.

## 10. findAll và aggregate có nhiều entity con

Trong Spring Data JDBC, repository quản lý aggregate root, không phải từng bảng độc lập. Nếu root có collection con được ánh xạ bằng `@MappedCollection`, việc đọc root cũng liên quan tới mapping các thành phần thuộc aggregate.

Ví dụ:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines = new ArrayList<>();
}
```

`findById(orderId)` đọc một aggregate PurchaseOrder cùng các thành phần thuộc nó. `findAll()` đọc tất cả PurchaseOrder và phần dữ liệu aggregate tương ứng. Vì vậy, nếu có nhiều đơn hàng và mỗi đơn chứa nhiều dòng hàng, chi phí thực tế có thể lớn hơn nhiều so với chỉ đọc bảng `purchase_orders`.

Nếu một màn hình chỉ cần số đơn hàng và tổng tiền, hãy cân nhắc projection hoặc query tổng hợp thay vì tải tất cả OrderLine thành domain objects.

### 10.1. Không dùng findAllById để truy vấn mọi quan hệ

Nếu muốn lấy tất cả Book thuộc một Author, nhưng chỉ có author ID, `findAllById` của `BookRepository` không phù hợp vì nó lọc theo **ID của Book**, không phải ID của Author.

Cần một query method hoặc truy vấn theo tham chiếu:

```java
List<Book> findByAuthor(AggregateReference<Author, Long> author);
```

hoặc custom query theo cột `author_id` tùy cách khai báo domain và khả năng query derivation. Ý nghĩa chính xác cần khớp mapping/property và phiên bản Spring Data JDBC đang dùng.

## 11. Kiểm thử ba phương thức

Một test slice Spring Data JDBC có thể xác nhận các hành vi chính:

```java
@DataJdbcTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void findsOneById() {
        Customer saved = customers.save(
            new Customer(null, "Lan", "lan@example.test", true)
        );

        Optional<Customer> found =
            customers.findById(saved.id());

        assertThat(found).contains(saved);
    }

    @Test
    void returnsEmptyWhenIdDoesNotExist() {
        assertThat(customers.findById(999L)).isEmpty();
    }

    @Test
    void findsAllCustomers() {
        customers.save(new Customer(null, "Lan", "lan@example.test", true));
        customers.save(new Customer(null, "Minh", "minh@example.test", false));

        assertThat(customers.findAll()).hasSize(2);
    }

    @Test
    void findsOnlyExistingIds() {
        Customer first = customers.save(
            new Customer(null, "Lan", "lan@example.test", true)
        );
        Customer second = customers.save(
            new Customer(null, "Minh", "minh@example.test", false)
        );

        List<Customer> found = customers.findAllById(
            List.of(first.id(), 999L, second.id())
        );

        assertThat(found)
            .extracting(Customer::id)
            .containsExactlyInAnyOrder(first.id(), second.id());
    }
}
```

Test minh họa cần schema và datasource test phù hợp. Nếu `@DataJdbcTest` mặc định thay datasource bằng embedded database, hãy cấu hình rõ database mong muốn khi dùng Testcontainers hoặc database test riêng.

Các assertion cố ý không kiểm tra thứ tự của `findAll` và `findAllById`. Nếu test dựa vào thứ tự ngẫu nhiên, nó có thể thất bại trên một database hoặc execution plan khác dù kết quả đúng theo contract.

### 11.1. Kiểm thử đầu vào không hợp lệ

Có thể bổ sung kiểm thử contract:

- `findById(null)` phải bị từ chối.
- `findAllById(null)` phải bị từ chối.
- `findAllById` với phần tử null phải bị từ chối.
- `findAllById(emptyList())` trả kết quả rỗng.
- Không tìm thấy ID không làm toàn bộ lời gọi thất bại; ID thiếu bị bỏ qua.

Không cần viết test cho mọi hành vi nội bộ của SQL. Tập trung vào contract mà ứng dụng dựa vào.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Gọi `findById` rồi gặp NullPointerException | Caller giả định Optional luôn có giá trị hoặc truyền ID null. | Kiểm tra Optional và validate ID. |
| Không tìm thấy entity nhưng mong repository ném lỗi | `findById` trả Optional rỗng. | Chuyển empty thành lỗi nghiệp vụ tại service khi cần. |
| `findAll` làm request chậm hoặc hết bộ nhớ | Đọc toàn bộ bảng và materialize nhiều aggregate. | Dùng filter, pagination, projection hoặc batch. |
| Kết quả `findAll` thay đổi thứ tự | Không có ORDER BY trong contract. | Sắp xếp rõ ràng bằng Sort/query. |
| Kết quả `findAllById` thiếu một số phần tử | ID không tồn tại bị bỏ qua. | So sánh tập ID yêu cầu và kết quả nếu tất cả đều bắt buộc tồn tại. |
| Kết quả `findAllById` không cùng thứ tự input | Contract không bảo đảm thứ tự. | Tái sắp xếp theo danh sách ID ban đầu. |
| Dùng `findAllById` để lọc theo foreign key | Method lọc theo ID của chính entity repository. | Dùng query method/custom query theo property tham chiếu. |
| Tải nhiều aggregate con ngoài nhu cầu | Repository đọc aggregate root theo mapping đầy đủ. | Thiết kế read query/projection riêng. |
| Truyền một tập ID rất lớn và truy vấn thất bại | Giới hạn parameter hoặc tài nguyên database/driver. | Chia batch hoặc dùng query chuyên biệt. |

## 13. Quy tắc chọn API trong thực tế

Trước khi gọi một phương thức, xác định rõ dữ liệu cần đọc:

1. **Một aggregate theo ID:** dùng `findById` và xử lý Optional.
2. **Toàn bộ aggregate trong một tập nhỏ:** dùng `findAll` nếu thực sự cần tất cả.
3. **Một tập aggregate đã biết ID:** dùng `findAllById`, nhưng không phụ thuộc thứ tự trả về.
4. **Tập dữ liệu lớn hoặc cần lọc/sắp xếp:** dùng query method, sorting/pagination hoặc custom query.
5. **Cần mọi ID đều phải tồn tại:** kiểm tra tập ID thiếu sau `findAllById`.
6. **Cần dữ liệu của aggregate khác:** truy xuất qua repository riêng hoặc read query kết hợp; không nhầm foreign key với aggregate child.
7. **Cần giữ thứ tự input:** tái sắp xếp kết quả theo danh sách ID gốc.
8. **Cần đọc ít cột hoặc dữ liệu tổng hợp:** dùng projection/DTO phù hợp thay vì materialize toàn bộ aggregate.

> **`findById` trả về Optional cho tối đa một aggregate; `findAll` đọc toàn bộ aggregate của repository; `findAllById` đọc những aggregate có ID trong tập đầu vào và bỏ qua ID không tồn tại.** Hai phương thức trả nhiều phần tử không bảo đảm thứ tự. Với dữ liệu lớn, hãy dùng truy vấn có điều kiện, pagination hoặc read model phù hợp thay vì tải toàn bộ aggregate.

### Tài liệu tham khảo

- [Spring Data Commons — Repository Core Concepts](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html): repository abstraction và các hợp đồng CRUD.
- [Spring Data Commons — CrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html): contract của `findById`, `findAll` và `findAllById`.
- [Spring Data Commons — ListCrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/ListCrudRepository.html): biến thể CRUD trả về List.
- [Spring Data JDBC — Reference Documentation](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repository và persistence aggregate trong Spring Data JDBC.
- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): query methods và truy vấn tùy chỉnh.
