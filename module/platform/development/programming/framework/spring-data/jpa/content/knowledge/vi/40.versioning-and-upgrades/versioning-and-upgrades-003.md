# Thay đổi phân cấp Repository và hợp đồng phương thức giữa các dòng phiên bản

## 1. Vì sao cần kiểm tra Repository khi nâng cấp?

Spring Data Repository được ghép từ nhiều interface nhỏ. Mỗi interface đóng góp một nhóm hợp đồng:

- \`Repository<T, ID>\`: interface đánh dấu, xác định domain type và kiểu khóa.
- \`CrudRepository<T, ID>\`: thao tác tạo, đọc, cập nhật và xóa.
- \`PagingAndSortingRepository<T, ID>\`: truy vấn có phân trang hoặc sắp xếp.
- \`ListCrudRepository<T, ID>\`: CRUD với các phương thức nhiều kết quả trả về \`List\`.
- \`ListPagingAndSortingRepository<T, ID>\`: sắp xếp và phân trang, với \`List\` cho truy vấn sắp xếp không phân trang.
- \`JpaRepository<T, ID>\`: kết hợp các hợp đồng trên và bổ sung thao tác riêng của JPA.

Một thay đổi trong quan hệ kế thừa có thể làm repository cũ mất một nhóm method dù tên interface vẫn tồn tại. Khi nâng cấp, cần kiểm tra cả interface repository kế thừa và kiểu trả về mà caller đang sử dụng.

Thay đổi quan trọng nhất giữa Spring Data 2.x và 3.x là \`PagingAndSortingRepository\` không còn kế thừa \`CrudRepository\`. Spring Data 3.0 cũng bổ sung các interface trả về \`List\`. Spring Data 4.x giữ mô hình tách này.

## 2. Phân cấp Repository trong Spring Data 2.x

### 2.1. PagingAndSortingRepository kế thừa CrudRepository

Trong Spring Data 2.x, phân cấp phổ biến là:

```text
Repository<T, ID>
        |
        v
CrudRepository<T, ID>
        |
        v
PagingAndSortingRepository<T, ID>
```

Do \`PagingAndSortingRepository\` kế thừa \`CrudRepository\`, repository chỉ cần khai báo:

```java
public interface CustomerRepository
        extends PagingAndSortingRepository<Customer, Long> {
}
```

Repository này có cả hai nhóm phương thức:

- CRUD: \`save\`, \`saveAll\`, \`findById\`, \`findAll\`, \`deleteById\`, \`delete\`, \`count\`...
- Paging/sorting: \`findAll(Pageable)\`, \`findAll(Sort)\`.

Ví dụ caller:

```java
customerRepository.save(customer);

Optional<Customer> customer =
    customerRepository.findById(10L);

Page<Customer> page =
    customerRepository.findAll(PageRequest.of(0, 20));

Iterable<Customer> sorted =
    customerRepository.findAll(Sort.by("name"));
```

Mã nguồn dựa trên quan hệ kế thừa này biên dịch với Spring Data 2.x.

### 2.2. Hợp đồng trả về của CrudRepository

Các phương thức có nhiều kết quả trong \`CrudRepository\` sử dụng \`Iterable\`:

```java
public interface CrudRepository<T, ID> {

    <S extends T> S save(S entity);

    <S extends T> Iterable<S> saveAll(Iterable<S> entities);

    Optional<T> findById(ID id);

    Iterable<T> findAll();

    Iterable<T> findAllById(Iterable<ID> ids);

    long count();

    void deleteById(ID id);
}
```

Các phương thức đơn lẻ như \`findById\`, \`save\`, \`count\` và \`deleteById\` không thay đổi ý nghĩa chỉ vì repository có thêm paging/sorting.

### 2.3. Hợp đồng của PagingAndSortingRepository

Trong dòng 2.x, interface này bổ sung:

```java
Page<T> findAll(Pageable pageable);

Iterable<T> findAll(Sort sort);
```

- \`Page<T>\` chứa nội dung trang cùng metadata như tổng số phần tử và tổng số trang.
- \`Iterable<T>\` chứa các entity đã được sắp xếp.
- \`findAll(Sort)\` không phân trang; nếu dữ liệu lớn, phương thức này có thể tải toàn bộ kết quả.

## 3. Thay đổi quan trọng từ Spring Data 3.0

### 3.1. PagingAndSortingRepository không còn kế thừa CrudRepository

Từ Spring Data 3.0, \`PagingAndSortingRepository\` là một repository fragment độc lập, trực tiếp mở rộng \`Repository\`:

```text
                 Repository<T, ID>
                   /          \\
                  v            v
       CrudRepository       PagingAndSortingRepository
                  |
                  v
          ListCrudRepository

       PagingAndSortingRepository
                  |
                  v
       ListPagingAndSortingRepository
```

Do hai nhánh CRUD và paging/sorting đã tách nhau, khai báo cũ:

```java
public interface CustomerRepository
        extends PagingAndSortingRepository<Customer, Long> {
}
```

không còn cung cấp \`save()\`, \`findById()\`, \`deleteById()\` hoặc các CRUD method khác trong Spring Data 3.x và 4.x. Interface này chỉ cung cấp hợp đồng paging/sorting.

Đây là thay đổi có thể làm mã nguồn cũ không biên dịch dù tên \`PagingAndSortingRepository\` vẫn tồn tại. Các dòng như:

```java
customerRepository.save(customer);
customerRepository.findById(10L);
```

sẽ báo lỗi nếu biến hoặc bean được khai báo chỉ bằng kiểu \`PagingAndSortingRepository<Customer, Long>\`.

### 3.2. Kết hợp hai nhánh sau khi nâng cấp

Nếu cần kiểu trả về CRUD truyền thống là \`Iterable\`, hãy kế thừa cả hai interface:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                PagingAndSortingRepository<Customer, Long> {
}
```

Nếu muốn các phương thức nhiều kết quả trả về \`List\`, dùng hai interface List:

```java
public interface CustomerRepository
        extends ListCrudRepository<Customer, Long>,
                ListPagingAndSortingRepository<Customer, Long> {
}
```

Không cần thêm cả \`CrudRepository\` lẫn \`ListCrudRepository\` vào cùng một khai báo. \`ListCrudRepository\` đã kế thừa \`CrudRepository\` và ghi đè các phương thức nhiều kết quả bằng kiểu trả về \`List\`.

### 3.3. Các interface List được bổ sung

Spring Data 3.0 giới thiệu các interface List tương ứng:

| Interface | Phương thức nhiều kết quả |
|---|---|
| \`CrudRepository\` | \`Iterable\` |
| \`ListCrudRepository\` | \`List\` |
| \`PagingAndSortingRepository\` | \`Iterable\` cho \`findAll(Sort)\`, \`Page\` cho \`findAll(Pageable)\` |
| \`ListPagingAndSortingRepository\` | \`List\` cho \`findAll(Sort)\`, \`Page\` cho \`findAll(Pageable)\` |

Ví dụ \`ListCrudRepository\`:

```java
public interface ListCrudRepository<T, ID>
        extends CrudRepository<T, ID> {

    List<T> findAll();

    List<T> findAllById(Iterable<ID> ids);

    <S extends T> List<S> saveAll(Iterable<S> entities);
}
```

Các phương thức đơn lẻ như \`findById()\`, \`save()\`, \`count()\` và \`deleteById()\` tiếp tục được kế thừa từ \`CrudRepository\`.

Ví dụ \`ListPagingAndSortingRepository\`:

```java
public interface ListPagingAndSortingRepository<T, ID>
        extends PagingAndSortingRepository<T, ID> {

    List<T> findAll(Sort sort);
}
```

Phương thức phân trang vẫn trả về \`Page<T>\`; interface List không biến \`Page<T>\` thành \`List<T>\`.

## 4. Phân cấp JpaRepository qua các dòng phiên bản

### 4.1. JpaRepository trong Spring Data JPA 2.x

Trong Spring Data JPA 2.x, \`JpaRepository\` kế thừa \`PagingAndSortingRepository\` và \`QueryByExampleExecutor\`. Vì \`PagingAndSortingRepository\` lúc đó kế thừa \`CrudRepository\`, \`JpaRepository\` có đầy đủ CRUD và paging/sorting.

Ngoài ra, \`JpaRepository\` khai báo lại một số phương thức với kiểu trả về \`List\`, chẳng hạn:

- \`List<T> findAll()\`
- \`List<T> findAll(Sort sort)\`
- \`List<T> findAllById(Iterable<ID> ids)\`
- \`List<S> saveAll(Iterable<S> entities)\`

Vì vậy, caller dùng trực tiếp \`JpaRepository\` trong 2.x thường đã nhận được \`List\` ở các phương thức này, dù \`CrudRepository\` tổng quát trả về \`Iterable\`.

### 4.2. JpaRepository từ Spring Data JPA 3.x

Từ 3.0, \`JpaRepository\` kết hợp trực tiếp các interface List:

```java
@NoRepositoryBean
public interface JpaRepository<T, ID>
        extends ListCrudRepository<T, ID>,
                ListPagingAndSortingRepository<T, ID>,
                QueryByExampleExecutor<T> {
    // JPA-specific methods
}
```

Các nhóm phương thức mà repository JPA cung cấp gồm:

- CRUD cơ bản thông qua \`ListCrudRepository\` và \`CrudRepository\`.
- Paging/sorting thông qua \`ListPagingAndSortingRepository\` và \`PagingAndSortingRepository\`.
- Query by Example thông qua \`QueryByExampleExecutor\`.
- JPA-specific operations như \`flush()\`, \`saveAndFlush()\`, \`saveAllAndFlush()\`, batch delete và \`getReferenceById()\`.

Vì \`JpaRepository\` đã ghép cả hai nhánh, khai báo thông thường vẫn đơn giản:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Đây là lựa chọn phù hợp cho repository JPA cần CRUD, paging/sorting và các thao tác đặc thù JPA.

### 4.3. JpaRepository trong Spring Data JPA 4.x

Spring Data JPA 4.x tiếp tục giữ mô hình phân tách từ 3.0. API hiện hành vẫn khai báo \`JpaRepository\` trên \`ListCrudRepository\`, \`ListPagingAndSortingRepository\` và \`QueryByExampleExecutor\`.

Do đó, quy tắc migration của 3.x vẫn áp dụng ở 4.x:

- \`PagingAndSortingRepository\` độc lập với CRUD.
- \`ListCrudRepository\` kế thừa \`CrudRepository\`.
- \`ListPagingAndSortingRepository\` kế thừa \`PagingAndSortingRepository\`.
- \`JpaRepository\` kết hợp các hợp đồng cần thiết cho JPA.

Không nên hiểu Spring Data 4.x đã khôi phục quan hệ kế thừa cũ của 2.x.

### 4.4. Bảng so sánh nhanh

| Hợp đồng | Spring Data 2.x | Spring Data 3.x | Spring Data 4.x |
|---|---|---|---|
| \`PagingAndSortingRepository\` kế thừa CRUD | Có | Không | Không |
| \`ListCrudRepository\` | Chưa có | Có | Có |
| \`ListPagingAndSortingRepository\` | Chưa có | Có | Có |
| \`JpaRepository\` có CRUD và paging | Có | Có | Có |
| \`JpaRepository.findAll()\` | \`List<T>\` | \`List<T>\` | \`List<T>\` |
| \`JpaRepository.findAll(Sort)\` | \`List<T>\` | \`List<T>\` | \`List<T>\` |
| \`JpaRepository.findAll(Pageable)\` | \`Page<T>\` | \`Page<T>\` | \`Page<T>\` |
| \`JpaRepository.saveAll(...)\` | \`List<S>\` | \`List<S>\` | \`List<S>\` |

Bảng mô tả các interface đồng bộ trong Spring Data Commons/JPA. Các module reactive và coroutine có những interface tương ứng riêng.

## 5. Hợp đồng kiểu trả về cần nắm rõ

### 5.1. Iterable và List

\`Iterable<T>\` là hợp đồng tổng quát, cho phép duyệt kết quả mà không yêu cầu cấu trúc danh sách. \`List<T>\` cung cấp thêm truy cập theo chỉ số và các thao tác của Collection/List.

```java
CrudRepository<Customer, Long> crudRepository = ...;

Iterable<Customer> all = crudRepository.findAll();

ListCrudRepository<Customer, Long> listRepository = ...;

List<Customer> list = listRepository.findAll();
```

Nếu caller chỉ cần duyệt, \`Iterable\` thường đủ. Nếu caller cần index hoặc truyền thẳng vào API nhận \`List\`, dùng hợp đồng List phù hợp.

Không ép kiểu tùy tiện:

```java
List<Customer> customers =
    (List<Customer>) crudRepository.findAll();
```

\`CrudRepository.findAll()\` chỉ cam kết trả về \`Iterable\`; implementation không bắt buộc phải trả một đối tượng \`List\`. Hãy dùng \`ListCrudRepository\` hoặc khai báo kiểu nhận là \`Iterable\`.

### 5.2. Page và Slice

\`Page<T>\` chứa nội dung trang cùng metadata như tổng phần tử và tổng trang. Việc tạo \`Page\` thường cần thêm count query để xác định tổng số kết quả, tùy cách Spring Data tối ưu và nội dung trang.

\`Slice<T>\` tập trung vào nội dung và thông tin còn trang tiếp theo hay không; nó không yêu cầu tổng số phần tử toàn bộ tập kết quả.

```java
Page<Customer> page =
    repository.findByStatus(
        CustomerStatus.ACTIVE,
        PageRequest.of(0, 20)
    );

List<Customer> content = page.getContent();
boolean hasNext = page.hasNext();
long total = page.getTotalElements();
```

Nếu API cần hiển thị tổng số trang, dùng \`Page<T>\`. Nếu chỉ cần nút “Tải thêm”, cân nhắc \`Slice<T>\` để tránh chi phí count không cần thiết.

### 5.3. Optional và kết quả đơn

Các phương thức như \`findById(ID)\` tiếp tục trả về \`Optional<T>\` trong các dòng phiên bản. Optional thể hiện rõ trường hợp không tìm thấy entity:

```java
Optional<Customer> customer = repository.findById(id);

customer.ifPresent(this::sendWelcomeMessage);
```

Với query method trả về entity đơn, Spring Data kỳ vọng tối đa một kết quả. Nếu query trả nhiều hơn một kết quả, framework ném lỗi kích thước kết quả không hợp lệ.

### 5.4. save và saveAll

Hợp đồng \`save\` vẫn là:

```java
<S extends T> S save(S entity);
```

Dùng đối tượng trả về từ \`save\` cho các thao tác tiếp theo:

```java
Customer saved = repository.save(customer);

Long id = saved.getId();
```

Với JPA, khi entity đã tồn tại, thao tác có thể dùng \`EntityManager.merge()\`. Kết quả merge là managed instance; nó có thể khác object truyền vào. Vì vậy, không giả định \`save(entity)\` luôn trả lại cùng reference.

\`saveAll\` trong \`CrudRepository\` trả về \`Iterable<S>\`; \`ListCrudRepository\` và \`JpaRepository\` cung cấp hợp đồng \`List<S>\`.

### 5.5. findAllById không bảo đảm thứ tự đầu vào

\`findAllById(ids)\` trả về các entity tìm thấy. Nếu một số ID không tồn tại, kết quả có thể ít phần tử hơn số ID đầu vào. Thứ tự kết quả không được bảo đảm trùng với thứ tự ID truyền vào.

Nếu API cần đúng thứ tự đầu vào, hãy tự lập bản đồ theo ID sau khi truy vấn hoặc dùng query có \`ORDER BY\` rõ ràng.

## 6. Các phương thức JpaRepository cần chú ý khi nâng cấp

### 6.1. getOne và getById chuyển sang getReferenceById

Các phương thức \`getOne(ID)\` và \`getById(ID)\` đã deprecated; API khuyến nghị dùng \`getReferenceById(ID)\`.

```java
Customer reference = repository.getReferenceById(customerId);
```

Phương thức này trả về entity reference. Provider thường có thể trả proxy mà chưa đọc row ngay; nếu ID không tồn tại, lỗi có thể chỉ xuất hiện khi truy cập dữ liệu proxy. Hành vi chính xác phụ thuộc provider.

Nếu cần kiểm tra entity có tồn tại và lấy dữ liệu ngay, dùng:

```java
Customer customer = repository.findById(customerId)
    .orElseThrow(() -> new CustomerNotFoundException(customerId));
```

Không thay \`findById\` bằng \`getReferenceById\` nếu nghiệp vụ cần xử lý trường hợp không tồn tại ngay tại điểm gọi.

### 6.2. deleteInBatch chuyển sang deleteAllInBatch

\`deleteInBatch(Iterable<T>)\` đã deprecated; dùng \`deleteAllInBatch(Iterable<T>)\`:

```java
repository.deleteAllInBatch(customers);
```

Đây là bulk operation. Nó không có cùng semantics với việc xóa từng entity:
- Không thực hiện cascade semantics như xóa từng entity theo JPA.
- Không phát các lifecycle event tương ứng cho từng entity.
- Persistence context cấp một có thể không đồng bộ với database sau câu lệnh bulk.
- Nên flush thay đổi đang chờ trước thao tác và clear/refresh entity bị ảnh hưởng sau đó khi cần.

Nếu cần cascade, callback hoặc lifecycle event, dùng \`deleteAll(entities)\` phù hợp thay vì batch delete.

### 6.3. saveAndFlush và saveAllAndFlush

Các phương thức này có từ Spring Data JPA 2.5:

```java
Customer saved = repository.saveAndFlush(customer);

List<Customer> savedCustomers =
    repository.saveAllAndFlush(customers);
```

\`flush()\` đẩy thay đổi đang chờ trong persistence context xuống database. Nó không đồng nghĩa với commit transaction. Transaction vẫn có thể rollback sau khi flush.

Không gọi \`saveAndFlush\` sau mọi \`save\` chỉ vì muốn chắc chắn dữ liệu được lưu. Flush thường xuyên có thể làm giảm khả năng batching và tăng round-trip.

## 7. Tác động của thay đổi phân cấp tới repository tùy biến

### 7.1. Repository chỉ cần CRUD

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Hoặc dùng List contract:

```java
public interface CustomerRepository
        extends ListCrudRepository<Customer, Long> {
}
```

### 7.2. Repository chỉ cần paging/sorting

Nếu repository chỉ cung cấp đọc có phân trang/sắp xếp, có thể kế thừa:

```java
public interface CustomerBrowseRepository
        extends PagingAndSortingRepository<Customer, Long> {
}
```

Trong 3.x/4.x, interface này không có \`save\` hoặc \`delete\`. Đây có thể là lựa chọn tốt nếu muốn giới hạn API của thành phần chỉ đọc.

### 7.3. Repository cần CRUD và paging/sorting

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                PagingAndSortingRepository<Customer, Long> {
}
```

Hoặc List variant:

```java
public interface CustomerRepository
        extends ListCrudRepository<Customer, Long>,
                ListPagingAndSortingRepository<Customer, Long> {
}
```

### 7.4. Repository JPA thông thường

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Không cần khai báo thêm \`CrudRepository\`, \`PagingAndSortingRepository\` hoặc các List variant vì \`JpaRepository\` đã kết hợp chúng.

### 7.5. Generic base repository

Có thể tạo interface cơ sở để chia sẻ hợp đồng giữa nhiều repository:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends ListCrudRepository<T, ID>,
                ListPagingAndSortingRepository<T, ID> {
}
```

Repository cụ thể:

```java
public interface CustomerRepository
        extends BaseRepository<Customer, Long> {
}
```

\`@NoRepositoryBean\` ngăn Spring Data cố tạo bean cho interface generic trung gian khi chưa có domain type cụ thể.

Nếu base repository chỉ dùng cho JPA và cần các method như \`flush()\`, có thể kế thừa \`JpaRepository<T, ID>\` thay cho hai interface List ở trên.

## 8. Ảnh hưởng của Java và Jakarta khi chuyển từ 2.x sang 3.x

Thay đổi phân cấp Repository không phải thay đổi duy nhất ở Spring Data 3.0. Đây là bước nâng cấp nền tảng lớn. Spring Data 3.x yêu cầu Spring Framework 6.x và Java 17+.

| Hạng mục | Spring Data JPA 2.7.x | Spring Data JPA 3.x |
|---|---|---|
| Spring Framework | 5.3.x | 6.x |
| Java baseline | Java 8+ tùy bản | Java 17+ |
| JPA namespace | \`javax.persistence\` | \`jakarta.persistence\` |
| Jakarta EE | Java EE/Jakarta EE 8 era | Jakarta EE 9+ |
| Hibernate thường đi cùng Spring Boot | Hibernate 5.x | Hibernate 6.x |

Ví dụ import entity phải đổi:

```java
// Spring Data JPA 2.x / JPA 2.x
import javax.persistence.Entity;
import javax.persistence.Id;
```

```java
// Spring Data JPA 3.x / Jakarta Persistence
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
```

Không thể giữ đồng thời hai namespace cho cùng một entity mapping rồi kỳ vọng provider tự chuyển đổi. Cần nâng cấp import, dependency, converter, annotation và thư viện tích hợp JPA cùng lúc.

### 8.1. Spring Data 4.x và Spring Framework 7

Spring Data 4.0 thuộc thế hệ Spring Framework 7, với nền Jakarta EE 11 và Jakarta Persistence 3.2. Java 17 vẫn là baseline của thế hệ Framework 7; Java 25 là LTS mới được hỗ trợ.

Với 4.x, cần kiểm tra:
- Spring Boot 4.x/Spring Framework 7 compatibility.
- Jakarta Persistence 3.2 và các thư viện tích hợp.
- JSpecify null-safety annotations trong API mới.
- AOT repository processing nếu ứng dụng dùng AOT/native image.
- Các deprecated API còn tồn tại trong version cụ thể.

Đối với phân cấp repository, 4.x vẫn giữ mô hình đã tách từ 3.0. Không cần đổi từ List interfaces quay lại kiểu kế thừa 2.x.

## 9. Cách nâng cấp Repository an toàn

### 9.1. Kiểm kê interface đang kế thừa PagingAndSortingRepository

Tìm toàn bộ khai báo dạng:

```java
interface XRepository
        extends PagingAndSortingRepository<X, Long> {
}
```

Phân loại:
- Chỉ đọc và paging/sorting: có thể giữ nguyên.
- Cần CRUD: thêm \`CrudRepository\` hoặc \`ListCrudRepository\`.
- Repository JPA cần đầy đủ JPA API: cân nhắc \`JpaRepository\`.

### 9.2. Kiểm tra caller đang phụ thuộc CRUD kế thừa

Tìm các call site:
- \`save()\`, \`saveAll()\`
- \`findById()\`, \`findAll()\`, \`findAllById()\`
- \`existsById()\`, \`count()\`
- \`delete()\`, \`deleteById()\`, \`deleteAll()\`

Nếu biến được khai báo bằng \`PagingAndSortingRepository\`, các CRUD method sẽ không còn khả dụng từ 3.x trở lên. Thay kiểu khai báo hoặc thay interface repository theo đúng hợp đồng cần thiết.

### 9.3. Chọn Iterable hay List có chủ đích

Nếu caller chỉ cần duyệt, \`Iterable\` vẫn là hợp đồng phù hợp. Nếu caller cần index, dùng List variant hoặc \`JpaRepository\`.

Không đổi mọi interface sang List chỉ vì muốn tránh vòng lặp. Một truy vấn không phân trang trả hàng trăm nghìn dòng vẫn có thể tiêu tốn nhiều bộ nhớ dù kiểu trả về là \`List\`.

### 9.4. Thay deprecated methods

Tìm và xử lý:
- \`getOne(id)\` → \`getReferenceById(id)\`.
- \`getById(id)\` → \`getReferenceById(id)\`.
- \`deleteInBatch(entities)\` → \`deleteAllInBatch(entities)\`.

Sau khi thay, kiểm tra lại semantics:
- Reference có thể chưa được khởi tạo.
- Batch delete không chạy cascade/lifecycle như xóa entity thông thường.
- Bulk operation có thể làm persistence context stale.

### 9.5. Căn chỉnh dependency

Không nâng cấp riêng \`spring-data-jpa\` mà để \`spring-data-commons\` ở một dòng phiên bản khác. Hai module có quan hệ phụ thuộc chặt chẽ.

Với ứng dụng Spring Boot:
- Ưu tiên Spring Boot dependency management/BOM.
- Chọn Spring Boot line hỗ trợ Spring Data train mong muốn.
- Chỉ override version khi đã kiểm tra compatibility matrix.
- Không trộn Spring Framework 5 với Spring Data 3 hoặc Framework 6 với các dependency Jakarta không tương thích.

Với ứng dụng tự quản lý dependency, dùng Spring Data release train BOM tương ứng để các module Spring Data đồng bộ.

### 9.6. Compatibility baseline và Spring Boot BOM

Khi nâng cấp Spring Data, không chọn version riêng lẻ cho từng thư viện. Spring Boot phát hành một bộ dependency đã được kiểm thử cùng nhau thông qua BOM `spring-boot-dependencies`. Với ứng dụng Spring Boot, hãy dùng BOM của đúng dòng Boot đang chạy làm nguồn quản lý phiên bản cho Spring Framework, Spring Data modules, Hibernate ORM và Jakarta Persistence API.

BOM quản lý version của dependency, nhưng không phải công cụ cài JDK trên máy. JDK baseline phải theo yêu cầu của dòng Spring Boot/Spring Framework và được phản ánh trong Maven compiler configuration hoặc Gradle Java toolchain. Vì vậy, hãy xem **Spring Boot release line + BOM + cấu hình compiler/toolchain** là bộ compatibility baseline của ứng dụng.

| Dòng Spring Boot | Spring Framework | Spring Data | Hibernate ORM | Persistence API | JDK baseline |
|---|---|---|---|---|---|
| Boot 2.x | 5.x | 2.x | 5.x | `javax.persistence` | Theo minor release; các bản 2.x hỗ trợ Java 8 trở lên tùy bản |
| Boot 3.x | 6.x | 3.x | 6.x | `jakarta.persistence` 3.1 generation | Java 17+ |
| Boot 4.x | 7.x | 4.x | 7.x generation | `jakarta.persistence` 3.2 generation | Theo system requirements của Boot 4.x; kiểm tra JDK được hỗ trợ cho đúng minor release |

Bảng trên thể hiện các major generation tương ứng, không pin patch version. Version cụ thể của từng module phải lấy từ BOM của Spring Boot release đang chọn. Spring Data modules có số major/minor riêng; ví dụ không yêu cầu `spring-data-jpa` có cùng số version với Spring Boot. BOM chọn các module thuộc release train tương thích.

#### Dùng Spring Boot BOM với Maven

Nếu dự án có thể kế thừa Spring Boot parent, dùng `spring-boot-starter-parent`. Parent này import dependency management tương ứng với phiên bản Boot:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
```

Ví dụ minh họa dùng Spring Boot 3.5 và Java 17. Khi nâng cấp, thay Boot version theo release line đã chọn và kiểm tra JDK tối thiểu của minor release đó. Không thêm version riêng cho `spring-data-jpa`, `spring-data-commons`, `hibernate-core` hoặc `jakarta.persistence-api` khi BOM đã quản lý chúng.

Nếu tổ chức có parent POM riêng, có thể import BOM mà không kế thừa Boot parent:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Trong trường hợp này, `boot.version` là property của dự án, phải trỏ tới một bản Spring Boot cụ thể. Giữ dependency declaration không có version để BOM quản lý.

#### Dùng Spring Boot BOM với Gradle

Khi dùng Spring Boot Gradle plugin cùng dependency management plugin, BOM tương ứng với Boot plugin version được import tự động. Có thể khai báo dependency mà không ghi version:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
```

Nếu dùng Gradle native BOM support, có thể khai báo platform:

```groovy
dependencies {
    implementation platform("org.springframework.boot:spring-boot-dependencies:${bootVersion}")
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
```

Khai báo `platform` áp dụng constraints của BOM cho configuration tương ứng. Chỉ dùng `enforcedPlatform` khi thật sự muốn ép version theo platform và đã hiểu tác động lên dependency graph.

#### Vì sao không trộn major line hoặc override tùy tiện?

Không ghép tùy ý các thành phần sau:
- Spring Framework 5 với Spring Data 3 hoặc 4.
- Spring Data 2.x với Spring Framework 6/7 chỉ vì compile được một phần.
- Hibernate 5 với Jakarta Persistence namespace của Boot 3/4.
- Hibernate 6/7 với dependency JPA cũ `javax.persistence`.
- Spring Data JPA và Spring Data Commons ở hai release train không tương thích.

Các major line có thể thay đổi namespace, method signature, SPI và binary contract. Dependency graph có thể biên dịch nhưng lỗi khi khởi tạo ApplicationContext, tạo EntityManagerFactory, scan repository hoặc chạy query.

Không override riêng version chỉ để làm mất lỗi Maven/Gradle resolution. Trình tự xử lý nên là:
1. Chọn Spring Boot release line tương thích JDK và yêu cầu triển khai.
2. Để Boot BOM quản lý Spring Framework, Spring Data, Hibernate ORM và Persistence API.
3. Khai báo starter/module không ghi version nếu BOM đã quản lý.
4. Nếu cần Spring Data train mới hơn, dùng property `spring-data-bom.version` khi phiên bản Spring Boot đang dùng hỗ trợ cơ chế đó, rồi kiểm tra compatibility và effective dependency graph.
5. Nếu cần bản vá bảo mật hoặc bugfix, ưu tiên nâng Spring Boot patch release. Chỉ override dependency riêng khi có căn cứ tương thích từ release notes/vendor và có test đầy đủ.

JDK không được BOM chọn như một artifact. Đặt compiler/toolchain theo baseline của Boot line và xác minh cả JDK chạy build lẫn JDK runtime. Một máy build dùng JDK mới không có nghĩa bytecode/runtime target của ứng dụng tự động tương thích với JDK production.

#### Kiểm tra dependency graph bằng Maven

Xem phiên bản Maven/JDK đang chạy:

```bash
./mvnw -version
java -version
```

Xem POM hiệu lực sau khi parent, profile và BOM được áp dụng:

```bash
./mvnw help:effective-pom
```

Xem dependency tree đầy đủ và các version bị conflict/omitted:

```bash
./mvnw dependency:tree -Dverbose
```

Lọc các dependency quan trọng cho Spring Data JPA:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:*,org.springframework.data:*,org.hibernate.orm:hibernate-core,org.hibernate:hibernate-core,jakarta.persistence:jakarta.persistence-api,javax.persistence:javax.persistence-api
```

Artifact Hibernate ở dòng cũ có thể dùng group `org.hibernate`; dòng mới thường dùng `org.hibernate.orm`. Kiểm tra cả hai group giúp nhận ra dependency cũ còn sót lại khi nâng cấp.

Nếu dự án đặt Java version trong Maven property, có thể xem giá trị:

```bash
./mvnw help:evaluate -Dexpression=java.version -q -DforceStdout
```

Đồng thời kiểm tra `maven.compiler.release`, `maven.compiler.source` hoặc cấu hình compiler plugin trong effective POM nếu dự án không dùng `java.version`.

#### Kiểm tra dependency graph bằng Gradle

Xem Gradle và JDK được dùng cho build:

```bash
./gradlew -version
java -version
```

Xem toàn bộ runtime dependency graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Dùng `dependencyInsight` để tìm lý do một version cụ thể được chọn:

```bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.persistence-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency javax.persistence-api --configuration runtimeClasspath
```

Kiểm tra Java toolchain đã khai báo:

```bash
./gradlew javaToolchains
```

Đọc kết quả để xác định version được chọn bởi BOM, constraint, conflict resolution hay một dependency khai báo trực tiếp. Nếu thấy nhiều major generation cùng xuất hiện, kiểm tra dependency path và loại bỏ override/dependency cũ có nguyên nhân.

#### Kiểm tra sau khi căn chỉnh

Sau khi sửa dependency:
- Chạy compile để phát hiện API không tương thích.
- Chạy unit và integration test để xác nhận repository, EntityManagerFactory và transaction hoạt động.
- Chạy migration trên database đúng vendor/version.
- Kiểm tra runtime dependency tree, không chỉ compile classpath.
- Kiểm tra JDK trong CI và runtime image giống baseline đã chọn.
- Ghi nhận lý do nếu có override được phê duyệt để lần nâng cấp tiếp theo không vô tình xóa nó.

Tài liệu chính thức:
- [Spring Boot — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html): curated dependency set và BOM.
- [Spring Boot — Maven Plugin Usage](https://docs.spring.io/spring-boot/maven-plugin/using.html): Boot parent, BOM và managed dependency versions.
- [Spring Boot — Gradle Dependency Management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html): dependency management plugin, platform và version override.
- [Spring Data — Dependencies and Release Train](https://docs.spring.io/spring-data/commons/reference/dependencies.html): quan hệ version giữa các Spring Data modules và Release Train BOM.


## 10. Kiểm thử hợp đồng Repository sau nâng cấp

### 10.1. Kiểm tra biên dịch theo kiểu trả về

```java
List<Customer> all = customerRepository.findAll();

List<Customer> byIds =
    customerRepository.findAllById(List.of(1L, 2L));

List<Customer> saved =
    customerRepository.saveAll(customers);

Page<Customer> page =
    customerRepository.findAll(PageRequest.of(0, 20));
```

Ví dụ này phù hợp khi \`customerRepository\` khai báo bằng \`JpaRepository\`, \`ListCrudRepository\` kết hợp \`ListPagingAndSortingRepository\`, hoặc một interface cung cấp các return type tương ứng.

Nếu repository chỉ khai báo bằng \`CrudRepository\`, các biến List đầu tiên không thể nhận trực tiếp method trả \`Iterable\` mà không chuyển đổi.

### 10.2. Kiểm thử repository với @DataJpaTest

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void exposesCrudAndPagingContracts() {
        repository.save(new Customer("anna@example.test"));
        repository.save(new Customer("minh@example.test"));

        List<Customer> all = repository.findAll();

        Page<Customer> firstPage =
            repository.findAll(PageRequest.of(0, 1));

        assertThat(all).hasSize(2);
        assertThat(firstPage.getContent()).hasSize(1);
        assertThat(firstPage.getTotalElements()).isEqualTo(2);
    }
}
```

Test giả định entity \`Customer\` có constructor nhận email và repository extends \`JpaRepository<Customer, Long>\`. Cần cấu hình test database phù hợp dự án; nếu query hoặc migration phụ thuộc vendor-specific SQL, hãy chạy thêm integration test trên PostgreSQL/MySQL thực.

### 10.3. Kiểm tra batch method và reference semantics

Nếu code dùng \`getReferenceById\`, kiểm thử cả trường hợp ID tồn tại và không tồn tại. Không chỉ assert proxy khác null; truy cập field có thể mới kích hoạt việc kiểm tra row.

Nếu code dùng \`deleteAllInBatch\`, kiểm tra:
- Database đã xóa đúng row.
- Persistence context được clear/refresh khi cần.
- Business rule không phụ thuộc cascade hoặc lifecycle callback bị bỏ qua.

### 10.4. Kiểm tra API mà service thực sự công bố

Đôi khi repository có đủ method nhưng service chỉ nhận bean bằng interface quá hẹp:

```java
private final PagingAndSortingRepository<Customer, Long> repository;
```

Trong Spring Data 3.x/4.x, field trên không cung cấp CRUD. Nếu service cần \`save()\`, hãy inject một interface phản ánh đầy đủ hợp đồng, ví dụ \`JpaRepository<Customer, Long>\` hoặc custom interface kế thừa cả CRUD và paging.

## 11. Các lỗi thường gặp khi nâng cấp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| \`save()\` không tìm thấy sau khi lên 3.x | Chỉ kế thừa \`PagingAndSortingRepository\` | Thêm CRUD interface hoặc chuyển sang \`JpaRepository\` |
| \`findById()\` không còn trên biến repository | Kiểu khai báo chỉ là paging/sorting | Khai báo kiểu bao gồm CRUD |
| Không gán được kết quả vào List | Method chỉ cam kết \`Iterable\` | Dùng List interface hoặc chuyển đổi có chủ đích |
| Caller mong \`findAll(Sort)\` trả List nhưng nhận Iterable | Dùng \`PagingAndSortingRepository\` tổng quát | Dùng \`ListPagingAndSortingRepository\` hoặc \`JpaRepository\` |
| Code vẫn gọi \`getOne()\` hoặc \`getById()\` | API đã deprecated | Dùng \`getReferenceById()\` và kiểm tra semantics |
| Batch delete làm entity trong memory không khớp DB | Bulk delete không đồng bộ persistence context | Flush trước, clear/refresh sau |
| Không nhận diện được entity sau khi nâng Boot 3 | Import còn \`javax.persistence\` | Chuyển sang \`jakarta.persistence\` |
| Lỗi method/class không tồn tại giữa các module | Spring Data JPA và Commons lệch version | Đồng bộ release train/BOM |
| Repository generic bị Spring tạo bean trực tiếp | Thiếu \`@NoRepositoryBean\` | Đánh dấu interface trung gian |
| Test compile nhưng paging metadata sai | Chỉ kiểm tra danh sách content | Assert Page total, sort và page boundary |

## 12. Checklist trước khi hoàn tất nâng cấp

- [ ] Đã xác định chính xác Spring Data 2.x, 3.x hay 4.x đang dùng.
- [ ] Đã kiểm tra quan hệ kế thừa của \`PagingAndSortingRepository\`.
- [ ] Repository cần CRUD đã khai báo CRUD interface rõ ràng trên 3.x/4.x.
- [ ] Đã chọn \`Iterable\` hay \`List\` theo hợp đồng caller cần.
- [ ] Đã xác nhận \`JpaRepository\` vẫn cung cấp CRUD và paging/sorting.
- [ ] Đã kiểm tra return type của \`findAll\`, \`findAllById\`, \`saveAll\`, \`findAll(Sort)\` và \`findAll(Pageable)\`.
- [ ] Đã thay \`getOne\`/\`getById\` bằng \`getReferenceById\` nếu phù hợp.
- [ ] Đã thay \`deleteInBatch\` bằng \`deleteAllInBatch\` và xem lại semantics.
- [ ] Đã cập nhật namespace \`javax.persistence\` sang \`jakarta.persistence\` khi chuyển sang Spring Data 3.x+.
- [ ] Java/Spring Framework/Jakarta Persistence versions tương thích.
- [ ] Spring Data JPA và Spring Data Commons được quản lý cùng release train.
- [ ] Generic repository trung gian có \`@NoRepositoryBean\`.
- [ ] Compile và integration tests chạy qua trên database mục tiêu.
- [ ] Đã kiểm tra paging metadata, List contract, transaction và persistence context sau bulk operation.

## 13. Tài liệu tham khảo chính thức

- [Spring Data Commons — Defining Repository Interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html): cách kết hợp CRUD, paging/sorting và các List repository variants.
- [Spring Data Commons — 2.7 PagingAndSortingRepository API](https://docs.spring.io/spring-data/commons/docs/2.7.x/api/org/springframework/data/repository/PagingAndSortingRepository.html): quan hệ kế thừa CRUD trong dòng 2.x.
- [Spring Data Commons — ListCrudRepository API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/ListCrudRepository.html): hợp đồng List được giới thiệu từ 3.0.
- [Spring Data Commons — ListPagingAndSortingRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/ListPagingAndSortingRepository.html): hợp đồng List cho phương thức sắp xếp.
- [Spring Data JPA — JpaRepository 2.7 API](https://docs.spring.io/spring-data/jpa/docs/2.7.6/api/org/springframework/data/jpa/repository/JpaRepository.html): các phương thức List được khai báo trong dòng 2.x và các JPA-specific methods.
- [Spring Data JPA — JpaRepository 3.0 API](https://www.springframework.org/spring-data/jpa/docs/3.0.12/api/org/springframework/data/jpa/repository/JpaRepository.html): composition từ ListCrudRepository và ListPagingAndSortingRepository.
- [Spring Data JPA — JpaRepository 4.1 API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html): phân cấp hiện hành và deprecated methods.
- [Announcing ListCrudRepository and Friends for Spring Data 3.0](https://spring.io/blog/2022/02/22/announcing-listcrudrepository-friends-for-spring-data-3-0/): giải thích lý do tách sorting khỏi CRUD.
- [Spring Data 2025.1 Goes GA](https://spring.io/blog/2025/11/14/spring-data-2025-1-goes-ga/): nền tảng Spring Framework 7 và Jakarta EE 11 của dòng 4.0.

## 14. Kết luận

Trong Spring Data 2.x, \`PagingAndSortingRepository\` kế thừa \`CrudRepository\`, vì vậy chỉ cần kế thừa paging/sorting là repository có cả CRUD. Từ Spring Data 3.0, hai nhóm này tách nhau để có thể kết hợp linh hoạt với các interface List mới. Repository cần cả hai phải khai báo cả CRUD và paging/sorting; \`ListCrudRepository\` và \`ListPagingAndSortingRepository\` là lựa chọn khi muốn return type List.

\`JpaRepository\` vẫn là lựa chọn đầy đủ cho JPA. Trong 2.x, nó kế thừa \`PagingAndSortingRepository\` và khai báo lại một số phương thức trả về List. Từ 3.x và trong 4.x, nó kết hợp trực tiếp \`ListCrudRepository\` và \`ListPagingAndSortingRepository\`. Vì vậy, repository JPA thông thường đang extends \`JpaRepository\` không cần thêm các interface CRUD/paging một cách dư thừa.

Khi nâng cấp, hãy kiểm tra kiểu repository mà service đang nhận, các phương thức caller sử dụng và kiểu trả về thực tế. Thay các API deprecated như \`getOne\`, \`getById\` và \`deleteInBatch\` sau khi xác minh semantics. Khi chuyển từ 2.x sang 3.x, cập nhật Java baseline và namespace \`javax.persistence\` sang \`jakarta.persistence\`; khi chuyển sang 4.x, căn chỉnh Spring Framework 7/Jakarta EE 11 và kiểm tra thêm AOT/null-safety changes. Cuối cùng, để Spring Boot BOM hoặc Spring Data release train quản lý các module đồng bộ và xác nhận bằng compile test cùng integration test trên database mục tiêu.