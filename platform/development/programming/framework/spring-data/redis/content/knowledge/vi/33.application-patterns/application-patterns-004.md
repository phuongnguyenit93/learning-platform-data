# Fencing token và bảo vệ tài nguyên ở hệ thống nhận thao tác

## 1. Vì sao một distributed lock có TTL vẫn chưa đủ bảo vệ dữ liệu?

Giả sử ứng dụng Spring Boot chạy trên nhiều instance, sử dụng Redis để khóa một công việc cập nhật báo cáo. Tại mỗi thời điểm, ta muốn chỉ một worker có quyền ghi kết quả cuối cùng vào database hoặc dịch vụ lưu trữ.

Một giải pháp ban đầu là đặt khóa Redis bằng `SET ... NX PX`:

```redis
SET lock:report:42 worker-A NX PX 10000
```

Ý nghĩa:

- `NX`: chỉ tạo khóa nếu chưa tồn tại.
- `PX 10000`: khóa tự hết hạn sau khoảng 10 giây.
- `worker-A`: giá trị định danh bên đang giữ khóa.

Nếu lệnh trả `OK`, worker A đã lấy được **lease** (quyền sở hữu có thời hạn). Nhưng điều gì xảy ra nếu A bị tạm dừng lâu hơn TTL?

```text
Thời gian       Worker A                 Redis                Worker B
   t0         Lấy khóa thành công   lock=worker-A, TTL=10s
   t1         Đọc dữ liệu, chuẩn bị kết quả
   t2         Bị dừng GC / pause / nghẽn mạng
   t3                                Khóa A hết hạn
   t4                                                     Lấy khóa thành công
   t5                                                     Tính kết quả mới
   t6                                                     Ghi kết quả B
   t7         A tiếp tục chạy
   t8         A ghi kết quả cũ
```

**Lỗi quan trọng:** dù Worker B đã trở thành chủ sở hữu mới, Worker A **không tự biết** rằng quyền của mình đã hết hạn. A có thể hoàn tất một thao tác đã bắt đầu trước đó và **ghi đè lên kết quả mới**.

Redis lock có TTL chủ yếu giúp hệ thống **không bị kẹt khóa mãi mãi** khi worker chết. Nó không thể thu hồi mã Java đang chạy, không thể hủy một HTTP request đã gửi đi và không thể ngăn một tiến trình bị pause tiếp tục tác động đến tài nguyên bên ngoài sau khi lease mất hiệu lực.

**Fencing token** giải quyết một phần rủi ro này bằng cách đánh dấu **thứ tự quyền sở hữu**. Quan trọng nhất, **hệ thống nhận thao tác** phải kiểm tra token và từ chối thao tác mang token cũ.

## 2. Fencing token là gì?

Fencing token là một số thứ tự **tăng đơn điệu**, được cấp khi một chủ sở hữu giành được quyền thao tác lên tài nguyên.

Ví dụ:

```text
Worker A được cấp lease -> fencing token = 41
Worker A hết lease
Worker B được cấp lease -> fencing token = 42
Worker C được cấp lease -> fencing token = 43
```

Các token thể hiện thứ tự cấp quyền:

```text
41 < 42 < 43
```

Khi worker gửi lệnh ghi tới hệ thống lưu trữ, nó phải gửi kèm token:

```json
{
  "resourceId": "report-42",
  "fencingToken": 42,
  "payload": "Kết quả tính toán mới"
}
```

Hệ thống nhận duy trì **token lớn nhất đã được chấp nhận** đối với tài nguyên đó:

```text
Resource report-42
    lastAcceptedFence = 42
```

Nếu một thao tác đến với token `41`, receiver có thể từ chối vì nó thuộc đời lease **cũ hơn**.

```text
Worker A (token 41) ───────────> Resource Server
                                  lastFence = 42
                                  41 <= 42 => REJECT

Worker C (token 43) ───────────> Resource Server
                                  lastFence = 42
                                  43 > 42 => ACCEPT
                                  lastFence = 43
```

**Tư tưởng cốt lõi:** thay vì chỉ hỏi Redis “khóa có còn tồn tại không?”, tài nguyên được bảo vệ phải **tự kiểm soát** thao tác nó nhận, dựa trên một thứ tự quyền sở hữu đáng tin cậy.

### 2.1. Fencing token không phải lock token

Trong thực tế thường có hai loại giá trị khác nhau:

| Giá trị | Vai trò |
|---|---|
| **Owner ID** hoặc **lock value** ngẫu nhiên | Xác định ai đang giữ khóa để chỉ chủ cũ được phép release/renew |
| **Fencing token** tăng đơn điệu | Cho phép hệ thống nhận nhận biết thao tác từ lease cũ hay mới |
| **TTL/lease duration** | Giới hạn thời gian chiếm khóa khi chủ sở hữu chết |
| **Event/operation ID** | Nhận biết một yêu cầu nghiệp vụ để chống thực hiện lặp |

Ví dụ:

```text
ownerId       = 9f87d7ce-6ca1-4e1d-8f40-49cb45d6c1a1
fencingToken  = 42
operationId   = operation-abc-123
```

Owner ID có thể là UUID khó trùng, nhưng **UUID không có thứ tự tăng đơn điệu**. Một UUID ngẫu nhiên không thể thay fencing token.

Ngược lại, fencing token `42` không nhất thiết là một bí mật hay một bằng chứng xác thực người dùng. Một client không đáng tin không được tự chọn `9999999` để chiếm quyền ghi. Hệ thống nhận còn phải có **xác thực và ràng buộc issuer/worker** phù hợp.

### 2.2. Fencing token khác optimistic locking version

Một cột `version` trong database thường được tăng theo mỗi lần cập nhật bản ghi nhằm ngăn lost update:

```sql
UPDATE document
SET body = :newBody, version = version + 1
WHERE id = :id AND version = :expectedVersion;
```

Đây là **optimistic concurrency control** dựa trên phiên bản dữ liệu hiện tại.

Fencing token, ngược lại, biểu diễn **thứ tự cấp quyền cho các worker**. Nó được cấp bởi cơ chế điều phối trước khi worker thực hiện tác vụ; receiver sử dụng token để loại lệnh của lease cũ.

Cả hai có thể dùng chung:

```text
fencing token -> loại bỏ chủ sở hữu lỗi thời
row version   -> phát hiện cập nhật cạnh tranh trên dữ liệu
```

Chúng có mục đích gần nhau nhưng không mặc nhiên tương đương.

## 3. Vì sao Redis SET NX PX và release đúng owner vẫn chưa giải quyết stale writer?

Một distributed lock Redis đơn giản có thể triển khai như sau:

```redis
SET lock:report-42 <unique-owner-id> NX PX 10000
```

Khi release, cần so sánh owner ID rồi mới xóa khóa bằng Lua để tránh A xóa nhầm khóa B:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Cơ chế **compare-and-delete** là cần thiết. Nhưng nó chỉ bảo vệ **việc xóa khóa**, không bảo vệ một ghi bên ngoài Redis.

```text
Worker A bị pause -> lease A hết hạn
Worker B có khóa -> update DB
Worker A tỉnh lại -> vẫn có thể gọi UPDATE DB
Worker A release -> compare-and-delete sẽ thất bại
```

Release thất bại **xảy ra quá muộn** nếu A đã ghi dữ liệu cũ vào database.

Một biện pháp khác là kiểm tra lại khóa Redis trước khi ghi:

```text
A: GET lock -> vẫn là A
           [Bị dừng ở đây]
Redis: khóa A hết hạn, B giành khóa
A: gửi ghi database
```

Đây là lỗi **time-of-check to time-of-use (TOCTOU)**: quyền sở hữu có thể đổi **sau khi kiểm tra nhưng trước lúc sử dụng**.

Thậm chí nếu A gửi request HTTP trong lúc lease còn hiệu lực, request có thể nằm chờ trên mạng, trong queue hoặc ở hệ thống nhận rồi được thực thi **sau khi lease hết hạn**.

Vì vậy, bảo vệ đúng chỗ là **điểm thực sự ghi hoặc thay đổi tài nguyên**, không chỉ là một lần GET Redis trước thao tác.

## 4. Hệ thống nhận phải kiểm tra fencing token

Giả sử hệ thống nhận là một service khác, database, object storage hoặc một bộ điều khiển thiết bị. Worker không được phép ghi trực tiếp bỏ qua lớp kiểm tra.

Mỗi yêu cầu phải có token:

```text
Worker
    |
    | update(resourceId, payload, fence=42)
    v
Resource Server
    |
    +-- Xác thực caller và ngữ cảnh tài nguyên
    |
    +-- Kiểm tra token theo trạng thái bền vững
    |
    +-- Token lỗi thời? -> REJECT
    |
    +-- Token hợp lệ? -> APPLY + lưu fence mới
    |
    v
Protected Resource
```

### 4.1. Luật kiểm tra đơn giản nhất

Nếu mỗi lease chỉ thực hiện **một lần ghi** cho một resource, receiver có thể áp dụng:

```text
Nếu incomingFence > lastAcceptedFence:
    áp dụng cập nhật
    lastAcceptedFence = incomingFence
Ngược lại:
    từ chối
```

Điều kiện cần được thực hiện **nguyên tử với thay đổi tài nguyên**.

Không triển khai bằng hai truy vấn độc lập:

```text
SELECT last_fence
if incomingFence > lastFence:
    UPDATE payload
```

vì hai request có thể xen kẽ giữa SELECT và UPDATE, tạo race condition. Cần một câu SQL cập nhật có điều kiện hoặc transaction/primitive tương đương.

### 4.2. Ví dụ đúng khi token mới đã được chấp nhận trước

Ban đầu:

```text
lastAcceptedFence = 40
```

Diễn biến:

```text
A lấy lease, fence=41
A pause
B lấy lease mới, fence=42
B gửi update, receiver chấp nhận 42
A tiếp tục và gửi update với 41
Receiver thấy 41 < 42 -> REJECT
```

Nhờ receiver nhớ fence cao nhất, A không thể ghi đè bản mới sau khi B đã được chấp nhận.

### 4.3. Giới hạn quan trọng của luật lastAcceptedFence

**Cần hiểu chính xác ngữ nghĩa:** chỉ so với token lớn nhất **đã được receiver nhìn thấy** không thể tự biết một lease mới vừa được cấp ở Redis nếu owner mới chưa gửi bất cứ lệnh nào đến receiver.

Ví dụ:

```text
Receiver lastAcceptedFence = 40
A lấy fence=41 rồi bị pause
Lease A hết hạn
B lấy fence=42 nhưng CHƯA gửi lệnh tới receiver
A tỉnh lại và gửi fence=41
```

Tại thời điểm nhận yêu cầu A, receiver vẫn nhớ `40`; theo luật `41 > 40`, receiver **có thể chấp nhận A** dù B đã giành lease mới.

Do đó:

- Luật **high-water mark** từ chối chắc chắn các token cũ **sau khi receiver đã ghi nhận token mới hơn**.
- Nó không tự tạo ra một cơ chế kiểm tra **lease đang có hiệu lực tại thời điểm hiện tại**.
- Nếu yêu cầu là “một owner cũ tuyệt đối không được ghi từ ngay thời điểm lease mới được cấp, dù owner mới chưa làm gì”, cần cơ chế mạnh hơn: **đăng ký epoch/fence mới tại receiver trước khi cho phép thao tác**, hoặc receiver kiểm tra quyền với nguồn điều phối có tính nhất quán phù hợp.
- Việc đăng ký fence và mọi cập nhật dữ liệu tại receiver phải được đồng bộ theo cùng một cơ chế nguyên tử/transaction; chỉ thêm một bước GET rồi UPDATE vẫn có race.
- Nếu nhiều bước nghiệp vụ cùng dùng một lease, receiver cần trạng thái epoch hiện hành và quy tắc cấp phép trong epoch, chứ không thể mặc định mọi lần ghi với cùng token đều bị từ chối.

Đây là ranh giới thiết kế rất quan trọng. Fencing token hiệu quả nhất khi **hệ thống nhận thực sự tham gia giao thức bảo vệ tài nguyên**.

## 5. Phát hành fencing token cần có những tính chất nào?

Một fencing token dùng để bảo vệ nhiều worker phải có các tính chất:

1. **Tăng đơn điệu:** một lease được cấp sau phải có token lớn hơn lease được cấp trước cho cùng miền bảo vệ.
2. **Không tái sử dụng:** token cũ không được xuất hiện như token của một đời lease mới.
3. **Cấp quyền và cấp token gắn với nhau:** worker không được thấy “đã có khóa” nhưng chưa biết token nào đại diện cho lease đó, rồi tự dùng token tùy ý.
4. **Không thể bị client giả mạo:** receiver phải biết token đến từ nguồn cấp quyền hợp lệ.
5. **Receiver giữ trạng thái đủ bền:** mốc fencing không được tự trở về 0 sau restart hoặc failover của nơi lưu trạng thái.
6. **So sánh tại điểm thay đổi tài nguyên:** chặn request cũ ngay lúc thực hiện, không chỉ lúc worker chuẩn bị gửi.

Token có thể tăng với khoảng trống:

```text
101, 102, 106, 107, ...
```

**Không cần liên tiếp**, chỉ cần thứ tự tăng đơn điệu và không tái sử dụng theo quy tắc của giao thức. Điều này cho phép mất một số token do lần thử cấp quyền thất bại.

### 5.1. Redis INCR là công cụ thuận tiện nhưng có giới hạn

Redis có lệnh:

```redis
INCR fence:report-42
```

Nếu khóa đếm đang là `41`, kết quả là `42`. Trên **một Redis primary đang hoạt động**, mỗi lệnh `INCR` được thực thi nguyên tử.

Nhưng:

```redis
INCR fence:report-42
SET lock:report-42 ... NX PX 10000
```

là **hai lệnh độc lập**. Nếu được thực thi không có giao thức chặt chẽ, việc token gắn với một lease thành công có thể khó xác định, hoặc có khoảng đua giữa các bước.

Có thể kết hợp cấp lease và tạo token trong **một Lua script** để nguyên tử trên một Redis server. Đó là phần tiếp theo.

**Giới hạn về độ bền:** Redis replication thường bất đồng bộ. Nếu primary đã cấp token `42` nhưng chưa đồng bộ trạng thái bộ đếm sang replica trước khi failover, primary mới có thể vẫn giữ `41` và về sau cấp lại `42`. Điều này vi phạm tính không tái sử dụng và tăng đơn điệu xuyên failover.

Vì vậy, **chỉ `INCR` trên Redis với failover bất đồng bộ không tự tạo fencing token có bảo đảm mạnh**. Với tài nguyên quan trọng, cần nguồn cấp token có tính bền vững/nhất quán phù hợp hoặc một giao thức fencing được đảm bảo bởi chính hệ thống nhận.

## 6. Lua script: gắn cấp lease với cấp fencing token

Trong một Redis primary, ta có thể yêu cầu: chỉ khi khóa không tồn tại, tăng bộ đếm và đặt lease mới, tất cả trong cùng một Lua script.

### 6.1. Thiết kế khóa

Cho tài nguyên `report-42`:

```text
lock key:     guard:{report-42}:lock
sequence key: guard:{report-42}:sequence
```

Phần `{report-42}` là **Redis Cluster hash tag**. Nếu ứng dụng sử dụng Redis Cluster, hai khóa này có cùng hash slot để một script nhiều khóa có thể thực thi theo quy tắc của Cluster.

Không đặt TTL cho sequence key trong ví dụ. Nếu xóa hoặc làm hết hạn sequence, số tiếp theo có thể bắt đầu lại từ giá trị thấp, khiến token bị tái sử dụng.

Lưu ý rằng việc giữ sequence key không hết hạn **chỉ loại bỏ một kiểu reset chủ động**; nó không giải quyết rủi ro failover/replication làm mất write hoặc chính sách eviction.

### 6.2. Lua cấp khóa và token

```lua
-- KEYS[1] = lock key
-- KEYS[2] = sequence key
-- ARGV[1] = lease TTL (milli giây, > 0)
-- ARGV[2] = owner ID duy nhất

if redis.call('EXISTS', KEYS[1]) == 1 then
    return nil
end

local token = redis.call('INCR', KEYS[2])

redis.call(
    'PSETEX',
    KEYS[1],
    ARGV[1],
    ARGV[2] .. ':' .. tostring(token)
)

return token
```

Trình tự trong script:

1. Kiểm tra khóa lease hiện có.
2. Nếu đã bị giữ thì **không cấp quyền mới**.
3. Nếu trống, tăng fencing sequence.
4. Đặt khóa mới với TTL, trong giá trị lưu cả owner ID và token.
5. Trả token cho worker.

Redis thực thi Lua script như một đơn vị nguyên tử đối với các lệnh khác trên cùng Redis server. Vì vậy, trong điều kiện hoạt động bình thường của primary, không có worker khác chen vào giữa `EXISTS`, `INCR` và `PSETEX`.

Đây là ví dụ giảng giải cơ chế cấp token, **không phải giao thức lock đã được chứng minh an toàn xuyên mọi kiểu failover**. Redis script có tính nguyên tử đối với các lệnh khác, nhưng **không phải transaction có rollback tổng quát** nếu script phát sinh lỗi sau khi đã thay đổi một phần trạng thái. Triển khai thực cần kiểm soát kiểu dữ liệu, TTL, quyền gọi lệnh, overflow và lỗi.

### 6.3. Khi khóa đã được giữ

Giả sử `guard:{report-42}:lock` đang tồn tại. Script trả `nil` và không tăng sequence.

Nếu khóa đã hết hạn, lần thử mới có thể nhận token tiếp theo:

```text
A -> token 41
A hết lease
B -> token 42
```

Token được sinh ra cùng thời điểm script cấp lease. Tuy nhiên, nếu A chưa nhận được phản hồi do lỗi mạng, A chưa thể biết chắc lệnh cấp lease đã chạy hay chưa. Phần xử lý lỗi mơ hồ sẽ được trình bày ở dưới.

## 7. Spring Data Redis: mã hóa giao thức cấp lease

Dưới đây là ví dụ dùng **`StringRedisTemplate` + `DefaultRedisScript`** để thực thi script trên Redis. Các khóa được tạo từ một `resourceId` hợp lệ. Ví dụ sử dụng Spring Data Redis và Java 17+.

### 7.1. Định nghĩa lease

```java
package com.example.fencing;

public record FencedLease(
        String resourceId,
        String ownerId,
        long fencingToken
) {
}
```

Bản ghi này mô tả quyền được cấp. Nó **không tự chứng minh lease vẫn còn hiệu lực vào mọi thời điểm sau khi được tạo**.

### 7.2. Service xin lease với token

```java
package com.example.fencing;

import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class RedisFencedLeaseService {

    private static final String ACQUIRE_SCRIPT = """
            if redis.call('EXISTS', KEYS[1]) == 1 then
                return nil
            end

            local token = redis.call('INCR', KEYS[2])

            redis.call(
                'PSETEX',
                KEYS[1],
                ARGV[1],
                ARGV[2] .. ':' .. tostring(token)
            )

            return token
            """;

    private static final String RELEASE_SCRIPT = """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end

            return 0
            """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> acquireScript;
    private final DefaultRedisScript<Long> releaseScript;

    public RedisFencedLeaseService(StringRedisTemplate redis) {
        this.redis = redis;

        acquireScript = new DefaultRedisScript<>();
        acquireScript.setScriptText(ACQUIRE_SCRIPT);
        acquireScript.setResultType(Long.class);

        releaseScript = new DefaultRedisScript<>();
        releaseScript.setScriptText(RELEASE_SCRIPT);
        releaseScript.setResultType(Long.class);
    }

    public Optional<FencedLease> tryAcquire(
            String resourceId,
            Duration leaseTime) {

        checkResourceId(resourceId);

        long ttlMillis = leaseTime.toMillis();

        if (ttlMillis <= 0) {
            throw new IllegalArgumentException(
                    "Lease TTL phải > 0 ms"
            );
        }

        String ownerId = UUID.randomUUID().toString();

        Long token = redis.execute(
                acquireScript,
                List.of(lockKey(resourceId), sequenceKey(resourceId)),
                Long.toString(ttlMillis),
                ownerId
        );

        if (token == null) {
            return Optional.empty();
        }

        return Optional.of(new FencedLease(
                resourceId,
                ownerId,
                token
        ));
    }

    public boolean release(FencedLease lease) {
        String expectedValue =
                lease.ownerId() + ":" + lease.fencingToken();

        Long deleted = redis.execute(
                releaseScript,
                List.of(lockKey(lease.resourceId())),
                expectedValue
        );

        return Long.valueOf(1L).equals(deleted);
    }

    private static String lockKey(String resourceId) {
        return "guard:{" + resourceId + "}:lock";
    }

    private static String sequenceKey(String resourceId) {
        return "guard:{" + resourceId + "}:sequence";
    }

    private static void checkResourceId(String resourceId) {
        if (resourceId == null
                || !resourceId.matches("[A-Za-z0-9._-]{1,128}")) {

            throw new IllegalArgumentException(
                    "resourceId không hợp lệ"
            );
        }
    }
}
```

Với `StringRedisTemplate`, arguments của script được mã hóa thành chuỗi phù hợp với ví dụ Lua. Hai khóa có chung hash tag để chạy trên cùng slot nếu sử dụng Cluster.

**Luồng cấp lease:**

```text
tryAcquire("report-42", 10 giây)
            |
            v
Lua trên Redis primary
            |
      +-----+-----+
      |           |
  lock có      lock trống
      |           |
      v           v
  return nil     INCR sequence
      |           |
      v           v
Optional.empty   PSETEX lock + owner:token
                  |
                  v
           return token
                  |
                  v
        Optional<FencedLease>
```

Lưu ý:

- **`Optional.empty()`** biểu thị script không cấp lease vì khóa đang bị giữ; lỗi mạng hoặc lỗi Redis sẽ phát exception chứ không nên âm thầm quy về “không có khóa”.
- Một `FencedLease` là **quyền có TTL**, không phải giấy phép ghi vô thời hạn.
- Nên đặt giới hạn thời gian làm việc và ngừng gửi thao tác khi đã biết lease bị mất.
- Không đặt TTL cho sequence key. Cần cấu hình persistence, eviction và failover phù hợp nếu phụ thuộc vào tính tăng đơn điệu của token.
- Với Redis Cluster, mọi key truy cập trong một Lua script phải tuân theo yêu cầu cùng hash slot.

### 7.3. Vì sao release phải so sánh owner và token?

Giả sử:

```text
A lấy khóa: value = owner-A:41
A bị pause, khóa hết hạn
B lấy khóa: value = owner-B:42
A tỉnh lại, gọi release
```

Nếu A gọi trực tiếp:

```redis
DEL guard:{report-42}:lock
```

nó sẽ xóa khóa của B. Đây là lỗi nghiêm trọng.

Script release:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

chỉ xóa nếu giá trị hiện tại đúng với `owner-A:41`. Khi Redis đang giữ `owner-B:42`, script trả `0` và không xóa khóa.

**Tuy nhiên:** release an toàn chỉ bảo vệ quyền sở hữu khóa. Để ngăn A ghi trễ vào database, **receiver vẫn phải kiểm tra fencing token**.

## 8. Receiver bảo vệ dữ liệu bằng phép cập nhật nguyên tử

Giả sử một service nhận tác vụ ghi kết quả báo cáo vào PostgreSQL. Mỗi báo cáo có một dòng chứa token lớn nhất từng được chấp nhận.

### 8.1. Cấu trúc dữ liệu

```sql
CREATE TABLE protected_report (
    report_id VARCHAR(128) PRIMARY KEY,
    result_text TEXT NOT NULL,
    last_fence BIGINT NOT NULL DEFAULT 0
);
```

Chuẩn bị một bản ghi:

```sql
INSERT INTO protected_report (
    report_id,
    result_text,
    last_fence
) VALUES (
    'report-42',
    'initial',
    0
);
```

### 8.2. Cập nhật bằng điều kiện fencing

Giả sử một lease chỉ được phép tạo **một bản ghi kết quả**. Receiver có thể dùng:

```sql
UPDATE protected_report
SET result_text = :result,
    last_fence = :incomingFence
WHERE report_id = :reportId
  AND last_fence < :incomingFence;
```

Điều kiện nằm **trong chính câu lệnh `UPDATE`**, nên database xử lý cập nhật và kiểm tra fence trong một thao tác đồng bộ theo ngữ nghĩa transaction của database.

Diễn biến minh họa:

```text
last_fence = 0

Worker B gửi token 42 -> UPDATE thành công
                        -> last_fence = 42

Worker A gửi token 41 -> WHERE last_fence < 41 sai
                        -> 0 row updated
                        -> REJECT
```

### 8.3. Spring JdbcTemplate tại Resource Server

```java
package com.example.fencing.receiver;

public record FencedReportCommand(
        String reportId,
        long fencingToken,
        String resultText
) {
}
```

Ví dụ service:

```java
package com.example.fencing.receiver;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProtectedReportWriter {

    private final JdbcTemplate jdbc;

    public ProtectedReportWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean applyOnce(FencedReportCommand command) {
        if (command.fencingToken() <= 0) {
            throw new IllegalArgumentException(
                    "Fencing token phải dương"
            );
        }

        int rows = jdbc.update(
                """
                UPDATE protected_report
                SET result_text = ?,
                    last_fence = ?
                WHERE report_id = ?
                  AND last_fence < ?
                """,
                command.resultText(),
                command.fencingToken(),
                command.reportId(),
                command.fencingToken()
        );

        return rows == 1;
    }
}
```

Nếu `applyOnce` trả `false`, nghĩa là không có dòng nào đáp ứng điều kiện. Những nguyên nhân có thể gồm:

- Token cũ hơn hoặc bằng token đã chấp nhận.
- `reportId` không tồn tại.
- Chính sách kiểm tra đầu vào khác khiến cập nhật không được áp dụng.

Trong ứng dụng thực, cần trả trạng thái lỗi cụ thể thay vì luôn gộp thành một thông báo chung. Để tránh tiết lộ thông tin tài nguyên, quyền truy cập và thông tin lỗi phải được thiết kế phù hợp.

**Ví dụ này chỉ cho phép một cập nhật cho mỗi token.** Nếu một worker cần ghi **nhiều bước dưới cùng một lease**, điều kiện `< incomingFence` sẽ từ chối bước thứ hai. Khi đó phải thiết kế receiver giữ **epoch/token hiện hành** và **operation ID/sequence** riêng để cho phép những thao tác hợp lệ trong cùng epoch, đồng thời chống thực hiện lặp. Không đổi `<` thành `<=` một cách tùy tiện vì như vậy có thể cho phép request lặp ghi đè.

### 8.4. Không thực hiện kiểm tra và ghi thành hai bước

Cách không an toàn:

```java
long known = jdbc.queryForObject(
        "SELECT last_fence FROM protected_report WHERE report_id = ?",
        Long.class,
        command.reportId()
);

if (command.fencingToken() > known) {
    jdbc.update(
            "UPDATE protected_report SET result_text = ? WHERE report_id = ?",
            command.resultText(),
            command.reportId()
    );
}
```

Giữa `SELECT` và `UPDATE`, worker khác có thể cập nhật token mới hơn. Code trên vẫn có thể ghi đè dữ liệu.

Một câu `UPDATE ... WHERE last_fence < ?` là cách rõ ràng hơn khi điều kiện và tác dụng phụ nằm trong cùng một database.

## 9. Toàn bộ luồng từ Spring Boot tới receiver

Một worker sẽ thực hiện:

```text
                 Spring Boot Worker
                         |
                         v
             tryAcquire(resourceId)
                         |
                  +------+------+
                  |             |
             Không có khóa    Có lease
                  |             |
                  v             v
            Bỏ qua/retry    FencedLease(token)
                                |
                                v
                      Tính kết quả nghiệp vụ
                                |
                                v
                     Gửi tới Resource Server
                       (resourceId, token, payload)
                                |
                                v
                       Receiver xác thực
                                |
                                v
                    UPDATE có điều kiện token
                                |
                     +----------+-----------+
                     |                      |
                Chấp nhận               Từ chối
                     |                      |
                     v                      v
               Lưu dữ liệu             Stale/repeated
                     |
                     v
               Release đúng owner
```

Một đoạn gọi ví dụ:

```java
package com.example.fencing;

import java.time.Duration;
import java.util.Optional;

public class ReportWorker {

    private final RedisFencedLeaseService leases;
    private final ReportCalculator calculator;
    private final ReportResourceClient resourceClient;

    public ReportWorker(
            RedisFencedLeaseService leases,
            ReportCalculator calculator,
            ReportResourceClient resourceClient) {
        this.leases = leases;
        this.calculator = calculator;
        this.resourceClient = resourceClient;
    }

    public void refreshReport(String reportId) {
        Optional<FencedLease> acquired = leases.tryAcquire(
                reportId,
                Duration.ofSeconds(10)
        );

        if (acquired.isEmpty()) {
            return;
        }

        FencedLease lease = acquired.get();

        try {
            String result = calculator.calculate(reportId);

            resourceClient.submit(
                    reportId,
                    lease.fencingToken(),
                    result
            );

        } finally {
            // Release bằng compare-and-delete.
            // Nếu lease đã hết hạn, release không xóa khóa
            // của worker mới.
            leases.release(lease);
        }
    }
}
```

Giả sử `ReportCalculator` và `ReportResourceClient` là các interface nghiệp vụ:

```java
public interface ReportCalculator {
    String calculate(String reportId);
}
```

```java
public interface ReportResourceClient {
    void submit(
            String reportId,
            long fencingToken,
            String result
    );
}
```

Phần cốt lõi của `submit(...)` là gửi `fencingToken` tới **receiver thực sự sở hữu tài nguyên**. Nếu receiver bỏ qua token, toàn bộ giao thức fencing mất tác dụng.

### 9.1. Dùng finally để release có đủ không?

`finally` giúp ứng dụng cố gắng giải phóng khóa khi luồng làm việc kết thúc, nhưng:

- Worker có thể bị kill, crash hoặc mất kết nối.
- `release(...)` có thể lỗi mạng.
- Lease có thể đã hết hạn.
- A không được xóa khóa của B sau khi hết hạn.
- `finally` **không ngăn** request cũ đã gửi tới receiver.

TTL giải quyết tình huống khóa bị bỏ lại khi owner chết; compare-and-delete giải quyết xóa nhầm khóa; fencing token giải quyết **một lớp bảo vệ riêng tại receiver**.

### 9.2. Nếu tác vụ kéo dài hơn TTL?

Có thể triển khai **renew/extend lease** nếu worker còn là owner và hệ thống muốn cho phép công việc dài.

Ví dụ Lua renew:

```lua
-- KEYS[1] = lock key
-- ARGV[1] = ownerId:token được kỳ vọng
-- ARGV[2] = TTL mới tính bằng mili giây

if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end

return 0
```

Nếu khóa đã hết hạn hoặc đổi chủ, renew phải thất bại. Worker cần dừng phát thêm thao tác khi phát hiện mất lease.

Tuy nhiên:

- Worker có thể bị pause và không kịp renew.
- Lệnh ghi đã gửi trước khi biết mất lease có thể hoàn thành sau đó.
- Dù renew tốt, receiver vẫn phải áp dụng fencing.
- Với hệ thống yêu cầu an toàn nghiêm ngặt, cần đảm bảo nguồn cấp token và receiver có cơ chế nhất quán phù hợp.

## 10. Một tài nguyên có nhiều thao tác trong cùng lease

Ví dụ `fencingToken = 42` được cấp cho worker và worker cần cập nhật nhiều đoạn của cùng một file hoặc nhiều trường của cùng một object.

Một receiver chỉ dùng:

```sql
WHERE last_fence < :incomingFence
```

sẽ chấp nhận **lần đầu token 42** nhưng từ chối các lần tiếp theo với token 42.

Không thể suy ra rằng mọi mô hình fencing đều chỉ cho phép một lệnh cho mỗi lease. Khi cần **nhiều lệnh hợp lệ** từ một owner, có thể chia giao thức thành hai bước.

### 10.1. Đăng ký epoch mới

Receiver lưu một **epoch hiện hành**:

```text
resource = report-42
currentFence = 42
currentOwner = worker-B
```

Worker giành lease mới phải **đăng ký token mới với receiver** trước khi gửi các lệnh thay đổi dữ liệu. Việc đăng ký yêu cầu token mới lớn hơn token trước:

```text
REGISTER_FENCE(report-42, token=42)
```

Receiver cập nhật `currentFence` **nguyên tử**. Từ đó, các lệnh mang token 41 sẽ bị từ chối.

### 10.2. Kiểm tra epoch của mỗi thao tác

Mỗi thao tác có thể bao gồm:

```json
{
  "resourceId": "report-42",
  "fencingToken": 42,
  "operationId": "op-550",
  "operationSequence": 3,
  "payload": "Một phần kết quả"
}
```

Receiver kiểm tra:

1. Caller hợp lệ và có quyền thao tác lên resource.
2. `fencingToken == currentFence` tại **thời điểm thay đổi dữ liệu**.
3. `operationId` chưa được áp dụng, hoặc có kết quả idempotent đã lưu.
4. Nếu thứ tự trong cùng lease quan trọng, `operationSequence` phải hợp lệ.
5. Ghi dữ liệu và ghi nhận `operationId` trong cùng transaction hoặc cơ chế nguyên tử tương đương.

```text
REGISTER epoch 42
       |
       v
       +--> WRITE(token=42, operation=1) -> ACCEPT
       +--> WRITE(token=42, operation=2) -> ACCEPT
       +--> WRITE(token=41, operation=3) -> REJECT
       |
REGISTER epoch 43
       |
       +--> WRITE(token=42, operation=4) -> REJECT
       +--> WRITE(token=43, operation=1) -> ACCEPT
```

**Đăng ký epoch và thao tác ghi phải được đồng bộ ở receiver**. Nếu một request cũ đã bắt đầu kiểm tra trước khi epoch mới được đăng ký, receiver cần dùng transaction/row locking/CAS đúng cách để không cho request cũ commit trái quy tắc sau khi epoch mới đã có hiệu lực.

### 10.3. Vẫn còn một cửa sổ trước khi receiver biết epoch mới

Trong hệ thống phân tán, receiver không thể đoán rằng Redis đã cấp token mới nếu chưa nhận và xác minh thông tin đó.

Nếu chính sách yêu cầu ngăn stale owner **ngay từ lúc lease cũ hết hạn**, không chỉ sau lúc receiver nhận epoch mới, phải có một cơ chế xác thực quyền hiện hành đủ mạnh ở nơi tài nguyên được thay đổi. Ví dụ receiver trực tiếp tham gia việc cấp quyền, hoặc một coordinator tuyến tính hóa (*linearizable*) đóng vai trò nguồn phiên bản hiện hành mà receiver tin cậy.

Chỉ thêm một token tăng dần vào HTTP header mà không phối hợp receiver **không thể cung cấp mọi bảo đảm** của một hệ thống locking nhất quán mạnh.

## 11. Fencing token phải được phát hành từ nguồn đáng tin cậy

### 11.1. Vấn đề khi dùng Redis với failover bất đồng bộ

Trong ví dụ Lua, Redis vừa tăng sequence vừa đặt lock. Trên một primary đang hoạt động, hai bước là nguyên tử so với các lệnh khác.

Nhưng hãy xét:

```text
Redis Primary P: sequence = 41
Redis Replica R: sequence = 41

P cấp token 42 cho Worker B
B có thể đã gửi token 42 tới receiver

Trước khi dữ liệu mới đồng bộ sang R:
P gặp sự cố
R được promote thành primary
R vẫn có sequence = 41

R cấp lại token 42 cho Worker C
```

Token `42` đã bị **tái sử dụng**, nên không còn đảm bảo thứ tự đời lease. Một receiver sử dụng luật `token > lastAccepted` có thể từ chối một lease mới hợp lệ hoặc không phân biệt được các lease khác nhau.

Đây không phải vấn đề chỉ riêng script: Redis replication/failover có những đánh đổi về độ bền dữ liệu. Script nguyên tử trên primary **không đồng nghĩa sequence đã được commit bền vững trên một hệ thống đồng thuận**.

Nếu cấu hình Redis có eviction làm mất sequence key, nếu người vận hành xóa key hoặc khôi phục backup cũ, số đếm cũng có thể bị reset. TTL chỉ được đặt trên **lock key**; **không đặt TTL trên sequence key**.

### 11.2. WAIT có đủ biến token thành tuyệt đối an toàn không?

Redis có lệnh `WAIT` để đợi một số replica xác nhận đã tiếp nhận tiến độ replication của các write trước đó trên kết nối.

Tuy nhiên, chỉ dùng `WAIT` không biến Redis thành hệ thống đồng thuận tuyến tính hóa hoặc đảm bảo zero data loss cho mọi kiểu failover. Thêm `WAIT` cũng có các vấn đề về connection, độ trễ và cách diễn giải số replica đã xác nhận.

Với yêu cầu fencing nghiêm ngặt, **không mặc nhiên coi Redis `INCR` + `WAIT` là bằng chứng token không bao giờ bị lặp trong mọi sự cố**.

### 11.3. Những phương án cấp token mạnh hơn

Tùy hệ thống và mức độ yêu cầu, có thể cân nhắc:

- **Database sequence và transaction** dưới một cơ chế primary/failover có cam kết durability đủ mạnh.
- **Một bảng trạng thái quyền sở hữu đặt cùng database với tài nguyên**, cho phép cấp epoch và thay đổi tài nguyên trong cùng miền transaction.
- **Hệ thống điều phối dựa trên đồng thuận** với thứ tự cấp phiên bản rõ ràng, chẳng hạn một coordinator hỗ trợ thứ tự giao dịch/phiên bản phù hợp.
- **Phiên bản tại receiver** do chính receiver cấp và kiểm soát, để không phụ thuộc sequence chỉ nằm ở Redis.
- Một thiết kế **single writer** bền vững hoặc queue có cơ chế phân phối và idempotency phù hợp khi yêu cầu thực tế là không được thực hiện công việc trùng.

Một ví dụ cấp số thứ tự bằng PostgreSQL:

```sql
CREATE SEQUENCE fencing_sequence START WITH 1 INCREMENT BY 1;
```

Lấy số:

```sql
SELECT nextval('fencing_sequence');
```

Số sequence có thể có **khoảng trống** nếu một transaction bị rollback hoặc một lần cấp quyền không thành công; đó không phải vấn đề của fencing. Tuy vậy, sequence **cần được gắn vào một giao thức cấp lease thực sự**, không chỉ gọi `nextval` rồi tự tuyên bố có quyền thao tác.

Độ tin cậy của phương án database vẫn phụ thuộc kiến trúc database, replication, failover và cấu hình độ bền. Không có một dòng SQL nào tự giải quyết mọi sự cố hạ tầng.

## 12. Token và việc xác thực caller

Một receiver rất dễ gặp rủi ro nếu nhận trực tiếp request từ mọi client:

```http
POST /reports/report-42/result
X-Fencing-Token: 999999999
Content-Type: application/json

{"result":"malicious"}
```

Nếu receiver chỉ dùng:

```text
incomingToken > lastAcceptedToken
```

và cho phép ai cũng tự chọn token, một client có thể gửi số rất lớn để chặn những worker hợp lệ về sau.

Fencing token **không phải cơ chế xác thực**. Cần thiết kế:

- Service-to-service authentication (ví dụ mTLS hoặc token xác thực dịch vụ).
- Authorization theo resource, tenant và loại thao tác.
- Không cho caller tự phát hành một token bất kỳ ngoài giao thức cấp quyền.
- Receiver phải có cơ sở tin cậy rằng token thuộc một lease/epoch hợp lệ; có thể tích hợp việc cấp token ngay vào receiver hoặc xác minh từ coordinator đáng tin.
- Không dùng token đoán được như một bí mật.
- Ghi log/audit token, resource và quyết định accept/reject theo cách không lộ dữ liệu nhạy cảm.

Nếu sử dụng HMAC/chữ ký cho một capability token, nó giúp ngăn **giả mạo** nhưng **không tự giải quyết** vấn đề lease hết hạn hoặc token bị lặp khi nguồn cấp số mất tính nhất quán.

## 13. Idempotency và fencing bổ sung cho nhau

Hai tình huống khác nhau:

**Stale worker:**

```text
A token 41 -> đã mất quyền
B token 42 -> receiver đã nhận
A gửi lệnh cũ -> cần REJECT bằng fencing
```

**Retry cùng một thao tác:**

```text
B token 42 -> receiver đã ghi thành công
Kết nối lỗi trước khi B nhận response
B retry lại cùng operationId
```

Fencing token không tự biết một thao tác của cùng lease đã được áp dụng hay chưa. Nếu receiver chấp nhận token bằng nhau mà không kiểm soát operation ID, có thể gây double update.

Các cách phối hợp:

| Cơ chế | Mục đích |
|---|---|
| Fencing token | Phát hiện thế hệ lease đã lỗi thời |
| Operation ID | Nhận diện yêu cầu nghiệp vụ bị gửi lặp |
| Unique constraint / idempotency table | Ngăn thực hiện tác dụng phụ nhiều lần |
| Database transaction | Gộp cập nhật dữ liệu và lưu dấu operation |
| Timeout/retry policy | Kiểm soát lỗi mạng nhưng không tạo đúng-một-lần |
| Lock TTL / renew | Giới hạn thời gian giữ quyền theo Redis |

Nếu receiver chỉ cho phép **một write duy nhất mỗi lease** bằng điều kiện `incomingFence > lastFence`, một retry cùng token sẽ bị từ chối. Ứng dụng nên phân biệt “đã áp dụng thành công trước đó” và “đã bị từ chối vì stale”, nhất là khi cần trả kết quả ổn định sau lỗi mạng.

Nếu cần nhiều thao tác trong một lease, dùng epoch và operation ID như phần trên.

## 14. Một số tài nguyên không cho phép kiểm tra fencing trực tiếp

Một database hỗ trợ câu SQL có điều kiện rất thuận tiện. Nhưng không phải hệ thống nhận nào cũng hỗ trợ đồng thời **đọc token hiện hành và ghi tài nguyên** một cách nguyên tử.

Ví dụ:

- HTTP API bên ngoài không có trường phiên bản/ETag.
- Bộ nhớ lưu trữ đối tượng chỉ hỗ trợ PUT ghi đè không điều kiện.
- Một thiết bị điều khiển từ xa nhận lệnh trực tiếp.
- Dịch vụ SaaS không có cơ chế conditional update.

Khi tài nguyên không hiểu token, việc worker gửi:

```json
{"fencingToken": 42}
```

**không có tác dụng bảo vệ** nếu phía nhận bỏ qua trường đó.

### 14.1. Đặt một lớp gateway có kiểm soát

Một phương án là đưa mọi thao tác qua một service trung gian:

```text
Workers
   |
   | request(resourceId, token, payload)
   v
Fenced Resource Gateway
   |
   | Kiểm tra epoch + idempotency
   | Kiểm soát thứ tự giao tiếp
   v
External resource
```

Tuy vậy, **kiểm tra token ở gateway rồi gửi request không đồng bộ sang tài nguyên ngoài** lại tạo một cửa sổ TOCTOU nếu gateway không thể kiểm soát thứ tự/commit của thao tác ngoài.

Để có bảo đảm mạnh, gateway phải thực sự là nơi **tuần tự hóa tất cả tác dụng phụ** lên tài nguyên, hoặc tài nguyên ngoài phải hỗ trợ một primitive tương đương conditional write/version. Nếu không, gateway chỉ giảm rủi ro chứ không loại bỏ mọi race.

### 14.2. Dùng compare-and-swap hoặc conditional write nếu có

Một số tài nguyên cung cấp:

- `UPDATE ... WHERE version = ?` trong SQL.
- Conditional PUT với ETag/version.
- Compare-and-swap dựa trên revision.
- Một API cho phép truyền expected version và từ chối khi stale.

Khi hệ thống nhận đã có versioning đúng, có thể xây dựng giao thức fencing dựa trên đó thay vì cố dùng Redis lock như một bảo đảm độc lập.

**Nguyên tắc:** kiểm tra phải xảy ra tại điểm có quyền quyết định thao tác có được commit hay không.

## 15. Vấn đề khi nhiều worker và nhiều resource

### 15.1. Token được tăng theo resource hay toàn hệ thống?

Có hai lựa chọn:

**Per-resource sequence:**

```text
report-42:  1, 2, 3, ...
report-43:  1, 2, 3, ...
```

Phù hợp khi hai resource có vòng đời độc lập. Receiver lưu `lastFence` theo `resourceId`.

**Global sequence:**

```text
Report 42 -> token 101
Report 43 -> token 102
Report 42 -> token 103
```

Dễ so sánh theo thứ tự toàn hệ thống nếu coordinator có bảo đảm phù hợp, nhưng có thể làm tăng sự phụ thuộc vào một nguồn phát hành chung.

**Không cần token của resource A so sánh được với token của resource B** nếu chúng không bao giờ cạnh tranh trên cùng tài nguyên. Điều bắt buộc là **mọi actor tranh quyền trên cùng miền bảo vệ** phải dùng chung một thứ tự fencing được tin cậy.

### 15.2. Một thao tác ghi ảnh hưởng nhiều resource

Giả sử một worker cần cập nhật cả:

```text
report-42
report-summary
```

Nếu mỗi resource dùng sequence riêng, việc sở hữu lock `report-42` không tự cấp quyền sửa `report-summary`.

Cần quyết định một trong các hướng:

- Cùng một miền khóa/fence bao phủ cả hai tài nguyên, receiver kiểm tra nguyên tử.
- Transaction đảm bảo cập nhật nhất quán nhiều bản ghi.
- Một giao thức phân tán phù hợp với nhiều hệ thống nếu không có transaction chung.
- Tránh thiết kế nhiều resource bị cập nhật trong khi chỉ bảo vệ một khóa.

Không nên tự mở rộng ý nghĩa của một fencing token sang resource không được thiết kế để sử dụng token đó.

### 15.3. Thời hạn lease và workload kéo dài

Nếu tác vụ thường mất 30 giây nhưng TTL chỉ 5 giây, worker hay mất quyền. Nếu TTL 30 phút, worker chết khiến các worker khác chờ lâu hơn.

Cần chọn TTL dựa trên:

- Thời gian tác vụ bình thường và ở đuôi phân bố.
- Khả năng renew với ownership check.
- Thời gian phát hiện worker bị dừng.
- Mức độ an toàn khi lease mất hiệu lực.
- Các lệnh đã gửi nhưng chưa nhận kết quả.
- Khả năng receiver chặn stale requests.

TTL là tham số vận hành; **không có TTL “an toàn tuyệt đối”** vì pause, partition và latency có thể vượt bất kỳ ước lượng nào.

## 16. Hướng xử lý lỗi và quan sát hệ thống

### 16.1. Các trường hợp lỗi quan trọng

| Tình huống | Điều gì có thể xảy ra | Cách ứng dụng nên phản ứng |
|---|---|---|
| Không lấy được khóa | Worker khác còn lease | Không thực hiện ghi; chờ/retry có giới hạn |
| Xin khóa timeout, không nhận kết quả | Redis có thể đã cấp lease | Không tự khẳng định thất bại; xác minh hoặc đợi hết TTL theo giao thức |
| Worker pause vượt TTL | Lease có thể đã chuyển chủ | Không tin rằng mình còn quyền; receiver phải fencing |
| Release trả 0 | Khóa không còn hoặc owner đã đổi | Không xóa khóa mới; ghi nhận trạng thái |
| Renew thất bại | Mất hoặc không xác minh được lease | Dừng phát thao tác mới, receiver vẫn chặn thao tác cũ |
| Receiver từ chối token | Stale/duplicate/invalid resource | Không retry mù quáng bằng token cũ |
| Receiver nhận token nhưng response mất | Có thể đã ghi thành công | Kiểm tra operation ID, idempotency/status |
| Redis failover mất sequence | Token có thể tái sử dụng | Không xem Redis counter là nguồn fencing mạnh |
| Receiver restart mất lastFence | Có thể chấp nhận token cũ | Lưu mốc fencing bền vững ở receiver |
| External system không hiểu token | Ghi cũ vẫn có thể ghi đè | Đổi giao thức/cơ chế bảo vệ tại điểm commit |

### 16.2. Logging và metrics

Nên theo dõi:

- Số lần thử acquire, số lần thành công/thất bại.
- Độ dài lease, số lần renew thành công/thất bại.
- Số release hợp lệ và release không còn owner.
- Fencing token theo resource ở mức log có kiểm soát.
- Số thao tác bị receiver từ chối do stale token.
- Số thao tác bị từ chối do duplicate operation ID.
- Độ trễ từ lúc cấp lease tới lúc receiver chấp nhận thao tác.
- Thời gian xử lý của worker so với TTL.
- Redis reconnect/failover, độ trễ replication, lỗi cấp token.
- Database transaction conflicts và conditional update failures.

Ví dụ log có cấu trúc:

```text
event=lease_acquired resource=report-42 owner=worker-B token=42 ttlMs=10000
event=write_accepted resource=report-42 token=42 operation=op-550
event=write_rejected resource=report-42 token=41 reason=stale_fence
event=lease_release_failed resource=report-42 token=41 reason=not_current_owner
```

Không nên thêm `resourceId` không giới hạn vào nhãn metrics độ phân giải cao vì có thể tạo cardinality rất lớn. Thường nên dùng tên nghiệp vụ/loại resource làm tag metric và đưa ID cụ thể vào log hoặc trace có kiểm soát.

## 17. Thực hành Redis CLI: xem token và lease

Thực hành này cần Redis dành cho phát triển; không thử với các khóa khóa nghiệp vụ thật.

### Bước 1. Tạo script cấp lease

Trong Lua:

```lua
if redis.call('EXISTS', KEYS[1]) == 1 then
    return nil
end

local token = redis.call('INCR', KEYS[2])
redis.call('PSETEX', KEYS[1], ARGV[1], ARGV[2] .. ':' .. tostring(token))
return token
```

Có thể gửi qua `EVAL`:

```redis
EVAL "if redis.call('EXISTS',KEYS[1])==1 then return nil end local t=redis.call('INCR',KEYS[2]) redis.call('PSETEX',KEYS[1],ARGV[1],ARGV[2]..':'..tostring(t)) return t" 2 guard:{demo-42}:lock guard:{demo-42}:sequence 3000 worker-A
```

Nếu khóa chưa tồn tại và sequence ban đầu là 0, Redis trả token `1`.

### Bước 2. Kiểm tra khóa và sequence

```redis
GET guard:{demo-42}:lock
GET guard:{demo-42}:sequence
PTTL guard:{demo-42}:lock
```

Kỳ vọng:

```text
lock value: worker-A:1
sequence:   1
TTL:        giảm theo thời gian
```

### Bước 3. Thử giành khóa khi lease còn hiệu lực

Chạy lại script với owner `worker-B` trước khi TTL hết hạn:

```redis
EVAL "if redis.call('EXISTS',KEYS[1])==1 then return nil end local t=redis.call('INCR',KEYS[2]) redis.call('PSETEX',KEYS[1],ARGV[1],ARGV[2]..':'..tostring(t)) return t" 2 guard:{demo-42}:lock guard:{demo-42}:sequence 3000 worker-B
```

Khi lease A còn tồn tại, script không cấp token mới. Nếu đã hết TTL, script có thể cấp token mới.

### Bước 4. Đợi hết hạn rồi lấy token mới

Sau khi TTL đã hết:

```redis
GET guard:{demo-42}:lock
GET guard:{demo-42}:sequence
```

Xin lease bằng worker B sẽ trả token tiếp theo:

```text
Worker A -> token 1
Worker B -> token 2
```

### Bước 5. Thử release của owner cũ

Khi B đang giữ lock, dùng script release với owner A:

```redis
EVAL "if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0" 1 guard:{demo-42}:lock worker-A:1
```

Kết quả phải là `0` khi lock hiện tại thuộc B. Kiểm tra lại:

```redis
GET guard:{demo-42}:lock
```

Khóa B vẫn tồn tại.

### Bước 6. Thử receiver với token cũ và mới

Khởi tạo bảng `protected_report` ở database thử nghiệm và áp dụng lệnh SQL có điều kiện:

```sql
UPDATE protected_report
SET result_text = 'new from B',
    last_fence = 2
WHERE report_id = 'report-42'
  AND last_fence < 2;
```

Sau đó thử worker A:

```sql
UPDATE protected_report
SET result_text = 'old from A',
    last_fence = 1
WHERE report_id = 'report-42'
  AND last_fence < 1;
```

Lệnh thứ hai không cập nhật dòng nào nếu token 2 đã được lưu. Qua đó chứng minh chính **receiver** ngăn stale write, không phải chỉ Redis lock.

### Bước 7. Dọn dữ liệu thử nghiệm

Nếu không cần dữ liệu nữa:

```redis
DEL guard:{demo-42}:lock
DEL guard:{demo-42}:sequence
```

**Chỉ xóa sequence của namespace demo**, tuyệt đối không áp dụng việc reset sequence tương tự với resource production đang được fencing. Reset sequence có thể tái sử dụng token và phá vỡ tính an toàn của giao thức.

## 18. Các lỗi thiết kế phổ biến

### Lỗi 1: Nghĩ TTL đã chặn worker cũ

TTL khiến Redis cho phép owner mới lấy khóa; nó không thể dừng worker cũ sau pause. Stale worker vẫn có thể gửi lệnh đã chuẩn bị.

### Lỗi 2: Dùng UUID ngẫu nhiên làm fencing token

UUID phân biệt owner nhưng không cung cấp thứ tự đời lease. Receiver không biết owner nào cũ hơn chỉ từ hai UUID ngẫu nhiên.

### Lỗi 3: Chỉ kiểm tra owner tại Redis

Dù compare-and-delete release đúng, hệ thống nhận thao tác ngoài Redis có thể vẫn cho worker cũ ghi đè dữ liệu.

### Lỗi 4: Gửi token nhưng receiver bỏ qua

Một trường `fencingToken` trong request không đủ. Receiver phải kiểm tra và thay đổi tài nguyên **nguyên tử** theo quy tắc tương ứng.

### Lỗi 5: SELECT token rồi UPDATE riêng biệt

Hai request có thể xen kẽ và tạo race condition. Sử dụng atomic conditional update, CAS hoặc transaction với locking phù hợp.

### Lỗi 6: Đặt TTL trên sequence key

Khi sequence hết hạn và số đếm reset, token có thể bị tái sử dụng. Tính đơn điệu cần một nguồn cấp số không bị reset theo quy tắc nghiệp vụ.

### Lỗi 7: Coi INCR trên Redis có failover là thứ tự bất biến

Replication bất đồng bộ có thể làm mất tiến độ sequence trong failover. Nếu yêu cầu nghiêm ngặt, nguồn cấp token cần có cam kết durability/consensus mạnh hơn.

### Lỗi 8: Coi lastAcceptedFence luôn xác minh lease hiện tại

Receiver chỉ biết token lớn nhất **đã được nhận**. Nếu lease mới được cấp nhưng chưa đăng ký ở receiver, stale owner vẫn có thể vượt kiểm tra high-water mark cũ.

### Lỗi 9: Dùng điều kiện nhỏ hơn nghiêm ngặt rồi muốn ghi nhiều lần trong cùng lease

Điều kiện `lastFence < incomingFence` từ chối các thao tác tiếp theo có cùng token. Cần giao thức epoch + operation ID, không sửa điều kiện một cách ngẫu nhiên.

### Lỗi 10: Không xác thực caller và nguồn token

Một client có thể gửi token rất lớn để phá trạng thái nếu receiver chỉ kiểm tra số. Token cần gắn với giao thức cấp quyền và quyền truy cập.

### Lỗi 11: Retry một lệnh ghi sau timeout mà không có idempotency

Lệnh có thể đã thành công, nhưng response bị mất. Retry có thể tạo tác dụng phụ lặp hoặc bị nhầm là stale. Dùng operation ID và trạng thái nghiệp vụ.

### Lỗi 12: Chỉ bảo vệ Redis key, không bảo vệ tài nguyên phụ

Một worker ghi đồng thời database và object storage có thể yêu cầu fencing trên cả hai nơi hoặc một giao thức đồng bộ chung. Lock một resource không tự cấp quyền ghi resource khác.

### Lỗi 13: Không có đường xử lý khi lease hết hạn trước lúc job kết thúc

Worker cần biết cách dừng, renew hoặc trả kết quả rejected. Không gửi thêm thao tác dù đã phát hiện mất quyền.

### Lỗi 14: Dùng gateway kiểm tra token rồi gọi API bên ngoài không điều kiện

Nếu gateway không thể tuần tự hóa và kiểm soát commit ở dịch vụ ngoài, vẫn có cửa sổ race sau khi kiểm tra. Fencing cần được áp dụng tại điểm thật sự có hiệu lực.

### Lỗi 15: Chỉ nhìn số lần lấy khóa thành công

Một hệ thống có thể có lock acquire tốt nhưng vẫn gặp stale writes. Cần quan sát receiver reject count, token, idempotency và hành vi sau pause/failover.

## 19. Chọn chiến lược theo mức độ quan trọng

| Yêu cầu | Thiết kế đáng cân nhắc |
|---|---|
| Tránh hai job không quan trọng chạy trùng phần lớn thời gian | Redis lease với unique owner + TTL có thể đủ nếu xử lý trùng an toàn |
| Job chạy lâu, có thể pause | Lease + renew có ownership check và giới hạn thời gian |
| Job ghi đè một resource có version | Fencing token + conditional update tại receiver |
| Nhiều bước ghi trong một lease | Receiver quản lý current epoch + operation IDs |
| Tài nguyên không hỗ trợ conditional write | Gateway thực sự tuần tự hóa thao tác hoặc đổi API/tài nguyên |
| Không được chấp nhận stale owner sau lease mới | Nguồn cấp epoch/lease nhất quán mạnh và receiver tham gia giao thức |
| Không được phép mất hoặc lặp token khi failover | Nguồn cấp token bền vững với failover có cam kết phù hợp |
| Tác vụ tài chính hoặc thao tác không được lặp | Fencing kết hợp transaction, idempotency và kiểm soát durability |

**Không có một cấu hình Redis duy nhất bảo đảm mọi hệ thống nhận đều an toàn.** Redis có thể tham gia khóa và phát số thứ tự, nhưng tính đúng đắn cuối cùng tùy thuộc việc **resource server kiểm soát quyền thao tác ra sao**.

## 20. Câu hỏi tự kiểm tra

**1. Redis lock có TTL 10 giây, worker bị pause 30 giây. Worker có tự bị chặn không?**

Không. Redis cho phép owner mới lấy khóa khi TTL hết, nhưng worker cũ vẫn có thể tỉnh lại và gửi thao tác. Receiver cần kiểm soát stale request.

**2. UUID owner ID khác fencing token ở đâu?**

UUID nhận diện ai đang giữ khóa; fencing token có thứ tự tăng đơn điệu giúp phân biệt đời lease cũ và mới.

**3. Vì sao cần kiểm tra token tại hệ thống nhận?**

Vì hệ thống nhận mới là nơi thay đổi tài nguyên. Kiểm tra Redis trước khi gửi có thể lỗi thời trước lúc request thực sự được xử lý.

**4. `XACK` trong Redis Streams có giống fencing token không?**

Không. `XACK` xác nhận xử lý entry trong consumer group; fencing token dùng để chặn lệnh của lease/epoch lỗi thời tại tài nguyên nhận.

**5. Nếu B token 42 đã được receiver chấp nhận, A token 41 đến sau sẽ ra sao?**

Với một conditional update đúng, receiver từ chối A vì token 41 thấp hơn mốc 42.

**6. Nếu B đã lấy token 42 ở Redis nhưng chưa bao giờ gửi nó tới receiver, luật lastAcceptedFence có tự biết B là owner mới không?**

Không. Nếu receiver còn mốc 40, request A với 41 vẫn có thể qua điều kiện. Muốn bảo đảm mạnh hơn cần đăng ký/quản lý epoch tại receiver hoặc kiểm tra quyền với nguồn điều phối phù hợp.

**7. Vì sao không đặt TTL cho sequence key?**

Vì số đếm có thể reset sau khi khóa hết hạn, dẫn tới token mới bị trùng hoặc nhỏ hơn token cũ.

**8. INCR chạy nguyên tử trên Redis primary có đủ bảo đảm fencing qua mọi failover không?**

Không. Replication bất đồng bộ có thể làm mất tiến độ bộ đếm khi replica được promote, khiến token bị tái sử dụng.

**9. Receiver dùng điều kiện `incomingFence > lastFence` có phù hợp với nhiều write trong cùng một lease không?**

Không tự phù hợp. Sau write đầu, token bằng lastFence; các write tiếp theo bị từ chối. Cần giao thức epoch + operation ID/sequence hoặc quy tắc nhận khác có kiểm soát.

**10. Nếu gọi HTTP API ngoài không hỗ trợ conditional write, chỉ thêm token vào header có đủ không?**

Không. API ngoài phải kiểm tra token hoặc một gateway thực sự kiểm soát việc tuần tự hóa/commit của các thao tác lên tài nguyên.

**11. Lỗi mạng sau ghi thành công nhưng trước khi worker nhận response cần làm gì?**

Không retry mù quáng. Dùng operation ID, trạng thái xử lý bền vững và idempotency để xác minh hoặc thực hiện lại an toàn.

**12. Vì sao release khóa bằng GET rồi DEL trong hai lệnh là không an toàn?**

Vì khóa có thể hết hạn và đổi owner giữa GET và DEL. Cần compare-and-delete trong Lua script hoặc primitive nguyên tử tương đương.

## 21. Ghi nhớ

- **Distributed lock có TTL không tự ngăn stale worker.** Một tiến trình bị pause hoặc request bị trễ vẫn có thể tác động lên tài nguyên sau khi lease đã hết hạn.
- **Fencing token** biểu thị thứ tự lease bằng số tăng đơn điệu; receiver phải **so sánh token tại điểm ghi** và lưu mốc đủ bền vững.
- **Owner ID và fencing token khác nhau:** owner ID dùng cho ownership/release, fencing token dùng để chặn thế hệ quyền cũ.
- **Redis Lua** có thể nguyên tử hóa `EXISTS` + `INCR` + `PSETEX` trên một primary, nhưng **không biến replication bất đồng bộ thành bảo đảm fencing xuyên failover**.
- **Atomic conditional update** tại receiver là điều kiện cần. Không kiểm tra bằng `SELECT` rồi mới `UPDATE` mà thiếu cơ chế đồng bộ.
- **High-water mark chỉ biết token đã được receiver nhìn thấy.** Nếu cần chặn stale owner ngay khi quyền mới được cấp, receiver phải tham gia giao thức epoch/lease mạnh hơn.
- **Fencing không thay thế authentication, idempotency hay transaction.** Tài nguyên nhận phải xác minh quyền, chặn retry trùng và kiểm soát những thao tác có tác dụng phụ.
- **Không có bảo đảm nếu receiver bỏ qua token.** Phải thiết kế bảo vệ tại đúng nơi thay đổi tài nguyên.

### Tài liệu tham khảo

- [Redis — Distributed Locks](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/).
- [Redis — SET](https://redis.io/docs/latest/commands/set/).
- [Redis — INCR](https://redis.io/docs/latest/commands/incr/).
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/).
- [Redis — WAIT](https://redis.io/docs/latest/commands/wait/).
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).
