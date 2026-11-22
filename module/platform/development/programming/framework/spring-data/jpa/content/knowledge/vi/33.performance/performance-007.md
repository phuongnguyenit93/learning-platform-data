# Giới hạn kích thước PersistenceContext và bộ nhớ ứng dụng trong Spring Data JPA

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao persistence context tăng theo số entity được nạp; phân biệt first-level cache với second-level cache và heap của ứng dụng; dùng `flush`, `clear`, `detach` đúng cách; xử lý ghi dữ liệu theo batch có giới hạn; đọc dữ liệu lớn bằng DTO projection và keyset pagination; và đo bộ nhớ để xác định đúng nơi đang giữ object.

Các ví dụ dùng Java 17+, Spring Boot 3+, Spring Data JPA và Jakarta Persistence (`jakarta.persistence.*`). Một số cấu hình batching được ghi rõ là đặc thù Hibernate. Các đoạn code là ví dụ trong package minh họa; cần ghép với entity, repository và cấu hình database của ứng dụng.

## 1. Persistence context là gì?

Persistence context là vùng làm việc của một `EntityManager`. Nó theo dõi các entity đang ở trạng thái managed, duy trì identity map để cùng một identity trong context được đại diện bởi cùng một object, và giữ thông tin cần thiết để phát hiện thay đổi (dirty checking).

Khi một query trả về entity, entity thường được đưa vào persistence context. Nếu một job đọc hàng trăm nghìn entity trong cùng một `EntityManager`, các entity đã đọc có thể vẫn được giữ managed cho tới khi context được clear hoặc transaction/context kết thúc.

Điều này có nghĩa `Stream<T>` hoặc vòng lặp xử lý từng hàng không tự bảo đảm bộ nhớ hằng số. Dù không gom kết quả vào `List`, persistence context vẫn có thể giữ entity và snapshot của chúng.

JPA gọi persistence context là first-level cache. Nó gắn với một `EntityManager` và không phải cache dùng chung toàn ứng dụng.

## 2. Phân biệt ba nguồn dùng bộ nhớ

Khi điều tra heap tăng trong một tác vụ JPA, hãy tách ít nhất ba nguồn:

| Nguồn | Ví dụ object được giữ | Cách kiểm soát chính |
| --- | --- | --- |
| Persistence context (first-level cache) | Managed entity, trạng thái theo dõi thay đổi và association đã nạp | `clear()`, `detach()`, batch transaction, DTO/scalar query |
| Bộ nhớ do code ứng dụng giữ | `List` lớn, map, DTO đã collect, queue, closure hoặc biến static | Xử lý theo chunk, không giữ kết quả cũ, giới hạn queue và phạm vi tham chiếu |
| Second-level/query cache và cache ứng dụng | Entity/cache entry dùng chung, query result, Redis hoặc cache tự viết | Cấu hình eviction/TTL/size riêng; đo cache hit và dung lượng |

Giải phóng persistence context không tự giải phóng một `List` mà code vẫn đang giữ. Ngược lại, bỏ tham chiếu tới list không bảo đảm entity đã rời persistence context.

Second-level cache (nếu được bật) có phạm vi dùng chung qua `EntityManagerFactory`. `EntityManager.clear()` chỉ detach entity trong persistence context hiện tại; nó không xóa second-level cache. Jakarta Persistence cung cấp `EntityManagerFactory.getCache()` để thao tác cache chuẩn, còn cache của provider hoặc ứng dụng có API riêng.

## 3. flush, clear và detach khác nhau thế nào?

Ba thao tác này giải quyết các vấn đề khác nhau:

| API | Tác dụng | Không có nghĩa là |
| --- | --- | --- |
| `entityManager.flush()` | Đồng bộ thay đổi đang chờ từ persistence context xuống database trong transaction hiện tại | Commit transaction hoặc giải phóng entity khỏi bộ nhớ |
| `entityManager.clear()` | Detach tất cả entity đang managed trong persistence context | Xóa object khỏi mọi collection/biến của ứng dụng hoặc xóa second-level cache |
| `entityManager.detach(entity)` | Detach một entity cụ thể | Detach các entity liên quan hoặc xóa tham chiếu tới object |

### 3.1. Flush không phải commit

`flush()` yêu cầu JPA phát các lệnh SQL cần thiết để đồng bộ trạng thái managed với database. Transaction vẫn mở; các thay đổi chưa được commit và có thể bị rollback.

Flush có thể làm database kiểm tra constraint hoặc phát sinh lỗi SQL sớm hơn thời điểm commit. Nó cũng có thể làm các khóa database được giữ lâu hơn cho tới khi transaction kết thúc.

### 3.2. Clear detach toàn bộ entity đang managed

`clear()` làm các entity managed trong persistence context trở thành detached. Thay đổi chưa flush trên các entity đó sẽ không còn được dirty checking tự động đồng bộ. Vì vậy, với batch ghi, thứ tự thường dùng là:

```java
entityManager.flush();
entityManager.clear();
```

Flush trước để gửi các thay đổi của batch hiện tại xuống database; clear sau để persistence context không tiếp tục giữ các entity của batch đó.

Không gọi `clear()` trước `flush()` nếu các thay đổi pending cần được lưu. Sau `clear()`, object Java vẫn có thể tồn tại trong biến hoặc collection, nhưng nó detached và không còn được JPA tự động theo dõi.

### 3.3. Detach từng entity

Khi chỉ cần bỏ theo dõi một object, có thể gọi:

```java
entityManager.detach(customer);
```

Entity phải thuộc persistence context hiện tại. Các entity liên quan không mặc nhiên bị detach cùng nhau. Cách này hữu ích khi xử lý từng object độc lập, nhưng với batch lớn, `clear()` theo chu kỳ thường dễ kiểm soát hơn. Hãy cẩn thận nếu còn cần lazy-load association hoặc cập nhật entity sau khi detach.

## 4. Vì sao batch ghi cần flush và clear?

Ví dụ một vòng lặp tạo và persist 100.000 entity trong một transaction mà không clear:

```java
for (ImportRow row : rows) {
    entityManager.persist(new Customer(row.email(), row.name()));
}
```

Các entity mới vẫn managed trong persistence context. Hibernate cũng cần giữ trạng thái theo dõi để xử lý flush. Khi số lượng tăng, heap và thời gian dirty checking có thể tăng đáng kể.

Có thể chia thành các nhóm có kích thước cố định, ví dụ 500 entity mỗi batch:

```java
private static final int BATCH_SIZE = 500;

public void persistRows(Iterator<ImportRow> rows) {
    int count = 0;

    while (rows.hasNext()) {
        ImportRow row = rows.next();
        entityManager.persist(
            new Customer(row.email(), row.name())
        );
        count++;

        if (count % BATCH_SIZE == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

Đoạn code minh họa phần thân xử lý trong một service có transaction. `Iterator<ImportRow>` phải lấy dữ liệu theo luồng hoặc theo chunk; nếu `rows` được tạo từ một `List` chứa toàn bộ file thì chính list đầu vào vẫn chiếm bộ nhớ.

### 4.1. Ví dụ service ghi một chunk

Entity và record đầu vào tối giản:

```java
package com.example.learning.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@SequenceGenerator(name = "customer_seq_gen", sequenceName = "customer_seq", allocationSize = 50)
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "customer_seq_gen")
    private Long id;

    @Column(nullable = false)
    private String email;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String email, String name) {
        this.email = email;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getName() { return name; }
}
```

```java
package com.example.learning.customer;

public record ImportRow(String email, String name) {
}
```

Writer nhận một chunk đã được giới hạn kích thước:

```java
package com.example.learning.customer;

import java.util.List;
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerBatchWriter {
    private static final int BATCH_SIZE = 500;

    private final EntityManager entityManager;

    public CustomerBatchWriter(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void writeChunk(List<ImportRow> chunk) {
        if (chunk.size() > BATCH_SIZE) {
            throw new IllegalArgumentException("chunk exceeds batch size");
        }

        for (ImportRow row : chunk) {
            entityManager.persist(new Customer(row.email(), row.name()));
        }

        entityManager.flush();
        entityManager.clear();
    }
}
```

Caller chỉ gửi một `chunk` đã được giới hạn kích thước. `@Transactional` mặc định dùng propagation `REQUIRED`. Khi `writeChunk` được gọi qua Spring proxy từ bean khác và chưa có transaction nào đang hoạt động, Spring mở transaction cho lần gọi; nếu coordinator đã có transaction, method tham gia transaction hiện tại. Vì vậy, với propagation mặc định, chunk chỉ commit độc lập khi coordinator không có transaction đang hoạt động trong lúc gọi `writeChunk` (thông thường coordinator không được đánh dấu `@Transactional` và cũng không được gọi từ một caller đang có transaction). Sau `flush()`/`clear()`, transaction do writer mở sẽ commit khi method kết thúc bình thường và không bị đánh dấu rollback-only.

Trong trường hợp coordinator cần giữ một transaction bên ngoài nhưng mỗi chunk vẫn phải có transaction riêng, có thể đặt `@Transactional(propagation = Propagation.REQUIRES_NEW)` trên `writeChunk` (import `org.springframework.transaction.annotation.Propagation`). Spring suspend transaction bên ngoài, mở transaction mới cho chunk, rồi resume transaction ngoài sau khi chunk commit/rollback. Cách này có nghĩa chunk đã commit vẫn tồn tại nếu transaction ngoài rollback; transaction trong cũng không thấy các thay đổi chưa commit của transaction ngoài. Transaction ngoài có thể vẫn giữ connection trong lúc transaction trong cần connection khác, làm tăng áp lực lên connection pool và nguy cơ chờ connection. Chỉ dùng `REQUIRES_NEW` khi các trade-off về atomicity, visibility và tài nguyên connection phù hợp.

Để xử lý file lớn, một job coordinator có thể đọc 500 dòng, gọi `writeChunk(chunk)`, bỏ tham chiếu tới chunk rồi đọc nhóm kế tiếp. Như vậy cả input chunk, persistence context và transaction đều có giới hạn rõ ràng.

Sequence generator trong ví dụ yêu cầu database có sequence `customer_seq` hoặc schema migration tạo sequence đó. Với Hibernate, chiến lược IDENTITY thường hạn chế JDBC insert batching vì ID phải được lấy sau từng insert. Nếu dùng database không hỗ trợ sequence, chọn chiến lược ID phù hợp và kiểm tra khả năng batching của provider.

Nếu toàn bộ import phải atomic, chia transaction thành nhiều chunk sẽ thay đổi semantics: một chunk có thể commit trước khi chunk sau lỗi. Khi cần all-or-nothing, phải cân nhắc transaction lớn và giới hạn bộ nhớ, hoặc thiết kế staging table/đánh dấu trạng thái để hỗ trợ resume và bù trừ.

### 4.2. Flush/clear trong một transaction dài chưa giải phóng transaction

Gọi `flush()` và `clear()` định kỳ giúp giới hạn persistence context, nhưng transaction vẫn có thể kéo dài từ đầu tới cuối job. Database có thể vẫn giữ khóa, undo/version data và connection trong suốt thời gian đó.

Với job rất lớn, transaction theo từng chunk thường dễ vận hành hơn. Đặt `@Transactional` trên một bean writer riêng và gọi method đó từ coordinator bean khác để lời gọi đi qua proxy; với propagation mặc định `REQUIRED`, coordinator phải không có transaction nào đang hoạt động thì mỗi chunk mới được commit độc lập. Nếu coordinator hoặc caller đã có transaction, writer sẽ tham gia transaction đó; khi cần tách transaction, chỉ dùng `REQUIRES_NEW` sau khi cân nhắc các trade-off ở mục 4.1. Tránh self-invocation vì lời gọi nội bộ có thể không kích hoạt transactional proxy.

## 5. Cấu hình JDBC batching của Hibernate

`flush()` và `clear()` kiểm soát persistence context. JDBC batching là cơ chế riêng: Hibernate gom nhiều câu lệnh tương thích thành batch gửi qua JDBC để giảm round trip.

Ví dụ cấu hình Hibernate trong `application.properties`:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

`hibernate.jdbc.batch_size` là cấu hình đặc thù Hibernate. `order_inserts` và `order_updates` có thể giúp nhóm câu lệnh cùng loại để batching hiệu quả hơn, nhưng có thể thay đổi thứ tự SQL; kiểm tra constraint và thứ tự nghiệp vụ trước khi bật.

Batch JDBC và batch persistence context là hai việc khác nhau. Nếu đặt JDBC batch size 50 nhưng giữ 100.000 entity managed, persistence context vẫn có thể tăng rất lớn. Ngược lại, flush/clear mỗi 500 entity không bảo đảm driver thực sự gửi SQL theo batch nếu Hibernate/JDBC batching chưa được cấu hình.

Với Hibernate, chiến lược sinh ID `IDENTITY` thường hạn chế khả năng JDBC insert batching vì cần lấy ID sau từng insert. Nếu cần insert batch lớn, xem xét sequence-based ID khi database/provider hỗ trợ và kiểm tra cấu hình sequence allocation phù hợp.

Không mặc định các property Hibernate có hiệu lực trên provider JPA khác. Hãy xác nhận provider thực tế của ứng dụng.

## 6. Đừng giữ cả đầu vào và đầu ra trong bộ nhớ

Ngay cả khi persistence context được clear đúng cách, code ứng dụng vẫn có thể làm heap tăng nếu giữ collection lớn:

```java
List<Customer> all = repository.findAll();
List<CustomerDto> result = all.stream()
    .map(CustomerDto::from)
    .toList();
```

Trong ví dụ này, list entity và list DTO có thể cùng tồn tại trong heap. Với dữ liệu lớn, tránh `findAll()` rồi chuyển toàn bộ sang một list khác.

Các cách xử lý tốt hơn:

- Đọc một chunk, xử lý chunk, ghi kết quả, rồi bỏ tham chiếu trước khi đọc chunk kế tiếp.
- Dùng DTO projection để database chỉ trả các cột cần thiết.
- Ghi kết quả trực tiếp theo luồng vào file hoặc output sink có backpressure thay vì collect toàn bộ.
- Giới hạn queue giữa producer và consumer; queue không giới hạn chỉ chuyển vấn đề bộ nhớ sang nơi khác.
- Không giữ entity/DTO đã xử lý trong map hoặc cache nếu use case không cần.

## 7. Đọc dữ liệu lớn bằng projection và keyset pagination

Với tác vụ chỉ đọc, DTO projection thường phù hợp hơn entity vì kết quả DTO không trở thành managed entity trong persistence context.

DTO:

```java
package com.example.learning.customer;

public record CustomerExportRow(Long id, String email, String name) {
}
```

Repository dùng JPQL constructor expression:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("""
        select new com.example.learning.customer.CustomerExportRow(
            c.id, c.email, c.name
        )
        from Customer c
        where c.id > :afterId
        order by c.id asc
        """)
    List<CustomerExportRow> findNextExportBatch(
        @Param("afterId") Long afterId,
        Pageable pageable
    );
}
```

Caller yêu cầu mỗi lần tối đa 500 hàng bằng `PageRequest.of(0, 500)`, xử lý danh sách rồi cập nhật `afterId` bằng ID cuối cùng. Điều kiện `id > :afterId` cùng thứ tự `id` tạo keyset pagination, tránh chi phí offset tăng ở các trang sâu và giảm nguy cơ bỏ qua/trùng hàng do insert trước offset.

Keyset cần thứ tự ổn định và có tie-breaker duy nhất. Nếu sort theo `createdAt`, nên thêm `id` vào cuối thứ tự và dùng cả hai giá trị trong điều kiện tiếp theo. Dữ liệu được cập nhật trong lúc job chạy vẫn cần một chính sách nhất quán, ví dụ snapshot/version, cutoff thời gian hoặc trạng thái job.

### 7.1. Mỗi chunk đọc trong transaction riêng

Có thể đặt query đọc trong một service riêng:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerExportReader {
    private final CustomerRepository customers;

    public CustomerExportReader(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public List<CustomerExportRow> nextChunk(long afterId) {
        return customers.findNextExportBatch(
            afterId, PageRequest.of(0, 500)
        );
    }
}
```

Coordinator gọi `nextChunk` qua bean proxy, xử lý và bỏ list trước khi gọi chunk tiếp theo. Vì method trả DTO, persistence context không cần giữ các `Customer` managed chỉ để export. Nếu dùng entity thay DTO, transaction kết thúc sẽ detach entity nhưng list trả về vẫn giữ object trong heap cho tới khi caller bỏ tham chiếu.

Không dùng offset pagination với thứ tự không ổn định. Nếu bản ghi mới được thêm hoặc xóa trong khi job đang chạy, offset có thể làm một hàng bị lặp hoặc bỏ qua. Keyset pagination phù hợp khi có khóa sắp xếp tăng dần hoặc một cursor ổn định.

## 8. Stream<T> không tự giới hạn PersistenceContext

Spring Data JPA có thể trả `Stream<T>` từ repository, nhưng cần phân biệt:

- Java Stream cho phép tiêu thụ kết quả tuần tự.
- JDBC fetch size điều khiển gợi ý số hàng driver lấy mỗi lượt.
- Persistence context vẫn có thể giữ entity đã được hydrate.

Vì vậy, stream entity qua hàng trăm nghìn bản ghi vẫn có thể làm first-level cache tăng. Stream cần được tiêu thụ trong transaction còn mở và đóng bằng `try-with-resources`:

```java
public interface CustomerStreamRepository extends JpaRepository<Customer, Long> {
    Stream<Customer> findAllByOrderByIdAsc();
}
```

```java
@Transactional(readOnly = true)
public void exportEmails(Consumer<String> sink) {
    try (Stream<Customer> stream = repository.findAllByOrderByIdAsc()) {
        stream.map(Customer::getEmail).forEach(sink);
    }
}
```

Đoạn service cần import `java.util.stream.Stream` và `java.util.function.Consumer`. Nó minh họa quản lý transaction/tài nguyên; không chứng minh heap sẽ giữ ở mức cố định.

Fetch size là gợi ý cho JDBC driver, không phải giới hạn số entity trong persistence context. Hãy kiểm tra provider, driver và database. Với đọc dữ liệu lớn, DTO projection kết hợp keyset/page theo chunk thường dễ kiểm soát bộ nhớ hơn stream entity.

Nếu định gọi `EntityManager.clear()` trong lúc đang duyệt stream entity, cần kiểm thử kỹ với provider/driver cụ thể: clear detach mọi entity đang managed và có thể làm lazy loading hoặc logic xử lý còn lại không hoạt động như mong đợi. Không áp dụng mẫu này một cách máy móc.

## 9. Lazy association và N+1 cũng tiêu tốn bộ nhớ

Khi truy cập lazy association trên mỗi entity, ORM có thể phát sinh thêm query và tạo thêm entity/collection trong persistence context. Ví dụ đọc từng customer rồi truy cập orders có thể tạo N+1 query và làm context lớn hơn.

Nếu chỉ cần vài thuộc tính từ quan hệ, ưu tiên DTO query có join/select rõ ràng. Nếu cần entity graph, giới hạn số hàng trong chunk và kiểm tra số query. Batch fetching (`hibernate.default_batch_fetch_size` hoặc `@BatchSize` trong Hibernate) có thể giảm số round trip khi tải association, nhưng nó không đặt giới hạn kích thước persistence context.

## 10. Second-level cache không phải PersistenceContext

First-level cache là bắt buộc trong mô hình EntityManager và có phạm vi một persistence context. Second-level cache là tùy chọn, có phạm vi dùng chung qua `EntityManagerFactory` và do provider quản lý.

`entityManager.clear()` detach entity trong first-level cache hiện tại. Nó không xóa cache entry dùng chung. Jakarta Persistence cung cấp `entityManagerFactory.getCache().evict(...)` và `evictAll()`; thao tác này ảnh hưởng cache dùng chung và chỉ nên dùng khi có lý do rõ ràng.

Cache không thay thế việc kiểm soát heap của ứng dụng. Một cache có giới hạn size/TTL vẫn tiêu thụ bộ nhớ; cần theo dõi dung lượng và eviction theo cấu hình riêng.

## 11. Các lỗi thường gặp

- **Chỉ dùng `Stream<T>` rồi kết luận bộ nhớ đã được giới hạn.** Entity vẫn có thể được giữ trong persistence context.
- **Gọi `flush()` nhưng không `clear()`.** SQL được đồng bộ, nhưng entity vẫn managed và có thể tiếp tục chiếm heap.
- **Gọi `clear()` trước khi flush.** Thay đổi pending có thể bị mất khỏi dirty checking; flush trước nếu cần lưu.
- **Nghĩ `clear()` xóa mọi object khỏi heap.** List, map, DTO và biến ứng dụng vẫn giữ tham chiếu.
- **Dùng `saveAll()` với một collection khổng lồ.** Input và kết quả trả về có thể cùng giữ nhiều object; chia chunk có giới hạn.
- **Cấu hình JDBC batch nhưng không clear persistence context.** Batch JDBC không giới hạn số entity managed.
- **Clear trong lúc còn cần lazy loading.** Entity bị detach và association có thể không tải được.
- **Dùng một transaction cho job chạy hàng giờ.** Flush/clear không kết thúc transaction hoặc giải phóng mọi khóa.
- **Dùng offset pagination sâu hoặc sort không ổn định.** Ưu tiên keyset với thứ tự duy nhất khi phù hợp.
- **Nhầm batch fetching với giới hạn persistence context.** Batch fetch giảm round trip, không giới hạn số entity được giữ.
- **Xóa second-level cache để xử lý first-level cache.** Hai cache có phạm vi và cách quản lý khác nhau.
- **Giữ kết quả đã xử lý trong queue không giới hạn.** Dùng queue bounded và backpressure.

## 12. Đo và chẩn đoán bộ nhớ

Đừng chọn batch size chỉ theo cảm tính. Hãy đo trên dữ liệu gần production:

1. Ghi nhận heap trước, trong và sau từng batch; quan sát xu hướng sau GC.
2. Dùng Java Flight Recorder (JFR), heap dump hoặc Memory Analyzer để tìm loại object và đường tham chiếu đang giữ chúng.
3. Kiểm tra số entity managed, số query, lazy load, collection và kích thước persistence context nếu provider cung cấp statistics.
4. Quan sát GC pause, allocation rate, old-generation occupancy và thời gian xử lý mỗi batch.
5. Theo dõi connection pool, thời gian transaction và lock wait; tối ưu heap không được làm transaction giữ connection quá lâu.
6. Thay đổi một yếu tố mỗi lần: batch size, projection, fetch size hoặc transaction chunk; sau đó so sánh kết quả.

Với Hibernate, có thể bật statistics trong môi trường đo bằng cấu hình `hibernate.generate_statistics=true` và đọc `SessionFactory` statistics. Không bật log SQL/statistics quá chi tiết liên tục ở production nếu overhead hoặc lượng log quá lớn.

Batch size nhỏ làm tăng số lần flush/round trip nhưng giảm lượng entity đồng thời được giữ. Batch size lớn giảm overhead gọi database nhưng tăng heap và thời gian flush. Chọn giá trị dựa trên kích thước entity, association, driver, database và giới hạn heap.

## 13. Khi nào nên dùng Hibernate StatelessSession?

Hibernate cung cấp `StatelessSession` như một API riêng cho xử lý bulk ít cần chức năng persistence context. Nó không phải API chuẩn Jakarta Persistence và không có cùng first-level cache, dirty checking, cascade, lifecycle callback hoặc identity management như `Session` thông thường.

`StatelessSession` có thể phù hợp cho import/export chuyên biệt sau khi đã đánh giá các khác biệt về semantics. Không thay thế EntityManager bằng API này chỉ để giảm heap nếu nghiệp vụ phụ thuộc cascade, entity lifecycle hoặc association management.

## 14. Checklist trước khi triển khai job dữ liệu lớn

- [ ] Xác định heap tăng do persistence context, collection ứng dụng hay cache dùng chung.
- [ ] Chọn entity hay DTO projection theo nhu cầu xử lý.
- [ ] Đặt giới hạn kích thước input/output chunk.
- [ ] Với batch ghi, flush rồi clear sau mỗi nhóm có giới hạn.
- [ ] Bảo đảm các thay đổi cần lưu đã flush trước khi clear.
- [ ] Cấu hình JDBC batching riêng nếu dùng Hibernate và đo hiệu quả thực tế.
- [ ] Quyết định transaction theo toàn job hay theo chunk dựa trên yêu cầu atomicity/resume.
- [ ] Với đọc lớn, dùng keyset hoặc paging ổn định; tránh collect toàn bộ kết quả.
- [ ] Không giả định Stream hoặc fetch size tự giới hạn first-level cache.
- [ ] Kiểm tra lazy loading, N+1 và association được giữ trong context.
- [ ] Đặt giới hạn cho queue/cache và bỏ tham chiếu sau khi xử lý chunk.
- [ ] Đo heap, GC, transaction duration, connection pool và throughput dưới tải thực tế.

## Kết luận

Persistence context có thể tăng theo số entity được nạp, ngay cả khi code xử lý tuần tự. `flush()` đồng bộ thay đổi xuống database nhưng không giải phóng entity; `clear()` detach toàn bộ entity managed; `detach()` chỉ bỏ theo dõi một entity. Với ghi dữ liệu lớn, chia input thành chunk, flush rồi clear và cân nhắc transaction theo từng chunk. Với đọc dữ liệu lớn, DTO projection kết hợp keyset pagination thường kiểm soát bộ nhớ tốt hơn việc giữ entity hoặc collect toàn bộ kết quả. Cuối cùng, hãy phân biệt first-level cache, second-level cache và các collection do ứng dụng giữ, rồi đo heap/GC để tìm đúng nguồn tiêu thụ.