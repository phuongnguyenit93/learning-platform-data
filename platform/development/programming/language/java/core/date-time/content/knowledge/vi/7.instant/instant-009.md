# Ứng dụng Instant cho nhật ký, thời điểm tạo và hạn hết hiệu lực

Trong Java, `Instant` biểu diễn **một thời điểm tuyệt đối trên dòng thời gian**, không gắn với giờ hiển thị của quốc gia hay múi giờ máy chủ. Đây thường là lựa chọn phù hợp để ghi **sự kiện xảy ra lúc nào** (`occurredAt`), **đối tượng được tạo lúc nào** (`createdAt`), và **dữ liệu/quyền truy cập hết hiệu lực lúc nào** (`expiresAt`).

Ví dụ một phiên đăng nhập được tạo tại `2024-06-01T12:00:00Z`, có thời hạn 30 phút:

~~~text
createdAt = 2024-06-01T12:00:00Z
expiresAt = 2024-06-01T12:30:00Z

12:29:59.999999999Z -> còn hiệu lực
12:30:00Z           -> hết hiệu lực
12:30:00.000000001Z -> hết hiệu lực
~~~

Hai giá trị đều chỉ một mốc xác định và có thể so sánh trực tiếp, không phải đoán “12:30 giờ Việt Nam hay New York?”. Tuy nhiên, `Instant` chỉ giải quyết **biểu diễn thời điểm**; độ chính xác đồng hồ, chính sách hết hạn và tính nhất quán giữa các máy vẫn phải thiết kế riêng.

## 1. Vì sao Instant phù hợp cho mốc sự kiện?

Những kiểu trong `java.time` có mục đích khác nhau:

| Kiểu | Ý nghĩa | Thích hợp cho |
|---|---|---|
| `Instant` | Một thời điểm trên timeline UTC/Java Time-Scale, gồm giây và phần nano. | `createdAt`, `updatedAt`, `occurredAt`, `expiresAt`, audit timestamp. |
| `LocalDateTime` | Ngày và giờ trên lịch, **không có múi giờ hoặc offset**. | Biểu diễn giờ địa phương khi ngữ cảnh vùng được giữ riêng. |
| `ZonedDateTime` | Ngày-giờ với `ZoneId`, offset đã được giải quyết. | Lịch hẹn 09:00 theo vùng, hiển thị giờ theo quy tắc khu vực. |
| `OffsetDateTime` | Ngày-giờ có offset UTC cố định. | Dữ liệu có offset rõ ràng trong API hoặc bản ghi. |
| `Duration` | Độ dài thời gian chính xác theo đơn vị giây/nano. | TTL 15 phút, timeout 30 giây, khoảng cách giữa hai `Instant`. |
| `Clock` | Nguồn cung cấp thời gian cho chương trình. | Gọi giờ hiện tại nhất quán, unit test không phụ thuộc thời gian thực. |

Ví dụ cùng một sự kiện:

~~~text
Instant gốc:                  2024-06-01T12:00:00Z
Hiển thị tại Asia/Ho_Chi_Minh: 2024-06-01T19:00+07:00[Asia/Ho_Chi_Minh]
Hiển thị tại America/New_York: 2024-06-01T08:00-04:00[America/New_York]
~~~

Đây là **ba cách biểu diễn cùng một thời điểm**. `Instant` không làm mất thời gian thực khi người dùng đổi múi giờ; việc đổi vùng chỉ thay đổi cách trình bày.

Java cung cấp:

~~~java
Instant now = Instant.now();
Instant nowFromClock = Instant.now(clock);
Instant parsed = Instant.parse("2024-06-01T12:00:00Z");
~~~

Đây là **mã minh họa** cần `import java.time.Instant;`, một biến `Clock clock` hợp lệ và được đặt trong phương thức/class. Trong production, thường nên **truyền `Clock` vào thành phần nghiệp vụ** để unit test có thể kiểm soát kết quả.

`Instant.now()` phản ánh đồng hồ hệ thống tại lúc đọc; nó **không hứa chính xác tuyệt đối tới nano giây** và không đảm bảo tiến đều giữa các lần đọc. Kiểu dữ liệu hỗ trợ phần nano, nhưng độ phân giải và độ lệch của nguồn đồng hồ là chuyện khác.

## 2. Nhật ký (logging): lưu thời điểm xảy ra sự kiện đúng cách

Giả sử hệ thống nhận một đơn hàng. Có thể tồn tại nhiều mốc cần phân biệt:

- `occurredAt`: thời điểm sự kiện thực sự xảy ra theo nguồn tạo sự kiện.
- `recordedAt` hoặc `receivedAt`: thời điểm hệ thống hiện tại ghi/nhận sự kiện.
- `processedAt`: thời điểm tác vụ xử lý hoàn tất.
- `createdAt` trên đối tượng đơn hàng: thời điểm đối tượng được tạo theo quy ước hệ thống.

Những mốc này **không bắt buộc trùng nhau**. Sự kiện có thể được đẩy qua hàng đợi, trễ mạng, retry hoặc replay. Đừng tùy tiện ghi đè `occurredAt` bằng thời điểm nhận mới nhất rồi làm mất ý nghĩa ban đầu.

Một log ứng dụng có cấu trúc có thể chứa:

~~~json
{
  "eventType": "ORDER_CREATED",
  "eventId": "evt-1001",
  "occurredAt": "2024-06-01T11:59:58.125Z",
  "recordedAt": "2024-06-01T12:00:00Z",
  "orderId": "order-42"
}
~~~

Các trường có giá trị riêng:

- `eventId` định danh sự kiện để phục vụ đối soát và idempotency.
- `orderId` chỉ đối tượng liên quan.
- `occurredAt` và `recordedAt` giữ hai điểm thời gian theo nghĩa của chúng.
- Không lấy `Instant` làm **ID duy nhất**: hai sự kiện có thể có cùng timestamp, nhất là khi đồng hồ có độ phân giải thực tế hạn chế.
- Không mặc định sắp xếp timestamp từ **nhiều máy** là thứ tự nhân quả chính xác; độ lệch đồng hồ và truyền thông có thể đảo thứ tự.

### Ví dụ Java độc lập: hai mốc của một sự kiện

Tệp `AuditEventDemo.java`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class AuditEventDemo {
    record AuditEvent(String type, Instant occurredAt, Instant recordedAt) {}

    public static void main(String[] args) {
        Instant occurred = Instant.parse("2024-06-01T11:59:58.125Z");
        Clock clock = Clock.fixed(
                Instant.parse("2024-06-01T12:00:00Z"),
                ZoneOffset.UTC);

        AuditEvent event = new AuditEvent(
                "ORDER_CREATED", occurred, Instant.now(clock));

        System.out.println("Type: " + event.type());
        System.out.println("Occurred: " + event.occurredAt());
        System.out.println("Recorded: " + event.recordedAt());
        System.out.println("Difference ms: "
                + Duration.between(
                        event.occurredAt(), event.recordedAt()).toMillis());
        System.out.println("ISO round-trip: "
                + Instant.parse(event.occurredAt().toString())
                        .equals(event.occurredAt()));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac AuditEventDemo.java
java AuditEventDemo
~~~

Stdout:

~~~text
Type: ORDER_CREATED
Occurred: 2024-06-01T11:59:58.125Z
Recorded: 2024-06-01T12:00:00Z
Difference ms: 1875
ISO round-trip: true
~~~

`Clock.fixed` giúp kết quả xác định trong ví dụ; nó **không** có nghĩa đồng hồ thật có độ chính xác tuyệt đối. Chênh lệch hai timestamp trong dữ liệu thực cũng có thể mang sai số do offset giữa các máy hoặc nguồn thời gian của sự kiện.

### Nhật ký phân tán và thứ tự sự kiện

Timestamp hữu ích để tra cứu và ghép luồng thời gian, nhưng nó không đủ để xác định mọi quan hệ:

- Hai sự kiện có thể trùng `Instant` hoặc ghi từ các máy có clock lệch nhau.
- Sự kiện được gửi sớm có thể đến sau vì hàng đợi hoặc retry.
- Đối với hệ thống cần thứ tự chắc chắn, bổ sung `sequenceNumber`, vị trí log của broker, version/transaction order, hoặc quan hệ nhân quả phù hợp.
- Giữ trace ID/correlation ID để nối các bước xử lý; không dùng chỉ riêng thời gian làm khóa join.
- Khi dùng log để điều tra, cần ghi múi giờ/đơn vị hiển thị thống nhất và bảo đảm clock máy chủ được đồng bộ, theo dõi offset và drift.

## 3. createdAt: một thời điểm tạo được gán khi nào?

`createdAt` thường phải biểu diễn **mốc tạo ban đầu**, không thay đổi mỗi lần cập nhật hoặc tải lại đối tượng. Với entity do ứng dụng quản lý, một quy ước phổ biến:

1. Chọn nguồn clock của hệ thống hoặc database và thống nhất ý nghĩa.
2. Lấy thời điểm **một lần** trong luồng tạo mới.
3. Gán `createdAt` và lưu cùng dữ liệu.
4. Với lần sửa sau, giữ nguyên `createdAt` và chỉ cập nhật `updatedAt` nếu cần.

Ví dụ mã minh họa:

~~~java
Instant createdAt = clock.instant();
Order order = new Order(orderId, createdAt);
repository.save(order);
~~~

Đoạn mã **không độc lập**, giả định `clock`, `Order`, `orderId` và `repository` đã được định nghĩa. Ý chính là timestamp được xác định một lần trước khi lưu; đừng gọi `Instant.now()` lặp lại cho mọi trường được cho là cùng một mốc.

### Chọn nguồn thời gian và định nghĩa “được tạo”

Cần ghi rõ "tạo lúc nào":

- **Thời điểm bắt đầu xử lý request:** do ứng dụng chụp khi nhận yêu cầu.
- **Thời điểm entity được lập trong ứng dụng:** do tầng dịch vụ chụp.
- **Thời điểm row được ghi hoặc transaction commit:** do database/transaction logic xác định theo hỗ trợ cụ thể.

Ba thời điểm này có thể khác nhau. Giá trị `Instant.now()` ngay trước `save` **không chứng minh** transaction đã commit đúng thời điểm đó. Với hệ thống có nhiều writer, cần thống nhất nguồn authoritative và cách quy đổi để tránh ứng dụng/dữ liệu DB có clock lệch nhau.

Với thao tác retry/idempotent, nếu yêu cầu tạo đã thành công trước đó, lần retry nên **trả lại bản ghi và `createdAt` cũ** thay vì tạo lại timestamp mới. Với cập nhật, cân nhắc thêm `version` để kiểm soát concurrency; timestamp đơn độc không bảo đảm chống ghi đè.

### createdAt và updatedAt khác nhau

| Trường | Khi nào đặt? | Có đổi khi update? |
|---|---|---|
| `createdAt` | Một lần khi tạo theo định nghĩa nghiệp vụ. | Thông thường **không**. |
| `updatedAt` | Khi có thay đổi cần ghi nhận. | Có; theo một quy tắc thống nhất. |
| `deletedAt` | Khi thực hiện soft delete (nếu có). | Khi đổi trạng thái xóa, không đồng nghĩa thời gian xóa vật lý. |
| `publishedAt` | Khi đối tượng thực sự được công bố. | Theo nghiệp vụ; có thể khác `createdAt`. |

Không nên suy luận tất cả các trường trên từ cùng một `now` nếu chúng biểu diễn **những giai đoạn khác nhau**. Nếu hai trường được cố ý đặt cùng thời điểm trong một hành động, nên **chụp clock một lần** để bảo đảm chúng khớp chính xác.

## 4. expiresAt: thời điểm hết hiệu lực và quy tắc biên

Một chính sách TTL (*time to live*) phổ biến:

~~~java
Instant issuedAt = clock.instant();
Instant expiresAt = issuedAt.plus(Duration.ofMinutes(30));
~~~

Đây là đoạn mã minh họa có biến `Clock clock` đã cung cấp trước. Với quy tắc “hợp lệ từ lúc tạo, hết hiệu lực đúng tại mốc `expiresAt`”, khoảng hiệu lực thường được định nghĩa dạng **nửa mở**:

~~~text
[createdAt, expiresAt)

activeAt(now)  = !now.isBefore(createdAt) && now.isBefore(expiresAt)
expiredAt(now) = !now.isBefore(expiresAt)
~~~

Điều này có nghĩa **ở đúng `expiresAt`, đối tượng đã hết hiệu lực**. Không dùng điều kiện `now.isAfter(expiresAt)` làm phép kiểm tra duy nhất vì nó sẽ coi thời điểm **bằng** `expiresAt` vẫn còn hợp lệ.

Nếu business không quan tâm thời điểm trước phát hành, chỉ cần kiểm tra chưa hết hạn: `now.isBefore(expiresAt)`. Nếu yêu cầu đầy đủ khoảng có hiệu lực thì kiểm tra thêm `createdAt`.

### Vì sao chọn Duration để tính TTL?

`Duration.ofMinutes(30)` hoặc `Duration.ofHours(24)` biểu diễn **thời lượng trôi qua**, thích hợp cho phiên tạm, link xác thực, giới hạn thời gian thao tác.

Ngược lại, “hết hạn vào **cuối ngày địa phương**” là quy tắc theo lịch, cần `LocalDate` + `ZoneId` để tìm ranh giới ngày chính xác. Qua DST, một ngày lịch có thể dài 23/25 giờ. Không tự coi “hết hạn cuối ngày mai” tương đương “`now` cộng 48 giờ”.

Ví dụ hết hạn tại **đầu ngày tiếp theo**, là khoảng loại trừ:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate = LocalDate.of(2024, 6, 1);
Instant expiresAt = businessDate.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();
~~~

Đây là đoạn mã minh họa; trong phương thức cần import `java.time.*`. Nó xác định hết hiệu lực khi bước vào `2024-06-02` theo lịch Việt Nam. Muốn hết hạn theo “30 phút kể từ tạo” thì dùng `Duration`, không phải thao tác lịch.

## 5. Ví dụ Java 17+: cấp và kiểm tra phiên có TTL

Tệp `ExpiryPolicyDemo.java` là chương trình độc lập, không phụ thuộc đồng hồ thật. Dùng `Clock.fixed` và `Clock.offset` để kiểm thử trước, đúng, và sau hạn.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class ExpiryPolicyDemo {
    record Session(String id, Instant createdAt, Instant expiresAt) {
        boolean isActiveAt(Instant now) {
            return !now.isBefore(createdAt) && now.isBefore(expiresAt);
        }

        boolean isExpiredAt(Instant now) {
            return !now.isBefore(expiresAt);
        }
    }

    static Session issue(String id, Clock clock, Duration ttl) {
        if (ttl.isNegative() || ttl.isZero()) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        Instant created = clock.instant();
        Instant expiry = created.plus(ttl);
        return new Session(id, created, expiry);
    }

    public static void main(String[] args) {
        Clock origin = Clock.fixed(
                Instant.parse("2024-06-01T12:00:00Z"),
                ZoneOffset.UTC);

        Session session = issue("session-1", origin,
                Duration.ofMinutes(30));

        Instant before = Clock.offset(origin,
                Duration.ofMinutes(29)).instant();
        Instant at = Clock.offset(origin,
                Duration.ofMinutes(30)).instant();
        Instant after = Clock.offset(origin,
                Duration.ofMinutes(31)).instant();

        System.out.println("Created: " + session.createdAt());
        System.out.println("Expires: " + session.expiresAt());
        System.out.println("Active before: " + session.isActiveAt(before));
        System.out.println("Active at: " + session.isActiveAt(at));
        System.out.println("Expired at: " + session.isExpiredAt(at));
        System.out.println("Expired after: " + session.isExpiredAt(after));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ExpiryPolicyDemo.java
java ExpiryPolicyDemo
~~~

Stdout xác định:

~~~text
Created: 2024-06-01T12:00:00Z
Expires: 2024-06-01T12:30:00Z
Active before: true
Active at: false
Expired at: true
Expired after: true
~~~

**Giải thích:**

- `issue` kiểm tra TTL dương để tránh tạo session hết hạn ngay hoặc ngược thời gian khi người gọi nhầm giá trị.
- Chỉ gọi `clock.instant()` **một lần** để tạo `createdAt`, từ đó tính `expiresAt` bằng TTL.
- `isActiveAt` xét thời điểm `now` ở trong khoảng `[createdAt, expiresAt)`.
- Tại thời điểm bằng `expiresAt`, `now.isBefore(expiresAt)` là `false`, do đó hết hiệu lực.
- `Clock.offset` được dùng cho unit test. Không cần `Thread.sleep`, nên test nhanh và ổn định.
- Nếu TTL quá lớn khiến kết quả `created.plus(ttl)` vượt miền `Instant`, Java có thể ném ngoại lệ; production nên giới hạn TTL theo chính sách trước khi cộng.

## 6. Đồng hồ thực tế có thể lệch hoặc nhảy: Instant không tự khắc phục

Mốc `Instant` có ý nghĩa tuyệt đối, nhưng **nguồn tạo timestamp** không nhất thiết đúng tuyệt đối. `Instant.now()` phụ thuộc đồng hồ tường (*wall clock*) của môi trường; hệ thống có thể được chỉnh tiến/lùi thủ công hoặc qua đồng bộ thời gian.

Giả sử hai máy:

~~~text
Máy A: clock nhanh +300 ms
Máy B: clock chậm -200 ms

Hai sự kiện thật cách nhau 100 ms có thể có
timestamp hiển thị đảo thứ tự khi phát sinh trên hai máy.
~~~

Không thể kết luận thứ tự nhân quả chỉ từ timestamp khi không kiểm soát sai số đồng hồ. Đối với hạn hết hiệu lực bảo mật, nếu máy kiểm tra chạy chậm, nó có thể coi token còn hiệu lực lâu hơn dự kiến so với mốc tham chiếu. Nếu máy chạy nhanh, token có thể bị từ chối sớm.

Biện pháp thực tế:

- Đồng bộ và giám sát offset/drift của đồng hồ máy chủ; không suy luận “có nhiều chữ số phần giây” nghĩa là clock chính xác.
- Định nghĩa **nguồn thời gian có thẩm quyền** cho việc phát hành/kiểm tra, đặc biệt khi hệ thống gồm nhiều service hoặc cơ sở dữ liệu.
- Không tin tưởng `createdAt` hay `expiresAt` do **client tự tuyên bố** trong nghiệp vụ yêu cầu kiểm soát phía server.
- Nếu chuẩn token/protocol cho phép một mức clock skew (*leeway*), chỉ áp dụng có chủ đích với giới hạn chặt; leeway sẽ làm thay đổi ranh giới chấp nhận thực tế và không thể thay thế đồng bộ đồng hồ.
- Với token có thể bị thu hồi sớm, `expiresAt` chỉ là **giới hạn thời gian**, không thay thế kiểm tra trạng thái thu hồi/đăng xuất/phân quyền.

### Instant và System.nanoTime() có hai nhiệm vụ khác nhau

`Instant.now()` tạo một mốc theo wall clock thích hợp để **ghi log hoặc lưu createdAt**. `System.nanoTime()` có gốc tùy ý và thích hợp đo **khoảng trôi qua** trong tiến trình, chẳng hạn benchmark hoặc thời gian thực thi. Giá trị `nanoTime()` không thể đưa thẳng vào cơ sở dữ liệu như epoch.

Để tính giới hạn phiên cần **lưu/persist** qua restart, lưu `Instant` hoặc epoch rõ đơn vị. Với timeout nội bộ ngắn, nơi yêu cầu thời lượng không chịu ảnh hưởng điều chỉnh wall clock, có thể sử dụng chênh lệch `System.nanoTime()` theo thiết kế phù hợp.

Không trộn epoch millis và `nanoTime()` vào cùng công thức vì chúng **không có chung gốc đếm**.

## 7. Lưu vào database và serialization API

### 7.1. Chuẩn hóa timestamp

Trong JSON, nên biểu diễn instant theo ISO-8601 có `Z` hoặc một offset rõ ràng:

~~~json
{
  "id": "session-1",
  "createdAt": "2024-06-01T12:00:00Z",
  "expiresAt": "2024-06-01T12:30:00Z"
}
~~~

`Z` cho biết UTC. Chuỗi `2024-06-01T12:00:00` **không có offset**, nên không thể mặc nhiên xem là thời điểm tuyệt đối.

Với Java:

~~~java
Instant createdAt = Instant.parse("2024-06-01T12:00:00Z");
String iso = createdAt.toString();
~~~

Đây là mã minh họa cần import `java.time.Instant` và đặt vào phương thức. Với timestamp có phần nano, `Instant` giữ phần lẻ nhưng **kiểu cột DB, driver, serialization và formatter** có thể làm tròn/cắt. Test round-trip giá trị có phần nano để xác nhận độ phân giải lưu trữ.

### 7.2. Epoch second khác epoch millisecond

Nếu API dùng số nguyên, đặt tên rõ:

~~~text
epochSecond: số giây từ 1970-01-01T00:00:00Z
epochMillis: số mili giây từ mốc đó

epochMillis ≈ epochSecond * 1000
(nếu không có phần lẻ; còn phải xét giới hạn long)
~~~

Với phần lẻ dưới giây, `Instant.getEpochSecond()` và `Instant.getNano()` tách thành phần giây nguyên/nano; `Instant.toEpochMilli()` trả mili giây và không giữ thông tin dưới mili giây. Không dùng `System.nanoTime()` để thay cho epoch nano.

Ví dụ `2024-06-01T12:00:00.123456789Z` lưu bằng mili giây sẽ không thể khôi phục chính xác `456789` nano cuối.

### 7.3. Schema và ranh giới query

Một schema mang ý nghĩa audit/hết hạn có thể trông như sau (**SQL minh họa; kiểu cột chính xác phụ thuộc hệ quản trị**):

~~~sql
CREATE TABLE sessions (
    id          VARCHAR(100) PRIMARY KEY,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at  TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Không phải mọi database đều có cùng tên kiểu/định nghĩa độ phân giải. Hãy kiểm tra rõ driver, session time zone, mapper và quy ước lưu UTC. Đặc biệt, đừng nhầm kiểu timestamp không chứa thông tin vùng với `Instant` đã xác định.

Một truy vấn còn hiệu lực theo chính sách `now < expiresAt`:

~~~sql
SELECT *
FROM sessions
WHERE id = :sessionId
  AND created_at <= :nowInstant
  AND expires_at > :nowInstant;
~~~

Đây là **SQL minh họa** dùng tham số đã bind và kiểu DB tương thích. Các điều kiện lần lượt xác nhận phiên đã bắt đầu và chưa hết hạn. Cần dùng giá trị `nowInstant` theo **cùng nguồn thời gian quy ước** cho toàn bộ lần kiểm tra; nếu DB dùng hàm thời gian riêng, quy tắc phải thống nhất với nơi tạo `expiresAt`.

Đối với truy vấn log trong một khoảng, dùng ranh giới nửa mở:

~~~sql
SELECT *
FROM audit_events
WHERE occurred_at >= :fromInstant
  AND occurred_at <  :untilInstant
ORDER BY occurred_at, event_id;
~~~

Khoảng `[from, until)` tránh trùng bản ghi ở mép khi ghép các cửa sổ. `event_id` ở `ORDER BY` chỉ là tiêu chí phụ tạo thứ tự ổn định, **không chứng minh thứ tự nhân quả giữa các máy**.

### 7.4. Hết hiệu lực về logic khác với xóa vật lý

Một bản ghi đã quá `expiresAt` phải được coi là hết hiệu lực **ngay khi kiểm tra**, dù quá trình dọn dẹp dữ liệu chạy theo lịch và chưa xóa bản ghi đó. Chức năng TTL index/job của database có thể xóa **bất đồng bộ** và không bảo đảm bản ghi biến mất tại chính xác nanosecond `expiresAt`. Vì vậy:

- Kiểm tra điều kiện thời gian trong đường xử lý cần bảo vệ.
- Xem job xóa dữ liệu là cơ chế dọn dẹp/retention, không thay cho phép kiểm tra hiệu lực.
- Khi cập nhật/xác nhận trạng thái quan trọng, áp điều kiện hạn trong thao tác transaction phù hợp để giảm race giữa “kiểm tra còn hạn” và “thực hiện hành động”.

Ví dụ một thao tác đọc rồi cập nhật ở hai request cạnh tranh nhau có thể gặp thời gian đổi trạng thái giữa hai bước; đọc `expiresAt` một lần rồi tự tin rằng nó **sẽ** còn hiệu lực trong suốt quá trình dài là giả định nguy hiểm.

## 8. Tránh các lỗi sai khi thiết kế thời hạn

| Lỗi | Vấn đề | Cách tránh |
|---|---|---|
| Dùng `LocalDateTime.now()` rồi lưu như thể UTC. | Giá trị thiếu offset, phụ thuộc múi giờ môi trường. | Lưu `Instant.now(clock)` khi cần timestamp tuyệt đối. |
| `createdAt` được ghi lại mỗi lần update. | Mất mốc tạo ban đầu và sai audit. | Chỉ gán lúc tạo; dùng `updatedAt` riêng. |
| `expiresAt = createdAt.plus(1, DAYS)` mà nghiệp vụ nói “cuối ngày theo vùng”. | TTL 24 giờ khác ranh giới ngày lịch có thể qua DST. | Tìm đầu ngày kế tiếp bằng `LocalDate` và `ZoneId`. |
| Xem `now.isAfter(expiresAt)` là điều kiện hết hạn đầy đủ. | Thời điểm đúng bằng `expiresAt` chưa bị coi là hết hạn. | Dùng `!now.isBefore(expiresAt)`. |
| Lấy `Instant.now()` nhiều lần cho các trường của cùng một sự kiện. | Tạo độ lệch không cần thiết trong một hành động. | Chụp clock một lần rồi tái dùng. |
| Tin tưởng client tự gửi `expiresAt`. | Client có thể tự kéo dài hạn. | Server tính TTL và xác thực trạng thái. |
| Nghĩ timestamp log luôn xác định thứ tự nhân quả. | Clock lệch và sự kiện bị delay/retry. | Dùng ID, sequence/transaction order/trace metadata. |
| Dùng epoch seconds nhưng API mong millis. | Timestamp bị diễn giải sai nghiêm trọng. | Định nghĩa đơn vị rõ tên/contract. |
| Cho rằng lưu Instant luôn giữ đủ nano trong mọi DB. | Schema/driver có thể giảm độ phân giải. | Kiểm thử round-trip và độ phân giải cột. |
| Coi bản ghi chỉ hợp lệ khi cleanup chưa xóa nó. | Cleanup có thể trễ so với hết hạn logic. | Kiểm tra `expiresAt` trên đường xử lý. |
| Dùng `Thread.sleep` trong unit test để chờ hết hạn. | Test chậm, dễ flaky. | Inject `Clock.fixed` và `Clock.offset`. |

## 9. Unit test: kiểm chứng ranh giới và ý nghĩa thời gian

Nên có các nhóm kiểm thử:

1. **Tạo mới:** `createdAt` được lấy một lần, `expiresAt = createdAt + TTL`, TTL rỗng/âm/không hợp lệ bị từ chối theo chính sách.
2. **Ranh giới:** trước `createdAt` chưa hiệu lực; đúng `createdAt` bắt đầu hiệu lực; trước `expiresAt` còn hiệu lực; **đúng `expiresAt` hết hiệu lực**.
3. **Bất biến tạo mới:** sửa entity không làm đổi `createdAt`, chỉ làm đổi `updatedAt` theo quy tắc.
4. **Serialization:** parse ISO-8601 `Z` và JSON round-trip giữ cùng `Instant`; kiểm tra giây/mili giây, phần nano, timestamp trước 1970 và giới hạn kiểu cột.
5. **Nguồn thời gian:** app sử dụng `Clock` inject, test chạy xác định, không phụ thuộc timezone mặc định và không phải đợi đồng hồ thật.
6. **Hệ thống phân tán:** mô phỏng clock lệch, event đến muộn, idempotent retry và race ở ranh giới hết hạn.
7. **Hiển thị:** cùng một instant khi chuyển sang nhiều `ZoneId` có local time khác nhưng không đổi thời điểm gốc.

### Ví dụ Java chạy được: kiểm tra đúng nanosecond cuối

Tệp `ExpiryBoundaryDemo.java`:

~~~java
import java.time.Instant;

public class ExpiryBoundaryDemo {
    static boolean active(Instant createdAt, Instant expiresAt,
                          Instant now) {
        return !now.isBefore(createdAt) && now.isBefore(expiresAt);
    }

    public static void main(String[] args) {
        Instant created = Instant.parse("2024-06-01T12:00:00Z");
        Instant expires = Instant.parse("2024-06-01T12:30:00Z");

        Instant justBefore = expires.minusNanos(1);

        System.out.println("Before created: "
                + active(created, expires, created.minusNanos(1)));
        System.out.println("At created: "
                + active(created, expires, created));
        System.out.println("Just before expiry: "
                + active(created, expires, justBefore));
        System.out.println("At expiry: "
                + active(created, expires, expires));
        System.out.println("One nano after: "
                + active(created, expires, expires.plusNanos(1)));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ExpiryBoundaryDemo.java
java ExpiryBoundaryDemo
~~~

Stdout:

~~~text
Before created: false
At created: true
Just before expiry: true
At expiry: false
One nano after: false
~~~

Ví dụ không dựa vào độ phân giải đồng hồ thực: tất cả instant được tạo tường minh và thao tác nano là tính toán trên **dữ liệu**, nên kết quả xác định.

## 10. Câu hỏi tự kiểm tra

**1.** Vì sao nên dùng `Instant` thay cho `LocalDateTime` làm `createdAt` trong hệ thống nhiều múi giờ?

**Đáp án:** `Instant` xác định một thời điểm tuyệt đối; `LocalDateTime` thiếu offset/zone nên có thể ánh xạ tới nhiều instant khác nhau. Lưu và trao đổi event timestamp theo instant giảm nhập nhằng khi hệ thống phân tán.

**2.** Nếu `createdAt=12:00Z` và TTL 30 phút thì 12:30Z còn hợp lệ không?

**Đáp án:** Không, theo quy tắc nửa mở `[createdAt, expiresAt)`. Điều kiện còn hiệu lực là `now.isBefore(expiresAt)`; tại đúng mốc hết hạn kết quả là false.

**3.** Tại sao `Instant.now()` có thể chưa đủ để xếp thứ tự tuyệt đối sự kiện giữa hai server?

**Đáp án:** Đồng hồ có thể lệch hoặc bị điều chỉnh, và sự kiện truyền qua mạng có thể bị trễ. Cần cơ chế thứ tự/version/sequence hoặc metadata nhân quả khi thứ tự là yêu cầu quan trọng.

**4.** `createdAt` có nên thay đổi sau một lần retry tạo cùng entity không?

**Đáp án:** Nếu retry là cùng một yêu cầu tạo đã thành công, thông thường nên dùng lại mốc tạo ban đầu và đảm bảo idempotency; không tạo một `createdAt` mới chỉ vì request được gửi lại.

**5.** Có thể coi session hết hạn khi database tự động xóa bản ghi không?

**Đáp án:** Không nên. Hạn hiệu lực logic cần được kiểm tra trên đường xử lý; dọn dẹp/xóa bản ghi có thể diễn ra muộn hơn.

**6.** Muốn thể hiện token hết hạn sau đúng 24 giờ từ lúc phát hành, nên dùng gì?

**Đáp án:** `Instant issuedAt` cộng `Duration.ofHours(24)`. Nếu yêu cầu là hết hạn ở **cuối ngày lịch theo vùng**, dùng ngày lịch và `ZoneId` để tính ranh giới.

## Ghi nhớ

- **`Instant` là loại dữ liệu phù hợp cho mốc sự kiện đã xảy ra, thời điểm tạo và thời điểm hết hạn**, vì nó xác định thời điểm trên timeline mà không phụ thuộc múi giờ hiển thị.
- Với audit log, phân biệt **thời điểm xảy ra**, **thời điểm ghi nhận** và **thời điểm xử lý** khi chúng có ngữ nghĩa khác nhau. Timestamp không phải ID hoặc bảo đảm thứ tự nhân quả.
- **`createdAt` thường chỉ gán một lần**; timestamp cập nhật nên nằm ở trường riêng.
- **`expiresAt` thường được tính từ một `Instant` cộng `Duration`**, với quy tắc hiệu lực nửa mở `[createdAt, expiresAt)`; ở đúng ranh giới hết hạn phải bị từ chối.
- Dùng **`Clock` được inject** để thử nghiệm thời gian xác định và có thể giả lập các mốc ranh giới. Quản lý đồng bộ clock, precision, serialization, database và concurrency là phần thiết yếu của triển khai thực tế.
