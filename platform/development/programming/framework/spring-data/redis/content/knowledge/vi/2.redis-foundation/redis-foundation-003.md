# Tính nguyên tử của một lệnh và giới hạn của chuỗi nhiều lệnh

## 1. Vì sao cần phân biệt một lệnh với nhiều lệnh?

Redis thường được dùng cho bộ đếm, tồn kho, phiên đăng nhập, giới hạn tần suất và cơ chế phối hợp giữa nhiều tiến trình. Trong những tình huống này, nhiều request có thể cùng đọc và sửa một dữ liệu gần như đồng thời. Nếu không xác định đúng **ranh giới nguyên tử (atomicity boundary)**, ứng dụng dễ mất cập nhật, vượt giới hạn hoặc ghi ra trạng thái không hợp lệ.

Điểm cốt lõi là:

> Trên một Redis server thực thi lệnh, một lệnh Redis thông thường được thực hiện như một đơn vị không bị lệnh của client khác chen vào giữa. Nhưng một chuỗi gồm nhiều lệnh riêng lẻ **không tự động** trở thành một đơn vị nguyên tử.

Ví dụ, **INCR counter** là một lệnh tăng bộ đếm nguyên tử. Trong khi đó, chuỗi **GET counter**, tính toán trong Java rồi **SET counter newValue** gồm nhiều bước; request khác có thể chạy giữa các bước này.

Đây là kiến thức nền tảng trước khi sử dụng **RedisTemplate**, **StringRedisTemplate**, **MULTI/EXEC**, **WATCH** hoặc Lua script trong Spring Data Redis.

## 2. Nguyên tử của một lệnh Redis nghĩa là gì?

Một thao tác nguyên tử có kết quả quan sát được như một lần chuyển trạng thái duy nhất: client khác thấy trạng thái trước hoặc sau lệnh, không thấy các bước nội bộ chưa hoàn tất của lệnh ấy. Trong mô hình thực thi lệnh thông thường của một Redis instance, lệnh của các client được xử lý theo thứ tự; Redis không xen một lệnh khác vào giữa lúc một lệnh đang thay đổi dữ liệu.

Ví dụ:

~~~redis
SET visits 10
INCR visits
GET visits
~~~

Sau **INCR**, giá trị là **11**. Nếu hai client cùng gửi **INCR visits** khi giá trị ban đầu là **10**, mỗi lệnh tăng sẽ được Redis xử lý trọn vẹn; kết quả cuối cùng là **12**, dù hai request đến gần như cùng lúc.

Một số lệnh có ích vì kết hợp được nhiều bước nghiệp vụ nhỏ trong **một lần thực thi phía Redis**:

| Lệnh | Thao tác nguyên tử trong một lệnh | Lưu ý |
|---|---|---|
| **INCR / INCRBY / DECRBY** | Thay đổi bộ đếm số nguyên | Không tự kiểm tra ngưỡng nghiệp vụ phức tạp. |
| **HINCRBY** | Tăng trường số nguyên trong hash | Phạm vi là trường của hash được chỉ định. |
| **SADD** | Thêm phần tử vào set | Kiểm tra trùng lặp và thêm diễn ra trong cùng lệnh. |
| **LPUSH / RPUSH** | Đẩy phần tử vào list | Không bảo đảm nguyên tử cho các lệnh xử lý tiếp theo. |
| **SET key value NX EX seconds** | Chỉ ghi nếu key chưa tồn tại, đồng thời gắn thời hạn | Tránh khoảng hở giữa đặt key và đặt TTL. |
| **MSET** | Ghi nhiều key bằng một lệnh trên một instance | Trong Redis Cluster, các key phải thỏa điều kiện cùng hash slot. |

Chữ **nguyên tử** ở đây nói về **ranh giới thực thi và tính cô lập của lệnh trên Redis**, không mặc nhiên nói rằng dữ liệu đã được ghi bền vững xuống đĩa, đã được replica xác nhận hay đã giao dịch đồng thời với cơ sở dữ liệu SQL.

### Phạm vi cần xác định

- **Một Redis instance**: tính nguyên tử của lệnh được hiểu trong phạm vi instance xử lý các key liên quan.
- **Redis Cluster**: dữ liệu phân bố trên nhiều master; không có lời hứa về một giao dịch nguyên tử tùy ý trải qua nhiều hash slot/master. Các lệnh nhiều key, script và transaction phải tuân thủ quy tắc key slot tương ứng.
- **Ứng dụng nhiều tầng**: một lệnh Redis không bao trùm các thay đổi trong PostgreSQL, Kafka, HTTP API hoặc hệ thống khác.

Redis có thể dùng nhiều luồng cho một số tác vụ I/O, nhưng điều đó không biến mỗi thao tác trên cấu trúc dữ liệu thành một chuỗi lệnh ứng dụng được khóa tự động. Điều quan trọng khi thiết kế vẫn là **lệnh nào được Redis thực thi như một đơn vị**.

## 3. Vì sao GET rồi SET có thể mất cập nhật?

Giả sử **counter = 10**. Hai request A và B cùng chạy logic:

~~~java
String current = redis.opsForValue().get("counter");
long next = Long.parseLong(current) + 1;
redis.opsForValue().set("counter", Long.toString(next));
~~~

Mỗi lần **GET** và **SET** riêng lẻ vẫn là lệnh nguyên tử. Tuy nhiên Redis hoàn toàn có thể nhận lệnh theo thứ tự:

| Thời điểm | Request A | Request B | Giá trị trong Redis |
|---|---|---|---|
| 1 | GET → 10 | | 10 |
| 2 | | GET → 10 | 10 |
| 3 | Tính 10 + 1 | | 10 |
| 4 | | Tính 10 + 1 | 10 |
| 5 | SET 11 | | 11 |
| 6 | | SET 11 | 11 |

Hai request đã yêu cầu tăng, nhưng kết quả chỉ tăng một lần. Đây là **lost update** (mất cập nhật). Một Redis connection duy nhất cho mỗi request, thứ tự câu lệnh trong source code hay việc gửi lệnh rất nhanh đều không loại bỏ khả năng xen kẽ này.

Nếu mục tiêu chỉ là tăng bộ đếm, hãy dùng **INCR**:

~~~redis
SET counter 10
INCR counter
INCR counter
GET counter
~~~

Kết quả là **12**. Mỗi **INCR** tự đọc, tính và ghi như một lệnh Redis; ứng dụng không cần thực hiện ba bước ở phía Java.

### Atomic command chưa chắc đủ cho quy tắc nghiệp vụ

Giả sử tồn kho là **5** và hai đơn hàng cùng muốn mua **3** sản phẩm. Việc mỗi request gọi **DECRBY stock 3** là nguyên tử đối với phép trừ, nhưng nếu cả hai được phép trừ thì tồn kho có thể thành **-1**. Quy tắc thật sự là:

> Chỉ trừ tồn kho **nếu** số lượng hiện có đủ, và việc kiểm tra với việc trừ phải ở cùng một ranh giới nguyên tử.

Chuỗi **GET stock** → kiểm tra trong Java → **DECRBY stock 3** không đạt yêu cầu đó. Hai request đều có thể đọc tồn kho **5**, đều cho rằng đủ hàng, rồi lần lượt trừ.

Các lỗi tương tự thường gặp:

- **EXISTS key** rồi **SET key** để tự tạo một khóa duy nhất: hai client có thể đều quan sát key chưa tồn tại.
- **SETNX lock value** rồi **EXPIRE lock 30**: nếu client dừng giữa hai lệnh, khóa có thể tồn tại không có TTL.
- **GET balance**, so sánh số dư, rồi **DECRBY balance amount**: hai request có thể đều vượt qua bước kiểm tra trên dữ liệu cũ.
- **GET** rồi **DEL** để lấy và xóa một giá trị: cần xem có lệnh nguyên tử phù hợp như **GETDEL** hay không.

Nguyên tắc chọn giải pháp: ưu tiên một lệnh Redis đã diễn đạt trọn vẹn điều kiện và thay đổi, chẳng hạn **SET ... NX EX** cho thao tác tạo key có TTL; nếu không có lệnh đơn phù hợp thì cân nhắc transaction với **WATCH** hoặc Lua script/Redis Function.

## 4. MULTI/EXEC: nhóm lệnh không bị chen ngang, nhưng không tự rollback

Redis cung cấp **MULTI** để bắt đầu xếp hàng lệnh và **EXEC** để thực thi các lệnh đã xếp hàng:

~~~redis
MULTI
INCR stats:orders
HINCRBY stats:region hcm 1
EXEC
~~~

Giữa lúc Redis đang thực thi danh sách lệnh của **EXEC**, các lệnh từ client khác không chen vào giữa. Client khác cũng không quan sát được một trạng thái trung gian bằng cách gửi lệnh đọc xen vào quá trình thực thi **EXEC**.

Tuy nhiên cần hiểu đúng giới hạn:

1. **MULTI** bắt đầu hàng đợi; lệnh được xếp hàng thường trả lời **QUEUED**, chưa trả kết quả thực thi để ứng dụng dùng ra quyết định ngay trong transaction.
2. **EXEC** thực thi các lệnh trong hàng đợi theo thứ tự, không bị lệnh của client khác xen vào.
3. **Redis không rollback các lệnh đã thành công nếu một lệnh sau đó lỗi lúc thực thi.** Những lệnh tiếp theo vẫn có thể được thực hiện. Vì vậy không được xem **MULTI/EXEC** như giao dịch SQL có rollback tự động.
4. Lỗi phát hiện trong lúc xếp hàng có thể khiến transaction bị từ chối khi **EXEC**; cần phân biệt lỗi xếp hàng với lỗi chỉ phát sinh lúc thực thi.
5. **DISCARD** hủy các lệnh đang xếp hàng trước **EXEC**; không dùng để đảo ngược một **EXEC** đã chạy.

Ví dụ minh họa trường hợp lỗi khi thực thi:

~~~redis
SET stats:total not-a-number
MULTI
INCR stats:total
SET audit:last-run completed
EXEC
~~~

**INCR** gặp lỗi vì giá trị không phải số nguyên, còn lệnh **SET audit:last-run completed** vẫn có thể thành công. Do đó điều kiện “hoặc tất cả thay đổi thành công hoặc không thay đổi gì” **không được bảo đảm chỉ bằng MULTI/EXEC**.

Nếu nghiệp vụ phải đọc trạng thái rồi mới quyết định ghi, **MULTI/EXEC đơn thuần** cũng không giải quyết được: việc **GET** trước **MULTI** vẫn có khoảng hở, còn **GET** được xếp hàng bên trong **MULTI** thì không cho ứng dụng sử dụng kết quả ngay trước **EXEC**.

## 5. WATCH: kiểm tra xung đột khi cần đọc trước, ghi sau

**WATCH** cung cấp cơ chế đồng bộ lạc quan (optimistic locking). Client theo dõi một hoặc nhiều key trước khi đọc; nếu key đã bị thay đổi trước thời điểm **EXEC**, transaction bị hủy thay vì thực thi trên giả định dữ liệu cũ.

Ví dụ quy trình dự trữ **3** sản phẩm khi **stock:{sku42}** đang là **5**:

**Client A:**

~~~redis
WATCH stock:{sku42}
GET stock:{sku42}
~~~

Ứng dụng nhận **5**, kiểm tra **5 >= 3**, sau đó chuẩn bị:

~~~redis
MULTI
DECRBY stock:{sku42} 3
EXEC
~~~

Nếu **Client B** đã sửa **stock:{sku42}** sau **WATCH** nhưng trước **EXEC** của A, **EXEC** của A trả kết quả hủy transaction (nil/null tùy client) và không chạy lệnh trừ trong hàng đợi. A phải đọc lại và thử lại nếu nghiệp vụ cho phép, với số lần thử và thời hạn hợp lý.

Nếu đọc được số lượng không đủ, ứng dụng có thể **UNWATCH** và trả kết quả hết hàng mà không mở transaction.

Những lưu ý thực tế:

- **WATCH** cần diễn ra **trước** **MULTI**; key được giám sát phải bao phủ dữ liệu làm căn cứ cho quyết định.
- Việc theo dõi và thực thi transaction cần được giữ trong **cùng một phiên kết nối Redis thích hợp**; tách tùy tiện qua các lời gọi template có thể dùng connection khác.
- Xung đột là tình huống bình thường khi tải cao. Cần giới hạn retry, xử lý kết quả hủy và tránh retry vô hạn.
- **WATCH** giải quyết việc dữ liệu bị đổi giữa đọc và ghi, nhưng vẫn không cung cấp rollback cho lỗi thực thi bên trong transaction.

## 6. Lua script: đưa điều kiện và cập nhật vào một lần thực thi

Khi một điều kiện nghiệp vụ cần nhiều lệnh Redis, script Lua có thể chuyển logic **đọc → kiểm tra → cập nhật** sang server để thực thi liên tiếp mà không bị client khác chen vào.

Ví dụ chỉ trừ tồn kho nếu đủ sản phẩm:

~~~lua
-- KEYS[1]: key tồn kho, ví dụ stock:{sku42}
-- ARGV[1]: số lượng cần mua
local quantity = tonumber(ARGV[1])
if not quantity or quantity <= 0 or quantity ~= math.floor(quantity) then
    return redis.error_reply('quantity must be a positive integer')
end

local available = tonumber(redis.call('GET', KEYS[1]) or '0')
if not available then
    return redis.error_reply('stock must be numeric')
end
if available < quantity then
    return 0
end

redis.call('DECRBY', KEYS[1], quantity)
return 1
~~~

Ý nghĩa kết quả:

| Kết quả | Diễn giải |
|---|---|
| **1** | Đủ hàng, Redis đã trừ số lượng yêu cầu. |
| **0** | Không đủ hàng, không thực hiện phép trừ. |
| **Error** | Đầu vào hoặc dữ liệu không hợp lệ; ứng dụng phải xử lý lỗi. |

Vì bước kiểm tra và **DECRBY** đều nằm trong một script, hai request không thể cùng vượt qua kiểm tra trên cùng một giá trị tồn kho cũ. Redis sẽ hoàn thành script của request thứ nhất trước khi thực thi script của request thứ hai trên instance đó.

Điều này có giới hạn quan trọng:

- Script thực thi nguyên tử về mặt **không bị chen lệnh**; **không có rollback tự động** nếu script đã ghi dữ liệu rồi gặp lỗi sau đó. Nên kiểm tra dữ liệu và điều kiện **trước các lệnh ghi** khi có thể.
- Script chạy quá lâu sẽ cản trở những lệnh khác trên Redis instance. Tránh vòng lặp lớn, tác vụ nặng hoặc coi Redis là nơi chạy nghiệp vụ kéo dài.
- Với **Redis Cluster**, các key truy cập trong một script phải tuân thủ quy tắc cùng hash slot; các key phải được khai báo và truyền đúng qua **KEYS**, không tạo tên key tùy tiện từ dữ liệu runtime.
- Redis Function cũng cho phép đặt logic chạy phía Redis, với cùng yêu cầu suy nghĩ rõ ranh giới thực thi, giới hạn tài nguyên và key slot.

## 7. Áp dụng trong Spring Data Redis

### 7.1. Ưu tiên API ánh xạ tới một lệnh nguyên tử

Với **StringRedisTemplate**, bộ đếm có thể viết:

~~~java
// redis là StringRedisTemplate được Spring inject.
Long count = redis.opsForValue().increment("metrics:views");
~~~

**increment** gửi thao tác tăng phía Redis; hai request không phải tự phối hợp **GET** rồi **SET**. Khi cần tạo một key **nếu chưa tồn tại** và gắn TTL ngay trong cùng thao tác:

~~~java
Boolean acquired = redis.opsForValue().setIfAbsent(
    "job:lease:42",
    "worker-7",
    java.time.Duration.ofSeconds(30)
);

if (Boolean.TRUE.equals(acquired)) {
    // Client này đã tạo key thành công.
}
~~~

Về mặt ý nghĩa, thao tác này tương ứng với **SET key value NX** kèm thời hạn trong cùng một lệnh Redis. Nó phù hợp để minh họa việc loại bỏ khoảng hở **SETNX** rồi **EXPIRE**. Nếu dùng cho distributed lock thật, còn phải xét token chủ sở hữu, thời hạn hết lease, giải phóng có điều kiện và tác vụ vượt quá TTL; chỉ tạo key thành công không bảo đảm toàn bộ quy trình nghiệp vụ an toàn.

### 7.2. Gọi Lua qua RedisTemplate

Spring Data Redis hỗ trợ **RedisScript** để thực thi script bằng template. Ví dụ dùng chính logic dự trữ tồn kho ở trên:

~~~java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

DefaultRedisScript<Long> reserveScript = new DefaultRedisScript<>();
reserveScript.setResultType(Long.class);
reserveScript.setScriptText("""
    local quantity = tonumber(ARGV[1])
    if not quantity or quantity <= 0 or quantity ~= math.floor(quantity) then
        return redis.error_reply('invalid quantity')
    end
    local available = tonumber(redis.call('GET', KEYS[1]) or '0')
    if not available then
        return redis.error_reply('invalid stock')
    end
    if available < quantity then
        return 0
    end
    redis.call('DECRBY', KEYS[1], quantity)
    return 1
    """);

// stringRedisTemplate là bean được inject.
Long reserved = stringRedisTemplate.execute(
    reserveScript,
    List.of("stock:{sku42}"),
    "3"
);

if (Long.valueOf(1L).equals(reserved)) {
    // Dự trữ thành công.
} else if (Long.valueOf(0L).equals(reserved)) {
    // Không đủ hàng.
}
~~~

Trong ví dụ này **stock:{sku42}** là tên key; dấu ngoặc nhọn cũng giúp tạo hash tag để phối hợp nhiều key liên quan cùng slot khi sử dụng Redis Cluster. Ứng dụng vẫn phải xử lý lỗi Redis, timeout và trường hợp không nhận được phản hồi.

### 7.3. Khi dùng transaction trong Spring Data Redis

Để chạy **MULTI/EXEC** theo một phiên kết nối, Spring Data Redis có **SessionCallback** cho các thao tác cùng một session. Khi cần **WATCH**, phần đọc, **MULTI** và **EXEC** phải nằm trong cùng ngữ cảnh kết nối phù hợp. Không nên giả định rằng việc lần lượt gọi **redisTemplate.watch(...)**, đọc, rồi gọi **multi()/exec()** từ các đoạn code rời rạc luôn dùng cùng connection.

Khi transaction đang xếp hàng, một số API template trả về giá trị rỗng/null cho câu lệnh được queue; kết quả thực thi thực tế phải lấy sau **EXEC**. **EXEC** có thể trả null khi **WATCH** phát hiện xung đột. Ứng dụng cần phân biệt việc transaction bị hủy với kết quả thực thi thành công.

Đừng nhầm các cơ chế thường gặp:

| Cơ chế | Bảo đảm chính | Điều không được bảo đảm |
|---|---|---|
| Một lệnh **INCR**, **SET NX EX** | Bản thân lệnh nguyên tử trên Redis server xử lý key. | Quy tắc nghiệp vụ trải qua những lệnh khác. |
| **Pipelining** | Gửi một loạt lệnh giảm số lần đi-về mạng. | Tự động gom thành giao dịch nguyên tử. |
| **MULTI/EXEC** | Thực thi các lệnh đã queue liên tiếp, không bị lệnh client khác chen vào. | Rollback tự động nếu một lệnh lỗi khi thực thi; kiểm tra điều kiện trên kết quả GET trong Java ngay bên trong MULTI. |
| **WATCH + MULTI/EXEC** | Hủy transaction khi key đã theo dõi bị thay đổi trước EXEC. | Thành công sau retry vô hạn; rollback khi lỗi runtime. |
| **Lua / Redis Function** | Đọc điều kiện và cập nhật trong một lần thực thi phía Redis. | Rollback sau khi đã ghi rồi gặp lỗi; giao dịch liên hệ thống. |
| **@Transactional** trong Spring | Phụ thuộc transaction manager và cấu hình nguồn dữ liệu cụ thể. | Tự động biến thao tác Redis và SQL thành một distributed transaction nguyên tử. |

Riêng hỗ trợ transaction của **RedisTemplate** có cấu hình và quy tắc kết nối riêng; việc đặt **@Transactional** lên method Java không đủ để mặc nhiên bảo đảm mọi lệnh Redis trong method có tính nguyên tử với nhau.

## 8. Phân biệt atomicity, durability và idempotency

Ba khái niệm này phục vụ các vấn đề khác nhau:

**Atomicity (tính nguyên tử):** xét các client có nhìn thấy hoặc can thiệp vào trạng thái trung gian khi thao tác đang thực thi hay không. Một lệnh **INCR** giải quyết lost update khi tăng bộ đếm.

**Durability (tính bền vững):** xét dữ liệu có sống sót khi Redis hoặc máy chủ hỏng hay không. RDB, AOF, replication và cấu hình failover ảnh hưởng tới điều này. Lệnh đã được thực thi nguyên tử trên master **không đồng nghĩa** mọi replica đã nhận lệnh hoặc dữ liệu đã chắc chắn tồn tại sau sự cố.

**Idempotency (tính lặp an toàn):** xét việc thực hiện lại cùng một yêu cầu có làm phát sinh tác dụng phụ lần thứ hai hay không. Chẳng hạn **INCR** là lệnh nguyên tử nhưng **không idempotent**: gọi hai lần sẽ tăng hai lần. Nếu client timeout sau khi gửi **INCR**, client không thể chỉ dựa vào timeout để kết luận Redis chưa thực hiện lệnh; retry mù có thể tăng trùng.

Trong nghiệp vụ đặt hàng hoặc thanh toán, nên có mã yêu cầu duy nhất và cơ chế chống xử lý trùng phù hợp, đồng thời xác định rõ phạm vi bảo đảm giữa Redis và hệ thống ghi dữ liệu chính. Atomicity trong Redis cũng không thay thế giao dịch của database lưu đơn hàng.

## 9. Cách chọn giải pháp cho từng yêu cầu

| Yêu cầu | Lựa chọn ban đầu | Lý do |
|---|---|---|
| Tăng lượt xem, số lần thử | **INCR/INCRBY** | Trọn vẹn trong một lệnh; tránh lost update. |
| Tạo marker duy nhất có TTL | **SET ... NX EX/PX** | Kiểm tra tồn tại, ghi và gắn TTL cùng lúc. |
| Đưa phần tử vào tập không trùng | **SADD** | Redis tự xử lý tính duy nhất trong một lệnh. |
| Ghi nhiều thay đổi đã biết trước trên cùng instance/slot | **MULTI/EXEC** hoặc lệnh nhiều key sẵn có | Không bị xen lệnh trong lúc thực thi khối lệnh. |
| Đọc giá trị rồi cập nhật nếu chưa có ai sửa | **WATCH + MULTI/EXEC** | Dùng xung đột để hủy thay đổi dựa trên dữ liệu cũ. |
| Kiểm tra điều kiện tồn kho rồi trừ ngay | **Lua/Redis Function** | Gói điều kiện với cập nhật ở server. |
| Cập nhật Redis và một SQL database | Thiết kế nhất quán liên hệ thống, idempotency và cơ chế khôi phục riêng | Redis không tự cung cấp distributed transaction cho các hệ thống khác. |

Trước khi chọn giải pháp, hãy trả lời ba câu hỏi: **Điều kiện nào phải được kiểm tra? Những key nào sẽ thay đổi? Chúng có nằm trên cùng Redis instance/hash slot không?** Sau đó tìm ranh giới thực thi nhỏ nhất bao trùm cả điều kiện lẫn thay đổi. Nếu kết quả phải chịu được retry, lỗi mạng hoặc failover, bổ sung thiết kế idempotency và khôi phục tương ứng.

## 10. Bài tập suy luận

**Tình huống A.** Hai request cùng chạy **GET rate:client**, tăng số lên một rồi **SET** trở lại. Hệ thống thỉnh thoảng ghi nhận ít request hơn thực tế. Vì sao?

**Giải thích:** Hai request có thể đọc cùng giá trị cũ và cùng ghi một giá trị mới. Đổi sang **INCR rate:client** sẽ tránh mất cập nhật của thao tác tăng đơn lẻ. Nếu còn yêu cầu về giới hạn theo cửa sổ thời gian, kiểm tra giới hạn và tăng cần được thiết kế trong cùng ranh giới nguyên tử phù hợp.

**Tình huống B.** Một service chạy **SETNX lock:job worker-1** rồi **EXPIRE lock:job 30**. Thi thoảng key khóa tồn tại mãi. Vì sao?

**Giải thích:** Service có thể dừng sau khi tạo key nhưng trước khi đặt TTL. Dùng một thao tác **SET lock:job worker-1 NX EX 30** loại bỏ khoảng hở đó. Khi dùng khóa cho công việc thật, cần thêm cơ chế giải phóng chỉ khi token chủ sở hữu còn khớp và xử lý trường hợp lease hết hạn khi công việc chưa kết thúc.

**Tình huống C.** Một Lua script ghi vào key A, rồi lệnh tiếp theo gặp lỗi dữ liệu ở key B. Redis có tự hoàn tác ghi vào A không?

**Giải thích:** Không. Script có tính không bị chen lệnh trong lúc chạy nhưng không có rollback giao dịch sau lỗi runtime. Hãy đưa các kiểm tra có thể thực hiện trước lên đầu script và thiết kế đường đi lỗi rõ ràng.

Điều cần nhớ khi xây dựng ứng dụng Spring Data Redis là: **một lệnh nguyên tử không làm cho toàn bộ phương thức Java trở thành nguyên tử**. Độ an toàn phụ thuộc vào việc cả bước kiểm tra lẫn thay đổi trạng thái quan trọng có thực sự được đặt trong cùng một ranh giới thực thi Redis hay không.
