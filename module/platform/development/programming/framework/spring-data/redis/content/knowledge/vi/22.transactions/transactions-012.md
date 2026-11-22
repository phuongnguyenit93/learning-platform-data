# Giới hạn giao dịch nhiều khóa trên Redis Cluster trong Spring Data Redis

## 1. Bài toán: vì sao giao dịch chạy trên Redis đơn lẻ có thể thất bại khi chuyển sang Cluster?

Trong ứng dụng Spring Data Redis, một thao tác nghiệp vụ thường cần thay đổi nhiều key: cập nhật trạng thái đơn hàng, lưu bản ghi thanh toán, điều chỉnh số lượng tồn kho hoặc chuyển tiền giữa hai tài khoản. Với Redis chạy một máy chủ, các lệnh có thể được xếp trong giao dịch `MULTI`/`EXEC` để thực thi liên tiếp trên cùng máy chủ.

Khi triển khai **Redis Cluster**, key được phân phối vào nhiều **hash slot** và các slot có thể nằm trên nhiều node. Do đó, một giao dịch gồm nhiều key không thể mặc nhiên thực thi trên nhiều node như một giao dịch cơ sở dữ liệu phân tán.

Quy tắc nền tảng cần nhớ:

> **Giao dịch nhiều key trên Redis Cluster phải được thực thi trong phạm vi một hash slot** và cần được driver/Redis client hỗ trợ đúng cách. Redis Cluster không cung cấp giao dịch ACID phân tán trên nhiều slot hoặc nhiều primary node.

Điều đó không có nghĩa Redis Cluster hoàn toàn không hỗ trợ giao dịch. Các thao tác nhiều key cùng slot vẫn có thể sử dụng `MULTI`/`EXEC`, `WATCH`, Lua script hoặc Redis Function trong những giới hạn tương ứng. Vấn đề bắt đầu khi nghiệp vụ cần cập nhật **nhiều key ở các slot khác nhau**.

Sau bài học, bạn có thể:

- Giải thích key, hash slot, primary node và cơ chế xác định slot.
- Phân biệt **cùng node** với **cùng slot**.
- Nhận biết nguyên nhân lỗi `CROSSSLOT`, `MOVED`, `ASK`, `TRYAGAIN`.
- Thiết kế tên key sử dụng **hash tag** để colocate dữ liệu cần giao dịch.
- Dùng `SessionCallback` của Spring Data Redis cho thao tác transaction trong một slot.
- Hiểu giới hạn của `@Transactional`, `WATCH`, pipeline và Lua trong Redis Cluster.
- Chọn phương án nghiệp vụ khi không thể đặt các key cùng một slot.
- Đánh giá trade-off về phân phối tải, hot slot, durability và nhất quán.

## 2. Redis Cluster phân phối key như thế nào?

Redis Cluster có **16.384 hash slot**, đánh số từ `0` đến `16383`. Một primary node sở hữu một tập slot nhất định. Redis sử dụng hash slot để xác định node chịu trách nhiệm cho một key.

Với key bình thường, phép tính cơ bản là:

```text
slot = CRC16(key) mod 16384
```

Ví dụ mô hình ba primary:

```text
Redis Cluster
│
├── Primary A: slots     0 .. 5460
├── Primary B: slots  5461 .. 10922
└── Primary C: slots 10923 .. 16383

Key order:101:status ──> slot X ──> primary sở hữu slot X
Key order:101:items  ──> slot Y ──> primary sở hữu slot Y
Key user:77:balance  ──> slot Z ──> primary sở hữu slot Z
```

Sơ đồ chỉ minh họa: `X`, `Y`, `Z` phụ thuộc kết quả CRC16 của chuỗi key và không nên đoán dựa trên việc chúng có cùng tiền tố.

Có thể xác định hash slot thật bằng Redis CLI:

```redis
CLUSTER KEYSLOT order:101:status
CLUSTER KEYSLOT order:101:items
CLUSTER KEYSLOT user:77:balance
```

Nếu các kết quả khác nhau thì chúng **không cùng slot**, cho dù hiện tại các slot tình cờ thuộc một primary node.

### 2.1. Vì sao phải kiểm tra slot thay vì kiểm tra node?

Một node có thể sở hữu hàng nghìn slot. Hai key cùng ở một primary **chưa đủ** điều kiện cho các thao tác nhiều key của Redis Cluster. Ràng buộc chủ yếu là **mọi key trong thao tác phải thuộc cùng hash slot**.

| Trường hợp | Cùng primary hiện tại? | Cùng slot? | Dùng giao dịch nhiều key theo quy tắc Cluster? |
|---|---|---|---|
| Hai key khác slot, khác primary | Không | Không | Không |
| Hai key khác slot, cùng primary | Có | Không | Không |
| Hai key cùng slot | Có, tại một thời điểm ổn định | Có | Có thể, tùy command và driver |
| Hai key cùng hash tag hợp lệ | Có cùng slot | Có | Có thể, tùy command và driver |

Khái niệm "có thể" nhắc rằng cùng slot là **điều kiện cần về phân vùng**, chưa đủ để đảm bảo mọi phiên bản Redis, mọi command hoặc mọi client Spring Data đều hỗ trợ giống nhau.

## 3. Hash tag: cách gom các key vào cùng một slot

Redis Cluster có quy tắc đặc biệt cho tên key chứa một phần nằm trong cặp ngoặc nhọn `{...}`.

Ví dụ:

```text
order:{o-101}:status
order:{o-101}:items
order:{o-101}:payment
```

Ba key này có cùng **hash tag** `o-101`. Khi tính slot, Redis sử dụng chuỗi bên trong cặp `{...}` hợp lệ thay vì toàn bộ tên key:

```text
CRC16("o-101") mod 16384
```

Vì vậy, chúng đi vào cùng một hash slot.

Kiểm tra:

```redis
CLUSTER KEYSLOT order:{o-101}:status
CLUSTER KEYSLOT order:{o-101}:items
CLUSTER KEYSLOT order:{o-101}:payment
```

Ba lệnh sẽ trả cùng một số slot. Từ đó có thể thiết kế một nhóm key cần thay đổi chung trong một transaction.

### 3.1. Những ví dụ đúng và sai

| Key thứ nhất | Key thứ hai | Kết luận |
|---|---|---|
| `order:{o-101}:status` | `order:{o-101}:items` | Cùng hash tag, chắc chắn cùng slot |
| `account:{u-77}:balance` | `account:{u-77}:holds` | Cùng slot |
| `order:{o-101}:status` | `order:{o-102}:status` | Hash tag khác, không được bảo đảm cùng slot |
| `order:101:status` | `order:101:items` | Cùng tiền tố nhưng không được bảo đảm cùng slot |
| `tenant:{t-7}:orders` | `tenant:{t-7}:ledger` | Cùng slot trong phạm vi tenant |
| `order:{}:status` | `order:{}:items` | Hash tag rỗng; không có cơ chế gom theo tag rỗng |
| `order:{o-101}:status` | `inventory:{sku-7}:qty` | Tag khác, không được bảo đảm cùng slot |

**Lưu ý về cú pháp:** Redis chỉ sử dụng phần tag khi tìm thấy cặp ngoặc `{` và `}` phù hợp với ít nhất một ký tự ở giữa. Không nên phụ thuộc vào nhiều cặp ngoặc phức tạp hoặc tag rỗng; dùng một định dạng nhất quán, rõ nghĩa cho toàn hệ thống.

### 3.2. Hash tag là lựa chọn phân vùng dữ liệu

Với một đơn hàng, các key liên quan có thể được colocate:

```text
order:{o-101}:state
order:{o-101}:items
order:{o-101}:amount
order:{o-101}:audit-sequence
```

Đây là một **aggregate boundary** tự nhiên: mọi thao tác nguyên tử chỉ cần những key của một đơn hàng. Các đơn hàng khác có tag khác, cho phép Redis Cluster phân bố nhiều đơn hàng vào nhiều slot.

Nhưng nếu mọi key đều có tag `{global}`:

```text
order:{global}:o-101
order:{global}:o-102
order:{global}:o-103
```

thì toàn bộ dữ liệu ấy rơi vào **một slot**, khiến khả năng chia tải bị giảm nghiêm trọng, có nguy cơ tạo hot slot/hot primary. Hash tag giúp giải quyết phạm vi transaction nhưng cũng quyết định cách phân bố tải.

## 4. Giao dịch MULTI/EXEC thực sự bảo đảm điều gì?

Trong Redis, có thể xếp nhiều lệnh vào transaction:

```redis
MULTI
SET order:{o-101}:state PAID
HSET order:{o-101}:metadata paidBy card
EXEC
```

Ở đây, cả hai key chứa tag `o-101`, nên thuộc cùng slot. Redis nhận các lệnh khi `MULTI` đang mở và thực thi chúng theo thứ tự lúc `EXEC` trên node sở hữu slot đó.

### 4.1. Tính chất của MULTI/EXEC

- Các lệnh trong transaction được **xếp hàng** trước `EXEC`.
- Khi `EXEC` chạy trên một node, các lệnh của transaction được thực thi tuần tự mà không xen lệnh từ client khác trong cùng execution.
- `EXEC` trả về danh sách kết quả của các lệnh đã thực thi.
- `DISCARD` hủy transaction còn đang xếp hàng trước khi thực thi.
- `WATCH` cho phép từ chối transaction khi key được theo dõi bị thay đổi trước `EXEC` (optimistic locking).

Nhưng transaction Redis **không có rollback kiểu SQL** cho tất cả lỗi.

Ví dụ:

```redis
SET demo:{x}:counter not-a-number
MULTI
INCR demo:{x}:counter
SET demo:{x}:status touched
EXEC
```

Nếu `INCR` phát sinh lỗi kiểu dữ liệu khi thực thi, lệnh `SET` sau đó vẫn có thể chạy và `EXEC` trả về cả lỗi của `INCR` lẫn kết quả lệnh `SET`. Một lỗi được phát hiện lúc xếp hàng có thể khiến transaction bị hủy theo cơ chế khác, nhưng không nên giả định "một lệnh lỗi thì mọi lệnh đã chạy được rollback".

### 4.2. Phạm vi atomicity

```text
                         Redis Cluster
Transaction trên slot S ─────────────────> Primary sở hữu slot S
  MULTI
    SET K1 ...
    SET K2 ...
  EXEC
        │
        └─ Không bị lệnh khác xen giữa trong thời gian thực thi EXEC

Transaction trên slot A + slot B
        │
        └─ Không có MULTI/EXEC phân tán do Redis Cluster cung cấp
```

Atomicity trong lúc thực thi không đồng nghĩa dữ liệu chắc chắn bền vững qua mọi sự cố. Redis replication có thể bất đồng bộ, và mức durability phụ thuộc cấu hình persistence, replication và failover. Sau sự cố node hoặc failover, cần phân tích điều kiện lưu trữ riêng, nhất là với dữ liệu tài chính hoặc nghiệp vụ có yêu cầu bền vững mạnh.

## 5. Vì sao transaction nhiều slot thất bại?

Giả sử muốn thay đổi:

```text
account:{u-11}:balance
account:{u-22}:balance
```

Hai key có tag khác nhau. Chúng thường nằm ở các slot khác nhau. Nếu cố đưa hai lệnh vào cùng một transaction Redis Cluster, không có primary nào quản lý cả hai slot như một transaction duy nhất.

Ví dụ không hợp lệ về mặt thiết kế:

```redis
MULTI
DECRBY account:{u-11}:balance 100
INCRBY account:{u-22}:balance 100
EXEC
```

Redis Cluster không cam kết thực hiện cặp thay đổi này như một giao dịch nguyên tử. Tùy client, node được chọn và bước gửi lệnh, thao tác có thể báo lỗi định tuyến hoặc từ chối giao dịch; không nên xem đây là một cách chuyển tiền an toàn.

Lỗi thường thấy ở các lệnh nhiều key không cùng slot:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

Ví dụ:

```redis
MGET account:{u-11}:balance account:{u-22}:balance
```

Lỗi có thể xảy ra ngay cả khi **không có `MULTI`**. Ràng buộc cùng slot áp dụng cho nhiều command có nhiều key (ví dụ `MGET`, `MSET`, một số thao tác Set, `RENAME`, script nhiều key), chứ không chỉ transaction.

### 5.1. `CROSSSLOT` và `MOVED` là hai vấn đề khác nhau

| Dấu hiệu | Ý nghĩa chính | Hướng điều tra |
|---|---|---|
| `CROSSSLOT` | Một thao tác có nhiều key thuộc những slot khác nhau | Kiểm tra tất cả key bằng `CLUSTER KEYSLOT`; xem lại hash tag |
| `MOVED <slot> <host>:<port>` | Node nhận lệnh không sở hữu slot đích | Kiểm tra cluster topology và khả năng redirect của client |
| `ASK <slot> <host>:<port>` | Chuyển hướng tạm trong quá trình di chuyển slot | Client phải hỗ trợ quy trình `ASKING`/redirect |
| `TRYAGAIN` | Cluster chưa xử lý được thao tác trong trạng thái chuyển slot hoặc tạm thời khác | Xem trạng thái resharding, cân nhắc retry an toàn |
| `CLUSTERDOWN` | Cluster không thể phục vụ yêu cầu theo trạng thái và cấu hình hiện tại | Kiểm tra cluster health, slot coverage, quorum |

Một cluster-aware client như Lettuce/Jedis có thể xử lý nhiều trường hợp `MOVED` hoặc `ASK` cho lệnh bình thường. **Redirect không biến một thao tác xuyên slot thành transaction phân tán**. Vì vậy, retry một lệnh bị `CROSSSLOT` mà không đổi mô hình key sẽ không giải quyết gốc vấn đề.

### 5.2. Resharding và failover

Cùng hash tag bảo đảm các key tính ra cùng slot, nhưng cluster có thể **di chuyển slot giữa các node** hoặc thay primary sau failover. Trong thời gian chuyển slot, những thao tác nhiều key có thể cần retry hoặc tạm thời thất bại tùy trạng thái di chuyển và hỗ trợ của client.

Với các thao tác có side effect, không retry vô điều kiện: nếu mất kết nối sau khi gửi lệnh mà chưa nhận phản hồi, không thể tự suy luận rằng thao tác chưa được thực thi. Sử dụng idempotency key hoặc cơ chế kiểm tra kết quả khi nghiệp vụ có nguy cơ thực hiện trùng.

## 6. Thực hành Redis CLI: giao dịch cùng slot

Giả sử đơn hàng `o-101` có key trạng thái và key đánh dấu giao nhận. Trước tiên kiểm tra:

```redis
CLUSTER KEYSLOT order:{o-101}:state
CLUSTER KEYSLOT order:{o-101}:shipment
```

Hai kết quả giống nhau. Trên kết nối tới node có thể phục vụ slot đó:

```redis
MULTI
SET order:{o-101}:state PAID
SET order:{o-101}:shipment READY
EXEC
```

Sau `EXEC`, có thể đọc:

```redis
MGET order:{o-101}:state order:{o-101}:shipment
```

Cũng nhờ cùng slot, `MGET` là một yêu cầu nhiều key phù hợp với ràng buộc Redis Cluster.

Ngược lại, hai key:

```redis
CLUSTER KEYSLOT order:{o-101}:state
CLUSTER KEYSLOT inventory:{sku-44}:available
```

có hash tag khác nhau nên **không được bảo đảm cùng slot**. Đừng thay thế mù quáng hai key đó vào transaction và kỳ vọng client tự tổ chức hai primary tham gia như một hệ thống 2-phase commit.

**Chú ý khi dùng `redis-cli -c`:** chế độ `-c` hỗ trợ các redirect Cluster cho những lệnh phù hợp. Nó không cung cấp distributed transaction và không giải quyết `CROSSSLOT`.

## 7. Spring Data Redis: làm transaction trên cùng kết nối

Spring Data Redis cung cấp `RedisTemplate`/`StringRedisTemplate` và `SessionCallback` để gắn nhiều thao tác vào một phiên sử dụng connection.

Với Redis Cluster, trước khi viết code transaction cần giải quyết **hai điều kiện độc lập**:

1. **Dữ liệu:** mọi Redis key cần dùng trong transaction thuộc **cùng hash slot**.
2. **Client:** phiên bản Spring Data Redis và connector đang dùng phải hỗ trợ transaction ở chế độ Cluster, sử dụng connection/route phù hợp. Có những API giao dịch được hỗ trợ khác nhau tùy driver và phiên bản.

Không nên giả định cứ gọi `multi()` và `exec()` trên một template thì Redis Cluster sẽ làm transaction xuyên slot.

### 7.1. Ví dụ `SessionCallback` cho hai key cùng slot

Ví dụ Spring Boot có `spring-boot-starter-data-redis`, dùng `StringRedisTemplate`:

```java
import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStatusService {

    private final StringRedisTemplate redis;

    public OrderStatusService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> markPaid(String orderId, String receiptId) {
        String tag = "{" + orderId + "}";
        String stateKey = "order:" + tag + ":state";
        String receiptKey = "order:" + tag + ":receipt";

        return redis.execute(new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings("unchecked")
            public <K, V> List<Object> execute(
                    RedisOperations<K, V> operations)
                    throws DataAccessException {

                operations.multi();
                operations.opsForValue()
                    .set((K) stateKey, (V) "PAID");
                operations.opsForValue()
                    .set((K) receiptKey, (V) receiptId);
                return operations.exec();
            }
        });
    }
}
```

Ví dụ dùng `StringRedisTemplate` nên các key và value thực tế đều là String; ép kiểu generic bên trong `SessionCallback` được dùng cho minh họa API. Khi phát triển thật, hãy bảo đảm tên key, serializer, validation của `orderId`, chính sách retry và driver nhất quán.

**Về tên tag:** không nhận trực tiếp một `orderId` tùy ý từ bên ngoài rồi nối vào `{...}` mà không kiểm soát. ID chứa dấu `}` hoặc `{` có thể làm Redis hiểu hash tag khác kỳ vọng. Nên xác thực hoặc mã hóa ID thành một thành phần tag an toàn, ổn định.

**Về kết quả:** `multi()` đưa connection vào chế độ transaction, các lệnh write được xếp hàng và `exec()` trả danh sách kết quả. Mã nghiệp vụ phải kiểm tra việc gọi có thành công và xử lý lỗi khi driver không hỗ trợ, cluster chuyển slot hoặc đường truyền gặp sự cố.

### 7.2. Vì sao dùng `SessionCallback`?

Nếu những lệnh có liên quan được gửi qua nhiều connection không được ghim chung, `MULTI`/`EXEC` có thể không áp dụng lên cùng phiên Redis. `SessionCallback` là cơ chế Spring Data Redis dùng để nhóm thao tác trên cùng connection/session theo contract của API.

Tuy vậy, **connection được ghim chung không tự làm các key khác slot trở thành hợp lệ**. Cluster vẫn áp dụng quy tắc hash slot.

### 7.3. `@Transactional` không tự tạo giao dịch phân tán

Một ngộ nhận thường gặp:

```java
@Transactional
public void transfer() {
    redis.opsForValue().decrement("account:{a}:balance");
    redis.opsForValue().increment("account:{b}:balance");
}
```

Đặt `@Transactional` **không biến Redis Cluster thành hệ thống giao dịch nhiều primary**. Trong Spring Data Redis, việc tham gia Spring-managed transaction của `RedisTemplate` cần được cấu hình phù hợp; transaction support của template không mặc nhiên được bật trong mọi ứng dụng.

Ví dụ cấu hình bật Redis transaction support cho template phải được thiết kế cùng transaction manager/context đang dùng:

```java
stringRedisTemplate.setEnableTransactionSupport(true);
```

Dòng lệnh này chỉ nói lên việc cho phép tham gia cơ chế giao dịch Spring ở cấp template, **không dỡ bỏ giới hạn cùng slot**. Ngoài ra, Spring Data Redis có các quy tắc riêng đối với read trong transaction (một số read được phục vụ qua connection ngoài transaction); việc kết hợp với giao dịch SQL và thời điểm commit cần được hiểu rõ.

Nếu một method vừa cập nhật cơ sở dữ liệu quan hệ vừa ghi Redis, `@Transactional` của database thông thường **không bảo đảm distributed atomic commit** của cả SQL và Redis. Với nghiệp vụ cần tính nhất quán giữa hệ thống, cần mô hình như outbox, event-driven workflow hoặc quy trình bù phù hợp.

## 8. WATCH: kiểm tra điều kiện trước khi ghi

`MULTI`/`EXEC` tự nó không giải quyết bài toán “đọc giá trị hiện tại rồi quyết định ghi” trong môi trường concurrent. Redis có `WATCH` để tạo **optimistic locking**.

Ví dụ cần trừ số lượng tồn kho chỉ khi còn đủ:

```text
WATCH inventory:{sku-44}:available
GET inventory:{sku-44}:available
  Nếu current < requested:
      UNWATCH và trả lỗi nghiệp vụ
  Nếu đủ:
      MULTI
      DECRBY inventory:{sku-44}:available requested
      EXEC
```

Nếu key được watch thay đổi trước `EXEC`, Redis có thể hủy transaction để client retry dựa trên trạng thái mới.

Với nhiều key:

```redis
WATCH order:{o-101}:state order:{o-101}:version
```

Cả hai cùng tag `o-101`, phù hợp với phạm vi hash slot. Nhưng `WATCH` trên các key xuyên slot **không trở thành optimistic lock phân tán trên nhiều primary**.

Một luồng xử lý tốt cần:

- Đọc các giá trị **trước `MULTI`**, sau `WATCH`, để ra quyết định.
- Thực hiện `MULTI` và `EXEC` trên cùng connection phù hợp.
- Phân biệt `EXEC` thành công, bị hủy do tranh chấp, và lỗi kết nối.
- Giới hạn số lần retry, tránh vòng lặp vô hạn khi có contention cao.
- Bảo đảm tất cả key giao dịch cùng slot.

Các thao tác đọc sau `MULTI` cũng được xếp hàng theo cơ chế Redis; vì thế không thể xử lý kết quả `GET` như thể nó đã trả về giá trị mới trước `EXEC`.

## 9. Lua script và Redis Function cũng chịu giới hạn slot

Lua thường được dùng để gộp một nhóm thao tác và kiểm tra điều kiện vào một lần thực thi trên Redis. Tuy nhiên, Redis Cluster vẫn cần biết những key mà script thao tác và áp dụng ràng buộc cùng slot.

Ví dụ Lua atomically chuyển một phần số lượng từ kho chờ sang kho đã giữ **trong cùng một đơn hàng**:

```lua
-- KEYS[1] = stock:{o-101}:available
-- KEYS[2] = stock:{o-101}:reserved
-- ARGV[1] = số lượng muốn giữ

local requested = tonumber(ARGV[1])
if requested == nil or requested <= 0 then
    return redis.error_reply("invalid amount")
end

local available = tonumber(redis.call("GET", KEYS[1]) or "0")
if available < requested then
    return 0
end

redis.call("DECRBY", KEYS[1], requested)
redis.call("INCRBY", KEYS[2], requested)
return 1
```

Hai key đều mang tag `{o-101}` nên nằm cùng slot. Kết quả `1` là đặt giữ hàng thành công; `0` là không đủ số lượng.

Gọi từ Spring Data Redis bằng `RedisScript`:

```java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

String scriptText = """
    local n = tonumber(ARGV[1])
    if n == nil or n <= 0 then
        return redis.error_reply("invalid amount")
    end
    local available = tonumber(redis.call("GET", KEYS[1]) or "0")
    if available < n then return 0 end
    redis.call("DECRBY", KEYS[1], n)
    redis.call("INCRBY", KEYS[2], n)
    return 1
    """;

DefaultRedisScript<Long> script = new DefaultRedisScript<>();
script.setScriptText(scriptText);
script.setResultType(Long.class);

Long result = stringRedisTemplate.execute(
    script,
    List.of("stock:{o-101}:available", "stock:{o-101}:reserved"),
    "3"
);
```

Ví dụ dùng Java text block (Java 15 trở lên) và một `StringRedisTemplate` được cấu hình kết nối Redis. Với Spring Boot/JDK cũ hơn, có thể lưu script trong resource hoặc chuỗi Java thông thường.

**Script không giải quyết giao dịch xuyên slot.** Không nên tạo key Redis tùy ý bên trong script dựa trên nội dung `ARGV` mà không khai báo chúng trong danh sách key phù hợp; trên Cluster, các key mà script sử dụng cần được khai báo và đặt ở cùng slot theo quy tắc Redis. Redis Function cũng có phạm vi thực thi tại node/slot và không cung cấp distributed atomic transaction cho nhiều shard.

Lua thích hợp khi cần kiểm tra và ghi một nhóm key cùng slot trong một bước nguyên tử. Với thao tác kéo dài hoặc quét nhiều dữ liệu, script có thể chặn server trong thời gian thực thi, nên cần giữ script ngắn và có giới hạn.

## 10. Pipeline, multi-key API và transaction: đừng nhầm lẫn

| Cơ chế | Mục đích chính | Nguyên tử với nhiều lệnh? | Vượt qua giới hạn slot? |
|---|---|---|---|
| `MULTI`/`EXEC` | Gom các lệnh transaction | Có phạm vi atomic execution trên node theo ngữ nghĩa Redis | Không |
| `WATCH` + `MULTI`/`EXEC` | Optimistic concurrency control | Có, nếu điều kiện watch và transaction hợp lệ | Không |
| Lua / Redis Function | Kiểm tra và cập nhật trong một lần thực thi | Có trong phạm vi thực thi hợp lệ | Không |
| Pipeline | Giảm round-trip bằng cách gửi nhiều lệnh | **Không** | Có thể gửi lệnh độc lập tới nhiều node tùy client, nhưng không nguyên tử |
| Hai lệnh Redis độc lập | Thao tác tuần tự | Không có transaction chung | Có thể truy cập các slot khác nhau, không nguyên tử |
| Saga/workflow bù | Điều phối nghiệp vụ nhiều bước | Không phải atomic Redis transaction; đạt nhất quán theo thiết kế | Có thể xử lý xuyên slot/nhiều hệ thống |

Ví dụ pipeline có thể gửi:

```text
SET account:{a}:status READY  --> slot A
SET account:{b}:status READY  --> slot B
```

Client có thể route từng lệnh tới node tương ứng. Nhưng một lệnh thành công và lệnh kia thất bại vẫn là tình huống phải xử lý. Pipeline **tăng hiệu suất truyền lệnh**, không thay thế transaction.

Tương tự, `RedisTemplate.opsForValue().multiGet(keys)` hoặc `multiSet(map)` có thể gặp giới hạn multi-key cùng slot trên Cluster. Những API Java có chữ *multi* không đồng nghĩa là distributed transaction; cần kiểm tra key slot và support của driver.

## 11. Một bài toán khó: chuyển tiền giữa hai tài khoản

Ứng dụng lưu:

```text
account:{a-101}:balance  = 1000
account:{a-202}:balance  = 200
```

Nghiệp vụ cần chuyển 150 từ tài khoản A sang B, với yêu cầu:

1. Không trừ nếu tài khoản A không đủ tiền.
2. Khi chuyển thành công, cả hai số dư phản ánh đúng giao dịch.
3. Không cộng/trừ hai lần khi request bị retry.
4. Có thể khôi phục sau crash hoặc timeout.

Hai key có tag khác nhau, nên không được bảo đảm cùng slot. Viết:

```redis
MULTI
DECRBY account:{a-101}:balance 150
INCRBY account:{a-202}:balance 150
EXEC
```

không cung cấp một transaction xuyên hai slot. Đổi sang pipeline cũng không giải quyết rủi ro một bên thành công, bên kia thất bại.

### 11.1. Phương án A: đặt cả hai key vào cùng slot khi quy mô cho phép

Nếu nghiệp vụ có ranh giới tự nhiên là **một ví nội bộ của cùng tài khoản doanh nghiệp**, có thể thiết kế:

```text
wallet:{wallet-77}:source-balance
wallet:{wallet-77}:target-balance
wallet:{wallet-77}:transfer-ledger
```

Các key cùng tag `{wallet-77}` nên có thể cập nhật nguyên tử với script/transaction hợp lệ. Nhưng nếu ép **tất cả** tài khoản vào một tag, Cluster mất khả năng phân tán tải cho tập key đó.

Phương án này phù hợp khi mọi dữ liệu cần giao dịch thực sự thuộc **một aggregate** có quy mô và lưu lượng đủ nhỏ.

### 11.2. Phương án B: mô hình nhiều bước có trạng thái

Nếu hai tài khoản phải ở các slot riêng:

```text
1. Ghi nhận transferId duy nhất, trạng thái INITIATED.
2. Ghi một bước giữ/trừ phía nguồn theo transaction/script cục bộ.
3. Ghi nhận trạng thái SOURCE_RESERVED hoặc SOURCE_DEBITED.
4. Thực hiện bước cộng vào đích theo transaction/script cục bộ.
5. Đánh dấu COMPLETED.
6. Nếu lỗi, retry an toàn hoặc thực hiện bù theo quy tắc nghiệp vụ.
```

Đây là hướng **saga/workflow** chứ không phải một giao dịch nguyên tử xuyên slot. Các bước cần lưu trạng thái bền vững phù hợp; không được chỉ tin vào tiến trình Java còn sống.

Mỗi bước nên có **idempotency key** (`transferId`) để thực hiện lại không nhân đôi hiệu ứng. Cần quy định khi nào hoàn tiền, xử lý timeout thế nào, và trạng thái nào có thể được nhìn thấy trong quá trình chuyển.

### 11.3. Phương án C: dùng nguồn dữ liệu giao dịch phù hợp

Nếu hệ thống yêu cầu chuyển tiền thực sự nguyên tử qua nhiều tài khoản, có ràng buộc kế toán và kiểm toán mạnh, hãy cân nhắc giữ sổ cái giao dịch trong một hệ thống lưu trữ hỗ trợ transaction mong muốn, sau đó cập nhật Redis như một read model hoặc cache. Redis Cluster vẫn có thể phục vụ truy xuất nhanh mà không phải chịu trách nhiệm cho atomic commit xuyên shard.

Đây là lựa chọn kiến trúc dựa trên **yêu cầu nhất quán**, không phải sự thiếu sót của Spring Data Redis.

## 12. Thiết kế ranh giới transaction theo aggregate

Một cách tránh giao dịch xuyên slot là thiết kế **aggregate** sao cho những bất biến phải giữ cùng lúc nằm trong một slot.

Ví dụ đơn hàng:

```text
order:{o-101}:state
order:{o-101}:items
order:{o-101}:reserved-amount
order:{o-101}:version
```

Các bất biến như “đơn đã thanh toán thì có mã xác nhận” có thể được cập nhật trong một transaction/script cùng slot.

Ngược lại:

```text
order:{o-101}:state
inventory:{sku-44}:stock
customer:{u-77}:points
```

là ba aggregate khác nhau. Một checkout thay đổi cả ba thường cần xử lý qua các bước nghiệp vụ có trạng thái và cơ chế bù, hoặc dùng nơi lưu trữ có khả năng transaction phù hợp.

### 12.1. Chọn phạm vi hash tag

| Phạm vi tag | Ví dụ | Ưu điểm | Rủi ro |
|---|---|---|---|
| Theo entity | `order:{o-101}:*` | Gom thao tác trong một đơn, phân tán đơn hàng | Không nguyên tử với entity khác |
| Theo tài khoản | `account:{a-101}:*` | Dễ giữ bất biến cục bộ của account | Chuyển giữa accounts xuyên slot |
| Theo tenant | `tenant:{t-7}:*` | Dễ transaction trong tenant | Tenant lớn tạo hot slot và dữ liệu dồn một node |
| Tag toàn cục | `{global}:*` | Nhiều key cùng slot | Mất phần lớn lợi ích sharding |
| Không có tag | `order:101:state` và `order:101:items` | Phân tán tự nhiên theo toàn tên key | Không đảm bảo hai key liên quan cùng slot |

Khi chọn tag, cần đánh giá số key, byte dữ liệu, QPS đọc/ghi, hotspot và khả năng mở rộng. Hash slot là đơn vị di chuyển giữa các primary; không thể chia đôi một slot đang quá nóng chỉ bằng cách thêm node.

## 13. Redis Repository có thể tạo thêm key ngoài ý định

Spring Data Redis Repository không chỉ ghi Hash của entity. Với `@RedisHash`, `@Indexed`, TTL và một số tính năng mapping, Repository còn có thể dùng:

- Hash chính của đối tượng.
- Set quản lý ID trong keyspace.
- Secondary index Set theo giá trị.
- Metadata giúp dọn chỉ mục.
- Key hoặc bản sao hỗ trợ expiration, tùy cấu hình.

Ví dụ:

```java
@RedisHash("orders")
public class Order {
    @Id private String id;
    @Indexed private String status;
}
```

Giả sử Redis key chính được quy ước dạng `orders:<id>`. Các key index thường dựa trên **tên thuộc tính và giá trị**, nên không thể mặc nhiên kết luận chúng cùng hash slot với key entity.

**Thêm hash tag vào riêng key thực thể không bảo đảm mọi key Repository nội bộ nằm cùng slot.** Đối với các hoạt động có secondary index, TTL hoặc transaction kết hợp nhiều thao tác Repository, cần xem rõ khả năng hỗ trợ Redis Cluster của **phiên bản Spring Data Redis, driver và cấu trúc key do mapping tạo ra**.

Không nên tự kết hợp `repository.save(entityA)`, `repository.save(entityB)` và giả định `@Transactional` khiến tất cả Hash, chỉ mục và cleanup trở thành atomic transaction xuyên slot.

Nếu dữ liệu cần giao dịch cùng slot với điều kiện nghiêm ngặt, thiết kế một tập key chuyên biệt và sử dụng RedisTemplate/script trong phạm vi đó có thể dễ kiểm soát hơn. Khi cần hành vi Repository, hãy kiểm chứng từng API và cấu trúc index cụ thể trong môi trường Cluster.

## 14. Kết nối Redis Cluster bằng Spring Boot

Spring Boot có thể cấu hình danh sách node Cluster, ví dụ:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - "redis-1.example.internal:6379"
          - "redis-2.example.internal:6379"
          - "redis-3.example.internal:6379"
```

Các địa chỉ chỉ là ví dụ, không phải hạ tầng có thật. Ứng dụng cần đúng driver, cấu hình bảo mật, xác thực và TLS nếu môi trường yêu cầu.

Khi thực hiện giao dịch:

- Dùng client hiểu topology Cluster.
- Bảo đảm các key transaction cùng slot và route về node phù hợp.
- Sử dụng connection/session đúng cách theo API transaction được driver hỗ trợ.
- Xử lý redirect, resharding, timeout và failover.
- Không dựa vào Spring transaction annotation để hợp nhất các primary node.
- Tránh tạo giao dịch quá dài khiến một node bị chiếm tài nguyên hoặc tăng tranh chấp.

### 14.1. Khác biệt giữa RedisTemplate và RedisClusterConnection

`RedisTemplate` cung cấp API cấp cao với serializer và callback. Khi dùng Redis Cluster, phía dưới là `RedisConnectionFactory` và client phải route lệnh theo slot. Các khả năng kết nối cụ thể của `RedisClusterConnection`, Redis driver và các method transaction có thể khác nhau giữa các phiên bản.

Khi một API hoạt động ở Redis standalone nhưng thất bại ở Cluster, hãy kiểm tra **hỗ trợ API của connector** trước khi kết luận Redis Cluster có thể hoặc không thể chạy mọi transaction cùng slot. Một cách dự phòng là sử dụng script hoặc một API cluster-aware có tính chất được xác nhận trong phiên bản đang dùng.

## 15. Kiểm tra và chẩn đoán sự cố

### 15.1. Trước tiên kiểm tra mọi key

```redis
CLUSTER KEYSLOT order:{o-101}:state
CLUSTER KEYSLOT order:{o-101}:receipt
CLUSTER KEYSLOT order:{o-102}:state
```

Hai key đầu cùng slot. Key của đơn khác không có bảo đảm cùng slot. Không kết luận dựa vào tên có cùng tiền tố.

### 15.2. Xác định slot đang thuộc node nào

```redis
CLUSTER SLOTS
CLUSTER INFO
```

`CLUSTER SLOTS` cho biết phân bố slot và các node phục vụ. `CLUSTER INFO` cung cấp tình trạng chung của Cluster. Các lệnh và quyền truy cập có thể bị hạn chế trên dịch vụ Redis managed.

Nếu slot đang di chuyển, cần xem xét resharding và hành vi của client đối với `MOVED`/`ASK`. Đừng sửa dữ liệu để tránh `CROSSSLOT` khi thực chất chỉ là thiếu hỗ trợ redirect hoặc sai cấu hình node.

### 15.3. Quan sát lỗi đúng ngữ cảnh

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách tiếp cận |
|---|---|---|
| `CROSSSLOT` khi `MGET`/`MSET` | Key khác slot | Dùng hash tag hoặc tách thành lệnh độc lập, hiểu rằng không nguyên tử |
| `CROSSSLOT` khi transaction | Nhiều key ngoài phạm vi một slot | Thiết kế lại aggregate hoặc workflow |
| `MOVED` khi thao tác đơn key | Client gửi nhầm node | Kiểm tra topology refresh, cluster-aware client |
| `TRYAGAIN` trong migration | Slot đang di chuyển, không đủ điều kiện xử lý ngay | Retry có kiểm soát, quan sát resharding |
| `EXEC` trả lỗi cho một lệnh | Lỗi runtime/kiểu dữ liệu hoặc giới hạn command | Xem từng kết quả; không giả định rollback |
| `EXEC` bị hủy do WATCH | Key đã được thay đổi | Đọc lại, retry có giới hạn và bảo đảm idempotency |
| Timeout sau khi ghi | Không rõ lệnh đã được chạy hay chưa | Kiểm tra trạng thái theo idempotency key, tránh retry mù |
| Giao dịch Spring không như kỳ vọng | Transaction support/driver/connection hoặc key khác slot | Xem cấu hình template, SessionCallback, contract Redis Cluster |

### 15.4. Kiểm tra bằng một test Cluster thật

Một Redis standalone không thể bộc lộ đầy đủ hành vi hash slot, redirect và failover. Để kiểm chứng giới hạn, môi trường thử nghiệm nên là **Redis Cluster có nhiều primary**.

Các trường hợp thử:

1. Hai key không tag: dùng `CLUSTER KEYSLOT` xác nhận chúng thuộc hai slot khác nhau, rồi thử một thao tác nhiều key cần same-slot.
2. Hai key có tag giống nhau: xác nhận chúng cùng slot và thực hiện transaction hoặc script được client hỗ trợ.
3. Thử thay đổi trạng thái song song bằng `WATCH` với contention.
4. Thử timeout/retry để kiểm tra idempotency của workflow.
5. Nếu hệ thống có yêu cầu sẵn sàng cao, kiểm thử ứng xử khi slot migration/failover bằng phương pháp vận hành kiểm soát.

Chỉ đọc key cuối cùng chưa đủ để khẳng định một giao dịch phức tạp đã an toàn trước crash, retry và failover. Cần quan sát cả lỗi, trạng thái từng bước và invariant nghiệp vụ.

## 16. Lựa chọn kiến trúc theo yêu cầu nhất quán

| Yêu cầu nghiệp vụ | Hướng thiết kế |
|---|---|
| Cập nhật vài key của cùng một đơn hàng | Dùng chung hash tag theo order, transaction/script cùng slot |
| Kiểm tra tồn kho rồi giữ số lượng trong một aggregate | Lua hoặc `WATCH` + `MULTI`/`EXEC` trên key cùng slot |
| Đọc nhiều key khác slot, không cần snapshot nhất quán | Các lệnh đọc độc lập/route qua Cluster, chấp nhận không atomic |
| Gửi nhiều thao tác độc lập để giảm RTT | Pipeline cluster-aware, không coi là transaction |
| Cập nhật hai account ở hai slot, có thể chấp nhận eventual consistency | Saga với trạng thái bền vững, idempotency và bù |
| Cần atomic commit qua nhiều shard hoặc cả SQL và Redis | Dùng hệ thống transaction phù hợp hoặc thiết kế lại ranh giới dữ liệu |
| Repository có index/TTL và cần thao tác nhất quán phức tạp | Kiểm tra tính năng cụ thể của Spring Data Redis/driver và thiết kế key phù hợp |
| Một tag chứa dữ liệu hoặc lưu lượng quá lớn | Giảm ranh giới aggregate, phân tách workflow, tránh hot slot |

Điểm chung: trước khi chọn Redis command, hãy xác định **bất biến nào cần được bảo toàn nguyên tử**. Sau đó xác định có thể đặt toàn bộ dữ liệu liên quan trong một slot hay không. Nếu không thể, phải thiết kế nhất quán liên bước hoặc chuyển phần nghiệp vụ đòi hỏi atomic commit sang nơi lưu trữ phù hợp.

## 17. Bài thực hành có hướng dẫn

### Bài 1 — Kiểm tra slot

Dùng một Redis Cluster thử nghiệm:

```redis
CLUSTER KEYSLOT order:101:state
CLUSTER KEYSLOT order:101:receipt
CLUSTER KEYSLOT order:{101}:state
CLUSTER KEYSLOT order:{101}:receipt
```

So sánh các kết quả. Giải thích tại sao hai key có hash tag `{101}` chắc chắn cùng slot, còn hai key dùng cùng tiền tố `order:101:` không có bảo đảm tương tự.

### Bài 2 — Transaction cùng slot

Thiết lập:

```redis
SET order:{101}:state NEW
SET order:{101}:receipt NONE
```

Thực hiện:

```redis
MULTI
SET order:{101}:state PAID
SET order:{101}:receipt R-9
EXEC
```

Đọc lại:

```redis
MGET order:{101}:state order:{101}:receipt
```

Quan sát kết quả của `EXEC` và lý giải vì sao cả hai key có thể tham gia transaction.

### Bài 3 — Thiết kế thử một giao dịch không cùng slot

Cho hai tài khoản:

```text
account:{alice}:balance
account:{bob}:balance
```

Trước khi chọn lệnh, dùng `CLUSTER KEYSLOT` kiểm tra slot. Nếu khác slot, hãy trình bày vì sao `MULTI`/`EXEC` hoặc Lua không giúp thực hiện chuyển tiền nguyên tử giữa hai tài khoản. Đề xuất transaction ID, trạng thái workflow, quy tắc retry và bước bù.

### Bài 4 — Hash tag và hot slot

Một nhóm đề xuất tag `{tenant-1}` cho 2 triệu key và hàng trăm nghìn thao tác mỗi giây. Hãy phân tích:

- Lợi ích nếu các giao dịch trong tenant cần nhiều key.
- Rủi ro tất cả key dồn vào cùng một slot/primary.
- Cách chia aggregate nhỏ hơn khi không cần atomicity xuyên toàn tenant.
- Những thao tác nào phải chuyển thành quy trình nhiều bước sau khi chia nhỏ.

### Bài 5 — Spring Data Redis

Viết một `SessionCallback` đặt hai String key `order:{o-9}:state` và `order:{o-9}:receipt`. Kiểm tra cùng slot bằng Redis CLI. Sau đó sửa một key thành `order:{o-10}:receipt`; quan sát giới hạn của Cluster/client và giải thích vì sao lỗi không thể khắc phục chỉ bằng `@Transactional`.

## 18. Những ngộ nhận quan trọng

**“Hai key nằm trên cùng primary nên dùng chung transaction được.”**  
Chưa đủ. Redis Cluster kiểm tra **hash slot**; khác slot vẫn vi phạm điều kiện multi-key dù node hiện tại giống nhau.

**“`redis-cli -c` tự giải quyết CROSSSLOT.”**  
Không. `-c` xử lý redirect ở mức CLI cho lệnh phù hợp, không xây distributed transaction.

**“`@Transactional` khiến Redis Cluster giống transaction SQL.”**  
Không. Spring transaction synchronization không thay thế atomic commit xuyên các Redis primary.

**“Pipeline có thể thay `MULTI`.”**  
Không. Pipeline giảm round-trip; hai lệnh ở hai slot vẫn có thể thành công/thất bại độc lập.

**“Lua script chạy atomically nên có thể sửa key ở mọi node.”**  
Không. Script chạy trên phạm vi node/slot hợp lệ của Redis Cluster; nó không phải một giao dịch distributed.

**“Chỉ cần thêm `{global}` cho mọi key.”**  
Kỹ thuật đó khiến nhiều key cùng slot nhưng có thể tạo hotspot, mất lợi ích chia tải, tăng rủi ro vận hành.

**“`EXEC` thành công có nghĩa mọi lệnh đều không thể lỗi.”**  
Không. Cần kiểm tra kết quả từng lệnh; Redis không cung cấp rollback của tất cả lỗi thực thi như database quan hệ.

**“Timeout nghĩa là transaction chưa chạy.”**  
Không chắc. Có thể lệnh đã được thực thi nhưng phản hồi bị mất. Hãy thiết kế idempotency và đối soát trạng thái.

## 19. Ghi nhớ

- Redis Cluster có **16.384 hash slot**, key được route theo CRC16; key cùng node chưa chắc cùng slot.
- **Hash tag `{...}`** giúp các key cùng một aggregate tính ra cùng slot. Đây là cách chủ đạo để thiết kế transaction nhiều key trong Redis Cluster.
- `MULTI`/`EXEC`, `WATCH`, Lua và Redis Function **không cung cấp atomic transaction xuyên các slot/primary**.
- `CROSSSLOT` phản ánh ràng buộc nhiều key khác slot; `MOVED`/`ASK` phản ánh redirect/topology và cần được xử lý theo cơ chế riêng.
- `SessionCallback` giúp nhóm thao tác trên cùng connection của Spring Data Redis, nhưng **không làm mất giới hạn Redis Cluster**. `@Transactional` cũng không thay đổi điều đó.
- Pipeline có thể xử lý nhiều lệnh độc lập nhưng **không bảo đảm atomicity**.
- Khi cần sửa dữ liệu xuyên slot, sử dụng **workflow/saga, idempotency, trạng thái bền vững và thao tác bù**, hoặc một hệ thống transactional phù hợp.
- Hash tag quá rộng tạo **hot slot**; thiết kế phạm vi transaction theo aggregate và nhu cầu mở rộng thực tế.
- Với Redis Repository có secondary index/TTL, phải xem xét cả **các key phụ do Repository quản lý**, không chỉ Hash chính.

### Tài liệu tham khảo chính thức

- [Redis Cluster specification — Hash slots, hash tags và multi-key operations](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/)
- [Redis — MULTI](https://redis.io/docs/latest/commands/multi/)
- [Redis — EXEC](https://redis.io/docs/latest/commands/exec/)
- [Redis — WATCH](https://redis.io/docs/latest/commands/watch/)
- [Redis — CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/)
- [Redis — Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/)
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
