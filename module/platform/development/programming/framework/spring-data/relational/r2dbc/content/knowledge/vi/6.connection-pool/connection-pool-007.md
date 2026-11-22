# Nhận diện cạn pool, rò rỉ kết nối và truy vấn giữ kết nối lâu

Connection pool giúp ứng dụng R2DBC tái sử dụng các kết nối database thay vì tạo một kết nối vật lý mới cho mỗi thao tác. Pool có giới hạn: khi mọi connection đều đang được sử dụng, yêu cầu mới phải chờ một connection được trả về hoặc chờ đến khi hết thời gian acquire.

Hiện tượng cạn pool thường biểu hiện bằng request chậm, hàng đợi acquire tăng và lỗi timeout lấy connection. Tuy nhiên, **pool cạn là triệu chứng, không phải nguyên nhân gốc**. Nó có thể đến từ truy vấn chậm, transaction kéo dài, luồng reactive tiêu thụ dữ liệu chậm, mức đồng thời quá cao, database quá tải hoặc connection bị giữ mà không được giải phóng.

Muốn xử lý đúng, cần đo thời gian lấy connection, thời gian thực thi SQL và tổng thời gian connection được giữ. Ba khoảng thời gian này giúp phân biệt pool thiếu dung lượng với truy vấn lâu hoặc rò rỉ connection.

## 1. Vòng đời của một connection trong R2DBC

Một thao tác dữ liệu thường đi qua các bước sau:

1. Ứng dụng subscribe vào publisher từ repository hoặc `DatabaseClient`.
2. Hạ tầng R2DBC yêu cầu một connection từ `ConnectionFactory` hoặc pool.
3. Pool cấp một connection đang rảnh hoặc tạo connection mới nếu còn trong giới hạn.
4. Driver gửi SQL tới database và nhận kết quả.
5. Kết quả được ánh xạ thành entity hoặc dữ liệu mà ứng dụng cần.
6. Khi thao tác hoàn tất, thất bại hoặc bị hủy, hạ tầng giải phóng connection về pool.

Với connection lấy từ pool, lời gọi `Connection.close()` thường có nghĩa là trả connection về pool để tái sử dụng; không nhất thiết đóng kết nối vật lý tới database ngay lập tức.

Repository và `DatabaseClient` quản lý vòng đời connection cho các thao tác thông thường. Ứng dụng cần chú ý hơn khi tự gọi `ConnectionFactory.create()`, mở transaction thủ công hoặc giữ một publisher dài hạn.

### 1.1. Connection được giữ trong bao lâu?

Thời gian thực thi SQL và thời gian giữ connection có thể khác nhau. Ví dụ, một câu SELECT có thể chạy trong 20 ms nhưng connection vẫn được giữ lâu hơn nếu:

- Kết quả được phát dần và subscriber xử lý từng phần rất chậm.
- Pipeline còn các bước nằm trong cùng transaction.
- Ứng dụng gọi thêm dịch vụ HTTP trước khi transaction kết thúc.
- Code thủ công chưa đóng connection sau khi đọc dữ liệu.
- Publisher không hoàn tất và cũng không được cancel.

Vì vậy, truy vấn chạy nhanh không đảm bảo connection được trả về pool nhanh.

### 1.2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa |
| --- | --- |
| Allocated connection | Connection pool đã tạo hoặc đang quản lý, gồm cả connection đang rảnh và đang được mượn |
| Acquired connection | Connection hiện được ứng dụng mượn từ pool để thực hiện công việc |
| Idle connection | Connection đang nằm trong pool và có thể được cấp cho yêu cầu mới |
| Pending acquire | Yêu cầu đang chờ pool cấp connection |
| Acquire time | Thời gian chờ từ lúc yêu cầu connection đến lúc nhận được connection |
| Hold time | Tổng thời gian connection ở trạng thái được ứng dụng mượn |
| Query time | Thời gian database thực thi hoặc trả kết quả truy vấn, tùy cách đo |

Các chỉ số này có thể được trình bày bằng tên metric khác nhau tùy phiên bản R2DBC Pool và hệ thống metrics. Khi phân tích, hãy đối chiếu ý nghĩa của metric thay vì chỉ dựa vào tên hiển thị.

## 2. Nhận diện pool đang cạn

Các dấu hiệu phổ biến gồm:

- Request database bắt đầu chậm dù số lượng request đến không tăng rõ rệt.
- Thời gian acquire connection tăng và xuất hiện hàng đợi chờ.
- Pool thường xuyên không còn idle connection.
- Số acquired connection chạm gần `max-size` trong một khoảng thời gian dài.
- Lỗi timeout khi chờ connection hoặc không thể lấy connection mới.
- Latency API tăng theo tải, sau đó throughput không tăng dù số request tiếp tục tăng.

Một snapshot như `acquired = max-size` chưa đủ chứng minh có leak. Trong thời gian tải cao, tất cả connection có thể đang được dùng hợp lệ. Cần quan sát xu hướng theo thời gian, thời lượng giữ connection và số pending acquire.

### 2.1. Các chỉ số pool cần theo dõi

Nếu hệ thống metrics cung cấp số liệu của R2DBC Pool, hãy theo dõi tối thiểu:

| Chỉ số | Điều cần quan sát |
| --- | --- |
| `allocatedSize` | Tổng connection pool đang quản lý; so với giới hạn tối đa |
| `acquiredSize` | Số connection đang được mượn; tăng liên tục hoặc giữ sát giới hạn là tín hiệu cần điều tra |
| `idleSize` | Số connection đang rảnh; thường xuyên bằng 0 khi có tải có thể cho thấy pool chịu áp lực |
| `pendingAcquireSize` | Số yêu cầu đang chờ; tăng và kéo dài cho thấy nhu cầu đang vượt khả năng cấp connection tức thời |

Các metric của pool có thể được expose thông qua Micrometer hoặc hệ thống quan sát mà ứng dụng tích hợp. Việc bật và tên metric cụ thể phụ thuộc phiên bản Spring Boot, R2DBC Pool và cấu hình metrics. Hãy kiểm tra tài liệu của phiên bản đang chạy.

Đừng chỉ nhìn số connection đang mở ở database. Pool có thể giữ sẵn connection idle, nên số session database cao không đồng nghĩa tất cả đều đang được sử dụng bởi request.

### 2.2. Đọc một tình huống mẫu

Giả sử pool có `max-size = 20` và metrics cho thấy:

| Chỉ số | Giá trị quan sát |
| --- | ---: |
| Allocated | 20 |
| Acquired | 20 |
| Idle | 0 |
| Pending acquire | 35 |

Điều này cho biết toàn bộ 20 connection đã được mượn và còn 35 yêu cầu đang chờ. Nó chưa cho biết nguyên nhân là truy vấn chậm, transaction kéo dài hay leak. Bước tiếp theo là đo thời gian giữ connection và đối chiếu với hoạt động database.

Nếu `acquired` giảm nhanh sau khi tải kết thúc và pending được giải phóng, có thể pool chỉ đang chịu một đợt tải đỉnh. Nếu acquired vẫn ở mức cao sau khi request đã kết thúc hoặc không giảm trong thời gian dài, cần điều tra đường đi giải phóng connection và các transaction còn mở.

## 3. Phân biệt cạn pool, leak và truy vấn lâu

Ba vấn đề này có thể tạo ra biểu hiện gần giống nhau nhưng cần cách xử lý khác nhau.

| Dấu hiệu | Pool thiếu dung lượng do tải | Connection bị giữ/rò rỉ | Truy vấn hoặc transaction kéo dài |
| --- | --- | --- | --- |
| Acquired | Tăng theo tải và giảm khi tải hạ | Có thể tăng dần rồi không giảm về mức bình thường | Tăng trong lúc truy vấn hoặc transaction chạy |
| Pending acquire | Tăng ở giờ cao điểm | Có thể tăng dù lưu lượng request không cao | Tăng khi nhiều truy vấn cùng chờ connection |
| Query duration | Thường ổn định nếu database đáp ứng tốt | Có thể không có query đang chạy tương ứng với connection bị giữ | Cao, hoặc database đang chờ lock/I/O |
| Hold time | Phù hợp với thời gian xử lý thông thường | Bất thường dài hoặc không kết thúc | Dài tương ứng với query, transaction hoặc stream |
| Khi tải giảm | Pool thường hồi phục | Acquired có thể vẫn bị giữ | Hồi phục sau khi query/transaction hoàn tất hoặc timeout |
| Hướng xử lý | Đo tải, giới hạn concurrency, cân nhắc sizing | Sửa vòng đời acquire/release và cancellation | Tối ưu SQL, lock, transaction và cách tiêu thụ kết quả |

Không phải mọi trường hợp đều phân loại được chỉ từ một biểu đồ. Một truy vấn chậm có thể làm cạn pool; khi đó hiện tượng cạn pool là hệ quả của thời gian giữ connection dài.

## 4. Rò rỉ connection trong ứng dụng R2DBC

Rò rỉ connection xảy ra khi ứng dụng mượn connection nhưng không trả lại pool sau khi công việc kết thúc. Khi nhiều connection bị giữ như vậy, pool không còn connection để cấp cho request mới.

### 4.1. Tự acquire connection nhưng không release

Một lỗi phổ biến là gọi trực tiếp `ConnectionFactory.create()` rồi chỉ xử lý trường hợp thành công, quên giải phóng khi xảy ra exception hoặc cancellation.

Ví dụ minh họa cách quản lý thủ công an toàn với Reactor `usingWhen`:

```java
import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import reactor.core.publisher.Mono;

public Mono<Integer> selectOne(ConnectionFactory connectionFactory) {
    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> Mono.from(connection.createStatement("SELECT 1").execute())
                    .flatMap(result -> Mono.from(result.map(
                            (row, metadata) -> row.get(0, Integer.class)))),
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

`usingWhen` đăng ký thao tác cleanup khi publisher hoàn tất, phát sinh lỗi hoặc bị cancel. Trong code thực tế, cần bổ sung import và xử lý kiểu dữ liệu theo truy vấn của ứng dụng.

Với các thao tác CRUD thông thường, ưu tiên repository hoặc `DatabaseClient` vì Spring quản lý việc acquire và release connection. Chỉ dùng API connection cấp thấp khi thật sự cần kiểm soát trực tiếp.

### 4.2. Chỉ cleanup khi thành công

Một mẫu code dễ gây lỗi là chỉ gọi `close()` trong nhánh hoàn tất bình thường. Nếu truy vấn ném lỗi, mapping thất bại hoặc subscriber cancel, nhánh cleanup có thể không chạy.

Khi tự quản lý resource bất đồng bộ, phải xử lý đủ ba đường đi:

- Hoàn tất bình thường.
- Kết thúc bằng lỗi.
- Bị hủy trước khi hoàn tất.

`usingWhen` của Reactor phù hợp với resource có thao tác cleanup bất đồng bộ như connection R2DBC. Không nên dùng `doFinally` để gọi `close()` rồi bỏ qua publisher cleanup, vì `doFinally` không chờ thao tác cleanup bất đồng bộ hoàn tất.

### 4.3. Lưu connection trong field hoặc chia sẻ giữa request

Không nên lấy một connection rồi lưu trong field của singleton service để dùng lại cho nhiều request. Connection được mượn từ pool thuộc về một thao tác hoặc transaction cụ thể. Chia sẻ connection đồng thời có thể gây lỗi transaction, cạnh tranh trạng thái và không trả connection về pool đúng thời điểm.

Hãy inject `ConnectionFactory`, repository hoặc `DatabaseClient`, sau đó để từng thao tác lấy connection theo vòng đời của publisher.

### 4.4. Publisher không được tiêu thụ hoặc không kết thúc

Reactive publisher là lazy: việc gọi repository thường chỉ tạo mô tả công việc; thao tác bắt đầu khi có subscription. Một khi đã subscribe và connection được acquire, publisher cần đi đến completion, error hoặc cancellation để tài nguyên được giải phóng.

Một luồng streaming kéo dài hoặc subscriber không tiêu thụ dữ liệu có thể khiến connection bị giữ lâu. Đây thường là connection bị giữ quá lâu hơn là leak do quên `close()` thủ công, nhưng tác động lên pool tương tự.

Đảm bảo các subscription có chủ sở hữu rõ ràng. Tránh tạo subscription fire-and-forget mà không quản lý cancellation, timeout hoặc vòng đời công việc.

### 4.5. Kiểm tra cancellation và timeout

Khi client ngắt kết nối hoặc pipeline bị timeout, cancellation cần truyền tới các bước reactive để driver và framework có thể dọn dẹp resource. Nếu có adapter hoặc code tùy chỉnh nuốt tín hiệu cancel, quá trình giải phóng có thể bị chậm hoặc không xảy ra như mong đợi.

Khi điều tra, thử các tình huống:

- Client đóng kết nối HTTP trong lúc truy vấn đang chạy.
- Request timeout trước khi database trả kết quả.
- Publisher gặp lỗi trong lúc đang đọc nhiều dòng.
- Một bước `flatMap` bị hủy khi pipeline cha bị cancel.

Quan sát acquired connection có giảm về mức ban đầu sau các tình huống này không.

## 5. Truy vấn giữ connection lâu

Một truy vấn lâu giữ connection trong suốt thời gian thao tác database cần connection. Nếu nhiều truy vấn như vậy chạy đồng thời, pool có thể cạn dù ứng dụng không có leak.

### 5.1. Truy vấn SQL chạy lâu

Các nguyên nhân thường gặp:

- Thiếu index hoặc index không phù hợp với điều kiện lọc và sắp xếp.
- Quét quá nhiều dòng hoặc join trên tập dữ liệu lớn.
- Truy vấn N+1 tạo nhiều round trip tới database.
- Database đang thiếu CPU, bộ nhớ, I/O hoặc connection.
- Truy vấn phải chờ lock do transaction khác giữ tài nguyên.
- Kế hoạch thực thi thay đổi sau khi dữ liệu hoặc statistics thay đổi.

Hãy đo thời gian truy vấn ở database và xem execution plan bằng công cụ của database. Không nên kết luận pool quá nhỏ trước khi biết SQL có thực thi hiệu quả hay không.

### 5.2. Transaction mở quá lâu

Trong transaction reactive, connection thường được giữ cho tới khi publisher thuộc transaction hoàn tất. Nếu transaction bao trùm nhiều bước không cần thiết, connection bị giữ trong cả khoảng thời gian đó.

Ví dụ thiết kế cần tránh:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .flatMap(saved -> inventoryClient.reserve(saved.getId())
                    .thenReturn(saved));
}
```

Trong ví dụ này, transaction có thể vẫn mở trong lúc ứng dụng chờ dịch vụ inventory qua HTTP. Nếu dịch vụ đó chậm, connection database cũng bị giữ lâu hơn cần thiết.

Nên giới hạn transaction vào phần thao tác database cần tính nguyên tử. Có thể tách phần lưu dữ liệu và lời gọi dịch vụ thành các bước riêng:

```java
@Service
class OrderWriter {

    private final OrderRepository repository;

    OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Order> save(Order order) {
        return repository.save(order);
    }
}

@Service
class OrderService {

    private final OrderWriter writer;
    private final InventoryClient inventoryClient;

    OrderService(OrderWriter writer, InventoryClient inventoryClient) {
        this.writer = writer;
        this.inventoryClient = inventoryClient;
    }

    public Mono<Order> createOrder(Order order) {
        return writer.save(order)
                .flatMap(saved -> inventoryClient.reserve(saved.getId())
                        .thenReturn(saved));
    }
}
```

Trong cấu trúc này, `OrderWriter` là một bean riêng để lời gọi qua Spring proxy áp dụng transaction. Publisher từ `save()` hoàn tất transaction trước khi `flatMap` bên ngoài gọi inventory. Với nghiệp vụ cần đảm bảo nhất quán giữa database và dịch vụ bên ngoài, hãy thiết kế outbox, saga hoặc cơ chế bù trừ phù hợp; tách transaction không tự giải quyết tính nhất quán phân tán.

### 5.3. Subscriber xử lý kết quả quá chậm

Với một truy vấn trả về `Flux<T>`, kết quả có thể được tiêu thụ dần. Nếu mỗi phần tử phải qua xử lý CPU nặng, gọi dịch vụ khác hoặc chờ client nhận dữ liệu, connection có thể được giữ trong suốt thời gian stream còn mở.

Ví dụ, API xuất dữ liệu hàng triệu dòng trực tiếp cho client chậm có thể giữ connection rất lâu. Cân nhắc:

- Phân trang theo key hoặc cursor và hoàn tất từng truy vấn nhỏ.
- Giới hạn số bản ghi trả về và thời gian sống của stream.
- Chuyển công việc xuất dữ liệu sang job nền, ghi kết quả ra file/object storage rồi cho client tải sau.
- Tách xử lý CPU hoặc gọi dịch vụ ngoài khỏi transaction database.

Không nên `collectList()` một tập dữ liệu rất lớn chỉ để tránh stream lâu nếu điều đó làm tăng mạnh bộ nhớ. Chọn cách đọc phù hợp với kích thước dữ liệu và yêu cầu nghiệp vụ.

### 5.4. Concurrency trong pipeline quá cao

Toán tử `flatMap` có thể subscribe nhiều publisher con đồng thời. Nếu mỗi publisher con thực hiện một truy vấn R2DBC, một request có thể dùng nhiều connection hoặc tạo áp lực acquire lớn hơn dự kiến.

Ví dụ:

```java
Flux.fromIterable(customerIds)
        .flatMap(customerRepository::findById);
```

Với danh sách lớn, hãy giới hạn mức đồng thời:

```java
Flux.fromIterable(customerIds)
        .flatMap(customerRepository::findById, 8);
```

Giá trị `8` chỉ là ví dụ. Chọn concurrency dựa trên kích thước pool, số request đồng thời, năng lực database và số truy vấn khác mà ứng dụng đang thực hiện. Giới hạn concurrency trong một pipeline không tự giới hạn tổng concurrency của toàn bộ ứng dụng.

## 6. Quy trình điều tra khi pool cạn

Khi có cảnh báo pool exhaustion, nên điều tra theo trình tự để tìm ra đoạn thời gian connection bị giữ.

### Bước 1: Xác nhận pool thực sự bị nghẽn

Thu thập cùng một khoảng thời gian các số liệu:

- `acquiredSize`, `allocatedSize`, `idleSize` và `pendingAcquireSize`.
- Số request, throughput và latency p50/p95/p99.
- Số lỗi timeout khi acquire connection.
- Số instance ứng dụng và cấu hình `max-size` của mỗi instance.

Nếu acquired chạm giới hạn, idle bằng 0 và pending tăng, pool đang thiếu connection sẵn sàng tại thời điểm đó. Ghi nhận thời điểm bắt đầu và kết thúc để đối chiếu với log ứng dụng và database.

### Bước 2: Tách thời gian acquire, query và hold

Đo riêng ba khoảng:

1. **Acquire latency:** thời gian chờ connection từ pool.
2. **Query latency:** thời gian gửi SQL và nhận kết quả từ database.
3. **Hold duration:** thời gian từ lúc acquire đến lúc release connection.

Một số cách diễn giải:

- Acquire tăng, query và hold vẫn bình thường: có thể tải đồng thời vượt sức chứa tức thời hoặc pool quá nhỏ so với mức concurrency.
- Query tăng và hold tăng cùng lúc: điều tra SQL, database, lock và network.
- Query ngắn nhưng hold dài: điều tra transaction, stream, subscriber chậm hoặc code giữ connection ngoài thao tác SQL.
- Request đã hoàn tất nhưng acquired không giảm: kiểm tra cleanup, cancellation và các transaction còn mở.

Hãy đảm bảo các phép đo dùng cùng định nghĩa thời gian. Một số công cụ đo query đến khi nhận metadata, trong khi công cụ khác đo đến khi toàn bộ rows được tiêu thụ.

### Bước 3: Kiểm tra database đang làm gì

Database có thể cho biết session nào đang chạy query, chờ lock hoặc ở trạng thái transaction chưa kết thúc. Cách xem phụ thuộc database và quyền quan sát được cấp.

Ví dụ với PostgreSQL, có thể xem các session hoạt động trong database hiện tại:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle'
ORDER BY query_start;
```

Các trạng thái như `active` hoặc `idle in transaction` cần được đọc cùng `wait_event`, thời lượng transaction và log ứng dụng. Một session `idle in transaction` có thể cho thấy transaction đã mở nhưng ứng dụng đang chờ bước tiếp theo hoặc chưa kết thúc transaction.

Để tìm blocker trong PostgreSQL, có thể xem `pg_blocking_pids(pid)` cho các session đang chờ lock. Truy vấn quan sát cần quyền phù hợp và cú pháp ở đây chỉ áp dụng cho PostgreSQL; MySQL, SQL Server và Oracle có view chẩn đoán riêng.

### Bước 4: Đối chiếu trace và log ứng dụng

Tìm request hoặc trace ID tương ứng với thời điểm pool bị nghẽn. Ghi nhận:

- Repository method hoặc câu SQL nào được gọi.
- Thời điểm bắt đầu transaction và thời điểm kết thúc.
- Có lời gọi HTTP, message broker hoặc xử lý CPU nào nằm giữa hai mốc không.
- Publisher có hoàn tất, phát lỗi hoặc bị cancel không.
- Có thao tác tự acquire connection nào trong code không.

Không log mật khẩu, thông tin nhạy cảm hoặc toàn bộ dữ liệu SQL có thể chứa thông tin cá nhân. Khi bật log SQL hoặc bind parameter, hãy giới hạn môi trường và thời gian sử dụng.

### Bước 5: Kiểm tra tình huống lỗi và cancellation

Thử tái hiện với timeout, client disconnect, lỗi mapping và tải đồng thời. Sau mỗi tình huống, xác nhận số acquired connection giảm về mức nền. Nếu chỉ có sự cố khi publisher bị cancel, xem lại code quản lý resource và các adapter reactive.

### Bước 6: Chỉ điều chỉnh pool sau khi hiểu nguyên nhân

Sau khi loại trừ leak, SQL chậm và transaction dài, mới đánh giá lại `max-size`, mức concurrency và số instance. Tăng pool mà không kiểm tra database có thể chỉ chuyển hàng đợi từ ứng dụng xuống database.

## 7. Cấu hình pool và timeout

Spring Boot có thể cấu hình R2DBC Pool qua các thuộc tính `spring.r2dbc.pool.*` khi dependency pool phù hợp có mặt và pooling được bật theo phiên bản đang dùng.

Ví dụ:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: shop_app
    password: ${DB_PASSWORD}
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-acquire-time: 2s
      max-create-connection-time: 5s
      max-idle-time: 30m
      max-life-time: 2h
```

Đây là cấu hình minh họa, không phải giá trị khuyến nghị cho mọi ứng dụng. Tên property, kiểu duration, điều kiện bật pool và dependency cần thiết có thể khác theo phiên bản Spring Boot. Hãy kiểm tra configuration metadata và tài liệu phiên bản dự án trước khi áp dụng.

### 7.1. Ý nghĩa các thuộc tính thường gặp

| Thuộc tính | Mục đích | Lưu ý |
| --- | --- | --- |
| `initial-size` | Số connection khởi tạo ban đầu | Giá trị lớn làm tăng số kết nối lúc startup |
| `max-size` | Số connection tối đa pool quản lý | Phải tính trên tất cả instance ứng dụng và giới hạn database |
| `max-acquire-time` | Thời gian tối đa chờ lấy connection | Giúp request thất bại có giới hạn khi pool nghẽn; không sửa nguyên nhân nghẽn |
| `max-create-connection-time` | Thời gian tối đa để tạo connection mới | Hữu ích khi database hoặc network không phản hồi |
| `max-idle-time` | Thời gian connection ở trạng thái idle trước khi bị loại bỏ theo chính sách pool | Cân nhắc idle timeout của database hoặc hạ tầng mạng |
| `max-life-time` | Tuổi thọ tối đa của connection trong pool | Có thể giúp luân chuyển connection cũ; không thay thế xử lý leak |

### 7.2. Chọn `max-size` dựa trên dữ liệu

Một ước lượng ban đầu có thể dùng định luật Little:

\[
N_{avg} \approx \lambda \times T_{hold}
\]

Trong đó:

- \(N_{avg}\) là số connection trung bình đang được mượn.
- \(\lambda\) là số thao tác database mỗi giây.
- \(T_{hold}\) là thời gian giữ connection trung bình tính bằng giây.

Ví dụ, ứng dụng thực hiện 80 thao tác database mỗi giây và mỗi thao tác giữ connection trung bình 0,05 giây:

\[
N_{avg} \approx 80 \times 0.05 = 4
\]

Con số 4 chỉ là mức trung bình ước lượng. Khi chọn pool thực tế, cần thêm headroom cho burst, p95/p99, transaction dài, số thao tác đồng thời trên một request và các workload khác. Đo tải thực tế trước khi quyết định.

Đặc biệt, `max-size` thường áp dụng cho từng instance. Nếu có 6 replica và mỗi replica có `max-size = 20`, tổng khả năng cấp connection của dịch vụ có thể lên tới 120 connection. Hãy cộng thêm worker nền, migration tool, ứng dụng khác và connection dành cho quản trị trước khi so với giới hạn database.

### 7.3. Đặt timeout theo ngân sách request

`max-acquire-time` nên phù hợp với timeout tổng thể của request. Nếu request chỉ được phép chạy 2 giây nhưng acquire có thể chờ 30 giây, ứng dụng sẽ giữ tài nguyên và tạo hàng đợi vô ích.

Phân bổ timeout theo từng tầng: chờ pool, thực thi SQL, gọi dịch vụ ngoài và tổng request. Cần tránh retry dồn dập khi pool đang nghẽn vì retry làm tăng thêm nhu cầu connection.

Tăng `max-acquire-time` có thể giảm lỗi timeout nhìn thấy trong ngắn hạn nhưng khiến request chờ lâu hơn. Tăng `max-size` có thể giúp khi pool thực sự quá nhỏ, nhưng cũng có thể làm database quá tải. Cả hai thay đổi phải dựa trên metrics và giới hạn database.

## 8. Các biện pháp giảm thời gian giữ connection

Một số biện pháp thường đem lại hiệu quả rõ rệt:

1. Tối ưu SQL, index, join và execution plan để giảm query duration.
2. Giữ transaction ngắn, chỉ bao quanh các thao tác cần tính nguyên tử.
3. Không gọi HTTP, gửi message hoặc chờ tác vụ CPU lâu trong transaction database.
4. Giới hạn concurrency của các pipeline có nhiều truy vấn con.
5. Phân trang hoặc giới hạn kết quả khi dữ liệu lớn.
6. Đảm bảo subscriber tiêu thụ stream có timeout và cancellation rõ ràng.
7. Dùng repository hoặc `DatabaseClient` cho thao tác thông thường để framework quản lý connection.
8. Dùng `usingWhen` khi phải tự acquire resource có cleanup bất đồng bộ.
9. Theo dõi connection pool và database cùng lúc để phát hiện vấn đề trước khi request timeout hàng loạt.

## 9. Kiểm thử khả năng chịu tải và rò rỉ

Không nên đợi production mới phát hiện pool exhaustion. Có thể thiết kế kiểm thử tải và kiểm thử lỗi có kiểm soát.

### 9.1. Kiểm thử tải đồng thời

Tăng dần số request đồng thời và ghi nhận:

- Throughput và latency p50/p95/p99.
- Acquire latency và pending acquire.
- Acquired, idle và allocated connection.
- Query duration, lock wait và database CPU.
- Số lỗi timeout và tỷ lệ request thành công.

Tải thử nên giống hành vi production: cùng kích thước dữ liệu, cùng loại query, transaction và tỷ lệ request đọc/ghi. Một benchmark chỉ chạy `SELECT 1` không phản ánh được workload thực tế.

### 9.2. Kiểm thử lỗi và cancel

Tạo các tình huống có chủ đích trong môi trường test:

- Hủy HTTP request trong lúc query đang chạy.
- Làm một bước mapping phát sinh exception.
- Cho dịch vụ ngoài phản hồi chậm trong luồng có transaction để quan sát hold time.
- Gửi tập dữ liệu lớn qua `Flux` với subscriber tiêu thụ chậm.
- Tạo burst request vượt quá `max-size` để quan sát pending acquire và timeout.

Sau mỗi lượt, đợi các thao tác đã kết thúc và xác nhận acquired connection trở về mức nền. Nếu acquired giữ nguyên dù không còn request tương ứng, hãy điều tra cleanup và transaction còn mở.

### 9.3. Dùng kiểm thử tích hợp với database thật

Kiểm thử bằng database thật hoặc Testcontainers giúp phát hiện khác biệt về driver, lock, kiểu dữ liệu và hành vi transaction. Cần dùng driver R2DBC tương thích và cấu hình pool nhỏ trong một số bài test để dễ quan sát việc acquire/release.

Không nên chỉ mock repository nếu mục tiêu là kiểm tra vòng đời connection. Mock không thực hiện connection acquisition thực tế và không thể phát hiện leak trong pool.

## 10. Ứng phó khi pool đã cạn trong production

Khi pool cạn và request đang timeout, cần khôi phục dịch vụ đồng thời giữ lại bằng chứng để tìm nguyên nhân.

1. Xác nhận acquired, idle, pending acquire và thời gian acquire hiện tại.
2. Kiểm tra database có query chạy lâu, lock wait hoặc transaction idle kéo dài không.
3. Xác định endpoint, query hoặc job nền tạo phần lớn connection đang được mượn.
4. Nếu có thể, giảm concurrency hoặc tạm dừng job nền gây tải để pool có thời gian hồi phục.
5. Nếu một query đã được xác định là bất thường, xử lý theo quy trình vận hành database để kết thúc hoặc khắc phục query đó; tránh kill session hàng loạt khi chưa hiểu tác động transaction.
6. Theo dõi pending acquire và acquired có giảm sau khi tải được điều tiết hay không.
7. Sau khi hệ thống ổn định, lưu metrics, trace và log để sửa nguyên nhân gốc.

Restart ứng dụng có thể giải phóng connection thuộc process đó, nhưng cũng làm mất thông tin chẩn đoán và có thể tạo một đợt kết nối mới tới database. Chỉ xem restart là biện pháp khôi phục có kiểm soát khi cần thiết, không coi đó là cách sửa leak.

## 11. Ví dụ đọc dấu hiệu và chọn hướng xử lý

| Quan sát | Khả năng cần kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Acquired đạt max, query latency tăng mạnh | SQL chậm, database quá tải hoặc lock | Xem execution plan, wait event, index và lock |
| Acquired đạt max, query nhanh nhưng hold duration dài | Transaction hoặc stream còn mở, subscriber chậm | Rút ngắn transaction, giới hạn stream, tách xử lý ngoài database |
| Acquired tăng dần qua mỗi batch và không giảm | Leak trong code tự acquire hoặc publisher không cleanup | Kiểm tra `ConnectionFactory.create()`, `usingWhen`, cancel và error path |
| Pending chỉ tăng ở giờ cao điểm, sau đó giảm | Burst concurrency hoặc pool sizing chưa phù hợp | Giới hạn concurrency, đo workload và tính lại pool |
| Idle connection có nhưng acquire vẫn chậm | Kiểm tra validation, tạo connection, lock nội bộ hoặc metrics sai lệch | Xem log pool, validation và định nghĩa metric theo phiên bản |
| Database có nhiều session `idle in transaction` | Transaction mở nhưng ứng dụng đang chờ hoặc chưa kết thúc | Rà soát ranh giới `@Transactional` và các bước chờ bên trong |

## 12. Danh sách kiểm tra khi điều tra

- [ ] Đã xác nhận `acquiredSize`, `idleSize`, `allocatedSize` và `pendingAcquireSize` theo thời gian.
- [ ] Đã đo riêng acquire latency, query latency và connection hold duration.
- [ ] Đã đối chiếu trace ứng dụng với session, query và lock trên database.
- [ ] Đã tìm các đoạn tự gọi `ConnectionFactory.create()` và xác nhận cleanup khi complete, error, cancel.
- [ ] Đã kiểm tra transaction có bao trùm lời gọi HTTP, message hoặc xử lý chậm hay không.
- [ ] Đã kiểm tra `Flux` lớn, subscriber chậm và concurrency của `flatMap`.
- [ ] Đã tính tổng `max-size` trên tất cả replica cùng các client khác tới database.
- [ ] Đã kiểm thử lại sau khi sửa và xác nhận pool hồi phục sau tải, timeout và cancellation.

## 13. Kết luận

Pool cạn xảy ra khi các yêu cầu cần connection vượt quá số connection sẵn sàng trong thời điểm đó. Rò rỉ connection, transaction kéo dài, truy vấn chậm, stream bị tiêu thụ chậm và concurrency quá cao đều có thể dẫn tới tình trạng này.

Hãy quan sát đồng thời acquired, idle, pending acquire, thời gian acquire, query duration và hold duration. Nếu query lâu, tối ưu database; nếu transaction hoặc stream giữ connection lâu, rút ngắn vòng đời; nếu code tự acquire mà không release, sửa cleanup cho cả complete, error và cancel. Chỉ điều chỉnh kích thước pool sau khi đã hiểu tải thực tế và giới hạn connection của database.
