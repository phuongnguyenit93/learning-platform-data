# Dùng hash tag để định vị các khóa liên quan trong Cluster

## 1. Bài toán: các key liên quan có thể nằm trên những node khác nhau

Trong Redis standalone, một Redis Server xử lý các lệnh trên những key mà nó lưu. Khi triển khai **Redis Cluster**, không gian key được phân chia thành **16.384 hash slot** (đánh số từ 0 đến 16383). Mỗi slot được một primary node phụ trách tại một thời điểm; các node phân chia trách nhiệm xử lý dữ liệu theo các slot này.

Ví dụ, ứng dụng Spring Boot quản lý giỏ hàng có ba key:

~~~text
shop:cart:42:summary
shop:cart:42:items
shop:cart:42:coupon
~~~

Chúng đều thuộc giỏ hàng số 42 theo góc nhìn nghiệp vụ. Tuy nhiên, Redis Cluster **không nhóm chúng theo chuỗi tiền tố**. Thông thường, Cluster tính slot từ toàn bộ bytes của từng key. Vì tên key khác nhau, chúng có thể nằm ở các slot khác nhau và được phục vụ bởi các primary node khác nhau.

Điều đó không nhất thiết gây vấn đề cho từng lệnh độc lập như GET, SET hoặc HGET. Redis client có nhận biết Cluster, chẳng hạn Lettuce được cấu hình đúng qua Spring Data Redis, sẽ định tuyến từng key đến node tương ứng.

Vấn đề xuất hiện khi muốn thực hiện **một lệnh hoặc một thao tác nguyên tử bao gồm nhiều key**:

~~~text
MGET shop:cart:42:summary shop:cart:42:coupon
DEL shop:cart:42:summary shop:cart:42:coupon
~~~

Trong Redis Cluster, các thao tác nhiều key như trên nói chung đòi hỏi tất cả key thuộc **cùng một hash slot**. Nếu các key ở slot khác nhau, Redis có thể trả lỗi:

~~~text
CROSSSLOT Keys in request don't hash to the same slot
~~~

**Hash tag** là cú pháp đặt tên key để cố ý đưa các key có liên quan vào **cùng slot**, từ đó đáp ứng yêu cầu của những thao tác nhiều key trong Cluster.

## 2. Redis Cluster xác định slot của key như thế nào?

Redis Cluster sử dụng hàm CRC16 để tính slot. Với một key thông thường không chứa hash tag hợp lệ:

\[
\operatorname{slot}(\text{key})=\operatorname{CRC16}(\text{key})\bmod 16384
\]

Điểm cần hiểu là thuật toán áp dụng cho **bytes của tên key mà Redis thực sự nhận được**, không phải khái niệm “thuộc cùng một nhóm dữ liệu” trong chương trình Java.

Ví dụ:

~~~text
shop:cart:42:summary
shop:cart:42:items
shop:cart:42:coupon
~~~

Ba key có nhiều phần ký tự chung, nhưng slot được tính từ ba tên key khác nhau. Không có bảo đảm chúng cùng slot.

### Hash tag thay đổi phần nào của key được đưa vào phép hash

Nếu tên key chứa một cặp ngoặc nhọn hợp lệ với nội dung không rỗng, Redis chỉ dùng **phần nằm giữa cặp ngoặc nhọn đó** để tính slot.

~~~text
shop:cart:{42}:summary
shop:cart:{42}:items
shop:cart:{42}:coupon
~~~

Trong cả ba key, Redis tính slot từ chuỗi:

~~~text
42
~~~

Do đó:

\[
\operatorname{slot}(\text{shop:cart:\{42\}:summary})
=\operatorname{slot}(\text{shop:cart:\{42\}:items})
=\operatorname{slot}(\text{shop:cart:\{42\}:coupon})
=\operatorname{CRC16}(\text{42})\bmod 16384
\]

Các key vẫn có **tên đầy đủ riêng biệt**. Ngoặc nhọn chỉ ảnh hưởng cách xác định slot; chúng không làm key biến thành một Hash, không rút ngắn tên key và không tự tạo quan hệ khóa ngoại.

~~~mermaid
flowchart TD
    A["shop:cart:{42}:summary"] --> D["Hash tag: 42"]
    B["shop:cart:{42}:items"] --> D
    C["shop:cart:{42}:coupon"] --> D
    D --> E["CRC16(42) mod 16384"]
    E --> F["Cùng một hash slot"]
    F --> G["Primary node đang sở hữu slot đó"]
~~~

**Cùng hash tag hợp lệ bảo đảm cùng slot** trong Redis Cluster. Điều ngược lại không nhất thiết đúng: hai tag khác nhau vẫn có thể ngẫu nhiên rơi vào cùng một slot vì chỉ có 16.384 slot. Đừng dựa vào va chạm slot tình cờ để thiết kế hệ thống.

## 3. Cú pháp hash tag: phần nào thực sự được hash?

Trong tên key, ký tự **{** và **}** là ký tự bình thường được Redis nhận diện để chọn hash tag. Quy tắc Redis sử dụng về cơ bản là:

1. Tìm **dấu { đầu tiên** trong tên key.
2. Tìm **dấu } đầu tiên** xuất hiện sau dấu { đó.
3. Nếu giữa hai dấu có ít nhất một byte, dùng phần bên trong để tính slot.
4. Nếu không tìm được cặp phù hợp hoặc phần giữa rỗng, hash **toàn bộ tên key**.

Ví dụ:

| Tên key | Phần dùng để tính slot | Giải thích |
| --- | --- | --- |
| **cart:{42}:items** | **42** | Tag hợp lệ. |
| **cart:{42}:summary** | **42** | Cùng slot với key trên. |
| **orders:{tenant7:user42}:list** | **tenant7:user42** | Tag có thể chứa dấu hai chấm. |
| **{cart42}:status** | **cart42** | Tag có thể đứng ngay đầu key. |
| **cart:42:items** | Toàn bộ key | Không có tag. |
| **cart:{}:items** | Toàn bộ key | Tag rỗng nên không có hiệu lực. |
| **cart:{42:items** | Toàn bộ key | Không có dấu đóng }. |
| **cart:{42}:items:{99}** | **42** | Cặp ngoặc hợp lệ đầu tiên được dùng. |
| **cart:{}:{42}:items** | Toàn bộ key | Cặp đầu tiên rỗng; Redis không tự chuyển sang cặp sau. |

**Một số lưu ý về đặt tên:**

- Dấu ngoặc nhọn là thành phần của **key**, còn phần được hash là **nội dung bên trong**.
- Không ghép nhiều tag để mong Redis hash kết hợp chúng; hãy tạo **một tag duy nhất** chứa đầy đủ định danh nhóm.
- Không để dữ liệu đầu vào tùy ý chứa **{** hoặc **}** khi xây dựng tag từ ID do người dùng cung cấp. Các ký tự này có thể thay đổi phần thực tế được hash.
- Hash tag **không phải Redis Hash**. Một key String có tên chứa {42} vẫn có TYPE là string; một key Hash cùng tag vẫn có TYPE là hash.

## 4. Thiết kế key: chọn nhóm nào cần ở cùng một slot?

Giả sử một giỏ hàng được biểu diễn bằng nhiều key để phục vụ những thao tác khác nhau:

~~~text
cart:{tenant:t7:cart:c42}:meta
cart:{tenant:t7:cart:c42}:items
cart:{tenant:t7:cart:c42}:discount
cart:{tenant:t7:cart:c42}:version
~~~

Tag chung là:

~~~text
tenant:t7:cart:c42
~~~

Toàn bộ key của **cùng giỏ hàng** được gán vào một slot, trong khi giỏ hàng khác sẽ có tag khác:

~~~text
cart:{tenant:t7:cart:c43}:meta
cart:{tenant:t7:cart:c43}:items
~~~

Mỗi giỏ hàng có cơ hội được phân phối sang slot khác, giúp Redis Cluster vẫn chia tải giữa các node.

### Định vị theo aggregate thay vì theo toàn bộ hệ thống

Một cách chọn tag thường hợp lý là **ranh giới dữ liệu cần xử lý chung** (aggregate):

| Nghiệp vụ | Nhóm key cùng tag | Tag gợi ý |
| --- | --- | --- |
| Giỏ hàng | meta, items, voucher, version của cùng một cart | **{tenant:t7:cart:c42}** |
| Đơn hàng | summary, status, audit ngắn hạn của cùng order | **{tenant:t7:order:o81}** |
| Quy trình thanh toán | state, idempotency marker, retry counter cùng một workflow | **{tenant:t7:payment:p19}** |
| Hồ sơ người dùng | profile cache và preference cache phải đọc chung | **{tenant:t7:user:u17}** |

Các mẫu này chỉ hữu ích nếu bài toán thật sự yêu cầu thao tác nhiều key cùng lúc hoặc cần chắc chắn đặt key chung slot. Nếu mỗi key luôn được xử lý độc lập, không cần thêm hash tag chỉ vì chúng cùng thuộc một module.

### Vì sao không dùng tag quá rộng?

Đây là hai thiết kế khác nhau:

~~~text
# Tag quá rộng: tất cả giỏ hàng của tenant t7 vào một slot
cart:{tenant:t7}:c42:meta
cart:{tenant:t7}:c43:meta
cart:{tenant:t7}:c44:meta

# Tag theo từng cart: nhiều giỏ hàng có thể phân tán giữa các slot
cart:{tenant:t7:cart:c42}:meta
cart:{tenant:t7:cart:c43}:meta
cart:{tenant:t7:cart:c44}:meta
~~~

Với mẫu thứ nhất, tất cả key của tenant t7 có cùng tag **tenant:t7**, nên bắt buộc vào cùng slot. Nếu tenant đó có lượng truy cập lớn, một primary node có thể chịu phần lớn tải dù Cluster có nhiều node. Đây là một dạng **hot slot**.

Mẫu thứ hai phân bố theo cart ID; nó phù hợp hơn khi thao tác nguyên tử chỉ cần nằm trong phạm vi mỗi giỏ hàng. Càng nhiều nhóm độc lập, Cluster càng có cơ hội trải các key lên nhiều slot.

**Nguyên tắc:** chọn tag **nhỏ nhất vẫn bao trùm những key bắt buộc phải cùng slot**. Không đồng nhất hash tag với toàn tenant, toàn bảng, toàn cache hay toàn ứng dụng nếu không có yêu cầu cụ thể.

### Tránh va chạm ý nghĩa giữa các hệ thống

Ví dụ hai nhóm key dùng tag **{42}**:

~~~text
shop:cart:{42}:items
shop:order:{42}:status
~~~

Hai key này cũng cùng slot dù chúng thuộc hai aggregate khác nhau. Không phải lỗi chức năng, nhưng có thể khiến phân phối tải và phân quyền vận hành khó dự đoán.

Ưu tiên tag có đầy đủ định danh ngữ cảnh khi các namespace khác nhau có thể dùng trùng ID:

~~~text
shop:cart:{tenant:t7:cart:42}:items
shop:order:{tenant:t7:order:42}:status
~~~

Tên key ngoài tag vẫn có thể dùng để tổ chức namespace, còn tag chứa chính xác **ranh giới cần định vị**.

## 5. Kiểm chứng slot bằng redis-cli

Để kiểm tra thiết kế, kết nối tới **Redis Cluster thật** bằng redis-cli. Ví dụ môi trường học có node ở cổng 7000:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000
~~~

Tùy chọn **-c** cho phép redis-cli tự xử lý các phản hồi chuyển hướng phổ biến như MOVED/ASK khi gửi lệnh đơn key tới Cluster. Nó **không làm một lệnh nhiều key ở các slot khác nhau trở nên hợp lệ**.

Trong redis-cli, sử dụng **CLUSTER KEYSLOT**:

~~~text
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:meta
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:items
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:discount
CLUSTER KEYSLOT cart:{tenant:t7:cart:c43}:items
~~~

Ba lệnh đầu sẽ trả **cùng một số slot**. Lệnh cuối dùng tag khác nên **không được bảo đảm** có cùng slot. Không cần biết trước số slot cụ thể: điều đáng kiểm tra là các key cần xử lý chung có kết quả giống nhau.

Bạn cũng có thể thử hai key không dùng tag:

~~~text
CLUSTER KEYSLOT cart:c42:meta
CLUSTER KEYSLOT cart:c42:items
~~~

Không nên giả định hai kết quả giống nhau chỉ vì cùng tiền tố **cart:c42:**.

**Giới hạn:** lệnh CLUSTER KEYSLOT hoạt động trong ngữ cảnh Redis Cluster. Trên Redis standalone không bật Cluster, lệnh nhóm CLUSTER có thể trả lỗi về việc hỗ trợ Cluster bị tắt. Việc kết nối tới một Redis standalone không xác nhận được hành vi multi-node.

### Thực hành lệnh nhiều key cùng slot

Trong Cluster đang hoạt động:

~~~text
MSET cart:{tenant:t7:cart:c42}:summary "2 items" cart:{tenant:t7:cart:c42}:coupon "WELCOME"
MGET cart:{tenant:t7:cart:c42}:summary cart:{tenant:t7:cart:c42}:coupon
DEL cart:{tenant:t7:cart:c42}:summary cart:{tenant:t7:cart:c42}:coupon
~~~

Hai key đều có tag **tenant:t7:cart:c42**, vì vậy chúng cùng slot. MSET và MGET trên hai String key có thể thực thi tại primary node phụ trách slot đó. DEL cũng xử lý được cả hai key trong cùng lệnh.

Nếu dùng hai key thuộc **slot khác nhau**:

~~~text
MGET cart:{tenant:t7:cart:c42}:summary cart:{tenant:t7:cart:c43}:summary
~~~

Lệnh trên không đáp ứng điều kiện cùng slot khi hai tag hash về các slot khác nhau; Redis Cluster sẽ trả **CROSSSLOT**. Điều này đúng dù đã bật -c ở redis-cli.

**Lưu ý:** MGET chỉ đọc được dữ liệu String. Nếu key lưu Hash, dùng các lệnh HGET hoặc HGETALL phù hợp. Hash tag không thay đổi kiểu dữ liệu của key.

## 6. Hash tag liên quan tới những lệnh nào?

Redis Cluster có thể xử lý các lệnh **một key** ở nhiều node bằng cơ chế định tuyến. Hash tag đặc biệt quan trọng với nhóm lệnh hoặc cấu trúc thực thi cần **nhiều key trên cùng một node/slot**.

| Tình huống | Ví dụ | Vai trò của hash tag |
| --- | --- | --- |
| Đọc một String | GET key | Không cần các key khác cùng slot. |
| Cập nhật một Hash | HSET key field value | Chỉ tác động một Redis key. |
| Đọc nhiều String bằng một lệnh | MGET key1 key2 | Các key phải cùng slot trong Cluster. |
| Ghi nhiều String bằng một lệnh | MSET key1 value1 key2 value2 | Các key phải cùng slot. |
| Xóa nhiều key cùng một lệnh | DEL key1 key2 | Cần cùng slot. |
| Di chuyển/đổi tên giữa hai key | RENAME source destination | Hai key phải cùng slot trong Cluster. |
| Giao dịch trên nhiều key | MULTI / EXEC với các thao tác liên quan | Tập key phải phù hợp ràng buộc cùng slot/định tuyến. |
| Lua script thao tác nhiều key | EVAL với KEYS[1], KEYS[2] | Những key tham gia phải cùng slot theo quy tắc Cluster. |
| Pipeline chứa nhiều key độc lập | Nhiều GET/SET | Client có thể phải chia/định tuyến theo node; hash tag không phải yêu cầu chung của mọi pipeline. |

### Lệnh nhiều key khác gì nhiều lệnh một key?

Hai đoạn sau không tương đương về tính nguyên tử:

~~~text
MSET cart:{c42}:summary ready cart:{c42}:coupon applied
~~~

và:

~~~text
SET cart:{c42}:summary ready
SET cart:{c42}:coupon applied
~~~

MSET được thực thi như một lệnh nhiều key trên một node khi các key ở cùng slot. Hai SET riêng lẻ vẫn là **hai thao tác**, dù key có cùng slot. Có thể xảy ra lỗi hoặc kết nối bị ngắt giữa hai lần SET; hash tag **không tự tạo transaction**.

Hash tag giải quyết **vị trí của key**, còn tính nguyên tử phụ thuộc **lệnh cụ thể**, giao dịch hoặc script được dùng.

### Redis transaction

Redis transaction sử dụng MULTI/EXEC để thực thi nhóm lệnh, nhưng trong Cluster không thể tự động mở rộng thành giao dịch phân tán giữa những slot khác nhau:

~~~text
MULTI
SET cart:{c42}:state ready
SET cart:{c42}:version 2
EXEC
~~~

Hai key dùng cùng tag nên phù hợp điều kiện định tuyến. Tuy nhiên, MULTI/EXEC không có cơ chế rollback như giao dịch database quan hệ khi một lệnh thực thi báo lỗi. Hơn nữa, mọi yêu cầu nhất quán giữa Redis và một database khác vẫn phải được xử lý ở mức kiến trúc ứng dụng.

### Lua script

Một Lua script có thể nhận tên các key qua danh sách **KEYS**:

~~~lua
-- KEYS[1]: cart:{c42}:state
-- KEYS[2]: cart:{c42}:version
-- ARGV[1]: trạng thái mới
redis.call('SET', KEYS[1], ARGV[1])
return redis.call('INCR', KEYS[2])
~~~

Trong Redis Cluster, các key mà script thực sự truy cập phải được định tuyến đúng và nằm ở cùng slot. Tên key được truyền rõ qua **KEYS**, thay vì tạo thêm tên key tùy tiện bên trong script; điều này giúp client/Cluster xác định đúng nơi thực thi.

Đặt **{c42}** trong tên key không tự chứng minh script an toàn: còn phải xét tính đúng đắn của thuật toán, quyền truy cập, lỗi dữ liệu, thời gian thực thi và ngữ nghĩa retry.

## 7. Tích hợp trong Spring Data Redis

Spring Data Redis không yêu cầu API đặc biệt để “bật hash tag”. **Hash tag là một phần của tên key**, được Redis Cluster nhận biết ở phía server. Nhiệm vụ của ứng dụng là tạo key nhất quán và dùng Redis client có khả năng định tuyến tới Cluster.

### 7.1. Cấu hình Spring Boot kết nối Redis Cluster

Ví dụ ứng dụng Spring Boot 3.x dùng starter và Redis Cluster đã tồn tại:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

~~~yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:7000
          - 127.0.0.1:7001
          - 127.0.0.1:7002
        max-redirects: 3
      connect-timeout: 2s
      timeout: 3s
~~~

Các host/port chỉ minh họa các node seed dùng để khám phá Cluster; chúng phải được thay bằng địa chỉ phù hợp với topology thực tế. Redis Cluster cần được khởi tạo, có phân bổ slot và các node có thể liên lạc qua mạng. Chỉ thêm ba host vào YAML không biến ba Redis standalone thành Cluster.

Nếu hệ thống yêu cầu ACL, TLS, username/password hoặc cấu hình client riêng, hãy bổ sung các thuộc tính phù hợp với môi trường. Không đưa secrets thật vào tài liệu hoặc Git.

Với cấu hình starter thông thường, Spring Boot có thể tạo **LettuceConnectionFactory**, **RedisTemplate** và **StringRedisTemplate**. Ở đây dùng StringRedisTemplate để tên key hiển thị đúng như chuỗi trong redis-cli.

### 7.2. Xây dựng nhóm key theo cùng một tag

Ví dụ service lưu hai String key của một giỏ hàng. Để tránh phát sinh tag sai cú pháp, phần định danh trong ví dụ được giới hạn ở các ký tự đơn giản:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartClusterStore {

    private final StringRedisTemplate redis;

    public CartClusterStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static String tag(String tenantId, String cartId) {
        requireSafeId(tenantId);
        requireSafeId(cartId);
        return "{tenant:" + tenantId + ":cart:" + cartId + "}";
    }

    private static void requireSafeId(String value) {
        if (value == null || !value.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid key identifier");
        }
    }

    private static String summaryKey(String tag) {
        return "cart:" + tag + ":summary";
    }

    private static String couponKey(String tag) {
        return "cart:" + tag + ":coupon";
    }

    public void save(String tenantId, String cartId,
                     String summary, String coupon) {
        String group = tag(tenantId, cartId);
        redis.opsForValue().multiSet(Map.of(
                summaryKey(group), summary,
                couponKey(group), coupon
        ));
    }

    public List<String> read(String tenantId, String cartId) {
        String group = tag(tenantId, cartId);
        return redis.opsForValue().multiGet(List.of(
                summaryKey(group),
                couponKey(group)
        ));
    }
}
~~~

Khi gọi:

~~~java
store.save("t7", "c42", "2 items", "WELCOME");
List<String> values = store.read("t7", "c42");
~~~

Hai tên key được tạo ra là:

~~~text
cart:{tenant:t7:cart:c42}:summary
cart:{tenant:t7:cart:c42}:coupon
~~~

**multiSet** tương ứng thao tác ghi nhiều String (MSET) và **multiGet** đọc nhiều String (MGET). Tên key có cùng nội dung trong cặp ngoặc nhọn nên hai lệnh nhiều key có thể được định tuyến đến một slot.

Đoạn mã là ví dụ ở tầng truy cập Redis. Trong dự án thực, cần xác định liệu **summary**, **coupon** có giá trị null không, định dạng có cần serialize phức tạp không, cách xử lý cache miss và exception, cùng việc dữ liệu cập nhật có cần transaction nghiệp vụ với database hay không.

**MSET không đặt TTL cho từng key.** Nếu cần cả hai key hết hạn đồng thời, đừng mặc định gọi MSET xong hai EXPIRE riêng sẽ tạo một thao tác nguyên tử. Có thể sử dụng lệnh/script phù hợp với yêu cầu, hoặc chọn một cấu trúc Redis duy nhất như Hash để quản lý TTL chung của một key.

### 7.3. Thao tác một key vẫn bình thường

Nếu chỉ cần đọc một Hash của giỏ hàng:

~~~java
String key = "cart:{tenant:t7:cart:c42}:items";
Map<Object, Object> fields = redis.opsForHash().entries(key);
~~~

Một key Hash có nhiều field **đã nằm trọn trong một slot** vì toàn bộ field thuộc cùng một key Redis. Không cần tạo thêm từng key cho mỗi field chỉ để chúng cùng vị trí.

Trong thiết kế dữ liệu, nên so sánh hai hướng:

- **Một Hash duy nhất:** tất cả field cùng một key, TTL theo key, dễ truy xuất field; không cần phối hợp nhiều key cho các field đơn giản.
- **Nhiều key với chung hash tag:** cho phép TTL riêng, kiểu dữ liệu riêng hoặc truy cập khác nhau; cần quản lý cách cập nhật nhiều key và ràng buộc Cluster.

Không có lựa chọn nào luôn tốt hơn; phụ thuộc vào kiểu dữ liệu, TTL, tần suất cập nhật và nhu cầu multi-key.

### 7.4. Lua script từ Spring Data Redis

Spring Data Redis cho phép thực thi **RedisScript** thông qua RedisTemplate. Khi script nhận nhiều key trong Redis Cluster, tất cả key tham gia phải được thiết kế ở cùng slot:

~~~java
import java.util.List;
import org.springframework.data.redis.core.script.DefaultRedisScript;

DefaultRedisScript<Long> incrementIfPresent = new DefaultRedisScript<>(
        "if redis.call('EXISTS', KEYS[1]) == 0 then return 0 end "
        + "return redis.call('INCR', KEYS[2])",
        Long.class
);

Long result = redis.execute(
        incrementIfPresent,
        List.of(
                "cart:{tenant:t7:cart:c42}:state",
                "cart:{tenant:t7:cart:c42}:counter"
        )
);
~~~

Ví dụ trên chỉ minh họa **cách truyền hai key cùng slot** cho một script. Nó không đặt ra quy tắc nghiệp vụ hoàn chỉnh về điều kiện tăng bộ đếm. Khi triển khai thật, bảo đảm serializer, loại dữ liệu String, cách xử lý lỗi và tên key được truyền đúng qua **KEYS**.

### 7.5. Redis Cache abstraction và tiền tố khóa

Khi dùng Spring Cache với Redis, key trên server thường được xây từ **tên cache**, separator/prefix và kết quả tính cache key. Ví dụ một dạng phổ biến là:

~~~text
cartSummaries::42
~~~

Nếu muốn key của hai cache cùng một cart nằm trên một slot, có thể thiết kế phần key được sinh ra chứa cùng hash tag:

~~~java
@Cacheable(
    cacheNames = "cartSummaries",
    key = "'{tenant:' + #p0 + ':cart:' + #p1 + '}'"
)
public String getSummary(String tenantId, String cartId) {
    return loadSummary(tenantId, cartId);
}
~~~

Với **tenantId = t7**, **cartId = c42** và prefix cache mặc định kiểu **cartSummaries::**, key có thể có dạng:

~~~text
cartSummaries::{tenant:t7:cart:c42}
~~~

Nội dung tag vẫn là **tenant:t7:cart:c42**, vì vậy nó sẽ cùng slot với:

~~~text
cart:{tenant:t7:cart:c42}:items
~~~

Tuy nhiên, **cấu hình RedisCacheManager, prefix, key serializer và KeyGenerator tùy chỉnh có thể thay đổi bytes của key thực tế**. Không chỉ nhìn annotation rồi khẳng định key trên Redis. Nên kiểm tra tên key bằng redis-cli hoặc lớp quan sát được phép sử dụng trên môi trường thử nghiệm.

Ngoài ra, việc hai cache key cùng slot **không có nghĩa hai method @Cacheable tự thực hiện một thao tác nguyên tử**. Tính nguyên tử phải được thiết kế ở nơi thao tác thật sự chạy.

## 8. Hash tag không thay thế serialization, key prefix hay định tuyến client

### 8.1. Serialization quyết định bytes gửi tới Cluster

Spring Data Redis có thể dùng các serializer khác nhau cho key/value. Ví dụ StringRedisTemplate thường dùng String serializer; một RedisTemplate tổng quát có thể dùng serializer khác.

Nếu key được mã hóa thành dữ liệu nhị phân, chuỗi hiển thị trong Java chưa chắc giống bytes mà Redis nhận. Điều này ảnh hưởng cả việc **đọc key bằng redis-cli** lẫn **phần nằm trong ngoặc nhọn mà Cluster nhận diện**.

Để hash tag có hành vi dự đoán được:

1. Quy định một cách xây dựng key thống nhất giữa các service.
2. Dùng serializer cho key giữ nguyên cú pháp tag theo thiết kế, ví dụ StringRedisSerializer khi phù hợp.
3. Tránh trộn các serializer key không tương thích khi hai service cùng truy cập một tập key.
4. Kiểm chứng bằng **CLUSTER KEYSLOT** trên **key thực sự được ghi** chứ không chỉ trên chuỗi tưởng tượng.

### 8.2. Prefix không phải hash tag

Hai key có chung prefix:

~~~text
shop:cart:42:summary
shop:cart:42:items
~~~

không được Cluster bảo đảm cùng slot. Chỉ khi chúng dùng **cùng tag hợp lệ**:

~~~text
shop:cart:{42}:summary
shop:cart:{42}:items
~~~

Redis mới cố ý hash cùng một phần tên. Prefix chủ yếu để tổ chức namespace, tìm kiếm key hoặc quy ước vận hành; nó không đồng nghĩa việc định vị.

### 8.3. Client cluster-aware vẫn cần thiết

Client Redis thông thường có thể không hiểu cách xử lý MOVED/ASK, discovery của Cluster hoặc định tuyến multi-key. Với Spring Data Redis, cần cấu hình Lettuce/Jedis và RedisConnectionFactory phù hợp Redis Cluster.

Hash tag chỉ giúp Redis xác định **key nào cùng slot**. Nó không biến kết nối tới một node đơn lẻ thành cluster-aware client và không khắc phục mọi lỗi liên quan topology, ACL, TLS, timeout hoặc network.

## 9. Những giới hạn khi gom nhiều key vào cùng slot

### 9.1. Hot slot và mất cân bằng tải

Một tag quá phổ biến khiến tất cả key mang tag đó tập trung vào cùng slot và cùng primary node sở hữu slot. Ví dụ:

~~~text
cache:{global}:product:1
cache:{global}:product:2
cache:{global}:product:3
...
~~~

Thiết kế này đưa **toàn bộ cache** vào một slot. Cluster có thể vẫn có nhiều node, nhưng phần dữ liệu này không tận dụng được việc phân chia slot.

Một cách khác là phân nhóm theo sản phẩm hoặc theo aggregate cần xử lý chung:

~~~text
cache:{product:1}:detail
cache:{product:1}:price
cache:{product:2}:detail
cache:{product:2}:price
~~~

Mỗi nhóm sản phẩm có thể nằm ở một slot khác, còn các key của cùng sản phẩm vẫn chung slot.

### 9.2. Phân tán dữ liệu và nhu cầu atomic phải được cân bằng

Đôi khi một nghiệp vụ cần thao tác trên **nhiều aggregate** trong cùng một transaction, ví dụ chuyển điểm giữa hai tài khoản bất kỳ. Nếu mỗi account dùng tag riêng để phân phối tải, hai account thường không ở cùng slot, nên không thể giả định Lua script/MULTI xử lý cả hai trực tiếp như trong standalone.

Không nên giải quyết bằng cách đặt **mọi tài khoản** vào một tag global: hiệu quả phân tán sẽ suy giảm và có nguy cơ hot slot.

Khi nghiệp vụ vượt qua ranh giới slot, cân nhắc:

- Thiết kế lại aggregate để thao tác quan trọng chỉ cần một key/slot.
- Dùng một nguồn dữ liệu hoặc hệ thống transaction phù hợp làm nơi bảo đảm nhất quán chính.
- Phối hợp nhiều thao tác theo workflow có trạng thái, idempotency, retry và cơ chế xử lý lỗi rõ ràng.

Hash tag là công cụ **định vị dữ liệu**, không phải giải pháp transaction phân tán.

### 9.3. Slot có thể chuyển node khi Cluster thay đổi

Một key luôn được hash tới cùng **số slot** theo quy tắc hiện hành nếu bytes tên key không đổi; tuy nhiên **node sở hữu slot có thể thay đổi** khi Cluster reshard hoặc failover. Vì vậy không nên hard-code IP của node dựa trên hash tag.

Ứng dụng phải dùng client hỗ trợ cập nhật topology và xử lý chuyển hướng. Việc các key cùng slot có nghĩa chúng cùng được điều phối qua **một slot**, không bảo đảm chúng nằm vĩnh viễn trên cùng một máy vật lý.

### 9.4. Đừng nhầm colocate với dữ liệu nhất quán

Hai key cùng slot có thể được cập nhật bằng hai lệnh đơn lẻ và lệch nhau trong một khoảng thời gian. Khi sửa key nguồn, cache có thể vẫn chứa giá trị cũ. Khi script có lỗi nghiệp vụ, hash tag không sửa được dữ liệu. Cần thiết kế rõ:

- Lệnh nào phải chạy nguyên tử?
- Các key cần TTL giống hay khác nhau?
- Khi một yêu cầu retry, thao tác có thể bị thực hiện lặp không?
- Nếu kết nối lỗi giữa các lệnh thì phục hồi thế nào?
- Dữ liệu nào là nguồn sự thật khi Redis và database không đồng bộ?

Những câu hỏi này vẫn cần trả lời dù Redis Cluster đã định vị các key cùng slot.

## 10. Cách thay đổi thiết kế key trên hệ thống đã có dữ liệu

Thêm hoặc sửa hash tag **làm thay đổi tên key**, và thường làm thay đổi slot. Ví dụ:

~~~text
cart:42:summary
cart:{42}:summary
~~~

Đây là **hai key khác nhau** đối với Redis. Không có thao tác “đổi cách hash nhưng giữ nguyên tên key”: muốn chuyển sang tên có tag mới, ứng dụng cần có kế hoạch di chuyển hoặc dựng lại dữ liệu.

Một quy trình chuyển đổi hợp lý:

1. **Xác định tập key** sẽ thay đổi và thời hạn tồn tại của chúng.
2. **Chọn tag ổn định** theo aggregate và đảm bảo mọi service tạo key giống nhau.
3. **Xác định nguồn sự thật**: cache có thể xóa để tái tạo hay đây là trạng thái không thể mất?
4. **Chuẩn bị đường đọc/ghi tương thích** khi cần triển khai nhiều phiên bản ứng dụng đồng thời.
5. **Di chuyển hoặc tái tạo dữ liệu** bằng cơ chế có kiểm soát; đừng giả định RENAME giữa hai slot khác nhau thực hiện được trực tiếp.
6. **Quan sát hiệu quả**: số lượng key theo slot, phân bố tải, lỗi CROSSSLOT, độ trễ và hit/miss của cache.
7. **Dọn key cũ** theo TTL hoặc kế hoạch riêng sau khi bảo đảm ứng dụng không còn phụ thuộc.

Với cache có thể tái tạo, nhiều khi đổi sang key mới và để key cũ tự hết hạn đơn giản hơn di chuyển. Với dữ liệu phiên hoặc trạng thái giao dịch không thể mất, cần quy trình migration và kiểm chứng riêng.

## 11. Các lỗi thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| **CROSSSLOT** khi MGET/MSET/DEL | Các key không cùng hash slot | Dùng CLUSTER KEYSLOT cho từng tên key thực tế. |
| Đã thêm dấu ngoặc nhưng vẫn CROSSSLOT | Tag không giống nhau, rỗng, sai vị trí, có cặp ngoặc trước đó | Kiểm tra chính xác bytes/tên key và cú pháp cặp ngoặc đầu tiên. |
| GET từng key thành công nhưng multiGet lỗi | Mỗi lệnh một key có thể định tuyến riêng; nhiều key phải cùng slot | So sánh các slot; dùng multiGet chỉ khi cùng slot. |
| redis-cli trả MOVED | Gửi lệnh đến node không sở hữu slot | Dùng redis-cli -c và client cluster-aware. |
| CLUSTER KEYSLOT báo Cluster disabled | Redis server hiện tại không chạy Cluster | Kết nối Redis Cluster thật. |
| Key xuất hiện dưới dạng ký tự lạ | Key serializer dùng bytes/định dạng khác | Kiểm tra StringRedisSerializer và bytes thực tế. |
| Tất cả key của tenant đổ vào một node | Tag chỉ chứa tenant ID, tạo hot slot | Cân nhắc tag theo aggregate nhỏ hơn. |
| @Cacheable không có hành vi như mong đợi | Prefix/KeyGenerator tạo key khác dự kiến | Xem cấu hình cache và key thực tế. |
| Giao dịch nhiều key vẫn lỗi | Cùng tên prefix nhưng khác slot | Kiểm tra slot và phạm vi của transaction/script. |
| Dùng tag đúng nhưng dữ liệu vẫn cũ | Không thiết kế invalidation/TTL | Kiểm tra đường cập nhật và vòng đời cache. |

### Quy trình debug ngắn bằng redis-cli

Giả sử lệnh Spring Data Redis trên hai key bị CROSSSLOT:

~~~text
cart:{tenant:t7:cart:c42}:state
cart:{tenant:t7:cart:c43}:version
~~~

Kiểm tra lần lượt:

~~~text
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:state
CLUSTER KEYSLOT cart:{tenant:t7:cart:c43}:version
~~~

Hai tag biểu diễn **hai giỏ hàng khác nhau**, nên không được bảo đảm cùng slot. Nếu ý định nghiệp vụ thực sự là đọc **state** và **version của cùng một cart**, phải sửa cách tạo key cho chúng dùng cùng cart ID, ví dụ:

~~~text
cart:{tenant:t7:cart:c42}:state
cart:{tenant:t7:cart:c42}:version
~~~

Khi đó mới có lý do dùng multi-key operation. Không đổi tag theo kiểu ép hai aggregate khác nhau về một nhóm nếu không phù hợp với yêu cầu.

## 12. Bài thực hành: thiết kế key cho một giỏ hàng trong Cluster

Giả sử ứng dụng có các dữ liệu sau:

| Thông tin | Kiểu Redis | Mục đích |
| --- | --- | --- |
| Tóm tắt giỏ hàng | String | Trả nhanh một bản tóm tắt. |
| Danh sách mặt hàng | Hash | Mã hàng thành số lượng. |
| Mã khuyến mãi | String | Lưu coupon hiện tại. |
| Số phiên bản | String dạng số nguyên | Phát hiện thay đổi và thực hiện thao tác điều kiện. |

**Bước 1: thiết kế key.**

~~~text
cart:{tenant:t7:cart:c42}:summary
cart:{tenant:t7:cart:c42}:items
cart:{tenant:t7:cart:c42}:coupon
cart:{tenant:t7:cart:c42}:version
~~~

Tất cả key dùng đúng tag **tenant:t7:cart:c42**.

**Bước 2: xác nhận slot** trên một Redis Cluster thử nghiệm.

~~~text
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:summary
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:items
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:coupon
CLUSTER KEYSLOT cart:{tenant:t7:cart:c42}:version
~~~

Kỳ vọng cả bốn lần đều trả cùng một số slot.

**Bước 3: ghi dữ liệu đúng với từng kiểu.**

~~~text
SET cart:{tenant:t7:cart:c42}:summary "2 products"
HSET cart:{tenant:t7:cart:c42}:items sku-1 1 sku-2 1
SET cart:{tenant:t7:cart:c42}:coupon WELCOME
SET cart:{tenant:t7:cart:c42}:version 1
~~~

**Bước 4: đọc và thao tác nhiều key.**

~~~text
GET cart:{tenant:t7:cart:c42}:summary
HGETALL cart:{tenant:t7:cart:c42}:items
MGET cart:{tenant:t7:cart:c42}:summary cart:{tenant:t7:cart:c42}:coupon
INCR cart:{tenant:t7:cart:c42}:version
~~~

MGET áp dụng cho hai key **String**. Key **items** là Hash, nên dùng HGETALL thay vì MGET. Một Hash vẫn được định vị theo tên key đầy đủ, dùng cùng tag với các key String bên cạnh.

**Bước 5: xem trạng thái sau thao tác.**

~~~text
TYPE cart:{tenant:t7:cart:c42}:items
GET cart:{tenant:t7:cart:c42}:version
EXISTS cart:{tenant:t7:cart:c42}:summary
~~~

**Bước 6: dọn đúng những key đã tạo trong môi trường thử nghiệm.**

~~~text
DEL cart:{tenant:t7:cart:c42}:summary cart:{tenant:t7:cart:c42}:items cart:{tenant:t7:cart:c42}:coupon cart:{tenant:t7:cart:c42}:version
~~~

Lệnh DEL nhiều key hợp lệ ở đây vì toàn bộ key cùng slot, dù giá trị thuộc những kiểu dữ liệu khác nhau. Chỉ chạy trên key thử nghiệm do bạn sở hữu.

### Câu hỏi tự suy nghĩ

1. Nếu thay key **cart:{tenant:t7:cart:c42}:coupon** bằng **cart:{tenant:t7}:coupon:c42**, chúng còn được bảo đảm cùng slot không? Vì sao?
2. Nếu một tenant có 200.000 giỏ hàng, dùng cùng tag **{tenant:t7}** cho mọi giỏ có ảnh hưởng gì tới phân phối tải?
3. Nếu chỉ cần lưu một số field chung TTL, có phải nhiều key với hash tag luôn tốt hơn một Hash không?
4. Nếu hai key cùng slot nhưng được cập nhật bằng hai lời gọi SET riêng, điều gì xảy ra khi thao tác thứ hai thất bại?

Đáp án nằm ở các nguyên tắc cốt lõi: **phần bên trong tag quyết định slot**, tag quá rộng dễ tạo điểm nóng, một Hash có thể đơn giản hơn nhiều key, và **cùng slot không tự tạo tính nguyên tử cho nhiều lệnh riêng**.

## 13. Những điểm cần nhớ khi làm việc với Spring Data Redis Cluster

- Redis Cluster có **16.384 hash slot**; slot của key thông thường là **CRC16(key) mod 16384**.
- Tên key có **{tag}** hợp lệ sẽ tính slot từ **tag**; hai key có cùng tag sẽ cùng slot.
- Các lệnh nhiều key như **MGET, MSET, DEL**, transaction hoặc Lua liên quan nhiều key phải tuân thủ ràng buộc slot trong Cluster.
- **Một lệnh một key** không nhất thiết cần hash tag; client cluster-aware sẽ định tuyến theo slot của key.
- Nên chọn tag theo **aggregate cần xử lý chung**, đủ hẹp để hạn chế hot slot, đủ ổn định để các service dùng nhất quán.
- **StringRedisTemplate/serializer** quyết định bytes key thực tế; phải kiểm chứng trên Redis chứ không chỉ từ chuỗi Java.
- **Cùng slot** không đồng nghĩa mọi thao tác hoặc mọi cập nhật giữa Redis và database đều nguyên tử.
- **CLUSTER KEYSLOT** là công cụ kiểm tra trực tiếp; **redis-cli -c** giúp theo chuyển hướng nhưng không bỏ qua quy tắc CROSSSLOT.

**Thông điệp chính:** trong Spring Data Redis Cluster, hash tag là một quyết định **thiết kế tên khóa**. Chọn một phần định danh ổn định đặt trong cặp ngoặc nhọn giúp những key có quan hệ thao tác được đưa về cùng một slot. Hãy dùng nó cho các nhóm key thật sự cần phối hợp và kiểm chứng bằng CLUSTER KEYSLOT, đồng thời giữ đủ nhiều nhóm độc lập để Cluster tiếp tục phân phối tải hiệu quả.
