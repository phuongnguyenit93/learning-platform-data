# Hợp đồng repository và cấu hình giao dịch do từng store cung cấp

## Mục tiêu và phạm vi

Trong chương **Ranh giới giao dịch** của Spring Data Commons, câu hỏi đầu tiên cần trả lời là: khi gọi một repository, những bảo đảm nào đến từ hợp đồng chung và những bảo đảm nào phụ thuộc kho dữ liệu?

Một lời gọi `save` thành công chưa đủ để kết luận rằng nhiều thay đổi đã được commit cùng nhau. Một interface kế thừa `CrudRepository` cũng chưa cho biết ứng dụng đang dùng transaction manager nào.

Sau bài học này, bạn có thể:

- Phân biệt abstraction repository của Commons với cơ chế giao dịch của module store.
- Xác định phạm vi nguyên tử của một use case có nhiều thao tác dữ liệu.
- Đặt ranh giới giao dịch ở lớp phù hợp và chọn đúng transaction manager.
- Giải thích giới hạn của các thuộc tính như `readOnly`, isolation và propagation.
- Nhận diện các suy luận sai khi chuyển giữa JPA, JDBC, MongoDB và R2DBC.

Bài tập trung vào hợp đồng và cấu hình. Ví dụ JPA chỉ minh họa một store cụ thể; không dùng hành vi riêng của JPA làm quy tắc cho tất cả Spring Data.

## 1. Bốn lớp trách nhiệm cần phân biệt

Một ứng dụng Spring Data thường có các lớp trách nhiệm sau:

| Lớp | Cung cấp điều gì? | Không thể tự suy ra điều gì? |
|---|---|---|
| Spring Data Commons | Interface repository, metadata và các abstraction dùng chung | Mọi store đều có cùng mô hình giao dịch |
| Module store | Implementation repository, mapping và tích hợp truy cập dữ liệu | Mọi thao tác của ứng dụng cùng tham gia một transaction |
| Spring transaction infrastructure | Cơ chế mở, tham gia, commit, rollback và áp dụng thuộc tính giao dịch | Backend hỗ trợ mọi isolation hoặc propagation được khai báo |
| Driver và hệ thống lưu trữ | Khả năng thực thi, khóa, mức nhất quán và atomicity thực tế | Các tài nguyên ngoài backend cùng được commit |

Ví dụ, `CrudRepository<T, ID>` định nghĩa các phương thức CRUD. Khi ứng dụng dùng Spring Data JPA, implementation cụ thể làm việc thông qua JPA. Khi dùng một module khác, cách mapping và thực thi đến từ module đó.

Do đó, cần đọc hợp đồng theo hai chiều:

1. **Hợp đồng API:** phương thức nhận gì, trả gì, biểu diễn không tìm thấy hoặc lỗi như thế nào?
2. **Hợp đồng thực thi:** phương thức chạy trong giao dịch nào, trên tài nguyên nào, với những khả năng mà store thực sự hỗ trợ?

Cùng tên `save` không đồng nghĩa cùng chiến lược ghi, cùng thời điểm gửi lệnh hay cùng phạm vi giao dịch.

## 2. Hợp đồng CRUD không thay thế hợp đồng giao dịch

Xét interface chung:

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Interface này mô tả cách ứng dụng gọi repository. Nó chưa mô tả đầy đủ cách cấu hình persistence, transaction manager, isolation hoặc kết nối tới backend.

Một số phân biệt quan trọng:

| Phương thức hoặc hành vi | Ý nghĩa ở mức sử dụng repository | Kết luận cần tránh |
|---|---|---|
| `save(entity)` | Lưu entity và trả về instance kết quả | Giá trị trả về chứng minh transaction ngoài đã commit |
| `saveAll(entities)` | Lưu các entity được truyền vào theo hợp đồng repository | Mọi store đều thực hiện cả tập trong một transaction duy nhất |
| `findById(id)` | Tìm entity theo ID, có thể không có kết quả | Entity sẽ không bị thay đổi bởi giao dịch khác sau lần đọc |
| `deleteById(id)` | Yêu cầu xóa theo hợp đồng implementation | Mọi thay đổi ngoài database được rollback theo |
| Ném lỗi truy cập dữ liệu | Báo thao tác không hoàn tất như mong muốn | Tất cả tài nguyên mà use case đã chạm tới đều được hoàn tác |

Hãy dùng instance do `save` trả về nếu còn cần thao tác với kết quả lưu. Implementation có thể trả về instance khác hoặc kết quả đã chứa giá trị được sinh khi lưu.

Ví dụ:

```java
Customer saved = customers.save(draft);
return saved.getId();
```

Ngay cả trong ví dụ này, việc có ID vẫn không thay thế việc xác nhận giao dịch đã commit. Một transaction bao ngoài còn có thể bị rollback sau khi đoạn mã trên chạy.

### Không đồng nhất save, flush và commit

Với JPA, một thay đổi có thể được theo dõi trong persistence context trước khi câu lệnh tương ứng được gửi tới database. Flush đồng bộ thay đổi với database trong giao dịch hiện tại; commit là bước kết thúc giao dịch thành công.

Vì vậy:

- `save` không có nghĩa là giao dịch ngoài đã kết thúc.
- Flush không đồng nghĩa commit.
- Một lỗi ràng buộc có thể xuất hiện ở thời điểm flush hoặc commit.
- Flush thành công vẫn có thể bị rollback bởi lỗi xảy ra sau đó.

Những khái niệm như persistence context và flush ở đây là ngữ cảnh JPA. Không áp đặt chúng lên một store không có mô hình đó.

## 3. Từ lời gọi repository đến ranh giới nghiệp vụ

Giả sử một chức năng thực hiện:

1. Cập nhật thông tin khách hàng.
2. Ghi lịch sử thay đổi vào cùng database.
3. Trả kết quả cho người gọi.

Nếu từng thao tác chạy trong giao dịch riêng, hệ thống có thể rơi vào trạng thái đã sửa khách hàng nhưng chưa ghi lịch sử.

```text
Không có giao dịch bao quanh toàn bộ use case:

save(customer)    -> giao dịch A commit
save(changeLog)   -> giao dịch B lỗi

Kết quả có thể xảy ra:
customer đã đổi, changeLog chưa được ghi
```

Một ranh giới giao dịch bao ngoài, khi hai repository dùng chung tài nguyên và manager phù hợp, cho phép hai thay đổi cùng thành công hoặc cùng rollback.

```text
Service bắt đầu giao dịch A
    |
    +-- đọc customer
    +-- cập nhật customer
    +-- ghi changeLog
    |
Service kết thúc
    +-- thành công: commit A
    +-- lỗi cần rollback: rollback A
```

Ranh giới đúng thường tương ứng một invariant nghiệp vụ cần giữ. Chẳng hạn: “mỗi lần đổi tên khách hàng phải có bản ghi lịch sử trong cùng database”.

Không nên mở rộng transaction chỉ vì một controller gọi nhiều phương thức. Những thao tác độc lập có thể không cần chung một ranh giới, còn một use case gọi nhiều repository có thể cần một transaction ở service.

## 4. Ranh giới ở service và giao dịch của từng phương thức repository

Cần phân biệt hai trường hợp:

### 4.1. Chỉ có giao dịch ở phương thức repository

Một store có thể cấu hình các phương thức repository để tự mở hoặc tham gia giao dịch. Khi không có giao dịch bên ngoài, mỗi lời gọi có thể là một ranh giới riêng.

Ví dụ, với cấu hình JPA repository thông thường, các phương thức CRUD được kế thừa có cấu hình giao dịch từ implementation repository cơ sở; các thao tác đọc thường có thuộc tính `readOnly`, còn các thao tác ghi có cấu hình giao dịch ghi.

Đây là hành vi của Spring Data JPA và cấu hình của nó, không phải một cam kết giao dịch áp dụng cho mọi implementation của `CrudRepository`.

### 4.2. Có giao dịch ở service bao ngoài

Khi service đã mở một giao dịch và các repository tham gia giao dịch đó, các thao tác thuộc cùng ranh giới bên ngoài.

Trong cấu hình propagation `REQUIRED` thông thường:

- Nếu chưa có giao dịch phù hợp, bắt đầu một giao dịch.
- Nếu đã có giao dịch phù hợp, tham gia giao dịch hiện tại.
- Phương thức repository trả về chưa làm giao dịch của service kết thúc.

Những thuộc tính của ranh giới đã được mở bên ngoài chi phối giao dịch đang diễn ra. Không mặc định một phương thức đọc có `readOnly = true` sẽ biến giao dịch ghi đang bao ngoài thành giao dịch chỉ đọc.

Nếu muốn từ chối các thuộc tính không tương thích khi tham gia giao dịch sẵn có, cần xem khả năng kiểm tra và cấu hình của transaction manager đang dùng.

## 5. Ví dụ JPA: cập nhật và ghi lịch sử trong cùng giao dịch

Giả định ứng dụng đã có:

- Entity JPA `Customer` với ID kiểu `Long` và phương thức `rename(String)`.
- Entity JPA `CustomerChange` với constructor nhận ID khách hàng và tên mới.
- Hai entity được quản lý bởi cùng `EntityManagerFactory`.
- Một transaction manager tên `customerTx` quản lý persistence unit đó.
- Mapping và schema tương ứng đã được cấu hình.

Các đoạn mã sau tập trung vào hợp đồng repository và ranh giới service; chúng không phải toàn bộ cấu hình của một ứng dụng chạy độc lập.

### 5.1. Hai repository cùng một store

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerChangeRepository
        extends JpaRepository<CustomerChange, Long> {
}
```

Dùng `JpaRepository` ở đây để làm rõ store của ví dụ. Không cần chuyển mọi repository Commons trong ứng dụng thành JPA.

### 5.2. Service xác định phạm vi nguyên tử

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository customers;
    private final CustomerChangeRepository changes;

    public CustomerService(
            CustomerRepository customers,
            CustomerChangeRepository changes) {
        this.customers = customers;
        this.changes = changes;
    }

    @Transactional(transactionManager = "customerTx")
    public Long rename(Long customerId, String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer name must not be blank");
        }

        Customer customer = customers.findById(customerId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Customer not found: " + customerId));

        customer.rename(newName);

        Customer saved = customers.save(customer);

        changes.save(new CustomerChange(
                saved.getId(),
                newName));

        return saved.getId();
    }
}
```

Khi lời gọi đi qua transactional proxy phù hợp:

1. `customerTx` mở hoặc tham gia giao dịch.
2. Hai repository làm việc với persistence unit tương ứng.
3. Nếu ghi lịch sử phát sinh lỗi khiến transaction phải rollback, thay đổi khách hàng trong cùng giao dịch cũng rollback.
4. Nếu phương thức kết thúc bình thường và không có trạng thái rollback-only, transaction có thể được commit ở ranh giới thích hợp.

Nếu service đang tham gia một giao dịch ngoài, thời điểm commit nằm ở ranh giới ngoài đó.

Trong JPA, entity được quản lý có thể được đồng bộ bằng dirty checking mà không cần gọi `save` lần nữa. Ví dụ vẫn gọi `save` để minh họa hợp đồng repository và việc sử dụng giá trị trả về. Không suy rằng các store khác có dirty checking giống JPA.

Ví dụ cũng không đảm bảo chống mọi xung đột cập nhật đồng thời. Nếu nghiệp vụ cần phát hiện lost update, cần cơ chế như optimistic locking với `@Version` ở store hỗ trợ hoặc chiến lược khóa phù hợp.

## 6. Cấu hình phải nối repository với đúng tài nguyên

Tên transaction manager chỉ có ý nghĩa khi bean đó thực sự quản lý tài nguyên mà repository sử dụng.

Ví dụ cấu hình tường minh cho một nhóm JPA repository:

```java
import jakarta.persistence.EntityManagerFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
@EnableJpaRepositories(
        basePackages = "example.customer.persistence",
        entityManagerFactoryRef = "customerEmf",
        transactionManagerRef = "customerTx")
public class CustomerPersistenceConfig {

    @Bean(name = "customerTx")
    public PlatformTransactionManager customerTransactionManager(
            @Qualifier("customerEmf")
            EntityManagerFactory entityManagerFactory) {

        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Ví dụ giả định bean `customerEmf` đã được khai báo, các entity được scan đúng và hạ tầng JPA đã sẵn sàng.

Trong dự án Spring Boot, một phần hạ tầng có thể được auto-configuration cung cấp. Không sao chép thêm cấu hình trùng lặp nếu ứng dụng đã có cấu hình tương đương.

Cần kiểm tra chuỗi liên kết:

```text
CustomerService
    @Transactional("customerTx")
            |
            v
customerTx
            |
            v
customerEmf
            |
            v
DataSource của nhóm customer
            ^
            |
CustomerRepository và CustomerChangeRepository
```

Các tên bean trên chỉ là ví dụ. Trong hệ thống có nhiều database, việc khai báo đúng tên nhưng nối nhầm `EntityManagerFactory` vẫn dẫn tới ranh giới giao dịch sai.

## 7. Mỗi store có cơ chế và giới hạn riêng

Bảng sau dùng để định hướng việc chọn hạ tầng, không thay thế việc kiểm tra cấu hình cụ thể của ứng dụng.

| Store hoặc mô hình | Hạ tầng giao dịch thường gặp | Điều phải xác minh |
|---|---|---|
| Spring Data JPA | `JpaTransactionManager` với `EntityManagerFactory`; có thể có hạ tầng JTA khi phù hợp | Persistence unit, datasource, flush, khóa và ranh giới giao dịch |
| Spring Data JDBC | Transaction manager JDBC, chẳng hạn `JdbcTransactionManager`, với `DataSource` | Repository thực sự dùng datasource nào, các bước cập nhật aggregate có nằm trong giao dịch hay không |
| Spring Data R2DBC | `R2dbcTransactionManager` với `ConnectionFactory` | Reactive pipeline có nằm trong transaction context và cùng factory hay không |
| Spring Data MongoDB | `MongoTransactionManager` hoặc `ReactiveMongoTransactionManager` theo mô hình truy cập | Cấu hình session, topology và khả năng giao dịch của MongoDB |
| Store khác | Tích hợp riêng của module hoặc backend | Có hỗ trợ giao dịch không, phạm vi atomicity và các thuộc tính được hỗ trợ |

Không thể thay `JpaTransactionManager` bằng một manager bất kỳ chỉ vì các repository đều có phương thức `save`.

### Atomicity một bản ghi không phải giao dịch nhiều bản ghi

MongoDB có các bảo đảm atomicity ở mức document, nhưng điều đó không tự biến một chuỗi thay đổi nhiều document thành một transaction.

Tương tự, một store có thao tác cập nhật nguyên tử cho một key hoặc một aggregate không có nghĩa là mọi repository trong ứng dụng cùng tham gia một giao dịch nhiều tài nguyên.

Khi backend chỉ bảo đảm nguyên tử trong phạm vi hẹp hơn invariant nghiệp vụ, cần:

1. Điều chỉnh mô hình dữ liệu nếu phù hợp.
2. Dùng cơ chế giao dịch mà backend thực sự hỗ trợ.
3. Hoặc thiết kế quy trình chấp nhận nhiều bước với cơ chế nhất quán riêng.

Không thể bổ sung một năng lực backend chưa có bằng cách chỉ thêm annotation.

## 8. Derived query, query khai báo và fragment cần được xét riêng

Spring Data có nhiều cách cung cấp phương thức repository:

- Phương thức CRUD được kế thừa.
- Derived query như `findByEmail`.
- Query khai báo bằng annotation của store.
- Phương thức mặc định trên interface.
- Repository fragment với implementation tùy biến.

Không suy rằng tất cả những cách trên tự nhận cùng một cấu hình giao dịch.

Với Spring Data JPA, các query method tự khai báo không mặc nhiên nhận cấu hình giao dịch của toàn bộ các phương thức CRUD cơ sở. Nếu cần ranh giới giao dịch, hãy cấu hình ở service hoặc tại phương thức/interface thích hợp.

Ví dụ một phương thức đọc được khai báo rõ:

```java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.transaction.annotation.Transactional;

public interface CustomerLookupRepository
        extends JpaRepository<Customer, Long> {

    @Transactional(
            transactionManager = "customerTx",
            readOnly = true)
    Optional<Customer> findByEmail(String email);
}
```

Đoạn mã giả định entity có property `email` và nhóm repository dùng đúng cấu hình JPA đã nêu.

Một thao tác query ghi của JPA có thể cần `@Modifying` để biểu diễn cách thực thi query. `@Modifying` không thay thế ranh giới giao dịch.

Với fragment tùy biến, cần xem implementation sử dụng `EntityManager`, template, driver hoặc kết nối nào. Một fragment tự tạo kết nối độc lập có thể không tham gia giao dịch mà service đang mở.

Nếu query cần dùng transaction đã có ở service, không bắt buộc lặp lại annotation ở mọi repository method. Mục tiêu là hợp đồng rõ ràng, không phải tăng số lượng annotation.

## 9. Hiểu đúng các thuộc tính giao dịch

### 9.1. readOnly là tín hiệu cấu hình, không phải cơ chế phân quyền

`readOnly = true` thể hiện ý định đọc và có thể được transaction manager, provider hoặc driver sử dụng để tối ưu hay áp dụng chế độ phù hợp.

Không dùng thuộc tính này làm bằng chứng rằng:

- Mọi backend sẽ chặn mọi lệnh ghi.
- Mọi query luôn đọc cùng một snapshot.
- Người gọi không có quyền ghi dữ liệu.
- Kết quả không thể thay đổi giữa hai lần đọc.

Cơ chế phân quyền, snapshot và mức nhất quán cần cấu hình riêng theo hệ thống.

Đặc biệt, không đặt một giao dịch chỉ đọc bao ngoài một use case ghi rồi trông chờ annotation ở phương thức ghi bên trong tự sửa mọi thuộc tính của giao dịch đang tồn tại.

### 9.2. Isolation phụ thuộc transaction manager và backend

Các isolation level mô tả những mức bảo vệ trước một số hiện tượng đọc và ghi đồng thời. Không phải backend nào cũng hỗ trợ đầy đủ các mức mà API cho phép khai báo.

Việc chọn isolation còn cần xét:

- Hiện tượng cạnh tranh thực sự cần ngăn chặn.
- Cách backend hiện thực isolation đó.
- Chi phí khóa, xung đột hoặc retry.
- Khả năng áp dụng thuộc tính khi tham gia một giao dịch đã tồn tại.

Hai lần `findById` trong cùng service không tự chứng minh rằng dữ liệu không thể thay đổi giữa hai lần đọc. Cần xét giao dịch và isolation thực tế.

### 9.3. Propagation xác định quan hệ với giao dịch hiện tại

| Lựa chọn | Ý nghĩa khái quát | Điểm cần chú ý |
|---|---|---|
| `REQUIRED` | Tham gia giao dịch hiện tại hoặc tạo mới | Các bước có thể cùng chịu quyết định rollback |
| `REQUIRES_NEW` | Chạy trong một giao dịch độc lập mới, với hạ tầng hỗ trợ | Commit riêng có thể tồn tại dù giao dịch ngoài rollback; có thêm nhu cầu tài nguyên |
| `NESTED` | Thực thi lồng với savepoint khi manager và tài nguyên hỗ trợ | Không đồng nghĩa một giao dịch độc lập như `REQUIRES_NEW` |

Không dùng `REQUIRES_NEW` chỉ để “chắc chắn dữ liệu được lưu”. Việc lưu một phần độc lập có thể phá invariant của use case.

Cũng không mặc định mọi transaction manager hỗ trợ savepoint hoặc giao dịch lồng theo cùng cách.

### 9.4. Timeout không phải cam kết về mọi hoạt động trong phương thức

Một timeout giao dịch được áp dụng theo khả năng của manager và tài nguyên tham gia. Nó không phải cơ chế bảo đảm rằng mọi phép tính, lời gọi HTTP hoặc tác vụ ngoài database đều tự dừng đúng thời hạn đó.

Giữ transaction ngắn và chỉ chứa các bước cần chia sẻ ranh giới dữ liệu thường giúp giảm thời gian giữ tài nguyên.

## 10. Điều kiện để annotation thực sự có hiệu lực

Khi dùng cơ chế proxy thông thường, `@Transactional` có tác dụng khi lời gọi được hạ tầng giao dịch của Spring chặn và xử lý.

Các trường hợp dễ bỏ sót:

### Gọi nội bộ trong cùng instance

```java
public void importCustomers() {
    this.renameOne();
}

@Transactional
public void renameOne() {
    // thao tác dữ liệu
}
```

Lời gọi `this.renameOne()` không đi qua proxy bên ngoài trong proxy mode thông thường. Vì vậy không nên dựa vào annotation đó để mở một giao dịch mới cho từng lần gọi nội bộ.

Có thể đặt ranh giới ở phương thức được gọi từ bên ngoài hoặc tách trách nhiệm sang một bean khác khi thật sự cần ranh giới riêng.

### Tự khởi tạo đối tượng

```java
CustomerService service =
        new CustomerService(customers, changes);
```

Đối tượng được tạo như trên không tự trở thành bean có transactional proxy. Việc inject repository vào nó không đủ để kích hoạt annotation trên service.

### Chọn sai manager

Một annotation chọn manager quản lý datasource A không tự bao phủ repository dùng datasource B.

### Tách công việc sang luồng hoặc pipeline khác

Giao dịch imperative thường gắn tài nguyên với luồng thực thi. Tự khởi tạo thread hoặc gửi công việc sang executor không tự truyền đầy đủ transaction hiện tại sang công việc đó.

Reactive transaction sử dụng context của reactive pipeline. Không dùng hiểu biết về thread-bound transaction để suy ra hành vi của reactive transaction.

Những trường hợp này cần được xem cùng với kiểu proxy, kiểu phương thức và cấu hình thực tế; annotation trên mã nguồn mới chỉ thể hiện ý định.

## 11. Rollback phải được hiểu theo quy tắc thực tế

Với cấu hình mặc định quen thuộc của `@Transactional` trong Spring, `RuntimeException` và `Error` là các loại lỗi dẫn tới rollback; checked exception không mặc nhiên có cùng quy tắc. Cấu hình ở ứng dụng hoặc annotation có thể thay đổi hành vi đó.

Ví dụ chỉ định checked exception cần rollback:

```java
@Transactional(
        transactionManager = "customerTx",
        rollbackFor = CustomerImportException.class)
public void importCustomers() throws CustomerImportException {
    // đọc, kiểm tra và ghi dữ liệu
}
```

Đoạn mã giả định `CustomerImportException` là exception do ứng dụng định nghĩa.

Cũng cần phân biệt lỗi có đi qua ranh giới giao dịch hay không:

```java
@Transactional(transactionManager = "customerTx")
public void updateCustomer() {
    try {
        performUpdate();
    } catch (RuntimeException ex) {
        // Chỉ ghi log rồi tiếp tục trả về bình thường.
    }
}
```

Nếu bắt lỗi rồi trả về bình thường, transaction interceptor ở ranh giới ngoài có thể không quan sát được lỗi đó. Ngược lại, một thao tác bên trong có thể đã đánh dấu giao dịch rollback-only, khiến giao dịch vẫn không thể commit dù lỗi bị bắt.

Vì vậy, không thể kết luận rằng “bắt exception thì commit được” hoặc “mọi exception đều tự rollback”. Phải xem loại lỗi, quy tắc rollback và trạng thái transaction.

Không dùng giá trị trả về như `false` hoặc `Optional.empty()` để kỳ vọng hạ tầng tự hiểu đó là yêu cầu rollback.

## 12. Repository reactive: giao dịch phải bao đúng pipeline

Tên phương thức không quyết định mô hình thực thi. Với reactive repository, giá trị trả về thường là `Mono` hoặc `Flux`; công việc thường được thực thi khi có subscription.

Một ví dụ khái niệm dùng `TransactionalOperator`:

```java
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;

public class ReactiveCustomerService {

    private final ReactiveCustomerRepository customers;
    private final ReactiveCustomerChangeRepository changes;
    private final TransactionalOperator transactions;

    public ReactiveCustomerService(
            ReactiveCustomerRepository customers,
            ReactiveCustomerChangeRepository changes,
            TransactionalOperator transactions) {
        this.customers = customers;
        this.changes = changes;
        this.transactions = transactions;
    }

    public Mono<Customer> rename(
            Long customerId,
            String newName) {

        Mono<Customer> work = customers.findById(customerId)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException(
                                "Customer not found")))
                .flatMap(customer -> {
                    customer.rename(newName);
                    return customers.save(customer);
                })
                .flatMap(saved -> changes.save(
                        new CustomerChange(
                                saved.getId(),
                                newName))
                        .thenReturn(saved));

        return transactions.transactional(work);
    }
}
```

Ví dụ giả định các repository và operator đã được cấu hình với cùng hạ tầng reactive có hỗ trợ transaction, chẳng hạn R2DBC và `R2dbcTransactionManager`.

Các thao tác phụ thuộc nhau được nối vào một pipeline. Không tự gọi `subscribe()` trong service để chạy phần ghi lịch sử rồi trả một publisher khác, vì công việc đó có thể bị tách khỏi vòng đời giao dịch mong muốn.

Ngoài ra:

- Tạo publisher chưa có nghĩa là dữ liệu đã commit.
- Subscription hoặc retry lại có thể thực thi lại công việc.
- Không tự dùng một JDBC/JPA transaction manager để quản lý I/O R2DBC.
- Chuyển sang coroutine bằng adapter không tự chọn transaction manager hay tạo ranh giới mới.

Khả năng sử dụng annotation cho phương thức reactive hoặc coroutine cần phù hợp với kiểu phương thức, transaction manager và tích hợp của framework đang dùng.

## 13. Nhiều repository không đồng nghĩa nhiều tài nguyên được commit cùng nhau

Hai repository cùng thuộc Spring Data vẫn có thể sử dụng:

- Hai datasource độc lập.
- Hai persistence unit.
- Một database quan hệ và một MongoDB.
- Một database và một hệ thống tìm kiếm.
- Một database và một dịch vụ HTTP ngoài hệ thống.

Một local transaction manager chỉ quản lý phạm vi tài nguyên của nó. Đặt `@Transactional` lên service không tự tạo một giao dịch phân tán cho toàn bộ các hệ thống này.

Ví dụ:

```text
Giao dịch database A:
    cập nhật customer
    gọi HTTP gửi thông báo
    lỗi khi ghi changeLog
    rollback database A

HTTP đã gửi thành công:
    không được database A tự hoàn tác
```

Nếu cần đưa sự kiện ra ngoài sau thay đổi dữ liệu, có thể xem xét:

- Lưu dữ liệu nghiệp vụ và bản ghi outbox trong cùng một database transaction.
- Có thành phần xử lý outbox và cơ chế retry.
- Thiết kế consumer hoặc tác vụ bên ngoài chịu được thông điệp lặp.

Outbox không tự cung cấp bảo đảm đúng một lần trên toàn bộ hệ thống. Nó tạo một điểm ghi nhận bền vững trong phạm vi transaction mà database có thể bảo đảm.

Một callback sau commit giúp sắp xếp thời điểm xử lý, nhưng riêng việc có callback không tạo ra hàng đợi bền vững khi tiến trình dừng đột ngột.

## 14. Các abstraction Commons khác không mở rộng atomicity

Những tính năng quen thuộc của Commons vẫn phải được đặt trong khả năng của store:

| Abstraction hoặc tính năng | Liên hệ với giao dịch |
|---|---|
| Derived query | Tạo phương thức truy vấn thuận tiện; không tự chọn isolation nghiệp vụ |
| Projection | Điều chỉnh hình dạng dữ liệu trả về; không tự tạo snapshot chung |
| `Pageable`, `Page`, `Slice`, `Sort` | Biểu diễn yêu cầu và kết quả truy xuất; không bảo đảm nhiều query cùng thấy một trạng thái |
| Query by Example | Mô tả điều kiện từ ví dụ; không khóa entity chỉ vì dùng example |
| Auditing | Gán metadata như người và thời điểm tạo/sửa theo tích hợp store; không phải chứng từ commit độc lập |
| Repository fragment | Mở rộng hành vi; cần kiểm tra tài nguyên và giao dịch của phần tùy biến |
| Metadata repository/entity | Mô tả cấu trúc và loại domain; không chứng minh backend hỗ trợ multi-record transaction |

Chẳng hạn, một kết quả `Page` có thể cần query lấy dữ liệu và query đếm. Nếu cần hai phần phản ánh một trạng thái dữ liệu nhất quán, phải xét cách thực thi, giao dịch và isolation; bản thân kiểu `Page` không cung cấp bảo đảm đó.

Tương tự, thấy property `lastModifiedDate` đã được gán trong object không có nghĩa là thay đổi đã commit. Object trong bộ nhớ và trạng thái đã commit của database là hai điều cần phân biệt.

## 15. Cách đọc hợp đồng của một repository trong dự án

Khi cần xác định một use case có được bảo vệ đúng hay không, hãy lần theo các câu hỏi sau:

1. Repository thuộc module store nào?
2. Implementation hoặc fragment thực sự dùng tài nguyên nào?
3. Phương thức đang được gọi là CRUD kế thừa hay query tùy biến?
4. Giao dịch bắt đầu ở service, repository hay qua API lập trình?
5. Lời gọi có đi qua hạ tầng giao dịch phù hợp không?
6. Transaction manager được chọn là bean nào và quản lý tài nguyên nào?
7. Các thao tác cần nguyên tử có cùng tham gia phạm vi đó không?
8. Store hỗ trợ những thuộc tính isolation, propagation, timeout nào?
9. Lỗi nào cần rollback và quy tắc đang cấu hình có đáp ứng không?
10. Có tác vụ ngoài transaction, lời gọi HTTP hoặc công việc bị tách vòng đời không?

Các câu hỏi này giúp chuyển từ suy luận theo tên interface sang xác định hợp đồng thực thi cụ thể.

Không cần ghi lại mọi chi tiết driver trong API nghiệp vụ. Chỉ cần tài liệu hóa rõ những bảo đảm mà người gọi dựa vào, chẳng hạn:

> Đổi tên khách hàng và ghi lịch sử được thực hiện trong cùng giao dịch của database customer. Gửi thông báo là quy trình riêng, có retry.

Mô tả như vậy chính xác hơn câu “service có transactional nên mọi thứ luôn đồng bộ”.

## 16. Chẩn đoán các hiểu nhầm thường gặp

| Hiện tượng hoặc nhận định | Điều cần kiểm tra |
|---|---|
| `save` trả kết quả nhưng cuối cùng không có bản ghi | Transaction ngoài có rollback hoặc commit thất bại không? |
| Một bước đã lưu dù bước sau lỗi | Có giao dịch riêng, `REQUIRES_NEW` hoặc tài nguyên khác không? |
| Có annotation nhưng không thấy giao dịch | Bean có do Spring quản lý, lời gọi có qua proxy và manager có đúng không? |
| Query method mới có hành vi khác CRUD kế thừa | Query tự khai báo đã được cấu hình giao dịch phù hợp chưa? |
| Giao dịch ngoài chỉ đọc nhưng bên trong muốn ghi | Phương thức ghi có đang tham gia giao dịch chỉ đọc đã tồn tại không? |
| Bắt exception nhưng commit vẫn thất bại | Giao dịch đã bị đánh dấu rollback-only chưa? |
| Hai repository không rollback cùng nhau | Chúng có cùng tài nguyên và transaction manager không? |
| Reactive service chưa truy vấn gì | Pipeline đã có subscription và chứa đầy đủ công việc chưa? |
| Metadata auditing đã đổi nhưng database chưa đổi | Đang quan sát object trong bộ nhớ hay dữ liệu đã commit? |
| Trang dữ liệu và tổng số không khớp khi có cập nhật đồng thời | Query dữ liệu và query đếm có cùng bảo đảm nhất quán mong muốn không? |

Chẩn đoán cần bắt đầu từ ranh giới và tài nguyên cụ thể. Thêm annotation vào mọi phương thức thường làm cấu hình khó hiểu hơn nếu chưa xác định được nguyên nhân.

## 17. Bài thực hành

Chọn một store mà môi trường học tập đã cấu hình hỗ trợ giao dịch. Với ví dụ JPA ở trên:

1. Tạo hai entity và repository cho khách hàng cùng lịch sử thay đổi.
2. Cấu hình chúng dùng chung persistence unit và transaction manager.
3. Viết service đổi tên rồi ghi lịch sử trong cùng ranh giới.
4. Tạo tình huống bước ghi lịch sử thất bại và quan sát dữ liệu sau khi giao dịch kết thúc.
5. Đối chiếu với cách gọi hai bước độc lập, không có giao dịch service bao ngoài.
6. Thêm một query method tự khai báo và xác định ranh giới giao dịch mà nó sử dụng.
7. Mô tả điều gì thay đổi nếu lịch sử được chuyển sang một database khác.
8. Giải thích vì sao gửi HTTP trong service không tự rollback theo database.

Khi kiểm tra rollback trong môi trường thật, hãy đọc lại dữ liệu sau khi giao dịch cần kiểm tra đã kết thúc, bằng một phạm vi đọc phù hợp. Không chỉ quan sát các object còn nằm trong persistence context.

Nếu có transaction bao ngoài do hạ tầng kiểm thử tạo ra, cần tính đến nó khi diễn giải thời điểm commit và rollback. Một kiểm tra chỉ gọi mock repository không xác minh được sự tham gia của tài nguyên thật vào transaction.

## 18. Những điều cần nắm vững

Hợp đồng repository của Spring Data Commons giúp ứng dụng diễn đạt thao tác dữ liệu theo một mô hình chung. Bảo đảm giao dịch đến từ sự phối hợp giữa module store, transaction manager, driver và backend.

Một ranh giới đúng phải bao phủ các thao tác cần giữ cùng invariant, sử dụng đúng tài nguyên và tồn tại trong vòng đời thực thi thực tế. Kiểu `CrudRepository`, từ khóa `save` hay annotation `@Transactional` đứng riêng lẻ đều chưa mô tả đủ bảo đảm đó.

Khi chuyển store hoặc thay mô hình imperative bằng reactive/coroutine, cần xác nhận lại hợp đồng giao dịch thay vì chỉ giữ nguyên tên phương thức.
