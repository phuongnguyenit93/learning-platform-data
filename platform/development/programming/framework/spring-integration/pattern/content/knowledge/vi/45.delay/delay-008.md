# Múi giờ và thời gian tuyệt đối trong Spring Integration Delayer

## 1. Bài toán: “gửi lúc 09:00” là 09:00 ở đâu?

Một ứng dụng bán hàng nhận yêu cầu: **“Ngày 01/12/2026 lúc 09:00, gửi thông báo cho khách tại Việt Nam.”** Nếu chỉ lưu chuỗi `2026-12-01 09:00`, hệ thống chưa biết thời điểm thực tế. Máy chủ chạy ở UTC, Việt Nam dùng múi giờ `Asia/Ho_Chi_Minh`, còn người vận hành có thể xem log trên một máy có múi giờ khác. Dùng sai múi giờ có thể khiến thông báo được phát lệch nhiều giờ.

Delayer trong Spring Integration có thể trì hoãn một message:

- **Theo khoảng thời gian tương đối:** “chờ thêm 30 giây kể từ lúc nhận”.
- **Theo thời điểm tuyệt đối:** “đến đúng mốc `2026-12-01T02:00:00Z` mới đủ điều kiện phát”.

Trong module **SPRING_INTEGRATION_PATTERN**, lựa chọn thời gian ảnh hưởng đến cách kết hợp Filter, Transformer, Router, Gateway, retry, error channel và correlation. Mục tiêu là xây dựng flow message ít phụ thuộc, dễ mở rộng, kiểm thử và theo dõi được **đến hạn lúc nào**, **đã phát lúc nào** và **vì sao phát muộn**.

Với bài toán ở đầu bài:

~~~text
Người dùng yêu cầu:  01/12/2026 09:00, Asia/Ho_Chi_Minh
Thời điểm UTC:      2026-12-01T02:00:00Z
Instant Java:       2026-12-01T02:00:00Z
Date cho Delayer:   Date.from(instant)  // biểu diễn cùng một mốc
~~~

**Điểm quan trọng:** Delayer nhận **một mốc thời gian đã xác định** để lập lịch. Việc chuyển “giờ địa phương + múi giờ + quy tắc nghiệp vụ” sang thời điểm đó nên xảy ra **trước** Delayer và được kiểm tra rõ ràng.

## 2. Các kiểu thời gian Java cần phân biệt

| Kiểu | Mang thông tin gì? | Vai trò trong luồng |
| --- | --- | --- |
| `LocalDateTime` | Ngày và giờ trên đồng hồ, **không có múi giờ** | Nhận lịch người dùng nhập, ví dụ `2026-12-01T09:00` |
| `ZoneId` | Múi giờ theo quy tắc khu vực | `Asia/Ho_Chi_Minh`, `America/New_York` |
| `ZonedDateTime` | Ngày giờ địa phương + `ZoneId` và offset tương ứng | Diễn giải lịch địa phương thành một mốc rõ ràng |
| `ZoneOffset` | Độ lệch UTC ở một thời điểm, ví dụ `+07:00` | Kiểm tra giờ hợp lệ, xử lý giờ mùa hè |
| `OffsetDateTime` | Ngày giờ + offset cố định tại thời điểm đó | Trao đổi một mốc có offset, nhưng không chứa toàn bộ quy tắc múi giờ khu vực |
| `Instant` | Mốc tuyệt đối trên dòng thời gian UTC | Lưu và so sánh deadline ổn định |
| `java.util.Date` | Mốc thời gian tuyệt đối, độ phân giải mili giây | Giá trị mà biểu thức Delayer có thể dùng làm **thời điểm phát** |
| `long` | Một con số | Khi Delayer hiểu là delay, **đơn vị là mili giây tương đối** |

**`LocalDateTime` không đủ để lập lịch chính xác.** Cùng “09:00” trên đồng hồ ở Hà Nội và New York là hai mốc khác nhau. Ngược lại, một `Instant` có thể được hiển thị thành nhiều giờ địa phương mà vẫn chỉ là **một thời điểm**.

### Từ cùng 09:00 đến những mốc UTC khác nhau

Giả sử ngày **01/12/2026**:

| Người dùng nhập | Múi giờ | Mốc UTC tương ứng |
| --- | --- | --- |
| 09:00 | `Asia/Ho_Chi_Minh` (UTC+07:00) | 02:00Z |
| 09:00 | `UTC` | 09:00Z |
| 09:00 | `America/New_York` (UTC−05:00 vào ngày này) | 14:00Z |

Trong ví dụ, mỗi bản ghi đều là “09:00”, nhưng không nên có cùng deadline nếu đối tượng sử dụng những múi giờ khác nhau.

## 3. Delay số tương đối và `Date` tuyệt đối

Trong Delayer, biểu thức delay có thể cung cấp số mili giây hoặc `java.util.Date`:

| Biểu thức trả về | Cách hiểu | Minh họa |
| --- | --- | --- |
| `30_000L` | Chờ **30 giây tính từ khi Delayer nhận message** | Nhận 10:00:00 → dự kiến phát từ 10:00:30 |
| `Date.from(instant)` | Chờ đến **mốc `instant`** | `2026-12-01T02:00:00Z` |
| `0L` hoặc số âm | Không cần chờ dương | Có thể chuyển ngay |
| `Date` trong quá khứ | Mốc đã đến hạn | Có thể chuyển ngay |
| `null` từ header thiếu | Dùng `defaultDelay` | Tùy cấu hình |

**Không gửi epoch milliseconds dưới dạng `Long` rồi mong Delayer hiểu đó là thời điểm tuyệt đối.** Ví dụ `1_796_090_400_000L` là một số rất lớn; khi được hiểu là *delay tương đối*, nó có thể tạo khoảng chờ nhiều năm. Nếu muốn một deadline, hãy chuyển số epoch đó thành `Date`:

~~~java
long epochMillis = java.time.Instant.parse("2026-12-01T02:00:00Z")
        .toEpochMilli();
java.util.Date deliverAt = new java.util.Date(epochMillis);
~~~

Mặc dù `Date` có tên gợi ý “ngày”, nó biểu diễn một mốc thời gian, không mang `ZoneId`. Cùng một `Date` có thể hiển thị khác nhau ở các máy khác nhau vì định dạng đầu ra sử dụng múi giờ mặc định. **Không dùng `Date.toString()` làm biểu diễn chuẩn của deadline trong log hoặc giao tiếp API.**

## 4. Chuyển giờ địa phương sang mốc tuyệt đối an toàn

### 4.1. Quy trình chuẩn

1. Nhận **ngày**, **giờ địa phương** và **múi giờ IANA** từ dữ liệu đầu vào.
2. Phân tích đầu vào thành `LocalDateTime` và `ZoneId`; kiểm tra giờ có tồn tại và có duy nhất trong múi giờ đó không.
3. Chuyển sang `Instant`.
4. Kiểm tra deadline: còn trong tương lai, không quá xa, tuân thủ quy tắc nghiệp vụ.
5. Tạo `Date.from(instant)` để gửi cho Delayer; đồng thời giữ `eventId` và thông tin múi giờ đã yêu cầu để audit.

~~~mermaid
flowchart LR
    A["Người dùng: 09:00 01/12/2026"] --> B["ZoneId: Asia/Ho_Chi_Minh"]
    B --> C["Kiểm tra ngày giờ trong ZoneRules"]
    C --> D["Instant: 2026-12-01T02:00:00Z"]
    D --> E["Date.from(instant)"]
    E --> F["Delayer: delayExpression"]
    F --> G["Release khi đến hạn"]
~~~

### 4.2. Hàm chuyển đổi có kiểm tra giờ mùa hè

Ví dụ Java 17+ từ chối cả giờ địa phương **không tồn tại** và giờ **có hai cách diễn giải**; ứng dụng có thể chọn một chính sách khác, nhưng phải công khai và kiểm thử được:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public final class ScheduleTimes {
    private ScheduleTimes() {
    }

    public static Instant resolveStrict(
            LocalDateTime localTime, ZoneId zone) {

        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(localTime);

        if (offsets.size() == 0) {
            throw new IllegalArgumentException(
                    "Giờ địa phương không tồn tại trong múi giờ đã chọn");
        }
        if (offsets.size() > 1) {
            throw new IllegalArgumentException(
                    "Giờ địa phương có hai mốc hợp lệ; cần chọn offset");
        }

        return ZonedDateTime.ofStrict(localTime, offsets.get(0), zone)
                .toInstant();
    }
}
~~~

Sử dụng cho giờ Việt Nam:

~~~java
LocalDateTime localTime =
        LocalDateTime.of(2026, 12, 1, 9, 0);
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant deliverAtInstant =
        ScheduleTimes.resolveStrict(localTime, businessZone);

// 2026-12-01T02:00:00Z
System.out.println(deliverAtInstant);

java.util.Date deliverAt = java.util.Date.from(deliverAtInstant);
~~~

Không lấy `ZoneId.systemDefault()` theo thói quen khi lịch thuộc về một khách hàng hoặc thị trường cụ thể. Múi giờ mặc định của JVM có thể thay đổi khi container được triển khai ở môi trường khác.

## 5. Giờ mùa hè (DST): giờ bị thiếu hoặc bị lặp

Một số khu vực thay đổi offset theo mùa. Có hai trường hợp đặc biệt:

- **Gap:** đồng hồ nhảy tiến, một số giờ địa phương không hề tồn tại.
- **Overlap:** đồng hồ lùi, cùng một giờ địa phương xuất hiện **hai lần** với hai offset khác nhau.

Ví dụ với dữ liệu quy tắc múi giờ hiện hành của `America/New_York`:

| Ngày giờ địa phương | Hiện tượng | Cách xử lý trong ví dụ |
| --- | --- | --- |
| `2026-03-08 02:30` | Gap khi chuyển sang giờ mùa hè | Từ chối, yêu cầu chọn giờ khác |
| `2026-11-01 01:30` | Overlap khi trở lại giờ chuẩn | Từ chối cho đến khi chọn offset rõ ràng |
| `2026-12-01 09:00` | Giờ hợp lệ, duy nhất | Chuyển sang `Instant` |

~~~mermaid
flowchart TD
    A["LocalDateTime + ZoneId"] --> B{"Số offset hợp lệ?"}
    B -->|0| C["Gap: từ chối hoặc điều chỉnh theo chính sách"]
    B -->|1| D["Đổi sang Instant"]
    B -->|2| E["Overlap: yêu cầu chọn offset hoặc áp chính sách rõ ràng"]
    C --> F["Trả lỗi có hướng dẫn"]
    E --> F
    D --> G["Lưu deadline tuyệt đối"]
~~~

`ZonedDateTime.of(localTime, zone)` có chính sách mặc định cho gap/overlap; nếu ứng dụng không muốn tự động điều chỉnh, hãy dùng `ZoneRules.getValidOffsets(...)` như ví dụ trên. Đừng coi kết quả Java tự điều chỉnh giờ địa phương là quyết định nghiệp vụ đã được người dùng chấp thuận.

**Quy tắc lịch định kỳ:** nếu người dùng muốn “mỗi ngày lúc 09:00 theo giờ New York”, hãy giữ **giờ địa phương + ZoneId + quy tắc lặp** để tính **deadline mới cho từng lần chạy**. Không thể thay toàn bộ lịch này bằng cách cộng mãi `24 * 60 * 60 * 1000` vào `Instant` trước đó, vì ngày đổi DST có thể dài 23 hoặc 25 giờ. Một Delayer đơn lẻ chỉ trì hoãn **một message đến một deadline**, không tự là scheduler cron.

### Khi nào cần lưu offset người dùng đã chọn?

Với overlap, ứng dụng có thể trình bày cho người dùng hai mốc hợp lệ (offset trước và offset sau khi đổi DST). Khi họ chọn, lưu lựa chọn đó hoặc lưu `Instant` cuối cùng. Không tự đoán “lần 01:30 đầu tiên” hay “lần 01:30 thứ hai” cho những nghiệp vụ quan trọng như lịch thanh toán và thông báo pháp lý.

## 6. Java DSL: Delayer nhận deadline tuyệt đối

Ví dụ khai báo flow có một header `deliverAt` chứa `java.util.Date`. Input channel nhận message từ producer; Delayer chờ đến deadline; `QueueChannel` đầu ra giúp kiểm thử bằng `receive(timeout)`.

Phụ thuộc trong Spring Boot gồm `spring-boot-starter-integration`; bài kiểm thử bên dưới cần `spring-boot-starter-test`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class AbsoluteTimeDelayConfig {

    @Bean("scheduled.in")
    public MessageChannel scheduledInput() {
        return new DirectChannel();
    }

    @Bean("scheduled.ready")
    public PollableChannel scheduledReady() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow absoluteTimeDelayFlow() {
        return IntegrationFlow.from("scheduled.in")
                .delay(spec -> spec
                        .messageGroupId("notifications.absolute-time.delay.v1")
                        .defaultDelay(1_000L)
                        .delayExpression("headers['deliverAt']"))
                .channel("scheduled.ready")
                .get();
    }
}
~~~

Ở đây:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `messageGroupId(...)` | Xác định nhóm message đang chờ của Delayer; quan trọng khi dùng persistent store |
| `delayExpression("headers['deliverAt']")` | Đọc `Date` tuyệt đối từ header |
| `defaultDelay(1_000L)` | **Fallback 1 giây** nếu không có deadline hợp lệ theo quy tắc biểu thức |
| `scheduled.ready` | Channel đầu ra để quan sát thời điểm message đã được release |

**Lưu ý về tính đúng đắn nghiệp vụ:** fallback 1 giây thích hợp để trình bày cơ chế, nhưng có thể không phù hợp với tính năng “phải gửi đúng ngày giờ đã hẹn”. Trong hệ thống thực, hãy **bắt buộc validate `deliverAt` trước khi gửi vào Delayer**, và đưa message sai về nhánh lỗi. Đừng dựa vào fallback để sửa một lịch hẹn bị thiếu.

### Producer: nhận giờ địa phương rồi gửi message

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Date;

import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public final class ScheduledNotificationPublisher {
    private final MessageChannel input;

    // Truyền bean "scheduled.in" khi khởi tạo lớp này.
    public ScheduledNotificationPublisher(MessageChannel input) {
        this.input = input;
    }

    public boolean schedule(String eventId,
                            String payload,
                            LocalDateTime localTime,
                            ZoneId zone) {
        Instant dueAt = ScheduleTimes.resolveStrict(localTime, zone);

        if (!dueAt.isAfter(Instant.now())) {
            throw new IllegalArgumentException(
                    "Deadline phải nằm trong tương lai");
        }

        if (dueAt.isAfter(Instant.now().plusSeconds(90L * 24 * 3600))) {
            throw new IllegalArgumentException(
                    "Deadline vượt giới hạn 90 ngày của ví dụ");
        }

        return input.send(MessageBuilder.withPayload(payload)
                .setHeader("eventId", eventId)
                .setHeader("deliverAt", Date.from(dueAt))
                .setHeader("requestedLocalTime", localTime.toString())
                .setHeader("requestedZoneId", zone.getId())
                .build());
    }
}
~~~

Đoạn mã đặt giới hạn 90 ngày **làm ví dụ chính sách**, không phải giới hạn của Spring Integration. Trong ứng dụng thực, tính `Instant.now()` một lần và kiểm tra hợp đồng nghiệp vụ (khách hàng, quyền sửa lịch, deadline tối đa, trạng thái yêu cầu). Với deadline rất xa, cân nhắc scheduler hoặc kho lịch có chức năng chỉnh sửa/hủy thay vì chỉ lưu Delayer message lâu ngày.

`requestedLocalTime` và `requestedZoneId` phục vụ audit. Header `deliverAt` là mốc tuyệt đối được Delayer dùng để lập lịch; hai header mô tả đầu vào không tự làm Delayer thay đổi deadline nếu sau này chính sách múi giờ được cập nhật.

## 7. Kiểm thử giờ địa phương, DST và release

Kiểm thử tốt cần tách **đúng phép chuyển múi giờ** và **hành vi của scheduler**:

1. Kiểm tra các kết quả thời gian tĩnh, không phụ thuộc tốc độ máy.
2. Kiểm tra Delayer không phát message trước deadline và cuối cùng phát với một timeout đủ rộng.
3. Không đòi phát chính xác từng mili giây; scheduler có thể phát muộn khi JVM hoặc host bận.

### 7.1. Unit test cho chuyển múi giờ

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ScheduleTimesTest {

    @Test
    void convertsVietnamLocalTimeToUtcInstant() {
        Instant actual = ScheduleTimes.resolveStrict(
                LocalDateTime.of(2026, 12, 1, 9, 0),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(Instant.parse("2026-12-01T02:00:00Z"), actual);
    }

    @Test
    void rejectsDstGapAndOverlap() {
        ZoneId newYork = ZoneId.of("America/New_York");

        assertThrows(IllegalArgumentException.class, () ->
                ScheduleTimes.resolveStrict(
                        LocalDateTime.of(2026, 3, 8, 2, 30), newYork));

        assertThrows(IllegalArgumentException.class, () ->
                ScheduleTimes.resolveStrict(
                        LocalDateTime.of(2026, 11, 1, 1, 30), newYork));
    }
}
~~~

Hai kiểm thử New York được minh họa theo dữ liệu múi giờ hiện hành của năm 2026. Các quy tắc dân sự có thể được chính quyền thay đổi; cần cập nhật **tzdb** trên JVM khi các khu vực thay đổi luật.

### 7.2. Integration test cho Delayer

~~~java
import java.time.Instant;
import java.util.Date;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(AbsoluteTimeDelayConfig.class)
class AbsoluteTimeDelayTest {

    @Autowired
    @Qualifier("scheduled.in")
    MessageChannel input;

    @Autowired
    @Qualifier("scheduled.ready")
    PollableChannel ready;

    @Test
    void releasesMessageWhenAbsoluteDeadlineIsReached() {
        Instant deadline = Instant.now().plusMillis(800);

        assertTrue(input.send(MessageBuilder.withPayload("NOTICE-101")
                .setHeader("eventId", "notice-101")
                .setHeader("deliverAt", Date.from(deadline))
                .build()));

        assertNull(ready.receive(100), "Không được phát quá sớm");

        Message<?> released = ready.receive(5_000);
        assertNotNull(released, "Message cần xuất hiện sau deadline");
        assertEquals("NOTICE-101", released.getPayload());
        assertEquals("notice-101",
                released.getHeaders().get("eventId"));
        assertFalse(Instant.now().isBefore(deadline),
                "Đồng hồ phải đi qua deadline trước khi thấy message");
    }
}
~~~

Kiểm thử trên dùng deadline cách lúc gửi khoảng 800 ms và giả định host không bị treo nhiều giây giữa lúc tạo deadline và lúc gửi. Trên CI chịu tải lớn, tăng khoảng cách deadline và timeout để giảm lỗi do scheduler hoặc quá trình khởi tạo máy ảo. Không dùng `Thread.sleep(...)` như bằng chứng duy nhất rằng message đã release.

**Ca cần bổ sung:** deadline nằm trong quá khứ (phát ngay), header `deliverAt` bị thiếu hoặc sai kiểu, message đến hạn khi ứng dụng đang restart, và việc nhiều message cùng deadline gây tăng tải ở consumer.

## 8. Persistence và restart khi đã có deadline tuyệt đối

Nếu Delayer dùng store trong RAM, message đang chờ có thể mất khi tiến trình dừng. Với thông báo quan trọng, có thể thay bằng một `MessageGroupStore` bền vững như `JdbcMessageStore`, dùng `messageGroupId` ổn định.

Đoạn cấu hình bổ sung trong flow đã có `JdbcMessageStore`:

~~~java
.delay(spec -> spec
        .messageGroupId("notifications.absolute-time.delay.v1")
        .messageStore(jdbcMessageStore)
        .defaultDelay(1_000L)
        .delayExpression("headers['deliverAt']"))
~~~

Đây là **đoạn cấu hình**, không phải ứng dụng JDBC chạy độc lập: cần `DataSource`, schema Message Store, transaction và cấu hình bean đầy đủ.

Giả sử deadline là `2026-12-01T02:00:00Z`:

| Tình huống | Kết quả dự kiến |
| --- | --- |
| Restart trước deadline | Delayer đọc message từ store và đặt lịch lại cho mốc tuyệt đối đã lưu |
| Restart sau deadline | Message đã quá hạn, có thể được release sau khi recovery hoàn tất |
| Máy chủ mới có timezone mặc định khác | `Date`/`Instant` vẫn biểu thị cùng mốc; cách hiển thị có thể khác |
| Có cập nhật quy tắc DST trong thời gian chờ | Deadline tuyệt đối **đã lưu không tự thay đổi**; nếu nghiệp vụ cần tuân theo giờ địa phương mới thì phải tính lại lịch có chủ đích |

Phải phân biệt **giữ nguyên một mốc tuyệt đối** và **giữ đúng giờ địa phương mong muốn trong tương lai**. Nếu pháp luật thay đổi offset của một múi giờ trước ngày hẹn, hai mục tiêu có thể xung đột. Lưu `requestedLocalTime` và `requestedZoneId` giúp ứng dụng đánh giá lại lịch khi cần; Delayer không tự giải quyết thay đổi quy tắc lịch của doanh nghiệp.

Persistence chưa bảo đảm exactly-once. Nếu consumer gọi dịch vụ ngoài thành công nhưng process crash trước khi xác nhận, retry/recovery có thể tạo tác động trùng. Dùng `eventId` ổn định, consumer idempotent và cơ chế outbox/inbox khi cần. Nếu hai instance cùng đọc một store, phải kiểm soát sở hữu lịch phát và transaction; chung database không tự bảo đảm chỉ một instance phát mỗi sự kiện.

## 9. Deadline, Gateway timeout và lỗi xử lý

**Deadline của Delayer** xác định thời điểm message bắt đầu đủ điều kiện release. **Gateway reply timeout** xác định caller chờ reply bao lâu; đây là hai mốc khác nhau.

Ví dụ Gateway chỉ chờ 5 giây trong khi Delayer đặt lịch 30 phút: caller có thể hết thời gian chờ từ lâu nhưng message vẫn còn chờ Delayer. Một reply channel tạm thời của Gateway thường không phù hợp với lịch thông báo kéo dài qua restart. Thay vào đó, xác nhận đã tiếp nhận yêu cầu, lưu `eventId` và cung cấp kết quả bất đồng bộ hoặc trạng thái có thể tra cứu.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as API
    participant D as Delayer
    participant C as Consumer
    U->>A: Yêu cầu lịch 09:00 Asia/Ho_Chi_Minh
    A->>A: Đổi thành Instant/Date, validate
    A->>D: Message + deliverAt + eventId
    A-->>U: Xác nhận đã tiếp nhận
    Note over D: Đến mốc UTC đã lưu
    D->>C: Release message
    C-->>A: Ghi kết quả theo eventId
~~~

Lỗi trong lúc Delayer phát sang downstream có thể xảy ra sau khi API đã phản hồi. Spring Integration có các cấu hình như `maxAttempts`, `retryDelay` và `delayedMessageErrorChannel` cho lỗi release; error flow cần ghi nhận sự kiện thất bại và quyết định retry, dead letter hay xử lý thủ công.

Quan trọng hơn, deadline không phải **thời hạn nghiệp vụ**. Một reminder đến hạn trễ do downtime có thể không còn cần gửi vì khách đã thanh toán. Hãy dùng Filter hoặc Service Activator **sau Delayer** để kiểm tra trạng thái mới nhất trước khi gọi dịch vụ ngoài.

## 10. Observability: một mốc tuyệt đối, nhiều cách hiển thị

Mọi log liên quan đến deadline nên có mốc chuẩn UTC:

~~~text
eventId=notification-101
requestedLocalTime=2026-12-01T09:00:00
requestedZoneId=Asia/Ho_Chi_Minh
dueAtUtc=2026-12-01T02:00:00Z
releasedAtUtc=2026-12-01T02:00:00.350Z
releaseLagMs=350
outcome=RELEASED
~~~

Các trường trên là **log do ứng dụng thiết kế**, không mặc định Spring Integration tạo đủ. Một `Date` cần được chuyển sang `Instant` khi ghi log để tránh lệ thuộc timezone của JVM:

~~~java
Date dueAt = Date.from(Instant.parse("2026-12-01T02:00:00Z"));
String utc = dueAt.toInstant().toString();

ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");
String userView = dueAt.toInstant().atZone(userZone).toString();
~~~

`utc` là mốc chuẩn, còn `userView` là cách biểu diễn cho người dùng. Khi muốn định dạng cụ thể, sử dụng `DateTimeFormatter` kèm `ZoneId` đã lưu.

Các metric hữu ích:

| Chỉ số | Công thức/diễn giải | Điều phát hiện |
| --- | --- | --- |
| `pendingCount` | Số message còn trong delay group | Backlog quá lớn |
| `overdueCount` | Số message chờ có `dueAtUtc` trước giờ hiện tại | Scheduler/recovery bị chậm |
| `releaseLagMs` | `releasedAt - dueAt` | Lệch deadline thực tế |
| `invalidLocalTimeCount` | Số lịch bị từ chối do gap/overlap | Vấn đề dữ liệu hoặc chính sách DST |
| `rescheduledCount` | Số lịch được điều chỉnh có chủ đích | Thay đổi timezone, giờ hẹn, yêu cầu nghiệp vụ |
| `duplicateEventCount` | Số `eventId` bị phát/nhận lại | Retry hoặc cạnh tranh nhiều instance |

Một message đủ điều kiện phát ở `dueAt` vẫn có thể ra muộn vì scheduler, database, host hoặc consumer bận. Đo thêm `consumerStartedAt` và `businessCompletedAt` nếu muốn kiểm soát SLA thực sự thay vì chỉ quan sát mốc Delayer release.

### Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Thông báo lệch đúng 7 giờ | Chuyển `LocalDateTime` sang UTC mà thiếu `Asia/Ho_Chi_Minh`, hoặc gán timezone sai |
| Phát lệch một giờ ở khu vực có DST | Quy tắc DST, gap/overlap, timezone database cũ |
| Date trong log khác trên hai server | Dùng `Date.toString()` hoặc timezone JVM mặc định để định dạng |
| Message bị chờ rất lâu | Đã truyền epoch milliseconds dạng `Long`, bị hiểu là delay tương đối |
| Message bị phát ngay | `Date` đã ở quá khứ, số delay bằng 0/âm |
| Không phát sau restart | Store không bền vững, `messageGroupId` đổi, lỗi recovery hoặc serialization |
| Message phát trễ sau deadline | Ứng dụng downtime, scheduler quá tải, DB hoặc downstream chậm |
| Phát hai lần | Retry/recovery/multi-instance; thiếu idempotency theo `eventId` |

## 11. Bài tập thực hành

1. Đổi `2026-12-01 09:00 Asia/Ho_Chi_Minh` sang `Instant`; kiểm chứng kết quả với unit test.
2. Cho cùng giờ `09:00` ở `Asia/Ho_Chi_Minh` và `America/New_York` trong ngày 01/12/2026. Giải thích vì sao deadline khác nhau.
3. Tạo input `2026-03-08 02:30 America/New_York`. Dùng `getValidOffsets(...)` để chứng minh đây là giờ không tồn tại.
4. Tạo input `2026-11-01 01:30 America/New_York`. Liệt kê hai offset hợp lệ; đề xuất chính sách chọn cho người dùng.
5. Xây flow Delayer dùng `headers['deliverAt']`, gửi `Date.from(Instant.now().plusSeconds(5))` và đo độ lệch release.
6. Gửi nhầm epoch milliseconds dưới dạng `Long` vào header delay trong môi trường test. Giải thích vì sao đây là lỗi nghiêm trọng về đơn vị (không cần đợi message đến hạn).
7. Chuyển ứng dụng sang timezone JVM khác trong một môi trường thử nghiệm. Giữ nguyên `Instant` và xác minh deadline không đổi.
8. Dùng persistent store, restart trước/sau deadline; giải thích hành vi khi ứng dụng tắt đúng thời điểm phải phát.
9. Xây yêu cầu “mỗi ngày 09:00 theo giờ của người dùng” và giải thích vì sao nên tạo từng deadline theo lịch địa phương thay vì cộng cố định 24 giờ trên UTC.
10. Thêm Filter phía sau Delayer để bỏ qua reminder đã hết hiệu lực, kể cả khi message được khôi phục sau downtime.

### Câu hỏi tự kiểm tra

- Vì sao `LocalDateTime` chưa đủ xác định một thời điểm trên toàn cầu?
- `Date` có mang thông tin `ZoneId` không? Nó khác `Long` delay như thế nào?
- Vì sao gap và overlap gây rủi ro cho các lịch dựa trên đồng hồ địa phương?
- Vì sao không nên lấy múi giờ mặc định của JVM làm múi giờ khách hàng?
- Nếu múi giờ của một quốc gia đổi luật trong tương lai, deadline tuyệt đối đã lưu có tự đổi không?
- Vì sao `replyTimeout` của Gateway và deadline của Delayer là hai vấn đề độc lập?
- Cần ghi những mốc nào để phân biệt phát muộn với xử lý nghiệp vụ muộn?

## Tài liệu tham khảo

- [Spring Integration Reference — Delayer](https://docs.spring.io/spring-integration/reference/delayer.html): delay tương đối, `java.util.Date` tuyệt đối, scheduler và message store.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): khai báo `IntegrationFlow`, cấu hình endpoint và channel.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): lựa chọn lưu trữ message đang chờ khi restart.
- [Java SE API — java.time](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html): `Instant`, `LocalDateTime`, `ZonedDateTime` và các loại dữ liệu thời gian.
- [Java SE API — ZoneRules](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html): tra cứu offset hợp lệ cho giờ địa phương, gồm DST gap/overlap.
