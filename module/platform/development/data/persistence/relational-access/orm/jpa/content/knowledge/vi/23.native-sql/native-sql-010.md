# Kiểm tra tương tác giữa native query, flush và dữ liệu trong ngữ cảnh

Trong JPA, **persistence context** giữ những entity đang được quản lý (*managed*), theo dõi thay đổi của chúng và phối hợp với database trong transaction. Khi sử dụng JPQL/Criteria, JPA provider có đủ thông tin từ entity mapping để thực hiện truy vấn. Nhưng ứng dụng còn có thể thực thi **native SQL** qua `EntityManager.createNativeQuery(...)`, tức chạy câu SQL trực tiếp theo bảng, cột và cú pháp của database.

Từ đây xuất hiện hai vấn đề rất dễ nhầm:

1. **Entity đã đổi trong bộ nhớ nhưng SQL chưa được flush:** native `SELECT` nhìn thấy giá trị nào? Việc thực thi native query có làm provider flush các thay đổi đang chờ hay không?
2. **Native SQL đã sửa/xóa hàng trong database nhưng persistence context vẫn giữ entity cũ:** gọi `find()` hoặc getter tiếp theo có thấy giá trị mới không? Có nguy cơ dirty checking ghi đè dữ liệu vừa được native SQL cập nhật không?

Hai chiều tương tác này không đối xứng. **Flush đồng bộ trạng thái từ persistence context xuống database; nó không tự kéo mọi thay đổi do native SQL tạo ra ngược vào các object Java đang managed.**

Ví dụ dễ hình dung:

```java
Book book = em.find(Book.class, 42L);
book.rename("JPA chuyên sâu");

Object result = em.createNativeQuery(
    "SELECT title FROM books WHERE id = ?"
).setParameter(1, 42L)
 .getSingleResult();
```

Nếu `book` vẫn managed, lệnh `rename()` đổi trạng thái Java. Giá trị mà native `SELECT` đọc phụ thuộc việc thay đổi có được đồng bộ trước query, flush mode, transaction và provider.

Ở chiều ngược lại:

```java
Book book = em.find(Book.class, 42L);

em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, "Tên do SQL sửa")
 .setParameter(2, 42L)
 .executeUpdate();

String title = book.getTitle();
```

Native `UPDATE` có thể đã thay đổi hàng database trong transaction, **nhưng getter trên `book` vẫn có thể trả title cũ**. JPA không tự cập nhật mọi managed instance khi một lệnh SQL tùy ý thay đổi dữ liệu.

Bài học **“Kiểm tra tương tác giữa native query, flush và dữ liệu trong ngữ cảnh”**, thuộc chương **Native SQL** của **Data Persistence Relational Access ORM JPA**, hướng dẫn cách xây dựng mô hình tư duy, kiểm chứng SQL thực tế, tổ chức transaction và viết integration test để tránh kết quả đọc sai, cập nhật chồng lấn, lỗi constraint và persistence context stale.

Các đoạn code sử dụng `jakarta.persistence`. Dự án JPA đời cũ có thể dùng `javax.persistence`. Một số hành vi tối ưu hóa native query là *provider-specific*, vì thế khi cần kết luận về số lượng/thứ tự SQL, phải kiểm thử đúng JPA provider, phiên bản JDBC driver và database đang sử dụng.

---

## 1. Ba nơi giữ trạng thái cần phân biệt

Một thao tác JPA có thể đồng thời liên quan đến ba tầng:

| Tầng | Ví dụ trạng thái | Điều cần nhớ |
| --- | --- | --- |
| Java object | `book.title = "Mới"` | Setter đã sửa object, không chứng minh database đã có giá trị mới |
| Persistence context | Managed Book #42 đang dirty | Theo dõi state/identity để flush, nhưng không phải một bản sao tức thời của mọi thay đổi DB |
| Database transaction | Hàng `books.id = 42` với giá trị đã được SQL ghi | SQL có thể đã chạy nhưng transaction vẫn chưa commit |

Một timeline:

```text
                 JAVA / PERSISTENCE CONTEXT                 DATABASE
                        │                                     │
T0: em.find(42)         ├──────── SELECT ───────────────────►│
                        │◄─────── Book(title="A") ──────────┤
                        │                                     │
T1: book.rename("B")    │ managed Book(title="B")             │ title="A"
                        │                                     │
T2: em.flush()          ├──────── UPDATE title="B" ─────────►│ title="B"
                        │                                     │ (chưa commit)
T3: native SQL UPDATE   ├──────── UPDATE title="C" ─────────►│ title="C"
                        │                                     │ (chưa commit)
T4: book.getTitle()     │ có thể vẫn trả "B"                  │ title="C"
                        │                                     │
T5: commit              ├──────── COMMIT ───────────────────►│
                        │                                     │
```

Ở T2, provider **đẩy** trạng thái context xuống DB qua flush. Ở T3, native SQL thay đổi DB **ngoài cơ chế dirty checking theo từng entity**. Vì thế tại T4 có thể tồn tại bất đồng giữa object Java và hàng DB trong chính transaction đó.

Không có quy tắc JPA chung nào nói native `UPDATE` sẽ tự gọi setter trên `book` hoặc cập nhật toàn bộ snapshot dirty checking nội bộ của provider.

## 2. Các khái niệm không được đồng nhất

### 2.1. Dirty checking

Với một entity managed:

```java
Book book = em.find(Book.class, 42L);
book.rename("Tên mới");
```

JPA provider có thể phát hiện thay đổi ở những thuộc tính persistent và phát `UPDATE` tại một điểm flush thích hợp. Không có phương thức `EntityManager.update(book)` trong API JPA chuẩn.

### 2.2. Flush

```java
em.flush();
```

`flush()` yêu cầu provider đồng bộ các thay đổi cần thiết của persistence context xuống database trong bối cảnh transaction hợp lệ. Có thể dẫn đến `INSERT`, `UPDATE`, `DELETE` hoặc SQL liên quan collection/join table.

**Flush không phải commit.**

### 2.3. Commit

```java
em.getTransaction().commit();
```

Nếu transaction resource-local commit thành công, những thay đổi SQL đã thực hiện trong transaction được xác nhận. Trong JTA/Spring, transaction manager quản lý commit thay vì ứng dụng gọi `getTransaction()` trực tiếp.

### 2.4. Refresh

```java
em.refresh(book);
```

`refresh()` có ý định tải lại trạng thái của **entity đang managed** từ database theo ngữ nghĩa JPA, ghi đè state trong bộ nhớ bằng dữ liệu được đọc. Nó khác với flush: **refresh kéo dữ liệu từ database vào entity; flush đẩy dữ liệu entity xuống database**.

### 2.5. Clear

```java
em.clear();
```

`clear()` detach toàn bộ managed entities khỏi persistence context. Nó không phải `rollback()` và không tự phục hồi field trên những object Java đã sửa; những thay đổi pending chưa flush có thể bị bỏ.

### Bảng hướng đồng bộ

| Thao tác | Hướng tác động chính | Điều không được suy ra |
| --- | --- | --- |
| Setter trên managed entity | Java object thay đổi, context theo dõi | SQL đã chạy |
| `em.flush()` | Context → database | Đã commit hoặc tự đọc thay đổi SQL ngoài context |
| `em.refresh(book)` | Database → managed Book | Toàn context được làm mới |
| `em.clear()` | Bỏ managed state khỏi context | Database rollback |
| Native `SELECT` | Database/query → scalar, array hoặc mapped entity | Tự đồng bộ mọi managed state theo hai chiều |
| Native `UPDATE/DELETE` | SQL trực tiếp → database | Tự cập nhật managed objects/snapshots |
| `commit()` thành công | Xác nhận transaction | Object stale tự được sửa |

---

## 3. Entity và schema dùng xuyên suốt

Giả sử ứng dụng quản lý sách:

```java
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
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean published;

    protected Book() {}

    public Book(String title, BigDecimal price) {
        rename(title);
        changePrice(price);
        this.published = false;
    }

    public Long getId() { return id; }

    public Long getVersion() { return version; }

    public String getTitle() { return title; }

    public BigDecimal getPrice() { return price; }

    public boolean isPublished() { return published; }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Invalid title");
        }
        title = newTitle.trim();
    }

    public void changePrice(BigDecimal newPrice) {
        Objects.requireNonNull(newPrice, "price");
        if (newPrice.signum() < 0) {
            throw new IllegalArgumentException("Negative price");
        }
        price = newPrice;
    }

    public void publish() {
        published = true;
    }
}
```

Schema minh họa:

```sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    price DECIMAL(14, 2) NOT NULL,
    published BOOLEAN NOT NULL
);
```

Cú pháp sinh ID và kiểu boolean thay đổi theo RDBMS. Ví dụ ban đầu:

| id | version | title | price | published |
| ---: | ---: | --- | ---: | --- |
| 42 | 3 | JPA cơ bản | 150000.00 | false |
| 43 | 1 | SQL nâng cao | 210000.00 | true |

Lưu ý `@Version` chỉ giúp optimistic locking khi provider thực hiện các thao tác entity theo ngữ nghĩa phù hợp. **Bulk native UPDATE tự viết không mặc nhiên tăng hoặc kiểm tra version**.

## 4. Hai chiều bất đồng phải kiểm thử riêng

### Chiều A: context dirty → native SELECT

```text
book.rename("B")
      │
      ▼
Persistence context: "B"
Database:            "A"
      │
      ▼
native SELECT title
      │
      ├── Nếu flush trước SELECT: DB có "B" → query thấy "B"
      └── Nếu chưa flush:          DB có "A" → query có thể thấy "A"
```

Câu hỏi kiểm thử: **native query đã phản ánh các thay đổi managed pending theo flush mode và transaction hiện tại chưa?**

### Chiều B: native UPDATE → entity managed stale

```text
em.find(Book, 42) → managed Book.title="A"
      │
      ▼
native UPDATE books SET title="C"
      │
      ▼
Database:            "C"
Persistence context: "A" (có thể vẫn vậy)
      │
      ▼
book.getTitle()       → có thể "A"
em.find(Book, 42)    → có thể trả cùng Book "A"
      │
      ▼
refresh / context mới → đọc lại "C" theo transaction/cache policy
```

Câu hỏi kiểm thử: **native SQL vừa cập nhật database có làm managed object đang có trong persistence context tự đổi theo không?**

Hai bài toán sử dụng các thao tác kiểm soát khác nhau. **Không thể dùng `flush()` để sửa mọi trường hợp managed entity stale do native SQL.** Ngược lại, `refresh()` không thay thế bước đồng bộ pending changes trước một native SELECT cần read-your-writes.

---

## 5. Native SELECT trước flush có thể đọc gì?

Giả sử transaction đã bắt đầu và entity được quản lý:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("JPA nâng cao");

Object titleFromSql = em.createNativeQuery(
    "SELECT title FROM books WHERE id = ?"
).setParameter(1, 42L)
 .getSingleResult();

em.getTransaction().commit();
```

Trong Java:

```java
book.getTitle() // "JPA nâng cao"
```

Nhưng native query thực thi SQL đọc từ database, nơi giá trị đổi tên có thể còn chưa được đồng bộ.

Ở chế độ `FlushModeType.AUTO`, khi persistence context tham gia transaction, provider phải bảo đảm những thay đổi đang chờ có thể ảnh hưởng kết quả query được phản ánh trong quá trình xử lý query theo ngữ nghĩa JPA. Một cách thường gặp là **flush trước khi thực thi native SELECT**. Tuy nhiên, provider, API gọi query, mapping và chiến lược thực thi có thể tác động đến thời điểm/loại SQL được phát.

Vì vậy **đừng viết ứng dụng dựa trên giả định “native SELECT luôn tự flush mọi dirty entity”** hoặc “native SELECT không bao giờ flush”. Cần hiểu bảo đảm của flush mode chuẩn, những extension đang sử dụng và xác minh hành vi của provider cụ thể.

### Nếu nghiệp vụ bắt buộc native SQL nhìn thấy thay đổi vừa làm?

Dùng transaction phù hợp và flush tường minh ở ranh giới rõ ràng:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("JPA nâng cao");

em.flush(); // Đồng bộ thay đổi pending trong transaction.

String titleFromSql = (String) em.createNativeQuery(
    "SELECT title FROM books WHERE id = ?"
).setParameter(1, 42L)
 .getSingleResult();

em.getTransaction().commit();
```

Trong một transaction hoạt động trên cùng database connection/transaction manager, native SELECT có thể đọc thay đổi đã flush của chính transaction đó theo quy tắc DB. Nhưng **flush không làm thay đổi được transaction isolation**, và việc transaction khác có nhìn thấy giá trị mới hay không còn phụ thuộc commit/isolation.

### Cẩn trọng với các cơ chế không chung một transaction

Nếu native SQL được thực thi bằng JDBC connection **khác** ngoài transaction JPA, việc JPA flush trước đó không đồng nghĩa connection kia có thể nhìn thấy dữ liệu chưa commit. Một integration test phải dùng đúng đường thực thi được ứng dụng sử dụng và xác định transaction boundary/connection participation.

## 6. FlushModeType.AUTO và COMMIT

JPA cung cấp:

```java
FlushModeType.AUTO
FlushModeType.COMMIT
```

Có thể đặt trên `EntityManager`:

```java
em.setFlushMode(FlushModeType.AUTO);
```

Hoặc trên query cụ thể:

```java
Query query = em.createNativeQuery(
    "SELECT title FROM books WHERE id = ?"
);

query.setFlushMode(FlushModeType.COMMIT);
query.setParameter(1, 42L);
Object value = query.getSingleResult();
```

### AUTO

Khi persistence context đang tham gia transaction, AUTO yêu cầu các thay đổi pending liên quan có thể ảnh hưởng kết quả query được tính đến khi xử lý query. Provider có thể:

- Flush những thay đổi cần thiết xuống database.
- Dùng một cách khác để bảo đảm query semantics nếu implementation hỗ trợ.

JPA không yêu cầu trước **mọi** SELECT phải phát toàn bộ UPDATE/INSERT/DELETE ngay cả khi query không liên quan. Với native SQL, việc provider xác định bảng phụ thuộc khó hơn so với JPQL/Criteria, nên chiến lược có thể thận trọng hơn.

### COMMIT

Ở COMMIT, tác động của những thay đổi pending trong persistence context lên query **trước commit** không được bảo đảm theo cách của AUTO. Không nên dùng kết quả native SELECT ở COMMIT để khẳng định chắc chắn rằng giá trị chưa flush đã được phản ánh.

Đồng thời:

> COMMIT không phải là lời hứa rằng provider tuyệt đối không phát SQL trước khi gọi `commit()`.

Ví dụ với `GenerationType.IDENTITY`, provider có thể chạy INSERT sớm để lấy ID. Một `em.flush()` tường minh vẫn đồng bộ được khi được gọi trong transaction phù hợp. Provider cũng có thể có chiến lược thực thi riêng.

### Ma trận

| Câu hỏi | AUTO | COMMIT |
| --- | --- | --- |
| Query phải xử lý thay đổi pending có liên quan theo bảo đảm JPA? | Có, trong joined transaction | Không có bảo đảm tương đương AUTO |
| Native SELECT có thể dẫn đến flush? | Có | Phụ thuộc provider và các yếu tố khác; không suy tuyệt đối |
| `em.flush()` tường minh có ý nghĩa? | Có | Có |
| Có phải mọi query đều phát UPDATE? | Không | Không |
| Có đảm bảo không SQL nào chạy trước commit? | Không | Không |
| Có làm stale managed entity được native SQL cập nhật tự đổi? | Không | Không |
| Có thay đổi mức cách ly DB không? | Không | Không |

Điểm cuối thường bị bỏ qua: **flush mode giải quyết khi nào pending state từ JPA ảnh hưởng query; nó không phải cơ chế invalidation toàn bộ context sau native DML**.

## 7. Tại sao provider xử lý native query khác JPQL?

Trong JPQL:

```java
em.createQuery(
    "SELECT b FROM Book b WHERE b.title = :title",
    Book.class
);
```

Provider có entity model và mapping của Book. Nó có thể phân tích các bảng/query spaces mà query đụng đến.

Trong native SQL:

```java
em.createNativeQuery(
    "SELECT b.title FROM books b WHERE b.id = ?"
);
```

provider nhận chuỗi SQL trực tiếp. Query có thể chứa:

- CTE (`WITH`).
- View hoặc materialized view.
- Subquery và window functions.
- Stored procedures.
- Database functions có side effects.
- Các bảng, join table và secondary table không hiển thị rõ trong metadata query.
- Dynamic SQL hoặc cú pháp dialect riêng.

Vì vậy, **mức độ provider biết query phụ thuộc những bảng nào có thể khác**. Một số provider chọn flush thận trọng trước native query; một số API extension cho phép khai báo query spaces hoặc synchronized entities.

### Khác biệt giữa chuẩn EntityManager và API riêng của provider

Khi dùng Hibernate, chẳng hạn, cách đồng bộ native query qua **JPA `EntityManager`** có thể khác khi dùng trực tiếp API **Hibernate `Session`**; các version và tùy chọn `addSynchronizedEntityClass`/`addSynchronizedQuerySpace` có thể ảnh hưởng auto-flush.

Điều này có hai hệ quả:

1. Không lấy một ví dụ dùng `Session.createNativeQuery(...)` rồi khẳng định mọi `EntityManager.createNativeQuery(...)` hoạt động giống hệt.
2. Nếu dùng extension provider để tối ưu flush, phải ghi rõ API, provider/version và query spaces được khai báo; khi nâng cấp phải chạy lại integration test.

**Không có một câu “native query luôn flush” hoặc “native query không bao giờ flush” đúng cho mọi tổ hợp API, mode, transaction và provider.**

## 8. Một query không liên quan có phải flush không?

Giả sử ứng dụng sửa Book nhưng đọc bảng Category:

```java
Book book = em.find(Book.class, 42L);
book.rename("Tên mới");

List<?> categories = em.createNativeQuery(
    "SELECT category_code FROM categories"
).getResultList();
```

Thay đổi `books.title` có thể không ảnh hưởng kết quả đọc `categories`. Một provider tối ưu có thể tránh flush nếu biết chắc query không phụ thuộc các bảng dirty.

Tuy vậy, native SQL khiến việc xác định dependency khó hơn. Provider có thể flush thận trọng vì:

- Không biết tất cả bảng hoặc view mà query dùng.
- Trigger/function có logic ẩn.
- Có pending changes tới join/secondary/collection tables.
- Provider không thực hiện native query space analysis.
- Cấu hình chung lựa chọn flush rộng hơn.

Đừng dùng giả định “hai bảng khác nhau chắc chắn không flush” như hợp đồng nghiệp vụ.

Ngược lại, nếu query có thể **ảnh hưởng kết quả**, hãy quan tâm tới tính đúng trước khi tối ưu số flush. Tối ưu hóa dựa trên query spaces là chuyện provider-specific và cần đo SQL.

## 9. Native COUNT cũng có thể chịu ảnh hưởng của pending INSERT

Giả sử đã tồn tại 10 Book thuộc danh mục `JAVA`:

```java
em.getTransaction().begin();

Book newBook = new Book(
    "JPA nâng cao",
    new BigDecimal("250000")
);

em.persist(newBook);

Number rawCount = (Number) em.createNativeQuery(
    "SELECT COUNT(*) FROM books"
).getSingleResult();

em.getTransaction().commit();
```

Nếu INSERT còn pending khi native COUNT chạy, database chưa chắc chứa hàng mới. Trong AUTO trên joined transaction, những pending changes ảnh hưởng query cần được xử lý đúng theo semantics; provider có thể flush trước query.

Tuy nhiên, trong entity ví dụ sử dụng `IDENTITY`, INSERT cũng có thể xảy ra sớm để lấy ID, trước cả thời điểm query. Vì thế **chỉ quan sát COUNT bao gồm sách mới không đủ chứng minh query đã kích hoạt flush**.

Muốn kiểm tra SQL thực tế cần:

- Bật SQL logging/statistics phù hợp.
- Biết ID generation strategy.
- Phân biệt INSERT do `persist()` với INSERT do flush trước query.
- Giữ transaction boundary rõ.
- Dùng fixture có những dirty UPDATE/DELETE không phụ thuộc generated ID nếu mục tiêu test là query-triggered flush.

### Kiểm thử có mục tiêu

Nếu muốn xác minh AUTO xử lý update pending, hãy load một Book đã persist, đổi field, rồi native SELECT lọc theo **field đó**. Cách này giúp giảm biến số liên quan tới INSERT của IDENTITY.

## 10. Native query có thể làm lỗi ghi xuất hiện tại dòng SELECT

Giả sử database có unique constraint:

```sql
ALTER TABLE books
ADD CONSTRAINT uq_books_title UNIQUE (title);
```

Code:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("Tên đã bị một sách khác dùng");

Object count = em.createNativeQuery(
    "SELECT COUNT(*) FROM books"
).getSingleResult();

em.getTransaction().commit();
```

Nếu query-triggered flush gửi `UPDATE` trước SELECT, database có thể ném constraint violation **ở `getSingleResult()`**, mặc dù SQL SELECT không có lỗi cú pháp.

Tương tự, một query native có thể là điểm biểu hiện của:

- `NOT NULL` violation từ pending INSERT/UPDATE.
- `UNIQUE` violation.
- Foreign key violation.
- Optimistic lock conflict của managed entity.
- Lock timeout hoặc deadlock khi pending SQL được flush.
- Lỗi conversion hoặc constraint check của DB.

Khi debug, phải nhìn **câu SQL ghi được phát ngay trước query**, không kết luận “SELECT đếm làm hỏng dữ liệu”.

### Không chữa lỗi bằng cách đổi AUTO sang COMMIT tùy tiện

`setFlushMode(COMMIT)` có thể làm thay đổi thời điểm biểu hiện lỗi. Nhưng nếu state không hợp lệ, lỗi có thể xuất hiện tại commit hoặc flush sau đó. **Flush mode không sửa được dữ liệu, mapping hay transaction nghiệp vụ đang sai.**

---

## 11. Native UPDATE tạo managed entity stale như thế nào?

Đây là chiều tương tác quan trọng thứ hai.

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
String before = book.getTitle();  // Ví dụ "JPA cơ bản".

int affected = em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, "SQL đã cập nhật")
 .setParameter(2, 42L)
 .executeUpdate();

String after = book.getTitle();

em.getTransaction().commit();
```

Giả sử affected bằng 1. Native SQL đã ghi thay đổi ở DB trong transaction, nhưng `book` vẫn có thể giữ:

```text
book.getTitle() = "JPA cơ bản"
```

vì JPA provider không tự biết câu SQL đã sửa field nào của instance đang managed, trừ khi một cơ chế đồng bộ/invalidation cụ thể của provider xử lý.

Quan trọng:

- `executeUpdate()` thực thi bulk/native DML, không tương đương gọi `book.rename(...)`.
- Không dựa vào `book.getTitle()` để xác nhận tác động native SQL vừa chạy.
- Không mặc định `em.find(Book.class, 42L)` sẽ đọc DB lại nếu Book này đã managed.
- Nếu tiếp tục cập nhật entity stale, có thể tạo xung đột/ghi đè.

### Vì sao `find()` có thể trả dữ liệu cũ?

Persistence context có identity map: trong cùng context, một persistent identity thường có một managed representative.

```java
Book sameBook = em.find(Book.class, 42L);

System.out.println(book == sameBook); // Thường true nếu cùng managed identity.
```

Provider có thể trả object đã quản lý, không phát SQL SELECT mới. Vì vậy `sameBook.getTitle()` có thể vẫn là state cũ, mặc dù DB đã nhận native UPDATE.

**`find()` không phải lệnh “bỏ cache và đọc lại từ database” trong mọi hoàn cảnh.**

## 12. Native SELECT trả scalar mới, getter vẫn cũ

Trong cùng transaction:

```java
Book book = em.find(Book.class, 42L);

em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, "Đã đổi bằng SQL")
 .setParameter(2, 42L)
 .executeUpdate();

String dbTitle = (String) em.createNativeQuery(
    "SELECT title FROM books WHERE id = ?"
).setParameter(1, 42L)
 .getSingleResult();

String objectTitle = book.getTitle();
```

Một kết quả có thể là:

```text
dbTitle     = "Đã đổi bằng SQL"
objectTitle = "JPA cơ bản"
```

Đây **không nhất thiết là lỗi đọc database**. Native scalar query đọc một giá trị từ SQL, còn `book.getTitle()` trả state Java của entity managed. Hai kênh có thể chưa được đồng bộ từ DB về object.

Ví dụ trên giúp chẩn đoán: nếu native scalar SELECT thấy giá trị mới nhưng managed getter vẫn cũ, hãy xem xét **first-level cache/persistence context stale**.

### Không nên coi mọi native SELECT đều trả scalar

```java
em.createNativeQuery("SELECT id, title FROM books")
```

thường trả mỗi hàng là `Object[]` khi không có result mapping đặc biệt. `createNativeQuery(sql, Book.class)` có thể trả managed Book entities. Khi đối chiếu hai kênh đọc, phải biết **result shape**.

Nếu muốn kiểm tra đúng giá trị DB trong ví dụ, scalar `SELECT title` thường rõ ràng hơn dùng entity result vì entity result có thể tái sử dụng managed representative trong context.

## 13. Native query mapping sang entity không nhất thiết làm mới entity cũ

JPA cho phép:

```java
Query query = em.createNativeQuery(
    "SELECT id, version, title, price, published " +
    "FROM books WHERE id = ?",
    Book.class
);

Book nativeBook = (Book) query
    .setParameter(1, 42L)
    .getSingleResult();
```

Giả sử Book #42 đã nằm trong context. Provider phải tôn trọng identity semantics của managed entities. Khi native SQL result mapping trả Book, nó **không có nghĩa tự tạo một Book managed thứ hai cho cùng ID**, cũng không có nghĩa tự refresh mọi state theo đúng dữ liệu DB vừa được native UPDATE sửa.

Vì vậy, nếu cần **đọc lại** state của entity đã managed, đừng coi `createNativeQuery(sql, Book.class)` là một lệnh refresh thay thế.

Có thể:

- Gọi `em.refresh(book)` khi book đang managed và ngữ cảnh phù hợp.
- Kết thúc context cũ rồi mở EntityManager/transaction mới.
- Dùng `em.clear()` có chủ đích sau khi xử lý pending changes, rồi tải entity lại.
- Dùng projection/scalar để đối chiếu giá trị DB, nếu mục tiêu là quan sát chứ không đồng bộ state.

Các lựa chọn này có trade-off khác nhau, sẽ được phân tích cụ thể.

## 14. `refresh()` sau native UPDATE

Nếu một entity đang managed, không còn thay đổi local muốn giữ và cần phản ánh state DB trong object, có thể làm:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);

em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, "Tên mới")
 .setParameter(2, 42L)
 .executeUpdate();

em.refresh(book);

String freshTitle = book.getTitle();

em.getTransaction().commit();
```

Trong transaction với DB state phù hợp, `refresh(book)` yêu cầu provider đọc lại Book và cập nhật managed instance. Giá trị vừa sửa qua native SQL có thể được quan sát qua getter sau refresh.

### Những rủi ro của refresh

- **`refresh()` có thể ghi đè thay đổi local chưa flush** trên entity.
- Entity phải đang managed theo contract phù hợp; detached entity có thể gây `IllegalArgumentException`.
- Nếu row đã bị native DELETE, refresh có thể thất bại vì entity không còn.
- Nếu đang có association lazy/collection hoặc cascade REFRESH, phạm vi tác động cần được hiểu rõ.
- Với cache và isolation, kết quả quan sát phụ thuộc chính sách persistence và DB.
- Nếu transaction đã hỏng/rollback-only, không dùng refresh như cách “hồi sinh” nó.

Ví dụ mất thay đổi:

```java
Book book = em.find(Book.class, 42L);
book.changePrice(new BigDecimal("199000")); // pending local

em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, "Tên SQL")
 .setParameter(2, 42L)
 .executeUpdate();

em.refresh(book); // Có thể loại bỏ thay đổi giá pending!
```

Nếu price cần lưu, phải thiết kế thứ tự flush và refresh rõ ràng, hoặc tách các thao tác thành transaction/context khác nhau.

**Refresh là một quyết định bỏ/đọc lại state, không phải nút đồng bộ vô hại.**

## 15. `clear()` sau native SQL: lợi ích và nguy cơ

`em.clear()` detach **tất cả** entity đang managed trong persistence context:

```java
em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, "Tên SQL")
 .setParameter(2, 42L)
 .executeUpdate();

em.clear();

Book reloaded = em.find(Book.class, 42L);
```

Do context không còn giữ representative cũ, `find()` có thể tải lại state từ DB theo cache/transaction semantics. Đây là cách làm hữu ích trong một số workflow bulk operations.

Nhưng:

```java
Book book42 = em.find(Book.class, 42L);
Book book43 = em.find(Book.class, 43L);

book43.changePrice(new BigDecimal("350000")); // pending

em.clear(); // book43 detached, thay đổi chưa flush có thể bị bỏ!
```

`clear()` không đồng bộ pending changes trước khi detach. Nếu muốn giữ các thay đổi pending, phải xử lý trước khi clear, thường bằng `flush()` trong transaction phù hợp — và phải hiểu việc flush đó sẽ ghi **tất cả thay đổi cần thiết**, không chỉ phần native SQL quan tâm.

### Mẫu dùng có điều kiện

```java
em.getTransaction().begin();

applyManagedChanges(em);
em.flush(); // Những thay đổi muốn giữ được đồng bộ.

int updated = em.createNativeQuery(
    "UPDATE books SET published = true WHERE price > ?"
).setParameter(1, new BigDecimal("200000"))
 .executeUpdate();

em.clear(); // Không còn dự định dùng các managed instances cũ.

List<Book> reloaded = em.createQuery(
    "SELECT b FROM Book b WHERE b.published = true",
    Book.class
).getResultList();

em.getTransaction().commit();
```

Đây là một chiến lược minh họa, không phải yêu cầu phải gọi `flush/clear` sau mọi native query. Nếu trong context có những pending changes không được phép flush ở thời điểm đó, cần tách transaction/context hoặc thiết kế lại.

## 16. `detach()` chỉ tách một entity, không refresh

Thay vì `clear()` toàn bộ, có thể detach một entity cụ thể:

```java
Book old = em.find(Book.class, 42L);

// ... native SQL UPDATE books id=42 ...

em.detach(old);

Book reloaded = em.find(Book.class, 42L);
```

Sau `detach(old)`, `old` vẫn là Java object với state cũ. Nó không tự trở thành state mới, cũng không thể tự động nhận dirty checking từ context vừa tách.

Điều cần lưu ý:

- `detach()` không phải `refresh()`.
- Nó không tự detach mọi associated entity, trừ khi có cấu hình/semantics cascade DETACH phù hợp.
- Nếu còn references từ các entity khác, object graph trong bộ nhớ có thể chứa một số instance detached cùng một số instance managed.
- Nếu code sau đó `merge(old)`, nó có thể copy state stale ngược vào context.

Trong một đơn vị công việc xử lý dữ liệu phức tạp, **context mới sau native bulk DML** thường dễ suy luận hơn việc detach chọn lọc nhiều object rải rác.

## 17. Vì sao `flush()` không làm stale managed entity tự đổi?

Một nhầm lẫn:

```java
Book book = em.find(Book.class, 42L);

em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, "Tên SQL")
 .setParameter(2, 42L)
 .executeUpdate();

em.flush();

String title = book.getTitle();
```

`flush()` đồng bộ **thay đổi trong persistence context xuống database**. Nó không có nhiệm vụ truy vấn lại những cột vừa được native UPDATE làm thay đổi và gán vào `book`.

Vì vậy, `book.getTitle()` vẫn có thể cũ sau `em.flush()`.

Thậm chí flush có thể tạo thêm nguy cơ: nếu `book` bị sửa một field khác, provider có thể phát `UPDATE` từ state managed cũ và vô tình ảnh hưởng cột đã được native SQL sửa.

Quy tắc:

> Khi vấn đề là **DB có dữ liệu mới nhưng managed object vẫn cũ**, hãy nghĩ tới `refresh()`, `clear()` hoặc context mới — không chỉ `flush()`.

Ngược lại, khi vấn đề là **managed object mới nhưng SQL chưa thấy**, hãy nghĩ tới flush mode và `flush()` trước native SELECT.

## 18. Nguy cơ lost update khi trộn native SQL và dirty checking

Giả sử Book #42 ban đầu:

```text
title="A", price=100000, version=3
```

Transaction:

```java
Book book = em.find(Book.class, 42L);

em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, "B")
 .setParameter(2, 42L)
 .executeUpdate();

book.changePrice(new BigDecimal("120000"));

em.flush();
```

Nếu provider phát SQL UPDATE chứa cả title và price từ entity managed (không chỉ cột dirty), nó có thể ghi:

```sql
UPDATE books
SET title = 'A', price = 120000, version = 4
WHERE id = 42 AND version = 3;
```

Lúc đó title vừa được native SQL đổi thành B có nguy cơ bị ghi đè về A.

Nếu provider sử dụng dynamic update chỉ với field dirty, SQL có thể chỉ sửa price/version. Nhưng **không được dựa vào chiến lược dynamic update riêng của provider như cơ chế bảo vệ dữ liệu**.

### Vì sao `@Version` chưa chắc bảo vệ?

Native UPDATE:

```sql
UPDATE books SET title = 'B' WHERE id = 42;
```

thông thường không tăng version tự động theo `@Version`, vì đó là SQL do ứng dụng tự viết. Managed Book vẫn có version 3; provider có thể cho rằng version chưa đổi và UPDATE thành công.

Để tránh mất cập nhật:

1. Không trộn native DML và các thay đổi entity managed trên cùng hàng trong cùng context khi không cần.
2. Nếu phải trộn, xác định thứ tự: `flush()` pending state cần giữ **trước** native DML.
3. Sau native DML, `refresh()` các managed entities liên quan hoặc kết thúc context và đọc lại.
4. Nếu concurrency quan trọng, native SQL phải tự bảo đảm điều kiện version/locking phù hợp.
5. Ưu tiên entity update bình thường nếu nghiệp vụ cần optimistic locking, callbacks, converters/cascade theo lifecycle JPA.

## 19. Native UPDATE và versioning chủ động

Một native update có thể dùng optimistic locking thủ công:

```sql
UPDATE books
SET title = ?, version = version + 1
WHERE id = ? AND version = ?;
```

Trong Java:

```java
int affected = em.createNativeQuery(
    "UPDATE books " +
    "SET title = ?, version = version + 1 " +
    "WHERE id = ? AND version = ?"
).setParameter(1, newTitle)
 .setParameter(2, bookId)
 .setParameter(3, expectedVersion)
 .executeUpdate();

if (affected != 1) {
    throw new OptimisticLockException(
        "Book was modified or does not exist"
    );
}
```

Ví dụ này áp dụng một điều kiện version ở SQL và tăng version khi UPDATE thành công. Nó không có nghĩa mọi business constraint đã được giải quyết. Cần:

- Có transaction phù hợp.
- Kiểm tra `affected` theo semantics của DB/JDBC/provider.
- Xác định phép tăng version tương thích schema và data type.
- Không giữ/tiếp tục dùng managed Book stale trong context cũ.
- Xác nhận optimistic locking và cách update version bằng integration test trên database mục tiêu.

Nếu native DML đã thay version trong DB, managed instance đang giữ version cũ có thể bị xung đột ở flush sau. Đây có thể là **tín hiệu bảo vệ đúng**, nhưng không phải cách “tự refresh” state.

### Native bulk update có bypass callback không?

Native SQL DML không đi qua toàn bộ vòng đời cập nhật managed entity như khi provider dirty-checks một Book rồi phát UPDATE. Vì vậy không giả định:

- `@PreUpdate`/`@PostUpdate` chạy như khi sửa managed entity.
- Cascade hoặc orphanRemoval được xử lý.
- Version được tăng tự động.
- Validation ở Java domain method đã được chạy.
- Trạng thái Java object đã được cập nhật.

Nếu nghiệp vụ dựa vào các hành vi đó, phải dùng cơ chế phù hợp hoặc thiết kế chúng rõ ràng ở SQL/service.

## 20. Native DELETE và entity còn trong persistence context

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);

int deleted = em.createNativeQuery(
    "DELETE FROM books WHERE id = ?"
).setParameter(1, 42L)
 .executeUpdate();

String oldTitle = book.getTitle(); // Object Java vẫn tồn tại.

em.getTransaction().commit();
```

Sau native DELETE, Book #42 có thể không còn hàng trong DB, nhưng object `book` vẫn tồn tại trong heap và có thể vẫn managed theo view của persistence context. Getter của nó không phải phép kiểm tra hàng DB còn tồn tại.

Ngay cả `em.find(Book.class, 42L)` trong cùng context cũng có thể trả lại instance đã managed, thay vì báo null. Nếu ứng dụng tiếp tục sửa entity và flush, provider có thể gặp:

- Entity not found/stale state.
- Optimistic lock conflict.
- Một câu UPDATE ảnh hưởng 0 hàng.
- Exception tùy provider.

### Đọc lại sau delete

Nếu cần xác nhận dữ liệu sau native DELETE:

```java
em.flush(); // Chỉ khi cần lưu pending changes hợp lệ khác.
em.clear();

Book afterDelete = em.find(Book.class, 42L);
```

Hoặc, rõ hơn cho kết quả **đã commit**, kết thúc transaction/context thao tác rồi dùng một EntityManager mới:

```java
EntityManager verifyEm = emf.createEntityManager();

try {
    Book afterDelete = verifyEm.find(Book.class, 42L);
} finally {
    verifyEm.close();
}
```

Lưu ý: Không thêm `em.flush()` sau DELETE như thói quen nếu đang có managed entity stale cần tránh ghi. Chỉ flush khi hiểu rõ pending state. Với native DELETE và dữ liệu liên quan, foreign key constraints/DB cascades có thể quyết định SQL thành công hay thất bại; JPA cascade từ `em.remove(entity)` không tự được kích hoạt bởi câu SQL DELETE tùy ý.

## 21. Native query và các association/collection đang managed

Giả sử Order có collection OrderLine:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

Ứng dụng đã load:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
int before = order.getLines().size();
```

Rồi thực thi:

```java
em.createNativeQuery(
    "DELETE FROM order_lines WHERE order_id = ?"
).setParameter(1, orderId)
 .executeUpdate();
```

Database xóa các hàng OrderLine theo điều kiện, nhưng collection `order.lines` đã load **không tự được làm rỗng**. Nếu nó còn nằm trong persistence context và ứng dụng tiếp tục sử dụng, object graph có thể stale.

Cần hiểu thêm:

- Inverse/owning association mapping không tự sửa relationship Java khi native DML chạy.
- Native DELETE không đi qua `orphanRemoval` như thao tác gỡ child khỏi managed collection.
- Database `ON DELETE CASCADE` cũng không tự xóa Java objects khỏi collection đã load.
- Nếu có second-level cache hoặc collection cache, cần xét chính sách cache invalidation của provider.

### Biện pháp

Nếu toàn bộ graph đã bị ảnh hưởng, thường dễ kiểm soát hơn khi:

1. Flush pending managed changes cần lưu trước native SQL.
2. Thực thi native SQL.
3. Kết thúc transaction/context và dùng context mới để đọc graph, hoặc clear/refresh có mục đích.
4. Tránh merge các detached graphs đã stale vào một context mới.

Nếu thao tác cần cascade/orphanRemoval đúng ngữ nghĩa entity, cân nhắc thao tác qua managed association/service thay vì native DML.

## 22. Cache cấp một và cấp hai

### First-level cache

First-level cache/identity map là thành phần gắn với persistence context. Đây là lý do `em.find()` có thể trả lại managed Book cũ sau native UPDATE.

`em.clear()` làm mất managed state từ context; `em.refresh(book)` có thể cập nhật một managed entity.

### Second-level cache

Second-level cache là shared cache tùy provider/configuration. Native SQL DML hoặc SQL thực hiện ngoài ORM có thể khiến các entry cache không còn khớp DB nếu cơ chế invalidation không được thiết lập phù hợp.

Các chi tiết phụ thuộc:

- Provider và cache strategy.
- Query/cache region.
- Native query được JPA/provider biết ảnh hưởng những bảng nào.
- Cách dữ liệu được cập nhật từ bên ngoài (JDBC, batch job, trigger, ứng dụng khác).
- Transaction completion/invalidation.

Không có một lệnh `clear()` trên EntityManager bảo đảm xóa **toàn bộ** second-level cache cho mọi provider. Nó chủ yếu xử lý persistence context hiện tại.

Nếu cần kiểm soát shared cache, JPA có API `EntityManagerFactory.getCache()` với các thao tác như `evict(...)` và `evictAll()` theo ngữ nghĩa chuẩn, đồng thời provider có thể có API cache riêng. Chỉ evict đúng phạm vi cần thiết; `evictAll()` bừa bãi có thể gây giảm hiệu năng lớn.

### Native scalar SELECT có dùng cache managed entity không?

Nếu query trả scalar từ SQL, nó thường không trả một managed entity qua identity map. Nhưng JDBC/provider query caching, transaction caching hoặc đặc thù provider có thể tác động. Vì vậy khi dùng scalar query để đối chiếu DB, hãy biết mình đang kiểm thử gì và có query cache đặc biệt hay không.

Đối với test tập trung vào database state đã commit, dùng EntityManager/context mới, kiểm soát cache và có thể JDBC độc lập khi cần phân tích sâu.

## 23. Flush trước native DML: thứ tự thao tác an toàn hơn

Một workflow có pending state:

```java
Book bookA = em.find(Book.class, 42L);
bookA.rename("Tên theo nghiệp vụ");

// Sau đó native bulk SQL cập nhật những Book khác:
em.createNativeQuery(
    "UPDATE books SET published = true WHERE price > ?"
).setParameter(1, new BigDecimal("200000"))
 .executeUpdate();
```

Các nguy cơ:

- Pending changes ở Book A có thể ảnh hưởng predicate của native UPDATE (nếu điều kiện phụ thuộc field vừa sửa).
- Provider có thể flush tự động hoặc không theo mode/implementation.
- Bulk SQL có thể tác động Book A hoặc Book khác đang managed.
- Managed entities không tự nhận state mới sau native DML.
- Flush sau đó có thể ghi chồng các thay đổi bulk SQL.

Một thứ tự có chủ đích hơn:

```java
em.getTransaction().begin();

applyManagedChanges(em);

em.flush(); // Bảo đảm pending changes cần lưu được đưa xuống DB.

int updated = em.createNativeQuery(
    "UPDATE books SET published = true WHERE price > ?"
).setParameter(1, new BigDecimal("200000"))
 .executeUpdate();

// Sau bulk DML không tiếp tục dùng managed Book đã tải
// như thể chúng tự phản ánh cờ published mới.

em.clear();

List<Book> publishedBooks = em.createQuery(
    "SELECT b FROM Book b WHERE b.published = true",
    Book.class
).getResultList();

em.getTransaction().commit();
```

Tuy vậy, đây **không phải công thức áp dụng máy móc**. Nếu native SQL có cùng mục tiêu cập nhật một entity đang dirty hoặc thay đổi version, việc flush trước chỉ giải quyết phần đầu; bạn vẫn phải xác định lại context state sau native DML.

### Khi nào nên tách hẳn transaction?

Nếu workflow bao gồm:

1. Nhiều entity operations có cascade/callback.
2. Một native bulk DML lớn.
3. Tiếp tục domain logic trên cùng aggregate.

việc chia thành những đơn vị công việc rõ ràng có thể an toàn hơn. Nhưng chia transaction cũng thay đổi atomicity và consistency, nên chỉ thực hiện khi nghiệp vụ chấp nhận. Không nên tách transaction chỉ để né một lỗi stale state mà làm mất tính nguyên tử cần thiết.

## 24. Vì sao native SQL có thể không nhìn thấy pending changes ngoài joined transaction?

Bảo đảm flush của JPA gắn với trạng thái **persistence context tham gia transaction**. Khi không có joined active transaction, provider không flush pending modifications xuống DB chỉ vì có một query AUTO.

Do đó, phải phân biệt:

```text
A. Active transaction + persistence context joined
   → AUTO có ngữ nghĩa đồng bộ các pending changes liên quan.

B. Không có active/joined transaction
   → Không thể suy query AUTO sẽ tự flush ghi dữ liệu.

C. Transaction có nhưng context unsynchronized chưa join
   → Cần xét joinTransaction() và lifecycle tương ứng.
```

Với application-managed resource-local EntityManager:

```java
em.getTransaction().begin();
try {
    // ... managed changes + query ...
    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
}
```

Với JTA hoặc Spring, transaction được container/framework quản lý theo contract phù hợp. Không sao chép `em.getTransaction()` vào một container-managed JTA EntityManager.

Native SELECT có thể chạy ngoài transaction trong những trường hợp được phép, nhưng điều đó không có nghĩa nó tự commit hoặc tự đồng bộ managed changes của một context không joined.

## 25. Rollback sau native query và trạng thái object Java

Nếu giao dịch gồm:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, 42L);
book.rename("Tên local");

em.flush();

em.createNativeQuery(
    "UPDATE books SET price = ? WHERE id = ?"
).setParameter(1, new BigDecimal("999999"))
 .setParameter(2, 42L)
 .executeUpdate();

em.getTransaction().rollback();
```

Khi rollback thành công, các SQL UPDATE thuộc transaction đó được hoàn tác ở DB. Nhưng object Java `book` vẫn có thể giữ title `"Tên local"`, thậm chí version/state khác so với DB.

Vì thế:

- **Rollback database không phải undo các setters.**
- Sau rollback hoặc lỗi persistence, không tiếp tục dùng entity graph cũ như nguồn dữ liệu đã commit.
- Kết thúc persistence context của đơn vị công việc thất bại; mở context mới và đọc lại nếu cần.
- Không vô điều kiện merge object đã trải qua rollback vì nó có thể chứa thay đổi bị từ chối.
- Nếu cần retry, retry command/DTO trong transaction mới thay vì tái dùng graph stale.

Một câu native SELECT chạy trong transaction trước rollback có thể đã thấy giá trị chưa commit của chính transaction; kết quả đó không chứng minh giá trị được lưu bền vững sau rollback.

## 26. Hai phép kiểm tra khác nhau: trong transaction và sau commit

Khi xây integration test, cần quyết định mình muốn xác minh:

1. **Read-your-writes trong một transaction:** sau flush, native SELECT trong transaction có quan sát thay đổi không?
2. **Database state sau commit:** sau khi transaction kết thúc, một EntityManager mới có thấy dữ liệu đã được commit không?
3. **Managed object stale sau native DML:** cùng một context, getter có còn state cũ không?
4. **Refresh/clear hiệu quả:** sau thao tác làm mới phù hợp, entity được đọc lại có phản ánh thay đổi DB không?
5. **Rollback:** native SQL đã chạy nhưng DB không giữ thay đổi của transaction.

Những mục tiêu này không thể gộp thành một assertion trên `book.getTitle()`.

Ví dụ test chỉ có:

```java
Book book = em.find(Book.class, 42L);
book.rename("Mới");
assertEquals("Mới", book.getTitle());
```

**Không kiểm thử flush hay native SQL**. Nó chỉ chứng minh setter và getter Java hoạt động.

Tương tự:

```java
em.createNativeQuery("UPDATE ...").executeUpdate();
assertEquals("Cũ", book.getTitle());
```

có thể minh họa stale context, nhưng không chứng minh DB đã commit và không chứng minh mapping refresh đúng.

Test cần có fixture, transaction boundaries và quan sát cả hai phía.

## 27. Chuẩn bị integration test với EntityManagerFactory

Giả sử dự án có persistence unit thử nghiệm tên `integration-test`, entity Book đã đăng ký và database/schema tương thích.

Một helper resource-local:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import java.util.function.Function;

public final class JpaTestTransactions {

    private final EntityManagerFactory emf;

    public JpaTestTransactions(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public <T> T inTransaction(
            Function<EntityManager, T> operation) {

        EntityManager em = emf.createEntityManager();
        try {
            em.getTransaction().begin();

            T result = operation.apply(em);

            em.getTransaction().commit();
            return result;
        } catch (RuntimeException ex) {
            if (em.getTransaction().isActive()) {
                try {
                    em.getTransaction().rollback();
                } catch (RuntimeException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
            }
            throw ex;
        } finally {
            em.close();
        }
    }

    public <T> T inFreshContext(
            Function<EntityManager, T> operation) {

        EntityManager em = emf.createEntityManager();
        try {
            return operation.apply(em);
        } finally {
            em.close();
        }
    }
}
```

Các test dưới đây giả định có fixture Book #42 được commit, hoặc một helper seed dữ liệu tạo Book mới và trả về ID. Không nên hardcode ID 42 trong test chạy trên database được chia sẻ; ưu tiên tạo mỗi test một Book với khóa định danh/giá trị riêng.

### Vì sao dùng context khác ở bước assert?

Một test dùng cùng EntityManager để seed, sửa native và assert có thể đọc lại **managed object cũ**, không phải dữ liệu DB sau commit. Khi cần kiểm tra kết quả thực sự, hãy **đóng context thao tác và mở context kiểm chứng mới**.

Nếu dùng Spring `@DataJpaTest`, cần biết các test thường rollback theo mặc định. Khi mục tiêu là kiểm tra sau commit, hãy thiết kế transaction boundaries cụ thể (ví dụ `TestTransaction`, `TransactionTemplate` hoặc test tích hợp ngoài test transaction), không chỉ dựa vào một assert trong context sẽ rollback.

---

## 28. Test A: explicit flush làm native SELECT nhìn thấy thay đổi

Mục tiêu là kiểm thử một điều portable và có ý định rõ: flush trước khi native SELECT trong cùng transaction.

```java
@Test
void nativeSelectReadsManagedChangeAfterExplicitFlush() {
    Long id = seededBookId;

    EntityManager em = emf.createEntityManager();
    try {
        em.getTransaction().begin();

        Book book = em.find(Book.class, id);
        assertNotNull(book);

        book.rename("Book title changed in test");

        em.flush();

        Object raw = em.createNativeQuery(
            "SELECT title FROM books WHERE id = ?"
        ).setParameter(1, id)
         .getSingleResult();

        assertEquals("Book title changed in test", raw);

        em.getTransaction().rollback();
    } finally {
        em.close();
    }
}
```

Điều test chứng minh:

- JPA managed change đã được flush trước native query.
- SQL scalar SELECT trong cùng transaction đọc được giá trị đã được đồng bộ.
- Không cần commit để transaction tự đọc thay đổi của mình.

Điều test **không** chứng minh:

- Nhà cung cấp sẽ luôn flush tự động trước mọi native query.
- Một transaction khác đã nhìn thấy dữ liệu chưa commit.
- Thay đổi sẽ tồn tại sau rollback.
- Native UPDATE sẽ tự làm mới mọi managed entity.

Nếu test này thất bại, cần kiểm tra transaction participation, mapping cột, DB connection, SQL, fixture và flush error trước khi kết luận JPA behavior.

## 29. Test B: quan sát AUTO native SELECT khi có dirty entity

Mục tiêu là hiểu hành vi trên provider đang dùng và bảo đảm kết quả mong muốn trong AUTO:

```java
@Test
void autoNativeQueryAccountsForRelevantPendingChange() {
    Long id = seededBookId;

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();
        em.setFlushMode(FlushModeType.AUTO);

        Book book = em.find(Book.class, id);
        book.rename("Title for native AUTO test");

        Object title = em.createNativeQuery(
            "SELECT title FROM books WHERE id = ?"
        ).setParameter(1, id)
         .getSingleResult();

        assertEquals("Title for native AUTO test", title);

        em.getTransaction().rollback();
    } finally {
        em.close();
    }
}
```

Điều test tập trung vào **kết quả query**. Nó không nên assert một số lượng SQL UPDATE cố định, bởi provider có thể flush theo cách khác, ID strategy có hiệu ứng riêng, hoặc sử dụng những tối ưu hóa không giống nhau giữa versions.

Để phân biệt query-triggered flush với các nguyên nhân khác, bật SQL logging và dùng entity đã tồn tại, sửa field đã quản lý, không dùng `persist()` với IDENTITY làm bằng chứng duy nhất.

### Test COMMIT cần viết thế nào?

Ở `FlushModeType.COMMIT`, không nên viết assertion portable rằng native SELECT **chắc chắn** trả giá trị cũ hoặc mới trước commit. Nếu ứng dụng cần hành vi ổn định, hãy sử dụng flush tường minh rồi assert. Nếu muốn ghi nhận sự khác nhau của provider ở COMMIT, hãy viết một test được gắn rõ với provider/version cụ thể.

## 30. Test C: native UPDATE và getter stale

Mục tiêu: phát hiện việc application lầm tưởng managed object tự được cập nhật.

```java
@Test
void nativeUpdateDoesNotRequireManagedEntityToRefreshItself() {
    Long id = seededBookId;

    EntityManager em = emf.createEntityManager();
    try {
        em.getTransaction().begin();

        Book book = em.find(Book.class, id);
        assertNotNull(book);

        String oldTitle = book.getTitle();
        String sqlTitle = "Updated by native SQL";

        int affected = em.createNativeQuery(
            "UPDATE books SET title = ? WHERE id = ?"
        ).setParameter(1, sqlTitle)
         .setParameter(2, id)
         .executeUpdate();

        assertEquals(1, affected);

        String titleFromDb = (String) em.createNativeQuery(
            "SELECT title FROM books WHERE id = ?"
        ).setParameter(1, id)
         .getSingleResult();

        assertEquals(sqlTitle, titleFromDb);

        // Có thể vẫn là state cũ ở managed object.
        // Không dựa vào getter để chứng minh native SQL đã được đồng bộ.
        System.out.println("Before: " + oldTitle);
        System.out.println("Managed: " + book.getTitle());

        em.refresh(book);

        assertEquals(sqlTitle, book.getTitle());

        em.getTransaction().rollback();
    } finally {
        em.close();
    }
}
```

Test phân biệt:

- `titleFromDb`: native scalar query quan sát database trong transaction.
- `book.getTitle()` trước refresh: managed object có thể stale.
- `book.getTitle()` sau refresh: đối chiếu với DB state theo ngữ nghĩa refresh.

**Đừng viết một assertion cứng yêu cầu mọi provider phải luôn giữ đúng oldTitle trước refresh nếu test nhằm portable**, vì implementation có thể có extension/synchronization behavior riêng. Hãy tập trung vào việc native SQL không cung cấp hợp đồng chung tự cập nhật Java object và kiểm tra refresh khi cần.

## 31. Test D: commit rồi đọc lại từ context mới

Mục tiêu: xác nhận dữ liệu DB cuối cùng sau native UPDATE.

```java
@Test
void nativeUpdateIsVisibleInFreshContextAfterCommit() {
    Long id = seededBookId;
    String expected = "Native committed title";

    JpaTestTransactions tx = new JpaTestTransactions(emf);

    tx.inTransaction(em -> {
        int affected = em.createNativeQuery(
            "UPDATE books SET title = ? WHERE id = ?"
        ).setParameter(1, expected)
         .setParameter(2, id)
         .executeUpdate();

        assertEquals(1, affected);
        return null;
    });

    String title = tx.inFreshContext(em -> {
        Book book = em.find(Book.class, id);
        assertNotNull(book);
        return book.getTitle();
    });

    assertEquals(expected, title);
}
```

Điểm cần phân biệt với Test C: Ở đây một transaction đã commit, context thao tác đã đóng, context đọc mới được tạo. Vì vậy assertion không còn dựa vào managed object cũ.

Nếu second-level cache được bật hoặc database có thao tác ngoài ORM, cần kiểm tra cache invalidation của provider. Với môi trường test cần chứng minh DB state chặt chẽ, có thể dùng JDBC độc lập để đối chiếu và xem chính sách cache.

## 32. Test E: rollback sau native UPDATE

```java
@Test
void rollbackUndoesNativeUpdateInDatabase() {
    Long id = seededBookId;
    String original = readCommittedTitle(id);

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        em.createNativeQuery(
            "UPDATE books SET title = ? WHERE id = ?"
        ).setParameter(1, "Uncommitted title")
         .setParameter(2, id)
         .executeUpdate();

        Object insideTx = em.createNativeQuery(
            "SELECT title FROM books WHERE id = ?"
        ).setParameter(1, id)
         .getSingleResult();

        assertEquals("Uncommitted title", insideTx);

        em.getTransaction().rollback();
    } finally {
        em.close();
    }

    assertEquals(original, readCommittedTitle(id));
}
```

Trong đó `readCommittedTitle` là helper tạo **EntityManager/context mới** và đọc title bằng native SQL hoặc cách xác minh có kiểm soát, sau khi transaction đã kết thúc.

Ý nghĩa:

- Cùng transaction có thể đọc thay đổi chưa commit của mình.
- Rollback thành công hoàn tác thay đổi thuộc transaction.
- Dùng context mới sau rollback để xác nhận DB state.
- Getter trên một entity cũ từ transaction lỗi không phải bằng chứng rollback đã phục hồi object Java.

Không test rollback bằng cách chỉ kiểm tra một field trên entity đã bị sửa trong heap.

## 33. Test F: native DELETE và identity map

Một bài test riêng nên:

1. Seed Book và commit.
2. Mở EntityManager, tải Book vào context.
3. Native DELETE Book trong transaction.
4. Native SELECT `COUNT(*)` để xác nhận hàng đã bị xóa trong transaction.
5. Không coi getter hoặc `find` cùng context là DB check đáng tin.
6. Commit và đóng context.
7. Mở context mới, assert `find(Book.class, id) == null`.

Ví dụ:

```java
@Test
void nativeDeleteRemovesRowAfterCommit() {
    Long id = seedDedicatedBook();

    JpaTestTransactions tx = new JpaTestTransactions(emf);

    tx.inTransaction(em -> {
        Book managedBeforeDelete = em.find(Book.class, id);
        assertNotNull(managedBeforeDelete);

        int deleted = em.createNativeQuery(
            "DELETE FROM books WHERE id = ?"
        ).setParameter(1, id)
         .executeUpdate();

        assertEquals(1, deleted);

        Number rawCount = (Number) em.createNativeQuery(
            "SELECT COUNT(*) FROM books WHERE id = ?"
        ).setParameter(1, id)
         .getSingleResult();

        assertEquals(0L, rawCount.longValue());

        return null;
    });

    boolean gone = tx.inFreshContext(
        em -> em.find(Book.class, id) == null
    );

    assertTrue(gone);
}
```

`seedDedicatedBook()` là fixture helper của test để đảm bảo Book chỉ thuộc test này, tránh ảnh hưởng test khác.

Không nên mở thêm thao tác sửa managed entity đã bị native DELETE sau lệnh DELETE vì có thể làm kết quả commit phụ thuộc flush/optimistic locking state và gây lỗi ngoài phạm vi test.

---

## 34. Kiểm thử cùng persistence context và context mới cho câu hỏi khác nhau

Có hai loại assertion thường bị dùng lẫn.

**Assertion trong cùng context:**

```java
Book book = em.find(Book.class, id);
// Native UPDATE...
String inMemory = book.getTitle();
```

Cho biết trạng thái của **Java managed instance** tại thời điểm đó, không chứng minh DB đã commit.

**Assertion với native scalar query trong cùng transaction:**

```java
String fromSql = (String) em.createNativeQuery(
    "SELECT title FROM books WHERE id = ?"
).setParameter(1, id)
 .getSingleResult();
```

Cho biết kết quả SQL được xử lý trong **transaction hiện tại**; có thể bao gồm dữ liệu chưa commit.

**Assertion sau commit bằng context mới:**

```java
EntityManager verificationEm = emf.createEntityManager();
try {
    Book saved = verificationEm.find(Book.class, id);
} finally {
    verificationEm.close();
}
```

Cho biết state mà context mới nhìn thấy sau transaction trước đã kết thúc, dưới isolation/cache policy hiện hành.

Nếu cần xác minh database physical row độc lập với ORM caches, dùng JDBC/SQL kiểm tra qua connection/transaction riêng theo contract phù hợp.

### Bảng lựa chọn kiểm tra

| Điều muốn chứng minh | Cách kiểm tra phù hợp |
| --- | --- |
| Managed entity được sửa trong heap | Getter trên entity managed |
| Native SELECT nhìn thấy pending change đã flush | Native scalar SELECT cùng transaction sau `flush()` |
| AUTO native query xử lý pending change liên quan | Integration test kết quả + SQL logging trên provider |
| Native UPDATE đã tác động database trong transaction | `executeUpdate()` + native SELECT/COUNT phù hợp |
| Managed entity đã nhận DB state mới | `refresh()` rồi getter, nếu entity/context hợp lệ |
| DB đã commit giá trị mới | Context/transaction mới sau commit |
| Rollback đã hoàn tác DB change | Context mới sau rollback thành công |
| Native DELETE không để lại hàng | Native COUNT + kiểm tra sau commit context mới |
| Provider có flush trước query hay không | SQL logging/statistics, không chỉ getter |
| Cache shared có stale không | Test có kiểm soát cache/provider + context mới/JDBC |

## 35. Quan sát SQL để hiểu thời điểm flush

Một thứ tự có thể gặp khi AUTO flush:

```text
BEGIN
SELECT ... FROM books WHERE id = 42
UPDATE books SET title = ?, version = ? WHERE id = ? AND version = ?
SELECT title FROM books WHERE id = ?
COMMIT
```

Khi SQL UPDATE đã chạy trước SELECT, có thể đây là auto-flush của pending entity state. Nhưng cần xác định xem có `em.flush()` hay update do ID generation hoặc mechanism khác trước đó không.

Tương tác ở chiều ngược có thể:

```text
BEGIN
SELECT ... FROM books WHERE id = 42
UPDATE books SET title = ? WHERE id = ?      -- native
SELECT title FROM books WHERE id = ?         -- scalar thấy title mới
COMMIT
```

Trong trace trên, nếu gọi `book.getTitle()` thấy title cũ thì đó là trạng thái Java object, **không nhất thiết có một câu SELECT khác**. Vì vậy log SQL giúp phân biệt:

- Getter Java trả state cũ.
- JPA `find` dùng first-level cache.
- Native SELECT phát SQL và trả giá trị mới.
- `refresh` phát SQL để cập nhật managed state.

### Tín hiệu cần theo dõi

- Statement order.
- Bound parameter values ở môi trường không lộ dữ liệu nhạy cảm.
- Number of flush operations/statistics nếu provider hỗ trợ.
- Tỷ lệ connection đang active.
- Query count và latency.
- Transaction begin/commit/rollback.
- Optimistic locking/version behavior.
- Cache hit/miss khi có second-level/query cache.

Không nên log toàn bộ thông tin cá nhân, access token hoặc SQL bind parameters nhạy cảm trong production chỉ để debug flush.

## 36. Phân biệt native SELECT, native bulk DML và stored procedure

Các lời gọi có cùng điểm khởi đầu nhưng semantics khác nhau:

```java
em.createNativeQuery("SELECT ...").getResultList();

em.createNativeQuery("UPDATE ...").executeUpdate();

em.createNativeQuery("DELETE ...").executeUpdate();
```

Native SQL có thể gọi stored procedure hoặc database function. Với những thủ tục có side effects, JPA provider có thể không hiểu hết bảng bị ảnh hưởng hoặc số row thực sự được sửa.

Nếu stored procedure:

1. Cập nhật nhiều bảng.
2. Tăng sequence.
3. Ghi audit.
4. Gọi trigger.
5. Trả result set.

thì persistence context có thể stale ở nhiều entity types, không chỉ entity xuất hiện trực tiếp trong câu gọi. Việc lập danh sách các bảng/aggregate bị ảnh hưởng và quyết định khi nào refresh/clear/new context trở nên quan trọng.

### Query SELECT có thật sự read-only?

Một số DB function hoặc stored procedure có thể tạo side effects mặc dù được gọi qua cú pháp SELECT. Không nên lấy tên phương thức `createNativeQuery` làm bằng chứng query chỉ đọc. Xác định semantics từ SQL và database function được sử dụng.

Với những thao tác này, **kiểm thử integration trên DB thực tế** là tuyến bảo vệ quan trọng hơn suy đoán từ API.

## 37. Một chiến lược service giúp tránh trộn state

Giả sử muốn:

1. Sửa Book #42 bằng domain method.
2. Cập nhật hàng loạt các Book khác bằng native SQL.
3. Trả danh sách Book mới nhất sau cập nhật.

Một service resource-local có thể tổ chức rõ các phase:

```java
public List<BookSummary> updateAndRead(
        EntityManagerFactory emf,
        Long bookId,
        String newTitle) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book managed = em.find(Book.class, bookId);

        if (managed == null) {
            throw new IllegalArgumentException("Book not found");
        }

        managed.rename(newTitle);

        // Phase 1: đẩy pending state sang DB.
        em.flush();

        // Phase 2: native DML.
        em.createNativeQuery(
            "UPDATE books SET published = true WHERE price > ?"
        ).setParameter(1, new BigDecimal("200000"))
         .executeUpdate();

        // Phase 3: bỏ managed state có thể stale.
        em.clear();

        // Phase 4: projection đọc kết quả mới.
        List<?> rawRows = em.createNativeQuery(
            "SELECT id, title FROM books " +
            "WHERE published = true ORDER BY id"
        ).getResultList();

        List<BookSummary> result = rawRows.stream()
            .map(raw -> {
                Object[] columns = (Object[]) raw;
                return new BookSummary(
                    ((Number) columns[0]).longValue(),
                    (String) columns[1]
                );
            })
            .toList();

        em.getTransaction().commit();
        return result;
    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            try {
                em.getTransaction().rollback();
            } catch (RuntimeException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
        }
        throw ex;
    } finally {
        em.close();
    }
}

public record BookSummary(long id, String title) {}
```

Đây là **một ví dụ tổ chức trách nhiệm**, không phải khuôn mẫu bắt buộc. Điểm quan trọng là từng phase có ý nghĩa rõ:

- Domain change trên managed entity.
- Flush trước native SQL khi cần kết quả logic chính xác.
- Native SQL thao tác DB trực tiếp.
- Clear khi chấp nhận bỏ managed graph cũ.
- Đọc DTO/scalar mới để không dựa vào entity stale.

Đối với ứng dụng cần entity graph phức tạp, optimistic locking chặt chẽ hoặc nhiều side effects, phải thiết kế versioning, callbacks và transaction isolation phù hợp hơn.

### Mẫu code cần tránh

```java
Book book = em.find(Book.class, id);

book.rename(newTitle);

em.createNativeQuery(
    "UPDATE books SET price = ? WHERE id = ?"
).setParameter(1, newPrice)
 .setParameter(2, id)
 .executeUpdate();

book.publish();

em.getTransaction().commit();
```

Mẫu này trộn **native UPDATE và dirty managed changes trên cùng Book** mà không kiểm soát version/state. Tùy provider và SQL update strategy, có thể ghi đè hoặc tạo xung đột khó hiểu.

## 38. Những sai lầm thường gặp

### Sai lầm 1: “Native SELECT chỉ đọc nên không thể gây flush”

Không đúng. Với AUTO trong joined transaction, provider phải xử lý pending changes liên quan, và flush có thể xảy ra trước query. Provider có thể dùng chiến lược riêng cho native SQL.

### Sai lầm 2: “AUTO chắc chắn flush mọi dirty entity trước mọi SELECT”

Không phải hợp đồng portable. AUTO bảo đảm ngữ nghĩa query, không quy định một danh sách SQL cố định.

### Sai lầm 3: “COMMIT chắc chắn không có SQL ghi trước commit”

Không đúng. `flush()` tường minh, ID generation và các yêu cầu khác có thể phát SQL sớm; tác động pending state lên query ở COMMIT không có bảo đảm như AUTO.

### Sai lầm 4: “Native UPDATE xong, entity managed đã nhận giá trị mới”

Không có bảo đảm chung. Getter có thể stale.

### Sai lầm 5: “Gọi `find()` lại thì chắc chắn SELECT từ DB”

Không đúng với identity map trong cùng persistence context. `find()` có thể trả managed instance đã có.

### Sai lầm 6: “Gọi `flush()` sau native UPDATE sẽ kéo dữ liệu mới lên Java”

Sai chiều đồng bộ. Flush đẩy managed state xuống DB; refresh là thao tác đọc lại cho managed entity.

### Sai lầm 7: “`refresh()` không ảnh hưởng những setter local”

Refresh có thể ghi đè pending local changes. Phải chọn thứ tự và scope có chủ đích.

### Sai lầm 8: “`clear()` chỉ xóa cache mà không làm mất thay đổi chưa flush”

`clear()` detach toàn context; pending changes chưa flush có thể bị bỏ. Không dùng tùy tiện.

### Sai lầm 9: “Native bulk UPDATE tự tăng `@Version`”

Không. SQL tự viết phải kiểm soát version theo nghiệp vụ. `@Version` không tự áp dụng đầy đủ cho mọi native bulk DML.

### Sai lầm 10: “Native DELETE chạy callback và orphanRemoval như `em.remove()`”

Không. Native SQL tác động trực tiếp DB; không tự đi qua mọi cơ chế entity lifecycle.

### Sai lầm 11: “Object Java đã đổi có nghĩa transaction khác thấy dữ liệu mới”

Không. Cần phân biệt setter, flush và commit; visibility phụ thuộc isolation.

### Sai lầm 12: “Rollback sẽ phục hồi field Java sau native DML và flush”

Không. Rollback hoàn tác transaction DB, không tự đảo setter hoặc tái tạo toàn bộ object graph.

### Sai lầm 13: “Second-level cache tự luôn được invalidated đúng với mọi native SQL ngoài ORM”

Phụ thuộc provider/cache strategy và đường cập nhật. Cần kiểm tra cache invalidation, đặc biệt khi có JDBC job hoặc ứng dụng khác.

### Sai lầm 14: “Test dùng cùng EntityManager đủ chứng minh dữ liệu đã commit”

Không. Context có thể trả state managed cũ. Khi kiểm chứng sau commit, dùng context mới.

### Sai lầm 15: “Một lỗi constraint tại native SELECT do SELECT sai”

Có thể là auto-flush của pending UPDATE/INSERT trước SELECT. Hãy xem SQL log và transaction state.

### Sai lầm 16: “Thêm native query synchronization hint là portable giữa Hibernate và mọi JPA provider”

Không. Những hint/API query-space là provider-specific và có thể khác theo version.

### Sai lầm 17: “Một native UPDATE ảnh hưởng một cột thì chắc chắn không ảnh hưởng managed entity khác”

Database triggers, secondary tables, callbacks ở DB và stored procedures có thể ảnh hưởng thêm các hàng/bảng. Xem transaction và DB behavior thực tế.

### Sai lầm 18: “Native scalar SELECT cùng transaction cho biết dữ liệu đã commit”

Không. Nó có thể thấy write chưa commit của chính transaction. Cần kiểm chứng sau commit bằng context mới.

## 39. Bảng chẩn đoán nhanh

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| Getter đã là “Mới”, native SELECT vẫn “Cũ” | Pending state chưa flush hoặc query/transaction khác | Kiểm tra joined transaction, flush mode; explicit flush nếu cần |
| Getter vẫn “Cũ”, native SELECT đã “Mới” | Native DML cập nhật DB, managed instance stale | Refresh managed entity hợp lệ hoặc context mới |
| Native SELECT ném unique constraint error | Auto-flush của pending UPDATE/INSERT | Xem SQL trước SELECT, sửa dữ liệu/mapping, rollback |
| `find()` trả Book đã bị native DELETE | First-level cache identity map | Dùng context mới/clear có chủ đích |
| Giá trị native SQL bị ghi đè lúc commit | Dirty checking từ stale entity | Không trộn DML và managed graph; flush rồi refresh/new context |
| Optimistic lock không phát hiện native update | Native SQL không tăng/kiểm tra version | Thêm version check/update có chủ đích |
| `clear()` làm mất thao tác vừa sửa | Pending changes chưa flush | Chỉ clear khi đã xử lý pending changes |
| Test AUTO khác nhau giữa API Hibernate | JPA EntityManager vs Session/provider configuration | Kiểm tra API/version, SQL logs, synchronized query spaces |
| Native COUNT có giá trị mới trước commit | Query-triggered flush hoặc INSERT sớm | Phân biệt IDENTITY/flush và transaction |
| Kết quả chỉ sai khi bật cache | Shared cache stale/invalidation thiếu | Kiểm tra cache policy và đối chiếu DB |
| Test xanh nhưng production stale | Test chỉ dùng một context hoặc DB khác | Test context mới, DB/driver/provider thực tế |
| Cập nhật ngoài ORM không hiện ngay | Persistence context/cache không biết thay đổi | Refresh/clear/new context, invalidation theo chiến lược |

Bảng này là điểm bắt đầu chẩn đoán, không phải một tập hợp kết luận tự động. Mỗi trường hợp cần xét transaction/SQL chính xác.

## 40. Bài tập suy luận

### Bài 1: Dirty entity và native SELECT

```java
Book book = em.find(Book.class, 42L);
book.rename("B");

Object title = em.createNativeQuery(
    "SELECT title FROM books WHERE id = 42"
).getSingleResult();
```

**Câu hỏi:** Có thể dựa vào getter để kết luận `title` chắc chắn bằng B không?

**Đáp án:** Không. Getter cho biết state Java. Native SELECT đọc database theo semantics flush mode/provider/transaction. Nếu nghiệp vụ bắt buộc đọc thay đổi pending, explicit flush trong joined transaction là ranh giới rõ.

### Bài 2: AUTO và COMMIT

**Câu hỏi:** AUTO có nghĩa “flush mọi thay đổi trước mọi native query” và COMMIT có nghĩa “không hề phát SQL ghi trước commit” không?

**Đáp án:** Không. AUTO bảo đảm thay đổi liên quan được phản ánh khi xử lý query trong context đã tham gia transaction; COMMIT không có bảo đảm query trước commit tương tự. SQL thực tế phụ thuộc provider và tình huống.

### Bài 3: Native UPDATE rồi find

```java
Book b = em.find(Book.class, id);
em.createNativeQuery(
    "UPDATE books SET title = 'C' WHERE id = ?"
).setParameter(1, id)
 .executeUpdate();

Book b2 = em.find(Book.class, id);
```

**Câu hỏi:** `b2.getTitle()` có chắc là C không?

**Đáp án:** Không. `find` có thể trả managed instance cũ từ identity map; `b2 == b` có thể true. Cần refresh hoặc context mới nếu muốn DB state.

### Bài 4: Refresh khi đang dirty

Book đã sửa price bằng setter nhưng chưa flush; native SQL sửa title, rồi gọi `refresh(book)`.

**Câu hỏi:** Điều gì có thể xảy ra với price local?

**Đáp án:** Refresh có thể ghi đè thay đổi local chưa flush. Cần quyết định có flush price trước hay không, hoặc thiết kế thứ tự thao tác khác.

### Bài 5: Clear khi còn managed changes

Một context có 50 Book dirty; native UPDATE một Book rồi gọi `em.clear()`.

**Câu hỏi:** Có rủi ro gì?

**Đáp án:** Clear detach toàn bộ managed entities; các dirty changes chưa flush có thể mất. Cần xử lý pending state trước hoặc tách transaction/context.

### Bài 6: Native bulk SQL và version

```sql
UPDATE books SET title = 'B' WHERE id = 42;
```

Entity Book có `@Version`.

**Câu hỏi:** SQL trên tự tăng version theo `@Version` không?

**Đáp án:** Không. Đây là SQL tự viết; muốn optimistic locking có kiểm soát, phải đưa version predicate/update vào SQL và kiểm tra số hàng ảnh hưởng hoặc dùng managed update.

### Bài 7: Native DELETE và object Java

Native SQL xóa Book #42; biến `book` được tải trước đó vẫn có field/title.

**Câu hỏi:** Điều đó có chứng minh DELETE thất bại không?

**Đáp án:** Không. Object Java vẫn tồn tại độc lập với DB. Xác minh bằng native COUNT và context mới sau commit.

### Bài 8: COUNT sau persist

Ứng dụng `persist(new Book(...))` rồi native COUNT trả tăng thêm một.

**Câu hỏi:** Có chứng minh COUNT đã auto-flush không?

**Đáp án:** Chưa. Với IDENTITY, INSERT có thể chạy sớm để lấy khóa. Cần SQL log và một test có mục tiêu khác nếu muốn xác định trigger flush.

### Bài 9: Constraint xuất hiện khi query

Native SELECT ném lỗi unique constraint sau khi sửa title trên managed entity.

**Câu hỏi:** Root cause có thể ở đâu?

**Đáp án:** Pending UPDATE được auto-flush trước SELECT và vi phạm unique constraint. Cần xem SQL log, sửa dữ liệu và rollback transaction thất bại.

### Bài 10: Commit và isolation

Transaction A flush Book title=B; transaction B đọc hàng trước khi A commit.

**Câu hỏi:** B chắc chắn thấy B không?

**Đáp án:** Không. Visibility phụ thuộc DB isolation/locking và transaction completion. Flush không phải commit.

### Bài 11: Kiểm thử readback

Test chỉ gọi `book.getTitle()` sau native UPDATE và assert bằng title mới.

**Câu hỏi:** Nếu test pass, có chắc DB đã commit không?

**Đáp án:** Không. Assertion ở getter không chứng minh transaction đã commit. Dùng context mới sau commit để kiểm tra DB state.

### Bài 12: SQL chạy ngoài EntityManager

Một JDBC job khác sửa Book; EntityManager hiện tại đã load Book trước khi job commit.

**Câu hỏi:** Làm thế nào để có state mới?

**Đáp án:** Sau khi giao dịch bên ngoài commit, cần refresh entity hợp lệ hoặc tạo context mới, đồng thời xem second-level cache/transaction isolation. Không suy rằng managed instance tự nhận update từ job.

### Bài 13: Session-specific native query

Một ví dụ Hibernate `Session.createNativeQuery` không flush trước query, trong khi ví dụ dùng JPA EntityManager lại flush.

**Câu hỏi:** Có mâu thuẫn không?

**Đáp án:** Không nhất thiết. API, phiên bản, query synchronization hints và flush mode có thể tạo khác biệt. Phải đọc contract provider hiện dùng và kiểm chứng bằng SQL logging.

### Bài 14: Bulk DELETE và orphanRemoval

Native SQL:

```sql
DELETE FROM purchase_orders WHERE id = ?;
```

**Câu hỏi:** JPA `orphanRemoval = true` trên Order.lines có tự chạy như `em.remove(order)` không?

**Đáp án:** Không. Native DELETE không phải entity lifecycle removal. Nếu DB không có cascade FK, có thể bị constraint violation; nếu có DB cascade, Java object graph cũng không tự được cập nhật.

### Bài 15: Chọn chiến lược an toàn

Bạn cần sửa Book theo domain method, chạy native bulk UPDATE, rồi trả dữ liệu mới nhất cho client.

**Gợi ý đáp án:** Xác định transaction boundary; flush managed changes cần giữ trước bulk DML; chạy native SQL; bỏ/refresh managed state có thể stale (hoặc dùng context mới); đọc DTO/scalar phù hợp; commit và kiểm tra kết quả sau commit nếu cần. Không tiếp tục merge/flush graph cũ tùy tiện.

## 41. Checklist trước khi kết hợp native SQL với JPA managed entities

1. **Có entity managed đang dirty không?** Những field/association nào đang pending?
2. **Native SQL thuộc SELECT, UPDATE, DELETE hay procedure có side effects?**
3. **Query có thể phụ thuộc những thay đổi pending nào?**
4. **Persistence context đã tham gia active transaction chưa?**
5. **Flush mode là AUTO hay COMMIT? Query có flush mode riêng không?**
6. **Ứng dụng dùng JPA EntityManager hay provider-specific Session/API?**
7. **Có cần explicit `flush()` trước native SELECT/DML để bảo đảm ngữ nghĩa không?**
8. **Native query có sử dụng view/function/trigger nên khó phân tích query spaces không?**
9. **Có thể có INSERT sớm vì `GenerationType.IDENTITY` không?**
10. **Native DML có tác động tới một entity đang managed trong context không?**
11. **Có pending changes nào có thể bị native DML ghi đè hoặc ngược lại không?**
12. **`@Version` có được native DML kiểm tra/tăng theo chính sách không?**
13. **Có callbacks/cascade/orphanRemoval mà native SQL sẽ bỏ qua không?**
14. **Có association collections stale sau native DML không?**
15. **Nên `refresh()` entity cụ thể, `detach()`, `clear()` hay dùng context mới?**
16. **Nếu gọi `clear()`, có còn pending changes quan trọng chưa flush không?**
17. **Nếu gọi `refresh()`, có local changes nào bị ghi đè không?**
18. **Native query có trả scalar/Object[] hay entity mapped?**
19. **Nếu trả entity mapped, có đang tái sử dụng managed instance cũ không?**
20. **Có second-level/query cache cần invalidation theo provider không?**
21. **Transaction khác hoặc JDBC job ngoài ORM có thể sửa cùng hàng không?**
22. **Transaction isolation có ảnh hưởng việc đọc dữ liệu mới không?**
23. **Có bắt exception và rollback sau auto-flush failure đúng cách không?**
24. **Đã kiểm tra SQL order và bind values trong môi trường an toàn chưa?**
25. **Có integration test kết quả trong transaction và context mới sau commit không?**
26. **Có test rollback để tránh nhầm flush với commit không?**
27. **Có test native UPDATE/DELETE khi entity đã được load vào identity map không?**
28. **Có test optimistic locking/lost update ở cạnh tranh đồng thời không?**
29. **Có kiểm thử với database, JDBC driver và provider giống production không?**
30. **Business service đã mô tả rõ ownership và transaction của từng pha chưa?**

Checklist không yêu cầu phải gọi `flush()`, `refresh()` hay `clear()` sau mọi query. Mục tiêu là chọn ranh giới đồng bộ dựa trên **tình trạng context và ngữ nghĩa thực sự của thao tác**.

## Kết luận

Native SQL cung cấp quyền truy cập trực tiếp tới khả năng của database, nhưng khi chạy bên cạnh JPA managed entities, nó tạo **hai chiều đồng bộ cần được kiểm soát**.

**Chiều thứ nhất:** entity được sửa trong persistence context nhưng chưa flush. Native SELECT đọc dữ liệu theo flush mode, transaction và provider; với AUTO trong joined transaction, những pending changes ảnh hưởng kết quả phải được xử lý phù hợp. Nếu nghiệp vụ cần native query nhìn thấy thay đổi một cách tường minh, `em.flush()` trước query là ranh giới rõ ràng. Nhưng **flush không phải commit**.

**Chiều thứ hai:** native UPDATE/DELETE ghi trực tiếp vào database, còn managed entity trong persistence context có thể giữ giá trị cũ. `flush()` không giải quyết chiều đồng bộ này; cần dùng `refresh()`, `clear()`, detach phù hợp hoặc một persistence context mới để đọc state mới. Những thao tác đó phải xét các local changes chưa flush, tránh mất dữ liệu hoặc merge lại graph stale.

Với dữ liệu quan trọng, đặc biệt khi có `@Version`, association/cascade, second-level cache hoặc transaction đồng thời, không được trộn native DML và dirty checking trên cùng entity mà thiếu chiến lược rõ. Native SQL tự viết không tự kế thừa mọi lifecycle callbacks và optimistic-locking behavior của cập nhật JPA thông thường.

Cách kiểm tra đáng tin cậy là **tách các phép quan sát**: getter cho biết object Java, native scalar SELECT cho biết kết quả SQL trong transaction, còn EntityManager/context mới sau commit cho biết trạng thái được lưu theo transaction và cache policy. Kết hợp các phép quan sát này với SQL logging và integration test trên database/provider thực tế sẽ giúp phát hiện sớm dữ liệu stale, flush ngoài dự kiến, lost update và lỗi rollback.

Khi đứng trước một native query, hãy hỏi: **“Những thay đổi nào đang chờ được đẩy xuống DB? Native SQL đã thay đổi những hàng nào trong DB? Managed entity nào có thể đang giữ state cũ? Và tôi đã xác minh kết quả ở đúng transaction/context chưa?”**. Trả lời được bốn câu hỏi ấy là nền tảng để sử dụng native SQL và JPA persistence context an toàn.
