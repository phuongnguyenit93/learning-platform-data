# Thay đổi cấu hình ghi log và giới hạn áp dụng động

Trong vận hành Spring Boot, có những thông số cần thay đổi khi ứng dụng đang chạy. Nhóm vận hành có thể tăng mức log lên `DEBUG` để điều tra lỗi trong thời gian ngắn, sau đó trả về `INFO`. Một dịch vụ cũng có thể cần giảm hoặc tăng giới hạn request theo tải thực tế mà không phải build lại image.

Spring Cloud Config cung cấp cấu hình tập trung; Spring Cloud Context hỗ trợ refresh Environment và các bean có vòng đời phù hợp. Spring Boot Actuator cung cấp endpoint quản lý mức log trực tiếp. Kết hợp các cơ chế này đúng cách giúp thay đổi cấu hình có kiểm soát, đồng thời cần hiểu rõ trạng thái nào được làm mới, trạng thái nào bị reset và cách xác nhận từng instance đã áp dụng giá trị mới.

Bài viết dùng hai ví dụ xuyên suốt: thay đổi mức log của package `com.example.orders` và thay đổi giới hạn request của `orders-service`. Các ví dụ giả định Spring Boot 3.x, Spring Cloud release train tương thích và Java 17 trở lên.

## 1. Phân biệt refresh cấu hình với thao tác runtime

Không phải mọi thay đổi runtime đều đi qua cùng một cơ chế.

| Nhu cầu | Cơ chế phù hợp | Tác dụng |
| --- | --- | --- |
| Lấy lại cấu hình từ Config Server | `POST /actuator/refresh` | Làm mới Environment của một client |
| Phát refresh đến nhiều instance | Spring Cloud Bus, thường qua `/actuator/busrefresh` | Phát sự kiện để các client cùng refresh |
| Thay đổi log level ngay | Actuator `loggers` endpoint | Cập nhật logger trong LoggingSystem của instance |
| Làm mới bean giữ cấu hình | `@RefreshScope` hoặc cơ chế rebind | Tạo lại target bean hoặc cập nhật thuộc tính |
| Thay đổi trạng thái bên ngoài ứng dụng | API của hệ thống tương ứng | Cập nhật tài nguyên thực tế, ví dụ gateway hoặc distributed rate limiter |

Refresh không tự động làm mới mọi trạng thái trong JVM. Environment có thể đã nhận giá trị mới trong khi một singleton vẫn giữ bản sao cấu hình cũ. Ngược lại, thao tác đổi logger trực tiếp có thể tác động tức thì nhưng không thay đổi file cấu hình nguồn trong Git.

Vì vậy, hãy xác định rõ thay đổi nào là cấu hình mong muốn lâu dài, thay đổi nào chỉ là thao tác điều tra tạm thời và thành phần nào phải được tạo lại hoặc cập nhật.

## 2. Đặt cấu hình log và rate limit trong Config Server

Ví dụ file `orders-service-prod.yml` trong Git repository:

```yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
    com.example.orders.client: WARN

api:
  rate-limit:
    capacity: 100
    refill-period: 1m
```

Ý nghĩa:

- Logger của toàn ứng dụng bắt đầu ở mức `INFO`.
- Package `com.example.orders` ghi log ở mức `INFO`.
- Package client được giới hạn ở mức `WARN`.
- Bộ giới hạn request có dung lượng 100 token và nạp đầy trong một phút.

Tên thuộc tính và cấu trúc có thể được tổ chức theo chuẩn nội bộ của dự án. Điều quan trọng là các giá trị có một nguồn quản lý rõ ràng, được review và gắn với application/profile/label phù hợp.

Config Client khai báo kết nối Config Server:

```yaml
spring:
  application:
    name: orders-service
  profiles:
    active: prod
  config:
    import: "configserver:http://config-server:8888"
```

Khi triển khai container, địa chỉ Config Server phải là hostname mà client truy cập được trên mạng triển khai, không dùng `localhost` trừ khi server thực sự nằm trong cùng network namespace.

Sau khi thay đổi file cấu hình, commit vào Git và xác nhận Config Server trả đúng revision. Việc commit chỉ cập nhật nguồn; các client đang chạy vẫn cần refresh hoặc nhận sự kiện Bus.

## 3. Thay đổi log level bằng Actuator Loggers endpoint

Spring Boot Actuator cung cấp endpoint `loggers` để đọc và thay đổi mức log của một logger đang chạy. Endpoint này tác động trực tiếp lên LoggingSystem của instance.

Cần có dependency Actuator:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Expose endpoint trong cấu hình client:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,loggers,refresh
```

Mặc định, không nên expose tất cả endpoint Actuator. Chỉ mở những endpoint cần thiết và bảo vệ bằng Spring Security, mạng quản trị hoặc gateway nội bộ.

Đọc mức log hiện tại:

```bash
curl http://localhost:8080/actuator/loggers/com.example.orders
```

Đổi package sang `DEBUG`:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"DEBUG"}' \
  http://localhost:8080/actuator/loggers/com.example.orders
```

Có thể đổi logger cụ thể hơn để tránh tạo quá nhiều log:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"TRACE"}' \
  http://localhost:8080/actuator/loggers/com.example.orders.repository
```

Khi kết thúc điều tra, khôi phục mức log kế thừa từ cấu hình cha bằng cách gửi `null`:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":null}' \
  http://localhost:8080/actuator/loggers/com.example.orders
```

GET endpoint trả thông tin như `configuredLevel` và `effectiveLevel`. `configuredLevel` là mức được đặt trực tiếp cho logger; `effectiveLevel` là mức thực tế sau khi xét quan hệ kế thừa logger.

Đổi log level trực tiếp qua Actuator rất hữu ích khi cần điều tra một instance cụ thể. Tuy nhiên, đây là thay đổi runtime của instance, không tự ghi ngược vào Git. Khi ứng dụng restart, giá trị có thể trở lại theo cấu hình khởi động.

## 4. Thay đổi log level qua Config Server và refresh

Nếu muốn mức log là cấu hình có thể review và áp dụng đồng nhất, thay đổi `logging.level` trong Git:

```yaml
# orders-service-prod.yml
logging:
  level:
    com.example.orders: DEBUG
    com.example.orders.client: INFO
```

Sau đó:

1. Review và commit thay đổi.
2. Xác nhận Config Server trả giá trị mới cho đúng application/profile/label.
3. Gọi refresh trên client hoặc phát sự kiện Bus.
4. Kiểm tra logger bằng `GET /actuator/loggers/{logger-name}`.
5. Sau khi điều tra xong, commit giá trị log level cần khôi phục và refresh lần nữa.

Spring Cloud Context có cơ chế lắng nghe `EnvironmentChangeEvent` để cập nhật mức log từ các thuộc tính `logging.level.*` thông qua `LoggingRebinder`. Nhờ đó, thay đổi log level đến từ Environment có thể được áp dụng sau refresh mà không cần restart toàn bộ ứng dụng. Hãy kiểm tra hành vi trên release train thực tế và xác nhận bằng endpoint `loggers`, vì logger backend, cấu hình tùy biến hoặc cách nạp cấu hình có thể ảnh hưởng kết quả.

Có thể dùng Actuator `loggers` cho một thao tác tạm thời, còn Git/Config Server là nguồn mong muốn lâu dài. Nếu dùng cả hai, hãy có quy tắc rõ ràng để lần refresh tiếp theo không bất ngờ ghi đè thao tác điều tra hoặc giữ lại mức log quá chi tiết.

Không bật `DEBUG` hoặc `TRACE` diện rộng trong thời gian dài. Log có thể chứa thông tin request, định danh người dùng, header hoặc dữ liệu nhạy cảm; cần kiểm tra nội dung log, giới hạn phạm vi logger và thời gian áp dụng.

## 5. Refresh một Config Client

Config Client cần các dependency tương thích, thường gồm Config Client và Actuator. Spring Cloud Context được đưa vào thông qua các dependency Spring Cloud tương ứng.

Expose endpoint refresh:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh,loggers
```

Sau khi Config Server đã trả giá trị mới, gửi request:

```bash
curl -X POST http://localhost:8080/actuator/refresh
```

Endpoint thường trả về danh sách key có thay đổi trong Environment. Request này yêu cầu client làm mới cấu hình từ xa và phát sự kiện thay đổi môi trường. Các bean cấu hình được hỗ trợ rebind; bean thuộc `@RefreshScope` được đánh dấu để target cũ bị loại khỏi cache và tạo lại khi có lần truy cập tiếp theo.

Refresh không đồng nghĩa restart process. Các thread, connection pool, cache hoặc object tự giữ state không tự động được thay thế trừ khi chúng được thiết kế để tham gia vòng đời refresh hoặc có cơ chế cập nhật riêng.

Khi endpoint không được expose hoặc bị chặn bởi security, request sẽ không thành công. Chỉ expose refresh cho nhóm vận hành được phân quyền; không mở endpoint này công khai.

## 6. Áp dụng rate limit động bằng RefreshScope

Giới hạn request thường được dùng trong API gateway, filter hoặc interceptor. Ví dụ một token bucket có dung lượng 100 token và nạp lại theo thời gian. Thay đổi `capacity` hoặc `refill-period` cần cập nhật chính sách mà thành phần giới hạn request đang sử dụng.

Có thể tạo một bean rate limiter thuộc `@RefreshScope`. Khi refresh, target bean cũ bị loại bỏ; lần gọi tiếp theo tạo target mới với giá trị được đọc từ Environment mới.

Ví dụ cấu hình:

```yaml
api:
  rate-limit:
    capacity: 100
    refill-period: 1m
```

Một triển khai token bucket minh họa:

```java
package com.example.orders.limiter;

import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class LocalRateLimiter {

    private final int capacity;
    private final long refillPeriodNanos;
    private final ConcurrentMap<String, Bucket> buckets =
            new ConcurrentHashMap<>();

    public LocalRateLimiter(
            @Value("${api.rate-limit.capacity:100}") int capacity,
            @Value("${api.rate-limit.refill-period:1m}")
            Duration refillPeriod) {

        if (capacity < 1) {
            throw new IllegalArgumentException(
                    "api.rate-limit.capacity phải lớn hơn 0");
        }
        if (refillPeriod.isZero() || refillPeriod.isNegative()) {
            throw new IllegalArgumentException(
                    "api.rate-limit.refill-period phải lớn hơn 0");
        }

        this.capacity = capacity;
        this.refillPeriodNanos = refillPeriod.toNanos();
    }

    public boolean tryConsume(String clientKey) {
        Bucket bucket = buckets.computeIfAbsent(
                clientKey,
                key -> new Bucket(capacity, refillPeriodNanos));

        return bucket.tryConsume();
    }

    private static final class Bucket {
        private final int capacity;
        private final long refillPeriodNanos;
        private double tokens;
        private long lastRefillNanos = System.nanoTime();

        private Bucket(int capacity, long refillPeriodNanos) {
            this.capacity = capacity;
            this.refillPeriodNanos = refillPeriodNanos;
            this.tokens = capacity;
        }

        private synchronized boolean tryConsume() {
            long now = System.nanoTime();
            long elapsed = now - lastRefillNanos;

            if (elapsed > 0) {
                double refill = (double) elapsed * capacity
                        / refillPeriodNanos;
                tokens = Math.min(capacity, tokens + refill);
                lastRefillNanos = now;
            }

            if (tokens < 1.0) {
                return false;
            }

            tokens -= 1.0;
            return true;
        }
    }
}
```

Bean được inject vào filter hoặc service như một proxy:

```java
@Component
public class OrderRequestGuard {

    private final LocalRateLimiter rateLimiter;

    public OrderRequestGuard(LocalRateLimiter rateLimiter) {
        this.rateLimiter = rateLimiter;
    }

    public boolean allow(String authenticatedClientId) {
        return rateLimiter.tryConsume(authenticatedClientId);
    }
}
```

Ở tầng HTTP, nếu `allow(...)` trả về `false`, ứng dụng có thể trả mã `429 Too Many Requests` và header `Retry-After` nếu xác định được thời gian chờ phù hợp. Key giới hạn nên lấy từ danh tính client đã xác thực hoặc tenant ID đáng tin cậy, không dùng một header tùy ý do người gọi tự đặt.

Ví dụ trên minh họa cơ chế làm mới policy, không phải một thư viện rate limiting hoàn chỉnh. Nó lưu bucket trong bộ nhớ của một JVM, map không tự giới hạn số lượng key và không chia sẻ trạng thái giữa các instance.

## 7. Những tác động cần hiểu khi refresh rate limiter

Khi `LocalRateLimiter` được refresh, target cũ và map bucket của nó bị loại bỏ. Target mới tạo map rỗng; bucket mới bắt đầu với đầy đủ token theo capacity mới. Điều này có thể tạo một đợt request được phép tăng đột biến ngay sau refresh.

Ngoài ra:

- Nếu ứng dụng chạy nhiều replica, mỗi replica có bucket riêng; giới hạn thực tế có thể nhân lên theo số instance.
- Restart hoặc refresh có thể reset trạng thái token bucket.
- Một key riêng cho mỗi người gọi có thể làm map tăng không giới hạn nếu không có eviction.
- Việc thay đổi capacity và refill period cần được validate để tránh giá trị bằng zero, âm hoặc quá lớn.
- Bean khác giữ tham chiếu trực tiếp tới object cũ thay vì proxy có thể tiếp tục dùng policy cũ.

Với giới hạn theo tenant hoặc API key trên nhiều instance, nên dùng API gateway hoặc rate limiter có kho trạng thái dùng chung như Redis. Khi cập nhật policy, cần xác định cách cập nhật cấu hình và trạng thái bucket trong hệ thống đó. Không nên coi việc refresh một bean cục bộ là cơ chế đồng bộ giới hạn toàn cụm.

Nếu muốn giữ trạng thái bucket qua refresh, có thể tách policy khỏi state: refresh chỉ thay đổi policy object; limiter dùng chung cập nhật capacity/refill cho các bucket hiện có theo quy tắc đã định nghĩa. Cách này phức tạp hơn vì phải quyết định xử lý token đang có, bucket đang vượt capacity và request đang chạy dở. Hãy chọn một quy tắc nhất quán và kiểm thử trước khi áp dụng production.

## 8. Phát refresh đến nhiều instance bằng Spring Cloud Bus

Khi một dịch vụ có nhiều replica, gọi `/actuator/refresh` trên từng instance có thể tốn công và dễ bỏ sót. Spring Cloud Bus dùng message broker để phát sự kiện refresh đến các ứng dụng đã tham gia Bus.

Ví dụ với RabbitMQ, các ứng dụng cần dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bus-amqp</artifactId>
</dependency>
```

Cấu hình kết nối broker:

```yaml
spring:
  rabbitmq:
    host: rabbitmq
    port: 5672
    username: ${RABBITMQ_USER}
    password: ${RABBITMQ_PASSWORD}
```

Các client phải kết nối cùng broker và có cấu hình Bus tương thích. Expose endpoint trên một điểm quản trị được bảo vệ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,busrefresh
```

Sau khi Git đã có cấu hình mới và Config Server có thể trả revision mới, phát refresh event:

```bash
curl -X POST http://localhost:8080/actuator/busrefresh
```

Sự kiện được phân phối đến các ứng dụng tham gia Bus; mỗi client nhận sự kiện sẽ làm mới Environment và refresh các bean phù hợp. Theo dõi log của từng instance để xác nhận event đã được nhận và xử lý. Bus không bảo đảm một bean không hỗ trợ refresh tự thay đổi state.

Một số phiên bản Spring Cloud Bus hỗ trợ giới hạn đích bằng tham số destination, cho phép refresh một service hoặc nhóm instance thay vì toàn bộ. Cú pháp và cách định tuyến cần xác minh theo phiên bản đang dùng. Trước khi phát sự kiện diện rộng, thử trên một nhóm nhỏ và xác nhận kết quả.

## 9. Kiểm thử thay đổi log và rate limit

Một quy trình kiểm thử có thể thực hiện trên môi trường staging:

1. Ghi nhận log level hiện tại bằng `GET /actuator/loggers/com.example.orders`.
2. Ghi nhận rate limit hiện tại, ví dụ capacity 100 token trong một phút.
3. Commit cấu hình mới với log level `DEBUG` và capacity 50.
4. Gọi endpoint Config Server để xác nhận application, profile, label và revision.
5. Gửi `POST /actuator/refresh` cho một instance hoặc phát `busrefresh`.
6. Đọc lại log level và kiểm tra logger thực sự áp dụng `DEBUG`.
7. Gửi request theo cùng client key để kiểm tra giới hạn mới.
8. Xác nhận log không chứa secret và mã 429 xuất hiện đúng khi bucket hết token.
9. Thử refresh lần nữa với cấu hình khôi phục và xác nhận trạng thái quay về mong muốn.

Có thể kiểm tra logger:

```bash
curl http://localhost:8080/actuator/loggers/com.example.orders
```

Có thể kiểm tra Config Server trả đúng property source:

```bash
curl http://config-server:8888/orders-service/prod/main
```

Đối với rate limiter, không nên chỉ kiểm tra giá trị trong Environment. Cần kiểm tra hành vi của component đang thực thi giới hạn, vì bean có thể chưa được refresh, một object khác có thể đang giữ state cũ hoặc limiter thực tế nằm ở gateway bên ngoài ứng dụng.

Integration test nên bao gồm ít nhất hai tình huống: thay đổi capacity/refill period rồi refresh và xác nhận bean mới sử dụng policy mới; đồng thời kiểm tra trạng thái token bucket được xử lý đúng theo quy tắc reset hoặc giữ state đã chọn.

## 10. Bảo vệ endpoint và giới hạn tác động

Các endpoint `refresh`, `busrefresh` và `loggers` có thể thay đổi hành vi ứng dụng đang chạy. Nếu người không có quyền gọi được endpoint, họ có thể bật log quá chi tiết, làm lộ dữ liệu hoặc thay đổi giới hạn request.

Một số biện pháp cần áp dụng:

- Chỉ expose endpoint cần dùng; không expose toàn bộ Actuator.
- Bảo vệ bằng xác thực và phân quyền theo vai trò vận hành.
- Giới hạn truy cập qua mạng quản trị hoặc gateway nội bộ.
- Ghi audit ai thay đổi logger, key cấu hình, thời điểm và phạm vi instance.
- Không log password, token, header nhạy cảm hoặc toàn bộ Environment.
- Đặt thời hạn cho mức log DEBUG/TRACE và có bước khôi phục rõ ràng.
- Validate rate limit trước khi áp dụng; không cho phép giá trị không hợp lệ.
- Thử thay đổi trên một instance hoặc nhóm nhỏ trước khi phát tán toàn cụm.
- Theo dõi metric request, tỷ lệ 429, log volume và lỗi sau refresh.

Nếu cần thay đổi khẩn cấp qua Actuator loggers, hãy ghi nhận đây là thao tác runtime ngoài Git và đồng bộ lại desired state sau đó. Nếu không, lần restart hoặc refresh tiếp theo có thể đưa ứng dụng về mức log khác với trạng thái operator đang quan sát.

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| POST refresh trả 404 | Endpoint chưa được expose hoặc Actuator không có trên classpath | Kiểm tra dependency và `management.endpoints.web.exposure.include` |
| POST refresh trả 401/403 | Security policy không cho phép caller | Kiểm tra role và rule bảo vệ endpoint |
| Config Server có giá trị mới nhưng bean vẫn cũ | Bean giữ state và không thuộc refresh scope/rebind | Kiểm tra annotation và proxy bean |
| Log level không đổi sau refresh | Logger property chưa được áp dụng hoặc logger backend tùy biến | GET Actuator loggers và kiểm tra LoggingSystem |
| Actuator đổi log nhưng restart lại mất | Runtime logger override không được ghi vào nguồn cấu hình | Commit desired log level vào Git nếu cần duy trì |
| Một số replica chưa đổi cấu hình | Bus event không đến được tất cả client hoặc client chưa kết nối broker | Kiểm tra broker, subscription và log từng instance |
| Rate limit tăng đột biến sau refresh | Bucket state bị reset và bắt đầu đầy token | Kiểm tra lifecycle của limiter và chính sách giữ/reset state |
| Giới hạn khác nhau giữa các replica | Mỗi JVM giữ bucket cục bộ riêng | Dùng gateway hoặc store phân tán nếu cần quota toàn cụm |
| Bộ nhớ tăng theo số client key | Map bucket không có eviction | Giới hạn cardinality hoặc dùng thư viện có cache/expiry |

Khi điều tra, tách ba câu hỏi: Config Server có trả giá trị mới không; client đã cập nhật Environment chưa; component thực thi có đang dùng policy mới không. Kiểm tra theo thứ tự này giúp xác định lỗi ở nguồn cấu hình, cơ chế refresh hay state của thành phần runtime.

## 12. Quy trình thay đổi an toàn

Với một thay đổi log level hoặc rate limit, quy trình vận hành nên có:

1. Xác định mục tiêu và phạm vi: một logger, một service hay toàn bộ instance.
2. Xác định thay đổi là tạm thời hay mong muốn lâu dài.
3. Chọn Actuator loggers cho thao tác chẩn đoán tức thời; chọn Git/Config Server cho cấu hình mong muốn có review.
4. Review giá trị rate limit, giới hạn trên/dưới và tác động tải.
5. Commit cấu hình và xác nhận Config Server trả đúng revision.
6. Refresh một instance hoặc nhóm nhỏ; kiểm tra logger và hành vi rate limiter.
7. Mở rộng rollout qua Bus nếu kết quả đúng.
8. Theo dõi log volume, latency, throughput và tỷ lệ 429.
9. Ghi nhận thay đổi runtime và khôi phục cấu hình sau khi hết thời gian điều tra.
10. Lưu lại revision, người thực hiện và kết quả kiểm tra để phục vụ audit.

Thay đổi cấu hình động giúp giảm restart và rút ngắn thời gian phản ứng khi vận hành, nhưng chỉ an toàn khi mỗi thành phần có vòng đời cập nhật rõ ràng. Actuator loggers thay đổi mức log của instance; refresh cập nhật Environment và các bean hỗ trợ refresh; Spring Cloud Bus phân phối sự kiện đến nhiều client. Với rate limiter có trạng thái, phải quyết định rõ cách xử lý token và dữ liệu đang chạy khi policy thay đổi. Khi xác nhận được cả nguồn cấu hình, giá trị hiệu lực và hành vi thực tế, nhóm có thể điều chỉnh logging và giới hạn request nhất quán mà vẫn kiểm soát được tác động.

