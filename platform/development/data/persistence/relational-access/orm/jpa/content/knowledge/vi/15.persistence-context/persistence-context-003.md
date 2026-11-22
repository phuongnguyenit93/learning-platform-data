# Phân biệt trạng thái trong bộ nhớ và trạng thái trong cơ sở dữ liệu với JPA Persistence Context

Một trong những nguồn gây hiểu lầm lớn nhất khi học Jakarta Persistence (JPA) là việc **đối tượng Java đã thay đổi không đồng nghĩa hàng dữ liệu tương ứng trong database đã thay đổi hoặc đã được commit**. Ngược lại, database có thể đã thay đổi bởi transaction khác, trigger hoặc câu lệnh SQL trực tiếp, trong khi đối tượng entity đang được JPA quản lý vẫn giữ giá trị trước đó.

Giả sử ứng dụng quản lý sản phẩm:

~~~java
Product product = em.find(Product.class, 101L);
product.changePrice(new BigDecimal("249000.00"));
~~~

Sau khi chạy hai dòng trên:

- Đối tượng `product` trong JVM có thể đã hiển thị giá mới.
- JPA có thể đã ghi nhận rằng entity managed có thay đổi cần đồng bộ.
- **Database chưa chắc đã nhận bất kỳ câu UPDATE nào.**
- Một transaction khác **chưa chắc** đọc được giá mới, ngay cả khi câu UPDATE đã được gửi nhưng transaction hiện tại chưa commit.

Để hiểu đúng, cần phân biệt ít nhất ba lớp: **trạng thái object trong Java**, **trạng thái quản lý của persistence context**, và **trạng thái của các hàng trong database theo transaction/isolation**. Bài học sẽ đi từ một ví dụ đơn giản tới các tình huống truy vấn, flush, commit, rollback, cache, cập nhật hàng loạt và ghi đồng thời.

## 1. Ba lớp trạng thái không nên đánh đồng

~~~text
Ứng dụng Java
┌──────────────────────────────────────────────────────────────┐
│ Object Product trong JVM                                     │
│     id = 101                                                 │
│     price = 249000.00  <-- Giá trị field hiện tại             │
│                                                              │
│ Persistence Context (do EntityManager quản lý)               │
│     Product#101 là managed                                   │
│     theo dõi identity, state và thay đổi cần ghi             │
└───────────────────────────────────┬──────────────────────────┘
                                    │ flush / SQL
                                    ▼
Cơ sở dữ liệu (transaction hiện tại)
┌──────────────────────────────────────────────────────────────┐
│ Hàng products(id=101)                                        │
│     có thể đã nhận UPDATE nhưng CHƯA COMMIT                  │
└───────────────────────────────────┬──────────────────────────┘
                                    │ commit
                                    ▼
Cơ sở dữ liệu (trạng thái đã commit)
┌──────────────────────────────────────────────────────────────┐
│ Những transaction khác nhìn thấy dữ liệu theo isolation     │
│ và snapshot mà chúng đang sử dụng                            │
└──────────────────────────────────────────────────────────────┘
~~~

Sự khác nhau:

| Lớp | Đơn vị quan sát | Thay đổi khi nào? |
| --- | --- | --- |
| Java object state | Giá trị field/getter của object | Khi ứng dụng gọi setter, sửa collection hoặc phương thức nghiệp vụ |
| Persistence context state | Entity là new, managed, detached, removed; trạng thái được theo dõi | Khi gọi `persist`, `find`, `merge`, `remove`, `detach`, `clear`... |
| Database transactional state | Hàng SQL đã được INSERT/UPDATE/DELETE trong transaction | Khi provider gửi SQL và DBMS thực thi thành công |
| Database committed state | Những thay đổi đã được commit | Khi transaction commit thành công |
| Góc nhìn của transaction khác | Tập phiên bản hàng mà transaction đó đọc được | Theo isolation level, snapshot, khóa và thời điểm đọc |

**Không phải cứ object có giá trị mới thì SQL đã chạy; không phải cứ SQL chạy thì transaction khác đã thấy; không phải cứ transaction khác commit thì managed object hiện tại tự đổi theo.**

## 2. Persistence context là gì?

**Persistence context** là một môi trường quản lý các entity instance và danh tính của chúng. Trong mô hình JPA, một persistence context được gắn với `EntityManager` hoặc do container/framework quản lý theo ranh giới thích hợp. Nó cho phép provider:

1. Nhận diện entity nào đang được quản lý (*managed*).
2. Đảm bảo một danh tính entity có một instance managed tương ứng trong cùng persistence context.
3. Theo dõi thay đổi của entity để đồng bộ xuống database.
4. Quản lý chuyển đổi trạng thái của entity và quan hệ liên quan.
5. Trì hoãn hoặc sắp xếp thao tác SQL khi đồng bộ.

Ví dụ:

~~~java
Product p1 = em.find(Product.class, 101L);
Product p2 = em.find(Product.class, 101L);

System.out.println(p1 == p2); // true trong cùng persistence context
~~~

Nếu cùng loại entity và cùng định danh đã được managed, lần `find` tiếp theo có thể trả về instance sẵn có mà không đọc lại database. Đây là biểu hiện quan trọng của **first-level cache/identity map**.

Tuy nhiên:

~~~java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();
~~~

Hai `EntityManager` này có thể có **hai persistence context khác nhau**. Một `Product#101` managed bởi `em1` không mặc nhiên là cùng object với `Product#101` managed bởi `em2`, và thay đổi trong `em1` không tự cập nhật object trong `em2`.

### Persistence context khác cache dữ liệu toàn hệ thống

First-level cache có phạm vi persistence context. Nó không giống **second-level cache** có thể được provider chia sẻ giữa nhiều context nếu được bật. Ngay cả khi tắt second-level cache, JPA vẫn cần quản lý identity của các entity trong persistence context.

Persistence context cũng **không phải bản sao realtime của database**. Sau khi nạp entity, nó có thể giữ dữ liệu cũ nếu một transaction khác cập nhật hàng tương ứng.

## 3. Một entity tối giản để theo dõi trạng thái

Các ví dụ dưới đây dùng entity `Product` và `EntityManager` kiểu JPA. Cú pháp import dùng namespace `jakarta.persistence`.

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 80)
    private String sku;

    @Column(
        name = "price",
        nullable = false,
        precision = 14,
        scale = 2)
    private BigDecimal price;

    @Version
    private Long version;

    protected Product() {
    }

    public Product(String sku, BigDecimal price) {
        this.sku = Objects.requireNonNull(sku);
        this.price = Objects.requireNonNull(price);
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

    public Long getVersion() {
        return version;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                    "Giá phải là số không âm");
        }
        this.price = newPrice;
    }
}
~~~

DDL PostgreSQL minh họa:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    price NUMERIC(14, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

`@Version` cho provider quản lý phiên bản để phát hiện một số xung đột cập nhật theo optimistic locking. Không dùng `version` làm số thứ tự nghiệp vụ hoặc tự ý gán giá trị cho field này.

Trong ví dụ, annotation nằm trên field, nên JPA dùng **field access**. Phương thức `changePrice()` chỉ thay một field Java; không chứa câu SQL và không cần tự gọi `em.update()` (JPA không định nghĩa phương thức `EntityManager.update()`).

## 4. Vòng đời entity: trạng thái quản lý khác với giá trị field

JPA phân biệt các trạng thái thường gặp:

| Trạng thái | Ý nghĩa | Tình huống |
| --- | --- | --- |
| **New / transient** | Object mới chưa gắn với persistence context | `new Product(...)` |
| **Managed / persistent** | Entity đang được context theo dõi | `em.find(...)`, `em.persist(...)` |
| **Detached** | Object từng có identity persistent nhưng hiện không được context đó quản lý | `em.detach(p)`, `em.clear()`, đóng context |
| **Removed** | Entity được đánh dấu để xóa trong persistence context | `em.remove(p)` khi p managed |

Sơ đồ khái quát:

~~~text
new Product(...)  --persist()--> MANAGED
       |                          |
       |                          | remove()
       |                          v
       |                       REMOVED
       |                          |
       |                          | flush/commit (SQL DELETE)
       |                          v
       |                    Row được xóa ở DB
       |
       +-- object chưa persist vẫn chỉ là object Java

MANAGED --detach()/clear()/close context--> DETACHED
DETACHED --merge()--> có bản managed được trả về
~~~

Sơ đồ cố ý phân biệt **chuyển trạng thái quản lý** với **thực thi SQL**. Ví dụ `persist()` làm một entity trở thành managed, nhưng không nhất thiết đã có INSERT thành công; `remove()` làm entity thành removed, nhưng không chứng minh DELETE đã chạy hoặc commit.

### Một object detached vẫn giữ giá trị trong bộ nhớ

~~~java
Product p = em.find(Product.class, 101L);
em.detach(p);

p.changePrice(new BigDecimal("299000.00"));
~~~

Sau `detach`, giá trị trong `p` đã đổi thành 299000, nhưng context không còn theo dõi `p`. Việc thay field này **không tự phát UPDATE**. Muốn ghi, ứng dụng cần một thao tác rõ ràng, chẳng hạn nạp entity managed rồi cập nhật, hoặc `merge()` có kiểm soát.

## 5. Dirty checking: vì sao không cần gọi UPDATE thủ công?

Khi một entity ở trạng thái **managed**, provider có thể nhận biết field persistent đã thay đổi. Cơ chế này thường được gọi là **dirty checking**.

~~~java
EntityTransaction tx = em.getTransaction();
tx.begin();

Product product = em.find(Product.class, 101L);
product.changePrice(new BigDecimal("249000.00"));

tx.commit();
~~~

Nếu transaction hoàn tất bình thường và entity vẫn managed, provider sẽ đồng bộ thay đổi bằng SQL thích hợp theo chính sách flush. Một câu UPDATE minh họa (không cam kết SQL chính xác của mọi provider) là:

~~~sql
UPDATE products
SET price = 249000.00,
    version = version + 1
WHERE id = 101
  AND version = 4;
~~~

Với `@Version`, provider thường dùng version cũ để bảo vệ khỏi cập nhật trên một phiên bản đã bị người khác thay đổi.

### Điều gì xảy ra ngay sau khi gọi setter?

Xét luồng:

~~~java
Product product = em.find(Product.class, 101L);
product.changePrice(new BigDecimal("249000.00"));

System.out.println(product.getPrice());
// 249000.00 trong object Java.
~~~

Đây **không phải** bằng chứng rằng đã chạy UPDATE. Thay đổi có thể chỉ mới có trong managed object và cơ chế theo dõi state của persistence context.

Khi nào SQL xuất hiện phụ thuộc thao tác tiếp theo, flush mode, transaction, kiểu sinh ID, câu truy vấn và provider. Điểm chắc chắn cần hiểu là **JPA tạo một khoảng cách có chủ đích giữa việc sửa object và thời điểm đồng bộ SQL**.

## 6. `persist()`: entity managed chưa đồng nghĩa INSERT đã commit

Ví dụ:

~~~java
tx.begin();

Product created = new Product(
        "BOOK-JPA-001",
        new BigDecimal("199000.00"));

em.persist(created);

System.out.println(em.contains(created)); // true
System.out.println(created.getId());       // Tùy chiến lược cấp ID.

tx.commit();
~~~

Ngay sau `em.persist(created)`:

- Object trở thành **managed**.
- Persistence context theo dõi entity để chèn vào database.
- Câu INSERT có thể được trì hoãn tới flush, hoặc được phát sớm nếu provider cần ID (đặc biệt với `IDENTITY`).
- Việc đã có ID trong Java **không chứng minh transaction đã commit**.
- Nếu commit thất bại hoặc transaction rollback, dữ liệu có thể không tồn tại ở trạng thái committed của database.

### IDENTITY, SEQUENCE và thời điểm có ID

| Chiến lược | Khả năng cấp ID | Điều không nên suy luận |
| --- | --- | --- |
| `IDENTITY` | Thường phải INSERT để nhận ID do DB sinh | Có ID không đồng nghĩa transaction đã commit |
| `SEQUENCE` | Có thể lấy giá trị sequence trước INSERT | Có ID không đồng nghĩa row đã được tạo |
| UUID do provider/ứng dụng cấp | Có thể có ID trước SQL | Có ID không đồng nghĩa database đã biết object |

Sequence có thể tiêu thụ giá trị ngay cả khi transaction rollback, nên việc ID bị bỏ trống là bình thường. Không nên lấy tính liên tục của surrogate ID làm tiêu chí xác định transaction thành công.

## 7. `flush()` làm gì?

**Flush** là quá trình provider đồng bộ những thay đổi đang chờ trong persistence context với database, thường bằng các lệnh INSERT, UPDATE và DELETE. Nó **không phải commit**.

~~~java
tx.begin();

Product product = em.find(Product.class, 101L);
product.changePrice(new BigDecimal("249000.00"));

em.flush();   // Yêu cầu đồng bộ trạng thái đang chờ bằng SQL.

// Transaction chưa commit.
tx.commit();
~~~

Sau `em.flush()` thành công:

1. Provider đã cố gắng đồng bộ các thay đổi cần thiết theo flush rules.
2. Database có thể đã thực thi UPDATE trong transaction hiện tại.
3. Transaction vẫn có thể bị rollback về sau.
4. Transaction khác có thể chưa nhìn thấy giá mới theo isolation.
5. Giá trị trong managed entity vẫn là trạng thái object của persistence context.

Không nên viết:

~~~text
flush == commit
~~~

Mô hình chính xác hơn:

~~~text
changePrice()            em.flush()                    tx.commit()
      |                       |                             |
      v                       v                             v
Đổi object Java       Đồng bộ SQL trong TX            Xác nhận TX
      |                       |                             |
      +-- giá mới trong RAM   +-- DB có thay đổi chưa commit +-- DB commit
~~~

### Flush có thể xảy ra không cần gọi tường minh

JPA provider có thể flush:

- Trước transaction commit.
- Trước một số truy vấn để bảo đảm kết quả phản ánh các thay đổi pending theo flush mode.
- Khi ứng dụng gọi `em.flush()`.
- Khi cần thực thi INSERT để cấp ID hoặc bảo đảm ràng buộc theo cách triển khai.

Vì vậy **không nên đếm câu SQL chỉ bằng số lần gọi `flush()` hoặc `commit()`**.

### Flush yêu cầu transaction phù hợp

Với transaction-scoped persistence context và các thao tác ghi thông thường, gọi `flush()` ngoài transaction có thể phát sinh `TransactionRequiredException`. Trong môi trường dùng container-managed entity manager, transaction do framework/container điều phối; không nên tự gọi `getTransaction()` khi đang dùng JTA-managed `EntityManager`.

## 8. `commit()` khác `flush()` thế nào?

**Commit** là hành động kết thúc transaction thành công theo DBMS. Nó xác nhận các thay đổi SQL của transaction, làm chúng trở thành trạng thái committed của database.

Ví dụ:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = em.find(Product.class, 101L);
    product.changePrice(new BigDecimal("249000.00"));

    em.flush();    // SQL trong transaction.
    tx.commit();   // Transaction được commit.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Sau commit thành công, một transaction mới thường có thể đọc giá mới theo cơ chế isolation và routing dữ liệu của hệ thống. Nhưng **transaction đã có snapshot cũ** ở isolation như repeatable read/snapshot isolation có thể vẫn đọc giá trước đó cho tới khi transaction ấy kết thúc.

Ngay cả khi có commit:

- Một instance managed trong persistence context khác **không bắt buộc được tự refresh**.
- Một read replica có độ trễ sao chép có thể chưa hiện giá mới.
- Một ứng dụng dùng cache ngoài hoặc cache provider cần chính sách invalidation/consistency riêng.

Do đó phát biểu chính xác là: **commit xác nhận thay đổi tại database theo transaction**, chứ không hứa mọi đối tượng trong mọi JVM lập tức mang giá trị mới.

## 9. Bảng thời gian: object, SQL và commit

Giả sử database ban đầu có:

~~~sql
products(id=101, price=199000.00, version=4)
~~~

Trong transaction T1:

| Mốc | Thao tác | `product.getPrice()` trong T1 | Hàng SQL trong T1 | Giá đã commit nhìn từ transaction mới |
| --- | --- | --- | --- | --- |
| 0 | Chưa bắt đầu | Chưa có object | 199000 | 199000 |
| 1 | `find(101)` | 199000 | 199000 | 199000 |
| 2 | `changePrice(249000)` | **249000** | Có thể vẫn 199000 | 199000 |
| 3 | `flush()` thành công | **249000** | **249000 (chưa commit)** | Thông thường vẫn 199000 |
| 4 | `commit()` thành công | 249000 (nếu object còn được giữ) | 249000 | **249000** với transaction mới phù hợp |

Nếu transaction T1 bị rollback ở mốc 4:

- Database phục hồi những thay đổi SQL chưa commit của T1 theo cơ chế transaction.
- Biến Java `product` **không tự được phục hồi về 199000**.
- Object có thể vẫn trả về 249000, dù hàng committed trong database là 199000.
- Không nên tiếp tục coi persistence context của transaction bị lỗi là nguồn trạng thái chính xác; thông thường cần kết thúc context/đơn vị công việc và nạp lại trong transaction mới.

Đây là một trong những biểu hiện rõ nhất của khác biệt giữa **RAM state** và **committed database state**.

## 10. Rollback không phải nút “undo” của mọi object Java

Xem đoạn:

~~~java
Product product = null;

try {
    tx.begin();
    product = em.find(Product.class, 101L);
    product.changePrice(new BigDecimal("900000.00"));

    em.flush();
    throw new IllegalStateException("Giả lập lỗi nghiệp vụ");
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
}

System.out.println(product.getPrice());
// Object Java vẫn có thể in ra 900000.00.
~~~

Database có thể đã rollback UPDATE, nhưng biến `product` tham chiếu đến một object trong JVM và **không có cơ chế mặc định tự đảo ngược các phép gán field khi SQL rollback**.

### Không tái dùng object như thể transaction đã thành công

Sau rollback, trạng thái entity instance và khả năng tiếp tục sử dụng persistence context phụ thuộc lifecycle/context/provider. Một lựa chọn rõ ràng là:

1. Kết thúc transaction thất bại.
2. Đóng hoặc clear context theo ranh giới ứng dụng.
3. Mở transaction/persistence context mới.
4. Nạp lại entity từ database theo yêu cầu.

Đừng sửa chữa bằng cách tự gán ngược tất cả field nếu còn collection, quan hệ, ID được sinh, callback và trigger phức tạp; làm thế không bảo đảm tái tạo đúng trạng thái của database.

## 11. First-level cache: cùng context không tự nạp lại từ database

Giả sử:

~~~java
Product product = em.find(Product.class, 101L);
System.out.println(product.getPrice()); // 199000
~~~

Sau đó một transaction **khác** commit giá 249000 cho hàng 101. Nếu context hiện tại vẫn quản lý `Product#101`:

~~~java
Product again = em.find(Product.class, 101L);
System.out.println(again == product);  // true
System.out.println(again.getPrice());   // Có thể vẫn là 199000.
~~~

Vì persistence context đã giữ một managed instance cho ID đó, lần `find` tiếp theo không mặc nhiên kiểm tra database để xem hàng đã bị người khác đổi chưa.

### Vậy tính nhất quán của JPA là kiểu nào?

Persistence context bảo đảm **identity và cách theo dõi object** trong phạm vi context. Nó không cung cấp một luồng cập nhật realtime từ tất cả transaction khác.

Muốn nhìn dữ liệu mới, ứng dụng có thể:

- Gọi `em.refresh(product)` khi cần nạp lại hàng tương ứng.
- Gọi `em.clear()` hoặc đóng context, sau đó dùng context mới để `find`.
- Thiết kế transaction ngắn theo request hoặc đơn vị công việc.
- Dùng optimistic/pessimistic locking khi cần xử lý xung đột ghi.

Các lựa chọn này có ý nghĩa khác nhau; không nên gọi `refresh()` theo thói quen trên mọi entity vì có thể gây thêm SELECT và làm mất các thay đổi chưa flush.

## 12. `refresh()`: lấy lại trạng thái từ database

`EntityManager.refresh(entity)` yêu cầu nạp lại persistent state của **managed entity** từ database theo ngữ nghĩa hiện hành của transaction.

~~~java
Product product = em.find(Product.class, 101L);

product.changePrice(new BigDecimal("249000.00"));
em.refresh(product);

System.out.println(product.getPrice());
// Giá sẽ phản ánh trạng thái DB mà refresh đọc được,
// không nhất thiết giữ 249000 vừa gán trong bộ nhớ.
~~~

**Điểm nguy hiểm:** `refresh()` có thể **ghi đè những thay đổi chưa được flush** trên entity bằng giá trị đọc từ database. Nếu mục tiêu là lưu giá mới, không nên gọi `refresh` trước khi những thay đổi đó được đồng bộ và có chiến lược transaction phù hợp.

### Refresh nhìn thấy dữ liệu nào?

Nó đọc theo ngữ cảnh transaction và quy tắc isolation. Ví dụ:

- Trong transaction hiện tại, nếu đã flush UPDATE, chính transaction đó có thể đọc được thay đổi chưa commit của mình.
- Nếu transaction khác vừa commit nhưng context hiện tại giữ snapshot cũ, refresh vẫn có thể đọc phiên bản hợp lệ theo snapshot đó.
- Nếu hàng đã bị xóa bởi transaction khác, refresh có thể dẫn đến exception tùy thời điểm và provider.

**Refresh không bảo đảm vượt qua isolation level của database để nhìn mọi commit mới nhất trong mọi trường hợp.**

## 13. `detach()` và `clear()`: ngừng quản lý không đồng nghĩa rollback

`detach(entity)` làm một entity không còn được context đó quản lý:

~~~java
Product product = em.find(Product.class, 101L);
em.detach(product);

product.changePrice(new BigDecimal("299000.00"));
// Không tự đồng bộ bởi EntityManager này.
~~~

`clear()` tách **tất cả các entity managed** khỏi persistence context:

~~~java
em.clear();
~~~

Hai thao tác này tác động tới **trạng thái quản lý**, không giống rollback transaction.

### Pending changes có thể bị mất

Ví dụ:

~~~java
Product product = em.find(Product.class, 101L);
product.changePrice(new BigDecimal("249000.00"));
em.clear();
~~~

Nếu những thay đổi chưa được flush thì chúng có thể **không còn được provider đồng bộ**, vì object đã detached. Điều này rất khác với:

~~~java
product.changePrice(new BigDecimal("249000.00"));
em.flush();
em.clear();
~~~

Ở đoạn thứ hai, SQL có thể đã chạy trong transaction trước khi `clear()`. `clear()` không xóa ngược SQL đã gửi; nếu muốn hủy thay đổi transactional, phải dùng **rollback**.

| Thao tác | Ảnh hưởng tới context | Ảnh hưởng tới SQL đã thực thi | Rủi ro với thay đổi chưa flush |
| --- | --- | --- | --- |
| `detach(p)` | p trở thành detached | Không tự rollback SQL | Thay đổi pending của p có thể không được ghi |
| `clear()` | Detach tất cả managed entities | Không tự rollback SQL | Nhiều thay đổi pending có thể không được ghi |
| `refresh(p)` | p vẫn managed | Đọc lại state từ DB | Giá trị Java mới có thể bị ghi đè |
| `rollback()` | Hủy transaction DB | DB rollback thay đổi của transaction | Object Java không tự khôi phục |

Với một batch lớn, gọi `flush()` rồi `clear()` theo đợt có thể giảm số managed entities mà provider phải theo dõi. Nhưng chiến lược batch phải đi cùng transaction, cách cấp ID và kiểm soát lỗi phù hợp; không coi `clear()` là thao tác miễn phí.

## 14. `merge()`: bản detached không tự trở lại thành managed

Một hiểu lầm khác là nghĩ `merge(detached)` sẽ làm chính object truyền vào trở thành managed. Trong JPA, `merge()` **trả về một instance managed** có trạng thái được hợp nhất; object detached ban đầu không vì thế mà trở thành managed.

~~~java
Product detached = ...; // Product từng được nạp trong context cũ.

Product managed = em.merge(detached);

System.out.println(managed == detached);
// Không nên giả định true.
~~~

Sau `merge`:

- `managed` là tham chiếu cần dùng tiếp trong context hiện tại.
- `detached` vẫn là detached.
- Việc ghi SQL phụ thuộc flush/commit.
- State từ detached có thể ghi đè state đang có trong persistence context theo quy tắc merge; cần cẩn trọng với dữ liệu detached cũ.

### Mẫu cập nhật có kiểm soát thường dễ hiểu hơn

Trong service nhận request sửa giá:

~~~java
public void updatePrice(
        EntityManager em, long productId, BigDecimal newPrice) {

    Product managed = em.find(Product.class, productId);
    if (managed == null) {
        throw new IllegalArgumentException("Không có sản phẩm");
    }

    managed.changePrice(newPrice);
    // Transaction commit sẽ đồng bộ.
}
~~~

Như vậy ứng dụng chỉ sửa field được phép trên managed entity, thay vì `merge` nguyên object graph do client gửi. Với HTTP DTO có thể thiếu field, `merge` tùy tiện còn có nguy cơ ghi giá trị null hoặc trạng thái cũ lên dữ liệu hiện hành.

### `@Version` và detached entity

Entity có `@Version` có thể giúp phát hiện cập nhật trên version cũ trong quá trình merge/flush. Tuy nhiên, optimistic locking không miễn trừ nhu cầu thiết kế luồng xử lý conflict, không tự biến detached graph thành bản mới nhất của database.

## 15. JPQL query có thể kích hoạt flush và nhìn state nào?

Giả sử trong một transaction:

~~~java
Product p = em.find(Product.class, 101L);
p.changePrice(new BigDecimal("249000.00"));

List<Product> expensive = em.createQuery(
        "SELECT p FROM Product p WHERE p.price >= :min",
        Product.class)
    .setParameter("min", new BigDecimal("240000.00"))
    .getResultList();
~~~

Câu hỏi: truy vấn này có phải thấy Product#101 theo giá mới không?

Điều đó phụ thuộc vào **flush mode** và khả năng provider xác định ảnh hưởng của các thay đổi pending.

### `FlushModeType.AUTO`

Với `AUTO`, JPA yêu cầu provider bảo đảm rằng các thay đổi trong persistence context có thể ảnh hưởng kết quả truy vấn phải **được phản ánh trong kết quả** theo quy tắc của specification. Provider có thể flush SQL trước query hoặc sử dụng cơ chế khác có hiệu quả tương đương.

Trong mô hình này, truy vấn lọc `price >= 240000` phải được xử lý nhất quán với sự thay đổi giá pending của managed entity, theo điều kiện transaction thích hợp.

### `FlushModeType.COMMIT`

Với `COMMIT`, provider có thể trì hoãn flush tới transaction commit. Ảnh hưởng của các thay đổi pending đối với kết quả truy vấn **không được định nghĩa chặt theo cùng cách như AUTO**. Vì vậy một truy vấn lọc tại DB có thể không phản ánh thay đổi đang chờ theo cách lập trình viên dự đoán.

Ví dụ đổi flush mode:

~~~java
em.setFlushMode(FlushModeType.COMMIT);
~~~

Cần import `jakarta.persistence.FlushModeType`. Đừng đổi sang `COMMIT` chỉ để giảm số UPDATE mà không xem lại các query phụ thuộc dữ liệu pending trong cùng transaction.

### `find` và JPQL có khác nhau?

`em.find(Product.class, 101L)` có thể dùng ngay instance đã managed, không cần SQL; còn JPQL lọc theo giá có thể cần gửi truy vấn tới database, kích hoạt quy tắc flush mode. Tuy nhiên, khi JPQL trả về chính entity có identity đã nằm trong persistence context, provider thường sử dụng managed instance cho identity đó, không tạo một object managed độc lập khác.

Điều này có thể tạo cảm giác khó hiểu:

- **Tập hàng** được SQL/query lọc theo một trạng thái.
- **Giá trị field** của object entity trả về có thể là trạng thái đang được giữ trong context.

Để xác định điều đã xảy ra, hãy tách hai câu hỏi: *truy vấn lọc bằng dữ liệu nào?* và *instance entity nào được trả về cho ID đó?*

## 16. JPQL bulk UPDATE/DELETE có thể làm context bị lệch

Một tình huống đặc biệt quan trọng: **bulk JPQL UPDATE/DELETE** đi trực tiếp đến database theo cơ chế truy vấn, không cập nhật từng managed entity như việc gọi setter.

Ví dụ:

~~~java
Product product = em.find(Product.class, 101L);

int changed = em.createQuery(
        "UPDATE Product p "
      + "SET p.price = :price "
      + "WHERE p.id = :id")
    .setParameter("price", new BigDecimal("199000.00"))
    .setParameter("id", 101L)
    .executeUpdate();

System.out.println(changed);
System.out.println(product.getPrice());
// product có thể vẫn giữ giá đã nạp trước bulk UPDATE.
~~~

Bulk UPDATE làm thay đổi hàng database nhưng **không buộc provider phải cập nhật state của managed object tương ứng**. Với bulk DELETE, các object managed có thể vẫn hiện diện trong context dù hàng SQL đã bị xóa.

### Quy trình làm việc với bulk operation

Một mẫu hợp lý trong transaction:

~~~java
em.flush();  // Đồng bộ các thay đổi managed đang chờ trước bulk.

int count = em.createQuery(
        "UPDATE Product p SET p.price = :newPrice "
      + "WHERE p.price < :threshold")
    .setParameter("newPrice", new BigDecimal("100000.00"))
    .setParameter("threshold", new BigDecimal("100000.00"))
    .executeUpdate();

em.clear();  // Bỏ managed instances có thể đã stale.
~~~

**Ý nghĩa:**

1. `flush()` trước bulk để giảm nguy cơ những thay đổi đang chờ bị ghi sau bulk và ghi đè kết quả.
2. `executeUpdate()` thực hiện bulk operation.
3. `clear()` detach các entity cũ để lần nạp sau có thể đọc lại.

Đây là mẫu cho **đơn vị công việc đã sẵn sàng bỏ các reference managed hiện tại**. Nếu còn thay đổi pending hoặc code sau `clear()` tiếp tục sử dụng những object detached như thể managed, có thể phát sinh lỗi nghiệp vụ.

### Bulk UPDATE và `@Version`

Bulk update trong JPQL thường **không tự thực hiện optimistic version checking/increment trên từng entity** như cập nhật managed entity thông thường. Nếu yêu cầu bảo vệ version, phải thiết kế explicit query hoặc thay cách cập nhật theo cơ chế phù hợp. Không coi `@Version` là lá chắn tự động cho mọi câu bulk SQL.

### Native SQL cũng có nguy cơ tương tự

Khi dùng:

~~~java
em.createNativeQuery(
        "UPDATE products SET price = 100000 WHERE id = 101")
    .executeUpdate();
~~~

database có thể thay đổi nhưng managed `Product#101` đã nạp vẫn mang giá cũ. Thao tác native SQL không tự làm mọi entity object được refresh. Ngoài ra, flush behavior khi chạy native query có thể khác theo provider và API; nếu cần thứ tự xác định, hãy chủ động thiết kế transaction và đồng bộ context.

## 17. Database default, trigger và generated column có thể làm lệch object

Giả sử schema có:

~~~sql
CREATE TABLE audit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Nếu một entity JPA không ghi `created_at` trong INSERT, database có thể tự tạo giá trị bằng default. Nhưng object Java **chưa chắc đã được provider nạp giá trị đó ngay**.

Các nguồn giá trị do database tạo có thể gồm:

- Giá trị DEFAULT khi INSERT.
- Trigger tính `updated_at` hoặc thay đổi giá trị business.
- Generated/computed column.
- Sequence/identity sinh khóa.
- Quy tắc chuẩn hóa dữ liệu ở database.

Ví dụ:

~~~text
Java object trước INSERT:
createdAt = null

Database sau INSERT:
created_at = 2027-04-01 09:15:00+00

Java object ngay sau INSERT:
createdAt có thể vẫn null nếu mapping/provider không nạp lại.
~~~

**Không nên giả định database default luôn xuất hiện tự động trong field Java.** Có thể cần:

1. Mapping chuyên dụng cho giá trị generated theo provider.
2. Cơ chế `RETURNING` hoặc SQL đặc thù được provider hỗ trợ.
3. `em.refresh(entity)` sau khi INSERT đã đồng bộ, với transaction/isolation phù hợp.
4. Nạp lại entity trong context mới.

### Trigger thay đổi dữ liệu ứng dụng vừa gửi

Nếu database trigger biến `sku` thành chữ hoa hoặc chuẩn hóa giá, object Java vừa persist có thể còn giữ giá trị trước trigger. Điều này làm lộ rõ phân biệt giữa **trạng thái object do ứng dụng gán** và **trạng thái cuối cùng của hàng SQL sau database processing**.

Với column generated và optimistic locking, cần thiết kế mapping đúng cho cột do DB kiểm soát; không tùy tiện ghi thủ công vào field đó.

## 18. Isolation: flush xong nhưng transaction khác vẫn thấy giá cũ

Giả sử hai transaction T1 và T2:

~~~text
T1                                      T2
----------------------------------      ----------------------------------
BEGIN                                   BEGIN
find(Product#101) = 199000              find(Product#101) = 199000
changePrice(249000)
flush() -> DB đã UPDATE trong T1
                                        Đọc lại theo isolation:
                                        có thể vẫn thấy 199000
COMMIT
                                        Nếu giữ managed Product#101:
                                        vẫn có thể thấy 199000
                                        nếu không refresh/clear
                                        và theo snapshot/isolation
                                        thích hợp
~~~

Có **hai lý do khác nhau** khiến T2 còn thấy 199000:

1. T1 chưa commit, nên isolation thường ngăn T2 đọc thay đổi chưa commit.
2. T2 đã có một managed entity hoặc transaction snapshot cũ, nên kể cả sau T1 commit, T2 không mặc nhiên nạp lại dữ liệu mới.

### Tách hiệu ứng của context và database isolation

Nếu muốn biết giá trị T2 thấy cũ vì nguyên nhân nào, có thể thử:

- Kiểm tra T1 đã commit hay chưa.
- Kiểm tra transaction T2 có cùng snapshot trước commit của T1 hay không.
- Kiểm tra T2 có đang giữ entity managed trong first-level cache hay không.
- Dùng transaction/context mới để loại trừ ảnh hưởng của entity đã nạp.
- Hiểu isolation level thực tế của DBMS: READ COMMITTED, REPEATABLE READ, SERIALIZABLE và các chế độ snapshot có hành vi khác nhau.

**Không có quy tắc rằng gọi `em.refresh()` là luôn nhìn thấy mọi commit mới**: refresh vẫn làm việc trong transaction và isolation hiện tại.

### Đọc chưa commit là trường hợp đặc biệt

Một số DBMS/isolation cho phép đọc bẩn ở chế độ cụ thể, nhưng không nên thiết kế nghiệp vụ dựa trên việc transaction khác nhìn thấy dữ liệu sau flush mà trước commit. Mô hình thông thường cần coi trạng thái chưa commit là **chưa được công bố đáng tin cậy**.

## 19. Lost update: hai persistence context cùng sửa một hàng

Giả sử hai request cùng đọc Product#101 giá 199000:

~~~text
T1: Product#101 price=199000, version=4
T2: Product#101 price=199000, version=4

T1: changePrice(249000)
T1: flush/commit -> version=5

T2: changePrice(209000)
T2: flush/commit -> cố cập nhật với version=4
                    => optimistic locking conflict
~~~

Nếu không có cơ chế kiểm soát concurrency, thao tác sau có thể ghi đè thao tác trước theo thứ tự SQL và isolation. Với `@Version`, provider thường cập nhật với điều kiện version cũ và phát hiện không có hàng phù hợp khi version đã đổi.

### `@Version` bảo vệ điều gì?

`@Version` liên kết phiên bản managed entity với lần cập nhật SQL. Khi hai context cùng sửa cùng entity từ bản cũ, một thao tác có thể bị từ chối bởi optimistic locking.

Ứng dụng cần:

1. Bắt lỗi optimistic locking thích hợp theo layer.
2. Rollback transaction thất bại.
3. Nạp lại dữ liệu trong context mới.
4. Cho người dùng giải quyết xung đột hoặc thực hiện retry nếu phép toán an toàn/idempotent.

**Không nên tự động retry vô hạn một thay đổi ghi đè ý định của người dùng.**

### Đừng xem version trong memory là trạng thái DB mới nhất

Một object có `version = 4` có thể đã stale nếu database đã lên version 5 trong transaction khác. Version trong entity là một **ảnh chụp của lần đọc/ghi mà context biết**, không phải bộ đếm realtime được broadcast tới mọi JVM.

## 20. Khóa bi quan và góc nhìn object/DB

Với một số nghiệp vụ cần kiểm soát chặt việc sửa đồng thời, JPA cho phép khóa bi quan:

~~~java
Product product = em.find(
        Product.class,
        101L,
        LockModeType.PESSIMISTIC_WRITE);
~~~

Đoạn này cần import `jakarta.persistence.LockModeType` và transaction đang hoạt động. Provider có thể ánh xạ sang cơ chế khóa row như `SELECT ... FOR UPDATE` hoặc lệnh thích hợp với DBMS.

Pessimistic lock giúp điều phối việc truy cập hàng database, nhưng:

- Không làm setter tự động commit.
- Không bảo đảm managed object trong context khác tự refresh.
- Có thể gây blocking, timeout hoặc deadlock khi các transaction khóa tài nguyên theo thứ tự khác nhau.
- Phạm vi và hành vi lock phụ thuộc DBMS, dialect và loại query.

Với read-only reporting, không nên thêm `PESSIMISTIC_WRITE` theo thói quen. Chọn chiến lược locking theo mức xung đột và yêu cầu nhất quán thực sự.

## 21. Quan hệ entity: hai phía Java có thể khác trạng thái FK trong DB

Tình huống phân biệt memory/DB không chỉ xảy ra ở field basic. Giả sử:

~~~java
@Entity
public class Employee {

    @Id
    private Long id;

    @ManyToOne
    @JoinColumn(name = "department_id")
    private Department department;

    public void setDepartment(Department department) {
        this.department = department;
    }
}
~~~

Và phía `Department` có:

~~~java
@OneToMany(mappedBy = "department")
private List<Employee> employees = new ArrayList<>();
~~~

Trong một quan hệ hai chiều kiểu này:

- `Employee.department` là owning side vì giữ FK.
- `Department.employees` là inverse side vì có `mappedBy`.
- Cột SQL `employees.department_id` do mapping ở owning side xác định.

Nếu ứng dụng chỉ làm:

~~~java
department.getEmployees().add(employee);
~~~

thì collection Java có thể hiện nhân viên, nhưng owning side `employee.department` chưa đổi, nên **không thể dựa vào thay đổi inverse collection đơn độc để đảm bảo FK được cập nhật**.

Đoạn có ý nghĩa lưu đúng quan hệ là:

~~~java
employee.setDepartment(department);
department.getEmployees().add(employee);
~~~

Ở đây, dòng đầu quyết định FK; dòng thứ hai đồng bộ object graph trong memory. Cả hai vẫn cần transaction và flush/commit để database lưu thay đổi.

### Một quan hệ Java “đúng” chưa chắc đã tồn tại ở DB

Ví dụ:

~~~java
Employee employee = new Employee();
employee.setDepartment(new Department());
~~~

Nếu `Department` mới là transient và quan hệ không có cascade persist phù hợp, provider có thể gặp lỗi khi flush. Một tham chiếu object hợp lệ trong JVM không chứng minh hàng cha có PK/FK hợp lệ trong database.

### Collection và orphan removal

Khi xóa một item khỏi collection managed có `orphanRemoval = true`, provider có thể lên lịch xóa entity con. Nhưng trước flush hoặc commit, object vẫn có thể còn tồn tại trong memory và hàng DB vẫn chưa bị xóa. Không đồng nhất **đã remove khỏi List** với **đã DELETE hàng thành công**.

## 22. Ràng buộc DB có thể chỉ phát lỗi khi flush hoặc commit

Giả sử database có:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    price NUMERIC(14,2) NOT NULL
);
~~~

Nếu ứng dụng tạo hai entity cùng SKU:

~~~java
em.persist(new Product("DUPLICATE", new BigDecimal("100.00")));
em.persist(new Product("DUPLICATE", new BigDecimal("200.00")));
~~~

JPA có thể chấp nhận các thao tác trên ở mức object trong một giai đoạn, nhưng khi các INSERT được gửi, database sẽ phát hiện unique constraint violation. Thời điểm lỗi cụ thể phụ thuộc chiến lược cấp ID, flush và DBMS.

Tương tự:

- FK tham chiếu hàng chưa tồn tại có thể thất bại khi INSERT/UPDATE.
- NOT NULL có thể thất bại khi giá trị null được ghi.
- CHECK constraint có thể chặn dữ liệu không hợp lệ.
- Một số DBMS hỗ trợ constraint deferrable, có thể trì hoãn việc kiểm tra tới cuối transaction.

### Ý nghĩa thực tế

**Không bắt exception ngay sau `persist()` không đồng nghĩa bản ghi chắc chắn hợp lệ ở DB.** Ứng dụng cần để transaction hoàn tất và xử lý exception ở flush/commit đúng ranh giới.

Khi operation phụ thuộc nhiều câu ghi, hãy để tất cả trong một transaction thích hợp để rollback khi bất kỳ constraint nào thất bại.

## 23. Một câu native SQL có thể không đồng bộ với managed entity

Giả sử:

~~~java
Product product = em.find(Product.class, 101L);
// product.price = 199000
~~~

Một thao tác khác gửi SQL trực tiếp:

~~~java
em.createNativeQuery(
        "UPDATE products SET price = 299000.00 WHERE id = 101")
    .executeUpdate();
~~~

Khi gọi:

~~~java
System.out.println(product.getPrice());
~~~

object managed **có thể vẫn in 199000** vì JPA không bắt buộc tự nạp lại state của mọi managed object khi native SQL sửa bảng.

Trong trường hợp cần đọc đúng giá vừa thay bằng native SQL, có thể:

~~~java
em.refresh(product);
~~~

Nhưng cần lưu ý:

- SQL native chạy trong transaction nào?
- Provider có pending dirty changes cho cùng hàng không?
- Refresh trong transaction này sẽ nhìn dữ liệu nào theo isolation?
- Có trigger và generated column làm thay đổi thêm các giá trị khác không?

Nếu đang dùng nhiều kết nối JDBC khác nhau, trạng thái chưa commit trên một kết nối **không mặc nhiên nhìn thấy được** trên kết nối khác. Chỉ coi các thao tác là cùng transaction khi hạ tầng thật sự quản lý chúng chung.

## 24. Second-level cache không giải quyết tự động mọi stale state

Một số JPA provider có **second-level cache** hoặc query cache để giảm truy vấn database giữa các persistence context. Cần phân biệt:

| Cơ chế | Phạm vi | Nguy cơ hiểu nhầm |
| --- | --- | --- |
| First-level cache / persistence context | Một context | `find` có thể trả managed entity cũ thay vì đọc lại DB |
| Second-level cache | Nhiều context tùy cấu hình provider | Có thể chứa dữ liệu stale nếu invalidation hoặc chính sách concurrency không phù hợp |
| Query cache (provider-specific) | Kết quả truy vấn/cache khóa kết quả | Có thể dùng danh sách ID hoặc result cũ theo chính sách |
| Database buffer/cache | Tầng DBMS | Không giống object cache của JPA và vẫn phải tuân thủ isolation |

Khi có lỗi “database đã đổi nhưng API trả dữ liệu cũ”, cần kiểm tra:

1. Cùng persistence context đã giữ entity từ trước chưa?
2. Transaction có snapshot cũ không?
3. Provider có second-level/query cache không?
4. Câu SQL có thật sự được gửi không?
5. Có read replica, service cache hoặc CDN nằm ngoài JPA không?

Không nên chỉ tắt toàn bộ cache khi chưa biết dữ liệu stale xuất hiện ở lớp nào.

## 25. Logging và quan sát SQL: phải hiểu giới hạn của log

Trong quá trình phát triển, xem SQL do provider phát giúp xác định lúc nào persistence context đồng bộ. Ví dụ:

~~~text
BEGIN
SELECT ... FROM products WHERE id = 101
(ứng dụng gọi changePrice)
(chưa có UPDATE ở log)
UPDATE products SET price = ?, version = ? WHERE id = ? AND version = ?
COMMIT
~~~

Tuy nhiên:

- **Log SQL có UPDATE** không chứng minh transaction đã commit.
- **Log không có UPDATE ngay sau setter** không chứng minh JPA sẽ không ghi sau này.
- **Có câu SELECT trong log** không bảo đảm query đọc giá mới nhất nếu transaction có snapshot cũ.
- **Không thấy SELECT lần thứ hai** có thể do first-level cache, nhưng cũng có thể do fetch plan/batch hoặc query cache; cần xem bối cảnh.
- **SQL đã gửi** chưa chắc tương ứng số hàng đã thay đổi nếu optimistic lock/FK/constraint gây lỗi.

Để quan sát sự khác biệt, nên dùng một transaction/EntityManager khác khi muốn kiểm tra **committed state**. Truy vấn native trong cùng EntityManager và transaction có thể nhìn thấy thay đổi chưa commit của chính transaction đó, nên không phải bằng chứng rằng người dùng khác cũng nhìn thấy.

## 26. Ví dụ tổng hợp với hai EntityManager

Đoạn dưới mô tả luồng khác biệt giữa state Java và committed DB. Giả sử Product#101 đã có sẵn và DBMS dùng một isolation thông thường không cho dirty read.

~~~java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();

EntityTransaction tx1 = em1.getTransaction();
EntityTransaction tx2 = em2.getTransaction();

try {
    tx1.begin();

    Product p1 = em1.find(Product.class, 101L);
    BigDecimal oldPrice = p1.getPrice();

    p1.changePrice(new BigDecimal("249000.00"));

    // 1. Java object đã đổi.
    System.out.println(p1.getPrice());

    // 2. Yêu cầu SQL được đồng bộ nhưng transaction chưa commit.
    em1.flush();

    // 3. Transaction khác đọc dữ liệu.
    tx2.begin();
    Product p2 = em2.find(Product.class, 101L);
    System.out.println(p2.getPrice());
    // Thường vẫn là oldPrice theo isolation không cho dirty read.
    tx2.commit();

    // 4. Transaction 1 xác nhận dữ liệu.
    tx1.commit();

    // 5. Context mới đọc sau commit.
    EntityManager em3 = emf.createEntityManager();
    try {
        Product p3 = em3.find(Product.class, 101L);
        System.out.println(p3.getPrice());
    } finally {
        em3.close();
    }
} catch (RuntimeException ex) {
    if (tx1.isActive()) tx1.rollback();
    if (tx2.isActive()) tx2.rollback();
    throw ex;
} finally {
    em1.close();
    em2.close();
}
~~~

Đây là ví dụ cho **EntityManager quản lý RESOURCE_LOCAL transactions**. Không chạy nguyên xi trong môi trường JTA/container-managed transaction. Tùy isolation/khóa, `em2.find()` có thể đọc phiên bản cũ, bị chặn, chờ timeout hoặc có hành vi đặc thù. Ví dụ nhằm tách **tính thấy được của object trong Java** và **tính thấy được của dữ liệu committed**; nó không khẳng định mọi DBMS luôn trả kết quả giống nhau ở mọi isolation.

### Điều cần quan sát

| Biến/nguồn | Trước T1 commit | Sau T1 commit |
| --- | --- | --- |
| `p1` trong em1 | Giá mới đã gán | Vẫn giữ giá đã gán |
| Hàng trong transaction T1 sau flush | Đã nhận thay đổi chưa commit | Committed |
| `p2` trong context/transaction khác | Theo isolation, thường giá cũ hoặc có thể chờ | Nếu vẫn giữ managed object, không tự refresh |
| `p3` được nạp trong context mới sau commit | Chưa tạo ở thời điểm này | Thường đọc giá mới khi không còn cache/snapshot stale |

Nếu không muốn thao tác ghi giữ row lock trong khi người dùng nhập liệu hoặc hệ thống gọi service khác, hãy thiết kế **transaction ngắn** và tách xử lý lâu dài ra khỏi transaction database khi có thể.

## 27. Các trường hợp phát biểu “đã lưu” dễ gây sai lệch

Trong code review hoặc trao đổi API, câu “đã lưu sản phẩm” có thể có nhiều nghĩa:

| Phát biểu | Có thể thực sự mới xảy ra |
| --- | --- |
| “Đã gọi setter.” | Object Java đổi field |
| “Đã gọi `persist()`.” | Entity chuyển sang managed, đang chờ insert hoặc đã insert sớm |
| “Đã gọi `save()` của repository.” | Hành vi framework/repository cụ thể; transaction có thể chưa commit |
| “Đã gọi `flush()`.” | SQL đã được đồng bộ trong transaction, chưa chắc commit |
| “Có ID rồi.” | ID đã được cấp; không chứng minh row committed |
| “SELECT trong cùng transaction thấy giá mới.” | Có thể nhìn thấy write của chính transaction, chưa có commit |
| “Transaction commit thành công.” | Database đã xác nhận thay đổi trong transaction |
| “Hệ thống khác thấy giá mới.” | Phụ thuộc isolation, context/cache/replica và thời điểm đọc |

Vì vậy nên dùng các từ rõ ràng: **đã thay trong memory**, **đã managed**, **đã flush**, **đã commit**, **đã được transaction khác quan sát**. Chúng không phải các mốc đồng nghĩa.

## 28. Một số tình huống thực tế

### Tình huống A — Getter trả giá mới, query SQL vẫn thấy giá cũ

Ứng dụng gọi `changePrice()` trên entity managed nhưng chưa flush. Getter đọc state Java mới; một câu SQL chạy qua kết nối khác nhìn state committed cũ.

**Giải thích:** hai nguồn đọc ở hai lớp và hai transaction khác nhau. Thiết kế transaction rõ ràng; đừng coi getter là bằng chứng DB đã ghi.

### Tình huống B — Sau `flush()` vẫn chưa thấy dữ liệu ở request khác

T1 đã flush INSERT nhưng chưa commit. Request T2 đọc database theo READ COMMITTED.

**Giải thích:** flush không commit; T2 thông thường không đọc dữ liệu chưa commit của T1.

### Tình huống C — Database đã update nhưng `find()` vẫn thấy giá cũ

Context hiện tại đã nạp `Product#101` từ trước; một transaction khác commit UPDATE.

**Giải thích:** first-level cache giữ managed instance. Cân nhắc `refresh()` hoặc context mới trong ranh giới transaction thích hợp.

### Tình huống D — Bulk UPDATE thành công nhưng entity vẫn cũ

JPQL `UPDATE Product ...` sửa trực tiếp database trong khi context đang giữ Product#101.

**Giải thích:** bulk operation bypass việc cập nhật từng managed object. Đồng bộ pending changes trước bulk và refresh/clear context sau bulk nếu cần.

### Tình huống E — Rollback rồi mà object vẫn in giá mới

Transaction bị rollback sau khi setter gán giá.

**Giải thích:** rollback hủy thay đổi database của transaction, không tự undo phép gán field trên Java object.

### Tình huống F — Persist trả ID nhưng database không có row

Provider cấp ID qua sequence hoặc INSERT trước commit, sau đó transaction rollback.

**Giải thích:** ID allocation và transaction commit là hai sự kiện khác nhau.

### Tình huống G — Trigger sửa mã nhưng object vẫn mã cũ

DB trigger chuẩn hóa SKU thành uppercase khi INSERT.

**Giải thích:** giá trị database-generated không tự xuất hiện trong managed object trừ khi provider hỗ trợ đọc lại hoặc ứng dụng refresh.

### Tình huống H — Inverse collection có phần tử mới nhưng FK không đổi

Ứng dụng chỉ cập nhật collection `mappedBy`, không cập nhật owning side của relationship.

**Giải thích:** object graph trong memory không đồng nhất với trạng thái liên kết mà JPA sử dụng để ghi FK.

### Tình huống I — Hai request cùng sửa giá, request sau mất thay đổi

Hai transaction đọc cùng version cũ, sau đó mỗi bên cập nhật.

**Giải thích:** cần chiến lược concurrency như `@Version` hoặc pessimistic locking theo domain; unique constraint cho ID không ngăn lost update.

## 29. Cách chọn thao tác JPA theo mục tiêu

| Mục tiêu | Thao tác thường phù hợp | Lưu ý |
| --- | --- | --- |
| Sửa thuộc tính của entity đang managed | Gọi phương thức nghiệp vụ / setter | Dirty checking, transaction, flush/commit |
| Chèn entity mới | `persist()` | ID và SQL có thể xuất hiện trước commit |
| Buộc đồng bộ SQL trong transaction | `flush()` | Không commit |
| Kết thúc transaction thành công | `commit()` hoặc boundary framework | Chỉ báo thành công khi commit thực sự thành công |
| Hủy thay đổi SQL chưa commit | `rollback()` | Không tự hoàn nguyên Java object |
| Đọc lại managed entity từ DB | `refresh()` | Có thể mất pending field changes; chịu isolation |
| Ngừng quản lý một entity | `detach(entity)` | Thay đổi sau đó không tự ghi |
| Ngừng quản lý toàn context | `clear()` | Pending changes có thể mất nếu chưa flush |
| Hợp nhất detached state | `merge(detached)` | Dùng instance managed trả về, tránh ghi đè state cũ |
| Cập nhật hàng loạt | JPQL bulk UPDATE/DELETE | Managed entities có thể stale; version rules khác |
| Kiểm soát lost update | `@Version`, locking | Chọn theo mức xung đột và nghiệp vụ |
| Bảo đảm FK/UNIQUE/NOT NULL | Constraint tại DB | Annotation không chứng minh schema vật lý |

### Một phương pháp điều tra lỗi state

Khi phát hiện “giá trong code và trong DB khác nhau”, hãy hỏi theo thứ tự:

1. **Đang so sánh với nguồn nào?** Field Java, managed entity, native SQL trong cùng transaction, transaction khác hay replica?
2. **Entity đang ở trạng thái nào?** New, managed, detached hay removed?
3. **Cùng một persistence context không?** `find` có trả object đã giữ từ trước?
4. **Có transaction không?** Đã bắt đầu, flush, commit hay rollback?
5. **Flush mode nào?** AUTO, COMMIT hay thiết lập provider-specific?
6. **Có bulk JPQL/native SQL/trigger không?** Chúng có thể thay DB mà không thay object.
7. **Có transaction concurrent không?** Isolation, snapshot và lock đang hoạt động ra sao?
8. **Có version/cache không?** `@Version`, second-level/query cache hoặc application cache có ảnh hưởng không?
9. **Ràng buộc DB có được kiểm tra chưa?** Lỗi có thể mới xuất hiện ở flush/commit.
10. **Có yêu cầu đọc lại hay đối soát?** Chọn `refresh`/context mới mà không làm mất pending changes.

Phương pháp này tránh việc xử lý sai kiểu “cứ thêm `flush()` vào mọi chỗ” hoặc “cứ tắt cache” khi chưa tìm đúng lớp gây khác biệt.

## 30. Câu hỏi và bài tập

### Câu 1 — Setter có ghi SQL ngay không?

Trong một transaction, `p = em.find(...); p.changePrice(...)` đã chạy nhưng chưa gọi flush hay commit. Có thể khẳng định database đã UPDATE không?

**Gợi ý:** không. Object đã thay đổi, provider có thể đang theo dõi dirty state, nhưng SQL có thể chưa được đồng bộ.

### Câu 2 — `flush()` có công bố dữ liệu cho mọi request không?

T1 flush UPDATE rồi chưa commit. T2 READ COMMITTED đọc cùng hàng. T2 bắt buộc thấy giá mới không?

**Gợi ý:** không. Flush không commit; isolation thường ngăn dirty read.

### Câu 3 — Vì sao `find()` hai lần trả cùng object?

Trong cùng persistence context, hai lần `em.find(Product.class, 101L)` trả cùng instance. Đây là sự bảo đảm ở lớp nào?

**Gợi ý:** identity map của persistence context/first-level cache, không phải bằng chứng có SELECT hai lần.

### Câu 4 — Rollback có reset object không?

Object Product trong JVM được gán giá 249000; T1 rollback. `product.getPrice()` có bắt buộc trở về 199000 không?

**Gợi ý:** không. Rollback tác động lên transaction database, không tự đảo phép gán Java.

### Câu 5 — Khi nào dùng `refresh()`?

Context hiện tại giữ Product#101 đã nạp; transaction khác vừa commit thay đổi. Muốn đọc lại theo ngữ nghĩa transaction hiện tại, nên xem xét gì?

**Gợi ý:** `refresh()` hoặc context mới; phải quan tâm isolation, pending dirty changes và chi phí SELECT.

### Câu 6 — Vì sao sau JPQL bulk UPDATE object vẫn stale?

`executeUpdate()` báo đã sửa một hàng, nhưng một entity managed tương ứng vẫn hiển thị giá cũ.

**Gợi ý:** bulk update đi thẳng tới DB, không tự đồng bộ field của từng managed object. Cân nhắc flush trước, clear/refresh sau.

### Câu 7 — Có ID tức là INSERT thành công chưa?

Một entity dùng SEQUENCE được cấp ID ngay sau persist nhưng transaction chưa commit.

**Gợi ý:** ID có thể được cấp trước INSERT; kể cả INSERT đã chạy, transaction vẫn có thể rollback.

### Câu 8 — Lỗi UNIQUE xuất hiện lúc nào?

Hai entity mới cùng `sku` được persist trong một transaction. Không lỗi ở lệnh persist đầu. Có thể lỗi khi nào?

**Gợi ý:** khi INSERT được gửi ở flush/commit hoặc sớm hơn nếu IDENTITY/provider cần; phải xử lý trong boundary transaction.

### Câu 9 — `@Version` giải quyết mọi ghi đồng thời không?

Ứng dụng dùng bulk JPQL UPDATE và trực tiếp sửa dữ liệu bằng JDBC bên ngoài JPA. Có thể tin tưởng phiên bản trên managed entity tự bảo vệ mọi thao tác không?

**Gợi ý:** không. Phải thống nhất đường ghi và quy tắc version/locking; bulk SQL có thể bypass optimistic checks per entity.

### Câu 10 — Inverse side có làm database đổi FK không?

Một phòng ban thêm nhân viên vào `employees` có `mappedBy="department"` nhưng không gán `employee.department`.

**Gợi ý:** thay inverse collection không đủ bảo đảm FK đổi; phải sửa owning side.

### Câu 11 — Vì sao cùng SELECT nhưng hai request trả khác nhau?

T1 và T2 có persistence context khác nhau; một transaction đang dùng snapshot cũ, bên khác đã commit mới. Cần xem những lớp nào?

**Gợi ý:** first-level cache, transaction isolation/snapshot, flush/commit và các cache/replica ngoài JPA.

### Câu 12 — Phân biệt bốn mốc

Hãy mô tả ngắn từng mốc: **managed**, **flushed**, **committed**, **observable by another transaction**.

**Gợi ý:** managed là trạng thái JPA theo dõi object; flushed là SQL đã đồng bộ theo transaction; committed là transaction DB hoàn tất; observable phụ thuộc isolation, context/cache và thời điểm đọc của transaction khác.

## Kết luận

**Persistence context quản lý trạng thái entity trong bộ nhớ, còn database quản lý các hàng và transaction; chúng có thể khác nhau một cách hoàn toàn hợp lệ trong nhiều thời điểm.** Khi gọi setter trên managed entity, Java object đổi ngay nhưng SQL có thể chờ flush. Khi flush, database có thể đã nhận thay đổi nhưng vẫn chưa commit. Khi commit thành công, dữ liệu đã được xác nhận, nhưng các managed object trong context khác không tự động refresh, và các transaction có snapshot cũ có thể tiếp tục nhìn giá trị trước đó.

Cần phân biệt rõ tác dụng của `persist`, `flush`, `commit`, `rollback`, `refresh`, `detach`, `clear` và `merge`; đặc biệt chú ý bulk JPQL/native SQL, database default/trigger và optimistic locking vì các cơ chế này có thể làm **state trong JVM** và **state trong DB** lệch nhau nếu ứng dụng không chủ động xử lý.

Quy tắc thực hành quan trọng nhất là **xác định lớp trạng thái đang được quan sát và ranh giới transaction trước khi kết luận dữ liệu đã được lưu, đã được đọc lại hoặc đã nhất quán**. Đó là nền tảng để làm việc an toàn với dirty checking, caching, concurrency và vòng đời entity trong JPA.
