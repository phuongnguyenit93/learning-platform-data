# Vì sao cần thận trọng với KEYS và các lệnh quét dữ liệu lớn?

## 1. Một thao tác tìm khóa có thể ảnh hưởng đến cả hệ thống

Giả sử một ứng dụng Spring Boot dùng Redis để lưu thông tin phiên đăng nhập, bộ nhớ đệm sản phẩm và giới hạn số lần gọi API:

~~~text
session:1234
session:5678
product:cache:1001
product:cache:1002
rate-limit:user:42
...
~~~

Khi cần kiểm tra hoặc dọn bộ nhớ đệm sản phẩm, cách làm có vẻ tự nhiên là tìm mọi khóa bắt đầu bằng `product:cache:`, rồi xóa chúng. Người mới học Redis có thể viết:

~~~redis
KEYS product:cache:*
~~~

Hoặc gọi trực tiếp trong Spring Data Redis:

~~~java
Set<String> keys = stringRedisTemplate.keys("product:cache:*");
~~~

Cả hai cách đều có một vấn đề: **Redis phải duyệt qua không gian khóa của cơ sở dữ liệu để xác định khóa nào khớp**, kể cả khi kết quả chỉ gồm vài khóa. Khi số khóa tăng đến hàng triệu và Redis đang phục vụ nhiều yêu cầu khác, thao tác quản trị tưởng nhỏ có thể làm tăng độ trễ của các yêu cầu nghiệp vụ.

Bài học này thuộc nhóm **Quản lý khóa** của **Spring Data Redis**. Mục tiêu là hiểu vì sao tìm kiếm hàng loạt cần thận trọng, cách quét tăng dần bằng `SCAN` và `Cursor`, cũng như khi nào nên thiết kế dữ liệu để khỏi phải quét.

## 2. Vì sao KEYS có thể gây nghẽn?

### 2.1. KEYS làm việc gì?

Cú pháp:

~~~redis
KEYS pattern
~~~

`pattern` dùng kiểu so khớp glob, chẳng hạn:

| Mẫu | Ý nghĩa |
|---|---|
| `KEYS *` | Tìm mọi khóa trong cơ sở dữ liệu Redis đang chọn |
| `KEYS session:*` | Tìm khóa có tiền tố `session:` |
| `KEYS product:cache:????` | Tìm khóa có đúng bốn ký tự sau tiền tố |
| `KEYS user:[12]:*` | Tìm khóa của các nhóm `user:1:` hoặc `user:2:` |

**Độ phức tạp của `KEYS` là O(N)**, trong đó `N` là số khóa phải xem xét, không phải chỉ số khóa được trả về. Ví dụ, kho có 5 triệu khóa nhưng chỉ có 10 khóa `product:cache:*` thì Redis vẫn phải thực hiện công việc phụ thuộc vào quy mô của kho khóa đó.

Kết quả của `KEYS` được trả về một lần. Nếu có rất nhiều khóa khớp mẫu, ngoài thời gian duyệt trên Redis, ta còn phải trả chi phí:

- Tạo và truyền một phản hồi lớn qua mạng.
- Giữ tập kết quả trong bộ nhớ của chương trình gọi, đặc biệt khi Spring Data Redis trả về `Set<String>`.
- Chuyển đổi dữ liệu khóa qua bộ mã hóa/giải mã (`serializer`).
- Xử lý toàn bộ kết quả ở phía ứng dụng, có thể dẫn tới thêm hàng nghìn hoặc hàng triệu lệnh khác.

### 2.2. Redis xử lý lệnh theo cách nào?

Phần xử lý thực thi lệnh Redis thông thường diễn ra tuần tự trên luồng xử lý lệnh chính. Khi một lệnh tốn nhiều thời gian CPU, các lệnh khác có thể phải chờ trước khi được phục vụ. Redis có các cơ chế I/O và tác vụ nền riêng, nhưng chúng không làm cho một lệnh `KEYS` dài trở thành thao tác không gây cản trở.

Ví dụ:

~~~text
Thời gian  ───────────────────────────────────────────────>

Client A: GET session:1234 ── ✓
Client B:                KEYS product:cache:* ────────── ✓
Client C:                      GET session:5678       ── ✓
Client D:                         INCR rate-limit:*  ─── ✓
                                  ↑
                           B và các lệnh sau
                           có thể tăng độ trễ
~~~

Một lệnh `KEYS` trong môi trường thử nghiệm ít dữ liệu có thể chạy nhanh. Nhưng **thời gian thực thi trong thử nghiệm không đủ để bảo đảm an toàn ở production**, nơi quy mô dữ liệu, tải đồng thời, phần cứng và cách tổ chức Redis có thể khác biệt.

### 2.3. Ví dụ lỗi thiết kế dễ gặp

~~~java
@Service
public class CacheMaintenanceService {

    private final StringRedisTemplate redis;

    public CacheMaintenanceService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    // Không phù hợp để gọi trên đường xử lý request có tải cao.
    public long deleteAllProductCache() {
        Set<String> keys = redis.keys("product:cache:*");

        if (keys == null || keys.isEmpty()) {
            return 0L;
        }

        Long deleted = redis.delete(keys);
        return deleted == null ? 0L : deleted;
    }
}
~~~

Đoạn này có hai rủi ro riêng biệt:

1. `keys(...)` có thể quét toàn bộ không gian khóa và tạo tập kết quả rất lớn.
2. `delete(keys)` có thể thực hiện một lượt xóa khối lượng lớn. Với các giá trị có cấu trúc lớn, việc giải phóng bộ nhớ đồng bộ còn làm tăng thời gian bận của Redis.

Chỉ chuyển `KEYS` sang một tác vụ chạy nền trong Spring Boot không giải quyết được phần Redis vẫn phải xử lý lệnh nặng.

## 3. SCAN chia việc quét thành những lượt nhỏ

Redis cung cấp họ lệnh quét tăng dần:

| Lệnh | Phạm vi quét |
|---|---|
| `SCAN` | Các khóa của cơ sở dữ liệu Redis |
| `HSCAN` | Các trường và giá trị trong một Hash |
| `SSCAN` | Các phần tử của một Set |
| `ZSCAN` | Các phần tử và điểm số trong một Sorted Set |

`SCAN` không trả toàn bộ kết quả trong một lần gọi. Nó nhận một **con trỏ (cursor)**, trả về một con trỏ mới cùng danh sách khóa ở lượt hiện tại. Bên gọi dùng con trỏ mới để tiếp tục.

~~~redis
SCAN 0 MATCH product:cache:* COUNT 200
~~~

Hình dung một chu kỳ quét:

~~~text
SCAN 0 MATCH product:cache:* COUNT 200
    │
    ├── cursor tiếp theo: 348
    └── danh sách khóa: [product:cache:1, product:cache:5, ...]

SCAN 348 MATCH product:cache:* COUNT 200
    │
    ├── cursor tiếp theo: 772
    └── danh sách khóa: [product:cache:9, ...]

SCAN 772 MATCH product:cache:* COUNT 200
    │
    ├── cursor tiếp theo: 0
    └── danh sách khóa: [...]
    
cursor = 0 ở KẾT QUẢ của lượt gọi ⇒ hoàn tất một vòng quét
~~~

Các số cursor trên chỉ minh họa; giá trị thực phụ thuộc trạng thái dữ liệu.

### 3.1. COUNT là gợi ý về lượng công việc

`COUNT 200` **không có nghĩa** Redis chắc chắn trả đúng 200 khóa, hoặc không bao giờ trả nhiều hơn 200 khóa. Đây là gợi ý điều chỉnh lượng công việc thực hiện ở mỗi lượt.

Redis có thể trả ít hơn, nhiều hơn hoặc thậm chí không trả khóa nào trong một lượt quét. Nếu con trỏ trả về vẫn khác `0`, vòng quét **chưa kết thúc**, dù danh sách khóa của lượt đó trống.

Tăng `COUNT` thường làm giảm số lượt đi về mạng nhưng có thể tăng thời gian của từng lệnh. Giảm `COUNT` giúp chia nhỏ công việc nhưng tăng số lượt truy cập. Giá trị phù hợp phụ thuộc kích thước dữ liệu, độ trễ Redis, mạng và tải của hệ thống; không có một con số mặc định an toàn cho mọi ứng dụng.

### 3.2. MATCH không làm SCAN trở thành truy vấn có chỉ mục

`MATCH product:cache:*` lọc kết quả phù hợp với mẫu. Redis vẫn phải đi qua các phần của không gian khóa để tìm kết quả. Nó không tự tạo chỉ mục cho tiền tố `product:cache:`.

Nếu chỉ 1 trong 100.000 khóa có tiền tố cần tìm, nhiều lượt quét có thể trả danh sách rỗng; tổng lượng công việc vẫn đáng kể. **`SCAN` làm giảm rủi ro của một lệnh chạy dài, nhưng không xóa bỏ tổng chi phí quét.**

Về độ phức tạp, một lời gọi `SCAN` có chi phí trung bình nhỏ, trong khi một vòng quét đầy đủ có tổng chi phí **O(N)**. Thời gian thực của từng lượt vẫn bị ảnh hưởng bởi `COUNT`, mẫu lọc và trạng thái cấu trúc dữ liệu.

### 3.3. SCAN không cung cấp bản chụp dữ liệu nhất quán

Trong khi vòng quét diễn ra, ứng dụng khác có thể thêm, xóa hoặc làm hết hạn khóa. Do đó:

- Một khóa **có thể xuất hiện nhiều lần**. Tác vụ xử lý cần chịu được việc gặp lại cùng khóa.
- Khóa được thêm hoặc xóa trong thời gian quét **có thể xuất hiện hoặc không**, tùy thời điểm.
- Khóa tồn tại liên tục từ đầu đến cuối một vòng quét đầy đủ được Redis bảo đảm sẽ được trả về ít nhất một lần.
- Một vòng quét trên tập dữ liệu liên tục tăng không giới hạn có thể khó hoàn tất.
- Không thể coi kết quả của một vòng `SCAN` là danh sách khóa chính xác tại cùng một thời điểm.

Vì vậy, nếu cần xóa theo lô, cập nhật thống kê hoặc xử lý dữ liệu, hãy thiết kế thao tác **có thể thực hiện lặp lại an toàn (idempotent)**. Nếu yêu cầu nghiệp vụ đòi hỏi ảnh chụp nhất quán hoặc chính xác tuyệt đối, việc quét khóa đơn thuần không đáp ứng yêu cầu đó.

## 4. Dùng SCAN trong Spring Data Redis

### 4.1. Cách gọi phù hợp với StringRedisTemplate

Spring Data Redis hỗ trợ `scan(ScanOptions)` và trả về `Cursor<K>`. Ví dụ dưới đây lấy **tối đa 50 khóa mẫu** từ namespace bộ nhớ đệm, không tải tất cả khóa vào một tập lớn.

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheKeyInspector {

    private static final String PREFIX = "product:cache:";

    private final StringRedisTemplate redis;

    public ProductCacheKeyInspector(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Set<String> sampleKeys() {
        ScanOptions options = ScanOptions.scanOptions()
                .match(PREFIX + "*")
                .count(200)
                .build();

        Set<String> sample = new LinkedHashSet<>();

        // Cursor giữ tài nguyên kết nối trong thời gian quét.
        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext() && sample.size() < 50) {
                String key = cursor.next();

                if (key != null && key.startsWith(PREFIX)) {
                    sample.add(key);
                }
            }
        }

        return sample;
    }
}
~~~

Giải thích các điểm chính:

1. `StringRedisTemplate` dùng chuỗi cho tên khóa và giúp mã nguồn dễ đọc.
2. `ScanOptions` chỉ định mẫu lọc và `COUNT`. Đây vẫn là quét tăng dần, không phải tìm theo chỉ mục.
3. `Cursor<String>` cung cấp cách lặp kết quả mà không phải nhận toàn bộ danh sách khóa từ máy chủ trong một phản hồi.
4. Khối `try-with-resources` đóng cursor kể cả khi có ngoại lệ hoặc dừng sau 50 khóa. Đóng cursor giúp giải phóng tài nguyên kết nối mà Spring Data Redis đang giữ.
5. `LinkedHashSet` loại bỏ khóa trùng trong mẫu kết quả nhỏ. Bộ nhớ chỉ tăng đến giới hạn 50 phần tử trong ví dụ.
6. `startsWith(PREFIX)` giúp bảo vệ ý định xử lý namespace cụ thể; ở đây mẫu tiền tố cố định do ứng dụng kiểm soát.

Đây là chức năng lấy **mẫu để kiểm tra**, không phải hàm kiểm kê mọi khóa. Khi đạt đủ 50 phần tử, vòng quét được dừng có chủ đích.

> Trong một ứng dụng dùng Redis Cluster, phạm vi quét cần được xác minh theo cấu hình và driver. Một lượt `SCAN` của một nút chỉ quét khóa thuộc nút đó. Không nên mặc định rằng một cursor từ một kết nối bất kỳ bao phủ toàn bộ các nút trong cụm.

### 4.2. Vì sao không nên gọi keys() trong endpoint?

Hãy so sánh:

~~~java
// Có thể quét toàn bộ keyspace và trả tập kết quả lớn.
Set<String> allKeys = redis.keys("product:cache:*");

// Quét tăng dần; ứng dụng kiểm soát số khóa lưu trong bộ nhớ.
try (Cursor<String> cursor = redis.scan(
        ScanOptions.scanOptions()
                .match("product:cache:*")
                .count(200)
                .build())) {

    int inspected = 0;
    while (cursor.hasNext() && inspected < 100) {
        String key = cursor.next();
        // Xử lý nhanh, tránh tác dụng phụ khi có khóa lặp.
        inspected++;
    }
}
~~~

Giới hạn `inspected < 100` ở đây giới hạn **số phần tử chương trình nhận và xử lý**, không giới hạn chính xác 100 thao tác nội bộ của Redis hoặc tổng số khóa được xem xét. Mức công việc của `SCAN` còn phụ thuộc vào cách Redis tìm khóa phù hợp.

Với nhu cầu hiển thị danh sách phân trang cho người dùng cuối, cursor của Redis **không phải** số trang ổn định: dữ liệu có thể thay đổi, khóa có thể trùng và một lần gọi không bảo đảm số phần tử. Nếu chức năng nghiệp vụ cần phân trang ổn định hoặc sắp xếp, nên lưu chỉ mục phù hợp ngay từ đầu.

### 4.3. Quét để dọn dữ liệu: phải kiểm soát cả bước xử lý

Khi phải dọn khóa theo tiền tố, có thể dùng `SCAN` để thu nhận khóa theo lô nhỏ, sau đó dùng `UNLINK` để yêu cầu Redis giải phóng giá trị khỏi không gian khóa và thực hiện phần thu hồi bộ nhớ có chi phí lớn theo hướng không đồng bộ khi thích hợp.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

// Chỉ dành cho tác vụ bảo trì có phạm vi namespace xác định.
public long unlinkSomeProductCacheKeys(StringRedisTemplate redis) {
    String prefix = "product:cache:";
    ScanOptions options = ScanOptions.scanOptions()
            .match(prefix + "*")
            .count(200)
            .build();

    List<String> batch = new ArrayList<>(100);
    long submitted = 0;
    long maxSubmitted = 1_000;

    try (Cursor<String> cursor = redis.scan(options)) {
        while (cursor.hasNext() && submitted < maxSubmitted) {
            String key = cursor.next();

            if (key == null || !key.startsWith(prefix)) {
                continue;
            }

            batch.add(key);
            submitted++;

            if (batch.size() >= 100) {
                redis.unlink(batch);
                batch.clear();
            }
        }
    }

    if (!batch.isEmpty()) {
        redis.unlink(batch);
    }

    return submitted;
}
~~~

**Ý nghĩa và giới hạn của ví dụ:**

- `100` là kích thước lô gửi lệnh xóa; `1_000` là giới hạn số lần tiếp nhận khóa trong một lượt bảo trì. Hai con số chỉ là ví dụ để điều chỉnh theo đo đạc thực tế.
- Chỉ sử dụng tiền tố mà tác vụ được phép quản lý. Không ghép trực tiếp mẫu glob tùy ý do người dùng cung cấp rồi xóa hàng loạt.
- `submitted` đếm số lần đưa khóa vào lệnh, **không phải số khóa thực tế đã xóa**: cursor có thể trả trùng, khóa có thể hết hạn hoặc bị xóa bởi tiến trình khác; kết quả `unlink(...)` mới phản ánh số khóa mà Redis thực sự gỡ trong lệnh tương ứng.
- `UNLINK` giảm nguy cơ chặn Redis khi thu hồi bộ nhớ của giá trị lớn, nhưng không làm chi phí quét biến mất và không xóa bỏ mọi tác động lên CPU, bộ nhớ hay I/O.
- Không cần dồn mọi khóa trong toàn bộ hệ thống vào một danh sách trước khi xóa. Với tác vụ lớn, thường nên có các đợt xử lý nhỏ, giới hạn tốc độ, số lần chạy và khả năng tạm dừng.
- Khi có ghi mới liên tục vào cùng namespace, quét rồi xóa có thể ảnh hưởng cả khóa vừa tạo. Cần có quy tắc nghiệp vụ về tuổi dữ liệu hoặc phiên bản namespace thay vì mặc định xóa mọi thứ khớp mẫu.

Trong môi trường thực tế, thao tác xóa phải được kiểm soát bởi tác vụ vận hành có quyền và phạm vi rõ ràng, thay vì được gọi ngẫu nhiên từ request người dùng.

## 5. Những lệnh khác cũng có thể gây tải lớn

Cẩn thận với `KEYS` không có nghĩa chỉ cần thay mọi `KEYS` bằng `SCAN`. Các lệnh lấy **toàn bộ một cấu trúc dữ liệu lớn** cũng có thể tạo phản hồi nặng và tốn thời gian xử lý.

| Nhu cầu | Thao tác có nguy cơ khi dữ liệu lớn | Hướng xử lý |
|---|---|---|
| Liệt kê khóa toàn cơ sở dữ liệu | `KEYS *` hoặc `KEYS prefix:*` | `SCAN` theo lô, giới hạn mục đích và tốc độ |
| Đọc toàn bộ Set | `SMEMBERS key` | `SSCAN` hoặc thiết kế truy cập theo phần tử |
| Đọc toàn bộ Hash | `HGETALL key` | `HSCAN` hoặc `HMGET` các field cần thiết |
| Đọc toàn bộ Sorted Set | `ZRANGE key 0 -1` | Chia phạm vi theo thứ hạng/điểm số, hoặc `ZSCAN` khi cần duyệt |
| Đọc toàn bộ List | `LRANGE key 0 -1` | `LRANGE` theo những đoạn nhỏ |
| Xóa nhiều khóa/giá trị lớn | `DEL` với lượng lớn dữ liệu | Lô nhỏ; cân nhắc `UNLINK` với ngữ nghĩa phù hợp |
| Kiểm kê mọi giá trị trong một request | Nhiều vòng đọc và xử lý không giới hạn | Tách tác vụ nền, đặt ngân sách tài nguyên, dùng chỉ mục |

`SCAN` là công cụ quét khóa của database, còn `HSCAN`, `SSCAN`, `ZSCAN` quét **phần tử trong một cấu trúc dữ liệu**. Chúng không thay thế lẫn nhau. Riêng `LRANGE` thường cần chia theo khoảng chỉ số; Redis không có `LSCAN` tương ứng.

Cũng cần tách biệt **quét** và **xử lý sau quét**. Dùng `SCAN` rồi gọi một lệnh đọc giá trị cực lớn cho mỗi khóa, hoặc gửi một lô `UNLINK` khổng lồ, vẫn có thể làm hệ thống chịu tải cao.

## 6. Thiết kế dữ liệu để không phải quét mọi khóa

Cách tốt hơn cho nhiều yêu cầu nghiệp vụ là biết trước khóa hoặc duy trì một cấu trúc dữ liệu truy cập có chủ đích.

### 6.1. Biết khóa từ định danh nghiệp vụ

Nếu API đã biết mã sản phẩm `1001`, hãy truy cập trực tiếp:

~~~java
String key = "product:cache:1001";
String value = redis.opsForValue().get(key);
~~~

Truy cập khóa đã biết tránh quét tìm theo mẫu.

### 6.2. Dùng TTL cho dữ liệu tạm

Bộ nhớ đệm nên có thời hạn sống nếu nghiệp vụ cho phép:

~~~java
redis.opsForValue().set(
        "product:cache:1001",
        jsonPayload,
        java.time.Duration.ofMinutes(15)
);
~~~

Với TTL phù hợp, Redis tự hết hạn khóa. Nhu cầu chạy một tác vụ quét để dọn toàn bộ cache sẽ giảm đáng kể. Tuy nhiên, TTL không thay thế những yêu cầu cần thu hồi ngay lập tức.

### 6.3. Duy trì chỉ mục riêng khi cần liệt kê

Nếu thường xuyên cần biết các sản phẩm thuộc một danh mục, có thể duy trì một Set chỉ mục:

~~~redis
SADD category:42:product-ids 1001 1002 1003
SMEMBERS category:42:product-ids
~~~

Đối với tập rất lớn, cũng cần tránh `SMEMBERS` và có thể dùng `SSCAN` hoặc một cách truy vấn phân trang thích hợp.

Duy trì chỉ mục yêu cầu xử lý tính nhất quán giữa khóa dữ liệu và chỉ mục khi thêm/xóa/hết hạn. Chẳng hạn, khóa cache tự hết hạn nhưng thành viên trong Set không tự biến mất. Vì vậy, chỉ mục này là lựa chọn kiến trúc có chi phí cập nhật và làm sạch riêng, không phải giải pháp miễn phí.

### 6.4. Đổi phiên bản namespace để vô hiệu hóa cache

Nếu nhiệm vụ là vô hiệu hóa toàn bộ cache của một nhóm dữ liệu, có thể dùng phiên bản:

~~~text
product:cache:v17:1001
product:cache:v17:1002

Đổi phiên bản đang dùng từ v17 sang v18:

product:cache:v18:1001
product:cache:v18:1002
~~~

Các request mới chỉ truy cập `v18`. Khóa thuộc `v17` tự hết hạn theo TTL. Cách này giúp tránh phải quét và xóa tất cả khóa ngay tại thời điểm thay đổi phiên bản, với điều kiện ứng dụng quản lý phiên bản cache nhất quán.

## 7. Nguyên tắc vận hành với dữ liệu lớn

Một số nguyên tắc thực hành có ích khi viết ứng dụng hoặc tác vụ quản trị Redis:

1. **Xác định phạm vi trước khi quét.** Biết chính xác database, namespace, chủ sở hữu khóa và tác động của việc truy xuất hoặc xóa.
2. **Không đặt lệnh quét toàn kho trong luồng request nhạy cảm độ trễ.** Nếu phải quét, dùng tác vụ bảo trì có giới hạn tốc độ và tài nguyên.
3. **Đặt giới hạn thời gian, số khóa, độ lớn lô và khả năng dừng.** Ngay cả `SCAN` vẫn có thể tốn thời gian nếu một tác vụ chạy liên tục đến khi hết mọi khóa.
4. **Đóng cursor.** Với Spring Data Redis, `Cursor` cần được đóng sau khi xử lý để tránh giữ tài nguyên kết nối.
5. **Chấp nhận trùng lặp và thay đổi đồng thời.** Chỉ thực hiện hành động an toàn khi lặp lại; không dựa vào `SCAN` để đếm chính xác dữ liệu đang thay đổi.
6. **Quan sát thực tế.** Đo độ trễ lệnh, CPU, bộ nhớ, băng thông, số lệnh mỗi giây và độ trễ phía ứng dụng trong lúc quét. `SLOWLOG` và `LATENCY DOCTOR` có thể hỗ trợ điều tra các đợt chậm.
7. **Xem xét mô hình triển khai.** Trong Redis Cluster, việc quét cần lưu ý khóa phân bố theo các nút; trong môi trường nhiều tenant, mẫu khóa rộng có thể đụng dữ liệu ngoài phạm vi mong muốn.
8. **Ưu tiên dữ liệu có thể truy cập trực tiếp.** TTL, chỉ mục có chủ đích và phiên bản cache thường phù hợp hơn việc định kỳ tìm mọi khóa bằng mẫu.

## 8. Thực hành: đối chiếu KEYS và SCAN trong môi trường thử nghiệm

Thực hiện trên Redis phát triển hoặc cơ sở dữ liệu thử nghiệm, không dùng kho dữ liệu production chung.

Tạo vài khóa mẫu:

~~~redis
SET product:cache:1001 "A"
SET product:cache:1002 "B"
SET product:cache:1003 "C"
SET session:1 "user-1"
~~~

Tìm khóa bằng `KEYS`:

~~~redis
KEYS product:cache:*
~~~

Quét tăng dần:

~~~redis
SCAN 0 MATCH product:cache:* COUNT 2
~~~

Lấy con trỏ trong phản hồi trước và tiếp tục:

~~~redis
SCAN <cursor-tu-luot-truoc> MATCH product:cache:* COUNT 2
~~~

Lặp lại cho đến khi **con trỏ trả về là `0`**. Nếu một lượt không trả khóa nào nhưng cursor còn khác `0`, vẫn phải tiếp tục. Không giả định số khóa trả về bằng giá trị `COUNT`.

Có thể dùng công cụ dòng lệnh để tự quét các khóa thuộc một tiền tố:

~~~bash
redis-cli --scan --pattern 'product:cache:*'
~~~

Công cụ trên giúp thực hiện việc lặp cursor. Nhưng nếu không giới hạn kết quả và in ra hàng triệu khóa, máy người dùng vẫn phải nhận và xử lý lượng dữ liệu lớn; sử dụng `--scan` không tự động bảo đảm tác vụ nhẹ.

### Câu hỏi kiểm tra hiểu biết

**Tình huống A:** Database có 2 triệu khóa, chỉ 20 khóa bắt đầu bằng `invoice:`. Gọi `KEYS invoice:*` có phải chỉ duyệt 20 khóa không?

Không. Chi phí tìm kiếm vẫn phụ thuộc vào quy mô không gian khóa được duyệt. Số kết quả ít không đồng nghĩa công việc ít.

**Tình huống B:** `SCAN 0 MATCH invoice:* COUNT 100` trả một mảng rỗng và cursor `912`. Có thể kết luận không tồn tại khóa phù hợp không?

Không. Phải tiếp tục với cursor `912` cho tới khi nhận cursor `0`, trừ khi chủ động dừng theo giới hạn tác vụ.

**Tình huống C:** Một tác vụ quét thấy cùng khóa hai lần và cần tăng biến đếm nghiệp vụ. Điều gì có thể xảy ra?

Nếu tăng mỗi lần xuất hiện, số đếm có thể lớn hơn thực tế. Cần chiến lược chống trùng, nguồn dữ liệu phù hợp hơn để đếm chính xác, hoặc thiết kế thao tác idempotent.

**Tình huống D:** Thay `DEL` bằng `UNLINK` rồi dùng `KEYS *` để lấy hàng triệu khóa trước khi xóa có an toàn không?

Không. `UNLINK` có thể giảm chi phí thu hồi bộ nhớ đồng bộ, nhưng `KEYS *` vẫn quét toàn bộ keyspace và tạo kết quả lớn. Nên xem lại mục tiêu xóa, phạm vi, cơ chế TTL/namespace và cách xử lý thành các lô giới hạn.

## 9. Ghi nhớ

- `KEYS` hữu ích cho khám phá dữ liệu nhỏ hoặc xử lý đặc biệt có kiểm soát, nhưng có độ phức tạp **O(N)** và có thể làm tăng độ trễ Redis khi kho khóa lớn.
- `SCAN` phân chia việc duyệt thành nhiều lượt; **không** biến tìm kiếm theo mẫu thành tra cứu có chỉ mục hoặc cung cấp ảnh chụp dữ liệu nhất quán.
- `COUNT` là gợi ý; cursor trả về `0` mới biểu thị kết thúc vòng quét.
- Trong Spring Data Redis, ưu tiên `scan(ScanOptions)` và **đóng `Cursor`**, đồng thời giới hạn dữ liệu lưu trong bộ nhớ và công việc phía ứng dụng.
- Nếu nhu cầu truy cập lặp đi lặp lại, hãy cân nhắc thiết kế khóa, TTL, cấu trúc chỉ mục hoặc phiên bản cache để không phải quét toàn bộ dữ liệu.

### Tài liệu tham khảo

- Redis — [KEYS](https://redis.io/docs/latest/commands/keys/).
- Redis — [SCAN và họ lệnh SCAN](https://redis.io/docs/latest/commands/scan/).
- Spring Data Redis — [RedisTemplate API](https://docs.spring.io/spring-data-redis/docs/3.5.x/api/org/springframework/data/redis/core/RedisTemplate.html).
