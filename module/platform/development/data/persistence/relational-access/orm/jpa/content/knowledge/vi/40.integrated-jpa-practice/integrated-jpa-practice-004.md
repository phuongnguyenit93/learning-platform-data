# Cập nhật entity đang được quản lý và quan sát thời điểm SQL phát sinh

Khi làm việc với Jakarta Persistence (JPA), một thay đổi đơn giản như `product.setName("Bàn phím mới")` có thể khiến cơ sở dữ liệu được cập nhật dù chương trình không gọi `update()` hay `save()`. Tuy nhiên, **câu lệnh SQL `UPDATE` thường không được gửi ngay tại thời điểm gọi setter**. JPA theo dõi thay đổi của entity trong *persistence context*, sau đó đồng bộ thay đổi xuống cơ sở dữ liệu ở một thời điểm phù hợp, thường là lúc *flush*.

Đây là thực hành tổng hợp để thấy rõ mối liên hệ giữa:

- **Entity đang được quản lý (managed entity)** và *dirty checking*.
- **Persistence context**, trạng thái entity và snapshot dữ liệu ban đầu.
- **Flush** (đồng bộ thao tác đang chờ) và **commit** (hoàn tất giao dịch).
- Truy vấn JPQL, `EntityManager.flush()`, cấu hình flush mode và thời điểm SQL thật sự được phát ra.
- Logging SQL và bind parameter để quan sát hành vi của JPA provider, điển hình là Hibernate trong Spring Boot.

## 1. Dự đoán kết quả trước khi chạy

Xét đoạn code nằm **trong một transaction**:

```java
CatalogProduct product = entityManager.find(CatalogProduct.class, 1L);
product.rename("Bàn phím cơ");
// Không gọi repository.save(product)
// Không gọi entityManager.merge(product)
```

Nếu `product` là một entity *managed* và JPA phát hiện thuộc tính `name` thay đổi, provider có thể sinh SQL khi flush:

```sql
UPDATE catalog_products
SET name = ?, version = ?
WHERE id = ? AND version = ?;
```

Đây là **SQL minh họa**, không phải cam kết về thứ tự cột hoặc số lượng statement: Hibernate có thể cập nhật thêm các cột được mapping, batching có thể thay đổi cách gửi JDBC và câu SQL còn tùy cấu hình mapping/provider.

Một trình tự hay gặp:

```text
BEGIN TRANSACTION
  |
  |-- find(id) --------> SELECT ... FROM catalog_products
  |
  |-- setName(...) ----> Thay đổi object trong bộ nhớ
  |                      (chưa chắc có UPDATE)
  |
  |-- flush() ---------> UPDATE catalog_products ...
  |
  |-- commit() --------> COMMIT
  |
END TRANSACTION
```

Lưu ý: `flush()` **không phải** `commit()`. Sau khi flush, transaction vẫn có thể rollback, khiến những thay đổi SQL vừa được gửi không trở thành dữ liệu đã commit.

## 2. Chuẩn bị môi trường thực hành

Ví dụ sử dụng Java, Spring Boot 3.x, Spring Data JPA, Hibernate 6.x, JDBC driver cho PostgreSQL và một database thực hành. Phần API JPA chính dùng gói `jakarta.persistence`; không dùng `javax.persistence` của hệ Jakarta Persistence cũ.

Cần các dependency tương đương:

```text
spring-boot-starter-data-jpa
postgresql                 (runtime)
spring-boot-starter-test   (test)
```

Cấu hình tham khảo cho **môi trường phát triển riêng**:

```yaml
# application-local.yml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/jpa_lab
    username: jpa_lab
    password: ${JPA_LAB_PASSWORD}
  jpa:
    hibernate:
      ddl-auto: create-drop
    properties:
      hibernate:
        format_sql: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

`ddl-auto: create-drop` chỉ phù hợp với database thử nghiệm có thể xóa. Trong môi trường dùng dữ liệu thật, cần migrations có kiểm soát (ví dụ Flyway/Liquibase) và thường không để Hibernate tự xóa/tạo lại bảng.

Với Spring Boot dùng Hibernate 6, logger `org.hibernate.SQL` hiển thị SQL, còn `org.hibernate.orm.jdbc.bind` cho biết giá trị tham số bind ở mức TRACE. Không bật log bind chứa dữ liệu nhạy cảm trong production. Tên logger có thể khác ở Hibernate 5 hoặc các provider khác.

Ví dụ log có thể trông như:

```text
DEBUG org.hibernate.SQL : select ... from catalog_products where id=?
TRACE org.hibernate.orm.jdbc.bind : binding parameter (1:BIGINT) <- [1]

DEBUG org.hibernate.SQL : update catalog_products
                          set name=?, price=?, version=?
                          where id=? and version=?
```

Thời điểm câu SQL hiện ra trong log phản ánh lúc provider chuẩn bị/thực thi câu lệnh ở tầng JDBC; đó không phải bằng chứng transaction đã commit. Nếu driver hoặc provider bật JDBC batching, muốn đối chiếu *số lần thực thi thật sự* cần thêm thống kê JDBC, tracing hoặc quan sát database.

## 3. Tạo entity dùng để theo dõi dirty checking

Thiết kế một entity tối giản có `name`, `price` và `version`:

```java
package com.example.jpa.lab;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "catalog_products")
public class CatalogProduct {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "catalog_product_seq_gen")
    @SequenceGenerator(
        name = "catalog_product_seq_gen",
        sequenceName = "catalog_product_seq",
        allocationSize = 1)
    private Long id;

    @Column(name = "name", nullable = false, length = 150)
    private String name;

    @Column(name = "price", nullable = false,
            precision = 12, scale = 2)
    private BigDecimal price;

    @Version
    @Column(name = "row_version", nullable = false)
    private long version;

    protected CatalogProduct() {
        // Bắt buộc có constructor không tham số cho JPA.
    }

    public CatalogProduct(String name, BigDecimal price) {
        this.name = Objects.requireNonNull(name);
        this.price = Objects.requireNonNull(price);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public long getVersion() {
        return version;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }
        this.name = newName;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        this.price = newPrice;
    }
}
```

**Các quyết định trong mapping:**

- `@Entity` và `@Id` đánh dấu entity và danh tính.
- `@GeneratedValue(strategy = SEQUENCE)` dùng sequence; trên PostgreSQL Hibernate có thể lấy giá trị sequence khi `persist()`, còn `INSERT` thường chờ flush. Điều này giúp phân biệt thao tác cấp ID và thao tác ghi row.
- `@Version` bật optimistic locking. Với Hibernate, `UPDATE` có thể kèm điều kiện `WHERE id=? AND row_version=?` và tăng phiên bản khi thực hiện thay đổi. Nó cũng giúp thí nghiệm dễ quan sát.
- `rename()` và `changePrice()` chỉ thay field của Java object; tự thân chúng không gọi JDBC.
- Không cần phương thức `save()` trong entity. Entity được quản lý bởi `EntityManager` là thành phần điều phối việc ghi.

Mô hình ví dụ giả định DB có hỗ trợ sequence, như PostgreSQL. Với MySQL hoặc DBMS khác, chiến lược sinh ID và DDL có thể phải điều chỉnh.

## 4. Thí nghiệm chính: thay đổi managed entity rồi flush

Tạo test tích hợp dùng `EntityManager` trực tiếp để kiểm soát điểm quan sát. `@SpringBootTest` tải ứng dụng và cấu hình persistence; `@Transactional` giữ một transaction cho phương thức test.

```java
package com.example.jpa.lab;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Transactional
class ManagedEntitySqlTimingTest {

    @PersistenceContext
    EntityManager em;

    @Test
    void updatesManagedEntityAtFlush() {
        // 1) Tạo dữ liệu cho riêng thí nghiệm.
        CatalogProduct seed = new CatalogProduct(
            "Bàn phím thường",
            new BigDecimal("350000.00"));
        em.persist(seed);
        em.flush();
        Long id = seed.getId();

        // 2) Bỏ entity seed khỏi persistence context,
        //    để lệnh find tiếp theo thực sự phải đọc DB.
        em.clear();

        // 3) SELECT và đưa entity vào trạng thái MANAGED.
        CatalogProduct managed = em.find(CatalogProduct.class, id);
        assertThat(em.contains(managed)).isTrue();
        System.out.println("A: sau find");

        // 4) Chỉ đổi object trong bộ nhớ.
        managed.rename("Bàn phím cơ");
        System.out.println("B: sau rename");

        // 5) Đồng bộ các thay đổi đang chờ vào DB.
        em.flush();
        System.out.println("C: sau flush");

        // 6) Xóa bộ nhớ context rồi đọc lại từ DB.
        em.clear();
        CatalogProduct reloaded = em.find(CatalogProduct.class, id);

        assertThat(reloaded.getName()).isEqualTo("Bàn phím cơ");
        assertThat(em.contains(reloaded)).isTrue();
    }
}
```

### Phân tích từng mốc

| Mốc | Code | Trạng thái | SQL thường thấy |
| --- | --- | --- | --- |
| Tạo dữ liệu | `persist(seed)` | seed chuyển sang managed | Có thể lấy sequence ngay; `INSERT` tùy provider/chiến lược ID |
| Đưa seed xuống DB | `flush()` | insert được đồng bộ trong transaction | `INSERT` nếu chưa phát ra |
| Xóa context | `clear()` | seed trở thành detached | Không cần `DELETE` hoặc `UPDATE` |
| Nạp lại | `find(id)` | Một managed entity mới | `SELECT` vì context rỗng |
| Đổi field | `rename(...)` | Vẫn managed, trở thành dirty | Thông thường chưa có `UPDATE` |
| Đồng bộ | `flush()` | Provider so sánh thay đổi và đồng bộ SQL | `UPDATE` |
| Nạp lại lần nữa | `clear(); find(id)` | Đọc từ DB thay vì context cũ | `SELECT` và nhận tên mới |

Tại thời điểm in chữ **B**, Hibernate trong cấu hình thông thường vẫn chưa gửi `UPDATE`, vì chưa có flush nào sau setter. Khi gọi `em.flush()`, log `UPDATE` xuất hiện **trước** dòng in chữ **C** nếu SQL được thực thi thành công. Đó là bằng chứng dễ quan sát nhất về thời điểm flush.

Vì test có `@Transactional`, framework kiểm thử Spring thông thường **rollback transaction ở cuối test**. Việc truy vấn sau `flush()` nhìn thấy giá trị mới chỉ chứng minh database đã nhận thay đổi trong **transaction hiện tại**, không chứng minh đã commit hoặc người dùng ở transaction khác nhìn thấy thay đổi.

### Log mẫu rút gọn

```text
Hibernate: select nextval('catalog_product_seq')
Hibernate: insert into catalog_products
           (name,price,row_version,id) values (?,?,?,?)
Hibernate: select ... from catalog_products where id=?
A: sau find
B: sau rename
Hibernate: update catalog_products
           set name=?,price=?,row_version=?
           where id=? and row_version=?
C: sau flush
Hibernate: select ... from catalog_products where id=?
```

Đây là **ví dụ log theo hành vi thường gặp**, không phải kết quả chạy thực tế được chép lại. SQL có thể khác về tên alias, thứ tự cột, cú pháp sequence, batching và cấu hình provider.

## 5. Dirty checking hoạt động ra sao?

Trong persistence context, EntityManager quản lý danh tính và trạng thái của entity. Khi load entity, provider thường giữ thông tin cần thiết để phát hiện thay đổi; với Hibernate, cơ chế có thể dựa trên snapshot hoặc bytecode enhancement tùy cấu hình.

```text
Sau find():
  DB                managed entity trong persistence context
  name = "A"  --->  name = "A"
                    snapshot ~ "A"

Sau rename("B"):
  DB                managed entity
  name = "A"        name = "B"
                    snapshot ~ "A"

Khi flush():
  So sánh trạng thái -> dirty -> gửi UPDATE
  DB (trong transaction) : name = "B"
```

Không có lời gọi `update()` trên `EntityManager`: Jakarta Persistence quản lý **identity map** và dirty checking của các instance đang managed.

Nếu trong **cùng một persistence context** gọi:

```java
CatalogProduct first = em.find(CatalogProduct.class, id);
CatalogProduct second = em.find(CatalogProduct.class, id);

assert first == second;
```

thì thông thường `first` và `second` trỏ tới cùng một Java object, bởi persistence context quản lý một instance cho một entity identity. `find()` lần thứ hai thường không cần `SELECT` mới. Điều này cũng giải thích tại sao dùng `find()` ngay sau setter **không phải cách đáng tin cậy để kiểm tra giá trị đã ghi vào DB**: nó có thể chỉ trả lại object từ bộ nhớ.

Để quan sát nội dung thực ở DB bằng EntityManager, cần cân nhắc `flush()` và `clear()`, hoặc đọc bằng một transaction/connection khác với mức isolation phù hợp. Việc đọc bằng connection khác **trước commit** không nhất thiết thấy dữ liệu vừa flush.

### Không phải mọi setter đều sinh UPDATE

Ví dụ:

```java
managed.rename("Bàn phím thường");
em.flush();
```

Nếu tên vốn đã là `"Bàn phím thường"`, Hibernate có thể không phát `UPDATE` khi nhận thấy không có trạng thái cần thay đổi. Tương tự, sửa giá trị rồi đổi trở lại giá trị ban đầu trước flush có thể khiến không có update ở bước cuối. Chi tiết so sánh kiểu dữ liệu và enhanced dirty tracking phụ thuộc provider/mapping; không suy đoán số câu SQL chỉ từ số lần gọi setter.

### UPDATE có thể chứa cả cột không đổi

Mặc định, Hibernate có thể tạo `UPDATE` với nhiều cột mapped, kể cả khi chỉ `name` thay đổi. Tính năng riêng của Hibernate như `@DynamicUpdate` có thể tối ưu danh sách cột cập nhật trong một số tình huống, nhưng mang thêm phụ thuộc provider, tác động tới việc cache statement/batching và cần kiểm thử. Bài thực hành này không cần `@DynamicUpdate`.

## 6. Flush và commit là hai sự kiện khác nhau

| Khái niệm | Mục đích | Điều đảm bảo |
| --- | --- | --- |
| `persist()` | Đưa entity mới vào quản lý và lên lịch insert | Chưa đồng nghĩa dữ liệu đã commit |
| Đổi field của managed entity | Thay đổi object trong persistence context | Chưa bảo đảm SQL phát ra ngay |
| `flush()` | Đồng bộ pending changes xuống database qua SQL | Thay đổi có thể vẫn rollback |
| `commit()` | Kết thúc transaction thành công | Thay đổi được commit theo quy tắc DB |
| `rollback()` | Hủy transaction | Pending changes và SQL chưa commit không trở thành kết quả đã commit |
| `clear()` | Loại toàn bộ entity khỏi persistence context | Không tự hủy transaction hoặc rollback SQL đã flush |

Trong một transaction thành công, provider thường tự flush trước hoặc trong quá trình commit để đồng bộ những thay đổi còn pending. Vì vậy, nếu chỉ gọi setter rồi thoát khỏi một phương thức `@Transactional` bình thường, dữ liệu vẫn có thể được cập nhật khi transaction commit.

```java
@Service
public class ProductService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void renameProduct(long id, String newName) {
        CatalogProduct product = em.find(CatalogProduct.class, id);
        if (product == null) {
            throw new IllegalArgumentException("Product not found");
        }
        product.rename(newName);
        // Không cần em.merge(product) vì product đang managed.
        // SQL UPDATE thường sẽ phát sinh khi transaction flush/commit.
    }
}
```

Với Spring proxy-based transaction, `@Transactional` thường cần được gọi qua proxy từ bên ngoài bean; lời gọi nội bộ `this.renameProduct(...)` không tự động kích hoạt advice trong cấu hình proxy thông thường. Khi không có transaction đúng phạm vi, kết quả cập nhật có thể khác với kỳ vọng, đặc biệt khi entity đã detached.

### Flush không làm thay đổi tính cô lập giao dịch

Ví dụ:

```text
Transaction T1: UPDATE name='B' (qua flush), chưa commit
Transaction T2: SELECT cùng row
```

Dưới mức isolation phổ biến như READ COMMITTED, T2 thường chưa thấy `'B'` cho tới khi T1 commit; còn chính T1 có thể đọc lại giá trị đã sửa. Những chi tiết như MVCC, khóa và isolation phụ thuộc DBMS.

Nếu T1 rollback, giá trị được commit vẫn là trước đó. Không dùng `flush()` để ép bên ngoài “nhìn thấy sớm” dữ liệu của một transaction chưa commit.

## 7. AUTO flush: truy vấn có thể làm SQL xuất hiện sớm

Mặc định JPA thường dùng `FlushModeType.AUTO`. Provider phải bảo đảm các truy vấn trong phạm vi áp dụng nhìn thấy thay đổi liên quan theo hợp đồng JPA; provider có thể flush trước query để đạt mục tiêu đó. Hibernate thường quyết định flush dựa trên quan hệ giữa pending changes và các bảng mà query truy cập.

Ví dụ sau khi `rename()`:

```java
CatalogProduct product = em.find(CatalogProduct.class, id);
product.rename("Bàn phím cơ");

Long count = em.createQuery(
    "select count(p) from CatalogProduct p where p.name = :name",
    Long.class)
    .setParameter("name", "Bàn phím cơ")
    .getSingleResult();
```

Với Hibernate ở AUTO mode, JPQL truy vấn `CatalogProduct` thường khiến các update pending trên cùng bảng được flush trước `SELECT COUNT`. Log minh họa:

```text
UPDATE catalog_products ...     -- flush trước truy vấn
SELECT count(*) FROM catalog_products WHERE name=?
```

Điểm quan trọng: **không có quy tắc “mọi SELECT đều làm flush”**. Tùy provider và loại query, khi query không ảnh hưởng tới bảng đang có thay đổi pending, Hibernate có thể bỏ qua flush. Native SQL, `EntityManager` và API `Session` riêng của Hibernate cũng có khác biệt về cách xác định query spaces và đồng bộ. Nếu cần biết SQL đã được gửi đúng lúc nào, hãy **gọi flush tường minh** tại ranh giới cần thiết.

### FlushModeType.COMMIT

```java
em.setFlushMode(FlushModeType.COMMIT);
```

Ở COMMIT mode, provider thường trì hoãn flush cho đến commit, nhưng ảnh hưởng của thay đổi chưa flush lên kết quả query được đặc tả không chặt như AUTO. Không chọn COMMIT chỉ để giảm SQL nếu nghiệp vụ cần read-your-writes bằng query trước commit.

Nếu dùng COMMIT mode rồi chạy JPQL COUNT trước commit, kết quả có thể chưa phản ánh dữ liệu mới trong object managed. Khi cần kết quả chắc chắn từ database, gọi `em.flush()` trước query hoặc thiết kế giao dịch phù hợp.

### FlushMode Hibernate riêng

Hibernate còn có các mức như `ALWAYS`, `AUTO`, `COMMIT`, `MANUAL` qua API riêng. Đây không phải toàn bộ enum chuẩn `jakarta.persistence.FlushModeType`. Ví dụ với Spring `@Transactional(readOnly = true)`, các cấu hình Hibernate/Spring có thể tối ưu flush hoặc cách load entity read-only. Không dựa vào đó để thực hiện cập nhật dữ liệu trong transaction chỉ đọc.

## 8. Khi nào phải gọi flush tường minh?

Thông thường **không cần `flush()` sau mỗi setter**. Việc flush quá thường xuyên làm tăng số round-trip, giảm lợi ích batching và có thể giữ lock lâu hơn.

Một số trường hợp hợp lý:

1. **Cần lấy lỗi ràng buộc sớm:** muốn phát hiện unique/foreign key/check constraint ngay trong một điểm xử lý thay vì chờ commit; vẫn phải lưu ý một số constraint có thể deferrable và chỉ được kiểm tra ở commit.
2. **Cần SQL có hiệu lực trong transaction trước một thao tác tiếp theo:** ví dụ gọi stored procedure hoặc truy vấn native phụ thuộc trạng thái vừa cập nhật.
3. **Điều khiển batch lớn:** flush theo batch, sau đó clear để giới hạn số managed entity trong bộ nhớ.
4. **Thực hành/quan sát:** tạo mốc kiểm chứng chính xác khi log UPDATE phải xuất hiện.

Ví dụ batch cập nhật:

```java
for (int i = 0; i < products.size(); i++) {
    CatalogProduct product = products.get(i);
    product.changePrice(calculatePrice(product));

    if ((i + 1) % 100 == 0) {
        em.flush();
        em.clear();
    }
}
em.flush();
em.clear();
```

**Điều kiện quan trọng:** cách trên chỉ an toàn khi các entity cần cập nhật vẫn là managed ở thời điểm sửa. Sau `clear()`, các object còn trong `products` trở thành detached; nếu vòng lặp tiếp tục sửa những detached object đó, JPA không tự ghi chúng. Với batch thực tế, nên đọc dữ liệu theo từng trang/batch từ DB, xử lý, flush và clear, rồi tải batch tiếp theo. Hơn nữa, `flush()` và `clear()` không chia một transaction lớn thành nhiều transaction nhỏ; muốn commit theo batch cần điều phối transaction riêng.

## 9. So sánh managed, detached, new và removed

JPA entity có các trạng thái vòng đời quan trọng:

| Trạng thái | Hình thành | Hệ quả khi đổi field |
| --- | --- | --- |
| New/transient | `new CatalogProduct(...)` chưa persist | Không tự được ghi xuống DB |
| Managed | `find()`, query trả entity trong context hoặc `persist()` | Có thể được dirty checking và đồng bộ khi flush |
| Detached | `detach()`, `clear()`, đóng context | Không tự được theo dõi; cần gắn lại theo quy tắc JPA |
| Removed | `remove()` trên managed entity | Chờ `DELETE` khi flush, trừ các trường hợp xử lý đặc thù |

Thí nghiệm với detached:

```java
CatalogProduct product = em.find(CatalogProduct.class, id);
em.detach(product);

assert !em.contains(product);
product.rename("Tên từ detached object");
em.flush();
```

Đổi field của `product` sau `detach()` không tự sinh `UPDATE` cho instance đó. Muốn đưa trạng thái từ detached object trở lại persistence context, thường dùng `merge()`:

```java
CatalogProduct detached = em.find(CatalogProduct.class, id);
em.detach(detached);
detached.rename("Tên mới");

CatalogProduct managedCopy = em.merge(detached);
assert em.contains(managedCopy);
assert !em.contains(detached);

em.flush();
```

`merge()` **trả về một managed instance** có trạng thái được hợp nhất; object `detached` ban đầu **không** tự trở thành managed. Merge cũng có thể truy vấn DB trước khi flush. Vì thế, sau merge nên làm việc với `managedCopy` khi cần tiếp tục cập nhật.

Khi entity đã managed, gọi `merge()` hay `Spring Data repository.save(entity)` một cách máy móc thường không cần để dirty checking hoạt động. `save()` với entity đã tồn tại trong Spring Data JPA thường đi theo đường `merge()` tùy cơ chế xác định entity mới; điều đó **không đồng nghĩa UPDATE được thực thi ngay tại lời gọi save**.

## 10. Thí nghiệm thay đổi rồi không flush tường minh

Mục tiêu: nhận diện SQL có thể xuất hiện ở cuối transaction.

```java
@Service
public class ProductCommandService {

    private final EntityManager em;

    public ProductCommandService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public void changeName(Long id, String newName) {
        CatalogProduct product = em.find(CatalogProduct.class, id);
        if (product == null) {
            throw new IllegalArgumentException("Unknown id: " + id);
        }

        product.rename(newName);
        System.out.println("Đã gọi rename; chưa yêu cầu flush");
        // Không có explicit flush.
    }
}
```

Khi `changeName()` được gọi qua Spring transaction proxy, transaction được bắt đầu trước khi chạy body. Sau khi method trả về cho interceptor, cơ chế commit sẽ tiến hành, bao gồm flush pending changes nếu cần.

Đầu ra thường có thứ tự:

```text
SELECT ... WHERE id = ?
Đã gọi rename; chưa yêu cầu flush
UPDATE ... WHERE id = ? AND row_version = ?
COMMIT (không nhất thiết có log cùng logger Hibernate SQL)
```

Nếu `changeName()` được gọi bên trong một transaction ngoài đã có, hành vi commit phụ thuộc propagation: method trả về không có nghĩa transaction ngoài đã commit. Với `@Transactional(propagation = REQUIRED)`, method thường tham gia transaction hiện tại và SQL có thể tiếp tục chờ tới khi transaction ngoài flush/commit.

## 11. Phân biệt `flush()`, `clear()`, `refresh()`

Ba thao tác này thường bị nhầm trong lúc quan sát SQL:

```java
CatalogProduct p = em.find(CatalogProduct.class, id);
p.rename("Tên chưa flush");

em.flush();   // Đồng bộ UPDATE đang chờ.
em.clear();   // Loại tất cả managed entity khỏi persistence context.

CatalogProduct fromDatabase =
    em.find(CatalogProduct.class, id); // Thường SELECT lại.
```

Ngược lại:

```java
CatalogProduct p = em.find(CatalogProduct.class, id);
p.rename("Đổi tạm trong RAM");

em.refresh(p);
```

`refresh()` tải lại trạng thái persistent từ database vào entity managed. Nó có thể làm mất thay đổi chưa flush của object (hành vi và thời điểm query liên quan flush mode/provider); không dùng refresh như cách “lưu” object. Với mục tiêu minh họa, hãy thử `refresh()` trong một transaction có dữ liệu mẫu riêng và xem giá trị của `name` sau đó.

`clear()` không rollback những thay đổi đã flush. Tuy nhiên, nếu gọi `clear()` **trước khi flush**, pending changes chỉ ở memory có thể bị bỏ đi vì entity trở thành detached. Khi cần giữ chúng, hãy flush trước khi clear.

## 12. Bulk update và vấn đề persistence context bị cũ

JPQL bulk `UPDATE` và `DELETE` tác động trực tiếp đến database theo cơ chế riêng, **không cập nhật từng managed object** trong persistence context như setter:

```java
CatalogProduct p = em.find(CatalogProduct.class, id);

int updated = em.createQuery(
    """
    update CatalogProduct p
    set p.name = :name
    where p.id = :id
    """)
    .setParameter("name", "Tên từ JPQL bulk update")
    .setParameter("id", id)
    .executeUpdate();

// p có thể vẫn giữ tên cũ trong bộ nhớ.
```

Thao tác bulk bỏ qua dirty checking theo từng entity và thường không tự cập nhật `@Version` trừ khi bạn chủ động xử lý theo chiến lược phù hợp. Nó cũng có thể khiến persistence context bị stale:

```java
em.clear();
CatalogProduct latest = em.find(CatalogProduct.class, id);
```

Sau bulk, nếu trong persistence context vẫn có thay đổi pending khác, thứ tự flush/clear cần được lập kế hoạch để không làm mất cập nhật hoặc vô tình ghi đè dữ liệu. Với Spring Data JPA, `@Modifying(clearAutomatically = true, flushAutomatically = true)` hỗ trợ điều phối theo cấu hình, nhưng phải hiểu tác động lên các managed entity khác trong cùng transaction.

Bulk update phù hợp với cập nhật nhiều hàng theo điều kiện. Nó không thay thế setter trên managed entity khi nghiệp vụ cần callbacks, optimistic locking theo entity hoặc invariant ở tầng domain.

## 13. Trường hợp INSERT, IDENTITY và thứ tự SQL

Để tránh kết luận sai “mọi SQL chỉ xuất hiện lúc flush”, cần phân biệt các chiến lược sinh ID:

- Với `GenerationType.SEQUENCE`, provider có thể lấy giá trị sequence ngay khi `persist()` và hoãn `INSERT` đến flush.
- Với `GenerationType.IDENTITY`, provider thường cần thực hiện `INSERT` sớm để DB tạo ID, nên có thể thấy `INSERT` ngay khi `persist()` trong một số tình huống. Các chi tiết còn tùy transaction và provider.
- Với assigned ID, dữ liệu có ID trước khi persist nhưng điều đó không bảo đảm INSERT đã được gửi.
- Với JDBC batching, nhiều statement có thể được gom gửi theo batch lúc flush. Log SQL “đã chuẩn bị” không phải luôn là một statement được thực thi độc lập.

Bởi vậy, khi quan sát thời điểm SQL, hãy phân loại `SELECT`, thao tác sequence, `INSERT`, `UPDATE`, `DELETE` và kết thúc transaction riêng rẽ.

## 14. `@Version` giúp kiểm tra cạnh tranh ghi

Với entity có `@Version`, SQL `UPDATE` thông thường của Hibernate dùng version hiện tại trong điều kiện `WHERE` và tăng version khi ghi thành công:

```sql
UPDATE catalog_products
SET name = ?, price = ?, row_version = ?
WHERE id = ? AND row_version = ?;
```

Nếu một transaction khác đã cập nhật cùng entity và tăng version trước đó, transaction hiện tại có thể phát hiện xung đột bằng số hàng được cập nhật và ném `OptimisticLockException` hoặc ngoại lệ tương ứng của provider/Spring.

Thử nghiệm hai giao dịch:

```text
T1: SELECT id=1, row_version=0
T2: SELECT id=1, row_version=0
T1: đổi name, flush + commit -> row_version=1
T2: đổi price, flush hoặc commit với WHERE version=0
    -> không update được hàng tương ứng
    -> lỗi optimistic locking
```

Không nên mô phỏng hai transaction bằng cách gọi `em.find()` hai lần trong cùng context: cả hai lời gọi có thể trả cùng một managed object. Cần hai transaction độc lập với persistence context riêng. Hành vi chờ khóa và thời điểm lỗi còn phụ thuộc DBMS/isolation.

Nếu dùng JPQL bulk update/native SQL update trực tiếp, hãy tự xác định cách kiểm soát `row_version`, vì các lệnh này không mặc nhiên được xử lý như dirty checking của managed entity.

## 15. Đo số lượng SQL và quản lý log

### Log SQL là công cụ quan sát đầu tiên

Với Hibernate 6:

```yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
```

Thường không cần bật `spring.jpa.show-sql=true` cùng lúc, vì `show-sql` có thể in thêm ra stdout làm trùng thông tin với logging framework. Dùng logging có cấu hình theo môi trường dễ kiểm soát hơn.

### Hibernate Statistics

Để quan sát số lần flush và các chỉ số khác trong môi trường thử nghiệm:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
```

Hibernate có `Statistics` trong SessionFactory, nhưng đây là API riêng của provider. Các counter của Hibernate không luôn đồng nhất một-một với số câu SQL JDBC được thực thi khi có batching/cache/statement preparation. Muốn đo SQL thực tế và thời lượng câu lệnh, có thể dùng datasource proxy, JDBC tracing hoặc database monitoring đã được cấu hình phù hợp.

Không nên bật toàn bộ bind logging, statistics và SQL debug lâu dài trong môi trường có tải lớn vì ảnh hưởng hiệu năng và có nguy cơ ghi thông tin nhạy cảm ra log.

### Thêm mốc thời gian trong chương trình

Một cách dễ đối chiếu:

```java
log.info("STEP A: before find");
CatalogProduct product = em.find(CatalogProduct.class, id);

log.info("STEP B: before change");
product.rename("Tên mới");

log.info("STEP C: before flush");
em.flush();
log.info("STEP D: after flush");
```

Đọc log theo timeline:

```text
STEP A
SELECT ...
STEP B
STEP C
UPDATE ...
STEP D
```

Log từ nhiều request/thread có thể xen kẽ. Nếu môi trường chạy song song, gắn correlation ID hoặc transaction/request ID để không nhầm SQL của request khác vào thí nghiệm. Thao tác ghi log của chương trình cũng không bảo đảm đồng hồ giữa các hệ log phân tán đồng bộ tuyệt đối.

## 16. Thực hành mở rộng theo từng tình huống

Sau khi hoàn thành thí nghiệm cơ bản, có thể tự sửa **từng yếu tố một** và đối chiếu log.

| Tình huống | Thay đổi trong code | Dự đoán cần kiểm chứng |
| --- | --- | --- |
| A | Gọi `rename()`, không flush tường minh, transaction commit | UPDATE ở lúc provider flush trước/trong commit |
| B | Gọi `rename()`, sau đó `em.flush()` | UPDATE xuất hiện ngay tại flush |
| C | Gọi setter bằng đúng giá trị ban đầu | Có thể không có UPDATE vì không dirty |
| D | `clear()` trước flush, rồi commit | Thay đổi chưa flush của detached object không tự đồng bộ |
| E | `detach()`, sửa field, rồi flush | Không UPDATE instance detached chỉ vì setter |
| F | `merge(detached)`, flush | Có thể SELECT để merge; UPDATE khi flush nếu thay đổi |
| G | Gọi JPQL query lên cùng entity trước flush | AUTO mode có thể flush trước query |
| H | Dùng `FlushModeType.COMMIT` rồi query | Query có thể chưa phản ánh pending changes |
| I | JPQL bulk update rồi đọc managed object cũ | Object trong context có thể stale |
| J | Hai transaction sửa cùng entity có `@Version` | Một transaction có thể gặp optimistic lock conflict |

Khi thực hành, mỗi case nên có dữ liệu riêng và transaction riêng để log của case trước không làm sai quan sát của case sau.

### Câu hỏi suy luận trước khi xem log

**Trường hợp 1 — Có `UPDATE` nào trong hai lần setter không?**

```java
CatalogProduct p = em.find(CatalogProduct.class, id);
p.rename("Tên A");
p.rename("Tên B");
em.flush();
```

Trong mô hình Hibernate thường gặp, provider so sánh trạng thái cuối cùng của entity lúc flush, nên có thể chỉ phát **một UPDATE**. Điều này khác với gọi hai câu `UPDATE` JDBC trực tiếp.

**Trường hợp 2 — Vì sao đọc lại bằng `find()` thấy giá trị mới dù chưa flush?**

```java
CatalogProduct p = em.find(CatalogProduct.class, id);
p.rename("Tên C");
CatalogProduct same = em.find(CatalogProduct.class, id);
```

`same` thường là cùng managed instance với `p`; kết quả mới có thể chỉ đến từ RAM, không chứng minh database đã nhận UPDATE.

**Trường hợp 3 — Flush thành công nhưng test vẫn rollback?**

Trong `@Transactional` test, mặc định Spring TestContext rollback transaction cuối test. SQL đã chạy trong transaction nhưng dữ liệu không được commit vĩnh viễn; đây là cơ chế giúp test độc lập.

**Trường hợp 4 — Gọi `save()` có thay được `flush()` không?**

`save()` của Spring Data JPA thực hiện persist/merge theo trạng thái entity; nó không có hợp đồng bảo đảm đồng bộ ngay như `EntityManager.flush()` hoặc `JpaRepository.flush()`. `saveAndFlush()` chủ động yêu cầu flush, nhưng vẫn không đồng nghĩa commit.

**Trường hợp 5 — Đổi entity trong transaction `readOnly = true` có được lưu không?**

`readOnly` thường là hint để tối ưu và thể hiện ý định đọc; Hibernate/Spring có thể thay flush mode hoặc cách theo dõi entity. Không dùng transaction read-only để thực hiện ghi. Khả năng DB thực sự cấm ghi còn phụ thuộc transaction manager, driver và DBMS.

## 17. Lỗi thường gặp khi quan sát SQL

### Không thấy UPDATE sau setter

Đầu tiên xác định entity có managed hay không bằng `em.contains(entity)`; nếu đã detached hoặc transaction kết thúc trước setter, dirty checking không tự đồng bộ. Tiếp theo kiểm tra:

- Có transaction ghi thực sự đang hoạt động không?
- Có gọi flush/commit không, hay test đã rollback trước điểm quan sát?
- Giá trị mới có thực sự khác trạng thái ban đầu không?
- Transaction bị đánh dấu read-only, provider đang ở MANUAL/COMMIT flush mode hay không?
- Logger SQL và bind parameter đã bật đúng phiên bản Hibernate chưa?
- Lời gọi `@Transactional` có đi qua Spring proxy hay đang tự gọi trong cùng bean?

### Thấy UPDATE trước dòng `flush()`

Có thể đã có một query gây AUTO flush, một thao tác `saveAndFlush()` ở tầng khác, gọi repository method có lệnh bulk update hoặc provider cần phát SQL sớm vì một ràng buộc/chiến lược sinh ID. Kiểm tra các lời gọi DB nằm giữa setter và flush tường minh; đừng kết luận rằng setter tự thực hiện SQL.

### Thấy nhiều SELECT hoặc UPDATE ngoài dự kiến

Nguyên nhân có thể là lazy loading, truy vấn count, auto flush, cascade, entity listener, kiểm tra version, `merge()`, các entity khác cùng persistence context, hoặc hoạt động nền. Cần dùng log theo transaction và so sánh với SQL thật. Đừng mặc định một lời gọi repository bằng đúng một statement.

### Thấy giá trị mới sau flush nhưng ứng dụng khác chưa thấy

Đó là dấu hiệu bình thường khi transaction của bạn chưa commit hoặc read replica chưa bắt kịp. Kiểm tra transaction boundary và isolation trước khi nghi ngờ dirty checking.

### Thấy cập nhật bị mất sau `clear()`

Nếu thay đổi chưa flush mà gọi `clear()`, entity bị detached, pending changes trong context không còn được theo dõi. Cách dùng phổ biến để xác minh là `flush()` trước `clear()`, rồi `find()` lại. Tuy nhiên, flush vẫn nằm trong transaction và có thể rollback.

### Thấy lỗi OptimisticLockException

Entity có `@Version` có thể đã bị transaction khác cập nhật, hoặc code bulk/native SQL và entity managed không phối hợp cùng chiến lược version. Không tự bỏ `@Version` để “sửa” lỗi. Cần xác định tác vụ có thể retry, cách nạp lại dữ liệu và chính sách xử lý conflict nghiệp vụ.

## 18. Quy trình thực hành hoàn chỉnh

Một lần thực hành có thể đi qua các điểm sau:

1. Tạo bảng/entity và bật Hibernate SQL logging trong profile local.
2. Tạo một `CatalogProduct`; gọi `persist()`, `flush()`, `clear()` để có dữ liệu đầu vào ổn định.
3. Dùng `find()` nạp product, xác nhận `em.contains(product) == true`.
4. Gọi `rename()` rồi in mốc log; quan sát chưa có UPDATE do riêng setter.
5. Gọi `flush()`; nhìn UPDATE và bind parameter xuất hiện.
6. Gọi `clear()`, `find()` lại để đọc trạng thái database trong cùng transaction.
7. Chạy lại thí nghiệm mà bỏ `flush()` tường minh, quan sát UPDATE ở transaction completion.
8. Chạy thử tình huống `detach()`, `merge()`, JPQL AUTO flush và `clear()` trước flush.
9. Tách hai transaction để thử optimistic locking; đối chiếu với bản ghi và version thực tế.
10. Ghi nhận phần nào là hành vi do JPA đảm bảo, phần nào là lựa chọn của Hibernate/dialect và phần nào thuộc transaction của DBMS.

**Kết quả cần nắm được:** thao tác gọi setter trên một *managed entity* chỉ đổi trạng thái object và làm provider có cơ sở nhận diện dữ liệu bị thay đổi. **Flush là điểm đồng bộ các thao tác đang chờ thành SQL**, có thể do chương trình gọi hoặc provider thực hiện trước query/commit. **Commit mới hoàn tất transaction**. Vì vậy, để giải thích tại sao SQL phát sinh ở một thời điểm cụ thể, phải nhìn đồng thời vào trạng thái entity, persistence context, flush mode, các query xen giữa và ranh giới transaction.
