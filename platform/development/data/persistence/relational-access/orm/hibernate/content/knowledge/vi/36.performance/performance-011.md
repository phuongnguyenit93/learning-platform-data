# Chọn truy vấn hàng loạt hoặc JDBC khi vòng đời thực thể không cần thiết

Hibernate ORM cung cấp nhiều hành vi hữu ích quanh entity: ánh xạ quan hệ, persistence context, dirty checking, callbacks, cascades, optimistic locking, Bean Validation và tích hợp audit. Nhưng mỗi hành vi đều có chi phí xử lý. Khi một use case chỉ cần thay đổi một tập rows theo cùng một quy tắc, hoặc ghi một lượng lớn dữ liệu đã được chuẩn hóa, việc tải từng entity lên Java rồi sửa từng object có thể tạo ra nhiều công việc không cần thiết.

Trong những trường hợp đó, **bulk HQL/JPQL hoặc JDBC có thể phù hợp hơn**, miễn là nghiệp vụ không phụ thuộc vào các hành vi entity lifecycle mà những đường này bỏ qua.

Ví dụ kho hàng cần trừ 5 đơn vị cho một SKU. Thay vì tải từng Inventory entity, gọi domain method và để Hibernate dirty-check, database có thể thực hiện phép toán trực tiếp:

~~~sql
update inventory
set quantity = quantity - :amount
where tenant_id = :tenantId
  and sku = :sku
  and quantity >= :amount;
~~~

Cách này tránh materialize từng entity và giảm round trips. Đổi lại, nó không gọi domain method trên từng object, không tự chạy per-entity callbacks, cascades, Bean Validation hoặc Envers events. Nếu những hành vi ấy là một phần của nghiệp vụ, cần giữ đường managed entity hoặc thiết kế cơ chế thay thế có chủ đích.

Bài học thuộc chương **Hiệu năng** của module *Data Persistence Relational Access ORM Hibernate*. Nội dung tập trung vào lựa chọn giữa entity lifecycle, bulk HQL/JPQL và JDBC; phân biệt set-based DML với JDBC batching; kiểm soát Persistence Context, versioning, transaction, tenant scope, lỗi và đo hiệu năng. Các ví dụ dùng Hibernate ORM 6.x, Jakarta Persistence và Spring JDBC.

## 1. Vì sao entity lifecycle có chi phí?

Một entity managed không chỉ là object Java. Hibernate theo dõi trạng thái của nó trong Persistence Context và phối hợp các cơ chế duy trì mapping semantics.

Quy trình khái quát khi ứng dụng tải và sửa nhiều entities:

~~~mermaid
flowchart TD
    A["SELECT entity rows"] --> B["Hydrate Java objects"]
    B --> C["Register in Persistence Context"]
    C --> D["Application changes entities"]
    D --> E["Dirty checking"]
    E --> F["Build entity actions"]
    F --> G["Callbacks / cascades / listeners"]
    G --> H["Generate SQL statements"]
    H --> I["JDBC execute / batching"]
    I --> J["Database commit"]
~~~

Các công việc này cần thiết khi ứng dụng yêu cầu entity semantics, nhưng có thể không cần thiết khi:

- Nhiều rows được thay đổi bằng cùng một phép toán.
- Một tập dữ liệu import đã được validate và transform ở pipeline khác.
- Một bảng staging đã chứa dữ liệu chuẩn bị để merge vào bảng đích.
- Một báo cáo chỉ cần projection hoặc aggregate, không cần entity graph.
- Một job xóa records theo retention rule đơn giản.
- Một batch cập nhật nhiều records với giá trị riêng nhưng không cần domain method của từng entity.

### 1.1. Chi phí của managed entities

Với N rows, đường entity-by-entity có thể phát sinh:

- Materialize N entities và các associations được truy cập.
- Lưu N snapshots/state entries trong Persistence Context.
- Dirty checking và action scheduling.
- N hoặc nhiều SQL statements.
- Callback, validation và audit work theo entity.
- Tăng bộ nhớ của L1 cache.
- Transaction và locks tồn tại lâu hơn nếu batch quá lớn.

Hibernate có nhiều tối ưu và JDBC batching có thể giảm round trips, nhưng ORM vẫn duy trì semantics cho từng entity.

### 1.2. Chi phí không có nghĩa luôn là vấn đề

Không bỏ entity lifecycle chỉ vì bulk query ngắn hơn. Nếu mỗi Order cần kiểm tra invariant riêng, ghi Envers revision, cập nhật association có cascade hoặc phát domain event, đó là một phần của yêu cầu nghiệp vụ.

**Chọn đường ghi theo semantics trước, rồi tối ưu trong phạm vi semantics ấy.**

## 2. Phân biệt ba cách xử lý nhiều rows

Từ “batch” và “bulk” thường bị dùng lẫn nhau. Có ba cách chính:

| Cách làm | Ý nghĩa | Database nhận gì? |
| --- | --- | --- |
| Managed entity operations | Tạo/tải entity, sửa object và flush | ORM-generated DML theo entity actions |
| Set-based bulk query | Một JPQL/HQL/SQL mutation áp dụng cho cả tập rows | Một hoặc một số SQL mutation statements |
| JDBC batching | Chuẩn bị statement rồi thực thi với nhiều bộ parameters | Nhiều executions được driver gom batch |

### 2.1. Set-based UPDATE

Ví dụ tăng giá 5% cho mọi sản phẩm trong một category:

~~~sql
update products
set price = price * 1.05
where category_id = :categoryId;
~~~

Database có thể thực hiện phép toán trên rows phù hợp mà không cần Java tải từng Product.

### 2.2. JDBC batch với values khác nhau

Một file import có thể chứa:

~~~text
Product 101 -> 12.50
Product 102 -> 15.00
Product 103 -> 11.75
...
~~~

Có thể chuẩn bị một câu UPDATE:

~~~sql
update products
set price = ?
where tenant_id = ?
  and id = ?;
~~~

rồi thực thi với nhiều parameter sets. Đây là nhiều executions của cùng prepared statement được driver gom lại; nó khác một câu set-based UPDATE dùng cùng biểu thức cho mọi rows.

### 2.3. Hibernate JDBC batching

Ngay cả khi cần managed entities, Hibernate cũng có thể batch những SQL statements tương thích. Đây là bước tối ưu nên cân nhắc trước khi bỏ entity lifecycle.

## 3. Khi nào cần giữ managed entity lifecycle?

Chọn entity operations khi use case phụ thuộc vào hành vi gắn với entity.

### 3.1. Domain invariants qua domain method

~~~java
public class Inventory {

    private int available;

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive"
            );
        }

        if (available < quantity) {
            throw new InsufficientInventoryException();
        }

        available -= quantity;
    }
}
~~~

Nếu reservation có logic phức tạp, domain method là nơi bảo vệ invariant. Một bulk SQL chỉ trừ số lượng không tự chạy những bước nghiệp vụ khác.

Có thể chuyển invariant xuống SQL khi biểu diễn được bằng một điều kiện atomic. Ví dụ predicate `available >= :quantity` trong UPDATE giúp ngăn số lượng âm, nhưng không tự xử lý các quy tắc khác như phê duyệt, quota, event hoặc authorization.

### 3.2. Entity callbacks và listeners

`@PrePersist`, `@PreUpdate`, `@PostRemove` hoặc custom listeners có thể là một phần của behavior. Bulk DML không gọi các callbacks này cho từng affected entity như managed lifecycle.

Nếu callback chỉ gán timestamp, có thể thay bằng DB default, trigger hoặc biểu thức SQL. Nếu callback kiểm tra invariant hay tạo audit event, cần một cơ chế tương đương được thiết kế rõ.

### 3.3. Cascades và orphan removal

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
~~~

Khi thao tác entity/association theo JPA lifecycle, cascade và orphan removal có thể phát sinh child operations. Bulk DELETE parent không tương đương gọi `entityManager.remove(order)` cho từng parent; DB FK cascade có semantics riêng.

### 3.4. Bean Validation và Envers

- Jakarta Bean Validation lifecycle có thể kiểm tra entities khi persist/update theo group cấu hình.
- Envers ghi lịch sử qua entity events mà nó nhận được.
- Bulk HQL/JPQL và JDBC không tự chạy các hành vi per-entity đó.

Nếu compliance yêu cầu history từng entity, không chuyển sang bulk DML rồi giả định Envers vẫn ghi đầy đủ.

### 3.5. Optimistic locking

Managed update thường dùng `@Version` để phát hiện một số concurrent modifications. Bulk DML không tự chạy optimistic version check cho từng managed entity như đường ORM thông thường. Nếu version check là bắt buộc, phải thiết kế explicit version predicate/increment hoặc giữ managed updates.

## 4. Khi nào bulk HQL/JPQL là lựa chọn tốt?

Bulk query phù hợp khi nhiều rows được thay đổi theo một biểu thức set-based, logic đồng nhất và không cần per-entity lifecycle.

Ví dụ:

- Đánh dấu hết hạn các sessions theo timestamp.
- Chuyển trạng thái invoices đã quá hạn.
- Tăng/giảm numeric field theo một factor.
- Cập nhật cờ xử lý theo predicate.
- Xóa records theo retention policy.
- Sửa dữ liệu kỹ thuật có quy tắc đồng nhất.

### 4.1. Bulk UPDATE bằng JPQL

Giả sử Inventory có tenantId, SKU và quantity:

~~~java
@Transactional
public int decrementStock(
        String tenantId,
        String sku,
        int amount
) {
    if (amount <= 0) {
        throw new IllegalArgumentException(
                "amount must be positive"
        );
    }

    int changed = entityManager.createQuery(
            """
            update Inventory i
            set i.quantity = i.quantity - :amount
            where i.tenantId = :tenantId
              and i.sku = :sku
              and i.quantity >= :amount
            """
        )
        .setParameter("amount", amount)
        .setParameter("tenantId", tenantId)
        .setParameter("sku", sku)
        .executeUpdate();

    if (changed != 1) {
        throw new InsufficientInventoryException();
    }

    return changed;
}
~~~

Ví dụ giả định mỗi tenant chỉ có một Inventory row cho SKU ấy. Nếu SKU có nhiều locations, điều kiện phải bổ sung location hoặc dùng một phép tổng hợp theo đúng nghiệp vụ. Tenant ID phải lấy từ trusted context, không lấy raw từ client.

### 4.2. Gộp kiểm tra và cập nhật trong một statement

Một cách ngây thơ là SELECT quantity, kiểm tra trong Java, rồi UPDATE. Giữa hai câu lệnh, transaction khác có thể thay quantity. Bulk UPDATE chứa cả predicate `quantity >= :amount` và phép trừ giúp database đánh giá điều kiện trên row state tại thời điểm thực thi.

Với invariants phức tạp hơn hoặc nhiều rows, cần cân nhắc transaction isolation, locking và constraints tương ứng.

### 4.3. Affected row count là một phần của nghiệp vụ

`executeUpdate()` trả số lượng entities/rows bị ảnh hưởng theo semantics provider.

- 1: một row phù hợp và được cập nhật.
- 0: không có row phù hợp, có thể do SKU không tồn tại, tenant không sở hữu SKU hoặc quantity không đủ.
- Lớn hơn 1: có thể cho thấy uniqueness/invariant bị vi phạm nếu thiết kế mong đợi một row.

Không trả thông báo phân biệt “SKU tồn tại ở tenant beta” cho người dùng alpha nếu điều đó tiết lộ dữ liệu ngoài phạm vi.

## 5. Bulk DELETE bằng JPQL

Ví dụ xóa expired tokens:

~~~java
@Transactional
public int deleteExpiredTokens(Instant now) {
    return entityManager.createQuery(
            """
            delete from ApiToken t
            where t.expiresAt < :now
            """
        )
        .setParameter("now", now)
        .executeUpdate();
}
~~~

Phù hợp khi mỗi row có thể xóa trực tiếp theo predicate và không cần per-token callback/domain transition.

### 5.1. Bulk delete không gọi entity remove lifecycle

Bulk delete không tải từng ApiToken rồi gọi `entityManager.remove(token)`. Cần xem xét:

- `@PreRemove` và `@PostRemove`.
- Envers deletion revisions.
- JPA `CascadeType.REMOVE`.
- `orphanRemoval`.
- Application cleanup của files/messages/caches.
- FK constraints và database cascade.
- Audit retention.

Nếu token removal phải thu hồi credential ở hệ thống khác hoặc ghi audit event, bulk DELETE có thể không đáp ứng. Có thể dùng DB cascade, trigger hoặc outbox, nhưng cần transaction semantics rõ ràng.

### 5.2. Retention jobs

Nếu dữ liệu đã hết hạn, không còn references hợp lệ, audit được ghi ở một hệ thống khác và DB constraints bảo vệ quan hệ, bulk delete có thể tiết kiệm nhiều round trips. Trước khi xóa cần xác định retention, backup và khả năng phục hồi.

## 6. HQL bulk mutation và CriteriaUpdate/CriteriaDelete

~~~java
int changed = entityManager.createQuery(
        """
        update Product p
        set p.status = :next
        where p.status = :previous
          and p.discontinuedAt < :cutoff
        """
    )
    .setParameter("next", ProductStatus.ARCHIVED)
    .setParameter("previous", ProductStatus.ACTIVE)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
~~~

Criteria API phù hợp khi predicate được xây động:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaUpdate<Product> update =
        cb.createCriteriaUpdate(Product.class);

Root<Product> product = update.from(Product.class);

update.set("status", ProductStatus.ARCHIVED);
update.where(
    cb.equal(product.get("status"), ProductStatus.ACTIVE),
    cb.lessThan(product.get("discontinuedAt"), cutoff)
);

int changed = entityManager.createQuery(update).executeUpdate();
~~~

Criteria API hỗ trợ dựng query có kiểu, nhưng **không đổi lifecycle semantics**: đây vẫn là bulk DML, không phải vòng lặp managed entity updates.

### 6.1. Inheritance mapping

Một entity hierarchy có thể map thành nhiều tables. Bulk mutation trên entity type có thể cần nhiều SQL statements hoặc chiến lược mutation provider-specific. Vì vậy không phải mọi HQL bulk query đều là một SQL UPDATE đơn giản. Kiểm tra SQL thực tế và execution plan với mapping/Dialect đang dùng.

### 6.2. JPQL và HQL extensions

JPQL thuộc Jakarta Persistence; HQL có thêm cú pháp riêng của Hibernate. Extension như `update versioned` không portable như JPQL. Ghi rõ provider dependency và kiểm tra khi nâng Hibernate.

## 7. Persistence Context sau bulk DML

Bulk UPDATE/DELETE tác động database trực tiếp và **không đồng bộ từng managed object trong L1 cache**.

~~~java
@Transactional
public void staleStateExample(Long id) {
    Product product = entityManager.find(Product.class, id);
    BigDecimal oldPrice = product.getPrice();

    entityManager.createQuery(
            "update Product p set p.price = :price where p.id = :id"
        )
        .setParameter("price", new BigDecimal("150.00"))
        .setParameter("id", id)
        .executeUpdate();

    BigDecimal valueStillInMemory = product.getPrice();
    // Có thể vẫn là oldPrice.
}
~~~

Database có giá 150 nhưng Java object `product` có thể giữ giá cũ. Nếu tiếp tục sửa rồi flush object này, state cũ có thể ghi đè dữ liệu mới tùy update strategy.

### 7.1. Flush trước, clear sau

~~~java
@Transactional
public int bulkArchive(Instant cutoff) {
    entityManager.flush();

    int affected = entityManager.createQuery(
            """
            update Product p
            set p.status = :archived
            where p.discontinuedAt < :cutoff
            """
        )
        .setParameter("archived", ProductStatus.ARCHIVED)
        .setParameter("cutoff", cutoff)
        .executeUpdate();

    entityManager.clear();

    return affected;
}
~~~

- `flush()` ghi các managed changes pending trước bulk query.
- Bulk statement cập nhật database.
- `clear()` detach tất cả managed entities, tránh tiếp tục dùng snapshots cũ.

`clear()` tác động toàn Persistence Context, không chỉ entities bị bulk update. Những thay đổi chưa flush có thể mất khỏi context; vì vậy phải flush có chủ đích và hiểu transaction.

### 7.2. Refresh một entity

~~~java
entityManager.refresh(product);
~~~

`refresh()` nạp lại state của entity đó từ DB. Tuy nhiên nó có thể ghi đè local changes chưa flush. Với nhiều objects, clear rồi load lại thường dễ kiểm soát hơn.

### 7.3. Xác minh kết quả bằng context mới

Sau bulk operation, không dựa vào object vẫn managed để xác minh database. Dùng EntityManager mới hoặc clear/refresh phù hợp. Một test đọc lại cùng object L1 có thể cho giá cũ dù database đã đổi.

## 8. L2 cache, query cache và application cache

Hibernate có cơ chế cleanup/invalidation cho một số cache regions/query spaces khi chạy HQL/JPQL bulk mutations. Behavior cụ thể phụ thuộc Hibernate version, mapping và cache provider.

Native SQL cung cấp ít metadata hơn để Hibernate biết bảng nào bị ảnh hưởng. Một số API có synchronization/query-space hints; nếu không khai báo affected spaces hoặc không evict cache thích hợp, kết quả cache có thể stale.

Nguyên tắc:

- L1 Persistence Context cần flush/clear/refresh có chủ đích.
- L2 entity cache và query cache phải được kiểm chứng theo provider/version.
- Native SQL cần khai báo affected spaces khi API hỗ trợ hoặc chủ động evict cache regions.
- Application cache cần invalidation riêng.
- Không suy luận “cache đã invalidated” đồng nghĩa callbacks hoặc Envers đã chạy.

## 9. Bulk DML và optimistic locking

Managed update thường dùng version predicate, ví dụ SQL khái niệm:

~~~sql
update products
set price = :price,
    version = :newVersion
where id = :id
  and version = :expectedVersion;
~~~

Nếu version cũ không khớp, ORM có thể phát hiện optimistic locking conflict.

Bulk JPQL/HQL không tự thực hiện optimistic version check cho từng managed entity như vậy. Một câu UPDATE nhiều rows có thể bỏ qua concurrency semantics mà application mong đợi.

### 9.1. Khi cần bảo vệ version

Có thể:

- Giữ managed entity update nếu cần kiểm tra từng version.
- Dùng Hibernate-specific `update versioned` khi semantics và version mapping phù hợp.
- Dùng native/JDBC SQL có `WHERE version = :expectedVersion` và tăng version atomically.
- Dùng staging table chứa expected versions rồi join vào mutation.
- Chọn pessimistic locking/isolation khi nghiệp vụ yêu cầu.

Ví dụ compare-and-swap cho một row:

~~~sql
update products
set price = :newPrice,
    version = version + 1
where tenant_id = :tenantId
  and id = :id
  and version = :expectedVersion;
~~~

Affected count bằng 0 nghĩa version không khớp hoặc row không tồn tại trong scope. Với batch nhiều rows, phải lưu expected version theo từng ID và xử lý các rows không update thành công.

Không tự cho rằng mọi JPQL provider hỗ trợ update version attribute giống nhau; tuân theo Jakarta Persistence và extension Hibernate đang dùng.

## 10. Khi nào dùng JDBC?

JDBC phù hợp khi use case cần:

- SQL DB-specific mà JPQL không biểu diễn tốt.
- CTE, window functions, upsert/merge hoặc returning clauses.
- Temporary/staging tables.
- Array parameters hoặc table-valued parameters.
- Vendor bulk-copy/import utilities.
- PreparedStatement batching với nhiều parameter sets.
- Kiểm soát fetch size, streaming hoặc row mapping.
- Tối ưu SQL plan đã đo được.

JDBC không có dirty checking, entity callbacks, cascades, Envers hay JPA validation tự động. Ứng dụng chịu trách nhiệm trực tiếp về SQL, mapping, constraints, transaction và cache synchronization.

### 10.1. JdbcTemplate batch UPDATE

Giả sử file import chứa mức giá khác nhau:

~~~java
public record PriceChange(
        String tenantId,
        Long productId,
        BigDecimal newPrice
) {}
~~~

Ví dụ Spring JDBC:

~~~java
@Transactional
public int[] applyPriceChanges(List<PriceChange> changes) {
    String sql = """
        update products
        set price = ?
        where tenant_id = ?
          and id = ?
        """;

    return jdbcTemplate.batchUpdate(
        sql,
        new BatchPreparedStatementSetter() {
            @Override
            public void setValues(
                    PreparedStatement ps,
                    int index
            ) throws SQLException {
                PriceChange change = changes.get(index);
                ps.setBigDecimal(1, change.newPrice());
                ps.setString(2, change.tenantId());
                ps.setLong(3, change.productId());
            }

            @Override
            public int getBatchSize() {
                return changes.size();
            }
        }
    );
}
~~~

Ví dụ cần imports Spring/JDBC tương ứng và validation đầu vào. `tenantId` phải được tạo/kiểm từ trusted context, không tin file import hoặc client có thể chọn tenant tùy ý.

### 10.2. Set-based SQL hay JDBC batch?

| Hình dạng workload | Lựa chọn nên cân nhắc |
| --- | --- |
| Cùng một phép biến đổi cho mọi rows theo predicate | Set-based bulk UPDATE |
| Mỗi row có parameter values khác nhau | JDBC batch |
| Mỗi entity có domain/lifecycle logic riêng | Managed entities + Hibernate batching |
| Dữ liệu cực lớn từ file/stream | JDBC batch hoặc vendor bulk loader |
| SQL phức tạp theo DBMS | Native SQL/JDBC |
| Read-only report chỉ cần vài cột | DTO projection hoặc JDBC row mapping |

### 10.3. PreparedStatement và parameter binding

~~~java
String sql =
    "update products set price = ? where id = ?";

PreparedStatement ps = connection.prepareStatement(sql);
ps.setBigDecimal(1, newPrice);
ps.setLong(2, productId);
~~~

Bind parameters tránh SQL injection đối với values và giúp driver/database tái sử dụng prepared statement. Tên bảng/cột hoặc sort direction không thể được bind như ordinary value; nếu phải chọn động, dùng whitelist identifiers.

## 11. JDBC batch không tự bảo đảm mọi rows thành công

`executeBatch()` hoặc Spring `batchUpdate` có thể trả update counts khác nhau theo driver:

- Số rows được cập nhật.
- `Statement.SUCCESS_NO_INFO` khi driver không biết số rows cụ thể.
- `Statement.EXECUTE_FAILED` cho command thất bại trong những trường hợp driver báo chi tiết.
- `BatchUpdateException` chứa counts của những commands trước/đến lỗi theo driver.

Không giả định mọi JDBC driver dừng hoặc tiếp tục batch giống nhau. Nếu một statement thất bại, transaction/database behavior phụ thuộc DBMS, driver và transaction mode.

### 11.1. Kiểm affected counts

Nếu mỗi Product ID phải update đúng một row, hãy kiểm counts tương ứng khi driver cung cấp số chính xác. Một số driver trả SUCCESS_NO_INFO; khi đó không thể xác nhận từng row chỉ từ update counts và có thể cần query đối chiếu hoặc thiết kế SQL trả về affected rows.

Nếu count bằng 0, row có thể không tồn tại, không thuộc tenant hiện hành hoặc version không khớp. Không tiết lộ sự tồn tại của dữ liệu tenant khác trong error response.

### 11.2. Không nuốt BatchUpdateException

Không bắt lỗi rồi tiếp tục commit như thể mọi rows đã thành công. Xác định batch atomicity mong muốn, rollback boundary và retry policy. Không retry toàn bộ batch trong cùng transaction đã lỗi.

## 12. Chia batch thành chunks

Một danh sách quá lớn làm tăng memory, driver buffers và transaction duration. Có thể giới hạn số records mỗi chunk:

~~~java
@Transactional
public void importInChunks(List<PriceChange> changes) {
    int chunkSize = 500;

    for (int start = 0; start < changes.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, changes.size());

        List<PriceChange> chunk =
                changes.subList(start, end);

        applyPriceChanges(chunk);
    }
}
~~~

Nếu method outer được gọi qua Spring proxy và không có transaction boundary khác, ví dụ trên vẫn dùng **một transaction**. Nó chỉ chia JDBC batch, không tự commit từng chunk.

### 12.1. Một transaction hay một transaction mỗi chunk?

**Một transaction bao trọn job:**

- All-or-nothing theo DB transaction nếu resource hỗ trợ.
- Có thể giữ locks và transaction log lâu.
- Rollback có thể tốn kém.
- Retry thường phải chạy lại toàn job hoặc dùng checkpoint riêng.

**Một transaction mỗi chunk:**

- Giảm thời gian và resource của mỗi transaction.
- Có thể resume từ chunk đã commit.
- Job không còn atomic toàn bộ; chunks trước có thể đã commit khi chunk sau lỗi.
- Cần idempotency/checkpoint để retry an toàn.

Không tự chuyển sang chunk-level commits nếu nghiệp vụ yêu cầu toàn bộ dữ liệu thay đổi cùng lúc.

### 12.2. Idempotency

Một import có thể được gửi lại sau timeout. Dùng import ID/operation ID và unique constraint phù hợp để nhận biết records đã xử lý. Không chỉ dựa vào vị trí dòng file vì thứ tự file có thể đổi khi retry.

## 13. Hibernate JDBC batching khi vẫn cần lifecycle

Nếu cần callbacks, cascades, Envers hoặc domain methods, hãy cân nhắc Hibernate batching trước khi chuyển sang JDBC.

~~~java
@Transactional
public void updateProducts(List<ProductInput> inputs) {
    int batchSize = 50;
    int count = 0;

    for (ProductInput input : inputs) {
        Product product = entityManager.find(
                Product.class,
                input.id()
        );

        product.changePrice(input.newPrice());

        if (++count % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

Ví dụ giả định mỗi entity thuộc tenant hiện hành và method domain phù hợp đã tồn tại. Sau `clear()`, entities bị detach; mỗi batch tiếp theo cần load đúng objects lại.

Cấu hình minh họa:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_updates=true
hibernate.order_inserts=true
~~~

Trong Spring Boot có thể truyền Hibernate properties qua `spring.jpa.properties.*` theo cấu hình dự án.

### 13.1. Batch size không có giá trị chung cho mọi hệ thống

Batch size phụ thuộc database, JDBC driver, số cột, statement shape, network latency, lock contention, transaction log, heap, ID generation và khả năng batching của driver.

Bắt đầu bằng một giá trị vừa phải rồi đo throughput, heap/GC, transaction duration, lock waits và số batch executions. Không tăng lên hàng nghìn chỉ vì benchmark local nhanh hơn.

### 13.2. IDENTITY generation có thể hạn chế insert batching

Với một số cấu hình Hibernate dùng IDENTITY generation, ORM cần thực hiện INSERT để lấy generated ID ngay, có thể ngăn insert batching thông thường. Sequence-based identifiers thường thuận lợi hơn cho batching, nhưng phụ thuộc DBMS và schema. Không đổi identifier strategy nếu chưa xét migration, portability và semantics.

## 14. Đọc nhiều rows: dùng projection nếu không cần entity

Một report chỉ cần id, status và totalAmount không nhất thiết phải hydrate toàn bộ Order graph.

~~~java
public record OrderRow(
        Long id,
        OrderStatus status,
        BigDecimal totalAmount
) {}
~~~

~~~java
List<OrderRow> rows = entityManager.createQuery(
        """
        select new com.example.reporting.OrderRow(
            o.id, o.status, o.totalAmount
        )
        from Order o
        where o.tenantId = :tenantId
        order by o.id
        """,
        OrderRow.class
    )
    .setParameter("tenantId", tenantId)
    .getResultList();
~~~

Projection giảm entity hydration và dirty checking khi chỉ đọc dữ liệu. Với kết quả lớn, cân nhắc pagination/keyset, streaming/scrolling, JDBC fetch size và giới hạn connection lifetime.

### 14.1. Tránh dùng entity làm DTO ngoài transaction

Entity có lazy associations và persistence-context semantics. Serialize entity sau transaction có thể gây lazy loading hoặc N+1. DTO/projection tách read model khỏi lifecycle.

## 15. JDBC streaming cho dữ liệu lớn

Ví dụ Spring JDBC đọc từng row:

~~~java
jdbcTemplate.query(
    connection -> {
        PreparedStatement ps = connection.prepareStatement(
            """
            select id, order_code, total_amount
            from orders
            where tenant_id = ?
            order by id
            """
        );
        ps.setString(1, tenantId);
        ps.setFetchSize(500);
        return ps;
    },
    rs -> {
        while (rs.next()) {
            long id = rs.getLong("id");
            String code = rs.getString("order_code");
            BigDecimal amount = rs.getBigDecimal("total_amount");

            exportRow(id, code, amount);
        }
    }
);
~~~

`exportRow` là placeholder cho logic ghi output. Tránh thực hiện network calls chậm trong khi giữ ResultSet/connection mở lâu; có thể buffer theo chunks rồi xử lý tiếp.

### 15.1. Fetch size là hint phụ thuộc driver

`setFetchSize` không bảo đảm mọi JDBC driver stream giống nhau. PostgreSQL JDBC, MySQL Connector/J, Oracle JDBC và SQL Server driver có những điều kiện riêng về cursor, transaction và connection settings. Một số driver vẫn buffer nhiều dữ liệu nếu server-side cursor không được bật.

Đo heap và xác nhận behavior với đúng driver/version production.

### 15.2. Keyset pagination

Với bảng lớn, OFFSET sâu có thể khiến database scan/skip nhiều rows. Keyset pagination:

~~~sql
select id, order_code
from orders
where tenant_id = :tenantId
  and id > :lastSeenId
order by id
fetch first :pageSize rows only;
~~~

Cú pháp limit/fetch phụ thuộc DBMS. Cần thứ tự ổn định và unique tie-breaker nếu sort theo nhiều cột. Nếu dữ liệu thay đổi đồng thời, xác định rõ semantics snapshot/consistency của export.

## 16. Khi nào dùng native SQL/JDBC thay bulk JPQL?

Chọn native SQL/JDBC khi cần CTE phức tạp, window functions, upsert/merge, returning clauses, temporary/staging tables, array parameters, table-valued parameters, vendor bulk-copy utilities hoặc locking clauses đặc thù DBMS.

JPQL thường portable hơn. Native SQL gắn với dialect, table/column names, generated columns, sequences và database behavior. Nếu ứng dụng hỗ trợ nhiều DBMS, có thể cần repository implementations riêng, SQL templates được kiểm soát, migration scripts riêng và integration tests trên từng database.

**JDBC không tự nhanh hơn Hibernate trong mọi trường hợp.** Một query JDBC vẫn có thể gây N+1, đọc quá nhiều rows, thiếu index, lock contention hoặc buffer khổng lồ. Lợi ích của JDBC là kiểm soát trực tiếp và bỏ entity lifecycle overhead khi không cần, không phải bảo đảm tốc độ.

## 17. JPA và JdbcTemplate phải phối hợp transaction đúng

Một service có thể dùng cả JPA và JDBC:

~~~java
@Service
public class ImportService {

    private final EntityManager entityManager;
    private final JdbcTemplate jdbcTemplate;

    @Transactional
    public void importAndFinalize(Long batchId) {
        Order order = createOrder();
        entityManager.persist(order);
        entityManager.flush();

        jdbcTemplate.update(
            "update import_batches set status = ? where id = ?",
            "DONE",
            batchId
        );
    }
}
~~~

Để hai đường tham gia cùng transaction, thường cần cùng underlying DataSource, transaction manager điều phối tương thích và JdbcTemplate lấy connection qua Spring transaction-aware mechanism.

Không mở connection độc lập bằng `DriverManager.getConnection()` rồi giả định nó tham gia transaction của JPA. Nếu dùng nhiều DataSources/transaction managers, phải thiết kế coordination rõ; một `@Transactional` đơn lẻ không làm nhiều databases commit atomic.

### 17.1. Flush trước khi JDBC đọc JPA writes

Nếu JPA persist Order nhưng chưa flush, một JDBC query có thể chưa nhìn thấy SQL INSERT ấy trong database. Flush đồng bộ pending SQL xuống transaction:

~~~java
entityManager.persist(order);
entityManager.flush();

Long count = jdbcTemplate.queryForObject(
    "select count(*) from orders where id = ?",
    Long.class,
    order.getId()
);
~~~

Flush chưa commit. Nếu JDBC và JPA thực sự dùng cùng transaction, JDBC có thể đọc những writes đã flush theo transaction semantics.

### 17.2. JDBC UPDATE có thể làm entity managed stale

Nếu JDBC sửa row mà EntityManager đang quản lý, Java object có thể giữ state cũ. Cần refresh/clear hoặc tránh trộn hai write paths trên cùng entities trong một Persistence Context.

## 18. Tenant scope và authorization vẫn bắt buộc

Bulk query/JDBC không được miễn kiểm soát tenant vì chúng chạy nhanh hơn.

Với shared-table strategy:

~~~java
String tenantId =
        tenantContext.requireAuthorizedTenantId();

int changed = jdbcTemplate.update(
    """
    update inventory
    set quantity = quantity - ?
    where tenant_id = ?
      and sku = ?
      and quantity >= ?
    """,
    amount,
    tenantId,
    sku,
    amount
);
~~~

Tenant ID phải đến từ trusted server context. Với schema/database-per-tenant, JDBC connection phải route đúng tenant database/schema và pool phải reset session state. Nếu dùng DB RLS, application role không được bypass policy và tenant setting phải được gắn trên chính connection thực thi statement.

Joins, subqueries, aggregates, exports và cache keys cũng cần cùng tenant boundary. Outer query lọc tenant nhưng subquery tính tổng toàn hệ thống vẫn là leak.

## 19. Những behavior cần giữ khi bỏ entity lifecycle

Trước khi thay managed entity loop bằng bulk/JDBC, liệt kê behavior cần được giữ:

| Behavior | Managed entities | Bulk HQL/JPQL | JDBC |
| --- | --- | --- | --- |
| Dirty checking | Có | Không theo từng entity | Không |
| Entity callbacks | Theo lifecycle | Không cho từng affected entity | Không |
| JPA cascades/orphan removal | Theo mapping/lifecycle | Không như entity operations | Không |
| Bean Validation lifecycle | Theo JPA integration | Không validate từng entity | Không |
| Envers per-entity audit | Theo audited events | Không tự ghi | Không tự ghi |
| @Version optimistic checks | Theo ORM update | Không tự như managed path | Phải thiết kế |
| DB constraints | Có | Có | Có |
| DB transaction | Có | Có | Có nếu setup đúng |
| SQL portability | ORM/dialect mapping | JPQL portable theo chuẩn | Phụ thuộc SQL/driver |

### 19.1. Chuyển invariant sang database hoặc operation boundary

Nếu bulk path vẫn phải giữ correctness:

- Dùng NOT NULL, UNIQUE, FK và CHECK cho các invariants phù hợp.
- Ghi audit/outbox tường minh trong cùng transaction.
- Dùng trigger nếu mọi writer phải được quan sát.
- Dùng explicit version predicate/increment.
- Validate input trước batch.
- Kiểm row counts và postconditions.
- Gọi domain service ở cấp operation nếu cần, thay vì giả định từng entity callback đã chạy.
- Tránh custom validator query DB cho từng row gây N+1.

### 19.2. Domain events không tự phát sinh từ bulk SQL

Nếu `@PostUpdate` hiện phát domain event, bulk query sẽ bypass listener. Có thể ghi operation event vào outbox. Tuy nhiên event “đã archive 50.000 rows” không tương đương 50.000 per-entity revision records nếu consumers cần từng entity state. Payload phải đáp ứng đúng contract.

## 20. Chọn chiến lược theo workload

| Workload | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Một entity có domain transition phức tạp | Managed entity | Cần invariants, callbacks hoặc locking |
| Nhiều entities, logic riêng từng entity | Managed + Hibernate batching | Giữ lifecycle, giảm round trips |
| Nhiều rows cùng phép biến đổi | Bulk HQL/JPQL hoặc native set-based SQL | Database xử lý set trực tiếp |
| Mỗi row có values khác nhau, cùng statement | JDBC batch | Driver gom parameter sets |
| Hàng triệu rows từ CSV | JDBC batch/vendor loader | Không cần entity graph |
| Data migration SQL phức tạp | Native SQL/JDBC | Cần CTE/temp table/DB features |
| Report vài cột | DTO projection/JDBC | Không cần hydrate entity |
| Cần per-entity Envers/cascade | Managed entity path | Behavior gắn với entity events |
| Cần bulk nhưng audit đầy đủ | Bulk + transactional audit strategy | Phải ghi audit tường minh |
| Cần portability nhiều DBMS | JPQL/ORM trước | Giảm phụ thuộc dialect |

### 20.1. Decision tree

~~~mermaid
flowchart TD
    A["Cần xử lý nhiều rows"] --> B{"Mỗi entity có domain/lifecycle behavior riêng?"}
    B -- Có --> C["Managed entities"]
    C --> D{"Round trips hoặc memory là bottleneck?"}
    D -- Có --> E["Hibernate JDBC batching + flush/clear"]
    D -- Không --> F["Giữ ORM path"]
    B -- Không --> G{"Cùng một phép biến đổi cho cả tập?"}
    G -- Có --> H["Set-based HQL/JPQL"]
    G -- Không --> I{"Cùng SQL nhưng values khác từng row?"}
    I -- Có --> J["JDBC PreparedStatement batch"]
    I -- Không --> K["Native SQL / staging / DB bulk loader"]
    H --> L["Kiểm tenant, version, L1, audit và constraints"]
    J --> M["Kiểm transaction, row counts, idempotency"]
    K --> M
~~~

## 21. Đo hiệu năng trước khi đổi

Một benchmark có ích nên đo:

- Số rows thực sự xử lý.
- Số SQL statements và round trips.
- Tổng transaction duration.
- DB execution time và application processing time.
- Heap/GC và Persistence Context size.
- Batch sizes và batch executions.
- Lock waits/deadlocks.
- Index usage và execution plans.
- Audit/validation overhead nếu phải giữ lifecycle.
- Error rate, retry rate và rollback cost.

### 21.1. So sánh cùng correctness contract

Nếu ORM path chạy Bean Validation, Envers và cascade còn JDBC path bỏ hết, hai đường không còn thực hiện cùng một contract. Benchmark tốc độ mà không công bố behavior bị bỏ là không công bằng.

Hoặc so sánh hai con đường có semantics tương đương, hoặc ghi rõ những hành vi được bỏ và chứng minh use case không cần chúng.

### 21.2. Dùng database production-like

Index, statistics, cardinality, locks, network latency và driver behavior làm thay đổi kết quả. H2 in-memory không đại diện đầy đủ cho PostgreSQL/Oracle/SQL Server nếu workload phụ thuộc Dialect hoặc JDBC driver.

## 22. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Bulk update nhanh nhưng entity managed có giá cũ | L1 không đồng bộ từng object | Flush/clear/refresh có chủ đích |
| Bulk delete không gọi callback | Không đi qua entity remove lifecycle | Managed path hoặc behavior DB/audit riêng |
| Envers thiếu revisions | Bulk/JDBC bypass entity events | Managed updates hoặc audit strategy khác |
| Quantity âm khi có concurrent updates | Check và update tách thành hai câu | Gộp predicate và mutation trong một statement |
| Batch cập nhật một phần | Driver counts/error semantics hoặc transaction boundary | Kiểm counts, rollback/retry theo contract |
| JDBC không rollback cùng JPA | Khác DataSource/transaction manager | Cùng transaction-aware DataSource hoặc coordination |
| Import ngốn memory | Load tất cả records/entities | Chunking, streaming, flush/clear |
| UPDATE sửa nhầm tenant | Thiếu tenant predicate/DB policy | Trusted scope, RLS và tests |
| Version conflict không được phát hiện | Bulk bypass optimistic checks | Explicit version check hoặc managed update |
| Report gây N+1 | Load entity rồi lazy access | Projection/join/aggregate |
| clear làm mất changes pending | Clear trước flush | Flush trước clear theo transaction contract |
| Native SQL làm cache stale | ORM không biết affected spaces | Synchronization/eviction và integration tests |
| Retry tạo duplicate | Thiếu idempotency | Operation ID/unique key/checkpoint |
| Bulk DML lưu dữ liệu sai | Thiếu DB constraints | UNIQUE/FK/CHECK phù hợp |
| JDBC batch không nhanh | Driver/config/statement shape không batch tốt | Đo execution, xem vendor bulk loader |

## 23. Quy trình triển khai an toàn

1. **Xác định invariants nghiệp vụ.** Điều gì phải đúng trước và sau operation?
2. **Liệt kê lifecycle behavior hiện có.** Callbacks, validation, cascades, Envers, versioning, domain events.
3. **Phân loại workload.** Cùng phép biến đổi, nhiều parameter sets, read-only projection hay migration.
4. **Chọn đường phù hợp.** Managed, set-based bulk, JDBC batch hoặc native bulk loader.
5. **Giữ tenant scope và authorization.** Từng SELECT/UPDATE/DELETE/JOIN/subquery phải đúng boundary.
6. **Thiết kế transaction boundary.** All-or-nothing hay chunk-level commits.
7. **Xử lý Persistence Context.** Flush pending state; clear/refresh sau bulk.
8. **Bảo vệ concurrency.** Version predicates, locks, isolation hoặc atomic conditions.
9. **Giữ data integrity.** DB constraints và postcondition checks.
10. **Bù audit/domain events nếu cần.** Ghi trong cùng transaction hoặc qua outbox.
11. **Thiết kế retry/idempotency.** Batch lỗi có thể chạy lại an toàn không?
12. **Kiểm tra caches.** L1/L2/query/application cache có stale không?
13. **Đo trên DBMS/driver thật.** SQL, latency, memory và lock contention.
14. **Viết integration tests.** Kết quả DB, affected counts, rollback và tenant boundaries.
15. **Theo dõi sau release.** Metrics, error rate, transaction duration và batch lag.

## 24. Bài tập thực hành

### Bài 1 — Managed hay bulk?

Một job đổi trạng thái 100.000 ApiToken hết hạn. Entity chỉ có status/expiresAt, không callback, audit hay cascade. Khi nào JPQL bulk UPDATE/DELETE phù hợp hơn việc load 100.000 entities?

### Bài 2 — Inventory atomicity

Vì sao SELECT quantity rồi kiểm tra trong Java, sau đó UPDATE có race condition? Viết một câu UPDATE chứa điều kiện quantity đủ lớn.

### Bài 3 — Persistence Context stale

Load Product vào EntityManager, sau đó bulk UPDATE giá. Giá đọc từ managed object có thể thế nào? Thiết kế flush/clear/refresh phù hợp.

### Bài 4 — Lifecycle bị bỏ qua

Một entity có `@PreUpdate` ghi audit timestamp và Envers `@Audited`. Developer chuyển sang HQL bulk UPDATE. Behavior nào không còn được bảo đảm? Nêu giải pháp nếu bulk bắt buộc.

### Bài 5 — JDBC batch hay set-based SQL?

Import 50.000 sản phẩm, mỗi row có price khác nhau. So sánh PreparedStatement batch, set-based SQL qua staging table và managed entities + Hibernate batching.

### Bài 6 — Versioning

Một JPQL bulk update thay đổi entities có `@Version`. Vì sao không mặc định có optimistic locking như managed update? Mô tả expected-version predicate trong JDBC.

### Bài 7 — BatchUpdateException

Driver ném `BatchUpdateException` sau một số commands. Những thông tin nào có thể nằm trong update counts? Vì sao không nên nuốt exception rồi commit tiếp?

### Bài 8 — Chunk transactions

Job xử lý một triệu rows, chia 500 rows mỗi chunk. So sánh một transaction lớn với một transaction mỗi chunk về atomicity, locks, retry và checkpoint.

### Bài 9 — JPA và JdbcTemplate

Một method `@Transactional` persist Order bằng EntityManager rồi query count bằng JdbcTemplate. Khi nào JDBC thấy row mới? Cần điều kiện gì để cả hai cùng transaction?

### Bài 10 — Tenant scope

Một JDBC batch UPDATE có `WHERE id = ?` nhưng thiếu tenant_id trong shared-table model. Rủi ro là gì? Sửa SQL và nêu nguồn tenant identity.

### Bài 11 — Cache

Bulk native SQL đổi Product nhưng application cache còn giá cũ. Vì sao Hibernate không nhất thiết biết cache nào phải evict? Thiết kế invalidation.

### Bài 12 — Benchmark

Đề xuất benchmark công bằng giữa managed entities + batching và bulk JPQL. Nêu metrics và semantics cần giữ hoặc công bố là đã bỏ.

### Bài 13 — Idempotency

Batch import timeout sau khi DB đã commit nhưng client không nhận response. Khi retry, làm sao tránh áp cùng operation hai lần?

### Bài 14 — Read projection

Một báo cáo chỉ cần id, status và totalAmount. Vì sao DTO projection có thể hiệu quả hơn load entity graph? Khi nào JDBC streaming phù hợp?

### Bài 15 — Database constraints

Bulk UPDATE có thể bypass Bean Validation. Những invariants nào nên đặt ở DB bằng NOT NULL/UNIQUE/FK/CHECK? Giới hạn của từng loại?

**Gợi ý:** (1) khi không cần lifecycle; (2) gộp predicate và mutation; (3) L1 stale; (4) callback/Envers không tự chạy; (5) phân biệt per-row values, lifecycle và staging; (6) explicit version compare; (7) update counts phụ thuộc driver; (8) atomicity toàn job so với checkpoint; (9) cùng DataSource/transaction manager và flush; (10) nguy cơ cross-tenant mutation; (11) native SQL synchronization/eviction; (12) cùng correctness contract; (13) operation ID/unique key; (14) không cần hydrate entity; (15) DB constraints bảo vệ mọi writer nhưng không thay mọi business rule.

## 25. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): flushing, batching, persistence context, stateless operations và JDBC integration.
- [Hibernate ORM 6.6 HQL Reference](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/Hibernate_Query_Language.html): bulk UPDATE/DELETE và HQL mutation queries.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): JPQL bulk update/delete, persistence context và optimistic locking semantics.
- [Spring Data JPA Reference — Modifying Queries](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): `@Modifying`, flushAutomatically và clearAutomatically.
- [Spring Framework Reference — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): JdbcTemplate, prepared statements và batch operations.
- [Java JDBC API — PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html): parameter binding và batch execution.
- [Java JDBC API — BatchUpdateException](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/BatchUpdateException.html): update counts khi batch thất bại.

**Kết luận:** chọn bulk HQL/JPQL hoặc JDBC khi thao tác được mô tả chính xác bằng SQL set-based hoặc batch statements và **không cần per-entity lifecycle behavior**. Nếu cần domain methods, callbacks, cascades, Bean Validation, Envers hoặc optimistic locking theo từng entity, giữ managed operations và tối ưu bằng Hibernate JDBC batching, pagination và flush/clear. Bulk DML phù hợp cho phép biến đổi đồng nhất; JDBC batch phù hợp khi từng row có parameter values riêng; native SQL/JDBC phù hợp khi cần DB-specific features hoặc kiểm soát trực tiếp. Dù chọn đường nào, vẫn phải bảo vệ tenant scope, database constraints, transaction atomicity, cache consistency, error handling và idempotency. Đo workload trên database/driver thực tế rồi mới quyết định tối ưu nào đem lại lợi ích đủ lớn.
