# Phân biệt API luồng kết quả và cách provider thực sự tải dữ liệu

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Hiệu năng

Một truy vấn JPA trả về một triệu bản ghi có thể khiến ứng dụng tốn nhiều bộ nhớ. Khi thấy `getResultList()` trả về `List`, lập trình viên thường muốn thay bằng `getResultStream()` vì `Stream` trong Java gợi ý việc xử lý tuần tự, lười (*lazy*), từng phần tử. Tuy nhiên, **trả về `Stream<T>` không bảo đảm database chỉ gửi một phần kết quả mỗi lần, provider không materialize cả result set, hoặc persistence context không tích lũy entities**.

Điều phải phân biệt là **ba tầng độc lập**:

1. **API tầng Java:** `getResultStream()`, `getResultList()`, `Stream.map/filter/limit` và `Stream.close()`.
2. **JPA provider/ORM:** Hibernate hoặc provider khác quyết định dựng danh sách trước hay dùng scroll/cursor, hydrate entity/DTO, quản lý identity map, batch loading và flush/dirty checking.
3. **JDBC driver và database:** `ResultSet`, `fetchSize`, server-side cursor, wire protocol, transaction/autocommit, prefetch và thời gian giữ connection.

Một API có tên “stream” chỉ nói cách **người gọi tiêu thụ kết quả**, không đủ để kết luận cơ chế thực tế ở hai tầng phía dưới.

Bài này đi từ nguyên lý, ví dụ Spring/JPA/Hibernate, trường hợp PostgreSQL/MySQL, phương án phân trang/keyset, cho tới cách kiểm chứng bằng SQL, metrics và thử nghiệm bộ nhớ. Các chi tiết extension được ghi rõ là **Hibernate-specific**; hành vi JDBC cursor phụ thuộc driver/database/version/configuration nên phải đo trên hệ thống thật.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt *Java Stream API* với *database cursor/streaming result set*.
2. Giải thích vì sao `Query.getResultStream()` không mặc nhiên giảm sử dụng heap.
3. Hiểu triển khai mặc định `getResultList().stream()` có thể tồn tại ở tầng chuẩn JPA.
4. Biết provider như Hibernate có thể override cách lấy stream qua scrollable results.
5. Giải thích `JDBC fetch size` là hint về cách nhận rows, không phải SQL `LIMIT`.
6. Nhận biết tác động của JDBC driver, autocommit, transaction và server-side cursor.
7. Biết khi nào `ResultSet.TYPE_FORWARD_ONLY` chưa đủ chứng minh dữ liệu đọc tăng dần.
8. Viết consumer dùng `try-with-resources` để đóng `Stream` đúng lúc.
9. Bảo đảm `EntityManager`/transaction/connection sống đủ lâu cho việc đọc.
10. Tránh trả `Stream<Entity>` qua boundary nơi persistence context đã đóng.
11. Phân biệt fetch size, JDBC batching, Hibernate `@BatchSize` và JPQL `setMaxResults`.
12. Hiểu rủi ro `collect(toList)`, `sorted()`, `distinct()`, `groupingBy()` và `parallel()` trên stream lớn.
13. Đẩy `WHERE`, `ORDER BY`, `LIMIT` và aggregation xuống database khi phù hợp.
14. Hiểu vì sao stream entities vẫn có thể làm **first-level cache/persistence context tăng**.
15. Biết khi nào nên chọn DTO/scalar projection thay vì managed entities.
16. Sử dụng Hibernate `scroll(ScrollMode.FORWARD_ONLY)` khi cần API cursor rõ hơn.
17. Chọn cách kiểm soát persistence context bằng read-only mode, detach/clear hoặc StatelessSession khi thích hợp.
18. Phân biệt một query streaming với nhiều truy vấn lazy N+1.
19. Tránh JOIN FETCH nhiều collection làm tăng số SQL rows trong một stream.
20. Sử dụng keyset pagination hoặc chunk processing để giới hạn cả data, memory và thời gian giữ connection.
21. Hiểu keyset pagination không tự mang snapshot consistency qua nhiều transactions.
22. Đánh giá xử lý export/report lớn và nguy cơ giữ DB connection khi client tải file chậm.
23. Thiết kế integration test phát hiện provider materialization/driver buffering.
24. Đo peak heap, GC, JDBC rows, SQL count, fetch round trips và transaction duration.
25. Chọn chiến lược phù hợp giữa `List`, `Stream`, scroll, pagination, DTO và JDBC.

---

## 2. Tình huống: xuất danh sách đơn hàng rất lớn

Giả sử ứng dụng cần xuất 2 triệu đơn hàng:

```text
purchase_orders
  id
  order_code
  created_at
  status
  grand_total
  version
```

Với phương án tải toàn bộ:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o ORDER BY o.id",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    export(order);
}
```

Vấn đề:

- Có thể giữ một danh sách rất lớn trong heap.
- ORM có thể quản lý nhiều entity instances và snapshots trong persistence context.
- Không phải mọi response/export đều cần toàn bộ các columns của entity.
- Các associations được truy cập trong vòng lặp có thể kích hoạt thêm SQL.
- Một transaction/connection kéo dài suốt quá trình xuất dữ liệu nếu triển khai không cẩn thận.

Người phát triển đổi:

```java
try (Stream<PurchaseOrder> stream = em.createQuery(
        "SELECT o FROM PurchaseOrder o ORDER BY o.id",
        PurchaseOrder.class
    ).getResultStream()) {

    stream.forEach(this::export);
}
```

Đây là bước cải thiện **cách viết consumer**, nhưng chưa đủ bằng chứng rằng số rows đang được nạp từ database theo từng đợt hoặc heap ổn định.

---

## 3. Ba tầng của đường đi dữ liệu

```text
                       APPLICATION CODE
                Query.getResultStream()
                       Stream.forEach()
                              |
                              v
                         JPA PROVIDER
                  Hibernate / EclipseLink / ...
                      Query execution plan
               Entity hydration, persistence context
                 List or scroll/result iterator
                              |
                              v
                          JDBC DRIVER
                PreparedStatement + ResultSet
                  fetchSize / cursor / buffering
                              |
                              v
                           DATABASE
                     SQL execution plan
                   server cursors / result rows
                              |
                              v
                        NETWORK / JVM
                Rows/batches crossing connection
```

Mỗi tầng có quyền quyết định khác nhau:

| Tầng | Quyết định tiêu biểu | Điều không tự bảo đảm |
|---|---|---|
| Java Stream | Consumer duyệt thế nào, operations nào áp dụng | Không bắt DB dùng cursor |
| JPA provider | List hay scroll, hydrate entity/DTO, session state | Không bắt JDBC driver bỏ buffering |
| JDBC driver | Fetch/prefetch, wire protocol, cursor behavior | Không xóa first-level cache của ORM |
| Database | Thực thi query, sort/aggregate, locks/snapshots | Không biết Java `Stream.limit()` là yêu cầu SQL LIMIT |
| Transaction | Isolation, connection lifetime, commit/rollback | `readOnly` không tự chọn fetch size |

**Kết luận:** Muốn biết có streaming thực sự hay không, phải kiểm tra **cả implementation và execution behavior**.

---

## 4. `getResultList()` và `getResultStream()` khác gì?

JPA cung cấp:

```java
List<PurchaseOrder> list =
    query.getResultList();
```

và, từ JPA 2.2 trở đi, có API:

```java
Stream<PurchaseOrder> stream =
    query.getResultStream();
```

### 4.1. Hợp đồng `getResultList()`

Kết quả được trả dưới dạng danh sách Java. Từ góc nhìn caller, mọi phần tử của result list đã sẵn sàng để truy cập. Provider có thể có các tối ưu nội bộ, nhưng một result list lớn thường kéo theo memory pressure đáng kể, đặc biệt nếu là managed entities.

### 4.2. Hợp đồng `getResultStream()`

API trả về `java.util.stream.Stream` cho việc duyệt kết quả. **Chuẩn JPA không bắt buộc mọi provider dùng server-side cursor hoặc giữ heap hằng số** chỉ vì API là Stream.

Một implementation mặc định về mặt ý tưởng có thể tương đương:

```java
default Stream<?> getResultStream() {
    return getResultList().stream();
}
```

Vì vậy nếu provider không có streaming implementation riêng, **trước khi caller đọc phần tử đầu tiên, toàn bộ danh sách có thể đã được materialize**.

### 4.3. Provider có thể override

Hibernate trong các phiên bản tương ứng triển khai stream bằng cơ chế scrollable results. Nhưng đây không phải cam kết rằng database driver thật sự truyền từng batch hoặc persistence context không lớn lên.

### 4.4. Không dùng kiểu trả về để suy performance

```java
Stream<T> != server-side cursor guarantee
List<T>   != always worst possible strategy
```

Một query giới hạn 20 rows trả `List` thường an toàn và đơn giản hơn một stream chạy nhiều giờ.

---

## 5. “Lazy” ở Java không có nghĩa “lazy” ở database

Java Stream có hai nhóm operations.

**Intermediate operations** tạo pipeline:

```java
stream
    .filter(row -> row.isActive())
    .map(row -> row.getId());
```

**Terminal operations** kích hoạt xử lý:

```java
stream.forEach(this::process);
stream.count();
stream.collect(Collectors.toList());
```

Tuy nhiên, tính lazy của pipeline không nói gì về **thời điểm provider đã chạy SQL và nhận rows**.

### 5.1. Ví dụ dễ hiểu

```java
Stream<PurchaseOrder> stream =
    query.getResultList().stream();
```

Java Stream chưa được duyệt, nhưng danh sách đã tải xong ở bước `getResultList()`.

### 5.2. Ngược lại, nếu provider dùng cursor

Một stream backed by cursor có thể trì hoãn việc hydrate từng entity cho đến khi terminal operation duyệt. Nhưng driver có thể đã nhận một lượng rows nhất định, database có thể đã thực thi sort hoặc aggregate toàn bộ trước khi gửi row đầu tiên.

### 5.3. Ba khái niệm “lazy” riêng biệt

| Thuật ngữ | Nghĩa |
|---|---|
| Java Stream lazy evaluation | Intermediate operations chỉ được thực hiện khi có terminal consumption |
| JPA lazy association fetching | Association/proxy/collection được tải khi cần theo fetch plan |
| JDBC incremental fetching | Driver nhận kết quả theo các đợt thay vì buffer toàn bộ |

Một ứng dụng có thể có lazy Java Stream nhưng **không** incremental JDBC fetching. Hoặc có streaming JDBC rows nhưng sau đó duyệt lazy associations làm phát N+1 queries.

---

## 6. JDBC ResultSet: cầu nối quan trọng

JDBC có `PreparedStatement` và `ResultSet`:

```java
try (PreparedStatement ps = connection.prepareStatement(
         "SELECT id, order_code FROM purchase_orders ORDER BY id",
         ResultSet.TYPE_FORWARD_ONLY,
         ResultSet.CONCUR_READ_ONLY)) {

    ps.setFetchSize(200);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            String code = rs.getString("order_code");
            process(id, code);
        }
    }
}
```

Code trên minh họa ý định **duyệt một chiều, đọc từng row qua ResultSet**.

### 6.1. Forward-only không bảo đảm server cursor

`TYPE_FORWARD_ONLY` quy định cách duyệt ResultSet, không buộc driver phải giữ toàn bộ kết quả ở server. Driver có thể buffer result set ở phía client, tùy config và DB protocol.

### 6.2. `fetchSize` không phải SQL LIMIT

`ps.setFetchSize(200)` là **hint** về số rows driver nên lấy ở mỗi lần tương tác với database theo cơ chế được hỗ trợ.

Nó **không có nghĩa query chỉ trả 200 rows**. Nếu query có 2 triệu matching rows và consumer đọc hết, cuối cùng vẫn có thể truyền toàn bộ 2 triệu rows.

### 6.3. Driver có quyền diễn giải hint

JDBC fetch size là một hint, behavior phụ thuộc driver, mode và database. Một số drivers cần transaction/autocommit/config đặc biệt mới dùng cursor; một số drivers có prefetch defaults riêng.

### 6.4. ResultSet còn bị ảnh hưởng bởi SQL plan

Ngay cả khi ResultSet được fetch incrementally, SQL có `ORDER BY` thiếu index, `DISTINCT` hay `GROUP BY` có thể yêu cầu database sort/hash/materialize dữ liệu trước khi trả row đầu tiên.

**Ít heap ở client không có nghĩa database không tốn memory/disk temporary space.**

---

## 7. `setMaxResults`, `fetchSize` và `Stream.limit()` khác nhau

Ba cách viết có vẻ “chỉ lấy 100” nhưng semantics rất khác.

### 7.1. JPA `setMaxResults(100)`

```java
query.setMaxResults(100);
```

Yêu cầu query result có tối đa 100 entries theo JPA query semantics. Provider thường dịch sang SQL `LIMIT`/`FETCH FIRST`/cú pháp dialect tương ứng khi có thể.

### 7.2. Hibernate/JDBC fetch size 100

```java
query.unwrap(org.hibernate.query.Query.class)
     .setFetchSize(100);
```

Yêu cầu về **cách JDBC driver lấy rows theo đợt**, không giới hạn tổng số entries.

### 7.3. Java `Stream.limit(100)`

```java
try (Stream<PurchaseOrder> stream =
         query.getResultStream()) {
    stream.limit(100).forEach(this::process);
}
```

Đây là operation của Java Stream. Nếu provider đã materialize toàn bộ result list, `limit(100)` không tiết kiệm việc tải ban đầu. Nếu backed by incremental cursor, short-circuit có thể tránh tiêu thụ hết rows **về phía client**, nhưng driver/database đã prefetch hoặc chạy công việc trước đó.

### 7.4. Bảng so sánh

| Cách giới hạn | Tầng | Giảm tổng số rows logic cần trả? | Giảm rows mỗi batch? |
|---|---|---|---|
| SQL `LIMIT 100` | Database | Có | Không quyết định fetch batch |
| JPA `setMaxResults(100)` | JPA/SQL dialect | Thường có | Không trực tiếp |
| JDBC `setFetchSize(100)` | JDBC driver | Không | Có thể, theo driver |
| Java `stream.limit(100)` | Client stream pipeline | Chỉ giới hạn tiêu thụ downstream; không chắc giảm DB work | Không quyết định |
| SQL `WHERE id > :cursor` | Database | Giới hạn tập kết quả theo predicate | Không quyết định |
| Java `stream.filter(predicate)` | Client | Không mặc nhiên | Không |

---

## 8. PostgreSQL JDBC: cursor cần điều kiện cấu hình

Với PostgreSQL JDBC driver, cơ chế cursor-based incremental fetching thường cần những điều kiện như:

- Connection **không ở autocommit mode** cho cursor-based fetching trong transaction.
- Statement/result set có dạng forward-only phù hợp.
- Fetch size dương.
- Query/result processing thuộc trường hợp driver hỗ trợ cursor.
- Driver/server versions và các driver properties tương ứng.

Ví dụ ý tưởng khi dùng JDBC thuần:

```java
connection.setAutoCommit(false);

try (PreparedStatement ps = connection.prepareStatement(
        """
        SELECT id, order_code
        FROM purchase_orders
        ORDER BY id
        """,
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    ps.setFetchSize(200);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            process(rs.getLong(1), rs.getString(2));
        }
    }
}

connection.commit();
```

### 8.1. Vì sao autocommit quan trọng?

Theo cơ chế cursor của PostgreSQL JDBC, nếu mỗi statement tự commit ngay thì cursor cần giữ qua quá trình fetching có thể không hoạt động như dự định. Driver có thể chọn fetch/buffering mode khác.

### 8.2. Không tự bật/tắt autocommit trên Spring-managed connection

Trong ứng dụng Spring/JPA, transaction manager và connection pool quản lý autocommit. Không lấy raw connection từ pool rồi tùy tiện `setAutoCommit(false)` hoặc `commit()` khi transaction đang do framework điều khiển.

### 8.3. `@Transactional(readOnly=true)` có bảo đảm streaming?

Không. Một transaction đang hoạt động giúp cung cấp môi trường transaction, nhưng **không tự set đúng fetch size, cursor mode hoặc bỏ ORM entity management**. Cần kiểm tra cấu hình driver/provider.

### 8.4. Phải đo driver behavior

Một cấu hình không hợp lệ có thể làm PostgreSQL driver buffer nhiều rows dù Java dùng Stream. Đo allocation, DB cursor behavior, network fetching hoặc instrument JDBC để xác nhận thay vì suy từ annotation.

---

## 9. MySQL/MariaDB: cơ chế streaming khác PostgreSQL

Các JDBC drivers của MySQL/MariaDB có chiến lược buffering, streaming và cursor fetching khác nhau theo driver/version/settings.

Ví dụ với **MySQL Connector/J**, các cơ chế thường được nhắc đến gồm:

- Cursor-based fetching khi bật các properties thích hợp như `useCursorFetch` và cấu hình fetch size/statement preparation tương ứng.
- Một chế độ streaming result set đặc thù driver trong một số phiên bản, sử dụng special fetch-size value; nó không phải semantics portable của JPA.

### 9.1. Không copy PostgreSQL recipe

Chỉ đặt `setFetchSize(200)` và mở transaction **không bảo đảm** MySQL Connector/J đang sử dụng cùng server-side cursor semantics như PostgreSQL JDBC.

### 9.2. Unbuffered streaming có giới hạn sử dụng connection

Một số modes streaming/result set của MySQL yêu cầu tiêu thụ hoặc đóng result set trước khi chạy statement khác trên cùng connection. Điều này ảnh hưởng rất lớn nếu trong lúc duyệt stream bạn còn lazy-load child entities (N+1).

### 9.3. Những điểm phải xác minh

- Driver name/version.
- JDBC URL properties.
- Prepared statement mode.
- Positive fetch size hoặc driver-specific mode.
- Autocommit/transaction requirements.
- Có được phép thực thi queries khác trên connection trong lúc stream mở không?
- Có buffering toàn bộ result set không?
- Khi gọi Stream.close(), server/driver resources có được trả lại không?

### 9.4. Oracle, SQL Server và DBMS khác

Driver có thể có `row prefetch`/fetch buffering riêng. Đừng suy mọi hệ thống đều sử dụng server-side cursor cùng cách hoặc hỗ trợ một keyword portable để “bật streaming”.

---

## 10. Hibernate: `getResultStream()` và scrollable results

Hibernate ORM cung cấp APIs hỗ trợ việc duyệt kết quả với chiến lược scroll.

Ở các phiên bản Hibernate phù hợp, `getResultStream()` có thể được triển khai trên cơ sở `ScrollableResults` thay vì `getResultList().stream()`.

### 10.1. Nhưng kết luận cần tách các tầng

Ngay cả khi Hibernate dùng scroll:

1. SQL vẫn được thực thi.
2. JDBC driver vẫn có quyền buffer/prefetch.
3. Hibernate vẫn hydrate result entries.
4. Nếu result là entity, persistence context có thể tiếp tục giữ managed entities.
5. Lazy associations có thể gây thêm SQL.
6. Connection/result set thường còn mở trong lúc duyệt.

### 10.2. Thế nào là “stream thực sự”?

Một kết luận có ích phải ghi rõ mức:

- **Application memory bounded**: peak heap không tăng theo tổng rows theo mức chấp nhận được.
- **ORM incremental hydration**: không materialize toàn bộ entities trước consumer.
- **JDBC incremental fetching**: driver không buffer toàn bộ.
- **Database cursor usage**: DB/driver giữ cursor hoặc protocol paging tương ứng.
- **Operationally safe**: connection/transaction không bị giữ quá lâu, cancellation và cleanup đúng.

Không gọi “true streaming” như một nhãn có/không duy nhất nếu chưa định nghĩa tiêu chí.

---

## 11. Cấu hình Hibernate fetch size từ JPA Query

Một cách dựa trên Hibernate API:

```java
TypedQuery<OrderExportRow> jpaQuery = em.createQuery(
    """
    SELECT NEW demo.dto.OrderExportRow(
        o.id,
        o.orderCode,
        o.grandTotal
    )
    FROM PurchaseOrder o
    ORDER BY o.id
    """,
    OrderExportRow.class
);

jpaQuery.unwrap(org.hibernate.query.Query.class)
        .setFetchSize(200);
```

`setFetchSize` ở đây là extension Hibernate; trong JPA API chuẩn không có phương thức `TypedQuery.setFetchSize` portable.

### 11.1. Không bắt buộc fetch size là 200

Các giá trị 50/100/200/500/1000 đều có thể là điểm thử nghiệm. Kết quả phụ thuộc row width, latency mạng, driver, database, heap và throughput.

### 11.2. Fetch size quá nhỏ

Có thể tăng số round trips và overhead điều khiển cursor, làm giảm throughput.

### 11.3. Fetch size quá lớn

Có thể tăng driver buffers, peak memory và tốc độ tiêu thụ tài nguyên trước khi consumer sẵn sàng.

### 11.4. Không nhầm với `@BatchSize`

`@BatchSize(size = 32)` của Hibernate tối ưu một số việc load proxies/collections theo batch IDs. `Query.setFetchSize(200)` chuyển JDBC fetch-size hint cho một result set. Hai cơ chế giải quyết hai vấn đề khác nhau.

---

## 12. So sánh ba từ “batch” dễ gây nhầm

| Thuật ngữ | Mục tiêu | Ví dụ |
|---|---|---|
| JDBC result fetch size | Driver lấy bao nhiêu rows mỗi đợt, nếu hỗ trợ | `setFetchSize(200)` |
| Hibernate batch fetching | Gom load nhiều entities/collections qua IDs để giảm N+1 | `@BatchSize(32)` |
| JDBC write batching | Gom nhiều INSERT/UPDATE/DELETE parameterized executions | `hibernate.jdbc.batch_size=50` |

Một thay đổi như:

```properties
hibernate.jdbc.batch_size=50
```

không tự khiến `SELECT getResultStream()` nhận 50 rows mỗi batch. Nó liên quan batching của write operations.

---

## 13. Transaction còn sống khi stream được đọc

Với cursor-backed stream, dữ liệu có thể được lấy **sau khi `getResultStream()` trả về**. Do đó, phải duyệt khi persistence context và transaction/connection cần thiết vẫn đang hoạt động.

### 13.1. Sai: trả Stream từ method đóng EntityManager

```java
Stream<PurchaseOrder> findOrders() {
    EntityManager em = emf.createEntityManager();

    try {
        return em.createQuery(
            "SELECT o FROM PurchaseOrder o",
            PurchaseOrder.class
        ).getResultStream();
    } finally {
        em.close();
    }
}
```

Caller nhận một Stream nhưng `EntityManager` đã đóng. Nếu stream-backed cursor cần connection, khi caller duyệt có thể phát sinh lỗi.

### 13.2. Sai: trả Stream từ service rồi mới duyệt ngoài transaction

```java
@Transactional(readOnly = true)
public Stream<PurchaseOrder> openStream() {
    return repository.streamAll();
}
```

Sau khi service method trả về, transaction proxy thường hoàn tất transaction. Nếu caller mới duyệt Stream ngoài transaction, resource có thể không còn hợp lệ.

### 13.3. Đúng hơn: tiêu thụ Stream *bên trong* transaction boundary

```java
@Transactional(readOnly = true)
public void consumeOrders(Consumer<PurchaseOrder> consumer) {
    try (Stream<PurchaseOrder> rows = repository.streamAll()) {
        rows.forEach(consumer);
    }
}
```

Ví dụ thuộc Spring Data repository có method `streamAll()` được khai báo phù hợp; phải đảm bảo call vào service đi qua transactional proxy và consumer xử lý trong thời gian transaction còn mở.

### 13.4. Dù đúng về lifetime, có thể sai về vận hành

Consumer lâu hoặc thực hiện I/O chậm có thể giữ transaction và connection trong nhiều phút/giờ. Khi đó chunk processing có thể là thiết kế tốt hơn.

---

## 14. Luôn đóng Stream có resource

`Stream` kế thừa `BaseStream`, có method `close()` và có thể dùng trong `try-with-resources`.

```java
try (Stream<OrderExportRow> rows =
         query.getResultStream()) {
    rows.forEach(this::writeExportRow);
}
```

### 14.1. Vì sao phải close?

Nếu Stream backed by cursor/ResultSet, `close` có thể giúp giải phóng JDBC/ORM resources. Dù provider sử dụng list-backed stream, việc luôn đóng an toàn với code dùng JPA provider khác hoặc thay config trong tương lai.

### 14.2. Terminal operation không tương đương close

`forEach` duyệt hết không phải là lời hứa chung rằng Stream tự gọi `close()` trong mọi implementation. `limit(100)`, `findFirst()`, `anyMatch()` càng dễ dừng sớm và để resources chưa được release nếu không close.

### 14.3. Exception cũng phải close

Nếu consumer ném lỗi:

```java
try (Stream<OrderExportRow> rows =
         query.getResultStream()) {
    rows.forEach(row -> {
        if (row.id() == null) {
            throw new IllegalStateException("Invalid row");
        }
    });
}
```

`try-with-resources` sẽ cố đóng Stream. Transaction rollback/cleanup do transaction manager xử lý theo policy.

### 14.4. Close stream và close EntityManager khác nhau

Trong resource-local JPA, entity manager, transaction và stream có lifecycle riêng. Một `Stream.close()` không mặc định thay `EntityManager.close()` hoặc transaction commit/rollback.

---

## 15. Tại sao không dùng `parallel()` trên JPA result stream?

Một Java Stream có thể viết:

```java
stream.parallel().forEach(this::process);
```

Nhưng JPA `EntityManager` và Hibernate `Session` **không được thiết kế thread-safe** để nhiều threads đồng thời truy cập một persistence context/connection/cursor.

### 15.1. Rủi ro

- Cursor forward-only không hỗ trợ access concurrent theo cách consumer nghĩ.
- Multiple threads truy cập lazy associations/session.
- Không bảo toàn order.
- Race ở shared mutable state.
- Transaction/security contexts dạng thread-local không tự propagate.
- JDBC connection/ResultSet bị dùng không an toàn.

### 15.2. Phương án nếu cần xử lý song song

Đọc dữ liệu qua DTO batches với boundary rõ, sau đó đưa **immutable detached DTOs** sang executor/worker pool độc lập. Điều chỉnh batch size, queue capacity, concurrency, backpressure và per-worker transaction; không chia sẻ một live JPA stream/cursor giữa threads.

### 15.3. Parallel Stream không làm database query tự song song hiệu quả

Ngay cả với dữ liệu đã materialized, parallel processing còn có overhead. Benchmark thực tế trước khi thêm concurrency.

---

## 16. Java Stream operations có thể giữ toàn bộ dữ liệu

Mặc dù nguồn dữ liệu là cursor, consumer vẫn có thể phá lợi ích streaming.

### 16.1. `collect(toList)`

```java
List<OrderExportRow> all;
try (Stream<OrderExportRow> rows =
         query.getResultStream()) {
    all = rows.collect(Collectors.toList());
}
```

Danh sách `all` giữ toàn bộ rows. Memory có thể tăng theo N, bất kể JDBC lấy theo đợt.

### 16.2. `toList()`

```java
List<OrderExportRow> all =
    stream.toList();
```

Tương tự, materialize toàn bộ kết quả trong Java collection.

### 16.3. `sorted()`

```java
stream.sorted(Comparator.comparing(
    OrderExportRow::orderCode));
```

Sorting là operation stateful; để sort tổng thể đúng thường phải giữ nhiều hoặc tất cả phần tử. Với dữ liệu lớn, **đẩy ORDER BY xuống SQL** khi có thể.

### 16.4. `distinct()`

```java
stream.distinct()
```

Có thể cần giữ các giá trị đã thấy để khử trùng lặp, làm state tăng theo số phần tử unique.

### 16.5. `groupingBy()`

```java
stream.collect(Collectors.groupingBy(
    OrderExportRow::status));
```

Thường giữ toàn bộ elements phân nhóm trong Map/Lists, dẫn tới memory `O(N)`.

### 16.6. `count()` và `max()`

Chúng không nhất thiết giữ toàn bộ rows, nhưng có thể **phải duyệt toàn bộ database result**. Nếu chỉ cần COUNT hoặc MAX, query `SELECT COUNT(...)` hoặc `MAX(...)` ở DB thường tốt hơn.

---

## 17. Đẩy filter, sort, aggregate về SQL

### 17.1. Lọc trong Java

```java
query.getResultStream()
    .filter(o -> "PAID".equals(o.getStatus()))
    .forEach(this::export);
```

Nếu query ban đầu không có predicate, provider có thể vẫn tải tất cả orders rồi Java mới loại những rows không PAID.

### 17.2. Lọc ở JPQL

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.status = :status
ORDER BY o.id
```

Database có thể dùng index, giảm rows truyền tới ứng dụng.

### 17.3. Sort trong Java

```java
stream.sorted(comparing(PurchaseOrder::getCreatedAt))
```

có thể cần giữ toàn bộ result trong memory.

### 17.4. Sort trong DB

```jpql
ORDER BY o.createdAt, o.id
```

SQL `ORDER BY` diễn đạt order trên DB. Tuy nhiên, DB có thể vẫn cần sort lớn nếu không có index phù hợp; kiểm `EXPLAIN`.

### 17.5. Đếm

Thay:

```java
long count = query.getResultStream().count();
```

bằng:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :status
```

khi chỉ cần count và query semantics cho phép.

---

## 18. Example entity cho bài thực hành

Định nghĩa một entity nhỏ:

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String orderCode;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "status", nullable = false)
    private String status;

    @Column(name = "grand_total",
            nullable = false, precision = 19, scale = 2)
    private BigDecimal grandTotal;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public PurchaseOrder(
            String orderCode,
            Instant createdAt,
            String status,
            BigDecimal grandTotal) {
        this.orderCode = Objects.requireNonNull(orderCode);
        this.createdAt = Objects.requireNonNull(createdAt);
        this.status = Objects.requireNonNull(status);
        this.grandTotal = Objects.requireNonNull(grandTotal);
    }

    public Long getId() { return id; }
    public String getOrderCode() { return orderCode; }
    public Instant getCreatedAt() { return createdAt; }
    public String getStatus() { return status; }
    public BigDecimal getGrandTotal() { return grandTotal; }
    public long getVersion() { return version; }
}
```

Code dùng `Long` ID do database sinh; cách generated identity và schema tương ứng phụ thuộc dialect/migration.

### 18.1. DTO phù hợp export

```java
package demo.dto;

import java.math.BigDecimal;

public record OrderExportRow(
    Long id,
    String orderCode,
    BigDecimal grandTotal
) {}
```

Đây là **DTO**, không phải managed entity. Tạo bằng JPQL constructor expression sẽ tránh đưa `PurchaseOrder` vào persistence context cho từng row, nếu query chỉ trả DTO scalars.

---

## 19. Ví dụ service JPA stream DTO trong transaction

Đây là ví dụ Spring/JPA/ Hibernate minh họa một stream được tiêu thụ *bên trong* service.

```java
package demo.service;

import demo.dto.OrderExportRow;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Objects;
import java.util.function.Consumer;
import java.util.stream.Stream;

@Service
public class OrderStreamService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public void exportRows(
            Consumer<OrderExportRow> consumer) {

        Objects.requireNonNull(consumer);

        TypedQuery<OrderExportRow> query = em.createQuery(
            """
            SELECT NEW demo.dto.OrderExportRow(
                o.id,
                o.orderCode,
                o.grandTotal
            )
            FROM PurchaseOrder o
            WHERE o.status = :status
            ORDER BY o.id
            """,
            OrderExportRow.class
        );

        query.setParameter("status", "PAID");

        query.unwrap(org.hibernate.query.Query.class)
             .setFetchSize(200);

        try (Stream<OrderExportRow> rows =
                 query.getResultStream()) {
            rows.forEachOrdered(consumer);
        }
    }
}
```

### 19.1. Thuộc phần nào của JPA, phần nào Hibernate?

- `TypedQuery` và `getResultStream()`: JPA API.
- `@Transactional` và `@Service`: Spring.
- `unwrap(org.hibernate.query.Query.class).setFetchSize(200)`: Hibernate-specific.
- Whether cursor data is fetched incrementally: driver/database-specific.

### 19.2. Tại sao DTO?

Query chọn ba cột cần thiết và materialize `OrderExportRow`, không managed `PurchaseOrder` entities. Việc trả DTO giảm overhead persistence context trong nhiều workloads.

### 19.3. Tại sao Consumer thay vì trả Stream?

Service giữ transaction boundary và đóng stream. Caller không cần biết khi nào cursor/EntityManager còn mở.

### 19.4. Giới hạn rất quan trọng

Consumer nếu gửi network response chậm, gọi API khác hoặc ghi dữ liệu khổng lồ có thể **giữ DB connection và transaction lâu**. Với file xuất lớn hoặc client chậm, xem chunked processing ở phần sau.

---

## 20. Hibernate `scroll(ScrollMode.FORWARD_ONLY)`

Khi cần điều khiển rõ hơn so với `getResultStream()`, Hibernate cung cấp `ScrollableResults`.

Ví dụ với Hibernate 6-style API:

```java
import org.hibernate.ScrollMode;
import org.hibernate.ScrollableResults;
import org.hibernate.Session;

Session session = em.unwrap(Session.class);

try (ScrollableResults<OrderExportRow> cursor =
         session.createQuery(
             """
             SELECT NEW demo.dto.OrderExportRow(
                 o.id,
                 o.orderCode,
                 o.grandTotal
             )
             FROM PurchaseOrder o
             ORDER BY o.id
             """,
             OrderExportRow.class
         )
         .setFetchSize(200)
         .scroll(ScrollMode.FORWARD_ONLY)) {

    while (cursor.next()) {
        OrderExportRow row = cursor.get();
        process(row);
    }
}
```

### 20.1. Vì sao FORWARD_ONLY?

Khi chỉ duyệt một chiều, không cần random access/backward scrolling. Nó phù hợp với các driver/queries hỗ trợ forward-only cursors.

### 20.2. ScrollableResults vẫn không bảo đảm mọi thứ

- Driver có thể prefetch/buffer.
- SQL có thể thực thi blocking sort.
- Nếu query trả entity, persistence context vẫn có thể lớn lên.
- Connection và transaction vẫn phải sống trong lúc cursor được sử dụng.

### 20.3. API thay đổi theo Hibernate version

Các APIs `ScrollableResults.get()`, `get(int)`, types/generics và query APIs đã có thay đổi giữa các đời Hibernate. Mẫu trên dành cho kiểu API tương ứng Hibernate 6; với Hibernate 5 hoặc phiên bản cụ thể, kiểm tra signatures thực tế trước khi đưa vào project.

### 20.4. Scroll là provider extension

JPA chuẩn không có một `TypedQuery.scroll(...)` portable tương đương. Nếu khả năng chạy trên nhiều providers quan trọng, bám vào JPA API hoặc tách adapter provider-specific.

---

## 21. Entity streaming vẫn có thể làm persistence context phình

Giả sử query trả managed entity:

```java
try (Stream<PurchaseOrder> rows =
         em.createQuery(
             "SELECT o FROM PurchaseOrder o ORDER BY o.id",
             PurchaseOrder.class
         ).getResultStream()) {

    rows.forEach(this::export);
}
```

JPA persistence context duy trì entity identity và quản lý trạng thái cần thiết. Khi duyệt rất nhiều entities, số managed instances có thể tăng và gây memory pressure, dù JDBC truyền 200 rows mỗi batch.

### 21.1. “Không giữ List” chưa đủ

Nếu ORM session giữ 1 triệu managed entities, bạn đã chuyển gánh nặng từ `List` sang **first-level cache**.

### 21.2. Hibernate read-only mode

Hibernate cung cấp read-only query/session options có thể giảm overhead dirty checking/snapshots cho entities được load, tùy mapping/implementation:

```java
query.unwrap(org.hibernate.query.Query.class)
     .setReadOnly(true);
```

Đây là **optimization hint/provider API**, không biến entities thành DTO, không bảo đảm persistence context không giữ identity references và không tự giải phóng heap.

### 21.3. Spring `@Transactional(readOnly=true)`

Trong một số Spring + Hibernate integrations, read-only transaction có thể được chuyển thành flush/read-only optimizations, nhưng behavior không nên coi như bảo đảm rằng mọi entity bị auto-detach hay cursor luôn streaming. Kiểm tra cấu hình thật.

### 21.4. DTO projection thường đơn giản hơn

Nếu chỉ xuất CSV, lấy `id`, `orderCode`, `grandTotal` trực tiếp vào DTO giúp tránh quản lý entity lifecycle không cần thiết.

---

## 22. Detach và clear khi stream entities

Một chiến lược giảm persistence context growth là detach những entity đã xử lý:

```java
try (Stream<PurchaseOrder> rows =
         em.createQuery(
             "SELECT o FROM PurchaseOrder o ORDER BY o.id",
             PurchaseOrder.class
         ).getResultStream()) {

    rows.forEach(order -> {
        writeToExport(order);
        em.detach(order);
    });
}
```

### 22.1. Đây là một phương án cần kiểm thử trên provider

Detach entity trong lúc cursor/stream đang duyệt có thể tương tác với proxies, fetch plans, collection loading, listeners và ORM state. Với các result graphs phức tạp, không coi đây là bảo đảm portable hay vô điều kiện an toàn.

### 22.2. Đừng detach trước khi đọc các trường cần thiết

Nếu `writeToExport(order)` truy cập LAZY association sau khi order đã detach, có thể gặp `LazyInitializationException`. Xử lý dữ liệu cần thiết trước khi detach, hoặc dùng DTO query tránh lazy associations.

### 22.3. Clear có tác động rộng hơn

`em.clear()` detach **tất cả** entities trong persistence context, không chỉ row hiện tại. Dùng khi bạn kiểm soát toàn bộ transaction/use case; nó có thể làm mất các pending changes chưa flush hoặc khiến những managed references khác trở thành detached.

### 22.4. Đừng clear tùy tiện trong transaction có writes

Nếu vừa sửa managed entities và gọi clear trước flush, các thay đổi có thể không được đồng bộ. Với read-only export, tránh mutate entities; với batch write, dùng flush/clear theo chiến lược khác.

---

## 23. StatelessSession của Hibernate: một lựa chọn khác

Hibernate có `StatelessSession`, cung cấp API làm việc với dữ liệu mà không có cùng first-level persistence context/automatic dirty checking semantics như một stateful `Session`.

### 23.1. Vì sao có ích?

Ở một số use cases batch processing, không cần identity map, automatic dirty checking hoặc managed entity graphs. Stateless access có thể giảm overhead.

### 23.2. Đánh đổi quan trọng

StatelessSession có semantics khác rõ rệt về lifecycle, cascading, persistence context, interceptors/events và các khả năng ORM khác tùy Hibernate version. Không thay `EntityManager` bằng StatelessSession rồi mong mọi JPA lifecycle callbacks, cascading và lazy association behavior giống hệt.

### 23.3. Không cần khi DTO query đã đáp ứng

Nếu yêu cầu chỉ là export một số cột, JPQL/native DTO projection với cursor hoặc pagination có thể đơn giản hơn mà vẫn hiệu quả.

### 23.4. Một API chuyên dụng cần proof-of-concept

Nếu chuyển sang StatelessSession, phải kiểm thử nghiệp vụ và measure memory/throughput riêng. Đây là Hibernate-specific design choice, không phải yêu cầu của JPA.

---

## 24. Cẩn thận với quan hệ LAZY khi đang stream

Giả sử:

```java
try (Stream<PurchaseOrder> rows = query.getResultStream()) {
    rows.forEach(o -> {
        System.out.println(o.getCustomer().getName());
    });
}
```

Nếu `customer` là LAZY `@ManyToOne` và chưa được fetch:

- Có thể có N+1 secondary selects.
- Streaming cursor đang giữ một result set mở.
- Driver/connection có thể không hỗ trợ một query khác đồng thời theo cách dự định.
- Per-row network latency có thể phá throughput.

### 24.1. Query phải lấy đúng dữ liệu consumer cần

Nếu cần `customerName`, có thể dùng to-one join trong DTO projection:

```jpql
SELECT NEW demo.dto.OrderWithCustomerRow(
    o.id,
    o.orderCode,
    c.name
)
FROM PurchaseOrder o
JOIN o.customer c
ORDER BY o.id
```

Đây là query minh họa cho model có association `PurchaseOrder.customer` và DTO `OrderWithCustomerRow` đã khai báo phù hợp; ví dụ entity ở phần 18 không chứa `customer`.

### 24.2. To-one join thường không nhân số parent rows

Với `@ManyToOne` hoặc `@OneToOne` hợp lệ, mỗi Order thường có tối đa một associated row, nên join lấy một thuộc tính customer không gây cùng kiểu Cartesian product như hai independent to-many collections.

### 24.3. Nhiều to-many JOIN FETCH lại rất nguy hiểm

Stream result không chữa row multiplication. Nếu query JOIN FETCH `lines` và `shipments`, database vẫn có thể tạo hàng chục/hàng trăm combinations per Order, và Hibernate có thể gặp `MultipleBagFetchException` với multiple bags.

### 24.4. Tránh nested query trong cursor loop nếu không chắc driver

Nếu thực sự cần children, cân nhắc đọc theo page/chunk IDs rồi dùng các queries riêng cho từng association, thay vì kích hoạt lazy query mỗi row.

---

## 25. Stream + JOIN FETCH collection không phải luôn phù hợp

Một query:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
ORDER BY o.id
```

có nhiều JDBC rows cho một parent. ORM có thể cần gom collection members và loại duplicate root references.

### 25.1. Vì sao khó streaming theo parent?

Nếu mỗi parent có hàng trăm child rows, một “parent object hoàn chỉnh” có thể chỉ sẵn sàng khi provider xử lý đủ rows liên quan. Các chi tiết hydrate/grouping/scrolling của provider có thể giới hạn cách stream entity graph được tiêu thụ.

### 25.2. Pagination over collection fetch còn khó hơn

Một SQL row limit có thể cắt giữa collection của một parent. Hibernate có thể cảnh báo, paginate trong memory hoặc fail nếu cấu hình guardrail phù hợp.

### 25.3. Hướng giải quyết

- Query parent IDs theo page/keyset.
- Query child rows theo `WHERE parent_id IN (:ids)`.
- Ghép thành DTO.
- Chỉ giữ một chunk/page trong memory.
- Release page resources trước khi tiếp tục.

### 25.4. Không đánh đồng Stream với “thiết kế fetch graph tốt”

Đúng SQL shape/cardinality thường có tác động lớn hơn việc đổi List sang Stream.

---

## 26. Phương án keyset pagination: giới hạn tài nguyên rõ ràng

Thay vì duyệt một cursor mở rất lâu, có thể đọc theo batches:

```text
SELECT next 500 rows WHERE id > lastId ORDER BY id
          |
          v
Process 500 DTO rows
          |
          v
Release objects / transaction
          |
          v
Repeat with new lastId
```

### 26.1. Tại sao keyset có ích?

- Mỗi query có giới hạn kết quả vật lý.
- Không giữ ResultSet/connection trong toàn bộ thời gian export.
- Memory phụ thuộc chunk size, không phụ thuộc tổng số rows.
- Có thể checkpoint progress bằng last processed ID.
- Giảm chi phí OFFSET lớn trên nhiều DBMS, nếu có index/predicate phù hợp.

### 26.2. Cần khóa sắp xếp ổn định

Ví dụ dùng ID tăng:

```jpql
SELECT NEW demo.dto.OrderExportRow(
    o.id,
    o.orderCode,
    o.grandTotal
)
FROM PurchaseOrder o
WHERE o.id > :lastId
ORDER BY o.id
```

và `setMaxResults(500)`.

### 26.3. Keyset không tự bảo đảm snapshot

Nếu Orders mới được thêm khi export chạy, chúng có thể xuất hiện ở các trang sau. Nếu rows bị xóa, kết quả có thể thiếu. Nếu cần export chính xác “tập dữ liệu tại một thời điểm”, phải định nghĩa snapshot/isolation/high-water mark hoặc một batch snapshot dataset.

---

## 27. Ví dụ Java keyset đọc DTO theo chunks

```java
package demo.service;

import demo.dto.OrderExportRow;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.function.Consumer;

@Service
public class OrderChunkReader {

    @PersistenceContext
    private EntityManager em;

    /**
     * Minh họa đọc từng page trong một transaction.
     * Với export dài, cân nhắc transaction riêng mỗi page.
     */
    @Transactional(readOnly = true)
    public void exportByKeyset(
            Consumer<OrderExportRow> consumer) {

        long lastId = 0L;
        final int pageSize = 500;

        while (true) {
            TypedQuery<OrderExportRow> query =
                em.createQuery(
                    """
                    SELECT NEW demo.dto.OrderExportRow(
                        o.id, o.orderCode, o.grandTotal
                    )
                    FROM PurchaseOrder o
                    WHERE o.id > :lastId
                    ORDER BY o.id
                    """,
                    OrderExportRow.class
                );

            List<OrderExportRow> page = query
                .setParameter("lastId", lastId)
                .setMaxResults(pageSize)
                .getResultList();

            if (page.isEmpty()) {
                break;
            }

            for (OrderExportRow row : page) {
                consumer.accept(row);
            }

            lastId = page.get(page.size() - 1).id();

            if (page.size() < pageSize) {
                break;
            }
        }
    }
}
```

### 27.1. Đây là ví dụ đơn giản nhưng vẫn giữ transaction dài

Dù mỗi query chỉ 500 rows, `@Transactional` bao quanh toàn bộ method nên transaction vẫn kéo dài đến cuối export. Nó giảm *result set/materialization size*, nhưng **chưa giải quyết connection/transaction lifetime** khi export rất lâu.

### 27.2. Cải tiến cho export lớn

Đưa hàm `fetchNextPage(lastId, size)` vào một service method/transaction độc lập, trả DTO List nhỏ, rồi xử lý output **sau khi transaction page đã kết thúc**. Gọi hàm qua Spring proxy/bean khác hoặc `TransactionTemplate` để không vướng self-invocation.

### 27.3. Không dùng JOIN FETCH collection ở page query

Query page nên dùng scalar/DTO projection hoặc root IDs. Nếu cần child data, tải theo page IDs bằng independent queries thay vì nhân child rows.

---

## 28. Transaction riêng từng trang: mô hình thực dụng

Sơ đồ:

```text
Export coordinator
    |
    +--> Transaction 1:
    |       fetch 500 OrderExportRows
    |       commit/close connection
    |
    +--> write 500 rows to file
    |
    +--> Transaction 2:
    |       fetch next 500 OrderExportRows
    |       commit/close connection
    |
    +--> write next 500 rows to file
    |
    +--> ...
```

### 28.1. Lợi ích

- Connection không bị giữ khi file writer/network bị chậm.
- Peak memory được giới hạn bởi page size và output buffer.
- Có checkpoint để tiếp tục sau lỗi.
- Transaction/lock/snapshot durations ngắn hơn.

### 28.2. Đánh đổi

- Không có một snapshot transaction xuyên suốt toàn export.
- Cần policy với inserts/updates/deletes trong lúc xuất.
- Mỗi page phải có order/cursor ổn định.
- Cần checkpoint/idempotency khi retry.
- Nhiều round trips hơn một cursor liên tục.

### 28.3. Khi consistency quan trọng hơn throughput

Một export kế toán cần ảnh chụp dữ liệu nhất quán có thể phải dùng transaction snapshot/copy hoặc xây một materialized export snapshot được version hóa, chứ không đơn giản chuyển sang per-page transactions.

---

## 29. So sánh offset, keyset và cursor

| Phương án | Memory caller | Connection giữ liên tục? | Phân trang/chạy lại | Nhược điểm |
|---|---|---|---|---|
| `getResultList()` toàn bộ | Thường cao | Query duration | Khó checkpoint nếu đã tải hết | Giữ tất cả results |
| `getResultStream()` cursor-backed | Có thể thấp nếu DTO/driver phù hợp | Thường có khi duyệt | Dừng giữa chừng cần close; resume không đơn giản | Cursor/session lifetime |
| Hibernate `scroll()` | Có thể thấp | Thường có | API explicit cursor | Provider-specific |
| Offset pages | Bounded theo page | Có thể kết thúc mỗi page | Dễ page number | OFFSET sâu tốn chi phí, concurrent changes |
| Keyset pages | Bounded theo page | Có thể kết thúc mỗi page | Resume theo last key | Cần stable order và semantics |
| Materialized snapshot/export table | Tùy cách đọc | Có thể chunk | Dễ reproduce | Storage/cost tạo snapshot |
| Native/JDBC cursor | Có thể thấp | Thường có | Thấp hơn pagination | Driver-specific config |

Chọn dựa trên **memory, connection lifetime, tính nhất quán, độ phức tạp và khả năng resume**, không phải chỉ từ tên API.

---

## 30. Hibernate query cache và stream

Một số hệ thống bật query cache hoặc second-level entity cache.

### 30.1. Query cache không biến stream thành miễn phí

Cache có thể thay cách provider lấy entity IDs/results và giảm một số SQL theo cấu hình, nhưng không phải bảo đảm rằng stream query sẽ trở thành incremental JDBC cursor hoặc không phải materialize dữ liệu.

### 30.2. Entity cache khác query cache

- Persistence context (L1): managed identity/state của session.
- Second-level cache (L2): cached entity/collection state dùng qua sessions theo provider.
- Query cache: cached query result identifiers/scalars theo query/parameters/cấu hình.

Không dùng cache hit để suy data loading strategy.

### 30.3. Benchmark cold/warm riêng

Nếu thử một lần đầu cold cache và một lần sau warm cache, có thể nghĩ Stream nhanh hơn List vì thứ tự benchmark. Reset/cô lập cache, query plans và page sizes khi so sánh.

---

## 31. Fetch size và độ rộng row

Hai truy vấn cùng 1 triệu rows nhưng tải dữ liệu khác nhau:

```sql
SELECT id, order_code
FROM purchase_orders;
```

và:

```sql
SELECT *
FROM purchase_orders;
```

Nếu row chứa `TEXT`/`BLOB` rất lớn, mỗi batch 200 rows có thể chiếm hàng chục MB.

### 31.1. Chọn projection là bước tối ưu đầu tiên

Nếu export chỉ cần ID, code, total, hãy chỉ SELECT ba cột ấy qua DTO.

### 31.2. Không có “fetchSize tốt nhất” cho mọi query

Với row 100 bytes, batch 1.000 có thể hợp lý. Với row 500 KB, batch 1.000 là quá lớn trong nhiều hệ thống. Nên đo row width và memory.

### 31.3. DB sort/hash cũng tốn memory

Một stream có `ORDER BY nonindexed_expression` vẫn có thể khiến database làm việc lớn trước khi trả row đầu tiên. Kiểm tra execution plan.

---

## 32. JDBC network round trips

Giả sử 100.000 rows, driver fetch theo batch 100:

```text
100,000 / 100 = 1,000 fetch batches (xấp xỉ)
```

Nếu batch 1.000:

```text
100,000 / 1,000 = 100 fetch batches (xấp xỉ)
```

Số round trips thực tế có thể khác do wire protocol/prefetch/driver optimizations.

### 32.1. Vì sao fetch size nhỏ quá chậm?

Mỗi fetch có latency mạng và xử lý ở server/driver. Nếu mỗi đợt 1 row, overhead có thể rất lớn.

### 32.2. Vì sao fetch size lớn quá tốn memory?

Driver có thể giữ nhiều rows cùng lúc, cộng thêm Java objects/cursor buffers. Nếu consumer xử lý chậm, dữ liệu đã prefetch có thể chiếm heap lâu.

### 32.3. Benchmark phải đo throughput và heap

Chọn fetch size dựa trên:

```text
rows / second
peak used heap
GC pause
database CPU
network bytes
number of fetch round trips
connection held time
```

Không chọn chỉ vì SQL count giống nhau.

---

## 33. Stream không phải reactive backpressure

Một `java.util.stream.Stream` là API đồng bộ để tiêu thụ dữ liệu theo pipeline. Nó **không** tự cung cấp reactive-streams `Publisher` backpressure, scheduling hoặc asynchronous non-blocking I/O.

### 33.1. Stream terminal operation có thể block thread

`stream.forEach(...)` chạy đồng bộ trên caller thread trong pipeline sequential thông thường. Nếu database fetch chậm, thread chờ.

### 33.2. Reactive database access là mô hình khác

R2DBC và reactive data access có APIs/semantics riêng, không phải chỉ đổi kiểu trả về từ `List` sang `Stream` trong JPA. JDBC truyền thống thường là blocking I/O; một Java Stream không biến connection thành non-blocking.

### 33.3. Có thể kết hợp với queue, nhưng phải giới hạn

Nếu dùng producer đọc DB và consumer ghi file/song song, bounded queue/backpressure được thiết kế riêng để không tạo một danh sách vô hạn trong memory.

---

## 34. Servlet HTTP streaming và transaction boundary

Ví dụ một Spring MVC controller trả streaming response:

```java
@GetMapping("/exports/orders")
public StreamingResponseBody export() {
    return outputStream -> {
        // Viết ra outputStream
    };
}
```

### 34.1. Cảnh báo quan trọng

`StreamingResponseBody` callback có thể chạy async sau khi controller method đã trả về. Không thể mặc nhiên dùng một `Stream` JPA mở trong controller transaction rồi trả nó qua callback.

### 34.2. Không nên giữ DB cursor theo tốc độ client

Nếu client đọc chậm hoặc mất mạng, việc đọc DB trong callback có thể giữ JDBC connection lâu, làm cạn connection pool. Một request export rất lớn có thể giữ connection hàng chục phút.

### 34.3. Hướng an toàn hơn

- Tạo export trong background job với page/chunk transactions.
- Ghi vào file/object storage tạm có retention/access control.
- Cho client tải file đã hoàn tất theo streaming HTTP riêng.
- Với export nhỏ, có thể đọc DTO page rồi trả response trong giới hạn thời gian chấp nhận.
- Nếu muốn stream DB trực tiếp ra HTTP, phải thiết kế transaction/thread/resource lifetime và cancellation cẩn thận.

### 34.4. “HTTP response streaming” khác “JDBC streaming”

Streaming HTTP nghĩa trả response bytes dần; JDBC streaming nghĩa driver nhận DB rows dần. Hai pipeline có thể được nối, nhưng chúng không phải một và không tự có backpressure xuyên suốt.

---

## 35. Connection pool exhaustion

Giả sử pool có 20 connections:

```text
20 requests export dài
  mỗi request giữ 1 connection 5 phút
  => pool hết connections cho các requests khác
```

Dù mỗi request chỉ sử dụng 10 MB heap, cả ứng dụng vẫn gặp lỗi/timeout.

### 35.1. Metrics cần xem

- Active/idle/pending connections.
- Connection acquisition wait.
- Transaction duration.
- Long-running cursor/statement count.
- Request duration và cancellation.
- Database lock/transaction age.
- Memory/GC.

### 35.2. Rate limit/concurrency limit

Có thể giới hạn số export jobs chạy đồng thời, phân tách export pool hoặc dùng queue. Không cho mọi request lớn giữ cursor không giới hạn.

### 35.3. Đóng stream khi client cancel

Nếu connection bị ngắt hoặc consumer ném exception, `try-with-resources`/transaction cleanup phải được thực thi. Test cancellation path, không chỉ happy path.

---

## 36. Transaction isolation khi đọc hàng triệu rows

Một long-running SELECT trong transaction có thể giữ một database snapshot tùy engine/isolation level.

### 36.1. Ví dụ rủi ro

Ở một DB dùng MVCC, giữ một transaction đọc rất lâu có thể ảnh hưởng việc dọn phiên bản rows cũ hoặc tạo pressure lên storage/vacuum/purge theo engine.

### 36.2. READ COMMITTED và REPEATABLE READ không giống nhau

Độ ổn định của dữ liệu khi duyệt cursor/nhiều queries phụ thuộc database, transaction isolation và cách cursor giữ snapshot.

### 36.3. Đừng dựa vào readOnly để suy isolation

`@Transactional(readOnly=true)` không tự động nghĩa là REPEATABLE READ hoặc một snapshot toàn export.

### 36.4. Pagination theo nhiều transactions cũng có rủi ro

Keyset với ID ổn định tránh một số lỗi OFFSET nhưng không chứng minh export là snapshot nhất quán khi records được sửa/xóa/thêm trong lúc chạy.

---

## 37. Một trường hợp muốn snapshot chính xác

Yêu cầu: “Xuất các đơn hàng ở trạng thái đúng tại 00:00 UTC.”

Các lựa chọn:

1. Database transaction snapshot phù hợp, chấp nhận connection/snapshot duration với workload đã đo.
2. Materialize danh sách IDs và dữ liệu tại một snapshot vào staging/export table.
3. Dùng event/history/temporal database để truy xuất as-of point nếu kiến trúc hỗ trợ.
4. Chụp dữ liệu vào read replica/reporting store phù hợp consistency requirements.
5. Chốt high-water mark cho dữ liệu append-only nếu business semantics cho phép.

### 37.1. Không nhầm high-water mark ID với snapshot đầy đủ

`WHERE id <= maxIdAtStart` có thể ngăn export bao gồm rows mới ID lớn hơn mốc ban đầu, nhưng **không** đóng băng các cập nhật/xóa của rows cũ.

### 37.2. Quyết định từ requirement

Nếu chỉ cần “best effort daily export”, pages theo thời điểm đọc có thể đủ. Nếu liên quan kiểm toán/tài chính, phải thiết kế consistency rõ ngay từ đầu.

---

## 38. Batch update và streaming read: hai use cases khác nhau

Đọc stream để xuất CSV thường không ghi vào DB. Nhưng một use case khác là:

```text
Đọc 1 triệu Products
Cập nhật category
Lưu về database
```

### 38.1. Đừng dùng read-only optimization cho write use case

Nếu `@Transactional(readOnly=true)` hoặc Hibernate query read-only mode được bật, thay đổi entity có thể không được dirty-checked/flushed như mong đợi. Phải thiết kế transaction và persistence state rõ.

### 38.2. Batch writes cần flush/clear chu kỳ phù hợp

Một pattern Hibernate/JPA thường gặp:

```text
for each batch of IDs:
  open transaction
  load bounded number of managed entities
  modify
  flush
  clear
  commit
```

Đây là **bounded batch processing**, không nhất thiết nên mở một stream cursor kéo dài trong cùng transaction vừa đọc vừa ghi.

### 38.3. Tránh update cùng table trong lúc cursor đang duyệt thiếu kiểm chứng

Tùy DB/driver/isolation, write/flush trong lúc một cursor lớn đang mở có thể gây locking, unstable selection hoặc lỗi connection/result set. Dùng ID pages và mỗi batch một transaction thường dễ reasoning hơn.

### 38.4. JDBC batching write khác fetch size read

Đừng giải quyết memory của batch update bằng cách chỉ tăng `hibernate.jdbc.batch_size`; vẫn cần kiểm soát số managed entities, page size và flush/clear.

---

## 39. Stream từ Spring Data JPA Repository

Spring Data JPA có khả năng repository query trả `Stream<T>` trong các phiên bản phù hợp.

Ví dụ:

```java
package demo.repository;

import demo.dto.OrderExportRow;
import demo.domain.PurchaseOrder;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.stream.Stream;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT NEW demo.dto.OrderExportRow(
            o.id,
            o.orderCode,
            o.grandTotal
        )
        FROM PurchaseOrder o
        WHERE o.status = :status
        ORDER BY o.id
        """)
    Stream<OrderExportRow> streamByStatus(
        @Param("status") String status);
}
```

### 39.1. Repository Stream không miễn yêu cầu transaction

Nên tiêu thụ trong một service method có transaction và đóng Stream:

```java
@Transactional(readOnly = true)
public void exportPaid(
        Consumer<OrderExportRow> consumer) {
    try (Stream<OrderExportRow> rows =
             repository.streamByStatus("PAID")) {
        rows.forEachOrdered(consumer);
    }
}
```

### 39.2. Một số cấu hình Spring Data yêu cầu surrounding transaction

Nếu cố gọi streaming repository method mà không có active transaction, Spring Data JPA có thể báo lỗi do resource lifetime. Không chữa bằng cách bỏ close hoặc chuyển sang EAGER tất cả.

### 39.3. Provider vẫn là yếu tố quyết định

Spring Data Stream return type không tự bắt driver dùng server cursor. Nó cần JPA provider, driver, transaction và fetch options phù hợp.

### 39.4. Đừng mở Stream trong controller rồi truyền qua view

Controller/serializer thường chạy qua boundary bất tiện cho transaction resources. Dùng service-level consumer hoặc DTO page.

---

## 40. Khi nào lấy List vẫn tốt hơn?

Đừng tối ưu sớm tất cả queries thành Stream.

Ví dụ:

```java
List<OrderExportRow> page = em.createQuery(
    """
    SELECT NEW demo.dto.OrderExportRow(
        o.id, o.orderCode, o.grandTotal
    )
    FROM PurchaseOrder o
    ORDER BY o.id
    """,
    OrderExportRow.class
).setMaxResults(50)
 .getResultList();
```

### 40.1. Vì sao hợp lý?

- Kết quả tối đa 50 rows.
- Không cần cursor mở ngoài query.
- Đơn giản để test, map và serialize.
- Có thể đóng transaction nhanh.
- Ít rủi ro resource leak.

### 40.2. Không cần Stream chỉ vì forEach

`page.forEach(this::process)` đủ cho một trang nhỏ. Dùng `page.stream()` để map/filter in-memory 50 records cũng hoàn toàn hợp lý vì mọi dữ liệu đã được giới hạn.

### 40.3. API tốt là API phù hợp kích thước/tính chất dữ liệu

Stream có giá trị khi tiêu thụ rất nhiều rows một cách tuyến tính và provider/driver đáp ứng. Với read requests nhỏ, List thường có chi phí phát triển và vận hành thấp hơn.

---

## 41. Sự khác biệt của DISTINCT khi stream entities

Một query:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.sku LIKE :prefix
ORDER BY o.id
```

có thể phải khử parent duplicate do JOIN child.

### 41.1. SQL DISTINCT có thể cần sort/hash

Một database có thể phải xây tập distinct/sort trước khi trả rows; streaming JDBC không làm biến mất DB work đó.

### 41.2. Java Stream.distinct có thể giữ state lớn

Nếu thay bằng `stream.distinct()`, Java phải theo dõi các elements đã xuất hiện. Với entities và equality theo ID/proxy, correctness còn phụ thuộc equality semantics.

### 41.3. Tránh nhân dữ liệu từ đầu nếu chỉ lọc parent

Dùng `EXISTS` để diễn đạt “Order có ít nhất một Line khớp”:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.sku LIKE :prefix
)
ORDER BY o.id
```

Đây là ví dụ cho model có `OrderLine` và association `order`, không nằm trong entity class đơn giản ở phần 18. Việc tối ưu đúng fetch shape thường có lợi hơn gọi Java Stream.distinct.

---

## 42. Cách biết provider có thực sự nạp từng phần không

Đừng chỉ nhìn tên method hoặc stack trace. Hãy kiểm chứng bằng **bằng chứng quan sát được**.

### 42.1. Kiểm thử thời điểm row đầu tiên

Với một result set lớn:

- Thời gian từ `getResultStream()` đến terminal consumption.
- Thời gian nhận phần tử đầu tiên.
- Thời gian xử lý hết result set.

Nếu implementation list-backed, việc materialize có thể xảy ra ngay trước khi Stream được trả. Nếu cursor-backed, row hydration có thể trải dài trong quá trình duyệt. Tuy nhiên DB sort/driver prefetch làm thời gian row đầu bị ảnh hưởng, nên test này **không đủ một mình**.

### 42.2. Kiểm thử peak heap

Chạy 10.000, 100.000 và 1.000.000 DTO rows với cùng code. So sánh peak used heap và allocation profile.

```text
Rows        10k      100k      1m
Peak heap   ? MB     ? MB      ? MB
```

Nếu memory tăng gần tuyến tính với rows dù consumer không giữ dữ liệu, có thể có buffering/materialization tại một tầng.

### 42.3. Kiểm tra JDBC/driver settings

Ghi rõ JDBC URL, fetch size, transaction/autocommit, provider version và driver version. Dùng instrumentation nếu cần để xác nhận cursor usage/fetch patterns.

### 42.4. Kiểm tra persistence context

So sánh stream `SELECT o` trả managed entities với `SELECT NEW ...` trả DTO. Nếu entity stream có memory growth còn DTO stream tương đối ổn định, first-level cache là giả thuyết đáng kiểm tra.

### 42.5. Kiểm tra SQL result rows

Một query JOIN nhiều associations có thể phát nhiều rows hơn entities. Dùng JDBC proxy hoặc database query instrumentation thay vì chỉ đếm Java List size.

---

## 43. Một test integration kiểm tra dữ liệu, chưa đo memory

Ví dụ JUnit:

```java
@Test
void stream_returns_expected_rows() {
    List<Long> ids = new ArrayList<>();

    try (Stream<OrderExportRow> rows =
             em.createQuery(
                 """
                 SELECT NEW demo.dto.OrderExportRow(
                     o.id,
                     o.orderCode,
                     o.grandTotal
                 )
                 FROM PurchaseOrder o
                 ORDER BY o.id
                 """,
                 OrderExportRow.class
             )
             .getResultStream()) {

        rows.forEach(row -> ids.add(row.id()));
    }

    assertEquals(expectedIds, ids);
}
```

### 43.1. Test này chứng minh điều gì?

- JPQL DTO constructor mapping đúng.
- Stream duyệt được các rows theo query.
- Resources được đóng qua try-with-resources.
- Order trong result phù hợp `ORDER BY id`.

### 43.2. Test này **không** chứng minh gì?

- Không chứng minh JDBC dùng server-side cursor.
- Không chứng minh peak heap bounded.
- Không chứng minh Hibernate không materialize sẵn.
- Không chứng minh driver không buffer.
- Không chứng minh behavior y hệt production DB.

Đây là **functional test**, cần thêm performance/instrumentation test cho streaming semantics.

---

## 44. Kiểm thử fetch size có hiệu lực

Một integration experiment:

1. Tạo database chứa ít nhất 100.000 DTO rows.
2. Dùng cùng JPQL SELECT.
3. Giữ transaction/driver settings cố định.
4. Chạy với fetch size mặc định.
5. Chạy với `setFetchSize(50)`.
6. Chạy với `setFetchSize(500)`.
7. Chạy với `setFetchSize(5_000)`.
8. Dùng consumer không giữ rows.
9. Ghi peak heap, throughput, round trips và latency.
10. Xác nhận mọi lần xử lý cùng số rows.

### 44.1. Nếu metrics không thay đổi?

Có thể driver bỏ qua fetch size trong mode hiện tại, database làm việc khác chi phối bottleneck, hoặc instrumentation chưa đo đúng tầng. Không kết luận “fetchSize không bao giờ hoạt động”.

### 44.2. Dùng DB mục tiêu

H2, PostgreSQL và MySQL có drivers/transaction behavior khác. Test trên H2 không đủ chứng minh PostgreSQL server-side cursor.

### 44.3. Benchmark lại sau nâng cấp version

Hibernate, driver và DBMS upgrades có thể thay buffering/cursor defaults; ghi version trong benchmark report.

---

## 45. Kiểm thử connection/resource lifetime

Một test nên quan sát:

```text
BEGIN transaction
open Stream
consume some rows
close Stream
finish transaction
release connection
```

### 45.1. Cancellation sớm

```java
try (Stream<OrderExportRow> rows =
         query.getResultStream()) {
    rows.limit(10).forEach(this::process);
}
```

Dù chỉ tiêu thụ 10 rows, Stream được đóng. Quan sát connection pool active count/DB cursor resource nếu instrumentation hỗ trợ.

### 45.2. Exception giữa stream

Cho consumer ném exception ở row thứ 10. Xác nhận `try-with-resources` close và transaction manager cleanup. Không để connections bị giữ sau failure.

### 45.3. Không đếm connection pool active ngay trước commit là resource leak

Một transaction hợp lệ có thể giữ connection đến khi kết thúc transaction dù stream đã close. Phải quan sát sau khi transaction hoàn tất và pool có cơ hội release.

---

## 46. Kiểm thử phân biệt list-backed và cursor-backed

Có thể đặt một interface adapter:

```java
public interface OrderReader {
    void forEachOrder(Consumer<OrderExportRow> consumer);
}
```

Tạo các implementations:

1. List-backed: `getResultList().forEach(...)`.
2. JPA stream: `getResultStream()` với try-with-resources.
3. Hibernate scroll: `scroll(FORWARD_ONLY)`.
4. Keyset pages: `setMaxResults(pageSize)`/`id > lastId`.

### 46.1. Giữ cùng workload

- Cùng SELECT/projection.
- Cùng ORDER BY.
- Cùng number of rows.
- Cùng DB/driver/config.
- Cùng data/cache state.
- Cùng work trong consumer.

### 46.2. Thu metrics

- Tổng rows processed.
- Peak heap.
- Allocation rate.
- GC pauses.
- Duration.
- Query/round trips.
- Connection hold duration.
- Database execution metrics.

### 46.3. Đừng chọn chiến lược chỉ theo throughput

Một cursor có thể nhanh nhưng giữ connection lâu. Keyset pages có thể chậm hơn chút nhưng giải phóng resources giữa các chunks, giúp hệ thống phục vụ các requests khác ổn định hơn.

---

## 47. Một phép đo đơn giản về memory: giới hạn của nó

Trong local experiment, có thể đọc:

```java
Runtime runtime = Runtime.getRuntime();

long used =
    runtime.totalMemory() - runtime.freeMemory();

System.out.println("Heap used: " + used);
```

### 47.1. Đây không phải profiler chính xác

GC scheduling, heap expansion, JIT, thread allocations và concurrent tasks làm số đọc dao động. Đừng dùng một lần `System.gc()` rồi kết luận chắc rằng approach A hơn B.

### 47.2. Phù hợp hơn

Dùng JFR, async-profiler, Java Flight Recorder/JMC, heap dumps, GC logs và benchmark harness trong môi trường cô lập. Với production, xem metrics aggregate/percentiles.

### 47.3. Quan sát sự tăng trưởng theo N

Nếu lượng rows tăng 10× mà peak memory tăng 10×, cần xem có giữ toàn bộ rows không. Nhưng Java heap không phải toàn bộ memory: driver/native buffers, database memory và OS page cache cũng có thể là nơi tiêu thụ.

---

## 48. Khi nào cursor-backed stream vẫn chậm?

Một số nguyên nhân:

- SQL cần sort/hash trên hàng triệu rows.
- Database không có index cho `WHERE`/`ORDER BY`.
- Bảng có LOBs lớn, row width cao.
- Fetch size quá nhỏ làm tăng round trips.
- Consumer xử lý CPU nặng.
- Consumer ghi network/file chậm.
- Connection tới DB ở xa/latency cao.
- N+1 lazy loading giữa lúc scroll.
- Entity hydration/dirty-check snapshots.
- Row multiplication vì JOIN to-many.
- Cache/plan/stats khác giữa lần đo.
- Database đang bị lock/IO pressure.

### 48.1. Stream không sửa query plan tệ

Hãy đọc `EXPLAIN (ANALYZE, BUFFERS)` trên PostgreSQL test database khi được phép, xem rows, indexes, sorts và temp disk usage. Trên DBMS khác dùng công cụ tương ứng.

### 48.2. Stream không giảm tổng data cần truyền nếu xử lý hết

Nếu cần toàn bộ 2 triệu rows, cuối cùng dữ liệu ấy vẫn phải được đọc. Lợi ích chính của incremental fetch có thể là **bounded memory** và **thời gian nhận/ghi từng row sớm hơn**, không phải giảm tổng số rows.

---

## 49. Một câu hỏi định lượng

Có 1.000.000 rows, mỗi row ~300 bytes cho fields lấy từ DB.

Lý thuyết payload thô tối thiểu:

```text
1,000,000 × 300 bytes ≈ 300 MB
```

Chưa tính protocol overhead, Java strings/objects, references, JDBC buffers, alignment, metadata và entity snapshots.

### 49.1. List-backed result

Có thể giữ phần lớn Java objects của 1 triệu rows cùng lúc. Peak heap có thể lớn hơn payload thô nhiều lần.

### 49.2. DTO cursor, fetch size 500, consumer không giữ

Về nguyên lý, driver/consumer có thể chỉ cần buffers của một số rows/batches tại một thời điểm, **nếu thật sự cursor-backed và không có tầng nào materialize toàn bộ**.

### 49.3. Entity cursor với persistence context giữ tất cả

Dù driver lấy 500 rows mỗi đợt, persistence context có thể tích lũy các managed entities. Heap vẫn tăng theo N.

### 49.4. Chunked 500 DTO rows

Memory per chunk có thể được giới hạn rõ hơn; đổi lại nhiều queries và snapshot semantics khác một long-lived cursor.

---

## 50. Chọn fetch plan theo nhu cầu thực tế

| Nhu cầu | Phương án thường phù hợp | Cảnh báo |
|---|---|---|
| Trang 20 orders | `getResultList()` + `setMaxResults(20)` | Dễ và đủ an toàn |
| Trả JSON summary | DTO projection | Không cần managed entities |
| Export 10.000 rows nhanh | DTO Stream/scroll hoặc pages | Đo driver/cursor |
| Export hàng triệu rows chạy lâu | Keyset/chunks, job background | Snapshot consistency/resume |
| Chạy read-only thuật toán tuyến tính | Cursor/stream trong transaction | Connection hold duration |
| Sửa hàng triệu entities | Batch pages + flush/clear | Không dùng read-only |
| Nhiều to-many associations | Split queries per page | Tránh Cartesian explosion |
| Count/report aggregate | SQL `COUNT/GROUP BY` | Không stream toàn bộ entities để đếm |
| App phải đổi ORM provider thường xuyên | JPA DTO pages | Hibernate-specific API giảm portability |
| Kiểm soát cursor rất chi tiết | JDBC/native provider APIs | Driver-specific behavior |
| Kết quả cần snapshot chặt | Transaction snapshot/read model | Có chi phí vận hành |
| HTTP client chậm | Tạo file theo chunks rồi download | Tránh giữ DB connection |

---

## 51. Những sai lầm thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đổi List sang Stream nhưng heap vẫn lớn | Provider list-backed | Xác minh provider, dùng DTO pages/scroll |
| Heap tăng tuyến tính khi stream entities | Persistence context giữ entities | DTO, read-only/detach/bounded batches |
| fetchSize=100 nhưng driver vẫn buffer | Driver mode/autocommit không phù hợp | Kiểm driver/database config |
| Stream không duyệt được sau service return | Transaction/EntityManager đã đóng | Duyệt trong transaction |
| Connection leak sau findFirst/limit | Không close stream | try-with-resources |
| Stream chậm dù heap thấp | Too many round trips / DB sort / slow consumer | Benchmark fetch size/SQL plan |
| SQL count=1 nhưng request rất nặng | JOIN fetch multiple collections | Split fetch, DTO |
| N+1 khi stream entities | LAZY association trong loop | Join to-one/project, batch/chunks |
| MySQL phát lỗi khi query khác chạy | Driver streaming mode giới hạn connection | Không nested queries trên same connection |
| BatchSize không thay số fetch rounds | Đó là association batching, không JDBC fetch size | Dùng query fetch size |
| JDBC batch_size không cải thiện SELECT | Là write batching | Điều chỉnh đúng setting |
| Stream.limit(100) không giảm DB work | Limit ở Java, đã prefetch/materialize | setMaxResults/SQL LIMIT |
| Stream.sorted làm hết memory | Stateful sorting | ORDER BY SQL hoặc bounded batches |
| collect(toList) làm heap phình | Giữ toàn bộ results | forEach incremental |
| Stream.parallel gặp lỗi Session | Session/EntityManager không thread-safe | Sequential read, parallel DTO batches |
| DTO query vẫn chậm | DB plan/index/row width hoặc driver buffering | EXPLAIN/instrument |
| readOnly=true nhưng memory tăng | Read-only không tự detach/cache-bypass | DTO/bounded chunks |
| HTTP export làm hết connection pool | DB cursor theo thời gian client download | Background export/chunks |
| H2 test ổn nhưng PostgreSQL khác | Driver/cursor/dialect khác | Test trên target DB |
| first row đến chậm | DB sort/aggregate hoặc eager materialization | Explain + profile |
| File export thiếu/lặp rows | Concurrent changes trong chunk pagination | Stable key/snapshot policy |
| Keyset export lẫn new rows | Không có snapshot/high-water policy | Xác định freshness |
| Query count giảm nhưng bytes tăng | JOIN multiplication/row width | Đo rows & network |
| Stream.close rồi connection vẫn active | Transaction chưa kết thúc | Kiểm transaction boundary |
| Hibernate scroll compile error | API đổi theo version | Đối chiếu đúng Hibernate API |
| Cần full history nhưng stream chỉ đọc hiện trạng | Không có temporal snapshot semantics | Audit history/snapshot design |

---

## 52. Bài thực hành A — Phân biệt Stream API và danh sách

1. Tạo 10.000 `OrderExportRow` records.
2. Chạy `getResultList()` rồi gọi `list.stream()`.
3. Đo thời điểm query hoàn tất và Java Stream được tạo.
4. So sánh với `getResultStream()`.
5. Ghi provider/version.
6. Quan sát heap.
7. Giải thích vì sao API type không chứng minh cursor behavior.
8. Thử `Stream.limit(10)` ở mỗi cách.

---

## 53. Bài thực hành B — JDBC fetch size trên database mục tiêu

1. Chạy PostgreSQL hoặc DBMS production-like.
2. Tạo bảng 100.000 rows.
3. Dùng forward-only PreparedStatement.
4. Thử fetch size 0/default, 50, 500, 5.000.
5. Đặt transaction/autocommit phù hợp driver.
6. Ghi thời gian row đầu, total time, peak heap.
7. Dùng JDBC/DB instrumentation kiểm tra batch behavior.
8. Thử autocommit setting khác trong test riêng.
9. Giải thích vì sao JDBC fetch size không giới hạn tổng rows.
10. Không sửa autocommit trực tiếp trên framework-managed connection.

---

## 54. Bài thực hành C — Hibernate getResultStream và scroll

1. Tạo 100.000 PurchaseOrders.
2. Stream managed entities.
3. Stream DTO projection.
4. Dùng Hibernate ScrollableResults FORWARD_ONLY.
5. Cùng fetch size 200.
6. Consume tất cả rows, không giữ references.
7. So sánh peak heap và counts.
8. Test Hibernate query read-only option.
9. Ghi hành vi first-level cache.
10. Đảm bảo close resources.

---

## 55. Bài thực hành D — Stream lifecycle

1. Mở JPA Stream trong active transaction.
2. Duyệt hết, close.
3. Mở Stream rồi `limit(10)`, close.
4. Mở Stream rồi consumer throw ở row thứ 10.
5. Quan sát transaction rollback/cleanup.
6. Mở Stream rồi cố duyệt sau khi đóng EntityManager.
7. Giải thích vì sao returning Stream qua service boundary có rủi ro.
8. Kiểm connection pool active count sau transaction kết thúc.
9. Không coi count khi transaction còn hoạt động là leak.

---

## 56. Bài thực hành E — Các Stream operations ngốn bộ nhớ

Trên cùng result dataset:

1. `forEachOrdered` và không giữ rows.
2. `collect(toList)`.
3. `sorted` theo orderCode.
4. `distinct` trên một property có nhiều giá trị.
5. `groupingBy` status.
6. `count()`.
7. So sánh peak heap/CPU.
8. Thay sort bằng SQL ORDER BY.
9. Thay group/count bằng GROUP BY/COUNT ở DB.
10. Giải thích stateful vs stateless operations.

---

## 57. Bài thực hành F — Filter ở Java so với SQL

1. Tạo 1 triệu Orders, 1% PAID.
2. Query toàn bộ rồi `stream.filter(status=PAID)`.
3. Query `WHERE status='PAID'`.
4. Ghi số JDBC rows, DB plan, heap.
5. Thêm index phù hợp status nếu workload cần.
6. So sánh total bytes.
7. Thử Stream.limit(100) sau filter.
8. Thử SQL WHERE + `setMaxResults(100)`.
9. Ghi kết luận về predicate pushdown.

---

## 58. Bài thực hành G — N+1 trong streaming cursor

1. Mapping Order→Customer LAZY to-one.
2. Stream 1.000 Orders.
3. Trong loop truy cập Customer.name.
4. Ghi SQL count.
5. Thử provider batch fetching.
6. Thử JPQL DTO projection join Customer.name.
7. Đo fetch behavior và driver limitations.
8. Ghi số rows/results.
9. Tránh nested queries trên cùng MySQL streaming connection nếu driver không hỗ trợ.
10. Giải thích vì sao streaming cursor không giải quyết N+1.

---

## 59. Bài thực hành H — First-level cache growth

1. Stream managed PurchaseOrder entities với transaction.
2. Ghi heap/profile theo 10k/50k/100k rows.
3. Lặp DTO projection.
4. Thử Hibernate read-only query.
5. Thử detach với use case an toàn.
6. Thử page-sized transactions.
7. So sánh entity loads và memory.
8. Không clear giữa write operations chưa flush.
9. Giải thích lợi ích/giới hạn của StatelessSession.

---

## 60. Bài thực hành I — Keyset pagination

1. Tạo Orders có IDs tăng.
2. Dùng `WHERE id > :lastId ORDER BY id`.
3. `setMaxResults(500)`.
4. Xử lý 500 DTO rows rồi lấy lastId.
5. Lặp tới khi hết.
6. Check mỗi ID xuất đúng một lần trên dataset ổn định.
7. Thử page 1 có 500 và page cuối có ít hơn 500.
8. Thử concurrent INSERT/DELETE.
9. Bổ sung high-water mark hoặc snapshot policy nếu cần.
10. So sánh connection hold time với cursor stream.

---

## 61. Bài thực hành J — HTTP export và client chậm

1. Dựng endpoint xuất CSV bằng streaming HTTP.
2. Thử trực tiếp DB cursor trong HTTP callback.
3. Giả lập client đọc chậm.
4. Đo active connections và transaction durations.
5. Giới hạn concurrent exports.
6. Viết phiên bản background export theo chunks.
7. Ghi file ra storage tạm và download sau.
8. So sánh pool usage/throughput.
9. Thử client cancellation và resource cleanup.
10. Thảo luận consistency và retention.

---

## 62. Bài thực hành K — Provider portability

1. Chạy cùng JPQL DTO query trên JPA provider A.
2. Chạy trên provider B nếu dự án hỗ trợ.
3. Ghi `getResultStream()` implementation behavior.
4. Test resource closure.
5. Kiểm JDBC fetch-size support/cursor settings.
6. So sánh memory và latency.
7. Không suy một provider hỗ trợ Hibernate `scroll()`.
8. Ghi rõ các adapter/provider-specific dependencies.
9. Chọn fallback là bounded DTO pages nếu cần portability.

---

## 63. Bài thực hành L — Benchmark công bằng

1. Chọn một DBMS/version cố định.
2. Seed 10k, 100k và 1m rows.
3. Xác định cùng projected fields.
4. Warm-up JVM/queries có kiểm soát.
5. Đo List, JPA Stream, Hibernate Scroll và keyset pages.
6. Ghi fetch size/driver/autocommit/transaction configs.
7. Đo peak heap, GC, total duration, first-row latency, bytes, round trips và pool usage.
8. Tách warm/cold cache.
9. Thử consumer CPU nhẹ và consumer file I/O chậm.
10. Ghi trade-offs, không công bố một “winner” cho mọi workloads.

---

## 64. Checklist trước khi đưa streaming query vào production

| Câu hỏi | Điều cần kiểm tra |
|---|---|
| Có cần toàn bộ rows không? | Nếu không, WHERE/LIMIT/page |
| Có cần managed entities không? | DTO projection có thể đủ |
| JPA provider nào/phiên bản nào? | Biết implementation getResultStream |
| Stream-backed hay list-backed? | Có bằng chứng quan sát |
| JDBC driver và version? | Cursor/fetch settings |
| fetchSize được đặt đúng tầng? | Hibernate Query/JDBC hint |
| fetchSize có hiệu lực không? | Instrument/measure |
| Có transaction phù hợp không? | Cursor lifetime |
| Autocommit phù hợp driver? | Đặc biệt PostgreSQL |
| Connection/result set có đóng? | try-with-resources |
| Có early exit/exception không? | Cleanup |
| Stream có bị return ra ngoài tx? | Không |
| Có gọi parallel() không? | Tránh với JPA Session |
| Có collect(toList)? | Nếu lớn, tránh |
| Có sorted/distinct/groupingBy trên Java stream? | Memory/stateful costs |
| SQL WHERE/ORDER BY phù hợp? | Predicate pushdown |
| SQL query có full scan/sort lớn? | EXPLAIN |
| Có LOB hoặc columns không cần? | Projection |
| Có lazy associations trong loop? | Tránh N+1 |
| Có JOIN FETCH nhiều to-many? | Tránh row explosion |
| Query trả entities, persistence context lớn? | DTO/read-only/detach/pages |
| Có transaction kéo dài? | Pool/locks/MVCC |
| HTTP client có thể đọc chậm? | Tách DB export và download |
| Có thể restart sau lỗi? | Keyset checkpoint |
| Có consistency/snapshot requirement? | Isolation/read model |
| Có keyset stable order? | Unique tie-breaker |
| Có database rows bị sửa trong lúc export? | Policy rõ |
| Có test trên DBMS production? | Không chỉ H2 |
| Có đo heap/GC? | Profile |
| Có đo SQL rows và bytes? | Không chỉ SQL count |
| Có đo pool active/wait? | Connection pressure |
| Có test cancellation? | Resource cleanup |
| Có benchmark cold/warm? | Công bằng |
| Có limit đồng thời cho long exports? | Rate/concurrency policy |
| Có test dữ liệu đúng đủ? | Correctness |
| Có lựa chọn List đơn giản hơn nếu result nhỏ? | Không tối ưu quá mức |

---

## 65. Những hiểu lầm phổ biến

### 65.1. “getResultStream luôn đọc một row từ database tại một thời điểm”

Không. Provider có thể materialize list trước, driver có thể prefetch theo batches hoặc buffer toàn bộ.

### 65.2. “Stream<T> tự động ít tốn heap”

Không. `collect(toList)`, stateful operations, ORM persistence context và driver buffering vẫn có thể giữ rất nhiều dữ liệu.

### 65.3. “Hibernate có scroll nên chắc chắn database dùng server cursor”

Không. Hibernate dùng JDBC/driver, và driver quyết định cách lấy rows.

### 65.4. “JDBC fetchSize=100 nghĩa query chỉ trả 100 rows”

Không. Nó là hint cho fetch batches, không phải SQL LIMIT.

### 65.5. “Stream.limit(100) giống setMaxResults(100)”

Không. Một cái diễn ra trên Java Stream; một cái là JPA query bound có thể đẩy xuống SQL.

### 65.6. “Connection setAutoCommit không liên quan cursor”

Có thể liên quan mạnh, đặc biệt PostgreSQL JDBC cursor behavior. Nhưng đừng tự sửa connection khi framework quản lý transaction.

### 65.7. “readOnly=true làm entity tự detach”

Không. Read-only optimization không mặc định xóa identity map.

### 65.8. “DTO stream và entity stream có memory behavior giống nhau”

Không nhất thiết. Entities có thể được giữ trong persistence context, còn DTO constructor result không mang managed entity lifecycle.

### 65.9. “Stream.forEach xong là chắc resources đã close”

Không suy như vậy. Dùng try-with-resources rõ ràng.

### 65.10. “Có thể trả Stream ra controller rồi duyệt lúc nào cũng được”

Không. Transaction/EntityManager/ResultSet có thể đã đóng.

### 65.11. “Stream.parallel sẽ tự tăng tốc truy vấn SQL”

Không. JPA Session không thread-safe; parallelizing cursor consumption có thể sai.

### 65.12. “Stream.filter chuyển thành SQL WHERE”

Không. Java filter chạy ở client sau khi query trả rows tương ứng; đẩy predicate vào JPQL nếu cần giảm DB result.

### 65.13. “Stream.sorted không cần nhiều memory”

Sorting toàn bộ result là operation stateful, có thể giữ nhiều rows.

### 65.14. “Stream.count nhanh hơn SELECT COUNT”

Không mặc nhiên. Stream.count có thể duyệt toàn bộ result set; SQL COUNT phù hợp hơn khi chỉ cần số lượng.

### 65.15. “BatchSize và fetchSize cùng một thứ”

Không. Một cái tối ưu load associations, một cái điều chỉnh JDBC result fetching.

### 65.16. “Hibernate jdbc.batch_size tăng tốc đọc stream”

Setting đó chủ yếu phục vụ batching statements ghi, không phải fetch SELECT result size.

### 65.17. “Một Stream query không thể gây N+1”

Có thể. Truy cập LAZY associations trong per-row consumer có thể tạo N+1.

### 65.18. “SQL JOIN nhiều collections sẽ ít data vì chỉ một query”

Không. Row multiplication có thể tăng dữ liệu rất lớn.

### 65.19. “Peak heap thấp nghĩa overall performance tốt”

Không. Có thể giữ connection lâu, tăng round trips, gây áp lực database hoặc phục vụ clients khác chậm.

### 65.20. “Keyset pages luôn tạo snapshot chính xác”

Không. Nếu records thay đổi trong lúc xuất, nhiều transactions có thể nhìn thấy states khác nhau.

### 65.21. “R2DBC reactive chỉ là JPA getResultStream”

Không. Reactive driver/data access là mô hình khác; Java Stream trên JPA/JDBC truyền thống vẫn có blocking I/O.

### 65.22. “Test H2 là đủ để kiểm chứng PostgreSQL cursor”

Không. JDBC driver/DB protocol và transaction requirements khác nhau.

### 65.23. “SQL count=1 là KPI hiệu năng tốt nhất”

Không. Phải đo rows, row width, heap, time, GC và pool usage.

### 65.24. “Một benchmark nhanh chứng minh mọi phiên bản/framework đều vậy”

Không. Behavior phụ thuộc provider, driver, DBMS, dataset, query shape, settings và version.

---

## 66. Câu hỏi ôn tập

1. Vì sao `Stream<T>` không đảm bảo server-side cursor?
2. `getResultStream()` của JPA khác `getResultList()` thế nào ở hợp đồng API?
3. Một provider có thể triển khai mặc định getResultStream theo cách nào?
4. Hibernate có thể dùng cơ chế nào thay cho list-backed stream?
5. Những tầng nào nằm giữa Java Stream và physical database rows?
6. JDBC `ResultSet.TYPE_FORWARD_ONLY` có bảo đảm incremental network fetch không?
7. `Statement.setFetchSize(200)` có làm SQL chỉ trả 200 rows không?
8. `setMaxResults(200)` khác fetch size ở đâu?
9. `Stream.limit(200)` có thể vẫn khiến toàn bộ dữ liệu được materialize vì sao?
10. Vì sao `Stream.filter` không tương đương SQL WHERE?
11. Vì sao Java `sorted` có thể phá bounded-memory streaming?
12. `collect(toList)` gây memory growth thế nào?
13. Khi chỉ cần số lượng, nên dùng Stream.count hay SQL COUNT?
14. Stream có cần đóng sau `forEach` không?
15. Vì sao try-with-resources quan trọng với early exit?
16. Nếu consumer throw exception, resources được xử lý thế nào?
17. EntityManager đóng trước khi duyệt Stream gây lỗi gì?
18. Vì sao không nên trả Stream qua một @Transactional method rồi consume ngoài?
19. Spring Data Stream repository cần transaction boundary thế nào?
20. Vì sao Spring readOnly hint không tự bảo đảm JDBC streaming?
21. PostgreSQL JDBC cursor thường cần điều kiện autocommit nào?
22. Vì sao không gọi setAutoCommit trực tiếp trong Spring transaction?
23. MySQL JDBC streaming/cursor configuration có giống PostgreSQL không?
24. Vì sao không nên chạy lazy N+1 queries giữa lúc một MySQL streaming ResultSet đang mở?
25. Hibernate Query.setFetchSize là portable JPA API không?
26. Hibernate @BatchSize giải quyết N+1 khác fetch size ra sao?
27. `hibernate.jdbc.batch_size` liên quan đọc hay ghi?
28. Tại sao stream entity có thể làm first-level cache lớn?
29. DTO projection giảm những loại overhead nào?
30. Khi nào nên dùng Hibernate Query.setReadOnly?
31. Read-only mode có bảo đảm entity không còn trong persistence context không?
32. Detach một entity trong cursor loop có giới hạn gì?
33. em.clear() có nguy cơ gì trong transaction có pending writes?
34. Hibernate StatelessSession khác EntityManager/Session thường ở đâu?
35. `ScrollMode.FORWARD_ONLY` có lợi ích gì?
36. Vì sao code ScrollableResults phải kiểm tra Hibernate version?
37. Tại sao parallel Stream không an toàn với EntityManager?
38. Tại sao JOIN FETCH nhiều to-many vẫn gây row multiplication trong Stream?
39. Lúc nào nên lọc parent bằng EXISTS?
40. Keyset pagination dùng predicate nào với ID tăng?
41. Vì sao keyset có thể giải phóng connection giữa các pages?
42. Vì sao keyset không tự bảo đảm một snapshot toàn bộ export?
43. Offset pagination khác keyset khi dataset lớn?
44. Vì sao export trực tiếp tới HTTP client chậm có nguy cơ hết connection pool?
45. StreamingResponseBody có tự giữ controller transaction không?
46. Tại sao HTTP streaming khác JDBC streaming?
47. Khi nào chọn background export file/object storage?
48. Một DB cursor dài ảnh hưởng MVCC và transaction lifetime như thế nào?
49. Tại sao readOnly không đồng nghĩa REPEATABLE READ?
50. Nếu cần snapshot chính xác, có những lựa chọn nào?
51. Vì sao payload thô 300 MB có thể thành heap dùng hơn 300 MB?
52. L1 cache và JDBC buffer khác nhau thế nào?
53. Một query `ORDER BY` thiếu index ảnh hưởng time to first row ra sao?
54. Fetch size lớn có mặt trái gì?
55. Fetch size nhỏ có mặt trái gì?
56. Công cụ nào đo peak memory và GC trên JVM?
57. Làm sao chứng minh driver đang dùng cursor/incremental fetching?
58. Tại sao test functional Stream không chứng minh performance?
59. Benchmark phải cố định những yếu tố nào?
60. Khi nào một List 50 DTO rows tốt hơn Stream phức tạp?
61. Dấu hiệu nào cho thấy phải chuyển từ cursor sang chunked processing?
62. Cần kiểm thử cancellation/resource cleanup thế nào?
63. Khi nào cần tách database output và HTTP download?
64. Vì sao số SQL statements đơn lẻ không đủ?
65. Hãy thiết kế một thí nghiệm cho 100.000 Orders phân biệt list-backed, cursor-backed và keyset, bao gồm correctness và resource metrics.

---

## 67. Bảng ghi nhớ cuối bài

| Câu hỏi | Câu trả lời ngắn |
|---|---|
| `getResultStream()` có bảo đảm server cursor? | **Không** |
| JPA provider có thể trả List-backed Stream? | **Có** |
| Hibernate có thể dùng scroll? | **Có**, tùy version/path |
| Hibernate scroll có bắt driver stream? | **Không** |
| JDBC fetchSize là gì? | Hint về cách fetch batches |
| fetchSize có giới hạn tổng rows không? | **Không** |
| JPA setMaxResults dùng để làm gì? | Giới hạn query result count |
| Stream.limit tương đương SQL LIMIT? | **Không mặc nhiên** |
| Stream.sorted/collect có giữ data lớn? | **Có thể** |
| Stream entity có bị L1 cache giữ? | **Có thể** |
| DTO projection có lợi gì? | Tránh managed entity overhead |
| Cần transaction khi duyệt cursor? | Thường cần theo provider/driver |
| Có cần close Stream? | **Có**, đặc biệt cursor-backed |
| Có nên return Stream qua closed EM boundary? | **Không** |
| Stream.parallel trên JPA cursor? | **Tránh** |
| PostgreSQL autocommit quan trọng? | **Có** với cursor fetching |
| Driver/DBMS khác nhau? | **Có** |
| @BatchSize là fetchSize JDBC? | **Không** |
| Stream tự chữa N+1? | **Không** |
| Stream tự chữa JOIN multiplication? | **Không** |
| List nhỏ có tốt không? | **Thường rất tốt** |
| Export dài cần giữ connection lâu? | Không nhất thiết; dùng pages |
| Keyset pagination có snapshot guarantee? | **Không** |
| HTTP streaming = JDBC streaming? | **Không** |
| Xác minh bằng gì? | SQL, driver, heap, GC, pool, latency |
| Tối ưu thứ gì trước? | Query shape, projection, dữ liệu cần |

### Sơ đồ quyết định cuối bài

```text
                  CẦN ĐỌC NHIỀU KẾT QUẢ JPA
                              |
                              v
                     Cần bao nhiêu rows?
                         /           \
                 Ít, đã giới hạn     Rất nhiều
                        |               |
                        v               v
                getResultList()      Có cần Entity managed?
                + DTO projection         /          \
                                        CÓ          KHÔNG
                                         |             |
                                         v             v
                                 Cân nhắc lifecycle   DTO/scalar
                                 / L1 cache costs     projection
                                         |             |
                                         +------+------+
                                                |
                                                v
                                  Cần xử lý trong một
                                  transaction/cursor dài?
                                      /           \
                                    CÓ            KHÔNG
                                     |              |
                                     v              v
                               JPA Stream /      Keyset pages
                               Hibernate scroll  + short transactions
                                     |              |
                                     v              |
                            Validate provider       |
                            + JDBC cursor mode      |
                            + fetchSize             |
                                     |              |
                                     v              v
                              close resources   checkpoint pages
                              manage EM/tx      bounded memory
                                     |              |
                                     +-------+------+
                                             |
                                             v
                                 Đo heap, SQL rows,
                                connection lifetime,
                                 throughput, errors
                                             |
                                             v
                                 Đạt correctness,
                                  consistency và
                                vận hành ổn định?
```

**Nguyên tắc cuối bài:** API `getResultStream()` chỉ cung cấp một **cách duyệt kết quả ở Java**. Khả năng tải dữ liệu theo từng phần thực tế phụ thuộc JPA provider, JDBC driver, database, fetch size, transaction và cách consumer dùng Stream. Ngay cả khi cursor-backed, việc tải managed entities có thể làm persistence context lớn lên, Java operations như `collect(toList)`/`sorted()` có thể materialize toàn bộ dữ liệu, và một Stream mở lâu có thể làm cạn connection pool. Hãy ưu tiên **truy vấn đúng dữ liệu bằng projection, predicate và ordering ở SQL**; với kết quả rất lớn, chọn giữa cursor-backed DTO processing và **bounded keyset/chunk transactions** theo yêu cầu consistency, memory và connection lifetime. Cuối cùng, **chứng minh bằng đo đạc** trên provider/driver/DBMS thật — không suy luận hiệu năng từ chữ “Stream” trong tên API.

