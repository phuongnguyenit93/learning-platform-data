# Update thực thể và xử lý bản ghi không tồn tại

Trong Spring Data Relational R2DBC, cập nhật một entity cần làm rõ hai việc: entity được xem là mới hay đã tồn tại, và điều gì xảy ra nếu câu lệnh update không tìm thấy dòng phù hợp trong database. Đây là hai vấn đề liên quan nhưng không giống nhau.

Phương thức save() có thể dùng cho cả entity mới và entity đã tồn tại. Spring Data xác định trạng thái entity trước, sau đó chọn INSERT hoặc UPDATE. Nếu entity được nhận diện là đã tồn tại nhưng bản ghi tương ứng không còn trong database, save() không tự động chuyển sang insert. Ứng dụng cần xử lý tình huống không có dòng nào được cập nhật theo đúng quy tắc nghiệp vụ.

Với R2DBC, các thao tác này trả về Mono hoặc Flux. Kết quả và lỗi chỉ xuất hiện khi publisher được subscribe. Vì vậy, kiểm tra not-found, cập nhật entity và chuyển lỗi phải được nối trong cùng reactive pipeline.

## 1. Update một entity là gì?

Update là thay đổi dữ liệu của một bản ghi đã tồn tại. Ví dụ bảng customer có dòng:

| id | name | email | status |
|---:|---|---|---|
| 42 | An | an@example.com | ACTIVE |

Khi đổi tên khách hàng, database cần cập nhật dòng có ID 42:

~~~sql
UPDATE customer
SET name = 'An Nguyen'
WHERE id = 42;
~~~

Điều kiện WHERE xác định bản ghi được cập nhật. Nếu không có dòng nào thỏa mãn điều kiện, database không cập nhật bản ghi nào. Ứng dụng phải quyết định đó là tình huống không tìm thấy tài nguyên, xung đột đồng thời hay một kết quả chấp nhận được theo nghiệp vụ.

Một update có điều kiện đúng thường cần:

- Xác định chính xác entity hoặc ID mục tiêu.
- Kiểm tra dữ liệu đầu vào và quy tắc nghiệp vụ.
- Gửi câu lệnh update với điều kiện phù hợp.
- Kiểm tra kết quả thực thi, đặc biệt số dòng bị tác động.
- Chuyển trường hợp không cập nhật được thành kết quả hoặc lỗi nghiệp vụ phù hợp.

## 2. save() chọn INSERT hay UPDATE

Spring Data cung cấp phương thức save() trên repository:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

Phương thức này không đơn giản có nghĩa là “cứ có ID thì update, không có ID thì insert”. Spring Data sử dụng cơ chế **entity state detection** để xác định entity đang ở trạng thái mới hay đã tồn tại.

Với cơ chế mặc định, thứ tự xác định thường là:

1. Nếu entity triển khai Persistable, Spring Data sử dụng isNew() do entity cung cấp.
2. Nếu có thuộc tính @Version, Spring Data dùng trạng thái version để nhận diện entity mới.
3. Nếu không có version property, Spring Data kiểm tra ID.

Với thuộc tính version dạng wrapper như Long, version null biểu thị entity mới; version có giá trị biểu thị entity đã tồn tại. Với version primitive số nguyên, giá trị mặc định 0 biểu thị trạng thái mới. Khi không có version, ID dạng wrapper null hoặc ID primitive ở giá trị mặc định thường được xem là new.

Sau khi xác định trạng thái:

| Trạng thái entity | Thao tác được chọn |
|---|---|
| New | INSERT |
| Existing | UPDATE |

Spring Data không mặc định truy vấn database trước mỗi lần save để xem ID có đang tồn tại hay không. Trạng thái được suy ra từ entity và chiến lược nhận diện new state.

### Entity mới

Entity mới được lưu bằng insert:

~~~java
Customer customer = new Customer("An", "an@example.com");

Mono<Customer> result = customerRepository.save(customer);
~~~

Nếu database hoặc ứng dụng sinh ID trong lúc insert, entity được trả về có thể chứa ID đã được thiết lập. Nếu có @Version, framework cũng khởi tạo version theo quy tắc của Spring Data Relational.

Nếu ID đã được gán trước nhưng entity vẫn được nhận diện là new, Spring Data vẫn chọn insert. Nếu ID đó đã tồn tại, database có thể từ chối insert do vi phạm khóa chính hoặc unique constraint.

### Entity đã tồn tại

Entity được tải từ repository thường mang ID và version hiện tại:

~~~java
Mono<Customer> result = customerRepository.findById(42L);
~~~

Khi thay đổi object và gọi save:

~~~java
return customerRepository.findById(42L)
    .flatMap(customer -> {
        customer.rename("An Nguyen");
        return customerRepository.save(customer);
    });
~~~

Spring Data nhận diện entity là existing và thực hiện update. Nếu bản ghi đã bị xóa sau lần đọc, update không tìm thấy dòng phù hợp. Spring Data không tự đổi thao tác này thành insert vì điều đó có thể vô tình tạo lại một entity mà nghiệp vụ đã xóa.

## 3. Phân biệt save() với upsert

save() là API repository thống nhất cho insert hoặc update dựa trên trạng thái entity. Không nên hiểu nó như một câu lệnh database upsert.

**Upsert** là hành vi database thực hiện insert nếu chưa có bản ghi phù hợp và update nếu đã có bản ghi phù hợp, thường dựa trên khóa chính hoặc unique constraint. Cú pháp upsert khác nhau giữa các database, ví dụ PostgreSQL có ON CONFLICT, MySQL có ON DUPLICATE KEY UPDATE.

| Tình huống | save() trong Spring Data Relational | Database upsert |
|---|---|---|
| Cách chọn nhánh | Dựa trên new-state detection của entity | Dựa trên điều kiện conflict/unique key trong câu SQL |
| Kiểm tra tồn tại | Không mặc định query trước để kiểm tra ID | Database kiểm tra khi thực thi lệnh |
| Entity được nhận diện new nhưng ID đã tồn tại | Thử INSERT; có thể lỗi duplicate key | Có thể UPDATE nếu câu upsert quy định |
| Entity được nhận diện existing nhưng dòng đã mất | Thử UPDATE; không tự chuyển sang INSERT | Có thể INSERT tùy cú pháp và điều kiện upsert |
| Tính portable | Repository abstraction che giấu một phần SQL | Cú pháp và semantics phụ thuộc database |

Nếu nghiệp vụ thực sự cần upsert, hãy thiết kế câu SQL và xử lý conflict rõ ràng cho database đang sử dụng. Không dùng save() với hy vọng database sẽ tự quyết định insert hay update theo ID.

## 4. Update entity bằng repository

Với Spring Data R2DBC, repository thường kế thừa ReactiveCrudRepository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

Một service có thể tìm entity, kiểm tra không tồn tại, thay đổi trạng thái rồi lưu:

~~~java
public Mono<Customer> rename(Long id, String newName) {
    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer -> {
            customer.rename(newName);
            return customerRepository.save(customer);
        });
}
~~~

Luồng xử lý:

1. findById(id) phát một customer nếu tìm thấy.
2. Nếu không có dòng, repository phát Mono.empty().
3. switchIfEmpty chuyển trường hợp rỗng thành lỗi nghiệp vụ not-found.
4. Nếu tìm thấy, flatMap gọi hành vi thay đổi trên entity.
5. save() thực hiện update và phát entity đã lưu.

Ví dụ này phù hợp khi cần tải entity để áp dụng quy tắc nghiệp vụ trước khi cập nhật. Entity có thể chứa version để optimistic locking phát hiện thay đổi cạnh tranh.

### findById không tìm thấy

Repository trả Mono.empty() khi không có entity. Không nên dùng null để biểu diễn trường hợp này:

~~~java
return customerRepository.findById(id)
    .switchIfEmpty(Mono.error(
        new CustomerNotFoundException(id)
    ));
~~~

switchIfEmpty chỉ được kích hoạt khi publisher hoàn tất mà không phát giá trị. Nó không bắt lỗi database; lỗi truy vấn vẫn đi theo tín hiệu onError.

## 5. Điều gì xảy ra nếu entity bị xóa giữa lúc đọc và update?

Giả sử request A đọc customer ID 42. Trước khi A lưu thay đổi, request B xóa customer đó.

~~~text
Request A                 Database                 Request B
    |                         |                         |
    |---- SELECT id = 42 ---->|                         |
    |<--- Customer 42 --------|                         |
    |                         |<---- DELETE id = 42 ----|
    |                         |---- Xóa thành công ---->|
    |---- UPDATE id = 42 ---->|                         |
    |<--- 0 dòng phù hợp -----|                         |
    |                         |                         |
    v
Không thể cập nhật entity đã bị xóa
~~~

Đây là một race condition: kết quả của lần đọc không bảo đảm bản ghi vẫn tồn tại tại thời điểm ghi. Chỉ kiểm tra findById() trước update chưa đủ để bảo đảm update thành công.

Nếu entity có @Version, câu update do Spring Data tạo có thể kiểm tra cả ID và version. Khi bản ghi đã bị xóa hoặc version không còn khớp, không có dòng nào được cập nhật và Spring Data báo lỗi optimistic locking.

Nếu entity không có version property, update vẫn phải tác động tới dòng theo ID. Khi không có dòng phù hợp, thao tác lưu không thành công; Spring Data không tự insert lại. Kiểu exception cụ thể phụ thuộc đường thực thi và phiên bản framework, vì vậy tầng ứng dụng nên xử lý theo loại lỗi thực tế được phát ra thay vì dựa vào một câu SQL giả định.

## 6. Phân biệt not-found và optimistic locking conflict

Hai trường hợp có thể dẫn đến update không tác động dòng nào nhưng ý nghĩa nghiệp vụ khác nhau:

- **Not found:** tài nguyên được yêu cầu không tồn tại tại thời điểm xử lý.
- **Optimistic locking conflict:** entity đã được đọc nhưng phiên bản trong database đã thay đổi trước khi cập nhật.

Khi dùng @Version, một update có điều kiện theo ID và version không thành công có thể do:

1. Bản ghi đã bị xóa.
2. Bản ghi vẫn tồn tại nhưng version đã tăng bởi request khác.

Chỉ nhìn số dòng được cập nhật bằng 0 không đủ phân biệt hai trường hợp này. Nếu API cần trả 404 cho bản ghi đã xóa và 409 cho version conflict, ứng dụng có thể đọc lại để xác định trạng thái hiện tại. Tuy nhiên, lần đọc bổ sung vẫn có thể gặp race condition nếu dữ liệu tiếp tục thay đổi. Muốn phân loại có bảo đảm mạnh hơn cần cân nhắc transaction, isolation level và chiến lược locking phù hợp.

Một chính sách API thường gặp:

| Trường hợp | Phản hồi có thể chọn |
|---|---|
| Không tìm thấy ngay ở lần đọc ban đầu | 404 Not Found |
| Entity bị xóa trước khi update hoàn tất | 404 hoặc 409 tùy hợp đồng và cách phân loại |
| Version đã cũ do request khác cập nhật | 409 Conflict |
| Lỗi kết nối hoặc lỗi database ngoài dự kiến | 5xx phù hợp |

Không nên trả 404 cho mọi lỗi update. Lỗi optimistic locking thường cần được biểu diễn là xung đột để client biết dữ liệu cần được tải lại hoặc hợp nhất.

## 7. Vai trò của @Version trong update

@Version đánh dấu thuộc tính version mà Spring Data dùng cho optimistic locking. Ví dụ:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;

    public void rename(String newName) {
        this.name = newName;
    }
}
~~~

Giả sử database đang lưu:

| id | name | version |
|---:|---|---:|
| 42 | An | 5 |

Hai request cùng tải version 5. Request A cập nhật trước và version được tăng thành 6. Request B vẫn giữ version 5. Khi B lưu, điều kiện update không còn khớp.

Về ý tưởng, SQL được tạo có dạng:

~~~sql
UPDATE customer
SET name = :name,
    version = :next_version
WHERE id = :id
  AND version = :previous_version;
~~~

Đây là minh họa ngữ nghĩa, không phải cam kết về SQL chính xác mà mọi phiên bản Spring Data hoặc mọi dialect sẽ sinh ra. Framework quản lý version cho các thao tác entity được hỗ trợ; ứng dụng nên tiếp tục sử dụng entity trả về từ save() vì version sau khi lưu có thể đã thay đổi.

Khi số dòng bị tác động không như mong đợi do version không khớp, Spring Data báo lỗi thuộc nhóm optimistic locking, thường là OptimisticLockingFailureException. Không nên âm thầm bỏ qua lỗi này hoặc ghi đè bằng một update không có version predicate nếu nghiệp vụ cần bảo vệ thay đổi đồng thời.

### Version không thay thế kiểm tra not-found ban đầu

@Version giúp phát hiện một update không còn khớp với trạng thái đã đọc. Nó không tự cung cấp thông điệp nghiệp vụ “customer không tồn tại” ở mọi tình huống. Nếu cần trả 404 khi ID không tồn tại ngay từ đầu, vẫn nên kiểm tra kết quả tìm kiếm hoặc dùng thao tác update có điều kiện và diễn giải số dòng bị tác động.

## 8. Update trực tiếp bằng DatabaseClient

Không phải lúc nào cũng cần tải toàn bộ entity. Nếu chỉ thay đổi một vài cột và không cần thực thi logic trên domain object, có thể dùng DatabaseClient:

~~~java
public Mono<Integer> updateStatus(Long id, String status) {
    return databaseClient.sql(
            "UPDATE customer SET status = :status WHERE id = :id"
        )
        .bind("status", status)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
~~~

rowsUpdated() trả về số dòng được database báo là đã tác động. Ứng dụng có thể kiểm tra:

~~~java
public Mono<Void> updateStatus(Long id, String status) {
    return databaseClient.sql(
            "UPDATE customer SET status = :status WHERE id = :id"
        )
        .bind("status", status)
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .flatMap(rows -> {
            if (rows == 0) {
                return Mono.error(
                    new CustomerNotFoundException(id)
                );
            }
            return Mono.empty();
        });
}
~~~

Đây là cách xử lý đơn giản khi database/driver cung cấp số dòng phù hợp với chính sách ứng dụng. Cần lưu ý semantics của affected rows có thể khác nhau theo database: có hệ thống báo số dòng khớp điều kiện, có hệ thống có thể báo số dòng thực sự thay đổi. Nếu câu lệnh gán lại đúng giá trị cũ, kết quả 0 không nhất thiết có nghĩa bản ghi không tồn tại trên mọi vendor.

Nếu cần phân biệt chắc chắn bản ghi không tồn tại với update không làm thay đổi giá trị, có thể thực hiện kiểm tra tồn tại bổ sung hoặc thiết kế câu lệnh trả về thông tin phù hợp với database. Cần xét race condition và transaction khi làm bước kiểm tra bổ sung.

### Cập nhật một phần entity

Một lệnh DatabaseClient update chỉ thay đổi các cột được liệt kê. Nó không tự tải hoặc đồng bộ toàn bộ entity domain. Nếu ứng dụng đã giữ một object Customer trong bộ nhớ, object đó có thể trở nên cũ sau câu SQL này. Hãy tải lại dữ liệu cần thiết hoặc cập nhật read model theo quy tắc rõ ràng.

## 9. Update trực tiếp và optimistic locking

Khi dùng SQL tự viết, @Version trên entity không tự động sửa câu SQL do ứng dụng khai báo trong DatabaseClient. Nếu muốn bảo vệ optimistic locking, câu lệnh phải tự kiểm tra version và tăng version:

~~~sql
UPDATE customer
SET status = :status,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
~~~

Ví dụ:

~~~java
public Mono<Integer> updateStatus(
        Long id,
        Long expectedVersion,
        String status) {

    return databaseClient.sql(
            "UPDATE customer " +
            "SET status = :status, version = version + 1 " +
            "WHERE id = :id AND version = :expectedVersion"
        )
        .bind("status", status)
        .bind("id", id)
        .bind("expectedVersion", expectedVersion)
        .fetch()
        .rowsUpdated();
}
~~~

Nếu rowsUpdated() trả về 0, có ít nhất hai khả năng:

- Không tồn tại dòng có ID đó.
- Dòng tồn tại nhưng version không bằng expectedVersion.

Ứng dụng có thể kiểm tra tồn tại để phân loại:

~~~java
return updateStatus(id, expectedVersion, status)
    .flatMap(rows -> {
        if (rows > 0) {
            return Mono.empty();
        }

        return customerRepository.existsById(id)
            .flatMap(exists -> exists
                ? Mono.error(new CustomerConflictException(id))
                : Mono.error(new CustomerNotFoundException(id))
            );
    });
~~~

Đây là ví dụ về chính sách phân loại ở mức ứng dụng. Việc kiểm tra existsById() sau update có thể quan sát trạng thái mới hơn hoặc khác đi nếu có request khác chạy xen giữa. Nếu cần phân loại nhất quán, hãy đặt các thao tác trong transaction và chọn isolation/locking phù hợp với database, hoặc dùng một câu lệnh vendor-specific có khả năng trả về trạng thái cần thiết.

Không được để một đường ghi SQL tùy chỉnh thay đổi dữ liệu nhưng quên tăng version. Nếu một request khác đang giữ version cũ, lần update tiếp theo sẽ không phát hiện được thay đổi trước đó.

## 10. Chọn giữa load-modify-save và direct update

Hai cách tiếp cận phù hợp với các nhu cầu khác nhau:

| Tiêu chí | Load → Modify → save() | DatabaseClient UPDATE |
|---|---|---|
| Đọc entity trước | Có | Không bắt buộc |
| Áp dụng quy tắc domain trên object | Thuận tiện | Ứng dụng phải tự tổ chức |
| Mapping và version | Spring Data quản lý theo entity metadata | SQL tự viết phải quản lý rõ |
| Kiểm tra số dòng tác động | Spring Data xử lý trong persistence path | Ứng dụng đọc rowsUpdated() |
| Cập nhật một vài cột | Có thể ghi theo mapping entity | Tường minh, gọn cho lệnh cập nhật hẹp |
| Phù hợp | Thay đổi có hành vi nghiệp vụ hoặc cần entity | Cập nhật hàng loạt, thao tác hẹp hoặc query tùy chỉnh |

Nên dùng load-modify-save khi cần kiểm tra trạng thái hiện tại, áp dụng hành vi domain, hoặc tận dụng @Version của Spring Data. Dùng direct update khi thao tác được biểu diễn tốt bằng một câu SQL và ứng dụng chủ động xử lý affected rows, version, transaction cùng tính nhất quán của object đang giữ.

## 11. Xử lý lỗi trong reactive pipeline

Vì repository trả Mono hoặc Flux, lỗi database không được ném đồng bộ ngay tại dòng gọi phương thức. Nó thường được phát ra khi publisher được subscribe. Có thể ánh xạ các lỗi persistence sang lỗi nghiệp vụ:

~~~java
public Mono<CustomerResponse> rename(
        Long id,
        String newName) {

    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer -> {
            customer.rename(newName);
            return customerRepository.save(customer);
        })
        .map(customer -> new CustomerResponse(
            customer.getId(),
            customer.getName()
        ))
        .onErrorMap(
            OptimisticLockingFailureException.class,
            error -> new CustomerConflictException(id, error)
        );
}
~~~

Các exception CustomerNotFoundException và CustomerConflictException trong ví dụ là kiểu do ứng dụng định nghĩa. Tầng web có thể ánh xạ chúng thành 404 và 409 theo hợp đồng API.

Không nên bắt mọi lỗi rồi trả về Mono.empty(). Làm vậy sẽ biến lỗi kết nối, lỗi SQL, lỗi constraint hoặc optimistic locking thành kết quả “không có dữ liệu”, khiến caller không thể phân biệt nguyên nhân.

Không nên dùng onErrorResume để retry vô điều kiện một update bị xung đột. Nếu cần retry, phải tải version mới, áp dụng lại thay đổi theo nghiệp vụ và cân nhắc tính idempotent của thao tác.

## 12. Transaction khi update nhiều bước

Một nghiệp vụ có thể cần cập nhật customer và ghi audit record. Nếu hai thao tác phải cùng thành công hoặc cùng thất bại, hãy dùng reactive transaction:

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String status) {
    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer -> {
            customer.changeStatus(status);
            return customerRepository.save(customer);
        })
        .flatMap(saved ->
            auditRepository.recordStatusChange(
                saved.getId(), status
            ).thenReturn(saved)
        );
}
~~~

Phương thức phải trả về publisher để Spring quản lý transaction reactive. Các repository cần tham gia cùng reactive transaction manager và ConnectionFactory. Không tự gọi subscribe() bên trong phương thức transactional, vì subscription tách rời có thể chạy ngoài transaction context.

Transaction bảo đảm tính nguyên tử của các thao tác thuộc transaction. @Version vẫn cần thiết nếu muốn phát hiện request khác đã cập nhật entity từ lúc được đọc. Transaction và optimistic locking giải quyết hai vấn đề khác nhau.

## 13. Các tình huống thường gặp

| Tình huống | Hành vi cần hiểu | Cách xử lý |
|---|---|---|
| ID không tồn tại khi gọi findById | Repository phát Mono.empty() | Dùng switchIfEmpty để trả not-found |
| Entity được nhận diện new nhưng ID trùng | Spring Data chọn INSERT | Xử lý duplicate key hoặc sửa chiến lược new-state |
| Entity được nhận diện existing nhưng dòng đã bị xóa | UPDATE không khớp; không tự INSERT | Trả lỗi phù hợp, thường not-found hoặc conflict |
| Version cũ do request khác update | Optimistic locking thất bại | Trả conflict, tải lại và giải quyết |
| SQL tùy chỉnh update 0 dòng | Có thể do không tồn tại hoặc version không khớp | Kiểm tra điều kiện và phân loại theo chính sách |
| Gán lại cùng giá trị cũ | Affected rows có thể phụ thuộc database | Xác nhận semantics driver/database |
| Update nhiều bảng trong một nghiệp vụ | Có thể cần nguyên tử | Dùng reactive transaction phù hợp |
| Một đường ghi bỏ qua tăng version | Có thể che giấu xung đột | Mọi đường ghi phải tuân thủ quy ước version |

## 14. Thiết kế phản hồi API cho update

Một API update cần có hợp đồng rõ ràng về trường hợp không tìm thấy và xung đột:

~~~text
PUT /customers/{id}
       |
       v
Tìm customer theo ID
       |
       +---- Không có ----> 404 Not Found
       |
       v
Kiểm tra và áp dụng thay đổi
       |
       v
Lưu entity
       |
       +---- Version conflict ----> 409 Conflict
       |
       +---- Database error ------> 5xx
       |
       v
Trả response DTO
~~~

Các mã trạng thái là một lựa chọn thiết kế API phổ biến, không phải quy định bắt buộc của Spring Data:

- 404 Not Found: ID không tồn tại tại thời điểm kiểm tra theo hợp đồng API.
- 409 Conflict: trạng thái hiện tại không còn phù hợp với version mà client hoặc service đã đọc.
- 400 Bad Request hoặc 422 Unprocessable Content: dữ liệu đầu vào không hợp lệ theo hợp đồng API.
- 5xx: lỗi hạ tầng hoặc lỗi database không được xử lý như một tình huống nghiệp vụ.

Nếu API nhận version từ client, có thể dùng version như concurrency token hoặc biểu diễn qua HTTP ETag/If-Match. Khi token không còn khớp, trả phản hồi conflict phù hợp. Cần xác thực token và không cho phép client tự đặt version tùy ý để ghi đè dữ liệu.

## 15. Ghi nhớ

- save() chọn INSERT hay UPDATE dựa trên new-state detection của entity; nó không mặc định là database upsert.
- Entity được nhận diện là existing sẽ đi theo nhánh update. Nếu bản ghi không còn, Spring Data không tự insert lại.
- findById() trả Mono.empty() khi không tìm thấy; dùng switchIfEmpty để chuyển thành lỗi not-found.
- Có race condition giữa lần đọc và lần ghi; lần đọc thành công không bảo đảm update sau đó thành công.
- @Version giúp phát hiện thay đổi đồng thời. Update không khớp version có thể phát sinh OptimisticLockingFailureException.
- Direct SQL qua DatabaseClient cần kiểm tra rowsUpdated() và tự đưa version predicate/increment vào câu lệnh nếu cần optimistic locking.
- Số affected rows có thể phụ thuộc database, nhất là khi update gán lại cùng giá trị cũ.
- Not-found và optimistic locking conflict có ý nghĩa khác nhau; không nên gộp mọi lỗi update thành 404 hoặc kết quả rỗng.
- Dùng reactive transaction cho nhiều thao tác cần nguyên tử, và tiếp tục pipeline thay vì tự gọi subscribe() trong service.
