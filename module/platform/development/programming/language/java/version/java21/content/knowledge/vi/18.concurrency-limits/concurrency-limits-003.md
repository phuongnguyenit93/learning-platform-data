# Connection pool cơ sở dữ liệu khi dùng virtual thread

Virtual thread cho phép ứng dụng Java 21 xử lý rất nhiều request đang chờ I/O mà không cần tạo một platform thread cho mỗi request. Nhưng database vẫn có giới hạn về số connection và lượng truy vấn có thể xử lý hiệu quả cùng lúc. Vì vậy, khi chuyển sang virtual thread, connection pool vẫn cần thiết và trở thành ranh giới điều tiết số tác vụ được truy cập database đồng thời.

Không nên tăng kích thước connection pool theo số virtual thread. Hãy định cỡ pool theo năng lực database, ngân sách connection được cấp cho ứng dụng và thời gian giữ connection của workload. Những virtual thread chưa lấy được connection có thể chờ, còn pool bảo vệ database khỏi việc mở quá nhiều session cùng lúc.

## 1. Vì sao vẫn cần connection pool?

Một JDBC connection đại diện cho một session làm việc với database. Tạo connection vật lý thường cần thiết lập mạng, xác thực, khởi tạo trạng thái session và cấp tài nguyên ở cả phía ứng dụng lẫn database. Tạo mới connection cho từng câu SQL thường tốn kém và làm tăng tải cho database.

Connection pool giữ một nhóm connection vật lý để tái sử dụng:

- Khi request cần truy cập database, nó lấy một connection từ pool.
- Khi hoàn thành công việc, nó đóng logical connection để trả connection vật lý về pool.
- Request khác có thể nhận lại connection đó.
- Khi tất cả connection đang được sử dụng, request tiếp theo phải chờ hoặc nhận timeout theo cấu hình pool.

Virtual thread thay đổi chi phí của việc chờ, nhưng không thay đổi số connection mà database có thể phục vụ. Một request đang chờ connection vẫn là một virtual thread còn sống; nó chưa thực hiện truy vấn và không chiếm một connection database.

## 2. Pool là giới hạn database, không phải giới hạn thread

Giả sử ứng dụng có 20.000 request đang chạy trên virtual thread và connection pool có tối đa 30 connection:

~~~text
             20.000 virtual threads
                       |
                       v
             DataSource.getConnection()
                       |
             +---------+---------+
             |                   |
             v                   v
       Có connection        Pool đã đủ 30
             |                   |
             v                   v
       Tối đa 30 tác vụ      Chờ connection
       đang dùng DB          hoặc hết timeout
             |                   |
             v                   |
       Query / transaction       |
             |                   |
             v                   |
       close connection ----------+
             |
             v
       Connection trở lại pool
~~~

Trong mô hình này:

- Số virtual thread phản ánh số tác vụ đang được quản lý.
- Số carrier thread phản ánh số virtual thread có thể chạy Java code tại một thời điểm.
- Số connection đang được pool cấp phản ánh số tác vụ có thể tương tác với database qua pool đó cùng lúc.

Ba con số này phục vụ ba mục đích khác nhau. Không cần một platform thread riêng cho mỗi connection, và cũng không cần tạo một virtual thread pool chỉ để giới hạn số truy vấn.

Tài liệu Oracle về virtual thread nêu rõ connection pool tự đóng vai trò như một semaphore: nếu pool có 10 connection, caller thứ 11 phải chờ lấy connection. Không cần thêm một Semaphore khác để áp đặt đúng cùng giới hạn database đó.

## 3. Dùng DataSource và connection pool

Ứng dụng nên phụ thuộc vào javax.sql.DataSource để lấy JDBC connection. DataSource có thể là implementation của pool như HikariCP hoặc một pool do application server/framework quản lý.

Ví dụ cấu hình HikariCP:

~~~java
HikariConfig config = new HikariConfig();

config.setJdbcUrl(System.getenv("DB_JDBC_URL"));
config.setUsername(System.getenv("DB_USERNAME"));
config.setPassword(System.getenv("DB_PASSWORD"));

config.setMaximumPoolSize(20);
config.setConnectionTimeout(1_500);

HikariDataSource dataSource = new HikariDataSource(config);
~~~

Các thuộc tính quan trọng:

| Thuộc tính HikariCP | Ý nghĩa |
|---|---|
| **maximumPoolSize** | Số connection tối đa của pool, tính cả connection idle và connection đang được mượn |
| **connectionTimeout** | Thời gian tối đa caller chờ lấy connection trước khi pool báo lỗi |
| **minimumIdle** | Số connection idle tối thiểu pool cố gắng duy trì |
| **maxLifetime** | Tuổi thọ tối đa của connection trước khi pool loại bỏ nó theo chính sách |
| **leakDetectionThreshold** | Ngưỡng để pool ghi log khi một connection bị giữ quá lâu, hỗ trợ tìm lỗi quên trả connection |

Ví dụ dùng 20 connection và 1.500 ms chỉ minh họa cách cấu hình. Giá trị production phải dựa trên giới hạn database, số instance ứng dụng, SLA và kết quả load test. Không sao chép nguyên các con số này cho mọi hệ thống.

Khởi tạo pool ở vòng đời ứng dụng và đóng nó khi ứng dụng dừng. Không tạo một pool mới cho mỗi request hoặc mỗi virtual thread; mỗi pool có thể mở thêm connection vật lý và làm vượt ngân sách database.

## 4. Lấy và trả connection trong virtual thread

Virtual thread có thể gọi JDBC API đồng bộ như platform thread. Dùng try-with-resources để đảm bảo connection, statement và result set được đóng dù truy vấn thành công hay phát sinh exception.

~~~java
static Optional<User> findUser(
        DataSource dataSource,
        long userId) throws SQLException {

    String sql = """
        select id, name
        from users
        where id = ?
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setQueryTimeout(2);
        statement.setLong(1, userId);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                return Optional.empty();
            }

            return Optional.of(new User(
                result.getLong("id"),
                result.getString("name")
            ));
        }
    }
}
~~~

Khi dùng connection pool, connection.close() thông thường trả logical connection về pool thay vì đóng session vật lý ngay lập tức. Đây là hành vi do implementation của pool cung cấp.

Không giữ connection trong field static, không chia sẻ cùng một connection cho nhiều virtual thread và không lưu connection trong một object dùng chung giữa các request. Mỗi đơn vị công việc nên sở hữu connection trong khoảng thời gian cần thiết rồi trả lại pool.

## 5. Giữ transaction ngắn và trả connection sớm

Connection thường bị giữ trong suốt transaction. Nếu transaction kéo dài, connection đó không thể được request khác mượn, đồng thời có thể giữ lock hoặc snapshot trong database.

Ví dụ, nếu request cần truy vấn database rồi gọi HTTP service, hãy hoàn thành và đóng phần làm việc với database trước khi chờ dịch vụ bên ngoài:

~~~java
User user;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "select id, name from users where id = ?")) {

    statement.setLong(1, userId);

    try (ResultSet result = statement.executeQuery()) {
        if (!result.next()) {
            throw new NoSuchElementException("Không tìm thấy user");
        }

        user = new User(
            result.getLong("id"),
            result.getString("name")
        );
    }
}

// Connection đã được trả về pool.
// Có thể chờ HTTP service mà không giữ connection database.
ExternalProfile profile = httpClient.fetchProfile(user.id());
~~~

Nếu nghiệp vụ cần transaction bao trùm nhiều câu SQL, hãy dùng cùng một connection cho transaction đó, commit hoặc rollback đúng cách rồi đóng connection. Không tách một transaction logic thành nhiều connection độc lập nếu cần tính nhất quán nguyên tử.

Tránh thực hiện các việc sau trong khi đang giữ connection hoặc transaction nếu chúng không cần thiết:

- Gọi HTTP service hoặc RPC bên ngoài.
- Chờ người dùng nhập liệu hoặc xác nhận.
- Chờ một semaphore không liên quan tới database.
- Thực hiện tính toán CPU lâu hoặc xử lý file lớn.
- Đưa công việc sang một tác vụ khác rồi chờ kết quả trong khi vẫn giữ connection.

Virtual thread giúp request chờ mà không nhất thiết giữ carrier, nhưng connection bị mượn vẫn chiếm một slot của pool trong suốt thời gian đó.

## 6. Định cỡ pool theo năng lực database

Số virtual thread có thể lớn hơn số connection rất nhiều. Kích thước pool phải xuất phát từ ngân sách connection và khả năng xử lý thực tế của database.

Một quy trình định cỡ thực tế:

1. Xác định giới hạn connection của database hoặc proxy/pooler đứng trước database.
2. Trừ phần dành cho quản trị, migration, monitoring, batch job và các ứng dụng khác.
3. Chia ngân sách còn lại cho số replica tối đa của ứng dụng.
4. Xem xét số DataSource/pool mà mỗi replica tạo ra; tổng các pool mới là số connection tối đa mà replica có thể mở.
5. Load test với truy vấn, transaction, dữ liệu và mức tải gần production.
6. Tăng hoặc giảm pool từng bước, theo dõi throughput, latency và tải database để tìm điểm hiệu quả.

Ví dụ: ngân sách dành cho một dịch vụ là 120 connection và hệ thống có thể scale tối đa 4 replica. Nếu mỗi replica có một pool, giới hạn ban đầu có thể được phân bổ tối đa 30 connection mỗi replica. Cần trừ thêm nếu mỗi replica có nhiều pool hoặc nếu có worker riêng dùng cùng database.

Không lấy số virtual thread, số request đồng thời hoặc số CPU của application server làm giá trị trực tiếp cho maximumPoolSize.

### Dùng thời gian giữ connection để ước lượng ban đầu

Định luật Little có thể giúp ước lượng số connection đang bận trung bình:

**Connection đang bận trung bình ≈ Throughput DB × Thời gian giữ connection trung bình**

Ví dụ, ứng dụng thực hiện trung bình 300 đơn vị công việc database mỗi giây và mỗi đơn vị giữ connection 40 ms:

~~~text
300 × 0,040 = 12
~~~

Khoảng 12 connection đang bận trung bình là điểm tham khảo ban đầu. Đây không phải kích thước pool production đã được xác định: burst, phân bố latency, transaction dài, truy vấn khóa nhau và năng lực database đều ảnh hưởng kết quả. Hãy dùng load test và metrics để xác nhận.

Các hướng dẫn sizing của HikariCP cũng khuyến nghị bắt đầu với pool nhỏ, đo trên workload thực tế và tránh giả định nhiều connection hơn luôn làm throughput tăng. Khi database đã bão hòa CPU, I/O hoặc lock contention, tăng connection có thể làm latency xấu hơn.

## 7. Phân bổ connection khi chạy nhiều replica

Giới hạn pool thường áp dụng trên từng process. Nếu chạy nhiều replica, tổng connection có thể vượt xa maximumPoolSize được cấu hình ở một replica.

Ví dụ:

| Thành phần | Số lượng |
|---|---:|
| Replica tối đa | 5 |
| maximumPoolSize mỗi replica | 24 |
| Tổng connection ứng dụng có thể mở | 120 |
| Ngân sách database dành cho dịch vụ | 100 |

Cấu hình trên có thể vượt ngân sách 20 connection khi tất cả replica đạt cực đại. Cần phân bổ lại pool size hoặc ngân sách replica để tổng connection nằm trong giới hạn.

Khi autoscaling, hãy tính theo số replica tối đa có thể chạy đồng thời, không chỉ số replica trung bình. Cũng cần tính các pool riêng cho read/write datasource, tenant, batch worker hoặc service khác dùng chung database.

Nếu dùng database proxy hoặc external pooler, cần hiểu proxy quản lý session vật lý và transaction như thế nào. Không mặc định rằng proxy có thể multiplex mọi connection của ứng dụng thành một số session nhỏ hơn trong mọi kiểu workload.

## 8. Timeout: phân biệt chờ connection và chờ truy vấn

Có nhiều loại timeout khác nhau. Đặt timeout cho truy vấn không thay thế timeout lấy connection từ pool.

| Timeout | Phạm vi | API/vị trí cấu hình |
|---|---|---|
| Chờ lấy connection | Caller chờ pool cấp connection | Cấu hình riêng của pool, ví dụ HikariCP connectionTimeout |
| Thiết lập kết nối vật lý | Tạo kết nối mới tới database | Driver hoặc DataSource login timeout |
| Thực thi SQL | Thời gian statement được phép chạy | Statement.setQueryTimeout(seconds) |
| Chờ phản hồi mạng của connection | Thời gian JDBC connection chờ database trả lời một request mạng | Connection.setNetworkTimeout(executor, milliseconds) nếu driver hỗ trợ |
| Transaction | Tổng thời gian transaction được phép tồn tại | Database hoặc transaction manager/framework |
| Toàn bộ request | Ngân sách thời gian xử lý request | Server hoặc tầng ứng dụng |

Ví dụ đặt query timeout:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql)) {

    statement.setQueryTimeout(3);

    try (ResultSet result = statement.executeQuery()) {
        // Đọc kết quả.
    }
}
~~~

setQueryTimeout tính bằng giây. Khi timeout, JDBC driver ném SQLTimeoutException nếu truy vấn vượt giới hạn được áp dụng. Chi tiết hủy câu lệnh và tác động lên connection cần được kiểm tra theo driver/database.

Connection.setNetworkTimeout có phạm vi khác với query timeout. JDBC API cảnh báo rằng nếu network timeout hết hạn, driver có thể đánh dấu connection đã đóng và các statement/result set liên quan không còn sử dụng được. Phương thức này cũng có thể không được driver hỗ trợ. Không dùng nó như một timeout query thông thường mà không đọc tài liệu driver.

Timeout lấy connection cần phù hợp với deadline tổng thể của request. Nếu request chỉ còn 300 ms, không nên cho nó chờ pool thêm 30 giây. Khi pool thường xuyên timeout, hãy điều tra saturation hoặc query chậm thay vì chỉ tăng timeout.

## 9. Khi pool cạn connection

Khi toàn bộ connection đang được sử dụng, các virtual thread tiếp tục gọi getConnection() sẽ chờ. Nếu connection được trả về trước khi acquisition timeout hết hạn, một caller có thể tiếp tục. Nếu không, pool báo lỗi để ứng dụng xử lý.

Cần phân biệt:

- **Pool saturation:** số connection active chạm giới hạn và caller phải chờ.
- **Connection leak:** code không đóng connection hoặc giữ connection lâu hơn dự kiến.
- **Slow query/transaction:** connection được dùng quá lâu do SQL, lock hoặc transaction.
- **Database saturation:** database không thể xử lý thêm công việc hiệu quả dù ứng dụng có thể mở thêm connection.
- **Request overload:** hệ thống nhận nhiều request hơn khả năng xử lý, làm số virtual thread đang chờ tăng liên tục.

Tăng maximumPoolSize chỉ có thể giúp nếu database còn năng lực xử lý. Nếu database đã bão hòa, tăng pool thường làm tăng số truy vấn cạnh tranh và có thể khiến mọi request chậm hơn.

Pool timeout nên được xử lý như một tín hiệu quá tải hoặc lỗi hạ tầng tạm thời. Tùy hợp đồng API, ứng dụng có thể trả lỗi tạm thời như HTTP 503, ghi metric và áp dụng retry có giới hạn ở client. Không retry ngay lập tức liên tục vì điều đó có thể làm pool và database quá tải thêm.

## 10. Có cần thêm Semaphore trước connection pool không?

Thông thường là không, nếu semaphore chỉ có cùng mục tiêu giới hạn số truy cập database như pool.

Ví dụ không cần thiết:

~~~java
private static final Semaphore DB_LIMIT = new Semaphore(20);

static User loadUser(DataSource dataSource, long id)
        throws Exception {

    DB_LIMIT.acquire();
    try (Connection connection = dataSource.getConnection()) {
        return queryUser(connection, id);
    } finally {
        DB_LIMIT.release();
    }
}
~~~

Nếu pool đã có maximumPoolSize = 20, semaphore trên tạo thêm một hàng chờ thứ hai cho cùng giới hạn nhưng không tăng số connection database có thể sử dụng. Hai cơ chế làm đường đi lấy connection khó quan sát hơn; nếu cấu hình hai giới hạn không khớp, semaphore còn có thể giảm concurrency dưới mức pool cho phép.

Semaphore vẫn có ích nếu nó bảo vệ một tài nguyên khác hoặc một phần workload cụ thể, ví dụ:

- Giới hạn số truy vấn báo cáo nặng để không cạnh tranh với truy vấn giao dịch.
- Giới hạn số request gọi một dịch vụ ngoài.
- Bảo vệ một tài nguyên dùng chung không được connection pool quản lý.

Nếu cần tách workload database, hãy xác định rõ ngân sách connection của từng pool và tổng ngân sách database. Đừng vô tình tạo nhiều pool độc lập có tổng maximumPoolSize vượt giới hạn.

## 11. Backpressure ở tầng request

Pool giới hạn số connection đang được sử dụng, nhưng bản thân nó không nhất thiết giới hạn số virtual thread đang chờ lấy connection. Nếu server nhận vô hạn request, số request đang chờ có thể tiếp tục tăng và giữ request body, context, trace span cùng nhiều object khác trong heap.

Vì vậy, cần hai lớp điều tiết:

1. **Pool database:** giới hạn số connection và truy vấn có thể hoạt động cùng lúc.
2. **Admission control/backpressure:** giới hạn số request được nhận hoặc được phép tiến sâu vào luồng xử lý khi hệ thống quá tải.

Tùy server/framework, có thể dùng giới hạn request đang xử lý, queue có giới hạn, rate limiter, từ chối sớm hoặc trả response quá tải. Không dùng một fixed platform-thread pool chỉ để giới hạn truy cập database; connection pool đã có vai trò giới hạn connection.

Nếu có semaphore cho một tài nguyên khác, hãy đặt nó tại đúng ranh giới của tài nguyên đó và luôn release permit trong finally.

## 12. Theo dõi pool và database

Để biết pool có đang được định cỡ phù hợp hay không, cần quan sát cả ứng dụng và database.

| Metric | Câu hỏi cần trả lời |
|---|---|
| Active connections | Bao nhiêu connection đang được mượn? Có thường xuyên chạm maximum không? |
| Idle connections | Pool còn connection sẵn sàng không? |
| Pending/waiting callers | Có bao nhiêu request đang chờ connection? |
| Acquisition time | Caller mất bao lâu để lấy được connection? |
| Connection usage duration | Connection bị giữ trong bao lâu? |
| Acquisition timeout count | Bao nhiêu request không lấy được connection kịp thời? |
| Query/transaction latency | SQL hoặc transaction nào giữ connection lâu? |
| DB CPU, I/O, locks, active sessions | Database còn khả năng xử lý thêm không? |

Với HikariCP, có thể xuất metrics qua cơ chế metrics registry hoặc quan sát qua JMX nếu cấu hình phù hợp. Leak detection giúp phát hiện connection bị giữ quá lâu, nhưng không thay thế việc đóng resource đúng cách.

Một số dấu hiệu và hướng điều tra:

- Active luôn bằng maximum, pending tăng: xem acquisition time, query latency và database capacity.
- Active thấp nhưng acquisition timeout xuất hiện: kiểm tra kết nối vật lý, pool lifecycle, network và cấu hình nhiều pool.
- Connection usage duration cao: kiểm tra transaction dài, code chờ HTTP khi giữ connection, ResultSet lớn hoặc xử lý dữ liệu bên trong transaction.
- Database CPU/lock tăng khi pool tăng: giảm concurrency hoặc tối ưu query/index thay vì tăng connection tiếp.
- Số virtual thread sống tăng mạnh trong khi pending connection cao: thêm admission control và kiểm tra request nào giữ dữ liệu trong lúc chờ.

## 13. Lưu ý về JDBC driver và virtual thread trên Java 21

Virtual thread được thiết kế để chờ blocking I/O mà không giữ carrier trong nhiều trường hợp. Tuy nhiên, không nên giả định mọi JDBC driver đều có cùng hành vi.

Trên Java 21–23, virtual thread có thể bị pin vào carrier nếu blocking xảy ra bên trong synchronized hoặc native method. Nếu JDBC driver dùng các đoạn mã như vậy trong đường đi blocking, throughput có thể bị ảnh hưởng. Điều này phụ thuộc driver, phiên bản driver, thao tác SQL và runtime; không có nghĩa mọi JDBC query đều pin virtual thread.

Khi kiểm thử driver:

- Dùng đúng phiên bản JDBC driver dự kiến triển khai.
- Đo thời gian lấy connection, thời gian query và thời gian giữ connection.
- Theo dõi JFR event jdk.VirtualThreadPinned trên Java 21.
- Kiểm tra thread dump khi pool bão hòa hoặc query bị treo.
- Nâng cấp driver nếu có bản sửa lỗi liên quan đến virtual thread và kiểm thử lại trước khi triển khai.

Từ Java 24, JEP 491 loại bỏ monitor-related pinning khi blocking bên trong synchronized. Tuy nhiên, native method và foreign function vẫn có thể pin virtual thread. Nếu ứng dụng chạy JDK mới hơn Java 21, hãy áp dụng hướng dẫn tương ứng với runtime thực tế.

## 14. Checklist thiết kế connection pool với virtual thread

- [ ] Dùng một connection pool có vòng đời ở cấp ứng dụng hoặc service.
- [ ] Không tạo connection pool mới cho từng request hoặc từng virtual thread.
- [ ] Không tạo virtual thread pool chỉ để giới hạn số truy vấn database.
- [ ] Đặt maximumPoolSize theo ngân sách database và tổng số replica tối đa.
- [ ] Dùng acquisition timeout phù hợp với deadline của request.
- [ ] Dùng try-with-resources để trả connection, statement và result set đúng lúc.
- [ ] Giữ transaction ngắn; không chờ HTTP, file I/O hoặc người dùng khi đang giữ connection.
- [ ] Đặt query timeout và timeout mạng theo hỗ trợ của JDBC driver.
- [ ] Không thêm Semaphore trùng với giới hạn mà connection pool đã thực hiện.
- [ ] Dùng admission control/backpressure để giới hạn request đang sống khi pool bão hòa.
- [ ] Theo dõi active, idle, pending, acquisition time, usage duration và timeout.
- [ ] Load test trên database và JDBC driver giống production trước khi thay đổi pool size.

## Tài liệu tham khảo chính thức

- [Oracle Java 21 — Virtual Threads: Use Semaphores to Limit Concurrency](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Java SE 21 API — DataSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/javax/sql/DataSource.html)
- [Java SE 21 API — Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html)
- [Java SE 21 API — Statement.setQueryTimeout](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html#setQueryTimeout(int))
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP/wiki/Configuration)
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)

