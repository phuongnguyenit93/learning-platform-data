# Lựa chọn một khóa lớn hay nhiều khóa nhỏ theo kiểu truy cập

Khi thiết kế dữ liệu trong **Spring Data Redis**, một câu hỏi quan trọng là: **nên gom nhiều thông tin vào một Redis key lớn, hay tách thành nhiều key nhỏ?** Ví dụ, một giỏ hàng có 100 sản phẩm có thể nằm trong một key kiểu Hash, một key chứa JSON, hoặc 100 key lưu từng sản phẩm. Cả ba cách đều có thể hoạt động, nhưng chi phí đọc, ghi, hết hạn, xóa, mở rộng tải và bảo trì rất khác nhau.

Không có nguyên tắc tuyệt đối rằng “càng ít key càng tốt” hoặc “mỗi thuộc tính phải là một key”. **Ranh giới key phải phục vụ kiểu truy cập (access pattern) và vòng đời dữ liệu**, sau đó mới cân nhắc kích thước, bộ nhớ và số lượng kết nối/lệnh.

Trong bài này, “**một khóa lớn**” nghĩa là một Redis key chứa **nhiều phần tử hoặc payload lớn** (chẳng hạn một String JSON rất dài, Hash có rất nhiều field, List hay Sorted Set lớn). “**Nhiều khóa nhỏ**” nghĩa là tách cùng dữ liệu thành các key độc lập, mỗi key chứa ít dữ liệu hơn. Cũng cần phân biệt **một key cho mỗi đối tượng** với **một key cho toàn bộ hệ thống**: hai phương án có tính mở rộng rất khác nhau.

## 1. Bài toán ví dụ: lưu giỏ hàng

Giả sử hệ thống thương mại điện tử quản lý giỏ hàng của từng người dùng. Mỗi giỏ chứa các cặp `productId → quantity`:

~~~text
User 42:
  SKU-A -> 2
  SKU-B -> 1
  SKU-C -> 4

User 57:
  SKU-D -> 1
  SKU-E -> 3
~~~

Cùng dữ liệu này có nhiều cách biểu diễn:

**Phương án A — Một String JSON cho mỗi giỏ:**

~~~text
Key: cart:42
Type: String
Value: {"SKU-A":2,"SKU-B":1,"SKU-C":4}
~~~

**Phương án B — Một Hash cho mỗi giỏ:**

~~~text
Key: cart:42
Type: Hash
Fields:
  SKU-A -> "2"
  SKU-B -> "1"
  SKU-C -> "4"
~~~

**Phương án C — Một key String cho mỗi dòng sản phẩm:**

~~~text
cart:42:SKU-A -> "2"
cart:42:SKU-B -> "1"
cart:42:SKU-C -> "4"
~~~

Có thể nghĩ đến **phương án D — Một Hash chứa giỏ hàng của mọi người dùng**:

~~~text
Key: carts:all
Type: Hash
Fields:
  42:SKU-A -> "2"
  42:SKU-B -> "1"
  57:SKU-D -> "1"
  ... hàng triệu field khác ...
~~~

Phương án D giảm số lượng key trong keyspace nhưng có nguy cơ tạo **một key rất lớn và rất nóng (hot key)**. Mọi thao tác lên key đó cùng hướng đến một key/slot; chính sách TTL, chia shard và dọn dẹp trở nên khó. Vì vậy, **đừng nhầm “một Hash cho mỗi giỏ” với “một Hash cho tất cả giỏ hàng”**.

## 2. Redis key là ranh giới của những gì?

Trong Redis, key là đơn vị quan trọng cho nhiều thao tác:

| Khả năng | Đơn vị áp dụng trong trường hợp phổ biến | Hệ quả thiết kế |
|---|---|---|
| `GET` / `SET` với String | Toàn bộ giá trị của một key | Có thể phải truyền/ghi lại cả payload khi sửa một phần |
| `HGET` / `HSET` với Hash | Một field nằm trong một key Hash | Có thể đọc/sửa từng field mà không lấy toàn bộ Hash |
| `DEL` / `UNLINK` | Một hoặc nhiều key | Xóa cả aggregate dễ, xóa một phần cần lệnh theo kiểu dữ liệu |
| `EXPIRE` / `TTL` | Toàn bộ key | Các field trong cùng key thường chia sẻ vòng đời hết hạn |
| Redis Cluster hash slot | Tính từ **tên key** | Một key và toàn bộ dữ liệu của nó nằm trong cùng slot |
| Redis ACL theo key pattern | Tên key | Prefix/key namespace ảnh hưởng ranh giới truy cập |
| Quan sát big key/hot key | Theo key và workload | Một key quá lớn hoặc quá nóng cần được phát hiện riêng |

Redis phiên bản mới có thể hỗ trợ một số cơ chế hết hạn ở cấp field của Hash, nhưng **không nên mặc định mọi Redis Server, driver và phiên bản Spring Data Redis đều hỗ trợ cùng API/semantics đó**. Với thiết kế phổ thông, TTL của cả key vẫn là ranh giới dễ dự đoán nhất. Khi cần TTL độc lập ở cấp phần tử, nhiều key riêng thường đơn giản hơn.

### 2.1. Key lớn không có nghĩa mọi lệnh đều chậm

Cần tách hai nhận định:

- `HGET cart:42 SKU-A` có thể đọc **một field** từ Hash mà không phải chuyển toàn bộ Hash qua mạng; nhiều thao tác Hash có độ phức tạp trung bình tốt, chẳng hạn `HGET` thường O(1) trung bình.
- `HGETALL carts:all` lại trả **mọi field**. Với Hash khổng lồ, dữ liệu truyền, bộ nhớ tạm và thời gian xử lý đều có thể rất lớn.

Vấn đề không chỉ là **key đang lớn bao nhiêu**, mà còn là **mỗi lệnh lấy/sửa bao nhiêu dữ liệu** và **có bao nhiêu client cùng truy cập key đó**.

Một key chứa vài nghìn field và chủ yếu dùng `HGET` có thể hợp lý. Một key chứa vài triệu field nhưng liên tục `HGETALL`, `HSCAN`, `DEL` hoặc bị ghi tranh chấp có thể trở thành điểm nghẽn.

## 3. Lựa chọn theo access pattern trước khi lựa chọn kiểu dữ liệu

Trước khi viết `RedisTemplate` hay `StringRedisTemplate`, hãy mô tả cách dữ liệu được sử dụng:

1. **Đọc gì?** Luôn đọc trọn đối tượng hay thường lấy một thuộc tính?
2. **Ghi gì?** Thay toàn bộ snapshot hay cập nhật từng field/counter?
3. **Đọc/ghi bao nhiêu lần?** Có một key bị gọi rất thường xuyên trong khi các key khác ít truy cập không?
4. **Hết hạn thế nào?** Mọi phần tử cùng TTL hay từng phần tử có TTL khác nhau?
5. **Xóa thế nào?** Xóa toàn bộ giỏ hàng/hồ sơ hay xóa từng phần tử?
6. **Cần atomicity ở mức nào?** Một lệnh đơn giản có đủ không, hay phải phối hợp nhiều key?
7. **Có Redis Cluster không?** Dữ liệu cần phân tán qua nhiều slot hay cần co-location cho multi-key command?
8. **Kích thước tăng đến đâu?** Bao nhiêu field/item mỗi key, payload bao nhiêu bytes, số key toàn hệ thống tăng ra sao?

Một bảng quyết định sơ bộ:

| Access pattern chủ đạo | Phương án thường đáng cân nhắc | Lý do |
|---|---|---|
| Luôn đọc/ghi **trọn snapshot nhỏ** | Một String JSON cho mỗi đối tượng | Một `GET`/`SET`, serialize đơn giản |
| Đọc/sửa **một vài field** trong cùng đối tượng | Một Hash cho mỗi đối tượng | `HGET`, `HMGET`, `HSET` thao tác theo field |
| Mọi field của đối tượng **hết hạn cùng lúc** | Một key cho đối tượng (String/Hash) | Một `EXPIRE`, xóa cả đối tượng tiện |
| Từng phần tử cần **TTL hoặc quyền/quy tắc xóa khác nhau** | Nhiều key nhỏ | Mỗi key có vòng đời riêng |
| Nhiều đối tượng độc lập, tải cao | Một key/aggregate cho mỗi đối tượng | Dễ phân tán và tránh gom toàn bộ tải vào một key |
| Cần đọc tất cả item của một aggregate rất lớn | Chia trang, phân vùng hoặc thiết kế collection phù hợp | Tránh trả payload khổng lồ mỗi request |
| Rất nhiều field nhỏ, cùng TTL, truy cập theo field | Hash theo nhóm hợp lý | Có thể tiết kiệm overhead key so với nhiều String key |
| Một counter nóng cập nhật liên tục | Key counter riêng, `INCR`, hoặc phân mảnh khi cần | Dễ atomic update, giám sát và kiểm soát tranh chấp |
| Nhiều item phải truy vấn theo score/thứ tự | Sorted Set/List/Stream theo bài toán | Cấu trúc Redis chuyên dụng tốt hơn tự tạo key-per-item để mô phỏng |

Đây là **hướng chọn điểm xuất phát**, không phải quy tắc cứng. Cần đo payload, latency, bộ nhớ và tải thực tế trước khi tối ưu.

## 4. Phương án 1: một String JSON cho mỗi đối tượng

Giả sử ứng dụng cache một bản snapshot hồ sơ sản phẩm:

~~~text
Key: product:sku-101:snapshot
Value:
{
  "name": "USB-C Cable",
  "price": 120000,
  "currency": "VND",
  "available": true
}
TTL: 10 phút
~~~

Ở Spring Data Redis, có thể lưu chuỗi JSON đã được serialize:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSnapshotCache {

    private final StringRedisTemplate redis;

    public ProductSnapshotCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String productId, String jsonPayload) {
        redis.opsForValue().set(
                "product:" + productId + ":snapshot",
                jsonPayload,
                Duration.ofMinutes(10)
        );
    }

    public String get(String productId) {
        return redis.opsForValue().get(
                "product:" + productId + ":snapshot"
        );
    }

    public void evict(String productId) {
        redis.delete("product:" + productId + ":snapshot");
    }
}
~~~

`jsonPayload` là JSON đã được ứng dụng tạo bằng serializer phù hợp, ví dụ Jackson. Bài học tập trung vào ranh giới key, nên không gắn vào một DTO cụ thể.

**Ưu điểm**

- Đọc trọn snapshot bằng một lệnh `GET`.
- Ghi trọn snapshot và đặt TTL bằng một lệnh `SET`.
- Dễ xóa cả snapshot bằng `DEL`.
- Serializer JSON giúp dữ liệu dễ tương tác với ứng dụng khác nếu schema được thống nhất.

**Giới hạn**

- Muốn đổi một trường nhỏ, thường phải **GET → deserialize → sửa → serialize → SET lại cả payload**.
- Hai luồng cùng cập nhật bằng quy trình đọc–sửa–ghi có thể ghi đè thay đổi của nhau (**lost update**).
- Khi payload lớn, mỗi lần đọc/ghi cả khối làm tăng bytes truyền và chi phí serialize/deserialize.
- Nếu một key lưu toàn bộ đối tượng của mọi người dùng, key có thể quá lớn và quá nóng.

### 4.1. Ví dụ lost update với JSON

Giả sử hai request đồng thời đọc:

~~~json
{"color":"black","stock":10}
~~~

Request A sửa `color` thành `white`; request B sửa `stock` thành `9`. Nếu cả hai đều `SET` lại toàn bộ JSON dựa trên snapshot cũ, kết quả có thể là:

~~~json
{"color":"black","stock":9}
~~~

Thay đổi của request A đã mất. Một `SET` là atomic ở mức lệnh, nhưng **chuỗi GET → sửa → SET không tự atomic**.

Nếu nghiệp vụ thường cập nhật một trường, Hash với `HSET` thường là điểm xuất phát tốt hơn. Nếu vẫn cần JSON nguyên khối và tính nhất quán chặt chẽ, có thể cân nhắc optimistic locking qua `WATCH`/`MULTI`/`EXEC`, Lua script hoặc cơ chế đồng bộ phù hợp.

## 5. Phương án 2: một Hash cho mỗi đối tượng

Với giỏ hàng, có thể đặt **mỗi giỏ là một Redis Hash**:

~~~text
Redis key: cart:42

Field    Value
------   -----
SKU-A    2
SKU-B    1
SKU-C    4
~~~

Các lệnh Redis tương ứng:

~~~bash
HSET cart:42 SKU-A 2 SKU-B 1 SKU-C 4
HGET cart:42 SKU-A
HMGET cart:42 SKU-A SKU-C
HGETALL cart:42
HDEL cart:42 SKU-B
EXPIRE cart:42 1800
~~~

### 5.1. Spring Data Redis thao tác Hash

~~~java
import java.time.Duration;
import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartHashStore {

    private static final Duration CART_TTL =
            Duration.ofMinutes(30);

    private final StringRedisTemplate redis;
    private final HashOperations<String, String, String> hash;

    public CartHashStore(StringRedisTemplate redis) {
        this.redis = redis;
        this.hash = redis.opsForHash();
    }

    private String key(String userId) {
        return "cart:" + userId;
    }

    public void putItem(
            String userId,
            String sku,
            int quantity) {
        String cartKey = key(userId);

        hash.put(cartKey, sku, Integer.toString(quantity));
        redis.expire(cartKey, CART_TTL);
    }

    public String getItem(String userId, String sku) {
        return hash.get(key(userId), sku);
    }

    public List<String> getSelectedItems(
            String userId,
            Collection<String> skus) {
        return hash.multiGet(key(userId), skus);
    }

    public Map<String, String> getAllItems(String userId) {
        return hash.entries(key(userId));
    }

    public void removeItem(String userId, String sku) {
        hash.delete(key(userId), sku);
    }

    public void clearCart(String userId) {
        redis.delete(key(userId));
    }
}
~~~

Trong ví dụ:

- `HSET` chỉ cập nhật một field `sku`.
- `HGET` đọc một sản phẩm mà không phải lấy tất cả sản phẩm của giỏ.
- `HMGET` đọc nhiều field chọn lọc trong cùng Hash.
- `HGETALL` thông qua `hash.entries(...)` hợp lý khi giỏ có kích thước giới hạn; với Hash rất lớn không nên dùng để trả tất cả dữ liệu liên tục.
- `HDEL` xóa một field, còn `DEL` xóa toàn bộ giỏ.
- `EXPIRE` áp dụng cho cả key `cart:42`, không mặc nhiên cho từng SKU.

**Lưu ý về tính atomic:** `hash.put(...)` và `redis.expire(...)` là **hai lệnh riêng**. Nếu ứng dụng bị ngắt giữa hai lệnh hoặc có luồng khác can thiệp, không có bảo đảm cập nhật field và TTL như một thao tác atomic duy nhất. Với yêu cầu TTL phải được gán đồng thời cùng lần cập nhật, cần dùng Lua script hoặc cơ chế transaction phù hợp; đoạn trên nhằm minh họa API cơ bản.

### 5.2. Khi nào một Hash cho mỗi đối tượng hợp lý?

Phù hợp khi:

- Các field thuộc cùng một aggregate (ví dụ giỏ hàng, user settings, cấu hình tạm).
- Thường xuyên đọc/sửa từng field.
- Cần xóa toàn bộ aggregate cùng lúc.
- Các field thường có **vòng đời hết hạn chung**.
- Số field/aggregate có giới hạn hợp lý.

Hạn chế khi:

- Mỗi field có TTL độc lập và thay đổi thường xuyên.
- Aggregate liên tục phát triển thành hàng trăm nghìn hoặc hàng triệu field.
- Một key là điểm nóng của rất nhiều luồng ghi hoặc nằm trên một shard quá tải.
- Ứng dụng luôn phải duyệt/tải toàn bộ Hash khổng lồ bằng `HGETALL`.

### 5.3. Một Hash không đồng nghĩa một String JSON

Hash cho phép thao tác field. Với JSON trong String, `GET` trả cả chuỗi và `SET` thay cả chuỗi. Hai cấu trúc có thể cùng sử dụng **một key**, nhưng access pattern và lượng dữ liệu mỗi lệnh khác nhau.

Trong Redis, mỗi field của Hash có thể được truy cập bằng `HGET` hoặc cập nhật bằng `HSET`. Điều đó giúp giảm network payload và tránh quy trình đọc–sửa–ghi cả JSON khi hai thao tác cập nhật hai field độc lập.

Tuy nhiên, nếu một nghiệp vụ cần sửa **nhiều field phải cùng thỏa invariant**, cần thiết kế atomicity của **cả nghiệp vụ** chứ không chỉ dựa vào từng `HSET` độc lập.

## 6. Phương án 3: nhiều key nhỏ theo phần tử

Thay vì mỗi giỏ là một Hash, có thể tách từng mục:

~~~text
cart-item:42:SKU-A -> "2"  TTL 15 phút
cart-item:42:SKU-B -> "1"  TTL 45 phút
cart-item:42:SKU-C -> "4"  TTL 10 phút
~~~

Spring Data Redis:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class IndependentCartItemStore {

    private final StringRedisTemplate redis;

    public IndependentCartItemStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private String key(String userId, String sku) {
        return "cart-item:" + userId + ":" + sku;
    }

    public void put(
            String userId,
            String sku,
            int quantity,
            Duration ttl) {
        redis.opsForValue().set(
                key(userId, sku),
                Integer.toString(quantity),
                ttl
        );
    }

    public String get(String userId, String sku) {
        return redis.opsForValue().get(key(userId, sku));
    }

    public void remove(String userId, String sku) {
        redis.delete(key(userId, sku));
    }
}
~~~

**Ưu điểm**

- Mỗi phần tử có **TTL riêng** và có thể được xóa độc lập.
- Một phần tử tăng kích thước hoặc thay đổi thường xuyên không bắt buộc ghi lại phần tử khác.
- Nhiều key của nhiều người dùng có thể phân bố qua Redis Cluster slots, giúp phân tán tải.
- Thao tác `GET`/`SET` với một phần tử đơn giản, dễ quan sát.

**Chi phí và vấn đề mới**

- Mỗi key có metadata và overhead riêng (tên key, cấu trúc keyspace, expiration nếu có); rất nhiều key nhỏ có thể dùng nhiều bộ nhớ hơn một Hash gom field phù hợp.
- Đọc toàn bộ giỏ phải biết danh sách key nào thuộc giỏ. Redis **không tự cung cấp một chỉ mục “mọi key thuộc user 42”** theo prefix để query hiệu quả ở thời gian cố định.
- Xóa cả giỏ có thể cần danh sách key hoặc một cơ chế quản lý index/namespace; không có một `DEL cart:42` như phương án một Hash.
- Đọc nhiều key có thể phát sinh nhiều round trips, trừ khi dùng batch/pipeline/multi-get thích hợp.
- Một nghiệp vụ cập nhật đồng thời nhiều key cần quan tâm atomicity và Redis Cluster.

### 6.1. Đừng dùng KEYS để “lấy tất cả phần tử của một user” trong request

Thiết kế kiểu:

~~~text
KEYS cart-item:42:*
~~~

không phải cách truy vấn hợp lý cho đường request của hệ thống có nhiều key, vì `KEYS` có thể quét toàn bộ keyspace và gây gián đoạn. `SCAN` giúp duyệt dần theo cursor, nhưng **vẫn là thao tác duyệt**, không phải index tìm kiếm tức thì. Nó có thể trả phần tử trùng lặp trong quá trình scan và cần caller xử lý đúng; dữ liệu đang thay đổi có thể ảnh hưởng kết quả quan sát.

Nếu nhu cầu thường xuyên là **“đọc/xóa toàn bộ giỏ của một user”**, hãy chọn một Hash theo giỏ hoặc duy trì cấu trúc index riêng (chẳng hạn Set chứa item IDs) cùng cơ chế cập nhật nhất quán. Không nên thiết kế đường API phụ thuộc vào việc quét prefix của Redis keyspace.

### 6.2. MGET/pipeline có giải quyết mọi chi phí nhiều key không?

Nếu ứng dụng **đã biết danh sách key**, có thể giảm round trips bằng `MGET`:

~~~java
import java.util.List;

List<String> keys = List.of(
        "cart-item:42:SKU-A",
        "cart-item:42:SKU-B",
        "cart-item:42:SKU-C"
);

List<String> values = redis.opsForValue().multiGet(keys);
~~~

Trong Redis standalone, `MGET` đọc nhiều String key trong một command; kết quả tương ứng các key và có thể chứa null khi key không tồn tại. Với **Redis Cluster**, các lệnh nhiều key bị ràng buộc bởi hash slot (cùng slot đối với nhiều thao tác native). Một số client cung cấp cơ chế phân tách/batch nhiều slot, nhưng không nên giả định mọi `MGET` đa slot hoạt động như một lệnh atomic hoặc luôn được hỗ trợ theo cùng cách.

`Pipelining` cũng có thể giảm round trips khi phải gửi nhiều lệnh. Tuy nhiên, pipeline không tự khiến nhiều thao tác độc lập trở thành transaction atomic và không giải quyết bài toán **không biết danh sách key**.

## 7. So sánh ba mô hình trên cùng một bài toán

| Tiêu chí | Một String JSON / giỏ | Một Hash / giỏ | Một String / món |
|---|---|---|---|
| Đọc cả giỏ | Một `GET`, chuyển toàn JSON | `HGETALL` | Cần biết và đọc nhiều key |
| Đọc một món | Thường phải lấy/parse JSON | `HGET` | `GET` |
| Sửa một món | Thường ghi lại JSON | `HSET` một field | `SET` một key |
| TTL từng món | Không tự có | Thường theo key; field TTL phụ thuộc Redis/version/API | Có, dễ thực hiện |
| TTL toàn giỏ | Một `EXPIRE`/ `SET` TTL | Một `EXPIRE` | Nhiều key phải phối hợp |
| Xóa cả giỏ | `DEL` một key | `DEL` một key | Xóa theo danh sách key/index |
| Xóa một món | Sửa lại JSON | `HDEL` | `DEL` một key |
| Partial update | Kém thuận tiện | Thuận tiện | Thuận tiện |
| Overhead keyspace | Ít key | Ít key | Nhiều key |
| Tranh chấp khi read-modify-write | Dễ lost update nếu không bảo vệ | Field độc lập tránh được một số xung đột | Key độc lập tránh xung đột giữa các món |
| Redis Cluster | Mỗi giỏ thuộc một slot | Mỗi giỏ thuộc một slot | Các món có thể rải nhiều slot |
| Phù hợp nhất | Snapshot nhỏ đọc/ghi trọn | Aggregate đọc/sửa theo field, TTL chung | Item độc lập, TTL riêng |

Không có phương án thắng mọi cột. Quyết định phải dựa vào **đường truy cập phổ biến nhất** và chi phí chấp nhận được cho những thao tác còn lại.

## 8. Thiết kế key theo ranh giới hết hạn (TTL)

TTL là một trong những tiêu chí có sức phân loại mạnh nhất.

### 8.1. Một TTL chung: có thể gom dữ liệu

Ví dụ một **session snapshot** gồm:

~~~text
session:abc123
  userId
  locale
  lastPage
  theme

Tất cả hết hạn sau 30 phút không hoạt động.
~~~

Nếu mọi thuộc tính đều tồn tại và bị xóa cùng session, đặt cùng một Hash hoặc String key có thể hợp lý. Khi session hết hạn, Redis xóa toàn aggregate theo chính sách TTL.

Với Hash, `HSET` chỉ thay đổi field và **không mặc nhiên làm mới TTL của key**. Nếu cần sliding expiration 30 phút kể từ lần hoạt động cuối, ứng dụng phải chủ động gọi `EXPIRE` ở sự kiện phù hợp. Với String, `SET` mặc định có thể làm mất TTL trước đó nếu không chỉ định TTL hoặc tùy chọn giữ TTL; vì vậy mã cập nhật snapshot nên **đặt TTL rõ ràng**.

### 8.2. TTL riêng: nhiều key thường tự nhiên hơn

Ví dụ:

~~~text
otp:user42:login     TTL 2 phút
otp:user42:reset     TTL 10 phút
token:user42:deviceA TTL 60 phút
~~~

Ba dữ liệu này có mục đích và vòng đời khác nhau, nên thường nên là các key riêng, không nhất thiết gom vào một Hash chỉ vì cùng userId.

Nếu dùng một Hash với nhiều field và gọi `EXPIRE` trên key đó, tất cả field sẽ chịu cùng thời điểm hết hạn của key. Khi mỗi field cần TTL độc lập, cần xem phiên bản Redis có hỗ trợ hash-field expiration và Spring Data Redis/driver có API thích hợp hay không; nếu không, tách key là cách đơn giản, dễ vận hành.

### 8.3. TTL phải nhất quán với thao tác cập nhật

Các câu hỏi thực tế:

- Khi sửa một field, TTL của cả aggregate có nên được làm mới?
- Một phần tử vừa được cập nhật có cần sống lâu hơn các phần tử khác không?
- Nếu TTL thay đổi, có nên reset tất cả phần tử trong một lần hay chỉ phần tử vừa sửa?
- Khi phần tử hết hạn, index/danh sách tham chiếu có được dọn không?

Nếu chưa trả lời được các câu hỏi này, thiết kế key dù tiết kiệm bộ nhớ cũng có thể sai về vòng đời nghiệp vụ.

## 9. Thiết kế theo mức cập nhật và atomicity

### 9.1. Một Redis command thường atomic, chuỗi lệnh thì không tự atomic

Ví dụ:

~~~text
INCR views:product:101
~~~

`INCR` là lệnh nguyên tử ở Redis: hai client tăng cùng counter không cần tự làm `GET → cộng 1 → SET`.

Ngược lại:

~~~text
GET cart:42
deserialize JSON
modify SKU-A
SET cart:42 new-json
~~~

gồm nhiều bước, có thể xảy ra lost update giữa các client.

Với Hash:

~~~text
HSET cart:42 SKU-A 3
HSET cart:42 SKU-B 2
~~~

mỗi lệnh độc lập là atomic, nhưng **hai lệnh không mặc nhiên tạo thành một transaction**. Nếu cần thay nhiều field đồng thời theo một invariant, có thể sử dụng một lệnh `HSET` nhiều cặp field hoặc cơ chế transaction/script thích hợp.

### 9.2. Chia thành nhiều key có thể làm khó thao tác liên quan

Giả sử nghiệp vụ phải vừa ghi:

~~~text
order:42:status = "PAID"
order:42:paidAt = "..."
~~~

Nếu status và paidAt phải được cập nhật cùng lúc, tách thành hai String key khiến ta phải điều phối nhiều lệnh và phải quan tâm các trường hợp cập nhật một phần. Một Hash theo order có thể cho phép cập nhật nhiều field trong **một lệnh HSET**.

Ngược lại, nếu `paidAt` được lưu vĩnh viễn còn một token xác nhận chỉ tồn tại hai phút, tách token thành key độc lập có thể hợp lý hơn dù đều liên quan cùng order.

### 9.3. Redis Cluster ảnh hưởng đến atomicity nhiều key

Trong Redis Cluster, hai key ở **hai hash slot khác nhau** không thể đơn giản tham gia mọi multi-key command/script như khi dùng một key trên standalone. Co-location bằng **hash tag** có thể hỗ trợ các lệnh cần key cùng slot, nhưng gom nhiều key vào một slot cũng giảm mức phân tán tải.

Vì vậy, nếu một nghiệp vụ thường xuyên cập nhật nhiều field **cần atomicity**, ưu tiên xem chúng có thuộc cùng một aggregate/Redis key hợp lý hay không trước khi quyết định chia quá nhỏ.

## 10. Redis Cluster: một key lớn có thể tạo điểm nóng

Redis Cluster chia key theo hash slot. **Một key không được chia thành nhiều shard chỉ vì value rất lớn**: toàn bộ Hash/String/List/Sorted Set của key đó thuộc về một slot, do một primary node chịu trách nhiệm tại một thời điểm.

Ví dụ:

~~~text
          Redis Cluster

   Node A           Node B           Node C
   +----------+     +----------+     +----------+
   | cart:42  |     | cart:57  |     | cart:91  |
   | cart:93  |     | cart:81  |     | cart:18  |
   +----------+     +----------+     +----------+
~~~

Khi mỗi user có một key/giỏ, các key có cơ hội phân tán qua nhiều slot/nodes.

Nếu thay bằng **một key `carts:all` chứa mọi user**, toàn bộ dữ liệu và mọi thao tác `HGET carts:all ...` tập trung vào **một slot**:

~~~text
Node A: carts:all (tất cả users; rất nóng)
Node B: gần như không có tải carts
Node C: gần như không có tải carts
~~~

Thậm chí dù `HGET` có độ phức tạp trung bình tốt, **một slot/node vẫn phải xử lý toàn bộ lưu lượng của key đó**. Ngoài throughput, key cực lớn còn gây khó khăn khi di chuyển slot, sao chép, phục hồi và xóa key.

### 10.1. Hash tag: gom key có chủ đích

Redis Cluster cho phép đặt phần tên trong `{...}` để các key dùng cùng hash tag được ánh xạ vào cùng slot.

~~~text
cart:{user42}:meta
cart:{user42}:item:SKU-A
cart:{user42}:item:SKU-B
~~~

Cả ba key có phần hash tag `user42`, vì vậy có thể được co-locate vào cùng slot; việc này hữu ích khi cần multi-key operation theo một user. Tuy nhiên, nếu **mọi key cùng mang tag `global`**, toàn bộ tải sẽ bị gom vào một slot, làm mất lợi thế phân tán.

**Hash tag là công cụ kiểm soát phân bố**, không phải cách làm cho key lớn tự chia nhỏ. Chỉ sử dụng khi có nhu cầu thao tác đa key cùng slot rõ ràng.

### 10.2. Nhiều key nhỏ không tự động phân tán đều

Nếu cách đặt tên hoặc hash tag khiến tất cả key vào cùng slot, chúng vẫn tập trung trên một node. Ngoài ra, một user rất nổi tiếng với nhiều request có thể gây **hot key** ngay cả khi key chỉ chứa vài bytes.

Cần phân biệt:

- **Big key:** key chứa payload nhiều bytes hoặc collection có số phần tử quá lớn.
- **Hot key:** key được truy cập rất thường xuyên, có thể trở thành điểm nghẽn do số request.

Một key có thể **to mà ít nóng**, **nhỏ mà rất nóng**, hoặc cả hai. Cách tối ưu của hai vấn đề không giống nhau.

## 11. Bộ nhớ: nhiều key nhỏ có giá riêng

Mỗi Redis key có chi phí quản lý ngoài bytes của value, ví dụ tên key, metadata của keyspace, expiration và cấu trúc dữ liệu nội bộ. Vì vậy:

- Một triệu key String rất ngắn có thể tốn nhiều bộ nhớ quản lý hơn cùng số field khi được nhóm hợp lý trong Hash.
- Một Hash nhỏ với field/value ngắn có thể được Redis biểu diễn rất tiết kiệm nhờ encoding tối ưu, tùy phiên bản và cấu hình.
- Khi Hash phát triển về số field hoặc kích thước field/value, cấu trúc nội bộ và memory footprint có thể thay đổi.
- Một JSON String nguyên khối có thể gọn ở một số trường hợp, nhưng cần truyền/serialize cả payload nếu cập nhật từng thuộc tính.

Không thể kết luận bằng cách chỉ so **độ dài chuỗi key** hoặc chỉ đếm số lượng lệnh. Cần so tổng bộ nhớ, kích thước payload truyền, CPU, latency, và chi phí dọn dẹp/phục hồi.

### 11.1. Ví dụ ước lượng định tính

Giả sử có 500.000 hồ sơ, mỗi hồ sơ 8 thuộc tính chuỗi ngắn:

~~~text
Thiết kế A: 500.000 Hash keys, mỗi Hash 8 fields
Thiết kế B: 4.000.000 String keys, mỗi key 1 field
~~~

Thiết kế B tăng số keyspace entries lên nhiều lần. Điều đó có thể làm tăng overhead metadata/expiration và chi phí quản lý key. Nhưng thiết kế A cũng phải được xem xét nếu một vài hồ sơ có hàng trăm nghìn field hoặc rất nhiều request đồng thời cập nhật cùng một hồ sơ.

Những con số trên là **số lượng minh họa**, không phải benchmark hiệu năng. Kích thước bộ nhớ thực tế phụ thuộc Redis version, encoding, tên key/field và dữ liệu cụ thể.

### 11.2. Tên key cũng có chi phí

Key quá dài tiêu tốn bộ nhớ và băng thông command. Key quá ngắn hoặc mơ hồ làm hệ thống khó quản lý.

Ví dụ:

~~~text
Nên cân nhắc:
product:sku101:snapshot
cart:user42
otp:login:user42

Hạn chế:
a1                         (khó hiểu, dễ trùng)
all-users-and-carts-and-... (trộn nhiều domain)
cart:user42:every-redundant-word:SKU-A:quantity...
~~~

Chọn naming convention nhất quán: **domain:entityId:purpose**, có thể bổ sung environment/tenant nếu cần cách ly. Tránh đưa mật khẩu, token thô hoặc dữ liệu cá nhân nhạy cảm vào tên key vì key thường xuất hiện trong log/metrics và công cụ quan sát.

## 12. Đọc và ghi theo batch: tối ưu đúng chỗ

Chi phí thực tế của một thao tác Redis thường gồm:

~~~text
Tổng thời gian cảm nhận
  ≈ network round trips
    + thời gian thực thi lệnh
    + bytes cần gửi/nhận
    + serialize/deserialize
    + chờ connection/thread/pool (nếu có)
~~~

Với dữ liệu chia nhiều key, ứng dụng có thể muốn giảm round trips:

- **`MGET`**: đọc nhiều String key đã biết.
- **`HMGET`**: đọc một số field từ cùng một Hash key.
- **Pipelining**: gửi nhiều command mà không đợi từng phản hồi ngay theo cách gọi tuần tự thông thường.
- **Batch ở tầng ứng dụng**: gom việc đọc hợp lý nhưng có giới hạn kích thước.

Ví dụ với `HashOperations`:

~~~java
List<String> wantedSkus = List.of("SKU-A", "SKU-C");

List<String> quantities =
        redis.<String, String>opsForHash()
             .multiGet("cart:42", wantedSkus);
~~~

`HMGET` chỉ gửi/trả các field được yêu cầu. Nếu giỏ có 100.000 field mà màn hình chỉ cần 3 field, `HMGET` phù hợp hơn `HGETALL`.

Nhưng batch quá lớn có thể làm tăng response size, gây áp lực bộ nhớ bên client và ảnh hưởng latency. Với collection lớn, hãy đặt giới hạn/ phân trang thay vì “lấy tất cả rồi lọc trong Java”.

## 13. Đừng tạo một key khổng lồ cho mọi đối tượng

Một thiết kế dễ mắc là:

~~~text
Key: users:all
Type: Hash

Field userId_1 -> JSON user 1
Field userId_2 -> JSON user 2
...
Field userId_1_000_000 -> JSON user 1.000.000
~~~

Nó có vẻ tiện vì keyspace chỉ có một key, nhưng gây nhiều vấn đề:

1. **Tập trung tải:** mọi yêu cầu đụng vào một key/slot trong Redis Cluster.
2. **TTL chung:** `EXPIRE users:all` sẽ tác động toàn bộ tập dữ liệu; khó cho từng user hết hạn độc lập theo API phổ thông.
3. **Dọn dẹp:** xóa cả key khổng lồ có thể tạo chi phí xử lý và giải phóng bộ nhớ đáng kể.
4. **Vận hành:** key quá lớn khó sao chép, di chuyển hoặc đánh giá mức tăng trưởng.
5. **Access pattern:** thao tác tải tất cả user qua `HGETALL` có thể gửi lượng dữ liệu khổng lồ.
6. **Phân quyền/tách tenant:** toàn bộ dữ liệu trộn trong một key khiến cô lập theo key pattern khó hơn.

Đổi lại, một Hash **cho mỗi user**:

~~~text
user:1:profile  -> Hash (8 fields)
user:2:profile  -> Hash (8 fields)
...
user:1000000:profile -> Hash (8 fields)
~~~

vẫn cho phép `HGET`/ `HSET` theo field và TTL theo user, đồng thời phân tán tải qua nhiều key. Đây thường là sự cân bằng tự nhiên giữa **gom field trong aggregate** và **tách aggregate độc lập**.

## 14. Dùng collection phù hợp thay vì luôn dùng String

Việc lựa chọn “một key hay nhiều key” luôn đi cùng lựa chọn **kiểu dữ liệu Redis**:

| Bài toán | Cấu trúc Redis có thể phù hợp | Lý do |
|---|---|---|
| Hồ sơ gồm vài thuộc tính, sửa từng field | Hash mỗi hồ sơ | `HGET`, `HSET`, `HMGET` |
| Cache response JSON đọc nguyên khối | String mỗi response/snapshot | `GET`/`SET` trọn payload |
| Counter độc lập theo sản phẩm | String counter mỗi sản phẩm | `INCR` atomic |
| Danh sách id thành viên không trùng | Set theo nhóm | `SADD`, `SREM`, membership |
| Bảng xếp hạng theo score | Sorted Set theo bảng xếp hạng | `ZADD`, truy vấn theo rank/score |
| Hàng đợi đơn giản | List hoặc Streams tùy yêu cầu | Dữ liệu có thứ tự, consumer semantics |
| Sự kiện cần ACK/replay | Streams với consumer group phù hợp | Không phải tự chế hàng đợi trên các String key |

Ví dụ, nếu bài toán là “top 100 sản phẩm có lượt mua cao nhất”, tạo một key String cho từng score rồi quét/sắp xếp bên Java thường kém tự nhiên hơn Sorted Set theo bảng xếp hạng. Nhưng **một Sorted Set có hàng chục triệu member** vẫn cần chính sách kích thước, phân vùng hoặc retention khi workload lớn.

Mục tiêu là **chọn đúng aggregate và đúng Redis data type**, rồi mới xem có cần chia nhỏ theo tenant, thời gian hoặc logical partition hay không.

## 15. Thiết kế theo kích thước tăng trưởng và giới hạn collection

Một key có thể ban đầu nhỏ nhưng tăng liên tục:

~~~text
Hôm nay:
  cart:user42 -> 3 fields

Một năm sau (nếu không giới hạn):
  events:global -> 20.000.000 fields
~~~

Hãy xác định **growth bound**:

- Giới hạn số item trong một giỏ/session là bao nhiêu?
- Một user hoặc tenant có thể tạo tối đa bao nhiêu field?
- Có chính sách loại bỏ mục cũ (`LTRIM`, `ZREMRANGEBYRANK`, `XTRIM`, `HDEL`) theo cấu trúc dữ liệu không?
- Những dữ liệu đã hết hạn nghiệp vụ có bị xóa không?
- Có cần phân vùng theo ngày/tháng/tenant/shard?

Ví dụ một leaderboard theo tháng:

~~~text
leaderboard:2026-10
leaderboard:2026-11
leaderboard:2026-12
~~~

Thay vì một `leaderboard:all-time` tăng vô hạn, chia theo kỳ thời gian có thể giúp dữ liệu có thời hạn, dễ lưu trữ/xóa và giảm kích thước mỗi key. Tuy nhiên, nếu nghiệp vụ cần xếp hạng all-time chính xác, phải thiết kế riêng và không xóa nhầm dữ liệu gốc.

## 16. Xóa một key rất lớn: DEL và UNLINK

Nếu một key chứa collection rất lớn, thao tác xóa có thể ảnh hưởng độ trễ:

- `DEL key` xóa key và thường giải phóng bộ nhớ trong luồng xử lý lệnh, nên giải phóng cấu trúc lớn có thể tốn thời gian.
- `UNLINK key` gỡ key khỏi keyspace, sau đó phần giải phóng bộ nhớ được xử lý bất đồng bộ ở nền khi thích hợp; cách này thường hữu ích khi dọn key lớn.

Ví dụ:

~~~bash
UNLINK old:large:hash
~~~

`UNLINK` **không phải phép màu giúp mọi thao tác trên big key trở nên rẻ**: dữ liệu vẫn phải được quản lý và thu hồi tài nguyên. Nó chủ yếu giảm phần công việc giải phóng có thể gây chặn ở đường xử lý lệnh. Cần xác nhận phiên bản Redis và API Spring Data Redis/driver hỗ trợ lệnh tương ứng nếu muốn gọi từ Java.

Với Hash lớn mà chỉ muốn xóa vài field, `HDEL` có thể phù hợp hơn xóa cả key. Với dữ liệu khổng lồ, nên thiết kế chia phần và retention trước khi phải dọn toàn bộ.

## 17. Quan sát big key, hot key và chi phí truy cập

Một thiết kế tốt phải có cách kiểm chứng từ hệ thống chạy thực tế.

### 17.1. Công cụ Redis CLI hữu ích

~~~bash
# Tìm key lớn theo loại dữ liệu bằng cách scan keyspace.
redis-cli --bigkeys

# Ước lượng lượng bộ nhớ một key đang dùng.
redis-cli MEMORY USAGE cart:42

# Đếm số field trong Hash.
redis-cli HLEN cart:42

# Kích thước payload String tính theo byte.
redis-cli STRLEN product:sku-101:snapshot

# Xem kiểu dữ liệu của key.
redis-cli TYPE cart:42

# Xem thông tin nội bộ về encoding (dành cho điều tra).
redis-cli OBJECT ENCODING cart:42
~~~

Các lệnh trên chỉ là ví dụ cho Redis CLI có quyền thích hợp. `MEMORY USAGE` là giá trị ước lượng theo cách Redis hạch toán bộ nhớ; một số collection được lấy mẫu theo tùy chọn/phiên bản. Không dùng một con số duy nhất để khẳng định tất cả overhead.

`--bigkeys` thực hiện quét keyspace và có thể tiêu tốn tài nguyên mạng/CPU trên tập dữ liệu lớn; hãy chạy có kiểm soát theo môi trường. Với hệ thống production, ưu tiên cơ chế metrics/observability được vận hành cho phép. Không sử dụng `KEYS *` trên keyspace lớn chỉ để thống kê.

### 17.2. Quan sát ở ứng dụng Spring

Theo dõi:

- P50/P95/P99 latency của đường API dùng Redis.
- Số lệnh `GET`, `HGET`, `HGETALL`, `MGET`, `HSET` và kích thước payload.
- Số lượng key/field và tốc độ tăng trưởng theo prefix.
- Network throughput ứng dụng ↔ Redis.
- Thời gian serialize/deserialize JSON.
- Redis CPU, memory usage, eviction, client connections và slowlog.
- Thao tác xóa key lớn gây latency spike hay không.

Đặc biệt, khi một service “chậm do Redis”, cần tách **network round trip**, **server execution**, **payload lớn**, **driver/pool wait**, **serialization** và **logic xử lý của application**. Chỉ đổi từ JSON String sang Hash hoặc tăng số key mà không xác định điểm nghẽn có thể không cải thiện tình hình.

### 17.3. Ví dụ câu hỏi đo đạc

Giả sử API đọc giỏ hàng dùng `HGETALL`:

~~~text
GET /carts/42  -> HGETALL cart:42
~~~

Nếu mỗi giỏ thường có 5–20 field, cách này có thể gọn. Nếu một số giỏ có 200.000 field, API nên cân nhắc giới hạn, phân trang hoặc thay đổi aggregate. Tránh khẳng định rằng `HGETALL` luôn tốt vì “chỉ có một Redis command”.

## 18. Các tình huống thiết kế cụ thể

### 18.1. Hồ sơ người dùng

**Kiểu truy cập:** thường lấy một vài trường (name, avatar, locale), cập nhật độc lập; hồ sơ user có thời hạn cache chung.

**Gợi ý:** `user:{id}:profile` là Hash theo user. `HMGET` lấy trường cần thiết, `HSET` sửa một trường. Nếu ứng dụng luôn đọc snapshot nguyên khối từ nguồn dữ liệu khác và cache nguyên response, một String JSON theo user cũng có thể hợp lý.

### 18.2. OTP hoặc mã xác minh

**Kiểu truy cập:** mỗi mã gắn với mục đích riêng, TTL ngắn và số lần kiểm tra/thu hồi khác nhau.

**Gợi ý:** key độc lập như `otp:login:{opaqueId}`, `otp:reset:{opaqueId}` với TTL từng key. Tránh gom vào một Hash có TTL chung nếu yêu cầu hết hạn độc lập. Với OTP, ngoài lưu trữ cần thiết kế bảo mật, giới hạn thử sai và nguyên tắc không log giá trị nhạy cảm.

### 18.3. Giỏ hàng

**Kiểu truy cập:** sửa quantity theo SKU, đọc toàn bộ giỏ khi checkout, xóa cả giỏ, TTL theo phiên mua sắm.

**Gợi ý:** một Hash `cart:{userId}` cho mỗi giỏ thường là điểm khởi đầu tốt. Nếu từng item có thời gian hết hạn khác nhau hoặc số item rất lớn, cần xem lại ranh giới và index.

### 18.4. Cache trang danh sách sản phẩm

**Kiểu truy cập:** mỗi trang hoặc mỗi bộ lọc trả một snapshot; thường đọc nguyên payload.

**Gợi ý:** một String cho mỗi tổ hợp query đã canonicalize, ví dụ `search:products:{queryHash}:page:1`, có TTL phù hợp. Không nhất thiết tách từng field JSON thành key khi API luôn cần toàn bộ response.

Cần kiểm soát cardinality của queryHash/filter để không tạo key vô hạn cho mọi biến thể truy vấn.

### 18.5. Bộ đếm view theo sản phẩm

**Kiểu truy cập:** tăng counter độc lập rất thường xuyên, đôi khi cần đọc một counter.

**Gợi ý:** `views:product:{id}` dùng `INCR`. Nếu một sản phẩm có traffic quá cao, key đó có thể thành hot key dù chỉ là String số nhỏ; cần đo tải và đánh giá sharded counter hoặc kiến trúc ghi phù hợp nếu thực sự nghẽn.

### 18.6. Thống kê theo ngày và tenant

**Kiểu truy cập:** nhiều counter theo tenant/ngày, cần xóa cả kỳ thống kê khi hết retention.

**Gợi ý:** có thể dùng Hash theo `metrics:{tenant}:{yyyyMMdd}` với field là metric name, rồi TTL theo kỳ. Tránh Hash `metrics:all` tồn tại mãi và nhận mọi ghi của tất cả tenant. Nếu mỗi metric có retention riêng, xem xét tách key cho metric tương ứng.

## 19. Anti-pattern và cách nhận diện

### 19.1. Một global Hash cho mọi tenant

~~~text
HSET all:tenants tenant1:status READY
HSET all:tenants tenant2:status READY
...
~~~

Vấn đề: tất cả tenant chung một key và một slot; khó TTL riêng, khó shard và khó cô lập quyền theo key.

**Thường nên:** chọn key theo tenant hoặc theo aggregate: `tenant:{id}:status`, `tenant:{id}:config`.

### 19.2. Một key cho mọi thuộc tính chỉ vì “microservice”

~~~text
user:42:firstName
user:42:lastName
user:42:timezone
user:42:locale
user:42:avatar
~~~

Nếu thường xuyên đọc tất cả hoặc vài thuộc tính cùng nhau và TTL như nhau, nhiều key nhỏ tạo overhead và chi phí index/đọc nhiều lệnh. Một Hash `user:42:profile` có thể đơn giản hơn.

### 19.3. JSON rất lớn nhưng chỉ cập nhật một trường

Nếu API mỗi giây sửa một trường trong JSON có hàng trăm KB, chi phí đọc/serialize/ghi lại toàn bộ payload có thể rất cao. Hash hoặc tách sub-aggregate theo kiểu truy cập đáng cân nhắc.

### 19.4. Xóa cả aggregate bằng SCAN theo prefix trong request

~~~text
SCAN 0 MATCH cart-item:42:*
DEL từng key ...
~~~

Việc quét keyspace không tạo ra một danh sách ổn định/atomic của các key đang thay đổi. Nếu xóa cả giỏ là yêu cầu phổ biến, hãy thiết kế **một key giỏ** hoặc một index có thể truy cập trực tiếp. Dùng SCAN như công cụ duyệt/maintenance có kiểm soát, không thay cho mô hình dữ liệu.

### 19.5. Một key “nhỏ” nhưng nóng bất thường

`home:global:counter` có thể chỉ chứa số nguyên nhưng nhận hàng trăm nghìn cập nhật trong thời gian ngắn. Chia giá trị thành nhiều key hoặc phân tầng đếm có thể giảm tập trung tải, song làm tăng chi phí tổng hợp và độ phức tạp nhất quán. Chỉ triển khai khi có số liệu cho thấy key thực sự là điểm nghẽn.

## 20. Quy trình ra quyết định thực tế

Khi thêm một tập dữ liệu mới vào Spring Data Redis, có thể đi theo trình tự:

~~~text
                       DỮ LIỆU CẦN LƯU
                              |
                              v
               Có một aggregate rõ ràng không?
                        /             \
                      Có              Không
                      |                 |
                      v                 v
           Đọc/ghi cả khối?       Xác định các tập
              /       \           dữ liệu độc lập
            Có        Không            |
            |            |             v
            v            v       TTL và tần suất
       String JSON   Hash/collection     truy cập riêng?
            |        theo aggregate       |
            +------------+---------------+
                         |
                         v
                  TTL chung hay riêng?
                   /             \
               Chung             Riêng
                 |                 |
                 v                 v
         Có thể gom key       Tách key hoặc chọn
         theo aggregate       hỗ trợ TTL phù hợp
                 |                 |
                 +--------+--------+
                          |
                          v
              Kích thước và hot spot có giới hạn?
                     /              \
                    Có              Không
                    |                 |
                    v                 v
             Thử nghiệm thực tế   Chia aggregate,
             đo latency/memory    partition, retention
                    |                 |
                    +--------+--------+
                             |
                             v
                  Kiểm tra Redis Cluster,
                atomicity, batch read, cleanup
                             |
                             v
                  Chọn model và giám sát
~~~

Một cách ngắn gọn để áp dụng bảng trên:

1. **Vẽ entity/aggregate** và các API thường gọi.
2. **Ghi rõ thao tác phổ biến nhất:** `GET` toàn bộ, `HGET` vài field, cập nhật từng item, xóa cả nhóm, v.v.
3. **Đánh dấu TTL:** cùng hạn hay độc lập.
4. **Dự kiến cardinality và skew:** số key, số field mỗi key, key nào có thể rất nóng.
5. **Xác định multi-key/atomic requirements** và Cluster slot constraints.
6. **Viết bản đơn giản**, đo đạc bằng dữ liệu gần thực tế.
7. **Chia nhỏ hoặc gom lại khi có số liệu**, kèm kế hoạch migration/invalidation nếu đã có dữ liệu đang sử dụng.

## 21. Bài thực hành với Spring Data Redis

### Bài tập A — So sánh đọc một field

Lưu dữ liệu:

~~~bash
SET demo:product:json '{"name":"Cable","price":120000,"stock":10}'
HSET demo:product:hash name Cable price 120000 stock 10
~~~

Đọc:

~~~bash
GET demo:product:json
HGET demo:product:hash stock
HMGET demo:product:hash name stock
~~~

Quan sát dữ liệu trả về: `GET` trả cả JSON; `HGET` chỉ trả field `stock`. Với một đối tượng nhỏ, sự khác biệt có thể không đáng kể, nhưng với payload lớn và tần suất truy cập cao, nó ảnh hưởng mạng và chi phí xử lý.

### Bài tập B — TTL chung và TTL riêng

~~~bash
HSET demo:cart:42 SKU-A 2 SKU-B 1
EXPIRE demo:cart:42 60
TTL demo:cart:42

SET demo:cart-item:42:SKU-A 2 EX 20
SET demo:cart-item:42:SKU-B 1 EX 90
TTL demo:cart-item:42:SKU-A
TTL demo:cart-item:42:SKU-B
~~~

Hỏi:

- Vì sao `demo:cart:42` hết hạn thì cả hai field biến mất?
- Vì sao hai key `demo:cart-item:...` có TTL độc lập?
- Nếu checkout cần xóa toàn bộ giỏ, cách nào dễ thực hiện trong một lệnh?

### Bài tập C — Quan sát memory và số field

~~~bash
TYPE demo:cart:42
HLEN demo:cart:42
MEMORY USAGE demo:cart:42
~~~

Thử tăng số field theo tập dữ liệu giả lập và so sánh với nhiều String key riêng. Không lấy một lần chạy để kết luận rộng: kích thước key/field, Redis version, encoding và trạng thái bộ nhớ đều ảnh hưởng kết quả. Khi hoàn thành, dọn các key thử nghiệm.

### Bài tập D — Thử thay đổi access pattern

Giả sử ban đầu API chỉ đọc cả hồ sơ, bạn chọn String JSON. Sau đó tính năng mới cần cập nhật `lastSeen` hàng chục lần mỗi giây, trong khi các field khác ít thay đổi.

Thảo luận:

- Có nên tiếp tục ghi lại cả JSON sau mỗi lần `lastSeen` thay đổi không?
- Có nên chuyển thành Hash per user, hoặc tách `lastSeen` thành một key độc lập?
- TTL của `lastSeen` có giống TTL của hồ sơ không?
- Dữ liệu `lastSeen` có cần độ chính xác tuyệt đối hay được phép trì hoãn/cập nhật theo batch?

Đây chính là bài toán lựa chọn ranh giới key theo **kiểu truy cập thay đổi theo thời gian**.

## 22. Câu hỏi củng cố

**1. Khi nào một String JSON là lựa chọn tốt hơn Hash?**

Khi ứng dụng thường đọc/ghi nguyên snapshot, dữ liệu không quá lớn và hiếm cập nhật riêng lẻ từng field. Một `GET`/`SET` trọn payload và TTL theo key làm mô hình đơn giản.

**2. Vì sao một Hash cho mỗi user thường tốt hơn một Hash chứa mọi user?**

Vì mỗi user có vòng đời, nhu cầu xóa và access pattern riêng. Nhiều key theo user có thể phân tán trên các slot Redis Cluster, tránh gom toàn bộ dữ liệu/tải vào một key khổng lồ.

**3. Nếu chỉ cần đọc một field trong Hash lớn, có nhất thiết phải tải toàn bộ Hash không?**

Không. Dùng `HGET` hoặc `HMGET`; tránh `HGETALL` nếu chỉ cần một vài field.

**4. Nhiều key nhỏ có lợi ích rõ nhất trong trường hợp nào?**

Khi các phần tử cần TTL riêng, được cập nhật/xóa độc lập, hoặc cần phân tán tải giữa nhiều aggregate.

**5. Tách 100 field thành 100 String key có phải luôn dùng ít bộ nhớ hơn một Hash không?**

Không. Mỗi key độc lập có metadata và expiration overhead. Một Hash có thể tiết kiệm bộ nhớ cho nhiều field nhỏ, tùy encoding và dữ liệu.

**6. Vì sao một key có `HGET` trung bình O(1) vẫn có thể là hot key?**

Vì quá nhiều request đổ vào cùng key/slot/node. Độ phức tạp một lệnh không giải quyết được giới hạn throughput khi tập trung tải.

**7. Có thể tìm mọi key theo prefix bằng `KEYS prefix:*` trong API production không?**

Không nên. `KEYS` có thể quét toàn keyspace. `SCAN` thích hợp hơn cho duyệt có kiểm soát nhưng vẫn không phải index lookup trực tiếp; thiết kế nên biết danh sách key từ aggregate/index.

**8. Vì sao `GET → sửa JSON → SET` cần cẩn thận với concurrent updates?**

Hai client có thể đọc cùng bản cũ rồi ghi đè kết quả của nhau. Một `SET` atomic không làm cả chuỗi đọc–sửa–ghi trở thành atomic.

**9. Hash field có mặc nhiên có TTL riêng không?**

Không thể mặc định như vậy. TTL key là khả năng phổ biến; hash-field expiration phụ thuộc Redis version và API hỗ trợ. Khi nghiệp vụ yêu cầu TTL riêng và chưa có hỗ trợ tương thích, nhiều key độc lập thường rõ ràng hơn.

**10. Vì sao dùng hash tag trong Redis Cluster phải có chủ đích?**

Hash tag giúp các key cùng nhóm nằm trong một slot khi cần multi-key operations, nhưng nếu gom tất cả traffic vào cùng tag, một shard có thể thành điểm nóng.

## Ghi nhớ

~~~text
THƯỜNG ĐỌC/GHI CẢ KHỐI NHỎ
  -> Một String JSON cho mỗi aggregate

THƯỜNG ĐỌC/SỬA THEO FIELD, TTL CHUNG
  -> Một Hash cho mỗi aggregate

MỖI PHẦN TỬ ĐỘC LẬP, TTL RIÊNG
  -> Nhiều key nhỏ (cần giải quyết index/batch/cleanup)

NHIỀU AGGREGATE ĐỘC LẬP
  -> Nhiều key theo aggregate; tránh một global mega-key

KEY RẤT LỚN
  -> Xem payload, số field, HGETALL, DEL/UNLINK, retention

KEY RẤT NÓNG
  -> Xem skew, throughput, Cluster slot, partition/caching

QUYẾT ĐỊNH
  -> Access pattern + TTL + atomicity + kích thước + topology
     rồi đo bằng workload thực tế
~~~

**Ranh giới Redis key tốt thường đi theo một đơn vị dữ liệu có cách đọc, cập nhật, hết hạn và xóa thống nhất.** Gom các field liên quan giúp giảm overhead và thuận tiện thao tác theo aggregate; tách các phần tử độc lập giúp đặt TTL riêng và phân tán tải. Trong Spring Data Redis, việc chọn `StringRedisTemplate`, `HashOperations`, nhiều key, batch hay collection chuyên dụng nên xuất phát từ access pattern và các yêu cầu vận hành này.
