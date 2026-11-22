# Insert, update, delete theo truy vấn và giới hạn ánh xạ thực thể

## 1. Khi nào cần bulk mutation trong HQL?

Trong Hibernate, cách làm quen thuộc để sửa dữ liệu là tải entity vào persistence context, thay đổi thuộc tính Java rồi để dirty checking tạo SQL khi flush. Cách này phù hợp khi nghiệp vụ cần kiểm tra trạng thái, gọi method domain, chạy validation và thực hiện cascade.

Nhưng một số tác vụ cần thay đổi hàng nghìn hoặc hàng triệu bản ghi theo cùng một điều kiện:

- Đánh dấu tất cả đơn hàng cũ là đã lưu trữ.
- Tăng giá hàng loạt sản phẩm theo một tỷ lệ.
- Xóa các bản ghi tạm đã hết hạn.
- Tạo snapshot cho những đơn hàng đã hoàn tất.
- Cập nhật trạng thái dựa trên dữ liệu của một entity liên quan.

Nếu tải từng entity rồi sửa, ứng dụng có thể phải materialize rất nhiều object, giữ chúng trong persistence context và phát ra nhiều câu SQL. HQL hỗ trợ các câu lệnh mutation để database thực hiện công việc theo tập hợp:

- INSERT INTO ... SELECT ...
- UPDATE ... SET ... WHERE ...
- DELETE FROM ... WHERE ...

Các thao tác này thường được gọi là **bulk DML** (*bulk data manipulation language*). Chúng chạy trực tiếp trên database thông qua SQL do Hibernate sinh ra. Vì vậy, chúng có hiệu năng tốt cho thao tác theo tập hợp, nhưng không có đầy đủ hành vi vòng đời entity như việc tải và sửa từng object.

Điểm quan trọng nhất: bulk mutation làm thay đổi dữ liệu trong database, còn các entity đang được quản lý trong persistence context có thể vẫn giữ state cũ. Cần thiết kế transaction và đồng bộ state rõ ràng.

## 2. HQL mutation tác động lên entity model

HQL dùng tên entity và thuộc tính được ánh xạ:

```hql
update Product p
set p.active = false
where p.discontinued = true
```

Ở đây Product, active và discontinued là tên trong mô hình entity. Hibernate phân tích metadata mapping rồi sinh SQL cho bảng/cột vật lý tương ứng.

Không viết theo tên bảng SQL trừ khi đang dùng native SQL:

```sql
update products
set active = false
where discontinued = true;
```

Bulk HQL vẫn tuân theo kiểu dữ liệu và mapping của entity. Tuy nhiên, nó không hoạt động như một vòng lặp gọi setter trên từng entity. Hibernate không tải từng Product, không gọi domain method cho từng instance và không thực hiện dirty checking từng object.

### 2.1. Ba loại mutation và mục đích

| Câu lệnh | Mục đích | Kết quả |
|---|---|---|
| INSERT INTO ... SELECT | Tạo hàng mới từ kết quả một truy vấn | Số entity/row được insert theo kết quả nguồn |
| UPDATE | Thay đổi thuộc tính của các entity thỏa điều kiện | Số entity instance bị ảnh hưởng theo semantics Hibernate |
| DELETE FROM | Xóa các entity thỏa điều kiện | Số entity instance bị xóa theo semantics Hibernate |

Trong HQL, INSERT có dạng insert-select. UPDATE và DELETE có thể là bulk operation trên một tập entity lớn.

## 3. API thực thi mutation trong Hibernate và JPA

### 3.1. Hibernate 6: createMutationQuery()

Hibernate 6 cung cấp API tường minh cho mutation query:

```java
String hql = """
    update Product p
    set p.active = false
    where p.discontinued = true
    """;

int affected = session.createMutationQuery(hql)
        .executeUpdate();
```

createMutationQuery() nhận HQL mutation statement và trả về MutationQuery. Gọi executeUpdate() để thực thi. Giá trị trả về là số entity instance bị ảnh hưởng theo semantics của Hibernate; với mapping nhiều bảng, con số này không nhất thiết bằng tổng số hàng SQL được cập nhật/xóa.

### 3.2. Jakarta Persistence: createQuery()

JPA có thể thực thi bulk update/delete bằng Query.executeUpdate():

```java
int affected = entityManager.createQuery("""
    update Product p
    set p.active = false
    where p.discontinued = true
    """)
    .executeUpdate();
```

JPA chuẩn hỗ trợ bulk update và bulk delete. INSERT ... SELECT không thuộc tập bulk DML chuẩn của JPQL; câu insert-select là khả năng HQL của Hibernate.

### 3.3. Hibernate 5 và code cũ

Ở các phiên bản Hibernate cũ, code thường gọi session.createQuery(hql).executeUpdate(). Khi nâng lên Hibernate 6, ưu tiên API createMutationQuery() cho câu mutation để thể hiện rõ loại query.

### 3.4. Mutation cần transaction

Bulk update/delete cần transaction đang hoạt động. Nếu gọi ngoài transaction, provider có thể ném TransactionRequiredException:

```java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();
try {
    int count = entityManager.createQuery("""
        update Product p
        set p.active = false
        where p.discontinued = true
        """).executeUpdate();

    tx.commit();
} catch (RuntimeException | Error failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
}
```

Trong Spring hoặc Jakarta EE, transaction có thể do interceptor/container sở hữu. Khi đó không gọi EntityTransaction.begin() hay commit() thủ công bên trong method đã được quản lý transaction.

## 4. INSERT INTO ... SELECT

### 4.1. Cú pháp

HQL hỗ trợ insert-select theo dạng:

```hql
insert into TargetEntity (property1, property2, property3)
select source.expression1, source.expression2, source.expression3
from SourceEntity source
where ...
```

Danh sách thuộc tính ở phần insert into phải tương ứng về số lượng, thứ tự và kiểu với các biểu thức ở phần select.

Ví dụ tạo snapshot đơn hàng. Giả sử entity đích có ID được gán từ ID đơn hàng:

```java
@Entity
@Table(name = "order_snapshots")
public class OrderSnapshot {
    @Id
    private Long id;

    @Column(nullable = false)
    private String orderNumber;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal total;

    @Column(nullable = false)
    private String status;

    protected OrderSnapshot() {}
}
```

HQL:

```hql
insert into OrderSnapshot (id, orderNumber, total, status)
select o.id, o.orderNumber, o.total, o.status
from Order o
where o.status = :completedStatus
```

Thực thi:

```java
int inserted = session.createMutationQuery("""
    insert into OrderSnapshot (id, orderNumber, total, status)
    select o.id, o.orderNumber, o.total, o.status
    from Order o
    where o.status = :status
    """)
    .setParameter("status", OrderStatus.COMPLETED)
    .executeUpdate();
```

Database có thể thực hiện một lệnh INSERT ... SELECT mà không cần tạo object OrderSnapshot cho từng đơn hàng trong Java.

### 4.2. Vì sao insert-select hữu ích?

Giả sử cần lưu snapshot cho 200.000 đơn hàng đã hoàn tất:

```text
Cách tải và persist từng entity:

SELECT Orders
    │
    ▼
Tạo 200.000 OrderSnapshot object
    │
    ▼
persist từng object
    │
    ▼
flush nhiều lần / quản lý batch

Cách insert-select:

INSERT INTO order_snapshots (...)
SELECT ...
FROM orders
WHERE status = 'COMPLETED'
    │
    ▼
Database tạo các hàng theo tập hợp
```

Insert-select giảm lượng object phải tạo và dữ liệu phải truyền qua JDBC. Nó đặc biệt hữu ích khi nguồn và đích nằm trong cùng database và mapping phù hợp với câu truy vấn.

### 4.3. Insert-select không phải INSERT VALUES

HQL insert có dạng lấy dữ liệu từ một truy vấn. Nếu chỉ muốn tạo một entity từ một command đơn lẻ:

```java
Product product = new Product(code, name, price);
entityManager.persist(product);
```

Đây thường là lựa chọn đúng hơn. persist() tham gia lifecycle entity, xử lý ID generation và các cơ chế mapping thông thường.

Nếu muốn insert nhiều dòng với giá trị literal cố định, hãy cân nhắc native SQL hoặc batch persist() tùy yêu cầu. Không giả định cú pháp INSERT INTO Entity (...) VALUES (...) của SQL cũng là cú pháp HQL insert chuẩn.

## 5. Giới hạn ánh xạ của INSERT

Insert-select có một số ràng buộc quan trọng.

### 5.1. Kiểu dữ liệu và thứ tự cột phải tương thích

```hql
insert into ProductSnapshot (code, price, capturedAt)
select p.code, p.price, current_timestamp
from Product p
```

Các biểu thức select phải có kiểu tương thích với thuộc tính đích:

- code phải tương thích kiểu với thuộc tính code.
- price phải tương thích kiểu số/tiền.
- current_timestamp phải được ánh xạ tương thích với thuộc tính thời gian.

Hibernate kiểm tra được một số sai lệch kiểu khi phân tích HQL, nhưng database vẫn có thể từ chối vì precision, length, nullability, constraint hoặc kiểu SQL cụ thể.

### 5.2. Identifier và strategy sinh khóa

Entity đích cần có identifier hợp lệ. Nếu ID không nằm trong danh sách insert, khả năng tự sinh ID phụ thuộc generator, Hibernate version và dialect. Không phải mọi identifier strategy đều có thể được sử dụng an toàn với một câu insert-select.

Để tránh giả định sai:

- Nếu dùng assigned identifier, liệt kê thuộc tính ID và cung cấp giá trị duy nhất trong select.
- Nếu muốn Hibernate sinh ID, xác nhận generator hỗ trợ bulk insertion trong phiên bản và dialect đang dùng.
- Kiểm tra sequence/identity behavior và uniqueness của dữ liệu nguồn.
- Không dùng lại ID nguồn cho entity đích nếu hai bảng dùng chung namespace khóa hoặc ID có thể trùng.

Với entity dùng IDENTITY, insert-select có thể gặp giới hạn vì database sinh ID trong lúc insert và HQL không nhận từng ID như vòng lặp persist(). Hãy kiểm chứng generator cụ thể; nếu không được hỗ trợ, dùng native SQL phù hợp hoặc batch persist.

### 5.3. Insert không polymorphic

HQL insert là thao tác **không polymorphic**. Câu insert nhắm tới entity được chỉ định và các thuộc tính được liệt kê; nó không tự tạo instance của mọi subclass như một lệnh persist() có thể làm khi ứng dụng tạo object subtype.

Ví dụ hierarchy:

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_type")
public abstract class Payment {
    @Id
    private Long id;

    private BigDecimal amount;
}

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    private String lastFourDigits;
}
```

Không giả định một lệnh insert into Payment ... select ... có thể suy ra subtype CardPayment từ dữ liệu nguồn và tự điền mọi thuộc tính subclass. Nếu cần tạo các subtype khác nhau, cần tách truy vấn/chiến lược phù hợp, hoặc dùng managed entities/native SQL được thiết kế cho schema cụ thể.

### 5.4. Thuộc tính mapping không phải cột ghi được

Một entity có thể chứa:

- Thuộc tính @Formula được tính từ SQL.
- Thuộc tính chỉ đọc hoặc được đánh dấu không insert/update.
- Thuộc tính do database generated.
- Thuộc tính nằm trong secondary table.
- Embedded value được trải trên nhiều cột.

Không thể coi mọi getter/field Java đều là cột insertable. Insert-select phải nhắm vào những thuộc tính mà Hibernate có thể ghi theo mapping. Thuộc tính formula/derived thường không phải target hợp lệ. Với secondary table, embeddable hoặc mapping phức tạp, kiểm tra SQL được sinh và khả năng của mutation strategy.

### 5.5. Association và collection

Insert một entity có quan hệ không giống với việc sao chép toàn bộ object graph. Insert-select không tự chạy cascade persist cho các entity liên quan và không tự tạo các phần tử collection như khi thao tác object graph.

Nếu target có association, việc gán foreign key phải được biểu diễn bằng giá trị tương thích với mapping/provider. Với mapping phức tạp, an toàn hơn là insert các scalar property/identifier được hỗ trợ, hoặc dùng managed entity/native SQL. Không giả định một câu insert-select sẽ tự insert các entity ở phía bên kia của association.

OneToMany, ManyToMany và ElementCollection có thể dùng bảng phụ/collection table. Việc insert entity gốc không tự tạo các row collection tương ứng. Nếu cần sao chép association, phải có mutation riêng cho bảng quan hệ (thường qua native SQL) hoặc xử lý qua managed entities.

### 5.6. Version và timestamp

Entity có @Version hoặc timestamp property cần giá trị hợp lệ. Hành vi khi không liệt kê các thuộc tính version/timestamp phụ thuộc cơ chế seed/generator và provider. Khi dữ liệu được insert-select, đừng giả định mọi giá trị khởi tạo giống hệt persist() trong mọi mapping.

Nếu cần version cụ thể, có thể đưa thuộc tính đó vào danh sách insert khi mapping và cú pháp cho phép; nếu muốn dùng giá trị seed do provider quản lý, hãy xác nhận behavior của Hibernate version. Database default và trigger cũng có thể tham gia, nhưng cần mapping tương ứng để Hibernate hiểu.

## 6. UPDATE: cập nhật nhiều entity theo điều kiện

### 6.1. Cú pháp cơ bản

```hql
update Product p
set p.active = false
where p.discontinued = true
```

Ví dụ tăng giá các sản phẩm thuộc một danh mục:

```hql
update Product p
set p.price = p.price * :factor
where p.category = :category
```

Thực thi:

```java
int updated = session.createMutationQuery("""
    update Product p
    set p.price = p.price * :factor
    where p.category = :category
    """)
    .setParameter("factor", new BigDecimal("1.05"))
    .setParameter("category", category)
    .executeUpdate();
```

Database cập nhật trực tiếp các hàng phù hợp. Hibernate không tải từng Product và gọi setPrice() trên từng instance.

### 6.2. Cập nhật nhiều thuộc tính

```hql
update Order o
set o.status = :newStatus,
    o.archived = true
where o.status = :oldStatus
  and o.createdAt < :cutoff
```

Mỗi thuộc tính trong SET phải là state được ánh xạ và có thể cập nhật trong ngữ cảnh mutation. Dùng parameter cho giá trị runtime thay vì ghép chuỗi.

### 6.3. Update với biểu thức số học

```hql
update InventoryItem i
set i.available = i.available - :quantity
where i.id = :id
  and i.available >= :quantity
```

Đây là dạng conditional update hữu ích cho tồn kho. Điều kiện và phép trừ được thực hiện nguyên tử trong một câu SQL. executeUpdate() trả số entity bị ảnh hưởng; nếu bằng 0, có thể không có item hoặc không đủ tồn kho.

Tuy nhiên, cần xác định cách phối hợp với @Version, audit, cache và các managed entity đang tồn tại. Bulk update không tự chạy domain method reserve() và validation Java của entity.

## 7. UPDATE với truy vấn con

HQL bulk update không dùng join clause như một truy vấn select thông thường. Khi điều kiện phụ thuộc entity khác, correlated subquery thường là cách diễn đạt phù hợp.

Ví dụ tăng giá những sản phẩm thuộc danh mục đang khuyến mãi:

```hql
update Product p
set p.price = p.price * 0.90
where exists (
    select 1
    from Promotion pr
    where pr.category = p.category
      and pr.active = true
)
```

Ví dụ cập nhật trạng thái đơn nếu Customer bị khóa:

```hql
update Order o
set o.status = :blockedStatus
where exists (
    select 1
    from Customer c
    where c = o.customer
      and c.blocked = true
)
```

Subquery giữ logic liên quan tới entity khác ở trong WHERE. Cách này thường dễ kiểm soát hơn việc cố viết join trực tiếp trong câu update.

### 7.1. Không dùng join tùy tiện trong SET

Một truy vấn SELECT có thể join nhiều association:

```hql
select p
from Product p
join p.category c
where c.active = true
```

Nhưng bulk update không có cùng khả năng join như SELECT. Tránh viết:

```hql
update Product p
join p.category c
set p.active = false
where c.active = false
```

Đây không phải mẫu HQL bulk update portable/được hỗ trợ như SELECT join. Hãy dùng subquery:

```hql
update Product p
set p.active = false
where exists (
    select 1
    from Category c
    where c = p.category
      and c.active = false
)
```

Với truy vấn cần join phức tạp, aggregate hoặc window function, native SQL có thể là lựa chọn phù hợp hơn HQL mutation.

## 8. Version khi bulk UPDATE

### 8.1. Bulk update không tự đồng bộ @Version như dirty checking

Với thao tác entity thông thường, Hibernate dùng @Version để phát hiện stale update. Nhưng bulk HQL update chạy trực tiếp trên database, bỏ qua cơ chế dirty checking từng entity. Do đó không nên giả định version property tự tăng như khi sửa managed entity.

Ví dụ entity:

```java
@Entity
public class InventoryItem {
    @Id
    private Long id;

    private int available;

    @Version
    private long version;
}
```

Bulk update:

```hql
update InventoryItem i
set i.available = i.available - :quantity
where i.id = :id
```

không tự mang đầy đủ semantics optimistic locking của một lần sửa entity bình thường. Một transaction khác có thể đã đọc version cũ mà không được phát hiện qua version check nếu câu bulk mutation không đưa version vào điều kiện.

### 8.2. HQL extension: update versioned

Hibernate HQL có từ khóa versioned:

```hql
update versioned InventoryItem i
set i.available = i.available - :quantity
where i.id = :id
  and i.available >= :quantity
```

update versioned yêu cầu Hibernate tăng version/timestamp property theo cơ chế versioning khi thực hiện bulk update. Đây là HQL extension, không thuộc JPQL chuẩn. Hỗ trợ với custom version type có giới hạn; cần kiểm tra kiểu version và Hibernate version của dự án.

Ví dụ:

```java
int changed = session.createMutationQuery("""
    update versioned InventoryItem i
    set i.available = i.available - :quantity
    where i.id = :id
      and i.available >= :quantity
    """)
    .setParameter("quantity", 2)
    .setParameter("id", itemId)
    .executeUpdate();

if (changed == 0) {
    throw new IllegalStateException(
            "Không tìm thấy mặt hàng hoặc tồn kho không đủ");
}
```

### 8.3. Compare-and-set với version tường minh

Một cách khác là đưa version mong đợi vào WHERE và tăng version trong SET:

```hql
update InventoryItem i
set i.available = i.available - :quantity,
    i.version = i.version + 1
where i.id = :id
  and i.version = :expectedVersion
  and i.available >= :quantity
```

Đây là dạng compare-and-set. Nếu không có hàng nào được cập nhật, version đã thay đổi, ID không tồn tại hoặc số lượng không đủ. Ứng dụng có thể đọc lại state trong transaction mới để xác định nguyên nhân chính xác.

Không đồng thời dùng update versioned và tự tăng version nếu không có chủ đích, vì có thể làm version tăng hai lần hoặc tạo semantics không mong muốn.

### 8.4. Khi nào dùng versioned bulk update?

- Dùng update versioned khi cần báo cho các transaction optimistic khác rằng entity đã thay đổi.
- Dùng version trong WHERE khi command mang theo version mà client đã đọc trước đó.
- Dùng conditional update theo giá trị hiện tại khi invariant có thể kiểm tra nguyên tử bằng SQL.
- Dùng managed entity nếu cần đầy đủ domain validation, callback và logic từng instance.

Versioning vẫn chỉ bảo vệ các row/version được câu lệnh cập nhật. Nó không tự bảo vệ một graph association không được thay đổi hoặc version hóa.

## 9. DELETE: xóa entity theo điều kiện

### 9.1. Cú pháp

```hql
delete from Review r
where r.createdAt < :cutoff
```

Hoặc có thể bỏ alias:

```hql
delete from Review
where createdAt < :cutoff
```

Ví dụ xóa các bản ghi tạm hết hạn:

```java
int deleted = session.createMutationQuery("""
    delete from TemporaryToken t
    where t.expiresAt < :now
    """)
    .setParameter("now", Instant.now())
    .executeUpdate();
```

Database xóa tập row thỏa điều kiện. Hibernate không tải từng TemporaryToken rồi gọi entityManager.remove() trên mỗi object.

### 9.2. DELETE với subquery

Xóa Review thuộc Book đã archive:

```hql
delete from Review r
where exists (
    select 1
    from Book b
    where b = r.book
      and b.archived = true
)
```

Xóa Order không có Payment:

```hql
delete from Order o
where not exists (
    select 1
    from Payment p
    where p.order = o
)
```

Đây là ví dụ về điều kiện trên association. Trước khi thực thi, cần xác định FK, cascade ở database, constraint và ý nghĩa nghiệp vụ của việc xóa.

## 10. DELETE không chạy cascade và callback entity như remove()

Đây là một trong những khác biệt quan trọng nhất giữa bulk delete và xóa entity thông thường.

Với entity managed:

```java
Order order = entityManager.find(Order.class, orderId);
entityManager.remove(order);
```

Hibernate/JPA có thể áp dụng cascade remove, orphan removal, entity lifecycle callbacks và các quy tắc mapping liên quan.

Với bulk HQL:

```hql
delete from Order o
where o.status = :cancelled
```

Hibernate không tải từng Order và không thực hiện đầy đủ vòng đời remove trên từng object. Không trông đợi:

- CascadeType.REMOVE chạy như khi gọi remove() từng entity.
- orphanRemoval=true xử lý graph giống thao tác collection.
- @PreRemove/@PostRemove được gọi cho từng entity.
- Bean Validation lifecycle được gọi trên từng object.
- Domain method hoặc listener ứng dụng được thực thi.

Database vẫn thực thi foreign key, unique/check constraints và trigger. Nếu FK ngăn xóa vì còn child rows, câu lệnh có thể thất bại. Nếu database có ON DELETE CASCADE, database có thể xóa hàng liên quan theo quy tắc riêng; đó là hành vi của database, không phải JPA cascade callback.

### 10.1. Bulk delete và collection table

Entity có thể được lưu ở nhiều bảng hoặc có collection table. Hibernate cần thực hiện mutation trên các bảng vật lý liên quan theo mapping và mutation strategy. Tuy nhiên, đừng suy ra rằng bulk delete sẽ chạy toàn bộ cascade object graph hoặc các callback giống remove() trên từng object.

Với FK/collection table, hãy kiểm tra schema và SQL thực tế:

- Bảng phụ có được provider dọn theo mutation strategy không?
- Có FK ON DELETE CASCADE hay không?
- Có bảng con entity độc lập cần xóa riêng không?
- Có constraint ngăn xóa parent không?

Nếu yêu cầu nghiệp vụ là xóa graph và chạy callback cho từng node, dùng managed entity lifecycle hoặc một quy trình xóa được thiết kế rõ ràng.

### 10.2. Soft delete

Nếu entity dùng cờ deleted thay vì xóa vật lý, có thể bulk update:

```hql
update Customer c
set c.deleted = true,
    c.deletedAt = :now
where c.lastActiveAt < :cutoff
```

Đây là một update theo tập hợp, nhưng cần bảo đảm nó phù hợp với filter, query restriction, audit và quy tắc uniqueness của hệ thống. Đừng giả định custom SQL delete hoặc annotation soft-delete của provider sẽ được áp dụng giống hệt cho mọi bulk HQL delete. Nếu muốn soft delete, một câu update tường minh thường dễ hiểu hơn.

## 11. Polymorphism và inheritance khi bulk mutation

HQL update và delete là các thao tác polymorphic theo entity target. Nếu query trên superclass/root entity, các subclass phù hợp cũng có thể nằm trong tập entity bị ảnh hưởng.

Ví dụ:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {
    @Id
    private Long id;
    private BigDecimal amount;
}

@Entity
public class CardPayment extends Payment {
    private String cardToken;
}

@Entity
public class BankTransfer extends Payment {
    private String bankReference;
}
```

Mutation:

```hql
update Payment p
set p.amount = 0
where p.amount < 0
```

Query nhắm tới entity hierarchy. Với JOINED, dữ liệu của một instance có thể nằm trong bảng superclass và bảng subclass. Hibernate phải sinh SQL phù hợp với nhiều bảng.

### 11.1. Một entity có thể chiếm nhiều bảng vật lý

Mapping nhiều bảng có thể đến từ:

- InheritanceType.JOINED.
- @SecondaryTable.
- Một số mapping component/collection.
- Các bảng phụ được provider quản lý.

Vì vậy một câu HQL mutation có thể cần nhiều SQL statement hoặc một chiến lược mutation đặc biệt. Hibernate có thể dùng bảng tạm, CTE, inline identifier list hoặc cơ chế phù hợp dialect để xác định tập ID rồi cập nhật/xóa các bảng vật lý.

### 11.2. Số lượng trả về không nhất thiết bằng số row SQL

executeUpdate() báo số entity instance bị ảnh hưởng theo semantics của Hibernate, không phải tổng số hàng trên mọi bảng vật lý. Một Payment có thể làm thay đổi nhiều hàng SQL nhưng vẫn là một entity instance.

Nếu cần đếm chính xác số row ở từng bảng, dùng native SQL hoặc truy vấn đo lường riêng trên schema/database.

### 11.3. Multi-table mutation phụ thuộc dialect

Chiến lược multi-table update/delete phụ thuộc Hibernate version, database dialect và cấu hình. Một số database hỗ trợ CTE hoặc temporary tables tốt; database khác có giới hạn về temporary table, DDL transaction hoặc số bind parameters.

Với inheritance hoặc secondary tables, hãy kiểm tra SQL được sinh trên database production-like. Không giả định một HQL mutation luôn trở thành một SQL statement đơn giản.

## 12. Mapping giới hạn việc ghi theo truy vấn

Bulk HQL hoạt động trên persistent state được mapping. Không phải mọi thứ trong entity Java đều là target hợp lệ.

| Mapping/đặc tính | Điều cần lưu ý |
|---|---|
| Basic property | Thường là target update/insert nếu mapping cho phép ghi |
| @Embedded | Các thuộc tính thành phần có thể được ánh xạ thành nhiều cột; kiểm tra path và SQL sinh ra |
| @ManyToOne | Association sở hữu FK có thể có giới hạn trong mutation; không coi nó là thao tác graph |
| @OneToMany | Collection không phải scalar property để gán bằng một bulk SET |
| @ManyToMany | Join table có vòng đời riêng; mutation entity không tự đồng bộ mọi association như object graph |
| @ElementCollection | Collection table không được sửa bằng cách gán một collection Java trong bulk update |
| @Formula | Thuộc tính dẫn xuất, thường không phải target ghi |
| insertable=false, updatable=false | Mapping đánh dấu cột không tham gia DML ORM thông thường; không giả định bulk HQL có thể ghi tùy ý |
| @Generated/database-generated | Giá trị do database sinh cần mapping và refresh/readback thích hợp |
| @SecondaryTable | Có thể yêu cầu multi-table mutation strategy |
| Inheritance | Có thể tác động nhiều bảng và cần xử lý polymorphic |

### 12.1. Không thể gán một collection bằng bulk SET

Một câu kiểu:

```hql
update Order o
set o.lines = :newLines
where o.id = :id
```

không phải cách cập nhật association collection bằng HQL bulk mutation. Collection có cấu trúc bảng riêng và semantics thêm/xóa phần tử. Hãy tải Order managed rồi thay đổi collection, hoặc viết các mutation riêng cho bảng liên quan bằng native SQL nếu thực sự cần thao tác theo tập hợp.

### 12.2. Embedded properties

```java
@Embeddable
public class Address {
    private String city;
    private String postalCode;
}

@Entity
public class Customer {
    @Id
    private Long id;

    @Embedded
    private Address address;
}
```

Các thuộc tính embedded được lưu trong bảng Customer theo mapping. Một số path scalar như c.address.city có thể được hỗ trợ trong mutation HQL tùy grammar/provider; cần kiểm tra phiên bản và SQL sinh ra. Nếu update nhiều cột hoặc mapping phức tạp, native SQL hoặc managed entity có thể dễ kiểm soát hơn.

### 12.3. Association không đồng nghĩa gán object graph

Nếu cần đổi Customer của nhiều Order, đừng giả định bulk HQL sẽ thực hiện cùng hành vi như gọi order.setCustomer(newCustomer) trên từng managed instance. Việc thay FK có thể có giới hạn theo HQL grammar, mapping và provider. Cần kiểm tra khả năng gán association-valued property trong phiên bản đang dùng; nếu không được hỗ trợ hoặc cần lifecycle đầy đủ, dùng managed entity hoặc native SQL có chủ đích.

## 13. Persistence context có thể stale sau bulk mutation

Đây là hệ quả quan trọng nhất cần xử lý trong ứng dụng.

Giả sử persistence context đã chứa Product:

```java
Product product = entityManager.find(Product.class, 10L);
System.out.println(product.getPrice()); // 100
```

Sau đó chạy bulk update:

```java
entityManager.createQuery("""
    update Product p
    set p.price = 120
    where p.id = 10
    """).executeUpdate();
```

Object product đang managed có thể vẫn giữ price = 100 trong memory. Bulk mutation cập nhật database trực tiếp; Hibernate không duyệt persistence context để sửa field của mọi instance đang tồn tại.

```text
Database:
  Product #10 price = 120

Persistence context:
  Product #10 price = 100  (stale managed state)
```

Nếu sau đó ứng dụng đọc product.getPrice(), nó có thể thấy giá trị cũ. Nếu sửa một field khác và flush, một số state cũ có thể tiếp tục ảnh hưởng tới SQL hoặc logic nghiệp vụ.

## 14. Flush trước, clear hoặc refresh sau

### 14.1. Flush trước mutation

Nếu persistence context đang có thay đổi pending, hãy flush trước bulk mutation để thứ tự database rõ ràng:

```java
entityManager.flush();

int affected = entityManager.createQuery("""
    update Product p
    set p.active = false
    where p.discontinued = true
    """)
    .executeUpdate();
```

Hibernate ở chế độ AUTO có thể tự flush trước một mutation query tùy query spaces/flush mode, nhưng gọi flush() tường minh giúp thể hiện rõ ý định và tránh phụ thuộc hành vi tự động khi code phức tạp.

### 14.2. Clear sau mutation

Nếu nhiều managed entities có thể bị ảnh hưởng:

```java
entityManager.flush();

int affected = entityManager.createQuery("""
    update Product p
    set p.active = false
    where p.discontinued = true
    """)
    .executeUpdate();

entityManager.clear();
```

clear() detach tất cả entity khỏi persistence context. Lần truy cập tiếp theo phải tải state mới trong persistence context phù hợp.

**Chú ý:** clear() cũng detach các entity không liên quan. Nếu có thay đổi pending chưa flush, chúng sẽ không còn được persistence context quản lý để ghi. Vì vậy hãy flush trước khi clear nếu muốn giữ các thay đổi đó.

### 14.3. Refresh entity cụ thể

Nếu chỉ một vài entity bị ảnh hưởng và vẫn cần tiếp tục dùng managed instance:

```java
entityManager.flush();
entityManager.createQuery("""
    update Product p
    set p.price = :price
    where p.id = :id
    """)
    .setParameter("price", new BigDecimal("120.00"))
    .setParameter("id", 10L)
    .executeUpdate();

entityManager.refresh(product);
```

refresh() nạp lại state từ database và ghi đè state hiện tại của entity. Dùng cẩn thận nếu object có thay đổi chưa flush vì refresh có thể làm mất các giá trị trong memory.

### 14.4. Chọn clear hay refresh

| Tình huống | Cách xử lý thường phù hợp |
|---|---|
| Bulk update tác động hàng nghìn entity | Flush rồi clear PC |
| Chỉ một entity cụ thể bị thay đổi | Refresh entity đó |
| Bulk mutation kết thúc một unit of work | Clear/đóng persistence context |
| Cần tiếp tục thao tác graph đang managed | Cân nhắc refresh các instance liên quan; tránh clear nếu không muốn detach toàn bộ |
| Có pending changes trước mutation | Flush trước khi clear/refresh |

## 15. Second-level cache và query cache

Bulk mutation không đồng bộ từng object trong first-level cache. Hibernate có thể dùng query-space/cache cleanup để vô hiệu hóa vùng cache liên quan đến entity/collection bị ảnh hưởng, nhưng chi tiết phụ thuộc Hibernate version, loại cache, mutation strategy và query.

Điều cần phân biệt:

- **First-level cache:** persistence context của Session/EntityManager; có thể giữ managed entity stale sau bulk mutation.
- **Second-level cache:** cache dùng chung giữa Session; Hibernate có cơ chế cleanup/invalidation cho các vùng bị ảnh hưởng theo mapping và strategy.
- **Query cache:** kết quả query đã cache; phụ thuộc query spaces và cơ chế invalidation.

Không dùng việc Hibernate dọn second-level/query cache để suy ra first-level state đã được cập nhật. Cần clear/refresh PC theo yêu cầu.

Với native SQL, Hibernate có thể không biết chính xác bảng/query spaces bị thay đổi nếu ứng dụng không khai báo synchronization phù hợp. Khi dùng native mutation cùng cache, cần khai báo synchronized query spaces hoặc evict cache region theo API/cấu hình thích hợp.

## 16. Bulk DML và entity lifecycle

Bulk mutation bỏ qua phần lớn quy trình xử lý từng entity:

| Cơ chế | persist()/managed update/remove | Bulk HQL |
|---|---|---|
| Tạo entity instance | Có | Không tải từng instance |
| Dirty checking | Có | Không |
| Domain setter/method | Có nếu ứng dụng gọi | Không tự gọi |
| @PrePersist/@PreUpdate/@PreRemove | Có theo lifecycle tương ứng | Không chạy cho từng entity |
| Cascade JPA | Theo mapping và thao tác | Không chạy như thao tác entity-by-entity |
| Orphan removal | Theo lifecycle collection | Không tự thực hiện như thay đổi collection |
| Bean Validation lifecycle | Có theo cấu hình/provider | Không chạy trên từng object |
| DB constraint/trigger | Có | Có |
| SQL audit trigger | Có thể chạy | Có thể chạy |

Vì vậy, nếu ứng dụng dựa vào @PreUpdate để tự cập nhật updatedAt, bulk update sẽ không tự gọi callback đó cho từng row. Hãy đưa updatedAt vào SET:

```hql
update Product p
set p.active = false,
    p.updatedAt = :now
where p.discontinued = true
```

Nếu audit cần ghi một row cho mỗi entity, có thể dùng insert-select vào bảng audit (nếu schema và dữ liệu đủ) hoặc dùng database trigger. Nếu audit phụ thuộc logic Java/domain phức tạp, dùng managed entities hoặc một workflow riêng.

## 17. Bulk mutation và optimistic/pessimistic concurrency

Bulk HQL vẫn chạy trong database transaction nên database isolation, row locks và constraints vẫn có hiệu lực. Tuy nhiên, nó không tự áp dụng tất cả concurrency semantics của entity lifecycle.

### 17.1. Không có version check mặc định như managed update

Nếu một client đọc Product ở version 5 rồi gửi command sửa giá, managed update có thể phát hiện version đã đổi. Bulk update không tự biết client đang giữ version nào nếu WHERE không có điều kiện version.

Ví dụ compare-and-set:

```hql
update Product p
set p.price = :newPrice,
    p.version = p.version + 1
where p.id = :id
  and p.version = :expectedVersion
```

Nếu executeUpdate() trả 0, dữ liệu đã đổi hoặc ID không tồn tại. Đây là cơ chế cập nhật có điều kiện rõ ràng.

### 17.2. Conditional update có thể tốt hơn read-then-write

Thay vì:

1. SELECT tồn kho.
2. Java kiểm tra đủ hàng.
3. UPDATE giảm tồn kho.

có thể dùng:

```hql
update InventoryItem i
set i.available = i.available - :quantity
where i.id = :id
  and i.available >= :quantity
```

Database đánh giá điều kiện và cập nhật trong một statement. Tuy nhiên, vẫn cần đảm bảo quantity > 0, transaction, versioning nếu cần và xử lý trường hợp affected count bằng 0.

### 17.3. Pessimistic lock không tự cần thiết cho mọi bulk update

Một conditional UPDATE đơn giản có thể đã nguyên tử theo database semantics. Khóa trước bằng SELECT FOR UPDATE rồi mới update có thể tăng thời gian giữ lock mà không mang lại lợi ích nếu điều kiện và thay đổi đã nằm trong cùng statement. Ngược lại, nếu nghiệp vụ cần kiểm tra nhiều bảng/state trước khi ghi, transaction có thể cần khóa hoặc isolation phù hợp.

Chọn cơ chế theo invariant và SQL thực tế.

## 18. Ví dụ hoàn chỉnh: archive đơn hàng cũ

Giả sử Order có trạng thái, ngày tạo và cờ archived:

```java
@Entity
public class Order {
    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    private Instant createdAt;
    private boolean archived;
    private Instant archivedAt;
}
```

Service Spring:

```java
@Service
public class OrderMaintenanceService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public int archiveOldCompletedOrders(Instant cutoff, Instant now) {
        em.flush();

        int affected = em.createQuery("""
            update Order o
            set o.archived = true,
                o.archivedAt = :now
            where o.status = :completed
              and o.createdAt < :cutoff
              and o.archived = false
            """)
            .setParameter("now", now)
            .setParameter("completed", OrderStatus.COMPLETED)
            .setParameter("cutoff", cutoff)
            .executeUpdate();

        em.clear();
        return affected;
    }
}
```

Method này:

1. Flush các thay đổi pending trước mutation.
2. Cập nhật tất cả Order phù hợp trong một bulk operation.
3. Clear persistence context để không giữ các Order stale.
4. Trả số entity instance bị ảnh hưởng.

Nếu archivedAt phải được ghi bởi entity listener hoặc cần phát event cho từng Order, bulk update đơn giản này chưa đủ. Cần bổ sung cơ chế audit/outbox phù hợp.

## 19. Ví dụ: xóa review cũ theo trạng thái sách

```java
@Transactional
public int deleteReviewsForArchivedBooks(Instant cutoff) {
    entityManager.flush();

    int deleted = entityManager.createQuery("""
        delete from Review r
        where r.createdAt < :cutoff
          and exists (
              select 1
              from Book b
              where b = r.book
                and b.archived = true
          )
        """)
        .setParameter("cutoff", cutoff)
        .executeUpdate();

    entityManager.clear();
    return deleted;
}
```

Điều kiện liên quan đến Book được đặt trong correlated subquery. Trước khi chạy, cần xác nhận không có quy tắc nghiệp vụ yêu cầu callback, audit per Review hoặc cascade xử lý từng entity. Cũng cần kiểm tra FK và mapping collection liên quan để tránh lỗi khi xóa.

## 20. Ví dụ: insert-select để tạo snapshot

```java
@Transactional
public int createSnapshots(OrderStatus status) {
    entityManager.flush();

    int inserted = entityManager.createQuery("""
        insert into OrderSnapshot
            (id, orderNumber, total, status)
        select
            o.id, o.orderNumber, o.total, o.status
        from Order o
        where o.status = :status
        """)
        .setParameter("status", status)
        .executeUpdate();

    entityManager.clear();
    return inserted;
}
```

Đây là HQL insert-select của Hibernate, không phải JPQL portable. Entity OrderSnapshot cần mapping/identifier tương thích với các giá trị được select. Nếu một snapshot cho mỗi Order đã tồn tại, primary key/unique constraint sẽ quyết định insert thất bại; muốn chạy lặp lại an toàn cần định nghĩa chiến lược chống trùng rõ ràng.

## 21. Bulk update/delete trong Spring Data JPA

Spring Data JPA hỗ trợ mutation query qua @Modifying:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true)
    @Query("""
        update Product p
        set p.active = false
        where p.discontinued = true
        """)
    int deactivateDiscontinued();
}
```

Phương thức nên được gọi trong transaction phù hợp, ví dụ từ service:

```java
@Service
public class ProductMaintenanceService {
    private final ProductRepository products;

    public ProductMaintenanceService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public int deactivate() {
        return products.deactivateDiscontinued();
    }
}
```

Ý nghĩa các thuộc tính:

- flushAutomatically = true: flush persistence context trước khi chạy query.
- clearAutomatically = true: clear persistence context sau khi chạy query.

clearAutomatically có thể detach mọi entity đang managed trong persistence context của transaction, không chỉ Product. Cần cân nhắc khi service còn dùng các entity khác sau repository call.

### 21.1. HQL extension trong @Query

@Query của Spring Data JPA thường được phân tích theo JPQL, nhưng khi provider là Hibernate có thể dùng một số HQL extension. Ví dụ update versioned không portable. Hãy xác nhận parser/provider của phiên bản Spring Data/Hibernate đang chạy và cân nhắc dùng Hibernate Session khi cần HQL-specific mutation rõ ràng.

## 22. Bulk mutation với inheritance và secondary tables

Một câu lệnh HQL có thể nhắm tới một entity nhưng mapping entity đó có nhiều bảng. Hibernate phải triển khai mutation sao cho phù hợp schema:

```text
Entity Payment
   ├── payments (id, amount, version)
   └── card_payments (payment_id, last_four_digits)

HQL:
  update Payment p set p.amount = 0 where ...

Mutation strategy có thể:
  1. Xác định tập ID cần cập nhật.
  2. Cập nhật bảng chứa amount.
  3. Xử lý bảng liên quan nếu mapping yêu cầu.
```

Với JOINED, update thuộc tính nằm ở bảng root có thể chỉ tác động bảng root, còn delete một entity subtype có thể cần xóa nhiều bảng theo thứ tự phù hợp với FK. Với TABLE_PER_CLASS, một query polymorphic có thể cần thao tác trên nhiều bảng subclass.

Hibernate có nhiều mutation strategy theo dialect và cấu hình. Do đó:

- Kiểm tra SQL thực tế khi entity dùng inheritance/secondary table.
- Kiểm tra hỗ trợ temporary table/CTE của database.
- Kiểm tra quyền tạo hoặc sử dụng bảng tạm nếu chiến lược yêu cầu.
- Đo số statement và chi phí khi tập ID rất lớn.
- Không suy ra executeUpdate() bằng tổng row bị thay đổi ở mọi bảng.

## 23. Bulk mutation không phải công cụ cập nhật graph

Hãy phân biệt:

| Nhu cầu | Cách thường phù hợp |
|---|---|
| Đổi một field trên hàng nghìn Product theo điều kiện | Bulk HQL update |
| Xóa hàng nghìn token hết hạn, không cần callback entity | Bulk HQL delete |
| Tạo bảng snapshot từ dữ liệu hiện có | HQL insert-select hoặc native SQL |
| Cập nhật một Order và gọi domain method | Load entity, gọi method, dirty checking |
| Xóa Order và cascade remove theo JPA | remove() trên managed entity |
| Thay đổi collection và áp dụng orphan removal | Sửa collection của managed entity |
| Chạy validation Java và phát domain event cho từng entity | Managed entity/workflow riêng |
| Dùng CTE/window function/database-specific feature | Native SQL |

Bulk DML là công cụ làm việc với **tập row**, còn persistence context là cơ chế quản lý **entity instance**. Hai tầng có semantics khác nhau.

## 24. Những vấn đề về filter, tenant và soft-delete

Nếu ứng dụng dùng Hibernate filters, tenant discriminator, soft-delete hoặc query restriction, phải kiểm tra xem mutation query có thực sự áp dụng đúng điều kiện đó hay không.

Không giả định:

- Một filter được bật cho SELECT sẽ luôn tự động áp dụng cho mọi bulk mutation theo cùng cách.
- Mọi custom SQL delete của entity sẽ được dùng khi chạy HQL bulk delete.
- Mọi quy tắc tenant trong Java service tự động xuất hiện trong HQL.
- Một soft-delete annotation tự chuyển mọi bulk delete thành update cờ.

Với dữ liệu tenant, hãy đưa điều kiện tenant vào query một cách rõ ràng hoặc dùng cơ chế provider/database đã được kiểm chứng. Ví dụ:

```hql
update Invoice i
set i.status = :expired
where i.tenantId = :tenantId
  and i.dueAt < :now
```

Nếu tenant ID được lấy từ security context, cần bind giá trị đáng tin cậy từ server-side context, không lấy tùy tiện từ request body.

Với soft delete, ưu tiên câu update tường minh:

```hql
update Invoice i
set i.deleted = true,
    i.deletedAt = :now
where i.id = :id
  and i.tenantId = :tenantId
  and i.deleted = false
```

Điều này làm rõ điều kiện và tác động dữ liệu của câu mutation.

## 25. Audit và domain event khi dùng bulk DML

Bulk update không gọi @PostUpdate trên từng entity. Nếu hệ thống dựa vào callback để ghi audit hoặc publish event, bulk mutation có thể bỏ qua các side effect đó.

Các lựa chọn:

1. **Đưa dữ liệu audit vào cùng transaction:** dùng insert-select để ghi một audit row cho mỗi bản ghi bị ảnh hưởng, nếu schema cho phép.
2. **Database trigger:** thích hợp khi audit phải áp dụng cho mọi writer, kể cả SQL ngoài Hibernate.
3. **Managed entity loop:** dùng khi cần domain method, callback, validation và event per entity.
4. **Transactional outbox:** nếu cần publish sự kiện sau khi database commit, ghi outbox trong cùng transaction rồi relay.

Không gửi hàng nghìn message trực tiếp từ một callback giả định của bulk DML. Nếu event là một phần của invariant, cần thiết kế cơ chế bền vững và idempotent.

## 26. Batch persist so với insert-select

Insert-select không phải lựa chọn duy nhất để insert nhiều entity.

| Tiêu chí | HQL insert-select | Batch persist |
|---|---|---|
| Nguồn dữ liệu | Query/database | Object Java |
| Entity lifecycle | Không chạy như persist từng entity | Có |
| Cascade persist | Không tự chạy | Có theo mapping |
| Callback/validation | Không chạy per entity | Có theo lifecycle/config |
| Lượng object trong memory | Thấp | Có thể lớn nếu không flush/clear theo batch |
| ID generation | Phụ thuộc hỗ trợ bulk insert | Theo generator/entity lifecycle |
| Dữ liệu nguồn ở cùng DB | Rất phù hợp | Có thể phải đọc và truyền qua ứng dụng |
| Logic Java cho từng row | Không | Có |

Nếu cần batch persist:

```java
int batchSize = 50;
int count = 0;

for (SourceRow row : rows) {
    entityManager.persist(mapToEntity(row));

    if (++count % batchSize == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}

entityManager.flush();
entityManager.clear();
```

Batch persist giữ lifecycle entity nhưng cần quản lý persistence context và JDBC batching đúng. Với insert-select, database có thể làm công việc trong một statement, nhưng mất những callback/domain behavior của từng entity.

## 27. Hiệu năng và transaction size

Bulk mutation giảm số round trips và object allocation, nhưng có thể tác động lớn tới database:

- Cập nhật nhiều index entries.
- Giữ row/table locks trong transaction.
- Tạo WAL/redo log lớn.
- Gây replication lag.
- Làm transaction dài và tăng lock contention.
- Kích hoạt trigger/constraint cho nhiều hàng.
- Tốn tài nguyên cho temporary table/multi-table mutation strategy.

Không có nghĩa một câu SQL lớn luôn nhanh hơn mọi batch. Nếu tập dữ liệu rất lớn hoặc cần giới hạn thời gian khóa, có thể chia theo key range/chunk:

```text
Transaction 1: IDs 1 - 10,000       → commit
Transaction 2: IDs 10,001 - 20,000 → commit
Transaction 3: IDs 20,001 - 30,000 → commit
...
```

Chia chunk thay đổi semantics atomicity: toàn bộ tác vụ không còn là một transaction duy nhất. Cần checkpoint, retry, idempotency và cách xử lý partial completion. Dùng điều kiện/keyset ổn định để tránh bỏ sót hoặc xử lý trùng khi dữ liệu thay đổi.

## 28. Kiểm tra số lượng bị ảnh hưởng

executeUpdate() trả về số entity instance bị ảnh hưởng. Ví dụ:

```java
int affected = query.executeUpdate();

if (affected == 0) {
    // Không có entity nào thỏa điều kiện.
}
```

Không diễn giải số này quá mức:

- 0 có thể nghĩa là không có entity phù hợp, hoặc điều kiện không làm thay đổi dữ liệu tùy semantics/database/provider.
- Với entity nhiều bảng, count không phải tổng physical row count.
- Với inheritance, count theo entity instance bị ảnh hưởng.
- Với insert-select, count biểu thị số entity/row được insert theo cách Hibernate báo cáo.

Nếu nghiệp vụ cần phân biệt “không tồn tại ID” với “đã tồn tại nhưng không đủ điều kiện”, cần query hoặc thiết kế kết quả riêng. Một con số affected không phải lúc nào cũng đủ để phân loại lỗi nghiệp vụ.

## 29. Native SQL khi HQL không đủ

HQL phù hợp khi mutation diễn đạt được bằng entity model. Native SQL phù hợp khi cần:

- CTE/recursive query đặc thù database.
- Window function hoặc UPDATE ... FROM.
- INSERT ... ON CONFLICT/upsert.
- Database-specific hints.
- Multi-table statement đặc biệt.
- Tính năng không được HQL grammar/provider hỗ trợ.

Ví dụ PostgreSQL upsert:

```sql
INSERT INTO daily_totals (business_date, total)
VALUES (:date, :total)
ON CONFLICT (business_date)
DO UPDATE SET total = EXCLUDED.total;
```

Đây là cú pháp PostgreSQL, không phải HQL portable. Khi dùng native mutation:

- Bind parameters, không nối chuỗi từ user input.
- Xác định transaction boundary.
- Đồng bộ persistence context sau mutation.
- Khai báo synchronized query spaces nếu cần Hibernate cache/query synchronization.
- Kiểm tra cache invalidation và row count.
- Kiểm tra schema/database version cụ thể.

## 30. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| TransactionRequiredException | Mutation chạy ngoài transaction | Mở hoặc tham gia transaction phù hợp |
| HQL insert không compile | Dùng cú pháp VALUES như SQL hoặc insert grammar không đúng | Dùng insert into ... select theo HQL |
| Insert-select sai kiểu | Số lượng/thứ tự/kiểu biểu thức không tương thích | Đối chiếu property list với select list |
| ID duplicate khi insert snapshot | Dùng lại identifier đã tồn tại | Chọn assigned ID/sequence hoặc chống trùng phù hợp |
| ID generation không hoạt động | Generator không hỗ trợ bulk insert theo dialect/version | Kiểm tra generator hoặc dùng batch persist/native SQL |
| Bulk update không tăng version | Không dùng update versioned/không tự tăng version | Chọn version semantics rõ ràng |
| Entity trong memory vẫn có giá trị cũ | Persistence context không được đồng bộ | Flush rồi clear/refresh |
| clear() làm mất thay đổi chưa ghi | Clear trước flush | Flush trước clear |
| Callback không chạy | Bulk DML bỏ qua lifecycle entity | Dùng managed entity hoặc audit/trigger/outbox |
| Cascade remove không chạy | Bulk delete không chạy cascade JPA như remove() | Xóa graph qua lifecycle hoặc dùng DB cascade có chủ đích |
| FK constraint lỗi khi delete | Còn row con phụ thuộc | Xóa child theo thứ tự hoặc thiết kế FK cascade |
| HQL update có join không chạy | Bulk update có giới hạn join | Dùng subquery trong WHERE hoặc native SQL |
| Update entity inheritance chậm | Mapping nhiều bảng/mutation strategy | Kiểm tra SQL, temp tables/CTE và dialect |
| executeUpdate() count gây hiểu nhầm | Count entity instance khác physical rows | Đo row count bằng SQL nếu cần |
| Soft delete bị xóa vật lý | Bulk delete không dùng semantics custom như kỳ vọng | Dùng bulk update cờ deleted rõ ràng |
| Filter/tenant không áp dụng như mong đợi | Mutation không kế thừa mọi SELECT filter | Đưa điều kiện tenant vào query và kiểm thử |
| Query cache trả dữ liệu cũ | Cache/query spaces chưa được đồng bộ | Xác nhận cleanup; khai báo query spaces/evict khi dùng native SQL |
| Bulk update bỏ qua validation Java | Không gọi setter/domain method | Kiểm tra điều kiện trong query/DB constraint hoặc dùng entity loop |

## 31. Quy trình thực hiện bulk mutation an toàn

Trước khi viết câu mutation, xác định rõ:

**1. Phạm vi dữ liệu.** Entity nào và điều kiện nào được phép thay đổi? Có cần tenant, soft-delete, status hoặc authorization predicate không?

**2. Mapping vật lý.** Entity có inheritance, secondary table, embedded, collection table hoặc association nào ảnh hưởng tới SQL không?

**3. Lifecycle cần thiết.** Có cần cascade, orphan removal, callbacks, validation, domain events hoặc audit per entity không? Nếu có, bulk DML có thể không phù hợp.

**4. Concurrency.** Có cần @Version, update versioned, compare-and-set, pessimistic lock hay constraint không?

**5. Transaction.** Mutation chạy trong transaction nào? Có flush pending changes trước khi chạy không?

**6. Persistence context.** Entity nào đang managed có thể stale? Sau mutation cần clear hay refresh?

**7. Cache.** Có second-level/query cache hoặc native SQL cần khai báo query spaces không?

**8. Khối lượng.** Một statement đủ tốt hay cần chunk? Chia chunk có làm thay đổi atomicity không?

**9. Kết quả.** executeUpdate() count có đủ để xử lý nghiệp vụ không?

**10. Kiểm thử.** Chạy trên database engine thực tế, kiểm tra SQL, row count, FK, cache và behavior khi lỗi.

## 32. Bảng quyết định: HQL bulk hay managed entities?

| Yêu cầu | Nên cân nhắc |
|---|---|
| Cập nhật một giá trị cho hàng nghìn row theo điều kiện đơn giản | HQL bulk update |
| Xóa bản ghi hết hạn không có lifecycle side effects | HQL bulk delete |
| Tạo snapshot/copy dữ liệu trong cùng database | HQL insert-select |
| Cần cascade, orphan removal hoặc entity callbacks | Managed entities |
| Cần gọi domain method/validation cho từng instance | Managed entities |
| Cần phát domain event riêng cho từng entity | Managed entities hoặc quy trình outbox/audit được thiết kế riêng |
| Cần thao tác SQL-specific như upsert/CTE | Native SQL |
| Entity hierarchy nhiều bảng | HQL nếu mutation strategy phù hợp, sau khi kiểm tra SQL; nếu không native SQL |
| Cần cập nhật collection graph | Managed entities hoặc mutation riêng cho bảng quan hệ |
| Cần cập nhật có điều kiện nguyên tử một row | Conditional bulk update/compare-and-set |

## 33. Sơ đồ lựa chọn

```text
                  Cần thay đổi nhiều dữ liệu?
                              │
                    Cần lifecycle từng entity?
                         ┌────┴────┐
                        CÓ        KHÔNG
                         │          │
                         ▼          ▼
                 Load managed    Mutation theo tập
                 entities            │
                 persist/update/     ▼
                 remove           HQL phù hợp?
                                      │
                                ┌─────┴─────┐
                               CÓ         KHÔNG
                                │           │
                                ▼           ▼
                         HQL insert/    Native SQL /
                         update/delete  batch workflow
                                │
                                ▼
                        Transaction rõ ràng
                                │
                                ▼
                         Flush pending state
                                │
                                ▼
                         Execute mutation
                                │
                                ▼
                       Clear/refresh persistence
                       context và kiểm tra cache
                                │
                                ▼
                         Commit và xử lý count
```

## 34. Những nguyên tắc cần nhớ

HQL bulk mutation cho phép database thực hiện insert-select, update và delete theo điều kiện trên entity model. Nó giảm việc tạo object và round trips khi cần thay đổi một tập lớn dữ liệu. HQL insert là insert-select và không thuộc bulk DML chuẩn của JPQL; JPQL chuẩn có bulk update/delete.

Bulk update không tự thực hiện dirty checking hay optimistic version check giống một entity managed. Hibernate có HQL extension update versioned để tăng version/timestamp; compare-and-set cũng có thể được biểu diễn bằng version trong WHERE và SET. Bulk delete không chạy cascade remove, orphan removal hay callback entity như remove() trên từng object. Insert-select không cascade persist toàn bộ graph.

Mapping giới hạn những thuộc tính có thể ghi. Inheritance và secondary tables có thể làm một mutation HQL sinh nhiều SQL statement. Số lượng từ executeUpdate() là số entity instance theo semantics Hibernate, không nhất thiết là tổng số physical rows.

Sau mutation, persistence context có thể chứa entity state cũ. Hãy flush trước khi chạy nếu có pending changes, rồi clear hoặc refresh theo phạm vi ảnh hưởng. Kiểm tra cache, transaction, tenant/soft-delete predicates và database constraints.

**Hãy dùng bulk HQL cho thay đổi theo tập hợp khi không cần lifecycle của từng entity.** Khi nghiệp vụ cần domain method, validation, cascade hoặc event cho từng object, dùng managed entity workflow. Khi cần tính năng SQL đặc thù, dùng native SQL với transaction và cache synchronization được kiểm soát.
