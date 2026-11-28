# Tạo định danh UUIDv7, tính hạn chót bằng plusSaturating

Một tác vụ có thời hạn thường cần hai giá trị độc lập: một định danh để nhận diện bản ghi và một thời điểm hết hạn để quyết định bản ghi còn hiệu lực hay không. JDK 26 cung cấp hai API chuẩn giúp tạo các giá trị này rõ ràng hơn:

- UUID.ofEpochMillis(long) tạo UUIDv7 với Unix timestamp theo mili giây nằm trong 48 bit đầu.
- Instant.plusSaturating(Duration) cộng một khoảng thời gian vào Instant và chặn kết quả tại Instant.MIN hoặc Instant.MAX nếu phép cộng vượt miền biểu diễn.

Bài thực hành kết hợp hai API để tạo một bản ghi có ID, thời điểm tạo và deadline. Ta sẽ kiểm tra version/variant của UUID, giải mã timestamp, xử lý TTL âm, thử các biên thời gian và xác định khi nào deadline bão hòa là kết quả hợp lệ.

Hai API này là API Java SE chính thức trong JDK 26, không phải preview hoặc incubator. Không cần --enable-preview hay --add-modules.

## 1. Bài toán thực tế

Giả sử hệ thống nhận một yêu cầu tạo tác vụ có thời hạn 15 phút. Ứng dụng cần:

1. Sinh ID duy nhất để lưu tác vụ và trả về cho client.
2. Ghi nhận thời điểm tạo theo UTC.
3. Tính deadline từ thời điểm tạo và TTL.
4. Xác định tác vụ đã hết hạn tại một thời điểm kiểm tra hay chưa.
5. Tránh lỗi tràn số hoặc vượt miền Instant khi TTL quá lớn.
6. Có thể kiểm thử mà không phụ thuộc đồng hồ thật.

Mô hình dữ liệu:

~~~text
Request
  |
  | TTL = 15 minutes
  v
Clock.instant()
  |
  +--> createdAt: Instant
  |
  +--> createdAt.toEpochMilli()
  |       |
  |       v
  |    UUID.ofEpochMillis(...)
  |       |
  |       v
  |    id: UUIDv7
  |
  +--> createdAt.plusSaturating(ttl)
          |
          v
       deadline: Instant
          |
          v
   ExpiringJob(id, createdAt, deadline)
~~~

Ví dụ bản ghi:

~~~json
{
  "id": "019ac7e0-5d00-7a12-9b63-4d7b63a83f21",
  "createdAt": "2026-11-28T00:00:00Z",
  "deadline": "2026-11-28T00:15:00Z"
}
~~~

UUID trong JSON chỉ minh họa hình thức UUIDv7. Khi chạy chương trình, giá trị được tạo mới bằng API của JDK.

## 2. UUIDv7 trong JDK 26

UUID là định danh 128 bit. UUIDv7 dùng Unix timestamp tính theo mili giây trong 48 bit đầu, tiếp theo là các bit version và variant, phần còn lại dành cho dữ liệu ngẫu nhiên theo RFC 9562.

JDK 26 cung cấp factory method:

~~~java
UUID id = UUID.ofEpochMillis(timestampMillis);
~~~

Tham số là số mili giây kể từ 1970-01-01T00:00:00Z, không phải giây, nanosecond hoặc giá trị từ System.nanoTime().

Cấu trúc tổng quát:

~~~text
128 bit
+--------------------------------+------+-------------------------------+
| Unix timestamp (48 bit)        | ver  | rand_a (12 bit)               |
+--------------------------------+------+-------------------------------+
| variant (2 bit)                | rand_b (62 bit)               |
+--------------------------------+--------------------------------+
              48 bit timestamp + 4 bit version + 2 bit variant
                           + 74 bit random
~~~

Các thuộc tính cần nhớ:

| Thuộc tính | Giá trị |
|---|---|
| Version | 7 |
| Variant của UUID chuẩn Java | 2 |
| Timestamp | Unix epoch milliseconds |
| Timestamp field | 48 bit |
| Phần còn lại sau version/variant | 74 bit random |
| JDK hỗ trợ factory chuẩn | JDK 26 trở lên |
| Preview/incubator | Không |

API đặt timestamp vào sáu byte đầu theo thứ tự big-endian. 74 bit còn lại được tạo từ bộ sinh số giả ngẫu nhiên mạnh về mật mã. Factory method từ chối timestamp âm hoặc lớn hơn (1L << 48) - 1.

Ví dụ:

~~~java
import java.time.Instant;
import java.util.UUID;

Instant now = Instant.now();
UUID id = UUID.ofEpochMillis(now.toEpochMilli());

System.out.println(id);
System.out.println(id.version()); // 7
System.out.println(id.variant()); // 2
~~~

UUID.randomUUID() vẫn tạo UUIDv4. Nó không tự chuyển sang UUIDv7 khi ứng dụng chạy trên JDK 26.

### 2.1. Kiểm tra miền timestamp

UUIDv7 chỉ biểu diễn timestamp từ 0 đến 2^48 - 1 mili giây:

~~~java
long maxUuidMillis = (1L << 48) - 1;

UUID first = UUID.ofEpochMillis(0);
UUID last = UUID.ofEpochMillis(maxUuidMillis);
~~~

Các trường hợp sau bị từ chối:

~~~java
UUID.ofEpochMillis(-1);                 // IllegalArgumentException
UUID.ofEpochMillis(1L << 48);            // IllegalArgumentException
~~~

Trong ứng dụng thông thường, timestamp hiện tại nằm trong miền hợp lệ. Tuy nhiên, nếu dùng Clock giả lập, dữ liệu lịch sử hoặc thời gian được nhập từ bên ngoài, vẫn cần xác định rõ miền đầu vào.

Instant có miền biểu diễn rộng hơn rất nhiều so với timestamp 48 bit của UUIDv7. Không phải mọi Instant hợp lệ đều có thể chuyển thành UUIDv7.

### 2.2. Không nhầm timestamp UUIDv7 với UUID.timestamp()

UUID.timestamp() là API dành cho UUID version 1. Gọi nó với UUIDv7 sẽ ném UnsupportedOperationException.

~~~java
UUID id = UUID.ofEpochMillis(Instant.now().toEpochMilli());

System.out.println(id.version()); // 7

// Không dùng cho UUIDv7:
// long timestamp = id.timestamp();
~~~

Nếu cần đọc timestamp UUIDv7, sau khi kiểm tra version và variant, có thể trích xuất 48 bit đầu từ most significant bits:

~~~java
static long uuidV7EpochMillis(UUID id) {
    if (id.version() != 7 || id.variant() != 2) {
        throw new IllegalArgumentException("Expected an IETF UUIDv7");
    }

    return id.getMostSignificantBits() >>> 16;
}
~~~

Phép dịch phải không dấu 16 bit loại bỏ 12 bit rand_a và 4 bit version. Phần còn lại là 48 bit timestamp.

Đây là cách đọc layout UUIDv7 theo RFC 9562. Không áp dụng phép trích xuất này cho UUID version khác.

## 3. Tính hạn chót bằng Instant.plusSaturating()

Instant.plus(Duration) cộng một Duration vào một Instant. Nếu kết quả vượt miền Instant hoặc xảy ra tràn số, phương thức có thể ném DateTimeException hoặc ArithmeticException.

JDK 26 bổ sung:

~~~java
Instant deadline = start.plusSaturating(timeout);
~~~

Phương thức này thực hiện phép cộng với saturated semantics:

- Nếu kết quả sớm hơn Instant.MIN, trả về Instant.MIN.
- Nếu kết quả muộn hơn Instant.MAX, trả về Instant.MAX.
- Nếu kết quả nằm trong miền hợp lệ, trả về kết quả cộng bình thường.

Ví dụ:

~~~java
Instant start = Instant.parse("2026-11-28T00:00:00Z");
Duration timeout = Duration.ofMinutes(15);

Instant deadline = start.plusSaturating(timeout);

System.out.println(deadline);
// 2026-11-28T00:15:00Z
~~~

Trường hợp cộng vượt biên trên:

~~~java
Instant nearMax = Instant.MAX.minusSeconds(2);

Instant result = nearMax.plusSaturating(
        Duration.ofSeconds(10));

System.out.println(result.equals(Instant.MAX)); // true
~~~

Trường hợp trừ vượt biên dưới bằng Duration âm:

~~~java
Instant nearMin = Instant.MIN.plusSeconds(2);

Instant result = nearMin.plusSaturating(
        Duration.ofSeconds(-10));

System.out.println(result.equals(Instant.MIN)); // true
~~~

Instant là immutable. plusSaturating() trả về một Instant mới và không thay đổi đối tượng ban đầu.

### 3.1. So sánh plus() và plusSaturating()

| Tình huống | Instant.plus(Duration) | Instant.plusSaturating(Duration) |
|---|---|---|
| Kết quả nằm trong miền Instant | Trả kết quả | Trả cùng kết quả |
| Kết quả vượt Instant.MAX | Có thể ném exception | Trả Instant.MAX |
| Kết quả sớm hơn Instant.MIN | Có thể ném exception | Trả Instant.MIN |
| Phù hợp tính deadline có thể rất xa | Phải tự xử lý overflow | Có semantics bão hòa sẵn |
| Null Duration | Ném NullPointerException | Ném NullPointerException |

plusSaturating() tránh exception do phép cộng vượt miền Instant. Nó không tự kiểm tra ý nghĩa nghiệp vụ của TTL.

Ví dụ, TTL âm có thể là dữ liệu sai đối với một yêu cầu tạo tác vụ mới. Ứng dụng phải quyết định từ chối TTL âm hay cho phép deadline nằm trong quá khứ. Trong bài thực hành, ta quy định TTL không âm và từ chối giá trị âm trước khi tính deadline.

### 3.2. Saturation không phải phép sửa mọi overflow

plusSaturating() nhận một Duration đã được tạo thành công. Nếu chính phép tạo hoặc cộng Duration đã overflow, lỗi xảy ra trước khi gọi plusSaturating().

Ví dụ:

~~~java
Duration huge = Duration.MAX;

Instant deadline =
        Instant.EPOCH.plusSaturating(huge);

// deadline == Instant.MAX
~~~

Trong khi đó, phép tính tạo Duration không hợp lệ vẫn có thể thất bại:

~~~java
// Phép cộng Duration có thể overflow trước khi tới Instant.
Duration invalid = Duration.ofSeconds(Long.MAX_VALUE)
        .plusSeconds(1);
~~~

Không dùng plusSaturating() như một phép toán bão hòa cho Duration. Nó là phương thức của Instant, nhận Duration làm tham số.

## 4. Quy ước nghiệp vụ cho deadline

Trước khi viết code, cần thống nhất semantics của thời hạn.

Bài thực hành dùng quy ước:

- TTL phải khác null.
- TTL không được âm.
- TTL bằng zero có nghĩa tác vụ hết hạn ngay tại thời điểm tạo.
- Deadline được tính từ cùng một createdAt dùng để sinh UUID.
- Tác vụ hết hạn khi now bằng hoặc sau deadline.

Điều kiện hết hạn:

~~~java
boolean expired = !now.isBefore(deadline);
~~~

Không viết:

~~~java
boolean expired = now.isAfter(deadline);
~~~

Cách viết thứ hai không coi thời điểm bằng deadline là hết hạn. Nếu quy tắc nghiệp vụ là hết hạn tại đúng deadline, cần dùng isBefore() như ví dụ đầu.

Nếu hệ thống cho phép TTL âm để biểu diễn một deadline đã nằm trong quá khứ, hãy bỏ kiểm tra isNegative() và ghi rõ quy tắc đó trong API contract. plusSaturating() vẫn hỗ trợ cộng Duration âm và bão hòa tại Instant.MIN.

## 5. Thiết kế record cho tác vụ có thời hạn

Ta dùng record để gom ba giá trị bất biến:

~~~java
public record ExpiringJob(
        UUID id,
        Instant createdAt,
        Instant deadline) {
}
~~~

Record phù hợp khi dữ liệu chỉ cần giữ trạng thái và cung cấp accessor. Có thể thêm factory method để buộc việc tạo ID và deadline tuân theo cùng một quy tắc.

Một nguyên tắc quan trọng: lấy clock một lần, lưu vào createdAt, rồi dùng chính giá trị đó để tạo UUID và deadline. Không gọi Instant.now() hai lần cho hai trường vì chúng có thể lệch nhau, dù chỉ vài mili giây hoặc nanosecond.

Không nên làm:

~~~java
UUID id = UUID.ofEpochMillis(Instant.now().toEpochMilli());
Instant deadline = Instant.now().plusSaturating(ttl);
~~~

Nên làm:

~~~java
Instant createdAt = clock.instant();

UUID id = UUID.ofEpochMillis(createdAt.toEpochMilli());
Instant deadline = createdAt.plusSaturating(ttl);
~~~

Nhờ đó timestamp trong UUID và trường createdAt xuất phát từ cùng một thời điểm.

## 6. Chương trình thực hành hoàn chỉnh

Tạo file UuidDeadlinePractice.java:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.UUID;

public class UuidDeadlinePractice {

    public record ExpiringJob(
            UUID id,
            Instant createdAt,
            Instant deadline) {

        public ExpiringJob {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(createdAt, "createdAt");
            Objects.requireNonNull(deadline, "deadline");

            if (id.version() != 7 || id.variant() != 2) {
                throw new IllegalArgumentException(
                        "id must be an IETF UUIDv7");
            }

            if (deadline.isBefore(createdAt)) {
                throw new IllegalArgumentException(
                        "deadline must not be before createdAt");
            }
        }

        public static ExpiringJob create(
                Clock clock,
                Duration ttl) {

            Objects.requireNonNull(clock, "clock");
            Objects.requireNonNull(ttl, "ttl");

            if (ttl.isNegative()) {
                throw new IllegalArgumentException(
                        "ttl must not be negative");
            }

            Instant createdAt = clock.instant();

            long epochMillis;
            try {
                epochMillis = createdAt.toEpochMilli();
            } catch (ArithmeticException ex) {
                throw new IllegalArgumentException(
                        "clock instant cannot be represented as epoch milliseconds",
                        ex);
            }

            UUID id;
            try {
                id = UUID.ofEpochMillis(epochMillis);
            } catch (IllegalArgumentException ex) {
                throw new IllegalArgumentException(
                        "clock instant is outside the UUIDv7 timestamp range",
                        ex);
            }

            Instant deadline = createdAt.plusSaturating(ttl);

            return new ExpiringJob(id, createdAt, deadline);
        }

        public boolean isExpired(Instant now) {
            Objects.requireNonNull(now, "now");
            return !now.isBefore(deadline);
        }
    }

    private static void verifyUuid(ExpiringJob job) {
        UUID id = job.id();

        if (id.version() != 7) {
            throw new AssertionError("Expected UUID version 7");
        }

        if (id.variant() != 2) {
            throw new AssertionError("Expected IETF variant 2");
        }

        long embeddedMillis =
                id.getMostSignificantBits() >>> 16;

        if (embeddedMillis != job.createdAt().toEpochMilli()) {
            throw new AssertionError(
                    "UUID timestamp differs from createdAt");
        }
    }

    private static void verifyDeadline(ExpiringJob job) {
        Instant beforeDeadline =
                job.createdAt().plus(Duration.ofMinutes(14));

        if (job.isExpired(beforeDeadline)) {
            throw new AssertionError(
                    "Job expired before its deadline");
        }

        if (!job.isExpired(job.deadline())) {
            throw new AssertionError(
                    "Job must expire exactly at its deadline");
        }
    }

    private static void verifySaturation() {
        Instant high = Instant.MAX.minusSeconds(2)
                .plusSaturating(Duration.ofSeconds(10));

        if (!high.equals(Instant.MAX)) {
            throw new AssertionError(
                    "Positive overflow must saturate at Instant.MAX");
        }

        Instant low = Instant.MIN.plusSeconds(2)
                .plusSaturating(Duration.ofSeconds(-10));

        if (!low.equals(Instant.MIN)) {
            throw new AssertionError(
                    "Negative overflow must saturate at Instant.MIN");
        }

        Instant huge = Instant.EPOCH.plusSaturating(Duration.MAX);

        if (!huge.equals(Instant.MAX)) {
            throw new AssertionError(
                    "Duration.MAX from EPOCH must saturate at Instant.MAX");
        }
    }

    private static void verifyNegativeTtlIsRejected(Clock clock) {
        try {
            ExpiringJob.create(clock, Duration.ofSeconds(-1));
        } catch (IllegalArgumentException expected) {
            return;
        }

        throw new AssertionError("Negative TTL should be rejected");
    }

    public static void main(String[] args) {
        Instant fixedTime =
                Instant.parse("2026-11-28T00:00:00Z");

        Clock clock = Clock.fixed(
                fixedTime,
                ZoneOffset.UTC);

        ExpiringJob job = ExpiringJob.create(
                clock,
                Duration.ofMinutes(15));

        verifyUuid(job);
        verifyDeadline(job);
        verifySaturation();
        verifyNegativeTtlIsRejected(clock);

        System.out.println("ID        : " + job.id());
        System.out.println("Version   : " + job.id().version());
        System.out.println("Variant   : " + job.id().variant());
        System.out.println("CreatedAt : " + job.createdAt());
        System.out.println("Deadline  : " + job.deadline());
        System.out.println("All checks passed.");
    }
}
~~~

### 6.1. Kết quả mong đợi

Timestamp của Clock được cố định để test có kết quả lặp lại. UUID vẫn có phần random nên ID cụ thể sẽ khác giữa các lần chạy.

Các giá trị thời gian phải là:

~~~text
CreatedAt : 2026-11-28T00:00:00Z
Deadline  : 2026-11-28T00:15:00Z
Version   : 7
Variant   : 2
All checks passed.
~~~

Nếu chương trình chạy thành công, các kiểm tra đã xác nhận:

- ID được tạo là UUIDv7.
- Variant đúng theo IETF UUID layout.
- Timestamp trong ID khớp với createdAt theo mili giây.
- Tác vụ chưa hết hạn trước deadline.
- Tác vụ hết hạn đúng tại deadline.
- Phép cộng vượt biên trả Instant.MAX hoặc Instant.MIN.
- TTL âm bị từ chối theo quy ước nghiệp vụ.

## 7. Tại sao phải inject Clock?

Nếu gọi Instant.now() trực tiếp trong logic nghiệp vụ, kết quả test phụ thuộc thời điểm chạy và khó kiểm thử chính xác tại ranh giới.

Clock cho phép thay nguồn thời gian:

~~~java
Clock systemClock = Clock.systemUTC();

Clock testClock = Clock.fixed(
        Instant.parse("2026-11-28T00:00:00Z"),
        ZoneOffset.UTC);
~~~

Trong production:

~~~java
ExpiringJob job = ExpiringJob.create(
        Clock.systemUTC(),
        Duration.ofMinutes(15));
~~~

Trong test:

~~~java
ExpiringJob job = ExpiringJob.create(
        testClock,
        Duration.ofMinutes(15));
~~~

Có thể tạo Clock.offset() để mô phỏng một thời điểm khác hoặc Clock.fixed() để kiểm tra chính xác deadline.

Clock giúp kiểm soát thời gian trong test. Nó không tự bảo đảm đồng hồ hệ thống chạy đơn điệu. Đồng hồ lịch có thể được điều chỉnh bởi NTP, quản trị viên, VM migration hoặc môi trường chạy.

## 8. Phân biệt deadline lịch và timeout đo thời gian thực thi

Instant biểu diễn một điểm trên timeline. Đây là lựa chọn phù hợp khi deadline cần lưu trữ, gửi qua API, so sánh giữa các service hoặc kiểm tra lại sau khi ứng dụng khởi động.

Ví dụ:

~~~java
Instant deadline = createdAt.plusSaturating(
        Duration.ofMinutes(15));
~~~

Tuy nhiên, nếu mục tiêu là đo một khoảng chờ bên trong cùng JVM, đồng hồ wall-clock có thể bị điều chỉnh. Khi cần đo elapsed time hoặc timeout trong một tiến trình, nên dùng đồng hồ monotonic như System.nanoTime() hoặc API concurrency nhận timeout phù hợp.

Phân biệt:

| Nhu cầu | Cách biểu diễn |
|---|---|
| Deadline được lưu trong database | Instant |
| Hạn xử lý được chia sẻ giữa nhiều service | Instant theo UTC |
| TTL đầu vào | Duration |
| Đo thời gian một đoạn code chạy | System.nanoTime() |
| Timeout chờ lock/future trong JVM | API concurrency với timeout/Duration |
| Hạn vào cuối ngày địa phương | ZonedDateTime/LocalDate và ZoneId |

Không dùng System.nanoTime() làm timestamp cho UUIDv7. nanoTime() là bộ đếm phục vụ đo khoảng thời gian, không có mốc Unix Epoch.

## 9. UUIDv7 và tính đơn điệu

UUIDv7 có timestamp ở phần đầu nên UUID có timestamp mili giây khác nhau thường sắp xếp theo thời gian. Tuy nhiên, điều này không tự bảo đảm thứ tự tuyệt đối theo thứ tự gọi hàm.

Các trường hợp cần lưu ý:

- Nhiều UUID được tạo trong cùng một mili giây có phần timestamp giống nhau; suffix random không bảo đảm ID tăng theo thứ tự gọi.
- Đồng hồ hệ thống có thể lùi, làm timestamp của UUID mới nhỏ hơn UUID đã tạo trước.
- Hai máy có clock skew có thể tạo ID không phản ánh đúng thứ tự sự kiện toàn cục.
- ID được tạo trước có thể được ghi vào database sau ID khác do concurrency và transaction scheduling.

Nếu yêu cầu ID tăng nghiêm ngặt trong một phạm vi, caller phải cấp timestamp tăng nghiêm ngặt theo mili giây trước khi gọi UUID.ofEpochMillis(). Việc đó có thể làm timestamp logic chạy trước đồng hồ thật. Nếu cần thứ tự toàn cục qua nhiều node, cần cơ chế phối hợp hoặc sequence/ordering service; UUIDv7 tự nó không cung cấp thứ tự commit toàn cục.

## 10. Deadline bão hòa có ý nghĩa gì với nghiệp vụ?

Nếu TTL rất lớn, plusSaturating() có thể trả Instant.MAX. Đây là kết quả hợp lệ trong miền biểu diễn Java, nhưng hệ thống phải quyết định ý nghĩa của nó.

Một số hệ thống có thể coi Instant.MAX là “không có hạn hết hiệu lực”. Hệ thống khác có thể không cho phép thời điểm này vì database, JSON consumer hoặc giao thức ngoài chỉ hỗ trợ một miền ngày nhỏ hơn.

Trước khi lưu hoặc truyền deadline, cần xác định:

- Database hỗ trợ miền timestamp đến đâu.
- Driver JDBC chuyển Instant sang kiểu SQL nào.
- JSON serializer có hỗ trợ năm rất lớn hay không.
- Hệ thống bên ngoài có giới hạn thời gian không.
- Instant.MAX là deadline thật hay sentinel “không hết hạn”.
- Khi đọc lại, có cần phân biệt giá trị bão hòa với deadline nghiệp vụ thông thường không.

Nếu hệ thống không cho phép deadline vô hạn, hãy kiểm tra TTL tối đa theo nghiệp vụ trước khi gọi plusSaturating(). Saturation tránh lỗi số học nhưng không thay thế giới hạn nghiệp vụ.

Ví dụ giới hạn TTL tối đa 365 ngày:

~~~java
Duration maxTtl = Duration.ofDays(365);

if (ttl.compareTo(maxTtl) > 0) {
    throw new IllegalArgumentException("TTL exceeds policy limit");
}

Instant deadline = createdAt.plusSaturating(ttl);
~~~

Trong hệ thống có chính sách TTL, validation nghiệp vụ nên xảy ra trước phép tính. plusSaturating() vẫn hữu ích như lớp bảo vệ cuối cùng trước miền Instant.

## 11. Duration và ngày theo lịch

Duration.ofDays(1) biểu diễn 24 giờ, không phải “đến cùng giờ vào ngày lịch tiếp theo” trong một múi giờ.

Khi deadline là TTL kỹ thuật, dùng Duration:

~~~java
Instant deadline = createdAt.plusSaturating(
        Duration.ofDays(1));
~~~

Khi yêu cầu là hết hạn lúc 00:00 ngày kế tiếp theo giờ địa phương, hãy dùng ZonedDateTime/LocalDate và ZoneId để xử lý thay đổi daylight saving time:

~~~java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime localNow = ZonedDateTime.now(zone);

ZonedDateTime nextDayStart = localNow.toLocalDate()
        .plusDays(1)
        .atStartOfDay(zone);
~~~

Sau đó có thể chuyển thành Instant để lưu:

~~~java
Instant deadline = nextDayStart.toInstant();
~~~

plusSaturating() nhận Duration và áp dụng trên Instant. Nó không thay thế logic lịch, timezone hoặc ngày nghỉ của nghiệp vụ.

## 12. Lưu UUID và deadline

Một schema SQL có thể dùng:

~~~sql
CREATE TABLE expiring_job (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    deadline TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_expiring_job_deadline
    ON expiring_job (deadline);
~~~

Cú pháp kiểu UUID và timestamp phụ thuộc database. Nếu database không có kiểu UUID native, có thể lưu 16 byte hoặc chuỗi chuẩn theo quy ước thống nhất.

Khi ghi dữ liệu:

- Lưu UUID ở định dạng native UUID hoặc binary 16 byte theo layout chuẩn.
- Lưu createdAt và deadline theo UTC/Instant.
- Dùng unique constraint hoặc primary key để phát hiện ID trùng.
- Index deadline nếu thường xuyên truy vấn bản ghi hết hạn.
- Không dùng timestamp trong UUID thay cho cột created_at nếu cần độ chính xác nanosecond hoặc thời điểm nghiệp vụ chính xác.

Khi truy vấn các tác vụ đã hết hạn tại thời điểm hiện tại:

~~~sql
SELECT id, created_at, deadline
FROM expiring_job
WHERE deadline <= CURRENT_TIMESTAMP;
~~~

Nếu hệ thống dùng clock nguồn riêng cho nghiệp vụ, truyền mốc now đã xác định thay vì dựa vào clock của database một cách không nhất quán.

## 13. An toàn và quyền riêng tư của UUIDv7

UUIDv7 để lộ timestamp ở phần đầu. Người quan sát ID có thể ước lượng thời điểm bản ghi được tạo. Vì vậy:

- UUIDv7 phù hợp làm identifier công khai nếu chấp nhận lộ thời điểm gần đúng.
- Không dùng UUIDv7 làm password, API key hoặc bearer token.
- Không coi UUID là cơ chế phân quyền.
- Giữ unique constraint trong database dù xác suất trùng rất thấp.
- Không nhúng dữ liệu cá nhân hoặc bí mật vào bit tùy biến.

Phần random của API JDK 26 được tạo bằng bộ sinh số giả ngẫu nhiên mạnh về mật mã. Điều đó không biến UUIDv7 thành secret token: timestamp vẫn công khai và mục đích của UUID là định danh.

Nếu cần token bí mật, tạo token có entropy phù hợp và quản lý vòng đời, phạm vi, hạn sử dụng và khả năng thu hồi riêng.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| UUID có version 4 | Dùng UUID.randomUUID() | Dùng UUID.ofEpochMillis() |
| UUID.ofEpochMillis() ném IllegalArgumentException | Timestamp âm hoặc vượt 48 bit | Kiểm tra epoch milliseconds |
| UUID.timestamp() ném UnsupportedOperationException | API này chỉ dành cho UUIDv1 | Kiểm tra version và giải mã UUIDv7 từ most significant bits |
| Deadline cộng quá xa bị exception | Dùng Instant.plus() và vượt miền Instant | Dùng plusSaturating() nếu saturation phù hợp |
| Duration không tạo được | Phép tính Duration đã overflow trước khi gọi Instant | Kiểm tra đầu vào và giới hạn TTL |
| Deadline bằng createdAt nhưng tác vụ vẫn hoạt động | Dùng now.isAfter(deadline) | Dùng !now.isBefore(deadline) nếu equality nghĩa là expired |
| UUID timestamp lệch createdAt | Lấy Instant.now() nhiều lần | Lấy clock.instant() một lần và tái sử dụng |
| UUID không tăng theo thứ tự gọi | Cùng mili giây hoặc clock rollback | Không giả định monotonicity; cấp timestamp logic nếu thật sự cần |
| Deadline Instant.MAX không lưu được | Database/serializer có miền nhỏ hơn Instant | Đặt giới hạn TTL và kiểm tra miền lưu trữ |
| Test thay đổi theo thời gian | Dùng Instant.now() trực tiếp | Inject Clock.fixed() |
| Hạn “ngày mai” lệch giờ địa phương | Dùng Duration.ofDays(1) cho yêu cầu ngày lịch | Dùng ZonedDateTime và ZoneId |
| Hệ thống coi UUID là token | Nhầm ID với secret | Dùng token bảo mật riêng |

## 15. Bài thực hành mở rộng

Thực hiện trên JDK 26:

1. Tạo ExpiringJob bằng Clock.systemUTC() và TTL 15 phút.
2. Kiểm tra UUID.version() bằng 7 và UUID.variant() bằng 2.
3. Trích xuất timestamp UUIDv7 bằng getMostSignificantBits() >>> 16 và so sánh với createdAt.toEpochMilli().
4. Tạo Clock.fixed() và xác nhận createdAt/deadline luôn giống nhau qua nhiều lần chạy.
5. Kiểm tra TTL bằng zero: deadline phải bằng createdAt và tác vụ hết hạn ngay tại createdAt.
6. Kiểm tra TTL âm: xác nhận factory từ chối theo chính sách bài thực hành.
7. Cộng Duration.ofSeconds(10) vào Instant.MAX.minusSeconds(2); xác nhận kết quả là Instant.MAX.
8. Cộng Duration.ofSeconds(-10) vào Instant.MIN.plusSeconds(2); xác nhận kết quả là Instant.MIN.
9. Cộng Duration.MAX vào Instant.EPOCH; xác nhận saturation.
10. So sánh Instant.plus() và plusSaturating() ở trường hợp vượt biên; ghi nhận khác biệt exception.
11. Thử Instant ở trước Unix Epoch và xác nhận UUIDv7 factory từ chối timestamp âm.
12. Lưu ID, createdAt, deadline vào database; đọc lại và kiểm tra equality.
13. Truy vấn tác vụ hết hạn bằng deadline <= current time.
14. Kiểm tra giới hạn miền timestamp của UUID và miền timestamp của database.
15. Viết test kiểm tra deadline bằng chính xác thời điểm now.
16. Viết test để chứng minh hai UUID tạo cùng một mili giây không được đảm bảo tăng theo thứ tự gọi.

**Tiêu chí hoàn thành:** tạo được UUIDv7 bằng API chuẩn JDK 26; hiểu timestamp 48 bit và version/variant; không dùng UUID.timestamp() cho v7; tính deadline bằng Instant.plusSaturating(); phân biệt overflow của Instant và Duration; validation TTL đúng quy ước; kiểm thử bằng Clock; xử lý Instant.MIN/MAX; xác định giới hạn khi lưu trữ và khi chia sẻ deadline giữa các service.

## 16. Tương thích JDK và trạng thái API

| API | Có từ | Trạng thái |
|---|---:|---|
| UUID.ofEpochMillis(long) | JDK 26 | Java SE API chính thức |
| Instant.plusSaturating(Duration) | JDK 26 | Java SE API chính thức |
| Duration.MIN / Duration.MAX | JDK 26 | Java SE API chính thức |
| Clock.fixed() | JDK 8 | API chính thức |
| UUID.randomUUID() | JDK 5 | API chính thức, tạo UUIDv4 |

Không cần bật preview cho UUIDv7 hoặc plusSaturating(). Không cần module incubator.

Ứng dụng biên dịch bằng JDK 25 trở về trước sẽ không tìm thấy hai method mới. Nếu cần hỗ trợ runtime cũ, phải dùng implementation tương thích có kiểm chứng hoặc tự triển khai logic tương đương với xử lý biên rõ ràng; không biên dịch với API JDK 26 rồi kỳ vọng runtime cũ có thể chạy.

Biên dịch trên JDK 26:

~~~powershell
javac --release 26 UuidDeadlinePractice.java
java UuidDeadlinePractice
~~~

Không thêm --enable-preview. Nếu ứng dụng còn dùng API preview hoặc incubator khác, hãy quản lý flag cho phần đó riêng.

## 17. Tài liệu tham khảo chính thức

- [UUID – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/UUID.html) — UUID.ofEpochMillis(), timestamp range, version, variant và UUID.timestamp().
- [Instant – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html) — plusSaturating(), Instant.MIN/MAX và semantics của phép cộng bão hòa.
- [Duration – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html) — Duration.MIN, Duration.MAX, ZERO và các factory tạo Duration.
- [Clock – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html) — clock injection, fixed clock và clock system.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) — JDK-8334015 về UUIDv7 và JDK-8368856 về cộng Duration vào Instant với saturation.
- [RFC 9562: Universally Unique IDentifiers](https://www.rfc-editor.org/rfc/rfc9562.html) — layout UUIDv7, timestamp, random bits và yêu cầu monotonicity.

UUIDv7 cung cấp định danh có timestamp để thuận tiện sắp xếp gần theo thời gian. Instant.plusSaturating() tính deadline mà không để phép cộng vượt miền Instant gây exception. Khi ghép hai API, hãy dùng cùng một createdAt, xác thực TTL theo nghiệp vụ và kiểm tra giới hạn của database cùng hệ thống nhận dữ liệu.

