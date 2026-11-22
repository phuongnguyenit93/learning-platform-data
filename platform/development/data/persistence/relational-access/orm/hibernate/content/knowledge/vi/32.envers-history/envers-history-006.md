# Theo dõi quan hệ và ranh giới giữa dữ liệu có với không có kiểm toán

Hibernate Envers là mô-đun ghi nhận **lịch sử phiên bản của các entity được đánh dấu kiểm toán**. Khi một entity được thêm, thay đổi hoặc xóa qua những thao tác ORM mà Envers hỗ trợ, Envers lưu lại trạng thái lịch sử vào các bảng audit để ứng dụng có thể hỏi: “Ở revision R, bản ghi này trông như thế nào?”.

Với các basic attributes như `name`, `status`, `total`, câu trả lời khá trực quan. Nhưng khi entity liên kết tới entity khác, câu hỏi trở nên khó hơn:

- **Một đơn hàng đã đổi customer ở revision nào?**
- **Danh sách OrderLine của đơn hàng tại revision R gồm những dòng nào?**
- **Nếu Customer được audit nhưng ProductCategory không được audit, việc đọc đơn hàng cũ sẽ thấy tên danh mục cũ hay tên hiện tại?**
- **Nếu entity đích đã bị xóa thì lịch sử quan hệ còn đọc được không?**
- **`@NotAudited` trên một field khác gì `@Audited(targetAuditMode = NOT_AUDITED)` trên một association?**
- **Một thay đổi qua bulk SQL hoặc ngoài Hibernate có đi vào lịch sử Envers không?**

Đây là bài toán về **ranh giới kiểm toán** (*audit boundary*): phần nào của object graph được tái dựng theo lịch sử, phần nào chỉ được lấy từ dữ liệu hiện hành, phần nào bị bỏ khỏi audit hoàn toàn.

Bài học tập trung vào cách Envers ghi nhận quan hệ `@ManyToOne`, `@OneToMany`, `@OneToOne`, `@ManyToMany`, collection membership và join tables; cách dùng `@Audited`, `@NotAudited`, `RelationTargetAuditMode.NOT_AUDITED`, `@AuditJoinTable`, `@AuditMappedBy`; cách đọc snapshot bằng `AuditReader`; cũng như các giới hạn về consistency, delete, transaction, migration, bảo mật và kiểm thử.

> **Nguyên tắc cốt lõi:** Có lịch sử của entity A không tự động có nghĩa ứng dụng sở hữu một “ảnh chụp bất biến của toàn bộ graph A” tại thời điểm đó. Lịch sử của quan hệ chỉ chính xác khi bạn biết cả **mối liên kết** và **trạng thái entity đích** được audit theo mô hình nào.

---

## 1. Envers lưu điều gì khi một entity được audit?

Khai báo cơ bản:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.envers.Audited;

@Entity
@Audited
public class Customer {

    @Id
    private Long id;

    private String displayName;

    // Constructors, methods...
}
```

Khi Hibernate/Envers được cấu hình đúng, entity `Customer` có bảng dữ liệu chính và một bảng lịch sử, thường có hậu tố `_AUD`.

Ví dụ khái niệm:

```text
customers
  id | display_name
  42 | "An Nguyễn"

customers_AUD
  id | REV | REVTYPE | display_name
  42 |  7  |  ADD    | "An"
  42 | 12  |  MOD    | "An Nguyễn"

REVINFO
  REV | REVTSTMP
   7  | ...
  12  | ...
```

`REVTYPE` trong DB là các mã Envers sử dụng cho `ADD`, `MOD`, `DEL`; chữ ở bảng chỉ là ký hiệu giải thích. Tên bảng/cột/khóa chính thực tế phụ thuộc naming strategy, Envers settings và audit strategy.

Envers ghi lịch sử theo **revision**, không phải copy toàn bộ database mỗi lần:

- Revision là mốc thay đổi do Envers quản lý, thường gắn với một transaction có thay đổi audited state.
- Nhiều entity cùng thay đổi trong một transaction có thể cùng revision.
- Với mỗi audited entity, audit tables chứa những dòng cần thiết để truy hồi trạng thái ở revision đó.
- Một entity không được audit **không tự có audit rows**, dù nó được tham chiếu từ entity khác.

### 1.1. Dependency và cấu hình cơ bản

Gradle:

```kotlin
dependencies {
    implementation("org.hibernate.orm:hibernate-envers")
}
```

Trong dự án thật nên quản lý phiên bản bằng Hibernate BOM / dependency management để `hibernate-core` và `hibernate-envers` cùng major/minor tương thích.

Với các phiên bản Hibernate hiện đại, Envers đăng ký listeners qua tích hợp mô-đun; thông thường không cần tự cấu hình event listeners Envers theo cách Hibernate rất cũ.

Envers được áp cho các entity/fields được đánh dấu `@Audited`. Nó **không tự bật audit cho toàn bộ persistence unit**.

### 1.2. Envers không phải database audit log toàn cục

Envers dựa vào những entity lifecycle actions mà Hibernate xử lý. Nó không tự thấy:

- `UPDATE`/`DELETE` do script DBA chạy trực tiếp.
- JDBC statements từ service khác.
- SQL triggers sửa những cột mà ORM không quản lý theo event phù hợp.
- Bulk JPQL/HQL/native SQL làm thay đổi hàng loạt mà không đi qua per-entity lifecycle.
- Thao tác trên external data store.

Nếu yêu cầu kiểm toán **mọi writer** trên database, Envers có thể không đủ; cần cân nhắc database triggers, CDC, transaction log hoặc một write boundary duy nhất được thực thi nghiêm ngặt.

## 2. Phân biệt bốn mức “có lịch sử”

Trong hệ thống có `Order`, `Customer`, `Product` và `OrderLine`, không nên hỏi chung “quan hệ này đã được audit chưa?” mà tách:

1. **Lịch sử thuộc tính của chủ thể**: ở revision R, `Order.status` và `Order.total` là gì?
2. **Lịch sử khóa liên kết**: ở revision R, `Order.customer_id` trỏ tới ID nào?
3. **Lịch sử thành viên collection**: ở revision R, `Order.lines` có những line IDs nào?
4. **Lịch sử nội dung đối tượng đích**: ở revision R, `Customer.displayName`, `Product.price`, `OrderLine.quantity` là gì?

Mức 2 có thể tồn tại trong khi mức 4 không tồn tại.

Ví dụ:

```text
Revision R=5:
  Order#1000.customer_id -> Customer#42

Revision R=10:
  Order#1000.customer_id -> Customer#43
```

Nếu `Order` được audit thì việc thay FK có thể được lưu trong `Order_AUD`. Nhưng muốn biết *tên Customer#42 ở R=5*, bản thân Customer cũng cần audit, hoặc bạn phải lưu tên đó như dữ liệu snapshot độc lập.

### 2.1. Bảng quyết định ranh giới

| Chủ thể | Quan hệ | Entity đích | Có thể đọc lại điều gì? |
| --- | --- | --- | --- |
| Audited | Audited, target audited | Audited | Quan hệ và dữ liệu đích theo revision |
| Audited | Audited, target `NOT_AUDITED` | Không audited | Khóa quan hệ lịch sử, dữ liệu đích hiện tại |
| Audited | Audited, target `NOT_AUDITED` | Audited nhưng ép current-target | Quan hệ lịch sử và trạng thái hiện tại của đích theo semantics phiên bản |
| Audited | `@NotAudited` | Bất kỳ | Không có contract lịch sử cho thuộc tính/quan hệ đó |
| Không audited | Association bình thường | Audited | Chủ thể không có lịch sử Envers chỉ vì đích audited |
| Không audited | Association bình thường | Không audited | Không có lịch sử Envers |

Một liên kết lịch sử tới **ID đích** không bằng một bản sao đầy đủ của đích.

## 3. Mô hình ví dụ: Order – Customer – Category – OrderLine

Ta dùng bốn entity:

```text
PurchaseOrder (audited)
   | customer (audited target)
   v
Customer (audited)

PurchaseOrder (audited)
   | category (non-audited reference data)
   v
ProductCategory (not audited)

PurchaseOrder (audited)
   | lines (audited collection + audited targets)
   v
OrderLine (audited)
```

Ý định nghiệp vụ:

- Đơn hàng cần lịch sử trạng thái, tổng tiền, customer đang được gán.
- Customer có thể đổi tên; báo cáo lịch sử cần tên theo revision.
- ProductCategory là dữ liệu tham chiếu mang tính danh mục, được phép hiển thị **tên hiện tại** (nếu chấp nhận semantics này).
- OrderLine cần lưu giá, số lượng và membership tại từng revision.
- Một field mang tính kỹ thuật như `lastViewedAt` không cần lưu lịch sử.

### 3.1. Audited Customer

```java
import jakarta.persistence.*;
import org.hibernate.envers.Audited;

@Entity
@Table(name = "customers")
@Audited
public class Customer {

    @Id
    private Long id;

    @Column(nullable = false)
    private String displayName;

    protected Customer() {}

    public Long getId() { return id; }
    public String getDisplayName() { return displayName; }

    public void rename(String next) {
        displayName = java.util.Objects.requireNonNull(next);
    }
}
```

### 3.2. ProductCategory không audited

```java
import jakarta.persistence.*;

@Entity
@Table(name = "product_categories")
public class ProductCategory {

    @Id
    private Long id;

    @Column(nullable = false, unique = true)
    private String code;

    @Column(nullable = false)
    private String displayName;

    protected ProductCategory() {}

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getDisplayName() { return displayName; }
}
```

Không có `@Audited` trên `ProductCategory`: Envers không tự tạo `product_categories_AUD` cho entity này.

### 3.3. Audited OrderLine

```java
import jakarta.persistence.*;
import org.hibernate.envers.Audited;
import java.math.BigDecimal;

@Entity
@Table(name = "order_lines")
@Audited
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false,
            precision = 18, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() {}

    void attachTo(PurchaseOrder nextOrder) {
        order = nextOrder;
    }

    public int getQuantity() { return quantity; }
    public BigDecimal getUnitPrice() { return unitPrice; }
}
```

`unitPrice` là **giá đã chốt tại thời điểm bán**, không phải giá catalog hiện tại. Đây là một thiết kế quan trọng: dữ liệu tài chính không nên phụ thuộc vào việc đọc lại một product catalog đang thay đổi.

### 3.4. Audited PurchaseOrder với ba loại quan hệ

```java
import jakarta.persistence.*;
import org.hibernate.envers.Audited;
import org.hibernate.envers.NotAudited;
import org.hibernate.envers.RelationTargetAuditMode;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
@Audited
public class PurchaseOrder {

    @Id
    private Long id;

    @Column(nullable = false)
    private String orderNumber;

    @Column(nullable = false)
    private String status;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal total;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    @Audited(
        targetAuditMode = RelationTargetAuditMode.NOT_AUDITED
    )
    private ProductCategory category;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    @NotAudited
    @Column(name = "last_viewed_at")
    private Instant lastViewedAt;

    protected PurchaseOrder() {}

    public Customer getCustomer() { return customer; }
    public ProductCategory getCategory() { return category; }
    public List<OrderLine> getLines() { return lines; }

    public void addLine(OrderLine line) {
        lines.add(line);
        line.attachTo(this);
    }

    // Setters, guards và các invariants còn lại...
}
```

Điểm cần nhìn ở đây:

- Cả `PurchaseOrder` và `Customer` được audit: mặc định một audited relation có thể trỏ tới **Customer lịch sử**.
- `ProductCategory` **không được audit**. Quan hệ `category` phải khai báo `targetAuditMode = NOT_AUDITED` nếu muốn theo dõi relation reference mà không yêu cầu lịch sử của category.
- `OrderLine` được audit và là owning side của FK `order_id`. Collection `lines` ở `PurchaseOrder` là inverse side thông thường.
- `lastViewedAt` là thuộc tính loại khỏi audit bằng `@NotAudited`.

Các entity đang dùng assigned IDs để ví dụ dễ đọc; production có thể dùng sequence/identity phù hợp và migrations tạo bảng audit. Snippets là một mô hình minh họa để giải thích annotation, không phải toàn bộ source compile-ready của một ứng dụng.

## 4. `@Audited` trên class và trên field khác nhau

Nếu:

```java
@Entity
@Audited
public class PurchaseOrder {
    // ...
}
```

Envers xem các persistent properties của entity là audited theo quy tắc mapping/hỗ trợ của nó, trừ những properties được loại bằng `@NotAudited` hoặc được cấu hình override phù hợp.

Ngược lại, nếu chỉ muốn một số field:

```java
@Entity
public class Customer {

    @Id
    private Long id;

    @Audited
    private String displayName;

    private String internalNote;
}
```

cần phân biệt phần audited với phần không audited. Việc áp annotation ở mức property phải tương thích với kiểu access (field/property) và cấu trúc entity thực tế.

### 4.1. `@NotAudited` là “không lưu lịch sử thuộc tính này”

Ví dụ:

```java
@Audited
@Entity
public class Customer {

    @Id
    private Long id;

    private String displayName;

    @NotAudited
    private String cachedSearchText;
}
```

Khi `cachedSearchText` thay đổi nhưng các audited properties khác không đổi, không có lý do để coi đó là một biến đổi lịch sử nghiệp vụ của `Customer` theo audit mapping đã chọn.

**Không dùng `@NotAudited` để nói “entity đích không cần audit nhưng vẫn muốn lịch sử mối quan hệ”**. Điều đó thuộc `targetAuditMode`, không phải `@NotAudited`.

## 5. Ba annotation dễ bị nhầm nhất

| Annotation | Đặt ở đâu | Ý nghĩa đúng |
| --- | --- | --- |
| `@Audited` | Entity/class hoặc persistent property | Ghi lịch sử cho entity/property |
| `@NotAudited` | Property/association | Loại property/association đó khỏi audit |
| `@Audited(targetAuditMode = NOT_AUDITED)` | Association property | Theo dõi quan hệ nhưng resolve **đích ở current state** thay vì audited target state |

Hai cách sau **không tương đương**:

```java
@NotAudited
@ManyToOne
private ProductCategory category;
```

và:

```java
@Audited(
    targetAuditMode = RelationTargetAuditMode.NOT_AUDITED
)
@ManyToOne
private ProductCategory category;
```

Cách thứ nhất: `category` không thuộc audit contract; bạn không thể đòi hỏi lịch sử category association từ Envers.

Cách thứ hai: Envers theo dõi relation reference của order, nhưng khi đọc `ProductCategory` từ một order lịch sử, nó lấy **bản ghi hiện tại** của category.

## 6. Tại sao Envers cần `targetAuditMode = NOT_AUDITED`?

Một audited association mặc định được hiểu trong mô hình audit: đích của quan hệ cũng có lịch sử để truy hồi tại revision tương ứng.

Nếu:

```java
@Audited
@Entity
class PurchaseOrder {

    @ManyToOne
    private ProductCategory category;
}
```

mà `ProductCategory` không audited, Envers có thể không dựng được relation mapping theo audit semantics mặc định và báo lỗi cấu hình khi bootstrap.

Để thể hiện rõ ranh giới:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "category_id")
@Audited(
    targetAuditMode = RelationTargetAuditMode.NOT_AUDITED
)
private ProductCategory category;
```

Đây không phải “tắt audit của PurchaseOrder”. Nó chỉ chọn cách Envers resolve **target entity** của một association được audit.

### 6.1. Tình huống phù hợp

- Bảng `country_codes` có mã quốc gia ổn định, ít đổi.
- Bảng taxonomy có ID cố định và chỉ cần đọc label hiện tại.
- Bảng loại hình tài liệu không yêu cầu tái dựng nội dung cũ.
- Reference entities được quản lý bởi hệ thống riêng nhưng business chấp nhận current representation.

### 6.2. Tình huống không nên dùng

- Giá sản phẩm tại ngày mua.
- Tỷ lệ thuế/phí tính vào giao dịch cũ.
- Thông tin quyền truy cập được yêu cầu cho điều tra lịch sử.
- Mô tả pháp lý/hợp đồng phải giữ nguyên khi đã ký.
- Tỷ giá đã áp cho giao dịch.
- Nhãn phân loại mà việc đổi nhãn làm thay đổi ý nghĩa báo cáo cũ.

Ở những trường hợp này, audit target hoặc lưu **immutable snapshot/value** vào audited entity theo domain là lựa chọn phù hợp hơn.

## 7. Đọc quan hệ tới target không audited: hiện tại và lịch sử trộn nhau

Giả sử:

```text
R1:
  PurchaseOrder#100.category_id = 9
  ProductCategory#9.displayName = "Điện tử"

R2:
  ProductCategory#9.displayName đổi thành "Thiết bị số"
  (ProductCategory không được audit)

R3:
  PurchaseOrder#100.status đổi từ DRAFT -> PAID
```

Đọc order ở R1:

```java
AuditReader reader = AuditReaderFactory.get(entityManager);

PurchaseOrder orderAtR1 =
    reader.find(PurchaseOrder.class, 100L, r1);

String name = orderAtR1.getCategory().getDisplayName();
```

Kết quả có thể là `"Thiết bị số"` — **tên hiện tại**, không phải `"Điện tử"` tại R1 — vì category là non-audited target.

Sơ đồ:

```text
PurchaseOrder_AUD (as of R1)
  order_id=100
  category_id=9
      |
      v
ProductCategory (live table, CURRENT)
  id=9
  display_name="Thiết bị số"
```

Đó là một historical owner cùng **live referenced entity**.

### 7.1. Không gọi kết quả này là “snapshot nguyên vẹn của toàn bộ graph”

Nó chỉ chính xác trong phạm vi contract đã chọn. Nếu hiển thị màn hình “Chi tiết đơn hàng ngày mua” mà dùng tên category hiện tại, phải hiểu và chấp nhận hậu quả, hoặc nêu rõ UI dùng **nhãn danh mục hiện tại**.

### 7.2. Lưu snapshot thuộc tính quan trọng khi cần

Ví dụ OrderLine có:

```java
@Audited
@Column(name = "product_name_at_purchase")
private String productNameAtPurchase;

@Audited
@Column(name = "unit_price", precision = 18, scale = 2)
private BigDecimal unitPrice;
```

Ngay cả khi `Product` trong catalog đổi tên/giá, dữ liệu giao dịch lịch sử vẫn có thông tin đúng tại thời điểm mua.

Không cần duplicate toàn bộ Product entity nếu chỉ cần một số giá trị bất biến cho chứng từ. Hãy chọn **business snapshot fields** rõ ràng.

## 8. Quan hệ giữa hai audited entities

Nếu cả `PurchaseOrder` và `Customer` đều `@Audited`, quan hệ:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

theo mặc định có audited target semantics.

Ví dụ:

```text
R4: Customer#42.displayName = "An"
R6: Order#100.customer_id = 42
R9: Customer#42.displayName = "An Nguyễn"
```

Đọc Order#100 tại R6:

```java
PurchaseOrder oldOrder =
    reader.find(PurchaseOrder.class, 100L, 6);

String customerName =
    oldOrder.getCustomer().getDisplayName();
```

Với audited relation được mapping hỗ trợ, Envers resolve **Customer lịch sử tại R6**, thường là `"An"`, thay vì tên mới ở R9. Quan hệ có FK lịch sử, target có audit rows, nên có thể dựng lại một lát cắt lịch sử theo revision.

### 8.1. Cùng revision không có nghĩa cùng timestamp tuyệt đối

Envers revision thường đại diện những thay đổi audited state trong transaction. Một graph lịch sử “as-of R” có nghĩa chọn state áp dụng tại revision đó.

Không tự suy revision numbers tuần tự tuyệt đối theo wall-clock giữa mọi database/node, hoặc giả định không có gaps. Revision identifiers và timestamps là metadata, có thể chịu ảnh hưởng transaction concurrency, ID allocation và clock policy.

## 9. Một thay đổi trong Hibernate 7.3 cần biết

Trước Hibernate 7.3, có trường hợp:

```java
@ManyToOne
@Audited(
    targetAuditMode = RelationTargetAuditMode.NOT_AUDITED
)
private Customer customer;
```

trong đó **Customer thực ra cũng được `@Audited`**. Dù developer yêu cầu `NOT_AUDITED`, Hibernate cũ có thể bỏ qua chế độ này và vẫn resolve **Customer lịch sử**.

Theo Hibernate ORM **7.3 Migration Guide**, từ Hibernate 7.3, setting `NOT_AUDITED` được tôn trọng: khi đọc owner lịch sử, `Customer` được lấy từ **current state**, kể cả khi Customer có bảng audit riêng.

Điều đó dẫn đến khác biệt quan sát:

| Cấu hình | Hibernate trước 7.3 (trường hợp được migration guide nêu) | Hibernate 7.3+ |
| --- | --- | --- |
| Owner audited, target audited, `targetAuditMode=NOT_AUDITED` | Có thể resolve target lịch sử vì setting bị bỏ qua | Resolve target hiện tại |
| Owner audited, target audited, mặc định `AUDITED` | Target lịch sử | Target lịch sử |
| Owner audited, target không audited, `NOT_AUDITED` | Target hiện tại | Target hiện tại |

Đây là lý do **khi nâng Hibernate phải chạy lại integration test về historical association**, không chỉ kiểm tra compile.

Tham khảo chính thức: [Hibernate ORM 7.3 Migration Guide — Envers association not-audited target mode](https://docs.hibernate.org/orm/7.3/migration-guide/).

## 10. Đích hiện tại đã bị xóa: rủi ro của NOT_AUDITED

Giả sử audit row của Order#100 ở R1 vẫn chứa:

```text
category_id = 9
```

Nhưng `ProductCategory#9` đã bị xóa khỏi bảng live:

```sql
DELETE FROM product_categories WHERE id = 9;
```

Quan hệ lịch sử vẫn biết ID=9, nhưng target hiện tại không còn.

Tùy cấu hình Envers và mapping, khi truy cập association có thể xảy ra:

- `EntityNotFoundException` hoặc lỗi load tương ứng.
- `null` nếu đã chọn chế độ bỏ qua target không tồn tại.
- Khác biệt lazy/eager loading và query behavior.

**Không mặc định historical relation luôn có thể traverse được khi target không audited đã hard-delete.**

### 10.1. Cách 1: giữ reference data, không hard-delete

Với bảng dictionary, có thể dùng:

```java
@Column(nullable = false)
private boolean active;
```

Thay vì DELETE, đánh dấu `active=false` và giữ row để historical references còn resolve được.

Điều này giúp giữ identity, nhưng không tự giải quyết vấn đề label đã đổi; historical owner vẫn nhìn current label.

### 10.2. Cách 2: chỉ rõ missing-target policy

Hibernate Envers các phiên bản hiện đại có thuộc tính trong `@Audited`:

```java
@Audited(
    targetAuditMode = RelationTargetAuditMode.NOT_AUDITED,
    targetNotFoundAction =
        org.hibernate.envers.RelationTargetNotFoundAction.IGNORE
)
@ManyToOne(fetch = FetchType.LAZY)
private ProductCategory category;
```

Ý định: khi target không tìm thấy, bỏ qua thay vì ném exception trong hoàn cảnh Envers áp dụng policy này. Cần kiểm chứng version chính xác vì API/policy có thành phần `@Incubating` và cài đặt/legacy behavior có thay đổi.

Cách khác được Hibernate documentation mô tả:

```java
@org.hibernate.annotations.NotFound(
    action = org.hibernate.annotations.NotFoundAction.IGNORE
)
```

Với to-one association, `@NotFound(IGNORE)` có thể dẫn đến **implicit eager fetching**, ảnh hưởng performance. Không bật `IGNORE` như cách che một lỗi dữ liệu đáng lẽ phải được báo.

### 10.3. Không biến “đích đã bị xóa” thành null mà bỏ qua nghiệp vụ

Nếu chứng từ pháp lý buộc hiển thị tên đối tác tại thời điểm ký, `null` không phải lịch sử đúng. Cần audit đối tác hoặc lưu immutable snapshot, không chỉ đổi exception thành null.

## 11. `@NotAudited` trên một quan hệ nghĩa là gì?

Ví dụ:

```java
@Audited
@Entity
class SupportTicket {

    @ManyToOne
    @NotAudited
    private Employee lastViewer;
}
```

Trường `lastViewer` không thuộc history contract của SupportTicket. Lịch sử của ticket không hứa biết ai là người cuối xem ở một revision trước đó.

Điều này phù hợp với:
- Thông tin cache/technical.
- Last-viewed, last-indexed.
- Association phục vụ presentation nhưng không liên quan audit.
- Dữ liệu dễ gây dư thừa hoặc thay đổi rất thường xuyên.

Không nên dùng `@NotAudited` cho:
- Owner của hợp đồng cần audit.
- Người phê duyệt giao dịch.
- Tài khoản được charge.
- Quan hệ nguồn ảnh hưởng số tiền đã ghi nhận.

Nếu business vẫn cần biết historical relationship ID, `@NotAudited` không phải lựa chọn đúng.

## 12. `@AuditOverride`: thay đổi phạm vi trên superclass/embeddable

Một application có các shared fields:

```java
@MappedSuperclass
public abstract class AuditableBase {

    @Column(name = "created_by")
    protected String createdBy;

    @Column(name = "last_indexed_at")
    protected Instant lastIndexedAt;
}
```

Nếu subclass được `@Audited`, có thể muốn override auditing một thuộc tính thừa hưởng:

```java
@Entity
@Audited
@AuditOverride(
    forClass = AuditableBase.class,
    name = "lastIndexedAt",
    isAudited = false
)
public class PurchaseOrder extends AuditableBase {
    // ...
}
```

Ví dụ tập trung vào `@AuditOverride`; class thực tế vẫn cần `@Id` và các mappings khác.

Annotation này còn hữu ích cho attributes trong `@Embeddable` theo cách Hibernate Envers hỗ trợ. Không cần đưa toàn bộ superclass vào audit chỉ vì một field trong đó quan trọng.

### 12.1. Ranh giới audit nên được review như schema contract

Nếu một superclass thêm `metadataJson` chứa thông tin nhạy cảm, việc mọi subclass đều annotated `@Audited` có thể vô tình đưa nội dung đó vào audit tables.

Hãy review fields mới theo chính sách:
- Có cần lịch sử không?
- Có chứa PII/secrets không?
- Có retention requirement không?
- Có ảnh hưởng kích thước audit tables không?
- Có migration audit schema tương ứng không?

## 13. `@ManyToOne`: FK và target version

Một `Order` có:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

Nếu `Order` và `Customer` audited:

```text
Order_AUD:
  order_id, revision, customer_id, ...

Customer_AUD:
  customer_id, revision, display_name, ...
```

Đọc `Order` ở R20 thường cần:

1. Xác định phiên bản Order hiện hành tại R20 từ `Order_AUD`.
2. Lấy `customer_id` ở phiên bản đó.
3. Resolve phiên bản Customer có hiệu lực tại R20.
4. Khi association được truy cập, hydrate Customer history state, không phải `customers` current row.

Nếu `targetAuditMode = NOT_AUDITED`, bước 3 đổi thành **đọc current Customer**.

### 13.1. Association FK thay đổi cũng là thay đổi lịch sử

Giả sử:

```text
R10: Order#100.customer_id = 42
R14: Order#100.customer_id = 43
```

Muốn điều tra “khách hàng nào được gán đơn trước khi chuyển?”, history của FK là thông tin có giá trị.

Nhưng nếu `Order.customer` bị `@NotAudited`, Envers không bảo đảm lưu chuyển đổi này.

## 14. `@OneToOne`: cần phân biệt owning và inverse side

Một quan hệ one-to-one:

```java
@Entity
@Audited
public class OrderPayment {

    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id", unique = true)
    private PurchaseOrder order;
}
```

Nếu cả OrderPayment và PurchaseOrder đều audited, FK `order_id` trên owning side là một phần thông tin quan hệ cần kiểm tra khi dựng history.

Với inverse side:

```java
@OneToOne(mappedBy = "order")
private OrderPayment payment;
```

Hibernate có thể cần query/audit metadata để dựng quan hệ tại revision. Không giả định tất cả các biến thể one-to-one đều có cùng performance hoặc schema audit.

### 14.1. Shared primary key one-to-one

`@MapsId` có thể khiến ID của dependent entity được chia sẻ với principal. Nếu dependent audited mà principal không audited, khi reconstruct history vẫn phải quyết định target audited/current và khả năng principal bị xóa.

Không dùng việc “PK giống nhau” như một cơ chế thay thế auditing of relationship meaning.

## 15. `@OneToMany(mappedBy=...)`: inverse collection và owning side

Quan hệ thường gặp:

```java
@Entity
@Audited
public class PurchaseOrder {

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();
}
```

```java
@Entity
@Audited
public class OrderLine {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;
}
```

`OrderLine.order` là **owning side của FK**. Việc thay đổi quan hệ cần được thực hiện nhất quán trên cả hai phía của Java object graph.

```java
public void addLine(OrderLine line) {
    lines.add(line);
    line.setOrder(this);
}
```

Nếu chỉ:

```java
order.getLines().add(line);
```

mà không cập nhật owning side, Hibernate có thể không lưu FK như application mong muốn. Envers không thể “ghi đúng lịch sử” cho một quan hệ mà ORM mapping được sử dụng sai.

### 15.1. History của collection membership

Khi thêm line:

```text
R1: Order#100 lines = {Line#1}
R5: Order#100 lines = {Line#1, Line#2}
R8: Order#100 lines = {Line#2}
```

Với mapping/Envers configuration hỗ trợ, đọc order ở R5 cần cho phép xác định tập lines tương ứng với R5.

Quan hệ history không phải List Java được serialize nguyên vẹn vào một cell; Envers dựng nó từ các audit rows/audit association metadata liên quan.

### 15.2. Collection change có thể tạo revision ở inverse side

Hibernate Envers có setting:

```properties
org.hibernate.envers.revision_on_collection_change=true
```

mặc định thường là `true`, quy định revision generation khi một relation field không sở hữu được thay đổi theo các trường hợp Envers theo dõi.

Không suy từ “parent không đổi scalar fields” rằng parent không thể có audit revision liên quan collection. Ngược lại, cấu hình này không bảo đảm mọi thao tác thay đổi Java List sai owning side đều có SQL/ history hợp lệ.

## 16. `orphanRemoval` và `CascadeType.REMOVE` trong history

Ví dụ:

```java
order.removeLine(line);
```

với `orphanRemoval=true`, Hibernate có thể xóa OrderLine entity khi flush. Với audited OrderLine, Envers thường ghi revision kiểu DELETE của child theo những entity lifecycle actions được xử lý.

Điều cần phân biệt:

- **Xóa membership** khỏi collection.
- **Xóa entity đích**.
- **Chuyển entity đích sang parent khác**.
- **Đánh dấu inactive mà không hard-delete**.

Bốn nghiệp vụ có lịch sử khác nhau.

Nếu một Line chuyển từ Order A sang Order B, lịch sử cần ghi **old FK/new FK** theo owning side. Nếu orphan removal lỡ xóa Line thay vì move, không còn đúng business event, dù audit tables có nhiều rows.

### 16.1. Đừng dùng cascade remove qua shared reference

Một `ManyToMany` hay `ManyToOne` tới entity dùng chung không nên cascade REMOVE tùy tiện. Điều đó có thể xóa dữ liệu của người khác và tạo lịch sử khó giải thích.

Lịch sử Envers ghi lại cái ORM đã làm; nó không xác nhận thao tác đó đúng nghiệp vụ.

## 17. `@OneToMany + @JoinColumn` và `@AuditJoinTable`

Có một kiểu mapping:

```java
@Entity
@Audited
public class Organization {

    @Id
    private Long id;

    @OneToMany
    @JoinColumn(name = "organization_id")
    private List<Office> offices;
}
```

Trường hợp **unidirectional `@OneToMany` có `@JoinColumn`** dùng FK column trên bảng child, nhưng association được quản lý từ phía collection. Envers documentation giải thích trong một số mapping này, Envers cần thêm **audit join table** để giữ history chính xác của membership, nhất là khi child entity state không tạo revision tương ứng với mọi membership change.

Có thể cấu hình tên audit join table:

```java
@OneToMany
@JoinColumn(name = "organization_id")
@AuditJoinTable(
    name = "organization_offices_AUD"
)
private List<Office> offices;
```

`@AuditJoinTable` thuộc:

```java
org.hibernate.envers.AuditJoinTable
```

Mẫu này minh họa annotation và mục đích; `Office` có audited hay không, FK ownership, schema, collection type và cấu hình Envers cần được xác định rõ trong mô hình thực tế.

### 17.1. Audit join table không đồng nghĩa bảng join nghiệp vụ

Có thể database nghiệp vụ chỉ có:

```text
office.organization_id
```

nhưng Envers vẫn dùng một bảng lịch sử liên kết như:

```text
organization_offices_AUD
```

để phục vụ truy hồi collection membership theo revision.

**Không tự thêm `@JoinTable` vào JPA mapping chỉ vì thấy Envers có audit join table.** Hai quyết định này độc lập: một bên là relational mapping hiện tại, bên kia là storage của lịch sử.

### 17.2. Vì sao không chọn `@AuditJoinTable` cho mọi collection?

Không phải mọi `@OneToMany(mappedBy=...)` hoặc `@ManyToMany` đều cần annotation này. Dùng khi mô hình Envers thực sự tạo audit join table bổ sung và bạn cần cấu hình name/schema/inverse join columns.

Trước khi thêm, hãy kiểm tra generated Envers schema cho **đúng collection mapping**, test revision membership và migrations thật.

## 18. `@AuditMappedBy`: “fake bidirectional” và giới hạn

Một kiểu mapping ít gặp dùng:

- `@OneToMany` + `@JoinColumn` trên one side.
- `@ManyToOne` ở many side với mapping FK read-only (`insertable=false, updatable=false`).
- Trong ngữ nghĩa JPA/Hibernate, collection vẫn là owning side, còn many side giống một association read-only theo FK.

Hibernate Envers có `@AuditMappedBy` để mô tả reverse property cho trường hợp “fake bidirectional” này, giúp audit membership theo cách gần với bidirectional relation thông thường.

Ví dụ cấu trúc:

```java
@OneToMany
@JoinColumn(name = "organization_id")
@AuditMappedBy(mappedBy = "organization")
private List<Office> offices;
```

`Office.organization` trong trường hợp đặc biệt này phải được mapping theo yêu cầu của `@AuditMappedBy`; không áp dụng annotation này tùy tiện cho **bidirectional standard** vốn đã có `mappedBy` ở collection.

### 18.1. `@AuditMappedBy` là Hibernate-specific và experimental

Theo Hibernate Javadoc, annotation này được coi là experimental. Một số biến thể có `positionMappedBy` cho indexed collections dùng `@OrderColumn`.

Nếu không thật sự có “fake bidirectional” mapping, hãy ưu tiên association mapping JPA tiêu chuẩn. Dùng `@AuditMappedBy` nghĩa là phải kiểm thử rất kỹ trên đúng Hibernate major version.

## 19. `@ManyToMany`: lịch sử của bảng liên kết

Ví dụ Customer và Tag đều audited:

```java
@Entity
@Audited
public class Customer {

    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "customer_tags",
        joinColumns = @JoinColumn(name = "customer_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private Set<Tag> tags = new HashSet<>();
}
```

```java
@Entity
@Audited
public class Tag {

    @Id
    private Long id;

    private String label;
}
```

Trong database live:

```text
customer_tags
  customer_id | tag_id
        42    |  7
        42    |  9
```

Khi membership thay đổi, audit storage cần thể hiện mối liên kết tại các revisions. Envers có thể dùng audit join table cho loại relation này theo mapping/config.

Cần phân biệt:
- Tag#7 tồn tại và có label `VIP`.
- Customer#42 có Tag#7 tại R10.
- Tag#7 đổi label tại R15.
- Customer#42 bỏ Tag#7 tại R20.

Nếu **Tag audited**, historical graph ở R10 có thể truy hồi label Tag ở R10.

Nếu **Tag không audited** và association dùng `targetAuditMode=NOT_AUDITED`, lịch sử membership có thể vẫn xác định tag ID, nhưng label được lấy từ Tag live hiện tại.

### 19.1. Không cascade remove trên ManyToMany dùng chung

```java
@ManyToMany(cascade = CascadeType.REMOVE)
```

rất dễ xóa `Tag` dùng chung bởi nhiều Customer. Xóa một link không nên đồng nghĩa xóa Tag entity.

Đây là quy tắc relational/business, không chỉ quy tắc Envers.

## 20. Collection có phần tử không audited

Giả sử `ProductCategory` là dictionary không audited, còn `Product` audited có nhiều category tags.

Có thể cần audit **tập category IDs gắn với product**, nhưng không audit từng row ProductCategory.

Để thiết kế đúng, cần:
1. Cho collection association thuộc audit contract.
2. Chọn `targetAuditMode=NOT_AUDITED` nơi được Envers hỗ trợ.
3. Bảo đảm storage lịch sử membership/ join table phù hợp.
4. Không hard-delete reference rows nếu historical traversal còn cần chúng.
5. Test các thao tác add/remove/reassign ở những revisions cụ thể.
6. Kiểm tra version behavior và các mapping exceptions với collection type.

Không suy luận rằng “target không audit thì collection không thể audit” hoặc “target không audit thì tất cả mọi kiểu collection tự hoạt động”. Hỗ trợ phụ thuộc mapping cụ thể.

## 21. Element collection và value objects

`@ElementCollection` không có identity entity riêng, ví dụ:

```java
@ElementCollection
@CollectionTable(
    name = "order_labels",
    joinColumns = @JoinColumn(name = "order_id")
)
@Column(name = "label")
private Set<String> labels = new HashSet<>();
```

Nếu owner được audit và mapping được Envers hỗ trợ, collection values/membership có thể được lưu trong audit collection table tương ứng.

Khác với một relation tới non-audited entity:

- `String` trong element collection là **giá trị**, không có row entity riêng để resolve current state.
- Một `@Embeddable` có các basic fields được xem là value object snapshot theo mapping hỗ trợ.
- Một entity trong `@ManyToOne` có identity/lifecycle độc lập và cần target resolution.

Vì vậy, nếu chỉ cần giữ một số nhãn/giá trị bất biến theo phiên bản, element collection hoặc field snapshot có thể đơn giản hơn một lịch sử quan hệ phức tạp.

### 21.1. Equality của value objects ảnh hưởng membership

Với `Set<Embeddable>`, cách Hibernate theo dõi thay đổi và Envers audit collection phụ thuộc equals/hashCode, mutability và collection semantics. Không thay đổi một key/hash field sau khi object đã nằm trong HashSet.

## 22. `@OrderColumn` và collection order history

Một `List<OrderLine>` có:

```java
@OrderColumn(name = "line_position")
private List<OrderLine> lines;
```

thì **vị trí** có thể là dữ liệu persistent. Thay đổi thứ tự danh sách có thể tạo collection DML và lịch sử position tương ứng theo mapping Envers.

Điều cần xác định:
- Order có ý nghĩa nghiệp vụ hay chỉ UI sort?
- Position nằm ở column nào?
- Kéo thả thứ tự có phải tạo revision không?
- Một xóa line có reindex các line còn lại?
- Audit join table/collection mapping có ghi position đúng không?

Không dùng vị trí tự nhiên của SQL rows để suy ra thứ tự lịch sử: SQL không cam kết row order nếu không có `ORDER BY`.

## 23. Revision lịch sử không phải “mọi trạng thái trung gian”

Ví dụ trong một transaction:

```java
order.setStatus("DRAFT");
em.flush();

order.setStatus("PAID");
em.flush();

tx.commit();
```

Envers thường nhóm các audited changes theo revision/transaction semantics của nó. Không nên kỳ vọng mỗi lệnh setter hoặc mỗi lần flush đều trở thành một revision **độc lập và có thể truy vấn**.

Nếu nghiệp vụ cần lưu mọi chuyển trạng thái `DRAFT -> VALIDATING -> PAID` dù chúng diễn ra trong một transaction, nên có một **domain event/history model** riêng ghi nhận từng hành động.

Envers chủ yếu phục vụ database entity versioning theo transaction revision, không thay thế event sourcing.

## 24. Revision number và thời điểm: khác nhau

AuditReader:

```java
import org.hibernate.envers.AuditReader;
import org.hibernate.envers.AuditReaderFactory;

AuditReader reader = AuditReaderFactory.get(em);
```

Một revision number là mốc logic của Envers. Nó không nhất thiết là timestamp của một entity riêng.

Để lấy các revisions cho một entity:

```java
List<Number> revisions =
    reader.getRevisions(PurchaseOrder.class, 100L);
```

Để đọc state as-of một revision:

```java
PurchaseOrder historical =
    reader.find(PurchaseOrder.class, 100L, revision);
```

`find()` thường chọn phiên bản có hiệu lực tại revision chỉ định, không bắt buộc phải có một audit row với `REV` **bằng chính xác** revision đó.

### 24.1. Khi nào không tìm thấy entity?

Nếu entity chưa tồn tại ở revision được hỏi hoặc đã bị delete tại/before revision đó, `find()` có thể trả null theo contract/history semantics. Không coi null là “không có audit table” khi không có bằng chứng.

### 24.2. Lấy revision timestamp

Envers có API lấy revision date/number mappings và có revision entity chứa timestamp. Đừng lấy `Instant.now()` tại thời điểm đọc rồi gắn cho lịch sử.

Tính nhất quán **theo revision** khác yêu cầu pháp lý “snapshot đúng UTC timestamp T” khi transaction overlap/multiple databases; cần xem business requirement và metadata recording.

## 25. Dựng historical graph bằng `AuditReader`

Ví dụ:

```java
AuditReader reader = AuditReaderFactory.get(em);

Number rev = 12;
PurchaseOrder oldOrder =
    reader.find(PurchaseOrder.class, 100L, rev);

if (oldOrder != null) {
    Customer historicalCustomer = oldOrder.getCustomer();
    ProductCategory currentCategory = oldOrder.getCategory();
    List<OrderLine> historicalLines = oldOrder.getLines();
}
```

Ý nghĩa mong muốn:

- `oldOrder` là historical PurchaseOrder snapshot.
- `historicalCustomer` được resolve theo revision khi relation audited mặc định.
- `currentCategory` là ProductCategory **live** vì `targetAuditMode=NOT_AUDITED`.
- `historicalLines` phản ánh collection history nếu mapping audited và được hỗ trợ.

**Không xem kết quả của `AuditReader.find()` như một entity managed bình thường để tiếp tục cập nhật.** Nó đại diện history state, không phải một transactional aggregate hiện tại. Nếu cần sửa current order, dùng `em.find(PurchaseOrder.class, id)` trong unit of work mới phù hợp.

### 25.1. Lazy loading và N+1 với lịch sử

Historical associations có thể phát thêm SQL truy vấn audit tables hoặc live tables. Lặp:

```java
for (PurchaseOrder order : histories) {
    order.getCustomer().getDisplayName();
    order.getCategory().getDisplayName();
}
```

có nguy cơ N+1, đặc biệt khi non-audited target cần đọc live rows. Cần đo SQL thực tế, có thể dùng revisions query/projection và ánh xạ DTO phù hợp.

Đừng vội coi graph lịch sử của Envers tương đương với một `JOIN FETCH` JPQL thông thường; AuditQuery có giới hạn API/traversal riêng.

## 26. Truy vấn lịch sử theo khóa liên kết

Nếu muốn tìm các revisions/order snapshots có Customer ID cụ thể, Envers `AuditEntity` có các toán tử cho association ID.

Ví dụ định hướng:

```java
import org.hibernate.envers.query.AuditEntity;

var auditQuery = reader.createQuery()
    .forRevisionsOfEntity(PurchaseOrder.class, false, true)
    .add(
        AuditEntity.relatedId("customer").eq(42L)
    );

List<?> raw = auditQuery.getResultList();
```

Khi dùng `forRevisionsOfEntity(entityClass, false, true)`, mỗi result thường có dạng tuple `Object[]` gồm entity snapshot, revision entity và `RevisionType`; với `selectEntitiesOnly=true` thì result shape khác.

### 26.1. `relatedId()` không có nghĩa join toàn bộ graph lịch sử

`relatedId("customer")` so association key, không tự đọc mọi audited properties của Customer và không tự bảo đảm hỗ trợ mọi quan hệ phức tạp.

Khả năng truy vấn qua association (*relation traversal*) đã được mở rộng ở một số Hibernate versions, nhưng vẫn có mapping/operator limits. Khi cần lọc tên Customer tại revision R, phải thử đúng AuditQuery API/SQL của phiên bản triển khai.

### 26.2. Kiểm tra cả owner revision và target revision

Nếu một Customer đổi tên R11 mà PurchaseOrder không thay đổi, `getRevisions(PurchaseOrder, id)` không nhất thiết chứa R11.

Tuy nhiên, đọc **PurchaseOrder tại R11** với audited target có thể trả Customer name ở R11, vì target history được chọn theo revision. Đây là khác biệt quan trọng giữa:
- **Các revision của owner**.
- **Trạng thái của graph owner + target as-of một revision**.

## 27. Chênh lệch giữa owner revisions và associated revisions

Ví dụ:

```text
R1: Order#100 được tạo với Customer#42 ("An")
R2: Customer#42 đổi tên thành "An Nguyễn"
R3: Order#100 đổi status thành PAID
```

Audit tables có thể là:

```text
Order_AUD:
  R1, R3

Customer_AUD:
  R1 (hoặc revision riêng trước đó), R2
```

Truy vấn:

```java
reader.getRevisions(PurchaseOrder.class, 100L);
```

có thể trả `[R1, R3]`, không bao gồm R2 vì Order không có thay đổi trong transaction R2.

Nhưng:

```java
PurchaseOrder asOfR2 =
    reader.find(PurchaseOrder.class, 100L, R2);
```

có thể trả Order version R1 và resolve Customer version R2.

Đây là lý do “owner không tạo revision mới” không đồng nghĩa “historical graph không thể thay đổi giữa hai revision numbers toàn cục”, nếu target audited thay đổi.

## 28. Audit strategy: Default vs Validity

Hibernate Envers hỗ trợ các audit strategies chính:

1. **DefaultAuditStrategy**: dùng revision bắt đầu; query lịch sử thường cần subquery để tìm bản ghi có REV lớn nhất không vượt quá revision mục tiêu.
2. **ValidityAuditStrategy**: lưu revision bắt đầu và **revision kết thúc** (`REVEND` theo mặc định) để xác định interval hiệu lực.

Minh họa:

```text
Default:
  id=100, REV=1, status=DRAFT
  id=100, REV=9, status=PAID

Validity:
  id=100, REV=1, REVEND=9,  status=DRAFT
  id=100, REV=9, REVEND=NULL, status=PAID
```

`ValidityAuditStrategy` có thể giúp một số historical range queries và joins, nhưng tăng chi phí cập nhật audit rows khi phiên bản mới xuất hiện. Nó không làm non-audited target có lịch sử.

### 28.1. Chọn strategy trước khi triển khai lâu dài

Chuyển giữa Default và Validity sau khi đã có audit history cần migration/backfill audit metadata hợp lệ. Không chỉ thay:

```properties
org.hibernate.envers.audit_strategy=...
```

rồi mong Hibernate tự chuyển đổi hàng triệu audit rows.

### 28.2. Chi phí khi nhiều quan hệ được audit

Historical graph query có thể cần:
- Một audit query cho owner.
- Audit queries cho các to-one targets.
- Audit join/collection queries.
- Entity audit queries cho children.
- Live table queries cho non-audited targets.

Thêm nhiều audited associations có thể làm storage, write amplification và read latency tăng đáng kể. Cần thiết kế scope dựa trên yêu cầu thực tế.

## 29. Delete revision và `store_data_at_delete`

Với entity audited bị xóa, Envers thường ghi audit row có `RevisionType.DEL`.

Theo cấu hình mặc định phổ biến:

```properties
org.hibernate.envers.store_data_at_delete=false
```

những thuộc tính khác ID ở delete revision có thể không được lưu lại đầy đủ trong chính row DEL. Có thể bật:

```properties
org.hibernate.envers.store_data_at_delete=true
```

để ghi các giá trị entity khi delete theo Envers configuration.

Hệ quả:

- Tăng storage ở delete events.
- Dễ truy vấn một số thông tin tại revision xóa.
- Không tự đảm bảo associated non-audited target còn tồn tại.
- Không tự giải quyết retention hoặc privacy requirements.
- Không biến Envers thành immutable forensic log nếu DBA có quyền sửa bảng audit.

### 29.1. Hard delete và historical foreign keys

Một bảng `Order_AUD` có thể lưu `customer_id=42` dù bảng `customers` hiện tại không còn row #42. Điều này **bình thường với lịch sử**, vì historical reference không nhất thiết phải có foreign key constraint sang bảng live.

Đừng áp FK từ mọi audit association tới live target mà không xét khả năng target bị xóa hợp lệ. Với audited target, lịch sử của nó có thể vẫn tồn tại; với non-audited target, cần policy preserve row/soft-delete/snapshot.

## 30. Dùng `withModifiedFlag` để biết field nào đã đổi

Một entity audited:

```java
@Audited(withModifiedFlag = true)
@Entity
public class PurchaseOrder {
    // ...
}
```

cho phép Envers lưu các modified flags cho những properties được audit theo cấu hình hỗ trợ, thường dưới dạng columns có hậu tố `_MOD`.

Ý tưởng:

```text
Order_AUD:
  REV | customer_id | customer_MOD | status | status_MOD
   1  |      42     |     true     | DRAFT  |    true
   5  |      43     |     true     | DRAFT  |    false
   8  |      43     |     false    | PAID   |    true
```

Các tên `_MOD` và cột thực tế tùy naming strategy/config.

Bạn có thể query:

```java
reader.createQuery()
    .forRevisionsOfEntity(PurchaseOrder.class, false, true)
    .add(AuditEntity.property("status").hasChanged())
    .getResultList();
```

### 30.1. Modified flags không thay dữ liệu lịch sử

Flag nói một property được coi là thay đổi ở revision tương ứng, không phải tự lưu một bảng “oldValue/newValue” cho mọi field. Muốn biết giá trị trước/sau, so các snapshots ở những revisions thích hợp.

Với collection, modified flags và revision-on-collection-change có semantics đặc thù; phải test trên đúng mapping nếu dùng flags để kết luận có thêm/bớt phần tử.

## 31. Bảng lịch sử và migration schema

Dự án dùng Flyway/Liquibase không nên để Hibernate `ddl-auto=update` tự tạo/sửa audit tables trên production không qua review.

Một sơ đồ cơ bản:

```text
purchase_orders
purchase_orders_AUD
order_lines
order_lines_AUD
customers
customers_AUD
product_categories
REVINFO
```

Thực tế có thể có thêm:
- Audit join table.
- Audit collection table.
- Sequence/index/constraint phục vụ revision metadata.
- `REVEND`, `REVEND_TSTMP` cho Validity strategy.
- Các modified flag columns.
- Audit tables cho secondary tables/embeddables.

### 31.1. Migration phải cập nhật cả bảng live và bảng audit

Nếu thêm audited field:

```java
@Column(name = "approved_by")
private String approvedBy;
```

thì schema cần có column mới trong bảng entity **và cấu trúc audit tương ứng** theo Envers mapping.

Nếu chuyển field sang `@NotAudited`, không tự xóa các audit columns/history cũ. Muốn drop historical data, cần migration/retention decision có review.

### 31.2. Test tạo schema từ Envers để tham khảo, không auto-apply prod

Có thể tạo reference schema bằng Hibernate schema tooling trên database test riêng để nhận diện những audit objects cần thiết, rồi viết/review Flyway migrations tương ứng.

Không thay `ddl-auto=validate` thành `create-drop` trên database có dữ liệu thật. Schema generated có thể thay đổi theo Hibernate version/naming strategy; cần snapshot/diff trước upgrade.

## 32. Bắt đầu audit một entity đã có hàng triệu rows

Nếu trước đây `PurchaseOrder` không audited, rồi hôm nay thêm `@Audited`, Envers **không tự dựng lại lịch sử đã xảy ra trước hôm nay**.

Ví dụ:

```text
2019–2025: Order được cập nhật nhiều lần, không audit
2026:    Bật Envers
2026+:   Các thay đổi ORM-supported bắt đầu được ghi
```

Không thể từ bảng current suy ra mọi customer reassignment, price changes, deleted rows của quá khứ.

Những lựa chọn:

- Chấp nhận “audit starts at deployment date”.
- Tạo **baseline revision** thể hiện current state tại thời điểm bắt đầu (cần thiết kế carefully).
- Import dữ liệu từ một nguồn lịch sử đáng tin cậy khác nếu có.
- Dùng domain event log/CDC sẵn có để backfill khi có đầy đủ dữ liệu.

Không tự INSERT vào các audit tables/REVINFO một cách tùy tiện mà không hiểu revision number, composite keys, revision type và audit strategy.

### 32.1. Có thể audit owner trước, target sau không?

Nếu Order được audit từ R1 nhưng Customer bắt đầu audited từ R10:

- Quan hệ ở R5 có thể chứa customer ID.
- Customer không có history trước R10.
- Historical target resolution ở R5 có thể thất bại hoặc không có snapshot theo semantics.

Không giả định chỉ cần thêm `@Audited` sau này là toàn bộ historical graph trước đó trở nên đầy đủ.

## 33. Những thay đổi Envers không nhìn thấy

Một bulk update:

```java
em.createQuery("""
    update PurchaseOrder o
    set o.status = :newStatus
    where o.status = :oldStatus
    """)
    .setParameter("newStatus", "PAID")
    .setParameter("oldStatus", "DRAFT")
    .executeUpdate();
```

có thể sửa nhiều rows trực tiếp bằng SQL mà không phát lifecycle events cho từng entity.

**Envers không ghi nhận đầy đủ các bulk JPQL/HQL/CriteriaUpdate/Delete/native SQL như những managed entity changes thông thường.**

Nếu yêu cầu mọi trạng thái phải có lịch sử:
- Tránh bulk DML cho audited data, hoặc
- Ghi audit manually bằng một cơ chế được thiết kế, hoặc
- Dùng database triggers/CDC, hoặc
- Đưa tất cả writes qua một service layer có audit contract được kiểm soát.

### 33.1. Lifecycle với database cascades

Nếu database dùng `ON DELETE CASCADE`, một parent DELETE có thể làm database tự xóa child rows. Hibernate Envers không nhất thiết nhận entity delete events cho từng child bị database xóa.

Không dựa vào audit listeners của Hibernate để chứng minh mọi DB-side cascade delete có đầy đủ child audit records.

## 34. Envers là versioning, không phải event sourcing

So sánh:

| Khía cạnh | Envers | Event sourcing |
| --- | --- | --- |
| Đơn vị cơ bản | Entity snapshots/changes theo revision | Domain events |
| Câu hỏi mạnh | Entity trông thế nào ở revision R? | Những hành động nghiệp vụ nào đã xảy ra? |
| Ý nghĩa transaction | Revision gắn với audited changes | Event append/stream semantics |
| Ranh giới | Các entities/properties được audit | Các events được domain định nghĩa |
| Quan hệ tới target non-audited | Có thể trỏ current state | Phụ thuộc event payload và projection |
| Bulk/external writes | Không tự bao phủ | Nếu bypass event store cũng không bao phủ |
| Tái dựng trạng thái | Envers AuditReader | Replay events/projectors |
| Yêu cầu thiết kế | ORM mapping và audit schema | Event schema, ordering, idempotency |

Nếu bài toán chỉ cần xem lại entity state và lịch sử thay đổi qua Hibernate, Envers là giải pháp phù hợp. Nếu cần biết “ai phê duyệt”, “vì sao chuyển trạng thái”, “thao tác đã được yêu cầu rồi bị từ chối” hoặc “đã gửi email chưa”, cần domain events/audit log riêng.

## 35. Ranh giới bảo mật và dữ liệu nhạy cảm

Không nên `@Audited` vô điều kiện mọi field.

Ví dụ:

```java
@Entity
@Audited
public class Account {

    @Id
    private Long id;

    private String displayName;

    @NotAudited
    private String passwordHash;

    @NotAudited
    private String passwordResetToken;
}
```

`@NotAudited` cho password/reset token là một lựa chọn cơ bản để tránh lịch sử hóa bí mật. Tuy nhiên còn phải kiểm tra:
- Value có được nhúng vào một field khác/JSON payload được audit không?
- Logs/CDC/backup có giữ thông tin đó không?
- Envers audit tables từ **trước khi thêm `@NotAudited`** có còn chứa dữ liệu nhạy cảm không?
- Chính sách retention và xóa dữ liệu có áp dụng lên audit tables không?
- Ai được quyền query AuditReader hoặc xem audit schema trực tiếp?

### 35.1. `@NotAudited` mới không xóa lịch sử cũ

Nếu trước đây field `secret` đã audited, việc thêm:

```java
@NotAudited
private String secret;
```

hôm nay chỉ thay audit contract tương lai. Các audit rows đã lưu trước đó có thể vẫn giữ secret. Muốn xử lý dữ liệu lịch sử phải có remediation/retention migration riêng, tùy yêu cầu pháp lý và nghiệp vụ.

### 35.2. Kiểm tra quyền khi xem lịch sử

Người không được quyền xem current Order không đương nhiên được xem historical Order. AuditReader query vẫn cần authorization và tenant scoping.

Không cho phép một API kiểu:

```text
GET /orders/{id}/revisions/{revision}
```

trả dữ liệu chỉ dựa vào ID+revision mà bỏ qua permission checks. Lịch sử có thể chứa thông tin đã bị chỉnh sửa/xóa khỏi UI hiện tại vì lý do bảo mật.

## 36. Multi-tenant và revision namespace

Envers revision number thường liên quan persistence unit/schema/database audit metadata. Với multi-tenant hệ thống:

- Tenants dùng database/schema riêng có thể có `REVINFO` riêng.
- Tenants dùng shared tables cần audit rows và query isolation đúng theo tenant model.
- Một revision number **không nhất thiết là định danh toàn cục** giữa nhiều databases/persistence units.
- Không xây API lấy revision của tenant A rồi đọc audit rows của tenant B.
- Audit table partitioning, retention và index design cần tính đến tenant cardinality.

### 36.1. Non-audited target có thể gây cross-tenant leakage

Một historical Order của tenant A trỏ `category_id=9`. Nếu live Category có ID trùng tenant hoặc một custom resolver quên tenant key, `NOT_AUDITED` lookup có thể trả sai dữ liệu tenant.

Không tự suy Envers/association mapping đã xử lý đầy đủ mọi application-specific tenant isolation. Test thực tế phải bao gồm hai tenants có trùng logical IDs nếu model cho phép.

## 37. Lịch sử có thể không đồng nhất qua nhiều databases

Nếu PurchaseOrder ở DB A được audit, nhưng ProductCatalog ở DB B không audited, `Order.category` có thể chỉ được ứng dụng join/resolve bằng service call chứ không phải JPA association trong một persistence unit.

Ngay cả khi các nguồn đều có lịch sử, “R10” ở DB A không có nghĩa tương đương “R10” ở DB B.

Nếu yêu cầu một **cross-service consistent snapshot**, cần:
- Temporal versioning/version IDs có thể tương quan.
- Event/transaction ordering metadata.
- Immutable snapshots theo aggregate/business document.
- Distributed consistency model rõ ràng.
- Không giả định AuditReader giải quyết nhất quán phân tán.

## 38. Hiệu năng và kích thước audit tables

Một system có 10 triệu Orders, 5 Lines/Order và cập nhật thường xuyên có thể sinh nhiều audit rows theo thời gian.

Chi phí gồm:
- Additional INSERTs vào audit tables khi audited state thay đổi.
- Revision entity rows.
- Indexes và storage cho revision-based queries.
- Audit join tables/collection histories.
- SQL khi resolve graph lịch sử.
- VACUUM/archival/partitioning/retention.
- L2 cache/query-cache interactions.

### 38.1. Không audit collection rất lớn theo mặc định

Nếu một entity có collection hàng trăm nghìn members thay đổi thường xuyên, audit membership có thể tốn nhiều hơn giá trị nó mang lại.

Hãy hỏi:
- Có cần biết chính xác thành viên tại từng revision không?
- Có cần nội dung từng member tại revision không?
- Có thể lưu business events hoặc một snapshot tóm tắt nhỏ hơn không?
- Có yêu cầu retention bao lâu?
- AuditQuery chủ yếu đọc 1 entity hay báo cáo số lượng lớn?
- Có cần archive older revisions?

### 38.2. Query lịch sử cũng cần index

Index phù hợp thường liên quan các cột như:
- Entity identifier.
- `REV`.
- `REVEND` với Validity strategy.
- FK/join keys của audit association tables.

Cấu hình index/DDL cụ thể phụ thuộc generated audit schema và query plan của DB. Không sao chép index blind; đo `EXPLAIN` với dữ liệu thực tế.

## 39. Integration tests: nên kiểm tra ranh giới như thế nào?

Một bộ kiểm thử có giá trị phải có **ít nhất hai transactions độc lập**, một lượt thay đổi current target và một lượt truy vấn historical revisions.

Fixture đề xuất:

```text
R1: Create Customer#42 ("An")
R2: Create ProductCategory#9 ("Điện tử") [không audited]
R3: Create Order#100 with Customer#42, Category#9
R4: Customer#42 rename -> "An Nguyễn"
R5: ProductCategory#9 rename -> "Thiết bị số"
R6: Order#100 change status
R7: Add Line#1
R8: Add Line#2
R9: Remove Line#1 (orphanRemoval)
```

Chú ý R2/R5 không nhất thiết tạo **Envers revision** vì chúng chỉ thay non-audited Category. Ký hiệu R2/R5 ở đây nên hiểu là **mốc thời gian nghiệp vụ**, không mặc định có revision number tương ứng trong `REVINFO`.

Test thực tế nên lưu `Number orderCreationRev`, `Number orderUpdateRev` bằng `reader.getRevisions(...)` **sau khi transaction commit**, thay vì hard-code các revision numbers 1,2,3.

### 39.1. Test owner audited + target audited

Sau khi Customer đổi tên, đọc Order ở revision tạo trước đó:

```java
PurchaseOrder old =
    reader.find(PurchaseOrder.class, 100L, creationRevision);

assertEquals(
    "An",
    old.getCustomer().getDisplayName()
);
```

Điều kiện: Customer audited từ trước, relation mapping audited, audit schema đúng, context không có stale managed references, và test dữ liệu transaction/revision được cô lập.

### 39.2. Test owner audited + target non-audited

Sau khi Category đổi tên và commit:

```java
PurchaseOrder old =
    reader.find(PurchaseOrder.class, 100L, creationRevision);

assertEquals(
    "Thiết bị số",
    old.getCategory().getDisplayName()
);
```

Đây là behavior cần được thẩm định theo `NOT_AUDITED` target mode: old Order + current Category.

Nếu test này thất bại sau upgrade, kiểm tra Hibernate version, category cache/L1, transaction isolation và đặc biệt thay đổi behavior trong Hibernate 7.3 khi target thật ra cũng audited.

### 39.3. Test `@NotAudited` không bảo đảm history

Thay đổi `lastViewedAt` nhiều lần nhưng không thay audited properties:

- Xem Envers có tạo revision nào từ thay đổi đó không trong model/config đã chọn.
- Đọc lịch sử rồi xác nhận ứng dụng **không phụ thuộc** vào historical value của `lastViewedAt`.
- Không assert một giá trị mặc định/null cụ thể nếu không phải contract được provider hỗ trợ.

### 39.4. Test membership qua collection revisions

Thực hiện:
1. Tạo Order với Line#1, commit.
2. Thêm Line#2, commit.
3. Remove Line#1 với orphanRemoval, commit.
4. Đọc Order as-of ba revisions có thay đổi.
5. Assert sets of line IDs bằng `{1}`, `{1,2}`, `{2}` tương ứng.
6. Assert state của Line#1 ở revision trước khi delete vẫn được truy hồi theo supported semantics.

Nếu owning side không được cập nhật, test có thể phơi bày bug trong helper method trước cả Envers.

## 40. Integration test: xóa target non-audited

Flow:

1. Tạo Order audited trỏ Category#9 non-audited.
2. Commit, lấy creation revision của Order.
3. Xóa Category#9 theo quy trình cho phép (nếu FK live không chặn).
4. Mở EntityManager mới, đọc historical Order.
5. Truy cập `old.getCategory()`.
6. Kiểm tra behavior theo `targetNotFoundAction`/`@NotFound`/provider version.

Đây là test rất quan trọng vì:
- Schema live FK có thể chặn delete Category#9 nếu Order vẫn trỏ tới nó.
- Muốn hard-delete Category, business thường phải gỡ current Order relation hoặc dùng soft-delete.
- Audit row vẫn có category ID lịch sử.
- Truy cập historical target có thể ném exception hoặc trả null theo policy.

Không thiết kế test bằng cách tắt FK constraints rồi kết luận workflow production có thể xóa target hợp lệ.

### 40.1. Test rollback không có lịch sử commit

Tạo Order và flush rồi rollback:

```java
tx.begin();
em.persist(order);
em.flush();
tx.rollback();
```

Sau đó trong EntityManager khác, kiểm tra:
- Order live row không có.
- Audit rows tương ứng với transaction rollback cũng không được commit.
- Revision IDs có thể có gaps tùy generator/DB; không assert số revision liên tục.

**`flush()` không phải `commit()`** đối với cả entity data và audit data.

## 41. Testcontainers và migrations audit schema

Một project dùng PostgreSQL production nên test Hibernate + Envers với PostgreSQL trong Testcontainers thay vì chỉ H2.

Kế hoạch integration suite:

```text
Start PostgreSQL container
      |
      v
Apply Flyway/Liquibase migrations:
  main entity tables
  _AUD tables
  REVINFO
  audit join tables
      |
      v
Bootstrap Hibernate (ddl-auto=validate)
      |
      v
Write through EntityManager
      |
      v
Commit + open new EntityManager
      |
      v
AuditReader historical reads
      |
      v
Assertions for owner, target, membership,
missing target, delete, rollback
```

Test phải dùng chính audit strategy/naming/version production. Khi đổi từ Default sang ValidityAuditStrategy, hoặc đổi target audit mode, cần test migration/dữ liệu cũ chứ không chỉ test database mới hoàn toàn.

### 41.1. Đừng dùng cùng Persistence Context cho mọi bước

Khi test current target đổi nhưng historical owner dùng non-audited relation, một EntityManager vẫn giữ Category trước khi đổi trong L1 có thể khiến assertion sai/khó hiểu.

Dùng transaction/context mới ở từng bước, clear/close đúng lifecycle, và kiểm tra cache/config nếu muốn xác nhận current target semantics.

## 42. Troubleshooting: khi lịch sử quan hệ không như kỳ vọng

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Envers bootstrap lỗi vì relation target non-audited | Audited relation mặc định cần target audit | Cân nhắc `targetAuditMode=NOT_AUDITED` hoặc audit target |
| Historical Order hiện tên Category mới | Target được resolve từ live table | Đây là semantics của `NOT_AUDITED`; cần snapshot/audit nếu muốn tên cũ |
| Historical relation đột ngột trả current target sau nâng Hibernate | Hibernate 7.3 sửa behavior `NOT_AUDITED` với target audited | Xem migration guide và chỉnh expectation/test |
| `EntityNotFoundException` khi mở relation cũ | Current target non-audited đã bị xóa | Soft-delete, snapshot, hoặc missing-target policy có chủ đích |
| `@NotFound(IGNORE)` làm query nhiều hơn | To-one association bị eager checking | Đo N+1, thiết kế lại missing target |
| `@NotAudited` làm mất lịch sử FK | Loại property khỏi audit | Dùng audited relation nếu cần history |
| Thêm child nhưng history không đổi | Chưa cập nhật owning side FK | Helper đồng bộ hai phía, test SQL |
| OneToMany `@JoinColumn` cho lịch sử membership sai | Cần audit join table trong mapping đặc thù | Xem `@AuditJoinTable` và schema |
| ManyToMany thiếu member khi đọc R cũ | Audit join table/schema/mapping lệch | Test add/remove/roles/migrations |
| Customer đổi tên nhưng Order không có revision mới | Target đổi, owner không đổi | Dùng as-of global revision; không đòi owner revision |
| Bulk UPDATE không có audit history | Không đi qua entity listeners | Tránh bulk hoặc bổ sung audit layer khác |
| DB cascade xóa child không có DEL audit | Database-side work không qua entity events | Trigger/CDC hoặc ORM-controlled delete |
| AuditQuery historical graph quá chậm | Subqueries/joins/N+1/audit growth | Index, Validity strategy, DTO queries |
| `@NotAudited` không xóa secret cũ | Chỉ ảnh hưởng future audit | Data retention/remediation audit table |
| Envers revision bị gap | ID generator/rollback/concurrency | Không đòi revision number liên tục |
| Historical entity bị dùng để UPDATE | Nhầm snapshot với current managed entity | Dùng `em.find()` current và domain command |
| Tenant A thấy lịch sử tenant B | Scope/authorization thiếu | RLS/security/query scoping và tests |
| Audit tables thiếu cột mới | Migration chỉ sửa live schema | Migration audit schema và validate |
| Missing target chỉ xuất hiện trên production | Dữ liệu hard-deleted/constraints khác test | Test real DB + retention policy |
| `AuditReader` lấy R không có audit row chính xác | `find` đọc phiên bản có hiệu lực as-of R | Hiểu revision semantics |
| FK audit row trỏ entity không còn live | History giữ reference, live lifecycle khác | Không ràng FK audit tới live một cách máy móc |

## 43. Checklist thiết kế ranh giới audit

Trước khi đưa một association vào mô hình được audit, hãy trả lời:

1. **Tại sao cần lịch sử?** Điều tra, hóa đơn, khôi phục state, compliance hay chỉ debug?
2. **Cần biết relationship ID hay thuộc tính lịch sử của target?** Hai yêu cầu khác nhau.
3. **Owner có audited không? Target có audited không?**
4. **Association có cần audited không hay là field kỹ thuật `@NotAudited`?**
5. **Nếu target không audited, việc thấy current target có chấp nhận được không?**
6. **Nếu target audited nhưng muốn current semantics, Hibernate version có tôn trọng `NOT_AUDITED` không?**
7. **Target có thể bị hard-delete?** Nếu có, lịch sử resolve ra sao?
8. **Dữ liệu tài chính/pháp lý có cần immutable snapshot không?**
9. **Collection membership có phải business history?**
10. **Owning side của JPA association được cập nhật đúng không?**
11. **Có mapping `@OneToMany@JoinColumn` hoặc fake bidirectional cần special audit table không?**
12. **Có các write paths bulk/native/JDBC bypass Envers không?**
13. **Có database cascades/triggers ảnh hưởng entity history không?**
14. **Có cần quan sát mọi trạng thái trung gian, không chỉ transaction revisions?**
15. **Có yêu cầu retention/xóa PII trong audit tables không?**
16. **Audit schema có nằm trong migrations và CI tests không?**
17. **Historical queries có thể chạy với dữ liệu lớn không?**
18. **Có multi-tenancy/cross-service consistency không?**
19. **Khi nâng Hibernate, có regression tests cho relation target mode không?**
20. **Ai được quyền đọc lịch sử, và log/exports có vô tình tiết lộ dữ liệu cũ không?**

Một ranh giới audit tốt là ranh giới **được lựa chọn vì yêu cầu nghiệp vụ**, không phải do đặt `@Audited` hàng loạt rồi hy vọng mọi quan hệ tự giữ đúng lịch sử.

## 44. Bài tập tình huống

### Bài 1 — Phân biệt hai annotation

Một audited `Order` trỏ `Category` non-audited. So sánh:

```java
@NotAudited
private Category category;
```

và:

```java
@Audited(targetAuditMode = RelationTargetAuditMode.NOT_AUDITED)
private Category category;
```

**Đáp án:** Trường hợp đầu loại quan hệ khỏi audit contract. Trường hợp sau audit reference nhưng resolve Category hiện tại.

### Bài 2 — Label đã thay đổi

Order ở R1 trỏ Category#9 khi tên là `"Điện tử"`. Category không audited, hiện tên `"Thiết bị số"`. Đọc Order R1 nhận tên nào?

**Đáp án:** Với `NOT_AUDITED` target mode và Category live còn tồn tại, tên hiện tại `"Thiết bị số"`.

### Bài 3 — Giá hàng tại thời điểm bán

OrderLine trỏ ProductCatalog không audited, giá catalog thay đổi hằng ngày. Dùng historical ProductCatalog current price để in hóa đơn cũ có đúng không?

**Đáp án:** Không. Lưu `unitPrice` và dữ liệu chứng từ đã chốt dưới dạng audited/immutable snapshot.

### Bài 4 — Entity đích cũng audited

Order.Customer và Customer đều audited, nhưng relation có `NOT_AUDITED`. Tại sao bản nâng Hibernate 7.3 có thể thay đổi output?

**Đáp án:** Hibernate 7.3 sửa việc bỏ qua setting này trong trường hợp target cũng audited; từ đó truy vấn target hiện tại thay vì lịch sử.

### Bài 5 — Target đã xóa

Historical Order có `category_id=9`; Category#9 live đã bị delete. Lỗi nào có thể gặp?

**Đáp án:** Historical target lookup không tìm thấy, có thể ném exception hoặc null theo policy/version. Cần giữ reference data, snapshot hoặc missing-target strategy có chủ đích.

### Bài 6 — `@NotAudited` field

Đổi `lastViewedAt` 100 lần mà không sửa audited properties. Có nên coi đó là 100 revisions nghiệp vụ?

**Đáp án:** Không. Field này bị loại khỏi audit; không dùng Envers để theo dõi nó.

### Bài 7 — Inverse collection

Bạn gọi `order.getLines().add(line)` nhưng không `line.setOrder(order)`. Lịch sử membership chắc chính xác không?

**Đáp án:** Không. Owning side FK chưa được cập nhật đúng; cần helper đồng bộ quan hệ trước khi xét Envers.

### Bài 8 — `@AuditJoinTable`

Tại sao Envers có thể cần thêm audit join table cho `@OneToMany + @JoinColumn`?

**Đáp án:** Để lưu lịch sử membership đúng khi JPA relation không dùng join table live và không thể suy membership từ audit state của child trong mọi mapping.

### Bài 9 — `@AuditMappedBy`

Có nên đặt `@AuditMappedBy` lên mọi bidirectional `@OneToMany(mappedBy=...)`?

**Đáp án:** Không. Đây là annotation experimental cho fake bidirectional mapping đặc thù, không phải thay `mappedBy` chuẩn.

### Bài 10 — Owner không đổi nhưng target đổi

Customer rename ở R7, Order không đổi từ R5. `getRevisions(Order.class,id)` có phải thêm R7 không?

**Đáp án:** Không nhất thiết. Owner revisions và global as-of graph snapshot là hai khái niệm khác nhau.

### Bài 11 — Bulk SQL

Một job dùng JPQL bulk UPDATE đổi 10.000 Order statuses. Envers có 10.000 audited updates tự động không?

**Đáp án:** Không. Bulk DML không đi qua per-entity lifecycle callbacks; cần alternative audit path nếu yêu cầu lịch sử đầy đủ.

### Bài 12 — ON DELETE CASCADE

Xóa parent bằng native DELETE khiến database cascade xóa children. Envers có chắc lưu mọi child DEL history không?

**Đáp án:** Không. Database-side cascades không tự phát Hibernate entity events từng child.

### Bài 13 — `store_data_at_delete`

Bật `org.hibernate.envers.store_data_at_delete=true` có làm non-audited ProductCategory lịch sử xuất hiện không?

**Đáp án:** Không. Setting liên quan dữ liệu audited entity tại delete revision, không tạo history cho target non-audited.

### Bài 14 — Chuyển sang Validity

Hệ thống đã có hàng triệu audit rows với Default strategy. Đổi property sang Validity có tự động chuyển toàn bộ history không?

**Đáp án:** Không. Cần migration/backfill audit metadata phù hợp và test historical queries.

### Bài 15 — Bảo mật

Trước đây password reset token từng được audited, nay thêm `@NotAudited`. Token cũ còn trong audit DB không?

**Đáp án:** Có thể còn. Phải xử lý retention/remediation riêng; annotation mới không xóa lịch sử cũ.

### Bài 16 — Khởi động audit muộn

Order có lịch sử giao dịch từ 2020 nhưng Envers mới bật từ 2026. Có thể tự dựng lịch sử customer assignment 2020 không?

**Đáp án:** Không nếu thiếu nguồn lịch sử độc lập. Chỉ có thể baseline current state hoặc import từ nguồn cũ đáng tin cậy.

### Bài 17 — Transaction rollback

`em.persist(order); em.flush(); tx.rollback();`. Envers có audit row đã commit không?

**Đáp án:** Không, nếu audit writes và entity writes cùng transaction DB rollback thành công.

### Bài 18 — One revision, nhiều entity

Một transaction đổi Order và Customer. Có phải hai revision numbers riêng?

**Đáp án:** Thông thường chúng có thể cùng revision do Envers ghi nhận các audited changes theo transaction, không theo từng entity.

### Bài 19 — Tìm orders của Customer cũ

Muốn query historical Orders có `customer_id=42`. Có thể dùng `AuditEntity.relatedId("customer").eq(42L)` không?

**Đáp án:** Đây là cách Envers hỗ trợ filter theo association identifier trong các mapping phù hợp; cần test query API/version và lựa chọn revision conditions đúng.

### Bài 20 — L2 cache

Historical Order trỏ non-audited Category, nhưng EntityManager hiện tại đang giữ Category cũ trong L1. Có thể nhìn thấy label cũ dù DB đã cập nhật không?

**Đáp án:** Có thể. Current-target semantics không vượt qua L1 cache/transaction isolation; dùng context mới và caching policy phù hợp để test.

## 45. Tài liệu tham khảo chính thức

- [Hibernate Envers — trang giới thiệu chính thức](https://hibernate.org/orm/envers/): revision model, historical entity/association snapshots, module dependency và overview.
- [Hibernate ORM 7.1 User Guide — Envers](https://docs.hibernate.org/orm/7.1/userguide/html_single/#envers): basics, relation auditing, audit strategies, AuditReader, mapping exceptions, collection change và configuration.
- [Hibernate ORM 7.3 Migration Guide — NOT_AUDITED target mode](https://docs.hibernate.org/orm/7.3/migration-guide/): thay đổi quan trọng khi association target thực ra cũng audited.
- [Hibernate ORM 7.1 Javadocs — `Audited`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/envers/Audited.html): entity/property auditing, target audit mode, target missing action và modified flags.
- [Hibernate ORM 7.1 Javadocs — `NotAudited`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/envers/NotAudited.html): loại property khỏi audit.
- [Hibernate ORM 7.1 Javadocs — `RelationTargetAuditMode`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/envers/RelationTargetAuditMode.html): audited/non-audited target semantics.
- [Hibernate ORM 7.1 Javadocs — `AuditJoinTable`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/envers/AuditJoinTable.html): cấu hình join table lịch sử.
- [Hibernate ORM 7.1 Javadocs — `AuditMappedBy`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/envers/AuditMappedBy.html): fake bidirectional relation; experimental.
- [Hibernate ORM 7.1 Javadocs — `AuditOverride`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/envers/AuditOverride.html): thay audit behavior của inherited/embedded properties.
- [Hibernate ORM 7.1 Javadocs — `AuditReader`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/envers/AuditReader.html): `find`, `getRevisions` và metadata.
- [Hibernate ORM 7.1 Javadocs — `AuditEntity`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/envers/query/AuditEntity.html): query historical attributes/relation identifiers.
- [Hibernate ORM 7.1 Javadocs — `EnversSettings`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/envers/configuration/EnversSettings.html): audit strategy, collection change, modified flags và delete behavior.
- [Hibernate ORM User Guide — Hibernate associations](https://docs.hibernate.org/orm/7.1/userguide/html_single/#associations): owning/inverse sides, collection mapping, join tables.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): entity lifecycle, relationship mapping, cascade, transaction semantics.

**Ghi chú phiên bản:** Envers là Hibernate-specific; `@AuditMappedBy` experimental; `@Audited(targetNotFoundAction=...)` và relation target behavior có các thay đổi theo version. Đặc biệt phải đọc migration guide khi nâng từ Hibernate 6/7.2 lên 7.3+, vì một audited target với `NOT_AUDITED` có thể chuyển từ historical resolution sang current resolution. Các ví dụ dùng mapping JPA/Hibernate hiện đại và cần được xác nhận trên đúng Hibernate, DBMS, migrations và caching configuration của dự án.

## Kết luận

Ranh giới kiểm toán quyết định điều một bản ghi lịch sử **có thể tái dựng**. `@Audited` ghi lịch sử entity/property; `@NotAudited` loại một property khỏi audit; `@Audited(targetAuditMode=NOT_AUDITED)` giữ lịch sử tham chiếu nhưng **đọc entity đích ở trạng thái hiện tại**, không tự tạo history cho target. Vì vậy, một “Order ở revision R” có thể là hỗn hợp của Order/Customer lịch sử và ProductCategory hiện tại.

Với collections, phải hiểu owning side của JPA, membership history, audit join table và các mapping đặc biệt như `@AuditJoinTable`/`@AuditMappedBy`. Với dữ liệu tài chính, pháp lý hoặc nghĩa vụ phải chính xác theo thời điểm, hãy audit target thật sự hoặc lưu immutable snapshot những giá trị quan trọng thay vì dựa vào current reference data.

Cuối cùng, Envers không tự bao phủ bulk/native SQL, database cascades, external writers hoặc mọi trạng thái trung gian trong một transaction. Hãy thiết kế rõ audit boundary, bảo vệ lịch sử theo tenant/permission, quản lý migrations/retention, và dùng integration tests qua nhiều revisions/transactions để xác nhận **cả quan hệ lẫn trạng thái của entity đích** trước khi coi historical graph là nguồn dữ liệu đáng tin cậy.
