# Điều khiển giao dịch cục bộ bằng EntityTransaction trong JPA

Trong một ứng dụng dùng **Jakarta Persistence (JPA)**, nhiều thay đổi dữ liệu phải được thực hiện như **một đơn vị công việc**: hoặc tất cả được chấp nhận, hoặc không thay đổi nào được cam kết. Ví dụ, khi chuyển 5 sản phẩm từ kho A sang kho B, hệ thống phải giảm tồn kho A **và** tăng tồn kho B. Nếu chỉ một trong hai thay đổi được lưu, dữ liệu tồn kho sẽ sai.

JPA cung cấp giao diện **`EntityTransaction`** để ứng dụng trực tiếp điều khiển những giao dịch kiểu **resource-local** thông qua `EntityManager`. Các phương thức trọng tâm là `begin()`, `commit()`, `rollback()`, `isActive()`, `setRollbackOnly()` và `getRollbackOnly()`.

```java
EntityTransaction tx = entityManager.getTransaction();

tx.begin();
try {
    // Thao tác với các entity đang managed.
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Đây là cấu trúc nền tảng, nhưng để sử dụng đúng trong ứng dụng thật cần hiểu **giao dịch nào là resource-local**, **EntityManager và persistence context có vai trò gì**, **khi nào SQL thực sự chạy**, **commit/rollback tác động ra sao**, và **điều gì xảy ra khi có lỗi hoặc giao dịch cạnh tranh**.

> **Ý chính:** `EntityTransaction` là API **quản lý giao dịch**, không phải API lưu một entity riêng lẻ. `persist()`, dirty checking, `merge()` và `remove()` xác định thay đổi cần làm; `begin()`, `commit()` và `rollback()` xác định **ranh giới cam kết nguyên tử** của các thay đổi đó.

## 1. Giao dịch cục bộ là gì?

**Giao dịch** (*transaction*) là tập hợp thao tác dữ liệu được thực hiện trong một ranh giới thống nhất. Với cơ sở dữ liệu quan hệ, bốn thuộc tính ACID thường được nhắc tới:

| Thuộc tính | Ý nghĩa trong ví dụ chuyển tồn kho |
| --- | --- |
| **Atomicity** (nguyên tử) | Giảm kho A và tăng kho B phải cùng thành công hoặc cùng bị hủy. |
| **Consistency** (nhất quán) | Các ràng buộc dữ liệu phải được duy trì, ví dụ số lượng tồn kho không âm. |
| **Isolation** (cô lập) | Các giao dịch đồng thời được quan sát/điều phối theo mức cô lập do database cung cấp. |
| **Durability** (bền vững) | Khi commit được xác nhận thành công, thay đổi được lưu theo bảo đảm của hệ quản trị database. |

Một **resource-local transaction** được quản lý ở cấp tài nguyên persistence/database gắn với một `EntityManager`. Trong Java SE và nhiều ứng dụng không dùng JTA, ứng dụng tự mở và kết thúc giao dịch bằng `EntityTransaction`.

```text
Ứng dụng Java
    |
    +-- EntityManagerFactory
              |
              +-- EntityManager
                       |
                       +-- Persistence Context
                       |
                       +-- EntityTransaction
                               |
                               +-- begin()
                               +-- commit()
                               +-- rollback()
                                         |
                                         v
                               Giao dịch cơ sở dữ liệu
```

Từ “cục bộ” ở đây **không có nghĩa dữ liệu chỉ nằm ở máy chạy Java**, cũng không có nghĩa ứng dụng không có transaction. Nó nghĩa là **ứng dụng điều khiển giao dịch gắn với một resource-local persistence context**, thay vì dùng một bộ quản lý giao dịch phân tán như JTA.

Một resource-local transaction thông thường **không bảo đảm tính nguyên tử xuyên nhiều tài nguyên độc lập**, chẳng hạn hai database riêng, hoặc một database và message broker. Nếu một yêu cầu phải đồng thời commit vào hai tài nguyên, cần xem xét kiến trúc khác như JTA/XA trong môi trường phù hợp hoặc transactional outbox/saga theo bài toán.

## 2. EntityTransaction được sử dụng khi nào?

JPA phân biệt hai kiểu quản lý giao dịch quan trọng:

- **`RESOURCE_LOCAL`:** ứng dụng lấy `EntityTransaction` từ `EntityManager` và trực tiếp gọi `begin()`, `commit()`, `rollback()`.
- **`JTA`:** giao dịch được điều phối thông qua môi trường/JTA transaction manager; không điều khiển bằng `EntityManager.getTransaction()` như resource-local.

Trong file `META-INF/persistence.xml`, một persistence unit dùng giao dịch cục bộ có thể khai báo:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="inventory-local"
        transaction-type="RESOURCE_LOCAL">

        <class>com.example.inventory.StockBalance</class>

        <properties>
            <property
                name="jakarta.persistence.jdbc.driver"
                value="org.h2.Driver"/>
            <property
                name="jakarta.persistence.jdbc.url"
                value="jdbc:h2:mem:inventory;DB_CLOSE_DELAY=-1"/>
            <property
                name="jakarta.persistence.jdbc.user"
                value="sa"/>
            <property
                name="jakarta.persistence.jdbc.password"
                value=""/>
        </properties>
    </persistence-unit>
</persistence>
```

Cấu hình trên minh họa một persistence unit **RESOURCE_LOCAL** sử dụng H2 in-memory database. Để chạy được, ứng dụng còn cần dependency Jakarta Persistence API, **một JPA provider** triển khai API (ví dụ Hibernate ORM hoặc EclipseLink), driver H2 và bảng dữ liệu tương ứng. Cách tạo schema tự động bằng property của provider có thể khác nhau; không nên mặc định file XML này tự tạo bảng.

Một điểm nên nhớ:

```java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("inventory-local");

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();
```

Ở đây `getTransaction()` phù hợp vì `EntityManager` đến từ persistence unit `RESOURCE_LOCAL`.

Ngược lại, với `EntityManager` gắn vào **JTA persistence context**, gọi `getTransaction()` để tự `begin/commit` là không phù hợp và có thể ném `IllegalStateException`. Cần dùng cơ chế JTA hoặc transaction manager do framework/container cung cấp.

## 3. Vai trò khác nhau của EntityManagerFactory, EntityManager và EntityTransaction

Ba đối tượng có trách nhiệm khác nhau:

| API | Trách nhiệm chính | Vòng đời điển hình |
| --- | --- | --- |
| `EntityManagerFactory` | Tạo `EntityManager`, quản lý cấu hình provider và tài nguyên dùng chung. | Tạo một lần hoặc ít lần cho ứng dụng; đóng khi ứng dụng dừng. |
| `EntityManager` | Quản lý persistence context, entity và truy vấn. | Một đơn vị công việc hoặc một phạm vi được thiết kế rõ; luôn đóng khi không cần. |
| `EntityTransaction` | Điều khiển trạng thái giao dịch resource-local của `EntityManager` tương ứng. | Lấy từ `EntityManager`; dùng để begin/commit/rollback theo từng transaction. |

Ví dụ:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

public final class Application {
    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("inventory-local");

        try {
            EntityManager em = emf.createEntityManager();
            try {
                // EntityManager được dùng trong một đơn vị công việc.
            } finally {
                em.close();
            }
        } finally {
            emf.close();
        }
    }
}
```

**`EntityManagerFactory`** thường được thiết kế để chia sẻ giữa các luồng, còn **`EntityManager` và persistence context không được chia sẻ tùy tiện giữa nhiều thread**. Không nên lưu một `EntityManager` thành singleton toàn hệ thống và cho nhiều request cùng gọi `begin()`/`commit()` trên nó.

Đối tượng `EntityTransaction` gắn với `EntityManager` đã tạo ra nó. Không lấy transaction từ `emA` rồi mong thao tác persist/remove của `emB` tự động được cam kết cùng transaction đó.

## 4. Vòng đời một giao dịch resource-local

Một transaction điển hình:

```text
                 EntityManager mở
                         |
                         v
                    tx.begin()
                         |
                         v
                       ACTIVE
                         |
                  Thao tác entity
                persist / find / update
                   remove / query
                         |
             +-----------+-----------+
             |                       |
      Không có lỗi               Có lỗi / hủy
             |                       |
        tx.commit()              tx.rollback()
             |                       |
             v                       v
       COMMITTED                 ROLLED BACK
             |                       |
             +-----------+-----------+
                         |
                  Đóng EntityManager
```

Một luồng nghiệp vụ có thể có nhiều giao dịch khác nhau, nhưng code phải tránh **begin khi transaction đã hoạt động**, commit khi transaction không hoạt động hoặc tiếp tục dùng persistence context lỗi sau rollback.

Các phương thức:

| Phương thức | Tác dụng |
| --- | --- |
| `begin()` | Bắt đầu giao dịch resource-local. |
| `commit()` | Đồng bộ và cố cam kết thay đổi của giao dịch; lỗi có thể phát sinh tại đây. |
| `rollback()` | Hủy những thay đổi database trong giao dịch đang hoạt động. |
| `isActive()` | Cho biết giao dịch hiện đang hoạt động hay không. |
| `setRollbackOnly()` | Đánh dấu giao dịch đang hoạt động là **chỉ được rollback**, không được commit thành công. |
| `getRollbackOnly()` | Kiểm tra giao dịch đang hoạt động đã bị đánh dấu rollback-only hay chưa. |

**`EntityTransaction` không có `save()`, `delete()` hay `find()`**. Những thao tác entity thuộc `EntityManager`; transaction chỉ xác định ranh giới của chúng.

## 5. begin(): bắt đầu giao dịch

```java
EntityTransaction tx = em.getTransaction();

tx.begin();
```

Sau khi `begin()` thành công, resource-local transaction đang ở trạng thái active. Các thay đổi JPA được thực hiện trong phạm vi đó có thể được đồng bộ rồi commit hoặc rollback như một đơn vị công việc.

Kiểm tra trạng thái:

```java
EntityTransaction tx = em.getTransaction();

System.out.println(tx.isActive()); // false trước begin, thông thường

tx.begin();

System.out.println(tx.isActive()); // true
```

Nếu gọi `begin()` khi transaction đã active, JPA có thể ném `IllegalStateException`. Không nên giả định rằng hai lần `begin()` tạo **nested transaction**.

```java
tx.begin();
tx.begin(); // Không tạo transaction lồng nhau hợp lệ.
```

JPA `EntityTransaction` **không cung cấp API chuẩn cho transaction lồng nhau hoặc savepoint**. Nếu nghiệp vụ cần một phần công việc có thể hoàn tác riêng, phải thiết kế transaction boundary, sử dụng khả năng database/JDBC theo hướng có kiểm soát, hoặc một phương án khác phù hợp provider/framework; không tự gọi `begin()` lần thứ hai.

### 5.1. Có cần begin trước find() không?

Một số thao tác đọc có thể chạy ngoài transaction trong những cấu hình phù hợp. Nhưng với luồng **đọc rồi cập nhật** cần một quyết định nhất quán, nên mở transaction trước khi tải và thay đổi entity:

```java
tx.begin();

StockBalance balance = em.find(StockBalance.class, balanceId);
balance.changeQuantity(newQuantity);

tx.commit();
```

Điều này giúp logic kiểm tra điều kiện, sửa entity và commit nằm trong một ranh giới transaction rõ ràng. Không nên hiểu rằng việc mở transaction tự động cung cấp mức isolation cao nhất; các vấn đề lost update, phantom read và lock vẫn cần xử lý theo yêu cầu nghiệp vụ.

## 6. commit(): đồng bộ và cam kết

```java
tx.begin();

em.persist(entity);

tx.commit();
```

`commit()` yêu cầu kết thúc giao dịch bằng cam kết. Trước hoặc trong quá trình commit, provider thường đồng bộ những thay đổi còn đang chờ trong persistence context xuống database.

Ví dụ có hai entity managed:

```java
tx.begin();

StockBalance from = em.find(StockBalance.class, fromId);
StockBalance to = em.find(StockBalance.class, toId);

from.decrease(5);
to.increase(5);

tx.commit();
```

Nếu commit thành công, cả hai thay đổi được cam kết theo transaction. Nếu một lệnh SQL thất bại hoặc optimistic locking conflict xảy ra, transaction có thể rollback và commit ném ngoại lệ.

**Không nên trả “đã lưu thành công” ngay sau `persist()` hoặc ngay sau khi sửa field Java**. Hãy xem transaction boundary và kết quả commit là dấu mốc nghiệp vụ quan trọng.

### 6.1. SQL có thể chạy trước commit

Dirty checking thường khiến SQL `UPDATE` xuất hiện tại flush hoặc commit, nhưng không có quy tắc rằng SQL chỉ chạy đúng lúc `commit()`:

- `GenerationType.IDENTITY` có thể khiến provider cần `INSERT` sớm để lấy khóa chính.
- `em.flush()` yêu cầu đồng bộ thay đổi ngay trong transaction.
- Flush mode `AUTO` có thể khiến provider flush trước truy vấn nhất định để bảo đảm ngữ nghĩa kết quả.
- Provider có thể tối ưu cách và thời điểm phát lệnh SQL tùy mapping.

Điều bất biến cần ghi nhớ là: **SQL đã thực thi trong transaction vẫn chưa nhất thiết được commit**.

### 6.2. Commit có thể thất bại muộn

Ví dụ:

```java
tx.begin();

em.persist(new StockBalance(...));

// Có thể chưa thấy lỗi ở persist().
tx.commit(); // Lỗi UNIQUE, FK, CHECK, locking... có thể xuất hiện ở đây.
```

Nếu database từ chối một constraint hoặc provider phát hiện xung đột, `commit()` có thể ném `RollbackException` hay một ngoại lệ persistence liên quan.

Ứng dụng cần xử lý cả lỗi ở `begin()`, thao tác entity, `flush()` và **`commit()`**, không chỉ bọc riêng `persist()` trong `try/catch`.

## 7. rollback(): hoàn tác thay đổi của giao dịch

```java
tx.begin();

try {
    // Thực hiện các thay đổi.
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

`rollback()` yêu cầu hủy thay đổi database của **transaction đang hoạt động**. Nó rất quan trọng khi:

- Validation nghiệp vụ không cho phép tiếp tục.
- Một câu SQL hoặc constraint thất bại.
- Có lỗi optimistic/pessimistic locking.
- Các thay đổi đã flush nhưng một bước sau đó thất bại.
- Ứng dụng chủ động quyết định không cam kết đơn vị công việc.

Ví dụ chuyển tồn kho: nếu kho A đã bị giảm 5 đơn vị trong transaction nhưng kho B không thể được cập nhật, rollback giúp không để database chỉ phản ánh một nửa việc chuyển.

### 7.1. Rollback không xóa object Java

`rollback()` không tự biến mọi field của managed entity trở về trạng thái ban đầu như một bản sao sạch trong bộ nhớ.

```text
Database đầu giao dịch: A=20, B=10
Java trong transaction: A=15, B=15
SQL đã flush:          A=15, B=15 (chưa commit)
rollback()
Database sau rollback: A=20, B=10

Java object cũ có thể không còn phản ánh chính xác trạng thái DB.
```

Sau rollback, JPA quy định phạm vi sử dụng/độ tin cậy của managed entities bị ảnh hưởng cần được xem xét cẩn thận. Cách thực hành an toàn với application-managed EntityManager là **đóng EntityManager của đơn vị công việc lỗi**, rồi nạp dữ liệu mới trong một EntityManager/transaction khác.

Không tiếp tục dùng object có ID hoặc version sinh trong transaction đã rollback như thể nó chắc chắn đại diện cho bản ghi đã commit.

### 7.2. Rollback sau flush vẫn có ý nghĩa

```java
tx.begin();

from.decrease(5);
em.flush(); // SQL UPDATE có thể đã chạy.

to.increase(5);

// Một điều kiện nghiệp vụ thất bại.
tx.rollback();
```

Trừ khi có một hành vi ngoại lệ từ hệ thống bên ngoài transaction, các thay đổi database của transaction chưa commit được hoàn tác. **Flush không phải commit**.

### 7.3. Rollback không tự hủy các tác dụng bên ngoài database

Một transaction resource-local của JPA không tự rollback:

- Email đã gửi.
- HTTP request đến hệ thống khác.
- Message đã gửi đến broker không tham gia cùng transaction.
- File đã ghi lên ổ đĩa.
- Thanh toán đã được thực thi bởi dịch vụ ngoài.

Vì thế, không nên gửi thông báo “chuyển kho thành công” trước khi commit và cho rằng `rollback()` sẽ thu hồi được email/message ấy.

Nếu cần phát sự kiện đáng tin cậy sau commit, cân nhắc **transactional outbox** hoặc một cơ chế điều phối phù hợp. Đây là vấn đề kiến trúc giao dịch, không có API `EntityTransaction` nào tự giải quyết toàn bộ hệ thống phân tán.

## 8. Mẫu xử lý exception bảo vệ rollback

Một mẫu đầy đủ hơn không chỉ rollback khi lỗi nghiệp vụ mà còn giữ lại thông tin nếu chính rollback cũng gặp lỗi.

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class TransactionBoundary {
    private final EntityManagerFactory factory;

    public TransactionBoundary(EntityManagerFactory factory) {
        this.factory = factory;
    }

    public void execute() {
        EntityManager em = factory.createEntityManager();
        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                // Thực hiện nghiệp vụ trong transaction.
                // Ví dụ: em.persist(entity), sửa managed entity...

                tx.commit();
            } catch (RuntimeException originalError) {
                try {
                    if (tx.isActive()) {
                        tx.rollback();
                    }
                } catch (RuntimeException rollbackError) {
                    originalError.addSuppressed(rollbackError);
                }
                throw originalError;
            }
        } finally {
            em.close();
        }
    }
}
```

Ý nghĩa của cấu trúc:

1. `EntityManager` được tạo cho đơn vị công việc và **đóng trong `finally`**.
2. `begin()` nằm bên trong phần được bắt lỗi.
3. Nếu thao tác, flush hoặc commit ném `RuntimeException`, code thử rollback **khi transaction vẫn active**.
4. Nếu rollback cũng lỗi, ngoại lệ rollback được gắn làm *suppressed exception* để không che mất lỗi đầu tiên.
5. Ngoại lệ gốc được ném lại; tầng ngoài có trách nhiệm log/xử lý đúng loại lỗi.

Mẫu trên minh họa các lỗi runtime thông thường. Trong hệ thống production, còn cần chính sách riêng cho lỗi hạ tầng nghiêm trọng và việc đóng EntityManager; không nên biến `catch (RuntimeException)` thành cách **nuốt lỗi rồi trả thành công**.

### 8.1. Vì sao kiểm tra isActive()?

Sau một lỗi commit, provider hoặc transaction manager có thể đã tự kết thúc giao dịch hoặc rollback. Gọi `rollback()` khi transaction không còn active có thể ném `IllegalStateException`.

```java
if (tx.isActive()) {
    tx.rollback();
}
```

Điều kiện này tránh gọi rollback mù quáng trong tình huống transaction đã kết thúc. Nhưng `isActive()` không phải bằng chứng transaction có thể tiếp tục sử dụng sau một lỗi DB; nó chỉ nói về trạng thái active ở thời điểm kiểm tra.

### 8.2. Không tiếp tục commit sau lỗi persistence nghiêm trọng

Một số ngoại lệ persistence có thể khiến transaction bị đánh dấu **rollback-only** hoặc database transaction không còn hợp lệ. Không nên:

```java
try {
    em.persist(entity);
} catch (PersistenceException ex) {
    // Ghi log rồi bỏ qua.
}
tx.commit(); // Không nên mặc định có thể commit.
```

Nếu một phần thao tác đã lỗi, chính sách an toàn thông thường là rollback **cả đơn vị công việc**, sửa dữ liệu/điều kiện, rồi thực hiện lại bằng transaction mới khi hợp lệ.

## 9. setRollbackOnly() và getRollbackOnly()

Có những lúc code muốn **đánh dấu một transaction không được phép commit** mà chưa muốn ném exception ngay ở vị trí đánh dấu.

`EntityTransaction` cung cấp:

```java
tx.setRollbackOnly();
boolean mustRollback = tx.getRollbackOnly();
```

`setRollbackOnly()` dùng khi transaction đang active và nghiệp vụ xác định transaction này phải hủy. Sau đó:

```java
tx.begin();

try {
    // Một điều kiện nghiệp vụ xác định toàn bộ giao dịch phải hủy.
    tx.setRollbackOnly();

    System.out.println(tx.getRollbackOnly()); // true

    // Không nên coi tx.commit() là thao tác có thể thành công.
    tx.rollback();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Nếu gọi `commit()` trên transaction đã đánh dấu rollback-only, giao dịch không được commit thành công; provider sẽ rollback và có thể báo `RollbackException`.

### 9.1. Khi nào nên dùng setRollbackOnly?

Nó hữu ích khi một thành phần bên trong luồng xử lý muốn báo rằng **transaction hiện tại không thể commit**, trong khi tầng gọi cần thêm xử lý để trả thông điệp nghiệp vụ.

Tuy nhiên, với một yêu cầu resource-local đơn giản, code thường dễ hiểu hơn nếu **ném exception nghiệp vụ** rồi để transaction boundary ở ngoài rollback:

```java
if (from.getQuantity() < amount) {
    throw new IllegalArgumentException("Not enough stock");
}
```

Chỉ dùng `setRollbackOnly()` khi thật sự cần cơ chế đánh dấu này. Tránh trộn lẫn những nhánh vừa gọi `setRollbackOnly()` vừa tiếp tục xử lý như thể giao dịch sẽ thành công.

### 9.2. Các phương thức trạng thái yêu cầu transaction active

`setRollbackOnly()` và `getRollbackOnly()` được dùng trên transaction đang hoạt động. Không nên gọi chúng trước `begin()` hoặc sau `commit()/rollback()` rồi kỳ vọng có trạng thái hợp lệ; JPA có thể ném `IllegalStateException`.

Với code cần biết có transaction không, hãy kiểm tra `isActive()` trước.

## 10. Ví dụ thực tế: chuyển số lượng giữa hai kho

Xét một ứng dụng quản lý tồn kho. Mỗi hàng `StockBalance` lưu tồn kho của một mã sản phẩm tại một kho.

```text
Warehouse 10: SKU-KEYBOARD quantity = 20
Warehouse 20: SKU-KEYBOARD quantity = 8

Yêu cầu: chuyển 5 sản phẩm từ kho 10 sang kho 20.

Kỳ vọng sau transaction:
Warehouse 10: quantity = 15
Warehouse 20: quantity = 13
```

Nếu giảm kho nguồn thành công nhưng không tăng kho đích, tổng tồn kho của hai kho bị sai. Đây là một bài toán tự nhiên để minh họa tính nguyên tử của transaction.

### 10.1. Schema database

```sql
CREATE TABLE stock_balances (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    warehouse_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT uq_stock_warehouse_sku
        UNIQUE (warehouse_id, sku),
    CONSTRAINT ck_stock_quantity
        CHECK (quantity >= 0)
);
```

Schema dùng khóa `id` riêng, đồng thời buộc mỗi `(warehouse_id, sku)` chỉ có một hàng. `@Version` ở entity giúp phát hiện việc nhiều transaction cùng thay đổi một số dư tồn kho.

### 10.2. Entity StockBalance

```java
package com.example.inventory;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;

@Entity
@Table(
    name = "stock_balances",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_stock_warehouse_sku",
        columnNames = {"warehouse_id", "sku"}
    )
)
public class StockBalance {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "warehouse_id", nullable = false)
    private Long warehouseId;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false)
    private Integer quantity;

    @Version
    @Column(nullable = false)
    private Long version;

    protected StockBalance() {
    }

    public StockBalance(Long warehouseId, String sku, int quantity) {
        if (warehouseId == null || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Invalid stock key");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("Negative quantity");
        }
        this.warehouseId = warehouseId;
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public Long getWarehouseId() {
        return warehouseId;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public Long getVersion() {
        return version;
    }

    public void decrease(int amount) {
        if (amount <= 0 || quantity < amount) {
            throw new IllegalArgumentException(
                "Invalid amount or insufficient stock"
            );
        }
        quantity -= amount;
    }

    public void increase(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException(
                "Amount must be positive"
            );
        }
        quantity = Math.addExact(quantity, amount);
    }
}
```

Class trên là một entity độc lập, có constructor không tham số cho JPA, khóa sinh tự động và version. `Math.addExact` giúp phát hiện overflow của số nguyên thay vì âm thầm vượt giới hạn `Integer`.

### 10.3. Service chuyển tồn kho bằng EntityTransaction

```java
package com.example.inventory;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import java.util.Objects;

public final class StockTransferService {
    private final EntityManagerFactory factory;

    public StockTransferService(EntityManagerFactory factory) {
        this.factory = Objects.requireNonNull(factory);
    }

    public void transfer(long sourceId, long targetId, int amount) {
        if (sourceId == targetId) {
            throw new IllegalArgumentException(
                "Source and target must be different"
            );
        }
        if (amount <= 0) {
            throw new IllegalArgumentException(
                "Amount must be positive"
            );
        }

        EntityManager em = factory.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                StockBalance source =
                    em.find(StockBalance.class, sourceId);
                StockBalance target =
                    em.find(StockBalance.class, targetId);

                if (source == null || target == null) {
                    throw new IllegalArgumentException(
                        "Source or target balance not found"
                    );
                }

                if (!source.getSku().equals(target.getSku())) {
                    throw new IllegalArgumentException(
                        "Both balances must have the same SKU"
                    );
                }

                source.decrease(amount);
                target.increase(amount);

                // Cả hai entity đang managed.
                // JPA dùng dirty checking khi flush/commit.
                tx.commit();
            } catch (RuntimeException error) {
                try {
                    if (tx.isActive()) {
                        tx.rollback();
                    }
                } catch (RuntimeException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        } finally {
            em.close();
        }
    }
}
```

Những điểm quan trọng trong ví dụ:

- `transfer()` tạo **một EntityManager**, từ đó lấy **một EntityTransaction**.
- `source` và `target` được tải trong **cùng transaction**, tạo thành hai managed entity thuộc cùng persistence context.
- Phương thức nghiệp vụ kiểm tra điều kiện trước khi commit.
- Code **không gọi `persist(source)` hoặc `persist(target)`**, vì đây là các entity đã tồn tại và đang managed.
- JPA nhận diện thay đổi `quantity` bằng dirty checking rồi phát SQL khi flush/commit.
- Nếu validation hoặc SQL thất bại, nhánh catch cố rollback giao dịch.
- Nếu commit thành công, cả hai thay đổi thuộc cùng một transaction được cam kết.

Ví dụ không có logic tạo StockBalance mới khi kho đích chưa có SKU; nếu nghiệp vụ cần điều đó, phải tạo hàng mới, giải quyết unique constraint và concurrency của thao tác “tìm hoặc chèn” riêng.

### 10.4. Luồng SQL minh họa

Giả sử source và target đều có `version = 0`:

```sql
SELECT id, warehouse_id, sku, quantity, version
FROM stock_balances WHERE id = ?;

SELECT id, warehouse_id, sku, quantity, version
FROM stock_balances WHERE id = ?;

UPDATE stock_balances
SET quantity = 15, version = 1
WHERE id = ? AND version = 0;

UPDATE stock_balances
SET quantity = 13, version = 1
WHERE id = ? AND version = 0;
```

Đây là SQL minh họa cho cách provider có thể kiểm tra optimistic locking. Thứ tự và hình dạng câu SQL thực tế tùy provider, dialect, batch settings và trạng thái entity.

Nếu câu UPDATE thứ hai thất bại và transaction rollback, câu UPDATE thứ nhất cũng không được commit. **Đó là lợi ích trực tiếp của việc đặt hai thay đổi trong cùng transaction resource-local.**

## 11. Tạo dữ liệu ban đầu và bảo đảm transaction cho persist()

Ví dụ tạo hai hàng tồn kho:

```java
EntityManager em = factory.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        StockBalance source =
            new StockBalance(10L, "SKU-KEYBOARD", 20);

        StockBalance target =
            new StockBalance(20L, "SKU-KEYBOARD", 8);

        em.persist(source);
        em.persist(target);

        tx.commit();

        System.out.println(source.getId());
        System.out.println(target.getId());
    } catch (RuntimeException error) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw error;
    }
} finally {
    em.close();
}
```

Khi gọi `em.persist(source)`, entity mới được đưa vào persistence context. Với generator `IDENTITY`, provider có thể cần thực hiện `INSERT` sớm để lấy ID. Nhưng **ID đã được cấp không phải bằng chứng rằng transaction đã commit**.

Nếu transaction rollback, hàng vừa chèn không được cam kết. Một giá trị ID đã được cấp trước đó có thể không được tái sử dụng và có thể vẫn nằm trong object Java. Không nên tự lấy ID đó làm dấu hiệu “đã lưu bền vững”.

### 11.1. Entity mới, managed và detached

| Tình huống | Thao tác JPA thường dùng | Giao dịch resource-local |
| --- | --- | --- |
| Entity mới | `em.persist(entity)` | Cần transaction phù hợp để ghi bền vững. |
| Entity đã managed và sửa field | Sửa field, dirty checking | Flush/commit trong transaction. |
| Entity detached cần đồng bộ | `managed = em.merge(detached)` | Merge trong transaction, dùng instance trả về. |
| Entity managed cần xóa | `em.remove(entity)` | Xóa được thực thi qua flush/commit. |
| Entity không tồn tại khi tìm | `em.find(...) == null` | Quyết định trả lỗi/no-op theo nghiệp vụ. |

`merge()` không biến chính object detached đầu vào thành managed. Nó trả về một instance managed có trạng thái được sao chép theo quy tắc JPA. Khi cần tiếp tục thao tác, sử dụng giá trị trả về và giữ ranh giới transaction hợp lệ.

## 12. flush() trong EntityTransaction

`EntityTransaction` không có phương thức `flush()`. Để ép đồng bộ trạng thái entity với database trong transaction, gọi trên `EntityManager`:

```java
tx.begin();

StockBalance stock = em.find(StockBalance.class, stockId);
stock.decrease(3);

em.flush(); // Gửi những thay đổi đang chờ xuống database.

tx.commit();
```

So sánh:

| Hành động | Tác dụng chính |
| --- | --- |
| `em.persist(entity)` | Làm entity mới trở thành managed, lên lịch lưu theo JPA. |
| Sửa thuộc tính của managed entity | Thay đổi trong Java được provider theo dõi. |
| `em.flush()` | Đồng bộ các thay đổi đang chờ của persistence context xuống database trong transaction. |
| `tx.commit()` | Yêu cầu kết thúc giao dịch và cam kết thay đổi; có thể phát sinh flush. |
| `tx.rollback()` | Hủy thay đổi database của transaction chưa commit. |

### 12.1. Khi nào cần flush chủ động?

`flush()` có thể hữu ích nếu:

- Muốn phát hiện lỗi constraint trước khi thực hiện các bước tiếp theo.
- Cần giá trị được database tính bằng trigger/generated column sau SQL.
- Cần bảo đảm database đã nhận một thay đổi trước khi chạy native SQL phụ thuộc vào nó.
- Cần kiểm tra một số điều kiện dựa trên dữ liệu đã đồng bộ.

Tuy nhiên, flush **đồng bộ những thay đổi đang chờ trong persistence context**, không chỉ riêng entity mà đoạn code vừa sửa. Do đó gọi flush quá sớm có thể khiến nhiều SQL chạy, gây lock và lỗi trước thời điểm mong muốn.

### 12.2. FlushModeType.AUTO và COMMIT

JPA có `FlushModeType`:

```java
em.setFlushMode(
    jakarta.persistence.FlushModeType.AUTO
);
```

- `AUTO`: provider bảo đảm ngữ nghĩa truy vấn phù hợp với thay đổi pending; có thể flush trước một số truy vấn.
- `COMMIT`: tập trung đồng bộ vào lúc commit; tác động của những thay đổi chưa flush lên kết quả truy vấn trong transaction có giới hạn theo hợp đồng JPA.

Không nên dùng `FlushModeType.COMMIT` như cách bảo đảm rằng ứng dụng sẽ không ghi SQL trước commit trong mọi hoàn cảnh, đặc biệt với IDENTITY hoặc provider-specific behavior.

**Không có flush mode nào thay thế quyền kiểm soát commit/rollback của `EntityTransaction`.**

## 13. Transaction isolation và lỗi dữ liệu đồng thời

`EntityTransaction` cung cấp cách bắt đầu/kết thúc transaction, nhưng **không tự cho phép chọn mọi mức isolation** bằng một phương thức chuẩn như `tx.setIsolationLevel(...)`.

Các mức isolation thường gặp của database:

| Mức isolation | Ý nghĩa khái quát |
| --- | --- |
| `READ UNCOMMITTED` | Có thể cho phép đọc dữ liệu chưa commit ở một số DBMS. |
| `READ COMMITTED` | Tránh dirty read; hai lần đọc có thể thấy dữ liệu khác nếu transaction khác commit. |
| `REPEATABLE READ` | Thường bảo vệ các lần đọc lặp lại tốt hơn; thực thi cụ thể tùy DBMS/MVCC. |
| `SERIALIZABLE` | Mức cô lập mạnh, các giao dịch được điều phối như một lịch thực thi tuần tự về mặt kết quả; có thể gây chờ khóa hoặc serialization failure. |

Mức isolation được cấu hình qua database, connection pool, datasource hoặc tính năng provider/framework tương ứng; `EntityTransaction` không định nghĩa một API portable đầy đủ để đặt nó cho từng giao dịch.

### 13.1. Lost update

Giả sử hai request cùng lấy tồn kho 20 và mỗi request muốn trừ 5:

```text
Transaction A                  Transaction B
-------------                  -------------
Đọc quantity=20
                               Đọc quantity=20
Sửa quantity=15
                               Sửa quantity=15
Commit
                               Commit
```

Nếu không có biện pháp concurrency phù hợp, kết quả có thể chỉ còn 15 thay vì 10. Một resource-local transaction **không tự loại bỏ mọi lost update**.

Trong `StockBalance`, `@Version` hỗ trợ optimistic locking:

```java
@Version
private Long version;
```

Provider có thể kiểm tra version cũ khi cập nhật. Nếu hai transaction cùng thay đổi hàng dựa trên phiên bản cũ, transaction tới sau có thể gặp `OptimisticLockException` hoặc lỗi liên quan tại flush/commit.

### 13.2. Xử lý optimistic locking

Một chiến lược phổ biến:

1. Rollback transaction bị xung đột.
2. Đóng EntityManager cũ.
3. Tạo EntityManager và transaction mới.
4. Tải lại dữ liệu mới nhất theo isolation phù hợp.
5. Chạy lại **toàn bộ đơn vị nghiệp vụ** nếu hành động có thể retry an toàn, hoặc báo xung đột cho caller.

Không nên chỉ bắt `OptimisticLockException` rồi gọi `tx.commit()` lần nữa trên transaction đã lỗi. Cũng không nên retry vô hạn hoặc tự coi xung đột là thành công.

### 13.3. Pessimistic locking khi cần

JPA có thể yêu cầu khóa khi tải entity:

```java
StockBalance source = em.find(
    StockBalance.class,
    sourceId,
    jakarta.persistence.LockModeType.PESSIMISTIC_WRITE
);
```

Trong một transaction hợp lệ, provider yêu cầu database lock phù hợp. Tùy DBMS và provider, có thể phát sinh `PessimisticLockException` hoặc `LockTimeoutException` nếu không lấy được khóa.

Khi chuyển giữa nhiều hàng, thứ tự lấy lock nhất quán có thể giúp giảm một số deadlock. Tuy nhiên, khóa pessimistic làm tăng độ tranh chấp và thời gian chờ; chỉ sử dụng khi yêu cầu nhất quán và mô hình tải thực sự cần.

### 13.4. Version không bảo vệ mọi invariant xuyên nhiều hàng

`@Version` trên `StockBalance` giúp phát hiện sửa **cùng một hàng**. Nhưng một ràng buộc như “tổng số hàng trong một kho không vượt sức chứa” có thể liên quan nhiều row. Hai transaction cùng thêm các SKU khác nhau có thể không xung đột version trên một hàng nào.

Cần một cách khóa/kiểm tra constraint ở mức aggregate hoặc database phù hợp. **Một transaction resource-local là nền tảng nguyên tử, không phải lời hứa tự bảo vệ mọi quy tắc nghiệp vụ đồng thời.**

## 14. Khi nào transaction được đánh dấu rollback-only?

Một transaction đang active có thể không còn được phép commit nếu:

- Ứng dụng gọi `tx.setRollbackOnly()`.
- Provider đánh dấu rollback-only do một lỗi persistence nghiêm trọng theo quy tắc JPA.
- Transaction manager/database không thể tiếp tục hoàn tất đơn vị công việc.

Ví dụ:

```java
tx.begin();

try {
    StockBalance source = em.find(StockBalance.class, sourceId);

    if (source.getQuantity() < amount) {
        tx.setRollbackOnly();
        // Tầng gọi cần trả lỗi/rollback, không nên commit.
    }

    if (tx.getRollbackOnly()) {
        tx.rollback();
        return;
    }

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Đoạn trên minh họa ý nghĩa của rollback-only; trong ứng dụng thực tế, nếu không đủ tồn kho thường **ném exception nghiệp vụ** sẽ đơn giản hơn. Ngoài ra phải kiểm tra `source != null` và tham số đầu vào trước khi dùng; ví dụ này giả định hàng đã tồn tại để chỉ tập trung vào `setRollbackOnly`.

Nếu một tầng nghiệp vụ tự đánh dấu rollback-only, tầng ngoài phải biết rằng **không thể báo thành công ở commit**. Đừng “bắt hết exception và vẫn trả HTTP 200” chỉ vì code không bị dừng ngay tại lúc đánh dấu.

## 15. Resource-local khác JTA như thế nào?

Đây là khác biệt cần hiểu trước khi chọn `EntityTransaction`.

| Đặc điểm | RESOURCE_LOCAL + EntityTransaction | JTA / container-managed transaction |
| --- | --- | --- |
| Ai bắt đầu/kết thúc? | Ứng dụng gọi `begin`, `commit`, `rollback`. | Transaction manager/framework/container điều phối. |
| Tạo EntityManager | Thường `EntityManagerFactory.createEntityManager()`. | Có thể được inject/quản lý bởi container; context scope theo môi trường. |
| API transaction điển hình | `em.getTransaction()`. | `UserTransaction`, `@Transactional`, EJB CMT hoặc API framework phù hợp. |
| Phạm vi tài nguyên | Thường một persistence/database resource theo resource-local. | Có thể tham gia quản lý transaction liên nhiều tài nguyên khi hệ thống hỗ trợ, nhưng không mặc định mọi tài nguyên đều là XA. |
| Có được gọi `em.getTransaction().begin()`? | Có, khi unit là RESOURCE_LOCAL. | Không dùng theo cách này trên JTA EntityManager. |
| Trường hợp phổ biến | Java SE, batch job độc lập, ứng dụng tự quản lý transaction. | Jakarta EE, ứng dụng dùng JTA transaction manager, các môi trường container-managed. |

### 15.1. Java SE resource-local

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

tx.begin();
try {
    // Công việc cần transaction.
    tx.commit();
} catch (RuntimeException e) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw e;
} finally {
    em.close();
}
```

### 15.2. Container-managed JTA

Trong một ứng dụng Jakarta EE có transaction do container quản lý, code có thể:

```java
import jakarta.ejb.Stateless;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Stateless
public class InventoryService {

    @PersistenceContext
    private EntityManager em;

    public void updateStock(long id, int amount) {
        StockBalance stock = em.find(StockBalance.class, id);
        stock.increase(amount);
        // Container quản lý transaction theo cấu hình.
    }
}
```

Đây là **mô hình thay thế**, không chạy cùng kiểu resource-local tự begin/commit trong một phương thức. Trong một EJB stateless có transaction attribute mặc định phù hợp, container thiết lập transaction cho lời gọi. Không tự gọi `em.getTransaction().commit()`.

### 15.3. Spring @Transactional

Trong Spring Data JPA, service thường viết:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StockApplicationService {
    private final StockBalanceRepository balances;

    public StockApplicationService(StockBalanceRepository balances) {
        this.balances = balances;
    }

    @Transactional
    public void decrease(Long id, int amount) {
        StockBalance stock = balances.findById(id)
            .orElseThrow();

        stock.decrease(amount);
    }
}
```

`StockBalanceRepository` ở đây giả định là repository đã được định nghĩa và inject. Spring dùng một `PlatformTransactionManager` được cấu hình để bắt đầu/kết thúc giao dịch, có thể là `JpaTransactionManager` với tài nguyên cục bộ hoặc một JTA transaction manager trong kiến trúc khác.

**`@Transactional` không đồng nghĩa mọi Spring application đều dùng JTA.** Nó là một cách khai báo transaction boundary; bên dưới có thể vẫn là resource-local database transaction. Điều quan trọng là **không vừa để Spring quản lý transaction, vừa tự ý `getTransaction().begin()` trên EntityManager đang được Spring quản lý**.

## 16. Dùng EntityTransaction trong một helper tái sử dụng

Nếu nhiều service Java SE cùng cần pattern begin/commit/rollback/close, có thể trích một transaction helper.

```java
package com.example.inventory;

import java.util.Objects;
import java.util.function.Function;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class LocalTransactions {
    private final EntityManagerFactory factory;

    public LocalTransactions(EntityManagerFactory factory) {
        this.factory = Objects.requireNonNull(factory);
    }

    public <T> T execute(Function<EntityManager, T> work) {
        EntityManager em = factory.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                T result = work.apply(em);

                tx.commit();
                return result;
            } catch (RuntimeException error) {
                try {
                    if (tx.isActive()) {
                        tx.rollback();
                    }
                } catch (RuntimeException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        } finally {
            em.close();
        }
    }
}
```

Sử dụng:

```java
LocalTransactions transactions =
    new LocalTransactions(entityManagerFactory);

Integer remaining = transactions.execute(em -> {
    StockBalance stock = em.find(StockBalance.class, 10L);
    if (stock == null) {
        throw new IllegalArgumentException("Stock not found");
    }
    stock.decrease(2);
    return stock.getQuantity();
});
```

Điểm lợi:

- Transaction boundary có **một nơi quản lý lỗi**.
- Caller tập trung vào logic domain.
- Mỗi lời gọi dùng **một EntityManager** mới.
- Kết quả trả về chỉ sau khi `commit()` hoàn tất thành công.

Nhưng cần nhớ một số giới hạn:

- Không gọi `execute()` lồng nhau rồi mặc định hai lần sẽ chia sẻ cùng một transaction; helper tạo **EntityManager/transaction mới** cho mỗi lần.
- Đừng trả ra một managed entity rồi kỳ vọng nó vẫn được quản lý sau khi helper đóng EntityManager. Lúc đó entity trả ra trở thành **detached**.
- Không dùng helper cho thao tác vừa ghi DB vừa gọi dịch vụ ngoài mà chưa thiết kế cơ chế xử lý side effect.
- Nếu `work.apply` cần ném checked exception, phải thiết kế functional interface/chính sách exception riêng thay vì cố che lỗi.

Nếu code có nhiều lớp service cần tham gia **cùng một transaction**, hãy truyền cùng `EntityManager` qua tầng nghiệp vụ hoặc dùng framework transaction manager thích hợp; không tạo helper độc lập ở mỗi repository rồi cho rằng chúng sẽ tự kết hợp thành một đơn vị nguyên tử.

## 17. Phạm vi EntityManager và transaction không giống nhau

Một `EntityManager` application-managed có thể còn mở sau `tx.commit()`:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

tx.begin();
// ...
tx.commit();

// EntityManager vẫn có thể đang mở.
boolean open = em.isOpen();

em.close();
```

**Commit kết thúc transaction, không tự đóng EntityManager.**

Điều này rất quan trọng với persistence context:

- Các entity có thể vẫn được managed nếu EntityManager còn mở, theo vòng đời context.
- Trạng thái vừa commit không nhất thiết được tự làm mới nếu transaction khác sửa database sau đó.
- Tải lazy association ngoài transaction có những giới hạn và hành vi phụ thuộc provider/runtime.
- Tái sử dụng EntityManager quá lâu có thể làm context tích lũy nhiều managed entity, tốn bộ nhớ và tạo stale state.

Trong Java SE, nhiều ứng dụng chọn **một EntityManager cho một đơn vị công việc**, đóng sau commit/rollback. Không phải quy tắc JPA bắt buộc mọi trường hợp, nhưng thường giúp quản lý trạng thái và tài nguyên rõ ràng.

### 17.1. Sau rollback nên kết thúc context lỗi

Dù EntityManager object có thể vẫn báo `isOpen() == true` sau một lỗi transaction, **không nên mặc định rằng mọi managed instance còn đáng tin**. Code thường nên đóng context, nạp lại state ở transaction mới, và không tái sử dụng entity đã bị thay đổi/đánh dấu xóa trong giao dịch lỗi.

### 17.2. Một EntityManager không dùng đồng thời nhiều thread

`EntityManager` không được thiết kế để chia sẻ không kiểm soát giữa các luồng. Nếu hai request cùng thao tác `tx.begin()` trên một instance, bạn có thể gặp transaction already active, race condition và sự pha trộn persistence contexts.

`EntityManagerFactory` là nơi phù hợp để chia sẻ; mỗi thread/request tạo EntityManager riêng hoặc sử dụng cách quản lý của framework/container.

## 18. Xử lý lỗi ràng buộc và trạng thái không tồn tại

Với transaction resource-local, các lỗi thường gặp gồm:

| Tình huống | Hậu quả có thể | Cách xử lý |
| --- | --- | --- |
| `persist()` trùng unique key | Lỗi constraint ở insert/flush/commit. | Rollback, trả lỗi nghiệp vụ phù hợp, tránh cố commit lại. |
| Cập nhật bị optimistic conflict | `OptimisticLockException` hoặc ngoại lệ transaction. | Rollback, tải lại và quyết định retry/báo conflict. |
| `find()` trả `null` | Entity không tìm thấy theo context/điều kiện truy vấn. | Ném exception nghiệp vụ hoặc trả no-op theo hợp đồng. |
| Xóa cha khi còn child bị FK bảo vệ | Constraint violation tại flush/commit. | Chọn chặn xóa, xử lý con, cascade đúng domain hoặc soft delete. |
| Gọi `commit()` khi chưa `begin()` | Trạng thái giao dịch không hợp lệ, có thể `IllegalStateException`. | Quản lý transaction boundary rõ ràng. |
| Gọi `begin()` hai lần | Transaction đã active. | Không dùng begin lồng nhau trên cùng transaction. |
| Transaction bị đánh dấu rollback-only | Commit không được thành công. | Rollback và báo lỗi phù hợp. |
| Lỗi mạng/DB khi commit | Có thể không chắc chắn kết quả phía database trong một số failure mode. | Không tự retry mù quáng; dùng idempotency, đối soát và chính sách phục hồi. |
| Quên `em.close()` | Giữ tài nguyên/persistence context lâu ngoài dự kiến. | Dùng `finally` hoặc cơ chế vòng đời do framework quản lý. |

Đối với lỗi mạng đúng lúc gửi commit, ứng dụng đôi khi **không thể biết chắc** database đã nhận và commit transaction hay chưa. Điều đó khác lỗi validation xảy ra trước khi gửi SQL. Các thao tác có side effect quan trọng nên có **business identifier/idempotency key** và cơ chế đối soát phù hợp, không retry tự động đến khi có hai giao dịch giống nhau.

## 19. Ví dụ dùng rollback khi validation nghiệp vụ thất bại

Nếu không đủ hàng tồn để chuyển, phải tránh ghi một phần dữ liệu.

```java
tx.begin();

try {
    StockBalance source = em.find(StockBalance.class, sourceId);
    StockBalance target = em.find(StockBalance.class, targetId);

    if (source == null || target == null) {
        throw new IllegalArgumentException("Balance not found");
    }

    if (source.getQuantity() < amount) {
        throw new IllegalStateException("Insufficient stock");
    }

    source.decrease(amount);
    target.increase(amount);

    tx.commit();
} catch (RuntimeException error) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw error;
}
```

Với lỗi validation trước khi sửa entity, rollback vẫn là lựa chọn nhất quán để kết thúc transaction đã bắt đầu. Nó giúp quy ước rằng một request thất bại **không được commit**.

Trong ứng dụng thực tế, cần kiểm tra `amount > 0`, source/target khác nhau và cùng SKU; phần service hoàn chỉnh ở mục 10 đã minh họa các điều kiện đó.

### 19.1. Kiểm tra trước begin có đủ không?

Một số validation tĩnh như `amount > 0` hoặc `sourceId != targetId` có thể làm trước transaction vì không phụ thuộc database.

Những validation **phụ thuộc dữ liệu có thể thay đổi bởi request khác** (ví dụ tồn kho hiện tại, quota, trạng thái đơn hàng) phải đặt trong ranh giới transaction với cách kiểm soát concurrency phù hợp.

Ngay cả khi tải số lượng trong transaction, dưới isolation yếu và không có locking, request khác vẫn có thể cập nhật cùng hàng. Vì vậy, “đã begin transaction” chưa đủ để bỏ qua `@Version` hoặc locking nếu nghiệp vụ yêu cầu.

## 20. Không dùng EntityTransaction để quản lý nhiều EntityManager độc lập như một transaction

Ví dụ không bảo đảm nguyên tử:

```java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

EntityTransaction txA = emA.getTransaction();
EntityTransaction txB = emB.getTransaction();

txA.begin();
txB.begin();

// emA cập nhật kho A.
// emB cập nhật kho B.

txA.commit();
txB.commit(); // Nếu thất bại, A đã commit trước.
```

Dù cả hai EntityManager cùng được tạo từ một `EntityManagerFactory`, **hai transaction resource-local không trở thành một transaction nguyên tử chung**.

Nếu cần cập nhật hai entity thuộc cùng database/resource, hãy làm trong **một EntityManager và một EntityTransaction** như ví dụ chuyển kho. Nếu thực sự cần giao dịch phối hợp hai tài nguyên độc lập, phải dùng một kiến trúc transaction được thiết kế cho trường hợp đó.

Không nên trông chờ `txB.rollback()` có thể hoàn tác `txA.commit()` đã thành công.

## 21. Transaction và thao tác đọc dữ liệu

JPA cho phép nhiều kiểu truy vấn:

```java
StockBalance stock = em.find(StockBalance.class, id);

List<StockBalance> list = em.createQuery(
    "SELECT s FROM StockBalance s WHERE s.warehouseId = :warehouseId",
    StockBalance.class
)
.setParameter("warehouseId", 10L)
.getResultList();
```

Đọc bên trong transaction có lợi khi cần **đọc rồi ra quyết định ghi** theo một quy tắc nhất quán. Nhưng vẫn cần nhớ:

- Persistence context có identity map; `find()` lặp lại có thể trả managed entity cũ.
- Query có thể kích hoạt auto-flush khi có thay đổi pending.
- Isolation database quyết định một transaction nhìn thấy những commit của transaction khác như thế nào.
- Lazy loading có thể phát sinh truy vấn ở thời điểm truy cập association.
- `refresh()` đọc lại state database của managed entity, nhưng có thể ghi đè thay đổi chưa flush và không vượt qua transaction isolation.

Không nên tạo transaction đọc rất dài chỉ để giữ EntityManager mở cho tầng giao diện. Với nhiều ứng dụng, service sẽ tải dữ liệu cần thiết trong transaction ngắn rồi trả DTO.

## 22. Transaction và trạng thái entity sau commit

### 22.1. Persist rồi commit

```java
tx.begin();

StockBalance stock =
    new StockBalance(10L, "SKU-MOUSE", 15);

em.persist(stock);
tx.commit();
```

Nếu commit thành công, hàng đã được cam kết. Tuy nhiên, việc `stock.getId()` có giá trị sau persist/flush không thay thế kiểm tra commit. Sau commit, nếu EntityManager còn mở, object có thể tiếp tục là managed trong context ấy; nếu đóng, nó trở thành detached.

### 22.2. Sửa managed entity rồi commit

```java
tx.begin();

StockBalance stock = em.find(StockBalance.class, id);
stock.decrease(2);

tx.commit();
```

Không cần gọi `em.persist(stock)` lại. `persist()` không phải “save tất cả”; JPA dirty checking theo dõi managed entity và đồng bộ khi flush.

### 22.3. Xóa rồi commit

```java
tx.begin();

StockBalance stock = em.find(StockBalance.class, id);
if (stock != null) {
    em.remove(stock);
}

tx.commit();
```

`remove()` đưa entity vào trạng thái removed; SQL DELETE có thể chạy muộn tại flush/commit. Sau khi xóa, không nên tái sử dụng object như một entity tồn tại và không giả định `remove()` gọi xong đã chứng minh constraint được kiểm tra thành công.

## 23. Đảm bảo đúng ranh giới nghiệp vụ

Một “transaction vừa đủ” thường bao phủ các bước cần thành công hoặc thất bại cùng nhau:

```text
Yêu cầu chuyển tồn kho
       |
       +-- Kiểm tra tham số không phụ thuộc DB
       |
       +-- begin()
       |     |
       |     +-- Tải kho nguồn và đích
       |     +-- Kiểm tra điều kiện nhất quán
       |     +-- Giảm kho nguồn
       |     +-- Tăng kho đích
       |     +-- Ghi audit/outbox vào cùng DB nếu yêu cầu
       |     |
       |     +-- commit() / rollback()
       |
       +-- Phản hồi kết quả
```

**Không nên đặt network call kéo dài vào giữa transaction** nếu có thể tránh; transaction càng lâu càng dễ giữ khóa và tranh chấp tài nguyên. Với thao tác bên ngoài database, cân nhắc outbox hoặc quy trình phân tán có bù trừ thích hợp.

Nếu có nhiều repository/service trong Java SE, cần tránh mỗi method tự mở transaction riêng khi toàn bộ request phải có tính nguyên tử. Transaction boundary thường nên đặt ở **use-case/application service**, không được phân mảnh tùy tiện theo từng lệnh repository.

### 23.1. Nếu dùng nhiều dữ liệu liên quan

Ví dụ tạo đơn hàng mới, chi tiết và phiếu xuất kho:

- Chúng phải được ghi trong cùng transaction nếu nghiệp vụ yêu cầu tất cả cùng thành công.
- `CascadeType.PERSIST` có thể lan truyền thao tác persist qua quan hệ entity, nhưng **cascade không tạo transaction riêng**.
- `EntityTransaction` quyết định ranh giới commit/rollback của tất cả thay đổi do cùng EntityManager quản lý.
- Không nên xem việc `persist(order)` đã chạy là bằng chứng mọi bản ghi liên quan đã commit.

## 24. Các câu hỏi về lỗi thường gặp

### “Có thể bắt đầu transaction một lần và chia sẻ cho mọi request không?”

Không nên. `EntityManager` không thread-safe và không thích hợp để nhiều request cùng sử dụng đồng thời. Mỗi request hoặc đơn vị công việc nên có transaction/context theo quản lý phù hợp.

### “Có thể gọi begin() lồng nhau để tạo savepoint không?”

Không. `EntityTransaction` không định nghĩa nested transaction/savepoint; gọi `begin()` khi transaction active là lỗi trạng thái.

### “Gọi flush() có giống commit() không?”

Không. Flush đồng bộ SQL trong transaction; rollback vẫn có thể hoàn tác. Commit kết thúc giao dịch bằng cam kết thành công hoặc ném lỗi.

### “Nếu persist() không ném lỗi thì dữ liệu đã lưu chưa?”

Chưa thể kết luận. Lỗi có thể chỉ xuất hiện ở flush/commit, và transaction còn có thể rollback.

### “Sau commit(), EntityManager có tự đóng không?”

Không. Application-managed EntityManager phải được đóng theo vòng đời ứng dụng, thường trong `finally`.

### “Nếu rollback thì object Java quay về dữ liệu database cũ không?”

Không nên kỳ vọng. Sau rollback, managed/detached state có thể không đồng bộ với database. Kết thúc context và tải lại khi cần.

### “Dùng Spring @Transactional rồi có nên tự gọi em.getTransaction() không?”

Không trên EntityManager do Spring/container quản lý theo mô hình transaction của nó. Chọn một cơ chế quản lý ranh giới nhất quán.

### “Có thể commit một transaction của emA để lưu thay đổi trên emB không?”

Không. Transaction resource-local của một EntityManager không tự bao phủ EntityManager khác.

### “@Version có thay thế transaction không?”

Không. `@Version` giúp phát hiện một số xung đột cập nhật; transaction vẫn cần để bảo đảm nguyên tử của các câu SQL.

### “Dùng EntityTransaction là có SERIALIZABLE mặc định?”

Không. Isolation được quyết định bởi database/datasource/provider configuration và các cơ chế khóa được sử dụng; `EntityTransaction` không tự nâng lên mức mạnh nhất.

### “Nếu commit() ném lỗi thì cứ chạy lại cùng em và commit một lần nữa?”

Không. Transaction có thể đã rollback hoặc đang ở trạng thái không rõ/không sử dụng được. Cần xử lý lỗi, giải phóng context và chỉ retry **toàn bộ đơn vị công việc** với chính sách idempotency phù hợp.

### “Một transaction local có tự rollback email đã gửi hay request HTTP bên ngoài không?”

Không. Những side effect không tham gia transaction DB sẽ không tự được hoàn tác.

## 25. Bài tập thực hành

### Bài tập 1 — Dự đoán trạng thái transaction

```java
EntityTransaction tx = em.getTransaction();

System.out.println(tx.isActive());
tx.begin();
System.out.println(tx.isActive());
tx.commit();
System.out.println(tx.isActive());
```

**Giải thích:** Trước begin thường là `false`, sau begin là `true`, sau commit thành công là `false`.

### Bài tập 2 — Tại sao thiếu rollback gây vấn đề?

```java
tx.begin();

StockBalance stock = em.find(StockBalance.class, id);
stock.decrease(10);

throw new IllegalStateException("Unexpected error");
```

**Giải thích:** Transaction còn dang dở nếu caller không xử lý. Code nên có transaction boundary với rollback khi lỗi và đóng EntityManager, tránh giữ tài nguyên/khóa và dữ liệu nửa chừng.

### Bài tập 3 — Hai EntityManager có cùng transaction không?

```java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();
```

**Giải thích:** Chúng là hai EntityManager riêng. `em1.getTransaction()` không tự bao phủ các thao tác trong `em2`, dù cùng một factory.

### Bài tập 4 — Flush rồi exception

```java
tx.begin();
stock.decrease(2);
em.flush();
throw new RuntimeException("Step later failed");
```

**Giải thích:** Nếu exception được bắt và transaction rollback hợp lệ, những thay đổi đã flush vẫn không được cam kết. Flush khác commit.

### Bài tập 5 — Tại sao không dùng persist cho entity đã managed?

```java
tx.begin();
StockBalance stock = em.find(StockBalance.class, id);
stock.increase(4);
tx.commit();
```

**Giải thích:** StockBalance đang managed. Dirty checking phát hiện thay đổi, không cần `persist(stock)` nữa.

### Bài tập 6 — Transaction bị rollback-only

```java
tx.begin();
tx.setRollbackOnly();

boolean flag = tx.getRollbackOnly();
```

**Giải thích:** `flag` là true. Transaction này không thể được commit thành công; cần rollback và báo lỗi phù hợp.

### Bài tập 7 — Hai giao dịch cùng trừ tồn kho

A và B cùng đọc quantity=10 rồi đều muốn trừ 8.

**Giải thích:** Resource-local transaction tự nó không bảo đảm phát hiện lost update dưới mọi isolation. `@Version` hoặc pessimistic locking/atomic SQL update giúp thực thi yêu cầu concurrency theo thiết kế.

### Bài tập 8 — Hệ thống ghi DB rồi gửi message

Ứng dụng commit thay đổi tồn kho, sau đó message broker không nhận sự kiện.

**Giải thích:** Một resource-local transaction đã commit không được rollback chỉ vì message ngoài DB thất bại. Cần cơ chế phát sự kiện đáng tin cậy, ví dụ outbox nằm trong cùng database transaction.

### Bài tập 9 — Lỗi unique key tại commit

Một `persist()` chạy bình thường, nhưng `tx.commit()` ném ngoại lệ vì `UNIQUE(warehouse_id, sku)`.

**Giải thích:** Đây vẫn là transaction thất bại. Không tuyên bố thành công; xử lý rollback nếu còn active, đóng context và trả lỗi phù hợp. Không dựa vào việc object đã có ID.

### Bài tập 10 — Kết hợp Spring và EntityTransaction

Một Spring service có `@Transactional` inject `@PersistenceContext EntityManager`, rồi gọi `em.getTransaction().begin()`.

**Giải thích:** Đây là trộn hai cơ chế quản lý transaction không đúng trên EntityManager do framework/container quản lý. Hãy để Spring transaction manager điều phối, hoặc thiết kế riêng một luồng Java SE resource-local thực sự nếu cần.

## 26. Ghi nhớ cốt lõi

**`EntityTransaction` là API điều khiển transaction của một `EntityManager` sử dụng `RESOURCE_LOCAL`.** `begin()` mở giao dịch; `commit()` đồng bộ và cố cam kết; `rollback()` hủy những thay đổi database chưa commit. `isActive()` giúp kiểm tra trạng thái; `setRollbackOnly()` và `getRollbackOnly()` hỗ trợ đánh dấu/nhận biết giao dịch buộc phải hủy.

Thay đổi entity được thực hiện bằng **`EntityManager` và managed entity**: `persist()` cho entity mới, dirty checking cho entity đã managed, `merge()` cho detached state khi cần, và `remove()` cho xóa. **`flush()` không phải commit**; lỗi có thể phát sinh ở flush hoặc commit, nên transaction boundary phải có xử lý lỗi và rollback phù hợp.

Trong Java SE, cách tổ chức đáng tin cậy thường là **tạo EntityManager theo đơn vị công việc, begin, thao tác nghiệp vụ, commit khi thành công, rollback khi lỗi, và đóng EntityManager trong finally**. Không tự chia sẻ EntityManager giữa thread, không gọi begin lồng nhau, không coi hai EntityManager cùng factory là cùng transaction, và không kết hợp tùy tiện `EntityTransaction` với JTA/Spring-managed transaction.

Cuối cùng, **transaction bảo vệ tính nguyên tử của các thay đổi database trong phạm vi của nó**, nhưng không thay thế concurrency control, business validation hay cơ chế điều phối side effect bên ngoài. Chọn đúng ranh giới transaction, xử lý lỗi và thiết kế locking/idempotency phù hợp sẽ giúp ứng dụng JPA giữ dữ liệu nhất quán cả khi thành công lẫn khi thất bại.
