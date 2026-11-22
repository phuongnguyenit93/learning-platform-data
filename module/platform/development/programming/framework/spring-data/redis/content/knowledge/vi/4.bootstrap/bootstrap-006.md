# Cấu hình thủ công ConnectionFactory và Template trong Spring Data Redis

Trong ứng dụng Spring Boot, chỉ thêm `spring-boot-starter-data-redis` và khai báo `spring.data.redis.*` thường đã đủ để Spring Boot tự tạo kết nối và các bean làm việc với Redis. Tuy nhiên, khi cần kiểm soát cách kết nối, dùng serializer riêng, có nhiều Redis server, hoặc muốn hiểu chính xác cơ chế bên dưới, chúng ta có thể **tự khai báo `RedisConnectionFactory` và `RedisTemplate` bằng Java Configuration**.

Bài học này tập trung vào việc **khởi tạo và kết nối các thành phần thủ công** trong Spring Data Redis: xây dựng factory, cấu hình client Lettuce, tạo template cho chuỗi và object, đưa bean vào service, quan sát dữ liệu Redis, cũng như xử lý các lỗi cấu hình thường gặp. Ví dụ chính sử dụng Java 17+, Spring Boot 3.x và Spring Data Redis 3.x; khi triển khai với phiên bản khác, cần kiểm tra API và thuộc tính cấu hình tương ứng.

## 1. Mục tiêu sau bài học

Sau khi học, bạn có thể:

1. Giải thích vai trò của `RedisConnectionFactory`, `LettuceConnectionFactory`, `RedisConnection`, `RedisTemplate` và `StringRedisTemplate`.
2. Khởi tạo thủ công `LettuceConnectionFactory` cho Redis standalone và áp dụng host, port, database, thông tin xác thực, command timeout, TLS.
3. Tạo một `RedisTemplate<String, ProductSnapshot>` có serializer cho key và value được chỉ định rõ ràng.
4. Tạo `StringRedisTemplate` để thao tác chuỗi, bộ đếm và TTL.
5. Inject đúng template vào service bằng constructor và `@Qualifier` khi có nhiều bean tương ứng.
6. Phân biệt cấu hình do Spring Boot tự tạo với bean do mình khai báo và hiểu các hệ quả khi override.
7. Kiểm tra kết nối, dữ liệu Redis và nhận biết các vấn đề thường gặp do sai địa chỉ, xác thực, database hoặc serialization.

**Điều kiện đầu vào:** đã biết Java cơ bản, `@Configuration`, `@Bean`, Dependency Injection và cách chạy một ứng dụng Spring Boot; biết Redis lưu dữ liệu theo key và có các kiểu dữ liệu như String/Hash/List/Set.

## 2. Kiến trúc kết nối: thành phần nào làm việc gì?

Luồng thao tác thường gặp:

~~~text
ProductService
    |
    | inject @Qualifier("productRedisTemplate")
    v
RedisTemplate<String, ProductSnapshot>
    |        |
    |        +-- Key serializer: StringRedisSerializer
    |        +-- Value serializer: Jackson2JsonRedisSerializer<ProductSnapshot>
    |
    v
RedisConnectionFactory (bean do ứng dụng khai báo)
    |
    v
LettuceConnectionFactory
    |
    v
Lettuce client  --->  Redis Server
~~~

| Thành phần | Trách nhiệm | Lưu ý |
| --- | --- | --- |
| `RedisConnectionFactory` | Abstraction tạo/cung cấp `RedisConnection` để thực thi lệnh Redis | Là interface; được template và các thành phần Spring Data Redis khác dùng |
| `LettuceConnectionFactory` | Implementation dựa trên client Lettuce | Hỗ trợ standalone, Sentinel, Cluster và các tùy chọn client |
| `RedisConnection` | Abstraction kết nối cấp thấp, có các thao tác Redis | Thông thường không tự quản lý thủ công trong business service |
| `RedisTemplate<K, V>` | API đồng bộ mức cao cho các thao tác Redis và tuần tự hóa dữ liệu | Phải quan tâm đến serializer của key, value, hash key và hash value |
| `StringRedisTemplate` | RedisTemplate chuyên dụng với key/value dạng String | Phù hợp lệnh `GET`, `SET`, `INCR` và dữ liệu chuỗi dễ đọc bằng CLI |
| `RedisSerializer<T>` | Chuyển dữ liệu giữa object Java và bytes Redis | Hai ứng dụng phải thống nhất định dạng khi dùng chung key |

**Redis Server** là tiến trình lưu và xử lý dữ liệu; **Lettuce** là thư viện client giao tiếp qua mạng; **Spring Data Redis** là lớp tích hợp và trừu tượng hóa cho ứng dụng Spring. Tạo `RedisConnectionFactory` không khởi chạy Redis Server: server phải chạy độc lập, có hostname/port mà ứng dụng truy cập được.

Thông thường service sử dụng template, không gọi `factory.getConnection()` rồi giữ một `RedisConnection` cho tất cả các request. Template xử lý việc lấy và giải phóng kết nối theo cơ chế của factory; các đối tượng template được cấu hình đầy đủ có thể chia sẻ giữa các bean.

## 3. Khi nào nên cấu hình thủ công?

Với phần lớn dự án Spring Boot, auto-configuration có thể đã đủ:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
~~~

Spring Boot phát hiện starter phù hợp và tạo `RedisConnectionFactory` cùng các template mặc định nếu chưa có bean tương ứng. Khai báo thủ công hữu ích khi:

- Cần kiểm soát cách khởi tạo Lettuce hoặc lựa chọn topology Redis khác cấu hình mặc định.
- Muốn tách cấu hình Redis của một module dưới prefix riêng, ví dụ `app.redis.*`.
- Phải dùng serializer rõ ràng cho từng loại dữ liệu, thay cho serialization mặc định.
- Dùng nhiều Redis khác nhau: cache, session, số liệu ngắn hạn hoặc hệ thống cũ.
- Cần cấu hình TLS, ACL, command timeout hoặc client options có chủ đích.
- Muốn quản lý tên bean, quan hệ giữa factory và từng template trong ứng dụng lớn.

Không cần cấu hình thủ công chỉ để thực hiện `GET`/`SET`. Nếu dự án chỉ cần một kết nối Redis với cấu hình chuẩn, phương án auto-configuration thường ngắn gọn và ít chi phí bảo trì hơn.

## 4. Chuẩn bị dự án và Redis cục bộ

### 4.1. Maven dependencies

Trong ứng dụng Spring Boot có BOM/dependency management phù hợp, thêm:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Đây là phần dependency, không phải file `pom.xml` hoàn chỉnh. `spring-boot-starter-data-redis` thường mang Lettuce làm Redis client mặc định. `spring-boot-starter-web` cung cấp REST/JSON phục vụ ví dụ và các dependency Jackson thường dùng. Có thể dùng Gradle tương đương:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Nếu muốn sử dụng Jackson JSON serializer nhưng không sử dụng starter web, cần bảo đảm ứng dụng có Jackson phù hợp trên classpath.

### 4.2. Chạy Redis bằng Docker

Ví dụ dành cho máy lập trình cá nhân:

~~~bash
docker run --name manual-redis -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it manual-redis redis-cli PING
~~~

Nếu Redis hoạt động, `PING` trả về `PONG`. Nếu đã có Redis khác chiếm port 6379, đổi port phía máy chủ, ví dụ `-p 127.0.0.1:6380:6379` rồi khai báo `app.redis.port: 6380`.

Lệnh trên dùng Redis local không mật khẩu, chỉ bind cổng máy host vào loopback. Khi kết nối đến Redis từ môi trường khác, phải áp dụng cơ chế kiểm soát mạng, xác thực và mã hóa phù hợp. Trong Docker Compose, container Spring Boot thường kết nối bằng **tên service của container Redis**; `localhost` bên trong container ứng dụng không chỉ đến container Redis khác.

## 5. Ví dụ hoàn chỉnh: tự khai báo ConnectionFactory và hai Template

Chúng ta sẽ sử dụng Redis standalone ở `localhost:6379`. Cấu hình dùng namespace `app.redis` để thể hiện rõ ứng dụng tự xử lý các thuộc tính này, thay vì phụ thuộc vào auto-configuration của Spring Boot.

### 5.1. Khai báo application.yml

~~~yaml
app:
  redis:
    host: ${APP_REDIS_HOST:localhost}
    port: ${APP_REDIS_PORT:6379}
    database: ${APP_REDIS_DATABASE:0}
    username: ${APP_REDIS_USERNAME:}
    password: ${APP_REDIS_PASSWORD:}
    command-timeout-ms: ${APP_REDIS_TIMEOUT_MS:2000}
    ssl: ${APP_REDIS_SSL:false}
~~~

- Redis local trong ví dụ không bật xác thực, nên `username`/`password` để trống.
- Khi dùng ACL hoặc mật khẩu, cấp giá trị qua biến môi trường; không ghi mật khẩu production vào mã nguồn hoặc file được commit.
- `database: 0` là logical database thông dụng trong Redis standalone. Redis Cluster có cách quản lý key khác và không hỗ trợ chọn nhiều logical database như standalone.
- `command-timeout-ms` là giới hạn thời gian chờ một lệnh phía client; cần chọn dựa trên SLA, độ trễ mạng và chính sách lỗi của ứng dụng.
- `ssl: true` chỉ hoạt động khi endpoint Redis thực sự cung cấp TLS và chứng chỉ được client tin cậy. Bật TLS phía client trong khi server chỉ hỗ trợ plaintext sẽ gây lỗi kết nối.

### 5.2. Khai báo model dùng để lưu vào Redis

Tạo `ProductSnapshot.java`:

~~~java
package com.example.redis;

import java.math.BigDecimal;

public record ProductSnapshot(
        String productId,
        String name,
        BigDecimal price
) {
}
~~~

Đây là đối tượng ví dụ cho cache/tạm lưu dữ liệu sản phẩm. Bài này dùng Java record để minh họa. Khi lưu object thật, cần xem xét kiểu dữ liệu, phiên bản schema, constructor/setter và khả năng đọc lại sau khi ứng dụng được nâng cấp.

### 5.3. Tạo bean RedisConnectionFactory thủ công

Tạo `ManualRedisConfig.java`:

~~~java
package com.example.redis;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ManualRedisConfig {

    @Bean
    public RedisConnectionFactory redisConnectionFactory(
            @Value("${app.redis.host:localhost}") String host,
            @Value("${app.redis.port:6379}") int port,
            @Value("${app.redis.database:0}") int database,
            @Value("${app.redis.username:}") String username,
            @Value("${app.redis.password:}") String password,
            @Value("${app.redis.command-timeout-ms:2000}") long timeoutMs,
            @Value("${app.redis.ssl:false}") boolean ssl) {

        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration(host, port);
        server.setDatabase(database);

        if (!username.isBlank()) {
            server.setUsername(username);
        }
        if (!password.isBlank()) {
            server.setPassword(RedisPassword.of(password));
        }

        var clientBuilder = LettuceClientConfiguration.builder();
        clientBuilder.commandTimeout(Duration.ofMillis(timeoutMs));
        if (ssl) {
            clientBuilder.useSsl();
        }

        return new LettuceConnectionFactory(server, clientBuilder.build());
    }

    @Bean("productRedisTemplate")
    public RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory redisConnectionFactory) {

        RedisTemplate<String, ProductSnapshot> template =
                new RedisTemplate<>();

        template.setConnectionFactory(redisConnectionFactory);

        StringRedisSerializer stringSerializer =
                new StringRedisSerializer();
        Jackson2JsonRedisSerializer<ProductSnapshot> jsonSerializer =
                new Jackson2JsonRedisSerializer<>(ProductSnapshot.class);

        template.setKeySerializer(stringSerializer);
        template.setHashKeySerializer(stringSerializer);
        template.setValueSerializer(jsonSerializer);
        template.setHashValueSerializer(jsonSerializer);

        return template;
    }

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory redisConnectionFactory) {
        return new StringRedisTemplate(redisConnectionFactory);
    }
}
~~~

**Giải thích theo thứ tự tạo bean:**

1. Spring đọc giá trị `app.redis.*` và gọi phương thức `redisConnectionFactory(...)` để khởi tạo `RedisStandaloneConfiguration`.
2. `RedisStandaloneConfiguration` chứa địa chỉ và thông tin xác thực đến Redis server; `LettuceClientConfiguration` chứa các thiết lập phía client, ở đây là command timeout và TLS tùy chọn.
3. `new LettuceConnectionFactory(server, clientBuilder.build())` tạo implementation của `RedisConnectionFactory` dựa trên Lettuce.
4. Spring đưa factory này vào phương thức tạo `productRedisTemplate(...)`. Template được thiết lập serializer và được quản lý vòng đời như một Spring bean.
5. Cùng một factory được inject vào `stringRedisTemplate(...)`; hai template dùng chung thông số kết nối nhưng thực hiện tuần tự hóa khác nhau.

Đây là **cấu hình thủ công đầy đủ cho một Redis standalone**. Factory không nên được khởi tạo mới mỗi lần service nhận request. Spring quản lý factory và template như các singleton theo cấu hình bean mặc định, rồi giải phóng tài nguyên khi application context đóng.

Tại ví dụ này, `@Bean("productRedisTemplate")` giúp tránh mơ hồ khi ứng dụng có nhiều `RedisTemplate`. `StringRedisTemplate` là class chuyên biệt cho dữ liệu chuỗi, nên việc gọi `INCR` hoặc đọc giá trị bằng Redis CLI rất trực quan.

### 5.4. Dùng template trong service

Tạo `ProductSnapshotService.java`:

~~~java
package com.example.redis;

import java.time.Duration;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSnapshotService {
    private final RedisTemplate<String, ProductSnapshot> redis;

    public ProductSnapshotService(
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductSnapshot> redis) {
        this.redis = redis;
    }

    public void save(ProductSnapshot product, Duration ttl) {
        if (product == null || product.productId() == null
                || product.productId().isBlank()) {
            throw new IllegalArgumentException("Invalid product");
        }
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        redis.opsForValue().set(key(product.productId()), product, ttl);
    }

    public Optional<ProductSnapshot> find(String productId) {
        return Optional.ofNullable(redis.opsForValue().get(key(productId)));
    }

    public boolean remove(String productId) {
        return Boolean.TRUE.equals(redis.delete(key(productId)));
    }

    private String key(String productId) {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("Invalid product ID");
        }
        return "demo:product:snapshot:" + productId;
    }
}
~~~

Khi gọi:

~~~java
ProductSnapshot example =
        new ProductSnapshot("42", "Ban phim", new BigDecimal("590000"));

productSnapshotService.save(example, Duration.ofMinutes(10));
Optional<ProductSnapshot> stored =
        productSnapshotService.find("42");
boolean deleted = productSnapshotService.remove("42");
~~~

thì key tương ứng là `demo:product:snapshot:42`. Giá trị được serializer chuyển từ `ProductSnapshot` thành JSON bytes. Lệnh `SET` có TTL sẽ tự hết hạn key sau thời gian được chỉ định; `GET` của key không tồn tại trả về `null` ở mức template, ở đây được chuyển thành `Optional.empty()`. `delete()` trả giá trị kiểu `Boolean` có thể nullable, do đó ví dụ kiểm tra bằng `Boolean.TRUE.equals(...)`.

Đoạn gọi service ở trên dùng để minh họa trong một method có sẵn; nếu muốn thực thi, hãy đặt nó trong controller, runner hoặc bài kiểm thử với bean `ProductSnapshotService` được inject.

### 5.5. Dùng StringRedisTemplate để ghi bộ đếm

Tạo `ViewCounterService.java`:

~~~java
package com.example.redis;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ViewCounterService {
    private final StringRedisTemplate redis;

    public ViewCounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long increase(String productId) {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("Invalid product ID");
        }

        String key = "demo:product:views:" + productId;
        Long count = redis.opsForValue().increment(key);
        if (count == null) {
            throw new IllegalStateException("Missing Redis increment result");
        }
        return count;
    }
}
~~~

Lệnh `increment(...)` tương ứng với phép tăng nguyên tử bằng Redis `INCR`. Redis server xử lý phần tăng; service không cần `GET` rồi cộng 1 phía Java và `SET` lại. Những số đếm cần lưu bền vững vẫn phải có chiến lược persistence/backup hoặc đưa vào nguồn lưu trữ phù hợp. Template không tự đảm bảo dữ liệu tồn tại mãi khi Redis gặp lỗi.

Nếu muốn tự đặt TTL cho bộ đếm, có thể dùng `redis.expire(key, Duration.ofHours(1))`, nhưng hai lời gọi `increment` và `expire` riêng lẻ không là một thao tác nguyên tử chung. Với giới hạn thời gian chính xác hay chống race condition, cần thiết kế lệnh/transaction/script phù hợp.

## 6. Serializer: phần quan trọng nhất khi tự tạo RedisTemplate

Redis lưu key/value dưới dạng bytes. Khai báo `RedisTemplate<String, ProductSnapshot>` chỉ cho compiler biết kiểu Java; **nó không tự xác định định dạng Redis phù hợp với dữ liệu của bạn**. Serializer thực tế mới quyết định bytes được ghi và đọc.

### 6.1. Bốn serializer thường cần cấu hình

| Property trên RedisTemplate | Dữ liệu áp dụng | Lựa chọn trong ví dụ |
| --- | --- | --- |
| `keySerializer` | Key của lệnh `GET`, `SET`, `DEL`… | `StringRedisSerializer` |
| `valueSerializer` | Value của dữ liệu key-value | `Jackson2JsonRedisSerializer<ProductSnapshot>` |
| `hashKeySerializer` | Field của Redis Hash | `StringRedisSerializer` |
| `hashValueSerializer` | Value thuộc một field của Redis Hash | JSON serializer cho `ProductSnapshot` |

Trong thực tế, loại dữ liệu của **value trong Hash** có thể khác value của thao tác `opsForValue()`. Nếu Redis Hash lưu những scalar như `name = "ABC"`, `price = "100"`, có thể cần `StringRedisSerializer` cho `hashValueSerializer` hoặc một template riêng. Không nên dùng một template cho mọi schema và kỳ vọng serializer tự suy đoán được định dạng.

### 6.2. Những lựa chọn phổ biến

**StringRedisSerializer**

- Chuyển chuỗi Java thành chuỗi bytes theo định dạng ký tự nhất quán.
- Thích hợp key, Redis String và Hash field dạng text.
- Cho phép người vận hành đọc giá trị bằng `redis-cli GET` hoặc `HGETALL` dễ hơn.

**Jackson2JsonRedisSerializer<T>**

- Serializer JSON với kiểu đích cụ thể, ví dụ `ProductSnapshot.class`.
- Dễ quan sát bằng CLI; có thể thay đổi schema JSON có chủ đích.
- Cần bảo đảm dữ liệu trong key thực sự phù hợp với loại `T` khi đọc lại.
- Khi nâng cấp model, cần có chiến lược tương thích trường cũ/mới, null và version.

**GenericJackson2JsonRedisSerializer**

- Có thể dùng khi một template cần lưu nhiều loại object, thường đi kèm thông tin kiểu để khôi phục object.
- Cần kiểm soát nguồn dữ liệu, cấu hình typing và các loại object được phép deserialize; không xem JSON có type metadata là an toàn để đọc từ nguồn không đáng tin.
- Có thể tạo phụ thuộc vào tên class Java nên migration phức tạp hơn template dùng một kiểu rõ ràng.

**JdkSerializationRedisSerializer**

- Một lựa chọn tuần tự hóa Java nhị phân được RedisTemplate dùng trong một số cấu hình mặc định.
- Khó đọc bằng CLI, phụ thuộc tương thích Java/class, tiềm ẩn rủi ro khi deserialize dữ liệu không đáng tin.
- Tránh dùng tùy tiện cho dữ liệu cần chia sẻ giữa nhiều ngôn ngữ hoặc cần ổn định qua nhiều phiên bản triển khai.

Nếu không đặt serializer tường minh cho một `RedisTemplate` mới, đừng giả định key sẽ trông giống chuỗi bạn truyền vào. Cấu hình mặc định của `RedisTemplate` có thể tạo key/value nhị phân theo JDK serialization, khiến `redis-cli GET demo:...` không tìm đúng key do các bytes key khác nhau.

### 6.3. Vì sao không dùng cùng một key với hai template khác serializer?

Giả sử:

~~~text
StringRedisTemplate:
  key = "demo:product:snapshot:42"
  value = "hello"

RedisTemplate<String, ProductSnapshot>:
  key = "demo:product:snapshot:42"
  value = JSON của ProductSnapshot
~~~

Hai thao tác sẽ **ghi đè cùng một Redis key** nếu key serializer của cả hai đều là chuỗi. Sau khi ghi `hello` bằng `StringRedisTemplate`, việc đọc lại qua template mong đợi `ProductSnapshot` có thể thất bại khi deserialize. Do đó:

1. Quy định **namespace/prefix** cho từng loại dữ liệu.
2. Chỉ một luồng/định dạng sở hữu một key, hoặc ghi rõ hợp đồng dữ liệu giữa các ứng dụng.
3. Khi đổi serializer, lên kế hoạch đổi key prefix, xóa cache cũ có kiểm soát hoặc migration.
4. Nếu nhiều ứng dụng cùng đọc Redis, xác định charset, schema JSON, loại value và thời gian tồn tại từ đầu.

Các module như Spring Cache hoặc Spring Session có thể có key namespace và serializer riêng; cấu hình thủ công cho template không đồng nghĩa mọi module đó tự chuyển sang định dạng JSON của template.

## 7. Kiểm tra RedisConnectionFactory và Template sau khi cấu hình

### 7.1. Xác nhận Redis server

~~~bash
docker exec -it manual-redis redis-cli PING
~~~

Kỳ vọng `PONG`. Nếu không, kiểm tra container, port mapping, Docker network và Redis logs trước khi điều tra Java.

### 7.2. Quan sát key được tạo

Sau khi service thực sự gọi `save(...)` hoặc `increase(...)`:

~~~bash
docker exec -it manual-redis redis-cli
~~~

Nhập các lệnh:

~~~redis
GET demo:product:snapshot:42
TTL demo:product:snapshot:42
TYPE demo:product:snapshot:42
GET demo:product:views:42
SCAN 0 MATCH demo:* COUNT 100
~~~

Kỳ vọng key snapshot có nội dung JSON cho `ProductSnapshot` và `TYPE` là `string`; TTL còn lại giảm theo thời gian. Key bộ đếm chứa chữ số và thay đổi khi tăng. `SCAN` trả về một cursor; muốn duyệt hết không gian key cần tiếp tục dùng cursor trả về cho đến khi nó trở thành 0.

Nếu `GET` không thấy key, kiểm tra đúng hostname, port, logical database, prefix và TTL; Redis CLI mặc định truy cập database 0. Trong standalone, nếu ứng dụng cấu hình database khác, dùng `SELECT <db>` trong CLI để kiểm tra. Trong Redis Cluster không áp dụng mô hình nhiều database này.

### 7.3. Kiểm tra bằng mã Java ở mức ứng dụng

Có thể tạo một `CommandLineRunner` cho môi trường phát triển:

~~~java
@Bean
CommandLineRunner redisDemo(
        ProductSnapshotService productService,
        ViewCounterService counterService) {

    return args -> {
        var product =
                new ProductSnapshot("42", "Ban phim", new BigDecimal("590000"));
        productService.save(product, Duration.ofMinutes(10));

        System.out.println(productService.find("42"));
        System.out.println(counterService.increase("42"));
    };
}
~~~

Đặt đoạn trên trong class `@Configuration` của ví dụ và bổ sung import `CommandLineRunner`, `BigDecimal`, `Duration`; chỉ dùng runner này ở môi trường học tập. Trong ứng dụng production, không nên ghi dữ liệu demo hoặc log object kinh doanh mỗi lần startup.

### 7.4. Vòng đời và kết nối

- `LettuceConnectionFactory` là bean Spring, được khởi tạo và dọn dẹp cùng application context.
- Template lấy connection từ factory để thực thi lệnh; ứng dụng thường không tự mở/đóng connection cho mỗi method.
- Kết nối Redis có thể được tạo khi cần thực thi lệnh. **Ứng dụng startup thành công không đảm bảo mọi lệnh Redis về sau đều thành công**; xác nhận bằng một thao tác thực hoặc health check.
- Trên triển khai thật, cần timeout, logging/metrics, error handling và chính sách khi Redis mất kết nối.

## 8. Bean tự khai báo tương tác thế nào với Spring Boot auto-configuration?

Spring Boot tạo một số Redis bean mặc định **khi chưa có bean phù hợp**. Quy tắc thực tế cần chú ý:

1. Khi khai báo `RedisConnectionFactory` của riêng mình, auto-configuration kết nối thông thường sẽ dùng factory đã có thay vì tạo thêm một factory mặc định cùng vai trò.
2. Spring Boot có thể vẫn tạo bean tên `redisTemplate` mặc định nếu chưa có bean với **tên** đó. Bean `productRedisTemplate` của ví dụ có tên riêng, nên hai template có thể cùng tồn tại.
3. Spring Boot thường tạo `StringRedisTemplate` khi chưa có bean thuộc loại tương ứng. Ở ví dụ, ta tự tạo bean `stringRedisTemplate` nên phần tự động đó không cần chạy.
4. Khi inject `RedisTemplate<String, ProductSnapshot>`, nên chủ động chỉ đúng bean qua `@Qualifier("productRedisTemplate")`, đặc biệt khi trong ứng dụng còn các RedisTemplate khác.
5. Nếu có nhiều bean `RedisConnectionFactory`, mọi điểm inject factory (template, cache, session…) cần giải quyết rõ qua `@Qualifier` hoặc bean `@Primary` phù hợp.

**Lưu ý quan trọng:** `@Primary` chỉ định một ứng viên ưu tiên khi dependency injection có nhiều bean cùng loại; nó không thay thế yêu cầu đặt tên bean rõ ràng, không thiết lập serializer và không đảm bảo module khác dùng đúng Redis.

Nếu dự án đang có một auto-configured `redisTemplate` và bạn cần thay thế nó bằng template riêng, có thể đặt tên bean là `redisTemplate` để Spring Boot không tạo bean cùng tên; sau đó phải cân nhắc kiểu generic và những caller đang phụ thuộc vào bean mặc định. Tránh thay đổi bean chung trong dự án lớn mà chưa xác định thành phần nào đang sử dụng.

## 9. Cấu hình thủ công theo từng loại Redis topology

Ví dụ ở phần 5 dùng `RedisStandaloneConfiguration`. Trong hạ tầng thật, factory còn có thể được tạo với cấu hình Sentinel hoặc Cluster. Phần này cho thấy **điểm thay đổi nằm ở cấu hình server được truyền cho factory**; template vẫn có thể giữ nguyên nếu hợp đồng dữ liệu không đổi.

### 9.1. Standalone

~~~java
RedisStandaloneConfiguration standalone =
        new RedisStandaloneConfiguration("redis.example.internal", 6379);
standalone.setDatabase(0);

RedisConnectionFactory factory =
        new LettuceConnectionFactory(standalone);
~~~

Hệ thống chỉ có một endpoint Redis. Cần tự cân nhắc kết nối, bảo mật, tính sẵn sàng và phục hồi khi server gặp sự cố. Với endpoint không thuộc mạng đáng tin, cấu hình xác thực và TLS phù hợp thay vì sử dụng đoạn tối giản trên.

### 9.2. Sentinel

Redis Sentinel giám sát master và hỗ trợ phát hiện/chuyển master trong cấu hình replication. Thay vì trỏ ứng dụng trực tiếp vào một master cố định, client biết danh sách Sentinel và tên master được quản lý.

~~~java
RedisSentinelConfiguration sentinel =
        new RedisSentinelConfiguration()
                .master("mymaster")
                .sentinel("sentinel-1.internal", 26379)
                .sentinel("sentinel-2.internal", 26379)
                .sentinel("sentinel-3.internal", 26379);

RedisConnectionFactory factory =
        new LettuceConnectionFactory(sentinel);
~~~

Import `RedisSentinelConfiguration` từ `org.springframework.data.redis.connection`. Cần bổ sung xác thực của Redis data nodes và Sentinel nếu hạ tầng yêu cầu; không mặc định rằng thông tin xác thực cho hai vai trò là giống nhau. Việc Sentinel chuyển master không làm mất yêu cầu xử lý timeout, lệnh thất bại hoặc retry có kiểm soát tại ứng dụng.

### 9.3. Cluster

Redis Cluster phân phối key theo hash slot trên nhiều node. Ví dụ tạo factory từ các node khởi tạo:

~~~java
RedisClusterConfiguration cluster =
        new RedisClusterConfiguration(
                List.of("redis-1.internal:6379",
                        "redis-2.internal:6379",
                        "redis-3.internal:6379"));

RedisConnectionFactory factory =
        new LettuceConnectionFactory(cluster);
~~~

Import `RedisClusterConfiguration` từ `org.springframework.data.redis.connection` và `List` từ `java.util`. Danh sách node chỉ là các điểm khởi tạo kết nối: client khám phá cấu trúc cluster theo khả năng của nó. Một số lệnh nhiều key chịu hạn chế của hash slot; Redis Cluster không hỗ trợ `SELECT` sang database khác như standalone. Khi cấu hình production, bổ sung TLS/ACL, cách resolve hostname được cluster quảng bá, retry/timeout hợp lý và kiểm tra hành vi failover.

**Không sử dụng cùng lúc ba kiểu cấu hình trên cho một factory.** Chọn topology đúng với Redis deployment. Một Redis standalone chạy trong Docker không tự trở thành Sentinel hoặc Cluster chỉ vì mã Java đổi constructor.

## 10. Nhiều RedisConnectionFactory và nhiều Template trong một ứng dụng

Một dự án có thể dùng Redis riêng cho các mục đích khác nhau, ví dụ cache ngắn hạn và số liệu sự kiện. Khi đó phải định nghĩa rõ bean nào đi với endpoint nào.

~~~java
@Bean("cacheRedisConnectionFactory")
RedisConnectionFactory cacheRedisConnectionFactory() {
    return new LettuceConnectionFactory(
            new RedisStandaloneConfiguration("cache-redis.internal", 6379));
}

@Bean("metricsRedisConnectionFactory")
RedisConnectionFactory metricsRedisConnectionFactory() {
    return new LettuceConnectionFactory(
            new RedisStandaloneConfiguration("metrics-redis.internal", 6379));
}

@Bean("metricsRedisTemplate")
StringRedisTemplate metricsRedisTemplate(
        @Qualifier("metricsRedisConnectionFactory")
        RedisConnectionFactory factory) {
    return new StringRedisTemplate(factory);
}
~~~

Ví dụ trên chỉ tập trung vào wiring; hostname là minh họa, chưa khai báo xác thực/TLS. Khi đặt hai factory trong cùng một context, **hãy gắn `@Qualifier` cho mọi bean phụ thuộc** hoặc chủ động chỉ định factory mặc định bằng `@Primary`. Không để Spring Boot tự chọn nhầm Redis cache cho Spring Session, Redis CacheManager hoặc các thành phần khác.

Nếu các Redis có định dạng giá trị khác nhau, đặt tên template thể hiện cả mục đích lẫn loại dữ liệu; đừng dùng một `RedisTemplate<Object, Object>` duy nhất cho mọi Redis server.

## 11. Phân biệt RedisTemplate, Spring Cache và Redis Repository

Khi mới khởi tạo Spring Data Redis, có ba cách tiếp cận dễ bị trộn lẫn:

| Công cụ | Khi nào dùng | Cấu hình liên quan |
| --- | --- | --- |
| `RedisTemplate` | Cần chọn lệnh Redis cụ thể: `SET`, `GET`, `HSET`, `INCR`, TTL… | `RedisConnectionFactory` và bốn nhóm serializer |
| `StringRedisTemplate` | Key/value chuỗi, bộ đếm, dữ liệu CLI-friendly | Factory và string serializer đã được thiết lập |
| Spring Cache với Redis backend | Cache kết quả method qua `@Cacheable`, `@CacheEvict` | `CacheManager`, `RedisCacheConfiguration`, serializer/cache key riêng |
| Redis Repository | Lưu entity thông qua Repository, `@RedisHash`, `@Id` | Cấu hình repository mapping và Redis operations được sử dụng |

**Tạo một `RedisTemplate<String, ProductSnapshot>` không có nghĩa Spring Cache tự dùng JSON serializer của template này.** Redis CacheManager quản lý serializer và key prefix của cache riêng; nếu ứng dụng dùng cache annotations, cần cấu hình phù hợp cho lớp cache.

Ví dụ minh họa Spring Cache độc lập với `RedisTemplate`:

~~~java
@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory factory) {
        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(5))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(factory)
                .cacheDefaults(defaults)
                .build();
    }
}
~~~

Đoạn này cần import `RedisCacheManager`, `RedisCacheConfiguration`, `Duration`, `@Bean`, `@Configuration` và `@EnableCaching`; đồng thời bổ sung `spring-boot-starter-cache` nếu dùng Spring Cache. Đây chỉ là phần minh họa mối quan hệ giữa factory và cache manager; serializer mặc định của CacheManager cần được đánh giá riêng theo schema và cách sử dụng của ứng dụng.

## 12. Vấn đề về timeout, transaction, performance và quản lý connection

### 12.1. Timeout cần thiết nhưng không xử lý thay lỗi

`commandTimeout(Duration.ofMillis(...))` giới hạn thời gian chờ thao tác Redis ở phía Lettuce. Khi timeout, ứng dụng vẫn phải quyết định:

- Đối với **cache có thể tái tạo**, có thể cân nhắc đọc nguồn chính rồi ghi cache lại sau; phải tránh làm nguồn chính quá tải khi Redis mất kết nối.
- Đối với **bộ đếm/lưu trạng thái nghiệp vụ quan trọng**, không nên âm thầm bỏ qua lỗi nếu giá trị đó cần chính xác hoặc bền vững.
- Nếu lệnh đã gửi nhưng client bị timeout trước khi nhận kết quả, cần thận trọng với retry thao tác **không idempotent** như `INCR`: retry có thể làm tăng hai lần.

Timeout là một ranh giới về thời gian chờ, không phải bảo đảm lệnh phía Redis đã hoặc chưa thực thi.

### 12.2. Có cần connection pool?

Lettuce hỗ trợ hoạt động trên kết nối native được chia sẻ cho nhiều thao tác thông thường. Không phải dự án nào cũng cần cấu hình pool riêng. Pool có thể phù hợp với một số kiểu kết nối đặc biệt hoặc khi đã đo được nhu cầu; cấu hình pool quá lớn không đồng nghĩa tăng throughput. Khi thêm pooling, cần quan sát số kết nối, thời gian chờ lấy connection, timeout và tài nguyên phía Redis.

### 12.3. Có nên gọi setEnableTransactionSupport(true)?

`RedisTemplate#setEnableTransactionSupport(true)` là một tùy chọn cho việc gắn thao tác Redis với giao dịch được Spring quản lý trong những tình huống phù hợp. **Nó không biến Redis và cơ sở dữ liệu quan hệ thành một giao dịch phân tán nguyên tử**; `MULTI/EXEC`, transaction của Spring và transaction của database có phạm vi khác nhau.

Chỉ bật khi thật sự đã thiết kế ngữ nghĩa transaction, kiểm tra ảnh hưởng đến đọc/ghi, kết nối và thứ tự commit. Đối với các ví dụ `GET`/`SET`/`INCR` thông thường ở bài này, không cần bật.

### 12.4. TTL và key naming

Template cho phép:

~~~java
redis.opsForValue().set("demo:product:snapshot:42",
        product, Duration.ofMinutes(10));

Boolean updated =
        redis.expire("demo:product:snapshot:42", Duration.ofMinutes(30));

Boolean existed =
        redis.hasKey("demo:product:snapshot:42");
~~~

Đoạn trên giả định có biến `redis` kiểu `RedisTemplate<String, ProductSnapshot>` và `product` kiểu `ProductSnapshot`. `expire` và `hasKey` có thể trả `Boolean` nullable trong API, nên khi dùng trong điều kiện hãy kiểm tra thích hợp.

Quy ước key nên bao gồm tên ứng dụng/feature và định danh phù hợp, ví dụ `shop:product:snapshot:42`. Nếu có tenant hoặc phạm vi truy cập, key phải thể hiện đủ ngữ cảnh để tránh chia sẻ nhầm dữ liệu. Đừng nhúng token, mật khẩu hoặc PII không cần thiết vào key.

## 13. Các lỗi thường gặp khi khai báo thủ công

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `RedisConnectionFailureException` hoặc Connection refused | Sai host/port, Redis chưa chạy, firewall, Docker network | `redis-cli PING`, kiểm tra port và hostname trong môi trường chạy app |
| Authentication failed / NOAUTH | Sai ACL username/password hoặc Redis yêu cầu xác thực | Kiểm tra quyền, biến môi trường, chính sách mật khẩu |
| TLS handshake failed | Client bật TLS nhưng server không bật; certificate không đáng tin; endpoint sai | Kiểm tra endpoint TLS, CA và thiết lập phía client/server |
| Command timeout | Redis chậm/không phản hồi, mạng lỗi, timeout quá ngắn | Xem metric latency, logs, tải Redis, network và deadline |
| `NoSuchBeanDefinitionException` | Thiếu bean hoặc cấu hình không được component scan | Kiểm tra package của `@Configuration` và kiểu/qualifier inject |
| `NoUniqueBeanDefinitionException` | Có nhiều factory hoặc template cùng phù hợp | Dùng `@Qualifier`, tên bean hoặc `@Primary` có chủ đích |
| Đọc `null` dù thấy dữ liệu | Khác DB, key prefix, key serializer, key đã hết TTL | So sánh bytes/key, `SELECT`, `TTL` và cấu hình factory |
| Giá trị là bytes khó đọc trong CLI | Serializer nhị phân, có thể dùng JDK serializer | Kiểm tra `keySerializer`/`valueSerializer` thực tế của template |
| JSON deserialize lỗi | Value được ghi bằng serializer khác hoặc model đã đổi schema | Xác định hợp đồng định dạng, version key và phương án migration |
| `WRONGTYPE Operation against a key...` | Key hiện có kiểu Redis khác với lệnh đang dùng | Dùng `TYPE <key>`, tách namespace, xóa dữ liệu thử nghiệm có kiểm soát |
| `MOVED` hoặc lỗi hash slot | Dùng cluster nhưng client/topology/cross-slot không phù hợp | Kiểm tra Cluster configuration, seed node và lệnh nhiều key |
| Cache annotation không dùng template đã khai báo | CacheManager có serializer và cấu hình riêng | Xem bean `CacheManager`/`RedisCacheConfiguration` |

**Một lỗi tinh vi:** có thể viết template với key `StringRedisSerializer` nhưng đọc nó bằng một `RedisTemplate` khác dùng JDK serializer. Phía Java nhìn như cùng key String, song bytes gửi đến Redis khác nhau nên kết quả là “không tìm thấy”. Do đó kiểm tra serializer trước khi kết luận Redis không lưu dữ liệu.

### Quy trình khoanh vùng sự cố

1. **Kiểm tra server:** Redis có chạy, phản hồi `PING` và địa chỉ đúng không?
2. **Kiểm tra credentials và TLS:** endpoint có yêu cầu AUTH, ACL, certificate hoặc port TLS riêng không?
3. **Kiểm tra bean:** Spring đang inject chính xác factory và template nào?
4. **Kiểm tra key:** đã vào đúng logical database, namespace và cùng cách serialize key chưa?
5. **Kiểm tra value:** serializer ghi và đọc có thống nhất, JSON schema có phù hợp không?
6. **Kiểm tra vòng đời:** TTL đã hết, key có bị một service khác xóa/ghi đè không?
7. **Kiểm tra tải thực:** timeout có tương quan với CPU, memory, network hoặc số lượng client không?

Không dùng `KEYS *` để quét toàn bộ key trên Redis đang phục vụ tải lớn; dùng `SCAN` theo cursor hoặc metric phù hợp. Không thử `FLUSHDB`/`FLUSHALL` trên môi trường có dữ liệu thật để “sửa lỗi” cấu hình.

## 14. Thiết kế cấu hình tốt hơn cho dự án lớn

Ví dụ ở phần 5 dùng `@Value` trực tiếp để tập trung vào cách tạo factory. Khi số lượng tham số tăng, có thể gom dưới một class `@ConfigurationProperties(prefix = "app.redis")` có validation, documentation và profile cho từng môi trường.

Cấu trúc gợi ý:

~~~text
com.example.redis
  ├── RedisClientProperties.java   # host, port, username, TLS, timeout...
  ├── ManualRedisConfig.java       # factory, named templates
  ├── ProductSnapshot.java         # model lưu Redis
  ├── ProductSnapshotService.java  # business operations
  └── ViewCounterService.java      # StringRedisTemplate
~~~

Đảm bảo phần khởi tạo connection được tách khỏi business logic, dễ thay địa chỉ/mật khẩu mà không sửa service. Khi thêm một kiểu value mới có schema độc lập, có thể tạo named template khác dùng chung factory.

Một số nguyên tắc thực hành:

- **Cấu hình theo môi trường:** local có thể standalone không mật khẩu và bind loopback; staging/production dùng endpoint, ACL/TLS và secret phù hợp.
- **Đặt tên bean rõ ràng:** `productRedisTemplate`, `sessionRedisTemplate`, `metricsRedisTemplate` nếu thực sự cần tách loại dữ liệu.
- **Chỉ định serializer:** key và hash key thường là String; value cần schema nhất quán, được version hóa khi cần.
- **Dùng một factory phù hợp cho từng topology:** không giả định mã dành cho standalone sẽ đúng cho Cluster/Sentinel.
- **Quản lý timeout/retry:** cân nhắc đặc tính idempotent của lệnh và tác động khi Redis gián đoạn.
- **Quản lý key và TTL:** dữ liệu tạm nên có TTL; dữ liệu quan trọng cần yêu cầu persistence rõ ràng.
- **Theo dõi kết nối và memory:** cấu hình ban đầu cần được đánh giá bằng số liệu và điều kiện tải thực tế.

## 15. Bài thực hành tổng hợp

**Yêu cầu:** Tự cấu hình một Spring Boot application kết nối Redis local, lưu snapshot sản phẩm dưới dạng JSON, tăng bộ đếm lượt xem bằng StringRedisTemplate, sau đó kiểm chứng rằng hai nhóm dữ liệu có thể được đọc riêng rẽ.

Các bước:

1. Chạy Redis local bằng Docker, xác nhận `PING` trả `PONG`.
2. Thêm dependency của Spring Data Redis và cấu hình `app.redis.*`.
3. Viết `ManualRedisConfig` gồm `redisConnectionFactory`, `productRedisTemplate`, `stringRedisTemplate`.
4. Khởi tạo `ProductSnapshot` và inject `productRedisTemplate` vào service bằng `@Qualifier`.
5. Lưu sản phẩm ID 42 với TTL 10 phút, đọc lại và xóa thử.
6. Tăng lượt xem sản phẩm ID 42 ba lần, xác nhận key `demo:product:views:42` chứa số tăng dần.
7. Dùng CLI xem `GET`, `TTL` và `TYPE` cho mỗi key; xác nhận snapshot ở dạng JSON, bộ đếm ở dạng chuỗi số.
8. Thử đổi prefix key hoặc database trong môi trường test và giải thích vì sao key cũ không còn được nhìn thấy.
9. Thử kết nối tới port sai để quan sát loại lỗi; khôi phục cấu hình đúng và chạy lại.
10. Viết lại bằng lời vai trò của factory, template, serializer, service và Redis server.

### Kết quả cần đạt

- Spring context tạo được các bean thủ công và service inject được đúng template.
- Thao tác lưu/đọc object sử dụng JSON serializer tường minh; key xuất hiện bằng tên dễ đọc.
- Lệnh tăng bộ đếm hoạt động qua `StringRedisTemplate`, không cần thao tác cộng ở Java.
- Có thể thay host/port/credentials/timeout theo cấu hình môi trường mà không sửa business service.
- Phân biệt được lỗi kết nối với lỗi serializer/key/database bằng các kiểm tra thực tế.

## 16. Câu hỏi tự ôn

1. Vì sao `RedisConnectionFactory` nên là bean dùng chung thay vì được khởi tạo trong mỗi request?
2. `LettuceConnectionFactory` và `RedisTemplate` khác nhau ở trách nhiệm nào?
3. Tại sao `RedisTemplate<String, ProductSnapshot>` vẫn cần `setKeySerializer(...)` và `setValueSerializer(...)`?
4. Khi nào bạn chọn `StringRedisTemplate` thay vì một template lưu object JSON?
5. Nếu cả hai template sử dụng cùng một Redis server, điều gì có thể xảy ra khi chúng ghi một key chung nhưng dùng serializer khác nhau?
6. Vì sao khai báo `productRedisTemplate` không bảo đảm Spring Cache dùng serializer này?
7. `@Qualifier` giúp giải quyết vấn đề gì khi có nhiều factory/template?
8. Chọn `RedisStandaloneConfiguration`, `RedisSentinelConfiguration` và `RedisClusterConfiguration` dựa trên yếu tố nào?
9. Một lệnh Redis bị client timeout có thể đã thực thi chưa? Vì sao điều đó ảnh hưởng đến retry `INCR`?
10. Nếu Redis dùng ACL/TLS, những thông tin nào phải được lấy từ cấu hình an toàn và tránh ghi cứng vào mã?

**Điểm cốt lõi:** `RedisConnectionFactory` phụ trách kết nối; `RedisTemplate` phụ trách giao diện thao tác và chuyển đổi dữ liệu; service phụ trách quy tắc nghiệp vụ. Cấu hình thủ công chỉ đáng tin cậy khi **factory trỏ đúng Redis, bean được inject đúng, serializer của từng key nhất quán và hành vi lỗi được thiết kế rõ ràng**.
