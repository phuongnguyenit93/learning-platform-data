# Khi nào cần pool kết nối và khi nào không cần trong Spring Data Redis

**Connection pool** là cơ chế duy trì và tái sử dụng một tập hợp kết nối đến máy chủ Redis. Khi một thao tác cần kết nối riêng, nó mượn một kết nối từ pool, thực hiện công việc rồi trả lại để thao tác khác tái sử dụng. Pool có thể giảm chi phí tạo kết nối TCP/TLS liên tục, đồng thời giới hạn số kết nối đồng thời của một ứng dụng. Nhưng pool cũng có chi phí quản lý, thời gian chờ mượn kết nối và nguy cơ làm nghẽn hàng đợi nếu kích thước không phù hợp.

Trong **Spring Data Redis**, câu hỏi “có cần pool không?” phụ thuộc mạnh vào **Redis client đang dùng** và **kiểu thao tác**. Đặc biệt, **Lettuce có thể chia sẻ một native connection an toàn giữa nhiều luồng cho những lệnh thông thường**, nên việc tạo pool cho mọi lời gọi Redis thường không cần thiết. Với các thao tác cần kết nối chuyên biệt như blocking command hoặc transaction, cách sử dụng kết nối khác và pool có thể có lợi. Nếu dùng **Jedis**, cách tổ chức kết nối và chia sẻ giữa luồng khác Lettuce, vì vậy nhu cầu pool cũng khác.

Bài này tập trung vào quyết định kỹ thuật trong ngữ cảnh **Spring Data Redis / Kết nối và pool**: hiểu chính xác kết nối nào đang được dùng, chọn thời điểm cần pool, thiết lập theo nhu cầu đo được, và tránh giải pháp “tăng max connections” cho mọi vấn đề hiệu năng. Ví dụ hướng đến Spring Boot 3.x, Spring Data Redis 3.x, Redis standalone và Java 17+; khi dùng phiên bản khác cần đối chiếu API hoặc tên cấu hình tương ứng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt kết nối TCP đến Redis, Spring `RedisConnection`, native connection của Lettuce và connection pool.
2. Giải thích vì sao Lettuce thường không cần pool cho `GET`/`SET`/`INCR` thông thường, ngay cả khi ứng dụng có nhiều request đồng thời.
3. Nhận biết loại công việc có thể cần kết nối chuyên biệt: blocking command, một số transaction, Pub/Sub và các luồng xử lý kéo dài.
4. Phân biệt hành vi dùng kết nối của Lettuce với Jedis để tránh áp dụng một cấu hình máy móc cho cả hai.
5. Thiết lập pool bằng Spring Boot hoặc bằng Java Configuration khi thực sự cần.
6. Ước lượng kích thước pool từ mức đồng thời, thời gian giữ kết nối, số replica và giới hạn tài nguyên.
7. Đo dấu hiệu thiếu kết nối, Redis chậm, pool cạn và lỗi mạng để quyết định điều chỉnh đúng nguyên nhân.

**Kiến thức chuẩn bị:** Redis có lệnh `GET`, `SET`, `INCR`; Spring Boot có `RedisConnectionFactory` và `RedisTemplate`; đã biết request HTTP có thể được phục vụ đồng thời. Không bắt buộc biết Redis Cluster hoặc reactive programming trước khi học bài này.

## 2. Hiểu đúng “connection” trước khi bàn đến “pool”

Một ứng dụng làm việc với Redis thường có các tầng:

~~~text
Nhiều HTTP requests / background jobs
                 |
                 v
      Service / RedisTemplate
                 |
                 v
       RedisConnectionFactory
                 |
                 v
          Lettuce / Jedis
                 |
                 v
        TCP/TLS connection(s)
                 |
                 v
             Redis Server
~~~

Có ba khái niệm dễ bị nhầm:

| Khái niệm | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| **Logical RedisConnection** | Đối tượng kết nối do Spring Data Redis cung cấp qua `RedisConnectionFactory` | Không nhất thiết tương ứng 1:1 với một socket TCP mới |
| **Native connection** | Kết nối thực tế do client Lettuce/Jedis sử dụng đến Redis | Có thể được chia sẻ hoặc mượn riêng tùy client và loại lệnh |
| **Connection pool** | Tập kết nối được tái sử dụng theo cơ chế borrow/return | Có giới hạn số lượng, hàng đợi chờ, idle/active và timeout |

Ví dụ, 100 request HTTP đồng thời gọi `redisTemplate.opsForValue().get(key)` **không có nghĩa Spring phải mở 100 socket TCP đến Redis**. Với cấu hình Lettuce mặc định phù hợp, nhiều thao tác thông thường có thể cùng dùng một native connection hỗ trợ multiplexing.

Ngược lại, khi một lệnh Redis giữ kết nối để chờ dữ liệu (ví dụ `BLPOP`), không thể đơn giản xem nó giống một `GET` ngắn: kết nối có thể bị chiếm dụng cho đến khi lệnh trả về hoặc hết thời gian chờ. Trong tình huống đó, nguồn kết nối riêng trở nên quan trọng.

### 2.1. Pool không biến Redis thành cơ sở dữ liệu quan hệ

Người học Java thường đã gặp connection pool của JDBC, ví dụ HikariCP. Với JDBC, mỗi phiên làm việc/giao dịch thường cần một connection riêng trong thời gian thực thi, và tạo connection với database có thể tốn chi phí. Redis khác ở giao thức, cách client thực hiện I/O và khả năng multiplexing của Lettuce.

Vì thế, suy luận “JDBC cần pool, nên Redis cũng phải dùng pool lớn” là không đủ căn cứ. Hãy xác định trước **client nào đang kết nối** và **những lệnh nào được gọi**.

### 2.2. “Nhiều thread” khác “nhiều connection”

Lettuce được xây dựng trên nền tảng I/O bất đồng bộ và hỗ trợ gửi nhiều lệnh qua kết nối được chia sẻ. Điều này giảm nhu cầu có một socket riêng cho mỗi luồng ứng dụng. Tuy nhiên, chia sẻ kết nối không có nghĩa các lệnh Redis trở thành không tốn thời gian; tốc độ vẫn bị ảnh hưởng bởi network latency, xử lý của Redis, kích thước payload, command chậm và tải máy chủ.

Nếu lệnh Redis bị chậm vì xử lý dữ liệu quá lớn hoặc server quá tải, **tăng số kết nối không tự làm máy chủ xử lý nhanh hơn**. Pool là công cụ quản lý connection, không phải giải pháp tổng quát cho latency.

## 3. Spring Data Redis dùng kết nối như thế nào?

### 3.1. Lettuce: mặc định ưu tiên chia sẻ native connection

Spring Data Redis thường sử dụng `LettuceConnectionFactory` khi ứng dụng chọn Lettuce. Một tùy chọn quan trọng là:

~~~java
LettuceConnectionFactory factory = ...;
factory.setShareNativeConnection(true);
~~~

Trong `LettuceConnectionFactory`, giá trị `shareNativeConnection` mặc định là **true** đối với các phiên bản Spring Data Redis thường dùng. Khi bật chế độ này, nhiều thao tác **thông thường, không chặn và không thuộc transaction** có thể dùng chung một native connection an toàn giữa các luồng. Kết nối logical từ Spring vẫn được quản lý theo từng lần thao tác, nhưng không đòi hỏi một socket độc lập cho mỗi request.

Các thao tác như:

~~~java
String value = stringRedisTemplate.opsForValue().get("shop:item:42");
stringRedisTemplate.opsForValue().set("shop:item:42", "available");
Long count = stringRedisTemplate.opsForValue().increment("shop:item:42:views");
~~~

thường không phải lý do để mở pool riêng chỉ vì API có nhiều lượt truy cập. Trước khi thêm pool, nên đo xem native connection dùng chung có thật sự gây giới hạn trong workload hay không.

**Quan trọng:** Trong trường hợp có `LettucePoolingClientConfiguration`, việc tạo pool không đồng nghĩa mọi `GET`/`SET` sẽ tự động mượn một kết nối từ pool. Nếu `shareNativeConnection=true`, các lệnh thông thường vẫn có thể đi qua shared native connection; pool chủ yếu được dùng cho các kết nối riêng mà factory cần tạo. Cần hiểu quy tắc này trước khi xem thông số `max-active` là số kết nối phục vụ mọi request.

### 3.2. Khi nào Lettuce cần một kết nối riêng?

Một số loại thao tác không phù hợp với shared native connection cho toàn bộ traffic:

- **Blocking Redis commands:** `BLPOP`, `BRPOP` hoặc các lệnh đọc chặn, tùy API và phương thức sử dụng, có thể giữ kết nối trong thời gian chờ.
- **Transaction:** thao tác có trạng thái kết nối như `MULTI`/`EXEC` phải được thực hiện trong ngữ cảnh kết nối phù hợp, không được trộn lẫn với lệnh của luồng khác trên một phiên transaction.
- **Pub/Sub:** subscription có vòng đời dài và luồng thông điệp riêng; thường dùng connection chuyên dụng do listener container quản lý.
- **Các luồng xử lý kéo dài khác:** ví dụ consumer dùng lệnh đọc blocking, kết nối được giữ lâu hơn một `GET`/`SET`.

Spring Data Redis/Lettuce xử lý việc tạo hoặc chọn connection phù hợp cho các nhánh này. **Chính sách dùng pool** và **nhu cầu thực tế** còn tùy factory, client configuration, từng API và số lượng consumer.

Không nên kết luận rằng mọi tác vụ Pub/Sub hay blocking đều phải “bật pool lớn”. Một subscriber cố định cần một connection ổn định có thể không hưởng lợi từ pool kích thước 100; điều cần theo dõi là số kết nối chuyên dụng đồng thời và vòng đời của chúng.

### 3.3. Khi dùng `setShareNativeConnection(false)`

Với Lettuce, có thể chủ động tắt việc chia sẻ native connection:

~~~java
LettuceConnectionFactory factory = ...;
factory.setShareNativeConnection(false);
~~~

Khi đó, mỗi logical connection được lấy qua cơ chế tạo/quản lý kết nối riêng của factory thay vì sử dụng shared native connection thông thường. **Nếu factory được xây dựng bằng cấu hình pooling**, việc này làm cho cả các thao tác thông thường đi qua cơ chế borrow/return của pool.

Hệ quả:

- Pool trở thành giới hạn truy cập của nhiều lệnh, kể cả `GET`/`SET`.
- Có thêm chi phí mượn/trả kết nối và khả năng chờ pool khi cạn.
- Có thể tăng số kết nối Redis và số tài nguyên TCP/TLS so với mô hình chia sẻ.
- Có thể cần thiết cho một số yêu cầu cách ly, nhưng không phải mặc định nên dùng.

**Không tắt shared native connection chỉ để “tận dụng pool đã cấu hình”.** Trước hết phải có dấu hiệu thực tế cho thấy chia sẻ kết nối là không phù hợp với workload hoặc có yêu cầu cô lập kết nối cụ thể.

### 3.4. Jedis: cách dùng kết nối khác

Jedis là một Redis client khác được Spring Data Redis hỗ trợ. Cách sử dụng kết nối của Jedis truyền thống khác Lettuce: một đối tượng kết nối Jedis thông thường **không nên được nhiều luồng dùng đồng thời theo cách chia sẻ như native Lettuce connection**. Trong ứng dụng đa luồng, mỗi tác vụ cần có kết nối riêng trong khoảng thời gian sử dụng; pooling là một cơ chế tái sử dụng kết nối thường gặp.

Do đó, với Jedis và nhiều request đồng thời, **pool thường là lựa chọn tự nhiên**. Tuy nhiên, vẫn cần giới hạn số connection, timeout khi chờ và cách trả kết nối đúng. Chuyển từ Lettuce sang Jedis chỉ để “dễ bật pool” không chứng minh được hiệu năng sẽ tốt hơn.

| Đặc điểm | Lettuce | Jedis |
| --- | --- | --- |
| Cơ chế chính | I/O bất đồng bộ, hỗ trợ multiplexing trên kết nối chia sẻ | Client đồng bộ truyền thống với kết nối thường được sử dụng theo từng tác vụ |
| Chia sẻ một native connection cho nhiều request thông thường | Có, trong trường hợp phù hợp | Không áp dụng mô hình chia sẻ connection như Lettuce |
| Pool cho `GET`/`SET` đơn giản | Thường không cần | Thường hữu ích trong ứng dụng đa luồng |
| Blocking/transaction | Cần ngữ cảnh connection riêng khi phù hợp | Cần connection được sở hữu trong thời gian thao tác |
| Câu hỏi khi tuning | Có cần nhiều connection thực sự, share mode ra sao? | Số request đồng thời và thời gian chiếm giữ connection là bao nhiêu? |

## 4. Những tình huống KHÔNG cần pool với Lettuce

### 4.1. API thông thường chỉ đọc/ghi key nhanh

Ví dụ ứng dụng Spring Boot có:

~~~java
@Service
public class ProductAvailabilityService {
    private final StringRedisTemplate redis;

    public ProductAvailabilityService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String currentStatus(String productId) {
        String value = redis.opsForValue()
                .get("shop:product:status:" + productId);
        return value == null ? "unknown" : value;
    }
}
~~~

Nếu mỗi request chỉ thực hiện `GET` đơn giản, không giữ transaction và không dùng lệnh blocking, kết nối dùng chung của Lettuce thường đã đáp ứng tốt. Số request HTTP nhiều không phải lý do độc lập để tạo nhiều socket Redis.

Tập trung cải thiện:

- Thiết kế key để đọc đúng dữ liệu với ít lệnh.
- Giữ giá trị hợp lý về kích thước; tránh tải object lớn không cần thiết.
- Dùng cache đúng nơi có tỷ lệ hit đủ cao.
- Theo dõi latency ở phía ứng dụng và Redis.
- Cấu hình timeout và cơ chế xử lý Redis gián đoạn.

### 4.2. Ứng dụng nhỏ hoặc ít giao tiếp Redis

Một ứng dụng dùng Redis để lưu trạng thái ngắn hạn, mỗi giây chỉ có vài lệnh, không cần tự cấu hình pool nếu không có nhu cầu cụ thể. Một pool có `min-idle` cao còn có thể duy trì nhiều connection không dùng đến.

### 4.3. Workload reactive và mô hình non-blocking

Với `ReactiveRedisTemplate` và Lettuce, không nên mặc định áp dụng tư duy “mỗi request giữ một thread và một connection”. Thiết kế reactive cần quan tâm đến backpressure, thời gian xử lý, lượng lệnh gửi đồng thời và giới hạn tài nguyên. Pool truyền thống không tự giải quyết các điểm này.

Reactive không có nghĩa không bao giờ cần connection chuyên biệt. Các tác vụ subscription/streaming hay trường hợp cần cô lập vẫn cần đánh giá; nhưng đặt pool lớn ngay từ đầu thường không phải bước tối ưu đầu tiên.

### 4.4. Khi bottleneck nằm ở Redis hoặc mạng

Nếu Redis xử lý lệnh chậm do:

- Key hoặc value quá lớn.
- Một lệnh nặng (ví dụ duyệt nhiều phần tử, Lua/script không tối ưu).
- CPU, memory, I/O hoặc network phía server bị bão hòa.
- Quá nhiều key hết TTL cùng lúc làm tải dồn lên nguồn chính.
- Hot key chịu lưu lượng lớn hoặc đường mạng có độ trễ cao.

thì pool khó giải quyết tận gốc. Cần xác định command latency, server CPU, slow log, kích thước payload, số round trip và phân bố tải. Việc tăng connection có thể chỉ giúp gửi thêm lệnh đến server vốn đã quá tải.

## 5. Những tình huống CÓ THỂ cần pool

Từ “có thể” ở đây quan trọng: hãy xem thời gian giữ connection, tính song song và số connection có sẵn trước khi quyết định.

### 5.1. Nhiều thao tác Redis blocking đồng thời

Một consumer dùng `BLPOP` chờ công việc có thể chiếm connection trong vài giây hoặc lâu hơn. Nếu ứng dụng có nhiều consumer như vậy, các connection riêng cần đủ để chúng hoạt động. Pool giúp tái sử dụng connection sau khi một lần chờ hoàn thành và giới hạn tổng số connection.

Ví dụ minh họa lệnh blocking với `StringRedisTemplate`:

~~~java
String task = stringRedisTemplate.opsForList()
        .leftPop("demo:job:queue", Duration.ofSeconds(5));
~~~

`leftPop(key, timeout)` có thể chờ đến khi có phần tử hoặc hết thời gian chờ. Đây là một kiểu hoạt động khác với `get(key)` thường trả nhanh. Nếu có 20 consumer gọi blocking cùng lúc, cần xem 20 luồng chờ đó đang chiếm bao nhiêu connection và pool có đáp ứng đủ hay không.

Đây là ví dụ cho mục tiêu học về connection. Với hàng đợi công việc cần xác nhận xử lý, retry hoặc bảo đảm giao hàng, cân nhắc Redis Streams hay hệ thống message broker phù hợp; không mặc định rằng `BLPOP` giải quyết mọi yêu cầu độ tin cậy.

### 5.2. Transaction và thao tác giữ trạng thái trên connection

Các lệnh `MULTI`/`EXEC` làm việc với trạng thái transaction trên connection. Trong Spring Data Redis, xử lý transaction cần cơ chế connection đúng ngữ cảnh; không được để lệnh từ nhiều request độc lập trộn vào một phiên transaction.

Nếu ứng dụng thường xuyên có nhiều transaction Redis chạy đồng thời, số connection dành cho các transaction có thể trở thành giới hạn. Pool giúp tái sử dụng các connection đó. Tuy nhiên, **bật pool không làm các lệnh trong transaction nhanh hơn**, cũng không biến giao dịch Redis thành giao dịch nguyên tử chung với database SQL.

### 5.3. Workload cần isolation giữa các luồng lệnh

Có những workload cần tách đường kết nối cho các loại công việc khác nhau, ví dụ:

- Một nhóm tác vụ blocking có nguy cơ giữ connection lâu.
- Các thao tác vận hành hoặc consumer riêng cần quản lý số connection độc lập.
- Hạ tầng có yêu cầu ranh giới kết nối mà shared native connection không đáp ứng.

Khi đó, có thể dùng factory riêng cho nhóm công việc có nhu cầu khác nhau, thay vì buộc mọi lệnh Redis của cả ứng dụng đi qua một pool. Cách này giúp đặt giới hạn và quan sát tác động theo đúng nguồn tải.

### 5.4. Khi client không cho phép chia sẻ một connection như Lettuce

Với Jedis, ứng dụng đa luồng có nhu cầu mượn/trả connection liên tục; pool thường giúp tránh việc tạo socket mới cho mỗi lời gọi. Quy mô pool vẫn phải dựa trên thực tế, không mặc định đặt bằng số HTTP worker thread.

### 5.5. Khi đo đạc cho thấy thiếu kết nối là nút thắt thật

Một số dấu hiệu phù hợp để khảo sát pool:

- Có thời gian chờ mượn connection đáng kể hoặc pool timeout/exception.
- Số active connection liên tục đạt giới hạn trong giờ cao điểm.
- Lượng connection mới được tạo/đóng rất lớn trong khi nhiều thao tác tương đối ngắn.
- Các blocking consumer thường xuyên thiếu connection để hoạt động song song.
- Sau khi tăng giới hạn pool có kiểm soát, throughput/latency cải thiện mà Redis server vẫn còn tài nguyên.

**Cần phân biệt:** nếu chỉ thấy request chậm nhưng Redis command đã tốn nhiều thời gian, tăng pool sẽ không giải quyết được latency. Nếu pool không bao giờ đầy, tăng `max-active` cũng không có lợi ích rõ rệt.

## 6. Bảng quyết định nhanh

| Tình huống | Client | Có nên dùng pool? | Lý do |
| --- | --- | --- | --- |
| REST API đọc `GET`/ghi `SET` ngắn | Lettuce | **Thường không** | Shared native connection thường đủ; ưu tiên đo latency |
| Bộ đếm dùng `INCR` ngắn | Lettuce | **Thường không** | Redis xử lý lệnh ngắn, không cần socket riêng/request |
| Cache thông thường qua Spring Cache Redis | Lettuce | **Thường không** | Chưa có bằng chứng cần connection pool chỉ vì cache có nhiều hit |
| Service nhỏ, traffic thấp | Lettuce | **Không cần mặc định** | Thêm cấu hình và connection idle không cần thiết |
| Nhiều consumer dùng `BLPOP` lâu | Lettuce | **Có thể cần** | Mỗi thao tác blocking có thể cần connection chuyên biệt |
| Nhiều transaction Redis đồng thời | Lettuce | **Có thể cần** | Transaction có ngữ cảnh connection riêng |
| Pub/Sub listener cố định | Lettuce | **Xem số subscription và vòng đời** | Kết nối chuyên dụng; pool lớn chưa chắc có lợi |
| Redis Streams consumer dùng blocking read | Lettuce | **Xem số consumer và cách quản lý connection** | Có thể chiếm connection trong lúc chờ |
| REST API đa luồng | Jedis | **Thường hữu ích** | Tái sử dụng connection dành cho từng thao tác |
| Redis CPU bão hòa hoặc lệnh chậm | Bất kỳ | **Không giải quyết bằng pool** | Bottleneck nằm ở server hoặc command |
| TLS handshake quá nhiều vì tạo connection mới liên tục | Tùy client | **Pool có thể giúp** | Tái sử dụng connection giảm số lần thiết lập |
| Muốn tăng tốc nhiều lệnh kế tiếp | Tùy client | **Đánh giá pipelining/batching** | Pool không giảm số round trip của một chuỗi lệnh |

**Nguyên tắc:** dùng cấu hình đơn giản nhất phù hợp workload. Chỉ thêm pool khi cần quản lý các connection riêng hoặc số liệu cho thấy nó cải thiện kết quả.

## 7. Spring Boot: cấu hình Lettuce không pool

Với Spring Boot 3.x, cách bắt đầu phổ biến là chỉ thêm starter và cấu hình endpoint:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 2s
~~~

Trong cấu hình thông thường, Spring Boot tự tạo `LettuceConnectionFactory` và template phù hợp khi chưa có bean do ứng dụng tự khai báo. Lettuce chia sẻ native connection theo mặc định cho các lệnh đủ điều kiện; không cần tự khai báo pool chỉ để chạy đoạn code:

~~~java
@Service
public class CounterService {
    private final StringRedisTemplate redis;

    public CounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long increment(String key) {
        Long value = redis.opsForValue().increment(key);
        if (value == null) {
            throw new IllegalStateException("Redis did not return a count");
        }
        return value;
    }
}
~~~

**Lưu ý:** timeout không đồng nghĩa chiến lược retry. Nếu `INCR` đã được Redis xử lý nhưng response bị mất, gửi lại có thể tăng hai lần. Ứng dụng phải phân biệt thao tác idempotent với thao tác không idempotent trước khi retry.

## 8. Spring Boot: bật pool khi có nhu cầu

Nếu các kết nối riêng của Lettuce cần được tái sử dụng, có thể sử dụng hỗ trợ pooling qua **Apache Commons Pool 2**.

Thêm dependency (để Spring Boot dependency management chọn phiên bản phù hợp):

~~~xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-pool2</artifactId>
</dependency>
~~~

Khi dùng cấu hình pool của Spring Boot 3.x, ví dụ:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      client-type: lettuce
      connect-timeout: 2s
      timeout: 2s
      lettuce:
        pool:
          enabled: true
          max-active: 12
          max-idle: 8
          min-idle: 0
          max-wait: 500ms
~~~

Giải thích các thuộc tính:

| Thuộc tính | Ý nghĩa | Sai lầm cần tránh |
| --- | --- | --- |
| `max-active` | Giới hạn số connection có thể đang được mượn trong pool của một application instance | Nhầm là giới hạn toàn bộ client Redis trong cluster ứng dụng |
| `max-idle` | Giới hạn số connection đang rảnh mà pool giữ lại | Đặt quá lớn khiến nhiều connection không phục vụ việc gì |
| `min-idle` | Số connection rảnh pool cố gắng duy trì theo chính sách pool | Đặt cao trên nhiều replica có thể tăng số socket idle rất lớn |
| `max-wait` | Thời gian tối đa một lần mượn connection chờ khi pool cạn | Đặt vô hạn gây request chờ dây chuyền; đặt quá nhỏ gây lỗi dưới tải tăng đột biến |
| `enabled` | Bật cấu hình pooling khi môi trường/dependency hỗ trợ | Nhầm với việc tất cả lệnh Lettuce đều mượn connection từ pool |

Các con số 12/8/0/500ms là **giá trị minh họa**, không phải khuyến nghị dùng chung cho mọi dự án. Cần biết số connection riêng thực sự cần trước khi thay đổi.

**Chú ý về phiên bản:** tên thuộc tính và điều kiện kích hoạt pooling khác nhau giữa các dòng Spring Boot. Ví dụ trên dùng namespace `spring.data.redis.*` trong Spring Boot 3.x; không sao chép nguyên sang các dòng Boot cũ rồi mặc định rằng đã được áp dụng.

### 8.1. Cấu hình pool chưa chắc khiến lệnh thường đi qua pool

Giả sử ứng dụng dùng Lettuce, `shareNativeConnection=true` và 500 request HTTP cùng chạy `GET`. Dù trong YAML có `max-active: 12`, **không nên coi 12 là số socket tối đa phục vụ 500 `GET` đó**. Các lệnh đủ điều kiện vẫn có thể dùng shared native connection; pool được dùng ở những thời điểm factory cần connection riêng.

Muốn đánh giá pool, phải biết chính xác phương thức sử dụng kết nối và client setup. Tránh kết luận sai chỉ từ số thread, số request hoặc việc nhìn thấy dependency `commons-pool2`.

### 8.2. Khi nào cần `max-wait`?

Ví dụ có tối đa 12 connection để phục vụ blocking consumers. Nếu cả 12 connection đang bận và consumer thứ 13 cần mượn:

~~~text
Consumer 1..12 -> đã mượn hết 12 connection
Consumer 13    -> chờ connection được trả lại
                     |
                     +-- có connection trước 500ms -> tiếp tục
                     |
                     +-- chờ vượt max-wait -> lỗi mượn connection
~~~

`max-wait` giúp giới hạn thời gian chờ ở pool. Nó khác với **command timeout** (chờ lệnh Redis trả kết quả) và **connect timeout** (chờ tạo kết nối mạng). Một request có thể trải qua nhiều giai đoạn chờ, nên tổng thời gian vượt quá một timeout đơn lẻ nếu ứng dụng không đặt deadline tổng thể.

## 9. Tự cấu hình `LettuceConnectionFactory` và pool bằng Java

Nếu dự án không dùng auto-configuration, hoặc cần kiểm soát factory riêng, có thể tạo bean thủ công. Ví dụ dưới đây dùng Redis standalone và thư viện Lettuce qua Spring Data Redis.

### 9.1. Factory không dùng pool

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class SimpleRedisConfig {

    @Bean
    RedisConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("localhost", 6379);

        LettuceClientConfiguration client =
                LettuceClientConfiguration.builder()
                        .commandTimeout(Duration.ofSeconds(2))
                        .build();

        return new LettuceConnectionFactory(server, client);
    }

    @Bean
    StringRedisTemplate stringRedisTemplate(RedisConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }
}
~~~

Ở đây factory mặc định dùng chia sẻ native connection khi phù hợp. Cấu hình này thường đủ cho service chỉ thực hiện các thao tác key-value ngắn. Một ứng dụng chỉ cần **một** cấu hình factory chính; đừng tạo đồng thời hai class cấu hình có cùng tên bean trong cùng context.

### 9.2. Factory có Lettuce pool

Nếu có yêu cầu pool, cần dependency `commons-pool2`. Ví dụ sử dụng `LettucePoolingClientConfiguration`:

~~~java
import java.time.Duration;

import io.lettuce.core.api.StatefulConnection;
import org.apache.commons.pool2.impl.GenericObjectPoolConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettucePoolingClientConfiguration;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class PooledRedisConfig {

    @Bean
    RedisConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("localhost", 6379);

        GenericObjectPoolConfig<StatefulConnection<?, ?>> pool =
                new GenericObjectPoolConfig<>();
        pool.setMaxTotal(12);
        pool.setMaxIdle(8);
        pool.setMinIdle(0);
        pool.setMaxWait(Duration.ofMillis(500));

        LettuceClientConfiguration client =
                LettucePoolingClientConfiguration.builder()
                        .poolConfig(pool)
                        .commandTimeout(Duration.ofSeconds(2))
                        .build();

        return new LettuceConnectionFactory(server, client);
    }

    @Bean
    StringRedisTemplate stringRedisTemplate(RedisConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }
}
~~~

Ý nghĩa:

1. `RedisStandaloneConfiguration` chỉ định Redis endpoint.
2. `GenericObjectPoolConfig` quy định số connection active/idle và thời gian chờ khi mượn.
3. `LettucePoolingClientConfiguration` kết hợp client Lettuce với pool.
4. `LettuceConnectionFactory` cấp connection cho các thao tác Spring Data Redis.
5. `StringRedisTemplate` không cần biết pool được cấu hình như thế nào; service vẫn gọi Redis API quen thuộc.

Đây là ví dụ cấu hình **pool có sẵn cho những kết nối riêng mà factory yêu cầu**. Factory mặc định vẫn chia sẻ native connection cho các lệnh phù hợp; pool không tự thay đổi ngữ nghĩa `GET`/`SET` thông thường. Nếu bạn đang dùng Spring Boot auto-configuration, không cần tạo thêm factory này song song với một factory khác cùng mục đích.

### 9.3. Buộc các logical connection mượn từ pool khi thực sự cần

Nếu mục tiêu cụ thể là để **các lệnh thông thường cũng mượn connection**, có thể tắt chia sẻ native connection trên factory đã cấu hình pooling:

~~~java
LettuceConnectionFactory factory =
        new LettuceConnectionFactory(server, client);
factory.setShareNativeConnection(false);
return factory;
~~~

Đặt các dòng trên thay cho `return new LettuceConnectionFactory(server, client);` trong method tạo factory ở phần 9.2. Không đặt hai đoạn `return` cùng lúc trong method.

Điều cần hiểu trước khi áp dụng:

- Đây là **thay đổi hành vi quản lý connection**, không đơn thuần bật một công tắc tối ưu tốc độ.
- Mọi thao tác mượn connection đều chịu `maxTotal`/`maxWait`; khi pool cạn, request có thể bị giữ ở hàng chờ.
- Khi tăng số connection, Redis cần phục vụ thêm socket và bộ nhớ client.
- Với workload chủ yếu `GET`/`SET`, chia sẻ native connection có thể hiệu quả hơn.

Không dùng `setShareNativeConnection(false)` như giải pháp chung cho lỗi connection, timeout hoặc lưu lượng lớn. Chỉ sử dụng sau khi hiểu workload và có đo đạc.

### 9.4. Nếu dùng Jedis?

Spring Boot có thể cấu hình Redis client là Jedis khi dependency và phiên bản phù hợp:

~~~yaml
spring:
  data:
    redis:
      client-type: jedis
      host: localhost
      port: 6379
      jedis:
        pool:
          enabled: true
          max-active: 12
          max-idle: 8
          min-idle: 0
          max-wait: 500ms
~~~

Phải bổ sung thư viện Jedis tương ứng, thường cần điều chỉnh dependency để tránh kéo client không sử dụng. Không áp dụng các cấu hình `lettuce.pool.*` để mong điều chỉnh Jedis. Khi tự tạo `JedisConnectionFactory`, hãy dùng `JedisClientConfiguration` với pooling và cách chọn factory phù hợp phiên bản Spring Data Redis hiện tại.

Ví dụ YAML này minh họa việc **chọn client riêng**; không chạy đồng thời cả cấu hình Lettuce và Jedis rồi mặc định rằng cả hai pool đều được dùng.

## 10. Chọn kích thước pool dựa trên số liệu

Không có một con số `max-active` phù hợp với mọi ứng dụng. Cần biết **mỗi thao tác giữ connection bao lâu** và **có bao nhiêu thao tác thực sự cần mượn connection cùng lúc**.

### 10.1. Ước lượng bước đầu

Một cách ước lượng sơ bộ, khi luồng công việc ổn định:

~~~text
Số connection bận trung bình
    ≈ Số thao tác mượn connection mỗi giây
      × Thời gian giữ mỗi connection (giây)
~~~

Ví dụ **giả định**:

- Một application instance có 100 thao tác/giây thực sự mượn connection riêng.
- Mỗi thao tác giữ connection trung bình 20 ms = 0,02 giây.
- Số connection bận trung bình ước lượng: 100 × 0,02 = 2.

Con số 2 là **trung bình**, chưa thể dùng làm kích thước pool cuối cùng: lưu lượng có đỉnh, thời gian giữ có p95/p99 và các tác vụ blocking có thể chiếm connection lâu hơn nhiều. Có thể thử một khoảng nhỏ có dư địa, ví dụ 4–8, rồi kiểm tra các chỉ số khi tăng tải. Đây là bài toán sizing theo **connection hold time**, không phải chỉ theo số request HTTP.

Ví dụ khác, 20 consumer đồng thời gọi `BLPOP` và mỗi consumer có thể chờ vài giây. Nếu chúng thực sự cần 20 connection chuyên biệt cùng lúc, pool `maxTotal=5` có thể khiến 15 consumer chờ lượt. Tăng pool lên mức phù hợp hoặc điều chỉnh số consumer mới là quyết định liên quan trực tiếp đến workload.

### 10.2. Số replica phải tính vào tổng số connection

Pool được cấu hình theo **mỗi application instance**, không phải một giới hạn toàn hệ thống.

~~~text
12 ứng dụng/replica × tối đa 16 pooled connections
    = 192 pooled connections tiềm năng
~~~

Phép tính này mới xét một nhóm pool. Redis còn có shared connections, Pub/Sub connections, health checks, kết nối quản trị, các service khác và kết nối nội bộ tùy topology. Khi triển khai thêm replica, tổng connection có thể tăng dù YAML không đổi.

Điều cần kiểm tra trên server:

- Giới hạn `maxclients` của Redis và giới hạn file descriptors hệ điều hành.
- Bộ nhớ cho connection buffers, nhất là client đọc chậm hoặc trả payload lớn.
- Số lượng connection thực tế và tốc độ tạo/đóng.
- Năng lực network, CPU và giới hạn phía load balancer/proxy nếu có.
- Nếu Redis Cluster, connection có thể tồn tại đến nhiều node, không nhất thiết chỉ một endpoint.

**Đừng đặt `max-active: 1000` chỉ vì máy chủ cho phép 1000 client.** Pool lớn có thể che lấp vấn đề chậm lệnh, làm tăng concurrency gửi vào Redis và khiến sự cố trầm trọng hơn.

### 10.3. MaxIdle, MinIdle và MaxWait

Tư duy ban đầu:

- **max-active / maxTotal:** đặt theo số connection đồng thời cần thiết ở giờ cao điểm, có dư địa vừa phải.
- **max-idle:** giữ một số connection đủ để tránh tạo lại liên tục; quá cao gây lãng phí tài nguyên.
- **min-idle:** chỉ cần dương nếu thực sự muốn giữ connection nóng; với service ít tải, `0` thường là khởi điểm hợp lý.
- **max-wait:** phải phù hợp deadline request; chờ quá lâu có thể khiến queue dồn lại, còn chờ quá ngắn tạo lỗi khi tải tăng bất chợt.

Đừng nhầm **pool wait timeout** với **Redis command timeout**. Một request có thể mất thời gian chờ pool, rồi mới bắt đầu chờ Redis trả lệnh.

## 11. Các chỉ số nên đo trước và sau khi dùng pool

### 11.1. Phía ứng dụng

| Chỉ số | Điều muốn biết |
| --- | --- |
| p50/p95/p99 Redis operation latency | Thời gian chờ Redis thay đổi ra sao theo tải? |
| Pool active connections | Bao nhiêu connection đang được mượn? |
| Pool idle connections | Có bao nhiêu connection đang rảnh? |
| Pool pending/waiters và borrow wait time | Tác vụ có bị giữ lại vì chờ connection không? |
| Pool exhaustion / borrow timeout | Có yêu cầu mượn bị từ chối vì vượt `maxWait` không? |
| Timeout/error rate | Lỗi xuất phát ở pool, mạng hay Redis command? |
| Throughput | Hoàn thành bao nhiêu thao tác/giây ở latency chấp nhận được? |
| Số consumer/transaction đồng thời | Có nhóm giữ connection quá lâu không? |

Tùy cách cấu hình Lettuce và phiên bản thư viện, metric pool có thể không được công bố tự động dưới các tên trên. Nếu hệ thống chưa expose, cần instrument hoặc thu thập từ thành phần pool phù hợp. Không giả định một dashboard có sẵn chỉ vì đã thêm `commons-pool2`.

### 11.2. Phía Redis

Redis cung cấp một số lệnh hỗ trợ quan sát:

~~~redis
INFO clients
INFO stats
INFO commandstats
INFO memory
SLOWLOG GET 10
LATENCY LATEST
~~~

Những chỉ số/tín hiệu thường cần xem gồm:

- Số client đang kết nối và bị chặn (blocked clients).
- Lệnh được xử lý theo loại, thời gian thực thi trung bình của command.
- Số timeout/network error ghi nhận ở phía ứng dụng.
- Dung lượng bộ nhớ, mức tải CPU, command nặng, key/value quá lớn.
- Latency tăng ngay cả khi pool còn nhiều idle connection.

Lệnh `SLOWLOG` ghi nhận thời gian thực thi lệnh ở phía Redis, không bao gồm toàn bộ thời gian truyền mạng và chờ pool phía ứng dụng. Vì vậy phải ghép thông tin từ cả hai phía.

### 11.3. Thử nghiệm A/B có kiểm soát

Một quy trình thực hành:

1. Dùng workload thật hoặc mô phỏng có cùng tỷ lệ `GET`, `SET`, blocking/transaction, kích thước payload và số request đồng thời.
2. Ghi số liệu ở cấu hình Lettuce chia sẻ native connection, chưa bật pool cho tất cả lệnh.
3. Nếu workload có dedicated connections, bật pooling với số lượng vừa đủ; so sánh error rate, p95/p99 và borrow wait.
4. Chỉ thử `shareNativeConnection=false` khi có giả thuyết cụ thể và hiểu tác động tới toàn bộ lệnh.
5. Tăng tải từng bước; theo dõi Redis CPU, client connections và tài nguyên server.
6. Giữ cấu hình có lợi ích đo được, không chỉ dựa vào throughput đỉnh khi độ trễ hoặc lỗi vượt mục tiêu.

Không cần dùng số liệu của một lần benchmark nhẹ tải để suy luận cho production. Redis cache nóng có thể khác hoàn toàn lúc cold start, traffic dồn sau deploy hoặc một số consumer mất kết nối rồi tái kết nối đồng thời.

## 12. Pool, concurrency, pipeline và batch khác nhau thế nào?

Các thuật ngữ hay bị trộn lẫn:

| Kỹ thuật | Giải quyết vấn đề chính | Không tự giải quyết |
| --- | --- | --- |
| **Connection pooling** | Tái sử dụng connection chuyên biệt và giới hạn số connection đồng thời | Không làm một lệnh Redis chậm trở nên nhanh |
| **Multiplexing (Lettuce)** | Nhiều yêu cầu có thể dùng một native connection theo mô hình client thích hợp | Không biến blocking/transaction thành thao tác vô trạng thái |
| **Pipelining** | Gửi nhiều lệnh mà không chờ từng phản hồi riêng, giảm round trip | Không đảm bảo nhóm lệnh nguyên tử |
| **Batching** | Gom công việc/đơn vị dữ liệu để giảm overhead khi phù hợp | Không tự bảo đảm transaction |
| **Caching** | Tránh tính toán/đọc nguồn chính lặp lại cho dữ liệu có thể tái sử dụng | Không tự xử lý stale data hoặc cache stampede |
| **Scaling Redis** | Tăng năng lực hạ tầng theo topology và pattern truy cập | Không sửa key design hoặc lệnh không hiệu quả |

Ví dụ một request cần đọc 50 key. Tăng pool từ 8 lên 64 không làm biến mất 50 lần trao đổi mạng nếu mã cứ gửi `GET` rồi chờ kết quả từng lần. Có thể cân nhắc `MGET` khi phù hợp hoặc cơ chế pipelining, đồng thời đánh giá key cùng slot khi dùng Redis Cluster.

Trong Spring Data Redis, một cách thao tác pipeline qua `RedisTemplate` là `executePipelined(...)`. Cần hiểu serializer của kết quả và vòng đời connection trong pipeline. Pool không thay thế phương pháp giảm round trip.

## 13. Kết nối đặc biệt: blocking, Pub/Sub, Stream và transaction

### 13.1. Blocking queue consumers

~~~text
Consumer 1 ------ BLPOP queue (chờ 5s) ------> nhận item
Consumer 2 ------ BLPOP queue (chờ 5s) ------> timeout
Consumer 3 ------ BLPOP queue (chờ 5s) ------> nhận item
~~~

Nếu một consumer giữ dedicated connection trong thời gian chờ, tăng số consumer kéo theo nhu cầu connection. Pool quá nhỏ có thể khiến một số consumer còn chưa gửi lệnh Redis vì vẫn chờ mượn connection.

Trong thiết kế queue, cần phân biệt:

- **Thời gian chờ mượn connection** ở application/pool.
- **Thời gian blocking command chờ dữ liệu** trên Redis.
- **Thời gian xử lý job** sau khi lấy được item.

Sau khi nhận item, worker nên xử lý job ngoài thời gian giữ connection nếu API/thiết kế cho phép, tránh mượn connection suốt quá trình xử lý nghiệp vụ không cần Redis.

### 13.2. Pub/Sub

Redis Pub/Sub dùng connection đăng ký nhận message liên tục. Một listener container thường quản lý subscription connection theo vòng đời của nó, không tương đương với mỗi message mượn một connection từ pool. Một service có vài subscription cố định có thể cần vài connection chuyên dụng chứ không phải pool lớn.

Pub/Sub cũng không lưu lại thông điệp cho subscriber offline theo cách một durable queue thường làm. Nếu cần consumer group, xác nhận xử lý và đọc lại, hãy xem xét Redis Streams hoặc hệ thống message broker khác.

### 13.3. Redis Streams

Các consumer dùng `XREADGROUP` với chế độ block có thể đợi message, dẫn đến nhu cầu quản lý dedicated connections/độ đồng thời. Số consumer, thời gian block, topology, cách listener container dùng kết nối và retry đều ảnh hưởng đến sizing. Pool là một phần trong tài nguyên vận hành, không phải cơ chế bảo đảm message đã được xử lý thành công.

### 13.4. Transaction

Nếu một chuỗi lệnh phải gắn vào cùng ngữ cảnh Redis transaction, connection được giữ theo ranh giới transaction tương ứng. Không được “trả connection về pool” giữa `MULTI` và `EXEC` theo cách phá vỡ ngữ nghĩa transaction. Spring Data Redis có API hỗ trợ thực thi trong ngữ cảnh connection/transaction thích hợp; ứng dụng phải tuân thủ cách dùng đó.

Với transaction kéo dài quá lâu, kết nối bị chiếm trong thời gian dài và pool dễ cạn. Cải thiện thiết kế giao dịch và giảm thời gian giữ connection thường hữu ích hơn chỉ tăng pool.

## 14. Lỗi thường gặp và cách xác định nguyên nhân

| Dấu hiệu | Nghi vấn | Việc cần làm |
| --- | --- | --- |
| Pool báo không mượn được connection | `maxTotal` nhỏ, connection bị giữ lâu, hoặc leak | Xem active/idle/waiters, phân tích blocking/transaction và thời gian giữ |
| Pool còn idle nhiều nhưng request vẫn chậm | Redis command, mạng hoặc xử lý ứng dụng chậm | Đo command latency, slow log và trace request |
| Tăng `max-active` nhưng throughput không tăng | Redis hoặc downstream đã bão hòa, lệnh tuần tự, shared mode | Đo server CPU, round trip, kết nối thực được sử dụng |
| Nhiều socket Redis dù traffic ít | `min-idle` lớn, nhiều replica, mỗi service có factory riêng | Nhân số instance, liệt kê connection sources và điều chỉnh idle |
| Redis báo too many clients | Tổng connection toàn cụm ứng dụng vượt giới hạn | Kiểm tra `INFO clients`, `maxclients`, replica và pools khác |
| `RedisConnectionFailureException` | Redis không chạy, mạng, DNS, ACL/TLS | Kiểm tra endpoint, auth/TLS, socket, health |
| Socket timeout | Lệnh không kịp phản hồi hoặc network chậm | Xem command timeout, blocking command, server latency |
| Request timeout trước khi lệnh chạy | Chờ pool quá lâu | Đo borrow wait, `max-wait` và số active |
| Redis client đang dùng không như dự kiến | Dependency/client-type auto-config không đúng | Kiểm tra loại `RedisConnectionFactory` thực tế và dependencies |
| Pooled config nhưng không thấy nhiều connection cho `GET` | Lettuce vẫn chia sẻ native connection | Xác nhận `shareNativeConnection` trước khi suy luận pool không hoạt động |
| Dùng `BLPOP` rồi lệnh khác chậm bất thường | Thiếu dedicated connection hoặc pool bị chiếm | Tách blocking workload, đo số consumer và connection |
| Triển khai thêm replica khiến Redis nhiều client | Pool giới hạn theo instance chứ không toàn hệ thống | Tính tổng số connection sau khi scale out |

### 14.1. Phân biệt ba loại timeout

~~~text
Ứng dụng muốn gọi Redis
    |
    +-- [A] Chờ mượn connection từ pool
    |          -> max-wait
    |
    +-- [B] Nếu tạo connection mới: kết nối tới server
    |          -> connect-timeout
    |
    +-- [C] Gửi lệnh và chờ Redis phản hồi
               -> command timeout
~~~

Ba khoảng thời gian này không đồng nhất. Ví dụ `max-wait=500ms`, `connect-timeout=2s` và `command-timeout=2s` không có nghĩa request tổng thể luôn kết thúc trong 2 giây. Để kiểm soát SLA, cần deadline toàn request, xử lý lỗi phù hợp và theo dõi từng giai đoạn.

**Cảnh báo retry:** Khi `INCR` hoặc ghi dữ liệu bị timeout, có thể lệnh đã thực thi ở Redis nhưng client chưa nhận kết quả. Retry tự động có thể làm tăng bộ đếm hoặc ghi lặp. Pool không giải quyết vấn đề tính đúng đắn này.

### 14.2. Kết nối có bị “rò rỉ” không?

Khi dùng `RedisTemplate` đúng cách, Spring Data Redis quản lý vòng đời của connection cho thao tác thông thường. Rủi ro giữ connection thường liên quan đến tự gọi API cấp thấp, listener/consumer dài hạn, transaction không được kết thúc đúng cách hoặc logic điều khiển connection ngoài cơ chế template.

Với code dùng `RedisConnectionFactory.getConnection()` trực tiếp, cần tuân thủ quy tắc đóng/giải phóng connection theo API tương ứng. Không giữ một logical `RedisConnection` tùy tiện làm field singleton rồi sử dụng đồng thời từ mọi thread.

### 14.3. Tại sao mỗi request chậm dù pool lớn?

Hình dung Redis server bị CPU quá tải vì một command phức tạp. Tăng pool khiến thêm request đi vào server, nhưng command nặng vẫn chiếm tài nguyên. Kết quả có thể là latency p99 tăng. Cần xem các lệnh chậm, dữ liệu đọc/ghi lớn, số round trip và chính sách giới hạn concurrency phía ứng dụng thay vì chỉ tăng connection.

## 15. Thiết kế tài nguyên khi có nhiều loại công việc

Một ứng dụng có thể vừa phục vụ API, vừa tiêu thụ queue và vừa nhận Pub/Sub:

~~~text
                 Spring Boot Application
             +-----------------------------+
HTTP API --->| GET/SET/INCR (Lettuce share) |----+
             |                             |    |
Worker  ---->| BLPOP/XREAD BLOCK           |----+---> Redis
             | (dedicated connections)     |    |
Listener --->| Pub/Sub subscription        |----+
             +-----------------------------+
~~~

Một cấu hình pool duy nhất có thể khó biểu đạt hết nhu cầu nếu nhóm worker giữ connection lâu còn HTTP API cần latency thấp. Khi đó cân nhắc:

1. Giữ đường kết nối thông thường của API trên Lettuce shared native connection.
2. Quản lý riêng số worker/consumer blocking phù hợp năng lực xử lý và connection chuyên dụng.
3. Nếu cần, tách `RedisConnectionFactory` hoặc cấu hình client cho từng nhóm công việc và inject template bằng `@Qualifier`.
4. Theo dõi số socket **trên mỗi application instance** và tổng kết nối đến Redis.
5. Không để consumer số lượng lớn chiếm hết pool mà các thao tác khác cũng phải mượn.

Lưu ý: thêm nhiều factory còn có chi phí riêng, như client resources, connection, health checks và cấu hình xác thực. Chỉ tách khi có lý do về vận hành hoặc cách ly công việc.

## 16. Lộ trình chọn cấu hình trong dự án thật

Có thể áp dụng chuỗi quyết định:

~~~text
Đang sử dụng client nào?
   |
   +-- Lettuce
   |     |
   |     +-- Chủ yếu GET/SET/INCR, không blocking/transaction?
   |     |       |
   |     |       +-- Có -> Bắt đầu với shared native connection
   |     |       |          Đo latency, errors, server load
   |     |       |
   |     |       +-- Không -> Xác định số dedicated connections
   |     |                  Đo thời gian giữ/độ đồng thời
   |     |                  Cân nhắc pool phù hợp
   |     |
   |     +-- Muốn tắt shareNativeConnection?
   |             |
   |             +-- Chỉ khi có yêu cầu và dữ liệu chứng minh
   |
   +-- Jedis
         |
         +-- Nhiều tác vụ đồng thời?
                 |
                 +-- Có -> Dùng pool phù hợp, đo borrow wait
                 +-- Ít -> Cấu hình nhỏ, tránh tạo socket thừa
~~~

Với bất kỳ nhánh nào, nếu Redis CPU cao, command chậm, dữ liệu quá lớn hoặc network latency cao, hãy xử lý đúng nguyên nhân trước khi tăng pool.

### 16.1. Bắt đầu từ cấu hình đơn giản

Đối với Spring Boot + Lettuce chỉ có GET/SET:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      timeout: 2s
~~~

Địa chỉ `redis.internal` là ví dụ; môi trường thật cần TLS/ACL và secret nếu Redis yêu cầu, đồng thời phải đặt hostname/port đúng nơi triển khai. Không đưa password vào repository.

Chỉ thêm pool khi đo được nhu cầu connection riêng hoặc có yêu cầu ứng dụng rõ ràng.

### 16.2. Đặt giới hạn trong bối cảnh toàn hệ thống

Giả sử:

- 8 replica của service API.
- Mỗi replica có nhóm worker cần tối đa 10 dedicated connections.
- Một service nền khác có 4 replica, mỗi replica có pool tối đa 15 connections.

Tổng số pooled connections tiềm năng:

~~~text
8 × 10 + 4 × 15 = 140 connections
~~~

Đây không phải số connection Redis thực luôn có, cũng chưa tính shared/subscription/monitoring connections. Nhưng nó nhắc bạn rằng cấu hình pool theo một instance có tác động gấp nhiều lần khi mở rộng hệ thống.

### 16.3. Pool sizing là quá trình đo và điều chỉnh

Không nên chỉ nhìn một lần test thành công. Hãy quan sát cả:

- Lưu lượng bình thường và giờ cao điểm.
- Cold start và warm traffic.
- Khi Redis mất kết nối rồi phục hồi, nhiều instance đồng loạt reconnect.
- Khi consumer blocking tăng số lượng.
- Khi deploy số replica lớn hơn.
- Khi Redis phục vụ thêm service mới.

Mục đích là tìm mức connection cần thiết để đáp ứng latency và tỷ lệ lỗi, đồng thời giữ tài nguyên ứng dụng/Redis trong giới hạn an toàn.

## 17. Bài thực hành: so sánh không pool và có pool

### 17.1. Chuẩn bị

Chạy một Redis local bằng Docker:

~~~bash
docker run --name redis-pool-lab -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-pool-lab redis-cli PING
~~~

Nếu Redis local đã sử dụng port 6379, chọn port khác và cập nhật cấu hình ứng dụng tương ứng. Ví dụ dùng port được bind vào loopback, không mở Redis thử nghiệm ra Internet.

Tạo Spring Boot app có `spring-boot-starter-data-redis`, `StringRedisTemplate` và service gọi `GET`/`SET`/`INCR`. Không cần tạo một Redis connection mới trong mỗi lần request.

### 17.2. Thử nghiệm A — Lệnh ngắn với Lettuce mặc định

1. Chạy 1 instance với cấu hình Lettuce mặc định, không tự thêm pool.
2. Gửi một lượng request cố định gọi `GET`/`INCR` ở các mức concurrency tăng dần.
3. Ghi nhận throughput, p95/p99 latency, error rate.
4. Kiểm tra số client Redis bằng `INFO clients`.
5. Giải thích vì sao nhiều request có thể không tạo tương ứng số TCP connections.

Kết quả cần nhìn là hành vi thực tế của shared native connection, không phải cố chứng minh pool luôn nhanh hơn hoặc luôn chậm hơn.

### 17.3. Thử nghiệm B — Nhiều blocking consumers

1. Tạo nhiều consumer cùng gọi `leftPop("demo:jobs", Duration.ofSeconds(5))`.
2. Theo dõi số kết nối cần thiết khi consumer cùng chờ.
3. Bật pooling với giới hạn nhỏ, ví dụ `max-active=3` cho workload có nhiều consumer hơn.
4. Quan sát việc chờ mượn connection và lỗi khi `max-wait` không đủ.
5. Điều chỉnh số consumer hoặc max-active; so sánh với tải thực tế.
6. Dừng consumer đúng cách, xác nhận connection được trả/giải phóng.

Không dùng ví dụ này để tạo một production queue không có cơ chế retry/ack. Mục tiêu ở đây là **hiểu connection occupancy**.

### 17.4. Thử nghiệm C — Cấu hình manual factory

1. Tạo `LettuceConnectionFactory` với `LettucePoolingClientConfiguration` như phần 9.2.
2. Xác nhận với `shareNativeConnection=true`, các lệnh thông thường không nhất thiết sử dụng pool.
3. Trong môi trường lab riêng, thử `setShareNativeConnection(false)` để các thao tác thường đi qua cơ chế pooled connection.
4. Dùng pool nhỏ và tải đủ lớn để quan sát giới hạn `maxTotal`/`maxWait`.
5. Trả lại cấu hình thích hợp sau khi so sánh, không mặc định giữ `false`.

### 17.5. Ghi bảng kết quả

| Cấu hình | Loại lệnh | Concurrency | p95 latency | Redis connected clients | Pool wait | Error rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Lettuce share | GET/INCR | Tự đo | Tự đo | Tự đo | Không áp dụng/tuỳ setup | Tự đo |
| Lettuce pool, share mặc định | Blocking read | Tự đo | Tự đo | Tự đo | Tự đo nếu có | Tự đo |
| Lettuce pool, share=false | GET/INCR | Tự đo | Tự đo | Tự đo | Tự đo | Tự đo |

Đừng điền số liệu giả làm kết quả benchmark. Mỗi môi trường có mạng, Redis version, CPU, kích thước dữ liệu và load khác nhau nên cần ghi rõ điều kiện đo.

## 18. Câu hỏi tự ôn

1. Vì sao nhiều HTTP request không nhất thiết cần bấy nhiêu native Redis connections khi dùng Lettuce?
2. `RedisConnection` của Spring và native connection của Lettuce khác nhau thế nào?
3. `shareNativeConnection=true` ảnh hưởng ra sao đến nhu cầu pool cho `GET`/`SET`?
4. Bật `LettucePoolingClientConfiguration` có khiến mọi lệnh thường tự động mượn connection từ pool không?
5. Khi nào `setShareNativeConnection(false)` có thể hữu ích, và tại sao nó không nên là mặc định?
6. Vì sao Jedis thường dùng pool trong ứng dụng Java đa luồng?
7. `BLPOP` với thời gian chờ vài giây tạo áp lực connection khác `GET` như thế nào?
8. Pool `max-active=20` trên 10 replica có nghĩa gì đối với tổng số connection tiềm năng?
9. Khi p99 latency tăng nhưng pool không đầy, bạn sẽ đo những gì trước khi điều chỉnh?
10. `max-wait` khác `connect-timeout` và `command timeout` như thế nào?
11. Pool có thay thế được pipelining, `MGET` hay tối ưu Redis command không?
12. Vì sao retry `INCR` sau timeout có thể làm sai số đếm, dù pool hoạt động bình thường?
13. Làm thế nào để lựa chọn pool size từ số consumer, thời gian giữ connection và traffic peak?
14. Khi dùng Redis Cluster, tại sao số lượng connection thực tế cần xét theo nhiều node?
15. Khi nào việc tách factory cho blocking workers và API service giúp quản lý tài nguyên tốt hơn?

**Ghi nhớ:** Với **Lettuce và các lệnh Redis thông thường**, bắt đầu từ **shared native connection** là lựa chọn phù hợp trong nhiều dự án Spring Data Redis. **Pool hữu ích khi cần quản lý và tái sử dụng các kết nối chuyên biệt**, nhất là các tác vụ giữ connection lâu hoặc khi client đòi hỏi mỗi thao tác có connection riêng như Jedis. Quyết định và kích thước pool phải được kiểm chứng bằng latency, số kết nối thực tế, thời gian chờ mượn connection và khả năng của Redis server.
