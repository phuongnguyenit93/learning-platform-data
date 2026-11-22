# Xác minh dữ liệu sau khi đồng bộ mà không chỉ đọc từ ngữ cảnh cũ

## 1. Vấn đề: đọc lại entity nhưng chưa chắc đã đọc database

Trong Jakarta Persistence (JPA), sau khi gọi `persist()`, sửa thuộc tính của một entity managed hoặc gọi `flush()`, lập trình viên thường muốn kiểm tra dữ liệu đã được lưu chính xác hay chưa. Một cách kiểm tra dễ nghĩ tới là gọi `EntityManager.find()` ngay sau đó:

```java
Product product = em.find(Product.class, productId);
product.rename("Bàn phím cơ");

em.flush();

Product check = em.find(Product.class, productId);
System.out.println(check.getName()); // "Bàn phím cơ"
```

Nhìn thấy chuỗi mới **không đủ để khẳng định vừa có một lượt đọc mới từ database**. Trong cùng một persistence context, `find()` có thể trả về **chính instance managed** đã được sửa trong bộ nhớ. Câu `SELECT` thứ hai thậm chí có thể không xuất hiện.

Đây là điểm xuất phát của bài học trong chương **Đồng bộ và flush**:

> **Đồng bộ thay đổi qua `flush` và xác minh dữ liệu bằng một lượt đọc thực sự độc lập là hai việc khác nhau.**

Nếu chỉ hỏi lại đối tượng đang được context theo dõi, ta có thể đang xác nhận **giá trị trong bộ nhớ Java**, chứ chưa xác nhận rằng câu SQL đã chạy, trigger đã áp dụng, transaction đã commit, hoặc một client khác có thể đọc kết quả.

Bài này trình bày cách phân biệt các mức xác minh; cách sử dụng `refresh`, `clear`, `detach`, một `EntityManager` mới và truy vấn SQL trực tiếp; cùng những giới hạn do transaction isolation, cache, bulk query và cơ chế đọc từ database gây ra.

## 2. Mô hình tư duy: ba lớp dữ liệu

Xét ba lớp trạng thái liên quan:

```text
                 Java application
            +-------------------------+
            | Entity object đang dùng |
            | product.name = "New"    |
            +-----------+-------------+
                        |
                        | managed bởi EntityManager
                        v
            +-------------------------+
            |  Persistence context    |
            |  identity map / L1 cache|
            |  snapshots / dirty state|
            +-----------+-------------+
                        |
                        | flush => INSERT / UPDATE / DELETE
                        v
            +-------------------------+
            |       Database          |
            | row, FK, trigger,       |
            | default, constraint     |
            +-----------+-------------+
                        |
                        | commit => transaction khác có thể thấy
                        v
            +-------------------------+
            | Lượt đọc độc lập sau    |
            | commit (context mới)    |
            +-------------------------+
```

Ba mệnh đề có thể **khác nhau về thời điểm và kết quả**:

1. **Entity object mang giá trị mới**: đã gọi setter hoặc thao tác Java khác.
2. **Database đã nhận SQL trong transaction hiện tại**: thay đổi đã được flush thành các thao tác cơ sở dữ liệu, nhưng có thể chưa commit.
3. **Một transaction độc lập sau commit thấy kết quả mới**: kết quả đã được xác nhận trong database nguồn và có thể được đọc theo quy tắc isolation/cache tương ứng.

Phương thức `flush()` chủ yếu liên quan mệnh đề 2. Một lượt `find()` trên entity managed trong cùng context chủ yếu có thể xác nhận mệnh đề 1. Để xác nhận mệnh đề 3, cần một **ranh giới transaction và đọc lại đủ độc lập**.

### 2.1. Persistence context là identity map

Trong một persistence context, JPA duy trì tính đồng nhất đối với cùng một entity identity. Ví dụ:

```java
Product first = em.find(Product.class, 7L);
Product second = em.find(Product.class, 7L);

System.out.println(first == second); // true khi tìm thấy entity.
```

Hai biến có thể trỏ tới một Java object. Dù database có hàng `products.id = 7`, lần `find` thứ hai thường không cần SELECT vì context đã quản lý instance này.

`EntityManager.contains(first)` có thể trả về `true`, nhưng cũng chỉ cho biết instance đang managed, **không xác nhận dữ liệu đã commit**.

### 2.2. Flush không phải làm mới trạng thái

`em.flush()` yêu cầu provider đồng bộ các thao tác pending sang database trong phạm vi transaction. Nó **không** làm mới toàn bộ entity graph từ database, không xóa persistence context và không buộc mọi lần `find` tiếp theo phải truy vấn lại SQL.

Tương tự, gọi `em.flush()` sau khi đổi `name` không tự chứng minh rằng giá trị của cột do trigger tính toán đã được phản ánh vào mọi field Java ngay lập tức.

### 2.3. Commit không tự động làm mất context trong mọi cấu hình

Với **application-managed EntityManager** còn mở, persistence context có thể tiếp tục tồn tại qua nhiều transaction. Với **transaction-scoped persistence context** do container/framework quản lý, context thường gắn với transaction; nhưng không nên đồng nhất hai mô hình.

Vì vậy, ngay cả “đã commit rồi gọi `find` trên cùng một `EntityManager`” cũng không phải công thức xác minh bằng một context mới trong mọi trường hợp.

## 3. `flush()` thực hiện những gì?

### 3.1. Đồng bộ pending changes

Các thao tác thường tạo công việc chờ đồng bộ:

```java
em.persist(newProduct);       // Entity mới được quản lý.
managedProduct.changePrice(...); // Dirty checking cho entity managed.
em.remove(oldProduct);        // Entity được đánh dấu xóa.
```

Khi flush, provider có thể phát `INSERT`, `UPDATE`, `DELETE` theo metadata ánh xạ và các quan hệ liên quan:

```java
em.flush();
```

Giả sử không có lỗi, những thao tác đã được gửi đến database trong transaction đang hoạt động theo semantics JPA. **Chưa có nghĩa transaction đã commit**: rollback vẫn có thể hủy các thay đổi đó.

### 3.2. Vì sao `flush` có thể làm lỗi lộ ra sớm?

Các lỗi schema/constraint có thể xuất hiện khi SQL được gửi:

- Cột `NOT NULL` thiếu giá trị.
- Foreign key trỏ tới hàng không tồn tại.
- Unique constraint bị vi phạm.
- Check constraint từ chối số lượng hoặc giá trị không hợp lệ.
- Optimistic locking phát hiện phiên bản đã thay đổi.
- Trigger hoặc function tại database ném lỗi.

Nhưng việc `flush` chạy thành công cũng **không bảo đảm mọi điều kiện của commit thành công**. Constraint deferred có thể chỉ bị kiểm tra tại commit; serialization conflicts, commit-time checks hoặc lỗi kết nối vẫn có thể xuất hiện sau đó.

### 3.3. Khi nào JPA tự flush?

`FlushModeType.AUTO` là lựa chọn mặc định thường dùng. Provider phải đảm bảo ngữ nghĩa phù hợp đối với các query chịu ảnh hưởng bởi những thay đổi pending; nó có thể flush trước một truy vấn. Với `FlushModeType.COMMIT`, tác động của thay đổi chưa flush lên các query trước commit có giới hạn và không nên dựa vào kết quả query để suy ra toàn bộ pending changes đã đồng bộ.

Không nên viết bài kiểm tra dựa vào giả định “JPQL query chắc chắn sẽ flush đúng lúc mình cần” nếu mục tiêu là xác minh thao tác đồng bộ. Trong bài kiểm tra, khi cần kiểm soát điểm đồng bộ, **gọi `em.flush()` tường minh**.

### 3.4. Ví dụ phân biệt flush và commit

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

Product product = em.find(Product.class, 7L);
product.changePrice(new BigDecimal("159000.00"));

em.flush(); // SQL UPDATE có thể đã chạy trong transaction.

System.out.println(em.contains(product)); // true.
System.out.println(product.getPrice());    // 159000.00

tx.rollback(); // Hủy SQL UPDATE chưa commit.
```

Sau rollback, object Java có thể vẫn mang giá mới; không nên tin rằng nó tự quay về giá cũ. Muốn kiểm tra database sau rollback, cần một lượt đọc phù hợp trong context/transaction mới.

## 4. Ví dụ nền tảng: Product và database

Ta dùng entity `Product` để tập trung vào cách đọc lại. Ví dụ sử dụng Jakarta Persistence và `BigDecimal`, không phụ thuộc một framework cụ thể.

### 4.1. Entity

```java
package com.example.shop.domain;

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

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal price;

    @Version
    @Column(name = "row_version", nullable = false)
    private long version;

    protected Product() {
    }

    public Product(String sku, String name, BigDecimal price) {
        this.sku = Objects.requireNonNull(sku);
        this.name = Objects.requireNonNull(name);
        changePrice(price);
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

    public void rename(String nextName) {
        this.name = Objects.requireNonNull(nextName);
    }

    public void changePrice(BigDecimal nextPrice) {
        if (nextPrice == null || nextPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá không được âm");
        }
        this.price = nextPrice;
    }
}
```

### 4.2. Schema tương ứng

Ví dụ PostgreSQL:

```sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL
        CHECK (unit_price >= 0),
    row_version BIGINT NOT NULL
);
```

Giả sử bản ghi `id = 7` có `name = 'Keyboard'` và `unit_price = 120000.00`. Lệnh đổi tên mong muốn:

```sql
UPDATE products
SET name = 'Mechanical Keyboard',
    row_version = row_version + 1
WHERE id = 7
  AND row_version = :previousVersion;
```

Đây là **SQL minh họa semantics version check**, không phải cam kết câu SQL do mọi provider sinh ra. Không tự thay `row_version` bằng SQL như vậy khi JPA đang quản lý entity và bạn không có chủ đích điều phối version.

### 4.3. Cách “kiểm tra” dễ gây hiểu nhầm

```java
Product product = em.find(Product.class, 7L);
product.rename("Mechanical Keyboard");

em.flush();

Product reloaded = em.find(Product.class, 7L);

System.out.println(product == reloaded); // true trong cùng context.
System.out.println(reloaded.getName());   // Giá trị vừa sửa.
```

Kết quả `true` ở phép so sánh tham chiếu chỉ ra đây thường **không phải một lượt tải mới**. Nó không thể dùng như bằng chứng độc lập rằng database trả về chuỗi mới sau một truy vấn SQL.

Cũng không nên chỉ đổi `find` sang `getReference`: một reference managed vẫn thuộc cùng persistence context và có thể không thực hiện SELECT.

## 5. Các mức xác minh và câu hỏi tương ứng

Trước khi chọn kỹ thuật, hãy hỏi **mình cần xác minh điều gì**.

| Mục tiêu | Bước phù hợp | Kết luận có thể đưa ra |
|---|---|---|
| Object đang giữ giá dự kiến? | Đọc getter Java | Chỉ xác minh trạng thái object hiện tại |
| Object có đang managed? | `em.contains(entity)` | Chỉ xác minh quản lý trong context |
| SQL pending đã được đưa đến database trong transaction? | `em.flush()` và xử lý lỗi | Đồng bộ đã được yêu cầu/thực hiện nếu thành công, chưa có commit |
| DB hiện trả về giá gì trong cùng transaction? | `refresh`, clear rồi find, scalar native SQL/JDBC phù hợp | Dữ liệu quan sát theo **transaction hiện tại** |
| Thay đổi đã commit và context khác đọc thấy? | Commit thành công, mở transaction/context mới, tải lại | Xác minh trạng thái đã commit theo isolation/cache |
| Giá trị thực sự tại bảng nguồn, không qua L1/L2 ORM? | SQL scalar/JDBC trên nguồn chính trong transaction đọc phù hợp | Xác minh kết quả SQL database theo mức nhìn thấy |
| Replica hoặc dịch vụ khác đã nhìn thấy? | Đọc từ **đúng** replica/consumer, theo consistency model | Xác minh sự lan truyền tới đối tượng đọc đó |
| Dữ liệu đã bền vững qua sự cố hệ thống? | Cơ chế durability/backup/replication được cấu hình và kiểm thử | Vượt phạm vi chỉ một lần `find` của JPA |

Bài này tập trung bốn mức đầu tiên liên quan JPA và điểm phân biệt quan trọng giữa **đọc trong transaction ghi** và **đọc sau commit ở transaction khác**.

## 6. `EntityManager.refresh()`: yêu cầu đọc lại managed entity

### 6.1. Cách sử dụng

`refresh` yêu cầu provider đồng bộ trạng thái một **managed entity** với dữ liệu trong database, theo phạm vi và cách quản lý của JPA:

```java
Product product = em.find(Product.class, 7L);

product.rename("Mechanical Keyboard");
em.flush();

em.refresh(product);

System.out.println(product.getName());
```

Sau `flush` rồi `refresh`, giá trị của `product` được đọc lại theo tình trạng database **mà transaction hiện tại có thể thấy**. Điều này hữu ích khi database tự tính hoặc chỉnh giá trị.

`refresh` **không tạo một Product mới để trả về**: phương thức trả về `void` và cập nhật trạng thái của managed instance đang dùng.

### 6.2. Vì sao nên flush trước refresh khi muốn xác minh thay đổi?

Nếu trước `refresh` còn pending changes chưa được đồng bộ, refresh có thể **ghi đè thay đổi trong bộ nhớ** bằng giá trị từ database. Vì vậy:

```java
Product product = em.find(Product.class, 7L);
product.rename("New");

// Không nên dùng như một quy trình "lưu rồi kiểm tra" đáng tin:
// em.refresh(product);
// Có thể mất thay đổi rename chưa flush.
```

Nếu ý định là “ghi thay đổi, rồi đọc giá trị database xử lý”, trình tự phù hợp thường là:

```java
product.rename("New");
em.flush();
em.refresh(product);
```

Cần transaction thích hợp, cùng các ràng buộc của `refresh`. Không dùng `refresh` như công cụ sửa tất cả lỗi trạng thái object sau rollback hoặc lỗi flush.

### 6.3. Các giới hạn của refresh

- Đối số phải là entity hợp lệ và đang managed; `refresh` trên detached entity không phải cách gắn lại object.
- Provider đọc lại theo transaction hiện tại; không đồng nghĩa commit thành công.
- Có thể phát sinh SELECT và chi phí tải association tùy fetch plan/cascade `REFRESH`.
- Những giá trị chưa flush có thể bị mất nếu refresh trực tiếp.
- Với optimistic locking, refresh phải tuân thủ quy tắc version/lock của provider và transaction.
- Database bên ngoài có thể sửa cùng hàng ở transaction khác, nhưng transaction hiện tại **không nhất thiết nhìn thấy** những sửa đổi đó do isolation/snapshot.

Nếu chỉ cần kiểm tra vài cột, truy vấn SQL scalar hoặc projection được thiết kế phù hợp có thể ít tốn kém hơn refresh cả entity graph.

## 7. `EntityManager.clear()`: bỏ context cũ trước khi tìm lại

### 7.1. Vì sao clear giúp tránh kết quả từ L1 cache?

`em.clear()` tách tất cả entity đang managed khỏi persistence context. Lần `find` tiếp theo không thể trả về instance cũ từ identity map của context đó.

```java
Product product = em.find(Product.class, 7L);
product.rename("Mechanical Keyboard");

em.flush();
em.clear();

Product fresh = em.find(Product.class, 7L);

System.out.println(product == fresh); // false theo luồng thông thường.
System.out.println(fresh.getName());
```

Đây là cách hữu ích để kiểm tra mapping và trạng thái đã đồng bộ **trong cùng transaction** mà không vô tình đọc lại managed instance cũ.

### 7.2. Hai cảnh báo quan trọng

**Thứ nhất, `clear` không phải `flush`:**

```java
Product product = em.find(Product.class, 7L);
product.rename("New");

em.clear(); // Thay đổi chưa flush có thể bị bỏ.

Product fresh = em.find(Product.class, 7L);
```

Nếu chưa flush, `clear` có thể làm mất pending changes. Khi mục tiêu là xác minh dữ liệu sau đồng bộ, cần `flush` **trước** `clear`.

**Thứ hai, `clear` tách toàn bộ entity** trong context, không chỉ Product được kiểm tra. Mọi reference cũ sẽ không còn được dirty checking theo dõi. Một service dài đang dùng nhiều entity có thể không muốn `clear` giữa chừng.

### 7.3. Clear không bảo đảm bỏ shared cache

`clear` loại bỏ managed instances khỏi **persistence context cấp 1 (L1)**. Nếu JPA provider bật **shared second-level cache (L2)**, lần `find` sau `clear` có thể nhận dữ liệu từ cache chia sẻ thay vì đọc SQL trực tiếp.

Nếu mục tiêu chỉ là **tránh đọc object đang managed cũ**, `clear` đã có tác dụng. Nếu mục tiêu là **xác minh chính hàng database bằng một SELECT thực**, cần cân nhắc bypass L2 hoặc dùng SQL/JDBC và một transaction rõ ràng.

## 8. `detach(entity)`: kiểm tra lại một entity mà không clear mọi thứ

### 8.1. Tách có chọn lọc

`detach` chỉ tách instance được chỉ định khỏi context hiện tại, và có thể tác động thêm theo cascade `DETACH`:

```java
Product product = em.find(Product.class, 7L);
product.rename("Mechanical Keyboard");

em.flush();
em.detach(product);

Product loadedAgain = em.find(Product.class, 7L);

System.out.println(em.contains(product));     // false.
System.out.println(em.contains(loadedAgain)); // true.
```

Lần `find` sau detach không thể trả lại `product` cũ như một managed instance từ L1. Tuy nhiên, shared cache hoặc persistence-provider optimizations vẫn có thể ảnh hưởng việc có SQL đọc mới hay không.

### 8.2. Khi nào detach phù hợp?

- Chỉ muốn loại một entity khỏi context, không làm thay đổi những entity khác.
- Cần so sánh một snapshot detached với một bản được tải lại.
- Không muốn clear toàn bộ context trong use case dài.

Nhưng `detach` không tự flush. Đừng quên đồng bộ pending changes trước khi detach nếu muốn chúng được ghi. Sau detach, sửa object cũ không được context tự theo dõi.

### 8.3. Không gọi `merge` chỉ để “đọc mới”

`merge(detached)` sao chép trạng thái của đối số detached vào managed instance; nó không phải thao tác kiểm chứng giá trị mới nhất từ database. Một detached instance chứa giá trị cũ có thể **ghi đè** trạng thái mới hơn khi merge, tùy version và concurrency controls.

Khi mục tiêu là **đọc lại** chứ không phải **áp dụng thay đổi**, ưu tiên `find` trong context phù hợp, `refresh` với managed instance, hoặc truy vấn đọc rõ nghĩa.

## 9. EntityManager mới sau commit: kiểm tra ranh giới quan trọng nhất

### 9.1. Vì sao một context khác hữu ích?

Một `EntityManager` mới có persistence context cấp 1 khác. Nếu tạo nó **sau khi transaction ghi đã commit**, ta có thể kiểm tra cách một transaction đọc mới quan sát thay đổi.

```text
EntityManager A                       EntityManager B
------------------------------        ------------------------------
begin TX A
find Product #7
modify name
flush SQL UPDATE
commit TX A
close A
                                     create B
                                     begin TX B (nếu cần)
                                     find Product #7
                                     assert database-visible state
                                     end TX B
                                     close B
```

Cách này mạnh hơn việc gọi lại `find` trong context cũ, bởi nó tránh tính đồng nhất của instance managed trước đó.

### 9.2. Ví dụ Java SE đầy đủ

Giả sử có `EntityManagerFactory emf` đã cấu hình persistence unit và Product #7 đang tồn tại:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;

import java.math.BigDecimal;
import java.util.Objects;

public class ProductUpdateVerification {

    public static void updateAndVerify(
            EntityManagerFactory emf, Long id) {

        // Pha 1: ghi và commit.
        EntityManager writer = emf.createEntityManager();
        try {
            writer.getTransaction().begin();

            Product product = writer.find(Product.class, id);
            if (product == null) {
                throw new IllegalArgumentException("Không có Product");
            }

            product.rename("Mechanical Keyboard");
            product.changePrice(new BigDecimal("159000.00"));

            writer.flush(); // Đồng bộ để phát hiện lỗi sớm.
            writer.getTransaction().commit();
        } catch (RuntimeException ex) {
            if (writer.getTransaction().isActive()) {
                writer.getTransaction().rollback();
            }
            throw ex;
        } finally {
            writer.close();
        }

        // Pha 2: đọc độc lập sau commit.
        EntityManager reader = emf.createEntityManager();
        try {
            reader.getTransaction().begin();

            Product reloaded = reader.find(Product.class, id);
            if (reloaded == null) {
                throw new AssertionError(
                    "Product đã biến mất sau commit");
            }

            if (!Objects.equals(
                    "Mechanical Keyboard", reloaded.getName())) {
                throw new AssertionError(
                    "Tên đọc lại không đúng dữ liệu mong đợi");
            }

            if (reloaded.getPrice().compareTo(
                    new BigDecimal("159000.00")) != 0) {
                throw new AssertionError(
                    "Đơn giá đọc lại không đúng");
            }

            reader.getTransaction().commit();
        } catch (RuntimeException ex) {
            if (reader.getTransaction().isActive()) {
                reader.getTransaction().rollback();
            }
            throw ex;
        } finally {
            reader.close();
        }
    }
}
```

Ở pha 1, `flush` giúp phát hiện lỗi sớm, còn **`commit`** mới xác nhận transaction. Ở pha 2, `reader` được tạo sau khi writer đóng và có một context riêng. Ví dụ tạo transaction đọc để ranh giới quan sát rõ ràng trong `RESOURCE_LOCAL`.

**Lưu ý về L2 cache:** một `reader` mới không tự chứng minh nó luôn thực hiện SELECT từ bảng. Nếu provider bật shared cache, dữ liệu có thể được phục vụ qua L2. Để kiểm tra **dữ liệu SQL thật**, có thể thêm chính sách bypass cache hoặc truy vấn scalar/JDBC như phần sau.

### 9.3. Vì sao không chỉ tạo EntityManager mới trước commit?

Một `EntityManager` mới có L1 context khác, nhưng nếu đọc khi writer chưa commit, nó có thể:

- Không thấy thay đổi vì isolation như `READ COMMITTED`.
- Bị chặn bởi lock, tùy DB và truy vấn.
- Nhìn thấy dữ liệu theo snapshot cũ trong một transaction đã bắt đầu trước đó.
- Trong môi trường chia sẻ cùng transaction JTA, nhận một góc nhìn khác với mong đợi “transaction độc lập”.

Vì vậy, nếu mục tiêu là xác minh **một người đọc độc lập thấy dữ liệu sau commit**, phải làm rõ ranh giới giao dịch: **writer commit thành công trước, reader bắt đầu transaction mới sau đó**.

## 10. Bypass shared cache khi cần nhìn database

### 10.1. L1 và L2 là hai cơ chế khác nhau

| Cache | Phạm vi | Tại sao ảnh hưởng xác minh |
|---|---|---|
| L1 / persistence context | Một context | `find` có thể trả cùng managed instance đã đổi |
| L2 / shared cache | Chia sẻ giữa nhiều context, nếu bật | Context mới vẫn có thể nhận dữ liệu cache thay vì SELECT |
| Query cache của provider | Thường là tính năng không chuẩn JPA | Một số query có thể được phục vụ theo cơ chế riêng |
| Cache phía ứng dụng/CDN/replica | Ngoài persistence context | API có thể đọc khác với database nguồn |

`clear()` hoặc `detach()` xử lý L1 theo phạm vi tương ứng. Nó **không tự xóa mọi cấp cache**.

### 10.2. `CacheRetrieveMode.BYPASS`

JPA cung cấp hint chuẩn để yêu cầu bỏ qua retrieval từ shared cache:

```java
import jakarta.persistence.CacheRetrieveMode;

import java.util.Map;

Product product = reader.find(
    Product.class,
    id,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
```

Đoạn này nên chạy trên **context mới hoặc context không đang quản lý Product cùng identity**. Nếu entity đã managed trong L1, một hint bypass L2 không tự biến `find` thành thao tác reload từ database.

`CacheRetrieveMode.BYPASS` chủ yếu điều khiển shared cache; các tính năng query cache hoặc provider extensions có thể yêu cầu cấu hình riêng. Nếu mục tiêu kiểm tra table row bằng SQL, dùng scalar native query/JDBC thường trực tiếp hơn.

### 10.3. Evict cache có phù hợp không?

`EntityManagerFactory.getCache()` cung cấp API quản lý shared cache ở phạm vi phù hợp:

```java
emf.getCache().evict(Product.class, id);
```

Nhưng **evict là hành động thay đổi trạng thái cache dùng chung**, không nên thực hiện bừa bãi chỉ để một bài test chạy qua. Nó có thể ảnh hưởng request khác hoặc che giấu bug cache invalidation thật sự.

Trong môi trường kiểm thử, dùng bypass hint hoặc một truy vấn database riêng thường rõ mục tiêu hơn. Nếu ứng dụng thật gặp stale data do L2, cần xem lại chiến lược cache, invalidation và đường cập nhật ngoài ORM thay vì evict mọi thứ như biện pháp lâu dài.

## 11. Truy vấn SQL trực tiếp để kiểm tra hàng thực tế

### 11.1. Native scalar query trong cùng transaction

Nếu chỉ cần một cột, thay vì yêu cầu JPA trả về một entity managed, có thể dùng native query trả về scalar:

```java
Product product = em.find(Product.class, id);
product.rename("Mechanical Keyboard");

em.flush();

Object dbValue = em.createNativeQuery(
        "SELECT name FROM products WHERE id = ?1"
    )
    .setParameter(1, id)
    .getSingleResult();

System.out.println(dbValue);
```

Vì query trả về giá trị scalar chứ không ánh xạ lại thành entity managed, nó có thể kiểm tra giá trị SQL mà **transaction hiện tại** nhìn thấy, thay vì chỉ đọc `product.getName()`.

Cần vẫn nhớ:

- Đây là **đọc trong transaction hiện tại**, không chứng minh dữ liệu đã commit.
- Một số query provider có thể flush tự động trước truy vấn; vì muốn kiểm soát điểm xác minh, ta đã gọi `flush`.
- SQL native và parameter binding phải phù hợp với database/provider.
- Nếu trigger tác động sau commit hoặc logic ghi async, query này không nhất thiết thấy tác động cuối cùng.

### 11.2. Truy vấn bằng JDBC ở một transaction đọc độc lập

Với yêu cầu xác minh vật lý tại database nguồn, một connection JDBC mới có thể kiểm tra trực tiếp sau writer commit:

```java
import javax.sql.DataSource;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ProductSqlVerifier {

    public static String readProductName(
            DataSource dataSource, long id)
            throws SQLException {

        String sql = "SELECT name FROM products WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, id);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return null;
                }

                return result.getString(1);
            }
        }
    }
}
```

Khi gọi từ một quy trình xác minh, hãy đảm bảo transaction ghi đã **commit**, connection đọc không bị buộc vào transaction ghi cũ, và `DataSource` thực sự trỏ tới **database nguồn cần kiểm tra**.

Không nên tự mở JDBC connection riêng giữa một transaction chưa commit rồi thấy dữ liệu cũ và kết luận ORM không hoạt động. Theo `READ COMMITTED` thông thường, một transaction khác không thấy dữ liệu chưa commit.

### 11.3. JDBC cùng connection với ORM và JDBC connection mới khác nhau

- **Cùng connection/transaction ghi**: có thể thấy thay đổi của chính transaction; vẫn chưa chứng minh commit.
- **Connection mới/transaction mới sau commit**: phù hợp kiểm tra dữ liệu đã được công bố cho reader độc lập.
- **Connection trên replica**: có thể bị replication lag, nên kết quả khác nguồn chính trong một khoảng thời gian.

Khi so sánh, phải nêu rõ đang dùng **connection nào, transaction nào và DB instance nào**. Không dùng khái niệm “query SQL trực tiếp” như một bảo đảm tuyệt đối nếu chưa chỉ ra ngữ cảnh đọc.

## 12. Database trigger, default và cột do server quản lý

Một lý do quan trọng để đọc lại sau flush là database có thể thay đổi dữ liệu **khác với giá trị Java gửi xuống**.

### 12.1. Ví dụ cột được tính bởi trigger

Giả sử bảng `products` có cột `normalized_sku` do database cập nhật từ `sku`:

```sql
ALTER TABLE products
ADD COLUMN normalized_sku VARCHAR(255);
```

Có thể có trigger ở database tự chuẩn hóa giá trị SKU. Entity chỉ đọc cột này:

```java
@Column(
    name = "normalized_sku",
    insertable = false,
    updatable = false
)
private String normalizedSku;

public String getNormalizedSku() {
    return normalizedSku;
}
```

Ví dụ `Product` mới có `sku = "  KEYBOARD-01  "`. Database trigger có thể ghi `normalized_sku = "KEYBOARD-01"` khi INSERT.

Nếu JPA chưa đọc lại giá trị DB tính, `product.getNormalizedSku()` có thể vẫn là `null` sau `persist`/`flush`, dù hàng SQL đã có giá trị do trigger.

Một hướng đọc lại trong **transaction hiện tại**:

```java
em.persist(product);
em.flush();

em.refresh(product);
String normalized = product.getNormalizedSku();
```

Nếu cần xác nhận giá trị **đã commit**, dùng context/SQL đọc mới **sau commit**. Trong một số provider có annotation/hint cho trường generated để tự lấy dữ liệu từ DB; đó là tính năng cần hiểu theo provider, không phải lý do bỏ kiểm tra.

### 12.2. `@Column(insertable=false, updatable=false)` không tự chạy SELECT

Hai thuộc tính `insertable=false` và `updatable=false` hướng dẫn ORM không đưa cột đó vào câu INSERT/UPDATE tương ứng. Chúng **không** tự bảo đảm rằng sau flush Java field đã mang giá trị trigger/default.

Nếu cột được tạo bởi database default, generated column hoặc trigger, cần một cơ chế đọc lại phù hợp khi ứng dụng cần giá trị ngay.

### 12.3. Trigger có thể thay nhiều hàng/bảng

Một trigger INSERT OrderLine có thể cập nhật tổng tiền ở `orders` hoặc ghi một audit row. `flush` trên OrderLine không tự làm managed `Order` trong persistence context trở nên mới nhất:

```java
Order order = em.find(Order.class, orderId);

em.persist(newLine);
em.flush();

// order.getTotal() có thể vẫn giữ snapshot cũ.
```

Có thể `refresh(order)` nếu Order managed và muốn đọc tổng tiền mới trong cùng transaction; hoặc dùng SQL scalar. Để kiểm tra bảng audit sau commit, dùng transaction/context độc lập. Những thay đổi từ DB không đi qua dirty checking của entity đang quản lý có thể làm context mang trạng thái cũ.

### 12.4. Version và trigger không được quản lý tùy tiện song song

Nếu dùng `@Version`, hãy để JPA quản lý version theo metadata của nó. Nếu trigger database cũng tự tăng cùng cột mà ORM không biết, optimistic locking có thể gặp sai lệch.

Khi kết hợp ORM và DB-owned columns, phải quyết định **nguồn quyền ghi** cho từng cột, đồng bộ schema, trigger và mapping. Không sửa version bằng SQL ngoài ORM mà không có chiến lược quản lý nhất quán.

## 13. Xác minh thao tác INSERT, UPDATE và DELETE

Không phải phép xác minh nào cũng giống nhau.

### 13.1. INSERT: ID được cấp không chứng minh commit

```java
Product product = new Product(
    "KB-01",
    "Keyboard",
    new BigDecimal("120000.00")
);

em.persist(product);

Long id = product.getId();
```

Với `IDENTITY`, provider có thể cần INSERT sớm để lấy ID; với `SEQUENCE`, ID có thể được cấp trước khi INSERT hàng. **`id != null` không chứng minh đã commit**.

Một quy trình kiểm chứng INSERT:

1. Tạo entity mới và `persist`.
2. `flush` để đưa pending INSERT/constraint tới database trong transaction.
3. Commit thành công.
4. Mở context/transaction đọc mới.
5. Tìm ID và xác nhận các cột bắt buộc, hoặc đọc scalar bằng SQL trên database nguồn.

### 13.2. UPDATE: getter không chứng minh SQL UPDATE

```java
Product managed = em.find(Product.class, id);
managed.rename("Keyboard V2");

System.out.println(managed.getName()); // "Keyboard V2"
```

Giá trị trên chỉ được gán trong bộ nhớ. Muốn kiểm chứng sau cập nhật, cần flush/commit và đọc mới, hoặc dùng `refresh`/SQL để kiểm tra góc nhìn transaction hiện tại.

Một tình huống đặc biệt: thay một thuộc tính thành **cùng giá trị cũ** có thể không phát SQL UPDATE do dirty checking. Vì vậy, “đã gọi setter” không bảo đảm “phải có SQL UPDATE”.

### 13.3. DELETE: context có thể biết entity removed trước khi database xóa

```java
Product product = em.find(Product.class, id);
em.remove(product);

// Product đang được đánh dấu removed.
// Chưa chắc DELETE đã phát hoặc commit.
```

`EntityManager.contains(product)` với removed state không phải bằng chứng hàng đã bị xóa vật lý. Để kiểm chứng DELETE, commit rồi dùng một context mới:

```java
Product found = reader.find(Product.class, id);
if (found != null) {
    throw new AssertionError("Product vẫn tồn tại sau DELETE");
}
```

Một lượt kiểm tra SQL `SELECT COUNT(*)` trên bảng nguồn sau commit có thể giúp phân biệt cache/provider behavior nếu cần.

### 13.4. Xóa association khác xóa entity

Với `@ManyToMany`, gỡ một phần tử thường xóa **hàng trong join table**, không xóa entity đích. Muốn kiểm tra thao tác đó, hãy đọc **đúng bảng liên kết**, không chỉ kiểm tra `Product` có còn tồn tại hay không.

Với `orphanRemoval=true`, gỡ child có thể dẫn tới DELETE entity con. Bài kiểm tra phải xác định đúng kỳ vọng theo lifecycle mapping: unlink hay delete, và đọc đúng bảng sau commit.

## 14. JPQL bulk UPDATE/DELETE và native SQL: context có thể stale

### 14.1. Bulk update bỏ qua state đồng bộ của từng managed entity

```java
Product product = em.find(Product.class, id);

em.createQuery(
        "update Product p set p.name = :name where p.id = :id"
    )
    .setParameter("name", "Tên được sửa bằng bulk JPQL")
    .setParameter("id", id)
    .executeUpdate();

System.out.println(product.getName());
```

JPQL bulk update làm việc trực tiếp qua query ở database và **không tự sửa mọi managed instance hiện có**. `product.getName()` có thể mang giá trị cũ; `em.contains(product)` vẫn có thể true.

Ngay cả gọi:

```java
Product again = em.find(Product.class, id);
```

cũng có thể trả lại chính `product` cũ từ L1. Đây là một trong những trường hợp cần **`refresh`, `clear` hoặc context mới** để đọc lại.

### 14.2. Bulk DELETE và entity đã tải

```java
Product product = em.find(Product.class, id);

em.createQuery(
        "delete from Product p where p.id = :id"
    )
    .setParameter("id", id)
    .executeUpdate();
```

Đối tượng `product` đang managed có thể vẫn ở persistence context dù hàng database đã bị xóa bởi bulk query. Lần đọc lại trong cùng context có thể gây nhầm. Sau transaction thành công, kiểm tra bằng context mới và, nếu cần, SQL độc lập.

Bulk JPQL thường không áp dụng lifecycle callbacks/cascade REMOVE cho từng entity như `em.remove()`. Vì vậy, khi kiểm tra cần phân biệt **kết quả DML trong database** với **trạng thái object graph trong ORM**.

### 14.3. SQL ngoài JPA còn gây stale mạnh hơn

Nếu một job, trigger, stored procedure hoặc một ứng dụng khác cập nhật bảng mà persistence context đang quản lý, JPA không nhất thiết biết thay đổi đó.

```text
EM1 loads Product#7 name="Old"
          |
External SQL updates Product#7 name="New"
          |
EM1 still has Product#7 name="Old"
          |
EM1.find(Product#7) may return "Old"
```

Đọc mới từ một transaction/context riêng là cách kiểm chứng phù hợp hơn; với transaction isolation có snapshot, context cũ cũng có thể không thấy thay đổi của transaction khác dù đã gọi một SQL SELECT mới.

## 15. Transaction isolation: vì sao một SELECT mới vẫn chưa chắc là “giá trị mới nhất”?

### 15.1. `READ COMMITTED`

Nhiều database dùng isolation `READ COMMITTED` trong các tình huống phổ biến. Một SELECT trong transaction này nhìn thấy dữ liệu đã commit phù hợp với thời điểm truy vấn của nó, cùng những thay đổi của chính transaction.

Ví dụ:

```text
TX A: UPDATE products SET name='New' WHERE id=7
TX A: flush; chưa commit

TX B: SELECT name FROM products WHERE id=7
      thường vẫn thấy 'Old' ở READ COMMITTED

TX A: commit

TX C: SELECT name FROM products WHERE id=7
      có thể thấy 'New' nếu không có cập nhật khác/caches bất thường
```

Vì vậy, mở `EntityManager` mới nhưng **đọc trước khi TX A commit** không kiểm chứng việc thay đổi đã được công bố cho reader khác.

### 15.2. `REPEATABLE READ` và snapshot cũ

Trong nhiều hệ quản trị dùng snapshot isolation hoặc repeatable read, một transaction đọc đã bắt đầu từ trước có thể tiếp tục nhìn thấy snapshot cũ, ngay cả khi transaction ghi khác đã commit.

```text
TX Reader: bắt đầu, snapshot thấy name="Old"
TX Writer: đổi name="New" và commit
TX Reader: chạy SELECT mới nhưng vẫn có thể thấy "Old"
```

Vì thế khi cần xác minh “sau commit một reader mới thấy gì”, nên **bắt đầu transaction đọc sau commit**, không chỉ gọi lại SELECT trong transaction đọc lâu đời.

Các chi tiết phụ thuộc DB, isolation level và câu query. Không có một quy tắc chung “mọi SELECT sau commit luôn thấy giá trị mới” nếu reader còn dùng snapshot cũ hoặc nguồn dữ liệu bị lag.

### 15.3. Uncommitted read không phải mục tiêu kiểm thử thông thường

Một số mức isolation có thể cho phép dirty reads. Nhưng kiểm chứng dữ liệu “đã lưu thành công” thường nên tập trung vào **committed state**, thay vì nhìn thấy một update có thể rollback.

Hãy xác định yêu cầu hệ thống về tính nhất quán và tách bài kiểm tra “flush đã đưa SQL tới DB trong transaction” khỏi bài kiểm tra “commit đã thành công”.

## 16. Khi đọc từ replica, cache bên ngoài hoặc hệ thống khác

Trong kiến trúc có primary database và read replica:

```text
Application write
       |
       v
Primary DB --- commit
       |
       | asynchronous replication
       v
Read replica --- may lag
       |
       v
GET /product/7 (route to replica)
```

Một transaction mới đọc từ primary ngay sau commit có thể thấy dữ liệu mới, trong khi GET endpoint đi qua replica vẫn trả dữ liệu cũ trong một khoảng thời gian.

Khi xác minh, phải chọn **đúng mục tiêu**:

- Kiểm chứng JPA mapping và transaction commit: đọc từ primary.
- Kiểm chứng hành vi API “read your writes”: đọc qua đúng luồng API/routing có chính sách consistency phù hợp.
- Kiểm chứng eventual consistency: dùng cơ chế quan sát/retry có giới hạn, không giả định có kết quả tức thì.

Tương tự, cache cấp ứng dụng, HTTP cache hoặc search index bất đồng bộ có thể chưa được cập nhật ngay. `em.flush()` không điều khiển việc cập nhật một search index hoặc replica ngoài transaction.

Nếu hệ thống có retry xác minh, cần timeout, backoff và tiêu chí thất bại rõ ràng; không dùng vòng lặp chờ vô hạn trong transaction ghi.

## 17. Spring Data JPA: tránh kiểm tra qua repository trong cùng context

### 17.1. `saveAndFlush()` chưa phải commit

Trong Spring Data JPA có:

```java
Product saved = productRepository.saveAndFlush(product);
```

`saveAndFlush` yêu cầu lưu và flush theo semantics repository/JPA, nhưng **không bảo đảm transaction bên ngoài đã commit**. Nếu method đang chạy trong `@Transactional` của service, transaction có thể kết thúc sau khi method service trả về.

Không nên suy ra gọi `saveAndFlush` rồi `findById` trong cùng transaction là phép đọc độc lập.

### 17.2. `findById` có thể sử dụng persistence context đang có

```java
@Transactional
public void updateProduct(Long id) {
    Product product = repository.findById(id).orElseThrow();
    product.rename("New");
    repository.flush();

    Product checked = repository.findById(id).orElseThrow();

    // checked có thể chính là instance managed product.
}
```

Không có gì bảo đảm câu `findById` thứ hai phát một SELECT mới. Nếu muốn kiểm tra đúng database state trong transaction:

```java
@Transactional
public void updateAndCheckInSameTransaction(Long id) {
    Product product = em.find(Product.class, id);
    product.rename("New");

    em.flush();
    em.refresh(product); // DB-visible state của transaction này.

    if (!"New".equals(product.getName())) {
        throw new IllegalStateException("Không đúng kết quả mong đợi");
    }
}
```

Nhưng đây vẫn **chưa phải kiểm tra sau commit từ reader độc lập**.

### 17.3. Hai transaction riêng trong kiểm thử Spring

Một ví dụ không đặt `@Transactional` trên **toàn test method**, dùng `TransactionTemplate` thực hiện transaction ghi rồi transaction đọc:

```java
@SpringBootTest
class ProductPersistenceIT {

    @Autowired
    TransactionTemplate transactionTemplate;

    @PersistenceContext
    EntityManager em;

    @Test
    void updatedValueIsVisibleAfterCommit() {
        Long id = transactionTemplate.execute(status -> {
            Product p = em.find(Product.class, 7L);
            if (p == null) {
                throw new IllegalStateException("Thiếu dữ liệu mẫu");
            }

            p.rename("Mechanical Keyboard");
            em.flush();

            return p.getId();
        });

        // TransactionTemplate đã kết thúc transaction ghi ở trên.
        transactionTemplate.executeWithoutResult(status -> {
            Product actual = em.find(Product.class, id);

            assertNotNull(actual);
            assertEquals("Mechanical Keyboard", actual.getName());
        });
    }
}
```

Cần các import JUnit, Spring Test, transaction và JPA phù hợp; ví dụ giả định Product #7 đã được seed trong database test. Với transaction-scoped persistence context đúng cấu hình, hai lời gọi `TransactionTemplate` tách thành hai transaction và context được quản lý theo ranh giới đó.

Để kiểm chứng mạnh hơn khi có shared cache hoặc Open EntityManager in View, hãy bypass shared cache và/hoặc dùng SQL/JDBC từ một connection đọc mới. Không giả định mọi thiết lập Spring Test đều tự động mở context mới chỉ vì gọi thêm một repository method.

### 17.4. `@DataJpaTest` và rollback mặc định

Nhiều kiểm thử `@DataJpaTest` chạy trong transaction được rollback sau test. Ví dụ:

```java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    TestEntityManager testEntityManager;

    @Autowired
    ProductRepository repository;

    @Test
    void persistenceExample() {
        Product p = new Product(
            "KB-01", "Keyboard",
            new BigDecimal("120000.00")
        );

        testEntityManager.persistAndFlush(p);
        testEntityManager.clear();

        Product reloaded =
            repository.findById(p.getId()).orElseThrow();

        assertEquals("Keyboard", reloaded.getName());
    }
}
```

Bài test này hữu ích để kiểm tra mapping và **đọc lại sau flush trong transaction test**, nhưng không chứng minh rằng dữ liệu còn tồn tại sau một commit thật. Cuối bài test, transaction có thể rollback theo cơ chế của Spring Test.

Khi cần kiểm tra commit thật, hãy tạo ranh giới transaction rõ ràng theo Spring Test utilities hoặc thực hiện integration test có transaction ghi/đọc độc lập. **Đừng gọi assert sau `clear` là “đã xác minh sau commit” nếu transaction chưa commit.**

### 17.5. `@Transactional` và self-invocation

Trong các ứng dụng dùng proxy-based transaction interception, lời gọi từ một method sang method khác **trên chính object `this`** có thể không đi qua Spring proxy. Vì vậy, đặt `@Transactional(propagation=REQUIRES_NEW)` lên một method rồi gọi `this.verify()` không bảo đảm mở transaction mới như mong đợi.

Nếu thiết kế cần một reader transaction độc lập, dùng service/proxy phù hợp hoặc `TransactionTemplate`; đồng thời chú ý transaction ghi phải commit trước khi reader bắt đầu. Không mở reader `REQUIRES_NEW` bên trong writer chưa commit rồi kỳ vọng thấy dữ liệu chưa được commit.

## 18. Kỹ thuật kiểm thử chống “false positive”

Một **false positive** là test báo thành công dù không kiểm chứng được điều nó tuyên bố. Với JPA, có vài mẫu rất thường gặp.

### 18.1. Chỉ assert trên object vừa sửa

```java
product.rename("New");
assertEquals("New", product.getName());
```

Đây là kiểm thử setter/logic Java, **không phải persistence test**.

### 18.2. Flush rồi query trong context cũ

```java
product.rename("New");
em.flush();

assertEquals(
    "New",
    em.find(Product.class, product.getId()).getName()
);
```

Có thể chỉ đang đọc lại cùng managed instance. Nếu mục tiêu kiểm tra mapping/SQL, cần thêm `refresh`, clear/detach hoặc một đường đọc DB độc lập phù hợp.

### 18.3. Clear trước flush

```java
product.rename("New");
em.clear();

Product reloaded = em.find(Product.class, product.getId());
```

Đây là một phép thử khác: nó có thể chứng minh pending changes chưa được lưu và bị bỏ, không phải chứng minh persistence hoạt động đúng. Muốn kiểm tra sau đồng bộ thì **flush trước clear**.

### 18.4. Chỉ kiểm tra ID được tạo

```java
em.persist(product);
assertNotNull(product.getId());
```

Với generator, ID có thể có trước INSERT/commit. Muốn kiểm tra dữ liệu đã được ghi và thấy sau commit, cần đọc từ transaction độc lập.

### 18.5. Test cùng transaction bị rollback

```java
@Test
@Transactional
void myTest() {
    repository.save(product);
    repository.flush();
    // ... assert bằng findById trong cùng transaction ...
}
```

Test có thể đúng về flush và mapping trong transaction, nhưng **không phải bằng chứng dữ liệu đã commit** nếu framework rollback ở cuối.

### 18.6. Dùng cache-bypass hint mà entity vẫn đang managed

```java
Product product = em.find(Product.class, id);

// Dù gọi find với hint bypass L2,
// persistence context vẫn đang giữ product.
```

Bypass shared cache không phải lệnh reset L1. Nếu yêu cầu một đối tượng mới từ SQL, hãy xử lý identity map trước, hoặc dùng `refresh`/SQL scalar.

### 18.7. Đọc từ một replica có độ trễ

Nếu test kiểm tra replica ngay sau commit primary và thất bại, chưa đủ kết luận writer không persist. Cần phân biệt DB source, replication lag và kỳ vọng consistency.

## 19. Chiến lược xác minh theo nhu cầu thực tế

Có thể chọn một trong ba cấp độ sau, theo mức bảo đảm cần thiết.

### Cấp A — Xác minh đồng bộ trong transaction

Mục tiêu: biết thao tác ORM có thể đẩy SQL xuống DB và giá trị DB trong transaction phù hợp.

```java
managedProduct.rename("New");
em.flush();
em.refresh(managedProduct);

assertEquals("New", managedProduct.getName());
```

**Phù hợp:** kiểm thử mapping trigger/default, kiểm thử quy tắc nghiệp vụ khi cần đọc kết quả DB ngay trong transaction. **Không đủ:** chứng minh transaction đã commit và reader mới nhìn thấy.

### Cấp B — Xác minh sau commit bằng context mới

Mục tiêu: chứng minh dữ liệu vừa được commit có thể được đọc từ một persistence context/transaction đọc mới.

```java
writerTx.begin();
managedProduct.rename("New");
writer.flush();
writerTx.commit();

reader = emf.createEntityManager();
readerTx = reader.getTransaction();
readerTx.begin();

Product actual = reader.find(Product.class, id);
assertEquals("New", actual.getName());

readerTx.commit();
```

Đoạn này chỉ minh họa trình tự; mã thực tế cần try/catch/finally để rollback/close đầy đủ. Với L2, cân nhắc bypass retrieval hoặc SQL khi muốn bằng chứng từ bảng nguồn.

**Phù hợp:** integration test cho JPA write/read, xác nhận ranh giới commit.

### Cấp C — Xác minh độc lập ở tầng SQL

Mục tiêu: kiểm tra chính cột trong database nguồn sau commit, tránh các managed entity/cache ORM.

```sql
SELECT id, sku, name, unit_price, row_version
FROM products
WHERE id = :id;
```

Gọi qua JDBC/driver trên connection đọc mới sau commit, hoặc native scalar query với isolation và cache tương ứng.

**Phù hợp:** đối chiếu trigger, constraint, bulk SQL, migration, cache invalidation và vấn đề dữ liệu khó giải thích. **Giới hạn:** vẫn cần biết connection có trỏ tới primary hay replica, có dùng snapshot cũ hay không.

### Bảng lựa chọn

| Vấn đề cần giải quyết | Cách xác minh nên bắt đầu |
|---|---|
| Đã gọi setter nhưng DB không đổi | Kiểm tra managed state/transaction, `flush`, quan sát SQL |
| Giá trị do trigger cập nhật không hiện trên entity | `flush` + `refresh` hoặc SQL scalar |
| `find` trả dữ liệu cũ sau bulk JPQL | `clear` rồi đọc lại, hoặc `refresh`/SQL |
| Muốn biết INSERT đã commit | Commit writer, dùng transaction/context mới tìm lại |
| Muốn biết DELETE xóa đúng hàng | Commit, SELECT/COUNT theo ID từ reader độc lập |
| API GET vẫn thấy cũ sau update | Kiểm tra transaction boundary, L1/L2, cache/API, replica |
| `@DataJpaTest` xanh nhưng production không lưu | Kiểm tra rollback mặc định và ranh giới commit thật |
| Đọc SQL trong TX B không thấy UPDATE TX A chưa commit | Đúng với isolation thông thường; đọc lại sau commit |
| Có lỗi optimistic locking dù getter đúng | Kiểm tra `@Version`, SQL UPDATE và transaction |
| Có lệch dữ liệu giữa ORM và JDBC | So sánh cùng DB, cùng thời điểm, isolation, trigger, cache |

## 20. Một quy trình kiểm tra có hệ thống

Khi cần xác minh dữ liệu sau đồng bộ mà không bị persistence context cũ đánh lừa, đi theo trình tự:

1. **Nêu kỳ vọng cụ thể:** bản ghi nào, cột nào, giá trị nào, bảng entity hay bảng liên kết?
2. **Xác định trạng thái entity:** new, managed, detached hay removed; object nào đang nằm trong context?
3. **Xác định transaction ghi:** có active transaction không, có dùng rollback mặc định hay không?
4. **Đồng bộ tường minh khi cần:** gọi `flush` trước khi muốn đọc kết quả DB trong transaction.
5. **Kiểm tra lỗi:** chú ý constraint, optimistic locking và lỗi hoãn tới commit.
6. **Chọn ranh giới đọc:** trong cùng transaction để kiểm tra flush, hoặc sau commit để kiểm tra committed state.
7. **Tránh L1 của writer:** dùng `refresh`, `clear`/`detach`, hoặc context mới theo mục tiêu.
8. **Nhận diện shared cache:** nếu cần SQL thật, bypass L2 hoặc dùng scalar SQL/JDBC.
9. **Xác định connection và DB instance:** primary, replica hay test DB khác? Có transaction/snapshot cũ không?
10. **Đọc đúng dữ liệu:** so sánh cột được DB tính, foreign key, row count, version, hoặc trạng thái join table.
11. **Đối chiếu kết quả sau commit:** nếu cần bảo đảm cho reader khác, commit xong mới tạo transaction đọc mới.
12. **Giữ test độc lập:** dọn dữ liệu, khôi phục transaction và đóng `EntityManager`/connection phù hợp.

**Không nên dùng một dấu hiệu đơn lẻ** như ID khác null, `contains=true`, getter đúng, hay `flush()` không ném lỗi để kết luận toàn bộ persistence workflow đã thành công.

## 21. Những hiểu lầm thường gặp

| Nhận định | Cách hiểu đúng |
|---|---|
| “`flush()` là commit.” | Flush đồng bộ SQL trong transaction; commit mới hoàn tất transaction. |
| “`find()` ngay sau flush chắc chắn SELECT từ DB.” | Có thể trả cùng managed instance từ L1. |
| “`clear()` luôn an toàn.” | Clear tách tất cả entity và có thể bỏ pending changes chưa flush. |
| “`refresh()` có thể dùng với mọi object detached.” | Refresh yêu cầu managed entity hợp lệ. |
| “`refresh()` không bao giờ mất thay đổi.” | Pending in-memory modifications có thể bị ghi đè. |
| “Tạo `EntityManager` mới chắc chắn không dùng cache.” | L2/shared cache có thể vẫn hoạt động. |
| “Bypass L2 sẽ bỏ qua cả L1.” | Identity map của persistence context vẫn có ưu tiên với entity đã managed. |
| “Có generated ID là đã INSERT và commit.” | ID có thể được cấp trước insert hoặc trước commit. |
| “Commit thành công thì reader đang dùng snapshot cũ phải thấy mới.” | Isolation/snapshot có thể giữ dữ liệu cũ trong transaction đọc. |
| “Native query luôn là phép thử sau commit.” | Native SQL trong writer transaction vẫn chỉ kiểm tra góc nhìn chưa commit. |
| “`@DataJpaTest` có flush nên dữ liệu còn sau test.” | Test transaction thường rollback. |
| “Bulk UPDATE tự cập nhật mọi entity managed.” | Bulk DML có thể làm context stale. |
| “Trigger sửa cột thì JPA field tự cập nhật sau flush.” | Có thể cần refresh/readback hoặc provider-specific generated-field support. |
| “Replica đọc cũ nghĩa là writer không commit.” | Có thể là replication lag hoặc cache. |
| “`contains=true` nghĩa là giá trị DB mới nhất.” | Contains chỉ xác minh trạng thái managed. |
| “Không có exception ở flush nghĩa là sẽ commit thành công.” | Lỗi có thể phát sinh tại commit hoặc do constraint deferred. |
| “Đọc lại API mà thấy đúng thì đủ chứng minh mọi nguồn dữ liệu đồng bộ.” | Cần biết API đang đọc cache, primary, replica hay read model khác. |

## 22. Bài thực hành

### Bài 1 — Chứng minh L1 trả cùng instance

Tạo Product có ID 7. Trong một `EntityManager` và transaction, gọi `find` hai lần. Kiểm tra `first == second` và dùng log SQL quan sát số câu SELECT thực tế.

Sửa tên trên `first` rồi gọi `find` lần thứ ba. Giải thích vì sao nhận tên mới chưa phải bằng chứng có SELECT mới.

### Bài 2 — Phân biệt flush và rollback

Tải Product managed, đổi `unitPrice`, gọi `flush` rồi rollback. Mở một `EntityManager` mới và đọc lại giá.

Giải thích vì sao giá trong object Java sau rollback có thể vẫn là giá mới nhưng database không giữ thay đổi.

### Bài 3 — `refresh` sau khi database tự chuẩn hóa

Thêm cột `normalized_sku` và trigger/default thích hợp trong database thử nghiệm. Persist Product với `sku` chưa chuẩn hóa, flush rồi kiểm tra field read-only trước và sau `refresh`.

Mục tiêu: phân biệt dữ liệu Java gửi xuống với dữ liệu database thực sự lưu.

### Bài 4 — `clear` trước và sau flush

Lần A: sửa entity managed, gọi `clear` trước `flush` rồi tìm lại ID. Lần B: làm lại từ đầu, gọi `flush` trước `clear`.

So sánh kết quả và xác định vì sao clear không phải thao tác ghi.

### Bài 5 — Commit rồi kiểm tra bằng EntityManager mới

Mở writer `EntityManager`, tạo hoặc sửa Product, flush và commit. Đóng writer. Mở reader `EntityManager` mới, bắt đầu transaction đọc, tìm lại Product và so sánh các cột.

Cần kiểm tra đúng cả giá trị tiền `BigDecimal`, không dùng `double` để so sánh chính xác.

### Bài 6 — SQL scalar và JPA entity khác nhau

Trong cùng transaction, sau một bulk JPQL UPDATE, so sánh:

- `managedProduct.getName()`.
- `em.find(Product.class, id).getName()`.
- Native scalar query `SELECT name FROM products WHERE id = ?`.
- Giá trị sau `em.refresh(managedProduct)`.

Giải thích vì sao hai phép đầu có thể stale, trong khi scalar SQL cho thấy trạng thái khác theo transaction.

### Bài 7 — Kiểm tra DELETE và join table

Tạo Student–Course qua bảng `student_courses`. Gỡ Course khỏi collection của Student, flush và commit. Trong transaction mới, kiểm tra hàng liên kết biến mất nhưng Student và Course vẫn tồn tại.

Câu hỏi: vì sao kiểm tra `Course` còn tồn tại không đủ để chứng minh đã gỡ đúng liên kết?

### Bài 8 — Kiểm thử Spring rollback

Tạo một `@DataJpaTest` có `persistAndFlush` và `clear`. Xác nhận query lại trong test thấy bản ghi. Sau đó thiết kế một integration test khác có ranh giới commit thật và transaction đọc mới.

Giải thích hai test chứng minh những điều gì khác nhau.

### Bài 9 — Shared cache

Bật L2 cache trong một môi trường thử nghiệm có kiểm soát. Commit thay đổi bằng một đường cập nhật có thể không thông báo ORM (ví dụ SQL bên ngoài), rồi đọc bằng `EntityManager` mới. So sánh kết quả với retrieval hint `CacheRetrieveMode.BYPASS` và JDBC trực tiếp.

Mục tiêu: tách stale L1, stale L2 và sự thật tại database nguồn.

### Bài 10 — Snapshot và replica

Thiết kế kịch bản có reader transaction bắt đầu trước khi writer commit. Trên database sử dụng snapshot isolation/repeatable read, quan sát reader cũ so với reader mới bắt đầu sau commit.

Nếu môi trường có read replica, thử so sánh primary và replica, ghi nhận độ trễ thay vì kết luận mọi khác biệt là lỗi flush.

## 23. Ghi nhớ cốt lõi

**`flush` đồng bộ các thay đổi của persistence context với database trong transaction, nhưng không đồng nghĩa commit.** Sau flush, gọi `find` hoặc đọc getter của entity đang managed có thể chỉ trả lại đối tượng cũ trong L1 cache, tạo một cảm giác xác minh thành công mà chưa thực sự đọc lại SQL.

Muốn biết **database hiện phản ánh gì trong transaction**, có thể dùng `flush` rồi `refresh`, `clear`/`detach` kết hợp đọc lại, hoặc SQL scalar phù hợp. Muốn biết **dữ liệu đã commit và reader độc lập thấy gì**, hãy commit thành công rồi mở transaction/context đọc mới; nếu yêu cầu nhìn chính hàng vật lý, cân nhắc shared cache và dùng JDBC/SQL trên đúng database nguồn.

Cuối cùng, không có một thao tác duy nhất giải quyết mọi mức xác minh. Hãy nêu rõ **đang kiểm tra in-memory state, flushed state hay committed state**, xác định đúng **persistence context, transaction, isolation và database instance** rồi mới diễn giải kết quả. Đó là cách tránh false positive và chứng minh dữ liệu thực sự được đồng bộ theo đúng yêu cầu.
