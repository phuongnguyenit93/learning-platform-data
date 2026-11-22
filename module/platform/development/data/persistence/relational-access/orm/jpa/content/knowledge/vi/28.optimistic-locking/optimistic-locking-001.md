# Vấn đề ghi đè thay đổi khi nhiều giao dịch cùng cập nhật trong JPA

Trong một ứng dụng có nhiều người dùng, hai giao dịch có thể **đọc cùng một bản ghi trước khi một trong hai ghi kết quả**. Nếu mỗi giao dịch sửa dữ liệu dựa trên giá trị đã đọc và ghi mà không kiểm tra bản ghi có bị thay đổi trong lúc đó hay không, thao tác ghi sau có thể **ghi đè kết quả của thao tác ghi trước**. Đây là một dạng *lost update* — lỗi mất cập nhật.

Ví dụ cửa hàng có một sản phẩm:

~~~text
Product#100:
  price = 100_000
  stock = 10
~~~

Hai nhân viên cùng mở trang chỉnh sửa giá. A nhập 110.000, B nhập 120.000. Cả hai form được tạo từ giá ban đầu 100.000.

~~~text
Thời gian     Giao dịch A                 Giao dịch B
-----------------------------------------------------------------
T1            Đọc price = 100_000
T2                                        Đọc price = 100_000
T3            Đổi price = 110_000
T4            COMMIT
T5                                        Đổi price = 120_000
T6                                        COMMIT
-----------------------------------------------------------------
Kết quả cuối: price = 120_000; cập nhật 110_000 của A không còn.
~~~

Đôi khi thay đổi sau **được phép** ghi đè thay đổi trước, chẳng hạn chính sách nghiệp vụ “last write wins”. Tuy nhiên, khi đây là hai thao tác đồng thời độc lập, việc im lặng ghi đè thường gây mất dữ liệu mà không bên nào biết.

JPA hỗ trợ **khóa lạc quan (optimistic locking)**, thường thông qua `@Version`, để phát hiện tình huống dữ liệu đã bị thay đổi từ lúc đọc đến lúc cập nhật. Thay vì khóa bản ghi ngay từ khi đọc, ứng dụng ghi nhận phiên bản và kiểm tra **phiên bản lúc ghi phải vẫn như phiên bản đã đọc**. Nếu không khớp, giao dịch được báo xung đột và phải quyết định tải lại, hợp nhất dữ liệu hoặc thử lại một cách có kiểm soát.

Bài này trình bày:

- Lost update xảy ra ở đâu trong JPA, từ database đến persistence context và giao diện người dùng.
- Vì sao `@Transactional` hoặc một lệnh UPDATE có row lock **chưa nhất thiết** ngăn lost update ở mọi thiết kế.
- Cơ chế `@Version` và cập nhật có điều kiện theo version; phát hiện xung đột tại flush/commit.
- Sự khác nhau giữa cập nhật cùng field và cập nhật khác field; dirty checking, merge và stale state.
- Hạn chế của native SQL, JPQL bulk updates, cache, retry tự động và cập nhật xuyên nhiều bảng.
- Cách phối hợp repository/service/API, xử lý HTTP conflict, idempotency và kiểm thử hai giao dịch thực.

## 1. Lost update là gì?

*Lost update* là hiện tượng một thay đổi hợp lệ đã được ghi, nhưng sau đó bị **một thao tác khác dùng dữ liệu cũ ghi đè**, khiến tác động của thay đổi thứ nhất không còn trong trạng thái cuối.

Ví dụ số dư điểm thưởng:

~~~text
Ban đầu: points = 100

A đọc 100, cộng 20 -> muốn ghi 120
B đọc 100, trừ 30 -> muốn ghi 70

A ghi 120 và commit.
B ghi 70 và commit.

Đúng theo hai nghiệp vụ tuần tự phải là 90,
nhưng kết quả cuối là 70.
=> Cộng 20 của A bị mất.
~~~

Sai lầm nằm ở kiểu thao tác **read → tính toán trong Java → write lại một giá trị tuyệt đối**, khi giá trị ban đầu có thể đã thay đổi.

### Một dạng khác: form chỉnh sửa

Hai người cùng đọc địa chỉ giao hàng:

~~~text
T0:
  recipientName = "An"
  phone = "090..."
  address = "Địa chỉ cũ"

A sửa phone.
B sửa address trên form cũ.
~~~

Nếu B gửi **toàn bộ object cũ** và server áp dụng tất cả field, B có thể vô tình khôi phục phone cũ, xóa cập nhật của A. Trường hợp này không chỉ liên quan một phép tính số học mà còn liên quan cách API **hợp nhất dữ liệu từ form/DTO**.

### Lost update khác “không đọc được thay đổi chưa commit”

Một giao dịch đọc dữ liệu cũ không nhất thiết là lỗi. Lỗi xảy ra khi nó **dùng dữ liệu cũ đó để ghi một kết quả không còn hợp lệ**, thường mà không phát hiện đã có thay đổi khác.

Không phải mọi trường hợp hai UPDATE đều là lost update. Nếu A và B có chủ đích thiết lập một trạng thái lần lượt và chính sách yêu cầu lệnh đến sau thắng, đó có thể là semantics hợp lệ. Cần xác định **mong muốn nghiệp vụ** trước khi chọn cơ chế concurrency.

## 2. Trình tự mất cập nhật khi không dùng @Version

Giả sử bảng:

~~~sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(18, 2) NOT NULL
);

INSERT INTO accounts(id, balance)
VALUES (1, 100.00);
~~~

Ứng dụng thực hiện:

~~~java
Account account = em.find(Account.class, 1L);
BigDecimal newBalance =
    account.getBalance().add(new BigDecimal("20.00"));
account.setBalance(newBalance);
~~~

Với hai transaction cùng đọc `100.00`, SQL cập nhật kiểu đặt giá trị tuyệt đối có thể gần như:

~~~sql
UPDATE accounts
SET balance = 120.00
WHERE id = 1;
~~~

và:

~~~sql
UPDATE accounts
SET balance = 70.00
WHERE id = 1;
~~~

Khi cả hai được phép commit theo isolation/DBMS, câu UPDATE ghi sau quyết định giá trị cuối. Điều kiện chỉ có `WHERE id=1` không biểu diễn **“tôi đang sửa trên phiên bản đã đọc”**.

### Timeline

~~~text
DB: balance = 100

Transaction A                    Transaction B
------------------------------   --------------------------------
BEGIN                            BEGIN
SELECT balance -> 100             SELECT balance -> 100
Tính 100 + 20 = 120               Tính 100 - 30 = 70
UPDATE balance = 120
COMMIT
                                 UPDATE balance = 70
                                 COMMIT

DB: balance = 70
~~~

Đây là một kịch bản có thể xảy ra ở hệ quản trị/cấu hình cho phép cập nhật cuối ghi đè giá trị tính từ snapshot cũ. Một số mức isolation hoặc DBMS có thể phát hiện write conflict và buộc rollback giao dịch thứ hai. **Không được kết luận mọi database ở mọi isolation luôn cho phép timeline này commit cả hai**.

## 3. Vì sao cần phân biệt concurrency với transaction?

Một transaction bảo đảm một nhóm thao tác có semantics commit/rollback của database. Nó **không tự quyết định chính sách xử lý trường hợp hai transaction cùng đọc và sửa dữ liệu cũ**.

| Khái niệm | Vấn đề nó xử lý |
| --- | --- |
| Atomicity | Một unit of work commit hoặc rollback theo transaction semantics |
| Isolation | Các transaction nhìn thấy và ảnh hưởng nhau như thế nào |
| Optimistic locking | Phát hiện thay đổi cạnh tranh bằng version/điều kiện |
| Pessimistic locking | Yêu cầu lock database để điều phối truy cập cạnh tranh |
| Validation | Giá trị đầu vào có hợp lệ theo nghiệp vụ không |
| Idempotency | Một yêu cầu gửi lại có bị thực hiện hai lần không |

Ví dụ:

~~~java
@Transactional
public void changeBalance(...) {
    Account a = repository.findById(...).orElseThrow();
    a.setBalance(...);
}
~~~

Đây là **một transaction** nhưng chưa thể suy ra đã bảo vệ lost update nếu entity không được versioned và isolation không ngăn kiểu xung đột tương ứng.

### Transaction rollback khi lỗi không đồng nghĩa sẽ có lỗi

Nếu DB/provider không phát hiện lost update, cả hai transaction có thể return thành công và không có exception để Spring/JTA rollback. Phải thiết kế **điều kiện phát hiện cạnh tranh** chứ không chỉ đặt try/catch quanh commit.

## 4. Mô hình ví dụ: quản lý tồn kho sản phẩm

Xét entity Product:

~~~text
products
-------------------------------------------------------
id | tenant_id | sku | name | price | stock | version
~~~

DDL PostgreSQL minh họa:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    stock INTEGER NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_product_tenant_sku
        UNIQUE (tenant_id, sku),
    CONSTRAINT ck_product_price
        CHECK (price >= 0),
    CONSTRAINT ck_product_stock
        CHECK (stock >= 0)
);
~~~

`version` là một thuộc tính persistent được quản lý theo chiến lược optimistic locking; không phải số đơn hàng, không phải timestamp chỉnh sửa từ client.

### Entity có @Version

~~~java
package com.example.shop;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private int stock;

    @Version
    @Column(nullable = false)
    private Long version;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public int getStock() {
        return stock;
    }

    public Long getVersion() {
        return version;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Giá phải không âm");
        }
        this.price = newPrice;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                "Tên không được rỗng");
        }
        this.name = newName.strip();
    }

    public void decreaseStock(int quantity) {
        if (quantity <= 0 || stock < quantity) {
            throw new IllegalArgumentException(
                "Số lượng không hợp lệ");
        }
        this.stock -= quantity;
    }
}
~~~

Ví dụ Java 17+ với namespace `jakarta.persistence`. Giá dùng `BigDecimal` thay vì `double`. Trường `version` được provider quản lý; **không cung cấp một public setter để client tự tăng hoặc đặt version**.

### Vì sao vừa có CHECK(stock >= 0) vừa có @Version?

Hai lớp bảo vệ khác nhau:

- `CHECK(stock >= 0)` ngăn giá trị âm tại database.
- `@Version` phát hiện phiên bản đã thay đổi khi transaction đang cố ghi từ state cũ.

Constraint không thay thế optimistic locking, còn optimistic locking không thay mọi ràng buộc dữ liệu của DB.

## 5. @Version thay đổi SQL UPDATE như thế nào?

Khi Product#10 có:

~~~text
price = 100000
version = 7
~~~

và một transaction sửa giá:

~~~java
Product p = em.find(Product.class, 10L);
p.changePrice(new BigDecimal("120000.00"));
~~~

JPA provider khi flush có thể sinh SQL về bản chất:

~~~sql
UPDATE products
SET price = 120000.00,
    version = 8
WHERE id = 10
  AND version = 7;
~~~

Thực tế SQL có thể cập nhật thêm persistent columns khác, dùng bind parameters và cú pháp riêng của dialect:

~~~sql
UPDATE products
SET price = ?,
    version = ?
WHERE id = ?
  AND version = ?;
~~~

**Điểm then chốt là điều kiện kiểm tra phiên bản cũ.**

### Cách phát hiện xung đột

Nếu DB vẫn có version=7:

~~~text
UPDATE ảnh hưởng 1 row
provider chấp nhận ghi,
version mới = 8
~~~

Nếu một transaction khác đã nâng version thành 8:

~~~text
WHERE version = 7 không còn khớp
UPDATE ảnh hưởng 0 row
provider phát hiện stale version
=> optimistic locking conflict
~~~

Tùy provider/transaction boundary, application có thể nhận `OptimisticLockException` hoặc exception được framework bao bọc/chuyển đổi khi flush hoặc commit.

### Version đóng vai trò gì?

`@Version` là **tín hiệu thay đổi đã có người khác ghi**, không phải cơ chế ngăn người khác đọc. Các transaction vẫn có thể đọc cùng một row; khi cập nhật, ít nhất một bên phải xử lý xung đột nếu cả hai dựa trên cùng phiên bản ban đầu.

## 6. Hai giao dịch cùng đọc version=7

~~~text
Ban đầu:
  Product#10.price = 100000
  Product#10.version = 7

Transaction A                          Transaction B
------------------------------------   ---------------------------------
BEGIN                                  BEGIN
SELECT Product -> price=100k, v=7      SELECT Product -> price=100k, v=7
changePrice(110k)                      changePrice(120k)
FLUSH:
  UPDATE ... WHERE version=7
  1 row, DB version -> 8
COMMIT
                                       FLUSH:
                                         UPDATE ... WHERE version=7
                                         0 row vì DB version=8
                                       CONFLICT
                                       ROLLBACK

Kết quả committed:
  price = 110000
  version = 8
  B được báo cập nhật xung đột.
~~~

Thứ tự thực tế có thể khác: B có thể flush trước A; transaction có thể phải chờ row lock; provider/DBMS có thể báo xung đột tại commit thay vì ngay tại update. **Bản chất là hai bản ghi cũ cùng version không được âm thầm ghi đè nhau qua đường ghi version-aware.**

### Ai được ưu tiên?

Optimistic locking **không chọn nhân viên A hay B theo vai trò, tuổi giao dịch hoặc thời điểm mở form**. Nó chỉ xác định thao tác nào đã cập nhật phiên bản thành công và thao tác nào trở nên stale. Nếu business yêu cầu ưu tiên một nguồn dữ liệu, đó là quy tắc riêng phải được thiết kế ở service/API.

### Có cần SELECT ... FOR UPDATE khi dùng @Version?

Không bắt buộc. Khóa lạc quan thường phát huy khi **ít xung đột** vì không cần giữ một database lock dài từ lúc người dùng đọc cho đến lúc cập nhật. Đổi lại, ứng dụng cần xử lý khi có conflict.

## 7. “Lạc quan” có nghĩa gì?

*Optimistic concurrency control* đặt giả định: **phần lớn giao dịch sẽ không sửa cùng một dữ liệu vào cùng thời điểm**.

Quy trình:

~~~text
1. Đọc Product + version hiện tại.
2. Cho phép ứng dụng xử lý mà không khóa độc quyền dài hạn.
3. Khi ghi, kiểm tra version đã đọc còn hợp lệ.
4. Nếu hợp lệ: ghi và tăng version.
5. Nếu không: báo conflict, rollback/retry/merge theo nghiệp vụ.
~~~

Lợi ích:

- Không cần giữ row lock suốt thời gian người dùng mở form.
- Phù hợp CRUD và nghiệp vụ ít tranh chấp.
- Phát hiện thay đổi concurrent một cách rõ ràng.
- Tương đối dễ đưa phiên bản vào HTTP API để tránh stale form overwrite.

Đánh đổi:

- Khi contention cao, một phần transaction phải rollback.
- Người dùng có thể cần giải quyết conflict.
- Retry tự động không phải lúc nào cũng an toàn.
- Những đường ghi native/bulk ngoài JPA phải tuân thủ giao thức version.

## 8. Entity được quản lý và dirty checking

Với một `EntityManager` trong transaction:

~~~java
em.getTransaction().begin();

Product p = em.find(Product.class, 10L);
p.changePrice(new BigDecimal("130000.00"));

em.getTransaction().commit();
~~~

Trong `RESOURCE_LOCAL`, provider có thể nhận ra Product managed đã thay đổi rồi flush một UPDATE version-aware trước khi commit. Không nhất thiết phải gọi `em.merge(p)` khi `p` đang managed.

### Phân biệt bốn thời điểm

| Thời điểm | Điều xảy ra |
| --- | --- |
| `find()` | Entity trở thành managed, mang state/version đã đọc |
| Setter/domain method | Thay đổi Java object trong persistence context |
| `flush()` | Đồng bộ SQL UPDATE và kiểm tra version khi provider thực thi ghi |
| `commit()` | Kết thúc transaction, có thể kích hoạt flush và lỗi concurrency/constraint |

### Không suy ra “setter thành công = cập nhật DB thành công”

~~~java
p.changePrice(newPrice);
return "OK";
~~~

Nếu transaction chưa commit, lời gọi setter không bảo đảm kết quả đã bền vững. Xung đột optimistic có thể chỉ được phát hiện khi flush/commit bên ngoài method, đặc biệt khi dùng Spring/JTA.

## 9. Xung đột có thể xuất hiện ở flush hoặc commit

Ví dụ resource-local:

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = em.find(Product.class, productId);
    product.changePrice(newPrice);

    em.flush();    // Có thể phát hiện optimistic conflict ở đây.
    tx.commit();   // Hoặc lỗi có thể xuất hiện khi commit.

} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

`flush()` có thể giúp phát hiện xung đột sớm hơn trước khi service làm bước tiếp, nhưng **không phải commit**. Một commit vẫn có thể thất bại sau flush vì ràng buộc khác, transaction rollback-only, resource failure hoặc điều kiện concurrency xuất hiện sau đó.

### Vì sao không bắt lỗi rồi tiếp tục giao dịch cũ?

Sau một optimistic conflict, transaction thường cần rollback. `OptimisticLockException` thường đánh dấu transaction rollback-only theo quy tắc JPA. Persistence context có thể đang chứa state không đồng bộ với database.

Không nên:

~~~java
try {
    em.flush();
} catch (OptimisticLockException ex) {
    // Chỉ ghi log rồi tiếp tục em.persist(...) và commit.
}
~~~

**Hướng xử lý:** rollback transaction thất bại, đóng/clear context theo lifecycle quản lý, rồi quyết định người dùng có cần tải lại hay application có được retry trong **transaction mới** hay không.

## 10. @Version dùng loại dữ liệu gì?

JPA hỗ trợ các kiểu version được đặc tả, phổ biến là số nguyên và một số kiểu thời gian:

~~~java
@Version
private Long version;
~~~

hoặc:

~~~java
@Version
private Integer version;
~~~

Một số mô hình dùng `java.sql.Timestamp` như version. Các phiên bản đặc tả/provider có thể có quy tắc kiểu tương thích khác nhau; khi cần portability, **Long** thường là lựa chọn dễ hiểu.

### Số version so với timestamp version

| Loại | Ưu điểm | Giới hạn |
| --- | --- | --- |
| Long/Integer | Tăng tuần tự, so sánh chính xác | Cần provider/DB quản lý nhất quán |
| Timestamp | Có thể giúp xem thời điểm thay đổi | Phụ thuộc độ chính xác clock, DB/provider và mapping |

Không nên sử dụng đồng hồ client hoặc `updatedAt` bình thường làm “version an toàn” khi không có giao thức compare-and-swap được enforce tại database.

### Ai được sửa version?

**Provider hoặc một giao thức DB thống nhất** phải quản lý version. Application không nên:

~~~java
product.setVersion(product.getVersion() + 1);
~~~

để “giải quyết optimistic locking”. Nếu tự ý đổi version trong managed entity, có thể phá cơ chế kiểm tra hoặc gây lỗi ở provider.

## 11. @Version có cần nằm trong primary key?

Không. Ví dụ:

~~~text
id       = 10
version  = 7
~~~

- `id` xác định entity identity.
- `version` xác định thế hệ/state snapshot mà thao tác ghi dựa trên.

SQL UPDATE thường dùng **cả id và version** trong điều kiện:

~~~sql
WHERE id = ? AND version = ?
~~~

Khi version tăng, identity Product vẫn là Product#10. Không đưa version vào `equals/hashCode` định danh entity một cách tùy tiện, vì version thay đổi trong vòng đời managed entity.

## 12. Cập nhật hai thuộc tính khác nhau có vẫn xung đột?

Ví dụ:

~~~text
Product#10, version=7
  name  = "Java Handbook"
  price = 100000

A sửa name thành "Java Persistence Handbook".
B sửa price thành 120000.
~~~

Với optimistic locking theo **entity-level version**, cả hai đều sửa cùng Product#10.

~~~text
A UPDATE -> version 8.
B đang giữ version 7 -> conflict.
~~~

### Tại sao lại chặn dù field khác nhau?

`@Version` thường bảo vệ **trạng thái persistent của entity như một đơn vị**, không chỉ một cột được sửa. Có những invariant phụ thuộc nhiều field, nên hai cập nhật “khác cột” cũng có thể cần được phối hợp.

### Có cần cho phép tự động merge?

Tùy nghiệp vụ. Nếu name và price thực sự độc lập, API có thể:

1. Tải phiên bản mới.
2. Xác định A đã sửa những field nào.
3. Kiểm tra field B muốn sửa có bị ai khác thay đổi không.
4. Áp dụng lại thay đổi an toàn lên state mới.
5. Commit một transaction mới.

Không thể mặc định mọi thay đổi khác field đều an toàn để merge. Ví dụ `discount` và `price` khác field nhưng cùng quyết định số tiền khách phải trả.

## 13. @DynamicUpdate có giải quyết lost update không?

Hibernate có extension `@DynamicUpdate`, có thể khiến SQL UPDATE chỉ đưa các cột được nhận diện là dirty vào SET:

~~~java
@org.hibernate.annotations.DynamicUpdate
@Entity
public class Product {
    // ...
}
~~~

Đây là **tính năng Hibernate-specific**, không thuộc JPA portable.

Nó có thể giảm số cột trong UPDATE và hạn chế một số overwrite ngoài ý định nếu không versioned. Nhưng:

- Hai transaction sửa **cùng một cột** vẫn có thể lost update.
- Những thay đổi khác cột có thể vi phạm invariant chung.
- Vẫn cần chiến lược phát hiện xung đột rõ nếu không muốn silent overwrite.
- Kết quả phụ thuộc provider dirty tracking, SQL được sinh và mapping.

**Không coi @DynamicUpdate là thay thế cho @Version.**

## 14. Transaction isolation và lost update

JPA không định nghĩa một isolation level cố định cho mọi persistence unit. Database/transaction manager quyết định READ COMMITTED, REPEATABLE READ, SERIALIZABLE hoặc cơ chế khác.

### READ COMMITTED

Trong nhiều DBMS, READ COMMITTED cho phép một transaction đọc giá trị đã commit rồi tính kết quả trong Java; khi đến lượt UPDATE, nếu query chỉ dùng PK và không kiểm tra version, nó có thể ghi đè giá trị được tính từ state cũ.

Nhưng hành vi cụ thể còn phụ thuộc row locking, thời điểm UPDATE và DBMS.

### REPEATABLE READ / Snapshot isolation

Những chế độ này có thể giúp giảm một số anomaly, và một số DBMS từ chối concurrent writes cùng row thay vì cho phép silent lost update. Tuy nhiên, tên isolation level không tự mô tả toàn bộ semantics ở mọi engine.

### SERIALIZABLE

Serializable yêu cầu kết quả của những transaction được commit tương đương một thứ tự tuần tự phù hợp; DBMS có thể buộc một transaction rollback với serialization failure. Nhưng điều này đi kèm chi phí contention và ứng dụng cần retry đúng cách.

### Bảng định hướng

| Cơ chế | Lost update cùng row | Lưu ý |
| --- | --- | --- |
| READ COMMITTED không version | Có thể xảy ra | Phụ thuộc cách đọc/ghi và DBMS |
| REPEATABLE READ | DBMS-dependent | Có thể phát hiện write conflict hoặc có semantics khác |
| SERIALIZABLE | Không nên commit lịch sử không serializable | Có thể rollback và cần retry |
| `@Version` | Phát hiện stale entity update qua đường ghi tuân thủ version | Không tự bảo vệ bulk/native writes |
| `PESSIMISTIC_WRITE` | Điều phối truy cập với DB lock | Có thể chờ, timeout hoặc deadlock |
| Atomic conditional SQL | Ngăn loại race cụ thể | Phải thiết kế đủ điều kiện nghiệp vụ |

**Không đặt toàn bộ ứng dụng sang SERIALIZABLE chỉ vì chưa muốn thiết kế conflict handling.** Cân nhắc chiến lược phù hợp từng thao tác và workload.

## 15. Row lock của UPDATE không tự thay thế version

Các DBMS transactional thường sử dụng lock hoặc conflict detection cho câu UPDATE. Nhưng nếu logic:

~~~text
READ balance = 100
TÍNH 100 + 20 = 120 trong Java
...
UPDATE balance = 120
~~~

thì việc UPDATE phải chờ lock được giải phóng không có nghĩa **giá trị 120 đã được tính lại** từ database sau khi lock được cấp.

Một SQL:

~~~sql
UPDATE accounts
SET balance = balance + 20
WHERE id = 1;
~~~

khác bản chất với:

~~~sql
UPDATE accounts
SET balance = 120
WHERE id = 1;
~~~

Câu thứ nhất yêu cầu database cập nhật **dựa trên giá trị hiện có tại thời điểm thực thi theo semantics/locking DBMS**; câu thứ hai đặt một giá trị tuyệt đối đã tính từ snapshot Java có thể cũ.

### Khi nào atomic SQL phù hợp?

Với counter, số lượng tồn kho hoặc phép cộng dồn thuần túy, conditional UPDATE có thể là giải pháp đơn giản và hiệu quả hơn nạp entity rồi cộng trong Java.

Nhưng nếu nghiệp vụ cần kiểm tra nhiều field, ghi audit, phát domain event, giữ optimistic version và dùng entity managed sau đó, phải thiết kế đầy đủ các tác động ấy.

## 16. Atomic decrement: ví dụ giữ tồn kho an toàn hơn

Thay vì:

~~~java
Product p = em.find(Product.class, id);
if (p.getStock() >= quantity) {
    p.decreaseStock(quantity);
}
~~~

rồi giả định không có transaction cạnh tranh, có thể dùng một lệnh SQL có điều kiện:

~~~sql
UPDATE products
SET stock = stock - :quantity,
    version = version + 1
WHERE id = :productId
  AND tenant_id = :tenantId
  AND stock >= :quantity;
~~~

Trong một DBMS thích hợp, thao tác có điều kiện này tránh kiểu check-then-act đơn giản trên stock khi các UPDATE cùng cạnh tranh một row.

Kết quả:

~~~text
affectedRows = 1 -> đã trừ stock.
affectedRows = 0 -> không có row hợp lệ hoặc stock không đủ.
~~~

### Cần phân biệt các nguyên nhân 0 row

Không nên trả “hết hàng” khi row ID không tồn tại hoặc thuộc tenant khác. Một API có thể trả thông báo chung để tránh rò rỉ tài nguyên, hoặc kiểm tra riêng theo chính sách authorization. Điều quan trọng là **không bỏ qua tenant predicate**.

### Vì sao tăng version trong SQL?

Native SQL không tự kích hoạt cơ chế `@Version` của managed JPA entity. Tăng version giúp những đường cập nhật JPA khác đang giữ phiên bản cũ nhận diện row đã đổi, nếu cùng dùng giao thức version.

### Cẩn trọng với persistence context

Nếu Product#10 đã được nạp bằng `em.find()`, sau native UPDATE, object managed có thể còn stock/version cũ. Cần `refresh()`, `clear()` hoặc thiết kế tránh dùng state cũ trong cùng transaction.

## 17. Check-and-set version thủ công ở SQL

Nếu API muốn chỉ cập nhật khi client có expectedVersion:

~~~sql
UPDATE products
SET price = :newPrice,
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND version = :expectedVersion;
~~~

Đây là **compare-and-swap** theo version:

- Row khớp ID, tenant và expectedVersion: cập nhật được.
- Version đã thay đổi: UPDATE ảnh hưởng 0 row.
- Row không tồn tại/không thuộc tenant: cũng ảnh hưởng 0 row.

Service phải xác định cách phân biệt 404/403/409 theo chính sách bảo mật và nghiệp vụ.

### Tại sao kiểm tra version ở SQL thay vì chỉ ở Java?

Sai:

~~~java
if (product.getVersion().equals(expectedVersion)) {
    // Sau check, transaction khác có thể commit.
    updateDatabaseWithoutVersionCondition();
}
~~~

Giữa câu kiểm tra và câu UPDATE có thể có **time-of-check-to-time-of-use race**. Điều kiện version cần được enforce **trong chính thao tác ghi** hoặc thông qua cơ chế versioned entity update của JPA.

### Dùng @Version hay tự viết CAS?

Khi làm việc với managed entity và dirty checking, `@Version` thường là lựa chọn JPA rõ ràng. Khi nghiệp vụ dùng atomic bulk SQL, hãy áp điều kiện version thủ công và đồng bộ persistence context. Không trộn hai cơ chế mà không định nghĩa owner của state.

## 18. Spring @Transactional và @Version

Ví dụ một service Spring:

~~~java
package com.example.shop;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;
import java.util.Objects;

@Service
public class ProductAdminService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void changePrice(
            long tenantId,
            long productId,
            BigDecimal newPrice) {

        Product product = em.find(
            Product.class, productId);

        if (product == null
                || !Objects.equals(
                    product.getTenantId(), tenantId)) {
            throw new IllegalArgumentException(
                "Không tìm thấy sản phẩm trong tenant");
        }

        product.changePrice(newPrice);

        // Không cần merge nếu product vẫn managed.
        // Provider sẽ flush/version check trước commit.
    }
}
~~~

Trong ví dụ, `@Transactional` của Spring tạo/tham gia transaction khi method được gọi qua cơ chế quản lý transaction đúng (thường qua proxy).

**Có transaction nhưng không có expectedVersion của lần người dùng mở form** vẫn có thể chưa đủ để bảo vệ **stale form cập nhật cách nhau nhiều phút**. Lý do: mỗi request HTTP thường mở transaction mới, tải Product mới và cập nhật version mới nhất; server không biết client đã nhìn dữ liệu cũ trước đó.

Vấn đề này được trình bày riêng ở phần API concurrency.

## 19. Hai dạng stale state cần phân biệt

### A. Hai transaction đang mở đồng thời

~~~text
Transaction A: find Product(version=7)
Transaction B: find Product(version=7)
A commit version=8
B commit -> optimistic conflict
~~~

`@Version` trên managed entity giúp phát hiện xung đột qua đường cập nhật version-aware.

### B. Hai lần chỉnh sửa form cách nhau nhiều request

~~~text
GET /products/10
  -> Client A nhận version=7
  -> Client B nhận version=7

Client A PUT /products/10 price=110k
  -> Service mới find Product(version=7)
  -> commit version=8

Client B PUT /products/10 price=120k
  -> Service mới find Product(version=8)
  -> commit version=9
~~~

Nếu server **không nhận/kiểm tra version mà B đã nhìn lúc GET**, request B vẫn có thể thành công vì nó vừa nạp entity version=8 mới. `@Version` chỉ kiểm soát state trong transaction mới từ lúc server nạp, không tự nhớ **lịch sử phiên bản của client**.

### Giải pháp

API cần gửi và kiểm tra **expectedVersion**, hoặc dùng HTTP conditional requests như `ETag`/`If-Match` theo một giao thức được thiết kế rõ.

**Đây là điểm phân biệt quan trọng:** @Version ở database và optimistic concurrency của một phiên chỉnh sửa UI nhiều request phải **được nối với nhau bằng contract API**.

## 20. DTO có expectedVersion

DTO đọc:

~~~java
package com.example.shop.api;

import java.math.BigDecimal;

public record ProductView(
        Long id,
        String name,
        BigDecimal price,
        Long version) {
}
~~~

Ví dụ JSON response:

~~~json
{
  "id": 10,
  "name": "Java Handbook",
  "price": 100000.00,
  "version": 7
}
~~~

DTO cập nhật:

~~~java
package com.example.shop.api;

import java.math.BigDecimal;

public record ChangePriceRequest(
        BigDecimal newPrice,
        Long expectedVersion) {
}
~~~

Client gửi:

~~~json
{
  "newPrice": 110000.00,
  "expectedVersion": 7
}
~~~

### Không tin version tự khai báo làm quyền truy cập

Version là **precondition cập nhật**, không phải authorization token. API vẫn phải xác minh người dùng có quyền chỉnh Product của tenant hay không. Client có thể đoán hoặc chỉnh version, nên nếu không có kiểm soát quyền, version không bảo vệ dữ liệu.

## 21. Kiểm tra expectedVersion trong service

Một phương án dùng managed entity + @Version:

~~~java
@Transactional
public void changePrice(
        long tenantId,
        long productId,
        ChangePriceRequest request) {

    if (request == null || request.expectedVersion() == null) {
        throw new IllegalArgumentException(
            "Thiếu expectedVersion");
    }

    Product product = em.find(Product.class, productId);
    if (product == null
            || !Objects.equals(
                product.getTenantId(), tenantId)) {
        throw new ProductNotFoundException(productId);
    }

    if (!Objects.equals(
            product.getVersion(),
            request.expectedVersion())) {
        throw new ProductConflictException(
            "Sản phẩm đã được cập nhật bởi giao dịch khác");
    }

    product.changePrice(request.newPrice());
}
~~~

`ProductNotFoundException` và `ProductConflictException` là custom exceptions do ứng dụng định nghĩa. Giả sử đoạn method nằm trong service dùng EntityManager transaction-bound và import DTO/Objects tương ứng.

### Có race sau kiểm tra version trong Java không?

Có thể có:

~~~text
T1: em.find Product(version=7)
T2: kiểm tra request.expectedVersion=7 -> khớp
T3: transaction khác commit version=8
T4: service sửa price và flush
~~~

Nhưng nếu Product vẫn là **managed entity có @Version**, UPDATE ở T4 sẽ kiểm tra version=7 và phát hiện conflict. Do đó cần **cả kiểm tra expectedVersion từ client** lẫn **version-aware write tại database** để bảo vệ hai khoảng thời gian khác nhau.

### Không tạo exception rồi trả HTTP success

Custom conflict exception thường là unchecked để transaction rollback theo cấu hình Spring mặc định. Cấu hình mapping exception sang HTTP cần thực hiện ngoài transaction boundary phù hợp. Không bắt conflict rồi gọi commit như thể cập nhật thành công.

## 22. OptimisticLockException và exception của framework

JPA định nghĩa `jakarta.persistence.OptimisticLockException` cho xung đột optimistic locking.

Trong ứng dụng Spring, exception có thể được chuyển thành các loại exception của Spring DataAccess như `ObjectOptimisticLockingFailureException` hoặc bao bọc bởi một exception ở transaction boundary, tùy stack và thời điểm phát hiện.

Không viết code chỉ mong đúng một class exception trên mọi provider:

~~~java
try {
    updateSomething();
} catch (OptimisticLockException ex) {
    // Chắc chắn bắt được mọi conflict?
}
~~~

Nếu conflict xảy ra khi transaction manager commit **sau khi method service đã return**, nơi try/catch trong service có thể không bắt được lỗi ấy.

### Ba lớp exception cần phân biệt

| Lỗi | Bản chất |
| --- | --- |
| Validation/business conflict | Request sai quy tắc hoặc không thể chấp nhận |
| JPA optimistic conflict | Dữ liệu versioned đã thay đổi trong lúc ghi |
| Serialization/deadlock conflict | DB isolation/locking không cho transaction commit |

Cả ba có thể khiến request không thành công, nhưng chiến lược retry/hiển thị cho người dùng khác nhau.

### Thông điệp cho người dùng

Thay vì trả một thông báo kỹ thuật chứa SQL và tên bảng:

> Sản phẩm đã được thay đổi từ lúc bạn mở trang. Hãy tải lại dữ liệu và kiểm tra trước khi lưu tiếp.

Đây là cách trình bày conflict ở tầng nghiệp vụ, không tiết lộ thông tin hạ tầng.

## 23. HTTP API: 409 Conflict và 412 Precondition Failed

Có hai cách phổ biến để biểu diễn optimistic concurrency ở HTTP:

1. Request JSON có `expectedVersion`, service trả **409 Conflict** khi state hiện tại không khớp.
2. Server phát **ETag**, client gửi `If-Match` ở PUT/PATCH; nếu precondition không thỏa, server thường trả **412 Precondition Failed**.

Đây là lựa chọn thiết kế HTTP/API, không phải JPA tự sinh những status code ấy.

### Ví dụ GET với ETag

~~~http
GET /api/products/10 HTTP/1.1
Authorization: Bearer ...
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-10-v7"

{
  "id": 10,
  "name": "Java Handbook",
  "price": 100000.00
}
~~~

### PUT có điều kiện

~~~http
PUT /api/products/10 HTTP/1.1
If-Match: "product-10-v7"
Content-Type: application/json

{
  "price": 110000.00
}
~~~

Server kiểm tra resource/version tương ứng. Nếu current version đã 8:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/json

{
  "code": "STALE_PRODUCT_VERSION",
  "message": "Dữ liệu đã thay đổi, vui lòng tải lại."
}
~~~

### Lưu ý về ETag

- ETag là validator của HTTP representation/resource, không phải một trường JPA bắt buộc.
- Nếu ánh xạ ETag chỉ từ entity version, phải định nghĩa trường hợp representation còn phụ thuộc dữ liệu khác và cache semantics.
- Với `If-Match`, cần tuân theo **strong comparison** của HTTP; không dùng một weak ETag (tiền tố `W/`) rồi kỳ vọng điều kiện mạnh khớp như nhau.
- Không lấy ETag từ client làm quyền truy cập; authorization vẫn độc lập.
- Cần xử lý missing precondition theo contract, có thể dùng 428 Precondition Required nếu API bắt buộc mọi update phải có điều kiện.

## 24. PATCH từng trường có tránh lost update?

Ví dụ client B gửi:

~~~json
{
  "price": 120000.00
}
~~~

thay vì gửi toàn bộ Product cũ. Đây là cách giảm rủi ro **ghi đè những field không định sửa**.

Nhưng PATCH **không tự giải quyết lost update** nếu hai client cùng sửa price:

~~~text
A PATCH price=110000
B PATCH price=120000 trên dữ liệu cũ
~~~

Nếu không có precondition/version check, B vẫn có thể âm thầm thay đổi giá của A.

### Hai cơ chế bổ sung nhau

| Cơ chế | Mục tiêu |
| --- | --- |
| PATCH chỉ field được sửa | Không ghi đè field client không định thay |
| ExpectedVersion/If-Match | Phát hiện resource đã thay đổi từ lúc client đọc |
| @Version khi flush | Phát hiện transaction khác vừa update giữa read và write của server |

Thiết kế tốt thường dùng **cả giới hạn write-set và concurrency precondition**, tùy yêu cầu nghiệp vụ.

## 25. Detached entity, merge và mất cập nhật

Một entity trở thành detached khi EntityManager đóng, `clear()` hoặc `detach()`. Khi gọi:

~~~java
Product managed = em.merge(detachedProduct);
~~~

JPA sao chép state của detached entity sang một managed instance. Không nên hiểu `merge()` là “chỉ điền các field client thay đổi”.

### Kịch bản nguy hiểm

~~~text
T0: Product (name="A", price=100, version=7)

Client X giữ object detached version=7.
Client Y cập nhật price=120, DB version=8.

X gửi detached object cũ:
   name="B"
   price=100
   version=7

Service merge toàn bộ state.
~~~

Nếu version của detached entity được giữ đúng và provider áp optimistic checking, merge/flush có thể phát hiện version stale và từ chối. Nhưng nếu ứng dụng **bỏ version**, tạo entity mới với default values, bypass checks hoặc tự ghi SQL, việc sao chép state cũ có thể làm mất các cập nhật của Y.

### Không merge entity dựng trực tiếp từ request

Anti-pattern:

~~~java
Product input = objectMapper.readValue(
    requestBody, Product.class);
em.merge(input);
~~~

Nó làm mờ các vấn đề:

- Những field nào người dùng thực sự được phép sửa?
- Những field nào vắng mặt trong request?
- Null nghĩa “xóa” hay “không cập nhật”?
- Version nào client đã nhìn thấy?
- Tenant/owner có được kiểm tra?
- Association nào được phép thay đổi?

Một DTO request rõ field + expectedVersion rồi cập nhật **managed entity đã được authorize** thường dễ an toàn hơn.

## 26. merge() trả về instance nào?

Ví dụ:

~~~java
Product managedCopy = em.merge(detached);
~~~

`merge()` **trả về managed instance** trong persistence context; đối tượng `detached` truyền vào không tự biến thành managed. Nếu tiếp tục sửa đối tượng detached sau merge:

~~~java
em.merge(detached);
detached.changePrice(new BigDecimal("100000.00"));
~~~

thay đổi sau trên `detached` không tự được dirty-check trên managed copy.

### Có thể phát hiện stale version khi merge?

Có, provider có thể kiểm tra version trong lúc merge hoặc hoãn đến flush/commit tùy trường hợp. Không hứa exception nhất thiết xuất hiện **ngay tại em.merge()**.

### Một nguyên tắc ứng dụng

Cho mục tiêu chỉnh một vài field từ UI, **load managed + xác nhận expectedVersion + áp domain methods** thường minh bạch hơn việc merge toàn bộ object graph do client cung cấp.

## 27. Bulk JPQL UPDATE bypass optimistic checking tự động

Ví dụ:

~~~java
int affected = em.createQuery(
        "UPDATE Product p " +
        "SET p.price = :newPrice " +
        "WHERE p.tenantId = :tenant",
        null /* không dùng overload này trong code thật */)
    .executeUpdate();
~~~

Đoạn trên chỉ để chỉ ra ý tưởng cú pháp; với bulk update thật cần dùng overload phù hợp bên dưới, không truyền `null` vào resultClass.

~~~java
int affected = em.createQuery(
        "UPDATE Product p " +
        "SET p.price = :newPrice " +
        "WHERE p.tenantId = :tenant")
    .setParameter("newPrice", new BigDecimal("150000.00"))
    .setParameter("tenant", tenantId)
    .executeUpdate();
~~~

Đây là **JPQL bulk update** trực tiếp tác động database. Nó không được xử lý bằng cách nạp từng Product managed rồi dirty-check như `product.changePrice(...)`.

Hệ quả:

- JPA không tự bảo đảm từng row được kiểm tra `@Version` như managed entity updates.
- Những Product đã managed trong persistence context có thể giữ state cũ.
- Entity lifecycle callbacks/đường nghiệp vụ trên từng entity không tự chạy như thao tác setter.
- Version có thể không tăng trừ khi query được thiết kế điều đó hoặc provider có extension rõ ràng.

### Khi muốn bulk update có version condition

Nếu chỉ cập nhật **một Product** theo expectedVersion:

~~~java
int updated = em.createQuery(
        "UPDATE Product p " +
        "SET p.price = :newPrice, " +
        "p.version = p.version + 1 " +
        "WHERE p.id = :id " +
        "AND p.tenantId = :tenant " +
        "AND p.version = :expected")
    .setParameter("newPrice", newPrice)
    .setParameter("id", id)
    .setParameter("tenant", tenantId)
    .setParameter("expected", expectedVersion)
    .executeUpdate();

if (updated != 1) {
    throw new ProductConflictException(
        "Không cập nhật được với version yêu cầu");
}
~~~

Đoạn này là một **giao thức CAS thủ công**, không phải automatic optimistic locking. Phải bảo đảm version dùng kiểu số thích hợp và query được DB/provider hỗ trợ.

### Đồng bộ persistence context sau bulk

Nếu entity Product đã managed, nó có thể vẫn giữ price/version cũ. Tránh dùng nó tiếp để ghi nếu chưa có kế hoạch `refresh()`, `clear()` hoặc đơn giản không load entity trước bulk.

## 28. Native SQL và stored procedure có thể bỏ qua @Version

Ví dụ một procedure khác:

~~~sql
UPDATE products
SET price = 170000.00
WHERE id = 10;
~~~

Nếu gọi từ JPA:

~~~java
StoredProcedureQuery sp =
    em.createStoredProcedureQuery("update_product_price");
sp.execute();
~~~

thì **@Version trên Java entity không tự chèn `AND version = ?` vào SQL nằm bên trong stored procedure**. Procedure có thể thay row nhưng không tăng version, làm những transaction JPA khác không phát hiện sự thay đổi như mong đợi.

### Quy ước bắt buộc khi có nhiều đường ghi

Nếu sản phẩm được cập nhật qua:

- Dirty checking của JPA.
- JPQL bulk UPDATE.
- Native SQL.
- Stored procedures.
- Một ứng dụng khác dùng JDBC.

thì các đường ghi cùng một row phải có **concurrency protocol thống nhất**. Chẳng hạn:

~~~text
UPDATE business columns
SET version = version + 1
WHERE id = ... AND version = expectedVersion
~~~

hoặc một chiến lược DB-trigger/lock/rowversion được thiết kế đầy đủ với provider. Không mặc định rằng annotation trong một ứng dụng Java có thể bảo vệ các câu SQL của mọi ứng dụng khác.

## 29. @Version và read-only transaction

Một query chỉ đọc:

~~~java
Product p = em.find(Product.class, id);
long v = p.getVersion();
~~~

không thường xuyên cần tăng version. `@Version` giúp phát hiện write conflicts, không có nghĩa cứ SELECT là tăng version.

Với Spring:

~~~java
@Transactional(readOnly = true)
public ProductView findProduct(Long id) {
    // Query DTO hoặc nạp entity chỉ đọc.
}
~~~

`readOnly=true` có thể ảnh hưởng flush mode và optimization theo Spring/provider, **không phải một cơ chế optimistic locking thay thế @Version**.

### Giữ version trong DTO đọc

Nếu GET cung cấp dữ liệu cho màn hình chỉnh sửa, response nên chứa expectedVersion hoặc một ETag phản ánh version phù hợp. Nếu endpoint chỉ hiển thị danh sách công khai, có thể không cần expose version.

## 30. LockModeType.OPTIMISTIC

JPA hỗ trợ optimistic lock mode tường minh:

~~~java
Product p = em.find(
    Product.class,
    productId,
    LockModeType.OPTIMISTIC);
~~~

Hoặc:

~~~java
em.lock(p, LockModeType.OPTIMISTIC);
~~~

`LockModeType.OPTIMISTIC` có thể yêu cầu provider bảo đảm version của entity không bị một transaction khác thay đổi không tương thích trong phạm vi transaction, kể cả khi thao tác hiện tại chủ yếu đọc.

### Khi nào cần?

Một use case đọc dữ liệu và dựa vào nó để quyết định ghi **ở một entity khác**. Nếu muốn phát hiện chính entity đã đọc bị thay đổi trước khi commit, optimistic lock rõ có thể phù hợp.

### Điều kiện áp dụng

- Entity phải hỗ trợ cơ chế versioned optimistic locking phù hợp.
- Thường cần transaction đang hoạt động cho lock operation.
- Thời điểm kiểm tra có thể là flush/commit tùy provider.

**Không nhầm `OPTIMISTIC` với một database row lock vật lý như SELECT FOR UPDATE.**

## 31. LockModeType.OPTIMISTIC_FORCE_INCREMENT

Một lock mode khác:

~~~java
Product p = em.find(Product.class, id);
em.lock(p, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
~~~

Nó yêu cầu tăng version theo cơ chế provider ngay cả khi không có persistent property nào được ứng dụng sửa trực tiếp, trong những điều kiện được đặc tả hỗ trợ.

### Ví dụ: aggregate root và quan hệ con

Giả sử PurchaseOrder có nhiều OrderLine:

~~~text
PurchaseOrder#10 version=5
  lines: Line#1, Line#2
~~~

Một thao tác chỉ sửa OrderLine có thể không mặc nhiên làm `PurchaseOrder.version` tăng theo mọi mapping/provider. Nếu business cần xem **toàn bộ Order + Lines là một aggregate concurrency unit**, có thể cân nhắc:

~~~java
em.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
~~~

để làm version của Order phản ánh một thay đổi cần bảo vệ ở cấp aggregate.

### Không xem force increment là giải pháp tự động cho mọi aggregate

Phải bảo đảm mọi đường ghi vào OrderLine đều theo cùng quy ước; nếu một stored procedure sửa Lines mà không làm tăng Order version, màn hình chỉnh Order theo version vẫn có thể không biết có thay đổi khác.

`OPTIMISTIC_FORCE_INCREMENT` có chi phí ghi thêm và có thể tạo xung đột không cần thiết; chỉ dùng khi invariant nghiệp vụ đòi hỏi.

## 32. PESSIMISTIC_WRITE khác optimistic locking

Với pessimistic locking:

~~~java
Product p = em.find(
    Product.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE);
~~~

Provider yêu cầu khóa ghi ở database theo semantics DBMS, ví dụ bằng một dạng SELECT FOR UPDATE.

| Tiêu chí | Optimistic (@Version) | Pessimistic (PESSIMISTIC_WRITE) |
| --- | --- | --- |
| Khi đọc | Thường không giữ exclusive row lock dài | Có thể yêu cầu DB lock |
| Khi phát hiện cạnh tranh | Lúc cập nhật/flush/commit | Khi lấy lock hoặc cập nhật |
| Ứng dụng phải xử lý | Version conflict và retry/merge | Lock wait/timeout/deadlock |
| Phù hợp | Xung đột hiếm, form CRUD | Tranh chấp cao, invariant cần khóa |
| Chi phí | Retry khi conflict | Giữ lock, giảm concurrency |
| Khóa qua thời gian người dùng mở form | Không | Không nên giữ transaction/lock lâu như vậy |

### Không dùng pessimistic lock xuyên thời gian người dùng chỉnh form

Một request GET trả form, người dùng mở 15 phút, rồi PUT. Không nên giữ database transaction và PESSIMISTIC_WRITE lock suốt 15 phút: nó gây block, timeout, deadlock và chiếm resource.

Đối với **long-running conversation**, expectedVersion/ETag là giải pháp thích hợp hơn trong nhiều hệ thống.

## 33. Lost update khác write skew

Một lỗi concurrency khác là **write skew**:

~~~text
Quy tắc:
  Phải có ít nhất 1 bác sĩ trực ca.

A đọc: B đang trực.
B đọc: A đang trực.

A cập nhật row của A -> OFF.
B cập nhật row của B -> OFF.

Hai row khác nhau, cả hai commit,
kết quả không còn bác sĩ trực.
~~~

Nếu A và B cập nhật **hai entity rows khác nhau**, version của từng row có thể đều hợp lệ. `@Version` trên A không tự so với version của B và ngược lại.

### Phân biệt

| Anomaly | Bản chất |
| --- | --- |
| Lost update | Hai giao dịch ghi cạnh tranh trên cùng state, một thay đổi bị ghi đè |
| Write skew | Hai giao dịch đọc một điều kiện chung và ghi những row khác nhau, làm phá invariant |
| Dirty read | Đọc thay đổi chưa commit của transaction khác |
| Non-repeatable read | Đọc lại cùng row và thấy giá trị committed khác |
| Phantom | Cùng predicate truy vấn và thấy tập row thay đổi |

Giải pháp write skew có thể cần lock một row chung, SERIALIZABLE isolation, DB constraint hoặc thiết kế lại aggregate/invariant. **Không kỳ vọng @Version trên mọi entity tự giải quyết toàn bộ concurrency anomalies.**

## 34. Lost update khác duplicate request

Một client gọi:

~~~text
POST /orders
  -> Server đã COMMIT đơn hàng
  -> Response bị mất

Client tự retry POST /orders
  -> Tạo thêm đơn thứ hai.
~~~

Đây là vấn đề **idempotency**, không phải cùng một Product bị ghi đè bởi transaction cũ.

### Vì sao @Version không đủ?

Hai request có thể tạo **hai entity mới** với hai ID khác nhau; mỗi insert không xung đột version của entity kia.

Nên dùng idempotency key và unique constraint, ví dụ:

~~~sql
UNIQUE (tenant_id, request_key)
~~~

và định nghĩa cách ứng dụng trả kết quả của request đã xử lý.

### Khi retry optimistic conflict cũng cần idempotency

Nếu retry transaction chứa **side effects ngoài DB** (email, charge payment, message broker), không được tự lặp toàn bộ một cách mù quáng. Hãy dùng transactional outbox/idempotency/compensation theo phạm vi nghiệp vụ.

## 35. Có nên retry optimistic conflict tự động?

**Không phải mọi optimistic conflict đều nên retry.**

Hai loại tác vụ:

### A. Tác vụ có thể tính lại một cách an toàn

Ví dụ cộng điểm theo một sự kiện đơn nhất, có idempotency key và logic tính từ dữ liệu mới:

~~~text
Attempt 1:
  Đọc points=100,v=7
  Tính +20
  Commit -> conflict
  Rollback

Attempt 2 (transaction mới):
  Đọc points=130,v=8
  Tính +20 -> 150
  Commit thành công
~~~

Nếu business cho phép retry và không tạo side effects lặp, có thể thực hiện retry **toàn bộ unit of work trong transaction mới** với số lần giới hạn.

### B. Người dùng đang sửa dữ liệu thủ công

Nhân viên B muốn nhập giá 120.000 dựa trên trang hiển thị 100.000. Trong khi đó A đã nhập 110.000. Nếu server tự retry bằng cách nạp version mới rồi đặt luôn 120.000:

~~~text
Optimistic conflict -> retry -> write 120000
~~~

thì **mục đích phát hiện xung đột để người dùng kiểm tra thay đổi của A bị vô hiệu hóa**.

### Nguyên tắc

- Với thao tác **máy tính có thể tái tính toán**: retry toàn transaction khi logic thực sự an toàn.
- Với thao tác **quyết định của con người**: thường trả conflict để UI hiển thị thay đổi và hỏi người dùng.
- Với thanh toán/tạo đơn/hệ thống ngoài: cần idempotency và xác nhận outcome trước khi retry.

## 36. Retry cần transaction và persistence context mới

Không nên:

~~~java
try {
    em.flush();
} catch (OptimisticLockException ex) {
    Product again = em.find(Product.class, id);
    again.changePrice(...);
    em.flush();
}
~~~

Vì transaction có thể đã rollback-only và persistence context còn giữ state lỗi.

Mẫu đúng về ý tưởng:

~~~text
for attempt 1..maxRetries:
    Bắt đầu transaction mới
    Dùng persistence context mới
    Đọc dữ liệu committed mới
    Kiểm tra lại invariant
    Tính lại thay đổi một cách idempotent
    Thử flush/commit
    Nếu conflict:
        rollback
        nếu retryable và còn lần thử -> tiếp tục
        nếu không -> báo lỗi
~~~

### Spring-specific caveat

Nếu một method có `@Transactional` bao quanh **toàn bộ vòng retry**, mỗi lần lặp có thể vẫn nằm trong cùng transaction thay vì tạo transaction mới. Cần đặt retry ở **ngoài transaction boundary**, hoặc dùng transaction template / lời gọi được proxy quản lý để mỗi attempt là một transaction riêng.

Không dùng `Thread.sleep` trong transaction đang giữ lock hoặc context stale. Backoff nếu cần nên diễn ra giữa các attempts.

## 37. Expose version như thế nào trong API DTO?

Một GET dùng để chỉnh sửa:

~~~json
{
  "id": 10,
  "name": "Java Handbook",
  "price": 100000.00,
  "stock": 10,
  "version": 7
}
~~~

Một PUT/PATCH có thể chỉ cần:

~~~json
{
  "newPrice": 110000.00,
  "expectedVersion": 7
}
~~~

### Có nên cho phép client tự đặt version mới?

Không. Client chỉ **khai báo version đã quan sát**, để server so với current version.

Sai:

~~~java
product.setVersion(request.version() + 1);
~~~

Đúng về luồng:

~~~text
Client gửi expectedVersion = 7.
Server tìm Product hiện tại và xác minh quyền.
Server so expectedVersion với version đã nạp.
Server áp domain update lên managed entity.
Provider tăng/check version khi flush/commit.
~~~

### Version có thể bị thay đổi khi update không?

Nếu thao tác không làm thay đổi persistent state, provider có thể không thực hiện UPDATE hay tăng version trong một số trường hợp. Đừng dùng version như “số lần nhấn nút Save”; nó phản ánh thay đổi được quản lý theo quy tắc provider.

## 38. Cập nhật một phần và nguyên tắc tránh stale full-object overwrite

Giả sử API PUT nhận toàn bộ Product DTO:

~~~json
{
  "name": "Java Handbook",
  "price": 100000.00,
  "stock": 10,
  "version": 7
}
~~~

Nếu client chỉ sửa name nhưng gửi price/stock từ form cũ, service:

~~~java
product.rename(request.name());
product.changePrice(request.price());
// Set stock từ request dù người dùng không hề sửa...
~~~

có nguy cơ ghi lại state cũ khi @Version không được giữ đúng hoặc check bị bỏ qua. Dù có @Version, việc gửi tất cả field làm nhiều thao tác xung đột hơn vì resource version đã đổi.

### Cách thiết kế rõ hơn

- Endpoint `PATCH /products/{id}/price` với request chỉ có newPrice + expectedVersion.
- Endpoint riêng để thay stock theo nghiệp vụ (reserve/release/adjust), không có setter stock tùy ý.
- DTO validation và authorization riêng cho từng operation.
- Cho phép UI hiển thị diff khi conflict.

**Cùng một Product có nhiều loại thay đổi**; một endpoint “replace toàn entity” không phải luôn là API nghiệp vụ tốt nhất.

## 39. Một phương án merge conflict có ý thức

Giả sử:

~~~text
Version 7:
  name="Java Handbook"
  price=100000

A thay name thành "Java/JPA Handbook", commit version 8.
B định thay price thành 110000 dựa trên version 7.
~~~

Nếu nghiệp vụ cho phép merge hai field độc lập:

1. B gửi cả expectedVersion=7 và **chỉ delta price**.
2. Server phát hiện current version=8.
3. Server tải dữ liệu mới.
4. Xác định thay đổi kể từ base version 7 là name, không phải price. Việc này đòi hỏi **base snapshot, lịch sử thay đổi hoặc domain logic đủ để phân biệt**.
5. Nếu an toàn, áp price=110000 lên current Product version=8.
6. Commit update version=9 với kiểm tra version.

### Không có base snapshot thì sao?

Chỉ biết client expectedVersion=7 và currentVersion=8 **chưa đủ để chứng minh price không bị ai khác sửa**. Có thể đã có hai thay đổi price nhưng current coincidentally quay về giá cũ. Nếu muốn automatic merge chính xác, cần diff/history hoặc quy tắc business rõ.

### Đưa quyết định về UI khi cần

Với dữ liệu nhạy cảm, UI có thể hiển thị:

~~~text
Bạn đã nhập:
  price = 110000

Dữ liệu mới nhất:
  name = "Java/JPA Handbook"
  price = 100000

Chọn:
  - Tải lại và hủy thay đổi
  - Xác nhận áp dụng giá mới
~~~

Lần xác nhận tiếp theo phải dùng **version hiện tại**, không tái sử dụng expectedVersion đã thất bại.

## 40. Một service đầy đủ để bảo vệ stale form

Ví dụ service thuần JPA RESOURCE_LOCAL. Các exception domain là class unchecked do ứng dụng định nghĩa:

~~~java
package com.example.shop;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import java.math.BigDecimal;
import java.util.Objects;

public class ProductUpdateService {

    private final EntityManagerFactory emf;

    public ProductUpdateService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public long changePrice(
            long tenantId,
            long productId,
            BigDecimal newPrice,
            long expectedVersion) {

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            Product product =
                em.find(Product.class, productId);

            if (product == null
                    || !Objects.equals(
                        product.getTenantId(), tenantId)) {
                throw new IllegalArgumentException(
                    "Không tìm thấy Product");
            }

            if (product.getVersion() == null
                    || product.getVersion() != expectedVersion) {
                throw new ProductConflictException(
                    "Version không còn hợp lệ");
            }

            product.changePrice(newPrice);

            // Kiểm tra optimistic conflict sớm nếu provider
            // phải thực hiện UPDATE tại điểm flush.
            em.flush();

            // Không trả thành công trước khi commit hoàn tất.
            tx.commit();
            return product.getVersion();

        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

Với product.version là `Long`, biểu thức so sánh với `long expectedVersion` ở đây unbox Long thành long do toán hạng nguyên thủy, nên so sánh **giá trị**, không phải so sánh identity của hai wrapper objects. Dù vậy, cách `Objects.equals(product.getVersion(), Long.valueOf(expectedVersion))` cũng dễ đọc và tránh nhầm trong code thực.

### Custom exception minh họa

~~~java
public class ProductConflictException
        extends RuntimeException {

    public ProductConflictException(String message) {
        super(message);
    }
}
~~~

### Giá trị trả về version

Sau flush/commit thành công, provider có thể đã cập nhật Product.version. Một số stack hoặc chiến lược version có điểm cập nhật state khác nhau; nếu API cần ETag/version tuyệt đối chính xác sau commit, nên xác nhận behavior của provider và transaction boundary đang dùng.

### Không gọi service này trong transaction JTA-managed

Ví dụ sử dụng `em.getTransaction()` chỉ dành cho `RESOURCE_LOCAL`. Với JTA/Spring transaction-managed EntityManager, transaction manager ngoài chịu trách nhiệm begin/commit/rollback như các mục tiếp theo.

## 41. Spring transaction boundary và error mapping

Với Spring, một service thường chỉ cần:

~~~java
@Service
public class ProductService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void changePrice(
            long productId,
            long tenantId,
            long expectedVersion,
            BigDecimal newPrice) {

        Product p = em.find(Product.class, productId);
        if (p == null || p.getTenantId() != tenantId) {
            throw new ProductNotFoundException(productId);
        }

        if (!Objects.equals(
                p.getVersion(),
                Long.valueOf(expectedVersion))) {
            throw new ProductConflictException(
                "Sản phẩm đã được thay đổi");
        }

        p.changePrice(newPrice);
        // Có thể flush tường minh nếu muốn lỗi xuất hiện
        // trước khi method trả về; commit vẫn do Spring.
    }
}
~~~

Giả sử các import Spring/JPA/BigDecimal và custom exceptions đã được khai báo.

Một controller có thể map conflict thành:

~~~java
@ExceptionHandler(ProductConflictException.class)
public ResponseEntity<ProblemDetail> conflict(
        ProductConflictException ex) {

    ProblemDetail problem = ProblemDetail.forStatus(409);
    problem.setTitle("Product update conflict");
    problem.setDetail(ex.getMessage());
    return ResponseEntity.status(409).body(problem);
}
~~~

Đây là Spring MVC-specific, không phải API JPA chuẩn. Đối với `If-Match` HTTP, nên dùng semantics 412 phù hợp với precondition.

### Chú ý exception ở commit

Nếu transaction commit diễn ra ở interceptor **sau** method service, conflict có thể được ném ngoài try/catch đặt bên trong method. Controller advice hoặc tầng exception translation phù hợp phải nhận diện các optimistic concurrency exceptions thực tế của stack.

### Rollback

Spring thông thường rollback khi unchecked exception lan ra từ transactional method. Không bắt optimistic exception rồi trả success, vì transaction có thể đã rollback-only.

## 42. Đa tenant và optimistic locking

Một Product có:

~~~text
id = 10
tenantId = 300
version = 7
~~~

Version không thể thay thế authorization:

~~~java
Product p = em.find(Product.class, productId);
if (p.getVersion().equals(expectedVersion)) {
    p.changePrice(...);
}
~~~

Nếu không kiểm tra tenant/quyền, một user biết ID và version có thể sửa tài nguyên ngoài phạm vi.

### Query an toàn hơn về ngữ nghĩa

Ứng dụng có thể truy vấn Product theo cả ID và tenant:

~~~java
List<Product> found = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.id = :id " +
        "AND p.tenantId = :tenant",
        Product.class)
    .setParameter("id", productId)
    .setParameter("tenant", currentTenantId)
    .setMaxResults(1)
    .getResultList();
~~~

Sau đó mới kiểm tra version và quyền thao tác cụ thể. Dù có lọc tenant trong query, hãy xác định policy cho mọi association và dữ liệu liên quan.

### 0 affected rows của CAS có thể có nhiều ý nghĩa

Nếu SQL:

~~~sql
UPDATE products
SET price = ?, version = version + 1
WHERE id = ?
  AND tenant_id = ?
  AND version = ?;
~~~

trả 0, có thể vì:

- Product không tồn tại.
- Product không thuộc tenant.
- Version đã thay đổi.
- Một điều kiện business khác trong WHERE không thỏa.

Không tự tiết lộ chi tiết về tài nguyên ngoài tenant bằng thông báo “Product tồn tại nhưng bạn thiếu quyền” nếu chính sách hệ thống muốn che tồn tại resource.

## 43. Optimistic version và association

Giả sử:

~~~text
Order#10 version=3
  |
  +-- OrderLine#100
  +-- OrderLine#101
~~~

Nếu một transaction chỉ sửa số lượng trên OrderLine#100, có nhất thiết Order.version tăng không?

**Không được mặc định như vậy trên mọi mapping/provider.** Tăng version của root có thể phụ thuộc:

- Quan hệ owning/inverse.
- Thao tác trên collection và entity con.
- Cơ chế version của từng entity.
- Provider-specific optimistic locking behavior.
- Application có gọi `OPTIMISTIC_FORCE_INCREMENT` hoặc domain method cập nhật root không.

### Nếu conflict cần bảo vệ ở cấp Order

Định nghĩa mọi thao tác thay đổi OrderLine là thay đổi aggregate Order theo domain:

~~~java
PurchaseOrder order = em.find(
    PurchaseOrder.class, orderId);
em.lock(
    order,
    LockModeType.OPTIMISTIC_FORCE_INCREMENT);
// Thao tác trên các OrderLine.
~~~

Hoặc thiết kế version riêng ở các entity con và kiểm soát invariant/order total thống nhất.

### Không version hóa mọi entity vô điều kiện

Một số read model immutable, log append-only hoặc dữ liệu hiếm khi sửa có thể có concurrency strategy khác. Chọn version theo **những thao tác ghi và invariant cần phát hiện xung đột**.

## 44. Tác động của cache và persistence context

Persistence context giữ một managed instance theo entity identity:

~~~java
Product p1 = em.find(Product.class, id);
Product p2 = em.find(Product.class, id);

System.out.println(p1 == p2); // true
~~~

Nhưng việc gọi `find()` lần hai trong cùng context thường không có nghĩa đọc một database snapshot mới. Nếu transaction khác đã cập nhật Product, Java object cũ có thể vẫn giữ version/price cũ.

### Khi cần refresh

~~~java
em.refresh(p1);
~~~

đưa state database trở lại managed entity theo rules của transaction/provider. Tuy nhiên:

- Refresh có thể ghi đè pending changes của entity.
- Refresh không làm transaction trước đó chưa commit trở nên visible.
- Refresh không tự hòa giải quyết định sửa của người dùng.
- Sau một optimistic conflict đã làm transaction rollback-only, không coi refresh trong cùng context lỗi là giải pháp an toàn.

### Second-level cache

Nếu bật L2 cache, provider cần chính sách invalidation/locking tương thích với versioned updates. Nhưng native SQL hoặc ứng dụng ngoài JPA có thể không tuân thủ invalidation; cache có thể stale theo cấu hình. Cần kiểm chứng cache integration thay vì suy luận chỉ từ `@Version`.

## 45. Flush và clear khi bulk update

Một flow:

~~~java
Product p = em.find(Product.class, id);

int affected = em.createQuery(
        "UPDATE Product p SET p.stock = p.stock - 1, " +
        "p.version = p.version + 1 " +
        "WHERE p.id=:id AND p.stock > 0")
    .setParameter("id", id)
    .executeUpdate();
~~~

Sau bulk update, `p.getStock()` và `p.getVersion()` có thể vẫn là state cũ. Một cách quản lý:

~~~java
em.refresh(p);
~~~

hoặc:

~~~java
em.clear();
Product reloaded = em.find(Product.class, id);
~~~

### Không gọi clear trước khi xử lý pending changes

`clear()` detach tất cả managed entities và có thể bỏ những thay đổi chưa flush. Nếu cần đồng bộ pending JPA state trước bulk:

~~~java
em.flush();
// bulk UPDATE
em.clear();
~~~

nhưng phải biết flush có thể gửi SQL của **toàn bộ context**, không chỉ Product đang quan tâm.

### Đừng kết hợp bulk UPDATE và managed updates lên cùng row mà không có protocol

Nếu `p` đang dirty, bulk update version rồi commit tiếp có thể dẫn đến optimistic conflict hoặc overwrite phức tạp. Tốt hơn là dùng **một chiến lược ghi chủ đạo cho từng operation** và kiểm soát ranh giới flush/refresh.

## 46. Timestamp version và độ chính xác

Nếu ứng dụng dùng timestamp như một tín hiệu thay đổi:

~~~java
@Version
private java.sql.Timestamp version;
~~~

hãy lưu ý:

- Database và Java có thể khác độ chính xác fractional seconds.
- Clock giữa node/application/database có thể không đồng bộ.
- Mapping kiểu timestamp và timestamp generation phụ thuộc provider/DBMS.
- Dữ liệu cập nhật nhiều lần trong khoảng độ phân giải thấp có thể cần cơ chế khác để bảo đảm phân biệt.

Trong nhiều ứng dụng CRUD, `Long version` dễ giải thích và ít phụ thuộc đồng hồ hơn. Nếu DB cung cấp rowversion/SCN hoặc cơ chế revision riêng, cần map đúng theo provider và thiết kế cùng một giao thức cho mọi đường ghi.

## 47. Kiểm thử lost update bằng hai EntityManager

Một unit test chỉ mock repository không chứng minh database/provider đã thực hiện optimistic check. Cần integration test tạo **hai persistence contexts độc lập**.

Chuẩn bị:

~~~text
products:
  id=10
  price=100000
  stock=10
  version=7
~~~

Luồng test:

~~~text
EM_A / Transaction A             EM_B / Transaction B
------------------------------   ----------------------------------
BEGIN                            BEGIN
find Product#10, v=7             find Product#10, v=7
changePrice(110000)              changePrice(120000)
flush + commit thành công
                                 flush/commit -> conflict
                                 rollback
~~~

Đọc kết quả bằng EntityManager mới:

~~~text
price = 110000
version = 8
Không có silent overwrite thành 120000.
~~~

### Skeleton test

~~~java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

try {
    emA.getTransaction().begin();
    emB.getTransaction().begin();

    Product a = emA.find(Product.class, productId);
    Product b = emB.find(Product.class, productId);

    a.changePrice(new BigDecimal("110000.00"));
    b.changePrice(new BigDecimal("120000.00"));

    emA.flush();
    emA.getTransaction().commit();

    try {
        emB.flush();
        emB.getTransaction().commit();
        throw new AssertionError(
            "Expected optimistic conflict");
    } catch (OptimisticLockException expected) {
        if (emB.getTransaction().isActive()) {
            emB.getTransaction().rollback();
        }
    }
} finally {
    if (emA.getTransaction().isActive()) {
        emA.getTransaction().rollback();
    }
    if (emB.getTransaction().isActive()) {
        emB.getTransaction().rollback();
    }
    emA.close();
    emB.close();
}
~~~

Đây là **skeleton mang tính mô tả**. Test thật phải tính đến provider có thể bọc OptimisticLockException, ném ở commit thay vì flush, hoặc DB isolation báo serialization failure; không bắt mọi RuntimeException rồi kết luận optimistic check đúng. Với một số database, emA.flush có thể giữ row lock và emB bị chờ nếu giao dịch chạy xen kẽ khác. Nên thiết lập fixture, isolation và transaction timelines có kiểm soát.

### Test mức lưu trữ

Sau hai transaction, dùng **EntityManager mới** để đọc row committed, kiểm tra price/version. Đừng kiểm tra bằng EM_B đang stale sau rollback.

## 48. Test concurrency không chỉ là test tuần tự

Một test:

~~~java
serviceA.update();
serviceB.update();
~~~

trong hai transaction **không overlap về thời gian đọc** sẽ không tái tạo tình huống hai transaction cùng giữ version cũ. B phải đọc **trước khi A commit**, sau đó mới ghi.

### Hai cách kiểm thử

**A. Điều phối thủ công hai EntityManager** như skeleton ở trên:

- Mở hai transaction.
- Bắt cả hai đọc cùng version.
- Commit A.
- Flush/commit B.

**B. Dùng hai thread + barrier/latch** khi muốn kiểm tra tranh chấp khóa/hành vi thực sự concurrent:

~~~text
Worker A             Barrier             Worker B
BEGIN/find v=7  ---- wait ----     BEGIN/find v=7
                  release
UPDATE/COMMIT                      UPDATE/COMMIT
~~~

Với thread concurrency test:

- Mỗi thread có EntityManager/transaction riêng.
- Pool connection đủ cho hai giao dịch.
- Có timeout để tránh test treo.
- Phân loại optimistic conflict, deadlock, serialization failure theo DBMS.
- Không chia sẻ một EntityManager giữa threads.
- Không dùng `Thread.sleep(...)` thay thế cơ chế đồng bộ chắc chắn.

## 49. Kiểm thử stale form qua hai request HTTP

Chỉ test hai transaction overlap chưa đủ. Cần test cả client edit dựa trên GET cũ:

1. GET Product#10 → version=7 cho A và B.
2. A gửi PATCH newPrice=110000, expectedVersion=7 → thành công, version=8.
3. B gửi PATCH newPrice=120000, expectedVersion=7 → **409 Conflict** hoặc **412 Precondition Failed** theo API contract.
4. GET mới → price=110000, version=8.

### Vì sao test này khác optimistic transaction test?

Trong step 3, server thường mở transaction mới và có thể nạp Product version=8 **sau khi A đã commit**. Nếu API không kiểm tra expectedVersion từ client, JPA @Version sẽ không tự biết B đang dựa vào state version=7.

Đây là test bảo vệ **long-running user edit**, không chỉ test concurrency trong một transaction ngắn.

## 50. Kiểm thử các đường ghi ngoài JPA

Nếu hệ thống còn có một stored procedure:

~~~sql
UPDATE products
SET stock = stock - 1
WHERE id = 10;
~~~

thì phải kiểm thử rằng đường ghi này cũng tuân thủ version protocol hoặc được tách quyền sở hữu rõ ràng.

Một bài test:

1. EM_A đọc Product#10 version=7.
2. Native/procedure UPDATE stock và commit.
3. EM_A sửa price dựa trên Product version=7.
4. Kỳ vọng optimistic conflict **chỉ khi native/procedure cũng thay đổi version theo quy ước**.

Nếu procedure không tăng version, test có thể cho phép ghi thành công, chứng minh **annotation @Version không tự bảo vệ mọi writer ngoài provider**.

## 51. Các tình huống thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách tiếp cận |
| --- | --- | --- |
| Hai nhân viên ghi giá, người sau âm thầm ghi đè | Không có optimistic precondition | @Version + expectedVersion/If-Match |
| Có @Version nhưng stale form vẫn lưu thành công | Server GET mới trước mỗi update, bỏ version client | Truyền/kiểm tra expectedVersion từ GET cũ |
| UPDATE báo 0 row | Version/tenant/business predicate không khớp | Phân loại conflict/not found theo policy |
| OptimisticLockException lúc flush | Entity stale tại thời điểm UPDATE | Rollback, hiển thị conflict hoặc retry an toàn |
| Exception chỉ xuất hiện ở commit | Provider hoãn SQL/transaction boundary | Xử lý lỗi ở tầng transaction boundary |
| Sau conflict vẫn cố tiếp tục EntityManager | Transaction rollback-only/context stale | Rollback, context/transaction mới |
| Native UPDATE thay row nhưng JPA version không tăng | SQL ngoài JPA không tuân thủ version | Tăng/check version rõ trong SQL |
| Bulk JPQL update không phát hiện stale entity | Bypass per-entity version checking | Conditional bulk CAS hoặc managed updates |
| Managed entity đọc giá cũ sau bulk | Persistence context chưa đồng bộ | Refresh/clear có chủ đích |
| @DynamicUpdate được tin là đủ | Chỉ giảm cột SET, không giải quyết mọi conflict | Dùng version/invariant protection |
| Hai transactions sửa hai field vẫn conflict | Version bảo vệ cấp entity | Xem domain merge policy, không bypass mù |
| Hai transactions sửa hai row vẫn phá luật chung | Write skew, không cùng version root | Lock chung/constraint/SERIALIZABLE |
| Retry tự động ghi đè quyết định của người dùng | Retry dùng giá tuyệt đối cũ | Trả conflict để người dùng xác nhận |
| Retry cùng EM sau OptimisticLockException | Transaction cũ đã thất bại | Retry transaction mới |
| Tăng version bằng setter | Phá giao thức provider | Provider/DB protocol quản lý version |
| Version dùng timestamp không ổn định | Độ phân giải/clock/mapping | Cân nhắc numeric version |
| Tồn kho âm dù có transaction | Check-then-act, không có invariant bảo vệ | Atomic conditional SQL và constraint |
| Client retry tạo hai đơn | Duplicate request, không phải lost update | Idempotency key/unique constraint |
| Response success trước commit nhưng commit fail | Sai transaction ownership | Chỉ xác nhận sau transaction success |
| Product ở tenant khác sửa được | Version bị dùng thay authorization | Xác minh tenant/ACL độc lập |
| Unit test mock pass nhưng production lost update | Không có kiểm tra DB concurrency | Integration test hai contexts |
| PESSIMISTIC_WRITE gây nhiều timeout | Lock giữ lâu/contended | Rút ngắn transaction, cân nhắc optimistic |
| L2 cache trả dữ liệu cũ | Invalidation/native writes không đồng bộ | Kiểm chứng cache và version strategy |

## 52. Quy trình xử lý một cập nhật versioned

Một workflow API:

~~~text
Client GET resource
    |
    v
Nhận DTO + expectedVersion hoặc ETag
    |
    v
Người dùng chỉnh sửa
    |
    v
PATCH/PUT kèm precondition cũ
    |
    v
Server kiểm tra identity/tenant/ACL
    |
    v
Load Product managed phiên bản hiện tại
    |
    +-- Không tồn tại/không có quyền -> error theo policy
    |
    +-- Version không khớp -> 409/412, không ghi
    |
    v
Apply domain method chỉ cho field được phép sửa
    |
    v
Flush/version-aware UPDATE
    |
    +-- 0 row/conflict -> ROLLBACK
    |
    v
COMMIT thành công
    |
    v
Trả resource/ETag mới
~~~

### Những nguyên tắc không thể thiếu

1. Dữ liệu request phải được validate.
2. Authorization/tenant độc lập với version.
3. Version client phải gắn với **lần đọc người dùng dựa vào**, không phải state server vừa fetch.
4. Database write phải còn kiểm tra version tại thời điểm update.
5. Không trả success trước khi commit.
6. Conflict cần đường xử lý có ý nghĩa nghiệp vụ.
7. Các đường ghi ngoài JPA phải tuân thủ cùng giao thức.
8. Retry phải cân nhắc idempotency và dữ liệu mới.

## 53. Khi nào không cần khóa lạc quan kiểu @Version?

Không phải mọi UPDATE đều cần nạp entity và @Version:

- Một event counter có thể dùng atomic `UPDATE counter = counter + 1`.
- Một append-only event table có thể dùng unique key/idempotency.
- Một thao tác cần serialized access trên một tài nguyên nóng có thể dùng pessimistic lock.
- Một báo cáo chỉ đọc không sửa state có thể không cần @Version trên read model.
- Một bảng có cơ chế concurrency riêng từ database có thể dùng strategy provider-specific phù hợp.

Tuy vậy, với **entity nghiệp vụ có nhiều thao tác cập nhật độc lập trong nhiều transaction**, versioned optimistic locking là điểm xuất phát phổ biến và rõ ràng.

### Không nhầm “không dùng @Version” với “không cần concurrency design”

Nếu không version, vẫn phải có cách bảo vệ lost update/invariant: atomic SQL, constraints, locks, isolation, append-only design hoặc chiến lược được chứng minh phù hợp. **Bỏ annotation không làm tranh chấp biến mất.**

## 54. Bài tập thực hành

### Bài 1 — Nhận diện lost update

Ban đầu `balance=100`. A cộng 20, B trừ 30, cả hai đọc ban đầu 100 rồi A ghi 120, B ghi 70. Kết quả đúng theo hai thao tác độc lập là bao nhiêu, và vì sao 70 là sai?

**Gợi ý:** 90; +20 đã bị ghi đè.

### Bài 2 — Viết SQL có điều kiện version

Product#10 version=5. Hãy viết UPDATE đặt price=200000 chỉ khi version vẫn bằng 5, đồng thời tăng version.

**Gợi ý:** `UPDATE ... SET price=?, version=version+1 WHERE id=10 AND version=5`.

### Bài 3 — Dấu hiệu conflict

Một UPDATE có `WHERE id=? AND version=?` ảnh hưởng 0 row. Có thể kết luận duy nhất “version sai” không?

**Gợi ý:** không; có thể ID không tồn tại, tenant không khớp hoặc điều kiện khác không thỏa.

### Bài 4 — @Version có tự increment khi set setter không?

Ngay sau `product.changePrice()`, có được hứa version đã tăng và database đã commit chưa?

**Gợi ý:** không. Provider kiểm soát version khi đồng bộ/commit.

### Bài 5 — Flush và commit

Provider phát hiện OptimisticLockException tại `em.flush()`. Có nên catch rồi tiếp tục commit transaction đó không?

**Gợi ý:** không; rollback và xử lý conflict từ transaction/context phù hợp.

### Bài 6 — Hai field khác nhau

A sửa Product.name, B sửa Product.price trên cùng version=7. Vì sao @Version có thể từ chối B dù field không trùng?

**Gợi ý:** version bảo vệ trạng thái entity, không chỉ từng cột.

### Bài 7 — @DynamicUpdate

Có thể chỉ dùng Hibernate @DynamicUpdate để bảo đảm không bao giờ lost update không?

**Gợi ý:** không; hai transaction có thể sửa cùng field, và invariant đa field vẫn bị ảnh hưởng.

### Bài 8 — Transaction vs concurrency

Một method có Spring @Transactional nhưng entity không @Version. Có chắc tránh lost update trong mọi isolation không?

**Gợi ý:** không; transaction boundary chưa đủ để định nghĩa conflict detection.

### Bài 9 — Managed entity

Entity đã managed và được sửa trong transaction. Có cần gọi `em.merge(entity)` mới được version check không?

**Gợi ý:** không; dirty checking trên managed entity là đường ghi thông thường.

### Bài 10 — Detached form

Hai người cùng GET Product version=7. A PUT và commit version=8. B PUT nhưng server chỉ `em.find()` bản mới version=8 rồi ghi mà không kiểm tra version=7 từ B. Có thể có silent overwrite không?

**Gợi ý:** có; cần expectedVersion từ lần GET của B.

### Bài 11 — HTTP conditional update

Nếu client gửi `If-Match: "product-10-v7"` nhưng resource đã version=8, HTTP status phù hợp với precondition failure là gì?

**Gợi ý:** 412 Precondition Failed; với conflict trong body version contract có thể dùng 409 theo thiết kế.

### Bài 12 — PATCH

PATCH chỉ gửi field price có tự bảo vệ hai người cùng sửa price không?

**Gợi ý:** không; cần expectedVersion/ETag hoặc cơ chế conflict khác.

### Bài 13 — Merge

Một detached entity có price cũ, name mới. Vì sao `em.merge(detached)` không nên coi là “cập nhật chỉ name”?

**Gợi ý:** merge sao chép state detached, không tự suy luận delta người dùng muốn.

### Bài 14 — Bulk JPQL

`UPDATE Product p SET p.price=:x` có tự thực hiện version check và tăng @Version per entity không?

**Gợi ý:** không có bảo đảm như managed updates; phải thiết kế bulk CAS hoặc dùng managed entity.

### Bài 15 — Native SQL

Procedure cập nhật stock nhưng không tăng version. Transaction JPA khác đang giữ version cũ có chắc phát hiện stock đã thay đổi không?

**Gợi ý:** không, phải thống nhất version protocol.

### Bài 16 — Atomic increment

Hai transaction cần tăng counter mỗi bên 1. Vì sao `UPDATE counter=counter+1` tốt hơn đọc counter rồi đặt bằng old+1 trong trường hợp chỉ cộng dồn?

**Gợi ý:** phép cộng được thực hiện theo state DB tại thời điểm UPDATE phù hợp với locking/isolation, tránh stale absolute assignment.

### Bài 17 — Invariant đa row

Hai transaction sửa hai Doctor rows khác nhau nhưng cùng làm ca trực không còn ai. @Version trên từng Doctor có tự phát hiện không?

**Gợi ý:** không mặc định; đây là write skew.

### Bài 18 — Optimistic force increment

Một Order versioned có các OrderLine. Khi chỉ thay Line, tại sao có thể cân nhắc `OPTIMISTIC_FORCE_INCREMENT` trên Order?

**Gợi ý:** bảo vệ invariant ở cấp aggregate root theo giao thức ứng dụng.

### Bài 19 — Retry

Người dùng B đã nhập giá 120000 từ form cũ. Có nên tự retry optimistic conflict bằng cách luôn ghi 120000 lên phiên bản mới không?

**Gợi ý:** thường không; cho người dùng xem/giải quyết thay đổi khác.

### Bài 20 — Retry transactional

Nếu một transaction thất bại vì optimistic conflict, lần retry tiếp theo nên dùng cùng EntityManager và transaction cũ hay transaction/context mới?

**Gợi ý:** mới; đọc lại state, kiểm tra invariant và idempotency.

### Bài 21 — Pessimistic lock

Có nên giữ `PESSIMISTIC_WRITE` row lock suốt thời gian nhân viên mở form 30 phút không?

**Gợi ý:** không; gây contention và chiếm tài nguyên.

### Bài 22 — Version và authorization

Người dùng đoán đúng Product ID và version. Có được phép cập nhật nếu tenant không khớp không?

**Gợi ý:** không; version không thay thế quyền truy cập.

### Bài 23 — Test hai EntityManager

Làm thế nào để integration test chứng minh version-aware UPDATE từ chối ghi đè?

**Gợi ý:** mở hai EM/transactions, cả hai đọc cùng version trước khi một commit; bên còn lại flush/commit và kiểm tra conflict, sau đó đọc DB bằng EM mới.

### Bài 24 — Test stale HTTP request

Vì sao kiểm thử hai transaction overlap chưa đủ để bảo vệ form người dùng?

**Gợi ý:** request B có thể bắt đầu transaction mới sau A và nạp version mới; phải kiểm tra expectedVersion từ lần GET cũ.

### Bài 25 — Thay đổi ngoài JPA

Một job JDBC cập nhật price mà không tăng version. Bạn sẽ bổ sung integration test nào?

**Gợi ý:** JPA đọc version cũ, JDBC cập nhật và commit, JPA sửa/flush; xác minh protocol cần tăng version để bắt conflict.

## 55. Bảng ghi nhớ nhanh

| Vấn đề | Cách hiểu/cách làm |
| --- | --- |
| Lost update | Ghi một giá trị từ state cũ, che mất write khác |
| @Transactional | Ranh giới transaction; không tự thay version check |
| @Version | Metadata để JPA kiểm tra version trên đường ghi entity managed |
| SQL version-aware | `UPDATE ... SET version=version+1 WHERE id=? AND version=?` |
| affected rows=0 | Không khớp PK/version/tenant/điều kiện khác |
| Conflict xảy ra khi nào | Có thể lúc flush hoặc commit |
| Sau optimistic conflict | Rollback, transaction/context mới |
| ETag/If-Match | Bảo vệ stale form qua nhiều HTTP requests |
| 409/412 | Lựa chọn contract; 412 cho If-Match không thỏa |
| Merge detached | Sao chép state, không phải patch-by-delta |
| Bulk JPQL/Native SQL | Không tự làm optimistic checks per entity như managed updates |
| @DynamicUpdate | Tối ưu SET columns; không thay version |
| Atomic increment | Dùng phép tính trên giá trị DB khi nghiệp vụ phù hợp |
| PESSIMISTIC_WRITE | DB lock, có chờ/timeout/deadlock |
| OPTIMISTIC_FORCE_INCREMENT | Có thể tăng version để bảo vệ aggregate |
| Write skew | Invariant đa row; @Version riêng từng row không đủ |
| Retry | Chỉ khi nghiệp vụ/idempotency cho phép; transaction mới |
| Multi-tenant | Kiểm tra quyền riêng với expectedVersion |
| Integration test | Hai EM đọc version cũ, một commit, một conflict |
| Stale form test | GET version 7, A update lên 8, B gửi 7 bị từ chối |

## Kết luận

**Vấn đề ghi đè thay đổi khi nhiều giao dịch cùng cập nhật** xuất hiện khi một thao tác ghi dựa trên state đã cũ nhưng không phát hiện có write khác xảy ra trong khoảng thời gian đọc–ghi. Một transaction và một lời gọi setter thành công chưa đủ để bảo đảm thao tác cuối không làm mất dữ liệu của người khác. Tùy DBMS/isolation, database có thể phát hiện một số xung đột, nhưng ứng dụng cần một concurrency protocol có ngữ nghĩa rõ.

Trong JPA, **`@Version` là cơ chế optimistic locking phổ biến**: provider cập nhật với điều kiện phiên bản cũ vẫn khớp, rồi tăng version; nếu row đã đổi, thao tác bị báo optimistic conflict thay vì âm thầm overwrite. Conflict có thể được phát hiện khi flush hoặc commit; sau đó thường phải rollback và quyết định retry hoặc yêu cầu người dùng giải quyết xung đột.

Để bảo vệ **form chỉnh sửa qua nhiều HTTP request**, không chỉ đặt @Version trên entity mà còn phải mang **expectedVersion hoặc ETag/If-Match từ lần GET đến lần PUT/PATCH**, kiểm tra precondition và giữ version-aware write tại database. Các đường ghi khác như bulk JPQL, native SQL, stored procedure hay JDBC phải tuân thủ cùng giao thức; thay đổi version đơn lẻ cũng không thay thế permission checks, idempotency, constraints hoặc giải pháp cho write skew nhiều row.

Nguyên tắc thực hành là **đọc kèm phiên bản, chỉ cập nhật những field được phép, kiểm tra phiên bản khi ghi, commit toàn bộ unit of work, và xử lý conflict một cách có chủ đích**. Khi thiết kế như vậy, hệ thống không hứa rằng mọi người có thể cập nhật cùng lúc mà không xung đột, nhưng bảo đảm những xung đột quan trọng **được nhận diện thay vì khiến dữ liệu bị ghi đè âm thầm**.
