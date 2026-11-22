# Thông tin kiểu, đa hình và giới hạn kiểu được phép khôi phục

Trong Spring Data Redis, dữ liệu được lưu dưới dạng byte. Redis biết một khóa đang chứa String, Hash, List, Set hoặc một cấu trúc Redis khác, nhưng **Redis không tự biết giá trị JSON nào là đối tượng Java thuộc lớp nào**. Việc chuyển dữ liệu đã lưu trở lại thành đối tượng Java là trách nhiệm của serializer/deserializer.

Điều này đặc biệt quan trọng khi ứng dụng:

- Lưu nhiều lớp Java khác nhau dưới cùng một kiểu tham chiếu như `Object`, interface hoặc abstract class.
- Sử dụng `RedisTemplate<String, Object>` và `GenericJackson2JsonRedisSerializer`.
- Tạo cache cho một đối tượng chứa trường có nhiều dạng (*polymorphic field*).
- Đọc dữ liệu Redis do phiên bản ứng dụng cũ, dịch vụ khác hoặc một thành phần bên ngoài ghi.
- Muốn kiểm soát **những kiểu Java nào được phép tạo ra khi khôi phục dữ liệu**, thay vì chấp nhận mọi tên lớp có trong payload.

Chủ đề này kết nối ba khái niệm: **thông tin kiểu** (*type metadata*), **đa hình** (*polymorphism*) và **danh sách kiểu được phép** (*allowlist*). Mục tiêu là vừa khôi phục đúng cấu trúc dữ liệu vừa tránh việc payload tùy ý quyết định lớp Java nào sẽ được tạo.

## 1. Ba tầng “kiểu” cần phân biệt

Một bản ghi cache có thể đi qua các tầng:

~~~text
Java object
  NotificationEnvelope(eventId="evt-42",
                       payload=EmailPayload(...))
           |
           | Jackson serializer
           v
JSON bytes
  {"eventId":"evt-42",
   "payload":{"kind":"email","address":"a@example.com"}}
           |
           | Spring Data Redis connection
           v
Redis key: notification:evt-42
Redis TYPE: string
Redis value: dãy byte chứa JSON
           |
           | Jackson deserializer + quy tắc nhận dạng subtype
           v
Java object
  NotificationEnvelope -> EmailPayload
~~~

| Tầng | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| **Kiểu dữ liệu Redis** | Redis hỗ trợ những lệnh nào trên key? | `TYPE notification:evt-42` trả về `string` |
| **Kiểu khai báo Java** | Code cần nhận đối tượng nào? | `NotificationEnvelope`, `NotificationPayload`, `Object` |
| **Thông tin kiểu trong payload** | Khi một trường có nhiều lớp con, cần chọn lớp cụ thể nào? | `"kind":"email"` hoặc `"@class":"com.example..."` |

Đừng nhầm `TYPE key` của Redis với tên class trong Java. Một Redis String có thể chứa JSON object, một số nguyên, Java binary serialization hoặc byte dữ liệu khác. Tương tự, dùng `opsForHash()` có nghĩa là đang thao tác Redis Hash, còn dùng `Jackson2JsonRedisSerializer` chỉ xác định cách chuyển giá trị Java sang JSON bytes.

### 1.1. Serialization và deserialization không đối xứng nếu mất thông tin kiểu

**Serialization** thường biết lớp cụ thể của object trong bộ nhớ:

~~~java
Object value = new EmailPayload("a@example.com", "Welcome");
// Lúc serialize, JVM vẫn biết value là EmailPayload.
~~~

Nhưng khi deserialization, một payload JSON bình thường chỉ có thuộc tính:

~~~json
{
  "address": "a@example.com",
  "subject": "Welcome"
}
~~~

JSON không có sẵn khái niệm “đây là EmailPayload”. Nếu code yêu cầu đọc thành `EmailPayload.class`, Jackson có thể ánh xạ trực tiếp. Nếu code yêu cầu đọc thành interface `NotificationPayload` hoặc `Object`, nó cần thêm quy tắc xác định loại đối tượng sẽ tạo.

Không phải lúc nào cũng cần ghi tên class vào JSON. Thường có ba hướng:

1. **Kiểu đích tĩnh:** ứng dụng đã biết lớp cụ thể khi gọi deserializer.
2. **Discriminator nghiệp vụ:** JSON có trường như `kind`, `type`; một tập subtype được khai báo trước.
3. **Metadata class động:** payload mang thông tin class; bộ đọc quyết định kiểu Java từ metadata, cần giới hạn kiểu nghiêm ngặt.

## 2. Khi nào có thể không cần metadata kiểu?

Hãy bắt đầu từ trường hợp đơn giản: mỗi cache key tuân theo một schema rõ ràng.

~~~java
public record ProductCache(
        String productId,
        String title,
        long priceInCents
) {}
~~~

Giá trị JSON:

~~~json
{
  "productId": "p-1001",
  "title": "Mechanical keyboard",
  "priceInCents": 12900
}
~~~

Nếu serializer được cấu hình với **kiểu đích cụ thể** `ProductCache.class`, nó không cần đọc một trường `@class` từ JSON để xác định lớp gốc.

Ví dụ Spring Data Redis dùng Jackson 2 (phù hợp nhánh Spring Data Redis 3.x):

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProductCacheRedisConfig {

    @Bean("productCacheRedisTemplate")
    RedisTemplate<String, ProductCache> productCacheRedisTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper) {

        RedisTemplate<String, ProductCache> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        objectMapper, ProductCache.class));
        return template;
    }
}
~~~

Dùng template:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;

@Service
public class ProductCacheService {

    private final RedisTemplate<String, ProductCache> redis;

    public ProductCacheService(
            @Qualifier("productCacheRedisTemplate")
            RedisTemplate<String, ProductCache> redis) {
        this.redis = redis;
    }

    public void save(ProductCache product) {
        redis.opsForValue().set(
                "product-cache:" + product.productId(),
                product,
                Duration.ofMinutes(10));
    }

    public ProductCache find(String productId) {
        return redis.opsForValue().get("product-cache:" + productId);
    }
}
~~~

Lưu ý: ví dụ bean dùng `ObjectMapper` được Spring cung cấp để giữ cấu hình JSON chung (modules, chính sách ngày giờ, v.v.). Nếu object mapper chung đã bật global default typing, serializer này cũng có thể chịu ảnh hưởng; muốn schema hoàn toàn tĩnh cần kiểm soát cấu hình mapper hoặc dùng một mapper riêng đã cấu hình rõ.

**Ưu điểm kiểu tĩnh:** payload dễ đọc, ít phụ thuộc tên class Java, dễ đổi package và dễ giới hạn loại đối tượng có thể khôi phục tại điểm đọc.

**Giới hạn:** nếu trường bên trong DTO là interface hoặc abstract class, vẫn phải giải quyết đa hình của **trường đó**. Khai báo lớp gốc cụ thể không tự động trả lời đối tượng con thuộc lớp nào.

## 3. Vì sao đa hình gây khó khi đọc từ Redis?

Giả sử hệ thống thông báo có hai cách gửi:

~~~text
NotificationPayload (interface)
        |
        +-- EmailPayload
        |      address
        |      subject
        |
        +-- SmsPayload
               phoneNumber
               message
~~~

Một envelope chứa trường interface:

~~~java
record NotificationEnvelope(
        String eventId,
        NotificationPayload payload
) {}
~~~

Lúc ghi:

~~~java
new NotificationEnvelope(
        "evt-42",
        new EmailPayload("a@example.com", "Hello")
)
~~~

Lúc đọc, Jackson biết cần tạo `NotificationEnvelope`, nhưng trường `payload` chỉ khai báo `NotificationPayload`. Nếu không có cấu hình hỗ trợ đa hình, thường sẽ xuất hiện lỗi không thể tạo instance của interface/abstract class hoặc kết quả thiếu thông tin subtype.

Một cách giải quyết kém bền vững là luôn đọc thành `Map<String, Object>` rồi tự ép kiểu:

~~~java
Object value = redis.opsForValue().get("notification:evt-42");
Map<?, ?> data = (Map<?, ?>) value;
~~~

Cách này không tự phục hồi `EmailPayload`, mất lợi ích kiểm tra kiểu của Java và buộc từng caller tự giải thích cấu trúc Map. Hãy chọn rõ hợp đồng dữ liệu cho cache.

## 4. Đa hình an toàn hơn với tên loại ổn định (`Id.NAME`)

Thường nên biểu diễn subtype bằng một **tên nghiệp vụ được định nghĩa trước**, ví dụ `email` và `sms`, thay vì ghi tên class JVM đầy đủ.

Ví dụ khai báo trong một file Java duy nhất:

~~~java
package com.example.app.cache;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

public final class NotificationTypes {
    private NotificationTypes() {}

    @JsonTypeInfo(
            use = JsonTypeInfo.Id.NAME,
            include = JsonTypeInfo.As.PROPERTY,
            property = "kind")
    @JsonSubTypes({
            @JsonSubTypes.Type(value = EmailPayload.class, name = "email"),
            @JsonSubTypes.Type(value = SmsPayload.class, name = "sms")
    })
    public sealed interface NotificationPayload
            permits EmailPayload, SmsPayload {}

    public record EmailPayload(
            String address,
            String subject) implements NotificationPayload {}

    public record SmsPayload(
            String phoneNumber,
            String message) implements NotificationPayload {}

    public record NotificationEnvelope(
            String eventId,
            NotificationPayload payload) {}
}
~~~

Khi trường `payload` được serialize theo kiểu interface đã khai báo, JSON có thể có dạng:

~~~json
{
  "eventId": "evt-42",
  "payload": {
    "kind": "email",
    "address": "a@example.com",
    "subject": "Hello"
  }
}
~~~

Khi đọc, Jackson ánh xạ `kind=email` tới `EmailPayload`, còn `kind=sms` tới `SmsPayload`, thông qua danh sách subtype đã được ứng dụng đăng ký.

~~~text
JSON field "kind"
       |
       v
   [email] --------> EmailPayload
   [sms] ----------> SmsPayload
   [unknown] ------> lỗi hoặc chính sách tương thích đã thiết kế
~~~

Đây là một **danh sách subtype được nhận biết rõ ràng**. Payload có thể yêu cầu `kind=email`, nhưng không thể tùy ý chỉ định một tên class mới chỉ bằng cách thay chuỗi `kind`, trừ khi ứng dụng đã đăng ký mapping tương ứng.

### 4.1. Kết hợp với serializer có kiểu gốc cụ thể

~~~java
import com.example.app.cache.NotificationTypes.NotificationEnvelope;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;

Jackson2JsonRedisSerializer<NotificationEnvelope> serializer =
        new Jackson2JsonRedisSerializer<>(
                objectMapper, NotificationEnvelope.class);
~~~

Khi `NotificationEnvelope` chứa `NotificationPayload`, các annotation trên interface giúp Jackson xác định subtype. Nếu sử dụng `RedisTemplate<String, NotificationEnvelope>`, đặt serializer này vào value serializer.

Hai quyết định tách biệt:

- **Lớp gốc:** `NotificationEnvelope.class` được xác định bởi template/serializer.
- **Lớp con:** `EmailPayload` hay `SmsPayload` được xác định bởi `kind` và danh sách subtype được đăng ký.

### 4.2. Vì sao alias tốt hơn tên class?

Giả sử class được đổi từ:

~~~text
com.example.app.notification.EmailPayload
~~~

sang:

~~~text
com.example.app.cache.EmailNotificationPayload
~~~

Nếu payload lưu `"kind":"email"`, ứng dụng có thể giữ alias `email` và cập nhật mapping mà không phải sửa dữ liệu cũ. Nếu payload lưu trực tiếp tên class JVM, đổi package hoặc rename class có thể làm deserialization thất bại.

Alias cũng làm JSON dễ hiểu và tách schema lưu trữ khỏi chi tiết tổ chức source code.

### 4.3. Biến thể: đăng ký subtype bằng `ObjectMapper`

Thay vì dùng `@JsonSubTypes`, có thể đăng ký tên cho subtype trong cấu hình Jackson:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.NamedType;

ObjectMapper mapper = new ObjectMapper();
mapper.registerSubtypes(
        new NamedType(NotificationTypes.EmailPayload.class, "email"),
        new NamedType(NotificationTypes.SmsPayload.class, "sms"));
~~~

Với cách này, vẫn cần quy tắc `@JsonTypeInfo(use = Id.NAME, ...)` trên base type, một mix-in tương ứng, hoặc một cơ chế cấu hình typing tương đương. Chỉ gọi `registerSubtypes` **không tự bật** việc thêm/đọc discriminator cho mọi nơi.

Khi subtype list thay đổi, hãy coi đó là thay đổi hợp đồng cache và kiểm tra khả năng đọc dữ liệu đã lưu bởi phiên bản trước.

## 5. Các dạng type identifier của Jackson

Jackson cung cấp nhiều cách mô tả kiểu trong JSON khi được cấu hình dùng đa hình.

| `JsonTypeInfo.Id` | Nội dung type identifier | Đặc điểm |
|---|---|---|
| `NAME` | Alias do ứng dụng đặt, ví dụ `email` | Dễ kiểm soát, tương đối bền vững khi refactor |
| `CLASS` | Tên class Java đầy đủ | Linh hoạt nhưng phụ thuộc package/class, bề mặt rủi ro lớn hơn |
| `MINIMAL_CLASS` | Tên class rút gọn tương đối so với base type | Vẫn gắn với cấu trúc package |
| `DEDUCTION` | Jackson suy ra subtype từ tổ hợp property | Dễ mơ hồ khi các subtype có hình dạng giống nhau |
| `NONE` | Không kèm type identifier | Chỉ phù hợp khi kiểu đích được xác định theo cách khác |

Bên cạnh `Id`, cách đưa metadata vào JSON cũng quan trọng:

- `As.PROPERTY`: đặt một property như `kind` hoặc `@class` trong object.
- `As.WRAPPER_OBJECT`: dùng object bao với một key biểu diễn type.
- `As.WRAPPER_ARRAY`: dùng array gồm type identifier và payload.
- `As.EXTERNAL_PROPERTY`: đặt discriminator bên ngoài property được phân kiểu ở những ngữ cảnh phù hợp.

Định dạng JSON thực tế thay đổi theo annotation, default typing, loại value, kiểu khai báo và phiên bản Jackson. Không nên tự giả định mọi class luôn được ghi `@class`.

## 6. `GenericJackson2JsonRedisSerializer` và metadata class

Spring Data Redis có hai cách sử dụng Jackson JSON phổ biến trong các nhánh hỗ trợ Jackson 2:

| Serializer | Hợp đồng khôi phục điển hình | Nhu cầu metadata |
|---|---|---|
| `Jackson2JsonRedisSerializer<T>` | Kiểu đích cụ thể `T` đã biết | Không nhất thiết cần metadata ở gốc; trường đa hình vẫn cần quy tắc |
| `GenericJackson2JsonRedisSerializer` | Giá trị được coi là `Object`/kiểu động | Thường cần type metadata để nhận lại lớp cụ thể |
| `StringRedisSerializer` | Chuỗi UTF-8 | Không dựng Java DTO từ JSON |
| `JdkSerializationRedisSerializer` | Java native object serialization | Mang thông tin class theo cơ chế Java serialization, rủi ro và tương thích khác JSON |

Với `RedisTemplate<String, Object>`, ứng dụng có thể lưu nhiều lớp dưới nhiều key. Một JSON generic serializer thường sử dụng thông tin kiểu để biết phải dựng lại lớp nào.

Ví dụ một payload có class identifier:

~~~json
{
  "@class": "com.example.app.cache.EmailCacheValue",
  "address": "a@example.com",
  "subject": "Hello"
}
~~~

Dấu `@class` chỉ mang tính minh họa cho một **quy ước metadata class** hay gặp. Tên property, nơi đặt type identifier và việc một value cụ thể có metadata hay không phụ thuộc cấu hình Jackson. Các kiểu collection/array có thể sử dụng hình thức type metadata khác với một bean bình thường.

### 6.1. Vấn đề về schema và bảo mật

Kiểu được ghi dưới dạng tên class tạo ra hai hệ quả:

1. **Phụ thuộc mã nguồn:** đổi package, tên class, constructor hoặc schema có thể làm các payload cũ không còn đọc được.
2. **Kiểm soát lớp được tạo:** nếu deserializer chấp nhận type identifier tùy ý, người ghi được payload có thể ảnh hưởng tới việc code nạp/khôi phục một loại Java không dự kiến.

Redis nằm trong mạng nội bộ không phải lý do để tin tưởng tuyệt đối mọi payload. Dữ liệu có thể đến từ một dịch vụ khác, một công cụ vận hành, bản snapshot cũ, môi trường dùng chung, lỗi quyền ACL hoặc một thành phần bị xâm nhập.

### 6.2. Default typing khác annotation đa hình

Jackson **default typing** là cơ chế tự bổ sung type metadata cho nhiều loại đối tượng dựa theo một chính sách chung, thường phục vụ tham chiếu kiểu `Object`, interface hoặc non-final type.

Điều này khác với cách đặt `@JsonTypeInfo` trên một interface cụ thể:

~~~text
@JsonTypeInfo tại NotificationPayload
    -> phạm vi hẹp, subtype được định nghĩa theo model

ObjectMapper default typing
    -> phạm vi áp dụng rộng hơn tới nhiều value/type
    -> phải xem xét chính sách loại được phép khôi phục
~~~

Không bật default typing trên một `ObjectMapper` dùng toàn hệ thống chỉ để sửa một cache JSON bị thiếu metadata. Mapper dùng chung có thể phục vụ HTTP API, logging hoặc nhiều serializer khác, khiến thay đổi lan ra ngoài phạm vi Redis.

## 7. `PolymorphicTypeValidator`: giới hạn kiểu được phép khôi phục

Khi dùng Jackson 2 với polymorphic type identifier dựa trên class, `PolymorphicTypeValidator` tham gia quyết định một subtype có được chấp nhận hay không. Một implementation thường dùng là `BasicPolymorphicTypeValidator`.

Có thể hình dung quy trình:

~~~text
Redis payload
     |
     v
Giải mã JSON
     |
     v
Có type id cần khôi phục?
     |
     +-- Không --> dùng kiểu đích tĩnh/định dạng đã biết
     |
     +-- Có ----> Xác định candidate subtype
                         |
                         v
                PolymorphicTypeValidator
                         |
                 +-------+--------+
                 |                |
              Cho phép          Từ chối
                 |                |
                 v                v
         Bind JSON vào DTO      Lỗi deserialization
~~~

Validator có thể xét base type, tên subtype và/hoặc subtype đã được phân giải tùy chính sách và cách Jackson gọi nó. **Allowlist phải dựa trên kiểu ứng dụng thật sự cho phép khôi phục**, không đơn thuần “mọi thứ có trên classpath”.

### 7.1. Ví dụ giới hạn theo gói DTO riêng

Ví dụ dưới đây minh họa cách kết hợp default typing với validator khi hệ thống **bắt buộc** dùng JSON class metadata động. Các API sử dụng Jackson 2 và Spring Data Redis 3.x.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.BasicPolymorphicTypeValidator;
import com.fasterxml.jackson.databind.jsontype.PolymorphicTypeValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RestrictedJsonRedisConfig {

    @Bean("restrictedJsonRedisTemplate")
    RedisTemplate<String, Object> restrictedJsonRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        PolymorphicTypeValidator validator =
                BasicPolymorphicTypeValidator.builder()
                        .allowIfSubType("com.example.app.cache.dto.")
                        .build();

        ObjectMapper mapper = new ObjectMapper();

        mapper.activateDefaultTypingAsProperty(
                validator,
                ObjectMapper.DefaultTyping.NON_FINAL,
                "@class");

        GenericJackson2JsonRedisSerializer valueSerializer =
                new GenericJackson2JsonRedisSerializer(mapper);

        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(valueSerializer);
        template.setHashKeySerializer(new StringRedisSerializer());
        template.setHashValueSerializer(valueSerializer);

        return template;
    }
}
~~~

**Ý nghĩa cấu hình:**

- `allowIfSubType("com.example.app.cache.dto.")` chỉ cho phép các subtype có tên trong namespace DTO được quy định khi validator được hỏi kiểm tra subtype. Chọn prefix **cụ thể**, có dấu chấm phân cách gói, và chỉ chứa model an toàn cho dữ liệu Redis.
- `DefaultTyping.NON_FINAL` biểu thị phạm vi kiểu cần default type metadata theo chính sách của Jackson; nó không đảm bảo mọi final class, collection hay root value đều có cùng định dạng metadata.
- `"@class"` là tên property cho type metadata theo cấu hình này, không phải trường nghiệp vụ.
- `GenericJackson2JsonRedisSerializer` sử dụng mapper đã cấu hình để ghi/đọc JSON.
- Template cấu hình cả value và hash-value serializer; không vì đã cấu hình value serializer mà Hash tự động dùng cùng chiến lược.

**Giới hạn quan trọng của ví dụ:** validator theo prefix chỉ cho phép những subtype trong namespace đó, nhưng không tự bảo đảm mọi class trong package là an toàn. Ngoài ra, payload có root type final, kiểu container JDK hoặc field có đặc tính riêng có thể không round-trip với chiến lược `NON_FINAL` và allowlist hẹp như trên. Cần chọn phạm vi default typing theo **tập DTO thực tế**, đăng ký Jackson module cần thiết và thử khôi phục các dạng dữ liệu được hỗ trợ trước khi triển khai. Nếu có thể chọn thiết kế khác, **serializer kiểu tĩnh + alias `Id.NAME` thường dễ bảo trì hơn**.

### 7.2. Allowlist chính xác theo subtype

Nếu chỉ một vài subtype được phép, nên ưu tiên một tập tường minh, hoặc dùng `@JsonSubTypes`/`registerSubtypes` với alias `Id.NAME`.

Một validator có thể giới hạn theo class/hierarchy:

~~~java
BasicPolymorphicTypeValidator validator =
        BasicPolymorphicTypeValidator.builder()
                .allowIfSubType(EmailCacheValue.class)
                .allowIfSubType(SmsCacheValue.class)
                .build();
~~~

Cách này chặt hơn một prefix package rộng, nhưng vẫn cần xem xét toàn bộ đồ thị object: một payload có thể chứa collection hoặc kiểu con lồng nhau; trong cơ chế class-based default typing, các kiểu đó cũng có thể cần được phép nếu Jackson yêu cầu metadata cho chúng. Hãy nhìn vào dữ liệu thực sự được hỗ trợ và tránh nới allowlist bằng một tiền tố quá rộng chỉ để làm lỗi biến mất.

### 7.3. Những cấu hình nên tránh

Tránh các lựa chọn như:

~~~java
// Minh họa chính sách quá rộng: không dùng cho payload không tin cậy.
BasicPolymorphicTypeValidator.builder()
        .allowIfSubType(Object.class)
        .build();
~~~

Hoặc cho phép mọi tên class bằng một validator không giới hạn tương đương. Các cấu hình này hầu như triệt tiêu mục đích xác thực subtype.

Đặc biệt, không xem việc bật một default typing “tiện lợi” cho `ObjectMapper` là biện pháp an toàn. Hãy xác định rõ những loại dữ liệu Java nào ứng dụng cần khôi phục, rồi chọn cơ chế typing đáp ứng đúng phạm vi đó.

## 8. Giới hạn kiểu không chỉ là `PolymorphicTypeValidator`

Có nhiều lớp kiểm soát độc lập, mỗi lớp giải quyết một vấn đề:

| Lớp kiểm soát | Giải quyết điều gì? | Không giải quyết điều gì? |
|---|---|---|
| Serializer `<T>` với `T` cụ thể | Cố định kiểu đích gốc | Trường `Object`/interface bên trong nếu không cấu hình |
| `@JsonTypeInfo(Id.NAME)` + tập subtype rõ ràng | Chỉ ánh xạ alias tới subtype đã đăng ký | Mọi lỗi nghiệp vụ hoặc JSON quá lớn |
| `PolymorphicTypeValidator` | Hạn chế class-based polymorphic resolution | Quyền truy cập Redis, kích thước dữ liệu, tính hợp lệ nghiệp vụ |
| Validator DTO/schema | Kiểm tra trường bắt buộc, giới hạn số, trạng thái hợp lệ | Loại trừ mọi rủi ro từ class metadata quá rộng |
| Redis ACL/TLS và network segmentation | Giới hạn ai có thể kết nối/ghi dữ liệu | Biến payload hợp lệ về cú pháp thành nghiệp vụ đúng |
| TTL và cache versioning | Giới hạn vòng đời, hỗ trợ migration | Chặn subtype độc hại |
| Giới hạn kích thước payload | Giảm nguy cơ JSON khổng lồ/đệ quy sâu | Thay thế allowlist subtype |

Nếu dùng **Java native serialization**, cơ chế filter và rủi ro lại khác với Jackson JSON. `PolymorphicTypeValidator` của Jackson **không lọc** payload `JdkSerializationRedisSerializer`. Với dữ liệu không đáng tin cậy, nên tránh Java native serialization hoặc áp dụng chính sách lọc Java serialization được thiết kế phù hợp theo cơ chế JVM.

### 8.1. Không dùng metadata class như một API công khai

Không để client HTTP tự cung cấp trực tiếp tên class Java mà server đưa nguyên vào JSON type metadata hoặc cơ chế phản chiếu (*reflection*). Nếu API cần cho người dùng chọn loại thông báo, hãy nhận các giá trị nghiệp vụ hữu hạn như `email`, `sms`, xác thực đầu vào và ánh xạ chúng tới DTO được phép.

### 8.2. Không dùng `Object.class` làm lối thoát mặc định

Khai báo mọi thứ là `Object` khiến serializer phải suy đoán hoặc mang type metadata trên nhiều điểm. Nếu ứng dụng thực tế chỉ cần ba schema cache, hãy cân nhắc ba template có kiểu cụ thể, hoặc một envelope có discriminator rõ ràng.

### 8.3. Đừng dựa vào package name làm hàng rào bảo mật duy nhất

Việc giới hạn `com.example.app.cache.dto.` chỉ hiệu quả nếu namespace đó thực sự được kiểm soát và không có class có hành vi không mong đợi khi tạo/khôi phục. Với dữ liệu nhạy cảm, kiểm soát danh sách subtype chính xác và cấu trúc DTO bất biến, thuần dữ liệu thường dễ đánh giá hơn.

## 9. Quan hệ giữa serializer của RedisTemplate và các trường Redis

Spring Data Redis hỗ trợ serializer cho những vị trí khác nhau:

~~~text
RedisTemplate<K,V>
    |
    +-- keySerializer        --> Redis key
    +-- valueSerializer      --> giá trị khi opsForValue/...
    +-- hashKeySerializer    --> field của Redis Hash
    +-- hashValueSerializer  --> value của Redis Hash
~~~

Ví dụ:

~~~java
RedisTemplate<String, ProductCache> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);

template.setKeySerializer(new StringRedisSerializer());
template.setValueSerializer(productJsonSerializer);

template.setHashKeySerializer(new StringRedisSerializer());
template.setHashValueSerializer(productJsonSerializer);
~~~

Việc cấu hình `StringRedisTemplate` với giá trị chuỗi không tự biến JSON thành `ProductCache`. Ngược lại, khi dùng `RedisTemplate` với JSON serializer, lệnh `TYPE key` vẫn có thể trả về `string` vì Redis coi value JSON là dãy byte.

Với `opsForHash()`, “kiểu” của Redis Hash field vẫn chỉ là byte value được hash-value serializer mã hóa. Đừng nhầm annotation trong DTO với việc Redis tự tạo các field Hash từ property Java.

### 9.1. Tránh đọc chéo key bằng serializer không tương thích

Ví dụ service A ghi:

~~~text
key = cache:product:42
serializer = Jackson2JsonRedisSerializer<ProductCache>
~~~

Nhưng service B đọc cùng key bằng:

~~~text
serializer = GenericJackson2JsonRedisSerializer
~~~

Service B có thể không biết kiểu đích vì JSON của A không chứa metadata class mà B kỳ vọng. Kết quả có thể là `Map`, lỗi type id hoặc một object khác dự kiến tùy serializer.

Đối với key được chia sẻ giữa các dịch vụ, cần một **hợp đồng dữ liệu** gồm: cách đặt key, serializer, encoding, schema, type identifier, phiên bản, TTL và cách xử lý dữ liệu cũ. Không trông chờ hai serializer JSON khác nhau tự hiểu lẫn nhau.

### 9.2. Các rủi ro khi thay serializer

Nếu trước đây dùng `JdkSerializationRedisSerializer` và chuyển sang JSON serializer, dữ liệu binary còn tồn tại trong Redis có thể không được parse thành JSON. Chuyển giữa hai JSON serializer cũng có thể làm đổi format type id.

Cách migration hợp lý tùy vai trò dữ liệu:

- **Cache có TTL:** có thể thay key prefix (ví dụ `product-cache:v2:42`) và để cache cũ hết hạn.
- **Cache có thể xóa:** chủ động invalidation theo phạm vi xác định và cho ứng dụng tái tạo từ nguồn chính.
- **Dữ liệu bền vững/quan trọng:** cần kế hoạch chuyển đổi có version, kiểm tra việc đọc trước khi xóa dữ liệu cũ.
- **Triển khai cuốn chiếu nhiều phiên bản:** xác minh phiên bản cũ và mới có thể đọc dữ liệu cùng tồn tại, hoặc tách namespace trong giai đoạn chuyển tiếp.

## 10. Versioning và tương thích tiến/lùi của payload đa hình

Type metadata ổn định chưa đủ để đảm bảo dữ liệu cũ vẫn đọc được. Cấu trúc fields cũng có thể thay đổi.

Giả sử format ban đầu:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-42",
  "payload": {
    "kind": "email",
    "address": "a@example.com"
  }
}
~~~

Một phiên bản mới bổ sung `subject` và đổi tên `address` thành `toAddress`. Khi đọc dữ liệu cũ, phải quyết định:

- Có chấp nhận trường thiếu và cung cấp default hợp lý không?
- Có cần `@JsonAlias("address")` để đọc cả tên cũ?
- Có chấp nhận field mới chưa biết hay báo lỗi?
- Có cần chuyển đổi từ schema version 1 sang 2 không?
- Các subtype cũ có còn được phép khôi phục trong thời gian rollout không?

**Không thay đổi allowlist bằng cách mở rộng vô hạn** để giữ tương thích. Tốt hơn là duy trì một danh sách subtype cũ có thời hạn hoặc thực hiện migration có chủ đích.

### 10.1. Phân biệt `schemaVersion` và `kind`

Hai trường mang ý nghĩa khác nhau:

~~~json
{
  "schemaVersion": 2,
  "payload": {
    "kind": "sms",
    "phoneNumber": "+84...",
    "message": "Your code"
  }
}
~~~

- `schemaVersion` cho biết phiên bản hợp đồng dữ liệu.
- `kind` cho biết biến thể đa hình cần khôi phục.

Không dùng một trường `type` chung để vừa diễn tả phiên bản schema vừa diễn tả tên Java class; việc pha trộn trách nhiệm làm dữ liệu khó migration.

### 10.2. Đổi tên class và refactor package

Với `Id.NAME` và alias ổn định, đổi tên class Java thường chỉ cần cập nhật subtype mapping. Với `Id.CLASS`, payload cũ tham chiếu trực tiếp class cũ, nên đọc dữ liệu sau refactor có thể lỗi `ClassNotFoundException`, `InvalidTypeIdException` hoặc exception được Spring Data Redis bọc lại.

Trường hợp Redis chỉ là cache, đổi namespace/key version có thể đơn giản hơn việc giữ alias tương thích với tên class cũ. Trường hợp Redis chứa dữ liệu cần bảo toàn, phải chủ động có bước chuyển đổi.

## 11. Xử lý lỗi deserialize trong runtime

Một số tình huống thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thể tạo instance của interface | Thiếu discriminator hoặc subtype mapping | Khai báo `@JsonTypeInfo` và subtype hợp lệ |
| `InvalidTypeIdException` | Không có type id, alias không hợp lệ, class không được phép | Kiểm tra schema/typing/validator, không nới allowlist tùy tiện |
| Lỗi `ClassNotFoundException` khi đọc cache | Metadata dùng class cũ sau refactor | Migration hoặc cache versioning |
| Đọc ra `LinkedHashMap` thay vì DTO | Đích là `Object` nhưng không có metadata nhận kiểu cụ thể | Dùng typed serializer hoặc discriminator rõ |
| Không parse được JSON | Serializer writer/reader khác format, value corrupt | Kiểm tra serializer và provenance của key |
| `SerializationException` trong Spring Data Redis | Lỗi serialize/deserialize được Spring bọc lại | Xem nguyên nhân gốc, key/schema/serializer |
| Class type id bị từ chối | Validator không cho phép subtype | Xác nhận subtype có thực sự được cho phép theo hợp đồng |
| Deserialize thành công nhưng dữ liệu nghiệp vụ sai | Thiếu validation hoặc schema không tương thích | Kiểm tra invariant, field, version và giới hạn kích thước |

### 11.1. Chiến lược theo vai trò dữ liệu

Nếu Redis là **cache tạm** và database khác là nguồn dữ liệu thật, có thể coi một value deserialize lỗi là cache miss, xóa hoặc đổi phiên bản key theo chính sách, rồi nạp lại từ nguồn chính. Nhưng thao tác xóa cache nên thận trọng trong hệ thống đồng thời: có thể một request khác vừa ghi value hợp lệ vào key đó.

Nếu Redis là **nguồn dữ liệu bắt buộc**, không nên bắt mọi lỗi JSON rồi trả `null` như thể khóa không tồn tại. Cần phát tín hiệu lỗi, lưu chứng cứ cần thiết và khôi phục dữ liệu theo quy trình phù hợp.

Một nguyên tắc hữu ích:

~~~text
Cache optional:
  lỗi deserialize -> metric/log -> fallback -> tái tạo cache

Dữ liệu quan trọng:
  lỗi deserialize -> báo lỗi có kiểm soát
                   -> xác định nguyên nhân và phiên bản
                   -> migration/khôi phục có thể kiểm chứng
~~~

### 11.2. Không log toàn bộ payload không tin cậy

Lỗi type id có thể kèm dữ liệu cá nhân hoặc nội dung do nguồn ngoài gửi. Log nên ghi tên key đã giảm nhạy cảm, serializer/schema version, mã lỗi và loại exception; không mặc định ghi toàn bộ JSON, token, email hay dữ liệu khác.

## 12. Cách chọn chiến lược cho một hệ thống thực tế

Giả sử ứng dụng có ba nhóm dữ liệu:

~~~text
product-cache:<id>               => ProductCache
notification-cache:<event-id>     => NotificationEnvelope
legacy-mixed-cache:<key>          => Object (nhiều kiểu Java)
~~~

Có thể đưa ra quyết định theo từng nhóm:

| Nhóm dữ liệu | Chiến lược đề xuất | Lý do |
|---|---|---|
| ProductCache chỉ có một DTO | `Jackson2JsonRedisSerializer<ProductCache>` | Không cần metadata class gốc |
| NotificationEnvelope chứa interface | Serializer typed + `@JsonTypeInfo(Id.NAME)` và subtype mapping | Đa hình tường minh, alias ổn định |
| Legacy mixed cache cần khôi phục nhiều class | Generic JSON serializer + allowlist hẹp, kế hoạch migration | Duy trì tương thích có kiểm soát |
| Cache chứa số lượng lớn chuỗi đơn giản | `StringRedisTemplate` | Tránh type metadata không cần thiết |
| Dữ liệu không tin cậy có JSON tùy ý | Parse vào DTO/schema hợp lệ do server kiểm soát | Không để input quyết định arbitrary Java class |
| Dữ liệu Java native serialization cũ | Phân tích/filter/migrate riêng | Không chịu tác động bởi Jackson validator |

Một kiến trúc dễ bảo trì thường giới hạn phạm vi của `Object` và sử dụng DTO thuần dữ liệu, bất biến khi phù hợp, với schema riêng cho từng namespace key.

### 12.1. Cây quyết định

~~~mermaid
flowchart TD
    A[Đọc JSON từ Redis] --> B{Biết trước kiểu gốc cụ thể?}
    B -->|Có| C[Typed JSON serializer]
    B -->|Không| D{Có thể định nghĩa schema/envelope?}
    D -->|Có| E[Định nghĩa DTO và discriminator NAME]
    D -->|Không, cần tương thích legacy| F[Generic JSON có kiểm soát]
    C --> G{Có field interface/abstract?}
    G -->|Có| E
    G -->|Không| H[Deserialize thành DTO đã biết]
    E --> I[Đăng ký subtype và alias được phép]
    F --> J[PolymorphicTypeValidator và danh sách subtype hẹp]
    I --> K[Kiểm tra schema/version và dữ liệu]
    J --> K
    H --> K
    K --> L[Ứng dụng sử dụng object]
~~~

Đường “Generic JSON có kiểm soát” nên được coi là ngoại lệ khi dữ liệu thực sự động hoặc cần duy trì dữ liệu legacy. Không chọn nó chỉ vì code ít phải khai báo generic type hơn.

## 13. Một số tình huống cần hiểu sâu

### 13.1. Trường khai báo `Object` bên trong một DTO

~~~java
public record AuditEnvelope(String eventId, Object payload) {}
~~~

Dù serializer gốc biết `AuditEnvelope.class`, Jackson vẫn không biết `payload` nên phục hồi thành DTO nào nếu không có thông tin bổ sung.

Có thể thay `Object` bằng một interface đóng với subtype rõ ràng, dùng một JSON tree (`JsonNode`) rồi parse theo một discriminator đáng tin cậy, hoặc thiết kế envelope có version. Không cần bật default typing cho mọi class chỉ vì một trường được khai báo quá rộng.

### 13.2. List các subtype

~~~java
public record BatchEnvelope(
        String batchId,
        java.util.List<NotificationTypes.NotificationPayload> items) {}
~~~

Dù `List` đã xác định là collection, mỗi phần tử vẫn cần được khôi phục thành `EmailPayload` hoặc `SmsPayload`. Annotation trên interface giúp xác định subtype cho từng phần tử; không nên giả định metadata của List tự đủ để phân biệt từng item.

### 13.3. Generic `List<T>` và type erasure

Nếu gọi trực tiếp `ObjectMapper.readValue(json, List.class)`, các phần tử JSON object thường được đọc thành `Map` vì `List.class` không mang `T`.

Với JSON mà không dùng Redis template, có thể chỉ định `JavaType`:

~~~java
var type = objectMapper.getTypeFactory()
        .constructCollectionType(
                java.util.List.class,
                ProductCache.class);

java.util.List<ProductCache> products =
        objectMapper.readValue(jsonBytes, type);
~~~

Hoặc dùng `TypeReference<List<ProductCache>>`. Khi cấu hình serializer trong Spring Data Redis, cần bảo đảm loại đích/JavaType tương ứng được bảo toàn; chỉ khai báo `List.class` là chưa đủ.

### 13.4. Trường ngày giờ và các module Jackson

DTO chứa `Instant`, `LocalDateTime` hoặc các loại Java Time có thể cần `JavaTimeModule` hoặc cấu hình mapper tương ứng theo version. Lỗi đọc ngày giờ **không nhất thiết là lỗi subtype**. Không bật default typing để “chữa” lỗi serializer chưa hỗ trợ kiểu dữ liệu ngày.

### 13.5. Null values và cache abstraction

Spring Cache có thể có cơ chế biểu diễn giá trị null trong cache qua serializer hoặc wrapper riêng. Một `ObjectMapper` tự tạo có thể không được cấu hình để hiểu null marker mà serializer mặc định dự kiến.

Khi dùng `GenericJackson2JsonRedisSerializer` với mapper do mình tạo và tích hợp Spring Cache, hãy kiểm tra cơ chế đăng ký null-value serializer theo API của phiên bản Spring Data Redis tương ứng. Không giả định JSON `null`, key vắng mặt và một wrapper biểu diễn null đều giống nhau.

## 14. Gợi ý minh họa cách đọc dữ liệu không hợp lệ

Giả sử contract chỉ hỗ trợ:

~~~json
{"kind":"email","address":"a@example.com","subject":"Hello"}
~~~

và:

~~~json
{"kind":"sms","phoneNumber":"+84123456789","message":"Hi"}
~~~

Nếu nhận:

~~~json
{"kind":"internal-job","command":"..."}
~~~

với `Id.NAME`, ứng dụng **không nên tự tìm một class theo chuỗi `internal-job`**. Nếu alias chưa được đăng ký, deserializer nên từ chối hoặc áp dụng một cơ chế unknown-type có chủ đích; không được suy luận bằng reflection tùy tiện.

Tương tự, nếu payload class-based cố yêu cầu:

~~~json
{
  "@class": "com.example.unknown.UnapprovedType",
  "data": "..."
}
~~~

một validator được cấu hình đúng cần từ chối subtype đó. Điều muốn thấy là lỗi đọc rõ ràng, không phải tạo một Java object tùy ý rồi mới hy vọng validation nghiệp vụ phát hiện.

## 15. Những nhầm lẫn thường gặp

### “Redis đã biết kiểu nên không cần JSON type info”

Redis biết kiểu dữ liệu **Redis** (String/Hash/...) chứ không biết Java DTO hay subtype. `TYPE key` không thay thế Java class metadata.

### “Mọi JSON đều cần `@class`”

Sai. Với serializer có kiểu đích tĩnh và DTO không chứa trường đa hình, không cần `@class`. Ngay cả khi cần đa hình, `Id.NAME` và alias hữu hạn thường là lựa chọn tốt.

### “Dùng `GenericJackson2JsonRedisSerializer` là tự động an toàn”

Không. Khả năng nhận lại kiểu động đi kèm trách nhiệm kiểm soát kiểu được phép và nguồn dữ liệu. Cấu hình mapper/validator phải phù hợp với schema và phiên bản Jackson đang dùng.

### “`@JsonSubTypes` cho phép mọi subtype của interface”

Không. Annotation khai báo các subtype cụ thể; điều này có lợi khi muốn contract chỉ chấp nhận một tập hữu hạn. Nếu thêm subtype mới, phải thay đổi mapping hoặc quy tắc đăng ký theo chủ đích.

### “Allowlist class package là đủ cho mọi dữ liệu”

Không. Package prefix không thay thế việc đánh giá class an toàn, xác thực schema, kiểm soát đầu vào và giới hạn kích thước payload. Hệ thống quan trọng thường nên dùng danh sách subtype cụ thể.

### “Đổi package class không ảnh hưởng Redis”

Có thể ảnh hưởng nếu JSON lưu tên class đầy đủ. Với `Id.NAME`, nếu giữ alias ổn định, tác động có thể nhỏ hơn.

### “Không đọc được cache thì bật validator cho `Object.class`”

Mở rộng quyền tạo object một cách cực đoan để xử lý một lỗi tương thích là lựa chọn nguy hiểm. Hãy tìm nguyên nhân thiếu type id, sai serializer hoặc thay đổi schema, rồi sửa trong phạm vi dữ liệu được hỗ trợ.

## 16. Tóm lược bằng một ví dụ thiết kế

Một thiết kế rõ ràng cho Redis cache đa hình có thể là:

~~~text
Key:
    notification:v2:evt-42

Serializer:
    Jackson2JsonRedisSerializer<NotificationEnvelope>

Payload:
    {
      "schemaVersion": 2,
      "eventId": "evt-42",
      "payload": {
        "kind": "email",
        "address": "a@example.com",
        "subject": "Hello"
      }
    }

Khôi phục:
    1. Đọc JSON từ Redis.
    2. Biết gốc là NotificationEnvelope.
    3. Đọc payload.kind.
    4. Chọn EmailPayload từ mapping đã khai báo.
    5. Kiểm tra các trường và phiên bản schema.
    6. Trả về đối tượng Java đúng kiểu.
~~~

Nếu yêu cầu thật sự buộc phải đọc nhiều loại Java không có schema chung, hãy thu hẹp phạm vi dynamic typing, kiểm soát `PolymorphicTypeValidator`, giới hạn nguồn ghi Redis và có kế hoạch chuyển đổi dữ liệu về schema có cấu trúc.

**Nguyên tắc chính:** chỉ cho phép payload lựa chọn **biến thể dữ liệu đã được ứng dụng chấp thuận**, thay vì cho phép nó tự quyết định bất kỳ class Java nào sẽ được khởi tạo. Kiểu đích tĩnh, alias subtype rõ ràng và allowlist có giới hạn giúp Spring Data Redis khôi phục dữ liệu đúng mà vẫn giữ được hợp đồng và ranh giới tin cậy khi ứng dụng phát triển.
