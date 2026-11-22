# Điều chỉnh kích thước lấy dữ liệu khi trình điều khiển hỗ trợ

Khi một truy vấn R2DBC trả về nhiều hàng, ứng dụng cần cân bằng giữa bộ nhớ, số lần trao đổi dữ liệu với database và tốc độ tiêu thụ kết quả. Một số driver cho phép ứng dụng đưa ra gợi ý về số hàng lấy trong mỗi đợt thông qua `Statement.fetchSize(int)`. Nếu driver hỗ trợ cơ chế fetch theo đợt, cấu hình này có thể giúp kiểm soát lượng dữ liệu driver đọc trước và giảm áp lực bộ nhớ khi xử lý result set lớn.

`fetchSize` là gợi ý ở tầng R2DBC statement, không phải cam kết rằng database luôn gửi đúng số hàng trong mỗi network packet hoặc ứng dụng chỉ giữ tối đa đúng số hàng đó trong heap. Driver có thể hỗ trợ, diễn giải khác nhau hoặc bỏ qua gợi ý. Một số driver buffer toàn bộ kết quả; một số dùng cursor hoặc cơ chế streaming riêng; một số yêu cầu transaction hoặc cấu hình kết nối bổ sung để fetch theo đợt hoạt động như mong đợi.

Vì vậy, cần phân biệt `fetchSize` với `LIMIT`, pagination, Reactive Streams backpressure và batch ghi. `LIMIT` giới hạn tổng số hàng của một truy vấn; `fetchSize` gợi ý cách driver lấy result set; backpressure điều tiết số phần tử subscriber yêu cầu; batch ghi gom nhiều bộ tham số hoặc câu lệnh để thực thi. Các cơ chế này có thể phối hợp, nhưng không thay thế nhau.

## 1. Vì sao cần điều chỉnh fetch size?

Giả sử một báo cáo cần đọc vài trăm nghìn hàng từ bảng `event_log`. Nếu driver tải và giữ toàn bộ result set trước khi phát cho ứng dụng, lượng bộ nhớ cần dùng có thể rất lớn. Nếu driver hỗ trợ lấy dữ liệu theo từng đợt, ứng dụng có thể tiêu thụ một phần kết quả, sau đó driver mới lấy thêm khi cần.

Fetch size có thể ảnh hưởng đến:

- **Bộ nhớ phía ứng dụng:** số hàng/row buffer driver giữ trước khi phát tiếp.
- **Số lần trao đổi với server:** đợt nhỏ có thể làm tăng số lần fetch; đợt lớn có thể giảm overhead giao tiếp.
- **Độ trễ:** thời gian chờ trước khi nhận hàng đầu tiên và giữa các đợt.
- **Throughput:** lượng hàng xử lý mỗi giây khi driver, mạng và database có thể tận dụng fetch theo lô.
- **Thời gian giữ connection:** một result set streaming có thể giữ connection lâu hơn trong lúc ứng dụng tiêu thụ.

Không có một fetch size tối ưu cho mọi truy vấn. Kết quả phụ thuộc kích thước hàng, số cột, tốc độ mạng, database, driver, pool, tốc độ xử lý downstream và concurrency của ứng dụng.

### Ví dụ tình huống

Một endpoint chỉ hiển thị 25 customer gần đây không cần đọc 100.000 hàng rồi bỏ phần lớn. Trường hợp này nên dùng `ORDER BY` và `LIMIT` phù hợp.

Một job export cần đi qua 500.000 event có thể không thể dùng một trang nhỏ rồi giữ tất cả trong `List`. Job có thể stream `Flux` và, nếu driver hỗ trợ, cấu hình fetch size để điều chỉnh cách driver lấy dữ liệu từ server.

Hai tình huống đều đọc dữ liệu nhưng giải quyết hai vấn đề khác nhau: `LIMIT` giảm tổng dữ liệu cần truy vấn; `fetchSize` điều chỉnh cách lấy các hàng thuộc result set.

## 2. `Statement.fetchSize(int)` trong R2DBC SPI

R2DBC SPI định nghĩa `Statement.fetchSize(int rows)` như một gợi ý cho driver về số hàng cần lấy trong mỗi đợt khi đọc result set. Có thể gọi method này trên statement trước khi `execute()`:

```java
Statement statement = connection.createStatement("""
        SELECT id, event_type, created_at
        FROM event_log
        WHERE tenant_id = ?
        ORDER BY id
        """);

statement.bind(0, tenantId);
statement.fetchSize(256);

Publisher<? extends Result> results = statement.execute();
```

Giá trị `256` là ví dụ minh họa, không phải mặc định hoặc khuyến nghị chung. Driver có thể dùng nó làm số hàng fetch mỗi lần, diễn giải thành prefetch hint hoặc bỏ qua nếu không hỗ trợ.

### Fetch size bằng 0

Theo semantics của SPI, giá trị `0` biểu thị không đặt một fetch size cụ thể và để driver sử dụng mặc định của nó. Không nên hiểu `0` là không lấy hàng hoặc không cho phép result set. Giá trị âm không hợp lệ; hãy kiểm tra tài liệu SPI/driver của phiên bản đang dùng và validate cấu hình trước khi tạo statement.

### Đây là hint, không phải giới hạn cứng

Ngay cả khi gọi `fetchSize(256)`, ứng dụng không nên kết luận:

- Database luôn trả đúng 256 hàng trong một lần truyền mạng.
- Driver không bao giờ buffer nhiều hơn 256 hàng.
- Mỗi lần downstream request 256 phần tử thì database fetch đúng 256 hàng.
- Heap của ứng dụng bị giới hạn ở 256 object.
- Truy vấn tự động dùng cursor hoặc server-side streaming.

Những điều đó phụ thuộc cách driver triển khai, protocol, server và các operator ở downstream. Hãy xem `fetchSize` là một cấu hình gợi ý cần được xác minh bằng integration test và đo đạc.

## 3. Fetch size khác gì với các cơ chế khác?

| Cơ chế | Tác động ở đâu | Điều nó kiểm soát |
| --- | --- | --- |
| `Statement.fetchSize(n)` | R2DBC driver/statement | Gợi ý số hàng lấy trong mỗi đợt từ result set |
| SQL `LIMIT n` | Database query | Giới hạn tổng số hàng truy vấn trả về |
| `OFFSET` / keyset pagination | Database query và access pattern | Chia tập kết quả thành các trang |
| Reactive Streams `request(n)` | Publisher/subscriber | Số phần tử downstream sẵn sàng nhận |
| Reactor `limitRate(n)` | Pipeline Reactor | Điều chỉnh cách upstream được request theo nhóm |
| `buffer(n)` | Ứng dụng/Reactor pipeline | Gom tối đa n phần tử vào một collection trước khi phát collection đó |
| `collectList()` | Ứng dụng | Tích lũy toàn bộ phần tử thành một `List` |
| `Statement.add()` | R2DBC statement | Thêm nhiều bộ bind cho cùng một câu SQL ghi |

Ví dụ, `LIMIT 1000` và `fetchSize(100)` có thể được dùng cùng nhau: database trả tối đa 1.000 hàng; driver có thể lấy chúng theo các đợt khoảng 100 hàng nếu hỗ trợ. Nếu không có `LIMIT`, fetch size không tự giới hạn tổng số hàng.

### Fetch size không phải batch size của thao tác ghi

`Statement.add()` và multi-row `INSERT` liên quan đến cách gửi nhiều bộ giá trị để ghi dữ liệu. `fetchSize` liên quan đến đọc result set. Không dùng `fetchSize` để điều chỉnh số hàng insert/update trong một batch.

## 4. Fetch size và Reactive Streams backpressure

Reactive Streams định nghĩa demand: subscriber gọi `request(n)` để cho biết nó sẵn sàng nhận tối đa n phần tử tiếp theo. Reactor truyền demand ngược qua pipeline theo semantics của các operator.

Ví dụ:

```java
Flux<EventView> events = databaseClient.sql("""
            SELECT id, event_type, created_at
            FROM event_log
            ORDER BY id
            """)
        .map((row, metadata) -> new EventView(
                row.get("id", Long.class),
                row.get("event_type", String.class),
                row.get("created_at", LocalDateTime.class)
        ))
        .all();
```

Subscriber có thể yêu cầu một số phần tử nhất định. Tuy nhiên, driver có thể prefetch hoặc buffer một phần result set trước khi downstream yêu cầu hết các phần tử đó. Fetch size ảnh hưởng đến cách driver lấy dữ liệu; demand là tín hiệu giữa subscriber và publisher. Hai tầng liên quan nhưng không đồng nhất.

### Dùng `limitRate` không đồng nghĩa đặt fetch size

```java
events.limitRate(128);
```

`limitRate` điều chỉnh request upstream theo nhóm/prefetch trong Reactor. Nó không nhất thiết gọi `Statement.fetchSize(128)` và không bảo đảm driver sử dụng cursor 128 hàng. Nếu cần điều khiển cả hai tầng, phải cấu hình riêng theo khả năng driver.

### Backpressure không tự loại bỏ việc buffer toàn bộ

Các operator như `collectList()` chủ động tích lũy tất cả phần tử:

```java
Mono<List<EventView>> allEvents = events.collectList();
```

Cho dù nguồn có hỗ trợ fetch theo đợt, cuối cùng toàn bộ danh sách vẫn nằm trong bộ nhớ. Với export lớn, ưu tiên xử lý từng hàng hoặc từng chunk rồi ghi ra đích theo luồng, thay vì `collectList()` toàn bộ result set.

## 5. Driver có thể triển khai fetch size khác nhau

R2DBC SPI cung cấp một API chung, nhưng cách thực hiện nằm ở driver. Tùy driver, fetch size có thể:

- Được chuyển thành cấu hình cursor/server-side result set.
- Điều chỉnh lượng dữ liệu driver yêu cầu hoặc prefetch từ server.
- Chỉ có tác dụng trong một chế độ transaction/connection nhất định.
- Bị bỏ qua nếu driver không có cơ chế tương ứng.
- Bị giới hạn hoặc diễn giải theo cách riêng của driver.

Không nên suy ra hỗ trợ chỉ từ việc code biên dịch được. Nếu method `fetchSize` có default implementation trong phiên bản SPI/driver, lời gọi có thể không tạo ra thay đổi thực tế.

### Những điều cần xác minh trong tài liệu driver

Trước khi bật fetch size, hãy tìm câu trả lời cho các câu hỏi:

1. Driver có hỗ trợ `Statement.fetchSize(int)` không?
2. Giá trị có được áp dụng cho mọi statement hay chỉ SELECT/result set?
3. Driver dùng cursor, server-side fetch hay buffer client-side?
4. Có yêu cầu transaction đang mở hoặc `autoCommit` tắt không?
5. Có yêu cầu option kết nối riêng để bật streaming/cursor không?
6. Giá trị 0 và giá trị tối đa được hiểu như thế nào?
7. Fetch size ảnh hưởng đến generated values hoặc nhiều result set không?
8. Điều gì xảy ra khi subscriber cancel hoặc timeout giữa các đợt fetch?
9. Có giới hạn đối với prepared statement, scrollability hoặc kiểu dữ liệu lớn không?
10. Phiên bản driver nào hỗ trợ hành vi đó?

Nếu tài liệu driver không cam kết hỗ trợ, hãy để mặc định hoặc kiểm chứng bằng test thực tế trước khi đưa cấu hình vào production.

## 6. Thiết lập fetch size ở tầng R2DBC SPI

Khi cần kiểm soát statement trực tiếp, có thể gọi `fetchSize` trước `execute()`:

```java
Statement statement = connection.createStatement("""
        SELECT id, name
        FROM customer
        WHERE status = ?
        ORDER BY id
        """);

statement.bind(0, "ACTIVE");
statement.fetchSize(200);

Flux<CustomerView> rows = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.map((row, metadata) ->
                new CustomerView(
                        row.get("id", Long.class),
                        row.get("name", String.class)
                )
        )));
```

Ví dụ dùng placeholder `?` minh họa cho driver có bind marker dạng positional; marker thực tế phụ thuộc dialect. `fetchSize(200)` phải được gọi trước `execute()`. Mapping từng row thành DTO giúp downstream xử lý từng phần tử mà không cần tạo một `List` chứa toàn bộ result set.

### Quản lý connection khi dùng SPI trực tiếp

Trong ứng dụng Spring, không nên gọi `ConnectionFactory.create()` tùy tiện nếu thao tác cần tham gia reactive transaction hiện tại. Dùng `ConnectionFactoryUtils.getConnection(...)` để tra cứu connection đã bind với transaction context và release qua helper tương ứng:

```java
public Flux<CustomerView> streamActiveCustomers(int fetchSize) {
    if (fetchSize < 0) {
        return Flux.error(new IllegalArgumentException(
                "fetchSize không được âm"
        ));
    }

    return Flux.usingWhen(
            ConnectionFactoryUtils.getConnection(connectionFactory),
            connection -> {
                Statement statement = connection.createStatement("""
                        SELECT id, name
                        FROM customer
                        WHERE status = ?
                        ORDER BY id
                        """);

                statement.bind(0, "ACTIVE");
                if (fetchSize > 0) {
                    statement.fetchSize(fetchSize);
                }

                return Flux.from(statement.execute())
                        .concatMap(result -> Flux.from(result.map(
                                (row, metadata) -> new CustomerView(
                                        row.get("id", Long.class),
                                        row.get("name", String.class)
                                )
                        )));
            },
            connection -> ConnectionFactoryUtils.releaseConnection(
                    connection, connectionFactory
            ),
            (connection, error) -> ConnectionFactoryUtils.releaseConnection(
                    connection, connectionFactory
            ),
            connection -> ConnectionFactoryUtils.releaseConnection(
                    connection, connectionFactory
            )
    );
}
```

Đây là ví dụ khung dùng R2DBC SPI; cần khai báo `connectionFactory`, DTO và imports tương ứng. Nếu `fetchSize` bằng 0, ví dụ không gọi method và để driver dùng mặc định. `usingWhen` xử lý release khi hoàn tất, lỗi hoặc cancellation. Khi connection thuộc transaction do Spring quản lý, `ConnectionFactoryUtils.releaseConnection` giữ đúng ownership của transaction manager; ngoài transaction, helper giải phóng connection đã lấy.

Nếu không cần điều khiển SPI trực tiếp, ưu tiên `DatabaseClient` hoặc repository để giữ code ở tầng abstraction của Spring Data.

## 7. Thiết lập qua `DatabaseClient` khi phiên bản Spring hỗ trợ filter

Một số phiên bản Spring Framework cung cấp `StatementFilterFunction` trên `DatabaseClient.Builder`. Filter có thể chỉnh statement trước khi thực thi:

```java
DatabaseClient client = DatabaseClient.builder()
        .connectionFactory(connectionFactory)
        .filter((statement, next) -> {
            statement.fetchSize(200);
            return next.execute(statement);
        })
        .build();
```

API filter và cách cấu hình có thể khác giữa các phiên bản Spring Framework. Kiểm tra Javadoc của `DatabaseClient.Builder` và `StatementFilterFunction` trong phiên bản dự án trước khi dùng. Filter trên áp dụng cho các statement đi qua client đã cấu hình; nó không tự áp dụng cho một `DatabaseClient` khác được tạo bởi infrastructure riêng.

### Phạm vi của filter

Một filter ở cấp builder có thể ảnh hưởng tới nhiều statement của client, bao gồm statement không phải truy vấn đọc. Nếu chỉ muốn đặt fetch size cho SELECT, cần có cách nhận diện statement phù hợp với phiên bản API và SQL convention của dự án. Không đặt một giá trị fetch size toàn cục một cách máy móc cho insert/update.

Nếu client được dùng bởi `R2dbcEntityTemplate` hoặc repository, cần bảo đảm template/repository thực sự được tạo từ client đã cấu hình. Tạo thêm một `DatabaseClient` bean không có nghĩa Spring Data repositories tự động dùng bean đó.

### Không có filter API phù hợp

Nếu phiên bản Spring không cung cấp cơ chế filter cần thiết, các lựa chọn gồm:

- Dùng R2DBC SPI trực tiếp cho truy vấn cần fetch size và quản lý connection đúng cách.
- Dùng cấu hình riêng của driver nếu driver cung cấp.
- Dùng abstraction query/adapter riêng để giới hạn phạm vi statement.
- Nâng cấp Spring Framework/driver sau khi kiểm tra tương thích.

Không nên dùng reflection để truy cập statement nội bộ của `DatabaseClient` hoặc sửa state sau khi execute.

## 8. Chọn giá trị fetch size

Fetch size nhỏ và lớn có trade-off khác nhau.

| Fetch size | Ưu điểm có thể có | Chi phí/rủi ro có thể có |
| --- | --- | --- |
| Nhỏ | Ít dữ liệu được prefetch; có thể giảm buffer và memory pressure | Nhiều lần fetch hơn, tăng round-trip và overhead |
| Trung bình | Cân bằng giữa memory và số lần fetch | Cần đo theo kích thước hàng và workload |
| Lớn | Có thể giảm số lần trao đổi và tăng throughput | Buffer lớn, memory tăng, dữ liệu có thể được đọc trước khi downstream cần |
| 0/default | Dùng chiến lược mặc định của driver | Không kiểm soát được hành vi cụ thể từ ứng dụng |

Đừng chọn fetch size chỉ dựa trên số hàng. Một hàng chứa vài cột số nhỏ khác xa một hàng chứa JSON lớn, text dài hoặc binary payload. Cần xem cả kích thước byte trung bình của hàng và số result set được xử lý đồng thời.

### Cách tìm điểm bắt đầu

Có thể bắt đầu benchmark với vài giá trị cách nhau rõ ràng, chẳng hạn 32, 128, 512 và driver default. Đây chỉ là tập giá trị thử nghiệm; không phải chuẩn chung. Với mỗi giá trị, đo:

- Thời gian đến hàng đầu tiên.
- Tổng thời gian đọc toàn bộ result set.
- Throughput hàng/giây.
- Heap usage và allocation rate.
- Số lần fetch/round-trip nếu driver expose metric hoặc log.
- Connection hold time và pool pending acquire.
- CPU của ứng dụng và database.

Chọn giá trị dựa trên workload thực tế và giới hạn latency/memory, không dựa trên một lần chạy duy nhất.

## 9. Kích thước hàng và bộ nhớ thực tế

Giả sử mỗi hàng sau decode và mapping chiếm trung bình khoảng 2 KB trong heap, 500 hàng prefetch có thể tương ứng khoảng 1 MB object payload, chưa tính overhead của object, buffer byte, metadata, queue và các publisher khác. Nếu mỗi hàng chứa một JSON document 100 KB, cùng fetch size 500 có thể tạo áp lực bộ nhớ lớn hơn nhiều.

Fetch size không giới hạn toàn bộ memory footprint của ứng dụng. Cần tính:

- Buffer ở network/protocol layer.
- Buffer của driver.
- `Row`/metadata và object sau mapping.
- Prefetch của Reactor operators.
- Queue do `flatMap` concurrency.
- Collection do `buffer`, `collectList` hoặc caching.
- Số query đang chạy đồng thời.

Ví dụ nếu mỗi request stream 10.000 hàng, có 20 request đồng thời và driver prefetch 500 hàng cho mỗi request, lượng dữ liệu được giữ có thể rất đáng kể. Tính toán thực tế cần đo trên driver và heap profiler; phép nhân số hàng chỉ là ước lượng ban đầu.

### Chọn cột cần thiết

Tránh `SELECT *` cho truy vấn stream lớn nếu downstream chỉ cần vài cột:

```sql
SELECT id, event_type, created_at
FROM event_log
WHERE tenant_id = :tenantId
ORDER BY id;
```

Giảm payload mỗi hàng giúp giảm network traffic, decode cost và heap allocation. Nếu truy vấn cần một trường JSON/binary lớn, chỉ lấy trường đó khi consumer thực sự cần.

## 10. Streaming result set không đồng nghĩa không dùng bộ nhớ

Khi driver hỗ trợ streaming, result set có thể được phát dần. Tuy nhiên, pipeline downstream vẫn có thể tích lũy dữ liệu:

```java
// Vẫn giữ toàn bộ kết quả trong một List.
return repository.findAll()
        .collectList();
```

Hoặc có thể tạo queue lớn bằng concurrency/prefetch cao:

```java
return repository.findAll()
        .flatMap(this::enrich, 64);
```

`flatMap` có thể có nhiều publisher con đồng thời và prefetch tùy operator. Nếu enrichment chậm, hàng chờ và kết quả đang chờ có thể tăng. Hãy điều chỉnh concurrency/prefetch riêng, đồng thời kiểm tra fetch size của driver.

Một pipeline có thể giữ bộ nhớ thấp hơn bằng cách xử lý tuần tự hoặc concurrency có giới hạn:

```java
return repository.findAll()
        .concatMap(this::processOne);
```

Nếu cần song song, chọn concurrency vừa phải và đo queue/heap. Fetch size không thay thế việc kiểm soát concurrency.

## 11. Fetch size và LIMIT/pagination

Nếu người dùng yêu cầu một trang dữ liệu, giới hạn số hàng ngay trong SQL:

```sql
SELECT id, name
FROM customer
WHERE status = :status
ORDER BY id
LIMIT :pageSize OFFSET :offset;
```

Không cần tăng fetch size lên hàng nghìn nếu query chỉ trả 20 hàng. Fetch size lớn hơn tổng số hàng không tạo thêm kết quả; chỉ có thể ảnh hưởng cách driver thực thi nếu nó có hỗ trợ.

### Duyệt dữ liệu lớn theo keyset

Với job cần đi qua toàn bộ bảng, keyset pagination có thể tránh offset sâu:

```sql
SELECT id, event_type, created_at
FROM event_log
WHERE id > :lastId
ORDER BY id
LIMIT :chunkSize;
```

Sau mỗi chunk, lưu `lastId` của hàng cuối và truy vấn tiếp. Index primary key hỗ trợ seek theo ID. Cách này giới hạn số hàng mỗi query và có thể giúp giải phóng connection giữa các chunk, tùy thiết kế pipeline.

Fetch size có thể vẫn hữu ích bên trong mỗi query chunk nếu driver hỗ trợ, nhưng khi `LIMIT` đã nhỏ, lợi ích có thể không đáng kể. Chọn giữa một cursor streaming dài và nhiều query chunk ngắn dựa trên yêu cầu snapshot consistency, thời gian giữ connection và khả năng phục hồi job.

## 12. Fetch size và transaction

Một số driver chỉ thực hiện cursor-based fetch khi connection ở trạng thái transaction hoặc khi auto-commit bị tắt. Đây là chi tiết driver-specific; không có một quy tắc chung áp dụng cho mọi R2DBC database.

Nếu driver yêu cầu transaction:

- Đảm bảo query chạy trong reactive transaction phù hợp.
- Không tự gọi `subscribe()` để tách query khỏi transaction context.
- Không giữ transaction lâu hơn cần thiết.
- Đọc hết result set hoặc hủy publisher đúng cách để cursor/resource được giải phóng.
- Kiểm tra isolation và snapshot semantics nếu dữ liệu thay đổi trong lúc stream.

Một transaction dài có thể giữ connection, lock hoặc snapshot lâu hơn; trên database MVCC, snapshot cũ kéo dài có thể làm tăng chi phí maintenance. Nếu job xử lý mỗi hàng chậm, việc giữ một cursor/transaction trong thời gian dài có thể ảnh hưởng pool và database.

### Đọc lâu và xử lý chậm

Ví dụ pipeline:

```java
return databaseClient.sql("SELECT id, payload FROM event_log ORDER BY id")
        .map((row, metadata) -> mapEvent(row))
        .all()
        .concatMap(event -> callSlowExternalService(event));
```

Nếu mỗi event cần gọi dịch vụ ngoài lâu, cursor/connection có thể được giữ trong suốt quá trình tiêu thụ. Cần cân nhắc đọc theo chunk, ghi checkpoint và đóng query trước khi thực hiện công việc bên ngoài lâu. Không nên giữ transaction database mở trong khi chờ HTTP service nếu không có yêu cầu nhất quán bắt buộc.

## 13. Cancellation và giải phóng tài nguyên

Subscriber có thể hủy stream do timeout, client disconnect hoặc chỉ lấy một phần dữ liệu. Driver cần nhận cancellation để dừng/đóng cursor hoặc giải phóng protocol resource theo khả năng hỗ trợ.

Ví dụ chỉ lấy 10 hàng đầu:

```java
return databaseClient.sql("SELECT id, payload FROM event_log ORDER BY id")
        .map((row, metadata) -> mapEvent(row))
        .all()
        .take(10);
```

`take(10)` hủy upstream sau khi đủ 10 phần tử. Tuy nhiên, việc server dừng đọc ngay lập tức hay driver đã prefetch thêm dữ liệu phụ thuộc driver. `fetchSize` nhỏ hơn có thể giảm lượng dữ liệu đọc trước trong một số driver, nhưng không thay thế cancellation.

Khi dùng R2DBC SPI trực tiếp, phải quản lý connection trên cả ba đường terminal: complete, error và cancel. `usingWhen` giúp khai báo cleanup bất đồng bộ. Với `DatabaseClient`/repository của Spring, framework quản lý resource theo lifecycle publisher; không tự đóng connection mà framework đang sở hữu.

## 14. Fetch size và connection pool

Một stream result set thường chiếm connection trong thời gian publisher còn hoạt động. Nếu mỗi subscriber giữ connection lâu, pool có thể cạn dù mỗi query không tạo lỗi.

Theo dõi:

- Số connection đang acquired.
- Số connection idle.
- Số request đang pending acquire.
- Thời gian acquire connection.
- Thời gian từ execute tới complete/cancel.
- Số stream đang mở đồng thời.
- Thời gian xử lý downstream sau mỗi row/chunk.

Fetch size lớn có thể giảm số lần fetch nhưng làm tăng prefetch; fetch size nhỏ có thể giảm buffer nhưng kéo dài query do nhiều lần lấy dữ liệu. Cả hai đều có thể tác động tới thời gian connection bị giữ, tùy driver và downstream.

Không tăng `maxSize` của pool chỉ để che việc stream giữ connection quá lâu. Trước hết xác định thời gian giữ connection, concurrency, query latency và tốc độ tiêu thụ. Nếu cần export rất dài, có thể tách job khỏi request/response và dùng worker có concurrency được giới hạn.

## 15. Kết hợp fetch size với `DatabaseClient`

`DatabaseClient` cung cấp API reactive để đọc kết quả thành `Flux`. Ví dụ thông thường:

```java
Flux<EventView> streamEvents(UUID tenantId) {
    return databaseClient.sql("""
                SELECT id, event_type, created_at
                FROM event_log
                WHERE tenant_id = :tenantId
                ORDER BY id
                """)
            .bind("tenantId", tenantId)
            .map((row, metadata) -> new EventView(
                    row.get("id", Long.class),
                    row.get("event_type", String.class),
                    row.get("created_at", LocalDateTime.class)
            ))
            .all();
}
```

`.all()` trả về `Flux` để tiêu thụ nhiều hàng. Bản thân API này không đồng nghĩa với một giá trị fetch size cụ thể. Nếu driver hỗ trợ fetch size, cần cấu hình statement qua API mà phiên bản Spring cung cấp hoặc dùng SPI trực tiếp.

### Filter statement ở DatabaseClient

Trong các phiên bản Spring Framework có `DatabaseClient.Builder.filter(StatementFilterFunction)`, có thể cấu hình:

```java
DatabaseClient client = DatabaseClient.builder()
        .connectionFactory(connectionFactory)
        .filter((statement, next) -> {
            statement.fetchSize(256);
            return next.execute(statement);
        })
        .build();
```

Đây là cấu hình áp dụng ở client đã tạo. Cần xác nhận API tồn tại trong đúng phiên bản Spring Framework và client đó được dùng bởi component cần kiểm soát. Nếu client này được truyền vào `R2dbcEntityTemplate`, template có thể dùng filter đó; repository factory cần được cấu hình theo cùng infrastructure nếu muốn áp dụng cho repository.

Không nên giả định annotation `@Query` có một thuộc tính `fetchSize` portable trên mọi phiên bản Spring Data R2DBC. Kiểm tra API cụ thể; nếu không có, dùng `DatabaseClient` filter hoặc SPI ở adapter phù hợp.

## 16. Kết hợp fetch size với repository

Repository method có thể trả `Flux<T>`:

```java
public interface EventRepository
        extends ReactiveCrudRepository<Event, Long> {

    Flux<Event> findByTenantIdOrderById(UUID tenantId);
}
```

API repository tập trung vào query/mapping và không phải lúc nào cũng expose fetch size trực tiếp trong method signature. Nếu cần fetch size riêng cho một query lớn:

- Kiểm tra xem phiên bản Spring Data R2DBC có cơ chế statement customization tương ứng không.
- Dùng một `DatabaseClient` đã cấu hình filter riêng cho truy vấn export.
- Dùng R2DBC SPI trong adapter chuyên biệt nếu cần kiểm soát chính xác statement.
- Giữ repository cho CRUD và truy vấn thông thường, tránh áp dụng fetch size lớn toàn cục nếu chỉ một số query cần.

Ví dụ adapter riêng:

```java
public interface EventExportReader {
    Flux<EventView> streamEvents(UUID tenantId, int fetchSize);
}
```

Service phụ thuộc vào abstraction `EventExportReader`, không cần biết driver hoặc connection management. Adapter triển khai bằng `DatabaseClient` filter hoặc SPI tùy khả năng driver. Cách này giúp logic nghiệp vụ không bị ràng buộc vào một API driver-specific.

## 17. Fetch size với nhiều result set

Một statement có thể trả một hoặc nhiều `Result` tùy câu lệnh/driver. Cần phân biệt:

- Số hàng trong một result set.
- Số result được phát bởi `Statement.execute()`.
- Fetch size áp dụng cho từng result set hay theo cơ chế riêng của driver.

Không giả định `fetchSize(n)` có nghĩa tối đa n hàng cho toàn bộ statement nếu statement có nhiều result set. Đọc tài liệu driver và xử lý `Result` theo đúng API.

Với truy vấn SELECT thông thường, thường có một result set. Với stored procedure hoặc nhiều statement/batch, semantics có thể phức tạp hơn. Nếu cần stream kết quả lớn từ stored procedure, hãy kiểm thử riêng và không suy diễn từ một SELECT đơn giản.

## 18. Fetch size và dữ liệu lớn như BLOB/CLOB/JSON

Khi mỗi hàng chứa payload lớn, số hàng trong một fetch batch không phản ánh đầy đủ dung lượng buffer. Ví dụ 100 hàng metadata nhỏ khác 100 hàng chứa ảnh hoặc JSON nhiều megabyte.

Các lưu ý:

- Chỉ chọn cột payload khi thực sự cần.
- Nếu driver hỗ trợ đọc LOB streaming, tìm hiểu API và lifecycle của LOB; không giả định mọi codec stream payload.
- Tránh map payload lớn thành object/byte array nếu downstream không cần giữ toàn bộ.
- Giới hạn số stream đồng thời.
- Đo peak heap và direct memory, không chỉ heap sau khi GC.
- Đặt timeout và cleanup khi client cancel giữa lúc đọc payload.

Fetch size nhỏ có thể giúp giảm số hàng prefetch, nhưng một hàng đơn lẻ rất lớn vẫn có thể tiêu thụ nhiều bộ nhớ. Cần kiểm soát cả kích thước payload và cách driver decode.

## 19. Đo lường để chọn fetch size

Không chọn fetch size dựa trên benchmark chỉ dùng `Flux.just(...)`; cần đo qua database và driver thật. Một kế hoạch benchmark:

1. Tạo dữ liệu với số hàng và kích thước cột gần production.
2. Chạy cùng một query và cùng thứ tự/index cho các giá trị fetch size khác nhau.
3. Đảm bảo pipeline downstream giống nhau, không một test dùng `collectList()` còn test kia stream từng hàng.
4. Đo thời gian đến hàng đầu tiên và thời gian hoàn tất toàn bộ.
5. Đo throughput, heap, direct memory, allocation, CPU và GC.
6. Quan sát connection pool, query duration và database load.
7. Lặp lại nhiều lần, gồm warm-up và workload concurrent.
8. Thử driver default để có baseline.
9. Xác nhận driver thực sự áp dụng fetch size, không chỉ nhận lời gọi API.
10. Chọn giá trị đáp ứng mục tiêu latency/memory, sau đó kiểm thử dưới tải gần production.

### Metrics nên so sánh

| Metric | Vì sao quan trọng |
| --- | --- |
| Time to first row | Ảnh hưởng cảm nhận ban đầu và thời gian bắt đầu xử lý |
| Total query/stream duration | Đo thời gian hoàn thành toàn bộ công việc |
| Rows per second | Đo throughput đọc |
| Peak heap/direct memory | Phát hiện buffer hoặc payload quá lớn |
| GC pause/allocation rate | Cho biết chi phí tạo object và áp lực GC |
| Fetch/round-trip count | Đánh giá overhead giao tiếp nếu driver expose được |
| Connection hold time | Đánh giá tác động tới pool |
| Pool pending acquire | Phát hiện thiếu connection khi stream lâu |
| Database CPU/I/O | Tránh tối ưu client nhưng làm server quá tải |

## 20. Kiểm thử fetch size

`TestPublisher` phù hợp để kiểm tra logic downstream về demand/cancellation, nhưng không chứng minh driver thật sự fetch theo từng đợt. Fetch size là behavior của R2DBC statement/driver và cần integration test với database tương ứng.

### Kiểm tra statement được cấu hình

Nếu dùng một wrapper/adapter tự quản lý statement, có thể unit test adapter bằng một `Statement` mock để xác nhận nó gọi `fetchSize(n)` trước `execute()`. Test này chỉ xác nhận lời gọi API, không xác nhận driver thực thi fetch theo đợt.

Ví dụ ý tưởng:

```java
verify(statement).fetchSize(256);
verify(statement).execute();
```

Không mock toàn bộ driver rồi tuyên bố memory đã được giới hạn. Hành vi buffer/cursor chỉ có thể xác nhận bằng driver thật.

### Integration test với driver thật

Nên kiểm tra:

- Query trả đủ hàng khi fetch size nhỏ hơn tổng số hàng.
- Mapping và thứ tự kết quả không thay đổi.
- Publisher có thể tiêu thụ hết result set.
- Cancellation giải phóng cursor/connection theo khả năng driver.
- Transaction boundary phù hợp nếu driver yêu cầu cursor trong transaction.
- Connection pool không giữ connection sau complete/error/cancel.
- Driver log/metric hoặc server observation cho thấy cơ chế fetch mong đợi nếu có công cụ quan sát.

Không phải driver nào cũng expose metric số lần fetch. Nếu không quan sát được trực tiếp, dùng tài liệu driver, test tải và memory profile để đánh giá, nhưng nêu rõ giới hạn bằng chứng.

## 21. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Gọi `fetchSize` nhưng heap vẫn tăng | Driver bỏ qua hint, buffer khác hoặc downstream tích lũy dữ liệu | Xác minh driver và loại bỏ `collectList`/queue lớn |
| Kết quả vẫn bị tải toàn bộ | Driver không dùng cursor/streaming hoặc cấu hình thiếu | Kiểm tra tài liệu và option của driver |
| Fetch size nhỏ làm query chậm | Quá nhiều lần fetch/round-trip | Benchmark giá trị lớn hơn và đo network latency |
| Fetch size lớn gây memory pressure | Nhiều hàng/payload được prefetch | Giảm fetch size, concurrency hoặc số cột |
| Cursor không hoạt động | Driver yêu cầu transaction hoặc connection option riêng | Kiểm tra điều kiện cursor của driver |
| Connection pool cạn | Stream dài giữ connection trong lúc downstream xử lý chậm | Rút ngắn stream, chia chunk hoặc giới hạn concurrency |
| Timeout giữa result set | Query/fetch chậm hoặc deadline quá ngắn | Đặt timeout phù hợp và xử lý cancellation |
| Cancel nhưng tài nguyên chưa được giải phóng | Driver/adapter cleanup sai hoặc SPI trực tiếp không quản lý `usingWhen` | Kiểm tra driver, cleanup complete/error/cancel |
| `limitRate` không thay đổi fetch behavior | Reactor demand khác statement fetch size | Cấu hình driver statement riêng |
| `LIMIT` lớn vẫn tiêu thụ nhiều memory | Tổng số hàng trả về vẫn lớn | Giảm LIMIT, phân trang hoặc stream/chunk |
| `collectList()` vẫn gây OOM | Toàn bộ result set được giữ trong heap | Xử lý từng row/chunk thay vì gom hết |
| Repository không có thuộc tính fetch size | Abstraction không expose statement hint trong API đó | Dùng DatabaseClient filter/SPI adapter theo version |
| API filter không biên dịch | Spring Framework version chưa có API đó hoặc signature khác | Kiểm tra Javadoc đúng version; dùng SPI/driver config |

## 22. Quy trình điều chỉnh fetch size

1. Xác định truy vấn có result set lớn và cần stream hay chỉ cần một trang nhỏ.
2. Dùng SQL `LIMIT`/keyset pagination nếu nghiệp vụ không cần toàn bộ result set trong một lần.
3. Kiểm tra R2DBC driver có hỗ trợ `Statement.fetchSize(int)` hay cơ chế fetch riêng không.
4. Kiểm tra yêu cầu transaction, cursor, auto-commit và connection option của driver.
5. Chọn điểm cấu hình: SPI trực tiếp, `DatabaseClient` statement filter nếu phiên bản Spring hỗ trợ, hoặc API driver-specific.
6. Tránh tích lũy toàn bộ kết quả bằng `collectList()` nếu dữ liệu lớn.
7. Giới hạn downstream concurrency/prefetch và số stream đồng thời.
8. Đo fetch size nhỏ, trung bình, lớn và driver default trên dữ liệu thực tế.
9. Kiểm tra time-to-first-row, throughput, memory, round-trip và connection hold time.
10. Integration test complete/error/cancel và xác nhận cleanup.
11. Ghi rõ driver/server version cùng giá trị cấu hình để có thể tái lập kết quả.

## 23. Ghi nhớ

- `Statement.fetchSize(int)` là hint của R2DBC SPI về số hàng lấy trong mỗi đợt; driver có thể hỗ trợ hoặc bỏ qua.
- Fetch size không giới hạn tổng số hàng; `LIMIT` mới giới hạn tổng result set.
- Fetch size khác Reactive Streams demand, `limitRate`, `buffer`, `collectList` và batch ghi.
- Không giả định fetch size 256 đồng nghĩa database gửi đúng 256 hàng mỗi packet hoặc heap chỉ giữ 256 row.
- Hành vi cursor/streaming, transaction requirement và connection option phụ thuộc driver/database/version.
- Fetch size nhỏ có thể giảm prefetch nhưng tăng round-trip; fetch size lớn có thể tăng throughput nhưng tốn buffer.
- Kích thước hàng và payload JSON/BLOB/CLOB quan trọng không kém số hàng.
- `collectList()` vẫn tích lũy toàn bộ kết quả dù driver fetch theo đợt.
- `limitRate` điều chỉnh demand trong Reactor, không tự gọi `Statement.fetchSize`.
- Với Spring `DatabaseClient`, chỉ dùng `StatementFilterFunction` nếu phiên bản Spring hỗ trợ và client đã cấu hình thực sự được dùng bởi component cần điều chỉnh.
- Khi dùng R2DBC SPI trực tiếp trong Spring, lấy connection qua `ConnectionFactoryUtils` và release đúng cả complete/error/cancel.
- Streaming result set có thể giữ connection lâu; cần theo dõi pool, transaction duration và tốc độ downstream.
- Dùng integration test với driver/database thật để xác nhận fetch behavior; TestPublisher chỉ kiểm tra tín hiệu ở tầng reactive pipeline.
- Benchmark trên dữ liệu gần production, đo time-to-first-row, throughput, heap, GC, round-trip và connection hold time trước khi chọn giá trị.

Điều chỉnh fetch size chỉ có ý nghĩa khi driver thực sự hỗ trợ cách lấy result set theo đợt. Hãy bắt đầu từ nhu cầu truy vấn, kiểm tra khả năng của driver, cấu hình tại statement phù hợp và giữ pipeline downstream không tích lũy dữ liệu không cần thiết. Cuối cùng, đo trên đúng database/driver production để chọn giá trị cân bằng giữa bộ nhớ, round-trip, throughput và thời gian giữ connection.
