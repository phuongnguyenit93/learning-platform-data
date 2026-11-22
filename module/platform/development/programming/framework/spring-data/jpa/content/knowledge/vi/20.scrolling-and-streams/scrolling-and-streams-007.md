# Đọc kết quả bằng Stream<T> trong phạm vi giao dịch

## Mục tiêu

Sau bài này, bạn có thể khai báo repository method trả về `Stream<T>`; tiêu thụ luồng dữ liệu trong transaction đang mở; đóng tài nguyên bằng `try-with-resources`; phân biệt Java Stream với việc database thực sự fetch dữ liệu từng phần; kiểm soát fetch size, persistence context và lazy loading; đồng thời chọn `Stream`, `Page`, `Slice` hoặc xử lý theo lô cho đúng nhu cầu.

Các ví dụ dùng Java 17+, Spring Boot 3+, Spring Data JPA và Jakarta Persistence (`jakarta.persistence.*`). Các đoạn code thuộc package minh họa `com.example.learning.customer`; chúng cần chạy trong ứng dụng Spring Boot có `spring-boot-starter-data-jpa`, `DataSource` và JDBC driver được cấu hình.

## 1. Vì sao repository có thể trả về Stream<T>?

Thông thường, repository trả `List<T>` hoặc `Page<T>`. Với `List<T>`, toàn bộ kết quả thường được materialize thành collection trước khi ứng dụng xử lý. Nếu truy vấn trả về hàng trăm nghìn bản ghi, việc giữ toàn bộ danh sách trong heap có thể tốn nhiều bộ nhớ.

Spring Data JPA hỗ trợ kiểu trả về `Stream<T>` cho query method. Stream cho phép ứng dụng tiêu thụ kết quả tuần tự bằng các thao tác của Java Stream API, chẳng hạn `map`, `filter` và `forEach`.

Ví dụ khai báo:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Stream<Customer> findByActiveTrueOrderByIdAsc();
}
```

Method trên tìm các customer đang active, sắp xếp theo ID và trả về `Stream<Customer>`. Caller có thể xử lý từng phần tử thay vì yêu cầu repository trả một `List<Customer>`.

Tuy nhiên, `Stream<T>` không tự động có nghĩa database chắc chắn gửi dữ liệu từng hàng một. Spring Data, JPA provider, JDBC driver và database cùng quyết định cách kết quả được lấy. Stream là API tiêu thụ kết quả; khả năng fetch tăng dần cần được xác nhận ở tầng provider/driver.

## 2. Stream phải được tiêu thụ trong transaction

Kết quả stream của repository có thể giữ tài nguyên ở tầng persistence, chẳng hạn JDBC `ResultSet`, statement và connection. Những tài nguyên này cần còn hợp lệ trong suốt quá trình đọc.

Vì vậy, hãy đặt ranh giới transaction ở service method bao quanh cả lời gọi repository lẫn thao tác terminal trên stream. `@Transactional(readOnly = true)` là lựa chọn phù hợp cho use case chỉ đọc:

```java
package com.example.learning.customer;

import java.util.function.Consumer;
import java.util.stream.Stream;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerExportService {
    private final CustomerRepository customers;

    public CustomerExportService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public void exportActiveEmails(Consumer<String> emailWriter) {
        try (Stream<Customer> stream = customers.findByActiveTrueOrderByIdAsc()) {
            stream
                .map(Customer::getEmail)
                .forEach(emailWriter);
        }
    }
}
```

Trong ví dụ này:

- Service mở transaction trước khi gọi repository.
- Repository tạo stream trong transaction đó.
- `forEach` là terminal operation, nên toàn bộ kết quả được tiêu thụ khi transaction vẫn đang mở.
- `try-with-resources` đóng stream khi xử lý xong hoặc khi có exception.
- Method trả về sau khi stream đã được đóng; caller không nhận một stream còn phụ thuộc vào transaction.

Đặt transaction ở service giúp một use case có ranh giới rõ ràng. Các query method được khai báo trong repository không nên được giả định tự có transaction bao quanh toàn bộ quá trình caller tiêu thụ stream. Nếu không có transaction bên ngoài, stream có thể mất tài nguyên persistence trước khi caller đọc xong.

### 2.1. Không trả stream ra khỏi transactional method

Đây là cách dùng nguy hiểm:

```java
// Không nên: transaction kết thúc khi method trả về stream.
@Transactional(readOnly = true)
public Stream<Customer> findActiveCustomers() {
    return customers.findByActiveTrueOrderByIdAsc();
}
```

Khi method trả về, transaction do Spring quản lý có thể đã kết thúc. Caller mới bắt đầu đọc stream sau đó, trong khi cursor hoặc connection có thể đã đóng. Các thao tác lazy loading trên entity cũng có thể thất bại vì persistence context không còn hoạt động.

Hãy tiêu thụ stream hoàn toàn bên trong method có transaction. Nếu cần trả dữ liệu cho controller hoặc tầng khác, hãy chuyển từng phần tử thành DTO và ghi ra đích trong ranh giới xử lý phù hợp, hoặc dùng phân trang để trả từng trang độc lập.

### 2.2. Transactional proxy phải thực sự được gọi

Trong Spring, `@Transactional` thường được thực thi qua proxy. Một lời gọi public method từ bean khác sẽ đi qua proxy và mở transaction theo cấu hình.

Nếu một method trong cùng object gọi trực tiếp method khác có `@Transactional` (self-invocation), lời gọi nội bộ thường không đi qua proxy; annotation ở method được gọi có thể không tạo transaction mới như mong đợi. Hãy đặt ranh giới transaction ở public service method được gọi từ bên ngoài bean hoặc tổ chức service để lời gọi đi qua Spring proxy.

`readOnly = true` mô tả ý định chỉ đọc và có thể giúp transaction manager/provider tối ưu hoạt động. Nó không phải cơ chế bảo mật tuyệt đối cấm mọi lệnh ghi ở database.

## 3. Luôn đóng Stream bằng try-with-resources

Java `Stream<T>` kế thừa `BaseStream`, có `close()` và hỗ trợ `try-with-resources`. Khi stream đến từ repository, hãy đóng nó tường minh:

```java
try (Stream<Customer> stream = customers.findByActiveTrueOrderByIdAsc()) {
    stream.forEach(customer -> process(customer));
}
```

Không chỉ đóng khi xử lý thành công. `try-with-resources` vẫn gọi `close()` nếu terminal operation ném exception, giúp giải phóng tài nguyên được gắn với stream.

Không nên chỉ gọi terminal operation rồi bỏ stream mà không đóng. Một số stream thuần Java không giữ tài nguyên ngoài bộ nhớ, nhưng stream từ repository có thể giữ cursor, result set hoặc connection. Quy tắc an toàn là luôn dùng `try-with-resources`.

Stream chỉ được tiêu thụ một lần. Sau `forEach`, `collect`, `count` hoặc terminal operation khác, không dùng lại cùng stream. Nếu cần truy vấn lại, gọi repository để tạo stream mới trong transaction phù hợp.

## 4. Dùng @Query để định nghĩa truy vấn trả Stream

Stream không chỉ dùng với derived query. Repository có thể khai báo JPQL bằng `@Query` và trả `Stream<T>`:

```java
package com.example.learning.customer;

import java.util.stream.Stream;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("""
        select c
        from Customer c
        where c.active = true
        order by c.id asc
        """)
    Stream<Customer> streamActiveCustomers();
}
```

JPQL dùng entity `Customer` và property `active`, `id`; nó không dùng tên bảng hoặc tên cột SQL. Việc tiêu thụ và đóng stream vẫn phải nằm trong transaction như ví dụ service ở phần trước.

Nếu chỉ cần một vài trường, có thể trả một projection/DTO thay vì entity:

```java
package com.example.learning.customer;

public record CustomerEmailRow(Long id, String email) {
}
```

```java
@Query("""
    select new com.example.learning.customer.CustomerEmailRow(c.id, c.email)
    from Customer c
    where c.active = true
    order by c.id asc
    """)
Stream<CustomerEmailRow> streamActiveEmailRows();
```

DTO projection giúp giới hạn dữ liệu mà query cần trả về và không đưa entity managed ra ngoài use case. Đây thường là lựa chọn tốt cho export hoặc xử lý chỉ đọc khi không cần thay đổi entity.

## 5. Stream không đồng nghĩa với fetch từng hàng từ database

Đây là điểm quan trọng nhất khi tối ưu dữ liệu lớn. Java Stream API cho phép xử lý tuần tự, nhưng provider có thể đã tải nhiều hoặc toàn bộ kết quả từ database trước khi stream tiêu thụ.

Khả năng fetch tăng dần phụ thuộc vào:

- JPA provider và cách provider triển khai query result stream.
- JDBC driver và hỗ trợ cursor/fetch size.
- Database, transaction mode và cấu hình connection.
- Query có join, sort, group, fetch collection hoặc kiểu kết quả nào.
- Cấu hình fetch size được truyền tới statement.

Do đó, đừng kết luận ứng dụng dùng ít bộ nhớ chỉ vì method trả `Stream<T>`. Hãy đo heap, số lượng hàng được fetch, số round trip và hành vi driver trên database mục tiêu.

### 5.1. Fetch size

Fetch size là gợi ý cho JDBC driver về số hàng nên lấy mỗi lần đọc từ database. Nó có thể giúp provider/driver sử dụng cursor hoặc fetch theo lô, nhưng ý nghĩa chính xác phụ thuộc driver và database.

Với Hibernate, có thể thử hint fetch size như sau:

```java
import java.util.stream.Stream;
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.QueryHints;

@QueryHints(
    value = @QueryHint(name = "org.hibernate.fetchSize", value = "200")
)
Stream<Customer> findByActiveTrueOrderByIdAsc();
```

`org.hibernate.fetchSize` là hint đặc thù Hibernate, không phải một cam kết portable của Jakarta Persistence. Nếu ứng dụng dùng provider khác, hãy kiểm tra tài liệu provider đó. Ngay cả khi đặt fetch size, driver vẫn có thể bỏ qua hoặc diễn giải khác; cần xác minh bằng integration test và quan sát thực tế.

Không có một fetch size tối ưu cho mọi hệ thống. Giá trị quá nhỏ có thể tăng số lần round trip; giá trị quá lớn có thể tăng bộ nhớ đệm. Chọn dựa trên kích thước hàng, độ trễ mạng, driver và giới hạn bộ nhớ.

### 5.2. SQL sort và kế hoạch truy vấn

Stream không làm một truy vấn vốn tốn kém trở nên rẻ hơn. Nếu query phải sắp xếp hàng triệu bản ghi, database vẫn cần thực hiện sort hoặc dùng index phù hợp trước khi trả kết quả.

Ví dụ truy vấn có `ORDER BY id` có thể tận dụng index của khóa chính, nhưng điều đó phụ thuộc schema và execution plan. Hãy kiểm tra index, điều kiện lọc, số hàng đọc và kế hoạch truy vấn thay vì chỉ tối ưu phía Java.

## 6. Persistence context vẫn có thể tăng bộ nhớ

Khi stream trả về entity, mỗi entity được nạp thường trở thành managed entity trong persistence context. Dù ứng dụng không tạo `List` chứa tất cả kết quả, Hibernate/JPA persistence context vẫn có thể giữ tham chiếu tới entity đã nạp để phục vụ identity map và dirty checking.

Vì vậy, stream entity qua một tập rất lớn có thể vẫn làm heap tăng theo số entity đã đọc. Cần phân biệt hai vấn đề:

- **JDBC fetch:** số hàng driver giữ trong buffer/cursor tại một thời điểm.
- **Persistence context:** số entity đang được JPA quản lý trong session/entity manager.

Giảm fetch size không tự động xóa entity khỏi persistence context. Ngược lại, `EntityManager.clear()` giải phóng trạng thái managed trong persistence context nhưng không thay thế cấu hình fetch ở JDBC.

Nếu xử lý chỉ đọc và không cần entity managed, hãy cân nhắc DTO/scalar projection để giảm việc hydrate và giữ entity. Nếu bắt buộc xử lý entity với số lượng rất lớn, có thể chia thành các batch và clear persistence context theo chiến lược đã kiểm thử. Khi clear, mọi entity đang managed sẽ bị detach; hãy đọc xong dữ liệu và quan hệ cần thiết trước khi detach, đồng thời kiểm tra hành vi với provider đang dùng.

Không gọi `clear()` tùy tiện giữa lúc còn cần lazy-load quan hệ hoặc cập nhật entity. Sau khi detach, thay đổi trên object không còn được dirty checking tự động ghi xuống database.

## 7. Lazy loading, N+1 và quan hệ

Stream entity trong transaction cho phép truy cập lazy association khi persistence context còn mở, nhưng điều đó không có nghĩa truy vấn quan hệ sẽ hiệu quả.

Ví dụ:

```java
try (Stream<Customer> stream = customers.findByActiveTrueOrderByIdAsc()) {
    stream.forEach(customer -> {
        String city = customer.getAddress().getCity();
        process(customer.getEmail(), city);
    });
}
```

Nếu `address` là lazy association, việc gọi `getAddress()` có thể phát sinh một truy vấn bổ sung cho mỗi customer. Đây là mẫu N+1: một truy vấn lấy danh sách customer, sau đó nhiều truy vấn nhỏ lấy association.

Cách xử lý:

- Nếu chỉ cần vài trường, dùng DTO projection và select các trường đó trong một query.
- Nếu cần quan hệ, cân nhắc batch fetching hoặc một truy vấn có join phù hợp.
- Kiểm tra số câu SQL thực tế và tránh gọi getter lazy trong vòng lặp mà không hiểu chi phí.
- Không đưa entity ra ngoài transaction rồi kỳ vọng lazy association vẫn tải được.

Cần thận trọng với collection fetch join trên một truy vấn stream. Join một-nhiều có thể nhân số hàng SQL cho mỗi entity cha, tạo duplicate hoặc làm provider phải xử lý/tập hợp kết quả phức tạp. Hãy kiểm tra SQL, tính duy nhất của root entity và giới hạn của provider; projection hoặc truy vấn theo batch thường dễ kiểm soát hơn.

## 8. Xử lý lỗi và thời gian giữ connection

Trong lúc tiêu thụ stream, exception có thể đến từ callback, mapping, JDBC hoặc database. `try-with-resources` đảm bảo gọi `close()` khi thoát block, nhưng transaction vẫn cần kết thúc đúng cách để rollback/commit theo quy tắc Spring.

Stream dài giữ transaction và có thể giữ connection trong thời gian dài. Điều này làm giảm số connection còn lại cho request khác, đặc biệt khi callback ghi file chậm hoặc gọi dịch vụ ngoài.

Tránh thực hiện HTTP call hoặc thao tác mạng chậm cho từng hàng trong khi giữ cursor database. Nếu cần export lớn, cân nhắc đọc theo batch, ghi file theo chunk, hoặc tách bước đọc và bước gửi dữ liệu. Theo dõi connection pool và thời gian transaction khi chạy tác vụ.

Không chuyển stream sang `CompletableFuture`, thread khác hoặc gọi `.parallel()` để xử lý đồng thời. `EntityManager`/persistence context không thread-safe; JDBC result set cũng không phải nguồn dữ liệu để nhiều thread tùy ý đọc. Hãy xử lý tuần tự trong transaction, hoặc chia dữ liệu thành các đơn vị độc lập có transaction riêng.

## 9. Integration test cho Stream repository

Ví dụ entity tối giản:

```java
package com.example.learning.customer;

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

    @Column(nullable = false)
    private String email;

    @Column(nullable = false)
    private boolean active;

    protected Customer() {
    }

    public Customer(String email, boolean active) {
        this.email = email;
        this.active = active;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public boolean isActive() { return active; }
}
```

Repository:

```java
package com.example.learning.customer;

import java.util.stream.Stream;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Stream<Customer> findByActiveTrueOrderByIdAsc();
}
```

Integration test:

```java
package com.example.learning.customer;

import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class CustomerRepositoryStreamTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void consumesActiveCustomersInsideTestTransaction() {
        customers.saveAll(List.of(
            new Customer("ada@example.test", true),
            new Customer("grace@example.test", false),
            new Customer("linus@example.test", true)
        ));
        customers.flush();

        try (Stream<Customer> stream = customers.findByActiveTrueOrderByIdAsc()) {
            assertThat(stream.map(Customer::getEmail).toList())
                .containsExactly("ada@example.test", "linus@example.test");
        }
    }
}
```

`@DataJpaTest` thường chạy mỗi test trong một transaction được rollback khi test kết thúc. Vì stream được tiêu thụ và đóng bên trong method test, nó nằm trong transaction test đang mở. `flush()` buộc các bản ghi mới được gửi xuống database trước khi truy vấn.

Test này xác nhận repository trả đúng dữ liệu và cách tiêu thụ/đóng stream. Nó không chứng minh driver thực sự fetch theo cursor hoặc ứng dụng giữ bộ nhớ hằng số. Muốn kiểm tra fetch tăng dần, cần integration test trên database/driver mục tiêu và đo hành vi thực tế.

## 10. Khi nào nên dùng Stream, Page, Slice hoặc batch?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Cần toàn bộ kết quả nhỏ và dùng ngay | `List<T>` |
| UI cần số trang và tổng số bản ghi | `Page<T>` |
| UI chỉ cần biết còn trang tiếp theo | `Slice<T>` |
| Xử lý tuần tự tập kết quả lớn trong một transaction | `Stream<T>` nếu provider/driver hỗ trợ và đã kiểm chứng |
| Công việc dài, cần transaction ngắn và phục hồi theo lô | Phân trang hoặc xử lý batch |
| Chỉ cần vài cột để export/report | DTO hoặc projection, có thể kết hợp `Stream` |

`Page` và `Slice` chia kết quả thành các lần gọi độc lập. Chúng thường dễ kiểm soát thời gian transaction và connection hơn khi mỗi batch có thể hoàn tất rồi mới lấy batch tiếp theo.

Với dữ liệu rất lớn, offset pagination ở các trang sâu có thể tốn kém. Nếu có khóa sắp xếp ổn định, có thể dùng keyset pagination hoặc cơ chế scrolling/batch phù hợp phiên bản Spring Data. Khi chọn cách này, cần xác định thứ tự duy nhất và xử lý dữ liệu thay đổi trong lúc job chạy.

Stream phù hợp khi tác vụ cần đi qua một tập kết quả tuần tự trong một ranh giới transaction có thể kiểm soát. Nó không phải lựa chọn mặc định cho mọi tác vụ lớn; connection bị giữ lâu và persistence context vẫn có thể tiêu tốn bộ nhớ.

## 11. Những lỗi thường gặp

- **Không có transaction bao quanh quá trình đọc.** Đặt `@Transactional(readOnly = true)` ở service method tiêu thụ stream.
- **Trả `Stream<T>` khỏi transactional method.** Stream có thể được đọc sau khi transaction/connection đã đóng; hãy tiêu thụ bên trong method.
- **Không đóng stream.** Dùng `try-with-resources` để giải phóng result set, statement và tài nguyên liên quan.
- **Nghĩ Stream luôn fetch từng hàng.** Provider/driver có thể buffer nhiều hoặc toàn bộ kết quả; xác minh fetch size và hành vi thực tế.
- **Chỉ giảm fetch size nhưng không quản lý persistence context.** Entity đã nạp vẫn có thể được giữ managed; cân nhắc DTO hoặc batch/clear có kiểm soát.
- **Gọi lazy association trong vòng lặp mà không đo SQL.** Có thể tạo N+1 query.
- **Gọi dịch vụ ngoài cho từng hàng trong transaction dài.** Connection bị giữ lâu; chuyển sang batch hoặc tách bước xử lý.
- **Dùng parallel stream với EntityManager/JDBC cursor.** Persistence context và nguồn JDBC không an toàn cho truy cập đồng thời tùy ý.
- **Thu thập stream vào `List` rất lớn.** `toList()`/`collect()` có thể loại bỏ lợi ích giảm bộ nhớ của xử lý tuần tự.
- **Dùng fetch size của Hibernate trên provider khác.** Hint là đặc thù provider; xác minh tên và hiệu lực với stack thực tế.
- **Cho rằng `readOnly = true` cấm ghi tuyệt đối.** Đây là gợi ý tối ưu giao dịch, không thay thế constraint và quyền database.

## 12. Checklist trước khi triển khai

- [ ] Repository method trả `Stream<T>` hoặc DTO projection phù hợp.
- [ ] Một service method có transaction bao quanh cả lời gọi repository và terminal operation.
- [ ] Stream được tiêu thụ trước khi transactional method kết thúc.
- [ ] Stream luôn được đóng bằng `try-with-resources`.
- [ ] Không trả stream qua controller, thread khác hoặc tác vụ async.
- [ ] Đã xác minh provider và JDBC driver có fetch tăng dần như mong muốn.
- [ ] Fetch size được kiểm thử trên database mục tiêu nếu cần.
- [ ] Đã đánh giá mức tăng persistence context/heap khi đọc nhiều entity.
- [ ] Đã kiểm tra N+1, lazy loading và collection fetch join.
- [ ] Thời gian giữ transaction/connection phù hợp với connection pool.
- [ ] Đã so sánh với `Page`, `Slice` hoặc batch nếu job dài.
- [ ] Integration test xác nhận dữ liệu, transaction và việc đóng stream.

## Kết luận

`Stream<T>` trong Spring Data JPA cho phép xử lý kết quả tuần tự, nhưng stream cần được tiêu thụ và đóng trong transaction đang mở. Hãy đặt transaction ở service method, dùng `try-with-resources`, xác minh fetch size/provider/driver, và theo dõi cả JDBC buffer lẫn persistence context. Khi chỉ cần một phần dữ liệu, DTO projection thường giúp giảm việc quản lý entity; khi cần transaction ngắn hoặc xử lý có thể phục hồi theo lô, `Page`, `Slice` hoặc batch thường dễ vận hành hơn.