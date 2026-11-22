# So sánh ảnh trạng thái với theo dõi thay đổi bằng bytecode enhancement trong Hibernate

Khi một entity đang được quản lý bởi Hibernate `Session` hoặc Jakarta Persistence `EntityManager`, ứng dụng có thể sửa thuộc tính Java mà không trực tiếp viết SQL `UPDATE`. Đến lúc **flush**, Hibernate phải xác định đối tượng nào đã thay đổi, thuộc tính nào cần đồng bộ và có phải phát DML hay không. Công việc này gọi là **dirty checking**.

Có hai cách quan trọng để nhận biết thay đổi: **so sánh trạng thái hiện tại với ảnh trạng thái được lưu (snapshot-based dirty checking)** và **theo dõi thao tác thay đổi trong bytecode của entity đã được enhancement (inline dirty tracking)**. Hai cách có mục đích giống nhau nhưng khác vị trí phát hiện thay đổi, chi phí và giới hạn khi giá trị là một đối tượng mutable.

Bài này xét Hibernate ORM 6.x trong ngữ cảnh kiến trúc Dirty Checking và Flush. API enhancement, chi tiết tối ưu nội bộ và SQL phát sinh có thể thay đổi theo phiên bản Hibernate, mapping, JDBC driver và `Dialect`. Các tính năng khác của bytecode enhancement như lazy attribute loading và association management là những chức năng riêng, không tự đồng nghĩa với bật dirty tracking.

## 1. Vì sao Hibernate cần dirty checking?

Giả sử một ứng dụng quản lý đơn hàng:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 24)
    private String status;

    @Column(name = "total_amount", precision = 19,
            scale = 2, nullable = false)
    private BigDecimal totalAmount;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public void markPaid() {
        status = "PAID";
    }

    public void changeTotal(BigDecimal amount) {
        totalAmount = amount;
    }

    public String getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Long getId() { return id; }
}
~~~

Khi entity được tải trong transaction:

~~~java
PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, 42L);

order.markPaid();

// Khi flush, Hibernate quyết định có cần SQL UPDATE.
entityManager.flush();
~~~

`markPaid()` chỉ gán field Java. Hibernate phải biết `status` đã thay đổi, liệu `totalAmount` có thay đổi không, có phải tăng `version` không và cần tạo SQL nào.

~~~mermaid
flowchart TD
    A[Entity được tải vào Persistence Context] --> B[Application thay đổi field]
    B --> C[Flush]
    C --> D{Có dirty state?}
    D -- Không --> E[Không tạo entity UPDATE]
    D -- Có --> F[Xác định thuộc tính thay đổi]
    F --> G[Lập update action và SQL DML]
    G --> H[DB thực thi trong transaction]
    H --> I[Commit hoặc rollback]
~~~

Sơ đồ là luồng khái niệm: flush còn xử lý insert, delete, collection actions và những thao tác ORM khác. **Flush khác commit**: SQL đã được thực thi trong transaction vẫn có thể bị rollback.

## 2. Dirty checking dựa trên snapshot hoạt động thế nào?

### 2.1. Loaded state và trạng thái hiện tại

Khi Hibernate tải một managed entity, nó thường giữ **loaded state**: thông tin các giá trị đã đọc hoặc đồng bộ, được tổ chức theo metadata ánh xạ. Tại flush, Hibernate có thể so sánh trạng thái hiện tại với ảnh này để xác định field dirty.

~~~text
Thời điểm tải (Book/Order id=42):

Database          Managed object        Loaded snapshot
status = NEW      status = NEW          status = NEW
total = 250.00    total = 250.00        total = 250.00
version = 3       version = 3           version = 3

Ứng dụng gọi order.markPaid():

Managed object        Loaded snapshot
status = PAID         status = NEW
total = 250.00        total = 250.00

Tại flush:
status: PAID != NEW       → dirty
total: 250.00 == 250.00   → unchanged
~~~

Ảnh trạng thái **không nhất thiết là một entity Java được clone đầy đủ**. Hibernate giữ state phục vụ việc so sánh theo metadata và hệ thống kiểu. Với giá trị mutable, cơ chế snapshot/deep copy phải phản ánh đúng mutability để phát hiện thay đổi của nội dung bên trong.

### 2.2. Các bước so sánh

Trong mô hình đơn giản, Hibernate:

1. Duyệt những entity và collection có thể cần được xử lý trong persistence context.
2. Đọc trạng thái của các thuộc tính cần kiểm tra.
3. So sánh từng giá trị phù hợp với loaded state hoặc dùng một cơ chế dirty detection khác đã có.
4. Dựa trên Java/JDBC type, converter, equality và mutability metadata để xác định dirty attributes.
5. Tạo entity update action nếu cần, phối hợp versioning, cascade, lifecycle và collection actions.
6. Gửi DML qua JDBC khi flush, rồi cập nhật trạng thái quản lý theo vòng đời tương ứng.

Chi phí so sánh có thể tăng khi context giữ nhiều entity với nhiều thuộc tính. Tuy vậy, đây không phải một vòng lặp bắt buộc quét mọi field trong mọi trường hợp: Hibernate có tối ưu cho entity immutable/read-only, dirty flags, collection, loại mapping và trạng thái đã biết.

### 2.3. So sánh theo ngữ nghĩa type

~~~java
order.changeTotal(new BigDecimal("375.00"));
~~~

`BigDecimal` bất biến. Hibernate xét giá trị theo mapping type tương ứng, chứ không nhất thiết chỉ kiểm tra hai object có cùng tham chiếu Java hay không. Hai instance `BigDecimal` khác nhau có thể được coi là bằng nhau cho mục đích dirty checking theo semantics của kiểu.

Cần hiểu rằng **setter được gọi không đồng nghĩa luôn có UPDATE**. Nếu giá trị mới không khác giá trị snapshot theo cách Hibernate xác định equality, entity có thể vẫn được coi là unchanged.

### 2.4. Ưu điểm và giới hạn

Ưu điểm của snapshot comparison là không yêu cầu entity class được instrument. Nó còn có thể nhận biết một số thay đổi **tại chỗ** trong object mutable nếu snapshot/type mapping hỗ trợ sao chép và so sánh đúng.

Đổi lại, loaded snapshots có chi phí bộ nhớ, và flush có thể tốn CPU để kiểm tra các thuộc tính ngay cả khi application chỉ sửa một phần nhỏ. Khi số lượng managed entities rất lớn, phải xem xét cả kích thước persistence context, không chỉ thời gian chạy phép so sánh.

## 3. Inline dirty tracking nhờ bytecode enhancement

**Bytecode enhancement** là quá trình chỉnh sửa bytecode của lớp entity sau khi biên dịch hoặc khi load class trong một môi trường có hỗ trợ. Hibernate thêm logic để entity ghi nhận thay đổi. Khi bật **inline dirty tracking**, Hibernate có thể hỏi một enhanced entity xem những thuộc tính nào đã được đánh dấu thay đổi, thay vì luôn phải tìm khác biệt bằng cách so sánh từng thuộc tính.

~~~mermaid
flowchart LR
    A[Java entity source] --> B[Biên dịch .class]
    B --> C[Hibernate enhancer]
    C --> D[Enhanced entity bytecode]
    D --> E[Gán thuộc tính]
    E --> F[Đánh dấu field dirty]
    F --> G[Flush đọc tracking information]
    G --> H[Update actions / SQL]
~~~

### 3.1. Ví dụ khái niệm về instrumentation

Đoạn sau là **pseudocode**, chỉ giải thích ý tưởng. Nó không phải API công khai cần tự viết vào entity:

~~~java
// PSEUDOCODE - không copy thành entity production.
class EnhancedOrderConcept {
    private String status;
    private Set<String> dirtyFields = new HashSet<>();

    private void writeStatus(String newValue) {
        status = newValue;
        dirtyFields.add("status");
    }

    Set<String> dirtyFields() {
        return dirtyFields;
    }
}
~~~

Trong Hibernate thật, enhancer có thể thêm interface/hook nội bộ, interceptor và những phương thức có tên riêng; cơ chế dữ liệu và việc reset tracker thay đổi theo phiên bản. Ứng dụng viết `order.markPaid()` như bình thường, còn bytecode đã instrument nhận biết field write tương ứng.

### 3.2. So sánh hai cách nhận biết thay đổi

| Khía cạnh | Snapshot-based checking | Enhanced inline dirty tracking |
| --- | --- | --- |
| Tín hiệu chính | Khác biệt giữa loaded state và current state | Thông tin thay đổi do enhanced entity ghi nhận khi field được ghi |
| Thời điểm xác định | Chủ yếu khi flush/dirty check | Có tín hiệu ngay trong lúc thao tác field được instrument, flush sử dụng thông tin ấy |
| Phụ thuộc build/load | Không cần enhancement cho use case bình thường | Bytecode phải thực sự được enhancement phù hợp |
| Nhiều field, rất ít thay đổi | Có thể tốn chi phí so sánh | Có thể giảm số phép so sánh cần thực hiện |
| Mutable value sửa tại chỗ | Có thể phát hiện nếu snapshot và mutability đúng | **Không bảo đảm** thay đổi nội bộ không qua field write sẽ được ghi nhận |
| Collection | Cần collection state/snapshot riêng | Vẫn cần collection handling riêng |
| Chi phí assignment | Thường không có dirty instrumentation | Thêm overhead nhỏ cho thao tác được instrument |
| Snapshot trong bộ nhớ | Thường giữ loaded state | **Không bảo đảm** loại bỏ mọi snapshot/loaded state |
| Chọn cột trong SQL UPDATE | Dựa vào dirty information + mapping/update strategy | Vẫn dựa vào dirty information + mapping/update strategy |
| Optimistic locking | Kết hợp `@Version`/locking | Kết hợp `@Version`/locking giống vậy |

Hai cơ chế không nhất thiết loại trừ nhau tuyệt đối. Hibernate có thể cần snapshot, type descriptors hoặc các phương án bổ sung tùy entity state và kiểu thuộc tính dù class đã enhanced.

### 3.3. Đổi chi phí lúc flush thành chi phí lúc gán field

Snapshot checking có thể dành nhiều thời gian ở flush để kiểm tra trạng thái. Inline tracking thêm việc ghi nhận thay đổi khi field được gán, từ đó giảm một số công việc diff tại flush.

Nếu một transaction tải hàng nghìn entity và chỉ sửa vài field, hướng thứ hai **có tiềm năng** tiết kiệm CPU. Ngược lại, nếu hàng triệu phép ghi field diễn ra trên entity đã enhanced, các tracker cũng có chi phí. SQL I/O, lock contention, snapshot còn cần thiết và persistence context traversal vẫn tồn tại; không thể kết luận enhancement luôn nhanh hơn chỉ từ cách mô tả.

## 4. Tại sao thuộc tính mutable là tình huống đặc biệt?

Khác biệt sâu nhất xuất hiện khi object thay đổi **mà field trong entity không được gán lại**.

### 4.1. `Date#setTime()` không phải gán field entity

Giả sử entity có:

~~~java
import java.util.Date;
import jakarta.persistence.Temporal;
import jakarta.persistence.TemporalType;

// Trong @Entity:
@Temporal(TemporalType.TIMESTAMP)
private Date reviewedAt;

public Date getReviewedAt() {
    return reviewedAt;
}
~~~

Application viết:

~~~java
Date date = order.getReviewedAt();
date.setTime(date.getTime() + 86_400_000L);
~~~

Ở đây không có lệnh `order.reviewedAt = ...`. Một tracker chỉ ghi nhận thao tác **field assignment** không tự thấy mutation bên trong `Date`. Trong khi đó, snapshot checker có thể phát hiện timestamp khác nếu type metadata và cơ chế deep copy đúng.

**Không suy ra** “cứ bật enhancement thì Hibernate sẽ bỏ sót mọi mutable type”. Cách Hibernate xử lý mutable values, type comparators và fallback có thể khác theo phiên bản/mapping. Điều chắc chắn là **theo dõi field write không đủ để bảo đảm nhìn thấy mọi thay đổi nội bộ của object**.

### 4.2. Ưu tiên kiểu bất biến khi hợp lý

~~~java
import java.time.Instant;

// Trong @Entity:
private Instant reviewedAt;

public void rescheduleReview(Instant newTime) {
    this.reviewedAt = newTime;
}
~~~

`Instant` bất biến: ứng dụng thay cả giá trị field nên ý định cập nhật rõ ràng, thuận lợi cho tracker và snapshot. Với `Date`, có thể gán object mới và dùng defensive copy:

~~~java
public void rescheduleReview(Date newValue) {
    this.reviewedAt = newValue == null
            ? null
            : new Date(newValue.getTime());
}

public Date getReviewedAt() {
    return reviewedAt == null
            ? null
            : new Date(reviewedAt.getTime());
}
~~~

Cách này còn tránh code ngoài entity giữ tham chiếu tới object mutable nội bộ rồi sửa vào lúc khó kiểm soát.

### 4.3. Mảng byte và JSON mutable

~~~java
import java.util.Map;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

// Trong @Entity:
private byte[] checksum;

@JdbcTypeCode(SqlTypes.JSON)
private Map<String, Object> attributes;
~~~

Những thay đổi:

~~~java
entity.getChecksum()[0] = 7;
entity.getAttributes().put("priority", "HIGH");
~~~

thay đổi phần tử mảng hoặc `Map`. Chúng không nhất thiết tạo phép gán mới cho field `checksum`/`attributes`, nên không thể chỉ dựa vào field-write tracker.

Với JSON/custom type, cần quan tâm JavaType, mutability, equality, serialization và snapshot/deep copy. Nếu snapshot chỉ giữ cùng tham chiếu mutable object đã bị sửa, nó cũng có thể không còn một “giá trị cũ” độc lập để so sánh chính xác. Cấu hình type đúng quan trọng hơn giả định một annotation có thể tự phát hiện toàn bộ mọi mutation.

### 4.4. Collection không chỉ là basic field

Với `@OneToMany` hoặc `@ElementCollection`, Hibernate thường quản lý **PersistentCollection wrapper**, snapshot/membership và actions riêng:

~~~java
order.getItems().add(new OrderItem(...));
~~~

Đây là mutation của collection chứ không chỉ là `order.items = ...`. Bytecode enhancement dirty tracking của entity không thay thế collection dirty checking, cascade, orphan removal, join table hoặc foreign key updates.

Nếu gọi `order.getItems().get(0).setQuantity(4)`, thay đổi thuộc về entity `OrderItem`, và `OrderItem` có dirty checking của riêng nó. Với `@Embeddable` được sửa nội bộ, cũng cần hiểu cách Hibernate xử lý composite value và enhancement theo phiên bản.

## 5. Chuỗi xử lý flush trong hai cách

### 5.1. Snapshot comparison

~~~text
Load entity
   ↓
Manage entity + loaded snapshot
   ↓
Application changes values
   ↓
Flush
   ↓
Compare current state with loaded snapshot
   ↓
Determine dirty fields/actions
   ↓
Execute INSERT/UPDATE/DELETE/collection DML
   ↓
Transaction commit or rollback
~~~

### 5.2. Enhanced inline tracking

~~~text
Load enhanced entity
   ↓
Application writes instrumented field
   ↓
Enhanced entity records change
   ↓
Flush reads tracking data
   ↓
Hibernate combines it with mapping/type/collection requirements
   ↓
Determine update actions
   ↓
Execute SQL within transaction
~~~

Cả hai vẫn phụ thuộc persistence context, transaction, action queue và flush mode.

~~~java
entityManager.getTransaction().begin();
PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, 42L);

order.markPaid();          // Thay trạng thái Java.
entityManager.flush();     // Có thể thực thi UPDATE.
entityManager.getTransaction().commit();
~~~

**Setter không tự gửi SQL ngay.** `flush()` thực hiện đồng bộ SQL nhưng **chưa commit**; transaction có thể rollback. Trong `FlushModeType.AUTO`, Hibernate có thể tự flush trước một số query hoặc lúc commit tùy quy tắc và provider. `FlushModeType.COMMIT` hay flush mode riêng của Hibernate làm thay đổi thời điểm và ngữ nghĩa tương ứng; enhancement không thay thế flush mode.

### 5.3. Flush xử lý nhiều thứ hơn entity fields

Trong cùng một flush, Hibernate còn có thể phải xử lý:

- Entity insert/delete, generated identifiers và generated values.
- Collection add/remove/update, orphan removal và association ownership.
- Cascading, lifecycle callback và interceptor.
- Optimistic locking bằng `@Version` và các kiểu lock khác.
- JDBC batching, SQL ordering và DB constraints.
- Các loại giá trị được converter hay custom type xử lý đặc biệt.

Do đó ngay cả khi enhanced tracker không báo property nào dirty, Hibernate vẫn cần xử lý những công việc khác trong persistence context.

## 6. Dirty tracking khác `@DynamicUpdate`

Cần phân biệt:

1. **Dirty detection:** Hibernate biết entity/field nào được thay đổi.
2. **Update SQL strategy:** Hibernate quyết định trong `UPDATE SET` có những cột nào.

Mặc định một entity update có thể sử dụng **static SQL** gồm nhiều cột updateable, ngay cả khi chỉ một property khác:

~~~sql
-- Minh họa, không cam kết SQL chính xác của mọi mapping:
update purchase_orders
set status = ?, total_amount = ?, version = ?
where id = ? and version = ?;
~~~

Nếu bật `@DynamicUpdate`:

~~~java
import org.hibernate.annotations.DynamicUpdate;

@Entity
@Table(name = "purchase_orders")
@DynamicUpdate
public class PurchaseOrder {
    // Các field tương tự ví dụ.
}
~~~

Hibernate có thể tạo dạng SQL chỉ cập nhật những cột cần thiết cùng version:

~~~sql
-- Minh họa khi chỉ status dirty:
update purchase_orders
set status = ?, version = ?
where id = ? and version = ?;
~~~

`@DynamicUpdate` **không bật bytecode enhancement**. Snapshot checking vẫn có thể xác định dirty fields để tạo dynamic update; enhanced tracking cũng có thể hoạt động dù không dùng dynamic update. SQL động có thể giảm số cột ghi nhưng tạo nhiều biến thể statement, ảnh hưởng statement cache, batching và chi phí tạo SQL. Lựa chọn phụ thuộc workload.

### 6.1. `@Version` giải quyết vấn đề khác

`@Version` hỗ trợ optimistic locking **giữa các transaction**. Nếu transaction A và B tải cùng entity version=3, A cập nhật thành version=4, thì update B với điều kiện version=3 có thể thất bại và Hibernate báo conflict.

Snapshot/inline tracker chỉ nói **cái gì đổi trong một context**. Chúng không tự ngăn lost update giữa hai persistence context; cần optimistic/pessimistic locking, isolation và conflict policy.

## 7. Cấu hình bytecode enhancement

### 7.1. Build-time enhancement với Maven

Một cách triển khai là dùng `hibernate-enhance-maven-plugin` cùng phiên bản Hibernate phù hợp. Ví dụ cấu hình phiên bản minh họa **6.6.0.Final**:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.hibernate.orm.tooling</groupId>
      <artifactId>hibernate-enhance-maven-plugin</artifactId>
      <version>6.6.0.Final</version>
      <executions>
        <execution>
          <goals>
            <goal>enhance</goal>
          </goals>
        </execution>
      </executions>
      <configuration>
        <enableDirtyTracking>true</enableDirtyTracking>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Khi áp dụng dự án thật, dùng **đúng version** phù hợp với Hibernate ORM runtime thay vì sao chép số version minh họa. Plugin goal, thuộc tính mặc định và cách kích hoạt enhancement có thể khác giữa Hibernate 5, 6, 7. Tài liệu phiên bản của Hibernate và lifecycle build phải được đối chiếu trước khi tích hợp.

Build-time enhancement làm biến đổi `.class` trong quy trình build. Không cần tự chèn các phương thức tracker nội bộ vào source Java.

### 7.2. Gradle và runtime enhancement

Hibernate có Gradle plugin/tích hợp enhancement trong những dòng phiên bản hỗ trợ. Cú pháp Groovy DSL và Kotlin DSL không giống nhau; module nào chứa entity thì module đó phải được xử lý thích hợp. Ngoài build-time, một số môi trường có thể dùng load-time enhancement/java agent, nhưng phụ thuộc class loader, thời điểm load class và container integration.

Những điểm cần hiểu:

- Build có thực sự chạy enhancer cho entity class sẽ được deploy không?
- Artifact runtime có phải artifact đã được enhancement không?
- Có công cụ khác cũng biến đổi bytecode (weaving, framework, test runner) không?
- Tính năng dirty tracking có được bật theo cấu hình và version không?
- Tính năng lazy attribute loading/association management có cần thiết và được bật riêng không?
- Entity có những mutable types hoặc custom mapping cần đặc biệt thận trọng không?

**Enhancement không làm `Session`/`EntityManager` thread-safe**. Chúng vẫn phải được sử dụng theo ranh giới unit of work thích hợp, không chia sẻ một session giữa nhiều thread.

## 8. Chi phí CPU và memory: khi nào có lợi?

Một mô hình đơn giản: nếu persistence context có `n` entity, mỗi entity có `p` property, việc so sánh mọi property một cách ngây thơ có thể tương đương `O(n × p)` phép xem xét. Nếu chỉ `k` field writes được ghi nhận, inline tracking có thể tránh phần lớn phép so sánh thuộc tính khi `k` nhỏ hơn nhiều `n × p`.

Đó chỉ là **ước lượng giải thích cơ chế**, không phải độ phức tạp cố định của Hibernate: entity state, type descriptors, collection checking, snapshots, callback và các tối ưu có thể thay đổi công việc thực tế.

| Tình huống | Nhận xét |
| --- | --- |
| Một transaction tải 2–5 entity đơn giản | Snapshot thường đủ tốt; lợi ích enhancement có thể nhỏ |
| Một transaction có rất nhiều managed entities, nhưng ít thay đổi | Enhanced tracking có tiềm năng giảm CPU time cho property diff |
| Batch sửa hầu hết entity | SQL/JDBC và lock có thể là nút thắt chính; tracker không thay thế batching |
| Entity có nhiều mutable value bị sửa tại chỗ | Cần chính sách type/mutability đúng; enhancement một mình không đảm bảo phát hiện |
| Entity thường immutable/read-only | Hibernate có thể tránh một phần dirty checking bằng mapping và session read-only |
| Collection lớn có nhiều thay đổi | Collection snapshots/actions vẫn đáng kể |
| Đối tượng sống lâu qua nhiều transaction | Cần xử lý stale state và memory, enhancement không giải quyết tất cả |
| Mục tiêu giảm lượng cột `UPDATE` | Xem `@DynamicUpdate` và truy vấn thực tế, không chỉ dirty tracker |

### 8.1. Có còn loaded snapshot sau enhancement không?

Không nên khẳng định enhancement xóa hết loaded state. Hibernate có thể cần thông tin trước đó cho optimistic locking, state comparisons, collection snapshots, converter, callback và các nhánh xử lý khác. Mức giảm bộ nhớ phụ thuộc loại entity, mapping và phiên bản.

Khi cân nhắc tối ưu, đo **heap allocations, memory footprint, CPU của flush, số SQL statements và DB latency**. Hai cơ chế dirty checking có thể sinh ra **cùng một SQL**, nên chỉ đếm số `UPDATE` là không đủ để so hiệu năng.

### 8.2. Cẩn thận với việc “setter chạy là dirty”

Với snapshot, nếu setter được gọi nhưng giá trị vẫn bằng trạng thái cũ, Hibernate có thể coi property là unchanged. Với enhanced tracker, chính sách đánh dấu khi ghi cùng giá trị có thể phụ thuộc instrumentation/version; không giả định mọi setter call luôn tạo `UPDATE`.

~~~java
// Nếu status vốn là "PAID":
order.markPaid();
~~~

Câu lệnh này không đủ để chứng minh đã có thay đổi database. Phải xét type semantics, tracker behavior, read-only mapping và update scheduling.

## 9. Entity lifecycle: managed, detached và merge

Dirty tracking không tự lưu entity khi nó đã rời persistence context.

~~~java
PurchaseOrder detached;

try (Session session = sessionFactory.openSession()) {
    detached = session.get(PurchaseOrder.class, 42L);
}

detached.markPaid();  // Chỉ thay đổi Java object đã detached.
~~~

Cho dù class đã enhanced, entity `detached` không còn session quản lý để flush. Trong context mới, có thể tải một entity managed rồi áp dụng command:

~~~java
PurchaseOrder managed = em.find(PurchaseOrder.class, 42L);
managed.markPaid();
~~~

Hoặc dùng `merge` khi đúng với nhu cầu nghiệp vụ:

~~~java
PurchaseOrder managed = em.merge(detached);
~~~

`merge` trả **managed instance** nhận state đã copy; tham số `detached` vẫn detached. Không phụ thuộc tracker của detached entity để tự đồng bộ với database hay thay thế việc quản lý concurrency.

Các API dễ nhầm:

| API | Tác dụng chính |
| --- | --- |
| `flush()` | Đồng bộ pending DML xuống DB trong transaction |
| `clear()` | Detach toàn bộ managed entities; pending changes chưa flush có thể không còn được đồng bộ |
| `detach(entity)` | Bỏ quản lý một entity |
| `refresh(entity)` | Nạp lại state của managed entity từ DB; có thể ghi đè thay đổi local |
| `close()` | Kết thúc session/entity manager và context của nó |
| `merge(detached)` | Copy state sang một managed instance và trả instance đó |

Bytecode enhancement không thay đổi các hợp đồng vòng đời cơ bản này.

## 10. Không phải mọi field dirty đều được ghi vào database

Một số tình huống khiến thay đổi không tạo `UPDATE` như mong đợi:

- Entity không còn managed (đã `detach`, `clear` hoặc session đã đóng).
- Thuộc tính có `@Column(updatable = false)`.
- Entity được khai báo immutable/read-only theo mapping hoặc session.
- Giá trị mới được type semantics coi là tương đương snapshot.
- Thay đổi tại chỗ trong mutable value không được tracking/type xử lý đúng.
- Flush mode và transaction chưa đồng bộ tại thời điểm quan sát.
- Application thay field rồi thay lại giá trị cũ trước flush.
- Lỗi transaction khiến DML bị rollback.

`@Immutable` và chế độ read-only có thể làm Hibernate tránh một số dirty checking/updates theo ngữ nghĩa tương ứng. Chúng không phải “phiên bản nhanh hơn của enhancement”; hãy dùng khi domain thật sự không cho phép cập nhật entity.

### 10.1. DB-side triggers, native SQL và bulk HQL

Nếu một trigger trong DB cập nhật cột khác, hay ứng dụng chạy native SQL/bulk HQL bypass state transitions của managed entity, persistence context có thể giữ state cũ.

~~~java
em.createMutationQuery(
        "update PurchaseOrder p set p.status = :status"
    )
    .setParameter("status", "ARCHIVED")
    .executeUpdate();
~~~

Bulk DML không giống thao tác trên từng managed entity: nó có thể bỏ qua một số dirty checking/callback/optimistic locking semantics per entity và không tự làm mới mọi object managed hiện có. Cần quản lý `flush`/`clear`/`refresh` và transaction theo yêu cầu.

Enhanced inline tracking chỉ ghi nhận những thay đổi qua những đường mà enhanced entity quan sát được; nó không tự phát hiện thay đổi do trigger hay một dịch vụ khác thực hiện trong database.

## 11. Dirty tracking với association và collection

Giả sử:

~~~java
// Trong Order entity:
@OneToMany(mappedBy = "order",
           cascade = CascadeType.ALL,
           orphanRemoval = true)
private List<OrderItem> items = new ArrayList<>();
~~~

Các thao tác khác nhau đòi hỏi cơ chế khác nhau:

| Thao tác | Thực thể/trạng thái liên quan |
| --- | --- |
| `order.setStatus("PAID")` | Basic property của `Order` |
| `order.getItems().add(item)` | Membership của managed collection; cascade/association |
| `order.getItems().remove(item)` | Collection dirty state, có thể orphan removal |
| `item.setQuantity(5)` | Basic property của entity `OrderItem` |
| `order.setItems(newList)` | Thay collection reference; wrapper/ownership cần được xử lý đúng |

Inline tracking của `Order.status` không thay thế collection snapshots và action queue. Nếu một relationship là hai chiều, cần đồng bộ owning side trong Java theo mapping. Bytecode enhancement có một chức năng *association management* riêng ở một số phiên bản, nhưng đó không phải dirty tracking.

## 12. Custom type và `MutabilityPlan`

Với custom basic type, Hibernate cần biết:

1. Ngữ nghĩa bằng nhau của Java value.
2. Giá trị là immutable hay mutable.
3. Cách copy/snapshot nếu mutable.
4. Cách bind/extract JDBC hoặc converter.
5. Hành vi với `null`, dirty checking và cached state.

Một value object bất biến thường dễ quản lý hơn:

~~~java
public record Money(
        java.math.BigDecimal amount,
        String currency
) {}
~~~

Nếu `Money` được lưu bằng `@Embeddable` hoặc mapping phù hợp, thay nguyên value object là một thao tác rõ ràng. Ngược lại, một custom `MutableSettings` tự thay đổi `Map` nội bộ có thể không phát sinh field assignment trên entity.

~~~java
public final class MutableSettings {
    private final Map<String, String> values = new HashMap<>();

    public void set(String key, String value) {
        values.put(key, value);
    }
}
~~~

Ví dụ giả định có imports `java.util.Map` và `java.util.HashMap`. Nếu dùng custom `JavaType`/`JdbcType`/`UserType`, phải xác định `MutabilityPlan` và equality đúng với domain. Một snapshot chỉ giữ cùng reference tới mutable object có thể khiến cả “trước” và “sau” đổi cùng lúc, làm mất khả năng so sánh.

## 13. Quan sát SQL và phân tích hiện tượng

Trong môi trường phát triển, Hibernate 6 thường sử dụng logger `org.hibernate.SQL` ở mức DEBUG để xem statement, và `org.hibernate.orm.jdbc.bind` ở mức TRACE để điều tra tham số khi thật sự cần. Cấu hình logger cụ thể tùy Spring Boot/Logback/Log4j; bind trace có thể lộ dữ liệu nhạy cảm, nên không bật tùy tiện trong production.

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, 42L);
order.markPaid();
em.flush();

order.changeTotal(new BigDecimal("390.00"));
em.flush();
~~~

Quan sát thực tế: số `UPDATE`, cột `SET`, thời điểm flush, thay đổi `version`, có `@DynamicUpdate` không, collection nào khác bị đồng bộ, driver và transaction behavior. **Một SQL UPDATE hợp lý không đủ chứng minh bytecode enhancement đã được bật** vì snapshot checker cũng có thể tạo đúng SQL đó.

| Hiện tượng | Cách lý giải cần xem xét |
| --- | --- |
| Setter được gọi nhưng không có SQL | Giá trị bằng snapshot; entity detached/read-only; flush chưa xảy ra; cột không updateable |
| Có SQL update nhiều cột dù chỉ sửa một field | Static update SQL hoặc các thuộc tính/version khác cùng được ghi |
| Sửa `Map` JSON bằng `put` nhưng không có DML | Mutable type, snapshot/deep copy và field-write tracking cần được hiểu |
| Update collection dù parent field không được gán | PersistentCollection ghi nhận membership change |
| Entity đã được enhanced nhưng flush vẫn tốn thời gian | Collection, action queue, snapshots, JDBC, lock hoặc DB I/O vẫn có chi phí |
| Sau bulk update, `find` trả dữ liệu cũ | First-level cache còn managed state, bulk DML không tự refresh |
| Hai transaction ghi đè nhau | Cần optimistic/pessimistic locking, không phải đổi dirty checking |
| Thay đổi object detached không được ghi | Không có persistence context quản lý object ở thời điểm flush |

## 14. Lựa chọn trong các tình huống ứng dụng

### 14.1. REST CRUD ngắn

Một service tải vài entity, thay một số field rồi commit thường hoạt động tốt với dirty checking mặc định. Không cần bắt buộc enhancement để ORM cập nhật đúng. Nếu performance profiling không cho thấy chi phí dirty checking đáng kể, hãy ưu tiên code/domain rõ ràng và transaction scope gọn.

### 14.2. Batch lớn có rất nhiều managed entities

Enhanced tracking có thể hữu ích khi entity nhiều field nhưng ít field thay đổi, tuy vậy **flush/clear theo chunk**, transaction boundary, ID generator và JDBC batching vẫn là những yếu tố chính. Giữ 100.000 entity trong một persistence context có thể gây memory pressure ngay cả khi bật enhancement.

### 14.3. Ứng dụng có nhiều mutable values

`Date`, mảng, `Map` JSON hoặc custom mutable type cần chủ động thiết kế equality, snapshot và cách sửa state. Ưu tiên immutable value object và thay bằng giá trị mới nếu phù hợp. Không dựa duy nhất vào field-write tracker.

### 14.4. Muốn SQL chỉ cập nhật cột thay đổi

Xem xét `@DynamicUpdate`, cột updateable, `@Version` và các SQL log thực tế. Bytecode tracking giúp phát hiện field thay đổi nhưng không tự bảo đảm `UPDATE` chỉ ghi đúng một cột. Đo chi phí SQL động và lợi ích trên DBMS thực tế.

### 14.5. Hệ thống có nhiều thread và transaction

Mỗi đơn vị công việc cần session/transaction phù hợp; enhanced entity không an toàn để chia sẻ mutable state tùy tiện giữa nhiều thread. `@Version` và locking giải quyết xung đột transaction; first-level cache chỉ quản lý entity identity trong context của nó.

## 15. Câu hỏi tự suy luận

1. Một entity có 60 thuộc tính nhưng chỉ một setter được gọi. Vì sao snapshot checking có thể so sánh nhiều giá trị hơn inline tracking?
2. Entity giữ `Date reviewedAt`; gọi `reviewedAt.setTime(...)` mà không gán lại field. Vì sao field-write tracker có thể không thấy thay đổi này?
3. Có `@DynamicUpdate` mà không bật enhancement, Hibernate có thể xác định dirty fields để tạo SQL động không?
4. Với `@ElementCollection List<String> tags`, gọi `tags.add("new")`. Vì sao không chỉ là một basic field assignment?
5. Sau `flush()` rồi `rollback()`, dữ liệu có được coi là đã commit không?
6. Entity được enhancement nhưng đã detached. Sửa nó có tự làm session khác ghi DB không?
7. Hai transaction đều sửa `PurchaseOrder#42`. Vì sao dirty tracking không thay thế `@Version`?
8. Nếu hai phương pháp tạo SQL giống hệt nhau, cần thêm metric nào để so hiệu năng của chúng?

**Gợi ý:** (1) so sánh ảnh xét old/current, inline tracking có dirty attribute set; (2) không ghi field của entity; (3) có, dynamic SQL khác cơ chế detection; (4) Hibernate quản lý collection state riêng; (5) không; (6) không; (7) concurrency khác local dirty state; (8) CPU của flush, allocations/heap, thời gian transaction và database I/O.

## 16. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): các phần về dirty checking, bytecode enhancement, persistence context, flush và mutable values.
- [Hibernate ORM Documentation](https://hibernate.org/orm/documentation/): chọn hướng dẫn enhancer/plugin và migration guide theo đúng phiên bản Hibernate đang chạy.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): các hợp đồng entity state, `EntityManager`, `flush`, managed/detached lifecycle và transactions.

**Điểm cần ghi nhớ:** snapshot-based dirty checking so sánh **trạng thái trước và sau**; bytecode-enhanced inline tracking ghi nhận **những thay đổi mà bytecode được instrument có thể quan sát**. Với giá trị mutable, collection và custom type, Hibernate còn cần những cơ chế type/snapshot riêng. Dù dùng cách nào, flush vẫn quyết định lúc đồng bộ SQL; commit/rollback quyết định transaction; optimistic locking xử lý xung đột giữa các giao dịch độc lập.
