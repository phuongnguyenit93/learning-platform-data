# Thay API lỗi thời như getOne, getById và các phương thức xóa theo lô trong Spring Data JPA

Spring Data JPA đã bổ sung các API rõ nghĩa hơn cho việc lấy reference của entity và chuẩn hóa tên các phương thức xóa theo lô. Khi nâng cấp dự án, các lời gọi như getOne(), getById() và deleteInBatch() có thể tạo cảnh báo deprecated. Việc thay tên method đơn thuần chưa đủ: cần giữ đúng ý nghĩa của thao tác cũ, đặc biệt là phân biệt lấy một reference với kiểm tra entity có tồn tại, và phân biệt xóa từng entity với bulk delete.

Bài học này tập trung vào hai nhóm thay đổi:

- Thay getOne() và getById() bằng getReferenceById() khi code thực sự cần một entity reference; dùng findById() khi cần xác nhận entity tồn tại và xử lý trường hợp không tìm thấy.
- Thay deleteInBatch() bằng deleteAllInBatch(Iterable), hoặc chọn deleteAllByIdInBatch(ids) khi chỉ có ID. Chỉ dùng bulk delete khi chấp nhận các semantics khác với xóa từng entity: không chạy JPA cascade/lifecycle callback và có thể làm persistence context mất đồng bộ.

Các ví dụ sử dụng Spring Data JPA repository với Customer và PurchaseOrder. API cụ thể có thể khác theo phiên bản Spring Data JPA đang được Spring Boot BOM quản lý; hãy kiểm tra dependency thực tế trước khi sửa hàng loạt.

## 1. Vì sao các API này bị deprecated?

Các method cũ vẫn có thể tồn tại trong một số phiên bản Spring Data JPA, nhưng API hiện hành đánh dấu chúng deprecated và hướng người dùng sang method có tên mô tả rõ hơn:

| API cũ | API thay thế | Ý nghĩa |
|---|---|---|
| getOne(id) | getReferenceById(id) | Lấy reference tới entity theo ID |
| getById(id) | getReferenceById(id) | Lấy reference tới entity theo ID |
| deleteInBatch(entities) | deleteAllInBatch(entities) | Bulk delete một tập entity |
| — | deleteAllByIdInBatch(ids) | Bulk delete theo tập ID |
| — | deleteAllInBatch() | Bulk delete toàn bộ entity của repository |

getOne() và getById() đều có semantics lấy reference, không phải truy vấn xác nhận entity tồn tại. getReferenceById() làm rõ ý định đó.

deleteInBatch() được thay bằng tên deleteAllInBatch(Iterable) để thống nhất với các API deleteAllInBatch() và deleteAllByIdInBatch(). Việc thay method không biến bulk delete thành thao tác xóa từng entity.

Theo API reference hiện hành, getReferenceById() có từ Spring Data JPA 2.7; deleteAllInBatch(Iterable) và deleteAllByIdInBatch(Iterable) có từ 2.5. Kiểm tra version đang dùng nếu dự án chưa ở các dòng này.

## 2. getOne(), getById() và getReferenceById() có cùng ý nghĩa gì?

Các method này trả về reference của entity theo khóa chính. JPA provider có thể trả về proxy/lazy reference và trì hoãn việc đọc hàng database cho đến khi code truy cập một thuộc tính cần khởi tạo entity.

Ví dụ với repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Code cũ:

~~~java
Customer customer = customerRepository.getOne(customerId);
~~~

Hoặc:

~~~java
Customer customer = customerRepository.getById(customerId);
~~~

Code thay thế trong phiên bản hỗ trợ:

~~~java
Customer customer =
        customerRepository.getReferenceById(customerId);
~~~

Tên method mới nói rõ rằng ứng dụng đang lấy reference. Không nên hiểu rằng lời gọi này đã xác nhận customerId tồn tại trong database.

Nếu ID không tồn tại, provider thường có thể trả proxy trước rồi ném EntityNotFoundException khi proxy được khởi tạo hoặc thuộc tính được truy cập. Một số provider có thể phát hiện và báo lỗi sớm hơn. Vì vậy, thời điểm exception xuất hiện không phải lúc nào cũng ngay tại dòng getReferenceById().

## 3. getReferenceById() khác findById() như thế nào?

Đây là quyết định quan trọng nhất khi thay API cũ.

| Tiêu chí | getReferenceById(id) | findById(id) |
|---|---|---|
| Kiểu trả về | Entity reference | Optional<Entity> |
| Mục đích | Có reference để thiết lập quan hệ hoặc thao tác tiếp | Tìm và xác nhận entity |
| Đọc database | Có thể trì hoãn cho tới khi cần dữ liệu | Thường truy vấn ngay nếu chưa có trong persistence context |
| Không tồn tại | Có thể ném EntityNotFoundException khi reference được khởi tạo; provider có thể báo sớm | Trả Optional.empty() |
| Phù hợp | Gán association bằng ID khi không cần đọc dữ liệu liên quan | Kiểm tra tồn tại, hiển thị thông tin, trả lỗi nghiệp vụ rõ ràng |

Dùng getReferenceById() khi code chỉ cần một reference hợp lệ về mặt cấu trúc để gán association và database có foreign key bảo vệ tính toàn vẹn:

~~~java
order.setCustomer(
        customerRepository.getReferenceById(customerId)
);
~~~

Dùng findById() khi cần xác nhận ID tồn tại và trả lỗi nghiệp vụ có kiểm soát:

~~~java
Customer customer = customerRepository.findById(customerId)
        .orElseThrow(() ->
                new CustomerNotFoundException(customerId));
~~~

Không thay findById() bằng getReferenceById() chỉ để giảm một câu SELECT nếu luồng nghiệp vụ cần biết ngay khách hàng có tồn tại hay không.

## 4. Ví dụ entity và repository

Entity Customer tối giản:

~~~java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

Repository:

~~~java
package com.example.orders;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Spring Data JPA kế thừa getReferenceById(), findById() và các method xóa theo lô từ JpaRepository. Không cần tự khai báo lại các method này trong interface.

Exception nghiệp vụ:

~~~java
package com.example.orders;

public class CustomerNotFoundException extends RuntimeException {

    public CustomerNotFoundException(Long id) {
        super("Customer not found: " + id);
    }
}
~~~

Ví dụ này dùng constructor nhận Long để giữ nguyên ID trong thông báo lỗi. Ứng dụng có thể ánh xạ exception sang HTTP 404 ở tầng web.

## 5. Khi nào dùng getReferenceById() để gán association?

Một use case phổ biến là tạo PurchaseOrder và gán Customer bằng ID từ request. Nếu service không cần đọc tên hoặc thuộc tính khác của Customer, có thể lấy reference:

~~~java
@Transactional
public PurchaseOrder createOrder(
        Long customerId,
        BigDecimal totalAmount) {

    Customer customer =
            customerRepository.getReferenceById(customerId);

    PurchaseOrder order =
            new PurchaseOrder(customer, totalAmount);

    return orderRepository.save(order);
}
~~~

Đây là method minh họa trong service có CustomerRepository và PurchaseOrderRepository được inject. Entity PurchaseOrder phải có association ManyToOne tới Customer và constructor tương ứng.

Ưu điểm là ứng dụng không cần tải toàn bộ Customer chỉ để thiết lập foreign key. Tuy nhiên, reference không thay thế validation nghiệp vụ. Nếu customerId sai, lỗi có thể xuất hiện khi association được khởi tạo hoặc khi database kiểm tra foreign key lúc flush/commit.

Nếu API cần trả ngay lỗi CustomerNotFoundException trước khi tạo order, hãy dùng findById():

~~~java
@Transactional
public PurchaseOrder createOrder(
        Long customerId,
        BigDecimal totalAmount) {

    Customer customer = customerRepository.findById(customerId)
            .orElseThrow(() ->
                    new CustomerNotFoundException(customerId));

    PurchaseOrder order =
            new PurchaseOrder(customer, totalAmount);

    return orderRepository.save(order);
}
~~~

Chọn cách nào dựa trên hợp đồng nghiệp vụ và thời điểm cần xác thực, không dựa riêng vào số câu SQL.

## 6. Không dùng getReferenceById() để đọc dữ liệu ngay lập tức

Ví dụ:

~~~java
Customer customer =
        customerRepository.getReferenceById(customerId);

String name = customer.getName();
~~~

Lệnh getName() có thể kích hoạt proxy và truy vấn database. Nếu mục tiêu là hiển thị tên, findById() thường dễ hiểu hơn vì nó thể hiện rõ ý định đọc entity.

Nếu lấy reference trong một transaction rồi trả proxy ra ngoài transaction, code ở tầng web có thể truy cập association sau khi persistence context đã đóng và gặp LazyInitializationException.

Nên đọc dữ liệu cần thiết và tạo DTO trong transaction:

~~~java
@Transactional(readOnly = true)
public CustomerView getCustomer(Long id) {
    Customer customer = customerRepository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

    return new CustomerView(customer.getId(), customer.getName());
}
~~~

DTO:

~~~java
package com.example.orders;

public record CustomerView(Long id, String name) {
}
~~~

Không trả một lazy proxy ra khỏi service chỉ vì method mới trả về một object ngay lập tức. Reference có thể chưa được khởi tạo đầy đủ.

## 7. Kiểm tra sự tồn tại: chọn đúng API

Nếu chỉ cần biết ID có tồn tại hay không, dùng existsById():

~~~java
if (!customerRepository.existsById(customerId)) {
    throw new CustomerNotFoundException(customerId);
}
~~~

Nếu sau đó cần đọc Customer, gọi findById() để lấy entity. Không nên gọi existsById() rồi tiếp tục getReferenceById() chỉ để đọc thuộc tính: đó có thể là hai lần kiểm tra/truy vấn mà một lần findById() đã giải quyết được.

Các lựa chọn:

- Chỉ kiểm tra tồn tại: existsById(id).
- Cần entity và xử lý trường hợp không có: findById(id).
- Cần reference để gán association, không cần đọc entity: getReferenceById(id).

existsById() rồi mới ghi vẫn có race condition nếu một transaction khác xóa entity giữa bước kiểm tra và bước ghi. Foreign key constraint và xử lý exception ở database vẫn là lớp bảo vệ cuối cùng.

## 8. Di chuyển từ getOne() và getById() theo đúng ý định

Không nên thay toàn bộ chuỗi getOne bằng getReferenceById một cách máy móc. Trước khi sửa, đọc các dòng sau lời gọi để biết code đang làm gì.

| Code cũ và ngữ cảnh | Thay thế phù hợp |
|---|---|
| Lấy reference để gán ManyToOne | getReferenceById(id) |
| Đọc name/email/status ngay sau khi lấy | findById(id) |
| Cần trả 404 nếu không tồn tại | findById(id).orElseThrow(...) |
| Chỉ cần kiểm tra có bản ghi | existsById(id) |
| Cần dùng reference trong cùng transaction | getReferenceById(id) |
| Trả entity/proxy ra API | Đọc trong transaction và chuyển DTO |

Ví dụ migration:

~~~java
// Trước: chỉ cần reference để gán quan hệ.
Customer customer = customerRepository.getOne(customerId);

// Sau: thể hiện đúng ý định lấy reference.
Customer customer =
        customerRepository.getReferenceById(customerId);
~~~

~~~java
// Trước: code dùng getById rồi đọc tên.
String name = customerRepository.getById(customerId).getName();

// Sau: xác nhận tồn tại và đọc dữ liệu.
String name = customerRepository.findById(customerId)
        .map(Customer::getName)
        .orElseThrow(() ->
                new CustomerNotFoundException(customerId));
~~~

Cả hai thay đổi đều loại bỏ API deprecated, nhưng chỉ thay đổi thứ hai làm rõ việc xử lý trường hợp không tìm thấy.

## 9. Phiên bản Spring Data JPA và khả năng tương thích

Không phải mọi dự án đều có cùng tập API. Spring Boot quản lý Spring Data JPA qua dependency BOM; không nên tự nâng riêng Spring Data JPA nếu chưa kiểm tra compatibility với Spring Framework, Hibernate và Jakarta Persistence.

Các mốc API cần lưu ý:

| API | Mốc phiên bản được API reference ghi nhận |
|---|---|
| getById(id) | Có từ Spring Data JPA 2.5 |
| getReferenceById(id) | Có từ Spring Data JPA 2.7 |
| deleteAllInBatch(Iterable) | Có từ Spring Data JPA 2.5 |
| deleteAllByIdInBatch(ids) | Có từ Spring Data JPA 2.5 |

Nếu dự án đang ở phiên bản trước 2.7, getReferenceById() có thể chưa có. Trong trường hợp cần lấy reference ở phiên bản đó, có thể dùng EntityManager.getReference() trong custom repository/service được quản lý transaction, hoặc nâng Spring Data JPA theo BOM tương thích.

Ví dụ với EntityManager:

~~~java
@PersistenceContext
private EntityManager entityManager;

@Transactional
public Customer reference(Long id) {
    return entityManager.getReference(Customer.class, id);
}
~~~

Đây là API chuẩn JPA. Tuy nhiên, khi repository đã hỗ trợ getReferenceById(), ưu tiên dùng method đó để code nhất quán với Spring Data.

Deprecated không đồng nghĩa method đã bị xóa ngay trong phiên bản hiện tại. Nó báo rằng API không còn được khuyến nghị và có thể bị loại bỏ ở phiên bản lớn sau. Hãy xử lý warning trước khi nâng major version.

## 10. Thay deleteInBatch() bằng deleteAllInBatch()

Code cũ:

~~~java
customerRepository.deleteInBatch(customers);
~~~

Code thay thế:

~~~java
customerRepository.deleteAllInBatch(customers);
~~~

deleteInBatch(Iterable<T>) đã deprecated; API reference hướng tới deleteAllInBatch(Iterable<T>).

Cả hai đều mang semantics bulk delete. deleteAllInBatch(customers) tạo một bulk query cho tập entity được cung cấp; không có nghĩa là Spring gọi EntityManager.remove() lần lượt cho từng Customer.

Điểm cần nhớ:

- Không thực hiện JPA cascade semantics như xóa entity từng cái.
- Không phát các JPA lifecycle event như @PreRemove.
- Persistence context có thể vẫn giữ entity vừa bị xóa ở trạng thái managed.
- Nên flush thay đổi đang chờ trước bulk operation nếu chúng phải được ghi trước.
- Sau bulk operation, cân nhắc clear/detach persistence context để tránh đọc trạng thái cũ.

Đừng thay deleteInBatch bằng deleteAllInBatch nếu code phụ thuộc @PreRemove, cascade REMOVE, orphan removal hoặc listener để cập nhật dữ liệu liên quan. Khi đó cần chọn đường xóa entity thông thường.

## 11. Chọn deleteAllByIdInBatch() khi chỉ có ID

Nếu caller chỉ có danh sách ID, không cần tải entity trước để truyền vào deleteAllInBatch().

~~~java
customerRepository.deleteAllByIdInBatch(customerIds);
~~~

Method này xóa các entity được xác định bởi các ID bằng một bulk query. Không cần:

~~~java
List<Customer> customers =
        customerRepository.findAllById(customerIds);

customerRepository.deleteAllInBatch(customers);
~~~

nếu mục tiêu chỉ là bulk delete theo ID và không cần kiểm tra từng entity.

So sánh:

| Method | Input | Mục đích |
|---|---|---|
| deleteAllInBatch() | Không có | Xóa toàn bộ entity của repository bằng bulk operation |
| deleteAllInBatch(entities) | Entity iterable | Bulk delete các entity được cung cấp |
| deleteAllByIdInBatch(ids) | ID iterable | Bulk delete theo ID |
| deleteAll(entities) | Entity iterable | Xóa từng entity theo semantics repository/JPA |
| deleteAllById(ids) | ID iterable | Xóa theo đường xóa thông thường, không phải API batch |

Nếu cần trả số lượng hàng thực sự bị ảnh hưởng, các method batch có kiểu trả về void không cung cấp count. Có thể viết custom @Modifying query trả int, nhưng cần hiểu bulk semantics và đồng bộ persistence context tương ứng.

## 12. Bulk delete khác xóa từng entity như thế nào?

Đây là khác biệt quan trọng hơn tên method.

~~~java
customerRepository.deleteAll(customers);
~~~

là đường xóa entity thông thường của repository. Spring Data xử lý từng entity qua cơ chế delete của repository/JPA, nên có thể áp dụng cascade và lifecycle callback theo mapping.

~~~java
customerRepository.deleteAllInBatch(customers);
~~~

là bulk delete. Nó ưu tiên thực thi một truy vấn cho tập entity, không tải/xóa từng entity qua lifecycle thông thường.

| Hành vi | deleteAll(entities) | deleteAllInBatch(entities) |
|---|---|---|
| Xóa qua entity remove | Có | Không theo từng entity |
| JPA cascade REMOVE | Được áp dụng theo mapping | Không được áp dụng |
| @PreRemove / @PostRemove | Được gọi theo lifecycle entity | Không được gọi |
| Số lần thao tác database | Có thể nhiều statement | Bulk query |
| First-level cache | Entity được quản lý theo lifecycle | Có thể stale sau bulk |
| Phù hợp | Domain cần cascade/callback | Xóa số lượng lớn, không cần lifecycle từng entity |

Các hành động do database thực hiện, ví dụ foreign key ON DELETE CASCADE hoặc trigger, là cơ chế database riêng. Chúng không phải JPA cascade và không đồng nghĩa với việc JPA lifecycle callback được gọi.

## 13. Persistence context có thể stale sau bulk delete

Giả sử Customer đã được load vào persistence context:

~~~java
Customer customer = customerRepository.findById(id)
        .orElseThrow();

customerRepository.deleteAllByIdInBatch(List.of(id));

System.out.println(customer.getName());
~~~

Bulk query xóa hàng trong database nhưng không đồng bộ object Customer đang managed. Code vẫn có thể đọc được tên từ object trong bộ nhớ dù hàng đã bị xóa.

Spring Data JPA API reference cảnh báo các batch delete có thể làm first-level cache và database mất đồng bộ. Vì vậy, nếu tiếp tục thao tác với cùng EntityManager, cần cân nhắc flush trước và clear sau.

Ví dụ:

~~~java
@Transactional
public void deleteIds(Collection<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return;
    }

    entityManager.flush();
    customerRepository.deleteAllByIdInBatch(ids);
    entityManager.clear();
}
~~~

entityManager.flush() đồng bộ thay đổi đang chờ trước khi chạy bulk delete. entityManager.clear() detach toàn bộ entity đang được quản lý trong persistence context.

clear() ảnh hưởng tất cả entity managed trong context, không chỉ Customer bị xóa. Chỉ gọi nó khi service boundary và các thao tác xung quanh cho phép. Nếu cần giữ entity khác managed, hãy thiết kế transaction hoặc persistence context phù hợp thay vì clear tùy tiện.

Không cần gọi flush/clear máy móc sau mọi repository delete. Hãy xem có entity managed nào liên quan, có thay đổi chưa flush và code còn sử dụng persistence context sau bulk operation hay không.

## 14. Xóa theo lô với danh sách ID lớn

deleteAllByIdInBatch(ids) dùng một bulk query với tập ID. Database có giới hạn số bind parameter hoặc giới hạn kích thước câu lệnh. Với danh sách rất lớn, một câu IN có thể vượt giới hạn của hệ quản trị hoặc tạo kế hoạch thực thi kém.

Có thể chia danh sách thành các chunk nhỏ. Kích thước chunk phải dựa trên database/provider và workload, không có một con số đúng cho mọi hệ thống.

Ví dụ service minh họa với helper partition do ứng dụng tự triển khai:

~~~java
@Transactional
public void deleteInChunks(List<Long> ids, int chunkSize) {
    if (ids == null || ids.isEmpty()) {
        return;
    }
    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize must be positive");
    }

    entityManager.flush();

    for (int start = 0; start < ids.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, ids.size());
        List<Long> chunk = ids.subList(start, end);
        customerRepository.deleteAllByIdInBatch(chunk);
    }

    entityManager.clear();
}
~~~

Ví dụ này dùng subList view của danh sách gốc và truyền từng phần cho repository. Không sửa danh sách ids trong lúc vòng lặp chạy.

Nếu một transaction bao trùm tất cả chunk, lỗi ở chunk sau có thể rollback toàn bộ transaction. Nếu muốn commit từng chunk, cần thiết kế transaction boundary riêng và hiểu rõ trade-off về tính nguyên tử. Không thêm REQUIRES_NEW chỉ để tăng tốc mà chưa xác định yêu cầu nghiệp vụ.

## 15. Khi cần cascade và lifecycle callback, không dùng bulk delete

Giả sử Customer có các entity con cần xử lý khi xóa:

- Order cần được giữ lại hoặc chuyển trạng thái.
- Address cần xóa theo cascade REMOVE.
- Audit listener cần ghi sự kiện.
- @PreRemove cần giải phóng tài nguyên nghiệp vụ.

Bulk delete bỏ qua lifecycle từng entity nên không đáp ứng yêu cầu này.

Dùng đường xóa entity thông thường:

~~~java
@Transactional
public void deleteCustomers(Collection<Long> ids) {
    List<Customer> customers = customerRepository.findAllById(ids);
    customerRepository.deleteAll(customers);
}
~~~

Cách này tải các entity cần xóa rồi xóa theo lifecycle. Chi phí database và bộ nhớ có thể cao hơn, nhưng giữ semantics của JPA entity operations.

Nếu cần xử lý rất nhiều entity mà vẫn phải phát domain event/cascade, cân nhắc batch theo từng nhóm entity trong transaction có giới hạn, hoặc thiết kế bulk workflow riêng có xử lý rõ các quan hệ và audit. Không kỳ vọng một bulk DELETE tự gọi @PreRemove cho từng hàng.

## 16. Batch delete và soft delete

Nếu entity dùng Hibernate @SoftDelete hoặc @SQLDelete, cần đặc biệt cẩn thận khi chuyển sang bulk delete.

Entity-level remove có thể đi qua cơ chế soft-delete do Hibernate quản lý. Bulk JPQL delete và các API batch thường dùng bulk DML, không chạy lifecycle remove từng entity. Vì vậy, không giả định deleteAllInBatch() hoặc deleteAllByIdInBatch() sẽ tạo cùng hành vi với repository.delete(entity).

Nếu yêu cầu là đánh dấu deleted thay vì xóa vật lý:

- Dùng entity-level remove nếu mapping/version/provider xác nhận soft-delete được áp dụng cho đường remove đó.
- Hoặc viết bulk UPDATE rõ ràng để đặt indicator column theo chính sách.
- Kiểm tra SQL thực tế để xác nhận database nhận UPDATE hay DELETE.
- Kiểm thử cả dữ liệu đã xóa và các query filter sau thao tác.

Không dùng bulk delete trong một domain soft-delete nếu chưa xác minh semantics của Hibernate và phiên bản đang chạy.

## 17. Batch delete với @Modifying query tùy biến

Nếu cần xóa theo điều kiện và muốn biết số entity bị ảnh hưởng, có thể dùng @Modifying:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Modifying(
        clearAutomatically = true,
        flushAutomatically = true
    )
    @Query("""
           delete from Customer c
           where c.id in :ids
           """)
    int deleteBulkByIds(@Param("ids") Collection<Long> ids);
}
~~~

Đây là bulk JPQL DELETE. Kiểu trả về int là số entity bị ảnh hưởng theo kết quả executeUpdate của provider.

Method cần được gọi trong transaction. Có thể đặt @Transactional ở service hoặc method repository theo kiến trúc dự án. clearAutomatically yêu cầu Spring Data clear persistence context sau query; flushAutomatically flush các thay đổi đang chờ trước khi chạy query.

Nếu ids rỗng, nên xử lý trước khi gọi repository. Không dựa vào provider để xử lý IN rỗng theo cùng một cách trên mọi database.

Không viết query này nếu mục tiêu là chạy JPA cascade hoặc @PreRemove. Đây vẫn là bulk delete, dù được khai báo bằng @Query.

## 18. Quyết định dùng API nào trong từng tình huống

| Nhu cầu | API nên chọn | Lý do |
|---|---|---|
| Lấy reference để gán association | getReferenceById(id) | Không cần tải entity ngay |
| Đọc thông tin và xử lý không tồn tại | findById(id) | Trả Optional |
| Chỉ kiểm tra có ID | existsById(id) | Diễn đạt đúng mục đích |
| Xóa entity và cần JPA cascade/callback | delete(entity), deleteAll(entities) | Đi qua entity lifecycle |
| Bulk delete theo entity iterable | deleteAllInBatch(entities) | Bulk query |
| Bulk delete theo ID | deleteAllByIdInBatch(ids) | Không cần load entity |
| Bulk delete toàn bộ bảng entity | deleteAllInBatch() | Bulk operation toàn repository |
| Xóa theo predicate và cần affected count | @Modifying query trả int | Kiểm soát predicate và số lượng |
| Soft delete | Entity-level soft-delete hoặc bulk UPDATE indicator | Không mặc định dùng bulk DELETE |

Chọn method dựa trên yêu cầu nghiệp vụ, không chỉ dựa trên tên API cũ đang báo warning.

## 19. Kiểm thử getReferenceById() và findById()

Test dưới đây dùng @DataJpaTest để repository thực sự chạy với JPA provider.

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void referenceCanBeUsedToReadAnExistingCustomer() {
        Customer customer = new Customer("Ada");
        entityManager.persist(customer);
        entityManager.flush();

        Long id = customer.getId();
        entityManager.clear();

        Customer reference = repository.getReferenceById(id);

        assertThat(reference.getId()).isEqualTo(id);
        assertThat(reference.getName()).isEqualTo("Ada");
    }

    @Test
    void findByIdReturnsEmptyForMissingCustomer() {
        assertThat(repository.findById(-999L)).isEmpty();
    }
}
~~~

Test đầu clear persistence context trước khi gọi getReferenceById để tránh lấy lại object đã managed từ bước setup. Việc truy cập getName() xác nhận reference có thể được khởi tạo và đọc dữ liệu.

Test thứ hai xác nhận findById biểu diễn trường hợp không có entity bằng Optional.empty(). Không nên viết test phụ thuộc vào việc getReferenceById luôn ném exception ngay tại dòng gọi method vì thời điểm phát hiện ID không tồn tại phụ thuộc provider.

## 20. Kiểm thử batch delete

Test sau kiểm tra deleteAllByIdInBatch xóa hàng khỏi database:

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class CustomerBatchDeleteTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void deleteAllByIdInBatchRemovesRows() {
        Customer first = new Customer("Ada");
        Customer second = new Customer("Grace");

        entityManager.persist(first);
        entityManager.persist(second);
        entityManager.flush();

        Long firstId = first.getId();
        Long secondId = second.getId();

        repository.deleteAllByIdInBatch(
                List.of(firstId, secondId));

        entityManager.clear();

        assertThat(repository.findById(firstId)).isEmpty();
        assertThat(repository.findById(secondId)).isEmpty();
    }
}
~~~

clear() được gọi trước khi xác minh để tránh đọc trạng thái entity cũ trong persistence context. Test này xác nhận kết quả dữ liệu; nếu cần chứng minh số SQL statement, cascade hoặc lifecycle callback, hãy bổ sung SQL logging, datasource proxy hoặc entity listener test riêng.

Một test khác nên so sánh deleteAll(entities) với deleteAllInBatch(entities) khi domain có cascade hoặc @PreRemove, để bảo đảm nhóm hiểu rõ semantics mà ứng dụng đang phụ thuộc.

## 21. Checklist nâng cấp API trong codebase

Khi nâng Spring Data JPA, thực hiện theo thứ tự:

1. Kiểm tra phiên bản Spring Boot/Spring Data JPA thực tế từ dependency tree hoặc BOM.
2. Tìm tất cả lời gọi getOne(), getById() và deleteInBatch().
3. Với từng getOne/getById, xác định code cần reference hay cần xác nhận tồn tại.
4. Thay reference semantics bằng getReferenceById() nếu phiên bản hỗ trợ.
5. Thay logic đọc/validation bằng findById().orElseThrow() hoặc existsById().
6. Thay deleteInBatch(entities) bằng deleteAllInBatch(entities) chỉ khi chấp nhận bulk semantics.
7. Nếu chỉ có ID, cân nhắc deleteAllByIdInBatch(ids).
8. Nếu cần cascade/lifecycle, giữ đường delete(entity)/deleteAll(entities).
9. Kiểm tra transaction, flush, persistence context và cache sau bulk operation.
10. Kiểm tra soft-delete mapping, foreign key, trigger và batch size.
11. Chạy compile, test repository và test integration trên database mục tiêu.
12. Xem lại deprecation warnings để phát hiện API cũ còn sót.

Không sửa hàng loạt chỉ bằng replace text. Một lời gọi getById có thể đang dùng để kiểm tra tồn tại; một lời gọi deleteInBatch có thể đang vô tình bỏ qua callback mà hệ thống cần.

## 22. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| getReferenceById trả object nhưng đọc thuộc tính mới lỗi | Reference chưa được khởi tạo hoặc ID không tồn tại | Dùng findById nếu cần xác nhận tồn tại |
| EntityNotFoundException xuất hiện khi flush | Reference không tồn tại nhưng chỉ bị phát hiện muộn | Validate bằng findById hoặc xử lý lỗi FK |
| LazyInitializationException sau service | Proxy được truy cập ngoài persistence context | Đọc và tạo DTO trong transaction |
| Thay getById bằng getReferenceById nhưng API vẫn lỗi | Code cần Optional/not-found handling | Chuyển sang findById().orElseThrow() |
| getReferenceById không biên dịch | Spring Data JPA quá cũ | Kiểm tra version; dùng EntityManager.getReference hoặc nâng BOM |
| deleteAllInBatch không chạy @PreRemove | Bulk delete bỏ qua entity lifecycle | Dùng deleteAll(entities) nếu cần callback |
| Child không bị cascade delete | Bulk delete không áp dụng JPA cascade | Xóa qua entity lifecycle hoặc xử lý child riêng |
| Entity vẫn đọc được sau bulk delete | Persistence context còn trạng thái cũ | Flush trước, clear sau khi phù hợp |
| Bulk delete vi phạm foreign key | Database không cho xóa hàng cha khi còn child | Xác định thứ tự xóa hoặc FK action |
| Batch ID quá lớn gây lỗi bind | Vượt giới hạn parameter/câu lệnh của database | Chia chunk theo giới hạn hệ quản trị |
| Soft delete bị xóa vật lý | Bulk DELETE không đi qua entity remove mapping | Dùng soft-delete entity operation hoặc bulk UPDATE |
| Test không phát hiện stale entity | Test chưa clear persistence context | Clear rồi truy vấn lại từ repository |
| deleteAllByIdInBatch không trả số dòng | API trả void | Dùng custom @Modifying query trả int nếu thật sự cần count |

## 23. Tài liệu API chính thức

- JpaRepository API: https://docs.spring.io/spring-data/jpa/docs/current/api/org/springframework/data/jpa/repository/JpaRepository.html
- Deprecated API list: https://docs.spring.io/spring-data/jpa/docs/current/api/deprecated-list.html
- Spring Data JPA reference: https://docs.spring.io/spring-data/jpa/reference/
- Jakarta Persistence EntityManager: https://jakarta.ee/specifications/persistence/

API reference của JpaRepository mô tả rõ getOne/getById được thay bằng getReferenceById, deleteInBatch được thay bằng deleteAllInBatch(Iterable), và các giới hạn của bulk delete đối với first-level cache, cascade và lifecycle event. Hãy đối chiếu tài liệu theo đúng dòng version của dự án khi thực hiện nâng cấp.

## 24. Kết luận

getOne() và getById() là các API lấy reference; thay thế hiện hành là getReferenceById(). Reference không đồng nghĩa với việc entity đã được xác nhận tồn tại. Nếu cần đọc dữ liệu hoặc trả lỗi not-found rõ ràng, dùng findById() và xử lý Optional; nếu chỉ cần kiểm tra tồn tại, dùng existsById().

deleteInBatch() được thay bằng deleteAllInBatch(Iterable). Khi chỉ có ID, deleteAllByIdInBatch(ids) giúp tránh tải entity trước khi bulk delete. Các API batch bỏ qua JPA cascade và lifecycle callback, đồng thời có thể làm persistence context stale. Nếu domain cần callback, cascade hoặc soft delete theo entity, hãy dùng đường xóa entity phù hợp. Trước khi nâng cấp, kiểm tra version, ý định từng call site, transaction và test trên database thực tế.
