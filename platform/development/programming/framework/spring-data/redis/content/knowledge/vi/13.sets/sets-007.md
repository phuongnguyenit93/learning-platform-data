# Giới hạn lệnh nhiều khóa khi chạy trên Cluster

Redis Set là cấu trúc dữ liệu hữu ích để lưu các tập phần tử không trùng nhau: danh sách người dùng thuộc nhóm, quyền truy cập, mã sản phẩm đủ điều kiện hoặc tập ID của các bản ghi. Trong Spring Data Redis, API `SetOperations` cho phép thao tác dễ dàng với các lệnh như `SADD`, `SINTER`, `SUNION`, `SDIFF` và `SMOVE`.

Khi Redis chạy ở chế độ **standalone**, nhiều thao tác trên các Set khác nhau có thể thực thi trên cùng một server. Nhưng khi triển khai **Redis Cluster**, những key này được phân vào nhiều **hash slot**, có thể nằm trên các primary khác nhau. Redis không thể mặc nhiên thực hiện một lệnh tính hợp, giao, hiệu hoặc di chuyển phần tử qua nhiều slot như thể tất cả dữ liệu đang ở một nơi.

Đối với Spring Data Redis, cần hiểu rõ hai tầng khác nhau:

1. **Giới hạn của lệnh Redis chạy trên server:** phần lớn các lệnh Set chứa nhiều Redis key yêu cầu tất cả key thuộc **cùng một hash slot**.
2. **Hành vi của client/framework:** một số thao tác cross-slot có thể được driver hoặc Spring Data Redis mô phỏng bằng nhiều lệnh đơn khóa rồi tổng hợp ở phía Java. Cách này khác với một lệnh nguyên tử trên Redis server, có chi phí và giới hạn riêng, đồng thời không phải thao tác nào cũng được hỗ trợ.

Bài học tập trung vào cách phân biệt hai tầng đó, thiết kế tên key có **hash tag**, kiểm tra lỗi `CROSSSLOT`, và lựa chọn chiến lược phù hợp khi bài toán thực sự cần tập hợp dữ liệu trên nhiều shard.

> **Ngữ cảnh:** Các ví dụ Java dùng Spring Boot 3.3.x, Spring Data Redis 3.3.x và Lettuce. Khả năng tự xử lý cross-slot có thể khác giữa các driver, phiên bản và phương thức gọi, đặc biệt trong pipeline/transaction. Không nên coi việc một API Java chạy thành công là bằng chứng rằng Redis đã thực hiện một lệnh nhiều khóa nguyên tử trên server.

## 1. Phân biệt “nhiều phần tử” với “nhiều khóa”

Đây là điểm đầu tiên cần làm rõ. Một Redis Set là **một Redis key** chứa nhiều member:

~~~redis
SADD shop:42:favorite-products p1 p2 p3
SMEMBERS shop:42:favorite-products
SISMEMBER shop:42:favorite-products p2
SCARD shop:42:favorite-products
~~~

`SADD` ở đây nhận nhiều **member**, nhưng chỉ thao tác với **một Redis key** là `shop:42:favorite-products`. Redis Cluster có thể định tuyến cả lệnh tới slot chứa key này; việc có ba member không biến nó thành một lệnh cross-slot.

Ngược lại:

~~~redis
SINTER shop:42:favorite-products shop:42:in-stock-products
~~~

`SINTER` nhận **hai Redis key**. Dù cả hai có kiểu SET, cluster phải xác định xem có thể xử lý cả hai trên cùng một hash slot hay không.

| Command | Số Redis key liên quan | Vai trò |
|---|---:|---|
| `SADD key member [member ...]` | 1 | Thêm nhiều member vào một Set |
| `SREM key member [member ...]` | 1 | Xóa nhiều member khỏi một Set |
| `SMEMBERS key`, `SSCAN key cursor` | 1 | Đọc/duyệt thành viên một Set |
| `SISMEMBER key member`, `SMISMEMBER key member ...` | 1 | Kiểm tra membership |
| `SINTER key1 key2 ...` | Từ 1 trở lên | Giao các Set |
| `SUNION key1 key2 ...` | Từ 1 trở lên | Hợp các Set |
| `SDIFF key1 key2 ...` | Từ 1 trở lên | Hiệu Set đầu với các Set còn lại |
| `SMOVE source destination member` | 2 | Chuyển một member giữa hai Set |
| `SINTERSTORE destination key1 key2 ...` | Nhiều key gồm cả destination | Tính giao rồi ghi kết quả vào Set đích |

**Số member không phải tiêu chí phân slot**. Redis Cluster băm tên *key* để định tuyến. Số lượng key được một command truy cập mới quyết định một giới hạn nhiều khóa có liên quan hay không.

## 2. Redis Cluster chia key vào 16.384 hash slot

Redis Cluster chia keyspace thành **16.384 hash slot**, đánh số từ 0 đến 16383. Mỗi primary giữ một tập slot. Với key thông thường, slot được tính gần như:

~~~text
slot = CRC16(keyBytes) mod 16384
~~~

Ngoại lệ quan trọng là **hash tag** nằm trong dấu ngoặc nhọn, sẽ được giải thích chi tiết ở phần sau.

Ví dụ sơ đồ:

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Data Redis"] --> B["Cluster-aware Lettuce driver"]
    B --> S{"Hash slot của key"}
    S -->|slot thuộc nhóm A| P1["Primary A"]
    S -->|slot thuộc nhóm B| P2["Primary B"]
    S -->|slot thuộc nhóm C| P3["Primary C"]
    P1 --> K1["Set A"]
    P2 --> K2["Set B"]
    P3 --> K3["Set C"]
~~~

Nếu hai Set thuộc hai slot khác nhau thì **không thể gửi một `SINTER` server-side duy nhất** để tính giao trực tiếp trên cả hai key trong Redis Open Source Cluster, kể cả khi do tình cờ hai slot đang được cùng một node quản lý. Điều kiện là **cùng slot**, không chỉ là “cùng IP” hoặc “cùng primary”.

Để thấy giới hạn, xem một ví dụ mô tả thao tác trên Redis Cluster:

~~~redis
SADD cohort:active u1 u2 u3
SADD cohort:paid u2 u3 u4
SINTER cohort:active cohort:paid
~~~

Hai key không có hash tag chung nên **không được bảo đảm** cùng slot. Nếu thực tế chúng rơi vào hai slot khác nhau và lệnh `SINTER` được gửi trực tiếp đến server, Redis trả lỗi tương tự:

~~~text
(error) CROSSSLOT Keys in request don't hash to the same slot
~~~

Việc một cặp key ngẫu nhiên có cùng slot hoàn toàn có thể xảy ra do hash collision; vì thế phải **kiểm tra slot thực tế**, không kết luận lỗi chỉ bằng cách nhìn tên.

### 2.1. Dùng `CLUSTER KEYSLOT` để biết slot của key

Khi kết nối tới một Redis Cluster trong môi trường thử nghiệm:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT cohort:active
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT cohort:paid
~~~

Hai lệnh trả về số slot thực tế. Nếu số slot khác nhau, một lệnh `SINTER cohort:active cohort:paid` trực tiếp trên cluster sẽ không thể được xử lý như một lệnh server-side duy nhất.

Ở đây `-c` cho phép `redis-cli` theo các phản hồi chuyển hướng `MOVED`/`ASK` khi phù hợp. **`-c` không làm một lệnh `CROSSSLOT` hợp lệ** và không tự mang hai key về cùng slot.

`CLUSTER KEYSLOT` tính slot theo **bytes tên key**. Nếu ứng dụng Java dùng serializer không giống chuỗi bạn nhập bằng CLI, số slot của key thực tế có thể khác. `StringRedisTemplate` với serializer chuỗi thống nhất giúp việc đối chiếu giữa Java và CLI dễ hơn.

## 3. Những lệnh Set nhiều khóa chịu giới hạn nào?

Các phép tập hợp quan trọng:

~~~text
A = {u1, u2, u3}
B = {u2, u3, u4}

A ∩ B = {u2, u3}           SINTER
A ∪ B = {u1, u2, u3, u4}   SUNION
A - B = {u1}               SDIFF A B
B - A = {u4}               SDIFF B A
~~~

Trên Redis Cluster, **mọi key tham gia cùng một lệnh Set nhiều khóa phải được xử lý trong cùng hash slot** để Redis server có thể thực thi lệnh đó.

| Redis command | Đặc điểm | Các key cần cùng slot khi thực thi server-side |
|---|---|---|
| `SINTER key1 key2 ...` | Trả giao các tập | Tất cả key nguồn |
| `SUNION key1 key2 ...` | Trả hợp các tập | Tất cả key nguồn |
| `SDIFF key1 key2 ...` | Trả hiệu, thứ tự nguồn quan trọng | Tất cả key nguồn |
| `SINTERCARD numkeys key1 ... [LIMIT n]` | Trả lực lượng giao; Redis 7.0+ | Tất cả key nguồn |
| `SINTERSTORE dest key1 key2 ...` | Ghi giao vào `dest` | **Destination và mọi key nguồn** |
| `SUNIONSTORE dest key1 key2 ...` | Ghi hợp vào `dest` | **Destination và mọi key nguồn** |
| `SDIFFSTORE dest key1 key2 ...` | Ghi hiệu vào `dest` | **Destination và mọi key nguồn** |
| `SMOVE source dest member` | Chuyển member từ nguồn sang đích | Cả `source` và `dest` |

Với nhóm `*STORE`, một sai lầm hay gặp là chỉ đặt các key nguồn cùng slot rồi đặt `destination` ở keyspace khác. **Destination cũng là một Redis key trong cùng command**, nên nó phải cùng slot khi muốn một lần thực thi server-side.

Ví dụ một lệnh không an toàn về slot:

~~~redis
SINTERSTORE campaign:result shop:{42}:active shop:{42}:paid
~~~

Hai nguồn có hash tag `42`, nhưng `campaign:result` không có tag đó. Để có một lệnh server-side hợp lệ, dùng đích cùng tag:

~~~redis
SINTERSTORE shop:{42}:campaign-result shop:{42}:active shop:{42}:paid
~~~

`SMOVE` cũng không ngoại lệ: `source` và `destination` phải cùng slot nếu thao tác chuyển member muốn chạy nguyên tử tại Redis server.

### 3.1. Vì sao Redis áp giới hạn này?

Một lệnh `SINTER` trên một Redis server có thể đọc nội dung hai Set, thực hiện phép giao và trả kết quả. Trong Cluster, nếu hai key nằm ở các primary khác nhau, một primary không có toàn bộ dữ liệu để tính giao. Redis Open Source Cluster không tự thực hiện transaction phân tán hoặc gửi một lệnh Set sang nhiều shard rồi đồng thuận kết quả.

Đây là quyết định thiết kế có liên hệ đến khả năng mở rộng và độ phức tạp phân tán:

- **Một slot:** server đang sở hữu slot có thể xử lý command theo mô hình Redis bình thường.
- **Nhiều slot:** ứng dụng phải đổi mô hình lưu dữ liệu, hoặc chấp nhận nhiều thao tác độc lập và tổng hợp ở phía client.
- **Giao dịch/phép ghi nhiều khóa:** nếu tách ra nhiều command/primary thì không còn nguyên tử như một command duy nhất.

Redis có thể cân bằng các slot giữa primary khác nhau khi thêm/bớt node. Nhưng **thay đổi primary đang sở hữu slot không làm thay đổi con số slot của key**, vì con số đó được tính từ tên key.

## 4. Hash tag: giữ các Set liên quan ở cùng slot

Redis Cluster hỗ trợ quy tắc hash tag: nếu tên key có cặp ngoặc nhọn hợp lệ chứa chuỗi không rỗng, phần bên trong được dùng để tính slot thay cho toàn bộ key.

Ví dụ:

~~~text
shop:{42}:active-customers
shop:{42}:paid-customers
shop:{42}:eligible-customers
shop:{42}:campaign-result
~~~

Bốn key này có cùng hash tag `42`, nên **chắc chắn cùng hash slot** trong Redis Cluster theo quy tắc hash tag chuẩn, dù phần còn lại của tên khác nhau.

### 4.1. Ví dụ CLI hoàn chỉnh

~~~redis
SADD shop:{42}:active-customers u1 u2 u3
SADD shop:{42}:paid-customers u2 u3 u4

SINTER shop:{42}:active-customers shop:{42}:paid-customers
SUNION shop:{42}:active-customers shop:{42}:paid-customers
SDIFF shop:{42}:active-customers shop:{42}:paid-customers

SINTERSTORE shop:{42}:campaign-result shop:{42}:active-customers shop:{42}:paid-customers
SMEMBERS shop:{42}:campaign-result
~~~

Kết quả theo logic tập hợp là:

- Giao: `{u2, u3}`.
- Hợp: `{u1, u2, u3, u4}`.
- Hiệu `active - paid`: `{u1}`.
- Destination `campaign-result`: chứa giao `{u2, u3}`.

Redis Set không duy trì thứ tự phần tử, nên thứ tự hiển thị trong `SMEMBERS`, `SINTER` hoặc `SUNION` không phải một phần của hợp đồng kết quả. Không nên viết code phụ thuộc thứ tự mặc định của Set.

Để xác nhận cùng slot:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'shop:{42}:active-customers'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'shop:{42}:paid-customers'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'shop:{42}:campaign-result'
~~~

Ba câu trả lời phải cùng số slot khi Redis sử dụng thuật toán Redis Cluster chuẩn.

### 4.2. Hash tag có quy tắc cú pháp riêng

Một số tên key:

| Key | Phần được băm |
|---|---|
| `shop:{42}:active` | `42` |
| `shop:{42}:paid` | `42` |
| `shop:{43}:active` | `43` |
| `shop:{}:active` | Toàn bộ tên key vì tag đầu tiên rỗng |
| `shop:42:active` | Toàn bộ tên key vì không có hash tag |
| `shop:{42}:active:{other}` | Phần tag hợp lệ đầu tiên, tức `42` |

Đừng cho rằng mọi cặp ngoặc nhọn trong tên key đều được Redis hiểu theo ý bạn. Quy tắc tập trung vào **cặp ngoặc nhọn đầu tiên phù hợp**. Một tag rỗng không đem lại hiệu ứng pin slot.

Dùng ngoặc nhọn trong **tên key**, không phải trong value hoặc member của Set. Ví dụ:

~~~redis
SADD shop:active "{42}"
~~~

không khiến key `shop:active` được phân vào slot của tag `42`, vì `{42}` ở đây là **member**, không phải tên Redis key.

### 4.3. Nên chọn phần nào làm hash tag?

Chọn theo **đơn vị dữ liệu cần thực hiện lệnh nhiều khóa cùng nhau**:

| Nhóm dữ liệu | Key mẫu | Điều được co-locate |
|---|---|---|
| Các Set của một shop | `shop:{42}:active`, `shop:{42}:paid` | Các Set của shop 42 |
| Danh sách quyền của một user | `user:{u123}:roles`, `user:{u123}:permissions` | Các Set của user u123 |
| Các phiên bản của một batch | `batch:{run-77}:before`, `batch:{run-77}:after` | Set cùng batch |
| Dữ liệu của một tenant nhỏ | `tenant:{acme}:group-a`, `tenant:{acme}:group-b` | Các Set của tenant acme |

Điều quan trọng không phải đặt dấu `{ }` ở vị trí nào cho đẹp mà là xác định: **những key nào thực sự cần cùng tham gia một lệnh Set nhiều khóa?**

## 5. Dùng hash tag quá rộng có thể làm hỏng cân bằng tải

Một cách “chữa” `CROSSSLOT` nguy hiểm là đặt chung một tag cho mọi key:

~~~text
{all}:shop:42:active
{all}:shop:57:active
{all}:shop:92:active
{all}:global:campaign
~~~

Tất cả key có tag `all` được đưa vào **cùng hash slot**. Redis Cluster chỉ có thể gán một slot cho một primary tại một thời điểm, nên nhiều key lớn và traffic cao sẽ dồn lên cùng một primary.

Hệ quả tiềm ẩn:

- Bộ nhớ và CPU tập trung vào một node.
- Một keyspace có tập hợp rất lớn gây tăng độ trễ chung.
- Khó tận dụng việc thêm primary để scale workload này.
- Khi chuyển slot, có thể có thêm áp lực migration và tạm gián đoạn một số multi-key command.

Hash tag giải quyết bài toán **cùng slot**, không tự giải quyết giới hạn dung lượng, tốc độ hoặc tính sẵn sàng.

### 5.1. “Pin theo tenant” cũng có đánh đổi

Nếu mỗi tenant có rất ít key và truy vấn nhiều khóa thường xuyên, pin theo tenant có thể hợp lý. Nhưng một tenant rất lớn vẫn dồn mọi key của tenant vào một slot.

Khi tenant lớn, cần cân nhắc phân vùng sâu hơn, chẳng hạn theo tenant + nhóm đối tượng hoặc partition của nghiệp vụ, và chấp nhận rằng một số phép tập hợp toàn tenant phải được tính qua nhiều bước.

Quyết định đúng phụ thuộc vào:

1. Số key và tổng RAM cho một tag.
2. Lượng request/giây và độ phức tạp các phép Set.
3. Tần suất cần giao/hợp/hiệu nhiều key với nhau.
4. Kích thước kết quả và số member.
5. Khả năng tách các phép tính toàn cục ra khỏi đường request nóng.

Không thể vừa buộc mọi key trên toàn cluster vào một slot, vừa kỳ vọng Cluster chia đều các key đó lên nhiều primary.

## 6. Spring Data Redis biểu diễn các phép Set ra sao?

Spring Data Redis cung cấp `SetOperations<K, V>`, thường lấy từ:

~~~java
SetOperations<String, String> sets = stringRedisTemplate.opsForSet();
~~~

Một số API tương ứng:

| Spring Data Redis | Ý nghĩa Redis |
|---|---|
| `sets.add(key, members...)` | `SADD` |
| `sets.members(key)` | `SMEMBERS` |
| `sets.intersect(keyA, keyB)` | `SINTER` hoặc cơ chế tương đương theo connection |
| `sets.union(keyA, keyB)` | `SUNION` hoặc cơ chế tương đương theo connection |
| `sets.difference(keyA, keyB)` | `SDIFF` hoặc cơ chế tương đương theo connection |
| `sets.intersectAndStore(keyA, keyB, destination)` | `SINTERSTORE` hoặc cách xử lý tương ứng |
| `sets.unionAndStore(keyA, keyB, destination)` | `SUNIONSTORE` hoặc cách xử lý tương ứng |
| `sets.differenceAndStore(keyA, keyB, destination)` | `SDIFFSTORE` hoặc cách xử lý tương ứng |
| `sets.move(source, value, destination)` | `SMOVE` hoặc cách xử lý tương ứng |

Chữ “hoặc cơ chế tương đương” là điểm quan trọng: API cấp cao không bắt buộc mọi lần gọi đều gửi **đúng một Redis command**. Trong môi trường Redis Cluster, một số kết quả có thể được Spring Data Redis hoặc driver thực hiện bằng nhiều lệnh và tổng hợp phía client. Điều này phụ thuộc vào từng method, connection implementation, phiên bản và chế độ pipeline/transaction.

### 6.1. Cấu hình Spring Boot kết nối Redis Cluster

Với Boot 3.x:

~~~yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-node-1.internal:6379
          - redis-node-2.internal:6379
          - redis-node-3.internal:6379
      connect-timeout: 2s
      timeout: 3s
~~~

Các hostname chỉ là ví dụ; chúng phải tồn tại trong môi trường triển khai. Danh sách node là các endpoint khởi đầu để driver phát hiện topology Cluster. Một Redis instance standalone bình thường không trở thành Cluster chỉ vì client khai báo nhiều node.

Redis Cluster chỉ hỗ trợ logical database 0, nên không dựa vào `spring.data.redis.database: 2` để chia nhóm dữ liệu khi chuyển sang Cluster.

Với `spring-boot-starter-data-redis`, Lettuce thường là driver mặc định và có khả năng kết nối Cluster. Việc driver tự xử lý chuyển hướng `MOVED`, `ASK` cho một key **không đồng nghĩa** nó tự biến mọi lệnh nhiều key khác slot thành lệnh server-side hợp lệ.

### 6.2. Ví dụ service đặt key cùng slot

~~~java
import java.util.Objects;
import java.util.Set;

import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ShopEligibilityService {

    private final SetOperations<String, String> sets;

    public ShopEligibilityService(StringRedisTemplate redis) {
        this.sets = redis.opsForSet();
    }

    private String key(String shopId, String suffix) {
        return "shop:{" + shopId + "}:" + suffix;
    }

    public void markActive(String shopId, String userId) {
        sets.add(key(shopId, "active"), userId);
    }

    public void markPaid(String shopId, String userId) {
        sets.add(key(shopId, "paid"), userId);
    }

    public Set<String> findEligible(String shopId) {
        Set<String> result = sets.intersect(
                key(shopId, "active"),
                key(shopId, "paid")
        );

        // Ví dụ được gọi trực tiếp, ngoài pipeline/transaction.
        // SetOperations có thể trả null khi queue lệnh trong
        // pipeline/transaction; không coi null tạm thời là Set rỗng.
        return Objects.requireNonNull(
                result,
                "Expected direct Redis Set result"
        );
    }

    public Long storeEligible(String shopId) {
        return sets.intersectAndStore(
                key(shopId, "active"),
                key(shopId, "paid"),
                key(shopId, "eligible")
        );
    }
}
~~~

Mỗi nhóm key của **cùng shopId** có tag giống nhau nên cùng slot. Các shop khác nhau vẫn có thể phân tán trên nhiều slot.

Đoạn code giả định `shopId` là định danh đã được validate, không chứa dấu ngoặc nhọn làm thay đổi quy tắc hash tag. Với dữ liệu đến từ người dùng, nên chuẩn hóa/kiểm soát định dạng ID trước khi dựng tên key.

`storeEligible` trả số phần tử của kết quả được ghi theo ngữ nghĩa API khi gọi trực tiếp và command thành công. Trong pipeline/transaction, một số method RedisTemplate trả `null` tạm thời vì response chưa được thu thập; phải lấy kết quả từ danh sách trả về sau thực thi.

### 6.3. Serializer cũng ảnh hưởng đến hash slot

Redis tính slot từ **tên key thực tế ở dạng bytes**, không từ chuỗi Java trước khi serialize.

Nếu một service dùng `StringRedisSerializer` cho Redis key nhưng service khác dùng JDK serialization hoặc JSON serializer cho tên key, chúng có thể gửi hai tên byte-level khác nhau dù cùng input Java `"shop:{42}:active"`.

Vì vậy:

- Thống nhất `keySerializer` ở mọi code path.
- Với key name dạng văn bản, `StringRedisTemplate` hoặc `StringRedisSerializer` thường dễ kiểm soát.
- Không tự suy rằng chuỗi gốc có tag đúng nghĩa nếu serializer làm thay đổi bytes.
- Kiểm tra slot thực tế khi đổi định dạng tên key.

Serializer của **Set member** ảnh hưởng giá trị thành viên và khả năng so sánh phần tử giữa các Set; serializer của **Redis key** mới ảnh hưởng trực tiếp đến hash slot.

## 7. Cross-slot trong Spring Data Redis: có thể tự tính ở client không?

Cần tránh kết luận quá đơn giản rằng “mọi lời gọi `SetOperations.intersect()` qua cluster đều luôn trả `CROSSSLOT`”. Có những triển khai cluster-aware trong Spring Data Redis xử lý một số thao tác trên nhiều slot bằng cách đọc dữ liệu từng key rồi kết hợp ở phía client.

Tài liệu Spring Data Redis nêu ví dụ `MGET` trên nhiều slot có thể được tách thành các lệnh `GET`; đối với một số phép giao/hợp Set, Spring Data Redis cũng có thể phải **tính ở client** khi key không cùng slot. Nhưng cũng có những operation không thể chuyển sang nhiều lệnh đơn một cách an toàn và sẽ báo lỗi.

Vì thế phân biệt:

| Trường hợp | Điều cần hiểu |
|---|---|
| Gửi trực tiếp `SINTER keyA keyB` đến Redis Cluster server khi khác slot | Redis server trả `CROSSSLOT` |
| Gọi API cluster-aware của Spring Data Redis | Một số operation có thể được mô phỏng tại client; phải xem đúng implementation và version |
| Gọi cùng API khi hai key cùng slot | Có thể dùng lệnh Set server-side trực tiếp |
| Kết hợp nhiều slot bằng nhiều lệnh Java | Không có snapshot/atomicity toàn cluster theo mặc định |
| Kết hợp trong pipeline Redis Cluster | Có thêm giới hạn hỗ trợ theo driver và operation |

**Không nên xây dựng tính đúng đắn nghiệp vụ dựa trên suy đoán về hành vi fallback.** Cần biết rõ operation đang được thực hiện trên server hay trên client, dữ liệu được sao chép qua mạng bao nhiêu và các thay đổi đồng thời ảnh hưởng đến kết quả thế nào.

### 7.1. Cross-slot client-side có thể tốn nhiều RAM

Giả sử hai Set nằm ở hai slot:

~~~text
segment:{east}:customers  → 1.500.000 IDs
segment:{west}:customers  → 1.200.000 IDs
~~~

Nếu tính hợp/giao tại phía client bằng cách đọc toàn bộ thành viên của từng Set, ứng dụng có thể phải nhận hàng triệu phần tử qua mạng và giữ chúng trong heap trước khi trả kết quả.

Hệ quả:

- Network throughput tăng đáng kể.
- Redis node phải truyền nhiều dữ liệu; client phải deserialize nhiều member.
- JVM tăng heap pressure và GC.
- Latency bị chi phối bởi Set lớn và đường mạng chậm nhất.
- Kết quả cuối cùng có thể quá lớn để trả qua REST API hoặc lưu ở nơi khác.

Một phép giao chỉ trả vài ID vẫn có thể tốn chi phí đọc một lượng dữ liệu khổng lồ để tìm ra các ID đó. Vì vậy mức độ nhỏ của **kết quả** không đồng nghĩa mức độ nhỏ của **phép tính**.

### 7.2. Client-side nhiều bước không có snapshot nguyên tử

Giả sử:

~~~text
Thời gian      Request đọc                     Request khác
t1             Đọc Set A
t2                                             SADD A u9
t3                                             SREM B u9
t4             Đọc Set B
t5             Tính A ∩ B ở Java
~~~

Hai Set được đọc ở hai thời điểm khác nhau. Kết quả tính tại Java có thể không tương ứng với trạng thái của cả hai Set tại một thời điểm duy nhất. Kể cả mỗi lệnh `SMEMBERS` riêng lẻ được Redis thực hiện nguyên tử, cả chuỗi **đọc A → đọc B → tính toán** vẫn không phải transaction phân tán.

Nếu bài toán chỉ là gợi ý sản phẩm, cache tìm kiếm hoặc thống kê gần đúng, tính nhất quán cuối cùng có thể chấp nhận được. Nếu đây là phép quyết định quyền truy cập, chuyển tiền hay số lượng hàng tồn, cần xác định mức nhất quán và nguồn dữ liệu chuẩn riêng.

### 7.3. Đừng lẫn client fallback với transaction

Một lệnh server-side trên cùng slot và một chuỗi lệnh client-side khác slot có thuộc tính khác nhau:

| Thuộc tính | Một lệnh server-side cùng slot | Nhiều lệnh client-side khác slot |
|---|---|---|
| Nơi tính giao/hợp | Redis server | Java hoặc driver |
| Số lượt giao tiếp | Có thể là một command | Có thể nhiều command/round trip |
| Snapshot kết quả khi command chạy | Trong ngữ nghĩa một command Redis | Không có snapshot xuyên shard theo mặc định |
| Chi phí truyền dữ liệu thành viên | Thường chỉ truyền kết quả | Có thể phải tải tập nguồn |
| Tính nguyên tử khi ghi destination | Command như `SINTERSTORE` theo cơ chế Redis cùng slot | Phải thiết kế cập nhật đích riêng |
| Khả năng dùng trong transaction/pipeline | Theo cơ chế Redis cùng slot | Có giới hạn và có thể không được hỗ trợ |

**Nếu yêu cầu là một thao tác nhiều Set nguyên tử trên Redis Cluster, hãy thiết kế các key liên quan cùng slot ngay từ đầu.**

## 8. Tự tính giao/hợp/hiệu trong Java khi Set đủ nhỏ

Có những bài toán không thể đổi key layout: một Set chứa người dùng có giao dịch từ vùng A, Set khác chứa thành viên từ vùng B, mỗi Set thuộc một shard khác nhau. Nếu các Set **nhỏ, có giới hạn kích thước** và nghiệp vụ chấp nhận dữ liệu tại nhiều thời điểm, ứng dụng có thể đọc từng Set và tính tại Java.

Ví dụ dưới đây chỉ dành cho nhóm dữ liệu được giới hạn trước bởi kiến trúc:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SmallSetAggregationService {

    private final StringRedisTemplate redis;

    public SmallSetAggregationService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Set<String> intersectAcrossKeys(
            String firstKey,
            String secondKey
    ) {
        // Mỗi câu lệnh members() chỉ truy cập một Redis key,
        // nên driver cluster-aware có thể route từng key độc lập.
        Set<String> first = Objects.requireNonNull(
                redis.opsForSet().members(firstKey),
                "Expected direct result for first Set"
        );

        Set<String> second = Objects.requireNonNull(
                redis.opsForSet().members(secondKey),
                "Expected direct result for second Set"
        );

        Set<String> result = new HashSet<>(first);
        result.retainAll(second);
        return result;
    }

    public Set<String> unionAcrossKeys(
            String firstKey,
            String secondKey
    ) {
        Set<String> first = Objects.requireNonNull(
                redis.opsForSet().members(firstKey)
        );
        Set<String> second = Objects.requireNonNull(
                redis.opsForSet().members(secondKey)
        );

        Set<String> result = new HashSet<>(first);
        result.addAll(second);
        return result;
    }

    public Set<String> differenceAcrossKeys(
            String firstKey,
            String secondKey
    ) {
        Set<String> first = Objects.requireNonNull(
                redis.opsForSet().members(firstKey)
        );
        Set<String> second = Objects.requireNonNull(
                redis.opsForSet().members(secondKey)
        );

        Set<String> result = new HashSet<>(first);
        result.removeAll(second);
        return result;
    }
}
~~~

Ví dụ dùng `HashSet` để mô phỏng ngữ nghĩa tập hợp; thứ tự phần tử không được bảo đảm. `differenceAcrossKeys(A, B)` khác `differenceAcrossKeys(B, A)`.

Ở Redis, `SMEMBERS` trên key vắng mặt trả tập rỗng, nhưng Spring Data Redis cũng có thể trả `null` khi lệnh đang queue trong pipeline/transaction. Vì vậy đoạn code chủ động yêu cầu **kết quả trực tiếp**; không trộn các method này vào callback pipeline mà vẫn kỳ vọng Set được trả ngay.

Các giới hạn phải nêu rõ trước khi dùng cách này:

- **Chỉ dùng cho Set nhỏ, có giới hạn cứng từ thiết kế dữ liệu.** Không chờ đến sau `SMEMBERS` mới kiểm tra kích thước; khi đó dữ liệu lớn đã được tải vào heap.
- Hai lần đọc không phải snapshot atomically nhất quán.
- Không có tính nguyên tử để ghi kết quả về Redis như `SINTERSTORE` cùng slot.
- Tất cả các client phải dùng cùng serializer/encoding cho member thì phép `Set.contains` trong Java mới mang ý nghĩa giống phần tử Redis.
- Có thể cần timeout, rate limit, pagination hoặc một thiết kế truy vấn khác cho tập lớn.

Đây là **một lựa chọn ứng dụng**, không phải cách “bật cross-slot tự do” trên Redis server.

### 8.1. Khi tập lớn, đừng dùng `SMEMBERS` không giới hạn

`SMEMBERS` trả toàn bộ member. Với Set rất lớn, lựa chọn ứng dụng có thể là:

- Thiết kế lại key layout để phép tính quan trọng có thể chạy server-side trong một slot.
- Đọc tập nhỏ hơn rồi kiểm tra membership của các phần tử trong Set khác bằng các lệnh đơn khóa, nếu chi phí hợp lý.
- Dùng `SSCAN` để duyệt từng phần phục vụ tác vụ batch, đồng thời hiểu rằng SCAN không bảo đảm snapshot nhất quán dưới ghi đồng thời và có thể trả phần tử lặp.
- Xây dựng **materialized set/read model** từ event hoặc nguồn dữ liệu chuẩn, cập nhật theo luồng nghiệp vụ.
- Đưa truy vấn giao/hợp phức tạp trên dữ liệu lớn sang hệ thống có mô hình query/index thích hợp.

Nếu phải tính kết quả chính xác tuyệt đối trên dữ liệu thay đổi liên tục qua nhiều shard, chỉ đổi từ `SMEMBERS` sang `SSCAN` không giải quyết được yêu cầu nhất quán.

## 9. Đặc biệt cẩn thận với `*STORE` và `SMOVE` khác slot

### 9.1. Destination không phải một key phụ có thể bỏ qua

`SINTERSTORE`, `SUNIONSTORE`, `SDIFFSTORE` đọc các source set và ghi kết quả thành một destination set. Đích có thể được thay thế hoàn toàn bằng kết quả phép tính. Vì vậy ràng buộc slot phải tính **cả destination**.

Ví dụ đúng theo hash tag:

~~~redis
SADD group:{42}:active u1 u2 u3
SADD group:{42}:paid u2 u3

SINTERSTORE group:{42}:eligible group:{42}:active group:{42}:paid
SMEMBERS group:{42}:eligible
~~~

Nếu đổi đích thành `group:eligible:42`, không thể giả định Redis server thực hiện được lệnh trên cùng slot.

### 9.2. Tự mô phỏng STORE qua nhiều shard không còn nguyên tử

Một cách client-side có thể là:

~~~text
1. Đọc Set A từ shard A
2. Đọc Set B từ shard B
3. Tính A ∩ B tại Java
4. Xóa destination cũ
5. Ghi từng member vào destination mới
~~~

Cách này có các cửa sổ sai lệch:

- Có khoảng thời gian destination rỗng hoặc chỉ chứa một phần kết quả.
- Ứng dụng có thể chết sau khi xóa đích nhưng trước khi ghi đủ dữ liệu.
- Các source có thể thay đổi trong lúc tính.
- Client khác có thể nhìn thấy destination ở trạng thái trung gian.
- Retry cần idempotency và định nghĩa rõ phiên bản kết quả.

Khi đọc/ghi nhiều shard, không thể coi transaction Redis trên một shard là transaction phân tán. Nếu yêu cầu một snapshot được xuất bản nguyên tử **ở riêng destination slot**, có thể cân nhắc ghi một key version tạm trong cùng slot với destination rồi đổi con trỏ/đổi tên theo một cơ chế nguyên tử trong slot đó. Tuy nhiên, điều này **không tạo snapshot nguyên tử cho các source trên nhiều shard**; chỉ cải thiện cách công bố kết quả.

### 9.3. `SMOVE` là trường hợp thay đổi hai Set

~~~redis
SMOVE group:{42}:waiting group:{42}:active u7
~~~

Khi hai key cùng slot, Redis có thể thực hiện việc chuyển member như một command. Nếu source/destination khác slot, bạn không thể mặc định dùng một `SMOVE` server-side.

Tự làm:

~~~text
SREM source u7
SADD destination u7
~~~

là **hai lệnh độc lập**, có cửa sổ lỗi giữa chúng. Nếu `SREM` thành công rồi `SADD` thất bại, member có thể biến mất khỏi cả hai Set. Đổi thứ tự có thể làm member tạm thời xuất hiện trong cả hai Set. Nếu việc chuyển biểu diễn trạng thái nghiệp vụ phải chính xác, cần chọn nguồn dữ liệu có transaction phù hợp hoặc thiết kế bù trừ/reconciliation.

## 10. Pipeline, transaction và Lua cũng chịu quy tắc slot

### 10.1. Pipeline không hợp thức hóa một lệnh CROSSSLOT

Pipeline nhằm giảm chi phí round trip bằng cách gửi nhiều command mà không chờ từng response. Nó không làm Redis server sở hữu dữ liệu ở slot khác, và **không biến `SINTER A B` giữa hai slot thành lệnh Redis hợp lệ**.

Tài liệu Spring Data Redis về Redis Cluster còn nêu hạn chế riêng cho **cluster pipelining**: trong các phiên bản được tài liệu đề cập, hỗ trợ pipeline chủ yếu qua Lettuce, và các lệnh nhiều khóa cross-slot như `sMove`, `sInter`, `sInterStore`, `sUnion`, `sUnionStore`, `sDiff`, `sDiffStore` nằm trong danh sách không được hỗ trợ ở chế độ này. Do đó không thể suy từ việc một lời gọi bình thường có fallback client-side sang kết luận nó cũng hoạt động trong pipeline.

### 10.2. `MULTI/EXEC` không thể trải nhiều slot như transaction phân tán

Một transaction Redis Cluster có nhiều key cần các key phù hợp cùng hash slot.

Ví dụ ý tưởng:

~~~redis
MULTI
SADD group:{42}:active u7
SREM group:{42}:waiting u7
EXEC
~~~

Hai key cùng tag `42` là điều kiện cơ bản để mô hình transaction này có thể thực hiện tại Redis server sở hữu slot đó. Ngược lại, nếu key thứ hai thuộc slot khác, không thể xem `MULTI/EXEC` như một công cụ khắc phục `CROSSSLOT`.

Khi dùng Spring Data Redis `SessionCallback` hoặc Spring-managed transaction support, vẫn phải xét topology và ràng buộc slot. Thêm annotation `@Transactional` của Spring không tự tạo distributed transaction giữa nhiều primary Redis hoặc giữa Redis với database SQL.

### 10.3. Lua/EVAL cũng cần co-locate key

Lua script chạy trên Redis server và thường dùng khi một phép xử lý nhiều thao tác cần nguyên tử trong phạm vi server. Nhưng trong Cluster, script truy cập nhiều key vẫn phải tuân thủ yêu cầu slot.

Các key được script truy cập phải được khai báo đúng qua `KEYS`/tham số lệnh, và không dùng một script như cách lén truy cập những key ở shard khác. Hash tag có thể giúp nhóm các key cần thao tác trong cùng script.

Khi thao tác nhiều Set cùng slot đã có một Redis command phù hợp, thường nên ưu tiên command đó trước khi tạo Lua script phức tạp.

## 11. Redis Cluster có thể báo lỗi trong lúc resharding dù các key cùng slot

Có cùng hash tag là **điều kiện thiết kế cần thiết**, nhưng không phải cam kết bất kỳ lúc nào lệnh multi-key cũng thành công.

Redis Cluster có thể di chuyển slot giữa các primary khi rebalance/reshard. Trong giai đoạn migration:

- Lệnh một key có thể nhận chuyển hướng `MOVED` hoặc `ASK` để client đi đúng node.
- Với multi-key operation thuộc một slot đang chuyển, nếu một số key chưa tới node đích hoặc chưa tồn tại và Redis chưa thể bảo đảm xử lý toàn bộ tại một nơi, Redis có thể trả `TRYAGAIN`.
- Khi việc di chuyển slot kết thúc, thao tác nhiều key trong slot đó trở lại bình thường theo quy tắc cluster.

Do đó cần phân biệt:

| Lỗi/hiện tượng | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| `CROSSSLOT` | Các key trong một command không nằm cùng slot | Sửa key design hoặc cách thực thi |
| `MOVED` | Slot do node khác sở hữu | Cluster-aware driver cập nhật routing |
| `ASK` | Chuyển hướng tạm trong lúc migration | Driver xử lý theo cluster protocol |
| `TRYAGAIN` | Slot đang migrate và multi-key command chưa xử lý được ngay | Retry giới hạn, backoff phù hợp |
| Timeout/network error | Kết nối chậm, lỗi node hoặc tải lớn | Quan sát topology, timeout, retry và tình trạng cluster |

**Retry vô hạn không chữa được `CROSSSLOT`**, vì tên key vẫn băm vào các slot khác nhau. Còn `TRYAGAIN` trong resharding có thể là lỗi tạm thời cần chính sách retry giới hạn phù hợp.

## 12. Thiết kế Set cho những truy vấn điển hình

### Trường hợp A: Giao giữa các trạng thái của cùng một cửa hàng

Yêu cầu: người dùng phải vừa **active** vừa **paid** trong shop 42.

~~~text
shop:{42}:active
shop:{42}:paid
shop:{42}:eligible
~~~

Các Set thường được truy vấn cùng nhau, nên dùng tag theo shop. `SINTER` hoặc `SINTERSTORE` có thể chạy trên cùng slot. Đây là trường hợp hash tag đem lại lợi ích rõ ràng.

### Trường hợp B: Giao giữa hai nhóm toàn cục rất lớn

Yêu cầu: tìm ID thuộc cả nhóm marketing A và nhóm hội viên B trên toàn hệ thống.

Nếu cả hai Set đều rất lớn, pin tất cả key marketing toàn cầu vào một slot có thể gây hotspot. Thay vào đó, cân nhắc mô hình dữ liệu:

- Chia tập theo partition có chủ đích, tính kết quả trong từng partition rồi gộp.
- Duy trì index/materialized result ở một hệ thống thích hợp.
- Dùng nguồn dữ liệu chuẩn hỗ trợ query, hoặc kiến trúc stream/batch cho yêu cầu lớn.
- Xác định độ trễ và tính nhất quán mong muốn trước khi quyết định cách cập nhật kết quả.

Không có phép đặt tên key nào vừa cho một lệnh `SINTER` toàn cluster server-side, vừa phân tán tự do mọi source trên nhiều slot.

### Trường hợp C: Chuyển member giữa hai trạng thái

Yêu cầu: chuyển user từ `pending` sang `approved`.

~~~text
approval:{tenant-42}:pending
approval:{tenant-42}:approved
~~~

Dùng cùng tag để `SMOVE` có thể xử lý trong một command. Nếu đó là trạng thái nghiệp vụ quan trọng được lưu ở nhiều hệ thống, cần quyết định rõ nguồn chuẩn và cách đồng bộ khi lỗi.

### Trường hợp D: Quyền truy cập cần điều kiện chính xác

Nếu yêu cầu “user có cả role X và entitlement Y”, hãy xác định dữ liệu nào là nguồn chuẩn và lúc nào quyền có hiệu lực. Tính giao của các Set cache tại hai thời điểm khác nhau có thể tạo kết quả sai về bảo mật.

Có thể tổ chức Set theo user để các key liên quan ở cùng slot và xử lý thay đổi một cách có kiểm soát, hoặc đặt quyết định phân quyền tại hệ thống có consistency/transaction đáp ứng yêu cầu. Chỉ vì dùng Set không có nghĩa một tập dữ liệu eventual-consistent phù hợp cho mọi quyết định bảo mật.

## 13. Quy trình kiểm tra một truy vấn Set trước khi dùng Cluster

Giả sử service có lời gọi:

~~~java
Set<String> result = redis.opsForSet()
        .intersect(firstKey, secondKey);
~~~

Trước khi đưa vào đường chạy nhiều shard, thực hiện các bước suy luận:

1. **Đếm Redis key thật.** `intersect` dùng ít nhất hai key, còn `add(key, a, b, c)` chỉ dùng một.
2. **Xác định serializer của Redis key.** Slot phụ thuộc bytes key thật, không chỉ chuỗi Java.
3. **Xác định slot từng key.** Dùng `CLUSTER KEYSLOT` trong môi trường thử nghiệm.
4. **Nếu phải là một command nguyên tử server-side, đặt mọi key cùng slot.** Với `*STORE` nhớ tính cả đích.
5. **Đánh giá mức độ pin key.** Tag rộng đến mức nào, một slot có trở thành hotspot không?
6. **Nếu phải xử lý nhiều slot, xác định rõ ai tính kết quả.** Spring Data Redis, driver hay code ứng dụng? Operation/version/pipeline có hỗ trợ không?
7. **Đo kích thước Set và chi phí network/heap.** Fallback client-side có thể rất tốn kém.
8. **Nêu mức nhất quán.** Kết quả qua nhiều thao tác có được phép là eventual-consistent hay phải phản ánh một thời điểm duy nhất?
9. **Thiết kế lỗi và retry.** `CROSSSLOT` cần sửa cấu trúc, `TRYAGAIN` khi resharding có thể retry giới hạn, còn lỗi ghi nhiều bước cần reconciliation.

Có thể biểu diễn quyết định:

~~~mermaid
flowchart TD
    A["Cần thao tác nhiều Redis Set"] --> B{"Một key hay nhiều key?"}
    B -->|Một key| C["Dùng SADD/SREM/SISMEMBER/SMEMBERS..."]
    B -->|Nhiều key| D{"Mọi key cùng hash slot?"}
    D -->|Có| E["Ưu tiên command server-side như SINTER/SUNION/SMOVE"]
    D -->|Không| F{"Có thể sửa mô hình key theo đơn vị truy vấn?"}
    F -->|Có| G["Thiết kế hash tag phù hợp, cân nhắc hotspot"]
    F -->|Không| H{"Set nhỏ và chấp nhận không có snapshot toàn cục?"}
    H -->|Có| I["Client-side aggregation có giới hạn rõ"]
    H -->|Không| J["Partitioned read model / hệ thống truy vấn khác"]
~~~

## 14. Những hiểu lầm cần tránh

**“Hai key cùng node là đủ.”** Redis Cluster yêu cầu cùng **hash slot**, không đơn giản là cùng primary tại một thời điểm.

**“SADD nhiều member là lệnh nhiều khóa.”** `SADD key a b c` vẫn chỉ dùng một Redis key; khác với `SINTER keyA keyB`.

**“Thêm `redis-cli -c` hoặc Lettuce tự động giải quyết CROSSSLOT.”** Cluster-aware client xử lý routing và một số thao tác đặc thù, nhưng không biến mọi multi-key command thành atomic cross-shard operation.

**“Spring Data Redis không bao giờ xử lý được Set khác slot.”** Một số lời gọi có thể được tính ở client. Cần kiểm tra method/version/driver và chấp nhận chi phí, giới hạn, tính nhất quán khác với command server-side.

**“Vì `SINTER` chỉ trả vài phần tử nên fallback luôn rẻ.”** Để tìm vài phần tử giao nhau, ứng dụng có thể vẫn phải tải những Set nguồn rất lớn.

**“Chỉ các key nguồn cần cùng slot.”** Với `*STORE`, destination cũng là một key trong command; với `SMOVE`, cả source và destination cần cùng slot cho một lệnh server-side.

**“Đặt toàn bộ key vào `{global}` là cách tối ưu.”** Cách này tập trung tải vào một slot và làm mất lợi thế phân phối.

**“Pipeline hoặc MULTI/EXEC giải quyết hạn chế nhiều slot.”** Chúng có mục tiêu khác. Một Redis transaction hoặc script không phải distributed transaction cho nhiều primary.

**“Cùng tag thì không bao giờ lỗi.”** Resharding có thể gây `TRYAGAIN` tạm thời; hạ tầng còn có timeout và các lỗi kết nối khác.

## 15. Những nguyên tắc nên áp dụng trong Spring Data Redis

- **Thiết kế key theo thao tác thực tế:** biết Set nào cần giao/hợp/hiệu/chuyển phần tử cùng nhau.
- **Đặt hash tag vừa đủ hẹp:** co-locate nhóm cần atomic multi-key, giữ khả năng phân tán các nhóm không liên quan.
- **Dùng serializer tên key ổn định:** phần băm slot phụ thuộc bytes của key được gửi.
- **Kiểm tra `CLUSTER KEYSLOT`:** không suy đoán từ tên key hoặc node đang giữ slot.
- **Phân biệt Redis server command và Spring Data Redis client fallback:** nhất là ở cross-slot, pipeline và transaction.
- **Không bỏ qua destination của `*STORE` và `SMOVE`.**
- **Giới hạn aggregation phía Java:** chỉ dùng khi dữ liệu có kích thước kiểm soát và nghiệp vụ chấp nhận nhiều thời điểm đọc.
- **Không giả định atomicity toàn cluster:** thay đổi nhiều shard cần chiến lược về consistency, retry, idempotency và reconciliation.
- **Đo tải và theo dõi resharding:** CPU/RAM của slot nóng, thời gian truyền dữ liệu và các phản hồi `TRYAGAIN` đều có ý nghĩa vận hành.

Redis Cluster cho phép mở rộng keyspace bằng cách phân dữ liệu lên nhiều primary. Đổi lại, các lệnh Set **nhiều khóa** không còn tự do thao tác trên mọi key như khi dùng một Redis instance. Hiểu đúng **hash slot**, **hash tag**, **ranh giới server/client** và **tính nguyên tử** giúp bạn viết mã Spring Data Redis đúng với topology, thay vì chỉ phát hiện giới hạn sau khi ứng dụng chuyển sang Cluster.

## Tài liệu tham khảo

- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis — Multi-key operations](https://redis.io/docs/latest/develop/using-commands/multi-key-operations/)
- [Redis — CROSSSLOT error](https://redis.io/docs/latest/develop/reference/errors/common/crossslot/)
- [Redis — Scaling with Redis Cluster](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — SINTER](https://redis.io/docs/latest/commands/sinter/)
- [Redis — SUNION](https://redis.io/docs/latest/commands/sunion/)
- [Redis — SDIFF](https://redis.io/docs/latest/commands/sdiff/)
- [Redis — SMOVE](https://redis.io/docs/latest/commands/smove/)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis — Redis Repositories Running on a Cluster](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/cluster.html)
- [Spring Data Redis API — SetOperations](https://docs.spring.io/spring-data/redis/docs/3.3.x/api/org/springframework/data/redis/core/SetOperations.html)
