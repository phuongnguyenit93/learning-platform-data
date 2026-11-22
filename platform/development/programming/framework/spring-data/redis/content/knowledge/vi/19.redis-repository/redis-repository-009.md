# Giới hạn giao dịch và các giả định không được áp dụng từ JPA trong Redis Repository

Spring Data Redis cung cấp `RedisRepository`, `@RedisHash`, `@Id`, các phương thức như `save`, `findById`, `deleteById` và khả năng ánh xạ đối tượng Java. Bề ngoài, cách viết có nhiều nét giống **Spring Data JPA**. Tuy nhiên, hai loại repository xây trên hai mô hình dữ liệu và cơ chế giao dịch rất khác nhau.

**Điều cần nhớ:** `RedisRepository` là cách tổ chức truy cập dữ liệu Redis theo mô hình repository; nó **không biến Redis thành cơ sở dữ liệu quan hệ**, không mang theo `EntityManager` và không tự cung cấp các bảo đảm giao dịch của JPA/Hibernate. Muốn có tính nguyên tử, phát hiện xung đột hoặc phối hợp nhiều nguồn dữ liệu, ứng dụng phải thiết kế rõ ở cấp lệnh Redis và ranh giới nghiệp vụ.

Bài viết phân biệt ba tầng thường bị gộp làm một:

1. **Spring Data Repository:** giao diện Java cho thao tác trên thực thể.
2. **Spring Data Redis / RedisTemplate:** ánh xạ thực thể và gửi các lệnh tới Redis.
3. **Redis server:** thực thi từng lệnh, `MULTI`/`EXEC`, `WATCH`, Lua và áp dụng cấu hình bộ nhớ, lưu trữ.

Việc một phương thức nằm trong interface repository không đồng nghĩa toàn bộ xử lý bên dưới có cùng ngữ nghĩa transaction với Spring Data JPA.

## 1. Vì sao API giống nhau dễ tạo giả định sai?

Xét một thực thể Redis:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("shopping-carts")
public class ShoppingCart {
    @Id
    private String id;
    private String ownerId;
    private int itemCount;

    public ShoppingCart() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getOwnerId() { return ownerId; }
    public void setOwnerId(String ownerId) { this.ownerId = ownerId; }

    public int getItemCount() { return itemCount; }
    public void setItemCount(int itemCount) { this.itemCount = itemCount; }
}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface ShoppingCartRepository
        extends CrudRepository<ShoppingCart, String> {
}
```

Ta có thể gọi:

```java
ShoppingCart cart = cartRepository.findById("cart-42")
        .orElseThrow();

cart.setItemCount(cart.getItemCount() + 1);
cartRepository.save(cart);
```

Điểm cần phân biệt là thao tác `findById` tạo/đọc một **đối tượng Java từ dữ liệu Redis**. Đối tượng đó không đương nhiên được quản lý bởi một *persistence context* như JPA. Thay đổi `cart.setItemCount(...)` không làm phát sinh quá trình *dirty checking* tự động; cần gọi một thao tác ghi phù hợp để cập nhật Redis.

Ở JPA, trong một transaction với entity được quản lý, thay đổi thuộc tính có thể được Hibernate phát hiện và đưa vào SQL khi flush/commit. Ở Redis Repository, không có vòng đời tương đương được bảo đảm chỉ vì class được gắn `@RedisHash`.

### 1.1. Bảng đối chiếu nhanh

| Khía cạnh | Spring Data JPA | Spring Data Redis Repository |
|---|---|---|
| Cơ sở lưu trữ | Bảng, hàng, khóa ngoại, truy vấn quan hệ | Redis key, hash, set và cấu trúc phụ trợ do mapper quản lý |
| `@Id` | Định danh entity trong mô hình JPA | Định danh được ánh xạ thành key Redis; lưu cùng ID có thể ghi đè dữ liệu |
| Persistence context | `EntityManager` quản lý thực thể trong phạm vi thích hợp | Không có JPA `EntityManager` hay identity map cùng ngữ nghĩa |
| Dirty checking | Có với managed entity | Không tự ghi thay đổi Java object nếu không gọi thao tác lưu |
| Flush | Đồng bộ thay đổi của persistence context xuống DB | Không có `EntityManager.flush()` của JPA |
| Transaction | Có thể gắn với transaction manager của RDBMS và ngữ nghĩa DB tương ứng | Phụ thuộc các lệnh Redis, cấu hình template, transaction manager và phạm vi key |
| Rollback | DB transaction có thể hoàn tác các thay đổi chưa commit | `MULTI`/`EXEC` không có rollback khi một lệnh đã được thực thi và gặp lỗi runtime |
| Khóa ngoại, unique, join | Có thể dựa vào khả năng RDBMS và mapping | Không tự có khóa ngoại, unique constraint hay SQL join |
| Cascade/orphan removal | Có quy tắc của JPA | Không tự áp dụng quy tắc cascade/orphan removal của JPA |
| Optimistic locking | Có thể dùng JPA `@Version` | Cần xác định cơ chế kiểm soát xung đột cụ thể của mô hình Redis, không mặc định kế thừa JPA |
| Lazy loading | Hibernate/JPA có cơ chế proxy và fetch plan | Không có cùng hợp đồng lazy loading/fetch join như JPA |
| Persistence | RDBMS thường cung cấp giao dịch và độ bền theo cấu hình DB | Redis phụ thuộc cấu hình RDB/AOF, replication, failover và chính sách triển khai |

Bảng này không có nghĩa Redis kém hữu ích; nó cho thấy thiết kế phải dựa trên **đúng khả năng của hệ lưu trữ được chọn**.

## 2. `save()` không đồng nghĩa một JPA unit of work

Trong JPA, lập trình viên thường nghĩ theo chu kỳ:

```text
Bắt đầu transaction
    |
EntityManager tải managed entity
    |
Sửa nhiều thuộc tính trên managed entities
    |
Dirty checking + flush
    |
Commit hoặc rollback
```

Trong Redis Repository, chu kỳ thường gần hơn với:

```text
findById -> đọc Redis -> dựng Java object
                          |
                      sửa object
                          |
                    repository.save(...)
                          |
               chuyển đổi object thành Redis writes
```

Những giới hạn trực tiếp:

- **Không có dirty checking tự động:** sửa object được lấy từ `findById` rồi thoát hàm mà không `save` không phải lời hứa ghi xuống Redis.
- **Không có flush kiểu JPA:** không dùng `flush()` hay suy luận theo thời điểm Hibernate phát SQL.
- **Không có first-level cache kiểu JPA:** hai lời gọi `findById` không mang bảo đảm trả cùng một object Java theo identity map của `EntityManager`.
- **Không có transaction-bound snapshot như JPA session:** một lần đọc tiếp theo có thể thấy thay đổi từ client khác.
- **Không có aggregate-level atomicity mặc định:** lưu một entity Redis có thể đụng nhiều Redis key, đặc biệt khi có secondary index hoặc key phụ trợ.

Ví dụ:

```java
ShoppingCart cart = cartRepository.findById("cart-42")
        .orElseThrow();

cart.setItemCount(5);

// Nếu dừng ở đây, không có thao tác Redis write tương ứng.
```

Muốn ghi thay đổi, cần gọi rõ:

```java
cartRepository.save(cart);
```

Nhưng ngay cả khi đã gọi `save`, ta vẫn cần xét tiếp: quá trình ghi có gồm một hay nhiều lệnh Redis? Có cập nhật index? Có client khác đang ghi cùng dữ liệu? Có transaction Redis bao quanh tất cả lệnh cần thiết không? **Tên phương thức `save` không trả lời các câu hỏi đó.**

## 3. Một entity có thể làm phát sinh nhiều Redis key

Redis Repository thường lưu dữ liệu thực thể trong một Redis Hash theo key có tiền tố từ `@RedisHash` và ID, chẳng hạn:

```text
shopping-carts:cart-42   -> Redis Hash chứa thuộc tính cart
```

Nếu dùng tập hợp ID theo keyspace hoặc **secondary index** như `@Indexed`, Spring Data Redis có thể quản lý thêm các key/set phụ trợ để tra cứu và dọn dữ liệu liên quan. TTL và cơ chế hỗ trợ sự kiện hết hạn cũng có thể tác động tới vòng đời của các key khác.

Ví dụ entity:

```java
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    @Indexed
    private String email;

    // constructor, getters, setters...
}
```

Các thao tác logic khi lưu/chỉnh sửa khách hàng có thể bao gồm:

```text
1. Lưu hoặc cập nhật Hash của customers:<id>
2. Cập nhật các key/set liên quan đến chỉ mục email
3. Cập nhật thông tin quản lý keyspace nếu cần
```

Các bước minh họa trên **không phải hợp đồng về thứ tự lệnh nội bộ** của mọi phiên bản Spring Data Redis. Điều quan trọng là một hành động repository có thể kéo theo nhiều thao tác và nhiều key.

Hệ quả:

- Không coi `repository.save(entity)` mặc nhiên là **một lệnh Redis nguyên tử**.
- Khi thao tác bị lỗi giữa chừng hoặc client gặp sự cố mạng, phải cân nhắc nguy cơ dữ liệu chính và chỉ mục chưa nhất quán trong một khoảng thời gian.
- Khi cập nhật trực tiếp hash bằng `HSET`, có thể bỏ qua việc cập nhật các chỉ mục do repository quản lý.
- Không dựa vào một câu lệnh Lua sửa hash rồi giả định mọi secondary index của repository tự được đồng bộ.
- Nếu logic đòi hỏi bảo đảm mạnh giữa nhiều key, cần xác định trước kiến trúc lưu trữ và cập nhật phù hợp.

**Một lệnh Redis đơn lẻ thường được thực thi nguyên tử ở phía server.** Điều đó không tự nâng một chuỗi nhiều lệnh bên trong thao tác ứng dụng thành một khối nguyên tử.

## 4. `@Transactional` không tự tạo transaction JPA cho Redis

Một lỗi phổ biến là viết:

```java
import org.springframework.transaction.annotation.Transactional;

@Service
public class CartService {
    private final ShoppingCartRepository carts;

    public CartService(ShoppingCartRepository carts) {
        this.carts = carts;
    }

    @Transactional
    public void updateTwoCarts(ShoppingCart a, ShoppingCart b) {
        carts.save(a);
        carts.save(b);

        throw new IllegalStateException("Lỗi nghiệp vụ");
    }
}
```

Rồi suy luận:

> Khi ném exception, chắc chắn cả hai lần `save` Redis sẽ bị rollback.

**Không thể rút ra kết luận này chỉ từ annotation `@Transactional`.** Annotation dùng cơ chế transaction management của Spring và cần một transaction manager thực tế. Nếu ứng dụng đang dùng `JpaTransactionManager` cho DB quan hệ, các lệnh Redis không tự nhiên trở thành phần của cùng transaction RDBMS.

Ngay cả khi bật khả năng transaction của RedisTemplate, ý nghĩa Redis transaction cũng khác rollback của SQL. Do đó phải phân biệt:

1. **Transaction Spring:** quản lý ranh giới transaction qua `PlatformTransactionManager` và các resource đã tham gia đúng cách.
2. **Transaction Redis:** nhóm lệnh được đưa vào `MULTI`/`EXEC`.
3. **Transaction CSDL quan hệ:** sử dụng cơ chế commit/rollback, isolation và durability của DB.

Ba khái niệm này không thể thay thế lẫn nhau bằng việc thêm một annotation.

### 4.1. `RedisTemplate` không tự tham gia transaction Spring theo mặc định

Spring Data Redis có cơ chế transaction support trên `RedisTemplate`. Việc bật nó được thực hiện rõ ràng khi cần, chẳng hạn:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
class RedisConfiguration {
    @Bean
    StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        StringRedisTemplate template =
                new StringRedisTemplate(connectionFactory);

        template.setEnableTransactionSupport(true);
        return template;
    }
}
```

Đây là **cấu hình khả năng tham gia transaction Spring của template**; không phải một transaction manager mới có thể rollback mọi lệnh Redis như RDBMS.

Khi sử dụng cơ chế này, các lệnh ghi trong transaction có thể được xếp hàng cho `EXEC` tại thời điểm Spring transaction commit, còn thao tác đọc có quy tắc xử lý riêng. Ứng dụng không nên dựa vào việc đọc lại ngay trong transaction sẽ luôn thấy giá trị đang được xếp hàng ghi. Hành vi cụ thể phụ thuộc API, connection và cấu hình template/repository.

Ngoài ra, không thể mặc định rằng mọi thao tác Redis repository đều có cùng phạm vi tham gia transaction như các lệnh gọi trực tiếp qua một `RedisTemplate` tùy biến. Cần thiết kế và kiểm tra ranh giới đang sử dụng.

### 4.2. Redis không có rollback kiểu SQL sau `EXEC`

Nếu dùng giao dịch Redis, khi các lệnh đã được `EXEC` thực thi và một lệnh gặp lỗi runtime, Redis **không tự hoàn tác** các lệnh khác đã thành công. Do đó giao dịch Redis không cung cấp cơ chế rollback từng bước sau execution như nhiều người quen dùng trong JPA.

Chi tiết này rất quan trọng với những luồng có yêu cầu toàn vẹn dữ liệu.

## 5. Hiểu chính xác `MULTI` và `EXEC`

Redis hỗ trợ nhóm lệnh theo giao thức:

```redis
MULTI
SET demo:order:1 "CREATED"
SET demo:order:2 "CREATED"
EXEC
```

Khi `MULTI` bắt đầu, các lệnh được **xếp hàng**. `EXEC` yêu cầu Redis chạy loạt lệnh đó. Trong quá trình Redis thực thi nhóm lệnh đã được `EXEC`, các lệnh của client khác không chen vào giữa các lệnh trong nhóm đó trên cùng server thực thi.

Các tính chất cần nhớ:

| Tính chất | Cách hiểu đúng |
|---|---|
| `MULTI` bắt đầu xếp hàng lệnh | Các lệnh thường trả `QUEUED`, chưa phải kết quả cuối |
| `EXEC` thực thi nhóm lệnh | Kết quả từng lệnh được trả trong danh sách phản hồi |
| Lệnh client khác không chen vào lúc nhóm đang thực thi | Có tính tuần tự ở server trong khoảng thực thi đó |
| `DISCARD` bỏ hàng đợi trước `EXEC` | Hủy lệnh chưa thực thi, không phải rollback các ghi đã hoàn tất |
| Lỗi phát hiện ở giai đoạn queue | Có thể khiến toàn bộ transaction bị hủy trước khi chạy |
| Lỗi khi lệnh đã bắt đầu thực thi | Không có rollback các lệnh khác đã thành công |

### 5.1. Ví dụ lỗi runtime nhưng lệnh khác vẫn được thực thi

```redis
SET demo:counter "hello"

MULTI
INCR demo:counter
SET demo:flag "done"
EXEC
```

`INCR demo:counter` gặp lỗi vì chuỗi `"hello"` không thể tăng như số nguyên. Tuy nhiên, `SET demo:flag "done"` vẫn có thể thực thi thành công trong cùng `EXEC`.

Điều này khác kỳ vọng thường gặp trong RDBMS rằng một lỗi SQL làm toàn bộ transaction bị rollback. **`EXEC` không phải cơ chế tự động khôi phục dữ liệu về trạng thái trước mọi lệnh.**

### 5.2. Trường hợp chỉ `MULTI`/`EXEC` là chưa đủ

Giả sử có kho hàng:

```text
stock:sku-7 = 1
```

Hai request muốn mua cùng một món hàng. Nếu logic gồm:

```text
GET stock:sku-7
Nếu stock > 0:
    DECR stock:sku-7
```

thì hai request có thể cùng đọc `1` trước khi request nào giảm số lượng. Kể cả từng lệnh `GET` và `DECR` là nguyên tử, **chuỗi đọc rồi quyết định rồi ghi** không tự nguyên tử.

Không giải quyết bằng cách đặt `GET`/`DECR` vào `MULTI` rồi kiểm tra kết quả `GET`: khi `MULTI` đang xếp hàng, giá trị `GET` chưa sẵn để ứng dụng dùng ra quyết định trước `EXEC`.

Các lựa chọn thường dùng là `WATCH` + `MULTI`/`EXEC`, Lua script/Redis Function hoặc định dạng dữ liệu hỗ trợ lệnh nguyên tử thích hợp.

## 6. `WATCH`: optimistic concurrency ở phía Redis

`WATCH` theo dõi một hoặc nhiều key trước khi thực hiện giao dịch. Nếu key được theo dõi bị thay đổi trước `EXEC`, Redis có thể từ chối thực thi nhóm lệnh và client phải xem xét thử lại.

Ví dụ minh họa quy trình trên cùng một kết nối:

```redis
WATCH stock:sku-7
GET stock:sku-7
```

Ứng dụng phân tích số lượng đọc được. Nếu đủ hàng, nó tiếp tục:

```redis
MULTI
DECR stock:sku-7
EXEC
```

Nếu một client khác sửa `stock:sku-7` trong khoảng giữa `WATCH` và `EXEC`, `EXEC` không thực thi danh sách lệnh đã xếp hàng. Ứng dụng cần nhận biết kết quả bị hủy, đọc lại dữ liệu và quyết định có retry hay không.

Một số lưu ý:

- `WATCH`, thao tác đọc, `MULTI` và `EXEC` cần cùng một **Redis connection**; tự gọi các lệnh trên những connection khác nhau không tạo được giao dịch dự kiến.
- `WATCH` là cơ chế optimistic concurrency. Dưới tranh chấp cao, có thể phải retry nhiều lần; cần giới hạn số lần, xử lý backoff và đưa ra phản hồi nghiệp vụ phù hợp.
- `WATCH` không tự tạo transaction cho **mọi key của entity và index** nếu ta chỉ watch một key.
- Trên Redis Cluster, các lệnh đa key chịu giới hạn hash slot; không thể giả định một giao dịch đi qua mọi shard.
- Khi điều kiện không cho phép cập nhật, ứng dụng nên `UNWATCH` hoặc kết thúc đúng cách để giải phóng trạng thái theo dõi của connection.

Với Spring Data Redis, thao tác `watch`/`multi`/`exec` cần giữ cùng connection. `SessionCallback` là API để gom các thao tác trong một session của `RedisTemplate`:

```java
redisTemplate.execute(new SessionCallback<Object>() {
    @Override
    public <K, V> Object execute(RedisOperations<K, V> operations)
            throws DataAccessException {
        // WATCH -> READ -> MULTI -> WRITE -> EXEC
        // Triển khai kiểm tra giá trị và kết quả EXEC tại đây.
        return null;
    }
});
```

Đoạn này chỉ minh họa ranh giới API. Logic thực tế cần xác định rõ serializer, kiểu key/value, xử lý `EXEC` bị hủy và chiến lược retry. Không gọi `watch`, `get`, `multi`, `exec` qua các request/template/connection không liên quan rồi kỳ vọng chúng tạo thành một giao dịch.

## 7. Lua script: thao tác kiểm tra và cập nhật nguyên tử

Với yêu cầu **đọc số lượng, kiểm tra điều kiện và trừ tồn kho** trên một key Redis native, một Lua script thường trực tiếp hơn so với tự retry qua `WATCH`.

Ví dụ lưu tồn kho trong key String riêng:

```redis
SET stock:sku-7 5
```

Lua script:

```lua
local current = redis.call('GET', KEYS[1])
if not current then
    return -1  -- chưa có tồn kho
end

local requested = tonumber(ARGV[1])
local available = tonumber(current)

if requested == nil or requested < 1 or available == nil then
    return -2  -- đầu vào / dữ liệu không hợp lệ
end

if available < requested then
    return 0   -- không đủ hàng
end

redis.call('DECRBY', KEYS[1], requested)
return 1       -- đã trừ thành công
```

Spring Data Redis có thể gọi script bằng `StringRedisTemplate`:

```java
import java.util.Collections;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class StockService {

    private static final String DECREASE_LUA = """
        local current = redis.call('GET', KEYS[1])
        if not current then
            return -1
        end

        local requested = tonumber(ARGV[1])
        local available = tonumber(current)

        if requested == nil or requested < 1 or available == nil then
            return -2
        end

        if available < requested then
            return 0
        end

        redis.call('DECRBY', KEYS[1], requested)
        return 1
        """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> decreaseScript;

    public StockService(StringRedisTemplate redis) {
        this.redis = redis;
        this.decreaseScript =
                new DefaultRedisScript<>(DECREASE_LUA, Long.class);
    }

    public long decrease(String sku, long quantity) {
        Long result = redis.execute(
                decreaseScript,
                Collections.singletonList("stock:" + sku),
                Long.toString(quantity)
        );
        if (result == null) {
            throw new IllegalStateException("Redis không trả kết quả");
        }
        return result;
    }
}
```

Ý nghĩa trả về:

| Kết quả | Ý nghĩa |
|---|---|
| `1` | Trừ tồn kho thành công |
| `0` | Không đủ số lượng |
| `-1` | Key tồn kho chưa tồn tại |
| `-2` | Dữ liệu hoặc số lượng yêu cầu không hợp lệ |

Script được Redis thực thi nguyên tử đối với thao tác trên key tham gia trong phạm vi Redis server tương ứng. Trong Redis Cluster, các key mà script truy cập phải tuân thủ ràng buộc hash slot của cluster.

**Lưu ý:** tính nguyên tử khi thực thi script không đồng nghĩa Lua tự có cơ chế SQL rollback nếu script gây lỗi sau khi đã thực hiện một số lệnh ghi. Nên kiểm tra đầu vào và điều kiện **trước** khi bắt đầu ghi khi thiết kế script.

Trong ví dụ này, `stock:<sku>` là **key Redis native do `StockService` quản lý**, không phải field của một `@RedisHash` entity đang được repository đồng thời quản lý. Việc tách ownership giúp tránh cập nhật trực tiếp field rồi làm sai trạng thái repository hoặc secondary index.

## 8. `@Transactional` giữa JPA và Redis: không có distributed commit tự động

Giả sử một service vừa ghi đơn hàng vào database quan hệ, vừa giảm số lượng trong Redis:

```java
@Service
public class CheckoutService {
    private final OrderJpaRepository orders;
    private final StringRedisTemplate redis;

    public CheckoutService(
            OrderJpaRepository orders,
            StringRedisTemplate redis) {
        this.orders = orders;
        this.redis = redis;
    }

    @Transactional
    public void checkout(Order order) {
        orders.save(order);             // RDBMS
        redis.opsForValue().increment(
                "metrics:orders:created"
        );                              // Redis

        throw new IllegalStateException("Giả lập sự cố");
    }
}
```

Nếu `@Transactional` dùng transaction manager cho JPA, lệnh Redis ở ví dụ không tự tham gia cùng transaction DB. Khi phương thức ném exception, DB có thể rollback còn thao tác Redis đã xảy ra.

Kể cả khi cấu hình để RedisTemplate xếp hàng ghi trong transaction Spring, **không được suy luận** rằng commit của Redis và commit của RDBMS trở thành một **atomic distributed transaction**. Hai resource có thể gặp lỗi ở hai thời điểm khác nhau, kết nối có thể ngắt và hệ thống có thể cần cơ chế bù trừ.

Có thể hình dung một phần các tình huống:

```text
JPA DB                 Redis
------                 -----
Order đã commit        Cache chưa bị xóa
Order rollback         Redis counter đã tăng
Order commit           Redis update thất bại
Redis update thành công  Phản hồi client bị mất trên mạng
```

Đây là vấn đề **dual write**. Thêm `@Transactional` vào phương thức không tự giải quyết.

### 8.1. Khi Redis là cache, ưu tiên luồng có thể tự phục hồi

Nếu dữ liệu nguồn nằm ở RDBMS, một hướng đơn giản là chỉ vô hiệu cache **sau khi DB commit thành công**:

```java
public record ProductChanged(String productId) {}
```

```java
@Service
public class ProductService {

    private final ProductJpaRepository products;
    private final ApplicationEventPublisher events;

    public ProductService(
            ProductJpaRepository products,
            ApplicationEventPublisher events) {
        this.products = products;
        this.events = events;
    }

    @Transactional
    public void rename(String productId, String newName) {
        Product product = products.findById(productId).orElseThrow();
        product.setName(newName);
        events.publishEvent(new ProductChanged(productId));
    }
}
```

Listener sau commit:

```java
@Component
public class ProductCacheInvalidator {

    private final StringRedisTemplate redis;

    public ProductCacheInvalidator(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void invalidate(ProductChanged event) {
        redis.delete("cache:product:" + event.productId());
    }
}
```

Cần import các type Spring tương ứng như `ApplicationEventPublisher`, `@Component`, `@TransactionalEventListener` và `TransactionPhase`.

Cách này tránh xóa cache khi transaction DB cuối cùng rollback, nhưng listener chạy sau commit **không phải thông báo bền vững**: tiến trình có thể dừng trước hoặc trong lúc xóa cache. Một request đồng thời cũng có thể nạp lại cache với dữ liệu cũ nếu không quản lý thứ tự đọc/ghi phù hợp.

Với yêu cầu bảo đảm truyền sự kiện, có thể dùng **transactional outbox**: lưu sự kiện cùng transaction DB, rồi có worker phát lại và xử lý idempotently. Khi Redis chỉ là cache, TTL và cơ chế nạp lại từ dữ liệu nguồn là thêm một lớp phục hồi hữu ích.

### 8.2. Khi Redis là nguồn dữ liệu nghiệp vụ

Nếu Redis chứa trạng thái có giá trị kinh doanh không thể tái tạo, cần cân nhắc:

- Các thao tác cần cập nhật đồng thời có cùng key hoặc cùng hash slot không?
- Có thể gói thành một lệnh Redis, script hoặc một mô hình trạng thái đơn nhất không?
- Cấu hình AOF/RDB, replication và failover có đáp ứng mức độ mất dữ liệu cho phép không?
- Cần cơ chế replay, log sự kiện hoặc nguồn dữ liệu bền vững khác không?
- Khi client không nhận được phản hồi, có phân biệt được **chưa thực thi** với **đã thực thi nhưng mất kết quả** không?

Các câu hỏi này tồn tại độc lập với interface `CrudRepository` đang sử dụng.

## 9. Không có dirty checking, lazy loading và cascade kiểu JPA

### 9.1. Dirty checking

Ví dụ JPA quen thuộc:

```java
@Transactional
public void changeEmail(String id, String email) {
    Customer customer = jpaRepository.findById(id).orElseThrow();
    customer.setEmail(email);
    // Managed entity có thể được flush khi transaction commit.
}
```

Không được chuyển nguyên mẫu kỳ vọng này sang Redis Repository:

```java
public void changeEmail(String id, String email) {
    Customer customer = redisRepository.findById(id).orElseThrow();
    customer.setEmail(email);
    // Chưa có save: thay đổi Java object không tự được ghi xuống Redis.
}
```

Với Redis, thao tác lưu phải xuất hiện rõ ràng tại nơi ứng dụng quyết định thay đổi:

```java
redisRepository.save(customer);
```

### 9.2. Lazy loading và quan hệ đối tượng

JPA có thể ánh xạ `@OneToMany`, `@ManyToOne` hoặc `@ManyToMany` tới các quan hệ dữ liệu và dùng `FetchType.LAZY`, join fetch, cascade. Redis Repository không cung cấp cùng một hệ thống persistence context để tự làm các tính năng này hoạt động.

Spring Data Redis có thể lưu object lồng nhau hoặc tham chiếu (`@Reference`) theo cơ chế riêng. Tuy nhiên:

- `@Reference` không phải khóa ngoại RDBMS.
- Không có ràng buộc DB bắt buộc target còn tồn tại mỗi khi tham chiếu được đọc.
- Không được giả định xóa object cha sẽ tự xóa tất cả object con giống `CascadeType.REMOVE`.
- Không có orphan removal của JPA được áp dụng ngầm.
- Không có JPQL `JOIN FETCH` tương đương trên các key Redis.
- Không có cơ chế session JPA bảo đảm cùng object identity cho các tham chiếu trong một transaction.

Nếu một nghiệp vụ cần quan hệ phức tạp, cần định nghĩa rõ đối tượng nào sở hữu dữ liệu, cách cập nhật tham chiếu và cách dọn các key mồ côi.

### 9.3. Kiểm tra tính hợp lệ trước khi lưu

Trong RDBMS, unique constraint, foreign key và check constraint có thể chặn dữ liệu vi phạm ngay tại database. Redis không cung cấp tự động bộ ràng buộc quan hệ tương ứng cho entity repository.

Ví dụ:

```java
@Indexed
private String email;
```

`@Indexed` phục vụ tra cứu thứ cấp theo khả năng Spring Data Redis hỗ trợ. **Nó không tương đương `@Column(unique = true)` hoặc unique index có ràng buộc từ RDBMS.**

Nếu hai request đồng thời đăng ký cùng email:

```text
Request A: kiểm tra chưa có email
Request B: kiểm tra chưa có email
Request A: lưu user A
Request B: lưu user B
```

cả hai có thể vượt qua một bước kiểm tra thực hiện tách rời. Để thực hiện “chỉ một tài khoản được sở hữu email”, cần cơ chế đặt quyền sở hữu **nguyên tử**, ví dụ key dành riêng cho tên email đã chuẩn hóa dùng `SET key owner NX`, kèm thiết kế xử lý lỗi giữa các bước và phục hồi khi cập nhật nhiều key. Nếu yêu cầu ràng buộc mạnh và các quan hệ phức tạp, RDBMS có thể là nguồn dữ liệu có bảo đảm phù hợp hơn.

## 10. Optimistic locking không tự suy ra từ `@Version` JPA

Trong JPA, ví dụ quen thuộc:

```java
@Version
private Long version;
```

gắn với cơ chế Hibernate/JPA để so sánh phiên bản khi update và phát hiện lost update.

Khi chuyển sang Redis, không nên mặc định rằng thêm cùng annotation sẽ đem lại **chính xác** hành vi đó cho toàn bộ Redis aggregate, index hoặc các lệnh tự gọi từ `RedisTemplate`.

Tùy phiên bản và khả năng của mô-đun lưu trữ, hỗ trợ versioning có thể khác; thiết kế cần dựa trên các bảo đảm thực tế đang sử dụng. Một số cách kiểm soát cạnh tranh cấp Redis:

1. **Lệnh nguyên tử:** `INCR`, `INCRBY`, `HINCRBY`, `SET ... NX` phù hợp khi phép cập nhật có thể diễn tả bằng một lệnh.
2. **`WATCH` + `MULTI`/`EXEC`:** kiểm tra dữ liệu rồi cập nhật với optimistic concurrency ở phạm vi các key được theo dõi.
3. **Lua/Redis Function:** gom kiểm tra và cập nhật trong một đoạn logic chạy tại server.
4. **Version key hoặc token nghiệp vụ:** so sánh phiên bản do ứng dụng quản lý trong một thao tác nguyên tử, kèm quy tắc retry/xung đột rõ ràng.
5. **Một nguồn dữ liệu giao dịch có ràng buộc mạnh:** khi thao tác trải trên nhiều aggregate, nhiều hệ thống hoặc cần unique/foreign key nghiêm ngặt.

### 10.1. Ví dụ lost update khi chỉ đọc rồi save

Giả sử `ShoppingCart.itemCount = 3`.

```text
Thời điểm    Request A                  Request B
---------    ---------                  ---------
t1           findById -> 3
t2                                      findById -> 3
t3           itemCount = 4
t4                                      itemCount = 4
t5           save(cart: 4)
t6                                      save(cart: 4)
```

Kết quả là `4`, dù hai request đều muốn thêm một món. Mẫu `GET -> cộng trong Java -> SAVE` không bảo đảm cộng dồn.

Nếu bài toán chỉ là tăng một counter, có thể tách ra key riêng để dùng:

```java
Long count = stringRedisTemplate.opsForValue()
        .increment("cart:item-count:cart-42", 1L);
```

Lệnh tăng trên một key Redis được server thực thi nguyên tử. Nhưng nếu counter là thành phần của entity Redis Repository, phải xác định cách đọc/ghi nhất quán: không vừa tăng counter riêng vừa lưu nguyên bản entity cũ rồi kỳ vọng hai nơi tự đồng bộ.

## 11. Transaction Redis không đồng nghĩa isolation level JPA

RDBMS thường hỗ trợ các mức isolation được biết đến như `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE` và cơ chế khóa hàng. Với Redis, cần diễn giải hành vi dựa trên từng command và `MULTI`/`EXEC`, thay vì bê nguyên các thuộc tính isolation của JPA sang.

Ví dụ:

```text
Client A: GET account:1 -> 100
Client B: SET account:1 80
Client A: SET account:1 90
```

Các lệnh riêng lẻ đã thực thi tuần tự, nhưng chuỗi đọc–tính–ghi ở Client A vẫn ghi đè cập nhật của B. `MULTI` chỉ xếp hàng lệnh và thực thi sau `EXEC`, không cung cấp snapshot Java object giữa nhiều lời gọi trước đó.

Tương tự, các ý niệm quen thuộc như:

- `SELECT ... FOR UPDATE`,
- row-level lock,
- savepoint của database,
- `EntityManager.lock(...)`,
- query kết hợp `JOIN` dưới một snapshot giao dịch,

không có cơ chế tương đương tự động chỉ vì thao tác xuất phát từ Redis Repository.

Nếu cần khóa phân tán, có thể nghiên cứu cơ chế Redis `SET NX PX`, token sở hữu, thời hạn khóa và fencing token, nhưng đây là một thiết kế đồng bộ riêng với các điều kiện an toàn; không phải chức năng sẵn có của JPA pessimistic lock.

## 12. Redis Cluster, pipeline và `MULTI` không phải một khái niệm

Ba cơ chế cần phân biệt:

| Cơ chế | Mục đích chính | Cam kết cần hiểu |
|---|---|---|
| Pipelining | Giảm round trip bằng cách gửi nhiều lệnh liên tiếp | Không tự tạo transaction hoặc rollback |
| `MULTI`/`EXEC` | Xếp hàng và thực thi nhóm lệnh Redis | Không có rollback runtime; bị giới hạn bởi Redis node/cluster |
| Lua/Redis Function | Chạy logic tại server, thường để kiểm tra rồi cập nhật nguyên tử | Cần kiểm soát lỗi, thời gian chạy và phạm vi key |

Trong **Redis Cluster**, những thao tác đa key như transaction/script có ràng buộc về hash slot. Việc dùng key có cùng hash tag có thể giúp các key liên quan nằm chung slot:

```text
cart:{42}:items
cart:{42}:total
cart:{42}:version
```

Tuy nhiên, thêm `{42}` vào tên key không tự bảo đảm tính đúng đắn của nghiệp vụ. Nó chỉ hỗ trợ phân bố key phù hợp để các thao tác đa key được phép chạy trong giới hạn cluster. Vẫn phải kiểm soát concurrency, lỗi và vòng đời dữ liệu.

Với Redis Repository, key dữ liệu chính, index và key phụ trợ có thể không mặc nhiên ở cùng hash slot. Vì vậy không nên giả định transaction nhiều key vận hành xuyên cụm chỉ vì repository có một method `save`.

## 13. Giao dịch và độ bền dữ liệu là hai vấn đề độc lập

Redis có cơ chế lưu dữ liệu và replication, nhưng việc `EXEC` hoặc `SET` trả thành công không có nghĩa thay đổi đó đã được ghi bền vững đồng thời ở mọi bản sao trong mọi cấu hình.

Cần phân biệt:

- **Atomicity of a command:** một lệnh được Redis xử lý như thao tác đơn lẻ.
- **Isolation khi thực thi `EXEC`:** không cho các lệnh khác chen giữa lệnh trong nhóm tại server thực thi.
- **Durability:** dữ liệu tồn tại thế nào sau crash/restart, phụ thuộc RDB, AOF và cấu hình.
- **Replication/failover:** dữ liệu đến replica nào, thời điểm nào; replica chưa nhận được dữ liệu có thể được nâng lên sau sự cố.
- **Application consistency:** dữ liệu Redis có đồng bộ với RDBMS, sự kiện và những dịch vụ khác hay không.

Không thể suy luận từ “lệnh Redis nguyên tử” thành “hệ thống có giao dịch ACID giống RDBMS trên mọi resource”. `WAIT` và các cơ chế chờ replica có thể hỗ trợ xác nhận replication trong những kịch bản nhất định, nhưng cũng không phải phép thay thế một distributed transaction hoặc bảo đảm tuyệt đối không mất dữ liệu trong mọi sự cố.

## 14. TTL, expiration và eviction phá vỡ giả định entity luôn tồn tại

Một đối tượng có thể được lưu với TTL:

```java
@RedisHash(value = "checkout-sessions", timeToLive = 900)
public class CheckoutSession {
    @Id
    private String id;

    private String userId;

    // ...
}
```

Sau 900 giây, Redis coi key là hết hạn. Nếu Redis được cấu hình eviction theo áp lực bộ nhớ, key có thể biến mất **trước khi hết TTL**. Khóa cũng có thể bị xóa chủ động bằng `deleteById`.

Điều này dẫn tới các giới hạn quan trọng:

- `findById` có thể trả `Optional.empty()` bất kỳ lúc nào nếu key đã biến mất.
- TTL của entity thường áp dụng cho key chứa entity, không phải transaction lifetime.
- Không có khóa ngoại tự động ngăn xóa entity đang được object khác tham chiếu.
- Secondary index và key phụ trợ có vòng đời riêng; dọn index nhờ expiration events không phải một cơ chế giao dịch xuyên key.
- Redis keyevent notifications dựa trên Pub/Sub, không phải log sự kiện bền vững bảo đảm nhận đủ mọi lần hết hạn.

Không nên xây quy tắc nghiệp vụ kiểu “thực thể đã đọc thì sẽ còn đó đến lúc commit” theo thói quen JPA. Với session/cache, hãy định nghĩa rõ cách xử lý khi key mất: trả về trạng thái phiên hết hạn, nạp lại cache hoặc yêu cầu người dùng thực hiện lại thao tác.

## 15. Lưu nhiều entity không đồng nghĩa transaction trên một aggregate quan hệ

Giả sử đơn hàng có hai bản ghi Redis độc lập:

```text
orders:order-101
payments:payment-101
```

Một service lưu lần lượt:

```java
orders.save(order);
payments.save(payment);
```

Nếu lần lưu thứ hai lỗi, đừng mặc định Spring Data Redis sẽ rollback lần lưu đầu. Cũng không nên mặc định quan hệ:

```text
order.paymentId = "payment-101"
```

được Redis bảo đảm bằng foreign key.

Các hướng thiết kế có thể là:

- Nếu hai giá trị **luôn phải cập nhật cùng nhau**, cân nhắc đưa về một trạng thái/đơn vị lưu thích hợp để thao tác có thể nguyên tử trên cùng key.
- Nếu bắt buộc tách hai key, cân nhắc script hoặc transaction Redis với phạm vi key cho phép, đồng thời thiết kế xử lý lỗi runtime.
- Nếu dữ liệu được quản lý bởi nhiều service hoặc nhiều storage engine, chọn cơ chế điều phối như saga/outbox hoặc một nguồn sự thật có giao dịch phù hợp.
- Nếu đây chỉ là các cache có thể tái tạo, chấp nhận lệch tạm thời rồi cung cấp cơ chế invalidation và rebuild an toàn.
- Nếu yêu cầu bất biến tài chính/tồn kho không được vi phạm, định nghĩa chặt các invariant và đặt thao tác kiểm tra + ghi tại nơi có khả năng bảo đảm chúng.

## 16. Những giả định JPA phải bỏ khi chuyển sang Redis Repository

### “Có `@Transactional` là mọi thay đổi sẽ rollback khi ném exception”

Sai. Cần xem resource nào tham gia transaction nào; Redis `MULTI`/`EXEC` có ngữ nghĩa rollback khác database. Đồng bộ Redis và RDBMS là bài toán riêng.

### “Đọc entity rồi sửa field là đủ; Hibernate sẽ tự flush”

Sai. Redis Repository không sử dụng persistence context/dirty checking của JPA. Cần chủ động lưu bằng API thích hợp.

### “`save` nhiều entity tương đương một transaction DB”

Sai. Mỗi lời gọi có thể tạo nhiều lệnh và key; không mặc định atomic qua toàn bộ chuỗi gọi.

### “Annotation `@Indexed` tự bảo đảm uniqueness”

Sai. Chỉ mục phục vụ tìm kiếm không có nghĩa là ràng buộc unique như RDBMS.

### “`@Reference` là foreign key; xóa cha sẽ cascade sang con”

Sai. Cơ chế tham chiếu Redis không mang toàn bộ ngữ nghĩa quan hệ và lifecycle của JPA.

### “Có `@Version` là chắc chắn tránh được mọi lost update”

Không thể mặc định. Phải dựa vào cách repository/Redis thực sự kiểm soát phiên bản và thiết kế CAS hoặc lệnh nguyên tử khi cần.

### “Đã đọc entity trong transaction thì đến commit key vẫn còn”

Sai. Redis key có thể hết hạn, bị xóa hoặc bị eviction, và Redis không tự giữ entity theo session JPA.

### “`MULTI`/`EXEC` có rollback giống SQL”

Sai. Một lỗi khi thực thi có thể để lại những lệnh khác đã thành công; `DISCARD` chỉ hủy nhóm đang xếp hàng, không hoàn tác điều đã thực hiện.

### “Redis trả OK thì dữ liệu chắc chắn bền vững trên mọi node”

Sai. Độ bền và replication phụ thuộc cấu hình, topology và tình huống lỗi.

### “Dùng pipeline sẽ tạo transaction”

Sai. Pipeline tối ưu việc gửi lệnh; nó không biến nhiều lệnh thành một đơn vị rollback/isolation.

## 17. Chọn giải pháp theo loại nghiệp vụ

| Bài toán | Nguy cơ nếu bê giả định JPA sang | Hướng thiết kế phù hợp |
|---|---|---|
| Cache sản phẩm | Nghĩ cache luôn tồn tại; cập nhật DB nhưng quên invalidation | Cache miss có thể nạp lại, TTL và invalidation sau commit |
| Bộ đếm lượt xem | `findById` + cộng + `save` gây lost update | `INCR`/`INCRBY` trên key phù hợp |
| Chỉ còn 1 sản phẩm | Hai request cùng đọc tồn kho rồi cùng trừ | Script nguyên tử hoặc optimistic CAS |
| Đăng ký email duy nhất | `@Indexed` bị nhầm với unique constraint | Đặt ownership nguyên tử hoặc dùng RDBMS unique constraint |
| Chuyển trạng thái nhiều key | Cho rằng `save` nhiều repository rollback đồng bộ | Thiết kế key/transaction/script đúng phạm vi, hoặc saga/outbox |
| Ghi DB và xóa cache | `@Transactional` tưởng bao gồm cả Redis | Invalidate sau commit, retry/outbox nếu cần bảo đảm |
| Thực thể có tham chiếu | Mong cascade/foreign key tự duy trì | Quản lý vòng đời và kiểm tra tham chiếu rõ ràng |
| Session có TTL | Nghĩ thời hạn còn dương thì không thể mất | Chấp nhận key mất sớm; xử lý hết phiên và chính sách eviction |
| Nhiều thao tác trong cluster | Giả định transaction đa key xuyên shard | Xác định hash slot, giới hạn thao tác hoặc thay đổi mô hình |

## 18. Hướng dẫn thiết kế ranh giới giao dịch thực tế

Khi viết một chức năng mới bằng Spring Data Redis, có thể đi theo trình tự:

**Bước 1 — Xác định invariant nghiệp vụ.**

Ví dụ: “Không được bán vượt tồn kho” hoặc “Mỗi email chỉ thuộc một người dùng” là các invariant phải được giữ, khác với yêu cầu “cache sản phẩm có thể mất và được tải lại”.

**Bước 2 — Xác định đơn vị dữ liệu cần cập nhật cùng nhau.**

Nếu invariant chỉ nằm trên một Redis String/Hash, cân nhắc thao tác nguyên tử tại server. Nếu kéo dài qua nhiều key hay Redis Cluster, phải kiểm tra ràng buộc transaction và hash slot.

**Bước 3 — Chọn cơ chế thích hợp.**

- Dùng một lệnh Redis nguyên tử khi có thể (`SET NX`, `INCRBY`, `HINCRBY`...).
- Dùng `WATCH` + `MULTI`/`EXEC` khi cần optimistic check với kết quả retry.
- Dùng Lua/Redis Function khi cần kiểm tra và cập nhật như một phép toán nguyên tử trên các key hỗ trợ.
- Dùng database quan hệ và transaction DB khi cần unique/foreign key, joins hoặc update nhiều bản ghi với các ràng buộc mạnh.
- Dùng outbox/saga và thao tác idempotent khi cần đồng bộ những nguồn dữ liệu độc lập.

**Bước 4 — Xác định điều gì xảy ra khi thất bại.**

Không chỉ xét “exception xảy ra”, mà còn phân biệt:

```text
Chưa gửi lệnh -> không có thay đổi
Gửi lệnh nhưng mất kết nối -> chưa biết server đã thực thi hay chưa
EXEC hoàn tất nhưng một lệnh lỗi runtime -> có thể đã có thay đổi khác
DB commit nhưng Redis chưa cập nhật -> cần retry / rebuild
Key hết TTL / eviction -> phải xử lý trạng thái không tồn tại
```

Các luồng nhận lại request, retry hoặc replay phải có **idempotency** nếu một hành động không được thực hiện hai lần.

**Bước 5 — Định nghĩa ownership của dữ liệu.**

Nếu `RedisRepository` sở hữu một entity cùng secondary index, nên cập nhật nó qua cùng abstraction. Nếu cần thao tác thấp tầng đặc thù (counter, script, set membership), có thể tách thành những key riêng do một component chuyên trách quản lý. Không cho hai cơ chế ghi cùng field mà không có giao thức đồng bộ rõ ràng.

**Bước 6 — Đặt yêu cầu về độ bền và khả năng khôi phục.**

Cache, phiên ngắn hạn, tồn kho và sổ cái thanh toán có mức độ chịu mất dữ liệu khác nhau. Hãy chọn persistence, replication, monitoring và nguồn dữ liệu phù hợp với mức độ quan trọng thực tế.

## 19. Một ví dụ thiết kế tổng hợp

Giả sử hệ thống thương mại điện tử có ba dữ liệu:

```text
PostgreSQL:
  orders, order_items, payments   (nguồn dữ liệu chính)

Redis:
  cache:product:<id>             (cache có thể tái tạo)
  stock:<sku>                    (bộ đếm nhanh, nếu thiết kế cho phép)
  checkout-session:<id>          (phiên tạm có TTL)
```

Ba hành vi khác nhau nên có ba chiến lược:

1. **Sửa mô tả sản phẩm:** commit thay đổi trong PostgreSQL, rồi invalidation cache Redis; nếu invalidation thất bại, có retry/TTL.
2. **Đặt hàng với giới hạn tồn kho:** đảm bảo invariant ở nơi được chọn làm nguồn sự thật. Nếu dùng Redis để giữ chỗ nhanh, có thể dùng Lua nguyên tử và cơ chế đối soát với DB; không coi một lời gọi `@Transactional` là distributed commit.
3. **Lưu checkout session:** dùng TTL và xử lý `findById` không thấy entity. Không đòi hỏi Redis giữ session đúng đến giây cuối nếu chính sách eviction có thể loại sớm.

Đây là cách dùng ưu thế của Redis — tốc độ, thao tác nguyên tử trên cấu trúc dữ liệu phù hợp, TTL và cache — mà không dựa vào những bảo đảm thực chất thuộc JPA/RDBMS.

## 20. Kết luận

`RedisRepository` và `JpaRepository` cùng sử dụng mô hình repository của Spring Data, nhưng **cùng API không có nghĩa cùng transaction semantics**.

Khi thiết kế với Spring Data Redis, cần nhớ rõ:

- Java entity lấy từ Redis **không phải JPA managed entity**; thay đổi thuộc tính không được dirty-check và flush tự động.
- Một lần `save` **có thể cập nhật nhiều key**; không tự suy ra atomicity của cả aggregate.
- `@Transactional` **không tự bảo đảm** rollback toàn bộ Redis và DB quan hệ; transaction support phải được cấu hình, hiểu đúng phạm vi.
- `MULTI`/`EXEC` có cơ chế xếp hàng và thực thi nhóm lệnh, **không có rollback runtime như SQL**.
- Redis có thể dùng `WATCH`, Lua và lệnh nguyên tử để giải quyết tranh chấp khi đúng với mô hình dữ liệu.
- Redis không tự áp dụng foreign key, unique constraint, JPA cascade, optimistic lock và lazy loading kiểu Hibernate.
- TTL, eviction, replication và persistence ảnh hưởng trực tiếp tới khả năng tồn tại và khôi phục dữ liệu.

Quyết định quan trọng nhất là xác định **invariant nghiệp vụ cần bảo đảm ở đâu** và chọn thao tác Redis/transaction/database thực sự có thể bảo đảm invariant đó. Khi trả lời được câu hỏi này, repository trở thành một lớp truy cập dữ liệu rõ ràng và hữu ích thay vì nguồn phát sinh những kỳ vọng giao dịch sai lệch.
