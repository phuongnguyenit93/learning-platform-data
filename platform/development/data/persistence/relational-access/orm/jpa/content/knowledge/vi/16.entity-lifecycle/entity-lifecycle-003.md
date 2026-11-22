# Theo dõi thay đổi entity đang được quản lý trong JPA

Trong Jakarta Persistence (JPA), lập trình viên thường không cần viết lệnh SQL `UPDATE` cho từng thay đổi của một entity. Nếu entity đang ở trạng thái **managed** trong một **persistence context**, ta có thể thay đổi các thuộc tính persistent của nó như thay một object Java bình thường; khi đến thời điểm thích hợp, JPA provider sẽ đồng bộ những thay đổi cần thiết xuống cơ sở dữ liệu.

Ví dụ:

~~~java
Product product = em.find(Product.class, 101L);
product.changePrice(new BigDecimal("249000.00"));

// Không có em.update(product) trong API JPA.
// Thay đổi được theo dõi khi product là managed.
~~~

Cơ chế nhận diện thay đổi này thường được gọi là **dirty checking** hoặc **automatic change detection**. Đây là một khả năng cốt lõi của mô hình *unit of work*: ứng dụng mô tả trạng thái nghiệp vụ mong muốn trên đối tượng, còn provider quản lý việc đồng bộ trạng thái đó xuống các hàng SQL.

Tuy nhiên, có một số điều cần phân biệt:

- **Thay đổi trong RAM** không đồng nghĩa câu `UPDATE` đã chạy.
- **Managed** không đồng nghĩa entity sẽ được lưu dù không có transaction ghi phù hợp.
- **Dirty checking** không áp dụng tự động cho mọi object Java, đặc biệt object *detached* hoặc trường `@Transient`.
- Quan hệ entity và collection có quy tắc **owning side**, cascade và tracking riêng; chỉ sửa một danh sách Java không bảo đảm khóa ngoại được cập nhật.
- Câu lệnh **bulk JPQL/native SQL** có thể thay database mà không đồng bộ ngược lại những managed entity đã nạp.

Bài học tập trung vào cách JPA theo dõi thay đổi của **entity đang được quản lý**: cơ chế, thời điểm, điều kiện, các trường hợp biên và cách áp dụng an toàn trong code nghiệp vụ.

## 1. Dirty checking là gì và giải quyết vấn đề nào?

Giả sử database đang có một sản phẩm:

~~~text
products
------------------------------------------------------------
id     sku             price          status        version
------------------------------------------------------------
101    JPA-BOOK        199000.00      ACTIVE        3
~~~

Ứng dụng muốn thay giá thành 249.000 đồng. Nếu dùng JDBC thuần, lập trình viên thường xây dựng và thực thi SQL:

~~~sql
UPDATE products
SET price = 249000.00
WHERE id = 101;
~~~

Với một entity managed trong JPA:

~~~java
Product product = em.find(Product.class, 101L);
product.changePrice(new BigDecimal("249000.00"));
~~~

Ta chỉ đổi trạng thái Java. Khi flush/commit trong transaction thích hợp, provider có thể phát SQL đại ý:

~~~sql
UPDATE products
SET price = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Lập trình viên không phải tự chuyển từng setter thành câu SQL. **Dirty checking** là việc provider nhận diện *state persistent hiện tại khác với state đã được theo dõi* và lên lịch hoặc thực hiện thao tác đồng bộ cần thiết.

Một cách nhìn:

~~~text
             Lần đọc hoặc persist entity
                        |
                        v
              Persistence Context
        +-----------------------------+
        | Product#101 đang MANAGED    |
        | Trạng thái đã theo dõi      |
        |   price = 199000.00         |
        +-----------------------------+
                        |
                changePrice(249000)
                        |
                        v
        +-----------------------------+
        | Product#101 trong RAM       |
        |   price = 249000.00         |
        +-----------------------------+
                        |
              flush / commit thích hợp
                        |
                        v
               Provider nhận diện
                 thay đổi cần ghi
                        |
                        v
                UPDATE ở database
~~~

**Chốt khái niệm:** dirty checking là tính năng của *persistence context và provider*, không phải “setter thông minh tự kết nối database”. Setter thường chỉ thay field Java.

## 2. Điều kiện để một thay đổi được tự động theo dõi

Trong ví dụ tiêu chuẩn, cần các điều kiện sau:

1. Đối tượng là **entity persistent** được khai báo bằng `@Entity` và có định danh hợp lệ.
2. Đối tượng đang ở trạng thái **managed** bởi persistence context hiện hành.
3. Thuộc tính được thay đổi là **persistent state** mà mapping cho phép ghi.
4. Có **transaction và flush/commit phù hợp** để phát SQL ghi dữ liệu.
5. Thao tác không bị ngăn bởi quyền ghi của mapping, trạng thái read-only/provider hint, validation hoặc ràng buộc database.

Ví dụ sự khác biệt:

| Object | Mã thay đổi | JPA tự theo dõi để ghi? |
| --- | --- | --- |
| Entity mới chưa persist | `new Product(...); p.changePrice(...)` | Chưa; object vẫn transient |
| Entity đã `persist()` trong context | `p.changePrice(...)` | Có thể được đồng bộ khi insert/flush theo state managed |
| Entity lấy bằng `find()` | `p.changePrice(...)` | Có, với field persistent writable |
| Entity đã `detach()` | `p.changePrice(...)` | Không tự ghi qua context đã detach |
| Entity sau khi `clear()` | `p.changePrice(...)` | Không tự ghi cho object cũ |
| Object DTO/record thông thường | `dto.setPrice(...)` | Không; không phải managed entity |
| Entity managed, field `@Transient` | Thay field transient | Không ghi field đó vào cột SQL |
| Entity managed, field `updatable = false` | Thay field trong Java | Mapping không cho đưa cột vào UPDATE thông thường |

JPA có thể quản lý entity trong nhiều dạng persistence context khác nhau (transaction-scoped hoặc extended). Nhưng **khả năng ghi có hiệu lực** vẫn phải tuân thủ ranh giới transaction và các quy tắc synchronization của cấu hình đó.

## 3. Một entity cụ thể để thực hành

Ta dùng entity `Product` với các field cơ bản, một trường phiên bản và một trường chỉ dùng cho giao diện.

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 60)
    private String sku;

    @Column(
        name = "price",
        nullable = false,
        precision = 14,
        scale = 2)
    private BigDecimal price;

    @Column(name = "status", nullable = false, length = 20)
    private String status;

    @Version
    private Long version;

    @Transient
    private boolean highlightedInUi;

    protected Product() {
        // Constructor cho JPA.
    }

    public Product(String sku, BigDecimal price) {
        this.sku = Objects.requireNonNull(sku);
        this.price = Objects.requireNonNull(price);
        this.status = "ACTIVE";
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public String getStatus() {
        return status;
    }

    public Long getVersion() {
        return version;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá không hợp lệ");
        }
        this.price = newPrice;
    }

    public void deactivate() {
        this.status = "INACTIVE";
    }

    public void setHighlightedInUi(boolean value) {
        this.highlightedInUi = value;
    }
}
~~~

Một schema SQL tương ứng, sử dụng cú pháp PostgreSQL:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    price NUMERIC(14, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

`highlightedInUi` không có cột SQL vì đã được đánh dấu `@Transient`. `@Version` cho phép provider thực thi optimistic locking; giá trị phiên bản nên do provider quản lý.

Trong entity này, `@Id` nằm trên **field**, nên JPA áp dụng **field access**. Provider theo dõi các trường persistent theo mapping; việc có gọi getter/setter công khai hay không không thay đổi nguyên tắc entity phải là managed.

## 4. Ví dụ đầy đủ: sửa managed entity trong transaction

Với JPA Java SE sử dụng transaction kiểu `RESOURCE_LOCAL`:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = em.find(Product.class, 101L);
    if (product == null) {
        throw new IllegalArgumentException("Sản phẩm không tồn tại");
    }

    product.changePrice(new BigDecimal("249000.00"));
    product.deactivate();

    // Không cần em.persist(product) hay em.merge(product)
    // vì product đã là managed.
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

Khi commit, provider phải đồng bộ những thay đổi pending theo quy tắc flush/transaction. SQL có thể là một UPDATE cho nhiều cột, hoặc khác tùy provider và cấu hình. Điều cốt lõi là **entity đã managed nên thay đổi persistent state được quan sát mà không cần gọi một lệnh update riêng**.

Trong Spring hoặc Jakarta EE, transaction thường được khai báo ở service hoặc được container quản lý:

~~~java
@Transactional
public void updateProduct(
        long id,
        BigDecimal newPrice) {

    Product product = em.find(Product.class, id);
    if (product == null) {
        throw new IllegalArgumentException("Không tìm thấy sản phẩm");
    }

    product.changePrice(newPrice);
    // Kết thúc transaction thành công sẽ đồng bộ thay đổi.
}
~~~

Ví dụ trên giả sử `@Transactional` và `em` được cung cấp bởi framework/container phù hợp; annotation và cách cấu hình transaction khác nhau giữa Jakarta Transactions và Spring. Không vừa gọi `em.getTransaction()` vừa dựa vào JTA transaction trên cùng entity manager theo cách không được hỗ trợ.

## 5. Dirty checking theo snapshot và enhancement

Chuẩn JPA mô tả **hành vi đồng bộ state managed entity**, không buộc mọi provider phải hiện thực dirty checking bằng cùng một thuật toán. Có hai nhóm kỹ thuật phổ biến:

### 5.1. Theo dõi bằng snapshot

Provider có thể giữ một biểu diễn của state persistent khi entity được nạp hoặc sau một mốc đồng bộ. Khi flush, provider so sánh trạng thái hiện tại với trạng thái được theo dõi để xác định field đã thay đổi.

~~~text
Khi load:
  snapshot = {price: 199000, status: ACTIVE}
  entity   = {price: 199000, status: ACTIVE}

Sau phương thức nghiệp vụ:
  snapshot = {price: 199000, status: ACTIVE}
  entity   = {price: 249000, status: INACTIVE}

Khi flush:
  provider nhận diện price và status đã thay đổi
  -> đồng bộ UPDATE
~~~

Snapshot thường là dữ liệu nội bộ của provider, không phải một object ứng dụng nên có quyền sửa. Không có API JPA chuẩn để trực tiếp truy cập và sửa snapshot rồi yêu cầu provider làm theo.

### 5.2. Bytecode enhancement hoặc cơ chế đánh dấu thay đổi

Một số provider hỗ trợ *bytecode enhancement*, instrumentation hoặc cơ chế riêng giúp entity thông báo thuộc tính nào bị sửa. Thay vì luôn so sánh toàn bộ state theo cùng một cách, provider có thể đánh dấu field thay đổi khi được gán.

Lợi ích tiềm năng là tối ưu chi phí phát hiện dirty state hoặc hỗ trợ lazy loading nâng cao. Tuy nhiên:

- Khả năng sử dụng phụ thuộc provider, phiên bản và cấu hình build/runtime.
- Không nên giả định mọi entity trong mọi dự án đều được enhancement.
- Cách đánh dấu thay đổi của provider có thể khác cách so sánh giá trị snapshot.
- Việc thay giá trị rồi gán lại bằng giá cũ có thể được provider xử lý khác nhau tùy chiến lược tracking.

**Thiết kế ứng dụng nên dựa trên hợp đồng JPA về state managed và flush, không dựa vào thuật toán dirty checking cụ thể trừ khi dự án chủ động phụ thuộc vào provider ấy.**

## 6. “Đã sửa field” và “đã phát SQL UPDATE” là hai thời điểm khác nhau

Ví dụ:

~~~java
tx.begin();
Product product = em.find(Product.class, 101L);

product.changePrice(new BigDecimal("249000.00"));
System.out.println(product.getPrice());  // 249000.00

em.flush();   // Yêu cầu đồng bộ SQL pending.
tx.commit();  // Xác nhận transaction.
~~~

Timeline:

| Mốc | State trong Java | State SQL | Đã commit? |
| --- | --- | --- | --- |
| Sau `find()` | Giá đã nạp, ví dụ 199000 | DB có hàng ban đầu | Có, từ transaction trước |
| Sau `changePrice()` | **249000** | Có thể vẫn 199000 | Chưa commit thay đổi mới |
| Sau `flush()` | **249000** | UPDATE có thể đã thực thi trong transaction | **Chưa** |
| Sau `commit()` thành công | Giá object đang giữ là 249000 | Thay đổi transaction được xác nhận | **Có** |

**Dirty checking không có nghĩa mỗi setter phát một UPDATE ngay lập tức.** Provider thường gom các thay đổi để xử lý ở lúc flush.

### Có thể UPDATE trước khi gọi `flush()` tường minh không?

Có. Provider có thể flush trước commit hoặc trước truy vấn theo flush mode. Với entity mới dùng `IDENTITY`, INSERT còn có thể được gửi sớm để lấy khóa sinh. Vì thế đừng kết luận thời điểm SQL chỉ dựa trên việc code có dòng `em.flush()` hay không.

### Có thể thay đổi object nhưng không có UPDATE không?

Có, chẳng hạn:

- Field đã gán có giá trị hiệu dụng như cũ và provider không nhận diện một thay đổi cần ghi.
- Field là `@Transient` hoặc không được mapping.
- Field được cấu hình `updatable = false`.
- Entity đã detached trước khi flush.
- Transaction bị rollback trước khi thay đổi được commit.
- Provider đặt entity vào chế độ read-only riêng của nó.
- Việc flush bị chặn bởi validation hoặc lỗi ràng buộc database.

Từng nguyên nhân khác nhau cần xử lý khác nhau; **không thấy UPDATE** chưa đủ để kết luận JPA hỏng dirty checking.

## 7. Flush mode quyết định cách query tương tác với thay đổi pending

JPA cung cấp `FlushModeType.AUTO` và `FlushModeType.COMMIT`.

### 7.1. AUTO

Với `AUTO`, provider phải bảo đảm rằng những thay đổi pending có thể ảnh hưởng đến kết quả truy vấn được phản ánh trong kết quả theo quy tắc JPA. Provider thường flush trước những truy vấn có liên quan hoặc dùng cơ chế khác có hiệu quả tương đương.

Ví dụ:

~~~java
Product p = em.find(Product.class, 101L);
p.changePrice(new BigDecimal("249000.00"));

List<Product> expensive = em.createQuery(
        "SELECT p FROM Product p WHERE p.price >= :min",
        Product.class)
    .setParameter("min", new BigDecimal("240000.00"))
    .getResultList();
~~~

Vì thay đổi giá có thể làm Product#101 đủ điều kiện lọc, provider phải xử lý truy vấn nhất quán với pending state theo cơ chế `AUTO` áp dụng.

### 7.2. COMMIT

Với `COMMIT`, việc đồng bộ có thể được trì hoãn tới commit; hiệu ứng của thay đổi pending lên các query trước đó không được xác định giống `AUTO`.

~~~java
em.setFlushMode(FlushModeType.COMMIT);
~~~

Đoạn trên cần import `jakarta.persistence.FlushModeType`. Chuyển sang `COMMIT` để giảm số lần flush có thể ảnh hưởng tới query phụ thuộc state vừa sửa, nên phải có lý do thiết kế cụ thể.

### Flush mode không thay thế transaction

Dù ở chế độ nào, một thao tác ghi vẫn cần transaction phù hợp. `flush()` đồng bộ SQL trong transaction, **không phải** một cơ chế tự commit độc lập.

## 8. Một entity managed có thể được sửa nhiều lần trước một lần flush

Ví dụ:

~~~java
Product product = em.find(Product.class, 101L);

product.changePrice(new BigDecimal("209000.00"));
product.changePrice(new BigDecimal("219000.00"));
product.changePrice(new BigDecimal("249000.00"));
~~~

Nếu không có flush ở giữa, khi đồng bộ, provider có thể chỉ cần ghi **giá trị cuối 249000**. Không có yêu cầu phải phát một UPDATE cho mỗi lời gọi `changePrice()`.

~~~text
Giá đã nạp    199000
  |
  +--> 209000
  +--> 219000
  +--> 249000
           |
           v
       flush/commit
           |
           v
       SQL ghi trạng thái cuối theo unit of work
~~~

Điều này vừa là lợi ích hiệu năng vừa là điều cần hiểu khi nghiệp vụ yêu cầu **lịch sử mỗi lần thay giá**. Dirty checking của entity trạng thái hiện tại không tự tạo một audit record cho mỗi lần setter được gọi. Muốn lưu lịch sử, cần mô hình log/sự kiện riêng hoặc cơ chế auditing phù hợp.

### Thay rồi trả lại giá cũ

~~~java
product.changePrice(new BigDecimal("209000.00"));
product.changePrice(new BigDecimal("199000.00"));
~~~

Nếu trạng thái cuối không khác state được theo dõi, một số cơ chế snapshot có thể không sinh UPDATE. Nhưng cơ chế enhanced tracking có thể có cách nhận biết setter đã chạy. **Không dùng giả định “chắc chắn không có UPDATE” làm quy tắc nghiệp vụ**; nếu muốn tránh write không cần thiết, đo hành vi trên provider cụ thể.

## 9. Field persistent, field transient và cột không được cập nhật

Provider chỉ đồng bộ những gì mapping mô tả là state persistent và có quyền ghi.

### 9.1. `@Transient`

~~~java
@Transient
private boolean highlightedInUi;
~~~

Thay đổi:

~~~java
product.setHighlightedInUi(true);
~~~

không có cột tương ứng để UPDATE. Đây là thay đổi hợp lệ của object Java nhưng **không phải dirty persistent state** của entity.

### 9.2. `@Column(updatable = false)`

~~~java
@Column(
    name = "external_reference",
    nullable = false,
    updatable = false)
private String externalReference;
~~~

Provider thường không đưa cột này vào SQL UPDATE của mapping. Điều đó không biến field Java thành bất biến tuyệt đối: code có thể vẫn gán giá trị khác trong RAM nếu có setter. Nếu domain yêu cầu bất biến, nên thiết kế API object và constraint phù hợp để tránh tồn tại hai cách nhìn khác nhau về giá trị.

### 9.3. `insertable = false`

Một column mapping có `insertable = false` không được dùng để ghi cột đó trong SQL INSERT do JPA tạo. Điều này **không tự có nghĩa DB sẽ sinh giá trị mới**; nếu cần default, trigger hoặc generated column, schema phải có cơ chế thật.

### 9.4. Derived/calculated field

Ví dụ:

~~~java
public BigDecimal getPriceWithTax() {
    return price.multiply(new BigDecimal("1.10"));
}
~~~

Nếu entity dùng field access và không ánh xạ method này, `getPriceWithTax()` chỉ là phép tính Java. Đổi cách tính không làm JPA sinh cột `price_with_tax`, trừ khi mapping được khai báo thêm một cách rõ ràng.

## 10. Field access và property access ảnh hưởng nơi JPA nhìn state

JPA có hai cách ánh xạ chính:

- **Field access:** annotation định danh đặt trên field; provider truy cập persistent fields.
- **Property access:** annotation định danh đặt trên getter; provider truy cập persistent properties.

Ví dụ property access:

~~~java
@Entity
@Access(AccessType.PROPERTY)
public class Customer {

    private Long id;
    private String displayName;

    protected Customer() {
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    @Column(name = "display_name")
    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Đoạn trên dùng `jakarta.persistence.Access` và `AccessType`. Với property access, provider dựa vào các thuộc tính ánh xạ qua accessors theo quy tắc JPA. Với field access, provider không cần một setter công khai cho mỗi cột.

**Không đồng nhất dirty checking với việc “JPA chỉ nhận biết nếu setter được gọi”.** Với snapshot checking, provider có thể thấy field persistent đổi dù field được sửa qua phương thức nghiệp vụ khác. Nhưng nếu dùng enhancement hoặc property access, hành vi ở các trường hợp can thiệp không đúng access strategy có thể phụ thuộc provider.

### Trộn annotation field/getter sai cách

Nếu `@Id` nằm trên field nhưng `@Column` khác lại đặt trên getter mà không sử dụng `@Access` có chủ đích, mapping có thể bị bỏ qua hoặc gây hành vi không xác định như mong đợi. Muốn dirty checking ổn định, phải xác định **mô hình persistent attributes** rõ trước.

## 11. Những kiểu giá trị nào nên được coi là bất biến?

Dirty checking có thể nhận diện thay đổi khi **thay reference/value** và, tùy kiểu, có thể cần xử lý đặc biệt nếu object bị sửa bên trong mà không được gán lại.

### 11.1. Kiểu bất biến

Các kiểu như `String`, `BigDecimal`, `LocalDate` và `Instant` thường được dùng theo cách bất biến:

~~~java
product.changePrice(new BigDecimal("249000.00"));
~~~

Trường `price` nhận một giá trị mới. Đây là kiểu cập nhật dễ hiểu và ít mơ hồ.

### 11.2. Mutable basic type

Với những kiểu mutable như `java.util.Date`, `Calendar`, mảng byte hoặc một loại custom mutable object, không nên tự giả định provider phát hiện mọi thay đổi nội bộ theo mọi mapping.

Ví dụ:

~~~java
Date current = event.getStartTime();
current.setTime(current.getTime() + 3_600_000L);
~~~

Thay đổi này tác động tới object `Date` đang được tham chiếu. Provider có thể phát hiện nhờ snapshot/deep copy hoặc cơ chế tracking, nhưng điều đó phụ thuộc kiểu basic, converter và provider. Để diễn đạt rõ ý định, một cách dễ hiểu hơn là dùng kiểu thời gian bất biến và gán lại:

~~~java
event.changeStartTime(
        event.getStartTime().plusHours(1));
~~~

Đoạn thứ hai giả sử `getStartTime()` trả về `LocalDateTime` và entity có phương thức nghiệp vụ `changeStartTime()`.

### 11.3. Custom `AttributeConverter`

Nếu một kiểu giá trị tự định nghĩa được ánh xạ qua `@Convert`, dirty checking còn chịu ảnh hưởng cách provider đánh giá equality/mutability của kiểu đó. Một converter chuyển đổi Java↔JDBC **không tự đảm bảo** provider hiểu được mọi thao tác mutate bên trong một custom object.

Với value object tự thiết kế, thường nên:

- Thiết kế bất biến về mặt ngữ nghĩa khi có thể.
- Có cách so sánh giá trị ổn định.
- Không lộ mutable internals ra bên ngoài.
- Cân nhắc hỗ trợ provider-specific về mutability nếu stack đòi hỏi.

## 12. Embeddable: thay đổi thành phần của một giá trị nhúng

Giả sử entity `Customer` chứa địa chỉ:

~~~java
@Embeddable
public class Address {

    @Column(name = "city", nullable = false)
    private String city;

    @Column(name = "postal_code")
    private String postalCode;

    protected Address() {
    }

    public Address(String city, String postalCode) {
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getCity() {
        return city;
    }
}
~~~

Trong `Customer`:

~~~java
@Embedded
private Address shippingAddress;

public void changeShippingAddress(
        String city, String postalCode) {
    this.shippingAddress = new Address(city, postalCode);
}
~~~

Khi `Customer` là managed, provider quản lý những thuộc tính persistent của embeddable như **một phần state của Customer**. Gọi:

~~~java
customer.changeShippingAddress("Da Nang", "550000");
~~~

có thể làm provider đồng bộ các cột `city` và `postal_code` của bảng `customers` khi flush.

### Tại sao thay embeddable nguyên khối thường rõ hơn?

Một `@Embeddable` không có identity JPA riêng. Việc tạo instance `Address` mới để thay toàn bộ giá trị dễ thể hiện ý định hơn so với cho nhiều nơi sửa trực tiếp các field nội bộ. Nếu embeddable có setter và ứng dụng mutate nested field, provider vẫn có thể phát hiện theo mapping/dirty-tracking implementation, nhưng cần hiểu mutability và field access của kiểu đó.

### Embeddable không phải entity con

Không gọi:

~~~java
em.persist(address);
~~~

cho một `Address` thuần `@Embeddable` như entity độc lập. Nó được lưu như phần state của entity sở hữu. Nếu địa chỉ cần ID, lịch sử, version hoặc nhiều đối tượng tham chiếu đến cùng một hàng, nên cân nhắc mô hình thành entity riêng.

## 13. Collection được quản lý: thêm/xóa phần tử cũng là một dạng thay đổi

Đối với collection persistent, dirty checking không chỉ là thay một field scalar. Provider thường quản lý collection thông qua wrapper hoặc cơ chế theo dõi membership.

Ví dụ `Order` có các dòng `OrderItem`:

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true)
    private List<OrderItem> items = new ArrayList<>();

    protected Order() {
    }

    public void addItem(OrderItem item) {
        items.add(item);
        item.assignTo(this);
    }

    public void removeItem(OrderItem item) {
        if (items.remove(item)) {
            item.assignTo(null);
        }
    }
}
~~~

Entity `OrderItem`:

~~~java
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private Order order;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderItem() {
    }

    public OrderItem(int quantity) {
        this.quantity = quantity;
    }

    void assignTo(Order order) {
        this.order = order;
    }

    public void changeQuantity(int quantity) {
        if (quantity < 1) {
            throw new IllegalArgumentException(
                    "Số lượng phải lớn hơn 0");
        }
        this.quantity = quantity;
    }
}
~~~

Các đoạn minh họa giả sử đã import đúng annotation `jakarta.persistence` và collection `java.util.List` / `java.util.ArrayList`. `OrderItem.order` là owning side của FK `order_id`; `Order.items` là phía ngược.

Khi `Order` managed:

~~~java
Order order = em.find(Order.class, orderId);
order.addItem(new OrderItem(3));
~~~

với cascade `PERSIST` thông qua `ALL` và owning side được thiết lập, provider có thể persist item mới và ghi FK khi flush.

### Điều cần phân biệt với dirty checking của field basic

- `order.getItems().add(item)` thay membership của collection Java.
- `item.assignTo(order)` mới đồng bộ owning side của quan hệ FK.
- Cascade quyết định thao tác persistence nào được lan truyền.
- `orphanRemoval = true` mô tả vòng đời của child khi bị loại khỏi quan hệ.
- SQL INSERT/DELETE/UPDATE thật được phát theo flush và transaction.

**Thay collection phía `mappedBy` mà không thay owning side không phải cách đáng tin cậy để đổi FK.** Hai chiều object graph cần được đồng bộ trong phương thức nghiệp vụ.

### Không thay hẳn collection wrapper một cách tùy tiện

Đối với entity đã managed, câu lệnh:

~~~java
this.items = new ArrayList<>();
~~~

có thể gây vấn đề với tracking wrapper, orphan removal và diff collection tùy provider. Thường nên giữ collection hiện tại và cung cấp các phương thức `addItem`, `removeItem`, `replaceItems` có kiểm soát. Trong những mô hình có orphan removal, thay reference collection không đúng cách có thể tạo ra xóa ngoài ý muốn hoặc exception.

## 14. `@ElementCollection`: thay Map hoặc List là thay state của owner

Không phải mọi collection chứa entity độc lập. Với:

~~~java
@ElementCollection
@CollectionTable(
    name = "product_labels",
    joinColumns = @JoinColumn(name = "product_id"))
@MapKeyColumn(name = "locale_code")
@Column(name = "display_label")
private Map<String, String> labels = new HashMap<>();
~~~

provider quản lý collection các giá trị basic như **một phần state của Product**.

~~~java
Product product = em.find(Product.class, productId);
product.putLabel("vi-VN", "Giáo trình JPA");
~~~

Đoạn gọi giả sử entity có phương thức:

~~~java
public void putLabel(String locale, String text) {
    labels.put(locale, text);
}
~~~

Khi Product managed và transaction phù hợp, thay Map có thể được đồng bộ thành SQL trên bảng `product_labels`. Tùy provider, có thể là INSERT, UPDATE, DELETE hoặc tái tạo nhiều hàng; **không có bảo đảm mỗi `Map.put()` luôn tương ứng đúng một câu UPDATE**.

### Với embeddable trong element collection

Nếu Map/List chứa embeddable mutable, provider cần theo dõi thay đổi thuộc tính của entry, membership và key. Để tránh bất ngờ:

- Sử dụng key bất biến và `equals/hashCode` ổn định.
- Khi đổi key Map, cân nhắc remove old key rồi put key mới.
- Khi đổi value embeddable, có thể thay value object nguyên khối.
- Tạo PK/UNIQUE phù hợp trên các cột owner và key trong database.
- Không coi element collection là tập entity có ID và version riêng.

Những điểm này thuộc phần tracking state của owner, không phải cơ chế `merge()` cho từng embeddable.

## 15. Quan hệ hai chiều và việc JPA quyết định ghi FK theo owning side

Giả sử một phòng ban có nhiều nhân viên:

~~~java
// Employee: owning side
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;
~~~

~~~java
// Department: inverse side
@OneToMany(mappedBy = "department")
private List<Employee> employees = new ArrayList<>();
~~~

Với quan hệ này:

~~~java
department.getEmployees().add(employee);
~~~

chỉ đổi collection Java ở inverse side. Nếu không gán:

~~~java
employee.setDepartment(department);
~~~

thì owning side vẫn chưa thay, nên không nên kỳ vọng provider cập nhật `employees.department_id` như mong đợi.

**Dirty checking không tự đoán ý định quan hệ khi object graph hai chiều mâu thuẫn.** Theo mapping JPA, owning side giữ thông tin quyết định việc ghi liên kết; inverse side chủ yếu giúp điều hướng trong Java.

### Many-to-many

Với `@ManyToMany`, owning side là phía khai báo `@JoinTable`; phía `mappedBy` là inverse. Thêm phần tử vào collection của owning side có thể dẫn đến thêm hàng join table, nhưng việc sửa riêng inverse collection không bảo đảm cập nhật liên kết.

### One-to-one

Với `@OneToOne` có FK ở bảng profile, `Profile.account` gắn `@JoinColumn` là owning side, còn `Account.profile` có `mappedBy` là inverse. Sửa vài field của profile managed là thay state của profile; thay *liên kết account–profile* cần tác động đúng owning side và chú ý UNIQUE trên FK.

## 16. `@PreUpdate` và `@PostUpdate`: callback có liên quan dirty checking

JPA có lifecycle callbacks giúp chạy logic ở một số mốc persistence.

~~~java
@PreUpdate
public void beforeUpdate() {
    this.updatedAt = Instant.now();
}
~~~

Ở entity thích hợp, khi provider chuẩn bị thực hiện UPDATE, callback `@PreUpdate` có thể được gọi. Nhưng cần hiểu:

- `@PreUpdate` **không phải callback cho mọi lần setter được gọi**.
- Nếu không phát sinh UPDATE cần thiết, không nên kỳ vọng callback luôn chạy.
- Callback có quy tắc và giới hạn riêng, không nên dùng như hệ thống audit transaction đầy đủ.
- Thời điểm callback được gọi liên quan tới flush/update theo provider và mô hình lifecycle.
- Bulk JPQL UPDATE không đi qua callback từng managed entity theo cách thông thường.

Ví dụ entity có hai field:

~~~java
@Column(name = "updated_at")
private Instant updatedAt;

@PreUpdate
void markUpdated() {
    updatedAt = Instant.now();
}
~~~

Để code độc lập cần import `java.time.Instant` và `jakarta.persistence.PreUpdate`. Nếu hệ thống yêu cầu timestamp chính xác theo database clock, trigger hay generated timestamp có thể phù hợp hơn, nhưng khi đó cần xử lý state Java có thể khác giá trị DB.

### Đừng dùng callback để ép UPDATE mọi lúc

Callback không thay thế việc thiết kế nghiệp vụ và transaction. Nếu muốn ghi lại **mỗi lần người dùng yêu cầu thay đổi** dù giá trị cuối vẫn như cũ, cần một audit/event model riêng. Provider không cam kết tạo UPDATE chỉ để kích hoạt callback.

## 17. `@Version`: dirty checking và optimistic locking

Khi nhiều transaction cùng thay đổi một hàng, dirty checking chỉ giải quyết *khi nào ghi thay đổi đã được nhận diện*, không tự giải quyết *ai được quyền ghi đè lên ai*.

Với `@Version`:

~~~java
@Version
private Long version;
~~~

Provider có thể phát SQL dạng:

~~~sql
UPDATE products
SET price = 249000.00,
    version = 4
WHERE id = 101
  AND version = 3;
~~~

Nếu transaction khác đã cập nhật bản ghi và tăng version từ 3 lên 4, câu UPDATE dựa trên version 3 không còn khớp, provider có thể phát hiện xung đột optimistic locking.

Timeline:

~~~text
T1                                     T2
----------------------------------     ----------------------------------
find Product#101 (version=3)           find Product#101 (version=3)
changePrice(249000)                    changePrice(219000)
flush/commit -> version=4
                                       flush/commit với version=3
                                       -> optimistic lock conflict
~~~

Ứng dụng cần rollback transaction thất bại và quyết định cách thông báo hoặc retry trong một transaction mới. Không tự động ghi đè mà không biết người dùng có chấp nhận mất thay đổi của bên kia hay không.

### Hai điều cần phân biệt

1. **Dirty checking:** entity managed có thay đổi persistent state cần ghi.
2. **Optimistic locking:** khi ghi, state có còn dựa trên phiên bản hợp lệ không?

Không có `@Version`, provider vẫn có thể thực hiện dirty checking, nhưng cơ chế phát hiện **lost update** cần được xử lý bằng phương pháp khác.

### Không phải mọi thao tác đều tăng version theo cùng cách

Không nên giả định sửa một inverse collection hoặc thực hiện bulk SQL sẽ luôn tăng version của entity cha. Chi tiết versioning của collection, entity relationship và bulk update phụ thuộc mapping/chuẩn/provider. Nếu nghiệp vụ cần đồng bộ nhiều thay đổi của aggregate thông qua version của root, phải thiết kế và xác nhận chính sách đó; có thể cần lock mode phù hợp, như `OPTIMISTIC_FORCE_INCREMENT`.

## 18. Detached entity: setter không được theo dõi

Một entity trở thành detached khi:

- EntityManager/persistence context đã đóng hoặc bị clear.
- Ứng dụng gọi `em.detach(entity)`.
- Entity đã đi ra khỏi boundary context mà không còn được quản lý.

Ví dụ:

~~~java
Product product;

try (/* pseudocode: EntityManager được tạo và đóng bên ngoài */) {
    // product = em.find(Product.class, 101L);
}

// product đã detached sau khi context đóng.
product.changePrice(new BigDecimal("249000.00"));
~~~

Đoạn trên là **mô tả vòng đời**, không phải Java code chạy nguyên xi. Ví dụ Java SE hoàn chỉnh và rõ ràng hơn:

~~~java
EntityManager em = emf.createEntityManager();
Product product;
try {
    product = em.find(Product.class, 101L);
} finally {
    em.close();
}

product.changePrice(new BigDecimal("249000.00"));
// Không có context nào tiếp tục theo dõi object này.
~~~

Giá trị field đổi trong RAM, nhưng **không có dirty checking tự động ở persistence context đã đóng**.

### Đúng cách với một command update

Nếu API nhận `id` và giá mới, cách dễ kiểm soát thường là:

~~~java
@Transactional
public void changePrice(long id, BigDecimal newPrice) {
    Product managed = em.find(Product.class, id);
    if (managed == null) {
        throw new IllegalArgumentException("Không có sản phẩm");
    }
    managed.changePrice(newPrice);
}
~~~

Ưu điểm là sử dụng entity managed mới nhất theo transaction và chỉ sửa field được phép, thay vì đẩy toàn bộ object graph cũ vào persistence context.

## 19. `merge()` không biến object detached thành managed

JPA có `EntityManager.merge()` để **hợp nhất state từ detached entity** vào một managed instance:

~~~java
Product detached = ...;
detached.changePrice(new BigDecimal("249000.00"));

Product managed = em.merge(detached);
~~~

Điểm quan trọng:

- Object `detached` vẫn detached sau khi merge.
- Instance `managed` do `merge()` trả về mới là đối tượng nên dùng tiếp trong context hiện tại.
- Merge không phải lệnh SQL UPDATE tức thì; đồng bộ vẫn gắn với flush/commit.
- Nếu context đã chứa một managed entity cùng identity, state từ detached có thể được copy sang instance đó theo ngữ nghĩa merge.
- Cascade merge có thể lan sang các quan hệ đã cấu hình `CascadeType.MERGE`.

**Không viết logic như sau nếu muốn tiếp tục theo dõi object:**

~~~java
em.merge(detached);
detached.changePrice(new BigDecimal("299000.00"));
// Thay đổi này trên detached không tự được theo dõi.
~~~

Thay vào đó:

~~~java
Product managed = em.merge(detached);
managed.changePrice(new BigDecimal("299000.00"));
~~~

### Nguy cơ của merge toàn bộ object graph từ request

Một DTO chỉ chứa `price` nhưng được biến thành entity detached với `status = null` có thể ghi đè field status khi merge không kiểm soát. Nếu API chỉ cho đổi giá, ưu tiên nạp managed entity bằng ID và cập nhật giá.

`merge()` không phải cơ chế giải quyết conflict tự động. Nếu detached entity cũ có `@Version`, provider có thể phát hiện phiên bản không hợp lệ; ứng dụng vẫn cần xử lý lỗi và giao dịch.

## 20. `detach()`, `clear()` và thay đổi chưa flush

Các thao tác này ảnh hưởng trực tiếp tới việc provider có tiếp tục theo dõi dirty state hay không.

~~~java
Product p = em.find(Product.class, 101L);
p.changePrice(new BigDecimal("249000.00"));

em.detach(p);
~~~

Nếu chưa flush, thay đổi đang chờ của `p` có thể không được đồng bộ, vì `p` đã rời khỏi context.

Tương tự:

~~~java
em.clear();
~~~

detach tất cả managed entities trong context hiện tại. Điều này khác:

~~~java
em.flush();
em.clear();
~~~

Ở đoạn thứ hai, thay đổi pending đã được yêu cầu đồng bộ xuống DB **trong transaction**, rồi entity mới được detached. `clear()` không rollback SQL đã thực thi.

| Thao tác | Managed state | Pending changes |
| --- | --- | --- |
| `em.detach(p)` | Chỉ p trở thành detached | Có thể không còn được đồng bộ nếu chưa flush |
| `em.clear()` | Tất cả entity trong context trở thành detached | Các thay đổi chưa flush có thể bị mất |
| `em.flush()` | Entity vẫn managed | Đồng bộ pending SQL trong transaction |
| `tx.rollback()` | Transaction DB bị hủy | Không tự hoàn nguyên mọi field Java |
| `em.refresh(p)` | p tiếp tục managed | Có thể ghi đè dirty state chưa flush bằng state DB |

### Khi nào dùng `flush(); clear();` trong batch?

Nếu persist hoặc update hàng nghìn entity, context giữ quá nhiều managed instances có thể làm tăng bộ nhớ và chi phí dirty checking. Một kỹ thuật thường gặp là chia theo lô:

~~~java
for (int i = 0; i < products.size(); i++) {
    Product p = em.find(Product.class, products.get(i).getId());
    p.changePrice(products.get(i).getNewPrice());

    if ((i + 1) % 100 == 0) {
        em.flush();
        em.clear();
    }
}
~~~

Đoạn này giả định chạy trong transaction phù hợp và `products` là danh sách command chứa ID/giá mới; cần flush cả phần tử còn lại sau vòng lặp khi cần. Việc clear khiến các reference entity cũ detached; không nên tiếp tục sửa chúng và kỳ vọng được track.

## 21. Bulk JPQL UPDATE/DELETE không dùng dirty checking từng entity

Bulk JPQL là trường hợp quan trọng nhất khiến state managed và database có thể lệch:

~~~java
Product product = em.find(Product.class, 101L);

int affected = em.createQuery(
        "UPDATE Product p "
      + "SET p.price = :newPrice "
      + "WHERE p.id = :id")
    .setParameter("newPrice", new BigDecimal("249000.00"))
    .setParameter("id", 101L)
    .executeUpdate();
~~~

Bulk UPDATE trực tiếp tác động tới hàng database; nó **không đồng bộ các field của từng managed Product instance** như một setter rồi dirty check.

Vì vậy:

~~~java
System.out.println(product.getPrice());
// Có thể vẫn là giá trước bulk UPDATE.
~~~

Ngay cả khi `affected == 1`, object `product` trong memory có thể stale.

### Mẫu thao tác thận trọng

~~~java
em.flush(); // Đồng bộ những thay đổi managed đang chờ.

int updated = em.createQuery(
        "UPDATE Product p "
      + "SET p.status = :status "
      + "WHERE p.price = :price")
    .setParameter("status", "INACTIVE")
    .setParameter("price", new BigDecimal("0.00"))
    .executeUpdate();

em.clear(); // Bỏ các managed entities có thể đã stale.
~~~

Ở đây, `clear()` có chủ đích **detach toàn context**, nên chỉ phù hợp khi code không cần tiếp tục dùng các managed references đã có. Nếu vẫn cần một entity, có thể cân nhắc `refresh(entity)` trong transaction phù hợp thay vì clear toàn bộ.

### Bulk query và version

Bulk JPQL UPDATE/DELETE thường bỏ qua optimistic version checking/increment trên từng entity như cách provider xử lý entity dirty checking. Không được giả định `@Version` tự bảo vệ mọi bulk query. Muốn versioning đúng với quy tắc của dự án, phải đưa điều kiện/increment vào bulk SQL hoặc dùng cập nhật từng entity trong transaction.

### Native SQL cũng có hệ quả tương tự

~~~java
em.createNativeQuery(
        "UPDATE products SET price = 249000 WHERE id = 101")
    .executeUpdate();
~~~

Native UPDATE không tự làm field `product.price` của một managed entity đã nạp đổi theo. Ngoài ra, trigger hoặc stored procedure có thể thay hàng mà provider không biết ngay. Cần quy tắc đồng bộ context và transaction rõ ràng.

## 22. `refresh()`: đọc lại thay vì giữ dirty state

`em.refresh(p)` nạp lại persistent state của **managed entity** từ database:

~~~java
Product p = em.find(Product.class, 101L);
p.changePrice(new BigDecimal("249000.00"));

em.refresh(p);
~~~

Sau refresh, giá field có thể quay về trạng thái database mà transaction hiện tại đọc được, thay vì giữ 249000 vừa gán trong RAM.

**Chú ý: `refresh()` có thể làm mất dirty changes chưa flush.** Nếu muốn lưu giá mới, không gọi refresh như một bước “xác nhận dữ liệu” một cách máy móc.

Refresh cũng chịu quy tắc isolation:

- Transaction hiện tại có thể đọc những thay đổi do chính nó đã flush.
- Nếu database đang giữ snapshot cũ theo isolation, refresh không nhất thiết đọc được commit mới nhất từ transaction khác.
- Nếu hàng đã bị xóa hoặc thay đổi ngoài context, có thể xảy ra exception hoặc khóa chờ tùy provider/DBMS.

### EntityGraph hoặc query mới có thay `refresh()` không?

Không mặc nhiên. Query JPQL trả về entity có identity đã managed trong context có thể tái sử dụng instance đó. Một query mới không nhất thiết tái nạp mọi field thành giá trị database mới. Muốn ép đồng bộ lại state của entity managed, sử dụng semantics của `refresh()` hoặc context mới một cách có chủ đích.

## 23. Database trigger, default và generated values

Dirty checking chủ yếu hoạt động từ **state Java → SQL**, không phải kênh cập nhật tự động từ **SQL → mọi object Java**.

Ví dụ database trigger tự tăng một cột `audit_counter` hoặc tạo `updated_at` khi UPDATE:

~~~text
Managed entity trước flush:
  price = 249000
  updatedAt = 2027-01-01T10:00Z

DB trigger sau UPDATE:
  price = 249000
  updated_at = 2027-01-02T09:30Z

Managed entity ngay sau flush:
  updatedAt có thể vẫn là giá trị cũ
  nếu mapping/provider không đọc generated value về.
~~~

Nếu ứng dụng cần giá trị do database tạo, có thể cần mapping generated property theo provider, cơ chế SQL `RETURNING` hoặc `refresh()` sau khi đã flush.

### Default của database có thể bị ghi đè

Nếu JPA gửi một cột trong INSERT với giá trị NULL, default SQL không nhất thiết được áp dụng như khi cột bị bỏ khỏi câu INSERT. Thiết kế `insertable = false`, default và giá trị Java phải được phối hợp rõ; đừng chỉ thấy schema có DEFAULT mà tin mọi object sau `persist()` sẽ có giá trị đó.

### Validation và constraint

Dirty checking xác định thay đổi cần ghi, nhưng database vẫn có thể từ chối:

- Giá trị `NOT NULL` bị thiếu.
- Vi phạm `UNIQUE`.
- FK tham chiếu bản ghi không có thật.
- Vi phạm CHECK hoặc constraint của DBMS.
- Optimistic lock conflict.

Lỗi có thể phát sinh khi flush hoặc commit. **Setter chạy thành công không phải bằng chứng transaction đã lưu thành công.**

## 24. Dirty checking và giới hạn của transaction

Một phương thức Java có thể sửa nhiều entity managed:

~~~java
Product p1 = em.find(Product.class, 101L);
Product p2 = em.find(Product.class, 102L);

p1.changePrice(new BigDecimal("199000.00"));
p2.changePrice(new BigDecimal("299000.00"));
~~~

Nếu cả hai thao tác nằm trong một transaction và commit thành công, chúng có thể được đồng bộ như một đơn vị công việc. Nếu một UPDATE thất bại do constraint, transaction thường cần rollback toàn bộ thao tác.

### Transaction rollback không tự “undo” field Java

~~~java
tx.begin();
Product p = em.find(Product.class, 101L);
p.changePrice(new BigDecimal("249000.00"));
em.flush();
tx.rollback();

System.out.println(p.getPrice());
// Object Java vẫn có thể giữ 249000.00.
~~~

Rollback hủy tác động SQL của transaction theo DBMS, nhưng không đảo mọi phép gán field trong JVM. Sau rollback, không nên tiếp tục dùng entity/context đó như nguồn trạng thái đáng tin mà không tái lập ranh giới persistence phù hợp.

### Extended persistence context

Một extended persistence context có thể duy trì managed entities qua nhiều lời gọi hoặc nhiều transaction theo cơ chế JPA/container. Việc sửa object trong RAM không có nghĩa UPDATE sẽ được ghi ngay khi chưa có transaction và synchronization phù hợp. Đây là ví dụ rõ vì sao **managed** và **đang thực hiện transaction ghi** là hai khái niệm liên quan nhưng khác nhau.

## 25. Managed entity trong cùng context có identity ổn định

Một persistence context bảo đảm rằng cùng entity identity có một managed instance tương ứng:

~~~java
Product a = em.find(Product.class, 101L);
Product b = em.find(Product.class, 101L);

System.out.println(a == b); // true

a.changePrice(new BigDecimal("249000.00"));
System.out.println(b.getPrice()); // 249000.00
~~~

Vì `a` và `b` là cùng instance, thay đổi field qua `a` xuất hiện ngay khi đọc bằng `b`.

Nhưng:

~~~java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();
~~~

Hai context có thể có hai instance Java khác nhau cùng đại diện Product#101:

~~~text
em1: Product#101 (price=249000, dirty)
em2: Product#101 (price=199000, managed nhưng stale)
DB:  price=199000 committed, chờ em1 commit
~~~

Khi em1 commit thành công, object ở em2 không tự cập nhật. **Dirty checking của em1 không broadcast giá mới tới các persistence context khác.**

Muốn xử lý cập nhật đồng thời, cần transaction isolation, optimistic/pessimistic locking và chính sách refresh/cache thích hợp.

## 26. Theo dõi thay đổi không đồng nghĩa theo dõi mọi hành động nghiệp vụ

Dirty checking làm việc với **state persistent**, chứ không biết mọi ý nghĩa domain của hành động.

Ví dụ:

~~~java
product.changePrice(new BigDecimal("219000.00"));
product.changePrice(new BigDecimal("249000.00"));
~~~

Provider chỉ cần lưu trạng thái cuối phù hợp; nó không tự lưu hai “sự kiện đổi giá”. Nếu domain yêu cầu audit trail:

~~~text
2027-01-01: user A đổi 199000 -> 219000
2027-01-02: user B đổi 219000 -> 249000
~~~

thì phải có thêm **audit entity**, **domain event**, **outbox** hoặc hệ thống auditing phù hợp, không dựa vào dirty checking như nguồn lịch sử đầy đủ.

### Không nhầm setter với invariant nghiệp vụ

Ví dụ:

~~~java
public void changePrice(BigDecimal newPrice) {
    if (newPrice.signum() < 0) {
        throw new IllegalArgumentException("Giá không âm");
    }
    this.price = newPrice;
}
~~~

Việc validate ở phương thức nghiệp vụ ngăn trạng thái Java không hợp lệ trước khi flush. Nhưng nó không thay thế CHECK constraint hay validation ở các đường ghi khác. Một hệ thống dùng cả JPA và import SQL cần giữ quy tắc dữ liệu nhất quán ở nhiều lớp.

## 27. Dirty checking và hiệu năng: khi nào bị tốn chi phí?

Lợi ích của dirty checking là giảm mã SQL thủ công, nhưng provider phải duy trì managed state và kiểm tra thay đổi ở những mốc đồng bộ.

Một số chi phí:

- Bộ nhớ lưu identity map, snapshots hoặc metadata tracking.
- CPU so sánh/tracking khi flush.
- SQL UPDATE/INSERT/DELETE tùy những field/collection bị thay đổi.
- Chi phí optimistic version check, index maintenance, locks, triggers.
- Chi phí nạp toàn bộ entity khi ứng dụng chỉ cần vài field.

### Đừng giữ persistence context quá lớn

Một batch sửa hàng trăm nghìn entity bằng một EntityManager duy nhất có thể dùng quá nhiều bộ nhớ. Các chiến lược thường gặp:

- Chia transaction thành các lô theo yêu cầu nhất quán.
- `flush()`/`clear()` định kỳ với quản lý reference cẩn thận.
- Dùng bulk DML khi không cần lifecycle/dirty checking từng entity.
- Dùng projection/DTO cho truy vấn chỉ đọc.
- Kiểm soát fetch plan, tránh nạp graph quan hệ không cần thiết.

### UPDATE mọi cột hay chỉ cột đổi?

Một provider có thể tạo UPDATE bao gồm nhiều cột persistent, kể cả một số cột không thực sự đổi, hoặc có cơ chế ghi chỉ các cột dirty. SQL cụ thể **không được JPA chuẩn hóa cho mọi provider**.

Với Hibernate, `@DynamicUpdate` là một tùy chọn **provider-specific** có thể tạo UPDATE chứa những cột được nhận diện là thay đổi. Không mặc định annotation này có hiệu lực trong EclipseLink hoặc mọi provider khác.

Ví dụ Hibernate-specific:

~~~java
@org.hibernate.annotations.DynamicUpdate
@Entity
public class Product {
    // Các field persistent...
}
~~~

Chỉ nên dùng tùy chọn này khi có kết quả đo đạc hoặc lý do cụ thể, bởi việc tạo nhiều SQL shape khác nhau cũng có thể ảnh hưởng cache kế hoạch truy vấn, batching và hiệu năng.

### Read-only entity/session

Ở một số provider, chế độ read-only có thể tắt hoặc thay đổi dirty checking cho những entity nhất định. Ví dụ annotation `@Immutable` của Hibernate hoặc các hint read-only không phải là API JPA portable.

Đặc biệt, `@Transactional(readOnly = true)` trong Spring là **một gợi ý cho infrastructure và cấu hình transaction/ORM**, không phải cam kết chuẩn JPA rằng database chắc chắn từ chối mọi UPDATE. Không nên suy ra “đọc-only” theo tên annotation mà bỏ qua cấu hình thực tế.

## 28. Kiểm tra dirty checking trong môi trường phát triển

Khi muốn xác minh một phương thức service có thực sự cập nhật DB, nên quan sát **hai lớp riêng**:

1. Giá trị trong managed object trước/ sau phương thức nghiệp vụ.
2. Giá trị trong database sau khi transaction commit, đọc bằng context mới phù hợp.

### Mẫu kiểm tra tích hợp

~~~java
// Chuẩn bị một Product#101 có giá 199000 trong database.

EntityManager em = emf.createEntityManager();
try {
    em.getTransaction().begin();

    Product p = em.find(Product.class, 101L);
    p.changePrice(new BigDecimal("249000.00"));

    // Chỉ kiểm tra Java object:
    assert p.getPrice().compareTo(
            new BigDecimal("249000.00")) == 0;

    em.getTransaction().commit();
} finally {
    em.close();
}

// Context mới sau commit: kiểm tra trạng thái persistent.
EntityManager verificationEm = emf.createEntityManager();
try {
    Product reloaded = verificationEm.find(Product.class, 101L);
    assert reloaded.getPrice().compareTo(
            new BigDecimal("249000.00")) == 0;
} finally {
    verificationEm.close();
}
~~~

Đây là đoạn minh họa cho Java SE/RESOURCE_LOCAL, giả sử dữ liệu test đã được thiết lập và không có transaction khác can thiệp. Trong test JUnit, nên dùng assertion của framework thay vì phụ thuộc vào từ khóa `assert` bị vô hiệu hóa nếu JVM không bật assertions.

### Kiểm tra thời điểm phát SQL

Khi bật logging SQL của provider, có thể thấy luồng:

~~~text
SELECT ... FROM products WHERE id=101
application: changePrice(249000)
application: no explicit UPDATE call
UPDATE products ... WHERE id=101 AND version=...
COMMIT
~~~

Đừng hiểu nhầm:

- Log UPDATE **không chứng minh commit đã thành công**.
- Không có UPDATE ngay sau setter **không chứng minh thay đổi không được track**.
- Một flush thành công **không bảo đảm không có lỗi khi commit**, đặc biệt với constraint trì hoãn.
- Một query chạy trong cùng transaction có thể đọc dữ liệu chưa commit của chính transaction đó.

Nếu cần khẳng định dữ liệu đã lưu, kiểm tra sau commit trong context/transaction riêng và xử lý isolation/cache phù hợp.

## 29. Phương pháp điều tra khi JPA “không lưu thay đổi”

Khi code gọi setter nhưng database không đổi, hãy lần lượt đặt câu hỏi:

1. **Entity có managed không?** Kiểm tra `em.contains(entity)` trong context tương ứng nếu cần.
2. **Context còn mở và đang được dùng đúng không?** Có phải object được trả ra khỏi service và đã detached?
3. **Có transaction ghi không?** Có lỗi rollback hoặc service chạy ngoài transaction không?
4. **Field có được ánh xạ không?** Có `@Transient`, sai access type, `updatable=false` hay mapping thiếu không?
5. **Thay đổi có thật sự khác state persistent không?** Có gán lại chính giá trị cũ hoặc normalize về cùng giá trị?
6. **Có flush/commit thành công không?** Exception có bị nuốt, transaction có bị đánh dấu rollback-only không?
7. **Có read-only hint/provider behavior không?** Session/readOnly transaction có thay dirty checking không?
8. **Có update qua bulk/native/trigger không?** Managed state có stale hoặc bị ghi đè do flush sau bulk không?
9. **Có thay đúng owning side của quan hệ không?** Chỉ thêm vào collection `mappedBy` có thể không ghi FK.
10. **Collection có còn là persistent wrapper không?** Code có thay collection reference hoặc dùng equality không ổn định?
11. **Có optimistic lock conflict không?** Version của DB có đổi từ transaction khác?
12. **Đang kiểm tra DB bằng cùng context hay context mới?** First-level cache có thể che state committed thật.

### So sánh các nguyên nhân phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Setter chạy nhưng không UPDATE | Entity đã detached | Nạp managed entity trong transaction rồi sửa; cân nhắc merge có kiểm soát |
| Không có SQL dù field đổi | Field `@Transient` hoặc `updatable=false` | Kiểm tra mapping và yêu cầu nghiệp vụ |
| UPDATE xuất hiện rồi mất sau yêu cầu | Transaction rollback | Xử lý exception/boundary transaction |
| UPDATE được chạy nhưng bản đọc trả giá cũ | Managed instance ở context khác stale | Dùng refresh/context mới theo isolation |
| Bulk UPDATE đúng DB nhưng entity đang giữ sai | Bulk bypass dirty checking per entity | Flush trước; clear/refresh sau nếu cần |
| Thêm child vào collection nhưng FK không đổi | Chỉ sửa inverse side | Đồng bộ owning side và cascade đúng |
| Bị lỗi UNIQUE khi thêm phần tử Map | Cùng key trong nhiều transaction | DB constraint + xử lý conflict |
| `merge()` xong sửa object cũ mà không lưu | Tiếp tục sửa detached thay vì instance trả về | Dùng giá trị do `merge()` trả về |
| Callback `@PreUpdate` không chạy | Không có UPDATE thật sự cần ghi | Không dùng callback như tín hiệu mọi setter |
| Thay một field nhưng UPDATE nhiều cột | SQL generation strategy của provider | Hiểu mapping; cân nhắc tuning dựa trên đo đạc |
| Giá trị do trigger cập nhật không hiện trong object | Provider chưa nạp lại DB-generated field | Generated mapping hoặc refresh |
| Thay giá đồng thời bị conflict | `@Version` phát hiện version cũ | Rollback, báo conflict hoặc retry có kiểm soát |

## 30. Bài tập vận dụng

### Bài 1 — Setter không có SQL

Một service gọi:

~~~java
Product p = em.find(Product.class, 101L);
p.changePrice(new BigDecimal("249000.00"));
~~~

Không có lệnh UPDATE thủ công. Có thể kết luận thay đổi sẽ không được lưu không?

**Gợi ý:** không. Nếu p managed và transaction flush/commit thành công, dirty checking có thể tự tạo UPDATE.

### Bài 2 — DTO khác managed entity

API nhận:

~~~java
UpdateProductRequest request;
request.setPrice(new BigDecimal("249000.00"));
~~~

Vì sao database chưa đổi?

**Gợi ý:** request DTO không phải managed entity. Cần tìm entity managed và áp dụng thay đổi vào field persistent trong transaction.

### Bài 3 — Đổi field `@Transient`

`p.setHighlightedInUi(true)` làm thay đổi object trong JVM. Có kỳ vọng JPA UPDATE bảng sản phẩm không?

**Gợi ý:** không. Field `@Transient` không được lưu vào cột.

### Bài 4 — Detached sau khi đóng EntityManager

Một method trả entity ra ngoài sau khi đóng context; ở controller, ứng dụng gọi setter trên entity đó. Thay đổi có được tự lưu không?

**Gợi ý:** không. Entity đã detached, nên cần service transaction tải managed entity hoặc merge có kiểm soát.

### Bài 5 — Merge trả về đối tượng mới

Code:

~~~java
em.merge(detached);
detached.changePrice(new BigDecimal("299000.00"));
~~~

Điểm nguy hiểm là gì?

**Gợi ý:** thay đổi sau merge vẫn áp dụng cho object detached, không phải instance managed trả về; hãy sử dụng `Product managed = em.merge(detached)`.

### Bài 6 — Dirty checking collection

`Order.items` có `mappedBy="order"`. Khi thêm `OrderItem` mới vào collection, tại sao cần thiết lập `item.order`?

**Gợi ý:** phía item sở hữu FK. Dirty checking collection không thể tự sửa một owning side chưa được cập nhật đúng.

### Bài 7 — UPDATE ở flush hay setter?

Service gọi `changePrice()` ba lần với ba giá khác nhau rồi commit. Có phải chắc chắn có ba câu UPDATE không?

**Gợi ý:** không. Provider có thể đồng bộ trạng thái cuối ở flush, SQL phụ thuộc chiến lược provider và thời điểm flush.

### Bài 8 — Rollback và object RAM

Sau `em.flush()`, transaction rollback nhưng `p.getPrice()` vẫn trả giá mới. Có mâu thuẫn không?

**Gợi ý:** không. Rollback thay đổi database, không tự hoàn nguyên field Java.

### Bài 9 — Bulk UPDATE

`executeUpdate()` thay DB nhưng `Product` managed vẫn có giá cũ. Cần làm gì?

**Gợi ý:** hiểu bulk bypass state đồng bộ per entity; cân nhắc flush pending changes trước và clear/refresh sau.

### Bài 10 — Version conflict

Hai request cùng load Product#101 version 3; request A commit trước, request B commit sau với version cũ. `@Version` hỗ trợ điều gì?

**Gợi ý:** có thể phát hiện lost update nhờ version check và yêu cầu xử lý conflict trong transaction mới.

### Bài 11 — Collection lớn

Một batch cập nhật 200.000 entity trong cùng một context có nguy cơ gì?

**Gợi ý:** snapshots/managed entities tiêu tốn memory và chi phí dirty checking; cân nhắc batching cùng flush/clear có kiểm soát hoặc bulk query phù hợp.

### Bài 12 — Callback audit

Đổi giá từ 199000 thành 209000, rồi đổi về 199000 trước flush. Có thể tin rằng `@PreUpdate` chắc chắn chạy để ghi hai sự kiện đổi giá không?

**Gợi ý:** không. Callback gắn với thao tác UPDATE, không phải mỗi setter. Muốn lịch sử hành động, thiết kế audit riêng.

## 31. Mẫu tư duy áp dụng trong code review

Khi nhìn thấy:

~~~java
managedEntity.changeSomething();
~~~

đừng hỏi ngay “ở đâu có lệnh UPDATE?”. Hãy tách ra bốn câu:

1. **Managed entity:** instance này có thực sự được persistence context theo dõi?
2. **Persistent attribute:** thay đổi có tác động vào field/collection thuộc mapping ghi?
3. **Unit of work:** transaction và flush/commit có diễn ra thành công?
4. **Database correctness:** SQL và các constraint/locking có cho phép trạng thái mới?

Chỉ khi bốn lớp này được xác định thì mới có thể kết luận thay đổi có được lưu đúng hay không.

### Phân biệt trách nhiệm

| Tầng | Trách nhiệm chính |
| --- | --- |
| Domain method | Bảo đảm nghiệp vụ, thay trạng thái object có chủ đích |
| Persistence context | Quản lý identity và theo dõi persistent changes |
| JPA provider | Dịch state pending thành SQL và điều phối mapping/lifecycle |
| Transaction | Bảo đảm tính nguyên tử và xác nhận/rollback các thao tác |
| Database | Thực thi SQL, FK, UNIQUE, CHECK, isolation, locking và committed state |

Điểm mạnh của JPA là ứng dụng có thể **làm việc với object** trong đơn vị công việc mà không phải rải lệnh SQL UPDATE khắp domain code. Điều đó chỉ an toàn khi lập trình viên hiểu ranh giới giữa các tầng.

## Kết luận

**Theo dõi thay đổi entity đang được quản lý (dirty checking)** là cơ chế mà JPA provider sử dụng để nhận diện state persistent đã thay đổi trong một persistence context và đồng bộ state đó xuống database tại thời điểm thích hợp. Với entity managed, việc sửa field qua phương thức nghiệp vụ thường là đủ để provider thực hiện UPDATE khi flush/commit trong transaction hợp lệ; không cần một lời gọi `EntityManager.update()`.

Tuy nhiên, dirty checking **không phải cơ chế quan sát mọi object Java** và không tự giải quyết các vấn đề thuộc transaction, concurrency, caching hoặc ownership quan hệ. Entity detached không còn được theo dõi; `merge()` trả về một managed instance; bulk JPQL/native SQL có thể bỏ qua state của các managed entities đang tồn tại; collection, embeddable và quan hệ hai chiều cần mapping nhất quán. `@Version` giúp phát hiện một số xung đột ghi, còn FK/UNIQUE/CHECK ở database vẫn là hàng rào bảo vệ dữ liệu thật.

Khi thiết kế và debug mã JPA, hãy luôn hỏi: **object có managed không, field nào là persistent, dirty state được flush khi nào, transaction đã commit chưa và database đã thực thi ràng buộc gì?** Trả lời đúng các câu hỏi ấy là nền tảng để sử dụng dirty checking hiệu quả, tránh mất dữ liệu và duy trì vòng đời entity nhất quán.
