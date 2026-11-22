# Tuần tự hóa kết quả pipeline và chọn serializer phù hợp trong Spring Data Redis

## 1. Vì sao pipeline trả kết quả không giống lệnh Redis bình thường?

Pipeline giúp gửi nhiều lệnh Redis trên cùng một kết nối mà không đợi phản hồi sau từng lệnh. Khi ứng dụng cần đọc hoặc ghi hàng trăm khóa, việc giảm số vòng chờ giữa ứng dụng và Redis có thể cải thiện đáng kể thời gian thực thi.

Tuy nhiên, pipeline cũng làm nổi bật một vấn đề dễ bỏ qua: **Redis giao tiếp bằng byte, còn Java làm việc với String, Long, Boolean, Map và đối tượng miền nghiệp vụ**. Một pipeline có thể trả nhiều loại phản hồi khác nhau. Spring Data Redis phải quyết định phần nào cần được giải mã bằng `RedisSerializer` và phần nào đã là giá trị số hoặc trạng thái.

Ví dụ:

~~~text
Java application                       Redis
      |                                  |
      | SET user:1 "An"                   |
      | GET user:1                        |
      | INCR stats:reads                  |
      | HGETALL user:1:flags              |
      |--------------------------------->|
      |                                  | xử lý các lệnh
      |<---------------------------------|
      | status, bytes, integer, map      |
      |                                  |
      v
Spring Data Redis giải mã các phần tử tương ứng
      |
      v
List<Object> kết quả pipeline
~~~

Đây là lý do không thể áp dụng một phép ép kiểu `(String)` hoặc `(User)` cho mọi phần tử trong `List<Object>`.

Hai câu hỏi chính cần trả lời:

1. **Dữ liệu được ghi vào Redis đã dùng serializer nào?**
2. **Khi lấy kết quả pipeline, Spring Data Redis dùng serializer nào để chuyển byte thành đối tượng?**

Nếu hai phía không tương thích, có thể gặp ký tự lạ, lỗi deserialization, sai kiểu hoặc kết quả bị hiểu nhầm.

## 2. Hai chiều serialization khác nhau

Một lời gọi Redis thông thường có hai chiều:

~~~text
Ứng dụng Java
  |
  | WRITE: Java value -> RedisSerializer.serialize(...) -> byte[]
  v
Redis
  |
  | READ: byte[] -> RedisSerializer.deserialize(...) -> Java value
  v
Ứng dụng Java
~~~

Với pipeline, các lệnh được gửi theo lô, còn phản hồi được thu lại và giải mã sau khi kết thúc pipeline.

**Phần gửi lệnh:** Nếu gọi lệnh qua API mức cao của `RedisTemplate`, template có thể tuần tự hóa key/value theo cấu hình. Nếu gọi trực tiếp qua `RedisConnection` trong `RedisCallback`, các lệnh mức thấp thường nhận `byte[]`; người viết callback phải tạo đúng bytes theo quy ước dữ liệu đang lưu.

**Phần đọc kết quả:** `RedisTemplate.executePipelined(...)` thu các reply và thực hiện deserialization khi trả về `List<Object>`, sử dụng serializer cấu hình trên template hoặc serializer được cung cấp qua overload của phương thức.

Một sai lầm phổ biến là đưa `StringRedisSerializer` vào bước đọc kết quả trong khi dữ liệu trong Redis đã được ghi bằng JSON hoặc JDK serialization. Redis không lưu metadata chung cho biết “value này dùng serializer nào” để Spring tự chọn đúng.

## 3. Các serializer cần phân biệt trên RedisTemplate

Một `RedisTemplate<K, V>` có nhiều serializer chứ không chỉ một:

| Serializer | Công dụng chính | Ví dụ dữ liệu |
| --- | --- | --- |
| `keySerializer` | Mã hóa khóa Redis | `user:42` |
| `valueSerializer` | Mã hóa/giải mã value của những lệnh như `GET`/`SET` | Nội dung đối tượng hoặc String |
| `hashKeySerializer` | Mã hóa field trong Redis Hash | `name`, `status` |
| `hashValueSerializer` | Mã hóa value của field trong Redis Hash | `An`, `ACTIVE` |
| `stringSerializer` | Hỗ trợ một số thao tác liên quan tới String khi template sử dụng | Tên khóa, chuỗi định dạng văn bản |
| `defaultSerializer` | Serializer mặc định khi template sử dụng cơ chế mặc định | Phụ thuộc cấu hình template |

Ví dụ cấu hình có chủ đích:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisSerializationConfig {

    @Bean
    public RedisTemplate<String, Object> jsonRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);

        StringRedisSerializer strings = new StringRedisSerializer();
        GenericJackson2JsonRedisSerializer json =
            new GenericJackson2JsonRedisSerializer();

        template.setKeySerializer(strings);
        template.setHashKeySerializer(strings);
        template.setValueSerializer(json);
        template.setHashValueSerializer(json);

        template.afterPropertiesSet();
        return template;
    }
}
~~~

Cấu hình trên chọn:

- Key và hash field là chuỗi UTF-8 dễ kiểm tra bằng `redis-cli`.
- Value và hash value được mã hóa thành JSON theo serializer đã chọn.
- Pipeline đọc các value thuộc cấu trúc Redis tương ứng bằng quy tắc deserialization của template.

**Cần chọn serializer nhất quán với dữ liệu đã được ghi.** Nếu cùng một tên khóa trước đây lưu JDK serialization nhưng sau đó chuyển sang JSON, việc đổi cấu hình template không tự chuyển dữ liệu cũ. Cần chiến lược migration hoặc namespace/version mới.

## 4. Khác biệt giữa StringRedisTemplate và RedisTemplate

`StringRedisTemplate` là lựa chọn tự nhiên khi cả key và value là chuỗi:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SimpleCounterStore {

    private final StringRedisTemplate redis;

    public SimpleCounterStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveLabel(String id, String label) {
        redis.opsForValue().set("label:" + id, label);
    }
}
~~~

`StringRedisTemplate` sử dụng `StringRedisSerializer` cho các phần dữ liệu chuỗi thông dụng, giúp kết quả `GET` có thể được giải mã thành `String`.

`RedisTemplate<String, Object>` với JSON phù hợp khi muốn lưu các DTO và cần quy tắc serialize/deserialize object. Một template mặc định chưa được cấu hình rõ ràng có thể sử dụng JDK serialization, tạo byte nhị phân không đọc được như văn bản thuần.

Bảng lựa chọn cơ bản:

| Dữ liệu lưu trữ | Serializer thường phù hợp | Lưu ý |
| --- | --- | --- |
| Key Redis, hash field | `StringRedisSerializer` | Dễ chẩn đoán, ổn định khi tên khóa là text |
| Giá trị String | `StringRedisSerializer` | Đọc được bằng lệnh Redis CLI |
| DTO JSON | JSON serializer, chẳng hạn `GenericJackson2JsonRedisSerializer` | Cần quy tắc schema và type metadata |
| Dữ liệu nhị phân | Serializer truyền nguyên bytes | Tránh chuyển bytes tùy ý thành String |
| Số nguyên với `INCR`/`DECR` | Giá trị Redis integer reply, không phải JSON object | Không ép số sang chuỗi chỉ vì value serializer là String |
| Tương thích Java native serialization cũ | `JdkSerializationRedisSerializer` | Có ràng buộc Java class và lưu ý bảo mật |
| Payload cần chia sẻ với ngôn ngữ khác | JSON, text hoặc một định dạng liên thông đã quy định | Thống nhất schema và version |

Không tồn tại serializer tối ưu cho tất cả trường hợp. Quy tắc quan trọng nhất là **đọc và ghi cùng một contract byte**.

## 5. API executePipelined trả về điều gì?

Spring Data Redis cung cấp các overload kiểu:

~~~java
List<Object> executePipelined(RedisCallback<?> action);

List<Object> executePipelined(
    RedisCallback<?> action,
    RedisSerializer<?> resultSerializer
);
~~~

Ngoài `RedisCallback`, template còn có các biến thể sử dụng `SessionCallback`.

Kết quả là `List<Object>` vì lệnh trong pipeline có thể trả nhiều loại:

~~~text
SET      -> status / Boolean tùy đường API và driver
GET      -> bytes -> String / DTO sau deserialization
INCR     -> integer -> Long
EXISTS   -> boolean/integer theo API của lệnh
HGETALL  -> map field/value sau deserialization
LRANGE   -> danh sách các phần tử
DEL      -> số khóa đã xóa
~~~

Đừng dựa vào việc lệnh `SET` luôn tạo `Boolean.TRUE` ở một index cố định trên mọi client/phiên bản. Cấu trúc reply cụ thể có thể phụ thuộc lệnh Redis, driver và cách Spring Data Redis xử lý; nên hiểu trước chuỗi lệnh và mapping kết quả khi thiết kế.

### Callback phải trả về null

Cách sử dụng quan trọng:

~~~java
List<Object> results = template.executePipelined(
    (RedisCallback<Object>) connection -> {
        // Xếp các lệnh Redis vào pipeline.
        // Không dựa vào phản hồi tức thời của từng lệnh.
        return null;
    }
);
~~~

Callback trả về `null` vì giá trị return của callback không phải kênh trả kết quả pipeline. Các reply thực tế xuất hiện trong danh sách trả về của `executePipelined`.

Không nên viết:

~~~java
Long count = connection.stringCommands().incr(keyBytes);

if (count > 10) {
    // Sai về mặt tư duy pipeline:
    // phản hồi INCR có thể chưa được nhận trong callback.
}
~~~

Trong quá trình enqueue pipeline, kết quả của một lệnh thường chưa sẵn sàng để xử lý như một lời gọi đồng bộ. Hãy thực hiện logic phụ thuộc kết quả **sau khi pipeline đóng và nhận đầy đủ phản hồi**, hoặc tách thành những pha giao tiếp riêng.

## 6. Ví dụ StringRedisTemplate: ghi, đọc, tăng bộ đếm

Đây là ví dụ đầy đủ về pipeline với dữ liệu văn bản:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PipelineDemoService {

    private final StringRedisTemplate template;

    public PipelineDemoService(StringRedisTemplate template) {
        this.template = template;
    }

    public List<Object> executeSimplePipeline() {
        return template.executePipelined(
            (RedisCallback<Object>) connection -> {

                byte[] nameKey = "demo:name:42"
                    .getBytes(StandardCharsets.UTF_8);

                byte[] nameValue = "An"
                    .getBytes(StandardCharsets.UTF_8);

                byte[] counterKey = "demo:reads"
                    .getBytes(StandardCharsets.UTF_8);

                connection.stringCommands().set(
                    nameKey, nameValue
                );

                connection.stringCommands().get(nameKey);

                connection.stringCommands().incr(counterKey);

                return null;
            }
        );
    }
}
~~~

Với StringRedisTemplate, phản hồi dạng bytes từ `GET` có thể được giải mã bằng `StringRedisSerializer` thành `"An"`. Phản hồi integer từ `INCR` giữ ngữ nghĩa số.

~~~text
Các lệnh theo thứ tự:
  SET demo:name:42 An
  GET demo:name:42
  INCR demo:reads

Kết quả dự kiến về mặt ngữ nghĩa:
  [phản hồi SET, "An", giá trị Long của INCR]
~~~

Giá trị thực tế của counter phụ thuộc trạng thái Redis trước đó. Ví dụ này tập trung vào **kiểu phản hồi**, không giả định một counter luôn bắt đầu tại 0.

### Vì sao dùng getBytes(UTF_8) trong ví dụ?

`RedisConnection` là API mức thấp và nhận `byte[]`. Vì key/value đều dùng text UTF-8, gọi `getBytes(StandardCharsets.UTF_8)` phù hợp với `StringRedisSerializer` trong trường hợp này.

Với value dùng JSON/JDK serialization, **không thay mọi serializer bằng getBytes(UTF_8)**. Cần dùng đúng serializer đã được dùng để ghi.

## 7. Hãy để serializer phụ trách cả chiều ghi và chiều đọc

Đối với giá trị JSON, dùng một serializer đã quy định và truyền nó nhất quán. Ví dụ dưới đây minh họa trực tiếp đường byte trong `RedisCallback`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;

public class JsonPipelineReader {

    private final RedisTemplate<String, Object> template;
    private final GenericJackson2JsonRedisSerializer json =
        new GenericJackson2JsonRedisSerializer();

    public JsonPipelineReader(RedisTemplate<String, Object> template) {
        this.template = template;
    }

    public List<Object> writeThenRead() {

        byte[] key = "profile:42"
            .getBytes(StandardCharsets.UTF_8);

        byte[] value = json.serialize(
            Map.of("id", "42", "name", "An")
        );

        return template.executePipelined(
            (RedisCallback<Object>) connection -> {
                connection.stringCommands().set(key, value);
                connection.stringCommands().get(key);
                return null;
            },
            json
        );
    }
}
~~~

Trong ví dụ:

1. `json.serialize(...)` tạo bytes để ghi xuống Redis.
2. `connection.stringCommands().set(...)` không tự biết `Map` vì nó chỉ nhận bytes.
3. `connection.stringCommands().get(...)` lấy phản hồi bytes.
4. Overload `executePipelined(..., json)` sử dụng serializer JSON cho những kết quả value dạng bytes thuộc phạm vi xử lý của overload.
5. `List<Object>` chứa reply của các lệnh, trong đó kết quả `GET` được giải mã theo JSON serializer.

Đoạn code giả định khóa dữ liệu này tuân theo contract JSON. Nếu các key khác lưu plain string hoặc JDK bytes, đưa chúng vào cùng một pipeline rồi giải mã tất cả bằng JSON có thể thất bại.

**Lưu ý về vòng đời serializer:** ở ứng dụng thực tế, nên tiêm cùng một bean serializer được chia sẻ giữa cấu hình template và code thao tác, thay vì vô tình tạo các serializer với quy tắc type metadata khác nhau ở nhiều nơi. Ví dụ tạo instance riêng chỉ để thể hiện cách truyền serializer vào overload.

## 8. Serializer truyền vào executePipelined thay đổi điều gì?

Overload nhận `resultSerializer` là công cụ điều chỉnh cách giải mã **kết quả**; nó **không tự thay đổi bytes đã được gửi trong callback**.

So sánh:

~~~text
A. Chiều WRITE trong RedisCallback
   Map/DTO --serialize(JSON)--> byte[] --SET--> Redis

B. Chiều READ sau khi kết thúc pipeline
   Redis --GET--> byte[] --resultSerializer--> Map/DTO
~~~

Nếu chỉ đổi result serializer:

~~~java
template.executePipelined(
    (RedisCallback<Object>) connection -> {
        // Vẫn ghi theo cách code ở đây tạo ra byte[].
        return null;
    },
    anotherSerializer
);
~~~

thì các lệnh trong callback **không tự đổi** cách serialize key hoặc value.

Một điểm chi tiết khác: `RedisTemplate` có cơ chế deserialization khác nhau cho scalar value, hash key và hash value. Khi truyền một `resultSerializer` riêng, đừng tự suy ra rằng mọi phần tử trong mọi loại container/map sẽ dùng duy nhất serializer đó. Với `HGETALL` hoặc danh sách lồng nhau, kết quả còn chịu quy tắc của lệnh và những serializer hash được cấu hình. Nếu trộn cấu trúc khác nhau trong cùng pipeline, nên kiểm tra contract của từng loại lệnh ở phiên bản đang triển khai.

### Trường hợp đúng để dùng resultSerializer riêng

- Cần đọc các value cũ với serializer khác value serializer mặc định của template.
- Một nhóm lệnh trong pipeline cùng trả value theo một định dạng riêng.
- Muốn pipeline chuyên biệt đọc binary payload bằng một serializer khớp với dữ liệu.
- Cần tách cách giải mã kết quả pipeline khỏi cấu hình template trong một phạm vi có kiểm soát.

### Trường hợp không phù hợp

- Pipeline trộn nhiều key có định dạng bytes hoàn toàn khác nhau nhưng chỉ có một resultSerializer chung.
- Mong resultSerializer quyết định cả cách viết bytes trong `RedisConnection`.
- Mong resultSerializer biến số đếm `Long` hoặc trạng thái `Boolean` thành DTO.
- Mong Spring tự biết schema của mọi hash và list khi dữ liệu nhiều phiên bản.

## 9. Một pipeline có kết quả hỗn hợp: đọc kiểu thế nào?

Giả sử một pipeline gồm:

~~~text
SET user:42 ...
GET user:42
INCR metrics:reads
HGETALL flags:42
DEL cache:old
~~~

Kết quả được trả dưới dạng `List<Object>`. Một số phần tử có thể là giá trị số, một số là chuỗi hoặc DTO, một số là `Map<?, ?>`.

Cách đọc an toàn là ràng buộc **ý nghĩa vị trí** với **kiểu mong đợi**:

~~~java
List<Object> replies = pipelineResult;

for (int i = 0; i < replies.size(); i++) {
    Object reply = replies.get(i);

    if (reply instanceof String text) {
        System.out.println("String reply: " + text);
    } else if (reply instanceof Number number) {
        System.out.println("Numeric reply: " + number.longValue());
    } else if (reply instanceof Map<?, ?> map) {
        System.out.println("Hash fields: " + map.size());
    } else {
        System.out.println(
            "Reply #" + i + ": " + String.valueOf(reply)
        );
    }
}
~~~

Đoạn này minh họa nhận dạng kiểu, **không thay thế contract về vị trí lệnh**. Trong code nghiệp vụ, cần biết phần tử nào ứng với `GET user:42`, phần tử nào ứng với `INCR` và phần tử nào ứng với `DEL`.

Không nên viết:

~~~java
// Dễ lỗi nếu reply đầu tiên là trạng thái SET, không phải String.
String user = (String) replies.get(0);
~~~

hoặc:

~~~java
// Dễ lỗi nếu giá trị này là Long/Boolean/Map.
byte[] raw = (byte[]) replies.get(2);
~~~

### Thiết kế pipeline theo nhóm kiểu dữ liệu

Một chiến lược dễ bảo trì:

~~~text
Pipeline A: đọc nhiều khóa String
  GET name:1, GET name:2, GET name:3
  -> cùng StringRedisSerializer

Pipeline B: đọc nhiều khóa DTO JSON
  GET product:1, GET product:2
  -> cùng JSON serializer

Pipeline C: cập nhật counter
  INCR count:1, INCR count:2
  -> replies kiểu số
~~~

Tách pipeline theo contract giúp đơn giản hóa deserialization và xử lý lỗi. Không nhất thiết phải tạo một pipeline lớn cho mọi lệnh không liên quan chỉ vì muốn giảm round-trip.

## 10. Hash cần hashKeySerializer và hashValueSerializer

Redis Hash khác với String value. Ví dụ:

~~~redis
HSET user:42 name An status ACTIVE
HGETALL user:42
~~~

Về mặt bytes:

~~~text
Redis Hash key:  "user:42"  -> keySerializer
Hash field:     "name"     -> hashKeySerializer
Hash value:     "An"       -> hashValueSerializer
~~~

Trong `RedisTemplate`, `hashKeySerializer` và `hashValueSerializer` có thể khác `valueSerializer`.

Ví dụ cấu hình toàn chuỗi:

~~~java
RedisTemplate<String, String> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);

StringRedisSerializer strings = new StringRedisSerializer();

template.setKeySerializer(strings);
template.setValueSerializer(strings);
template.setHashKeySerializer(strings);
template.setHashValueSerializer(strings);
template.afterPropertiesSet();
~~~

Pipeline mức thấp:

~~~java
List<Object> replies = template.executePipelined(
    (RedisCallback<Object>) connection -> {
        byte[] hashKey = "user:42".getBytes(StandardCharsets.UTF_8);
        byte[] field = "status".getBytes(StandardCharsets.UTF_8);
        byte[] value = "ACTIVE".getBytes(StandardCharsets.UTF_8);

        connection.hashCommands().hSet(hashKey, field, value);
        connection.hashCommands().hGetAll(hashKey);

        return null;
    }
);
~~~

Kết quả `HGETALL` có cấu trúc map; Spring Data Redis xử lý các phần tử của hash theo cấu hình serializer tương ứng. Nếu `hashKeySerializer` là String nhưng `hashValueSerializer` là JSON, field có thể là String trong khi value là đối tượng đã giải mã.

**Lỗi kinh điển:** ghi field `name` bằng UTF-8, nhưng cấu hình hash key là JDK serialization. Khi đọc, Redis sẽ tìm bytes khác với field đã ghi. Tùy thao tác, có thể trả `null`, map không phù hợp hoặc báo lỗi giải mã.

### Không dùng value serializer để giả định kiểu của hash

Một template cấu hình:

~~~text
keySerializer       = String
valueSerializer     = JSON
hashKeySerializer   = String
hashValueSerializer = String
~~~

là hoàn toàn hợp lệ. Trong trường hợp đó, value của `GET` và value của `HGETALL` có quy ước khác nhau. Chọn pipeline và cách ép kiểu theo cấu trúc đã đọc.

## 11. Các lệnh trả số và trạng thái có cần serializer không?

Không phải mọi reply Redis đều là bytes cần chuyển thành String hoặc DTO.

Ví dụ:

~~~redis
INCR page:views
DEL cache:old
TTL session:42
EXISTS session:42
SCARD users:online
~~~

Các lệnh này trả dữ liệu mang nghĩa integer hoặc boolean tùy API. Trong Java, kết quả thường là các kiểu như `Long` và `Boolean` mà driver/Spring đã chuyển từ RESP reply. `StringRedisSerializer` không nên được dùng để giả định mọi reply là `String`.

Bảng tư duy:

| Loại reply | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Binary bulk string | `GET key` | Giải mã bằng đúng value serializer |
| Hash map | `HGETALL key` | Giải mã hash key/value theo contract |
| List/set các bulk string | `LRANGE`, `SMEMBERS` | Xác định serializer của từng phần tử |
| Integer | `INCR`, `SCARD`, `TTL` | Giữ ngữ nghĩa số |
| Status/Boolean | `SET` và các lệnh trạng thái qua driver | Dùng kiểu của API thực tế |
| Nil/null | `GET missing` | Xử lý khóa không tồn tại, tránh ép kiểu tùy tiện |

Một serializer chỉ giải quyết **biểu diễn byte**, không tạo ra kiểu nghiệp vụ khi Redis trả integer/status/nil.

## 12. Pipelining không có nghĩa mọi reply đều là dữ liệu hữu ích

Khi xây pipeline để ghi hàng loạt:

~~~text
SET a 1
SET b 2
SET c 3
~~~

mục tiêu có thể chỉ là giảm round-trip khi gửi lệnh. Kết quả là các status/reply của lệnh ghi; không nhất thiết có payload nghiệp vụ để deserialize.

Nếu chỉ cần xác nhận đã gửi và xử lý xong, đừng xây một tầng mapping phức tạp cố chuyển mọi reply thành DTO. Khi cần kiểm tra riêng lệnh nào thành công, phải hiểu cách driver/Spring báo lỗi, số reply và thứ tự lệnh. Redis không biến pipeline thành transaction; một số lệnh có thể được thực thi trước khi lệnh sau gặp lỗi.

### Không dùng pipeline để phụ thuộc kết quả lệnh trước

Ví dụ nghiệp vụ:

~~~text
GET inventory:sku-1
nếu còn > 0:
  DECR inventory:sku-1
~~~

Không thể đặt `GET` và nhánh `if` vào callback pipeline rồi mong đọc được ngay kết quả. Nếu cần quyết định nguyên tử tại Redis, nên dùng kỹ thuật tương ứng như Lua script hoặc transaction với điều kiện được thiết kế phù hợp. Pipeline chỉ tối ưu số lượt trao đổi, không tạo tính nguyên tử hoặc khóa giao dịch.

## 13. Chọn giữa JSON, String, JDK và bytes

### StringRedisSerializer

Phù hợp với key, hash field và giá trị thuần văn bản.

**Ưu điểm:** UTF-8 dễ quan sát, tương thích nhiều client, payload thường gọn. **Nhược điểm:** không tự biểu diễn type của đối tượng Java phức tạp; muốn lưu cấu trúc cần tự quy định format.

Ví dụ:

~~~java
StringRedisSerializer serializer = new StringRedisSerializer();

byte[] bytes = serializer.serialize("ACTIVE");
String value = serializer.deserialize(bytes);
~~~

### JSON serializer

Phù hợp DTO cần trao đổi giữa dịch vụ hoặc cần đọc bằng công cụ ngoài Java.

**Ưu điểm:** tương đối dễ đọc, hỗ trợ schema có trường tên rõ ràng. **Nhược điểm:** có chi phí parse và vấn đề tương thích schema/type metadata. Một số JSON serializer có khả năng lưu thông tin kiểu runtime; phải hiểu chính sách type handling và dữ liệu tin cậy.

~~~java
GenericJackson2JsonRedisSerializer json =
    new GenericJackson2JsonRedisSerializer();

byte[] bytes = json.serialize(
    Map.of("id", "42", "enabled", true)
);

Object restored = json.deserialize(bytes);
~~~

Nếu hệ thống cần kiểu DTO xác định, cân nhắc serializer JSON có cấu hình type rõ ràng, quy tắc migration và validator/schema của ứng dụng. Không tùy ý bật polymorphic deserialization cho dữ liệu không tin cậy.

### JdkSerializationRedisSerializer

Có thể xuất hiện trong cấu hình RedisTemplate mặc định hoặc hệ thống cũ.

**Ưu điểm:** có thể tái tạo Java object phù hợp với cơ chế Java serialization. **Nhược điểm:** phụ thuộc class Java và phiên bản, khó trao đổi liên ngôn ngữ, payload thường lớn và có rủi ro bảo mật khi deserialize bytes không đáng tin.

Không nên chọn JDK serialization cho dữ liệu có thể bị tác nhân không tin cậy thao túng hoặc cần giao tiếp với hệ thống ngoài Java. Nếu bắt buộc đọc dữ liệu cũ, kiểm soát nguồn bytes và phạm vi class được deserialize.

### Byte array serializer

Phù hợp khi cần bảo toàn payload nhị phân, ảnh nhỏ, mã nén hoặc định dạng custom. Khi muốn xử lý raw bytes, tránh chuyển sang String rồi chuyển ngược, vì binary không nhất thiết là văn bản UTF-8 hợp lệ.

**Điểm chung:** serializer dùng lúc đọc pipeline phải tương thích với chính bytes đã ghi. Tên class trên Java không quan trọng bằng contract wire format đã xác lập.

## 14. Dữ liệu đa định dạng trong cùng Redis namespace

Xét ba khóa:

~~~text
user:1        -> JSON {"id":1,"name":"An"}
user:2        -> Java serialized object (legacy)
user:3        -> plain text "guest"
~~~

Nếu gọi `MGET` hoặc nhiều `GET` trong một pipeline rồi dùng **một JSON resultSerializer**, chỉ các value JSON tương thích mới có thể được đọc đúng. Với bytes Java serialization hoặc plain text, quá trình giải mã JSON có thể báo lỗi hoặc tạo dữ liệu không phù hợp.

Các hướng xử lý:

**A. Chuẩn hóa contract trước.** Migration tất cả khóa theo schema mới, hoặc tạo namespace version như `user:v2:...`. Đây là lựa chọn sạch khi có quyền kiểm soát dữ liệu.

**B. Chia pipeline theo serializer.** Dùng pipeline A cho JSON, B cho text, C cho legacy. Mỗi batch có quy tắc rõ ràng.

**C. Đọc raw rồi giải mã theo metadata có kiểm soát.** Lưu format version hoặc type bên ngoài payload, sau đó chọn đúng decoder cho từng key. Cách này cần chủ động quản lý kết quả và cẩn thận với hash/list lồng nhau.

Không nên đoán định dạng bằng cách thử JSON rồi ngẫu nhiên fallback sang JDK deserialization cho mọi bytes nhận được. Cách đó vừa khó đoán lỗi vừa mở rộng bề mặt rủi ro.

## 15. Khi cần đọc raw bytes, hãy định nghĩa contract riêng

Có thể viết một `RedisSerializer<byte[]>` truyền nguyên bytes:

~~~java
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.lang.Nullable;

public class RawBytesSerializer implements RedisSerializer<byte[]> {

    @Override
    public byte[] serialize(@Nullable byte[] value) {
        return value;
    }

    @Override
    public byte[] deserialize(@Nullable byte[] bytes) {
        return bytes;
    }
}
~~~

Khi kết quả là một bulk string và Spring Data Redis áp dụng serializer này, ứng dụng nhận lại `byte[]` để quyết định giải mã theo schema riêng:

~~~java
RawBytesSerializer raw = new RawBytesSerializer();

List<Object> replies = template.executePipelined(
    (RedisCallback<Object>) connection -> {
        connection.stringCommands().get(
            "format:v2:item:1".getBytes(StandardCharsets.UTF_8)
        );
        return null;
    },
    raw
);

Object first = replies.get(0);

if (first instanceof byte[] bytes) {
    // Ứng dụng có thể decode theo format version đã biết.
}
~~~

**Phạm vi:** ví dụ áp dụng cho một kết quả `GET` là bulk string. Không giả định serializer này tự biến mọi phản hồi lệnh hash, collection hoặc status thành một mảng bytes nguyên trạng; quá trình dựng cấu trúc kết quả phụ thuộc API của Spring Data Redis.

Ở các phiên bản Spring Data Redis có factory serializer byte array sẵn có, có thể dùng implementation đó thay cho lớp tự định nghĩa, miễn là contract readback giữ nguyên bytes.

## 16. So sánh executePipelined và tự mở pipeline qua RedisConnection

Có hai tầng API thường gặp.

**`RedisTemplate.executePipelined(...)`**

~~~text
RedisCallback / SessionCallback
           |
           v
RedisTemplate tổ chức pipeline
           |
           v
Redis connection nhận raw replies
           |
           v
RedisTemplate deserializes theo cấu hình
           |
           v
List<Object>
~~~

**`RedisConnection.openPipeline() / closePipeline()`**

~~~text
RedisConnection.openPipeline()
        |
        v
gửi lệnh mức thấp
        |
        v
RedisConnection.closePipeline()
        |
        v
raw driver/connection replies
~~~

Khi làm việc trực tiếp với connection, có thể cần giải mã các `byte[]` bằng chính serializer đã sử dụng. Đừng nhầm kết quả thô từ tầng connection với những gì `RedisTemplate.executePipelined` đã xử lý.

Nếu đang viết code ứng dụng sử dụng RedisTemplate, **ưu tiên cơ chế pipeline mà template cung cấp** để nhất quán với lifecycle kết nối và quy tắc serialization. Chỉ xuống tầng connection khi có lý do cụ thể và đã xác định trách nhiệm decode.

## 17. Lỗi thường gặp và cách chẩn đoán

### Lỗi 1: Đọc bytes JDK bằng StringRedisSerializer

Triệu chứng: trả ký tự vô nghĩa, ký tự thay thế hoặc lỗi ở tầng xử lý.

Nguyên nhân: dữ liệu không phải text UTF-8. Cần kiểm tra serializer lúc ghi, không cố "sửa" bằng cách đổi encoding ngẫu nhiên.

### Lỗi 2: Đọc plain text bằng JSON serializer

Triệu chứng: `SerializationException` hoặc lỗi parse JSON.

Nguyên nhân: bytes như `ACTIVE` không phải JSON string hợp lệ nếu chưa được quote theo định dạng JSON. Dùng đúng serializer hoặc migrate format.

### Lỗi 3: Phân biệt sai value và hash value

Triệu chứng: `GET` trả object đúng nhưng `HGETALL` có field/value bất thường hoặc không giải mã được.

Nguyên nhân: `hashKeySerializer`/`hashValueSerializer` khác `valueSerializer`. Xác minh riêng contract của lệnh Hash.

### Lỗi 4: Ép kiểu mọi phần tử kết quả sang String

Triệu chứng: `ClassCastException: Long cannot be cast to String` hoặc tương tự.

Nguyên nhân: các lệnh như `INCR`, `TTL`, `DEL` trả kết quả số. Dùng type theo response contract, không phụ thuộc template String.

### Lỗi 5: Dùng kết quả của lệnh trong callback ngay lập tức

Triệu chứng: `NullPointerException` hoặc nhánh điều kiện không chạy như tưởng tượng.

Nguyên nhân: lệnh đang được enqueue; reply chưa có. Tách quyết định sau pipeline hoặc chọn cơ chế atomic thích hợp.

### Lỗi 6: Callback trả về kết quả thay vì null

Triệu chứng: code khó hiểu hoặc kỳ vọng sai rằng return của callback là danh sách reply.

Nguyên nhân: giá trị return của callback không phải kênh kết quả. Trả về `null` và đọc `List<Object>` của `executePipelined`.

### Lỗi 7: Cùng một key được ghi bằng nhiều serializer

Triệu chứng: chạy đúng trên môi trường mới nhưng lỗi ở môi trường có cache cũ, hoặc chỉ lỗi một phần key.

Nguyên nhân: lịch sử dữ liệu dùng format khác. Cần namespace version, migration hoặc phân nhóm decoder có kiểm soát.

### Lỗi 8: Giả định pipeline là giao dịch

Triệu chứng: thấy một số lệnh đã thay đổi dữ liệu dù lệnh khác lỗi.

Nguyên nhân: pipeline tối ưu truyền thông, không bảo đảm all-or-nothing. Khi yêu cầu transaction, thiết kế MULTI/EXEC/Lua phù hợp; cần lưu ý cả việc parse kết quả lồng nhau.

## 18. Gợi ý thiết kế một pipeline đọc danh sách profile

Giả sử có 500 khóa `profile:ID` lưu cùng định dạng JSON và cần lấy 50 profile mỗi lần.

Thiết kế:

1. Dùng key UTF-8 theo quy tắc `profile:v2:{id}`.
2. Lưu value JSON bằng một serializer duy nhất, có schema/version ổn định.
3. Lấy danh sách ID cần thiết từ nguồn thích hợp.
4. Pipeline các lệnh `GET` của đúng 50 key.
5. Dùng cùng JSON resultSerializer để decode.
6. Ghép kết quả với ID đầu vào theo thứ tự đã xếp lệnh.
7. Xử lý `null` nếu một số key đã hết TTL.

Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;

public class ProfileBatchReader {

    private final RedisTemplate<String, Object> template;
    private final GenericJackson2JsonRedisSerializer json;

    public ProfileBatchReader(
            RedisTemplate<String, Object> template,
            GenericJackson2JsonRedisSerializer json) {
        this.template = template;
        this.json = json;
    }

    public List<Object> read(List<String> ids) {
        if (ids.isEmpty()) {
            return List.of();
        }

        return template.executePipelined(
            (RedisCallback<Object>) connection -> {
                for (String id : ids) {
                    byte[] key = ("profile:v2:" + id)
                        .getBytes(StandardCharsets.UTF_8);

                    connection.stringCommands().get(key);
                }
                return null;
            },
            json
        );
    }
}
~~~

**Lưu ý:** service giả định serializer `json` đã được cấu hình tương thích với dữ liệu tồn tại. Để dùng production, cần quản lý số lượng ID đầu vào và giới hạn batch; đồng thời map `results[i]` với `ids[i]`, xử lý key không tồn tại và exception một cách rõ ràng.

Với 50 `GET`, kết quả có thể trộn object và `null`; việc dùng `List<Object>` là thực tế hơn so với ép ngay thành `List<Profile>` mà chưa kiểm tra kiểu.

### Vấn đề thứ tự kết quả

Replies được liên kết theo thứ tự các lệnh trong pipeline. Nếu API chỉ enqueue đúng một `GET` cho mỗi ID theo thứ tự đầu vào, ứng dụng có thể dùng index để ghép.

~~~text
ids:        [p1, p2, p3]
commands:   GET p1, GET p2, GET p3
results:    [obj1, null, obj3]
~~~

Không được bỏ `null` trước khi ghép với ID, vì sẽ làm lệch vị trí của các kết quả sau. Sau khi tạo ánh xạ `id -> decoded value`, mới có thể lọc các mục không tồn tại tùy contract API.

## 19. Khi nào pipeline giúp nhanh hơn và khi nào không?

Pipeline giảm phần chi phí mạng do nhiều vòng chờ liên tiếp, nhưng vẫn có những chi phí:

~~~text
Tổng thời gian request xấp xỉ:
  thời gian serialize nhiều giá trị
+ truyền bytes đến Redis
+ Redis xử lý các lệnh
+ truyền nhiều replies về
+ deserialize kết quả
+ xử lý nghiệp vụ tại Java
~~~

Tối ưu network không làm serialization trở nên miễn phí. Dùng JSON object lớn trong pipeline có thể tốn nhiều CPU và bộ nhớ JVM; dùng các batch quá lớn có thể tạo burst bytes và gây áp lực lên Redis/client.

Một số nguyên tắc:

- Chọn batch size theo kích thước payload và mục tiêu latency, không chỉ số lệnh.
- Không pipeline hàng triệu lệnh vào một lần gọi rồi giữ toàn bộ `List<Object>` trong bộ nhớ.
- Ưu tiên các lệnh có ý nghĩa trong cùng request và cùng contract serialization.
- Nếu chỉ cần một tập khóa, cân nhắc các lệnh hỗ trợ batch phù hợp như `MGET` khi cùng kiểu value.
- Nếu cần quyết định dựa vào phản hồi trước đó, không ép mô hình tuần tự vào pipeline.
- Với Redis Cluster, pipeline có thể bị phân phối theo các node/slot tùy client; chi phí và hỗ trợ cần xét theo topology.
- Đo thời gian serialize, gửi lệnh, nhận reply và deserialize để tìm nút thắt thực sự.

### Pipeline không phải lúc nào cũng tốt hơn MGET

Nếu mục tiêu là đọc nhiều key String, `MGET` có thể trả nhiều value trong một lệnh. Pipeline nhiều `GET` hữu ích khi cần phối hợp nhiều loại lệnh hoặc khi API sẵn có không thể dùng một batch command duy nhất. Cả hai đều cần quy tắc serializer tương thích.

## 20. Chọn serializer theo tính tương thích và vòng đời dữ liệu

Khi quyết định serializer, nên hỏi:

| Câu hỏi | Vì sao quan trọng? |
| --- | --- |
| Những service nào cùng đọc dữ liệu Redis? | Java binary có thể không phù hợp service Node.js/Python |
| Value có cần tương thích nhiều phiên bản không? | DTO thay đổi có thể làm decoder cũ lỗi |
| Key có cần quan sát bằng redis-cli không? | Key serializer String dễ debug hơn binary |
| Data gồm String, JSON hay bytes tùy ý? | Mỗi loại có contract riêng |
| Có sử dụng Redis Hash? | Phải cấu hình cả hash key/hash value |
| Có pipeline trộn nhiều định dạng? | Một result serializer có thể không đủ |
| Value lớn hay nhiều lệnh trong batch? | Chi phí encode/decode và bộ nhớ là đáng kể |
| Có dữ liệu từ nguồn không đáng tin? | Deserialization cần hạn chế kiểu và validate |
| Có cần migration từ cache cũ? | Đổi serializer không tự chuyển dữ liệu đã lưu |

Một quy ước đủ rõ có thể là:

~~~text
Namespace "profile:v2:*":
  key           -> StringRedisSerializer / UTF-8
  value         -> JSON serializer đã thống nhất
  schemaVersion -> v2 ở namespace hoặc payload
  pipeline      -> chỉ đọc profile:v2, giải mã JSON

Namespace "metrics:*":
  key           -> StringRedisSerializer / UTF-8
  value         -> Redis integer commands
  pipeline      -> kết quả Long

Namespace "avatar:*":
  key           -> StringRedisSerializer / UTF-8
  value         -> raw binary
  pipeline      -> đọc bytes, decode bởi tầng ứng dụng
~~~

Với quy tắc này, người bảo trì có thể biết serializer nào dùng ở mỗi pipeline mà không phải đoán từ dữ liệu trả về.

## 21. Thực hành: tự quan sát đường đi của kết quả

Một bài tập nhỏ trong môi trường Redis thử nghiệm:

### Trường hợp A — String

~~~redis
SET demo:text "hello"
GET demo:text
~~~

Dùng `StringRedisTemplate` pipeline một lệnh `GET` và quan sát result là String khi deserialization phù hợp.

### Trường hợp B — Integer

~~~redis
SET demo:counter 0
INCR demo:counter
~~~

Pipeline `INCR`, quan sát kiểu reply số; nó không cần phải biến thành String chỉ vì template có `StringRedisSerializer`.

### Trường hợp C — Hash

~~~redis
HSET demo:hash name An status ACTIVE
HGETALL demo:hash
~~~

Cấu hình hash key/value serializer là String, sau đó quan sát map nhận được.

### Trường hợp D — JSON

Dùng JSON serializer ghi object qua API Spring Data Redis, rồi pipeline `GET` và đọc bằng serializer JSON tương thích. Đổi resultSerializer sai định dạng trong môi trường thử nghiệm để thấy vì sao việc deserialization phải tuân theo contract.

### Trường hợp E — Key không tồn tại

Pipeline hai `GET` theo thứ tự:

~~~text
GET demo:exists
GET demo:missing
~~~

Quan sát phần tử `null` và giữ vị trí của nó khi map reply về ID/key. Đừng loại `null` trước khi căn chỉnh.

## 22. Câu hỏi thường gặp

**Vì sao RedisTemplate trả List<Object> thay vì List<String>?**

Vì pipeline có thể chứa nhiều lệnh trả các kiểu khác nhau: bulk string, số nguyên, boolean, map, list hoặc null. Spring không thể bảo đảm một kiểu generic đồng nhất cho mọi reply.

**`executePipelined(..., resultSerializer)` có tự serialize value khi SET không?**

Không. Overload đó điều khiển việc giải mã kết quả thích hợp. Khi dùng RedisConnection mức thấp, lập trình viên vẫn phải tạo bytes đúng để gửi.

**Dùng StringRedisTemplate thì mọi reply đều là String?**

Không. Những reply bytes phù hợp được giải mã thành String; lệnh đếm, trạng thái hoặc dữ liệu có cấu trúc khác vẫn có kiểu theo API lệnh.

**Vì sao HGETALL có kiểu khác GET?**

Redis Hash có field/value serializer riêng, và kết quả HGETALL là map. Không nên ép map thành value đơn hay giả định hash dùng cùng serializer với GET.

**Có thể trộn JSON và String trong cùng pipeline không?**

Có thể gửi nhiều lệnh bất kỳ, nhưng nếu mọi bulk result được giải mã bằng một serializer chung thì dễ lỗi. Nên tách pipeline theo format hoặc nhận raw bytes rồi giải mã có kiểm soát.

**Vì sao GET bình thường đúng nhưng executePipelined lỗi?**

Đường đọc bình thường có thể dùng serializer cụ thể của thao tác `opsForValue`, trong khi callback mức thấp tạo bytes/serializer khác, hoặc resultSerializer pipeline không khớp format. So sánh cả chiều ghi, chiều đọc và cấu hình hash/value.

**Có thể dùng pipeline để cập nhật điều kiện trên giá trị vừa đọc?**

Không nên. Pipeline không tạo khả năng chờ và rẽ nhánh ngay trong callback dựa trên reply. Dùng hai pha có điều kiện hoặc script/transaction phù hợp với tính đúng mong muốn.

**Pipelining có nguyên tử không?**

Không. Các lệnh trong pipeline được gửi thành lô để giảm round-trip; lệnh khác vẫn có thể xen vào theo trạng thái hệ thống và không có bảo đảm all-or-nothing như giao dịch.

**Có nên dùng JDK serializer vì code ít hơn?**

Chỉ khi có lý do tương thích cụ thể và kiểm soát đầy đủ dữ liệu. JSON/String thường dễ trao đổi và quan sát hơn; JDK serialization có chi phí/giới hạn bảo mật, tương thích class và đa ngôn ngữ.

## 23. Ghi nhớ khi triển khai

- **Pipeline tối ưu giao tiếp**, không thay đổi bản chất dữ liệu bytes của Redis và không tạo transaction.
- **Serialization chiều ghi và deserialization chiều đọc là hai bước khác nhau.** `resultSerializer` không tự thay đổi các bytes được ghi bằng `RedisConnection`.
- **`executePipelined` trả `List<Object>`** vì reply có nhiều kiểu; luôn xử lý theo loại lệnh và thứ tự đã enqueue.
- **`StringRedisTemplate` phù hợp với chuỗi**, trong khi template cho DTO cần serializer có schema rõ ràng.
- **Hash có hashKeySerializer/hashValueSerializer riêng.** Không mặc định chúng giống valueSerializer.
- **Dữ liệu hỗn hợp cần chiến lược hỗn hợp.** Nên tách pipeline theo định dạng hoặc định nghĩa đường đọc raw bytes có kiểm soát.
- **Tối ưu hiệu năng cần đo cả encode/decode và bộ nhớ**, không chỉ đo số round-trip.

## Tài liệu tham khảo

- [Spring Data Redis – Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html)
- [Spring Data Redis – Serializers](https://docs.spring.io/spring-data/redis/reference/redis/serializer.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis – API RedisTemplate](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/RedisTemplate.html)
- [Spring Data Redis – API RedisSerializer](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/serializer/RedisSerializer.html)
- [Redis – Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/)
- [Redis – Data types](https://redis.io/docs/latest/develop/data-types/)
