# Khi nào truy cập qua ORM phù hợp và khi nào cần SQL hoặc JDBC trực tiếp

Trong ứng dụng Java dùng cơ sở dữ liệu quan hệ, Hibernate/JPA giúp lập trình viên làm việc với đối tượng và vòng đời của thực thể (entity). Tuy nhiên, không phải mọi truy vấn đều nên đi qua cơ chế ánh xạ đối tượng. Có những công việc cần kiểm soát trực tiếp câu SQL; có những công việc cần xử lý từng dòng dữ liệu hoặc thao tác JDBC ở mức thấp.

Mục tiêu của bài này là **chọn cách truy cập dữ liệu dựa trên đặc điểm công việc**, hiểu chi phí của từng cách và biết phối hợp chúng an toàn trong cùng một ứng dụng.

## 1. Phân biệt ORM, SQL và JDBC

Ba thuật ngữ này thuộc các tầng khác nhau:

| Khái niệm | Vai trò | Ví dụ trong Java |
| --- | --- | --- |
| **SQL** | Ngôn ngữ khai báo thao tác với cơ sở dữ liệu quan hệ: lọc, kết hợp bảng, tổng hợp, cập nhật, khóa dữ liệu… | `SELECT ... JOIN ...`, `UPDATE ... WHERE ...` |
| **JDBC** | API Java để mở kết nối, gửi SQL, gắn tham số và đọc `ResultSet` | `DataSource`, `Connection`, `PreparedStatement` |
| **ORM** | Ánh xạ hàng dữ liệu thành entity, quản lý quan hệ, trạng thái và đồng bộ thay đổi với database | JPA `EntityManager`, Hibernate `Session` |

**ORM cuối cùng vẫn phát sinh SQL** và Hibernate thường sử dụng JDBC ở tầng dưới để làm việc với database. Vì vậy, “dùng SQL” không đồng nghĩa với “bỏ Hibernate”: ứng dụng có thể gửi native SQL qua `EntityManager` hoặc `Session`, đồng thời vẫn tận dụng transaction hiện tại.

Trong thực tế có bốn kiểu truy cập thường gặp:

1. **ORM với entity/JPQL/Criteria**: thao tác trên mô hình đối tượng; Hibernate sinh SQL.
2. **Truy vấn projection qua ORM**: chỉ lấy những trường cần thiết vào DTO, không nhất thiết tạo entity đầy đủ.
3. **Native SQL thông qua JPA/Hibernate**: chủ động viết SQL, nhưng vẫn dùng hạ tầng session/transaction của ORM.
4. **JDBC trực tiếp** (hoặc công cụ như Spring JDBC): tự chuẩn bị lệnh SQL, nhận kết quả và quyết định cách ánh xạ từng dòng.

Việc chọn giữa chúng phụ thuộc vào **dạng dữ liệu cần xử lý, lượng dữ liệu, mức kiểm soát SQL và yêu cầu giao dịch**; không nên áp một cách duy nhất cho toàn bộ ứng dụng.

## 2. Khi nào ORM là lựa chọn phù hợp?

ORM đặc biệt có ích khi nghiệp vụ xoay quanh **vòng đời của entity**: tạo đơn hàng, đổi trạng thái, thêm chi tiết, quản lý quan hệ khách hàng–đơn hàng, kiểm tra quy tắc nghiệp vụ trước khi lưu.

### 2.1. Đọc và thay đổi một tập entity có kích thước hợp lý

Giả sử ứng dụng có entity `PurchaseOrder` ánh xạ bảng `purchase_orders`, với các thuộc tính `id`, `status`, `customer`, `totalAmount`. Một thao tác đổi trạng thái có thể viết như sau:

~~~java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
    if (order == null) {
        throw new IllegalArgumentException("Không tìm thấy đơn hàng");
    }
    order.setStatus(OrderStatus.SHIPPED);

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

Đây là ví dụ với **transaction do ứng dụng tự quản lý**. Trong ứng dụng dùng Spring hoặc Jakarta EE, framework thường quản lý `EntityManager` và transaction thay cho đoạn mã bao quanh.

Khi `order` đang ở trạng thái **managed**, Hibernate theo dõi thay đổi (dirty checking) và phát lệnh `UPDATE` lúc đồng bộ (flush), thường trước khi commit. Không cần gọi `persist()` lần nữa chỉ để cập nhật một entity đã được quản lý.

ORM mang lại các lợi ích:

- Mô hình Java phản ánh tương đối rõ các khái niệm nghiệp vụ và quan hệ giữa chúng.
- Persistence context giữ danh tính entity trong một phiên làm việc: đọc cùng một entity theo khóa chính thường trả về cùng đối tượng managed.
- Dirty checking, quan hệ, cascade và optimistic locking có thể giảm đáng kể mã lặp khi dùng đúng.
- JPQL/Criteria diễn đạt nhiều truy vấn thông thường bằng mô hình entity thay vì phụ thuộc tên bảng và cột cụ thể.
- Logic trong domain/service dễ duy trì khi mô hình nghiệp vụ liên tục thay đổi.

**Điều kiện quan trọng:** số entity nạp vào bộ nhớ phải phù hợp, quan hệ được fetch có chủ đích và SQL thực tế do Hibernate sinh ra phải được quan sát.

### 2.2. Truy vấn thông thường và danh sách API

Với màn hình danh sách chỉ hiển thị vài cột, có thể dùng **DTO projection** thay vì lấy cả entity và toàn bộ quan hệ.

~~~java
// com.example.OrderSummary là DTO có constructor (Long, BigDecimal).
List<OrderSummary> page = em.createQuery("""
    SELECT new com.example.OrderSummary(o.id, o.totalAmount)
    FROM PurchaseOrder o
    WHERE o.customer.id = :customerId
    ORDER BY o.createdAt DESC, o.id DESC
    """, OrderSummary.class)
    .setParameter("customerId", customerId)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

Điểm đáng chú ý: **ORM không có nghĩa là lúc nào cũng phải nạp entity**. JPQL/Criteria có thể trả về projection hiệu quả cho các trang danh sách. Với các trang rất sâu, cần cân nhắc chi phí của `OFFSET` và khả năng dùng keyset pagination.

### 2.3. Quan hệ, quy tắc miền và cập nhật có tính nhất quán

ORM có giá trị lớn khi việc ghi dữ liệu liên quan nhiều entity cùng một aggregate, chẳng hạn đơn hàng và các dòng hàng. Tùy ánh xạ, cascade có thể giúp lưu thay đổi liên quan, còn trường phiên bản `@Version` hỗ trợ phát hiện cập nhật cạnh tranh bằng optimistic locking.

Dù vậy, **cascade không thay thế thiết kế transaction**, và lazy loading không đồng nghĩa với hiệu năng tốt: cả hai cần được cấu hình theo yêu cầu của từng ca sử dụng.

## 3. Khi nào nên tự viết SQL?

Khi kết quả cần là **bảng tính toán/tập hàng dữ liệu** hơn là một đồ thị entity, SQL thường diễn đạt vấn đề tự nhiên và rõ ràng hơn.

Những trường hợp tiêu biểu:

- **Báo cáo và phân tích:** `GROUP BY`, tổng hợp nhiều bảng, `HAVING`, hàm cửa sổ (window function), CTE, truy vấn phân cấp.
- **Truy vấn tối ưu chuyên biệt:** cần quyết định chính xác cách join, projection, câu SQL hoặc tận dụng đặc tính của hệ quản trị cụ thể.
- **Thao tác hàng loạt:** cập nhật/xóa hàng chục nghìn hoặc hàng triệu bản ghi theo điều kiện chung mà không cần áp dụng logic riêng lên từng entity.
- **Tính năng theo database:** `UPSERT`, `RETURNING`, JSON/JSONB, full-text search, stored procedure, loại khóa đặc thù… tùy PostgreSQL, MySQL, Oracle, SQL Server, v.v.

### 3.1. Báo cáo doanh thu không cần tạo hàng nghìn entity

Ví dụ tìm 20 khách hàng có tổng giá trị đơn đã thanh toán cao nhất kể từ một thời điểm:

~~~sql
SELECT c.id AS customer_id,
       c.name AS customer_name,
       SUM(o.total_amount) AS revenue
FROM customers c
JOIN purchase_orders o ON o.customer_id = c.id
WHERE o.status = 'PAID'
  AND o.created_at >= ?
GROUP BY c.id, c.name
ORDER BY revenue DESC
~~~

Database có thể thực hiện join, lọc và tổng hợp rồi chỉ trả về số ít hàng kết quả. Nếu thay bằng cách nạp mọi `PurchaseOrder` qua ORM và cộng tiền trong Java, ứng dụng sẽ chịu chi phí truyền dữ liệu, cấp phát đối tượng và bộ nhớ không cần thiết.

Có thể thực thi SQL trực tiếp **qua Hibernate/JPA**, vẫn giữ transaction của `EntityManager`:

~~~java
@SuppressWarnings("unchecked")
List<Object[]> topCustomers = em.createNativeQuery("""
    SELECT c.id, c.name, SUM(o.total_amount) AS revenue
    FROM customers c
    JOIN purchase_orders o ON o.customer_id = c.id
    WHERE o.status = :status AND o.created_at >= :fromTime
    GROUP BY c.id, c.name
    ORDER BY revenue DESC
    """)
    .setParameter("status", "PAID")
    .setParameter("fromTime", fromTime)
    .setMaxResults(20)
    .getResultList();
~~~

Ví dụ trên dùng **named parameter trong native query do Hibernate hỗ trợ**; tính tương thích của cú pháp/kiểu dữ liệu cần kiểm tra nếu đổi provider JPA hoặc hệ quản trị cơ sở dữ liệu. Với kết quả phức tạp, nên ánh xạ rõ sang DTO hoặc result mapping và xác minh kiểu số do driver trả về (`BigDecimal`, `Long`, v.v.).

**Đừng vội chọn native SQL cho mọi phép tổng hợp.** JPQL hỗ trợ nhiều phép `JOIN`, `COUNT`, `SUM`, `GROUP BY`; hãy dùng JPQL khi nó diễn đạt gọn và sinh SQL phù hợp. Native SQL hữu ích khi truy vấn trở nên khó biểu đạt, khó tối ưu hoặc phụ thuộc tính năng database.

### 3.2. Cập nhật hàng loạt: không tải mọi entity để sửa một thuộc tính

Ví dụ đóng các đơn hàng cũ theo một điều kiện duy nhất. JPQL bulk update có thể đủ:

~~~java
int updated = em.createQuery("""
    UPDATE PurchaseOrder o
    SET o.status = :closed
    WHERE o.status = :pending
      AND o.createdAt < :cutoff
    """)
    .setParameter("closed", OrderStatus.CLOSED)
    .setParameter("pending", OrderStatus.PENDING)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
~~~

Bulk JPQL và native SQL đều có thể thao tác trực tiếp trên các hàng trong database, **bỏ qua dirty checking theo từng entity**, các callback entity và nhiều cơ chế tự động ở cấp đối tượng. Chúng thường cũng không tự đồng bộ trạng thái của những entity đã nạp trong persistence context. Vì vậy cần cân nhắc `flush()`, `clear()` hoặc `refresh()` đúng lúc, cùng ảnh hưởng tới version/locking và cache.

Nếu cập nhật cần chạy logic nghiệp vụ riêng cho từng đơn hàng, bulk SQL có thể **không phù hợp** dù chạy nhanh hơn. Khi đó hãy dùng ORM theo batch có kiểm soát, hoặc thiết kế lại logic để đưa quy tắc cần thiết xuống một câu SQL an toàn.

## 4. Khi nào JDBC trực tiếp đáng sử dụng?

JDBC trao quyền kiểm soát về kết nối, `PreparedStatement`, tham số, cách duyệt `ResultSet`, kích thước batch và khả năng xử lý dữ liệu tuần tự. Đổi lại, lập trình viên phải tự giải quyết nhiều việc mà ORM thường làm hộ.

Các ca sử dụng có lý do rõ ràng:

- **Xuất dữ liệu lớn** ra CSV, hệ thống khác hoặc pipeline: đọc lần lượt, xử lý từng hàng, tránh tạo một danh sách entity khổng lồ.
- **Nạp dữ liệu khối lượng lớn**: thao tác batch, quản lý thời điểm commit và đo chi phí chuyển đổi dữ liệu.
- **Tích hợp thư viện/hệ thống cấp thấp** cần `Connection` hoặc `PreparedStatement` thật.
- **Truy vấn chỉ đọc có cấu trúc đơn giản nhưng tần suất rất cao**, nơi chi phí ánh xạ có thể quan trọng sau khi đo đạc thực tế.

Ví dụ đọc các đơn đã thanh toán theo luồng bằng `DataSource`:

~~~java
// Giả định OrderRow là record (long id, long customerId, BigDecimal total).
String sql = """
    SELECT id, customer_id, total_amount
    FROM purchase_orders
    WHERE status = ? AND created_at >= ?
    ORDER BY id
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         sql, ResultSet.TYPE_FORWARD_ONLY, ResultSet.CONCUR_READ_ONLY)) {

    ps.setString(1, "PAID");
    ps.setTimestamp(2, Timestamp.valueOf(fromTime));
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            OrderRow row = new OrderRow(
                rs.getLong("id"),
                rs.getLong("customer_id"),
                rs.getBigDecimal("total_amount"));
            exportSink.accept(row);
        }
    }
}
~~~

Trong đó `exportSink` là thành phần nhận từng hàng để xuất/tiêu thụ ngay, không tích lũy toàn bộ hàng vào `List`. Các import JDBC/`BigDecimal` và cách tạo `DataSource` được lược bỏ để tập trung vào lựa chọn truy cập.

`setFetchSize(500)` là **gợi ý cho driver**, không bảo đảm mọi driver đều stream từ server. Chẳng hạn, một số driver cần thêm cấu hình cursor/transaction hoặc chế độ forward-only. Muốn xử lý dữ liệu rất lớn, phải kiểm tra tài liệu driver đang sử dụng, hành vi autocommit và mức dùng bộ nhớ thực tế.

Với ghi hàng loạt, `PreparedStatement.addBatch()` và `executeBatch()` có thể giảm round-trip. Tuy nhiên Hibernate cũng có JDBC batching khi cấu hình phù hợp; JDBC tự viết **không tự động nhanh hơn** ORM. Đặc biệt, chiến lược sinh khóa (ví dụ một số trường hợp dùng identity) có thể ảnh hưởng khả năng batch insert của ORM.

## 5. Bảng quyết định theo tình huống

| Tình huống | Cách nên cân nhắc trước | Lý do |
| --- | --- | --- |
| Tạo đơn hàng, sửa trạng thái, quản lý các dòng hàng | ORM entity | Cần vòng đời đối tượng, quan hệ và quy tắc nghiệp vụ. |
| API liệt kê 20 đơn với 3 trường | JPQL/Criteria DTO projection | Lấy đúng các trường cần hiển thị, tránh nạp graph entity dư thừa. |
| Trang chi tiết đơn kèm khách hàng và một số quan hệ | ORM với fetch plan có chủ đích | Dễ thao tác domain; phải kiểm soát lazy load/N+1. |
| Tổng hợp doanh thu theo nhóm, xếp hạng, CTE phức tạp | SQL qua JPA/Hibernate hoặc JDBC | Đưa phép tính về database, tận dụng khả năng SQL. |
| Đổi trạng thái hàng trăm nghìn bản ghi theo cùng điều kiện | JPQL bulk update hoặc SQL | Database cập nhật theo tập hàng, không materialize mỗi entity. |
| Xuất hàng triệu dòng sang tệp | JDBC có cơ chế đọc từng hàng, hoặc API streaming được cấu hình đúng | Giảm bộ nhớ ứng dụng; cần kiểm chứng cách driver fetch. |
| Nhập dữ liệu số lượng lớn | Hibernate batching hoặc JDBC batching | Chọn sau khi đo throughput, giới hạn bộ nhớ và xử lý lỗi từng batch. |
| `UPSERT` hoặc cú pháp đặc thù database | Native SQL/JDBC | Có thể không được JPQL biểu đạt trực tiếp. |
| Tìm kiếm lọc đơn giản, có phân trang | ORM/JPQL | Dễ bảo trì; tối ưu projection và index khi cần. |

Không nhất thiết phải chọn một công nghệ cho cả module. Ví dụ service đơn hàng có thể dùng ORM để ghi nghiệp vụ, một native query để tính bảng xếp hạng và JDBC để xuất báo cáo dung lượng lớn.

## 6. Quy trình chọn công cụ trong một use case

Hãy trả lời theo thứ tự sau:

1. **Cần entity có trạng thái hay chỉ cần các hàng/cột kết quả?** Nếu cần sửa và quản lý quan hệ, ưu tiên ORM. Nếu chỉ cần báo cáo hoặc DTO, tránh nạp entity đầy đủ.
2. **Dữ liệu trả về lớn đến đâu?** Với hàng triệu dòng, tính đến phân trang, cursor/streaming, batch và giới hạn bộ nhớ ngay từ thiết kế.
3. **Logic chủ yếu nằm ở Java hay là thao tác trên tập dữ liệu?** Quy tắc trên từng aggregate thường hợp ORM; tổng hợp, lọc và cập nhật set-based thường hợp SQL.
4. **JPQL/Criteria có biểu đạt truy vấn rõ và sinh SQL tốt không?** Nếu có, chưa cần native SQL. Nếu cần CTE, window function hoặc tính năng riêng của DB, cân nhắc native SQL.
5. **Có thực sự cần quyền điều khiển JDBC ở mức thấp không?** Chỉ chuyển sang JDBC trực tiếp khi cần hành vi driver/stream/batch/tích hợp cụ thể hoặc có số đo chỉ ra lợi ích.
6. **Đã đo được nút thắt chưa?** Nếu chưa, xem SQL sinh ra, kế hoạch thực thi, index, số round-trip, bộ nhớ và thời gian thực tế trước khi thay đổi kiến trúc.

Một nguyên tắc thực dụng: **bắt đầu từ cách đơn giản nhất đáp ứng đúng nghiệp vụ và yêu cầu hiệu năng đã biết; tối ưu tại nơi có bằng chứng**.

## 7. Những chi phí ORM cần nhận diện trước khi bỏ ORM

### 7.1. N+1 query do quan hệ lazy

Ví dụ tải 100 đơn hàng rồi gọi `order.getCustomer().getName()` cho từng đơn. Nếu `customer` chưa được nạp, Hibernate có thể gửi thêm nhiều lệnh SQL. Cụm từ “N+1” nói đến một truy vấn lấy danh sách và thêm N truy vấn để lấy quan hệ.

Trước khi đổi cả đoạn sang JDBC, có thể sửa cách fetch:

~~~java
List<PurchaseOrder> orders = em.createQuery("""
    SELECT o
    FROM PurchaseOrder o
    JOIN FETCH o.customer
    WHERE o.id IN :ids
    """, PurchaseOrder.class)
    .setParameter("ids", ids)
    .getResultList();
~~~

Với quan hệ to-one như `customer`, fetch join thường là lựa chọn hữu ích. Với quan hệ to-many, fetch join kết hợp phân trang có thể làm nhân số hàng kết quả, gây sai kỳ vọng hoặc khiến Hibernate phân trang trong bộ nhớ. Các lựa chọn khác gồm `EntityGraph`, batch fetching, projection hay truy vấn hai bước lấy ID rồi lấy chi tiết.

### 7.2. Nạp quá nhiều thuộc tính, entity và bộ nhớ

Nếu chỉ cần `id` và `totalAmount`, projection thường rẻ hơn việc nạp entity cùng các cột không cần thiết. Nếu sửa số lượng lớn entity trong một transaction, persistence context có thể giữ quá nhiều đối tượng; xem xét xử lý theo lô và `flush()/clear()` ở điểm phù hợp.

### 7.3. Quá nhiều câu lệnh thay vì thao tác trên tập

Vòng lặp 50.000 entity và gọi setter có thể tạo rất nhiều `UPDATE`, ngay cả khi batching được bật. Nếu thay đổi đồng nhất và không cần callback của từng entity, một bulk update có thể hợp lý hơn. Cần phân biệt *ít SQL hơn* với *đúng nghiệp vụ*: bulk update thay đổi ngữ nghĩa của vòng đời entity.

### 7.4. Chi phí không chỉ đến từ ORM

Một câu SQL chậm vẫn có thể chậm nếu chạy bằng JDBC: thiếu index, join không phù hợp, thống kê cũ, locking, network và lượng dữ liệu trả về thường tác động lớn hơn chi phí ánh xạ Java. Vì vậy đổi `EntityManager` sang `PreparedStatement` không bảo đảm chữa được truy vấn chậm.

## 8. Trộn ORM, native SQL và JDBC trong cùng transaction

Việc phối hợp là bình thường, nhưng cần đặc biệt chú ý **trạng thái trong persistence context** và **kết nối thuộc transaction nào**.

### 8.1. Bulk SQL có thể làm entity managed trở nên cũ

Giả sử một `PurchaseOrder` đã được `em.find()` nạp với `status = PENDING`. Sau đó native SQL đổi trạng thái hàng tương ứng trong database. Đối tượng đang ở bộ nhớ không tự cập nhật chỉ vì hàng trong database đã đổi.

Khi chủ động làm bulk update, một cách xử lý là:

~~~java
em.flush(); // Đẩy các thay đổi entity đang chờ xuống DB trước.

int changed = em.createNativeQuery("""
    UPDATE purchase_orders
    SET status = :newStatus
    WHERE status = :oldStatus
    """)
    .setParameter("newStatus", "CLOSED")
    .setParameter("oldStatus", "PENDING")
    .executeUpdate();

em.clear(); // Bỏ các entity managed cũ; lần đọc sau nạp lại.
~~~

`clear()` **detach toàn bộ entity** đang được quản lý. Chỉ dùng khi phù hợp với luồng nghiệp vụ và chắc chắn các thay đổi cần thiết đã được `flush()` hoặc xử lý; có thể chọn `refresh()` với một vài entity cụ thể thay vì clear tất cả. Bộ đệm cấp hai hay cache ứng dụng cũng cần được xem xét nếu ghi ngoài cơ chế quản lý entity.

### 8.2. Kết nối JDBC phải tham gia đúng transaction

Nếu ứng dụng dùng Spring `@Transactional`, một `JdbcTemplate` được cấu hình cùng `DataSource` và transaction manager có thể tham gia transaction đang hoạt động. Nếu tự gọi `dataSource.getConnection()` rồi `commit()` độc lập, thao tác có thể đi vào một transaction khác hoặc phá vỡ giả định về ranh giới giao dịch.

Khi sử dụng Hibernate và cần thao tác trực tiếp trên connection gắn với session, có thể dùng:

~~~java
Session session = em.unwrap(Session.class);

session.doWork(connection -> {
    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE purchase_orders SET status = ? WHERE id = ?")) {
        ps.setString(1, "SHIPPED");
        ps.setLong(2, orderId);
        ps.executeUpdate();
    }
});
~~~

`doWork()` là API riêng của Hibernate, truyền connection do session quản lý. **Không tự đóng connection và không tự commit/rollback** trong callback này; transaction bên ngoài chịu trách nhiệm. Cũng cần đồng bộ trạng thái entity sau cập nhật bằng JDBC giống như khi dùng native SQL.

Trong môi trường Jakarta EE/JTA, cách lấy và tham gia transaction lại phụ thuộc cấu hình container. Trước khi pha trộn các công cụ, phải xác nhận cơ chế transaction thực tế của dự án.

## 9. An toàn, tính đúng đắn và khả năng bảo trì

**Truyền tham số, không ghép trực tiếp dữ liệu người dùng vào SQL.** Trong JDBC hãy dùng `PreparedStatement`; trong JPQL/native query dùng tham số có bind. Ví dụ:

~~~java
// Đúng: dữ liệu tìm kiếm được bind thành một giá trị.
PreparedStatement ps = connection.prepareStatement(
    "SELECT id, name FROM customers WHERE email = ?");
ps.setString(1, email);
~~~

Placeholder chỉ đại diện cho **giá trị**, không đại diện cho tên bảng, cột hoặc từ khóa SQL. Nếu API cho phép chọn cột sắp xếp, hãy ánh xạ từ tập tên cột được cho phép thay vì nối chuỗi tùy ý.

Ngoài SQL injection, cần lưu ý:

- **Transaction và concurrency:** ranh giới commit/rollback, isolation, optimistic/pessimistic locking và thứ tự cập nhật phải phù hợp cả khi dùng ORM lẫn SQL.
- **Logic tự động:** native SQL/bulk JPQL không kích hoạt đầy đủ lifecycle callback, validation hoặc cascade như khi làm việc với entity. Nếu cần các bất biến nghiệp vụ, phải thực thi chúng bằng cách thích hợp.
- **Cấu trúc kết quả:** JDBC/native SQL yêu cầu mã ánh xạ cột sang kiểu Java; nên dùng DTO rõ ràng, tránh rải `Object[]` và vị trí cột khắp code.
- **Tính di động:** JPQL thường ít phụ thuộc cú pháp DB hơn; native SQL tận dụng tối đa tính năng DB nhưng tăng chi phí khi đổi hệ quản trị.
- **Kiểm thử:** nên có integration test với loại database, driver và cách quản lý transaction tương tự môi trường thật, nhất là cho native SQL và JDBC streaming.
- **Quan sát:** bật log SQL/metrics phù hợp trong môi trường phát triển, theo dõi số query, thời gian, số hàng trả về và tình trạng pool kết nối; tránh log giá trị nhạy cảm.

## 10. Ba ca sử dụng trong một hệ thống bán hàng

Giả sử một hệ thống có giao diện quản lý đơn, dashboard phân tích doanh thu và tác vụ xuất dữ liệu hàng đêm.

**Ca A — Nhân viên xác nhận một đơn hàng.** Dịch vụ kiểm tra trạng thái hiện tại, quyền người dùng, kho hàng và đổi trạng thái trong một transaction. Chọn ORM entity vì nghiệp vụ phụ thuộc vào trạng thái và quan hệ của đơn. Dùng `@Version` nếu cần phát hiện hai người cập nhật cùng lúc.

**Ca B — Dashboard hiển thị doanh thu theo nhóm khách hàng của 90 ngày gần nhất.** Chỉ cần các nhóm và tổng doanh thu, không cần hành vi của `PurchaseOrder`. Ưu tiên truy vấn tổng hợp tại database; bắt đầu bằng JPQL nếu đủ diễn đạt, dùng native SQL nếu cần CTE/window function hoặc tối ưu riêng. Trả về DTO cho dashboard.

**Ca C — Mỗi đêm xuất vài triệu đơn hàng sang kho dữ liệu.** Không giữ hàng triệu entity trong persistence context. Dùng truy vấn SQL có lựa chọn cột chính xác và cơ chế đọc theo luồng hoặc theo lô; JDBC có thể là lựa chọn tốt nếu driver hỗ trợ streaming và tác vụ cần xử lý từng `ResultSet`. Đặt giới hạn thời gian, lưu trạng thái tiến độ và quản lý transaction theo đặc điểm DB.

Ba cách truy cập có thể cùng tồn tại trong một module. Điểm chung cần giữ là **một hợp đồng dữ liệu nhất quán**: schema, quy tắc cập nhật, transaction và cách ánh xạ kết quả.

## 11. Đo hiệu năng trước và sau khi quyết định

Nếu một tính năng chậm, thực hiện các bước chẩn đoán có thứ tự:

1. **Xác định mục tiêu**: độ trễ p95 của API, số hàng/giây của job, bộ nhớ tối đa, hoặc số lượng query trên một request.
2. **Quan sát số lệnh SQL thực tế**: nhận diện N+1, query lặp, `SELECT *` ngoài ý muốn, nhiều lần flush.
3. **Kiểm tra kế hoạch truy vấn** bằng `EXPLAIN` hoặc công cụ của database, cùng index và số hàng thực sự đọc/trả về.
4. **Tối ưu ngay trên cách đang dùng**: fetch plan, projection, phân trang, index, cấu hình batch, hoặc đưa phép tổng hợp vào database.
5. **So sánh phương án** trên dữ liệu và mức đồng thời đại diện: ORM/JPQL, native SQL qua Hibernate và JDBC trực tiếp nếu cần.
6. **Kiểm tra tính đúng đắn sau tối ưu**: transaction, kết quả trả về, lock, trạng thái cache, thứ tự và phân trang ổn định.

Ví dụ, nếu thời gian chủ yếu nằm ở database vì thiếu index, JDBC khó mang lại khác biệt đáng kể. Nếu SQL vốn nhanh nhưng tầng Java cấp phát quá nhiều entity, projection hoặc JDBC streaming có thể cải thiện rõ.

## 12. Những kết luận dễ gây nhầm lẫn

- **“ORM luôn chậm hơn SQL.”** ORM phát sinh SQL; hiệu năng phụ thuộc câu SQL, số lần truy cập DB, cách fetch và ánh xạ. ORM có thể đủ nhanh cho phần lớn thao tác nghiệp vụ.
- **“Muốn viết SQL bắt buộc phải dùng JDBC.”** Hibernate/JPA hỗ trợ native SQL; có thể giữ quản lý transaction của ORM.
- **“Lazy loading luôn tiết kiệm truy vấn.”** Lazy chỉ trì hoãn tải dữ liệu và có thể gây N+1 nếu truy cập quan hệ trong vòng lặp.
- **“Bulk update giống vòng lặp setter nhưng nhanh hơn.”** Nó bỏ qua nhiều cơ chế ở cấp entity, có thể làm trạng thái trong persistence context cũ và ảnh hưởng version/callback.
- **“Gọi `setFetchSize()` là chắc chắn streaming.”** Hành vi phụ thuộc driver, transaction và cấu hình kết nối.
- **“Chỉ cần bỏ ORM là giải quyết được truy vấn chậm.”** Nhiều nút thắt đến từ index, SQL plan, lock hoặc network.

## 13. Bài tập áp dụng lựa chọn

Với mỗi tình huống dưới đây, hãy nêu cách truy cập ban đầu và một rủi ro cần kiểm tra:

1. Một API cần hiển thị 30 đơn mới nhất, mỗi đơn chỉ có mã, ngày và tổng tiền.
2. Một job đổi trạng thái 400.000 đơn quá hạn, nhưng hệ thống hiện có callback gửi thông báo khi từng entity đổi trạng thái.
3. Một trang dashboard dùng hàm cửa sổ để tính thứ hạng doanh thu; kết quả chỉ có 10 hàng.
4. Một tác vụ xuất 8 triệu bản ghi, driver đang dùng chưa được kiểm tra khả năng đọc cursor.

Gợi ý định hướng: (1) projection và phân trang; (2) xác minh ý nghĩa của callback trước khi dùng bulk update; (3) native SQL thông qua hạ tầng transaction hiện có; (4) thiết kế streaming/batching và đo hành vi driver trước khi quyết định. Không nên chỉ chọn theo số lượng hàng mà bỏ qua nghiệp vụ và tính đúng đắn.

**Nguyên tắc ghi nhớ:** dùng ORM khi bài toán là quản lý entity và quy tắc miền; dùng truy vấn SQL khi bài toán chủ yếu là xử lý tập dữ liệu ở database; dùng JDBC khi thực sự cần điều khiển chi tiết cách gửi SQL, truyền dữ liệu và tiêu thụ kết quả. Có thể phối hợp cả ba, miễn là transaction, cache và ngữ nghĩa nghiệp vụ được giữ nhất quán.
