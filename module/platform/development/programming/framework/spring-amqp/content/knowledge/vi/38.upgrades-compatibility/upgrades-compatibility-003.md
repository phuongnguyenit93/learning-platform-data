# Di chuyển converter Jackson 2 sang Jackson 3 theo dòng phiên bản

Trong một ứng dụng **Spring AMQP**, producer thường gọi `RabbitTemplate.convertAndSend(...)` để gửi DTO tới RabbitMQ, còn consumer nhận DTO bằng `@RabbitListener`. Để truyền object Java thành JSON, nhiều dự án Spring Boot 3.x / Spring AMQP 3.x đã cấu hình `Jackson2JsonMessageConverter`. Khi chuyển sang dòng **Spring Boot 4.x và Spring AMQP 4.x**, Jackson 3 trở thành hướng tích hợp mới, cùng converter **`JacksonJsonMessageConverter`**.

Việc đổi tên class chỉ là bước đầu. Một deployment thực tế có thể có producer phiên bản cũ, consumer phiên bản mới, message cũ nằm trong queue, retry queue và dead-letter queue. Nếu thay mapper làm đổi JSON, `__TypeId__`, content type, enum/date format hoặc cách giải mã dữ liệu thiếu trường, hệ thống có thể gặp `MessageConversionException`, retry vô hạn hoặc chuyển nhầm message hợp lệ vào DLQ.

Bài học thuộc chương **Nâng cấp và tương thích** của module **SPRING_AMQP**: học tích hợp RabbitMQ với `RabbitTemplate`, `@RabbitListener`, exchange/queue/binding, routing, xác nhận publish/ACK, retry, dead-letter, giao dịch và giám sát. Ta sẽ học **lộ trình theo dòng phiên bản**, các thay đổi dependency/API, cấu hình converter ở **cả producer lẫn listener**, cách giữ hợp đồng JSON ổn định, viết kiểm thử tương thích hai chiều, và rollout không làm mất message.

**Mục tiêu sau bài:** Có thể đọc dependency graph để biết hệ thống đang dùng Jackson 2 hay 3, chọn đúng `MessageConverter`, chuyển `ObjectMapper`/type mapper đúng phiên bản, đồng thời đưa ứng dụng mới lên production mà không bắt message cũ phải được viết lại.

## 1. Phân biệt ba lớp: Jackson, Spring AMQP và RabbitMQ

~~~mermaid
flowchart LR
    P["Producer Java DTO"] --> MC["Spring AMQP MessageConverter"]
    MC --> JSON["JSON bytes + AMQP properties"]
    JSON --> EX["RabbitMQ exchange"]
    EX --> Q["Queue / retry / DLQ"]
    Q --> RC["Consumer MessageConverter"]
    RC --> L["@RabbitListener DTO"]
    L --> DB["Business transaction + ACK"]
~~~

| Lớp | Chịu trách nhiệm | Điều **không** tự thay đổi khi nâng Jackson |
|---|---|---|
| **Jackson 2/3** | Ánh xạ Java object ↔ JSON; annotation, modules, serializer/deserializer | Không quản lý RabbitMQ connection/channel |
| **Spring AMQP `MessageConverter`** | Ánh xạ DTO ↔ `org.springframework.amqp.core.Message`; xử lý content type, encoding và type headers | Không định nghĩa exchange, queue, binding, retry policy |
| **RabbitMQ** | Lưu và route bytes + headers, delivery, publisher confirms và consumer ACK/NACK | Broker **không** biết một byte JSON được tạo bởi Jackson 2 hay 3 |
| **Business layer** | Kiểm tra schema, ghi DB, idempotency và xử lý lỗi | Không tự nhận exactly-once chỉ vì converter parse thành công |

Việc đổi converter **không yêu cầu đổi RabbitMQ queue type**, cũng không tự thay đổi routing key. Nhưng một consumer parse lỗi sẽ tác động trực tiếp đến hành vi ACK/NACK, retry và DLQ, vì exception thường xảy ra **trước khi method nghiệp vụ được gọi**.

## 2. Lộ trình theo phiên bản Spring AMQP và Spring Boot

Thông tin dưới đây là hướng chuyển đổi cho các **nhánh phiên bản**, không khuyến khích tự trộn các bản jar:

| Dòng ứng dụng | JSON mặc định/ưu tiên trong hệ Spring | Spring AMQP converter điển hình | Hành động khi migration |
|---|---|---|---|
| **Spring Boot 3.x** với Spring AMQP 3.x (ví dụ 3.2) | **Jackson 2** | `Jackson2JsonMessageConverter` | Giữ ổn định producer/consumer, chuẩn bị golden messages và API inventory |
| **Spring AMQP 4.0+** | Có converter **Jackson 3** mới | `JacksonJsonMessageConverter`; API Jackson 2 được đánh dấu deprecated for removal từ **4.0** | Chuyển code sang converter mới, type mapper mới và Jackson 3 mapper |
| **Spring Boot 4.0+** (dựa trên Spring Framework 7) | **Jackson 3** là hướng auto-configuration ưu tiên | Dùng converter Jackson 3 khi tích hợp RabbitMQ | Nâng nền tảng đồng bộ và kiểm tra khác biệt serialization |
| **Giai đoạn quá độ Boot 4** | Có thể tồn tại Jackson 2 **song song** Jackson 3 trong classpath | Có thể dùng hỗ trợ Jackson 2 tạm thời nếu nhánh còn cung cấp | Chỉ làm cầu nối có kế hoạch xóa, không xem là đích lâu dài |
| **Các bản vá/nhánh tiếp theo** | Tính năng và ngày loại bỏ có thể đổi theo release | Xác minh Javadoc/BOM của nhánh đích | Không giả định API deprecated sẽ tồn tại mãi |

**Mốc chính xác cần nhớ:**

- Ở **Spring AMQP 3.2**, `Jackson2JsonMessageConverter` sử dụng `com.fasterxml.jackson.databind.ObjectMapper` thuộc Jackson 2.
- Từ **Spring AMQP 4.0**, xuất hiện `JacksonJsonMessageConverter` sử dụng Jackson 3; `AbstractJackson2MessageConverter`, `Jackson2JsonMessageConverter`, `Jackson2JavaTypeMapper` và các API liên quan được **đánh dấu deprecated for removal** — *không đồng nghĩa lập tức bị xóa ở 4.0*.
- **Spring Boot 4** ưu tiên `tools.jackson.databind.json.JsonMapper`/Jackson 3. Boot có cơ chế tương thích Jackson 2 tạm thời, nhưng dự án cần lên kế hoạch chuyển hẳn.

Với nâng cấp lớn, hãy nâng đến **bản vá cuối phù hợp của dòng cũ**, đọc migration guide của cả **Spring Boot lẫn Spring AMQP**, sau đó chọn phiên bản đích từ **BOM nhất quán**. Không nâng riêng một jar `spring-amqp` lên 4.x trong ứng dụng Boot 3.x chỉ để có converter mới.

### 2.1. Bản đồ đổi tên class

| Dòng Jackson 2 | Dòng Jackson 3 | Nhận xét |
|---|---|---|
| `Jackson2JsonMessageConverter` | **`JacksonJsonMessageConverter`** | Converter JSON cho Spring AMQP |
| `AbstractJackson2MessageConverter` | `AbstractJacksonMessageConverter` | Base class, thường không dùng trực tiếp |
| `Jackson2XmlMessageConverter` | `JacksonXmlMessageConverter` | Nếu ứng dụng có XML, cũng cần chuyển |
| `Jackson2JavaTypeMapper` | `JacksonJavaTypeMapper` | API quản lý type metadata |
| `DefaultJackson2JavaTypeMapper` | `DefaultJacksonJavaTypeMapper` | Type mapper được dùng với Jackson 3 |
| `com.fasterxml.jackson.databind.ObjectMapper` | `tools.jackson.databind.json.JsonMapper` hoặc Jackson 3 `tools.jackson.databind.ObjectMapper` tùy API | **Khác package và binary type**, không thể truyền mapper cũ vào converter mới |
| Các Jackson 2 modules/serializers | Tương ứng Jackson 3 modules/serializers | Kiểm tra APIs, signatures và modules tương thích trước khi đổi |

**Điểm ngoại lệ cần nhớ:** Jackson 3 chuyển nhiều group ID và package từ `com.fasterxml.jackson` sang `tools.jackson`, **nhưng annotation module vẫn có namespace `com.fasterxml.jackson.annotation`** theo migration guide Spring Boot 4. Đừng thay mọi import `@JsonProperty`, `@JsonIgnore` bằng một package tưởng tượng `tools.jackson.annotation`.

## 3. Kiểm kê cấu hình và dependency trước khi sửa

### 3.1. Truy tìm mọi chỗ dùng JSON trong ứng dụng

Không chỉ tìm trong một `@Configuration`. Các điểm cần kiểm kê:

- Producer `RabbitTemplate` và các bean `RabbitTemplate` đặt tên riêng.
- `SimpleRabbitListenerContainerFactory` / `DirectRabbitListenerContainerFactory` và `@RabbitListener(messageConverter=...)` nếu có override.
- `RabbitMessagingTemplate`, message adapter, Spring Integration AMQP gateways, stream converter hoặc listener batch.
- `ObjectMapper`/`JsonMapper` được khai báo thủ công, module Java Time, Kotlin, custom serializer/deserializer.
- `DefaultClassMapper`, `DefaultJackson2JavaTypeMapper`, `__TypeId__`, `__ContentTypeId__`, `__KeyTypeId__` và các enum/type discriminator.
- Header/body từ non-Java producers, message còn trong **retry/DLQ**, outbox archive và request/reply.

Một ứng dụng có thể đang sử dụng **converter khác nhau cho producer và consumer**. Nếu chỉ đổi bean producer thì `@RabbitListener` vẫn có thể dùng `SimpleMessageConverter`; method nhận `byte[]` hoặc lỗi convert thay vì DTO mong đợi.

### 3.2. Đọc dependency đã được resolve

Ví dụ Maven (để người học chạy trong dự án của họ):

~~~bash
mvn dependency:tree \
  -Dincludes=org.springframework.amqp:*,com.fasterxml.jackson.core:*,tools.jackson.core:*

# Khi cần xem đầy đủ nguồn kéo dependency:
mvn dependency:tree
~~~

Ví dụ Gradle:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind \
  --configuration runtimeClasspath

./gradlew dependencyInsight --dependency spring-amqp \
  --configuration runtimeClasspath
~~~

Các lệnh này để **minh họa workflow**, không phải lệnh đã chạy trên repository. Kiểm tra cả runtime classpath của artifact container, không chỉ dependency được khai báo trực tiếp. Có thể có **cả Jackson 2 và 3 cùng tồn tại** trong giai đoạn chuyển đổi; do package khác nhau, sự tồn tại đồng thời không có nghĩa code tự động chọn đúng mapper.

### 3.3. Dùng BOM thay vì vá bằng version rời rạc

Ví dụ Maven trong dự án Spring Boot (không ghim version cho các dependency được BOM quản lý):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <!-- Đảm bảo Jackson 3 đã có trên classpath thông qua
         starter hoặc dependency management phù hợp của ứng dụng. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-json` minh họa cách bổ sung hỗ trợ JSON cho ứng dụng Boot; không có nghĩa mọi microservice phải khai báo đúng hai starter này. Kiểm tra tổ hợp Spring Boot/AMQP/Framework và Java runtime được nhánh đích hỗ trợ. Với dự án đa module hoặc dùng Gradle, thống nhất dependency management để tránh một module kéo `spring-rabbit` cũ trong khi module khác sử dụng converter mới.

## 4. Trước và sau: thay converter nhưng giữ hợp đồng JSON

Giả sử hai service trao đổi một DTO ổn định:

~~~java
package com.example.messaging.dto;

// DTO truyền trên message bus, không phải JPA entity.
public record OrderCreated(
        String eventId,
        String orderId,
        int schemaVersion) {
}
~~~

Trên wire, ứng dụng mong đợi một record JSON:

~~~json
{
  "eventId": "event-7",
  "orderId": "order-42",
  "schemaVersion": 1
}
~~~

**Hợp đồng nằm ở bytes + metadata, không ở tên Java converter.** Nếu cùng DTO cho ra JSON tương thích và consumer giải mã được type an toàn, producer Jackson 2 và consumer Jackson 3 có thể giao tiếp qua RabbitMQ. Nhưng đây là một **khả năng phải test**, không phải cam kết mặc định cho mọi serializer, module và trường hợp polymorphic.

### 4.1. Cấu hình cũ: Spring AMQP 3.x và Jackson 2

~~~java
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class LegacyRabbitJsonConfig {

    @Bean
    MessageConverter rabbitJsonConverter() {
        // Định nghĩa vùng class được phép giải mã từ type headers.
        return new Jackson2JsonMessageConverter(
                "com.example.messaging.dto");
    }
}
~~~

Ở nhánh cũ, một mapper tùy chỉnh thường là `com.fasterxml.jackson.databind.ObjectMapper` và có thể được truyền cho `Jackson2JsonMessageConverter(ObjectMapper, String...)`. Khi chuyển lên Spring AMQP 4.x, code cũ có thể vẫn biên dịch nếu nhánh đó **còn** giữ API deprecated và dependency Jackson 2, nhưng đó là **cầu nối quá độ**, không phải đường nâng cấp mục tiêu.

### 4.2. Cấu hình mới: Spring AMQP 4.x và Jackson 3

Ví dụ một ứng dụng **Spring Boot 4** có bean `JsonMapper` được Boot cấu hình (với hỗ trợ JSON trên classpath):

~~~java
import java.util.Map;
import org.springframework.amqp.support.converter.DefaultClassMapper;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.json.JsonMapper;
import com.example.messaging.dto.OrderCreated;

@Configuration
class RabbitJson3Config {

    @Bean("rabbitJsonConverter")
    JacksonJsonMessageConverter rabbitJsonConverter(JsonMapper jsonMapper) {
        DefaultClassMapper classMapper = new DefaultClassMapper();
        classMapper.setTrustedPackages("com.example.messaging.dto");
        classMapper.setIdClassMapping(Map.of(
                "order.created.v1", OrderCreated.class));

        // DefaultClassMapper được tạo thủ công, không là Spring bean riêng.
        classMapper.afterPropertiesSet();

        JacksonJsonMessageConverter converter =
                new JacksonJsonMessageConverter(
                        jsonMapper, "com.example.messaging.dto");
        converter.setClassMapper(classMapper);
        return converter;
    }
}
~~~

Ở đây:

- `JacksonJsonMessageConverter` thuộc `org.springframework.amqp.support.converter`, **không có số 2 trong tên**.
- `JsonMapper` thuộc package **`tools.jackson.databind.json`**, không phải `com.fasterxml.jackson.databind`.
- `DefaultClassMapper` ánh xạ một **type ID ổn định** `order.created.v1` sang DTO. Khi publish qua converter, metadata `__TypeId__` có thể dùng alias này thay vì tên class đầy đủ; khi nhận, alias giúp giải mã trong bối cảnh Java package thay đổi.
- `setTrustedPackages(...)` chỉ cho phép resolver nạp class từ nhóm package đã được phép. **Không dùng `"*"` để trust toàn bộ packages** trong hệ thống nhận message không tin cậy.
- `afterPropertiesSet()` xây dựng mapping class → type ID. Khi để Spring quản lý `DefaultClassMapper` như một bean độc lập, Spring thực hiện lifecycle; khi tạo thủ công như ví dụ, ta gọi tường minh.

**Giới hạn:** nếu bạn tạo `JacksonJsonMessageConverter()` với mapper nội bộ, nó **không tự đồng nhất mọi setting** với `JsonMapper` do Spring Boot tạo. Nếu ứng dụng dùng module Java Time, Kotlin, custom serializers, naming strategy hay format ngày giờ, nên truyền mapper đã cấu hình phù hợp và kiểm tra output. Đừng cho rằng `spring.jackson.*` áp dụng cho mọi mapper được new thủ công.

### 4.3. Gắn converter vào đúng cả hai đường

Với Spring AMQP không dựa hoàn toàn vào auto-configuration, có thể nối converter vào producer và listener factory:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class RabbitJson3Wiring {

    @Bean
    RabbitTemplate rabbitTemplate(
            ConnectionFactory connectionFactory,
            @Qualifier("rabbitJsonConverter")
            JacksonJsonMessageConverter converter) {

        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(converter);
        return template;
    }

    @Bean
    SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            ConnectionFactory connectionFactory,
            @Qualifier("rabbitJsonConverter")
            JacksonJsonMessageConverter converter) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(converter);
        return factory;
    }
}
~~~

Đoạn này bổ sung cho `RabbitJson3Config` ở trên và giả định đã có `ConnectionFactory`. Trong Spring Boot, auto-configuration có thể tạo `RabbitTemplate` và listener factory; **không vừa để Boot tự tạo vừa đăng ký hai bean cùng tên**. Hãy chọn phương án sử dụng bean converter do Boot auto-wire **hoặc** cấu hình factory/template tường minh như trên; xác minh bean thực được injection bằng integration test.

Consumer:

~~~java
import com.example.messaging.dto.OrderCreated;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class OrderCreatedListener {
    private final OrderService service;

    OrderCreatedListener(OrderService service) {
        this.service = service;
    }

    @RabbitListener(queues = "orders.created.q")
    public void onOrderCreated(OrderCreated event) {
        service.applyIdempotently(event);
    }
}
~~~

`OrderService` và `applyIdempotently(...)` là code nghiệp vụ giả định; xử lý event trùng phải được bảo vệ ở mức database/side effects. Khi converter báo lỗi **trước khi gọi listener**, exception có thể được phân loại là lỗi conversion và đi qua handler/recoverer khác lỗi nghiệp vụ; phải thử riêng.

### 4.4. Hai bước chuyển đổi ở @RabbitListener

Khi Spring gọi một listener method, có thể có **hai giai đoạn**:

1. Spring AMQP `MessageConverter` chuyển `org.springframework.amqp.core.Message` (bytes + properties) thành payload object.
2. Bộ chuyển đổi argument ở tầng Spring Messaging chọn/ép kiểu payload để khớp tham số method `@RabbitListener`.

Vì vậy, cấu hình sai converter giai đoạn 1 có thể làm listener nhận `byte[]` thay vì DTO, còn một số lỗi chỉ xuất hiện ở bước argument conversion. Nếu một method nhận `Message` hoặc raw bytes để debug, việc nó hoạt động **không chứng minh** typed listener có thể giải mã cùng message.

Khi khai báo `@RabbitListener` ở method với một tham số DTO **concrete**, Spring thường suy luận type từ tham số và có thể ưu tiên type đó hơn header `__TypeId__`. Khi khai báo listener ở **class-level** cùng nhiều `@RabbitHandler`, lựa chọn handler dựa nhiều hơn vào type sau conversion. Cần kiểm thử cả hai kiểu khi migration.

## 5. Type metadata và type mapper là vùng dễ vỡ nhất

JSON bytes bản thân có thể tương thích, nhưng Spring AMQP còn đặt type metadata trong `MessageProperties`:

| Header / property | Dùng để làm gì? | Rủi ro khi nâng cấp |
|---|---|---|
| `contentType` | Chỉ JSON, ví dụ `application/json` hoặc vendor `application/*+json` | Converter có thể trả raw `byte[]` nếu không nhận ra content type |
| `contentEncoding` hoặc `charset` trong media type | Xác định charset decode | Chuỗi Unicode hỏng khi producer/consumer dùng encoding khác |
| `__TypeId__` | Định danh type payload | Tên class/package thay đổi, class không có ở consumer mới |
| `__ContentTypeId__` | Type phần tử collection (nếu được dùng) | `List<OrderCreated>` thành list of map hoặc lỗi type |
| `__KeyTypeId__` | Type key của map (nếu được dùng) | Mất thông tin key hoặc không resolve type |
| `inferredArgumentType` | Type Spring suy ra từ method `@RabbitListener` | Method signature có thể override thông tin `__TypeId__` |
| Custom headers `eventType`/`schemaVersion` | Hợp đồng nghiệp vụ độc lập Java package | Phải duy trì versioning và mapping rõ ràng |

### 5.1. Ưu tiên alias ổn định thay vì FQN của Java class

Ví dụ **dễ vỡ**:

~~~text
__TypeId__ = com.oldcompany.order.messages.OrderCreated
~~~

Sau khi tách module hoặc đổi package thành `com.example.messaging.dto.OrderCreated`, consumer có thể không tìm thấy class cũ. Trong thời gian migration, cần hỗ trợ alias hoặc map FQN cũ đến DTO mới **theo danh sách cho phép**, không cho phép nạp tùy ý class từ header.

Ví dụ **ổn định hơn**:

~~~text
contentType   = application/json
__TypeId__    = order.created.v1
eventType     = order.created
schemaVersion = 1
eventId       = event-7
~~~

Type alias có thể được đặt bằng `DefaultClassMapper.setIdClassMapping(...)` hoặc `DefaultJacksonJavaTypeMapper.setIdClassMapping(...)` theo chiến lược type mapper bạn chọn. Nếu converter cũ đã phát FQN trong nhiều ngày, đừng đổi sang alias mới mà không kiểm tra consumer cũ có hiểu alias đó hay không.

### 5.2. INFERRED hay TYPE_ID?

Theo mặc định, type **inferred** của một parameter concrete tại method-level `@RabbitListener` có thể được ưu tiên hơn type header. Điều này có ích nếu producer gửi class DTO khác tên Java package nhưng consumer vẫn nhận đúng DTO riêng của nó.

Khi cần deserialize một **subclass** theo `__TypeId__` (ví dụ listener nhận base class hoặc một event hierarchy), có thể đổi precedence:

~~~java
import org.springframework.amqp.support.converter.JacksonJavaTypeMapper;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;

JacksonJsonMessageConverter converter =
        new JacksonJsonMessageConverter("com.example.messaging.dto");
converter.setTypePrecedence(
        JacksonJavaTypeMapper.TypePrecedence.TYPE_ID);
~~~

**Không bật `TYPE_ID` toàn hệ thống theo thói quen.** Nó làm thông tin từ message header quan trọng hơn type của method, có rủi ro bảo mật và lỗi mapping nếu producer không đáng tin. Nếu sử dụng custom `DefaultJacksonJavaTypeMapper`, đặt precedence trên mapper hoặc xác minh setter của converter không bị bỏ qua.

### 5.3. Class mapper và Java type mapper không thay nhau một cách vô thức

`DefaultClassMapper` phù hợp khi muốn map đơn giản alias → class DTO; `DefaultJacksonJavaTypeMapper` biểu diễn cả `JavaType` cho collection/generic type. Cùng thuộc tầng type metadata nhưng **không tự tương đương trong mọi trường hợp**:

- Với DTO đơn giản, một class alias thường đủ.
- Với `List<OrderCreated>`, `Map<String, OrderCreated>`, nested generics hoặc polymorphic events, cần test headers element/key và generic type resolution.
- Khi đổi `DefaultJackson2JavaTypeMapper` sang `DefaultJacksonJavaTypeMapper`, các type tùy chỉnh trả về/nhận vào dùng **Jackson 3 `tools.jackson.databind.JavaType`**, không phải `com.fasterxml.jackson.databind.JavaType`.
- Nếu hệ thống gửi event cho consumer không sử dụng Java, nên dựa vào **schema/eventType/version rõ ràng** thay vì yêu cầu consumer hiểu tên lớp trong header Spring.

### 5.4. Trusted packages: không dùng wildcard rộng

Các mapper có `trustedPackages` để giới hạn class có thể resolve từ type headers. Đặt `"*"` có nghĩa **trust all**, không phải “mở một tính năng Jackson 3 bắt buộc”. Một producer bên ngoài có thể tự đặt header kiểu Java; việc tin cậy mọi package làm tăng bề mặt deserialization.

Với message chỉ có type cụ thể, ưu tiên mapping alias allowlist. Kiểm thử message có header `__TypeId__` trỏ tới một class không được phép: consumer phải **từ chối an toàn**, log đủ thông tin nhận diện message (không lộ payload nhạy cảm), và route tới kênh lỗi theo policy.

## 6. Các khác biệt JSON cần so sánh bằng dữ liệu thực

**Jackson 3 không cam kết tạo từng byte giống Jackson 2** khi hai bên dùng các cấu hình và module khác nhau. Ngay cả khi cùng deserialize thành DTO, thay đổi format có thể phá consumer bên ngoài, chữ ký số payload hoặc logic dùng JSON string làm idempotency key.

| Nhóm dữ liệu | Ví dụ | Kiểm tra khi migration |
|---|---|---|
| **Ngày giờ** | `Instant`, `LocalDateTime`, offset/timezone | ISO-8601 hay timestamp, milliseconds/nanoseconds, timezone và module hỗ trợ |
| **Số thập phân** | `BigDecimal("10.00")` | Precision/scale, notation, rounding, giữ tiền tệ dưới dạng chuỗi hay số |
| **Enum** | `PAID`, `paid`, renamed constants | Case sensitivity, unknown enum, giá trị legacy |
| **Tên field** | `orderId` vs `order_id` | Naming strategy, `@JsonProperty`, alias và versioning |
| **Null/missing** | `couponCode: null` hoặc thiếu field | Default value, null handling, primitive 0 vs thiếu |
| **Unknown fields** | Producer mới thêm `campaignId` | Consumer cũ xử lý trường mới như thế nào |
| **Polymorphism** | `PaymentEvent` có nhiều subtype | Discriminator, `__TypeId__`, `@JsonTypeInfo` và trust allowlist |
| **Collection/generic** | `List<OrderItem>`, `Map<String, Long>` | Type headers, element type và inferred method parameter |
| **Binary/Unicode** | Tiếng Việt, emoji, base64, escape | UTF-8, contentEncoding, escape và downstream không dùng default charset sai |
| **Custom serializer** | Một field được serialize theo format công ty | Module đã chuyển sang Jackson 3 và cùng output |
| **Mix-ins / views** | Ẩn field trong JSON View | Mapping khác do default hoặc mix-in không được nạp |
| **Payload signed/hashed** | Chữ ký dựa trên bytes hoặc JSON canonical | Thứ tự field/whitespace có thể đổi, cần định nghĩa canonicalization riêng |

### 6.1. Không dùng byte equality làm tiêu chí duy nhất

Hai JSON sau **có thể có ý nghĩa dữ liệu giống nhau** nhưng không giống bytes:

~~~json
{"eventId":"e42","amount":10.00}
~~~

~~~json
{"amount":10.0,"eventId":"e42"}
~~~

Với consumer JSON thông thường, có thể so **semantic equality** sau deserialize. Nhưng nếu hệ thống hash/kiểm chữ ký trên body, khác bytes là khác hợp đồng: cần canonical serialization hoặc định nghĩa schema chính xác, không chỉ mong Jackson 2/3 “tình cờ” in cùng thứ tự.

### 6.2. Mặc định Jackson 3 và compatibility mode của Boot

Spring Boot 4 giới thiệu cấu hình sau để đưa mapper **do Boot auto-configure** gần các defaults Jackson 2 từng dùng trong Boot 3:

~~~yaml
spring:
  jackson:
    use-jackson2-defaults: true
~~~

Đây là **công cụ hỗ trợ quá độ**, không phải phép biến Jackson 3 thành Jackson 2 và không bảo đảm mọi module/custom serializer cho cùng bytes. Quan trọng hơn, property này áp dụng cho **JsonMapper do Boot cấu hình**; nếu ứng dụng `new JacksonJsonMessageConverter()` hoặc `JsonMapper.builder().build()` riêng, hãy cấu hình và kiểm tra mapper đó, không suy đoán property tự lan sang mọi instance.

Theo migration guide Boot 4, Jackson auto-configuration còn:

- Ưu tiên `JsonMapper` cho JSON (và `XmlMapper` cho XML); khai báo `com.fasterxml.jackson.databind.ObjectMapper` bean không tự thay thế `JsonMapper` mới.
- Có thể phát hiện/đăng ký các Jackson modules trên classpath khác với cách Boot 3 xử lý. Nếu thay đổi output, kiểm tra module được nạp thực tế, không chỉ mapper feature.
- Có một số property điều khiển JSON read/write chuyển vị trí, và các customizer class được đổi tên. Đối chiếu migration guide trước khi copy các `spring.jackson.*` cũ.

Nếu muốn giữ Jackson 2 trong giai đoạn tạm thời, **Spring Boot 4.0** cung cấp module deprecated `spring-boot-jackson2` với các cấu hình `spring.jackson2.*`. Đây là **phương án ngắn hạn** khi dependency chưa migrate, không nên xem là chiến lược dài hạn. Nó cũng **không tự thay đổi converter Spring AMQP bạn đã khai báo**: vẫn phải chọn converter Jackson 2 và cung cấp các dependency tương ứng.

### 6.3. Jackson 3 serializer API và annotations

Thay đổi có thể không dừng ở `ObjectMapper` → `JsonMapper`:

- Custom serializers/deserializers của Jackson 2 có thể cần chuyển sang `tools.jackson.databind.ValueSerializer` / `ValueDeserializer`, với chữ ký method tương ứng.
- JSON parser/generator, codec, `JsonNode` và module API sử dụng `tools.jackson.*` trong Jackson 3.
- Các annotation phổ biến `@JsonProperty`, `@JsonIgnore`, `@JsonCreator` tiếp tục thuộc `com.fasterxml.jackson.annotation` theo hướng dẫn di chuyển; **đừng rename toàn bộ annotations bằng regex**.
- Các module của framework ngoài (Kotlin, Hibernate, Spring Security, Java Time hoặc thư viện bên thứ ba) phải kiểm tra có phiên bản Jackson 3 tương thích hay chưa. Không nạp một Jackson 2 module cũ bằng ép kiểu vào `tools.jackson` API mới.

Với custom code, hãy tạo **golden input/output tests** cho từng serializer trước khi nâng thư viện; sau khi thay, chạy lại cùng fixtures để tìm khác biệt có chủ ý hay lỗi.

## 7. Content type, charset và trường hợp không có type header

Một JSON message nên có tối thiểu:

~~~text
contentType = application/json
body        = UTF-8 JSON bytes
__TypeId__  = order.created.v1      (nếu dùng Spring type mapping)
eventType   = order.created        (hợp đồng nghiệp vụ)
schemaVersion = 1
~~~

Trong Spring AMQP, `JacksonJsonMessageConverter` phát metadata JSON tương ứng khi `convertAndSend(dto)` và converter đã được gắn vào template. Nếu producer là hệ thống khác Spring hoặc gửi raw bytes, cần **chủ động đặt `contentType`** cùng những headers đã quy định.

### 7.1. Tại sao consumer nhận byte[]?

Một converter có thể không coi content type là JSON (ví dụ `application/octet-stream` hoặc custom media type không nhận biết). Tùy setting và phiên bản, nó có thể:

- Giả định JSON cho content type bị thiếu hoặc ở giá trị mặc định nhất định.
- Trả raw body `byte[]` khi content type không được hỗ trợ.
- Ném lỗi khi parse JSON, type header hoặc charset không hợp lệ.

Đừng dựa vào fallback mặc định như một hợp đồng lâu dài. Spring AMQP có `setAssumeSupportedContentType(boolean)` và `setSupportedContentType(...)` trong họ Jackson converters, nhưng quyết định nới hay chặt phải dựa trên **producer thực tế và chính sách validation**.

### 7.2. Charset và Unicode

Ưu tiên **UTF-8** và khai báo rõ content type khi nhiều ngôn ngữ cùng gửi message. Nếu legacy producer dùng UTF-16 hay `contentEncoding` khác, test phải bao gồm tên khách hàng tiếng Việt, emoji và ký tự đặc biệt; tránh một bản vá biến chuỗi hợp lệ thành chữ bị lỗi.

Tài liệu Spring AMQP mô tả việc converter xem `contentEncoding`, `charset` trong `contentType` và charset mặc định theo quy tắc cụ thể. Hãy kiểm tra nhánh version: thứ tự ưu tiên và phạm vi MIME type có thể thay đổi qua các bản.

### 7.3. Không có __TypeId__ không có nghĩa luôn parse được DTO

Khi method-level `@RabbitListener` nhận một tham số DTO concrete, Spring có thể suy luận class đích để deserialize dù không có `__TypeId__`. Nhưng khi gọi `converter.fromMessage(message)` trực tiếp hoặc nhận một interface, collection generic hay class-level handler, type inference có thể không đủ: kết quả có thể là `Map` hoặc lỗi mapping.

Vì thế cần có **hai loại test**: test một converter nhận message thuần `MessageProperties`, và test listener thật sau adapter/argument conversion. Một trong hai pass không bảo đảm loại kia pass.

## 8. Kiểm thử tương thích hai chiều không cần broker

Trong **giai đoạn chuyển đổi khi class Jackson 2 deprecated còn tồn tại ở nhánh Spring AMQP 4.x đang dùng**, có thể chạy thử cả hai converter trong cùng test classpath (với dependencies Jackson 2/3 tương thích). Bài test dưới kiểm chứng hai phía trao đổi cùng DTO và type alias:

~~~java
package com.example.messaging.dto;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.support.converter.DefaultClassMapper;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;

class JacksonMigrationContractTest {

    @Test
    @SuppressWarnings("removal") // Chỉ cho migration test bridge.
    void oldAndNewConvertersReadEachOthersMessages() {
        DefaultClassMapper aliases = new DefaultClassMapper();
        aliases.setTrustedPackages("com.example.messaging.dto");
        aliases.setIdClassMapping(Map.of(
                "order.created.v1", OrderCreated.class));
        aliases.afterPropertiesSet();

        Jackson2JsonMessageConverter oldConverter =
                new Jackson2JsonMessageConverter("com.example.messaging.dto");
        oldConverter.setClassMapper(aliases);

        JacksonJsonMessageConverter newConverter =
                new JacksonJsonMessageConverter("com.example.messaging.dto");
        newConverter.setClassMapper(aliases);

        OrderCreated event = new OrderCreated("e-7", "order-42", 1);

        Message oldWire =
                oldConverter.toMessage(event, new MessageProperties());
        assertEquals("application/json",
                oldWire.getMessageProperties().getContentType());
        assertEquals("order.created.v1",
                oldWire.getMessageProperties().getHeaders().get("__TypeId__"));
        assertEquals(event, newConverter.fromMessage(oldWire));

        Message newWire =
                newConverter.toMessage(event, new MessageProperties());
        assertEquals(event, oldConverter.fromMessage(newWire));
    }
}
~~~

**Điều kiện thực hiện:** DTO `OrderCreated` từ phần 4 nằm trong package như test; JUnit 5 và cả Jackson 2/3 phải có mặt. `Jackson2JsonMessageConverter` được sử dụng **chỉ trong test bridge**, không phải lời khuyên giữ mã deprecated ở production. Test này **chưa** kiểm tra queue routing, ACK, DLQ hoặc sự khác biệt của hai deployment độc lập.

Khi bản Spring AMQP tương lai **không còn** class Jackson 2, vẫn có thể duy trì contract test bằng **golden message fixture** do service cũ phát, hoặc chạy producer cũ và consumer mới trong hai tiến trình/test containers riêng. Không giữ dependency lỗi thời chỉ để duy trì một bài test nếu có cách kiểm chứng wire contract an toàn hơn.

### 8.1. Golden messages nên lưu gì?

Một fixture nên chứa:

~~~text
event id / schema version
body bytes (UTF-8 JSON, có thể encoded để giữ nguyên byte)
contentType / contentEncoding
__TypeId__ / __ContentTypeId__ / __KeyTypeId__
business headers và expected DTO
expected result khi field thiếu, enum lạ, null hoặc sai schema
~~~

Tạo ít nhất các case: *producer cũ → consumer mới*, *producer mới → consumer cũ*, *message không có type header*, *type alias khác*, *header FQN legacy*, *date/time*, *BigDecimal*, *unknown field*, *Unicode*, *polymorphism*, *collection* và *payload không hợp lệ*.

**Quan trọng:** so **giá trị được parse, contract/version và side effects**, không chỉ việc `newConverter.fromMessage` không ném exception. Một DTO có `amount=0` do missing field vẫn deserialize “thành công” nhưng sai nghiệp vụ.

## 9. Kiểm thử integration với RabbitMQ thật

Unit test converter chưa chứng minh `RabbitTemplate` và `@RabbitListener` dùng cùng mapper. Bài integration test cần chạy trên **RabbitMQ thực** (broker staging hoặc Testcontainers) với topology riêng, không dùng queue production.

### 9.1. Kiến trúc kiểm thử hai phiên bản

~~~mermaid
flowchart TD
    OLD["Producer Jackson 2"] --> EX["orders.events.x"]
    NEW["Producer Jackson 3"] --> EX
    EX --> Q1["queue test-old-consumer"]
    EX --> Q2["queue test-new-consumer"]
    Q1 --> C2["Consumer Jackson 2"]
    Q2 --> C3["Consumer Jackson 3"]
    C2 --> A["Assertions: idempotent DB effect"]
    C3 --> A
    C2 --> PARK["DLQ / quarantine"]
    C3 --> PARK
~~~

Để mỗi consumer độc lập nhận được cùng event trong test, dùng **hai queues được bind** đến exchange; không đặt hai consumer vào một queue rồi mong cả hai đều nhận từng message. Khi kiểm tra **rolling upgrade trên một competing-consumer queue thật**, lại cần một test riêng nơi cả pods cũ/mới có thể nhận bất kỳ delivery nào trong cửa sổ triển khai.

### 9.2. Các bước test đầu-cuối

1. Khởi động broker, tạo exchange/queues/bindings và parking/DLX riêng cho test.
2. Khởi động listener Jackson 2 và Jackson 3 với converter đã cấu hình rõ ràng.
3. Publish các golden event bằng cả producer Jackson 2 lẫn Jackson 3, giữ `eventId` và `schemaVersion`.
4. Chờ **business state** được commit ở consumer, không chỉ chờ `RabbitTemplate.convertAndSend(...)` trở về.
5. Xác nhận cả hai listener giải mã đúng payload, type alias, Unicode/date/time; so sánh kết quả.
6. Test một event malformed JSON và một type header không được trust; theo dõi xử lý lỗi và DLQ/parking.
7. Restart consumer khi có message chưa ACK; xác minh redelivery và idempotency.
8. Test publisher confirm + mandatory return khi exchange/binding sai, vì đổi converter có thể trùng thời điểm thay topology.

Ví dụ gửi message trong một test có topology và `RabbitTemplate` đã cấu hình:

~~~java
OrderCreated event =
        new OrderCreated("e-7", "order-42", 1);

rabbitTemplate.convertAndSend(
        "orders.events.x",
        "orders.created",
        event,
        message -> {
            message.getMessageProperties()
                    .setHeader("eventType", "order.created");
            message.getMessageProperties()
                    .setHeader("schemaVersion", 1);
            return message;
        });
~~~

Nếu `RabbitTemplate` chưa được gắn `JacksonJsonMessageConverter`, lời gọi trên **không** bảo đảm gửi được record JSON đúng contract. Nên assert `contentType` và `__TypeId__` qua test producer cùng consumer state, không dựa riêng vào conversion thành công ở local.

### 9.3. Vì sao test chỉ dùng broker cũ hoặc chỉ dùng converter mới là thiếu?

Trong deployment thực, thường còn:

- Message cũ đã publish và chờ trong queue.
- Message ở retry queue với TTL dài, vài giờ/ngày sau mới quay lại main queue.
- Message bị đẩy tới DLQ và được replay thủ công sau khi code đã đổi.
- Producer phiên bản cũ hoặc một bên đối tác chưa nâng Jackson.
- Event trong outbox có payload lưu trước khi nâng và được relay phát sau khi nâng.

Nếu bộ test chỉ gửi event **mới** từ producer mới vào consumer mới, các nguồn trên sẽ trở thành **lỗi production bị bỏ sót**.

### 9.4. Phân biệt conversion failure với lỗi nghiệp vụ

Với `@RabbitListener`, message có thể lỗi **trước khi method chạy**: JSON malformed, type không được trust hoặc converter không hiểu schema. Khi đó transaction nghiệp vụ chưa bắt đầu, nhưng listener container vẫn phải quyết định reject/requeue/recover.

Spring AMQP thường dùng `ConditionalRejectingErrorHandler` để nhận diện một số exception **fatal** như lỗi conversion và tránh requeue vô hạn trong cấu hình mặc định, nhưng hành vi thực tế còn phụ thuộc version, `defaultRequeueRejected`, recoverer, retry advice, manual ACK và topology. **Không coi mọi `MessageConversionException` mặc nhiên được chuyển vào đúng DLQ.**

Test cần kiểm chứng:

- Lỗi schema vĩnh viễn không tạo **hot requeue loop**.
- Thông điệp lỗi được cách ly bền vững khi policy yêu cầu.
- DLX, routing key và parking queue tồn tại; không để message biến mất vì DLX không route.
- Payload lỗi đủ metadata để sửa và replay có kiểm soát, nhưng log không in credential/PII.
- Không ACK thành công một payload chưa áp dụng được nghiệp vụ chỉ vì handler bắt exception rồi return.

## 10. Kế hoạch rolling migration cho nhiều producer/consumer

Khi triển khai nhiều pod, có thể đồng thời tồn tại:

~~~text
Producer Jackson 2  ─┐
                     ├── RabbitMQ queue ───┬── Consumer Jackson 2
Producer Jackson 3  ─┘                    └── Consumer Jackson 3
~~~

Trên một queue với competing consumers, **không có bảo đảm message cũ chỉ đến consumer cũ**, hoặc message mới chỉ đến consumer mới. Vì vậy cần một **khoảng giao nhau về khả năng đọc**, không được nâng tất cả bằng cách hy vọng tỷ lệ pod routing đúng.

### 10.1. Thứ tự triển khai giảm rủi ro

**Giai đoạn 0 — Kiểm kê và đóng băng wire contract.** Chốt event names, DTO schema, `contentType`, type aliases, date/enum policies; lưu golden fixtures từ traffic cũ; ghi lại retry/DLQ đang có.

**Giai đoạn 1 — Consumer mới đọc được message cũ.** Deploy canary consumer Jackson 3 có khả năng đọc **cả JSON và type metadata legacy**. Producer vẫn phát payload cũ. Kiểm tra conversion error, duplicate rate và DLQ.

**Giai đoạn 2 — Mọi consumer cần tương thích đã sẵn sàng.** Nâng dần consumer còn lại; giữ producer cũ. Nếu cả phiên bản consumer cùng nằm trên một queue, canary phải xử lý được mọi message đang còn; không dùng routing giả định.

**Giai đoạn 3 — Bật producer Jackson 3 với wire format tương thích.** Có thể giữ chính schema/alias cũ trước, chỉ đổi thư viện; đối chiếu p95/p99, bytes/headers và lỗi parse. Nếu cần phát `schemaVersion=2` không tương thích, tách **hai thay đổi**: thư viện migration trước, schema evolution sau.

**Giai đoạn 4 — Dọn dependency/bridge cũ.** Chỉ gỡ Jackson 2 converter/mapping tạm khi không còn producer cũ, message tồn đọng, retry/DLQ hoặc archive cần đọc theo contract cũ. Với DLQ lâu dài, có thể phải giữ một **offline repair tool** hiểu schema cũ mà không giữ Jackson 2 trong ứng dụng chính.

~~~mermaid
flowchart LR
    BASE["Chốt contract & golden tests"] --> C3["Nâng consumer đọc legacy + new"]
    C3 --> COK{"Conversion/DLQ/DB đúng?"}
    COK -->|Không| STOP["Dừng rollout; rollback consumer"]
    COK -->|Có| ALL["Nâng tất cả consumers"]
    ALL --> P3["Nâng producers; giữ wire tương thích"]
    P3 --> POK{"Chỉ số ổn định?"}
    POK -->|Không| REST["Quay về producer cũ"]
    POK -->|Có| CLEAN["Dọn bridge; schema change sau"]
~~~

**Quy tắc:** kiểm soát **producer compatibility** và **consumer compatibility** là hai phép thử khác nhau. Nếu consumer cũ không hiểu header/field mới, không bật producer mới trong khi consumer cũ còn cạnh tranh cùng queue.

### 10.2. Nếu producer mới cần gửi schema v2

Không nên gắn việc đổi converter với việc đổi schema trong cùng một release không thể đảo ngược. Ưu tiên một trong các chiến lược:

- **Expand/contract:** consumer chấp nhận cả v1 và v2 trước, sau đó producer mới gửi v2; chỉ loại v1 sau khi dữ liệu cũ không còn.
- **Versioned event:** dùng `eventType` và `schemaVersion` rõ ràng, upcaster hoặc mapper theo version. Không phụ thuộc FQN trong `__TypeId__`.
- **Route song song có kiểm soát:** queue/binding hoặc routing key v1/v2 riêng khi cần cách ly consumer không tương thích, nhưng phải giải quyết dual publication và idempotency.
- **Tách adapter:** một service chuyển đổi message legacy thành format mới với log/metrics, có kế hoạch rollback và bounded retry.

Một DTO v2 thêm trường có default an toàn không tự bảo đảm backward compatibility: consumer v1 có thể bật `FAIL_ON_UNKNOWN_PROPERTIES` hoặc dùng enum unknown, mapper tùy chỉnh và signature khác. Cần chạy test trên **binary thật của consumer v1**.

### 10.3. Rollback không có nghĩa restore message đã lỗi

Nếu producer mới phát message không tương thích, rollback image **không làm các message đó tự biến mất** khỏi queue, DLQ hoặc outbox. Một producer cũ có thể còn phát lại event theo schema cũ khi relay restart. Runbook rollback phải xác định:

1. Những event ID nào đã được phát với schema mới?
2. Event nào đang ready, unacked, trong retry và DLQ?
3. Consumer cũ có đọc được tất cả message đang chờ sau rollback?
4. Có cần pause consumer, quarantine hoặc đưa adapter tạm thời vào xử lý?
5. Có idempotency protection khi cùng event được replay lần nữa không?

Nếu không thể đảm bảo an toàn khi rollback, chuyển sang **roll-forward có kiểm soát** hoặc repair bằng bản đọc được cả hai format. Không purge queue để “làm sạch” lỗi migration.

## 11. Bảng chẩn đoán lỗi thường gặp

| Dấu hiệu sau migration | Khả năng nguyên nhân | Cách xác minh | Hướng xử lý |
|---|---|---|---|
| `ClassNotFoundException` với `com.old...OrderCreated` | `__TypeId__` đang chứa Java FQN cũ | Kiểm tra type header trên message lỗi | Map alias/FQN legacy → DTO mới bằng danh sách cho phép |
| `MessageConversionException` khi consumer mới đọc message cũ | Content type, type mapping, custom serializer hoặc JSON shape khác | Replay golden fixture qua converter mới | Giữ contract, bật reader tương thích trước producer |
| `ClassCastException` `byte[]` → DTO | Converter không được gắn vào listener hoặc content type không được hỗ trợ | Kiểm tra listener factory/`@RabbitListener` và raw properties | Cấu hình đúng `MessageConverter`, contentType |
| `NoSuchMethodError` / `NoClassDefFoundError` ở Jackson | Mix Jackson 2/3 APIs hoặc BOM lệch | Dependency tree, classloader, resolved artifact | Đồng bộ Boot/AMQP/Jackson; không ép version transitive |
| DTO parse được nhưng `Instant` hoặc `BigDecimal` thay đổi | Mapper feature/module/format không đồng nhất | So golden semantic và JSON bytes | Cấu hình `JsonMapper` tương thích, schema rõ ràng |
| Unknown enum làm listener fail | Producer phát giá trị mới mà consumer chưa hỗ trợ | Test binary consumer cũ với payload mới | Expand/contract hoặc versioning |
| `@RabbitHandler` không được chọn | Class-level handler dựa vào type sau conversion | Xem headers/type mapping và method signatures | Kiểm thử polymorphism, mapping và factory |
| Header `__TypeId__` không được trust | Trusted packages/alias mapping thiếu | Log exception, kiểm tra whitelist | Thêm đúng DTO/package; **không** mở `"*"` |
| Nhiều message vào DLQ sau deploy | Consumer không đọc được payload cũ hoặc error handler reject | Đối chiếu thời điểm deploy với conversion failures | Dừng rollout, sửa mapper, replay DLQ có kiểm soát |
| Retry loop nóng, CPU/broker tăng | Parse lỗi vĩnh viễn nhưng requeue=true | `redelivered`, listener errors và queue rates | Phân loại fatal, giới hạn retry, DLX/parking |
| Payload kiểu `Map` thay vì DTO | Không suy luận được target type hoặc thiếu type header | Test `converter.fromMessage` và listener typed | Cấu hình class mapper hoặc explicit type contract |
| `@JsonProperty` bị báo import không tồn tại | Đổi sai annotations sang `tools.jackson.annotation` | Compile/Javadoc dependencies | Giữ `com.fasterxml.jackson.annotation` theo migration guide |
| Boot4 property đã bật nhưng AMQP JSON không đổi | Converter tạo `JsonMapper` nội bộ khác Boot | So identity/config của mapper được inject | Inject `JsonMapper` auto-configured vào converter |
| Jackson 2 converter warning deprecated | Code còn dùng API quá độ trên Spring AMQP 4.x | Compiler deprecation report và search | Chuyển sang `JacksonJsonMessageConverter`, lên lịch gỡ bridge |
| Message đã gửi nhưng DB không được cập nhật | Listener parse lỗi trước method hoặc business exception | Trace eventId → publish → conversion → DB → ACK | Không đồng nhất publisher confirm với consumer success |

### 11.1. Một số lỗi xuất hiện ở nơi không ngờ

**Producer vẫn chạy nhưng consumer lỗi:** producer có thể tạo JSON bình thường, broker xác nhận publish ACK, exchange vẫn route vào queue. `MessageConversionException` xảy ra *sau đó*, tại listener. Vì thế dashboard chỉ theo dõi publisher confirms sẽ không phát hiện migration thất bại.

**Message cũ quay lại sau vài ngày:** một retry queue TTL hoặc parking queue có thể giữ event do Jackson 2 tạo. Thay đổi class/package làm event cũ lỗi khi được redrive dù traffic mới đã ổn. Luôn test **redrive và backlog cũ**.

**Một service dùng nhiều converter:** producer của HTTP API có thể dùng Jackson 3 `JsonMapper`, nhưng RabbitMQ listener vẫn sử dụng `SimpleMessageConverter` hoặc `Jackson2JsonMessageConverter` do factory riêng cấu hình. Kiểm tra **đúng bean đang được dùng ở runtime**, không chỉ code import.

**Lỗi không mất dữ liệu ngay nhưng gây nghẽn:** nếu hàng đợi requeue vô hạn, consumer xử lý cùng message lỗi hàng nghìn lần, chiếm CPU, làm tăng channel churn và khiến message hợp lệ phải chờ. Recovery policy cần dựa trên loại lỗi.

## 12. Bảo toàn độ tin cậy khi chuyển converter

Mặc dù bài tập trung vào JSON, mục tiêu cuối vẫn là message được **route, xử lý, ACK/retry và ghi DB** một cách đáng tin cậy.

### 12.1. Publisher confirm không chứng minh deserialize thành công

~~~mermaid
sequenceDiagram
    participant P as RabbitTemplate + JSON converter
    participant B as RabbitMQ
    participant C as @RabbitListener + JSON converter
    participant DB as Database
    P->>B: Publish JSON + headers
    B-->>P: Publisher confirm ACK
    B->>C: Delivery
    alt JSON / type metadata hợp lệ
        C->>DB: COMMIT nghiệp vụ (idempotent)
        C-->>B: Consumer ACK
    else Không parse được
        C-->>B: Reject / retry / DLQ theo policy
    end
~~~

Một producer không nhận publisher confirm có thể retry và publish duplicate. Một consumer đã commit DB nhưng kết nối mất trước khi ACK có thể được redeliver. **Đổi Jackson 2 → 3 không thay các failure window này**.

Nên giữ:

- `eventId`/`commandId` ổn định qua retry và qua hai phiên bản producer.
- Transactional outbox nếu event xuất phát từ DB transaction và không được mất ý định gửi.
- Consumer inbox/unique constraint hoặc idempotency mechanism tương đương.
- Giới hạn retry, backoff và parking queue cho lỗi vĩnh viễn.
- Publisher confirms và mandatory returns để phân biệt broker nhận publish với message thực sự được route.
- Monitoring end-to-end từ producer đến business commit/ACK.

### 12.2. Không tự động replay DLQ vô hạn khi sửa converter

Sau khi sửa class mapper, có thể redrive message cũ từ DLQ; tuy nhiên một event từng đi DLQ vì validation nghiệp vụ không nên được gửi lại vô điều kiện.

Quy trình redrive có kiểm soát:

1. Phân loại lỗi do **converter** hay **business validation**.
2. Xác minh code consumer mới có thể parse payload lỗi bằng golden test.
3. Giữ `eventId`, `schemaVersion`, original payload và correlation metadata.
4. Chọn một batch nhỏ, redrive qua đường routing được phép.
5. Theo dõi committed effects, duplicate detection và DLQ mới.
6. Tăng tốc dần, tránh gây bão retry hoặc làm vượt capacity downstream.

Nếu một message được redrive sau nhiều tuần, schema/DTO mới phải hiểu format cũ hoặc có **upcaster/version adapter**; không dựa vào việc class cũ còn tình cờ nằm trên classpath.

## 13. Quan sát, phát hiện lỗi sớm và tiêu chí dừng rollout

| Nhóm chỉ số | Cần theo dõi | Vì sao |
|---|---|---|
| **Converter** | `MessageConversionException` theo queue/eventType/schemaVersion; unsupported contentType; forbidden type headers | Phát hiện sai JSON/type mapper ngay khi canary |
| **Publisher** | Confirm ACK/NACK/timeout, mandatory returns, outbox pending | Phân biệt JSON encode lỗi và lỗi broker/routing |
| **Consumer** | Delivery/ACK/NACK, redelivery, unacked count, listener invocation | Phát hiện consumer không bắt đầu được nghiệp vụ |
| **Retry/DLQ** | Retry attempts, parking queue depth và tuổi message | Phát hiện poison record sau deploy |
| **Business** | Số event IDs đã commit, dedup hits, số invoice/order updates | Bảo đảm dữ liệu không mất/ghi trùng |
| **Runtime** | Classloading errors, Jackson2/Jackson3 warnings, heap/GC, CPU | Phát hiện lệch dependency hoặc mapper bất thường |
| **Deployment** | Version mỗi pod, canary share, % consumers đã nâng | Biết chính xác khoảng chạy mixed-version |

**Không nên in toàn bộ payload** khi gặp lỗi JSON, đặc biệt nếu chứa thông tin cá nhân/thanh toán. Log `eventId`, `schemaVersion`, queue, type ID (đã sanitize), exception class và deployment version là đủ để điều tra nhiều tình huống.

### 13.1. Các ngưỡng dừng gợi ý

Giá trị cụ thể phải theo SLO, nhưng rollout nên **dừng ngay** khi:

- Xuất hiện lỗi JSON/type mapping tăng đột ngột so với baseline.
- DLQ/parking queue tăng theo canary traffic mà không có nguyên nhân nghiệp vụ hợp lệ.
- Số event IDs commit thấp hơn số delivery thành công trong thời gian đối chiếu thích hợp.
- Có khác biệt về số tiền, timezone, enum hoặc trường quan trọng giữa consumer cũ và mới.
- Có bằng chứng consumer ACK trước khi hoàn tất business effect.
- Publisher mới phát schema mà consumer cũ còn chạy trên competing queue không thể đọc.

Một bản nâng cấp “không crash pod” vẫn có thể **thất bại về dữ liệu**. Dùng business assertions và log/metrics đối chiếu là điều kiện mở rộng rollout, không chỉ health check HTTP.

## 14. Bài thực hành tổng hợp

**Bài toán:** dịch vụ order đang dùng Spring AMQP 3.x và Jackson 2. Ta muốn lên Spring Boot 4 / Spring AMQP 4 với Jackson 3 nhưng trong nhiều giờ sẽ tồn tại consumer mới và producer cũ. Queue `orders.created.q` có backlog, retry queue giữ dữ liệu tối đa 24 giờ.

### Bước 1: Lưu hợp đồng cũ

Từ producer đang chạy, thu thập message thử nghiệm **không chứa dữ liệu thật nhạy cảm**:

~~~text
contentType: application/json
__TypeId__: com.legacy.order.events.OrderCreated
eventId: e-100
schemaVersion: 1
body: {"eventId":"e-100","orderId":"o-10","schemaVersion":1}
~~~

Lưu các mẫu có ngày giờ, BigDecimal, null, enum và Unicode. Xác nhận custom serializer/modules của ứng dụng thực tế trước khi định nghĩa output đích.

### Bước 2: Viết consumer Jackson 3 đọc legacy

Chọn cách xử lý header legacy:

- Trong một listener nhận **DTO concrete**, nếu phù hợp, type inferred có thể giải quyết dù `__TypeId__` khác tên class; **vẫn phải test**.
- Với class mapper, thêm một **mapping tường minh** từ token legacy được phép đến DTO mới. Ví dụ:

~~~java
DefaultClassMapper mapper = new DefaultClassMapper();
mapper.setTrustedPackages("com.example.messaging.dto");
mapper.setIdClassMapping(java.util.Map.of(
        "com.legacy.order.events.OrderCreated",
        OrderCreated.class,
        "order.created.v1",
        OrderCreated.class));
mapper.afterPropertiesSet();

JacksonJsonMessageConverter converter =
        new JacksonJsonMessageConverter("com.example.messaging.dto");
converter.setClassMapper(mapper);
~~~

Vì hai IDs cùng map tới một class, **đừng dựa vào reverse mapping để đoán converter sẽ phát ra alias nào** nếu không kiểm thử. Khi cần publisher luôn phát một alias duy nhất, dùng mapping/serializer được xây riêng cho đường producer và xác nhận `__TypeId__` trên message thực tế.

### Bước 3: Test backward/forward compatibility

| Hướng | Test | Kết quả mong đợi |
|---|---|---|
| Old producer → new consumer | JSON + legacy FQN header | Consumer mới parse và xử lý đúng |
| New producer → old consumer | Alias hoặc header/JSON được định nghĩa | Chỉ bật nếu consumer cũ thật sự đọc được |
| Old retry/DLQ → new consumer | Payload đã giữ 24 giờ | Có thể redrive và dedup |
| New consumer → DB | Event hợp lệ/duplicate | Một tác dụng nghiệp vụ cho mỗi eventId |
| Malformed JSON → handler | JSON thiếu cấu trúc | Lỗi được phân loại; không retry vô hạn |
| Forbidden type → handler | `__TypeId__` không được trust | Reject/quarantine an toàn |

### Bước 4: Triển khai canary

Giữ producer cũ; triển khai một consumer mới trong môi trường có kiểm soát, theo dõi mapping failures và DLQ. Sau khi xác nhận mọi consumer mới đọc được backlog/legacy, triển khai tiếp cho toàn bộ consumer. **Chỉ sau đó** mới đổi producer sang Jackson 3 với schema tương thích.

### Bước 5: Tháo bridge

Chỉ sau khi producer cũ không còn, retry/DLQ/backup đã được giải quyết và không còn FQN legacy cần đọc trong live path, mới gỡ mapper/dependency tương thích. Đặt ngày đánh giá và người chịu trách nhiệm trong ADR/upgrade record.

## 15. Những hiểu lầm phải tránh

| Nhận định sai | Điều đúng |
|---|---|
| “Chỉ đổi import Jackson2JsonMessageConverter thành JacksonJsonMessageConverter là xong” | Còn mapper type, runtime dependencies, JSON defaults, consumer wiring và wire compatibility |
| “Spring AMQP 4.0 đã xóa toàn bộ Jackson 2 API” | Từ 4.0 chúng được **deprecated for removal**; kiểm tra bản vá/nhánh mục tiêu để biết còn tồn tại không |
| “Jackson 3 dùng mọi class trong com.fasterxml.jackson như cũ” | Nhiều nhóm chuyển sang `tools.jackson`; annotations là ngoại lệ quan trọng |
| “Boot 4 JsonMapper tự cấu hình mọi converter tạo thủ công” | Mapper mới tạo riêng có thể có settings khác; nên inject mapper đúng |
| “`spring.jackson.use-jackson2-defaults` bảo đảm JSON giống tuyệt đối” | Chỉ hỗ trợ tương thích mặc định của mapper Boot; custom code/modules vẫn phải test |
| “Message là JSON thì mọi consumer đọc được” | Content type, charset, schema, type header và custom converter đều quan trọng |
| “`__TypeId__` nên chứa FQN để dễ debug” | FQN làm coupling với Java package; alias/schema version ổn định hơn |
| “Có `@RabbitListener(OrderCreated)` thì header type không cần quan tâm” | Inferred type có điều kiện; direct converter, interface và class-level handlers khác |
| “Trust all `*` để sửa lỗi type” | Mở rộng bề mặt deserialization; mapping allowlist an toàn hơn |
| “Thấy confirm ACK là Jackson 3 migration thành công” | Broker ACK publish không chứng minh consumer deserialize/commit |
| “Canary 1 pod với 1 queue chỉ đọc message của canary producer” | Competing consumers nhận phân phối từ queue chung, không có ràng buộc version |
| “Rollback image là khôi phục toàn bộ message” | Message mới đã ở queue/outbox/DLQ; cần rollback contract và repair plan |
| “Giữ Jackson 2 vô thời hạn trên Boot 4 là chiến lược chuẩn” | Bridge deprecated chỉ dùng tạm để migration |

## 16. Checklist trước khi đóng đợt nâng cấp

1. **Dòng version:** Spring Boot, Spring AMQP, Framework và Java tương thích theo BOM/release notes.
2. **Resolved dependencies:** xác định classpath thực tế chứa Jackson 2/3, phiên bản modules và không có conflict.
3. **Producer converter:** `RabbitTemplate` đang dùng `JacksonJsonMessageConverter` với `JsonMapper` đúng cấu hình.
4. **Consumer converter:** `@RabbitListener` factory/override bean phù hợp; không còn `SimpleMessageConverter` ngoài ý muốn.
5. **Type mapping:** `__TypeId__`/collection headers được map bằng alias/trusted packages; FQN legacy có kế hoạch hỗ trợ/gỡ.
6. **Wire contract:** UTF-8, contentType, schemaVersion, eventId, null/enum/date/decimal, field naming đã qua golden test.
7. **Custom Jackson modules:** mọi serializer/deserializer/mix-in cần thiết đã chuyển và được nạp đúng.
8. **Mixed-version tests:** old → new và new → old pass khi rollout yêu cầu; old backlog/DLQ cũng được kiểm tra.
9. **Integration test:** broker thật xác minh exchange/queue/binding, listener conversion, business commit và ACK.
10. **Failure handling:** malformed/untrusted messages không hot-requeue, DLQ có đường phục hồi an toàn.
11. **Idempotency:** duplicate sau timeout/redelivery không ghi DB hoặc gọi API nghiệp vụ lặp.
12. **Observability:** conversion failure rate, type header, schemaVersion, publisher results, retry/DLQ và business outcomes có dashboard/alerts.
13. **Rollout:** consumer-first, canary metrics, feature flag và rollback/roll-forward playbook có owner.
14. **Cleanup:** bỏ compatibility module Jackson 2 và mapper bridge sau khi không còn dữ liệu legacy; tránh nợ deprecated kéo dài.

### Tài liệu chính thức để đối chiếu với đúng phiên bản

- [Spring AMQP 3.2 — Message Converters](https://docs.spring.io/spring-amqp/reference/3.2/amqp/message-converters.html): converter Jackson 2, type inference và headers.
- [Spring AMQP 4.0 — Message Converters](https://docs.spring.io/spring-amqp/reference/4.0/amqp/message-converters.html): converter Jackson 3 và deprecation của API Jackson 2.
- [Spring AMQP — JacksonJsonMessageConverter Javadoc](https://docs.spring.io/spring-amqp/docs/current/api/org/springframework/amqp/support/converter/JacksonJsonMessageConverter.html): constructor với `JsonMapper`, trusted packages.
- [Spring AMQP — DefaultJacksonJavaTypeMapper Javadoc](https://docs.spring.io/spring-amqp/docs/current/api/org/springframework/amqp/support/converter/DefaultJacksonJavaTypeMapper.html): type ID mapping, type precedence và trusted packages.
- [Spring AMQP — DefaultClassMapper Javadoc](https://docs.spring.io/spring-amqp/docs/current/api/org/springframework/amqp/support/converter/DefaultClassMapper.html): alias → class, default type, afterPropertiesSet.
- [Spring Boot 4.0 Migration Guide — Jackson](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide#upgrading-jackson): `tools.jackson`, compatibility properties, `spring-boot-jackson2` bridge.
- [Spring Boot — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): auto-configured `JsonMapper`, modules và Jackson 2 compatibility.
- [Jackson 3 Support in Spring](https://spring.io/blog/2025/10/07/introducing-jackson-3-support-in-spring/): nguyên tắc đồng tồn tại Jackson 2/3 và định hướng migration.

**Kết luận:** Di chuyển converter Jackson 2 → Jackson 3 không phải bài toán thay một tên class. Hãy xác định đúng **dòng Spring AMQP 3.x/4.x và Spring Boot 3.x/4.x**, thay `Jackson2JsonMessageConverter` bằng `JacksonJsonMessageConverter` với `JsonMapper` Jackson 3 đúng cấu hình, duy trì **JSON bytes + contentType + type alias/schemaVersion** như một hợp đồng ổn định, và kiểm chứng **cả hai chiều** khi producer/consumer chạy mixed versions. Triển khai consumer tương thích trước producer, xem xét backlog/retry/DLQ, bảo vệ trusted packages và idempotency, rồi tháo bridge Jackson 2 sau khi đã có bằng chứng dữ liệu legacy được xử lý an toàn.
