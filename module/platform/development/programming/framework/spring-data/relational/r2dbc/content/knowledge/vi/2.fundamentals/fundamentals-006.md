# Điều tiết nhu cầu dữ liệu (backpressure) và giới hạn ở tầng cơ sở dữ liệu

Trong Spring Data Relational R2DBC, ứng dụng truy vấn cơ sở dữ liệu bằng các kiểu reactive như `Mono<T>` và `Flux<T>`. Những kiểu này cho phép dữ liệu được phát ra theo nhu cầu của subscriber, giúp ứng dụng xử lý luồng kết quả mà không phải chặn một thread để chờ từng thao tác I/O.

Tuy nhiên, backpressure ở tầng Reactive Streams chỉ là một phần của bài toán kiểm soát tải. Một truy vấn vẫn có thể đọc quá nhiều hàng, quét một bảng lớn, giữ connection lâu hoặc làm cơ sở dữ liệu chịu quá nhiều truy vấn đồng thời. Muốn kiểm soát tài nguyên từ đầu đến cuối, cần phối hợp nhu cầu reactive với giới hạn trong câu SQL, cách phân trang, cấu hình driver, connection pool và các giới hạn do hệ quản trị cơ sở dữ liệu cung cấp.

## 1. Vì sao cần kiểm soát lượng dữ liệu?

Giả sử một API gọi `repository.findAll()` để đọc hàng triệu bản ghi rồi trả kết quả về client. Dù API trả về `Flux<Customer>`, ứng dụng vẫn có thể gặp các vấn đề sau:

- Client đọc chậm khiến luồng kết quả tồn tại lâu. Connection hoặc transaction dùng cho truy vấn có thể bị giữ trong thời gian dài.
- Một toán tử gom toàn bộ kết quả như `collectList()` khiến toàn bộ dữ liệu phải nằm trong bộ nhớ của ứng dụng.
- Driver có thể đọc trước hoặc buffer một số hàng. Vì vậy, số phần tử subscriber đã nhận không nhất thiết bằng số hàng database đã xử lý hoặc gửi qua mạng.
- Nhiều request đồng thời có thể chiếm hết connection trong pool, làm request mới phải chờ hoặc hết thời gian chờ lấy connection.
- Một câu SQL thiếu điều kiện lọc hoặc index phù hợp vẫn có thể quét, sắp xếp hay join một lượng dữ liệu rất lớn, kể cả khi ứng dụng chỉ cần một phần kết quả.

Do đó, cần trả lời riêng ba câu hỏi: subscriber đang cần bao nhiêu phần tử, câu SQL được phép trả về bao nhiêu hàng, và database được phép tiêu tốn bao nhiêu tài nguyên để tạo ra các hàng đó.

## 2. Backpressure trong Reactive Streams

Reactive Streams định nghĩa cơ chế trao đổi nhu cầu giữa subscriber và publisher. Trong Reactor, `Flux` và `Mono` là các kiểu publisher thường gặp trong Spring Data R2DBC.

Một subscriber không nhất thiết phải nhận tất cả dữ liệu ngay lập tức. Nó có thể yêu cầu publisher phát một số phần tử bằng `request(n)`. Publisher chỉ phát tối đa lượng phần tử đã được yêu cầu, trừ các tín hiệu kết thúc hoặc lỗi. Subscriber cũng có thể hủy subscription bằng `cancel()` khi không cần dữ liệu nữa.

Ví dụ về ý nghĩa của nhu cầu:

1. Subscriber đăng ký vào một `Flux` nhưng ban đầu chưa yêu cầu phần tử nào.
2. Subscriber gọi `request(1)` và cho biết hiện tại nó có thể tiếp nhận một phần tử.
3. Publisher phát một phần tử bằng `onNext`.
4. Khi xử lý xong, subscriber có thể yêu cầu thêm phần tử.
5. Khi subscriber hủy subscription, tín hiệu hủy được truyền ngược lên chuỗi publisher ở mức mà các thành phần hỗ trợ.

Trong một luồng R2DBC điển hình, nhu cầu có thể đi qua các tầng như sau:

```text
HTTP client
    |
    v
Spring WebFlux handler / subscriber
    |
    v
Service: Flux<Customer>
    |
    v
Spring Data R2DBC repository / DatabaseClient
    |
    v
R2DBC driver
    |
    v
Database server
```

Backpressure giúp các publisher reactive phối hợp lượng dữ liệu được phát xuống downstream. Khi downstream xử lý chậm, demand có thể giảm và làm chậm việc phát thêm dữ liệu từ upstream. Khi subscriber hủy, các tầng phía trên có cơ hội hủy công việc đang thực hiện.

**Backpressure không đồng nghĩa với giới hạn số hàng của truy vấn.** Một subscriber có thể nhận dữ liệu theo từng nhóm nhỏ nhưng cuối cùng vẫn đọc hết hàng triệu bản ghi. Cơ chế demand cũng không đảm bảo database ngừng thực thi ngay lập tức: mức độ dừng đọc, hủy cursor và giải phóng tài nguyên phụ thuộc vào driver, giao thức và hệ quản trị cơ sở dữ liệu.

## 3. Phân biệt các loại giới hạn

Các cơ chế sau giải quyết những vấn đề khác nhau và không thể thay thế hoàn toàn cho nhau.

| Cơ chế | Kiểm soát điều gì? | Có giới hạn tổng số hàng trả về không? |
|---|---|---|
| Reactive Streams demand | Số phần tử subscriber yêu cầu tại một thời điểm | Không |
| Reactor `limitRate(n)` | Cách Reactor chia nhỏ và điều tiết request upstream | Không |
| SQL `LIMIT` hoặc cú pháp tương đương | Số hàng tối đa mà truy vấn trả về | Có |
| Phân trang theo khóa (keyset pagination) | Kích thước từng lô và phạm vi đọc tiếp theo | Có, theo từng truy vấn |
| Fetch size của driver | Gợi ý số hàng driver lấy trong một lần trao đổi hoặc một đợt đọc | Không |
| Connection pool `maxSize` | Số connection được cấp đồng thời từ pool | Không |
| Giới hạn ở database | Thời gian truy vấn, connection, khóa, bộ nhớ hoặc tài nguyên khác tùy hệ quản trị | Không nhất thiết |

Thiết kế tốt thường dùng nhiều lớp: SQL giới hạn kết quả, subscriber tiêu thụ theo demand, driver đọc theo lô phù hợp, pool giới hạn số truy vấn đồng thời và database áp dụng các guardrail về tài nguyên.

## 4. Đọc dữ liệu bằng Spring Data R2DBC

Repository reactive thường trả về `Mono<T>` cho kết quả đơn hoặc `Flux<T>` cho nhiều kết quả:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByActiveTrue();
}
```

`findByActiveTrue()` trả về một `Flux<Customer>`. Subscriber có thể tiêu thụ từng phần tử theo nhu cầu, nhưng phương thức này vẫn có thể trả về tất cả customer đang hoạt động. Nếu nghiệp vụ chỉ cần một số lượng hữu hạn, hãy đưa giới hạn vào truy vấn.

Ví dụ dùng `@Query` với cú pháp `LIMIT` của PostgreSQL hoặc MySQL:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Query("""
        SELECT id, name, created_at
        FROM customer
        WHERE active = true
          AND id > :afterId
        ORDER BY id
        LIMIT :batchSize
        """)
    Flux<Customer> findNextBatch(
            @Param("afterId") Long afterId,
            @Param("batchSize") int batchSize);
}
```

Ở đây:

- `id > :afterId` xác định điểm bắt đầu của lô tiếp theo.
- `ORDER BY id` tạo thứ tự ổn định để xác định cursor.
- `LIMIT :batchSize` giới hạn số hàng database trả về trong một lần truy vấn.
- `Flux<Customer>` cho phép consumer xử lý các hàng theo kiểu reactive.

`LIMIT` là cú pháp phụ thuộc dialect. SQL Server, Oracle và các hệ quản trị khác có thể dùng cú pháp giới hạn hàng khác. Hãy kiểm tra SQL được hỗ trợ bởi database và dialect đang sử dụng. Nếu dùng `DatabaseClient`, nguyên tắc tương tự áp dụng: viết giới hạn ngay trong SQL rồi gọi `fetch().all()` để nhận `Flux`.

```java
Flux<Customer> customers = databaseClient.sql("""
        SELECT id, name
        FROM customer
        WHERE active = :active
        ORDER BY id
        LIMIT :maxRows
        """)
    .bind("active", true)
    .bind("maxRows", 200)
    .map((row, metadata) -> new Customer(
        row.get("id", Long.class),
        row.get("name", String.class)))
    .all();
```

Trong ứng dụng thực tế, không nên để client tùy ý gửi một `batchSize` rất lớn. Hãy xác thực và áp dụng giới hạn tối đa ở service hoặc tầng API:

```java
public Flux<Customer> findNextBatch(long afterId, int requestedSize) {
    int batchSize = Math.max(1, Math.min(requestedSize, 500));
    return customerRepository.findNextBatch(afterId, batchSize);
}
```

Giá trị `500` chỉ là ví dụ; giới hạn phù hợp phải dựa trên kích thước bản ghi, độ trễ, tải database và phép đo của hệ thống.

## 5. Giới hạn kết quả bằng SQL và phân trang

### 5.1. LIMIT và OFFSET

Phân trang offset phù hợp với màn hình cần chuyển đến một trang cụ thể:

```sql
SELECT id, name, created_at
FROM customer
WHERE active = true
ORDER BY created_at DESC, id DESC
LIMIT 50 OFFSET 100;
```

`LIMIT 50` giới hạn số hàng trả về ở trang hiện tại. `OFFSET 100` bỏ qua 100 hàng trước đó. Cần có `ORDER BY` ổn định; nếu không, cùng một offset có thể trả về các tập hàng khác nhau giữa những lần chạy.

Với offset lớn, database thường phải đi qua nhiều hàng trước khi trả về trang cần lấy. Điều này có thể tốn chi phí khi người dùng chuyển đến các trang sâu. Nếu cần đọc liên tục một tập dữ liệu lớn, phân trang theo khóa thường phù hợp hơn.

### 5.2. Keyset pagination

Keyset pagination dùng giá trị của hàng cuối cùng ở lô trước làm cursor. Ví dụ, nếu `id` tăng đơn điệu và duy nhất:

```sql
SELECT id, name, created_at
FROM customer
WHERE id > :lastSeenId
ORDER BY id
LIMIT :batchSize;
```

Sau khi xử lý lô hiện tại, lấy `id` của hàng cuối làm `lastSeenId` cho truy vấn tiếp theo. Database không cần bỏ qua một số lượng lớn hàng bằng `OFFSET`.

Để cách làm này đáng tin cậy:

- Thứ tự sắp xếp phải ổn định và nên kết thúc bằng một khóa duy nhất.
- Điều kiện cursor phải khớp với thứ tự sắp xếp. Nếu sắp xếp theo nhiều cột, cursor cần chứa đủ các giá trị để xác định vị trí tiếp theo.
- Các cột dùng trong điều kiện lọc và sắp xếp nên có index phù hợp.
- Cần xác định nghiệp vụ xử lý dữ liệu mới được thêm hoặc bị cập nhật trong lúc đang đọc.

Nếu sắp xếp theo `created_at` nhưng nhiều hàng có cùng timestamp, chỉ dùng `created_at > :lastSeenTime` có thể bỏ sót hàng. Có thể dùng thêm khóa duy nhất làm điều kiện phân định:

```sql
SELECT id, name, created_at
FROM customer
WHERE created_at > :lastSeenTime
   OR (created_at = :lastSeenTime AND id > :lastSeenId)
ORDER BY created_at, id
LIMIT :batchSize;
```

### 5.3. Chỉ lấy các cột cần thiết

Giới hạn số hàng chưa đủ nếu mỗi hàng chứa nhiều cột lớn. Hãy chỉ `SELECT` các cột cần cho nghiệp vụ, đặc biệt với cột JSON, văn bản dài hoặc dữ liệu nhị phân. Projection giúp giảm dữ liệu truyền từ database, lượng dữ liệu driver phải giữ và chi phí chuyển đổi thành object.

### 5.4. Đếm tổng số hàng

Để hiển thị tổng số trang, ứng dụng thường cần thêm một truy vấn `COUNT(*)`. Truy vấn đếm có thể tốn tài nguyên riêng và không nên được chạy tự động cho mọi luồng dữ liệu lớn nếu nghiệp vụ không cần. Hãy quyết định rõ API cần tổng số chính xác, ước lượng hay chỉ cần cursor để lấy trang tiếp theo.

## 6. Điều tiết demand bằng các toán tử Reactor

Các toán tử Reactor giúp điều chỉnh cách dữ liệu đi qua pipeline. Cần hiểu rõ toán tử nào điều tiết nhu cầu, toán tử nào giới hạn tổng số phần tử và toán tử nào có thể tạo buffer.

### 6.1. `limitRate`

```java
customerRepository.findByActiveTrue()
    .limitRate(128)
    .subscribe(this::processCustomer);
```

`limitRate(128)` điều tiết cách Reactor yêu cầu dữ liệu từ upstream theo các nhóm request. Nó có thể giúp tránh việc downstream yêu cầu một lượng rất lớn cùng lúc. Nó **không** có nghĩa là truy vấn chỉ trả về 128 hàng; khi subscriber tiếp tục yêu cầu, luồng vẫn có thể phát tất cả kết quả.

### 6.2. `take`

```java
customerRepository.findByActiveTrue()
    .take(100);
```

`take(100)` giới hạn số phần tử mà pipeline phát tiếp xuống downstream rồi hủy subscription. Đây là giới hạn ở tầng reactive. Tùy driver và database, một phần dữ liệu có thể đã được đọc trước hoặc buffer. Nếu yêu cầu nghiệp vụ là database chỉ trả về tối đa 100 hàng, hãy dùng `LIMIT 100` trong SQL.

### 6.3. Giới hạn concurrency của `flatMap`

Khi mỗi hàng cần gọi thêm một dịch vụ hoặc thực hiện một thao tác bất đồng bộ, `flatMap` có thể tạo nhiều tác vụ đồng thời:

```java
customerRepository.findByActiveTrue()
    .flatMap(this::enrichCustomer, 8, 1);
```

Tham số `8` giới hạn số inner publisher được xử lý đồng thời; `1` đặt prefetch cho mỗi inner publisher. Giới hạn concurrency giúp tránh mở quá nhiều công việc cùng lúc. Nếu thao tác bên trong cũng truy cập database, concurrency cần được cân đối với kích thước connection pool và khả năng chịu tải của database.

Khi cần xử lý tuần tự, `concatMap` là lựa chọn dễ kiểm soát hơn:

```java
customerRepository.findByActiveTrue()
    .concatMap(this::processCustomer);
```

Đổi lại, xử lý tuần tự có thể làm giảm throughput. Hãy chọn dựa trên yêu cầu thứ tự và giới hạn tài nguyên.

### 6.4. Các toán tử buffer và backpressure

Một số upstream không thể giảm tốc độ phát dữ liệu theo demand. Trong tình huống đó, Reactor cung cấp các chiến lược như `onBackpressureBuffer`, `onBackpressureDrop` và `onBackpressureLatest`.

- `onBackpressureBuffer` giữ phần tử trong buffer khi downstream chậm. Buffer cần có giới hạn và chính sách khi đầy; buffer không giới hạn có thể làm cạn bộ nhớ.
- `onBackpressureDrop` bỏ các phần tử không thể tiếp nhận. Cách này chỉ phù hợp khi nghiệp vụ chấp nhận mất dữ liệu.
- `onBackpressureLatest` giữ phần tử mới nhất và bỏ các phần tử cũ hơn trong tình huống quá tải. Nó phù hợp với một số luồng trạng thái cập nhật liên tục, nhưng thường không phù hợp với truy vấn cần xử lý đầy đủ từng hàng.

Publisher R2DBC tuân theo mô hình reactive demand. Vì vậy, không nên thêm buffer hoặc chiến lược drop một cách máy móc vào truy vấn repository. Trước tiên hãy xác định upstream nào không hỗ trợ backpressure và dữ liệu có được phép mất hay không.

### 6.5. Chú ý các toán tử làm tăng bộ nhớ

Các toán tử như `collectList()`, `collectMap()`, `sort()` hoặc `buffer()` có thể giữ nhiều dữ liệu trong bộ nhớ trước khi phát kết quả tiếp theo. Ví dụ:

```java
// Có thể giữ toàn bộ kết quả trong bộ nhớ.
customerRepository.findAll()
    .collectList();
```

Nếu kết quả không có giới hạn, việc gom toàn bộ thành một `List` có thể gây áp lực bộ nhớ hoặc `OutOfMemoryError`. Hãy ưu tiên xử lý từng phần tử hoặc từng lô có kích thước hữu hạn. Chỉ gom thành collection khi đã giới hạn kích thước và hiểu rõ lượng dữ liệu tối đa.

## 7. Fetch size và cách driver đọc dữ liệu

Fetch size mô tả số hàng mà driver được gợi ý lấy trong một đợt đọc. Trong R2DBC SPI, `Statement.fetchSize(int)` là một gợi ý cho driver về kích thước lấy dữ liệu. Đây không phải giới hạn tổng số hàng của truy vấn.

Ví dụ minh họa ở mức R2DBC SPI:

```java
connection.createStatement("SELECT id, name FROM customer ORDER BY id")
    .fetchSize(100)
    .execute();
```

Hành vi thực tế phụ thuộc driver và database. Một số driver có thể dùng cursor hoặc cơ chế đọc theo lô; driver khác có thể bỏ qua gợi ý hoặc buffer dữ liệu theo cách riêng. Cũng cần kiểm tra điều kiện giao dịch và cấu hình mà driver yêu cầu để sử dụng cursor.

Trong Spring Data R2DBC, các phương thức repository cấp cao không nhất thiết cung cấp một chỗ cấu hình fetch size thống nhất cho mọi driver. Nếu cần điều khiển ở mức statement, hãy xem API của driver và cách tích hợp statement của phiên bản Spring Data đang dùng. Đừng giả định rằng đặt fetch size sẽ giới hạn số hàng hoặc bảo đảm bộ nhớ luôn bị chặn ở một con số cố định.

## 8. Giới hạn số truy vấn đồng thời bằng connection pool

Connection pool kiểm soát số connection được cấp đồng thời. Với R2DBC Pool, có thể cấu hình kích thước tối đa và thời gian chờ lấy connection:

```java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(2)
        .maxSize(20)
        .maxAcquireTime(Duration.ofSeconds(5))
        .maxIdleTime(Duration.ofMinutes(10))
        .build();

ConnectionPool pool = new ConnectionPool(configuration);
```

Đoạn mã minh họa cấu hình pool; các import và cách tạo `ConnectionFactory` phụ thuộc cấu hình ứng dụng. `maxSize(20)` giới hạn số connection pool có thể cấp cùng lúc. Khi hết connection, request mới phải chờ connection được trả về hoặc hết `maxAcquireTime`.

Connection pool giúp giới hạn số session mà ứng dụng mở đến database, nhưng không giới hạn số hàng trong mỗi truy vấn. Một truy vấn duy nhất vẫn có thể đọc một lượng dữ liệu rất lớn. Ngược lại, quá nhiều request nhỏ chạy đồng thời vẫn có thể gây tải cao dù mỗi request chỉ lấy vài hàng.

Khi chọn `maxSize`, cần tính đến giới hạn connection của database, số instance ứng dụng, các service khác và connection dành cho quản trị. Không nên tăng pool chỉ để giảm thời gian chờ nếu database đã gần chạm giới hạn. Hãy theo dõi số connection đang hoạt động, connection nhàn rỗi, số request chờ và thời gian acquire.

## 9. Transaction và thời gian giữ connection

Với reactive transaction management, transaction gắn với quá trình subscribe và thực thi reactive publisher. Nếu một phương thức `@Transactional` trả về `Flux` dài, transaction có thể tiếp tục mở trong suốt thời gian luồng còn hoạt động. Connection được dùng trong transaction vì thế có thể bị giữ lâu.

Ví dụ, nếu API stream kết quả cho một client có mạng chậm, việc tiêu thụ chậm có thể kéo dài thời gian đọc và thời gian giữ connection. Nếu luồng bị bỏ quên hoặc không kết thúc đúng cách, tài nguyên có thể bị chiếm lâu hơn dự kiến.

Một số cách giảm rủi ro:

- Giới hạn số hàng trong từng truy vấn và chia công việc thành các lô có kích thước hữu hạn.
- Tránh giữ một transaction mở trong khi chờ một tác vụ bên ngoài hoặc một client đọc chậm.
- Với xử lý nền, đọc một lô, xử lý và lưu checkpoint phù hợp rồi mới đọc lô tiếp theo.
- Đảm bảo subscription kết thúc hoặc được hủy khi công việc không còn cần thiết.
- Kiểm tra cách transaction manager và driver giải phóng connection khi publisher hoàn tất, phát lỗi hoặc bị hủy.

Transaction có thể cần thiết để bảo đảm tính nhất quán của một nghiệp vụ. Hãy giữ transaction trong phạm vi nhỏ nhất đáp ứng yêu cầu nhất quán, đồng thời không chia nhỏ transaction một cách tùy tiện nếu điều đó làm thay đổi tính đúng đắn của nghiệp vụ.

## 10. Guardrail ở tầng database

Giới hạn ở tầng database bảo vệ hệ thống khi truy vấn chạy quá lâu hoặc tiêu thụ quá nhiều tài nguyên. Các khả năng cụ thể phụ thuộc hệ quản trị và phiên bản.

Các nhóm guardrail thường gặp gồm:

- **Statement/query timeout:** giới hạn thời gian một câu lệnh được phép chạy.
- **Lock timeout:** giới hạn thời gian chờ khóa, tránh một truy vấn chờ khóa vô thời hạn.
- **Connection limit:** giới hạn tổng số session hoặc connection.
- **Resource governance:** giới hạn hoặc phân bổ CPU, bộ nhớ, I/O hay mức đồng thời theo workload, user hoặc nhóm truy vấn nếu database hỗ trợ.
- **Quyền truy cập:** dùng tài khoản ứng dụng với quyền tối thiểu cần thiết, giới hạn thao tác và schema được phép truy cập.

Ví dụ, PostgreSQL có các thiết lập như `statement_timeout` và `lock_timeout`; các hệ quản trị khác có cơ chế và cú pháp riêng. Cần cấu hình ở đúng phạm vi (session, role, database hoặc hệ thống) theo chính sách vận hành. Không nên sao chép nguyên cấu hình của một database sang hệ quản trị khác.

Timeout bảo vệ hệ thống khỏi truy vấn kéo dài, nhưng không thay thế việc tối ưu truy vấn. Khi timeout xảy ra, ứng dụng cần xử lý lỗi và xác định liệu driver đã hủy câu lệnh, transaction đã rollback và connection có được trả lại pool hay chưa.

Một câu SQL có `LIMIT 20` vẫn có thể tốn nhiều tài nguyên nếu phải quét hàng triệu hàng hoặc sắp xếp một tập lớn trước khi tìm ra 20 hàng phù hợp. Hãy kiểm tra execution plan và tạo index phù hợp với điều kiện `WHERE`, thứ tự `ORDER BY` và cách join. Với PostgreSQL có thể dùng `EXPLAIN` hoặc `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường kiểm thử phù hợp; các hệ quản trị khác có công cụ xem execution plan tương ứng.

## 11. Kết hợp các lớp trong một luồng xử lý

Một luồng đọc dữ liệu lớn có thể được thiết kế theo các bước sau:

1. API nhận cursor và kích thước lô, sau đó xác thực kích thước lô trong giới hạn cấu hình.
2. Repository chạy câu SQL có điều kiện cursor, `ORDER BY` ổn định và `LIMIT`.
3. Driver đọc kết quả theo cách được hỗ trợ bởi driver; fetch size chỉ được xem là gợi ý nếu driver hỗ trợ.
4. Service xử lý từng phần tử hoặc dùng `flatMap` với concurrency hữu hạn.
5. Connection pool giới hạn số truy vấn có thể giữ connection đồng thời.
6. Database áp dụng timeout, connection limit và các guardrail phù hợp.
7. Client dùng cursor của hàng cuối để yêu cầu lô tiếp theo.

Sơ đồ luồng:

```text
Client gửi cursor + batchSize
            |
            v
Service xác thực batchSize
            |
            v
Repository chạy WHERE cursor + ORDER BY + LIMIT
            |
            v
R2DBC driver đọc kết quả theo khả năng hỗ trợ
            |
            v
Flux phát theo demand của subscriber
            |
            v
Xử lý có concurrency hữu hạn
            |
            v
Trả cursor tiếp theo cho client
```

Điểm quan trọng là mỗi lớp giải quyết một loại giới hạn. `LIMIT` kiểm soát kích thước kết quả của một truy vấn; demand kiểm soát tốc độ tiêu thụ; concurrency kiểm soát số công việc đang chạy; pool kiểm soát connection; database guardrail kiểm soát thời gian và tài nguyên ở phía server.

## 12. Kiểm thử và quan sát

Có thể kiểm tra hành vi demand ở tầng Reactor bằng `StepVerifier`:

```java
StepVerifier.create(customerRepository.findByActiveTrue(), 0)
    .thenRequest(1)
    .expectNextCount(1)
    .thenCancel()
    .verify();
```

Ví dụ này tạo subscriber ban đầu chưa yêu cầu phần tử, sau đó yêu cầu một phần tử và hủy subscription. Nó giúp kiểm tra cách publisher phản ứng với demand và cancellation ở tầng reactive. Nó **không chứng minh** database chỉ đọc đúng một hàng: driver có thể đã đọc trước hoặc buffer dữ liệu. Muốn kiểm tra điều đó, cần quan sát hành vi của driver, cursor, truy vấn và database bằng công cụ phù hợp.

Khi vận hành, nên theo dõi:

- Số hàng trả về, số hàng được xử lý và kích thước từng batch.
- Thời gian truy vấn, thời gian chờ connection và số lần timeout.
- Số connection active/idle, số request chờ acquire và thời gian giữ connection.
- Bộ nhớ heap, GC, kích thước buffer và độ trễ của downstream.
- CPU, I/O, số session, lock wait và execution plan ở database.
- Số subscription bị hủy và cách driver giải phóng tài nguyên sau cancellation.

Hãy kiểm thử với dữ liệu có quy mô gần thực tế và mô phỏng downstream đọc chậm. Một truy vấn chạy nhanh trên vài trăm hàng trong môi trường phát triển chưa chứng minh rằng cách làm đó an toàn với hàng triệu hàng trong production.

## 13. Những lỗi thiết kế thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng `Flux` tự động giới hạn tổng số hàng | Truy vấn vẫn có thể đọc toàn bộ bảng | Thêm điều kiện lọc và giới hạn SQL |
| Dùng `limitRate(100)` như giới hạn kết quả | Luồng vẫn tiếp tục phát khi có demand mới | Dùng `LIMIT` hoặc phân trang nếu cần giới hạn tổng số hàng |
| Dùng `take(n)` thay cho giới hạn SQL | Driver có thể đã đọc trước một phần dữ liệu | Đẩy giới hạn xuống câu SQL |
| Gọi `collectList()` trên truy vấn lớn | Tất cả kết quả có thể nằm trong heap | Xử lý từng hàng hoặc từng batch hữu hạn |
| Dùng buffer không giới hạn | Bộ nhớ tăng khi downstream chậm | Dùng backpressure tự nhiên hoặc buffer hữu hạn có chính sách overflow |
| `flatMap` không giới hạn trên nguồn lớn | Quá nhiều tác vụ và truy vấn đồng thời | Đặt concurrency và prefetch phù hợp |
| Tăng connection pool mà không đo tải database | Database có thể quá tải vì quá nhiều session | Đặt giới hạn pool dựa trên tổng ngân sách connection |
| Dùng offset rất lớn để quét dữ liệu tuần tự | Chi phí bỏ qua hàng tăng theo độ sâu trang | Dùng keyset pagination khi phù hợp |
| Chỉ thêm `LIMIT` mà không xem execution plan | Database vẫn có thể quét hoặc sort lượng dữ liệu lớn | Tối ưu index, điều kiện lọc và thứ tự sắp xếp |

## 14. Nguyên tắc lựa chọn

- Cần kiểm soát **tổng số hàng** của một truy vấn: dùng `LIMIT` hoặc cú pháp tương đương trong SQL.
- Cần đọc một tập dữ liệu lớn theo nhiều lượt: ưu tiên keyset pagination với cursor ổn định.
- Cần điều tiết **tốc độ tiêu thụ** trong pipeline: dùng demand tự nhiên của Reactive Streams và cân nhắc `limitRate`.
- Cần giới hạn số tác vụ bất đồng bộ chạy cùng lúc: đặt concurrency cho `flatMap` hoặc dùng `concatMap` khi cần tuần tự.
- Cần kiểm soát **số connection**: cấu hình connection pool và theo dõi thời gian acquire.
- Cần tránh truy vấn hoặc chờ khóa kéo dài: cấu hình timeout ở database hoặc cơ chế tương ứng của hệ quản trị.
- Cần giảm lượng dữ liệu truyền và chuyển đổi: chỉ chọn các cột cần thiết và dùng index phù hợp.
- Cần giữ bộ nhớ ổn định: tránh gom toàn bộ kết quả và kiểm soát mọi buffer theo kích thước hữu hạn.

Backpressure giúp Spring Data R2DBC xử lý luồng dữ liệu theo khả năng tiếp nhận của downstream. Giới hạn SQL và guardrail của database bảo vệ hệ thống ở phía truy vấn và server. Khi các lớp này được phối hợp, ứng dụng có thể xử lý dữ liệu lớn theo cách có kiểm soát, đồng thời giảm nguy cơ cạn bộ nhớ, cạn connection và tạo tải quá mức lên cơ sở dữ liệu.
