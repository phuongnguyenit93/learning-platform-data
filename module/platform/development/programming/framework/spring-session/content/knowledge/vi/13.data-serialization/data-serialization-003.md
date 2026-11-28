# RedisSerializer và bean springSessionDefaultRedisSerializer

## Mục tiêu bài học

Spring Session Redis lưu thuộc tính của session vào Redis. Vì thuộc tính có thể là nhiều kiểu object Java khác nhau, ứng dụng cần một cơ chế chuyển object thành byte để lưu và khôi phục object khi request tiếp theo tải session. Cơ chế đó được cung cấp bởi Redis serializer.

Trong cấu hình Spring Session Redis, bean có tên chính xác `springSessionDefaultRedisSerializer` cho phép ứng dụng tùy chỉnh cách serialize các giá trị thuộc tính session. Đây là một điểm cấu hình quan trọng khi muốn dùng JSON, hỗ trợ DTO riêng hoặc kiểm soát định dạng dữ liệu giữa nhiều instance.

Sau bài học, bạn có thể:

- Giải thích vì sao dữ liệu session cần serialize trước khi lưu vào Redis.
- Phân biệt serializer của Spring Session với serializer của RedisTemplate.
- Hiểu vai trò của bean `springSessionDefaultRedisSerializer`.
- Cấu hình bean `RedisSerializer<Object>` với JSON serializer.
- Nhận biết yêu cầu về kiểu dữ liệu, type metadata và khả năng deserialize.
- Lập kế hoạch thay đổi serializer mà không làm các phiên đang hoạt động bị lỗi ngoài dự kiến.
- Kiểm thử round-trip serialization và session thực tế qua nhiều request hoặc nhiều instance.

## 1. Vì sao Spring Session cần serializer?

Redis lưu dữ liệu theo key và value. Giá trị lưu trữ cuối cùng là byte hoặc chuỗi theo giao thức Redis. Trong khi đó, thuộc tính session trong Java có thể là String, số, collection hoặc object do ứng dụng định nghĩa.

Ví dụ một session có thể chứa:

~~~java
session.setAttribute("locale", "vi");
session.setAttribute("cartCount", 3);
session.setAttribute("cart", new CartSnapshot(items));
~~~

Các giá trị trên có kiểu Java khác nhau. Để ghi chúng vào Redis, Spring Session phải chuyển đổi từng giá trị sang dạng có thể lưu trữ. Khi request sau tải session, repository cần chuyển dữ liệu đã lưu trở lại object mà ứng dụng có thể đọc.

Quá trình này gồm hai chiều:

~~~text
Java object
    |
    | serialize
    v
Bytes / Redis value
    |
    | deserialize
    v
Java object
~~~

Serializer quyết định định dạng byte được ghi và cách khôi phục object. Nếu hai instance dùng serializer hoặc cấu hình kiểu dữ liệu không tương thích, instance ghi session có thể thành công nhưng instance khác không đọc được thuộc tính đó.

### Serialization không phải mã hóa

Serialize chuyển đổi biểu diễn dữ liệu. Nó không mặc nhiên mã hóa bí mật.

- JSON có thể đọc được nếu truy cập được Redis.
- Java serialization tạo byte nhị phân nhưng không bảo đảm dữ liệu bí mật.
- Một serializer nén dữ liệu cũng không bảo đảm confidentiality.

Nếu dữ liệu session nhạy cảm, hãy bảo vệ Redis bằng network isolation, authentication, ACL, TLS, quyền truy cập tối thiểu và chính sách backup phù hợp. Nếu cần mã hóa ở tầng ứng dụng, hãy thiết kế riêng cơ chế encryption và quản lý khóa.

## 2. RedisSerializer là gì?

`RedisSerializer<T>` là abstraction của Spring Data Redis để chuyển object kiểu `T` thành byte array và khôi phục byte array thành object.

Các thao tác cơ bản:

| Phương thức | Vai trò |
|---|---|
| `serialize(value)` | Chuyển object thành byte array để lưu |
| `deserialize(bytes)` | Khôi phục object từ byte array |

Ví dụ một serializer có kiểu `RedisSerializer<Object>` có thể nhận nhiều loại giá trị thuộc tính session. Spring Session cần serializer tổng quát vì các thuộc tính khác nhau có thể có kiểu Java khác nhau.

Không nên nhầm `RedisSerializer` với `RedisTemplate`:

- `RedisSerializer` là thành phần chuyển đổi một giá trị.
- `RedisTemplate` là API thao tác Redis và có thể dùng serializer riêng cho key, value, hash key hoặc hash value.
- Spring Session Redis repository quản lý cấu trúc session và sử dụng serializer mà nó được cấu hình để dùng.

Thay serializer của một `RedisTemplate` không tự động thay serializer của Spring Session. Hai thành phần có thể dùng cấu hình riêng.

## 3. Bean springSessionDefaultRedisSerializer có vai trò gì?

Spring Session Redis cho phép ứng dụng cung cấp một bean có tên:

`springSessionDefaultRedisSerializer`

Bean này có kiểu trả về thường dùng là:

`RedisSerializer<Object>`

Spring Session Redis repository tìm bean theo tên quy ước để dùng serialize các giá trị thuộc tính session. Tên bean là một phần của hợp đồng cấu hình; chỉ khai báo một bean RedisSerializer với tên bất kỳ có thể không khiến Spring Session sử dụng nó.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;

@Configuration
public class SessionRedisSerializationConfiguration {

    @Bean(name = "springSessionDefaultRedisSerializer")
    public RedisSerializer<Object> springSessionDefaultRedisSerializer() {
        return new GenericJackson2JsonRedisSerializer();
    }
}
~~~

Trong ứng dụng Spring Boot có Spring Session Redis, bean này cho repository biết cách serialize thuộc tính session. Khi dùng cấu hình thủ công, cần bảo đảm repository Spring Session Redis được đăng ký trong application context và nhìn thấy bean đó.

### Vì sao tên bean phải chính xác?

Spring Session sử dụng tên bean quy ước để nhận serializer mặc định cho thuộc tính session. Ví dụ, nếu khai báo:

~~~java
@Bean
public RedisSerializer<Object> mySessionSerializer() {
    return new GenericJackson2JsonRedisSerializer();
}
~~~

thì bean có tên mặc định là `mySessionSerializer`. Tên này không trùng với `springSessionDefaultRedisSerializer`. Nếu repository đang tìm bean theo tên quy ước, serializer trên có thể không được sử dụng.

Nên khai báo rõ tên:

~~~java
@Bean(name = "springSessionDefaultRedisSerializer")
public RedisSerializer<Object> springSessionDefaultRedisSerializer() {
    return new GenericJackson2JsonRedisSerializer();
}
~~~

Chỉ nên có một bean serializer mang tên quy ước trong cùng application context. Nếu có nhiều cấu hình cùng khai báo tên này, ứng dụng có thể gặp xung đột bean hoặc hành vi override phụ thuộc cấu hình.

## 4. Chọn định dạng serialization

Có nhiều lựa chọn serializer. Việc chọn phụ thuộc khả năng tương thích, yêu cầu hiệu năng, mức độ dễ quan sát và chính sách bảo mật.

| Lựa chọn | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|
| JDK serialization | Hỗ trợ object Java triển khai Serializable; ít cấu hình | Phụ thuộc class Java và phiên bản; dữ liệu khó quan sát; cần thận trọng khi deserialize dữ liệu không tin cậy |
| JSON serializer | Dễ quan sát, hỗ trợ nhiều client và ngôn ngữ | Cần xử lý kiểu cụ thể, type metadata và thay đổi schema |
| Serializer nhị phân khác | Có thể tối ưu kích thước hoặc tốc độ | Cần quản lý schema, version và tương thích giữa instance |
| Serializer tùy chỉnh | Kiểm soát chính xác định dạng | Tăng mã bảo trì và trách nhiệm tương thích |

Không có định dạng nào phù hợp cho mọi ứng dụng. Với session, thường nên ưu tiên DTO nhỏ, ổn định và dễ serialize. Tránh lưu object phụ thuộc vào vòng đời của một request hoặc persistence context.

### JDK serialization

JDK serializer thường được dùng làm mặc định trong một số cấu hình Spring Data Redis/Spring Session. Object cần đáp ứng yêu cầu serializable của serializer.

Ví dụ:

~~~java
import java.io.Serializable;
import java.util.List;

public class CartSnapshot implements Serializable {

    private static final long serialVersionUID = 1L;

    private List<CartItem> items;

    public CartSnapshot() {
    }

    public CartSnapshot(List<CartItem> items) {
        this.items = items;
    }

    public List<CartItem> getItems() {
        return items;
    }

    public void setItems(List<CartItem> items) {
        this.items = items;
    }
}
~~~

Nếu lưu object không đáp ứng yêu cầu của JDK serialization, thao tác lưu có thể lỗi khi repository serialize thuộc tính. Việc thêm `implements Serializable` chỉ giải quyết một phần; mọi object được tham chiếu trong object graph cũng phải tương thích.

Khi thay đổi class đã lưu, cần quan tâm `serialVersionUID` và khả năng tương thích với dữ liệu cũ. Nếu class không tương thích, session cũ có thể không deserialize được.

### JSON serialization

JSON thường thuận tiện khi muốn định dạng dễ quan sát hoặc cần chia sẻ cấu trúc dữ liệu với hệ thống khác. Với session chứa nhiều kiểu object khác nhau, serializer phải biết cách khôi phục kiểu cụ thể.

`GenericJackson2JsonRedisSerializer` là lựa chọn phổ biến trong Spring Data Redis để serialize object tổng quát thành JSON, thường kèm type metadata để khôi phục kiểu.

Ví dụ cấu hình cơ bản:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;

@Configuration
public class SessionRedisSerializationConfiguration {

    @Bean(name = "springSessionDefaultRedisSerializer")
    public RedisSerializer<Object> springSessionDefaultRedisSerializer() {
        return new GenericJackson2JsonRedisSerializer();
    }
}
~~~

Ví dụ này đơn giản và phù hợp để minh họa cách đăng ký bean. Với ứng dụng production, cần xem xét cấu hình ObjectMapper, type metadata, các kiểu DTO được phép deserialize và yêu cầu bảo mật của hệ thống.

## 5. Type metadata và polymorphic deserialization

Khi serializer nhận một giá trị có kiểu cụ thể nhưng nơi đọc chỉ biết kiểu tổng quát `Object`, nó cần thông tin để khôi phục lớp thực tế.

Ví dụ, session có thể chứa:

~~~java
session.setAttribute("cart", new CartSnapshot(items));
session.setAttribute("preferences", new UserPreferences("vi", true));
~~~

Nếu dữ liệu JSON chỉ có field mà không có thông tin kiểu, serializer có thể deserialize thành `Map` hoặc cấu trúc generic thay vì `CartSnapshot` hay `UserPreferences`. Khi controller ép kiểu, ứng dụng có thể gặp `ClassCastException`.

Type metadata giúp serializer biết object được ghi thuộc kiểu nào. Tuy nhiên, cơ chế polymorphic deserialization cần được kiểm soát chặt chẽ.

### Allowlist kiểu dữ liệu

Khi dữ liệu Redis có thể bị sửa bởi một thành phần không đáng tin cậy, deserialize type metadata quá rộng có thể mở rộng bề mặt tấn công. Không nên cho phép mọi lớp trên classpath được khởi tạo chỉ vì dữ liệu JSON yêu cầu.

Các nguyên tắc:

- Chỉ cho phép các package hoặc lớp DTO thực sự cần cho session.
- Không lưu object tùy ý do client cung cấp trực tiếp vào session.
- Giới hạn quyền ghi Redis bằng ACL và network policy.
- Không dùng type metadata như một cách kiểm tra tính hợp lệ của dữ liệu.
- Kiểm thử deserialize với dữ liệu không hợp lệ và kiểu không được cho phép.

Nếu dùng ObjectMapper với polymorphic typing, hãy cấu hình validator theo allowlist phù hợp với các kiểu DTO ứng dụng và các kiểu collection cần thiết. API cấu hình Jackson có thể thay đổi theo phiên bản; hãy đối chiếu phiên bản Jackson được Spring Boot quản lý trước khi áp dụng cấu hình tùy chỉnh.

### Ví dụ cấu hình ObjectMapper có allowlist

Ví dụ sau minh họa ý tưởng giới hạn kiểu được phép. Package được cho phép cần thay bằng package DTO thực tế của ứng dụng; không sao chép nguyên xi nếu cấu trúc dự án khác.

~~~java
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.BasicPolymorphicTypeValidator;
import com.fasterxml.jackson.databind.jsontype.PolymorphicTypeValidator;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;

@Configuration
public class SessionRedisSerializationConfiguration {

    @Bean(name = "springSessionDefaultRedisSerializer")
    public RedisSerializer<Object> springSessionDefaultRedisSerializer() {
        PolymorphicTypeValidator validator =
                BasicPolymorphicTypeValidator.builder()
                        .allowIfSubType("com.example.session.dto.")
                        .allowIfSubType("java.util.")
                        .allowIfSubType("java.time.")
                        .build();

        ObjectMapper mapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .build();

        mapper.activateDefaultTyping(
                validator,
                ObjectMapper.DefaultTyping.NON_FINAL,
                JsonTypeInfo.As.PROPERTY
        );

        return new GenericJackson2JsonRedisSerializer(mapper);
    }
}
~~~

Đây là ví dụ định hướng, không phải allowlist dùng chung cho mọi dự án. Chỉ mở rộng package khi ứng dụng thực sự lưu kiểu đó trong session. Cấu hình type metadata phải được kiểm thử với collection, DTO lồng nhau, kiểu ngày giờ và phiên bản thư viện cụ thể.

Nếu ứng dụng chỉ lưu một số kiểu đã biết, một serializer chuyên biệt hoặc DTO envelope có discriminator rõ ràng có thể dễ kiểm soát hơn so với cho phép polymorphic typing rộng.

## 6. Những object nên và không nên lưu trong session

Serializer có thể xử lý nhiều kiểu object, nhưng điều đó không có nghĩa mọi object đều phù hợp để lưu trong session.

Nên lưu:

- String, số, boolean và các giá trị nhỏ.
- ID tham chiếu đến dữ liệu nghiệp vụ.
- DTO nhỏ, có schema ổn định.
- Collection nhỏ gồm các kiểu dữ liệu đã kiểm soát.
- Snapshot cần thiết cho quy trình nhiều bước.

Tránh lưu:

- `HttpServletRequest` hoặc `HttpServletResponse`.
- Connection, socket, stream, thread hoặc executor.
- Spring service, repository hoặc bean chứa dependency runtime.
- Entity JPA có lazy proxy hoặc quan hệ phức tạp.
- Object phụ thuộc persistence context.
- File, ảnh hoặc payload lớn.
- Object có cấu trúc thay đổi liên tục giữa các lần deploy.

Ví dụ, thay vì lưu toàn bộ entity `Order` với quan hệ đến customer, items, payment và shipment, hãy lưu `orderId` hoặc một DTO nhỏ chỉ chứa dữ liệu cần cho bước tiếp theo. Khi cần dữ liệu mới nhất, truy vấn lại kho nghiệp vụ.

Session thường được đọc và ghi ở nhiều request. Object lớn làm tăng chi phí serialize, network transfer, Redis memory và thời gian xử lý request.

## 7. Serializer của Spring Session khác RedisTemplate serializer

Một ứng dụng có thể dùng `RedisTemplate` cho cache hoặc dữ liệu nghiệp vụ, đồng thời dùng Spring Session Redis cho session. Hai cấu hình serializer không mặc nhiên giống nhau.

Ví dụ:

~~~java
@Bean
public RedisTemplate<String, Object> applicationRedisTemplate(
        RedisConnectionFactory connectionFactory) {

    RedisTemplate<String, Object> template = new RedisTemplate<>();
    template.setConnectionFactory(connectionFactory);
    return template;
}
~~~

Bean trên chỉ minh họa RedisTemplate của ứng dụng. Nó không thay thế bean `springSessionDefaultRedisSerializer`.

Nếu muốn cả cache và session dùng cùng một định dạng, có thể tái sử dụng serializer bean trong cấu hình của RedisTemplate nếu kiểu key/value và yêu cầu dữ liệu phù hợp. Nhưng không nên giả định việc thay đổi serializer ở RedisTemplate sẽ tự ảnh hưởng repository Spring Session.

Cũng cần phân biệt serializer của key với serializer của value. RedisTemplate có thể dùng serializer khác nhau cho key, value, hash key và hash value. Spring Session có cấu trúc Redis riêng; không tùy tiện dùng cùng serializer cho mọi thành phần.

## 8. Cấu hình trong ứng dụng Spring Boot

Một ứng dụng Servlet dùng Redis thường có dependency cho web, Spring Data Redis và Spring Session Redis. Ví dụ Gradle:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.session:spring-session-data-redis")
}
~~~

Spring Boot dependency management nên quản lý phiên bản các thư viện Spring tương thích. Không tự chọn phiên bản Jackson hoặc Spring Data Redis độc lập nếu BOM đã quản lý.

Ví dụ cấu hình kết nối:

~~~properties
spring.data.redis.host=localhost
spring.data.redis.port=6379
spring.session.timeout=30m
~~~

Sau đó đăng ký bean serializer theo tên quy ước:

~~~java
@Configuration
public class SessionSerializationConfig {

    @Bean(name = "springSessionDefaultRedisSerializer")
    public RedisSerializer<Object> springSessionDefaultRedisSerializer() {
        return new GenericJackson2JsonRedisSerializer();
    }
}
~~~

Nếu dự án dùng cấu hình thủ công như `EnableRedisHttpSession`, bean serializer vẫn cần có mặt trong application context mà repository sử dụng. Tránh đăng ký nhiều repository hoặc nhiều cấu hình session chồng lấn.

### Bean serializer không thay RedisConnectionFactory

`springSessionDefaultRedisSerializer` chỉ định cách chuyển đổi thuộc tính session. Ứng dụng vẫn cần kết nối Redis thông qua `RedisConnectionFactory`, được cung cấp bởi Spring Boot auto-configuration hoặc cấu hình thủ công.

Nếu lỗi kết nối Redis, serializer không thể khắc phục. Nếu lỗi deserialize, kiểm tra định dạng và kiểu dữ liệu trước khi thay đổi network connection.

## 9. Thay đổi serializer là thay đổi định dạng dữ liệu đang lưu

Giả sử hệ thống trước đây dùng JDK serialization, sau đó đổi sang JSON. Các session hiện có trong Redis vẫn chứa byte theo định dạng cũ. Serializer mới có thể không đọc được chúng.

Tương tự, đổi ObjectMapper, type metadata, package DTO hoặc cách đặt tên field có thể làm dữ liệu cũ không còn tương thích.

Đây là một thay đổi schema dữ liệu, dù dữ liệu nằm trong cache/session store.

### Rủi ro khi rolling deployment

Giả sử App A vẫn dùng serializer cũ và App B đã dùng serializer mới:

1. App A ghi thuộc tính theo định dạng cũ.
2. Request tiếp theo đến App B.
3. App B cố deserialize dữ liệu cũ bằng serializer mới.
4. Nếu định dạng không tương thích, request có thể lỗi.
5. Ngược lại, App B ghi JSON và App A có thể không đọc được JSON.

Trong thời gian nhiều phiên bản chạy song song, các instance cần đọc được dữ liệu mà các instance khác ghi.

### Các chiến lược chuyển đổi

| Chiến lược | Khi phù hợp | Lưu ý |
|---|---|---|
| Giữ tương thích ngược | Có thể thiết kế serializer đọc được định dạng cũ và mới | Cần kiểm thử cả hai chiều |
| Chuyển đổi dữ liệu có kiểm soát | Có thể đọc và ghi lại session theo schema mới | Phải xử lý lỗi và phiên đang hoạt động |
| Chờ session cũ hết hạn | Session có TTL ngắn và có thể yêu cầu người dùng đăng nhập lại | Người dùng có thể mất trạng thái phiên |
| Cắt chuyển đồng bộ | Có cửa sổ bảo trì và quy trình rollout có kiểm soát | Cần dừng hoặc drain các writer cũ |

Không nên chỉ deploy serializer mới rồi giả định Redis tự chuyển dữ liệu. Redis không hiểu schema Java của session.

Nếu chọn để session cũ hết hạn tự nhiên, hãy xác định rõ tác động đến đăng nhập và quy trình người dùng. Với hệ thống yêu cầu trải nghiệm liên tục, cần chiến lược tương thích hoặc migration riêng.

## 10. Lỗi serialization và cách chẩn đoán

Một số lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể |
|---|---|
| Không serialize được thuộc tính | Object không được serializer hỗ trợ hoặc object graph có thành phần không thể serialize |
| Deserialize thành Map thay vì DTO | Thiếu type metadata hoặc cấu hình khôi phục kiểu không phù hợp |
| ClassCastException | Kiểu object được khôi phục khác với kiểu controller mong đợi |
| InvalidTypeIdException | Type metadata thiếu, sai hoặc bị validator từ chối |
| Lỗi khi rolling deploy | DTO hoặc serializer giữa các instance không tương thích |
| Dữ liệu session cũ không đọc được | Đã thay định dạng serializer mà không migration |
| Request lỗi ở cuối response | Serialization có thể diễn ra khi repository flush/save session |

Khi chẩn đoán:

1. Xác định request nào ghi thuộc tính và request nào đọc lại.
2. Xác định bean `springSessionDefaultRedisSerializer` thực sự được đăng ký.
3. Kiểm tra class cụ thể của thuộc tính và object lồng nhau.
4. Kiểm tra serializer và ObjectMapper giữa các instance.
5. Xác minh lỗi xảy ra ở serialize hay deserialize.
6. Kiểm thử với dữ liệu đại diện từ Redis test instance.
7. Kiểm tra thay đổi class hoặc type metadata giữa các phiên bản.

Không nên log nguyên byte session hoặc toàn bộ thuộc tính. Log tên thuộc tính, loại lỗi và correlation ID đã được bảo vệ thường đủ để điều tra.

## 11. Kiểm thử RedisSerializer theo hai mức

Cần kiểm tra cả serializer riêng và Spring Session repository thực tế.

### Unit test round-trip

Round-trip nghĩa là serialize một object rồi deserialize lại và xác minh object khôi phục có dữ liệu mong đợi.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;

class SessionSerializerTest {

    private final RedisSerializer<Object> serializer =
            new GenericJackson2JsonRedisSerializer();

    @Test
    void shouldSerializeAndDeserializeSessionDto() {
        CartSnapshot original = new CartSnapshot(
                List.of(new CartItem("BOOK-01", 2))
        );

        byte[] bytes = serializer.serialize(original);
        Object restored = serializer.deserialize(bytes);

        assertThat(restored).isInstanceOf(CartSnapshot.class);
        CartSnapshot cart = (CartSnapshot) restored;
        assertThat(cart.items()).hasSize(1);
        assertThat(cart.items().get(0).productId()).isEqualTo("BOOK-01");
        assertThat(cart.items().get(0).quantity()).isEqualTo(2);
    }

    record CartSnapshot(List<CartItem> items) {
    }

    record CartItem(String productId, int quantity) {
    }
}
~~~

Ví dụ dùng Java record và AssertJ. Cấu hình serializer thực tế của ứng dụng cần được dùng trong test thay vì tạo một serializer khác với production. Nếu dùng ObjectMapper tùy chỉnh, test phải kiểm tra đúng allowlist và module đã đăng ký.

### Integration test với Spring Session Redis

Unit test chỉ xác nhận serializer có thể chuyển đổi object. Nó chưa xác minh Spring Session repository thực sự dùng bean theo tên quy ước.

Integration test nên:

1. Khởi động Redis test instance hoặc Testcontainers.
2. Khởi động application context có Spring Session Redis.
3. Xác minh bean `springSessionDefaultRedisSerializer` có mặt và được repository sử dụng.
4. Gửi request tạo session và lưu DTO.
5. Giữ cookie hoặc Session ID từ response.
6. Gửi request mới với cùng ID.
7. Đọc thuộc tính và xác minh đúng kiểu, field và dữ liệu.
8. Lặp lại qua instance thứ hai dùng cùng repository và serializer.
9. Kiểm tra lỗi khi dữ liệu có type metadata không được phép hoặc không tương thích.

Mock `HttpSession` đơn giản không kiểm tra serialization vì nó có thể giữ object trực tiếp trong bộ nhớ.

### Kiểm thử tương thích giữa phiên bản

Nếu hệ thống rolling deployment, cần có test fixture đại diện cho dữ liệu được ghi bởi phiên bản trước. Test phiên bản mới phải đọc được fixture cũ nếu chiến lược migration yêu cầu tương thích ngược.

Không nên chỉ kiểm tra serialize rồi deserialize trong cùng một phiên bản; phép thử đó không phát hiện được mọi lỗi khi hai phiên bản ứng dụng dùng schema khác nhau.

## 12. Các nguyên tắc vận hành an toàn

- Dùng một bean `springSessionDefaultRedisSerializer` duy nhất trong application context.
- Giữ serializer và cấu hình ObjectMapper thống nhất giữa các instance.
- Chỉ lưu DTO nhỏ, có cấu trúc ổn định.
- Kiểm soát type metadata và allowlist khi deserialize object tổng quát.
- Bảo vệ Redis bằng ACL, network isolation và TLS.
- Không coi serialization là encryption.
- Đặt TTL session phù hợp để dữ liệu cũ được dọn theo chính sách.
- Lập kế hoạch migration trước khi đổi serializer.
- Theo dõi lỗi serialize/deserialize và tỷ lệ request lỗi.
- Không tự ghi hoặc sửa key nội bộ Spring Session để chữa lỗi serializer.

Nếu một thuộc tính không cần tồn tại qua request, đừng lưu nó vào session. Giảm số lượng và kích thước object là cách đơn giản để giảm chi phí serialization và rủi ro tương thích.

## 13. Những nhầm lẫn thường gặp

**“Chỉ cần khai báo một RedisSerializer bean bất kỳ là Spring Session sẽ dùng.”**  
Spring Session Redis tìm serializer theo tên quy ước `springSessionDefaultRedisSerializer`. Hãy khai báo đúng tên và kiểu trả về.

**“Serializer của RedisTemplate cũng là serializer của session.”**  
Hai cấu hình độc lập. Thay đổi RedisTemplate không tự động thay serializer mà Spring Session repository sử dụng.

**“JSON luôn tự biết khôi phục kiểu Java ban đầu.”**  
JSON mô tả cấu trúc dữ liệu. Với thuộc tính tổng quát `Object`, cần type metadata hoặc một quy tắc mapping rõ ràng để khôi phục kiểu.

**“Serialize nghĩa là dữ liệu đã được mã hóa.”**  
Không. Serializer chỉ chuyển định dạng; cần cơ chế bảo vệ và encryption riêng nếu dữ liệu yêu cầu.

**“Đổi serializer không ảnh hưởng session đang hoạt động.”**  
Session cũ vẫn chứa dữ liệu theo định dạng đã ghi. Serializer mới có thể không đọc được nếu không tương thích.

**“Lưu entity JPA vào session là tiện nhất.”**  
Entity có thể chứa proxy, quan hệ lazy và tham chiếu persistence context. DTO nhỏ hoặc ID tham chiếu thường ổn định hơn.

**“Round-trip test cùng một serializer là đủ cho rolling deployment.”**  
Cần kiểm thử dữ liệu được ghi từ phiên bản cũ và đọc bởi phiên bản mới, cũng như dữ liệu mới được đọc bởi mọi instance còn hoạt động.

## 14. Tự kiểm tra

1. Vì sao Spring Session cần serialize thuộc tính trước khi ghi vào Redis?
2. `RedisSerializer` khác `RedisTemplate` như thế nào?
3. Bean `springSessionDefaultRedisSerializer` có tên và kiểu trả về quan trọng ra sao?
4. Vì sao thay serializer trong RedisTemplate không tự động thay serializer của Spring Session?
5. JSON serializer cần thông tin gì để khôi phục một thuộc tính có kiểu tổng quát `Object`?
6. Vì sao polymorphic deserialization cần allowlist?
7. Vì sao không nên lưu entity JPA, HttpServletRequest hoặc socket vào session?
8. Điều gì có thể xảy ra khi App A và App B dùng serializer khác nhau?
9. Vì sao đổi serializer là một thay đổi định dạng dữ liệu cần kế hoạch migration?
10. Unit test round-trip khác integration test Spring Session Redis ở điểm nào?

### Gợi ý trả lời

1. Redis lưu byte hoặc chuỗi, còn thuộc tính session có thể là object Java; serializer chuyển đổi giữa hai biểu diễn.
2. RedisSerializer chuyển đổi object thành byte và ngược lại; RedisTemplate là API thao tác Redis, sử dụng một hoặc nhiều serializer.
3. Spring Session Redis dùng bean quy ước tên `springSessionDefaultRedisSerializer` với kiểu thường là `RedisSerializer<Object>` để serialize thuộc tính session.
4. Vì RedisTemplate và Spring Session repository có cấu hình serializer riêng.
5. Cần type metadata hoặc quy tắc mapping để khôi phục lớp Java cụ thể.
6. Vì dữ liệu có thể chứa type metadata; allowlist giới hạn những lớp được phép deserialize.
7. Các object đó phụ thuộc vòng đời request, connection hoặc persistence context và thường không phù hợp để serialize, chia sẻ giữa instance.
8. Một instance có thể ghi thành công nhưng instance kia không deserialize được, gây lỗi khi đọc session.
9. Session đang lưu vẫn mang định dạng cũ; serializer mới có thể không hiểu dữ liệu đó.
10. Round-trip test kiểm tra chuyển đổi object; integration test xác minh repository thực tế dùng đúng bean, lưu Redis và khôi phục qua request.

## Kết luận

`RedisSerializer` chuyển đổi thuộc tính session giữa object Java và byte lưu trong Redis. Spring Session Redis cho phép tùy chỉnh serializer thông qua bean có tên chính xác `springSessionDefaultRedisSerializer` và kiểu thường dùng `RedisSerializer<Object>`. Đây là cấu hình của repository session; nó độc lập với serializer của `RedisTemplate`.

JSON serializer giúp dữ liệu dễ quan sát nhưng cần xử lý type metadata và kiểm soát polymorphic deserialization. Dù chọn JDK serialization hay JSON, hãy lưu DTO nhỏ, ổn định, bảo vệ Redis và kiểm thử round-trip cũng như repository thực tế. Thay serializer là thay đổi định dạng dữ liệu: các instance cần tương thích trong rolling deployment và session cũ cần được đọc, chuyển đổi hoặc hết hạn theo kế hoạch rõ ràng.

