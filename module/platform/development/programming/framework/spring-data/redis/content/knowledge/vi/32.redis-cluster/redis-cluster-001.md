# Hash slot và cơ chế phân phối khóa trong Redis Cluster

Một ứng dụng dùng Redis Standalone thường không phải quan tâm key được lưu ở đâu: bất kỳ lệnh `GET user:42` hay `SET order:913 ...` nào cũng đi tới cùng một Redis server. Khi chuyển sang **Redis Cluster**, dữ liệu được phân tán trên nhiều **master node**, mỗi node quản lý một phần của không gian khóa. Để quyết định key nằm ở đâu, Redis Cluster dùng **16.384 hash slot**, đánh số từ **0 đến 16383**.

Với một key thông thường, Redis tính:

```text
HASH_SLOT = CRC16(key) mod 16384
```

Kết quả là **số slot**, không phải địa chỉ node. Client tiếp tục tra bảng **slot → master** để biết gửi lệnh tới đâu. Khi Cluster thêm node, đổi master hoặc cân bằng lại dữ liệu, Redis có thể chuyển **quyền sở hữu slot** và các key thuộc slot đó sang node mới mà không cần đổi cách tính hash của từng key.

Trong Spring Data Redis, mô hình này tác động trực tiếp đến `StringRedisTemplate`, `RedisTemplate`, `ReactiveRedisTemplate`, các lệnh nhiều key, transaction, script và chiến lược đặt tên key. Một key design phù hợp giúp ứng dụng phân tán tải mà vẫn xử lý được những nhóm key cần thao tác cùng nhau.

## 1. Vì sao cần hash slot?

Giả sử hệ thống có hàng chục triệu key:

```text
user:1:profile
user:2:profile
user:3:profile
order:913:state
order:914:state
product:100:stock
product:101:stock
...
```

Nếu mọi key nằm trên một master, RAM, CPU và network của máy đó tạo ra giới hạn mở rộng. Redis Cluster chia keyspace thành các **slot logic** để phân phối cho nhiều master. Ví dụ giả định:

```text
                  Redis Cluster
             16.384 hash slot
              (0 đến 16383)
                       |
          +------------+------------+
          |            |            |
          v            v            v
       Master A     Master B     Master C
       0..5460      5461..10922 10923..16383
          |            |            |
       Replica A'   Replica B'   Replica C'
```

Sơ đồ minh họa một cluster ổn định với ba master chia slot thành ba khoảng; **không phải** quy tắc Redis luôn chia slot liên tục hoặc chia đều cho mọi cluster. Một master có thể quản lý nhiều khoảng slot không liền nhau.

Mỗi key được tính một slot nhất định. **Master đang sở hữu slot** phục vụ các lệnh ghi/đọc mặc định của key đó. Replica có thể sao chép dữ liệu từ master và được bầu làm master mới khi failover; việc đọc từ replica cần cấu hình riêng và phải chấp nhận khả năng dữ liệu chưa cập nhật kịp.

### 1.1. Ba khái niệm tuyệt đối không được trộn lẫn

| Khái niệm | Là gì? | Ví dụ |
|---|---|---|
| **Key** | Tên định danh dữ liệu Redis | `order:913:state` |
| **Hash slot** | Một trong 16.384 nhóm logic của key | Slot `s` do hàm CRC16 tính ra |
| **Node** | Redis server đang phục vụ một số slot | `redis-a:7000` |

Một master thường quản lý **nhiều slot** và mỗi slot có thể chứa **rất nhiều key**. Hai key khác nhau:

- Có thể thuộc cùng slot.
- Có thể thuộc hai slot khác nhau nhưng hiện do **cùng master** quản lý.
- Có thể thuộc các slot do hai master khác nhau quản lý.

Những trường hợp này quan trọng vì **một lệnh nhiều key trên Cluster thường yêu cầu cùng slot**, không chỉ cùng địa chỉ master.

## 2. Thuật toán tính slot: CRC16/XMODEM và modulo 16384

Theo đặc tả Redis Cluster:

```text
HASH_SLOT(key) = CRC16_XMODEM(key_bytes) % 16384
```

CRC16 dùng cấu hình **XMODEM**:

| Thuộc tính | Giá trị |
|---|---|
| Độ rộng CRC | 16 bit |
| Đa thức (polynomial) | `0x1021` |
| Giá trị khởi tạo | `0x0000` |
| Reflect input/output | Không |
| XOR output | `0x0000` |
| Kiểm tra chuỗi ASCII `123456789` | CRC = `0x31C3` |
| Miền hash slot | `0..16383` |

Vì 16.384 bằng `2^14`, có thể hiểu phép lấy modulo tương ứng lấy 14 bit thấp của CRC. Redis chọn một slot từ **bytes của key**; Redis server không diễn giải key theo một object Java hay tự hiểu tiền tố `order:` là loại dữ liệu đặc biệt.

### 2.1. Cùng key bytes thì cùng slot

Giả sử hai ứng dụng đều gửi key byte UTF-8:

```text
order:913:state
```

Kết quả slot sẽ giống nhau ở các Redis Cluster tuân theo cùng thuật toán, không phụ thuộc node đang sở hữu slot, ngôn ngữ client hay nội dung value.

Nhưng nếu hai client serialize key khác nhau:

```text
Client A: UTF-8("order:913:state")
Client B: JDK serialization của Java String "order:913:state"
```

Thì **bytes khác nhau → slot có thể khác nhau**, đồng thời Redis nhìn thấy **hai key vật lý khác nhau**.

Đây là lý do cần kiểm soát serializer khi sử dụng `RedisTemplate` hoặc `ReactiveRedisTemplate`. Với key có thể đọc bằng CLI, `StringRedisTemplate`/`ReactiveStringRedisTemplate` thường dễ hiểu hơn vì key được mã hóa dạng String.

### 2.2. Một ví dụ tính slot bằng Java

Đoạn mã tự tính CRC16/XMODEM dưới đây có mục đích giải thích. Khi triển khai thực tế, nên để driver cluster-aware thực hiện routing; không cần tính slot thủ công cho từng lệnh thông thường.

```java
import java.nio.charset.StandardCharsets;

public final class RedisHashSlot {

    private RedisHashSlot() {
    }

    public static int slot(String key) {
        byte[] bytes = key.getBytes(StandardCharsets.UTF_8);
        return slot(bytes);
    }

    public static int slot(byte[] keyBytes) {
        int from = 0;
        int to = keyBytes.length;

        // Redis xét cặp { ... } đầu tiên.
        int left = -1;
        for (int i = 0; i < keyBytes.length; i++) {
            if (keyBytes[i] == '{') {
                left = i;
                break;
            }
        }

        if (left != -1) {
            int right = -1;
            for (int i = left + 1; i < keyBytes.length; i++) {
                if (keyBytes[i] == '}') {
                    right = i;
                    break;
                }
            }

            // Chỉ hash nội dung trong ngoặc nếu có ít nhất 1 byte.
            if (right > left + 1) {
                from = left + 1;
                to = right;
            }
        }

        int crc = 0;
        for (int i = from; i < to; i++) {
            crc ^= (keyBytes[i] & 0xff) << 8;
            for (int bit = 0; bit < 8; bit++) {
                if ((crc & 0x8000) != 0) {
                    crc = ((crc << 1) ^ 0x1021) & 0xffff;
                } else {
                    crc = (crc << 1) & 0xffff;
                }
            }
        }
        return crc % 16384;
    }
}
```

Có thể đối chiếu kết quả với Redis CLI:

```java
System.out.println(RedisHashSlot.slot("order:{913}:state"));
System.out.println(RedisHashSlot.slot("order:{913}:items"));
```

Hai dòng trên trả **cùng một slot** vì hash tag `{913}` giống nhau. Không nên dự đoán slot chỉ bằng số thứ tự `913`; Redis thực sự hash bytes `913`.

**Giới hạn của ví dụ:** nó nhận `String` UTF-8. Nếu driver dùng serializer khác, muốn có cùng slot phải đưa vào hàm đúng **byte[] key mà driver gửi đi**. Redis Cluster không có bước chuẩn hóa chữ hoa/chữ thường, Unicode hay tên key theo business domain.

## 3. Redis xác định master sở hữu slot như thế nào?

Tính slot chỉ là nửa đầu quá trình. Nửa còn lại là ánh xạ **slot → node**.

```text
Application
    |
    | GET order:913:state
    v
Cluster-aware Redis driver
    |
    +-- Bước 1: serialize key thành bytes
    |
    +-- Bước 2: tính CRC16/hash slot
    |
    +-- Bước 3: tra slot map
    |       slot s -> master B
    |
    +-- Bước 4: gửi GET tới master B
    |
    +-- Bước 5: nhận response và trả về ứng dụng
```

Redis Cluster dùng cơ chế **client-side routing**: các client như Lettuce/Jedis có thể học danh sách master và khoảng slot chúng quản lý. Một cluster-aware client không cần gửi mọi truy vấn qua một proxy trung tâm hoặc luôn hỏi một node trung gian trước mỗi lệnh.

### 3.1. Seed nodes không phải toàn bộ nơi giữ dữ liệu

Ví dụ Spring Boot:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a.example:7000
          - redis-b.example:7001
          - redis-c.example:7002
      timeout: 3s
```

Danh sách trên là các **địa chỉ ban đầu để khám phá topology**. Chúng không có nghĩa ứng dụng chỉ được gửi lệnh tới đúng ba endpoint đó, và không có nghĩa mỗi endpoint giữ một phần ba keyspace theo thứ tự trong YAML.

Client kết nối tới seed nodes, khám phá bảng slot và thông tin master/replica rồi điều hướng lệnh tới node phụ trách slot. Khi Cluster thay đổi, client cần cập nhật bảng này.

Với Lettuce trong Spring Data Redis, khả năng topology refresh phụ thuộc cấu hình driver và phiên bản; phải bảo đảm những địa chỉ node Redis công bố có thể truy cập được từ ứng dụng. Nếu đang dùng Docker/Kubernetes, đừng chỉ kiểm tra kết nối tới seed node mà bỏ qua các IP/hostname bên trong topology trả về.

### 3.2. Các lệnh xem topology

Trong Redis CLI kết nối tới một Cluster thật:

```redis
CLUSTER INFO
CLUSTER NODES
CLUSTER SHARDS
```

Ý nghĩa:

- `CLUSTER INFO` cho biết trạng thái chung như `cluster_state`, `cluster_slots_assigned` và số node được biết.
- `CLUSTER NODES` liệt kê các node, vai trò, liên kết replication và vùng slot mà node đang phục vụ.
- `CLUSTER SHARDS` (Redis 7.0+) trả thông tin shard, các khoảng slot và danh sách node/master/replica ở dạng có cấu trúc.
- `CLUSTER SLOTS` là lệnh discovery cũ, vẫn tồn tại vì tương thích, nhưng tài liệu Redis hiện đại ưu tiên `CLUSTER SHARDS` cho client mới.

Ví dụ kết quả `CLUSTER INFO` của một Cluster ổn định:

```text
cluster_state:ok
cluster_slots_assigned:16384
cluster_slots_ok:16384
cluster_slots_pfail:0
cluster_slots_fail:0
```

Đây là ví dụ minh họa, không phải lời khẳng định Cluster trong môi trường hiện tại đang khỏe mạnh. Nếu còn slot chưa được gán hoặc có node lỗi, tình trạng phục vụ lệnh phụ thuộc cấu hình và trạng thái thực tế.

## 4. Hash tag: chủ động đưa nhiều key vào cùng slot

Redis Cluster cho phép dùng **hash tag** trong tên key để kiểm soát phần bytes được hash. Nếu tìm được cặp `{...}` hợp lệ và phần giữa **không rỗng**, Redis chỉ hash phần đó thay vì hash cả key.

Ví dụ:

```text
order:{913}:state
order:{913}:items
order:{913}:total
```

Cả ba key được tính slot từ cùng chuỗi `913`. Vì vậy chúng **luôn cùng slot**, dù tên đầy đủ khác nhau.

Đối chiếu bằng Redis CLI:

```redis
CLUSTER KEYSLOT order:{913}:state
CLUSTER KEYSLOT order:{913}:items
CLUSTER KEYSLOT order:{913}:total
```

Cả ba trả về **một số slot giống nhau**. Khi Redis chuyển slot này sang master khác, cả nhóm key vẫn thuộc cùng slot theo thuật toán hash tag.

### 4.1. Redis nhận diện hash tag theo quy tắc nào?

Redis không dùng mọi cặp ngoặc nhọn xuất hiện trong key. Thuật toán xét **dấu `{` đầu tiên**, sau đó **dấu `}` đầu tiên xuất hiện sau nó**:

| Key | Phần bytes dùng để hash | Giải thích |
|---|---|---|
| `user:42:profile` | Toàn bộ key | Không có hash tag |
| `user:{42}:profile` | `42` | Hash tag hợp lệ |
| `cart:{42}:items` | `42` | Cùng slot với `user:{42}:profile` |
| `foo{bar}{zap}` | `bar` | Chỉ xét cặp hợp lệ đầu tiên |
| `foo{}{bar}` | Toàn bộ key | Cặp đầu tiên rỗng; không bỏ qua để tìm cặp sau |
| `foo{bar` | Toàn bộ key | Không có dấu đóng sau dấu mở đầu tiên |
| `foo{bar}baz` | `bar` | Phần ngoài tag không ảnh hưởng slot |

**Không dùng regex lấy cặp ngoặc cuối cùng** hoặc bỏ qua `{}` rỗng: kết quả có thể khác thuật toán Redis.

### 4.2. Hash tag giúp gì?

Nếu một nghiệp vụ phải lấy tổng đơn hàng, trạng thái và nội dung cart bằng **một lệnh nhiều key**, hash tag cho phép chúng thuộc cùng slot:

```redis
MSET order:{913}:state CREATED order:{913}:total 250000

MGET order:{913}:state order:{913}:total
```

Nếu không dùng cùng tag:

```redis
MGET order:913:state order:913:total
```

hai key có thể bị hash sang **hai slot khác nhau**; khi đó Redis trả `CROSSSLOT`. Có trường hợp ngẫu nhiên hai key khác nhau cùng slot do va chạm modulo, nhưng **không thiết kế hệ thống dựa vào sự trùng hợp đó**.

### 4.3. Không đặt cùng một tag cho tất cả key

Ví dụ không nên:

```text
product:{all}:1
product:{all}:2
product:{all}:3
...
order:{all}:1
order:{all}:2
```

Mọi key dùng `{all}` rơi vào cùng **một slot**. Dù Cluster có nhiều master, lượng dữ liệu và lệnh của nhóm này đều tập trung vào một slot/một master ở một thời điểm, tạo **hot slot** và mất lợi ích sharding.

Thay vào đó, chọn hash tag theo **đơn vị nghiệp vụ thật sự cần atomic multi-key** như `{order-913}`, `{cart-42}` hoặc một phân vùng có kích thước hợp lý.

## 5. Single-key và multi-key: giới hạn CROSSSLOT

Redis Cluster hỗ trợ phần lớn các lệnh thao tác trên **một key**. Client cluster-aware tính slot của key rồi route tới node sở hữu slot.

Ví dụ:

```redis
SET product:100:stock 12
SET product:101:stock 5
GET product:100:stock
GET product:101:stock
```

Hai key có thể thuộc hai slot khác nhau mà mỗi lệnh riêng vẫn hợp lệ. Nhưng lệnh nhiều key cần được kiểm tra theo quy tắc Cluster.

### 5.1. Multi-key cùng slot

Ví dụ hợp lệ:

```redis
MSET cart:{user-42}:subtotal 100 cart:{user-42}:currency VND
MGET cart:{user-42}:subtotal cart:{user-42}:currency
DEL cart:{user-42}:subtotal cart:{user-42}:currency
```

Cùng tag `{user-42}` khiến các key cùng slot. Redis có thể xử lý chúng trong một lệnh ở node sở hữu slot đó.

### 5.2. Multi-key khác slot

Ví dụ có nguy cơ lỗi:

```redis
MGET cart:{user-42}:subtotal cart:{user-43}:subtotal
```

Redis Cluster thường trả:

```text
(error) CROSSSLOT Keys in request don't hash to the same slot
```

**CROSSSLOT xét các key trong cùng một command**, không chỉ xét việc các key đang nằm ở node nào. Nếu hai slot khác nhau cùng do Master A phục vụ, `MGET` trên cả hai vẫn không trở thành lệnh cùng slot.

### 5.3. Vì sao có lệnh nhiều key mà API driver vẫn chạy được?

Một số client hoặc API cấp cao hỗ trợ **chia thao tác thành nhiều lệnh đơn** rồi tổng hợp kết quả tại phía client. Ví dụ ứng dụng có thể tự đọc hai key bằng hai `GET`:

```text
GET cart:{user-42}:subtotal --> slot A --> master X
GET cart:{user-43}:subtotal --> slot B --> master Y
         \                       /
          \-- ứng dụng ghép kết quả
```

Đây là **hai lệnh Redis độc lập**; không có atomic snapshot toàn Cluster. Nếu API wrapper dùng tên “multiGet”, cần kiểm tra cách driver/Spring Data Redis triển khai trên Cluster thực tế: có thể scatter/gather, có thể yêu cầu cùng slot hoặc có giới hạn theo phiên bản.

Không nên nghĩ rằng một lệnh `MGET` cross-slot của server trở nên hợp lệ chỉ vì chạy qua client Java.

## 6. Tính slot bằng CLI và xem node sở hữu slot

Một bộ lệnh đơn giản dành cho Cluster test:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'user:{42}:profile'
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'user:{42}:orders'
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'user:{43}:profile'
```

Kỳ vọng hai key đầu có cùng slot vì đều hash `42`. Key `{43}` thường ở slot khác; Redis không bảo đảm mọi tag khác nhau sẽ ở slot khác nhau vì chỉ có 16.384 giá trị slot.

Quan sát bảng slot:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SHARDS
```

Trên Redis cũ chưa hỗ trợ `CLUSTER SHARDS`, có thể dùng:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SLOTS
```

Kết quả cho biết khoảng slot và các endpoint master/replica. Ghép số slot vừa tính vào khoảng chứa nó để biết master hiện tại.

Để xem số key trên một slot cụ thể trong môi trường quản trị:

```redis
CLUSTER COUNTKEYSINSLOT 1234
CLUSTER GETKEYSINSLOT 1234 20
```

Số `1234` là ví dụ, cần thay bằng slot thật. Đây là lệnh quan sát trong phạm vi node có dữ liệu của slot; không chạy quét/điều tra trên dữ liệu production lớn mà không cân nhắc tác động.

### redis-cli -c: theo chuyển hướng Cluster

`redis-cli -c` bật chế độ hỗ trợ redirect của Cluster:

```bash
redis-cli -c -h 127.0.0.1 -p 7000 GET 'user:{42}:profile'
```

Nếu seed node không sở hữu slot, CLI có thể đi theo thông báo `MOVED` tới node đúng. Không có `-c`, bạn có thể nhìn thấy lỗi chuyển hướng thay vì dữ liệu.

**Dấu `-c` không chữa lỗi `CROSSSLOT` của một lệnh nhiều key.** Nó giúp theo redirect node/slot, không thay đổi luật tất cả key của command phải cùng slot.

## 7. MOVED và ASK: khi bảng slot của client chưa khớp

Vì Cluster có thể failover hoặc resharding, slot map trong client đôi khi lạc hậu. Redis dùng các phản hồi điều hướng để hướng dẫn client.

### 7.1. MOVED: slot được phục vụ bởi node khác

Giả sử client nghĩ slot `12182` thuộc Master A, nhưng thực tế đã chuyển sang Master C:

```text
Client                   Master A                 Master C
   | GET foo                 |                       |
   |------------------------>|                       |
   |<------------------------| MOVED 12182 C:7002    |
   |                                                |
   | GET foo (gửi lại tới C)                        |
   |----------------------------------------------->|
   |<-----------------------------------------------| giá trị
```

`MOVED` thường được dùng khi địa chỉ phục vụ slot đã thay đổi. Cluster-aware driver có thể cập nhật mapping slot và gửi lại lệnh. Một phản hồi `MOVED` thường là tín hiệu tốt để refresh toàn bộ topology, nhất là khi failover làm đổi chủ nhiều slot.

`MOVED` **không có nghĩa Redis đã tự chuyển key trong chính lệnh `GET` đó**. Nó là thông báo client nên gửi lệnh tới node khác.

### 7.2. ASK: redirect tạm trong lúc chuyển slot

Khi một slot đang được chuyển từ Master A sang Master B:

```text
Slot s: MIGRATING ở A  ------>  IMPORTING ở B
          |
          +-- Key cũ còn ở A: A vẫn có thể phục vụ
          |
          +-- Key đã chuyển / không còn ở A:
                   A có thể trả ASK s B
```

Với `ASK`, client:

1. **Không** lập tức đổi mapping lâu dài của slot từ A sang B.
2. Mở/gửi lệnh đến B, trước lệnh đích gửi `ASKING`.
3. Chỉ chuyển hướng **lệnh hiện tại**; lệnh sau vẫn có thể hỏi A cho đến khi slot chuyển xong.

Ví dụ ở mức giao thức:

```text
GET order:{913}:state trên A
-> ASK <slot> B:7001

Kết nối tới B:
ASKING
GET order:{913}:state
-> dữ liệu
```

Khi hoàn tất migration, Redis sẽ dùng `MOVED` để client cập nhật owner mới. Lettuce/Jedis cluster-aware thường xử lý việc này ở tầng driver; ứng dụng hiếm khi phải gửi `ASKING` thủ công.

| Tình huống | `MOVED` | `ASK` |
|---|---|---|
| Ý nghĩa | Slot đang được node khác sở hữu | Chuyển hướng tạm thời khi slot đang được di chuyển |
| Cập nhật slot map lâu dài? | Nên cập nhật/refresh | Không cập nhật ngay |
| Có cần `ASKING` trước lệnh trên node đích? | Không | Có |
| Thường gặp | Client mới, failover, resharding hoàn tất | Giai đoạn đang migrate/import slot |

### 7.3. Chuyển slot có thể ảnh hưởng multi-key

Trong giai đoạn resharding, những key **cùng slot** có thể tạm ở các node khác nhau khi migration chưa hoàn tất. Một số lệnh nhiều key có thể gặp lỗi tạm thời như `TRYAGAIN`, dù theo hash tag chúng thuộc cùng slot. Vì vậy:

- Cấu hình timeout và retry có giới hạn.
- Không tự động retry lệnh có tác dụng phụ mà chưa xét idempotency.
- Đo lỗi redirect và topology change trong quá trình nâng cấp/rebalance.
- Thiết kế các thao tác nghiệp vụ quan trọng để chịu được thất bại tạm thời.

## 8. Resharding: thêm master mà không đổi hàm hash của key

Giả sử ba master đang sở hữu:

```text
Master A: slots 0..5460
Master B: slots 5461..10922
Master C: slots 10923..16383
```

Ứng dụng cần mở rộng, thêm Master D. Redis có thể chuyển một số slot từ A/B/C sang D:

```text
Trước:
   slot 1200 -> A
   slot 7200 -> B
   slot 13000 -> C

Sau resharding:
   slot 1200 -> D
   slot 7200 -> B
   slot 13000 -> C
```

Key `order:{913}:state` có slot `s` tính từ `913` **không đổi**. Nếu `s` nằm trong phần slot chuyển sang D, dữ liệu của key đó được di chuyển cùng slot và những yêu cầu mới phải route sang D.

**Redis Cluster không áp dụng consistent hashing trực tiếp trên danh sách node để đặt từng key.** Có một tầng hash slot ổn định ở giữa, làm cho việc di chuyển tập slot và cân bằng dữ liệu giữa các node dễ quản lý hơn.

Điều này khác với cách một số hệ thống phân mảnh gắn key trực tiếp vào node bằng vòng băm nhất quán. Trong Redis Cluster:

```text
key --CRC16--> slot --owner map--> master
```

Hàm key→slot ổn định; ánh xạ slot→master có thể thay đổi.

### 8.1. Phân phối số slot không đồng nghĩa phân phối tải bằng nhau

Cho ba master cùng nhận khoảng một phần ba slot, vẫn có thể xảy ra:

- Master A có nhiều key hơn vì phân bố key thực tế lệch.
- Master B có một hot key nhận hàng chục nghìn lệnh mỗi giây.
- Master C nhận nhiều value lớn hơn, nên dùng RAM cao hơn.
- Một hash tag quá rộng dồn phần lớn thao tác của một tenant vào một slot.

Vì vậy, cân bằng slot chỉ là **một công cụ**; cần quan sát memory, CPU, key count, throughput, command latency và hot keys theo từng node.

## 9. Replication và failover: key thuộc slot, không “gắn chết” vào một máy

Mỗi master có thể có replica:

```text
Slot group s
     |
     v
Master B ---------> Replica B'
 (phục vụ ghi)      (sao chép bất đồng bộ)
```

Khi B lỗi và điều kiện failover của Cluster được thỏa, Replica B' có thể được bầu thành master mới. Bảng owner của slot cập nhật để các client gửi lệnh tới B' thay vì B.

**Không cần đổi tên Redis key** sau failover. Slot của key không đổi. Điều thay đổi là node đang phục vụ slot.

Do replication của Redis Cluster thường bất đồng bộ, mất master có thể gây mất một số ghi mới chưa đến replica. Redis Cluster không phải hệ thống bảo đảm mọi lần ghi đã ACK đều bền vững trong mọi kịch bản phân vùng mạng. Cấu hình persistence, replication, tình trạng majority và quy tắc retry cần được đánh giá theo SLA.

### 9.1. Đọc replica khác với sở hữu slot

Một replica có thể được phép phục vụ một số lệnh đọc khi client gửi `READONLY` và driver được cấu hình read-from replica. Tuy nhiên:

- **Owner master** vẫn là nơi quyết định thao tác ghi của slot.
- Replica có thể **trễ** hơn master (eventual consistency).
- Không nên dùng dữ liệu replica để ra quyết định cần read-after-write mạnh mà không có thiết kế phù hợp.
- Driver có thể route lại tới master khi topology thay đổi hoặc khi replica không còn phù hợp.

Ứng dụng sử dụng `RedisTemplate` có thể chọn read preference ở connector tương ứng, nhưng đừng suy luận rằng chỉ cần thêm replica thì mọi lệnh đọc mặc nhiên chuyển sang replica.

## 10. Cấu hình Redis Cluster với Spring Data Redis

Spring Data Redis cung cấp abstraction `RedisClusterConfiguration` và `RedisClusterConnection`. Các connector như Lettuce/Jedis có thành phần cluster-aware để quản lý slot map và các redirect.

### 10.1. Spring Boot auto-configuration

Ví dụ cho Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a.example:7000
          - redis-b.example:7001
          - redis-c.example:7002
        max-redirects: 5
      connect-timeout: 3s
      timeout: 3s
```

Đây là **ví dụ cấu hình**, không phải địa chỉ Redis có thật. Cần thêm credentials/TLS và cấu hình discovery phù hợp môi trường. Khi dùng Spring Boot BOM, kiểm tra đúng phiên bản property và connector mặc định; không kết luận từ một ví dụ của phiên bản khác.

Với cấu hình cluster nodes và hạ tầng hợp lệ, ứng dụng có thể inject `StringRedisTemplate` và các template Redis như thường lệ. Driver đảm nhiệm định tuyến key đơn theo slot.

### 10.2. Tự tạo LettuceConnectionFactory

Nếu không dựa vào auto-configuration của Boot, có thể dùng:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class ClusterRedisConfiguration {

    @Bean
    public RedisConnectionFactory redisConnectionFactory() {
        RedisClusterConfiguration config =
                new RedisClusterConfiguration(List.of(
                        "redis-a.example:7000",
                        "redis-b.example:7001",
                        "redis-c.example:7002"
                ));
        config.setMaxRedirects(5);
        return new LettuceConnectionFactory(config);
    }
}
```

Không khai báo đồng thời một factory thủ công và mong Boot tạo factory mặc định cùng loại rồi tự chọn đúng. Nên xác định rõ nguồn cấu hình connection, TLS, password, pool và lifecycle của bean theo dự án.

### 10.3. RedisClusterConnection dùng khi nào?

`RedisClusterConnection` mở rộng khả năng thao tác Redis Cluster so với kết nối Standalone và giúp truy cập các thông tin điều hành theo API của Spring Data Redis. Trong phần lớn logic nghiệp vụ chỉ cần `RedisTemplate` hoặc `ReactiveRedisTemplate`; trực tiếp điều khiển cluster connection thường dành cho thao tác quản trị, chẩn đoán hoặc chức năng driver đặc thù.

Hãy để **driver** quyết định node đích cho lệnh thường. Một lệnh `GET` không nên yêu cầu service tự gọi `CLUSTER NODES`, tính slot rồi mở socket tới master mỗi lần truy cập.

## 11. Ví dụ Spring Data Redis: key đơn phân phối trên các node

Service dùng `StringRedisTemplate`:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ClusterKeyService {

    private final StringRedisTemplate redis;

    public ClusterKeyService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveStock(String productId, int stock) {
        redis.opsForValue().set(
                "product:" + productId + ":stock",
                Integer.toString(stock));
    }

    public String loadStock(String productId) {
        return redis.opsForValue().get(
                "product:" + productId + ":stock");
    }
}
```

Khi gọi:

```java
service.saveStock("100", 12);
service.saveStock("101", 5);
service.saveStock("102", 9);
```

key `product:100:stock`, `product:101:stock` và `product:102:stock` có thể thuộc các slot khác nhau, và driver tự route từng lệnh tới owner master tương ứng.

Đối với thao tác **một key**, ứng dụng thường không cần thêm hash tag. Cố gắng gắn mọi sản phẩm vào `{products}` chỉ để dễ nhớ sẽ dồn dữ liệu vào một slot, rất không phù hợp nếu muốn phân tải sản phẩm.

### 11.1. Multi-key cùng slot bằng StringRedisTemplate

Khi cần lấy trạng thái và tổng tiền của cùng đơn hàng:

```java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderCacheService {

    private final StringRedisTemplate redis;

    public OrderCacheService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> loadSummary(String orderId) {
        String tag = "{order-" + orderId + "}";
        List<String> keys = List.of(
                "order:" + tag + ":state",
                "order:" + tag + ":total"
        );

        return redis.opsForValue().multiGet(keys);
    }
}
```

Các key tạo ra có dạng:

```text
order:{order-913}:state
order:{order-913}:total
```

Chúng cùng slot, phù hợp với ràng buộc multi-key của Redis Cluster. Trong một application thật, cần xác thực `orderId` và chuẩn hóa cách đặt tên tag, không lấy chuỗi bất kỳ của người dùng ghép vào key rồi cho phép dấu ngoặc nhọn làm thay đổi slot ngoài ý muốn.

Nếu `orderId` có thể chứa `{` hoặc `}`, hãy **mã hóa/chuẩn hóa identifier** thành một định danh key an toàn trước khi tạo hash tag. Không muốn một input lạ như `orderId="{x}"` vô tình khiến Redis lấy sai phần tag.

### 11.2. Kết quả multiGet vẫn phải được diễn giải theo contract

`multiGet` có thể trả `null` hoặc danh sách chứa phần tử `null` tùy tình huống key không tồn tại và serializer. Đừng coi việc các key cùng slot đồng nghĩa dữ liệu của chúng luôn được tạo/xóa cùng lúc.

Để bảo đảm invariant nhiều trường của một đơn hàng, đôi khi tốt hơn là lưu các trường vào **một Redis Hash**:

```text
order:913
   field state = CREATED
   field total = 250000
```

Khi mọi dữ liệu liên quan đã ở trong **một Redis key**, các lệnh như `HGETALL` hoặc `HMGET` chỉ cần route theo slot của key đó, và không phát sinh `CROSSSLOT` giữa các field. Đây là một lựa chọn thiết kế quan trọng trước khi thêm hàng loạt key con.

## 12. Chọn mô hình key: nhiều key có tag hay một Redis Hash?

Giả sử một shopping cart có nhiều thành phần:

```text
cart:{user-42}:items
cart:{user-42}:total
cart:{user-42}:coupon
```

Tất cả cùng slot. Điều này cho phép một số thao tác có điều kiện giữa chúng bằng lệnh multi-key/script/transaction trong cùng shard.

Nhưng cũng có thể lưu:

```text
cart:user-42
    itemCount
    total
    coupon
```

như một Redis Hash nếu dữ liệu phù hợp.

| Tiêu chí | Nhiều key chung hash tag | Một Redis Hash |
|---|---|---|
| Số Redis key | Nhiều | Một |
| Cách phân phối | Cùng một slot theo tag | Một slot theo key Hash |
| TTL | Có thể khác giữa từng key | TTL áp dụng toàn bộ Hash key |
| Thao tác field | Theo loại dữ liệu của từng key | `HSET`/`HGET`/`HMGET` |
| Multi-key script/transaction | Cần cùng slot, phải quản lý key | Nhiều thay đổi có thể nằm trên một key |
| Mức tách biệt dữ liệu | Cao hơn | Gộp thành một aggregate |

Hash tag không phải công cụ thay thế mô hình dữ liệu. Nếu một aggregate có thể biểu diễn tự nhiên bằng một Redis Hash, việc đó thường giảm nhu cầu multi-key. Nếu cần cấu trúc độc lập, TTL riêng, Redis Set/List/Sorted Set khác nhau, nhiều key cùng tag có thể hợp lý hơn.

## 13. Spring Data Redis Repository và secondary indexes trên Cluster

Với Redis Repository:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;
    private String name;
}
```

Spring Data Redis có thể lưu entity vào keyspace với tên key dạng `customers:<id>` và tạo các key phụ trợ để quản lý ID hoặc secondary index. Trong Cluster:

- Key entity được hash theo **bytes của tên key** mà mapping/serializer tạo.
- Một key ID-set hoặc secondary index có **tên key khác** có thể nằm ở slot khác.
- TTL, index maintenance và thao tác repository có thể kéo theo nhiều lệnh Redis trên các key khác nhau.
- Không được giả định toàn bộ hạ tầng repository/secondary indexing trở thành một giao dịch nguyên tử trên Cluster chỉ vì entity có `@RedisHash`.

Khả năng sử dụng Repository với Redis Cluster có những hạn chế theo phiên bản/driver và loại thao tác. Khi thiết kế ứng dụng cần repository indexing, query phức tạp hoặc nhiều key phụ trợ, hãy kiểm tra đúng tài liệu tương thích Spring Data Redis và chạy integration test trên **Cluster thật** thay vì chỉ kiểm tra Standalone.

**Ghi nhớ:** hash tag áp dụng cho **tên Redis key**, không áp dụng cho field của Java object. Thêm `@Indexed` vào thuộc tính không có nghĩa Redis tự đặt entity key và index key cùng slot.

### 13.1. Cache và key prefix

Spring Cache với Redis thường đặt tên key như:

```text
products::p-100
products::p-101
inventory::p-100
```

Các key đó được phân tán theo CRC16 của **tên đầy đủ**, bao gồm prefix. Nếu vô tình dùng cùng hash tag cho mọi cache key, ví dụ `cache:{all}:...`, có thể dồn tải về một slot.

Khi cần nhiều cache key cùng slot vì một thao tác nhiều key có chủ đích, phải thiết kế prefix và key generation để tag có nghĩa nghiệp vụ. Đừng tắt prefix hoặc đặt một tag chung toàn bộ Redis chỉ để tránh `CROSSSLOT`.

## 14. Pipeline, transaction và Lua trên Cluster

Hash slot tác động khác nhau tùy loại thao tác.

| Tình huống | Khả năng trong Cluster | Điều kiện và lưu ý |
|---|---|---|
| Nhiều `GET` một key gọi riêng | Có | Driver định tuyến từng key |
| Một `MGET` nhiều key | Chỉ khi phù hợp slot hoặc API hỗ trợ fan-out riêng | Server-side `MGET` yêu cầu cùng slot |
| Một pipeline gồm nhiều `SET` độc lập | Có thể ở tầng cluster-aware client | Phụ thuộc driver/API, không phải một transaction |
| `MULTI`/`EXEC` nhiều key | Giới hạn theo cùng slot | Transaction không trải toàn Cluster và không có SQL rollback |
| Lua script đọc/ghi nhiều key | Các key phải đáp ứng quy tắc cùng slot | Không tự hỗ trợ cross-shard atomicity |
| Redis Function với nhiều key | Có giới hạn slot tương ứng | Tất cả key phải được khai báo/định tuyến đúng |
| Đọc từ replica | Có với cấu hình phù hợp | Có thể trả dữ liệu chậm cập nhật |

### 14.1. Pipeline không sửa luật hash slot

Ví dụ ứng dụng phát một loạt lệnh độc lập:

```text
SET user:1:status READY
SET user:2:status READY
SET user:3:status READY
```

Một driver cluster-aware có thể gửi chúng tới các node khác nhau theo từng slot. Nhưng **không phải mọi API pipeline trong Spring Data Redis đều hỗ trợ fan-out trên Cluster**; khả năng phụ thuộc phiên bản Spring Data Redis, Lettuce/Jedis và thao tác. Việc key khác slot không phải lỗi của từng `SET`, song adapter pipeline cụ thể vẫn có thể không hỗ trợ.

### 14.2. MULTI/EXEC không tạo một giao dịch toàn Cluster

Giả sử cần chuyển số dư giữa:

```text
account:{alice}:balance
account:{bob}:balance
```

Hai tag khác nhau có thể thuộc hai slot. Không thể giả định dùng `MULTI`/`EXEC` qua một cluster-aware `RedisTemplate` sẽ cập nhật cả hai key như một distributed ACID transaction.

Nếu nghiệp vụ cần rollback, tính nhất quán giao dịch mạnh hoặc ghi sổ, thường nên dùng nguồn dữ liệu giao dịch phù hợp (ví dụ RDBMS) làm nơi giữ dữ liệu chính, còn Redis cache/định tuyến hỗ trợ nhu cầu đọc nhanh. Việc ép các tài khoản vào cùng tag có thể tránh `CROSSSLOT`, nhưng **không tự sinh rollback kiểu SQL**, và có thể làm mất cân bằng tải.

### 14.3. Lua cùng-slot vẫn cần thiết kế tránh lỗi sau khi ghi

Redis cho phép script thực thi nguyên tử ở phạm vi shard, nhưng script **không tự rollback** các thao tác đã ghi nếu lỗi runtime xuất hiện sau đó. Hãy kiểm tra input/tiền điều kiện trước khi ghi và thiết kế idempotency cho trường hợp client mất phản hồi.

## 15. Redis Cluster không dùng nhiều logical database

Redis Standalone hỗ trợ nhiều logical database, ví dụ có thể `SELECT 0` hoặc `SELECT 1` theo cấu hình. Nhưng **Redis Cluster chỉ hỗ trợ database 0**; không dùng `SELECT 1` để chia tenant hoặc module trên một Cluster.

Nếu cần namespace, dùng prefix có chủ đích:

```text
dev:orders:913
prod:orders:913
tenantA:users:42
tenantB:users:42
```

Tuy nhiên, chỉ có prefix tên key không tự tạo isolation về bảo mật, quota hay vòng đời. Với môi trường cần cách ly mạnh, cân nhắc tách Redis deployment/cluster hoặc dùng cơ chế ACL và hạ tầng phù hợp.

Đừng nhầm prefix tên key với hash tag. Prefix thông thường vẫn tham gia tính CRC16 của toàn key; hash tag `{...}` thay đổi chính xác phần bytes dùng để hash.

## 16. SCAN/KEYS trên Cluster và vị trí của key

Trong Standalone, một lệnh `SCAN` có thể duyệt keyspace của server đó. Trong Cluster, **mỗi node chỉ giữ các key thuộc những slot nó phục vụ**, nên quét một node không đồng nghĩa quét toàn Cluster.

Ví dụ:

```bash
redis-cli -h 127.0.0.1 -p 7000 SCAN 0 MATCH 'product:*' COUNT 100
```

Kết quả chỉ phản ánh key trên node đang được hỏi. Nếu ứng dụng phải duyệt **toàn bộ keyspace**, cần sử dụng API cluster-aware có chiến lược quét tất cả các master liên quan, xử lý phân trang từng node và topology thay đổi.

Không dùng `KEYS *` trên production lớn để “xem tất cả key”. Nó có thể gây tải nghiêm trọng và khi chạy trên một node Cluster vẫn không đại diện toàn bộ dữ liệu.

Redis 8.0 có tối ưu một số glob-style pattern nhận diện một hash tag cố định để tìm trên slot tương ứng. Đây là tối ưu truy vấn pattern khi đáp ứng điều kiện, **không thay đổi** thuật toán CRC16 hoặc biến `SCAN` của một node thành một cluster-wide snapshot.

### 16.1. Thiết kế tránh quét Cluster cho truy vấn nghiệp vụ

Nếu thường xuyên cần “tìm toàn bộ đơn hàng đang chờ xử lý”, không nên dựa vào `SCAN order:*` trên hàng chục master cho mỗi HTTP request. Cân nhắc:

- Redis Set/Sorted Set làm index theo nghiệp vụ, có cơ chế duy trì nhất quán.
- Một kho dữ liệu hỗ trợ truy vấn phù hợp.
- Redis Streams cho luồng sự kiện công việc.
- Cơ chế lưu metadata/key index riêng, có mô hình shard rõ ràng.

Việc chia key theo hash slot giúp mở rộng Redis key-value; nó không tự biến Redis thành database truy vấn theo mọi thuộc tính.

## 17. Tối ưu phân phối key và tránh hot slot

Một thiết kế key tốt phải cân bằng hai mục tiêu **đôi khi xung đột**:

1. Phân phối tải và dữ liệu đều trên nhiều slot/master.
2. Giữ những key thật sự cần thao tác cùng nhau trong một slot.

### 17.1. Mô hình theo user

```text
user:{42}:profile
user:{42}:settings
user:{42}:cart

user:{43}:profile
user:{43}:settings
user:{43}:cart
```

Mỗi user có một nhóm key cùng slot; khác user có thể phân tán. Phù hợp nếu thường xuyên cần multi-key của **cùng user**.

Đánh đổi: user rất lớn/hot có thể dồn tải vào một slot. Đừng dựa vào giả định có hàng triệu user thì chắc chắn không có user nào nóng.

### 17.2. Mô hình theo order

```text
order:{913}:state
order:{913}:items
order:{913}:payment

order:{914}:state
order:{914}:items
order:{914}:payment
```

Mỗi order có các key liên quan cùng slot. Điều này hợp lý cho workflow cần đọc/cập nhật nhiều key một order, nhưng các báo cáo **cross-order** vẫn cần thiết kế riêng.

### 17.3. Đặt tag theo tenant lớn có thể gây bất cân bằng

```text
tenant:{enterpriseA}:user:1
tenant:{enterpriseA}:user:2
tenant:{enterpriseA}:user:3
...
```

Tất cả key của tenant `enterpriseA` thuộc một slot. Nếu tenant đó chiếm 60% tải, toàn bộ lượng tải đó có thể tập trung vào một master. Cách an toàn hơn có thể là tag theo user/order, hoặc chia tenant thành các partition như `{enterpriseA:bucket07}` khi nghiệp vụ không yêu cầu transaction trên toàn tenant.

### 17.4. Tránh hot key ngay cả khi slot phân bố đều

Nếu một key riêng `global:counter` nhận hầu hết lưu lượng, nó vẫn nằm trên **một slot** và **một master**. Chia đều 16.384 slot không thể song song hóa một lệnh `INCR global:counter` sang nhiều master. Cần thiết kế counter sharded, aggregation hoặc cơ chế dữ liệu khác nếu tải thật sự vượt khả năng một node.

## 18. Checklist sự cố và chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `GET` trả `MOVED` | Client kết nối sai owner hoặc slot map cũ | Dùng client cluster-aware/`redis-cli -c`, refresh topology |
| Lệnh nhận `ASK` | Slot đang được migrate | Driver phải gửi `ASKING` trước lệnh được redirect |
| `MGET` báo `CROSSSLOT` | Key trong cùng lệnh thuộc các slot khác nhau | `CLUSTER KEYSLOT` từng key; cân nhắc hash tag |
| `MGET` vẫn `CROSSSLOT` dù hai key ở cùng master | Hai key thuộc **hai slot** | Thiết kế lại tên key, không dựa vào cùng node |
| Hai key có tag giống nhau nhưng trong ứng dụng lại khác slot | Key bytes/serializer khác hoặc tag bị hình thành sai | In key bytes thực tế, kiểm tra dấu ngoặc và serializer |
| Dữ liệu của một key “chuyển node” sau rebalance | Slot owner đã thay đổi | Đối chiếu `CLUSTER SHARDS`/`NODES` trước và sau |
| Latency cao một master dù slot chia đều | Hot slot/key, value lớn, tải lệch | Đo per-node throughput, latency, memory, key size |
| Một node `SCAN` không thấy key nhưng `GET` qua cluster client lại thấy | Key thuộc node khác | Quét đúng owner hoặc dùng scan cluster-aware |
| Đọc replica trả giá trị cũ | Replication bất đồng bộ | Chọn master read cho đường cần độ mới mạnh |
| Lỗi kết nối sau lần redirect | Địa chỉ node Cluster công bố không truy cập được | Kiểm tra DNS, NAT, firewall, TLS, announce hostname/port |
| Spring Data Redis hoạt động Standalone nhưng lỗi trên Cluster | Cross-slot, pipeline/transaction/index hạn chế | Test tương thích đúng driver/API và key design |
| Mất một số ghi sau failover | Replication chưa kịp đồng bộ | Đánh giá durability, retry/idempotency, SLA |
| Lệnh `SELECT 1` không hoạt động | Cluster chỉ dùng logical database 0 | Dùng namespace hoặc tách deployment |

### 18.1. Những lệnh chẩn đoán thiết thực

```bash
# Tổng quan Cluster.
redis-cli -h 127.0.0.1 -p 7000 CLUSTER INFO

# Master/replica và các khoảng slot.
redis-cli -h 127.0.0.1 -p 7000 CLUSTER NODES
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SHARDS

# Slot của hai key cần thao tác chung.
redis-cli -h 127.0.0.1 -p 7000 \
  CLUSTER KEYSLOT 'order:{913}:state'
redis-cli -h 127.0.0.1 -p 7000 \
  CLUSTER KEYSLOT 'order:{913}:total'

# Client theo redirect.
redis-cli -c -h 127.0.0.1 -p 7000 \
  GET 'order:{913}:state'
```

Nếu `CLUSTER INFO` báo `cluster_state:fail`, vấn đề không chỉ là sai hash tag: phải kiểm tra slot coverage, master failure và khả năng liên lạc giữa các node.

## 19. Bài thực hành với Redis Cluster và Spring

### Bài 1 — Chứng minh key→slot

Trên Redis Cluster test:

```redis
CLUSTER KEYSLOT foo
CLUSTER KEYSLOT bar
CLUSTER KEYSLOT user:{42}:profile
CLUSTER KEYSLOT cart:{42}:items
CLUSTER KEYSLOT user:{43}:profile
```

Ghi lại slot, so sánh kết quả:

- `foo` và `bar` có thể khác slot.
- `user:{42}:profile` và `cart:{42}:items` chắc chắn cùng slot.
- `user:{43}:profile` thường khác slot với nhóm `{42}`.

Sau đó chạy hàm `RedisHashSlot.slot(...)` của mục 2 và so với `CLUSTER KEYSLOT`. Sự trùng khớp chứng minh cả hai đang hash cùng bytes, chưa bao gồm việc node hiện tại nào sở hữu slot.

### Bài 2 — Quan sát slot owner

1. Gọi `CLUSTER SHARDS` hoặc `CLUSTER SLOTS`.
2. Chọn một key, tìm slot của nó bằng `CLUSTER KEYSLOT`.
3. Tra slot thuộc khoảng master nào.
4. Gửi `GET` trên master khác khi không dùng `redis-cli -c` để quan sát `MOVED`.
5. Gửi lại với `redis-cli -c` để thấy CLI có thể tự theo redirect.

### Bài 3 — CROSSSLOT không phụ thuộc hai node có khác nhau không

1. Tìm hai key có slot khác nhau nhưng cùng owner master bằng `CLUSTER KEYSLOT` và `CLUSTER SHARDS`.
2. Chạy `MGET` trên hai key đó.
3. Quan sát `CROSSSLOT` dù owner master giống nhau.
4. Đổi key thành `k:{lab-350}:a` và `k:{lab-350}:b`.
5. Chạy `MSET` và `MGET` để thấy multi-key hoạt động khi cùng slot.

### Bài 4 — Đường đi Spring Data Redis

1. Cấu hình `spring.data.redis.cluster.nodes` cho test Cluster.
2. Dùng `StringRedisTemplate` lưu nhiều `product:<id>:stock`.
3. Đối chiếu key slot của các tên key tương ứng.
4. Dùng `OrderCacheService.loadSummary("913")` từ mục 11 để đọc hai key có chung hash tag.
5. Thay một key sang tag `{order-914}`, quan sát giới hạn của thao tác nhiều key trong adapter/server đang sử dụng.

### Bài 5 — Resharding chỉ trong môi trường test

1. Ghi lại owner của một slot.
2. Trong Cluster test được phép thay đổi, chuyển slot đó sang master khác bằng công cụ quản trị cluster.
3. Ghi lại slot ID của key trước và sau: **không đổi**.
4. Ghi lại owner master trước và sau: **thay đổi**.
5. Quan sát redirect `ASK` trong giai đoạn đang migrate và `MOVED` sau khi đổi owner, nếu công cụ/log có thể ghi nhận.
6. Kiểm tra client Spring kết nối lại/refresh topology và tiếp tục đọc key.

Không reshard production chỉ để thử bài tập. Việc chuyển slot có thể ảnh hưởng latency, lỗi tạm thời và các thao tác nhiều key.

### Bài 6 — Cảnh báo về hot slot

1. Tạo một nhóm key `test:{all}:1..N` và ghi nhận cùng slot.
2. Tạo một nhóm key `test:{user-1}:a`, `test:{user-2}:a`, ... và ghi nhận phân bố slot.
3. Thảo luận vì sao tag `{all}` có thể khiến mọi request của nhóm tập trung vào một node.
4. Chọn một cách đặt tên phù hợp nếu yêu cầu nghiệp vụ chỉ cần thao tác cùng-slot theo **mỗi order**, không phải toàn bộ tenant.

## 20. Câu hỏi tự kiểm tra

**1. Redis Cluster có bao nhiêu hash slot?** Có 16.384 slot, đánh số 0–16383. Một slot không phải một node.

**2. CRC16 quyết định trực tiếp IP master không?** Không. CRC16 quyết định slot; bảng slot→master quyết định node.

**3. Hai key khác nhau có thể thuộc cùng slot không?** Có. Hash tag chung bảo đảm điều này, và các key khác cũng có thể vô tình trùng slot do va chạm hash.

**4. Hai key ở cùng master nhưng khác slot có chạy `MGET` cùng lúc được không?** Lệnh `MGET` server-side vẫn có thể báo `CROSSSLOT` vì quy tắc là cùng slot, không phải cùng master. Có thể chia thành hai `GET` độc lập nếu semantics cho phép.

**5. Hash tag thay đổi dữ liệu value hoặc ID entity không?** Không. Hash tag chỉ ảnh hưởng phần bytes được dùng để tính slot từ **tên key**.

**6. Khi thêm master, phải đổi tên mọi key không?** Không. Redis di chuyển một phần slot và dữ liệu liên quan; key→slot không đổi, owner slot có thể thay đổi.

**7. Redis Cluster có hỗ trợ `SELECT 1` để phân tách tenant không?** Không; Cluster chỉ dùng database 0.

**8. `MOVED` khác `ASK` ở đâu?** `MOVED` hướng tới cập nhật mapping owner, còn `ASK` là chuyển hướng tạm cho một lệnh trong lúc migration và cần `ASKING` ở node đích.

## 21. Kết luận

Redis Cluster phân phối khóa qua **hai tầng**:

```text
Redis key bytes
    |
    | CRC16/XMODEM
    v
Hash slot (0..16383)
    |
    | Slot ownership map
    v
Master node đang phục vụ slot
```

Thuật toán hash key→slot ổn định; ánh xạ slot→master có thể đổi trong quá trình failover/resharding. Spring Data Redis và các driver cluster-aware giúp ứng dụng tự định tuyến lệnh đơn, nhưng không xóa ràng buộc **các key trong cùng một lệnh nhiều key phải cùng slot**.

Hash tag như `order:{913}:state` và `order:{913}:total` là cách kiểm soát placement của một nhóm key, hữu ích cho multi-key và workflow cùng aggregate. Tuy nhiên, lạm dụng một tag cho quá nhiều key tạo hot slot và làm mất khả năng phân tải.

Để thiết kế đúng, hãy kiểm tra **bytes của key sau serialization**, xác định những key thật sự cần cùng slot, chọn tag theo ranh giới nghiệp vụ, quan sát topology với `CLUSTER SHARDS`/`CLUSTER KEYSLOT`, và nhớ rằng `MOVED`/`ASK` là hoạt động bình thường khi Cluster thay đổi. Với transaction, pipeline, Repository indexing và truy vấn toàn Cluster, luôn kiểm tra giới hạn API/driver cụ thể thay vì mặc định Redis Cluster hoạt động giống một Redis Standalone lớn.

## Tài liệu tham khảo

- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): 16.384 slot, CRC16/XMODEM, hash tag, chủ sở hữu slot, `MOVED`/`ASK` và resharding.
- [Redis — Scale with Redis Cluster](https://redis.io/docs/latest/management/scaling/): giải thích phân phối key theo hash slot và thêm/bớt node.
- [Redis — CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/): tìm hash slot của key.
- [Redis — CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/): khám phá shard, slot và master/replica.
- [Redis — CLUSTER INFO](https://redis.io/docs/latest/commands/cluster-info/): trạng thái slot coverage và sức khỏe Cluster.
- [Redis — ASK error](https://redis.io/docs/latest/develop/reference/errors/common/ask/): chuyển hướng tạm khi migrate slot.
- [Redis — CROSSSLOT error](https://redis.io/docs/latest/develop/reference/errors/common/crossslot/): giới hạn multi-key trên Cluster.
- [Spring Data Redis — Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html): `RedisClusterConfiguration`, `RedisClusterConnection` và connector.
- [Spring Data Redis — Drivers](https://docs.spring.io/spring-data/redis/reference/redis/drivers.html): so sánh khả năng Lettuce/Jedis với Cluster.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): keyspace của entity và những thành phần phụ trợ.
