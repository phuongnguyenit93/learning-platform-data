# Các thao tác CRUD và ý nghĩa kết quả trả về

## 1. CRUD trong Spring Data R2DBC

CRUD là bốn nhóm thao tác dữ liệu cơ bản:

- **Create:** tạo bản ghi mới.
- **Read:** đọc một hoặc nhiều bản ghi.
- **Update:** thay đổi dữ liệu đã tồn tại.
- **Delete:** xóa dữ liệu.

Trong Spring Data R2DBC, các thao tác này thường được thực hiện qua repository reactive kế thừa `ReactiveCrudRepository<T, ID>`. Repository cung cấp API theo kiểu entity, còn Spring Data và R2DBC driver chịu trách nhiệm tạo SQL, bind tham số, thực thi và ánh xạ kết quả.

Điểm cần hiểu không chỉ là phương thức nào dùng để tạo, đọc, sửa hoặc xóa, mà còn là **kiểu trả về nói lên điều gì**. `Mono<T>`, `Flux<T>`, `Mono<Boolean>`, `Mono<Long>` và `Mono<Void>` có ngữ nghĩa khác nhau. Nếu dùng sai hoặc bỏ qua giá trị trả về, ứng dụng có thể mất ID được sinh, không nhận biết bản ghi không tồn tại hoặc vô tình che giấu lỗi database.

## 2. Repository CRUD cơ bản

Ví dụ entity và repository:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @Column("email_address")
    private String email;

    // Constructors, getters and setters
}
```

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
```

`Customer` là kiểu entity được lưu; `Long` là kiểu ID. Khi kế thừa `ReactiveCrudRepository`, repository nhận các thao tác CRUD phổ biến mà không cần tự viết SQL cho từng thao tác.

Các chữ ký phương thức cốt lõi thường gặp:

| Phương thức | Kiểu trả về | Ý nghĩa kết quả |
| --- | --- | --- |
| `save(entity)` | `Mono<S>` | Entity sau khi lưu |
| `saveAll(entities)` | `Flux<S>` | Các entity sau khi lưu |
| `findById(id)` | `Mono<T>` | Một entity hoặc publisher rỗng |
| `findAll()` | `Flux<T>` | Dòng entity có thể có nhiều phần tử |
| `findAllById(ids)` | `Flux<T>` | Các entity tìm thấy theo danh sách ID |
| `existsById(id)` | `Mono<Boolean>` | `true` hoặc `false` |
| `count()` | `Mono<Long>` | Số lượng entity |
| `deleteById(id)` | `Mono<Void>` | Tín hiệu hoàn tất xóa, không phát entity hoặc số hàng |
| `delete(entity)` | `Mono<Void>` | Tín hiệu hoàn tất xóa entity |
| `deleteAll()` | `Mono<Void>` | Tín hiệu hoàn tất xóa toàn bộ entity của repository |

Repository cũng có các overload nhận `Iterable` hoặc `Publisher` cho một số thao tác như `saveAll`, `findAllById` và `deleteAll`. Hãy xem chữ ký của phiên bản Spring Data đang dùng khi cần lựa chọn overload cụ thể.

## 3. Hiểu Mono và Flux trong kết quả CRUD

Spring Data R2DBC dùng Project Reactor để biểu diễn kết quả reactive:

- `Mono<T>` phát tối đa một phần tử rồi hoàn tất, có thể hoàn tất rỗng hoặc kết thúc bằng lỗi.
- `Flux<T>` phát từ 0 đến nhiều phần tử rồi hoàn tất hoặc kết thúc bằng lỗi.
- `Mono<Void>` biểu diễn một thao tác chỉ cần biết đã hoàn tất hay gặp lỗi; nó không phát giá trị dữ liệu.

Ví dụ:

```java
Mono<Customer> one = customerRepository.findById(10L);
Flux<Customer> many = customerRepository.findAll();
Mono<Boolean> exists = customerRepository.existsById(10L);
Mono<Long> total = customerRepository.count();
Mono<Void> deleted = customerRepository.deleteById(10L);
```

Các biến trên giữ publisher. Với repository reactive, thao tác database thường được thực thi khi publisher được subscribe. Chỉ gọi `findAll()` rồi bỏ kết quả đi không có nghĩa là ứng dụng đã đọc dữ liệu.

### 3.1. Không có phần tử khác với false hoặc null

Các kết quả sau có ý nghĩa khác nhau:

| Kết quả | Ý nghĩa |
| --- | --- |
| `Mono.just(false)` | Truy vấn existence đã chạy và không tìm thấy bản ghi thỏa điều kiện |
| `Mono.just(0L)` | Truy vấn count đã chạy và đếm được 0 bản ghi |
| `Mono.empty()` | Publisher hoàn tất mà không phát phần tử; thường gặp khi `findById` không tìm thấy |
| `Mono.error(error)` | Thao tác kết thúc bằng lỗi, ví dụ lỗi kết nối hoặc SQL |
| `Mono<Void>` hoàn tất | Thao tác đã hoàn tất bình thường nhưng không có giá trị dữ liệu được phát |

Reactive Streams không cho publisher phát `null` như một phần tử. Khi không có entity, `findById` biểu diễn bằng `Mono.empty()`, không phải `Mono.just(null)`.

Không nên chuyển mọi lỗi thành `false`, `0` hoặc empty một cách tùy tiện. Nếu database không thể kết nối, ứng dụng không biết bản ghi có tồn tại hay không; đó là lỗi, không phải kết quả “không tồn tại”.

## 4. Create và ý nghĩa của save

Phương thức `save` lưu một entity và trả về entity đã lưu:

```java
Mono<Customer> saved = customerRepository.save(customer);
```

Giá trị trả về có thể chứa ID được database sinh, version mới hoặc trạng thái đã được mapping sau khi ghi. Vì vậy, nên sử dụng entity mà publisher phát ra thay vì mặc định object đầu vào luôn được cập nhật tại chỗ.

Ví dụ:

```java
public Mono<Long> createCustomer(String name, String email) {
    Customer customer = new Customer();
    customer.setName(name);
    customer.setEmail(email);

    return customerRepository.save(customer)
            .map(Customer::getId);
}
```

Nếu ID được sinh tự động, giá trị ID chỉ có sau khi thao tác lưu hoàn tất. Không đọc `customer.getId()` ngay sau khi gọi `save` mà chưa tiêu thụ publisher.

### 4.1. Save không phải lúc nào cũng là INSERT

Tên `save` bao gồm cả tạo mới và cập nhật. Spring Data xác định entity có mới hay không bằng cơ chế nhận diện trạng thái mới (*newness detection*). Tùy entity và cấu hình, việc nhận diện thường dựa vào:

1. Nếu entity triển khai `Persistable`, Spring Data dùng `isNew()` do entity cung cấp.
2. Nếu entity có thuộc tính `@Version`, giá trị version có thể được dùng để xác định trạng thái mới.
3. Nếu không có các cơ chế trên, Spring Data thường kiểm tra ID; ID chưa có giá trị thường biểu thị entity mới.

Do đó, `save` không có nghĩa là database thực hiện một câu lệnh UPSERT nguyên tử theo cú pháp riêng của hệ quản trị. Spring Data chọn đường insert hoặc update dựa trên trạng thái entity.

### 4.2. ID tự sinh và ID gán trước

Với ID tự sinh, entity thường có ID `null` trước khi lưu:

```java
Customer customer = new Customer();
customer.setName("Lan Nguyen");
customer.setEmail("lan@example.com");

return customerRepository.save(customer)
        .doOnNext(saved -> System.out.println(saved.getId()));
```

Nếu ID được gán trước, ví dụ UUID hoặc ID do hệ thống khác cấp, Spring Data có thể xem entity là đã tồn tại khi không có `@Version` hay `Persistable` điều khiển trạng thái mới. Khi đó `save` có thể đi theo đường update và không insert như mong muốn.

Với entity dùng ID gán trước, hãy thiết kế newness detection rõ ràng. Có thể dùng `Persistable<ID>` để cung cấp `isNew()`, hoặc dùng một thuộc tính version nullable nếu phù hợp với mô hình và schema.

### 4.3. Save trả về entity có thể là instance khác

Với entity mutable, Spring Data có thể cập nhật ID hoặc version trên object tùy cách mapping. Với entity immutable hoặc dùng constructor/wither, framework có thể tạo instance mới chứa giá trị sau khi lưu.

Vì thế, cách an toàn là luôn dùng kết quả trả về:

```java
return customerRepository.save(customer)
        .flatMap(savedCustomer -> publishCustomerCreated(savedCustomer));
```

Không nên bỏ kết quả rồi tiếp tục dùng object đầu vào với giả định rằng mọi thuộc tính generated đã được cập nhật.

## 5. Update và optimistic locking

Trong repository CRUD, cập nhật thường cũng dùng `save`. Nếu entity được nhận diện là đã tồn tại, Spring Data thực hiện thao tác update phù hợp với mapping.

Ví dụ:

```java
public Mono<Customer> renameCustomer(Long id, String newName) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                customer.setName(newName);
                return customerRepository.save(customer);
            });
}
```

`findById` trả `Mono.empty()` nếu không có customer. `switchIfEmpty` chuyển trường hợp đó thành lỗi nghiệp vụ. Nếu tìm thấy, `flatMap` thay đổi entity rồi nối publisher do `save` trả về.

### 5.1. Không tìm thấy entity không đồng nghĩa với save tự tạo mới

Một điểm dễ nhầm là: nếu `findById(id)` không tìm thấy, việc tạo object mới với cùng ID rồi gọi `save` không phải lúc nào cũng là hành vi mong muốn. Nếu ID đã được gán, Spring Data có thể nhận diện entity là existing và thực hiện update. Tùy database, update không có hàng phù hợp có thể hoàn tất mà không thay đổi bản ghi.

Nếu nghiệp vụ là “cập nhật khi tồn tại, nếu không thì trả lỗi”, hãy xử lý `Mono.empty()` trước khi gọi `save`, như ví dụ trên. Nếu nghiệp vụ là upsert, hãy thiết kế rõ bằng SQL/DatabaseClient hoặc cơ chế database phù hợp, thay vì dựa vào suy đoán từ tên `save`.

### 5.2. Dùng @Version để phát hiện cập nhật đồng thời

Khi hai request cùng đọc một entity, cả hai có thể sửa và lưu. Nếu không kiểm soát, một thay đổi có thể ghi đè thay đổi của request kia.

Spring Data Relational hỗ trợ optimistic locking qua `@Version`:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;
}
```

Spring Data dùng version khi cập nhật để kiểm tra entity vẫn ở phiên bản mà ứng dụng đã đọc. Nếu bản ghi đã bị cập nhật bởi thao tác khác hoặc không còn tồn tại theo version mong đợi, thao tác có thể kết thúc bằng `OptimisticLockingFailureException`.

Kết quả `save` cũng có thể chứa version mới. Nếu ứng dụng cần tiếp tục thao tác trên entity đã cập nhật, hãy dùng entity được phát ra từ `save`.

Không nên tự động retry mọi lỗi optimistic locking. Trước khi thử lại, cần tải trạng thái mới và kiểm tra hành động còn hợp lệ theo nghiệp vụ hay không.

## 6. Read: findById, findAll và findAllById

### 6.1. findById

`findById(id)` trả `Mono<T>`:

```java
Mono<Customer> customer = customerRepository.findById(10L);
```

Nếu tìm thấy, publisher phát một entity rồi hoàn tất. Nếu không tìm thấy, publisher hoàn tất rỗng. Nếu truy vấn lỗi, publisher kết thúc bằng `onError`.

Ví dụ xử lý cả trường hợp có và không có:

```java
public Mono<Customer> getCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
```

Nếu muốn dùng giá trị thay thế:

```java
return customerRepository.findById(id)
        .defaultIfEmpty(Customer.anonymous());
```

Chỉ dùng giá trị thay thế khi đó là hành vi nghiệp vụ có ý nghĩa. Với API chi tiết một customer, trả lỗi not found thường rõ ràng hơn trả một entity giả.

### 6.2. findAll

`findAll()` trả `Flux<T>`:

```java
Flux<Customer> customers = customerRepository.findAll();
```

`Flux` có thể phát nhiều entity. Nếu bảng rỗng, nó hoàn tất mà không phát phần tử. Nếu có lỗi khi đọc dữ liệu, lỗi được truyền qua publisher.

Không nên mặc định `findAll()` phù hợp cho mọi bảng. Nếu dữ liệu lớn, hãy dùng truy vấn có điều kiện, phân trang hoặc xử lý theo dòng. Thu thập toàn bộ `Flux` thành `List` có thể tiêu tốn nhiều bộ nhớ.

### 6.3. findAllById

`findAllById(ids)` nhận danh sách ID và phát ra các entity tìm thấy:

```java
Flux<Customer> customers = customerRepository.findAllById(List.of(10L, 20L, 30L));
```

Nếu một số ID không tồn tại, phương thức chỉ phát các entity tìm thấy; không phát placeholder cho ID bị thiếu. Thứ tự phần tử trả về không được bảo đảm theo thứ tự danh sách ID đầu vào. Nếu nghiệp vụ yêu cầu đúng thứ tự, hãy sắp xếp lại theo danh sách ID ở ứng dụng hoặc dùng truy vấn có `ORDER BY` và quy tắc thứ tự rõ ràng.

## 7. Exists và count

Hai phương thức này trả kết quả scalar thay vì entity:

```java
Mono<Boolean> exists = customerRepository.existsById(10L);
Mono<Long> total = customerRepository.count();
```

`existsById` phát `true` hoặc `false`; `count` phát tổng số bản ghi. Nếu chỉ cần biết có hay không, dùng `exists` thay vì tải entity hoặc đếm toàn bộ hàng.

Repository cũng có thể khai báo derived query:

```java
Mono<Boolean> existsByEmail(String email);
Mono<Long> countByStatus(String status);
```

Đây là các phương thức truy vấn theo điều kiện, không phải thao tác đọc entity đầy đủ. Cần chọn theo dữ liệu đầu ra cần dùng.

## 8. Delete và ý nghĩa Mono<Void>

Các phương thức xóa trong `ReactiveCrudRepository` thường trả `Mono<Void>`:

```java
Mono<Void> deleteById(Long id);
Mono<Void> delete(Customer customer);
Mono<Void> deleteAll();
```

`Mono<Void>` không phát ra entity đã xóa, số hàng bị ảnh hưởng hoặc boolean thành công. Nó biểu diễn rằng thao tác hoàn tất bình thường hay kết thúc bằng lỗi.

Ví dụ xóa theo ID:

```java
public Mono<Void> removeCustomer(Long id) {
    return customerRepository.deleteById(id);
}
```

Khi publisher hoàn tất, thao tác xóa đã hoàn tất theo hợp đồng của repository. Nếu database phát sinh lỗi như vi phạm ràng buộc, mất kết nối hoặc lỗi transaction, publisher kết thúc bằng lỗi.

### 8.1. Xóa ID không tồn tại

`deleteById(id)` không trả về boolean để nói có bản ghi bị xóa hay không. Trong thao tác xóa theo ID, nếu không có hàng phù hợp, lệnh DELETE có thể tác động 0 hàng nhưng publisher vẫn hoàn tất bình thường.

Nếu nghiệp vụ cần trả lời “đã xóa một bản ghi hay không”, `Mono<Void>` không đủ thông tin. Có thể kiểm tra trước bằng `existsById`, nhưng chuỗi kiểm tra rồi xóa có race condition; hoặc dùng SQL tùy chỉnh trả số hàng bị ảnh hưởng.

### 8.2. Xóa entity và optimistic locking

Khi gọi `delete(entity)` trên entity có `@Version`, Spring Data có thể kiểm tra version để phát hiện entity đã bị thay đổi hoặc bị xóa bởi thao tác khác. Nếu không còn hàng phù hợp với ID và version mong đợi, thao tác có thể kết thúc bằng lỗi optimistic locking.

`deleteById(id)` chỉ có ID nên không thể kiểm tra version của entity mà caller đã đọc. Nếu cần bảo vệ xung đột theo version, hãy dùng thao tác trên entity có version hoặc một câu lệnh tùy chỉnh có điều kiện version.

### 8.3. Xóa toàn bộ

`deleteAll()` xóa tất cả entity thuộc repository. Đây là thao tác có phạm vi lớn và cần được gọi có chủ đích:

```java
Mono<Void> clearCustomers() {
    return customerRepository.deleteAll();
}
```

Không nhầm `deleteAll()` với việc xóa dữ liệu của một tenant hoặc một điều kiện nghiệp vụ. Nếu chỉ cần xóa một nhóm bản ghi, hãy dùng phương thức có điều kiện hoặc truy vấn delete tùy chỉnh.

## 9. Ý nghĩa kết quả của từng nhóm CRUD

| Nhóm | API điển hình | Publisher phát gì? | Trường hợp không có dữ liệu |
| --- | --- | --- | --- |
| Create/update | `save` | Entity đã lưu | Thường không phải empty nếu thao tác thành công; lỗi được phát qua error signal |
| Save nhiều entity | `saveAll` | Từng entity đã lưu qua `Flux` | Iterable/Publisher đầu vào rỗng thì không có phần tử |
| Read một entity | `findById` | Một entity | `Mono.empty()` |
| Read nhiều entity | `findAll`, `findAllById` | Các entity tìm thấy | `Flux` hoàn tất rỗng |
| Existence | `existsById` | Boolean | `false` |
| Count | `count` | Long | `0L` |
| Delete | `delete`, `deleteById`, `deleteAll` | Không phát giá trị (`Void`) | Thường hoàn tất bình thường nếu không có lỗi |

Điểm khác biệt quan trọng là `findById` dùng empty để biểu diễn không tìm thấy, còn `existsById` dùng `false`. Các thao tác delete dùng `Mono<Void>` nên không thể suy ra số hàng đã xóa chỉ từ việc publisher hoàn tất.

## 10. Dùng saveAll cho nhiều entity

`saveAll` nhận nhiều entity và trả `Flux<S>` chứa các entity đã được lưu:

```java
public Flux<Customer> importCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

Có overload nhận `Iterable` và overload nhận `Publisher`, hữu ích khi dữ liệu đầu vào được tạo hoặc đọc từ một luồng reactive khác:

```java
Flux<Customer> incoming = readCustomersFromSource();

return customerRepository.saveAll(incoming);
```

Kết quả là một `Flux` để downstream xử lý từng entity đã lưu. Nếu cần lấy ID được sinh, hãy đọc từ các entity được phát ra bởi `saveAll`.

Không nên mặc định `saveAll` luôn biến thành một câu SQL bulk insert duy nhất. Tùy implementation, mapping và driver, các entity có thể được xử lý qua nhiều thao tác. Nếu hiệu năng batch quan trọng, hãy đo SQL thực tế và xem API batch phù hợp với database.

### 10.1. Lỗi giữa chừng và transaction

Nếu một entity trong luồng không lưu được, publisher có thể kết thúc bằng lỗi. Những thao tác đã được thực hiện trước lỗi có thể đã hoàn tất tùy ranh giới transaction. Không nên giả định một chuỗi `saveAll` luôn tự động có tính nguyên tử trên mọi cách gọi và mọi cấu hình.

Nếu nghiệp vụ yêu cầu toàn bộ đợt import phải thành công hoặc rollback cùng nhau, hãy đặt một transaction reactive bao quanh toàn bộ publisher phù hợp:

```java
@Transactional
public Flux<Customer> importCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

Phương thức phải trả publisher để Spring quản lý vòng đời transaction. Với transaction được quản lý bởi `R2dbcTransactionManager`, các thao tác cần tham gia cùng transaction context và connection. Nếu cần xử lý batch rất lớn, một transaction quá dài có thể giữ connection lâu và tạo áp lực cho database; có thể chia thành các chunk theo yêu cầu nghiệp vụ.

## 11. Dùng kết quả CRUD trong service reactive

Một application service có thể kết hợp nhiều thao tác mà không chặn thread:

```java
@Service
public class CustomerApplicationService {

    private final CustomerRepository repository;

    public CustomerApplicationService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> create(String name, String email) {
        Customer customer = new Customer();
        customer.setName(name);
        customer.setEmail(email);

        return repository.save(customer);
    }

    public Mono<Customer> get(Long id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
    }

    public Mono<Customer> updateName(Long id, String newName) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
                .flatMap(customer -> {
                    customer.setName(newName);
                    return repository.save(customer);
                });
    }

    public Mono<Void> delete(Long id) {
        return repository.deleteById(id);
    }
}
```

Service trả trực tiếp publisher cho tầng gọi. Không cần tự gọi `subscribe()` bên trong từng phương thức. Khi dùng WebFlux, framework có thể subscribe publisher do controller trả về và quản lý tín hiệu theo vòng đời request.

### 11.1. Khi muốn trả thông báo sau khi xóa

Vì `deleteById` trả `Mono<Void>`, có thể nối thêm một kết quả sau khi thao tác hoàn tất:

```java
public Mono<String> deleteAndRespond(Long id) {
    return customerRepository.deleteById(id)
            .thenReturn("Delete operation completed");
}
```

`thenReturn` chỉ phát chuỗi khi publisher trước hoàn tất bình thường. Nếu delete lỗi, chuỗi không được phát mà lỗi tiếp tục truyền xuống.

Nếu muốn trả HTTP 204, controller có thể trả `Mono<Void>`:

```java
@DeleteMapping("/{id}")
public Mono<Void> delete(@PathVariable Long id) {
    return customerService.delete(id);
}
```

HTTP 204 ở ví dụ này chỉ nói thao tác được xử lý mà không có response body; nó không tự xác nhận rằng một hàng chắc chắn đã bị xóa nếu ID không tồn tại.

## 12. Khi cần số hàng bị ảnh hưởng

Các phương thức delete CRUD tiêu chuẩn trả `Mono<Void>`, nên không cung cấp số hàng bị ảnh hưởng. Nếu nghiệp vụ cần phân biệt “đã xóa” và “không có hàng nào phù hợp”, có thể dùng `DatabaseClient`:

```java
public Mono<Long> deleteCustomer(DatabaseClient databaseClient, Long id) {
    return databaseClient.sql("DELETE FROM customer WHERE id = :id")
            .bind("id", id)
            .fetch()
            .rowsUpdated();
}
```

`rowsUpdated()` trả về số hàng được thay đổi theo kết quả thực thi của driver. Ví dụ, giá trị `1` thường có nghĩa một hàng bị xóa, còn `0` có nghĩa không có hàng phù hợp. Kiểu và hành vi cụ thể cần được xác nhận theo phiên bản Spring Framework R2DBC và driver đang dùng.

Tương tự, với UPDATE tùy chỉnh:

```java
public Mono<Long> updateCustomerEmail(
        DatabaseClient databaseClient,
        Long id,
        String email) {

    return databaseClient.sql("""
            UPDATE customer
            SET email_address = :email
            WHERE id = :id
            """)
            .bind("email", email)
            .bind("id", id)
            .fetch()
            .rowsUpdated();
}
```

Đây là thao tác SQL tường minh, không phải kết quả mặc định của `ReactiveCrudRepository.save`. Khi dùng custom SQL, ứng dụng chịu trách nhiệm bảo đảm mapping, điều kiện WHERE, optimistic locking nếu cần và tính nhất quán với domain.

## 13. Transaction và ranh giới của một thao tác CRUD

Một thao tác repository đơn lẻ thường có cơ chế transaction theo cấu hình Spring Data. Nhưng use case gồm nhiều lời gọi repository cần xác định ranh giới transaction ở tầng ứng dụng.

Ví dụ, tạo customer và một bản ghi audit:

```java
@Transactional
public Mono<Customer> register(Customer customer) {
    return customerRepository.save(customer)
            .flatMap(saved -> auditRepository.save(
                    new AuditEntry("CUSTOMER_CREATED", saved.getId()))
                    .thenReturn(saved));
}
```

Nếu hai repository cùng dùng `ConnectionFactory` và transaction manager phù hợp, các thao tác có thể tham gia cùng reactive transaction. Nếu audit lưu ở database hoặc hệ thống khác, transaction R2DBC này không tự bao phủ hệ thống kia.

Transaction reactive gắn với Reactor Context và publisher lifecycle. Vì vậy, không nên gọi `subscribe()` độc lập bên trong phương thức `@Transactional`, rồi trả về một publisher khác. Subscription độc lập có thể chạy ngoài transaction của caller.

## 14. Derived query và CRUD tùy chỉnh

`ReactiveCrudRepository` cung cấp thao tác tổng quát, nhưng ứng dụng thường cần truy vấn theo điều kiện domain:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);

    Mono<Boolean> existsByEmail(String email);

    Mono<Long> countByStatus(String status);
}
```

Tên phương thức được phân tích dựa trên property của entity. Các phương thức đọc có thể trả `Mono` hoặc `Flux` tùy số lượng kết quả cần biểu diễn. Các phương thức exists/count trả scalar tương ứng.

Khi cần SQL tùy chỉnh, có thể dùng `@Query` cho truy vấn repository hoặc `DatabaseClient` cho thao tác cần kiểm soát chi tiết. Với câu lệnh sửa/xóa tùy chỉnh, cần đánh dấu và cấu hình theo cơ chế modifying query mà phiên bản Spring Data R2DBC hỗ trợ, đồng thời chọn kiểu trả về phù hợp với số hàng bị ảnh hưởng nếu cần thông tin đó.

## 15. Lỗi và cách xử lý kết quả CRUD

Lỗi database không nên bị nhầm với trường hợp không có dữ liệu. Ví dụ:

```java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .onErrorMap(DataAccessException.class,
                error -> new CustomerPersistenceException(error));
```

Trong thực tế, cần giữ nguyên hoặc chuyển đổi lỗi theo chính sách rõ ràng. Một số tình huống thường gặp:

| Thao tác | Trường hợp | Ý nghĩa xử lý |
| --- | --- | --- |
| `save` | Vi phạm unique constraint | Không lưu được; chuyển lỗi thành lỗi nghiệp vụ phù hợp nếu xác định đúng constraint |
| `save` với `@Version` | Version đã thay đổi | Optimistic locking failure; tải lại và quyết định xử lý |
| `findById` | Không có hàng | `Mono.empty()`; có thể chuyển thành not found |
| `findAll` | Không có hàng | `Flux` hoàn tất rỗng; không phải lỗi |
| `existsById` | Không có hàng | Phát `false` |
| `count` | Không có hàng | Phát `0L` |
| `deleteById` | Không có hàng | Thường hoàn tất mà không phát số hàng bị xóa |
| Bất kỳ thao tác nào | Mất kết nối, timeout, lỗi SQL | Publisher kết thúc bằng error signal |

`onErrorResume` có thể cung cấp publisher thay thế khi một loại lỗi cụ thể xảy ra. Không nên dùng nó để biến mọi lỗi thành empty hoặc giá trị mặc định, vì điều đó làm mất thông tin quan trọng cho quan sát và xử lý nghiệp vụ.

## 16. Những nhầm lẫn thường gặp

### save luôn là INSERT

`save` có thể insert hoặc update dựa trên trạng thái mới của entity. Cần hiểu `isNew` detection, ID, `@Version` và `Persistable`.

### Save thành công nghĩa object đầu vào luôn có ID mới

Hãy dùng entity được phát ra từ `Mono<S>` hoặc `Flux<S>`. Entity immutable có thể được thay bằng instance mới; giá trị generated phụ thuộc database, dialect và driver.

### findById không tìm thấy trả false

`findById` trả `Mono.empty()`. `existsById` mới trả `Mono<Boolean>` với giá trị `false` khi không tồn tại.

### deleteById trả số hàng đã xóa

Phương thức chuẩn trả `Mono<Void>`. Nếu cần số hàng bị ảnh hưởng, dùng truy vấn sửa/xóa tùy chỉnh có API trả `rowsUpdated()`.

### delete hoàn tất nghĩa là chắc chắn có một hàng đã bị xóa

Hoàn tất chỉ cho biết thao tác không phát lỗi. Nếu ID không tồn tại, SQL DELETE có thể tác động 0 hàng nhưng publisher vẫn hoàn tất bình thường.

### saveAll luôn là một bulk SQL duy nhất

Không nên giả định như vậy. Cách xử lý phụ thuộc implementation, mapping và driver. Đo SQL thực tế nếu hiệu năng batch quan trọng.

### Có thể gọi block hoặc subscribe ở mọi nơi

`block()` chặn thread; `subscribe()` tạo subscription độc lập. Trong service reactive, hãy kết hợp publisher bằng `map`, `flatMap`, `then` và trả kết quả cho tầng gọi.

## 17. Cách chọn API CRUD theo nhu cầu

| Mục tiêu | API nên dùng | Kết quả cần tiêu thụ |
| --- | --- | --- |
| Tạo hoặc lưu entity | `save(entity)` | Entity đã lưu, đặc biệt ID/version |
| Lưu một luồng entity | `saveAll(...)` | Từng entity được lưu qua `Flux` |
| Lấy một entity | `findById(id)` | Entity hoặc empty |
| Lấy nhiều entity | `findAll()` / `findAllById(...)` | Các entity được phát qua `Flux` |
| Kiểm tra tồn tại | `existsById(id)` hoặc `existsBy...` | Boolean |
| Đếm bản ghi | `count()` hoặc `countBy...` | Long |
| Xóa theo ID/entity | `deleteById` / `delete` | Tín hiệu hoàn tất (`Mono<Void>`) |
| Xóa toàn bộ | `deleteAll()` | Tín hiệu hoàn tất (`Mono<Void>`) |
| Cần số hàng bị thay đổi | `DatabaseClient.fetch().rowsUpdated()` | Số hàng bị ảnh hưởng |

Khi thiết kế service, hãy xác định trước kết quả nghiệp vụ cần trả cho caller. Nếu cần entity sau khi lưu, trả `Mono<Entity>`. Nếu chỉ cần xác nhận hoàn tất, `Mono<Void>` là đủ. Nếu cần biết số hàng thay đổi, chọn API cung cấp số lượng đó. Không nên suy diễn thông tin mà kiểu trả về không cung cấp.

## 18. Kiểm thử kết quả CRUD

Với repository reactive, có thể dùng `StepVerifier` để kiểm tra publisher:

```java
StepVerifier.create(customerRepository.save(customer))
        .assertNext(saved -> {
            assertNotNull(saved.getId());
            assertEquals("lan@example.com", saved.getEmail());
        })
        .verifyComplete();
```

Kiểm tra `findById` không tìm thấy:

```java
StepVerifier.create(customerRepository.findById(-1L))
        .verifyComplete();
```

Kiểm tra exists:

```java
StepVerifier.create(customerRepository.existsById(existingId))
        .expectNext(true)
        .verifyComplete();
```

Kiểm tra delete:

```java
StepVerifier.create(customerRepository.deleteById(existingId))
        .verifyComplete();
```

Với `Mono<Void>`, không dùng `expectNext` vì publisher không phát phần tử. `verifyComplete()` xác nhận thao tác hoàn tất bình thường; nếu có lỗi, test sẽ thất bại.

Nên có integration test với database và R2DBC driver thực tế cho các hành vi phụ thuộc persistence:

- ID được sinh và trả về đúng.
- `save` chọn insert hay update theo trạng thái entity.
- `@Version` phát hiện xung đột cập nhật.
- `findById` trả empty khi không có bản ghi.
- `deleteById` xử lý ID không tồn tại theo hợp đồng mong muốn.
- `saveAll` có hành vi transaction phù hợp với use case.
- Lỗi constraint và lỗi kết nối được truyền thành error signal.

Mock repository hữu ích để kiểm thử logic điều phối trong service, nhưng không chứng minh SQL, mapping hoặc transaction của driver hoạt động đúng.

## 19. Quy trình sử dụng CRUD trong một use case

Khi xây dựng một chức năng với Spring Data R2DBC, có thể lần lượt xác định:

1. Chức năng cần tạo, đọc, sửa hay xóa dữ liệu?
2. Nếu lưu, entity là mới hay đã tồn tại? Cơ chế nhận diện newness có phù hợp với kiểu ID không?
3. Caller cần entity trả về, boolean, số đếm hay chỉ tín hiệu hoàn tất?
4. Nếu đọc một entity, trường hợp không tồn tại được xử lý bằng empty hay lỗi nghiệp vụ?
5. Nếu xóa, có cần biết số hàng bị ảnh hưởng hay `Mono<Void>` là đủ?
6. Nếu nhiều thao tác phải thành công cùng nhau, transaction reactive được đặt ở đâu?
7. Có optimistic locking, unique constraint hoặc race condition cần xử lý không?
8. Publisher được trả xuyên suốt pipeline hay bị chặn bằng `block()`/tách rời bằng `subscribe()`?
9. Integration test có xác nhận giá trị trả về và hành vi database thật không?

Các API CRUD của `ReactiveCrudRepository` cung cấp một hợp đồng rõ ràng giữa ứng dụng và tầng persistence. `save` trả entity sau khi lưu; `find` trả entity hoặc dòng entity; `exists` trả boolean; `count` trả số lượng; còn delete thường chỉ trả tín hiệu hoàn tất. Hiểu đúng ngữ nghĩa này giúp service xử lý chính xác ID được sinh, bản ghi không tồn tại, lỗi database, xung đột cập nhật và transaction trong pipeline reactive.
