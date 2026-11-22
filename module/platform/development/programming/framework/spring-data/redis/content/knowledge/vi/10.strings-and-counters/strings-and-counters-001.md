# Ghi, đọc và thay thế giá trị chuỗi bằng ValueOperations

## 1. ValueOperations dùng để làm gì?

Trong Redis, kiểu dữ liệu **String** không chỉ dành cho văn bản. Một Redis String là một giá trị dạng byte sequence, có thể chứa tên người dùng, mã xác nhận, token, một bộ đếm biểu diễn bằng số hoặc dữ liệu đã tuần tự hóa thành JSON. Khi sử dụng Spring Data Redis, nhóm thao tác với Redis String được biểu diễn bằng interface **ValueOperations<K, V>**.

~~~java
ValueOperations<String, String> values = stringRedisTemplate.opsForValue();
~~~

**ValueOperations** không đại diện cho một collection trong Java. Nó là bộ API gửi các Redis command liên quan tới String, chẳng hạn:

| Phương thức Spring Data Redis | Ý nghĩa | Redis command tương ứng |
|---|---|---|
| **set(key, value)** | Ghi mới hoặc ghi đè | **SET** |
| **get(key)** | Đọc giá trị hiện tại | **GET** |
| **getAndSet(key, newValue)** | Lấy giá trị cũ và thay bằng giá trị mới trong một thao tác nguyên tử | **GETSET** |
| **setIfAbsent(key, value)** | Chỉ ghi nếu key chưa tồn tại | **SET ... NX** |
| **setIfPresent(key, value)** | Chỉ ghi nếu key đã tồn tại | **SET ... XX** |
| **set(key, value, duration)** | Ghi và đặt TTL trong cùng thao tác | **SET ... EX/PX** |
| **getAndDelete(key)** | Đọc giá trị và xóa key trong một thao tác | **GETDEL** |
| **multiGet(keys)** | Đọc nhiều key | **MGET** |
| **multiSet(values)** | Ghi nhiều cặp key/value | **MSET** |
| **append(key, suffix)** | Nối thêm nội dung dạng chuỗi | **APPEND** |
| **size(key)** | Lấy độ dài dữ liệu String tính theo byte | **STRLEN** |

Điểm chính cần nắm khi bắt đầu: **get() chỉ đọc; set() là thao tác ghi đè; getAndSet() vừa thay thế vừa lấy giá trị cũ trong cùng một lệnh Redis**. Các hành vi này khác nhau ở kết quả trả về, ảnh hưởng đến TTL và cách xử lý khi nhiều request cùng truy cập một key.

## 2. Luồng từ ứng dụng Java đến Redis

~~~text
Controller / Job / Message Consumer
                |
                v
         Application Service
                |
                v
        StringRedisTemplate
                |
                v
     ValueOperations<String, String>
                |
                v
      RedisConnectionFactory
                |
                v
         Lettuce / Jedis
                |
                v
         Redis server
                |
        SET / GET / GETSET ...
~~~

**StringRedisTemplate** là một biến thể của RedisTemplate được cấu hình để làm việc với key và value dạng chuỗi. Khi gọi **opsForValue()**, template cung cấp một đối tượng ValueOperations để thực hiện Redis String commands. Spring quản lý kết nối, serializer và chuyển đổi kết quả từ driver sang kiểu Java.

Ví dụ dữ liệu trong Redis:

~~~text
Key                     Value
----------------------------------------------
customer:42:name        "An"
settings:theme:42       "dark"
otp:register:4f9a       "615204"
metrics:page:home       "123"
~~~

Những giá trị trên có cùng Redis data type là **string**, dù ý nghĩa nghiệp vụ khác nhau. Đối với Redis, key là định danh của dữ liệu, còn value là nội dung được lưu. Quy ước key rõ ràng giúp tránh vô tình ghi đè dữ liệu của tính năng khác.

### StringRedisTemplate hay RedisTemplate?

~~~java
// Phù hợp cho key và value đều là chuỗi:
StringRedisTemplate stringRedisTemplate;

// Có thể làm việc với kiểu khác, tùy serialization context:
RedisTemplate<String, CustomerDto> customerRedisTemplate;
~~~

**ValueOperations<K, V>** phụ thuộc vào serializer đã cấu hình. Generic **V** là kiểu Java, còn Redis nhận bytes; một đối tượng Java có thể được chuyển thành JSON hoặc một định dạng khác rồi vẫn được lưu dưới dạng Redis String. Để học các thao tác ghi, đọc và thay thế chuỗi, **StringRedisTemplate** giúp kết quả dễ quan sát bằng **redis-cli** và tránh nhiễu do serializer tùy biến.

Không nên dùng một template với serializer A để ghi, rồi template khác với serializer B để đọc cùng key nếu chưa thống nhất định dạng dữ liệu.

## 3. Chuẩn bị Spring Boot

### 3.1. Dependency

Với Spring Boot dùng Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Starter Redis tích hợp Spring Data Redis và driver, phổ biến là Lettuce. Starter Web phục vụ ví dụ HTTP trong bài; một service không cung cấp HTTP API có thể không cần dependency web.

### 3.2. Kết nối Redis

Ví dụ Redis chạy local:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Trong trường hợp cấu hình hợp lệ và không có bean tùy biến xung đột, Spring Boot tạo **RedisConnectionFactory** và **StringRedisTemplate** để ứng dụng inject. Không cần tự tạo connection mới mỗi khi gọi ValueOperations.

Ở các môi trường triển khai khác, cần cấu hình hostname, xác thực, TLS, Sentinel/Cluster và timeout phù hợp. Không đưa credential thực tế vào repository hoặc ví dụ mã nguồn.

## 4. Ghi giá trị chuỗi với set()

Phương thức cơ bản:

~~~java
stringRedisTemplate.opsForValue().set("customer:42:name", "An");
~~~

Tương ứng về ý nghĩa với lệnh:

~~~redis
SET customer:42:name An
~~~

Nếu key **chưa tồn tại**, Redis tạo key mới với value **An**. Nếu key **đã tồn tại** và có Redis type tương thích với lệnh SET, Redis thay value bằng **An**. **SET có thể ghi đè key đang chứa kiểu dữ liệu khác**, vì vậy không nên dùng nhầm key vốn thuộc Redis hash, list hoặc set.

Một ví dụ theo thứ tự:

~~~redis
SET customer:42:name An
GET customer:42:name
# "An"

SET customer:42:name Binh
GET customer:42:name
# "Binh"
~~~

Sau lệnh SET thứ hai, giá trị **An** không còn nằm trong key đó. Redis không tự lưu phiên bản trước để ứng dụng gọi GET lại; nếu cần biết giá trị cũ trong lúc thay thế thì phải chọn một thao tác khác, chẳng hạn **getAndSet()**.

### set() có giá trị trả về gì?

Trong API ValueOperations imperative, **set(key, value)** có kiểu trả về **void**:

~~~java
ValueOperations<String, String> values =
    stringRedisTemplate.opsForValue();

values.set("app:notice", "Maintenance at 22:00");
~~~

Khi phương thức kết thúc bình thường, command đã nhận kết quả theo đường xử lý đồng bộ của client. Nếu Redis không khả dụng hoặc lệnh lỗi, Spring Data Redis có thể phát exception; việc **set() trả void** không có nghĩa lệnh không thể thất bại.

Một điểm khác biệt khi so sánh code Java với redis-cli: câu trả lời **OK** của Redis CLI thường không được truyền nguyên dạng thành String cho **ValueOperations.set()**.

## 5. Đọc giá trị với get()

~~~java
String name = stringRedisTemplate.opsForValue()
    .get("customer:42:name");
~~~

Trong redis-cli:

~~~redis
GET customer:42:name
~~~

**get()** trả về String nếu key có Redis String value hợp lệ với serializer. Nếu key không tồn tại, kết quả thông thường là **null**.

~~~java
String nickname = stringRedisTemplate.opsForValue()
    .get("customer:42:nickname");

if (nickname == null) {
    // Key không tồn tại: dùng mặc định hoặc báo không tìm thấy.
}
~~~

### Phân biệt null và chuỗi "null"

Ba trạng thái sau không giống nhau:

| Trạng thái Redis | get() trong Java |
|---|---|
| Key không tồn tại | **null** |
| Key chứa chuỗi có bốn ký tự **null** | String **"null"** |
| Key chứa chuỗi rỗng | String **""** |

Do đó, điều kiện **value == null** kiểm tra trường hợp không có kết quả, khác với **"null".equals(value)**. Không tự ý biến **null** thành chuỗi **"null"** để lưu vào Redis nếu đó không phải giá trị nghiệp vụ hợp lệ.

### Redis key có kiểu dữ liệu khác

Giả sử:

~~~redis
HSET customer:42 name An
GET customer:42
~~~

Lệnh GET với key thuộc Redis **hash** sẽ thất bại do sai loại dữ liệu, thường là **WRONGTYPE**; đây không phải tình huống key vắng mặt. Service cần phân biệt lỗi Redis với việc không tìm thấy key.

Nếu key tồn tại nhưng bytes không giải mã được bằng serializer đã cấu hình, ứng dụng cũng có thể gặp lỗi deserialization. Khi có nhiều ứng dụng dùng chung Redis, hãy thống nhất namespace, data type và serializer cho từng keyspace.

### Một phương thức đọc an toàn với Optional

~~~java
import java.util.Optional;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class DisplayNameService {
    private final StringRedisTemplate redis;

    public DisplayNameService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Optional<String> findName(String customerId) {
        String key = "customer:" + customerId + ":name";
        return Optional.ofNullable(redis.opsForValue().get(key));
    }
}
~~~

**Optional.empty()** ở ví dụ này biểu diễn key không tồn tại. Exception kết nối hoặc sai kiểu dữ liệu vẫn phải được xử lý riêng, không được mặc nhiên chuyển mọi lỗi thành “không tìm thấy”.

## 6. Thay thế giá trị và nhận giá trị cũ với getAndSet()

Nhiều bài toán yêu cầu **ghi giá trị mới đồng thời biết giá trị trước đó là gì**. Thực hiện hai lệnh riêng:

~~~java
String old = values.get(key);
values.set(key, newValue);
~~~

có thể tạo khoảng hở giữa GET và SET. Một request khác có thể thay đổi key sau khi request hiện tại đọc, khiến dữ liệu **old** không còn là giá trị ngay trước lần ghi của mình.

**ValueOperations.getAndSet()** giải quyết yêu cầu đọc giá trị cũ rồi thay bằng giá trị mới trong **một lệnh Redis nguyên tử**:

~~~java
ValueOperations<String, String> values = redis.opsForValue();

values.set("settings:theme:42", "light");

String previous = values.getAndSet("settings:theme:42", "dark");
// previous = "light"

String current = values.get("settings:theme:42");
// current = "dark"
~~~

Lệnh Redis tương ứng:

~~~redis
GETSET settings:theme:42 dark
~~~

Redis thực hiện việc lấy giá trị hiện tại và cập nhật giá trị mới trong cùng command. Không có command của client khác chen giữa hai công đoạn này trong lúc server thực thi command.

### getAndSet() khi key chưa tồn tại

~~~java
String before = values.getAndSet("settings:theme:new-user", "dark");
// before == null nếu key chưa tồn tại.

String after = values.get("settings:theme:new-user");
// after = "dark"
~~~

**getAndSet() vẫn tạo key và ghi value mới ngay cả khi key cũ không tồn tại**. Vì thế, việc kết quả cũ bằng null **không đồng nghĩa thao tác thay thế thất bại**.

### Những khác biệt quan trọng

| Tiêu chí | get() rồi set() | getAndSet() |
|---|---|---|
| Số Redis command | Hai | Một |
| Có trả về giá trị cũ? | Có, nhưng đọc tách biệt | Có, là giá trị cũ tại thời điểm thay thế |
| Có thể bị client khác chen giữa đọc và ghi? | Có | Không, trong phạm vi một command |
| Có tạo key nếu chưa tồn tại? | set() sẽ tạo | Có |
| Có bảo vệ điều kiện “chỉ thay nếu giá trị cũ là X”? | Không | Không |

Điểm cuối rất quan trọng: **getAndSet() là atomic replacement, không phải compare-and-set**. Nếu nghiệp vụ yêu cầu “chỉ ghi dark khi giá trị hiện tại đúng bằng light”, phải thực hiện kiểm tra điều kiện cùng thao tác ghi, chẳng hạn qua Lua script hoặc cơ chế đồng bộ phù hợp. Chỉ đọc giá trị cũ sau khi thay xong không ngăn được lần ghi không mong muốn.

## 7. Ghi có điều kiện: setIfAbsent() và setIfPresent()

Với thao tác **set()** thông thường, tồn tại hay không tồn tại key đều có thể bị ghi đè. Hai phương thức sau cho phép quyết định dựa trên **sự tồn tại của key** ngay tại Redis.

### 7.1. setIfAbsent(): chỉ tạo nếu chưa có

~~~java
Boolean created = values.setIfAbsent("config:site:language", "vi");

if (Boolean.TRUE.equals(created)) {
    // Key chưa tồn tại và lần gọi này đã tạo thành công.
} else if (Boolean.FALSE.equals(created)) {
    // Key đã tồn tại nên không bị ghi đè.
}
~~~

Ý nghĩa tương đương **SET ... NX**. Redis kiểm tra key chưa tồn tại và ghi trong cùng một command, tránh race condition của **EXISTS → SET**:

~~~text
Client A: EXISTS key -> false
Client B: EXISTS key -> false
Client A: SET key "A"
Client B: SET key "B"    // Ghi đè A ngoài ý muốn
~~~

**setIfAbsent()** giúp chỉ một client thắng khi nhiều client cùng cố tạo một key đang vắng mặt.

### 7.2. setIfPresent(): chỉ thay khi đã có

~~~java
Boolean replaced = values.setIfPresent(
    "config:site:language",
    "en"
);
~~~

Ý nghĩa tương đương **SET ... XX**:

- Nếu key đã tồn tại, Redis cập nhật value và trả về kết quả thành công.
- Nếu key chưa tồn tại, Redis không tạo key.

Tuy nhiên, **setIfPresent() không kiểm tra giá trị cũ**. Hai client vẫn có thể cùng ghi lên một key đã tồn tại và kết quả sau cùng phụ thuộc thứ tự lệnh tại Redis. Đây không phải cơ chế optimistic locking dựa trên version.

### 7.3. Xử lý kết quả Boolean

Các thao tác có điều kiện thông thường trả **Boolean.TRUE** hoặc **Boolean.FALSE**. Trong ngữ cảnh Redis pipeline hoặc transaction đang queue command, một số API có thể trả **null** trước khi kết quả thực thi thực tế có sẵn. Vì vậy code cần tuân thủ đúng ngữ cảnh sử dụng; ở lệnh đồng bộ bình thường, **Boolean.TRUE.equals(result)** tránh unboxing null không mong muốn.

## 8. TTL khi ghi và khi thay thế giá trị

**TTL (Time To Live)** là thời hạn tồn tại của key trước khi Redis coi key hết hạn. Đây là thuộc tính của key, không phải một phần ký tự trong String value.

### 8.1. Ghi kèm TTL bằng set(key, value, Duration)

~~~java
import java.time.Duration;

values.set(
    "otp:login:request-42",
    "851204",
    Duration.ofMinutes(5)
);
~~~

Redis ghi value và thiết lập TTL trong **cùng lệnh SET**. Đây là cách thích hợp để tránh khoảng hở giữa hai lệnh độc lập:

~~~redis
SET otp:login:request-42 851204
EXPIRE otp:login:request-42 300
~~~

Nếu ứng dụng dừng sau SET nhưng trước EXPIRE ở cách hai lệnh, key có thể tồn tại không có TTL. Truyền **Duration** khi SET giúp ranh giới ghi và đặt thời hạn rõ ràng hơn.

### 8.2. Tạo nếu vắng mặt và gắn TTL ngay

~~~java
Boolean created = values.setIfAbsent(
    "request:dedupe:order-918",
    "processing",
    Duration.ofMinutes(10)
);
~~~

Thao tác này kết hợp kiểm tra **chưa tồn tại**, ghi value và thiết lập thời hạn trong cùng command (tương đương **SET ... NX EX/PX**). Nếu key đã tồn tại, lần gọi không thay value và không tự gia hạn TTL của key cũ.

Lệnh phù hợp cho marker, giới hạn thao tác trùng hoặc tạo lease có thời hạn, nhưng các nghiệp vụ phức tạp vẫn cần xét trạng thái khi request thất bại, retry và owner token khi sử dụng khóa.

### 8.3. Ghi đè có làm mất TTL cũ?

Có. Theo semantics mặc định của Redis **SET**, khi ghi value mới vào một key đang tồn tại, TTL cũ thường bị loại bỏ nếu không chỉ định lựa chọn giữ TTL. Điều đó ảnh hưởng cả các thao tác dùng **SET** để ghi đè, bao gồm **getAndSet()** vốn sử dụng GETSET và các phương thức SET có điều kiện khi thực sự thay đổi value.

Ví dụ:

~~~redis
SET message:42 hello EX 60
TTL message:42
# Một số dương, tùy thời điểm thực thi.

SET message:42 world
TTL message:42
# -1: key tồn tại nhưng không có thời hạn hết hạn.
~~~

Nếu nghiệp vụ yêu cầu mỗi lần thay value sẽ bắt đầu lại thời hạn 5 phút, hãy sử dụng:

~~~java
values.set("message:42", "world", Duration.ofMinutes(5));
~~~

Nếu yêu cầu “thay value nhưng giữ nguyên TTL đang có”, phải dùng cơ chế hỗ trợ **KEEPTTL** hoặc logic server-side tương ứng, đồng thời xem phiên bản Redis và API client. **get() rồi set() rồi expire()** không cung cấp một thao tác nguyên tử và dễ phát sinh race condition.

### 8.4. Bảng tác động đến TTL

| Thao tác | Tác động đến key và TTL |
|---|---|
| **get(key)** | Chỉ đọc, không thay đổi TTL |
| **set(key, value)** | Ghi mới/ghi đè; SET mặc định bỏ TTL cũ |
| **set(key, value, Duration)** | Ghi mới/ghi đè và đặt TTL mới |
| **getAndSet(key, value)** | Thay value, lấy value cũ; TTL cũ bị xóa |
| **setIfAbsent(key, value, Duration)** | Khi tạo thành công: key có TTL mới; nếu không tạo: key cũ giữ nguyên |
| **setIfPresent(key, value, Duration)** | Khi key tồn tại: thay value và đặt TTL mới; nếu vắng: không tạo |
| **getAndDelete(key)** | Xóa key nên TTL không còn |

Khi debug TTL qua redis-cli:

~~~redis
TTL message:42
~~~

Thông thường kết quả **-2** nghĩa là key không tồn tại; **-1** là key đang tồn tại nhưng không có expiration. Giá trị không âm là thời gian còn lại tính bằng giây. Với thời hạn rất ngắn, **PTTL** cho độ phân giải mili giây.

## 9. Lấy rồi xóa bằng getAndDelete()

Một biến thể hữu ích là **getAndDelete(key)**, ánh xạ đến Redis **GETDEL** (cần Redis hỗ trợ command này).

~~~java
String code = values.getAndDelete("otp:login:request-42");
~~~

Kết quả là value ngay trước khi xóa, hoặc **null** nếu key không tồn tại. Lệnh đọc và xóa được Redis thực hiện trong một thao tác, phù hợp cho tình huống một giá trị chỉ nên bị lấy ra một lần.

So sánh:

~~~java
// Hai lệnh tách rời: hai request có thể cùng đọc code trước khi xóa.
String code = values.get(key);
redis.delete(key);
~~~

Với **getAndDelete()**, nếu nhiều client cùng đọc/xóa một key, chỉ một client có thể lấy được giá trị tồn tại trước khi key bị xóa; client tiếp theo sẽ thấy key không còn. Tuy nhiên “một lần lấy code” chưa tự đảm bảo cả quá trình xác thực và cấp quyền ở hệ thống khác đều hoàn thành đúng một lần. Nếu cần vừa **kiểm tra code đúng** vừa **xóa khi đúng**, phải đưa cả điều kiện và xóa vào một ranh giới nguyên tử phía Redis, chẳng hạn Lua script phù hợp.

## 10. Nhiều key: multiSet() và multiGet()

**ValueOperations** cũng hỗ trợ thao tác với nhiều Redis String key:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

Map<String, String> settings = new LinkedHashMap<>();
settings.put("site:title", "Java Learning");
settings.put("site:language", "vi");
settings.put("site:theme", "dark");

values.multiSet(settings);

List<String> result = values.multiGet(
    List.of("site:title", "site:language", "site:theme")
);
~~~

**multiSet()** có ý nghĩa tương ứng Redis **MSET**; **multiGet()** là Redis **MGET**. Kết quả multiGet thường tương ứng thứ tự key được yêu cầu; vị trí của key chưa tồn tại có thể chứa **null**. Cần chọn Collection có thứ tự rõ ràng khi kết quả phải ghép về các key đầu vào.

Chú ý khi thiết kế:

- **multiSet() không có TTL riêng cho từng key trong lời gọi này**. Nếu muốn các giá trị hết hạn theo thời gian nghiệp vụ, phải thiết kế cách ghi có TTL thích hợp.
- Trên một Redis instance, **MSET** là một Redis command; tuy nhiên một chuỗi lệnh MSET rồi EXPIRE cho từng key không phải toàn bộ một thao tác nguyên tử.
- Với **Redis Cluster**, các command nhiều key chịu ràng buộc hash slot. Phải thiết kế key cùng slot khi cần thực hiện MSET/MGET trong một command; đừng giả định các key nằm trên nhiều master luôn được Redis xử lý như một thao tác nguyên tử duy nhất.

Không dùng **multiGet()** để quét mọi key có chung prefix. Nó cần danh sách key đã biết; việc khám phá key thuộc nhu cầu khác, chẳng hạn scan với phạm vi và chiến lược phù hợp.

## 11. Các thao tác chuỗi khác cần biết

### 11.1. append(): nối nội dung

~~~java
values.set("document:42:notes", "Redis");

Integer lengthAfterAppend = values.append(
    "document:42:notes",
    " and Spring"
);
~~~

Lệnh Redis tương ứng **APPEND**. Value trở thành **Redis and Spring**. Giá trị trả về là độ dài chuỗi sau khi append theo cách Redis biểu diễn, tính theo **byte**, không nhất thiết bằng số ký tự Unicode Java.

**APPEND** nguyên tử đối với một command nối chuỗi. Nhưng dùng nó làm nhật ký vô hạn trong một key có thể khiến value tăng mãi; để lưu nhiều sự kiện có thứ tự và tiêu thụ riêng, hãy cân nhắc Redis Stream hoặc mô hình dữ liệu phù hợp.

### 11.2. size(): kích thước byte

~~~java
Long bytes = values.size("document:42:notes");
~~~

Lệnh Redis **STRLEN** đo số byte của String value. Với UTF-8, ký tự tiếng Việt có dấu có thể chiếm nhiều byte. Vì vậy:

~~~text
"abc"  -> 3 byte trong UTF-8
"đ"    -> nhiều hơn 1 byte trong UTF-8
~~~

Không dùng **size()** để áp dụng giới hạn số chữ hoặc số ký tự hiển thị cho giao diện người dùng. Với nghiệp vụ cần độ dài ký tự Unicode, nên xử lý theo quy tắc Java/Unicode ở tầng ứng dụng.

### 11.3. Đọc một đoạn với get(key, start, end)

~~~java
String prefix = values.get("document:42:notes", 0, 4);
~~~

Biến thể này sử dụng semantics tương ứng **GETRANGE**: offset bắt đầu và kết thúc là chỉ số **byte** và điểm cuối là **bao gồm**. Với chuỗi ASCII, khoảng **0..4** lấy năm byte đầu. Với Unicode UTF-8, cắt giữa một chuỗi nhiều byte có thể tạo dữ liệu không giải mã được như mong đợi.

### 11.4. Ghi vào offset với set(key, value, offset)

~~~java
values.set("fixed:record", "abcdef");
values.set("fixed:record", "ZZ", 2);

String after = values.get("fixed:record");
// abZZef
~~~

Đây là một thao tác tương ứng **SETRANGE** vào vị trí byte cụ thể. Nó có ích với dữ liệu có cấu trúc nhị phân hoặc ASCII được quản lý chặt; không nên sử dụng tùy tiện để thay một “ký tự thứ N” trong văn bản Unicode.

### 11.5. Chọn API theo thao tác

| Nhu cầu | Cách gọi | Đặc điểm |
|---|---|---|
| Ghi hoàn toàn nội dung mới | **set(key, value)** | Thay toàn bộ value |
| Ghi và giới hạn tuổi thọ | **set(key, value, Duration)** | Một lần ghi kèm TTL |
| Xem nội dung | **get(key)** | Không sửa dữ liệu |
| Thay nội dung đồng thời lấy bản cũ | **getAndSet(key, newValue)** | Nguyên tử trong một command |
| Lấy nội dung một lần rồi xóa | **getAndDelete(key)** | Nguyên tử trong một command |
| Thêm nội dung vào cuối | **append(key, text)** | Không cần GET rồi SET |
| Lấy độ dài Redis String | **size(key)** | Đếm byte |
| Cắt chuỗi theo byte | **get(key, from, to)** | Chú ý UTF-8 |
| Ghi vào offset byte | **set(key, value, offset)** | Chú ý định dạng dữ liệu |

## 12. Ví dụ service hoàn chỉnh: quản lý thông báo dạng String

Giả sử ứng dụng cần lưu một dòng thông báo ngắn theo mã định danh. Mục tiêu:

- Ghi hoặc ghi đè thông báo.
- Đọc thông báo hiện tại.
- Thay thông báo và biết nội dung trước đó.
- Tạo thông báo chỉ khi chưa tồn tại.
- Ghi có TTL để thông báo tạm tự hết hạn.

Ta đặt các thao tác Redis trong một service có trách nhiệm rõ ràng.

~~~java
package com.example.redis.service;

import java.time.Duration;
import java.util.Optional;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.stereotype.Service;

@Service
public class NoticeStore {
    private final ValueOperations<String, String> values;

    public NoticeStore(StringRedisTemplate redis) {
        this.values = redis.opsForValue();
    }

    private String keyFor(String noticeId) {
        if (noticeId == null || noticeId.isBlank()) {
            throw new IllegalArgumentException("Notice id is required");
        }
        return "notice:" + noticeId;
    }

    public void put(String noticeId, String text) {
        values.set(keyFor(noticeId), text);
    }

    public void putTemporary(
            String noticeId,
            String text,
            Duration ttl) {

        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        values.set(keyFor(noticeId), text, ttl);
    }

    public Optional<String> find(String noticeId) {
        return Optional.ofNullable(values.get(keyFor(noticeId)));
    }

    public Optional<String> replaceReturningOld(
            String noticeId,
            String newText) {
        return Optional.ofNullable(
            values.getAndSet(keyFor(noticeId), newText)
        );
    }

    public boolean createIfMissing(String noticeId, String text) {
        return Boolean.TRUE.equals(
            values.setIfAbsent(keyFor(noticeId), text)
        );
    }

    public boolean replaceIfExisting(String noticeId, String text) {
        return Boolean.TRUE.equals(
            values.setIfPresent(keyFor(noticeId), text)
        );
    }

    public Optional<String> takeAndDelete(String noticeId) {
        return Optional.ofNullable(
            values.getAndDelete(keyFor(noticeId))
        );
    }
}
~~~

### Dòng thực thi của ví dụ

~~~java
store.put("maintenance", "System available");

String now = store.find("maintenance").orElse("missing");
// System available

String old = store.replaceReturningOld(
    "maintenance", "Maintenance at 22:00"
).orElse("missing");
// System available

String updated = store.find("maintenance").orElse("missing");
// Maintenance at 22:00

boolean inserted = store.createIfMissing(
    "maintenance", "Another message"
);
// false vì key đã tồn tại.

String taken = store.takeAndDelete("maintenance").orElse("missing");
// Maintenance at 22:00

boolean existsAfter = store.find("maintenance").isPresent();
// false
~~~

Các lệnh trên minh họa sự khác nhau giữa **trả về giá trị mới**, **trả về giá trị cũ**, **trả về Boolean theo điều kiện tồn tại** và **đọc rồi xóa**. Biến **store** đại diện bean **NoticeStore** đã được Spring inject ở tầng gọi; các dòng này là ví dụ sử dụng chứ không phải một ứng dụng Java độc lập.

### Không biến Optional.empty() thành kết luận sai

Với **replaceReturningOld()**, Optional.empty() có nghĩa **giá trị cũ không tồn tại**; phương thức **getAndSet()** vẫn đã ghi giá trị mới. Nếu API muốn phân biệt rõ “created” và “replaced”, service có thể đặt kiểu kết quả nghiệp vụ diễn đạt chính xác hai tình huống; không nên chỉ nhìn kết quả Optional rồi tuyên bố lệnh không thành công.

Trong service thực tế, cần xác định chính sách kiểm tra text null/rỗng, kích thước payload, dữ liệu nhạy cảm, quyền truy cập và key ID trước khi lưu. Ví dụ để tập trung vào API ValueOperations nên chỉ kiểm tra những ràng buộc cơ bản về ID và TTL.

## 13. Ví dụ HTTP API sử dụng service

Controller không cần biết Redis command hoặc cấu hình connection:

~~~java
package com.example.redis.web;

import com.example.redis.service.NoticeStore;
import java.time.Duration;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/notices")
public class NoticeController {
    private final NoticeStore store;

    public NoticeController(NoticeStore store) {
        this.store = store;
    }

    @GetMapping("/{id}")
    public ResponseEntity<String> get(@PathVariable String id) {
        return ResponseEntity.of(store.find(id));
    }

    @PutMapping("/{id}")
    public ResponseEntity<Void> put(
            @PathVariable String id,
            @RequestBody String text) {
        store.putTemporary(id, text, Duration.ofMinutes(30));
        return ResponseEntity.noContent().build();
    }
}
~~~

Ở ví dụ này, **PUT** ghi đè thông báo và đặt lại TTL 30 phút; **GET** trả HTTP 404 khi key không còn. Cách ánh xạ này chỉ là lựa chọn API mẫu. Trong ứng dụng production, nên dùng DTO, validation, cơ chế xử lý exception và quy tắc phân quyền tương ứng.

Điểm kiến trúc: controller giao tiếp qua API nghiệp vụ **NoticeStore**, còn service quản lý key prefix, ValueOperations và semantics của TTL.

## 14. Tính nguyên tử và race condition khi đọc rồi ghi

Tính nguyên tử của một lệnh Redis là một lợi thế, nhưng không có nghĩa mọi chuỗi lệnh Java đều nguyên tử.

### Tình huống hai request cùng đọc rồi sửa

Giả sử value của **settings:theme:42** đang là **light**. Hai request chạy:

~~~java
String current = values.get("settings:theme:42");
String next = transform(current);
values.set("settings:theme:42", next);
~~~

**transform** là hàm nghiệp vụ minh họa. Redis có thể nhận lệnh theo thứ tự:

| Thời điểm | Request A | Request B | Value trong Redis |
|---|---|---|---|
| 1 | GET → light | | light |
| 2 | | GET → light | light |
| 3 | Tính value mới A | | light |
| 4 | | Tính value mới B | light |
| 5 | SET value A | | value A |
| 6 | | SET value B | value B |

Nếu cả hai request cần bảo tồn thay đổi của nhau, cập nhật của A có thể bị ghi đè và mất. **getAndSet()** bảo đảm lấy lại đúng giá trị cũ của lần thay thế tại Redis, nhưng vẫn **không tự chạy transform trên giá trị mới nhất theo điều kiện**.

Nếu yêu cầu là tăng bộ đếm, dùng **increment()** (Redis INCR) thay vì GET rồi parse, cộng và SET. Nếu yêu cầu là “chỉ thay khi version còn bằng X”, có thể dùng cơ chế optimistic locking (**WATCH + MULTI/EXEC**) hoặc Lua script/Redis Function để kiểm tra và thay đổi trong một lần thực thi phía Redis.

### Ghi có điều kiện không đồng nghĩa so sánh nội dung

**setIfPresent(key, value)** chỉ kiểm tra key có tồn tại, không kiểm tra giá trị hiện tại có đúng kỳ vọng.

**setIfAbsent(key, value)** chỉ kiểm tra key chưa tồn tại, không kiểm tra giá trị logic của dữ liệu.

**getAndSet(key, value)** không bảo đảm một logic “read-modify-write” phức tạp được thực hiện chính xác nếu phần tính toán vẫn ở Java và có request concurrent.

Do đó, trước khi chọn phương thức, cần đặt câu hỏi: *“Điều kiện của lệnh ghi chỉ là key tồn tại, hay còn phụ thuộc vào nội dung và phiên bản hiện tại?”*

## 15. Giá trị String và dữ liệu số

Redis vẫn dùng kiểu String để lưu nhiều bộ đếm. Ví dụ:

~~~redis
SET page:views:home 10
INCR page:views:home
GET page:views:home
# "11"
~~~

Trong Spring Data Redis:

~~~java
Long newCount = stringRedisTemplate.opsForValue()
    .increment("page:views:home");
~~~

Không nên:

~~~java
String raw = values.get("page:views:home");
long next = Long.parseLong(raw) + 1L;
values.set("page:views:home", Long.toString(next));
~~~

Hai request có thể cùng đọc giá trị cũ và cùng ghi một giá trị tăng giống nhau. **increment()** gói phép tăng trong một command nguyên tử ở Redis. Lệnh chỉ hợp lệ khi value có thể được hiểu như số nguyên phù hợp với command; nếu value chứa **abc**, Redis sẽ báo lỗi.

Đừng nhầm khái niệm String trong Redis với **String Java luôn là text thuần**. Redis String là byte sequence, nhưng lệnh tăng số áp dụng những quy tắc parse giá trị số của Redis; serializer và định dạng dữ liệu quyết định command nào thích hợp.

## 16. Lỗi và tình huống cần xử lý

### 16.1. Redis không khả dụng hoặc timeout

Tùy lỗi và driver, Spring Data Redis có thể phát exception thuộc hệ thống Spring DataAccessException với nguyên nhân là lỗi kết nối, timeout hoặc Redis server error. Không nên chuyển mọi lỗi thành **null**, vì **null từ get()** có ý nghĩa riêng là key không tồn tại.

Nếu một lệnh **SET**, **GETSET** hoặc **INCR** bị timeout ở phía client, chưa chắc Redis chưa thực thi nó. Khi áp dụng retry tự động cho lệnh ghi, cần xác định thao tác có idempotent hay không:

| Thao tác | Ảnh hưởng của retry |
|---|---|
| **GET** | Thường chỉ đọc lại; có thể nhận dữ liệu mới hơn nếu key thay đổi |
| **SET key fixedValue** | Ghi lại cùng value, nhưng có thể reset TTL hoặc ghi đè một thay đổi xen vào |
| **SET với TTL** | Có thể gia hạn thời điểm hết hạn khi retry |
| **GETSET** | Lần retry có thể nhận chính value đã ghi lần trước thay vì giá trị cũ ban đầu |
| **INCR** | Có nguy cơ tăng thêm một lần |
| **GETDEL** | Lần retry có thể không còn giá trị vì lệnh đầu đã xóa |

Kết quả từ client phải được diễn giải theo semantics của lệnh và điều kiện lỗi; “không nhận được phản hồi” không tự đồng nghĩa “Redis không thay đổi”.

### 16.2. Key hết hạn giữa hai câu lệnh

~~~java
String value = values.get(key);
Boolean exists = redis.hasKey(key);
~~~

Key có thể hết hạn hoặc bị client khác thay đổi giữa GET và EXISTS. Không thiết kế logic phụ thuộc vào việc hai lời gọi độc lập chắc chắn nhìn cùng một snapshot. Nếu cần kiểm tra và cập nhật đồng bộ, chọn một command thích hợp hoặc thao tác server-side nguyên tử.

### 16.3. Value có kích thước quá lớn

Redis String hỗ trợ dữ liệu nhị phân nhưng không phải nơi phù hợp để dồn vô hạn log, file hoặc nhiều bản ghi vào một key. Value lớn khiến serialization, network traffic và thao tác cập nhật tốn bộ nhớ/độ trễ hơn. Nên chọn cấu trúc dữ liệu phù hợp nếu cần truy xuất từng phần, truy vấn có cấu trúc hoặc luồng sự kiện.

### 16.4. Dùng serializer sai

Nếu một service ghi **notice:42** bằng **StringRedisTemplate**, rồi service khác đọc bằng template cấu hình JDK serialization, dữ liệu có thể không được giải mã đúng. Kiểu generic **ValueOperations<String, T>** không làm Redis tự biết T; việc chuyển đổi phụ thuộc serializer.

### 16.5. Thao tác Redis String lên key thuộc data type khác

**GET** trên hash/list/set sẽ trả lỗi **WRONGTYPE**. **SET** có thể thay thế key đang có loại khác, làm mất dữ liệu cũ. Phải đặt prefix và nguồn quản lý keyspace rõ ràng; không để Redis Repository dùng **@RedisHash** và StringRedisTemplate vô tình tranh cùng một key.

## 17. Quan sát bằng redis-cli

Sau khi chạy một service sử dụng StringRedisTemplate, có thể đối chiếu hành vi ở mức Redis command. Ví dụ thao tác trong một môi trường thử nghiệm:

~~~redis
SET lesson:message first
GET lesson:message
# "first"

GETSET lesson:message second
# "first"

GET lesson:message
# "second"

SET lesson:message third NX
# Không ghi vì key đã tồn tại.

SET lesson:message third XX
# Ghi thành công do key tồn tại.

SET lesson:temporary hello EX 120
TTL lesson:temporary
# Thời gian còn lại tính bằng giây.

GETDEL lesson:message
# "third"

GET lesson:message
# (nil), key không tồn tại.
~~~

Đây là command và ví dụ kết quả minh họa; redis-cli hiển thị phản hồi theo chế độ trình bày của client. Một số Redis deployment yêu cầu authentication/TLS hoặc giới hạn quyền đối với command.

Với trường hợp muốn biết chắc key đang có Redis data type nào, có thể kiểm tra:

~~~redis
TYPE lesson:temporary
# string
~~~

Với trường hợp muốn biết còn TTL hay không:

~~~redis
TTL lesson:temporary
~~~

Không đưa token, OTP thật hoặc giá trị nhạy cảm vào log khi debug; Redis command monitoring trực tiếp cũng có thể làm lộ payload trong môi trường không phù hợp.

## 18. Chọn phương thức theo yêu cầu nghiệp vụ

| Tình huống | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Lưu tên hiển thị mới, cho phép ghi đè | **set()** | Đơn giản và rõ thao tác ghi |
| Lưu thông báo tạm 15 phút | **set(key, value, Duration)** | Ghi kèm TTL trong một command |
| Đọc cấu hình hiện tại | **get()** | Truy xuất value, xử lý null khi vắng mặt |
| Thay cấu hình và ghi nhận nội dung trước đó | **getAndSet()** | Thay thế và trả lại value cũ nguyên tử |
| Tạo marker chỉ một lần nếu chưa có | **setIfAbsent()** | Điều kiện key chưa tồn tại được kiểm tra tại Redis |
| Chỉ thay value khi key hiện đang tồn tại | **setIfPresent()** | Không vô tình tạo key mới |
| Lấy mã một lần rồi loại bỏ | **getAndDelete()** | Đọc và xóa trong một command |
| Cần cộng số liệu đồng thời | **increment()/decrement()** | Không tạo race condition GET rồi SET |
| Cần cập nhật nếu nội dung/version khớp kỳ vọng | **Lua/WATCH** hoặc cơ chế atomic phù hợp | Điều kiện vượt quá sự tồn tại của key |
| Ghi/đọc nhiều key đã biết | **multiSet()/multiGet()** | Giảm số command; chú ý Cluster slot |

Trước khi viết code, nên xác định: key đã có thể tồn tại chưa, có được phép ghi đè không, value cũ có cần trả về không, TTL cần giữ hay đặt lại, có request concurrent không, và thao tác có thể bị retry sau timeout không. Những câu hỏi này giúp chọn đúng phương thức ValueOperations ngay từ đầu.

## 19. Bài tập áp dụng

### Bài 1 — Ghi và đọc tên

Viết một service ghi tên khách hàng vào key **customer:{id}:name**, sau đó đọc lại. Nếu key không có, trả về Optional.empty().

**Hướng giải:** dùng **set(key, value)** để ghi, **get(key)** để đọc và **Optional.ofNullable(...)** để diễn đạt sự vắng mặt. Chú ý validate ID và quy ước namespace.

### Bài 2 — Thay đổi nội dung và nhận bản cũ

Giá trị ban đầu của **settings:theme:42** là **light**. Thực hiện **getAndSet(key, "dark")**.

**Kết quả mong đợi:** lệnh trả về **light**, key sau đó chứa **dark**. Nếu key chưa từng tồn tại, kết quả cũ là null nhưng **dark** vẫn được ghi vào key.

### Bài 3 — Không ghi đè cấu hình đã có

Nhiều request cùng muốn tạo **system:startup:owner**. Làm sao để chỉ request đầu tiên thành công khi key chưa tồn tại?

**Hướng giải:** dùng **setIfAbsent()** để Redis kiểm tra điều kiện tồn tại và thực hiện ghi nguyên tử. Nếu marker phải tự hết hạn, chọn overload nhận **Duration**.

### Bài 4 — Bẫy TTL

Một key được tạo với TTL 10 phút, sau 2 phút code gọi **getAndSet()** để thay nội dung. Key có còn tự hết hạn sau 8 phút không?

**Đáp án:** Theo semantics mặc định của **GETSET**, TTL cũ bị loại bỏ. Nếu nghiệp vụ cần key tiếp tục hết hạn, phải thiết kế cách thay value giữ hoặc đặt TTL trong một thao tác phù hợp.

### Bài 5 — Hai request cùng tăng counter

Nếu hai request cùng đọc giá trị **9**, tính **10** rồi cùng SET **10**, kết quả sau hai request là bao nhiêu? Đổi sang API nào?

**Đáp án:** Có thể chỉ còn **10** dù có hai lần tăng được yêu cầu, vì cả hai đọc cùng giá trị cũ. Dùng **ValueOperations.increment()** để Redis tăng bộ đếm theo một command nguyên tử; kết quả sau hai lệnh là **11** nếu giá trị ban đầu là **9** và cả hai lệnh tăng thành công.

### Bài 6 — GETDEL và xác nhận OTP

Hai request đồng thời đọc OTP bằng **GET** rồi **DEL**. Vì sao cả hai có thể nhận cùng một OTP? Dùng **getAndDelete()** đã đủ để xác thực mọi OTP an toàn chưa?

**Đáp án:** GET và DEL là hai command tách biệt nên cả hai request có thể đọc cùng giá trị trước khi một request xóa. **getAndDelete()** bảo đảm chỉ một request lấy được giá trị còn tồn tại, nhưng nếu cần “so sánh OTP đầu vào, chỉ xóa nếu khớp và ghi nhận đã xác nhận” thì phải thiết kế toàn bộ điều kiện và thay đổi trạng thái trong một thao tác nguyên tử phù hợp.

## 20. Tổng kết

**ValueOperations** là API chính của Spring Data Redis cho kiểu dữ liệu Redis String. Với **StringRedisTemplate**, ứng dụng có thể làm việc trực tiếp với chuỗi mà không phải tự quản lý connection hoặc chuyển đổi bytes.

Ba thao tác nền tảng cần phân biệt rõ là **set()** để ghi hoặc ghi đè, **get()** để đọc và nhận null khi key không tồn tại, **getAndSet()** để thay giá trị đồng thời lấy giá trị cũ trong một lệnh nguyên tử. Các biến thể **setIfAbsent()**, **setIfPresent()** và overload có **Duration** giải quyết điều kiện tồn tại và thời hạn key; **getAndDelete()** giúp đọc/xóa trong một thao tác.

Khi đưa vào ứng dụng thực tế, phải xác định **semantics ghi đè, TTL, serialization và xử lý đồng thời**. Một lời gọi ValueOperations có thể nguyên tử ở cấp Redis command, nhưng một chuỗi nhiều lời gọi vẫn có thể bị request khác chen vào. Chọn API dựa trên quy tắc nghiệp vụ sẽ giúp dữ liệu nhất quán hơn và code dễ hiểu hơn.
