# Kiểm tra giới hạn các lệnh, pipeline và script trước khi chuyển sang Redis Cluster

Chuyển từ Redis standalone hoặc Redis Sentinel sang **Redis Cluster** không chỉ là đổi danh sách `host:port` trong `application.yml`. Redis Cluster phân vùng key thành **16.384 hash slot** và phân phối các slot này lên nhiều primary. Vì thế, nhiều thao tác đã chạy bình thường trên một Redis server — đặc biệt là lệnh **nhiều key**, `MULTI/EXEC`, **pipeline** và **Lua script** — có thể gặp hạn chế khi các key thuộc những slot khác nhau.

Trong Spring Data Redis, những hạn chế ấy không biến mất chỉ vì ứng dụng sử dụng `RedisTemplate`, `StringRedisTemplate`, `ReactiveRedisTemplate` hoặc `RedisRepository`. Framework giúp quản lý serialization, kết nối và một phần định tuyến lệnh; còn **ngữ nghĩa của Redis Cluster và khả năng hỗ trợ của driver** vẫn quyết định thao tác nào hợp lệ.

Trước migration, cần trả lời được:

1. Những thao tác Redis nào chỉ dùng **một key**, những thao tác nào dùng **nhiều key**?
2. Những key cần được xử lý cùng một lệnh, transaction hoặc script có **cùng hash slot** không?
3. Pipeline hiện tại có giả định mọi lệnh đi qua **một connection/Redis node** hay không?
4. Lua script có truy cập key tự tạo trong code, key không khai báo trong `KEYS`, hoặc key ở slot khác không?
5. Spring Cache, Redis Repository, Redis Streams và các module thư viện có phát sinh thêm lệnh hoặc key mà ta chưa kiểm kê không?
6. Client đang dùng — ví dụ Lettuce hoặc Jedis — hỗ trợ những chế độ pipeline, transaction và redirect nào trên **phiên bản cụ thể**?
7. Sau resharding/failover, ứng dụng có xử lý được `MOVED`, `ASK`, timeout và kết quả ghi **không chắc chắn** không?

Mục tiêu của bài học là xây dựng phương pháp **kiểm tra tính tương thích trước khi chuyển sang Cluster**, nhận biết lỗi sớm và thiết kế lại những thao tác cần tính nguyên tử hoặc hiệu năng cao mà không vô tình làm mất dữ liệu.

## 1. Khác biệt cốt lõi giữa standalone, Sentinel và Cluster

### 1.1. Standalone

Một Redis standalone thông thường lưu các key trên cùng một server:

```text
Spring service
      |
      v
Redis primary
  ├── cart:42:items
  ├── cart:42:total
  ├── product:99
  └── stock:sku-1
```

Những lệnh nhiều key như:

```redis
MGET cart:42:items cart:42:total
```

không gặp vấn đề phân bố slot, dù vẫn phải tuân thủ type và cú pháp của lệnh.

### 1.2. Sentinel

Redis Sentinel giám sát **một nhóm replication** và có thể chuyển primary khi node lỗi. Trong mô hình một primary với replica:

```text
              Sentinel
                 |
          Redis primary
           /         \
       replica A    replica B
```

Dữ liệu ghi vẫn thuộc một primary logic. Sentinel giúp discovery và failover, nhưng không chia toàn bộ key thành nhiều shard độc lập theo hash slot như Redis Cluster.

### 1.3. Redis Cluster

Cluster phân tán 16.384 hash slot qua nhiều primary:

```text
                          Redis Cluster

                  Slots 0 .. 5460          -> Primary A
                  Slots 5461 .. 10922      -> Primary B
                  Slots 10923 .. 16383     -> Primary C

                         +--------------------+
                         | Spring application |
                         +--------------------+
                                  |
               +------------------+------------------+
               |                  |                  |
               v                  v                  v
           Primary A          Primary B          Primary C
          (some keys)        (some keys)        (some keys)
               |                  |                  |
           Replica A          Replica B          Replica C
```

Lệnh dùng một key có thể được định tuyến tới node sở hữu slot của key đó. Nhưng nếu **một lệnh cần thao tác trên nhiều key**, Redis thường đòi hỏi các key liên quan **cùng slot** để cùng một node thực hiện thao tác.

Đây là sự thay đổi tác động trực tiếp tới code.

### 1.4. Bảng so sánh

| Khía cạnh | Standalone/Sentinel một primary | Redis Cluster |
|---|---|---|
| Phân bố key | Một primary logic | 16.384 slot phân trên nhiều primary |
| `GET`/`SET` một key | Thông thường được hỗ trợ | Được định tuyến theo hash slot |
| `MGET` nhiều key bất kỳ | Có thể thực thi trên một server | Cần xem quy tắc **cùng slot** |
| Lua truy cập nhiều key | Cùng server | Key của một execution phải phù hợp cùng slot |
| Transaction nhiều key | Có thể chạy trên một primary | Phải phù hợp slot/node; không có distributed transaction toàn cluster |
| Pipeline | Một kết nối đích là mô hình đơn giản | Phụ thuộc routing, node, driver, redirect |
| Resharding | Không có chuyển slot giữa primary | Có thể chuyển ownership slot |
| Replica đọc | Có thể stale | Cũng có thể stale; còn phụ thuộc node/slot |
| Cấu hình kết nối | Endpoint hoặc Sentinel discovery | Cluster topology discovery và redirect |

**Chuyển sang Cluster không tạo một Redis database nguyên tử trải trên mọi primary.** Các phép toán nhiều key cần được thiết kế theo ranh giới slot.

## 2. Hiểu 16.384 hash slot và key routing

Redis Cluster xác định slot từ byte của key bằng hàm băm CRC16 và lấy modulo 16384:

```text
slot = CRC16(keyBytes) mod 16384
```

Nếu key chứa **hash tag** hợp lệ, Redis dùng phần bên trong cặp ngoặc nhọn đầu tiên phù hợp thay cho toàn bộ key để tính slot.

Ví dụ:

```text
cart:{customer-42}:items
cart:{customer-42}:total
cart:{customer-42}:updated
```

Ba key có cùng phần hash tag `customer-42`, vì vậy cùng hash slot.

Ngược lại:

```text
cart:customer-42:items
cart:customer-42:total
```

có cùng tiền tố dễ đọc nhưng **không được bảo đảm** cùng slot.

### 2.1. Cách kiểm tra slot bằng Redis CLI

Trên một Redis Cluster đang hoạt động:

```redis
CLUSTER KEYSLOT cart:{customer-42}:items
CLUSTER KEYSLOT cart:{customer-42}:total
CLUSTER KEYSLOT cart:{customer-99}:items
```

Hai lệnh đầu trả **cùng một số slot**. Key thuộc `customer-99` thường rơi vào slot khác, nhưng để kiểm tra cụ thể phải xem kết quả từ cluster đang chạy.

Có thể so sánh key không có hash tag:

```redis
CLUSTER KEYSLOT cart:customer-42:items
CLUSTER KEYSLOT cart:customer-42:total
```

Không tự giả định kết quả bằng nhau chỉ vì phần tên tương tự.

**Lưu ý về công cụ:** `CLUSTER KEYSLOT` là lệnh dùng trong môi trường Redis Cluster. Không lấy lỗi “cluster support disabled” trên standalone làm kết luận một key không hợp lệ.

### 2.2. Các trường hợp hash tag dễ hiểu sai

| Key | Thành phần dùng để hash slot |
|---|---|
| `cart:{42}:items` | `42` |
| `cart:{42}:total` | `42` |
| `cart:{99}:items` | `99` |
| `cart:42:items` | Toàn bộ key |
| `a{42}b` | `42` |
| `a{}b` | Thông thường toàn bộ key vì tag rỗng |
| `a{{42}}b` | Theo quy tắc tìm cặp ngoặc đầu, phần tag có thể khác với suy đoán bằng mắt |

Không nên tự xây một parser đơn giản lấy cặp `{}` cuối cùng để tính slot. Với key phức tạp, kiểm chứng bằng `CLUSTER KEYSLOT`.

### 2.3. Redis hash theo **byte**, không theo ý nghĩa tên Java

Trong Spring Data Redis, key được serialize thành `byte[]` trước khi gửi Redis. Ví dụ:

```java
String key = "cart:{customer-42}:items";
```

sẽ khác về byte nếu dùng `StringRedisSerializer` so với một serializer có prefix, metadata hoặc định dạng JDK serialization.

Vì Redis tính hash slot từ **key bytes thực tế**, hãy:

- Ưu tiên serializer key dễ dự đoán, như `StringRedisSerializer`, khi phù hợp.
- Kiểm tra serializer của từng `RedisTemplate`, `RedisCacheManager` và repository.
- Đừng dựa vào `key.toString()` của Java để suy ra Redis sẽ nhìn thấy key gì.
- Dùng CLI kiểm tra trên key **đúng như đã lưu**, không chỉ trên tên được suy diễn từ code.
- Khi đổi serializer lúc migration, cân nhắc tương thích dữ liệu và việc các service đang chạy cùng lúc.

## 3. Phân loại lệnh: một key, nhiều key và tác vụ toàn node

Không phải tất cả lệnh Redis đều có cùng ràng buộc trên Cluster.

### 3.1. Lệnh một key

Những lệnh phổ biến:

```redis
GET user:42:name
SET user:42:name "An"
INCR metrics:views:42
HGET user:42:profile city
HSET user:42:profile city "Hue"
LPUSH events:42 event-1
SADD tags:42 java
ZADD scores:week-1 150 user-42
EXPIRE cache:42 60
```

Mỗi lệnh thao tác trên một Redis key (dù Hash có nhiều field, ZSet có nhiều member). Một Redis Cluster client phù hợp có thể định tuyến những lệnh này tới node đang sở hữu slot.

Điều đó **không có nghĩa các lệnh riêng lẻ có tính nguyên tử tập thể**. Hai lệnh `GET key` và `SET key` vẫn có thể bị client khác chen giữa, dù cùng slot.

### 3.2. Lệnh nhiều key có yêu cầu cùng slot

Những lệnh thường phải rà soát:

```redis
MGET key1 key2
MSET key1 value1 key2 value2
DEL key1 key2
UNLINK key1 key2
EXISTS key1 key2
RENAME key1 key2
SUNION set1 set2
SINTER set1 set2
SDIFF set1 set2
ZUNION ... / ZINTER ...
XREAD STREAMS stream1 stream2 0-0 0-0
EVAL ... 2 key1 key2
```

Với nhiều lệnh trong nhóm này, nếu key thuộc các slot khác nhau, Redis có thể trả:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

Lưu ý rằng **một số phiên bản client/framework có thể tự tách hoặc thực hiện fan-out cho một số API cấp cao**; hành vi ấy không đồng nghĩa Redis đã thực thi một multi-key command nguyên tử trên các shard. Cần kiểm tra API và driver cụ thể.

Ví dụ `DEL key1 key2` như **một lệnh Redis** có ràng buộc khác với việc gọi hai lệnh `DEL` riêng cho từng key. Trường hợp thứ hai có thể được định tuyến tới hai node, nhưng **không có atomicity toàn cluster**.

### 3.3. Các lệnh quản trị và keyspace toàn cụm

Một số lệnh không mang nghĩa “thực thi trên mọi node” chỉ vì caller kết nối Cluster:

```redis
DBSIZE
KEYS pattern
SCAN cursor
INFO
FLUSHDB
```

Phạm vi của các lệnh quản trị có thể là node đang được gọi hoặc được client/framework triển khai fan-out tùy API. Không được mặc định một lệnh `KEYS` tại một node đã liệt kê mọi key trong Cluster.

Đặc biệt:

- Redis Cluster sử dụng database logic `0`; không thiết kế dựa trên `SELECT 1`, `SELECT 2` như nhiều ứng dụng standalone.
- `SCAN` thường là vòng quét **theo node**; muốn khám phá toàn Cluster cần chiến lược quét từng primary hoặc API cluster-aware hỗ trợ rõ ràng.
- `KEYS pattern` có thể gây chặn trên node xử lý và không phù hợp cho công việc quét rộng thường xuyên.
- `FLUSHDB`/`FLUSHALL` là thao tác phá dữ liệu; không dùng để “làm sạch Cluster” trong phép thử migration trừ khi đó là môi trường test cô lập.

Việc kiểm kê phải bao gồm **lệnh nền từ framework** (ví dụ clear cache, repository indexing, keyspace event listener), không chỉ những lệnh xuất hiện trực tiếp trong service.

## 4. Bài thử đầu tiên: `MGET` cùng slot và khác slot

Trong một lab Redis Cluster, tạo các key cùng hash tag:

```redis
SET cart:{customer-42}:items "A,B,C"
SET cart:{customer-42}:total "350000"
```

Thử:

```redis
MGET cart:{customer-42}:items cart:{customer-42}:total
```

Đây là hai key cùng slot, nên phù hợp với quy tắc của `MGET` trong Cluster.

Tạo thêm:

```redis
SET cart:{customer-99}:total "780000"
```

Rồi thử:

```redis
MGET cart:{customer-42}:items cart:{customer-99}:total
```

Thông thường sẽ gặp `CROSSSLOT` vì hai hash tag khác nhau dẫn tới slot khác nhau. Nếu làm một ví dụ với hai key bất kỳ không có hash tag, phải xác minh slot trước; hai key khác nhau vẫn **có thể trùng slot ngẫu nhiên**, không nên xây test dựa trên đoán mò.

### 4.1. `redis-cli -c` không sửa được `CROSSSLOT`

Khi kết nối Cluster qua CLI:

```bash
redis-cli -c -h 127.0.0.1 -p 7000
```

tùy chọn `-c` giúp CLI theo redirect khi gửi một lệnh tới sai node. Nhưng **redirect không làm một lệnh `MGET` trải qua hai slot trở nên hợp lệ**.

Phân biệt:

```text
MOVED <slot> <host:port>
```

nghĩa là client cần gửi lệnh tới node khác đang sở hữu slot.

Trong khi:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

là vấn đề **thiết kế tập key của một lệnh**, không thể sửa chỉ bằng retry sang node khác.

## 5. Lập danh mục mọi thao tác Redis trước migration

Đừng chỉ tìm từ khóa `MGET` hoặc `EVAL` trong controller. Một thao tác cấp framework có thể sinh nhiều Redis commands.

Một bảng kiểm kê hữu ích:

| Tầng gọi | Ví dụ | Cần kiểm tra |
|---|---|---|
| `opsForValue()` | `multiGet`, `multiSet` | Tập key có cùng slot không? |
| `opsForHash()` | `putAll`, `entries` | Thao tác chủ yếu trên một Redis key hay nhiều key? |
| `opsForList()` | `leftPop`, di chuyển giữa list | Một hay hai Redis key, có yêu cầu cùng slot? |
| `opsForSet()` | `union`, `intersect`, `difference` | Các set key khác slot? |
| `opsForZSet()` | Union/intersection giữa nhiều ZSet | Co-location và hiệu quả dữ liệu? |
| `opsForStream()` | Đọc đồng thời nhiều stream | Nhiều stream key có cùng slot? |
| `RedisTemplate.executePipelined` | Pipeline GET/SET/INCR nhiều key | Driver có hỗ trợ routing/pipeline Cluster? |
| `RedisTemplate.execute(RedisScript)` | Lua `KEYS[1..n]` | Cùng slot, khai báo key đầy đủ? |
| `SessionCallback` | `multi`, `watch`, `exec` | Connection và tất cả key có tương thích Cluster? |
| `@Cacheable` / `Cache.clear()` | Key prefix, quét/xóa cache | Prefix/clear theo node và khối lượng dữ liệu |
| Redis Repository | `save`, `delete`, index | Key phụ, secondary index, transaction giả định |
| Khóa phân tán | `SET NX`, unlock script | Lock key và các key mà script động tới |
| Job/batch quản trị | `SCAN`, `KEYS`, `DBSIZE` | Không giả định một node đại diện toàn Cluster |

Trong báo cáo migration, mỗi thao tác nên được phân loại:

```text
SINGLE_KEY
SAME_SLOT_MULTI_KEY
CROSS_SLOT_DESIGN_REQUIRED
NODE_LOCAL_ADMIN
CLIENT_SPECIFIC_PIPELINE
SCRIPT_SAME_SLOT
UNSUPPORTED_OR_UNVERIFIED
```

Mục tiêu là **xác định lệnh nào có thể giữ nguyên, lệnh nào cần đổi key design và lệnh nào phải thay thuật toán**.

## 6. Hash tag: cách gom key cùng slot đúng mục đích

Nếu một nghiệp vụ bắt buộc thao tác hai key trong cùng lệnh hoặc script, dùng hash tag là công cụ hữu ích.

Ví dụ giỏ hàng của một khách:

```text
cart:{customer-42}:items
cart:{customer-42}:total
cart:{customer-42}:version
```

Tất cả key cùng tag `customer-42` nên cùng slot. Khi đó một lệnh `MGET`, Lua script hoặc transaction tác động lên nhóm key này có thể chạy trên node đang sở hữu slot đó.

### 6.1. Chọn tag theo **đơn vị nhất quán nghiệp vụ**

Tag phù hợp thường là:

- Một giỏ hàng.
- Một đơn hàng.
- Một tài khoản có một nhóm state cần thao tác nguyên tử.
- Một session.
- Một aggregate/domain entity được cập nhật theo nhiều key.

Ví dụ:

```text
order:{order-1001}:state
order:{order-1001}:events
order:{order-1001}:version
```

Nhưng không nên dùng tag quá rộng:

```text
order:{ALL}:state:1001
order:{ALL}:state:1002
order:{ALL}:state:1003
```

Vì **mọi key có tag `ALL` cùng slot**, chúng bị dồn vào một primary, có thể tạo **hot slot** và làm Cluster mất lợi ích phân phối tải.

### 6.2. Không thêm hash tag tùy tiện cho toàn ứng dụng

Một cách sửa nhanh sai hướng:

```text
Trước:
  product:1
  product:2
  product:3

Sau:
  product:{products}:1
  product:{products}:2
  product:{products}:3
```

Về kỹ thuật cả ba key giờ cùng slot. Nhưng hàng triệu product key cũng sẽ cùng một slot, làm một node chịu phần lớn CPU/memory/traffic.

**Co-location có cái giá của nó.** Chỉ đặt cùng tag những key thật sự cần thao tác chung trong một phạm vi nguyên tử hoặc một nhóm truy cập có lý do rõ ràng.

### 6.3. Ranh giới aggregate đôi khi không thể gom đơn giản

Giả sử một lần đặt hàng cần cập nhật:

```text
stock:sku-42
order:order-1001
customer:customer-9
```

Ba key thuộc ba aggregate khác nhau. Việc thêm cùng hash tag theo `order-1001` có thể khiến inventory không còn thuận tiện cho những đơn hàng khác, hoặc đẩy mọi đơn hàng của một SKU vào cùng slot.

Không thể giải quyết mọi giao dịch phân tán bằng cách nhét tất cả dữ liệu vào một tag. Khi nghiệp vụ vượt qua ranh giới shard, cần xem:

- Một thao tác nguyên tử trên **một key/hash aggregate** thay vì nhiều key.
- Kiến trúc reservation, saga hoặc các bước có idempotency.
- Event/outbox để đồng bộ trạng thái cuối cùng.
- Một storage có transaction liên key/aggregate theo yêu cầu, nếu cần invariant mạnh.

## 7. Thiết kế key API trong Spring để tránh lặp logic hash tag

Một cách đơn giản là tập trung tạo key vào một hàm:

```java
package com.example.redis;

public final class CartKeys {

    private CartKeys() {}

    public static String items(String customerId) {
        return "cart:{" + safeTag(customerId) + "}:items";
    }

    public static String total(String customerId) {
        return "cart:{" + safeTag(customerId) + "}:total";
    }

    public static String version(String customerId) {
        return "cart:{" + safeTag(customerId) + "}:version";
    }

    private static String safeTag(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is empty");
        }

        // Với ID không phải dạng cố định, cần encode để dấu {} do
        // user cung cấp không làm đổi cách Redis hiểu hash tag.
        if (customerId.indexOf('{') >= 0
                || customerId.indexOf('}') >= 0) {
            throw new IllegalArgumentException(
                "customerId must not contain braces"
            );
        }

        return customerId;
    }
}
```

Trong production, nếu customer ID có thể chứa ký tự tùy ý, nên định nghĩa **codec ổn định** cho tag (ví dụ Base64 URL-safe hoặc một mã định danh đã chuẩn hóa) thay vì chỉ cấm ngoặc.

Không nên thay đổi cách tạo key ở một service mà không cập nhật service khác cũng đọc cùng dữ liệu. Migration key naming thường cần kế hoạch version và chuyển dữ liệu.

### 7.1. Ví dụ `multiGet` sau khi co-locate

```java
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;

public class CartReadService {

    private final StringRedisTemplate redis;

    public CartReadService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> readItemsAndTotal(String customerId) {
        List<String> keys = List.of(
            CartKeys.items(customerId),
            CartKeys.total(customerId)
        );

        return redis.opsForValue().multiGet(keys);
    }
}
```

Cả hai key dùng cùng tag theo `customerId`. Ví dụ này phù hợp khi muốn giữ `MGET` như một lệnh Redis nhiều key; trong Cluster cần xác nhận serializer và topology thực tế để bảo đảm hai key đến cùng slot.

`multiGet` có thể trả danh sách chứa `null` cho key thiếu. Không lấy kết quả `null` của một vị trí làm dấu hiệu toàn bộ lệnh đã thất bại.

## 8. Transaction `MULTI/EXEC` và `WATCH` có giới hạn theo slot

Trong standalone, một transaction có thể queue lệnh tác động đến nhiều key khác nhau trên cùng server:

```redis
MULTI
SET order:1001 PAID
INCR metrics:orders-paid
EXEC
```

Khi lên Cluster, nếu hai key ở slot khác nhau, không thể mặc định nhóm lệnh này chạy như một transaction duy nhất. **Redis Cluster không cung cấp `MULTI/EXEC` nguyên tử trải qua nhiều primary.**

### 8.1. Transaction cùng slot

Đổi các key cần phối hợp thành:

```text
order:{1001}:status
order:{1001}:version
```

Ví dụ CLI:

```redis
MULTI
SET order:{1001}:status PAID
INCR order:{1001}:version
EXEC
```

Hai key cùng hash tag `1001`, vì vậy có thể cùng được xử lý trên node sở hữu slot đó.

Tuy nhiên:

- `MULTI/EXEC` không có rollback tổng quát khi lệnh runtime lỗi sau khi nhóm đã bắt đầu chạy.
- Không cho phép một lệnh trong transaction dùng kết quả của lệnh trước để rẽ nhánh phía client trong khi đang queue.
- Transaction trên Redis không đồng nghĩa transaction JPA/PostgreSQL.
- Khi slot đang resharding hoặc client bị redirect, có thể cần retry toàn bộ **với hiểu biết về kết quả đã xảy ra** và giới hạn driver.
- Một transaction cùng slot vẫn không tự bảo đảm dữ liệu được replica xác nhận trước khi primary crash.

### 8.2. `WATCH` phải dùng trong đúng phạm vi connection/slot

Optimistic locking bằng `WATCH` có thể phát hiện key bị thay đổi trước `EXEC` theo ngữ nghĩa Redis. Khi chuyển Cluster:

- Những key được `WATCH` và thao tác transaction liên quan cần phù hợp **cùng node/slot**.
- Cần giữ connection/session đúng trong suốt `WATCH` → `MULTI` → `EXEC`.
- Không dùng hai lời gọi template độc lập rồi giả định Spring sẽ giữ cùng session.
- Với `SessionCallback`, vẫn phải xác nhận khả năng transaction của driver khi dùng Cluster.
- `WATCH` không giải quyết transaction giữa hai slot khác nhau.

### 8.3. Không thay thế multi-key transaction bằng pipeline

Một cách nghĩ sai:

```text
MULTI + SET A + SET B + EXEC không chạy CROSSSLOT
    |
    v
Đổi sang pipeline SET A, SET B
    |
    v
Tưởng vẫn nguyên tử
```

Pipeline có thể gửi hai lệnh tới hai node, nhưng **không đảm bảo cả hai cùng thành công hoặc cùng thất bại**, và client khác có thể quan sát trạng thái trung gian.

Nếu yêu cầu nghiệp vụ là “đã thanh toán thì order và inventory luôn đồng bộ nguyên tử”, pipeline không phải giải pháp thay thế distributed transaction.

## 9. Pipeline trên Cluster: không phải cứ cùng template là cùng connection

Trong standalone, pipeline có thể được hình dung:

```text
Client ---- [GET A, GET B, SET C] ----> Redis server
Client <--- [resultA, resultB, OK] ---
```

Với Cluster:

```text
                      Spring Data Redis
                             |
                  [GET A, GET B, SET C]
                             |
                   Cluster-aware driver
                    /       |        \
                   v        v         v
                 Node A   Node B     Node C
```

Một pipeline có thể chứa lệnh đến **nhiều slot, nhiều node**. Tùy driver/phiên bản Spring Data Redis, client có thể:

- Route/group lệnh theo node phù hợp.
- Duy trì nhiều connection và ghép kết quả.
- Giới hạn một số kiểu pipeline trong Cluster.
- Trả lỗi cho những tổ hợp lệnh không được hỗ trợ.
- Xử lý redirect bằng cơ chế phù hợp hoặc yêu cầu retry ở tầng application.

Do đó, **không mặc định** `executePipelined(...)` trên standalone sẽ giữ nguyên behavior khi bật Cluster.

### 9.1. Phân biệt “nhiều lệnh” với “một lệnh nhiều key”

Hai mẫu này không giống nhau:

```text
MGET keyA keyB
```

là **một Redis command có hai key**, có thể gặp `CROSSSLOT` nếu khác slot.

Trong khi:

```text
Pipeline:
    GET keyA
    GET keyB
```

là **hai Redis commands riêng biệt**; một Cluster-aware client có thể định tuyến từng lệnh tới node của nó, nếu chế độ pipeline đó được driver hỗ trợ.

Ngay cả khi cả hai `GET` chạy thành công, pipeline **không tạo snapshot nguyên tử trên hai node**. Một client khác có thể thay đổi một key giữa hai lần đọc.

### 9.2. Hậu quả của redirect trong pipeline

Khi resharding, một slot có thể chuyển từ Node A sang Node B. Lệnh mới tới Node A có thể nhận:

```text
MOVED 12000 10.0.0.8:6379
```

Hoặc trong giai đoạn di chuyển key, cơ chế redirect tạm thời có thể dùng:

```text
ASK 12000 10.0.0.8:6379
```

**`MOVED` và `ASK` không tương đương:**

- `MOVED`: thông báo ownership slot đã ở node khác; client thường cập nhật topology/routing.
- `ASK`: redirect tạm thời khi slot đang di chuyển; client thực hiện thủ tục phù hợp cho lệnh được chuyển tiếp, không nhất thiết cập nhật slot map vĩnh viễn ngay.
- Một số lỗi khác như `TRYAGAIN` hoặc `CLUSTERDOWN` cần được xử lý theo trạng thái cluster, không chỉ thay endpoint.

Trong một pipeline đang có nhiều lệnh và phản hồi, xử lý redirect phức tạp hơn một lệnh đơn lẻ. Cần dựa vào khả năng thực sự của driver/phiên bản và test trong lúc resharding.

### 9.3. Lỗi một phần và kết quả không chắc chắn

Nếu pipeline gồm:

```text
INCR metrics:orders:1  -> Node A
INCR metrics:orders:2  -> Node B
SET cache:p42 ...     -> Node C
```

rồi mạng ngắt, ứng dụng có thể không biết lệnh nào đã được thực thi. Không retry mù quáng toàn bộ pipeline có lệnh **cộng dồn** như `INCR`, vì có thể thực thi hai lần.

Cần:

- Phân loại lệnh idempotent và không idempotent.
- Dùng operation ID hoặc token nghiệp vụ khi cần retry an toàn.
- Tách các batch theo phạm vi node/slot khi driver khuyến nghị.
- Giới hạn kích thước pipeline để tránh timeout và áp lực bộ nhớ.
- Không báo thành công cả batch nếu phản hồi cho từng thao tác chưa được xác nhận theo semantics của API.

## 10. Ví dụ `executePipelined` và điều cần thử trên Cluster

Một mẫu Spring Data Redis:

```java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;

public class CartPipelineReader {

    private final StringRedisTemplate redis;

    public CartPipelineReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> readMany(String customerId) {
        RedisSerializer<String> serializer =
                redis.getStringSerializer();

        List<String> keys = List.of(
            CartKeys.items(customerId),
            CartKeys.total(customerId),
            CartKeys.version(customerId)
        );

        return redis.executePipelined(
            (RedisCallback<Object>) connection -> {
                for (String key : keys) {
                    connection.stringCommands().get(
                        serializer.serialize(key)
                    );
                }

                // executePipelined yêu cầu callback return null.
                return null;
            }
        );
    }
}
```

Ở đây, ba key có cùng hash tag theo `customerId`, vì vậy cùng slot. Đây là **một ca tương thích đơn giản** để thử trong Cluster.

Nhưng cần phân biệt hai ràng buộc:

1. **Cùng slot** giúp các lệnh cùng được định tuyến về một primary, thuận tiện cho pipeline nếu được hỗ trợ.
2. **Pipeline support** vẫn phải được xác nhận với driver/client và Spring Data Redis version đang dùng.

Cùng slot không tự khiến một chế độ pipelining không được driver hỗ trợ trở nên có sẵn.

### 10.1. Kiểm tra các giả định trong callback

- Lệnh gửi qua `RedisConnection` cấp thấp thường nhận `byte[]`; phải serialize key đúng cách.
- Kết quả của các lời gọi `get` bên trong callback **không phải** kết quả mà ta xử lý trực tiếp khi lệnh đang được pipeline.
- Callback trả `null`; lấy phản hồi từ `List<Object>` mà `executePipelined` trả về.
- Mỗi phản hồi cần được ghép với lệnh tương ứng; không ép toàn bộ kết quả sang một kiểu nếu lệnh hỗn hợp.
- Nếu thêm một lệnh vào giữa callback, thứ tự mapping kết quả cũng thay đổi.
- Pipeline không đảm bảo `GET` từ ba key là một snapshot nhất quán, ngay cả khi cùng slot.
- Thao tác ghi lỗi ở giữa không khiến các thao tác đã thực thi bị rollback.

### 10.2. Một bộ ca test pipeline bắt buộc

| Test | Mục đích |
|---|---|
| 100 `GET` cùng slot | Hành vi đơn giản, thứ tự trả kết quả |
| 100 `GET` trải nhiều slot | Khả năng routing nhiều node |
| `GET`/`SET`/`INCR` hỗn hợp | Kiểu phản hồi và thứ tự |
| Key không tồn tại | Cách biểu diễn null/cache miss |
| Một key sai type | Cách driver trả exception/lỗi một phần |
| Pipeline đang chạy khi reshard | `MOVED`/`ASK`, retry và kết quả không chắc chắn |
| Failover primary giữa batch | Command timeout, reconnect, duplicate |
| Batch rất lớn | Throughput, memory, latency p95/p99 |
| Lệnh ghi không idempotent | Chứng minh retry phải có quy tắc nghiệp vụ |

Không cần chạy mọi thử nghiệm bằng một phương thức duy nhất; mỗi test nên cô lập một loại rủi ro để biết chính xác giới hạn nào đang bị vi phạm.

## 11. Khi nào thay multi-key bằng nhiều single-key commands?

Giả sử service từng gọi:

```java
redis.opsForValue().multiGet(
    List.of("product:p1", "product:p2", "product:p3")
);
```

Nếu ba key ở các slot khác nhau, một hướng là chia thành các lệnh `GET` riêng:

```java
public List<String> loadSequentially(List<String> keys) {
    return keys.stream()
        .map(k -> redis.opsForValue().get(k))
        .toList();
}
```

Điều này có thể chạy qua cluster-aware connection factory, nhưng có **nhiều round trip** và không giữ snapshot nhất quán giữa các key.

Khi muốn tối ưu hơn, có thể:

- Dùng client/API hỗ trợ fan-out nhiều lệnh single-key.
- Chia pipeline theo slot/node khi phù hợp.
- Chỉ dùng `MGET` cho những key có cùng tag.
- Dùng các lời gọi reactive với giới hạn concurrency nếu ứng dụng ở mô hình WebFlux.
- Thiết kế lại data model để một aggregate thường đọc cùng lúc được lưu trong **một Hash hoặc một String** khi phù hợp.

**Không được thay tất cả multi-key command bằng các lệnh single-key nếu nghiệp vụ yêu cầu tính nguyên tử.** Đó là thay đổi semantics chứ không chỉ thay đổi cách gửi lệnh.

## 12. Lua script: ranh giới slot nghiêm ngặt hơn code bình thường

Lua script giúp gom nhiều lệnh thành một đơn vị thực thi nguyên tử trên Redis server. Trong Cluster, script phải được thực thi ở một node có quyền truy cập những key liên quan.

Ví dụ Lua truy cập hai key:

```lua
local current = redis.call('GET', KEYS[1])
local limit = redis.call('GET', KEYS[2])
```

Khi gọi:

```redis
EVAL "<lua script>" 2 key1 key2
```

hai key phải được khai báo trong `KEYS` và **được đặt vào slot phù hợp**. Nếu khác slot, script không thể tự yêu cầu Node A đọc một key rồi Node B đọc key khác như một transaction nguyên tử toàn Cluster.

### 12.1. Ràng buộc phải kiểm tra

- **Mọi Redis key mà script truy cập cần được cung cấp rõ trong `KEYS`.**
- Các key liên quan đến một execution phải thuộc **cùng hash slot**, khi script thực hiện thao tác cần co-location.
- Các giá trị không phải key, như số lượng và ngưỡng, phải truyền qua `ARGV`, không giả làm key.
- Không xây tên key động dựa trên nội dung Redis data structure rồi kỳ vọng Redis sẽ route sang node khác.
- Không dùng `KEYS pattern` trong Lua để quét toàn bộ logical cluster.
- Script thực thi ở **một node**, không tự trở thành distributed transaction.
- Redis có thể chặn những lệnh khác trên node đó trong lúc script chạy lâu; thêm Cluster không làm Lua script nặng tự nhanh.
- Script cache (`EVALSHA`) được quản lý theo node/cơ chế triển khai, không phải một catalog SHA luôn có trên mọi node.

### 12.2. Ví dụ cách viết không phù hợp

Một script:

```lua
local keyA = KEYS[1]
local keyB = "customer:" .. ARGV[1] .. ":balance"

local a = redis.call('GET', keyA)
local b = redis.call('GET', keyB)

return {a, b}
```

`keyB` được tự tạo trong script, không được khai báo trong `KEYS`, và có thể ở slot khác. Đây là mẫu cần loại bỏ trước migration.

Một cách khác cũng có nguy cơ:

```lua
local accountIds = redis.call('SMEMBERS', KEYS[1])

for _, id in ipairs(accountIds) do
    local balance = redis.call('GET', "account:" .. id .. ":balance")
    -- ...
end
```

Script động tới những Redis key được tạo từ dữ liệu của Set, có thể phân tán khắp Cluster. Không thể coi đây là phép tính nguyên tử toàn cluster.

Thay bằng mô hình dữ liệu/thuật toán có tập key **được biết trước và cùng slot**, hoặc chia công việc thành các bước không nguyên tử kèm cơ chế consistency phù hợp.

## 13. Ví dụ Lua đúng phạm vi: cập nhật hai key cùng tag

Giả sử một giỏ hàng có:

```text
cart:{customer-42}:used
cart:{customer-42}:limit
```

Yêu cầu: chỉ tăng `used` nếu tổng không vượt `limit`. Một script có thể đọc hai key rồi cập nhật một key trong cùng execution.

```lua
-- KEYS[1] = cart:{customer-42}:used
-- KEYS[2] = cart:{customer-42}:limit
-- ARGV[1] = quantity (số nguyên dương được giới hạn nghiệp vụ)

if #KEYS ~= 2 or #ARGV ~= 1 then
    return redis.error_reply('invalid argument count')
end

local quantity = tonumber(ARGV[1])

if not quantity
    or quantity % 1 ~= 0
    or quantity < 1
    or quantity > 1000 then
    return redis.error_reply('invalid quantity')
end

local usedRaw = redis.call('GET', KEYS[1])
local limitRaw = redis.call('GET', KEYS[2])

if not limitRaw then
    return redis.error_reply('limit not initialized')
end

local used = tonumber(usedRaw or '0')
local limit = tonumber(limitRaw)

if not used or not limit then
    return redis.error_reply('invalid stored number')
end

if used < 0 or limit < 0 or used > limit then
    return redis.error_reply('invalid state')
end

if quantity > (limit - used) then
    return -1  -- Không đủ hạn mức
end

return redis.call('INCRBY', KEYS[1], quantity)
```

Ví dụ này giả định các số được lưu là số nguyên hợp lệ trong phạm vi nhỏ đủ để cả Lua number và Redis signed integer biểu diễn an toàn. Với hạn mức cực lớn, cần định nghĩa giới hạn chính xác và tránh sai số/overflow trước khi ghi.

Điểm phù hợp với Cluster:

1. Script nhận đúng hai key trong `KEYS`.
2. Key cùng tag `customer-42`.
3. Tập key không thay đổi theo nội dung được đọc.
4. Điều kiện và cập nhật nằm trong cùng một script trên node sở hữu slot.

Không có nghĩa script này có thể tự đọc thêm `product:{sku-99}:stock` ở một slot khác. Để cập nhật cả giỏ hàng và tồn kho của SKU trong một lần nguyên tử, cần thiết kế lại ranh giới dữ liệu hoặc áp dụng workflow khác.

### 13.1. Gọi script qua `StringRedisTemplate`

```java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

public class CartLimitService {

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> script;

    public CartLimitService(
        StringRedisTemplate redis,
        DefaultRedisScript<Long> cartLimitScript
    ) {
        this.redis = redis;
        this.script = cartLimitScript;
    }

    public long reserve(String customerId, long quantity) {
        String usedKey =
                "cart:{" + customerId + "}:used";

        String limitKey =
                "cart:{" + customerId + "}:limit";

        Long result = redis.execute(
            script,
            List.of(usedKey, limitKey),
            Long.toString(quantity)
        );

        if (result == null) {
            throw new IllegalStateException(
                "Lua script returned no result"
            );
        }

        return result;
    }
}
```

`DefaultRedisScript<Long>` phải được cấu hình với nội dung script Lua tương ứng:

```java
@Bean
DefaultRedisScript<Long> cartLimitScript() {
    DefaultRedisScript<Long> script = new DefaultRedisScript<>();
    script.setLocation(
        new ClassPathResource("redis/cart-limit.lua")
    );
    script.setResultType(Long.class);
    return script;
}
```

Trong ứng dụng thực tế cần import `@Bean` từ Spring và `ClassPathResource` từ Spring Core, đồng thời đặt file Lua ở `src/main/resources/redis/cart-limit.lua`.

Nên tái sử dụng `DefaultRedisScript` bean thay vì tạo mới script text ở mỗi request để cho phép framework tận dụng SHA caching theo khả năng của phiên bản.

**Lưu ý:** `customerId` trong ví dụ phải được chuẩn hóa hoặc encode để không chứa dấu ngoặc phá hash tag. Có thể dùng một tiện ích tạo key dùng chung như `CartKeys` ở phần 7.

### 13.2. Thử script khác slot

Gọi cùng logic với:

```text
KEYS[1] = cart:{customer-42}:used
KEYS[2] = cart:{customer-99}:limit
```

sẽ không phù hợp ràng buộc cùng slot cho execution. Cần có integration test xác nhận logic fail rõ thay vì che lỗi bằng retry không giới hạn.

## 14. `EVALSHA`, `NOSCRIPT` và di chuyển key

Trong standalone, ứng dụng có thể gọi `SCRIPT LOAD` một lần rồi dùng `EVALSHA` trên cùng Redis server. Trong Cluster, có nhiều primary; mỗi node có trạng thái script cache riêng theo semantics của Redis và phiên bản triển khai.

Các kịch bản:

```text
Script được nạp ở Node A
Key thuộc slot trên Node A
    |
    +-- EVALSHA có thể hoạt động

Slot chuyển sang Node B
Key giờ thuộc Node B
    |
    +-- Node B có thể chưa biết SHA
    +-- EVALSHA có thể trả NOSCRIPT
```

Failover/restart/eviction script cache cũng có thể làm script không còn sẵn trên node đích.

### 14.1. Cách xử lý

- Khi sử dụng `RedisTemplate.execute(RedisScript, ...)`, Spring Data Redis có thể áp dụng quy trình gọi bằng SHA rồi fallback bằng script text theo API/version; hãy xác nhận trong môi trường đang dùng.
- Nếu dùng `RedisConnection.evalSha(...)` cấp thấp trực tiếp, phải xử lý `NOSCRIPT` phù hợp, không giả định framework tự fallback.
- Không hardcode rằng script đã được nạp trên **mọi primary tương lai**.
- Với resharding, đảm bảo script vẫn dùng tập key cùng slot và client đủ khả năng xử lý redirect.
- Không retry vô điều kiện một script đã gây side effect khi nhận timeout/connection reset; kết quả có thể không chắc chắn.

**`NOSCRIPT` khác lỗi `CROSSSLOT`:** cái đầu nói node đang nhận lệnh không có script SHA đã nạp; cái sau nói tập key không hợp lệ cho thao tác. Tải lại Lua script không thể sửa được hai key ở khác slot.

### 14.2. Script chạy lâu và ảnh hưởng node

Một script duyệt hàng trăm nghìn phần tử có thể chặn xử lý những lệnh khác trên node đó. Redis Cluster phân bố tải nhưng **không làm một script nặng trở thành không chặn** trên primary giữ slot.

Nếu nhiều key cùng hash tag tạo hot slot, script dài càng làm primary ấy thành nút nghẽn. Cần giới hạn số key, vòng lặp, dữ liệu bên trong cấu trúc và latency p95/p99 của script.

## 15. `RedisRepository` và Spring Cache cần kiểm tra riêng

Dù một ứng dụng không có câu lệnh `MGET` trong service, framework vẫn có thể phát sinh nhiều Redis keys khi lưu entity hoặc dọn cache.

### 15.1. Redis Repository có thể ghi nhiều cấu trúc

Ví dụ entity:

```java
@RedisHash("products")
public class ProductEntity {
    @Id
    private String id;

    @Indexed
    private String category;

    private String name;
}
```

Một thao tác:

```java
productRepository.save(entity);
```

có thể liên quan đến:

- Key dữ liệu entity.
- Key metadata/index.
- Secondary index theo field.
- Keyspace tracking và các cấu trúc khác tùy cấu hình.

Không mặc định `save()` là **một Redis command nguyên tử** hoặc các key phụ đều cùng slot. Nếu implementation repository/secondary index dùng multi-key operation hoặc Lua/transaction, Cluster có thể phát sinh vấn đề không lộ ở code service.

Trước migration cần kiểm tra **khả năng hỗ trợ Redis Repository trong Cluster của Spring Data Redis version cụ thể**, mô hình index và tính nhất quán cần có. Đừng tự gắn `{id}` cho một key rồi giả định mọi index do framework tạo cũng sẽ cùng slot.

### 15.2. Spring Cache key prefix và clear

`RedisCacheManager` có thể tạo key kiểu:

```text
catalog::products::p42
catalog::products::p99
```

Các key này không mặc định cùng slot. Điều đó thường **không sao** cho đọc/ghi từng entry bằng `@Cacheable`, nhưng `Cache.clear()` có thể phải quét/xóa nhiều key trên nhiều primary.

Cần thử:

- `@Cacheable` GET/SET từng entry khi key ở nhiều slot.
- `@CacheEvict(key = ...)` với một key.
- `@CacheEvict(allEntries = true)` và behavior của cache writer trong Cluster.
- `BatchStrategies.scan(...)` với driver/version cụ thể.
- Key prefix/serializer khác nhau giữa những service.
- TTL và eviction khi khối lượng dữ liệu tăng.
- Tính an toàn khi cache clear đang diễn ra đồng thời với refill.

Không chuyển mọi cache key về một hash tag chỉ để `Cache.clear()` đơn giản hơn; như vậy có thể gom cả cache vào một slot, đi ngược lợi ích sharding.

### 15.3. Quét toàn Cluster không giống `SCAN` một node

Ví dụ một job cũ:

```java
Set<String> keys = redis.keys("cache:product:*");
```

Trên standalone, lời gọi có thể tìm các key của database đó. Trên Cluster, behavior phụ thuộc client/framework có thực hiện **fan-out tất cả primary** hay không.

Nên thay những job toàn keyspace bằng API được thiết kế cho Cluster và kiểm tra độ phức tạp, hoặc thiết kế namespace/version và quản lý key theo dữ liệu nguồn thay vì dùng quét rộng.

Nếu cần quét từng primary, cần hiểu cursor độc lập theo node và tránh chặn các Redis node bằng `KEYS` trên tập dữ liệu lớn.

## 16. Redis Streams và nhiều stream key

`XADD` một Stream key thường là thao tác một key, được route theo slot:

```redis
XADD stream:orders * type CREATED orderId o-42
```

Tuy nhiên, đọc nhiều stream cùng một lệnh:

```redis
XREAD STREAMS stream:orders stream:payments 0-0 0-0
```

cần xem quy tắc nhiều key trong Cluster. Nếu `stream:orders` và `stream:payments` ở khác slot, một `XREAD` chung có thể không hợp lệ.

Hướng thiết kế:

- Đọc từng stream bằng những consumer/connection độc lập.
- Dùng một tên stream hoặc một nhóm stream được co-locate **nếu thật sự cần**.
- Đừng gom mọi event của toàn hệ thống vào một hash tag nếu tạo hotspot.
- Xem xét consumer group, PEL, checkpoint và retention độc lập với key placement.

Một stream consumer dùng `ReadOffset.lastConsumed()` không tự đảm bảo ACK/reclaim pending hay transaction across shards. Cần giữ những bảo đảm delivery của Stream tách biệt với các ràng buộc slot.

## 17. Phân biệt redirect, lỗi slot và lỗi cluster

Trong thời gian migration/res harding/failover, có thể thấy nhiều mã phản hồi:

| Thông báo | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| `CROSSSLOT` | Một lệnh nhiều key không phù hợp slot | **Sửa thiết kế key/lệnh**, không retry mù |
| `MOVED` | Slot đang thuộc node khác | Cluster-aware client cập nhật routing/topology |
| `ASK` | Redirect tạm thời trong quá trình slot di chuyển | Client theo thủ tục ASK phù hợp |
| `TRYAGAIN` | Một thao tác tạm thời chưa thực hiện được trong trạng thái Cluster | Retry có giới hạn nếu operation an toàn và lỗi được hiểu đúng |
| `CLUSTERDOWN` | Cluster không thể phục vụ thao tác theo trạng thái hiện tại | Kiểm tra slot coverage, node health, retry/fallback theo chính sách |
| `READONLY` | Gửi write tới replica | Kiểm tra routing và role |
| `NOSCRIPT` | Script SHA không có ở node đích | Gửi script text/fallback theo client |
| Connection timeout/reset | Mạng/node lỗi, trạng thái thực thi có thể không xác định | Phân loại lệnh, idempotency và reconnect |
| `WRONGTYPE` | Thao tác sai kiểu dữ liệu | Kiểm tra schema/serializer, không sửa bằng retry |
| `OOM`/memory errors | Node thiếu bộ nhớ hoặc cấu hình maxmemory | Đánh giá phân phối key và memory |

Không nên viết:

```java
catch (Exception ex) {
    retryForever();
}
```

Nếu lỗi là `CROSSSLOT` hoặc `WRONGTYPE`, retry cùng request không thay đổi điều kiện sai. Với lệnh cộng dồn, retry sau timeout có nguy cơ thực hiện hai lần.

## 18. Redis Cluster client và topology discovery

Trong Spring Boot, có thể khai báo seed nodes:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:7000
          - 127.0.0.1:7001
          - 127.0.0.1:7002
        max-redirects: 5
      timeout: 3s
      connect-timeout: 2s
```

Đây là cấu hình minh họa cho Spring Boot dùng prefix `spring.data.redis.*`. Những phiên bản khác có thể dùng property khác hoặc có tùy chọn topology refresh riêng. Seed nodes giúp client tìm Cluster; **không phải danh sách duy nhất những node client sẽ cần kết nối**.

Nếu tự tạo connection factory:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class ClusterRedisConfiguration {

    @Bean
    public RedisConnectionFactory redisConnectionFactory() {
        RedisClusterConfiguration cluster =
                new RedisClusterConfiguration(
                    List.of(
                        "127.0.0.1:7000",
                        "127.0.0.1:7001",
                        "127.0.0.1:7002"
                    )
                );

        cluster.setMaxRedirects(5);

        return new LettuceConnectionFactory(cluster);
    }
}
```

Ví dụ này bỏ qua authentication/TLS để ngắn gọn. Khi tự tạo bean, phải kiểm tra các Spring Boot properties có còn được áp dụng như mong muốn không.

### 18.1. Topology refresh và resharding

Client cần nhận biết node/slot map mới khi:

- Slot được chuyển sang primary khác.
- Primary failover làm replica được promote.
- Node mới thêm vào cluster.
- Một endpoint bị thay đổi hoặc không còn reachable.

Lettuce có khả năng làm việc theo Cluster topology và có các chế độ topology refresh. Cách cấu hình proactive/periodic/adaptive refresh khác nhau theo phiên bản Lettuce và Spring Boot. Không giả định mọi chế độ refresh đều được bật mặc định.

Trong staging, cần thực sự thử **resharding khi có traffic**, không chỉ kết nối lần đầu vào cluster còn rảnh.

### 18.2. Docker/NAT và địa chỉ được Cluster quảng bá

Trong Docker, Redis có thể trả địa chỉ node nội bộ:

```text
172.20.0.5:6379
```

trong khi app chạy ở host chỉ truy cập được:

```text
localhost:7001
```

Seed node có thể kết nối được nhưng khi redirect tới node khác, client lại không truy cập được địa chỉ được quảng bá. Cần cấu hình network, announce hoặc address mapping phù hợp.

Đây là lỗi topology/network **khác với `CROSSSLOT`**. Đừng sửa code key routing nếu thực chất app không tới được endpoint được Cluster công bố.

## 19. Thiết lập một lab Cluster để thử tương thích

Một lab hữu ích thường gồm **ba primary và ba replica** trên các port khác nhau, để thử được cả slot distribution lẫn failover.

Ví dụ danh sách node cục bộ:

```text
127.0.0.1:7000  primary candidate
127.0.0.1:7001  primary candidate
127.0.0.1:7002  primary candidate
127.0.0.1:7003  replica candidate
127.0.0.1:7004  replica candidate
127.0.0.1:7005  replica candidate
```

Nếu mỗi Redis instance đã khởi chạy với:

```conf
cluster-enabled yes
cluster-config-file nodes-<port>.conf
cluster-node-timeout 5000
appendonly yes
```

và có cấu hình bind/port/dir riêng cùng mạng được phép liên lạc, có thể dùng CLI trên **lab cô lập**:

```bash
redis-cli --cluster create \
  127.0.0.1:7000 \
  127.0.0.1:7001 \
  127.0.0.1:7002 \
  127.0.0.1:7003 \
  127.0.0.1:7004 \
  127.0.0.1:7005 \
  --cluster-replicas 1
```

Lệnh chỉ minh họa khi đã có đủ sáu tiến trình Redis trên các port tương ứng. Không chạy với các endpoint production hoặc cluster đã có dữ liệu.

Kiểm tra topology:

```bash
redis-cli -c -p 7000 CLUSTER INFO
redis-cli -c -p 7000 CLUSTER NODES
redis-cli --cluster check 127.0.0.1:7000
```

Một số phiên bản Redis còn hỗ trợ thông tin chi tiết qua:

```redis
CLUSTER SHARDS
CLUSTER SLOTS
```

Cần xác nhận đủ 16.384 slot được phân bổ, cluster healthy và mỗi primary/replica có vai trò mong đợi trước khi chạy integration test.

### 19.1. Không lấy kết quả standalone làm bằng chứng Cluster-ready

Một unit test mock `StringRedisTemplate` hoặc integration test với một Redis container standalone **không thể kích hoạt `CROSSSLOT` thật**.

Nên có ít nhất một suite dùng Redis Cluster thật trong staging/CI riêng để kiểm tra các giả định về slot, routing, script và pipeline.

## 20. Checklist kiểm thử lệnh nhiều key

Một bộ kiểm thử cụ thể:

### Tình huống A – Lệnh một key

```redis
SET test:single:1 v1
GET test:single:1
INCR test:counter:1
```

Mục tiêu: single-key commands route đúng và deserialize giá trị như standalone.

### Tình huống B – Hai key cùng slot

```redis
SET test:{group-1}:a A
SET test:{group-1}:b B
MGET test:{group-1}:a test:{group-1}:b
```

Mục tiêu: một multi-key command hợp lệ chạy trên cùng slot.

### Tình huống C – Hai key khác slot

```redis
SET test:{group-2}:a A
SET test:{group-3}:b B
MGET test:{group-2}:a test:{group-3}:b
```

Trước khi khẳng định kết quả, kiểm tra:

```redis
CLUSTER KEYSLOT test:{group-2}:a
CLUSTER KEYSLOT test:{group-3}:b
```

Mục tiêu: phát hiện lỗi `CROSSSLOT` hoặc behavior khác được driver hỗ trợ ở API đang dùng; không che lấp khác biệt giữa một lệnh multi-key với các lệnh riêng.

### Tình huống D – Set/ZSet unions

Tạo các set khác slot rồi thử những lệnh `SUNION`/`SINTER` tương ứng. Không chỉ test GET/SET vì những lệnh tập hợp thường là nơi thiết kế cũ giả định một server.

### Tình huống E – Transaction

Thử `MULTI/EXEC` trên nhóm key cùng tag, sau đó trên nhóm key khác tag. Quan sát exception ở Spring Data Redis và trạng thái Redis sau lỗi.

### Tình huống F – Script

Thử `EVAL` với `KEYS` cùng slot, khác slot, rồi thử `EVALSHA` sau khi thay node/reshard hoặc làm mới script cache theo quy trình lab.

### Tình huống G – Pipeline

Thử pipeline một slot, nhiều slot, có key thiếu, có error và có resharding. Đối chiếu số lệnh, thứ tự phản hồi và dữ liệu thực tế.

## 21. Kiểm thử resharding và failover khi ứng dụng đang chạy

Cluster khỏe mạnh ở thời điểm triển khai đầu tiên không bảo đảm ứng dụng hoạt động đúng trong suốt vòng đời.

### 21.1. Resharding

Trong lab, tạo lưu lượng nền đọc/ghi qua `RedisTemplate`, sau đó di chuyển slot bằng công cụ quản lý Cluster. Quan sát:

```text
Trước chuyển:
    slot S thuộc Primary A
    Java route tới A

Đang chuyển:
    có thể gặp ASK, TRYAGAIN hoặc trạng thái di chuyển

Sau chuyển:
    slot S thuộc Primary B
    Java route tới B
```

Cần đo:

- Số lệnh lỗi/timeout.
- Thời gian đến khi client cập nhật routing.
- Pipeline có trả được đủ kết quả không.
- Script dùng key thuộc slot đang chuyển có bị lỗi tạm thời không.
- Ghi không idempotent có bị retry thành duplicate không.
- Cluster driver có bị giữ topology cũ quá lâu không.

### 21.2. Failover

Dừng một primary trên **lab** và để replica được promote. Kiểm tra:

- Client phát hiện endpoint mới.
- `GET`/`SET` một key hoạt động lại.
- Một transaction/script cùng slot vẫn chạy sau recovery.
- `EVALSHA` có fallback khi node mới chưa biết script SHA.
- Không có lệnh ghi nào được đánh dấu thành công khi chưa có xác nhận.
- Các thao tác timeout có outcome không chắc chắn được ghi nhận riêng.

**Không dùng failover chỉ để thử “có reconnect không” rồi bỏ qua data consistency.** Redis Cluster replication cũng thường bất đồng bộ; một write đã trả thành công có thể chưa được replica mới nhận tại thời điểm primary lỗi.

### 21.3. Timeouts và idempotency

Ví dụ:

```text
Client gửi INCR balance-adjustments
Primary thực thi INCR
Phản hồi mất khi failover
Client timeout
Client retry INCR
```

Nếu Redis đã tăng lần đầu và vẫn còn dữ liệu ở primary mới, retry có thể tăng tiếp lần thứ hai.

Một thao tác `INCR`, `LPUSH`, `ZINCRBY` hoặc `XADD *` không nên retry mù quáng sau timeout, cho dù lỗi xảy ra đồng thời với `MOVED`, mạng mất hay failover.

Ứng dụng cần mô hình operation ID/idempotency hoặc bước đối chiếu nguồn sự thật phù hợp. Redis Cluster không tự cung cấp exactly-once execution cho toàn bộ workflow nhiều node.

## 22. Hiệu năng: Cluster không có nghĩa mọi thao tác nhanh hơn

Cluster giúp phân chia dữ liệu và tải khi key được phân bố đều. Nhưng có những trường hợp hiệu năng xấu đi sau migration:

- Nhiều request cross-node tăng kết nối và round trip.
- Pipeline trước đây chỉ dùng một connection phải được tách theo node.
- Một hash tag quá rộng tạo **hot slot**, chỉ một primary gánh tải.
- Script dài chặn những lệnh khác trên primary giữ slot.
- Quét/dọn cache phải đi qua nhiều node.
- Topology refresh và redirect tạo thêm chi phí tạm thời.
- Key placement gây mất cân bằng RAM hoặc network giữa primary.
- Nhiều thao tác vốn nguyên tử bị tách thành workflow nhiều bước, cần retry/reconciliation.

Do đó nên đo:

| Chỉ số | Cần quan sát |
|---|---|
| Throughput theo từng primary | Có phân bố đều hay một node quá tải? |
| CPU/memory theo node | Có hot slot hoặc mất cân bằng dữ liệu? |
| Request p50/p95/p99 | Độ trễ của API trong điều kiện bình thường và reshard/failover |
| Redis command latency | Lệnh nào bị chậm khi đi qua cluster? |
| Pipeline batch duration | Khi chia node, latency/overhead thay đổi ra sao? |
| Network connections và bytes | Có tăng đáng kể lượng kết nối/chuyển dữ liệu? |
| `MOVED`/`ASK`/`TRYAGAIN` | Mức redirect và ổn định topology |
| `CROSSSLOT` | Lỗi thiết kế key hoặc command chưa được xử lý |
| `NOSCRIPT` | Cơ chế nạp script khi node thay đổi |
| Retry/timeout và duplicate | Tính an toàn của những write không idempotent |
| Command-level memory/CPU | Script hoặc keyspace command có làm nghẽn node? |

Không dùng một benchmark với 100 key nhỏ và một thread để kết luận toàn bộ ứng dụng production đã sẵn sàng; workload, giá trị lớn, số lượng node và tỷ lệ read/write phải gần với thực tế.

## 23. Mẫu bảng rà soát và quyết định migration

Trước triển khai, có thể điền bảng cho từng thao tác nghiệp vụ:

| Chức năng | Lệnh hiện tại | Key liên quan | Slot | Rủi ro | Quyết định |
|---|---|---|---|---|---|
| Đọc giỏ hàng | `MGET` | `cart:{id}:items`, `cart:{id}:total` | Cùng tag | Thấp nếu serializer phù hợp | Giữ `MGET`, test Cluster |
| Xem hai người dùng | `MGET` | `user:42`, `user:99` | Có thể khác | `CROSSSLOT` | Tách read hoặc redesign |
| Cập nhật order và metric tổng | `MULTI/EXEC` | `order:{id}:*`, `metrics:global` | Khác | Mất atomicity | Workflow/event khác |
| Cập nhật limit | Lua | `cart:{id}:used`, `cart:{id}:limit` | Cùng tag | Script/driver | Giữ Lua, test EVALSHA |
| Xử lý inventory nhiều SKU | Lua | `stock:{sku1}`, `stock:{sku2}` | Khác | Không thể atomic trên nhiều slot | Đổi mô hình reservation |
| Warm-up cache | Pipeline `SET` | Hàng nghìn product IDs | Nhiều slot | Driver routing, batch error | Test và chia batch |
| Xóa toàn cache | `Cache.clear()` | Prefix trên cả cluster | Nhiều slot | Scan/clear bất toàn | Dùng writer phù hợp, kiểm tra |
| Tìm entity theo index | Redis Repository | Entity + index keys | Không rõ | Framework-generated commands | Kiểm tra hỗ trợ cụ thể |
| Đọc nhiều stream | `XREAD` nhiều key | `stream:A`, `stream:B` | Khác | `CROSSSLOT` | Nhiều reader độc lập |

Bảng giúp phân biệt các thay đổi:

- **Giữ nguyên** khi một key hoặc tất cả key cần thiết đã cùng slot và driver hỗ trợ.
- **Chỉ đổi key naming** khi co-location có ý nghĩa về aggregate và không tạo hotspot.
- **Đổi API hoặc chia thao tác** khi chấp nhận mất snapshot/atomicity.
- **Đổi kiến trúc nghiệp vụ** khi invariant trải nhiều shard và không thể tách an toàn.
- **Chặn migration** nếu chưa có cách giải quyết lỗi cross-slot hoặc độ tin cậy quan trọng.

## 24. Những giả định nguy hiểm cần loại bỏ

**“Chỉ cần sửa `spring.data.redis.cluster.nodes` là toàn bộ code chạy như cũ.”** Sai. Multi-key, transaction, Lua và pipeline đều có thể thay đổi khả năng thực thi.

**“Mọi lệnh có chữ `multi` đều không hỗ trợ Cluster.”** Không đúng tuyệt đối. Nhiều lệnh hỗ trợ khi các key cùng slot; một số client cũng có API fan-out riêng. Cần kiểm tra từng trường hợp.

**“Các key có cùng prefix tự động cùng slot.”** Sai. Chỉ hash tag đúng cách mới bảo đảm co-location theo quy tắc băm.

**“Thêm `{ALL}` vào mọi key là cách chuẩn.”** Sai. Nó tạo một hot slot và làm mất tác dụng phân phối tải.

**“`redis-cli -c` tự sửa `CROSSSLOT`.”** Sai. `-c` xử lý redirect, không biến lệnh đa slot thành nguyên tử.

**“Pipeline trên nhiều slot tương đương `MGET` nhiều slot.”** Sai. Pipeline là nhiều command độc lập, còn `MGET` là một command có ràng buộc slot.

**“Pipeline làm nhiều `SET` cùng thành công hoặc rollback.”** Sai. Pipeline không có all-or-nothing.

**“Script Lua có thể gọi key trên các primary khác bằng `redis.call`.”** Sai. Script chạy ở một node và phải tuân thủ key/slot restrictions.

**“Script chỉ truy cập key được ghép từ `ARGV` vẫn được Cluster route đúng.”** Không được dựa vào điều đó. Redis yêu cầu key được khai báo phù hợp; key tự tạo động có thể phá ranh giới slot và key-access contract.

**“`EVALSHA` đã nạp ở Node A thì Node B chắc chắn có sẵn.”** Không được bảo đảm như vậy. Phải có fallback/triển khai script phù hợp.

**“`MOVED` là lỗi dữ liệu.”** Không nhất thiết; đó có thể là redirect hợp lệ sau thay đổi slot ownership.

**“Một lần `SCAN` trên một node đã duyệt hết cluster.”** Sai nếu không có lớp fan-out cluster-aware rõ ràng.

**“Redis Repository `save` chắc chắn là một command và không có secondary index.”** Sai. Mapping/index có thể tạo thêm key và lệnh.

**“Bật `@Transactional` sẽ tạo transaction xuyên tất cả primary.”** Sai. Spring transaction không tự biến Redis Cluster thành distributed transaction.

**“Dùng Lettuce reactive làm mất giới hạn slot.”** Sai. Reactive thay đổi API/client execution model, không thay đổi server semantics.

**“Một test Redis standalone xanh chứng minh Cluster-ready.”** Sai. Phải có integration test với Cluster thật.

## 25. Tiêu chí chấp nhận trước khi chuyển traffic

Một checklist cho bước quyết định triển khai:

### 25.1. Tương thích lệnh

- [ ] Đã kiểm kê các lệnh Redis từ service, thư viện, cache manager, repository và worker.
- [ ] Các lệnh nhiều key đã được phân loại cùng slot/khác slot.
- [ ] Không có code phụ thuộc `SELECT` database khác `0`.
- [ ] Các lệnh quét keyspace và quản trị có phạm vi Cluster phù hợp.
- [ ] Những chỗ từng dùng command nhiều key đã có integration test trên Cluster.

### 25.2. Pipeline và script

- [ ] Đã xác định Spring Data Redis và Lettuce/Jedis version thực tế.
- [ ] Pipeline cùng slot và nhiều slot được thử nghiệm theo khả năng driver.
- [ ] Đã xử lý thứ tự phản hồi, lỗi từng phần và retry không idempotent.
- [ ] Mọi Lua script khai báo key rõ trong `KEYS` và tuân thủ cùng slot.
- [ ] Không có script quét hoặc tự tạo tên key ở slot khác.
- [ ] `EVALSHA`/`NOSCRIPT` được thử sau failover/reshard.
- [ ] Các script có giới hạn thời gian và khối lượng công việc.

### 25.3. Key schema và tính nhất quán

- [ ] Hash tag chỉ dùng cho aggregate thật sự cần co-location.
- [ ] Không có tag chung khiến phần lớn dữ liệu dồn về một slot.
- [ ] Serializer key/value được kiểm tra và version hóa khi cần.
- [ ] Những invariant cross-shard đã có mô hình thay thế.
- [ ] Các thao tác không còn nguyên tử sau khi tách lệnh được ghi nhận rõ trong thiết kế.

### 25.4. Vận hành và phục hồi

- [ ] Cluster đủ slot coverage và node được quảng bá có thể truy cập từ app.
- [ ] Client xử lý `MOVED`, `ASK`, reconnect, topology refresh theo config đúng.
- [ ] Test resharding/failover dưới tải đã được thực hiện.
- [ ] Log/metric phân biệt `CROSSSLOT` với timeout/redirect.
- [ ] Các write không idempotent có chiến lược unknown outcome.
- [ ] Có kế hoạch rollback migration và đối chiếu dữ liệu trước/sau.

**Không đánh dấu “đã sẵn sàng” chỉ vì ứng dụng kết nối được và `PING` trả `PONG`.** Điều cần chứng minh là **luồng nghiệp vụ thực sự đọc/ghi đúng trong điều kiện phân phối slot và biến động topology**.

## 26. Quy trình migration gợi ý theo giai đoạn

### Giai đoạn 1 – Kiểm kê và phân loại

Liệt kê mọi Redis command và key pattern, kể cả các lệnh do framework tạo ra. Chạy phân tích slot trên key mẫu và phân nhóm rủi ro.

### Giai đoạn 2 – Chuẩn hóa key schema

Xác định hash tag cho những aggregate cần co-location. Không sửa toàn bộ key vô điều kiện. Ghi rõ version namespace và cách chuyển dữ liệu từ key cũ.

### Giai đoạn 3 – Thay đổi những phần không tương thích

- Multi-key cross-slot: tách lệnh nếu nghiệp vụ cho phép, hoặc thiết kế lại dữ liệu.
- Lua truy cập key động/cross-slot: đổi script và cách cung cấp key.
- Pipeline: thay đổi chiến lược routing/batching nếu driver yêu cầu.
- Cache clear/index/SCAN: dùng cơ chế cluster-aware phù hợp.
- Transaction cross-slot: chuyển sang workflow có idempotency/compensation hoặc storage phù hợp.

### Giai đoạn 4 – Kiểm thử trên Redis Cluster thật

Triển khai lab/staging có nhiều primary và replica, chạy integration tests, benchmark và phép thử resharding/failover. Quan sát kết quả cuối tại Redis, không chỉ response từ Java.

### Giai đoạn 5 – Chuyển dữ liệu và traffic

Thiết kế cách copy/migrate key, kiểm tra dữ liệu sau chuyển, xác định cửa sổ cutover và chính sách với những write đang bay. Việc dual-write vào standalone và Cluster có thể phát sinh xung đột hoặc thứ tự khác nhau; không dùng dual-write như cam kết đồng bộ nguyên tử giữa hai hệ thống.

Chỉ chuyển traffic theo quy trình có thể kiểm soát, kèm metric và khả năng rollback. Không xóa hệ thống cũ trước khi đối chiếu kết quả và có quyết định vận hành.

### Giai đoạn 6 – Theo dõi hậu migration

Theo dõi `CROSSSLOT`, redirect, timeout, replica lag, hot slots, latency và sai khác dữ liệu. Những vấn đề này có thể chỉ xuất hiện khi feature ít dùng chạy, data volume tăng hoặc Cluster bắt đầu reshard.

## 27. Tổng kết

Trước khi chuyển Spring Data Redis sang Redis Cluster, cần kiểm tra **khả năng thực thi và ý nghĩa nghiệp vụ** của lệnh, pipeline và script, không chỉ thử kết nối.

Những nguyên tắc quan trọng nhất:

1. **Redis Cluster phân vùng key theo 16.384 hash slot.** Một lệnh nhiều key hoặc một script/transaction cần co-location thường phải dùng những key cùng slot.
2. **Hash tag `{...}`** giúp đặt một nhóm key cùng slot, nhưng phải chọn theo aggregate; dùng tag quá rộng tạo hot slot.
3. **Lệnh một key** thường dễ chuyển nhất khi client cluster-aware; những lệnh như `MGET`, `MSET`, unions, multi-stream read và transaction cần kiểm tra slot cụ thể.
4. **Pipeline là tối ưu truyền lệnh**, không phải transaction. Hỗ trợ pipeline xuyên node phụ thuộc driver/version và phải thử dưới redirect/failover.
5. **Lua script chạy trên một node**, phải dùng key được khai báo trong `KEYS` với slot phù hợp; không tự tạo key dynamic để truy cập các shard khác.
6. **`EVALSHA`/script cache không được mặc định có trên mọi node**; phải có phương án `NOSCRIPT` và routing thích hợp khi topology thay đổi.
7. **Spring Cache, Redis Repository và keyspace jobs** cũng cần audit vì có thể phát sinh multi-key operations hoặc quét dữ liệu theo phạm vi node.
8. **Thử nghiệm trên Cluster thật** cần bao gồm same-slot/cross-slot, resharding, failover, timeout và retry/idempotency.
9. **Không đánh đổi atomicity mà không nhận ra.** Việc tách một lệnh nhiều key thành nhiều lệnh đơn có thể giúp chạy được trên Cluster nhưng làm thay đổi bảo đảm nhất quán.

Một bản migration được coi là an toàn khi mỗi luồng nghiệp vụ đã có **key schema, tập lệnh, chiến lược concurrency, đường xử lý lỗi và bằng chứng kiểm thử** phù hợp với ranh giới slot. Khi những yếu tố đó rõ ràng, Redis Cluster mới thực sự cung cấp khả năng mở rộng mà không làm mất các bảo đảm cần thiết của ứng dụng.
