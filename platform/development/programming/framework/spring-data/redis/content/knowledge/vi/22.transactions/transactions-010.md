# Tương tác với @Transactional và transaction manager bên ngoài Redis

Trong ứng dụng Spring Boot, một phương thức nghiệp vụ có thể vừa ghi vào cơ sở dữ liệu quan hệ vừa thao tác Redis. Việc thêm `@Transactional` lên phương thức khiến nhiều lập trình viên nghĩ rằng **cả SQL và Redis sẽ cùng commit hoặc cùng rollback như một giao dịch duy nhất**. Đây là một suy luận nguy hiểm.

Spring Data Redis có hỗ trợ giao dịch Redis thông qua `MULTI`/`EXEC`, đồng thời có thể **đồng bộ việc sử dụng kết nối Redis với giao dịch Spring đang hoạt động**. Nhưng Redis không tự trở thành một tài nguyên XA chỉ vì ứng dụng dùng chung `@Transactional` với `JpaTransactionManager` hoặc `DataSourceTransactionManager`. Muốn xây dựng tính nhất quán đúng, cần phân biệt giao dịch của hệ quản trị dữ liệu, transaction synchronization của Spring và các bảo đảm thực sự từ Redis.

Bài này tập trung vào trường hợp phổ biến: **một transaction manager bên ngoài Redis** đang quản lý giao dịch chính, còn ứng dụng muốn thao tác Redis trong cùng phương thức `@Transactional`.

## 1. Phân biệt ba lớp giao dịch

| Lớp | Thành phần | Tác dụng | Giới hạn |
|---|---|---|---|
| Giao dịch SQL/JPA | `DataSourceTransactionManager`, `JpaTransactionManager` | Bắt đầu, commit, rollback giao dịch trên database được quản lý | Không sở hữu trực tiếp Redis |
| Giao dịch Redis | `MULTI`, `EXEC`, `DISCARD` và `WATCH` | Queue rồi thực thi các lệnh Redis trong một giao dịch Redis | Không cung cấp rollback cho từng lệnh đã chạy trong `EXEC`; không tự bao gồm SQL |
| Đồng bộ giao dịch Spring | `@Transactional`, `TransactionSynchronizationManager` và hỗ trợ của `RedisTemplate` | Gắn vòng đời một kết nối/nhóm thao tác Redis với giao dịch Spring hiện tại | Không phải giao thức distributed two-phase commit giữa database và Redis |

Ví dụ phương thức:

```java
@Transactional
public void payOrder(Long orderId) {
    orderRepository.markPaid(orderId);     // Database
    redis.opsForValue().set(
            "orders:status:" + orderId,
            "PAID");                       // Redis
}
```

Ở đây, `@Transactional` lựa chọn một **Spring `PlatformTransactionManager`** phù hợp. Nếu transaction manager là JPA, giao dịch chính thuộc database. Việc Redis có thực sự được queue và tham gia cơ chế đồng bộ hay không còn phụ thuộc vào **template, cấu hình và luồng gọi**.

Không nên suy ra Redis được điều khiển bởi JPA manager chỉ vì hai lời gọi nằm trong cùng một phương thức Java.

## 2. Hành vi mặc định: RedisTemplate không tự tham gia Spring transaction

Spring Data Redis **không bật transaction support của `RedisTemplate` theo mặc định**. Khi dùng một `RedisTemplate` hoặc `StringRedisTemplate` chưa bật hỗ trợ transaction, một lệnh:

```java
redis.opsForValue().set("orders:status:42", "PAID");
```

thường được gửi đi và thực thi theo đường Redis bình thường tại thời điểm gọi, ngay cả khi luồng hiện tại có một giao dịch database đang mở.

Điều đó có thể tạo ra tình huống:

```text
T0  Bắt đầu @Transactional (giao dịch SQL)
T1  UPDATE orders SET status = 'PAID' WHERE id = 42   -- chưa commit SQL
T2  Redis SET orders:status:42 PAID                     -- đã ghi Redis
T3  Một thao tác SQL tiếp theo báo lỗi
T4  SQL ROLLBACK

Kết quả:
  Database: order 42 chưa được ghi PAID
  Redis:    orders:status:42 vẫn có thể là PAID
```

Đây là lý do không thể dùng riêng `@Transactional` của database để bảo đảm Redis tự rollback.

### Ví dụ lỗi có thể tái hiện

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.redis.core.StringRedisTemplate;

@Service
public class OrderStatusService {

    private final OrderRepository orders;
    private final StringRedisTemplate ordinaryRedisTemplate;

    public OrderStatusService(
            OrderRepository orders,
            StringRedisTemplate ordinaryRedisTemplate) {
        this.orders = orders;
        this.ordinaryRedisTemplate = ordinaryRedisTemplate;
    }

    @Transactional(transactionManager = "transactionManager")
    public void demonstrateRisk(long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.setStatus("PAID");

        ordinaryRedisTemplate.opsForValue().set(
                "orders:status:" + orderId, "PAID");

        throw new IllegalStateException("Demo database rollback");
    }
}
```

Ví dụ giả định ứng dụng có bean transaction manager của database tên `transactionManager`, một `OrderRepository` và entity `Order` phù hợp. Exception không được bắt trong phương thức khiến Spring đánh dấu rollback theo quy tắc mặc định cho unchecked exception. SQL bị rollback, nhưng một lệnh Redis đã chạy bên ngoài transaction support vẫn có thể tồn tại.

Điểm cần nhớ: **mặc định của template là yếu tố quyết định quan trọng**, không phải chỉ sự hiện diện của annotation `@Transactional`.

## 3. Bật Redis transaction support để đồng bộ với Spring transaction

Spring Data Redis hỗ trợ `RedisTemplate.setEnableTransactionSupport(true)`. Với cấu hình này, khi template được sử dụng trong một **Spring-managed transaction** đang hoạt động, nó có thể gắn kết nối Redis với ngữ cảnh giao dịch của luồng hiện tại.

Một ví dụ tạo template riêng cho nghiệp vụ cần đồng bộ transaction:

```java
package example.tx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class TransactionalRedisConfiguration {

    @Bean("transactionalRedisTemplate")
    public StringRedisTemplate transactionalRedisTemplate(
            RedisConnectionFactory factory) {

        StringRedisTemplate template =
                new StringRedisTemplate(factory);

        template.setEnableTransactionSupport(true);
        return template;
    }
}
```

Ví dụ phương thức sử dụng template trên cùng một transaction do database quản lý:

```java
package example.tx;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {

    private final OrderRepository orders;
    private final StringRedisTemplate txRedis;

    public OrderPaymentService(
            OrderRepository orders,
            @Qualifier("transactionalRedisTemplate")
            StringRedisTemplate txRedis) {
        this.orders = orders;
        this.txRedis = txRedis;
    }

    @Transactional(transactionManager = "transactionManager")
    public void markPaid(long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.setStatus("PAID");

        txRedis.opsForValue().set(
                "orders:status:" + orderId,
                "PAID");
    }
}
```

Trong ví dụ, `transactionManager` **phải là bean transaction manager thực tế của database**. Nếu ứng dụng có nhiều transaction manager, dùng đúng tên bean hoặc qualifier thay vì phụ thuộc vào việc Spring tự đoán một manager.

Khi có giao dịch Spring đang hoạt động, template đã bật hỗ trợ transaction có thể thực hiện các thao tác ghi Redis dưới dạng lệnh được queue trong một phiên `MULTI`/`EXEC`. Khi Spring thông báo giao dịch hoàn tất thành công, phần đồng bộ Redis thực thi `EXEC`; khi giao dịch bị rollback, phần lệnh đang queue có thể được hủy bằng `DISCARD`.

Luồng logic:

```text
Client
  |
  v
Spring @Transactional
  |
  +--> Database transaction bắt đầu
  |
  +--> UPDATE order trong database
  |        chưa commit
  |
  +--> RedisTemplate (enableTransactionSupport=true)
  |        MULTI
  |        QUEUE: SET orders:status:42 PAID
  |
  +--> Kết thúc phương thức
           |
           +--> Thành công:
           |       database transaction hoàn tất
           |       đồng bộ Redis: EXEC các lệnh đang queue
           |
           +--> Rollback:
                   database rollback
                   đồng bộ Redis: DISCARD queue (nếu chưa EXEC)
```

Sơ đồ mô tả vai trò và tín hiệu commit/rollback, **không phải một giao thức commit nguyên tử trên hai tài nguyên**. Chi tiết thứ tự callback và thời điểm chạy `EXEC` phụ thuộc đường tích hợp Spring và phiên bản triển khai; không dựa vào sơ đồ để thiết kế bảo đảm đồng thời giữa SQL và Redis.

## 4. Tại sao transaction manager bên ngoài Redis vẫn có thể ảnh hưởng tới Redis?

`JpaTransactionManager` biết cách quản lý giao dịch của `EntityManager`; `DataSourceTransactionManager` quản lý `Connection` JDBC. Hai manager này không cần phải biết cách gửi lệnh `MULTI` đến Redis để Spring Data Redis đồng bộ công việc.

Spring cung cấp **transaction synchronization**: khi một giao dịch Spring đang hoạt động trong luồng, thư viện có thể đăng ký hành động phản ứng với vòng đời commit/rollback. RedisTemplate có hỗ trợ này khi được cấu hình phù hợp.

Có thể hình dung:

```text
            Spring transaction context (cùng thread)
                            |
               +------------+------------+
               |                         |
               v                         v
        Database transaction       Redis synchronization
               |                         |
          SQL UPDATE               MULTI / queued writes
               |                         |
            Commit?                  EXEC / DISCARD
               +------------+------------+
                            |
                    Không có XA coordinator
```

Điều này tạo ra sự phối hợp hữu ích: nếu phương thức thất bại trước khi kết thúc, Redis có thể không áp dụng các lệnh đã queue. Nhưng nó **không có bước prepare/commit toàn cục** để cả database và Redis cùng xác nhận “hoặc tất cả thành công, hoặc tất cả không đổi”.

### Có RedisTransactionManager mặc định không?

Trong mô hình Spring Data Redis phổ biến, Spring Data Redis **không cung cấp một `RedisTransactionManager` chuẩn tương tự `JpaTransactionManager` để thay thế manager SQL**. Redis transactions được thực hiện qua Redis connection/`RedisTemplate` và Redis commands, còn integration với Spring transaction dựa trên synchronization.

Nếu ứng dụng chỉ sử dụng Redis và muốn nhóm các lệnh Redis một cách trực tiếp, có thể dùng `MULTI`/`EXEC` thông qua `SessionCallback`. Không nhất thiết phải tạo một `@Transactional` giả định do Redis manager quản lý.

## 5. Chú ý: đọc trong transaction có thể không thấy các lệnh Redis đang queue

Một sự khác biệt dễ gây lỗi: lệnh **ghi Redis** bên trong transaction sẽ được queue, trong khi lệnh **đọc** có thể được Spring Data Redis thực hiện bằng **một kết nối Redis khác** không thuộc transaction đang queue.

Ví dụ:

```java
@Transactional(transactionManager = "transactionManager")
public void exampleReadAfterWrite() {
    txRedis.opsForValue().set("demo:status", "READY");

    String observed = txRedis.opsForValue().get("demo:status");

    // Không giả định observed == "READY".
    // Lệnh SET vẫn có thể nằm trong hàng đợi MULTI
    // và chưa được EXEC ở thời điểm GET.
}
```

Nếu trước đó không có khóa `demo:status`, `observed` có thể bằng `null`. Nếu khóa đã tồn tại, lệnh đọc ngoài hàng đợi có thể nhìn thấy **giá trị cũ**, do `SET` mới chưa được commit. Trên một kết nối đang ở chế độ `MULTI`, một số API trả về giá trị tạm/`null` cho thao tác được queue, vì kết quả thực tế chỉ có sau `EXEC`.

Vì vậy:

- Không dùng `GET` ngay sau một `SET` đang queue làm bằng chứng ghi Redis thành công.
- Nếu logic nghiệp vụ cần giá trị mới trong cùng phương thức, giữ nó trong **biến Java** hoặc trong aggregate đang xử lý.
- Khi cần xác minh giá trị Redis đã commit, thực hiện đọc **sau khi transaction thực sự hoàn tất**, có cân nhắc tới lỗi đồng bộ và đồng thời từ writer khác.
- Tránh thiết kế quy trình nghiệp vụ dựa trên giả định các lệnh Redis queued đã ảnh hưởng tức thì đến người đọc khác.

Đây là khác biệt đáng kể so với cách nhiều người quen đọc chính dữ liệu vừa ghi bên trong SQL transaction trên cùng một database connection.

## 6. MULTI/EXEC có bảo đảm điều gì và không bảo đảm điều gì?

Khi một kết nối Redis phát:

```text
MULTI
SET inventory:42 9
INCR inventory:version
EXEC
```

Redis queue các lệnh sau `MULTI` và khi `EXEC` được nhận sẽ thực thi chúng liên tiếp, không xen lệnh của client khác vào giữa nhóm thực thi đó. Nhưng đây **không phải giao dịch kiểu SQL có rollback mọi thay đổi khi một lệnh bên trong `EXEC` thất bại lúc chạy**.

Ví dụ:

```text
MULTI
SET demo:key hello
INCR demo:key
EXEC
```

`SET` có thể thành công, còn `INCR` thất bại vì giá trị không phải số. Redis không hoàn tác `SET` chỉ vì `INCR` lỗi lúc chạy. Cần hiểu rõ kiểu dữ liệu và kiểm tra từng kết quả của `EXEC` nếu mức độ tin cậy của thao tác yêu cầu.

| Điều kiện | Redis MULTI/EXEC |
|---|---|
Lệnh được gửi sau `MULTI` | Được queue để thực thi sau |
`DISCARD` trước `EXEC` | Bỏ nhóm lệnh chưa được thực thi |
`EXEC` chạy một nhóm lệnh | Không để lệnh của client khác chen vào giữa nhóm lệnh được thực thi |
Một lệnh phát sinh lỗi khi đang `EXEC` | Không có rollback tự động những lệnh khác đã thành công |
Mất kết nối sau khi gửi `EXEC` | Có thể không biết chắc server đã áp dụng nhóm lệnh hay chưa nếu thiếu xác nhận |
Nhiều tài nguyên SQL + Redis | Không có atomic commit phân tán chỉ nhờ `MULTI`/`EXEC` |

Nếu dùng Redis Cluster, một transaction nhiều khóa còn phải tuân thủ các giới hạn **hash slot**, thường yêu cầu các khóa liên quan nằm cùng slot. Việc phối hợp nhiều tài nguyên ngoài Redis vẫn là vấn đề khác với atomicity bên trong một Redis node.

## 7. Rollback với transaction synchronization: khi nào có ích?

Giả sử controller gọi một service qua proxy Spring:

```java
@Transactional(transactionManager = "transactionManager")
public void markPaidThenFail(long orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.setStatus("PAID");

    txRedis.opsForValue().set(
            "orders:status:" + orderId,
            "PAID");

    throw new IllegalStateException("Simulated failure");
}
```

Với đúng cấu hình, transaction kết thúc bằng rollback trước khi nhóm lệnh Redis được `EXEC`, nên các lệnh đang queue có thể được `DISCARD`. Điều này **giảm** trường hợp SQL rollback nhưng Redis đã phản ánh trạng thái mới.

Tuy nhiên, cần phân biệt:

1. **Lỗi trước tín hiệu commit, Redis còn đang queue:** thường có thể hủy thay đổi Redis đang queue.
2. **Database đã commit, Redis `EXEC` thất bại:** không thể dùng rollback SQL thông thường để quay ngược commit đã hoàn tất.
3. **Redis `EXEC` đã thực thi, sau đó có lỗi ở thành phần khác:** Redis không có cách tự động đảo ngược nhóm thay đổi đã thực hiện.
4. **Một phần command trong `EXEC` lỗi:** Redis có thể áp dụng một số command, một số command khác lỗi; không có rollback tổng thể kiểu SQL.
5. **Thao tác không sử dụng template được bật transaction support:** có thể đã thực thi ngay, không chịu `DISCARD` của template kia.

Vì vậy, kết quả tốt trong một bài test rollback không chứng minh rằng hệ thống đã có **giao dịch phân tán ACID**.

## 8. Vì sao không thể gộp SQL commit và Redis EXEC thành một commit nguyên tử?

Giả sử một đơn hàng được cập nhật ở PostgreSQL và trạng thái rút gọn của nó được cập nhật trong Redis. Hai hệ thống có vòng đời commit riêng. Ngay cả khi Spring đồng bộ thứ tự, vẫn tồn tại các thời điểm lỗi:

```text
Ứng dụng
   |
   |--- SQL: COMMIT thành công
   |
   |--- (ứng dụng mất kết nối / process dừng / Redis quá tải)
   |
   +--- Redis: EXEC không thực hiện hoặc không được xác nhận

Database: trạng thái mới đã bền vững
Redis:    trạng thái cũ, thiếu hoặc kết quả chưa xác định
```

Không có một transaction coordinator thực hiện **prepare** trên cả SQL và Redis rồi ra quyết định commit duy nhất, nên không thể loại trừ hoàn toàn cửa sổ lỗi giữa hai tài nguyên bằng một annotation.

| Kết quả quan sát | SQL | Redis | Điều cần làm |
|---|---|---|---|
Thành công bình thường | Commit | Các lệnh Redis thực thi thành công | Hệ thống đạt trạng thái mong muốn |
Thất bại trước commit và Redis chưa EXEC | Rollback | Queue bị hủy | Không có cập nhật Redis từ queue đó |
Commit SQL xong nhưng Redis lỗi | Commit | Có thể chưa cập nhật | Cần retry/reconciliation hoặc cập nhật bù |
Redis đã áp dụng thay đổi nhưng phần việc khác lỗi | Có thể khác Redis | Đã thay đổi | Cần xử lý bù, không thể đòi rollback tự động từ Redis |
Ứng dụng mất kết nối lúc EXEC | Trạng thái SQL tùy thời điểm | Kết quả EXEC có thể chưa rõ | Dùng thao tác idempotent, kiểm tra trạng thái và retry có điều kiện |

**Không dựa vào thứ tự commit mặc định để cam kết nhất quán tuyệt đối.** Kể cả nếu một phiên bản thực hiện database commit trước Redis, crash hoặc lỗi mạng vẫn tạo ra trạng thái hai phía khác nhau. Đổi thứ tự chỉ thay đổi hướng của rủi ro, không xóa được rủi ro.

## 9. Các yếu tố Spring khiến @Transactional không hoạt động như dự kiến

### 9.1. Chọn nhầm transaction manager

Ứng dụng có thể có JPA, JDBC và một manager phục vụ nguồn dữ liệu khác. Khi đó, `@Transactional` không chỉ rõ manager có thể chọn một manager khác với giả định, hoặc báo lỗi vì không xác định được bean phù hợp.

```java
@Transactional(transactionManager = "transactionManager")
public void updateOrderAndRedis(...) {
    // ...
}
```

Tên `transactionManager` trong ví dụ phải đúng với **bean database transaction manager** ở ứng dụng cụ thể. Nếu tên thực tế là `ordersTransactionManager`, hãy dùng tên đó. Cũng cần xác nhận template kết nối đúng Redis deployment.

### 9.2. Gọi nội bộ không đi qua proxy

Ví dụ:

```java
@Service
public class OrderService {
    public void outer() {
        this.inner(); // Gọi cùng object; có thể bỏ qua proxy @Transactional.
    }

    @Transactional
    public void inner() {
        // ...
    }
}
```

Trong cấu hình Spring proxy transaction phổ biến, gọi `this.inner()` không kích hoạt interceptor của `@Transactional`. Nếu transaction không thật sự được mở, RedisTemplate sẽ không thể đồng bộ với transaction mà bạn tưởng đang tồn tại. Nên đặt ranh giới giao dịch tại một service method được gọi thông qua bean/proxy Spring hoặc một phương pháp quản lý transaction tường minh.

### 9.3. Ngữ cảnh transaction gắn với thread

Giao dịch Spring kiểu imperative thường dùng ngữ cảnh theo **thread**. Nếu trong phương thức transaction có `@Async`, `CompletableFuture`, một thread tự tạo hoặc callback chạy trên executor khác, đừng mặc định RedisTemplate ở thread kia vẫn dùng cùng transaction.

```java
@Transactional
public void processOrder(long id) {
    orders.findById(id).orElseThrow();

    CompletableFuture.runAsync(() -> {
        // Chạy trên thread khác.
        // Không tự động có cùng Spring transaction context.
        txRedis.opsForValue().set("orders:status:" + id, "PROCESSING");
    });
}
```

Muốn làm việc bất đồng bộ sau commit, nên thiết kế cơ chế phát công việc rõ ràng và bền vững khi cần, thay vì dựa vào việc truyền ngầm transaction giữa thread.

### 9.4. Quy tắc rollback mặc định

`@Transactional` mặc định đánh dấu rollback cho `RuntimeException` và `Error`, không phải mọi checked exception. Nếu nghiệp vụ ném checked exception nhưng vẫn mong rollback, phải khai báo phù hợp, ví dụ:

```java
@Transactional(
        transactionManager = "transactionManager",
        rollbackFor = Exception.class
)
public void update(...) throws Exception {
    // ...
}
```

Điều quan trọng là **transaction được commit hay rollback thực tế**, vì đồng bộ Redis phản ứng với kết quả đó, không tự suy luận từ mong đợi của lập trình viên.

### 9.5. Propagation và giao dịch lồng nhau

`REQUIRES_NEW`, `NESTED` và savepoint có ý nghĩa cụ thể đối với transaction manager được chọn. Không nên mặc định một rollback về SQL savepoint sẽ tương đương với việc hoàn tác một phần hàng đợi Redis trong cùng kết nối.

Nếu dùng propagation phức tạp, hãy xác định chính xác connection nào được bind, lúc nào `MULTI` bắt đầu và lúc nào `EXEC`/`DISCARD` diễn ra, cùng các test tích hợp cần thiết cho môi trường cụ thể. Không đặt logic tài chính hoặc bất biến quan trọng dựa vào suy luận “nested SQL = nested Redis”.

## 10. Spring Data Redis Repository có tự tham gia transaction không?

Redis Repository, `RedisTemplate` và Redis cache là **ba tầng API khác nhau**, dù có thể cùng sử dụng RedisConnectionFactory.

| API | Ví dụ | Điều cần xác minh |
|---|---|---|
| `RedisTemplate`/`StringRedisTemplate` | `opsForValue().set()` | Template đang dùng có bật `enableTransactionSupport` và nằm trong Spring transaction không |
| Redis Repository | `customerRepository.save(entity)` | Repository thực sự sử dụng template/adapter nào, có cơ chế duy trì keyspace/index ra sao và transaction support của đường gọi thực tế |
| Spring Cache dùng Redis | `@CachePut`, `@CacheEvict` | Cache manager có cấu hình transaction-aware không; hành động cache được hoãn tới after-commit hay thực thi ngay |
| Low-level connection/client | Lettuce/Jedis trực tiếp, Redis CLI | Có tham gia Spring transaction synchronization không; thông thường không chỉ vì cùng host Redis |

**Không suy ra `repository.save()` có cùng hành vi queue/rollback với một template tùy chỉnh** chỉ vì cả hai cùng kết nối một Redis server. Repository có thể ghi nhiều khóa vật lý để duy trì entity, tập keyspace, secondary index và TTL. Giới hạn transaction/cluster cần được xác nhận tại đúng đường API đang dùng.

Tương tự, chỉ bật transaction support trên một bean `StringRedisTemplate` không tự cấu hình lại mọi bean Redis khác của ứng dụng.

## 11. RedisCacheManager.transactionAware(): một cơ chế phối hợp khác

Đối với một cache dùng Redis, nhu cầu phổ biến là **không đưa trạng thái mới vào cache khi transaction database cuối cùng rollback**.

Spring Cache hỗ trợ cache manager có khả năng **hoãn thao tác cache liên quan đến transaction**:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class CacheConfiguration {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration cacheDefaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(cacheDefaults)
                .transactionAware()
                .build();
    }
}
```

Khi được dùng thông qua Spring Cache, chế độ `transactionAware()` có thể hoãn các thao tác như `put`/`evict`/`clear` để thực hiện **sau khi Spring transaction commit thành công**. Đây là một kiểu **defer cache mutation until after commit**.

Phải phân biệt:

- `RedisTemplate.setEnableTransactionSupport(true)`: hỗ trợ Redis transaction bằng `MULTI`/`EXEC` gắn với Spring transaction.
- `RedisCacheManager.transactionAware()`: hoãn một số thao tác của lớp Spring Cache đến thời điểm after-commit.

Hai cơ chế đều có thể giảm tình huống ghi cache khi SQL rollback, nhưng **không giống nhau**. Chế độ transaction-aware của cache manager không biến SQL và Redis thành một giao dịch XA; thao tác cache sau commit vẫn có thể thất bại. Một số thao tác có ngữ nghĩa tức thời như `putIfAbsent` cũng cần được xem xét riêng theo hợp đồng của Spring Cache.

### Ví dụ cache invalidation

```java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.transaction.annotation.Transactional;

@Transactional(transactionManager = "transactionManager")
@CacheEvict(cacheNames = "orderById", key = "#orderId")
public void changeOrderStatus(long orderId, String status) {
    Order order = orders.findById(orderId).orElseThrow();
    order.setStatus(status);
}
```

Nếu cache manager thực sự transaction-aware, thao tác evict có thể được dời tới sau commit. Điều đó tránh một số cập nhật cache khi SQL rollback; tuy nhiên, nếu ứng dụng chết ngay sau database commit và trước khi cache được evict, giá trị cache cũ vẫn có thể tồn tại đến khi TTL hết hoặc có cơ chế sửa sai.

Nếu cần bảo đảm mạnh hơn, việc xây dựng giao thức cập nhật cache/đồng bộ sự kiện phải xử lý được khoảng lỗi này.

## 12. Giải pháp đáng tin cậy hơn cho thay đổi liên tài nguyên: transactional outbox

Khi database là **nguồn dữ liệu chuẩn** còn Redis dùng làm cache, bảng tra cứu hoặc read model, lựa chọn phổ biến là **transactional outbox**.

Ý tưởng:

1. Trong **một giao dịch database**, lưu thay đổi nghiệp vụ và một dòng outbox biểu thị sự kiện cần xử lý.
2. Commit database cho cả hai dòng cùng nhau.
3. Một worker đọc outbox chưa xử lý rồi cập nhật Redis.
4. Chỉ xác nhận outbox đã xử lý sau khi thao tác Redis thành công; lỗi thì retry.
5. Thiết kế consumer **idempotent** để xử lý trường hợp cập nhật Redis thành công nhưng chưa kịp đánh dấu outbox.

```text
             HTTP / Command
                   |
                   v
         @Transactional (Database)
                   |
          +--------+--------+
          |                 |
          v                 v
      UPDATE order      INSERT outbox
          |                 |
          +--------+--------+
                   |
             DB COMMIT
                   |
                   v
          Background publisher
                   |
           Load pending outbox
                   |
                   v
            Update Redis
                   |
                   v
           Mark event delivered
```

Ví dụ ở mức khái niệm:

```java
@Transactional(transactionManager = "transactionManager")
public void markPaid(long orderId) {
    Order order = orders.findById(orderId).orElseThrow();
    order.setStatus("PAID");

    // Lưu sự kiện trong cùng DB transaction.
    outboxRepository.save(
            OutboxEvent.orderPaid(orderId, order.getVersion()));
}
```

Một consumer riêng thực hiện logic:

```text
for each pending outbox event:
    claim event theo cơ chế tránh hai worker xử lý đồng thời
    đọc event id, order id và version
    cập nhật Redis theo quy tắc idempotent / version-aware
    nếu Redis xác nhận thành công:
        đánh dấu event đã xử lý trong database
    nếu lỗi:
        ghi nhận lỗi, retry theo chính sách
```

**Vì sao tốt hơn việc hy vọng SQL + Redis commit đồng thời?** Cả thay đổi nghiệp vụ và yêu cầu đồng bộ Redis đã được ghi **bền vững trong cùng database transaction**. Nếu Redis tạm ngừng, event vẫn có thể được đọc lại.

Nhưng outbox cũng có những giới hạn phải thiết kế:

- Consumer thường có ngữ nghĩa **at-least-once**, có thể chạy lại cùng một event; Redis update phải idempotent hoặc kiểm soát version.
- Redis có thể tạm thời chậm hơn database, nên chấp nhận **eventual consistency**.
- Nếu nhiều event cho cùng entity được xử lý đảo thứ tự, trạng thái Redis có thể trở lại giá trị cũ; cần bảo toàn thứ tự theo entity hoặc dùng version/compare-and-set phù hợp.
- Outbox cần vận hành: retry, dead-letter/error state, giám sát độ trễ và dọn dữ liệu.

Transactional outbox là một cách xây dựng **đồng bộ có thể phục hồi**, không phải công cụ biến Redis và database thành cùng một giao dịch nguyên tử.

## 13. Lựa chọn kiến trúc khi SQL và Redis phải tương tác

| Mục tiêu | Cách tiếp cận | Tính chất |
|---|---|---|
Chỉ cần vài lệnh Redis có thể cùng được queue trong một Spring transaction | `RedisTemplate` với `enableTransactionSupport=true` | Phối hợp commit/rollback theo synchronization; vẫn còn rủi ro liên tài nguyên |
Muốn quản lý một nhóm lệnh **chỉ trên Redis** | `SessionCallback` với `MULTI`/`EXEC` | Transaction Redis; không bao gồm SQL |
Redis là **cache**, có thể chấp nhận tự sửa sau TTL | Cache-aside, TTL, `RedisCacheManager.transactionAware()` nếu phù hợp | Giảm cache ghi sai sau rollback; chấp nhận khoảng inconsistency |
Database là nguồn chuẩn, Redis cần được cập nhật đáng tin cậy | Transactional outbox + worker idempotent | Có retry/recovery; eventual consistency |
Muốn phát sự kiện sau commit với độ tin cậy thấp hơn outbox | `@TransactionalEventListener(phase = AFTER_COMMIT)` | Tránh gửi khi rollback, nhưng sự kiện không bền vững khi process chết |
Muốn ràng buộc mạnh cùng lúc trên SQL và Redis | Xem lại việc chia nguồn sự thật, đặt bất biến ở một tài nguyên | `@Transactional` + Redis không cung cấp XA atomicity mặc định |

### Cách dùng TransactionalEventListener đúng kỳ vọng

```java
import org.springframework.context.event.EventListener;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPaid(OrderPaid event) {
    redis.opsForValue().set(
            "orders:status:" + event.orderId(),
            "PAID");
}
```

Với một event được publish trong transaction, listener `AFTER_COMMIT` chỉ chạy sau khi commit thành công. Nhưng callback này **không lưu sự kiện bền vững**. Nếu process chết sau commit trước khi listener xử lý hoặc Redis lỗi, không có cơ chế retry chắc chắn chỉ từ annotation.

Một chi tiết khác: trong callback after-commit, một số tài nguyên Spring transaction có thể còn ở trạng thái được bind tạm thời. Không khởi tạo công việc database mới mà mặc định nó sẽ được commit trong giao dịch đã hoàn tất; cần transaction mới riêng hoặc outbox khi muốn ghi log/trạng thái xử lý chắc chắn.

## 14. Giao dịch Redis thuần qua SessionCallback

Để phân biệt với việc dùng transaction manager của database, xem một ví dụ **Redis-only** bằng `SessionCallback`:

```java
import java.util.List;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

List<Object> results =
        redisTemplate.execute(new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public List<Object> execute(RedisOperations operations)
                    throws DataAccessException {

                operations.multi();
                operations.opsForValue().set("demo:count", "1");
                operations.opsForValue().set("demo:state", "READY");
                return operations.exec();
            }
        });
```

Trong ví dụ, `SessionCallback` giúp các thao tác sử dụng **cùng một Redis connection** cho phiên lệnh `MULTI`/`EXEC`. Kết quả từng lệnh được trả về khi `exec()` hoàn tất. Đây là một nhóm thao tác Redis độc lập, không cần một `JpaTransactionManager`.

Nếu lệnh hoặc ứng dụng gặp lỗi **trước** `EXEC`, cần bảo đảm đường xử lý giải phóng/trả về kết nối đúng cách và bỏ queue nếu cần; không dùng ví dụ giản lược này làm một framework giao dịch với đầy đủ retry/cleanup.

Không tự thêm `multi()`/`exec()` thủ công vào giữa một luồng RedisTemplate đang được Spring quản lý transaction nếu chưa xác định rõ ai sở hữu kết nối và lifecycle; hai cơ chế điều khiển không nên chồng nhau tùy tiện.

### Redis Cluster và hash tag

Nếu triển khai trên Redis Cluster và thực hiện giao dịch nhiều khóa, các khóa phải thỏa giới hạn slot của Redis. Ví dụ:

```text
order:{42}:status
order:{42}:version
```

Hai khóa trên có cùng hash tag `{42}` nên được ánh xạ đến cùng slot. Trái lại, các khóa không liên quan slot có thể gây `CROSSSLOT` cho một số lệnh/transaction. **Cùng slot không giải quyết yêu cầu SQL + Redis atomic commit**; nó chỉ liên quan phạm vi và khả năng thực thi một số thao tác Redis nhiều khóa.

## 15. Bài thực hành: quan sát ba kịch bản với một database và Redis

Giả sử có một bảng `orders` và một Redis key `orders:status:42`. Thực hành nên dùng database/Redis riêng, có thể xóa dữ liệu thử nghiệm và không chứa dữ liệu thật.

### Kịch bản A — template mặc định, SQL rollback

1. Dùng `StringRedisTemplate` không bật transaction support.
2. Trong phương thức `@Transactional`, cập nhật order trong SQL và `SET` Redis.
3. Ném một `RuntimeException` để transaction SQL rollback.
4. Sau khi phương thức kết thúc bằng lỗi, đọc lại SQL và Redis.

Kết quả cần quan sát: SQL rollback, trong khi Redis có thể đã lưu trạng thái mới ngay lúc `SET` chạy. Điều đó chỉ ra hai đường ghi chưa được đồng bộ.

### Kịch bản B — template bật transaction support, rollback trước commit

1. Dùng template `setEnableTransactionSupport(true)`.
2. Cùng phương thức `@Transactional` có hoạt động SQL và Redis.
3. Ném unchecked exception **trước khi phương thức hoàn tất**.
4. Đọc Redis bên ngoài transaction.

Kết quả cần quan sát: các lệnh Redis còn queue có thể được `DISCARD`, trong khi database rollback. Đây là ích lợi của transaction synchronization ở trường hợp lỗi trước commit.

### Kịch bản C — template bật transaction support, đọc trong transaction

1. Đọc giá trị Redis ban đầu ở ngoài transaction.
2. Bắt đầu phương thức `@Transactional` và gọi `SET` giá trị mới.
3. Gọi `GET` ngay trong phương thức để xem trả về gì.
4. Cho transaction hoàn tất thành công và đọc lại sau đó.

Kết quả cần quan sát: `GET` trong transaction không nhất thiết thấy giá trị mới khi `SET` còn đang queue; sau khi commit/`EXEC` thành công, kết quả đọc ngoài transaction mới có thể phản ánh giá trị mới.

### Kịch bản D — lỗi Redis quanh commit

Giả lập Redis không khả dụng trong môi trường thử nghiệm khi giao dịch database đi tới giai đoạn hoàn tất. Quan sát trạng thái database và Redis sau lỗi. Không cần giả định một kết quả cụ thể cho mọi driver/transaction-manager; mục tiêu là thấy rằng **chỉ bật transaction support không bảo đảm cả hai tài nguyên commit nguyên tử**.

Không nên thực hiện thử nghiệm cố ý ngắt kết nối trên Redis hoặc database production.

## 16. Những câu hỏi thường gặp

### “Chỉ có @Transactional trên service là đủ để rollback Redis chưa?”

**Chưa.** Cần xác định transaction manager đang quản lý gì, template nào được dùng, có bật Redis transaction support không và thao tác có thực sự diễn ra trong ngữ cảnh transaction Spring hay không.

### “Bật enableTransactionSupport=true có khiến Redis và JPA thành một transaction duy nhất?”

**Không.** Nó hỗ trợ đồng bộ vòng đời và sử dụng `MULTI`/`EXEC`/`DISCARD` cho Redis. Không có distributed XA commit giữa JPA/JDBC và Redis chỉ từ cấu hình này.

### “Vì sao vừa SET xong mà GET trong cùng @Transactional vẫn thấy giá trị cũ?”

Vì lệnh ghi có thể đang queue trong `MULTI`, chưa tới `EXEC`. Spring Data Redis có thể thực hiện lệnh đọc ngoài connection đang queue để lấy dữ liệu đã commit trước đó.

### “Nếu SQL rollback thì Redis chắc chắn rollback không?”

Nếu Redis command đã được thực thi tức thì ngoài transaction, **không**. Nếu command được queue đúng cơ chế synchronization và rollback diễn ra trước `EXEC`, queue thường được hủy. Không thể suy rộng thành bảo đảm toàn cục cho mọi đường ghi Redis.

### “Nếu Redis EXEC có lỗi, database có tự rollback trở lại không?”

Không thể mong đợi điều đó sau khi database đã commit. Đây chính là giới hạn phối hợp hai tài nguyên độc lập; cần retry, reconciliation, thao tác bù hoặc outbox tùy yêu cầu.

### “Dùng RedisCacheManager.transactionAware() có giống RedisTemplate MULTI/EXEC không?”

Không. Cache transaction-aware thường **hoãn thao tác cache đến after-commit**; còn RedisTemplate transaction support sử dụng cơ chế Redis transaction trên kết nối tương ứng.

### “@TransactionalEventListener(AFTER_COMMIT) có thay thế outbox không?”

Không khi nghiệp vụ cần bảo đảm event vẫn xử lý được sau crash. Listener in-memory có thể không chạy nếu process chết hoặc có lỗi sau commit; outbox lưu sự kiện bền vững trong database để retry.

### “Có thể dùng @Transactional với Redis Cluster nhiều hash slot không?”

Không nên giả định mọi lệnh đều hỗ trợ. Redis Cluster có giới hạn riêng đối với transaction và thao tác nhiều khóa khác slot. Cần xem cụ thể lệnh, driver, API và cách đặt hash tag; ràng buộc slot cũng không tạo atomicity với database.

## 17. Ghi nhớ khi thiết kế

- `@Transactional` điều khiển **Spring transaction manager được chọn**, thường là JPA hoặc JDBC trong ứng dụng có database.
- RedisTemplate **không tự tham gia transaction Spring theo mặc định**. Cần bật `setEnableTransactionSupport(true)` khi muốn dùng đường đồng bộ Redis tương ứng.
- Với transaction support, **ghi Redis có thể được queue** và chỉ thực thi ở thời điểm hoàn tất giao dịch; **đọc trong transaction** có thể thấy giá trị cũ.
- Redis `MULTI`/`EXEC` giúp nhóm các lệnh Redis, nhưng **không có rollback mọi lệnh đã thực thi khi một lệnh lỗi lúc EXEC**.
- Một transaction manager của database và Redis synchronization **không tạo distributed XA transaction**; lỗi ở ranh giới commit có thể làm SQL và Redis lệch nhau.
- Phân biệt `RedisTemplate`, Redis Repository, Spring Cache và low-level client: mỗi đường ghi có cơ chế transaction khác nhau.
- Với Redis là cache, cân nhắc cache transaction-aware, TTL và khả năng làm mới; với đồng bộ đáng tin cậy từ database sang Redis, cân nhắc **transactional outbox** và consumer idempotent.
- Nếu bất biến nghiệp vụ bắt buộc đúng tuyệt đối, đặt điểm quyết định tại **một nguồn sự thật** và coi Redis là projection/cache có chiến lược khôi phục rõ ràng.

Một câu hỏi thiết kế hiệu quả hơn “có `@Transactional` chưa?” là: **Tại thời điểm SQL commit thành công nhưng Redis chưa được xác nhận, hệ thống sẽ làm gì?** Trả lời được câu hỏi đó mới biết cách phối hợp Spring transaction và Redis phù hợp với yêu cầu nghiệp vụ.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): `MULTI`/`EXEC`, `SessionCallback`, bật transaction support và cách Spring transaction synchronization xử lý Redis.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cấu hình RedisCacheManager và khả năng phối hợp cache với transaction.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxy và quy tắc rollback.
- [Spring Framework — Transaction Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html): cách các tài nguyên liên hệ với vòng đời giao dịch Spring.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và các phase của transaction.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): `MULTI`, `EXEC`, `DISCARD`, `WATCH` và giới hạn rollback của Redis transaction.
- [Redis — Redis Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slot và ràng buộc thao tác nhiều khóa trong Redis Cluster.
