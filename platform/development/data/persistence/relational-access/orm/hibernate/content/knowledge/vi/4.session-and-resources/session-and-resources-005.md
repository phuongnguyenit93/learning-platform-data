# Kết nối được lấy hoặc trả vào thời điểm nào theo cấu hình

Một `Session` Hibernate **không nhất thiết chiếm giữ một JDBC `Connection` ngay khi được mở**. Hibernate quản lý một *logical connection* gắn với phiên làm việc, còn JDBC connection thực tế có thể được lấy từ `DataSource` hoặc `ConnectionProvider` khi cần và được trả ở thời điểm được xác định bởi cấu hình.

Để trả lời chính xác câu hỏi “connection được lấy lúc nào và trả lúc nào?”, cần xem **connection handling mode**, loại transaction (`RESOURCE_LOCAL` hay `JTA`), cấu hình autocommit của pool, connection provider, các tài nguyên JDBC còn đang mở và việc ứng dụng có tự đưa connection cho `Session` hay không.

> **Kết luận thực hành:** Với một ứng dụng **resource-local** dùng cấu hình Hibernate thông thường, mode mặc định là `DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION`: connection được lấy khi Hibernate cần nó và trả sau khi transaction hoàn tất. Nhưng `beginTransaction()` thường **đã làm Hibernate lấy connection** để kiểm tra/tắt autocommit, trước cả câu SQL đầu tiên. Chỉ khi cấu hình đúng cam kết pool đã tắt autocommit, Hibernate mới có thể trì hoãn thao tác lấy connection đến lúc thực sự cần truy cập JDBC.

## 1. Bốn thứ cần phân biệt

| Đối tượng | Ý nghĩa | Vòng đời thường gặp |
| --- | --- | --- |
| `SessionFactory` | Factory dùng chung để tạo `Session`, nắm cấu hình và nhiều service | Khởi tạo lúc ứng dụng bắt đầu; đóng khi ứng dụng dừng |
| `Session` / `EntityManager` | Phiên ORM, chứa *persistence context* và theo dõi entity | Mở/đóng theo đơn vị công việc hoặc request/transaction |
| JDBC `Connection` | Handle dùng để thực hiện các thao tác JDBC với database | Được lấy từ provider/pool và được Hibernate trả theo handling mode |
| Connection pool | Nơi quản lý các kết nối để tái sử dụng | Sống lâu hơn nhiều session; cấp phát và thu hồi connection theo nhu cầu |

Các khái niệm **logical connection**, **connection handle** và **physical database connection** cũng không đồng nhất:

- **Logical connection** là abstraction Hibernate dùng để giữ trạng thái truy cập JDBC. Nó có thể tồn tại khi chưa giữ một JDBC connection cụ thể.
- **JDBC connection handle** là đối tượng ứng dụng nhận được từ pool/provider. Với pool, `close()` trên handle thường có nghĩa trả quyền sử dụng về pool.
- **Physical database connection** là kết nối thực với server. Trả handle vào pool **không có nghĩa đóng socket TCP hoặc hủy session trên database**; pool có thể giữ kết nối vật lý đang rảnh để dùng lại.

Vì vậy, phát biểu “đóng `Session` là đóng kết nối database” thường không chính xác trong ứng dụng có pool. `Session.close()` giải phóng phiên làm việc và những tài nguyên mà phiên còn nắm; pool mới quyết định thời điểm thật sự đóng kết nối vật lý.

### 1.1. Sơ đồ vòng đời

```text
Ứng dụng
   |
   | SessionFactory.openSession()
   v
[Session / persistence context] --------------------+
   |                                                |
   | Khi cần thao tác JDBC                          | Theo dõi entity,
   v                                                | thay đổi, lazy load
[Logical JDBC connection]                           |
   |                                                |
   | acquire (tùy cấu hình)                         |
   v                                                |
[ConnectionProvider / DataSource / pool]            |
   |                                                |
   | checkout                                       |
   v                                                |
[JDBC Connection handle] ---> [Database server]     |
   |                                                |
   | release theo handling mode                     |
   v                                                |
[Trả handle về provider/pool]                        |
                                                    |
                  Session.close() -------------------+
```

Có hai điểm độc lập: **thời điểm nhận connection** (*acquisition*) và **thời điểm trả connection** (*release*). Hibernate ghép chúng thành `PhysicalConnectionHandlingMode`.

## 2. Các connection handling mode

Trong các phiên bản Hibernate ORM hiện đại, cấu hình trọng tâm là:

```properties
hibernate.connection.handling_mode=DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION
```

Giá trị tương ứng với các chế độ của `org.hibernate.resource.jdbc.spi.PhysicalConnectionHandlingMode`. Bảng sau trình bày ý nghĩa; việc áp dụng thực tế còn phụ thuộc provider, transaction và tài nguyên JDBC đang hoạt động.

| Handling mode | Lúc lấy connection | Lúc trả connection | Hệ quả chính |
| --- | --- | --- | --- |
| `IMMEDIATE_ACQUISITION_AND_HOLD` | Ngay lúc mở `Session` | Khi đóng `Session` | Session rảnh vẫn có thể giữ một connection |
| `DELAYED_ACQUISITION_AND_HOLD` | Khi JDBC thực sự cần connection | Khi đóng `Session` | Tránh lấy sớm, nhưng sau lần lấy đầu giữ qua các transaction |
| `DELAYED_ACQUISITION_AND_RELEASE_AFTER_STATEMENT` | Khi JDBC cần connection | Sau statement, nếu có thể giải phóng an toàn | Phù hợp một số môi trường JTA/container; phụ thuộc khả năng *aggressive release* |
| `DELAYED_ACQUISITION_AND_RELEASE_BEFORE_TRANSACTION_COMPLETION` | Khi JDBC cần connection | Trong pha xử lý trước khi transaction hoàn tất bình thường; có dọn dẹp khi transaction kết thúc bất thường | Mode ít dùng, cần hiểu rõ transaction coordinator và phiên bản Hibernate |
| `DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION` | Khi JDBC cần connection | Sau `commit`/`rollback` hoặc transaction completion | Thường phù hợp resource-local; session còn mở vẫn có thể không giữ connection |

> Không phải mọi dòng Hibernate đều trình bày đầy đủ cùng một tập giá trị trong user guide. Hãy tra **Javadoc và user guide của đúng phiên bản đang dùng**, đặc biệt khi muốn sử dụng `BEFORE_TRANSACTION_COMPLETION`.

### 2.1. `IMMEDIATE_ACQUISITION_AND_HOLD`

```text
openSession()          → checkout connection
beginTransaction()     → dùng connection đã có
query / flush          → dùng connection đã có
commit()               → vẫn giữ connection
... xử lý Java khác ...→ vẫn giữ connection
session.close()        → release connection
```

Mode này dễ lý giải nhưng có thể giữ connection lâu không cần thiết nếu session tồn tại qua những khoảng xử lý không sử dụng database. Trong hệ thống nhiều request đồng thời, giữ connection qua “thời gian nghĩ” của người dùng hoặc gọi API ngoài có thể khiến pool nhanh cạn.

### 2.2. `DELAYED_ACQUISITION_AND_HOLD`

```text
openSession()          → chưa checkout
công việc Java thuần   → chưa checkout
thao tác JDBC đầu tiên → checkout connection
query / commit         → dùng connection đang giữ
session.close()        → release connection
```

Từ lúc đã lấy, session có thể giữ connection qua nhiều transaction cho tới khi đóng. Đây là **giữ sau lần sử dụng đầu**; khác với mode `AFTER_TRANSACTION`, vốn có khả năng trả connection giữa các transaction trong cùng session.

### 2.3. `DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION`

```text
openSession()             → chưa nhất thiết checkout
beginTransaction()        → có thể checkout vì cần xử lý autocommit
query / flush             → dùng connection
transaction.commit()      → hoàn tất transaction; release connection
session còn mở            → không nhất thiết giữ connection
transaction tiếp theo     → có thể checkout lại
session.close()           → dọn tài nguyên ORM còn lại
```

Đây là **mặc định cho resource-local transaction** trong tài liệu Hibernate. `rollback()` cũng là một kết thúc transaction và sẽ kích hoạt quy trình trả connection theo mode này.

Điểm dễ bỏ sót: tên mode có chữ `DELAYED` nhưng không đảm bảo lần checkout đầu chỉ xảy ra khi `SELECT`/`INSERT` đầu tiên. Việc chuẩn bị transaction, đọc metadata hoặc chạy callback JDBC cũng có thể cần connection.

### 2.4. `DELAYED_ACQUISITION_AND_RELEASE_AFTER_STATEMENT`

```text
Session cần statement A → acquire → thực thi A → release nếu an toàn
Session cần statement B → acquire → thực thi B → release nếu an toàn
Session cần statement C → acquire → thực thi C → release nếu an toàn
```

Đây là *aggressive release*, thường được dùng trong một số môi trường **JTA**. Nhưng câu “trả sau mỗi statement” chỉ là **chính sách yêu cầu**, không phải lời hứa rằng sau mọi `execute()` connection vật lý đều trở lại trạng thái rảnh.

Các hạn chế quan trọng:

- `ConnectionProvider` phải hỗ trợ *aggressive release* và tái nhận một connection thích hợp, đặc biệt khi phải duy trì ngữ nghĩa của cùng một transaction.
- Nếu provider **không** hỗ trợ, Hibernate có thể chuyển cách xử lý thực tế về **release after transaction**.
- Nếu còn tài nguyên JDBC phụ thuộc connection, như `ResultSet`/cursor/stream đang mở, việc release có thể được trì hoãn cho đến khi tài nguyên đó đóng.
- Trong container JTA, “Hibernate release handle” vẫn có thể giữ connection được liên kết với transaction/thread ở tầng container. Có thể checkout lại đúng connection underlying khi truy vấn kế tiếp.

### 2.5. `DELAYED_ACQUISITION_AND_RELEASE_BEFORE_TRANSACTION_COMPLETION`

Mode này đặt một mốc trả connection trong chu trình xử lý completion của transaction thay vì đơn giản giữ đến lúc session đóng. Nó chỉ thích hợp khi người phát triển hiểu chính xác thứ tự **flush → transaction synchronization → before-completion → after-completion** của transaction coordinator và phiên bản Hibernate. Trường hợp rollback hoặc completion không đi qua đường bình thường vẫn cần cơ chế cleanup sau transaction.

Đây **không phải** lựa chọn khởi đầu để khắc phục pool starvation; trước tiên nên kiểm tra thời gian transaction, rò rỉ JDBC resource và mode mặc định.

## 3. Vì sao mặc định resource-local có thể lấy connection ngay khi `beginTransaction()`?

Xét một ứng dụng Java SE dùng Hibernate với JDBC transaction, không qua JTA:

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        Book book = session.find(Book.class, 42L);
        if (book != null) {
            book.rename("Hibernate Essentials");
        }

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
```

Ở đây, `Session` quản lý các entity; database transaction được điều khiển bằng transaction resource-local. Với default mode:

```properties
hibernate.connection.handling_mode=DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION
```

Hibernate cần bảo đảm các thao tác JDBC trong transaction **không chạy với autocommit bật**. Nếu không biết trước trạng thái `Connection.getAutoCommit()`, Hibernate thường phải lấy connection khi bắt đầu transaction để kiểm tra và chuyển nó sang `false`.

Điều này cho ra một dòng thời gian có thể quan sát:

```text
T0  sessionFactory.openSession()    : Session được tạo, chưa lấy Connection
T1  session.beginTransaction()      : checkout Connection để xử lý autocommit
T2  tính toán / kiểm tra nghiệp vụ  : connection có thể đang được giữ
T3  session.find(Book.class, 42L)   : thực thi SQL SELECT nếu cần database
T4  tx.commit()                     : flush (nếu có), commit
T5  transaction completion          : release về pool
T6  session.close()                 : kết thúc Session (không phải mốc trả đầu tiên)
```

T1–T5 là thời gian pool coi connection đang được mượn, **ngay cả khi T2 không thực thi SQL**. Ví dụ một phương thức `@Transactional` mở transaction sớm rồi gọi dịch vụ bên ngoài trong vài giây có thể giữ connection dài hơn dự kiến.

### 3.1. Cấu hình để thực sự trì hoãn checkout sau khi bắt đầu transaction

Hibernate có property:

```properties
hibernate.connection.provider_disables_autocommit=true
```

Ý nghĩa của nó là **cam kết với Hibernate rằng `ConnectionProvider` luôn trả về connection đã có `autoCommit=false`**. Khi bảo đảm này đúng, Hibernate có thể bỏ qua thao tác checkout sớm chỉ để chỉnh autocommit:

```text
T0  openSession()                   : chưa checkout
T1  beginTransaction()              : chưa nhất thiết checkout
T2  logic không truy cập database  : vẫn chưa checkout
T3  find()/flush()/JDBC callback   : checkout nếu thực sự cần JDBC
T4  commit()                        : transaction completion
T5  release                         : trả handle về pool
```

**Điều kiện bắt buộc:** pool/provider thực tế phải cấu hình `autoCommit=false` cho **mọi** connection mà Hibernate có thể nhận. Đặt `provider_disables_autocommit=true` mà pool vẫn phát connection ở `autoCommit=true` có thể khiến lệnh SQL được thực hiện **ngoài transaction dự kiến**, làm hỏng tính nguyên tử và khả năng rollback.

Không nhầm hai property:

| Thuộc tính | Bản chất |
| --- | --- |
| `hibernate.connection.provider_disables_autocommit=true` | Lời xác nhận để Hibernate **tin** provider trả connection có autocommit đã tắt |
| `hibernate.connection.autocommit=false` | Yêu cầu xử lý autocommit đối với **một số** loại connection provider Hibernate cung cấp; không thay thế cấu hình pool bên ngoài |
| Cấu hình `autoCommit=false` trực tiếp trên pool | Thiết lập trạng thái các connection do chính pool phát ra; phụ thuộc khả năng hỗ trợ của pool |

Nếu dùng một `DataSource` bên ngoài, **đừng mặc định** cho rằng `hibernate.connection.autocommit=false` đủ để ép trạng thái connection của datasource. Hibernate documentation ghi nhận provider dựa trên datasource có quy tắc riêng.

### 3.2. Ví dụ với HikariCP và Hibernate

Giả sử ứng dụng sử dụng HikariCP làm pool và đã kiểm chứng pool cấp connection với autocommit tắt:

```java
HikariConfig hikari = new HikariConfig();
hikari.setJdbcUrl(System.getenv("JDBC_URL"));
hikari.setUsername(System.getenv("DB_USER"));
hikari.setPassword(System.getenv("DB_PASSWORD"));
hikari.setAutoCommit(false); // Quan trọng: pool phải thực sự bảo đảm trạng thái này

HikariDataSource dataSource = new HikariDataSource(hikari);
```

Khi đưa `dataSource` vào cấu hình Hibernate, có thể dùng:

```properties
hibernate.connection.handling_mode=DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION
hibernate.connection.provider_disables_autocommit=true
```

Đoạn mã chỉ minh họa **phần cấu hình connection pool**, chưa bao gồm khởi tạo `SessionFactory`, mapping entity và đóng datasource khi ứng dụng dừng. Với Spring Boot, việc điều chỉnh pool và giao dịch do framework quản lý cần được xác nhận cùng `JpaTransactionManager`/JTA đang dùng.

## 4. Mặc định trong JTA khác resource-local như thế nào?

**JTA (Jakarta Transactions)** có thể phối hợp nhiều resource và thường được quản lý bởi container/transaction manager. Theo tài liệu Hibernate, default connection handling cho JTA là:

```text
DELAYED_ACQUISITION_AND_RELEASE_AFTER_STATEMENT
```

Trong môi trường JTA được quản lý phù hợp:

```text
JTA transaction bắt đầu
  ├─ SQL A : Hibernate checkout → execute → release handle
  ├─ xử lý khác / gọi service khác
  ├─ SQL B : Hibernate checkout → execute → release handle
  └─ JTA commit / rollback
```

Lợi ích của cách xử lý này bao gồm giảm việc Hibernate giữ handle qua các bước chuyển giữa component, ví dụ khi transaction đi qua nhiều EJB; một số application server xem việc nắm giữ connection qua boundary đó là “leak” dù thực tế là giao dịch vẫn đang hoạt động.

Tuy nhiên, container/transaction manager có thể vẫn **giữ liên kết connection với transaction hoặc thread**, để lần checkout tiếp theo trả đúng tài nguyên cần thiết. Điều kiện để `AFTER_STATEMENT` hoạt động đúng là nhà cung cấp connection bảo đảm ngữ nghĩa transaction.

**Không áp dụng máy móc `AFTER_STATEMENT` vào resource-local** chỉ để tăng lượng connection rảnh: một JDBC transaction không thể được ghép tùy tiện từ các physical connection khác nhau nếu provider không bảo đảm đúng semantics. Với provider không hỗ trợ aggressive release, Hibernate có thể chuyển về after-transaction.

### 4.1. Bảng so sánh hai transaction coordinator

| Tiêu chí | Resource-local | JTA |
| --- | --- | --- |
| Điều khiển transaction điển hình | Hibernate/JDBC connection commit/rollback hoặc framework resource-local transaction manager | JTA transaction manager/container |
| Default handling mode theo Hibernate user guide | `DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION` | `DELAYED_ACQUISITION_AND_RELEASE_AFTER_STATEMENT` |
| Lấy connection khi bắt đầu transaction | Có thể lấy sớm để kiểm tra/tắt autocommit | Tùy transaction manager/provider và nhu cầu JDBC |
| Trả connection | Sau transaction completion | Sau statement khi có thể release an toàn |
| Điều kiện cần chú ý | Pool autocommit, transaction duration | Aggressive release, JTA enlistment, provider/container |
| Điểm dễ hiểu sai | Chữ `DELAYED` không bảo đảm chờ tới SQL đầu tiên | “Release” không nhất thiết giải phóng kết nối vật lý khỏi transaction |

Trong dự án Spring dùng Spring Data JPA, không phải cứ có `@Transactional` là đang dùng JTA. Một ứng dụng Spring Boot đơn giản với `JpaTransactionManager` và datasource thông thường thường dùng transaction **resource-local**. Cần xem **transaction manager thực tế**, thay vì suy đoán từ tên annotation.

## 5. Vòng đời `Session` không giống vòng đời `Connection`

Cùng một `Session`, hai transaction liên tiếp có thể sử dụng hai lần checkout khác nhau:

```java
try (Session session = sessionFactory.openSession()) {
    Transaction first = session.beginTransaction();
    session.find(Book.class, 1L);
    first.commit(); // AFTER_TRANSACTION: trả Connection

    // Session còn mở, persistence context vẫn tồn tại.
    // Chưa thể kết luận Connection vẫn đang được giữ.

    Transaction second = session.beginTransaction();
    session.find(Book.class, 2L);
    second.commit(); // Trả Connection của transaction thứ hai
}
```

Ví dụ trên nhằm minh họa **mốc release**, không khuyến nghị giữ cùng một `Session` lâu dài. Với ứng dụng nghiệp vụ thông thường, nên giới hạn session/persistence context theo đơn vị công việc. Persistence context giữa hai transaction vẫn có thể giữ entity trong bộ nhớ và đưa tới dữ liệu cũ nếu không được quản lý cẩn thận.

### 5.1. Các thao tác nào có thể buộc Hibernate lấy connection?

Không phải mọi lệnh trên `Session` đều phát sinh SQL. Một vài tình huống:

| Hoạt động | Có nhất thiết checkout connection? | Giải thích |
| --- | --- | --- |
| `sessionFactory.openSession()` với delayed mode | Không | Mở abstraction và context |
| `session.beginTransaction()` resource-local | Thường có, nếu phải xử lý autocommit | Có thể checkout trước SQL |
| `session.persist(entity)` | Không phải luôn ngay lúc gọi | SQL `INSERT` có thể được trì hoãn đến flush; một số chiến lược sinh ID cần insert sớm |
| `session.find(...)` | Không chắc chắn | Có thể trả từ first-level cache, second-level cache nếu được cấu hình, hoặc phải SELECT |
| `session.getReference(...)` | Không chắc chắn | Có thể tạo proxy/reference trước khi cần SQL; truy cập thuộc tính có thể phát SELECT |
| `session.flush()` | Có khi cần thực thi SQL | Nếu có DML cần đồng bộ; flush không đồng nghĩa commit |
| `session.doWork(connection -> ...)` | Có | Callback cần một JDBC connection |
| Đọc database metadata | Có | Một số thao tác metadata/config/runtime có thể cần connection |
| `session.clear()` | Không phải mốc release | Chỉ clear các entity managed khỏi persistence context |
| `tx.commit()` | Có thể flush/commit; sau đó release theo mode | Thời điểm trả không thể suy ra từ `flush()` |
| `session.close()` | Giải phóng tài nguyên còn giữ | Không nhất thiết là lần đầu tiên connection được trả |

**First-level cache** và metadata có thể làm một đoạn code không đụng tới database dù tên hàm là `find`. Vì vậy, khi minh họa thời điểm checkout bằng truy vấn, phải xác nhận truy vấn đó thực sự thực thi SQL.

### 5.2. `flush()` không tương đương `commit()` hoặc `close()`

Giả sử:

```java
Transaction tx = session.beginTransaction();
session.persist(new Book("Hibernate"));
session.flush();   // Gửi SQL INSERT nếu cần
// Transaction vẫn đang hoạt động.
// Với AFTER_TRANSACTION, Connection có thể vẫn đang được giữ.
tx.commit();       // Hoàn tất transaction, sau đó Hibernate có thể release.
```

`flush()` làm Hibernate đồng bộ các thay đổi của persistence context với database. Sau `flush()`, các thao tác đó vẫn có thể bị rollback; không mặc định trả connection vào pool. Mode `AFTER_STATEMENT` có thể release handle giữa các statement nếu môi trường cho phép, nhưng transaction vẫn chưa kết thúc.

## 6. Tài nguyên JDBC đang mở có thể trì hoãn việc release

Connection không thể được release một cách an toàn nếu một số tài nguyên đang sử dụng nó chưa kết thúc. Các tình huống quan trọng:

- **Scrollable results/cursor:** kết quả đang duyệt tiếp từ database nên thường cần connection tiếp tục sống.
- **Streaming result:** với API stream truy vấn, phải đóng stream để giải phóng các tài nguyên mà Hibernate đang giữ.
- **JDBC callback:** không lấy `Connection` trong `doWork()` rồi giữ nó sau khi callback kết thúc; callback phải hoàn tất trước khi Hibernate quyết định release.
- **PreparedStatement/ResultSet thủ công:** đóng bằng `try-with-resources` ngay trong cùng phạm vi làm việc.

Ví dụ với Hibernate Query stream:

```java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        try (java.util.stream.Stream<Book> books =
                 session.createQuery(
                     "select b from Book b order by b.id",
                     Book.class
                 ).getResultStream()) {

            books.forEach(book -> process(book));
        }

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
```

Đoạn code giả định `process(book)` là phương thức của ứng dụng. **Đóng stream trước khi kết thúc transaction/session** giúp tránh giữ result resources. Khi dùng stream để xử lý lượng dữ liệu lớn, còn cần kiểm soát batch/fetch, bộ nhớ persistence context và phương thức đọc của driver.

### 6.1. JDBC thủ công trong session

```java
session.doWork(connection -> {
    // Hibernate cấp connection phù hợp với Session/transaction hiện tại.
    try (java.sql.PreparedStatement ps = connection.prepareStatement(
             "update books set last_viewed_at = current_timestamp where id = ?")) {
        ps.setLong(1, 10L);
        ps.executeUpdate();
    }

    // KHÔNG gọi connection.close() tại đây.
    // Hibernate/provider quyết định khi nào release connection.
});
```

Nếu trực tiếp dùng JDBC để thay đổi hàng đã được map thành entity đang managed, trạng thái trong persistence context có thể không còn đồng bộ với database; cần cân nhắc flush/refresh/clear và thứ tự xử lý. Đó là vấn đề **tính nhất quán dữ liệu**, khác với chính sách checkout/release connection.

## 7. Trường hợp ứng dụng tự cung cấp JDBC connection

Hibernate cho phép mở session với `Connection` có sẵn:

```java
java.sql.Connection external = dataSource.getConnection();

try {
    try (Session session = sessionFactory
            .withOptions()
            .connection(external)
            .openSession()) {

        // Sử dụng session với connection do ứng dụng cung cấp.
        Book book = session.find(Book.class, 10L);
    }
} finally {
    external.close(); // Ứng dụng trả connection do mình đã tự mượn.
}
```

Ở đây, **ứng dụng mượn connection trước**, rồi cung cấp cho Hibernate. Theo Hibernate user guide, cách mở này chọn semantics **`IMMEDIATE_ACQUISITION_AND_HOLD`**: session sử dụng connection từ lúc khởi tạo đến lúc đóng. Ứng dụng chịu trách nhiệm quản lý kết nối ngoài session, bao gồm trả về pool khi đã hoàn tất. Mẫu này có thể làm phức tạp quản lý transaction; trong ứng dụng thông thường nên ưu tiên để Hibernate/framework dùng `DataSource`/`ConnectionProvider` trực tiếp.

> Ví dụ chỉ tập trung vào quyền sở hữu connection. Khi làm việc thật, còn phải quản lý transaction/rollback và trạng thái autocommit của `external` phù hợp với datasource; không coi `session.close()` là lời gọi thay thế cho việc đóng handle do ứng dụng tự mượn.

## 8. Cấu hình trong ứng dụng và hệ quả

### 8.1. Cấu hình Hibernate thuần

Ví dụ `hibernate.properties`:

```properties
# Resource-local: acquire theo nhu cầu, release khi transaction kết thúc.
hibernate.connection.handling_mode=DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION

# Chỉ bật nếu provider/pool chắc chắn trả Connection với autoCommit=false.
# hibernate.connection.provider_disables_autocommit=true
```

Với cấu hình qua `Map`, dùng cùng property:

```java
Map<String, Object> settings = new HashMap<>();
settings.put(
    "hibernate.connection.handling_mode",
    "DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION"
);
```

Đoạn `Map` là một phần cấu hình; để sử dụng phải truyền nó vào quy trình bootstrap Hibernate. Nếu không có nhu cầu thay đổi hành vi, việc giữ **mặc định của transaction coordinator** thường đơn giản và an toàn hơn.

### 8.2. Cấu hình qua Spring Boot

Ví dụ `application.properties` khi thực sự có lý do chọn handling mode:

```properties
spring.jpa.properties.hibernate.connection.handling_mode=DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION
```

Nếu muốn Hibernate trì hoãn checkout qua bước `beginTransaction()` và dùng **HikariCP** do Spring Boot quản lý, một cách phối cấu hình có điều kiện là:

```properties
# Chỉ áp dụng khi đã kiểm chứng HikariCP thực sự cấp connection autoCommit=false.
spring.datasource.hikari.auto-commit=false
spring.jpa.properties.hibernate.connection.provider_disables_autocommit=true
```

Không bật property thứ hai nếu không chắc toàn bộ connection Hibernate nhận được đều đã `autoCommit=false`. Trong ứng dụng có JTA, datasource do container quản lý hoặc routing/multitenancy datasource, cần xét riêng lifecycle và người sở hữu connection. Các tên cấu hình bên trên **không khẳng định** mọi phiên bản Boot và mọi transaction manager đều có timing giống hệt nhau.

### 8.3. Đặt handling mode bằng `SessionBuilder`

Một số bản Hibernate hỗ trợ API đặt mode ở mức session, ví dụ:

```java
Session session = sessionFactory.withOptions()
    .connectionHandling(
        org.hibernate.ConnectionAcquisitionMode.AS_NEEDED,
        org.hibernate.ConnectionReleaseMode.AFTER_TRANSACTION
    )
    .openSession();
```

API này có thể phụ thuộc phiên bản Hibernate; hãy tra Javadoc của bản đang dùng. Quy tắc hợp lệ là **acquisition `IMMEDIATELY` chỉ đi với release `ON_CLOSE`**. Nếu chọn release sau statement, vẫn phải thỏa điều kiện provider hỗ trợ aggressive release.

## 9. Quan sát checkout/release đúng cách

Chỉ bật log SQL không đủ. Log:

```text
Hibernate:
  select b1_0.id, b1_0.title from books b1_0 where b1_0.id=?
```

chỉ chứng minh một statement được gửi; nó **không nói** Hibernate checkout connection trước đó bao lâu và lúc nào đã trả connection.

Một số công cụ thích hợp:

| Nguồn quan sát | Thấy được | Lưu ý |
| --- | --- | --- |
| Pool metrics (`active`, `idle`, `pending`) | Số connection đang mượn, rảnh, chờ theo thời điểm | Là trạng thái pool, không đồng nghĩa số transaction hoặc số SQL |
| HikariCP DEBUG/TRACE hoặc pool-specific logging | Những sự kiện pool liên quan tới borrow/return và cấu hình | Tùy phiên bản, logging level và loại pool |
| `ConnectionProvider`/DataSource proxy | Lúc gọi `getConnection()` và `close()` trên handle | Dùng wrapper an toàn, không log password/JDBC URL nhạy cảm |
| Hibernate JDBC/connection logs | Một số sự kiện bên trong Hibernate | Tên logger và nội dung thay đổi giữa các phiên bản |
| Metrics database/server | Session/kết nối thật đang mở, transaction đang chạy | Pool có thể giữ nhiều physical connections đang idle |
| Transaction tracing | Bắt đầu, kết thúc, thời gian giữ transaction | Cần kết hợp với pool metrics để định vị checkout sớm |

### 9.1. Thí nghiệm lý thuyết để so sánh

Với một `DataSource` có pool, một entity đã được mapping và một database đã sẵn sàng, có thể so sánh 3 tình huống:

**A. Mặc định resource-local, pool autocommit chưa được cam kết tắt**

```text
openSession()
beginTransaction()    ← dự kiến có thể thấy active connection tăng
chờ/thực hiện logic Java
find()                ← SELECT
commit()              ← active connection giảm sau transaction completion
closeSession()
```

**B. Resource-local, pool autoCommit=false và provider flag=true**

```text
openSession()
beginTransaction()    ← chưa nhất thiết mượn connection
logic Java thuần
find()                ← mượn connection nếu thật sự có SELECT
commit()              ← trả sau transaction completion
closeSession()
```

**C. Immediate-and-hold**

```text
openSession()         ← mượn connection ngay
logic Java thuần
beginTransaction()
find()
commit()
closeSession()        ← trả connection
```

Đây là **kỳ vọng cần đối chiếu với metrics/log**, không phải kết quả kiểm thử đã thực hiện. Metadata, ID generation, SQL tự động và hạ tầng transaction có thể làm thời điểm checkout thực tế khác timeline tối giản.

### 9.2. Một thao tác đo có thể làm sai kết quả

Để “kiểm tra có connection chưa”, nhiều người gọi:

```java
session.doReturningWork(java.sql.Connection::getAutoCommit);
```

Nhưng lời gọi này **tự nó buộc Hibernate cung cấp JDBC connection**. Nếu được chèn trước truy vấn để đo delayed acquisition, kết quả sẽ bị thay đổi bởi chính phép đo. Nên quan sát ở **pool/provider**, hoặc ghi log các lần checkout/return, thay vì lấy connection trong code chỉ để kiểm tra.

## 10. Tác động tới pool, hiệu năng và độ ổn định

### 10.1. Khoảng chờ trong transaction vẫn tiêu tốn connection

Giả sử 30 request đồng thời đều:

1. `beginTransaction()`.
2. Chờ API bên ngoài 3 giây.
3. Thực hiện một `SELECT`.
4. `commit()`.

Với resource-local mặc định và checkout tại bước 1, các request có thể giữ 30 connection trong phần lớn thời gian chờ. Nếu pool chỉ có 10 connection, những request sau có thể phải đợi và hết thời gian chờ (`connectionTimeout`).

Trì hoãn checkout có thể giúp **giảm thời gian giữ connection** trong tình huống này, nhưng không thay thế thiết kế transaction hợp lý: tốt hơn là thực hiện call bên ngoài **trước hoặc sau transaction database** nếu nghiệp vụ cho phép, và giữ transaction càng ngắn càng tốt.

### 10.2. `AFTER_STATEMENT` không tự động tốt hơn

Trả handle sau mỗi statement có thể làm tăng số lần tương tác với pool/provider và chỉ an toàn khi provider bảo đảm ngữ nghĩa transaction. Với JTA container có connection gắn theo transaction, việc release/re-acquire có thể vẫn dùng physical connection cũ. Vì vậy không nên coi mode này là “luôn giảm số connection đang dùng” hoặc “luôn tăng throughput”.

### 10.3. `HOLD` dễ gây pool starvation

Nếu session sống lâu, kể cả qua nhiều bước xử lý không dùng database, mode `IMMEDIATE_ACQUISITION_AND_HOLD` hoặc `DELAYED_ACQUISITION_AND_HOLD` có thể kéo dài thời gian chiếm connection. Hạn chế scope session, đóng session chắc chắn, tránh *session-per-application* và không chia sẻ `Session` giữa các thread.

### 10.4. Một số truy vấn khóa làm transaction cần giữ lâu hơn

SQL như `SELECT ... FOR UPDATE` hoặc transaction với nhiều thay đổi cần giữ cùng transaction tới commit/rollback. Việc trả một handle cho pool không có nghĩa transaction DB đã kết thúc hoặc lock đã được giải phóng; lock phụ thuộc transaction completion. **Đừng thay connection handling mode để chữa lock contention**; cần kiểm tra thời gian transaction, câu SQL, index, isolation và chiến lược khóa.

## 11. Các ngộ nhận và cách giải thích

### “`openSession()` lúc nào cũng gọi `DataSource.getConnection()`”

Không. Với delayed mode, `Session` có thể được tạo trước khi lấy JDBC connection. Nhưng tạo `SessionFactory`, khởi tạo pool hoặc đọc database metadata trong lúc bootstrapping có thể mở connection **ngoài vòng đời của session**. Đừng quy mọi connection quan sát lúc startup cho `openSession()`.

### “`beginTransaction()` không thực hiện SQL nên không mượn connection”

Sai trong nhiều cấu hình resource-local. Hibernate có thể phải nhận connection để bảo đảm autocommit tắt. Muốn trì hoãn hơn phải có **bảo đảm từ pool/provider** và cấu hình tương ứng.

### “`releaseAfterTransaction` nghĩa là `closeSession()`”

Không. Với `AFTER_TRANSACTION`, connection có thể được trả ngay sau `commit()` hoặc `rollback()` khi session vẫn còn mở. `Session.close()` vẫn phải được gọi để giải phóng các tài nguyên và trạng thái của session.

### “`AFTER_STATEMENT` luôn trả connection sau từng `SELECT`”

Không hoàn toàn. Open cursor/stream/`ResultSet`, khả năng aggressive release của provider và transaction manager có thể ngăn hoặc trì hoãn release. Provider không hỗ trợ có thể dẫn tới chiến lược after-transaction.

### “Connection được `close()` là kết nối database vật lý bị hủy”

Không nhất thiết. Với pool, `Connection.close()` thường là **trả về pool**. Physical connection có thể tồn tại cho request tiếp theo; việc đóng socket là quyết định của pool khi idle timeout, max lifetime, shutdown hoặc xảy ra lỗi.

### “Sau `flush()` là đã trả connection”

Sai. `flush()` gửi SQL nhưng không hoàn tất transaction. Connection release phụ thuộc handling mode và trạng thái transaction/tài nguyên đang mở.

### “Đổi sang `provider_disables_autocommit=true` lúc nào cũng tăng hiệu năng”

Không. Đây là **khai báo một sự thật về provider**, không phải công tắc tối ưu độc lập. Cấu hình sai là lỗi về giao dịch và dữ liệu, nghiêm trọng hơn độ trễ hoặc pool exhaustion.

## 12. Tình huống thực tế và lựa chọn cấu hình

| Tình huống | Cách tiếp cận hợp lý | Điều cần xác minh |
| --- | --- | --- |
| Dịch vụ CRUD resource-local thông thường | Giữ mặc định `DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION` | Thời điểm begin có mượn connection, thời lượng transaction |
| Resource-local, nhiều xử lý Java trước SQL | Xem xét pool autocommit=false + `provider_disables_autocommit=true` | Pool thực sự bảo đảm autocommit=false; không có provider phụ trả trạng thái khác |
| Container JTA với provider hỗ trợ aggressive release | Theo mặc định JTA, thường `AFTER_STATEMENT` | JTA enlistment, resource vẫn mở, khả năng tái nhận connection |
| Session dài do công cụ/framework đặc thù | Tránh các mode HOLD nếu không cần | Scope session, số active connections, cleanup |
| Ứng dụng tự cấp connection cho Hibernate | Quản lý connection tại ứng dụng; semantics immediate/hold | Ai mượn, ai commit/rollback và ai đóng connection |
| Thấy pool hết connection khi lưu lượng cao | Đo active/pending và transaction duration trước khi đổi mode | Leak thực, SQL lâu, call ngoài trong transaction, open stream/cursor |

Không có mode “tốt nhất cho mọi hệ thống”. Có những ràng buộc do transaction coordinator, provider và framework quyết định; một thay đổi tối ưu trên máy thử nghiệm cũng có thể không phù hợp môi trường JTA hoặc database sản xuất.

## 13. Bài tập tự giải thích vòng đời

**Tình huống 1**

Ứng dụng dùng resource-local mặc định, `Session` còn mở sau khi `commit()` thành công. Connection được trả khi nào?

**Giải thích:** Theo mode mặc định `DELAYED_ACQUISITION_AND_RELEASE_AFTER_TRANSACTION`, Hibernate trả connection sau **transaction completion**; session vẫn mở không có nghĩa connection vẫn bị giữ. Cần tiếp tục đóng `Session` để dọn các tài nguyên ORM.

**Tình huống 2**

Dự án dùng HikariCP với `autoCommit=true` nhưng cấu hình:

```properties
hibernate.connection.provider_disables_autocommit=true
```

Kết quả nào đáng lo?

**Giải thích:** Hibernate được báo sai rằng mọi connection nhận về đã tắt autocommit. SQL có thể chạy auto-commit ngay khi được gửi, dẫn tới dữ liệu không rollback như transaction mong đợi. Phải sửa lại cấu hình cho nhất quán và kiểm tra cả môi trường triển khai.

**Tình huống 3**

Một truy vấn trả stream để ứng dụng duyệt trong 2 phút. Hibernate được cấu hình release-after-statement. Có thể khẳng định connection đã trở lại pool sau `executeQuery()` không?

**Giải thích:** Không. Stream/cursor đang mở có thể giữ tài nguyên JDBC và làm trì hoãn release. Cần đóng stream/cursor và xem provider có hỗ trợ aggressive release.

**Tình huống 4**

JTA container hiển thị nhiều “release” trong log Hibernate, nhưng metrics database không giảm số connection. Có mâu thuẫn không?

**Giải thích:** Không. Hibernate có thể release logical handle trong khi transaction manager/pool giữ physical connection để tái sử dụng hoặc bảo đảm JTA semantics. Cần phân biệt metrics borrowed/idle ở pool với connection vật lý trên server.

**Tình huống 5**

Dùng delayed acquisition, nhưng ngay khi bật ứng dụng đã thấy database có 5 connection. Hibernate có trái cấu hình không?

**Giải thích:** Không nhất thiết. Pool có thể tạo sẵn connection tối thiểu; quá trình bootstrap/metadata/schema validation cũng có thể cần JDBC. Delayed acquisition nói về thời điểm session lấy connection để làm việc, không cấm mọi connection ở mức toàn ứng dụng.

## 14. Nguồn tham khảo và cách tra đúng phiên bản

Các chế độ có thể thay đổi về tài liệu mô tả hoặc khả năng API giữa các dòng Hibernate. Khi dự án dùng phiên bản cụ thể, ưu tiên documentation tương ứng:

- [Hibernate ORM User Guide 7.2 — Connection handling](https://docs.hibernate.org/orm/7.2/userguide/html_single/#database-connection-handling): acquisition/release mode, resource-local và JTA, connection do ứng dụng cung cấp.
- [Hibernate ORM User Guide 6.4 — Connection handling](https://docs.hibernate.org/orm/6.4/userguide/html_single/#database-connection-handling): cùng mô hình với hệ thống Hibernate 6.x.
- [Hibernate ORM User Guide 8.0 — Database access](https://docs.hibernate.org/orm/8.0/userguide/html_single/): mô tả connection acquisition/release, ownership và những lưu ý về tài nguyên JDBC còn mở.
- [Hibernate Javadoc — `PhysicalConnectionHandlingMode`](https://docs.hibernate.org/orm/7.0/javadocs/org/hibernate/resource/jdbc/spi/PhysicalConnectionHandlingMode.html): ý nghĩa enum và những tổ hợp acquisition/release hợp lệ.
- [Hibernate Javadoc — `ConnectionProvider`](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/engine/jdbc/connections/spi/ConnectionProvider.html): điều kiện hỗ trợ `supportsAggressiveRelease()`.
- [Hibernate Javadoc — JDBC settings](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/cfg/JdbcSettings.html): ý nghĩa và rủi ro của `hibernate.connection.provider_disables_autocommit`.
- [Hibernate Javadoc — `SessionBuilder`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/SessionBuilder.html): connection do ứng dụng cung cấp và cấu hình handling mode ở mức session.

## Kết luận

Muốn biết connection được lấy và trả khi nào, hãy xác định **ai sở hữu connection, transaction coordinator nào đang chạy, handling mode nào có hiệu lực, provider có thể aggressive release hay không và autocommit của pool thực tế là gì**. Với resource-local mặc định, mốc trả thường là transaction completion; mốc lấy có thể là `beginTransaction()` do autocommit. Với JTA mặc định, Hibernate có thể release handle sau từng statement nhưng container vẫn quản lý connection liên kết với transaction. Quan sát pool/provider và transaction cùng lúc mới phản ánh đúng vòng đời kết nối, thay vì suy từ mỗi lệnh mở/đóng `Session` hoặc log SQL.
