# Giới hạn số hàng, fetch size JDBC và kích thước trang không phải một khái niệm

Một ứng dụng Hibernate/JPA có thể cùng lúc sử dụng ba con số:

~~~java
query.setMaxResults(100);
hibernateQuery.setFetchSize(200);
PageRequest pageRequest = PageRequest.of(2, 20);
~~~

Nhìn bề ngoài, cả ba đều liên quan đến “số hàng được lấy”, nhưng **chúng trả lời ba câu hỏi khác nhau**:

- **Giới hạn số hàng** (*result limit*, thường dùng `setMaxResults` hoặc SQL `LIMIT`): tối đa **bao nhiêu kết quả** thuộc truy vấn được trả về?
- **JDBC fetch size** (`Statement.setFetchSize` hoặc Hibernate `Query.setFetchSize`): driver được **gợi ý lấy bao nhiêu hàng trong một đợt truyền dữ liệu** khi đọc `ResultSet`?
- **Kích thước trang** (*page size*, như `PageRequest.of(pageNumber, pageSize)`): ứng dụng muốn **mỗi trang có tối đa bao nhiêu phần tử**, đồng thời cần xác định trang nào, thứ tự nào và có cần tổng số bản ghi không?

Nếu nhầm ba khái niệm này, ứng dụng dễ gặp các lỗi: tưởng `setFetchSize(100)` sẽ chỉ trả 100 kết quả; tưởng phân trang 20 phần tử thì JDBC chắc chắn chỉ lấy 20 hàng mỗi round trip; hoặc dùng fetch join collection với `setMaxResults(20)` và phát hiện Hibernate tải rất nhiều hàng rồi mới phân trang trong bộ nhớ.

Bài học thuộc chương **Kết quả và phân trang** trong module *Data Persistence Relational Access ORM Hibernate*. Ví dụ dùng Java, Jakarta Persistence, Hibernate ORM, JDBC, Spring Data JPA và SQL minh họa trên PostgreSQL. Hành vi driver, SQL dialect và một số API thay đổi theo phiên bản; những chỗ đó được lưu ý riêng.

## 1. Sơ đồ tư duy ba tầng

Hãy hình dung một truy vấn có thể khớp 100.000 hàng trong bảng `products`.

~~~text
                           DATABASE
                     100.000 hàng phù hợp
                                |
             +------------------+------------------+
             |                                     |
     Result limit / OFFSET                  Truy vấn không limit
       (SQL LIMIT 40)                         (100.000 hàng)
             |                                     |
       Tập kết quả logic                       Tập kết quả logic
       tối đa 40 hàng                         100.000 hàng
             |                                     |
             +---------------+---------------------+
                             |
                     JDBC ResultSet
                             |
                   fetchSize: gợi ý
                ví dụ 10, 50 hoặc 200
              hàng mỗi đợt đọc nếu driver
                hỗ trợ cơ chế tương ứng
                             |
                  Java / Hibernate
                             |
             +---------------+---------------+
             |                               |
      getResultList()                  stream() / scroll()
       materialize list                 xử lý tăng dần
             |
         Trang UI
       pageSize = 20
~~~

Đây là **sơ đồ khái niệm**, không phải cam kết rằng mọi driver luôn phân lô theo đúng fetch size hoặc rằng mọi limit đều được đẩy xuống SQL trong mọi trường hợp. Đặc biệt, collection fetch join có thể khiến giới hạn Hibernate bị áp dụng trong memory.

Ba con số tác động đến các tầng khác nhau:

| Cơ chế | Tầng tác động chính | Có giới hạn tổng kết quả không? | Có định nghĩa trang không? |
| --- | --- | --- | --- |
| `setMaxResults(40)` | JPA/Hibernate query và thường SQL | Có, tối đa 40 kết quả truy vấn | Chưa; cần offset/sort nếu muốn trang |
| SQL `LIMIT 40` | Database SQL | Có, tối đa 40 hàng SQL | Chưa; cần offset/cursor/sort |
| `Statement.setFetchSize(40)` | JDBC driver/ResultSet | **Không** | **Không** |
| Hibernate `Query.setFetchSize(40)` | Chuyển hint xuống JDBC | **Không** | **Không** |
| `PageRequest.of(2, 20)` | Spring Data/API pagination | Có, một trang tối đa 20 phần tử | Có, trang số 2 và page size 20 |
| SQL `OFFSET 40 LIMIT 20` | Database | Tối đa 20 hàng SQL sau offset | Biểu diễn trang offset nếu có sort ổn định |

**Quy tắc ngắn gọn:** *Limit quyết định số kết quả; fetch size điều chỉnh cách vận chuyển kết quả; page size quyết định cách ứng dụng chia kết quả thành trang.*

## 2. Mô hình dữ liệu minh họa

Giả sử bảng sản phẩm:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    category VARCHAR(60) NOT NULL,
    price NUMERIC(15, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_products_created_id
    ON products(created_at DESC, id DESC);
~~~

Entity:

~~~java
@Entity
@Table(name = "products")
public class Product {
    @Id
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private String category;

    @Column(nullable = false)
    private BigDecimal price;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public String getName() {
        return name;
    }
}
~~~

Trong ví dụ, code có import tương ứng từ `jakarta.persistence`, `java.math` và `java.time`. Các field khác, constructor nghiệp vụ hoặc validation không phải trọng tâm bài học.

Giả sử truy vấn không giới hạn:

~~~jpql
select p
from Product p
where p.category = :category
order by p.createdAt desc, p.id desc
~~~

có thể khớp hàng chục nghìn sản phẩm. Tùy mục đích, ta sẽ chọn result limit, fetch size hoặc pagination khác nhau.

## 3. Giới hạn số hàng với JPA `setMaxResults`

Jakarta Persistence có phương thức:

~~~java
TypedQuery<Product> query = em.createQuery(
    """
    select p from Product p
    where p.category = :category
    order by p.createdAt desc, p.id desc
    """,
    Product.class
);

List<Product> products = query
    .setParameter("category", "BOOK")
    .setMaxResults(100)
    .getResultList();
~~~

`setMaxResults(100)` yêu cầu query trả **tối đa 100 kết quả**. Nếu chỉ có 37 sản phẩm phù hợp, kết quả có thể gồm 37 phần tử. Không có bảo đảm rằng chính xác 100 phần tử sẽ xuất hiện.

Thông thường, Hibernate chuyển giới hạn này thành cú pháp giới hạn của database như `LIMIT`, `FETCH FIRST` hoặc cơ chế tương đương. Ví dụ SQL minh họa:

~~~sql
SELECT p.*
FROM products p
WHERE p.category = ?
ORDER BY p.created_at DESC, p.id DESC
LIMIT 100;
~~~

SQL chính xác phụ thuộc dialect. Không phải Hibernate bắt buộc sinh chuỗi `LIMIT 100` trên mọi database.

### `setMaxResults` không quyết định thứ tự

Đây là code hợp lệ về cú pháp:

~~~java
query.setMaxResults(100);
~~~

Nhưng nếu query không có `ORDER BY`, 100 sản phẩm nào được trả về có thể phụ thuộc kế hoạch thực thi, index, tình trạng dữ liệu hoặc các thay đổi khác. Không có thứ tự mặc định để dựa vào.

Với kết quả giới hạn dùng trong nghiệp vụ, nên xác định ordering rõ ràng:

~~~jpql
order by p.createdAt desc, p.id desc
~~~

ID là khóa phụ giúp thứ tự ổn định khi nhiều sản phẩm có cùng `createdAt`.

### `setMaxResults(100)` có liên quan JDBC fetch size không?

Không trực tiếp. Nó đặt giới hạn số kết quả. Driver có thể dùng fetch size 0, 50 hoặc 500 theo cấu hình mà result limit vẫn là 100. Fetch size lớn hơn limit không có nghĩa ứng dụng sẽ trả 500 kết quả.

## 4. `setFirstResult`: điểm bắt đầu trong danh sách kết quả

JPA hỗ trợ offset của query result:

~~~java
List<Product> products = em.createQuery(
    """
    select p from Product p
    where p.category = :category
    order by p.createdAt desc, p.id desc
    """,
    Product.class
)
.setParameter("category", "BOOK")
.setFirstResult(40)
.setMaxResults(20)
.getResultList();
~~~

Ý nghĩa:

- `setFirstResult(40)`: bỏ qua 40 kết quả đầu tiên theo thứ tự query.
- `setMaxResults(20)`: trả tối đa 20 kết quả tiếp theo.
- Vị trí kết quả đầu tiên trong JPA được đánh số **0**, không phải 1.

Với dialect hỗ trợ LIMIT/OFFSET:

~~~sql
SELECT p.*
FROM products p
WHERE p.category = ?
ORDER BY p.created_at DESC, p.id DESC
OFFSET 40 ROWS
FETCH NEXT 20 ROWS ONLY;
~~~

Đây là minh họa SQL; PostgreSQL cũng hỗ trợ cú pháp `LIMIT 20 OFFSET 40`.

Cặp `firstResult + maxResults` thường được dùng để thực hiện offset pagination.

## 5. Tính toán trang: page number khác page size

Giả sử hệ thống hiển thị 20 sản phẩm mỗi trang, đánh số trang từ 0:

| Page number | Page size | Offset | Kết quả theo thứ tự 1-based |
| ---: | ---: | ---: | --- |
| 0 | 20 | 0 | 1–20 |
| 1 | 20 | 20 | 21–40 |
| 2 | 20 | 40 | 41–60 |
| 3 | 20 | 60 | 61–80 |
| 4 | 20 | 80 | 81–100 |

Công thức:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

Với page number 2 và page size 20:

\[
\text{offset} = 2 \times 20 = 40
\]

Java:

~~~java
int pageNumber = 2;
int pageSize = 20;

int offset = Math.multiplyExact(pageNumber, pageSize);

List<Product> page = em.createQuery(
    "select p from Product p order by p.createdAt desc, p.id desc",
    Product.class
)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
~~~

`Math.multiplyExact` giúp phát hiện overflow khi tính offset trên kiểu `int`. Trong ứng dụng thực, cần validate pageNumber không âm, pageSize dương, giới hạn size tối đa và xử lý offset vượt khả năng JDBC/JPA API.

**Page size 20 không phải fetch size 20.** Nó chỉ nói một trang cần bao nhiêu kết quả.

## 6. Page size trong Spring Data JPA

Spring Data dùng `Pageable` và `PageRequest` để biểu diễn yêu cầu phân trang:

~~~java
Pageable pageable = PageRequest.of(
    2,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
~~~

Ý nghĩa:

- Page index là 2, bắt đầu từ 0.
- Page size là 20.
- Sắp xếp theo `createdAt DESC`, rồi `id DESC`.
- Offset tương ứng là 40.

Repository minh họa:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Page<Product> findByCategory(
        String category,
        Pageable pageable
    );
}
~~~

Sử dụng:

~~~java
Pageable pageable = PageRequest.of(
    2,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<Product> page =
    productRepository.findByCategory("BOOK", pageable);

List<Product> items = page.getContent();

int requestedPageSize = page.getSize();
int actualNumberOfElements = page.getNumberOfElements();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

Điểm cần phân biệt:

- `page.getSize()` là **kích thước trang được yêu cầu**.
- `page.getNumberOfElements()` là **số phần tử thực sự có trong trang này**.
- `page.getTotalElements()` là **tổng số phần tử phù hợp toàn bộ truy vấn**, không phải số hàng của trang.
- `page.getTotalPages()` là tổng số trang theo size hiện tại.
- `page.getContent()` chứa những entity/projection thuộc trang trả về.

Nếu một trang cuối chỉ còn 7 kết quả, `getSize()` vẫn có thể là 20, còn `getNumberOfElements()` là 7.

## 7. `Page`, `Slice` và `List`: kết quả phân trang không giống nhau

Trong Spring Data, repository có thể trả ba kiểu phổ biến.

| Kiểu trả về | Dữ liệu | Metadata | Count query |
| --- | --- | --- | --- |
| `Page<T>` | Content trang | Page number, size, total elements/pages, hasNext | Có thể cần query đếm tổng |
| `Slice<T>` | Content trang | Có trang kế tiếp không, không có total chính xác | Thường không cần đếm tổng |
| `List<T>` với `Pageable` | Danh sách theo khoảng yêu cầu | Không mang metadata trang | Thường không cần query đếm tổng |

Ví dụ:

~~~java
Page<Product> findByCategory(
    String category,
    Pageable pageable
);

Slice<Product> findByNameContaining(
    String keyword,
    Pageable pageable
);

List<Product> findByPriceGreaterThan(
    BigDecimal amount,
    Pageable pageable
);
~~~

Đây là ba ví dụ method signature được đặt trong repository interface; khi viết mã thật cần tránh hai overload có cùng tên/signature bất hợp lý và cấu hình Spring Data đúng.

### Vì sao `Page` có thể tốn hơn `Slice`?

Để biết tổng số hàng, Spring Data có thể phải thực thi một câu count query:

~~~sql
SELECT COUNT(*)
FROM products
WHERE category = ?;
~~~

Nếu dataset lớn và điều kiện phức tạp, count có thể tốn đáng kể. Spring Data có thể tối ưu bỏ count trong một số tình huống suy ra được tổng, nên không phải mọi `Page` luôn phát đúng hai query.

`Slice` thường kiểm tra có trang kế tiếp bằng cách lấy nhiều hơn page size một phần tử, ví dụ pageSize + 1. Khi pageSize = 20, infrastructure có thể yêu cầu 21 kết quả để xác định `hasNext()`, rồi chỉ trả tối đa 20 trong content.

**Page size vẫn là 20**, dù một truy vấn nội bộ có thể đọc thêm một hàng để biết có trang sau.

## 8. Bản chất của JDBC fetch size

JDBC chuẩn định nghĩa:

~~~java
statement.setFetchSize(200);
~~~

Phương thức `java.sql.Statement.setFetchSize(int)` chỉ cung cấp **một hint cho JDBC driver**: khi cần thêm dữ liệu cho `ResultSet`, hãy cân nhắc lấy khoảng 200 hàng trong một đợt.

Nó **không** có ý nghĩa:

- Chỉ SELECT tối đa 200 hàng.
- Ngừng ResultSet sau khi đọc 200 hàng.
- Tự động chia API response thành các trang 200 phần tử.
- Tự động thêm `LIMIT 200` vào SQL.
- Bảo đảm luôn có đúng 200 hàng trong mỗi network packet.
- Bảo đảm memory consumption bị chặn ở 200 entity.

JDBC cho phép driver quyết định có làm theo hint hay không. Một số driver dùng cursor/server-side fetching; driver khác có thể tải toàn bộ result set vào client trước khi application code bắt đầu duyệt.

### Fetch size bằng 0

Theo JDBC API, `setFetchSize(0)` nghĩa là bỏ qua hint, sử dụng hành vi mặc định của driver. Không nên hiểu nó là “lấy 0 hàng”.

Ví dụ:

~~~java
statement.setFetchSize(0);
// Driver dùng fetch policy mặc định.
~~~

Với giá trị âm, hợp đồng `Statement.setFetchSize` chuẩn yêu cầu không hợp lệ; một số driver có extension dùng giá trị đặc biệt cho streaming, nhưng đó không phải quy ước portable của JDBC.

### Các yếu tố driver quyết định

- Có hỗ trợ server-side cursor không?
- Có yêu cầu transaction đang hoạt động không?
- ResultSet có phải forward-only không?
- Statement có phải prepared statement không?
- Kết nối có dùng protocol/cấu hình cho cursor không?
- Driver có cho prefetch nhiều hàng vào client buffer không?
- Query có phù hợp cursor/streaming không?
- Độ rộng hàng, network latency và kích thước buffer ra sao?

Vì vậy cần kiểm tra trên **JDBC driver và database thực tế**, không chỉ đọc code có `setFetchSize(200)`.

## 9. JDBC thực hành: đọc nhiều hàng theo fetch size

Ví dụ JDBC thuần:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         """
         SELECT id, sku, name
         FROM products
         ORDER BY id
         """
     )) {

    statement.setFetchSize(200);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            String sku = rs.getString("sku");
            String name = rs.getString("name");

            consumeProduct(id, sku, name);
        }
    }
}
~~~

Trong code trên, `consumeProduct` được hiểu là hàm xử lý một hàng và không lưu giữ vô hạn dữ liệu. `setFetchSize(200)` không giới hạn tổng số lần vòng lặp `rs.next()`.

Nếu query khớp 100.000 hàng và driver sử dụng fetch size 200 như kích thước block, vòng lặp vẫn có thể chạy **100.000 lần**. Driver có thể cần nhiều đợt truyền dữ liệu để cung cấp các hàng tiếp theo.

Nhưng vì fetch size chỉ là hint, số round trip và buffer thực tế không thể suy ra chính xác bằng cách lấy 100.000 chia cho 200.

### Vì sao fetch size thường liên quan tới streaming?

Khi xử lý nhiều hàng, fetch size hợp lý có thể giúp driver tránh materialize toàn bộ result set ở phía client một lần. Tuy nhiên, **streaming chỉ thực sự có lợi nếu cách đọc, transaction và persistence context cũng không tích lũy toàn bộ dữ liệu**.

Nếu vòng lặp liên tục thêm từng object vào một `ArrayList` vô hạn, lợi ích bộ nhớ của cursor sẽ bị triệt tiêu ở application layer.

## 10. PostgreSQL JDBC: fetch size có điều kiện để mở cursor

Với PostgreSQL JDBC driver (*pgJDBC*), việc fetch tăng dần bằng cursor có các điều kiện quan trọng:

- Connection phải ở trong transaction phù hợp, thường **auto-commit tắt**.
- Statement/ResultSet phải cho phép duyệt forward-only.
- Query phải phù hợp với cursor; ví dụ không phải nhiều statement ghép trong một lời gọi.
- Fetch size nên là số dương để driver cân nhắc cursor fetching.
- Driver có thể fallback về lấy toàn bộ result set nếu điều kiện cursor không được đáp ứng.

Ví dụ JDBC thuần, nơi ứng dụng **tự quản lý transaction**:

~~~java
try (Connection connection = dataSource.getConnection()) {
    boolean oldAutoCommit = connection.getAutoCommit();

    try {
        connection.setAutoCommit(false);

        try (PreparedStatement statement =
                 connection.prepareStatement(
                     """
                     SELECT id, sku, name
                     FROM products
                     ORDER BY id
                     """,
                     ResultSet.TYPE_FORWARD_ONLY,
                     ResultSet.CONCUR_READ_ONLY
                 )) {

            statement.setFetchSize(200);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    consumeProduct(
                        rs.getLong("id"),
                        rs.getString("sku"),
                        rs.getString("name")
                    );
                }
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    } finally {
        connection.setAutoCommit(oldAutoCommit);
    }
}
~~~

Đoạn này nhằm minh họa cursor fetching trong JDBC thuần và đơn giản hóa việc phục hồi connection state. Trong ứng dụng production, nếu rollback hoặc connection bị hỏng, phần cleanup có thể phát sinh ngoại lệ bổ sung; cần một connection/transaction management policy đầy đủ.

**Không copy `connection.setAutoCommit(false)` vào trong một Hibernate/Spring transaction đã được quản lý.** Nếu dùng Hibernate Session, hãy bắt đầu transaction bằng `Session.beginTransaction()` hoặc `@Transactional` rồi để Hibernate quản lý JDBC connection.

### Vì sao auto-commit quan trọng?

Trong PostgreSQL, cursor gắn với database transaction. Nếu auto-commit khiến transaction kết thúc ngay khi statement hoàn thành, server-side cursor có thể không còn tồn tại để driver fetch các block tiếp theo. Vì vậy chỉ đặt fetch size mà không có transaction phù hợp thường **không tạo cursor fetching** như mong đợi.

## 11. MySQL Connector/J: fetch size phụ thuộc cấu hình driver

MySQL Connector/J có cơ chế streaming/cursor riêng. Với **cursor-based fetching**, driver có thể cần:

- `useCursorFetch=true`.
- Fetch size dương trên statement, hoặc cấu hình default fetch size.
- Server-side prepared statement theo quy tắc Connector/J; driver có thể bật cơ chế cần thiết khi sử dụng cursor fetching.
- Hành vi đúng theo phiên bản Connector/J và server.

Ví dụ cấu hình kết nối minh họa:

~~~properties
jdbc:mysql://localhost:3306/shop?useCursorFetch=true
~~~

Sau đó:

~~~java
try (PreparedStatement statement = connection.prepareStatement(
         "SELECT id, name FROM products"
     )) {

    statement.setFetchSize(200);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            // Xử lý từng hàng.
        }
    }
}
~~~

Không mặc định rằng chỉ `setFetchSize(200)` là đủ trên mọi cấu hình MySQL. Connector/J còn có những chế độ streaming riêng và các extension giá trị fetch size, nhưng chúng **không phải hành vi chuẩn JDBC**, nên phải xem hướng dẫn đúng driver/version thay vì sao chép các “mẹo” từ dự án khác.

### Không đặt một quy tắc cho mọi JDBC driver

| Driver/database | Điều cần xác nhận |
| --- | --- |
| PostgreSQL JDBC | Transaction không auto-commit, forward-only cursor, fetch size dương |
| MySQL Connector/J | Cấu hình cursor/streaming, prepared statements, driver version |
| Oracle JDBC | Row prefetch/fetch size và bộ nhớ driver |
| SQL Server JDBC | Buffering/streaming behavior, response buffering, cursor support |
| Driver khác | Hợp đồng driver cụ thể về `setFetchSize` |

Tên và khả năng cụ thể có thể thay đổi theo phiên bản; bảng này chỉ là checklist thiết kế, không khẳng định mọi driver hoạt động một cách duy nhất.

## 12. Hibernate `setFetchSize` là một hint được chuyển xuống JDBC

Hibernate cung cấp API trên query:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        SelectionQuery<Product> query =
            session.createSelectionQuery(
                """
                select p from Product p
                where p.category = :category
                order by p.id
                """,
                Product.class
            );

        query.setParameter("category", "BOOK");
        query.setFetchSize(200);

        List<Product> products = query.getResultList();

        processProducts(products);

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

`org.hibernate.query.SelectionQuery.setFetchSize(200)` truyền **JDBC fetch size hint** xuống statement mà Hibernate dùng để chạy query. Nó **không thay thế** `setMaxResults`.

Phần lớn ví dụ Hibernate 6.x dùng `SelectionQuery` hoặc `org.hibernate.query.Query`; API cụ thể thay đổi theo phiên bản. Với phiên bản mới, hãy ưu tiên selection-query API phù hợp do provider công bố.

### Giới hạn và fetch size trên cùng query

~~~java
SelectionQuery<Product> query =
    session.createSelectionQuery(
        """
        select p from Product p
        where p.category = :category
        order by p.createdAt desc, p.id desc
        """,
        Product.class
    );

query.setParameter("category", "BOOK");
query.setFirstResult(40);
query.setMaxResults(20);
query.setFetchSize(200);

List<Product> result = query.getResultList();
~~~

Trong trường hợp phân trang root thông thường:

- Offset = 40.
- Tối đa 20 kết quả được trả trong danh sách.
- JDBC driver nhận hint fetch size 200.
- Hint 200 **không mở rộng** result size thành 200.
- Driver có thể bỏ qua hint nếu điều kiện không phù hợp.
- Nếu SQL cuối có LIMIT 20, database không cần trả 200 hàng cho trang đó chỉ vì fetch size đặt 200.

**Đặt fetch size lớn hơn result limit thường không đem lại lợi ích rõ ràng** cho một trang nhỏ. Hãy tối ưu dựa trên workload thay vì dùng một con số cố định cho mọi query.

## 13. JPA chuẩn không có `Query.setFetchSize`

Jakarta Persistence chuẩn có:

~~~java
TypedQuery<Product> query = em.createQuery(
    "select p from Product p order by p.id",
    Product.class
);

query.setFirstResult(40);
query.setMaxResults(20);
~~~

Nhưng API `jakarta.persistence.Query` không định nghĩa phương thức `setFetchSize` như Hibernate query API.

Nếu Hibernate là provider, có thể unwrap query:

~~~java
TypedQuery<Product> jpaQuery = em.createQuery(
    "select p from Product p order by p.id",
    Product.class
);

org.hibernate.query.Query<?> hibernateQuery =
    jpaQuery.unwrap(org.hibernate.query.Query.class);

hibernateQuery.setFetchSize(200);
jpaQuery.setMaxResults(20);

List<Product> result = jpaQuery.getResultList();
~~~

Đoạn này dùng Hibernate-specific query interface và cần phiên bản hỗ trợ `setFetchSize` phù hợp. `unwrap` phụ thuộc provider; không portable với EclipseLink hoặc provider khác.

### Dùng query hint

Hibernate cũng có hint:

~~~java
List<Product> result = em.createQuery(
    "select p from Product p order by p.id",
    Product.class
)
.setHint("org.hibernate.fetchSize", 200)
.setMaxResults(20)
.getResultList();
~~~

Tên hint `org.hibernate.fetchSize` là **Hibernate-specific**, không phải hint chuẩn của JPA. Nên xác nhận với Hibernate version thực tế.

### Thiết lập fetch size mặc định

Hibernate cung cấp setting:

~~~properties
hibernate.jdbc.fetch_size=200
~~~

Nó là setting mặc định cho JDBC statement fetch size trong những đường truy vấn mà Hibernate quản lý, không phải số hàng tối đa hay page size mặc định của API.

Lưu ý rằng tên setting, giá trị mặc định và phạm vi áp dụng có thể thay đổi theo version/configuration; test driver behavior khi cần cursor fetching.

## 14. Có thể dùng `setMaxResults` và `setFetchSize` cùng nhau không?

Có. Chúng độc lập về ý nghĩa.

Ví dụ:

~~~java
query.setMaxResults(1000);
query.setFetchSize(100);
~~~

Tình huống phù hợp: một báo cáo cần lấy tối đa 1.000 hàng và driver hỗ trợ fetch theo block 100 hàng để giảm peak buffering.

Tình huống khác:

~~~java
query.setMaxResults(20);
query.setFetchSize(1000);
~~~

Về mặt API có thể hợp lệ, nhưng fetch size 1000 thường không mang lại lợi ích nếu result set có tối đa 20 hàng. Driver không phải lấy thêm 980 hàng không nằm trong result limit.

Ngược lại:

~~~java
query.setFetchSize(10);
~~~

không tự đặt tổng giới hạn 10 hàng. Nếu query khớp 1.000.000 hàng và code gọi `getResultList()`, ứng dụng có thể vẫn nạp 1.000.000 kết quả vào danh sách.

## 15. `getResultList()` có thể làm đầy bộ nhớ dù fetch size nhỏ

Một hiểu nhầm nguy hiểm:

~~~java
List<Product> products = session.createSelectionQuery(
    "select p from Product p",
    Product.class
)
.setFetchSize(100)
.getResultList();
~~~

Nếu query trả 500.000 Product, Hibernate có thể materialize **500.000 phần tử** vào Java `List`. Nếu kết quả là managed entities, persistence context còn giữ state/snapshot và các association/proxy tùy mapping.

`fetchSize(100)` không giới hạn tổng số entity trong persistence context.

### Những nơi có thể dùng bộ nhớ

1. **Database server:** cursor/sort/hash/query execution state.
2. **JDBC driver:** buffer các hàng đã fetch.
3. **Hibernate:** materialize entity, identifier, snapshots và collection state.
4. **Java application:** List, DTO, map, cache hoặc dữ liệu tự tích lũy.
5. **JSON/API layer:** nội dung response được tạo trước khi gửi.

Giảm driver fetch buffer không có nghĩa mọi tầng khác đều giảm bộ nhớ.

### Khi nào dùng `getResultList()`?

Phù hợp khi tập kết quả được giới hạn hợp lý và cần sử dụng đồng thời danh sách đó. Không thích hợp để xử lý hàng triệu entity nếu chỉ muốn biến đổi từng phần tử rồi bỏ.

## 16. Streaming/scrolling: kết hợp fetch size và cách duyệt kết quả

Đối với tập dữ liệu lớn, Hibernate có các API xử lý dần kết quả, chẳng hạn `stream()` hoặc `scroll()` theo version.

Ví dụ với Hibernate 6.x:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        SelectionQuery<Product> query =
            session.createSelectionQuery(
                "select p from Product p order by p.id",
                Product.class
            );

        query.setFetchSize(200);
        query.setReadOnly(true);

        try (ScrollableResults<Product> rows =
                 query.scroll(ScrollMode.FORWARD_ONLY)) {

            while (rows.next()) {
                Product product = rows.get();

                exportProduct(product);

                session.detach(product);
            }
        }

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

Cần import `org.hibernate.ScrollMode`, `org.hibernate.ScrollableResults` và `org.hibernate.query.SelectionQuery` phù hợp version. Với Hibernate 5, API `ScrollableResults` có khác biệt về kiểu trả về; ví dụ trên nhắm đến Hibernate 6.x.

Ở đây:

- `setFetchSize(200)` cung cấp JDBC hint.
- `scroll(FORWARD_ONLY)` cho phép ứng dụng xử lý tăng dần.
- `setReadOnly(true)` giảm overhead dirty checking/snapshots cho entities nạp mới trong query khi provider hỗ trợ.
- `session.detach(product)` giảm lượng managed entities tích lũy nếu không cần tiếp tục quản lý chúng.
- `try-with-resources` đóng cursor/scroll resource trước khi transaction kết thúc.

**Không được cho rằng `setFetchSize` đơn độc đã biến `getResultList()` thành streaming.** Phải chọn API consumption phù hợp.

### Có nên dùng `session.clear()` theo lô?

Đôi khi người ta flush/clear theo batch khi xử lý rất nhiều entity. Nhưng `clear()` detach **tất cả** managed entities và có thể làm mất pending changes chưa flush. Nếu đang dùng active scroll/cursor, phải kiểm tra lifecycle và provider semantics trước khi clear giữa lúc duyệt.

Với thao tác đọc/biến đổi thuần túy, projection DTO và cách xử lý tăng dần thường đơn giản hơn entity + detach. Với thao tác ghi batch, transaction boundaries và flush/clear cần thiết kế riêng.

## 17. `Stream<T>` cũng không mặc định giải quyết mọi vấn đề

Một số Hibernate/JPA API hỗ trợ:

~~~java
try (Stream<Product> stream =
         query.getResultStream()) {

    stream.forEach(product -> {
        exportProduct(product);
    });
}
~~~

API streaming có thể giữ JDBC resources trong suốt vòng đời stream. Với Hibernate, `stream()` có thể tận dụng cursor/scrolling theo query implementation. Nhưng **đừng suy ra**:

- Bất kỳ JPA provider nào cũng stream từ database thay vì materialize.
- `stream()` tự detach mọi entity.
- Không cần transaction cho cursor.
- Stream có thể dùng an toàn sau khi đóng Session.
- Stream được phép xử lý song song trên cùng Session/Connection.

Hãy đóng Stream đúng scope, tránh gọi network I/O dài trong vòng lặp nếu khiến connection giữ quá lâu, và không chuyển Hibernate Session/ResultSet sang các thread không được quản lý.

## 18. Pagination khác streaming ở mục tiêu

**Pagination** phục vụ việc chọn một phần kết quả rõ ràng cho người dùng, thường theo trang số hoặc cursor.

**Streaming** phục vụ việc xử lý liên tục một tập kết quả lớn mà không phải materialize tất cả cùng lúc.

| Tiêu chí | Pagination | Streaming |
| --- | --- | --- |
| Mục tiêu chính | Chọn một trang có kích thước giới hạn | Xử lý tăng dần nhiều hàng |
| Thường dùng | UI/API danh sách, tìm kiếm | Export, batch read, migration |
| Tham số | Page number/size, offset, sort hoặc cursor | Fetch size, scroll/stream, lifecycle |
| Số hàng tối đa toàn bộ workflow | Có thể chỉ một trang | Có thể rất lớn |
| Transaction | Tùy query và isolation | Cursor có thể cần transaction mở |
| Memory | Giới hạn nhờ trang nhỏ | Phụ thuộc driver và việc giữ managed objects |
| Count query | Có thể cần nếu dùng `Page` | Thường không cần total count |

Một chức năng export 2 triệu bản ghi có thể dùng cursor/streaming. Một API hiển thị 20 kết quả mỗi trang nên dùng pagination. Nếu export phải ổn định giữa các lần chạy và có thể resume, keyset/chunk pagination đôi khi phù hợp hơn một cursor transaction kéo dài hàng giờ.

## 19. Cẩn thận khi phân trang bằng JOIN FETCH collection

Đây là một ngoại lệ rất quan trọng đối với suy luận “`setMaxResults(20)` nghĩa database chỉ trả 20 hàng”.

Mapping:

~~~java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Query:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    """
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    order by o.id
    """,
    PurchaseOrder.class
)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
~~~

Một Order có thể có nhiều OrderLine. SQL JOIN nhân số hàng:

| order_id | line_id |
| ---: | ---: |
| 1 | 10 |
| 1 | 11 |
| 1 | 12 |
| 2 | 13 |
| 3 | NULL |
| ... | ... |

Nếu database giới hạn 20 **hàng SQL đã join**, nó có thể cắt một collection ở giữa, khiến Hibernate không thể trả entity root có collection đầy đủ.

Vì vậy Hibernate có thể **bỏ giới hạn SQL cho collection fetch và phân trang kết quả root ở bộ nhớ**. Điều này làm query tải rất nhiều hàng, mặc dù Java result list cuối chỉ có 20 PurchaseOrder.

### Cấu hình fail fast

Hibernate có setting:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

Khi bật trong tình huống phù hợp, Hibernate có thể ném lỗi thay vì âm thầm phân trang collection fetch trong memory. Đây là một kiểm soát hữu ích trong development/test và production khi muốn tránh truy vấn khổng lồ.

Setting này không phải phép tối ưu để biến collection fetch join thành phân trang SQL hợp lệ. **Cần sửa chiến lược truy vấn.**

### Giải pháp: phân trang root IDs trước

Bước 1:

~~~java
List<Long> ids = em.createQuery(
    """
    select o.id
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """,
    Long.class
)
.setParameter("status", OrderStatus.CONFIRMED)
.setFirstResult(40)
.setMaxResults(20)
.getResultList();
~~~

Bước 2:

~~~java
List<PurchaseOrder> fetched;

if (ids.isEmpty()) {
    fetched = List.of();
} else {
    fetched = em.createQuery(
        """
        select distinct o
        from PurchaseOrder o
        left join fetch o.lines
        where o.id in :ids
        """,
        PurchaseOrder.class
    )
    .setParameter("ids", ids)
    .getResultList();
}
~~~

`IN :ids` không bảo đảm thứ tự giống trang ID ban đầu. Nếu API cần đúng thứ tự, hãy sắp xếp lại theo vị trí các ID trong `ids` ở Java hoặc áp dụng ORDER BY phù hợp.

Hai truy vấn có thể quan sát các snapshot khác nhau nếu transaction isolation cho phép dữ liệu thay đổi giữa chúng. Nếu nghiệp vụ cần tính nhất quán cao, dùng transaction/isolation phù hợp hoặc một chiến lược khác.

**Page size 20 là 20 root entities** trong thiết kế này, không phải 20 hàng join của collection.

## 20. Có phải giới hạn SQL và giới hạn entity result luôn giống nhau?

Không. Với projection scalar một-hàng-một-kết-quả, `LIMIT 20` thường tương ứng tối đa 20 phần tử result.

Với JOIN FETCH collection, một entity root có thể chiếm nhiều hàng SQL. Với DISTINCT, aggregation, multiset/array aggregation hoặc grouping, mối quan hệ giữa SQL rows và Java result objects có thể phức tạp hơn.

Ví dụ:

~~~jpql
select p.category, count(p)
from Product p
group by p.category
~~~

`setMaxResults(10)` ở đây giới hạn **10 nhóm category trong kết quả query**, không phải 10 Product entities.

Vì thế khi nói “giới hạn số hàng”, phải hỏi **đơn vị kết quả là gì?** Root entity, DTO row, aggregate group hay raw SQL row? Trong trường hợp ORM collection fetch, giới hạn logic còn cần tránh cắt collection.

## 21. Giới hạn JDBC `setMaxRows` là một khái niệm nữa

JDBC Statement còn có:

~~~java
statement.setMaxRows(100);
~~~

`Statement.setMaxRows` yêu cầu giới hạn tối đa số hàng trong ResultSet của statement theo API JDBC. Nó **khác** `setFetchSize`:

~~~java
statement.setMaxRows(100);    // Giới hạn kết quả JDBC.
statement.setFetchSize(20);   // Hint lấy theo block 20 hàng.
~~~

Một statement có thể có cả hai setting. `setMaxRows` và JPA `setMaxResults` đều liên quan tới giới hạn kết quả nhưng nằm ở các tầng API khác nhau, và khả năng đẩy giới hạn xuống server có thể khác tùy driver.

Trong ứng dụng Hibernate/JPA, nếu mục tiêu là limit query result, thường ưu tiên `setMaxResults` để Hibernate/dialect xử lý. Không cần tự truy cập JDBC statement chỉ để setMaxRows.

## 22. `FetchType.LAZY` không phải JDBC fetch size

Một nhầm lẫn do cùng chữ “fetch”:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

`FetchType.LAZY` mô tả **khi nào association được tải**.

~~~java
query.setFetchSize(200);
~~~

`setFetchSize(200)` mô tả **JDBC driver được gợi ý chuyển bao nhiêu hàng khi cần thêm ResultSet data**.

Hai cơ chế độc lập:

| Cơ chế | Câu hỏi |
| --- | --- |
| `FetchType.LAZY` | Khi load Product/Order có phải load association ngay không? |
| `FetchType.EAGER` | Association có phải được fetch như một phần fetch plan không? |
| JPQL `JOIN FETCH` | Query này có phải nạp association được join không? |
| `@BatchSize(size = 20)` | Hibernate nên gom tải các association/proxy theo lô bao nhiêu? |
| JDBC `setFetchSize(200)` | Driver nên lấy ResultSet theo block cỡ bao nhiêu? |
| `PageRequest.of(0, 20)` | Trang đầu của UI cần tối đa bao nhiêu item? |

Ví dụ: một trang có 20 đơn, mỗi đơn cần customer. Dùng JDBC fetch size 20 không giải quyết N+1 nếu customer vẫn LAZY và được truy cập riêng. Cần fetch plan như JOIN FETCH to-one hoặc batch fetching. Ngược lại, JOIN FETCH có thể loại N+1 mà không thay đổi JDBC fetch size.

## 23. `@BatchSize` và JDBC batch size cũng khác fetch size

Hibernate có annotation:

~~~java
@BatchSize(size = 32)
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
~~~

`@BatchSize` liên quan việc Hibernate gom một số lazy associations/collections để tải trong ít query hơn. Nó **không** đặt số hàng được JDBC driver đọc mỗi round trip.

Cấu hình:

~~~properties
hibernate.jdbc.batch_size=50
~~~

lại liên quan đến **batching các câu INSERT/UPDATE/DELETE** trong Hibernate. Nó cũng không phải JDBC result-set fetch size.

Ba thứ:

~~~properties
hibernate.jdbc.fetch_size=200
hibernate.jdbc.batch_size=50
hibernate.default_batch_fetch_size=32
~~~

khác nhau:

| Setting | Tầng | Mục tiêu |
| --- | --- | --- |
| `hibernate.jdbc.fetch_size` | JDBC SELECT ResultSet | Hint số hàng driver lấy mỗi đợt |
| `hibernate.jdbc.batch_size` | JDBC DML batching | Gom nhiều lệnh ghi JDBC |
| `hibernate.default_batch_fetch_size` | Hibernate association loading | Gom tải nhiều entity/collection lazy |

Không đổi một setting rồi kỳ vọng nó sửa mọi tình huống có từ “batch” hoặc “fetch”.

## 24. Kích thước trang và dung lượng dữ liệu là hai đại lượng khác

Hai trang đều có 20 phần tử nhưng dung lượng mạng/bộ nhớ có thể rất khác.

**Trang A:** 20 DTO, mỗi DTO gồm ID và tên.

**Trang B:** 20 entity Product, mỗi entity có 10 association đã được fetch, cùng một collection lớn.

Cả hai có `pageSize = 20`, nhưng trang B có thể tải hàng nghìn SQL rows và rất nhiều object.

Kích thước trang không tự bảo đảm:

- Độ rộng mỗi SQL row.
- Số collection elements được tải kèm.
- JSON response byte size.
- JDBC round trips.
- Heap sử dụng của persistence context.
- Thời gian truy vấn hoặc serialization.

Để kiểm soát các yếu tố đó, cần query projection, fetch plan phù hợp, chỉ số DB, giới hạn page size ở API và đo thực tế.

## 25. Fetch size quá nhỏ hoặc quá lớn có thể gây hại

Với driver thực sự fetch theo block, fetch size ảnh hưởng trade-off giữa round trip và memory.

### Fetch size quá nhỏ

Ví dụ `fetchSize = 1` đối với 100.000 hàng:

- Có thể cần nhiều lần yêu cầu thêm hàng qua network.
- Latency mỗi round trip có thể cộng dồn đáng kể.
- CPU/network overhead tăng.
- Bộ nhớ buffer mỗi block nhỏ hơn.

### Fetch size quá lớn

Ví dụ `fetchSize = 50_000`:

- Driver có thể buffer lượng dữ liệu lớn.
- Peak memory tăng, nhất là với hàng rộng hoặc LOB.
- Client có thể tải nhiều hàng hơn cần thiết nếu dừng đọc sớm.
- Không cải thiện hiệu năng nếu DB/driver không dùng hint.
- Một số driver có hạn chế/cơ chế riêng cho cursor.

### Fetch size vừa phải

Không có một con số luôn tối ưu. Nhiều dự án bắt đầu đo ở vài chục đến vài trăm hàng mỗi block, rồi điều chỉnh theo row width, latency, throughput và driver behavior.

**Con số 200 trong ví dụ là minh họa, không phải cấu hình tối ưu phổ quát.**

## 26. Deep OFFSET pagination có chi phí riêng

Giả sử ứng dụng muốn trang số 20.000 với 20 phần tử mỗi trang:

\[
\text{offset} = 20{,}000 \times 20 = 400{,}000
\]

SQL:

~~~sql
SELECT id, name, created_at
FROM products
ORDER BY created_at DESC, id DESC
OFFSET 400000
LIMIT 20;
~~~

Database có thể phải đi qua lượng lớn dữ liệu trước khi xác định 20 hàng thuộc trang hiện tại, tùy kế hoạch thực thi và index.

Thay đổi fetch size từ 100 thành 500 **không xử lý chi phí bỏ qua 400.000 kết quả ở database**. Đây là chi phí của offset pagination, không phải vấn đề truyền ResultSet theo block.

Với feed/lịch sử lớn và chức năng “xem tiếp”, có thể dùng **keyset pagination**.

## 27. Keyset pagination: lấy tiếp sau khóa sắp xếp

Giả sử sort:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Với cursor từ phần tử cuối trang trước (`lastCreatedAt`, `lastId`), truy vấn trang kế tiếp:

~~~sql
SELECT id, name, created_at
FROM products
WHERE created_at < :lastCreatedAt
   OR (
       created_at = :lastCreatedAt
       AND id < :lastId
   )
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Đây là mẫu seek pagination với hai khóa sắp xếp DESC. Cần xác định thứ tự tie-breaker duy nhất, index phù hợp và quy tắc xử lý NULL nếu sort columns có thể null.

So sánh:

| Offset pagination | Keyset pagination |
| --- | --- |
| Truy cập trang N theo số | Truy cập phần tiếp theo theo cursor |
| Cần offset lớn khi đi sâu | Tránh bỏ qua N hàng bằng offset sâu |
| Dễ hỗ trợ “tới trang 100” | Phù hợp nút “Tiếp theo”/infinite scroll |
| Dễ bị dịch trang khi dữ liệu thêm/xóa | Có thể ổn định hơn theo khóa nhưng vẫn cần concurrency semantics |
| Cần ORDER BY ổn định | Cần ORDER BY và điều kiện seek tương thích |

Keyset thay đổi **cách chọn trang**, không phải fetch size. Driver vẫn có thể sử dụng JDBC fetch size độc lập khi đọc ResultSet.

## 28. Count query không quyết định fetch size

Một `Page<Product>` có thể yêu cầu cả data query và count query:

~~~sql
SELECT id, sku, name, created_at
FROM products
WHERE category = ?
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 40;
~~~

và:

~~~sql
SELECT COUNT(*)
FROM products
WHERE category = ?;
~~~

Count query thường trả một hàng chứa con số, nhưng database có thể phải quét/index scan rất nhiều dữ liệu để tính count. JDBC fetch size 200 không làm count query chỉ đếm 200 rows.

Đây là khác biệt giữa:

- **Khối lượng công việc database phải làm** để tính kết quả.
- **Số hàng trong ResultSet cuối**.
- **Số lần driver truyền dữ liệu**.
- **Số phần tử của trang UI**.

Một query chỉ trả một aggregate row vẫn có thể rất đắt. Giảm page size không nhất thiết làm count query rẻ hơn nếu count vẫn phải tính toàn bộ tập kết quả.

## 29. Giới hạn số hàng không phải giới hạn công việc database

Ngay cả khi truy vấn có:

~~~sql
SELECT *
FROM products
ORDER BY price DESC
LIMIT 10;
~~~

database có thể phải xem xét rất nhiều hàng để sắp xếp/tìm 10 sản phẩm đắt nhất, nếu thiếu index phù hợp.

Câu lệnh LIMIT giảm số hàng **trả về**, nhưng không có nghĩa engine chỉ đọc đúng 10 hàng từ bảng.

Tương tự:

~~~sql
SELECT DISTINCT category
FROM products
LIMIT 10;
~~~

có thể cần xử lý nhiều hàng để tìm các category duy nhất tùy plan/index.

Đừng dùng `setMaxResults` như phương án thay thế index, WHERE có chọn lọc, projection hợp lý hoặc EXPLAIN ANALYZE.

## 30. Tại sao fetch size không làm giảm N+1?

Giả sử một trang có 20 đơn hàng:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o order by o.id",
    PurchaseOrder.class
)
.setMaxResults(20)
.getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCustomer().getDisplayName()
    );
}
~~~

Nếu `customer` LAZY và mỗi đơn có customer khác nhau, có thể phát 1 query lấy 20 đơn + 20 query lấy customer.

JDBC fetch size 200 trên query root **không gộp những query customer riêng**. Nó chỉ ảnh hưởng cách driver lấy rows của từng ResultSet nếu được sử dụng.

Giải pháp có thể là:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    """
    select o from PurchaseOrder o
    left join fetch o.customer
    order by o.id
    """,
    PurchaseOrder.class
)
.setMaxResults(20)
.getResultList();
~~~

Với fetch join **to-one** có cardinality đúng, pagination trên root thường thuận lợi. Với collection fetch join **to-many**, phải quay lại cảnh báo phân trang trong memory ở phần 19.

Để giảm N+1, cần giải quyết **fetch plan và association loading**, không phải chỉ tăng JDBC fetch size.

## 31. Những con số cùng tồn tại trong một request

Giả sử REST endpoint:

~~~text
GET /products?page=2&size=20
~~~

Ứng dụng cấu hình:

~~~properties
hibernate.jdbc.fetch_size=200
~~~

Repository trả:

~~~java
Page<Product> result =
    repository.findByCategory(
        "BOOK",
        PageRequest.of(2, 20)
    );
~~~

Hãy phân tích:

1. Request muốn trang số 2, tối đa 20 sản phẩm.
2. Framework tính offset = 40.
3. Data query thường có giới hạn 20 result theo dialect.
4. Driver có thể nhận fetch size hint 200.
5. Nếu data query chỉ trả tối đa 20 rows, fetch size 200 không làm result thành 200.
6. Nếu trả `Page`, framework có thể chạy thêm count query để biết total.
7. Nếu entity có LAZY associations được truy cập sau đó, các query phụ có thể xuất hiện.
8. Nếu query fetch join collection, limit có thể không được đẩy xuống SQL như dự kiến.

Ba lớp quyết định vẫn tách rời: **API page size 20, Hibernate result limit 20, JDBC fetch hint 200**.

## 32. API bảo vệ page size đầu vào

Không nên cho client yêu cầu page size tùy ý:

~~~text
GET /products?page=0&size=10000000
~~~

Một request có thể chiếm quá nhiều database/heap/network resources.

Ví dụ service validation:

~~~java
public PageRequest normalizePage(
    int pageNumber,
    int requestedSize
) {
    if (pageNumber < 0) {
        throw new IllegalArgumentException(
            "pageNumber không được âm"
        );
    }

    int defaultSize = 20;
    int maxSize = 100;

    int size = requestedSize <= 0
        ? defaultSize
        : Math.min(requestedSize, maxSize);

    return PageRequest.of(
        pageNumber,
        size,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        )
    );
}
~~~

Số 20 và 100 là ví dụ chính sách API. Trong hệ thống thật, cần quy định rõ size=0/âm là lỗi hay dùng default, validate pageNumber lớn gây overflow và giới hạn request theo workload.

Điều này là **kiểm soát API page size**. Nó không thay việc chọn JDBC fetch size cho export/streaming query khác.

## 33. Đo hiệu năng đúng tầng

Để chọn các con số hợp lý, nên quan sát những chỉ số riêng.

| Câu hỏi | Chỉ số nên đo |
| --- | --- |
| Query lấy quá nhiều kết quả? | Result row count, maxResults/page size, response size |
| Driver đọc ResultSet quá chậm? | JDBC round trips, network latency, fetch size, driver buffering |
| Database tốn CPU? | Execution plan, rows scanned, sort/hash, index usage |
| Heap tăng khi export? | Peak heap, retained entities, List size, persistence context size |
| API trang chậm? | Data query, count query, serialization, N+1 |
| N+1 xảy ra? | Số SQL SELECT, fetch plan, batch fetching |
| Deep pagination chậm? | Offset depth, index, keyset alternative |
| Pool cạn? | Connection hold time, stream/cursor lifecycle, transaction duration |

Một thay đổi fetch size có thể giảm round trips nhưng tăng heap. Một thay đổi page size có thể giảm response payload nhưng count query vẫn chậm. Một result limit có thể làm response nhỏ nhưng database vẫn scan/sort nhiều hàng.

Để tối ưu hiệu quả, phải xác định **nút thắt nằm ở đâu** trước khi điều chỉnh con số.

## 34. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| `setFetchSize(100)` chỉ trả 100 kết quả | Không; chỉ hint cho driver khi đọc ResultSet |
| `setMaxResults(100)` làm JDBC fetch từng block 100 | Không; nó giới hạn result query, không đặt fetch hint |
| Page size 20 nghĩa driver luôn lấy 20 hàng mỗi đợt | Không; page size thuộc API, fetch size thuộc JDBC |
| SQL LIMIT 20 nghĩa database chỉ đọc 20 hàng | Không; có thể scan/sort nhiều hơn |
| `getResultList()` + fetchSize nhỏ là streaming | Không; List vẫn có thể chứa toàn bộ kết quả |
| `FetchType.LAZY` và JDBC fetch size là một | Không; một cái tải association, một cái điều khiển ResultSet hint |
| `@BatchSize(20)` là JDBC fetchSize 20 | Không; BatchSize tối ưu association loading |
| `hibernate.jdbc.batch_size` ảnh hưởng SELECT ResultSet | Không; chủ yếu cho batching DML |
| `Page` luôn chỉ chạy một SELECT | Có thể cần count query và association queries |
| `Slice` biết total elements chính xác | Không; chỉ cần biết có tiếp hay không |
| `setMaxResults` luôn đẩy limit xuống SQL | Có ngoại lệ như collection fetch pagination |
| JOIN FETCH collection + LIMIT 20 luôn chỉ tải 20 SQL rows | Có thể Hibernate phân trang trong memory |
| Fetch size càng lớn càng nhanh | Không; trade-off round trips, memory, driver behavior |
| Page 0 luôn là trang số 1 | Spring Data PageRequest dùng zero-based index |
| Fetch size có thể khắc phục deep OFFSET | Không; offset là vấn đề selection/cost database |
| LIMIT không cần ORDER BY | Không; kết quả trang có thể không ổn định |
| Stream luôn giải phóng mọi entity state | Không; cần quản lý Session/persistence context |
| PostgreSQL fetchSize>0 luôn dùng cursor | Cần transaction không auto-commit và điều kiện driver khác |
| MySQL setFetchSize dương luôn streaming | Cần cấu hình driver/cursor phù hợp |
| Result limit 20 đồng nghĩa response nhẹ | Không nếu fetch graph rộng hoặc nhiều collection |

## 35. Cây quyết định chọn cơ chế

~~~mermaid
flowchart TD
    A["Ứng dụng cần đọc dữ liệu"] --> B{"Có cần UI/API phân trang?"}
    B -- "Có" --> C["Đặt pageSize và thứ tự rõ"]
    C --> D{"Cần tổng số kết quả?"}
    D -- "Có" --> E["Page + count query khi cần"]
    D -- "Không" --> F["Slice/List/Window nếu phù hợp"]
    E --> G["Limit/offset hoặc keyset để chọn trang"]
    F --> G
    B -- "Không" --> H{"Cần xử lý tập dữ liệu rất lớn?"}
    H -- "Không" --> I["setMaxResults nếu cần giới hạn nghiệp vụ"]
    H -- "Có" --> J["Stream/scroll hoặc chunk pagination"]
    J --> K["JDBC fetchSize theo driver và transaction"]
    G --> L{"Fetch join collection?"}
    L -- "Có" --> M["Tránh offset pagination trực tiếp; lấy root ID trước"]
    L -- "Không" --> N["Đo SQL và response size"]
    M --> N
    K --> O["Không giữ tất cả managed entities trong memory"]
    O --> N
    I --> N
~~~

Sơ đồ nhấn mạnh: **chọn page size dựa trên sản phẩm/UI, chọn result limit dựa trên query contract, chọn fetch size dựa trên driver và cách consume ResultSet**.

## 36. Bài tập tình huống

### Bài 1 — Fetch size 50, query trả 10.000 hàng

~~~java
query.setFetchSize(50);
List<Product> list = query.getResultList();
~~~

**Câu hỏi:** Danh sách Java có tối đa 50 phần tử không?

**Đáp án:** Không. `fetchSize` không giới hạn tổng kết quả. Danh sách có thể chứa 10.000 Product nếu query trả 10.000 và không có result limit.

### Bài 2 — setMaxResults 50, fetch size 500

~~~java
query.setMaxResults(50);
query.setFetchSize(500);
~~~

**Câu hỏi:** Có thể trả 500 Product không?

**Đáp án:** Không vì result limit là 50. Fetch size 500 chỉ là hint driver.

### Bài 3 — PageRequest.of(3, 25)

**Câu hỏi:** Offset và số phần tử tối đa là bao nhiêu?

**Đáp án:** Offset = 3 × 25 = 75; content tối đa 25 phần tử. Page index là zero-based.

### Bài 4 — Page size 20 nhưng chỉ có 7 hàng ở trang cuối

**Câu hỏi:** `getSize()` và `getNumberOfElements()` thường là bao nhiêu?

**Đáp án:** `getSize() = 20`; `getNumberOfElements() = 7`.

### Bài 5 — PostgreSQL không dùng cursor dù fetchSize 100

**Câu hỏi:** Một nguyên nhân thường gặp là gì?

**Đáp án:** Connection còn auto-commit true. Cursor-based fetching trong pgJDBC thông thường cần transaction không auto-commit, forward-only và query phù hợp.

### Bài 6 — MySQL không stream dù setFetchSize 100

**Câu hỏi:** Kiểm tra gì?

**Đáp án:** Connector/J version và cấu hình như `useCursorFetch=true`, server-side prepared statements và điều kiện cursor của driver.

### Bài 7 — Dùng `FetchType.LAZY` để giảm ResultSet fetch size

**Câu hỏi:** Có đúng không?

**Đáp án:** Không. LAZY quyết định association có tải khi cần không; không đặt hint JDBC `Statement.setFetchSize`.

### Bài 8 — Trang đơn hàng có collection JOIN FETCH

**Câu hỏi:** Tại sao limit 20 mà Hibernate vẫn đọc hàng nghìn SQL rows?

**Đáp án:** Collection join nhân số hàng và giới hạn SQL có thể cắt collection. Hibernate có thể phân trang root trong memory. Nên phân trang ID trước rồi fetch collection.

### Bài 9 — Export 1 triệu Product qua getResultList và fetchSize 100

**Câu hỏi:** Có chắc dùng ít memory không?

**Đáp án:** Không. `getResultList()` materialize toàn bộ danh sách; persistence context có thể giữ nhiều managed entities. Dùng stream/scroll hoặc chunk pagination và quản lý state.

### Bài 10 — Deep OFFSET chậm

**Câu hỏi:** Tăng fetch size từ 100 lên 1000 có chắc sửa không?

**Đáp án:** Không. OFFSET sâu có chi phí chọn/bỏ qua hàng ở database. Cân nhắc keyset pagination và index.

### Bài 11 — Page có tổng 500 phần tử, size 20

**Câu hỏi:** Có bao nhiêu trang?

**Đáp án:** 25 trang nếu tổng chính xác là 500 và size = 20.

### Bài 12 — Slice size 20 nhưng query đọc 21 phần tử

**Câu hỏi:** Có sai page size không?

**Đáp án:** Không. Infrastructure có thể đọc thêm một phần tử để biết có trang tiếp theo, nhưng content của Slice vẫn tối đa 20.

### Bài 13 — Count query chậm dù trang 10 phần tử

**Câu hỏi:** Giảm fetch size có giúp count nhanh không?

**Đáp án:** Thường không. Count query trả một scalar nhưng có thể phải scan nhiều hàng. Cần xem execution plan, index và có thật sự cần total count không.

### Bài 14 — Truy vấn LIMIT 20 không có ORDER BY

**Câu hỏi:** Có ổn định cho pagination không?

**Đáp án:** Không được bảo đảm. Thêm ORDER BY với khóa phụ duy nhất.

### Bài 15 — Hibernate fetchSize và batchSize

**Câu hỏi:** `hibernate.jdbc.fetch_size=200` và `hibernate.jdbc.batch_size=50` giống nhau không?

**Đáp án:** Không. Fetch size là hint đọc ResultSet; JDBC batch size là cấu hình gom lệnh ghi DML.

### Bài 16 — Query phân trang không có count

**Câu hỏi:** Có buộc phải dùng Page không?

**Đáp án:** Không. Có thể trả Slice/List/Window tùy API và yêu cầu, tránh count không cần thiết.

## 37. Gợi ý chiến lược theo tình huống

| Trường hợp | Result limit | JDBC fetch size | Pagination |
| --- | --- | --- | --- |
| Autocomplete tối đa 10 gợi ý | `setMaxResults(10)` | Thường không cần tùy chỉnh | Không cần page number |
| Trang danh sách 20 sản phẩm | Tối đa 20 | Driver default thường đủ | `PageRequest.of(n,20)` |
| Trang cuối có 7 sản phẩm | Tối đa 20, thực tế 7 | Độc lập | Page metadata phản ánh 7 content |
| Báo cáo giới hạn 1000 hàng | `setMaxResults(1000)` | Có thể đo hint phù hợp | Không nhất thiết có page |
| Export 500.000 hàng | Không dùng List vô hạn | Đo fetch size cho cursor | Stream/scroll/chunk |
| Infinite scroll | Limit cho mỗi batch | Độc lập | Keyset/Window/Slice |
| Danh sách đơn kèm customer to-one | Limit theo root | Tùy driver | Có thể kết hợp to-one fetch join |
| Danh sách đơn kèm collection lines | Paginate root IDs trước | Không sửa được multiplication | Two-phase pagination |
| Analytics COUNT(*) | Result là một scalar | Không đáng kể | Không cần page |
| Lazy collection N+1 | Không phải vấn đề chính | Không tự sửa N+1 | Fetch plan/batch fetching |
| JDBC cursor PostgreSQL | Theo use case | Positive hint + transaction | Không nhất thiết có pagination |
| MySQL cursor fetching | Theo use case | Hint + Connector/J config | Không nhất thiết có pagination |

## 38. Tổng kết

**Giới hạn số hàng, JDBC fetch size và kích thước trang là ba cơ chế độc lập, dù có thể xuất hiện trong cùng một truy vấn.**

- `setMaxResults(n)` hoặc SQL `LIMIT n`: giới hạn **số kết quả tối đa**, thường nhằm giảm tập dữ liệu trả về. Nó không xác định JDBC row prefetch behavior.
- `setFetchSize(n)`: cung cấp **gợi ý cho JDBC driver** về số hàng lấy khi cần thêm dữ liệu của ResultSet. Nó không biến query thành LIMIT, không tự tạo trang và không bảo đảm streaming.
- `PageRequest.of(pageNumber, pageSize)`: diễn đạt **yêu cầu phân trang của ứng dụng**. Framework thường chuyển nó thành offset/limit và có thể thêm count query hoặc đọc dư một hàng nếu cần biết có trang tiếp theo.

Khi thiết kế truy vấn với Hibernate/JPA:

1. Xác định use case cần **bao nhiêu kết quả**.
2. Đặt **ORDER BY ổn định** khi giới hạn hoặc phân trang.
3. Dùng `setFirstResult/setMaxResults` hoặc pagination abstraction để chọn **đúng phần dữ liệu**.
4. Đừng lấy `fetchSize` thay cho result limit.
5. Nếu cần đọc dữ liệu lớn, chọn **streaming/scrolling hoặc chunk pagination**, đồng thời quản lý transaction và persistence context.
6. Chỉ tối ưu JDBC fetch size theo **driver/database thực tế**.
7. Tránh **pagination trực tiếp với collection JOIN FETCH** vì giới hạn có thể được áp dụng trong memory.
8. Phân biệt fetch size với **LAZY/EAGER, batch association loading và JDBC write batching**.
9. Đo riêng **SQL execution cost, JDBC transport, heap/memory và API response**.

Một hệ thống có thể chọn **pageSize = 20** để phục vụ UI, **setMaxResults = 20** để giới hạn trang, và **JDBC fetchSize = 200** theo cấu hình driver mà không hề mâu thuẫn. Chúng chỉ đang điều khiển các tầng khác nhau của quá trình truy vấn.

## Tài liệu tham khảo

- [Hibernate ORM — SelectionQuery API](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/query/SelectionQuery.html)
- [Hibernate ORM — User Guide, query hints và JDBC fetch size](https://docs.hibernate.org/stable/core/userguide/html_single/)
- [Java JDBC — Statement.setFetchSize](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Statement.html)
- [PostgreSQL JDBC — Cursor-based fetching](https://jdbc.postgresql.org/documentation/query/#getting-results-based-on-a-cursor)
- [MySQL Connector/J — JDBC API implementation notes](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-implementation-notes.html)
- [Spring Data JPA — Paging and query methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
