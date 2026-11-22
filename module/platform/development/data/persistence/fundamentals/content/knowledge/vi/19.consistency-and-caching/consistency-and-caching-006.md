# Cuộc đua giữa tải dữ liệu, cập nhật nguồn và vô hiệu hóa

## Mục tiêu học tập

Sau khi học xong, người học có thể:

1. Vẽ lịch thực thi của **cache miss**, **đọc nguồn dữ liệu**, **cập nhật/commit** và **vô hiệu hóa cache** để phát hiện điều kiện tranh chấp (*race condition*).
2. Giải thích vì sao chính sách **cache-aside + xóa cache sau commit** vẫn có thể để một lượt tải cũ ghi lại dữ liệu đã lỗi thời.
3. Phân biệt **tính nhất quán của cache**, **tính nhất quán của transaction DB**, **độ bền sau commit** và **độ mới của dữ liệu nhìn thấy ở API**.
4. Chọn các cơ chế phù hợp như TTL, generation token, version/compare-and-set, đọc từ primary, transactional outbox và cơ chế chống cache stampede.
5. Nhận diện giới hạn của khóa `synchronized` trong một JVM khi ứng dụng chạy nhiều instance hoặc có cache phân tán.
6. Thiết kế kiểm thử đồng thời có lịch thực thi xác định, đo stale-read và giám sát đường vô hiệu hóa.

Bài thuộc chương **Nhất quán và cache** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Nội dung đặt cache vào ranh giới persistence của Java: schema, query, transaction, isolation, kiểm soát đồng thời, lỗi kết nối, backup, bảo mật và hiệu năng. **Cache là bản sao phục vụ đọc**, không mặc nhiên là nguồn sự thật; vì vậy mỗi lựa chọn tăng tốc phải xác định rõ dữ liệu có thể cũ trong bao lâu và hành vi nghiệp vụ nào không được phép dựa vào dữ liệu cũ.

## 1. Ba tác nhân cùng thay đổi trạng thái

Giả sử API Java hiển thị giá sản phẩm. Có ba thành phần:

- **Nguồn dữ liệu (source of truth):** PostgreSQL lưu `price` và `version`, bảo vệ transaction và ràng buộc dữ liệu.
- **Cache:** lưu một bản tóm tắt sản phẩm để giảm lượt truy vấn DB; có thể là cache bộ nhớ trong JVM hoặc Redis dùng chung.
- **Đường cập nhật:** thay đổi sản phẩm trong DB, sau đó phát hành tín hiệu vô hiệu hóa/bản cập nhật cho cache.

Luồng đọc *cache-aside* phổ biến:

~~~text
                   GET product(tenant, id)
                            |
                            v
                       Đọc cache
                       /       \
                    HIT        MISS
                     |           |
                     v           v
                Trả dữ liệu    SELECT từ DB
                                  |
                                  v
                           Ghi dữ liệu vào cache
                                  |
                                  v
                              Trả dữ liệu
~~~

Luồng ghi phổ biến:

~~~text
                    UPDATE product
                           |
                           v
                   BEGIN transaction
                           |
                           v
                    UPDATE ở DB
                           |
                           v
                        COMMIT
                           |
                           v
                   Invalidate cache
                           |
                           v
                     Báo thành công
~~~

Trong sơ đồ này, `SELECT`, `COMMIT`, `DEL cache` và `SET cache` **không thuộc một transaction nguyên tử chung**. Hai luồng trên có thể đan xen theo nhiều thứ tự. Đây chính là nguồn gốc của cuộc đua.

### 1.1. Những thuật ngữ cần tách biệt

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Cache hit** | Cache có một giá trị cho key; chưa chắc giá trị đó còn mới |
| **Cache miss** | Cache không trả được giá trị, ứng dụng phải tìm nguồn khác |
| **Cache fill/populate** | Đưa dữ liệu vừa tải từ nguồn vào cache |
| **Invalidation/eviction** | Đánh dấu dữ liệu cũ không còn dùng được hoặc xóa key |
| **Stale read** | Ứng dụng nhận bản cũ hơn trạng thái cần quan sát |
| **Read-your-writes** | Sau khi một bên ghi thành công, các lần đọc kế tiếp của chính bên đó thấy tác động của ghi theo hợp đồng |
| **Eventual consistency** | Bản sao có thể trễ, nhưng được kỳ vọng hội tụ khi thay đổi/ngừng lỗi và cơ chế đồng bộ hoạt động |
| **Version/fencing token** | Thông tin thứ tự dùng để ngăn thao tác đến muộn ghi đè trạng thái mới |

**TTL (time to live)** chỉ giới hạn tuổi thọ của một mục cache theo chính sách hết hạn. Nó không tự đảm bảo rằng một lần đọc sau commit sẽ thấy ngay phiên bản mới.

## 2. Race kinh điển: xóa cache rồi vẫn bị ghi lại dữ liệu cũ

Giả sử sản phẩm `tenant=42, id=101` có giá `100.000` và phiên bản `v7`. Cache ban đầu trống.

Hai request chạy song song:

- **A** là request đọc sản phẩm.
- **B** là request cập nhật giá thành `120.000`, tạo phiên bản `v8`.

Lịch thực thi:

| Thời điểm | Request đọc A | Request cập nhật B | Database | Cache |
| --- | --- | --- | --- | --- |
| T0 | — | — | Giá 100.000, v7 | MISS |
| T1 | GET cache → MISS | — | v7 | MISS |
| T2 | SELECT DB → nhận v7, nhưng tạm dừng trước SET cache | — | v7 | MISS |
| T3 | — | UPDATE giá và COMMIT | **v8** | MISS |
| T4 | — | DEL cache thành công | v8 | MISS |
| T5 | **SET cache = v7** từ kết quả đọc ở T2 | — | v8 | **v7 — lỗi thời** |
| T6 | Request khác GET cache | — | v8 | Trả **v7** |

~~~text
Thời gian →
A (reader):  MISS --- SELECT v7 ---------------- SET v7 ---->
B (writer):                UPDATE v8 -- COMMIT -- DEL ---->
DB:           v7 ---------------------- v8 ---------------
Cache:       empty ----------------- empty -- v7 (stale) -
~~~

**Kết luận:** `DEL` sau `COMMIT` là một quy tắc hợp lý, nhưng **chỉ thao tác DEL đơn lẻ không đảm bảo** mọi lượt `SET` đến muộn đã được chặn. Reader A đã giữ bản v7 ở bộ nhớ Java trước khi B xóa cache, sau đó mới ghi lại cache. Cache có thể tiếp tục phục vụ v7 đến khi TTL hết hoặc lần vô hiệu hóa khác xảy ra.

Lỗi không đòi hỏi database đọc dữ liệu chưa commit. Ở T2, A hoàn toàn có thể đọc v7 hợp lệ trước khi B commit. Vấn đề nằm ở **thứ tự phát hành bản sao vào cache**, chứ không phải transaction DB đã commit sai.

### 2.1. Vì sao lỗi khó xuất hiện trong test thông thường?

Nếu A SELECT xong rồi SET ngay lập tức, còn B chỉ cập nhật sau đó, luồng B xóa v7 cuối cùng và mọi thứ có vẻ đúng. Cửa sổ lỗi thường chỉ lộ khi có độ trễ mạng, GC pause, worker bị chuyển ngữ cảnh, cache bị quá tải hoặc tải dữ liệu lớn.

Không nên kết luận giải pháp an toàn chỉ vì một bài test với 10 thread chạy ngẫu nhiên chưa gặp trường hợp này. Cần **ép lịch thực thi đúng các mốc T2–T5** trong integration test.

## 3. Race ngược: vô hiệu hóa **trước** COMMIT

Một người có thể nghĩ: “Vậy hãy xóa cache trước, rồi cập nhật database.” Cách đó tạo cửa sổ khác.

~~~text
T1 Writer B: DEL cache
T2 Reader A: cache miss
T3 Reader A: SELECT DB, vẫn thấy v7 vì B chưa commit
T4 Reader A: SET cache = v7
T5 Writer B: COMMIT v8
T6 Không có DEL nào tiếp theo
T7 Request khác đọc v7 từ cache
~~~

Xóa cache **trước** khi DB commit không thể bảo đảm rằng reader sẽ chỉ tải phiên bản mới. Với PostgreSQL READ COMMITTED, khi B còn chưa commit, SELECT thông thường ở A không thấy thay đổi chưa commit của B. Việc reader đưa v7 vào cache lúc T4 vì vậy là diễn biến hoàn toàn hợp lệ.

Điều này giải thích quy tắc chung: **không công bố thay đổi cache như thể dữ liệu đã commit khi transaction DB chưa thực sự thành công**. Tuy vậy, chỉ đổi từ “xóa trước” sang “xóa sau” vẫn chưa loại bỏ race ở phần 2.

### 3.1. Ghi cache trước COMMIT còn có rủi ro rollback

Nếu B viết giá mới v8 vào cache trong khi transaction DB chưa commit, rồi transaction rollback vì vi phạm constraint, cache có thể hiển thị **giá chưa từng được commit**. Với những dữ liệu tài chính, trạng thái đơn hàng hoặc quyền truy cập, rủi ro này đặc biệt nghiêm trọng.

Vì vậy, với chiến lược cache-aside, thông thường **DB là nơi quyết định commit; cache chỉ được sửa hoặc vô hiệu hóa theo sự kiện đã commit**. Ranh giới “đã commit” quan trọng hơn việc gọi một API cache thành công.

## 4. Bốn thứ dễ bị đánh đồng là “nhất quán”

| Thuộc tính | Câu hỏi | Ai chịu trách nhiệm chính? |
| --- | --- | --- |
| **Isolation của DB** | Transaction A có thấy thay đổi chưa commit của B không? Hai SELECT có cùng snapshot không? | Database và mức isolation |
| **Durability của DB** | Transaction đã commit có phục hồi được sau crash trong mô hình sự cố đã chọn không? | WAL/redo, flush, thiết bị lưu trữ, backup |
| **Coherence/consistency của cache** | Bản sao cache có theo kịp version đã commit tại nguồn không? | Chính sách fill/invalidate, version, delivery, TTL |
| **Consistency của API** | Người dùng có thể thấy giá cũ sau khi đã đổi giá? Trong bao lâu? | Hợp đồng nghiệp vụ, chọn đường đọc và cache |

Một DB transaction hoàn toàn đúng vẫn có thể đi kèm cache stale. Ngược lại, một GET cache trả đúng giá mới không chứng minh transaction DB đã an toàn qua mất điện hoặc replica khác đã bắt kịp.

**Ví dụ:** PostgreSQL READ COMMITTED chấp nhận một SELECT bắt đầu trước lúc B commit trả v7. Nếu A giữ v7 rồi phát hành vào cache **sau** khi B commit, lỗi thứ tự nằm ở cache. Chọn `SERIALIZABLE` cho writer không tự khiến `SET cache` từ Java trở thành một phần của transaction DB.

## 5. Các kiểu cache và điểm race tương ứng

| Kiểu | Đường đọc | Đường ghi | Rủi ro cần xét |
| --- | --- | --- | --- |
| **Cache-aside / lazy loading** | App GET; miss thì đọc DB rồi SET | DB ghi; app/event xóa cache | Stale repopulation, xóa thất bại, cache stampede |
| **Read-through** | Cache service tự tải khi miss | Nguồn cập nhật và báo vô hiệu hóa | Loader bên trong cache vẫn có race nếu không phối hợp version |
| **Write-through** | Đọc qua cache | Lệnh ghi qua lớp quản lý cả cache và nguồn | Thứ tự commit/rollback, lỗi giữa hai hệ thống, khả năng đồng bộ |
| **Write-behind / write-back** | Có thể trả giá trị cache mới nhất | Ghi cache trước, đẩy DB sau | Rủi ro mất dữ liệu chưa được ghi bền, thứ tự và retry |
| **Near cache (L1) + distributed cache (L2)** | JVM tra L1, miss thì L2/DB | Phải vô hiệu hóa cả L1/L2 theo hợp đồng | Một JVM vẫn giữ bản cũ sau khi L2 đã xóa |

Sự lựa chọn tùy dữ liệu. Giá sản phẩm hiển thị đôi khi chấp nhận trễ vài giây; **quyết định trừ tồn kho hay xác nhận thanh toán** phải bảo vệ bất biến ở DB bằng constraint, conditional UPDATE hoặc transaction, không thể chỉ tin vào cache.

### 5.1. Cache L1 và L2 trong nhiều JVM

~~~text
             JVM A                JVM B
          L1 cache v7          L1 cache v7
              |                    |
              +---------+----------+
                        |
                    L2 / Redis
                        |
                        v
                    PostgreSQL
                   (source of truth)
~~~

B ghi DB v8 và xóa key ở Redis, nhưng JVM A vẫn có L1 v7. Một chương trình chỉ phát `DEL Redis` không đảm bảo các L1 được thông báo. Để kiểm soát, cần chính sách invalidation L1, giới hạn TTL, version hoặc chấp nhận bounded staleness.

`synchronized` trên một object Java chỉ phối hợp thread dùng chung đúng monitor **trong cùng JVM**. Nó không khóa JVM khác, Redis, DB hoặc một batch job riêng. Tương tự, một `ConcurrentHashMap` thread-safe không tự tạo consistency giữa nhiều tiến trình.

### 5.2. Đọc từ replica tạo thêm một đường dữ liệu cũ

Ngay cả sau khi vô hiệu hóa cache, loader có thể đọc từ **read replica đang trễ**:

~~~text
Primary: đã commit v8
Redis: đã xóa v7
Replica: vẫn ở v7
Reader: cache miss -> đọc replica v7 -> SET cache v7
~~~

Generation token chỉ phát hiện thay đổi **trong khoảng load**; nếu invalidation đã xảy ra trước khi reader bắt đầu, reader lấy generation mới rồi tải v7 từ replica vẫn có thể ghi stale. Với đường cache fill cần dữ liệu mới nhất đã commit, hãy dùng nguồn đọc có cam kết phù hợp (thường là primary) hoặc kiểm tra version với watermark/nguồn có authority.

## 6. TTL làm gì và không làm gì?

Giả sử cache có TTL 30 giây. Nếu reader cũ ghi v7 sau khi invalidation xảy ra, giá v7 có thể còn được đọc trong thời gian tới 30 giây **tính từ lượt SET lỗi thời**, không phải từ thời điểm B commit.

TTL có một số lợi ích:

- Giới hạn tuổi thọ của mục cache khi cơ chế invalidation bị bỏ sót, **nếu clock và hệ cache thực thi hết hạn đúng như hợp đồng**.
- Giúp kiểm soát dung lượng và làm mới dữ liệu theo chu kỳ.
- Cung cấp phương án phục hồi khi một sự kiện cập nhật bị mất và không có cơ chế reconciliation khác.

Nhưng TTL **không giải quyết**:

- Bắt buộc đọc đúng v8 ngay sau khi B commit.
- Cùng một key bị ghi lại phiên bản cũ sau khi DEL.
- Transaction DB bị rollback hoặc ghi trùng.
- Read-replica lag, thứ tự event bị đảo, hoặc invalidation tới sai key.
- Giao dịch nghiệp vụ cần bảo vệ stock/credit/permission tại thời điểm ghi.

TTL ngắn còn làm tăng cache miss và tải database, có thể gây cache stampede vào thời điểm nhiều key đồng loạt hết hạn. **Đừng dùng TTL như bằng chứng duy nhất cho bất biến nghiệp vụ.**

## 7. Cơ chế generation: chặn lượt tải cũ ghi lại sau invalidation

Một cách xử lý race ở phần 2 là gắn với mỗi key một **generation/epoch**, tăng nó mỗi khi xảy ra invalidation. Reader chỉ được ghi dữ liệu vừa tải nếu generation không thay đổi trong suốt thời gian tải.

Quy trình ở mức logic:

~~~text
READ(key):
  g0 = atomic_read_generation(key)
  cached = read_cache(key)
  if cached exists:
      return cached
  loaded = read_authoritative_source(key)
  atomic_publish_if_generation_equals(key, g0, loaded, ttl)
  return loaded hoặc đọc lại theo chính sách nhất quán của API

INVALIDATE(key):
  atomic_increment_generation_and_delete_value(key)
~~~

**Hai thao tác phải có tính nguyên tử với nhau ở nơi giữ cache state:**

1. Bên invalidation tăng generation và xóa dữ liệu như **một thay đổi được phối hợp**.
2. Bên fill kiểm tra generation rồi SET như **một thao tác có điều kiện nguyên tử**; tách thành `GET generation` rồi `SET value` mà không có CAS vẫn có race.

Khi reader A bắt đầu với `g=5`, sau đó writer B commit và invalidate làm `g=6`, A không được publish v7 vào cache vì generation đã đổi. Như vậy loại bỏ được **stale repopulation xuyên qua một invalidation đã quan sát**.

### 7.1. Nhưng generation không tạo linearizable read sau COMMIT

Giả sử B đã commit v8, **chưa kịp invalidate** do mạng chậm. Một reader vẫn có thể HIT v7. Hoặc nếu reader bắt đầu trước commit, nó có thể trả v7 trực tiếp cho chính request đó sau khi invalidation diễn ra, dù không được ghi v7 vào cache.

Vì vậy generation guard đảm bảo **thứ tự publish so với invalidation** trong phạm vi state được bảo vệ, **không đảm bảo** mọi GET sau khi một DB commit đã có kết quả mới. Yêu cầu mạnh hơn thường cần bypass cache, đọc trực tiếp từ DB, hoặc một protocol thống nhất giữa ghi/đọc và version.

### 7.2. Pseudocode cho cache phân tán

Với một hệ cache có hỗ trợ CAS hoặc script nguyên tử, có thể hình dung:

~~~text
invalidation(key):
    ATOMIC {
        generation[key] = generation[key] + 1
        delete cached_value[key]
    }

fill(key, observedGeneration, fetchedValue):
    ATOMIC {
        if generation[key] != observedGeneration:
            return REJECTED
        if cached_value[key] is absent:
            cached_value[key] = fetchedValue with TTL
        return ACCEPTED
    }
~~~

Ví dụ Redis có thể dùng Lua script để bảo đảm đọc generation và ghi cache là một thao tác nguyên tử **trên một Redis primary**; trong Redis Cluster, các key liên quan phải thỏa điều kiện cùng slot của thao tác nhiều key. Failover, mất state, replication bất đồng bộ và thay đổi topology vẫn cần xem xét. Một generation counter bị mất hoặc reset có thể tái sử dụng số cũ; tránh hết hạn marker trong khi có loader chưa hoàn thành hoặc dùng cơ chế version/fencing đủ mạnh.

Không triển khai kiểu “GET generation, nếu bằng thì SET” bằng hai request Redis tách rời: writer có thể invalidate đúng **giữa** bước so sánh và SET.

## 8. Minh họa Java 17: cache cục bộ chống stale repopulation

Ví dụ này dùng `ConcurrentHashMap` và khóa ngắn theo key để minh họa **nguyên lý generation**. Nó đúng trong phạm vi **một JVM**, không phải thay thế cho Redis CAS, distributed invalidation hay một giải pháp linearizable liên hệ thống.

~~~java
import java.math.BigDecimal;
import java.sql.SQLException;
import java.util.concurrent.ConcurrentHashMap;

record ProductKey(long tenantId, long productId) {}

record ProductView(
        long tenantId,
        long productId,
        BigDecimal price,
        long version) {}

interface ProductReader {
    // Đọc từ nguồn đủ mới cho giao thức cache fill;
    // ví dụ primary PostgreSQL, không phải replica trễ.
    ProductView loadFromPrimary(ProductKey key) throws SQLException;
}

final class LocalVersionedCacheAside {
    private static final class Slot {
        long generation;
        ProductView value;
    }

    private final ConcurrentHashMap<ProductKey, Slot> slots =
            new ConcurrentHashMap<>();
    private final ProductReader reader;

    LocalVersionedCacheAside(ProductReader reader) {
        this.reader = reader;
    }

    ProductView getOrLoad(ProductKey key) throws SQLException {
        Slot slot = slots.computeIfAbsent(key, ignored -> new Slot());
        long observedGeneration;

        synchronized (slot) {
            if (slot.value != null) {
                return slot.value;
            }
            observedGeneration = slot.generation;
        }

        // Không giữ monitor khi chạy I/O.
        ProductView loaded = reader.loadFromPrimary(key);

        synchronized (slot) {
            if (slot.generation == observedGeneration) {
                // Một reader khác có thể đã fill trước.
                if (slot.value == null) {
                    slot.value = loaded;
                }
                return slot.value;
            }
        }

        // Có invalidation trong lúc tải: không cache bản cũ.
        // Đọc lại; kết quả trả về không phải một linearizable read
        // nếu nguồn tiếp tục thay đổi trong lúc thực thi.
        return reader.loadFromPrimary(key);
    }

    void invalidate(ProductKey key) {
        Slot slot = slots.computeIfAbsent(key, ignored -> new Slot());

        synchronized (slot) {
            slot.generation++;
            slot.value = null;
        }
    }
}
~~~

Ở ví dụ này, cache không lưu kết quả `null` (không tìm thấy sản phẩm); khi source trả `null`, kết quả vẫn là miss ở những request sau. Trong sản phẩm thật có thể dùng `Optional` hoặc đại diện riêng cho **negative cache** với TTL ngắn, đồng thời phải vô hiệu hóa khi bản ghi được tạo trở lại.

**Vì sao khóa chỉ bao quanh thao tác ngắn?** Nếu giữ `synchronized(slot)` khi gọi DB, một truy vấn chậm sẽ chặn những request khác của cùng key, kéo dài thời gian chờ và làm cho invalidation bị trì hoãn. Ví dụ cố ý đọc DB **ngoài khóa**, rồi kiểm tra generation trong cùng critical section với thao tác publish.

**Giới hạn quan trọng của ví dụ:**

- Đây chỉ là **một tiến trình**. Những JVM khác sẽ có `slots` riêng, nên sự kiện invalidation phải được gửi đến từng instance hoặc dùng cache phân tán có CAS.
- Ví dụ không có TTL, giới hạn kích thước hay dọn dẹp `Slot`. Không dùng nguyên xi làm production cache: map có thể tăng không giới hạn.
- Khi DB commit nhưng `invalidate()` chưa chạy, vẫn có một **khoảng dữ liệu stale**.
- Một giá trị vừa tải có thể trở nên cũ ngay sau khi được trả cho caller; protocol không hứa snapshot cho toàn bộ request.
- Nếu nhiều request cùng miss, code vẫn có thể tạo nhiều SELECT song song. Cần bổ sung single-flight/bounded concurrency nếu đây là vấn đề hiệu năng.

### 8.1. Một implementation đọc nguồn bằng JDBC

Với bảng `catalog_products` ở phần tiếp theo, source reader có thể như sau:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

final class JdbcProductReader implements ProductReader {
    private final DataSource primaryDataSource;

    JdbcProductReader(DataSource primaryDataSource) {
        this.primaryDataSource = primaryDataSource;
    }

    @Override
    public ProductView loadFromPrimary(ProductKey key)
            throws SQLException {
        String sql = """
            SELECT price, version
            FROM catalog_products
            WHERE tenant_id = ?
              AND product_id = ?
            """;

        try (Connection connection = primaryDataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, key.tenantId());
            statement.setLong(2, key.productId());

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return null;
                }
                return new ProductView(
                        key.tenantId(),
                        key.productId(),
                        rows.getBigDecimal("price"),
                        rows.getLong("version"));
            }
        }
    }
}
~~~

Đoạn JDBC chỉ minh họa nguồn đọc có giới hạn và đóng tài nguyên đúng cách. Nó giả định `primaryDataSource` thực sự trỏ tới primary với mức nhất quán đọc phù hợp. Không đưa kết nối hay `ResultSet` vào object cache; chỉ cache một DTO bất biến.

## 9. Version của nguồn dữ liệu và thứ tự cập nhật

Generation mô tả **lịch sử invalidation của cache**; một cách khác là lưu **version từ source** cùng payload, ví dụ `(v7, price=100000)`, `(v8, price=120000)`.

Khi một hệ cache nhận cả bản v8 và một thông điệp chậm chứa v7, nó phải không được thay v8 bằng v7. Cần một điều kiện ghi kiểu:

~~~text
putIfNewer(key, incoming):
    current = atomic_read_cached_or_fence_version(key)
    if incoming.version < current.version:
        REJECT
    else:
        PUBLISH incoming
~~~

**Lưu ý:** Nếu chỉ so sánh với giá trị cache hiện có và key đang vắng mặt, một `SET v7` đến muộn vẫn có thể được chấp nhận. Với yêu cầu loại bỏ stale repopulation, cần marker/tombstone version hoặc generation có tuổi thọ đủ dài, và cập nhật marker theo thứ tự commit tương ứng.

### 9.1. Schema và lệnh cập nhật có version

Trong môi trường PostgreSQL thử nghiệm:

~~~sql
CREATE TABLE catalog_products (
    tenant_id  BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    price      NUMERIC(14, 2) NOT NULL CHECK (price >= 0),
    version    BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, product_id)
);

INSERT INTO catalog_products (tenant_id, product_id, price, version)
VALUES (42, 101, 100000.00, 7);
~~~

Lệnh cập nhật giá đơn hàng mẫu:

~~~sql
UPDATE catalog_products
SET price = 120000.00,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE tenant_id = 42
  AND product_id = 101
RETURNING product_id, price, version;
~~~

Với nhiều writer đồng thời, database phải là nơi phối hợp cập nhật version. Đối với nghiệp vụ **đọc–tính–ghi**, có thể thêm điều kiện `AND version = :expectedVersion` để phát hiện xung đột optimistic locking. Không tự sinh version bằng đồng hồ của mỗi JVM rồi coi đó là thứ tự commit toàn cục: clock skew và nhiều giao dịch đồng thời làm timestamp không phải fencing token đáng tin trong mọi trường hợp.

Đối với một hàng PostgreSQL, hai UPDATE tranh chấp trên cùng hàng được database điều phối bằng locking; tuy nhiên **không tự suy rộng version từng hàng thành thứ tự toàn cục giữa các hàng**. Nếu event liên quan nhiều aggregate, cần xác định phạm vi thứ tự riêng.

## 10. Invalidation phải được phát sau COMMIT và không được mất âm thầm

Một kiểu code dễ viết nhưng có khoảng lỗi:

~~~java
transactionManager.commit();
cache.evict(key); // Nếu JVM crash đúng ở đây thì sao?
~~~

Nếu DB đã commit v8 mà tiến trình chết trước khi gửi invalidation, cache vẫn có thể giữ v7 cho đến TTL. Ngay cả nếu eviction được gọi, timeout hoặc lỗi mạng có thể khiến ứng dụng không chắc Redis đã nhận được hay chưa.

Đối với cache chấp nhận eventual consistency, có thể dùng TTL và retry để hạn chế thời gian cũ. Nếu cập nhật cache quan trọng hơn, nên có một **dấu vết bền vững** của việc cần vô hiệu hóa.

### 10.1. Transactional outbox

Ý tưởng: ghi thay đổi sản phẩm **và** sự kiện yêu cầu vô hiệu hóa trong **cùng transaction DB**. Một worker riêng đọc outbox sau commit rồi thực hiện evict.

~~~sql
CREATE TABLE cache_invalidation_outbox (
    event_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    product_id  BIGINT NOT NULL,
    version     BIGINT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ
);
~~~

Ví dụ dùng PostgreSQL CTE để cập nhật và ghi outbox nguyên tử ở mức transaction:

~~~sql
BEGIN;

WITH changed AS (
    UPDATE catalog_products
    SET price = 120000.00,
        version = version + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE tenant_id = 42
      AND product_id = 101
    RETURNING tenant_id, product_id, version
)
INSERT INTO cache_invalidation_outbox
    (tenant_id, product_id, version)
SELECT tenant_id, product_id, version
FROM changed;

COMMIT;
~~~

Nếu transaction rollback, cả cập nhật sản phẩm lẫn outbox row đều rollback. Nếu transaction commit thành công, có bản ghi bền vững để worker phát lại việc invalidation. **Outbox giải quyết nguy cơ mất thông báo giữa commit và publish**, nhưng không tự biến cache và DB thành một transaction chung: thông báo vẫn có thể đến chậm, lặp hoặc sai thứ tự.

Một worker thực tế cần:

1. Lấy các event chưa hoàn thành với cơ chế phân phối công việc thích hợp, ví dụ `FOR UPDATE SKIP LOCKED` hoặc một hàng đợi được thiết kế rõ.
2. Thực thi invalidation tới đúng L2/L1 hoặc thông qua một bus event.
3. Chỉ đánh dấu `processed_at` sau khi đã có bằng chứng phù hợp về bước xử lý; nếu worker chết giữa invalidate và ack, event có thể được xử lý lại.
4. Đảm bảo handler **idempotent**: xóa cùng key hai lần không gây lỗi nghiệp vụ; nếu áp dụng payload mới vào cache thì phải có version guard.
5. Giám sát số event tồn đọng, độ trễ từ commit đến invalidate, số lần retry và dead-letter/failure.

Cần chú ý: event đã đánh dấu “đã publish” vào bus không đồng nghĩa mọi JVM L1 đã xử lý. Muốn đo thời gian đến trạng thái nhất quán cần biết **mốc xác nhận ở từng tầng**.

### 10.2. CDC và sự kiện theo commit

Một lựa chọn khác là CDC (*change data capture*) đọc thay đổi đã commit từ log của database rồi phát event, giảm việc ứng dụng phải tự gọi `cache.evict()` trên mọi đường ghi. Nhưng CDC cũng có các vấn đề về độ trễ, retry, thứ tự, snapshot khởi tạo và failover. Phải xác định cách key `(tenant_id, product_id)` được tạo và cách xử lý delete/recreate.

Không mặc định một event bus cung cấp “exactly once” end-to-end từ DB qua cache. Ngay cả nếu bus có cơ chế kiểm soát trùng, handler và cập nhật cache vẫn cần idempotency và thứ tự version.

## 11. Thứ tự sự kiện: stale write đến sau new write

Giả sử hai cập nhật liên tiếp:

~~~text
DB commit v8, phát E8
DB commit v9, phát E9

Worker 2 xử lý E9 trước
Worker 1 xử lý E8 sau
~~~

Nếu handler **SET giá trong event** không có kiểm tra phiên bản, giá v8 có thể ghi đè giá v9. Nếu handler chỉ **DEL cache**, E8 xử lý muộn thường gây mất cache hit thêm một lần hơn là làm giá cũ xuất hiện ngay; tuy nhiên một reader tải cũ vẫn có thể repopulate theo race ở phần 2.

Để tránh ghi dữ liệu lùi phiên bản, cần một **monotonic fence** theo key, kiểm tra và cập nhật một cách nguyên tử. Event có version cũ hơn marker đã chấp nhận phải bị từ chối. Những event cùng version có thể xử lý lặp theo chính sách idempotent.

**Không dùng `created_at` từ máy ứng dụng khác nhau làm bằng chứng thứ tự**, đặc biệt với clock skew. Nếu cần thứ tự per-key, dùng version được nguồn dữ liệu quản lý hoặc cơ chế sequence/commit ordering được thiết kế và kiểm chứng.

## 12. Cache stampede là vấn đề khác nhưng có thể làm race trầm trọng hơn

Khi một key hot hết hạn hoặc bị invalidate, hàng trăm request có thể cùng cache miss và đồng loạt SELECT DB. Đây là **cache stampede/thundering herd**.

~~~text
100 request đồng thời
       |
       v
    Cache miss
       |
       +-- SELECT DB
       +-- SELECT DB
       +-- SELECT DB
       +-- ... 97 SELECT nữa
       |
       v
    Nhiều loader cố SET cùng key
~~~

Số loader lớn tăng tải DB và tạo nhiều cơ hội một kết quả cũ tới muộn. Những cách giảm rủi ro:

- **Single-flight/per-key coalescing:** trong một JVM, chỉ một loader cho cùng key, các request khác chờ kết quả chung; trong nhiều JVM cần cơ chế điều phối phân tán hoặc chấp nhận nhiều loader.
- **TTL jitter:** tránh nhiều key hết hạn tại cùng một thời điểm.
- **Stale-while-revalidate:** có thể trả bản cũ trong cửa sổ được nghiệp vụ chấp nhận, đồng thời một worker làm mới. Phải công khai rõ chính sách stale.
- **Rate limit/circuit breaker:** khi database bị quá tải, tránh miss storm làm hỏng cả nguồn sự thật.
- **Negative caching:** cache kết quả “không tồn tại” trong thời gian ngắn để giảm query miss lặp; phải invalidate khi tạo bản ghi mới.
- **Warm-up có kiểm soát:** prefetch key hot dựa trên dữ liệu và tải có thật, không tải đồng loạt khiến DB nghẽn.

**Single-flight không đồng nghĩa giải quyết stale repopulation.** Nó chỉ giảm số lượt tải trong một phạm vi điều phối; writer vẫn có thể commit và invalidate xen giữa tải và publish. Cần kết hợp với version/generation hoặc giao thức khác nếu không chấp nhận lượt fill lỗi thời.

## 13. Khi nào nên đọc trực tiếp nguồn thay vì cố sửa mọi race cache?

Không phải dữ liệu nào cũng có cùng yêu cầu về độ mới:

| Loại thông tin | Có thể chấp nhận stale không? | Chiến lược thường cân nhắc |
| --- | --- | --- |
| Mô tả sản phẩm, ảnh, danh mục | Có thể chấp nhận trong một khoảng rõ ràng | Cache-aside + TTL + invalidation/outbox |
| Giá hiển thị tham khảo | Tùy hợp đồng và cách chốt giá khi checkout | Cache cho màn hình; DB xác nhận giá khi tạo đơn |
| Số lượng tồn kho hiển thị | Có thể chấp nhận con số gần đúng | Cache cho display; conditional UPDATE ở DB khi đặt hàng |
| Quyền truy cập, thu hồi quyền | Thường cần độ trễ thu hồi rất thấp | Cân nhắc source/epoch bắt buộc, TTL rất ngắn, invalidation ưu tiên hoặc đường kiểm tra authoritative |
| Số dư trước giao dịch | Rủi ro cao nếu dựa trên cache | DB/ledger và transaction phù hợp cho quyết định |
| Chặn đặt trùng ghế, thanh toán | Không dùng cache làm bảo đảm duy nhất | UNIQUE/constraint, transaction, idempotency tại nguồn |
| Báo cáo snapshot chính xác | Cần định nghĩa cùng thời điểm | Snapshot DB/warehouse theo hợp đồng, không ghép tùy tiện cache từ nhiều lúc |

Nếu API bắt buộc **read-your-writes** ngay sau commit, cách đơn giản và dễ chứng minh thường là đọc từ primary hoặc bypass cache trên đường trả lời/những GET kế tiếp có yêu cầu đó. Một write-through protocol chặt chẽ có thể cung cấp bảo đảm mạnh hơn, nhưng cần thiết kế ranh giới nguyên tử thật và phân tích sự cố; chỉ “SET cache ngay sau UPDATE” không đủ.

Đối với hành động tài chính, bảo mật hoặc thay đổi trạng thái không thể đảo ngược, hãy **bảo vệ bất biến tại database** bằng transaction, constraint, lock/optimistic version. Cache dùng để phục vụ đọc hoặc gợi ý giao diện, không thay thế cơ chế kiểm soát đồng thời.

## 14. Bảo mật và multi-tenant: đúng phiên bản nhưng sai key vẫn nguy hiểm

Trong hệ thống đa tenant, cache key phải chứa đầy đủ phạm vi phân biệt dữ liệu. Ví dụ:

~~~text
product:{tenantId}:{productId}
~~~

Nếu key chỉ là `product:{productId}`, hai tenant có cùng product ID có thể nhìn thấy dữ liệu của nhau. Dù version/generation hoạt động chính xác, **phân vùng key sai là lỗi bảo mật và toàn vẹn dữ liệu**.

Ngoài ra:

- Chỉ một event invalidation thiếu `tenant_id` có thể xóa nhầm hoặc bỏ sót key.
- Thay đổi quyền truy cập cần vô hiệu hóa các cache token/permission liên quan, không chỉ cache DTO sản phẩm.
- Tránh đặt PII, secret hoặc dữ liệu nhạy cảm trực tiếp vào key nếu cache log/metrics có thể lộ key.
- Bảo vệ đường truyền, quyền truy cập Redis/cache, TTL và chính sách xóa dữ liệu cả ở L1/L2.
- Không lấy cache hit làm bằng chứng người gọi có quyền xem dữ liệu: **kiểm tra authorization** vẫn phải áp dụng ở ranh giới phù hợp.

## 15. Kiểm thử race bằng lịch thực thi có kiểm soát

Một bài test chạy ngẫu nhiên nhiều thread có thể không gặp race. Hãy dùng latch/barrier hoặc một fake source để ép đúng thứ tự.

### 15.1. Kịch bản bắt buộc cho stale repopulation

1. Chuẩn bị DB `v7` và cache miss.
2. Reader A bắt đầu, đọc thành công `v7`, **chặn trước khi publish cache**.
3. Writer B cập nhật DB và COMMIT `v8`.
4. Worker/handler vô hiệu hóa cache cho key sản phẩm và xác nhận hoàn tất.
5. Cho A tiếp tục bước publish.
6. Kiểm tra: cache **không được chứa v7** sau bước 5 nếu đã dùng generation/fencing.
7. Đọc lại với connection mới từ source: phải nhìn thấy v8 theo hợp đồng đọc đã chọn.
8. Chạy lại với cache-aside đơn giản để minh họa vì sao test thất bại.

Ví dụ timeline có thể mô phỏng bằng `CountDownLatch` trong một JVM cho cache cục bộ. Với cache Redis và hai service instance, cần dùng hai process hoặc hai connection/client để bảo đảm mọi writer/reader thực sự chia sẻ cùng trạng thái phân tán.

### 15.2. Ma trận test quan trọng

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Reader fill v7 sau invalidation v8 | Guard từ chối publish v7 |
| Writer rollback v8 | Không công bố cache v8 như giá đã commit |
| Writer COMMIT nhưng tiến trình chết trước evict | Outbox/CDC hoặc TTL cuối cùng xử lý; đo thời gian stale |
| Event E9 tới trước E8 | Không được ghi v8 đè lên v9 nếu handler cập nhật payload |
| Invalidation lặp | Handler có thể chạy lại an toàn, không phá dữ liệu |
| L1 A đã cache v7, L2 bị DEL | L1 A phải tuân thủ chính sách invalidation/TTL đã cam kết |
| Replica vẫn v7 sau primary commit v8 | Cache fill không được mặc nhiên coi replica lag là dữ liệu mới nhất |
| Cache/Redis restart mất marker | Không tái dùng generation cũ để cho loader lỗi thời publish |
| Key hot đồng loạt hết hạn | Có giới hạn tải DB, quan sát single-flight/stampede |
| Product bị xóa hoặc tạo lại | Negative cache/version/invalidations xử lý đúng |
| Hai tenant có cùng product ID | Không có cross-tenant cache hit hoặc invalidation |
| Client đòi read-your-writes | Đường đọc sau commit thỏa hợp đồng đã công bố |

### 15.3. Mẫu Java test bằng điểm chặn

Ở mức ý tưởng, fake `ProductReader` có thể:

~~~java
CountDownLatch sourceReadCompleted = new CountDownLatch(1);
CountDownLatch mayReturnToLoader = new CountDownLatch(1);

// Trong fake reader của request A:
ProductView oldVersion = productV7;
sourceReadCompleted.countDown();
mayReturnToLoader.await(); // Ví dụ test cần xử lý InterruptedException.
return oldVersion;

// Trong thread điều phối test:
startReaderA();
sourceReadCompleted.await();
commitProductV8();
cache.invalidate(key);
mayReturnToLoader.countDown();
joinReaderA();
assertCacheDoesNotContainV7();
~~~

Đây là **pseudocode Java cho lịch test**, không phải một phương thức có thể biên dịch nguyên xi: `ProductReader` ở ví dụ trước khai báo `SQLException`, còn fake cần xử lý `InterruptedException` theo hợp đồng test. Điểm cần rút ra là **tạo được lịch T1–T5 một cách quyết định**, không dựa vào `Thread.sleep(10)` để đoán timing.

Ngoài tính đúng đắn, cần thử cả error path: `cache.evict()` timeout, `COMMIT` mất phản hồi, outbox worker chết sau publish nhưng trước ack, cache full, DB chậm, GC pause và retry event. Một giao thức cache đúng phải nêu rõ hành vi khi từng bước lỗi.

## 16. Quan sát và vận hành consistency của cache

Chỉ số hit ratio cao không đủ chứng minh cache đúng. Có thể cache hit **rất cao và rất sai** nếu một giá trị cũ còn ở key hot trong thời gian dài.

Theo dõi các nhóm chỉ số:

| Nhóm | Chỉ số | Ý nghĩa |
| --- | --- | --- |
| Đường đọc | Hit/miss, load duration, số query DB per miss | Cache có giảm tải thật không? |
| Đường ghi | Thời gian từ DB commit đến invalidation hoàn tất | Khoảng stale do delivery |
| Thứ tự | Tỷ lệ publish bị CAS/version guard từ chối | Có bao nhiêu cuộc đua đang xảy ra? |
| Chất lượng | Tỷ lệ đọc version cũ so với authoritative source (qua lấy mẫu an toàn) | Đo stale thực tế, không chỉ hit ratio |
| Invalidation | Outbox backlog, event lag, retry, dead-letter | Có event bị mất, tắc hoặc xử lý muộn không? |
| Multi-layer | L1/L2 hit rate, version mismatch, thời gian đồng bộ | Có bỏ sót invalidation trên một instance không? |
| Tải | Cache stampede, đồng thời loader theo key, DB CPU/I/O, pool pending | Khi miss đồng loạt có làm DB nghẽn không? |
| Bảo mật | Cross-tenant key collision, dữ liệu nhạy cảm bị lưu/log | Rủi ro truy cập sai phạm vi |

Nên đặt ngưỡng chất lượng theo yêu cầu nghiệp vụ, chẳng hạn “giá hiển thị có thể trễ tối đa X giây ở p99” hoặc “kiểm tra quyền phải phản ánh quyết định thu hồi trước hành động nhạy cảm”. Các con số cần xuất phát từ SLO, không phải chọn tùy ý.

Khi triển khai cơ chế version mới, có thể tạm thời so sánh version giữa cache và source ở một lượng nhỏ request được chọn để định lượng stale mà không ép mọi request đọc thêm DB. Thống kê phải chú ý chi phí giám sát và dữ liệu cá nhân.

## 17. Những hiểu lầm thường gặp

**“DB transaction đã COMMIT nên cache tự mới.”** Sai: DB và cache là hai hệ thống; invalidation có thể chậm, lỗi hoặc bị ghi đè bằng lượt load cũ.

**“DELETE cache sau COMMIT là loại bỏ hoàn toàn race.”** Sai: reader đã đọc v7 từ trước vẫn có thể SET v7 sau DEL.

**“DELETE trước khi COMMIT sẽ an toàn hơn.”** Sai: cache miss có thể tải lại bản chưa đổi từ DB và giữ nó sau khi writer commit.

**“TTL đảm bảo đọc đúng sau ghi.”** Sai: TTL chỉ ràng buộc hạn tồn tại của bản cache và không phải bảo đảm read-your-writes.

**“Redis GET generation rồi SET cache là có CAS.”** Sai: hai lệnh rời vẫn có khoảng writer xen vào; cần atomic compare-and-publish.

**“Có generation token thì mọi GET sau commit đều thấy bản mới.”** Sai: còn cửa sổ commit → invalidation và nguồn đọc có thể là replica trễ.

**“`synchronized` trong service giải quyết race của Redis giữa hai instance.”** Sai: mỗi JVM có monitor riêng.

**“Single-flight giải quyết cả tính đúng đắn và hiệu năng.”** Nó có thể giảm số loader, nhưng cần một guard riêng để chặn stale publish.

**“Outbox đảm bảo event tới đúng một lần theo đúng thứ tự.”** Outbox cung cấp dấu vết bền vững cùng transaction; delivery có thể lặp, trễ hoặc cần cơ chế quản lý thứ tự.

**“Ghi value trong event trực tiếp lên cache luôn nhanh và đúng.”** Event cũ có thể tới sau event mới; cần version fence và kiểm chứng trạng thái.

**“Cache tốt thì có thể dùng để quyết định trừ tồn kho.”** Cache có thể phục vụ hiển thị; bất biến tồn kho cần được DB bảo vệ bằng SQL nguyên tử và transaction.

## 18. Bài tập vận dụng

**Bài 1 — dựng timeline.** Với DB `v7`, cache miss, reader A đọc v7, writer B commit v8 và DEL key, A SET v7: hãy vẽ lịch và giải thích vì sao v7 tồn tại sau invalidation. Xác định bước nào cần generation/CAS.

**Bài 2 — so sánh xóa trước/sau commit.** Hãy thiết kế hai timeline khác nhau, một với DEL trước COMMIT, một với DEL sau COMMIT. Trong mỗi timeline, chỉ ra cửa sổ stale và cách thu hẹp mà không giả định có transaction chung giữa DB và cache.

**Bài 3 — sửa cache phân tán.** Một Redis cache lưu `value` và `generation` nhưng code làm `GET generation`, sau đó `SET value` ở request khác. Hãy minh họa cuộc đua làm sai kết quả và mô tả atomic compare-and-set hoặc Lua script cần có. Xét tình huống Redis failover hoặc marker hết hạn.

**Bài 4 — thiết kế outbox.** Với bảng `catalog_products`, xây transaction cập nhật price/version và tạo event. Viết logic worker idempotent, cách xử lý event lặp và event đến ngược thứ tự. Giải thích tại sao chỉ `processed_at` không chứng minh toàn bộ JVM L1 đã vô hiệu hóa.

**Bài 5 — chọn consistency theo nghiệp vụ.** Đề xuất chính sách cache cho mô tả sản phẩm, số lượng tồn kho hiển thị, số dư trước thanh toán và quyền truy cập. Nêu độ trễ stale chấp nhận được, đường nguồn sự thật và phép kiểm tra bắt buộc trước hành động quan trọng.

**Bài 6 — kiểm thử có rào chắn.** Dùng hai thread và latch để ép reader tải v7 trước, writer commit v8 rồi invalidate, reader mới tiếp tục SET. Chạy với cache-aside naive và với generation guard; ghi nhận số lần cache chứa v7 sau invalidation.

**Bài 7 — đánh giá chi phí.** Một hệ thống có L1 per-JVM, Redis L2 và PostgreSQL primary/replica. Vẽ đường đi khi cache miss, DB update và event invalidation. Đề xuất metrics cho khoảng stale, hit ratio, event lag, version mismatch và stampede. Giải thích vì sao tăng TTL có thể cải thiện hit ratio nhưng làm giảm độ mới dữ liệu.

## Ghi nhớ

**Cuộc đua giữa tải dữ liệu, commit và invalidation xảy ra vì cache fill và DB transaction không có một thứ tự nguyên tử chung.** Một reader có thể tải bản cũ trước commit rồi ghi vào cache sau khi writer đã xóa key. Xóa trước commit cũng không an toàn vì reader có thể tải lại dữ liệu cũ từ nguồn. TTL chỉ giới hạn tuổi thọ và không phải bằng chứng về tính đúng đắn.

Trong ứng dụng Java, cần chọn hợp đồng consistency theo nghiệp vụ, phân biệt DB với cache, dùng version/generation và atomic publish khi cần ngăn stale repopulation, đọc từ nguồn có cam kết phù hợp, ghi dấu invalidation bằng outbox/CDC khi không được mất sự kiện, kiểm soát nhiều tầng cache và kiểm thử lịch thực thi có chủ đích. **Bất biến quan trọng phải được bảo vệ tại kho dữ liệu**, không chỉ bằng tốc độ hoặc tính thread-safe của cache.
