# Phân biệt thời hạn tương đối với thời điểm hết hạn tuyệt đối

## 1. Vì sao cần phân biệt hai cách diễn đạt “hết hạn”?

Trong Spring Data Redis, một key có thể được xóa khỏi không gian dữ liệu khi đến thời hạn hết hạn (**expiration**). Điều này rất hữu ích với cache, phiên làm việc, mã xác minh ngắn hạn, khóa giữ chỗ, bộ đếm tạm thời và dữ liệu có vòng đời giới hạn.

Tuy nhiên, có hai yêu cầu tưởng giống nhau nhưng mang ý nghĩa khác nhau:

1. **“Lưu dữ liệu trong 15 phút kể từ lúc ghi vào Redis.”** Đây là **thời hạn tương đối** (relative duration, TTL).
2. **“Dữ liệu phải hết hạn lúc 00:00 ngày mai theo giờ Việt Nam.”** Đây là **thời điểm hết hạn tuyệt đối** (absolute expiration deadline).

Nếu một request chạy lúc 23:58, thời hạn tương đối 15 phút sẽ cho key sống đến khoảng **00:13 ngày hôm sau**. Nhưng thời điểm hết hạn tuyệt đối 00:00 chỉ còn **2 phút**. Dùng nhầm hai mô hình sẽ tạo ra cache cũ, phiên làm việc sống quá hạn hoặc dữ liệu bị xóa sớm hơn quy tắc nghiệp vụ.

Trong Redis, cần phân biệt:

- **EXPIRE / PEXPIRE:** đặt thời gian sống tương đối, tính từ lúc Redis xử lý lệnh.
- **EXPIREAT / PEXPIREAT:** đặt thời điểm hết hạn tuyệt đối bằng Unix timestamp.
- **TTL / PTTL:** hỏi còn bao lâu trước khi key hết hạn.
- **EXPIRETIME / PEXPIRETIME:** hỏi thời điểm hết hạn tuyệt đối đã được gán cho key (trên phiên bản Redis hỗ trợ).

Trong Spring Data Redis, hai API quan trọng tương ứng là **expire(key, Duration)** và **expireAt(key, Date hoặc kiểu thời điểm tương ứng)**. Bài học này tập trung vào cách lựa chọn, kiểm chứng và tránh lỗi khi làm việc với hai ngữ nghĩa thời gian trên.

## 2. Bốn khái niệm nền tảng

### 2.1. Thời hạn tương đối (duration)

Duration là **một lượng thời gian kéo dài**, chẳng hạn:

~~~text
30 giây
15 phút
2 giờ
24 giờ
~~~

Nếu một key được gán TTL 15 phút khi Redis nhận lệnh lúc 10:00:00, thời điểm hết hạn dự kiến sẽ xấp xỉ **10:15:00** theo đồng hồ của Redis Server.

Duration không mang thông tin ngày, tháng hay múi giờ. Trong Java, **java.time.Duration.ofMinutes(15)** là một thời lượng, không phải một thời điểm trên lịch.

### 2.2. Thời điểm tuyệt đối (instant/deadline)

Deadline là **một thời điểm cụ thể trên trục thời gian**, chẳng hạn:

~~~text
2027-01-01T00:00:00Z
2027-01-01T07:00:00+07:00
~~~

Hai cách viết trên biểu diễn **cùng một thời điểm**. Chữ **Z** nghĩa là UTC; **+07:00** nghĩa là giờ địa phương đi trước UTC 7 giờ.

Trong Java, **Instant** mô tả một thời điểm tuyệt đối. Bạn có thể chuyển từ một thời điểm lịch ở một vùng giờ cụ thể sang Instant để dùng làm deadline.

### 2.3. TTL là thời gian còn lại, không phải ngày hết hạn

Nếu key hết hạn lúc 10:15:00:

| Thời điểm quan sát | TTL còn lại, xấp xỉ |
| --- | --- |
| 10:00:00 | 15 phút |
| 10:05:00 | 10 phút |
| 10:14:30 | 30 giây |
| Sau 10:15:00 | Key không còn hiệu lực để truy cập |

Redis cung cấp **TTL** với đơn vị giây và **PTTL** với đơn vị mili giây. Vì thời gian trôi qua giữa thao tác ghi và đọc, TTL quan sát được không nhất thiết chính xác bằng con số ban đầu.

### 2.4. Redis lưu thông tin hết hạn dưới dạng mốc thời gian

Dù ứng dụng gửi một duration bằng EXPIRE, Redis vẫn cần xác định key hết hạn tại **một thời điểm trong tương lai** dựa trên đồng hồ của server. Vì vậy về mặt trạng thái Redis có thể suy ra thời điểm hết hạn của một key từ TTL, hoặc suy ra TTL từ thời điểm tuyệt đối.

Nhưng **đầu vào nghiệp vụ** vẫn quan trọng:

- Gửi EXPIRE 900 mỗi lần thực thi sẽ tạo thời điểm hết hạn mới **900 giây sau lần gọi đó**.
- Gửi EXPIREAT với cùng một Unix timestamp sẽ nhắm tới **cùng một deadline**, bất kể lệnh được gửi sớm hay muộn.

Không nên vì Redis có thể quy đổi hai dạng mà xem chúng luôn tương đương trong thiết kế ứng dụng.

## 3. Những lệnh Redis đặt thời hạn tương đối

### 3.1. EXPIRE: thời hạn tính bằng giây

Cú pháp:

~~~text
EXPIRE key seconds
~~~

Ví dụ trong redis-cli:

~~~text
SET lesson:expiry:relative "processing"
EXPIRE lesson:expiry:relative 120
TTL lesson:expiry:relative
GET lesson:expiry:relative
~~~

Redis đặt thời hạn sống cho key đang tồn tại là **120 giây**, tính từ lúc lệnh EXPIRE được xử lý. Nếu key không tồn tại, EXPIRE trả **0** và không tạo key. Nếu đặt được expiration, lệnh thường trả **1**.

Khi gọi lại:

~~~text
EXPIRE lesson:expiry:relative 120
TTL lesson:expiry:relative
~~~

TTL được **đặt lại** về gần 120 giây. Đây là một thao tác gia hạn hoặc thay đổi deadline, không phải “giữ nguyên lần hết hạn ban đầu”.

### 3.2. PEXPIRE: thời hạn tính bằng mili giây

~~~text
PEXPIRE lesson:expiry:relative 1500
PTTL lesson:expiry:relative
~~~

PEXPIRE dùng đơn vị **mili giây**, thuận tiện cho thời hạn ngắn hoặc yêu cầu biểu diễn độ chính xác cao hơn giây.

**Chú ý:** PEXPIRE 1500 nghĩa là **1,5 giây**, không phải 1.500 giây. Khi đặt TTL từ Java, nên dùng **Duration** để tránh đổi đơn vị bằng các số nguyên dễ nhầm.

### 3.3. SET với EX/PX: ghi dữ liệu và gán TTL cùng một lệnh

Nếu key chưa tồn tại, thường không nên tách thành SET và EXPIRE:

~~~text
SET lesson:expiry:session "active"
EXPIRE lesson:expiry:session 900
~~~

Giữa hai lệnh có khoảng hở: ứng dụng có thể mất kết nối hoặc bị dừng sau SET nhưng trước EXPIRE, khiến key tồn tại mà không có TTL.

Hãy ưu tiên:

~~~text
SET lesson:expiry:session "active" EX 900
~~~

Hoặc:

~~~text
SET lesson:expiry:short "active" PX 2500
~~~

**SET ... EX** và **SET ... PX** gộp việc ghi giá trị và gán hạn vào **một lệnh Redis nguyên tử**. EX dùng giây; PX dùng mili giây.

Những lệnh lịch sử như SETEX hoặc PSETEX cũng biểu đạt ý tưởng lưu String với expiration, nhưng cú pháp SET có tùy chọn EX/PX giúp nhìn rõ các điều kiện ghi hiện đại trong cùng một lệnh.

## 4. Những lệnh Redis đặt thời điểm hết hạn tuyệt đối

### 4.1. Unix timestamp là gì?

Unix timestamp biểu diễn thời điểm tính từ mốc **1970-01-01T00:00:00Z**. Redis sử dụng:

- **EXPIREAT key timestamp:** timestamp theo **giây**.
- **PEXPIREAT key millisecondsTimestamp:** timestamp theo **mili giây**.

Cùng một thời điểm có thể có hai số khác nhau vì đơn vị:

~~~text
Unix epoch seconds      = số giây từ 1970-01-01T00:00:00Z
Unix epoch milliseconds = số mili giây từ 1970-01-01T00:00:00Z
~~~

Không cần đưa múi giờ vào con số epoch: timestamp là mốc thời gian tuyệt đối. Múi giờ chỉ cần thiết khi chuyển từ biểu thức trên lịch như **00:00 tại Asia/Ho_Chi_Minh** thành một Instant.

### 4.2. EXPIREAT và PEXPIREAT

Ví dụ minh họa một deadline cố định là **2030-01-01T00:00:00Z**, tương ứng Unix epoch seconds **1893456000**:

~~~text
SET lesson:expiry:absolute "valid-until-deadline"
EXPIREAT lesson:expiry:absolute 1893456000
TTL lesson:expiry:absolute
~~~

Lệnh trên yêu cầu Redis xóa key khi tới **mốc 2030-01-01T00:00:00Z**, không phải 1.893.456.000 giây tính từ hiện tại. Số timestamp được chọn để dễ minh họa; khi áp dụng thực tế, phải tính deadline từ quy tắc nghiệp vụ của bạn.

Dùng mili giây cho cùng deadline:

~~~text
PEXPIREAT lesson:expiry:absolute 1893456000000
PTTL lesson:expiry:absolute
~~~

**PEXPIREAT** nhận 13 chữ số mili giây trong ví dụ này; **EXPIREAT** nhận 10 chữ số giây. Đưa timestamp mili giây vào EXPIREAT có thể dẫn tới một ngày trong tương lai quá xa; đưa giây vào PEXPIREAT thường khiến timestamp bị hiểu là thời điểm rất lâu trong quá khứ và key bị xóa ngay.

Khi deadline ở quá khứ hoặc thời điểm không còn trong tương lai theo đồng hồ Redis, đặt expiration có thể khiến key bị xóa ngay. Do đó, phải kiểm tra deadline trước khi đưa vào hệ thống.

### 4.3. SET với EXAT/PXAT

Trong Redis hỗ trợ các tùy chọn **EXAT** và **PXAT** của SET (Redis 6.2 trở lên), có thể gộp việc ghi giá trị và chỉ định deadline tuyệt đối trong **một lệnh**:

~~~text
SET lesson:expiry:published "available" EXAT 1893456000
SET lesson:expiry:published-ms "available" PXAT 1893456000000
~~~

Ý nghĩa:

- **EXAT:** đặt expiration tại Unix timestamp **giây**.
- **PXAT:** đặt expiration tại Unix timestamp **mili giây**.
- Redis xử lý ghi value và deadline trong cùng một thao tác.

Đây là lựa chọn rõ ràng khi muốn **tạo một key mới với deadline tuyệt đối mà không để xảy ra khoảng hở giữa SET và EXPIREAT**.

Phiên bản Redis cũ không hỗ trợ EXAT/PXAT của SET phải dùng chiến lược khác phù hợp phiên bản đang chạy.

### 4.4. So sánh trực diện

| Nhu cầu | Lệnh phù hợp | Deadline được xác định như thế nào? |
| --- | --- | --- |
| Hết hạn sau 120 giây từ lúc Redis xử lý | **EXPIRE key 120** | Redis lấy thời gian hiện tại của mình rồi cộng 120 giây. |
| Hết hạn sau 1500 ms | **PEXPIRE key 1500** | Redis lấy thời gian hiện tại rồi cộng 1500 ms. |
| Hết hạn tại Unix epoch second X | **EXPIREAT key X** | Cố định tại thời điểm X. |
| Hết hạn tại Unix epoch millisecond Y | **PEXPIREAT key Y** | Cố định tại thời điểm Y. |
| Ghi value và giữ 2 phút | **SET key value EX 120** | Ghi và TTL tương đối trong một lệnh. |
| Ghi value, hết hạn tại X | **SET key value EXAT X** | Ghi và deadline tuyệt đối trong một lệnh. |

## 5. Lệnh đọc thời gian còn lại và thời điểm hết hạn

### 5.1. TTL và PTTL: còn bao lâu?

~~~text
TTL lesson:expiry:relative
PTTL lesson:expiry:relative
~~~

Kết quả đặc biệt:

| Giá trị | Nghĩa |
| --- | --- |
| **-2** | Key không tồn tại (hoặc đã hết hạn). |
| **-1** | Key tồn tại nhưng không có expiration. |
| **Số không âm** | TTL còn lại; đơn vị giây với TTL hoặc mili giây với PTTL. |

TTL phản ánh **thời gian còn lại ở thời điểm lệnh được xử lý**, nên kết quả thay đổi qua mỗi lần gọi.

### 5.2. EXPIRETIME và PEXPIRETIME: hết hạn lúc nào?

Với Redis **7.0 trở lên**, có thể hỏi deadline đã được Redis ghi cho key:

~~~text
EXPIRETIME lesson:expiry:relative
PEXPIRETIME lesson:expiry:relative
~~~

Phân biệt:

- **EXPIRETIME** trả Unix timestamp **giây** khi key có expiration.
- **PEXPIRETIME** trả Unix timestamp **mili giây** khi key có expiration.
- **-1**: key tồn tại nhưng không có expiration.
- **-2**: key không tồn tại.

Ví dụ:

~~~text
SET lesson:expiry:inspect "ok" EX 60
TTL lesson:expiry:inspect
EXPIRETIME lesson:expiry:inspect
PEXPIRETIME lesson:expiry:inspect
~~~

TTL trả một khoảng còn lại gần 60 giây; EXPIRETIME trả một **mốc epoch** cố định theo deadline đã được gán. Nếu đọc lại vài giây sau, TTL giảm còn deadline của key không đổi, miễn không có lệnh sửa expiration.

### 5.3. Hai lệnh đọc không tạo một snapshot nguyên tử

~~~text
PTTL lesson:expiry:inspect
PEXPIRETIME lesson:expiry:inspect
~~~

Hai lệnh được thực thi lần lượt; giữa chúng có thể có client khác gia hạn TTL, xóa key hoặc ghi đè. Vì vậy, nếu kết quả không khớp chính xác, chưa thể kết luận Redis tính sai thời gian.

Khi debug, nên xem **tên key, TTL, deadline và đường ghi thực tế**, đồng thời ghi nhớ thời gian giữa các lệnh quan sát và việc Redis có những request concurrent khác.

## 6. Bản chất khác nhau khi request chạy trễ

Giả sử doanh nghiệp định “mã khuyến mãi hết hạn đúng 23:59:59 thứ Sáu”, nhưng một worker chỉ bắt đầu lưu mã vào Redis sau khi nhận sự kiện trễ.

**Thiết kế dùng duration:**

~~~text
SET promotion:42 active EX 3600
~~~

Lệnh này luôn tạo thêm **một giờ** tính từ lúc Redis nhận lệnh. Nếu worker xử lý trễ 20 phút, deadline cũng trễ 20 phút; có thể vô tình kéo dài chương trình khuyến mãi.

**Thiết kế dùng deadline:**

~~~text
SET promotion:42 active EXAT <epoch-second-cua-deadline>
~~~

Thay placeholder bằng Unix timestamp **được tính từ deadline nghiệp vụ**. Dù worker ghi sớm hay muộn, key đều có cùng mốc hết hạn. Nếu worker chạy sau deadline, key không nên được coi là đang hợp lệ.

Đây là lý do thường chọn **absolute expiration** cho các quy định có mốc lịch cố định, còn chọn **relative expiration** cho dữ liệu cần sống một lượng thời gian nhất định tính từ một sự kiện.

### Trục thời gian minh họa

~~~text
                      Lưu sớm         Lưu trễ         Deadline chung
Trục thời gian: --------|---------------|----------------|----------->

TTL 30 phút từ lúc ghi: [30 phút]       [30 phút]
                        ^ hết hạn A          ^ hết hạn B

Hết hạn tuyệt đối:      ------------------------------->|
                       cả hai lần ghi đều dùng cùng deadline
~~~

Hai cách có thể cho kết quả giống nhau trong một lần gọi cụ thể nếu Duration được tính đúng bằng khoảng còn lại đến deadline. Nhưng **ngữ nghĩa và điểm neo thời gian** của chúng khác nhau.

## 7. Spring Data Redis: expire(Duration) và expireAt(Date)

### 7.1. Chuẩn bị dự án Spring Boot

Ví dụ ứng dụng Spring Boot 3.x với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

Cấu hình minh họa Redis Server tại máy local. Với Redis có ACL/TLS, Redis Cluster hoặc môi trường container, cần thay endpoint và cấu hình bảo mật tương ứng. Không đưa password thực vào mã nguồn.

Khi dùng starter và auto-configuration thông thường, Spring Boot cung cấp **StringRedisTemplate** để thao tác với key/value dạng chuỗi.

### 7.2. Đặt hạn tương đối trên key đang tồn tại

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

String key = "lesson:expiry:cart:42";

redis.opsForValue().set(key, "ACTIVE");

Boolean result = redis.expire(
        key, Duration.ofMinutes(15));

boolean updated = Boolean.TRUE.equals(result);
~~~

**expire(key, Duration)** diễn tả “key này phải hết hạn sau một khoảng thời gian”. Nó phù hợp với **EXPIRE/PEXPIRE** ở mức ý nghĩa.

Điểm cần lưu ý:

- **expire** yêu cầu key đã tồn tại; nếu key không có, kết quả thông thường là false.
- Gọi expire nhiều lần thường **đặt lại thời hạn** tính từ mỗi lần gọi.
- SET và expire trong ví dụ là **hai lệnh riêng**; nếu cần tạo key với TTL chắc chắn, nên dùng overload SET có Duration.

### 7.3. Ghi key với TTL tương đối trong một thao tác

~~~java
redis.opsForValue().set(
        "lesson:expiry:one-call",
        "ACTIVE",
        Duration.ofMinutes(15)
);
~~~

Đây là mẫu nên dùng khi mục tiêu là **tạo/cập nhật String và đặt một TTL tính từ lần ghi**. Redis có thể thực hiện thao tác với expiration trong cùng lệnh SET, tránh khoảng hở nếu gọi SET rồi expire riêng.

Nếu service ghi đè key bằng SET không chỉ định expiration sau đó, TTL cũ có thể bị xóa. Do đó cần thống nhất mọi đường ghi đối với key này.

### 7.4. Đặt deadline tuyệt đối cho key đang tồn tại

Spring Data Redis hỗ trợ cách đặt thời điểm hết hạn qua **expireAt**. Một overload phổ biến nhận **java.util.Date**, có thể tạo Date từ **Instant**:

~~~java
import java.time.Instant;
import java.util.Date;
import org.springframework.data.redis.core.StringRedisTemplate;

String key = "lesson:expiry:offer:42";
Instant deadline = Instant.parse("2030-01-01T00:00:00Z");

redis.opsForValue().set(key, "ACTIVE");

Boolean result = redis.expireAt(
        key, Date.from(deadline));

boolean updated = Boolean.TRUE.equals(result);
~~~

**expireAt** diễn tả **hết hạn tại deadline**, không phải “sống thêm deadline giây”. Trong Redis, nó có ý nghĩa tương ứng với các lệnh EXPIREAT/PEXPIREAT.

**java.util.Date** lưu một thời điểm tuyệt đối theo epoch milliseconds. Khi chuyển từ **Instant**, không cần cộng/trừ múi giờ thủ công. Cách Date được in ra console có thể theo múi giờ hệ điều hành, nhưng thời điểm được lưu vẫn là cùng một mốc.

Lưu ý: **SET rồi expireAt ở trên vẫn là hai lệnh Redis riêng**. Nếu ứng dụng crash giữa chúng, key có thể tồn tại không có expiration. Khi cần tạo value và deadline tuyệt đối atomically, sử dụng lệnh SET EXAT/PXAT hoặc một cách thực thi tương đương được client hỗ trợ.

### 7.5. Đọc TTL từ Spring Data Redis

~~~java
import java.util.concurrent.TimeUnit;

Long ttlSeconds = redis.getExpire(
        "lesson:expiry:offer:42");

Long ttlMillis = redis.getExpire(
        "lesson:expiry:offer:42",
        TimeUnit.MILLISECONDS);
~~~

Kết quả trong lời gọi thông thường:

- **-2** nếu key không còn.
- **-1** nếu key có nhưng không có expiration.
- **Số không âm** nếu key còn TTL.

Trong pipeline/transaction, một số API trả kết quả sau khi lệnh được thực thi, nên không mặc định kết quả có ngay tại nơi gọi khi đang xếp lệnh. Nếu cần xem trực tiếp deadline tuyệt đối từ Redis 7+, có thể dùng redis-cli với EXPIRETIME/PEXPIRETIME hoặc API command tương ứng mà phiên bản Spring Data Redis hỗ trợ.

## 8. Ví dụ Spring Boot: chọn đúng chính sách cho hai loại dữ liệu

Một service có hai nghiệp vụ:

- **Trạng thái thao tác tạm:** hết hạn **10 phút kể từ lúc ghi**.
- **Ưu đãi theo lịch:** hết hạn **đúng 00:00 ngày mai theo giờ Asia/Ho_Chi_Minh**.

Hai trường hợp cần hai cách biểu diễn.

### 8.1. Service minh họa

~~~java
package example.redis;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ExpirationPolicyService {

    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private final StringRedisTemplate redis;
    private final Clock clock;

    public ExpirationPolicyService(
            StringRedisTemplate redis,
            Clock clock) {
        this.redis = redis;
        this.clock = clock;
    }

    private static String safeId(String id) {
        if (id == null || !id.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid identifier");
        }
        return id;
    }

    /** Thời hạn tương đối: 10 phút kể từ lần ghi. */
    public void saveTemporaryState(String requestId, String state) {
        String key = "temp:request:" + safeId(requestId);
        redis.opsForValue().set(
                key, state, Duration.ofMinutes(10));
    }

    /** Cố định deadline lúc bắt đầu ngày mai ở giờ Việt Nam. */
    public void savePromotionUntilTomorrow(String promotionId,
                                           String value) {
        String key = "promotion:active:" + safeId(promotionId);

        LocalDate tomorrow = LocalDate.now(
                clock.withZone(BUSINESS_ZONE)).plusDays(1);

        Instant deadline = tomorrow
                .atStartOfDay(BUSINESS_ZONE)
                .toInstant();

        redis.opsForValue().set(key, value);
        boolean expirySet = Boolean.TRUE.equals(
                redis.expireAt(key, Date.from(deadline)));

        if (!expirySet) {
            throw new IllegalStateException(
                    "Unable to assign promotion expiration");
        }
    }
}
~~~

Để inject **Clock** vào service, có thể cấu hình:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

**Vì sao dùng Clock?** Thay vì gọi trực tiếp Instant.now ở mọi nơi, bạn có thể inject một Clock cố định trong test để kiểm tra chính xác các trường hợp gần nửa đêm và ranh giới ngày.

**Vì sao dùng ZoneId?** “Ngày mai lúc 00:00” là yêu cầu theo **lịch địa phương**. Chuyển LocalDate.atStartOfDay(zone) sang Instant giúp xác định đúng thời điểm UTC mà Redis cần. Không nên cộng cố định 7 giờ vào epoch timestamp bằng tay.

**Giới hạn của method savePromotionUntilTomorrow:** đoạn code dùng SET rồi expireAt riêng để minh họa rõ **expireAt**. Nếu yêu cầu không được phép tạo key không có TTL khi ứng dụng crash, hãy áp dụng cách ghi atomically ở mục tiếp theo.

### 8.2. Giới hạn 24 giờ khác “đến nửa đêm ngày mai”

Hai đoạn logic:

~~~java
Duration.ofHours(24)
~~~

và:

~~~java
LocalDate.now(clock.withZone(BUSINESS_ZONE))
        .plusDays(1)
        .atStartOfDay(BUSINESS_ZONE)
        .toInstant()
~~~

khác nhau:

- **Duration.ofHours(24):** 24 giờ kể từ điểm neo khi thực thi.
- **Start of next day:** mốc lịch 00:00 của ngày tiếp theo theo một ZoneId cụ thể.

Nếu hiện tại là 23:58, deadline nửa đêm chỉ còn hai phút. Ở vùng có chuyển giờ mùa hè (DST), một “ngày theo lịch” thậm chí có thể dài **23 hoặc 25 giờ** thay vì đúng 24 giờ. Bởi vậy, các deadline nghiệp vụ liên quan ngày/giờ phải sử dụng kiểu dữ liệu và vùng giờ phù hợp.

## 9. Ghi value và deadline tuyệt đối như một đơn vị nguyên tử

### 9.1. Vấn đề của hai lệnh riêng biệt

Ví dụ:

~~~java
redis.opsForValue().set(key, value);
redis.expireAt(key, Date.from(deadline));
~~~

Nếu lệnh đầu đã thực hiện nhưng lệnh thứ hai không chạy vì service bị dừng, key mới có thể sống mãi. Ngược lại, nếu một writer khác ghi đè key giữa hai lần gọi, deadline mà bạn gán có thể vô tình áp dụng cho value mới của writer khác.

**Một deadline đúng không đủ; cần xem cả tính nguyên tử của việc gắn deadline với value.**

### 9.2. SET ... EXAT/PXAT

Khi Redis hỗ trợ:

~~~text
SET lesson:expiry:atomic "ACTIVE" EXAT 1893456000
~~~

Redis xử lý value và deadline tuyệt đối trong **một lệnh**, vì vậy không có khoảng hở giữa SET và EXPIREAT của client.

**Đặc tính của lệnh này:** nếu một client khác cũng SET cùng key sau đó, trạng thái cuối cùng còn phụ thuộc thứ tự các lệnh. Atomicity của một lệnh không tự giải quyết mọi xung đột cập nhật giữa nhiều writer.

### 9.3. Thực thi PXAT từ StringRedisTemplate bằng RedisScript

Nếu API thao tác của template đang dùng không cung cấp overload ghi String với deadline tuyệt đối trong một lời gọi, một cách minh họa là đưa lệnh SET PXAT vào RedisScript:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

public class AbsoluteDeadlineWriter {

    private final StringRedisTemplate redis;

    private static final RedisScript<String> SET_ABSOLUTE;

    static {
        DefaultRedisScript<String> script = new DefaultRedisScript<>();
        script.setScriptText("""
                local expireMillis = tonumber(ARGV[2])
                if not expireMillis or expireMillis <= 0
                   or expireMillis ~= math.floor(expireMillis) then
                    return redis.error_reply('Invalid expiration timestamp')
                end
                return redis.call('SET',
                    KEYS[1], ARGV[1], 'PXAT', ARGV[2])
                """);
        script.setResultType(String.class);
        SET_ABSOLUTE = script;
    }

    public AbsoluteDeadlineWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String key, String value, Instant deadline) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(deadline, "deadline");

        String result = redis.execute(
                SET_ABSOLUTE,
                List.of(key),
                value,
                Long.toString(deadline.toEpochMilli()));

        if (!"OK".equals(result)) {
            throw new IllegalStateException("Redis write was not confirmed");
        }
    }
}
~~~

Trong ví dụ này:

1. Spring gửi **key** dưới dạng KEYS[1].
2. Value và epoch milliseconds được gửi dưới dạng ARGV.
3. Lua kiểm tra timestamp trước khi ghi.
4. Redis thực thi **SET ... PXAT** trong một script; thao tác thực chất vẫn là một lần SET có deadline tuyệt đối.

Ví dụ dành cho **Redis 6.2+** có hỗ trợ PXAT. Trước khi sử dụng trong hệ thống thật, phải bảo đảm serializer key/value tương ứng với cách lưu chuỗi, quyền ACL cho phép thực thi script/lệnh cần dùng, và deadline được tính đúng theo yêu cầu nghiệp vụ.

**Không nên gọi Lua script một cách mặc định cho mọi lệnh Redis.** Nếu Redis client hoặc phiên bản Spring Data Redis đang dùng cung cấp API trực tiếp phù hợp cho SET EXAT/PXAT, có thể sử dụng API đó để giảm độ phức tạp triển khai. Script chủ yếu minh họa cách đảm bảo ghi và deadline đi cùng nhau.

## 10. Dùng duration tính từ deadline có tương đương expireAt không?

Một cách thường gặp:

~~~java
Instant deadline = ...;
Duration remaining = Duration.between(
        Instant.now(), deadline);

redis.opsForValue().set(key, value, remaining);
~~~

Đoạn này **tính một TTL từ mốc tuyệt đối**, sau đó gửi Redis thao tác với TTL tương đối. Nó có thể phù hợp khi không có API đặt expiration tuyệt đối và độ chính xác vài mili giây không phải yêu cầu cứng.

Nhưng có những khác biệt:

1. **Khoảng thời gian chờ ở client:** between được tính ở JVM, nhưng Redis chỉ bắt đầu TTL khi xử lý lệnh. Nếu request bị trì hoãn trên đường đi, deadline thực tế sẽ muộn hơn một chút so với mốc mong muốn.
2. **Đồng hồ khác nhau:** JVM có thể tính thời điểm bằng đồng hồ khác với đồng hồ Redis Server.
3. **Deadline đã qua:** Duration có thể bằng 0 hoặc âm; phải xử lý trước khi gọi overload có timeout.
4. **Sai lệch khi retry:** nếu mỗi lần retry lại dùng Duration.ofMinutes(15), deadline sẽ trượt; còn nếu tính lại Duration.between(now, fixedDeadline), deadline có xu hướng giữ được gần mốc ban đầu.

Ví dụ xử lý deadline đã qua:

~~~java
Duration remaining = Duration.between(clock.instant(), deadline);
if (remaining.isNegative() || remaining.isZero()) {
    redis.delete(key);
    return;
}

redis.opsForValue().set(key, value, remaining);
~~~

Mẫu này còn có **khoảng hở** giữa phép kiểm tra và lệnh ghi; nếu lệnh bị trì hoãn quá lâu, server có thể nhận một Duration đã không còn phù hợp với deadline. Với deadline tuyệt đối nghiêm ngặt, một thao tác **SET EXAT/PXAT** là cách diễn đạt sát ngữ nghĩa hơn.

## 11. Gia hạn TTL và giữ deadline: quy tắc nào phù hợp?

### 11.1. Gia hạn theo hoạt động (sliding idle timeout)

Một phiên thao tác hết hạn sau 20 phút **không hoạt động** cần gia hạn khi có hoạt động mới:

~~~text
EXPIRE session:42 1200
~~~

Nếu client tiếp tục gọi EXPIRE 1200 mỗi khi có hoạt động hợp lệ, deadline sẽ dịch về phía sau. Đây là **relative expiration có chủ ý được làm mới**.

Tuy nhiên, nếu hệ thống giới hạn session phải kết thúc tuyệt đối sau 24 giờ kể từ lúc phát hành, việc gia hạn 20 phút không được vượt quá **absolute maximum lifetime**.

### 11.2. Deadline cố định không được kéo dài bởi mỗi lần đọc

Một mã giảm giá kết thúc đúng 23:59:59 phải luôn hướng đến một deadline:

~~~text
EXPIREAT promotion:42 <same-deadline-epoch-seconds>
~~~

Nếu mỗi lần đọc mã lại đặt EXPIRE 15 phút, hệ thống có thể vô tình kéo dài tuổi thọ của mã qua thời điểm chương trình kết thúc.

### 11.3. Khi cần cả idle timeout và absolute maximum

Ví dụ session có hai điều kiện:

- Hết hạn sau **20 phút không hoạt động**.
- Nhưng **không bao giờ vượt quá 8 giờ kể từ lúc đăng nhập**.

Deadline thực tế nên là **min(now + 20 phút, loginTime + 8 giờ)**. Khi người dùng hoạt động:

1. Xác định absolute maximum từ loginTime cố định.
2. Tính idle deadline mới từ thời điểm hoạt động.
3. Chọn deadline sớm hơn.
4. Gán deadline đó cho key.

Nếu chỉ dùng EXPIRE 1200 không có giới hạn tuyệt đối, một session hoạt động liên tục có thể sống quá 8 giờ.

Khi nhiều request đồng thời gia hạn cùng key, các lệnh đặt TTL có thể chạy không theo thứ tự mong muốn. Nếu không được phép rút ngắn hoặc kéo dài deadline ngoài quy tắc, cần dùng điều kiện gán TTL hoặc script nguyên tử với trạng thái session cần thiết.

## 12. Tùy chọn NX, XX, GT, LT của EXPIRE: tránh sửa TTL tùy tiện

Trên **Redis 7.0 trở lên**, EXPIRE và những biến thể đặt expiration hỗ trợ các tùy chọn điều kiện theo quyền năng từng lệnh.

Ví dụ:

~~~text
EXPIRE lesson:expiry:conditional 60 NX
EXPIRE lesson:expiry:conditional 120 XX
EXPIRE lesson:expiry:conditional 180 GT
EXPIRE lesson:expiry:conditional 30 LT
~~~

Ý nghĩa:

| Tùy chọn | Điều kiện đặt expiration mới |
| --- | --- |
| **NX** | Chỉ đặt khi key chưa có expiration. |
| **XX** | Chỉ đặt khi key đã có expiration. |
| **GT** | Chỉ đặt khi deadline mới **muộn hơn** deadline hiện tại. |
| **LT** | Chỉ đặt khi deadline mới **sớm hơn** deadline hiện tại. |

Đối với key không có expiration, Redis xem deadline hiện tại như **vô hạn** khi đánh giá GT/LT. Vì vậy:

- **GT** không dùng để thêm hạn cho key đang không có TTL.
- **LT** có thể đặt một hạn hữu hạn cho key chưa có expiration.

Không thể kết hợp các tùy chọn tùy tiện; chẳng hạn GT và LT là những chính sách đối nghịch. Những điều kiện này hữu ích để tránh ghi đè expiration theo hướng không mong muốn trong một lệnh.

Tuy nhiên, khi nghiệp vụ cần **tăng bộ đếm rồi đặt TTL** mà cả hai bước phải nguyên tử, chỉ thêm EXPIRE NX ở lệnh thứ hai vẫn không xóa khoảng hở giữa hai lệnh. Có thể cần MULTI/EXEC hoặc script.

**Phiên bản Redis quan trọng:** không chạy các ví dụ NX/XX/GT/LT trên Redis cũ nếu phiên bản đó chưa hỗ trợ cú pháp mở rộng.

## 13. TTL thay đổi thế nào khi ghi đè, cập nhật và xóa dữ liệu?

Một key không phải lúc nào cũng giữ expiration đã gán trước đó. Cần phân biệt các thao tác:

| Thao tác | Tác động thường gặp tới expiration |
| --- | --- |
| **SET key newValue** | Thường **xóa TTL cũ** khi không chỉ định KEEP TTL/expiration mới. |
| **SET key newValue EX 60** | Ghi value và đặt TTL 60 giây tính từ lần ghi. |
| **SET key newValue EXAT epoch** | Ghi value và gán deadline tuyệt đối. |
| **SET key newValue KEEPTTL** | Giữ expiration hiện có nếu key đang có, trên Redis hỗ trợ tùy chọn này. |
| **INCR key** | Thay đổi value số nguyên nhưng thường giữ TTL đang có. |
| **HSET key field value** | Cập nhật field trong Hash, thường giữ TTL của key Hash. |
| **LPUSH / RPUSH key value** | Cập nhật List hiện có, thường giữ TTL của key List. |
| **SADD / ZADD** | Cập nhật Set/ZSet hiện có, thường giữ TTL. |
| **EXPIRE / EXPIREAT** | Thay deadline của key theo lệnh tương ứng. |
| **PERSIST key** | Gỡ expiration, khiến key tồn tại không TTL nếu còn dữ liệu. |
| **DEL key** | Xóa cả key, không còn deadline để theo dõi. |

Ví dụ quan sát sự khác biệt:

~~~text
SET lesson:expiry:overwrite A EX 90
TTL lesson:expiry:overwrite
SET lesson:expiry:overwrite B
TTL lesson:expiry:overwrite
~~~

Sau SET không kèm expiration, TTL có thể là **-1**: key vẫn tồn tại nhưng không còn hạn.

Nếu muốn giữ TTL cũ khi thay giá trị String và Redis có hỗ trợ:

~~~text
SET lesson:expiry:overwrite C EX 90
SET lesson:expiry:overwrite D KEEPTTL
TTL lesson:expiry:overwrite
~~~

**KEEPTTL** giữ thời điểm hết hạn đã có, không “gia hạn thêm 90 giây” ở lần ghi D. Việc lựa chọn giữa KEEPTTL và tạo TTL mới phụ thuộc quy tắc nghiệp vụ.

## 14. Clock, múi giờ và độ chính xác: các nguồn sai lệch phổ biến

### 14.1. Deadline theo lịch phải chọn múi giờ trước khi đổi ra epoch

“Hết hạn cuối ngày 31/12” không đủ rõ nếu hệ thống có người dùng ở nhiều quốc gia. Cần xác định:

- Cuối ngày theo **UTC**?
- Theo múi giờ **Asia/Ho_Chi_Minh**?
- Theo múi giờ của **từng người dùng**?
- Theo giờ địa phương của **đơn vị kinh doanh**?

Chỉ sau khi xác định ZoneId mới chuyển **LocalDate/ZonedDateTime** thành Instant.

Ví dụ ngày đầu năm theo giờ Việt Nam:

~~~java
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
Instant deadline = LocalDate.of(2030, 1, 1)
        .atStartOfDay(vietnam)
        .toInstant();
~~~

Deadline này **khác** Instant.parse("2030-01-01T00:00:00Z") vì nửa đêm Việt Nam xảy ra sớm hơn UTC 7 giờ.

### 14.2. Đồng hồ JVM và Redis không hoàn toàn là một

Nếu Spring Boot tính deadline bằng **clock.instant()** còn Redis Server đánh giá thời điểm hiện tại bằng đồng hồ của nó, cần chú ý:

- Clock skew giữa các máy.
- Đồng bộ thời gian NTP hoặc dịch vụ thời gian được quản lý.
- Clock bị điều chỉnh tiến/lùi.
- Độ trễ từ lúc ứng dụng tạo deadline tới lúc Redis nhận lệnh.

Với EXPIRE, Redis tự tính deadline từ duration khi thực thi lệnh. Với EXPIREAT, ứng dụng cung cấp mốc epoch, nên kết quả nhạy với việc **deadline được tính đúng** và đồng hồ server có bám sát thời gian thực hay không.

### 14.3. Redis expiration dựa trên thời gian thực, không phải lịch hẹn chính xác của ứng dụng

Redis có cơ chế xử lý key hết hạn khi truy cập và quét chủ động các key cần xóa. Khi key đã quá hạn, Redis không nên trả key như dữ liệu còn hiệu lực; tuy vậy, **việc giải phóng vật lý khỏi bộ nhớ không nhất thiết xảy ra đúng tại một thời điểm microsecond chính xác**.

Không nên dùng TTL làm cơ chế scheduler đáng tin cậy để chạy một job chính xác lúc nửa đêm. Nếu cần phát sự kiện, chuyển trạng thái hợp đồng hoặc ghi sổ đúng lịch, hãy sử dụng job scheduler/queue/workflow thích hợp và kiểm tra deadline nghiệp vụ trực tiếp.

### 14.4. Chính sách clock và RDB/AOF/replication

Expiration được ghi dưới dạng thời điểm hết hạn, nên clock không đồng bộ giữa các máy hoặc thay đổi thời gian có thể ảnh hưởng việc key bị xem là đã hết hạn hay chưa. Persistence và replication có quy tắc riêng về lưu, tải và truyền trạng thái expiration.

Điều cần nhớ là **TTL không thay thế chiến lược về độ bền dữ liệu, failover và tính nhất quán**. Khi deadline có ý nghĩa bảo mật/tài chính, ứng dụng nên xác thực thêm mốc hạn trong bản ghi nghiệp vụ hoặc nguồn dữ liệu đáng tin cậy, thay vì coi việc key vẫn còn hoặc đã biến mất là tất cả bằng chứng cần có.

## 15. Phân biệt expiration, eviction và xóa chủ động

Chương “Hết hạn và loại bỏ” thường đề cập ba cách key biến mất:

| Cơ chế | Tại sao key bị xóa? | Ví dụ |
| --- | --- | --- |
| **Expiration** | Đến hạn theo TTL/deadline được gán | EXPIRE, EXPIREAT, SET EX/PX/EXAT/PXAT |
| **Eviction** | Redis cần giải phóng bộ nhớ theo cấu hình maxmemory và eviction policy | allkeys-lru, volatile-lru, allkeys-random... |
| **Explicit deletion** | Client ra lệnh xóa | DEL, UNLINK hoặc lệnh làm cấu trúc rỗng |

**Có TTL không bảo đảm key sống đủ đến deadline:** key vẫn có thể bị eviction sớm hơn nếu chính sách bộ nhớ cho phép. Ngược lại, một key không có TTL vẫn có thể bị eviction trong những chính sách áp dụng cho mọi key.

Ngoài ra, **ZREMRANGEBYSCORE** xóa từng member của Sorted Set theo khoảng score không phải expiration tự động của Redis. Score có thể chứa timestamp, nhưng Redis không tự chạy lệnh dọn khi timestamp đó tới hạn.

Khi ứng dụng đọc null từ Redis, các nguyên nhân khả dĩ gồm key chưa từng tồn tại, đã hết hạn, bị chủ động xóa hoặc bị eviction. Muốn xác định chính xác, cần có thông tin quan sát và chính sách vận hành phù hợp.

## 16. Redis Cluster, nhiều instance và concurrency

### 16.1. Expiration áp dụng cho key dù được định tuyến theo slot nào

Trong Redis Cluster, key thuộc một trong **16.384 hash slot**. Client cluster-aware sẽ định tuyến EXPIRE, EXPIREAT, GET và các lệnh một key đến node phụ trách slot tương ứng.

Nếu một ứng dụng cần gán TTL cho **nhiều key** và yêu cầu việc đó nguyên tử trong một script/transaction, các key cần phù hợp ràng buộc **cùng slot** của Redis Cluster. Hash tag có thể giúp đặt những key liên quan chung slot:

~~~text
session:{user42}:state
session:{user42}:meta
~~~

Nhưng cùng slot **không có nghĩa** mỗi lệnh EXPIRE riêng biệt trên hai key tự trở thành một thao tác nguyên tử.

### 16.2. “Last writer wins” với các lệnh cập nhật deadline

Giả sử hai service cùng gán expiration:

~~~text
Service A: EXPIREAT key deadline-A
Service B: EXPIREAT key deadline-B
~~~

Lệnh chạy sau sẽ quyết định deadline hiện tại nếu không dùng điều kiện bổ sung. Nếu yêu cầu “deadline không bao giờ được vượt quá mốc ban đầu”, các lệnh gán TTL không điều kiện có thể vi phạm yêu cầu.

Redis 7+ cung cấp các tùy chọn điều kiện như **GT/LT** cho expiration, và script có thể đọc, so sánh rồi thay đổi deadline như một đơn vị nếu nghiệp vụ cần các quy tắc phức tạp hơn.

### 16.3. Retry sau timeout

Một lệnh expireAt với **cùng một deadline cố định** thường biểu diễn ngữ nghĩa dễ dự đoán khi retry, vì cả hai lần đều yêu cầu cùng một mốc thời gian.

Ngược lại, retry câu lệnh **EXPIRE key 900** sau 30 giây có thể kéo dài thời gian sống thêm 30 giây. Nếu muốn retry nhưng không làm trượt deadline, cần lưu deadline cố định hoặc dùng cơ chế điều kiện phù hợp.

Dù vậy, retry một thao tác **SET value EXAT deadline** có thể ghi đè value từ request khác. Cần xem xét concurrency và idempotency của **cả value lẫn deadline**, không chỉ expiration.

## 17. Thực hành bằng redis-cli: quan sát hai mô hình

Thực hiện trên Redis học tập có quyền ghi. Nếu Redis cần ACL/TLS, dùng endpoint và phương thức xác thực an toàn tương ứng.

### Bước 1. Tạo key hết hạn tương đối

~~~text
SET lesson:row164:relative "R" EX 90
GET lesson:row164:relative
TTL lesson:row164:relative
PTTL lesson:row164:relative
~~~

Kỳ vọng:

- GET trả **R** nếu key chưa hết hạn.
- TTL gần 90 giây và giảm dần.
- PTTL phản ánh thời gian còn lại theo mili giây.

### Bước 2. Gán lại TTL tương đối

~~~text
EXPIRE lesson:row164:relative 90
TTL lesson:row164:relative
~~~

TTL trở lại gần 90 giây. Nếu key đã hết hạn trước lần gọi EXPIRE, lệnh không tạo lại key; khi đó phải tạo key mới để quan sát lại.

### Bước 3. Tạo key với deadline tuyệt đối

~~~text
SET lesson:row164:absolute "A" EXAT 1893456000
TTL lesson:row164:absolute
~~~

Deadline là mốc **2030-01-01T00:00:00Z**. Đọc TTL để thấy thời lượng còn lại từ thời điểm hiện tại đến năm 2030; nó **không phải** 1893456000 giây tính từ lúc chạy lệnh.

Nếu Redis 7.0+, đọc thêm:

~~~text
EXPIRETIME lesson:row164:absolute
PEXPIRETIME lesson:row164:absolute
~~~

Kết quả EXPIRETIME dự kiến là **1893456000** (giây), còn PEXPIRETIME là **1893456000000** (mili giây), với điều kiện key chưa bị client khác sửa expiration.

### Bước 4. Thay thời hạn tương đối bằng một deadline tuyệt đối

~~~text
EXPIREAT lesson:row164:relative 1893456000
TTL lesson:row164:relative
~~~

Key **relative** giờ cũng hết hạn theo mốc cố định 2030-01-01T00:00:00Z. Tên key không quyết định tính tương đối hay tuyệt đối; **lệnh gán expiration gần nhất** (nếu thành công và không bị ràng buộc điều kiện) quyết định deadline hiện tại.

### Bước 5. Quan sát key không có TTL

~~~text
SET lesson:row164:no-ttl "N"
TTL lesson:row164:no-ttl
PERSIST lesson:row164:absolute
TTL lesson:row164:absolute
~~~

TTL của no-ttl là **-1**; sau PERSIST, TTL của absolute cũng là -1 vì expiration đã được gỡ.

### Bước 6. Quan sát khi key không còn

~~~text
DEL lesson:row164:no-ttl
TTL lesson:row164:no-ttl
~~~

TTL trả **-2** nếu key không tồn tại.

### Bước 7. Dọn key thử nghiệm

~~~text
DEL lesson:row164:relative
DEL lesson:row164:absolute
DEL lesson:row164:no-ttl
~~~

Chỉ xóa đúng key thử nghiệm. Không dùng FLUSHDB hoặc FLUSHALL để dọn bài tập vì các lệnh đó có thể xóa dữ liệu khác trong Redis.

## 18. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Key sống lâu hơn mốc nghiệp vụ | Dùng TTL tương đối mỗi lần ghi dù deadline cần cố định | So sánh Duration với Instant deadline, xem đường ghi và EXPIRETIME. |
| Key biến mất ngay sau EXPIREAT | Timestamp ở quá khứ hoặc nhầm giây/mili giây | Xem số epoch và cách quy đổi đơn vị. |
| TTL = -1 dù trước đó có expiration | SET không kèm TTL, KEEPTTL thiếu, hoặc PERSIST đã gỡ hạn | Kiểm tra toàn bộ nơi ghi key. |
| TTL = -2 | Key không tồn tại, hết hạn, bị xóa hoặc eviction | Kiểm tra log nghiệp vụ, policy và dữ liệu quan sát. |
| expireAt trả false | Key không tồn tại tại lúc đặt deadline | Kiểm tra thao tác tạo key và concurrency. |
| SET rồi expireAt để lại key không có TTL | App dừng giữa hai lệnh | Dùng SET EXAT/PXAT hoặc thao tác nguyên tử tương đương. |
| EXPIRETIME không tồn tại | Redis phiên bản chưa hỗ trợ | Kiểm tra phiên bản, dùng TTL/PTTL để quan sát tương đối. |
| Hết hạn sai 7 giờ | Chuyển local time sang epoch sai hoặc bỏ qua ZoneId | Tạo Instant từ ZonedDateTime/LocalDate ở múi giờ đúng. |
| Hết hạn sớm/muộn giữa các máy | Clock skew hoặc node được đổi | Đồng bộ thời gian, theo dõi clock Redis/JVM. |
| Cache hit kéo dài không đúng | Mỗi lần cập nhật lại gán TTL từ đầu | Xác định muốn sliding TTL hay deadline cố định; dùng KEEPTTL khi phù hợp. |
| Retry kéo dài TTL thêm một khoảng | Gọi lại EXPIRE với cùng duration | Dùng deadline cố định hoặc điều kiện expiration. |
| Xóa key dù TTL chưa về 0 | Eviction hoặc explicit deletion | Phân biệt expiration, eviction và DEL/UNLINK. |
| Key tạo lại không còn TTL cũ | Key trước đó đã hết hạn/xóa, lệnh ghi mới không đặt TTL | Luôn chỉ định TTL/deadline khi tạo key mới nếu bắt buộc. |
| Mọi request thấy deadline khác nhau | Mỗi instance tính ngày theo zone/clock khác nhau | Chuẩn hóa ZoneId và nguồn tính deadline. |

### Quy trình điều tra có hệ thống

1. **Xác định yêu cầu nghiệp vụ:** sống bao lâu từ lúc tạo hay hết hạn lúc nào?
2. **Kiểm tra key thực tế:** đúng host/port/database/Cluster slot và serializer chưa?
3. **Đọc TTL/PTTL:** key còn tồn tại không và còn bao lâu?
4. **Đọc deadline:** EXPIRETIME/PEXPIRETIME nếu Redis 7+; so sánh với Instant mong muốn.
5. **Tìm đường ghi:** có SET không kèm TTL, PERSIST, EXPIRE gia hạn hoặc lệnh xóa từ service khác không?
6. **Kiểm tra timezone/clock:** thời điểm nghiệp vụ đã được chuyển sang epoch đúng đơn vị và ZoneId chưa?
7. **Kiểm tra concurrency/retry:** hai lệnh có bị xen kẽ, request trễ hoặc timeout không?
8. **Kiểm tra vận hành:** eviction policy, clock skew, failover và persistence nếu dữ liệu có ràng buộc nghiêm ngặt.

## 19. Bài toán lựa chọn: dùng tương đối hay tuyệt đối?

| Tình huống | Lựa chọn ưu tiên | Giải thích |
| --- | --- | --- |
| Cache kết quả tính toán trong 5 phút kể từ lần ghi | **TTL tương đối** | Thời lượng tính từ lúc tạo/cập nhật cache. |
| Khóa tạm để ngăn trùng xử lý trong 30 giây | **TTL tương đối** | Thời hạn ngắn gắn với lần tạo key; cần thêm thiết kế ownership/release. |
| Mã xác minh có hiệu lực đúng 3 phút từ lúc phát hành | **Deadline tuyệt đối nếu phát hành xảy ra trước khi ghi Redis** | Xử lý chậm không được tự cộng thêm 3 phút từ lúc lưu; nếu phát hành và lưu cùng một thao tác, TTL tương đối có thể phù hợp. |
| Khuyến mãi kết thúc lúc 23:59:59 theo lịch | **Deadline tuyệt đối** | Cố định theo mốc lịch và ZoneId. |
| Phiên hết hạn sau 20 phút không hoạt động | **TTL tương đối có gia hạn** | Mỗi hoạt động hợp lệ làm mới idle timeout. |
| Session có tuổi thọ tối đa 8 giờ kể từ khi login | **Deadline tuyệt đối** | Không cho gia hạn vượt hạn tối đa. |
| Một lượt thống kê theo phút UTC | **Thiết kế bucket theo mốc thời gian** | TTL giúp dọn bộ đếm nhưng bucket key xác định khoảng thống kê. |
| Lưu dữ liệu đến một ngày do hệ thống đối tác quy định | **Deadline tuyệt đối** | Tránh bị dịch mốc khi xử lý sự kiện muộn. |
| Dọn member trong Sorted Set khi score < cutoff | **Lệnh dọn theo score** | Đây không phải Redis TTL của từng member. |

### Tình huống phân tích: OTP phát hành trước khi lưu

Hệ thống tạo OTP lúc **10:00:00**, chính sách hợp lệ trong 3 phút. Do queue bị chậm, worker chỉ ghi vào Redis lúc **10:01:30**.

- Nếu worker dùng **SET EX 180**, OTP có thể sống đến **10:04:30**, tức dài thêm 90 giây so với thời hạn kể từ lúc phát hành.
- Nếu worker tính deadline = **10:03:00** và dùng **SET EXAT/PXAT** tương ứng, OTP không bị kéo dài hạn do xử lý chậm.

Đây không chỉ là lựa chọn kỹ thuật; nó phụ thuộc **sự kiện nào được xem là bắt đầu thời hạn hiệu lực**. Khi có nhiều service, event timestamp của nguồn phát hành và deadline phải là một phần rõ ràng của hợp đồng nghiệp vụ.

### Tình huống phân tích: nửa đêm và giờ UTC

Một giá trị phải hết hạn lúc **00:00 ngày 01/01/2030 ở Việt Nam**. Nếu gửi epoch của **2030-01-01T00:00:00Z**, Redis sẽ xóa muộn hơn 7 giờ so với mong muốn.

Trong Java:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant deadline = LocalDate.of(2030, 1, 1)
        .atStartOfDay(zone)
        .toInstant();
~~~

Chuyển kết quả này sang Unix epoch bằng **deadline.getEpochSecond()** hoặc **deadline.toEpochMilli()**, tùy lệnh Redis dùng EXAT hay PXAT. Việc dùng ZoneId đảm bảo biểu thức “nửa đêm Việt Nam” được diễn giải đúng.

## 20. Tổng kết các quy tắc cần ghi nhớ

1. **Relative expiration = thời lượng.** EXPIRE/PEXPIRE tính một khoảng sống kể từ lúc Redis xử lý lệnh.
2. **Absolute expiration = thời điểm cụ thể.** EXPIREAT/PEXPIREAT và SET EXAT/PXAT định nghĩa một deadline bằng Unix timestamp.
3. **TTL/PTTL trả thời gian còn lại**, còn **EXPIRETIME/PEXPIRETIME trả deadline tuyệt đối** trên Redis hỗ trợ lệnh.
4. **Đơn vị cực kỳ quan trọng:** EXPIRE/EXPIREAT dùng giây; PEXPIRE/PEXPIREAT dùng mili giây. EXAT/PXAT tương ứng giây/mili giây.
5. **Tạo key với expiration trong một lệnh** bằng SET EX/PX hoặc EXAT/PXAT khi được hỗ trợ, thay vì SET rồi gọi expire/expireAt riêng nếu cần tính nguyên tử.
6. **Duration khác Instant.** Duration không biết ngày/múi giờ; deadline theo lịch phải được chuyển từ ZoneId sang Instant trước khi gửi Redis.
7. **Đặt lại EXPIRE là thay deadline.** Hữu ích cho idle timeout, nhưng có thể sai với mốc hết hạn nghiệp vụ cố định.
8. **SET không kèm tùy chọn có thể làm mất TTL.** Kiểm soát những đường ghi đè và sử dụng KEEPTTL khi muốn giữ expiration hiện có.
9. **Expiration khác eviction và xóa chủ động.** Key có thể biến mất trước deadline do áp lực bộ nhớ hoặc client xóa.
10. **Thời gian tuyệt đối không phải scheduler.** Nếu cần hành động đúng thời điểm, dùng cơ chế vận hành thích hợp và kiểm tra mốc nghiệp vụ độc lập.

**Điểm cốt lõi:** trước khi gọi API của Spring Data Redis, hãy hỏi **“Dữ liệu phải sống bao lâu kể từ bây giờ, hay phải kết thúc tại một thời điểm đã định?”**. Nếu là một khoảng sống, dùng **Duration/expire** hoặc **SET có TTL**; nếu là một mốc lịch, chuyển đúng ZoneId thành **Instant** rồi dùng **expireAt** hoặc lệnh ghi với deadline tuyệt đối. Chọn đúng mô hình giúp tránh gia hạn ngoài ý muốn, lỗi lệch múi giờ và các khoảng hở làm key sống quá hạn.
