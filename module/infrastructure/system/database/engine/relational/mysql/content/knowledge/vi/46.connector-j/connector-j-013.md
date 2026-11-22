# Fetch size, useCursorFetch và đọc tập kết quả lớn dạng luồng

Khi một truy vấn trả về hàng trăm nghìn hoặc hàng triệu dòng, cách đọc kết quả có thể quyết định ứng dụng dùng vài MB hay chiếm hết heap. MySQL Connector/J mặc định nhận và lưu toàn bộ kết quả truy vấn ở phía client trước khi ứng dụng duyệt `ResultSet`. Cách này đơn giản nhưng tốn bộ nhớ theo kích thước kết quả.

Connector/J cung cấp hai cơ chế để xử lý tập kết quả lớn: chế độ streaming tương thích cũ bằng `setFetchSize(Integer.MIN_VALUE)` và cursor phía server bằng `useCursorFetch=true` kết hợp `Statement.setFetchSize(n)` hoặc `PreparedStatement.setFetchSize(n)` với giá trị dương. Hai cơ chế có cách vận hành khác nhau; cần chọn theo workload, phiên bản driver và yêu cầu xử lý.

Bài học dùng MySQL Connector/J 8.x/9.x với MySQL Server 8.0/8.4. Kiểm tra tài liệu đúng phiên bản Connector/J đang triển khai vì một số thuộc tính và hành vi có thể thay đổi theo bản phát hành.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao ResultSet lớn có thể làm đầy heap của ứng dụng.
- Phân biệt fetch size, giới hạn số dòng và phân trang SQL.
- Bật server-side cursor bằng `useCursorFetch` và server-side prepared statement.
- Dùng `setFetchSize()` với giá trị dương để lấy dữ liệu theo từng đợt.
- Dùng chế độ streaming cũ với `Integer.MIN_VALUE` khi phù hợp.
- Chọn batch size, đóng tài nguyên đúng cách và tránh giữ connection/transaction quá lâu.
- Theo dõi bộ nhớ, network round-trip, thời gian xử lý và tác động lên server.

## 1. Vì sao đọc ResultSet lớn cần chú ý bộ nhớ?

Ví dụ truy vấn lấy toàn bộ khách hàng:

```sql
SELECT customer_id, full_name, email
FROM customers;
```

Nếu bảng có vài triệu dòng, ứng dụng có thể nhận một tập kết quả rất lớn. Với cách mặc định của Connector/J, driver đọc kết quả từ server và lưu ở phía client; chỉ sau khi nhận xong, ứng dụng mới duyệt các dòng trong `ResultSet`. Heap cần thiết phụ thuộc vào số dòng, số cột, kích thước chuỗi, object do driver tạo và object ứng dụng giữ lại.

Một lỗi thường gặp là đọc tất cả dòng vào `List<Customer>`:

```java
List<Customer> customers = new ArrayList<>();

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT customer_id, full_name, email FROM customers");
     ResultSet rs = ps.executeQuery()) {
    while (rs.next()) {
        customers.add(new Customer(
            rs.getLong("customer_id"),
            rs.getString("full_name"),
            rs.getString("email")
        ));
    }
}
```

Ngay cả khi driver đọc theo từng đợt, việc giữ tất cả object trong list vẫn làm bộ nhớ tăng theo tổng số dòng. Streaming hoặc cursor chỉ giúp giảm phần dữ liệu ResultSet driver giữ trong bộ nhớ; ứng dụng cũng phải xử lý từng dòng hoặc ghi ra đích theo batch, không gom toàn bộ kết quả vào collection.

## 2. Phân biệt fetch size, LIMIT và pagination

Ba khái niệm này giải quyết ba vấn đề khác nhau:

| Cơ chế | Vai trò | Có làm giảm tổng số dòng truy vấn trả về không? |
|---|---|---|
| `setFetchSize(n)` | Gợi ý hoặc điều khiển số dòng driver lấy mỗi lần fetch trong các chế độ hỗ trợ | Không |
| `LIMIT n` | Giới hạn số dòng SQL trả về | Có |
| Pagination/keyset pagination | Chia một tập dữ liệu thành nhiều truy vấn nhỏ theo trang hoặc theo khóa | Có, mỗi truy vấn chỉ trả về một phần |

`fetchSize=500` không có nghĩa truy vấn chỉ trả về tối đa 500 dòng. Nó có nghĩa driver có thể lấy kết quả theo các đợt khoảng 500 dòng khi cơ chế fetch tương ứng được bật. Nếu truy vấn trả về 2 triệu dòng, ứng dụng vẫn có thể duyệt hết 2 triệu dòng.

Ví dụ giới hạn kết quả bằng SQL:

```sql
SELECT customer_id, full_name
FROM customers
ORDER BY customer_id
LIMIT 500;
```

Ví dụ phân trang theo khóa (keyset pagination):

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id > ?
ORDER BY customer_id
LIMIT 500;
```

Keyset pagination hữu ích khi muốn xử lý theo từng trang, lưu checkpoint và tiếp tục sau lỗi. Nó khác với cursor fetch: mỗi trang là một câu SQL mới, còn cursor fetch giữ một `ResultSet` và lấy thêm các dòng từ cùng kết quả.

## 3. Hai cơ chế đọc kết quả lớn trong Connector/J

### 3.1. Chế độ mặc định: buffered ResultSet

Nếu không bật cơ chế fetch đặc biệt, Connector/J thường buffer toàn bộ kết quả ở client. Ưu điểm là dễ sử dụng: có thể đọc kết quả sau khi truy vấn đã hoàn tất, driver có thể hỗ trợ các thao tác điều hướng theo loại `ResultSet` và connection sẵn sàng cho câu lệnh tiếp theo sau khi kết quả được nhận.

Nhược điểm là mức sử dụng heap tăng theo kích thước kết quả. Một truy vấn trả về quá nhiều cột hoặc trường `TEXT`/`BLOB` lớn có thể gây `OutOfMemoryError`, GC liên tục hoặc tăng thời gian phản hồi.

Với kết quả nhỏ và vừa, buffered ResultSet thường là lựa chọn hợp lý. Không cần bật cursor cho mọi truy vấn vì cursor cũng có chi phí phía server và thêm các lần trao đổi mạng.

### 3.2. Cursor phía server: useCursorFetch

`useCursorFetch=true` yêu cầu Connector/J dùng cursor phía server để lấy kết quả theo từng đợt. Cursor chỉ khả dụng qua server-side prepared statements, vì vậy khi bật `useCursorFetch`, Connector/J tự động bật `useServerPrepStmts`.

Cấu hình rõ cả hai thuộc tính trong JDBC URL:

```text
jdbc:mysql://db.example.internal:3306/sales?useServerPrepStmts=true&useCursorFetch=true
```

Khi cursor fetch được bật, đặt fetch size là số nguyên dương trước khi gọi `executeQuery()`. Có thể dùng `PreparedStatement` cho SQL có tham số:

```java
String sql =
    "SELECT customer_id, full_name, email " +
    "FROM customers WHERE customer_id > ? " +
    "ORDER BY customer_id";

try (PreparedStatement ps = connection.prepareStatement(
        sql,
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    ps.setLong(1, lastCustomerId);
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("customer_id");
            String name = rs.getString("full_name");
            String email = rs.getString("email");
            processCustomer(id, name, email);
        }
    }
}
```

Trong ví dụ, `setFetchSize(500)` được gọi trước `executeQuery()`. Driver lấy dữ liệu theo từng nhóm, giúp giảm lượng dữ liệu ResultSet cần giữ ở phía client tại cùng một thời điểm. Ứng dụng vẫn phải duyệt đến cuối kết quả nếu muốn xử lý mọi dòng.

Tài liệu Connector/J cũng minh họa cursor fetch với `Statement` thông thường:

```java
try (Statement st = connection.createStatement()) {
    st.setFetchSize(500);
    try (ResultSet rs = st.executeQuery(
            "SELECT customer_id, full_name FROM customers")) {
        while (rs.next()) {
            processCustomer(
                rs.getLong("customer_id"),
                rs.getString("full_name")
            );
        }
    }
}
```

Với truy vấn có tham số, ưu tiên `PreparedStatement` để bind giá trị an toàn. Với cả hai kiểu statement, hãy dùng ResultSet forward-only/read-only và fetch size dương khi cần cursor fetch. Không gọi `last()`, `absolute()` hoặc thao tác yêu cầu cuộn ngược trên kết quả forward-only.

### 3.3. Chế độ streaming cũ: Integer.MIN_VALUE

Connector/J còn hỗ trợ một chế độ streaming tương thích cũ. Với cơ chế này, tạo statement forward-only/read-only và gọi `setFetchSize(Integer.MIN_VALUE)` trước khi thực thi:

```java
String sql =
    "SELECT customer_id, full_name, email " +
    "FROM customers ORDER BY customer_id";

try (Statement st = connection.createStatement(
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    st.setFetchSize(Integer.MIN_VALUE);

    try (ResultSet rs = st.executeQuery(sql)) {
        while (rs.next()) {
            processCustomer(
                rs.getLong("customer_id"),
                rs.getString("full_name"),
                rs.getString("email")
            );
        }
    }
}
```

`Integer.MIN_VALUE` là giá trị đặc biệt của Connector/J để kích hoạt streaming ResultSet từng dòng; nó không phải batch size âm thông thường. Chế độ này đọc dữ liệu tuần tự từ kết nối, không dùng cursor fetch theo batch phía server.

Trong khi ResultSet streaming còn mở, không thực thi một câu lệnh khác trên cùng connection. Hãy đọc hết hoặc đóng ResultSet trước khi dùng connection cho truy vấn tiếp theo. Connector/J cũng lưu ý rằng statement chưa hoàn tất cho đến khi các dòng đang chờ được đọc hoặc ResultSet được đóng; các lock do statement giữ có thể chỉ được giải phóng khi statement/transaction hoàn tất. Vì vậy, xử lý dữ liệu nhanh và không giữ streaming ResultSet trong lúc chờ tác vụ bên ngoài.

Không kết hợp chế độ `Integer.MIN_VALUE` với kỳ vọng cursor fetch theo batch. Nếu cần điều khiển batch size dương, dùng `useCursorFetch=true` và fetch size dương.

## 4. Cấu hình useCursorFetch

### 4.1. JDBC URL

Ví dụ cấu hình trong ứng dụng:

```properties
db.url=jdbc:mysql://db.example.internal:3306/sales?useServerPrepStmts=true&useCursorFetch=true
db.username=app_reader
```

Không đặt mật khẩu trong URL hoặc file cấu hình được commit vào source control. Lấy credentials từ secret manager hoặc cơ chế cấu hình an toàn của môi trường triển khai.

Nếu dùng connection pool, cấu hình URL/driver properties ở `DataSource` hoặc pool. Mỗi connection được tạo từ pool phải nhận các thuộc tính phù hợp. Tránh bật `useCursorFetch` ở một nơi và vô tình ghi đè `useServerPrepStmts` ở nơi khác.

### 4.2. Cấu hình mặc định cho mọi statement

Connector/J có thuộc tính `defaultFetchSize`. Giá trị mặc định là `0`. Khi đặt giá trị dương, driver gọi `setFetchSize(n)` với giá trị đó trên các statement mới được tạo:

```text
jdbc:mysql://db.example.internal:3306/sales?useCursorFetch=true&defaultFetchSize=500
```

`defaultFetchSize` có phạm vi rộng vì áp dụng cho các statement mới trên connection. Chỉ dùng khi phần lớn truy vấn cần cách fetch này. Trong ứng dụng có nhiều loại truy vấn, đặt `setFetchSize()` riêng trên những câu lệnh trả về nhiều dòng thường dễ kiểm soát hơn.

### 4.3. Kiểm tra cấu hình thực tế

Không suy luận rằng cursor đang hoạt động chỉ vì URL có chuỗi `useCursorFetch=true`. Kiểm tra driver version, thuộc tính DataSource/pool, fetch size của statement và kiểu ResultSet. Nếu server hoặc driver không hỗ trợ cấu hình mong muốn, kiểm tra exception, warning và log JDBC.

Hãy thử một truy vấn nhỏ có cùng kiểu statement trong môi trường kiểm thử trước khi áp dụng cho export hoặc batch job lớn. Đảm bảo fetch size được đặt trước khi statement thực thi.

## 5. Cursor phía server hoạt động như thế nào?

Với server-side prepared statement và cursor fetch, Connector/J gửi yêu cầu thực thi statement theo chế độ cursor. MySQL tạo cursor cho kết quả và driver yêu cầu từng nhóm dòng bằng giao thức fetch. Thay vì chuyển toàn bộ kết quả về client một lần, dữ liệu được truyền theo nhiều lượt.

Điều này giảm lượng dữ liệu driver phải giữ ở client, nhưng không có nghĩa server không cần lưu kết quả. MySQL triển khai server-side cursor bằng cách materialize kết quả vào bảng tạm nội bộ. Bảng tạm ban đầu có thể nằm trong memory và chuyển sang lưu trữ trên đĩa khi vượt giới hạn cấu hình. Vì vậy, truy vấn có thể tiêu tốn bộ nhớ hoặc đĩa phía server, thêm chi phí tạo cursor và tạo nhiều lượt trao đổi mạng.

Server-side cursor của MySQL là read-only, non-scrollable và non-holdable: không dùng cursor để cập nhật hàng, cuộn tùy ý hoặc tiếp tục dùng cursor sau khi transaction commit. Không dùng cursor fetch nếu ứng dụng cần cập nhật hàng qua ResultSet hoặc điều hướng ngẫu nhiên. Khi cần cuộn hoặc truy cập ngẫu nhiên, hãy cân nhắc buffered ResultSet cho kết quả vừa phải hoặc thiết kế truy vấn phân trang.

## 6. Chọn fetch size phù hợp

Fetch size là sự cân bằng giữa bộ nhớ client, số lượt trao đổi mạng và chi phí xử lý:

| Fetch size | Ưu điểm | Hạn chế |
|---|---|---|
| Nhỏ (ví dụ 50–100) | Mỗi batch chiếm ít bộ nhớ client | Nhiều lượt fetch, có thể tăng latency và overhead mạng |
| Vừa (ví dụ 500–1.000) | Cân bằng giữa memory và số round-trip trong nhiều workload | Vẫn cần đo với kích thước hàng thực tế |
| Lớn (ví dụ 5.000–10.000) | Ít lượt fetch hơn, có thể tăng throughput | Batch lớn tốn heap hơn và làm tăng thời gian xử lý mỗi đợt |

Các con số chỉ là điểm bắt đầu để benchmark, không phải giá trị tối ưu mặc định. Một hàng có vài cột số nhỏ khác xa một hàng chứa JSON hoặc BLOB nhiều MB. Với dữ liệu lớn, cùng fetch size nhưng kích thước batch theo byte có thể chênh lệch rất nhiều.

Quy trình chọn giá trị:

1. Đo kích thước trung bình và phân bố kích thước hàng.
2. Chạy cùng truy vấn với một vài fetch size, chẳng hạn 100, 500 và 1.000.
3. Theo dõi heap, GC pause, thời gian truy vấn, tổng thời gian duyệt, network round-trip và CPU/I/O phía server.
4. Kiểm tra số dòng thực sự được xử lý và dữ liệu đầu ra.
5. Chọn giá trị đáp ứng giới hạn bộ nhớ và SLA; benchmark lại khi schema hoặc dữ liệu thay đổi.

Nếu ứng dụng xử lý mỗi dòng rất chậm, giảm fetch size không nhất thiết làm truy vấn nhanh hơn. Cursor vẫn giữ tài nguyên và connection trong suốt thời gian ResultSet mở.

## 7. Quản lý ResultSet, connection và transaction

### 7.1. Luôn đóng tài nguyên

Dùng try-with-resources để đóng ResultSet và statement ngay cả khi xử lý gặp exception:

```java
try (PreparedStatement ps = connection.prepareStatement(
        sql,
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY)) {

    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            processRow(rs);
        }
    }
}
```

Nếu connection lấy từ pool, trả connection về pool sau khi ResultSet và statement đã đóng. Một ResultSet còn mở có thể giữ cursor, bộ nhớ, socket và connection slot. Nếu job bị dừng giữa chừng, đóng statement/connection trong `finally` hoặc try-with-resources để giải phóng tài nguyên.

### 7.2. Connection pool và xử lý lâu

Streaming giữ connection trong suốt thời gian ứng dụng đọc dữ liệu. Nếu mỗi job giữ một connection trong nhiều phút, pool có thể hết connection cho các request thông thường. Hãy tách workload export/reporting khỏi pool phục vụ giao dịch nếu cần, đặt timeout hợp lý và giới hạn số job chạy đồng thời.

Không giữ ResultSet mở trong khi chờ thao tác mạng bên ngoài, gọi API chậm hoặc chờ người dùng. Nếu cần xử lý lâu, cân nhắc đọc một batch, đóng tài nguyên, lưu checkpoint rồi tiếp tục bằng keyset pagination ở truy vấn tiếp theo.

### 7.3. Transaction và snapshot

Server-side cursor không được giữ mở qua commit. Nếu ResultSet được đọc trong một transaction tường minh, đừng commit hoặc rollback trước khi đọc xong và đóng cursor; transaction kết thúc có thể đóng cursor hoặc làm ResultSet không còn dùng được. Với InnoDB, một consistent read kéo dài cũng có thể giữ snapshot cũ lâu, làm chậm purge undo history và tăng áp lực lưu trữ.

Không mặc định bật `autoCommit=false` chỉ để dùng fetch size. Chọn transaction boundary theo yêu cầu nhất quán của nghiệp vụ. Với báo cáo dài, cân nhắc snapshot nhất quán, thời gian đọc, tác động tới purge và cách chia truy vấn theo mốc khóa.

## 8. Streaming hay keyset pagination?

Streaming/cursor fetch phù hợp khi cần duyệt một kết quả liên tục trong một lần chạy, ví dụ export dữ liệu, tính toán tổng hợp phía ứng dụng hoặc gửi dữ liệu sang hệ thống khác.

Keyset pagination phù hợp khi cần:

- Lưu checkpoint và tiếp tục sau khi job bị dừng.
- Nhả connection giữa các batch.
- Giới hạn thời gian transaction và thời gian giữ snapshot.
- Chạy nhiều worker theo các khoảng khóa không chồng lấn.

Ví dụ vòng lặp keyset pagination:

```java
long lastId = 0L;
int pageSize = 500;
long upperBound = readMaxCustomerId(dataSource);

while (lastId < upperBound) {
    String sql =
        "SELECT customer_id, full_name, email " +
        "FROM customers " +
        "WHERE customer_id > ? AND customer_id <= ? " +
        "ORDER BY customer_id LIMIT ?";

    int rows = 0;
    try (Connection conn = dataSource.getConnection();
         PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setLong(1, lastId);
        ps.setLong(2, upperBound);
        ps.setInt(3, pageSize);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                long id = rs.getLong("customer_id");
                processCustomer(
                    id,
                    rs.getString("full_name"),
                    rs.getString("email")
                );
                lastId = id;
                rows++;
            }
        }
    }

    if (rows == 0) {
        break;
    }

    saveCheckpoint(lastId);
}
```

Đoạn code là khung minh họa; trong ứng dụng thực tế cần xử lý lỗi idempotent và lưu checkpoint sau khi dữ liệu đầu ra của batch đã được ghi nhận an toàn. Giới hạn `upperBound` cố định giúp job không liên tục đuổi theo các hàng mới được thêm trong lúc chạy. Nếu dữ liệu nguồn có thể bị xóa hoặc cập nhật trong lúc job chạy, xác định rõ semantics của snapshot và cutoff trước khi bắt đầu.

Keyset pagination yêu cầu thứ tự ổn định và cột phân trang có index phù hợp. Nếu khóa sắp xếp không duy nhất, dùng thêm khóa phụ duy nhất, ví dụ `(created_at, customer_id)`, để tránh bỏ sót hoặc lặp hàng giữa các trang. Tránh `OFFSET` lớn vì server vẫn phải bỏ qua nhiều dòng trước khi trả về trang sau.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `OutOfMemoryError` khi chạy truy vấn lớn | ResultSet được buffer toàn bộ hoặc ứng dụng giữ mọi dòng trong collection | Dùng cursor/streaming hoặc pagination; xử lý từng dòng và không tích lũy toàn bộ object. |
| `setFetchSize(500)` không giảm memory | `useCursorFetch` chưa bật, fetch size không dương hoặc cấu hình statement không phù hợp | Kiểm tra URL properties, server-side prepared statements, ResultSet type và driver version. |
| Streaming ResultSet còn active | Chạy statement khác trên cùng connection khi ResultSet streaming chưa đóng | Đọc hết hoặc đóng ResultSet trước khi dùng connection tiếp. |
| Cursor bị đóng giữa chừng | Statement/connection đóng hoặc transaction kết thúc trước khi đọc xong | Giữ tài nguyên đến khi duyệt xong; không commit sớm. |
| Connection pool cạn | Job streaming giữ connection quá lâu hoặc chạy quá nhiều đồng thời | Tách pool, giới hạn concurrency, dùng batch pagination và timeout. |
| Throughput thấp với fetch size nhỏ | Quá nhiều lượt fetch và round-trip mạng | Benchmark batch lớn hơn, cân bằng với heap và kích thước hàng. |
| Server tốn temp disk hoặc I/O | Cursor materialize kết quả trong bảng tạm nội bộ | Thu hẹp cột/hàng, tối ưu truy vấn, cân nhắc pagination và theo dõi tài nguyên server. |
| Dữ liệu lặp hoặc thiếu giữa các batch | Thứ tự phân trang không duy nhất hoặc checkpoint sai | Dùng keyset với khóa duy nhất, lưu checkpoint sau khi batch được xử lý an toàn. |

## 10. Quy trình kiểm thử một truy vấn lớn

1. Ghi nhận driver version và JDBC URL properties đang dùng.
2. Chạy truy vấn với buffered ResultSet để có baseline thời gian và heap.
3. Chạy lại bằng `useCursorFetch=true`, server-side prepared statement và fetch size dương.
4. Nếu phù hợp, so sánh với streaming `Integer.MIN_VALUE`.
5. Kiểm tra số dòng, giá trị đầu/cuối, thứ tự và dữ liệu null để xác nhận không mất hoặc lặp hàng.
6. Đo heap, GC, network round-trip, thời gian xử lý và tài nguyên temp phía server.
7. Kiểm tra behavior khi exception xảy ra giữa chừng, đảm bảo tài nguyên được đóng và job có thể tiếp tục theo checkpoint nếu thiết kế yêu cầu.

Đừng benchmark chỉ bằng thời gian `executeQuery()`. Với cursor/streaming, phần lớn thời gian truyền dữ liệu có thể diễn ra trong vòng lặp `ResultSet.next()`. Đo toàn bộ thời gian từ lúc gửi truy vấn đến khi đọc xong và đóng tài nguyên.

## 11. Checklist triển khai

- [ ] Truy vấn chỉ lấy các cột cần thiết và có điều kiện lọc phù hợp.
- [ ] Đã chọn buffered, cursor fetch, legacy streaming hoặc keyset pagination theo workload.
- [ ] Nếu dùng cursor fetch, `useCursorFetch=true` và server-side prepared statement đã được bật.
- [ ] Dùng `PreparedStatement` hoặc `Statement` phù hợp, ResultSet forward-only/read-only và fetch size dương.
- [ ] Nếu dùng legacy streaming, `Integer.MIN_VALUE` được cấu hình có chủ đích.
- [ ] Ứng dụng không giữ toàn bộ kết quả trong collection.
- [ ] ResultSet, Statement và Connection được đóng đúng cách.
- [ ] Connection pool đủ capacity cho job dài và concurrency được giới hạn.
- [ ] Transaction/snapshot lifetime đã được đánh giá.
- [ ] Fetch size được benchmark với kích thước hàng thực tế.
- [ ] Theo dõi heap, GC, round-trip, server temp table và I/O.
- [ ] Có xử lý exception, checkpoint và khả năng tiếp tục nếu job cần chạy lâu.

## 12. Bài tập tự kiểm tra

1. Vì sao fetch size 500 không giới hạn tổng số dòng truy vấn trả về?
2. Để dùng `useCursorFetch`, vì sao Connector/J cần server-side prepared statement?
3. Khác biệt chính giữa `setFetchSize(500)` với cursor fetch và `setFetchSize(Integer.MIN_VALUE)` là gì?
4. Vì sao server-side cursor có thể giảm heap client nhưng vẫn tăng I/O phía server?
5. Tại sao không nên gọi `executeQuery()` lần nữa trên cùng connection khi legacy streaming ResultSet chưa đóng?
6. Trong trường hợp nào keyset pagination phù hợp hơn cursor fetch?
7. Vì sao fetch size lớn không phải lúc nào cũng nhanh hơn?
8. Khi dùng transaction tường minh, điều gì có thể xảy ra nếu commit trước khi đọc hết ResultSet?

**Gợi ý đáp án:** (1) Fetch size quyết định số dòng lấy mỗi lượt; `LIMIT` mới giới hạn tổng dòng SQL. (2) Cursor fetch của MySQL dùng giao thức server-side prepared statement. (3) Giá trị dương kết hợp `useCursorFetch` lấy từng batch qua server cursor; `Integer.MIN_VALUE` kích hoạt chế độ streaming cũ, đọc tuần tự từ kết nối. (4) MySQL materialize kết quả cursor vào bảng tạm nội bộ, có thể dùng memory hoặc disk. (5) Connection còn một kết quả streaming chưa tiêu thụ; driver không thể bắt đầu statement khác trên connection đó. (6) Khi cần checkpoint, nhả connection giữa các batch, giới hạn transaction hoặc tiếp tục sau lỗi. (7) Batch lớn tăng memory và thời gian xử lý mỗi lượt; kích thước hàng và network ảnh hưởng kết quả. (8) Transaction commit đóng cursor; ResultSet không thể tiếp tục đọc.

## Tài liệu tham khảo

- [MySQL Connector/J Developer Guide: JDBC API Implementation Notes](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-implementation-notes.html)
- [MySQL Connector/J Developer Guide: Performance Extensions](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html)
- [MySQL Connector/J Developer Guide: Configuration Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-configuration-properties.html)
- [MySQL 8.4 Reference Manual: Restrictions on Server-Side Cursors](https://dev.mysql.com/doc/refman/8.4/en/cursor-restrictions.html)
- [MySQL 8.4 Reference Manual: Prepared Statements](https://dev.mysql.com/doc/refman/8.4/en/sql-prepared-statements.html)
