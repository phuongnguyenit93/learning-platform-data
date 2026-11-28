# Đồng bộ timestamp và timezone

## 1. Vì sao log của các module phải thống nhất thời gian?

Trong ứng dụng Spring Boot dùng **Spring Modulith**, các application module có thể phối hợp bằng lời gọi API hoặc domain event. Ví dụ, module `ordering` lưu đơn hàng và phát `OrderPlaced`; module `notification` nhận event bất đồng bộ để gửi email; module `payment` gọi cổng thanh toán. Khi sự cố xảy ra, đội vận hành cần ghép log từ nhiều module để biết bước nào diễn ra trước, thời gian chờ ở đâu và lỗi bắt đầu từ thời điểm nào.

Nếu mỗi service, container hoặc log appender ghi timestamp theo timezone riêng, cùng một sự kiện có thể xuất hiện dưới những giờ khác nhau. Một log ghi `09:00` theo UTC+7 và log khác ghi `02:00Z` thực ra có thể là cùng một thời điểm, nhưng người đọc khó nhận ra nếu timestamp không có offset. Nếu đồng hồ máy chủ lệch nhau, ngay cả log đã chuẩn hóa UTC cũng có thể bị sắp xếp sai theo thời gian.

Đồng bộ thời gian vì vậy gồm **hai việc khác nhau**:

1. **Chuẩn hóa biểu diễn:** thống nhất cách ghi timestamp, thường dùng UTC và định dạng ISO 8601/RFC 3339 có offset rõ ràng.
2. **Đồng bộ đồng hồ thực:** bảo đảm các node/container lấy thời gian hệ thống từ nguồn thời gian đáng tin cậy và có độ lệch nằm trong giới hạn chấp nhận được.

Chỉ đổi timezone sang UTC không sửa được clock drift. Ngược lại, đồng bộ NTP tốt nhưng log không ghi offset vẫn khiến việc đối chiếu giữa các vùng khó hiểu.

Bài học thuộc chương **Logging** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module này hướng dẫn dùng Spring Modulith để tài liệu hóa ranh giới application module và quan sát tương tác khi ứng dụng Spring Boot vận hành, thông qua module graph, Actuator, event metrics, tracing và context propagation.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Chọn `Instant`, `OffsetDateTime`, `ZonedDateTime` và `LocalDateTime` đúng ngữ nghĩa.
- Chuẩn hóa timestamp log và telemetry về UTC mà vẫn giữ được thời điểm thực.
- Cấu hình Logback/Spring Boot ghi timestamp có offset, đồng thời giữ trace ID và span ID.
- Phân biệt thời điểm event xảy ra, event được publish, listener xử lý và log được ghi.
- Đồng bộ đồng hồ ở máy chủ/container bằng NTP/chrony và nhận biết clock skew.
- Cấu hình database/JDBC dùng timezone nhất quán.
- Dùng monotonic clock để đo duration thay vì trừ hai wall-clock timestamps.
- Kiểm thử thời gian xác định bằng `Clock.fixed` và xử lý timezone/DST đúng cách.

## 2. Timestamp, timezone và clock là ba khái niệm khác nhau

### 2.1. Instant biểu diễn một thời điểm tuyệt đối

`Instant` trong Java biểu diễn một điểm trên timeline theo UTC, không gắn với timezone địa phương. Ví dụ:

~~~java
Instant occurredAt = Instant.parse("2026-11-27T02:00:00Z");
~~~

Đây là một thời điểm duy nhất. Khi hiển thị tại Việt Nam, nó có thể được chuyển thành `2026-11-27T09:00:00+07:00`; hai biểu diễn cùng một instant.

### 2.2. Offset và ZoneId mang thông tin khác nhau

| Kiểu Java | Chứa thông tin | Dùng khi nào? |
| --- | --- | --- |
| `Instant` | Thời điểm tuyệt đối theo UTC. | Log timestamp, event occurrence time, thời điểm tạo/cập nhật dữ liệu. |
| `OffsetDateTime` | Ngày giờ kèm UTC offset như `+07:00`. | API cần biểu diễn timestamp kèm offset rõ ràng. |
| `ZonedDateTime` | Ngày giờ, offset và vùng timezone như `Asia/Ho_Chi_Minh`. | Quy tắc lịch theo giờ địa phương, có DST hoặc quy tắc vùng. |
| `LocalDateTime` | Ngày giờ trên đồng hồ địa phương, không có offset/zone. | Giờ mở cửa hoặc thời gian địa phương khi zone được lưu riêng. Không đủ để biểu diễn một thời điểm toàn cầu. |
| `LocalDate` / `LocalTime` | Ngày hoặc giờ địa phương, không có zone. | Ngày sinh, giờ mở cửa, giờ làm việc theo ngữ cảnh. |

Không dùng `LocalDateTime` đơn lẻ làm timestamp xuyên service. Chuỗi `2026-11-27T09:00:00` không cho biết nó thuộc UTC, UTC+7 hay một vùng có daylight saving time.

### 2.3. UTC không phải timezone của người dùng

UTC là chuẩn thuận tiện để lưu và truyền thời điểm. Khi hiển thị cho người dùng, chuyển `Instant` sang timezone phù hợp:

~~~java
Instant instant = Instant.parse("2026-11-27T02:00:00Z");

ZonedDateTime vietnamTime = instant.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh")
);

System.out.println(vietnamTime);
// 2026-11-27T09:00+07:00[Asia/Ho_Chi_Minh]
~~~

Không cần thay đổi instant khi đổi timezone; chỉ thay đổi cách biểu diễn. Dùng IANA Zone ID như `Asia/Ho_Chi_Minh`, `Europe/Paris` hoặc `America/New_York` khi cần quy tắc vùng. Một offset cố định như `+07:00` không mô tả quy tắc DST của một vùng khác.

## 3. Chuẩn timestamp cho log và event

### 3.1. Chọn UTC và định dạng có offset

Một format dễ trao đổi giữa log aggregator, tracing backend và service là ISO 8601/RFC 3339 với UTC:

~~~text
2026-11-27T02:00:00.123Z
~~~

Hoặc biểu diễn cùng thời điểm bằng offset:

~~~text
2026-11-27T09:00:00.123+07:00
~~~

Hai giá trị trên tương đương về thời điểm. Chữ `Z` có nghĩa offset UTC. Không ghi timestamp không có offset nếu nó được dùng để đối chiếu giữa nhiều service.

Nên thống nhất:

- Dùng UTC trong log, event contract và dữ liệu lưu trữ cần so sánh xuyên hệ thống.
- Dùng ISO 8601/RFC 3339 có `Z` hoặc offset tường minh.
- Thống nhất độ chính xác khi hiển thị, ví dụ milliseconds; không cắt độ chính xác trong dữ liệu nếu nghiệp vụ cần microseconds/nanoseconds.
- Giữ timezone gốc riêng nếu nghiệp vụ cần biết vùng lịch của người dùng, chẳng hạn lịch hẹn theo `Asia/Ho_Chi_Minh`.
- Parse timestamp theo định dạng đã công bố; từ chối hoặc xử lý rõ chuỗi thiếu offset.

### 3.2. Phân biệt các loại timestamp trong event flow

Một domain event có thể đi qua nhiều mốc thời gian. Đừng dùng một trường tên `timestamp` cho mọi ý nghĩa:

| Trường đề xuất | Ý nghĩa |
| --- | --- |
| `occurredAt` | Thời điểm sự kiện nghiệp vụ thực sự xảy ra. |
| `publishedAt` | Thời điểm publisher công bố/gửi event, nếu ứng dụng ghi nhận riêng. |
| `processedAt` | Thời điểm listener bắt đầu hoặc hoàn tất xử lý; nên tách `processingStartedAt` và `processedAt` nếu cần đo duration. |
| Log `timestamp` | Thời điểm bản ghi log được tạo/ghi nhận bởi logging pipeline. |
| Collector observed time | Thời điểm collector quan sát/nhận bản ghi telemetry. |

Ví dụ, một đơn hàng được tạo lúc 09:00 nhưng listener gửi email lúc 09:00:03. Log listener xuất hiện sau log publisher là bình thường. Chênh lệch ba giây có thể là thời gian commit, queueing hoặc scheduling, không nhất thiết là clock skew.

### 3.3. Ví dụ domain event dùng Instant

~~~java
package com.example.shop.ordering;

import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
    UUID orderId,
    Instant occurredAt
) {}
~~~

Service nên nhận `Clock` qua dependency injection:

~~~java
package com.example.shop.ordering;

import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final Clock clock;
    private final ApplicationEventPublisher events;

    public OrderService(Clock clock, ApplicationEventPublisher events) {
        this.clock = clock;
        this.events = events;
    }

    public UUID placeOrder() {
        UUID orderId = UUID.randomUUID();
        events.publishEvent(new OrderPlaced(orderId, clock.instant()));
        return orderId;
    }
}
~~~

`occurredAt` ở đây là thời điểm code nghiệp vụ tạo event. Nếu event được lưu trong outbox hoặc publication registry, thời điểm persist/publish có thể khác và cần trường hoặc metadata riêng nếu bài toán cần đo. Không thay `occurredAt` bằng thời điểm listener nhận event.

### 3.4. Dùng Clock thay cho gọi thời gian rải rác

Khai báo một bean:

~~~java
package com.example.shop.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Inject cùng `Clock` vào service, listener và các thành phần cần thời gian. Lợi ích:

- Logic dễ kiểm thử với clock cố định.
- Không gọi `Instant.now()` rải rác trong domain code.
- Có một điểm cấu hình rõ ràng cho nguồn wall clock của ứng dụng.
- Có thể thay clock trong test mà không phải sửa logic nghiệp vụ.

`Clock.systemUTC()` vẫn đọc system clock của máy chạy ứng dụng; nó **không đồng bộ NTP** và không sửa clock drift ở node.

## 4. Cấu hình Logback và Spring Boot ghi UTC

Spring Boot mặc định thường dùng Logback nếu không thay logging implementation. Với Logback, pattern date converter cho phép chỉ định timezone sau dấu phẩy.

### 4.1. Cấu hình nhanh qua application.yml

Ví dụ:

~~~yaml
logging:
  pattern:
    console: "%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX,UTC} %-5level [%thread] %logger{36} traceId=%X{traceId} spanId=%X{spanId} - %msg%n"
    file: "%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX,UTC} %-5level [%thread] %logger{36} traceId=%X{traceId} spanId=%X{spanId} - %msg%n"
~~~

Giải thích:

- `%d{...,UTC}` định dạng timestamp theo UTC.
- `XXX` in offset theo dạng `Z` hoặc `+hh:mm`.
- `%thread` giúp nhận biết log đến từ thread nào, hữu ích khi listener chạy bất đồng bộ.
- `%X{traceId}` và `%X{spanId}` đọc correlation fields trong MDC khi Micrometer Tracing logging integration đã thiết lập chúng.
- `%msg%n` ghi message và xuống dòng.

Nếu dùng Log4j2 hoặc logging encoder khác, pattern và cách đặt timezone có thể khác. Hãy kiểm tra logging implementation thực tế thay vì copy cú pháp Logback.

### 4.2. Cấu hình bằng logback-spring.xml

Khi cần kiểm soát appender rõ hơn:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX,UTC} %-5level [%thread] %logger{36} traceId=%X{traceId} spanId=%X{spanId} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đặt file tại `src/main/resources/logback-spring.xml` nếu dùng Spring Boot extensions. Nếu thay file cấu hình logging mặc định, hãy giữ lại các appender, rolling policy, file output và cấu hình level mà ứng dụng đang cần; ví dụ trên chỉ minh họa format console tối thiểu.

### 4.3. Ví dụ log sau khi chuẩn hóa

~~~text
2026-11-27T02:00:00.123Z INFO  [http-nio-8080-exec-1] c.e.shop.ordering.OrderService traceId=4bf92f... spanId=00f067... - event=OrderPlaced orderId=...
2026-11-27T02:00:00.145Z INFO  [module-event-1] c.e.shop.notification.OrderListener traceId=4bf92f... spanId=9c12ab... - event=OrderPlaced received
2026-11-27T02:00:00.188Z INFO  [module-event-1] c.e.shop.notification.OrderListener traceId=4bf92f... spanId=9c12ab... - notification sent
~~~

Các dòng trên là dữ liệu giả lập. Cùng trace ID cho thấy các log có thể được liên kết với một trace; span ID khác nhau cho biết chúng thuộc những span khác nhau. Nếu context không được truyền qua executor, listener có thể không có trace ID hoặc có trace ID khác.

**Không ghi toàn bộ payload, email, token hoặc thông tin thanh toán vào log để bù cho việc thiếu trace.** Hãy dùng correlation ID được phép và các field nghiệp vụ tối thiểu.

## 5. Structured logging và timestamp trong pipeline

Log dạng text phù hợp đọc nhanh, nhưng hệ thống tập trung thường dùng JSON để parser không phải tách chuỗi tự do. Một bản ghi có cấu trúc có thể như sau:

~~~json
{
  "@timestamp": "2026-11-27T02:00:00.123Z",
  "level": "INFO",
  "service.name": "shop-service",
  "log.logger": "com.example.shop.ordering.OrderService",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "event.name": "OrderPlaced",
  "occurredAt": "2026-11-27T02:00:00.100Z"
}
~~~

Trong ví dụ:

- `@timestamp` là thời điểm log record được ghi nhận.
- `occurredAt` là thời điểm nghiệp vụ trong event.
- `traceId`/`spanId` nối log với trace.
- `service.name` nhận diện service/ứng dụng.

Không ghi `@timestamp` bằng giờ địa phương thiếu offset. Nếu dùng Spring Boot structured logging hoặc JSON encoder, cấu hình cụ thể phụ thuộc phiên bản Boot và encoder; cần xác nhận output thực tế có UTC/offset đúng như mong đợi.

### 5.1. Timestamp của log và observed timestamp của collector

Trong pipeline tập trung, có thể tồn tại hai thời điểm:

1. **Timestamp nguồn:** thời điểm ứng dụng tạo log record.
2. **Observed timestamp:** thời điểm collector nhận hoặc quan sát record.

Hai thời điểm khác nhau giúp nhận ra log bị trễ do buffering, mạng hoặc queue. Nếu collector ghi đè timestamp nguồn bằng thời điểm nhận, đội vận hành mất khả năng đo độ trễ vận chuyển và có thể hiểu nhầm thứ tự sự kiện.

Với OpenTelemetry Logs data model, `Timestamp` và `ObservedTimestamp` có ý nghĩa riêng. Hãy giữ cả hai khi pipeline có thể cung cấp chúng; không thay timestamp nguồn bằng thời điểm ingest nếu cần điều tra event chronology.

## 6. Đồng bộ đồng hồ ở máy chủ và container

### 6.1. UTC format không sửa clock skew

Giả sử node A nhanh hơn giờ chuẩn 800 ms, node B chậm hơn 500 ms. Cả hai đều ghi UTC:

~~~text
Node A: 2026-11-27T02:00:00.800Z
Node B: 2026-11-27T01:59:59.500Z
~~~

Nếu cùng một hoạt động đi qua hai node, timestamp có thể tạo cảm giác node B chạy trước node A dù thực tế nó nhận request sau. Đổi timezone không thay đổi độ lệch này.

**Clock skew** là độ lệch giữa đồng hồ của một node và nguồn tham chiếu hoặc giữa các node. Độ lệch nhỏ có thể chấp nhận được trong nhiều ứng dụng; hệ thống tài chính, audit, giao dịch phân tán hoặc đo SLA có thể cần ngưỡng chặt hơn và giám sát riêng.

### 6.2. Dùng NTP hoặc chrony ở tầng hạ tầng

Đồng bộ thời gian hệ điều hành thường do hạ tầng quản lý:

- Linux có thể dùng `chronyd`/`chronyc` hoặc dịch vụ NTP tương đương.
- Máy ảo, Kubernetes node và host container cần được đồng bộ với nguồn thời gian đáng tin cậy.
- Môi trường có yêu cầu chính xác cao có thể dùng nguồn PTP hoặc hạ tầng time service chuyên dụng.
- Theo dõi trạng thái đồng bộ, offset, jitter và mất kết nối tới time source.

Ví dụ lệnh kiểm tra trên Linux khi hệ thống có chrony:

~~~bash
chronyc tracking
chronyc sources -v
timedatectl status
~~~

Các lệnh chỉ đọc trạng thái. Cách cài đặt, bật dịch vụ và cấu hình nguồn thời gian phụ thuộc bản phân phối Linux, quyền quản trị và hạ tầng. Ứng dụng Spring Boot không nên tự chạy lệnh NTP để sửa đồng hồ của node.

### 6.3. Container dùng clock của host

Container thông thường chia sẻ system clock của kernel host. Nếu nhiều container trên cùng node ghi timestamp lệch, nguyên nhân thường nằm ở host clock, cấu hình timezone/formatter hoặc pipeline log, không phải mỗi container có một đồng hồ độc lập.

Trong Kubernetes, cần giám sát node time synchronization và xử lý node bị drift. Restart pod không phải cách sửa clock skew của host. Khi pod chuyển node, log có thể xuất hiện timestamp khác nếu node mới chưa đồng bộ.

### 6.4. Giám sát clock offset

Không chỉ kiểm tra timezone một lần khi triển khai. Nên theo dõi:

- Offset so với time source.
- Trạng thái NTP/chrony synchronization.
- Jitter hoặc thay đổi đột ngột của clock.
- Số node không đồng bộ.
- Tương quan giữa source timestamp và collector observed timestamp.

Nếu hạ tầng có metric clock offset, tạo alert theo ngưỡng vận hành đã thống nhất. Đừng tự đặt một ngưỡng millisecond cho mọi hệ thống; yêu cầu phụ thuộc độ chính xác nghiệp vụ và độ ổn định của time source.

## 7. Database và JDBC cũng cần timezone nhất quán

Ngay cả khi log ghi UTC, dữ liệu database có thể bị diễn giải sai nếu schema hoặc session timezone không rõ.

### 7.1. PostgreSQL: timestamp with time zone và without time zone

Trong PostgreSQL:

- `timestamp with time zone` (thường viết `timestamptz`) biểu diễn một instant. PostgreSQL chuẩn hóa thời điểm nội bộ và hiển thị theo timezone của session.
- `timestamp without time zone` chỉ là ngày giờ địa phương, không mang offset/zone.

Ví dụ schema cho thời điểm event:

~~~sql
CREATE TABLE order_event (
    id UUID PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL
);
~~~

Có thể đặt timezone session là UTC:

~~~sql
SET TIME ZONE 'UTC';
~~~

`timestamptz` không lưu lại tên zone gốc như `Asia/Ho_Chi_Minh`; nó lưu thời điểm. Nếu nghiệp vụ cần giữ vùng lịch đã chọn, lưu thêm `zone_id` riêng.

### 7.2. Cấu hình Hibernate/JDBC

Với Hibernate, có thể cấu hình JDBC timezone:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          time_zone: UTC
~~~

Đây là cấu hình Hibernate; hiệu quả còn phụ thuộc mapping Java type, JDBC driver và kiểu cột database. Hãy xác minh round-trip bằng một giá trị `Instant` đã biết, không chỉ dựa vào cấu hình.

### 7.3. Lưu thời điểm và lưu timezone nghiệp vụ

Ví dụ lịch hẹn lúc 09:00 tại Việt Nam:

- Thời điểm tuyệt đối: `Instant` tương ứng.
- Vùng lịch: `Asia/Ho_Chi_Minh`.
- Giờ địa phương ban đầu: 09:00.

Nếu chỉ lưu instant, ứng dụng vẫn hiển thị được giờ tương đương ở các vùng khác. Nếu cần bảo toàn ý nghĩa “09:00 giờ địa phương” cho lịch định kỳ hoặc audit, lưu cả `ZoneId` và quy tắc nghiệp vụ.

## 8. DST và giờ địa phương

Một số vùng có daylight saving time (DST), khiến đồng hồ địa phương nhảy tới hoặc lùi lại theo mùa. Có hai trường hợp khó:

- **Gap:** một số giờ địa phương không tồn tại khi đồng hồ nhảy tới.
- **Overlap:** một số giờ địa phương xuất hiện hai lần khi đồng hồ lùi lại.

Ví dụ, một lịch định kỳ “09:00 mỗi ngày tại Europe/Paris” phải dùng `ZoneId` để áp dụng quy tắc vùng theo từng ngày. Không cộng cố định 24 giờ vào một instant rồi giả định giờ địa phương vẫn là 09:00.

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDate date = LocalDate.of(2026, 10, 25);
LocalTime localTime = LocalTime.of(9, 0);

ZonedDateTime appointment = ZonedDateTime.of(date, localTime, zone);
Instant scheduledAt = appointment.toInstant();
~~~

Nếu thời gian rơi vào gap/overlap, cần xác định chính sách nghiệp vụ: đẩy tới thời điểm hợp lệ tiếp theo, chọn offset sớm/muộn hay yêu cầu người dùng chọn lại. Không để mặc định thư viện quyết định thay cho quy tắc nghiệp vụ quan trọng.

Đối với log vận hành, tránh ghi giờ địa phương không offset. Nếu muốn người trực ở Việt Nam đọc dễ hơn, có thể hiển thị thêm giờ địa phương trong giao diện, nhưng giữ UTC/offset chuẩn trong log gốc.

## 9. Đo duration bằng monotonic clock, không trừ wall-clock timestamps

`Instant.now()` và `Clock.systemUTC()` đọc **wall clock** của hệ điều hành. Đồng hồ này có thể được điều chỉnh bởi NTP, người quản trị hoặc virtualization. Nếu lấy hai instant để đo duration, đồng hồ có thể nhảy lùi hoặc tiến:

~~~java
Instant start = Instant.now();
doWork();
Instant end = Instant.now();
Duration elapsed = Duration.between(start, end);
~~~

Đoạn code trên hữu ích khi cần thời điểm bắt đầu/kết thúc để audit, nhưng không phải lựa chọn tốt nhất để đo thời gian thực thi chính xác.

Với duration, dùng monotonic clock như `System.nanoTime()`:

~~~java
long start = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - start;
Duration elapsed = Duration.ofNanos(elapsedNanos);
~~~

`nanoTime()` không biểu diễn ngày giờ, không dùng để ghi timestamp hoặc so sánh giữa process/máy. Nó chỉ phù hợp đo khoảng thời gian trong cùng một tiến trình. Với ứng dụng Spring Boot, Micrometer `Timer` thường là lựa chọn tốt hơn vì có thể xuất count, total time và phân phối độ trễ.

~~~java
Timer timer = registry.timer("payment.authorization");
timer.record(() -> paymentGateway.authorize(orderId));
~~~

Timer dùng clock/registry phù hợp để đo duration và xuất metrics; không cần tự trừ hai wall-clock timestamps.

## 10. Đồng bộ timestamp với trace và log correlation

### 10.1. Timestamp giúp đặt sự kiện trên timeline; trace ID giúp liên kết nhân quả

Timestamp trả lời “log được ghi lúc nào?”. Trace ID trả lời “log/span này thuộc luồng xử lý nào?”. Hai thông tin bổ sung nhau.

Trong Micrometer Tracing/Spring Boot, trace context thường được đưa vào MDC để logging pattern có thể in:

- `traceId`: định danh trace.
- `spanId`: định danh span hiện hành.

Khi ứng dụng xử lý async, context propagation giúp MDC/tracing context đi cùng task nếu executor được cấu hình đúng. Nhưng timestamp đồng bộ không tự nối trace; trace ID giống nhau cũng không đảm bảo các node có đồng hồ chính xác.

### 10.2. Ví dụ log event trong Spring Modulith listener

~~~java
package com.example.shop.notification;

import com.example.shop.ordering.OrderPlaced;
import java.time.Clock;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderNotificationListener.class);

    private final Clock clock;

    OrderNotificationListener(Clock clock) {
        this.clock = clock;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        Instant processingStartedAt = clock.instant();
        log.info(
            "event=OrderPlaced orderId={} occurredAt={} processingStartedAt={}",
            event.orderId(),
            event.occurredAt(),
            processingStartedAt
        );

        // Thực hiện gửi thông báo.
    }
}
~~~

Trong log pattern, timestamp đầu dòng là thời điểm log được ghi; `occurredAt` là thời điểm nghiệp vụ; `processingStartedAt` là thời điểm listener bắt đầu. Từ ba giá trị này, ta có thể ước lượng độ trễ event tới listener nếu clocks được đồng bộ và semantics đã rõ.

`@ApplicationModuleListener` xử lý event theo semantics transactional/asynchronous của Spring Modulith. Nếu listener chạy trên thread khác, hãy kiểm tra context propagation để log có trace ID/span ID phù hợp; không giả định chỉ vì event là nội bộ tiến trình mà MDC tự được sao chép.

### 10.3. Đừng dùng timestamp làm khóa sắp xếp duy nhất

Hai log có thể có cùng millisecond; hai node có thể lệch clock; event có thể được xử lý không theo thứ tự publish. Khi cần xác định thứ tự, kết hợp:

- Trace parent/child và span links để hiểu quan hệ thực thi.
- Message ID, partition/offset hoặc sequence number để xác định thứ tự message theo broker.
- Aggregate version hoặc event sequence để xác định thứ tự nghiệp vụ.
- Correlation ID để liên kết các bước cùng giao dịch.
- Timestamp để biết thời điểm gần đúng và đo latency khi clock đủ chính xác.

Không kết luận quan hệ nhân quả chỉ từ việc một timestamp nhỏ hơn timestamp khác.

## 11. Kiểm thử timestamp và timezone

### 11.1. Dùng Clock.fixed để kiểm thử ổn định

Thay vì chờ thời gian thực:

~~~java
Instant fixedInstant = Instant.parse("2026-11-27T02:00:00Z");
Clock fixedClock = Clock.fixed(fixedInstant, ZoneOffset.UTC);

OrderService service = new OrderService(fixedClock, eventPublisher);
~~~

Khi gọi `placeOrder()`, event luôn có `occurredAt` bằng instant đã cố định. Test không phụ thuộc timezone của máy developer hoặc CI.

### 11.2. Kiểm tra chuyển đổi timezone

~~~java
Instant instant = Instant.parse("2026-11-27T02:00:00Z");

assertEquals(
    "2026-11-27T09:00+07:00",
    instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toOffsetDateTime()
        .toString()
);
~~~

Test này xác nhận cách biểu diễn của cùng một instant tại timezone được chỉ định. Không đổi instant để “khớp giờ máy”.

### 11.3. Test logging pattern và MDC

Một test logging integration có thể:

1. Đặt timezone JVM khác UTC để chứng minh pattern vẫn in UTC.
2. Đưa trace ID/span ID giả lập vào MDC.
3. Ghi một log có `occurredAt` khác log timestamp.
4. Xác nhận output có offset `Z` và correlation fields.
5. Kiểm tra MDC được dọn sau scope nếu test tự đặt thủ công.

Đừng chỉ kiểm tra cấu hình YAML; hãy kiểm tra **log output thực tế** sau khi logging backend khởi động.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Hai service hiển thị giờ khác nhau | Log theo timezone hệ điều hành khác nhau hoặc thiếu offset. | Chuẩn hóa output UTC và in `Z`/offset tường minh. |
| Log UTC vẫn bị sắp xếp sai | Clock drift giữa các node hoặc collector ghi đè timestamp nguồn. | Kiểm tra NTP/chrony offset và giữ source timestamp riêng. |
| Event time khác log timestamp | Event được xử lý async, commit/queue delay hoặc log được ghi muộn. | Ghi rõ `occurredAt`, `processedAt` và log timestamp; đo event age. |
| Listener log không có trace ID | MDC/tracing context không được truyền qua executor. | Kiểm tra task decorator và executor thực tế. |
| API trả giờ lệch 7 tiếng | Mapping `LocalDateTime`/`Instant`, JDBC session timezone hoặc serialization không nhất quán. | Xác minh Java type, database type, JDBC và JSON offset. |
| Timestamp không có `Z` hoặc offset | Dùng `LocalDateTime` hoặc formatter thiếu zone. | Dùng `Instant`/`OffsetDateTime` và format có offset. |
| Lịch định kỳ chạy sai khi DST đổi | Cộng thời lượng cố định thay vì áp dụng ZoneId. | Dùng IANA ZoneId và định nghĩa chính sách gap/overlap. |
| Duration âm hoặc quá lớn | Đo bằng wall clock bị điều chỉnh. | Dùng `System.nanoTime()` hoặc Micrometer Timer. |
| Log aggregator hiển thị thời gian ingest | Pipeline ghi đè timestamp nguồn. | Giữ source timestamp và observed timestamp thành hai field. |
| Timestamp event không ổn định trong test | Code gọi `Instant.now()` trực tiếp. | Inject `Clock`, dùng `Clock.fixed` trong test. |
| Database hiển thị giờ khác khi query | Session timezone khác nhau; `timestamptz` được hiển thị theo timezone session. | Chuẩn hóa session timezone và giữ instant trong ứng dụng. |
| Trace và log không khớp timeline | Clock skew, sampling hoặc trace context mất ở async boundary. | Kiểm tra clock, propagation và timestamp semantics riêng biệt. |

## 13. Checklist triển khai cho modular monolith

1. **Domain model:** dùng `Instant` cho thời điểm tuyệt đối; chỉ dùng local date/time khi nghiệp vụ thực sự là giờ địa phương.
2. **Event contract:** đặt tên rõ `occurredAt`, `publishedAt`, `processedAt`; không dùng một trường timestamp cho nhiều nghĩa.
3. **Application clock:** inject `Clock` thay cho gọi wall clock rải rác trong domain service.
4. **Logging:** chuẩn hóa UTC, ghi offset, giữ thread name và correlation fields.
5. **Structured logs:** tách source timestamp và observed timestamp; parser không ghi đè thời điểm gốc.
6. **Tracing:** giữ `traceId`/`spanId` trong MDC; kiểm tra context propagation cho listener async.
7. **Infrastructure:** đồng bộ host/node bằng NTP/chrony hoặc time service được quản lý.
8. **Database:** chọn kiểu cột có semantics thời điểm rõ ràng; cấu hình JDBC/Hibernate timezone và kiểm tra round-trip.
9. **Duration:** dùng monotonic timer, không trừ hai wall-clock timestamps để đo latency.
10. **Timezone nghiệp vụ:** lưu IANA ZoneId nếu lịch phải tuân theo quy tắc vùng/DST.
11. **Ordering:** không dựa vào timestamp làm thứ tự nhân quả duy nhất; dùng sequence/offset/trace relationships.
12. **Test:** dùng `Clock.fixed`, kiểm tra formatter, timezone và log output trong CI.

## 14. Bài tập thực hành

### Bài 1 — Chuẩn hóa log UTC

Thay logging pattern của Spring Boot để timestamp có định dạng `yyyy-MM-dd'T'HH:mm:ss.SSSXXX` và timezone UTC. Chạy ứng dụng trên máy có timezone khác UTC, kiểm tra output có `Z` hay không.

### Bài 2 — So sánh event time với processing time

Tạo `OrderPlaced` chứa `occurredAt: Instant`, xử lý bằng `@ApplicationModuleListener` và ghi `processingStartedAt`. Đo khoảng cách giữa hai thời điểm. Giải thích vì sao khoảng cách bao gồm commit/queue/scheduling delay chứ không chỉ thời gian thực thi listener.

### Bài 3 — Kiểm tra clock skew

Trong môi trường lab có nhiều node, kiểm tra trạng thái chrony/NTP. Đối chiếu source timestamp và observed timestamp ở collector. Ghi lại offset và xác định mức sai lệch nào ảnh hưởng tới SLO của bài tập.

### Bài 4 — Database round-trip

Lưu một `Instant` cố định vào cột `TIMESTAMPTZ`, đọc lại qua JDBC/JPA và so sánh instant. Thay session timezone để quan sát cách hiển thị thay đổi nhưng thời điểm vẫn giữ nguyên.

### Bài 5 — DST và lịch địa phương

Tạo lịch định kỳ 09:00 tại một vùng có DST. Thử ngày trước và sau khi đồng hồ chuyển mùa. Xác định cách ứng dụng xử lý gap/overlap và so sánh với cách cộng 24 giờ vào instant.

### Bài 6 — Trace correlation

Ghi log trong publisher và listener. Bật Micrometer Tracing và context propagation cho executor. Xác nhận trace ID được liên kết, span ID có thể khác nhau và timestamp vẫn theo UTC.

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao log nên dùng UTC với offset rõ ràng?

**Đáp án:** Để các service ở timezone khác nhau biểu diễn cùng một thời điểm nhất quán và parser có thể chuyển đổi chính xác.

**Câu 2.** `Instant` khác `LocalDateTime` ở điểm nào?

**Đáp án:** `Instant` là một thời điểm tuyệt đối trên timeline; `LocalDateTime` chỉ là ngày giờ địa phương, không có offset hoặc timezone để xác định thời điểm toàn cầu.

**Câu 3.** Đổi Logback sang UTC có sửa được clock skew không?

**Đáp án:** Không. Formatter chỉ đổi cách hiển thị; đồng hồ hệ điều hành phải được đồng bộ qua NTP/chrony hoặc time service.

**Câu 4.** Vì sao nên dùng `System.nanoTime()` hoặc Micrometer Timer để đo duration?

**Đáp án:** Đây là phép đo monotonic phù hợp với khoảng thời gian; wall clock có thể bị điều chỉnh và nhảy tiến/lùi.

**Câu 5.** `occurredAt` có giống timestamp của log listener không?

**Đáp án:** Không. `occurredAt` là thời điểm nghiệp vụ xảy ra; log listener được ghi khi listener thực thi, có thể muộn hơn do commit, queue hoặc scheduling.

**Câu 6.** Khi nào cần lưu ZoneId bên cạnh Instant?

**Đáp án:** Khi nghiệp vụ cần giữ quy tắc giờ địa phương, chẳng hạn lịch định kỳ theo vùng có DST; Instant một mình chỉ giữ thời điểm tuyệt đối.

## 15. Tài liệu tham khảo

- [Java — Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html): biểu diễn thời điểm tuyệt đối.
- [Java — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html): nguồn thời gian có thể thay thế và kiểm thử bằng fixed clock.
- [Java — ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html): chuyển đổi theo timezone và quy tắc vùng.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): cấu hình logging pattern và logging system.
- [Logback — Layouts](https://logback.qos.ch/manual/layouts.html): date conversion word, timezone và pattern.
- [PostgreSQL — Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html): semantics timestamp with time zone và timestamp without time zone.
- [Hibernate ORM — JDBC time zone](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): cấu hình timezone khi bind/extract temporal values.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): phân biệt Timestamp và ObservedTimestamp.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo duration và xuất timer metrics.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional event listeners và xử lý event trong application modules.

**Ghi nhớ:** hãy lưu và truyền thời điểm tuyệt đối bằng UTC (`Instant`), ghi log có offset rõ ràng, giữ riêng `occurredAt` và thời điểm xử lý, đồng bộ system clock ở hạ tầng, dùng ZoneId cho lịch địa phương và dùng monotonic timer cho duration. Khi đối chiếu log giữa các module, hãy kết hợp timestamp với trace ID, message/sequence ID và ngữ nghĩa event; không suy luận quan hệ nhân quả chỉ từ thứ tự đồng hồ.
