# Phân biệt thao tác một nút với thao tác toàn Redis Cluster

Trong Spring Data Redis, cùng một tên lệnh như `KEYS`, `SCAN` hay `FLUSHDB` có thể mang ý nghĩa rất khác nhau tùy **lệnh được gửi đến một Redis server** hay **Spring Data Redis chủ động phối hợp nhiều server**. Hiểu sai phạm vi thực thi dễ dẫn đến hai vấn đề đối lập: kiểm tra không thấy đủ khóa dù dữ liệu vẫn tồn tại, hoặc vô tình quét/xóa dữ liệu trên quy mô lớn hơn dự kiến.

Bài học này tập trung vào **quản lý khóa** trong Redis Cluster: xác định khóa nằm ở đâu, nhận biết thao tác chỉ ảnh hưởng đến một node, thực hiện thao tác cần bao phủ toàn cluster và lựa chọn API phù hợp trong Spring Data Redis.

## 1. Redis Cluster phân chia dữ liệu như thế nào?

Redis Cluster chia không gian khóa thành **16.384 hash slot** (từ `0` đến `16383`). Mỗi khóa được ánh xạ đến một slot; mỗi **primary node** (còn gọi là *master*) chịu trách nhiệm một tập slot. Replica sao chép dữ liệu của primary để hỗ trợ khả dụng cao, không phải một phân vùng dữ liệu độc lập cần cộng thêm vào kết quả thống kê.

Ví dụ mô hình ba primary:

```text
                    Ứng dụng Spring Data Redis
                               |
                     Cluster-aware client
                               |
              +----------------+----------------+
              |                |                |
        Primary A         Primary B         Primary C
        slots 0–5460      slots 5461–10922   slots 10923–16383
          /                    |                    \
     Replica A             Replica B             Replica C

  key1 → slot 3200  → A
  key2 → slot 8000  → B
  key3 → slot 14000 → C
```

Các slot và tên khóa trong sơ đồ mang tính minh họa. Trong cluster thực tế, tính slot từ tên khóa rồi tra bảng phân bổ slot hiện tại để xác định node sở hữu. Khi failover hoặc resharding, node sở hữu slot có thể thay đổi.

Điều quan trọng là phân biệt ba khái niệm:

1. **Thao tác trên một khóa**: ví dụ `GET key`, `TTL key`, `EXPIRE key 60`, `DEL key`. Client biết tên khóa, tính slot và định tuyến đến primary phù hợp. Dù gửi qua bất kỳ địa chỉ khởi tạo nào, phạm vi dữ liệu vẫn là khóa đó.
2. **Thao tác trên một node**: ví dụ thực thi `SCAN`, `KEYS`, `DBSIZE` trực tiếp trên Primary A. Lệnh chỉ quan sát tập khóa mà A đang phục vụ; không tự đến B và C.
3. **Thao tác toàn cluster**: ứng dụng/client lần lượt hoặc song song làm việc với các primary cần thiết và tổng hợp kết quả. Đây là **cơ chế phối hợp ở phía client**, không mặc nhiên là một lệnh Redis nguyên tử áp dụng cho mọi node.

> **Chú ý:** “Kết nối đến cluster” không đồng nghĩa “mọi lệnh chạy trên toàn cluster”. Cần xem API cụ thể có định tuyến theo khóa, chọn một node hay tự *fan-out* sang nhiều primary.

## 2. Bảng đối chiếu phạm vi những lệnh quản lý khóa

| Thao tác | Khi chạy trên một Redis node | Khi muốn xét toàn Redis Cluster | Điều cần nhớ |
|---|---|---|---|
| `GET`, `SET`, `TTL`, `EXPIRE`, `DEL` với **một khóa** | Client cluster-aware định tuyến theo slot của khóa | Không cần quét mọi node; khóa vẫn có một primary sở hữu | Đừng nhầm “một khóa” với “một node bất kỳ” |
| `KEYS pattern` | Chỉ trả về khóa khớp trên node nhận lệnh | Gửi đến từng primary rồi hợp nhất tập kết quả | `KEYS` quét keyspace theo cách có thể chặn xử lý, rất rủi ro khi dữ liệu lớn |
| `SCAN cursor MATCH pattern` | Duyệt từng phần keyspace của **node đó** | Duyệt riêng từng primary, mỗi node có cursor của nó | `SCAN` không cung cấp snapshot toàn cluster; có thể trả lại khóa trùng |
| `DBSIZE` | Đếm khóa trên node nhận lệnh | Thu thập số đếm từ các primary rồi cộng | Kết quả là ảnh chụp tại các thời điểm khác nhau, không nhất thiết nhất quán tuyệt đối |
| `RANDOMKEY` | Lấy khóa ngẫu nhiên từ node hiện tại | Cần cơ chế chọn/lấy mẫu trên các primary | Chọn ngẫu nhiên một node rồi lấy khóa có thể làm mẫu bị lệch |
| `FLUSHDB`, `FLUSHALL` | Xóa keyspace trên node nhận lệnh | Thực hiện có chủ đích trên toàn bộ primary | Tác vụ phá hủy dữ liệu; gọi trên một node **không** có nghĩa toàn cluster đã sạch |
| `MGET`, `MSET`, `RENAME` và lệnh nhiều khóa | Redis Cluster ràng buộc hash slot cho nhiều lệnh nguyên tử | Một số API của Spring Data Redis có thể tách lệnh để hỗ trợ nhiều slot; không phải lệnh nào cũng hỗ trợ | Không giả định các thao tác nhiều khóa ở nhiều slot đều được chấp nhận hay vẫn nguyên tử |

Trong Redis Cluster chuẩn, chỉ dùng database logic số `0`; không phân chia dữ liệu bằng `SELECT 1`, `SELECT 2`,... như trên Redis standalone.

## 3. Thao tác trên **một khóa**: driver tự tìm node sở hữu

Với `StringRedisTemplate` được cấu hình để kết nối Redis Cluster, lập trình viên thường không cần biết khóa nằm ở primary nào khi thao tác với một khóa:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public class SessionKeyService {
    private final StringRedisTemplate redis;

    public SessionKeyService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void demo() {
        String key = "session:{user42}:token";

        redis.opsForValue().set(key, "abc123", Duration.ofMinutes(15));
        String value = redis.opsForValue().get(key);
        Long ttlSeconds = redis.getExpire(key);
        Boolean removed = redis.delete(key);

        // Mỗi lệnh ở trên nhắm đến cùng một khóa logic.
        // Driver cluster-aware định tuyến yêu cầu đến slot của key.
    }
}
```

Trong tên `session:{user42}:token`, phần `{user42}` là **hash tag**. Các khóa có cùng hash tag hợp lệ, ví dụ `session:{user42}:profile`, được tính vào cùng slot. Đây là kỹ thuật hữu ích khi ứng dụng cần dùng các thao tác nhiều khóa yêu cầu cùng slot; không có nghĩa các khóa đó luôn nằm trên cùng một máy vật lý mãi mãi nếu cluster thay đổi phân bổ slot.

Với một khóa đơn lẻ, sự khác biệt về địa chỉ kết nối ban đầu thường được driver xử lý qua metadata slot hoặc phản hồi chuyển hướng `MOVED`/`ASK`. Nhưng `KEYS` và `SCAN` không có một khóa mục tiêu cụ thể để driver định tuyến theo slot, nên phải xem phạm vi node hoặc cách API tổng hợp.

## 4. `KEYS`: kết quả một node và kết quả đã hợp nhất toàn cluster

### 4.1. Lệnh Redis `KEYS` là cục bộ theo node

Giả sử cluster có ba primary và chứa:

```text
Primary A: session:1001, cart:1001
Primary B: session:1002
Primary C: session:1003, product:10
```

Nếu gửi `KEYS session:*` **trực tiếp đến A**, kết quả chỉ có `session:1001`. Điều đó không chứng minh rằng `session:1002` và `session:1003` không tồn tại. Ngay cả `redis-cli -c` (hỗ trợ chuyển hướng theo slot) cũng không biến `KEYS` thành truy vấn khóa toàn cluster.

### 4.2. Spring Data Redis cung cấp hai phạm vi tường minh

`RedisClusterConnection` phân biệt:

```java
import java.nio.charset.StandardCharsets;
import java.util.Set;
import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisClusterNode;
import org.springframework.data.redis.connection.RedisConnectionFactory;

public class ClusterKeysExample {
    public static void run(RedisConnectionFactory factory,
                           RedisClusterNode selectedNode) {
        byte[] pattern = "session:*".getBytes(StandardCharsets.UTF_8);

        try (RedisClusterConnection connection = factory.getClusterConnection()) {
            // Chỉ hỏi một node được chỉ định.
            Set<byte[]> oneNodeKeys = connection.keys(selectedNode, pattern);

            // Spring Data Redis gửi KEYS đến các primary của cluster
            // và hợp nhất kết quả trả về.
            Set<byte[]> clusterKeys = connection.keys(pattern);
        }
    }
}
```

Đây là khác biệt có chủ ý trong Spring Data Redis: `keys(node, pattern)` chỉ hỏi node được chỉ định, còn `keys(pattern)` trên `RedisClusterConnection` có cơ chế gom khóa từ các primary. Khi chỉ cần khảo sát một node, API cấp cao `redisTemplate.opsForCluster().keys(node, pattern)` cũng biểu đạt phạm vi đó bằng đối tượng `RedisClusterNode`.

Hàm `RedisTemplate.keys(pattern)` thường ủy quyền đến lệnh `keys` trên kết nối đang dùng; với kết nối Redis Cluster, việc thu thập kết quả có thể diễn ra trên nhiều primary. Vì vậy **không lấy cảm giác “chỉ một lời gọi Java” để suy ra chi phí “chỉ một lệnh trên một node”**. Cần xem loại kết nối, driver và phiên bản thư viện đang triển khai.

**Tại sao tránh `KEYS` trong đường xử lý production?** Mỗi lệnh `KEYS` phải rà soát keyspace trên server nhận lệnh. Khi fan-out đến nhiều primary, ứng dụng có thể tạo tải lên toàn cluster và phải giữ một lượng lớn khóa trong bộ nhớ để hợp nhất kết quả. `KEYS` chỉ phù hợp cho môi trường kiểm thử nhỏ hoặc thao tác vận hành có kiểm soát chặt chẽ; với dữ liệu lớn, ưu tiên `SCAN`.

## 5. `SCAN`: duyệt khóa trên một node, rồi mở rộng ra toàn cluster

`SCAN` hoạt động theo cursor. Mỗi lần gọi server trả một phần khóa và cursor tiếp theo; lặp đến khi cursor quay về `0`. Khác với `KEYS`, ứng dụng có thể xử lý dần các kết quả, nhờ đó giảm thời gian chiếm dụng server của từng lần gọi.

Tuy vậy, **một cursor chỉ đại diện cho một keyspace trên một node**. Muốn khảo sát toàn cluster, cần lặp qua từng primary và giữ cursor riêng cho từng node. Không có “cursor SCAN toàn cluster” duy nhất trong giao thức Redis chuẩn.

### 5.1. Duyệt tất cả primary bằng Spring Data Redis

Đoạn mã sau sử dụng API `RedisClusterConnection.scan(node, options)` để biểu đạt rõ phạm vi từng lần quét. Ví dụ giả định tên khóa được lưu với serializer UTF-8, như `StringRedisSerializer`.

```java
import java.nio.charset.StandardCharsets;
import java.util.function.Consumer;
import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisClusterNode;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;

public class ClusterKeyScanner {
    private final RedisConnectionFactory factory;

    public ClusterKeyScanner(RedisConnectionFactory factory) {
        this.factory = factory;
    }

    public void forEachSessionKey(Consumer<String> consumeKey) {
        ScanOptions options = ScanOptions.scanOptions()
                .match("session:*")
                .count(500)  // Gợi ý kích thước mỗi lượt, không phải LIMIT cứng.
                .build();

        try (RedisClusterConnection connection = factory.getClusterConnection()) {
            for (RedisClusterNode node : connection.clusterGetNodes()) {
                if (!node.isMaster()) {
                    continue; // Không đếm thêm bản sao từ replica.
                }

                try (Cursor<byte[]> cursor = connection.scan(node, options)) {
                    while (cursor.hasNext()) {
                        String key = new String(
                                cursor.next(), StandardCharsets.UTF_8);
                        consumeKey.accept(key);
                    }
                }
            }
        }
    }
}
```

Ví dụ gọi:

```java
ClusterKeyScanner scanner = new ClusterKeyScanner(connectionFactory);
scanner.forEachSessionKey(key -> System.out.println("Found: " + key));
```

Ý nghĩa từng bước:

1. Lấy danh sách node từ topology của cluster.
2. Chỉ chọn `isMaster()` để không lặp lại dữ liệu replica.
3. Mở cursor `SCAN` **riêng** cho mỗi primary và xử lý khóa theo dòng; đóng cursor sau khi dùng.
4. Kết thúc khi đã quét xong các primary được phát hiện ở thời điểm bắt đầu.

Đây là ví dụ duyệt khóa, không phải một bộ quét production đầy đủ. Trong công việc định kỳ trên dữ liệu lớn, cần giới hạn tốc độ, đo số node đã quét, kiểm soát lỗi từng node, cân nhắc retry/checkpoint và xử lý việc thay đổi topology trong khi quét. Không nên âm thầm trả “đã hoàn tất” nếu một primary lỗi hoặc không truy cập được.

### 5.2. `SCAN` không tạo ảnh chụp nhất quán

Cần hiểu đúng các đặc tính sau:

- `COUNT 500` là **gợi ý** cho Redis; một lượt có thể trả ít hơn, nhiều hơn, thậm chí không có khóa phù hợp nhưng cursor vẫn chưa kết thúc.
- Một khóa có thể xuất hiện nhiều lần trong một vòng quét. Nếu xử lý yêu cầu không trùng, cần cơ chế khử trùng hoặc thao tác có tính idempotent.
- Khóa được thêm/xóa trong lúc quét có thể khiến kết quả khác nhau giữa các lượt. Khi resharding, một khóa có thể chuyển node, dẫn đến bỏ sót hoặc xử lý lại nếu chỉ duyệt topology cố định.
- Pattern `MATCH` lọc khóa phù hợp nhưng không đảm bảo không phải duyệt nhiều phần của keyspace. `SCAN` giảm độ chặn theo từng lượt; tổng chi phí quét vẫn đáng kể.
- Lớp ứng dụng phải đóng cursor/connection và tránh giữ toàn bộ khóa trong một `List`/`Set` khổng lồ khi có thể xử lý dần.

Nếu cần số liệu chính xác ở một thời điểm, `SCAN` không phải giao dịch snapshot xuyên cluster. Thiết kế thống kê/đối soát chuyên dụng hoặc cơ chế ngừng ghi và xác minh topology có thể cần thiết tùy yêu cầu nghiệp vụ.

## 6. `DBSIZE`, `FLUSHDB` và các lệnh quản trị: phạm vi rất dễ nhầm

Không phải lệnh quản trị nào cũng có ý nghĩa toàn cluster khi kết nối qua một client cluster-aware.

### `DBSIZE` trên một node

```bash
# Lệnh này được gửi đến đúng node ở 127.0.0.1:7000.
redis-cli -h 127.0.0.1 -p 7000 DBSIZE
```

Giá trị thu được là số khóa được node đó phục vụ, không phải tự động là tổng số khóa của các primary khác. Muốn ước lượng tổng trên cluster, lấy số đếm từ **từng primary** rồi cộng. Vì các primary không được đo đồng thời, kết quả không mang tính nhất quán nguyên tử; failover, resharding và ghi/xóa khóa trong quá trình đo đều ảnh hưởng kết quả.

### `FLUSHDB`/`FLUSHALL`: tuyệt đối xác định phạm vi trước khi dùng

Trong Redis Cluster, một lệnh `FLUSHDB` gửi trực tiếp đến một primary xóa dữ liệu của node đó; nó không phải một thao tác “xóa tất cả shard” chỉ vì node thuộc cluster. Redis Cluster chỉ có DB `0`, nên `FLUSHDB` và `FLUSHALL` có hiệu lực tương đương trên node về phạm vi DB. Xóa toàn cluster đòi hỏi thao tác riêng với các primary, hoặc API quản trị có hợp đồng fan-out rõ ràng.

Spring Data Redis có API quản trị theo node, chẳng hạn:

```java
// Ví dụ chữ ký API: redisTemplate.opsForCluster().flushDb(node);
// node ở đây là RedisClusterNode cụ thể, không biểu thị mọi primary.
```

Không nên đặt lệnh xóa toàn bộ keyspace trong logic xử lý yêu cầu người dùng. Việc xóa theo prefix nghiệp vụ cũng cần chọn cách quét và xóa có kiểm soát, thay vì biến pattern `session:*` thành một lệnh `FLUSHDB` (lệnh này xóa **mọi** khóa trên node, không lọc theo prefix).

## 7. Xóa theo mẫu trên toàn cluster: quy trình đúng về phạm vi

Giả sử nghiệp vụ cần loại bỏ các khóa `session:*` trên Redis Cluster. Cách tiếp cận có kiểm soát:

```text
Lấy topology cluster
         |
         v
Chọn danh sách primary
         |
         v
SCAN MATCH session:* trên primary A → xử lý khóa tìm thấy
         |
         v
SCAN MATCH session:* trên primary B → xử lý khóa tìm thấy
         |
         v
SCAN MATCH session:* trên primary C → xử lý khóa tìm thấy
         |
         v
Tổng hợp thống kê, lỗi, thời điểm quét và các node đã xử lý
```

Với mỗi khóa, ứng dụng có thể gọi `StringRedisTemplate.unlink(key)` để yêu cầu xóa không đồng bộ phần giải phóng bộ nhớ theo cơ chế Redis, hoặc `delete(key)` nếu có lý do cần `DEL`. Đây là các **thao tác trên khóa cụ thể**: driver tự định tuyến theo slot, kể cả khi khóa đã chuyển node từ lúc `SCAN` trả về. Một ví dụ thao tác sau khi đã xác định rõ và giới hạn danh sách khóa:

```java
// Chỉ gọi sau khi quy trình đã lọc đúng phạm vi khóa và kiểm soát tải.
for (String key : keysSelectedForDeletion) {
    redisTemplate.unlink(key);  // UNLINK cho từng khóa, định tuyến theo slot.
}
```

Đoạn mã này minh họa cách xóa một khóa bằng API có định tuyến; nó **không** phải bản triển khai tự động xóa toàn cluster. Trong hệ thống thực, thay `keysSelectedForDeletion` bằng luồng có giới hạn tốc độ/chunk, cân nhắc dry-run, ghi log/metric, giới hạn thời gian và điều kiện dừng. Không gom hàng triệu khóa vào bộ nhớ rồi mới bắt đầu xóa.

Lệnh `UNLINK` chỉ giải phóng bộ nhớ của giá trị ở chế độ nền sau khi tách khóa khỏi keyspace; việc gửi quá nhiều lệnh vẫn có thể tạo tải I/O/CPU lên cluster. Nếu dùng API xóa **nhiều** khóa trong cùng một lời gọi, phải xem nó xử lý quy tắc *cross-slot* ra sao; đừng mặc định một lệnh Redis nhiều khóa khác slot là hợp lệ.

## 8. Những tình huống dễ dẫn đến kết luận sai

### Tình huống A: “Kết nối tới node A, `GET` được key, nhưng `SCAN` của A không thấy key”

Không mâu thuẫn. `GET key` được driver định tuyến đến primary sở hữu slot của khóa; `SCAN` gửi thẳng đến A chỉ thấy khóa hiện nằm trên A. Hãy xác định slot và owner hiện tại trước khi kết luận dữ liệu bị mất.

### Tình huống B: “`KEYS` trong Spring trả nhiều khóa hơn `redis-cli KEYS`”

`RedisClusterConnection.keys(pattern)` có thể tự gọi `KEYS` trên tất cả primary và trả kết quả hợp nhất. `redis-cli` gửi `KEYS` đến đúng một node thì chỉ trả phạm vi của node đó. Cả hai hành vi có thể đúng, nhưng chi phí và ý nghĩa hoàn toàn khác nhau.

### Tình huống C: “Đã `SCAN` đến cursor `0` mà vẫn thiếu nhiều khóa”

Cursor `0` chỉ khẳng định hoàn tất vòng duyệt trên **node tương ứng**. Kiểm tra đã quét đủ mọi primary hay chưa, có lỗi giữa chừng không, bộ lọc `MATCH` có đúng không và cluster có vừa chuyển slot không. Nếu cần ảnh chụp nhất quán thì bản thân `SCAN` không đáp ứng được.

### Tình huống D: “Cộng `DBSIZE` của cả primary lẫn replica cho ra số khóa gấp đôi”

Replica chứa bản sao dữ liệu của primary. Để ước lượng tổng khóa logic, chỉ cộng từ primary; việc có nhiều replica không làm tăng số khóa logic của cluster.

### Tình huống E: “`MGET` hai key khác slot vẫn chạy nên `RENAME` cũng sẽ chạy”

Đây là suy luận sai. Spring Data Redis có thể tách một số lệnh nhiều khóa thành thao tác riêng theo slot rồi gộp kết quả (ví dụ `MGET` trên một số đường thực thi). Các lệnh đòi hỏi thao tác nguyên tử hoặc server-side trên nhiều khóa có thể báo `CROSSSLOT`. Cần kiểm tra API/lệnh cụ thể; nếu dùng transaction/script nhiều khóa, hãy thiết kế hash tag để các khóa liên quan cùng slot.

## 9. Quan sát cluster bằng `redis-cli` khi học và gỡ lỗi

Các câu lệnh bên dưới chỉ dùng để **quan sát** trong cụm thực hành. Thay host/port bằng địa chỉ node đang chạy:

```bash
# Thấy các node, vai trò và dải slot được quảng bá trong topology.
redis-cli -h 127.0.0.1 -p 7000 CLUSTER NODES

# Tính slot cho một khóa cụ thể.
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'session:{user42}:token'

# Xem số khóa của một node (không tự cộng toàn cluster).
redis-cli -h 127.0.0.1 -p 7000 DBSIZE

# Quét một node; lặp với cursor được trả về đến khi cursor là 0.
redis-cli -h 127.0.0.1 -p 7000 SCAN 0 MATCH 'session:*' COUNT 100

# Đọc một khóa: -c cho phép redis-cli theo chuyển hướng slot.
redis-cli -c -h 127.0.0.1 -p 7000 GET 'session:{user42}:token'
```

Khi `SCAN` trả cursor khác `0`, gọi tiếp `SCAN <cursor-mới> ...` **trên đúng node đó**. Để có góc nhìn toàn cluster, tìm các primary từ topology và thực hiện vòng lặp riêng trên mỗi primary. Đừng dùng `KEYS *` để dò toàn bộ production cluster; và đừng xem `CLUSTER NODES` là bằng chứng đã truy vấn khóa trên tất cả node: lệnh này chỉ trả **metadata topology**.

## 10. Chọn chiến lược theo mục tiêu

| Mục tiêu | Chiến lược phù hợp | Không nên giả định |
|---|---|---|
| Đọc/xóa/đặt TTL cho một khóa biết trước | `StringRedisTemplate`/`RedisTemplate` với key cụ thể | Phải tự tìm node rồi kết nối trực tiếp |
| Xem các khóa của một primary để gỡ lỗi | `scan(node, options)` hoặc `keys(node, pattern)` trên dữ liệu nhỏ | Kết quả đại diện cho toàn cluster |
| Tìm khóa theo prefix trên cả cluster | `SCAN` mỗi primary, xử lý streaming, theo dõi kết quả từng node | Có một cursor toàn cluster hoặc một snapshot nhất quán |
| Liệt kê nhanh toàn bộ khóa trong cụm lab nhỏ | `RedisClusterConnection.keys(pattern)` nếu đã hiểu chi phí | Đây là lựa chọn an toàn cho production lớn |
| Đếm số khóa | Thu `DBSIZE` từ mỗi primary, lưu ý tính thời điểm | Cộng cả replica; tổng là snapshot giao dịch |
| Xóa khóa theo prefix nghiệp vụ | Duyệt theo node rồi xóa **từng key** bằng lệnh có định tuyến, điều tiết tải | `FLUSHDB` có bộ lọc pattern |
| Dùng thao tác nhiều khóa | Kiểm tra giới hạn slot của lệnh; cân nhắc `{hashTag}` | Mọi lệnh nhiều khóa đều được Spring tự chia hoặc giữ tính nguyên tử |

## 11. Ghi nhớ khi thiết kế chức năng quản lý khóa

- **Một khóa xác định**: để cluster-aware driver định tuyến theo hash slot.
- **Một node xác định**: dùng API có tham số `RedisClusterNode` hoặc kết nối đến node đó; `SCAN`/`KEYS`/`DBSIZE` chỉ phản ánh phạm vi node.
- **Toàn cluster**: phải xác nhận rõ API nào thực hiện fan-out, API nào cần tự duyệt các primary và tổng hợp kết quả.
- **Replica**: là bản sao của primary, không cộng như một shard dữ liệu mới.
- **An toàn vận hành**: dùng `SCAN` cho duyệt lớn, đóng cursor, tránh lưu trữ toàn bộ kết quả, kiểm soát tốc độ, xử lý lỗi từng node và xem xét resharding/failover.

Điểm mấu chốt trong Spring Data Redis là **phạm vi thao tác do phương thức và cách kết nối quyết định**. Hai lời gọi cùng mang từ “keys” có thể một bên chỉ hỏi một primary, bên kia phát lệnh đến tất cả primary; nắm rõ điều đó giúp vừa không bỏ sót khóa vừa tránh tạo tải ngoài dự kiến lên Redis Cluster.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): định tuyến slot, khác biệt `keys(pattern)` và `keys(node, pattern)`, xử lý nhiều khóa.
- [Spring Data Redis — RedisClusterConnection API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/RedisClusterConnection.html): `keys`, `scan` và các thao tác theo node.
- [Spring Data Redis — ClusterOperations API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/ClusterOperations.html): thao tác quản trị có tham số node.
- [Redis — Scale with Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/): hash slot, primary, replica, thay đổi phân bố slot và giới hạn thao tác nhiều khóa.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): cursor, `MATCH`, `COUNT`, giới hạn về tính nhất quán của kết quả.
- [Redis — FLUSHDB](https://redis.io/docs/latest/commands/flushdb/): phạm vi và tác động của lệnh xóa dữ liệu.
