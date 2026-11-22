# Optional, tập rỗng và quy ước kết quả không tồn tại

Trong **Spring Data Relational JDBC**, một truy vấn repository có thể tìm thấy một bản ghi, nhiều bản ghi hoặc không tìm thấy bản ghi nào. Kiểu kết quả của phương thức cần diễn đạt đúng những khả năng đó để code nghiệp vụ xử lý rõ ràng, tránh trả về `null` tùy tiện và tránh nhầm lẫn giữa “không có dữ liệu” với “truy vấn gặp lỗi”.

Ba quy ước cần nắm vững:

- **`Optional<T>`** diễn đạt một kết quả đơn có thể tồn tại hoặc không tồn tại.
- **Collection rỗng** diễn đạt truy vấn nhiều kết quả nhưng hiện không có phần tử phù hợp.
- **Exception** diễn đạt truy vấn không thể hoàn tất hoặc vi phạm quy tắc kết quả, chẳng hạn một phương thức yêu cầu tối đa một bản ghi nhưng thực tế có nhiều bản ghi.

Các quy ước này xuất hiện trong CRUD repository, derived query, truy vấn SQL tùy chỉnh và service layer. Hiểu đúng chúng giúp API repository có hợp đồng rõ ràng và giúp ứng dụng xử lý trường hợp thiếu dữ liệu theo đúng nghiệp vụ.

## 1. Ba trạng thái kết quả khác nhau

Giả sử ứng dụng có bảng `customer` và cần tìm khách hàng theo email. Một lời gọi repository có thể gặp các trường hợp:

| Kết quả | Ý nghĩa | Cách biểu diễn phù hợp |
| --- | --- | --- |
| Có đúng một khách hàng | Truy vấn tìm thấy bản ghi phù hợp | `Optional<Customer>` chứa Customer |
| Không có khách hàng | Không có hàng nào thỏa điều kiện | `Optional.empty()` |
| Database không truy cập được | Không thể thực hiện truy vấn | Exception của tầng truy cập dữ liệu |
| Có nhiều khách hàng trong truy vấn đơn | Kết quả vi phạm giả định “tối đa một” | Exception về kích thước kết quả |

Điểm quan trọng là **không tìm thấy dữ liệu không phải lỗi kỹ thuật**. Ví dụ tìm khách hàng theo email có thể không tìm thấy vì email chưa được đăng ký. Đây là một kết quả bình thường mà nghiệp vụ quyết định xử lý thế nào.

Ngược lại, nếu database mất kết nối, repository không thể xác định khách hàng có tồn tại hay không. Không nên biến lỗi kết nối thành `Optional.empty()`, vì như vậy ứng dụng có thể hiểu sai rằng email chưa được đăng ký.

## 2. `Optional<T>` trong Java

`java.util.Optional<T>` là một container có thể chứa một giá trị kiểu `T` hoặc không chứa giá trị nào.

~~~java
Optional<String> present = Optional.of("customer@example.com");
Optional<String> absent = Optional.empty();
~~~

Có thể hình dung:

~~~text
Optional<Customer>
       |
       +--- có giá trị ------> Customer object
       |
       +--- không có giá trị -> Optional.empty()
~~~

`Optional` giúp người gọi nhìn thấy ngay trong chữ ký phương thức rằng kết quả có thể vắng mặt. Thay vì phải nhớ một quy ước ngầm “nếu không tìm thấy thì trả null”, caller được yêu cầu xử lý trường hợp không có giá trị thông qua API của Optional.

### 2.1. Tạo Optional

| Phương thức | Ý nghĩa |
| --- | --- |
| `Optional.of(value)` | Tạo Optional có giá trị; ném `NullPointerException` nếu value là null |
| `Optional.ofNullable(value)` | Tạo Optional rỗng nếu value là null, ngược lại chứa value |
| `Optional.empty()` | Tạo Optional không có giá trị |

Ví dụ:

~~~java
Customer customer = findCustomerFromLegacyCode();

Optional<Customer> result = Optional.ofNullable(customer);
~~~

Trong code ứng dụng mới, nên tránh tạo ra `null` rồi mới bọc lại nếu có thể kiểm soát API từ đầu. Hãy trả `Optional.empty()` trực tiếp khi kết quả không tồn tại.

### 2.2. Đọc giá trị an toàn

Một số phương thức thường dùng:

~~~java
Optional<Customer> customer = repository.findById(customerId);

String label = customer
        .map(Customer::getName)
        .orElse("Khách hàng không xác định");
~~~

| Phương thức | Hành vi |
| --- | --- |
| `isPresent()` | Kiểm tra có giá trị |
| `isEmpty()` | Kiểm tra không có giá trị (Java 11+) |
| `ifPresent(action)` | Chạy action khi có giá trị |
| `ifPresentOrElse(action, emptyAction)` | Chọn hành động theo hai trường hợp (Java 9+) |
| `map(mapper)` | Biến đổi giá trị nếu có; kết quả mapper được bọc trong Optional |
| `flatMap(mapper)` | Biến đổi bằng hàm vốn đã trả Optional, tránh Optional lồng nhau |
| `filter(predicate)` | Giữ giá trị nếu thỏa điều kiện |
| `orElse(defaultValue)` | Trả giá trị chứa bên trong hoặc giá trị mặc định |
| `orElseGet(supplier)` | Trả giá trị bên trong hoặc gọi supplier để tạo mặc định |
| `orElseThrow()` | Trả giá trị hoặc ném `NoSuchElementException` |
| `orElseThrow(supplier)` | Trả giá trị hoặc ném exception do supplier tạo |
| `stream()` | Chuyển thành stream có 0 hoặc 1 phần tử (Java 9+) |

### 2.3. Phân biệt `orElse` và `orElseGet`

`orElse` nhận một giá trị đã được tính trước:

~~~java
Customer customer = repository.findById(id)
        .orElse(createGuestCustomer());
~~~

Biểu thức `createGuestCustomer()` được đánh giá trước khi gọi `orElse`, kể cả khi Optional đã có Customer.

`orElseGet` nhận một supplier:

~~~java
Customer customer = repository.findById(id)
        .orElseGet(this::createGuestCustomer);
~~~

Phương thức `createGuestCustomer` chỉ được gọi khi Optional rỗng. Khi tạo mặc định tốn chi phí, có side effect hoặc cần thực hiện truy vấn khác, `orElseGet` thường là lựa chọn phù hợp hơn.

### 2.4. Dùng `orElseThrow` khi thiếu dữ liệu là lỗi nghiệp vụ

~~~java
Customer customer = customerRepository.findById(customerId)
        .orElseThrow(() -> new CustomerNotFoundException(customerId));
~~~

Ở đây, repository diễn đạt khả năng không tồn tại; service quyết định rằng use case hiện tại bắt buộc phải có khách hàng. Việc ném exception là quyết định ở tầng nghiệp vụ, không phải vì repository mặc định xem mọi kết quả rỗng là lỗi.

Không nên dùng `get()` mà không kiểm tra:

~~~java
// Dễ ném NoSuchElementException nếu không có giá trị.
Customer customer = repository.findById(id).get();
~~~

Nếu nghiệp vụ yêu cầu dữ liệu phải tồn tại, `orElseThrow` cho phép đặt loại exception và thông điệp phù hợp. Nếu việc không có dữ liệu là bình thường, dùng `map`, `ifPresent` hoặc nhánh xử lý rõ ràng.

## 3. `CrudRepository.findById` trả về Optional

Spring Data JDBC cung cấp repository dựa trên `CrudRepository`:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Phương thức:

~~~java
Optional<Customer> findById(Long id);
~~~

Hợp đồng:

- Có hàng với ID tương ứng: trả Optional chứa Customer.
- Không có hàng: trả `Optional.empty()`.
- Truy vấn lỗi: ném exception truy cập dữ liệu phù hợp.
- Truyền ID null: tham số không hợp lệ, không phải cách yêu cầu tìm “bản ghi không có ID”.

Ví dụ:

~~~java
Optional<Customer> result = customerRepository.findById(42L);

if (result.isPresent()) {
    Customer customer = result.orElseThrow();
    System.out.println(customer.getName());
} else {
    System.out.println("Không tìm thấy khách hàng");
}
~~~

Có thể viết ngắn hơn:

~~~java
customerRepository.findById(42L)
        .ifPresent(customer -> sendWelcomeReminder(customer));
~~~

Nếu cần một giá trị trả về:

~~~java
Customer customer = customerRepository.findById(42L)
        .orElseThrow(() -> new CustomerNotFoundException(42L));
~~~

### 3.1. Không tìm thấy khác với ID null

`findById(null)` không mang ý nghĩa “tìm hàng không có khóa”. Khóa chính không null và hợp đồng repository yêu cầu ID hợp lệ. Truyền null là lỗi tham số và có thể dẫn đến `IllegalArgumentException`.

Tương tự, `existsById(null)` không phải cách kiểm tra một entity chưa được lưu. Nếu cần phân biệt entity mới, hãy dùng quy tắc ID/version hoặc factory của domain.

### 3.2. `existsById` khi chỉ cần biết có hay không

Nếu chỉ cần boolean:

~~~java
boolean exists = customerRepository.existsById(customerId);
~~~

`existsById` phù hợp khi caller không cần nội dung Customer. Nếu sau đó vẫn phải tải Customer, một lần `findById` thường đủ và tránh hai round-trip:

~~~java
// Có thể tạo hai truy vấn không cần thiết:
if (repository.existsById(id)) {
    Customer customer = repository.findById(id).orElseThrow();
}
~~~

Giữa hai câu lệnh, trạng thái database cũng có thể thay đổi. Khi cần object, gọi `findById` trực tiếp và xử lý Optional.

## 4. Kết quả nhiều bản ghi: dùng collection, không dùng Optional

Một truy vấn có thể tìm thấy không, một hoặc nhiều bản ghi. Nếu nghiệp vụ cho phép nhiều kết quả, kiểu trả về nên là collection:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    List<Customer> findByStatus(String status);
}
~~~

Hợp đồng của truy vấn collection:

- Có kết quả: collection chứa các phần tử phù hợp.
- Không có kết quả: collection rỗng.
- Không có trường hợp bình thường trả `null` thay cho collection rỗng.

Ví dụ:

~~~java
List<Customer> activeCustomers =
        customerRepository.findByStatus("ACTIVE");

if (activeCustomers.isEmpty()) {
    System.out.println("Chưa có khách hàng hoạt động");
}
~~~

Không cần:

~~~java
// Không nên thiết kế method collection trả null khi không có dữ liệu.
List<Customer> customers = findCustomers();
if (customers == null) {
    // ...
}
~~~

Một collection rỗng là kết quả bình thường, có thể lặp, stream, serialize hoặc nối tiếp với thao tác khác mà không cần nhánh xử lý null.

### 4.1. Khi nào dùng List, Set hoặc Iterable?

| Kiểu trả về | Khi nào phù hợp |
| --- | --- |
| `List<T>` | Caller cần collection có thứ tự do query quy định và cần các thao tác List |
| `Set<T>` | Caller cần ngữ nghĩa tập hợp không trùng lặp và việc loại trùng có chủ đích |
| `Collection<T>` | Caller chỉ cần một tập phần tử tổng quát |
| `Iterable<T>` | Hợp đồng CRUD cơ bản của Spring Data, ví dụ `findAll()` |
| `Page<T>` / `Slice<T>` | Truy vấn phân trang khi repository/query hỗ trợ kiểu tương ứng |

Đừng tự chuyển kết quả sang `Set` chỉ để “loại trùng” nếu điều đó che giấu lỗi dữ liệu hoặc làm mất thứ tự cần thiết. Quy tắc distinct và sort nên được xác định rõ trong query hoặc tầng nghiệp vụ.

## 5. Các phương thức CRUD và quy ước tập rỗng

Những phương thức CRUD cơ bản có kiểu kết quả khác nhau:

| Phương thức | Kiểu kết quả | Khi không có bản ghi |
| --- | --- | --- |
| `findById(id)` | `Optional<T>` | `Optional.empty()` |
| `findAll()` | `Iterable<T>` | Iterable rỗng |
| `findAllById(ids)` | `Iterable<T>` | Iterable rỗng nếu không tìm thấy bản ghi nào |
| `existsById(id)` | `boolean` | `false` |
| `count()` | `long` | `0` |
| `save(entity)` | `T` | Không phải truy vấn tìm kiếm; trả entity đã lưu theo cơ chế persistence |
| `deleteById(id)` | `void` | Nếu không tìm thấy ID, thao tác xóa không làm gì |

Các quy ước này giúp caller biết rõ kết quả vắng mặt được thể hiện như thế nào mà không cần đoán qua null.

### 5.1. `findAll()` không trả null

~~~java
Iterable<Customer> customers = customerRepository.findAll();

for (Customer customer : customers) {
    process(customer);
}
~~~

Nếu bảng không có hàng, vòng lặp chạy zero lần. Không cần kiểm tra `customers == null`.

Nếu caller cần List:

~~~java
List<Customer> customers = StreamSupport
        .stream(customerRepository.findAll().spliterator(), false)
        .toList();
~~~

Trong Java 16+, `Stream.toList()` trả danh sách không sửa được. Nếu cần danh sách mutable, có thể thu thập bằng `Collectors.toCollection(ArrayList::new)`. Chỉ chuyển đổi khi caller thực sự cần List; không tạo thêm bản sao không cần thiết.

### 5.2. `findAllById` có thể trả ít hơn số ID đầu vào

Giả sử:

~~~java
List<Long> ids = List.of(10L, 20L, 30L, 40L);
Iterable<Customer> found = customerRepository.findAllById(ids);
~~~

Nếu ID 20 và 40 không tồn tại, kết quả chỉ chứa các customer tìm thấy. Theo hợp đồng `CrudRepository`:

- Iterable trả về không null.
- Kết quả có thể chứa ít phần tử hơn số ID đầu vào.
- Không bảo đảm thứ tự phần tử trả về tương ứng thứ tự ID đầu vào.

Không được giả định:

~~~java
// Sai giả định: kết quả thứ hai luôn ứng với ids.get(1).
Customer second = toList(found).get(1);
~~~

Nếu cần ánh xạ theo ID, hãy tạo Map từ kết quả:

~~~java
Map<Long, Customer> byId = StreamSupport
        .stream(found.spliterator(), false)
        .collect(Collectors.toMap(Customer::getId, Function.identity()));
~~~

Sau đó truy cập theo ID:

~~~java
Customer customer10 = byId.get(10L);
Customer customer20 = byId.get(20L); // null nếu ID 20 không tồn tại
~~~

Nếu cần phân biệt rõ ID thiếu, có thể dùng `containsKey`:

~~~java
if (!byId.containsKey(20L)) {
    // ID 20 không có trong kết quả truy vấn.
}
~~~

Hoặc tạo một Map có giá trị Optional khi API nội bộ cần biểu diễn rõ sự vắng mặt. Tránh dùng `null` nếu có thể chuyển sang lookup method trả Optional.

### 5.3. Nếu nghiệp vụ yêu cầu tất cả ID đều tồn tại

`findAllById` không tự ném lỗi khi một vài ID không tồn tại. Service cần so sánh tập ID yêu cầu với tập ID tìm thấy:

~~~java
Set<Long> requestedIds = new HashSet<>(ids);
Set<Long> foundIds = byId.keySet();

Set<Long> missingIds = new HashSet<>(requestedIds);
missingIds.removeAll(foundIds);

if (!missingIds.isEmpty()) {
    throw new CustomerNotFoundException(missingIds);
}
~~~

Ví dụ này giả định ID đầu vào đã được kiểm tra không null và việc loại trùng là đúng với nghiệp vụ. Nếu thứ tự hoặc số lần xuất hiện của ID đầu vào có ý nghĩa, cần giữ thêm danh sách ban đầu thay vì chỉ dùng Set.

## 6. Derived query trả Optional hay collection?

Spring Data JDBC cho phép khai báo query method theo tên thuộc tính:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatus(String status);

    List<Customer> findByCity(String city);
}
~~~

Chọn kiểu trả về theo cardinality nghiệp vụ:

- `findByEmail`: nếu email là duy nhất, một kết quả tối đa, dùng `Optional<Customer>`.
- `findByStatus`: nhiều khách hàng có thể cùng trạng thái, dùng List.
- `findByCity`: nhiều khách hàng có thể ở cùng thành phố, dùng List hoặc kiểu collection phù hợp.

### 6.1. Optional đơn không có nghĩa database tự bảo đảm duy nhất

Giả sử email được kỳ vọng duy nhất:

~~~java
Optional<Customer> findByEmail(String email);
~~~

Chữ ký này diễn đạt query trả tối đa một Customer. Nó không tự tạo unique constraint trên cột email.

Nếu database có hai hàng cùng email, query thực tế có nhiều kết quả và phương thức đơn có thể ném `IncorrectResultSizeDataAccessException` (hoặc exception tương ứng trong hệ sinh thái Spring). Không nên chọn Optional chỉ vì “thường chỉ có một kết quả”.

Hãy bảo vệ giả định duy nhất bằng schema:

~~~sql
ALTER TABLE customer
    ADD CONSTRAINT uk_customer_email UNIQUE (email);
~~~

Trước khi thêm constraint vào bảng hiện hữu, cần xử lý dữ liệu trùng và xét quy tắc chuẩn hóa email (hoa/thường, khoảng trắng, collation) theo nghiệp vụ.

### 6.2. Nếu query có thể trả nhiều bản ghi

Nếu một email có thể được dùng ở nhiều tenant:

~~~java
List<Customer> findByEmail(String email);
~~~

Hoặc query theo cả phạm vi:

~~~java
Optional<Customer> findByTenantIdAndEmail(
        Long tenantId,
        String email
);
~~~

Với trường hợp thứ hai, schema nên có unique constraint trên `(tenant_id, email)` nếu đó là quy tắc nghiệp vụ.

## 7. Optional trong service layer

Repository trả Optional để biểu diễn kết quả dữ liệu. Service quyết định trường hợp thiếu dữ liệu có được chấp nhận không.

### 7.1. Không tìm thấy là bình thường

Ví dụ kiểm tra xem khách hàng có được đăng ký hay chưa:

~~~java
public boolean isRegistered(String email) {
    return customerRepository.findByEmail(email).isPresent();
}
~~~

Nếu chỉ cần boolean, có thể khai báo query/exists method phù hợp để không phải materialize toàn bộ entity.

### 7.2. Không tìm thấy là lỗi của use case

~~~java
public CustomerDetail getCustomerDetail(Long id) {
    Customer customer = customerRepository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

    return CustomerDetail.from(customer);
}
~~~

Exception miền có thể được controller hoặc exception handler ánh xạ thành HTTP 404. Repository không cần biết HTTP và không nên ném exception gắn với giao thức web.

### 7.3. Tạo mới khi chưa có

~~~java
public Customer registerIfAbsent(String email, String name) {
    return customerRepository.findByEmail(email)
            .orElseGet(() -> customerRepository.save(
                    Customer.create(email, name)
            ));
}
~~~

Đây là ví dụ ngắn về luồng kiểm tra rồi tạo. Trong hệ thống đồng thời, hai request vẫn có thể cùng thấy Optional rỗng rồi cùng insert. Unique constraint phải bảo vệ email; service cần bắt và diễn giải lỗi vi phạm constraint hoặc dùng chiến lược upsert phù hợp với database.

### 7.4. Biến đổi giá trị bằng map và flatMap

Nếu chỉ cần một thuộc tính:

~~~java
Optional<String> email = customerRepository.findById(id)
        .map(Customer::getEmail);
~~~

Nếu hàm tiếp theo cũng trả Optional:

~~~java
Optional<Address> address = customerRepository.findById(id)
        .flatMap(Customer::getPrimaryAddress);
~~~

Giả sử `getPrimaryAddress()` trả `Optional<Address>`. Dùng `flatMap` giúp kết quả là `Optional<Address>` thay vì `Optional<Optional<Address>>`.

### 7.5. Lọc điều kiện bổ sung

~~~java
Optional<Customer> activeCustomer = customerRepository.findById(id)
        .filter(Customer::isActive);
~~~

Kết quả rỗng có thể có hai nguyên nhân: không có ID hoặc khách hàng tồn tại nhưng không active. Nếu nghiệp vụ cần phân biệt hai trường hợp, đừng gộp chúng thành một Optional duy nhất; hãy xử lý theo từng bước:

~~~java
Customer customer = customerRepository.findById(id)
        .orElseThrow(() -> new CustomerNotFoundException(id));

if (!customer.isActive()) {
    throw new CustomerInactiveException(id);
}
~~~

## 8. Optional không thay thế mọi kiểu kết quả

`Optional` hữu ích cho kết quả đơn có thể thiếu, nhưng không nên dùng như container tổng quát cho mọi tình huống.

### 8.1. Không dùng Optional cho collection

Tránh:

~~~java
Optional<List<Customer>> findByStatus(String status);
~~~

Nếu không có khách hàng, trả `Optional.empty()` hay `Optional.of(List.of())`? Hai trạng thái này thường không mang ý nghĩa khác nhau. Collection rỗng đã diễn đạt “không có phần tử”, vì vậy nên dùng:

~~~java
List<Customer> findByStatus(String status);
~~~

### 8.2. Không dùng Optional để che lỗi kỹ thuật

Tránh bắt mọi exception rồi trả empty:

~~~java
public Optional<Customer> findCustomer(Long id) {
    try {
        return repository.findById(id);
    } catch (Exception ex) {
        return Optional.empty();
    }
}
~~~

Đoạn code này biến database outage, lỗi mapping, lỗi SQL và nhiều lỗi không liên quan thành “không tìm thấy”. Caller không thể phân biệt và có thể thực hiện hành động sai.

Chỉ chuyển một trường hợp lỗi thành kết quả nghiệp vụ khác khi có quy tắc rõ ràng và chỉ bắt đúng loại exception cần xử lý.

### 8.3. Không dùng Optional làm field persistence

Không nên khai báo:

~~~java
class Customer {
    private Optional<String> middleName;
}
~~~

Optional được thiết kế chủ yếu cho kiểu trả về, để caller nhìn thấy khả năng vắng mặt. Với entity Spring Data JDBC, dùng field kiểu giá trị thực tế có thể null theo mapping, hoặc mô hình hóa rõ hơn bằng value object/nullable semantics. Không yêu cầu framework lưu một container Optional như một cột đơn giản nếu mapping không hỗ trợ theo cách mong muốn.

Nếu một thuộc tính có thể không tồn tại, hãy diễn đạt ở API service/repository bằng Optional khi trả về một kết quả đơn; còn trong entity, dùng kiểu property phù hợp với mapping và quy tắc null của database.

### 8.4. Không dùng Optional làm tham số mặc định

Tránh API:

~~~java
void updateCustomer(Long id, Optional<String> newName);
~~~

Caller có thể truyền null thay cho Optional, tạo thêm một lớp vắng mặt. Thông thường, dùng overload, command object hoặc quy ước rõ ràng cho patch/update. Optional phù hợp hơn khi **phương thức trả về** một giá trị có thể không tồn tại.

## 9. Quy ước nullability của Spring Data

Một hợp đồng repository rõ ràng nên phân biệt:

- Giá trị trả về không được null.
- Giá trị có thể vắng mặt được diễn đạt bằng Optional.
- Collection trả về không null; không có phần tử thì collection rỗng.
- Tham số bắt buộc không được null.

Spring Data hỗ trợ nullability annotations để mô tả và kiểm tra hợp đồng null, ví dụ `@NonNullApi` ở cấp package và `@Nullable` trên phần tử cụ thể khi API thực sự cho phép null.

Ví dụ ý tưởng:

~~~java
@NonNullApi
package com.example.customer;

import org.springframework.lang.NonNullApi;
~~~

Với package áp dụng `@NonNullApi`, tham số và giá trị trả về mặc định được xem là non-null trừ khi đánh dấu `@Nullable`. Với repository method trả `Optional<T>`, bản thân Optional không null; sự vắng mặt nằm bên trong container.

Khi thiết kế API, tránh ba dạng biểu diễn đồng thời cho cùng một tình huống:

~~~text
null
Optional.empty()
empty collection
~~~

Mỗi loại có ngữ nghĩa riêng:

- `null`: thiếu hợp đồng rõ ràng hoặc một giá trị nullable được khai báo cụ thể.
- `Optional.empty()`: một kết quả đơn không tồn tại.
- Collection rỗng: không có phần tử nào trong tập kết quả.

### 9.1. Database NULL khác với không có hàng

Một hàng có thể tồn tại nhưng một cột có giá trị SQL `NULL`. Điều này khác với truy vấn không trả về hàng nào.

Ví dụ:

~~~sql
SELECT id, middle_name
FROM customer
WHERE id = 42;
~~~

Có hai trường hợp:

1. Không có customer ID 42: không có row kết quả, repository `findById` trả Optional rỗng.
2. Có customer ID 42 nhưng `middle_name IS NULL`: row tồn tại; entity được dựng với thuộc tính middleName không có giá trị theo mapping.

Không dùng Optional của entity để biểu diễn giá trị null bên trong một cột. Đó là hai cấp độ khác nhau.

## 10. Truy vấn SQL tùy chỉnh và kết quả rỗng

Với `@Query` hoặc `JdbcClient`, quy ước kết quả vẫn cần phù hợp với số hàng trả về.

Ví dụ một truy vấn tìm khách hàng:

~~~java
@Query("SELECT * FROM customer WHERE email = :email")
Optional<Customer> findByEmail(String email);
~~~

Nếu không có hàng, kết quả Optional rỗng. Nếu query trả nhiều hàng trong khi method yêu cầu một kết quả đơn, Spring Data có thể ném lỗi kích thước kết quả.

Với query nhiều hàng:

~~~java
@Query("SELECT * FROM customer WHERE status = :status")
List<Customer> findAllByStatus(String status);
~~~

Không có hàng thì List rỗng.

### 10.1. `COUNT` trả một hàng có giá trị 0

Một điểm dễ nhầm:

~~~sql
SELECT COUNT(*)
FROM customer
WHERE status = 'UNKNOWN';
~~~

Truy vấn aggregate `COUNT(*)` thông thường vẫn trả **một hàng** với giá trị `0` khi không có bản ghi phù hợp. Nó không trả zero row.

Vì vậy, nếu map kết quả count sang một giá trị số, kết quả là 0 chứ không phải Optional rỗng chỉ vì bảng không có hàng thỏa điều kiện.

### 10.2. `SUM` và `AVG` có thể trả SQL NULL

Khác với COUNT, một số aggregate function như `SUM` hoặc `AVG` có thể trả SQL NULL khi không có input phù hợp (trừ khi query dùng `COALESCE`). Ví dụ:

~~~sql
SELECT SUM(amount)
FROM payment
WHERE order_id = ?;
~~~

Nếu không có payment, kết quả có thể là một hàng với giá trị SQL NULL. Nếu nghiệp vụ muốn tổng bằng 0:

~~~sql
SELECT COALESCE(SUM(amount), 0)
FROM payment
WHERE order_id = ?;
~~~

Hãy phân biệt:

- Không có row kết quả.
- Có row với cột SQL NULL.
- Có row với giá trị số 0.

Ba tình huống này có ý nghĩa khác nhau và cần mapping/kiểu trả về phù hợp.

## 11. Trường hợp một kết quả nhưng dữ liệu có thể trùng

Giả sử:

~~~java
Optional<Customer> findByEmail(String email);
~~~

Method này ngụ ý query có tối đa một kết quả. Nếu dữ liệu trùng, framework không nên tùy tiện lấy hàng đầu tiên vì điều đó che giấu vi phạm tính duy nhất.

Hãy xác định quy tắc ở database:

~~~sql
ALTER TABLE customer
    ADD CONSTRAINT uk_customer_email UNIQUE (email);
~~~

Nếu tính duy nhất chỉ trong tenant:

~~~sql
ALTER TABLE customer
    ADD CONSTRAINT uk_customer_tenant_email
    UNIQUE (tenant_id, email);
~~~

Khi unique constraint được bảo vệ, Optional thể hiện chính xác hai trạng thái: có một khách hàng hoặc không có khách hàng.

Nếu nghiệp vụ thực sự cho phép nhiều hàng, đổi kiểu trả về thành collection hoặc thiết kế query giới hạn/kèm thứ tự một cách rõ ràng. Không giả vờ dữ liệu duy nhất chỉ bằng cách chọn Optional.

## 12. Kết hợp Optional với HTTP/API

Repository không nên biết HTTP status code. Service có thể chuyển Optional thành exception miền, controller advice ánh xạ exception thành HTTP response.

~~~java
@GetMapping("/customers/{id}")
public CustomerResponse getCustomer(@PathVariable Long id) {
    return customerService.getById(id);
}
~~~

Service:

~~~java
public CustomerResponse getById(Long id) {
    Customer customer = repository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

    return CustomerResponse.from(customer);
}
~~~

Exception handler:

~~~java
@ExceptionHandler(CustomerNotFoundException.class)
ResponseEntity<ProblemDetail> handleNotFound(
        CustomerNotFoundException exception
) {
    ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
    problem.setDetail(exception.getMessage());
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
}
~~~

Các lớp được rút gọn để tập trung vào luồng dữ liệu. Trong ứng dụng thật, cần khai báo imports, constructor injection và exception handler theo cấu trúc dự án.

Luồng:

~~~text
HTTP request
    |
    v
Controller
    |
    v
Service
    |
    v
Repository.findById()
    |
    +--- Optional có giá trị ---> tạo response
    |
    +--- Optional rỗng --------> ném domain exception
                                      |
                                      v
                              Exception handler
                                      |
                                      v
                                  HTTP 404
~~~

Nếu endpoint tìm kiếm danh sách không có kết quả, thường trả HTTP 200 với mảng rỗng thay vì 404, vì resource collection vẫn tồn tại nhưng hiện không có phần tử phù hợp. Quyết định API cụ thể phụ thuộc hợp đồng sản phẩm.

## 13. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Trả null khi không tìm thấy một entity | Caller phải tự đoán nullability | Trả `Optional<T>` |
| Trả Optional cho truy vấn nhiều hàng | Không thể diễn đạt đầy đủ tập kết quả | Trả List/Collection/Iterable |
| Trả null cho collection rỗng | Tạo nhánh null không cần thiết | Trả collection rỗng |
| Dùng `get()` không kiểm tra | Có thể ném NoSuchElementException khó hiểu | Dùng `orElseThrow` hoặc xử lý absence |
| Dùng `orElse(expensiveCall())` | Tính mặc định ngay cả khi đã có giá trị | Dùng `orElseGet` |
| Bắt mọi exception rồi trả Optional.empty | Che lỗi database, mapping và lập trình | Chỉ xử lý đúng loại lỗi được dự kiến |
| Chọn Optional vì nghĩ dữ liệu duy nhất | Dữ liệu trùng gây lỗi runtime | Unique constraint + method đơn |
| Dùng Optional<List<T>> | Hai lớp “rỗng” không cần thiết | Trả List rỗng |
| Dùng Optional làm field entity | Mapping và mô hình null phức tạp | Dùng property type phù hợp; Optional chủ yếu cho return |
| Cho rằng findAllById trả đúng thứ tự input | Ghép nhầm ID và entity | Tạo Map theo ID hoặc sắp xếp rõ ràng |
| Dùng existsById rồi findById | Thêm round-trip và tạo race window | Gọi findById nếu cần entity |
| Nhầm SQL NULL với không có row | Diễn giải sai dữ liệu | Phân biệt nullable column và absence của row |

## 14. Tình huống thực hành

### Tình huống A — Tìm tài khoản theo ID

Use case hiển thị chi tiết khách hàng theo ID. ID không tồn tại thì trả 404.

**Cách làm:** repository trả `Optional<Customer>`; service dùng `orElseThrow` để ném `CustomerNotFoundException`; tầng web ánh xạ exception thành 404.

### Tình huống B — Tìm đơn theo khách hàng

Một khách hàng có thể chưa có đơn hàng hoặc có nhiều đơn.

**Cách làm:** method trả `List<PurchaseOrder>`. Khi chưa có đơn, trả list rỗng. Không dùng `Optional<List<PurchaseOrder>>`.

### Tình huống C — Tải nhiều ID được chọn

Request chứa 10 customer ID; database chỉ có 8 hàng.

**Cách làm:** `findAllById` trả các hàng tìm thấy. Nếu nghiệp vụ chấp nhận thiếu, xử lý tập kết quả. Nếu bắt buộc đủ 10, so sánh requested IDs với found IDs và trả lỗi rõ ràng.

### Tình huống D — Tìm email duy nhất

Method `findByEmail` trả Optional nhưng database có thể chứa email trùng do dữ liệu cũ.

**Cách làm:** làm sạch dữ liệu, xác định quy tắc chuẩn hóa và thêm unique constraint. Nếu trùng là hợp lệ theo tenant, bổ sung tenant vào điều kiện query và constraint.

### Tình huống E — Không tìm thấy hay database bị lỗi?

Một endpoint trả “không có khách hàng” khi database đang mất kết nối.

**Vấn đề:** code đã bắt exception quá rộng và chuyển thành Optional rỗng.

**Cách làm:** để exception hạ tầng được xử lý theo chính sách lỗi hệ thống; chỉ Optional rỗng biểu diễn truy vấn thành công nhưng không có hàng phù hợp.

## 15. Quy trình chọn kiểu kết quả cho repository

Khi khai báo một query method, hãy xác định:

1. **Query có thể trả bao nhiêu hàng?** Không hàng, tối đa một hay nhiều hàng?
2. **Không có hàng có phải tình huống bình thường không?** Nếu một kết quả đơn có thể thiếu, dùng Optional.
3. **Nhiều kết quả không có phần tử thì sao?** Dùng collection rỗng.
4. **Tính duy nhất được bảo vệ ở đâu?** Nếu method giả định một hàng, database cần unique constraint phù hợp.
5. **Lỗi kỹ thuật được xử lý thế nào?** Không chuyển lỗi truy cập dữ liệu thành absence.
6. **Service cần hành vi gì khi thiếu?** Trả kết quả vắng mặt, dùng mặc định, bỏ qua hay ném exception miền.
7. **Có cần phân biệt SQL NULL với không có row không?** Chọn projection và kiểu dữ liệu phù hợp.
8. **Truy vấn nhiều ID có thể thiếu hoặc đảo thứ tự không?** Không dựa vào thứ tự input nếu hợp đồng không bảo đảm.

## Ghi nhớ

Trong Spring Data JDBC, `Optional<T>` là hợp đồng rõ ràng cho một kết quả đơn có thể không tồn tại; collection rỗng là hợp đồng tự nhiên cho truy vấn nhiều kết quả không tìm thấy phần tử; exception dành cho lỗi truy vấn hoặc vi phạm giả định về cardinality. `findById` trả Optional, `findAll` và `findAllById` trả tập kết quả có thể rỗng, còn `existsById` và `count` trả boolean/số lượng.

Hãy để repository diễn đạt trạng thái dữ liệu, service quyết định ý nghĩa nghiệp vụ và database bảo vệ những giả định như tính duy nhất. Khi giữ rõ ba trách nhiệm đó, code không phải đoán null, không che lỗi hạ tầng và dễ xử lý chính xác cả trường hợp có dữ liệu lẫn không có dữ liệu.
