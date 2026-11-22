# Cấu hình SharedCacheMode và Cacheable

Trong JPA, **bộ nhớ đệm** (*cache*) có thể giúp giảm số lượt đọc database và tránh phải tái tạo cùng một trạng thái entity nhiều lần. Tuy nhiên, từ “cache” dễ gây hiểu nhầm: JPA luôn có cơ chế quản lý entity trong **persistence context** (thường được gọi là cache cấp một), còn **shared cache** (thường được gọi là cache cấp hai) là một khả năng **tùy chọn**, được chia sẻ ở phạm vi rộng hơn một `EntityManager`.

Hai cấu hình chuẩn quan trọng để biểu đạt chính sách shared cache là:

- **`SharedCacheMode`**: chọn chính sách mặc định ở phạm vi **persistence unit**.
- **`@Cacheable`**: khai báo khả năng cache của một **entity type** khi chế độ chọn lọc có hiệu lực.

Ví dụ:

```java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
@Cacheable(true)
public class Book {
    @Id
    private Long id;
}
```

và cấu hình:

```xml
<shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>
```

Trong chế độ `ENABLE_SELECTIVE`, `@Cacheable(true)` có ý nghĩa **đánh dấu Book đủ điều kiện đưa vào shared cache**. Nhưng điều đó **không hứa rằng mọi lần đọc Book đều cache hit**, không có nghĩa Book luôn được giữ vĩnh viễn và không biến cache thành nơi lưu dữ liệu có tính nhất quán mạnh độc lập với database.

Bài **“Cấu hình SharedCacheMode và Cacheable”** thuộc chương **Bộ nhớ đệm**, chủ đề **Data Persistence Relational Access ORM JPA**. Nội dung hướng dẫn phân biệt cache cấp một/cấp hai, nắm vững năm giá trị `SharedCacheMode`, giải thích tương tác với `@Cacheable`, cấu hình `persistence.xml`, lựa chọn cho dữ liệu ít biến động hoặc nhạy cảm, các hint đọc/ghi cache, API `EntityManagerFactory.getCache()`, lưu ý về bulk SQL và môi trường nhiều node, cùng cách kiểm thử hiệu lực cấu hình.

Các ví dụ sử dụng Jakarta Persistence (`jakarta.persistence`) với Java 17+. Với hệ thống JPA cũ, thay package bằng `javax.persistence` và dùng đúng namespace cấu hình/hint tương ứng. Những khả năng triển khai cache region, TTL, chiến lược đồng bộ, thống kê hoặc query cache cụ thể thuộc **provider** (Hibernate, EclipseLink, v.v.) và hạ tầng cache, **không phải cam kết chung của JPA**.

---

## 1. Trước hết phải phân biệt hai cấp cache

Xét một transaction đọc Book #42 hai lần:

```java
EntityManager em = emf.createEntityManager();

Book a = em.find(Book.class, 42L);
Book b = em.find(Book.class, 42L);

System.out.println(a == b); // Thường true trong cùng persistence context.
```

Trong cùng persistence context, JPA duy trì nguyên tắc nhận diện cùng persistent identity và thường tái sử dụng managed instance. Đây là đặc tính của **cache cấp một / identity map**.

Nó **không chứng minh** shared cache đã được bật.

Thử với hai EntityManager:

```java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();

try {
    Book one = em1.find(Book.class, 42L);
    Book two = em2.find(Book.class, 42L);

    // Thường là hai Java objects managed bởi hai contexts khác nhau.
    System.out.println(one == two); // Không mong đợi cùng instance.
} finally {
    em1.close();
    em2.close();
}
```

Nếu shared cache có hiệu lực, provider có thể dùng dữ liệu đã cache khi `em2` tải Book, giảm SQL/đọc DB. Dù vậy, `em1` và `em2` vẫn có **persistence contexts độc lập**: `Book` của hai context không vì shared cache mà trở thành một Java object managed dùng chung.

### Sơ đồ

```text
                 EntityManagerFactory / persistence unit
                                  │
                      Shared cache (L2, optional)
                         ┌────────┴────────┐
                         │                 │
                  EntityManager 1    EntityManager 2
                  Persistence       Persistence
                  Context 1 (L1)   Context 2 (L1)
                         │                 │
                    Book #42 A         Book #42 B
                         │                 │
                         └────────┬────────┘
                                  │
                               Database
```

**`SharedCacheMode` và `@Cacheable` điều khiển chính sách shared cache, không tắt identity map bắt buộc của mỗi persistence context.**

## 2. Bảng phân biệt L1 và L2

| Tiêu chí | Persistence context / L1 | Shared cache / L2 |
| --- | --- | --- |
| Phạm vi | Một `EntityManager`/context | Thường chia sẻ giữa các context thuộc một `EntityManagerFactory` hoặc hạ tầng rộng hơn theo provider |
| Là đặc tính nền tảng của JPA? | Có, vì gắn với entity management | Tùy chọn |
| Giữ managed instances? | Có | Không phải một context quản lý entity chung |
| Cùng entity ID trong một context có chung representative? | Có | Không làm hai contexts dùng chung Java instance |
| Dirty checking? | Có trên managed entity | Không thay thế dirty checking |
| `em.clear()` tác động? | Detach managed entities khỏi context | Không phải thao tác evict toàn shared cache |
| `emf.getCache().evict(...)` tác động? | Không tự detach managed instance | Yêu cầu evict entry/type trong shared cache |
| Được điều khiển bởi `SharedCacheMode`? | Không | Có |
| Được đánh dấu bằng `@Cacheable`? | Không | Có khi chế độ liên quan |
| Có thể bị stale khi DB thay đổi bên ngoài ORM? | Có | Có |
| Có thể cấu hình TTL/region? | Không theo cùng nghĩa | Tùy provider/cache backend |

Một nguyên tắc quan trọng: **“L2 miss” không có nghĩa mỗi `find()` sẽ phát SQL nếu object vẫn managed trong L1**. Khi đo shared cache, phải dùng persistence contexts mới hoặc xóa context có chủ đích.

## 3. Shared cache lưu gì?

Ở mức khái niệm, shared cache có thể giữ biểu diễn của **persistent state** theo entity type và identifier để một persistence context mới không phải truy vấn database cho mỗi lần nạp entity.

Nó không phải:

- Một bản sao thứ hai của toàn bộ `EntityManager`.
- Một nơi giữ mọi entity Java managed và mọi pending changes.
- Một kho dữ liệu thay thế database.
- Một transactional outbox.
- Một cách bảo đảm đọc mới nhất trên mọi node.
- Một cơ chế khóa đồng thời thay cho `@Version` hoặc database locking.
- Một nơi mặc nhiên cache mọi JPQL/native result list.
- Một bộ nhớ đệm tự động cho mọi association collection.

Ví dụ Book có Author và Reviews, việc Book đủ điều kiện L2 **không đồng nghĩa toàn bộ graph Book–Author–Reviews được cache như một khối nguyên tử**. Provider có thể quản lý các region/cấu trúc riêng cho entity, collection hoặc natural ID.

### Shared cache không tự bỏ qua transaction

Ngay cả khi dữ liệu lấy từ cache, entity được nạp vào persistence context vẫn chịu lifecycle của JPA. Khi sửa Book managed và commit, provider xử lý dirty checking, versioning và cập nhật database theo semantics ứng dụng. Cache không có quyền tự tuyên bố transaction thành công thay database.

## 4. Năm giá trị của `SharedCacheMode`

JPA có enum:

```java
import jakarta.persistence.SharedCacheMode;
```

Các giá trị:

```java
SharedCacheMode.ALL
SharedCacheMode.NONE
SharedCacheMode.ENABLE_SELECTIVE
SharedCacheMode.DISABLE_SELECTIVE
SharedCacheMode.UNSPECIFIED
```

Ý nghĩa tổng quan:

| Giá trị | Chính sách đối với entity types |
| --- | --- |
| `ALL` | Tất cả entity types được coi là đủ điều kiện shared cache |
| `NONE` | Không entity type nào được shared cache theo chính sách persistence unit |
| `ENABLE_SELECTIVE` | Chỉ các entity types được đánh dấu `@Cacheable(true)` tương ứng mới đủ điều kiện |
| `DISABLE_SELECTIVE` | Các entity types đủ điều kiện theo mặc định, trừ loại được đánh dấu `@Cacheable(false)` |
| `UNSPECIFIED` | Không ấn định chính sách chuẩn cụ thể; provider quyết định behavior |

**Đủ điều kiện cache ≠ chắc chắn luôn có cache entry.** Provider có thể không có L2 backend, entry có thể chưa được nạp, hết hạn, bị eviction, không hỗ trợ vùng tương ứng hoặc bị bypass theo query hints.

Vì thế các bảng sau mô tả **cacheability policy**, không phải phép đo cache hit.

## 5. `SharedCacheMode.ALL`

`ALL` chọn chính sách mọi JPA entity types đều đủ điều kiện cache:

```xml
<shared-cache-mode>ALL</shared-cache-mode>
```

Với Book, Author, Category, InventoryItem:

```text
Book           → cacheable
Author         → cacheable
Category       → cacheable
InventoryItem  → cacheable
```

Theo semantics của `ALL`, chính sách áp cho **mọi entity** chứ không chọn lọc bằng `@Cacheable`.

Điểm phải suy nghĩ:

- Entity thay đổi nhiều cũng được xem đủ điều kiện cache.
- Dữ liệu nhạy cảm hoặc thay đổi ngoài ORM có thể cần tránh cache.
- Hạ tầng L2 vẫn phải được cấu hình và vận hành đúng.
- Lợi ích phụ thuộc access pattern và cache hit ratio.
- Các vùng cache có thể tốn memory và chi phí invalidation cao.

**`ALL` không phải “lựa chọn tốt nhất cho hiệu năng” chỉ vì nó cache mọi entity.**

Nếu một hệ thống có InventoryItem cập nhật rất thường xuyên cùng Category rất ít đổi, `ALL` có thể làm việc giữ và invalidating inventory state đắt hơn lợi ích, trong khi Category cache có ích.

## 6. `SharedCacheMode.NONE`

`NONE` chọn chính sách không shared-cache entity states:

```xml
<shared-cache-mode>NONE</shared-cache-mode>
```

Ngay cả khi Book có:

```java
@Entity
@Cacheable(true)
public class Book {
    // ...
}
```

`NONE` vẫn thể hiện chính sách **không cho entity dùng shared cache** ở persistence unit này. Annotation không được hiểu như quyền bật L2 trái với mode NONE.

Khi nào nên chọn?

- Dữ liệu thay đổi cực thường xuyên, không có cache hit hiệu quả.
- Muốn giảm rủi ro stale state do cập nhật ngoài JPA.
- Hệ thống chưa có cấu hình cache backend phù hợp.
- Đang debug hoặc benchmark sự khác nhau giữa cached/uncached access.
- Ưu tiên tính đơn giản cho persistence unit nhỏ.
- Muốn chủ động đưa caching lên tầng application với key/TTL/invalidation riêng.

Nhưng lưu ý:

```java
Book a = em.find(Book.class, id);
Book b = em.find(Book.class, id);
```

vẫn có thể không phát SQL lần hai **trong cùng persistence context**. `NONE` không vô hiệu hóa L1.

## 7. `SharedCacheMode.ENABLE_SELECTIVE`

`ENABLE_SELECTIVE` phù hợp cách tiếp cận **chỉ bật cache với entity được lựa chọn rõ ràng**.

Cấu hình:

```xml
<shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>
```

Entity:

```java
@Entity
@Cacheable(true)
public class Category {
    @Id
    private Long id;

    private String name;
}
```

Entity khác không khai báo:

```java
@Entity
public class InventoryItem {
    @Id
    private Long id;

    private int quantity;
}
```

Theo chính sách `ENABLE_SELECTIVE`:

- Category được đánh dấu cacheable.
- InventoryItem không được chọn cache chỉ vì là entity.

Một lựa chọn phổ biến là dùng mode này cho các entity đọc nhiều, thay đổi ít và có chính sách cập nhật rõ:

- Category.
- CountryCode.
- ReferenceType.
- Immutable lookup tables.
- Product taxonomy.
- Các thông số cấu hình ít thay đổi trong một phạm vi đã xác định.

Không mặc định cache Customer hoặc Payment chỉ vì muốn giảm SELECT; các entity này có thể thay đổi thường xuyên, liên quan phân quyền hoặc được sửa bên ngoài ORM.

### `@Cacheable` viết trống tương đương true

Annotation:

```java
@Cacheable
```

có giá trị mặc định `true`, nên đối với selective mode có nghĩa tương đương:

```java
@Cacheable(true)
```

Nếu mục tiêu là làm chính sách rõ ràng cho người đọc, dùng `@Cacheable(true)` thường dễ nhận biết hơn.

## 8. `SharedCacheMode.DISABLE_SELECTIVE`

`DISABLE_SELECTIVE` áp dụng hướng ngược:

- Entity types đủ điều kiện shared cache theo mặc định.
- Entity types được đánh dấu `@Cacheable(false)` bị loại khỏi chính sách shared cache.

Ví dụ:

```xml
<shared-cache-mode>DISABLE_SELECTIVE</shared-cache-mode>
```

```java
@Entity
public class Category {
    @Id
    private Long id;
}
```

```java
@Entity
@Cacheable(false)
public class InventoryItem {
    @Id
    private Long id;
}
```

Ở mode này:

```text
Category       → cacheable theo mặc định
InventoryItem  → bị loại bởi @Cacheable(false)
```

Mode này phù hợp khi đa số entity thực sự có lợi từ shared cache, chỉ có một số loại phải tắt.

Tuy nhiên, nó có một rủi ro quản trị: **entity mới được thêm vào model có thể trở thành cacheable nếu không ai chủ động đánh dấu ngược lại**.

Ví dụ nhóm phát triển thêm `PaymentAttempt` nhưng quên `@Cacheable(false)`. Trong `DISABLE_SELECTIVE`, entity mới đó thuộc nhóm đủ điều kiện cache theo mặc định, dù dữ liệu rất dễ thay đổi. Vì vậy code review và policy danh sách ngoại lệ quan trọng.

### So sánh tư duy

`ENABLE_SELECTIVE`:

> Không cache mặc định; muốn cache thì đánh dấu.

`DISABLE_SELECTIVE`:

> Cache mặc định; muốn không cache thì đánh dấu.

Không có một lựa chọn đúng cho mọi dự án. Cần biết tỷ lệ entity phù hợp cache, mức biến động schema và cách nhóm phát triển kiểm soát thay đổi.

## 9. `SharedCacheMode.UNSPECIFIED`

`UNSPECIFIED` có nghĩa chính sách không được xác định tường minh theo một trong bốn chế độ trên, nên **provider có thể chọn cách xử lý**.

Ví dụ:

```xml
<shared-cache-mode>UNSPECIFIED</shared-cache-mode>
```

hoặc trong một cấu hình không nêu shared cache mode, provider có thể sử dụng behavior mặc định tương ứng.

Hệ quả:

- Một provider có thể chọn cách gần selective.
- Provider khác có thể có cấu hình mặc định riêng.
- Provider version hoặc integration framework có thể thay đổi behavior.
- Không nên dựa vào `@Cacheable` và mặc định không được kiểm chứng để suy L2 đã bật/tắt.

Đối với hệ thống cần kiểm soát cacheability rõ, **hãy chọn một trong bốn mode có ý nghĩa tường minh**, thay vì trông chờ behavior của `UNSPECIFIED`.

Khi nâng cấp provider, đây là một trong những setting đáng kiểm tra vì mặc định có thể ảnh hưởng hiệu năng và tính nhất quán.

## 10. Ma trận tương tác `SharedCacheMode` và `@Cacheable`

Giả sử có ba entity classes:

```java
@Entity
@Cacheable(true)
class A {
    @Id Long id;
}

@Entity
@Cacheable(false)
class B {
    @Id Long id;
}

@Entity
class C {
    @Id Long id;
}
```

Ma trận **đủ điều kiện**:

| SharedCacheMode | A: `@Cacheable(true)` | B: `@Cacheable(false)` | C: không annotation |
| --- | --- | --- | --- |
| `ALL` | Có | Có theo mode ALL | Có |
| `NONE` | Không | Không | Không |
| `ENABLE_SELECTIVE` | Có | Không | Không |
| `DISABLE_SELECTIVE` | Có | Không | Có |
| `UNSPECIFIED` | Phụ thuộc provider | Phụ thuộc provider | Phụ thuộc provider |

Đây là bảng quan trọng nhất của bài.

### Đọc bảng đúng cách

- `ALL`: chỉ thị “all entities cacheable”; không dùng `@Cacheable(false)` như cách tắt từng loại trong mode này. Muốn ngoại lệ chọn lọc, chọn `DISABLE_SELECTIVE`.
- `NONE`: chỉ thị “no entities cacheable”; `@Cacheable(true)` không tự bật lại L2.
- `ENABLE_SELECTIVE`: `@Cacheable(true)` mới tạo opt-in rõ ràng.
- `DISABLE_SELECTIVE`: `@Cacheable(false)` tạo opt-out rõ ràng.
- `UNSPECIFIED`: cần kiểm tra provider/config thay vì suy đoán.

### Cacheable không phải cached

Dù A thuộc “Có”:

```java
cache.contains(A.class, someId)
```

vẫn có thể trả `false` nếu A chưa được load, entry đã evict hoặc provider không duy trì L2 entry. Đánh dấu đủ điều kiện không tương đương lời hứa entry đã tồn tại.

## 11. Vai trò chính xác của `@Cacheable`

JPA annotation:

```java
import jakarta.persistence.Cacheable;
```

Thường đặt trên entity:

```java
@Entity
@Cacheable(true)
public class Category {
    // ...
}
```

hoặc:

```java
@Entity
@Cacheable(false)
public class PaymentAttempt {
    // ...
}
```

Ý nghĩa: khai báo **cacheability** của entity type trong shared cache policy liên quan, đặc biệt hai selective modes.

Nó **không**:

- Khởi tạo cache backend.
- Định nghĩa TTL.
- Định nghĩa cache size.
- Chọn distributed cache cluster.
- Chọn eviction policy theo LRU/LFU.
- Bật query result cache.
- Chỉ định consistency strategy (ví dụ READ_WRITE).
- Bắt buộc mọi lần `find` đều cache hit.
- Cache toàn bộ association graph.
- Bỏ qua authorization khi entity được lấy từ cache.

Nếu muốn những khả năng trên, hãy xem tài liệu và cấu hình **JPA provider/cache backend**, không gán chúng cho `@Cacheable`.

## 12. Kế thừa `@Cacheable` trong entity hierarchy

Trong JPA, `@Cacheable` trên một entity có thể được kế thừa trong entity hierarchy và được khai báo lại ở subclass để điều chỉnh cacheability theo quy tắc của specification.

Ví dụ mô hình kế thừa:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
@Cacheable(true)
public class Document {
    @Id
    private Long id;
}

@Entity
public class Manual extends Document {
    private String productCode;
}

@Entity
@Cacheable(false)
public class SensitiveDocument extends Document {
    private String secret;
}
```

Với selective mode, cần hiểu **kế thừa và override của Cacheable** theo mapping đang dùng. Không chỉ kiểm tra annotation nằm trực tiếp trên subclass bằng reflection rồi suy toàn bộ hiệu lực.

Các lưu ý:

- Entity inheritance có thể gồm nhiều physical tables.
- Cache region/entry policy theo inheritance hierarchy có thể là chi tiết provider.
- Một subclass không cacheable không bảo đảm mọi related entity/other class đều không cacheable.
- Nếu entity base class được đánh dấu và subclass đặc biệt chứa dữ liệu nhạy cảm, hãy viết integration test/metadata review riêng.
- Với mapped superclass, khả năng đặt/lan truyền annotation phải được hiểu theo đặc tả và provider tương ứng; ví dụ trên sử dụng một entity base class để tránh nhập nhằng.

Trước khi dùng inheritance phức tạp, hãy thiết kế chính sách cacheability cho toàn hierarchy, không chỉ một class đơn lẻ.

## 13. Cấu hình trong `persistence.xml`

Một ví dụ Jakarta Persistence:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="shopPU"
        transaction-type="RESOURCE_LOCAL">

        <class>com.example.domain.Category</class>
        <class>com.example.domain.Book</class>
        <class>com.example.domain.InventoryItem</class>

        <shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>

        <properties>
            <!-- Datasource/JDBC/provider-specific properties
                 được cấu hình tùy môi trường triển khai. -->
        </properties>
    </persistence-unit>
</persistence>
```

Trong ví dụ:

- `shopPU` là tên persistence unit.
- `RESOURCE_LOCAL` biểu thị transaction do ứng dụng quản lý khi dùng SE/application-managed EntityManager.
- `shared-cache-mode` định nghĩa một chính sách shared cache của persistence unit.
- Danh sách `<class>` chỉ minh họa entity types; dự án thật có thể dùng class scanning hoặc config khác theo môi trường.
- Kết nối database và hạ tầng cache còn phải được cung cấp phù hợp; file mẫu chưa phải cấu hình kết nối có thể chạy độc lập.

### Thay mode

Nếu muốn opt-out:

```xml
<shared-cache-mode>DISABLE_SELECTIVE</shared-cache-mode>
```

Nếu muốn tắt:

```xml
<shared-cache-mode>NONE</shared-cache-mode>
```

Nếu muốn mọi entity đủ điều kiện:

```xml
<shared-cache-mode>ALL</shared-cache-mode>
```

**Chỉ chọn một mode cho persistence unit**, không khai báo nhiều `shared-cache-mode` như các chính sách cộng dồn.

## 14. Namespace Jakarta và Javax

Một dự án dùng Jakarta Persistence 3.x thường có:

```java
import jakarta.persistence.Cacheable;
import jakarta.persistence.SharedCacheMode;
import jakarta.persistence.Cache;
```

Dự án JPA 2.x cũ thường có:

```java
import javax.persistence.Cacheable;
import javax.persistence.SharedCacheMode;
import javax.persistence.Cache;
```

Namespace cấu hình cũng khác.

Jakarta:

```text
jakarta.persistence.cache.retrieveMode
jakarta.persistence.cache.storeMode
jakarta.persistence.sharedCache.mode
```

Javax legacy:

```text
javax.persistence.cache.retrieveMode
javax.persistence.cache.storeMode
javax.persistence.sharedCache.mode
```

Khi nâng cấp Spring Boot/Hibernate/Jakarta Persistence, không chỉ đổi `import` mà cần kiểm tra:

- `persistence.xml` schema/version.
- Annotation package.
- Hints truyền vào `find`/query.
- Hibernate/provider properties.
- Cache backend integration.
- Tests xác minh shared-cache behavior.

Đừng trộn `javax.persistence.Cacheable` với runtime chỉ scan `jakarta.persistence.Cacheable` rồi giả định annotation vẫn được nhận diện.

## 15. Cấu hình bằng bootstrap properties

Ngoài `persistence.xml`, JPA bootstrap có thể nhận properties map khi tạo `EntityManagerFactory`. Một số môi trường cho phép cung cấp shared-cache mode qua key chuẩn:

```java
Map<String, Object> properties = new HashMap<>();

properties.put(
    "jakarta.persistence.sharedCache.mode",
    SharedCacheMode.ENABLE_SELECTIVE
);

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory(
        "shopPU",
        properties
    );
```

Cần tuân thủ contract của Jakarta Persistence version/provider đang dùng về kiểu giá trị property, nguồn cấu hình và thứ tự ưu tiên khi có nhiều nguồn (persistence.xml, bootstrap map, container settings, framework overrides). Đối với dự án chạy trong Spring hoặc application server, **framework/container thường quản lý EntityManagerFactory**, không nên tự bootstrap thêm một factory chỉ để cấu hình cache.

### Tránh nhiều nguồn cấu hình mâu thuẫn

Ví dụ:

```text
persistence.xml: ENABLE_SELECTIVE
framework property: ALL
provider default: UNSPECIFIED
```

Nếu không biết nguồn nào thực sự có hiệu lực, developer có thể nhìn `@Cacheable(false)` và tưởng InventoryItem không được cache, trong khi persistence unit thực chạy ở mode khác.

Nên chọn **một nơi làm nguồn cấu hình chính**, ghi nhận các override theo môi trường và có integration test xác minh chính sách.

## 16. SharedCacheMode không đồng nghĩa L2 backend đã sẵn sàng

Một lỗi cấu hình phổ biến:

```xml
<shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>
```

và:

```java
@Entity
@Cacheable(true)
public class Category {
    // ...
}
```

rồi kết luận cache đã hoạt động hiệu quả.

Trong thực tế, provider có thể cần:

- Bật shared second-level cache.
- Cấu hình cache implementation/region factory.
- Tích hợp JCache (JSR-107) hoặc bộ nhớ đệm tương ứng.
- Thiết lập cache regions.
- Chọn concurrency strategy.
- Có cache provider library trên classpath.
- Cấu hình cache backend TTL/eviction/size.
- Cấu hình cluster/serialization nếu nhiều JVM.
- Phối hợp versioning/transactions/invalidation.

**`SharedCacheMode` mô tả cacheability policy ở cấp chuẩn; hạ tầng thực thi cache có thể là provider-specific.**

Đây là lý do một entity annotated `@Cacheable(true)` vẫn có thể phát SQL ở mỗi EntityManager mới nếu shared cache thực tế không được bật hoặc không được hỗ trợ như bạn nghĩ.

## 17. Phân biệt JPA `@Cacheable` và Hibernate `@Cache`

Hai annotation không giống nhau:

```java
import jakarta.persistence.Cacheable;
```

và, khi dùng Hibernate:

```java
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;
```

Một cấu hình Hibernate thường gặp:

```java
@Entity
@Cacheable
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE
)
public class Category {
    @Id
    private Long id;
}
```

Ý nghĩa tổng quan:

- `@Cacheable`: thông tin cacheability theo JPA.
- `@org.hibernate.annotations.Cache`: cấu hình Hibernate riêng, chẳng hạn concurrency strategy và cache region.
- Hibernate còn cần cache provider/region factory và các settings phù hợp.
- Cách provider kết hợp hai annotation phụ thuộc version/config, không được coi là quy tắc portable của JPA.

Ví dụ trên **không phải mã chạy đầy đủ nếu thiếu backend và mappings**. Dùng để thấy rõ hai tầng cấu hình.

### Về `READ_WRITE`

`CacheConcurrencyStrategy.READ_WRITE` là chiến lược của Hibernate, không phải `LockModeType.PESSIMISTIC_WRITE` của JPA. Chúng giải quyết hai loại vấn đề khác nhau:

- Cache concurrency strategy: đồng bộ/invalidation trạng thái cache.
- Pessimistic DB lock: phối hợp transaction tranh chấp database rows.

Đừng nhầm “READ_WRITE cache” với “khóa đọc/ghi database”.

## 18. Cache query result khác cache entity state

Ví dụ:

```java
List<Book> books = em.createQuery(
    "SELECT b FROM Book b WHERE b.price > :min",
    Book.class
).setParameter("min", new BigDecimal("100000"))
 .getResultList();
```

Ngay cả khi Book cacheable ở L2, provider vẫn có thể phải chạy SQL để biết **những ID nào** phù hợp điều kiện `price > :min`.

Entity cache hữu ích khi tải Book theo ID hoặc hydrate known keys, nhưng không đồng nghĩa query `WHERE`/`ORDER BY`/`COUNT` tự được memoize.

Một số provider như Hibernate có **query cache** riêng, với cấu hình, region và invalidation policy khác. Đó không phải tính năng mà `@Cacheable` một mình bảo đảm.

Bảng:

| Loại cache | Nội dung khái niệm | Có được bật chỉ bằng `@Cacheable`? |
| --- | --- | --- |
| L1 persistence context | Managed entity state/identity map | Không liên quan |
| L2 entity cache | State entity theo type/ID | Chỉ đủ điều kiện theo policy; còn cần provider/backend |
| Collection cache | Trạng thái/keys collection theo mapping provider | Không tự bật cho mọi collection |
| Query result cache | Tập kết quả/IDs của một query cụ thể | Không |
| Application DTO cache | DTO values do ứng dụng cache | Không |
| HTTP/CDN cache | Response HTTP | Không |

### Một SELECT vẫn có thể chạy dù cache hit ở entity

Nếu query phải tìm IDs, nó có thể gửi SQL rồi provider lấy entity state từ L2. Vì vậy phép đo “có chạy một SELECT không” cần phân biệt:

- Query DB để tìm rows/IDs.
- SQL SELECT theo primary key để load một entity.
- Additional SELECT do lazy associations.
- Cache hit/miss của provider.

## 19. `@Cacheable` và quan hệ entity

Giả sử:

```java
@Entity
@Cacheable(true)
public class Book {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Author author;

    @OneToMany(mappedBy = "book")
    private List<Review> reviews;
}
```

**Book cacheable không nghĩa Author và Reviews tự cacheable theo cùng điều kiện**.

Có thể xảy ra:

- Book state được cache.
- Author không cacheable nên phải truy vấn DB khi lazy reference được khởi tạo.
- Reviews collection cần SELECT riêng nếu chưa được khởi tạo/cache bằng cơ chế riêng.
- Entity Book có version cập nhật nhưng cache của một association không được invalidated đúng nếu cập nhật ngoài ORM.
- Một kết quả Book được nạp từ L2 vẫn có thể gây N+1 khi service duyệt liên kết.

Do đó:

> Tối ưu cache không thay thế thiết kế fetch plan, JOIN FETCH, DTO projection hoặc batch loading.

Khi hiệu năng chậm do N+1, việc thêm `@Cacheable(true)` vào Book có thể không xử lý nguyên nhân là mỗi Book đều lazy-load Reviews.

## 20. Cache và `@Version`

Entity có version:

```java
@Entity
@Cacheable(true)
public class Book {

    @Id
    private Long id;

    @Version
    private Long version;

    private String title;
}
```

`@Version` được dùng trong optimistic locking của JPA. Shared cache có thể lưu version/persistent state để phối hợp với provider caching/concurrency strategy.

Nhưng:

- `@Version` không tự bật L2.
- L2 cache không tự thay thế version check.
- Cache hit không chứng minh dữ liệu còn là version mới nhất nếu có writers ngoài ORM.
- Một native SQL UPDATE không tăng `version` có thể làm cached state và optimistic checks thiếu tín hiệu cần thiết.
- Concurrency strategy của provider ảnh hưởng khi cập nhật cache theo transaction.
- Không nên tự chỉnh version của managed entity để “làm cache mới lại”.

Nếu cập nhật nhiều node hoặc ngoài JPA, cần chính sách invalidation rõ, dù entities có version.

## 21. API chuẩn `EntityManagerFactory.getCache()`

JPA cung cấp:

```java
import jakarta.persistence.Cache;

Cache cache = emf.getCache();
```

Một số thao tác:

```java
boolean present = cache.contains(Book.class, 42L);

cache.evict(Book.class, 42L);

cache.evict(Book.class);

cache.evictAll();
```

Diễn giải:

- `contains(Book.class, 42L)`: hỏi shared cache có entry của Book ID đó theo contract của provider không.
- `evict(Book.class, 42L)`: yêu cầu loại một entity instance entry.
- `evict(Book.class)`: yêu cầu loại entries thuộc entity class.
- `evictAll()`: yêu cầu loại tất cả shared cache entries do JPA Cache API quản lý.

Đây là API quan trọng để kiểm thử/hỗ trợ vận hành cache theo cách gần portable hơn provider statistics.

### `getCache()` không bảo đảm có cache thật

Shared cache là optional. Nếu không hỗ trợ hoặc không bật, `Cache` có thể hoạt động kiểu no-op đối với nội dung shared cache. `contains` có thể luôn false; gọi `evict` không đột nhiên bật bộ nhớ đệm.

Vì vậy phải kiểm tra khả năng/provider/config trước khi coi kết quả `contains` là bằng chứng mọi cấu hình đã hiệu quả.

## 22. `Cache.evict(...)` không xóa managed entity trong L1

Giả sử:

```java
Book book = em.find(Book.class, 42L);

emf.getCache().evict(Book.class, 42L);

Book again = em.find(Book.class, 42L);
```

Trong cùng EntityManager, `again` thường vẫn là chính managed Book đó, vì **evict L2 không detach L1**.

Nếu muốn quan sát reload từ DB trong context mới:

```java
emf.getCache().evict(Book.class, 42L);

EntityManager freshEm = emf.createEntityManager();
try {
    Book fresh = freshEm.find(Book.class, 42L);
} finally {
    freshEm.close();
}
```

Nếu `em` cũ còn Book managed, nó không tự được cập nhật sau eviction. Khi muốn đọc lại state của **cùng managed Book**, có thể cân nhắc `em.refresh(book)` ở transaction/context phù hợp; phải hiểu refresh có thể ghi đè local pending changes.

### So sánh

| Cách gọi | L1 | L2 |
| --- | --- | --- |
| `em.clear()` | Detach tất cả managed entities trong context đó | Không tự evict toàn bộ L2 |
| `em.detach(book)` | Detach Book cụ thể | Không tự evict L2 |
| `em.refresh(book)` | Tải lại state cho managed Book | Có thể tác động cache tùy strategy |
| `emf.getCache().evict(Book.class, id)` | Không detach Book đang managed | Evict entry của Book ID |
| `emf.getCache().evictAll()` | Không xóa managed objects hiện hữu | Evict toàn shared cache theo API |

Không dùng `clear` và `evictAll` như hai cách gọi hoán đổi nhau.

## 23. Cache retrieve mode: chọn có đọc từ L2 hay không

JPA có:

```java
import jakarta.persistence.CacheRetrieveMode;
```

Các giá trị phổ biến:

```java
CacheRetrieveMode.USE
CacheRetrieveMode.BYPASS
```

Ý nghĩa:

- `USE`: cho phép sử dụng shared cache khi tìm dữ liệu theo chính sách.
- `BYPASS`: yêu cầu bỏ qua shared cache khi retrieval.

Khi query cần đọc dữ liệu mới thay vì dựa vào shared cache:

```java
Map<String, Object> hints = new HashMap<>();

hints.put(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

Book book = em.find(Book.class, 42L, hints);
```

Nhưng **BYPASS L2 không có nghĩa BYPASS L1**. Nếu Book #42 đã managed trong `em`, provider có thể trả lại managed object theo persistence context identity map mà không đọc lại DB.

### Cách kiểm tra trạng thái database mới

Nếu muốn tránh L1 đã load sẵn:

- Dùng EntityManager mới, kết hợp retrieve bypass khi cần.
- Hoặc refresh managed entity có chủ đích.
- Hoặc `clear()` sau khi đã xử lý pending changes, rồi đọc lại với hints phù hợp.

Không coi query hint L2 là nút “đọc lại DB bất chấp mọi context”.

## 24. Cache store mode: chọn có đưa kết quả vào L2 không

JPA có:

```java
import jakarta.persistence.CacheStoreMode;
```

Các giá trị:

```java
CacheStoreMode.USE
CacheStoreMode.BYPASS
CacheStoreMode.REFRESH
```

Khái quát:

- `USE`: sử dụng shared cache theo chính sách mặc định khi lưu state.
- `BYPASS`: không lưu vào shared cache từ hoạt động tương ứng.
- `REFRESH`: yêu cầu cập nhật/làm mới state cached theo semantics khi lấy dữ liệu phù hợp từ database.

Ví dụ:

```java
Map<String, Object> hints = new HashMap<>();

hints.put(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

hints.put(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
);

Book book = em.find(Book.class, 42L, hints);
```

Đoạn code diễn đạt **bỏ qua entry L2 cũ khi tìm và làm mới shared cache từ dữ liệu nhận được**, trong điều kiện operation, provider và cacheability policy hỗ trợ.

### Hai mode khác hai loại chính sách

`SharedCacheMode` là **persistence-unit cacheability policy**: entity types nào đủ điều kiện cache.

`CacheRetrieveMode` và `CacheStoreMode` là **cách một operation tương tác với shared cache**.

Chúng không hoán đổi nhau. `BYPASS` không tự chuyển một entity không cacheable thành cacheable và `REFRESH` không biến `NONE` thành ALL.

## 25. Hint cho một JPQL query

Ngoài `find`, có thể đặt trên query:

```java
TypedQuery<Book> query = em.createQuery(
    "SELECT b FROM Book b WHERE b.id = :id",
    Book.class
);

query.setParameter("id", 42L);

query.setHint(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

query.setHint(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.BYPASS
);

Book book = query.getSingleResult();
```

Mục đích là tạm thời giảm tương tác với L2 cho query này. Nhưng:

- Nếu Book đã managed trong context, L1 identity map vẫn có hiệu lực.
- Query có thể phải thực thi SQL theo semantics JPQL.
- Provider có thể có query cache extension ngoài entity cache hints.
- Cache hints không phải isolation mode và không tự khóa row.
- Kết quả sau một query không chứng minh cache backend đã tắt cho toàn ứng dụng.

Khi áp dụng hints, ghi rõ chúng thuộc **operation-specific access policy**, không phải cấu hình toàn bộ shared cache.

## 26. Bảng kết hợp mode ở ba lớp

| Lớp | API/Cấu hình | Tác dụng |
| --- | --- | --- |
| Persistence unit | `SharedCacheMode.ENABLE_SELECTIVE` | Quy định entity classes nào đủ điều kiện shared cache |
| Entity type | `@Cacheable(true)` | Đánh dấu entity đủ điều kiện dưới selective mode |
| Operation read | `CacheRetrieveMode.BYPASS` | Không dùng L2 khi lấy dữ liệu của thao tác tương ứng |
| Operation store | `CacheStoreMode.BYPASS` | Không ghi state vào L2 theo hint |
| Operation refresh | `CacheStoreMode.REFRESH` | Yêu cầu cập nhật cached state từ dữ liệu mới theo contract |
| Runtime management | `emf.getCache().evict(...)` | Evict cached entries |
| Context management | `em.clear()` | Detach managed entities khỏi L1 của EntityManager |

Ba lớp chính sách không nên gộp thành một boolean “cache on/off”.

Ví dụ Book `@Cacheable(true)` và `ENABLE_SELECTIVE` chỉ **cho phép cache**. Một request đọc Book với `CacheRetrieveMode.BYPASS` có thể không tận dụng L2 entry hiện tại. Ngược lại, một lần đọc default `USE` có thể cache hit nếu entry hợp lệ và provider hỗ trợ.

## 27. Cấu hình theo nhu cầu dữ liệu

Giả sử ứng dụng có:

```text
Category            ít thay đổi, đọc nhiều
CountryCode         gần như cố định
Book                cập nhật vừa phải
InventoryItem       cập nhật rất thường xuyên
PaymentAttempt      trạng thái giao dịch thay đổi liên tục
CustomerProfile     có yêu cầu cập nhật/xóa dữ liệu nhạy cảm
```

Một policy minh họa:

```xml
<shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>
```

```java
@Entity
@Cacheable(true)
class Category { /* ... */ }

@Entity
@Cacheable(true)
class CountryCode { /* ... */ }

@Entity
class InventoryItem { /* ... */ }

@Entity
class PaymentAttempt { /* ... */ }
```

Book có được cache hay không là quyết định dựa trên load/update patterns; không nên tự động chọn vì nó là entity quan trọng.

### Tiêu chí đánh giá

1. **Read/write ratio:** số lần đọc giữa những lần cập nhật.
2. **Cache hit potential:** nhiều requests đọc lại cùng IDs hay luôn truy cập records mới?
3. **Entry size:** object state lớn hay nhỏ?
4. **Update source:** mọi cập nhật đi qua một provider hay có batch/JDBC/external writers?
5. **Staleness tolerance:** màn hình chấp nhận dữ liệu cũ bao lâu?
6. **Authorization scope:** dữ liệu có phụ thuộc tenant/user không?
7. **Concurrency:** nhiều nodes có cần coherent invalidation không?
8. **Memory/cost:** cache backend có đủ dung lượng không?
9. **Recovery:** khi cache outage, app có tiếp tục đọc database được không?
10. **Observability:** có đo hit/miss/evict rate và DB latency không?

Không nên bật shared cache vì một benchmark nhỏ chỉ có cùng ID được đọc lặp trong một EntityManager; lợi ích ở L2 phải được chứng minh bằng **requests/contexts độc lập**.

## 28. Không cache bằng mọi giá dữ liệu thay đổi nhanh

Ví dụ InventoryItem:

```java
@Entity
@Cacheable(false)
public class InventoryItem {
    @Id
    private Long id;

    @Version
    private Long version;

    private int availableQuantity;
}
```

Trong mode `DISABLE_SELECTIVE`, annotation `false` loại InventoryItem khỏi L2 cacheability. Trong mode `ENABLE_SELECTIVE`, đơn giản không opt-in cũng đủ theo policy; thêm annotation false có thể làm ý định rõ hơn.

Tại sao InventoryItem thường cần thận trọng?

- Số lượng thay đổi liên tục.
- Có thể được cập nhật bởi batch jobs.
- Một số update dùng native SQL có conditional decrement.
- Dữ liệu cũ gây quyết định nghiệp vụ sai.
- Có nhiều concurrent writers cần `@Version`/locks/constraints.

Tuy nhiên, **không cache L2 không tự làm nghiệp vụ tồn kho an toàn**. Vẫn cần transaction, optimistic/pessimistic locking hoặc atomic update và database constraints. L1 và transaction isolation vẫn tồn tại.

## 29. Khi entity chứa dữ liệu nhạy cảm

Một số hệ thống không muốn shared cache giữ một số entity types lâu hơn cần thiết, ví dụ chứa PII hoặc security-sensitive state.

`@Cacheable(false)` dưới `DISABLE_SELECTIVE` hoặc mode `NONE` có thể là một phần policy, nhưng không thay thế:

- Encryption at rest/in memory khi phù hợp.
- TTL/eviction của application cache.
- Phân quyền và tenant isolation.
- Data retention rules.
- Audit cho external cache storage.
- Quy trình xóa dữ liệu/erasure.
- Bảo vệ logs và backups.
- Cơ chế tránh cache những query chứa thông tin nhạy cảm ở các tầng khác.

Đặc biệt, tắt JPA L2 **không tự tắt HTTP, Redis application cache, browser cache hoặc CDN**. Cần xem toàn bộ data flow.

## 30. Môi trường nhiều node: local cache và cluster cache

Một ứng dụng chạy ở một JVM có thể không gặp nhiều vấn đề consistency, nhưng production có nhiều instances:

```text
App Node A           App Node B
  L2 cache A           L2 cache B
       │                    │
       └──────── DB ────────┘
```

Nếu A cập nhật Book và invalidates cache A nhưng B vẫn giữ entry cũ, B có thể trả stale state theo cấu hình.

Một số cache backends hỗ trợ distributed cache hoặc clustered invalidation. Nhưng `SharedCacheMode` và `@Cacheable` **không tự định nghĩa giao thức coherence giữa các JVM**.

Khi dùng nhiều nodes:

- Chọn cache backend có mô hình coherence phù hợp.
- Hiểu invalidation vs replication.
- Thiết kế transaction commit/invalidation ordering.
- Kiểm tra versioned entities.
- Đo stale-read windows.
- Xác định behavior khi network partition.
- Thiết lập TTL nếu policy cho phép eventual freshness.
- Kiểm thử updates từ cả nodes và batch jobs.

**“Cả hai node đều @Cacheable” không có nghĩa chúng tự chia sẻ một vùng nhớ nhất quán.**

## 31. Cập nhật qua JPA managed entity

Khi một entity cached được cập nhật bình thường:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("Tên mới");

em.getTransaction().commit();
```

JPA provider có trách nhiệm thực hiện entity lifecycle và quản lý cache interactions theo cache configuration/concurrency strategy hỗ trợ.

Nhưng không nên suy ra provider luôn cập nhật L2 **ngay tại setter**. Thời điểm flush/commit ảnh hưởng dữ liệu nào được xem là committed, và transaction rollback không được biến cached state thành giá trị đã được lưu.

Đối với consistency nhạy cảm, hãy xem provider cache concurrency strategy và kiểm thử với transaction commit/rollback thực tế.

### `flush()` không phải commit

```java
book.rename("Mới");
em.flush();
```

SQL có thể đã chạy trong transaction nhưng vẫn chưa commit. Không kết luận shared cache đã có state “Mới” cho mọi transaction chỉ vì flush hoàn tất.

## 32. Cập nhật ngoài JPA có thể khiến L2 stale

Giả sử một job JDBC:

```sql
UPDATE books
SET title = 'Tên mới từ batch'
WHERE id = 42;
```

Nếu Book #42 nằm trong shared cache của JPA provider, một transaction mới dùng `em.find(Book.class, 42L)` có thể nhận state cũ nếu cache entry không được invalidated theo cơ chế phù hợp.

Tại sao?

- SQL được thực thi **ngoài ORM awareness**.
- Provider không nhất thiết biết lúc nào job external commit.
- Cache backend không tự hiểu arbitrary SQL.
- `@Version` không được tăng nếu SQL không thực hiện điều đó.
- Nhiều nodes có thể giữ cached entries độc lập.

Biện pháp:

1. Ưu tiên thống nhất đường ghi khi có thể.
2. Thiết kế invalidation sau commit của external writer.
3. Nếu DB thay đổi qua event stream, phát event mang entity IDs/types cần evict.
4. Dùng cache TTL khi chấp nhận một khoảng stale.
5. Dùng bypass/refresh cho use case yêu cầu đọc mới.
6. Duy trì version/optimistic-locking discipline trong các native/bulk writes.
7. Kiểm chứng trên provider/cache backend cụ thể.

Không nên tin `@Cacheable(true)` và `@Version` tự phối hợp mọi SQL ở bất kỳ hệ thống nào.

## 33. Bulk JPQL và native SQL cũng cần xem cache invalidation

Trong JPA:

```java
int changed = em.createQuery(
    "UPDATE Book b " +
    "SET b.title = :title " +
    "WHERE b.id = :id"
).setParameter("title", "Bulk change")
 .setParameter("id", 42L)
 .executeUpdate();
```

hoặc:

```java
int changed = em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, "Native change")
 .setParameter(2, 42L)
 .executeUpdate();
```

Bulk DML không đi qua từng managed entity theo cách dirty checking thông thường. Hệ quả:

- L1 managed Book có thể stale.
- Shared cache invalidation phụ thuộc provider và mức provider biết những bảng/entity bị ảnh hưởng.
- Một số provider có cơ chế evict/refresh automatic cho bulk JPQL/native DML, nhưng không nên suy chúng áp dụng đủ cho mọi custom SQL/stored procedure.
- Native SQL không tự tăng `@Version` nếu không viết trong SQL.
- Query cache hoặc application DTO cache có thể cần invalidation riêng.

### Một chiến lược có ý định rõ

Sau bulk update có phạm vi biết được, có thể:

```java
em.flush(); // Chỉ khi cần đồng bộ pending changes hợp lệ trước bulk DML.

int count = em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, newTitle)
 .setParameter(2, id)
 .executeUpdate();

em.clear(); // Bỏ state L1 có thể stale nếu chấp nhận detach toàn context.
```

Sau transaction commit và tại boundary an toàn, cân nhắc:

```java
emf.getCache().evict(Book.class, id);
```

Nhưng **thứ tự invalidation so với commit và concurrent readers phải được thiết kế cẩn thận**. Ví dụ evict quá sớm trước commit có thể cho transaction khác load và cache lại state cũ; invalidation sau commit hoặc cơ chế transaction-aware cache của provider có thể phù hợp hơn. Đừng sao chép mẫu gọi evict vào giữa transaction rồi coi là bảo đảm mạnh trên mọi cluster.

## 34. Vì sao chỉ gọi `clear()` không giải quyết stale shared cache?

Giả sử Book #42 trong L2 có title “Cũ”. Bạn gọi:

```java
em.clear();
```

Context hiện tại bỏ managed Book. Nhưng nếu shared cache vẫn giữ entry “Cũ”, lần `find()` tiếp theo có thể lấy chính entry đó từ L2.

Muốn tách hai lớp:

```java
em.clear();

emf.getCache().evict(Book.class, 42L);

Book reloaded = em.find(Book.class, 42L);
```

Đoạn này có thể buộc provider đi theo đường không có entry L1/L2 cũ, nhưng vẫn cần xét transaction isolation, cache backend và state DB thật. Nếu đang có dirty changes chưa flush, `clear` có thể bỏ mất chúng. Vì vậy thao tác trên chỉ phù hợp khi người viết hiểu rõ pending state và transaction boundary.

**Clear L1 và evict L2 là hai quyết định độc lập.**

## 35. Vì sao chỉ gọi `evict(Book.class,id)` vẫn có thể đọc giá trị cũ?

Giả sử:

```java
Book book = em.find(Book.class, 42L);

emf.getCache().evict(Book.class, 42L);

Book again = em.find(Book.class, 42L);
```

`again` có thể là cùng Java instance `book` trong L1, với title cũ.

Vì vậy nếu user báo “đã evict cache nhưng giá trị chưa đổi”, hãy hỏi:

- Entity đã managed trong cùng EntityManager chưa?
- Persistence context có extended scope không?
- Có query/DTO cache ở tầng khác không?
- Có database transaction snapshot/isolation không?
- External update đã commit chưa?
- Eviction có chạy trên đúng EntityManagerFactory/node/cache region không?
- Entity inheritance/proxy type có liên quan không?

**Không quy mọi stale read thành L2 cache bug.**

## 36. Cache và native query trả entity

Một native query:

```java
Query query = em.createNativeQuery(
    "SELECT id, version, title, price " +
    "FROM books WHERE id = ?",
    Book.class
);
```

có thể trả managed Book nếu mapping phù hợp. Điều này không có nghĩa native SQL luôn bỏ qua L1/L2 và refresh entity đang managed.

Nếu Book #42 đã managed trong context, provider phải tôn trọng persistence identity semantics. Một native entity result có thể tái sử dụng managed representative.

Ngược lại, native scalar query:

```java
String title = (String) em.createNativeQuery(
    "SELECT title FROM books WHERE id = ?"
).setParameter(1, 42L)
 .getSingleResult();
```

đọc một SQL scalar result; nó không tự thay đổi Book đang managed và cũng không có nghĩa result được cache ở L2 entity cache.

Khi kiểm tra stale state, hãy xác định query trả **scalar, Object[] hay managed entity**.

## 37. Cache không thay thế optimistic locking

`@Version`:

```java
@Entity
@Cacheable(true)
public class Book {
    @Id
    private Long id;

    @Version
    private Long version;
}
```

Nếu hai transactions cùng cập nhật Book, optimistic locking vẫn phải được xét theo JPA semantics. Cache entry không biến database version check thành vô nghĩa.

Các trường hợp cần phân biệt:

- **L2 hit + managed update:** provider vẫn phải đảm bảo update hợp lệ theo transaction/versioning.
- **L2 stale do native SQL ngoài ORM:** version check có thể không phát hiện nếu SQL không tăng version.
- **L1 stale sau bulk DML:** ngay cả khi evict L2, managed object vẫn có thể ghi đè state nếu tiếp tục flush.
- **READ-only caching:** một số provider có strategy phù hợp entity thật sự immutable, nhưng không được dùng với entity thường xuyên bị update.
- **Replica lag:** DB read replica chậm không phải lỗi `SharedCacheMode`; cache bypass cũng không tự loại bỏ lag của replica.

Cache là tối ưu hóa truy cập state, không phải một concurrency-control policy hoàn chỉnh.

## 38. Cấu hình shared cache theo môi trường

Một dự án có thể có:

```text
Development:
  Khối lượng dữ liệu nhỏ
  Đôi khi bật SQL logging

Integration test:
  Test cacheability, eviction và transaction correctness

Production:
  Backend L2 thật
  Nhiều nodes
  Monitoring hit/miss, memory và invalidation
```

Có thể chọn mode khác nhau theo mục tiêu, nhưng cần tránh trường hợp code chỉ được test ở `NONE` trong khi production chạy `ALL` mà không có test cache consistency.

Một chiến lược:

- Unit tests: kiểm tra entity annotations và DTO mappings đơn giản.
- Integration tests không cache: xác minh business semantics.
- Integration tests có cache: xác minh behavior trong mode production.
- Performance tests: đo hit/miss/DB SQL trên nhiều contexts.
- Multi-node tests: xác minh invalidation khi có writer khác.

**Test có L2 thật cần một backend/cache provider giống môi trường production đủ để tái hiện cấu hình quan trọng.**

## 39. Lập kế hoạch thử nghiệm theo ma trận mode

Nếu dự án có hai entity:

```java
@Entity @Cacheable(true)
class Category { /* ... */ }

@Entity @Cacheable(false)
class InventoryItem { /* ... */ }
```

Các tình huống:

| Mode | Category cacheable? | InventoryItem cacheable? | Kết luận cần xác minh |
| --- | --- | --- | --- |
| ALL | Có | Có | ALL áp dụng rộng |
| NONE | Không | Không | Không có shared entity cache |
| ENABLE_SELECTIVE | Có | Không | Opt-in hoạt động |
| DISABLE_SELECTIVE | Có | Không | Opt-out hoạt động |
| UNSPECIFIED | Không biết trước | Không biết trước | Provider-specific default |

Với entity không annotation, bổ sung thêm một test để phân biệt `ENABLE_SELECTIVE` và `DISABLE_SELECTIVE`.

### Đừng kỳ vọng đổi mode runtime trên một EntityManagerFactory

`SharedCacheMode` là cấu hình ở phạm vi persistence unit/EntityManagerFactory. Thay mode trong một test thường có nghĩa tạo một factory/configuration khác và đảm bảo tài nguyên đã đóng hợp lệ. Không dùng `em.setProperty(...)` như cách biến toàn factory từ ALL sang NONE khi nhiều contexts đang chạy.

Khi chạy các test matrix, mỗi cấu hình có thể cần một persistence unit hoặc bootstrap factory riêng.

## 40. Integration test: kiểm tra context identity trước

Một test nền tảng:

```java
@Test
void sameEntityManagerKeepsIdentity() {
    EntityManager em = emf.createEntityManager();

    try {
        Book first = em.find(Book.class, bookId);
        Book second = em.find(Book.class, bookId);

        assertSame(first, second);
    } finally {
        em.close();
    }
}
```

Test này giúp nhớ rằng identity map có hiệu lực **ngay cả khi shared cache mode là NONE**. Vì vậy **không dùng test này làm bằng chứng second-level cache**.

Một anti-pattern:

```java
Book first = em.find(Book.class, id);
Book second = em.find(Book.class, id);

assertEquals(1, sqlCount);
```

rồi kết luận `@Cacheable` đã hoạt động — hoàn toàn có thể chỉ là L1.

## 41. Integration test: đo qua hai EntityManagers

Ví dụ đo lần đọc đầu và lần đọc sau bằng hai contexts khác nhau:

```java
@Test
void cacheabilityCanBeObservedAcrossContexts() {
    emf.getCache().evict(Book.class, bookId);

    EntityManager em1 = emf.createEntityManager();
    try {
        assertNotNull(em1.find(Book.class, bookId));
    } finally {
        em1.close();
    }

    EntityManager em2 = emf.createEntityManager();
    try {
        assertNotNull(em2.find(Book.class, bookId));
    } finally {
        em2.close();
    }

    // Đọc Hibernate/EclipseLink statistics hoặc SQL capture
    // tại đây nếu provider/backend hỗ trợ.
}
```

Điều test này **chưa tự chứng minh cache hit**: nó chỉ thiết lập bối cảnh cho quan sát qua contexts độc lập.

Để kết luận:

- Bật second-level cache thật.
- Cấu hình đúng shared cache mode.
- Chọn entity được cacheable.
- Dùng SQL trace/provider statistics.
- Kiểm tra cache entry hit/miss theo API backend.
- Tránh shared cache bị làm nóng từ fixture/setup.
- Không chạy song song workload làm nhiễu statistics.

Nếu mode NONE hoặc entity không cacheable, SQL thường phát ở mỗi context mới khi không có cơ chế cache khác. Nhưng exact statement count còn phụ thuộc lazy relations, provider fetching và các query khác.

## 42. `Cache.contains` như một phép kiểm tra

Ví dụ:

```java
Cache cache = emf.getCache();

cache.evict(Category.class, categoryId);

boolean before = cache.contains(
    Category.class, categoryId
);

EntityManager em = emf.createEntityManager();
try {
    em.find(Category.class, categoryId);
} finally {
    em.close();
}

boolean after = cache.contains(
    Category.class, categoryId
);
```

Trong một setup L2 active, một lần load có thể khiến `after` thành true. Nhưng:

- Cache entry có thể không được store theo hint/provider policy.
- Provider có thể không hỗ trợ shared caching, `contains` luôn false.
- Entry có thể bị evict do memory pressure hoặc TTL.
- Nếu cache backend có asynchronous operations, timing có thể khác.
- Với entity mapping/inheritance hoặc keys provider-specific, hành vi quan sát cần xác minh.

**Test dựa duy nhất vào `contains` mà không kiểm tra cache backend có chạy thật có thể dẫn tới kết luận sai.**

## 43. Test eviction: đừng dùng cùng context

Một test eviction đúng mục tiêu nên:

1. Đảm bảo cache entry đã có trên provider/backend.
2. Gọi `emf.getCache().evict(EntityClass.class, id)`.
3. Đóng mọi EntityManager dùng để seed/đọc entry, hoặc ít nhất không dùng context đã managed entity để quan sát reload.
4. Mở EntityManager mới.
5. Thực hiện `find`.
6. Đối chiếu SQL/cache statistics, không chỉ getter.

Ví dụ:

```java
@Test
void evictionShouldForceCacheMissInFreshContext() {
    warmCacheWithCommittedCategory(categoryId);

    emf.getCache().evict(
        Category.class,
        categoryId
    );

    EntityManager fresh = emf.createEntityManager();

    try {
        Category category = fresh.find(
            Category.class,
            categoryId
        );

        assertNotNull(category);
    } finally {
        fresh.close();
    }

    // Phần xác minh miss/SQL là provider-specific.
}
```

`warmCacheWithCommittedCategory` phải là helper dùng context/transaction riêng; không giả định fixture không commit có thể làm nóng shared cache theo cùng cách.

## 44. Test store/retrieve bypass

Một test cần kiểm tra các hint:

```java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS,
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.BYPASS
);

EntityManager em = emf.createEntityManager();

try {
    Book book = em.find(
        Book.class,
        bookId,
        hints
    );

    assertNotNull(book);
} finally {
    em.close();
}
```

Khi so sánh với default USE mode, nên dùng:

- Đúng provider/cache backend.
- EntityManager mới mỗi lần.
- Cache entry state được kiểm soát.
- SQL statistics/trace.
- Dữ liệu đã commit và ổn định.
- Không có test khác cùng lúc flush/evict.

**Không nên assert rằng gọi BYPASS trong context đã managed Book sẽ luôn tạo một SELECT**, vì L1 vẫn có thể trả cùng object.

## 45. Test external update làm stale cache

Một scenario giá trị:

1. Seed Book và commit.
2. Bật shared cache, load Book #42 qua một context để có khả năng cache entry.
3. Đóng context.
4. Dùng JDBC hoặc ứng dụng khác cập nhật Book #42 và commit.
5. Dùng EntityManager mới đọc Book theo default cache settings.
6. Quan sát state có thể stale theo provider/backends.
7. Evict Book #42 khỏi shared cache hoặc dùng BYPASS phù hợp.
8. Dùng EntityManager mới khác đọc lại.
9. Xác minh giá trị mới đã commit bằng JDBC/SQL khi cần.

Đây là **scenario test stale/invalidation policy**, không phải assertion portable “mọi provider bắt buộc trả dữ liệu cũ ở bước 5”.

Kết quả phụ thuộc provider/backend và đường cập nhật. Một số hạ tầng cache có TTL/invalidation khác nhau nên có thể thấy dữ liệu mới ngay; điều quan trọng là biết và kiểm soát ranh giới consistency.

### Khi external writer dùng native SQL từ chính provider

Provider có thể nhận ra một số bảng được ảnh hưởng và tự invalidate cache regions theo cơ chế riêng. **Không chuyển một trường hợp Hibernate đã xử lý thành khẳng định JPA chuẩn cho mọi native query**. Kiểm thử từng loại bulk operation thực tế.

## 46. Test bulk update và first-level cache

Một ví dụ kiểm tra sự khác nhau:

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    Book managed = em.find(Book.class, bookId);

    em.createQuery(
        "UPDATE Book b " +
        "SET b.title = :title WHERE b.id = :id"
    ).setParameter("title", "Bulk changed")
     .setParameter("id", bookId)
     .executeUpdate();

    // managed.getTitle() có thể còn state cũ.
    // Cần xác định context/refresh strategy.

    em.getTransaction().commit();
} finally {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    em.close();
}
```

Dù L2 có xử lý invalidation đúng, **L1 của EntityManager đang giữ Book vẫn có thể stale**. Khi debug, tách hai vấn đề:

- “Book managed trong context chưa refresh.”
- “Shared cache entry còn stale sau transaction.”

Không gọi `Cache.evictAll()` để sửa một stale managed Book trong current context. Điều đó làm rỗng L2 rộng mà không thay đổi L1.

## 47. Spring Boot/Hibernate: cấu hình nhiều tầng

Một ứng dụng Spring Data JPA dùng Hibernate có thể có:

```text
Spring Boot application configuration
          │
          ▼
Hibernate/JPA EntityManagerFactory settings
          │
          ├─ SharedCacheMode policy
          ├─ @Cacheable entity metadata
          ├─ Hibernate L2 enabled/region factory
          ├─ Cache backend (JCache/Ehcache/Infinispan/...)
          └─ Hibernate cache regions/concurrency strategies
```

Ví dụ thuộc tính provider-specific quen thuộc:

```properties
hibernate.cache.use_second_level_cache=true
hibernate.cache.region.factory_class=jcache
```

Cú pháp/giá trị chính xác của `region.factory_class` và cách cung cấp cache provider có thể đổi theo Hibernate version. Dùng đúng tài liệu của phiên bản đang triển khai và bảo đảm cache provider library được cài.

Không coi hai dòng minh họa là một cấu hình production hoàn chỉnh: cache regions, provider class, properties, transaction strategy và classpath vẫn có thể cần thêm.

### Spring `@Cacheable` không phải JPA `@Cacheable`

Spring có:

```java
org.springframework.cache.annotation.Cacheable
```

khác với:

```java
jakarta.persistence.Cacheable
```

| Annotation | Đặt ở đâu | Ý nghĩa |
| --- | --- | --- |
| `jakarta.persistence.Cacheable` | Entity class | JPA shared-cache eligibility |
| `org.springframework.cache.annotation.Cacheable` | Method/class theo Spring caching abstraction | Cache kết quả gọi method theo key, cache manager và policy của Spring |
| `org.hibernate.annotations.Cache` | Hibernate entity/collection mapping | Provider-specific L2 cache region/strategy |

Nếu một service method có `@org.springframework.cache.annotation.Cacheable` và trả Book DTO, đó là **application cache**, không thể suy nó thay thế hoặc được điều khiển bởi `SharedCacheMode`.

Ngược lại, nếu entity Category có JPA `@Cacheable(true)`, Spring `@Cacheable` ở service method không tự được bật.

## 48. Monitoring: hit, miss và eviction

Khi bật shared cache, cần đo:

- L2 cache hit count/rate.
- L2 miss count/rate.
- Cache put count.
- Eviction count.
- Cache memory footprint.
- Cache entry TTL/expiry.
- DB SELECT count.
- Response latency và p95/p99.
- Transaction contention.
- Stale-data incidents/invalidation lag.
- GC pressure hoặc remote cache latency.
- Cluster synchronization cost.

Các chỉ số cụ thể là provider/backend-specific. Ví dụ Hibernate có `Statistics` API cho second-level cache metrics, nhưng nó không phải phần API bắt buộc của Jakarta Persistence.

Một cache hit rate cao không tự động tốt nếu:

- Cache hit nhưng sai dữ liệu.
- Mỗi update phải invalidates rất nhiều regions.
- Serialization/network tới distributed cache đắt hơn DB query.
- Cache lưu dữ liệu cực lớn nhưng hiếm dùng.
- Cache hit chỉ xuất hiện do một workload test nhân tạo.

**Đo tính đúng và hiệu năng cùng nhau**.

## 49. Một cache benchmark có ý nghĩa

Không benchmark:

```java
for (int i = 0; i < 10_000; i++) {
    em.find(Book.class, 42L);
}
```

trong **cùng EntityManager** rồi khẳng định L2 giúp giảm 9.999 SELECT. Kết quả đó chủ yếu phản ánh L1 identity map.

Một benchmark L2 có ý nghĩa hơn:

1. Seed dữ liệu và commit.
2. Đóng setup contexts.
3. Chạy nhiều independent EntityManagers/transactions.
4. Phân bố IDs theo workload thực tế (hot IDs và cold IDs).
5. Dùng cache provider/backend production-like.
6. Đo trước/sau warm-up.
7. Có tỷ lệ update/evict thực tế.
8. Có multi-node và latency nếu production có.
9. Đảm bảo DB connection pool/config không thành biến nhiễu.
10. Đo end-to-end latency và memory, không chỉ số SQL.

So sánh mode `NONE` với `ENABLE_SELECTIVE` cùng workload có thể giúp quyết định entity nào đáng cache. Nhưng không chỉ nhìn thẳng số SELECT vì một số query vẫn chạy để chọn IDs.

## 50. Các lỗi thường gặp

### Lỗi 1: Tưởng `SharedCacheMode.NONE` tắt cả L1

Sai. Persistence context vẫn giữ managed entities trong một EntityManager.

### Lỗi 2: Nghĩ `@Cacheable(true)` là đủ bật cache

Sai. Cần mode phù hợp, provider support và hạ tầng L2.

### Lỗi 3: Dùng `ALL` rồi nghĩ `@Cacheable(false)` sẽ loại một entity

Trong `ALL`, tất cả entities đều thuộc phạm vi cacheable theo mode. Nếu cần ngoại lệ per entity, chọn `DISABLE_SELECTIVE` và khai báo `@Cacheable(false)`.

### Lỗi 4: Dùng `ENABLE_SELECTIVE` rồi không đánh dấu entity muốn cache

Entity không annotation không tự cacheable theo mode này.

### Lỗi 5: Dùng `DISABLE_SELECTIVE` rồi thêm entity nhạy cảm mà quên false

Entity mới có thể cacheable mặc định. Cần policy/code review.

### Lỗi 6: Xem `UNSPECIFIED` là một mode cố định giữa providers

Không. Provider quyết định default behavior.

### Lỗi 7: Cho rằng L2 hit luôn đồng nghĩa không SQL nào chạy

JPQL query vẫn có thể cần SQL để tìm matching IDs, associations có thể lazy-load.

### Lỗi 8: Nhầm query cache với entity cache

`@Cacheable` không mặc nhiên cache toàn bộ JPQL/native query result sets.

### Lỗi 9: Tưởng cache entity tự cache tất cả collections

Collections/associations có region và fetching semantics riêng.

### Lỗi 10: Evict L2 rồi đọc cùng managed Book trong L1

Vẫn có thể trả Java object cũ. Dùng context mới hoặc refresh phù hợp.

### Lỗi 11: Clear L1 rồi nghĩ shared cache cũng bị clear

Không. `em.clear()` không phải `emf.getCache().evictAll()`.

### Lỗi 12: Dùng retrieve BYPASS để bỏ qua cả L1

Không. Bypass hint chỉ điều khiển shared-cache retrieval theo contract, không tự phá identity map.

### Lỗi 13: Native SQL sửa DB nhưng không invalidates L2

Có thể gây stale entries. Cần thiết kế policy cho external writes.

### Lỗi 14: Evict trước commit rồi coi là không thể có stale reload

Concurrent reader có thể load lại state cũ trước khi writer commit. Phải xét invalidation timing và transactional cache integration.

### Lỗi 15: Tưởng `@Version` tự xử lý mọi native SQL update

Không. Native SQL phải tuân theo versioning nếu muốn optimistic semantics nhất quán.

### Lỗi 16: Tưởng Spring `@Cacheable` là JPA `@Cacheable`

Khác package, mục đích và cache manager.

### Lỗi 17: Tưởng Hibernate `@Cache` là annotation portable JPA

Không. Nó là provider-specific.

### Lỗi 18: Cấu hình cache trong một file nhưng runtime bị override

Cần kiểm tra nguồn cấu hình thực sự có hiệu lực.

### Lỗi 19: Benchmark nhiều `find` trong cùng EntityManager

Đó chủ yếu đo L1, không phải L2.

### Lỗi 20: Kỳ vọng cache API trả đúng SQL count trên mọi provider

`Cache.contains` và `evict` không thay thế provider-specific statistics và trace.

### Lỗi 21: Cache dữ liệu nhạy cảm mà không xét retention/security

L2 chỉ là một trong nhiều cache layers; phải kiểm soát toàn hệ thống.

### Lỗi 22: Bật `ALL` trên hệ thống nhiều nodes mà không có coherence policy

Có nguy cơ stale state nếu backend/invalidation không được phối hợp.

### Lỗi 23: Bật cache để “sửa” N+1

N+1 cần fetch plan/projection/batching, cache chỉ giảm một phần chi phí tùy hit.

### Lỗi 24: Nghĩ FORCE_INCREMENT/pessimistic locking tự đồng bộ cache mọi node

Lock/version và shared cache invalidation là các cơ chế khác nhau.

### Lỗi 25: Dùng `evictAll()` sau mọi update

Có thể xóa các hot entries không liên quan, tạo DB load lớn. Chọn invalidation phạm vi phù hợp.

## 51. Bài tập thực hành

### Bài 1: Chọn mode cho một entity ít thay đổi

Category được đọc ở hầu hết requests, hiếm khi sửa. InventoryItem cập nhật liên tục.

**Câu hỏi:** Mode nào giúp cache Category mà không cache InventoryItem theo hướng opt-in?

**Đáp án:** `ENABLE_SELECTIVE` với `@Cacheable(true)` trên Category và không opt-in InventoryItem.

### Bài 2: ALL và annotation false

```java
@Entity
@Cacheable(false)
class InventoryItem {}
```

Persistence unit có `ALL`.

**Câu hỏi:** InventoryItem đủ điều kiện cache theo mode ALL không?

**Đáp án:** Có theo semantics ALL. Muốn opt-out từng entity, dùng `DISABLE_SELECTIVE`.

### Bài 3: NONE và annotation true

```java
@Entity
@Cacheable(true)
class Category {}
```

Persistence unit có `NONE`.

**Câu hỏi:** Category có được bật shared cache theo policy này không?

**Đáp án:** Không. `NONE` không cho entity cacheable trong shared cache của persistence unit.

### Bài 4: ENABLE_SELECTIVE và annotation trống

```java
@Entity
class Category {}
```

**Câu hỏi:** Cacheable không?

**Đáp án:** Không được opt-in ở `ENABLE_SELECTIVE` nếu không có annotation/inherited metadata phù hợp.

### Bài 5: DISABLE_SELECTIVE

Entity Book không có `@Cacheable`; PaymentAttempt có `@Cacheable(false)`.

**Câu hỏi:** Loại nào đủ điều kiện cache?

**Đáp án:** Book có; PaymentAttempt không.

### Bài 6: UNSPECIFIED

Dự án không cấu hình `shared-cache-mode`.

**Câu hỏi:** Có thể kết luận entity không được cache không?

**Đáp án:** Không. Cần kiểm tra default/provider và runtime configuration.

### Bài 7: L1 vs L2

Hai lần `em.find(Book.class, id)` trong cùng EntityManager không phát SQL lần hai.

**Câu hỏi:** Đã chứng minh L2 chưa?

**Đáp án:** Chưa. L1 identity map có thể giải thích hiện tượng.

### Bài 8: L2 qua contexts khác nhau

Đọc Category ở EntityManager A rồi ở EntityManager B mới.

**Câu hỏi:** Làm sao biết lần B dùng L2?

**Đáp án:** Kiểm soát shared cache state, đo provider SQL/cache statistics; không chỉ so sánh Java references.

### Bài 9: Evict

`emf.getCache().evict(Book.class, id)` rồi `em.find(Book.class,id)` trong context đang giữ Book.

**Câu hỏi:** Có chắc phát SELECT mới không?

**Đáp án:** Không. L1 có thể trả managed Book.

### Bài 10: Bypass

`CacheRetrieveMode.BYPASS` được dùng trên `find`, nhưng Book đã managed.

**Câu hỏi:** Vì sao có thể vẫn thấy state cũ?

**Đáp án:** Hint bypass shared cache, không xóa L1 identity map hoặc tự refresh managed entity.

### Bài 11: Native SQL

Batch JDBC update Book title, JPA L2 vẫn giữ entry cũ.

**Câu hỏi:** Cần làm gì?

**Đáp án:** Thiết kế invalidation/refresh strategy sau commit, evict entry/region phù hợp, cân nhắc bypass và context mới; không giả định `@Version` tự sửa khi native update không tăng version.

### Bài 12: Query cache

JPQL `SELECT b FROM Book b WHERE b.price > :min` vẫn gửi SQL dù Book `@Cacheable(true)`.

**Câu hỏi:** Có mâu thuẫn không?

**Đáp án:** Không. Entity cache khác query result cache; provider có thể phải chạy SQL để tìm IDs khớp predicate.

### Bài 13: Association

Book được cache nhưng `book.getReviews()` gây SELECT.

**Câu hỏi:** Vì sao?

**Đáp án:** Cacheability của Book không đồng nghĩa Reviews collection/Review entities đã được cache hoặc eager-fetched.

### Bài 14: Spring annotation

`@org.springframework.cache.annotation.Cacheable` trên service GET BookCard.

**Câu hỏi:** Có thể điều khiển bằng `SharedCacheMode.NONE` không?

**Đáp án:** Không trực tiếp. Spring method cache là cơ chế application-level riêng.

### Bài 15: Hibernate cache annotation

`@org.hibernate.annotations.Cache` được thêm trên Category.

**Câu hỏi:** Có portable giữa JPA providers không?

**Đáp án:** Không. Nó cấu hình Hibernate-specific cache behavior/region strategy.

### Bài 16: Cluster

Node A cập nhật Book và evict cache A, node B vẫn trả Book cũ.

**Câu hỏi:** `@Cacheable` có tự bảo đảm coherence không?

**Đáp án:** Không. Cần distributed cache/invalidation coordination hoặc policy staleness phù hợp.

### Bài 17: Version

Native UPDATE Book title không tăng version.

**Câu hỏi:** `@Version` trên entity có đủ phát hiện mọi stale read không?

**Đáp án:** Không. External/native writer phải phối hợp versioning/invalidation theo nghiệp vụ.

### Bài 18: Inheritance

Base entity `@Cacheable(true)`; subclass không có annotation.

**Câu hỏi:** Có nên chỉ kiểm tra annotation trực tiếp trên subclass?

**Đáp án:** Không. Cần xét inheritance/override semantics của `@Cacheable` và cách provider tổ chức entity hierarchy cache.

### Bài 19: TTL

Nhóm muốn Category hết hạn sau 30 phút.

**Câu hỏi:** Có đặt TTL trực tiếp bằng `@Cacheable(ttl=...)` không?

**Đáp án:** Không. JPA `@Cacheable` không có thuộc tính TTL; cấu hình qua provider/cache backend tương ứng.

### Bài 20: Cache refresh

Bạn muốn query một lần bỏ qua shared cache cũ rồi làm mới cache từ DB.

**Gợi ý:** Dùng `CacheRetrieveMode.BYPASS` kết hợp `CacheStoreMode.REFRESH` trong scope thích hợp, đảm bảo không có managed entity stale trong L1 và kiểm chứng provider behavior.

## 52. Checklist trước khi đưa shared cache vào production

1. Có phân biệt L1 và L2 trong kiến trúc chưa?
2. Persistence unit đang dùng mode nào: ALL, NONE, ENABLE_SELECTIVE, DISABLE_SELECTIVE hay UNSPECIFIED?
3. Có chứng minh mode thực tế không bị framework/container override không?
4. Cache provider/backend có thực sự được bật và tương thích với JPA provider không?
5. Những entity nào được cacheable theo ma trận mode/annotation?
6. Có hiểu `@Cacheable` inheritance/override trong entity hierarchy không?
7. Có loại những entity thay đổi nhanh hoặc nhạy cảm khi cần không?
8. Có biết `@Cacheable(true)` không bảo đảm cache hit không?
9. Có phân biệt JPA `@Cacheable`, Hibernate `@Cache` và Spring `@Cacheable` không?
10. Có cần query result cache khác với entity cache không?
11. Các collection/associations có fetch/cache strategy riêng không?
12. Có dùng `@Version` và concurrency strategy phù hợp không?
13. Mọi đường ghi có đi qua JPA hay có JDBC/native/bulk/external writers?
14. Có invalidation strategy cho external writes sau commit không?
15. Đã xem race khi evict trước commit chưa?
16. Có nhiều nodes/JVM cần coherence hoặc TTL policy không?
17. Có kiểm soát first-level context khi thử shared-cache bypass/evict không?
18. Có biết `CacheRetrieveMode` và `CacheStoreMode` chỉ điều khiển operation không?
19. Có tránh gọi `evictAll()` bừa bãi không?
20. Có policy cache memory size, TTL, eviction và monitoring không?
21. Có bảo vệ PII/tenant data ở các cache layers khác không?
22. Có test with cache NONE để đối chiếu business correctness không?
23. Có test với production-like L2 provider và nhiều EntityManagers không?
24. Có test cache entry invalidation sau managed update/rollback không?
25. Có test native/bulk SQL không để cache stale không mong đợi không?
26. Có test query result/projection không bị nhầm với entity cache không?
27. Có đo hit/miss/put/eviction thay vì chỉ lặp `find` trong cùng context không?
28. Có đánh giá DB load, p95 latency, heap/GC và network overhead không?
29. Có cơ chế degrade gracefully nếu cache provider không sẵn sàng không?
30. Có tài liệu hóa chính sách cacheability cho entity mới khi schema phát triển không?

Checklist này phục vụ thiết kế và triển khai thực tế; nó không nói rằng mọi ứng dụng JPA đều phải bật L2. Khi chưa có lợi ích đo được hoặc chưa có invalidation policy rõ, `NONE` hoặc `ENABLE_SELECTIVE` hạn chế có thể là lựa chọn đơn giản và an toàn hơn.

## Kết luận

**`SharedCacheMode` là chính sách shared cache ở cấp persistence unit; `@Cacheable` là metadata trên entity type dùng để lựa chọn cacheability khi chế độ chọn lọc có hiệu lực.**

Năm giá trị cần nhớ:

- **`ALL`**: tất cả entities đủ điều kiện shared cache.
- **`NONE`**: không entity nào đủ điều kiện shared cache.
- **`ENABLE_SELECTIVE`**: opt-in bằng `@Cacheable(true)`.
- **`DISABLE_SELECTIVE`**: opt-out bằng `@Cacheable(false)`.
- **`UNSPECIFIED`**: provider-specific default, không nên dựa vào nếu cần policy ổn định.

Một annotation `@Cacheable(true)` không tự cấp L2 backend, không cache toàn bộ object graph, không bật query cache và không bảo đảm dữ liệu luôn mới. Cache cấp một vẫn tồn tại trong mỗi persistence context, ngay cả khi shared cache bị tắt. Muốn điều khiển một lượt đọc, JPA còn có `CacheRetrieveMode` và `CacheStoreMode`; muốn quản lý cached entries, dùng `EntityManagerFactory.getCache()` với các thao tác `contains`/`evict`/`evictAll` thích hợp.

Với hệ thống có nhiều writers, bulk/native SQL và nhiều application nodes, tính đúng còn phụ thuộc **versioning, transaction boundary, cache concurrency strategy và invalidation policy**. Hãy kiểm thử ở nhiều EntityManagers độc lập, kiểm soát L1 và L2 riêng, đo cache hit/miss cùng số SQL và xác nhận cập nhật ngoài ORM không làm ứng dụng đọc dữ liệu stale ngoài mức chấp nhận được.

Bốn câu hỏi trọng tâm khi cấu hình là: **“Persistence unit đang ở chế độ nào? Entity type này có đủ điều kiện cache theo mode và annotation không? Cache provider có thực sự lưu/đọc entry qua các contexts không? Và khi database đổi ngoài JPA, ai chịu trách nhiệm làm mới hoặc invalidates cached state?”**. Trả lời rõ bốn câu hỏi đó sẽ giúp sử dụng `SharedCacheMode` và `@Cacheable` đúng mục đích: **tăng hiệu năng mà không đánh đổi sự rõ ràng và tính nhất quán dữ liệu một cách vô tình**.
