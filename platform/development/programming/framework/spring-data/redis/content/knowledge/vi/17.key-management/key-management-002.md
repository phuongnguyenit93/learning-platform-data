# Xóa đồng bộ với DEL và giải phóng bất đồng bộ với UNLINK trong Spring Data Redis

Khi vô hiệu hóa một phiên đăng nhập, xóa cache lỗi thời hoặc dọn dữ liệu tạm trong Redis, ứng dụng cần loại bỏ **key**. Hai lệnh liên quan trực tiếp là `DEL` và `UNLINK`. Cả hai đều khiến key không còn được truy cập qua tên cũ ngay khi lệnh hoàn tất, nhưng khác nhau ở **cách thu hồi bộ nhớ chứa giá trị**. Sự khác biệt đặc biệt quan trọng khi một key lưu Hash, List, Set hoặc Sorted Set rất lớn.

Trong Spring Data Redis, hai thao tác tương ứng là `RedisTemplate.delete(...)` và `RedisTemplate.unlink(...)`. Hiểu chúng giúp chọn cách xóa đáp ứng yêu cầu độ trễ mà không nhầm “bất đồng bộ” với việc xóa key vào một thời điểm không xác định.

## 1. Hai phần của việc xóa một key

Một key Redis có thể được hình dung gồm:

1. **Ánh xạ trong keyspace:** tên key trỏ đến đối tượng dữ liệu.
2. **Bộ nhớ của đối tượng:** cấu trúc và phần tử được cấp phát để lưu giá trị.

Để xóa key, Redis phải gỡ ánh xạ trong keyspace và giải phóng bộ nhớ của đối tượng. Với cách xử lý thông thường, `DEL` làm cả hai việc trong luồng xử lý lệnh, còn `UNLINK` gỡ tên key trước và giao phần thu hồi bộ nhớ tốn kém cho luồng nền.

```text
Client gửi DEL my:key
      |
      v
Redis gỡ key khỏi keyspace
      |
      v
Redis giải phóng bộ nhớ trong quá trình xử lý lệnh
      |
      v
Trả kết quả cho client

Client gửi UNLINK my:key
      |
      v
Redis gỡ key khỏi keyspace
      |                         \
      v                          \--> Đưa công việc thu hồi bộ nhớ
Trả kết quả cho client                  sang luồng nền
                                         |
                                         v
                                  Thu hồi bộ nhớ sau đó
```

**Điểm cốt lõi:** “UNLINK bất đồng bộ” nói về thu hồi bộ nhớ, không có nghĩa key vẫn đọc được sau khi lệnh trả kết quả. Tên key đã bị gỡ khỏi keyspace trong chính lệnh `UNLINK`. Nếu tiến trình khác ghi lại cùng tên sau đó, đó là dữ liệu mới.

## 2. So sánh DEL và UNLINK

| Khía cạnh | `DEL` | `UNLINK` |
|---|---|---|
| Cú pháp | `DEL key [key ...]` | `UNLINK key [key ...]` |
| Khả năng truy cập key sau khi lệnh hoàn tất | Không còn key cũ | Không còn key cũ |
| Thu hồi bộ nhớ | Thông thường thực hiện trong luồng xử lý lệnh | Gỡ key nhanh; việc thu hồi tốn kém được chuyển sang luồng nền |
| Chi phí với key String | Thường O(1) | O(1) khi gỡ một key |
| Chi phí với Hash/List/Set/Sorted Set lớn | Có thể tăng theo số phần tử và chặn luồng xử lý | O(1) theo mỗi key trên đường xử lý; phần giải phóng được xử lý sau |
| Xóa nhiều key | O(số key) cộng với chi phí giải phóng giá trị | O(số key) trên đường xử lý cộng với công việc giải phóng nền |
| Giá trị trả về | Số key thực sự xóa | Số key thực sự gỡ khỏi keyspace |
| Trường hợp phù hợp | Key nhỏ, ít key, thao tác đơn giản | Key lớn, dọn dữ liệu hàng loạt, nhạy cảm với độ trễ |

Redis xử lý thao tác xóa key theo thứ tự và bảo đảm tính nguyên tử của thay đổi keyspace. Phần việc giải phóng bộ nhớ chạy sau không làm key cũ xuất hiện lại.

**Ngoại lệ cấu hình:** Redis có tùy chọn `lazyfree-lazy-user-del` cho phép `DEL` do người dùng gọi cũng sử dụng lazy free. Bởi vậy, nói “DEL luôn giải phóng đồng bộ” là quá tuyệt đối: đó là hành vi thông thường khi không bật tùy chọn này. `UNLINK` thể hiện rõ ý định chuyển công việc thu hồi sang nền ở cấp lệnh.

## 3. Thực hành bằng Redis CLI

### 3.1. Xóa một key nhỏ với DEL

```redis
SET session:42 "active"
EXISTS session:42
# (integer) 1

DEL session:42
# (integer) 1

EXISTS session:42
# (integer) 0

DEL session:42
# (integer) 0
```

`DEL` trả về `1` khi key tồn tại và được xóa. Lần gọi thứ hai trả về `0` vì key không còn tồn tại. Kết quả là **số key bị xóa**, không phải số phần tử bên trong giá trị. Với nhiều key:

```redis
SET session:43 "active"
SET session:44 "expired"
DEL session:43 session:44 session:missing
# (integer) 2
```

### 3.2. Xóa cấu trúc dữ liệu với UNLINK

```redis
HSET report:2026:11 author "team-a" state "ready" rows "100000"
EXISTS report:2026:11
# (integer) 1

UNLINK report:2026:11
# (integer) 1

EXISTS report:2026:11
# (integer) 0
HGETALL report:2026:11
# (empty array)
```

Ví dụ dùng Hash nhỏ để dễ thử. Lợi ích về độ trễ của `UNLINK` sẽ rõ hơn khi giá trị rất lớn và việc giải phóng nó tốn công. Key không cần đợi luồng nền giải phóng xong mới biến mất khỏi keyspace.

```redis
SET cache:a "A"
SET cache:b "B"
UNLINK cache:a cache:b cache:unknown
# (integer) 2
```

Key không tồn tại được bỏ qua ở cả hai lệnh. Việc gọi xóa lần nữa an toàn nếu mục đích chỉ là bảo đảm key không còn tồn tại.

### 3.3. Quan sát bộ nhớ sau khi xóa

```redis
INFO memory
INFO stats
SLOWLOG GET 10
```

Tùy phiên bản Redis, `INFO` có các chỉ số như `used_memory` và `lazyfree_pending_objects`. Với `UNLINK`, bộ nhớ có thể được giải phóng **sau** khi lệnh trả về nên không thể giả định `used_memory` giảm ngay. RSS của tiến trình còn phụ thuộc bộ cấp phát và hệ điều hành; có khi đối tượng đã giải phóng nhưng RSS chưa giảm. `SLOWLOG` giúp phát hiện lệnh tốn thời gian, song không đo toàn bộ thời gian công việc nền của `UNLINK`.

## 4. Dùng DEL và UNLINK qua Spring Data Redis

Ứng dụng Spring Boot thường dùng starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Với tên key dạng chuỗi, `StringRedisTemplate` thuận tiện vì serializer của key dùng chuỗi. Các phương thức chính:

| API Spring Data Redis | Lệnh Redis | Kết quả thông thường |
|---|---|---|
| `redisTemplate.delete(key)` | `DEL key` | `Boolean`: key được xóa hay không |
| `redisTemplate.delete(keys)` | `DEL key1 key2 ...` | `Long`: số key bị xóa |
| `redisTemplate.unlink(key)` | `UNLINK key` | `Boolean`: key được gỡ hay không |
| `redisTemplate.unlink(keys)` | `UNLINK key1 key2 ...` | `Long`: số key được gỡ |

Các API thuộc `RedisOperations`, được `RedisTemplate` hiện thực. Trong pipeline hoặc transaction, Spring Data Redis có thể trả `null` khi lệnh vừa được xếp hàng; kết quả thực tế phải lấy sau khi thực thi. **Không diễn giải `null` thành xóa thất bại.**

### 4.1. Service xóa key theo mục đích

```java
import java.util.Collection;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisKeyRemovalService {

    private final StringRedisTemplate redisTemplate;

    public RedisKeyRemovalService(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    // Key String nhỏ, ví dụ trạng thái phiên.
    public boolean deleteSession(String sessionId) {
        String key = "session:" + sessionId;
        return Boolean.TRUE.equals(redisTemplate.delete(key));
    }

    // Key có thể chứa Hash, Set hoặc List lớn.
    public boolean unlinkReport(String reportId) {
        String key = "report:cache:" + reportId;
        return Boolean.TRUE.equals(redisTemplate.unlink(key));
    }

    // Chỉ dùng cách lấy số đếm trực tiếp ngoài pipeline/transaction.
    public long unlinkKeys(Collection<String> keys) {
        if (keys.isEmpty()) {
            return 0L;
        }

        Long removed = redisTemplate.unlink(keys);
        if (removed == null) {
            throw new IllegalStateException(
                    "Chưa có kết quả UNLINK: kiểm tra pipeline/transaction");
        }
        return removed;
    }
}
```

`unlinkReport(...)` vẫn đợi gửi lệnh tới Redis và nhận phản hồi từ server: nó **không** tự biến lời gọi Java thành reactive hoặc fire-and-forget. Bất đồng bộ ở đây nằm trong cơ chế Redis thu hồi bộ nhớ. Nếu cần client không chặn thread, đó là quyết định riêng về API reactive/asynchronous.

Giá trị `true` nghĩa là tên key đã bị xóa, **không** xác nhận bộ nhớ đã được hệ điều hành trả lại. `false` khi key không tồn tại là kết quả bình thường cho thao tác xóa idempotent.

### 4.2. Serializer và namespace phải khớp

Redis lưu tên key dưới dạng byte. Key tạo bởi `StringRedisTemplate` hoặc `redis-cli` có thể không khớp với key được mã hóa theo serializer khác của `RedisTemplate<Object, Object>`. Nếu `delete("session:42")` trả `false` dù CLI nhìn thấy tên tương tự, hãy kiểm tra:

- Serializer của key lúc **ghi** và lúc **xóa** có trùng nhau hay không.
- Ứng dụng kết nối đúng Redis instance, database logic hoặc cluster hay không.
- Tiền tố namespace và quy tắc đặt tên key có nhất quán hay không.

Không thay đổi serializer của key đang hoạt động trong production mà thiếu phương án tương thích hoặc chuyển đổi dữ liệu.

## 5. Dọn nhiều key: SCAN kết hợp UNLINK theo lô

Giả sử cần dọn cache cũ với tiền tố `report:archive:`. Có hai nguồn gây chậm:

1. **Tìm key:** `KEYS report:archive:*` quét toàn bộ keyspace trong một lệnh, có thể gây chặn Redis khi dữ liệu lớn.
2. **Xóa giá trị:** `DEL` trên các đối tượng lớn có thể tốn thời gian giải phóng bộ nhớ trong luồng xử lý lệnh.

Cách thường dùng là quét tăng dần bằng `SCAN` rồi `UNLINK` theo lô vừa phải. `SCAN` trả cursor, **không** phải ảnh chụp nhất quán của keyspace; nó có thể trả key trùng lặp và có giới hạn đảm bảo khi dữ liệu thay đổi giữa lúc quét. Với việc dọn cache, xóa lặp lại cùng key thường là thao tác an toàn.

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ArchivedReportCleanup {

    private static final int BATCH_SIZE = 200;
    private final StringRedisTemplate redisTemplate;

    public ArchivedReportCleanup(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public long unlinkArchivedReports() {
        ScanOptions options = ScanOptions.scanOptions()
                .match("report:archive:*")
                .count(500)
                .build();

        List<String> batch = new ArrayList<>(BATCH_SIZE);
        long removedCount = 0;

        // Luôn đóng cursor sau khi dùng.
        try (Cursor<String> cursor = redisTemplate.scan(options)) {
            while (cursor.hasNext()) {
                batch.add(cursor.next());
                if (batch.size() == BATCH_SIZE) {
                    removedCount += unlinkBatch(batch);
                    batch.clear();
                }
            }
        }

        if (!batch.isEmpty()) {
            removedCount += unlinkBatch(batch);
        }
        return removedCount;
    }

    private long unlinkBatch(List<String> keys) {
        Long removed = redisTemplate.unlink(keys);
        if (removed == null) {
            throw new IllegalStateException("Thiếu kết quả UNLINK của batch");
        }
        return removed;
    }
}
```

`COUNT 500` là **gợi ý** cho số key trong mỗi lần quét, không bảo đảm trả đúng 500 key. `BATCH_SIZE = 200` chỉ là số minh họa; chọn dựa trên số key, độ trễ và tải thực tế. Nếu dọn hàng triệu key, nên giới hạn tốc độ, chia lịch công việc và theo dõi tài nguyên vì `UNLINK` vẫn tiêu tốn CPU để giải phóng dữ liệu ở luồng nền.

Trong Redis Cluster, thao tác nhiều key có thể chịu ràng buộc về **hash slot**. Không mặc định rằng danh sách key bất kỳ có thể truyền cho một lệnh `DEL`/`UNLINK` trên mọi triển khai cluster. Có thể nhóm key cùng slot bằng hash tag đã thiết kế trước, hoặc xử lý theo key/slot phù hợp với driver; việc `SCAN` trên cluster cũng cần bao phủ các node liên quan. Hãy kiểm tra khả năng định tuyến của cấu hình đang dùng trước khi dọn dữ liệu lớn.

## 6. Chọn lệnh theo tình huống

| Tình huống | Lựa chọn khởi đầu | Giải thích |
|---|---|---|
| Xóa key String nhỏ của phiên đăng nhập | `DEL` hoặc `UNLINK` | Chi phí giải phóng thường thấp; `DEL` đơn giản |
| Xóa key chứa hàng trăm nghìn phần tử | `UNLINK` | Tránh chặn Redis do giải phóng cấu trúc lớn |
| Xóa nhiều cache key sau thay đổi dữ liệu nguồn | `UNLINK` theo lô | Chuyển phần thu hồi tốn kém sang nền |
| Dọn cache theo tiền tố trong production | `SCAN` + `UNLINK` theo lô | Tránh quét toàn bộ keyspace bằng `KEYS` |
| Dữ liệu chỉ cần hết hạn theo thời gian | Đặt TTL bằng `EXPIRE` hoặc khi ghi | Redis tự quản lý việc hết hạn, giảm nhu cầu xóa thủ công |
| Chỉ xóa một field của Hash | `HDEL` | `DEL` và `UNLINK` xóa **cả key**, không phải một field |

Hai lệnh có cùng mục tiêu nghiệp vụ là xóa tên key. Khác biệt chủ yếu là thời gian xử lý lệnh và cách phân bổ công việc giải phóng bộ nhớ.

## 7. Những nhầm lẫn cần tránh

**“UNLINK trả về trước khi key biến mất.”** Sai. Redis gỡ key khỏi keyspace trong khi xử lý `UNLINK`. Phần được hoãn là việc thu hồi bộ nhớ. Sau khi lệnh thành công, lệnh đọc tiếp theo không còn thấy giá trị cũ qua tên key đó.

**“UNLINK làm bộ nhớ hệ điều hành giảm ngay.”** Không có bảo đảm này. Đối tượng có thể còn đợi lazy free; sau khi giải phóng, bộ cấp phát vẫn có thể giữ vùng nhớ để tái sử dụng.

**“UNLINK không tạo tải.”** Sai. Redis vẫn tra cứu và gỡ key; luồng nền vẫn cần CPU để giải phóng đối tượng. Một đợt xóa khổng lồ có thể tạo hàng đợi công việc nền và áp lực tài nguyên. Cần điều chỉnh kích thước lô và tránh thiết kế big key ngay từ đầu.

**“Xóa xong thì key không thể xuất hiện lại.”** Sai nếu tiến trình khác tiếp tục ghi vào cùng tên key. Đây là vấn đề tranh chấp giữa các thao tác nghiệp vụ; nếu cần kiểm soát, dùng phiên bản dữ liệu, điều kiện ghi hoặc cơ chế đồng bộ phù hợp. Đổi `DEL` thành `UNLINK` không xử lý race condition.

**“Kết quả `null` từ RedisTemplate nghĩa là không xóa được.”** Sai trong pipeline/transaction. Phải lấy và diễn giải kết quả tại thời điểm thực thi tương ứng.

**“DEL/UNLINK có thể thay HDEL/SREM.”** Hai lệnh xóa **toàn bộ key**. Để loại bỏ một field của Hash dùng `HDEL`, một member của Set dùng `SREM`; các kiểu dữ liệu khác có lệnh chỉnh sửa phần tử riêng.

## 8. Nguyên tắc vận hành

Trước khi dọn Redis có lưu lượng cao, nên biết **kích thước giá trị**, **số key cần xóa**, và **ngưỡng độ trễ chấp nhận được**. Một big key thường là dấu hiệu cần xem lại mô hình dữ liệu chứ không chỉ đổi lệnh xóa.

Với dữ liệu ngắn hạn, đặt TTL và namespace rõ ràng ngay khi tạo. Với dọn theo tiền tố, dùng `SCAN` và xóa có kiểm soát. Theo dõi độ trễ, `SLOWLOG`, bộ nhớ và số tác vụ lazy free đang chờ. Đo trên dữ liệu đại diện trước khi quyết định batch size cho production.

**Ghi nhớ:** `DEL` thường vừa gỡ key vừa giải phóng giá trị trong quá trình xử lý lệnh (trừ khi cấu hình lazy free thay đổi hành vi); `UNLINK` ưu tiên gỡ key nhanh, chuyển phần việc thu hồi tốn kém sang nền. Trong cả hai trường hợp, khi lệnh hoàn tất, tên key không còn ánh xạ đến dữ liệu cũ.

## Tài liệu tham khảo

- [Redis — DEL](https://redis.io/docs/latest/commands/del/): cú pháp, độ phức tạp, giá trị trả về.
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/): gỡ key và giải phóng bộ nhớ nền.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): quét theo cursor và các giới hạn.
- [Spring Data Redis — RedisOperations API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/RedisOperations.html): các phương thức `delete`, `unlink` và `scan`.
