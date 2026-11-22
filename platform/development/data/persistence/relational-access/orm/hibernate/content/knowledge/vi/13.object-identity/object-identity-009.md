# Kiểm thử tính đối xứng, bắc cầu và hành vi trước với sau khi lưu

Khi làm việc với Hibernate/Jakarta Persistence, **danh tính đối tượng** không chỉ là trường `@Id` trong database. Cùng một hàng dữ liệu có thể xuất hiện dưới dạng một object mới tạo, entity đang được quản lý (*managed*), entity đã tách khỏi persistence context (*detached*), hoặc Hibernate proxy. Việc cài đặt và kiểm thử `equals()`/`hashCode()` quyết định liệu những object đó có được coi là tương đương trong Java hay không.

Bài học tập trung vào cách **kiểm thử tính đối xứng (*symmetry*), bắc cầu (*transitivity*) và hành vi trước/sau khi lưu (`persist`, `flush`, `commit`, `detach`, `merge`)**. Đây là những bài kiểm thử cần thiết khi thiết kế entity có ID tự sinh, khóa nghiệp vụ, kế thừa, proxy và khi lưu entity trong `HashSet`/`HashMap`.

> **Thông điệp cốt lõi:** Hibernate đảm bảo danh tính entity trong **một persistence context**, nhưng không tự bảo đảm các object cùng trỏ tới một hàng sẽ có `equals() == true` ở **các persistence context khác nhau**. Đó là quyết định của thiết kế `equals()`/`hashCode()`. Một implementation trông đúng khi entity đã có ID vẫn có thể sai nghiêm trọng **trước lần persist đầu tiên**.

## 1. Ba tầng danh tính cần phân biệt

| Tầng | Câu hỏi | Cơ chế | Phạm vi |
| --- | --- | --- | --- |
| **Reference identity** | Hai biến có trỏ tới đúng cùng object Java? | `a == b` | JVM object hiện tại |
| **Persistent identity** | Hai entity có biểu diễn cùng một hàng ở database? | Entity type + primary key | Ánh xạ Hibernate/JPA và DB |
| **Logical equality** | Hai object có được ứng dụng coi là bằng nhau? | `equals()` và `hashCode()` | Toàn bộ Java code, collections, tests |

Ví dụ:

```java
PurchaseOrder order1 = em.find(PurchaseOrder.class, 100L);
PurchaseOrder order2 = em.find(PurchaseOrder.class, 100L);

System.out.println(order1 == order2);      // Thường true trong cùng persistence context.
System.out.println(order1.equals(order2)); // True ngay cả khi chưa override equals().
```

Trong **cùng** persistence context, JPA quản lý một object đại diện cho một entity identity. Nhưng nếu tải cùng khóa ở hai `EntityManager` khác nhau:

```java
PurchaseOrder first;

try (EntityManager em1 = emf.createEntityManager()) {
    first = em1.find(PurchaseOrder.class, 100L);
}

PurchaseOrder second;

try (EntityManager em2 = emf.createEntityManager()) {
    second = em2.find(PurchaseOrder.class, 100L);
}

System.out.println(first == second); // Thường false.
```

Nếu entity vẫn sử dụng `Object.equals()` mặc định, `first.equals(second)` cũng thường `false`, **dù cả hai biểu diễn cùng một hàng database**. Điều này không nhất thiết là lỗi: có dự án chủ động chỉ dựa vào identity trong persistence context. Nhưng nếu entity được so sánh giữa request/transaction hoặc đưa vào collection, cần xác định **hợp đồng equality của domain**.

### 1.1. Hai object có cùng dữ liệu không nhất thiết là cùng entity

```text
PurchaseOrder(id=100, number="PO-100")
PurchaseOrder(id=101, number="PO-100")
```

Nếu hai hàng khác khóa chính nhưng có cùng `number` (ví dụ khi dữ liệu lịch sử cho phép), chúng vẫn là hai persistent identities. Một `equals()` dựa vào `number` sẽ coi chúng bằng nhau, có thể trái ý định nếu `number` không có UNIQUE constraint.

Ngược lại:

```text
Object A: PurchaseOrder(id=100, status="DRAFT")
Object B: PurchaseOrder(id=100, status="PAID")
```

Hai object có thể phản ánh cùng entity tại hai thời điểm khác nhau. Nếu equality dựa trên `id`, chúng bằng nhau dù `status` khác. Đó thường là mục đích khi so **danh tính entity**, không phải so toàn bộ snapshot.

## 2. Hợp đồng `equals()` trong Java

Theo `java.lang.Object`, `equals()` phải tuân thủ các tính chất:

| Tính chất | Điều kiện | Minh họa |
| --- | --- | --- |
| **Phản xạ (reflexive)** | `x.equals(x)` luôn `true` với `x != null` | `a.equals(a)` |
| **Đối xứng (symmetric)** | Nếu `x.equals(y)` thì `y.equals(x)` | So hai chiều |
| **Bắc cầu (transitive)** | Nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)` | So ba object |
| **Nhất quán (consistent)** | Kết quả ổn định khi thông tin dùng trong equality không đổi | Không phụ thuộc thời gian ngẫu nhiên |
| **Không bằng `null`** | `x.equals(null)` luôn `false` | Dùng guard `other == null` |

Đồng thời, `hashCode()` phải thỏa:

1. Nếu `a.equals(b)` là `true`, bắt buộc `a.hashCode() == b.hashCode()`.
2. Trong khi những thông tin quyết định equality không thay đổi, hash code phải ổn định theo hợp đồng Java.
3. Nếu `a` và `b` không bằng nhau, **không bắt buộc** hash code khác nhau. Va chạm hash (*collision*) là hợp lệ, nhưng nhiều collision có thể giảm hiệu năng hash collection.

**Chỉ so kết quả `equals()` với nhau mà không kiểm tra `hashCode()` là chưa đủ**. Ngược lại, cùng hash code cũng không chứng minh hai object bằng nhau.

### 2.1. Ví dụ tính đối xứng

Một implementation sai có thể tạo kết quả:

```text
a.equals(b) = true
b.equals(a) = false
```

Thường gặp khi một class dùng `instanceof` còn class con dùng `getClass()`, hoặc khi một phía có logic so sánh business key bổ sung.

### 2.2. Ví dụ tính bắc cầu

Một implementation khác có thể khiến:

```text
a.equals(b) = true
b.equals(c) = true
a.equals(c) = false
```

Bất kỳ trường hợp nào như vậy đều vi phạm hợp đồng Java, bất kể database có bao nhiêu hàng. Với entity có kế thừa và proxy, tính bắc cầu đặc biệt dễ gặp rủi ro nếu các subtype chọn cách so sánh khác nhau.

## 3. Chu trình sống của entity làm vấn đề phức tạp hơn

| Trạng thái | Entity đang ở đâu? | ID có thể thế nào? | Điều cần quan sát |
| --- | --- | --- | --- |
| **Transient/New** | Mới gọi constructor, chưa được quản lý | Với ID sinh tự động thường là `null` | Hai new object không tự được coi là cùng entity |
| **Managed** | Đang nằm trong persistence context | ID được provider gán theo chiến lược | `find` cùng identity thường trả cùng object |
| **Flushed** | SQL đã đồng bộ nhưng transaction có thể chưa commit | ID thường có nếu lưu thành công | `flush()` khác `commit()` |
| **Detached** | Entity không còn gắn với context | ID vẫn còn trên object | So với object được load ở context khác |
| **Merged** | `merge(detached)` trả về managed instance | Thường cùng persistent ID | Đối tượng truyền vào vẫn detached |
| **Removed** | Đã gọi remove với managed entity | ID có thể vẫn còn trên object | `equals()` không xác nhận hàng còn tồn tại ở DB |
| **Proxy/Reference** | Hibernate có thể cung cấp proxy thay cho entity đã tải đầy đủ | Thường có identifier trước khi initialize | `getClass()`, lazy loading, `equals()` đối xứng |

Sơ đồ:

```text
new PurchaseOrder(...)
      |
      | em.persist(order)
      v
  MANAGED ------------- em.detach(order) / em.close()
      |                              |
      | em.flush()                   v
      |                           DETACHED
      |                              |
      |                              | managedCopy = em.merge(order)
      |                              v
      +--------------------------> MANAGED COPY
      |
      | em.remove(order)
      v
   REMOVED
```

**ID sinh tự động không có thời điểm gán cố định chung cho mọi chiến lược**. `IDENTITY` thường cần INSERT để lấy ID, còn `SEQUENCE` có thể cấp ID trước INSERT; provider và flush mode cũng ảnh hưởng thời điểm. Vì thế bài kiểm thử muốn xác nhận ID sau lưu nên dùng `flush()` trong transaction thay vì luôn đòi ID đã có ngay sau `persist()`.

## 4. Lỗi kinh điển: hai entity mới đều có ID `null`

Implementation có vẻ hợp lý nhưng sai:

```java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof PurchaseOrder that)) {
        return false;
    }
    return java.util.Objects.equals(id, that.id);
}

@Override
public int hashCode() {
    return java.util.Objects.hashCode(id);
}
```

Giả sử:

```java
PurchaseOrder a = new PurchaseOrder("PO-A");
PurchaseOrder b = new PurchaseOrder("PO-B");

// Cả a.id và b.id đều null.
System.out.println(a.equals(b)); // true — SAI về danh tính.
```

`Objects.equals(null, null)` trả về `true`. Hậu quả:

```java
Set<PurchaseOrder> orders = new HashSet<>();
orders.add(a);
orders.add(b);

System.out.println(orders.size()); // Có thể chỉ 1, dù là hai order mới.
```

Nguyên tắc tối thiểu khi dùng ID sinh bởi database:

```text
this == other                     → true
hai object khác nhau, ID null     → false
hai object cùng entity type,
cùng ID không null                → true
```

Tức là **ID null không phải là một “giá trị khóa” có thể dùng để khẳng định hai entity bằng nhau**.

## 5. Lỗi thứ hai: hashCode thay đổi sau khi persist

Một implementation khác thường gặp:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof PurchaseOrder that)) return false;
    return id != null && id.equals(that.id);
}

@Override
public int hashCode() {
    return id == null ? 0 : id.hashCode();
}
```

Nó xử lý đúng trường hợp hai ID null **nhưng lại đổi hash code khi ID được gán**.

```java
PurchaseOrder order = new PurchaseOrder("PO-1");

Set<PurchaseOrder> set = new HashSet<>();
set.add(order); // Hash dựa vào null.

em.persist(order);
em.flush(); // Giả sử ID được cấp, hashCode giờ dựa vào ID.

boolean found = set.contains(order); // Có thể false!
```

**Lý do:** `HashSet` đã đặt object vào bucket dựa trên hash cũ. Khi ID chuyển từ `null` sang `100`, `hashCode()` thay đổi nhưng Java không tự di chuyển phần tử sang bucket mới. Vì vậy `contains()` và `remove()` có thể thất bại dù object vẫn có mặt trong set khi duyệt.

Đây là một ví dụ rõ rằng chỉ kiểm thử equality **sau khi lưu** sẽ bỏ sót lỗi quan trọng **trước và sau khi lưu**.

### 5.1. Không dùng field mutable khác làm hash code tùy tiện

Giả sử equality dựa vào `orderNumber` nhưng mã này có thể sửa:

```java
order.setOrderNumber("PO-2");
```

`hashCode()` cũng thay đổi nếu phụ thuộc `orderNumber`. Rủi ro với `HashSet` tương tự ID sinh tự động. Nếu chọn **business key equality**, business key đó phải thực sự ổn định từ trước persist đến hết vòng đời object theo mô hình sử dụng.

## 6. Một chiến lược cho entity dùng ID sinh tự động

Một lựa chọn phổ biến là:

- Hai entity **cùng instance** luôn bằng nhau.
- Hai instance khác nhau chỉ bằng nhau nếu có cùng **entity type** và **ID khác null**.
- `hashCode()` là giá trị ổn định theo **entity type**, không phụ thuộc ID sinh tự động.

Ví dụ entity Java/Jakarta Persistence kết hợp Hibernate proxy handling:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.proxy.HibernateProxy;

import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = Objects.requireNonNull(orderNumber);
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    private static Class<?> persistentType(Object object) {
        if (object instanceof HibernateProxy proxy) {
            return proxy.getHibernateLazyInitializer().getPersistentClass();
        }
        return object.getClass();
    }

    @Override
    public final boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (other == null || persistentType(this) != persistentType(other)) {
            return false;
        }

        PurchaseOrder that = (PurchaseOrder) other;

        // Chỉ so khi ID khác null; dùng accessor để không trực tiếp đọc
        // field ID có thể chưa được điền trong đối tượng proxy.
        Long thisId = getId();
        return thisId != null && thisId.equals(that.getId());
    }

    @Override
    public final int hashCode() {
        // Ổn định trước và sau persist, không phụ thuộc generated ID.
        return persistentType(this).hashCode();
    }
}
```

Các thành phần trong ví dụ có vai trò riêng:

1. `@Id` và `@GeneratedValue` xác định persistent identifier.
2. Hai object mới có `id = null` **không** bằng nhau, trừ khi chúng là cùng reference.
3. Khi hai object đã có cùng ID và cùng persistent type, `equals()` trả `true`.
4. `hashCode()` dựa vào type nên **không thay đổi khi provider gán ID**.
5. Hàm `persistentType()` nhận biết `HibernateProxy` để so entity type theo mapping thay vì chỉ gọi `getClass()` của proxy.
6. `getId()` giúp tránh truy cập trực tiếp field `id` ở một đối tượng proxy chưa được initialize.

Đây là **một chiến lược cụ thể**, không phải yêu cầu bắt buộc của JPA. Với hệ thống có entity inheritance phức tạp, bytecode enhancement, composite IDs hoặc provider không phải Hibernate, cần điều chỉnh quy tắc type/proxy và kiểm thử ở đúng cấu hình.

### 6.1. Tại sao hashCode cố định theo class là hợp lệ?

Hai object khác nhau cùng entity type có thể có cùng hash code:

```text
PurchaseOrder(id=100) → hashCode = PurchaseOrder.class.hashCode()
PurchaseOrder(id=101) → hashCode = PurchaseOrder.class.hashCode()
```

Điều này **không vi phạm** hợp đồng Java, bởi yêu cầu là *equals true ⇒ hash giống nhau*; chiều ngược lại không bắt buộc.

Đổi lại, rất nhiều `PurchaseOrder` trong một `HashSet` sẽ gây va chạm hash, có thể làm các thao tác kém hiệu quả hơn so với hash phân bố tốt theo ID. Vì vậy:

- Phù hợp với nhiều tập entity có kích thước nhỏ/vừa, nơi **tính ổn định qua persist** quan trọng hơn tốc độ hash tối đa.
- Với collection rất lớn, cần đo hiệu năng và cân nhắc business key bất biến hoặc ID được cấp ngay khi tạo.
- Không “tối ưu” thành `hashCode()` theo ID nếu entity có thể được thêm vào hash collection **trước** khi ID được cấp.

### 6.2. Vì sao không chỉ gọi `getClass()`?

Hibernate có thể trả **proxy subclass** của entity:

```text
PurchaseOrder.class
PurchaseOrder$HibernateProxy$...class
```

Vì vậy:

```java
this.getClass() == other.getClass()
```

có thể là `false` với entity thật và proxy cùng một hàng.

Ngược lại, dùng `instanceof PurchaseOrder` quá rộng có thể khiến **hai subtype khác nhau** trong hệ phân cấp entity bị xem là bằng nhau chỉ vì cùng giá trị ID, nếu quy tắc ID cho phép trùng. Cần một quy tắc type nhất quán với hierarchy và kiểm thử cả chiều `entity.equals(proxy)` lẫn `proxy.equals(entity)`.

Ví dụ `HibernateProxy` ở trên là giải pháp **Hibernate-specific**. Trong một hệ thống cần portable giữa JPA providers, nên cân nhắc equality dựa trên **business key ổn định** hoặc tiêu chí type được hỗ trợ bởi provider đích, kèm test integration.

### 6.3. Vai trò của `final` trong equals/hashCode

Một số chiến lược sử dụng `final` cho hai method để ngăn các subclass thay đổi quy tắc equality và giảm bất đồng giữa entity/proxy. Hibernate proxy/enhancement và yêu cầu JPA vẫn có những ràng buộc riêng, nên **không suy ra toàn bộ entity class cần được đánh dấu `final`**.

Nếu project dùng bytecode enhancement hoặc custom proxy, test cần phản ánh đúng cấu hình thực tế. `final` method ở ví dụ không phải giấy bảo đảm rằng mọi công cụ proxy của mọi thư viện sẽ có cùng hành vi.

## 7. Một chiến lược khác: business key bất biến

Không phải entity nào cũng cần equality dựa trên generated ID. Nếu domain có một **natural/business key duy nhất, được biết từ lúc tạo và không thay đổi**, có thể dùng nó.

Ví dụ mã quốc gia:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "countries")
public class Country {

    @Id
    @Column(name = "iso_code", length = 2, nullable = false)
    private String isoCode;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Country() {
    }

    public Country(String isoCode, String displayName) {
        this.isoCode = Objects.requireNonNull(isoCode);
        this.displayName = Objects.requireNonNull(displayName);
    }

    public String getIsoCode() {
        return isoCode;
    }

    public String getDisplayName() {
        return displayName;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Country that)) return false;
        return isoCode != null && isoCode.equals(that.isoCode);
    }

    @Override
    public int hashCode() {
        return isoCode == null ? 0 : isoCode.hashCode();
    }
}
```

Trong ví dụ này, `isoCode` là **khóa được ứng dụng cấp trước khi persist** và không có setter thay đổi sau đó. Vì thế `hashCode()` ổn định từ lúc khởi tạo:

```java
Country a = new Country("VN", "Việt Nam");
Country b = new Country("VN", "Vietnam");

System.out.println(a.equals(b)); // true: cùng identity theo isoCode.
```

Để business key equality an toàn:

- Key phải **thực sự duy nhất** theo database, thường có `PRIMARY KEY` hoặc `UNIQUE` constraint.
- Key phải có **trước khi object được đưa vào hash collection**.
- Key phải không thay đổi khi entity đang được sử dụng làm thành viên set hoặc map key.
- Quy tắc chuẩn hóa phải nhất quán ở Java và database: chữ hoa/thường, dấu cách, Unicode, locale, collation.
- Khi dùng kế thừa entity, phải cân nhắc so type và cả proxy thay vì copy nguyên `instanceof` một cách máy móc.

Hibernate có `@NaturalId` để mô tả natural key trong một số trường hợp, nhưng nó không tự tạo một chính sách `equals()`/`hashCode()` hoàn chỉnh cho bạn.

### 7.1. Khi nào business key không phù hợp?

Nếu mã đơn hàng có thể đổi do sửa nghiệp vụ, hoặc không chắc duy nhất tại thời điểm `new`, dùng mã đó trong equality có thể làm object **đang ở trong `HashSet` thay đổi hash code**.

Ví dụ `username` đổi được không phải lúc nào cũng là business key phù hợp. `email` có thể cần xác minh, thay đổi, chuẩn hóa; không nên tự coi nó là identity bất biến. Hãy phân biệt **cột có UNIQUE constraint** với **business key đủ ổn định để dùng cho equality**.

## 8. Chiến lược ID được gán từ lúc tạo: UUID

Một giải pháp khác là cấp ID cho entity ngay trong constructor/factory, ví dụ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.util.UUID;

@Entity
public class Document {

    @Id
    private UUID id;

    protected Document() {
    }

    public Document(String title) {
        this.id = UUID.randomUUID();
        this.title = title;
    }

    private String title;

    public UUID getId() {
        return id;
    }
}
```

Nếu ID được cấp **trước khi thêm object vào set**, hash code theo ID có thể ổn định ngay từ đầu. Tuy nhiên:

- Đây là **assigned ID**, không giống `@GeneratedValue(strategy = GenerationType.UUID)` nơi provider có thể tạo ID trong `persist()`.
- UUID có xác suất va chạm cực nhỏ nhưng vẫn cần PK/UNIQUE constraint ở database.
- Dùng ID được cấp trước khi persist có thể làm logic nhận biết entity mới/cũ trong một số framework/repository (như Spring Data JPA) cần cấu hình rõ hơn.
- Equality vẫn phải xét đúng entity type/proxy và đảm bảo ID không đổi sau tạo.

Không có phương án đúng cho mọi hệ thống; chọn dựa trên identity semantics, lifecycle, chiến lược tạo ID và nhu cầu collection.

## 9. Các lỗi đối xứng và bắc cầu khi có kế thừa

Một lỗi khó thấy là class cha và class con định nghĩa equality khác nhau.

Giả sử:

```java
class BaseEntity {
    Long id;

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof BaseEntity that)) {
            return false;
        }
        return id != null && id.equals(that.id);
    }
}

class SpecialEntity extends BaseEntity {
    String region;

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof SpecialEntity that)) {
            return false;
        }
        return super.equals(other) &&
               java.util.Objects.equals(region, that.region);
    }
}
```

Nếu `BaseEntity(id=1)` và `SpecialEntity(id=1, region="A")`:

```text
base.equals(special)    → true
special.equals(base)    → false
```

**Tính đối xứng bị phá vỡ.** Tình huống này có thể xuất hiện khi entity hierarchy áp dụng `instanceof` ở base nhưng subtype lại yêu cầu các thuộc tính riêng.

Bắc cầu cũng có thể bị phá khi một số lớp dùng kiểu so sánh “tương thích gần đúng” khác nhau, hoặc khi key/field dùng cho equality bị thay đổi giữa các lần gọi.

Quy tắc thiết kế:

1. Xác định identity bằng **một chính sách chung cho cả hierarchy**.
2. Nếu các subtype là **những entity types khác biệt**, cân nhắc equality yêu cầu persistent type giống nhau.
3. Không cho mỗi subtype tự ý bổ sung field mutable vào equality.
4. Kiểm thử cả entity thật và Hibernate proxy.
5. Kiểm thử cả ba đối tượng thuộc cùng và khác subtype nếu model cho phép.

Một số hệ kế thừa dùng khóa chính chung trên hierarchy và định danh theo root type; số khác coi subtype là type riêng. Vì vậy lựa chọn `instanceof` hay strict persistent class phải được thống nhất theo **mô hình định danh**, không chỉ theo một snippet.

## 10. Bộ kiểm thử đơn vị cho hợp đồng Java

Có thể dùng JUnit 5 (`org.junit.jupiter.api.Test`, các assertion trong `Assertions`) để kiểm tra equality trước khi cần database.

Giả sử `PurchaseOrder` dùng implementation ở mục 6.

### 10.1. Phản xạ, null và hai object mới

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class PurchaseOrderEqualityUnitTest {

    @Test
    void newEntityIsReflexiveAndNotEqualToNull() {
        PurchaseOrder order = new PurchaseOrder("PO-1");

        assertEquals(order, order);
        assertNotEquals(null, order);
        assertFalse(order.equals(null));
    }

    @Test
    void twoDifferentNewEntitiesAreNotEqual() {
        PurchaseOrder first = new PurchaseOrder("PO-1");
        PurchaseOrder second = new PurchaseOrder("PO-1");

        assertNull(first.getId());
        assertNull(second.getId());
        assertNotEquals(first, second);
        assertNotEquals(second, first);
    }
}
```

Hai order mới có cùng `orderNumber` nhưng chưa có ID **không bằng nhau** theo chiến lược ID-based equality đang chọn. Nếu chọn business-key equality, kỳ vọng này phải được thay tương ứng với hợp đồng của domain.

### 10.2. Đối xứng phải so cả hai chiều

```java
static void assertSymmetric(Object first, Object second) {
    boolean forward = first.equals(second);
    boolean backward = second.equals(first);

    assertEquals(
        forward,
        backward,
        "equals() phải đối xứng"
    );
}
```

Không chỉ viết:

```java
assertEquals(a, b);
```

vì các framework assertion thường gọi `a.equals(b)` theo một chiều. Nếu implementation sai mà phía `a` trả `true`, bài test đó có thể qua dù `b.equals(a)` là `false`.

Dùng hai assertion rõ ràng với trường hợp kỳ vọng bằng nhau:

```java
assertTrue(a.equals(b));
assertTrue(b.equals(a));
```

### 10.3. Bắc cầu: ba object cùng identity

```java
static void assertTransitive(Object a, Object b, Object c) {
    assertTrue(a.equals(b));
    assertTrue(b.equals(c));
    assertTrue(a.equals(c));

    // Không bắt buộc theo định nghĩa bắc cầu,
    // nhưng cần kiểm tra đối xứng của mọi cặp.
    assertTrue(b.equals(a));
    assertTrue(c.equals(b));
    assertTrue(c.equals(a));
}
```

Các input phải được chuẩn bị để **a, b, c thực sự cùng biểu diễn một identity** theo chính sách đang dùng. Nếu tạo ba entity mới có ID null theo ID-based equality, chúng **không nên** qua điều kiện này; điều đó không phải lỗi tính bắc cầu, chỉ là test setup sai.

### 10.4. Hash code của hai object bằng nhau

```java
static void assertEqualHash(Object a, Object b) {
    assertTrue(a.equals(b));
    assertTrue(b.equals(a));
    assertEquals(a.hashCode(), b.hashCode());
}
```

Không viết test yêu cầu **hai object không bằng nhau phải có hash khác nhau**: hợp đồng Java không yêu cầu điều đó.

## 11. Kiểm thử integration trước và sau `persist()`

Unit test ở mục 10 chưa kiểm tra **thời điểm Hibernate gán ID**. Để bắt lỗi biến đổi hash trong `HashSet`, cần một test có `EntityManagerFactory` thực và database kiểm thử.

### 11.1. Giả định hạ tầng test

Các ví dụ tiếp theo giả định:

- `emf` là một `EntityManagerFactory` đã được tạo cho persistence unit có mapping `PurchaseOrder`.
- Test dùng transaction **resource-local** (`em.getTransaction()`).
- Database kiểm thử đã có bảng `purchase_orders` và có chiến lược sinh ID phù hợp.
- Mỗi test chủ động mở/đóng `EntityManager`.
- Test tạo order number duy nhất để không vi phạm `UNIQUE`.
- Nếu dùng Spring Boot/JTA, hãy dùng transaction manager/test slice tương ứng thay vì bê nguyên `getTransaction()`.

### 11.2. Test `HashSet.contains` không đổi sau khi Hibernate cấp ID

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;
import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class PurchaseOrderPersistenceTest {

    // Khởi tạo/đóng emf trong @BeforeAll/@AfterAll hoặc test fixture.
    private final jakarta.persistence.EntityManagerFactory emf;

    PurchaseOrderPersistenceTest(
        jakarta.persistence.EntityManagerFactory emf
    ) {
        this.emf = emf;
    }

    @Test
    void hashSetStillFindsEntityAfterIdAssignment() {
        String number = "PO-" + UUID.randomUUID();
        PurchaseOrder order = new PurchaseOrder(number);

        Set<PurchaseOrder> set = new HashSet<>();
        set.add(order);

        int beforeHash = order.hashCode();
        assertNull(order.getId());
        assertTrue(set.contains(order));

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();
            em.persist(order);
            em.flush();

            assertNotNull(order.getId());
            assertEquals(beforeHash, order.hashCode());
            assertTrue(set.contains(order));

            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }

        assertTrue(set.contains(order)); // Order đã detached nhưng hash ổn định.
    }
}
```

**Lưu ý triển khai:** JUnit 5 không tự truyền `EntityManagerFactory` cho constructor như đoạn minh họa; cần **cấu hình fixture/extension, hoặc khởi tạo `emf` trong `@BeforeAll` và đóng trong `@AfterAll`**. Đoạn trên nhấn mạnh phần kiểm tra; một project thực nên dùng lifecycle test fixture sẵn có để test được runner tạo instance.

Để test hoàn toàn tự chứa phần setup, có thể dùng:

```java
static EntityManagerFactory emf;

@BeforeAll
static void setup() {
    emf = Persistence.createEntityManagerFactory("identity-test");
}

@AfterAll
static void cleanup() {
    if (emf != null) {
        emf.close();
    }
}
```

kết hợp file `META-INF/persistence.xml` và dependency JDBC/Hibernate phù hợp. Không cần database sản xuất: một database test riêng hoặc Testcontainers với đúng DBMS thường an toàn hơn.

### 11.3. Test hai entity mới không bị gộp trong Set

```java
PurchaseOrder first = new PurchaseOrder("PO-A");
PurchaseOrder second = new PurchaseOrder("PO-B");

Set<PurchaseOrder> set = new HashSet<>();
set.add(first);
set.add(second);

assertEquals(2, set.size());
assertNotEquals(first, second);
assertNotEquals(second, first);
```

Test này bắt lỗi `Objects.equals(null, null)` ở mục 4, dù chưa chạy ORM.

### 11.4. Nếu muốn test với một chiến lược ID khác

Đừng hardcode kỳ vọng “ID chắc chắn null ngay sau `persist()`” hoặc “đã có trước flush” khi đổi giữa `SEQUENCE`, `IDENTITY`, `UUID`/assigned ID. Kỳ vọng ổn định cho test generated ID là:

```text
Trước lần persist đầu:
    id == null (nếu constructor/ứng dụng không tự cấp)

Sau em.persist(...) + em.flush():
    id != null (khi flush thành công, strategy phù hợp)

Trước và sau gán ID:
    hashCode ổn định nếu object đã ở trong hash collection
```

## 12. So sánh hai EntityManager khác nhau

Với ID-based equality, hai Java object biểu diễn cùng một hàng cần bằng nhau, dù reference khác.

Mẫu helper tạo bản ghi:

```java
static Long createOrder(
    EntityManagerFactory emf,
    String orderNumber
) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();
        PurchaseOrder order = new PurchaseOrder(orderNumber);
        em.persist(order);
        em.flush();

        Long id = order.getId();
        tx.commit();
        return id;
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
```

Dùng hai `EntityManager`:

```java
Long id = createOrder(emf, "PO-UNIQUE-101");

PurchaseOrder a;
PurchaseOrder b;

EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();

try {
    a = em1.find(PurchaseOrder.class, id);
    b = em2.find(PurchaseOrder.class, id);

    assertNotNull(a);
    assertNotNull(b);

    assertNotSame(a, b);
    assertTrue(a.equals(b));
    assertTrue(b.equals(a));
    assertEquals(a.hashCode(), b.hashCode());
} finally {
    em1.close();
    em2.close();
}
```

`assertNotSame(a,b)` cho thấy có **hai object references**. `equals()` đúng về identity cho phép chúng **bằng nhau về mặt domain**. Test này không thể thay bằng việc gọi `find()` hai lần trên cùng `EntityManager`, vì trường hợp đó thường trả cùng object và `equals()` qua được bằng `this == other`, không thử logic dựa trên ID.

## 13. Kiểm thử tính bắc cầu với ba persistence contexts

Một bài test mạnh hơn dùng ba object cùng khóa từ **ba context**:

```java
Long id = createOrder(emf, "PO-TRANSITIVE");

EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();
EntityManager emC = emf.createEntityManager();

try {
    PurchaseOrder a = emA.find(PurchaseOrder.class, id);
    PurchaseOrder b = emB.find(PurchaseOrder.class, id);
    PurchaseOrder c = emC.find(PurchaseOrder.class, id);

    assertNotSame(a, b);
    assertNotSame(b, c);
    assertNotSame(a, c);

    assertTrue(a.equals(b));
    assertTrue(b.equals(c));
    assertTrue(a.equals(c));

    assertTrue(b.equals(a));
    assertTrue(c.equals(b));
    assertTrue(c.equals(a));

    assertEquals(a.hashCode(), b.hashCode());
    assertEquals(b.hashCode(), c.hashCode());
} finally {
    emA.close();
    emB.close();
    emC.close();
}
```

Giá trị kiểm thử: `a.equals(b)` và `b.equals(c)` đều `true`, vì vậy `a.equals(c)` **phải** `true`. Nếu không, logic equality có vi phạm bắc cầu. Các kiểm tra theo chiều ngược bổ sung hợp đồng đối xứng.

Với business key equality, bộ test tương tự có thể dùng ba object mới có cùng key bất biến, nhưng cần tránh tạo nhiều hàng database trùng UNIQUE; chỉ persist một object, các object còn lại nên là các representation được load hoặc tạo không persist tùy use case.

## 14. Test entity thật và Hibernate proxy

Hibernate có thể trả một reference chưa được tải toàn bộ thông qua `EntityManager.getReference()` hoặc `Session.getReference()`. Equality phải được thiết kế sao cho **object thật và proxy của cùng identity không mâu thuẫn**.

```java
Long id = createOrder(emf, "PO-PROXY-101");

EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();

try {
    PurchaseOrder actual = em1.find(PurchaseOrder.class, id);
    PurchaseOrder reference = em2.getReference(PurchaseOrder.class, id);

    assertNotNull(actual);
    assertNotNull(reference);

    // Nếu dùng ID-based equality, kỳ vọng hai chiều:
    assertTrue(actual.equals(reference));
    assertTrue(reference.equals(actual));

    assertEquals(actual.hashCode(), reference.hashCode());
} finally {
    em1.close();
    em2.close();
}
```

**Đây là integration test**, vì proxy behavior phụ thuộc Hibernate version, proxy/enhancement configuration và cách entity được map. Đừng chỉ thay `reference` bằng `new PurchaseOrder(...)` trong unit test rồi kết luận proxy-safe.

Một số điều cần quan sát khi test proxy:

- `getReference()` không bảo đảm luôn tạo subclass proxy; có thể trả object đã managed hoặc dùng enhancement strategy khác.
- Truy cập một non-ID property có thể **initialize proxy**, phát SQL hoặc ném `EntityNotFoundException` nếu hàng không tồn tại.
- `equals()`/`hashCode()` không nên duyệt quan hệ LAZY hay gọi `toString()`/getter business data chỉ để so identity.
- Gọi `getClass()` trực tiếp trên proxy và entity thật có thể trả class khác nhau.
- `Hibernate.getClass(proxy)` trong một số Hibernate version có thể kích hoạt initialization; nếu cần tránh SQL, dùng API proxy phù hợp với bản đang chạy và xác minh qua test.
- Cần thử `actual.equals(reference)` **và** `reference.equals(actual)`; chỉ một chiều có thể che lỗi symmetry.

## 15. Detached và `merge()`: cùng identity, khác reference

`EntityManager.merge(detached)` **không biến object detached truyền vào thành managed**. Nó trả về một object managed đại diện trạng thái được merge:

```java
Long id = createOrder(emf, "PO-MERGE-101");

PurchaseOrder detached;
EntityManager loadEm = emf.createEntityManager();
try {
    detached = loadEm.find(PurchaseOrder.class, id);
} finally {
    loadEm.close();
}

EntityManager mergeEm = emf.createEntityManager();
EntityTransaction tx = mergeEm.getTransaction();

try {
    tx.begin();

    PurchaseOrder managed = mergeEm.merge(detached);

    assertNotSame(detached, managed);
    assertTrue(detached.equals(managed));
    assertTrue(managed.equals(detached));
    assertEquals(detached.hashCode(), managed.hashCode());

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    mergeEm.close();
}
```

Ý nghĩa: cả hai biểu diễn cùng **persistent identity** nên equality theo ID phải giống nhau, dù tham chiếu object và trạng thái managed/detached khác nhau.

**Không nên dùng `merge()` như “cách tạo ID cho object mới” chỉ để có entity có thể so sánh**. Với transient object, `merge()` có thể tạo bản persistent mới khác object đầu vào, dẫn tới những điều kiện kiểm thử khác. Cần phân biệt merge detached entity đã có ID với merge transient entity.

## 16. `HashMap` và `HashSet`: hành vi qua các trạng thái

Nếu object dùng làm key trong `HashMap`, các vấn đề hash cũng xảy ra:

```java
PurchaseOrder order = new PurchaseOrder("PO-HASHMAP");
Map<PurchaseOrder, String> notes = new HashMap<>();

notes.put(order, "priority");
String before = notes.get(order);

em.persist(order);
em.flush();

String after = notes.get(order);
```

Nếu `hashCode()` thay đổi khi ID được gán, `after` có thể `null`. Với chiến lược class-constant hash code, `before` và `after` đều là `"priority"`.

### 16.1. Nên test nhiều hơn contains

Một bộ kỳ vọng tối thiểu khi object đổi từ transient sang managed:

```java
int hashBefore = order.hashCode();
set.add(order);

em.persist(order);
em.flush();

assertEquals(hashBefore, order.hashCode());
assertTrue(set.contains(order));
assertTrue(set.remove(order));
```

Có thể thay `HashSet` bằng `HashMap` nếu entity thực sự được dùng làm key. Trường hợp `remove()` không thành công thường chỉ lộ ra khi code cleanup, gây leak object hoặc cập nhật sai collection.

### 16.2. Không sửa business key sau khi đã dùng làm hash key

Nếu equality dựa theo `orderNumber`, test thay đổi business key phải khẳng định **ứng dụng không cho phép thay đổi**, hoặc thay đổi đó không làm object đang dùng làm key bị lỗi. Tốt nhất là giới hạn public API và database constraint, thay vì viết test mong `HashSet` tự thích nghi với mutation.

## 17. Tính nhất quán qua `flush()`, `clear()` và transaction

Một bộ test có thể chạm các mốc:

```text
new
  → persist
  → flush
  → commit
  → clear/close
  → find ở EntityManager mới
  → getReference/proxy
  → merge
```

Những mốc này không có cùng ý nghĩa:

- `persist()` chuyển entity mới sang managed theo quy tắc JPA; ID có thể hoặc chưa thể xuất hiện tùy generator.
- `flush()` đồng bộ pending changes tới database; **không tự commit**.
- `commit()` hoàn tất transaction, dữ liệu có thể được nhìn thấy bởi context khác theo mức isolation.
- `clear()`/`detach()` làm entity không còn managed trong persistence context hiện tại.
- `find()` sau `clear()` có thể tạo instance khác đại diện cùng identity.
- `getReference()` có thể cấp proxy mà chưa đọc mọi column.
- `merge()` trả managed copy, không đồng nhất object đầu vào với object trả về.

Khi test **cùng hàng từ nhiều context**, hãy persist và **commit thành công** trước khi mở context khác; nếu chỉ `flush()` nhưng transaction chưa commit, query từ context khác có thể không thấy hàng do isolation. Khi dùng rollback per test, việc tạo context khác cũng cần nằm trong strategy transaction phù hợp.

## 18. `equals/hashCode` với composite ID

Entity dùng `@EmbeddedId` hoặc `@IdClass` có yêu cầu bổ sung: **lớp khóa ghép phải có equality theo các thành phần khóa**, phù hợp với khóa database.

Ví dụ:

```java
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineId implements Serializable {

    private Long orderId;
    private Integer lineNo;

    protected OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNo) {
        this.orderId = orderId;
        this.lineNo = lineNo;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineId that)) return false;
        return Objects.equals(orderId, that.orderId)
            && Objects.equals(lineNo, that.lineNo);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNo);
    }
}
```

Test:

```java
OrderLineId a = new OrderLineId(10L, 1);
OrderLineId b = new OrderLineId(10L, 1);
OrderLineId c = new OrderLineId(10L, 1);

assertTrue(a.equals(b));
assertTrue(b.equals(c));
assertTrue(a.equals(c));

assertEquals(a.hashCode(), b.hashCode());
```

Ở đây cả `orderId` và `lineNo` **được gán đầy đủ và ổn định**. Nếu dùng `@MapsId` để đưa FK cha vào `EmbeddedId`, một thành phần khóa có thể bắt đầu `null` rồi được Hibernate đồng bộ từ parent sau persist/flush. **Không đưa object `OrderLineId` còn thiếu thành phần vào `HashMap`/`HashSet` rồi thay trường ID**; nguy cơ đổi hash cũng xuất hiện với embeddable ID.

### 18.1. Tránh so khóa ghép bằng entity associations

Lớp composite ID portable nên chứa **các giá trị khóa**, không nên dựa vào `@ManyToOne` bên trong để lấy equality qua proxy. Điều đó có thể kích hoạt lazy loading, tạo vòng lặp khi các entity liên quan cũng dùng associations trong equality, và làm việc so khóa đơn giản trở nên phức tạp.

## 19. Không đưa association và collection LAZY vào equals

Một cài đặt nguy hiểm:

```java
@Override
public boolean equals(Object other) {
    if (!(other instanceof Customer that)) return false;

    return Objects.equals(name, that.name)
        && Objects.equals(orders, that.orders);
}
```

Các hệ quả:

1. `orders` là lazy collection, nên so sánh có thể phát SQL hoặc ném `LazyInitializationException` sau khi session đóng.
2. Nếu `Order` tham chiếu ngược `Customer`, Lombok hoặc IDE-generated `equals()` có thể gây **đệ quy vô hạn/StackOverflowError**.
3. Collection mutable làm equality thay đổi sau thao tác add/remove.
4. `hashCode()` có thể duyệt cả graph dữ liệu, gây N+1 và rất chậm.
5. Hai object cùng primary key nhưng có collection tải khác nhau có thể bị coi không bằng.

**Entity identity equality** thường chỉ cần type + ID đã gán, hoặc **một business key bất biến**. Không thêm association/collection chỉ vì IDE/Lombok gợi ý “include all fields”.

### 19.1. Lombok `@Data` và `@EqualsAndHashCode`

`@Data` bao gồm các behavior sinh `equals()`/`hashCode()` theo field. Trên JPA entity có generated ID, lazy relationships và mutable fields, mặc định đó có thể không phải hợp đồng mong muốn.

Nếu dùng Lombok, cần chỉ định **chính xác** thuộc tính tham gia equality và hiểu các vấn đề proxy, null ID và hash stability. Không copy `@Data` vào entity rồi dựa vào unit test một object managed duy nhất để kết luận đúng.

## 20. So sánh giá trị trong business key cũng phải nhất quán

Ngay cả khi không có proxy hay generated ID, key component vẫn có thể có đặc điểm Java khác SQL.

Ví dụ `BigDecimal`:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

a.equals(b);        // false: scale khác nhau.
a.compareTo(b) == 0; // true: giá trị số học bằng nhau.
```

Nếu một entity dùng business key chứa `BigDecimal` và `equals()` so bằng `compareTo() == 0`, **`hashCode()` phải được xây từ một biểu diễn đã chuẩn hóa tương thích**. Không thể dùng `BigDecimal.hashCode()` thô cho hai giá trị mà equality coi bằng nhưng scale khác nhau, vì sẽ vi phạm equals ⇒ same hash.

Tương tự:

- String có thể được database so không phân biệt hoa/thường theo collation, nhưng `String.equals()` phân biệt.
- Thời gian `Timestamp`/`Instant` có thể bị database cắt precision, tạo chênh lệch giữa object trước và sau persist.
- `double`/`float` xấp xỉ có thể không phù hợp làm khóa.
- UUID/case-insensitive identifier cần một chính sách chuẩn hóa duy nhất giữa Java và schema.

**Test phải bao gồm cả dữ liệu ở ranh giới Java ↔ JDBC ↔ SQL**, đặc biệt khi chọn business key thay vì generated ID.

## 21. So sánh `getClass()` và `instanceof`: chọn theo domain

Hai cách được thấy nhiều:

```java
// A: kiểm tra class chính xác
if (getClass() != other.getClass()) return false;

// B: kiểm tra có cùng supertype
if (!(other instanceof PurchaseOrder)) return false;
```

Không có một lựa chọn đơn giản luôn đúng:

| Cách | Lợi ích | Rủi ro |
| --- | --- | --- |
| `getClass()` | Không coi hai subclass khác nhau là cùng type | Hibernate proxy subclass có thể làm false dù same row |
| `instanceof` | Thường chấp nhận proxy của entity | Trong entity hierarchy có thể coi subtype khác nhau là bằng |
| Hibernate proxy-aware persistent type | So theo mapped class thay vì proxy runtime class | Phụ thuộc Hibernate API/version và inheritance strategy |
| Business key equality | Có thể ổn định trước persist | Cần key duy nhất, bất biến, chuẩn hóa và proxy-safe |

Với entity hierarchy, còn phải cân nhắc **ID uniqueness scope**: các subclass của cùng entity root có thể dùng chung khóa; entity roots độc lập có thể trùng số ID. Vì vậy `id=10` ở `PurchaseOrder` **không có nghĩa** bằng `id=10` ở `Customer`.

Bộ test nên có:

```text
PurchaseOrder(id=10) vs PurchaseOrder proxy(id=10)  → true theo ID equality
PurchaseOrder(id=10) vs Customer(id=10)             → false
SubtypeA(id=10) vs SubtypeB(id=10)                  → theo policy hierarchy, nhất quán
```

Đặc biệt phải kiểm tra symmetry ở hai chiều của mọi cặp.

## 22. Một bảng kịch bản test tối thiểu cho entity generated ID

| Case | Đối tượng A | Đối tượng B | Kỳ vọng với chiến lược type + non-null ID |
| --- | --- | --- | --- |
| 1 | `new A(id=null)` | Chính A | `equals=true` |
| 2 | `new A(id=null)` | `new B(id=null)` | `equals=false` |
| 3 | `new A(id=null)` | `null` | `equals=false` |
| 4 | A trước persist | A sau khi gán ID | Hash của **cùng object** không đổi |
| 5 | A trước persist đã nằm trong `HashSet` | A sau flush | `set.contains(A)=true` |
| 6 | A managed | `em.find(A.id)` trong cùng context | Thường cùng reference |
| 7 | A detached | B loaded cùng ID ở context khác | `equals` hai chiều `true` |
| 8 | A loaded | B proxy cùng ID | `equals` hai chiều `true`; hash giống |
| 9 | A, B, C cùng ID khác contexts | So ba cặp | Bắc cầu và đối xứng |
| 10 | A cùng type, ID khác B | B | `equals=false` |
| 11 | A type X, ID=10 | B type Y, ID=10 | `equals=false` nếu policy tách entity types |
| 12 | A detached | `merge(A)` trả managed B | Cùng identity, equality theo policy |
| 13 | A managed | B managed cùng ID trong context khác | Không cần `==`; equality theo identity |
| 14 | A sau remove | Object đã load trước remove cùng ID | `equals()` có thể vẫn true; không đại diện tồn tại DB |
| 15 | A trong `HashMap` trước persist | A sau flush | `map.get(A)` còn đọc được |

Bảng là **đặc tả test behavior**, không phải kết quả kiểm thử đã chạy.

### 22.1. Khi nào kỳ vọng khác?

- Với **business key equality**, hai object transient có cùng key bất biến có thể bằng nhau trước persist.
- Với **reference equality** (`Object.equals` mặc định), hai object từ hai persistence contexts không bằng nhau dù same primary key.
- Với **assigned UUID** từ constructor, entity có ID ngay khi tạo; test `id==null` không áp dụng.
- Với **composite ID**, equality và hash cần kiểm tra cả lớp ID, đặc biệt thời điểm một phần khóa đến từ `@MapsId`.

Chọn **một policy rõ ràng** rồi test theo policy; đừng trộn các kỳ vọng của nhiều chiến lược vào cùng một entity.

## 23. Property-based tests và kiểm thử mở rộng

Những test ví dụ ở trên dùng ba object cố định. Với hệ thống có nhiều entity/subtype, có thể dùng **property-based testing** để sinh hàng loạt tổ hợp:

```text
Cho mọi x không null:
    equals(x,x) = true
    equals(x,null) = false

Cho mọi cặp x,y:
    equals(x,y) = equals(y,x)

Cho mọi bộ ba x,y,z:
    nếu equals(x,y) và equals(y,z) thì equals(x,z)

Cho mọi cặp x,y:
    nếu equals(x,y) thì hash(x) = hash(y)

Cho mọi entity được đưa vào Set trước persist:
    contains(entity) vẫn đúng sau persist + flush
```

Không sinh ngẫu nhiên các trạng thái ORM một cách không kiểm soát, vì test sẽ dễ tạo transient entity thiếu constraint, transaction bị rollback hoặc proxy trỏ tới hàng không tồn tại. Nên tách:

1. **Unit property tests** cho hợp đồng Java với object giả định hợp lệ.
2. **Integration tests** cho vòng đời ORM và proxy với database thực.
3. **Concurrency tests** khi identity/natural key có thể bị tạo trùng hoặc thay đổi bởi nhiều transaction.

Thư viện như EqualsVerifier có thể giúp phát hiện một số lỗi của `equals()/hashCode()` thông thường, nhưng **không thay thế integration test Hibernate proxy + persist + detach**. Tương tự, JUnit tests thành công trên H2 không bảo đảm mapping/timing sinh ID giống PostgreSQL/Oracle production.

## 24. Chiến lược kiểm thử hiệu quả trong dự án Hibernate

Một quy trình từ dễ đến khó:

### Bước 1 — Viết rõ quy tắc identity

Ví dụ:

```text
PurchaseOrder:
    Entity type: PurchaseOrder
    ID: Long do database sinh
    Equality: cùng instance hoặc cùng type + cùng ID khác null
    Hash: ổn định theo class từ lúc new
```

Hoặc:

```text
Country:
    ID: isoCode được gán lúc tạo
    Equality: cùng mã quốc gia chuẩn hóa
    Hash: dựa trên isoCode bất biến
```

### Bước 2 — Viết unit tests cho Java contract

Kiểm tra reflexive, null, symmetry, transitivity với object hợp lệ; kiểm tra equal hash. Không chỉ test kết quả của `equals()` theo một chiều.

### Bước 3 — Test hai transient entity

Đặc biệt quan trọng với generated ID null: chúng **không** được coi bằng nhau theo ID-based equality.

### Bước 4 — Test hash collections trước và sau persist

Cho object vào `HashSet`/`HashMap` trước `persist`, rồi `flush`. Hash không được đổi nếu entity vẫn được dùng làm key. Kiểm tra `contains`, `get`, `remove`.

### Bước 5 — Test nhiều persistence contexts

Dùng ID đã commit để `find()` từ hai hoặc ba `EntityManager` khác nhau, kiểm tra same identity nhưng different references, tính đối xứng/bắc cầu/hash.

### Bước 6 — Test proxy

Dùng `getReference` từ context khác và kiểm tra cả hai chiều; quan sát xem equality có khởi tạo proxy ngoài dự kiến không. Test cả tình huống session đã đóng nếu chính sách equality mong không cần tải thêm ngoài ID.

### Bước 7 — Test detached và merge

Kiểm tra `merge()` trả managed copy khác reference nhưng cùng identity; object đầu vào vẫn detached. Với `@EmbeddedId`, kiểm tra key đã ổn định trước khi dùng làm hash key.

### Bước 8 — Test inheritance và dữ liệu biên

Thêm các cặp type khác nhau cùng ID, composite IDs, business keys có chữ hoa/thường, `BigDecimal` khác scale hoặc timestamp precision khác nhau.

### Bước 9 — Test với database và mapping production-like

Chạy trên DBMS/driver tương đồng production, vì hành vi sinh ID và kiểu dữ liệu có thể khác giữa database. Kiểm tra schema constraint và thời điểm flush thực tế.

## 25. Những hiểu nhầm thường gặp

**“Hai `find()` cùng ID luôn cho cùng Java object.”** Chỉ có bảo đảm identity map trong **cùng persistence context**. Hai context có thể tạo hai objects khác references.

**“Có `@Id` thì Hibernate tự override `equals()`.”** Không. JPA/Hibernate không tự viết policy `equals()/hashCode()` cho entity Java của bạn.

**“ID null ở hai entity mới nghĩa là hai entity bằng nhau.”** Không, nếu strategy equality dựa trên generated ID. `null` không phải một khóa đại diện một hàng.

**“Hash code nên luôn lấy theo ID, vì database dùng PK.”** Không nếu ID được cấp sau khi object đã vào `HashSet`/`HashMap`.

**“Chỉ cần test `a.equals(b)` là đã test đối xứng.”** Không; phải test cả `b.equals(a)`.

**“Cùng hash code nghĩa là equals true.”** Sai. Hash collision hợp lệ.

**“Một entity proxy có `getClass()` khác entity thật thì chắc chắn là entity khác.”** Sai; proxy thường là đại diện của cùng persistent identity.

**“Chỉ cần dựa vào toàn bộ field để equals chính xác hơn.”** Không; các field mutable/lazy/association có thể làm equality bất ổn và phát SQL.

**“Sau `merge()`, object detached trở thành managed.”** Sai; `merge()` trả managed object, còn object đầu vào giữ trạng thái detached.

**“`flush()` đã commit, có thể load từ context khác.”** Sai; commit phụ thuộc transaction, isolation. Không dựa vào uncommitted dữ liệu để so cross-context.

**“Hai object equals true nghĩa là hàng còn tồn tại ở database.”** Không; equality là quy tắc Java, không xác minh existence, trạng thái soft-delete hoặc transaction.

## 26. Bài tập tình huống

### Tình huống A — Hai `Order` mới

```java
Order a = new Order();
Order b = new Order();
```

Cả hai ID đều null. Hàm equals của chúng là `Objects.equals(id, other.id)`. Kết quả nào sai?

**Đáp án:** `a.equals(b)` sẽ true dù hai object khác nhau. Cần guard `id != null` khi dùng generated ID equality, ngoài trường hợp `this == other`.

### Tình huống B — HashSet sau khi persist

Một object có `hashCode()` trả `id.hashCode()` khi ID khác null, trả `0` trước persist. `set.contains(entity)` false sau flush. Nguyên nhân?

**Đáp án:** Object được đặt vào bucket hash cũ khi ID null; hash thay đổi khi provider cấp ID. Dùng hash ổn định từ lúc object tham gia collection hoặc không dùng entity với ID chưa ổn định làm hash key.

### Tình huống C — JPA context identity

```java
Entity x = em.find(Entity.class, 5L);
Entity y = em.find(Entity.class, 5L);
```

Có nên dùng case này làm bằng chứng equality đúng giữa hai context?

**Đáp án:** Không. Trong một persistence context, `x` và `y` thường cùng reference. `Object.equals()` mặc định cũng qua; phải tải từ context khác để kiểm tra ID-based equality.

### Tình huống D — Symmetry với subclass

Base class so bằng `instanceof Base`, subclass yêu cầu `instanceof Subclass` và thêm field. Điều gì có thể xảy ra?

**Đáp án:** `base.equals(subclass)=true` nhưng `subclass.equals(base)=false`. Cần policy equality chung cho hierarchy và test cả hai chiều.

### Tình huống E — Ba context

Ba instance A, B, C của cùng entity ID được load ở ba context. `A.equals(B)=true` và `B.equals(C)=true`, nhưng `A.equals(C)=false`. Lỗi gì?

**Đáp án:** Vi phạm **tính bắc cầu**. Điều tra logic type, ID, proxy, subclass và các mutable fields tham gia so sánh.

### Tình huống F — Hibernate proxy

`actual.getClass()` khác `proxy.getClass()` dù cùng hàng. Có nên cho equals trả false ngay không?

**Đáp án:** Nếu policy là equality theo persistent identity thì không. Cần so type theo cách hiểu proxy và test đối xứng/không phát SQL ngoài dự kiến với cấu hình Hibernate thực.

### Tình huống G — Merge detached

`managed = em.merge(detached)` trả object khác reference. Equality theo ID nên như thế nào?

**Đáp án:** Nếu cả hai là cùng persistent type với cùng ID không null, `detached.equals(managed)` và chiều ngược phải true; hash cũng phải bằng nhau theo hợp đồng.

### Tình huống H — Business key thay đổi

Một entity dùng `email` làm equality/hash nhưng email có thể được sửa, và entity đang ở trong `HashSet`. Rủi ro?

**Đáp án:** Hash thay đổi gây `contains/remove` thất bại. Cần business key thực sự bất biến hoặc đổi chiến lược identity/collection.

### Tình huống I — Same PK ở hai entity types

`Customer(id=10)` và `PurchaseOrder(id=10)` có bằng nhau không?

**Đáp án:** Không theo chiến lược entity type + ID. ID số bằng nhau ở hai entity roots khác nhau không làm hai objects biểu diễn cùng persistent identity.

### Tình huống J — Composite ID và `@MapsId`

Một `OrderLineId` được cho vào HashMap khi `orderId=null`, sau đó Hibernate điền `orderId=200`. Kết quả?

**Đáp án:** Nếu `hashCode()` của `OrderLineId` dựa trên `orderId`, hash của key thay đổi và lookup có thể sai. Chỉ dùng ID ghép làm map key sau khi đầy đủ thành phần khóa, hoặc dùng một immutable key snapshot đã chuẩn hóa.

## 27. Tài liệu tham khảo

- [Java SE `Object.equals()` và `hashCode()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html): hợp đồng phản xạ, đối xứng, bắc cầu, nhất quán và quan hệ giữa equals/hash.
- [Hibernate ORM User Guide — Implementing equals() and hashCode()](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#mapping-model-pojo-equalshashcode): ví dụ business key, generated ID và hash collection.
- [Hibernate ORM 7.2 User Guide](https://docs.hibernate.org/orm/7.2/userguide/html_single/): mô hình entity, persistent identity, equality, proxy và lifecycle; đọc phần tương ứng theo version.
- [Hibernate Javadoc — `HibernateProxy`](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/proxy/HibernateProxy.html): cách nhận biết proxy và truy cập lazy initializer.
- [Jakarta Persistence Specification 3.2](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): entity identity, lifecycle (`persist`, `merge`, `detach`), primary key và composite identifiers.
- [Jakarta Persistence API `EntityManager`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/entitymanager): `find`, `getReference`, `persist`, `flush`, `clear`, `merge`.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): cấu trúc unit/integration tests, assertions và lifecycle test fixture.

## Kết luận

Đúng `equals()`/`hashCode()` với Hibernate không chỉ là so hai object có cùng ID sau khi database đã lưu. Cần xác định chính sách **reference identity, persistent identity và business equality**, rồi kiểm thử **tính phản xạ, đối xứng, bắc cầu, nhất quán và hợp đồng hash code**.

Với entity có **generated ID**, hai object khác nhau cùng `id=null` không được mặc nhiên bằng nhau; đồng thời `hashCode()` không nên đổi sau persist nếu entity đã nằm trong `HashSet`/`HashMap`. Với hai object từ các **persistence context khác nhau**, detached/managed và proxy, phải kiểm tra đối xứng và bắc cầu bằng các instance khác reference nhưng cùng persistent identity. Với **business key** hoặc **composite ID**, chỉ sử dụng các thành phần khóa ổn định, chuẩn hóa và nhất quán với database.

Một bộ unit tests cho Java contract kết hợp integration tests **new → persist → flush → commit → detach → find/getReference → merge** sẽ phát hiện các lỗi mà test một entity managed trong cùng `EntityManager` thường bỏ sót.
