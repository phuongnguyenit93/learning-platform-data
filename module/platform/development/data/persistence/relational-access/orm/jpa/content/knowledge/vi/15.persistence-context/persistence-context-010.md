# Xử lý ngữ cảnh sống lâu và dữ liệu có thể đã cũ trong JPA

## 1. Vấn đề: entity trong bộ nhớ có thể khác dữ liệu hiện tại của database

Trong **Jakarta Persistence (JPA)**, ứng dụng làm việc với các đối tượng Java được quản lý bởi `EntityManager`. Khi một entity được tải, JPA đặt nó vào **persistence context** (*ngữ cảnh lưu trữ*) và theo dõi trạng thái của nó. Cách làm này giúp giữ một bản thể đối tượng nhất quán trong một đơn vị công việc và hỗ trợ cơ chế *dirty checking*.

Tuy nhiên, database có thể được cập nhật đồng thời bởi một transaction khác, một ứng dụng khác, một tiến trình chạy nền, một câu lệnh SQL trực tiếp, hoặc một tác vụ batch. Một entity đã được tải từ trước **không tự động biến thành ảnh chụp mới nhất của database** chỉ vì thời gian trôi qua.

Ví dụ:

```text
Thời điểm      Phiên A / EntityManager A          Phiên B / Database
-----------    -------------------------------    ----------------------------
10:00          find(Product, 42)
               -> name = "Sách Java"
               -> entity được quản lý

10:01                                           UPDATE products
                                                SET name = 'Sách Jakarta'
                                                WHERE id = 42;
                                                COMMIT

10:02          find(Product, 42) lần nữa
               -> vẫn có thể nhận cùng object
               -> name = "Sách Java"

10:03          hiển thị dữ liệu cũ
               dù database đã có "Sách Jakarta"
```

Đây là **stale data** — dữ liệu đã cũ trong bộ nhớ so với một phiên bản mới hơn đã được commit vào database.

Rủi ro nghiêm trọng hơn là **lost update**: người dùng dựa trên dữ liệu cũ rồi lưu thay đổi, có thể ghi đè thay đổi hợp lệ của người khác nếu không có cơ chế phát hiện xung đột.

Bài học này làm rõ:

- Vì sao persistence context tồn tại lâu có thể giữ state cũ.
- Cách phân biệt **transaction-scoped** và **extended persistence context**.
- Khi nào dùng `refresh()`, `clear()`, `detach()` hoặc entity manager mới.
- Vì sao `flush()`, `@Transactional` và isolation level không tự giải quyết mọi tình huống.
- Cách dùng **`@Version` và optimistic locking** để tránh cập nhật mất dữ liệu.
- Cách tổ chức workflow dài qua nhiều request mà không giữ một `EntityManager` quá lâu.

## 2. Persistence context làm gì?

### 2.1. Identity map và first-level cache

Một persistence context là tập các entity instance đang được JPA quản lý. Trong cùng persistence context, đối với một entity identity cụ thể, provider duy trì **một managed instance đại diện cho identity đó**.

Giả sử:

```java
Product first = em.find(Product.class, 42L);
Product second = em.find(Product.class, 42L);

System.out.println(first == second); // true, trong cùng context
```

Lệnh `find()` lần hai có thể không gửi câu `SELECT` mới vì entity đã được quản lý. Đây là một biểu hiện của **first-level cache** (*cache cấp một*), gắn với persistence context.

Cơ chế này mang lại các lợi ích:

1. Bảo đảm những phần code trong cùng ngữ cảnh cùng nhìn một managed object cho cùng một entity identity.
2. Cho phép provider phát hiện thay đổi thuộc tính và lập SQL `UPDATE` khi đồng bộ.
3. Tránh nhiều lần tải cùng một entity trong một đơn vị công việc.
4. Duy trì quan hệ giữa các entity được quản lý trong cùng object graph.

Nhưng đó cũng là nguồn của vấn đề **dữ liệu cũ**: một lời gọi `find()` mới **không nhất thiết là một yêu cầu đọc mới từ database**.

### 2.2. Managed entity không phải kết nối SQL “trực tiếp”

Một entity Java được quản lý là **đối tượng trong bộ nhớ**, không phải một con trỏ luôn trỏ vào hàng SQL sống.

```text
Database row                         Persistence context
products.id = 42                     managed Product #42
name = "Sách Jakarta"                name = "Sách Java"
version = 8                          version = 7
```

Khi database thay đổi từ bên ngoài, provider không có nghĩa vụ liên tục quan sát và tự sửa object đang managed. Muốn có dữ liệu mới, ứng dụng phải dùng chiến lược đọc và đồng bộ phù hợp.

### 2.3. Những trạng thái entity cần phân biệt

| Trạng thái | Ý nghĩa | Hệ quả với dữ liệu cũ |
|---|---|---|
| **New/transient** | Object mới, chưa được quản lý/persist. | Không có bản ghi DB tương ứng để tự cập nhật. |
| **Managed** | Object thuộc persistence context, provider theo dõi thay đổi. | Có thể trở nên stale khi DB bị sửa ngoài context. |
| **Detached** | Object có identity nhưng không còn được quản lý trong context đang dùng. | Giá trị chỉ là snapshot cũ; sửa object không tự ghi DB. |
| **Removed** | Entity đã được đánh dấu để xóa. | Không nên xem là dữ liệu dùng để cập nhật thông thường. |

Một entity trở thành detached khi gọi `detach()`, `clear()`, đóng entity manager thích hợp hoặc sau một số thay đổi vòng đời của persistence context. Detached entity **không tự động mới hơn** managed entity; nó chỉ không còn được theo dõi trong context đó.

## 3. Hai khái niệm phải tách biệt: vòng đời transaction và vòng đời persistence context

Một lỗi nhận thức phổ biến là cho rằng **transaction kết thúc thì mọi entity trong bộ nhớ sẽ tự động bị tải lại**. Điều này không đúng với mọi loại persistence context.

### 3.1. Transaction-scoped persistence context

Với **transaction-scoped persistence context**, ngữ cảnh chủ yếu được gắn với phạm vi transaction theo cách JPA/container quản lý. Sau khi transaction kết thúc, các entity đã được quản lý bởi ngữ cảnh đó thường trở thành detached khi context transaction-scoped kết thúc.

Ví dụ điển hình trong Jakarta EE:

```java
@Stateless
public class ProductService {

    @PersistenceContext
    private EntityManager em;

    public Product find(Long id) {
        return em.find(Product.class, id);
    }
}
```

Một injection `@PersistenceContext` không chỉ định type thường có **`PersistenceContextType.TRANSACTION`**. Container cung cấp ngữ cảnh phù hợp với transaction đang chạy; không nên hiểu field `em` là một entity manager vật lý được giữ riêng để cache mọi entity qua mọi request.

Trong một ứng dụng dùng Spring Data JPA, cách thường gặp cũng là xử lý một đơn vị công việc bên trong transaction/service method, nhưng lifecycle thực tế do Spring cấu hình, **không phải mọi hành vi đều đồng nhất với container-managed Jakarta EE**.

### 3.2. Extended persistence context

**Extended persistence context** là ngữ cảnh có thể tồn tại qua **nhiều transaction**. Các entity được tải từ trước vẫn có thể được quản lý trong cùng context sau khi transaction hiện tại kết thúc, cho tới khi vòng đời ngữ cảnh kết thúc hoặc entity bị detach/clear.

Ví dụ trong mô hình Jakarta EE dùng stateful session bean:

```java
@Stateful
public class EditingConversation {

    @PersistenceContext(type = PersistenceContextType.EXTENDED)
    private EntityManager em;

    // Các business method thuộc cùng một conversation.
}
```

Trong source thật, cần import `jakarta.ejb.Stateful`, `jakarta.persistence.PersistenceContext`, `jakarta.persistence.PersistenceContextType` và `jakarta.persistence.EntityManager`.

Ngữ cảnh mở rộng có thể hữu ích cho một **business conversation** dài gồm nhiều bước nhập dữ liệu. Nhưng chính vì giữ entity lâu nên nó dễ giữ lại những giá trị đã trở nên stale.

### 3.3. Application-managed EntityManager cũng có thể sống lâu

Trong Java SE hoặc khi chủ động tạo entity manager:

```java
EntityManager em = emf.createEntityManager();
```

Ngữ cảnh gắn với `em` này tồn tại tới khi entity manager bị đóng hoặc những thao tác quản lý trạng thái làm entity rời ngữ cảnh. Nếu ứng dụng giữ `em` trong một object có vòng đời quá lâu, entity có thể tiếp tục managed qua nhiều transaction/resource-local operation.

Vì vậy, vấn đề stale data không chỉ xảy ra với annotation `EXTENDED`. **Giữ một application-managed `EntityManager` lâu** cũng tạo ra những rủi ro tương tự.

### 3.4. Bảng so sánh

| Khía cạnh | Transaction-scoped context | Extended context / EntityManager tồn tại lâu |
|---|---|---|
| Vòng đời điển hình | Gắn với một đơn vị transaction. | Có thể đi qua nhiều transaction. |
| Entity sau khi một transaction kết thúc | Có thể trở thành detached khi context transaction-scoped chấm dứt. | Có thể vẫn managed nếu context còn sống. |
| Mỗi request có đọc lại DB không? | Tùy mỗi request có context mới, cache cấp hai và isolation. | Không nhất thiết; context có thể trả object cũ. |
| Bộ nhớ | Thường được giải phóng sớm hơn. | Có thể tích lũy nhiều managed entity. |
| Thích hợp | CRUD thông thường, request/service ngắn. | Business conversation được quản lý chặt chẽ. |
| Rủi ro | Detached data, xung đột khi cập nhật, lazy loading sau context. | Stale state, dirty checking ngoài ý muốn, memory growth, xung đột qua nhiều bước. |

**Transaction và persistence context không phải cùng một đối tượng.** Transaction quyết định phạm vi nhất quán và commit/rollback của thay đổi ở database; persistence context quản lý identity và state của các Java entity instance.

## 4. Timeline: vì sao `find()` lần hai vẫn thấy dữ liệu cũ?

Giả sử hai context A và B cùng làm việc với `Product#42`.

```text
               Context A                    Context B / Database
                 |                                |
t0:              | find(Product, 42)              |
                 |   name = "Bút xanh"             |
                 |   version = 3                  |
                 |                                |
t1:              |                                | BEGIN
                 |                                | find(Product, 42)
                 |                                | setName("Bút đỏ")
                 |                                | COMMIT
                 |                                | name = "Bút đỏ"
                 |                                | version = 4
                 |                                |
t2:              | find(Product, 42)              |
                 | trả lại cùng managed object    |
                 | name = "Bút xanh"               |
                 | version = 3                    |
                 |                                |
t3:              | refresh(product)               |
                 | name = "Bút đỏ"                 |
                 | version = 4                    |
                 v                                v
```

Nếu `Context A` có `Product#42` managed, lời gọi `find` không nhất thiết query lại database. JPA bảo toàn identity của object trong context; một truy vấn JPQL trả về entity cùng identity cũng thường sử dụng managed instance đã có thay vì âm thầm ghi đè mọi field của nó.

### 4.1. Đừng nhầm `find()` với “SELECT mới nhất”

```java
Product p1 = em.find(Product.class, 42L);

// Một transaction khác đã commit thay đổi tên.

Product p2 = em.find(Product.class, 42L);
System.out.println(p1 == p2); // true nếu vẫn trong cùng context
```

Vì `p1` và `p2` cùng object, chúng có cùng state trong bộ nhớ. Điều này đúng ngay cả khi lệnh thứ hai nằm ở một business step khác dùng **cùng extended context**.

### 4.2. Tại sao truy vấn JPQL cũng chưa đủ?

```java
Product product = em.createQuery(
    "SELECT p FROM Product p WHERE p.id = :id",
    Product.class
)
.setParameter("id", 42L)
.getSingleResult();
```

Ngay cả nếu provider thực thi SQL để xác định hàng, khi trả về entity identity đã managed trong context, kết quả vẫn liên quan đến **managed instance hiện có**. Không nên coi việc chạy một JPQL query như một lời hứa rằng provider sẽ ghi đè mọi state stale trên entity đã quản lý.

Nếu ứng dụng **cần đồng bộ lại entity từ database**, hãy chọn rõ `refresh()` hoặc tạo một ngữ cảnh mới theo yêu cầu nhất quán.

## 5. Stale read và lost update là hai vấn đề khác nhau

### 5.1. Stale read: hiển thị dữ liệu đã cũ

Người dùng mở trang sửa sản phẩm lúc 09:00:

```text
price = 100000
version = 7
```

09:05, nhân viên khác sửa giá thành `120000` và commit. Nếu người dùng thứ nhất tiếp tục đọc entity đã nằm trong extended context, họ có thể vẫn thấy `100000`.

Đây là **stale read**, ảnh hưởng tới thông tin hiển thị, báo cáo hoặc quyết định nghiệp vụ.

### 5.2. Lost update: ghi đè thay đổi của người khác

Hai người dùng đọc cùng bản ghi ban đầu:

```text
Database: name="Sách A", price=100000

User 1 đọc: name="Sách A", price=100000
User 2 đọc: name="Sách A", price=100000

User 2 sửa price=120000, COMMIT.

User 1 sửa name="Sách B" trên form cũ,
gửi lại cả name="Sách B" và price=100000.
```

Nếu service lưu toàn bộ form mà không có cơ chế kiểm soát xung đột, giá `120000` có thể bị ghi đè thành `100000`. Đó là **lost update**.

Trong thực tế, JPA provider có thể chỉ cập nhật những cột được phát hiện đã thay đổi, nhưng **không nên dựa vào kiểu SQL UPDATE của một provider để bảo vệ nghiệp vụ trước mọi lost update**. Cách bảo vệ chuẩn là **optimistic locking bằng `@Version`**, hoặc một cơ chế concurrency control được thiết kế tương đương.

### 5.3. Không có stale read vẫn có thể mất cập nhật

Ngay cả khi mỗi request tạo entity manager mới, một form đã mở trong browser 20 phút vẫn chứa **dữ liệu cũ ở phía client**. Nếu API nhận form đó rồi ghi đè database mà không kiểm tra version, lost update vẫn xảy ra.

Vì thế cần phân biệt:

- **Freshness:** khi đọc, có đang quan sát dữ liệu hợp lý mới nhất không?
- **Concurrency safety:** khi ghi, có ngăn thay đổi dựa trên phiên bản lỗi thời ghi đè người khác không?

`refresh()` giúp giải quyết một số tình huống **freshness**. `@Version` giúp phát hiện nhiều tình huống **concurrent modification**. Hai cơ chế bổ sung nhau.

## 6. Ví dụ entity có `@Version`

Để trình bày rõ, dùng entity `Product`:

```java
package com.example.catalog;

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

    @Column(name = "name", nullable = false, length = 150)
    private String name;

    @Column(name = "price", nullable = false,
            precision = 15, scale = 2)
    private BigDecimal price;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    protected Product() {
        // Constructor không tham số cho JPA.
    }

    public Product(String name, BigDecimal price) {
        rename(name);
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

    public Long getVersion() {
        return version;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không được trống");
        }
        this.name = newName.trim();
    }

    public void changePrice(BigDecimal newPrice) {
        Objects.requireNonNull(newPrice, "newPrice");
        if (newPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá không được âm");
        }
        this.price = newPrice;
    }
}
```

`@Version` khai báo thuộc tính **phiên bản của entity**. JPA provider quản lý giá trị này để hỗ trợ **optimistic locking**: khi cập nhật, nó có thể kiểm tra rằng phiên bản tại database vẫn khớp với phiên bản mà entity đang sử dụng.

Một DDL minh họa:

```sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    price DECIMAL(15, 2) NOT NULL,
    row_version BIGINT NOT NULL
);
```

Giá trị ban đầu và cách tăng version phụ thuộc provider/chiến lược lưu, nên không nên mặc định mọi provider bắt đầu bằng 0 hay 1 trong tất cả tình huống. **Ứng dụng không tự tăng `version` trong setter**; provider chịu trách nhiệm theo dõi và thay đổi.

Một phiên bản `Long` là lựa chọn thường gặp; JPA hỗ trợ một tập kiểu dữ liệu thích hợp cho version theo đặc tả. Đặt **một version attribute** ở vị trí mapping nhất quán trong entity hierarchy.

## 7. `EntityManager.refresh()`: tải lại state cho entity managed

### 7.1. `refresh()` làm gì?

Khi entity đang **managed**, `refresh(entity)` yêu cầu provider lấy state hiện có từ nguồn persistence và thay thế state của entity theo mapping:

```java
Product product = em.find(Product.class, 42L);

// Dữ liệu có thể đã bị thay đổi từ transaction khác.

em.refresh(product);
System.out.println(product.getName());
```

Sau refresh thành công, các thuộc tính được làm mới theo state provider đọc được, bao gồm giá trị version nếu mapping đó áp dụng. **Đối tượng `product` vẫn là managed instance trong cùng context**; ta không cần thay tham chiếu Java.

### 7.2. `refresh()` có thể làm mất thay đổi chưa lưu

Đây là rủi ro quan trọng nhất:

```java
Product product = em.find(Product.class, 42L);

product.rename("Tên người dùng vừa sửa");

// Nếu chưa flush/commit, việc refresh có thể ghi đè
// state đang sửa bằng state lấy từ database:
em.refresh(product);
```

Nếu state ở database vẫn là `"Tên cũ"`, thao tác refresh có thể khiến tên vừa sửa trong bộ nhớ bị mất. Đó là lý do **không gọi `refresh()` như một thói quen trước mọi lần đọc**.

Trước khi refresh cần quyết định:

1. Entity có đang chứa thay đổi người dùng chưa muốn bỏ không?
2. Có cần lưu, hủy hay đối chiếu những thay đổi đó?
3. Transaction hiện tại có cho phép thấy version mới đã commit hay không?
4. Có đang muốn làm mới toàn bộ entity hay chỉ cần đọc một giá trị riêng?

`refresh()` thường phù hợp khi ứng dụng **chủ động muốn bỏ state hiện có và lấy lại state từ database**, ví dụ ngay trước khi hiển thị một trang kiểm tra mới, hoặc sau khi một thao tác ngoài JPA đã cập nhật dữ liệu mà không cần giữ thay đổi chưa flush.

### 7.3. `refresh()` không dành cho detached entity

```java
Product detached = ...; // Không thuộc context hiện tại.
em.refresh(detached);   // Không phải cách sử dụng hợp lệ.
```

JPA yêu cầu entity được refresh phải là entity **managed** trong context thích hợp; gọi trên object detached có thể ném `IllegalArgumentException`.

Nếu object detached chỉ dùng để hiển thị, cách đơn giản hơn thường là **mở entity manager mới, `find` entity theo ID, rồi tạo DTO mới**. Đừng vội `merge` chỉ để đọc dữ liệu.

### 7.4. `refresh()` chịu ảnh hưởng của transaction isolation

Ngay cả khi gọi refresh, **dữ liệu quan sát được còn phụ thuộc transaction isolation**. Ví dụ transaction đang ở mức repeatable-read/snapshot isolation có thể tiếp tục nhìn snapshot cũ khi đọc lại, tùy database và cơ chế MVCC.

Vì vậy:

> `refresh()` yêu cầu provider làm mới từ persistence store theo transaction hiện tại; nó **không phải nút “bỏ qua mọi isolation và đọc trạng thái toàn cục mới nhất”**.

Nếu mục tiêu là quan sát các commit từ transaction khác, một chiến lược hữu ích là kết thúc transaction đọc cũ rồi mở transaction/ngữ cảnh mới theo isolation phù hợp.

### 7.5. Ví dụ đọc lại với transaction resource-local

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    try {
        Product product = em.find(Product.class, productId);

        // Chỉ gọi khi đã quyết định có thể bỏ state local
        // hoặc cần đồng bộ rõ ràng từ database.
        em.refresh(product);

        System.out.println(product.getName());
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
} finally {
    em.close();
}
```

Dùng transaction giúp thể hiện ranh giới nhất quán rõ ràng. Tùy loại entity manager, kiểu transaction, lock mode và provider, một số thao tác đọc có thể được cho phép ngoài transaction; đừng suy luận từ ví dụ rằng mọi ứng dụng JPA đều bắt buộc begin transaction chỉ để gọi `find()`.

## 8. `clear()`, `detach()` và `close()`: bỏ state khỏi context

Không phải lúc nào cũng cần `refresh()`. Đôi khi cách tốt nhất là **ngừng quản lý object cũ** và dùng một context mới.

### 8.1. `clear()` — detach tất cả entity trong context

```java
Product oldProduct = em.find(Product.class, 42L);

// Không còn muốn giữ managed state cũ:
em.clear();

// Một lần tìm sau có thể tạo managed instance mới:
Product reloaded = em.find(Product.class, 42L);
```

`clear()` detach **toàn bộ managed entity** hiện có trong context và loại bỏ các thay đổi chưa đồng bộ đang chờ trong context. Nếu đang có chỉnh sửa chưa flush, chúng có thể bị mất.

Lưu ý:

- `oldProduct` không bị xóa khỏi bộ nhớ Java ngay lập tức; nó chỉ không còn managed.
- `oldProduct` vẫn chứa state cũ nếu code giữ tham chiếu đến nó.
- `reloaded` không nhất thiết cùng object với `oldProduct`.
- `clear()` **không xóa dữ liệu SQL** và **không commit transaction**.
- `clear()` không có nghĩa tự vô hiệu hóa shared second-level cache của provider.

### 8.2. `detach(entity)` — chỉ detach một entity

```java
Product oldProduct = em.find(Product.class, 42L);

em.detach(oldProduct);

Product reloaded = em.find(Product.class, 42L);
```

`detach` chỉ yêu cầu tách entity được chỉ định khỏi context; tác động tới quan hệ có cascade `DETACH` còn phụ thuộc mapping. Dùng khi chỉ một managed entity cần được bỏ khỏi context, thay vì làm mất state quản lý của tất cả entity khác.

Giống `clear()`, detach một entity có thay đổi chưa flush có thể khiến các thay đổi đó không được ghi xuống database.

### 8.3. `close()` — kết thúc EntityManager do ứng dụng quản lý

```java
EntityManager em = emf.createEntityManager();

try {
    // Một đơn vị công việc ngắn.
} finally {
    em.close();
}
```

Đóng application-managed entity manager là cách dọn tài nguyên rõ ràng. Sau khi đóng, không được tiếp tục sử dụng entity manager như một context đang hoạt động; các entity đã trả ra không còn được tự theo dõi bởi context đó.

Với container-managed `EntityManager` được inject bởi `@PersistenceContext`, ứng dụng **không tự đóng injected entity manager**; container quản lý vòng đời. Cần phân biệt hai trường hợp để tránh lỗi lifecycle.

### 8.4. Bảng lựa chọn nhanh

| Thao tác | Tác dụng chính | Khi phù hợp | Cảnh báo |
|---|---|---|---|
| `em.refresh(entity)` | Làm mới state của **một managed entity** từ persistence store. | Cần reload entity và đồng ý bỏ state local chưa lưu. | Có thể ghi đè thay đổi đang sửa. |
| `em.detach(entity)` | Đưa một entity ra khỏi context. | Không muốn tiếp tục quản lý entity đó. | Thay đổi chưa flush có thể bị mất; object vẫn cũ. |
| `em.clear()` | Detach tất cả managed entity. | Kết thúc một khối xử lý hoặc sau bulk update. | Mất pending changes chưa flush; không xóa L2 cache. |
| `em.close()` | Kết thúc application-managed EntityManager. | Sau đơn vị công việc; ngăn giữ context quá lâu. | Không dùng với container-managed injected EntityManager. |
| Tạo `EntityManager` mới | Tạo một persistence context mới. | Request mới cần snapshot phù hợp; giảm stale L1. | L2 cache và isolation vẫn cần được xét. |
| `em.flush()` | Đồng bộ thay đổi **từ context xuống DB** trong transaction. | Muốn SQL pending được thực hiện, phát hiện lỗi sớm. | Không phải thao tác refresh; không tự commit. |

## 9. `flush()` không phải giải pháp làm mới dữ liệu

`flush()` và `refresh()` đi theo hai hướng khác nhau:

```text
                Persistence context
                  managed Product
                      /     \
                     /       \
                flush()    refresh()
                   |           ^
                   v           |
                  Database / Persistence store
```

- **`flush()`**: đồng bộ các thay đổi của context xuống database, thường trong transaction đang hoạt động.
- **`refresh()`**: lấy state từ persistence store để cập nhật managed entity.

Nếu `Product` đang stale, gọi `flush()` không bảo đảm làm nó tươi mới. Trái lại, nếu entity đã bị chỉnh sửa, flush có thể ghi **state cũ hoặc các giá trị dựa trên state cũ** xuống database. Vì vậy cần cơ chế version/locking.

### 9.1. `FlushModeType.AUTO` và `COMMIT`

```java
em.setFlushMode(FlushModeType.COMMIT);
```

Flush mode ảnh hưởng **thời điểm provider đồng bộ các thay đổi đang chờ**:

- `AUTO`: provider bảo đảm cách thực thi phù hợp semantics truy vấn và flush theo các thời điểm cần thiết.
- `COMMIT`: ưu tiên đồng bộ khi commit; ảnh hưởng của thay đổi chưa flush tới một số query có thể không xác định theo các quy tắc JPA.

**Flush mode không kiểm soát độ mới của managed entity.** Đổi sang `COMMIT` không phải cách xử lý stale read và không thay thế optimistic locking.

### 9.2. Transaction đã commit không đồng nghĩa context đã trống

Với extended context, sau commit, những entity đã managed có thể **vẫn nằm trong context**. Nếu transaction khác thay database sau đó, các entity này có thể trở thành stale dù transaction trước đã commit thành công.

Đây là lý do phải quan sát cả **vòng đời của context**, không chỉ kiểm tra code đã gọi `commit()` hay chưa.

## 10. Ví dụ tái hiện stale state giữa hai EntityManager

Đoạn mã sau mô tả một tình huống có **hai application-managed EntityManager** truy cập cùng bản ghi. Giả sử đã có `Product` với khóa `productId` và `name = "Bút xanh"`.

```java
EntityManager longLived = emf.createEntityManager();
EntityManager writer = emf.createEntityManager();

try {
    // Context A tải Product#id.
    Product held = longLived.find(Product.class, productId);
    String oldName = held.getName();

    // Context B sửa bản ghi rồi commit.
    EntityTransaction tx = writer.getTransaction();

    try {
        tx.begin();
        Product changing = writer.find(Product.class, productId);
        changing.rename("Bút đỏ");
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }

    // Context A vẫn quản lý cùng object đã tải:
    Product same = longLived.find(Product.class, productId);

    System.out.println(held == same);          // true
    System.out.println(same.getName());         // Có thể vẫn là "Bút xanh".

    // Chủ động làm mới; không có thay đổi local cần giữ.
    EntityTransaction readTx = longLived.getTransaction();
    try {
        readTx.begin();
        longLived.refresh(held);
        readTx.commit();
    } catch (RuntimeException ex) {
        if (readTx.isActive()) {
            readTx.rollback();
        }
        throw ex;
    }

    System.out.println(held.getName());         // "Bút đỏ" theo ví dụ.
} finally {
    writer.close();
    longLived.close();
}
```

**Giả định của ví dụ:** chỉ có writer thay đổi bản ghi, transaction đầu đã commit thành công, và transaction refresh nhìn thấy commit đó theo isolation của database. `@Version` trên `Product` giúp bảo vệ các bản cập nhật xung đột; trong ví dụ này context A chưa sửa entity trước khi refresh.

Kết luận từ ví dụ không phải “cứ refresh sau mỗi find”. Kết luận là: **context A có quyền giữ state cũ cho tới khi ứng dụng quyết định đồng bộ hoặc kết thúc nó**.

### 10.1. Tại sao không nên giữ `longLived` trong singleton?

`EntityManager` và persistence context không được thiết kế làm kho lưu trữ entity chung cho mọi request/thread. `EntityManager` **không an toàn cho truy cập đồng thời giữa các thread**. Giữ nó trong singleton hoặc biến static có thể gây:

- Trộn state của nhiều request/người dùng.
- Tranh chấp và race condition.
- Dữ liệu stale kéo dài.
- Rò rỉ bộ nhớ do rất nhiều managed entity được giữ.
- Transaction lifecycle khó kiểm soát.
- Ngoại lệ và state lỗi của context lan sang request khác.

Một `EntityManagerFactory` thường được chia sẻ và quản lý dài hạn; **`EntityManager` nên có phạm vi sử dụng được kiểm soát**.

## 11. Extended persistence context dùng cho một business conversation

### 11.1. Lợi ích và đánh đổi

Một wizard nhập hồ sơ dài có thể có các bước:

```text
Bước 1: mở hồ sơ khách hàng
Bước 2: sửa tên
Bước 3: sửa thông tin liên hệ
Bước 4: xem lại
Bước 5: xác nhận lưu
```

Nếu cùng extended persistence context được giữ qua các bước, entity có thể vẫn managed và các thay đổi tích lũy trong bộ nhớ. Điều này đơn giản hóa một số trường hợp object graph phức tạp nhưng mang thêm rủi ro:

- Người khác có thể sửa dữ liệu giữa bước 1 và bước 5.
- Những thay đổi tạm thời có thể bị flush ngoài ý muốn nếu context tham gia transaction.
- Bộ nhớ sống lâu và lifecycle cần được dọn khi người dùng hủy hoặc phiên làm việc hết hạn.
- Có nguy cơ cùng một conversation bị truy cập đồng thời qua nhiều tab/request.

**Extended persistence context không có nghĩa là một transaction SQL được mở suốt toàn bộ wizard.** Giữ transaction qua thời gian người dùng suy nghĩ sẽ tăng lock time, tài nguyên database và rủi ro timeout.

### 11.2. Phác thảo Jakarta EE với stateful session bean

Trong Jakarta EE, một trường hợp hỗ trợ extended context điển hình là **stateful session bean**:

```java
import jakarta.ejb.Stateful;
import jakarta.ejb.Remove;
import jakarta.ejb.TransactionAttribute;
import jakarta.ejb.TransactionAttributeType;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;
import jakarta.persistence.SynchronizationType;

@Stateful
public class ProfileWizard {

    @PersistenceContext(
        type = PersistenceContextType.EXTENDED,
        synchronization = SynchronizationType.UNSYNCHRONIZED
    )
    private EntityManager em;

    private CustomerProfile profile;

    @TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
    public void open(Long id) {
        profile = em.find(CustomerProfile.class, id);
    }

    @TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
    public void changeDisplayName(String newName) {
        if (profile == null) {
            throw new IllegalStateException("Chưa mở hồ sơ");
        }
        profile.changeDisplayName(newName);
    }

    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public void save() {
        if (profile == null) {
            throw new IllegalStateException("Chưa mở hồ sơ");
        }

        em.joinTransaction();
        em.flush();
    }

    @Remove
    @TransactionAttribute(TransactionAttributeType.NOT_SUPPORTED)
    public void finish() {
        // Container kết thúc lifecycle của stateful bean.
    }
}
```

Đây là **minh họa về các annotation và vòng đời**, giả định `CustomerProfile` là một entity có `@Id`, `@Version` và phương thức `changeDisplayName` phù hợp, được đăng ký trong persistence unit.

Ý nghĩa:

- `PersistenceContextType.EXTENDED`: context tồn tại theo lifecycle của stateful bean, thay vì chỉ một transaction.
- `SynchronizationType.UNSYNCHRONIZED`: context không tự tham gia mọi transaction đang chạy; ứng dụng chủ động gọi `joinTransaction()` khi muốn đồng bộ.
- `NOT_SUPPORTED`: các bước mở/sửa draft không chạy trong transaction container-managed.
- `REQUIRED`: bước lưu chạy trong transaction; provider có thể flush thay đổi của managed entities sau khi join.
- `@Remove`: kết thúc conversation/stateful bean khi không còn cần giữ context.

**Lưu ý quan trọng:** Một unsynchronized context đã tham gia transaction có những quy tắc liên kết với transaction tiếp theo do Jakarta Persistence/container quy định; không coi nó là “nút bật/tắt ghi dữ liệu” tùy ý. Trong dự án thật, thiết kế lifecycle, cách xử lý lỗi commit, timeout, passivation, retry và quyền truy cập phải bám theo container đang sử dụng.

Nếu có nhiều thay đổi khác nhau trong wizard, gọi `save()` thất bại vì optimistic locking cần được xử lý bằng **đọc lại và giải quyết conflict**, không tự động ghi đè lên phiên bản mới của database.

### 11.3. Khi nào không nên dùng extended context?

Với hầu hết ứng dụng REST/stateless CRUD:

- Request được xử lý nhanh.
- UI gửi DTO/command.
- Service mở transaction ngắn.
- Repository tìm entity trong context mới.
- Service cập nhật đúng các field cần thay đổi.
- Commit và kết thúc ngữ cảnh.

Cách này thường đơn giản và an toàn hơn là giữ một extended context cho mỗi phiên người dùng.

Nếu một form kéo dài vài phút, **lưu draft DTO ở client/session** (hoặc một bản nháp riêng có version) là lựa chọn phổ biến. Không cần giữ hàng trăm entity managed chỉ vì người dùng chưa nhấn “Lưu”.

## 12. Kiểm soát cập nhật đồng thời với `@Version`

### 12.1. Optimistic locking giải quyết điều gì?

Optimistic locking giả định phần lớn transaction không xung đột; thay vì giữ khóa database lâu, nó phát hiện nếu phiên bản dữ liệu đã thay đổi trước khi cập nhật.

Với `Product`:

```text
Database: id=42, name="Bút xanh", row_version=5

Context A tải: version=5
Context B tải: version=5

B sửa name="Bút đỏ"
B commit -> database version=6

A sửa price dựa trên state version=5
A commit -> phát hiện version không còn là 5
          -> OptimisticLockException / rollback
```

Một SQL minh họa provider có thể dùng:

```sql
UPDATE products
SET name = ?, price = ?, row_version = 6
WHERE id = 42 AND row_version = 5;
```

Nếu không có hàng nào còn `id = 42 AND row_version = 5`, câu cập nhật có thể không cập nhật hàng nào; provider phát hiện xung đột và báo lỗi optimistic lock. SQL thực tế có thể khác về cách tăng version, trường được cập nhật và thời điểm phát hiện.

**Optimistic locking không tự merge những thay đổi của hai người dùng.** Nó **phát hiện xung đột** để ứng dụng lựa chọn cách xử lý an toàn.

### 12.2. `OptimisticLockException` có thể xuất hiện khi nào?

Lỗi optimistic locking có thể xuất hiện khi:

- Gọi `em.flush()`.
- Gọi `tx.commit()`.
- Thực hiện `merge()` trên detached entity có version đã cũ, tùy provider/thời điểm kiểm tra.
- Một thao tác lock/read yêu cầu kiểm tra version.

Không nên bọc chỉ `persist()` hoặc chỉ một dòng setter và cho rằng mọi xung đột sẽ được bắt ở đó. Ở transaction-boundary, exception có thể bị bọc bởi exception của transaction/provider.

Sau một conflict, transaction thường đã rollback hoặc không còn an toàn để tiếp tục. Nên **kết thúc đơn vị công việc hiện tại và mở context/transaction mới** để lấy state mới và hướng dẫn người dùng giải quyết xung đột.

### 12.3. Không tự sửa version bằng tay

```java
// Sai về nguyên tắc:
product.setVersion(product.getVersion() + 1);
```

JPA provider sở hữu việc quản lý `@Version`. Ứng dụng chỉ nên xem giá trị version như **token nhận biết phiên bản**, không thay nó để “vượt qua” kiểm tra xung đột.

Với hệ thống không thể dùng `@Version`, có thể cân nhắc các hình thức concurrency control khác, nhưng chúng cần được thiết kế riêng; không nên giả định một field `updatedAt` tự động thay thế đúng mọi semantics của version.

## 13. Form web dài: mang version từ lúc đọc đến lúc lưu

Một wizard dài không bắt buộc giữ extended context. Một thiết kế thường dễ vận hành hơn là **DTO chứa version**.

### 13.1. DTO dữ liệu gửi về client

Ví dụ Java record:

```java
public record ProductEditView(
    Long id,
    String name,
    BigDecimal price,
    Long version
) {}
```

Khi mở màn hình sửa, service trả:

```json
{
  "id": 42,
  "name": "Bút xanh",
  "price": 100000.00,
  "version": 5
}
```

Trong Java/API thực tế, biểu diễn số tiền nên được serialization theo quy ước chính xác (ví dụ JSON number phù hợp hoặc chuỗi decimal theo contract API); JSON trên chỉ minh họa cấu trúc payload.

Client gửi command:

```json
{
  "id": 42,
  "name": "Bút xanh loại mới",
  "price": 120000.00,
  "expectedVersion": 5
}
```

Service không chỉ lấy ID rồi ghi đè mọi trường. Nó kiểm tra **version mà user đã đọc**.

### 13.2. Service cập nhật trong context mới

```java
public void updateProduct(
        EntityManagerFactory emf,
        Long productId,
        String newName,
        BigDecimal newPrice,
        Long expectedVersion
) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Product product = em.find(Product.class, productId);
        if (product == null) {
            throw new IllegalArgumentException("Sản phẩm không tồn tại");
        }

        if (!Objects.equals(
                product.getVersion(),
                expectedVersion
        )) {
            throw new IllegalStateException(
                "Dữ liệu đã thay đổi; hãy tải lại trước khi lưu"
            );
        }

        product.rename(newName);
        product.changePrice(newPrice);

        // Có thể phát hiện lỗi optimistic locking tại flush
        // hoặc commit tùy provider.
        em.flush();
        tx.commit();
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

Ví dụ cần import `jakarta.persistence.*`, `java.math.BigDecimal` và `java.util.Objects`.

Có **hai tầng kiểm soát**:

1. **Kiểm tra `expectedVersion`** giúp phát hiện ngay khi mở transaction rằng form đã dựa trên dữ liệu cũ.
2. **`@Version` của JPA** vẫn cần thiết để phát hiện transaction khác cập nhật **sau bước kiểm tra** nhưng **trước khi transaction này commit**.

Chỉ kiểm tra `expectedVersion` mà bỏ `@Version` vẫn tồn tại **race condition**. Hai request có thể cùng thấy version còn khớp rồi cùng update; optimistic locking ở database giúp đóng khoảng trống cạnh tranh đó.

### 13.3. Trả conflict cho client

Trong API HTTP, một cách thiết kế thường gặp là trả trạng thái **409 Conflict** khi cập nhật dựa trên version cũ. Có thể dùng **412 Precondition Failed** khi hệ thống sử dụng HTTP `If-Match`/ETag để biểu diễn version và không đáp ứng điều kiện tiền đề.

Sau conflict, ứng dụng có thể hiển thị:

```text
Sản phẩm đã được một người khác thay đổi.

Phiên bản bạn đã mở:
  Tên: Bút xanh
  Giá: 100000

Phiên bản hiện tại:
  Tên: Bút đỏ
  Giá: 120000

Thay đổi của bạn:
  Tên: Bút xanh loại mới

Chọn:
  - Xem lại dữ liệu mới
  - Áp dụng lại thay đổi trên phiên bản mới
  - Hủy
```

Không tự động retry bằng cách lấy phiên bản mới rồi **ghi lại toàn bộ payload cũ**, vì hành vi đó có thể biến một conflict được phát hiện thành một lost update.

### 13.4. Update đúng các field người dùng thực sự thay đổi

Nếu một form chỉ sửa `name`, không nên luôn gửi và ghi lại `price` cũ trừ khi đó là yêu cầu của API. Cập nhật có chủ đích giúp giảm nguy cơ thay đổi ngoài ý muốn, nhưng **không thay thế version check** khi hai người cùng sửa field hoặc invariant liên quan.

Nếu dùng PATCH, cần định nghĩa semantics trường vắng mặt, trường gửi `null` và validation rõ ràng. Nếu dùng PUT để thay thế toàn bộ tài nguyên, càng cần phiên bản/ETag hoặc cơ chế concurrency control thích hợp.

## 14. `merge()` không phải “lấy mới và gộp thông minh”

Khi entity đã **detached**, JPA có `merge()`:

```java
Product detached = ...; // Đến từ một context cũ.

Product managed = em.merge(detached);
```

`merge()` sao chép state của detached entity vào một managed instance tương ứng (hoặc tạo/đưa vào managed context theo semantics JPA) và trả về **managed instance**. Đối tượng `detached` được truyền vào **vẫn không trở thành managed chỉ vì gọi merge**.

### 14.1. Vì sao merge dễ gây nhầm với dữ liệu cũ?

Giả sử detached object được tạo từ dữ liệu trước đây:

```text
detached Product:
  name="Bút xanh"
  price=100000
  version=5
```

Trong lúc đó database đã được cập nhật lên version 6. Nếu service gọi merge, cơ chế optimistic locking phải được áp dụng theo version của entity, và provider có thể báo conflict. Nếu không có version hoặc mapping/version không hoạt động như mong đợi, việc sao chép state cũ sang managed object có thể ghi đè dữ liệu mới.

Do đó:

- `merge()` **không bảo đảm chọn field mới nhất của hai phiên bản**.
- `merge()` không phải cơ chế giải quyết conflict nghiệp vụ.
- `merge()` không nên được dùng chỉ để đọc dữ liệu mới nhất.
- Không nên đưa một entity detached có rất nhiều field từ browser rồi merge toàn bộ một cách mù quáng.

Đối với form web, cách an toàn thường là **đọc entity mới trong transaction ngắn, kiểm tra version, áp dụng command vào những thuộc tính cho phép**.

### 14.2. Dùng kết quả trả về của merge

```java
Product managed = em.merge(detached);

// Các thay đổi tiếp theo nên tác động vào managed:
managed.rename("Tên hợp lệ mới");
```

Không dựa vào:

```java
em.merge(detached);
detached.rename("Tên sửa tiếp"); // Detached object không được tự theo dõi.
```

Nếu context được đóng sau đó, đối tượng `managed` cũng trở thành detached. Lifecycle của object và context phải luôn được hiểu rõ.

## 15. Pessimistic locking: khi cần bảo vệ bằng khóa database

Optimistic locking thích hợp với phần lớn form web, nơi người dùng có thể suy nghĩ lâu và conflict tương đối hiếm. Trong một số nghiệp vụ transaction ngắn với cạnh tranh cao, ứng dụng có thể dùng **pessimistic locking**.

Ví dụ:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = em.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (product == null) {
        throw new IllegalArgumentException("Không có sản phẩm");
    }

    product.changePrice(new BigDecimal("125000.00"));

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Các import cần `jakarta.persistence.LockModeType` và `java.math.BigDecimal`.

Tùy provider/database, `PESSIMISTIC_WRITE` thường yêu cầu khóa ở DB để hạn chế cập nhật đồng thời cho tới khi transaction kết thúc. Các lock mode liên quan còn có `PESSIMISTIC_READ` và `PESSIMISTIC_FORCE_INCREMENT` theo điều kiện áp dụng tương ứng.

**Không giữ pessimistic lock trong thời gian user nhập form 10 phút.** Điều đó biến sự chậm trễ của người dùng thành thời gian giữ lock database, dễ gây:

- Lock timeout.
- Deadlock.
- Giảm thông lượng.
- Chặn transaction khác không cần thiết.

Pessimistic locking nên nằm trong **transaction ngắn** thực thi một thao tác nghiệp vụ đủ hẹp. Với phiên làm việc dài, optimistic locking + version và cơ chế giải quyết conflict thường phù hợp hơn.

### 15.1. Optimistic lock qua API

Ngoài `@Version`, JPA còn hỗ trợ lock mode như `OPTIMISTIC` và `OPTIMISTIC_FORCE_INCREMENT` để yêu cầu kiểm tra/tăng version theo semantics chuẩn:

```java
Product product = em.find(Product.class, id);
em.lock(product, LockModeType.OPTIMISTIC);
```

Việc dùng lock mode cụ thể phụ thuộc transaction, loại entity, yêu cầu nghiệp vụ và database. `OPTIMISTIC_FORCE_INCREMENT` không nên được dùng như một nút “làm mới dữ liệu”; nó liên quan đến kiểm soát phiên bản khi lock entity.

## 16. JPQL bulk UPDATE/DELETE và native SQL có thể làm context stale ngay lập tức

Đôi khi không cần có transaction từ người dùng khác: **chính ứng dụng** có thể cập nhật database bằng bulk statement, bỏ qua các managed entity đang giữ trong context.

### 16.1. Bulk JPQL update không đồng bộ trực tiếp managed instances

Ví dụ:

```java
Product product = em.find(Product.class, 42L);

int updated = em.createQuery(
    """
    UPDATE Product p
    SET p.price = :price
    WHERE p.id = :id
    """
)
.setParameter("price", new BigDecimal("155000.00"))
.setParameter("id", 42L)
.executeUpdate();

// product.getPrice() có thể vẫn giữ giá cũ.
```

JPQL bulk update thao tác trực tiếp trên dữ liệu persistence và **không tự đồng bộ state của mọi entity đã managed** theo cách dirty checking thông thường. Cơ chế version checking/incrementing của từng managed entity cũng **không được tự áp dụng giống một update entity thông thường** cho mọi câu bulk update.

Vì vậy cần đặc biệt cẩn thận khi update các bảng có `@Version`: bulk update mặc định có thể bỏ qua quy tắc version thông thường của entity nếu không thiết kế lại câu update.

### 16.2. Quy trình phổ biến: flush trước, clear sau

Khi cần bulk operation trong cùng transaction:

```java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    // Đồng bộ các thay đổi managed đã được xác định là cần giữ.
    em.flush();

    int count = em.createQuery(
        """
        UPDATE Product p
        SET p.price = :newPrice
        WHERE p.id IN :ids
        """
    )
    .setParameter("newPrice", new BigDecimal("150000.00"))
    .setParameter("ids", productIds)
    .executeUpdate();

    // Không giữ lại những managed instances có thể đã stale.
    em.clear();

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Ý nghĩa:

1. `flush()` trước bulk update giúp tránh pending entity changes vô tình đè lên kết quả bulk. Chỉ dùng nếu các thay đổi pending **đã được chấp nhận**; nếu không, cần hủy hoặc xử lý chúng theo nghiệp vụ.
2. Bulk update chạy trực tiếp tới DB.
3. `clear()` detach managed entities đang có để những lần đọc sau không trả về state stale từ L1.
4. Transaction vẫn cần commit để bulk update trở thành bền vững.

**Quan trọng:** `clear()` có thể làm mất thay đổi chưa flush; không được copy quy trình trên máy móc vào một transaction đang sửa nhiều entity khác. Đặt bulk operation trong entity manager riêng thường dễ kiểm soát hơn.

### 16.3. Native SQL cũng có cùng vấn đề

```java
em.createNativeQuery(
    "UPDATE products SET price = ? WHERE id = ?"
)
.setParameter(1, new BigDecimal("150000.00"))
.setParameter(2, 42L)
.executeUpdate();
```

Managed `Product#42` đang trong context không tự được cập nhật chỉ vì SQL native thay row. Database trigger, stored procedure và các ứng dụng khác cũng có thể gây trạng thái tương tự.

Nếu dùng native SQL ngoài JPA để đổi cột version hoặc dữ liệu khác, cần thống nhất một cơ chế concurrency control để các transaction JPA không đánh giá phiên bản sai.

## 17. First-level cache, second-level cache và query cache khác nhau

### 17.1. First-level cache gắn với persistence context

```text
EntityManager / Persistence Context A
  Product#42 -> object A (state đã tải)

EntityManager / Persistence Context B
  Product#42 -> object B (state có thể khác)
```

Mỗi context giữ managed instances của chính nó. `em.clear()` ảnh hưởng L1 của **context đang gọi**, không xóa toàn bộ cache của mọi entity manager.

### 17.2. Second-level cache chia sẻ ở phạm vi provider/factory

Một số provider có **second-level cache (L2)**, thường dùng để chia sẻ state đã đọc giữa nhiều context của cùng persistence unit/entity manager factory, theo cấu hình.

```text
EntityManager A -- L1 A --+
                          +--> L2 shared cache --> Database
EntityManager B -- L1 B --+
```

Nếu dùng một entity manager mới, L1 mới bắt đầu trống. Nhưng lần đọc vẫn có thể lấy dữ liệu từ L2 nếu cache được bật và provider cho phép. Trong môi trường nhiều node hoặc có ứng dụng bên ngoài cập nhật trực tiếp DB, coherence/invalidation của L2 cần được thiết kế rõ.

### 17.3. `CacheRetrieveMode.BYPASS` không bỏ qua managed entity đang nằm trong L1

JPA cung cấp cache retrieve mode nhằm điều khiển việc sử dụng shared cache:

```java
EntityManager em = emf.createEntityManager();

try {
    em.setProperty(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    );

    Product product = em.find(Product.class, productId);
} finally {
    em.close();
}
```

Với một context mới, cách này có thể hữu ích khi yêu cầu **bỏ qua shared cache** cho phép đọc theo semantics provider/JPA. Nhưng nó **không có nghĩa bỏ qua managed instance đã tồn tại trong cùng persistence context**.

Nếu entity đã managed và stale:

```java
Product old = em.find(Product.class, productId);

// Set shared-cache BYPASS tại đây không buộc old
// tự được tải lại từ database:
em.setProperty(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

Product again = em.find(Product.class, productId);
```

`again` vẫn có thể chính là `old` của L1. Để đồng bộ thực sự, cân nhắc `refresh` hoặc context mới phù hợp.

### 17.4. Evict shared cache khác clear persistence context

Với shared cache qua `EntityManagerFactory`:

```java
emf.getCache().evict(Product.class, productId);
```

Thao tác này yêu cầu evict entry khỏi shared cache theo API JPA nếu provider hỗ trợ cache tương ứng. Nó **không tự detach hoặc refresh** một `Product#id` đang managed trong một entity manager khác.

| Công cụ | Phạm vi tác động chủ yếu |
|---|---|
| `em.refresh(product)` | State của managed product trong context hiện tại. |
| `em.clear()` | Toàn bộ managed instances của context hiện tại. |
| `em.detach(product)` | Entity được chỉ định (và cascade liên quan nếu có). |
| `emf.getCache().evict(Product.class, id)` | Entry L2/shared cache cho identity được chỉ định. |
| `CacheRetrieveMode.BYPASS` | Chính sách lấy dữ liệu từ shared cache, không phải lệnh xóa L1. |

Query cache là một cơ chế khác do provider cung cấp: nó có thể cache kết quả/trình tự ID của truy vấn, không đồng nghĩa với managed entity cache và có những quy tắc invalidation riêng. Không nên coi “đã bật cache” là một khái niệm duy nhất.

## 18. Transaction isolation và stale data

Ngay cả khi persistence context không giữ object cũ, database isolation vẫn ảnh hưởng **dữ liệu mà một transaction có thể nhìn thấy**.

### 18.1. Các hiện tượng đồng thời

| Hiện tượng | Ví dụ | Cơ chế cần xem xét |
|---|---|---|
| Dirty read | Một transaction nhìn thay đổi chưa commit của transaction khác. | Isolation của database, thường tránh bằng READ COMMITTED trở lên tùy hệ thống. |
| Non-repeatable read | Cùng transaction đọc một hàng hai lần nhưng thấy giá trị khác do transaction khác commit. | Isolation của database, snapshot/MVCC/lock behavior. |
| Phantom read | Hai truy vấn cùng điều kiện trả về tập hàng khác nhau do transaction khác thêm/xóa hàng. | Isolation và cơ chế khóa/predicate, tùy DB. |
| Stale managed state | JPA giữ object cũ trong L1 dù DB đã thay đổi. | Vòng đời persistence context, `refresh`/`clear`/context mới. |
| Lost update | Thay đổi dựa trên dữ liệu cũ ghi đè thay đổi của người khác. | `@Version`, locking, transaction và conflict handling. |

### 18.2. Isolation cao không làm managed object tự reload

Ví dụ dùng `REPEATABLE_READ` có thể cố ý giữ một snapshot ổn định trong transaction. Trong khi đó, persistence context còn có identity map riêng.

Hai lớp này độc lập:

```text
Java layer:      JPA Persistence Context / L1 managed state
                           |
                           v
Database layer:  Transaction isolation / MVCC / locks
                           |
                           v
                 Committed database rows
```

Đổi isolation level không tự gọi `em.refresh()`. Ngược lại, `em.refresh()` cũng không được phép vượt qua những giới hạn snapshot mà database áp dụng cho transaction.

### 18.3. Không mở transaction xuyên suốt thời gian người dùng suy nghĩ

Giữ một database transaction từ lúc user mở form đến lúc user nhấn Save sau 20 phút có thể làm tăng:

- Thời gian giữ kết nối hoặc tài nguyên transaction.
- Lock contention.
- MVCC snapshot retention và ảnh hưởng cleanup.
- Nguy cơ timeout/rollback.
- Khó mở rộng khi có nhiều người dùng đồng thời.

Thay vào đó, thường chia workflow thành:

```text
GET /products/42/edit
  -> transaction đọc ngắn
  -> DTO {id, name, price, version}
  -> đóng context

Người dùng chỉnh sửa trong browser
  -> không giữ transaction mở

PUT /products/42
  -> transaction ghi ngắn
  -> đọc entity mới + kiểm tra expectedVersion
  -> cập nhật, flush, commit
  -> trả thành công hoặc conflict
```

Đây là cách giải quyết “long conversation” mà **không cần long transaction hoặc long-lived managed context**.

## 19. Thiết kế với Spring: lưu ý về `@Transactional` và Open EntityManager in View

Trong dự án Spring, developer dễ gặp một context dài hơn mong đợi khi có cơ chế **Open EntityManager in View** (OEIV hoặc OSIV đối với Hibernate Session).

Cơ chế này có thể giữ entity manager gắn với request để view/serializer truy cập lazy associations sau khi service transaction kết thúc. Nhưng:

- Việc giữ entity manager qua phần render/view **không đồng nghĩa giữ transaction nghiệp vụ**.
- Một số thao tác lazy load có thể phát SQL sau khi transaction service đã hoàn tất, theo cơ chế framework/provider và cấu hình.
- Object graph có thể giữ state đã tải, còn phần khác được truy cập ở thời điểm muộn hơn.
- API serialization có thể tạo nhiều truy vấn khó dự đoán hoặc N+1.
- Không nên hiểu OEIV là một thiết kế extended persistence context dành cho wizard nhiều request.

Đối với REST API, một cách tổ chức thường dễ dự đoán là:

1. Service method đặt transaction rõ ràng.
2. Query lấy đủ dữ liệu cần thiết.
3. Map entity sang DTO trong phạm vi context.
4. Trả DTO, không để serializer tự duyệt managed entity graph ngoài service.
5. Không giữ `EntityManager`/JPA Session trong HTTP session hoặc singleton.

Nếu hệ thống dùng `@Transactional(readOnly = true)`, cần nhớ đó là metadata/hint cho framework và cơ chế transaction/provider; **không tự có nghĩa mọi entity luôn được refresh từ DB**, cũng không tự giải quyết lost update.

## 20. Quản lý bộ nhớ của persistence context sống lâu

Một persistence context giữ managed entities, state và metadata phục vụ dirty checking. Nếu ứng dụng import hàng trăm nghìn bản ghi trong **một context liên tục**, bộ nhớ có thể tăng đáng kể.

### 20.1. Batch processing và `flush()/clear()` có kiểm soát

Trong một tác vụ batch có transaction và các entity mới được persist:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    int count = 0;
    for (Product product : productsToImport) {
        em.persist(product);
        count++;

        if (count % 100 == 0) {
            em.flush();
            em.clear();
        }
    }

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Ý nghĩa:

- `flush()` đồng bộ các thay đổi đang chờ trước khi tách entity.
- `clear()` giúp context không phải giữ mãi các entity đã được đưa xuống DB.
- `commit()` mới là bước xác nhận transaction.

Đây chỉ là phác thảo quản lý context cho batch; với lượng dữ liệu lớn, còn cần cân nhắc transaction chia lô, JDBC batching, chi phí `IDENTITY`, error recovery, ID generator, quan hệ cascade và giới hạn bộ nhớ.

**Không clear trước khi flush** nếu muốn giữ những thay đổi chưa được ghi. Và nếu các entity đang được code giữ bên ngoài vòng lặp, sau `clear()` chúng đã detached; sửa tiếp sẽ không tự được đồng bộ vào transaction hiện tại.

### 20.2. Giải phóng context của business conversation

Nếu thật sự dùng extended context, cần có chính sách:

- Khi nào conversation bắt đầu và kết thúc.
- Người dùng hủy wizard thì xử lý state chưa commit ra sao.
- Khi request timeout/session timeout thì giải phóng object và tài nguyên thế nào.
- Giới hạn số entity/collection được tải trong context.
- Không dùng một context cho nhiều người dùng.
- Không dùng cùng `EntityManager` đồng thời từ nhiều thread.

Trong các hệ có stateful session bean, container quản lý vòng đời tài nguyên tương ứng, nhưng ứng dụng vẫn phải thiết kế logic kết thúc conversation và phục hồi lỗi.

## 21. Quy trình chẩn đoán một lỗi dữ liệu cũ

Giả sử user báo:

> “Tôi đã sửa giá sản phẩm ở màn hình A, nhưng màn hình B vẫn hiển thị giá cũ.”

Có thể chẩn đoán theo trình tự:

### Bước 1: Xác nhận dữ liệu đã commit thật chưa

Màn hình A có thể chỉ gọi `flush()` nhưng transaction rollback sau đó. Kiểm tra ranh giới transaction và kết quả commit trước khi kết luận màn hình B bị stale.

### Bước 2: Kiểm tra B có đang dùng cùng persistence context không

Nếu B giữ cùng một `EntityManager`/extended context hoặc object managed từ trước, `find()` có thể trả state cũ từ L1.

### Bước 3: Kiểm tra dữ liệu có phải detached DTO/entity cũ không

Nếu B giữ một DTO trong HTTP session hoặc browser state, dù DB đã cập nhật, JPA không tự làm mới DTO đó. Cần có chiến lược fetch lại từ backend.

### Bước 4: Kiểm tra L2 cache/query cache

Nếu B dùng entity manager mới nhưng vẫn thấy giá cũ, xem caching của provider, tính nhất quán giữa các node, invalidation và chính sách cache khi có SQL trực tiếp.

### Bước 5: Kiểm tra database isolation/replica

B có thể đọc trên một transaction snapshot cũ hoặc một **read replica đang trễ replication**. Trong trường hợp này, làm mới JPA L1 không bảo đảm đọc được commit mới nhất.

### Bước 6: Kiểm tra bulk update/native SQL

Một JPQL bulk update hoặc SQL ngoài JPA có thể đổi database mà không cập nhật managed instances hiện có. Cần xác định chỗ phát bulk và quy trình flush/clear của service.

### Bước 7: Thiết kế biện pháp đúng loại lỗi

| Nguyên nhân | Hướng giải quyết |
|---|---|
| Managed entity stale trong context lâu | `refresh` khi phù hợp; hoặc kết thúc context và đọc lại bằng context mới. |
| Form client stale và user chuẩn bị ghi | Truyền version từ thời điểm đọc; kiểm tra và dùng `@Version` khi update. |
| Bulk update làm context stale | Kiểm soát flush/clear hoặc dùng context riêng. |
| L2 cache stale | Cấu hình cache/invalidation, BYPASS hoặc evict đúng phạm vi. |
| Snapshot isolation cố giữ bản đọc cũ | Kết thúc transaction và đọc ở transaction mới theo isolation phù hợp. |
| Replica chưa đồng bộ | Cân nhắc chính sách read-after-write, đọc writer/primary khi cần. |
| EntityManager sống quá lâu | Rút ngắn lifecycle, dùng context theo request/transaction thay vì singleton. |
| Hai người dùng cập nhật xung đột | Optimistic locking, trả conflict và giải quyết thay đổi. |

## 22. Các anti-pattern cần tránh

### 22.1. Giữ `EntityManager` trong biến static

```java
// Không nên:
public class EntityManagers {
    public static final EntityManager EM =
            emf.createEntityManager();
}
```

Một entity manager chung toàn ứng dụng không thread-safe, giữ state dài và khiến transaction/context bị chia sẻ không đúng. **Chia sẻ `EntityManagerFactory`, tạo/tiêm `EntityManager` theo scope phù hợp**.

### 22.2. Refresh mọi entity ngay trước mỗi getter

```java
public String getName(Product product) {
    em.refresh(product);
    return product.getName();
}
```

Cách này vừa có thể xóa pending changes, vừa tạo thêm SQL không cần thiết, vừa không giải quyết các vấn đề concurrency sau thời điểm đọc. Cần làm mới có chủ đích, không biến getter thành truy vấn DB ngầm.

### 22.3. Gọi `clear()` để sửa mọi lỗi

```java
em.clear();
```

Có thể làm mất state chưa flush của các entity khác. Clear là thao tác cấp context, ảnh hưởng toàn bộ managed entities; nếu chỉ cần một entity, cân nhắc refresh/detach hoặc dùng một context mới, không phá state đang xử lý.

### 22.4. Merge nguyên object gửi từ browser

```java
// Rủi ro nếu DTO/client đã cũ hoặc bị sửa field ngoài quyền:
em.merge(productFromClient);
```

Browser không nên được coi là nguồn sự thật của toàn bộ entity state. Dùng command/DTO, kiểm tra quyền, version và chỉ áp dụng thuộc tính được phép sửa vào managed entity.

### 22.5. Tự động retry conflict bằng cách ghi đè

Nếu `OptimisticLockException` xảy ra, không nên lập tức:

```text
Conflict -> reload -> ghi toàn bộ dữ liệu cũ -> commit
```

mà không có chính sách merge. Điều đó có thể biến bảo vệ optimistic locking thành **last-write-wins** một cách âm thầm. Retry tự động có thể hợp lý cho thao tác idempotent hoặc phép biến đổi có thể áp dụng lại, nhưng cần xác định lại logic nghiệp vụ trên state mới và giới hạn retry.

### 22.6. Dùng `synchronized` Java thay lock database

`synchronized` chỉ bảo vệ concurrency trong phạm vi JVM và object monitor tương ứng. Nó không bao quát nhiều instance ứng dụng, tác vụ batch hoặc client SQL bên ngoài. JPA version/locking và database constraints mới phù hợp để bảo vệ dữ liệu ở phạm vi nhiều tiến trình.

### 22.7. Xem `refresh()` như xác nhận cập nhật thành công

`refresh()` chỉ giúp lấy state theo semantics transaction hiện tại. Nếu thao tác cập nhật trước đó rollback, refresh sẽ đọc state trước đó của database. Nó **không biến transaction thất bại thành thành công**.

## 23. Chọn chiến lược theo loại ứng dụng

| Tình huống | Chiến lược khuyến nghị | Vì sao |
|---|---|---|
| CRUD REST thông thường | Transaction ngắn + context theo đơn vị công việc + DTO. | Dễ quản lý vòng đời và giảm stale L1. |
| Form sửa kéo dài nhiều phút | DTO chứa version + `@Version` khi lưu. | Không giữ transaction/EntityManager trong lúc user suy nghĩ. |
| Wizard có object graph phức tạp trong Jakarta EE | Có thể cân nhắc stateful bean + extended context + policy đồng bộ chặt. | Duy trì state giữa các business method, nhưng cần xử lý stale/conflict/memory. |
| Người dùng muốn “Tải lại dữ liệu” và đồng ý bỏ thay đổi local | `refresh(entity)` hoặc đọc bằng context mới. | Chủ động thay snapshot. |
| Một entity managed đã stale nhưng các entity khác cần giữ | `refresh(entity)` sau khi xem xét local changes. | Tác động hẹp hơn `clear()`. |
| Sau bulk JPQL UPDATE/DELETE | Flush phù hợp, thực thi bulk, clear context hoặc dùng context riêng. | Tránh managed state lệch với DB. |
| Tác vụ ghi hàng loạt | `flush()/clear()` theo batch có kiểm soát. | Hạn chế bộ nhớ và dirty checking. |
| Dữ liệu ít xung đột, nhiều người đọc | Optimistic locking bằng `@Version`. | Không cần giữ DB lock lâu. |
| Cạnh tranh cập nhật rất cao trong transaction ngắn | Đánh giá pessimistic locking. | Có thể bảo vệ thao tác theo hàng tại DB. |
| Ứng dụng có cache chia sẻ nhiều node | Chiến lược L2 invalidation/BYPASS/evict và read-after-write phù hợp. | Context mới chưa chắc bảo đảm freshness nếu cache/replica stale. |

### 23.1. Một kiến trúc thực dụng cho service stateless

```text
HTTP GET /products/42
        |
        v
Transaction đọc ngắn
  - EntityManager context mới
  - find Product
  - map Product -> ProductDTO(name, price, version)
        |
        v
Trả DTO, đóng context
        |
        v
User chỉnh sửa ở browser, không giữ DB transaction
        |
        v
HTTP PUT /products/42, expectedVersion=...
        |
        v
Transaction ghi ngắn
  - EntityManager context mới
  - find Product
  - kiểm tra expectedVersion
  - áp dụng thay đổi hợp lệ
  - @Version kiểm tra khi flush/commit
        |
        +-- commit thành công -> trả kết quả mới
        |
        +-- conflict -> rollback -> đọc bản mới -> thông báo user
```

Đây không phải cơ chế duy nhất, nhưng nó giải quyết đồng thời nhiều vấn đề của ngữ cảnh sống lâu: không giữ context quá lâu, không giữ transaction trong thời gian user nhập liệu và có cơ chế phát hiện dữ liệu cũ lúc ghi.

## 24. Câu hỏi tự kiểm tra

**1. Vì sao gọi `em.find(Product.class, id)` hai lần trong cùng persistence context có thể không đọc database lần hai?**

Vì persistence context duy trì managed instance theo entity identity (first-level cache). `find` có thể trả về object đã managed.

**2. Extended persistence context có nghĩa transaction database cũng mở qua nhiều request không?**

Không. Extended context có thể tồn tại qua nhiều transaction, còn mỗi transaction database có boundary riêng. Không nên giữ transaction mở suốt thời gian user suy nghĩ.

**3. Hai entity manager khác nhau có thể nhìn thấy hai giá trị khác nhau của cùng một hàng không?**

Có, do mỗi context có state riêng, thời điểm đọc khác nhau, cache hoặc isolation. Những khác biệt này không tự là lỗi JPA.

**4. `refresh()` có thể xóa thay đổi chưa flush không?**

Có. Nó làm mới state của managed entity theo dữ liệu được đọc từ persistence store, nên cần quyết định có được phép bỏ thay đổi local hay không.

**5. `flush()` có làm một entity stale tự mới lên không?**

Không. Flush đồng bộ thay đổi từ context xuống DB, không phải đọc state mới từ DB vào context.

**6. `clear()` khác `detach(entity)` ở đâu?**

`clear()` detach tất cả managed entities của context; `detach(entity)` detach một entity được chỉ định (và những ảnh hưởng cascade phù hợp).

**7. Đã tạo EntityManager mới thì có chắc chắn đọc DB mới nhất không?**

Chưa chắc. Có thể còn L2 cache, query cache, transaction snapshot, read replica hoặc các yếu tố nhất quán dữ liệu khác.

**8. Vì sao `@Version` giúp tránh lost update?**

Provider kiểm tra version khi cập nhật; nếu một transaction khác đã sửa và tăng version, update dựa trên version cũ có thể bị từ chối bằng optimistic locking conflict.

**9. Nếu UI đã nhận DTO version 5, lúc người dùng lưu database đang version 6, nên làm gì?**

Báo conflict hoặc yêu cầu người dùng xem lại dữ liệu mới, không lặng lẽ ghi đè. Có thể hiển thị khác biệt và cho phép áp dụng lại thay đổi có kiểm soát.

**10. `merge()` có tự gộp field mới nhất của detached object với field mới nhất trong database không?**

Không. Merge sao chép detached state vào managed instance theo JPA semantics; nó không phải thuật toán merge nghiệp vụ thông minh.

**11. Sau JPQL bulk UPDATE, tại sao entity đang managed có thể vẫn cũ?**

Bulk update thao tác trực tiếp ở persistence store, bỏ qua đồng bộ managed instances thông thường. Cần kế hoạch flush/clear hoặc context riêng.

**12. `CacheRetrieveMode.BYPASS` có buộc `find` bỏ qua một managed Product đã nằm trong L1 không?**

Không. Nó điều khiển việc sử dụng shared cache; first-level context identity vẫn có thể trả về managed instance.

**13. Khi nào nên cân nhắc `PESSIMISTIC_WRITE`?**

Khi cần bảo vệ cập nhật có cạnh tranh cao trong transaction ngắn và chấp nhận chi phí lock/timeout theo database. Không dùng để giữ khóa qua form dài.

**14. Có nên đặt `EntityManager` trong singleton service dùng cho mọi HTTP request?**

Không. EntityManager không thread-safe và việc chia sẻ context dễ gây state stale, race condition và rò rỉ tài nguyên.

**15. Nếu `refresh()` vẫn không thấy commit mới, có thể do đâu?**

Có thể transaction đang dùng snapshot isolation, đọc từ replica chậm, dữ liệu chưa commit thật hoặc bị cache ở tầng khác. Cần xác định nguồn dữ liệu và transaction boundary.

## 25. Tổng kết

**Ngữ cảnh sống lâu** giữ các managed entity qua thời gian dài hoặc qua nhiều transaction. Đây có thể là một công cụ hữu ích cho business conversation được quản lý chặt chẽ, nhưng cũng tạo rủi ro **stale data**, **lost update**, tải dữ liệu không dự đoán được và tiêu thụ bộ nhớ.

Các nguyên tắc cốt lõi:

1. **Persistence context là identity map/first-level cache**, không phải cửa sổ luôn phản chiếu database mới nhất.
2. **Transaction boundary khác persistence-context lifetime.** Extended context và application-managed EntityManager có thể giữ state qua nhiều transaction.
3. `refresh()`, `detach()`, `clear()` và `close()` phục vụ những mục đích khác nhau; dùng đúng khi biết có đang giữ thay đổi local chưa lưu hay không.
4. **`flush()` không làm mới dữ liệu**; nó đồng bộ pending state của context xuống database.
5. **`@Version` là cơ chế quan trọng để phát hiện cập nhật xung đột**. Không thay nó bằng những lần đọc/refresh tùy tiện.
6. Với form web dài, thường nên **giữ DTO + version và dùng transaction ngắn tại bước Save**, thay vì giữ entity manager hoặc transaction trong suốt thời gian người dùng chỉnh sửa.
7. Khi làm việc với bulk update, L2 cache, query cache, database isolation và read replica, cần xét cả những tầng ngoài first-level cache.
8. Mỗi EntityManager cần có **vòng đời rõ ràng, không chia sẻ đồng thời giữa nhiều thread**, và cần giải phóng tài nguyên khi công việc kết thúc.

Cách nhìn tổng quát:

```text
Dữ liệu đúng và nhất quán
   |
   +-- Freshness khi đọc
   |     +-- vòng đời context ngắn / context mới
   |     +-- refresh có chủ đích
   |     +-- cache và isolation phù hợp
   |
   +-- Safety khi ghi
   |     +-- @Version / optimistic locking
   |     +-- transaction boundary rõ
   |     +-- xử lý conflict, không ghi đè mù quáng
   |
   +-- Hiệu quả vận hành
         +-- không giữ EM hoặc DB transaction quá lâu
         +-- flush/clear có kiểm soát cho batch
         +-- fetch đúng nhu cầu và giải phóng context
```

Khi phân biệt rõ **độ mới của dữ liệu**, **an toàn cập nhật đồng thời** và **vòng đời persistence context**, ứng dụng JPA có thể duy trì mô hình entity nhất quán mà không biến dữ liệu trong bộ nhớ thành nguồn lỗi âm thầm.

### Tài liệu tham khảo

- [Jakarta Persistence — đặc tả chính thức](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — `EntityManager`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager)
- [Jakarta Persistence API — `@Version`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/version)
- [Jakarta Persistence API — `PersistenceContextType`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/persistencecontexttype)
- [Jakarta Persistence API — `SynchronizationType`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/synchronizationtype)
