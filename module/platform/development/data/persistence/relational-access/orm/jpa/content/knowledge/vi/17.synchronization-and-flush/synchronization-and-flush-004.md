# Vai trò của FlushModeType.AUTO và COMMIT trong JPA

Trong JPA, sửa thuộc tính của một entity đang được quản lý không có nghĩa ứng dụng đã thực thi ngay lệnh `UPDATE` trên database. Tương tự, gọi `persist()` không bảo đảm `INSERT` đã chạy ngay, và gọi `remove()` không nhất thiết phát `DELETE` tức thời. Các thay đổi có thể được giữ trong **persistence context**, rồi được đồng bộ với cơ sở dữ liệu vào một thời điểm do JPA provider xác định.

**Flush mode** điều khiển một phần thời điểm đồng bộ này, đặc biệt là mối quan hệ giữa **thay đổi đang chờ** và **truy vấn được thực hiện trước khi giao dịch commit**.

JPA cung cấp hai giá trị chuẩn trong `jakarta.persistence.FlushModeType`:

- **`FlushModeType.AUTO`:** chế độ mặc định. Khi thực hiện truy vấn trong điều kiện phù hợp, provider phải bảo đảm các thay đổi đang chờ **có thể ảnh hưởng tới kết quả truy vấn** được nhìn thấy khi xử lý truy vấn. Provider có thể flush trước truy vấn hoặc dùng phương pháp khác để đáp ứng yêu cầu này.
- **`FlushModeType.COMMIT`:** ưu tiên đồng bộ khi transaction commit; ảnh hưởng của các thay đổi chưa được flush lên kết quả truy vấn trước commit **không được JPA đặc tả bảo đảm**.

Điểm quan trọng: **AUTO không có nghĩa “cứ query là INSERT/UPDATE ngay”**, và **COMMIT không có nghĩa “chắc chắn không có SQL trước commit”**. Cả hai đều không làm thay đổi ý nghĩa của commit hay rollback.

Bài học này giải thích ngữ nghĩa chuẩn, vòng đời persistence context, cách đặt flush mode, ví dụ thực hành, ảnh hưởng tới JPQL, Spring Data JPA, hiệu năng, xử lý lỗi và những nhầm lẫn phổ biến.

## 1. Flush đứng ở đâu trong vòng đời persistence?

### 1.1. Persistence context là nơi JPA theo dõi entity

`EntityManager` quản lý các entity trong một **persistence context**. Với entity managed, provider có thể theo dõi thay đổi và lập kế hoạch đồng bộ chúng bằng SQL.

Ví dụ:

~~~java
PurchaseOrder order =
    entityManager.find(PurchaseOrder.class, orderId);

order.setStatus(OrderStatus.PAID);
~~~

Nếu `order` đang managed và nằm trong transaction phù hợp, JPA có thể phát hiện trạng thái thay đổi (*dirty checking*) và đưa `UPDATE` vào công việc cần đồng bộ. Nhưng tại thời điểm gọi setter, không thể khẳng định một lệnh SQL đã được gửi.

Một luồng thường gặp:

~~~text
Java application                Persistence context             Database
       |                                 |                           |
       | em.find(id)                     |                           |
       |-------------------------------->|------ SELECT có thể ---->|
       |<--------------------------------|<--------------------------|
       |                                 |                           |
       | order.setStatus(PAID)           |                           |
       |-------------------------------->| ghi nhận thay đổi         |
       |                                 |                           |
       | em.flush() hoặc auto flush      |                           |
       |-------------------------------->|------ UPDATE ----------->|
       |                                 |                           |
       | transaction.commit()            |                           |
       |----------------------------------------------------------->|
       |                                 |                        COMMIT
       v                                 v                           v
~~~

Việc provider có gửi SQL theo đúng số lần và thứ tự trong sơ đồ phụ thuộc mapping, transaction, generator, batching và implementation. Sơ đồ chỉ diễn đạt các **mốc trách nhiệm**, không phải lịch thực thi bắt buộc.

### 1.2. Bốn hành động dễ bị nhầm

| Hành động | Tác dụng chính | Có bảo đảm transaction đã commit? |
|---|---|---|
| `entityManager.persist(entity)` | Yêu cầu quản lý và lưu entity mới | Không |
| Thay đổi field trên entity managed | Thay đổi trạng thái trong context; có thể cần SQL `UPDATE` | Không |
| `entityManager.flush()` | Đồng bộ các thay đổi pending xuống DB trong transaction | Không |
| `transaction.commit()` | Kết thúc và xác nhận transaction theo DB | Có, khi commit thực sự thành công |

`FlushModeType` điều chỉnh hành vi **flush tự động**, không thay thế API `flush()` và không biến truy vấn thành transaction commit.

### 1.3. Flush khác commit

Ví dụ SQL ý tưởng:

~~~sql
BEGIN;

UPDATE purchase_order
SET status = 'PAID'
WHERE id = 100;

-- Tương ứng SQL đã được gửi khi flush.
-- Transaction vẫn đang mở.

ROLLBACK;
~~~

`UPDATE` đã chạy nhưng bị rollback. Nếu thay `ROLLBACK` bằng `COMMIT` và commit thành công, tác động mới được xác nhận.

Vì vậy:

> **Flush đồng bộ SQL trong transaction; commit xác nhận transaction.**

Kể cả flush thành công, transaction vẫn có thể lỗi do constraint được kiểm tra muộn, xung đột đồng thời hoặc các vấn đề khác khi commit.

## 2. Hai hằng số chuẩn của `FlushModeType`

API Jakarta Persistence:

~~~java
import jakarta.persistence.FlushModeType;

FlushModeType auto = FlushModeType.AUTO;
FlushModeType commit = FlushModeType.COMMIT;
~~~

### 2.1. AUTO — Bảo đảm tính nhìn thấy của những thay đổi liên quan tới truy vấn

Với `AUTO`, khi `EntityManager` thực hiện truy vấn trong ngữ cảnh transaction đã tham gia thích hợp, JPA provider có trách nhiệm bảo đảm **những thay đổi trong persistence context có thể ảnh hưởng kết quả truy vấn được phản ánh trong xử lý truy vấn**.

Provider có thể đạt điều đó bằng một trong các cách:

1. Flush các thay đổi liên quan tới DB trước khi chạy truy vấn.
2. Sử dụng cơ chế khác bảo đảm ngữ nghĩa tương đương, nếu implementation hỗ trợ.
3. Quyết định không cần flush nếu các thay đổi pending không thể ảnh hưởng kết quả truy vấn.

Do đó, đây là nhận định đúng:

> Với AUTO, **kết quả truy vấn phải phản ánh các thay đổi pending có liên quan theo hợp đồng JPA**, nhưng **không có lời hứa rằng mọi truy vấn đều chạy flush toàn bộ**.

Cách Hibernate hoặc EclipseLink tối ưu kiểm tra mức độ liên quan có thể thay đổi theo phiên bản, API truy vấn, mapping và database.

### 2.2. COMMIT — Không bảo đảm visibility của pending changes trong query

Với `COMMIT`, provider thường trì hoãn việc flush tự động cho tới giai đoạn transaction commit, nếu không có thao tác hoặc lý do khác yêu cầu SQL xảy ra sớm hơn.

Tuy nhiên, đặc tả JPA **không xác định kết quả** của truy vấn trước commit đối với các thay đổi đã có trong persistence context nhưng chưa được flush. Một truy vấn có thể thấy dữ liệu cũ, dữ liệu mới hoặc sự kết hợp tùy ngữ cảnh/provider; ứng dụng **không được dựa vào một kết quả cụ thể**.

Đặc biệt, **COMMIT không được định nghĩa là chế độ “luôn đọc dữ liệu cũ”**. Nếu SQL đã chạy sớm hoặc provider tự đồng bộ theo cách khác, truy vấn có thể thấy thay đổi.

### 2.3. Bảng so sánh

| Khía cạnh | `AUTO` | `COMMIT` |
|---|---|---|
| Có thuộc chuẩn JPA? | Có | Có |
| Là mặc định của JPA? | **Có** | Không |
| Tự động flush trước mọi truy vấn? | **Không bắt buộc** | Không hứa không flush |
| Visibility của thay đổi pending có ảnh hưởng query | Được bảo đảm trong ngữ cảnh thích hợp | **Không được đặc tả bảo đảm** |
| Thời điểm ghi SQL có thể trước commit? | Có | **Có** |
| Gọi `flush()` tường minh có hiệu lực? | Có | Có |
| Khi commit thành công, thay đổi hợp lệ phải được đồng bộ? | Có | Có |
| Flush thành công có nghĩa commit thành công? | Không | Không |
| Có thể rollback sau khi SQL đã chạy? | Có | Có |
| Phù hợp khi | Cần tính nhất quán giữa thay đổi managed và truy vấn tiếp theo | Có thể chấp nhận không xác định visibility trước commit để tránh một số flush do query |

### 2.4. Quy tắc không thể bỏ qua

**AUTO đặt ra một yêu cầu về kết quả xử lý truy vấn; COMMIT bỏ bảo đảm ấy cho trạng thái chưa flush.** Hai giá trị này không phải là “AUTO tự commit” và “COMMIT tự ghi khi query”.

## 3. Ví dụ entity để theo dõi flush mode

Giả sử hệ thống đơn hàng dùng enum trạng thái:

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Entity:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_gen"
    )
    @SequenceGenerator(
        name = "purchase_order_gen",
        sequenceName = "purchase_order_seq",
        allocationSize = 1
    )
    private Long id;

    @Version
    private long version;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status = OrderStatus.NEW;

    @Column(
        name = "total",
        nullable = false,
        precision = 14,
        scale = 2
    )
    private BigDecimal total;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(BigDecimal total) {
        if (total == null || total.signum() < 0) {
            throw new IllegalArgumentException("Invalid order total");
        }
        this.total = total;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void markPaid() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                "Only NEW orders can become PAID"
            );
        }
        status = OrderStatus.PAID;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Với PostgreSQL, schema khái niệm có thể là:

~~~sql
CREATE SEQUENCE purchase_order_seq
    START WITH 1 INCREMENT BY 1;

CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total DECIMAL(14,2) NOT NULL
);
~~~

`@Version` dùng optimistic locking khi entity được cập nhật. SQL và thứ tự đồng bộ trong ví dụ phụ thuộc provider; schema phải tương thích mapping thực tế.

Trong các phần sau, `em` là `EntityManager`, `emf` là `EntityManagerFactory` đã cấu hình sẵn.

## 4. AUTO khi persist rồi chạy JPQL query

Giả sử trước transaction bảng không có đơn nào ở trạng thái NEW với tổng tiền 120.000.

~~~java
em.setFlushMode(FlushModeType.AUTO);

tx.begin();

PurchaseOrder order =
    new PurchaseOrder(new BigDecimal("120000.00"));

em.persist(order);

Long count = em.createQuery(
        "SELECT COUNT(o) FROM PurchaseOrder o " +
        "WHERE o.status = :status",
        Long.class
    )
    .setParameter("status", OrderStatus.NEW)
    .getSingleResult();

System.out.println("Count = " + count);

tx.rollback();
~~~

Trong ngữ cảnh AUTO với transaction đã tham gia, một entity NEW mới được persist có thể làm thay đổi kết quả truy vấn `COUNT`. Provider phải xử lý truy vấn theo cách phản ánh những thay đổi phù hợp. Thực tế thông thường là flush `INSERT` trước khi thực thi câu SQL đếm.

Quan sát log SQL có thể thấy:

~~~sql
SELECT nextval('purchase_order_seq');
INSERT INTO purchase_order (...);
SELECT COUNT(*) FROM purchase_order WHERE status = 'NEW';
~~~

Đây là một **khả năng thực thi điển hình**, không phải chuỗi SQL bắt buộc của mọi provider. Khi có các đơn NEW khác từ trước, `count` là tổng số các đơn thỏa điều kiện; ví dụ không khẳng định nó luôn bằng 1.

Quan trọng hơn, **ngay sau truy vấn này transaction vẫn có thể rollback**. Việc `COUNT` đã nhìn thấy đơn mới không chứng minh đơn đã commit.

### 4.1. Không nên phát biểu “AUTO luôn flush trước SELECT”

Nếu không có thay đổi pending, provider không cần flush chỉ để chạy một truy vấn. Nếu thay đổi chỉ liên quan bảng khác và không thể ảnh hưởng truy vấn, provider cũng có thể bỏ qua flush ở thời điểm ấy.

Ví dụ:

~~~java
customer.setDisplayName("Tên mới");

// Query chỉ đếm product, không liên quan customer:
Long productCount = em.createQuery(
    "SELECT COUNT(p) FROM Product p", Long.class
).getSingleResult();
~~~

Một provider có thể kết luận thay đổi Customer không ảnh hưởng truy vấn Product và không flush Customer trước truy vấn. Provider khác có thể flush rộng hơn; cả hai đều có thể đáp ứng hợp đồng AUTO.

Không thiết kế logic dựa trên số lượng `INSERT`/`UPDATE` xuất hiện chính xác trước một truy vấn cụ thể, trừ khi đó là một hành vi riêng đã được provider tài liệu hóa và dự án kiểm chứng.

### 4.2. Thế nào là “có thể ảnh hưởng query”?

Các thay đổi liên quan bao gồm:

- Persist entity mới có thể khớp bộ lọc.
- Xóa entity có thể đang được truy vấn.
- Sửa field được dùng trong `WHERE`.
- Sửa field được chọn trong `SELECT` hoặc được dùng để sắp xếp.
- Sửa quan hệ làm thay đổi kết quả `JOIN`.
- Sửa dữ liệu làm thay đổi `COUNT`, `SUM` hoặc các aggregate khác.

Đây là lý do AUTO rất quan trọng với chuỗi thao tác “ghi trong transaction, rồi dùng JPQL để ra quyết định tiếp”.

## 5. COMMIT khi persist rồi query: Không được giả định kết quả

Cùng thao tác nhưng đặt COMMIT:

~~~java
em.setFlushMode(FlushModeType.COMMIT);

tx.begin();

PurchaseOrder order =
    new PurchaseOrder(new BigDecimal("120000.00"));

em.persist(order);

Long count = em.createQuery(
        "SELECT COUNT(o) FROM PurchaseOrder o " +
        "WHERE o.status = :status",
        Long.class
    )
    .setParameter("status", OrderStatus.NEW)
    .getSingleResult();

tx.commit();
~~~

Không được viết test như sau:

~~~java
// Không portable:
assertEquals(0L, count);
~~~

với lý do “COMMIT chưa flush, nên query chắc chắn chưa thấy đơn mới”. Đây là một giả định **không được JPA bảo đảm**.

Cũng không được viết:

~~~java
// Cũng không được đặc tả bảo đảm nếu chưa flush:
assertEquals(1L, count);
~~~

trong trường hợp chỉ có đúng một đơn NEW và không có thay đổi trước đó. Với COMMIT, visibility của pending changes chưa flush đối với query là **không xác định**. Tùy provider, chiến lược sinh ID, việc đồng bộ sớm và loại truy vấn, kết quả có thể khác.

### 5.1. Nếu thật sự cần query thấy thay đổi trong COMMIT?

Hãy flush tường minh trước truy vấn:

~~~java
em.setFlushMode(FlushModeType.COMMIT);

tx.begin();

PurchaseOrder order =
    new PurchaseOrder(new BigDecimal("120000.00"));

em.persist(order);

// Đồng bộ SQL trong transaction.
em.flush();

Long count = em.createQuery(
        "SELECT COUNT(o) FROM PurchaseOrder o " +
        "WHERE o.status = :status",
        Long.class
    )
    .setParameter("status", OrderStatus.NEW)
    .getSingleResult();

tx.commit();
~~~

`flush()` đưa pending changes vào DB trong transaction hiện tại. Truy vấn DB tiếp theo trong cùng transaction có thể nhìn thấy chính những thay đổi đã ghi, theo cơ chế transaction/isolation của DB.

Đây là cách đạt ranh giới đồng bộ rõ ràng khi code cần dựa vào kết quả query sau khi đã sửa managed state.

**Lưu ý:** `flush()` chưa commit; transaction khác ở mức cô lập phổ biến `READ COMMITTED` thường chưa thấy các hàng chưa commit đó.

### 5.2. Nếu không cần query thấy thay đổi?

Giả sử transaction chỉ xây dựng một loạt đơn hàng rồi commit; không có logic query phụ thuộc vào chúng trước commit. Khi ấy COMMIT có thể là một lựa chọn hợp lý để giảm các lần đồng bộ bị kích hoạt do query.

Tuy nhiên, hãy đo hiệu năng và hiểu provider trước khi đổi mode; khác biệt không chỉ là tốc độ mà còn là ngữ nghĩa nhìn thấy dữ liệu giữa các thao tác trong transaction.

## 6. AUTO khi cập nhật entity managed rồi truy vấn

Giả sử trong DB có:

~~~text
purchase_order
id=10, status=NEW, total=120000.00
~~~

Trong transaction:

~~~java
em.setFlushMode(FlushModeType.AUTO);
tx.begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, 10L);

order.markPaid();

Long paidCount = em.createQuery(
        "SELECT COUNT(o) FROM PurchaseOrder o " +
        "WHERE o.status = :status",
        Long.class
    )
    .setParameter("status", OrderStatus.PAID)
    .getSingleResult();

tx.rollback();
~~~

Việc `markPaid()` sửa entity managed từ NEW sang PAID có thể ảnh hưởng đến `COUNT` với điều kiện `status = PAID`. AUTO phải bảo đảm việc xử lý query phản ánh thay đổi liên quan trong ngữ cảnh transaction phù hợp.

Thực tế thường gặp:

~~~text
find(10)        -> SELECT (nếu chưa có trong context)
markPaid()      -> đổi state ở bộ nhớ
COUNT(PAID)     -> provider flush UPDATE nếu cần, rồi SELECT COUNT
rollback()      -> UPDATE bị rollback
~~~

Không phải cứ thấy entity ở trạng thái PAID trong Java là bản ghi đã được commit. Điều đó chỉ mô tả state hiện tại của managed object và những thay đổi đang chờ/đã flush trong transaction.

### 6.1. COMMIT có thể khiến query dùng dữ liệu chưa đồng bộ

Nếu đổi AUTO thành COMMIT và bỏ `flush()`:

~~~java
em.setFlushMode(FlushModeType.COMMIT);
tx.begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, 10L);

order.markPaid();

Long paidCount = em.createQuery(
        "SELECT COUNT(o) FROM PurchaseOrder o " +
        "WHERE o.status = :status",
        Long.class
    )
    .setParameter("status", OrderStatus.PAID)
    .getSingleResult();

tx.commit();
~~~

Không nên dùng `paidCount` để quyết định một nghiệp vụ mà đòi hỏi nó **chắc chắn** đã tính trạng thái PAID mới, trừ khi explicit flush hoặc có một cơ chế khác được bảo đảm. Với COMMIT, kết quả query có thể không phản ánh pending update.

### 6.2. Một query trả về entity có thể khác query trả scalar/aggregate

Ví dụ:

~~~java
PurchaseOrder same =
    em.find(PurchaseOrder.class, 10L);
~~~

Nếu `order` đã managed trong cùng persistence context, `find` thường trả lại chính object đó:

~~~java
same == order  // thường true
~~~

và `same.getStatus()` có thể là PAID dù SQL `UPDATE` chưa chạy.

Điều này khác với `SELECT COUNT(o)`, một truy vấn scalar có thể được tính tại DB. Với COMMIT, có thể xuất hiện hiện tượng:

~~~text
Entity đã managed trong Java:   status = PAID
Cột ở DB trước flush:           status = NEW
JPQL COUNT(status = PAID):      không được bảo đảm phản ánh PAID
~~~

Không xem đây là mâu thuẫn; đó là khác biệt giữa **identity map/managed object** và **kết quả truy vấn DB trước khi đồng bộ**.

## 7. AUTO với remove và thay đổi quan hệ

Flush mode không chỉ liên quan `persist` và update.

### 7.1. Entity bị remove

~~~java
tx.begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

em.remove(order);

Long count = em.createQuery(
        "SELECT COUNT(o) FROM PurchaseOrder o",
        Long.class
    )
    .getSingleResult();
~~~

Nếu entity bị xóa có thể ảnh hưởng `COUNT`, AUTO yêu cầu query phản ánh thay đổi phù hợp khi xử lý. Provider có thể flush `DELETE` trước truy vấn.

Với COMMIT mà chưa flush, **không được giả định chắc chắn** `COUNT` đã trừ đi entity bị remove.

### 7.2. Quan hệ và join table

Giả sử `PurchaseOrder` có `@OneToMany` các dòng hàng, hoặc `Student` liên kết nhiều `Course` qua bảng nối. Thêm hoặc xóa liên kết trong managed context có thể tạo:

- `INSERT`/`DELETE` ở join table.
- `UPDATE` foreign key.
- `INSERT`/`DELETE` entity phụ thuộc do cascade và orphanRemoval.

Một JPQL query có `JOIN` hoặc `COUNT` trên quan hệ đó có thể bị ảnh hưởng bởi những thay đổi pending. AUTO yêu cầu xử lý đúng ngữ nghĩa visibility trong phạm vi có hiệu lực; COMMIT không bảo đảm nhìn thấy chúng trước flush.

### 7.3. Cascade và orphanRemoval

Nếu `removeLine(...)` gỡ một `OrderLine` khỏi quan hệ có `orphanRemoval = true`, phần tử có thể được xóa khi flush. Flush mode ảnh hưởng thời điểm đồng bộ tự động, nhưng **không thay thế việc thiết kế ownership**. Khi quan hệ hai chiều, phải cập nhật owning side và collection nhất quán; AUTO không thể sửa một graph nghiệp vụ đã gắn sai liên kết.

## 8. Thiết lập flush mode trên EntityManager

API chuẩn:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.FlushModeType;

EntityManager em = emf.createEntityManager();

em.setFlushMode(FlushModeType.AUTO);

FlushModeType current = em.getFlushMode();
~~~

`EntityManager.setFlushMode(...)` đặt flush mode áp dụng cho hoạt động của entity manager, bao gồm các truy vấn không có override riêng.

Thông thường:

~~~java
em.getFlushMode() == FlushModeType.AUTO
~~~

khi chưa có thay đổi cấu hình, vì AUTO là mặc định của JPA. Trong những môi trường framework/provider có can thiệp vào chế độ flush, cần kiểm tra trạng thái thực tế nếu hành vi cụ thể quan trọng.

### 8.1. Ví dụ trong resource-local transaction

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    em.setFlushMode(FlushModeType.COMMIT);

    tx.begin();

    PurchaseOrder order =
        new PurchaseOrder(new BigDecimal("50000.00"));

    em.persist(order);

    // Không có bảo đảm query sẽ thấy pending insert nếu chưa flush.
    em.flush();

    tx.commit();

} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Đây là ví dụ `RESOURCE_LOCAL`. Trong môi trường JTA hoặc Spring-managed transaction, không nên trộn trực tiếp `getTransaction()` với cơ chế transaction manager của container.

### 8.2. Không nên thay mode tùy tiện giữa chừng

Nếu một service bất kỳ gọi:

~~~java
em.setFlushMode(FlushModeType.COMMIT);
~~~

trên EntityManager đang được dùng chung trong phạm vi transaction, các truy vấn tiếp theo có thể bị ảnh hưởng cho tới khi mode được đổi lại. Việc này làm semantic behavior khó dự đoán ở các tầng khác.

Nếu chỉ một truy vấn cụ thể có thể chấp nhận semantics của COMMIT, thường rõ ràng hơn khi đặt **flush mode ở cấp Query** thay vì đổi mode của cả EntityManager.

## 9. Thiết lập flush mode riêng trên Query

JPA cung cấp `Query.setFlushMode(FlushModeType)` và `TypedQuery.setFlushMode(FlushModeType)`.

Ví dụ:

~~~java
em.setFlushMode(FlushModeType.AUTO);

TypedQuery<Long> query = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o",
    Long.class
);

query.setFlushMode(FlushModeType.COMMIT);

Long count = query.getSingleResult();
~~~

Trong trường hợp này, **riêng truy vấn `query`** sử dụng flush mode COMMIT. EntityManager vẫn có mode AUTO cho các query khác không override.

Ví dụ ngược lại:

~~~java
em.setFlushMode(FlushModeType.COMMIT);

TypedQuery<Long> query = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o",
    Long.class
);

query.setFlushMode(FlushModeType.AUTO);

Long count = query.getSingleResult();
~~~

Ở đây query riêng yêu cầu AUTO, dù EntityManager được đặt COMMIT.

### 9.1. Thứ tự ưu tiên

Có thể hình dung:

~~~text
Lệnh query được thực thi
          |
          v
Query có gọi setFlushMode(...) riêng?
          |
          +-- Có --> dùng flush mode của Query
          |
          +-- Không --> dùng flush mode có hiệu lực trên EntityManager
                            |
                            +-- Mặc định JPA: AUTO
~~~

Override trên Query không đồng nghĩa thay đổi vĩnh viễn flush mode của EntityManager.

### 9.2. Lấy giá trị flush mode

~~~java
FlushModeType emMode = em.getFlushMode();

TypedQuery<Long> q = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o",
    Long.class
);

FlushModeType queryMode = q.getFlushMode();
~~~

Theo API chuẩn, nếu Query không có flush mode riêng, `getFlushMode()` phản ánh mode có hiệu lực theo EntityManager. Khi cần đảm bảo, nên đặt rõ mode ngay tại query thay vì đoán provider có giữ một thiết lập cũ hay không.

### 9.3. Khi nào override ở Query?

Cân nhắc query-level COMMIT khi:

- Query chỉ đọc dữ liệu không phụ thuộc các thay đổi pending hiện tại.
- Transaction có nhiều thao tác ghi ở các vùng khác, nhưng một query báo cáo độc lập không cần đồng bộ trước.
- Đội phát triển hiểu rõ ràng rằng visibility của pending changes đối với query là không xác định.
- Có đo đạc chứng minh flush trước query tạo chi phí đáng kể trong use case cụ thể.

Cân nhắc query-level AUTO khi:

- EntityManager bị cấu hình COMMIT vì lý do tổng thể.
- Một query cụ thể phải nhận kết quả có liên hệ nhất quán với các thay đổi managed trước đó.

Không chọn COMMIT chỉ vì tên nó có vẻ “an toàn hơn” hoặc “giống read-only”. Đây là điều chỉnh visibility và thời điểm đồng bộ, không phải cơ chế kiểm soát quyền ghi.

## 10. Flush mode không phải chế độ chỉ đọc

Một nhầm lẫn:

~~~java
em.setFlushMode(FlushModeType.COMMIT);
~~~

và kết luận “EntityManager đã ở chế độ read-only”.

**Sai.** COMMIT không cấm `persist`, `merge`, `remove` hay dirty checking. Nó chỉ điều chỉnh ngữ nghĩa auto flush/visibility theo hợp đồng JPA. Khi transaction commit, thay đổi hợp lệ vẫn có thể được ghi.

Tương tự, AUTO không làm mọi query trở thành lệnh ghi; một truy vấn đọc vẫn là truy vấn đọc, chỉ có thể kích hoạt đồng bộ những thay đổi trước đó trong cùng persistence context.

Phân biệt:

| Khái niệm | Nhiệm vụ |
|---|---|
| `FlushModeType.AUTO` | Bảo đảm visibility của pending changes có thể ảnh hưởng query |
| `FlushModeType.COMMIT` | Không bảo đảm visibility đó trước flush/commit |
| `@Transactional(readOnly = true)` của Spring | Gợi ý/cấu hình framework cho transaction đọc, phụ thuộc transaction manager/provider |
| `@Column(updatable = false)` | Metadata cho cột không được đưa vào SQL update theo mapping |
| Database read-only transaction | Cơ chế/hint do transaction manager/DB quản lý |
| Hibernate-specific read-only entity/session | Tính năng riêng provider, có thể ảnh hưởng dirty checking |
| Query trả DTO/projection | Cách giới hạn dữ liệu đọc, không phải flush mode |

Một số tích hợp Spring/Hibernate có thể tối ưu flush khi dùng `@Transactional(readOnly = true)`. Nhưng đây **không phải định nghĩa của `FlushModeType.COMMIT`**, và chi tiết phụ thuộc cấu hình/phiên bản.

## 11. Flush mode và Spring Data JPA

Trong Spring, transaction thường được quản lý bằng `@Transactional`:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.FlushModeType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final EntityManager em;

    public OrderService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public long markPaidAndCount(Long orderId) {
        PurchaseOrder order =
            em.find(PurchaseOrder.class, orderId);

        if (order == null) {
            throw new IllegalArgumentException("Order not found");
        }

        order.markPaid();

        em.setFlushMode(FlushModeType.AUTO);

        return em.createQuery(
                "SELECT COUNT(o) FROM PurchaseOrder o " +
                "WHERE o.status = :status",
                Long.class
            )
            .setParameter("status", OrderStatus.PAID)
            .getSingleResult();
    }
}
~~~

Ở đây `@Transactional` cung cấp ranh giới transaction thông qua Spring. Nếu method được gọi qua proxy và tự mở transaction ngoài cùng, Spring sẽ commit sau khi method body trả về bình thường. Nếu method tham gia transaction lớn hơn, commit có thể xảy ra muộn hơn ở outer service.

**Không dùng giá trị `COUNT` hoặc ID trả về bên trong method làm bằng chứng transaction ngoài cùng đã commit.**

### 11.1. `save()` và `saveAndFlush()` là gì?

Với Spring Data JPA:

~~~java
PurchaseOrder saved = repository.save(order);
~~~

`save` dựa trên entity state để gọi `persist` hoặc `merge`, không phải API cam kết transaction vừa kết thúc.

~~~java
PurchaseOrder saved = repository.saveAndFlush(order);
~~~

`saveAndFlush` yêu cầu flush sau khi lưu. Nhưng **flush không phải commit**; nếu transaction ngoài cùng rollback, tác động SQL bị hủy.

Nếu service cần chắc chắn một query tiếp theo đã nhìn thấy trạng thái mới, `saveAndFlush` hoặc `entityManager.flush()` có thể giúp tạo ranh giới đồng bộ. Nhưng không nên flush vô điều kiện mỗi lần sửa nếu không có yêu cầu quan sát/constraint cụ thể, vì có thể làm tăng số lần đồng bộ và giảm hiệu quả batching.

### 11.2. `@Transactional(readOnly = true)` không thay thế hiểu biết về flush

Một số cấu hình Spring/Hibernate tối ưu transaction đọc bằng việc thay đổi behavior flush hoặc dirty checking. Nếu một method được đánh dấu readOnly nhưng lại sửa managed entity, không nên dựa vào hành vi “có vẻ vẫn lưu” hoặc “có vẻ không lưu”.

Hãy khai báo transaction đọc/ghi đúng theo nghiệp vụ và không dùng COMMIT như một cách che giấu thao tác ghi trong read-only workflow.

### 11.3. Transaction propagation

Ví dụ:

~~~java
@Transactional
public void checkout(Long orderId) {
    orderService.markPaidAndCount(orderId);
    shippingService.reserveShipment(orderId);
}
~~~

Nếu các service cùng tham gia transaction ngoài bằng propagation `REQUIRED`, thao tác flush có thể xảy ra trong service con, nhưng commit thuộc outer transaction. Nếu bước reserveShipment ném exception làm transaction rollback, những SQL đã flush trước đó cũng bị rollback.

Flush mode không thay đổi quy tắc transaction propagation.

## 12. Có thể có INSERT trước commit ngay khi dùng COMMIT

Một câu khẳng định sai phổ biến:

> “Dùng `FlushModeType.COMMIT` thì không có SQL nào được gửi trước commit.”

Không đúng. Có nhiều lý do SQL có thể xảy ra sớm:

- `entityManager.flush()` được gọi tường minh.
- Một chiến lược sinh khóa như `GenerationType.IDENTITY` cần thực thi `INSERT` để nhận generated key, tùy provider.
- Provider có cơ chế đồng bộ hoặc thực thi SQL riêng được phép theo đặc tả.
- Một số operation khác đòi hỏi tương tác với database.
- Query riêng có override `AUTO`, trong khi EntityManager là COMMIT.

Ví dụ IDENTITY:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Provider thường phải insert để nhận giá trị ID từ cột identity của database. Vì vậy, lệnh INSERT có thể xuất hiện trước commit dù EntityManager được đặt COMMIT.

Tương tự, một SEQUENCE:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
~~~

có thể khiến provider gọi sequence để lấy ID từ sớm. **Gọi sequence không đồng nghĩa flush một INSERT của entity**. Không dùng log `SELECT nextval(...)` để suy ra toàn bộ dữ liệu entity đã được ghi.

### 12.1. Vì sao điều này quan trọng khi benchmark?

Nếu một test đo rằng với IDENTITY, AUTO và COMMIT đều phát INSERT ngay lúc `persist`, không thể suy ra flush mode vô tác dụng. Cần đo thêm thay đổi managed, nhiều query liên tiếp, các association và thời điểm flush/commit.

Ngược lại, nếu thử với SEQUENCE và thấy COMMIT phát ít INSERT trước truy vấn hơn, đó có thể là tối ưu provider cụ thể, không phải bảo đảm JPA về số lần gửi SQL.

## 13. Flush mode khi transaction chưa hoạt động hoặc context chưa tham gia transaction

`flush()` không phải một thao tác độc lập có thể ghi thay đổi mà không có transaction phù hợp.

Trong JPA thông thường, yêu cầu flush khi không có transaction đang hoạt động hoặc persistence context chưa tham gia transaction có thể dẫn tới `TransactionRequiredException` hoặc lỗi transaction phù hợp.

Ví dụ **không phải cách làm đúng**:

~~~java
EntityManager em = emf.createEntityManager();

PurchaseOrder order =
    new PurchaseOrder(new BigDecimal("10000.00"));

em.persist(order);
em.flush(); // Không có transaction resource-local đã begin.
~~~

Với resource-local transaction, phải bắt đầu transaction:

~~~java
EntityTransaction tx = em.getTransaction();

tx.begin();
em.persist(order);
em.flush();
tx.commit();
~~~

Trong JTA hoặc container-managed transaction, cần có transaction đang hoạt động và entity manager joined phù hợp. Không dùng `getTransaction()` nếu entity manager thuộc JTA mà framework/container đang quản lý.

### 13.1. AUTO không tự tạo transaction

Nếu ứng dụng chỉ thực hiện một SELECT ngoài transaction, việc EntityManager có AUTO không có nghĩa provider tự bắt đầu transaction ghi và flush các pending changes bằng mọi giá. Nghĩa vụ đồng bộ của AUTO gắn với ngữ cảnh transaction mà persistence context đã tham gia, theo các quy tắc của JPA.

### 13.2. Unsynchronized persistence context

JPA có `SynchronizationType.UNSYNCHRONIZED` cho các tình huống nâng cao. Một persistence context có thể tồn tại mà chưa tham gia transaction, và cần `joinTransaction()` trong môi trường phù hợp trước khi flush các thay đổi với transaction.

Vì vậy, khi quan sát AUTO “không flush như mong muốn”, phải xem cả:

- Có transaction thực sự đang hoạt động không?
- EntityManager có thuộc đúng persistence context không?
- Context đã tham gia transaction chưa?
- Query có override flush mode hay không?
- Có thay đổi pending nào có thể ảnh hưởng query không?

Không đổ lỗi ngay cho `FlushModeType` mà bỏ qua các điều kiện transaction.

## 14. Flush, visibility và isolation của database là hai tầng khác nhau

Giả sử Transaction A sửa đơn hàng rồi flush:

~~~text
Transaction A                         Transaction B
-----------------------------------   ----------------------------------
BEGIN                                 BEGIN
UPDATE order SET status = 'PAID'
(được gửi bởi flush)
SELECT order -> thấy PAID             SELECT order -> thường vẫn thấy NEW
                                      dưới READ COMMITTED
COMMIT
                                      SELECT mới -> có thể thấy PAID
                                      tùy isolation/snapshot
~~~

Giải thích:

1. **Flush** chuyển pending SQL của A tới database.
2. **Transaction A** có thể đọc lại những thay đổi do chính nó đã ghi.
3. **Transaction B** được bảo vệ bởi isolation, thường chưa thấy thay đổi chưa commit của A.
4. **Commit** mới xác nhận tác động của A.
5. Nếu B đang ở snapshot isolation/repeatable read, một truy vấn sau commit của A có thể vẫn nhìn snapshot cũ trong transaction B.

Flush mode điều chỉnh xử lý truy vấn trong persistence context, không ghi đè quy tắc isolation của database. Đừng nghĩ AUTO khiến mọi transaction khác tự động nhìn thấy dữ liệu pending.

### 14.1. First-level cache làm tình hình dễ nhầm

`EntityManager.find` có thể trả entity đang managed ngay từ persistence context. Nếu field trong Java đã đổi, code gọi getter có thể thấy giá trị mới, dù chưa flush và chưa commit.

Ngược lại, một truy vấn aggregate hay native SQL có thể phụ thuộc trạng thái tại database. Khi COMMIT chưa flush, hai đường đọc có thể không khớp theo điều ứng dụng tưởng tượng.

Nên phân biệt ba lớp quan sát:

~~~text
(1) Managed entity trong Java
(2) SQL state đã flush trong transaction hiện tại
(3) Committed state mà các transaction khác có thể quan sát
~~~

`FlushModeType` nằm chủ yếu ở ranh giới (1) → (2) khi query và commit; database isolation/transaction quyết định (2) → (3).

## 15. Truy vấn JPQL, Criteria và native SQL

### 15.1. JPQL

Ví dụ:

~~~java
Long count = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o " +
    "WHERE o.status = :status",
    Long.class
)
.setParameter("status", OrderStatus.PAID)
.getSingleResult();
~~~

JPQL làm việc với entity và thuộc tính mapped. Provider có metadata để xác định những thay đổi nào có thể ảnh hưởng truy vấn và có thể tối ưu flush.

AUTO phải bảo đảm ngữ nghĩa visibility thích hợp; COMMIT không bảo đảm kết quả phản ánh pending changes khi chưa flush.

### 15.2. Criteria API

Criteria cũng là truy vấn JPA; ví dụ ý tưởng:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<PurchaseOrder> root = cq.from(PurchaseOrder.class);

cq.select(cb.count(root));
cq.where(cb.equal(
    root.get("status"),
    OrderStatus.PAID
));

Long count = em.createQuery(cq).getSingleResult();
~~~

Query tạo từ Criteria vẫn có thể được cấu hình flush mode:

~~~java
TypedQuery<Long> query = em.createQuery(cq);
query.setFlushMode(FlushModeType.AUTO);
Long count = query.getSingleResult();
~~~

Nó không phải một cơ chế bỏ qua flush mode; bản chất vẫn là JPA query.

### 15.3. Native SQL

Một truy vấn native:

~~~java
Object result = em.createNativeQuery(
    "SELECT COUNT(*) FROM purchase_order WHERE status = 'PAID'"
).getSingleResult();
~~~

có thể có cách kích hoạt flush khác JPQL vì provider khó phân tích chính xác các bảng/ảnh hưởng của SQL tùy ý. Hibernate hoặc provider khác có thể có hành vi khác nhau giữa API JPA và native Session API, phiên bản và cách đồng bộ query spaces.

Vì vậy, **không suy ra quy tắc cụ thể “native query luôn flush” hay “native query không bao giờ flush”** cho mọi provider. Nếu kết quả native query bắt buộc phản ánh pending entity changes, cách đơn giản, rõ ràng hơn là:

~~~java
em.flush();

Object result = em.createNativeQuery(
    "SELECT COUNT(*) FROM purchase_order WHERE status = 'PAID'"
).getSingleResult();
~~~

Điều này vẫn cần transaction phù hợp và không thay thế commit.

### 15.4. JDBC thao tác trực tiếp bên ngoài persistence context

Nếu ứng dụng dùng JDBC để thay đổi bảng rồi tiếp tục dùng entity managed, JPA persistence context có thể giữ state cũ. Flush mode **không tự đồng bộ ngược từ JDBC vào managed objects**.

Tùy tình huống, có thể cần:

- Thiết kế thứ tự thao tác và transaction nhất quán.
- `flush()` trước khi JDBC đọc trạng thái JPA chưa đồng bộ.
- `refresh(entity)` để tải lại một entity managed khi phù hợp.
- `clear()` để bỏ các managed state cũ và đọc lại nếu cần.
- Tránh trộn nhiều đường ghi lên cùng dữ liệu không có chiến lược đồng bộ.

Nhớ rằng `clear()` detach các entity và có thể làm mất những thay đổi **chưa flush**. Không gọi clear như một cách “làm mới tất cả” khi còn công việc đang chờ.

## 16. Bulk UPDATE/DELETE và persistence context

JPQL bulk DML khác việc sửa từng managed entity:

~~~java
int changed = em.createQuery(
    "UPDATE PurchaseOrder o " +
    "SET o.status = :paid " +
    "WHERE o.status = :newStatus"
)
.setParameter("paid", OrderStatus.PAID)
.setParameter("newStatus", OrderStatus.NEW)
.executeUpdate();
~~~

Bulk update được thực thi trực tiếp đối với database và không tự đồng bộ mọi instance `PurchaseOrder` đã managed trong context như dirty checking từng entity. Persistence context có thể tiếp tục giữ object với trạng thái cũ sau bulk update.

Một quy trình có chủ đích khi cần bulk DML:

~~~java
tx.begin();

// Đẩy pending changes để DB ở trạng thái phù hợp trước bulk DML.
em.flush();

int changed = em.createQuery(
    "UPDATE PurchaseOrder o " +
    "SET o.status = :paid " +
    "WHERE o.status = :newStatus"
)
.setParameter("paid", OrderStatus.PAID)
.setParameter("newStatus", OrderStatus.NEW)
.executeUpdate();

// Chỉ clear khi đã xử lý mọi pending changes cần giữ.
// clear làm detach các entity đang managed.
em.clear();

tx.commit();
~~~

Ở đây `clear()` giúp tránh tiếp tục sử dụng entity cached không khớp với dữ liệu sau bulk update. Cần hiểu rằng bulk DML có quy tắc riêng về optimistic locking, lifecycle callbacks và các association; không được coi nó như gọi setter cho từng entity.

**Flush mode không giải quyết hoàn toàn vấn đề stale persistence context sau bulk DML.** Đây là một lớp đồng bộ khác.

## 17. Optimistic locking, constraint và lỗi lúc flush

Một lợi ích của flush tường minh là phát hiện một số lỗi SQL trước khi đến cuối transaction.

### 17.1. Constraint có thể báo lỗi tại flush

Ví dụ tạo entity có một mã đơn hàng nghiệp vụ phải UNIQUE:

~~~java
@Column(name = "external_code", nullable = false, unique = true)
private String externalCode;
~~~

Nếu hai transaction cùng chèn mã trùng, một transaction có thể bị DB từ chối khi `INSERT` được thực thi, có thể tại flush hoặc commit.

~~~java
tx.begin();
em.persist(order);
em.flush(); // Có thể phát hiện vi phạm UNIQUE tại đây.
~~~

Nhưng **không phải mọi lỗi được kiểm tra tại flush**. Constraint deferred, xung đột serialization hoặc lỗi kết nối lúc commit có thể phát sinh muộn hơn.

### 17.2. Optimistic locking cũng có thể lỗi lúc đồng bộ

Nếu entity có `@Version`, provider thường tạo SQL update có điều kiện version. Khi state đã bị transaction khác thay đổi, việc đồng bộ update có thể làm phát sinh `OptimisticLockException` hoặc exception tương đương.

Lỗi có thể được phát hiện ở flush hoặc commit, tùy thời điểm update thực sự xảy ra. Đổi AUTO sang COMMIT có thể làm lỗi chỉ xuất hiện muộn hơn nếu SQL được trì hoãn; không có nghĩa COMMIT vô hiệu hóa optimistic locking.

### 17.3. Không tiếp tục dùng transaction lỗi như chưa có gì

Khi flush thất bại với `PersistenceException` hoặc lỗi DB nghiêm trọng, transaction có thể đã bị đánh dấu rollback-only và persistence context có thể không còn ở trạng thái an toàn để tiếp tục thao tác.

Trong resource-local transaction, thường xử lý:

~~~java
try {
    tx.begin();

    em.persist(order);
    em.flush();

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

Không “bắt exception rồi tiếp tục query” mà không xem transaction status và không giải quyết nguyên nhân gốc.

### 17.4. Flush nhiều lần không làm commit nhiều lần

~~~java
tx.begin();
em.persist(order1);
em.flush();

em.persist(order2);
em.flush();

tx.rollback();
~~~

Cả hai lần flush có thể đã gửi INSERT, nhưng rollback hủy các thay đổi thuộc transaction. Thêm nhiều `flush()` không tạo ra những transaction commit riêng biệt.

## 18. Hiệu năng: AUTO có thể tạo thêm các đợt đồng bộ

Giả sử service lưu nhiều entity, cứ sau một ít insert lại chạy query:

~~~java
for (int i = 0; i < 1000; i++) {
    em.persist(new PurchaseOrder(
        new BigDecimal("10000.00")
    ));

    if (i % 10 == 0) {
        em.createQuery(
            "SELECT COUNT(o) FROM PurchaseOrder o",
            Long.class
        ).getSingleResult();
    }
}
~~~

Với AUTO, query `COUNT` có thể buộc provider đồng bộ các pending inserts liên quan nhiều lần. Điều này có thể:

- Gây thêm round trip tới DB.
- Làm giảm khả năng gom nhiều insert/update trong một batch.
- Đưa một số lỗi constraint lên sớm hơn.
- Tăng công việc SQL trước khi logic nghiệp vụ kết thúc.

Nhưng đổi sang COMMIT **không phải tối ưu vô hại**, vì count trước commit sẽ không còn được bảo đảm phản ánh các entity vừa persist.

### 18.1. Tối ưu bằng cách giảm truy vấn, không chỉ đổi mode

Nếu mục tiêu chỉ là đếm những item vừa tạo, có thể đếm ở bộ nhớ khi hợp lý:

~~~java
int createdCount = 0;

for (OrderRequest request : requests) {
    em.persist(toEntity(request));
    createdCount++;
}
~~~

Nếu cần tổng số đơn hiện có trong DB cộng với số vừa tạo, phải xem isolation, concurrency và đặc tính nghiệp vụ; phép cộng đơn giản có thể không tương đương một query nhất quán.

Các cách khác:

- Gom các thao tác ghi trước rồi thực hiện query sau.
- Dùng một flush tường minh tại điểm cần đồng bộ thay vì query xen kẽ liên tục.
- Chọn batching/generator phù hợp, theo tài liệu provider.
- Sử dụng query projection/aggregate riêng khi thật sự cần.
- Đo số SQL và thời gian thực tế trước khi thay đổi flush mode.

### 18.2. Khi COMMIT có thể hợp lý

Một transaction có nhiều pending changes nhưng những query xen giữa **không được phép ảnh hưởng quyết định dựa trên thay đổi đó**, ví dụ đọc danh mục cấu hình độc lập.

~~~java
em.setFlushMode(FlushModeType.AUTO);

TypedQuery<ShippingRate> rateQuery = em.createQuery(
    "SELECT r FROM ShippingRate r " +
    "WHERE r.regionCode = :region",
    ShippingRate.class
);

rateQuery.setParameter("region", region);
rateQuery.setFlushMode(FlushModeType.COMMIT);

List<ShippingRate> rates = rateQuery.getResultList();
~~~

Đây là ví dụ về cách override riêng một query. Nó chỉ hợp lý nếu các thay đổi pending trong transaction **không thể tạo khác biệt nghiệp vụ cần quan sát** khi tính giá cước.

### 18.3. Benchmark đúng điều kiện

Để đánh giá hiệu năng, nên ghi nhận:

1. Số statement SQL và số batch.
2. Thời điểm query kích hoạt flush.
3. Khác biệt giữa JPQL, Criteria và native SQL.
4. Chiến lược sinh ID (SEQUENCE, IDENTITY, UUID...).
5. Kích thước persistence context và số entity dirty.
6. Cơ sở dữ liệu/driver/provider thực tế.
7. Số transaction, thời gian commit và lỗi constraint.

Không lấy một test đơn giản trên in-memory DB để khẳng định kết quả luôn giống PostgreSQL, MySQL, Oracle hay SQL Server.

## 19. Hibernate có nhiều flush mode hơn, nhưng JPA chuẩn chỉ có hai

Khi đọc tài liệu Hibernate, có thể gặp các chế độ như:

- `AUTO`
- `COMMIT`
- `ALWAYS`
- `MANUAL`

Đó là tập chế độ hoặc tên gọi của **API Hibernate cụ thể**, không phải toàn bộ `jakarta.persistence.FlushModeType`.

Trong JPA chuẩn:

~~~java
FlushModeType.AUTO
FlushModeType.COMMIT
~~~

là hai lựa chọn có tính di động. Nếu code unwrap `EntityManager` thành Hibernate `Session` và dùng flush mode riêng như MANUAL, behavior có thể khác và không còn di động giữa các JPA provider.

Ví dụ chỉ mang tính định hướng cho code phụ thuộc Hibernate:

~~~java
// Hibernate-specific, không phải JPA portable:
// Session session = em.unwrap(Session.class);
// session.setHibernateFlushMode(FlushMode.MANUAL);
~~~

Không nên kết luận rằng JPA COMMIT tương đương hoàn toàn Hibernate MANUAL hoặc ALWAYS chỉ từ tên gọi. Nếu dùng extension, cần đối chiếu tài liệu chính xác của phiên bản provider đang triển khai.

### 19.1. Flush mode của query trong Spring Data/Hibernate

Framework hoặc repository có thể áp dụng query hint, entity graph, read-only setting hoặc cấu hình riêng. Trong trường hợp có kết quả query gây ngạc nhiên, nên kiểm tra:

- EntityManager flush mode đang có hiệu lực.
- Query có override bằng `setFlushMode` hay không.
- Transaction có hoạt động và context joined không.
- Session/provider có setting ngoài JPA không.
- Các SQL `INSERT`/`UPDATE` có được gửi trước query không.
- Query đang chạy JPQL, native SQL hay thao tác trực tiếp JDBC.

Không suy đoán hành vi chỉ từ tên method repository.

## 20. Những tình huống ra quyết định

### Tình huống A — Ghi rồi cần query để quyết định tiếp

Ví dụ tạo đơn rồi truy vấn số đơn NEW của khách để áp dụng giới hạn.

**Ưu tiên:** AUTO hoặc flush tường minh trước truy vấn nếu EntityManager đang COMMIT. Nhưng còn phải bảo vệ concurrency bằng constraint/locking hoặc transaction isolation thích hợp; một count đúng trong transaction hiện tại chưa chắc ngăn hai request song song cùng vượt giới hạn.

### Tình huống B — Ghi nhiều, chỉ đọc dữ liệu độc lập

Ví dụ import hàng nghìn tồn kho rồi đọc bảng cấu hình thuế không phụ thuộc tồn kho.

**Có thể cân nhắc:** COMMIT ở query cụ thể, hoặc giữ AUTO nếu provider đã tối ưu không flush do dữ liệu không liên quan. Cần đo và bảo đảm query không phụ thuộc pending changes.

### Tình huống C — Muốn phát hiện FK/UNIQUE sớm

**Dùng:** `flush()` tường minh tại điểm có ý nghĩa, dù mode là AUTO hay COMMIT. Flush có thể phát hiện nhiều lỗi nhưng không cam kết mọi lỗi đã được loại trừ, và không commit transaction.

### Tình huống D — Chỉ cần ID sinh tự động

Không nên đồng nhất “đã có ID” với “đã flush” hoặc “đã commit”. SEQUENCE/UUID có thể cấp ID sớm; IDENTITY có thể phải INSERT sớm. Quyết định flush dựa trên nhu cầu đồng bộ, không chỉ dựa trên một kiểm tra `id != null`.

### Tình huống E — Báo cáo sau khi transaction hoàn tất

Nếu cần bảo đảm dữ liệu đã committed được báo cáo chính xác, thực hiện công việc ở ranh giới **sau commit thành công** hoặc transaction đọc tiếp theo tùy yêu cầu. AUTO không phải sự kiện after-commit.

### Tình huống F — Một truy vấn thống kê lớn không cần thay đổi pending

Có thể cân nhắc Query.setFlushMode(COMMIT) nếu ứng dụng chấp nhận semantics, nhưng không dùng COMMIT để “bắt” query phải đọc dữ liệu cũ. Nếu muốn snapshot ổn định, đó là chủ đề isolation/transaction/snapshot, không phải chỉ là flush mode.

## 21. Các nhầm lẫn phổ biến và cách hiểu đúng

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “AUTO flush trước mọi query.” | AUTO phải bảo đảm visibility của thay đổi liên quan; provider có thể flush hoặc dùng cách khác và không nhất thiết flush khi query không bị ảnh hưởng. |
| “COMMIT luôn đợi tới commit mới phát SQL.” | SQL có thể chạy sớm do explicit flush, IDENTITY hoặc cơ chế provider khác. |
| “COMMIT query chắc chắn không thấy entity mới persist.” | Visibility của pending changes trước flush là **không xác định** theo JPA; không được dựa vào kết quả cũ. |
| “Flush tương đương commit.” | Flush đồng bộ SQL; transaction vẫn có thể rollback. |
| “Có ID là entity đã được lưu vào DB.” | ID có thể được cấp trước INSERT, và INSERT có thể bị rollback. |
| “`find()` trả entity mới nên đã flush.” | First-level cache có thể trả managed entity mà không cần SQL. |
| “Đổi mode thành COMMIT là read-only.” | COMMIT không cấm các thao tác ghi hoặc dirty checking. |
| “`saveAndFlush()` đảm bảo dữ liệu đã commit.” | Nó yêu cầu flush, không kết thúc transaction ngoài. |
| “AUTO làm các transaction khác thấy thay đổi chưa commit.” | Database isolation vẫn kiểm soát visibility giữa transaction. |
| “Nếu flush thành công, commit chắc chắn thành công.” | Constraint deferred, locking, lỗi mạng và các vấn đề khác vẫn có thể xuất hiện. |
| “Entity đang managed luôn đồng bộ với bulk UPDATE.” | Bulk DML có thể khiến persistence context giữ stale state. |
| “JPA COMMIT là Hibernate MANUAL.” | Hai chế độ thuộc các API khác nhau và không có hợp đồng hoàn toàn tương đương. |
| “Để tăng hiệu năng chỉ cần đổi mọi query sang COMMIT.” | Việc đó đổi semantics visibility; nên thiết kế lại query/flush và đo thực tế. |
| “Clear context sau query sẽ tự giữ mọi thay đổi.” | `clear()` detach entity và có thể làm mất pending changes chưa flush. |

## 22. Bài tập thực hành

### Bài 1 — AUTO có nhất thiết phát SQL?

~~~java
em.setFlushMode(FlushModeType.AUTO);
tx.begin();

PurchaseOrder o =
    new PurchaseOrder(new BigDecimal("10000.00"));

em.persist(o);

Long count = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o",
    Long.class
).getSingleResult();
~~~

**Câu hỏi:** JPA có bắt buộc provider phát `INSERT` trước `SELECT COUNT` không?

**Đáp án:** Không bắt buộc một chuỗi SQL cụ thể. AUTO bắt buộc kết quả xử lý truy vấn phản ánh thay đổi pending liên quan. Flush trước query là cách thường gặp, nhưng provider có thể dùng phương pháp khác.

### Bài 2 — COMMIT có chắc trả count cũ?

~~~java
em.setFlushMode(FlushModeType.COMMIT);
tx.begin();

em.persist(new PurchaseOrder(
    new BigDecimal("10000.00")
));

Long count = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o",
    Long.class
).getSingleResult();
~~~

**Câu hỏi:** Có thể khẳng định `count` bằng số lượng trước khi persist không?

**Đáp án:** Không. JPA không xác định tác động của các thay đổi chưa flush tới truy vấn khi dùng COMMIT. Không viết logic phụ thuộc vào kết quả cũ hoặc mới được bảo đảm nếu chưa explicit flush.

### Bài 3 — Khi cần query phản ánh thay đổi với COMMIT

Service đặt `FlushModeType.COMMIT`, sửa một Order từ NEW sang PAID, rồi cần truy vấn tổng số PAID theo JPQL để ra quyết định.

**Câu hỏi:** Làm gì để có ranh giới đồng bộ rõ ràng?

**Đáp án:** Gọi `entityManager.flush()` trước query hoặc cấu hình query cụ thể với AUTO, trong transaction đã tham gia phù hợp. Explicit flush giúp bảo đảm SQL đã được đồng bộ nhưng không thay thế commit.

### Bài 4 — Override theo query

~~~java
em.setFlushMode(FlushModeType.AUTO);

TypedQuery<Long> q = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o",
    Long.class
);

q.setFlushMode(FlushModeType.COMMIT);
~~~

**Câu hỏi:** Mode có hiệu lực của `q` là gì? Các query khác của EntityManager cũng thành COMMIT không?

**Đáp án:** `q` dùng COMMIT. EntityManager vẫn ở AUTO, nên những query khác không override tiếp tục dùng AUTO.

### Bài 5 — Có SQL trước commit

Mapping dùng `GenerationType.IDENTITY`, EntityManager đặt `FlushModeType.COMMIT`, sau `persist()` log hiển thị INSERT.

**Câu hỏi:** Đây có nhất thiết là lỗi provider không?

**Đáp án:** Không. IDENTITY thường cần INSERT sớm để nhận generated key; COMMIT không bảo đảm trì hoãn tất cả SQL cho tới commit.

### Bài 6 — Rollback sau flush

~~~java
tx.begin();
em.persist(order);
em.flush();
tx.rollback();
~~~

**Câu hỏi:** Tại sao bản ghi có thể không tồn tại sau rollback dù log có INSERT?

**Đáp án:** Flush thực thi SQL trong transaction chưa commit. Rollback hủy các thay đổi dữ liệu thuộc transaction theo ngữ nghĩa database.

### Bài 7 — Query thấy state mới nhưng transaction khác không thấy

Transaction A đổi status và flush. Transaction B đọc ở READ COMMITTED trước khi A commit.

**Câu hỏi:** AUTO có buộc B thấy status mới không?

**Đáp án:** Không. AUTO điều chỉnh visibility của pending changes trong xử lý query của persistence context/transaction phù hợp; isolation giữa hai transaction vẫn thuộc database.

### Bài 8 — Bulk update và stale entity

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, 10L);

em.createQuery(
    "UPDATE PurchaseOrder o " +
    "SET o.status = :paid WHERE o.id = :id"
)
.setParameter("paid", OrderStatus.PAID)
.setParameter("id", 10L)
.executeUpdate();
~~~

**Câu hỏi:** `order.getStatus()` có bắt buộc đổi sang PAID trong managed object không?

**Đáp án:** Không. Bulk DML không đồng bộ trực tiếp mọi entity managed. Cần thiết kế `refresh`, `clear` hoặc tách persistence context theo tình huống, sau khi xử lý pending changes thích hợp.

### Bài 9 — AUTO ảnh hưởng batching

Một service persist 10.000 entity và cứ 5 entity lại chạy JPQL `COUNT` trên cùng loại.

**Câu hỏi:** Tại sao có thể chậm và xử lý thế nào?

**Đáp án:** AUTO có thể phải đồng bộ các pending changes trước các query liên quan, làm tăng đợt flush và giảm khả năng batch. Có thể tổ chức lại thao tác để giảm query xen kẽ, đặt ranh giới flush rõ ràng hoặc cân nhắc query-level COMMIT nếu query không cần nhìn thấy pending changes. Phải đo thực tế và không hy sinh tính đúng nghiệp vụ.

## 23. Checklist thiết kế khi chọn flush mode

Trước khi đổi AUTO sang COMMIT cho một transaction/query, nên trả lời:

1. **Có những entity mới, bị sửa hoặc bị xóa nào đang pending?**
2. **Truy vấn tiếp theo có thể bị ảnh hưởng bởi chúng không?**
3. **Logic nghiệp vụ có cần truy vấn thấy các thay đổi đó trước commit không?**
4. **Transaction và EntityManager có đang được quản lý/join đúng không?**
5. **Có query-level override nào đang áp dụng không?**
6. **Có native SQL, JDBC trực tiếp hoặc bulk DML làm khác biệt trạng thái không?**
7. **Có cần phát hiện constraint/optimistic-locking sớm bằng flush tường minh không?**
8. **Có đang dựa vào IDENTITY/SEQUENCE khiến SQL xuất hiện sớm không?**
9. **Có rủi ro N+1, query xen kẽ hoặc batching khiến AUTO gây chi phí?**
10. **Có integration test trên DB/provider thật xác nhận hành vi cần thiết không?**

Nếu tính đúng của nghiệp vụ phụ thuộc vào kết quả query sau thay đổi managed, hãy chọn **AUTO hoặc explicit flush** thay vì dựa vào những tác động chưa được đặc tả của COMMIT.

Nếu query độc lập với các thay đổi đang chờ và profiling cho thấy auto flush thực sự có chi phí, **COMMIT có thể là tối ưu có chủ đích**, tốt nhất giới hạn ở phạm vi nhỏ nhất cần thiết.

## 24. Tóm tắt

~~~text
Persistence context có thay đổi pending
                 |
                 v
      Chạy một JPA query trước commit
                 |
           +-----+-----+
           |           |
          AUTO        COMMIT
           |           |
           v           v
  Provider phải    Visibility của pending
  bảo đảm query    changes trong query
  phản ánh thay    chưa flush là không
  đổi liên quan    được JPA bảo đảm
           |           |
           +-----+-----+
                 |
                 v
         Explicit em.flush()
         (nếu ứng dụng gọi)
                 |
                 v
         SQL đồng bộ trong
         transaction đang mở
                 |
        +--------+--------+
        |                 |
      COMMIT            ROLLBACK
      thành công        |
        |                 |
        v                 v
  Dữ liệu được       Thay đổi dữ liệu
  xác nhận           giao dịch bị hủy
~~~

Ghi nhớ những nguyên tắc cuối cùng:

- **`FlushModeType.AUTO` là mặc định của JPA.** Nó bảo đảm thay đổi managed có thể ảnh hưởng query được phản ánh trong xử lý query, nhưng không bắt buộc flush trước mọi query.
- **`FlushModeType.COMMIT` không bảo đảm query trước commit nhìn thấy pending changes chưa flush.** Đừng hiểu nó là “luôn query ra dữ liệu cũ”.
- **`flush()` luôn khác `commit()`.** Flush đồng bộ SQL vào transaction, transaction vẫn có thể rollback.
- **COMMIT không cấm SQL chạy sớm.** `IDENTITY`, explicit flush hoặc những cơ chế provider khác vẫn có thể khiến SQL phát sinh trước commit.
- **Có thể cấu hình mode ở `EntityManager` hoặc từng `Query`.** Query-level override giúp giới hạn thay đổi ngữ nghĩa.
- **Entity managed trong first-level cache khác kết quả JPQL aggregate và khác dữ liệu committed.** Đừng dùng một cách đọc để suy luận quá mức về cách đọc khác.
- **Flush mode không thay thế transaction isolation, optimistic locking, constraint, read-only hay quản lý vòng đời entity.**
- **Tối ưu hiệu năng phải dựa trên workload và SQL thực tế**, không chỉ đổi AUTO thành COMMIT theo cảm tính.

Nắm vững vai trò của `AUTO` và `COMMIT` giúp thiết kế các luồng “ghi rồi đọc” nhất quán trong JPA, kiểm soát thời điểm đồng bộ SQL và tránh nhầm lẫn giữa **trạng thái trong bộ nhớ**, **dữ liệu đã flush** và **dữ liệu thực sự được commit**.
