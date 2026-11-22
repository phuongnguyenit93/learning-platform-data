# Kiểm tra kết nối bằng thao tác ghi–đọc đơn giản

Sau khi thêm Spring Data Redis và cấu hình địa chỉ Redis Server, bước đầu tiên nên làm là **xác nhận ứng dụng Spring Boot thực sự có thể ghi một giá trị vào Redis rồi đọc lại đúng giá trị đó**. Một lần kiểm tra ghi–đọc (write–read smoke test) giúp phát hiện sớm các lỗi kết nối, cấu hình và quyền truy cập trước khi triển khai logic cache, session, token hoặc lưu trữ dữ liệu phức tạp hơn.

Ý tưởng cốt lõi rất đơn giản:

1. Ứng dụng tạo một **key kiểm tra riêng**, tránh trùng với dữ liệu thật.
2. Sử dụng **StringRedisTemplate** để ghi một giá trị bằng lệnh tương đương **SET**.
3. Đọc chính key đó bằng lệnh tương đương **GET**.
4. So sánh giá trị đọc được với giá trị đã ghi; nếu giống nhau thì thao tác ghi–đọc thành công.
5. Xóa key kiểm tra sau khi hoàn tất và đặt **TTL ngắn** phòng trường hợp ứng dụng bị ngắt trước khi dọn dẹp.

Bài học này sử dụng Spring Boot 3.x, Spring Data Redis và Redis Server chạy cục bộ làm ví dụ. Cách tư duy tương tự áp dụng cho Redis ở Docker Compose, máy chủ riêng hoặc dịch vụ Redis được quản lý.

## 1. Kiểm tra ghi–đọc xác nhận được điều gì?

Khi một lệnh **SET** rồi **GET** thành công từ ứng dụng, điều đó cho thấy tại thời điểm kiểm tra:

- Ứng dụng đã tạo được đường kết nối qua Spring Data Redis và Redis driver đến một Redis endpoint.
- Redis Server nhận và xử lý được lệnh ghi cho key kiểm tra.
- Ứng dụng có thể đọc lại key đó và nhận đúng giá trị mong đợi.
- Cấu hình mã hóa key/value đã sử dụng trong lượt ghi–đọc này hoạt động thống nhất.

Đây là phép thử **đầu-cuối cho một thao tác nhỏ**, mạnh hơn việc chỉ nhìn thấy ứng dụng Spring Boot khởi động thành công.

Tuy nhiên, một lần SET/GET thành công **không chứng minh** toàn bộ hệ thống Redis đã sẵn sàng cho production. Nó chưa kiểm tra tính bền dữ liệu sau restart, failover, replication, Redis Cluster, độ trễ dưới tải lớn, quyền đối với mọi loại lệnh hay khả năng chạy ổn định dài hạn. Các yêu cầu đó cần kiểm thử và quan sát riêng.

### PING và SET/GET khác nhau

| Phép kiểm tra | Chứng minh chủ yếu | Điều chưa được chứng minh |
|---|---|---|
| **PING** qua redis-cli hoặc driver | Redis endpoint phản hồi một lệnh đơn giản | Ứng dụng có thể SET, GET với key mong muốn hoặc có đủ quyền ghi |
| **SET** từ ứng dụng Spring | Đường kết nối và thao tác ghi hoạt động | Giá trị có đọc lại đúng không |
| **SET rồi GET và so sánh** | Ghi–đọc khép kín với cấu hình client/serializer đang dùng | Tính bền, tải lớn, failover hoặc mọi tính năng Redis khác |
| **SET với TTL, GET rồi DEL** | Ghi–đọc hoạt động và có chiến lược dọn key thử nghiệm | Không đồng nghĩa dữ liệu nghiệp vụ và toàn bộ Redis đều khỏe |

Ví dụ, **redis-cli PING** có thể trả **PONG** nhưng ứng dụng vẫn gặp **NOAUTH**, **WRONGPASS**, kết nối nhầm máy chủ, hoặc người dùng Redis chỉ có quyền đọc. Vì vậy, hãy kiểm tra từ **chính ứng dụng Spring Boot** khi mục tiêu là xác nhận cấu hình của ứng dụng.

## 2. Chuẩn bị Redis Server đang chạy

Ứng dụng Spring Data Redis chỉ là **client**; nó không tự tạo một Redis Server khi thêm starter. Trước khi viết mã kiểm tra, cần có Redis endpoint có thể truy cập.

### 2.1. Ví dụ khởi chạy Redis bằng Docker

Nếu đã có Docker, có thể chạy một Redis Server dành cho môi trường học tập:

~~~bash
docker run -d \
  --name redis-spring-demo \
  -p 127.0.0.1:6379:6379 \
  redis:7-alpine
~~~

Lệnh này ánh xạ cổng Redis của container ra cổng **6379 trên loopback của máy host**, phù hợp với ví dụ ứng dụng Spring Boot chạy trực tiếp trên cùng máy. Nếu Redis Server đã chạy sẵn ở cổng đó, sử dụng instance hiện có hoặc đổi cổng ánh xạ; không chạy hai server tranh cùng một cổng.

Kiểm tra Redis Server bên trong container:

~~~bash
docker exec redis-spring-demo redis-cli PING
~~~

Kết quả mong đợi:

~~~text
PONG
~~~

**PONG ở bước này chỉ kiểm tra Redis trong container**. Bước ghi–đọc từ Spring Boot ở các phần tiếp theo mới kiểm tra toàn bộ đường kết nối từ ứng dụng.

Nếu có công cụ **redis-cli** trên host, có thể kiểm tra thêm đường truy cập qua cổng đã publish:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 PING
~~~

Khi học xong, có thể dừng/xóa container thử nghiệm nếu không còn cần:

~~~bash
docker stop redis-spring-demo
docker rm redis-spring-demo
~~~

### 2.2. Lưu ý về địa chỉ localhost

**localhost chỉ chính môi trường đang chạy chương trình client**:

| Nơi Spring Boot đang chạy | Redis Server ở đâu? | Host cấu hình trong ứng dụng |
|---|---|---|
| Spring Boot trên máy host, Redis publish cổng 6379 từ Docker lên host | Cùng máy host qua port mapping | **localhost** hoặc **127.0.0.1** |
| Spring Boot và Redis ở hai container cùng mạng Docker Compose | Container Redis có service name redis | **redis** (tên service Compose) |
| Spring Boot trên máy phát triển, Redis ở máy chủ khác | Server riêng | DNS/IP của máy Redis |
| Spring Boot trên cloud, Redis managed | Dịch vụ Redis được quản lý | Endpoint do nhà cung cấp cấp |

Khi Spring Boot chạy **bên trong container**, localhost trỏ vào container của Spring Boot. Nếu Redis nằm ở container khác, cấu hình localhost thường gây lỗi kết nối. Hai container nên nói chuyện qua tên service/hostname và network thích hợp.

## 3. Thêm Spring Data Redis vào ứng dụng

Trong Spring Boot sử dụng Gradle, khai báo starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Starter cung cấp hạ tầng Spring Data Redis và thường dùng **Lettuce** làm Redis driver mặc định. Khi Spring Boot auto-configuration thỏa điều kiện, ứng dụng có thể inject **StringRedisTemplate** và **RedisConnectionFactory**.

Đường đi của một thao tác:

~~~text
Spring Boot Service / ApplicationRunner
                 |
                 v
         StringRedisTemplate
                 |
                 v
       RedisConnectionFactory
                 |
                 v
           RedisConnection
                 |
                 v
       Lettuce (Redis driver)
                 |
                 v
         Redis Server :6379
~~~

Với bài kiểm tra đơn giản, **StringRedisTemplate** là lựa chọn thuận tiện: cả key lẫn value đều là chuỗi, nên ít gặp nhầm lẫn do serializer của đối tượng Java. **StringRedisTemplate không tự lưu dữ liệu**; nó dùng connection factory và driver để gửi lệnh tới Redis Server.

## 4. Cấu hình kết nối và bật phép kiểm tra khi cần

Ví dụ cấu hình trong **src/main/resources/application.yml**:

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      timeout: 2s

app:
  redis:
    smoke-test:
      enabled: ${REDIS_SMOKE_TEST_ENABLED:false}
~~~

Ý nghĩa:

- **spring.data.redis.host** và **port**: Redis endpoint mà ứng dụng sẽ kết nối.
- **timeout: 2s**: cấu hình timeout phù hợp cho ví dụ local; mạng cloud hoặc hệ thống thực tế cần điều chỉnh theo yêu cầu.
- **REDIS_HOST** và **REDIS_PORT**: cho phép thay địa chỉ Redis bằng biến môi trường mà không sửa mã nguồn.
- **app.redis.smoke-test.enabled**: cờ tùy chọn của ví dụ, mặc định **false**, để chỉ chạy bài kiểm tra khi chủ động bật.

Trong Spring Boot 3.x, prefix cấu hình Redis được dùng ở đây là **spring.data.redis**. Nếu đang làm việc với phiên bản Spring Boot khác, cần đối chiếu thuộc tính theo chính phiên bản đang sử dụng.

Cờ **app.redis.smoke-test.enabled** không phải thuộc tính Redis chuẩn của Spring Boot; đây là khóa do bài học đặt ra để điều khiển bean kiểm tra riêng.

Với Redis Server yêu cầu xác thực hoặc TLS, cần thêm cấu hình tương ứng như username/password và SSL theo môi trường. Không hardcode mật khẩu vào mã Java hoặc commit secret thật vào repository.

## 5. Viết chương trình kiểm tra SET → GET bằng StringRedisTemplate

Ta triển khai một bean **ApplicationRunner**. Bean này chạy một lần sau khi Spring Boot tạo xong application context và nhận các tham số chạy ứng dụng. Nhờ **@ConditionalOnProperty**, nó chỉ được tạo khi bật cờ smoke test.

Tạo file Java trong package thuộc ứng dụng, ví dụ **RedisSmokeTestConfiguration.java**:

~~~java
package com.example.redislearning;

import java.time.Duration;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class RedisSmokeTestConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(RedisSmokeTestConfiguration.class);

    @Bean
    @ConditionalOnProperty(
            name = "app.redis.smoke-test.enabled",
            havingValue = "true"
    )
    ApplicationRunner redisWriteReadSmokeTest(StringRedisTemplate redis) {
        return args -> {
            String key = "smoke:redis:" + UUID.randomUUID();
            String expected = "spring-data-redis-ok";
            boolean writeCompleted = false;

            try {
                // SET key value EX 60: ghi dữ liệu có TTL 60 giây.
                redis.opsForValue().set(
                        key,
                        expected,
                        Duration.ofSeconds(60)
                );
                writeCompleted = true;

                // GET key: đọc lại dữ liệu qua chính ứng dụng Spring.
                String actual = redis.opsForValue().get(key);

                if (!expected.equals(actual)) {
                    throw new IllegalStateException(
                            "Redis write/read mismatch for key: " + key
                                    + ", actual=" + actual
                    );
                }

                log.info("REDIS_SMOKE_OK: SET/GET succeeded, key={}", key);
            } finally {
                if (writeCompleted) {
                    try {
                        // Dọn key thử nghiệm; TTL vẫn bảo vệ khi cleanup lỗi.
                        redis.delete(key);
                    } catch (RuntimeException cleanupFailure) {
                        log.warn(
                                "Could not delete temporary Redis key: {}",
                                key,
                                cleanupFailure
                        );
                    }
                }
            }
        };
    }
}
~~~

### 5.1. Tại sao dùng key có UUID?

~~~java
String key = "smoke:redis:" + UUID.randomUUID();
~~~

Mỗi lần kiểm tra có một key riêng, chẳng hạn:

~~~text
smoke:redis:9be4fe07-88bb-4773-8a68-31dd78b0ef3d
~~~

Tiền tố **smoke:redis:** nhận diện mục đích kiểm tra. UUID giảm nguy cơ:

- Ghi đè key nghiệp vụ đang có.
- Hai instance Spring Boot đồng thời sử dụng cùng key và gây kết quả không ổn định.
- Đọc nhầm giá trị được lưu từ một lần kiểm tra trước đó.

Trong hệ thống dùng Redis chung, nên sử dụng namespace dành riêng cho ứng dụng/môi trường. Nếu Redis có ACL giới hạn theo mẫu key, namespace smoke test phải nằm trong phạm vi key mà client được phép truy cập.

### 5.2. Tại sao SET phải có TTL?

~~~java
redis.opsForValue().set(
        key,
        expected,
        Duration.ofSeconds(60)
);
~~~

Spring Data Redis sẽ yêu cầu Redis Server thực hiện thao tác tương đương:

~~~text
SET smoke:redis:<id> spring-data-redis-ok EX 60
~~~

**EX 60** đặt thời gian hết hạn 60 giây cùng lúc với thao tác ghi. Nếu chương trình dừng đột ngột, connection gặp sự cố hoặc không chạy được phần dọn dẹp, key kiểm tra vẫn có thời hạn.

Đây là lựa chọn an toàn hơn việc ghi key thử nghiệm không có TTL rồi hy vọng lúc nào cũng xóa được. Trong ví dụ, **60 giây** đủ cho thao tác local bình thường; ứng dụng thực tế cần chọn TTL theo đặc điểm mạng và độ trễ.

### 5.3. Vì sao phải so sánh giá trị, không chỉ gọi GET?

~~~java
String actual = redis.opsForValue().get(key);

if (!expected.equals(actual)) {
    throw new IllegalStateException(
            "Redis write/read mismatch for key: " + key
                    + ", actual=" + actual
    );
}
~~~

**GET** có thể trả **null** nếu key không tồn tại hoặc đã hết hạn. Kết quả chỉ được xem là thành công khi **actual** đúng bằng **expected**. Cách viết **expected.equals(actual)** còn tránh **NullPointerException** khi actual là null.

Không nhất thiết phải log toàn bộ value trong ứng dụng thật. Với dữ liệu nhạy cảm như OTP, token hoặc thông tin phiên, chỉ nên log trạng thái kiểm tra và mã định danh không nhạy cảm.

### 5.4. Vì sao luôn giải phóng key?

Khối **finally** chạy sau nhánh thành công hoặc nhánh ném exception. Nếu thao tác ghi đã trả về thành công, chương trình cố gắng xóa key bằng **DEL**. Việc dọn dẹp được bọc trong try/catch riêng để lỗi dọn dẹp không che mất lỗi chính của thao tác ghi–đọc.

Nếu SET đã được Redis Server thực thi nhưng kết nối bị ngắt trước khi client nhận phản hồi, **writeCompleted** có thể vẫn false. Vì key đã được ghi cùng TTL, dữ liệu thử nghiệm vẫn sẽ hết hạn thay vì tồn tại vô thời hạn.

Lệnh xóa có thể bị từ chối do Redis ACL. Điều đó không phủ nhận kết quả SET/GET, nhưng cảnh báo dọn dẹp cần được xử lý theo quyền và chính sách vận hành; TTL là cơ chế dự phòng.

## 6. Chạy bài kiểm tra và đọc kết quả

Điều kiện trước khi chạy:

1. Redis Server đang chạy và có thể truy cập từ môi trường Spring Boot.
2. Ứng dụng có dependency **spring-boot-starter-data-redis**.
3. **application.yml** chứa cấu hình kết nối đúng và cờ smoke test.
4. Class **RedisSmokeTestConfiguration** thuộc package được Spring Boot component scan.

Có thể bật cờ trong cấu hình chạy của IDE bằng một trong hai cách:

- Thêm program argument: **--app.redis.smoke-test.enabled=true**.
- Hoặc đặt biến môi trường **REDIS_SMOKE_TEST_ENABLED=true**.

Nếu đã đóng gói ứng dụng thành JAR executable, ví dụ:

~~~bash
java -jar app.jar --app.redis.smoke-test.enabled=true
~~~

Tên **app.jar** chỉ là ví dụ, cần thay bằng đường dẫn JAR thực tế. Khi chạy thành công, log sẽ có thông báo tương tự:

~~~text
INFO  ... RedisSmokeTestConfiguration :
REDIS_SMOKE_OK: SET/GET succeeded, key=smoke:redis:9be4fe07-...
~~~

Chuỗi UUID thay đổi mỗi lượt. Thông điệp thành công chỉ xuất hiện **sau khi SET, GET và phép so sánh đã chạy xong**. Nếu Redis không truy cập được hoặc kết quả đọc khác giá trị mong đợi, runner sẽ ném exception và Spring Boot báo lỗi khi khởi động.

### Cờ mặc định false có tác dụng gì?

Nếu không bật cờ, **@ConditionalOnProperty** không tạo bean ApplicationRunner kiểm tra. Điều này tránh việc mỗi lần ứng dụng production khởi động đều tạo lệnh ghi thử nghiệm ngoài ý muốn.

Một smoke test **cố tình làm lỗi khởi động** khi Redis ghi–đọc thất bại có thể hữu ích ở môi trường học tập, kiểm thử hoặc khi Redis là dependency bắt buộc. Với hệ thống production, quyết định có khóa việc khởi động vì Redis tạm thời không sẵn sàng cần được đưa ra theo mức phụ thuộc thực tế và chiến lược health/readiness; không nên vô tình dùng bài kiểm tra demo làm chính sách availability.

## 7. Diễn giải luồng SET và GET trong Spring Data Redis

Khi runner thực hiện:

~~~java
redis.opsForValue().set(key, expected, Duration.ofSeconds(60));
String actual = redis.opsForValue().get(key);
~~~

Luồng xử lý có thể hình dung như sau:

~~~text
  ApplicationRunner
         |
         | set(key, value, 60s)
         v
  StringRedisTemplate
         |
         | chuyển String thành bytes
         | lấy RedisConnection từ RedisConnectionFactory
         v
  Lettuce / Jedis
         |
         | SET key value EX 60
         v
     Redis Server
         |
         | lưu key và TTL; trả phản hồi
         v
  Spring Data Redis
         |
         | get(key)
         v
     Redis Server
         |
         | trả value (hoặc nil nếu không có key)
         v
  StringRedisTemplate
         |
         | chuyển bytes thành String
         v
  ApplicationRunner
         |
         | expected.equals(actual)?
         +---- Có ---> ghi log REDIS_SMOKE_OK
         |
         '---- Không -> ném lỗi, kiểm tra nguyên nhân
~~~

Trong mô hình này:

- **StringRedisTemplate** cung cấp API cho Java và xử lý serialization chuỗi.
- **RedisConnectionFactory** cấp RedisConnection theo cấu hình ứng dụng.
- **RedisConnection và driver** đưa lệnh/nhận phản hồi qua kết nối.
- **Redis Server** thực thi SET/GET/DEL và quản lý TTL.

Việc RedisTemplate hoạt động không chứng minh RedisConnectionFactory tự lưu dữ liệu: nơi chứa dữ liệu vẫn là Redis Server.

## 8. Một phiên bản tối giản để thử trong service

Nếu đã có một service hoặc một bài lab chủ động gọi hàm thử nghiệm, có thể rút gọn logic:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SimpleRedisProbe {

    private final StringRedisTemplate redis;

    public SimpleRedisProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean checkWriteRead() {
        String key = "smoke:redis:" + UUID.randomUUID();
        String expected = "hello-redis";

        try {
            redis.opsForValue().set(
                    key, expected, Duration.ofSeconds(30));
            String actual = redis.opsForValue().get(key);

            return expected.equals(actual);
        } finally {
            // Nếu không xóa được, Redis sẽ tự hết hạn key theo TTL.
            redis.delete(key);
        }
    }
}
~~~

Gọi **checkWriteRead()** từ một bài lab hoặc một đoạn mã kiểm thử đã được kiểm soát sẽ trả true nếu vòng ghi–đọc thành công, trả false nếu giá trị sai/không tồn tại, và có thể ném **DataAccessException** hoặc exception liên quan nếu không thể kết nối/thực thi lệnh. **Không nên expose hàm này thành endpoint công khai không bảo vệ**, vì mỗi yêu cầu sẽ tạo thao tác ghi lên Redis.

Đây là bản ngắn để nhận diện ý chính. Khối **finally** ở đây đơn giản nên nếu dọn dẹp ném lỗi thì exception dọn dẹp có thể thay đổi kết quả hoặc che lỗi trước đó; bản ApplicationRunner ở phần 5 đã tách riêng xử lý cleanup để tránh điều đó.

## 9. Kiểm tra bằng redis-cli: đối chiếu từ phía Redis Server

Để hiểu hành vi của server độc lập với Spring, thử các lệnh trên một key thủ công:

~~~bash
docker exec redis-spring-demo redis-cli SET smoke:manual hello EX 60
docker exec redis-spring-demo redis-cli GET smoke:manual
docker exec redis-spring-demo redis-cli TTL smoke:manual
docker exec redis-spring-demo redis-cli DEL smoke:manual
~~~

Kết quả điển hình:

~~~text
OK
"hello"
(integer) 58
(integer) 1
~~~

Giá trị TTL chỉ mang tính minh họa vì nó giảm theo thời gian; có thể thấy các số khác. **DEL** trả 1 nếu đã xóa một key tồn tại, trả 0 nếu key không tồn tại tại thời điểm xóa.

Đây là bài thử phía Redis qua **redis-cli**. Nếu nó thành công nhưng Spring Boot thất bại, hãy tập trung vào địa chỉ Redis nhìn từ ứng dụng, biến môi trường, xác thực/TLS, quyền của Redis user, network giữa hai môi trường và cách Spring cấu hình connection factory.

Ngược lại, nếu cả redis-cli và ứng dụng đều không kết nối được từ cùng vị trí mạng, cần kiểm tra Redis Server và network trước.

Lưu ý rằng code ApplicationRunner dùng key ngẫu nhiên và xóa ngay sau khi đọc thành công; vì thế thường **không thể bắt gặp key đó bằng redis-cli sau khi log thành công**. Điều đó là hành vi mong muốn của smoke test, không phải bằng chứng SET thất bại.

## 10. Tự động hóa thành integration test

Ngoài kiểm tra lúc khởi động, có thể viết một **integration test** nhằm phát hiện lỗi kết nối trong môi trường kiểm thử. Mã dưới đây giả định đang có Redis Server thử nghiệm, cấu hình trong profile test trỏ tới nó, và dự án đã có **spring-boot-starter-test**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class RedisWriteReadIntegrationTest {

    @Autowired
    private StringRedisTemplate redis;

    @Test
    void shouldWriteAndReadTheSameValue() {
        String key = "test:redis:" + UUID.randomUUID();
        String expected = "round-trip-ok";

        try {
            redis.opsForValue().set(
                    key, expected, Duration.ofSeconds(60));

            String actual = redis.opsForValue().get(key);

            assertEquals(expected, actual);
        } finally {
            redis.delete(key);
        }
    }
}
~~~

Phép thử này tương tác với **Redis thật** và không phải unit test mock. Nó sẽ thất bại nếu không có Redis endpoint phù hợp. Để chạy đáng tin cậy trong CI, nên cung cấp Redis test riêng (ví dụ container test), cấu hình host/port cho test và không phụ thuộc Redis production hoặc dữ liệu chung của người dùng.

Khác biệt giữa hai cách:

| Cách kiểm tra | Thời điểm | Kết quả |
|---|---|---|
| **ApplicationRunner** có cờ bật | Khi ứng dụng khởi động ở môi trường được chọn | Log thành công hoặc exception làm thất bại khởi động |
| **JUnit integration test** | Khi chạy bộ test | Assertion pass/fail trong kết quả test |
| **redis-cli SET/GET** | Khi người dùng thực thi CLI | Chứng minh endpoint được CLI truy cập, chưa chắc phản ánh cấu hình client Spring |

Chọn một hoặc kết hợp tùy quy trình phát triển. Không cần chạy cả ba cách trong mọi request của ứng dụng.

## 11. Chẩn đoán lỗi theo triệu chứng

### 11.1. Connection refused hoặc không thể kết nối

Ví dụ log thường gặp có thể chứa **RedisConnectionFailureException**, **Connection refused**, **Unable to connect** hoặc exception tương đương.

Kiểm tra theo thứ tự:

1. Redis Server có đang chạy không? Lệnh **docker ps** có thấy container không?
2. Redis có lắng nghe đúng host/port và port mapping không?
3. Ứng dụng chạy trên host hay trong container? Giá trị localhost đang chỉ về đâu?
4. DNS, firewall, Docker network hoặc security group có chặn đường kết nối không?
5. Cấu hình timeout có phù hợp với môi trường không?

Trong Docker Compose, nếu Spring Boot và Redis là hai service cùng mạng, đặt **REDIS_HOST=redis** (giả sử tên service Redis là redis), không dùng localhost của container Spring Boot.

### 11.2. Redis yêu cầu xác thực hoặc TLS

Nếu log chứa **NOAUTH**, **WRONGPASS** hoặc lỗi TLS handshake, xem lại cấu hình kết nối và quyền truy cập:

- Redis ACL có yêu cầu username và password không?
- Spring Boot có nhận đúng biến môi trường hoặc secret không?
- Server yêu cầu TLS nhưng client lại kết nối TCP không mã hóa, hoặc ngược lại?
- Có dùng endpoint và port đúng loại kết nối của nhà cung cấp không?

Với Redis user có quyền hạn chế, cần cho phép các lệnh cần thiết như **SET** và **GET** trong namespace smoke test. **DEL** chỉ phục vụ dọn dẹp và có thể được xử lý riêng nếu ACL không cho phép; TTL vẫn giới hạn thời gian tồn tại của key.

### 11.3. PONG nhưng SET thất bại

PING và thao tác ghi có yêu cầu khác nhau. Các nguyên nhân có thể gồm:

- Redis user được phép PING nhưng bị từ chối SET hoặc không được phép truy cập mẫu key này.
- Ứng dụng đang kết nối vào Redis replica read-only hoặc endpoint không nhận ghi.
- Redis Server đang có trạng thái vận hành không cho phép thao tác ghi.
- PING được gửi từ **redis-cli với một cấu hình khác**, còn ứng dụng dùng host, account hoặc TLS khác.

Vì vậy, PONG không được dùng thay thế phép kiểm tra ghi–đọc.

### 11.4. SET không ném lỗi nhưng GET trả null

Các khả năng cần xem xét:

- Key đã hết hạn trước khi GET hoặc bị xóa bởi tác vụ khác.
- Key bị eviction do chính sách bộ nhớ và áp lực tài nguyên.
- Hai lệnh thực tế không dùng cùng endpoint/database/namespace như dự kiến.
- Client dùng serializer/encoding key khác nhau ở hai đường gọi.
- Ứng dụng dùng đọc từ replica và dữ liệu chưa được đồng bộ theo kỳ vọng của kiến trúc.

Với ví dụ **StringRedisTemplate** dùng cùng bean, cùng key và GET ngay sau SET, lỗi này là dấu hiệu cần điều tra. TTL ngắn giúp dọn dữ liệu, nhưng nếu môi trường rất chậm có thể cần TTL dài hơn.

### 11.5. GET trả về dữ liệu lạ

**StringRedisTemplate** sử dụng serializer chuỗi cho key/value. Nếu một service khác ghi cùng key bằng RedisTemplate với serializer khác, dữ liệu đọc ra có thể khác mong muốn hoặc không thể diễn giải như chuỗi.

Đối với kiểm tra ghi–đọc, dùng **một StringRedisTemplate cho cả SET và GET** để giảm biến số. Khi triển khai dữ liệu thật, các service phải thống nhất định dạng key/value và chính sách serialize.

### 11.6. Không tìm thấy bean StringRedisTemplate

Nếu Spring báo không inject được StringRedisTemplate, kiểm tra:

- Dependency **spring-boot-starter-data-redis** có trong module thực sự đang chạy không?
- Spring Boot auto-configuration có bị loại bỏ hoặc tùy chỉnh không?
- Có bean connection factory hợp lệ không?
- Class đang inject nằm trong application context và có được Spring quản lý không?

Đây là lỗi khởi tạo bean/ cấu hình Spring, khác với trường hợp đã có template nhưng không kết nối được Redis Server.

### 11.7. Test vẫn pass dù kết nối nhầm Redis

Một endpoint Redis **khác** cũng có thể đáp ứng SET/GET. Phép thử thành công chỉ xác nhận truy cập đến endpoint đang được cấu hình; nó không tự xác minh danh tính môi trường mong muốn.

Trước khi chạy ở môi trường dùng chung, cần kiểm tra giá trị host, profile, secret, Redis database/namespace và network mapping để tránh ghi nhầm vào Redis production.

## 12. Những vấn đề kỹ thuật cần phân biệt

### 12.1. Kết nối thực sự thường xảy ra khi thực hiện command

Trong nhiều cấu hình Spring Boot, ứng dụng có thể tạo thành công bean RedisTemplate và RedisConnectionFactory dù Redis Server chưa sẵn sàng. Driver có thể chỉ mở kết nối khi được yêu cầu, hoặc kết nối bị mất sau khởi động.

Do đó, **application context khởi động thành công không tương đương SET/GET đã được kiểm chứng**. Bài smoke test cố tình thực hiện lệnh để xác nhận đường kết nối đang hoạt động.

### 12.2. Redis connection và Redis data là hai vấn đề khác nhau

Factory/driver chịu trách nhiệm giao tiếp. Redis Server lưu dữ liệu. Khi đọc thấy dữ liệu sai, cần xác định:

- Client có kết nối đúng Redis endpoint không?
- Key đã được mã hóa đúng và có nằm trong database/namespace tương ứng không?
- Có TTL, eviction, xóa key hay luồng ghi khác tác động không?

Đổi Redis driver hoặc tăng connection timeout không tự sửa được lỗi logic key/value.

### 12.3. Không dùng key kiểm tra cố định của ứng dụng thật

Tránh đặt key như **user:1**, **session:current** hoặc **cart:123** trong smoke test. Đó có thể là key nghiệp vụ và ghi đè sẽ gây hậu quả không mong muốn.

Tiền tố riêng kết hợp UUID và TTL giúp bài thử độc lập hơn, kể cả khi nhiều người chạy song song. Tuy nhiên, trong production vẫn nên xem xét ACL, prefix và traffic trước khi bật việc ghi thử nghiệm.

### 12.4. Kiểm tra một lần khác với theo dõi liên tục

Một smoke test chạy lúc startup trả lời câu hỏi: **“Ứng dụng có ghi–đọc được Redis vào thời điểm này không?”**

Nó không tự theo dõi sự cố phát sinh sau khi ứng dụng đã chạy. Muốn quan sát liên tục, có thể sử dụng health/readiness checks, metrics, logs và cảnh báo phù hợp. Health check kiểu PING thường nhẹ hơn kiểm tra SET/GET định kỳ; việc ghi dữ liệu kiểm tra liên tục cần được thiết kế có chủ đích để tránh tạo tải và key thừa.

### 12.5. Sự khác biệt giữa việc ném exception và trả false

Xét hàm kiểm tra:

~~~java
String actual = redis.opsForValue().get(key);
return expected.equals(actual);
~~~

- **true**: GET trả chính xác giá trị mong đợi.
- **false**: GET trả null hoặc chuỗi khác, trong khi lời gọi không ném lỗi.
- **exception**: thao tác kết nối, ghi hoặc đọc không hoàn tất theo cách bình thường.

Ở một smoke test dùng làm điều kiện bắt buộc, cả false lẫn exception đều nên được xem là **không đạt**; đừng chỉ bắt mọi exception rồi trả true hoặc ghi log “Redis connected” khi chưa có kết quả đọc.

## 13. Bài thực hành mở rộng

Sau khi kiểm tra SET/GET thành công, có thể thử một vài thay đổi có kiểm soát:

### Bài tập A — Xác nhận thời gian hết hạn

Ngay sau khi SET với TTL 60 giây, có thể hỏi Redis về thời gian còn lại:

~~~java
Long remainingSeconds = redis.getExpire(key);
System.out.println("Remaining TTL (seconds): " + remainingSeconds);
~~~

Kết quả thường là số giây dương gần 60. TTL giảm theo thời gian; tùy lệnh và trạng thái key, các giá trị đặc biệt có thể biểu thị key không tồn tại hoặc không có thời hạn. **Không so sánh cứng rằng TTL phải bằng đúng 60** do có thời gian trôi qua giữa SET và lệnh kiểm tra.

### Bài tập B — Kiểm tra lỗi kết nối có chủ đích

Trong môi trường thử nghiệm riêng, thay cấu hình host/port thành một địa chỉ không có Redis Server, rồi bật smoke test. Quan sát exception của Spring Data Redis và phân biệt với lỗi kiểu dữ liệu. Sau đó khôi phục cấu hình đúng.

Mục đích là nhận diện lỗi kết nối từ ứng dụng; không thực hiện thao tác ngắt Redis trên hệ thống dùng chung chỉ để thử.

### Bài tập C — Kiểm tra namespace

Thay **smoke:redis:** bằng một prefix dành riêng cho môi trường, chẳng hạn **dev:inventory:smoke:**, và lặp lại bài thử. Khi có nhiều ứng dụng dùng cùng Redis Server, một quy ước key nhất quán giúp chẩn đoán và tránh va chạm.

### Bài tập D — So sánh PING và SET/GET

Gửi PING bằng redis-cli trước khi chạy ứng dụng. Sau đó bật smoke test của Spring và quan sát cả hai kết quả. Tự trả lời: nếu PONG xuất hiện nhưng ứng dụng không thể SET, lỗi có thể ở đâu?

## 14. Câu hỏi củng cố

**1. Vì sao chỉ nhìn thấy Spring Boot khởi động không đủ để kết luận Redis kết nối tốt?**

Vì bean Redis có thể được tạo mà chưa thực hiện network command. SET/GET từ ứng dụng mới chứng minh đường truy cập cho thao tác đó tại thời điểm thử.

**2. Vì sao dùng StringRedisTemplate cho phép thử đầu tiên?**

Vì nó thao tác key/value chuỗi bằng API đơn giản, có serializer nhất quán và được Spring quản lý connection. Kết quả dễ hiểu và có thể đối chiếu với redis-cli.

**3. GET trả null thì có nên log thành công không?**

Không. Nếu expected là một chuỗi cụ thể nhưng actual là null, phép kiểm tra không đạt, dù phương thức GET không ném exception.

**4. Vì sao cần UUID và TTL?**

UUID giúp tránh trùng key giữa các lượt chạy. TTL giới hạn vòng đời dữ liệu kiểm tra nếu code không dọn dẹp được.

**5. Nếu PING từ container Redis thành công nhưng SET/GET trong Spring thất bại thì tìm lỗi ở đâu?**

Kiểm tra host/port từ vị trí ứng dụng, Docker network, ACL, xác thực, TLS, driver và cấu hình Spring. PING bên trong container chỉ cho biết Redis Server ở đó có phản hồi.

**6. Việc ghi–đọc thành công có bảo đảm Redis sẽ không mất dữ liệu sau restart không?**

Không. Khả năng lưu bền và phục hồi phụ thuộc cấu hình RDB/AOF, replication, topology và quy trình vận hành, nằm ngoài một phép thử SET/GET đơn giản.

**7. Có nên để ApplicationRunner kiểm tra này chạy ở mọi lần khởi động production không?**

Chỉ khi đó là yêu cầu được quyết định rõ cho hệ thống. Ví dụ dùng cờ mặc định tắt để tránh làm phát sinh lệnh ghi và lỗi khởi động ngoài ý muốn.

## Ghi nhớ

~~~text
1. Redis Server sẵn sàng và ứng dụng có cấu hình đúng
                       |
                       v
2. StringRedisTemplate SET key ngẫu nhiên + TTL
                       |
                       v
3. StringRedisTemplate GET cùng key
                       |
                       v
4. So sánh actual với expected
       |                         |
       | bằng nhau               | khác / null / exception
       v                         v
    THÀNH CÔNG                 KHÔNG ĐẠT
       |                         |
       '-----------+-------------'
                   |
                   v
5. Dọn key khi có thể; TTL bảo đảm key thử nghiệm không tồn tại mãi
~~~

**Kiểm tra ghi–đọc là bước xác nhận kết nối Redis ở mức ứng dụng**, không chỉ ở mức network. Một ví dụ dùng **StringRedisTemplate**, key riêng, **SET có TTL**, **GET so sánh giá trị** và **dọn dẹp an toàn** là điểm khởi đầu rõ ràng trước khi xây dựng các chức năng Spring Data Redis phức tạp hơn.
