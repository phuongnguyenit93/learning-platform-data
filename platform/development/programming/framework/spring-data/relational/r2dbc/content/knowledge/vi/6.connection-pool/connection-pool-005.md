# Xác thực kết nối và xử lý kết nối hỏng

Connection pool trong Spring Data R2DBC tái sử dụng các kết nối đến database để giảm chi phí mở kết nối mới cho mỗi thao tác. Việc tái sử dụng chỉ an toàn khi pool có thể quản lý vòng đời kết nối và phát hiện những kết nối không còn sử dụng được. Trong thực tế, database có thể restart, network có thể ngắt, firewall có thể đóng kết nối nhàn rỗi, hoặc một kết nối có thể hết thời gian sống theo chính sách vận hành. Vì vậy, ứng dụng cần hiểu cách xác thực kết nối, loại bỏ kết nối hỏng, xử lý lỗi khi đang truy vấn và thử lại một cách có kiểm soát.

Xác thực kết nối là một phần của chiến lược quản lý pool, không phải bảo đảm rằng mọi truy vấn tiếp theo chắc chắn thành công. Kết nối có thể hợp lệ tại thời điểm kiểm tra nhưng bị ngắt ngay sau đó. Thiết kế đúng cần phối hợp validation, eviction, timeout, xử lý lỗi reactive và retry phù hợp với tính chất của nghiệp vụ.

## 1. Vì sao cần xác thực kết nối?

Một connection được tạo thành công không có nghĩa nó sẽ luôn còn sử dụng được. Sau khi được trả về pool, connection có thể nằm nhàn rỗi trong một khoảng thời gian. Trong thời gian đó, một thành phần bên ngoài có thể đóng nó mà pool không nhận được tín hiệu ngay lập tức.

Các nguyên nhân phổ biến làm connection trở nên stale hoặc hỏng:

- Database restart, failover hoặc chuyển primary/replica.
- Database đóng session do idle timeout, giới hạn tài nguyên hoặc chính sách quản trị.
- Firewall, NAT, proxy hoặc load balancer xóa TCP connection nhàn rỗi.
- Mất mạng tạm thời, thay đổi route, DNS hoặc lỗi TLS.
- Database chủ động ngắt session vì vượt giới hạn thời gian hoặc tài nguyên.
- Driver phát hiện lỗi giao thức, lỗi I/O hoặc trạng thái connection không còn hợp lệ.
- Connection tồn tại quá lâu và vượt quá tuổi thọ mà hạ tầng cho phép.

Nếu pool cấp lại một connection stale, câu lệnh tiếp theo có thể thất bại với lỗi như connection closed, connection reset, I/O error hoặc lỗi giao thức. Một số lỗi chỉ xuất hiện khi ứng dụng gửi câu lệnh hoặc đọc kết quả, nên việc kiểm tra trước khi cấp connection chỉ giảm xác suất lỗi chứ không thể loại bỏ hoàn toàn.

Xác thực trước khi sử dụng giúp pool phát hiện một số connection không còn hoạt động. Eviction giúp loại bỏ connection quá cũ hoặc nhàn rỗi quá lâu. Khi lỗi xảy ra trong lúc thực thi, ứng dụng phải để lỗi được truyền đúng cách và để pool/driver xử lý vòng đời connection theo khả năng hỗ trợ.

## 2. Các thời điểm và cách thức xác thực

Validation có thể được thực hiện ở những thời điểm khác nhau tùy pool và driver:

| Cách thức | Thời điểm | Mục đích | Chi phí |
|---|---|---|---|
| Validate khi acquire (mượn connection) | Trước khi giao connection cho ứng dụng | Phát hiện connection stale trước khi dùng | Có thể tăng độ trễ mỗi lần lấy connection |
| Validate khi release hoặc trước khi đưa lại pool | Sau khi ứng dụng trả connection | Kiểm tra trạng thái trước khi tái sử dụng | Tăng công việc lúc trả connection |
| Background eviction | Định kỳ khi connection nằm trong pool | Loại bỏ connection hết tuổi thọ hoặc nhàn rỗi quá lâu | Tạo công việc nền và có thể phát sinh kiểm tra định kỳ |
| Kiểm tra cục bộ (local validation) | Khi pool/driver kiểm tra trạng thái đối tượng | Phát hiện connection đã đóng hoặc trạng thái cục bộ không hợp lệ | Thường thấp, nhưng không xác nhận server còn phản hồi |
| Kiểm tra từ xa (remote validation) | Khi cần xác nhận database có thể phản hồi | Phát hiện một số lỗi mạng hoặc server | Có thể cần round trip đến database |

Không phải pool nào cũng triển khai mọi thời điểm kiểm tra hoặc có cùng chính sách mặc định. Hãy đọc tài liệu của đúng phiên bản R2DBC Pool và driver đang sử dụng. Cấu hình validation cần cân bằng giữa độ tin cậy, độ trễ và tải database.

### 2.1. Local validation và remote validation

R2DBC SPI định nghĩa `ValidationDepth` để biểu thị độ sâu kiểm tra connection:

- `ValidationDepth.LOCAL`: kiểm tra tính hợp lệ ở phía client/driver, chẳng hạn trạng thái connection đã bị đóng hay chưa. Cách kiểm tra này không nhất thiết gửi yêu cầu đến database.
- `ValidationDepth.REMOTE`: kiểm tra sâu hơn để xác nhận connection vẫn có thể giao tiếp với phía server theo khả năng của driver. Việc này có thể cần một thao tác I/O hoặc round trip.

Một cách gọi ở mức SPI có dạng:

```java
connection.validate(ValidationDepth.REMOTE);
```

`validate(...)` trả về một `Publisher<Boolean>`, không phải một boolean đồng bộ. Cần subscribe và xử lý kết quả trong pipeline reactive. Driver quyết định cách thực hiện kiểm tra và có thể có giới hạn riêng. `REMOTE` giúp phát hiện nhiều trường hợp connection không còn giao tiếp được, nhưng không thể bảo đảm connection sẽ còn tốt ở lần query kế tiếp.

### 2.2. Validation query

Một số pool cho phép cấu hình câu SQL nhỏ để kiểm tra connection. Với PostgreSQL, MySQL và nhiều hệ quản trị khác, câu lệnh đơn giản như sau thường được dùng:

```sql
SELECT 1
```

Validation query tạo một thao tác thực tế đến database. Nếu câu lệnh không chạy thành công trong thời gian cho phép, pool có thể xem connection là không hợp lệ và loại bỏ nó theo chính sách của pool.

Validation query cần:

- Nhẹ, chạy nhanh và không đọc lượng dữ liệu lớn.
- Không thay đổi dữ liệu hoặc gây side effect.
- Không phụ thuộc bảng nghiệp vụ có thể bị đổi tên hoặc xóa.
- Được database/dialect và driver đang dùng hỗ trợ.
- Có timeout phù hợp để một lần validation không giữ connection quá lâu.

`SELECT 1` là ví dụ phổ biến, không phải cú pháp bắt buộc của mọi database. Hãy kiểm tra cú pháp được hệ quản trị mục tiêu hỗ trợ.

### 2.3. Không kiểm tra quá mức

Thực hiện một remote validation query trước mọi câu SQL có thể tăng số round trip và làm giảm throughput, đặc biệt khi mỗi request vốn đã chạy một truy vấn ngắn. Ngược lại, không kiểm tra connection nhàn rỗi trong một môi trường thường xuyên cắt kết nối có thể làm nhiều request đầu tiên sau thời gian nghỉ gặp lỗi.

Chính sách nên dựa trên đặc điểm hạ tầng:

- Nếu firewall đóng TCP connection sau một khoảng idle cố định, đặt `maxIdleTime` thấp hơn ngưỡng đó và cân nhắc validation khi acquire.
- Nếu database có giới hạn tuổi thọ session, đặt `maxLifeTime` thấp hơn giới hạn vận hành.
- Nếu network ổn định và round trip đắt, có thể dựa nhiều hơn vào idle/lifetime eviction và chỉ remote validate ở những điểm phù hợp.
- Nếu workload nhạy với lỗi connection đầu tiên sau thời gian nhàn rỗi, tăng độ tin cậy của validation khi acquire.

## 3. Cấu hình validation trong R2DBC Pool

R2DBC Pool cung cấp các tùy chọn để giới hạn tuổi thọ connection và xác thực connection trước khi tái sử dụng. Trong Spring Boot, cấu hình thường được đặt dưới `spring.r2dbc.pool` khi pool được bật và dependency phù hợp có mặt.

Ví dụ `application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: app
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 20m
      max-life-time: 2h
      max-acquire-time: 5s
      validation-query: SELECT 1
```

Ý nghĩa của các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `enabled` | Bật hoặc tắt R2DBC connection pool nếu phiên bản Spring Boot và dependency hỗ trợ |
| `initial-size` | Số connection ban đầu pool cố gắng tạo |
| `max-size` | Số connection tối đa pool có thể cấp |
| `max-idle-time` | Thời gian tối đa connection được giữ nhàn rỗi trước khi đủ điều kiện bị loại bỏ theo chính sách pool |
| `max-life-time` | Tuổi thọ tối đa của connection kể từ khi được tạo |
| `max-acquire-time` | Thời gian tối đa một yêu cầu chờ lấy connection từ pool |
| `validation-query` | Câu SQL dùng để kiểm tra connection nếu pool/driver được cấu hình hỗ trợ |

Tên thuộc tính, kiểu giá trị và khả năng hỗ trợ phụ thuộc phiên bản Spring Boot và R2DBC Pool. Hãy kiểm tra metadata cấu hình và tài liệu của phiên bản đang chạy. Không phải mọi tùy chọn trong builder cấp thấp đều có thuộc tính tương ứng trong mọi phiên bản Spring Boot.

### 3.1. Cấu hình bằng R2DBC Pool API

Khi tự tạo pool, có thể cấu hình trực tiếp bằng `ConnectionPoolConfiguration`:

```java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(5)
        .maxSize(20)
        .maxIdleTime(Duration.ofMinutes(20))
        .maxLifeTime(Duration.ofHours(2))
        .maxAcquireTime(Duration.ofSeconds(5))
        .validationQuery("SELECT 1")
        .build();

ConnectionPool pool = new ConnectionPool(configuration);
```

Ví dụ này minh họa các thuộc tính thường gặp trong R2DBC Pool. Các phương thức builder cụ thể có thể khác theo phiên bản. Nếu ứng dụng đã để Spring Boot auto-configure pool, không nên tạo thêm một pool thủ công cho cùng `ConnectionFactory` mà chưa xác định rõ bean nào được `DatabaseClient` sử dụng.

### 3.2. Chọn maxIdleTime và maxLifeTime

`maxIdleTime` và `maxLifeTime` giải quyết hai vấn đề khác nhau:

- `maxIdleTime` hạn chế thời gian một connection không được sử dụng. Nó hữu ích khi firewall, NAT hoặc database có idle timeout.
- `maxLifeTime` hạn chế tuổi thọ tổng thể của connection, kể cả khi connection vẫn thường xuyên được sử dụng. Nó hữu ích khi hạ tầng yêu cầu thay connection định kỳ.

Ví dụ, nếu network đóng connection sau 30 phút không hoạt động, đặt `maxIdleTime` nhỏ hơn 30 phút có thể giúp pool loại bỏ connection trước khi network làm điều đó. Nếu database buộc session phải được thay sau một khoảng thời gian, `maxLifeTime` cần thấp hơn giới hạn đó với biên an toàn.

Các con số trong cấu hình chỉ là ví dụ. Cần tính đến thời gian idle timeout thực tế, độ trễ network, số connection tối đa và chi phí tạo connection mới. Đặt lifetime quá ngắn khiến pool liên tục tạo và hủy connection; đặt quá dài khiến stale connection có cơ hội tồn tại lâu hơn.

## 4. Phân biệt các loại timeout

Một hệ thống có thể có nhiều timeout cùng lúc. Không nên xem chúng là một thuộc tính duy nhất:

| Timeout | Giới hạn điều gì? | Khi hết thời gian |
|---|---|---|
| Acquire timeout | Thời gian chờ một connection rảnh trong pool | Yêu cầu lấy connection thất bại |
| Create connection timeout | Thời gian tạo kết nối mới đến database | Thao tác tạo connection thất bại |
| Validation timeout | Thời gian kiểm tra connection | Validation thất bại hoặc connection bị xem là không hợp lệ theo pool |
| Query/statement timeout | Thời gian thực thi câu lệnh SQL | Câu lệnh bị timeout theo driver/database |
| Transaction timeout | Thời gian cho phép transaction tồn tại | Transaction bị hủy hoặc rollback theo cơ chế quản lý |
| Network/socket timeout | Thời gian chờ I/O ở tầng mạng | Driver nhận lỗi I/O hoặc timeout |

Ví dụ, `maxAcquireTime: 5s` không có nghĩa câu SQL chỉ được chạy tối đa 5 giây. Nó chỉ giới hạn thời gian chờ connection từ pool. Nếu connection đã được cấp và câu lệnh chạy 60 giây, query timeout hoặc timeout phía database mới là cơ chế kiểm soát thời gian thực thi.

Nên đặt các timeout theo quan hệ hợp lý. Validation không nên giữ connection quá lâu; acquire timeout phải phù hợp với SLA của request; query timeout nên phù hợp với loại truy vấn; transaction timeout phải tính cả thời gian thực hiện nghiệp vụ trong transaction.

## 5. Eviction và vòng đời connection

Eviction là quá trình loại bỏ connection khỏi pool. Một connection có thể bị loại bỏ vì:

- Đã vượt `maxIdleTime`.
- Đã vượt `maxLifeTime`.
- Validation thất bại.
- Driver báo connection đã đóng hoặc không còn hợp lệ.
- Pool phát hiện lỗi khi sử dụng hoặc khi release theo chính sách hỗ trợ.
- Quản trị viên hoặc ứng dụng chủ động đóng pool.

Eviction giúp pool thay dần những connection cũ bằng connection mới. Nó đặc biệt hữu ích trong môi trường có database failover, proxy, load balancer hoặc chính sách đóng session định kỳ.

Một số pool hỗ trợ background eviction, tức là quét các connection nhàn rỗi theo chu kỳ. Một số pool chỉ kiểm tra khi acquire hoặc release. Không nên giả định rằng connection hết `maxIdleTime` sẽ bị đóng đúng tại mili giây đó; thời điểm thực tế còn phụ thuộc lịch chạy eviction và trạng thái pool.

Pool cần được đóng khi ứng dụng shutdown để giải phóng connection và tài nguyên nền. Trong ứng dụng Spring, bean lifecycle thường quản lý việc đóng bean pool nếu pool được khai báo đúng cách. Nếu tự tạo pool ngoài container, cần đảm bảo có bước dispose/close khi ứng dụng dừng.

## 6. Connection bị hỏng trong khi đang sử dụng

Validation trước khi acquire không thể ngăn mọi lỗi. Một connection có thể bị mất ngay sau khi kiểm tra hoặc đang giữa câu lệnh. Ví dụ:

1. Pool xác thực connection và thấy connection còn hoạt động.
2. Ứng dụng nhận connection.
3. Network bị reset hoặc database restart.
4. Ứng dụng gửi SQL hoặc đọc kết quả.
5. Driver phát lỗi I/O, connection closed hoặc lỗi giao thức.

Đây là tình huống bình thường cần được xử lý trong hệ thống phân tán. Ứng dụng phải để lỗi được truyền tới tầng có thể quyết định trả lỗi cho client, thử lại hoặc đưa công việc vào hàng đợi.

### 6.1. Không tái sử dụng connection đã biết là hỏng

Khi driver hoặc pool xác định connection không hợp lệ, connection đó cần được loại khỏi vòng tái sử dụng. Pool có thể tự đánh dấu và dispose connection trong một số trường hợp. Chi tiết phụ thuộc pool và driver.

Với connection lấy thủ công từ `ConnectionFactory`, luôn quản lý vòng đời bằng reactive cleanup. Ví dụ dùng `Mono.usingWhen`:

```java
Mono<Integer> readHealth(ConnectionFactory connectionFactory) {
    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> Mono.from(connection.validate(ValidationDepth.REMOTE))
            .map(valid -> valid ? 1 : 0),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
```

Ví dụ minh họa cách bảo đảm cleanup khi publisher hoàn tất, phát lỗi hoặc bị hủy. `Connection.close()` trên connection lấy từ pool thường trả connection về pool; nó không nhất thiết đóng socket vật lý. Nếu connection đã được xác định là hỏng và cần discard, hãy dùng cơ chế invalidation/disposal được tài liệu của pool cụ thể hỗ trợ. R2DBC SPI chung không cung cấp một API discard phổ quát cho mọi pool.

Không giữ `Connection` trong field singleton hoặc cache để dùng lại qua nhiều request. Hãy acquire trong phạm vi thao tác, thực thi và release đúng vòng đời. Với `DatabaseClient`, Spring quản lý việc acquire/release connection cho thao tác thông thường; ứng dụng không cần tự đóng connection nội bộ của client.

### 6.2. Để lỗi đi qua reactive pipeline

Không nên biến lỗi kết nối thành kết quả thành công giả:

```java
// Không nên: che giấu lỗi và khiến tầng gọi tưởng rằng truy vấn thành công.
return repository.findById(id)
    .onErrorResume(error -> Mono.empty());
```

Nếu nghiệp vụ cần chuyển lỗi kỹ thuật thành lỗi ứng dụng, hãy giữ nguyên nguyên nhân:

```java
return repository.findById(id)
    .onErrorMap(R2dbcException.class, error ->
        new CustomerStoreUnavailableException(
            "Không thể truy cập dữ liệu khách hàng", error));
```

Tầng web có thể ánh xạ lỗi này thành HTTP status phù hợp, còn tầng xử lý nền có thể ghi nhận và lên lịch xử lý lại theo chính sách. Không nên trả dữ liệu rỗng nếu thực tế là database không truy cập được, trừ khi hợp đồng nghiệp vụ định nghĩa rõ hành vi fallback đó.

## 7. Retry khi connection gặp lỗi

Retry có thể hữu ích khi lỗi mang tính tạm thời, nhưng không phải lỗi database nào cũng nên thử lại. Một số lỗi là lỗi cấu hình hoặc dữ liệu vĩnh viễn, ví dụ sai SQL, vi phạm constraint, thiếu quyền hoặc dữ liệu đầu vào không hợp lệ. Thử lại các lỗi này chỉ làm tăng tải và kéo dài thời gian phản hồi.

Các trường hợp có thể cân nhắc retry:

- Network reset ngắn hạn hoặc lỗi kết nối tạm thời.
- Database failover đã hoàn tất và node mới có thể nhận kết nối.
- Connection bị đóng ngoài dự kiến nhưng thao tác có thể được thực hiện lại an toàn.
- Một số lỗi quá tải tạm thời, nếu có chính sách backoff và giới hạn tải phù hợp.

Các trường hợp cần thận trọng:

- Query timeout khi server có thể vẫn đang xử lý.
- Mất kết nối trong lúc commit transaction.
- INSERT/UPDATE có side effect và client không biết thao tác đã commit hay chưa.
- Lỗi constraint, cú pháp hoặc quyền truy cập.

### 7.1. Retry có giới hạn và backoff

Với thao tác đọc idempotent, có thể dùng Reactor Retry để thử lại một số lần với backoff:

```java
Mono<Customer> findCustomer(Long id) {
    return Mono.defer(() -> customerRepository.findById(id))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.5)
            .filter(this::isTransientConnectionFailure));
}
```

Trong ví dụ:

- `Mono.defer` tạo thao tác đọc mới ở mỗi lần subscribe lại.
- `Retry.backoff(2, ...)` cho phép tối đa hai lần retry sau lần thử đầu tiên.
- `maxBackoff` giới hạn thời gian chờ tăng dần.
- `jitter` thêm độ ngẫu nhiên để nhiều client không đồng loạt retry cùng lúc.
- `filter` chỉ cho retry các lỗi được phân loại là tạm thời.

`isTransientConnectionFailure` là hàm nghiệp vụ cần được triển khai dựa trên loại exception, mã SQL state, driver và database cụ thể. Không nên dùng `retry()` không giới hạn cho mọi lỗi.

### 7.2. Retry và transaction

Nếu một thao tác chạy trong transaction, vị trí đặt retry rất quan trọng. Sau một lỗi connection hoặc SQL, transaction hiện tại có thể đã rollback hoặc không còn sử dụng được. Retry bên trong cùng transaction có thể tiếp tục dùng context/connection đã hỏng.

Với thao tác có thể retry an toàn, thường nên đặt retry bên ngoài ranh giới transaction để mỗi lần thử tạo transaction mới:

```java
Mono<Order> createOrder(Command command) {
    return Mono.defer(() ->
            transactionalOperator.transactional(createOrderOnce(command)))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .filter(this::isTransientConnectionFailure));
}
```

Đoạn mã chỉ phù hợp nếu `createOrderOnce` có cơ chế bảo đảm idempotency. Nếu lần trước đã commit nhưng client mất phản hồi, lần retry có thể tạo đơn hàng thứ hai. Hãy dùng idempotency key, unique constraint, upsert phù hợp hoặc cơ chế deduplication để bảo đảm cùng một yêu cầu không tạo side effect lặp.

### 7.3. Kết quả commit không rõ ràng

Một tình huống nguy hiểm là connection bị ngắt trong lúc commit. Ứng dụng có thể không biết database đã commit transaction hay chưa. Nếu tự động gửi lại lệnh tạo dữ liệu, nghiệp vụ có thể bị thực hiện hai lần.

Giải pháp thường dùng:

- Tạo idempotency key duy nhất cho mỗi yêu cầu nghiệp vụ.
- Lưu key cùng kết quả xử lý trong transaction.
- Đặt unique constraint để database ngăn xử lý trùng.
- Khi retry, kiểm tra kết quả đã tồn tại theo key trước khi tạo mới.
- Với tác vụ quan trọng, lưu trạng thái xử lý và dùng outbox/inbox hoặc cơ chế deduplication phù hợp.

Retry chỉ là cơ chế thực thi lại. Idempotency mới là cơ chế giúp việc thực thi lại an toàn.

## 8. Phân loại lỗi trước khi retry hoặc fallback

Không phải mọi `R2dbcException` đều là lỗi connection. Có thể phân loại theo nhóm:

| Nhóm lỗi | Ví dụ | Hướng xử lý thường gặp |
|---|---|---|
| Kết nối/network | Connection reset, closed connection, I/O failure | Loại bỏ connection hỏng; cân nhắc retry có giới hạn nếu thao tác an toàn |
| Quá tải/tạm thời | Pool acquire timeout, database tạm thời từ chối kết nối | Backoff, giới hạn concurrency, xem lại tải và pool |
| Timeout câu lệnh | Statement timeout, query timeout | Tối ưu SQL hoặc điều chỉnh timeout; chỉ retry nếu phù hợp |
| SQL/data | Syntax error, type mismatch, constraint violation | Sửa câu SQL hoặc dữ liệu; thường không retry |
| Xác thực/phân quyền | Invalid credentials, permission denied | Sửa secret hoặc quyền; không retry liên tục |
| Cấu hình/protocol | Sai URL, thiếu driver, lỗi TLS/certificate | Sửa cấu hình hoặc dependency; không retry mù quáng |

Mã SQL state có thể giúp phân loại, nhưng mã và ý nghĩa cụ thể phụ thuộc database. Không nên chỉ dựa vào chuỗi thông báo exception vì thông báo có thể thay đổi theo driver hoặc phiên bản. Hãy kiểm tra cause chain, loại exception, SQL state và tài liệu driver.

## 9. Kiểm soát tải khi pool không còn connection tốt

Nếu database mất kết nối hoặc pool không thể tạo connection mới, request sẽ bắt đầu chờ acquire và cuối cùng có thể timeout. Trong giai đoạn này, tăng `max-size` không nhất thiết giúp ích: nếu database không nhận connection mới, pool lớn hơn chỉ tạo thêm áp lực khi database hồi phục.

Các biện pháp nên phối hợp:

- Đặt `max-size` theo ngân sách connection của database và số instance ứng dụng.
- Đặt `max-acquire-time` để request không chờ vô hạn.
- Giới hạn concurrency ở service hoặc tầng API để tránh dồn quá nhiều yêu cầu vào pool.
- Dùng circuit breaker nếu cần ngăn request tiếp tục gọi database khi lỗi liên tục, đồng thời cấu hình cửa sổ half-open và phục hồi hợp lý.
- Dùng bulkhead hoặc giới hạn hàng đợi để sự cố database không làm cạn tài nguyên của toàn bộ ứng dụng.
- Trả lỗi rõ ràng hoặc fallback có ý nghĩa nghiệp vụ khi database tạm thời không sẵn sàng.

Circuit breaker và retry cần phối hợp cẩn thận. Retry quá nhiều trước khi circuit breaker mở có thể khuếch đại tải. Circuit breaker mở quá lâu có thể làm ứng dụng không thử lại dù database đã phục hồi. Cần theo dõi trạng thái và đặt ngưỡng theo latency/error rate thực tế.

## 10. Quan sát sức khỏe connection pool

Để phát hiện connection hỏng và pool cạn trước khi người dùng báo lỗi, cần theo dõi cả chỉ số pool lẫn chỉ số database.

Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa khi vận hành |
|---|---|
| Allocated/total connections | Tổng số connection pool đã tạo hoặc đang quản lý |
| Acquired/active connections | Số connection hiện đang được ứng dụng sử dụng |
| Idle connections | Số connection sẵn sàng được cấp |
| Pending acquire | Số yêu cầu đang chờ connection |
| Acquire latency | Thời gian từ lúc yêu cầu đến khi nhận connection |
| Creation failures | Số lần pool không tạo được connection mới |
| Validation failures | Số connection không vượt qua validation |
| Evicted/disposed connections | Số connection bị loại khỏi pool |
| Connection lifetime/idle time | Tuổi thọ và thời gian nhàn rỗi của connection |
| Query latency/error rate | Độ trễ và tỷ lệ lỗi truy vấn ở tầng ứng dụng/database |

Tên metric cụ thể phụ thuộc R2DBC Pool, Micrometer, Spring Boot Actuator và phiên bản đang dùng. Hãy xem danh sách metric được export thực tế thay vì giả định mọi pool dùng cùng tên.

Các dấu hiệu cần chú ý:

- Pending acquire tăng liên tục: pool có thể quá nhỏ, connection bị giữ lâu hoặc database chậm.
- Idle bằng 0 và acquired chạm max-size: pool đang bão hòa.
- Validation failure tăng sau một khoảng idle: có thể network hoặc database đóng connection nhàn rỗi.
- Creation failure tăng sau database restart: database chưa sẵn sàng hoặc cấu hình kết nối có vấn đề.
- Acquire latency tăng nhưng query latency bình thường: có thể vấn đề nằm ở pool hoặc connection lifecycle.
- Query latency và lock wait cùng tăng: có thể database đang quá tải hoặc bị tranh chấp khóa.

Nên tạo cảnh báo theo xu hướng và thời gian kéo dài, tránh cảnh báo chỉ vì một lần validation thất bại ngắn hạn.

## 11. Kiểm thử validation và xử lý connection hỏng

Kiểm thử cần bao gồm tình huống connection hoạt động bình thường và các lỗi có thể xảy ra trong vòng đời của pool.

### 11.1. Kiểm thử validation cơ bản

Với pool đã cấu hình validation query, có thể chạy một thao tác đơn giản qua `DatabaseClient` hoặc repository nhiều lần, trả connection về pool giữa các lần gọi và quan sát validation/eviction metrics. Kiểm tra rằng connection được tạo lại khi pool loại bỏ connection không hợp lệ.

### 11.2. Mô phỏng database đóng connection nhàn rỗi

Trong môi trường kiểm thử cô lập:

1. Lấy connection và thực hiện một truy vấn thành công.
2. Trả connection về pool.
3. Dùng database admin hoặc công cụ kiểm thử để đóng session tương ứng, hoặc cấu hình môi trường để connection nhàn rỗi hết hạn.
4. Yêu cầu ứng dụng lấy connection tiếp theo.
5. Xác nhận pool phát hiện connection cũ, loại bỏ nó và tạo/cấp connection hợp lệ mới.

Không thực hiện thao tác kill session trên production để kiểm thử. Cần có môi trường thử nghiệm và xác định rõ session nào thuộc ứng dụng.

### 11.3. Kiểm thử network reset hoặc failover

Có thể mô phỏng mất mạng hoặc restart database trong môi trường thử nghiệm. Xác nhận rằng:

- Lỗi được truyền ra reactive pipeline.
- Connection lỗi không tiếp tục được tái sử dụng như connection khỏe.
- Pool có thể tạo connection mới sau khi database phục hồi.
- Retry có giới hạn và không tạo vòng lặp vô hạn.
- Request nhận lỗi hoặc kết quả phù hợp trong thời gian database không sẵn sàng.
- Transaction và dữ liệu không bị nhân đôi khi có retry.

### 11.4. Kiểm thử cancellation và cleanup

Khi subscriber hủy publisher hoặc request bị timeout, connection phải được release theo cơ chế cleanup. Nếu connection bị giữ lại, pool có thể cạn dù database vẫn hoạt động. Dùng metrics acquired/idle/pending để quan sát sau các tình huống thành công, lỗi và cancellation.

## 12. Những lỗi thiết kế thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng connection đã tạo thì luôn khỏe | Server hoặc network có thể đóng connection khi nó nhàn rỗi | Cấu hình validation và eviction phù hợp |
| Remote validation trước mọi query mà không đo | Tăng round trip và tải database | Chọn thời điểm validation theo đặc điểm workload |
| Dùng local validation như bằng chứng server còn sống | Local check không nhất thiết kiểm tra network | Dùng remote validation hoặc validation query khi cần xác nhận server |
| Đặt `max-idle-time` dài hơn firewall idle timeout | Pool có thể cấp connection đã bị network đóng | Đặt idle time thấp hơn ngưỡng hạ tầng với biên an toàn |
| Không đặt acquire timeout | Request có thể chờ pool quá lâu | Đặt timeout theo SLA và xử lý quá tải |
| Tăng `max-size` mỗi khi acquire timeout | Database có thể bị quá tải thêm | Đo connection usage, query latency và ngân sách connection |
| Bắt lỗi rồi trả `Mono.empty()` | Che giấu sự cố database và tạo kết quả sai | Truyền lỗi hoặc ánh xạ thành lỗi ứng dụng rõ ràng |
| Retry mọi exception | Lặp lỗi vĩnh viễn và tăng tải | Phân loại lỗi, retry có giới hạn và backoff |
| Retry thao tác ghi không idempotent | Có thể ghi dữ liệu hai lần khi commit outcome không rõ | Dùng idempotency key và unique constraint |
| Retry bên trong transaction đã hỏng | Có thể tiếp tục dùng transaction/connection không hợp lệ | Đặt retry bên ngoài ranh giới transaction để tạo transaction mới |
| Giữ connection trong field hoặc cache | Connection có thể stale và pool không quản lý được vòng đời | Acquire/release trong phạm vi thao tác |
| Quên cleanup khi tự acquire connection | Connection leak làm pool cạn | Dùng `usingWhen` hoặc API quản lý resource tương ứng |

## 13. Quy trình xử lý khi phát hiện connection hỏng

Khi có lỗi connection trong production, có thể xử lý theo trình tự:

1. **Nhận diện loại lỗi:** lấy exception root cause, SQL state, thông tin driver và thời điểm xảy ra.
2. **Kiểm tra sức khỏe database/network:** xác định database restart, failover, hết connection, firewall reset hoặc lỗi xác thực.
3. **Quan sát pool:** xem acquired, idle, pending, creation failure, validation failure và acquire latency.
4. **Để pool thay connection lỗi:** xác nhận driver/pool có loại bỏ connection không hợp lệ; nếu cần invalidation thủ công, dùng API được hỗ trợ bởi pool cụ thể.
5. **Giới hạn request mới:** dùng acquire timeout, concurrency limit hoặc circuit breaker để tránh làm sự cố lan rộng.
6. **Quyết định retry:** chỉ retry lỗi tạm thời và thao tác có thể thực hiện lại an toàn; dùng backoff, jitter và số lần thử hữu hạn.
7. **Xử lý kết quả không chắc chắn:** với lỗi trong commit, tra cứu theo idempotency key hoặc trạng thái nghiệp vụ trước khi gửi lại lệnh ghi.
8. **Xác nhận phục hồi:** theo dõi connection creation, validation failure, pending acquire và query success sau khi database hoạt động lại.

## 14. Nguyên tắc lựa chọn cấu hình

- Dùng validation để giảm nguy cơ cấp connection stale, nhưng vẫn phải xử lý lỗi trong lúc query.
- Dùng local validation cho trạng thái cục bộ và remote validation/validation query khi cần xác nhận khả năng giao tiếp với server.
- Chọn `maxIdleTime` theo idle timeout của database và network; chọn `maxLifeTime` theo chính sách tuổi thọ session.
- Đặt acquire timeout để giới hạn thời gian chờ pool; không nhầm nó với query timeout.
- Đặt validation query nhẹ, không gây side effect và tương thích với database.
- Để `DatabaseClient` quản lý connection thông thường; nếu acquire thủ công, luôn cleanup khi complete, error và cancel.
- Không tái sử dụng connection đã biết là hỏng; dùng cơ chế discard của pool cụ thể nếu cần loại bỏ tường minh.
- Retry có giới hạn, backoff, jitter và lọc lỗi tạm thời; không retry mù quáng thao tác ghi.
- Đặt retry bên ngoài transaction cần tạo mới sau lỗi và bảo đảm idempotency cho side effect.
- Theo dõi metrics pool, database và network để điều chỉnh cấu hình dựa trên số liệu.

Connection pool giúp tái sử dụng tài nguyên hiệu quả, nhưng chỉ hoạt động tin cậy khi ứng dụng quản lý được vòng đời connection và phản ứng đúng với lỗi. Validation, idle/lifetime eviction và timeout làm giảm khả năng connection stale được cấp cho request. Khi sự cố vẫn xảy ra trong lúc sử dụng, reactive error handling, cleanup, retry có giới hạn và idempotency giúp hệ thống phục hồi mà không che giấu lỗi hoặc tạo side effect lặp.
