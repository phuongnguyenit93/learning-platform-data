# Chọn độ dài khóa và kiểm soát số lượng khóa

Trong Redis, mỗi **key** là một tên định danh cho một giá trị hoặc cấu trúc dữ liệu. Với Spring Data Redis, key có thể được tạo trực tiếp qua `StringRedisTemplate`, `RedisTemplate`, hoặc gián tiếp thông qua Redis Repository, Spring Cache và các thành phần tích hợp khác. Cách đặt tên và số lượng key ảnh hưởng trực tiếp đến **bộ nhớ, hiệu năng, mức tăng trưởng dữ liệu, độ rõ ràng của mô hình và khả năng vận hành**.

Hai mục tiêu phải được cân bằng:

- **Độ dài khóa (key length)**: tên đủ ngắn để không lãng phí bộ nhớ nhưng đủ rõ nghĩa, ổn định, không xung đột và không để lộ thông tin nhạy cảm.
- **Số lượng khóa (key cardinality)**: không tạo quá nhiều key độc nhất do timestamp, request ID, tổ hợp tham số hoặc dữ liệu tạm thiếu thời hạn xóa.

Rút ngắn tên key không giải quyết được việc tạo hàng trăm triệu key. Gom mọi thứ vào một Hash để giảm số key cũng có thể tạo ra **big key**, gây vấn đề bộ nhớ và độ trễ. Vì vậy, việc chọn độ dài key phải gắn với **mô hình dữ liệu, TTL, cấu trúc Redis, ngân sách bộ nhớ và công cụ giám sát**.

## 1. Phân biệt key length, key count và value size

Ví dụ một ứng dụng thương mại điện tử có các key:

~~~text
shop:production:catalog:product:detail:0000000000000042
shop:prod:product:42
product:42
p:42
~~~

Bốn tên trên có thể cùng định danh một sản phẩm. Tên dài hơn có thêm byte lưu trữ và gửi qua mạng; tên quá ngắn lại khó nhận diện owner trong hệ thống nhiều dịch vụ.

| Đại lượng | Đơn vị | Tác động | Cách kiểm soát |
|---|---|---|---|
| Độ dài tên key | Byte sau serialize | Byte lưu trữ, byte gửi lệnh, khả năng đọc log | Tên nhất quán, bỏ đoạn thừa, ID ngắn và ổn định |
| Số key khác nhau | Key | Metadata Redis, RAM, TTL, scanning | TTL, hạn mức, thiết kế cardinality |
| Kích thước value | Byte | RAM, băng thông, serialize/deserialize | Chỉ lưu dữ liệu cần thiết, giới hạn kích thước |
| Field/member mỗi Hash/Set/ZSet/List | Số phần tử | Big key, thao tác phức tạp | Cắt bớt item, quota, phân vùng |
| Lưu lượng tới một key | Lệnh/giây | Hot key, cạnh tranh tài nguyên | Phân tải, bucket, cache phù hợp |

Một key String có value một byte vẫn tiêu tốn bộ nhớ cho đối tượng và metadata. Ngược lại, một Hash có hàng triệu field tuy chỉ được tính là **một key** nhưng vẫn có thể sử dụng rất nhiều RAM.

### 1.1. Vì sao một byte key cũng đáng quan tâm khi quy mô lớn?

Giả sử hai quy ước key chênh nhau 24 byte. Với 8 triệu key đang tồn tại:

~~~text
24 byte/key × 8.000.000 key
= 192.000.000 byte
≈ 183 MiB
~~~

Đó chỉ là **chênh lệch byte tên key trên lý thuyết**, chưa tính chi phí cấp phát bộ nhớ, value, expiry metadata, replication, allocator fragmentation và các cấu trúc nội bộ Redis. Bộ nhớ thực tế cần được đo.

Với 1.000 key, chênh lệch chỉ khoảng 24 KB. Không nên hy sinh tính rõ nghĩa hoặc tăng nguy cơ collision để tiết kiệm vài kilobyte.

### 1.2. Đừng nhầm số ký tự Java với số byte của Redis

Redis key là byte sequence. Nếu dùng `StringRedisTemplate` với UTF-8, tên chứa ký tự nhiều byte sẽ có kích thước khác `String.length()` trong Java.

~~~java
import java.nio.charset.StandardCharsets;

String key = "shop:prod:user:42";
int byteLength = key.getBytes(StandardCharsets.UTF_8).length;

System.out.println("Key bytes = " + byteLength);
~~~

`String.length()` đếm đơn vị UTF-16; không dùng nó làm con số byte cho key khi có Unicode. Với namespace, code và ID kỹ thuật, dùng ASCII nhất quán giúp dễ ước tính và xử lý.

Redis có giới hạn lý thuyết về chiều dài key rất lớn, nhưng đó không phải một mục tiêu thiết kế. Nên quy định **ngưỡng độ dài thực dụng trong ứng dụng** dựa vào loại key và số lượng dự kiến, chẳng hạn 128 byte với một nhóm key có thể lên đến hàng triệu bản ghi. Ngưỡng này chỉ là ví dụ chính sách, không phải giới hạn mặc định của Redis.

## 2. Quy ước tên key: đủ nghĩa, ổn định và có owner

Một mẫu dễ hiểu:

~~~text
<application>:<environment>:<domain>:<entity-id>[:<purpose>]
~~~

Ví dụ:

~~~text
shop:prod:product:42
shop:prod:cart:user:782
shop:prod:inventory:sku:K83Z
shop:prod:rate-limit:user:782
shop:prod:report:job:9e5d2c
~~~

Không cần áp dụng mọi tầng prefix cho mọi hệ thống. Một Redis deployment chỉ dành riêng cho ứng dụng và môi trường có thể không cần lặp lại tên ứng dụng trong từng key. Nhưng với Redis dùng chung, namespace giúp ngăn xung đột và dễ thống kê theo nhóm.

Các nguyên tắc quan trọng:

1. **Một thực thể, một cách tạo tên:** cùng đầu vào và cùng mục đích phải sinh cùng key.
2. **Có delimiter hoặc encoding rõ ràng:** tránh nối hai ID thành một chuỗi dễ collision.
3. **Owner xác định:** biết service/module nào tạo, đọc, cập nhật và xóa.
4. **Dùng ID ngắn, ổn định:** không nhét toàn bộ URL, JSON, câu truy vấn hoặc object vào key.
5. **Không lộ dữ liệu nhạy cảm:** tránh access token, mật khẩu, email, thông tin cá nhân trong tên key vì key có thể xuất hiện trong log hoặc công cụ quản trị.
6. **Không biến tên key theo mỗi request nếu không cần:** timestamp millisecond, UUID mỗi lần đọc, trace ID thường làm số key tăng nhanh.
7. **Có kế hoạch thay đổi schema key:** nếu đổi prefix/version, cần TTL hoặc migration để key cũ không tồn tại vĩnh viễn.

### 2.1. Tránh xung đột khi ghép thành phần

Nối trực tiếp hai số không có dấu phân cách:

~~~text
userId=12, productId=34 -> "1234"
userId=1, productId=234 -> "1234"
~~~

Hai cặp khác nhau tạo cùng key. Hãy chọn:

~~~text
shop:prod:user:12:product:34
shop:prod:user:1:product:234
~~~

Nếu thành phần chứa chính dấu `:`, hãy chuẩn hóa hoặc escape ID theo quy ước. Một schema thiếu phân định có thể ghi đè dữ liệu dù key rất ngắn.

### 2.2. Prefix dài có thực sự cần thiết?

So sánh:

~~~text
com.company.shopping.production.inventory.product.byId.42
shop:prod:inventory:product:42
~~~

Tên thứ hai thường đủ rõ. Nếu cùng một Redis instance chỉ phục vụ `inventory` ở production, có thể rút nữa. Nhưng `p:42` dễ bị lẫn với `payment:42` hoặc `promotion:42` trong ứng dụng lớn.

Nguyên tắc: **giảm phần lặp vô ích trước, giữ lại những phần phân biệt ý nghĩa và trách nhiệm**.

## 3. Khi đầu vào là URL, truy vấn hoặc chuỗi rất dài

Giả sử cần cache kết quả tìm kiếm theo bộ lọc người dùng:

~~~text
shop:prod:search:category=book&sort=price&brand=...&filters=...
~~~

Nếu key chứa nguyên URL/query, độ dài có thể lên đến hàng nghìn byte, có nguy cơ chứa thông tin nhạy cảm và nhiều chuỗi tương đương có thể cho ra nhiều key:

~~~text
?sort=price&category=book
?category=book&sort=price
~~~

Khi ý nghĩa hai truy vấn là một, cần **chuẩn hóa đầu vào** trước khi sinh key: thống nhất thứ tự parameter, casing theo quy tắc, encoding, default value và cách biểu diễn tập filter.

Với chuỗi chuẩn hóa vẫn dài, có thể tính digest:

~~~text
shop:prod:search-result:<sha256-hex>
~~~

Ví dụ Java 17+:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class RedisKeys {

    private RedisKeys() {}

    public static String searchResult(String canonicalQuery) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(canonicalQuery.getBytes(StandardCharsets.UTF_8));
            return "shop:prod:search-result:"
                    + HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

Digest SHA-256 dạng hex dài 64 ký tự ASCII. Với URL dài vài kilobyte, đây có thể là bước giảm độ dài đáng kể; với ID chỉ 5–10 ký tự, đổi ID sang digest thường làm key **dài hơn**. Không nên băm mọi key một cách máy móc.

Digest không phải mã hóa bí mật; nếu nguồn đầu vào có không gian giá trị nhỏ, người khác có thể đoán và tính lại digest. Tránh đưa dữ liệu bí mật vào schema khóa và kiểm soát quyền truy cập Redis riêng.

Rút gọn digest quá mức làm tăng nguy cơ collision; đánh giá xác suất collision theo **số key tối đa có thể sinh trong toàn bộ vòng đời**, không chỉ một phiên thử nghiệm nhỏ.

## 4. Key cardinality: số key sẽ tăng đến mức nào?

Điều đáng lo ngại thường không phải key dài 50 byte mà là **mỗi hành vi người dùng tạo một key mới**.

Giả sử:

~~~text
200.000 user hoạt động
× 50 lượt xem/ngày
= 10.000.000 lượt xem/ngày
~~~

Nếu lưu một key cho mỗi lượt xem trong 30 ngày:

~~~text
10.000.000 × 30 = 300.000.000 key đồng thời
~~~

Đây là ước lượng khi key độc nhất, tốc độ ổn định và TTL đúng 30 ngày. Chỉ tên key 30 byte đã tạo hàng gigabyte byte key; còn value và metadata có thể chiếm nhiều hơn.

Nếu yêu cầu thực tế chỉ là sản phẩm xem gần nhất, ta có thể dùng:

~~~text
shop:prod:user:last-viewed:782
~~~

và ghi đè value cho cùng user. Thay vì key mới mỗi sự kiện, số key gần với số user có dữ liệu gần đây.

### 4.1. Công thức dự trù số key có TTL

~~~text
Số key đang sống xấp xỉ
= tốc độ tạo key độc nhất/giây × thời gian tồn tại trung bình (giây)
~~~

Ví dụ 500 key mới/giây, TTL 1 giờ:

~~~text
500 × 3600 = 1.800.000 key
~~~

Đây là công thức dự báo với tốc độ gần ổn định. Nếu cùng key được ghi đè nhiều lần hoặc TTL được gia hạn, số key và thời gian sống hiệu dụng sẽ khác.

Không có TTL, mô hình tăng trưởng:

~~~text
Key cuối kỳ
= key đầu kỳ + key mới được tạo - key đã xóa
~~~

Nếu luôn có key mới mà hầu như không xóa, keyspace tăng theo thời gian. Dùng Redis cùng `maxmemory` không biến sự tăng trưởng đó thành một chính sách vòng đời dữ liệu đúng đắn.

### 4.2. Cardinality là tích của nhiều chiều

Một key:

~~~text
shop:prod:tenant:<tenant>:user:<user>:report:<report-id>:day:<date>
~~~

Có thể biến thiên theo tenant, user, report và day. Ví dụ trần lý thuyết:

~~~text
100 tenant × 20.000 user/tenant × 40 report/user × 30 day
= 2.400.000.000 tổ hợp
~~~

Không phải mọi tổ hợp đều tồn tại đồng thời; tuy nhiên phép tính giúp nhận ra mức độ bùng nổ nếu hệ thống tạo key cho từng tổ hợp. Thêm một chiều `requestId`, `deviceId` hoặc timestamp có thể biến một mô hình vốn ổn định thành keyspace tăng không giới hạn.

Khi thiết kế, hỏi: **thành phần này thật sự cần nằm trong tên key, hay có thể lưu dưới dạng field/member, bucket hoặc value?**

## 5. TTL và chính sách xóa: giới hạn thời gian sống của key

Với dữ liệu tạm, TTL cần là một phần của API ghi ngay từ đầu.

~~~java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TemporaryMarkerStore {

    private static final Duration TTL = Duration.ofMinutes(15);

    private final StringRedisTemplate redis;

    public TemporaryMarkerStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String requestId) {
        String key = "shop:prod:processed-request:" + requestId;
        redis.opsForValue().set(key, "1", TTL);
    }
}
~~~

Lệnh `set(key, value, timeout)` đặt value và TTL cùng thao tác, tránh khoảng thời gian giữa hai lệnh `SET` rồi `EXPIRE` mà key có thể tồn tại không có TTL nếu tiến trình lỗi. Nhưng ví dụ trên ghi đè marker, nên **chưa tự bảo đảm chống xử lý trùng**.

Khi cần chỉ tạo key nếu chưa có:

~~~java
public boolean markIfAbsent(String requestId) {
    String key = "shop:prod:processed-request:" + requestId;

    Boolean created = redis.opsForValue()
            .setIfAbsent(key, "1", Duration.ofMinutes(15));

    return Boolean.TRUE.equals(created);
}
~~~

Đây là ví dụ phương thức của class có field `StringRedisTemplate redis` ở trên. `setIfAbsent` kết hợp điều kiện chưa tồn tại và TTL ở Redis. Tuy vậy, marker thành công trước khi nghiệp vụ thực thi xong có thể chặn retry sau sự cố. Những hệ thống cần idempotency thật sự phải thiết kế trạng thái, recovery và tính nhất quán với transaction nghiệp vụ.

### 5.1. TTL phải theo ý nghĩa dữ liệu

| Loại key | Chính sách vòng đời |
|---|---|
| Cache kết quả có thể tái tạo | TTL theo mức cũ có thể chấp nhận, invalidation khi nguồn dữ liệu đổi |
| Rate-limit counter theo cửa sổ | TTL phù hợp độ dài cửa sổ và biên cho xử lý trễ |
| Marker xử lý request | TTL theo thời hạn retry/idempotency nghiệp vụ |
| OTP hoặc token tạm | TTL ngắn, giới hạn lượt sử dụng và tiêu hủy khi hoàn tất |
| Kết quả job tạm | TTL theo thời gian người dùng cần tải kết quả |
| Session | Để Spring Session quản lý session inactivity/expiration |
| Dữ liệu nguồn quan trọng | Không gắn TTL tùy tiện; xác định rõ khả năng phục hồi |

**Không phải key nào cũng nên có TTL.** Nhưng key không có TTL phải có lý do, owner và quy trình xóa khi dữ liệu hết giá trị.

### 5.2. Gia hạn TTL có thể khiến key không bao giờ hết hạn

Nếu mỗi lần user truy cập, ứng dụng lại đặt TTL 30 ngày cho cùng key, key có thể tồn tại mãi nếu user hoạt động đều đặn. Phân biệt:

- **Absolute TTL**: thời hạn tính từ lần tạo; cập nhật không gia hạn.
- **Sliding TTL**: hoạt động mới gia hạn thời hạn.
- **Hạn theo sự kiện**: xóa sau khi đơn hàng đóng, campaign kết thúc hoặc job đã được xử lý.

Sliding TTL hợp lý với một số trạng thái phiên, nhưng không phù hợp với mọi key audit/idempotency. Chọn có chủ đích.

### 5.3. TTL không phải hạn mức cardinality tuyệt đối

Với TTL 60 phút và 500 key mới/giây, trạng thái ổn định khoảng 1,8 triệu key. Nếu lưu lượng tăng đột ngột lên 5.000 key/giây, số key đồng thời có thể tăng lên 18 triệu. Vẫn cần **rate limit, quota, backpressure và ngân sách bộ nhớ**.

## 6. Khi nào dùng Hash để giảm số key?

Thay vì một key cho mỗi thuộc tính:

~~~text
shop:prod:user:42:name   -> An
shop:prod:user:42:locale -> vi
shop:prod:user:42:theme  -> dark
~~~

ta có thể tạo một Hash:

~~~text
shop:prod:user:42
    name   = An
    locale = vi
    theme  = dark
~~~

Redis Hash có thể giảm số lượng key ngoài cùng và metadata tương ứng. Với Hash nhỏ, Redis có thể sử dụng representation tối ưu. Tuy nhiên, mức tiết kiệm phụ thuộc kích thước field/value, ngưỡng encoding của Redis và workload.

Ví dụ Spring Data Redis:

~~~java
import java.util.Map;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class UserPreferenceStore {

    private final StringRedisTemplate redis;

    public UserPreferenceStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(long userId, String locale, String theme) {
        String key = "shop:prod:user-preferences:" + userId;

        redis.opsForHash().putAll(
                key,
                Map.of("locale", locale, "theme", theme)
        );
    }

    public Object getLocale(long userId) {
        return redis.opsForHash().get(
                "shop:prod:user-preferences:" + userId,
                "locale"
        );
    }
}
~~~

Các field trong cùng Hash thường chia sẻ **TTL ở cấp key**; việc muốn field A hết hạn sau 5 phút và field B sau 7 ngày cần thiết kế phù hợp với tính năng Redis/phiên bản đang sử dụng, hoặc dùng key riêng và các cơ chế kiểm soát khác.

**Gom vào Hash phù hợp khi** nhiều thuộc tính của cùng entity có vòng đời tương tự, số field có giới hạn và thường được truy cập cùng nhau.

**Không phù hợp khi** gom toàn bộ user vào `shop:prod:all-users` không có giới hạn số field. Redis sẽ có một key rất lớn; số lượng key giảm nhưng tải và dữ liệu tập trung thành big key/hot key, có thể khó phân tải qua Redis Cluster.

## 7. Giới hạn số member trong List, Set và Sorted Set

Nếu yêu cầu giữ "100 sản phẩm xem gần đây của mỗi user", không cần tạo một key cho từng lượt xem. Có thể dùng **List riêng cho user** và trim.

~~~java
import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RecentProductStore {

    private final StringRedisTemplate redis;

    public RecentProductStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void record(long userId, long productId) {
        String key = "shop:prod:user:recent-products:" + userId;

        redis.opsForList().leftPush(key, Long.toString(productId));
        redis.opsForList().trim(key, 0, 99);
        redis.expire(key, Duration.ofDays(14));
    }

    public List<String> latest(long userId) {
        return redis.opsForList().range(
                "shop:prod:user:recent-products:" + userId, 0, 99
        );
    }
}
~~~

Ở trạng thái tuần tự, chỉ giữ tối đa 100 phần tử gần nhất. Nhưng `leftPush`, `trim` và `expire` là ba lệnh riêng. Khi nhiều request đồng thời, có thể có trạng thái trung gian hoặc thứ tự khác dự kiến. Nếu cần **nguyên tử**, có thể gói thao tác trong Lua script trên cùng key, phù hợp cơ chế Redis Cluster.

Với yêu cầu không trùng item, ưu tiên Set hoặc Sorted Set tùy ý nghĩa nghiệp vụ. Với Sorted Set cần giới hạn member bằng chính sách trim; nếu không, chỉ chuyển vấn đề từ **rất nhiều key** sang **một key có vô số member**.

| Dữ liệu cần giữ | Mô hình tham khảo | Giới hạn quan trọng |
|---|---|---|
| Giá trị hiện tại mỗi user | Một String hoặc Hash/user | Số user, TTL |
| 100 sự kiện gần nhất | Một List/user | Tối đa 100 item, TTL |
| Danh sách item duy nhất gần nhất | Sorted Set/user | Số member, score/thứ tự |
| Counter theo product | String/product | Số product, cleanup khi xóa product |
| Tổng lượt xem theo phút | Bucket theo phút | Số bucket đang sống, thời gian giữ |
| Hàng đợi công việc | List/Stream theo thiết kế | Độ dài queue, ack, cleanup, retention |

## 8. Bucket theo thời gian để tránh key mỗi sự kiện

Không cần thiết phải ghi:

~~~text
shop:prod:pageview:2026-11-12T15:30:01.124
shop:prod:pageview:2026-11-12T15:30:01.125
shop:prod:pageview:2026-11-12T15:30:01.126
...
~~~

nếu nghiệp vụ chỉ cần số lượt xem theo phút. Có thể dùng:

~~~text
shop:prod:pageviews:2026-11-12T15:30 -> 128
shop:prod:pageviews:2026-11-12T15:31 -> 135
~~~

hoặc một Hash cho ngày, field là phút:

~~~text
shop:prod:pageviews:2026-11-12
    "15:30" -> 128
    "15:31" -> 135
~~~

Với retention 7 ngày và bucket 1 phút:

~~~text
7 ngày × 24 giờ × 60 phút = 10.080 bucket
~~~

Đây là số bucket cho **một loại metric không phân thêm nhiều chiều**. Nếu tạo bucket riêng theo 100.000 product, số tổ hợp tối đa có thể tăng mạnh. Cần cân nhắc tính thưa của dữ liệu, chỉ tạo key khi có traffic và quy tắc retention.

Bucket đã đóng thường không cần gia hạn TTL mỗi lần được đọc. Nếu sự kiện đến trễ, định nghĩa rõ có ghi vào bucket cũ, ghi bù qua kho dữ liệu dài hạn hay bỏ qua.

## 9. Không dùng Redis maxmemory làm giải pháp duy nhất

Redis có thể cấu hình:

~~~conf
maxmemory 2gb
maxmemory-policy allkeys-lru
~~~

Khi đạt giới hạn và chính sách yêu cầu eviction, Redis có thể loại key để lấy chỗ cho dữ liệu mới. Nhưng eviction:

- Không tự hiểu **hạn mức từng tenant hoặc từng tính năng**.
- Có thể loại cả key quan trọng nếu chính sách cho phép.
- Không bảo đảm cache hit rate ổn định khi keyspace tăng.
- Không thay thế TTL, cleanup và capacity planning.
- Không giải quyết một big key hay một hot key bị thiết kế sai.

Nếu chung Redis server chứa cache có thể tái tạo và trạng thái nghiệp vụ không được phép mất, cần đánh giá chiến lược eviction và độ sẵn sàng thật cẩn thận. Khi các mục đích có yêu cầu khác biệt lớn, có thể tách Redis deployment.

### 9.1. Quota số key chính xác khác đo đếm định kỳ

Giả sử mỗi tenant được giữ tối đa 500 job tạm. Nếu hai request cùng làm:

~~~text
A: đếm được 499 job
B: đếm được 499 job
A: tạo job mới
B: tạo job mới
Kết quả: 501 job
~~~

Cách `SCAN` rồi `SET` không nguyên tử. Nếu quota phải chính xác, cần state/membership/quota được cập nhật **nguyên tử** cùng quyết định tạo dữ liệu; có thể dùng Lua trên các key cùng slot với Redis Cluster. Cũng phải xử lý đồng bộ state khi TTL xóa key job, retry, cleanup và lỗi sau timeout. Counter quota không được tự giả định khớp với số key thực tế nếu các thao tác xóa/hết hạn diễn ra độc lập.

Nếu chỉ muốn **cảnh báo vận hành**, số liệu lấy định kỳ theo nhóm key có thể đủ mà không cần khóa mọi request bằng giao thức quota phức tạp.

## 10. Đặc điểm của Spring Data Redis làm thay đổi độ dài và số key

### 10.1. Serializer quyết định byte key thực tế

`StringRedisTemplate` dùng serializer dành cho chuỗi. Khi gọi:

~~~java
redis.opsForValue().set("shop:prod:product:42", "active");
~~~

key trên Redis được mã hóa theo cơ chế chuỗi (thường UTF-8).

Với `RedisTemplate<K,V>`, key serializer có thể là JDK serialization hoặc serializer tùy cấu hình. **Không giả định** một key trong Java nhìn giống `shop:prod:product:42` thì byte trên Redis cũng giống chuỗi ASCII này.

Ví dụ cấu hình template với String key:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisTemplateConfig {

    @Bean
    RedisTemplate<String, byte[]> byteValueRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, byte[]> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(RedisSerializer.byteArray());
        template.afterPropertiesSet();
        return template;
    }
}
~~~

Ở ví dụ, key là String và value là byte array. Việc chuyển serializer trên hệ thống đang có dữ liệu phải có kế hoạch tương thích hoặc migration để đọc được key/value cũ.

### 10.2. Spring Cache tạo key dựa vào phương thức và tham số

~~~java
@Cacheable(cacheNames = "products", key = "#id")
public ProductView getProduct(Long id) {
    // Truy vấn dữ liệu nguồn
}
~~~

Một entry có thể được lưu dưới tên gần như:

~~~text
products::42
~~~

với prefix mặc định của Redis Cache trong một số cấu hình phổ biến. Cache cho nhiều cách truy vấn cùng product có thể tạo nhiều entry:

~~~text
products::42
productsBySku::K83Z
featuredProducts::42
~~~

Vì thế cardinality của cache phụ thuộc **số tổ hợp tham số và cache name**, không chỉ số product.

Với các query có filter, sort, page, locale và user ID, số tổ hợp có thể rất lớn và cache hit rate thấp. Đôi khi tối ưu đúng là **không cache các truy vấn hiếm gặp**, thay vì chỉ rút ngắn key.

Redis Cache có cấu hình TTL qua `RedisCacheManager` hoặc thuộc tính Spring Boot như:

~~~yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
~~~

TTL giới hạn vòng đời entry nhưng không bảo đảm số entry đồng thời nằm dưới một quota nếu tốc độ tạo cao.

### 10.3. Spring Session và Redis Repository có thể sinh key phụ

Spring Session quản lý key session và tùy implementation có thể dùng key hoặc index hỗ trợ expiration. Spring Data Redis Repository với `@RedisHash` có thể duy trì key cho entity, index hoặc expiration metadata tùy cấu hình.

Do đó:

~~~text
Số entity/session nghiệp vụ ≠ luôn bằng số Redis key thực tế
~~~

Không tự xóa các key nội bộ do framework quản lý vì thấy tên dài hay số lượng nhiều. Hãy kiểm soát số session, inactivity timeout, kích thước session attribute; với Repository, cân nhắc nhu cầu index và chính sách vòng đời entity.

## 11. Redis Cluster: thiết kế key theo slot

Trong Redis Cluster, key được phân vào **16.384 hash slot** rồi chia cho nhiều primary. Key bình thường như:

~~~text
shop:prod:product:42
shop:prod:product:43
~~~

có thể rơi vào các slot khác nhau.

Nếu một lệnh hoặc Lua script cần nhiều key ở cùng slot, dùng hash tag hợp lệ:

~~~text
shop:prod:cart:{user42}:items
shop:prod:cart:{user42}:summary
~~~

Hai key trên dùng hash tag `{user42}` và cùng slot.

**Không tạo mọi key với cùng hash tag**:

~~~text
shop:{prod}:product:1
shop:{prod}:product:2
shop:{prod}:product:3
~~~

Tất cả sẽ vào cùng slot, có thể gây mất cân bằng tài nguyên và tạo hot slot. Prefix bình thường `shop:prod:` không phải vấn đề; cặp ngoặc nhọn dùng làm hash tag mới là yếu tố điều khiển slot.

Số key của toàn Cluster là tổng phân bố trên các primary; khi đo bằng lệnh theo node, cần biết node nào sở hữu slot. Một phép đo trên một node không tự đại diện toàn Cluster.

## 12. Quan sát số key, độ dài và bộ nhớ

### 12.1. Tổng số key và mức sử dụng tài nguyên

Trên Redis standalone:

~~~bash
redis-cli INFO keyspace
redis-cli DBSIZE
redis-cli INFO memory
redis-cli INFO stats
~~~

| Lệnh | Cung cấp | Giới hạn |
|---|---|---|
| `INFO keyspace` | Key và thông tin expiry theo logical DB | Không phân loại theo prefix |
| `DBSIZE` | Số key trong DB hiện tại | Không phải số key toàn Cluster |
| `INFO memory` | Used memory, fragmentation và thông tin RAM | Không cho biết ngay namespace nào tốn RAM |
| `INFO stats` | Counter như `expired_keys`, `evicted_keys`, cache hit/miss | Cần so sánh theo thời gian; không phải ảnh chụp chi tiết key |

Theo dõi xu hướng: **key count tăng liên tục**, `used_memory` tiệm cận budget, `evicted_keys` tăng hoặc TTL không còn phù hợp đều là tín hiệu cần điều tra.

### 12.2. Đo một key cụ thể

~~~bash
redis-cli TYPE shop:prod:product:42
redis-cli MEMORY USAGE shop:prod:product:42
redis-cli TTL shop:prod:product:42
redis-cli STRLEN shop:prod:product:42
~~~

- `TYPE` xác định String, Hash, List, Set, ZSet hoặc kiểu hỗ trợ khác.
- `MEMORY USAGE` ước tính RAM liên quan đến một key/value theo cơ chế Redis.
- `TTL` trả về giây còn lại; `-1` nghĩa là key tồn tại nhưng không có TTL, `-2` nghĩa là key không tồn tại.
- `STRLEN` trả độ dài **value String**, không phải chiều dài tên key.

Để tìm big key chứa nhiều phần tử:

~~~bash
redis-cli HLEN shop:prod:user-preferences:42
redis-cli LLEN shop:prod:user:recent-products:42
redis-cli SCARD shop:prod:active-users
redis-cli ZCARD shop:prod:leaderboard
~~~

Không xem số key đơn lẻ là thước đo bộ nhớ đầy đủ.

### 12.3. Quét key theo prefix bằng SCAN

Tránh gọi:

~~~bash
redis-cli KEYS 'shop:prod:*'
~~~

trên keyspace production lớn vì `KEYS` duyệt toàn bộ và có thể chặn Redis lâu. Thay vào đó, duyệt theo lô:

~~~bash
redis-cli --scan --pattern 'shop:prod:product:*'
~~~

hoặc gọi tương tác:

~~~text
SCAN 0 MATCH shop:prod:product:* COUNT 500
~~~

`SCAN` trả cursor và một batch key. Client lặp đến khi cursor trở lại `0`.

Những điểm phải nhớ:

- `COUNT 500` chỉ là gợi ý lượng công việc, không bảo đảm luôn trả đúng 500 key.
- Có thể trả **trùng** key giữa các vòng lặp; cần deduplicate nếu mục tiêu là danh sách key riêng biệt.
- Keyspace thay đổi liên tục nên không thể xem kết quả scan là snapshot nhất quán.
- Tổng một lượt duyệt vẫn phải đi qua lượng dữ liệu lớn; nên chạy quản trị theo batch, tránh quét toàn Redis mỗi request.
- Trong Redis Cluster, cần hiểu quét đang đi qua node/primary nào và thiết kế thu thập theo topology.

Redis CLI còn có chế độ quét thống kê như:

~~~bash
redis-cli --bigkeys
~~~

Tùy phiên bản công cụ, có thể có thêm chế độ quan sát bộ nhớ. Trước khi chạy trên production nhiều dữ liệu, đánh giá tác động và tốc độ quét.

## 13. Quét key bằng Spring Data Redis

`StringRedisTemplate` hỗ trợ `scan(ScanOptions)`:

~~~java
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class KeyInventoryService {

    private final StringRedisTemplate redis;

    public KeyInventoryService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long estimateProductKeyCount() {
        ScanOptions options = ScanOptions.scanOptions()
                .match("shop:prod:product:*")
                .count(500)
                .build();

        long count = 0;
        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext()) {
                cursor.next();
                count++;
            }
        }
        return count;
    }
}
~~~

Tên phương thức là `estimateProductKeyCount` vì số đếm này có thể bị ảnh hưởng bởi key trùng từ scan và keyspace thay đổi. Mẫu này phù hợp với một Redis standalone hoặc khi hiểu rõ phạm vi scan của connection đang dùng. Với Cluster, đừng giả định một cursor tự quét tất cả primary.

`Cursor` cần được đóng để giải phóng tài nguyên. Đây là công việc **batch/administration**, không dùng trực tiếp trong endpoint phổ biến cần trả lời nhanh.

Nếu cần thống kê chính xác và liên tục theo tenant/tính năng, thiết kế một index hoặc hệ thống metrics phù hợp ngay ở nơi tạo/xóa key, và xử lý tính nguyên tử khi đồng bộ quota.

## 14. Dự trù memory budget theo nhóm key

Một bảng dự báo minh họa:

| Nhóm key | Số key dự kiến | Value | TTL | Hành động khi vượt |
|---|---:|---|---|---|
| `shop:prod:product:*` | 300.000 | DTO | 30 phút | Giảm biến thể cache, xem hit rate |
| `shop:prod:processed-request:*` | 1.800.000 | Marker | 1 giờ | Giới hạn tốc độ marker, điều chỉnh TTL hợp lý |
| `shop:prod:user:recent-products:*` | 200.000 | List tối đa 100 ID | 14 ngày | Giới hạn item và số user hoạt động |
| `shop:prod:report:job:*` | 10.000 | JSON kết quả | 24 giờ | Quota job/tenant và cleanup |

Đây là **con số minh họa**, không phải khả năng định mức sẵn có của Redis.

Để ước tính RAM:

1. Xác định key schema, số key hiện hữu và số key cực đại.
2. Đo độ dài byte của key sau serializer, kích thước value và số phần tử của cấu trúc.
3. Dùng dữ liệu mẫu gần thực tế để đo `INFO memory` và `MEMORY USAGE`.
4. Tính thêm allocator overhead, fragmentation, replication, persistence và tải đỉnh.
5. Giám sát theo **node/primary** khi dùng Redis Cluster để phát hiện nơi phân bổ lệch.
6. Đặt cảnh báo sớm và có phương án giảm tốc độ tạo key hoặc dọn dữ liệu cũ.

Tối ưu thêm 15 byte/key không có nhiều ý nghĩa nếu mỗi value đang chứa hàng trăm kilobyte, hoặc một cache entry có hit rate gần bằng 0.

## 15. Quy trình thiết kế key cho một tính năng mới

Giả sử ứng dụng muốn cache kết quả tìm kiếm sản phẩm theo filter.

**Bước 1 — Xác định mục đích.** Kết quả được tái tạo từ DB nên có thể cache ngắn hạn; nếu cần dữ liệu tức thời sau cập nhật, phải có invalidation.

**Bước 2 — Thiết kế tên.** Chuẩn hóa filter/sort và tạo key ổn định. Dùng digest chỉ khi chuỗi tham số dài hoặc chứa nhiều tổ hợp khó quản lý.

**Bước 3 — Ước tính cardinality.** Có bao nhiêu tổ hợp filter thực sự được lặp lại? Có tham số ngẫu nhiên khiến cache key luôn mới không? Nếu hit rate thấp, có thể chỉ cache truy vấn phổ biến.

**Bước 4 — Đặt TTL và giới hạn size.** Chọn TTL theo mức dữ liệu cũ chấp nhận được; giới hạn size của payload và tránh lưu những kết quả khổng lồ.

**Bước 5 — Ước lượng ngân sách.** Lấy mẫu key/value và thử tải để đo memory footprint; tính cả tình huống cao điểm.

**Bước 6 — Bố trí giám sát.** Theo dõi key count, expired/evicted keys, used memory, cache hit rate, tốc độ tạo key và big key.

**Bước 7 — Xác định owner và kế hoạch cleanup.** Mỗi schema key phải có người chịu trách nhiệm vòng đời; khi đổi prefix, có kế hoạch xóa/để hết hạn dữ liệu cũ.

~~~text
             Dữ liệu mới cần lưu Redis
                        |
             Một key cho mỗi sự kiện?
                   /            \
                 Không           Có
                   |              |
              Key ổn định     Có thể gom thành
              theo entity     bucket/List/Stream?
                   |              |
                   +------+-------+
                          |
              Nhiều field cùng entity,
              cùng vòng đời/TTL?
                   /          \
                 Có           Không
                  |              |
              Xét Hash       Key riêng
                   \          /
                    +--------+
                        |
             Ước tính key count
             × key bytes × value bytes
                        |
               Có TTL hoặc cleanup?
                  /            \
                Có             Không
                 |               |
            Thiết lập TTL    Owner và cơ chế xóa
                 \               /
                  +-------------+
                        |
             Đo đạc, quota và cảnh báo
~~~

## 16. Những sai lầm thường gặp

### Sai lầm 1 — Tạo một key cho mỗi lần request

Request ID hoặc timestamp làm key gần như không bao giờ trùng. Nếu chỉ cần counter, state cuối hoặc dữ liệu tổng hợp, dùng key ổn định và giới hạn vòng đời.

### Sai lầm 2 — Rút key mất hết ý nghĩa

`p:42` không tự an toàn hơn `shop:prod:product:42`. Nếu các team cùng dùng Redis mà không có quy ước, nguy cơ ghi đè/xóa nhầm lớn hơn khoản tiết kiệm byte.

### Sai lầm 3 — Cho rằng một Hash khổng lồ tiết kiệm vô hạn

Số key ít nhưng value/field nhiều vẫn có thể gây big key, latency, khó backup hoặc cân bằng slot. Giới hạn member luôn là một phần của thiết kế.

### Sai lầm 4 — Không tính key do framework sinh ra

Spring Cache, Spring Session, Redis Repository có thể sinh key theo logic riêng, kể cả key phụ trợ. Phải đo keyspace thực tế, không chỉ số lệnh `StringRedisTemplate.set()` trong mã.

### Sai lầm 5 — Dựa hoàn toàn vào TTL

TTL vẫn cho phép rất nhiều key sống đồng thời nếu tốc độ ghi cao. Cần quota, rate limit và ngân sách bộ nhớ.

### Sai lầm 6 — Dùng Redis `KEYS` để đếm theo request

Việc duyệt toàn keyspace theo mỗi HTTP request có thể ảnh hưởng Redis. Dùng metrics/index hoặc quét batch để vận hành.

### Sai lầm 7 — Chỉ nhìn số key, không nhìn kích thước value

Một vài Hash, Stream hoặc Sorted Set rất lớn có thể tốn RAM hơn hàng trăm nghìn key String nhỏ. Đo cả key count, value size và số field/member.

### Sai lầm 8 — Coi prefix là bảo vệ tài nguyên

Prefix tổ chức keyspace, không tạo quota riêng, ACL riêng hay giới hạn RAM theo namespace. Cần thiết kế chính sách hạ tầng phù hợp.

### Sai lầm 9 — Dùng cùng một Cluster hash tag cho mọi key

`{prod}` trong mọi key đẩy tất cả vào cùng hash slot, làm mất lợi thế phân tải của Redis Cluster.

### Sai lầm 10 — Không quản lý thay đổi schema key

Nếu mỗi đợt deploy đổi prefix mà key cũ không hết hạn, các thế hệ key song song có thể làm tăng bộ nhớ dù logic hiện tại không còn đọc chúng.

## 17. Bài tập tự tính

**Bài 1.** Một hệ thống tạo 250 marker độc nhất mỗi giây, TTL 20 phút. Số marker tồn tại ở trạng thái ổn định xấp xỉ:

~~~text
250 × 20 × 60 = 300.000 key
~~~

Nếu tăng lên 1.000 marker/giây trong suốt 20 phút, lượng tạo mới trong giai đoạn đó có thể đạt 1,2 triệu key, chưa tính key cũ còn sống.

**Bài 2.** Hai schema tên key chênh 30 byte và có 100.000 key:

~~~text
30 × 100.000 = 3.000.000 byte ≈ 2,86 MiB
~~~

Trong trường hợp này, tính rõ nghĩa có thể quan trọng hơn vài MiB. Nếu số key lên 50 triệu, cần đo đạc và cân nhắc tối ưu lại prefix.

**Bài 3.** Mỗi user cần 50 product xem gần nhất trong 14 ngày; có 500.000 user hoạt động và 30 triệu lượt xem/ngày.

- Một key mỗi event trong 14 ngày có thể tạo khoảng **420 triệu key** nếu mỗi event độc nhất.
- Một List/ZSet cho mỗi user có thể dùng khoảng **500.000 key ngoài cùng**, nhưng cần giới hạn mỗi cấu trúc còn 50 phần tử và đặt TTL theo nghiệp vụ.
- Nếu thực sự cần lịch sử sự kiện dài hạn, Redis có thể giữ bản tóm tắt nhanh; hệ thống lưu sự kiện dài hạn chịu trách nhiệm dữ liệu đầy đủ.

## 18. Tổng kết lựa chọn

| Câu hỏi | Hướng quyết định |
|---|---|
| Key nên dài bao nhiêu? | Vừa đủ phân biệt ngữ nghĩa, namespace và owner; đo theo **byte**, không theo cảm giác |
| Có nên băm mọi key? | Không; chỉ hữu ích cho đầu vào dài hoặc có nhiều biểu diễn cần chuẩn hóa |
| Key có timestamp được không? | Được nếu dùng bucket hữu hạn và retention rõ; tránh timestamp cho mỗi event khi chỉ cần số liệu tổng |
| Nên dùng String hay Hash? | Dựa vào vòng đời, số field và pattern truy cập; Hash không được tăng vô hạn |
| Có nên đặt TTL cho tất cả? | Dữ liệu tạm cần TTL; dữ liệu bền vững cần owner và quy trình xóa rõ ràng |
| TTL đủ giới hạn RAM không? | Không; phải tính tốc độ tạo, value size, peak và quota |
| Cần đếm key bằng gì? | `INFO keyspace`, `DBSIZE`, `SCAN`, metrics theo loại và số liệu thực tế |
| `SCAN` có exact snapshot không? | Không bảo đảm khi keyspace thay đổi và có thể trả trùng key |
| Redis Cluster có thay đổi thiết kế key không? | Có; cần hiểu hash slot, hash tag, phân bố key và hot slot |
| Giảm số key có phải luôn tốt? | Không; có thể tạo big key/hot key nếu gom quá mức |

**Chọn độ dài khóa** giúp tránh lưu trữ byte không cần thiết mà vẫn giữ tính rõ ràng. **Kiểm soát số lượng khóa** giúp keyspace không phát triển ngoài khả năng RAM và vận hành. Trong Spring Data Redis, thiết kế key cần đi cùng serializer, TTL, cấu trúc dữ liệu, tốc độ tạo key, giới hạn nghiệp vụ và phương pháp đo đạc ngay từ khi phát triển tính năng.
