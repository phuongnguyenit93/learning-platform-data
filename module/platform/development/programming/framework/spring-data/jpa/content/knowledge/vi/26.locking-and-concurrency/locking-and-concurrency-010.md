# Kiểm thử đồng thời cho tồn kho, số dư và đặt chỗ

## Mục tiêu

Trong ứng dụng có nhiều người dùng cùng thao tác, hai request có thể đọc cùng một trạng thái rồi cùng ghi kết quả. Nếu không có cơ chế bảo vệ phù hợp, tồn kho có thể âm, tài khoản có thể chi vượt số dư, hoặc cùng một ghế có thể được đặt hai lần. Những lỗi này là race condition: kết quả phụ thuộc vào thứ tự xen kẽ của các transaction.

Kiểm thử đồng thời cần chứng minh **bất biến dữ liệu (invariant)** vẫn đúng khi nhiều transaction tranh chấp cùng một tài nguyên. Bài này xây dựng cách kiểm thử cho ba tình huống:

- **Tồn kho:** nhiều đơn hàng mua cùng SKU; số lượng khả dụng không được âm và tổng số lượng bán thành công không vượt tồn kho ban đầu.
- **Số dư:** nhiều giao dịch chuyển tiền cùng lúc; tài khoản không được âm và tổng tiền giữa các tài khoản phải được bảo toàn.
- **Đặt chỗ:** nhiều request đặt cùng một ghế; tối đa một reservation được ghi nhận cho một sự kiện và ghế đó.

Ba tình huống cần những cơ chế bảo vệ khác nhau: cập nhật có điều kiện nguyên tử ở database, khóa pessimistic khi cần đọc rồi cập nhật nhiều hàng, và unique constraint cho tài nguyên chỉ được đặt một lần. Test phải chạy bằng nhiều thread với transaction độc lập và xác minh trạng thái cuối trong database.

## 1. Vì sao kiểm thử tuần tự không phát hiện race condition?

Giả sử tồn kho có 1 sản phẩm. Hai request cùng mua một sản phẩm. Nếu code đọc rồi ghi theo hai bước:

```java
InventoryItem item = repository.findById(id).orElseThrow();
if (item.getAvailable() > 0) {
    item.setAvailable(item.getAvailable() - 1);
    repository.save(item);
}
```

Trong một lần chạy tuần tự, request thứ nhất giảm tồn kho từ 1 xuống 0. Request thứ hai đọc 0 và bị từ chối. Test đơn luồng sẽ pass.

Nhưng hai transaction có thể xen kẽ như sau:

```text
Transaction A                 Transaction B
---------------------------   ---------------------------
SELECT available -> 1
                              SELECT available -> 1
available = 0
                              available = 0
UPDATE available = 0
                              UPDATE available = 0
COMMIT                        COMMIT
```

Cả hai request có thể báo mua thành công dù chỉ còn một sản phẩm. Đây là lost update và overselling. Kiểm thử tuần tự không tạo được interleaving này.

Với số dư, hai request rút tiền có thể cùng đọc một số dư cũ và ghi đè kết quả. Với đặt chỗ, hai request có thể cùng kiểm tra ghế chưa được đặt rồi cùng insert reservation. Vì vậy, test cần nhiều thread và transaction riêng, sau đó xác minh invariant ở database.

## 2. Xác định invariant trước khi viết test

Không bắt đầu bằng câu hỏi “thread nào phải thắng?”. Thứ tự chạy giữa các thread không được bảo đảm. Hãy bắt đầu bằng các điều kiện dữ liệu luôn phải đúng.

| Nghiệp vụ | Invariant cần giữ | Kết quả test nên xác minh |
| --- | --- | --- |
| Tồn kho | `available >= 0` | Số lần mua thành công không vượt số lượng ban đầu; số tồn cuối đúng. |
| Số dư | `balance >= 0` và tổng tiền không đổi khi chuyển nội bộ | Không có tài khoản âm; tổng debit bằng tổng credit; giao dịch thất bại không làm thay đổi số dư. |
| Đặt ghế | Một `(eventId, seatNumber)` chỉ có tối đa một reservation | Nhiều request cùng ghế chỉ có một request commit thành công và database có đúng một hàng. |
| Đặt chỗ theo sức chứa | `remaining >= 0` | Số booking thành công không vượt capacity; decrement capacity và insert reservation phải cùng transaction. |

Invariant nên được bảo vệ ở database, không chỉ ở Java. Kiểm tra trước bằng `existsBy...` hoặc đọc số dư rồi quyết định không đủ để chống race condition vì transaction khác có thể ghi sau lần kiểm tra đó.

## 3. Chọn cơ chế bảo vệ theo loại tranh chấp

### Tồn kho: một câu UPDATE có điều kiện

Với bộ đếm tồn kho, cách gọn và an toàn là cập nhật nguyên tử có điều kiện:

```sql
update inventory_items
set available = available - :quantity
where id = :id
  and available >= :quantity;
```

Database thực hiện phép kiểm tra và giảm số lượng trong cùng một câu lệnh. Mỗi request nhận số hàng được cập nhật:

- `1`: giảm tồn kho thành công.
- `0`: không có item phù hợp hoặc tồn kho không đủ.

Không có khoảng thời gian giữa SELECT và UPDATE để request khác chen vào dùng cùng giá trị cũ. Hãy kiểm tra `quantity > 0` ở service và thêm CHECK constraint `available >= 0` ở database để bảo vệ invariant ở lớp cuối.

### Số dư: pessimistic lock hoặc optimistic lock

Chuyển tiền thường phải đọc số dư, kiểm tra điều kiện, rồi cập nhật hai tài khoản trong cùng transaction. Hai chiến lược phổ biến:

- **Pessimistic locking:** lấy `PESSIMISTIC_WRITE` trên các hàng tài khoản trước khi kiểm tra số dư và ghi. Transaction khác phải chờ khóa được giải phóng.
- **Optimistic locking:** thêm `@Version`; nếu transaction ghi trên version cũ, một transaction bị từ chối với lỗi optimistic locking. Ứng dụng có thể thử lại toàn bộ use case trong transaction mới nếu nghiệp vụ cho phép.

Với chuyển tiền giữa hai tài khoản, nếu dùng pessimistic lock, luôn khóa theo cùng một thứ tự ID (ví dụ ID nhỏ trước, ID lớn sau). Điều này giảm nguy cơ deadlock khi hai giao dịch chuyển tiền ngược chiều.

Debit và credit phải ở trong một transaction. Nếu debit thành công nhưng credit lỗi, transaction phải rollback cả hai.

### Đặt ghế: unique constraint

Với ghế cụ thể trong một sự kiện, đặt unique constraint trên cặp `(event_id, seat_number)`. Hai transaction có thể cùng thử insert, nhưng database chỉ cho phép một hàng tồn tại.

```sql
alter table reservations
add constraint uk_event_seat unique (event_id, seat_number);
```

Ứng dụng có thể kiểm tra trước để hiển thị thông báo thân thiện, nhưng unique constraint mới là bảo đảm cuối cùng khi hai request đến đồng thời. Khi vi phạm constraint, Spring thường chuyển lỗi persistence thành `DataIntegrityViolationException`.

Với đặt chỗ theo sức chứa thay vì từng ghế, dùng UPDATE có điều kiện `remaining > 0` để giảm capacity. Nếu phải tạo reservation, giảm capacity và insert reservation trong cùng transaction để không có trường hợp trừ chỗ nhưng không tạo được booking.

## 4. Ranh giới transaction và thread trong test

Mỗi thao tác cạnh tranh phải chạy trong transaction độc lập. Một cách thực tế là gọi Spring service bean có method `@Transactional` từ các worker thread. Transaction interceptor mở transaction riêng cho từng lời gọi.

Test class không nên đặt `@Transactional` cho các test kiểu này:

- Transaction của test chạy trên thread test, không tự truyền sang worker thread.
- Dữ liệu setup chưa commit có thể không nhìn thấy từ transaction của worker.
- Assertion cuối có thể đọc dữ liệu chưa commit hoặc rollback khi test kết thúc.

Hãy để test không transactional, dùng `saveAndFlush` hoặc transaction setup đã commit, gọi service từ nhiều thread, đợi mọi Future hoàn thành rồi đọc trạng thái cuối qua repository.

Không chia sẻ một `EntityManager`, Hibernate `Session` hoặc entity đang managed giữa các thread. EntityManager không thread-safe. Mỗi worker gọi service/repository thông qua Spring proxy để nhận persistence context gắn với transaction của chính nó.

## 5. Tạo đồng thời có kiểm soát

Dùng `ExecutorService` để tạo nhiều worker và `CountDownLatch` làm cổng bắt đầu:

1. Tạo pool có số thread bằng số worker.
2. Mỗi worker báo đã sẵn sàng bằng `ready.countDown()`.
3. Worker chờ `start.await()`.
4. Test đợi tất cả worker sẵn sàng rồi gọi `start.countDown()` một lần.
5. Thu kết quả qua `Future.get()` với timeout.
6. Tắt executor trong `finally`.

Không dùng `Thread.sleep()` để “hy vọng” hai transaction đụng nhau. Sleep phụ thuộc tốc độ máy và làm test chập chờn. Start gate giúp các worker bắt đầu cùng lúc và tạo contention có chủ đích.

Với một race condition cụ thể cần đồng bộ chính xác giữa hai bước đọc và ghi, có thể dùng `CyclicBarrier` hoặc `CountDownLatch` trong test harness để dừng hai transaction ngay sau khi đọc. Không đưa barrier vào production service. Ví dụ optimistic locking ở phần sau giải thích cách kiểm soát interleaving này.

## 6. Thiết kế test tồn kho

Giả sử tồn kho ban đầu là 10 và có 20 request đồng thời, mỗi request mua một đơn vị. Kết quả hợp lệ:

- Chính xác 10 request thành công.
- 10 request còn lại bị từ chối vì hết hàng.
- Tồn kho cuối bằng 0.
- Không có lúc nào database lưu `available < 0`.

Test nên kiểm tra số request thành công và đọc lại giá trị tồn kho từ database. Không chỉ kiểm tra exception hoặc kết quả trả về trong từng thread, vì lỗi có thể nằm ở trạng thái đã commit.

### Vì sao dùng row count?

UPDATE có điều kiện trả về số hàng thực sự được cập nhật. Đây là tín hiệu trực tiếp để service quyết định thành công hay hết hàng. Nếu dùng `findById`, kiểm tra Java rồi `save`, hai transaction có thể cùng vượt qua điều kiện trước khi một transaction ghi.

## 7. Thiết kế test chuyển tiền

Giả sử tài khoản A có 100, tài khoản B có 100. Có 20 request đồng thời chuyển 10 từ A sang B.

Kết quả hợp lệ:

- Chính xác 10 giao dịch thành công.
- A có số dư 0; B có số dư 200.
- Tổng tiền vẫn là 200.
- Không có tài khoản âm.
- 10 giao dịch bị từ chối không thay đổi số dư.

Test này tạo contention trên cùng hai hàng. Pessimistic lock bảo đảm mỗi transaction kiểm tra số dư sau khi đã lấy khóa. Thứ tự khóa thống nhất giúp các giao dịch ngược chiều không khóa A/B theo hai thứ tự khác nhau.

Với optimistic locking, test tương đương cần tạo hai transaction đọc cùng version trước khi một transaction ghi. Một transaction commit; transaction còn lại phải nhận lỗi optimistic lock. Nếu ứng dụng retry, retry phải chạy lại toàn bộ use case trong transaction mới và có giới hạn.

## 8. Thiết kế test đặt ghế

Hai worker cùng đặt `eventId=77`, `seatNumber=A-10`. Database có unique constraint trên cặp giá trị đó.

Kết quả hợp lệ:

- Một request commit thành công.
- Một request nhận lỗi duplicate key/constraint.
- `countByEventIdAndSeatNumber(77, "A-10")` bằng 1.

Không dựa vào việc hai request đều gọi `existsBy...` trước khi insert. Cả hai có thể cùng thấy chưa tồn tại. Kiểm tra trước chỉ giúp thông báo sớm; unique constraint mới giải quyết tranh chấp.

Nếu API hỗ trợ retry do client không nhận được response, thêm idempotency key có unique constraint. Khi cùng request được gửi lại, hệ thống trả lại kết quả của request đã xử lý thay vì tạo booking mới.

## 9. Ví dụ hoàn chỉnh với Java 17+, Spring Boot và H2

Ví dụ dùng ba chiến lược khác nhau trong cùng ứng dụng:

- Inventory: conditional atomic UPDATE.
- Account: hai `PESSIMISTIC_WRITE` lock theo thứ tự ID.
- Reservation: unique constraint cho event và seat.

Integration test chạy 20 worker đồng thời cho tồn kho và số dư, hai worker cho cùng một ghế. Mỗi service method được gọi qua Spring bean nên mỗi lời gọi có transaction riêng.

### Cấu trúc dự án

```text
concurrency-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/concurrency/
    │   │   ├── ConcurrencyApplication.java
    │   │   ├── InventoryItem.java
    │   │   ├── Account.java
    │   │   ├── Reservation.java
    │   │   ├── InventoryRepository.java
    │   │   ├── AccountRepository.java
    │   │   ├── ReservationRepository.java
    │   │   ├── InventoryService.java
    │   │   ├── AccountTransferService.java
    │   │   └── ReservationService.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/concurrency/ConcurrencyIntegrationTest.java
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>concurrency-tests</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:concurrency;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=30000
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=30
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

`LOCK_TIMEOUT` và connection pool được đặt đủ rộng để các worker của test có thể chờ nhau trong lúc tranh chấp. Giá trị phù hợp cho production cần dựa trên database, latency và giới hạn connection thực tế.

### `ConcurrencyApplication.java`

```java
package com.example.concurrency;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConcurrencyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConcurrencyApplication.class, args);
    }
}
```

### `InventoryItem.java`

```java
package com.example.concurrency;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Check;

@Entity
@Table(name = "inventory_items")
@Check(constraints = "available >= 0")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 60)
    private String sku;

    @Column(nullable = false)
    private int available;

    protected InventoryItem() {
    }

    public InventoryItem(String sku, int available) {
        this.sku = sku;
        this.available = available;
    }

    public Long getId() {
        return id;
    }

    public int getAvailable() {
        return available;
    }
}
```

`@Check` tạo CHECK constraint thông qua Hibernate schema generation. Với production, nên quản lý constraint bằng migration như Flyway hoặc Liquibase để schema được kiểm soát và triển khai nhất quán.

### `Account.java`

```java
package com.example.concurrency;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import org.hibernate.annotations.Check;

@Entity
@Table(name = "accounts")
@Check(constraints = "balance >= 0")
public class Account {
    @Id
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal balance;

    protected Account() {
    }

    public Account(Long id, BigDecimal balance) {
        this.id = id;
        this.balance = balance;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getBalance() {
        return balance;
    }

    public void debit(BigDecimal amount) {
        balance = balance.subtract(amount);
    }

    public void credit(BigDecimal amount) {
        balance = balance.add(amount);
    }
}
```

ID tài khoản được gán sẵn để ví dụ tập trung vào khóa hai hàng theo thứ tự. Hệ thống thực tế có thể dùng ID sinh tự động; nguyên tắc khóa theo một thứ tự nhất quán vẫn giữ nguyên.

### `Reservation.java`

```java
package com.example.concurrency;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "reservations",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_reservation_event_seat",
        columnNames = {"event_id", "seat_number"}
    )
)
public class Reservation {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_id", nullable = false)
    private Long eventId;

    @Column(name = "seat_number", nullable = false, length = 20)
    private String seatNumber;

    protected Reservation() {
    }

    public Reservation(Long eventId, String seatNumber) {
        this.eventId = eventId;
        this.seatNumber = seatNumber;
    }
}
```

Unique constraint là cơ chế bảo đảm một ghế chỉ được đặt một lần. Nếu reservation có trạng thái CANCELLED và cho phép đặt lại ghế sau khi hủy, thiết kế cần unique constraint có điều kiện/partial index theo trạng thái nếu database hỗ trợ, hoặc mô hình hóa một hàng seat inventory riêng để khóa và chuyển trạng thái.

### `InventoryRepository.java`

```java
package com.example.concurrency;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository extends JpaRepository<InventoryItem, Long> {
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("update InventoryItem i "
         + "set i.available = i.available - :quantity "
         + "where i.id = :id and i.available >= :quantity")
    int decreaseIfAvailable(
            @Param("id") Long id,
            @Param("quantity") int quantity
    );
}
```

Bulk update bỏ qua trạng thái entity đang managed trong persistence context. `clearAutomatically = true` xóa persistence context sau query để tránh dùng entity cũ; nếu fragment/service đang quản lý những entity khác, hãy cân nhắc phạm vi clear và flush trước khi chạy bulk update.

### `AccountRepository.java`

```java
package com.example.concurrency;

import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AccountRepository extends JpaRepository<Account, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = :id")
    Optional<Account> findForUpdateById(@Param("id") Long id);
}
```

`PESSIMISTIC_WRITE` yêu cầu database khóa hàng được đọc để transaction khác không thể đồng thời cập nhật hàng đó theo cùng cách. Khóa được giữ đến khi transaction commit hoặc rollback.

### `ReservationRepository.java`

```java
package com.example.concurrency;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ReservationRepository extends JpaRepository<Reservation, Long> {
    long countByEventIdAndSeatNumber(Long eventId, String seatNumber);
}
```

### `InventoryService.java`

```java
package com.example.concurrency;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void purchase(Long itemId, int quantity) {
        if (itemId == null || quantity <= 0) {
            throw new IllegalArgumentException("itemId and positive quantity are required");
        }

        int changed = repository.decreaseIfAvailable(itemId, quantity);
        if (changed != 1) {
            throw new OutOfStockException("Item not found or insufficient stock");
        }
    }

    public static class OutOfStockException extends RuntimeException {
        public OutOfStockException(String message) {
            super(message);
        }
    }
}
```

Service không đọc tồn kho trước khi cập nhật. Database kiểm tra điều kiện `available >= quantity` và giảm trong một câu lệnh. Nếu không có hàng được cập nhật, service báo hết hàng hoặc không tìm thấy item.

### `AccountTransferService.java`

```java
package com.example.concurrency;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountTransferService {
    private final AccountRepository repository;

    public AccountTransferService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void transfer(Long fromId, Long toId, BigDecimal amount) {
        if (fromId == null || toId == null || amount == null
                || amount.signum() <= 0 || fromId.equals(toId)) {
            throw new IllegalArgumentException("Invalid transfer request");
        }

        // Every transfer locks the lower ID first to reduce deadlock risk.
        Long firstId = Math.min(fromId, toId);
        Long secondId = Math.max(fromId, toId);

        Account first = repository.findForUpdateById(firstId)
                .orElseThrow(() -> new IllegalArgumentException("Account not found: " + firstId));
        Account second = repository.findForUpdateById(secondId)
                .orElseThrow(() -> new IllegalArgumentException("Account not found: " + secondId));

        Account source = fromId.equals(firstId) ? first : second;
        Account target = fromId.equals(firstId) ? second : first;

        if (source.getBalance().compareTo(amount) < 0) {
            throw new InsufficientFundsException("Insufficient balance");
        }

        source.debit(amount);
        target.credit(amount);
    }

    public static class InsufficientFundsException extends RuntimeException {
        public InsufficientFundsException(String message) {
            super(message);
        }
    }
}
```

Không cần gọi `save()` cho hai account đã managed trong transaction; dirty checking sẽ ghi thay đổi khi flush/commit. Nếu credit hoặc commit thất bại, transaction rollback cả debit và credit.

### `ReservationService.java`

```java
package com.example.concurrency;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationService {
    private final ReservationRepository repository;

    public ReservationService(ReservationRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserve(Long eventId, String seatNumber) {
        if (eventId == null || seatNumber == null || seatNumber.isBlank()) {
            throw new IllegalArgumentException("eventId and seatNumber are required");
        }

        // Flush inside the service so the unique-key violation is raised here.
        repository.saveAndFlush(new Reservation(eventId, seatNumber));
    }
}
```

Không cần khóa Java hoặc `synchronized` để bảo đảm uniqueness giữa nhiều application instance. Unique constraint hoạt động ở database và bảo vệ cả khi request đi vào nhiều server khác nhau.

### `ConcurrencyIntegrationTest.java`

```java
package com.example.concurrency;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;

@SpringBootTest
class ConcurrencyIntegrationTest {
    @Autowired
    private InventoryRepository inventoryRepository;

    @Autowired
    private InventoryService inventoryService;

    @Autowired
    private AccountRepository accountRepository;

    @Autowired
    private AccountTransferService transferService;

    @Autowired
    private ReservationRepository reservationRepository;

    @Autowired
    private ReservationService reservationService;

    @BeforeEach
    void cleanDatabase() {
        reservationRepository.deleteAllInBatch();
        inventoryRepository.deleteAllInBatch();
        accountRepository.deleteAllInBatch();
    }

    @Test
    void concurrentPurchasesNeverOversell() throws Exception {
        InventoryItem item = inventoryRepository.saveAndFlush(
                new InventoryItem("SKU-1", 10));

        List<Boolean> outcomes = runConcurrently(20, () -> {
            try {
                inventoryService.purchase(item.getId(), 1);
                return true;
            } catch (InventoryService.OutOfStockException expected) {
                return false;
            }
        });

        long successful = outcomes.stream().filter(Boolean::booleanValue).count();
        assertThat(successful).isEqualTo(10L);
        assertThat(inventoryRepository.findById(item.getId())
                .orElseThrow().getAvailable()).isZero();
    }

    @Test
    void concurrentTransfersCannotOverspendOrCreateMoney() throws Exception {
        accountRepository.saveAllAndFlush(List.of(
                new Account(1L, new BigDecimal("100.00")),
                new Account(2L, new BigDecimal("100.00"))
        ));

        List<Boolean> outcomes = runConcurrently(20, () -> {
            try {
                transferService.transfer(1L, 2L, new BigDecimal("10.00"));
                return true;
            } catch (AccountTransferService.InsufficientFundsException expected) {
                return false;
            }
        });

        long successful = outcomes.stream().filter(Boolean::booleanValue).count();
        assertThat(successful).isEqualTo(10L);

        BigDecimal balanceA = accountRepository.findById(1L)
                .orElseThrow().getBalance();
        BigDecimal balanceB = accountRepository.findById(2L)
                .orElseThrow().getBalance();

        assertThat(balanceA).isEqualByComparingTo("0.00");
        assertThat(balanceB).isEqualByComparingTo("200.00");
        assertThat(balanceA.add(balanceB)).isEqualByComparingTo("200.00");
    }

    @Test
    void theSameSeatCanBeReservedOnlyOnce() throws Exception {
        List<Boolean> outcomes = runConcurrently(2, () -> {
            try {
                reservationService.reserve(77L, "A-10");
                return true;
            } catch (DataIntegrityViolationException expected) {
                return false;
            }
        });

        long successful = outcomes.stream().filter(Boolean::booleanValue).count();
        assertThat(successful).isEqualTo(1L);
        assertThat(reservationRepository.countByEventIdAndSeatNumber(77L, "A-10"))
                .isEqualTo(1L);
    }

    private static <T> List<T> runConcurrently(
            int workerCount, Callable<T> action) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(workerCount);
        CountDownLatch ready = new CountDownLatch(workerCount);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<T>> futures = new ArrayList<>();
            for (int i = 0; i < workerCount; i++) {
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new TimeoutException("Workers did not receive start signal");
                    }
                    return action.call();
                }));
            }

            assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
            start.countDown();

            List<T> results = new ArrayList<>();
            for (Future<T> future : futures) {
                results.add(future.get(60, TimeUnit.SECONDS));
            }
            return results;
        } finally {
            start.countDown();
            executor.shutdownNow();
            assertThat(executor.awaitTermination(10, TimeUnit.SECONDS)).isTrue();
        }
    }
}
```

Test class không có `@Transactional`. Dữ liệu khởi tạo được ghi bằng `saveAndFlush`, sau đó các worker gọi service bean. Mỗi lời gọi service được Spring mở transaction độc lập; `Future.get()` đợi transaction hoàn tất trước khi test đọc trạng thái cuối.

### Chạy test

```bash
mvn test
```

Test suite có ba bài kiểm thử:

```text
concurrentPurchasesNeverOversell
  20 request, 10 thành công, tồn kho cuối = 0

concurrentTransfersCannotOverspendOrCreateMoney
  20 request chuyển 10, 10 thành công, A = 0.00, B = 200.00

theSameSeatCanBeReservedOnlyOnce
  2 request cùng ghế, 1 thành công, số reservation = 1
```

Maven sẽ in số test, failure và error theo định dạng của Surefire. Các dòng trên mô tả assertion mong đợi, không phải log đã được chạy trong môi trường tài liệu này.

## 10. Optimistic locking và cách kiểm thử conflict

Nếu dữ liệu ít tranh chấp và muốn tránh giữ row lock trong lúc xử lý, có thể dùng optimistic locking với `@Version`:

```java
@Entity
public class Wallet {
    @Id
    private Long id;

    private BigDecimal balance;

    @Version
    private long version;
}
```

Khi transaction đọc Wallet version 4, Hibernate cập nhật theo điều kiện tương tự:

```sql
update wallets
set balance = ?, version = 5
where id = ? and version = 4;
```

Nếu transaction khác đã cập nhật version lên 5, UPDATE cũ không còn khớp hàng nào và provider báo optimistic locking conflict. Spring thường chuyển thành `ObjectOptimisticLockingFailureException` hoặc một subtype của `OptimisticLockingFailureException`.

Để test conflict một cách có kiểm soát:

1. Mở hai transaction độc lập trên hai thread.
2. Mỗi transaction đọc cùng một Wallet và cùng version.
3. Dùng `CyclicBarrier` trong test để đợi cả hai đã đọc xong.
4. Cho cả hai cập nhật và flush.
5. Xác nhận một transaction commit, transaction còn lại nhận optimistic locking exception.
6. Đọc lại database và xác nhận chỉ một thay đổi được ghi.

Barrier chỉ dùng trong test harness để tạo interleaving có chủ đích. Không đặt barrier hoặc sleep vào service production.

Nếu retry optimistic conflict, retry toàn bộ thao tác nghiệp vụ trong transaction mới. Không bắt lỗi rồi tiếp tục dùng transaction đã bị đánh dấu rollback-only. Retry phải có giới hạn, có backoff phù hợp và chỉ áp dụng khi thao tác có semantics idempotent hoặc có cơ chế chống lặp.

## 11. Kiểm thử deadlock và thứ tự khóa

Deadlock có thể xảy ra khi:

- Transaction A khóa account 1 rồi chờ account 2.
- Transaction B khóa account 2 rồi chờ account 1.

Cách giảm rủi ro là khóa các hàng theo cùng một thứ tự toàn cục, ví dụ ID tăng dần. Cả hai hướng chuyển tiền đều khóa account ID nhỏ trước, sau đó ID lớn.

Trong test nâng cao, chạy nhiều giao dịch chuyển tiền hai chiều và đặt timeout cho Future. Sau khi mọi transaction hoàn tất, xác nhận tổng tiền không đổi và không có số dư âm. Nếu database phát hiện deadlock, một transaction có thể bị hủy; ứng dụng cần xử lý lỗi phù hợp và có thể retry transaction mới với giới hạn.

Không thể chứng minh ứng dụng không bao giờ deadlock chỉ bằng một test. Hãy xem execution plan, thứ tự truy cập nhiều bảng, index và lock timeout trên database production.

## 12. Những lỗi thường gặp khi viết concurrency test

1. **Test tuần tự:** không tạo contention và có thể bỏ sót race condition. Dùng nhiều worker thread.
2. **Dùng `Thread.sleep()` để điều phối:** phụ thuộc tốc độ máy và không bảo đảm interleaving. Dùng latch hoặc barrier.
3. **Một transaction dùng chung cho mọi worker:** không mô phỏng nhiều request độc lập. Gọi transactional service qua Spring proxy từ từng thread.
4. **Đặt `@Transactional` trên test:** worker không tham gia transaction của test; dữ liệu setup chưa commit có thể không nhìn thấy.
5. **Chia sẻ EntityManager hoặc Session:** các đối tượng này không thread-safe. Mỗi thread phải dùng transaction/persistence context riêng.
6. **Chỉ kiểm tra response:** đọc lại database để xác minh invariant sau khi mọi Future hoàn thành.
7. **Chỉ kiểm tra `existsBy...` trước khi insert:** hai transaction vẫn có thể cùng vượt qua check. Dùng unique constraint.
8. **Đọc rồi ghi bộ đếm trong Java:** dùng atomic conditional UPDATE hoặc lock phù hợp.
9. **Khóa nhiều hàng không theo thứ tự:** dễ tạo deadlock. Khóa theo thứ tự nhất quán.
10. **Bắt lỗi constraint rồi tiếp tục transaction:** transaction có thể đã rollback-only. Xử lý lỗi bên ngoài transaction thất bại.
11. **Dùng H2 để kết luận hành vi production:** H2 hữu ích cho test nhanh nhưng lock, isolation, SQL và constraint behavior có thể khác PostgreSQL, MySQL, SQL Server hoặc Oracle.
12. **Chỉ kiểm thử một lần:** race condition có thể hiếm. Chạy lặp trong CI, tăng contention có kiểm soát và giữ assertion theo invariant.
13. **Không kiểm thử retry/idempotency:** client hoặc message broker có thể gửi lại request. Dùng idempotency key/unique constraint nếu nghiệp vụ cần.
14. **Không đặt timeout:** test có thể treo khi deadlock hoặc worker không kết thúc. Dùng timeout cho latch, Future và test runner.

## 13. Chạy test trên database giống production

Concurrency phụ thuộc mạnh vào database engine, isolation level, lock implementation, index và connection pool. H2 không thay thế được integration test trên engine production.

Đối với hệ thống production dùng PostgreSQL, MySQL hoặc SQL Server, nên bổ sung Testcontainers để chạy cùng loại database trong CI:

- Dùng cùng phiên bản major của database với môi trường triển khai.
- Áp dụng migration thật thay vì chỉ dựa vào `ddl-auto=create-drop`.
- Chạy lại các test tồn kho, chuyển tiền, đặt chỗ và deadlock.
- Kiểm tra lock timeout, deadlock exception và transaction isolation.
- Xác nhận CHECK/UNIQUE constraint được tạo đúng và có index cần thiết.
- Kiểm tra connection pool đủ cho mức concurrency của test nhưng không vượt giới hạn database.

Ví dụ H2 ở trên minh họa cấu trúc test và cơ chế JPA. Kết quả cuối cùng cần được xác nhận trên database mục tiêu trước khi xem là bằng chứng cho hành vi production.

## 14. Checklist trước khi phát hành

- [ ] Đã xác định invariant cho tồn kho, số dư và đặt chỗ.
- [ ] Tồn kho dùng conditional UPDATE hoặc cơ chế khóa tương đương; có CHECK `available >= 0`.
- [ ] Chuyển tiền chạy trong một transaction; khóa theo thứ tự nhất quán hoặc dùng `@Version`.
- [ ] Có CHECK constraint ngăn số dư âm nếu quy tắc nghiệp vụ yêu cầu.
- [ ] Ghế/suất đặt có unique constraint phù hợp.
- [ ] Giảm capacity và tạo reservation nằm trong cùng transaction.
- [ ] Mỗi worker test dùng transaction độc lập và không chia sẻ EntityManager.
- [ ] Test tạo contention bằng executor và latch/barrier, không dùng sleep.
- [ ] Test xác minh số thành công và trạng thái cuối trong database.
- [ ] Có timeout cho worker, Future và test runner.
- [ ] Có test cho rollback, optimistic conflict, deadlock và retry nếu ứng dụng dùng các cơ chế đó.
- [ ] Chạy integration test trên cùng loại database với production.

## 15. Nguyên tắc thực hành

- Thiết kế invariant trước khi thiết kế test.
- Để database bảo vệ dữ liệu bằng conditional update, row lock, CHECK và UNIQUE constraint.
- Dùng optimistic locking cho tranh chấp thấp và phát hiện xung đột; dùng pessimistic lock khi cần tuần tự hóa thao tác đọc-sửa-ghi.
- Khóa nhiều hàng theo cùng một thứ tự để giảm deadlock.
- Giữ mọi bước của một nghiệp vụ nguyên tử trong cùng transaction.
- Tạo worker thread riêng và gọi service transactional qua Spring proxy.
- Đồng bộ điểm bắt đầu bằng latch/barrier; không dựa vào sleep.
- Đọc lại database sau khi tất cả transaction kết thúc và kiểm tra invariant.
- Chạy test trên database mục tiêu vì H2 không mô phỏng đầy đủ mọi hành vi khóa production.

Điểm cốt lõi: **Concurrency test phải tạo nhiều transaction độc lập cùng tranh chấp một tài nguyên và kiểm tra invariant sau commit. Tồn kho cần cập nhật có điều kiện nguyên tử, số dư cần khóa hoặc versioning trong transaction, còn đặt chỗ cần unique constraint. Test nhiều thread chỉ có giá trị khi trạng thái cuối trong database vẫn đúng.**