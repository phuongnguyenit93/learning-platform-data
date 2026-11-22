# Vai trò của r2dbc-pool và điều kiện cần sử dụng

Trong ứng dụng Spring Data Relational R2DBC, mỗi lần truy cập cơ sở dữ liệu cần một connection do R2DBC driver cung cấp. Việc tạo connection vật lý có thể tốn thời gian và tài nguyên: ứng dụng phải mở kết nối mạng, xác thực, thiết lập session và sử dụng một phần giới hạn connection mà database cho phép.

`r2dbc-pool` là thư viện pool dành cho R2DBC. Nó quản lý một tập connection có thể tái sử dụng, cho phép nhiều thao tác mượn connection trong thời gian ngắn rồi trả connection về pool sau khi hoàn tất. Pool giúp giới hạn số connection đồng thời và giảm chi phí tạo kết nối lặp lại.

Pool không phải điều kiện bắt buộc để sử dụng Spring Data R2DBC. Ứng dụng chỉ nên thêm nó khi mô hình tải, chi phí kết nối hoặc giới hạn tài nguyên của database cho thấy việc tái sử dụng connection có ích. Bài học này giải thích vai trò, vòng đời connection, điều kiện sử dụng, cách cấu hình và những điểm cần theo dõi khi vận hành.

## 1. ConnectionFactory và connection trong R2DBC

R2DBC SPI định nghĩa `ConnectionFactory` là thành phần tạo connection tới database. Driver của từng hệ quản trị cung cấp cách tạo `ConnectionFactory` tương ứng với giao thức và cấu hình kết nối của database đó.

Ví dụ, ứng dụng kết nối PostgreSQL có thể dùng driver `r2dbc-postgresql`; khi gọi `create()` trên connection factory, driver tạo một connection để làm việc với database. Nếu ứng dụng thường xuyên tạo rồi đóng connection, mỗi lần có thể phát sinh chi phí kết nối vật lý.

Vòng đời đơn giản của một connection không dùng pool:

~~~text
Ứng dụng
   |
   | ConnectionFactory.create()
   v
R2DBC driver
   |
   | mở connection vật lý
   v
Database
   |
   | thực hiện câu lệnh SQL
   v
Ứng dụng đóng connection
   |
   v
Connection vật lý được giải phóng
~~~

`ConnectionFactory` là điểm truy cập chung mà Spring R2DBC, `DatabaseClient`, `R2dbcEntityTemplate`, repository và transaction manager có thể sử dụng. Các thành phần này không cần biết chi tiết giao thức mạng của từng database.

## 2. r2dbc-pool làm nhiệm vụ gì?

`r2dbc-pool` cung cấp một `ConnectionPool` hoạt động như một `ConnectionFactory`. Pool bọc một connection factory do driver cung cấp, quản lý các connection vật lý và cấp một connection logic cho mỗi lần ứng dụng yêu cầu.

Khi ứng dụng gọi `create()` trên pool:

1. Pool tìm connection đang rảnh và còn hợp lệ.
2. Nếu có connection phù hợp, pool cấp connection đó cho người gọi.
3. Nếu chưa có connection rảnh và pool chưa đạt giới hạn, pool có thể tạo connection vật lý mới.
4. Nếu pool đã đạt giới hạn, yêu cầu phải chờ một connection được trả về hoặc hết thời gian chờ.
5. Khi người gọi đóng connection logic, pool thu hồi lease và đưa connection vật lý trở lại trạng thái có thể tái sử dụng, nếu connection vẫn hợp lệ.

Sơ đồ khái quát:

~~~text
                 +-------------------------+
                 |  Spring Data R2DBC      |
                 |  DatabaseClient         |
                 |  Repository / Service   |
                 +------------+------------+
                              |
                              v
                    +------------------+
                    | ConnectionPool   |
                    | max-size = 20    |
                    +---+----------+---+
                        |          |
                 connection     connection
                    rảnh          đang dùng
                        |          |
                        v          v
                  +--------------------+
                  |   R2DBC driver     |
                  +---------+----------+
                            |
                            v
                         Database
~~~

Pool quản lý việc mượn và trả connection. Nó không thay thế driver, không thực thi SQL thay repository và không tự quyết định transaction isolation.

### 2.1. Tái sử dụng connection vật lý

Một connection vật lý có thể được dùng cho nhiều thao tác ở các thời điểm khác nhau. Sau khi một thao tác hoàn tất và connection được trả về pool, yêu cầu tiếp theo có thể mượn lại connection đó.

Việc tái sử dụng giúp giảm số lần mở session mới, giảm độ trễ do thiết lập kết nối và tránh tạo quá nhiều connection đồng thời. Lợi ích rõ hơn khi ứng dụng xử lý nhiều request ngắn, liên tục truy cập cùng một database.

Connection được mượn từ pool là một lease. Khi thao tác kết thúc, ứng dụng phải đóng lease để pool biết rằng connection có thể được tái sử dụng. Trong Spring Data R2DBC, các abstraction của Spring quản lý vòng đời connection trong những thao tác repository và transaction thông thường. Khi tự làm việc trực tiếp với R2DBC SPI, lập trình viên phải bảo đảm connection được đóng trong mọi đường kết thúc, kể cả khi publisher lỗi hoặc bị hủy.

### 2.2. Giới hạn số connection đồng thời

Pool có giới hạn `max-size`. Khi đạt giới hạn, pool không tiếp tục mở vô hạn connection vật lý. Yêu cầu mới phải đợi connection được trả về hoặc nhận lỗi timeout nếu chờ quá lâu.

Điều này bảo vệ database khỏi việc một ứng dụng tạo số lượng session không kiểm soát. Tuy nhiên, `max-size` quá thấp có thể làm các request xếp hàng; `max-size` quá cao có thể làm database hết connection hoặc tăng tranh chấp tài nguyên.

### 2.3. Quản lý connection không còn sử dụng được

Connection có thể mất hiệu lực vì database khởi động lại, mạng bị gián đoạn, session bị server đóng hoặc connection đã tồn tại quá lâu. Pool có các cơ chế giới hạn tuổi thọ, thời gian idle và kiểm tra connection theo cấu hình.

Khi connection không còn phù hợp để tái sử dụng, pool có thể loại bỏ nó và tạo connection mới theo nhu cầu. Việc validation có thể thêm một lượt kiểm tra vào đường lấy connection, vì vậy cần chọn chiến lược phù hợp với driver và môi trường.

## 3. Khi nào nên sử dụng r2dbc-pool?

Việc thêm pool nên xuất phát từ đặc điểm vận hành của ứng dụng, không phải chỉ vì dự án sử dụng R2DBC.

### 3.1. Ứng dụng phục vụ nhiều request đồng thời

Một API server thường có nhiều request cùng truy cập database. Nếu mỗi thao tác đều tạo connection vật lý mới, chi phí kết nối có thể tăng nhanh và số session đồng thời khó kiểm soát.

Pool phù hợp khi:

- Ứng dụng nhận nhiều request ngắn và lặp lại truy cập cùng database.
- Có nhiều tác vụ reactive cùng cần connection trong các khoảng thời gian chồng lấn.
- Chi phí mở connection đáng kể so với thời gian thực hiện truy vấn.
- Database có giới hạn connection cần được chia sẻ giữa nhiều instance ứng dụng.
- Muốn tạo giới hạn rõ ràng cho số thao tác đang giữ connection.

### 3.2. Database hoặc hạ tầng có giới hạn connection

Database thường có giới hạn số session/connection. Một ứng dụng có nhiều instance cũng có thể tạo ra tổng số connection lớn dù mỗi instance chỉ mở một số lượng vừa phải.

Pool giúp đặt giới hạn theo từng instance. Khi tính toán, phải tính tổng số connection có thể được mở bởi tất cả instance, không chỉ nhìn vào `max-size` của một tiến trình.

### 3.3. Chi phí tạo connection cao

Nếu database nằm qua mạng, có bước xác thực hoặc thiết lập TLS, tạo connection mới liên tục có thể gây độ trễ và tải không cần thiết. Tái sử dụng connection có thể cải thiện thời gian phản hồi và giảm công việc ở database.

Lợi ích thực tế phụ thuộc driver, database, network, thời gian sống của request và cách ứng dụng sử dụng connection. Hãy đo trước và sau khi bật pool để xác nhận thay đổi có ích.

### 3.4. Cần giới hạn tải database từ ứng dụng

Pool là một điểm điều tiết số connection đang được ứng dụng sử dụng. Khi database đã đạt mức tải phù hợp, giới hạn pool có thể khiến request chờ ở phía ứng dụng thay vì mở thêm session làm database chịu tải cao hơn.

Đây không phải cơ chế tự động điều khiển tải hoàn chỉnh. Nếu thời gian giữ connection quá dài hoặc số request chờ tăng liên tục, cần xử lý nguyên nhân ở truy vấn, transaction, backpressure hoặc giới hạn request.

## 4. Khi nào chưa cần sử dụng pool?

Pool bổ sung thêm dependency, cấu hình và trạng thái cần giám sát. Có trường hợp không cần dùng:

- Ứng dụng chạy một lần để thực hiện một tác vụ nhỏ, ít kết nối database.
- Công cụ dòng lệnh hoặc batch ngắn có rất ít thao tác database.
- Môi trường kiểm thử đơn giản, không cần mô phỏng tải đồng thời hoặc pool production.
- Ứng dụng có rất ít request và việc tạo connection chưa phải nút thắt.
- Hạ tầng đã cung cấp một cơ chế quản lý pool ở lớp kết nối khác và ứng dụng không cần thêm một pool thứ hai.
- Có yêu cầu đặc thù cần connection riêng cho từng thao tác và đã kiểm chứng rằng pool không mang lại lợi ích.

Không dùng pool không có nghĩa ứng dụng không thể dùng Spring Data R2DBC. Driver có thể tạo connection trực tiếp thông qua connection factory. Chỉ cần chọn cách kết nối phù hợp với tải và mô hình vận hành.

Nếu ứng dụng dùng JDBC với HikariCP, không nên mặc định rằng HikariCP cũng quản lý connection R2DBC. HikariCP quản lý `DataSource` của JDBC; `r2dbc-pool` quản lý `ConnectionFactory` của R2DBC. Đây là hai API và hai loại connection khác nhau.

## 5. Điều kiện cần để sử dụng r2dbc-pool

Để pool hoạt động, ứng dụng cần đáp ứng các điều kiện sau:

1. Có R2DBC SPI và driver tương ứng với hệ quản trị cơ sở dữ liệu.
2. Thêm thư viện `io.r2dbc:r2dbc-pool` vào runtime classpath.
3. Tạo pool bọc connection factory của driver, hoặc bật cơ chế tự động cấu hình pool nếu framework hỗ trợ.
4. Cấu hình giới hạn pool và thời gian chờ phù hợp với database cùng số instance ứng dụng.
5. Các thành phần Spring dùng chung connection factory đã được bọc bởi pool.
6. Bảo đảm connection được trả lại pool sau khi thao tác hoàn tất.
7. Có cách theo dõi tình trạng pool, lỗi lấy connection và thời gian chờ.

`r2dbc-pool` không tự cung cấp driver database. Chỉ thêm pool mà thiếu driver tương ứng thì ứng dụng vẫn không biết cách kết nối tới hệ quản trị cụ thể.

Cũng không nên tạo một pool cho repository, một pool khác cho transaction manager và một pool khác cho `DatabaseClient` nếu các thao tác cần chia sẻ cùng transaction. Hãy dùng cùng connection factory đã được bọc pool cho các thành phần thuộc cùng cấu hình truy cập dữ liệu.

## 6. Khai báo dependency

`r2dbc-pool` là dependency riêng, có thể khai báo bằng Gradle hoặc Maven. Khi ứng dụng dùng Spring Boot, nên để BOM của Spring Boot quản lý phiên bản tương thích nếu BOM có quản lý artifact đó.

### 6.1. Gradle Groovy DSL

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
    runtimeOnly 'io.r2dbc:r2dbc-pool'
}
~~~

Trong ví dụ:

- Starter cung cấp tích hợp Spring Data R2DBC.
- Driver PostgreSQL tạo connection tới PostgreSQL.
- `r2dbc-pool` cung cấp lớp quản lý pool.

Nếu mã nguồn trực tiếp tham chiếu `ConnectionPool` hoặc `ConnectionPoolConfiguration`, khai báo `r2dbc-pool` ở `implementation` để các lớp đó có mặt trên compile classpath.

### 6.2. Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
    runtimeOnly("io.r2dbc:r2dbc-pool")
}
~~~

Không cần thêm version riêng nếu plugin hoặc BOM của dự án đã quản lý phiên bản dependency. Nếu dự án không dùng BOM, hãy chọn phiên bản `r2dbc-pool` tương thích với R2DBC SPI và driver đang dùng.

### 6.3. Maven

Khi dùng Spring Boot parent hoặc import BOM tương ứng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>io.r2dbc</groupId>
        <artifactId>r2dbc-pool</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Nếu mã Java trực tiếp sử dụng các lớp của `r2dbc-pool`, bỏ scope `runtime` hoặc dùng scope `compile` mặc định để mã nguồn có thể biên dịch.

### 6.4. Không ép version rời rạc khi có BOM

Pool, R2DBC SPI và driver cần tương thích. Khi dự án dùng Spring Boot BOM, nên ưu tiên phiên bản mà BOM quản lý. Chỉ ghi đè version khi có lý do cụ thể, đã kiểm tra tương thích và đã kiểm thử tích hợp.

Khi dependency resolution có vấn đề, xem cây dependency để biết phiên bản `r2dbc-spi`, `r2dbc-pool` và driver thực tế được chọn. Một version có thể được kéo vào theo quan hệ transitive từ một dependency khác.

## 7. Bật pool trong Spring Boot

Với Spring Boot hỗ trợ tự động cấu hình R2DBC pool, ứng dụng có thể thêm dependency `r2dbc-pool` và khai báo các thuộc tính dưới `spring.r2dbc.pool`.

Ví dụ PostgreSQL:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/appdb
    username: app_user
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 30m
      max-life-time: 2h
      max-acquire-time: 5s
      max-create-connection-time: 5s
~~~

Ý nghĩa các thuộc tính chính:

| Thuộc tính | Vai trò |
|---|---|
| `enabled` | Bật cấu hình pool nếu phiên bản Spring Boot đang dùng hỗ trợ thuộc tính này |
| `initial-size` | Số connection pool cố gắng khởi tạo ban đầu |
| `max-size` | Số connection tối đa mà pool quản lý |
| `max-idle-time` | Thời gian connection được phép ở trạng thái idle trước khi có thể bị loại bỏ |
| `max-life-time` | Tuổi thọ tối đa của connection trong pool |
| `max-acquire-time` | Thời gian tối đa một yêu cầu chờ mượn connection |
| `max-create-connection-time` | Thời gian tối đa dành cho việc tạo connection mới |

Tên và khả năng hỗ trợ thuộc tính phụ thuộc phiên bản Spring Boot. Hãy kiểm tra metadata cấu hình và tài liệu đúng với phiên bản dự án; không sao chép một property từ phiên bản mới sang phiên bản cũ mà chưa xác nhận.

Nếu `r2dbc-pool` không có trên runtime classpath hoặc pool chưa được bật theo cơ chế của phiên bản Boot đang dùng, ứng dụng có thể vẫn kết nối bằng driver connection factory không được pool bọc. Vì vậy, cần kiểm tra cấu hình thực tế và runtime dependency, không chỉ nhìn vào file YAML.

### 7.1. Dùng profile theo môi trường

Thông số pool có thể khác nhau giữa môi trường phát triển, kiểm thử và production. Có thể dùng profile hoặc biến môi trường để điều chỉnh giới hạn mà không thay đổi mã nguồn.

Ví dụ:

~~~yaml
spring:
  config:
    activate:
      on-profile: production
  r2dbc:
    pool:
      enabled: true
      initial-size: 5
      max-size: 30
      max-acquire-time: 5s
~~~

Các con số trên chỉ minh họa. `max-size` production phải được tính từ giới hạn connection database, số instance ứng dụng, số dịch vụ cùng dùng database và lượng connection cần dành cho công việc quản trị.

Không nên đặt thông tin xác thực trực tiếp trong file profile được commit vào repository. Dùng biến môi trường hoặc secret manager.

## 8. Cấu hình pool bằng Java khi không dùng tự động cấu hình

Trong ứng dụng Spring Framework không dùng Spring Boot, hoặc khi cần tự tạo pool với quy tắc riêng, có thể dùng API của `r2dbc-pool`.

Ví dụ khái quát:

~~~java
ConnectionFactory driverConnectionFactory =
        ConnectionFactories.get(connectionFactoryOptions);

ConnectionPoolConfiguration poolConfiguration =
        ConnectionPoolConfiguration.builder(driverConnectionFactory)
                .initialSize(5)
                .maxSize(20)
                .maxIdleTime(Duration.ofMinutes(30))
                .maxLifeTime(Duration.ofHours(2))
                .maxAcquireTime(Duration.ofSeconds(5))
                .build();

ConnectionPool connectionPool =
        new ConnectionPool(poolConfiguration);
~~~

`driverConnectionFactory` là connection factory do driver cung cấp. `ConnectionPoolConfiguration` mô tả giới hạn và vòng đời connection. `ConnectionPool` bọc factory ban đầu và trở thành connection factory mà ứng dụng sử dụng.

Các import và cách tạo `ConnectionFactoryOptions` phụ thuộc driver, nên ví dụ chỉ tập trung vào phần cấu hình pool. Khi đăng ký pool làm Spring bean, cần quản lý vòng đời của nó để pool được dispose khi ứng dụng dừng:

~~~java
@Bean(destroyMethod = "dispose")
ConnectionPool connectionPool(ConnectionFactory driverConnectionFactory) {
    ConnectionPoolConfiguration configuration =
            ConnectionPoolConfiguration.builder(driverConnectionFactory)
                    .initialSize(5)
                    .maxSize(20)
                    .maxIdleTime(Duration.ofMinutes(30))
                    .maxLifeTime(Duration.ofHours(2))
                    .maxAcquireTime(Duration.ofSeconds(5))
                    .build();

    return new ConnectionPool(configuration);
}
~~~

Trong ứng dụng Boot đã tự cấu hình pool, không tạo thêm bean pool thứ hai chỉ để lặp lại cấu hình. Tự tạo bean có thể làm ứng dụng có hai lớp pool hoặc khiến các thành phần sử dụng connection factory khác nhau. Chỉ dùng cấu hình thủ công khi đã chủ động thay thế hoặc kiểm soát cấu hình tự động.

Nếu dùng pool thủ công, transaction manager phải nhận đúng connection factory đã bọc pool. Các repository và `DatabaseClient` cũng phải dùng cùng factory đó để các thao tác trong một giao dịch có thể chia sẻ connection do transaction manager quản lý.

## 9. Chọn kích thước pool

`max-size` là một trong những thông số ảnh hưởng lớn nhất tới hành vi của ứng dụng. Không có một giá trị đúng cho mọi hệ thống.

### 9.1. Tính ngân sách connection toàn hệ thống

Giả sử một ứng dụng chạy 4 instance và mỗi instance có `max-size` là 20. Riêng ứng dụng đó có thể mở tối đa:

\[
4 \times 20 = 80 \text{ connections}
\]

Nếu database có giới hạn 150 connection, vẫn phải dành chỗ cho các dịch vụ khác, tác vụ migration, giám sát, quản trị và các kết nối ngoài ứng dụng.

Có thể dùng công thức lập ngân sách đơn giản:

\[
C_{\text{app}} = N_{\text{instances}} \times P_{\text{max}}
\]

Trong đó:

- \(N_{\text{instances}}\) là số instance ứng dụng có thể chạy đồng thời, kể cả khi autoscaling.
- \(P_{\text{max}}\) là `max-size` trên mỗi instance.
- \(C_{\text{app}}\) là số connection tối đa ứng dụng có thể chiếm.

Tổng ngân sách phải thỏa:

\[
C_{\text{app}} + C_{\text{other}} + C_{\text{reserve}}
\leq C_{\text{database}}
\]

`C_other` là connection từ các dịch vụ và công việc khác; `C_reserve` là phần dự phòng cho quản trị và biến động tải; `C_database` là giới hạn connection có thể sử dụng an toàn.

### 9.2. Cân bằng giữa chờ đợi và tải database

Pool quá nhỏ có thể khiến request phải xếp hàng chờ connection dù database còn khả năng xử lý. Pool quá lớn có thể làm database chịu quá nhiều truy vấn đồng thời, tăng lock contention, chuyển context và thời gian phản hồi.

Hãy bắt đầu với một giới hạn thận trọng, sau đó đo:

- Số connection đang được mượn.
- Số connection đang idle.
- Thời gian chờ acquire.
- Tỷ lệ acquire timeout.
- Thời gian truy vấn và transaction.
- Mức sử dụng CPU, bộ nhớ và giới hạn connection của database.

Tăng pool size không giải quyết được truy vấn chậm, transaction giữ connection quá lâu hoặc database đã bão hòa. Trong các trường hợp đó, cần tối ưu SQL, index, transaction boundary hoặc giảm lượng công việc đồng thời.

### 9.3. Phân biệt concurrency của request và concurrency của database

Một server có thể nhận hàng trăm request đồng thời nhưng không phải request nào cũng giữ connection database cùng lúc. Một số request có thể đang xác thực, xử lý cache, gọi dịch vụ khác hoặc chờ dữ liệu.

Ngược lại, một request có thể thực hiện nhiều truy vấn nối tiếp và giữ connection trong toàn bộ transaction. Vì vậy, không nên lấy số thread hoặc số request tối đa làm `max-size` một cách máy móc.

Cần đo số thao tác database thực sự chồng lấn và thời gian giữ connection. Với reactive application, số thread nhỏ không đồng nghĩa số connection cần dùng cũng nhỏ.

## 10. Thời gian chờ, idle và tuổi thọ connection

### 10.1. Acquire timeout

`max-acquire-time` giới hạn thời gian một yêu cầu chờ mượn connection. Nếu pool đã hết connection và không có connection được trả lại trong khoảng thời gian đó, thao tác có thể thất bại.

Timeout quá ngắn khiến request thất bại khi tải tăng đột biến trong thời gian ngắn. Timeout quá dài làm request nằm chờ, chiếm tài nguyên upstream và có thể tạo hàng đợi lớn. Hãy liên kết acquire timeout với timeout tổng thể của request và mục tiêu thời gian phản hồi.

Acquire timeout cũng là tín hiệu vận hành. Nếu tăng đột biến, hãy kiểm tra pool saturation, truy vấn chậm, connection leak, database quá tải và transaction kéo dài.

### 10.2. Idle timeout

`max-idle-time` giới hạn thời gian connection không được sử dụng. Pool có thể loại bỏ connection idle quá lâu để giảm tài nguyên giữ ở database.

Giá trị cần cân nhắc cùng chính sách idle timeout của database, firewall, proxy và load balancer. Nếu hạ tầng đóng connection sau một khoảng thời gian ngắn hơn pool dự kiến, pool có thể giữ connection đã chết và gặp lỗi khi mượn lại.

### 10.3. Maximum lifetime

`max-life-time` giới hạn tuổi thọ của connection. Việc thay connection định kỳ có thể tránh giữ một session quá lâu khi hạ tầng có giới hạn tuổi thọ hoặc thay đổi endpoint.

Không đặt lifetime quá ngắn vì pool sẽ liên tục đóng và tạo connection mới. Không đặt quá dài nếu database hoặc proxy có chính sách buộc đóng connection theo tuổi thọ.

### 10.4. Thời gian tạo connection

`max-create-connection-time` giới hạn thời gian tạo connection mới. Nếu database không phản hồi, DNS lỗi hoặc mạng chậm, yêu cầu tạo connection không nên chờ vô hạn.

Timeout tạo connection khác acquire timeout: acquire timeout giới hạn tổng thời gian chờ lấy connection; create timeout giới hạn riêng quá trình mở connection mới. Cần đọc tài liệu phiên bản đang dùng để hiểu cách hai giới hạn được áp dụng trong pool.

## 11. Validation và connection không còn hợp lệ

Một connection có thể đã bị database hoặc hạ tầng đóng khi đang idle. Pool cần biết connection nào còn dùng được trước khi cấp lại.

Tùy phiên bản `r2dbc-pool` và driver, có thể cấu hình validation depth hoặc validation query. Validation có thể kiểm tra connection ở mức giao thức hoặc chạy một câu truy vấn xác nhận. Tên thuộc tính và mức hỗ trợ phụ thuộc API, driver và Spring Boot version.

Nếu dùng validation query, hãy chọn câu lệnh nhẹ, hợp lệ với database và không làm thay đổi dữ liệu. Ví dụ `SELECT 1` thường dùng được trên nhiều hệ quản trị, nhưng cần xác nhận với driver và database cụ thể.

Validation quá thường xuyên có thể làm tăng số truy vấn phụ và độ trễ acquire. Không nên bật một cơ chế kiểm tra nặng cho mọi lần mượn connection nếu driver và hạ tầng đã cung cấp cơ chế phù hợp hơn.

Pool không thể bảo đảm mọi connection đều sống trong mọi thời điểm. Mạng có thể đứt ngay sau khi validation thành công. Ứng dụng vẫn cần xử lý lỗi kết nối và retry có giới hạn đối với thao tác an toàn để thử lại.

## 12. Pool và giao dịch reactive trong Spring Data R2DBC

Spring sử dụng `ConnectionFactory` để lấy connection cho repository, `DatabaseClient` và transaction manager. Khi có pool, connection factory mà các thành phần này dùng là factory đã được pool bọc.

Trong một giao dịch reactive, transaction manager lấy connection và gắn tài nguyên vào Reactor Context. Các thao tác trong cùng giao dịch sử dụng connection được quản lý đó. Khi giao dịch kết thúc, connection được đóng theo API R2DBC và pool thu hồi lease để tái sử dụng.

Điều này dẫn tới một số nguyên tắc:

- Dùng cùng một connection factory đã bọc pool cho repository, `DatabaseClient` và `R2dbcTransactionManager` thuộc cùng cấu hình.
- Không tự tạo subscription độc lập bằng `subscribe()` để chạy truy vấn cần tham gia giao dịch.
- Không giữ connection trong field của service hoặc chia sẻ connection giữa các request.
- Không tự đóng connection khi transaction manager vẫn đang sử dụng nó.
- Không chạy song song các thao tác trên cùng connection nếu driver không hỗ trợ.
- Giữ transaction ngắn để connection sớm được trả về pool.

Pool chỉ quản lý tài nguyên kết nối. Nó không tự làm cho hai câu lệnh trở thành một transaction, không thay thế `@Transactional` hoặc `TransactionalOperator`, và không giải quyết lost update hay isolation anomaly.

## 13. Connection leak và cách phòng tránh

Connection leak xảy ra khi ứng dụng mượn connection nhưng không trả lại pool. Sau một thời gian, số connection đang được mượn tăng lên dù các thao tác đã kết thúc hoặc không còn tiến triển. Pool có thể hết connection và các request mới bắt đầu timeout.

Các nguyên nhân thường gặp:

- Tự gọi `ConnectionFactory.create()` nhưng quên đóng connection.
- Có nhánh xử lý lỗi hoặc hủy subscription không giải phóng connection đúng cách.
- Giữ transaction mở quá lâu.
- Gọi dịch vụ bên ngoài trong lúc đang giữ connection hoặc lock.
- Tạo publisher nhưng không tiêu thụ hoặc không kết thúc.
- Lưu connection để dùng lại giữa nhiều request.

Khi dùng trực tiếp R2DBC SPI, hãy bảo đảm đóng connection trong mọi trường hợp. Với reactive resource, dùng các abstraction hỗ trợ quản lý vòng đời hoặc toán tử `usingWhen` khi cần tự quản lý tài nguyên bất đồng bộ. Không nên viết một chuỗi thủ công chỉ đóng connection ở nhánh thành công.

Với Spring Data R2DBC, ưu tiên dùng repository, `DatabaseClient`, `R2dbcEntityTemplate` và transaction manager để Spring quản lý việc mượn/trả connection.

## 14. Pool không thay thế backpressure hoặc giới hạn request

Pool giới hạn số connection được cấp đồng thời, nhưng request chờ mượn connection vẫn có thể tích tụ. Nếu hệ thống nhận request nhanh hơn tốc độ database xử lý, hàng đợi acquire có thể tăng và thời gian phản hồi kéo dài.

Hãy phối hợp:

- Giới hạn số request đồng thời ở tầng API hoặc service.
- Dùng backpressure trong reactive pipeline khi nguồn dữ liệu hỗ trợ.
- Đặt timeout cho acquire và request.
- Hủy công việc không còn cần thiết để giải phóng tài nguyên.
- Giảm truy vấn chậm và thời gian giữ transaction.
- Dùng bulkhead hoặc giới hạn concurrency cho các tác vụ truy cập database có tải cao.

Pool là một giới hạn tài nguyên ở tầng connection, không phải giới hạn tổng số request của ứng dụng.

## 15. Theo dõi và chẩn đoán pool

Khi bật pool trong production, cần quan sát ít nhất:

| Chỉ số | Ý nghĩa |
|---|---|
| Acquired / allocated connections | Số connection đang được sử dụng và tổng số connection được pool quản lý |
| Idle connections | Số connection sẵn sàng được mượn |
| Pending acquire | Số yêu cầu đang chờ connection |
| Acquire latency | Thời gian chờ lấy connection |
| Acquire timeout | Số yêu cầu không lấy được connection trong thời hạn |
| Connection creation | Tốc độ và lỗi khi tạo connection mới |
| Connection lifetime | Tuổi thọ và thời gian idle của connection |
| Query/transaction duration | Thời gian connection bị giữ trong quá trình xử lý |

Nếu pending acquire và acquire latency tăng nhưng database còn dư tài nguyên, có thể pool quá nhỏ hoặc connection bị giữ quá lâu. Nếu pool thường xuyên đạt max-size đồng thời database đã bão hòa, tăng pool có thể làm tình hình xấu hơn; cần tối ưu truy vấn và giảm concurrency.

Nếu acquired connections luôn cao dù lượng request thấp, hãy điều tra connection leak, publisher không kết thúc hoặc transaction chưa được đóng. Nếu connection creation liên tục tăng, kiểm tra lifetime/idle policy, lỗi mạng, database đóng session và cấu hình validation.

Có thể tích hợp metrics của pool với hệ thống giám sát nếu phiên bản thư viện và cấu hình metrics hỗ trợ. Tên metric cụ thể phụ thuộc phiên bản và registry được sử dụng; hãy kiểm tra metric thực tế thay vì giả định một tên cố định.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ thêm `r2dbc-pool` mà thiếu driver | Pool không thể tạo connection tới database | Thêm driver R2DBC tương ứng |
| Nghĩ rằng pool là bắt buộc cho mọi ứng dụng | Thêm cấu hình và chi phí vận hành không cần thiết | Chỉ dùng khi có nhu cầu tái sử dụng và giới hạn connection |
| Dùng HikariCP để pool R2DBC | HikariCP quản lý JDBC `DataSource`, không phải R2DBC `ConnectionFactory` | Dùng `r2dbc-pool` cho R2DBC |
| Không bật pool trong cấu hình Boot | Ứng dụng có thể tiếp tục dùng driver factory trực tiếp | Kiểm tra dependency, property và cấu hình tự động của phiên bản Boot |
| Đặt `max-size` quá lớn | Database cạn connection hoặc chịu quá nhiều truy vấn đồng thời | Tính ngân sách trên tất cả instance và dịch vụ |
| Đặt `max-size` quá nhỏ | Request xếp hàng và acquire timeout | Đo concurrency database và điều chỉnh có kiểm soát |
| Acquire timeout quá dài | Request chờ lâu, hàng đợi tích tụ | Đồng bộ timeout với SLA request và xử lý saturation |
| Connection không được đóng | Pool hết connection do leak | Quản lý vòng đời bằng Spring hoặc API resource phù hợp |
| Tạo nhiều pool cho cùng database không có chủ đích | Tổng connection vượt ngân sách và transaction không dùng chung factory | Dùng một factory/pool có chủ đích cho mỗi cấu hình truy cập |
| Giữ transaction trong lúc gọi HTTP | Connection và lock bị giữ lâu | Đưa công việc ngoài database ra ngoài transaction |
| Nghĩ pool giải quyết concurrency anomaly | Dữ liệu vẫn có thể bị lost update hoặc vi phạm quy tắc | Dùng transaction, isolation, atomic SQL, version hoặc lock |
| Bỏ qua metrics | Chậm và timeout khó xác định nguyên nhân | Theo dõi pending acquire, latency, size và lỗi |

## 17. Quy trình quyết định và triển khai

Khi cân nhắc thêm `r2dbc-pool`, có thể làm theo trình tự:

1. Đo tần suất tạo connection, số connection đồng thời, độ trễ kết nối và tải database.
2. Xác định giới hạn connection của database và tổng số instance ứng dụng có thể chạy.
3. Tính ngân sách connection dành cho ứng dụng, các dịch vụ khác và phần dự phòng.
4. Nếu tái sử dụng connection có lợi, thêm `io.r2dbc:r2dbc-pool` cùng driver R2DBC tương ứng.
5. Bật pool bằng cơ chế phù hợp với Spring Boot hoặc cấu hình `ConnectionPool` thủ công.
6. Đặt `max-size`, initial size, acquire timeout, idle timeout và lifetime theo tải cùng chính sách hạ tầng.
7. Bảo đảm repository, `DatabaseClient` và transaction manager dùng cùng connection factory đã bọc pool.
8. Chạy kiểm thử tải và lỗi kết nối, quan sát pending acquire, latency, connection creation và timeout.
9. Điều chỉnh thông số dựa trên số liệu production; không tăng pool chỉ để che truy vấn chậm hoặc transaction kéo dài.

## 18. Ghi nhớ

- `r2dbc-pool` là thư viện tùy chọn để tái sử dụng và giới hạn connection R2DBC.
- Pool bọc một connection factory do driver cung cấp; nó không thay thế driver hoặc Spring Data R2DBC.
- Pool phù hợp với ứng dụng có nhiều thao tác database lặp lại, kết nối vật lý tốn chi phí hoặc cần giới hạn session đồng thời.
- Ứng dụng nhỏ, tác vụ ngắn hoặc môi trường đã có cơ chế quản lý kết nối khác có thể chưa cần pool.
- Thêm dependency `io.r2dbc:r2dbc-pool` và bật cấu hình pool theo phiên bản framework đang dùng.
- `max-size` phải được tính trên tổng số instance và các dịch vụ cùng sử dụng database.
- Acquire timeout, idle timeout và maximum lifetime cần phù hợp với SLA và chính sách của database/hạ tầng.
- Spring transaction manager và repository phải dùng cùng connection factory đã được bọc pool.
- Connection phải được trả về pool sau khi dùng; transaction dài và connection leak làm pool cạn.
- Pool giới hạn tài nguyên kết nối, không thay thế backpressure, transaction, isolation hoặc cơ chế bảo vệ dữ liệu đồng thời.

