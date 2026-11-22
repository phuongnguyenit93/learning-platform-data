# Tùy chỉnh ObjectMapper và giữ cấu hình nhất quán giữa các bên

## 1. Vấn đề cần giải quyết

Redis lưu dữ liệu dưới dạng byte, không lưu trực tiếp đối tượng Java. Khi dùng Spring Data Redis để cache một DTO, ứng dụng phải quyết định cách biến đối tượng thành dữ liệu lưu trong Redis và cách khôi phục đối tượng khi đọc lại. Nếu chọn JSON, thành phần quyết định phần lớn quy tắc chuyển đổi là **Jackson ObjectMapper**.

Trong ứng dụng chỉ có một service, việc ghi và đọc có thể diễn ra bình thường vì cả hai lần đều sử dụng cùng serializer. Nhưng khi dữ liệu Redis được chia sẻ bởi nhiều service, nhiều phiên bản triển khai hoặc một client viết bằng Python/Node.js, khác biệt cấu hình rất dễ trở thành lỗi:

- Service A ghi **Instant** theo chuỗi ISO-8601, còn Service B dự kiến một timestamp dạng số.
- Service A lưu thuộc tính **userId**, Service B đang tìm **user_id**.
- Service A bật thông tin lớp Java **@class** trong JSON, trong khi client khác không biết package/class đó.
- Service A bỏ qua thuộc tính không biết; Service B từ chối JSON khi có trường mới.
- Service A lưu JSON object, trong khi Service B đọc cùng key như một chuỗi hoặc một Redis hash.
- Hai service dùng cùng key prefix nhưng khác phiên bản cấu trúc DTO.

Do đó, nhiệm vụ không dừng ở việc gọi **new ObjectMapper()**. Cần thiết kế một **hợp đồng dữ liệu (wire contract)**, cấu hình serializer đúng nơi và bảo đảm mọi bên cùng hiểu được dữ liệu đã lưu.

Trong bài này, “các bên” bao gồm các thành phần trong cùng Spring Boot application, các microservice khác nhau, các bản phát hành cũ/mới chạy song song và cả ứng dụng không viết bằng Java.

## 2. Đường đi của dữ liệu qua ObjectMapper

Với một **RedisTemplate<String, UserCacheDocument>** dùng JSON serializer, luồng ghi/đọc có thể hình dung:

~~~text
Java UserCacheDocument
         |
         v
Jackson2JsonRedisSerializer<UserCacheDocument>
         |
         v
ObjectMapper: property names, dates, enum,
              modules, null policy, type handling
         |
         v
UTF-8 JSON bytes
         |
         v
Redis key -> value bytes
         |
         v
JSON bytes returned to reader
         |
         v
Reader's JSON deserializer / ObjectMapper
         |
         v
Java DTO / Python dict / JS object
~~~

Hai thành phần có trách nhiệm khác nhau:

**RedisSerializer** là cầu nối giữa kiểu dữ liệu Java và mảng byte. Nó được cấu hình cho key, value, hash key hoặc hash value của một **RedisTemplate**.

**ObjectMapper** quyết định JSON được tạo/đọc như thế nào: tên thuộc tính, mô-đun xử lý **java.time**, format thời gian, enum, null, unknown field, custom serializer/deserializer và xử lý kiểu đa hình.

Serializer chọn nơi sử dụng mapper; mapper không tự động thay đổi mọi dữ liệu Redis trong ứng dụng.

### ObjectMapper không quyết định Redis data type

Một lệnh **SET** lưu JSON vào value của Redis key thuộc kiểu **string**. Một thực thể Spring Data Redis dùng **@RedisHash** lại có thể được map thành cấu trúc **Redis hash**. Cả hai có thể biểu diễn cùng một loại đối tượng Java, nhưng **không dùng chung cách lưu vật lý**.

Ví dụ:

~~~text
SET user-cache:v1:42 '{"userId":"42","displayName":"An"}'
~~~

là Redis string chứa JSON. Còn khi dữ liệu nằm trong Redis hash, thao tác **GET user-cache:v1:42** có thể trả lỗi **WRONGTYPE**. Tùy chỉnh ObjectMapper cho JSON value serializer không làm repository dựa trên **@RedisHash** tự đổi sang lưu JSON string.

## 3. Phân biệt các lựa chọn serializer JSON trong Spring Data Redis

| Thành phần | Đặc điểm | Nên dùng khi |
|---|---|---|
| **StringRedisSerializer** | Mã hóa/giải mã String, thường theo UTF-8; không biến DTO thành JSON | Key hoặc value đã là chuỗi |
| **Jackson2JsonRedisSerializer<T>** | JSON dựa trên một kiểu Java mục tiêu xác định; có thể truyền ObjectMapper riêng | Một keyspace có DTO rõ ràng |
| **GenericJackson2JsonRedisSerializer** | Hỗ trợ value nhiều kiểu; thường dựa trên metadata kiểu để khôi phục object | Thực sự cần nhiều kiểu và đã kiểm soát type handling |
| **JdkSerializationRedisSerializer** | Định dạng Java serialization nhị phân, không có JSON contract liên ngôn ngữ | Chỉ trong hệ thống đã chấp nhận định dạng Java riêng; không nên mặc định cho dữ liệu chia sẻ |

Với keyspace sử dụng chung giữa các service, **typed JSON serializer** thường dễ kiểm soát nhất. Người đọc biết trước schema của **UserCacheDocument**, và JSON không cần phụ thuộc vào tên class/package Java.

**GenericJackson2JsonRedisSerializer** có tính tiện lợi khi một template ghi nhiều loại đối tượng, nhưng sẽ cần quan tâm đặc biệt đến metadata kiểu, độ ổn định của tên class, khả năng tương thích khi refactor package và bảo mật deserialization. Không nên bật default typing không giới hạn cho dữ liệu có thể bị bên ngoài sửa.

Một serializer key bằng String không đồng nghĩa serializer value cũng là String. Hai phía cần khớp ở đúng loại byte được ghi, bao gồm cả **key serializer**; nếu ghi key bằng JDK serialization rồi tìm bằng **redis-cli GET user-cache:v1:42**, client có thể không tìm ra key do bytes thực tế khác nhau.

## 4. Bắt đầu từ JSON contract, rồi mới cấu hình mapper

Giả sử một nhóm service chia sẻ bản sao hồ sơ người dùng. Ta xác định hợp đồng JSON phiên bản 1:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z"
}
~~~

Quy ước đi kèm:

| Thuộc tính | Quy ước | Ý nghĩa |
|---|---|---|
| Redis key | **user-cache:v1:{userId}** | Keyspace và schema version có chủ đích |
| Redis type | **string** | Một JSON document nằm trong value |
| Encoding | **UTF-8** | Các client thống nhất byte encoding |
| **schemaVersion** | Số nguyên **1** | Đánh dấu phiên bản nội dung |
| **userId** | String | Tránh nhầm ID với số cần tính toán |
| **displayName** | String | Văn bản Unicode |
| **updatedAt** | ISO-8601 UTC, ví dụ **2026-11-12T10:20:00Z** | Thời điểm cập nhật |
| Field naming | **camelCase** | Cùng tên trong mọi reader/writer |
| TTL | Ví dụ **15 phút** | Hết hạn bản cache; không phải version của JSON |
| Unknown field | Quy ước reader có thể bỏ qua trường bổ sung | Hỗ trợ triển khai dần các trường tùy chọn |

Việc có **schemaVersion** ở payload và **v1** trong key không phải lúc nào cũng bắt buộc đồng thời. Hai tầng version phục vụ mục đích khác nhau: prefix giúp tránh đọc nhầm keyspace cũ, còn trường version giúp các reader nhận diện dạng payload. Chọn một chiến lược rõ ràng, không chỉ thêm hai chỗ version cho có.

Hợp đồng cần nêu thêm cách xử lý trường thiếu, trường **null**, giá trị enum không biết, ý nghĩa của giá trị tiền/timestamp và dữ liệu nào được phép chia sẻ. Cùng một **ObjectMapper** trong Java giúp giảm sai lệch nội bộ, nhưng **công bố quy ước JSON mới là điều giúp các ngôn ngữ khác đọc được**.

## 5. Tạo DTO rõ ràng cho dữ liệu Redis

Trong Java, có thể dùng record:

~~~java
package com.example.redis.model;

import java.time.Instant;

public record UserCacheDocument(
    int schemaVersion,
    String userId,
    String displayName,
    Instant updatedAt
) {}
~~~

Record phù hợp với một document bất biến. Khi đọc JSON, Jackson cần biết cách tạo **UserCacheDocument**; với Java và Jackson hiện đại, record được hỗ trợ trực tiếp.

Không nhất thiết dùng cùng class cho response HTTP, database entity và Redis cache. Nếu gắn toàn bộ trách nhiệm vào một DTO duy nhất, thay đổi API công khai hoặc thay đổi entity có thể vô tình làm thay đổi dữ liệu Redis. Với dữ liệu được nhiều service tiêu thụ, **document dành riêng cho Redis** giúp kiểm soát schema ổn định hơn.

Khi thiết kế DTO, cần cân nhắc:

- Giá trị nào thật sự cần được lưu, dữ liệu nào có thể tính lại?
- Dữ liệu nào có thể vắng mặt khi đọc phiên bản cũ?
- Giá trị mặc định của trường mới có phù hợp mọi trường hợp không?
- Có trường nào nhạy cảm như mật khẩu, access token, khóa bí mật không nên đưa vào document chia sẻ?
- Thay đổi Java field name có làm thay đổi tên trường JSON đang được consumer dùng không?

## 6. Cấu hình ObjectMapper riêng cho RedisTemplate

Ví dụ Spring Boot với **Spring Data Redis**, **Jackson** và mô-đun Jackson hỗ trợ **java.time**. Phần phụ thuộc thường có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
    implementation 'com.fasterxml.jackson.datatype:jackson-datatype-jsr310'
}
~~~

Khi ứng dụng đã dùng một starter cung cấp Jackson, không nhất thiết phải khai báo lại các dependency Jackson trùng lặp. Spring Boot dependency management nên quản lý phiên bản thư viện.

Tạo một template dành riêng cho **UserCacheDocument**:

~~~java
package com.example.redis.config;

import com.example.redis.model.UserCacheDocument;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class UserRedisSerializationConfig {

    @Bean("userCacheRedisTemplate")
    public RedisTemplate<String, UserCacheDocument> userCacheRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        ObjectMapper redisMapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

        var jsonSerializer =
            new Jackson2JsonRedisSerializer<>(
                redisMapper,
                UserCacheDocument.class
            );

        var template = new RedisTemplate<String, UserCacheDocument>();
        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(jsonSerializer);

        // Chỉ cần khi sử dụng hash operations; phải xác định
        // rõ kiểu dữ liệu hash value mà template này quản lý.
        template.setHashKeySerializer(new StringRedisSerializer());
        template.setHashValueSerializer(jsonSerializer);

        template.afterPropertiesSet();
        return template;
    }
}
~~~

Đoạn cấu hình minh họa các ranh giới:

1. **RedisConnectionFactory** chịu trách nhiệm kết nối đến Redis, không quyết định hình dạng JSON.
2. **ObjectMapper** xử lý JSON và các quy tắc chuyển đổi DTO.
3. **Jackson2JsonRedisSerializer<UserCacheDocument>** sử dụng mapper đó để tạo bytes và đọc bytes.
4. **StringRedisSerializer** xử lý key; key có thể nhìn thấy trực tiếp bằng Redis CLI.
5. **RedisTemplate** gắn connection và serializers lại thành API thao tác dữ liệu.

Trong ví dụ, **hash value serializer** cũng được đặt theo **UserCacheDocument**, chỉ có nghĩa nếu ứng dụng thật sự lưu một object như vậy trong mỗi hash field. Không được suy ra rằng mọi hash field của mọi key đều có cấu trúc đó. Với ứng dụng có nhiều Redis data type, có thể dùng template khác hoặc một adapter giới hạn phạm vi thao tác.

**Lưu ý phiên bản API:** constructor của serializer và cách cấu hình Jackson có thể thay đổi giữa các dòng Spring Data Redis/Jackson. Ví dụ trên sử dụng dạng constructor nhận **ObjectMapper** và **Class<T>** của Spring Data Redis 3.x. Khi nâng phiên bản lớn, cần đối chiếu API tương ứng; hợp đồng JSON có thể giữ ổn định ngay cả khi cách khởi tạo serializer thay đổi.

### Tại sao tạo ObjectMapper bên trong cấu hình Redis?

Ứng dụng Spring Boot có thể có một **ObjectMapper** dùng cho HTTP JSON. Nếu thay đổi trực tiếp mapper dùng chung, các API HTTP hoặc những nơi sử dụng Jackson khác cũng có thể đổi format ngoài ý muốn. Ví dụ, tắt tính năng ghi ngày dạng timestamp cho Redis có thể thay đổi output của một controller đang phụ thuộc mapper đó.

Một mapper riêng cho Redis giúp quy tắc lưu trữ có vòng đời độc lập. Nếu muốn tái sử dụng các module hoặc chuẩn đặt tên của ứng dụng, có thể tạo mapper từ **Jackson2ObjectMapperBuilder** đã được Spring Boot cấu hình, nhưng vẫn nên xây một **instance riêng** trước khi tùy chỉnh các quy tắc dành riêng cho Redis.

ObjectMapper có thể được sử dụng lại giữa các thread sau khi đã cấu hình hoàn chỉnh. Không nên thay đổi **registerModule**, **setDateFormat**, **setPropertyNamingStrategy**, default typing... giữa lúc template đang được nhiều request sử dụng.

## 7. Ví dụ ghi và đọc bằng template đã cấu hình

~~~java
package com.example.redis.service;

import com.example.redis.model.UserCacheDocument;
import java.time.Duration;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserProfileCache {
    private final RedisTemplate<String, UserCacheDocument> redis;

    public UserProfileCache(
            @Qualifier("userCacheRedisTemplate")
            RedisTemplate<String, UserCacheDocument> redis) {
        this.redis = redis;
    }

    public void put(UserCacheDocument document) {
        redis.opsForValue().set(
            key(document.userId()),
            document,
            Duration.ofMinutes(15)
        );
    }

    public Optional<UserCacheDocument> find(String userId) {
        return Optional.ofNullable(
            redis.opsForValue().get(key(userId))
        );
    }

    public void evict(String userId) {
        redis.delete(key(userId));
    }

    private String key(String userId) {
        return "user-cache:v1:" + userId;
    }
}
~~~

Ví dụ lưu:

~~~java
var document = new UserCacheDocument(
    1,
    "42",
    "Nguyễn An",
    java.time.Instant.parse("2026-11-12T10:20:00Z")
);
userProfileCache.put(document);
~~~

Với cấu hình trên, Redis value được lưu dưới dạng JSON bytes có nội dung tương đương:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z"
}
~~~

Thứ tự field và khoảng trắng không phải cam kết của JSON contract, trừ khi hệ thống có lý do đặc biệt để yêu cầu output canonical. Cái cần nhất quán là **tên trường, kiểu giá trị, ý nghĩa dữ liệu, định dạng thời gian và bộ ký tự**.

Để xem dữ liệu trực tiếp:

~~~bash
redis-cli --raw GET user-cache:v1:42
redis-cli TTL user-cache:v1:42
~~~

**GET** cho phép quan sát JSON đã ghi; **TTL** cho biết số giây đến khi key hết hạn hoặc trạng thái key không có hạn/không tồn tại. Không nhầm TTL với thời hạn kết nối hoặc serializer.

## 8. Những tùy chỉnh ObjectMapper ảnh hưởng trực tiếp đến hợp đồng

### 8.1. Ngày giờ, múi giờ và độ chính xác

Jackson cần mô-đun **JavaTimeModule** để xử lý hiệu quả nhiều kiểu **java.time**, ví dụ **Instant**, **LocalDate**, **OffsetDateTime**.

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

**WRITE_DATES_AS_TIMESTAMPS** là một lựa chọn serialization; nếu hai bên cấu hình khác nhau, một bên có thể ghi chuỗi ISO-8601 trong khi bên kia ghi dạng số hoặc cấu trúc timestamp khác.

Nên thống nhất rõ ý nghĩa:

- **Instant** biểu diễn một thời điểm tuyệt đối, thường xuất ra ISO-8601 với **Z** khi dùng UTC.
- **LocalDate** chỉ có ngày, không kèm múi giờ; ví dụ **2026-11-12**.
- **LocalDateTime** không chứa offset/timezone; không nên xem nó mặc nhiên là UTC khi dữ liệu đi qua nhiều hệ thống.
- Timestamp dạng **epoch milliseconds** khác **epoch seconds** và khác độ chính xác micro/nanoseconds.

Nếu sử dụng numeric timestamp, phải nói rõ đơn vị, độ chính xác và cách xử lý số lớn. Đừng để reader tự đoán “13 chữ số chắc là milliseconds”.

Với những hệ thống có nhiều múi giờ, ISO-8601 kèm offset/UTC thường dễ diễn giải hơn chuỗi ngày giờ mơ hồ. Nếu cần giữ timezone gốc của người dùng, lưu nó như một trường riêng theo hợp đồng thay vì dựa vào timezone mặc định của JVM.

### 8.2. Tên thuộc tính: camelCase, snake_case và @JsonProperty

Ví dụ Java field là **userId**:

~~~json
{"userId":"42"}
~~~

Nếu bật **PropertyNamingStrategies.SNAKE_CASE**, JSON thường thành:

~~~json
{"user_id":"42"}
~~~

Reader đang tìm **userId** sẽ không tự hiểu **user_id** khi không có cấu hình hoặc alias phù hợp.

Có thể đặt một quy tắc toàn mapper:

~~~java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;

mapper.setPropertyNamingStrategy(
    PropertyNamingStrategies.SNAKE_CASE
);
~~~

Thao tác này phải thực hiện **trước khi mapper bắt đầu được dùng**. Nếu hợp đồng chỉ có một vài tên trường cần giữ ổn định, có thể khai báo **@JsonProperty** ở DTO:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record UserIdWire(
    @JsonProperty("user_id") String userId
) {}
~~~

Việc refactor tên field Java không nên âm thầm thay đổi tên field bên Redis mà các consumer đang phụ thuộc. Với dữ liệu chia sẻ, coi tên thuộc tính JSON là một API contract.

### 8.3. Thuộc tính không biết và khả năng tương thích tiến

Giả sử writer mới thêm:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z",
  "avatarUrl": "https://example.org/avatar/42"
}
~~~

Reader cũ chỉ có bốn trường ban đầu. Với cấu hình:

~~~java
mapper.disable(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
);
~~~

reader có thể bỏ qua **avatarUrl** khi deserialize. Cách này hỗ trợ thêm thuộc tính tùy chọn trong lúc hai phiên bản service cùng hoạt động.

Tuy nhiên, bỏ qua unknown field **không tự động bảo đảm tương thích toàn diện**. Nếu trường cũ bị xóa, đổi kiểu hoặc đổi nghĩa, reader cũ vẫn có thể đọc sai hoặc nhận giá trị thiếu. Với dữ liệu nhạy cảm nghiệp vụ, cần thêm validation sau deserialize và chính sách schema rõ ràng.

### 8.4. Null, missing field và giá trị mặc định

Ba trường hợp cần phân biệt:

~~~json
{"displayName": "An"}
~~~

~~~json
{"displayName": null}
~~~

~~~json
{}
~~~

Một field **vắng mặt**, một field **có giá trị null**, và một field **chứa chuỗi rỗng** có thể mang ý nghĩa khác nhau. Nếu bật:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

mapper.setSerializationInclusion(
    JsonInclude.Include.NON_NULL
);
~~~

những thuộc tính Java có giá trị **null** sẽ không được ghi trong JSON. Đây là thay đổi hợp đồng: consumer không còn phân biệt được “writer chủ động ghi null” với “writer không biết field này” chỉ từ payload.

Với các trường quan trọng, có thể yêu cầu luôn có mặt và validate sau khi đọc. Không mặc định rằng một Java record **int schemaVersion** vắng mặt có cùng ý nghĩa với một phiên bản hợp lệ; giá trị primitive mặc định có thể khiến lỗi schema bị che lấp nếu không kiểm tra.

### 8.5. Enum và thay đổi giá trị

Ví dụ:

~~~java
public enum AccountStatus {
    ACTIVE, SUSPENDED
}
~~~

JSON có thể ghi:

~~~json
{"status":"ACTIVE"}
~~~

Thêm enum **PENDING** ở writer mới có thể làm reader cũ không deserialize được. Đổi tên **SUSPENDED** thành **DISABLED** cũng là một thay đổi wire contract nếu chưa có cơ chế ánh xạ.

Cần quyết định chiến lược enum:

- Dùng chuỗi ổn định, tách tên hiển thị khỏi mã dữ liệu.
- Khi thêm trạng thái mới, xác định hành vi của consumer cũ.
- Nếu cần fallback, triển khai có kiểm soát và log/metric để nhận diện giá trị lạ.
- Tránh để một enum chưa biết âm thầm trở thành trạng thái có quyền cao hơn hoặc ít hạn chế hơn.

### 8.6. Số thập phân và số nguyên lớn

JSON chỉ định dạng cú pháp cho number, không cam kết mọi ngôn ngữ dùng cùng độ chính xác. Java **BigDecimal** và JavaScript **Number** có thể có hành vi khác nhau; một số số nguyên 64-bit lớn vượt phạm vi số nguyên chính xác của Number trong JavaScript.

Với giá tiền, tỷ giá hoặc ID lớn, hãy chọn định dạng từ đầu. Ví dụ:

~~~json
{
  "priceMinorUnits": "199900",
  "currency": "VND"
}
~~~

Đây là một thiết kế minh họa dùng chuỗi cho số nguyên đơn vị nhỏ nhất, giúp consumer tránh mất độ chính xác do kiểu number mặc định. Cũng có thể dùng decimal string với quy ước cụ thể, ví dụ **"1999.00"**. Quan trọng là tất cả bên tham gia hiểu **đơn vị, thang đo, cách làm tròn và kiểu dữ liệu**.

## 9. Tính nhất quán giữa RedisTemplate, HTTP và Spring Cache

Một dự án có thể tồn tại đồng thời:

~~~text
HTTP ObjectMapper
       |
  JSON API response

RedisTemplate<String, UserCacheDocument>
       |
  Jackson2JsonRedisSerializer
       |
  user-cache:v1:*

RedisCacheManager
       |
  RedisCacheConfiguration
       |
  cache namespace

Spring Data Redis Repository
       |
  RedisMappingContext / @RedisHash
       |
  Redis hash + index metadata
~~~

Chúng không mặc nhiên dùng cùng serializer hoặc cùng data layout.

### 9.1. RedisTemplate không tự điều khiển Spring Cache

Nếu code sử dụng **@Cacheable**, giá trị cache thường đi qua **RedisCacheManager** và **RedisCacheConfiguration**. Tùy chỉnh **RedisTemplate.setValueSerializer(...)** không có nghĩa cache manager lập tức dùng serializer đó.

Để dùng JSON serializer riêng cho cache, cấu hình tương ứng trong cache manager:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import java.time.Duration;

@Configuration
public class UserCacheManagerConfig {

    @Bean("userCacheManager")
    public RedisCacheManager userCacheManager(
            RedisConnectionFactory connectionFactory) {

        var serializer = new Jackson2JsonRedisSerializer<>(
            UserCacheDocument.class
        );

        RedisCacheConfiguration configuration =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(15))
                .serializeValuesWith(
                    RedisSerializationContext
                        .SerializationPair
                        .fromSerializer(serializer)
                );

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(configuration)
            .build();
    }
}
~~~

Ví dụ trên minh họa **vị trí cấu hình cache serializer**, chưa dùng mapper tùy biến ở phần 6. Nếu cần chính xác cùng định dạng, thay **serializer** bằng instance đã được tạo với **ObjectMapper** và schema tương ứng. Ngoài ra, cache dùng cho nhiều method trả về nhiều kiểu thường **không thể** dùng an toàn một serializer cố định của **UserCacheDocument** cho mọi cache name. Hãy đặt cache manager/cache config theo từng loại hoặc chọn serialization contract phù hợp.

Khi dùng **@Cacheable**, hãy phân biệt cả prefix và key encoding do cache abstraction tạo ra; đừng giả định key của cache manager sẽ giống key do **UserProfileCache.key(...)** tạo.

### 9.2. @RedisHash không biến thành JSON chỉ vì có ObjectMapper

**@RedisHash** dùng cơ chế Redis mapping riêng để lưu object dưới dạng Redis hash và có thể duy trì secondary index. Nếu muốn tạo JSON string value theo contract liên ngôn ngữ, hãy sử dụng template/adapter dành riêng cho dữ liệu đó.

Không cho một template dùng lệnh **SET** ghi JSON string vào key mà Redis repository đang dùng Redis hash. Redis có một data type cho mỗi key tại một thời điểm; việc thay đổi kiểu có thể phá hỏng dữ liệu hoặc khiến thao tác kế tiếp trả **WRONGTYPE**.

### 9.3. Mapper HTTP có nên giống mapper Redis không?

Không nhất thiết. Các bên cần nhất quán **đúng contract mà họ chia sẻ**. Một API HTTP công khai có thể dùng snake_case và format khác, trong khi cache nội bộ dùng camelCase. Nếu muốn tái sử dụng schema, có thể chia sẻ các quy ước/mô-đun hoặc chuyển đổi qua DTO rõ ràng.

Tránh sửa trực tiếp **ObjectMapper** toàn ứng dụng chỉ để chữa một lỗi Redis. Thay đổi như bật default typing, đổi date format hoặc tắt fail-on-unknown trên global mapper có thể ảnh hưởng cả HTTP, Kafka và những JSON serializer khác.

## 10. Giữ các service độc lập nhưng cùng hiểu dữ liệu

Giả sử hai service:

~~~text
User Service (Java/Spring)
       |
       | write user-cache:v1:42
       v
  Redis JSON value
       ^
       | read user-cache:v1:42
       |
Notification Service (Node.js)
~~~

User Service có thể ghi bằng:

~~~java
redisTemplate.opsForValue().set(
    "user-cache:v1:42",
    new UserCacheDocument(
        1,
        "42",
        "Nguyễn An",
        Instant.parse("2026-11-12T10:20:00Z")
    ),
    Duration.ofMinutes(15)
);
~~~

Notification Service không cần class Java. Nó chỉ cần biết Redis key, UTF-8, JSON schema và quy tắc thời gian. Ví dụ JavaScript minh họa phần parse đã nhận:

~~~javascript
const raw = '{"schemaVersion":1,"userId":"42",'
  + '"displayName":"Nguyễn An",'
  + '"updatedAt":"2026-11-12T10:20:00Z"}';

const user = JSON.parse(raw);

if (user.schemaVersion !== 1 || typeof user.userId !== "string") {
  throw new Error("Unsupported user-cache payload");
}

const updatedAt = new Date(user.updatedAt);
if (Number.isNaN(updatedAt.getTime())) {
  throw new Error("Invalid updatedAt");
}
~~~

Đây là phần kiểm tra JSON contract, không bao gồm kết nối Redis của Node.js. Một consumer thực tế nên có validation đầy đủ cho các field bắt buộc, giới hạn kích thước payload và chính sách rõ khi gặp schema version chưa được hỗ trợ.

Nếu mỗi service tự tạo một mapper khác nhau nhưng cùng tuân thủ contract, dữ liệu vẫn tương thích. **Tương thích được chứng minh bằng bytes và schema thực tế, không phải chỉ vì hai service cùng dùng Jackson**.

### Có nên dùng chung thư viện DTO Java?

Nếu tất cả service đều là Java, một module hợp đồng dùng chung có thể giúp giảm lệch tên field. Tuy nhiên, thư viện chung cũng tạo phụ thuộc phiên bản và không giải quyết hoàn toàn vấn đề rolling deployment: service cũ vẫn có thể đọc payload của service mới.

Với kiến trúc nhiều ngôn ngữ, nên có tài liệu schema độc lập với Java, ví dụ JSON Schema/OpenAPI schema dành cho payload, cùng bộ dữ liệu mẫu và compatibility tests. Quy định rõ ai sở hữu hợp đồng, khi nào được đổi schema và quy trình thông báo cho consumer.

## 11. Polymorphic JSON và rủi ro của thông tin kiểu Java

Một payload có thể chứa metadata kiểu khi serializer generic sử dụng type information, ví dụ minh họa:

~~~json
{
  "@class": "com.example.user.internal.UserRecord",
  "userId": "42",
  "displayName": "Nguyễn An"
}
~~~

Thông tin **@class** làm JSON phụ thuộc vào Java package/class. Khi refactor **com.example.user.internal.UserRecord** sang package khác, client cũ có thể không khôi phục được đối tượng. Client Python/Node.js cũng không cần biết tên lớp Java để diễn giải business schema.

### Tại sao không bật default typing tùy tiện?

Jackson có cơ chế polymorphic deserialization. Nếu cho phép một payload không đáng tin xác định tùy ý lớp Java cần tạo, một cấu hình deserialization không an toàn có thể tạo thêm bề mặt tấn công, đặc biệt khi classpath có các kiểu không phù hợp để deserialize từ dữ liệu bên ngoài.

Nguyên tắc:

1. Với keyspace có DTO cố định, ưu tiên **typed serializer** và tránh thông tin class Java trong payload.
2. Chỉ dùng polymorphic deserialization khi nghiệp vụ thật sự cần nhiều subtype.
3. Nếu dùng, chỉ chấp nhận những subtype đã được cho phép bằng cơ chế hạn chế type như **PolymorphicTypeValidator** phù hợp; không bật default typing rộng không giới hạn.
4. Dùng mã loại nghiệp vụ ổn định như **type: "EMAIL"** thay vì biến tên lớp Java thành hợp đồng công khai nếu cần hỗ trợ nhiều event type.
5. Đảm bảo Redis ACL, mạng và quyền ghi keyspace hạn chế các bên có thể sửa payload.

Ví dụ hợp đồng độc lập với Java:

~~~json
{
  "schemaVersion": 1,
  "type": "EMAIL",
  "payload": {
    "recipientId": "42",
    "templateCode": "WELCOME"
  }
}
~~~

Consumer dựa vào **type** để chọn DTO được phép, thay vì lấy một tên lớp tùy ý từ JSON để khởi tạo.

## 12. Nâng cấp schema khi nhiều phiên bản chạy song song

Một vấn đề phổ biến: bản V2 của service triển khai trước, bắt đầu ghi dữ liệu mà V1 chưa chắc đọc được. Trong thời gian rolling deployment, các instance V1/V2 có thể cùng truy cập Redis.

### 12.1. Thêm field tùy chọn

V1:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z"
}
~~~

V2 bổ sung **avatarUrl**:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z",
  "avatarUrl": "https://example.org/avatar/42"
}
~~~

Giữ **schemaVersion = 1** có thể chấp nhận khi đây là **thay đổi tương thích trong cùng hợp đồng V1** và reader cũ được thiết kế để bỏ qua unknown field. Cần xác minh reader cũ thực sự chịu được field mới; không chỉ dựa trên ý định.

### 12.2. Đổi kiểu/ý nghĩa field

Nếu **updatedAt** đổi từ ISO string thành epoch milliseconds, đó là thay đổi không tương thích với reader đang chờ string:

~~~json
{
  "schemaVersion": 2,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAtEpochMillis": 1794478800000
}
~~~

Khi đó nên:

- Tạo keyspace mới **user-cache:v2:{userId}**, hoặc
- Định nghĩa reader hỗ trợ cả V1 và V2 với phân nhánh rõ ràng, hoặc
- Tổ chức quá trình chuyển dữ liệu và rolling deployment đảm bảo reader mới có mặt trước writer thay đổi.

Không sử dụng song song dữ liệu V1 và V2 dưới cùng một key rồi hy vọng mọi bản service tự đoán định dạng.

### 12.3. Quy trình thay đổi có kiểm soát

Một quy trình thường phù hợp:

1. **Định nghĩa schema mới** và nguyên tắc đọc dữ liệu cũ.
2. **Triển khai reader tương thích** (đọc được V1, nếu cần cả V2) trước khi writer chỉ ghi V2.
3. **Triển khai writer mới** với keyspace/version được quy định.
4. **Chuyển đổi dữ liệu** bằng cache miss/repopulate hoặc migration có kiểm soát, tùy vai trò của Redis.
5. **Theo dõi lỗi deserialization** và lượng dữ liệu V1 còn được đọc.
6. **Loại bỏ đường đọc cũ** chỉ sau khi hết thời hạn hỗ trợ, TTL hoặc hoàn tất migration.

Nếu Redis chỉ là cache có thể tái tạo, dùng versioned key prefix và để key cũ tự hết TTL có thể đơn giản hơn migration. Nếu Redis đang giữ dữ liệu nghiệp vụ không thể tái tạo, cần kế hoạch chuyển đổi, kiểm soát mất dữ liệu và rollback chặt chẽ hơn.

### 12.4. Dual-read, single-write

Ví dụ service mới ưu tiên V2 nhưng tạm đọc V1 nếu chưa có:

~~~text
READ user-cache:v2:42
   |
   +-- found -> deserialize V2
   |
   +-- absent -> READ user-cache:v1:42
                   |
                   +-- found -> deserialize V1, map sang V2
                   |
                   +-- absent -> cache miss / load source

WRITE -> user-cache:v2:42
~~~

Đây là chiến lược **dual-read, single-write**. Cần tránh trường hợp một consumer V1 vẫn hoạt động nhưng writer V2 đã ngừng cập nhật dữ liệu V1 trong khi consumer đó còn phụ thuộc dữ liệu cũ. Cách triển khai tùy trình tự deployment và hợp đồng đồng bộ giữa các bên.

## 13. Chia sẻ cấu hình thế nào để tránh drift?

Hai service có thể cùng dùng JSON nhưng vẫn cấu hình khác nhau do dependency hoặc team khác nhau. **Configuration drift** xảy ra khi một thay đổi nhỏ ở một bên không được phản ánh ở bên còn lại.

Ví dụ:

| Điểm có thể lệch | Service A | Service B | Hậu quả |
|---|---|---|---|
| Date format | ISO-8601 UTC | Epoch milliseconds | Deserialize sai/không đọc được |
| Property naming | camelCase | snake_case | Field bị mất/không map |
| Enum | String | Ordinal | Ý nghĩa dữ liệu không khớp |
| Unknown properties | Bỏ qua | Throw error | Deployment không tương thích |
| Type metadata | Không có | Yêu cầu **@class** | Reader không tái tạo object |
| Redis type | String JSON | Redis hash | **WRONGTYPE** |
| TTL | 15 phút | 24 giờ | Dữ liệu stale lâu hơn thiết kế |

Có thể phòng tránh bằng các biện pháp:

**Hợp đồng versioned:** mô tả schema, key prefix, encoding, data type, TTL và quy tắc tương thích ở một nơi rõ ràng.

**Module cấu hình chung:** khi các service Java có cùng dependency và lifecycle, có thể cung cấp module nhỏ tạo mapper/serializer theo hợp đồng. Tuy nhiên vẫn cần kiểm tra backward compatibility khi nâng version của module.

**Golden payload:** lưu các JSON mẫu chuẩn và dữ liệu byte mẫu; mọi consumer chạy test đọc được payload mẫu, mọi writer tạo được payload hợp lệ. Với JSON không yêu cầu thứ tự field, nên so sánh cấu trúc JSON thay vì so sánh string raw nếu không có lý do canonicalization.

**Consumer-driven compatibility tests:** khi writer thêm/đổi field, xác minh những consumer còn được hỗ trợ vẫn đọc được.

**Schema validation:** xử lý payload từ nguồn ngoài dựa vào version/contract rõ ràng; không chỉ dựa trên việc Jackson không ném exception.

**Quan sát lỗi:** theo dõi số lần deserialize lỗi, schema version không biết, cache miss bất thường, TTL không đúng và dữ liệu không hợp lệ.

Mục tiêu không phải bắt mọi service phải có một file **ObjectMapperConfig.java** giống hệt nhau. Mục tiêu là tạo ra và đọc được **cùng dữ liệu có cùng ý nghĩa**, kể cả khi kỹ thuật triển khai ở các ngôn ngữ khác nhau.

## 14. Các ví dụ lỗi thường gặp và cách suy luận

### 14.1. Lỗi đọc Instant

**Triệu chứng:** JSON chứa **"updatedAt": "2026-11-12T10:20:00Z"**, nhưng reader báo không xử lý được **java.time.Instant**.

**Nguyên nhân có thể:** mapper của Redis serializer chưa đăng ký **JavaTimeModule**, hoặc reader đang dùng serializer khác với writer.

**Cách tiếp cận:** kiểm tra bytes thực tế trong Redis, template đang được inject, serializer của value và modules của đúng ObjectMapper. Thêm **JavaTimeModule** vào mapper được serializer sử dụng; không mặc định rằng mapper HTTP đã được cấu hình thì Redis serializer cũng được cấu hình.

### 14.2. Một service đọc ra object trống/null field

**Triệu chứng:** Redis JSON có **user_id** nhưng Java DTO chờ **userId**.

**Nguyên nhân có thể:** writer và reader có naming strategy khác nhau, hoặc field bị rename mà không duy trì alias.

**Cách tiếp cận:** xác định tên field chuẩn trong contract, sau đó dùng **@JsonProperty/@JsonAlias** hoặc cấu hình naming rõ ràng để đọc dữ liệu cũ. Tránh đặt **FAIL_ON_UNKNOWN_PROPERTIES = false** rồi kết luận đã giải quyết xong: reader có thể bỏ qua **user_id** nhưng vẫn không gán **userId**.

### 14.3. ClassNotFoundException hoặc lỗi type id

**Triệu chứng:** payload chứa **@class** với package cũ; sau khi refactor code, deserialize bị lỗi.

**Nguyên nhân có thể:** serializer generic đã đưa Java class name thành một phần của định dạng dữ liệu.

**Cách tiếp cận:** đánh giá khả năng chuyển sang DTO cố định hoặc type discriminator nghiệp vụ; nếu phải chuyển đổi dữ liệu cũ, triển khai reader/migration có kiểm soát. Không bật cơ chế tự động khởi tạo bất kỳ class nào để “đọc cho được”.

### 14.4. WRONGTYPE sau khi đổi cơ chế truy cập

**Triệu chứng:** repository có **@RedisHash**, nhưng service khác đọc cùng key bằng **opsForValue().get()**.

**Nguyên nhân:** hai bên không thống nhất Redis data type. Một bên cần Redis hash, một bên dùng Redis string.

**Cách tiếp cận:** thống nhất key owner, prefix và data type. Chỉ sử dụng đúng API hoặc migrate sang keyspace khác; ObjectMapper không sửa được vấn đề Redis type.

### 14.5. Cache đọc được nhưng giá trị đã cũ

**Triệu chứng:** service A ghi TTL 15 phút; service B dùng SET ghi lại cùng key nhưng bỏ TTL hoặc gắn TTL dài hơn.

**Nguyên nhân:** hợp đồng dữ liệu không chỉ gồm JSON, mà còn gồm vòng đời của key.

**Cách tiếp cận:** định nghĩa owner và quy tắc TTL; dùng operation phù hợp để ghi cùng TTL. Thao tác **SET** có thể làm thay đổi hoặc xóa TTL hiện có tùy tùy chọn, nên không suy luận TTL sẽ tự được bảo toàn.

### 14.6. Thêm field mới khiến bản cũ lỗi

**Triệu chứng:** một số pod chạy bản cũ không đọc được payload do bản mới ghi.

**Nguyên nhân:** contract thay đổi không tương thích hoặc reader cũ bật fail-on-unknown.

**Cách tiếp cận:** xác định các version đang chạy; nếu chỉ thêm field tùy chọn, cho reader cũ bỏ qua unknown field khi phù hợp. Với thay đổi phá vỡ cấu trúc, sử dụng versioned key/schema và triển khai theo lộ trình đọc trước, ghi sau.

## 15. Kiểm chứng hợp đồng bằng bài kiểm thử

### 15.1. Round-trip test cho serializer

Một test nhỏ có thể kiểm tra **serialize → deserialize** ngay tại tầng serializer, không cần Redis server:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;

class UserCacheSerializationTest {

    @Test
    void shouldRoundTripUserDocument() {
        var mapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();

        var serializer = new Jackson2JsonRedisSerializer<>(
            mapper,
            UserCacheDocument.class
        );

        var before = new UserCacheDocument(
            1,
            "42",
            "Nguyễn An",
            Instant.parse("2026-11-12T10:20:00Z")
        );

        byte[] bytes = serializer.serialize(before);
        assertNotNull(bytes);

        UserCacheDocument after = serializer.deserialize(bytes);
        assertEquals(before, after);
    }
}
~~~

Test này chứng minh **một serializer** có thể đọc lại output của chính nó. Nó **chưa chứng minh** rằng Node.js, serializer cũ hoặc một cấu hình Jackson khác cũng đọc được.

### 15.2. Golden JSON test

Thêm một payload mẫu cố định:

~~~json
{
  "schemaVersion": 1,
  "userId": "42",
  "displayName": "Nguyễn An",
  "updatedAt": "2026-11-12T10:20:00Z"
}
~~~

Reader cần deserialize payload này đúng nghĩa; writer cần tạo JSON có cùng cấu trúc. Không nhất thiết cố định thứ tự field hoặc whitespace.

Ví dụ kiểm tra hình dạng JSON bằng **JsonNode**:

~~~java
byte[] bytes = serializer.serialize(document);
JsonNode tree = mapper.readTree(bytes);

assertEquals(1, tree.path("schemaVersion").asInt());
assertEquals("42", tree.path("userId").asText());
assertEquals("2026-11-12T10:20:00Z",
    tree.path("updatedAt").asText());
~~~

Đoạn minh họa giả định các biến **serializer**, **document**, **mapper** và các import Jackson/JUnit đã được định nghĩa trong test trước đó. Kiểm tra cấu trúc giúp phát hiện việc mapper đột ngột đổi thành snake_case hoặc ghi timestamp numeric.

### 15.3. Compatibility test giữa phiên bản

Khi phiên bản V2 thêm field:

1. Đọc payload V1 bằng reader V2.
2. Đọc payload V2 bằng reader V1 nếu hợp đồng yêu cầu backward compatibility.
3. Kiểm tra field bắt buộc không bị mất hay hiểu sai.
4. Kiểm tra enum và số lớn/decimal với dữ liệu biên.
5. Kiểm tra dữ liệu Unicode và Instant có offset khác nhau nhưng cùng thời điểm.
6. Kiểm tra data type, key serializer và TTL trên Redis thật.

Nếu một thay đổi không được thiết kế để tương thích, test phải thể hiện rõ rằng version cũ bị từ chối **có kiểm soát**, thay vì để exception ngẫu nhiên hoặc ghi sai dữ liệu.

### 15.4. Integration test với Redis

Một test có Redis thật hoặc Redis test instance cần xác minh:

- Key có byte format mà các client khác tra cứu được.
- Value là JSON UTF-8 đúng schema.
- **GET** trả Redis string, không gặp WRONGTYPE.
- TTL được thiết lập đúng khi ghi.
- Service khác thực sự deserialize được dữ liệu.
- Khi key không tồn tại, ứng dụng xử lý cache miss phù hợp.

Mock **RedisTemplate** không thể xác minh serializer, Redis data type hoặc TTL thực tế. Tuy vậy, các test JSON ở tầng Java không cần mở Redis và có thể chạy nhanh trong mỗi commit.

## 16. Quy trình triển khai một shared JSON keyspace

Giả sử hệ thống chuẩn bị chia sẻ **user-cache:v1** cho ba service.

**Bước 1 — Chốt owner và mục đích dữ liệu.** Xác định service nào có quyền ghi, service nào chỉ đọc, Redis là cache có thể tái tạo hay nguồn dữ liệu chính và khi nào dữ liệu phải hết hạn.

**Bước 2 — Chốt wire contract.** Tài liệu hóa key pattern, Redis data type, UTF-8, JSON field names, field types, time format, null policy, enum policy, TTL và schema version.

**Bước 3 — Chọn typed serializer.** Mỗi keyspace DTO rõ ràng nên dùng serializer tương ứng; khi cần polymorphism, định nghĩa subtype và type discriminator được phép.

**Bước 4 — Xây ObjectMapper ở tầng cấu hình.** Đăng ký JavaTimeModule, định nghĩa naming/date/unknown-field behavior trước khi mapper được dùng, hạn chế tác động tới ObjectMapper HTTP.

**Bước 5 — Cho writer và reader dùng cùng mẫu dữ liệu.** Test golden payload, cả trường hợp cũ và mới. Với hệ thống đa ngôn ngữ, mỗi consumer tự chứng minh có thể đọc theo contract.

**Bước 6 — Quan sát lỗi trong production.** Theo dõi deserialization failures, unknown schema version, TTL bất thường và cache miss. Không log nguyên payload nếu có thông tin cá nhân/nhạy cảm.

**Bước 7 — Nâng cấp có lộ trình.** Thay đổi tương thích có thể thêm field tùy chọn; thay đổi phá vỡ contract nên version key/schema và lên kế hoạch triển khai/migration.

Nếu có nhiều template/cache manager, duy trì một bản mô tả rõ template nào quản lý keyspace nào. Khi đó một team khác có thể đánh giá ảnh hưởng trước khi dùng một serializer hoặc một cache name khác để ghi lên cùng key.

## 17. Bài tập suy luận

**Tình huống A.** Spring Boot REST API trả **updatedAt** dưới dạng ISO string, nhưng dữ liệu Redis lại thành timestamp số. Vì sao?

**Giải thích:** HTTP JSON và RedisTemplate có thể sử dụng hai ObjectMapper/serializer khác nhau. Cần kiểm tra **ObjectMapper của chính Redis value serializer**, các module và **WRITE_DATES_AS_TIMESTAMPS**; không suy đoán từ response HTTP.

**Tình huống B.** Một service đổi package Java **com.example.v1.User** thành **com.example.v2.User**. Dữ liệu Redis cũ có **@class** chứa tên package V1 và không đọc được. Giải pháp lâu dài?

**Giải thích:** Tránh buộc shared JSON vào tên Java class bằng cách dùng typed DTO và schema hoặc mã loại nghiệp vụ ổn định. Thiết kế migration cho payload cũ; không mở rộng default typing tùy tiện để bỏ qua lỗi.

**Tình huống C.** Writer mới thêm **avatarUrl**, reader cũ báo unknown property. Có nhất thiết tạo keyspace V2?

**Giải thích:** Nếu chỉ thêm field tùy chọn và reader cũ được phép bỏ qua unknown field, có thể duy trì V1 sau khi xác nhận tương thích. Nếu reader cũ bắt buộc strict hoặc thay đổi làm lệch ý nghĩa, cần chiến lược version/triển khai khác.

**Tình huống D.** Hai service cùng dùng **ObjectMapper** của Jackson, nhưng một bên không đọc được **user_id** do bên kia ghi. “Cùng thư viện” có đủ không?

**Giải thích:** Không. Naming strategy, annotation và DTO schema vẫn có thể khác nhau. Cần thống nhất tên field trong contract và dùng golden payload để kiểm chứng.

**Tình huống E.** Tùy chỉnh **RedisTemplate** thành JSON rồi gọi **@Cacheable** nhưng cache vẫn không đọc được từ template. Vì sao?

**Giải thích:** Spring Cache dùng **RedisCacheManager/RedisCacheConfiguration**, không mặc nhiên kế thừa serializer của RedisTemplate tùy chỉnh. Cần xác định đúng cache manager, key prefix, serializer và các kiểu dữ liệu đang được cache.

**Tình huống F.** Một client timeout khi ghi JSON bằng **SET**. Có chắc JSON chưa xuất hiện trong Redis không?

**Giải thích:** Không. Lệnh có thể đã được server thực thi nhưng response không tới client. Nếu retry hoặc thay đổi TTL, cần hiểu tính idempotent, thứ tự ghi và chiến lược chống cập nhật cũ ghi đè dữ liệu mới. Cấu hình ObjectMapper đúng không thay thế xử lý lỗi phân tán.

## 18. Điều cần ghi nhớ

**ObjectMapper là phần trung tâm của JSON serialization, nhưng tính nhất quán giữa nhiều bên được xác định bởi hợp đồng dữ liệu thực tế.** Một hệ thống đọc/ghi Redis an toàn cần thống nhất key, Redis data type, UTF-8, JSON schema, date/time, enum, null, field naming, TTL và chiến lược version.

Trong Spring Data Redis, đặt cấu hình mapper/serializer tại tầng infrastructure, gắn đúng serializer vào **RedisTemplate** hoặc **RedisCacheManager** mà tính năng thực sự dùng, và không vô tình thay đổi ObjectMapper chung của HTTP. Với dữ liệu chia sẻ, ưu tiên DTO và JSON contract ổn định, tránh phụ thuộc không cần thiết vào tên class Java. Khi schema thay đổi, dùng dữ liệu mẫu, test tương thích và lộ trình triển khai giữa writer/reader để ngăn lỗi xuất hiện trong giai đoạn các phiên bản chạy song song.
