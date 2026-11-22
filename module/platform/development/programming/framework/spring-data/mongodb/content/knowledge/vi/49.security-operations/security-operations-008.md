# Cấu hình timeout, retry và pool theo tải ứng dụng

## 1. Vì sao timeout, retry và connection pool phải thiết kế cùng nhau?

Trong module **SPRING_DATA_MONGODB**, Spring Data MongoDB được dùng để kết nối, ánh xạ document và thao tác MongoDB thông qua **MongoTemplate** hoặc **repository**. Bên cạnh thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu, ứng dụng còn phải xử lý tải tăng cao và sự cố kết nối. Đây là nội dung của chương **Bảo mật và vận hành**.

Giả sử dịch vụ đơn hàng sử dụng một MongoDB replica set. Khi traffic tăng đột ngột, các request chờ connection từ pool; một số truy vấn giữ connection quá lâu; MongoDB có thể đang bầu lại primary. Nếu timeout quá dài, request chiếm thread và connection dù người gọi đã bỏ cuộc. Nếu timeout quá ngắn, request hợp lệ thất bại. Nếu retry quá nhiều, hệ thống nhân thêm tải đúng lúc server đang chậm.

Thiết kế tốt cần trả lời:

1. Một request được phép chờ server, kết nối và kết quả trong bao lâu?
2. Thao tác nào được retry, lỗi nào phải dừng ngay và khi nào kết quả ghi chưa rõ?
3. Mỗi instance/pod cần bao nhiêu connection, trong tổng ngân sách của MongoDB?
4. Chỉ số nào chứng minh rằng thay đổi cấu hình thực sự cải thiện độ trễ và tính ổn định?

**Mục tiêu học tập:** phân biệt timeout, hiểu CSOT, cấu hình retryable reads/writes, ước lượng pool theo concurrency, dùng Spring Data MongoDB cấu hình driver, kiểm chứng bằng metrics và kiểm thử failover.

## 2. Một thao tác MongoDB đi qua những giai đoạn nào?

~~~mermaid
flowchart LR
  A[HTTP request] --> B[Server selection]
  B --> C[Checkout connection]
  C --> D[Gửi command]
  D --> E[MongoDB xử lý]
  E --> F[Đọc kết quả]
  F --> G[Trả connection về pool]
  G --> H[HTTP response]
~~~

| Giai đoạn | Điều gì có thể gây chậm? | Tín hiệu |
| --- | --- | --- |
| Server selection | Primary không sẵn sàng, DNS/topology lỗi, read preference không có ứng viên | MongoTimeoutException và cluster description |
| Mở kết nối TCP/TLS | Mạng, firewall, TLS handshake | Socket open/connect hoặc SSL exception |
| Checkout từ pool | Nhiều thao tác đang giữ connection, pool đã chạm maxPoolSize | Checkout wait và checkout timeout |
| Gửi/nhận dữ liệu | Network chậm, response lớn, server không phản hồi | Socket I/O/operation timeout |
| Thực thi query | Thiếu index, blocking sort, CPU/I/O hoặc lock contention | Slow query, explain, server metrics |
| Retry | Driver/app thử lại lỗi nhất thời | Attempt count và latency đuôi |

**Một timeout đơn lẻ không nhất thiết là deadline toàn HTTP request.** Nhiều timeout truyền thống áp dụng cho giai đoạn khác nhau hoặc mỗi lần thử. Cần tính cả thời gian gateway, xử lý nghiệp vụ, MongoDB, retry và serialization.

## 3. Các loại timeout trong MongoDB Java Driver

### 3.1. Các tùy chọn thường gặp

| Tùy chọn | Giới hạn | Điểm cần nhớ |
| --- | --- | --- |
| serverSelectionTimeoutMS | Thời gian tìm server phù hợp với topology/read preference | Không phải thời gian query được phép chạy |
| connectTimeoutMS | Thời gian mở kết nối socket | Không giới hạn thời gian command sau khi kết nối xong |
| socketTimeoutMS | Thời gian chờ socket I/O theo cơ chế cũ | Không bảo đảm server đã dừng lệnh |
| waitQueueTimeoutMS | Chờ lấy connection từ pool theo cơ chế cũ | Driver Java hiện hành đã đánh dấu tùy chọn này deprecated |
| maxTimeMS | Server được phép xử lý một số command trong thời gian giới hạn | Không bao gồm mọi thời gian phía client |
| wtimeoutMS | Chờ đạt write concern theo cơ chế cũ | Hết thời gian không nhất thiết là ghi chưa xảy ra |
| timeoutMS | Deadline thao tác phía client theo CSOT | Bao gồm server selection, checkout và xử lý theo cơ chế mới |

Theo tài liệu **Java Sync Driver 5.x**, các mặc định điển hình là serverSelectionTimeoutMS **30.000 ms**, connectTimeoutMS **10.000 ms**, socketTimeoutMS **0** (không giới hạn kiểu cũ), maxPoolSize **100**. Các giá trị có thể phụ thuộc phiên bản; luôn đối chiếu với driver được ứng dụng sử dụng.

Ví dụ cấu hình theo nhóm timeout **truyền thống**:

~~~text
mongodb://db1.example.internal:27017,db2.example.internal:27017/shop?replicaSet=rs0&tls=true&serverSelectionTimeoutMS=3000&connectTimeoutMS=1500&socketTimeoutMS=7000&waitQueueTimeoutMS=1200
~~~

Các con số trên chỉ để minh họa cách khai báo. Không sao chép vào production nếu chưa đo SLO HTTP, độ trễ mạng, thời gian failover và tốc độ xử lý của MongoDB.

### 3.2. Ba timeout dễ nhầm

**Server selection timeout:** nếu replica set chỉ còn secondary nhưng ứng dụng phải ghi vào primary, driver có thể chờ đến khi primary sẵn sàng; lệnh chưa được gửi đi. Tăng socketTimeoutMS không giải quyết trường hợp này.

**Connect timeout:** giới hạn lúc tạo socket TCP tới server. Kết nối mới có thể hết thời gian vì firewall/network; một query chạy trên connection đã tồn tại có thể lâu hơn giá trị này.

**Socket timeout:** giới hạn I/O trên socket theo cơ chế truyền thống; không phải công cụ chuyên dụng để ngắt query server đúng N mili giây. Client có thể hết thời gian chờ trong khi server vẫn đang xử lý, nhất là với lệnh ghi. Cần thiết kế xử lý kết quả không chắc chắn.

Ví dụ:

~~~text
serverSelectionTimeoutMS = 3000 ms
connectTimeoutMS         = 1500 ms
socketTimeoutMS          = 7000 ms
HTTP gateway timeout     = 3500 ms
~~~

Ứng dụng có thể vẫn đang đợi thao tác MongoDB khi gateway đã trả timeout cho client. Muốn SLO HTTP 3,5 giây, cần dành thời gian cho xác thực, gọi dịch vụ khác và kết xuất kết quả; database phải có ngân sách hợp lý bên trong deadline.

### 3.3. CSOT: timeoutMS cho toàn bộ một thao tác

MongoDB Java Driver mới hỗ trợ **Client-Side Operation Timeout (CSOT)** qua tham số timeoutMS. Theo tài liệu Java Driver 5.x, CSOT áp giới hạn tổng cho các bước thực hiện thao tác, gồm chọn server, lấy connection và xử lý command. CSOT từng được giới thiệu ở Java Driver 5.3 và hiện vẫn được mô tả là tính năng **experimental** trong tài liệu; cần xác minh khả năng tương thích với phiên bản đang sử dụng.

~~~text
mongodb://db1.example.internal:27017/shop?tls=true&timeoutMS=4000
~~~

Khi timeoutMS được đặt, driver bỏ qua những tùy chọn timeout cũ tương ứng như **waitQueueTimeoutMS, socketTimeoutMS, wtimeoutMS, maxTimeMS và maxCommitTimeMS**. Vì vậy không đặt timeoutMS cùng các giá trị này và kỳ vọng chúng cộng dồn. connectTimeoutMS vẫn là tham số kết nối; tham khảo đúng tài liệu của phiên bản để hiểu tương tác với deadline.

| Cách tiếp cận | Cấu hình | Đánh đổi |
| --- | --- | --- |
| Truyền thống | serverSelectionTimeoutMS, connectTimeoutMS, socketTimeoutMS, waitQueueTimeoutMS | Mỗi giai đoạn có timeout riêng, khó áp deadline duy nhất |
| CSOT | timeoutMS, cùng các option kết nối/pool liên quan | Dễ gắn với ngân sách thao tác, nhưng có thể thay đổi hành vi retry và vô hiệu hóa timeout cũ |

Không dùng timeoutMS = 0 cho API online chỉ để loại bỏ lỗi timeout. Giá trị này có nghĩa không đặt giới hạn toàn thao tác theo mô hình CSOT và có thể khiến request chờ rất lâu.

### 3.4. maxTimeMS và write concern timeout

Trước khi dùng CSOT, có thể đặt thời gian server được phép xử lý truy vấn bằng maxTimeMS:

~~~javascript
db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .maxTimeMS(1200)
  .limit(50);
~~~

Trong Spring Data MongoDB:

~~~java
import java.time.Duration;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-A")
        .and("status").is("PAID")
);
query.maxTime(Duration.ofMillis(1200));
query.limit(50);
~~~

maxTimeMS là giới hạn phía server của các command hỗ trợ; nó không bao gồm toàn bộ server selection, pool wait, network và HTTP response. Khi dùng timeoutMS, phải lưu ý các cơ chế cũ có thể bị driver bỏ qua.

**Write concern timeout không chứng minh ghi đã bị rollback**: dữ liệu có thể đã ghi trên primary nhưng chưa được xác nhận theo mức write concern yêu cầu. Đặc biệt với thanh toán hoặc tạo đơn, cần truy vấn lại trạng thái hoặc dùng khóa idempotency, không tự tạo request mới sau mọi lỗi timeout.

## 4. Retryable reads và retryable writes

### 4.1. Driver retry được những thao tác nào?

Java Driver hiện đại thường bật **retryReads=true** và **retryWrites=true** mặc định. Ở cơ chế truyền thống, với command đủ điều kiện, driver thường thử lại thêm **một lần** khi gặp lỗi được phân loại là retryable. Nếu dùng CSOT, số lần thử có thể khác do retry dựa trên deadline timeoutMS.

~~~text
mongodb://db1.example.internal:27017,db2.example.internal:27017/shop?replicaSet=rs0&tls=true&retryReads=true&retryWrites=true
~~~

| Nhóm thao tác | Khả năng retry của driver | Giới hạn |
| --- | --- | --- |
| Một số read command như find | Retryable reads khi gặp lỗi phù hợp | Không phải mọi read hoặc mọi loại lỗi |
| insertOne, updateOne, replaceOne, deleteOne | Retryable writes khi đáp ứng yêu cầu topology/acknowledgment | Không áp dụng cho mọi thao tác ghi |
| updateMany, deleteMany | Không thuộc nhóm retryable write một-document thông thường | Phải thiết kế retry riêng nếu thực sự an toàn |
| Writes trong multi-document transaction | Không retry độc lập bằng retryWrites | Phải xử lý lỗi transaction/commit riêng |
| Email, payment API, REST side effect | Không thuộc MongoDB Driver | Cần cơ chế idempotency của nghiệp vụ |

Retryable writes đòi hỏi **replica set hoặc sharded cluster** hỗ trợ; standalone không có cùng cơ chế. Lệnh ghi phải có write concern được xác nhận, không phải **w:0**. Sau lỗi mất kết nối, kết quả ghi có thể không rõ, vì vậy không được đồng nhất lỗi với kết quả chưa xảy ra.

### 4.2. Driver retry khác retry toàn bộ HTTP request

Giả sử endpoint POST /api/orders làm ba việc:

~~~text
1. Ghi order vào MongoDB
2. Gửi yêu cầu thanh toán tới provider
3. Gửi email xác nhận
~~~

Driver chỉ có thể retry command MongoDB đủ điều kiện. Nếu API gateway retry POST và service retry toàn bộ method, thanh toán/email có thể bị gọi nhiều lần, ngay cả khi ghi order chỉ xảy ra một lần.

Nên thiết kế:

1. Mỗi request tạo đơn có **idempotency key** do client gửi hoặc service phát sinh theo hợp đồng.
2. Lưu một bản ghi duy nhất theo key với unique index.
3. Ghi theo một khóa định danh ổn định; không tạo ObjectId mới ở mỗi lượt retry.
4. Nếu kết quả ghi chưa rõ, tìm lại key trước khi thử hành động nghiệp vụ tiếp theo.
5. Đối với payment/email, dùng outbox và consumer idempotent hoặc cơ chế tương đương của hệ thống.

Ví dụ upsert có thể lặp lại với key ổn định:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class RequestReceiptStore {
    private final MongoTemplate template;

    public RequestReceiptStore(MongoTemplate template) {
        this.template = template;
    }

    public void ensureReceived(String requestId) {
        Query query = Query.query(Criteria.where("_id").is(requestId));
        Update update = new Update()
            .setOnInsert("status", "RECEIVED")
            .setOnInsert("requestId", requestId);
        template.upsert(query, update, "request_receipts");
    }
}
~~~

MongoDB tự tạo unique index cho _id, nên cùng requestId không tạo hai document khác nhau. Ví dụ này **chỉ minh họa một bước ghi idempotent**, chưa giải quyết toàn bộ trạng thái concurrent requests hoặc các side effect ngoài MongoDB.

### 4.3. Trường hợp không nên retry

Không retry bừa bãi các lỗi:

- **Authentication hoặc authorization:** credential sai hoặc thiếu quyền không tự khắc phục bằng chờ.
- **Validation, schema, duplicate key hoặc command sai:** thường cần sửa dữ liệu/hợp đồng thay vì gửi lặp.
- **Ghi có kết quả chưa chắc chắn:** cần đối soát key/trạng thái trước khi thực hiện lại side effect.
- **Lỗi lâu dài, backend bão hòa:** retry liên tục gây áp lực, khiến phục hồi chậm hơn.

Nếu có retry ở tầng service, phải kiểm tra thao tác an toàn để chạy lại, dùng deadline chung, số lần thử hữu hạn, exponential backoff và **jitter**. Không dùng vòng lặp retry vô hạn chỉ vì exception thuộc họ network.

### 4.4. Transaction có logic retry riêng

Writes trong transaction không được retry riêng lẻ chỉ nhờ retryWrites=true. Với MongoDB transaction, có thể gặp các nhãn lỗi **TransientTransactionError** hoặc **UnknownTransactionCommitResult**. Tùy trường hợp cần retry cả transaction hoặc thử lại commit theo quy tắc driver/transaction.

Nếu Spring Data MongoDB dùng MongoTransactionManager hoặc ReactiveMongoTransactionManager, cần tìm hiểu cách ứng dụng xử lý exception và trạng thái commit. Không tự bao toàn bộ service có side effect bên ngoài trong một vòng retry. Transaction dài còn có thể giữ connection lâu hơn và gây pressure lên pool.

## 5. Retry budget và chống retry storm

### 5.1. Vì sao nhiều tầng retry nguy hiểm?

Giả sử ba tầng đều tự cho phép thử lại:

~~~text
HTTP client: tối đa 3 attempts
API service: tối đa 3 attempts
MongoDB driver: tối đa 2 attempts

Trường hợp xấu nhất có thể tới: 3 x 3 x 2 = 18 attempts
~~~

Đây là phép tính minh họa khi mỗi tầng hoạt động độc lập, không phải cam kết driver luôn retry đúng hai lần. Retry nhiều tầng có thể nhân lưu lượng MongoDB ngay khi server bị failover hoặc quá tải.

Một thiết kế hợp lý:

- Chọn tầng chịu trách nhiệm retry chính; biết rõ driver đã retry những lệnh nào.
- Đặt deadline cho toàn bộ request và giới hạn tổng attempts.
- Chỉ retry lỗi được phân loại là transient.
- Sử dụng backoff tăng dần có jitter, tránh đồng bộ retry giữa nhiều pod.
- Áp dụng rate limit, bounded queue hoặc load shedding khi hệ thống đang nghẽn.
- Đảm bảo idempotency, đặc biệt cho tạo đơn, chuyển tiền hoặc webhook.

~~~mermaid
flowchart TD
  A[Mongo operation lỗi] --> B{Lỗi transient?}
  B -->|Không| C[Trả lỗi hoặc xử lý nghiệp vụ]
  B -->|Có| D{An toàn để lặp lại?}
  D -->|Không| E[Đối soát trạng thái theo idempotency key]
  D -->|Có| F{Còn deadline và attempts?}
  F -->|Không| G[Fail fast và ghi metrics]
  F -->|Có| H[Backoff + jitter]
  H --> I[Retry có kiểm soát]
  I --> A
~~~

Circuit breaker hoặc bulkhead cũng cần được cấu hình theo nhu cầu thực tế. Không để một truy vấn báo cáo chậm làm nghẽn mọi request quan trọng; cân nhắc cách ly concurrency hoặc tài nguyên cho các workload dài.

## 6. Connection pool của MongoDB Driver

### 6.1. Pool được quản lý theo từng server

Một **MongoClient** giữ pool theo **từng server trong topology**. Với replica set, các pool đến primary và secondary có thể có độ sử dụng khác nhau theo read preference. Driver còn mở kết nối riêng phục vụ monitoring.

Những điều cần nhớ:

1. Dùng lại MongoClient do Spring Boot quản lý trong vòng đời ứng dụng. **Không tạo client mới cho mỗi request**.
2. maxPoolSize là giới hạn cho một pool của một MongoClient đến một server, không phải toàn cluster.
3. Nếu pool đang dùng hết connection, thao tác mới phải chờ checkout hoặc hết deadline.
4. Nhiều pod/instance đồng nghĩa có nhiều pool độc lập; tổng connection có thể tăng mạnh.
5. Một ứng dụng có cả sync MongoClient và reactive MongoClient có thể sở hữu thêm các pool riêng.

### 6.2. Những tham số cần đo

| Tham số | Vai trò | Rủi ro cấu hình |
| --- | --- | --- |
| maxPoolSize | Số connection tối đa trong pool mỗi server | Nhỏ làm chờ; lớn có thể làm MongoDB quá tải |
| minPoolSize | Số connection tối thiểu duy trì | Cao gây chiếm nhiều connection rỗi trên nhiều pod |
| maxConnecting | Số connection được phép thiết lập cùng lúc trong pool | Cao gây connection storm; thấp khiến pool mở chậm |
| maxIdleTimeMS | Đóng connection khi rỗi quá lâu | Quá thấp gây churn; quá cao dễ gặp idle disconnect |
| maxLifeTimeMS | Tuổi thọ tối đa của connection | Quá thấp tăng TLS handshake/CPU |
| waitQueueTimeoutMS | Timeout checkout theo mô hình cũ | Có thể bị bỏ qua khi bật timeoutMS |
| timeoutMS | Giới hạn toàn thao tác theo CSOT | Cần đánh giá timeout riêng cho tác vụ dài |

Theo tài liệu Java Sync Driver 5.x, **maxPoolSize=100**, **minPoolSize=0** và **maxConnecting=2** là các giá trị mặc định điển hình. Đây là điểm tham khảo, không phải công thức cấu hình tối ưu cho mọi deployment.

### 6.3. Ví dụ URI với pool và timeout

Một cấu hình thử nghiệm dùng timeout truyền thống:

~~~text
mongodb://db1.example.internal:27017/shop?tls=true&maxPoolSize=40&minPoolSize=4&maxConnecting=2&maxIdleTimeMS=60000&serverSelectionTimeoutMS=2500&connectTimeoutMS=1500&socketTimeoutMS=6500&retryReads=true&retryWrites=true
~~~

Một cấu hình riêng sử dụng CSOT, khi driver đã hỗ trợ và ứng dụng đã kiểm chứng:

~~~text
mongodb://db1.example.internal:27017/shop?tls=true&maxPoolSize=40&minPoolSize=4&maxConnecting=2&maxIdleTimeMS=60000&timeoutMS=4000&retryReads=true&retryWrites=true
~~~

**Không trộn hai mô hình timeout** mà không hiểu tùy chọn nào được driver sử dụng. URI chứa username/password thật phải được cấp qua secret manager, không commit vào repository hoặc ghi log.

### 6.4. Cấu hình qua Spring Boot và MongoClientSettings

Trong **Spring Boot 3.x**, application.yml có thể nhận URI từ biến môi trường:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

MONGODB_URI được cấp bởi hệ thống triển khai. Với Spring Boot 4, property MongoDB được tổ chức khác (ví dụ spring.mongodb.uri); cần xác minh đúng phiên bản thực tế. Nếu ứng dụng tự tạo MongoClient hoặc có nhiều client, kiểm tra các bean và thứ tự áp dụng cấu hình.

Một ví dụ **Spring Boot 3.x** tùy chỉnh pool bằng code:

~~~java
package example.mongo;

import java.util.concurrent.TimeUnit;
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MongoPoolConfiguration {

    @Bean
    MongoClientSettingsBuilderCustomizer mongoPoolCustomizer() {
        return settings -> settings.applyToConnectionPoolSettings(pool ->
            pool.maxSize(40)
                .minSize(4)
                .maxConnecting(2)
                .maxConnectionIdleTime(60, TimeUnit.SECONDS)
        );
    }
}
~~~

Các con số là giá trị minh họa để thử tải. Nếu URI cũng chứa pool options, cần kiểm tra **thứ tự ưu tiên** và cấu hình driver cuối cùng để tránh việc code ghi đè giá trị đã vận hành. Không tạo MongoClient mới trong từng HTTP handler.

## 7. Ước lượng pool theo tải

### 7.1. RPS không đồng nghĩa số connection cần dùng

Một request HTTP chỉ giữ connection MongoDB trong thời gian thao tác database đang dùng nó. Có thể dùng Little's Law làm ước lượng khởi đầu:

~~~text
Concurrent checked-out connections trung bình
≈ MongoDB operations/giây x Thời gian giữ connection trung bình (giây)
~~~

Giả sử **mỗi pod**:

- Nhận 150 HTTP request/giây.
- Trung bình 0,8 thao tác MongoDB cho mỗi HTTP request.
- Thời gian giữ connection trung bình là 50 ms = 0,05 giây.

Ta có:

~~~text
MongoDB ops/s = 150 x 0,8 = 120
Concurrent connections trung bình ≈ 120 x 0,05 = 6
~~~

Giá trị **6** là mức trung bình, không phải maxPoolSize tối ưu. Burst traffic, transaction, cursor streaming, query p95/p99 và background jobs có thể làm concurrency cao hơn. Có thể thử maxPoolSize=20 như một **ứng viên đo kiểm**, rồi điều chỉnh theo checkout wait, tỷ lệ timeout và tài nguyên server.

Nếu có 8 pod, mỗi pod maxPoolSize=20, số connection tiềm năng của riêng các pool hướng đến primary là:

~~~text
8 x 20 = 160 connection
~~~

Đây là giới hạn tiềm năng, không phải số socket luôn mở. Cần cộng thêm monitoring connection, pool tới secondary và client của những service/job khác. Vì pool được duy trì theo server, **maxPoolSize của một pod không phải giới hạn connection của toàn cluster**.

### 7.2. Khi nào nên tăng pool?

| Tình trạng quan sát | Hành động nên thử |
| --- | --- |
| Pool đầy, checkout p95 cao, MongoDB CPU/I/O còn dư | Đo tác động tăng pool từng bước; kiểm tra có cursor/transaction giữ connection lâu không |
| Pool đầy nhưng MongoDB CPU/I/O cũng bão hòa | Tối ưu query/index, giảm tải hoặc mở rộng server trước |
| Pool không đầy nhưng command duration cao | Điều tra explain, query plan, network, lock, tài nguyên MongoDB |
| Checkout nhanh nhưng HTTP latency cao | Kiểm tra các bước khác của HTTP request và service phụ thuộc |
| Nhiều connection bị tạo/đóng liên tục | Xem maxIdleTimeMS, maxLifeTimeMS, TLS, proxy idle timeout |
| Nhiều pod khởi động cùng lúc | Giới hạn maxConnecting, kiểm soát warm-up và tổng ngân sách connection |

**Tăng maxPoolSize không làm truy vấn thiếu index chạy nhanh hơn.** Nếu một query scan lớn giữ connection 3 giây, tăng pool có thể chỉ khiến nhiều query tốn tài nguyên cùng chạy, gây quá tải nặng hơn.

### 7.3. Bảng dữ liệu cần thu thập trước khi chọn pool

| Đầu vào | Ví dụ | Nguồn |
| --- | --- | --- |
| Số pod thường xuyên / cao điểm | 4 / 8 | Deployment, HPA |
| RPS cao điểm mỗi pod | 150 | HTTP metrics |
| Số MongoDB ops/request | 0,8 | Tracing, command metrics |
| Thời gian checkout hold trung bình | 50 ms | Driver pool metrics |
| Checkout wait p95 | Mục tiêu dưới 20 ms | Telemetry từ driver |
| Command duration p95 | 120 ms | Driver/server metrics |
| MongoDB CPU/I/O/connection limit | Theo cụm | Server metrics |
| maxPoolSize ứng viên | 20 | Load test |

Nên dùng dữ liệu tải **cao điểm** và tenant lớn/nhỏ; trung bình toàn ngày sẽ che khuất burst. Không tăng minPoolSize chỉ vì muốn số lượng connection lớn luôn sẵn sàng nếu môi trường có nhiều pod.

## 8. Spring Data sync và reactive dưới tải

Với **MongoTemplate** hoặc repository đồng bộ, thread gọi thường chờ thao tác MongoDB hoàn tất. Khi pool hết connection, nhiều servlet thread có thể đứng chờ checkout, làm giảm khả năng phục vụ HTTP.

Với **ReactiveMongoTemplate** hoặc reactive repository, thao tác I/O có thể không chặn thread theo mô hình blocking truyền thống, nhưng pool MongoDB, CPU, băng thông và khả năng xử lý server vẫn hữu hạn. Reactive không có nghĩa vô hạn concurrency.

Các nguyên tắc:

- Giới hạn số thao tác độc lập chạy song song, đặc biệt khi dùng flatMap trên hàng nghìn phần tử.
- Ưu tiên query theo batch thay vì N query riêng nếu nghiệp vụ cho phép.
- Không gọi block() trên event-loop để biến pipeline reactive thành xử lý đồng bộ.
- Đóng cursor/stream và xử lý cancellation đúng vòng đời, tránh giữ tài nguyên.
- Nếu ứng dụng có MongoClient đồng bộ và reactive khác nhau, đo tổng pool/connection.

Ví dụ giới hạn concurrency trong một service reactive:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<Order> loadOrders(
        ReactiveMongoTemplate template, List<String> orderIds) {
    return Flux.fromIterable(orderIds)
        .flatMap(id ->
            template.findOne(
                Query.query(Criteria.where("orderId").is(id)),
                Order.class
            ),
            8 // Giá trị thử nghiệm cho các truy vấn đồng thời.
        );
}
~~~

Ví dụ giả định class Order và khóa orderId dạng string đã tồn tại. Con số **8** giới hạn số inner publisher đồng thời trong thao tác này, **không phải maxPoolSize**. Cần đo và cân nhắc đổi sang truy vấn theo lô nếu số ID lớn.

## 9. Metrics và chẩn đoán

### 9.1. Bộ chỉ số tối thiểu

| Metrics | Trả lời câu hỏi | Dấu hiệu bất thường |
| --- | --- | --- |
| Checked-out / available connections | Pool đang dùng bao nhiêu? | Duy trì sát maxPoolSize liên tục |
| Checkout wait p50/p95/p99 | Request chờ connection bao lâu? | p99 tăng mạnh dưới burst |
| Checkout failure/timeout | Có request không lấy được connection? | Pool bão hòa, operation giữ connection lâu |
| Created/closed connections | Connection churn có cao? | Cấu hình idle/lifetime hoặc lỗi mạng |
| Server selection timeout | Có chọn được server? | Failover, DNS, read preference |
| Command duration p95/p99 | Query thực sự chậm bao nhiêu? | Thiếu index, CPU/I/O cao |
| Retry/error count | Có retry storm hoặc lỗi nhất thời? | Attempts tăng đột biến |
| HTTP p95/p99 và 5xx | Người dùng bị ảnh hưởng thế nào? | Deadline giữa gateway và DB không khớp |
| DB connections/CPU/I/O | Server còn headroom? | Tăng pool khiến backend quá tải |

MongoDB Java Driver cung cấp **ConnectionPoolListener** để theo dõi sự kiện checkout, checkin, tạo/đóng connection và **CommandListener** cho sự kiện command. Có thể kết hợp Micrometer hoặc monitoring stack của tổ chức. Tránh ghi raw command chứa thông tin khách hàng, token hoặc URI/credential vào log và trace.

### 9.2. Hai chẩn đoán trái ngược

**Tình huống A** (số đo minh họa):

~~~text
HTTP p95:                  2800 ms
MongoDB command p95:        180 ms
Pool checkout p95:         1700 ms
Checked-out connections:   40 / 40
MongoDB CPU:                45%
~~~

Pool đang nghẽn nhưng server còn headroom. Cần kiểm tra request/cursor giữ connection quá lâu, transaction bị kéo dài, sau đó mới thử tăng pool có kiểm soát.

**Tình huống B** (số đo minh họa):

~~~text
HTTP p95:                  3500 ms
MongoDB command p95:       3000 ms
Pool checkout p95:           20 ms
MongoDB CPU:                95%
~~~

Nút thắt ở query/server, không phải checkout. Tăng pool lúc này có thể làm CPU và queue trong MongoDB tăng thêm. Nên kiểm tra slow queries, explain, index, aggregation, lock và tài nguyên cluster.

## 10. Load test và kiểm thử sự cố

### 10.1. Kịch bản cần thử

| Tình huống | Bằng chứng cần thu thập |
| --- | --- |
| Tải đều và burst 2–5 lần | Throughput, HTTP p95/p99, checkout wait |
| maxPoolSize 10/20/40 trên cùng workload | Lợi ích và tác động tới CPU/I/O MongoDB |
| Nhiều pod scale cùng lúc | Tổng connections, maxConnecting, thời gian warm-up |
| Query thiếu index hoặc aggregation nặng | Command duration, pool occupancy và timeouts |
| Replica set failover | Server selection, retry, thời gian phục hồi |
| Mạng mất gói hoặc socket chậm | Connect/socket/operation timeout đúng thiết kế |
| Retry driver cùng retry service/HTTP | Số attempts, idempotency, duplicate request |
| Transaction commit không chắc chắn | Cách xử lý UnknownTransactionCommitResult |
| Reactive fan-out | Concurrency, backpressure và pool checkout |
| Cursor/stream dài bị hủy | Giải phóng tài nguyên và connection sau cancellation |

Thực hiện trên replica set **test** với dữ liệu và phân bố truy vấn đại diện. Có thể dùng công cụ load test và proxy lỗi mạng để mô phỏng failover/latency; không chủ động ngắt primary production chỉ để kiểm tra.

### 10.2. Quy trình điều chỉnh cấu hình

1. **Chốt SLO:** ví dụ HTTP p95, tỷ lệ 5xx, thời gian failover chấp nhận và giới hạn request concurrency.
2. **Đo baseline:** lưu thông số driver, MongoDB version, index, p95/p99, checkout wait và tình trạng server.
3. **Chọn một thay đổi:** timeout hoặc pool hoặc retry budget; không đổi đồng thời mọi giá trị.
4. **Chạy lại cùng workload:** so metrics với baseline và xác minh không sai kết quả nghiệp vụ.
5. **Kiểm thử lỗi:** kiểm tra failover, credential lỗi, query chậm và request cancellation.
6. **Đánh giá tổng ngân sách connection:** tính cả số pod tối đa, job nền, các MongoClient và server đích.
7. **Lưu quyết định:** ghi version cấu hình, số đo và các tradeoff; không lưu password.

### 10.3. Tiêu chí nghiệm thu

Một cấu hình được chấp nhận khi:

- HTTP p95/p99 và error rate đạt SLO trong mức tải đã định.
- Connection checkout wait có headroom và ít timeout không mong muốn.
- MongoDB server còn CPU/I/O/connection budget cho workload khác.
- Retry không nhân đôi order, thanh toán, email hoặc các side effect liên quan.
- Hệ thống phục hồi từ failover trong giới hạn; không retry vô ích lỗi validation/auth.
- Sự kiện connection pool và command được quan sát bằng metrics không làm lộ dữ liệu nhạy cảm.

## 11. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tăng mọi timeout lên rất lớn để hết báo lỗi | Request giữ thread/pool lâu và che nguyên nhân | Phân loại từng giai đoạn, thiết kế deadline theo SLO |
| Dùng socketTimeoutMS như giới hạn query tuyệt đối | Client lỗi khi server vẫn chạy | Phân biệt socket, maxTimeMS và CSOT |
| Đặt timeoutMS cùng các timeout cũ và tưởng cộng dồn | Một số option bị driver bỏ qua | Dùng mô hình timeout tương thích với driver |
| Coi timeout write là rollback | Retry có thể gây side effect trùng lặp | Idempotency và đối soát |
| Retry mọi lỗi không giới hạn | Retry storm, tăng độ trễ | Deadline, attempts hữu hạn, backoff và jitter |
| Dùng maxPoolSize mặc định cho mọi pod không đo | Số connection toàn cluster có thể quá lớn | Tính ngân sách theo số instance và server |
| Thấy pool đầy là tăng maxPoolSize | Có thể làm server đang bão hòa tệ hơn | Kiểm tra CPU/I/O, index, slow query |
| Tạo MongoClient ở mỗi HTTP request | Churn kết nối và phân mảnh pool | Dùng client sống cùng vòng đời Spring |
| minPoolSize quá cao với nhiều pod | Connection rỗi chiếm tài nguyên | Điều chỉnh theo warm-up và tải thật |
| Reactive fan-out không giới hạn | Pool queue, bộ nhớ và latency tăng | Giới hạn concurrency và batch hóa |
| Chỉ đo latency trung bình | Bỏ sót đuôi p99 và sự cố burst | Theo dõi histogram và từng giai đoạn |

## 12. Bài thực hành

Chuẩn bị một ứng dụng Spring Boot + Spring Data MongoDB, kết nối MongoDB replica set thử nghiệm và dữ liệu orders chứa nhiều tenant/status.

1. Chạy truy vấn MongoTemplate ở baseline; ghi throughput, HTTP p95/p99, command duration, checkout wait, connection count.
2. Chọn cấu hình timeout truyền thống và đo hành vi khi primary không có sẵn hoặc socket bị làm chậm. Nếu driver hỗ trợ CSOT, tạo cấu hình riêng với timeoutMS để so sánh.
3. Thử maxPoolSize 10, 20 và 40 dưới cùng tải; giải thích vì sao một mức có thể tốt hơn mức khác.
4. Viết một thao tác upsert có requestId cố định, mô phỏng lỗi tạm thời, xác minh chỉ có một bản ghi.
5. Cho một query thiếu index chạy trên dữ liệu test, đo tác động đến pool rồi tối ưu index và kiểm tra lại.
6. Scale số pod và kiểm tra tổng connection tới primary, checkout p95, CPU MongoDB.
7. Nếu dùng reactive, giới hạn flatMap concurrency và so sánh với fan-out quá lớn.
8. Lập báo cáo cấu hình được chọn, SLO, driver version, workload và số đo trước/sau.

**Câu hỏi tự đánh giá:**

- serverSelectionTimeoutMS khác connectTimeoutMS và socketTimeoutMS ở điểm nào?
- Khi timeoutMS bật CSOT, các timeout cũ bị xử lý thế nào?
- Vì sao một lệnh ghi timeout không chứng minh rằng dữ liệu chưa được ghi?
- Vì sao retry ở HTTP, service và driver có thể nhân lưu lượng đến MongoDB?
- maxPoolSize=40 có giới hạn toàn cluster ở 40 connection không?
- Khi checkout wait cao nhưng MongoDB CPU 95%, có nên tăng pool ngay không?
- ReactiveMongoTemplate giảm chờ thread nhưng vẫn chịu giới hạn gì của pool?

Thiết kế timeout, retry và pool phải dựa trên **workload, SLO và metrics thực tế**. Chọn deadline có ý nghĩa, chỉ retry thao tác an toàn và điều chỉnh pool theo mức đồng thời đo được giúp dịch vụ xử lý tải lớn mà không gây thêm sự cố khi MongoDB gặp lỗi.

## 13. Tài liệu tham khảo

- [MongoDB Java Sync Driver – Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/): cấu hình pool theo server và các giới hạn.
- [MongoDB Java Sync Driver – Socket Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/socket-settings/): connectTimeoutMS, socketTimeoutMS.
- [MongoDB Java Sync Driver – Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/): serverSelectionTimeoutMS.
- [MongoDB Java Sync Driver – Limit Server Execution Time](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/): timeoutMS và CSOT.
- [MongoDB Server – Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): điều kiện và giới hạn retryable writes.
- [MongoDB Server – Retryable Reads](https://www.mongodb.com/docs/manual/core/retryable-reads/): các read command có thể retry.
- [MongoDB Server – Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/): timeout, pool, retry qua URI.
- [Spring Boot 3.x – Working with NoSQL Technologies](https://docs.spring.io/spring-boot/3.4/reference/data/nosql.html): MongoClient và auto-configuration.
- [Spring Data MongoDB – Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): Query.maxTime và MongoTemplate.
