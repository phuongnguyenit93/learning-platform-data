# Ánh xạ MapRecord, ObjectRecord và serializer tương ứng trong Spring Data Redis Streams

> **Module:** Spring Data Redis  
> **Chương:** Redis Streams  
> **Bài học:** Cách Spring Data Redis ánh xạ Redis Stream entry thành `MapRecord` hoặc `ObjectRecord`, sự khác biệt giữa `HashMapper` và `RedisSerializer`, cũng như cách cấu hình writer/reader để các bản ghi tương thích.

## 1. Redis Streams và khái niệm record

Redis Streams lưu dữ liệu dạng nhật ký các entry được thêm bằng `XADD`. Mỗi entry chứa một **Record ID** và tập hợp các cặp **field–value**. Khác với Redis Pub/Sub, entry của Stream được lưu lại cho đến khi bị xóa hoặc trim theo chính sách retention.

Ví dụ trong Redis CLI:

~~~redis
XADD events:orders * eventType order.created orderId o-101 amountMinor 125000
XRANGE events:orders - +
~~~

Phản hồi có thể giống:

~~~text
1) 1) "1794541200123-0"
   2) 1) "eventType"
      2) "order.created"
      3) "orderId"
      4) "o-101"
      5) "amountMinor"
      6) "125000"
~~~

Cần phân biệt ba thành phần:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Stream key | `events:orders` | Tên Redis key có data type là `stream` |
| Record ID | `1794541200123-0` | Định danh entry, dùng cho cursor/ACK |
| Record body | `eventType=order.created`, `orderId=o-101` | Các field–value mang dữ liệu nghiệp vụ |

Spring Data Redis diễn đạt chúng thành những Java record object, nhưng Redis server **không lưu Java object trực tiếp**. Tại Redis, cả `MapRecord` lẫn `ObjectRecord` cuối cùng đều được biểu diễn thành một entry có field và value dưới dạng bytes.

### 1.1. Sơ đồ tổng thể

~~~mermaid
flowchart TD
    APP["Publisher Java"] --> CHOICE{"Loại record"}
    CHOICE --> MAP["MapRecord: Map field/value"]
    CHOICE --> OBJ["ObjectRecord: Java object"]
    OBJ --> MAPPER["HashMapper.toHash"]
    MAPPER --> MAP
    MAP --> SERIAL["keySerializer + hashKeySerializer + hashValueSerializer"]
    SERIAL --> REDIS["Redis XADD"]
    REDIS --> READ["Redis XREAD / XREADGROUP"]
    READ --> DESERIAL["Deserialize MapRecord"]
    DESERIAL --> C1["Consumer xử lý Map trực tiếp"]
    DESERIAL --> FROM["HashMapper.fromHash"]
    FROM --> C2["Consumer xử lý ObjectRecord"]
~~~

**Hai công đoạn khác nhau:** `HashMapper` chuyển **object ↔ Map**. `RedisSerializer` chuyển **Java values ↔ bytes**. Chỉ thay một trong hai công đoạn không bảo đảm chiều còn lại tương thích.

## 2. MapRecord và ObjectRecord khác nhau ở đâu?

Những kiểu API quan trọng thuộc package `org.springframework.data.redis.connection.stream`:

- `Record<S, V>`: giao diện chung có stream key, record ID và body.
- `MapRecord<S, HK, HV>`: body là `Map<HK, HV>`.
- `ObjectRecord<S, V>`: body là object kiểu `V`.
- `StringRecord`: dạng MapRecord cho String.
- `ByteRecord` và `ByteBufferRecord`: dạng record cấp thấp cho bytes.
- `RecordId`: định danh entry, không phải một field của body.
- `StreamRecords`: tiện ích tạo các record.

| Nội dung | MapRecord | ObjectRecord |
|---|---|---|
| Body trong Java | `Map` | Object domain/DTO |
| Khai báo điển hình | `MapRecord<String,String,String>` | `ObjectRecord<String,UserEvent>` |
| Cần ánh xạ object sang field? | Không, vì body đã là Map | Có, qua mapper |
| Dễ kiểm soát tên field? | Có, tường minh | Phụ thuộc mapper/DTO |
| Dễ dùng cho nhiều ngôn ngữ? | Có nếu contract bytes rõ ràng | Tùy mapping/type metadata |
| Có thể đọc bằng Redis CLI? | Có, nếu serialization dễ đọc | Có, nhưng field và type metadata tùy mapper |
| Rủi ro khi đổi tên class Java? | Thường ít hơn | Có thể cao nếu lưu tên class trong record |
| Redis type thực tế | `stream` | `stream` |

Generic `MapRecord<String,String,String>` có nghĩa lần lượt là **kiểu stream key**, **kiểu field name**, **kiểu field value**. Generic `ObjectRecord<String,UserEvent>` có nghĩa **kiểu stream key** và **kiểu object body**. Đừng nhầm generic thứ hai của MapRecord với tên Redis key.

### 2.1. Hai biểu diễn tương đương ở tầng Redis

Ứng dụng có thể tự định nghĩa MapRecord với field:

~~~text
stream = events:orders
id = 1794541200123-0
body = {
  eventType: "order.created",
  orderId: "o-101"
}
~~~

Hoặc cung cấp một object Java và để HashMapper tạo field:

~~~text
ObjectRecord<String, OrderCreated>
    |
    +-- Mapper -> _class: com.example.OrderCreated
    +-- Mapper -> orderId: o-101
    +-- Mapper -> eventType: order.created
~~~

Dạng thứ hai là ví dụ **quy ước mapping**: tên field/metadata thực phụ thuộc mapper, không phải tính chất bắt buộc của Redis.

## 3. Ba serializer bắt buộc phải hiểu khi dùng Redis Streams

Tài liệu Spring Data Redis mô tả quy tắc serializer cho Stream như sau:

| Thành phần của entry | Serializer của RedisTemplate | Ví dụ |
|---|---|---|
| `Record#getStream()` | `keySerializer` | `events:orders` |
| Field name | `hashKeySerializer` | `eventType` |
| Field value | `hashValueSerializer` | `order.created` |

Điểm dễ nhầm: với `StreamOperations`, các field/value của record **không được lấy trực tiếp từ `valueSerializer` như một Redis String thông thường**. Chúng đi qua `hashKeySerializer` và `hashValueSerializer`. Điều này đúng cho MapRecord và cho body sau khi ObjectRecord được mapper chuyển thành Map.

Ví dụ:

~~~java
RedisTemplate<String, String> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);

template.setKeySerializer(stringSerializer);
template.setValueSerializer(jsonSerializer);
template.setHashKeySerializer(stringSerializer);
template.setHashValueSerializer(stringSerializer);
template.afterPropertiesSet();
~~~

Giả sử `jsonSerializer` là serializer được định nghĩa tương thích với generic/cấu hình ở nơi khác. Trong ví dụ này, việc đặt JSON `valueSerializer` **không khiến từng field value của Stream tự động trở thành JSON**, bởi Stream sử dụng `hashValueSerializer`.

### 3.1. Mô hình bytes

~~~text
MapRecord<String,String,String>
  stream = "events:orders"
  body = {"eventType": "order.created"}
            |
            v
  keySerializer("events:orders")
  hashKeySerializer("eventType")
  hashValueSerializer("order.created")
            |
            v
  Redis XADD: stream key bytes + field bytes + value bytes
            |
            v
  Redis XREAD trả bytes
            |
            v
  Reader deserialize bằng cùng wire format
            |
            v
  MapRecord<String,String,String>
~~~

Nếu producer dùng String serialization nhưng consumer dùng JDK serialization cho hash values, hai bên có thể kết nối đúng Redis và cùng nhìn thấy stream mà vẫn không đọc được record.

### 3.2. Các serializer phổ biến

| Serializer | Đặc tính | Lưu ý khi dùng trong stream |
|---|---|---|
| `StringRedisSerializer` | UTF-8 String | Tốt cho key, field name, field value dạng text |
| `JdkSerializationRedisSerializer` | Nhị phân phụ thuộc Java serialization | Không phù hợp làm contract mở giữa các service/ngôn ngữ |
| JSON serializer | Mã hóa từng value thành JSON | Cần consumer cùng hiểu định dạng và class/type policy |
| Byte-array/raw | Chuyển bytes ít hoặc không mã hóa thêm | Ứng dụng phải tự chịu trách nhiệm decode |
| Custom serializer | Phục vụ binary contract riêng | Cần versioning, đối chiếu writer/reader và migration |

**Generic Java không thay thế serializer.** Ví dụ khai báo `MapRecord<String,String,String>` không biến bytes JDK thành UTF-8 String một cách tự động.

### 3.3. Vì sao StringRedisTemplate dễ dùng với MapRecord?

`StringRedisTemplate` thường được cấu hình dùng String serializers cho key, value, hash key và hash value. Nó thích hợp khi mọi field/value trong Stream đã được biểu diễn thành text theo một schema tường minh.

Nếu cần nội dung là số nguyên hoặc decimal, serialize theo contract (ví dụ số tiền tính bằng đơn vị nhỏ nhất và biểu diễn bằng String) rồi parse có kiểm soát khi đọc.

## 4. Ghi MapRecord bằng StringRedisTemplate

Trong ứng dụng Spring Boot có Redis starter và `RedisConnectionFactory` phù hợp:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
~~~

Cấu hình kết nối ví dụ:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Service tạo MapRecord:

~~~java
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    public static final String STREAM = "events:orders";

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId publish(String orderId, long amountMinor) {
        Map<String, String> body = new LinkedHashMap<>();
        body.put("eventType", "order.created");
        body.put("schemaVersion", "1");
        body.put("orderId", orderId);
        body.put("amountMinor", Long.toString(amountMinor));
        body.put("occurredAt", Instant.now().toString());

        MapRecord<String, String, String> record =
                MapRecord.create(STREAM, body);

        return redis.opsForStream().add(record);
    }
}
~~~

**Các bước:** `MapRecord.create(...)` tạo record Java; `opsForStream().add(...)` gửi `XADD`; Redis trả `RecordId`. `schemaVersion` là field nghiệp vụ do application tự định nghĩa. Redis không tự cấp schema version.

### 4.1. Các cách tạo MapRecord

~~~java
Map<String, String> fields =
        Map.of("eventType", "order.created",
               "orderId", "o-101");

MapRecord<String, String, String> first =
        MapRecord.create("events:orders", fields);

MapRecord<String, String, String> second =
        StreamRecords.<String, String, String>mapBacked(fields)
                .withStreamKey("events:orders");
~~~

Một cách khác là `StreamRecords.string(fields).withStreamKey("events:orders")`, trả về `StringRecord`. Các factory chỉ **tạo object record**, không tự lưu Redis cho đến khi gọi `add(...)`.

### 4.2. Đọc MapRecord

~~~java
import java.util.List;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderEventReader {

    private final StringRedisTemplate redis;

    public OrderEventReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<MapRecord<String, String, String>> readBeginning() {
        List<MapRecord<String, String, String>> result =
                redis.opsForStream().read(
                        StreamReadOptions.empty().count(20),
                        StreamOffset.create(
                                OrderEventPublisher.STREAM,
                                ReadOffset.from("0-0")));

        return result == null ? List.of() : result;
    }
}
~~~

`ReadOffset.from("0-0")` phù hợp minh họa đọc lại các entry từ đầu. Trong ứng dụng xử lý liên tục phải quản lý offset hoặc consumer group, nếu không có thể đọc lại cùng lịch sử nhiều lần.

Sử dụng record:

~~~java
for (MapRecord<String, String, String> record : records) {
    RecordId recordId = record.getId();
    String streamName = record.getStream();
    Map<String, String> body = record.getValue();

    String eventType = body.get("eventType");
    String orderId = body.get("orderId");
    long amountMinor = Long.parseLong(
            body.get("amountMinor"));

    // Validate, dispatch event và xử lý nghiệp vụ.
}
~~~

Phải xử lý thiếu field, schemaVersion lạ và giá trị số không hợp lệ. Một MapRecord deserialize thành công chỉ xác nhận bytes đọc được, **không** xác nhận dữ liệu đúng nghiệp vụ.

### 4.3. Đối chiếu với Redis CLI

~~~bash
redis-cli TYPE events:orders
redis-cli XLEN events:orders
redis-cli XRANGE events:orders - + COUNT 10
~~~

`TYPE` trả `stream`, không phải `hash`. Dù Stream entry có field–value, bạn không thể thay `XRANGE` bằng `HGETALL events:orders`; Redis sẽ trả lỗi kiểu dữ liệu.

## 5. Tự cấu hình RedisTemplate cho stream văn bản

`StringRedisTemplate` không phải lựa chọn duy nhất. Nếu cần template riêng cho stream, nên cấu hình đúng **cả stream key và hash serializers**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class TextStreamConfiguration {

    @Bean("textStreamTemplate")
    RedisTemplate<String, String> textStreamTemplate(
            RedisConnectionFactory connectionFactory) {

        StringRedisSerializer strings = new StringRedisSerializer();

        RedisTemplate<String, String> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(strings);
        template.setValueSerializer(strings);
        template.setHashKeySerializer(strings);
        template.setHashValueSerializer(strings);
        template.afterPropertiesSet();

        return template;
    }
}
~~~

Ở đây `setValueSerializer(strings)` giúp các Redis operations khác đồng nhất, nhưng với Stream fields, thứ quan trọng là `hashKeySerializer` và `hashValueSerializer`.

Khi có nhiều bean RedisTemplate, chọn đúng bean qua `@Qualifier("textStreamTemplate")`. Khai báo một template mới không tự khiến các consumer/RedisMessageListenerContainer đang tồn tại dùng serializer mới.

### 5.1. Điểm dễ lỗi: đổi serializer sau khi đã có dữ liệu

Ví dụ:

- Tuần 1, producer ghi String field value bằng UTF-8.
- Tuần 2, code đổi hashValueSerializer sang JDK hoặc JSON.
- Redis Stream vẫn chứa entry cũ từ tuần 1.
- Consumer mới cố giải mã tất cả bằng format tuần 2.

Kết quả có thể là lỗi deserialization hoặc những giá trị khác logic ban đầu. **Đổi RedisTemplate serializer là một thay đổi wire format**, không tự chuyển đổi dữ liệu lịch sử.

Nếu stream có retention dài, cần kế hoạch dùng stream mới, reader đọc nhiều format hoặc migration rõ ràng.

## 6. ObjectRecord: Spring biểu diễn body bằng Java object

Thay vì dựng Map thủ công, có thể tạo `ObjectRecord`:

~~~java
ObjectRecord<String, String> record =
        StreamRecords.newRecord()
                .in("events:simple")
                .ofObject("hello");

redisTemplate.opsForStream().add(record);

List<ObjectRecord<String, String>> result =
        redisTemplate.opsForStream().read(
                String.class,
                StreamOffset.fromStart("events:simple"));
~~~

`redisTemplate` ở đây là template đã cấu hình tương thích cho stream/object mapping. Theo quy ước mapping mặc định trong Spring Data Redis, một simple value có thể được chuyển thành các field:

~~~redis
XADD events:simple * _class java.lang.String _raw hello
~~~

`_class` và `_raw` là field metadata của quy ước Spring, **không phải** field đặc biệt Redis bắt buộc phải có.

### 6.1. ObjectRecord với domain object

Giả sử domain event Java:

~~~java
public class UserLoggedIn {

    private String username;
    private String device;

    public UserLoggedIn() {
    }

    public UserLoggedIn(String username, String device) {
        this.username = username;
        this.device = device;
    }

    public String getUsername() { return username; }
    public String getDevice() { return device; }

    public void setUsername(String username) {
        this.username = username;
    }

    public void setDevice(String device) {
        this.device = device;
    }
}
~~~

Gửi và đọc typed record:

~~~java
ObjectRecord<String, UserLoggedIn> record =
        StreamRecords.newRecord()
                .in("events:user-logon")
                .ofObject(new UserLoggedIn("night", "mobile"));

RecordId id = redisTemplate.opsForStream().add(record);

List<ObjectRecord<String, UserLoggedIn>> messages =
        redisTemplate.opsForStream().read(
                UserLoggedIn.class,
                StreamOffset.fromStart("events:user-logon"));
~~~

Lợi ích là handler không cần gọi `Map.get("username")`, nhưng sự tiện lợi phụ thuộc mapper hiểu đúng object.

Một mapping có thể tạo các field:

~~~text
_class   = com.example.UserLoggedIn
username = night
device   = mobile
~~~

Tên và biểu diễn thực tế có thể khác theo `HashMapper`/`RedisConverter`/version. Không nên giả định `ObjectRecord` được ghi thành một JSON String duy nhất.

## 7. HashMapper: bước chuyển đổi riêng biệt

`HashMapper<T, HK, HV>` là hợp đồng object ↔ Map.

~~~text
GHI:
  UserLoggedIn
       |
       v
  HashMapper.toHash(object)
       |
       v
  Map<HK, HV>
       |
       v
  RedisSerializer (stream key, hash key, hash value)
       |
       v
  Redis XADD

ĐỌC:
  Redis XREAD
       |
       v
  RedisSerializer.deserialize
       |
       v
  Map<HK, HV>
       |
       v
  HashMapper.fromHash(map)
       |
       v
  UserLoggedIn
~~~

Spring Data Redis dùng `ObjectHashMapper` làm mapper mặc định cho object records theo tài liệu Streams. Bạn có thể cung cấp mapper khác qua `opsForStream(hashMapper)` khi cần conversion có chủ đích.

### 7.1. ObjectHashMapper

`ObjectHashMapper` kết hợp các quy tắc Spring Data mapping và RedisConverter để chuyển các property của object thành hash fields/values. Nó thường làm việc với `Map<byte[],byte[]>` tại tầng chuyển đổi.

Các điểm cần hiểu:

- Mapper có thể lưu type metadata, ví dụ `_class`.
- Các property nested có thể tạo nhiều field theo path.
- Converter/custom conversions có thể thay đổi representation.
- Đọc lại object cần matching mapping context, constructor/setter và converter.
- Nếu mapper tạo `byte[]` mà một serializer lại cố xử lý như `String`, cấu hình có thể không hợp lệ.

**Không chọn một StringRedisTemplate chỉ vì stream key là String rồi mặc định ObjectHashMapper cũng trả String fields.** Phải xác định kiểu do mapper tạo và serializer tương ứng cho cả hai chiều.

### 7.2. JacksonHashMapper

`JacksonHashMapper` tạo Map từ object qua Jackson, có lựa chọn hierarchical hoặc flatten. Ví dụ:

~~~json
{
  "username": "night",
  "address": {
    "city": "Hanoi",
    "country": "VN"
  }
}
~~~

Hai kiểu mapping:

| Hierarchical | Flat |
|---|---|
| `username=night` | `username=night` |
| `address={"city":"Hanoi","country":"VN"}` | `address.city=Hanoi` |
| — | `address.country=VN` |

Trong chế độ flat, dấu chấm hoặc ngoặc vuông trong tên field/path có thể gây vấn đề, và dữ liệu đã flatten có thể không dựng lại object một cách trọn vẹn. Cần cân nhắc việc **đọc ngược** trước khi chọn flatten.

API khởi tạo Jackson mapper đã có thay đổi giữa các thế hệ Spring Data Redis/Jackson: có tài liệu cũ dùng `Jackson2HashMapper` hoặc constructor với tham số `boolean flatten`, trong khi phiên bản mới có `JacksonHashMapper` builder/factory khác. Đọc đúng Javadoc của phiên bản trong dự án trước khi sao chép code.

### 7.3. Tùy chỉnh mapper trong StreamOperations

Dạng API theo tài liệu:

~~~java
// Một HashMapper phù hợp đã được tạo và cấu hình.
// Có thể gắn vào StreamOperations khi thao tác ObjectRecord.

redisTemplate.opsForStream(customHashMapper).add(objectRecord);
~~~

Đoạn này minh họa chỗ mở rộng; `customHashMapper` và `objectRecord` phải có generic/format tương thích với template được sử dụng.

Nếu một consumer dùng mapper khác producer, nó có thể không đọc được record, dù cả hai cùng dùng RedisTemplate và stream key giống nhau.

## 8. Đọc ObjectRecord từ MapRecord

Khi Redis trả một entry, Spring có thể deserialize thành `MapRecord`. Nếu yêu cầu target class, lớp mapping có thể chuyển record thành `ObjectRecord` tương ứng.

~~~text
Redis bytes -> MapRecord
                   |
                   +--> Consumer tự xử lý Map
                   |
                   +--> HashMapper.fromHash
                                   |
                                   v
                             ObjectRecord
~~~

Vì thế, một record được ghi từ ObjectRecord vẫn có thể được đọc ở dạng MapRecord khi các bytes được giải mã đúng. Tuy nhiên chiều ngược **không tùy tiện**: một MapRecord chứa `payload` JSON không tự động trở thành bất kỳ POJO nào thông qua ObjectHashMapper mặc định.

Spring `StreamOperations` có API mapping MapRecord → ObjectRecord theo target type, nhưng target mapper phải hiểu field representation mà writer tạo ra.

### 8.1. RecordId được giữ riêng

Mỗi MapRecord hoặc ObjectRecord đều có `getStream()` và `getId()`. Khi chuyển từ Map sang object, metadata này phải tiếp tục phục vụ offset và ACK.

~~~text
stream    = events:orders
recordId  = 1794541200123-0
body      = {orderId=o-101, eventType=order.created}
~~~

`recordId` không nằm trong `getValue()` trừ khi ứng dụng tự ghi một field khác để lưu business ID. Hãy phân biệt Redis RecordId với `eventId` của domain event dùng để deduplicate.

## 9. MapRecord nhiều field và JSON một field

Đối với hệ thống dùng nhiều ngôn ngữ, hai contract phổ biến đều dùng MapRecord.

### 9.1. Nhiều field độc lập

~~~redis
XADD events:orders * eventType order.created schemaVersion 1 orderId o-101 amountMinor 125000
~~~

Ưu điểm: dễ đọc bằng CLI, tường minh field, đơn giản với StringRedisTemplate.

Nhược điểm: phải thống nhất cách biểu diễn số/ngày giờ và object lồng nhau; consumer tự parse/validate.

### 9.2. Một field chứa JSON

~~~redis
XADD events:orders * payload "{\"eventType\":\"order.created\",\"schemaVersion\":1,\"orderId\":\"o-101\",\"amountMinor\":125000}"
~~~

Ưu điểm: schema JSON có thể chứa nested objects/arrays, contract tương thích đa ngôn ngữ và dễ versioning.

Nhược điểm: consumer cần JSON parser; Redis không biết các property bên trong field `payload`.

Ví dụ Java:

~~~java
String json = objectMapper.writeValueAsString(eventDto);

RecordId id = stringRedisTemplate.opsForStream().add(
        "events:orders",
        Map.of(
                "contentType", "application/json",
                "payload", json));
~~~

`eventDto` là DTO domain của ứng dụng; `objectMapper` là Jackson mapper tương ứng. Lệnh `add` vẫn ghi một MapRecord; Jackson chỉ mã hóa payload **trước** khi đưa vào StringRedisTemplate.

### 9.3. Khi nào nên chọn mỗi cách?

| Nhu cầu | Lựa chọn khuyến nghị |
|---|---|
| Số lượng field ít, toàn text, consumer đa ngôn ngữ | MapRecord field–value |
| Nested payload phức tạp, cần schema contract | MapRecord chứa JSON |
| DTO Java nội bộ, converter được kiểm soát | ObjectRecord |
| Cần tối ưu binary contract riêng | ByteRecord/custom serializer được công bố |
| Stream tồn tại lâu, nhiều phiên bản reader | Contract có schemaVersion và backward compatibility |
| Consumer không biết Java class của producer | Tránh phụ thuộc type metadata Java |

`ObjectRecord` **không đồng nghĩa JSON**; nó là một Java representation và có thể phát sinh nhiều field theo mapper.

## 10. Ánh xạ trong consumer group và ACK

Redis Streams có consumer groups. `XREADGROUP` phân phối entry cho consumer; Redis duy trì Pending Entries List (PEL) cho những entry đã được giao nhưng chưa ACK.

MapRecord hay ObjectRecord **không làm thay đổi** ý nghĩa của ACK: consumer phải dùng record ID để xác nhận sau khi xử lý thành công.

Ví dụ đọc bằng MapRecord:

~~~java
import java.util.List;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;

List<MapRecord<String, String, String>> records =
        stringRedisTemplate.opsForStream().read(
                Consumer.from("orders-group", "worker-1"),
                StreamReadOptions.empty().count(10),
                StreamOffset.create(
                        "events:orders",
                        ReadOffset.lastConsumed()));
~~~

Group cần tồn tại trước khi đọc. Với record được xử lý xong:

~~~java
for (MapRecord<String, String, String> record : records) {
    handleOrderEvent(record.getValue());

    stringRedisTemplate.opsForStream()
            .acknowledge("orders-group", record);
}
~~~

`handleOrderEvent` là phương thức nghiệp vụ do ứng dụng cung cấp. Cần kiểm tra null list, các trường hợp decode lỗi, retry và idempotency.

**Không ACK trước khi xử lý** nếu yêu cầu retry khi handler lỗi. ACK không xóa nội dung stream; nó loại record khỏi danh sách pending của group. Retention của Stream được quản lý riêng bởi trimming như `XTRIM`.

### 10.1. Lỗi object mapping và các pending entries

Nếu listener đọc trực tiếp ObjectRecord nhưng không deserialize được vì metadata hoặc class không tồn tại, handler có thể chưa nhận được record để xử lý/ACK. Khi đó, record có thể còn pending và cần cơ chế xử lý lỗi phù hợp.

Đối với event cần hỗ trợ nhiều schema versions, một chiến lược là:

1. Đọc dạng MapRecord/bytes có kiểm soát.
2. Kiểm tra `schemaVersion` và `eventType`.
3. Dùng đúng parser/mapper cho phiên bản.
4. Validate dữ liệu nghiệp vụ.
5. Thực hiện side effect idempotent.
6. ACK khi xử lý được xác nhận hoàn tất.
7. Với record lỗi, áp dụng retry, quarantine/dead-letter hoặc đối soát theo chính sách nghiệp vụ.

Redis Streams có khả năng đọc lại entry còn lưu, nhưng **không tự đảm bảo exactly-once side effects**. Một worker có thể xử lý thành công rồi crash trước ACK, khiến entry được nhận lại.

### 10.2. ReadOffset phải được hiểu đúng

- `ReadOffset.from("0-0")`: bắt đầu đọc từ ID đã chỉ định (sau ID đó), hay dùng khi thử đọc lịch sử.
- `ReadOffset.latest()`: đọc các entry mới kể từ vị trí cuối theo semantics cụ thể; có thể có khoảng trống giữa các lượt poll.
- `ReadOffset.lastConsumed()`: dùng phổ biến với consumer group để đọc tiếp từ vị trí đã tiêu thụ.

Dữ liệu pending sau crash cần được xử lý theo cơ chế pending/reclaim phù hợp, không chỉ dùng `lastConsumed()` và cho rằng mọi pending entry sẽ tự được phát lại như message mới.

## 11. StreamMessageListenerContainer và serializer

Spring Data Redis cung cấp `StreamMessageListenerContainer` cho mô hình imperative polling/dispatch, và `StreamReceiver` cho reactive. Cả hai vẫn phải giải mã key, field và value thành record.

Một listener MapRecord:

~~~java
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.stream.StreamListener;

public class OrderStreamListener
        implements StreamListener<
                String, MapRecord<String, String, String>> {

    @Override
    public void onMessage(
            MapRecord<String, String, String> message) {
        System.out.println("Stream: " + message.getStream());
        System.out.println("Id: " + message.getId());
        System.out.println("Body: " + message.getValue());
    }
}
~~~

Container minh họa:

~~~java
import java.time.Duration;

import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.data.redis.stream.StreamMessageListenerContainer
        .StreamMessageListenerContainerOptions;

StreamMessageListenerContainerOptions<
        String, MapRecord<String, String, String>> options =
        StreamMessageListenerContainerOptions.builder()
                .pollTimeout(Duration.ofMillis(100))
                .build();

StreamMessageListenerContainer<
        String, MapRecord<String, String, String>> container =
        StreamMessageListenerContainer.create(
                connectionFactory, options);

container.receive(
        StreamOffset.fromStart("events:orders"),
        new OrderStreamListener());

container.start();
~~~

Đoạn cấu hình nằm trong ngữ cảnh có `connectionFactory` phù hợp; ứng dụng Spring nên quản lý container như bean với lifecycle và error handler thích hợp.

### 11.1. Container không tự “thừa hưởng” serializer của publisher

Một lỗi phổ biến:

- Publisher gửi MapRecord bằng `StringRedisTemplate` dùng UTF-8 String serialization.
- Listener container được tạo riêng từ `RedisConnectionFactory` với options/default codecs khác.
- Container deserialize field/value không đúng, dù `opsForStream().read(...)` qua StringRedisTemplate vẫn hoạt động.

Hãy chọn serializer và mapper phù hợp cho **cả writer, reader trực tiếp và listener container**. Không suy luận container tự dùng serializer của một template bean khác chỉ vì cùng RedisConnectionFactory.

### 11.2. ObjectRecord listener cần mapper phù hợp

API options của listener container hỗ trợ mapper object:

~~~java
StreamMessageListenerContainerOptions<
        String, ObjectRecord<String, Object>> options =
        StreamMessageListenerContainerOptions.builder()
                .objectMapper(objectHashMapper)
                .build();
~~~

`objectHashMapper` được tạo với conversion context phù hợp. Đặc biệt khi dùng `@TypeAlias`, listener container có thể cần RedisMappingContext biết trước các domain types để resolve alias.

### 11.3. Reactive StreamReceiver

`StreamReceiver` dùng Reactive Redis connection factory và phát record qua `Flux`. Khác biệt về async/polling/backpressure không thay đổi yêu cầu **đúng serializer và object mapper**.

Nếu reactive reader tạm dừng polling và dùng `ReadOffset.latest()`, có nguy cơ bỏ lỡ entry xuất hiện trong khoảng giữa những lần poll. Cần chọn offset strategy và group semantics theo yêu cầu xử lý. Với consumer group, vẫn phải xét ACK, pending và recovery.

## 12. Type metadata, @TypeAlias và việc đổi Java class

`ObjectHashMapper` có thể lưu thông tin kiểu dưới field `_class`. Nếu dữ liệu lưu:

~~~text
_class = com.example.events.UserLoggedIn
~~~

nhưng lần deploy sau đổi thành:

~~~text
com.example.contract.UserLoggedIn
~~~

record cũ có thể không map ngược được nếu converter vẫn mong tên class trước. Stream có lịch sử nên việc refactor Java package có thể ảnh hưởng những entry cũ.

`@TypeAlias` có thể cho phép dùng tên alias ổn định hơn trong những trường hợp mapping hỗ trợ. Tuy nhiên consumer cần mapping context đã đăng ký type/alias đó. Spring Data Redis lưu ý listener container có thể chưa biết những alias này nếu không được khởi tạo với `initialEntitySet` tương ứng.

Ví dụ cấu hình định hướng:

~~~java
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.convert.MappingRedisConverter;
import org.springframework.data.redis.core.convert.RedisConverter;
import org.springframework.data.redis.core.mapping.RedisMappingContext;
import org.springframework.data.redis.hash.ObjectHashMapper;

@Configuration
public class ObjectStreamMappingConfiguration {

    @Bean
    RedisMappingContext redisMappingContext() {
        RedisMappingContext context = new RedisMappingContext();
        context.setInitialEntitySet(Set.of(UserLoggedIn.class));
        return context;
    }

    @Bean
    RedisConverter redisConverter(RedisMappingContext context) {
        return new MappingRedisConverter(context);
    }

    @Bean
    ObjectHashMapper streamObjectHashMapper(RedisConverter converter) {
        return new ObjectHashMapper(converter);
    }
}
~~~

Với Spring Boot có sẵn mapping/converter bean cho Redis Repository, không tự tạo thêm bean trùng nếu chưa hiểu wiring. Các config snippets là lựa chọn định hướng cần ghép vào dự án có package/import và phiên bản thư viện phù hợp.

**Một alias ổn định không thay thế schema version.** Nó cũng không giải quyết tự động việc đổi tên field, đổi kiểu hoặc đổi semantics của dữ liệu.

## 13. Tiến hóa schema và thay đổi mapping

Một stream có thể chứa record do nhiều phiên bản producer tạo ra. Ví dụ:

**Schema v1:**

~~~text
eventType = order.created
schemaVersion = 1
orderId = o-101
amountMinor = 125000
~~~

**Schema v2:**

~~~text
eventType = order.created
schemaVersion = 2
orderId = o-101
amountMinor = 125000
salesChannel = WEB
~~~

Consumer MapRecord có thể dispatch tường minh:

~~~java
Map<String, String> body = record.getValue();

int schemaVersion = Integer.parseInt(
        body.getOrDefault("schemaVersion", "0"));

switch (schemaVersion) {
    case 1 -> handleV1(body);
    case 2 -> handleV2(body);
    default -> handleUnsupported(body, record.getId());
}
~~~

Các handler là logic do ứng dụng viết. Với ObjectRecord, nếu v2 đổi DTO hoặc HashMapper, một mapper duy nhất có thể không đủ để đọc cả v1 và v2. Cân nhắc đọc raw MapRecord trước rồi map theo version, hoặc giữ serializer/mapper tương thích với lịch sử.

### 13.1. Đổi ObjectHashMapper sang JacksonHashMapper

Đây có thể là breaking change, không chỉ là đổi “cách đọc JSON”:

- Metadata `_class` và `@class` có thể khác nhau.
- Nested properties có thể lưu theo path khác.
- Kiểu value trả về có thể là bytes hoặc object/string tùy mapper.
- Consumer cũ có thể thiếu converters/aliases để đọc data mới.

Tài liệu về mapping không hứa các mapper tạo wire format tương đương. Do đó phải có chiến lược versioning hoặc migration nếu Stream vẫn giữ dữ liệu cũ.

### 13.2. Đừng để Java class quyết định event contract công khai

Nếu Stream được dùng bởi Python/Node/Go service, các consumer đó không biết cách instantiate `com.example.UserLoggedIn`. Chúng chỉ thấy field/value. Với kiến trúc đa ngôn ngữ, ưu tiên hợp đồng như:

~~~json
{
  "eventType": "user.logged-in",
  "schemaVersion": 1,
  "eventId": "e-123",
  "userId": "u-101",
  "device": "mobile"
}
~~~

Publisher có thể biến DTO thành JSON qua Jackson trước, rồi gửi JSON như một String field trong MapRecord. Cách này tách event contract khỏi type metadata của Spring Data Redis.

## 14. Những lỗi serialization dễ gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
|---|---|---|
| Field name hiện bytes khó đọc | `hashKeySerializer` khác String | Đồng bộ với publisher |
| Stream key đọc không thấy | `keySerializer` khác nhau, nhầm Redis DB/endpoint | Kiểm tra raw key và connection |
| Value bị thừa dấu nháy JSON | Writer JSON serializer, reader String serializer | Dùng decoder tương ứng |
| `ClassCastException` khi đọc MapRecord | Hash value được decode thành kiểu khác generic mong muốn | Đối chiếu serializer và loại dữ liệu |
| Không thể map thành ObjectRecord | HashMapper đọc khác mapper ghi | Dùng cùng conversion contract |
| Lỗi do class Java đã đổi package | Type metadata chứa FQCN cũ | Alias, compatibility reader hoặc migration |
| Object mapping mất property | Field name/constructor/converter không khớp | Kiểm tra mapping metadata |
| Flattened object không đọc ngược | Giới hạn tên field/path hoặc mapper flat | Chọn hierarchical/contract tường minh |
| Listener thất bại nhưng read thủ công thành công | Container có mapper/serializer khác | Kiểm tra container options |
| Group pending không giảm | Handler không ACK hoặc decode lỗi | Xem `XPENDING`, policy retry |
| Cùng event xử lý nhiều lần | Retry/reclaim hoặc publisher gửi lặp | Idempotency và business eventId |

### 14.1. Không nhầm Redis Stream với Redis Hash

Stream entry có field–value tương tự Hash, nhưng key vẫn là `stream`. `opsForHash()` và `opsForStream()` là hai API khác nhau.

~~~bash
redis-cli TYPE events:orders
# stream

redis-cli XRANGE events:orders - + COUNT 5
# Đọc Stream entries

redis-cli HGETALL events:orders
# WRONGTYPE nếu key là stream
~~~

### 14.2. Không nhầm RecordId với payload

`RecordId` là metadata của entry, không phải field tự động được đưa vào `getValue()`. Nếu cần business eventId để deduplicate xuyên nhiều stream, hãy đặt field `eventId` riêng trong body.

### 14.3. Không nhầm đổi valueSerializer với đổi MapRecord body

Thay `RedisTemplate.setValueSerializer(...)` không tự thay đổi body serialization của `StreamOperations`, vì Stream fields dùng `hashValueSerializer`. Phải kiểm tra đúng tầng.

### 14.4. Không nhầm ObjectRecord với JSON document

`ObjectRecord` có thể tạo nhiều field/value qua ObjectHashMapper. Nếu yêu cầu JSON một field, hãy encode JSON tường minh hoặc định nghĩa mapper phù hợp. Việc dùng một object Java trong API không chứng minh bytes trên Redis là JSON.

## 15. Bảo mật và khả năng xử lý lại

Một Redis Stream record có thể đến từ producer khác, có thể tồn tại lâu và có thể được replay. Vì vậy cần:

- Validate dữ liệu và `schemaVersion` sau deserialize.
- Chỉ chấp nhận các DTO/alias được định nghĩa.
- Hạn chế polymorphic type instantiation và native Java deserialization trên dữ liệu không tin cậy.
- Không ghi raw payload chứa PII/secrets vào log.
- Giới hạn kích thước và độ phức tạp của JSON.
- Sử dụng Redis ACL/TLS và tách quyền producer–consumer.
- Thiết kế handler idempotent vì retry/reclaim có thể xử lý lại cùng record.
- Chỉ ACK khi hoàn tất xử lý hoặc sau khi quyết định chính sách xử lý lỗi đã được ghi nhận.

Redis Streams có retention và consumer groups, nhưng không có bảo đảm exactly-once side effects chỉ vì dùng `XACK`. Nếu xử lý thành công rồi crash trước ACK, event có thể được nhận lại.

### 15.1. TTL của Stream key không phải TTL của từng entry

Nếu gọi `EXPIRE events:orders 3600`, Redis sẽ đặt TTL lên **toàn bộ Stream key**. Khi key hết hạn, toàn bộ entries biến mất. Muốn giới hạn số lượng/tuổi entries của Stream, dùng retention và trimming (`XTRIM`, `MAXLEN`, `MINID` nếu phiên bản Redis hỗ trợ). Không xem từng MapRecord/ObjectRecord như Redis key độc lập có TTL riêng.

## 16. Chẩn đoán theo từng tầng

Một quy trình ngắn:

1. **Key có đúng Redis type không?** Dùng `TYPE`, `XLEN`.
2. **Record tồn tại không?** Dùng `XRANGE`/`XREVRANGE`.
3. **Stream key có decode đúng?** Kiểm tra `keySerializer`.
4. **Field name và value có đúng?** Kiểm tra `hashKeySerializer` và `hashValueSerializer`.
5. **MapRecord đúng nhưng ObjectRecord lỗi?** Kiểm tra HashMapper, converter, metadata, target class.
6. **Reader thủ công được nhưng listener lỗi?** Kiểm tra listener options, offset, group và lifecycle.
7. **Handler xử lý trùng hoặc mất dữ liệu?** Kiểm tra ACK, pending, reclaim, idempotency và retention.

Các lệnh CLI hữu ích trên môi trường thử nghiệm:

~~~bash
redis-cli TYPE events:orders
redis-cli XLEN events:orders
redis-cli XRANGE events:orders - + COUNT 10
redis-cli XREVRANGE events:orders + - COUNT 10
redis-cli XINFO STREAM events:orders
redis-cli XINFO GROUPS events:orders
redis-cli XPENDING events:orders orders-group
~~~

Các lệnh `XINFO GROUPS`/`XPENDING` cần nhóm phù hợp. Với serializer nhị phân, Redis CLI có thể hiển thị escaped bytes — đó chưa chắc là dữ liệu hỏng.

### 16.1. Metrics nên quan sát

- Tốc độ `XADD` và `XREADGROUP`.
- Độ dài Stream và kích thước trung bình record.
- Số lỗi serializer/deserializer và không hỗ trợ schemaVersion.
- Pending entries, age và số lần reclaim.
- Thời gian xử lý handler và ACK failure.
- Số message xử lý trùng theo eventId.
- Redis latency, memory và connection failures.

Không dùng recordId/eventId làm metric label do cardinality cao; chúng phù hợp trong structured logs/traces có giới hạn.

## 17. Ma trận quyết định sử dụng

| Use case | Kiểu record nên cân nhắc | Serialization |
|---|---|---|
| Event đơn giản giữa nhiều ngôn ngữ | MapRecord | UTF-8 String field/value |
| Event có object nested, versioned schema | MapRecord với `payload` JSON | UTF-8 String + JSON parser |
| Java-only worker xử lý domain DTO | ObjectRecord | HashMapper và hash serializers đồng bộ |
| Ánh xạ nested object thành nhiều field | ObjectRecord + mapper phù hợp | Chọn hierarchical/flat cẩn thận |
| Protocol bytes gọn, custom binary | ByteRecord/MapRecord | Binary contract có version |
| Stream lịch sử dài, đa version | MapRecord/raw → version dispatcher | Giữ reader cho định dạng cũ |

Câu hỏi nên đặt trước khi chọn: **Ai sẽ đọc record, nó tồn tại bao lâu và publisher/consumer có được deploy độc lập không?** Nếu các service không cùng ngôn ngữ hoặc nâng cấp khác lịch, wire format độc lập Java thường quan trọng hơn việc ObjectRecord giúp code publisher ngắn thêm vài dòng.

## 18. Câu hỏi thường gặp

**MapRecord và ObjectRecord có phải hai kiểu dữ liệu Redis khác nhau không?**  
Không. Cả hai được lưu dưới dạng Stream entry field–value; khác ở representation Java và bước object mapping.

**Stream field value được ghi qua valueSerializer hay hashValueSerializer?**  
Qua `hashValueSerializer` của RedisTemplate trong StreamOperations thông thường.

**ObjectRecord có tự biến object thành JSON không?**  
Không mặc định như vậy. Nó có thể tạo Map fields qua `ObjectHashMapper`, kèm type metadata.

**Có thể đọc ObjectRecord thành MapRecord không?**  
Có nếu reader deserialize được field/value; body trên Redis vẫn là field–value.

**MapRecord có tự map thành một DTO bất kỳ không?**  
Không. Mapper phải hiểu đúng format; một field `payload` JSON cần parser hoặc mapping riêng.

**Vì sao đọc bằng StringRedisTemplate được nhưng listener container thất bại?**  
Có thể container dùng serializer/mapper khác template. Hai luồng phải được cấu hình đồng bộ.

**Đổi Java class name có ảnh hưởng dữ liệu stream cũ không?**  
Có thể ảnh hưởng nếu ObjectHashMapper lưu metadata kiểu dựa trên tên class. Cần alias, reader tương thích hoặc migration.

**ACK có phụ thuộc MapRecord hay ObjectRecord?**  
Không. ACK dùng Redis Record ID và consumer group. Điều quan trọng là chỉ ACK khi chính sách xử lý cho phép.

**StringRedisTemplate có thể ghi JSON không?**  
Có. Serialize DTO sang JSON String trước rồi ghi field `payload` bằng StringRedisTemplate. JSON được parse bởi consumer, không phải Redis server.

**Redis Stream entry có TTL riêng không?**  
Không theo nghĩa một Redis key riêng. Expire trên stream key xóa toàn bộ stream; retention của entry dùng trimming.

## 19. Tổng kết

**`MapRecord` biểu diễn field–value rõ ràng; `ObjectRecord` biểu diễn Java object và cần `HashMapper` để chuyển thành field–value.** Cả hai được lưu dưới dạng Redis Streams, không có hai loại Stream khác nhau ở phía Redis.

Trong Spring Data Redis Streams, quy tắc serializer phải nhớ là:

- `Record#getStream()` → **`keySerializer`**.
- Tên field → **`hashKeySerializer`**.
- Giá trị field → **`hashValueSerializer`**.

`valueSerializer` của RedisTemplate không phải serializer mặc định cho từng field value của Stream. Với ObjectRecord, còn phải bảo đảm `HashMapper`/`RedisConverter`/`@TypeAlias` tương thích ở cả phía ghi và đọc. Khi stream giữ lịch sử lâu, mọi thay đổi serializer, mapper hoặc class metadata đều là thay đổi contract cần chiến lược versioning.

Đối với dữ liệu đa ngôn ngữ và contract công khai, một **MapRecord dùng UTF-8 String hoặc JSON payload có schemaVersion** thường dễ tiến hóa. Đối với ứng dụng Java kiểm soát toàn bộ producer/consumer, **ObjectRecord** có thể tiện hơn nếu mapping/serialization được thống nhất. Dù chọn kiểu nào, hãy quản lý rõ RecordId, ACK, error handling, idempotency và retention.

## Tài liệu tham khảo

- Spring Data Redis — [Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): record, serializers, object mapping, listeners và consumer groups.
- Spring Data Redis — [StreamOperations API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/StreamOperations.html): thêm, đọc, map và acknowledge record.
- Spring Data Redis — [MapRecord API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/stream/MapRecord.html): `MapRecord` và serialization.
- Spring Data Redis — [StreamRecords API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/stream/StreamRecords.html): các factory tạo record.
- Spring Data Redis — [Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/hash-mappers.html): `ObjectHashMapper`, `JacksonHashMapper`, nested/flat mapping.
- Redis — [Streams](https://redis.io/docs/latest/develop/data-types/streams/): lệnh, entry ID, consumer groups và retention.
- Redis — [XADD](https://redis.io/docs/latest/commands/xadd/), [XREAD](https://redis.io/docs/latest/commands/xread/), [XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/), [XACK](https://redis.io/docs/latest/commands/xack/): commands gốc.
