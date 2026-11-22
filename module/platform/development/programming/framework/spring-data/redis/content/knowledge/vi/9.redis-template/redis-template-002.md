# Chọn StringRedisTemplate cho dữ liệu chuỗi

## 1. Bối cảnh: cùng một Redis Server nhưng cách ghi từ Java có thể khác nhau

Trong Spring Boot, có nhiều cách giao tiếp với Redis: gọi trực tiếp Redis client, sử dụng **RedisTemplate**, sử dụng **StringRedisTemplate**, dùng Spring Cache hoặc Redis Repository. Khi chỉ cần đọc/ghi những giá trị dạng chuỗi như tên hiển thị, mã trạng thái, cấu hình ngắn hạn, token tham chiếu hoặc bộ đếm, **StringRedisTemplate** thường là điểm bắt đầu phù hợp.

Hãy xét một yêu cầu rất đơn giản: ứng dụng lưu dòng chữ **Spring Data Redis** với key **lesson:redis:title**, sau đó một người vận hành mở **redis-cli** để kiểm tra. Kỳ vọng của họ là:

~~~text
GET lesson:redis:title
"Spring Data Redis"
~~~

Để điều đó hoạt động, ứng dụng Java không chỉ cần biết địa chỉ Redis. Nó phải chuyển **key** và **value** thành dãy byte theo định dạng mà redis-cli và các ứng dụng khác có thể hiểu được. Đây là trách nhiệm của **serializer**.

StringRedisTemplate được thiết kế cho những ứng dụng mà tên key và dữ liệu cần lưu được biểu diễn bằng **String**. Nó chọn các serializer chuỗi thích hợp để những key/value này có dạng văn bản có thể quan sát và trao đổi dễ dàng.

Bài học tập trung vào việc **khi nào nên chọn StringRedisTemplate, vì sao cách chọn đó quan trọng và sử dụng nó thế nào trong Spring Data Redis**.

## 2. Redis String và Java String không phải cùng một khái niệm

Redis lưu các key và value dưới dạng byte. Một value trong Redis có thể là kiểu **String**, **Hash**, **List**, **Set**, **Sorted Set** hoặc nhiều cấu trúc dữ liệu khác. Còn **java.lang.String** là kiểu dữ liệu chuỗi trong JVM.

Ví dụ Java gọi:

~~~java
redis.opsForValue().set("lesson:color", "blue");
~~~

Với một StringRedisTemplate được cấu hình theo mặc định, Redis sẽ nhận một key có dạng văn bản **lesson:color** và một value **blue**; trên server, TYPE của key là **string**.

Nhưng một StringRedisTemplate cũng có thể thao tác **Redis Hash**:

~~~java
redis.opsForHash().put("lesson:product:42", "name", "Redis Guide");
~~~

Lúc này **lesson:product:42** là một key có kiểu **hash**, trong đó field **name** và value **Redis Guide** được biểu diễn bằng chuỗi. Nói cách khác:

**StringRedisTemplate quyết định cách mã hóa dữ liệu Java thành chuỗi bytes; nó không giới hạn Redis Server chỉ dùng cấu trúc String.**

| Khái niệm | Câu hỏi nó giải quyết |
| --- | --- |
| Java String | Giá trị trong ứng dụng Java được biểu diễn bằng kiểu nào? |
| StringRedisSerializer | Java String được chuyển thành bytes và ngược lại ra sao? |
| StringRedisTemplate | Các thao tác Redis sử dụng serializer chuỗi nào? |
| Redis data type | Value lưu trên Redis thuộc String, Hash, List, Set hay cấu trúc khác? |

## 3. StringRedisTemplate là gì?

**StringRedisTemplate** là một lớp chuyên dụng trong Spring Data Redis, kế thừa từ **RedisTemplate<String, String>**. Nó cung cấp các API thao tác quen thuộc của RedisTemplate nhưng cấu hình sẵn serializer cho việc làm việc với dữ liệu dạng chuỗi.

Những serializer cần quan tâm gồm:

- **Key serializer:** mã hóa tên key Redis.
- **Value serializer:** mã hóa value của những thao tác như SET/GET.
- **Hash key serializer:** mã hóa field bên trong Redis Hash.
- **Hash value serializer:** mã hóa value của từng field.

StringRedisTemplate sử dụng **StringRedisSerializer** cho các thành phần này trong cấu hình mặc định. StringRedisSerializer dùng mã hóa UTF-8 để chuyển đổi giữa Java String và bytes.

~~~mermaid
flowchart LR
    A["Java: String key/value"] --> B["StringRedisTemplate"]
    B --> C["StringRedisSerializer"]
    C --> D["UTF-8 bytes"]
    D --> E["Redis Server"]
    E --> F["redis-cli: GET / HGET"]
~~~

Đối với người mới học, lợi ích dễ thấy nhất là **khóa có tên dễ đọc trong redis-cli**, chẳng hạn:

~~~text
lesson:redis:welcome
profile:displayName:42
feature:checkout:enabled
counter:article:108
~~~

Khi đọc dữ liệu bằng công cụ ngoài Java, hệ thống ít gặp vấn đề do định dạng nhị phân bất ngờ.

### Khác biệt với RedisTemplate tổng quát

**RedisTemplate<K, V>** là lớp tổng quát, cho phép chọn kiểu Java cho key/value và cấu hình serializer riêng. Nó phù hợp khi cần lưu đối tượng, cấu trúc dữ liệu phức tạp hoặc quy tắc mã hóa khác với chuỗi thuần.

Trong những cấu hình RedisTemplate mặc định nhất định, serializer được dùng có thể là serializer của Java, làm tên key và value xuất hiện dưới dạng bytes khó đọc từ redis-cli. Điều này đặc biệt dễ gây nhầm lẫn khi developer sử dụng RedisTemplate theo cách mặc định mà chưa chủ động cấu hình serializer.

Tuy nhiên, **không nên khẳng định RedisTemplate luôn mã hóa bằng JDK serialization** trong mọi dự án. Một RedisTemplate đã được cấu hình StringRedisSerializer cho key và value có thể lưu dữ liệu chuỗi theo cách tương tự. Sự khác biệt thực tế phải được xác định từ **bean và cấu hình serializer đang được ứng dụng sử dụng**.

| Tiêu chí | StringRedisTemplate | RedisTemplate<K, V> |
| --- | --- | --- |
| Mục đích chính | Làm việc thuận tiện với key và dữ liệu chuỗi | Làm việc tổng quát với nhiều kiểu Java |
| Kiểu key/value trong khai báo | String/String | Tùy kiểu K/V |
| Serializer mặc định của biến thể | Dành cho String/UTF-8 | Phụ thuộc cách cấu hình template |
| Dễ xem bằng redis-cli | Có, khi key/value thực sự là chuỗi | Phụ thuộc serializer |
| Lưu DTO Java trực tiếp | Không tự chuyển DTO sang String | Có thể cấu hình serializer JSON hoặc loại khác |
| Redis Hash/List/Set/ZSet | Vẫn được hỗ trợ với dữ liệu chuỗi | Được hỗ trợ theo serializer đã chọn |
| Khi nào ưu tiên | Key và value tự nhiên là text, số dạng chuỗi, JSON text | Dữ liệu có kiểu Java phức tạp hoặc cần chiến lược serializer riêng |

## 4. Những bài toán phù hợp với StringRedisTemplate

### 4.1. Cấu hình và trạng thái nhỏ

Các giá trị như **enabled**, **disabled**, **pending**, URL ngắn, mã tham chiếu hoặc tên hiển thị vốn là chuỗi:

~~~text
feature:checkout:enabled -> "true"
order:status:81         -> "pending"
lesson:title:1          -> "Spring Data Redis"
~~~

StringRedisTemplate phù hợp vì service có thể đọc thẳng String và tự diễn giải nó theo quy ước nghiệp vụ. Tuy nhiên, nếu lưu boolean hoặc enum dưới dạng text, cần thống nhất cách biểu diễn, xử lý giá trị thiếu và giá trị lạ.

### 4.2. Dữ liệu có TTL

Ví dụ: một mã tham chiếu chỉ hợp lệ trong 5 phút; một trạng thái xử lý sống tối đa 30 giây; một kết quả tra cứu được phép cache trong 10 phút.

Redis cho phép đặt **TTL** ở cấp key. Với StringRedisTemplate, Spring Data Redis hỗ trợ đặt value và TTL trong một thao tác:

~~~java
redis.opsForValue().set(
        "lesson:temporary:reference:42",
        "READY",
        Duration.ofMinutes(5)
);
~~~

Sau khi hết TTL, key không còn tồn tại về mặt truy cập. Các lần GET sau đó trả null.

### 4.3. Bộ đếm dạng số nguyên

Redis có các lệnh **INCR**, **INCRBY**, **DECR** thực hiện số học trên những value kiểu Redis String có nội dung số nguyên hợp lệ. StringRedisTemplate giúp ứng dụng gọi các lệnh đó qua **opsForValue()**.

~~~java
Long views = redis.opsForValue()
        .increment("counter:article:108");
~~~

Lệnh tăng được Redis xử lý nguyên tử ở cấp **một lệnh**, nên phù hợp cho các bộ đếm thường xuyên được cập nhật đồng thời. Nếu bộ đếm đang chứa văn bản không biểu diễn số nguyên hợp lệ, lệnh sẽ báo lỗi.

### 4.4. Danh sách, tập hợp và Hash có field/value đều là chuỗi

Một nhóm khóa học:

~~~text
course:redis:students
~~~

có thể được lưu bằng Redis Set với member là các mã học viên dạng chuỗi. Một Redis Hash có thể lưu một tập field text như **name**, **status**, **category**. Khi mọi phần tử đều là chuỗi, StringRedisTemplate vẫn là lựa chọn tự nhiên dù Redis data type không phải String.

### 4.5. Payload JSON được quản lý như văn bản

Ứng dụng đôi khi cần lưu một JSON đã được serialize thành String:

~~~json
{"id":42,"name":"Spring Data Redis","active":true}
~~~

StringRedisTemplate có thể lưu JSON này như một giá trị Redis String. Nhưng Spring Data Redis **không tự hiểu schema của JSON** chỉ vì nó đang là text: code phải chủ động serialize/deserialize bằng Jackson hoặc thư viện tương ứng, quản lý phiên bản schema và lỗi định dạng.

Với nhiều DTO Java và yêu cầu type safety, một RedisTemplate được cấu hình JSON serializer thường dễ bảo trì hơn so với việc tự gọi ObjectMapper ở mọi vị trí.

## 5. Thiết lập Spring Boot để sử dụng StringRedisTemplate

### 5.1. Khai báo dependency

Ví dụ dự án dùng Spring Boot 3.x và Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Starter mang các thành phần cần thiết để sử dụng Spring Data Redis và Redis client phù hợp với cơ chế auto-configuration của Spring Boot. Với cấu hình thường gặp, Spring Boot sử dụng **Lettuce**.

### 5.2. Cấu hình kết nối

Giả sử Redis Server chạy tại **localhost:6379**:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

Lưu ý:

- Cài starter chỉ thêm thư viện; bạn vẫn cần một Redis Server thực sự đang chạy.
- Nếu chạy Spring Boot **trong container**, localhost thường là chính container ứng dụng chứ không phải Redis container. Hãy dùng DNS/service name tương ứng với hạ tầng.
- Nếu Redis có password, ACL hoặc TLS, bổ sung cấu hình bảo mật phù hợp. Không lưu mật khẩu thật vào source code.
- Thuộc tính ở trên dùng namespace **spring.data.redis** phổ biến trong Spring Boot 3.x. Với dự án cũ, cần kiểm tra namespace thuộc tính của phiên bản đang chạy.

Trong trường hợp auto-configuration mặc định và không có bean tùy chỉnh xung đột, Spring Boot có thể cung cấp **StringRedisTemplate** để inject trực tiếp:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisGreetingStore {

    private final StringRedisTemplate redis;

    public RedisGreetingStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveGreeting() {
        redis.opsForValue().set(
                "lesson:redis:greeting",
                "Xin chào Redis"
        );
    }

    public String readGreeting() {
        return redis.opsForValue().get("lesson:redis:greeting");
    }
}
~~~

Đây là thao tác **blocking** thông thường. Không cần tự mở socket, tạo RedisConnection hay gọi Redis AUTH trong từng method nghiệp vụ.

**Không cần bật @EnableCaching để dùng StringRedisTemplate trực tiếp.** @EnableCaching là một phần của Spring Cache abstraction, được dùng khi muốn kích hoạt cơ chế cache qua annotation như @Cacheable.

## 6. API cơ bản với dữ liệu chuỗi

### 6.1. Ghi và đọc một giá trị

~~~java
redis.opsForValue().set("lesson:redis:language", "vi");

String language = redis.opsForValue()
        .get("lesson:redis:language");
~~~

Ý nghĩa tương đương khi quan sát qua redis-cli:

~~~text
SET lesson:redis:language vi
GET lesson:redis:language
~~~

Nếu key chưa tồn tại, đã hết hạn hoặc bị xóa, **get(...) trả null**. Phân biệt null với String rỗng **""**: String rỗng vẫn là một giá trị tồn tại.

Khi muốn đọc nhiều key dạng String:

~~~java
List<String> values = redis.opsForValue().multiGet(
        List.of("lesson:redis:language", "lesson:redis:greeting")
);
~~~

Nếu hai key tồn tại, danh sách giá trị giữ thứ tự tương ứng với danh sách key. Với key không tồn tại, một phần tử trong danh sách có thể là null. Khi dùng pipeline/transaction, một số API có thể trả null tại thời điểm xếp lệnh; cần đọc hợp đồng phương thức tương ứng.

**Đối với Redis Cluster**, thao tác nhiều key trực tiếp như MGET có ràng buộc định tuyến theo slot. Đừng giả định mọi danh sách key tùy ý đều được hỗ trợ như trên Redis standalone; nếu cần thao tác chung nhiều key, hãy thiết kế key và hash tag theo yêu cầu của Cluster.

### 6.2. Ghi giá trị có TTL trong một lệnh

~~~java
import java.time.Duration;

redis.opsForValue().set(
        "lesson:redis:temporary:42",
        "processing",
        Duration.ofSeconds(90)
);
~~~

Khi sử dụng overload nhận Duration, thao tác ghi được gửi với thông tin expiration phù hợp. Đây là cách nên ưu tiên khi **giá trị cần được tạo cùng thời hạn sống**, vì tránh khoảng thời gian giữa SET và một lệnh EXPIRE riêng.

Redis-cli kiểm tra:

~~~text
GET lesson:redis:temporary:42
TTL lesson:redis:temporary:42
PTTL lesson:redis:temporary:42
~~~

Kết quả TTL có thể là:

| Giá trị | Ý nghĩa |
| --- | --- |
| Số không âm | Còn thời gian sống, tính bằng giây với TTL hoặc mili giây với PTTL. |
| -1 | Key tồn tại nhưng không có expiration. |
| -2 | Key không tồn tại. |

**Ghi đè bằng SET thông thường thường làm mất TTL cũ.** Ví dụ một key đang có TTL 60 giây mà bị SET bằng overload không có expiration có thể chuyển sang TTL = -1. Đây là lỗi dễ gặp trong code cache có nhiều đường cập nhật.

### 6.3. Ghi chỉ khi key chưa tồn tại

~~~java
Boolean reserved = redis.opsForValue().setIfAbsent(
        "lesson:redis:reservation:42",
        "reserved",
        Duration.ofSeconds(30)
);

boolean created = Boolean.TRUE.equals(reserved);
~~~

Điều này tương ứng về ý nghĩa với:

~~~text
SET lesson:redis:reservation:42 reserved NX EX 30
~~~

- Nếu key chưa tồn tại, Redis ghi giá trị kèm TTL và kết quả là true.
- Nếu key đã tồn tại, Redis không ghi đè; kết quả là false.
- Trong một số ngữ cảnh pipeline/transaction, kiểu trả về Boolean có thể là null trong lúc lệnh được xếp, nên dùng Boolean.TRUE.equals(...) sẽ tránh NullPointerException.

Đây là **nguyên tử ở cấp một lệnh SET có điều kiện**, hữu ích khi tạo marker hoặc giới hạn việc đặt một key mới. Tuy nhiên, một distributed lock hoàn chỉnh còn cần xác định chủ sở hữu, release an toàn, timeout, retry và xử lý lỗi; không nên gọi bất kỳ SET NX nào là lock hoàn chỉnh.

Một biến thể khác là **setIfPresent**, chỉ cập nhật khi key đã có. Hãy chọn theo quy tắc nghiệp vụ thay vì ghép GET rồi SET nếu tính đồng thời quan trọng.

### 6.4. Xóa, kiểm tra tồn tại và thời gian hết hạn

~~~java
Boolean exists = redis.hasKey("lesson:redis:temporary:42");

Long secondsLeft = redis.getExpire(
        "lesson:redis:temporary:42"
);

Boolean deleted = redis.delete(
        "lesson:redis:temporary:42"
);
~~~

Với kết quả thông thường ngoài pipeline/transaction:

- hasKey trả true nếu key tồn tại.
- getExpire trả thời gian hết hạn theo đơn vị mặc định của overload (giây với ví dụ trên); giá trị đặc biệt -1/-2 biểu thị không TTL hoặc key vắng mặt.
- delete trả true nếu đã xóa một key có tồn tại, false nếu không có key để xóa.

Phương thức **hasKey() rồi get()** trong hai lần gọi không phải một thao tác nguyên tử: key có thể hết hạn hoặc bị client khác xóa giữa hai lệnh. Vì vậy, với logic đọc thông thường, đôi khi **GET và kiểm tra null** là đủ.

### 6.5. Tăng bộ đếm

~~~java
Long first = redis.opsForValue()
        .increment("lesson:redis:views:42");

Long next = redis.opsForValue()
        .increment("lesson:redis:views:42", 5);
~~~

Tương ứng:

~~~text
INCR lesson:redis:views:42
INCRBY lesson:redis:views:42 5
GET lesson:redis:views:42
~~~

Nếu key trước đó không tồn tại, INCR tạo value bắt đầu từ 1. Redis lưu kết quả kiểu String chứa số. Việc tăng **không tự đặt TTL** cho một key mới. Nếu bài toán cần bộ đếm theo cửa sổ thời gian, phải thiết kế cách tạo key, expiration và concurrency; lệnh INCR riêng không tự biến thành rate limiter đúng.

Nếu key chứa văn bản không phải số nguyên hợp lệ hoặc giá trị vượt giới hạn số nguyên của thao tác, Redis báo lỗi. StringRedisTemplate không tự chuyển mọi String thành số hợp lệ.

## 7. Ví dụ service hoàn chỉnh: trạng thái ngắn hạn và bộ đếm

Giả sử ứng dụng cần lưu trạng thái nhập liệu theo mã yêu cầu, có TTL 5 phút, và đếm số lần mở một tài liệu. Mỗi dữ liệu phù hợp với String.

~~~java
package example.redis;

import java.time.Duration;
import java.util.Optional;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RequestStateStore {

    private static final Duration STATE_TTL = Duration.ofMinutes(5);

    private final StringRedisTemplate redis;

    public RequestStateStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static String stateKey(String requestId) {
        return "request:state:" + validateId(requestId);
    }

    private static String viewKey(String documentId) {
        return "document:views:" + validateId(documentId);
    }

    private static String validateId(String id) {
        if (id == null || !id.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid identifier");
        }
        return id;
    }

    public void saveState(String requestId, String state) {
        if (state == null || state.isBlank()) {
            throw new IllegalArgumentException("State is required");
        }
        redis.opsForValue().set(stateKey(requestId), state, STATE_TTL);
    }

    public Optional<String> findState(String requestId) {
        return Optional.ofNullable(
                redis.opsForValue().get(stateKey(requestId))
        );
    }

    public boolean removeState(String requestId) {
        return Boolean.TRUE.equals(redis.delete(stateKey(requestId)));
    }

    public long recordDocumentView(String documentId) {
        Long total = redis.opsForValue().increment(viewKey(documentId));
        if (total == null) {
            throw new IllegalStateException("Redis increment did not return a value");
        }
        return total;
    }
}
~~~

Giả sử service được gọi lần lượt:

~~~java
stateStore.saveState("req42", "PENDING");
Optional<String> state = stateStore.findState("req42");
long views = stateStore.recordDocumentView("doc108");
~~~

Redis sẽ có những key dễ kiểm tra:

~~~text
GET request:state:req42
TTL request:state:req42
GET document:views:doc108
TYPE request:state:req42
TYPE document:views:doc108
~~~

Trạng thái **PENDING** có TTL xấp xỉ 300 giây sau khi ghi. Bộ đếm sẽ có value dạng số nguyên lưu bằng Redis String; nếu mới tăng một lần từ key chưa tồn tại, value là **1** và không có TTL mặc định. Cả hai đều là **Java String / Redis String** trong đường đọc/ghi, nhưng có **ngữ nghĩa nghiệp vụ khác nhau**.

Ở đây **Optional.empty()** có thể có nghĩa là key chưa được tạo, đã bị xóa hoặc đã hết hạn; logic nghiệp vụ cần tự diễn giải. Nếu yêu cầu phân biệt các trạng thái đó, cần thêm cơ chế dữ liệu phù hợp.

Việc kiểm tra id bằng một tập ký tự giới hạn giúp tránh tạo tên key tùy ý từ input người dùng. Trong một ứng dụng thật, key nên được chuẩn hóa theo quy ước rõ ràng và tránh lộ thông tin nhạy cảm trong tên key.

## 8. Dùng StringRedisTemplate với Hash, List, Set và Sorted Set

Tên lớp StringRedisTemplate dễ khiến người học tưởng nó chỉ cho phép **opsForValue()**. Thực tế, template này thừa hưởng các nhóm thao tác của RedisTemplate; giá trị Java được biểu diễn dưới dạng chuỗi thông qua serializer tương ứng.

### 8.1. Hash có field và value là String

~~~java
import org.springframework.data.redis.core.HashOperations;

HashOperations<String, String, String> hashes = redis.opsForHash();

hashes.put("lesson:product:42", "name", "Redis Guide");
hashes.put("lesson:product:42", "status", "ACTIVE");

String name = hashes.get("lesson:product:42", "name");
~~~

Kiểm tra bằng redis-cli:

~~~text
TYPE lesson:product:42
HGET lesson:product:42 name
HGETALL lesson:product:42
~~~

Redis TYPE là **hash**. Field/name/value là chuỗi; TTL nếu có áp dụng cho **toàn bộ key Hash**, không tự áp dụng cho từng field theo cách làm việc với TTL truyền thống ở cấp key.

### 8.2. List chứa chuỗi

~~~java
redis.opsForList().rightPush("lesson:queue:notes", "note-1");
redis.opsForList().rightPush("lesson:queue:notes", "note-2");

List<String> notes = redis.opsForList()
        .range("lesson:queue:notes", 0, -1);
~~~

Kiểm tra:

~~~text
LRANGE lesson:queue:notes 0 -1
~~~

Redis List giữ thứ tự phần tử. Nếu dùng List cho hàng đợi xử lý nền, vẫn cần xét cơ chế bảo đảm xử lý, retry và acknowledge; StringRedisTemplate không tự cung cấp những thuộc tính đó.

### 8.3. Set chứa chuỗi

~~~java
redis.opsForSet().add("lesson:course:tags",
        "spring", "redis", "java");

Boolean hasRedis = redis.opsForSet()
        .isMember("lesson:course:tags", "redis");
~~~

Kiểm tra:

~~~text
SMEMBERS lesson:course:tags
SISMEMBER lesson:course:tags redis
~~~

Set chỉ chứa phần tử duy nhất, không bảo đảm thứ tự hiển thị.

### 8.4. Sorted Set: member String, score dạng số

~~~java
redis.opsForZSet().add(
        "lesson:leaderboard", "student:42", 92.5);

Double score = redis.opsForZSet()
        .score("lesson:leaderboard", "student:42");
~~~

Kiểm tra:

~~~text
ZRANGE lesson:leaderboard 0 -1 WITHSCORES
~~~

Trong Sorted Set, member được mã hóa thành chuỗi, nhưng score được Redis quản lý như giá trị số theo quy tắc của kiểu dữ liệu Sorted Set. Việc chọn StringRedisTemplate không biến score thành field chuỗi tự do.

### Các kiểu dữ liệu cần mô hình hóa riêng

Nếu một phần tử là đối tượng Java phức tạp, có nhiều thuộc tính, cần cập nhật và truy vấn theo field, bạn nên đánh giá việc dùng Redis Hash với cách ánh xạ rõ ràng, hoặc RedisTemplate với JSON serializer. Không nên nối tất cả field vào một String rồi tách bằng dấu phẩy nếu dữ liệu cần tiến hóa và có ký tự đặc biệt.

## 9. JSON String: dùng được nhưng cần quản lý schema

Một ví dụ với Jackson:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;

record ProductSnapshot(long id, String name, boolean active) {}

ObjectMapper mapper = new ObjectMapper();

ProductSnapshot product = new ProductSnapshot(42, "Redis Guide", true);
String json = mapper.writeValueAsString(product);

redis.opsForValue().set(
        "product:snapshot:42", json, Duration.ofMinutes(10));

String raw = redis.opsForValue().get("product:snapshot:42");
if (raw != null) {
    ProductSnapshot restored =
            mapper.readValue(raw, ProductSnapshot.class);
}
~~~

Đoạn mã minh họa cách biểu diễn dữ liệu, giả định các lệnh đang nằm trong một phương thức xử lý ngoại lệ **JsonProcessingException** hoặc khai báo throws. Jackson phải có trong dependency của ứng dụng; một dự án Spring Boot web thường đã có, nhưng không nên giả định mọi module đều đã bổ sung Jackson.

Redis-cli có thể thấy nội dung JSON như văn bản:

~~~text
GET product:snapshot:42
~~~

**Ưu điểm:** dễ quan sát, dễ chia sẻ với công cụ ngoài Java, chủ động định dạng JSON.

**Chi phí:** application code phải quản lý schema, phiên bản, kiểu dữ liệu, lỗi deserialize và độ tương thích khi thay đổi DTO. Nếu mọi service đều lặp lại thao tác JSON String, cân nhắc một lớp codec dùng chung hoặc một RedisTemplate có serializer kiểu JSON.

Không nên deserialize dữ liệu không tin cậy sang các kiểu tùy ý hoặc sử dụng cơ chế polymorphic type handling thiếu kiểm soát. Dữ liệu nhận từ Redis cũng cần được kiểm tra theo hợp đồng ứng dụng.

## 10. Khi nào KHÔNG nên chọn StringRedisTemplate?

| Nhu cầu | Lựa chọn nên cân nhắc | Lý do |
| --- | --- | --- |
| Chỉ có key và value dạng text, hoặc số nguyên dạng chuỗi | **StringRedisTemplate** | Đơn giản, có thể kiểm tra trực tiếp bằng redis-cli. |
| Cần lưu nhiều DTO Java có cấu trúc | **RedisTemplate** với JSON serializer hoặc lớp codec rõ ràng | Giảm việc serialize/deserialize thủ công lặp lại. |
| Chỉ muốn cache kết quả phương thức với annotation | **Spring Cache** dùng RedisCacheManager | Tập trung vào chính sách cache, không cần gọi template trong từng service. |
| Cần repository cho dữ liệu ánh xạ vào Redis | **Spring Data Redis repositories** khi phù hợp | Sử dụng abstraction repository và mô hình ánh xạ tương ứng. |
| Ứng dụng WebFlux reactive xuyên suốt | **ReactiveStringRedisTemplate** | Cung cấp API reactive, tránh thao tác blocking trong event loop. |
| Cần khóa hoặc value nhị phân thuần túy | **RedisTemplate với serializer bytes phù hợp** hoặc API client phù hợp | Không ép dữ liệu bytes thành String. |
| Phải tương thích dữ liệu cũ đang dùng serializer khác | **Giữ serializer tương thích hoặc xây lộ trình migration** | Tránh ứng dụng mới không đọc được key/value cũ. |

### Vì sao StringRedisTemplate không đồng nghĩa với @Cacheable?

StringRedisTemplate thực hiện các lệnh Redis **trực tiếp** qua Java API. Annotation **@Cacheable** dùng **Spring Cache** và một **CacheManager**. Nếu CacheManager là RedisCacheManager, dữ liệu được ghi vào Redis theo cách cấu hình của CacheManager, **không tự động dùng serializer và key convention của StringRedisTemplate**.

Ví dụ:

~~~java
@Cacheable(cacheNames = "products", key = "#id")
public Product findProduct(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Method này dùng CacheManager; nó không đòi hỏi bạn inject StringRedisTemplate vào service. Key Redis có thể có prefix dạng **products::42**, còn value có thể là bytes theo serializer của cache manager. Không nên tự giả định **redis.opsForValue().get("products::42")** đọc được trực tiếp DTO đã cache.

Nếu yêu cầu chỉ là “cache kết quả của method”, annotation cache thường gọn hơn; nếu cần “đọc, ghi, tăng, xóa một key theo một quy tắc cụ thể”, StringRedisTemplate đem lại quyền điều khiển trực tiếp.

## 11. Serializer, UTF-8 và những lỗi tương thích thường gặp

### 11.1. Cùng tên key ở Java chưa chắc là cùng key bytes

Giả sử hai service:

- Service A sử dụng StringRedisTemplate, ghi String key **customer:42:name** bằng UTF-8.
- Service B dùng RedisTemplate đã được cấu hình serializer key khác, chẳng hạn dạng nhị phân.

Nếu Service B gửi một chuỗi Java có ký tự giống hệt nhưng serializer chuyển thành bytes khác, Redis xem đó là **hai key khác nhau**. Một bên có thể GET được dữ liệu của mình trong khi bên kia trả null.

Redis định danh key bằng bytes, không dựa trên chữ hiển thị trong source Java. Khi nhiều service cùng dùng Redis, phải thống nhất **cách tạo tên key và serializer**.

### 11.2. Value String khác value đối tượng

Nếu một key được ghi bằng JDK serialization hay JSON serializer có cấu trúc khác, đọc bằng StringRedisTemplate có thể trả một chuỗi ký tự không mong muốn, báo lỗi giải mã hoặc không mang ý nghĩa nghiệp vụ phù hợp. Ngược lại, một DTO serializer đang mong dữ liệu JSON có thể không đọc được String thuần do StringRedisTemplate ghi.

**Không trộn serializer trên cùng một namespace/key nếu không có kế hoạch tương thích.**

### 11.3. Unicode và UTF-8

StringRedisSerializer mã hóa String theo UTF-8. Điều này hỗ trợ văn bản tiếng Việt như:

~~~java
redis.opsForValue().set(
        "lesson:redis:welcome:vi",
        "Chào mừng bạn đến với Spring Data Redis");
~~~

Redis lưu bytes UTF-8 tương ứng. Công cụ dòng lệnh và terminal cần dùng encoding hiển thị tương thích nếu muốn thấy dấu tiếng Việt đúng. Nếu terminal hiện ký tự lỗi, cần phân biệt **lỗi hiển thị terminal** với **lỗi serializer**; không kết luận dữ liệu trong Redis bị hỏng khi chưa kiểm tra.

### 11.4. Tên key và giá trị rỗng

Một String rỗng **""** vẫn khác key không tồn tại. Vì vậy:

~~~java
redis.opsForValue().set("lesson:empty", "");
String value = redis.opsForValue().get("lesson:empty");
~~~

GET trả String rỗng, còn GET một key chưa từng tạo trả null. Logic nghiệp vụ không nên coi cả hai trường hợp là một trừ khi đó là quyết định có chủ đích.

Một key có tên rất dài hoặc chứa thông tin cá nhân sẽ khó vận hành. Nên chọn tiền tố ngắn, có ý nghĩa và tránh đưa bí mật, email, số định danh nhạy cảm vào tên key.

## 12. Thiết kế key cho dữ liệu String

Các quy ước đặt tên thường giúp đọc code và quản lý Redis thuận tiện:

~~~text
<domain>:<entity>:<identifier>:<attribute>
~~~

Ví dụ:

~~~text
course:redis:42:title
feature:checkout:enabled
request:state:req42
document:views:doc108
product:snapshot:42
~~~

Tùy nghiệp vụ, đôi khi thêm **version** trong key giúp thay đổi cấu trúc dữ liệu mà không đụng vào dữ liệu cũ:

~~~text
product:v1:snapshot:42
product:v2:snapshot:42
~~~

Nếu ứng dụng dùng **Redis Cluster** và cần thao tác nhiều key trong một lệnh, các key liên quan phải tuân theo quy tắc slot. Có thể dùng hash tag với cùng phần trong cặp ngoặc nhọn:

~~~text
cart:{tenant:t7:cart:c42}:summary
cart:{tenant:t7:cart:c42}:coupon
~~~

StringRedisTemplate sẽ mã hóa các tên key String đó thành bytes UTF-8, giúp cú pháp hash tag được Redis Cluster nhận diện theo tên key thực tế. Dùng tag cho những nhóm cần cùng slot, tránh một tag quá rộng khiến tất cả key đổ vào một hot slot.

## 13. Các lưu ý về tính đúng đắn và hiệu năng

### 13.1. Đừng tạo thao tác read–modify–write thiếu nguyên tử

Ví dụ tự tăng bộ đếm theo kiểu sau dễ xảy ra race condition:

~~~java
String current = redis.opsForValue().get(key);
long n = current == null ? 0 : Long.parseLong(current);
redis.opsForValue().set(key, Long.toString(n + 1));
~~~

Hai request có thể cùng đọc giá trị cũ rồi cùng ghi một kết quả mới, làm mất lượt tăng. Khi chỉ cần cộng số nguyên, hãy ưu tiên **increment(...)** vì Redis xử lý thao tác này nguyên tử.

Nếu nghiệp vụ cần nhiều bước nguyên tử, phải sử dụng lệnh phù hợp, script hoặc giao dịch có cân nhắc rõ. StringRedisTemplate không tự biến nhiều lời gọi Java riêng biệt thành một transaction.

### 13.2. TTL phải được thiết kế theo ngữ nghĩa dữ liệu

Nếu key lưu trạng thái chỉ hợp lệ trong 5 phút, ghi kèm TTL ngay từ đầu. Nếu key là bộ đếm dài hạn và cần giữ qua các lần truy cập, có thể không đặt TTL. Với cache, cần có chính sách invalidation khi nguồn dữ liệu thay đổi.

Không có một TTL đúng cho mọi String. TTL quá ngắn có thể khiến cache miss liên tục; TTL quá dài có thể khiến dữ liệu cũ được trả về lâu hơn mong muốn.

### 13.3. StringRedisTemplate không làm Redis trở thành database giao dịch quan hệ

Redis hỗ trợ thao tác dữ liệu nhanh, nhưng cần cân nhắc persistence, replication, failover, maxmemory, eviction, backup và tính nhất quán khi dữ liệu quan trọng.

Với dữ liệu nguồn chính, yêu cầu độ bền và khả năng khôi phục có thể nghiêm ngặt hơn cache. Việc chọn template String không quyết định được những đặc tính vận hành đó.

### 13.4. Lỗi kết nối và timeout

Các lời gọi template thông thường phải giao tiếp với Redis Server qua network. Nếu Redis unavailable, timeout hoặc ACL từ chối, lệnh có thể phát sinh exception thay vì trả null.

Phân biệt:

- **null từ GET**: bình thường, thường là key chưa tồn tại hoặc hết hạn.
- **exception**: có thể là lỗi kết nối, xác thực, thiếu quyền, WRONGTYPE hoặc lỗi khác.

Không nên bắt toàn bộ exception rồi coi như “cache miss” khi thao tác Redis đang mang ý nghĩa nghiệp vụ bắt buộc, chẳng hạn ghi marker chống xử lý trùng.

### 13.5. StringRedisTemplate là API blocking

Trong ứng dụng Spring MVC thông thường, API blocking thường phù hợp. Nhưng với reactive flow dùng WebFlux, việc gọi thao tác blocking trên event loop có thể gây giảm khả năng xử lý đồng thời.

Nếu stack sử dụng Reactor, **ReactiveStringRedisTemplate** cung cấp API tương tự theo hướng reactive, với kết quả được biểu diễn qua Mono/Flux. Chọn biến thể phù hợp với mô hình ứng dụng thay vì trộn hai cách gọi tùy tiện.

## 14. Thực hành kiểm chứng bằng redis-cli

Giả sử Redis chạy trên máy local, không cần xác thực trong môi trường học. Mở redis-cli:

~~~bash
redis-cli -h 127.0.0.1 -p 6379
~~~

Nếu Redis yêu cầu ACL/TLS/password, sử dụng cách kết nối an toàn theo cấu hình hệ thống. Các lệnh bên dưới thực hiện **bên trong redis-cli**.

### Bước 1: Quan sát key do StringRedisTemplate ghi

Sau khi gọi các method của ví dụ Java:

~~~text
PING
TYPE request:state:req42
GET request:state:req42
TTL request:state:req42
TYPE document:views:doc108
GET document:views:doc108
~~~

Bạn sẽ thấy **request:state:req42** và **document:views:doc108** có Redis TYPE là string. Value đầu là trạng thái văn bản; value sau là số nguyên biểu diễn dạng String. TTL chỉ có ở key được ghi với expiration trong ví dụ.

### Bước 2: Thử các thao tác chuỗi trực tiếp

~~~text
SET lesson:probe:language vi EX 60
GET lesson:probe:language
TTL lesson:probe:language
SET lesson:probe:empty ""
GET lesson:probe:empty
EXISTS lesson:probe:empty
~~~

Key **lesson:probe:empty** tồn tại dù String rỗng. Nếu bạn gọi GET khi đã hết TTL, kết quả của key language sẽ là nil.

### Bước 3: Quan sát bộ đếm

~~~text
INCR lesson:probe:views
INCR lesson:probe:views
GET lesson:probe:views
TTL lesson:probe:views
~~~

Nếu key chưa tồn tại, hai lần INCR tạo giá trị 2 và TTL thường là -1 vì chưa gán expiration. Đừng dùng một key đếm thật đang được ứng dụng production sử dụng để thử lệnh.

### Bước 4: Quan sát Hash lưu field/value dạng String

~~~text
HSET lesson:probe:hash name "Redis Guide" status ACTIVE
TYPE lesson:probe:hash
HGET lesson:probe:hash name
HGETALL lesson:probe:hash
~~~

TYPE là hash, dù các phần tử bạn ghi có thể được thao tác bằng StringRedisTemplate trong Java. Điều này nhắc lại khác biệt giữa **serialization bằng String** và **Redis data type**.

### Bước 5: Dọn đúng key thử nghiệm

~~~text
DEL lesson:probe:language lesson:probe:empty lesson:probe:views lesson:probe:hash
~~~

Chỉ xóa những key bạn vừa tạo trong Redis học tập. Không dùng FLUSHDB hoặc FLUSHALL chỉ để dọn các ví dụ nhỏ.

## 15. Khắc phục lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| Java GET trả null | Key chưa có, hết TTL, sai Redis instance hoặc key khác serializer | Kiểm tra tên key, host/port/database, TTL và serializer. |
| redis-cli GET ra nil nhưng Java đọc được | Key được serializer khác mã hóa, sai database hoặc key prefix | Kiểm tra bean template, cache prefix, bytes của key thực tế. |
| redis-cli hiển thị dữ liệu nhị phân | Một template/cache manager khác ghi value bằng serializer khác | Xem cấu hình value serializer và người tạo key. |
| GET báo WRONGTYPE | Key thực tế là Hash/List/Set/... | TYPE key rồi dùng HGET, LRANGE, SMEMBERS phù hợp. |
| INCR báo value is not an integer | Value không biểu diễn số nguyên hợp lệ | GET key, sửa quy ước lưu dữ liệu. |
| Bộ đếm mất dữ liệu khi có nhiều request | Ứng dụng dùng GET rồi SET thay vì INCR | Dùng thao tác tăng nguyên tử. |
| Key không còn sau một khoảng thời gian | Key được gán TTL hoặc Redis có chính sách eviction | Kiểm tra TTL, INFO và cấu hình server. |
| TTL = -1 dù trước đó có đặt thời gian | Đường cập nhật dùng SET không kèm TTL, hoặc có PERSIST | Xem toàn bộ đường ghi key. |
| @Cacheable có key nhưng StringRedisTemplate không đọc được value | CacheManager dùng serializer khác | Kiểm tra RedisCacheConfiguration và cách tạo key. |
| Lỗi NOAUTH/WRONGPASS/NOPERM | Thiếu credential hoặc thiếu quyền ACL | Kiểm tra connection config và quyền Redis user. |
| Redis Cluster báo CROSSSLOT khi multiGet/multiSet | Các key thuộc những hash slot khác nhau | Thiết kế key cùng slot hoặc thay đổi cách thao tác. |

### Khi đang dùng RedisTemplate và muốn chuyển sang StringRedisTemplate

Không nên chỉ thay kiểu bean trong constructor rồi kỳ vọng tự đọc toàn bộ key cũ. Cần xác định:

1. **Key serializer cũ** và key bytes Redis đã lưu.
2. **Value serializer cũ** và định dạng value thực tế.
3. Các code path khác còn ghi key theo định dạng cũ hay không.
4. Loại dữ liệu: String, Hash, List, Set hay kiểu khác.
5. Có thể xóa và tạo lại dữ liệu hay cần migration có bảo toàn trạng thái?

Với cache có thể dựng lại, đổi namespace/prefix và để key cũ hết hạn có thể là giải pháp đơn giản. Với dữ liệu không thể mất, cần đường migration dữ liệu và kiểm chứng trước khi chuyển hoàn toàn. Thay serializer **không tự chuyển đổi bytes hiện có trong Redis**.

## 16. Quy tắc chọn template trong một dự án thực tế

Khi định thêm thao tác Redis vào một service, hãy xác định bốn điều:

1. **Key và value ở phía Java có tự nhiên là String không?** Nếu có, StringRedisTemplate là lựa chọn thuận tiện.
2. **Redis data type cần dùng là gì?** Nếu là String, chọn opsForValue; nếu là Hash, List, Set hoặc Sorted Set, chọn nhóm ops tương ứng.
3. **Ai khác sẽ đọc dữ liệu này?** Nếu có redis-cli, service khác ngôn ngữ hoặc một pipeline phân tích, thống nhất UTF-8, key convention và định dạng value.
4. **Dữ liệu có TTL, cần nguyên tử hay tính nhất quán cao không?** Chọn lệnh phù hợp với ràng buộc nghiệp vụ và hạ tầng (Cluster, ACL, latency, persistence).

StringRedisTemplate giúp các thao tác Redis với dữ liệu chuỗi trở nên rõ ràng: **khóa dễ đọc, value được serialize thành UTF-8, API quen thuộc và thuận tiện khi đối chiếu bằng redis-cli**. Hãy chọn nó cho các giá trị text, số nguyên dạng chuỗi và những cấu trúc Redis có phần tử chuỗi. Khi cần lưu các object Java có schema, cache phương thức hoặc xử lý reactive, hãy cân nhắc RedisTemplate cấu hình serializer, Spring Cache hoặc ReactiveStringRedisTemplate theo đúng bài toán.
