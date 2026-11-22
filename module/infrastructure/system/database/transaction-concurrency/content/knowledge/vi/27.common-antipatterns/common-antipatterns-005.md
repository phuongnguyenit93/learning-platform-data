# Dùng khóa trong bộ nhớ ứng dụng để bảo vệ nhiều tiến trình hoặc máy chủ

## Khóa trong bộ nhớ chỉ điều phối các thread cùng một tiến trình

Trong Java, `synchronized`, `ReentrantLock`, `ReadWriteLock` và các primitive trong `java.util.concurrent` giúp nhiều thread phối hợp khi truy cập dữ liệu dùng chung. Chúng rất hữu ích trong một JVM, nhưng phạm vi bảo vệ của chúng chỉ nằm trong bộ nhớ của tiến trình đang chạy.

Nếu một ứng dụng được triển khai thành nhiều JVM, container hoặc máy chủ, mỗi instance có vùng heap và đối tượng lock riêng. Hai instance có thể tạo hai lock khác nhau dù dùng cùng một tên khóa. Vì vậy, khóa trong bộ nhớ của instance A không ngăn instance B chạy cùng đoạn code.

Đây là lỗi thiết kế thường gặp khi ứng dụng ban đầu chỉ chạy một instance rồi được scale ngang. Code có thể đúng khi chạy local, đúng trong unit test một JVM, nhưng mất tính loại trừ tương hỗ khi có nhiều replica.

**Một khóa chỉ bảo vệ được những execution path cùng tham chiếu tới đúng một cơ chế đồng bộ.** Với Java lock trong heap, điều đó thường có nghĩa các thread trong cùng một JVM và cùng chia sẻ đối tượng lock.

## `synchronized` và `ReentrantLock` hoạt động ở phạm vi nào?

Mỗi object Java có monitor riêng. Khi thread vào một `synchronized` block trên object, các thread khác muốn vào block được đồng bộ trên cùng object phải chờ monitor được giải phóng.

```java
public class InventoryService {
    private final Object lock = new Object();
    private int quantity = 10;

    public boolean reserveOne() {
        synchronized (lock) {
            if (quantity <= 0) {
                return false;
            }

            quantity--;
            return true;
        }
    }
}
```

Nếu tất cả thread gọi cùng một instance `InventoryService`, monitor `lock` bảo vệ việc đọc và giảm `quantity`. Nhưng nếu hai ứng dụng khởi chạy hai object `InventoryService` trong hai JVM, chúng có hai object `lock` khác nhau và hai vùng heap khác nhau.

`ReentrantLock` cũng có phạm vi process-local:

```java
public class InventoryService {
    private final ReentrantLock lock = new ReentrantLock();
    private int quantity = 10;

    public boolean reserveOne() {
        lock.lock();
        try {
            if (quantity <= 0) {
                return false;
            }

            quantity--;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
```

`ReentrantLock` cung cấp các tính năng như `tryLock`, timeout, interruptible acquisition và fairness tùy cấu hình. Các tính năng này không mở rộng phạm vi khóa sang JVM khác. Hai instance của service vẫn không nhìn thấy lock của nhau.

### `static` không biến lock thành distributed lock

Một lỗi khác là dùng `static` và nghĩ rằng mọi instance đều chia sẻ cùng lock:

```java
public class InventoryService {
    private static final Object LOCK = new Object();

    public void update() {
        synchronized (LOCK) {
            // Critical section.
        }
    }
}
```

`static` làm field được chia sẻ giữa các object của cùng class trong cùng class loader/JVM. Mỗi JVM vẫn nạp class và giữ static field trong bộ nhớ riêng. Hai container không chia sẻ một static object chỉ vì chúng chạy cùng một artifact.

`static synchronized` cũng chỉ khóa monitor của đối tượng `Class` trong JVM hiện tại. Nó không tạo một khóa toàn cụm.

## Race condition khi scale từ một instance lên nhiều instance

Giả sử ứng dụng có endpoint cấp mã khuyến mãi. Trong một instance, code dùng `synchronized` để kiểm tra và tăng bộ đếm:

```java
public class CouponService {
    private final Object lock = new Object();
    private int issued = 0;
    private static final int LIMIT = 100;

    public boolean issueCoupon() {
        synchronized (lock) {
            if (issued >= LIMIT) {
                return false;
            }

            issued++;
            return true;
        }
    }
}
```

Trong một JVM với một instance service, các thread cùng tranh chấp monitor nên bộ đếm không vượt giới hạn. Nhưng nếu load balancer gửi request tới hai server:

```text
             Load balancer
              /         \
             /           \
       Instance A      Instance B
       JVM A            JVM B
       issued = 99      issued = 99
       lock A           lock B
```

Hai instance không chia sẻ `issued` hoặc `lock`. Cả A và B đều có thể đọc `99`, đều cấp một coupon và tăng bộ đếm local lên `100`. Hệ thống đã cấp tổng cộng 101 coupon dù mỗi JVM riêng lẻ không vượt `LIMIT`.

Ngay cả khi bộ đếm được lưu trong database, chỉ khóa một biến local quanh câu `SELECT`/`UPDATE` vẫn không bảo vệ được hai instance. Mỗi instance có monitor riêng, nên cả hai có thể cùng đọc một giá trị và ghi cạnh tranh.

### Mô phỏng lịch chạy giữa hai JVM

| Bước | Instance A | Instance B |
| --- | --- | --- |
| 1 | Lấy `lockA` | Lấy `lockB` |
| 2 | Đọc số coupon đã cấp = 99 | Đọc số coupon đã cấp = 99 |
| 3 | Kiểm tra `99 < 100`, hợp lệ | Kiểm tra `99 < 100`, hợp lệ |
| 4 | Cấp coupon A | Cấp coupon B |
| 5 | Ghi nhận coupon A | Ghi nhận coupon B |
| 6 | Nhả `lockA` | Nhả `lockB` |

Không có bước nào khiến A phải chờ B. Hai khóa thuộc hai JVM độc lập, nên cả hai critical section chạy đồng thời.

## Vì sao sticky session không phải giải pháp khóa đáng tin cậy?

Sticky session (session affinity) khiến load balancer cố gắng gửi request của một người dùng tới cùng instance. Cách này có thể làm giảm số request của cùng user đi qua nhiều instance, nhưng không tạo distributed lock:

- Hai người dùng khác nhau vẫn có thể cùng sửa một tài nguyên.
- Một job hoặc message consumer có thể chạy ở instance khác.
- Retry sau failover có thể tới một instance khác.
- Autoscaling, rolling deployment và health check có thể thay đổi định tuyến.
- Một instance có thể xử lý nhiều request đồng thời của cùng session.

Không nên dùng sticky session để bảo vệ bất biến dữ liệu. Nếu nghiệp vụ yêu cầu chỉ một thao tác được phép thay đổi một tài nguyên tại một thời điểm, cơ chế phối hợp phải nằm ở nơi mọi instance cùng quan sát được, thường là database hoặc một dịch vụ coordination dùng chung.

## Khóa trong bộ nhớ vẫn có những trường hợp phù hợp

Process-local lock không phải kỹ thuật sai. Nó phù hợp khi tài nguyên cần bảo vệ chỉ tồn tại trong một JVM, hoặc khi mục tiêu chỉ là tối ưu nội bộ chứ không phải bảo đảm bất biến toàn hệ thống.

Các trường hợp phù hợp gồm:

- bảo vệ một cache local không được chia sẻ giữa instance;
- tránh hai thread trong cùng JVM cùng khởi tạo một singleton hoặc tài nguyên local;
- điều phối truy cập vào một cấu trúc dữ liệu trong heap;
- giới hạn số tác vụ đồng thời trong một process bằng `Semaphore`;
- giảm duplicate work trong một instance như một tối ưu bổ sung, trong khi database vẫn có ràng buộc bảo vệ cuối cùng.

Ví dụ, cache local có thể dùng `ConcurrentHashMap.computeIfAbsent` để tránh nhiều thread cùng tải một giá trị trong một JVM:

```java
private final ConcurrentHashMap<String, Product> cache =
        new ConcurrentHashMap<>();

public Product getProduct(String id) {
    return cache.computeIfAbsent(id, productRepository::loadById);
}
```

Điều này giảm tải trùng trong cùng instance. Nếu có 5 instance, mỗi instance vẫn có cache riêng và có thể cùng tải sản phẩm một lần. Nếu dữ liệu cần đồng nhất giữa các instance, phải bổ sung cache invalidation hoặc một cơ chế chia sẻ phù hợp.

### Dùng striped lock để giảm số lock object

Nếu cần khóa theo key trong một JVM, có thể dùng một tập lock cố định (striped locks) thay vì tạo một lock object cho mọi key:

```java
public final class StripedLock {
    private final ReentrantLock[] locks;

    public StripedLock(int stripes) {
        if (stripes <= 0) {
            throw new IllegalArgumentException("stripes must be positive");
        }

        this.locks = IntStream.range(0, stripes)
                .mapToObj(index -> new ReentrantLock())
                .toArray(ReentrantLock[]::new);
    }

    public ReentrantLock forKey(String key) {
        int index = Math.floorMod(key.hashCode(), locks.length);
        return locks[index];
    }
}
```

Các key khác nhau có thể rơi vào cùng stripe và chờ nhau, nhưng số lock object được giới hạn. Đây vẫn là khóa local trong một JVM. Nó không bảo vệ dữ liệu khi có instance khác.

### Cẩn thận với registry tạo lock theo key

Một mẫu thường thấy là:

```java
private final ConcurrentHashMap<String, ReentrantLock> locks =
        new ConcurrentHashMap<>();

public void process(String key) {
    ReentrantLock lock = locks.computeIfAbsent(key, ignored -> new ReentrantLock());
    lock.lock();
    try {
        doWork(key);
    } finally {
        lock.unlock();
    }
}
```

Mẫu này tránh tạo hai lock khác nhau cho cùng key trong một map, nhưng map có thể tăng không giới hạn nếu số key rất lớn. Xóa lock ngay sau `unlock()` cũng có thể tạo race: thread khác đã lấy reference tới lock cũ nhưng thread mới tạo lock mới sau khi map entry bị xóa; hai thread khi đó khóa hai object khác nhau.

Nếu cần khóa theo key trong một JVM, hãy dùng striped lock hoặc một thư viện quản lý lock có vòng đời rõ ràng. Dù chọn cách nào, đừng coi nó là khóa phân tán.

## Bảo vệ bất biến ở nơi dữ liệu được lưu

Nếu mục tiêu là không để dữ liệu nghiệp vụ bị sai khi nhiều tiến trình cùng ghi, database thường là nơi thích hợp để thực thi bất biến. Mọi instance cùng ghi vào một database có thể được điều phối bằng transaction, unique constraint, row lock hoặc optimistic locking.

Điểm quan trọng là cơ chế phải được áp dụng ở ranh giới ghi dữ liệu. Một `synchronized` quanh service không bảo vệ được khi có:

- nhiều application instance;
- batch job hoặc worker ghi trực tiếp;
- script vận hành hoặc admin cập nhật dữ liệu;
- một service khác dùng chung database;
- retry sau khi instance cũ chết.

### Unique constraint cho quy tắc không được trùng

Nếu nghiệp vụ yêu cầu mỗi user chỉ có một coupon cho một campaign, hãy để database bảo vệ điều đó:

```sql
CREATE TABLE issued_coupons (
    id           BIGINT PRIMARY KEY,
    campaign_id  BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    issued_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_coupon_campaign_user
        UNIQUE (campaign_id, user_id)
);
```

Hai instance có thể cùng thử `INSERT`, nhưng unique constraint chỉ cho phép một dòng có cùng `(campaign_id, user_id)`. Instance thua cuộc nhận duplicate-key/conflict và xử lý như trường hợp coupon đã được cấp.

Đây là lựa chọn tốt khi quy tắc có thể biểu diễn bằng tính duy nhất. Không cần một distributed lock để bảo vệ một bất biến mà unique index có thể bảo đảm trực tiếp.

### Atomic UPDATE với điều kiện

Nếu giới hạn là số lượng coupon tổng cộng, có thể dùng một câu lệnh cập nhật có điều kiện:

```sql
UPDATE campaigns
SET issued_count = issued_count + 1
WHERE id = :campaign_id
  AND issued_count < coupon_limit;
```

Kiểm tra số dòng bị ảnh hưởng:

- `1`: đã giữ được một slot cấp coupon.
- `0`: campaign không tồn tại hoặc đã đạt giới hạn; ứng dụng xác định nhánh phù hợp.

Phép kiểm tra và tăng bộ đếm diễn ra trong cùng câu lệnh database. Các transaction cạnh tranh được database điều phối trên dòng campaign. Nếu sau đó cần tạo coupon, hãy tạo coupon và tăng bộ đếm trong cùng transaction; nếu insert coupon thất bại, rollback cả cập nhật bộ đếm.

### SELECT ... FOR UPDATE để tuần tự hóa theo dòng

Nếu quyết định nghiệp vụ cần đọc nhiều cột trước khi ghi, có thể khóa dòng trong transaction:

```sql
START TRANSACTION;

SELECT issued_count, coupon_limit
FROM campaigns
WHERE id = :campaign_id
FOR UPDATE;

-- Ứng dụng kiểm tra issued_count < coupon_limit.

UPDATE campaigns
SET issued_count = issued_count + 1
WHERE id = :campaign_id;

INSERT INTO issued_coupons(campaign_id, user_id)
VALUES (:campaign_id, :user_id);

COMMIT;
```

Transaction khác muốn khóa dòng campaign này phải chờ. Tất cả thao tác kiểm tra, tăng bộ đếm và tạo coupon phải nằm trong cùng transaction. Trong production, cần xử lý nhánh hết quota và duplicate user, đồng thời giữ transaction ngắn.

### Optimistic locking bằng version

Khi xung đột hiếm, có thể dùng cột version:

```sql
UPDATE campaigns
SET issued_count = :new_count,
    version = version + 1
WHERE id = :campaign_id
  AND version = :version_read
  AND issued_count < coupon_limit;
```

Nếu không có dòng nào được cập nhật, dữ liệu đã thay đổi hoặc quota không còn. Ứng dụng đọc lại và quyết định thử lại hay trả kết quả hết quota. Optimistic locking không cần giữ một khóa local qua toàn bộ thao tác; database phát hiện cập nhật dựa trên version.

## Khi nào cần distributed lock?

Có những công việc không thể bảo vệ chỉ bằng unique constraint hoặc một câu update đơn giản. Ví dụ:

- chỉ một worker được chạy tác vụ tổng hợp dài cho một tenant tại một thời điểm;
- chỉ một instance được thực hiện leader task như điều phối lịch hoặc phân phối partition;
- một quy trình cần độc quyền trên nhiều hệ thống trong khi xử lý;
- tránh hai job cùng thực hiện một thao tác không thể diễn đạt thành một transaction database ngắn.

Khi đó, có thể cần distributed coordination hoặc distributed lock. Khóa phân tán là cơ chế chia sẻ trạng thái khóa qua một hệ thống mà mọi process đều truy cập được, chẳng hạn database, Redis hoặc một hệ thống coordination chuyên dụng.

Distributed lock phức tạp hơn `ReentrantLock` vì mạng có thể phân vùng, node có thể chết, lease có thể hết hạn và client có thể không biết thao tác acquire/release đã thành công hay chưa. Nó cần giao thức rõ về ownership, thời hạn, gia hạn và xử lý chủ sở hữu cũ.

## Khóa trong database

Nếu dữ liệu nghiệp vụ đã nằm trong database, dùng chính database làm coordinator thường là lựa chọn đơn giản nhất.

### Một dòng lock theo resource key

Có thể tạo bảng lock:

```sql
CREATE TABLE resource_locks (
    resource_key VARCHAR(200) PRIMARY KEY,
    owner_id     VARCHAR(100) NOT NULL,
    acquired_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Ứng dụng cố gắng chèn dòng cho resource. Primary key bảo đảm chỉ một owner có thể tạo dòng với cùng `resource_key`:

```sql
INSERT INTO resource_locks(resource_key, owner_id)
VALUES (:resource_key, :owner_id);
```

Nếu insert thành công, transaction đã chiếm lock theo quy ước ứng dụng. Nếu duplicate key, resource đang được giữ. Khi hoàn tất, owner xóa đúng dòng của mình:

```sql
DELETE FROM resource_locks
WHERE resource_key = :resource_key
  AND owner_id = :owner_id;
```

Mẫu này cần xử lý crash của owner. Nếu process chết trước khi xóa, dòng lock có thể tồn tại mãi. Có thể thêm lease/expiry, nhưng khi đó phải xử lý an toàn trường hợp lease hết hạn trong khi owner cũ vẫn đang chạy. Không dùng `DELETE WHERE resource_key = ?` mà không kiểm tra owner, vì một process cũ có thể xóa lock do process mới chiếm.

### Transaction row lock

Một cách khác là giữ row lock bằng transaction:

```sql
BEGIN;

SELECT id
FROM scheduled_jobs
WHERE id = :job_id
FOR UPDATE;

-- Thực hiện cập nhật ngắn trong database.
UPDATE scheduled_jobs
SET status = 'RUNNING'
WHERE id = :job_id;

COMMIT;
```

Các instance khác dùng cùng database sẽ cạnh tranh trên cùng row lock. Khi transaction commit hoặc rollback, khóa được giải phóng. Cách này phù hợp khi critical section chủ yếu là thao tác database ngắn.

Không giữ row lock trong lúc gọi HTTP hoặc chạy tác vụ dài. Nếu công việc dài, hãy claim bằng lease và trạng thái bền vững, xử lý bên ngoài transaction ngắn rồi cập nhật kết quả có kiểm tra ownership/version.

### Advisory lock

Một số database có advisory lock, cho phép ứng dụng khóa theo một key logic thay vì phải khóa một dòng nghiệp vụ cụ thể. Ví dụ PostgreSQL có advisory lock theo session hoặc transaction:

```sql
-- Transaction-scoped advisory lock.
SELECT pg_advisory_xact_lock(42, 1001);

-- Thực hiện phần công việc cần phối hợp.

COMMIT;
```

Transaction-scoped lock được giải phóng khi transaction kết thúc. PostgreSQL còn có các hàm `pg_try_advisory_xact_lock` để thử lấy khóa không chờ. MySQL cũng có `GET_LOCK()`/`RELEASE_LOCK()` với semantics theo session. Advisory lock là tính năng riêng của database, cần hiểu scope và vòng đời session/transaction của từng engine.

Advisory lock không thay thế unique constraint hoặc kiểm tra dữ liệu. Nếu một writer không tuân theo quy ước lấy advisory lock, nó vẫn có thể sửa dữ liệu. Hãy dùng ràng buộc database để bảo vệ bất biến dữ liệu quan trọng.

## Distributed lock bằng Redis và lease

Redis thường được dùng để cung cấp khóa chia sẻ giữa nhiều instance. Một thao tác acquire đơn giản cần đặt key nếu key chưa tồn tại và gắn thời hạn:

```text
SET lock:campaign:42 <random-token> NX PX 10000
```

- `NX` chỉ đặt key nếu key chưa tồn tại.
- `PX 10000` đặt TTL 10.000 ms.
- `<random-token>` là token ngẫu nhiên duy nhất cho lần acquire của owner.

Nếu Redis xác nhận thành công, client được cấp lease trong khoảng thời gian TTL. Nếu key đã tồn tại, client không lấy được lock và có thể chờ, thử lại hoặc bỏ qua công việc theo chính sách.

`SET NX PX` là một mẫu acquire lease cơ bản, không phải bằng chứng rằng mọi cấu hình Redis replication/failover đều cung cấp khóa tuyến tính tuyệt đối. Nếu primary xác nhận ghi lock nhưng sự kiện đó chưa được replica nhận trước khi primary lỗi, một primary mới có thể không còn thấy key và cấp lock cho client khác. Với thao tác mà sai sót gây hậu quả nghiêm trọng, phải xác định rõ failure model của coordinator và bảo vệ tài nguyên đích bằng fencing token hoặc ràng buộc database. Không dựa riêng vào việc client nhận được `OK` từ một lần `SET` để suy ra toàn bộ hệ thống chỉ có một owner trong mọi tình huống lỗi.

### Vì sao cần token khi release?

Không được release bằng lệnh `DEL lock:key` một cách vô điều kiện. Giả sử:

1. Client A lấy lock với token A và bắt đầu xử lý.
2. Lease A hết hạn vì xử lý lâu hoặc A bị pause.
3. Client B lấy lock mới với token B.
4. A tiếp tục chạy và gọi `DEL lock:key`.

Nếu A xóa key vô điều kiện, nó xóa lock của B. Vì vậy, release phải kiểm tra token hiện tại có khớp token của owner hay không rồi mới xóa, trong một thao tác nguyên tử ở Redis:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
```

Script kiểm tra và xóa trong cùng một thao tác nguyên tử. Token ngăn owner cũ xóa lease mới.

### Lease hết hạn không dừng được owner cũ

TTL giúp tránh khóa tồn tại mãi khi process chết, nhưng nó tạo một tình huống quan trọng: lease có thể hết hạn trong khi client cũ vẫn đang thực hiện công việc.

```text
Thời gian  -------------------------------------------->

Client A:  acquire A ======== pause / xử lý chậm ======= ghi dữ liệu
Redis:     owner A --------- TTL hết -------- owner B --------
Client B:                         acquire B ===== xử lý =====
```

Sau khi B lấy lease, A vẫn có thể tỉnh lại và tiếp tục. Redis đã chuyển ownership nhưng không tự dừng code A hoặc thu hồi câu SQL A sắp gửi tới database. Nếu A và B cùng ghi dữ liệu, distributed lock đơn thuần có thể vẫn cho phép thao tác cũ xảy ra muộn.

Vì vậy, distributed lock dựa trên lease không tự bảo đảm an toàn cho mọi tài nguyên được bảo vệ. Tài nguyên đích cần có cách từ chối owner cũ hoặc thao tác stale.

## Fencing token: ngăn owner cũ ghi sau owner mới

Fencing token là một số thứ tự tăng dần được cấp mỗi lần chiếm quyền. Tài nguyên được bảo vệ lưu token mới nhất đã chấp nhận và từ chối thao tác mang token cũ hơn. Quy tắc với nhiều thao tác cùng token phải được xác định theo giao thức; fencing token ngăn owner cũ ghi sau owner mới, còn idempotency/version xử lý việc phát lại cùng một thao tác.

Ví dụ:

```text
Client A lấy lease, fencing token = 41
Client A bị pause và lease hết hạn
Client B lấy lease, fencing token = 42
Client B ghi dữ liệu với token 42 -> chấp nhận
Client A tỉnh lại, ghi dữ liệu với token 41 -> từ chối
```

Tài nguyên đích phải kiểm tra token, ví dụ:

```sql
UPDATE protected_resource
SET payload = :payload,
    last_fencing_token = :token
WHERE id = :resource_id
  AND last_fencing_token <= :token;
```

Ứng dụng kiểm tra đúng một dòng được cập nhật. Nếu token cũ hơn token đã chấp nhận, câu lệnh không tác động dòng nào. Điều kiện `<=` cho phép owner hiện tại dùng cùng token cho nhiều lần ghi liên tiếp, trong khi token nhỏ hơn bị từ chối. Nếu mỗi token chỉ được phép thực hiện một lần ghi, cần thêm định danh thao tác hoặc điều kiện version phù hợp để ngăn lặp.

Token phải được cấp theo thứ tự tăng đơn điệu bởi một coordinator đáng tin cậy. Token ngẫu nhiên chỉ giúp nhận diện owner, không thay thế fencing token vì không biểu diễn thứ tự mới/cũ.

Nếu hệ thống đích là API bên thứ ba không hỗ trợ fencing hoặc idempotency, ứng dụng không thể tự ép provider từ chối thao tác của owner cũ. Khi đó cần dùng cơ chế idempotency/reference của provider, truy vấn trạng thái, hoặc chấp nhận và xử lý quy trình đối soát.

## Phân biệt lock, lease, idempotency và uniqueness

Các cơ chế này giải quyết các câu hỏi khác nhau:

| Cơ chế | Câu hỏi được giải quyết | Ví dụ |
| --- | --- | --- |
| In-memory lock | Các thread trong cùng JVM có được vào critical section cùng lúc không? | `synchronized`, `ReentrantLock`. |
| Distributed lock | Instance nào đang giữ quyền xử lý resource theo coordinator dùng chung? | Redis lease, database advisory lock. |
| Lease | Quyền sở hữu còn hiệu lực tới thời điểm nào? | Redis key có TTL, database `locked_until`. |
| Fencing token | Làm sao từ chối thao tác từ owner cũ? | Sequence tăng dần được kiểm tra tại resource đích. |
| Idempotency key | Retry của cùng một ý định có tạo hiệu ứng lặp không? | API payment nhận cùng key và phát lại kết quả. |
| Unique constraint | Hai bản ghi có vi phạm quy tắc duy nhất không? | `UNIQUE (campaign_id, user_id)`. |

Một hệ thống có thể cần nhiều lớp. Ví dụ, Redis lease giảm khả năng hai worker cùng xử lý một job; fencing token ngăn worker cũ ghi kết quả sau khi lease hết hạn; unique constraint bảo vệ dữ liệu không trùng; idempotency key bảo vệ lời gọi tới provider khi retry.

Không dùng distributed lock để thay thế một constraint đơn giản. Nếu chỉ cần “mỗi user một coupon”, unique constraint thường trực tiếp và đáng tin cậy hơn. Nếu cần chỉ một worker làm tác vụ dài, lease có thể hữu ích nhưng cần ownership và recovery rõ ràng.

## Lỗi thường gặp khi triển khai distributed lock

| Cách làm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Dùng `synchronized` và nghĩ nó khóa mọi replica | Mỗi JVM có monitor riêng. | Dùng database/shared coordinator hoặc bảo vệ bất biến bằng constraint. |
| Dùng `static` để biến lock thành global | Static field chỉ chia sẻ trong JVM/class loader tương ứng. | Đặt coordination ở hệ thống dùng chung. |
| Dựa vào sticky session | Request khác, worker khác hoặc failover vẫn có thể chạy song song. | Thiết kế khóa ở nơi mọi writer cùng tuân theo. |
| Redis `SET NX` không có TTL | Process chết có thể để lock tồn tại vô hạn. | Dùng lease có TTL và quy trình gia hạn/khôi phục. |
| Release bằng `DEL` không kiểm tra owner | Owner cũ có thể xóa lock của owner mới. | Dùng token và script compare-and-delete nguyên tử. |
| TTL quá ngắn | Lease hết hạn khi owner còn đang làm việc. | Đo thời gian xử lý, gia hạn có kiểm soát và dùng fencing token. |
| TTL quá dài | Khôi phục sau crash chậm và công việc bị chặn lâu. | Chọn lease theo SLA và cơ chế takeover. |
| Nghĩ lease hết hạn sẽ dừng process cũ | Owner cũ vẫn có thể chạy và gửi lệnh ghi. | Bảo vệ tài nguyên bằng fencing token/version. |
| Giữ distributed lock trong khi gọi nhiều dịch vụ mà không có recovery | Network failure làm kết quả không rõ, lease có thể hết hạn giữa quy trình. | Dùng workflow bền vững, idempotency và đối soát. |
| Khóa một resource bằng tên không chuẩn hóa | Hai instance có thể tạo hai key khác nhau cho cùng tài nguyên logic. | Chuẩn hóa namespace, tenant và resource ID. |
| Dùng lock như lớp bảo vệ duy nhất cho dữ liệu | Writer không lấy lock vẫn có thể vi phạm bất biến. | Giữ unique constraint, transaction hoặc version check ở database. |

## Thiết kế key và ownership cẩn thận

Distributed lock chỉ hữu ích nếu mọi client tạo cùng một key cho cùng một tài nguyên. Key cần bao gồm namespace và phạm vi nghiệp vụ:

```text
lock:<environment>:<tenant-id>:<resource-type>:<resource-id>
```

Ví dụ:

```text
lock:prod:tenant-17:campaign:42
```

Tránh tạo key chỉ từ tên hiển thị hoặc một chuỗi có thể thay đổi. Cần thống nhất cách chuẩn hóa chữ hoa/thường, khoảng trắng, encoding và tenant scope. Nếu hai instance tạo key khác nhau cho cùng một resource, chúng sẽ không tranh chấp cùng lock.

Owner token nên đủ ngẫu nhiên để không trùng với lần acquire khác. Không dùng hostname hoặc tên pod làm token duy nhất vì pod có thể restart và tên có thể được tái sử dụng. Token chỉ nhận diện lần sở hữu; nó không tự bảo vệ tài nguyên khỏi thao tác stale.

## Quy trình xử lý job dài bằng lease

Với công việc dài, một mẫu phổ biến là lưu lease trong database:

```sql
CREATE TABLE jobs (
    id                 BIGINT PRIMARY KEY,
    status             VARCHAR(20) NOT NULL,
    owner_id           VARCHAR(100),
    locked_until       TIMESTAMP,
    fencing_token      BIGINT NOT NULL DEFAULT 0,
    attempt_count      INTEGER NOT NULL DEFAULT 0
);
```

Worker claim job bằng một câu cập nhật có điều kiện. Cú pháp cụ thể phụ thuộc database; ý tưởng là chỉ worker đầu tiên cập nhật được job đang `READY` hoặc lease đã hết hạn:

```sql
UPDATE jobs
SET status = 'RUNNING',
    owner_id = :owner_id,
    locked_until = :lease_until,
    fencing_token = fencing_token + 1,
    attempt_count = attempt_count + 1
WHERE id = :job_id
  AND (
      status = 'READY'
      OR (status = 'RUNNING' AND locked_until < CURRENT_TIMESTAMP)
  );
```

Worker kiểm tra số dòng bị ảnh hưởng. Nếu bằng `1`, nó đọc `fencing_token` mới và bắt đầu xử lý. Nếu bằng `0`, worker khác đang sở hữu job hoặc job đã hoàn tất.

Khi hoàn tất, worker cập nhật kết quả với điều kiện owner và token vẫn khớp:

```sql
UPDATE jobs
SET status = 'COMPLETED',
    locked_until = NULL
WHERE id = :job_id
  AND owner_id = :owner_id
  AND fencing_token = :fencing_token;
```

Nếu worker cũ mất lease và worker mới đã claim, token đã tăng. Câu cập nhật của worker cũ không còn khớp và không thể ghi đè trạng thái của worker mới.

Ví dụ này minh họa một lease bền vững trong database. Cần bổ sung transaction, index cho điều kiện claim, xử lý thời gian theo clock của database và quy tắc heartbeat/renewal. Không dựa vào đồng hồ local của từng JVM để so sánh lease nếu các máy có thể lệch thời gian; dùng thời gian của coordinator/database khi có thể.

## Chọn cơ chế theo bài toán

| Bài toán | Cơ chế thường phù hợp | Lý do |
| --- | --- | --- |
| Bảo vệ `HashMap` trong một JVM | `synchronized`, `ReentrantLock`, concurrent collection | Dữ liệu nằm trong heap của một process. |
| Ngăn hai request tạo cùng một bản ghi nghiệp vụ | Unique constraint | Database là nơi ghi dữ liệu và có thể bảo vệ trực tiếp quy tắc duy nhất. |
| Trừ tồn kho hoặc tăng bộ đếm có điều kiện | Atomic `UPDATE` hoặc row lock | Phép kiểm tra và ghi được database điều phối. |
| Nhiều worker claim cùng một job ngắn | `SELECT ... FOR UPDATE SKIP LOCKED` hoặc atomic claim | Database chọn worker và ghi trạng thái trong transaction. |
| Chỉ một worker làm tác vụ dài trên một resource | Lease + owner token + fencing/version | Cho phép takeover sau crash và ngăn owner cũ ghi stale. |
| Điều phối leader hoặc tác vụ toàn cụm | Distributed coordination service hoặc advisory lock | Cần một coordinator dùng chung và quy tắc failover. |
| Retry lời gọi payment/email/API | Idempotency key và lưu kết quả | Lock không giải quyết timeout sau khi provider đã xử lý. |

Trước khi thêm distributed lock, hãy hỏi liệu thao tác có thể được diễn đạt bằng một transaction database, unique constraint hoặc atomic update hay không. Các cơ chế đó thường ít thành phần hơn và bảo vệ dữ liệu ngay tại nơi lưu.

## Kiểm thử để phát hiện khóa local bị dùng sai phạm vi

Một unit test chạy nhiều thread trên cùng một object chỉ chứng minh khóa hoạt động trong một JVM. Nó không chứng minh khóa phối hợp được nhiều instance.

Để tái hiện lỗi scale-out:

1. Khởi chạy hai application context hoặc hai JVM độc lập.
2. Gửi request đồng thời tới cả hai instance cho cùng một resource ID.
3. Đồng bộ request ở một điểm xác định bằng test hook/barrier hoặc load generator có kiểm soát.
4. Kiểm tra bất biến tại database sau khi cả hai request hoàn tất.
5. Lặp lại với instance restart hoặc failover nếu bài toán có lease/owner.

Ví dụ, nếu service dùng `synchronized` để bảo vệ giới hạn coupon, test cần xác nhận tổng số coupon trong database không vượt quota khi hai instance cùng cấp. Test một JVM không thể phát hiện lỗi này vì cả hai request trong test vẫn dùng chung monitor.

Khi kiểm thử Redis lease, cần mô phỏng owner A bị pause lâu hơn TTL, owner B lấy lease mới và A tiếp tục. Kiểm tra rằng tài nguyên đích từ chối thao tác của A nhờ fencing token. Chỉ kiểm tra rằng Redis có một key tại một thời điểm là chưa đủ để chứng minh dữ liệu nghiệp vụ được bảo vệ.

## Bài tập vận dụng

Một dịch vụ Java cấp mã voucher với giới hạn 500 voucher cho mỗi campaign. Ban đầu dịch vụ chỉ chạy một instance và dùng `synchronized` quanh đoạn đọc bộ đếm rồi tạo voucher. Sau khi triển khai Kubernetes, hệ thống chạy 6 pod và đôi khi cấp vượt giới hạn.

Hãy phân tích:

1. Vì sao `synchronized` và `static synchronized` không ngăn sáu pod cùng cấp voucher?
2. Vì sao sticky session không bảo vệ được giới hạn campaign?
3. Nếu chỉ cần mỗi user nhận một voucher trong một campaign, nên đặt constraint nào?
4. Nếu cần bảo đảm tổng số voucher không vượt 500, hãy viết một `UPDATE` có điều kiện và giải thích cách kiểm tra số dòng bị ảnh hưởng.
5. Khi nào `SELECT ... FOR UPDATE` phù hợp hơn atomic update?
6. Nếu công việc cấp voucher kéo dài và cần một worker duy nhất cho mỗi campaign, lease và fencing token giúp gì?
7. Vì sao Redis lock vẫn cần idempotency hoặc unique constraint ở nơi lưu voucher?

Một thiết kế phù hợp có thể dùng `UNIQUE (campaign_id, user_id)` để ngăn cấp trùng cho cùng user, cùng với atomic `UPDATE campaigns SET issued_count = issued_count + 1 WHERE id = ? AND issued_count < coupon_limit` trong transaction tạo voucher. Nếu hai instance cùng thử, database chỉ cho phép các cập nhật còn thỏa quota. Distributed lock chỉ cần thiết nếu còn một đoạn công việc dài phải được một worker điều phối; khi đó cần lease, token ownership, fencing/version và cơ chế phục hồi. Ràng buộc database vẫn là lớp bảo vệ cuối cùng cho dữ liệu voucher.
